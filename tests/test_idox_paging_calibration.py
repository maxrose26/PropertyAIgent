"""Offline proof for the Oldham paging calibration: its bounds, its stop conditions and its predeclared classifier. A scripted fake council (synthetic, sanitised markup; no network, no council)
answers every scenario. Passing these tests proves the TOOL's handling and decision rules; it says nothing about what the real portal returns, which is what the owner-approved live run is for.
"""
import json
import os
import stat
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_discovery_idox_listing import page as _bolton_page
from tests.test_discovery_idox_window import SORT, Response
from verification.bolton_recon.fixtures import FORM
from verification.discovery import idox_paging_calibration as c
from verification.discovery import idox_response_diagnostic as d

HEADING = '<h1>Planning – Results for Application Search</h1>'
BASE = 'https://planningpa.oldham.gov.uk/online-applications'


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(d, 'STATE_ROOT', tmp_path / 'default-state')
    for key in list(os.environ):
        if any(s in key.upper() for s in d.FORBIDDEN_ENV):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def private(tmp_path):
    p = tmp_path / 'private'
    p.mkdir(mode=0o700)
    os.chmod(p, 0o700)
    return p


class Resp(Response):
    def __init__(self, body, status=200, headers=None):
        super().__init__(body)
        self.status_code = status
        self.headers = headers or {'Content-Type': 'text/html'}


def listing(first, last, total, refs, *, next_page=None, prefix='A'):
    body = _bolton_page(first=first, last=last, total=total, refs=tuple(refs), next_page=next_page).replace(b'Mon 28 Sep 2026', b'Thu 15 Oct 2026').replace(b'keyVal=K', ('keyVal=' + prefix + 'K').encode())
    return body.replace(b'</html>', SORT + b'</html>')


def refs(top, n):
    return ['R%03d/26' % (top - i) for i in range(n)]


def echo():
    return FORM.replace(b'name="date(applicationReceivedStart)" value=""', b'name="date(applicationReceivedStart)" value="08/10/2026"').replace(
        b'name="date(applicationReceivedEnd)" value=""', b'name="date(applicationReceivedEnd)" value="21/10/2026"')


def results_shell(inner, heading=HEADING):
    return ('<html>' + heading + inner + '</html>').encode()


SHAPES = {
    'message': results_shell('<div class="messagebox"><ul><li>There are no more results.</li></ul></div><ul id="searchresults"></ul>'),
    'empty': results_shell('<ul id="searchresults"></ul>'),
    'error': results_shell('<p>Sorry</p>', heading='<h1>Error</h1>'),
    'login': results_shell('<form id="login"><input type="password" name="p"></form>', heading='<h1>Sign in</h1>'),
    'wrong_total': results_shell('<p class="pager">Showing 0 - 0 of 99</p><ul id="searchresults"></ul>'),
}


class Council:
    """A scripted portal. `pages` is the number of result pages; `total` the explicit total; `beyond`/`control` choose the answers to the two special requests."""

    def __init__(self, pages=2, total=20, beyond='explicit_total', control='error', session_alive=True, ignore_page_parameter=False, bad_boundary=False):
        self.calls, self.pages, self.total, self.beyond, self.control_kind, self.alive, self.ignore, self.bad_boundary = [], pages, total, beyond, control, session_alive, ignore_page_parameter, bad_boundary

    def page_body(self, n):
        first = (n - 1) * 10 + 1
        last = min(n * 10, self.total)
        top = 500 - (n - 1) * 10
        body = listing(first, last, self.total, refs(top, last - first + 1), next_page=n + 1 if n < self.pages else None, prefix='P%d' % n)
        if self.bad_boundary and n == 2:
            body = body.replace(b'<option value="Reference" selected>', b'<option value="Reference">')      # the sort is no longer retained on page 2
        return body

    def __call__(self, method, url, **kw):
        body = kw.get('data')
        self.calls.append((method, url))
        if method == 'GET' and url.endswith('/search.do?action=advanced&searchType=Application'):
            return Resp(FORM)
        if method == 'POST' and 'advancedSearchResults.do' in url:
            return Resp(self.page_body(1))
        if method == 'POST' and url.endswith('/pagedSearchResults.do'):
            return Resp(self.page_body(1))
        if method == 'GET' and 'refineSearch.do' in url:
            return Resp(echo() if self.alive else FORM)
        if method == 'GET' and 'searchCriteria.page=' in url:
            n = int(url.rsplit('=', 1)[1])
            if n == 0:
                return self.special(self.control_kind)
            if n > self.pages:
                return self.special(self.beyond)
            return Resp(self.page_body(1 if self.ignore else n))
        raise AssertionError('unscripted request ' + method + ' ' + url)

    def special(self, kind):
        if kind == 'explicit_total':
            return Resp(results_shell('<p class="pager">Showing 0 - 0 of %d</p><ul id="searchresults"></ul>' % self.total))
        if kind == 'repeat_first':
            return Resp(self.page_body(1))
        if kind == 'repeat_last':
            return Resp(self.page_body(self.pages))
        if kind == 'rows_beyond':
            return Resp(listing(self.total + 1, self.total + 3, self.total, refs(5, 3), prefix='Z'))
        if kind == 'redirect':
            return Resp(b'', status=302, headers={'Content-Type': 'text/html', 'Location': BASE + '/search.do'})
        if kind in ('http400', 'http404', 'http500'):
            return Resp(results_shell('<p>Sorry</p>', heading='<h1>Error</h1>'), status=int(kind[4:]))
        if kind == 'clamped_hidden':      # the last page's marker again, its rows not in a recognised element
            return Resp(results_shell('<p class="pager">Showing %d-%d of %d</p><ul id="searchresults"></ul>' % ((self.pages - 1) * 10 + 1, self.total, self.total)))
        if kind == 'rows_beyond_unrecognised':
            return Resp(listing(self.total + 1, self.total + 3, 999, refs(5, 3), prefix='Z'))
        if kind == 'download':
            return Resp(b'%PDF', headers={'Content-Type': 'application/pdf'})
        return Resp(SHAPES[kind])


def run(council, private):
    return c.capture(council, c.config(), private)


def names(out):
    return [s['name'] for s in out['steps']]


# ---------------------------------------------------------------------------------------------------------------------------------------- bounds
def test_the_two_page_sequence_is_exactly_seven_requests_in_the_declared_order(private):
    council = Council()
    out = run(council, private)
    assert out['failure'] is None and out['abort'] is None and names(out) == ['form', 'search', 'page-1', 'page-2', 'beyond-end', 'session-check', 'control-invalid-page']
    assert [m for m, _ in council.calls] == ['GET', 'POST', 'POST', 'GET', 'GET', 'GET', 'GET'] and out['resource']['requests_attempted'] == 7
    assert council.calls[3][1] == BASE + '/pagedSearchResults.do?action=page&searchCriteria.page=2'      # the portal's own next link
    assert council.calls[4][1] == BASE + '/pagedSearchResults.do?action=page&searchCriteria.page=3'      # the single beyond-the-end request, in the portal's own link shape
    assert council.calls[6][1] == BASE + '/pagedSearchResults.do?action=page&searchCriteria.page=0'      # the single invalid-page control
    assert out['resource']['retries'] == 0 and out['resource']['redirects'] == 0 and out['resource']['budget_exhaustion'] is False


def test_a_three_page_result_uses_exactly_the_eight_request_ceiling(private):
    council = Council(pages=3, total=25)
    out = run(council, private)
    assert out['resource']['requests_attempted'] == c.LIMITS['requests'] == 8 and out['failure'] is None
    assert [p['ordinal'] for p in out['pages']] == [1, 2, 3] and c.classify(out)['verdict'] == 'ESTABLISHED'


def test_the_limits_are_the_existing_readers_ceilings_and_the_request_cap_follows_the_plan():
    reader = d.WindowBoundary(lambda *a, **k: None, c.config()).budget
    assert c.LIMITS['response_bytes'] == reader.response_bytes and c.LIMITS['reader_seconds'] == reader.seconds and c.LIMITS['total_bytes'] == 3_000_000
    assert c.LIMITS['requests'] == 3 + (c.MAX_PAGES - 1) + 3      # form, search, sort, next pages, beyond-end, session check, control
    b = c.CalibrationBoundary(lambda *a, **k: None, c.config())
    assert (b.budget.requests, b.budget.response_bytes, b.budget.total_bytes, b.budget.seconds) == (8, 500_000, 3_000_000, 45)


def test_only_the_two_special_urls_are_admitted_and_only_once_each():
    from verification.stage26b_l1.request_boundary import BoundaryFailure
    special = BASE + '/pagedSearchResults.do?action=page&searchCriteria.page=3'

    def boundary():
        b = c.CalibrationBoundary(lambda *a, **k: Resp(listing(1, 2, 2, ['R002/26', 'R001/26'])), c.config())
        b.phase = 'BEYOND_END'
        b.extra['BEYOND_END'] = special
        return b
    for other in (BASE + '/pagedSearchResults.do?action=page&searchCriteria.page=4', BASE + '/applicationDetails.do?keyVal=X', special + '&x=1', special.replace('https', 'http')):
        b = boundary()
        with pytest.raises(BoundaryFailure):
            b.observe(other)
        assert b.requests == 0      # refused before any dispatch
    b = boundary()
    status, _, _ = b.observe(special)
    assert status == 200 and 'BEYOND_END' not in b.extra and b.requests == 1
    with pytest.raises(BoundaryFailure):
        b.observe(special)      # single use
    assert b.requests == 1


def test_observe_returns_error_and_redirect_answers_with_their_bodies_and_keeps_the_budget_alive():
    for status, headers in ((400, None), (404, None), (500, None), (302, {'Content-Type': 'text/html', 'Location': BASE + '/search.do'})):
        b = c.CalibrationBoundary(lambda *a, **k: Resp(b'<html>body</html>', status=status, headers=headers), c.config())
        b.phase = 'BEYOND_END'
        b.extra['BEYOND_END'] = BASE + '/pagedSearchResults.do?action=page&searchCriteria.page=3'
        got, ctype, data = b.observe(BASE + '/pagedSearchResults.do?action=page&searchCriteria.page=3')
        assert got == status and data == b'<html>body</html>' and b.budget.failure is None and b.requests == 1 and b.received_bytes == len(data) and b.redirects == 0


def test_observe_still_refuses_a_download_and_an_oversize_body():
    from verification.stage26b_l1.request_boundary import BoundaryFailure
    for resp in (Resp(b'%PDF', headers={'Content-Type': 'application/pdf'}), Resp(b'x' * 500_001)):
        b = c.CalibrationBoundary(lambda *a, **k: resp, c.config())
        b.phase = 'CONTROL'
        b.extra['CONTROL'] = BASE + '/pagedSearchResults.do?action=page&searchCriteria.page=0'
        with pytest.raises(BoundaryFailure):
            b.observe(BASE + '/pagedSearchResults.do?action=page&searchCriteria.page=0')


@pytest.mark.parametrize('council,reason,requests', [
    (Council(pages=1, total=7), 'NOT_CALIBRATABLE', 3),
    (Council(pages=4, total=40), 'TOO_MANY_PAGES', 5),
])
def test_an_uncalibratable_result_stops_before_any_beyond_the_end_request(private, council, reason, requests):
    out = run(council, private)
    assert out['abort'] == reason and out['resource']['requests_attempted'] == requests and 'beyond-end' not in names(out)
    assert not any('page=0' in u or u.endswith('page=%d' % (council.pages + 1)) for _, u in council.calls)
    assert c.classify(out)['verdict'] == 'INCONCLUSIVE'


def test_raw_bodies_are_private_and_the_export_holds_no_record_text_or_keys(private):
    out = run(Council(), private)
    exported = json.dumps(out)
    import re
    assert not re.search(r'R\d{3}/26', exported) and not re.search(r'P\dK\d', exported) and 'keyVal=' not in exported and '<html' not in exported.lower() and '"_keys"' not in exported
    for step in out['steps']:
        proj = step['projection']
        assert all(set(h) == {'results_heading', 'sha256'} for h in proj.get('headings', [])) and all(set(m) == {'exhaustion_wording', 'sha256'} for m in proj.get('messages', []))
        f = private / step['private_file']
        assert stat.S_IMODE(f.stat().st_mode) == 0o600 and f.read_bytes() and step['sha256']


# ------------------------------------------------------------------------------------------------------------------------------------ classifier
def verdict(council, private):
    return c.classify(run(council, private))


@pytest.mark.parametrize('kind,shape', [('explicit_total', 'EXPLICIT_TOTAL_WITH_NO_ROWS'), ('message', 'NO_MORE_RESULTS_MESSAGE')])
def test_a_valid_advance_and_a_specific_exhaustion_response_establish_the_signal(tmp_path, kind, shape):
    private = tmp_path / 'p'
    private.mkdir(mode=0o700)
    result = verdict(Council(beyond=kind), private)
    assert result['verdict'] == 'ESTABLISHED' and result['terminal']['shape'] == shape and result['advance']['established'] is True, result


@pytest.mark.parametrize('beyond,reason', [
    ('repeat_first', 'REPEATED_PAGE'), ('repeat_last', 'REPEATED_PAGE'), ('empty', 'AMBIGUOUS_OR_GENERIC_RESPONSE'), ('error', 'AMBIGUOUS_OR_GENERIC_RESPONSE'),
    ('login', 'AMBIGUOUS_OR_GENERIC_RESPONSE'), ('wrong_total', 'TOTAL_CONTRADICTED'), ('redirect', 'TRANSPORT_OR_REDIRECT_OR_NOT_HTML'), ('http400', 'TRANSPORT_OR_REDIRECT_OR_NOT_HTML'),
    ('http404', 'TRANSPORT_OR_REDIRECT_OR_NOT_HTML'), ('http500', 'TRANSPORT_OR_REDIRECT_OR_NOT_HTML'), ('clamped_hidden', 'AMBIGUOUS_OR_GENERIC_RESPONSE'), ('download', None)])
def test_generic_repeated_ambiguous_or_failed_responses_stay_inconclusive(tmp_path, beyond, reason):
    private = tmp_path / 'p'
    private.mkdir(mode=0o700)
    result = verdict(Council(beyond=beyond), private)
    assert result['verdict'] == 'INCONCLUSIVE', result
    if reason:
        assert reason in result['reasons']


def test_rows_beyond_a_recognised_results_page_with_the_same_total_contradict_it_but_unrecognised_rows_do_not(tmp_path):
    a, b = tmp_path / 'a', tmp_path / 'b'
    a.mkdir(mode=0o700)
    b.mkdir(mode=0o700)
    assert verdict(Council(beyond='rows_beyond'), a)['verdict'] == 'CONTRADICTED'
    unvalidated = verdict(Council(beyond='rows_beyond_unrecognised'), b)
    assert unvalidated['verdict'] == 'INCONCLUSIVE' and unvalidated['reasons'] == ['UNVALIDATED_ROWS_BEYOND_END']


def test_an_ignored_page_parameter_is_inconclusive_not_a_terminal_signal(private):
    council = Council(ignore_page_parameter=True)
    result = verdict(council, private)
    assert not any('page=3' in u or 'page=0' in u for _, u in council.calls)      # no beyond-the-end or control request once the advance failed
    assert result['verdict'] == 'INCONCLUSIVE' and result['reasons'] == ['FAILURE:PAGE_2']      # the parser's own marker check refuses a page 2 that carries page 1's rows


def test_a_sort_that_is_not_retained_on_a_later_page_stops_the_run_as_a_failure_not_a_pass(private):
    out = run(Council(bad_boundary=True), private)
    assert out['failure'] is not None and out['failure']['stage'] == 'PAGE_2' and 'beyond-end' not in names(out)
    assert c.classify(out)['verdict'] == 'INCONCLUSIVE'


def test_a_page_missing_the_sort_flag_in_the_export_fails_the_advance_check():
    out = run_audit()
    out['pages'][1]['sort_retained'] = False
    assert 'SORT_NOT_RETAINED_ACROSS_PAGES' in c.classify(out)['advance']['reasons']


def test_a_dead_session_or_changed_criteria_after_the_beyond_response_is_inconclusive(private):
    result = verdict(Council(session_alive=False), private)
    assert result['verdict'] == 'INCONCLUSIVE' and 'SESSION_NOT_ALIVE_OR_CRITERIA_CHANGED' in result['reasons']


@pytest.mark.parametrize('control', ['message', 'explicit_total'])
def test_a_signal_that_the_invalid_request_control_also_produces_is_not_specific_to_exhaustion(tmp_path, control):
    private = tmp_path / 'p'
    private.mkdir(mode=0o700)
    beyond = 'message' if control == 'message' else 'explicit_total'
    result = verdict(Council(beyond=beyond, control=control), private)
    assert result['verdict'] == 'INCONCLUSIVE' and 'SIGNAL_NOT_SPECIFIC_TO_EXHAUSTION' in result['reasons']


def test_a_control_that_looks_exactly_like_the_beyond_response_even_if_unshaped_is_not_specific(tmp_path):
    private = tmp_path / 'p'
    private.mkdir(mode=0o700)
    out = run(Council(beyond='message', control='message'), private)
    assert c.classify(out)['verdict'] == 'INCONCLUSIVE'
    steps = {s['name']: s for s in out['steps']}
    assert steps['beyond-end']['projection']['fingerprint'] == steps['control-invalid-page']['projection']['fingerprint']


def test_no_established_verdict_without_the_control_or_the_session_check():
    out = run_audit()
    out['steps'] = [s for s in out['steps'] if s['name'] != 'control-invalid-page']
    assert 'NO_INVALID_REQUEST_CONTROL' in c.classify(out)['reasons']
    out = run_audit()
    out['session_check'] = None
    assert 'SESSION_NOT_ALIVE_OR_CRITERIA_CHANGED' in c.classify(out)['reasons']


def run_audit():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / 'p'
        p.mkdir(mode=0o700)
        return run(Council(), p)


@pytest.mark.parametrize('mutate,reason', [
    (lambda a: a['pages'][1].update(overlap_with_earlier_pages=1), 'REPEATED_ROWS'),
    (lambda a: a['pages'][1].update(total=21), 'TOTAL_CHANGED_OR_ABSENT'),
    (lambda a: a['pages'][1].update(first=12), 'IGNORED_OR_MISPLACED_PAGE'),
    (lambda a: a['pages'][0].update(next_present=False), 'PREMATURE_TERMINAL'),
    (lambda a: a['pages'][1].update(terminal=None), 'LAST_PAGE_NOT_EXPLICIT_OR_UNION_MISMATCH'),
    (lambda a: a['pages'][1].update(rows=9), 'IGNORED_OR_MISPLACED_PAGE'),
])
def test_every_advance_condition_is_checked_individually(mutate, reason):
    out = run_audit()
    assert c.classify(out)['verdict'] == 'ESTABLISHED'
    mutate(out)
    result = c.classify(out)
    assert result['verdict'] == 'INCONCLUSIVE' and reason in result['advance']['reasons']


def test_a_single_page_audit_cannot_be_classified_as_established():
    out = run_audit()
    out['pages'] = out['pages'][:1]
    assert c.classify(out)['advance']['reasons'] == ['NOT_MULTI_PAGE']


# ---------------------------------------------------------------------------------------------------------------------------- registration and run
REV, TREE = 'a' * 40, 'b' * 40
IDENT = 'oldham-paging-calibration-20261028-a1'
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def test_the_registration_binds_the_calibration_scope_plan_and_limits():
    r = d.render(IDENT, REV, TREE, NOW.isoformat(), (NOW + timedelta(hours=1)).isoformat(), c.profile())
    assert r['kind'] == c.KIND and r['scope'] == dict(council='oldham', semantics='RECEIVED', start='2026-10-08', end='2026-10-21') and r['limits']['requests'] == 8
    assert r['plan'] == c.PLAN and r['page_size'] == 10 and r['calibratable_total'] == [11, 30] and r['max_pages'] == 3 and r['collection_observation'] is False
    assert r['publication'] == 'NONE' and r['database_synchronised'] is False
    with pytest.raises(ValueError):
        d.render('oldham-search-response-diagnostic-20261028-a1', REV, TREE, NOW.isoformat(), (NOW + timedelta(hours=1)).isoformat(), c.profile())      # another tool's identity
    with pytest.raises(ValueError):
        d.render(IDENT, REV, TREE, NOW.isoformat(), (NOW + timedelta(hours=1)).isoformat())      # the diagnostic profile refuses this identity
    raw = d.canonical(r)
    git = dict(head=REV, tree=TREE, dirty=False)
    assert d.validate(json.loads(raw), d.sha(raw), raw, git=git, clock=lambda: NOW + timedelta(minutes=1), profile=c.profile()) == r
    tampered = dict(r, limits=dict(r['limits'], requests=9))
    with pytest.raises(ValueError):
        d.validate(tampered, d.sha(d.canonical(tampered)), d.canonical(tampered), git=git, clock=lambda: NOW + timedelta(minutes=1), profile=c.profile())
    with pytest.raises(ValueError):      # the diagnostic's own profile does not validate a calibration registration
        d.validate(json.loads(raw), d.sha(raw), raw, git=git, clock=lambda: NOW + timedelta(minutes=1))


def test_the_calibration_run_is_single_use_scope_gated_and_launches_its_own_worker(tmp_path, monkeypatch):
    import verification.stage26b_l1.actions_runner as runner
    monkeypatch.setattr(d, 'STATE_ROOT', tmp_path / 'state')
    monkeypatch.setattr(d, '_git', lambda: dict(head=REV, tree=TREE, dirty=False))
    monkeypatch.setattr(d, 'containment', lambda: dict(scope='x'))
    launched = []
    monkeypatch.setattr(runner, 'supervise', lambda command, **kw: launched.append(command) or (0, False))
    now = datetime.now(timezone.utc)
    raw = d.canonical(d.render(IDENT, REV, TREE, (now - timedelta(minutes=1)).isoformat(), (now + timedelta(hours=1)).isoformat(), c.profile()))
    reg = tmp_path / 'reg.json'
    reg.write_bytes(raw)
    args = ['run', '--registration', str(reg), '--registration-sha256', d.sha(raw), '--enable-reviewed-source-only-diagnostic']
    assert d.main(args, profile=c.profile()) == 1      # the stub worker wrote no audit
    assert launched[0][:4] == [launched[0][0], '-m', 'verification.discovery.idox_paging_calibration', 'worker']
    with pytest.raises(FileExistsError):
        d.main(args, profile=c.profile())
    with pytest.raises(ValueError):
        d.main(args)      # the diagnostic profile rejects the calibration registration


def test_the_worker_needs_the_parents_fresh_claim(tmp_path, monkeypatch):
    monkeypatch.setattr(c, 'live', lambda *a, **k: (_ for _ in ()).throw(AssertionError('a request would have been made')))
    bare = tmp_path / 'bare'
    bare.mkdir(mode=0o700)
    with pytest.raises(ValueError, match='CLAIM_REQUIRED'):
        d.main(['worker', '--directory', str(bare), '--registration-sha256', '0' * 64], profile=c.profile())


# ----------------------------------------------------------------------------------------------------------------- error answers are observed
@pytest.mark.parametrize('control', ['http400', 'http404', 'http500', 'redirect', 'error'])
def test_an_error_or_redirect_answer_to_the_invalid_page_control_is_observed_and_differs_from_the_signal(tmp_path, control):
    private = tmp_path / 'p'
    private.mkdir(mode=0o700)
    out = run(Council(control=control), private)
    assert out['failure'] is None and names(out)[-1] == 'control-invalid-page' and out['resource']['requests_attempted'] == 7 and out['resource']['redirects'] == 0
    assert c.classify(out)['verdict'] == 'ESTABLISHED'


@pytest.mark.parametrize('beyond', ['http404', 'redirect'])
def test_an_error_answer_to_the_beyond_end_request_still_lets_the_session_check_and_control_run(tmp_path, beyond):
    private = tmp_path / 'p'
    private.mkdir(mode=0o700)
    out = run(Council(beyond=beyond), private)
    assert names(out)[-3:] == ['beyond-end', 'session-check', 'control-invalid-page'] and out['failure'] is None
    assert c.classify(out) ['verdict'] == 'INCONCLUSIVE'


def test_classify_is_total_over_incomplete_or_unparseable_exports():
    out = run_audit()
    broken = json.loads(json.dumps(out))
    broken['steps'] = [s for s in broken['steps'] if s['name'] != 'page-2']
    assert c.classify(broken)['reasons'] == ['UNPARSEABLE_EXPORT']
    non_html = json.loads(json.dumps(out))
    end = next(s for s in non_html['steps'] if s['name'] == 'beyond-end')
    end['projection'] = c.project(b'\xff\xfe')
    result = c.classify(non_html)
    assert result['verdict'] == 'INCONCLUSIVE' and 'TRANSPORT_OR_REDIRECT_OR_NOT_HTML' in result['reasons']
    assert c.classify({})['verdict'] == 'INCONCLUSIVE'


@pytest.mark.parametrize('marker,expected', [([0, 0, 20], True), ([21, 20, 20], True), ([25, 24, 20], True), ([11, 20, 20], False), ([1, 10, 20], False), ([15, 20, 20], False)])
def test_a_marker_must_describe_an_empty_range_that_no_earlier_page_showed(marker, expected):
    step = dict(http_status=200, media_type='text/html', redirect='NONE', projection=dict(html=True, headings=[dict(results_heading=True, sha256='x')], rows=0, password_inputs=0, results_containers=1,
                                                                                         pager_markers=[marker], messages=[]))
    assert (c._shape(step, 20, [(1, 10), (11, 20)]) is not None) is expected
