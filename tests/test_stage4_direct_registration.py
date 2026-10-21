"""Offline-only registration tests. Synthetic fixtures are not live evidence."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
import requests
import yaml

from verification.direct_reference import registration as r
from verification.direct_reference.fixtures import Session,summary
from verification.direct_reference.refresh import load_manifest
from verification.stage26b_l1.request_boundary import BoundaryFailure


def good(application_id=78,**kwargs):
    case=r.cohort()[r.IDS.index(application_id)]
    return r.observe(application_id,lambda:Session(summary(case['reference'],**kwargs)))


def test_exact_cohort_and_shared_bytes():
    assert r.IDS==(202,42,78)
    assert [x['council'] for x in r.cohort()]==['bolton','oldham','stockport']
    root=Path('verification/direct_reference')
    accepted=Path('../PropertyAIgent-stage4-direct/verification/direct_reference')
    # Immutable accepted blob digests, independent of that local checkout.
    expected=json.loads((root/'accepted-dependencies.json').read_text())
    for path,digest in expected.items():
        if path=='verification/direct_reference/refresh.py':
            # Keep the consumed accepted dependency immutable. Only the exact
            # reviewed optional-diagnostic revision is a current-code exception.
            assert digest=='914445cc890ac3d7882f969399d0867f098229631b1abb468d08a409c476ebc9'
            archive=root/'history/refresh-pre-diagnostics.py.txt'
            assert hashlib.sha256(archive.read_bytes()).hexdigest()==digest
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest()=='e59301682bdb78ac2838db40214af583299596648d77b1cab0801267f5fc88d2'
        elif path=='verification/stage26b_l1/request_boundary.py':
            # The accepted/consumed boundary bytes remain immutable. Only this
            # exact opt-in retry-policy successor may differ in the current tree.
            assert digest=='ad243bd5148a90147fa5f04047e316355909cabf263d53d0f1827a6ba0660c76'
            assert hashlib.sha256((root/'history/request-boundary-pre-no-retry.py.txt').read_bytes()).hexdigest()==digest
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest()=='188198827c2192dec97f75a373fa3f3bbd066cd5f245ebad43e576a7b6e90057'
        else:
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
    assert len(load_manifest())==202
    # The authorised status-scope evolution never replaces historical evidence.
    historical=json.loads((root/'accepted-dependencies-v1.json').read_text())
    assert set(historical)==set(expected)
    for path,digest in historical.items():
        source=(root/'history/refresh-v1.py.txt' if path=='verification/direct_reference/refresh.py'
                else root/'history/models-v1.py.txt' if path=='app/db/models.py'
                else root/'history/idox-v1.py.txt' if path=='app/scrapers/idox_portal.py'
                else root/'history/unit-filter-v1.py.txt' if path=='app/scrapers/unit_filter.py'
                else root/'history/request-boundary-pre-no-retry.py.txt' if path=='verification/stage26b_l1/request_boundary.py' else Path(path))
        assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    provenance=json.loads((root/'history/provenance.json').read_text())
    assert provenance['original_live_sha']=='a0feeb7c1cd39c979e2a9018b82d764d1edcd76b'
    assert provenance['immutable_refresh_sha256']==historical['verification/direct_reference/refresh.py']


@pytest.mark.parametrize('application_id',r.IDS)
def test_shared_success_identity_accounting_cleanup(application_id):
    a=good(application_id,status='Decided',decision='Granted',date='Wed 27 Dec 2023')
    assert a['outcome']=='LITERAL_VERIFIED'
    assert a['identity_qualification']=='EXACT_DISPLAYED_REFERENCE'
    assert a['cleanup_state']=='CLOSED'
    assert a['requests']==1 and a['retries']==a['redirects']==0
    assert a['received_body_bytes']>0
    r.validate_row(a,application_id)


def test_deposited_omitted_fields_literal_only():
    a=good(202,status='Deposited',omit=('Decision','Decision Issued Date'))
    assert a['outcome']=='LITERAL_VERIFIED'
    assert a['semantic_qualification']=='UNKNOWN_UNMAPPED'
    assert a['field_states']['decision']=='NOT_PRESENT'
    assert 'Decision' not in a['literal_facts']
    assert a['normalized_facts']['Decision'] is None


@pytest.mark.parametrize('status,outcome,requests_count',[(429,'RATE_LIMITED',1),(403,'SOURCE_UNAVAILABLE',1),(404,'SOURCE_UNAVAILABLE',1),(503,'SOURCE_UNAVAILABLE',2),(302,'REDIRECT_VIOLATION',1)])
def test_http_failures(status,outcome,requests_count):
    session=Session(b'private body',status=status)
    a=r.observe(202,lambda:session)
    assert a['outcome']==outcome and a['requests']==requests_count
    assert a['received_body_bytes']==0 and a['literal_facts'] is None
    assert session.closed and all(x.closed for x in session.responses)


@pytest.mark.parametrize('error,outcome',[(requests.Timeout('secret'),'TIMEOUT'),(requests.ConnectionError('private'),'SOURCE_UNAVAILABLE')])
def test_transport_failure(error,outcome):
    a=r.observe(202,lambda:Session(error))
    assert a['outcome']==outcome and a['requests']==2 and a['retries']==1
    assert 'secret' not in json.dumps(a) and 'private' not in json.dumps(a)


@pytest.mark.parametrize('body,outcome',[
 (summary('WRONG'),'AMBIGUOUS_SOURCE_RESULT'),
 (b'<html>incomplete','PARTIAL_RETRIEVAL'),
 (summary('00307/26').replace(b'</table>',b'<tr><th>Status</th><td>Refused</td></tr></table>'),'AMBIGUOUS_SOURCE_RESULT'),
 (b'x'*1_000_001,'PARTIAL_RETRIEVAL')])
def test_identity_conflict_partial_bounds(body,outcome):
    a=r.observe(202,lambda:Session(body))
    assert a['outcome']==outcome and a['literal_facts'] is None
    assert a['cleanup_state']=='CLOSED'
    if len(body)>1_000_000:assert a['budget_state']=='EXHAUSTED'


def test_scope_wrapper_denies_substitution():
    session=Session(b'')
    meter=r.MeteredSession(r.cohort()[0],session)
    with pytest.raises(BoundaryFailure):meter.get('https://example.org',allow_redirects=False)
    assert meter.requests==0 and not session.calls


def test_cleanup_failure_never_success():
    class Broken(Session):
        def close(self):raise RuntimeError('private failure')
    a=r.observe(202,lambda:Broken(summary('00307/26')))
    assert a['outcome']=='CLEANUP_FAILURE' and a['literal_facts'] is None


def test_field_and_audit_privacy():
    a=r.observe(202,lambda:Session(summary('00307/26').replace(b'</body>',b'<p>applicant secret@address.com</p></body>')))
    assert a['outcome']=='LITERAL_VERIFIED'
    assert b'secret' not in r.encode(a)
    for key in ('cookies','headers','proposal','token','raw_html'):
        bad=copy.deepcopy(a);bad[key]='x'
        with pytest.raises(ValueError):r.validate_row(bad,202)
    bad=copy.deepcopy(a);bad['literal_facts']['Proposal']='secret'
    with pytest.raises(ValueError):r.validate_row(bad,202)
    bad=copy.deepcopy(a);bad['requests']=0
    with pytest.raises(ValueError):r.validate_row(bad,202)


def test_interrupt_unknown_and_stop():
    rows=[r.empty_row(202,'INTERRUPTED'),r.empty_row(42),r.empty_row(78)]
    a=r.aggregate('a'*40,'offline',rows)
    assert a['totals']['requests']=='UNKNOWN' and not a['accounting_complete']
    assert a['assessment']=='STOPPED_REVIEW_REQUIRED'
    rows[1]=good(42)
    with pytest.raises(ValueError):r.aggregate('a'*40,'offline',rows)
    bad=r.empty_row(202,'INTERRUPTED');bad['requests']=0
    with pytest.raises(ValueError):r.validate_row(bad,202)


def live_env():
    return dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_EVENT_NAME='workflow_dispatch',
      DIRECT_WORKFLOW_SHA='a'*40,GITHUB_RUN_ATTEMPT='1',GITHUB_RUN_NUMBER='1',
      GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_RUN_ID='123',
      GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+r.WORKFLOW+'@refs/heads/master')


@pytest.mark.parametrize('key,value',[(k,v) for k,v in [
 ('GITHUB_RUN_ATTEMPT','2'),('GITHUB_RUN_NUMBER','2'),('GITHUB_EVENT_NAME','pull_request'),
 ('RUNNER_ENVIRONMENT','self-hosted'),('DIRECT_WORKFLOW_SHA','b'*40),('GITHUB_RUN_ID',''),
 ('GITHUB_WORKFLOW_REF','wrong'),('GITHUB_REPOSITORY','other/repo')]])
def test_live_admission_failures(monkeypatch,key,value):
    monkeypatch.setattr(subprocess,'check_output',lambda cmd,**kw:'a'*40 if cmd[1]=='rev-parse' else '')
    env=live_env();r.admit('a'*40,'live',r.AUTHORITY,env)
    env[key]=value
    with pytest.raises(ValueError):r.admit('a'*40,'live',r.AUTHORITY,env)


def test_clean_head_and_authority(monkeypatch):
    monkeypatch.setattr(subprocess,'check_output',lambda cmd,**kw:'a'*40 if cmd[1]=='rev-parse' else '')
    with pytest.raises(ValueError):r.admit('b'*40,'live',r.AUTHORITY,live_env())
    with pytest.raises(ValueError):r.admit('a'*40,'live','NOT_AUTHORISED',live_env())
    monkeypatch.setattr(subprocess,'check_output',lambda cmd,**kw:'a'*40 if cmd[1]=='rev-parse' else ' M file')
    with pytest.raises(ValueError):r.admit('a'*40,'offline','OFFLINE_ONLY')


def test_persistence_fence():
    fence=r.AuditFence()
    for module in ('app.pipeline.status_verification','app.pipeline.run_weekly','app.db.session','app.settings','openai','psycopg','supabase'):
        with pytest.raises(BoundaryFailure):fence.find_spec(module)
    source=Path('verification/direct_reference/registration.py').read_text()
    assert 'verify_application_status(' not in source and '.refresh(' not in source


def test_live_workflow_closed_manual_contract():
    text=Path(r.WORKFLOW).read_text();doc=yaml.safe_load(text)
    triggers=doc.get('on',doc.get(True))
    assert set(triggers)=={'workflow_dispatch'}
    assert set(triggers['workflow_dispatch']['inputs'])=={'reviewed_sha','authority'}
    assert doc['permissions']=={'contents':'read'}
    job=doc['jobs']['audit']
    assert job['runs-on']=='ubuntu-24.04' and job['timeout-minutes']==3
    assert doc['concurrency']['cancel-in-progress'] is False
    checkout=next(x for x in job['steps'] if x.get('uses','').startswith('actions/checkout'))
    assert checkout['with']['persist-credentials'] is False
    assert 'secrets.' not in text and 'DATABASE_URL' not in text and 'workflow_dispatch:' in text
    assert '"$RUN_NUMBER" == 1' in text and '"$RUN_ATTEMPT" == 1' in text
    assert 'env -i ' in text


def test_execute_stops_after_failure_and_strips_environment(monkeypatch,tmp_path):
    monkeypatch.setattr(r,'admit',lambda *a:None)
    calls=[]
    def supervisor(command,env,deadline):
        calls.append((command,env,deadline))
        out=Path(command[command.index('--output')+1])
        row=r.observe(202,lambda:Session(b'',status=403))
        out.write_bytes(r.encode(row));return 1,False
    monkeypatch.setattr(r,'supervise',supervisor)
    monkeypatch.setenv('DATABASE_URL','private');monkeypatch.setenv('OPENAI_API_KEY','private')
    output=tmp_path/'out.json'
    assert r.execute('a'*40,'offline','OFFLINE_ONLY',output)==1
    assert len(calls)==1 and calls[0][2]==45
    assert not {'DATABASE_URL','OPENAI_API_KEY'} & calls[0][1].keys()
    audit=json.loads(output.read_text())
    assert [x['outcome'] for x in audit['results']]==['SOURCE_UNAVAILABLE','NOT_ATTEMPTED','NOT_ATTEMPTED']


def test_supervisor_interrupt_and_no_later_reference(monkeypatch,tmp_path):
    monkeypatch.setattr(r,'admit',lambda *a:None)
    monkeypatch.setattr(r,'supervise',lambda *a,**kw:(124,True))
    output=tmp_path/'out.json'
    assert r.execute('a'*40,'offline','OFFLINE_ONLY',output)==1
    assert json.loads(output.read_text())['totals']['requests']=='UNKNOWN'


def test_old_setup_refused_before_worker(monkeypatch,tmp_path):
    monkeypatch.setattr(r,'admit',lambda *a:None)
    monkeypatch.setattr(r.time,'time',lambda:200)
    with pytest.raises(ValueError):r.execute('a'*40,'live',r.AUTHORITY,tmp_path/'out',job_start_epoch=0)


def test_unreviewed_refresh_mutation_does_not_use_diagnostic_exception(monkeypatch):
    original=Path.read_bytes
    def altered(path):
        raw=original(path)
        return raw+b'\n# unreviewed mutation\n' if str(path)=='verification/direct_reference/refresh.py' else raw
    monkeypatch.setattr(Path,'read_bytes',altered)
    with pytest.raises(AssertionError):test_exact_cohort_and_shared_bytes()
