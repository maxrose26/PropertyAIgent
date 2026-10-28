"""Offline proof for the Oldham single-page count-signal probe: bounds, stop conditions and the predeclared classifier, against a scripted fake council (synthetic, sanitised markup; no network).
Passing these tests proves the TOOL's handling and decision rules, not what the real portal returns."""
import json
import os
import stat
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_discovery_idox_listing import page as _bolton_page
from tests.test_discovery_idox_window import SORT, Response
from tests import test_idox_paging_calibration as cal_tests
from verification.bolton_recon.fixtures import FORM
from verification.discovery import idox_paging_calibration as cal
from verification.discovery import idox_response_diagnostic as d
from verification.discovery import idox_single_page_probe as pr

BASE = 'https://planningpa.oldham.gov.uk/online-applications'
HEADING = '<h1>Planning – Results for Application Search</h1>'
REFS = ['R005/26', 'R004/26', 'R003/26', 'R002/26', 'R001/26']


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


def single_page(refs=REFS, *, proposal=None, pager=False, total=None, next_page=None):
    body = _bolton_page(first=1, last=len(refs), total=total or len(refs), refs=tuple(refs), pager=pager, next_page=next_page).replace(b'Mon 28 Sep 2026', b'Thu 15 Oct 2026').replace(b'keyVal=K', b'keyVal=S')
    if proposal:
        body = body.replace(b'Outline residential development, scale unknown', proposal)
    return body.replace(b'</html>', SORT + b'</html>')


def echo():
    return FORM.replace(b'name="date(applicationReceivedStart)" value=""', b'name="date(applicationReceivedStart)" value="15/10/2026"').replace(
        b'name="date(applicationReceivedEnd)" value=""', b'name="date(applicationReceivedEnd)" value="21/10/2026"')


def shell(inner, heading=HEADING):
    return ('<html>' + heading + inner + '</html>').encode()


def marker(first, last, total):
    return shell('<p class="pager">Showing %s - %s of %s</p><ul id="searchresults"></ul>' % (first, last, total))


def original_audit(refs=REFS):
    return dict(council='oldham', date_semantics='RECEIVED', requested_interval=['2026-10-15', '2026-10-21'], failure=None,
                records=[dict(reference=r, source_key='SK%d' % i, fields={'proposal': dict(value=None), 'address': dict(value=None), 'received_date': dict(value=None), 'validated_date': dict(value=None)})
                         for i, r in enumerate(refs)])


def expected_for(refs=REFS, proposal=None):
    """The registration's expected-record hashes, built from the same generator through the production helper."""
    return pr.expected_from_audit(original_audit(refs), '1' * 64)


def seen_expected(private_dir_unused=None, refs=REFS, proposal=None):
    """Expected hashes computed from what the fake serves, so that the unchanged scenario matches exactly."""
    from verification.discovery.idox_window import WindowConfig
    from app.scrapers.discovery_idox import parse_page
    page = parse_page(single_page(refs, proposal=proposal), 'oldham', 1, pr.config().start, pr.config().end, 'RECEIVED')
    ids = sorted(pr.identity_digest(r.reference, r.source_key) for r in page.rows)
    metas = sorted(pr.metadata_digest(r.fields['proposal'].value, r.fields['address'].value, r.fields['received_date'].value, r.fields['validated_date'].value) for r in page.rows)
    joint = sorted(pr.record_digest(pr.identity_digest(r.reference, r.source_key), pr.metadata_digest(r.fields['proposal'].value, r.fields['address'].value, r.fields['received_date'].value,
                                                                                                  r.fields['validated_date'].value)) for r in page.rows)
    return dict(count=len(ids), source_audit_sha256='2' * 64, identity_sha256=ids, metadata_sha256=metas, record_sha256=joint)


class Council:
    def __init__(self, page2='explicit', control='http500', page1=None, alive=True):
        self.calls, self.page2_kind, self.control_kind, self.alive = [], page2, control, alive
        self.p1 = page1 if page1 is not None else single_page()

    def __call__(self, method, url, **kw):
        self.calls.append((method, url))
        if method == 'GET' and url.endswith('/search.do?action=advanced&searchType=Application'):
            return Resp(FORM)
        if method == 'POST' and ('advancedSearchResults.do' in url or url.endswith('/pagedSearchResults.do')):
            return Resp(self.p1)
        if method == 'GET' and 'refineSearch.do' in url:
            return Resp(echo() if self.alive else FORM)
        if method == 'GET' and 'searchCriteria.page=' in url:
            return self.special(self.control_kind if url.endswith('page=0') else self.page2_kind)
        raise AssertionError('unscripted request ' + method + ' ' + url)

    def special(self, kind):
        n = len(REFS)
        table = {
            'explicit': Resp(marker(11, n, n)), 'zero_zero': Resp(marker(0, 0, n)), 'greater': Resp(marker(11, 9, 9)), 'smaller': Resp(marker(11, 3, 3)),
            'malformed': Resp(shell('<p class="pager">Showing 11 - x of y</p><ul id="searchresults"></ul>')), 'missing': Resp(shell('<ul id="searchresults"></ul>')),
            'repeat_page1': Resp(self.p1), 'wrong_page_marker': Resp(marker(21, n, n)), 'nonempty_marker': Resp(marker(1, n, n)),
            'error_page': Resp(shell('<p>Sorry</p>', heading='<h1>Error</h1>')), 'http500': Resp(shell('<p>Sorry</p>', heading='<h1>Error</h1>'), status=500), 'http404': Resp(b'<html>x</html>', status=404),
            'redirect': Resp(b'', status=302, headers={'Content-Type': 'text/html', 'Location': BASE + '/search.do'}), 'login': Resp(shell('<form><input type="password" name="p"></form>', heading='<h1>Sign in</h1>')),
            'message_only': Resp(shell('<div class="messagebox"><ul><li>There are no more results.</li></ul></div><ul id="searchresults"></ul>')), 'download': Resp(b'%PDF', headers={'Content-Type': 'application/pdf'}),
        }
        return table[kind]


def run(council, private, expected=None):
    return pr.capture(council, pr.config(), private, expected or seen_expected())


def names(out):
    return [s['name'] for s in out['steps']]


# ---------------------------------------------------------------------------------------------------------------------------------------- bounds
def test_the_sequence_is_exactly_six_requests_in_order_with_the_verified_page_url(private):
    council = Council()
    out = run(council, private)
    assert out['failure'] is None and out['abort'] is None and names(out) == ['form', 'search', 'page-1', 'page-2', 'session-check', 'control-invalid-page']
    assert [m for m, _ in council.calls] == ['GET', 'POST', 'POST', 'GET', 'GET', 'GET'] and out['resource']['requests_attempted'] == 6 == pr.LIMITS['requests']
    assert council.calls[3][1] == BASE + '/pagedSearchResults.do?action=page&searchCriteria.page=2'
    assert council.calls[5][1] == BASE + '/pagedSearchResults.do?action=page&searchCriteria.page=0'
    assert out['resource']['retries'] == 0 and out['resource']['redirects'] == 0 and out['resource']['budget_exhaustion'] is False


def test_the_ceilings_are_the_calibrations_with_only_the_request_cap_changed():
    assert pr.LIMITS == dict(cal.LIMITS, requests=6) and pr.LIMITS['response_bytes'] == 500_000 and pr.LIMITS['total_bytes'] == 3_000_000 and pr.LIMITS['reader_seconds'] == 45
    b = pr.ProbeBoundary(lambda *a, **k: None, pr.config())
    assert (b.budget.requests, b.budget.response_bytes, b.budget.total_bytes, b.budget.seconds) == (6, 500_000, 3_000_000, 45)


def test_a_seventh_request_is_refused_by_the_budget():
    from verification.stage26b_l1.request_boundary import BoundaryFailure
    b = pr.ProbeBoundary(lambda *a, **k: Resp(single_page()), pr.config())
    b.retrieve('GET', b.config.form_url)
    b.admitted_post, b.admitted_body, b.phase = b.config.base + '/advancedSearchResults.do?action=firstPage', b'x=1', 'SEARCH'
    b.retrieve('POST', b.admitted_post, b.admitted_body)
    b.phase = 'SORT'
    b.admitted_post, b.admitted_body = b.config.base + '/pagedSearchResults.do', b'x=1'
    b.retrieve('POST', b.admitted_post, b.admitted_body)
    for n in (2, 0):
        url = BASE + '/pagedSearchResults.do?action=page&searchCriteria.page=%d' % n
        b.phase, b.extra = ('BEYOND_END' if n == 2 else 'CONTROL'), {('BEYOND_END' if n == 2 else 'CONTROL'): url}
        b.observe(url)
    b.phase = 'REFINE'
    b.retrieve('GET', b.policy.base_url + '/refineSearch.do?action=refine')
    assert b.requests == 6
    with pytest.raises(BoundaryFailure):
        b.retrieve('GET', b.policy.base_url + '/refineSearch.do?action=refine')
    assert b.requests == 6


@pytest.mark.parametrize('p1,reason', [(single_page(['R%03d/26' % (50 - i) for i in range(10)], pager=True, total=14, next_page=2), 'NOT_SINGLE_PAGE_SHAPE')], ids=['multi-page-pager'])
def test_a_page_1_that_is_not_the_single_page_shape_stops_before_page_2(private, p1, reason):
    council = Council(page1=p1)
    out = run(council, private)
    assert out['abort'] == reason and out['resource']['requests_attempted'] == 3 and not any('searchCriteria.page=' in u for _, u in council.calls)
    assert pr.classify_probe(out)['verdict'] == 'INCONCLUSIVE'


def test_raw_bodies_are_private_and_the_export_holds_no_record_text_key_or_reference(private):
    import re
    out = run(Council(), private)
    exported = json.dumps(out)
    assert not re.search(r'R\d{3}/26', exported) and 'SK0' not in exported and 'keyVal=' not in exported and '<html' not in exported.lower() and '"_keys"' not in exported
    assert all(set(h) == {'results_heading', 'sha256'} for s in out['steps'] for h in s['projection'].get('headings', []))
    for s in out['steps']:
        f = private / s['private_file']
        assert stat.S_IMODE(f.stat().st_mode) == 0o600 and f.read_bytes()


# ---------------------------------------------------------------------------------------------------------------------------------- classifier
def verdict(council, private, expected=None):
    return pr.classify_probe(run(council, private, expected))


def fresh(tmp_path, name='p'):
    p = tmp_path / name
    p.mkdir(mode=0o700)
    return p


def test_a_valid_explicit_total_with_a_distinct_control_is_established_and_applies_to_the_original(tmp_path):
    result = verdict(Council(), fresh(tmp_path))
    assert result['verdict'] == 'ESTABLISHED' and result['reasons'] == [] and result['signal'] == dict(marker_total=5, seen=5) and result['historical_application'] == 'APPLICABLE'
    zero = verdict(Council(page2='zero_zero'), fresh(tmp_path, 'q'))
    assert zero['verdict'] == 'INCONCLUSIVE' and 'NO_EXPLICIT_EMPTY_RANGE_MARKER_FOR_PAGE_2' in zero['reasons']      # a 0-0 marker is not FOR page 2


@pytest.mark.parametrize('kind,reason', [
    ('missing', 'NO_EXPLICIT_EMPTY_RANGE_MARKER_FOR_PAGE_2'), ('malformed', 'NO_EXPLICIT_EMPTY_RANGE_MARKER_FOR_PAGE_2'), ('message_only', 'NO_EXPLICIT_EMPTY_RANGE_MARKER_FOR_PAGE_2'),
    ('repeat_page1', 'REPEATED_OR_CLAMPED_PAGE'), ('wrong_page_marker', 'NO_EXPLICIT_EMPTY_RANGE_MARKER_FOR_PAGE_2'), ('nonempty_marker', 'NO_EXPLICIT_EMPTY_RANGE_MARKER_FOR_PAGE_2'),
    ('error_page', 'NO_EXPLICIT_EMPTY_RANGE_MARKER_FOR_PAGE_2'), ('login', 'NO_EXPLICIT_EMPTY_RANGE_MARKER_FOR_PAGE_2'),
    ('http500', 'TRANSPORT_OR_REDIRECT_OR_NOT_HTML'), ('http404', 'TRANSPORT_OR_REDIRECT_OR_NOT_HTML'), ('redirect', 'TRANSPORT_OR_REDIRECT_OR_NOT_HTML'), ('download', None)])
def test_missing_repeated_clamped_generic_or_failed_page_2_answers_stay_inconclusive(tmp_path, kind, reason):
    result = verdict(Council(page2=kind), fresh(tmp_path))
    assert result['verdict'] == 'INCONCLUSIVE', result
    if reason:
        assert reason in result['reasons']


@pytest.mark.parametrize('kind,reason', [('greater', 'TOTAL_GREATER_THAN_RECORDS_SEEN'), ('smaller', 'TOTAL_LESS_THAN_RECORDS_SEEN')])
def test_a_well_formed_total_that_differs_from_the_records_seen_is_unreconciled_not_established(tmp_path, kind, reason):
    result = verdict(Council(page2=kind), fresh(tmp_path))
    assert result['verdict'] == 'UNRECONCILED' and result['reasons'] == [reason]      # cause undetermined: changed result set, reader defect or portal


def test_the_expected_count_is_never_forced(tmp_path):
    """An expected record count of 9 in the registration does not turn a total of 9 into success: only the records actually seen on page 1 reconcile."""
    wrong = seen_expected()
    wrong.update(count=9, identity_sha256=sorted({'%064x' % i for i in range(9)}), metadata_sha256=sorted('%064x' % i for i in range(9)), record_sha256=sorted('%064x' % (i + 100) for i in range(9)))
    result = verdict(Council(page2='greater'), fresh(tmp_path), wrong)
    assert result['verdict'] == 'UNRECONCILED' and result['historical_application'] == 'WITHHELD_NO_ESTABLISHED_SIGNAL'


@pytest.mark.parametrize('refs,proposal,applicable', [
    (REFS, None, 'APPLICABLE'), (REFS[:-1] + ['R099/26'], None, 'WITHHELD_DRIFT'), (REFS + ['R006/26'], None, 'WITHHELD_DRIFT'), (REFS[:4], None, 'WITHHELD_DRIFT'),
    (REFS, b'Changed proposal wording', 'WITHHELD_DRIFT')])
def test_a_changed_original_record_set_or_metadata_is_reported_as_drift_and_withholds_application(tmp_path, refs, proposal, applicable):
    council = Council(page1=single_page(refs, proposal=proposal))
    out = run(council, fresh(tmp_path), seen_expected())      # expectation: the ORIGINAL five, unchanged
    n = len(refs)
    council2 = Council(page1=single_page(refs, proposal=proposal), page2='explicit')
    council2.special = lambda kind, c=council2, n=n: Resp(marker(11, n, n)) if kind == 'explicit' else Resp(shell('<p>Sorry</p>', heading='<h1>Error</h1>'), status=500)
    result = pr.classify_probe(run(council2, fresh(tmp_path, 'r'), seen_expected()))
    assert result['verdict'] == 'ESTABLISHED' and result['historical_application'] == applicable      # the signal can hold while the historical observation is withheld
    assert result['drift']['expected_count'] == 5 and result['drift']['seen_count'] == n
    assert 'SK' not in json.dumps(out) and 'R0' not in json.dumps(out['original_comparison'])


def test_drift_counts_distinguish_identity_from_metadata(tmp_path):
    ident = pr.classify_probe(run(Council(page1=single_page(REFS[:-1] + ['R099/26'])), fresh(tmp_path), seen_expected()))
    assert ident['drift']['identity_missing'] == 1 and ident['drift']['identity_extra'] == 1
    meta = pr.classify_probe(run(Council(page1=single_page(REFS, proposal=b'Changed proposal wording')), fresh(tmp_path, 'm'), seen_expected()))
    assert meta['drift']['identity_missing'] == meta['drift']['identity_extra'] == 0 and meta['drift']['metadata_matches'] == 0


@pytest.mark.parametrize('control,reason', [('explicit', 'CONTROL_NOT_DISTINCT_FROM_THE_SIGNAL'), ('zero_zero', 'CONTROL_NOT_DISTINCT_FROM_THE_SIGNAL')])
def test_a_control_that_shows_the_exhaustion_shape_is_not_a_distinct_control(tmp_path, control, reason):
    result = verdict(Council(control=control), fresh(tmp_path))
    assert result['verdict'] == 'INCONCLUSIVE' and reason in result['reasons']


@pytest.mark.parametrize('control', ['http500', 'http404', 'redirect', 'error_page', 'login', 'missing'])
def test_an_error_redirect_or_generic_control_is_recorded_and_distinct(tmp_path, control):
    out = run(Council(control=control), fresh(tmp_path))
    assert out['failure'] is None and names(out)[-1] == 'control-invalid-page' and out['resource']['requests_attempted'] == 6 and pr.classify_probe(out)['verdict'] == 'ESTABLISHED'


def test_the_control_is_mandatory_and_a_failed_or_absent_control_cannot_establish(tmp_path):
    out = run(Council(control='download'), fresh(tmp_path))      # a download type refuses the control: the run fails at CONTROL
    assert out['failure']['stage'] == 'CONTROL' and pr.classify_probe(out)['verdict'] == 'INCONCLUSIVE'
    ok = run(Council(), fresh(tmp_path, 'b'))
    ok['steps'] = [s for s in ok['steps'] if s['name'] != 'control-invalid-page']
    assert 'NO_INVALID_REQUEST_CONTROL' in pr.classify_probe(ok)['reasons']
    same = run(Council(control='explicit'), fresh(tmp_path, 'c'))
    assert pr.classify_probe(same)['verdict'] == 'INCONCLUSIVE'
    identical = run(Council(page2='http500', control='http500'), fresh(tmp_path, 'd'))
    assert pr.classify_probe(identical)['verdict'] == 'INCONCLUSIVE'


def test_a_lost_session_or_changed_criteria_cannot_establish(tmp_path):
    result = verdict(Council(alive=False), fresh(tmp_path))
    assert result['verdict'] == 'INCONCLUSIVE' and 'SESSION_NOT_ALIVE_OR_CRITERIA_CHANGED' in result['reasons']


def test_accounting_that_shows_a_retry_or_redirect_follow_disqualifies(tmp_path):
    out = run(Council(), fresh(tmp_path))
    out['resource']['retries'] = 1
    assert 'ACCOUNTING_DISQUALIFIES' in pr.classify_probe(out)['reasons']


@pytest.mark.parametrize('mutate,reason', [
    (lambda a: a['page1'].update(rows=0), 'PAGE_1_NOT_RECOGNISED_SORTED_AND_UNIQUE'), (lambda a: a['page1'].update(unique_keys=False), 'PAGE_1_NOT_RECOGNISED_SORTED_AND_UNIQUE'),
    (lambda a: a['page1'].update(sort_retained=False), 'PAGE_1_NOT_RECOGNISED_SORTED_AND_UNIQUE'), (lambda a: a['page1'].update(total=5), 'PAGE_1_NOT_THE_SINGLE_PAGE_SHAPE'),
    (lambda a: a['page1'].update(terminal='EXPLICIT_LAST_EQUALS_TOTAL'), 'PAGE_1_NOT_THE_SINGLE_PAGE_SHAPE')])
def test_every_page_1_precondition_is_checked(tmp_path, mutate, reason):
    out = run(Council(), fresh(tmp_path))
    assert pr.classify_probe(out)['verdict'] == 'ESTABLISHED'
    mutate(out)
    assert reason in pr.classify_probe(out)['reasons']


def test_classify_probe_is_total_over_broken_exports(tmp_path):
    out = run(Council(), fresh(tmp_path))
    broken = json.loads(json.dumps(out))
    broken['steps'] = [s for s in broken['steps'] if s['name'] != 'page-1']
    assert pr.classify_probe(broken)['reasons'] == ['UNPARSEABLE_EXPORT'] and pr.classify_probe({})['verdict'] == 'INCONCLUSIVE'


# ---------------------------------------------------------------------------------------------------------- registration, profile separation, run
REV, TREE = 'a' * 40, 'b' * 40
IDENT = 'oldham-single-page-count-probe-20261028-a1'
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def reg(profile=None, **kw):
    args = dict(identity=IDENT, revision=REV, tree=TREE, issued=NOW.isoformat(), expires=(NOW + timedelta(hours=1)).isoformat())
    args.update(kw)
    return d.render(args['identity'], args['revision'], args['tree'], args['issued'], args['expires'], profile or pr.profile(seen_expected()))


def test_the_registration_binds_scope_plan_limits_control_and_expected_hashes():
    r = reg()
    assert r['kind'] == pr.KIND and r['scope'] == dict(council='oldham', semantics='RECEIVED', start='2026-10-15', end='2026-10-21') and r['limits']['requests'] == 6
    assert r['plan'] == pr.PLAN and r['control'] == 'MANDATORY' and r['rule'] == 'classify_probe:v1' and r['expected_records']['count'] == 5 and r['collection_observation'] is False
    assert r['publication'] == 'NONE' and r['database_synchronised'] is False
    assert 'R00' not in json.dumps(r) and 'SK' not in json.dumps(r)      # hashes only


@pytest.mark.parametrize('bad', [None, {}, dict(count=5), dict(seen_expected(), count=4), dict(seen_expected(), identity_sha256=['x'] * 5), dict(seen_expected(), source_audit_sha256='z'),
                                 dict(seen_expected(), identity_sha256=sorted(seen_expected()['identity_sha256'], reverse=True))])
def test_malformed_expected_records_are_refused(bad):
    with pytest.raises(ValueError):
        pr.profile(bad)


def test_profiles_do_not_accept_each_others_registrations():
    probe_profile, cal_profile = pr.profile(seen_expected()), cal.profile()
    git = dict(head=REV, tree=TREE, dirty=False)
    clock = lambda: NOW + timedelta(minutes=1)
    raw = d.canonical(reg())
    assert d.validate(json.loads(raw), d.sha(raw), raw, git=git, clock=clock, profile=probe_profile)['kind'] == pr.KIND
    for other in (cal_profile, d.default_profile()):
        with pytest.raises(ValueError):
            d.validate(json.loads(raw), d.sha(raw), raw, git=git, clock=clock, profile=other)
    for other_reg in (d.canonical(d.render('oldham-paging-calibration-20261028-a1', REV, TREE, NOW.isoformat(), (NOW + timedelta(hours=1)).isoformat(), cal_profile)),
                      d.canonical(d.render('oldham-search-response-diagnostic-20261028-a1', REV, TREE, NOW.isoformat(), (NOW + timedelta(hours=1)).isoformat()))):
        with pytest.raises(ValueError):
            d.validate(json.loads(other_reg), d.sha(other_reg), other_reg, git=git, clock=clock, profile=probe_profile)


def test_the_registration_cannot_be_tampered_or_used_outside_its_window():
    git = dict(head=REV, tree=TREE, dirty=False)
    r = reg()
    raw = d.canonical(r)
    p = pr.profile(seen_expected())
    for kwargs in (dict(clock=lambda: NOW - timedelta(seconds=1)), dict(clock=lambda: NOW + timedelta(hours=1)), dict(git=dict(git, head='c' * 40)), dict(git=dict(git, dirty=True))):
        with pytest.raises(ValueError):
            d.validate(json.loads(raw), d.sha(raw), raw, **{'git': git, 'clock': lambda: NOW + timedelta(minutes=1), 'profile': p, **kwargs})
    tampered = dict(r, expected_records=dict(r['expected_records'], count=4))
    with pytest.raises(ValueError):
        d.validate(tampered, d.sha(d.canonical(tampered)), d.canonical(tampered), git=git, clock=lambda: NOW + timedelta(minutes=1), profile=p)
    with pytest.raises(ValueError):
        d.render(IDENT, REV, TREE, NOW.isoformat(), (NOW + timedelta(hours=3)).isoformat(), p)      # more than two hours


def test_the_cli_renders_from_the_consumed_audit_as_hashes_and_run_and_worker_take_the_approved_registrations_hashes(tmp_path, monkeypatch):
    import verification.stage26b_l1.actions_runner as runner
    audit = original_audit()
    audit_path = tmp_path / 'source-0.json'
    audit_path.write_text(json.dumps(audit))
    out = tmp_path / 'reg.json'
    assert pr.cli(['render', '--identity', IDENT, '--revision', REV, '--tree', TREE, '--issued-at', datetime.now(timezone.utc).isoformat(), '--expires-at',
                   (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), '--output', str(out), '--original-audit', str(audit_path)]) == 0
    registration = json.loads(out.read_bytes())
    assert registration['expected_records']['count'] == 5 and registration['expected_records']['source_audit_sha256'] == d.sha(audit_path.read_bytes()) and 'R00' not in out.read_text()
    monkeypatch.setattr(d, 'STATE_ROOT', tmp_path / 'state')
    monkeypatch.setattr(d, '_git', lambda: dict(head=REV, tree=TREE, dirty=False))
    monkeypatch.setattr(d, 'containment', lambda: dict(scope='x'))
    launched = []
    monkeypatch.setattr(runner, 'supervise', lambda command, **kw: launched.append(command) or (0, False))
    args = ['run', '--registration', str(out), '--registration-sha256', d.sha(out.read_bytes()), '--enable-reviewed-source-only-diagnostic']
    assert pr.cli(args) == 1 and launched[0][3] == 'worker' and 'verification.discovery.idox_single_page_probe' in launched[0]
    with pytest.raises(FileExistsError):
        pr.cli(args)      # single use
    monkeypatch.setattr(pr, 'live', lambda cfg, directory, expected: (_ for _ in ()).throw(AssertionError('no request without a fresh claim')))
    with pytest.raises((ValueError, FileNotFoundError)):
        bare = tmp_path / 'bare'
        bare.mkdir(mode=0o700)
        (bare / 'registration.json').write_bytes(out.read_bytes())
        pr.cli(['worker', '--directory', str(bare), '--registration-sha256', d.sha(out.read_bytes())])      # not the parent's fresh claim directory


def test_interruption_is_cancellation_and_leaves_the_claim_consumed(tmp_path, monkeypatch):
    import signal
    import verification.stage26b_l1.actions_runner as runner
    r = reg(issued=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), expires=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    raw = d.canonical(r)
    path = tmp_path / 'reg.json'
    path.write_bytes(raw)
    monkeypatch.setattr(d, 'STATE_ROOT', tmp_path / 'state')
    monkeypatch.setattr(d, '_git', lambda: dict(head=REV, tree=TREE, dirty=False))
    monkeypatch.setattr(d, 'containment', lambda: dict(scope='x'))
    monkeypatch.setattr(runner, 'supervise', lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    previous = signal.getsignal(signal.SIGTERM)
    try:
        with pytest.raises(KeyboardInterrupt):
            pr.cli(['run', '--registration', str(path), '--registration-sha256', d.sha(raw), '--enable-reviewed-source-only-diagnostic'])
    finally:
        signal.signal(signal.SIGTERM, previous)
    assert (tmp_path / 'state' / IDENT).is_dir()
    with pytest.raises(FileExistsError):
        pr.cli(['run', '--registration', str(path), '--registration-sha256', d.sha(raw), '--enable-reviewed-source-only-diagnostic'])


def test_the_probe_reuses_the_reviewed_machinery_rather_than_duplicating_it():
    assert pr.ProbeBoundary.__mro__[1] is cal.CalibrationBoundary and pr.cal.project is cal.project and pr.base._write_private is d._write_private


# ------------------------------------------------------------------------------------------------------------------------- review findings
def test_a_control_that_shows_a_stamped_total_on_a_page_with_rows_is_not_distinct(tmp_path):
    council = Council()
    council.special_original = council.special
    council.special = lambda kind, c=council: Resp(single_page(pager=True, total=5)) if kind == 'http500' else c.special_original(kind)
    # the control (page=0) is clamped to a real results page that carries rows AND a `Showing 1 - 5 of 5` marker
    result = verdict(council, fresh(tmp_path))
    assert result['verdict'] == 'INCONCLUSIVE' and 'CONTROL_NOT_DISTINCT_FROM_THE_SIGNAL' in result['reasons']


def test_historical_application_is_only_ever_applicable_after_an_established_signal_on_an_unchanged_set(tmp_path):
    assert verdict(Council(), fresh(tmp_path))['historical_application'] == 'APPLICABLE'
    for name, council in (('greater', Council(page2='greater')), ('smaller', Council(page2='smaller')), ('missing', Council(page2='missing')), ('repeat', Council(page2='repeat_page1')),
                          ('abort', Council(page1=single_page(['R%03d/26' % (50 - i) for i in range(10)], pager=True, total=14, next_page=2)))):
        out = run(council, fresh(tmp_path, name), seen_expected() if name != 'abort' else None)
        res = pr.classify_probe(out)
        assert res['verdict'] != 'ESTABLISHED' and res['historical_application'] == 'WITHHELD_NO_ESTABLISHED_SIGNAL', (name, res)


def test_a_drifted_set_never_changes_the_verdict_only_the_application(tmp_path):
    drifted = Council(page1=single_page(REFS[:-1] + ['R099/26']), page2='greater')
    result = pr.classify_probe(run(drifted, fresh(tmp_path), seen_expected()))
    assert result['verdict'] == 'UNRECONCILED' and result['historical_application'] == 'WITHHELD_NO_ESTABLISHED_SIGNAL' and result['drift']['identity_extra'] == 1


@pytest.mark.parametrize('mutate', [lambda a: a.update(council='bury'), lambda a: a.update(date_semantics='VALIDATED'), lambda a: a.update(requested_interval=['2026-10-08', '2026-10-14']),
                                    lambda a: a.update(failure='X'), lambda a: a.update(records=[]), lambda a: a['records'].append(dict(a['records'][0])), lambda a: a.pop('records')])
def test_render_refuses_an_audit_that_is_not_the_oldham_received_15_21_october_observation(mutate):
    audit = original_audit()
    mutate(audit)
    with pytest.raises(ValueError, match='ORIGINAL_AUDIT_SCOPE'):
        pr.expected_from_audit(audit, '1' * 64)
    with pytest.raises(ValueError, match='ORIGINAL_AUDIT_SCOPE'):
        pr.expected_from_audit([], '1' * 64)


def test_swapping_metadata_between_identities_is_drift_because_records_are_hashed_jointly(tmp_path):
    base_page = single_page()
    swapped = base_page.replace(b'Thu 15 Oct 2026', b'Fri 16 Oct 2026', 1)      # first record's received date differs: identities unchanged, one record's metadata changed
    out = run(Council(page1=swapped), fresh(tmp_path), seen_expected())
    cmp_ = out['original_comparison']
    assert cmp_['identity_missing'] == 0 and cmp_['identity_extra'] == 0 and cmp_['record_matches'] == 4 and cmp_['metadata_matches'] == 4
    # a pure swap keeps the identity set and the metadata multiset equal, but the joint per-record hashes still differ
    a = original_audit()
    a['records'][0]['fields']['proposal']['value'], a['records'][1]['fields']['proposal']['value'] = 'ALPHA', 'BETA'
    exp = pr.expected_from_audit(a, '1' * 64)
    b = original_audit()
    b['records'][0]['fields']['proposal']['value'], b['records'][1]['fields']['proposal']['value'] = 'BETA', 'ALPHA'
    other = pr.expected_from_audit(b, '1' * 64)
    assert exp['identity_sha256'] == other['identity_sha256'] and exp['metadata_sha256'] == other['metadata_sha256'] and exp['record_sha256'] != other['record_sha256']


def test_page_1_without_unique_identities_or_with_another_page_size_stops_before_page_2(tmp_path):
    duplicated = single_page(['R001/26', 'R001/26', 'R003/26'])
    wrong_size = single_page().replace(b'<option value="10" selected>10</option>', b'<option value="20" selected>20</option>', 1)
    for name, body in (('dup', duplicated), ('size', wrong_size)):
        council = Council(page1=body)
        out = run(council, fresh(tmp_path, name))
        assert (out['abort'] == 'PAGE_1_NOT_RECOGNISED' or out['failure'] is not None) and out['resource']['requests_attempted'] == 3 and not any('searchCriteria.page=' in u for _, u in council.calls), name
        assert pr.classify_probe(out)['verdict'] == 'INCONCLUSIVE'


def test_the_classifier_rechecks_the_request_count_and_page_1_pager_facts(tmp_path):
    out = run(Council(), fresh(tmp_path))
    assert pr.classify_probe(out)['verdict'] == 'ESTABLISHED'
    for mutate, reason in ((lambda a: a['resource'].update(requests_attempted=7), 'ACCOUNTING_DISQUALIFIES'), (lambda a: a['page1'].update(pager_elements=2), 'PAGE_1_NOT_THE_SINGLE_PAGE_SHAPE'),
                           (lambda a: a['page1'].update(next_controls=1), 'PAGE_1_NOT_THE_SINGLE_PAGE_SHAPE'), (lambda a: a['page1'].update(page_size=20), 'PAGE_1_NOT_RECOGNISED_SORTED_AND_UNIQUE')):
        broken = json.loads(json.dumps(out))
        mutate(broken)
        assert reason in pr.classify_probe(broken)['reasons']
