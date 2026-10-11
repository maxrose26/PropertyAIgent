"""Synthetic form/transport expectations. No council truth or network access."""
import copy
import inspect
import json
import os
from pathlib import Path
import sys
import time
import pytest
import yaml
from verification.stage26b_l1 import form_metadata as m
from verification.stage26b_l1 import form_metadata_runner as runner
from verification.stage26b_l1.form_metadata_fixture import BODY, Response

SHA = 'a' * 40


def result(body=BODY, status=200):
    return m.run(SHA, dispatch=lambda *a, **k: Response(body, status))


def test_realistic_fixture_privacy_and_complete_selection():
    r = result()
    runner.validate(r, sha=SHA, mode='offline', status=0)
    assert r['request_count'] == 1 and r['council_network_requests'] == 0
    assert r['form']['form_count'] == 2 and r['form']['selected_form_ordinal'] == 1
    assert r['form']['classification_is_approval'] is False
    assert len(r['form']['fields']) == 19
    encoded = m.encode(r)
    for secret in (b'SECRET', b'PRIVATE', b'HIDDEN_SECRET_MARKER', b'TOKEN_VALUE', b'x7_f7ac', b'oversized_identifier', b'<html', b'OPTION_SECRET'):
        assert secret not in encoded
    assert len(encoded) <= m.MAX_ARTIFACT
    rows = r['form']['fields']
    assert rows[0]['classification_candidate'] == 'REQUIRED_SERVER_STATE'
    assert rows[1]['classification_candidate'] == 'APPROVED_REFERENCE_INPUT'
    assert rows[2]['classification_candidate'] == 'PROHIBITED_SEARCH_EXPANSION'
    assert rows[7]['populated'] is False
    assert rows[8]['selected_ordinals'] == [0] and rows[8]['option_count'] == 2
    assert rows[9]['checked'] is True and rows[10]['checked'] is False
    assert rows[12]['disabled'] is True
    assert rows[13]['duplicate_name'] and rows[14]['duplicate_name']
    assert rows[15]['identifier_redacted'] and rows[16]['identifier_redacted']


@pytest.mark.parametrize('method,url', [('POST', m.URL), ('GET', m.URL+'&reference=FUL/355686/26'), ('GET', 'https://example.com/'), ('GET', m.URL.replace('search.do', 'applicationDetails.do'))])
def test_mechanical_request_admission(method, url):
    calls = []
    transport = m.OneGet(lambda *a, **k: calls.append(a))
    with pytest.raises(m.Failure, match='REQUEST_DENIED'): transport.request(method, url)
    assert calls == [] and transport.requests == 0


def test_second_request_rejected_no_follow_assets_or_links():
    calls = []
    body = BODY + b'<script src="https://evil.test/script"></script><img src="/asset"><a href="/results">go</a><iframe src="/doc"></iframe>'
    response = Response(body)
    def dispatch(*a, **k):
        calls.append((a, k)); return response
    transport = m.OneGet(dispatch)
    _, captured = transport.request('GET', m.URL)
    m.parse_form(captured)
    with pytest.raises(m.Failure): transport.request('GET', m.URL)
    assert len(calls) == 1 and response.closed
    assert calls[0][1] == dict(allow_redirects=False, stream=True, timeout=15)


@pytest.mark.parametrize('status,reason', [(301,'REDIRECT_DENIED'), (302,'REDIRECT_DENIED'), (307,'REDIRECT_DENIED'), (429,'HTTP_UNAVAILABLE'), (503,'HTTP_UNAVAILABLE')])
def test_redirect_and_http_failure_no_retry(status, reason):
    calls = []
    response = Response(status=status)
    r = m.run(SHA, dispatch=lambda *a, **k: (calls.append(a) or response))
    assert r['failure_category'] == reason and r['http_status'] == status
    assert len(calls) == 1 and response.closed and r['form'] is None
    runner.validate(r, sha=SHA, mode='offline', status=1)


def test_timeout_no_retry_no_exception_leak():
    calls = []
    def dispatch(*a, **k): calls.append(a); raise TimeoutError('SECRET_TOKEN')
    r = m.run(SHA, dispatch=dispatch)
    assert len(calls) == 1 and r['execution_status'] == 'FAIL'
    assert b'SECRET_TOKEN' not in m.encode(r)


def test_body_limit_counts_actual_not_content_length():
    response = Response(b'x' * (m.MAX_BODY + 1))
    r = m.run(SHA, dispatch=lambda *a, **k: response)
    assert r['failure_category'] == 'BODY_OVERFLOW' and r['received_bytes'] > m.MAX_BODY
    assert response.closed and r['form'] is None


def test_encoded_and_decoded_measure_uses_larger():
    class Wire:
        def tell(self): return m.MAX_BODY + 1
    response = Response(); response.raw = Wire()
    r = m.run(SHA, dispatch=lambda *a, **k: response)
    assert r['failure_category'] == 'BODY_OVERFLOW' and response.closed


@pytest.mark.parametrize('body', [b'<html>malformed', BODY+BODY, b'<form><input name="other"></form>', b'\xff'])
def test_unselectable_or_malformed_fails_without_output(body):
    r = result(body)
    assert r['execution_status'] == 'FAIL' and r['form'] is None


@pytest.mark.parametrize('method,action,expected', [('DELETE','https://evil.test/SECRET', None), ('post','/online-applications/search.do', '/online-applications/search.do'), ('get','/documents?token=SECRET', None)])
def test_unexpected_form_shapes_observed_never_followed(method, action, expected):
    body = f'<form method="{method}" action="{action}"><input name="searchCriteria.reference"></form>'.encode()
    r = result(body)
    assert r['form']['form_action_path'] == expected
    assert b'SECRET' not in m.encode(r)
    assert r['request_count'] == 1


@pytest.mark.parametrize('name', ['token_34bd447f113142a11ddbe99ff940020d', 'a'*1000, 'a@secret.test', 'unsafe[password]', '', 'unrecognisedField'])
def test_identifier_safety(name):
    body = f'<form><input name="searchCriteria.reference"><input name="{name}" value="CREDENTIAL_SECRET"></form>'.encode()
    r = result(body)
    row = r['form']['fields'][1]
    assert row['identifier'] is None and row['identifier_redacted'] is bool(name)
    assert b'CREDENTIAL_SECRET' not in m.encode(r)
    if name: assert name.encode() not in m.encode(r)


@pytest.mark.parametrize('name', ['searchCriteria.applicant','searchCriteria.address','searchCriteria.postcode','searchCriteria.keyword','searchCriteria.dateFrom','searchCriteria.dateTo'])
def test_expansion_classification_not_approval(name):
    category, _ = m.classification(name, 'PRIVATE')
    assert category == 'PROHIBITED_SEARCH_EXPANSION'


def test_schema_rejects_arbitrary_value_or_cookie():
    r = result()
    for key in ('value', 'cookie', 'html', 'csrf'):
        bad = copy.deepcopy(r); bad['form']['fields'][0][key] = 'SECRET'
        with pytest.raises(ValueError): runner.validate(bad, sha=SHA, mode='offline', status=0)
    bad = copy.deepcopy(r); bad['form']['fields'][0]['identifier'] = 'SECRET'
    with pytest.raises(ValueError): runner.validate(bad, sha=SHA, mode='offline', status=0)


def test_field_and_artifact_overflow_fail_closed():
    body = b'<form><input name="searchCriteria.reference">'+b'<input name="searchCriteria.address">'*80+b'</form>'
    assert result(body)['failure_category'] == 'FIELD_OVERFLOW'
    with pytest.raises(m.Failure, match='ARTIFACT_OVERFLOW'): m.encode({'x':'x'*m.MAX_ARTIFACT})


def test_offline_network_and_model_denial():
    import requests
    with m.offline_network_denial():
        with pytest.raises(Exception): requests.get(m.URL)
        assert m.run(SHA)['execution_status'] == 'COMPLETE'
    fence = m.ImportFence()
    for module in ('openai', 'anthropic', 'app.db.session', 'supabase', 'psycopg'):
        with pytest.raises(Exception): fence.find_spec(module, None)


def test_workflow_manual_distinct_fixed_scope():
    path = Path('.github/workflows/oldham-form-metadata.yml')
    text = path.read_text(); workflow = yaml.safe_load(text)
    triggers = workflow.get('on', workflow.get(True))
    assert set(triggers) == {'workflow_dispatch'}
    assert workflow['permissions'] == {'contents':'read'}
    job = workflow['jobs']['diagnostic']
    assert job['runs-on'] == 'ubuntu-24.04' and job['timeout-minutes'] == 3
    assert 'secrets.' not in text and 'environment:' not in text
    assert 'persist-credentials: false' in text and 'github.workflow_sha' in text
    assert set(triggers['workflow_dispatch']['inputs']) == {'reviewed_sha','mode','authority'}
    assert m.AUTHORITY in text and 'FAILSWORTH' not in text and 'SOUTHLINK' not in text
    assert '--deadline 30' in text


def test_no_submission_or_database_call_graph():
    source = inspect.getsource(m)
    assert 'session.post' not in source and 'requests.post' not in source
    assert 'DATABASE_URL' not in source and 'applicationDetails' not in source
    assert 'allow_redirects=False' in source and 'max_retries=0' in source and 'trust_env = False' in source
    assert 'BeautifulSoup' in source and 'playwright' not in source


def test_independent_hung_worker_deadline():
    start = time.monotonic()
    status, timed_out = runner.supervise([sys.executable,'-c','import time; time.sleep(60)'], env=dict(PATH='/usr/bin:/bin'), deadline=0.1)
    assert status == 124 and timed_out and time.monotonic()-start < 4


def test_interrupted_counts_unknown_not_zero():
    r = runner.interrupted(SHA, 'live', 'INDEPENDENT_DEADLINE')
    runner.validate(r, sha=SHA, mode='live', status=124)
    assert r['accounting_complete'] is False and r['request_count'] is None


@pytest.mark.parametrize('scenario', ['success', 'timeout', 'malformed', 'overflow'])
def test_supervisor_scrubs_environment_validates_artifact_cleans_temp(monkeypatch, tmp_path, scenario):
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setenv('RUNNER_ENVIRONMENT', 'github-hosted')
    monkeypatch.setenv('PRODUCTION_SECRET_SENTINEL', 'DO_NOT_INHERIT')
    monkeypatch.setattr(runner.subprocess, 'check_output', lambda args, **k: SHA+'\n' if args[1]=='rev-parse' else '')
    paths = []
    def supervise(command, *, env, deadline):
        assert deadline <= 30 and 'PRODUCTION_SECRET_SENTINEL' not in env
        assert set(env) == {'PATH','HOME','TMPDIR','LANG','PYTHONNOUSERSITE','PYTHONDONTWRITEBYTECODE'}
        artifact = Path(command[-1]); paths.append(artifact.parent)
        if scenario == 'timeout': return 124, True
        if scenario == 'success': artifact.write_bytes(m.encode(result()))
        elif scenario == 'malformed': artifact.write_text('{"cookie":"SECRET"}')
        else: artifact.write_bytes(b'x'*(m.MAX_ARTIFACT+1))
        return 0, False
    monkeypatch.setattr(runner, 'supervise', supervise)
    output = tmp_path/'metadata.json'
    code = runner.execute(sha=SHA,mode='offline',authority='OFFLINE_ONLY',output=output)
    assert code == (0 if scenario == 'success' else 1)
    assert all(not p.exists() for p in paths)
    assert len(output.read_bytes())<=m.MAX_ARTIFACT and b'SECRET' not in output.read_bytes()


def test_select_default_and_multiple_ordinals_no_values():
    body = b'<form><input name="searchCriteria.reference"><select name="searchCriteria.status"><option value="SECRET_FIRST">X</option></select><select multiple name="searchCriteria.ward"><option value="SECRET_SECOND" selected>Y</option><option value="SECRET_THIRD" selected>Z</option></select></form>'
    r = result(body); rows=r['form']['fields']
    assert rows[1]['selected_ordinals']==[0] and rows[2]['selected_ordinals']==[0,1]
    assert rows[2]['multiple'] is True and b'SECRET' not in m.encode(r)


def test_live_transport_configuration_using_fake_session_only(monkeypatch):
    calls = []; session_closed=[]
    class Session:
        def __init__(self): self.trust_env=True
        def mount(self, origin, adapter):
            assert origin=='https://' and adapter.max_retries.total==0
        def request(self, method,url,**kwargs):
            assert self.trust_env is False
            calls.append((method,url,kwargs)); return Response()
        def close(self): session_closed.append(True)
    monkeypatch.setattr(m.requests,'Session',Session)
    r=m.run(SHA,mode='live')
    assert len(calls)==1 and r['council_network_requests']==1 and session_closed==[True]
    assert calls[0][0]=='GET' and calls[0][1]==m.URL and calls[0][2]['allow_redirects'] is False


def test_missing_distinct_live_authority_rejected_before_worker(monkeypatch,tmp_path):
    monkeypatch.setenv('GITHUB_ACTIONS','true');monkeypatch.setenv('RUNNER_ENVIRONMENT','github-hosted')
    monkeypatch.setattr(runner.subprocess,'check_output',lambda args,**k:SHA+'\n' if args[1]=='rev-parse' else '')
    with pytest.raises(ValueError,match='distinct live authority'):
        runner.execute(sha=SHA,mode='live',authority='AUTHORISE_FAILSWORTH_SOUTHLINK_ONLY',output=tmp_path/'a.json')


@pytest.mark.parametrize('deadline', [0,31,180])
def test_deadline_cannot_expand(tmp_path, deadline):
    with pytest.raises(ValueError): runner.execute(sha=SHA,mode='offline',authority='OFFLINE_ONLY',output=tmp_path/'a.json',deadline=deadline)
