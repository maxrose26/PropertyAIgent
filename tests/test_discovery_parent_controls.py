"""Synthetic HTTP and injected owned processes, actual caller/worker/parent path."""
import hashlib,json,os,sys,time
from pathlib import Path
from unittest.mock import MagicMock,patch
import pytest,yaml
from verification.discovery import r0_parent_metadata as p,r0_proposal as outer,r0_registered_scopes as shared
from tests.test_discovery_r0_registered_scopes import context,proc_namespace
from tests.test_discovery_idox_window import Response
from verification.bolton_recon.fixtures import FORM


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for k in list(os.environ):
        if 'DATABASE' in k or k.startswith(('SUPABASE_','OPENAI_','ANTHROPIC_')):monkeypatch.delenv(k,raising=False)


def fixture_session(index,closed):
    ref=p.metadata.REFERENCES[index]
    summary=f'<html><table id="simpleDetailsTable"><tr><th>Reference</th><td>{ref}</td></tr><tr><th>Proposal</th><td>Residential development scale unknown</td></tr></table></html>'.encode()
    queue=[FORM,b'<html><a href="applicationDetails.do?activeTab=summary&amp;keyVal=ONLY">record</a></html>',summary]
    class Session:
        trust_env=True
        def mount(self,*a):pass
        def request(self,*a,**kw):
            assert self.trust_env is False and kw['timeout']==(3,8) and kw['allow_redirects'] is False
            assert 'deadline' not in kw
            return Response(queue.pop(0))
        def close(self):closed.append(index)
    return Session()


def supervised_value(index):
    closed=[];v=p.source_worker(index,session_factory=lambda:fixture_session(index,closed));assert closed==[index]
    v['outer_supervisor']=dict(cleanup='CLOSED',live_owned_survivors=0,expired=False,exit_code=0,limit_hit=None)
    return v


def test_real_main_outer_record_worker_and_checkpoint_chain(tmp_path,monkeypatch):
    w=yaml.load(p.TEMPLATE.read_text(),Loader=yaml.BaseLoader);e=dict(context('bolton53'),GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+p.WORKFLOW+'@refs/heads/master')
    vals={'${{ inputs.reviewed_sha }}':'a'*40,'${{ inputs.manifest_sha }}':p.MANIFEST_SHA,'${{ inputs.authority }}':p.AUTHORITY,'${{ github.workflow_sha }}':'a'*40,'${{ env.SOURCE_JOB_STARTED_EPOCH }}':str(int(time.time()))}
    for s in w['jobs']['source']['steps']:
        e.update({k:vals[v] for k,v in s.get('env',{}).items() if v in vals})
    for k,v in e.items():monkeypatch.setenv(k,v)
    root=tmp_path/'audit';closed=[];sessions=[];launches=[]
    def factory():
        i=len(sessions)
        if i:assert (root/'checkpoints/000.json').is_file()
        sessions.append(i);return fixture_session(i,closed)
    def source(index):return original_source(index,session_factory=factory)
    def runner(command,**kw):
        launches.append(command)
        assert command[1:3]==['-m','verification.discovery.r0_parent_metadata']
        assert not any('DATABASE' in k or 'AUTHORITY' in k for k in kw['env'])
        p.execute_worker(json.loads(Path(command[command.index('--worker')+1]).read_bytes()),Path(command[command.index('--output')+1]),Path(command[command.index('--audit-dir')+1]))
        child=MagicMock(pid=999999,returncode=0);child.poll.return_value=0;child.wait.return_value=0;return child
    real=outer.supervise_round;original_source=p.source_worker;admit=p.admit
    monkeypatch.setattr(sys,'argv',['parent','--reviewed-sha','a'*40,'--manifest-sha',p.MANIFEST_SHA,'--authority',p.AUTHORITY,'--output',str(root)])
    with proc_namespace(),patch.object(shared,'checkout'),patch.object(p,'source_worker',source),patch.object(outer,'supervise_round',side_effect=lambda a,b,**kw:real(a,b,runner=runner,**kw)),patch.object(psutil_module(),'Process',return_value=MagicMock()),patch.object(psutil_module(),'wait_procs',return_value=([],[])):
        assert p.main()==0
    d=json.loads((root/'result.json').read_bytes())
    assert sessions==closed==[0,1] and len(launches)==3
    assert d['requests']==6 and d['received_bytes']<=6000000 and d['accounting_complete']
    assert len(d['checkpoint_sha256'])==2 and shared.audit_bytes(root)<=131072
    for i,h in enumerate(d['checkpoint_sha256']):assert hashlib.sha256((root/f'checkpoints/{i:03}.json').read_bytes()).hexdigest()==h
    assert d['outer_supervisor']['cleanup']=='CLOSED' and (p.ROOT/p.WORKFLOW).read_bytes()==p.TEMPLATE.read_bytes()


def psutil_module():
    import psutil
    return psutil


@pytest.mark.parametrize('change',[
    lambda a:a.update(reference='WRONG'),lambda a:a.update(identity='WITHHELD',failure='SOURCE_OR_IDENTITY_REJECTED'),
    lambda a:a.update(session_cleanup='UNKNOWN'),lambda a:a['resource'].update(requests_attempted=None),
    lambda a:a['resource'].update(received_bytes=3000001),lambda a:a['resource'].update(elapsed_seconds=46),
    lambda a:a['outer_supervisor'].update(cleanup='FAILED'),lambda a:a['outer_supervisor'].update(live_owned_survivors=1),
    lambda a:a['outer_supervisor'].update(expired=True,limit_hit='DEADLINE'),
    lambda a:a.update(accounting_complete=False),
])
def test_uncertainty_stops_before_second_parent(tmp_path,change):
    calls=[]
    def reader(i):calls.append(i);a=supervised_value(i);change(a);return a
    out=p.execute(tmp_path/'result.json',tmp_path,reader=reader)
    assert calls==[0] and out['stop_reason'] and out['not_attempted']==['20683/25']
    assert out['requests'] is None and out['received_bytes'] is None and out['source_seconds'] is None


def test_checkpoint_failure_and_deadline_stop(tmp_path):
    calls=[]
    class Broken(shared.AuditStore):
        def record(self,v):raise OSError('fixture failure')
    def reader(i):calls.append(i);return supervised_value(i)
    out=p.execute(tmp_path/'one.json',tmp_path,reader=reader,store_factory=Broken)
    assert calls==[0] and out['stop_reason']=='CHECKPOINT_UNCERTAIN_NO_NEXT_CALL'
    other=tmp_path/'other';other.mkdir();times=iter([0,100])
    out=p.execute(other/'result.json',other,reader=lambda _:pytest.fail('source'),clock=lambda:next(times,100))
    assert out['attempted']==0 and out['stop_reason']=='AGGREGATE_BUDGET_NO_NEXT_CALL'


def test_audit_duplication_and_fixed_context():
    assert 2*(2*p.PROFILE['record_output_bytes'])+32768<=131072
    assert 120+160+80==360 and p.PROFILE['seconds']+10==160
    assert p.validate_plan(p.plan(0))['seconds']==50 and p.PROFILE['source_seconds']==90
    assert p.metadata.REFERENCES==('00284/26','20683/25')
    with pytest.raises(ValueError):p.plan(2)
    with pytest.raises(ValueError):p.validate_plan(dict(p.plan(),scope='arbitrary'))


def test_worker_cli_returns_zero_not_audit_dict(tmp_path,monkeypatch):
    plan=tmp_path/'plan.json';plan.write_text(json.dumps(p.plan()))
    monkeypatch.setattr(sys,'argv',['worker','--worker',str(plan),'--audit-dir',str(tmp_path),'--output',str(tmp_path/'result.json')])
    monkeypatch.setattr(p,'execute',lambda *a,**kw:{'synthetic':'audit dictionary'})
    monkeypatch.setattr('resource.setrlimit',lambda *a:None)
    assert p.main()==0


@pytest.mark.parametrize('cause',['DEADLINE','RSS','AUDIT_BYTES','ACCOUNTING','CLEANUP'])
def test_actual_parent_outer_hard_limit_and_cleanup(cause,tmp_path):
    import psutil
    profile=p.PROFILE;signals=[];child=MagicMock(pid=999999,returncode=None);child.poll.return_value=None
    def waited(**kw):child.returncode=-9;return -9
    child.wait.side_effect=waited
    process=MagicMock(pid=999999);process.children.return_value=[];process.create_time.return_value=1
    process.memory_info.return_value.rss=1536*1024*1024+1 if cause=='RSS' else 10
    process.status.side_effect=[psutil.STATUS_RUNNING,psutil.STATUS_RUNNING if cause=='CLEANUP' else psutil.STATUS_ZOMBIE]
    ticks=iter([0,151,152,153]) if cause=='DEADLINE' else None
    amounts=iter([0,131072,0,0,0,0])
    def measured(_):return next(amounts,0) if cause=='AUDIT_BYTES' else 0
    def proc(_):
        if cause=='ACCOUNTING':raise psutil.AccessDenied(999999)
        return process
    def killed(pid,sig):
        signals.append(pid)
        if cause=='CLEANUP':raise PermissionError('synthetic cleanup denial')
    with proc_namespace(),patch.object(psutil,'Process',side_effect=proc),patch.object(psutil,'wait_procs',return_value=([],[])),patch.object(outer.os,'killpg',side_effect=killed),patch.object(shared,'audit_bytes',measured),patch.object(outer.time,'sleep',lambda _:None),patch.object(outer.time,'monotonic',side_effect=(lambda:next(ticks,153)) if ticks else lambda:0):
        # CLEANUP requires termination to reach the deliberately denied reaper.
        if cause=='CLEANUP':process.memory_info.return_value.rss=1536*1024*1024+1
        out=outer.supervise_round(p.plan(),tmp_path/'result.json',runner=lambda *a,**k:child,deadline=150,worker_module='verification.discovery.r0_parent_metadata')
    assert signals==[999999] and not out['accounting_complete']
    if cause in {'ACCOUNTING','CLEANUP'}:assert out['stop_reason']=='OUTER_ACCOUNTING_OR_CLEANUP_UNCERTAIN'
    else:assert out['outer_supervisor']['limit_hit']==cause
