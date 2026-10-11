"""Fixed Bolton summary observations. No search, browser, database or writer.

The global classifier's fallback is NEVER evidence for an unmapped label.
Transport is injected; the only command-line entry point is offline rehearsal.
"""
from dataclasses import dataclass
import datetime as dt
import json
import re
import time
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
    if not re.search(r'</table\s*>', html, re.I):
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
        any(x in low for x in ('committee', 'resolution', 'recommend'))
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
            row.update(outcome=exc.outcome, source_fact_verified=False,
                       qualification=exc.reason)
        except Exception:
            row.update(outcome='PARSER_FAILURE', source_fact_verified=False,
                       qualification='summary decoding or parsing failed')
        finally:
            boundary.close()
        row.update(requests=boundary.requests, redirects=boundary.redirects,
                   retries=boundary.retries, received_bytes=boundary.received_bytes,
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
    return artifact

def encode(artifact):
    data = json.dumps(artifact, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if len(data) > MAX_ARTIFACT:
        raise ValueError('Audit artifact overflow')
    return data
