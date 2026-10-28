"""Oldham single-page count-signal probe (dormant; inactive until the owner approves its exact registration hash).

Question: for a SINGLE-PAGE Oldham search (page 1 shows no pager and no total), does the portal state its explicit result total when page 2 is requested in the same session? The paging calibration
(`idox_paging_calibration`) showed that on a two-page result the page after the last answers with an empty-range `Showing a - b of T` marker. Whether that holds when page 1 had no pager is unknown.
This probe asks exactly once, in one fresh session, reusing the calibration's boundary, structural projection, registration/authority, containment and private storage unchanged:

  form, exact date search, sort (page 1), ONE page-2 GET in the portal's own link shape, the refine-view criteria/session check, and the MANDATORY invalid-page control (`page=0`): at most 6 requests.

`classify_probe` is a pure function of the safe export with outcomes fixed before any live response. The original five records enter only as hashes (registration fields); they are compared, never forced. Nothing here
changes a parser, proof or completeness classification, and the evidence is diagnostic, never a registered collection audit.
"""
import hashlib
import json
import re
from datetime import date
from urllib.parse import urlencode

from app.scrapers.discovery_idox import ListingError, explicit_zero, parse_page, source_url
from verification.bolton_recon.recon import Failure
from verification.stage26b_l1.request_boundary import BoundaryFailure, Budget

from . import idox_paging_calibration as cal
from . import idox_response_diagnostic as base
from .idox_sort import require_reference_sort, sort_payload
from .idox_window import WindowConfig

KIND = 'OLDHAM_SINGLE_PAGE_COUNT_PROBE_V1'
SCOPE = dict(council='oldham', semantics='RECEIVED', start='2026-10-15', end='2026-10-21')
PAGE_SIZE = 10
PAGE_2_FIRST = PAGE_SIZE + 1      # the marker's `first` for page 2 at ten per page
# requests: form, search, sort, page 2, session check, control. The byte, time, dispatch and supervisor ceilings are the calibration's own (which are the existing reader's).
LIMITS = dict(cal.LIMITS, requests=6)
IDENTITY = re.compile(r'oldham-single-page-count-probe-[0-9]{8}-[a-z0-9]{1,16}')
PLAN = ['FORM', 'SEARCH', 'SORT_PAGE_1', 'PAGE_2_VIA_PORTAL_LINK_SHAPE', 'SESSION_CHECK_REFINE', 'INVALID_PAGE_CONTROL']
HEX64 = re.compile(r'[0-9a-f]{64}')


def config():
    return WindowConfig(SCOPE['council'], SCOPE['semantics'], date.fromisoformat(SCOPE['start']), date.fromisoformat(SCOPE['end']), 0)


# ------------------------------------------------------------------------------------------------------------------------------------- expected records
def identity_digest(reference, source_key):
    return hashlib.sha256(('%s\x1f%s' % (reference, source_key)).encode()).hexdigest()


def metadata_digest(proposal, address, received, validated):
    return hashlib.sha256(json.dumps([proposal, address, received, validated], separators=(',', ':')).encode()).hexdigest()


def record_digest(identity, metadata):
    return hashlib.sha256((identity + '\x1f' + metadata).encode()).hexdigest()


def expected_from_audit(audit, audit_sha256):
    """The original observation's records as HASHES only (identity, metadata and the two joined per record), for the registration. The audit must be the Oldham RECEIVED 15-21 October observation with unique records;
    no reference, key or text is kept."""
    recs = audit.get('records') if isinstance(audit, dict) else None
    if (not isinstance(recs, list) or not recs or audit.get('council') != SCOPE['council'] or audit.get('date_semantics') != SCOPE['semantics']
            or audit.get('requested_interval') != [SCOPE['start'], SCOPE['end']] or audit.get('failure') is not None
            or len({r['reference'] for r in recs}) != len(recs) or len({r['source_key'] for r in recs}) != len(recs)):
        raise ValueError('ORIGINAL_AUDIT_SCOPE')
    ids, metas, joint = [], [], []
    for r in recs:
        f = r['fields']
        i = identity_digest(r['reference'], r['source_key'])
        m = metadata_digest(f['proposal'].get('value'), f['address'].get('value'), f['received_date'].get('value'), f['validated_date'].get('value'))
        ids.append(i)
        metas.append(m)
        joint.append(record_digest(i, m))
    return dict(count=len(recs), source_audit_sha256=audit_sha256, identity_sha256=sorted(ids), metadata_sha256=sorted(metas), record_sha256=sorted(joint))


def check_expected(expected):
    if (not isinstance(expected, dict) or set(expected) != {'count', 'source_audit_sha256', 'identity_sha256', 'metadata_sha256', 'record_sha256'} or type(expected['count']) is not int or not 1 <= expected['count'] <= 10
            or not HEX64.fullmatch(str(expected['source_audit_sha256'])) or len(expected['identity_sha256']) != expected['count'] or len(expected['metadata_sha256']) != expected['count'] or len(expected['record_sha256']) != expected['count']
            or any(not HEX64.fullmatch(str(h)) for h in [*expected['identity_sha256'], *expected['metadata_sha256'], *expected['record_sha256']])
            or expected['identity_sha256'] != sorted(set(expected['identity_sha256'])) or expected['metadata_sha256'] != sorted(expected['metadata_sha256']) or expected['record_sha256'] != sorted(set(expected['record_sha256']))):
        raise ValueError('EXPECTED_RECORDS')
    return expected


def profile(expected):
    check_expected(expected)
    return dict(kind=KIND, identity=IDENTITY, scope=SCOPE, limits=LIMITS, extra=dict(plan=list(PLAN), page_size=PAGE_SIZE, control='MANDATORY', rule='classify_probe:v1', expected_records=expected,
                                                                                      collection_observation=False),
                module='verification.discovery.idox_single_page_probe', live=lambda directory: live(config(), directory, expected))


# ---------------------------------------------------------------------------------------------------------------------------------------------- capture
class ProbeBoundary(cal.CalibrationBoundary):
    """The calibration boundary with a six-request budget (its two special-URL admissions, redirect handling and observation semantics unchanged)."""

    def __init__(self, dispatch, cfg):
        super().__init__(dispatch, cfg)
        self.budget = Budget(requests=LIMITS['requests'], per_reference=LIMITS['requests'], total_bytes=LIMITS['total_bytes'], response_bytes=LIMITS['response_bytes'], seconds=LIMITS['reader_seconds'])


class _Stop(Exception):
    pass


def capture(dispatch, cfg, directory, expected):
    from pathlib import Path
    directory = Path(directory)
    base._private_directory_check(directory)
    check_expected(expected)
    b = ProbeBoundary(dispatch, cfg)
    out = dict(kind=KIND, council=cfg.council, requested_interval=[cfg.start.isoformat(), cfg.end.isoformat()], date_semantics=cfg.semantics, collection_observation=False, persistence=False,
               raw_html_published=False, steps=[], page1=None, original_comparison=None, failure=None, abort=None, session_check=None, cleanup='UNKNOWN')
    page1_keys = []
    stage = 'FORM_REQUEST'

    def keep(name, raw, prior=True):
        base._write_private(directory, name + '.html', raw)
        shape = b.last_response or {}
        step = dict(ordinal=len(out['steps']) + 1, name=name, http_status=shape.get('http_status'), media_type=shape.get('media_type'), redirect=shape.get('redirect'), bytes=len(raw),
                    sha256=hashlib.sha256(raw).hexdigest(), private_file=name + '.html')
        proj = cal.project(raw, [page1_keys] if (prior and page1_keys) else ())
        proj.pop('_keys', None)
        step['projection'] = proj
        out['steps'].append(step)
        return step

    try:
        form = b.retrieve('GET', cfg.form_url)
        keep('form', form)
        stage = 'FORM_PARSE'
        target, payload = cfg.payload(form)
        b.admitted_post, b.admitted_body, b.phase = target, urlencode(payload).encode(), 'SEARCH'
        payload.clear()
        stage = 'SEARCH_REQUEST'
        html = b.retrieve('POST', target, b.admitted_body)
        b.admitted_body = None
        keep('search', html)
        if explicit_zero(html, cfg.council):
            out['abort'] = 'ZERO_RESULTS'
            raise _Stop
        stage = 'SORT'
        target, payload = sort_payload(html, b.policy.base_url)
        b.admitted_post, b.admitted_body, b.phase = target, urlencode(payload).encode(), 'SORT'
        payload.clear()
        html = b.retrieve('POST', target, b.admitted_body)
        b.admitted_body = None
        stage = 'PAGE_1'
        require_reference_sort(html)
        page = parse_page(html, cfg.council, 1, cfg.start, cfg.end, cfg.semantics)
        step = keep('page-1', html, prior=False)
        keys = [r.source_key for r in page.rows]
        refs = [r.reference or '' for r in page.rows]
        page1_keys.extend(keys)
        ids = sorted(identity_digest(r.reference, r.source_key) for r in page.rows)
        metas = sorted(metadata_digest(r.fields['proposal'].value, r.fields['address'].value, r.fields['received_date'].value, r.fields['validated_date'].value) for r in page.rows)
        out['page1'] = dict(rows=len(keys), unique_keys=len(set(keys)) == len(keys), unique_references=len(set(refs)) == len(refs), sort_retained=True,
                            reference_order_observed_descending=refs == sorted(refs, reverse=True), first=page.first, last=page.last, total=page.total, terminal=page.terminal, page_size=page.page_size,
                            next_present=page.next_url is not None, next_controls=step['projection']['next_controls'], pager_elements=len(step['projection']['pager_markers']), response_sha256=step['sha256'])
        joint = sorted(record_digest(identity_digest(r.reference, r.source_key), metadata_digest(r.fields['proposal'].value, r.fields['address'].value, r.fields['received_date'].value, r.fields['validated_date'].value)) for r in page.rows)
        exp_ids, exp_meta = expected['identity_sha256'], expected['metadata_sha256']
        out['original_comparison'] = dict(
            expected_count=expected['count'], seen_count=len(ids), identity_matches=len(set(ids) & set(exp_ids)), identity_missing=len(set(exp_ids) - set(ids)), identity_extra=len(set(ids) - set(exp_ids)),
            metadata_matches=sum(min(metas.count(h), exp_meta.count(h)) for h in set(metas) & set(exp_meta)), record_matches=len(set(joint) & set(expected['record_sha256'])), seen_identity_set_sha256=hashlib.sha256(json.dumps(ids).encode()).hexdigest())
        if not (len(keys) >= 1 and out['page1']['unique_keys'] and out['page1']['unique_references'] and page.page_size == PAGE_SIZE and all(refs)):
            out['abort'] = 'PAGE_1_NOT_RECOGNISED'      # missing or duplicate identities, or another page size: nothing is asked beyond page 1
            raise _Stop
        if page.total is not None or page.terminal is not None or page.next_url is not None or step['projection']['pager_markers'] or step['projection']['next_controls']:
            out['abort'] = 'NOT_SINGLE_PAGE_SHAPE'      # a pager, total or next control on page 1 means this is not the single-page case: nothing is asked beyond it
            raise _Stop
        b.extra.update(BEYOND_END=source_url(cfg.council, 'pagedSearchResults.do?action=page&searchCriteria.page=2', page=2), CONTROL=b.policy.base_url + '/pagedSearchResults.do?action=page&searchCriteria.page=0')
        stage = 'PAGE_2'
        b.phase = 'BEYOND_END'
        _, _, data = b.observe(b.extra['BEYOND_END'])
        keep('page-2', data)
        stage = 'SESSION_CHECK'
        b.phase = 'REFINE'
        echoed = b.retrieve('GET', b.policy.base_url + '/refineSearch.do?action=refine')
        keep('session-check', echoed, prior=False)
        try:
            _, echo = cfg.payload(echoed, echo=True)
            echo.clear()
            out['session_check'] = dict(criteria_echo_matches=True)
        except Exception:
            out['session_check'] = dict(criteria_echo_matches=False)
        stage = 'CONTROL'
        b.phase = 'CONTROL'
        _, _, data = b.observe(b.extra['CONTROL'])
        keep('control-invalid-page', data)
    except _Stop:
        pass
    except (ListingError, BoundaryFailure, Failure) as exc:
        from .source_diagnostics import transport_facts
        out['failure'] = dict(stage=stage, error=type(exc).__name__, transport=transport_facts(b.last_response, exc))
    except Exception:
        out['failure'] = dict(stage=stage, error='UNCLASSIFIED_FAILURE', transport=None)
    finally:
        b.admitted_body = None
        b.close()
    out['resource'] = b.audit('PROBED' if out['failure'] is None and out['abort'] is None else 'STOPPED')
    out['cleanup'] = 'BOUNDARY_CLOSED'
    return out


def live(cfg, directory, expected):
    import time
    import requests
    with requests.Session() as s:
        s.trust_env = False
        s.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))
        previous = [None]

        def dispatch(method, url, **kwargs):
            if previous[0] is not None:
                time.sleep(max(0, 0.4 - (time.monotonic() - previous[0])))      # the reader's own spacing
            previous[0] = time.monotonic()
            kwargs.pop('deadline', None)
            kwargs['timeout'] = (LIMITS['connect_seconds'], LIMITS['read_seconds'])
            return s.request(method, url, **kwargs)
        result = capture(dispatch, cfg, directory, expected)
    result['cleanup'] = 'SESSION_BOUNDARY_CLOSED'
    return result


# ----------------------------------------------------------------------------------------------------------------------------------------- classify
def _results_page_marker(step):
    """(first, last, total) of the single explicit marker on a recognised, zero-row results page (HTTP 200 HTML, no redirect, results heading, one container), or None."""
    p = step.get('projection') or {}
    if step.get('http_status') != 200 or step.get('media_type') != 'text/html' or step.get('redirect') != 'NONE' or not p.get('html'):
        return None
    if not any(h['results_heading'] for h in p['headings']) or p['rows'] != 0 or p['password_inputs'] or p['results_containers'] != 1:
        return None
    markers = [m for m in p['pager_markers'] if m]
    return tuple(markers[0]) if markers and len({tuple(m) for m in markers}) == 1 else None


def _any_marker_on_results_page(step):
    """For the CONTROL: ANY pager marker on a recognised results page, whatever its rows. A control that carries a stamped total (clamped to a real page, say) shows that the portal marks every page request, so the
    page-2 marker would not be specific."""
    p = step.get('projection') or {}
    if step.get('http_status') != 200 or step.get('media_type') != 'text/html' or step.get('redirect') != 'NONE' or not p.get('html'):
        return False
    return any(h['results_heading'] for h in p['headings']) and not p['password_inputs'] and any(p['pager_markers'])


def _marker(step):
    """The page-2 signal: an explicit marker that is FOR page 2 (`first` = 11) and describes an EMPTY range (a start beyond its own total, or an end before its start)."""
    m = _results_page_marker(step)
    if m is None:
        return None
    first, last, total = m
    return m if first == PAGE_2_FIRST and (first > total or last < first) else None


def classify_probe(audit):
    """Pure and total over exports. ESTABLISHED (the page-2 signal) / UNRECONCILED (a well-formed marker whose total differs from the records seen) / INCONCLUSIVE. `historical_application` is reported
    separately: the original observation is only ever matched, never forced, and any drift withholds it."""
    try:
        return _classify_probe(audit)
    except (KeyError, TypeError, IndexError, AttributeError):
        return dict(verdict='INCONCLUSIVE', reasons=['UNPARSEABLE_EXPORT'], historical_application='WITHHELD_NO_ESTABLISHED_SIGNAL', signal=None)


def _classify_probe(audit):
    cmpr = audit.get('original_comparison')

    def hashes_unchanged():
        return bool(cmpr) and cmpr['identity_missing'] == 0 and cmpr['identity_extra'] == 0 and cmpr['metadata_matches'] == cmpr['expected_count'] == cmpr['seen_count'] == cmpr['record_matches']
    result = dict(verdict='INCONCLUSIVE', reasons=[], historical_application='WITHHELD_NO_ESTABLISHED_SIGNAL', signal=None, drift=cmpr)
    if audit.get('abort') or audit.get('failure'):
        result['reasons'] = [audit.get('abort') or 'FAILURE:' + str((audit['failure'] or {}).get('stage'))]
        return result
    p1 = audit['page1']
    steps = {s['name']: s for s in audit['steps']}
    page2, session, control, page1 = steps.get('page-2'), steps.get('session-check'), steps.get('control-invalid-page'), steps['page-1']
    r = result['reasons']
    if not (p1['rows'] >= 1 and p1['unique_keys'] and p1['unique_references'] and p1['sort_retained'] is True and p1['page_size'] == PAGE_SIZE):
        r.append('PAGE_1_NOT_RECOGNISED_SORTED_AND_UNIQUE')
    if p1['total'] is not None or p1['terminal'] is not None or p1['next_present'] or p1['first'] is not None or p1['pager_elements'] or p1['next_controls']:
        r.append('PAGE_1_NOT_THE_SINGLE_PAGE_SHAPE')      # never asserted as complete: the shape is only the precondition for asking
    if page2 is None:
        return dict(result, reasons=sorted(set(r + ['NO_PAGE_2_OBSERVATION'])))
    proj = page2['projection']
    if page2.get('http_status') != 200 or page2.get('media_type') != 'text/html' or page2.get('redirect') != 'NONE' or not proj.get('html'):
        r.append('TRANSPORT_OR_REDIRECT_OR_NOT_HTML')
    elif proj['rows'] > 0 or page2['sha256'] == p1['response_sha256'] or proj['fingerprint'] == page1['projection']['fingerprint'] or any(proj['overlap_with_prior_pages']):
        r.append('REPEATED_OR_CLAMPED_PAGE')
    marker = _marker(page2)
    if marker is None and not r:
        r.append('NO_EXPLICIT_EMPTY_RANGE_MARKER_FOR_PAGE_2')
    if not (audit.get('session_check') or {}).get('criteria_echo_matches') or session is None or session['projection'].get('password_inputs'):
        r.append('SESSION_NOT_ALIVE_OR_CRITERIA_CHANGED')
    if control is None:
        r.append('NO_INVALID_REQUEST_CONTROL')
    elif _any_marker_on_results_page(control) or (control['projection'].get('fingerprint') == proj.get('fingerprint') and control.get('http_status') == page2.get('http_status')):
        r.append('CONTROL_NOT_DISTINCT_FROM_THE_SIGNAL')
    res = audit.get('resource', {})
    if res.get('retries') != 0 or res.get('redirects') != 0 or res.get('budget_exhaustion') or res.get('requests_attempted') != LIMITS['requests'] or len(audit['steps']) != 6:
        r.append('ACCOUNTING_DISQUALIFIES')
    if r:
        return dict(result, reasons=sorted(set(r)))
    total = marker[2]
    seen = p1['rows']
    result['signal'] = dict(marker_total=total, seen=seen)
    if total == seen:
        applicable = 'APPLICABLE' if hashes_unchanged() else 'WITHHELD_DRIFT'      # only an ESTABLISHED signal can ever apply, and only to an unchanged record set
        return dict(result, verdict='ESTABLISHED', reasons=[], historical_application=applicable)
    return dict(result, verdict='UNRECONCILED', reasons=['TOTAL_GREATER_THAN_RECORDS_SEEN' if total > seen else 'TOTAL_LESS_THAN_RECORDS_SEEN'])      # cause (changed result set, reader defect, portal) undetermined


# --------------------------------------------------------------------------------------------------------------------------------------------------- CLI
def cli(argv=None):
    """`render` takes the consumed observation's audit (`--original-audit`) and hashes its records into the registration; `run` and `worker` take the expected-record hashes from the registration the owner
    approved (its exact bytes are hash-bound). Everything else is the shared, reviewed `main`."""
    import sys
    from pathlib import Path
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = argv[0] if argv else ''
    if mode == 'render':
        i = argv.index('--original-audit')
        path = Path(argv[i + 1])
        raw = path.read_bytes()
        expected = expected_from_audit(json.loads(raw), hashlib.sha256(raw).hexdigest())
        return base.main(argv[:i] + argv[i + 2:], profile=profile(expected))
    if mode == 'run':
        registration = json.loads(Path(argv[argv.index('--registration') + 1]).read_bytes())
    elif mode == 'worker':
        registration = json.loads((Path(argv[argv.index('--directory') + 1]) / 'registration.json').read_bytes())
    else:
        return base.main(argv, profile=profile(dict(count=1, source_audit_sha256='0' * 64, identity_sha256=['0' * 64], metadata_sha256=['0' * 64])))
    return base.main(argv, profile=profile(registration.get('expected_records')))


if __name__ == '__main__':
    raise SystemExit(cli())
