"""Oldham paging calibration (dormant; inactive until the owner approves its exact registration hash).

Question: can the existing Idox paging mechanism establish TERMINAL pagination for a single-page result that shows no total? The 2026-10-28 diagnostic found no count or navigation signal in the inspected
places of the Oldham single-page response, so completeness stays UNKNOWN. This tool calibrates the portal's own paging behaviour on a result that DOES show an explicit total, so that a later,
separately approved application to the single-page window would be read against a predeclared rule rather than invented after the fact.

One bounded session (reusing `WindowBoundary`, the council's own form payload and the sort form exactly as the reader does): form, date search, sort by Reference descending, then every next-page link the
portal itself offers to the explicit last page, then ONE request for the page after the last (built in the same `action=page&searchCriteria.page=N` shape as the portal's own links), a refine-view
request that proves the session and criteria are still alive, and ONE invalid-page control. Raw bodies stay private; the export holds hashes, sizes, statuses, counts and structural fingerprints only.
`classify` is a pure function of that export with predeclared outcomes (ESTABLISHED / INCONCLUSIVE / CONTRADICTED). Nothing here changes the parser, the proof or any completeness classification.
"""
import hashlib
import json
import re
from datetime import date
from urllib.parse import urlencode

from app.scrapers.discovery_idox import ListingError, explicit_zero, parse_page, source_url
from verification.bolton_recon.recon import Failure
from verification.stage26b_l1.request_boundary import BoundaryFailure, Budget

from . import idox_response_diagnostic as base
from .idox_sort import require_reference_sort, sort_payload
from .idox_window import WindowBoundary, WindowConfig

KIND = 'OLDHAM_PAGING_CALIBRATION_V1'
SCOPE = dict(council='oldham', semantics='RECEIVED', start='2026-10-08', end='2026-10-21')      # 14 days (the reader's own window rule allows 28): chosen so the result is expected to span two pages
PAGE_SIZE = 10
MIN_TOTAL, MAX_TOTAL, MAX_PAGES = 11, 30, 3      # a result outside 2..3 pages is not calibratable: the run stops BEFORE any beyond-the-end request
# requests: form, search, sort, (P-1) next pages, beyond-the-end, session check, invalid-page control = P + 5, and P <= 3.
# Combined bytes, per-response bytes and the reader time are the existing reader's own ceilings (WindowBoundary: 3,000,000 / 500,000 / 45 s), not a function of any earlier response.
LIMITS = dict(requests=8, response_bytes=500_000, total_bytes=3_000_000, reader_seconds=45, connect_seconds=3, read_seconds=8, supervisor_seconds=50, max_registration_hours=2)
IDENTITY = re.compile(r'oldham-paging-calibration-[0-9]{8}-[a-z0-9]{1,16}')
PLAN = ['FORM', 'SEARCH', 'SORT', 'NEXT_PAGES_VIA_PORTAL_LINKS', 'BEYOND_END_PAGE', 'SESSION_CHECK_REFINE', 'INVALID_PAGE_CONTROL']
EXHAUSTION_WORDING = re.compile(r'^\W*(?:there\s+are\s+)?no\s+(?:more|further)\s+results\b|^\W*end\s+of\s+results\b', re.I)
RESULTS_HEADING = re.compile(r'Planning\s*[–-]\s*Results for Application Search')
TEXT = 120


def config():
    return WindowConfig(SCOPE['council'], SCOPE['semantics'], date.fromisoformat(SCOPE['start']), date.fromisoformat(SCOPE['end']), 0)


def profile():
    return dict(kind=KIND, identity=IDENTITY, scope=SCOPE, limits=LIMITS, extra=dict(plan=list(PLAN), page_size=PAGE_SIZE, calibratable_total=[MIN_TOTAL, MAX_TOTAL], max_pages=MAX_PAGES,
                                                                                      rule='classify:v1', collection_observation=False),
                module='verification.discovery.idox_paging_calibration', live=lambda directory: live(config(), directory))


# ------------------------------------------------------------------------------------------------------------------------------------------ capture
class CalibrationBoundary(WindowBoundary):
    """The window boundary with an eight-request budget and exactly two further admitted GETs (the beyond-the-end page and the invalid-page control), each only in its own phase and only once."""

    def __init__(self, dispatch, cfg):
        super().__init__(dispatch, cfg)
        self.budget = Budget(requests=LIMITS['requests'], per_reference=LIMITS['requests'], total_bytes=LIMITS['total_bytes'], response_bytes=LIMITS['response_bytes'], seconds=LIMITS['reader_seconds'])
        self.extra = {}

    def validate(self, method, url, body=None):
        if self.phase in ('BEYOND_END', 'CONTROL') and method == 'GET' and body is None and self.extra.get(self.phase) == url:
            self.budget.check()
            if self.closed:
                self.budget.reject('PARTIAL_RETRIEVAL', 'closed')
            return
        return super().validate(method, url, body)

    def observe(self, url):
        """One GET whose ANY answer (including a redirect or an HTML error page) is an observation: status, content type and body, never an exception for the shape alone."""
        self.last_response = None
        status, headers, data = self.request('GET', url)
        self.extra.pop(self.phase, None)      # single use
        return status, headers.get('Content-Type', ''), data


def _keys_of(soup):
    keys = []
    for a in soup.select('#searchresults > li.searchresult a.summaryLink'):
        m = re.search(r'keyVal=([A-Za-z0-9_]+)', a.get('href') or '')
        keys.append(m.group(1) if m else '')
    return keys


def project(raw, prior_pages=()):
    """The structural projection of one response for classification: no record text, no key values, no token."""
    from bs4 import BeautifulSoup
    out = dict(bytes=len(raw), html=False)
    try:
        html = raw.decode('utf-8', errors='strict')
    except UnicodeError:
        return out
    soup = BeautifulSoup(html, 'html.parser')
    out['html'] = True
    h1 = [re.sub(r'\s+', ' ', h.get_text()).strip() for h in soup.select('h1')]
    keys = _keys_of(soup)
    prior = [set(p) for p in prior_pages]
    markers = []
    for p in soup.select('p.pager'):
        m = re.match(r'Showing\s+(\d+)\s*-\s*(\d+)\s+of\s+(\d+)', re.sub(r'\s+', ' ', p.get_text()).strip())
        markers.append(list(map(int, m.groups())) if m else None)
    messages = [re.sub(r'\s+', ' ', li.get_text()).strip()[:TEXT] for box in soup.select('div.messagebox') for li in box.select('li')]
    out.update(
        headings=[dict(results_heading=bool(RESULTS_HEADING.fullmatch(t)), text=t[:80]) for t in h1][:5],
        title=[re.sub(r'\s+', ' ', t.get_text()).strip()[:80] for t in soup.select('title')][:2],
        results_containers=len(soup.select('#searchresults')), rows=len(keys), pager_markers=markers[:4], next_controls=len(soup.select('p.pager a.next')),
        messages=messages[:5], forms=sorted({f.get('id') or '' for f in soup.select('form')})[:5], password_inputs=len(soup.select('input[type=password]')),
        overlap_with_prior_pages=[len(set(keys) & p) for p in prior])
    out['fingerprint'] = hashlib.sha256(json.dumps([out['headings'], out['title'], out['results_containers'], out['rows'], out['pager_markers'], out['messages'], out['forms'], out['password_inputs']],
                                                  sort_keys=True).encode()).hexdigest()
    out['_keys'] = keys      # in memory only; removed before export
    return out


def capture(dispatch, cfg, directory):
    from pathlib import Path
    directory = Path(directory)
    base._private_directory_check(directory)
    b = CalibrationBoundary(dispatch, cfg)
    out = dict(kind=KIND, council=cfg.council, requested_interval=[cfg.start.isoformat(), cfg.end.isoformat()], date_semantics=cfg.semantics, collection_observation=False, persistence=False,
               raw_html_published=False, steps=[], pages=[], failure=None, abort=None, session_check=None, cleanup='UNKNOWN')
    page_keys = []
    stage = 'FORM_REQUEST'

    def keep(name, raw, keys_of_prior=True):
        base._write_private(directory, name + '.html', raw)
        shape = b.last_response or {}
        step = dict(ordinal=len(out['steps']) + 1, name=name, http_status=shape.get('http_status'), media_type=shape.get('media_type'), redirect=shape.get('redirect'), bytes=len(raw),
                    sha256=hashlib.sha256(raw).hexdigest(), private_file=name + '.html')
        proj = project(raw, page_keys if keys_of_prior else ())
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
        ordinal, last_reference, last_page = 1, None, None
        while True:
            stage = 'PAGE_%d' % ordinal
            require_reference_sort(html)
            page = parse_page(html, cfg.council, ordinal, cfg.start, cfg.end, cfg.semantics)
            keys = [r.source_key for r in page.rows]
            references = [r.reference or '' for r in page.rows]
            step = keep('page-%d' % ordinal, html)
            overlap = sum(len(set(keys) & set(k)) for k in page_keys)
            out['pages'].append(dict(ordinal=ordinal, via_portal_next_link=ordinal >= 2, first=page.first, last=page.last, total=page.total, rows=len(keys), terminal=page.terminal,
                                     next_present=page.next_url is not None, overlap_with_earlier_pages=overlap, unique_keys=len(set(keys)) == len(keys), sort_retained=True,
                                     reference_order_observed_descending=references == sorted(references, reverse=True) and (last_reference is None or (bool(references) and last_reference >= references[0])),      # informational: the portal's own collation may differ from Python's, so it never gates
                                     response_sha256=step['sha256']))
            page_keys.append(keys)
            last_reference = references[-1] if references else last_reference
            last_page = page
            if page.next_url is None:
                break
            if ordinal == MAX_PAGES:
                out['abort'] = 'TOO_MANY_PAGES'
                raise _Stop
            b.phase, b.next_url = 'PAGE', page.next_url
            html = b.retrieve('GET', page.next_url)
            ordinal += 1
        if not (ordinal >= 2 and last_page.total is not None and MIN_TOTAL <= last_page.total <= MAX_TOTAL and last_page.terminal == 'EXPLICIT_LAST_EQUALS_TOTAL'):
            out['abort'] = 'NOT_CALIBRATABLE'      # no explicit multi-page total in range: nothing is asked beyond the end
            raise _Stop
        pages = ordinal
        beyond = source_url(cfg.council, 'pagedSearchResults.do?action=page&searchCriteria.page=%d' % (pages + 1), page=pages + 1)
        control = b.policy.base_url + '/pagedSearchResults.do?action=page&searchCriteria.page=0'
        b.extra.update(BEYOND_END=beyond, CONTROL=control)
        stage = 'BEYOND_END'
        b.phase = 'BEYOND_END'
        status, ctype, data = b.observe(beyond)
        keep('beyond-end', data)
        stage = 'SESSION_CHECK'
        b.phase = 'REFINE'
        echoed = b.retrieve('GET', b.policy.base_url + '/refineSearch.do?action=refine')
        keep('session-check', echoed, keys_of_prior=False)
        try:
            _, echo = cfg.payload(echoed, echo=True)
            echo.clear()
            out['session_check'] = dict(criteria_echo_matches=True)
        except Exception:
            out['session_check'] = dict(criteria_echo_matches=False)
        stage = 'CONTROL'
        b.phase = 'CONTROL'
        status, ctype, data = b.observe(control)
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
    out['resource'] = b.audit('CALIBRATED' if out['failure'] is None and out['abort'] is None else 'STOPPED')
    out['cleanup'] = 'BOUNDARY_CLOSED'
    return out


class _Stop(Exception):
    pass


def live(cfg, directory):
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
        result = capture(dispatch, cfg, directory)
    result['cleanup'] = 'SESSION_BOUNDARY_CLOSED'
    return result


# ----------------------------------------------------------------------------------------------------------------------------------------- classify
def _shape(step):
    """The predeclared exhaustion shapes, read from a projection. None means 'not a specific exhaustion shape'."""
    p = step['projection']
    if step.get('http_status') != 200 or step.get('media_type') != 'text/html' or step.get('redirect') != 'NONE' or not p.get('html'):
        return None
    if not any(h['results_heading'] for h in p['headings']) or p['rows'] != 0 or p['password_inputs']:
        return None
    markers = [m for m in p['pager_markers'] if m]
    if markers:
        return ('EXPLICIT_TOTAL_WITH_NO_ROWS', markers[0][2])
    if any(EXHAUSTION_WORDING.search(m) for m in p['messages']):
        return ('NO_MORE_RESULTS_MESSAGE', None)
    return None


def _advance(pages):
    reasons = []
    if len(pages) < 2:
        return ['NOT_MULTI_PAGE']
    total = pages[0]['total']
    union = 0
    for i, p in enumerate(pages, 1):
        union += p['rows']
        if p['ordinal'] != i:
            reasons.append('ORDINAL')
        if p['total'] != total or total is None:
            reasons.append('TOTAL_CHANGED_OR_ABSENT')
        elif p['first'] != (i - 1) * PAGE_SIZE + 1 or p['rows'] != p['last'] - p['first'] + 1 or p['last'] != min(i * PAGE_SIZE, total):
            reasons.append('IGNORED_OR_MISPLACED_PAGE')
        if p['overlap_with_earlier_pages'] or not p['unique_keys']:
            reasons.append('REPEATED_ROWS')
        if p.get('sort_retained') is not True:      # every page's form must show Reference / Descending selected (`require_reference_sort` raises otherwise, which is a failure, not a pass)
            reasons.append('SORT_NOT_RETAINED_ACROSS_PAGES')
        if i < len(pages) and (not p['next_present'] or p['terminal']):
            reasons.append('PREMATURE_TERMINAL')
    last = pages[-1]
    if last['next_present'] or last['terminal'] != 'EXPLICIT_LAST_EQUALS_TOTAL' or union != total:
        reasons.append('LAST_PAGE_NOT_EXPLICIT_OR_UNION_MISMATCH')
    return sorted(set(reasons))


def classify(audit):
    """ESTABLISHED only if every predeclared condition holds; CONTRADICTED if the portal returns rows beyond its own explicit total; otherwise INCONCLUSIVE with the reasons. Pure function of the export."""
    if audit.get('abort') or audit.get('failure'):
        return dict(verdict='INCONCLUSIVE', advance=None, terminal=None, reasons=[audit.get('abort') or 'FAILURE:' + str((audit['failure'] or {}).get('stage'))])
    adv = _advance(audit['pages'])
    steps = {s['name']: s for s in audit['steps']}
    end, control, session = steps.get('beyond-end'), steps.get('control-invalid-page'), steps.get('session-check')
    result = dict(advance=dict(established=not adv, reasons=adv), terminal=dict(shape=None, reasons=[]), reasons=[])
    if adv:
        return dict(result, verdict='INCONCLUSIVE', reasons=['ADVANCE_NOT_ESTABLISHED'])
    t = result['terminal']['reasons']
    if end is None:
        return dict(result, verdict='INCONCLUSIVE', reasons=['NO_BEYOND_END_OBSERVATION'])
    pages_hashes = {p['response_sha256'] for p in audit['pages']}
    if end.get('http_status') != 200 or end.get('media_type') != 'text/html' or end.get('redirect') != 'NONE':
        t.append('TRANSPORT_OR_REDIRECT')
    elif end['projection']['rows'] > 0 and not any(end['projection']['overlap_with_prior_pages']):
        return dict(result, verdict='CONTRADICTED', reasons=['ROWS_BEYOND_EXPLICIT_TOTAL'])
    elif end['projection']['rows'] > 0 or end['sha256'] in pages_hashes or end['projection']['fingerprint'] in {steps['page-%d' % p['ordinal']]['projection']['fingerprint'] for p in audit['pages']}:
        t.append('REPEATED_PAGE')
    shape = _shape(end)
    result['terminal']['shape'] = shape[0] if shape else None
    if shape is None and not t:
        t.append('AMBIGUOUS_OR_GENERIC_RESPONSE')
    if shape and shape[1] is not None and shape[1] != audit['pages'][0]['total']:
        t.append('TOTAL_CONTRADICTED')
    if not (audit.get('session_check') or {}).get('criteria_echo_matches') or session is None or session['projection'].get('password_inputs'):
        t.append('SESSION_NOT_ALIVE_OR_CRITERIA_CHANGED')
    if control is None:
        t.append('NO_INVALID_REQUEST_CONTROL')
    elif _shape(control) is not None or control['projection'].get('fingerprint') == end['projection'].get('fingerprint') and control.get('http_status') == end.get('http_status'):
        t.append('SIGNAL_NOT_SPECIFIC_TO_EXHAUSTION')
    return dict(result, verdict='ESTABLISHED' if not t else 'INCONCLUSIVE', reasons=sorted(set(t)))


if __name__ == '__main__':
    raise SystemExit(base.main(profile=profile()))
