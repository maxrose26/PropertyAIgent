"""Synthetic/offline narrow bindings and actual shared handoff; never live evidence."""
import json,time
from pathlib import Path
from unittest.mock import patch
import pytest,yaml
from sqlalchemy.orm import Session
from app.db.models import Council,Application
from tests.test_discovery_admission import engine
from verification.discovery import narrow_manchester as m,narrow_comparison as c,narrow_oldham as o,narrow_oldham_record as a,narrow_oldham_binding as b,narrow_oldham_supervisor as sup
ROOT=Path(__file__).resolve().parents[1]


def assert_registered(kind,raw):
    names={'manchester1':'stage4-manchester-20261015-once.yml','comparison3':'stage4-bolton-delta3-comparison-once.yml','oldham2':'stage4-oldham-two-capture-once.yml'}
    assert raw==(m.PACK/f'registered-{kind}.yml.txt').read_bytes()
    w=yaml.load(raw,Loader=yaml.BaseLoader)
    assert set(w['on'])=={'workflow_dispatch'} and w['permissions']=={'contents':'read'}
    assert set(w['on']['workflow_dispatch']['inputs'])=={'reviewed_sha','manifest_sha','authority'}
    assert w['concurrency']['cancel-in-progress']=='false'
    job=next(iter(w['jobs'].values()));assert 'env' not in w and 'env' not in job
    steps=job['steps'];checkout=next(s for s in steps if s.get('uses')=='actions/checkout@v4')
    assert checkout['with']=={'ref':'${{ inputs.reviewed_sha }}','persist-credentials':'false'}
    secrets=[s for s in steps if 'secrets.' in str(s)]
    if kind=='manchester1':assert not secrets and 'environment' not in job
    else:
        assert job['environment']=='stage4-production-canary' and len(secrets)==1
        assert list(v for v in secrets[0]['env'].values() if 'secrets.' in str(v))==['${{ secrets.DATABASE_URL }}']
    assert names[kind] in str(steps[0]) and 'GITHUB_RUN_NUMBER' in str(steps[0]) and 'GITHUB_RUN_ATTEMPT' in str(steps[0])
    return w


def hosted(workflow):
    sha='a'*40
    return dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/master',GITHUB_SHA=sha,GITHUB_WORKFLOW_SHA=sha,GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+workflow+'@refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',JOB_STARTED_EPOCH=str(int(time.time())))


@pytest.mark.parametrize('kind',['manchester1','comparison3','oldham2'])
def test_registered_actual_environment_and_mutations(kind):
    workflow=m.profile(kind)['workflow'] if kind=='manchester1' else c.WORKFLOW if kind=='comparison3' else b.WORKFLOW
    raw=(ROOT/workflow).read_bytes();w=assert_registered(kind,raw)
    env=hosted(workflow)
    calls=(lambda e:m.admit(kind,'a'*40,m.profile(kind)['manifest_sha'],m.profile(kind)['authority'],e)) if kind=='manchester1' else (lambda e:c.admit(e,'a'*40,c.MANIFEST_SHA,c.AUTHORITY)) if kind=='comparison3' else (lambda e:b.admit('a'*40,o.COHORT_SHA,b.AUTHORITY,e))
    # Map the real workflow field, not a made-up alternate env key.
    mapped=[s['env'] for s in next(iter(w['jobs'].values()))['steps'] if 'GITHUB_WORKFLOW_SHA' in s.get('env',{})]
    assert mapped and all(v['GITHUB_WORKFLOW_SHA']=='${{ github.workflow_sha }}' for v in mapped)
    calls(env)
    for key,value in [('GITHUB_WORKFLOW_SHA','b'*40),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_RUN_NUMBER','2'),('GITHUB_REF','refs/heads/other')]:
        with pytest.raises(ValueError):calls(dict(env,**{key:value}))
    without=dict(env);without.pop('GITHUB_WORKFLOW_SHA')
    with pytest.raises(ValueError):calls(without)
    with pytest.raises(AssertionError):assert_registered(kind,raw+b'# altered\n')


def synthetic(row,status='Decided',decision='Granted',date='Wed 14 Oct 2026'):
    from verification.direct_reference.fixtures import Session as SourceSession,summary
    from verification.discovery.material_qualification import idox_worker,project_idox
    fixture=SourceSession(summary(row['reference'],status=status,decision=decision,date=date))
    with patch('verification.direct_reference.refresh.requests_session',lambda:fixture),patch('verification.direct_reference.batch_supervisor.resource_limits',lambda:None):raw=idox_worker(row)
    raw.update(process_cleanup='CLOSED',live_owned_survivors=0,peak_owned_rss=100,owned_processes_seen=1,supervisor_seconds=1,supervisor_limit_hit=False)
    return project_idox(row,raw)


def seed(engine):
    with Session(engine) as s:
        s.add(Council(code='oldham',name='Oldham',base_url='https://planningpa.oldham.gov.uk',date_field_mode='received',doc_system='idox'));s.commit()


def exercise(engine):
    seed(engine);row=next(a.rows());phases=[]
    out=a.record(engine,row,retrieve=synthetic,journal=phases.append)
    assert out['identity']=='CREATED_PENDING' and out['facts']=='COUPLED_FACTS_VERIFIED',out
    assert out['transaction']=='COMMIT_READBACK_CONFIRMED' and out['readback']['site_id'] is None
    assert out['admission_mode']=='COMPLETE_WINDOW' and out['verification_scope']=='COUPLED'
    assert 'FACTS_COMMIT_READBACK_CONFIRMED' in phases
    with Session(engine) as s:app=s.get(Application,out['application_id']);app.status='PRESERVE';s.commit()
    again=a.record(engine,row,retrieve=lambda _:pytest.fail('existing must not refetch'))
    assert again['identity']=='ALREADY_KNOWN' and again['facts']=='EXISTING_NOT_WRITTEN'
    with Session(engine) as s:assert s.get(Application,out['application_id']).status=='PRESERVE'


def test_shared_primary_b2_coupled_path(engine):exercise(engine)


def test_frozen_original_window_provenance():
    rows=list(a.rows());assert [r['reference'] for r in rows]==['NMA/356901/26','VAR/356938/26']
    assert all(a.envelope(r).window.run_id=='38758465439' and a.envelope(r).window.outcome.value=='COMPLETE' for r in rows)
    assert [x['reference'] for x in c.identities()]==['01859/26','01860/26','01861/26']
    assert m.manifest('manchester1')['rows'][0]['start']==m.manifest('manchester1')['rows'][0]['end']=='2026-10-15'


def test_unaccepted_initial_scope_withheld(engine):
    seed(engine);row=next(a.rows())
    out=a.record(engine,row,retrieve=lambda r:synthetic(r,status='Deposited',decision='',date=''))
    assert out['identity']=='CREATED_PENDING' and out['facts']=='WITHHELD_FRESH_EVIDENCE'
    assert out['readback']['status'] is None


@pytest.mark.parametrize('failure',['source','readback','checkpoint','cleanup','commit'])
def test_uncertainty_prevents_next_record(engine,failure):
    seed(engine);calls=[]
    def factory():calls.append(1);return engine
    def source(r):
        if failure=='source':raise RuntimeError('not exported')
        return synthetic(r)
    def checkpoint(_):
        if failure=='checkpoint':raise RuntimeError('checkpoint')
    from contextlib import ExitStack
    with ExitStack() as stack:
        if failure=='readback':stack.enter_context(patch.object(a,'readback',side_effect=RuntimeError('readback')))
        if failure=='cleanup':stack.enter_context(patch.object(engine,'dispose',side_effect=RuntimeError('cleanup')))
        if failure=='commit':stack.enter_context(patch.object(a,'admit_identity',side_effect=a.UncertainDiscoveryCommit('commit')))
        out=o.run(engine_factory=factory,reader=source,checkpoint=checkpoint,journal=lambda *_:None)
    assert len(calls)==1 and out['stop']
    assert 'not exported' not in str(out)


def test_source_child_closed_mapping_and_credentials():
    from verification.direct_reference import instrumented_probe as i
    assert set(i.OLDHAM_TWO_CASES)=={'narrow_oldham_0','narrow_oldham_1'}
    text=(ROOT/'verification/direct_reference/instrumented_probe.py').read_text()
    assert "'verification.discovery.narrow_oldham_source' if case in OLDHAM_TWO_CASES" in text
    with pytest.raises(ValueError):a.source.shared.credential_free({'DATABASE_URL':'forbidden'})


def test_phase_limits_and_checkpoint(tmp_path):
    j=sup.Journal(tmp_path);j(0,'RECORD_STARTED');j(0,'SOURCE_STARTED')
    assert sup.phase_bound(tmp_path,time.monotonic()+56)=='PHASE_DEADLINE'
    with pytest.raises(ValueError):j(2,'RECORD_STARTED')
    assert o.LIMITS['seconds']==2*180+120 and o.LIMITS['requests']==4


def test_actual_source_supervisor_delegates_and_strips_credentials(tmp_path,monkeypatch):
    from verification.direct_reference import instrumented_probe as i
    from tests.test_discovery_r0_registered_scopes import proc_namespace
    from unittest.mock import MagicMock
    import psutil,os
    captured={}
    def launch(command,**kw):
        captured.update(command=command,env=kw['env'])
        Path(command[command.index('--output')+1]).write_text(json.dumps(dict(case='narrow_oldham_0',failure=None)))
        child=MagicMock(pid=999999,returncode=0);child.poll.return_value=0;child.wait.return_value=0;return child
    monkeypatch.setenv('DATABASE_URL','DO_NOT_EXPORT');monkeypatch.setenv('BOLTON_ADMISSION_DATABASE_URL','DO_NOT_EXPORT')
    monkeypatch.setenv('GITHUB_ACTIONS','true');monkeypatch.setenv('RUNNER_ENVIRONMENT','github-hosted')
    with proc_namespace(),patch.object(i.subprocess,'Popen',launch),patch.object(psutil,'Process',return_value=MagicMock()),patch.object(psutil,'wait_procs',return_value=([],[])):
        i.supervised('narrow_oldham_0',tmp_path/'source.json')
    assert captured['command'][2]=='verification.discovery.narrow_oldham_source'
    assert not any('DATABASE' in k or 'TOKEN' in k or 'SECRET' in k for k in captured['env'])
    assert 'DO_NOT_EXPORT' not in str(captured)


@pytest.mark.parametrize('kind',['comparison','capture'])
def test_outer_kills_hanging_owned_child_and_no_retry(kind,tmp_path):
    import os,subprocess,sys
    from verification.discovery import narrow_read_supervisor as ro
    module=ro if kind=='comparison' else sup;captured={}
    def launch(command,**kw):
        captured.update(command=command,env=kw['env'])
        return subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'],**kw)
    if int(Path('/proc/self/stat').read_text().split()[0])!=os.getpid():
        with pytest.raises(ValueError,match='PROCESS_NAMESPACE_MISMATCH'):module.supervise(tmp_path/'audit',credential='DISPOSABLE',runner=launch,deadline=.1)
        assert not captured;return
    out=module.supervise(tmp_path/'audit',credential='DISPOSABLE',runner=launch,deadline=.1)
    assert out['stop_reason']=='AGGREGATE_DEADLINE' and out['cleanup']=='CLOSED' and out['live_owned_survivors']==0 and out['retry'] is False
    assert captured['command'][2]=='verification.discovery.narrow_'+('read_supervisor' if kind=='comparison' else 'oldham_supervisor')
    assert 'DISPOSABLE' not in json.dumps(out)


def test_manchester_parent_reaches_exact_reader_without_setup_overhead_exhausting_call(tmp_path):
    calls=[]
    def reader(row):calls.append(row);raise RuntimeError('synthetic no source')
    # Exercise actual parent admission of one full 55s allocation plus accounting reserve.
    # Failure is deliberately synthetic; no council call occurs in this test.
    (tmp_path/'audit').mkdir()
    with patch.dict('os.environ',{},clear=True),patch.object(m,'read',reader):m.execute_worker(m.plan('manchester1'),tmp_path/'out.json',tmp_path/'audit')
    assert calls==m.manifest('manchester1')['rows']
    out=json.loads((tmp_path/'out.json').read_bytes())
    assert out['stop_reason']=='SOURCE_EXCEPTION' and out['accounting_complete'] is False
    assert m.profile('manchester1')['worker_allocation_seconds']==55
    assert m.profile('manchester1')['seconds']+m.profile('manchester1')['setup_seconds']+m.profile('manchester1')['cleanup_upload_seconds']==480
