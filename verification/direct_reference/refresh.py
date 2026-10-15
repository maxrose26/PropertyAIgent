"""Direct official-summary MVP. Transport is injected; no live CLI or activation.

Idox contract admission is offline only. Arcus dynamic detail is unsupported.
B2 remains sole writer; incomplete/unmapped literal observations stay source-only.
"""
from dataclasses import dataclass, field
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import requests
from verification.stage26b_l1.bolton_literal import parse_summary, semantic_state
from verification.stage26b_l1.request_boundary import BoundaryFailure

MANIFEST_SHA256 = 'ce143eafd498e89129965d098b2f820295fa1d1e1b4d9458f5d9209543071dde'
DISPOSITIONS = {'ADMITTED_DIRECT_ROUTE', 'MANUAL_FALLBACK_CANDIDATE', 'UNSUPPORTED_ROUTE',
                'INSUFFICIENT_RETAINED_EVIDENCE', 'DEFERRED_BY_ACCEPTED_FAILURE'}
# Exact official origins/paths from the frozen source destinations, not suffix matching.
IDOX = {
 'bolton': ('paplanning.bolton.gov.uk', '/online-applications/applicationDetails.do'),
 'bury': ('planning.bury.gov.uk', '/online-applications/applicationDetails.do'),
 'oldham': ('planningpa.oldham.gov.uk', '/online-applications/applicationDetails.do'),
 'stockport': ('planning.stockport.gov.uk', '/PlanningData-live/applicationDetails.do'),
 'tameside': ('publicaccess.tameside.gov.uk', '/online-applications/applicationDetails.do'),
 'trafford': ('pa.trafford.gov.uk', '/online-applications/applicationDetails.do'),
 'wigan': ('planning.wigan.gov.uk', '/online-applications/applicationDetails.do'),
}

def fail(outcome, reason):
    raise BoundaryFailure(outcome, reason)

def load_manifest():
    data = Path(__file__).with_name('manifest.json').read_bytes()
    if hashlib.sha256(data).hexdigest() != MANIFEST_SHA256:
        raise ValueError('Frozen manifest digest mismatch')
    rows = json.loads(data)['rows']
    if len(rows) != 202 or len({r['application_id'] for r in rows}) != 202:
        raise ValueError('Frozen identities mismatch')
    if any(r['admission'] not in DISPOSITIONS for r in rows):
        raise ValueError('Unknown admission disposition')
    return rows

def validate_destination(row):
    if row['admission'] != 'ADMITTED_DIRECT_ROUTE' or row['platform_family'] != 'IDOX':
        fail('UNSUPPORTED_ROUTE', 'Direct transport not admitted')
    u = urlsplit(row['source_url'])
    expected = IDOX.get(row['council'])
    if (expected is None or (u.netloc, u.path) != expected or u.scheme != 'https'
            or u.fragment or '\\' in row['source_url'] or '%' in u.path
            or parse_qs(u.query, keep_blank_values=True) !=
            {'activeTab': ['summary'], 'keyVal': [row['source_identifier']]}
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', row['source_identifier'])):
        fail('UNSUPPORTED_ROUTE', 'Destination outside exact summary contract')

def admitted_row(application_id):
    row = next((r for r in load_manifest() if r['application_id'] == application_id), None)
    if row is None:
        row = next((r for r in extended_admission() if r['application_id'] == application_id), None)
    if row is None:
        fail('UNSUPPORTED_ROUTE', 'Unknown manifest identity')
    validate_destination(row)
    return row

EXTENDED_SHA256 = 'e7ac8017fc0a18c810afb6ba23e09de16fa2c8ebd888f847bb2da4c62c01c5c7'

def extended_admission():
    """Closed six-council offline admission. Individual live availability unproved."""
    raw = Path(__file__).with_name('extended-admission.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXTENDED_SHA256:
        raise ValueError('Extended admission digest mismatch')
    data = json.loads(raw)
    if set(data) != {'schema','census_at','rows'} or data['schema'] != 1:
        raise ValueError('Extended admission schema')
    rows=data['rows']; old=load_manifest(); ids={r['application_id'] for r in old}
    if len(rows)!=512 or len({r['application_id'] for r in rows})!=512:
        raise ValueError('Extended admission count')
    keys={'application_id','council','reference','source_url','source_identifier','platform_family','admission','admission_reason'}
    combined=[r for r in old if r['admission']=='ADMITTED_DIRECT_ROUTE']+rows
    for r in rows:
        if (set(r)!=keys or type(r['application_id']) is not int or r['application_id']<=0
                or r['application_id'] in ids or r['council']=='trafford'
                or not isinstance(r['reference'],str) or not re.fullmatch(r'[A-Za-z0-9 /._-]{1,100}',r['reference'])
                or r['admission_reason']!='OFFLINE_EXACT_IDOX_CONTRACT_ONLY'):
            raise ValueError('Extended admission identity')
        validate_destination(r)
    for key in ('reference','source_identifier','source_url'):
        if len({(r['council'],r[key]) for r in combined})!=len(combined):
            raise ValueError('Extended admission collision')
    return rows

@dataclass
class Budget:
    """Whole invocation accounting. Sequential references; no concurrent use."""
    request_limit: int = 40
    byte_limit: int = 20_000_000
    seconds: float = 150
    started: float = field(default_factory=time.monotonic)
    requests: int = 0
    bytes: int = 0
    rows: int = 0
    failed: bool = False

    def __post_init__(self):
        if not (0 < self.request_limit <= 40 and 0 < self.byte_limit <= 20_000_000
                and 0 < self.seconds <= 150):
            raise ValueError('Budget outside MVP ceiling')

    def check(self):
        if self.failed:
            fail('PARTIAL_RETRIEVAL', 'Run budget previously exhausted')
        if time.monotonic() - self.started >= self.seconds:
            self.failed = True
            fail('TIMEOUT', 'Whole-run deadline')

    def request(self):
        self.check()
        if self.requests >= self.request_limit:
            self.failed = True
            fail('PARTIAL_RETRIEVAL', 'Request ceiling')
        self.requests += 1

    def charge(self, size):
        self.bytes += size
        self.check()
        if self.bytes > self.byte_limit:
            self.failed = True
            fail('PARTIAL_RETRIEVAL', 'Whole-run byte ceiling')

@dataclass
class Observation:
    application_id: int
    reference: str
    source_url: str
    fields: dict
    field_states: dict
    semantic_state: str
    body_sha256: str
    literal_fields: dict
    literal_verified: bool = True
    b2_eligible: bool = False
    verification_scope: str = 'COUPLED'
    field_evidence: dict | None = None

def pending_status_evidence(observation):
    """Positive literal status proof; omission never proves absent decisions."""
    return (observation.literal_verified
        and isinstance(observation.fields,dict)
        and set(observation.fields)=={'Reference','Status','Decision','Decision Issued Date'}
        and observation.fields['Reference']==observation.reference
        and observation.fields['Decision'] is None and observation.fields['Decision Issued Date'] is None
        and observation.field_states == {'reference':'PRESENT_VALUE','status':'PRESENT_VALUE',
            'decision':'NOT_PRESENT','decision_date':'NOT_PRESENT'}
        and observation.literal_fields == {'Reference':observation.reference,'Status':'Awaiting decision'}
        and observation.fields.get('Status') == 'Awaiting decision')


def retrieve(application_id, *, session_factory, budget):
    """Bounded streaming GET with injected Requests-compatible session.

    Invoke under the disposable-worker supervisor for an independent deadline.
    There is no search, redirect following, document or browser path.
    """
    return _retrieve_row(admitted_row(application_id), application_id, session_factory=session_factory, budget=budget)


def _retrieve_row(row, application_id, *, session_factory, budget, diagnostic=None):
    """Same transport/parser; only reviewed fixed callers supply a row."""
    if diagnostic is not None:
        diagnostic.update(stage='DESTINATION',body=b'')
    def mark(stage,body=None):
        if diagnostic is not None:
            diagnostic['stage']=stage
            if body is not None:diagnostic['body']=body
    validate_destination(row)
    budget.check()
    if budget.rows >= 20:
        fail('PARTIAL_RETRIEVAL', 'Reference ceiling')
    budget.rows += 1
    start = time.monotonic()
    reference_bytes = 0
    session = session_factory()
    try:
        session.trust_env = False
        # Avoid inherited auth, cookies or retry-enabled adapters in the concrete adapter.
        for attempt in range(2):
            budget.request()
            response = None
            retry = False
            try:
                remaining = min(40 - (time.monotonic()-start),
                                budget.seconds - (time.monotonic()-budget.started))
                if remaining <= 0:
                    fail('TIMEOUT', 'Reference deadline')
                mark('REQUEST')
                response = session.get(row['source_url'], stream=True, allow_redirects=False,
                    timeout=(min(3, remaining), min(8, remaining)),
                    headers={'Accept': 'text/html', 'Accept-Encoding': 'identity',
                             'User-Agent': 'PropertyAIgent-direct-status/1.0'})
                # Requests must not have internally followed any destination.
                if response.url != row['source_url'] or getattr(response, 'history', []):
                    fail('PARTIAL_RETRIEVAL', 'Unexpected response destination')
                mark('HEADERS')
                status = response.status_code
                if 300 <= status < 400:
                    fail('PARTIAL_RETRIEVAL', 'Redirect not admitted')
                if status == 429:
                    fail('RATE_LIMITED', 'Source rate limit; no retry')
                if status in (502, 503, 504):
                    retry = True
                elif status != 200:
                    fail('SOURCE_UNAVAILABLE', 'HTTP failure is not authoritative not-found')
                else:
                    content_type = response.headers.get('Content-Type', '').lower()
                    if ('text/html' not in content_type or
                        response.headers.get('Content-Encoding', 'identity').lower() not in ('', 'identity') or
                        'attachment' in response.headers.get('Content-Disposition', '').lower()):
                        fail('PARTIAL_RETRIEVAL', 'Non-summary response rejected')
                    declared = response.headers.get('Content-Length')
                    if declared and (not declared.isdigit() or int(declared) > 1_000_000):
                        fail('PARTIAL_RETRIEVAL', 'Declared response bound')
                    mark('BODY')
                    body = bytearray()
                    for chunk in response.iter_content(chunk_size=16384):
                        budget.check()
                        if time.monotonic()-start >= 40:
                            fail('TIMEOUT', 'Reference deadline')
                        if not chunk:
                            continue
                        budget.charge(len(chunk)); reference_bytes += len(chunk)
                        if len(chunk) > 16384 or len(body)+len(chunk) > 1_000_000 or reference_bytes > 2_000_000:
                            fail('PARTIAL_RETRIEVAL', 'Response/reference byte ceiling')
                        body.extend(chunk)
                    if declared and len(body) != int(declared):
                        fail('PARTIAL_RETRIEVAL', 'Truncated response')
                    mark('DECODE',bytes(body))
                    try:
                        html = body.decode('utf-8', errors='strict')
                    except UnicodeDecodeError:
                        fail('PARSER_FAILURE', 'Unsupported response encoding')
                    # Bound parser work in addition to bytes. No script execution.
                    mark('STRUCTURE')
                    if html.count('<') > 20000 or html.lower().count('<tr') > 256:
                        fail('PARSER_FAILURE', 'Parser structural ceiling')
                    mark('SUMMARY_PARSE')
                    fields = parse_summary(html, SimpleNamespace(reference=row['reference']))
                    # Existing parser permits case normalisation; require literal agreement here.
                    mark('EXACT_REFERENCE')
                    from bs4 import BeautifulSoup
                    refs = [tr.find_all(['th','td'])[1].get_text(strip=True)
                        for tr in BeautifulSoup(html, 'html.parser').select('#simpleDetailsTable tr')
                        if len(tr.find_all(['th','td'])) == 2 and
                        tr.find_all(['th','td'])[0].get_text(strip=True) == 'Reference']
                    if refs != [row['reference']]:
                        fail('AMBIGUOUS_SOURCE_RESULT', 'Independent exact displayed identity required')
                    mark('OBSERVATION')
                    missing = any(fields.evidence[k] == 'NOT_PRESENT' for k in ('decision','decision_date'))
                    semantic = 'UNKNOWN_UNMAPPED' if fields.evidence['decision']=='NOT_PRESENT' else semantic_state(fields)
                    budget.check()
                    return Observation(application_id, row['reference'], row['source_url'],
                        dict(fields), dict(fields.evidence), semantic, hashlib.sha256(body).hexdigest(),
                        {tr.find_all(['th','td'])[0].get_text(strip=True): tr.find_all(['th','td'])[1].get_text(strip=True)
                         for tr in BeautifulSoup(html, 'html.parser').select('#simpleDetailsTable tr')
                         if len(tr.find_all(['th','td'])) == 2 and tr.find_all(['th','td'])[0].get_text(strip=True)
                         in ('Reference','Status','Decision','Decision Issued Date')},
                        b2_eligible=not missing and semantic != 'UNKNOWN_UNMAPPED')
            except (requests.Timeout, requests.ConnectionError) as error:
                if attempt:
                    fail('TIMEOUT' if isinstance(error, requests.Timeout) else 'SOURCE_UNAVAILABLE', 'Transport failed')
                retry = True
            finally:
                if response is not None:
                    response.close()
            if retry and attempt:
                fail('SOURCE_UNAVAILABLE', 'Transient retry exhausted')
    finally:
        session.close()


def requests_session():
    """Concrete adapter for separately authorised future use; never called by offline CLI."""
    session = requests.Session()
    session.trust_env = False
    session.auth = None
    session.cookies.clear()
    adapter = requests.adapters.HTTPAdapter(max_retries=0, pool_connections=1, pool_maxsize=1)
    session.mount('https://', adapter)
    return session


def refresh(session, application, council, *, retrieve_evidence):
    """Retrieve after B2's old-state snapshot; no second writer or pre-fetched stamp.

    Literal-only evidence is returned separately, never certified by B2's watermark.
    """
    row = admitted_row(application.id)
    return _refresh_row(session, application, council, row, retrieve_evidence=retrieve_evidence)


def _refresh_row(session, application, council, row, *, retrieve_evidence):
    """Shared B2 handoff; callers must establish their closed source admission.

    This extraction does not admit any additional route in the production batch.
    """
    from app.pipeline.status_verification import verify_application_status
    from app.scrapers.idox_portal import ScrapedApplication
    if (application.reference != row['reference'] or application.council_code != row['council']
            or council.code != row['council'] or urlsplit(council.base_url).hostname != urlsplit(row['source_url']).hostname):
        fail('AMBIGUOUS_SOURCE_RESULT', 'Stored identity differs from admitted manifest')
    observation = None
    failure = None
    raw_before = (application.status, application.decision, application.decision_issued_date)
    def loader(prior):
        nonlocal observation, failure
        try:
            observation = retrieve_evidence()
            if (observation.application_id != row['application_id'] or
                observation.reference != row['reference'] or observation.source_url != row['source_url']):
                fail('AMBIGUOUS_SOURCE_RESULT', 'Handoff identity mismatch')
            if observation.verification_scope == 'INITIAL_STATUS_ONLY':
                if not observation.literal_verified or not observation.b2_eligible:
                    fail('PARTIAL_RETRIEVAL', 'Initial observation not qualified')
                result=ScrapedApplication(reference=row['reference'],
                    fields={'Reference':row['reference'],'Status':observation.fields['Status']},
                    summary_url=row['source_url'],further_info_url='',keyval=None,estimated_unit_count=None,
                    application_category='',opportunity_classification='',qualifies=False)
                result.verification_scope='INITIAL_STATUS_ONLY'
                result.field_evidence=observation.field_evidence
                result.body_sha256=observation.body_sha256
                return result
            if observation.verification_scope == 'FIELD_LEVEL_DATE_ONLY':
                if (not observation.literal_verified or not observation.b2_eligible
                        or observation.field_states.get('reference') != 'PRESENT_VALUE'
                        or observation.field_states.get('decision_date') != 'PRESENT_VALUE'
                        or observation.fields.get('Reference') != row['reference']):
                    fail('PARTIAL_RETRIEVAL', 'Field-level identity/date not qualified')
                result=ScrapedApplication(reference=row['reference'],
                    fields={'Reference':row['reference'],'Decision Issued Date':observation.fields['Decision Issued Date']},
                    summary_url=row['source_url'],further_info_url='',keyval=None,estimated_unit_count=None,
                    application_category='',opportunity_classification='',qualifies=False)
                result.verification_scope='FIELD_LEVEL_DATE_ONLY'
                result.field_evidence=observation.field_evidence
                result.body_sha256=observation.body_sha256
                return result
            if observation.verification_scope == 'UNCHANGED_PENDING_STATUS_ONLY':
                if (not pending_status_evidence(observation) or prior[0] != 'Awaiting decision'
                        or prior[1] is not None or prior[2] is not None):
                    fail('PARTIAL_RETRIEVAL', 'Pending-only evidence cannot verify retained decision/date or changed status')
                result=ScrapedApplication(reference=row['reference'],fields={'Reference':row['reference'],'Status':'Awaiting decision'},
                    summary_url=row['source_url'],further_info_url='',keyval=None,estimated_unit_count=None,
                    application_category='',opportunity_classification='',qualifies=False)
                result.verification_scope='UNCHANGED_PENDING_STATUS_ONLY'
                return result
            if observation.verification_scope != 'COUPLED':fail('PARTIAL_RETRIEVAL','Unknown verification scope')
            if (set(observation.fields) != {'Reference','Status','Decision','Decision Issued Date'}
                or observation.fields['Reference'] != row['reference']
                or set(observation.field_states) != {'reference','status','decision','decision_date'}
                or any(v not in {'PRESENT_VALUE','PRESENT_BLANK'} for v in observation.field_states.values())
                or observation.field_states['reference'] != 'PRESENT_VALUE'
                or observation.field_states['status'] != 'PRESENT_VALUE'
                or semantic_state(observation.fields) == 'UNKNOWN_UNMAPPED'
                or not observation.b2_eligible):
                fail('PARTIAL_RETRIEVAL', 'Literal-only observation; B2 completeness/semantic gate not met')
            for field_name, retained in [('Decision',prior[1]),('Decision Issued Date',prior[2])]:
                if not observation.fields.get(field_name) and retained:
                    fail('PARTIAL_RETRIEVAL', 'Blank cannot certify retained nonblank fact')
            return ScrapedApplication(reference=row['reference'],fields=observation.fields,
                summary_url=row['source_url'], further_info_url='', keyval=None,
                estimated_unit_count=None, application_category='', opportunity_classification='', qualifies=False)
        except BoundaryFailure as error:
            failure = error.outcome
            raise
    result = verify_application_status(session, None, council, application, evidence_loader=loader)
    outcome = failure or {'verified_unchanged':'VERIFIED_UNCHANGED','verified_changed':'VERIFIED_MATERIAL_CHANGE','verified_status_only':'VERIFIED_STATUS_ONLY','field_level_verified':'FIELD_LEVEL_VERIFIED',
        'conflicting_source':'PARTIAL_RETRIEVAL','stale_response':'STALE_RESPONSE',
        'persistence_failed':'PERSISTENCE_FAILED','fetch_failed':'PARSER_FAILURE'}.get(result.outcome,'SOURCE_UNAVAILABLE')
    if outcome == 'VERIFIED_UNCHANGED' and raw_before != (application.status,application.decision,application.decision_issued_date):
        outcome = 'VERIFIED_NON_MATERIAL_CHANGE'
    return {'outcome':outcome,'observation':observation,'b2_outcome':result.outcome,
            'accepted':result.outcome in ('verified_unchanged','verified_changed','verified_status_only','field_level_verified')}
