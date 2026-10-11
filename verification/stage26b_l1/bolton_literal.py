"""Fixed Bolton summary observations. No search, browser, database or writer.

The global classifier's fallback is NEVER evidence for an unmapped label.
Transport is injected; the only command-line entry point is offline rehearsal.
"""
from dataclasses import dataclass
import datetime as dt
import json
import re
import time
from html.parser import HTMLParser
from types import SimpleNamespace
from urllib.parse import urlsplit, parse_qs

from bs4 import BeautifulSoup
from app.scrapers.idox_portal import extract_table_fields
from app.pipeline.lapse_tracking import parse_portal_date
from app.pipeline.material_change import _classify_planning_state
from .contract import assess
from .request_boundary import Boundary, BoundaryFailure, Budget, Policy

VERSION = 'bolton-literal-summary-v1'
BASE = 'https://paplanning.bolton.gov.uk/online-applications'
MAX_ARTIFACT = 16_384
FIELDS = ('Reference', 'Status', 'Decision', 'Decision Issued Date')

@dataclass(frozen=True)
class Case:
    site_id: int
    application_id: int
    reference: str
    key: str
    status: str
    decision: str | None
    date: str | None
    verified: str

    @property
    def url(self):
        return BASE + '/applicationDetails.do?activeTab=summary&keyVal=' + self.key

CASES = (
    Case(129, 202, '00307/26', 'TAPAO1DEGJP00', 'Deposited', None, None,
         '2026-09-28T05:08:55.246164+00:00'),
    Case(140, 74, '21233/25', 'T487AODEM3700', 'Decided',
         'Approve subject to conditions', '2026-09-11',
         '2026-09-13T11:27:32.696252+00:00'),
)

def admit(case):
    if case not in CASES:
        raise ValueError('Unapproved application/reference/source tuple')
    u = urlsplit(case.url)
    if (u.scheme != 'https' or u.netloc != 'paplanning.bolton.gov.uk' or
        u.path != '/online-applications/applicationDetails.do' or u.fragment or
        parse_qs(u.query) != {'activeTab': ['summary'], 'keyVal': [case.key]}):
        raise ValueError('Unapproved source')

def reject(outcome, reason):
    raise BoundaryFailure(outcome, reason)

class SummaryClosure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth, self.selected, self.closed = 0, None, 0
    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            if self.selected is not None:
                reject('PARTIAL_RETRIEVAL', 'nested summary table')
            self.depth += 1
            if dict(attrs).get('id') == 'simpleDetailsTable':
                if sum(k == 'id' for k,v in attrs) != 1:
                    reject('PARSER_FAILURE', 'ambiguous summary identifier')
                self.selected = self.depth
    def handle_endtag(self, tag):
        if tag == 'table':
            if self.selected == self.depth:
                self.closed += 1
                self.selected = None
            self.depth = max(0, self.depth-1)

def parse_summary(html, case):
    """Explicit blank rows establish absence; omitted rows do not.

    Require the summary table, all four factual labels, a closed document and
    no conflicting duplicate fields. Never project the rest of the page.
    """
    if not isinstance(html, str) or not re.search(r'</html\s*>\s*$', html, re.I):
        reject('PARTIAL_RETRIEVAL', 'incomplete summary document')
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.select('table#simpleDetailsTable')
    if len(tables) != 1:
        reject('PARTIAL_RETRIEVAL', 'unique summary table unavailable')
    table = tables[0]
    closure = SummaryClosure()
    closure.feed(html)
    if closure.closed != 1 or closure.selected is not None:
        reject('PARTIAL_RETRIEVAL', 'incomplete summary table')
    values = {k: [] for k in FIELDS}
    for row in table.find_all('tr'):
        cells = row.find_all(['th', 'td'])
        if len(cells) != 2:
            reject('PARSER_FAILURE', 'malformed summary row')
        name, value = (c.get_text(strip=True) for c in cells)
        if name in values:
            values[name].append(value)
    if any(not v for v in values.values()):
        reject('PARTIAL_RETRIEVAL', 'required source field omitted')
    if any(len(set(v)) != 1 for v in values.values()):
        reject('AMBIGUOUS_SOURCE_RESULT', 'conflicting factual fields')
    parsed = extract_table_fields(str(table))  # existing deterministic Idox parser
    fields = {k: parsed[k] or None for k in FIELDS}
    ref = fields['Reference']
    if ref is None:
        reject('PARTIAL_RETRIEVAL', 'displayed reference missing')
    if ref.strip().upper() != case.reference:
        reject('AMBIGUOUS_SOURCE_RESULT', 'displayed reference mismatch')
    fields['Reference'] = case.reference
    if fields['Status'] is None:
        reject('PARTIAL_RETRIEVAL', 'literal status missing')
    for k in ('Status', 'Decision'):
        v = fields[k]
        if v is not None and not re.fullmatch(r'[A-Za-z0-9 ()/.,:;-]{1,256}', v):
            reject('PARSER_FAILURE', 'unsafe or excessive factual field')
    raw_date = fields['Decision Issued Date']
    if raw_date:
        if len(raw_date) > 64:
            reject('PARSER_FAILURE', 'date field exceeds bound')
        date = parse_portal_date(raw_date)
        if date == dt.date.min:
            reject('PARSER_FAILURE', 'decision date unparseable')
        fields['Decision Issued Date'] = date.isoformat()
    return fields

def semantic_state(fields):
    """Evidence-gated entry to the unchanged canonical classifier.

    No decision + an unrecognised status never reaches its permissive fallback.
    This includes Deposited, even with a date present.
    """
    status, decision = fields.get('Status') or '', fields.get('Decision') or ''
    low = status.casefold()
    supported = bool(re.search(r'grant|approv|refus|withdraw', decision, re.I)) or low in {'pending', 'awaiting decision',
        'awaiting determination', 'decided', 'decision made', 'withdrawn'} or \
        'recommend' in low
    if not supported:
        return 'UNKNOWN_UNMAPPED'
    candidate = SimpleNamespace(reference=fields['Reference'], summary_url=BASE,
                                fields=fields)
    same = dict(status=status, decision=decision or None,
                decision_issued_date=fields.get('Decision Issued Date'))
    check = assess(same, candidate, reference=fields['Reference'], base_url=BASE)
    if not check['outcome'].startswith('VERIFIED_'):
        reject(check['outcome'], 'semantic evidence inconsistent or unsupported')
    if low in {'decided', 'decision made'} and not decision:
        return 'decision_outcome_unknown'
    return _classify_planning_state(decision, status)

def interpret(case, fields):
    before = {'Reference': case.reference, 'Status': case.status,
              'Decision': case.decision, 'Decision Issued Date': case.date}
    keys = ('Status', 'Decision', 'Decision Issued Date')
    changed = any(before[k] != fields[k] for k in keys)
    # Loss of previously evidenced terminal facts is incomplete retrieval, not
    # a successful observation that silently clears the accepted facts.
    if (case.decision and not fields['Decision']) or (case.date and not fields['Decision Issued Date']):
        reject('PARTIAL_RETRIEVAL', 'previously evidenced decision fact absent')
    state = semantic_state(fields)
    prior = semantic_state(before)
    outcome = 'SOURCE_FACT_VERIFIED_CHANGED' if changed else 'SOURCE_FACT_VERIFIED_UNCHANGED'
    materiality = 'UNKNOWN_REQUIRES_REVIEW' if changed else 'NO_SOURCE_FACT_CHANGE'
    if prior != 'UNKNOWN_UNMAPPED' and state != 'UNKNOWN_UNMAPPED':
        candidate = SimpleNamespace(reference=case.reference, summary_url=case.url, fields=fields)
        comparison = assess(dict(status=case.status, decision=case.decision,
                                 decision_issued_date=case.date), candidate,
                            reference=case.reference, base_url=BASE)
        outcome = comparison['outcome']
        if not outcome.startswith('VERIFIED_'):
            reject(outcome, 'semantic transition requires review')
        materiality = 'MATERIAL' if outcome == 'VERIFIED_MATERIAL_CHANGE' else 'NON_MATERIAL'
    qualification = ('Authoritative source status verified; normalised planning-state meaning not established.'
                     if state == 'UNKNOWN_UNMAPPED' else
                     'Current semantic state established; prior unmapped state prevents transition materiality determination.'
                     if prior == 'UNKNOWN_UNMAPPED' and changed else 'Accepted semantic evidence rules applied.')
    return dict(outcome=outcome, source_fact_verified=True,
        source_status_raw=fields['Status'], source_decision_raw=fields['Decision'],
        source_decision_date=fields['Decision Issued Date'], semantic_state=state,
        semantic_qualification=qualification,
        source_fact_change='CHANGED' if changed else 'UNCHANGED',
        semantic_materiality=materiality)

def http_dispatch(method, url, **kwargs):
    """Existing Requests streaming transport; never called by offline entrypoint.

    No environment proxy/credential inheritance; exact URL GET only.
    The separately reviewed future launcher must explicitly supply this adapter.
    """
    if method != 'GET' or url not in {c.url for c in CASES} or kwargs.get('data'):
        reject('PARTIAL_RETRIEVAL', 'transport scope rejected')
    session = __import__('requests').Session()
    session.trust_env = False
    try:
        response = session.get(url, stream=True, allow_redirects=False, timeout=(3, 8))
    except BaseException:
        session.close()
        raise
    original_close = response.close
    def close():
        try: original_close()
        finally: session.close()
    response.close = close
    return response

def run(*, sha, dispatch, qualification='MOCKED_EXPECTATION'):
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('Exact code identity required')
    if qualification not in {'MOCKED_EXPECTATION', 'exact_public_council_summary'}:
        raise ValueError('Source qualification')
    budget = Budget(requests=4, per_reference=2, total_bytes=2_000_000,
                    response_bytes=1_000_000, seconds=45)
    results = []
    for case in CASES:
        admit(case)
        boundary = Boundary(Policy('bolton', case.reference, 'idox', BASE, BASE+'/search.do'), budget, dispatch)
        boundary.keyval = case.key
        def accounted_dispatch(*args, **kwargs):
            response = dispatch(*args, **kwargs)
            if 300 <= response.status_code < 400:
                boundary.redirects += 1  # observed redirect, even when denied
            return response
        boundary.dispatch = accounted_dispatch
        started = time.monotonic()
        row = dict(council='bolton', application_id=case.application_id,
                   reference=case.reference, source_url=case.url,
                   source_qualification=qualification)
        try:
            budget.check()
            status, headers, body = boundary.request('GET', case.url)
            if 300 <= status < 400:
                reject('PARTIAL_RETRIEVAL', 'redirect not admitted')
            if 'html' not in headers.get('Content-Type', '').lower():
                reject('PARTIAL_RETRIEVAL', 'summary media type unavailable')
            row.update(interpret(case, parse_summary(body.decode('utf-8', errors='strict'), case)))
        except BoundaryFailure as exc:
            budget.failure = budget.failure or exc
            row.update(outcome=exc.outcome, source_fact_verified=False,
                       qualification=exc.reason)
        except Exception:
            budget.failure = budget.failure or BoundaryFailure('PARSER_FAILURE', 'summary decoding or parsing failed')
            row.update(outcome='PARSER_FAILURE', source_fact_verified=False,
                       qualification='summary decoding or parsing failed')
        finally:
            boundary.close()
        row.update(requests=boundary.requests, redirects=boundary.redirects,
                   retries=boundary.retries, received_bytes=boundary.received_bytes,
                   attempted=boundary.requests > 0,
                   elapsed_seconds=round(time.monotonic()-started, 3))
        results.append(row)
    complete = all(r['source_fact_verified'] for r in results) and not budget.failure
    artifact = dict(manifest_version=VERSION, repository_sha=sha,
        execution_time=dt.datetime.now(dt.timezone.utc).isoformat(),
        execution_status='COMPLETE' if complete else 'FAIL', persistence=False,
        budget_state='WITHIN_LIMITS' if complete else 'FAILED_OR_INCOMPLETE',
        requests=sum(r['requests'] for r in results),
        received_bytes=sum(r['received_bytes'] for r in results), results=results)
    encode(artifact)
    validate(artifact)
    return artifact

def encode(artifact):
    data = json.dumps(artifact, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if len(data) > MAX_ARTIFACT:
        raise ValueError('Audit artifact overflow')
    return data

def validate(artifact):
    """Closed audit contract; literal success cannot imply semantic materiality."""
    if set(artifact) != {'manifest_version','repository_sha','execution_time',
            'execution_status','persistence','budget_state','requests','received_bytes','results'}:
        raise ValueError('Audit fields')
    if artifact['manifest_version'] != VERSION or artifact['persistence'] is not False or \
        not re.fullmatch('[0-9a-f]{40}', artifact['repository_sha']):
        raise ValueError('Audit provenance')
    dt.datetime.fromisoformat(artifact['execution_time'])
    rows = artifact['results']
    if not isinstance(rows,list) or len(rows) != 2:
        raise ValueError('Complete fixed scope required')
    common = {'council','application_id','reference','source_url','source_qualification',
              'outcome','source_fact_verified','requests','redirects','retries',
              'received_bytes','attempted','elapsed_seconds'}
    fact = {'source_status_raw','source_decision_raw','source_decision_date',
            'semantic_state','semantic_qualification','source_fact_change','semantic_materiality'}
    from .contract import FAILURES
    for case,row in zip(CASES,rows):
        if (row.get('council'),row.get('application_id'),row.get('reference'),row.get('source_url')) != \
            ('bolton',case.application_id,case.reference,case.url):
            raise ValueError('Audit source identity')
        if row.get('source_qualification') not in {'MOCKED_EXPECTATION','exact_public_council_summary'}:
            raise ValueError('Audit source qualification')
        for key,cap in [('requests',2),('redirects',2),('retries',1),('received_bytes',2_131_072)]:
            if type(row.get(key)) is not int or not 0 <= row[key] <= cap:
                raise ValueError('Audit accounting')
        if type(row.get('attempted')) is not bool or row['attempted'] != (row['requests']>0):
            raise ValueError('Audit attempt state')
        if not isinstance(row.get('elapsed_seconds'),(int,float)) or not 0 <= row['elapsed_seconds'] <= 51:
            raise ValueError('Audit elapsed time')
        if row.get('source_fact_verified') is True:
            if set(row) != common|fact or not row['attempted'] or row['received_bytes']>2_000_000:
                raise ValueError('Verified source fields')
            if row['outcome'] not in {'SOURCE_FACT_VERIFIED_CHANGED','SOURCE_FACT_VERIFIED_UNCHANGED',
                    'VERIFIED_UNCHANGED','VERIFIED_NON_MATERIAL_CHANGE','VERIFIED_MATERIAL_CHANGE'}:
                raise ValueError('Verified outcome')
            fields = {'Reference':case.reference,'Status':row['source_status_raw'],
                'Decision':row['source_decision_raw'],'Decision Issued Date':row['source_decision_date']}
            if any(value is not None and not isinstance(value,str) for value in fields.values()):
                raise ValueError('Audit literal types')
            for key in ('Status','Decision'):
                value = fields[key]
                if value is not None and not re.fullmatch(r'[A-Za-z0-9 ()/.,:;-]{1,256}',value):
                    raise ValueError('Audit literal privacy')
            if not fields['Status']:
                raise ValueError('Audit missing status')
            date = fields['Decision Issued Date']
            if date is not None and (not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date) or
                    dt.date.fromisoformat(date).isoformat() != date):
                raise ValueError('Audit date')
            expected = interpret(case,fields)
            if any(row[k] != value for k,value in expected.items()):
                raise ValueError('Audit source/semantic separation')
        elif row.get('source_fact_verified') is False:
            if set(row) != common|{'qualification'} or row['outcome'] not in FAILURES or \
                not re.fullmatch('[A-Za-z0-9 _/.-]{1,120}',row['qualification']):
                raise ValueError('Failure must not certify facts')
        else:
            raise ValueError('Audit verification flag')
    if artifact['requests'] != sum(r['requests'] for r in rows) or \
        artifact['received_bytes'] != sum(r['received_bytes'] for r in rows):
        raise ValueError('Audit totals')
    complete = all(r['source_fact_verified'] for r in rows)
    if artifact['execution_status'] != ('COMPLETE' if complete else 'FAIL') or \
        artifact['budget_state'] != ('WITHIN_LIMITS' if complete else 'FAILED_OR_INCOMPLETE'):
        raise ValueError('Audit completion')
    if complete and (artifact['requests']>4 or artifact['received_bytes']>2_000_000):
        raise ValueError('Audit run budget')
    encode(artifact)
