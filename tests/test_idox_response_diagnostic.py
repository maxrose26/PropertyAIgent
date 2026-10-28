"""Offline proof for the Oldham single-page response diagnostic. No council, database or network: every response is a synthetic, sanitised fixture and the dispatch is a stub.

These tests prove the BOUNDS and HANDLING (two requests, no redirects, no retries, private files, no record text or credentials in exports, fail-closed authority). They say nothing about
what the real Oldham response contains; that is the purpose of the owner-approved live diagnostic.
"""
import json
import os
import stat
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_discovery_idox_listing import page as _bolton_page
from tests.test_discovery_idox_window import Response, page
from verification.bolton_recon.fixtures import FORM
from verification.discovery import idox_response_diagnostic as d
from verification.stage26b_l1.request_boundary import BoundaryFailure

PROPOSAL_MARKER = b'Erection of 20 SECRETWORD dwellings'


def raw_page(**kw):
    """The repository's own listing generator with dates inside the Oldham window (sanitised, synthetic)."""
    return _bolton_page(**kw).replace(b'Mon 28 Sep 2026', b'Thu 15 Oct 2026').replace(b'Outline residential development, scale unknown', b'Outline residential development, scale unknown')


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch):
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


def stub(*responses):
    calls = []

    def dispatch(method, url, **kwargs):
        calls.append((method, url, kwargs.get('data')))
        if len(calls) > len(responses):
            raise AssertionError('a request beyond the stubbed responses was attempted')
        return responses[len(calls) - 1]
    return dispatch, calls


# ---------------------------------------------------------------------------------------------------------------------------------------- capture
def test_capture_makes_exactly_the_two_requests_and_keeps_raw_bodies_private(private):
    body = page().replace(b'Outline', PROPOSAL_MARKER)
    dispatch, calls = stub(Resp(FORM), Resp(body))
    out = d.capture(dispatch, d.config(), private)
    assert [c[0] for c in calls] == ['GET', 'POST'] and len(calls) == 2
    assert out['failure'] is None and out['collection_observation'] is False and out['persistence'] is False and out['raw_html_published'] is False
    assert [(r['phase'], r['http_status'], r['media_type'], r['redirect']) for r in out['responses']] == [('FORM', 200, 'text/html', 'NONE'), ('SEARCH', 200, 'text/html', 'NONE')]
    assert out['resource']['requests_attempted'] == 2 and out['resource']['retries'] == 0 and out['resource']['redirects'] == 0 and out['resource']['budget_exhaustion'] is False
    assert out['cleanup'] == 'BOUNDARY_CLOSED'
    for response, raw in zip(out['responses'], (FORM, body)):
        file = private / response['private_file']
        assert file.read_bytes() == raw and response['sha256'] == __import__('hashlib').sha256(raw).hexdigest() and response['bytes'] == len(raw)
        assert stat.S_IMODE(file.stat().st_mode) == 0o600
    exported = json.dumps(out)
    assert 'SECRETWORD' not in exported and '<html' not in exported.lower() and 'cookie' not in exported.lower()


def test_the_search_is_the_exact_date_search_of_the_oldham_window(private):
    dispatch, calls = stub(Resp(FORM), Resp(page()))
    d.capture(dispatch, d.config(), private)
    assert calls[0][1] == d.config().form_url and calls[1][1].startswith('https://planningpa.oldham.gov.uk/online-applications/')
    assert b'15%2F10%2F2026' in calls[1][2] and b'21%2F10%2F2026' in calls[1][2]


def test_a_third_request_is_refused_by_the_budget_not_by_the_stub():
    b = d.DiagnosticBoundary(lambda *a, **k: Resp(page()), d.config())
    b.retrieve('GET', b.config.form_url)
    b.admitted_post = b.config.base + '/advancedSearchResults.do?action=firstPage'
    b.admitted_body = b'x=1'
    b.phase = 'SEARCH'
    b.retrieve('POST', b.admitted_post, b.admitted_body)
    with pytest.raises(BoundaryFailure):
        b.retrieve('POST', b.admitted_post, b.admitted_body)
    assert b.requests == 2 and (b.budget.requests, b.budget.response_bytes, b.budget.total_bytes, b.budget.seconds) == (2, 500_000, 1_000_000, 45)


def test_the_declared_limits_are_the_existing_reader_ceilings_not_a_function_of_a_previous_response():
    assert d.LIMITS == dict(requests=2, response_bytes=500_000, total_bytes=1_000_000, reader_seconds=45, connect_seconds=3, read_seconds=8, supervisor_seconds=50, max_registration_hours=2)
    assert d.LIMITS['total_bytes'] == d.LIMITS['requests'] * d.LIMITS['response_bytes']


@pytest.mark.parametrize('first', [Resp(b'<html></html>', status=404), Resp(b'<html></html>', status=503), Resp(b'<html></html>', status=302, headers={'Content-Type': 'text/html', 'Location': '/x'}),
                                   Resp(b'%PDF', headers={'Content-Type': 'application/pdf'})])
def test_a_bad_form_response_stops_without_a_search_a_retry_or_a_saved_body(private, first):
    dispatch, calls = stub(first)
    out = d.capture(dispatch, d.config(), private)
    assert len(calls) == 1 and out['failure'] is not None and out['responses'] == [] and list(private.iterdir()) == []
    assert out['resource']['retries'] == 0


def test_a_redirected_search_is_not_followed(private):
    dispatch, calls = stub(Resp(FORM), Resp(b'', status=302, headers={'Content-Type': 'text/html', 'Location': d.config().base + '/search.do'}))
    out = d.capture(dispatch, d.config(), private)
    assert len(calls) == 2 and out['failure'] is not None and [r['phase'] for r in out['responses']] == ['FORM'] and not (private / 'search.html').exists()


def test_an_oversize_response_is_refused_and_not_stored(private):
    dispatch, calls = stub(Resp(FORM), Resp(b'<html>' + b'x' * 500_001 + b'</html>'))
    out = d.capture(dispatch, d.config(), private)
    assert out['failure'] is not None and not (private / 'search.html').exists() and out['resource']['budget_exhaustion'] is True


def test_set_cookie_and_other_headers_never_reach_the_export_or_disk(private):
    headers = {'Content-Type': 'text/html', 'Set-Cookie': 'JSESSIONID=SECRETSESSION; Path=/', 'X-Other': 'SECRETHEADER'}
    dispatch, _ = stub(Resp(FORM, headers=headers), Resp(page(), headers=headers))
    out = d.capture(dispatch, d.config(), private)
    assert 'SECRET' not in json.dumps(out) and all(b'SECRETSESSION' not in f.read_bytes() for f in private.iterdir())


@pytest.mark.parametrize('make', [lambda p: p / 'absent', lambda p: p.parent.joinpath('loose').__class__(p.parent / 'loose')])
def test_the_private_directory_must_exist_with_mode_0700(tmp_path, make):
    target = make(tmp_path)
    if target.name == 'loose':
        target.mkdir()
        os.chmod(target, 0o755)
    dispatch, calls = stub()
    with pytest.raises(ValueError, match='PRIVATE_DIRECTORY'):
        d.capture(dispatch, d.config(), target)
    assert calls == []


def test_a_symlinked_private_directory_is_refused(tmp_path, private):
    link = tmp_path / 'link'
    link.symlink_to(private)
    with pytest.raises(ValueError, match='PRIVATE_DIRECTORY'):
        d.capture(stub()[0], d.config(), link)


def test_existing_private_files_are_never_overwritten_and_stop_before_the_search(private):
    (private / 'form.html').write_bytes(b'earlier')
    dispatch, calls = stub(Resp(FORM), Resp(page()))
    out = d.capture(dispatch, d.config(), private)
    assert len(calls) == 1 and out['failure']['error'] == 'UNCLASSIFIED_FAILURE' and (private / 'form.html').read_bytes() == b'earlier'


# --------------------------------------------------------------------------------------------------------------------------------------- inspector
def inspect(body):
    return d.inspect_html(body)


def test_a_page_with_no_signal_reports_none_and_the_parser_view():
    r = inspect(raw_page(pager=False))
    assert r['count_text'] == [] and r['navigation_links'] == [] and r['signal_inputs'] == [] and r['scripts'] == []
    assert r['parser_selector'] == dict(pager_elements=0, next_anchors_in_pager=0)
    assert r['parser']['accepted'] and r['parser']['total'] is None and r['parser']['terminal'] is None and r['parser']['next_url_present'] is False
    assert r['structure']['result_rows'] == 2 and r['structure']['results_containers'] == 1


def test_a_recognised_pager_is_reported_as_such():
    r = inspect(raw_page(first=1, last=2, total=2))
    assert r['parser']['total'] == 2 and r['parser']['terminal'] == 'EXPLICIT_LAST_EQUALS_TOTAL' and r['parser_selector']['pager_elements'] == 1
    assert any(h['pattern'] == 'SHOWING_RANGE_OF_TOTAL' and 'p.pager' in h['element'] for h in r['count_text'])


@pytest.mark.parametrize('markup,expect', [
    (b'<div class="resultsInfo"><span>5 results found</span></div>', lambda r: any(h['pattern'] == 'NUMBER_RESULTS' and 'resultsInfo' in h['element'] for h in r['count_text'])),
    (b'<p class="info">Showing 1 - 5 of 5</p>', lambda r: any(h['pattern'] == 'SHOWING_RANGE_OF_TOTAL' for h in r['count_text'])),
    (b'<p>This is the last page</p>', lambda r: any(h['pattern'] == 'END_OR_NONE_WORDING' for h in r['count_text'])),
    (b'<script>var searchState = {"totalResults": 5, "page": 1};</script>', lambda r: {'name': 'totalResults', 'value': 5} in r['scripts'][0]['numeric_assignments']),
    (b'<a class="next disabled" href="/online-applications/pagedSearchResults.do?searchCriteria.page=2">Next</a>',
     lambda r: r['navigation_links'][0]['parameter_names'] == ['searchCriteria.page'] and any(e['disabled'] for e in r['navigation_like_elements'])),
    (b'<link rel="next" href="/online-applications/pagedSearchResults.do?searchCriteria.page=2">', lambda r: r['navigation_links'][0]['rel'] == ['next']),
    (b'<form action="/online-applications/pagedSearchResults.do"><input type="hidden" name="searchCriteria.page" value="1"><input type="hidden" name="resultCount" value="5"></form>',
     lambda r: {i['name']: i['value'] for i in r['signal_inputs']} == {'searchCriteria.page': '1', 'resultCount': '5'}),
    (b'<meta name="totalResults" content="5">', lambda r: r['meta'] == [dict(name='totalResults', content='5')]),
])
def test_signals_outside_the_pager_selector_are_found_and_the_parser_still_sees_none(markup, expect):
    r = inspect(raw_page(pager=False).replace(b'</body>', markup + b'</body>') if b'</body>' in raw_page(pager=False) else raw_page(pager=False).replace(b'</html>', markup + b'</html>'))
    assert expect(r), r
    assert r['parser']['total'] is None and r['parser']['terminal'] is None and r['parser_selector']['pager_elements'] == 0      # the mismatch is visible, never silently reconciled


def test_record_text_is_never_read_or_reported():
    body = raw_page(pager=False).replace(b'Outline', PROPOSAL_MARKER + b' 7 results of 9 Showing 1-2 of 9')
    r = inspect(body)
    assert 'SECRETWORD' not in json.dumps(r) and r['count_text'] == [] and [e['element'] for e in r['navigation_like_elements']] == ['select#resultsPerPage < html']      # the results list is never read, described or counted as a signal, even when it looks like a count


def test_lists_are_bounded():
    many = b''.join(b'<span>%d results</span>' % i for i in range(100))
    r = inspect(raw_page(pager=False).replace(b'</html>', many + b'</html>'))
    assert len(r['count_text']) == d.MAX_ITEMS and all(len(h['text']) <= d.TEXT + 1 for h in r['count_text'])


def test_an_invalid_encoding_is_reported_not_raised():
    assert inspect(b'\xff\xfe\x00')['availability'] == 'INVALID_ENCODING'


def test_an_explicit_no_results_page_is_reported():
    r = inspect(b'<html><body><h1>Planning \xe2\x80\x93 Applications Search</h1><div class="messagebox"><ul><li>No results found.</li></ul></div></body></html>')
    assert any(h['pattern'] == 'END_OR_NONE_WORDING' for h in r['count_text']) and r['structure']['message_boxes'] == 1 and r['parser']['accepted'] is False


# ------------------------------------------------------------------------------------------------------------------------- registration and run
REV, TREE = 'a' * 40, 'b' * 40
IDENT = 'oldham-search-response-diagnostic-20261028-a1'
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def reg(**kw):
    args = dict(identity=IDENT, revision=REV, tree=TREE, issued=NOW.isoformat(), expires=(NOW + timedelta(hours=1)).isoformat())
    args.update(kw)
    return d.render(args['identity'], args['revision'], args['tree'], args['issued'], args['expires'])


def test_the_registration_is_inactive_scoped_and_database_free():
    r = reg()
    assert r['scope'] == dict(council='oldham', semantics='RECEIVED', start='2026-10-15', end='2026-10-21') and r['limits']['requests'] == 2
    assert r['publication'] == 'NONE' and r['database_synchronised'] is False and r['collection_observation'] is False and r['preserved_stops'] == d.PRESERVED


@pytest.mark.parametrize('change', [dict(identity='bolton-x'), dict(identity=IDENT.upper()), dict(revision='z' * 40), dict(tree='1'), dict(expires=(NOW + timedelta(hours=3)).isoformat()),
                                    dict(expires=NOW.isoformat()), dict(issued='2026-10-28T12:00:00', expires='2026-10-28T13:00:00')])
def test_render_refuses_bad_identity_binding_or_interval(change):
    with pytest.raises(ValueError):
        reg(**change)


def test_validate_binds_the_exact_bytes_the_clock_and_the_checkout():
    r = reg()
    raw = d.canonical(r)
    git = dict(head=REV, tree=TREE, dirty=False)
    assert d.validate(json.loads(raw), d.sha(raw), raw, clock=lambda: NOW + timedelta(minutes=5), git=git) == r
    for kwargs in (dict(clock=lambda: NOW - timedelta(seconds=1)), dict(clock=lambda: NOW + timedelta(hours=1)), dict(git=dict(git, head='c' * 40)), dict(git=dict(git, tree='c' * 40)), dict(git=dict(git, dirty=True))):
        with pytest.raises(ValueError):
            d.validate(json.loads(raw), d.sha(raw), raw, **{'clock': lambda: NOW + timedelta(minutes=5), 'git': git, **kwargs})
    with pytest.raises(ValueError, match='REGISTRATION_HASH'):
        d.validate(json.loads(raw), '0' * 64, raw, clock=lambda: NOW + timedelta(minutes=5))
    tampered = dict(r, limits=dict(r['limits'], requests=3))
    with pytest.raises(ValueError):
        d.validate(tampered, d.sha(d.canonical(tampered)), d.canonical(tampered), clock=lambda: NOW + timedelta(minutes=5))


def run_args(tmp_path, flag=True, sha=None):
    r = reg(issued=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), expires=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    raw = d.canonical(r)
    path = tmp_path / 'reg.json'
    path.write_bytes(raw)
    return ['run', '--registration', str(path), '--registration-sha256', sha or d.sha(raw)] + (['--enable-reviewed-source-only-diagnostic'] if flag else [])


def test_run_is_single_use_and_creates_nothing_without_the_enabling_flag(tmp_path, monkeypatch):
    import verification.stage26b_l1.actions_runner as runner
    monkeypatch.setattr(d, 'STATE_ROOT', tmp_path / 'state')
    monkeypatch.setattr(d, '_git', lambda: dict(head=REV, tree=TREE, dirty=False))
    launched = []
    monkeypatch.setattr(runner, 'supervise', lambda command, **kw: launched.append(command) or (0, False))
    with pytest.raises(ValueError, match='DIAGNOSTIC_NOT_ENABLED'):
        d.main(run_args(tmp_path, flag=False))
    assert not (tmp_path / 'state').exists() and launched == []
    with pytest.raises(ValueError, match='REGISTRATION_HASH'):
        d.main(run_args(tmp_path, sha='0' * 64))
    assert not (tmp_path / 'state').exists()
    assert d.main(run_args(tmp_path)) == 1      # the stub child wrote no audit: reported as a failed run, not success
    directory = tmp_path / 'state' / IDENT
    assert len(launched) == 1 and stat.S_IMODE(directory.stat().st_mode) == 0o700 and (directory / 'registration.json').exists()
    with pytest.raises(FileExistsError):
        d.main(run_args(tmp_path))      # consumed: never replayed
    assert len(launched) == 1


def test_run_refuses_a_credential_environment_and_a_wrong_checkout(tmp_path, monkeypatch):
    import verification.stage26b_l1.actions_runner as runner
    monkeypatch.setattr(d, 'STATE_ROOT', tmp_path / 'state')
    monkeypatch.setattr(runner, 'supervise', lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not launch')))
    monkeypatch.setattr(d, '_git', lambda: dict(head=REV, tree=TREE, dirty=False))
    monkeypatch.setenv('DATABASE_URL', 'x')
    with pytest.raises(ValueError, match='OWNER_CREDENTIAL_CONTEXT'):
        d.main(run_args(tmp_path))
    monkeypatch.delenv('DATABASE_URL')
    monkeypatch.setattr(d, '_git', lambda: dict(head='c' * 40, tree=TREE, dirty=False))
    with pytest.raises(ValueError, match='CHECKOUT_BINDING'):
        d.main(run_args(tmp_path))
    assert not (tmp_path / 'state').exists()


def test_the_module_makes_no_request_on_import_render_or_inspect(monkeypatch):
    import socket
    monkeypatch.setattr(socket, 'socket', lambda *a, **k: (_ for _ in ()).throw(AssertionError('network')))
    reg()
    inspect(raw_page(pager=False))
