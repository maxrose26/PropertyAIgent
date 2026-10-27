"""Local fixtures for the bounded end-to-end connection. EVERYTHING HERE IS SYNTHETIC TEST DATA.

No council is contacted and no production database is touched. Idox listings run the production reader (`idox_window.run`) over synthetic pages; Arcus listings run the
production capture and qualification code (`capture_fields`, `qualify_segment`) over locator doubles, so the browser layer itself is NOT exercised here. Archives are written
by an isolated test publisher and are labelled so they can never be mistaken for live evidence. Synthetic contract tests qualify no real council markup.
"""
import hashlib
import json
from datetime import date
from html import escape
from unittest.mock import patch
from urllib.parse import urlsplit

from app.ingestion.arcus_adapter import ArcusListingContract
from app.ingestion.idox_adapter import IdoxListingContract
from app.pipeline.discovery_contract import SOURCE_ROOTS
from tests.test_discovery_idox_window import SORT, Response
from tests.test_discovery_screening_assessment import Fields, immediate
from verification.direct_reference.arcus_http_probe import FACT_FIELDS, PLANNING_OBJECT, record_observation
from verification.direct_reference.fixtures import Session
from verification.discovery import material_qualification as q
from verification.discovery import screening_capture as cap
from verification.discovery.arcus_ui_audit import validate as validate_arcus
from verification.discovery.arcus_ui_config import MANCHESTER, ROCHDALE, SALFORD, assessment_dated_config
from verification.discovery.arcus_ui_window import qualify_segment
from verification.discovery.finite_acceptance import ARCUS, SEMANTICS
from verification.discovery.idox_window import WindowConfig, run

LABEL = 'TEST_ARCHIVE_NOT_LIVE_EVIDENCE'
TEST_QUALIFICATION = 'e' * 64      # a clearly synthetic stand-in; NOT a registered qualification identity
IDOX_COUNCILS = ('bolton', 'bury', 'oldham', 'stockport', 'tameside', 'wigan')
ARCUS_COUNCILS = ('manchester', 'rochdale', 'salford')
IDOX_PREFIX = {c: '/online-applications' for c in IDOX_COUNCILS} | {'stockport': '/PlanningData-live'}
ARCUS_BASE = {'manchester': MANCHESTER, 'rochdale': ROCHDALE, 'salford': SALFORD}

# One proposal per frozen v3 outcome (verified against the rule in the unit tests, not assumed).
SCHEME = 'Erection of 20 residential dwellings'                          # ADMIT_SCHEME
ASSESS = 'Erection of up to 20 residential dwellings'                    # ADMIT_FOR_ASSESSMENT
NO_COUNT = 'Residential development, number of dwellings unknown'        # ROUTE_COUNT_UNCONFIRMED
EXTENSION = 'Erection of a single storey rear extension'                 # RETAIN_NOT_RESIDENTIAL_SUPPLY
BELOW = 'Erection of 4 dwellings'                                        # RETAIN_BELOW_THRESHOLD (threshold 10)
PARENT = 'Discharge of condition 3 attached to planning permission 01234/26'      # RETAIN_RELATED_TO_PARENT


class IsolatedTestPublisher:
    """Writes the raw audit to a private test directory, reads it back and reports exactly what it read. Never GitHub, never the evidence branch.

    mode: ok | corrupt_write (the stored bytes differ, so readback fails) | wrong_sha (the receipt names another hash) | wrong_bytes | raises
    """

    def __init__(self, root, mode='ok'):
        self.root, self.mode, self.calls = root, mode, []

    def __call__(self, raw):
        self.calls.append(hashlib.sha256(raw).hexdigest())
        if self.mode == 'raises':
            raise OSError('isolated test publisher unavailable')
        sha = hashlib.sha256(raw).hexdigest()
        target = self.root / (sha + '.json')
        target.write_bytes(raw[:-1] + b'X' if self.mode == 'corrupt_write' else raw)
        back = target.read_bytes()
        return dict(commit=hashlib.sha1(raw).hexdigest(), path='docs/design/TEST-ONLY-NOT-LIVE-EVIDENCE/' + sha + '.json',
                    sha256='0' * 64 if self.mode == 'wrong_sha' else sha, bytes=len(raw) + (1 if self.mode == 'wrong_bytes' else 0),
                    readback_verified=back == raw, label=LABEL)


def outer():
    """A synthetic, compliant outer-supervisor object (the release does not yet produce one in the ledger's shape)."""
    return dict(exit_code=0, cleanup='CLOSED', live_owned_survivors=0, expired=False, limit_hit=None, peak_owned_rss=1000, elapsed_seconds=1)


def entry(reference, proposal, *, address='1 Test Street, Testville TT1 1TT', key=None, record_id=None, application_type=None, received=None, validated=None):
    return dict(reference=reference, proposal=proposal, address=address, key=key or ('K' + hashlib.sha256(reference.encode()).hexdigest()[:11].upper()),
                record_id=record_id or ('a' + hashlib.sha256(reference.encode()).hexdigest()[:17]), application_type=application_type, received=received, validated=validated)


class _Response(Response):
    headers = {'Content-Type': 'text/html; charset=utf-8'}      # Wigan's reader refuses a response that does not declare a qualified charset


def idox_key(council, e):
    """The detail key in the council's own shape (Bury's reader requires `_BURY_DCAPR_<digits>`)."""
    return '_BURY_DCAPR_' + str(int(hashlib.sha256(e['reference'].encode()).hexdigest()[:8], 16)) if council == 'bury' else e['key']


def mid(start, end):
    return start + (end - start) // 2


# ----------------------------------------------------------------------------------------------------------------------------- Idox
def _fmt(d):
    return d.strftime('%a %d %b %Y')


def _idox_form(semantics, start='', end=''):
    stem = 'Received' if semantics == 'RECEIVED' else 'Validated'
    return ('<html><body><form method="post" action="advancedSearchResults.do?action=firstPage">\n'
            '<input type="hidden" name="_csrf" value="SYNTHETIC_STATE_DO_NOT_EXPORT_8675309"/>\n'
            f'<input name="date(application{stem}Start)" value="{start}"/>\n<input name="date(application{stem}End)" value="{end}"/>\n'
            '<input name="searchCriteria.reference" value=""/>\n<select name="searchCriteria.status"><option value="">All</option></select>\n'
            '<input type="submit" name="action" value="Search"/>\n</form></body></html>').encode()


def _idox_page(council, entries, start, end):
    when = mid(start, end)
    rows = ''.join(
        f'<li class="searchresult"><a class="summaryLink" href="applicationDetails.do?keyVal={idox_key(council, e)}&amp;activeTab=summary">{escape(e["proposal"])}</a>'
        f'<p class="address">{escape(e["address"])}</p><p class="metaInfo">Ref. No: {e["reference"]} · Received: {_fmt(e["received"] or when)} · Validated: {_fmt(e["validated"] or when)}</p></li>'
        for e in entries)
    n = len(entries)
    sort = SORT.replace(b'/online-applications/', (IDOX_PREFIX[council] + '/').encode())
    page = (f'<html><h1>Planning – Results for Application Search</h1><select id="resultsPerPage"><option value="10" selected>10</option></select>'
            f'<p class="pager">Showing 1-{n} of {n}</p><ul id="searchresults">{rows}</ul></html>').encode()
    return page.replace(b'</html>', sort + b'</html>')


def idox_config(council, start, end):
    return WindowConfig(council=council, semantics=SEMANTICS[council], start=start, end=end, max_transport_retries=0)


def idox_audit(council, entries, start, end):
    """The PRODUCTION Idox reader run over synthetic pages; returns the audit it produced."""
    cfg = idox_config(council, start, end)
    echo = _idox_form(cfg.semantics, start.strftime('%d/%m/%Y'), end.strftime('%d/%m/%Y'))
    page = _idox_page(council, entries, start, end)
    bodies = iter([_idox_form(cfg.semantics), page, page, echo])
    return run(lambda *args, **kwargs: _Response(next(bodies)), cfg)


def idox_contract(council, start, end, *, name=None):
    return IdoxListingContract(name or f'e2e-idox-{council}', idox_config(council, start, end), TEST_QUALIFICATION)


def idox_detail_target(council, record, case='e2e_idox_detail'):
    return dict(admission='ADMITTED_DIRECT_ROUTE', platform_family='IDOX', application_id=None, application_role='UNKNOWN', site_relationship='UNKNOWN',
                case=case, council=council, reference=record['reference'], source_identifier=record['source_record_id'], source_url=record['source_url'])


def idox_detail(target, body):
    """The production Idox detail worker over a synthetic transport that answers the target's own URL."""
    transport = Session(body)
    with patch('verification.direct_reference.refresh.requests_session', lambda: transport), \
         patch('verification.direct_reference.batch_supervisor.resource_limits', lambda: None):
        raw = q.idox_worker(target)
    raw.update(process_cleanup='CLOSED', live_owned_survivors=0, peak_owned_rss=100, owned_processes_seen=1, supervisor_seconds=1, supervisor_limit_hit=False)
    return raw


# ---------------------------------------------------------------------------------------------------------------------------- Arcus
def arcus_config(council, start, end):
    return assessment_dated_config(ARCUS_BASE[council], start.isoformat(), end.isoformat())


def arcus_case(council):
    return 'discovery_' + council + '_ui_window'


def arcus_audit(council, entries, start, end, *, budget=None):
    """Production capture + qualification over locator doubles; the audit is assembled exactly as the reader's own fields require."""
    cfg = arcus_config(council, start, end)
    origin = '{0.scheme}://{0.netloc}'.format(urlsplit(cfg.destination))
    when = mid(start, end)
    cards = []
    for e in entries:
        texts = [f'Reference\n{e["reference"]}', 'Applicant\nPRIVATE']
        if cfg.row_date:
            texts.insert(1, f'Valid Date\n{(e["validated"] or when).strftime("%d/%m/%Y")}')
        if e['proposal'] is not None:
            texts.append(f'{e.get("label", "Description")}\n{e["proposal"]}')
        if e.get('both_labels'):
            texts.append(f'Proposal\n{e["proposal"]}')      # two aliases for the proposal: the production projection must call this CONFLICTING
        if e['address'] is not None:
            texts.append(f'Site Address\n{e["address"]}')
        if e['application_type']:
            texts.append(f'Application type\n{e["application_type"]}')
        fields = [dict(label='Reference', value=e['reference'])] + ([dict(label='Valid Date', value=(e['validated'] or when).strftime('%d/%m/%Y'))] if cfg.row_date else [])
        cards.append(dict(fields=fields, links=[dict(text=e['reference'], href=f'{origin}/pr/s/detail/{e["record_id"]}?c__r=Arcus_BE_Public_Register')],
                          assessment_capture=immediate(cap.capture_fields(Fields(texts)))))
    n = len(entries)
    rows = qualify_segment(f'Showing 1 to {n} of {n} results', cards, 1, config=cfg)[3]
    audit = dict(case=arcus_case(council), destination=cfg.destination, persistence=False, failure=None, safety_failure=False, safety_events=[], cleanup='CONTEXT_BROWSER_CLOSED',
                 process_cleanup='CLOSED', live_owned_survivors=0, supervisor_limit_hit=False, enumeration_evidence='COUNT_RECONCILED', completeness='UNKNOWN',
                 applied_interval=[cfg.start, cfg.end], requested_interval=[cfg.start, cfg.end], requests=20, decoded_bytes=1000, encoded_bytes=800, outbound_payload_bytes=100,
                 public_ui_posts=1, measured_public_ui_posts=1, supervisor_seconds=5, peak_owned_rss=100000, pages=1, navigations=1, redirects=0, listing_records=rows,
                 listing_segments=[dict(ordinal=1, first=1, last=n, total=n, evidence_sha256=hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest())])
    if budget is not None:
        audit.update(execution_budget=budget, stage_timings={'NAVIGATION': 1200, 'READY': 600, 'CRITERIA': 300, 'SEGMENT': [300]})
    return audit


def arcus_contract(council, start, end, *, budget=None, name=None):
    return ArcusListingContract(name or f'e2e-arcus-{council}', arcus_config(council, start, end), arcus_case(council), validate_arcus, qualify_segment, TEST_QUALIFICATION, budget)


def arcus_detail_target(council, record, case='e2e_arcus_detail'):
    return dict(case=case, council=council, reference=record['reference'], source_identifier=record['source_record_id'], source_url=record['source_url'], application_id=None)


def arcus_detail_audit(target, *, status='Under Consideration', reference=None):
    """A supervised-detail audit shaped as the committee route's own (`tests/test_arcus_transport.py::worker`), built for an arbitrary synthetic target."""
    reference = reference or target['reference']
    fields = {FACT_FIELDS[k]: {'value': v} for k, v in dict(reference=reference, status=status).items()}
    data = {'context': {'globalValueProviders': [{'values': {'records': {target['source_identifier']: {PLANNING_OBJECT: {'record': {'id': target['source_identifier'], 'fields': fields}}}}}}]}}
    body = json.dumps(data).encode()
    source = record_observation(data, target['source_identifier'], target['reference'])
    source.update(attempted=True, outcome='GUEST_JSON_OBSERVED', http_status=200, received_bytes=len(body), response_sha256=hashlib.sha256(body).hexdigest())
    origin = target['source_url'].split('/pr/')[0]
    return dict(case=target['case'], application_id=None, reference=target['reference'], destination=target['source_url'], persistence=False, requests=40, redirects=0,
                decoded_bytes=10000000, encoded_bytes=3000000, pages=1, navigations=2, local_frames=0, peak_owned_rss=800000000, owned_processes_seen=8, live_owned_survivors=0,
                elapsed_seconds=14, supervisor_seconds=15, supervisor_limit_hit=False, process_cleanup='CLOSED', cleanup='CONTEXT_BROWSER_CLOSED', requested_origins=[origin],
                navigated_origins=[origin], navigation_mismatch=None, safety_failure=False, safety_events=[], failure='UNREVIEWED_METHOD', record_http_probe=source)


def window(council):
    """A fixed synthetic Monday-to-Sunday week (never described as any real observation)."""
    start = date(2026, 11, 9)
    return start, date(2026, 11, 15)
