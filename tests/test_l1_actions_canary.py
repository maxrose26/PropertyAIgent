"""Synthetic HTTP expectations, no authoritative/live council truth."""
import json
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode
import pytest
import requests
import yaml
from verification.stage26b_l1.actions_canary import (
    AUTHORITY, BASE, SEARCH, CASES, VERSION, MAX_ARTIFACT, ImportFence,
    OldhamBoundary, FixtureResponse, fixture_dispatch, run, retrieve,
    exact_status_lookup, encode_artifact, offline_network_denial,
)
from verification.stage26b_l1.request_boundary import Budget, BoundaryFailure

SHA = 'a' * 40
ROOT = Path(__file__).resolve().parents[1]


def make(dispatch=None, **limits):
    return OldhamBoundary(CASES[0]['reference'], Budget(**limits),
        dispatch or fixture_dispatch(CASES[0]['reference']))


def test_complete_offline_canary():
    with offline_network_denial(): result = run(sha=SHA)
    assert result['execution_status'] == 'COMPLETE'
    assert result['council_network_requests'] == 0
    assert result['requests_attempted'] == 6
    assert [r['outcome'] for r in result['results']] == ['VERIFIED_MATERIAL_CHANGE', 'VERIFIED_UNCHANGED']
    assert result['results'][0]['status'] == 'refused'
    assert result['results'][0]['decision_date'] == '2026-09-25'
    assert result['results'][1]['decision'] is None
    assert all(r['source_qualification'] == 'MOCKED_EXPECTATION' for r in result['results'])
    encoded = encode_artifact(result)
    assert len(encoded) < MAX_ARTIFACT
    assert encoded == encode_artifact(json.loads(encoded))
    assert result['persistence'] is False


@pytest.mark.parametrize('reference', ['OTHER', 'FUL/355686/26 ', 'FUL/355201/25X'])
def test_exact_reference_allowlist(reference):
    with pytest.raises(ValueError): OldhamBoundary(reference, Budget(), lambda *a, **k: None)


@pytest.mark.parametrize('url', ['https://evil.example/search.do', BASE + '/applicationDetails.do?activeTab=documents&keyVal=X',
    BASE + '/applicationDetails.do?activeTab=relatedCases&keyVal=X', BASE + '/document.pdf', BASE + '/asset.js',
    BASE + '/search.do?searchType=Application&query=all'])
def test_route_domain_document_discovery_asset_denial(url):
    b = make(lambda *a, **k: pytest.fail('Rejected before dispatch'))
    with pytest.raises(BoundaryFailure): b.request('GET', url)
    assert b.requests == 0


@pytest.mark.parametrize('fields', [dict(query='all'), {'searchCriteria.address': 'street'},
    {'searchCriteria.reference': 'OTHER'}, {'_csrf': 'bad!'}, {'searchCriteria.reference': ['FUL/355686/26', 'OTHER']}])
def test_form_no_search_expansion(fields):
    body = {'searchCriteria.reference': CASES[0]['reference'], **fields}
    b = make(lambda *a, **k: pytest.fail('Rejected form'))
    with pytest.raises(BoundaryFailure):
        b.request('POST', BASE + '/advancedSearchResults.do?action=firstPage', body=urlencode(body, doseq=True).encode())


def test_actual_form_nonce_and_empty_criteria_only():
    b = make(lambda *a, **k: FixtureResponse('ok'))
    b.request('POST', BASE + '/advancedSearchResults.do?action=firstPage',
        body=urlencode({'searchCriteria.reference': CASES[0]['reference'], '_csrf': 'publicNonce', 'searchCriteria.address': ''}).encode())
    assert b.requests == 1


def dispatch_pages(*pages):
    iterator = iter(FixtureResponse(p) for p in pages)
    return lambda *a, **k: next(iterator)


FORM = '<form method="post" action="advancedSearchResults.do?action=firstPage"><input name="searchCriteria.reference"></form>'


@pytest.mark.parametrize('results,outcome', [('', 'PARTIAL_RETRIEVAL'),
    ('<a href="applicationDetails.do?keyVal=A">one</a><a href="applicationDetails.do?keyVal=B">two</a>', 'AMBIGUOUS_SOURCE_RESULT')])
def test_zero_and_ambiguous_matches(results, outcome):
    with pytest.raises(BoundaryFailure) as exc: exact_status_lookup(make(dispatch_pages(FORM, results)))
    assert exc.value.outcome == outcome


def test_duplicate_status_label_is_ambiguous():
    links = '<a href="applicationDetails.do?keyVal=A">one</a>'
    page = '<table><tr><th>Status</th><td>Pending</td></tr><tr><th>Status</th><td>Refused</td></tr></table>'
    with pytest.raises(BoundaryFailure) as exc: exact_status_lookup(make(dispatch_pages(FORM, links, page)))
    assert exc.value.outcome == 'AMBIGUOUS_SOURCE_RESULT'


def test_single_key_on_paginated_search_not_certified_unique():
    page = '<a href="applicationDetails.do?keyVal=A">one</a><a href="advancedSearchResults.do?action=nextPage">Next</a>'
    b = make(dispatch_pages(FORM, page))
    with pytest.raises(BoundaryFailure) as exc: exact_status_lookup(b)
    assert exc.value.outcome == 'PARTIAL_RETRIEVAL'
    assert b.requests == 2


def test_wrong_detail_reference_stops_whole_run():
    def factory(reference):
        if reference != CASES[0]['reference']:
            return lambda *a, **k: pytest.fail('No dispatch after parser/identity failure')
        return dispatch_pages(FORM, '<a href="applicationDetails.do?keyVal=A">one</a>',
            '<table><tr><th>Reference</th><td>OTHER</td></tr><tr><th>Status</th><td>Pending</td></tr></table>')
    result = run(sha=SHA, dispatch_factory=factory)
    assert result['execution_status'] == 'FAIL'
    assert result['results'][0]['outcome'] == 'AMBIGUOUS_SOURCE_RESULT'
    assert result['results'][1]['requests_attempted'] == 0
    assert result['results'][1]['attempted'] is False


@pytest.mark.parametrize('status,decision,date,expected', [('Decided', 'Granted', 'Fri 25 Sep 2026', 'VERIFIED_MATERIAL_CHANGE'),
    ('Withdrawn', 'Withdrawn', '', 'VERIFIED_MATERIAL_CHANGE'), ('Awaiting decision', 'Refused', 'Fri 25 Sep 2026', 'AMBIGUOUS_SOURCE_RESULT'),
    ('Decided', 'Refused', 'malformed', 'PARSER_FAILURE')])
def test_terminal_and_conflicting_summary(status, decision, date, expected):
    result = run(sha=SHA, dispatch_factory=lambda ref: fixture_dispatch(ref, status=status, decision=decision, date=date))
    assert result['results'][0]['outcome'] == expected
    if not expected.startswith('VERIFIED_'): assert result['results'][1]['requests_attempted'] == 0


def test_total_request_accounting_ceiling():
    budget = Budget()
    first = OldhamBoundary(CASES[0]['reference'], budget, lambda *a, **k: FixtureResponse('x'))
    second = OldhamBoundary(CASES[1]['reference'], budget, lambda *a, **k: FixtureResponse('x'))
    for b in (first, second):
        for _ in range(10): b.request('GET', SEARCH)
    with pytest.raises(BoundaryFailure): second.request('GET', SEARCH)
    assert first.requests + second.requests == 20


def test_existing_generic_idox_functions_unchanged():
    import ast
    source = 'app/scrapers/idox_portal.py'
    before = subprocess.check_output(['git', 'show', '27966c34d1b4dbb88c15cd59d0805d55b14af9a7:' + source], cwd=ROOT, text=True)
    old = {n.name: ast.dump(n) for n in ast.parse(before).body if isinstance(n, ast.FunctionDef)}
    new = {n.name: ast.dump(n) for n in ast.parse((ROOT / source).read_text()).body if isinstance(n, ast.FunctionDef)}
    assert all(new[name] == value for name, value in old.items())


def test_redirects_accounted():
    responses = iter([FixtureResponse('', 302, {'Location': BASE + '/advancedSearchResults.do?action=firstPage'}), FixtureResponse('ok')])
    b = make(lambda *a, **k: next(responses))
    retrieve(b, 'GET', SEARCH)
    assert b.requests == 2 and b.redirects == 1


def test_external_redirect_rejected_without_second_request():
    b = make(lambda *a, **k: FixtureResponse('', 302, {'Location': 'https://evil.example/'}))
    with pytest.raises(BoundaryFailure): retrieve(b, 'GET', SEARCH)
    assert b.requests == 1


@pytest.mark.parametrize('error,outcome,count', [(requests.Timeout(), 'TIMEOUT', 2),
    (requests.ConnectionError(), 'SOURCE_UNAVAILABLE', 2), (None, 'RATE_LIMITED', 1)])
def test_failure_retry_and_rate_limits(error, outcome, count):
    def dispatch(*a, **k):
        if error: raise error
        return FixtureResponse('rate limited', 429)
    result = run(sha=SHA, dispatch_factory=lambda _: dispatch)
    assert result['execution_status'] == 'FAIL'
    assert result['results'][0]['outcome'] == outcome
    assert result['results'][0]['requests_attempted'] == count
    assert result['results'][0]['retries'] <= 1
    assert all(not r['outcome'].startswith('VERIFIED_') for r in result['results'])


@pytest.mark.parametrize('limits', [dict(response_bytes=10), dict(total_bytes=10), dict(per_reference=1)])
def test_overflow_fail_closed(limits):
    b = make(**limits)
    with pytest.raises(BoundaryFailure): exact_status_lookup(b)
    assert b.budget.failure.budget


def test_artifact_overflow_rejected():
    with pytest.raises(BoundaryFailure): encode_artifact({'extra': 'x' * MAX_ARTIFACT})


@pytest.mark.parametrize('defect', ['failure_complete', 'repository', 'workflow', 'adapter', 'council', 'counter', 'private_field', 'bytes'])
def test_malformed_worker_artifact_rejected(defect):
    from verification.stage26b_l1.actions_runner import validate_worker_artifact
    result = run(sha=SHA)
    validate_worker_artifact(result, sha=SHA, mode='offline', status=0)
    if defect == 'failure_complete': result['results'][0]['outcome'] = 'PARSER_FAILURE'
    elif defect == 'repository': result['repository'] = 'other/repo'
    elif defect == 'workflow': result['workflow_version'] = 'unknown'
    elif defect == 'adapter': result['results'][0]['adapter'] = 'arcus'
    elif defect == 'council': result['results'][0]['council'] = 'other'
    elif defect == 'counter': result['results'][0]['requests_attempted'] = 11
    elif defect == 'private_field': result['results'][0]['html'] = 'private text'
    elif defect == 'bytes': result['received_bytes'] += 1
    with pytest.raises((ValueError, TypeError)): validate_worker_artifact(result, sha=SHA, mode='offline', status=0)


def test_offline_socket_and_requests_denied():
    with offline_network_denial():
        for action in (lambda: socket.getaddrinfo('planningpa.oldham.gov.uk', 443),
                       lambda: requests.get(SEARCH)):
            with pytest.raises(BoundaryFailure): action()


@pytest.mark.parametrize('name', ['app.db.session', 'app.pipeline.run_weekly', 'openai', 'supabase', 'psycopg'])
def test_database_model_connectivity_import_denial(name):
    with pytest.raises(BoundaryFailure): ImportFence().find_spec(name)


def test_fresh_process_no_database_connectivity_import():
    code = "from verification.stage26b_l1.actions_canary import run,offline_network_denial; import sys; "
    code += "\nwith offline_network_denial(): result=run(sha='" + SHA + "')\n"
    code += "assert result['execution_status']=='COMPLETE'; assert not any(n.startswith(('app.db.session','openai','psycopg','supabase')) for n in sys.modules)"
    subprocess.run([sys.executable, '-c', code], cwd=ROOT, check=True, timeout=15)


def test_manual_workflow_security_contract():
    text = (ROOT / '.github/workflows/l1-oldham-canary.yml').read_text()
    workflow = yaml.safe_load(text)
    triggers = workflow.get('on', workflow.get(True))
    assert set(triggers) == {'workflow_dispatch'}
    assert workflow['permissions'] == {'contents': 'read'}
    job = workflow['jobs']['canary']
    assert job['runs-on'] == 'ubuntu-24.04' and job['timeout-minutes'] == 3
    assert 'secrets.' not in text and 'environment:' not in text and 'DATABASE_URL' not in text
    assert 'github.workflow_sha' in text and 'persist-credentials: false' in text
    assert 'ref: ${{ inputs.reviewed_sha }}' in text
    assert 'env -i' in text and 'mode' in text and 'OFFLINE_ONLY' in text


def test_supervisor_rejects_non_disposable_runtime(tmp_path):
    from verification.stage26b_l1.actions_runner import execute
    with pytest.raises(ValueError): execute(sha=SHA, mode='offline', authority='OFFLINE_ONLY', output=tmp_path / 'audit.json')


def test_independent_supervisor_deadline_native():
    from verification.stage26b_l1.actions_runner import supervise
    status, triggered = supervise([sys.executable, '-c', 'import time; time.sleep(30)'],
        env={'PATH': '/usr/bin:/bin'}, deadline=0.15)
    assert status == 124 and triggered


def test_normal_worker_native():
    from verification.stage26b_l1.actions_runner import supervise
    status, triggered = supervise([sys.executable, '-c', 'pass'], env={'PATH': '/usr/bin:/bin'}, deadline=5)
    assert status == 0 and not triggered
