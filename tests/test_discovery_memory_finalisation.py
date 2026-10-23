"""Bounded post-failure finalisation: a latched memory failure may only publish and close.

Drives the real OperationalMemory latch/finalisation code against a file-backed
cgroup tree and the real launcher/publisher with the fixture API. Native kernel
behaviour is proved separately by tests/four_council_release_fixture_cli.py.
"""
import json
import os
from pathlib import Path
import shutil
import pytest
from verification.discovery import four_council_release as r
from verification.ingestion_storage.memory_enforcement import MemoryUnavailable
from tests.test_discovery_failure_reporting import kernel, journalled, final
from tests.test_discovery_three_council_isolation import world

GROUPS=('aggregate','controller','source')
EVENTS=('low','high','max','oom','oom_kill','oom_group_kill')


def path(m,name):return {'aggregate':m.root,'controller':m.controller,'source':m.source}[name]


def events(m,name,**values):
    path(m,name).joinpath('memory.events').write_text(''.join(f'{k} {values.get(k,0)}\n' for k in EVENTS))


def enforcing(tmp_path,monkeypatch):
    m=kernel(tmp_path);m.controller.joinpath('cgroup.procs').write_text(str(os.getpid()))
    original=Path.rmdir
    monkeypatch.setattr(Path,'rmdir',lambda p:shutil.rmtree(p) if tmp_path in p.parents else original(p))
    return m


def limit_event(m):
    """Kernel-shaped reclaim at the limit: max counted, no OOM (as reproduced natively)."""
    events(m,'source',max=26);events(m,'aggregate',max=26)


def latched(tmp_path,monkeypatch):
    m=enforcing(tmp_path,monkeypatch);limit_event(m)
    with pytest.raises(MemoryUnavailable,match='MEMORY_LIMIT_HIT'):m.snapshot()
    return m,m.latch()


# --- OperationalMemory -------------------------------------------------------

def test_unlatched_behaviour_is_unchanged(tmp_path,monkeypatch):
    m=enforcing(tmp_path,monkeypatch);limit_event(m)
    with pytest.raises(MemoryUnavailable,match='MEMORY_LIMIT_HIT'):m.close()
    assert m.source.is_dir() and not m.finalisation_only
    with pytest.raises(MemoryUnavailable,match='FINALISATION_BASELINE_UNAVAILABLE'):m.finalisation_check()


def test_latch_records_counters_and_closes_execution_permanently(tmp_path,monkeypatch):
    m,latch=latched(tmp_path,monkeypatch)
    assert latch['events']['source']['max']==26 and latch['events']['source']['oom']==0 and latch['execution_authority'] is False
    evidence=m.finalisation_check()
    assert evidence['source']['latched_events']==latch['events']['source'] and evidence['source']['events']['max']==26
    events(m,'source');events(m,'aggregate')  # even an apparently clean kernel never reopens execution
    with pytest.raises(MemoryUnavailable,match='FINALISATION_ONLY'):m.snapshot()
    with pytest.raises(MemoryUnavailable,match='FINALISATION_ONLY'):m.latch()


@pytest.mark.parametrize('name',GROUPS)
@pytest.mark.parametrize('field',EVENTS)
def test_any_counter_change_after_latch_refuses(tmp_path,monkeypatch,name,field):
    m,latch=latched(tmp_path,monkeypatch)
    values=dict(latch['events'][name]);values[field]+=1;events(m,name,**values)
    with pytest.raises(MemoryUnavailable,match='MEMORY_EVENT_AFTER_LATCH'):m.finalisation_check()
    with pytest.raises(MemoryUnavailable,match='MEMORY_EVENT_AFTER_LATCH'):m.close()
    assert m.source.is_dir() and m.controller.is_dir()


@pytest.mark.parametrize('name',GROUPS)
@pytest.mark.parametrize('field,value',[('memory.max','max'),('memory.max','1'),('memory.swap.max','max'),('memory.oom.group','0')])
def test_changed_enforcement_refuses_latch_and_finalisation(tmp_path,monkeypatch,name,field,value):
    m,_=latched(tmp_path,monkeypatch)
    path(m,name).joinpath(field).write_text(value)
    with pytest.raises(MemoryUnavailable,match='MEMORY_ENFORCEMENT_LOST|EXACT_AGGREGATE_MEMORY_LIMIT'):m.finalisation_check()
    with pytest.raises(MemoryUnavailable):m.close()
    fresh=enforcing(tmp_path/'fresh',monkeypatch);limit_event(fresh);path(fresh,name).joinpath(field).write_text(value)
    with pytest.raises(MemoryUnavailable):fresh.latch()
    assert fresh.finalisation_only and fresh.latched is None
    with pytest.raises(MemoryUnavailable,match='FINALISATION_BASELINE_UNAVAILABLE'):fresh.finalisation_check()


def test_populated_source_or_controller_survivor_refuses(tmp_path,monkeypatch):
    m=enforcing(tmp_path,monkeypatch);limit_event(m)
    m.source.joinpath('cgroup.events').write_text('populated 1\nfrozen 0\n')
    with pytest.raises(MemoryUnavailable,match='SOURCE_SURVIVORS'):m.latch()
    with pytest.raises(MemoryUnavailable,match='SOURCE_SURVIVORS'):m.close()
    m.source.joinpath('cgroup.events').write_text('populated 0\nfrozen 0\n')  # emptied later: still no baseline
    with pytest.raises(MemoryUnavailable,match='FINALISATION_BASELINE_UNAVAILABLE'):m.close()
    with pytest.raises(MemoryUnavailable,match='FINALISATION_ONLY'):m.snapshot()
    m,_=latched(tmp_path/'after',monkeypatch)
    m.source.joinpath('cgroup.events').write_text('populated 1\nfrozen 0\n')
    with pytest.raises(MemoryUnavailable,match='SOURCE_SURVIVORS'):m.finalisation_check()
    m.source.joinpath('cgroup.events').write_text('populated 0\nfrozen 0\n')
    m.controller.joinpath('cgroup.procs').write_text(f'{os.getpid()}\n1\n')
    with pytest.raises(MemoryUnavailable,match='CONTROLLER_OWNED_SURVIVORS'):m.finalisation_check()


def test_replaced_group_or_moved_process_refuses(tmp_path,monkeypatch):
    m,_=latched(tmp_path,monkeypatch)
    old=tmp_path/'old-source';m.source.rename(old);shutil.copytree(old,m.source)  # same contents, new group
    with pytest.raises(MemoryUnavailable,match='CGROUP_IDENTITY_CHANGED'):m.finalisation_check()
    m,_=latched(tmp_path/'moved',monkeypatch)
    original=Path.read_text
    monkeypatch.setattr(Path,'read_text',lambda p,*a,**k:'0::/elsewhere\n' if str(p)=='/proc/self/cgroup' else original(p,*a,**k))
    with pytest.raises(MemoryUnavailable,match='CGROUP_IDENTITY_CHANGED'):m.finalisation_check()


@pytest.mark.parametrize('raw',[None,'garbage','max 0\n','low 0\nhigh 0\nmax x\noom 0\noom_kill 0\noom_group_kill 0\n'])
def test_uncertain_counter_readback_refuses(tmp_path,monkeypatch,raw):
    m,_=latched(tmp_path,monkeypatch)
    target=m.source/'memory.events'
    if raw is None:target.unlink()
    else:target.write_text(raw)
    with pytest.raises(MemoryUnavailable,match='MEMORY_FIELD_UNAVAILABLE'):m.finalisation_check()
    with pytest.raises(MemoryUnavailable,match='MEMORY_FIELD_UNAVAILABLE'):m.close()
    assert m.source.is_dir()


@pytest.mark.parametrize('where,field',[('controller',f) for f in ('max','oom','oom_kill','oom_group_kill')]+[('aggregate-local',f) for f in ('max','oom','oom_kill','oom_group_kill')])
def test_controller_or_aggregate_own_event_is_never_finalised(tmp_path,monkeypatch,where,field):
    m=enforcing(tmp_path,monkeypatch);limit_event(m)
    if where=='controller':events(m,'controller',**{field:1})
    else:m.root.joinpath('memory.events.local').write_text(''.join(f'{k} {1 if k==field else 0}\n' for k in EVENTS))
    with pytest.raises(MemoryUnavailable,match='CONTROLLER_OR_AGGREGATE_MEMORY_EVENT'):m.latch()
    assert m.finalisation_only and m.latched is None
    with pytest.raises(MemoryUnavailable,match='FINALISATION_BASELINE_UNAVAILABLE'):m.close()


def test_source_oom_is_latched_and_reported_not_hidden(tmp_path,monkeypatch):
    m=enforcing(tmp_path,monkeypatch);events(m,'source',max=3,oom=1,oom_kill=2,oom_group_kill=1);events(m,'aggregate',max=3,oom=1,oom_kill=2,oom_group_kill=1)
    latch=m.latch();assert latch['events']['source']['oom_kill']==2
    assert m.close()['memory']['source']['latched_events']['oom_group_kill']==1


def test_latched_close_removes_groups_and_reports_counters(tmp_path,monkeypatch):
    m,latch=latched(tmp_path,monkeypatch)
    value=m.close()
    assert value['owned_groups_removed'] and value['finalisation']=='LATCHED_COUNTERS_UNCHANGED'
    assert value['memory']['source']['latched_events']==latch['events']['source']
    assert not m.source.exists() and not m.controller.exists()


def test_bounded_memory_stat_categories_without_summing_subsets(tmp_path,monkeypatch):
    m=enforcing(tmp_path,monkeypatch)
    value=m.observe();stat=value['groups']['source']['memory.stat']
    assert value['status']=='OBSERVED' and stat==dict(anon=10,file=60,kernel=30,sock=0,shmem=0,file_mapped=5)
    assert value['stat_categories']['disjoint']==['anon','file','kernel','sock']
    assert value['stat_categories']['subset_of']['shmem']=='file' and value['stat_categories']['subset_of']['slab_reclaimable']=='kernel'
    for raw in ('x'*16385,'anon 1\nfile 2\n','anon 1\nanon 2\nfile 1\nkernel 1\nshmem 0\n','anon -1\nfile 1\nkernel 1\nshmem 0\n'):
        m.source.joinpath('memory.stat').write_text(raw)
        value=m.observe()
        assert value['status']=='PARTIAL' and 'memory.stat' not in value['groups']['source'] and not value['execution_authority']


# --- Launcher -----------------------------------------------------------------

@pytest.fixture
def kworld(world,tmp_path,monkeypatch):
    reg,api,_,source,launch,events_=world
    m=enforcing(tmp_path/'kernel',monkeypatch);launch.memory=m
    def run(index,check):
        source.calls.append(index);check();limit_event(m)
        try:m.snapshot()
        except MemoryUnavailable as error:
            raise r.SourceFailure(r.failure_detail(error,'SOURCE_MEMORY_CHECK'),dict(source_group_closed=True,child_reaped=True,failures=[])) from None
        raise AssertionError('limit event not detected')
    source.run=run
    return reg,api,m,source,launch,journalled(launch,tmp_path)


def mutations(api,start):return [c for c in api.calls[start:] if c[0]!='GET']


def test_max_without_oom_finalises_without_upgrading_source_evidence(kworld,tmp_path):
    reg,api,m,source,launch,journal=kworld
    out=launch.execute()
    assert out['finalisation']['state']=='FINALISATION_ONLY' and out['finalisation']['latched_counters']['source']['max']==26
    assert out['owned_cleanup']['memory']['source']['events']['max']==26 and not out['reporting_failures']
    assert r.finish(launch,journal,out,tmp_path)==1
    value=final(tmp_path)
    assert value['failure']==dict(stage='SOURCE_MEMORY_CHECK',code='MEMORY_LIMIT_HIT',kind='MEMORY',message_exported=False)
    assert value['reason']=='MEMORY_LIMIT_HIT' and value['status']=='STOP_RECONCILE_NO_RETRY'
    assert value['final_publication']=='VERIFIED' and value['owned_group_closure']=='CLOSED'
    assert value['owned_cleanup']['finalisation']=='LATCHED_COUNTERS_UNCHANGED' and not m.source.exists()
    # Execution failure, source evidence and accounting are not upgraded by cleanup.
    assert value['source_outcome']=='UNVERIFIED' and value['accounting_status']=='PARTIAL_SOURCE_USAGE_UNKNOWN'
    assert value['source_usage']==dict(requests=None,mixed_bytes=None,worker_seconds=None)
    assert value['containment_status']=='UNCERTAIN' and value['cleanup']=='UNCERTAIN'
    assert source.calls==[1] and len(value['not_attempted'])==2 and not value['results']
    assert not any('slot-' in p for _,p in api.calls)
    import base64
    raws=[base64.b64decode(b['content']) for b in api.blobs.values()]
    published=[json.loads(x) for x in raws if x.startswith(b'{"accounting"')]
    assert published and all(x['failure']['code']=='MEMORY_LIMIT_HIT' and x['finalisation']['state']=='FINALISATION_ONLY' for x in published)
    # The exported packet must not show pending/clean cleanup for a latched failure.
    assert all(x['cleanup']=='UNCERTAIN' and x['process_cleanup']=='UNCERTAIN' and x['containment_status']=='UNCERTAIN' for x in published)
    r.verify_chain((tmp_path/'events.jsonl').read_bytes())


def test_no_later_council_or_source_process_after_latch(kworld,tmp_path,monkeypatch):
    reg,api,m,source,launch,journal=kworld
    launch.execute()
    with pytest.raises(MemoryUnavailable,match='FINALISATION_ONLY'):launch.poll()
    with pytest.raises(MemoryUnavailable,match='FINALISATION_ONLY'):launch.slot_closure(dict(source_group_closed=True))
    started=[];monkeypatch.setattr(r.subprocess,'Popen',lambda *a,**k:started.append(a))
    m.source.mkdir(exist_ok=True);(m.source/'cgroup.kill').write_text('')
    with pytest.raises(r.SourceFailure) as caught:r.Source(m,{'version':r.SUCCESSOR_VERSION},tmp_path).run(2,lambda:None)
    assert caught.value.primary['code']=='FINALISATION_ONLY' and not started and source.calls==[1]


@pytest.mark.parametrize('change',['counter','limit','survivor','identity'])
def test_change_after_latch_holds_export_and_group_removal(kworld,tmp_path,change):
    reg,api,m,source,launch,journal=kworld
    out=launch.execute();before=len(api.calls)
    if change=='counter':events(m,'controller',max=1);events(m,'aggregate',max=27)
    elif change=='limit':m.source.joinpath('memory.max').write_text(str(2*1024**3))
    elif change=='survivor':m.source.joinpath('cgroup.events').write_text('populated 1\nfrozen 0\n')
    else:m.latched['identity']['groups']['source']=[0,0]
    assert r.finish(launch,journal,out,tmp_path)==1
    value=final(tmp_path)
    assert value['final_publication']=='UNCERTAIN_OR_HELD' and value['owned_group_closure']=='NOT_VERIFIED'
    assert value['failure']['stage']=='SOURCE_MEMORY_CHECK' and value['reason']=='MEMORY_LIMIT_HIT'
    assert {x['stage'] for x in value['reporting_failures']}>={'FINAL_PUBLICATION','OWNED_GROUP_CLOSURE'}
    assert not mutations(api,before) and m.source.is_dir() and value['cleanup']=='UNCERTAIN'
    assert value['local_evidence_packet']['status']=='PRESERVED'


def test_uncertain_source_closure_never_latches(kworld,tmp_path):
    reg,api,m,source,launch,journal=kworld
    def run(index,check):
        source.calls.append(index);limit_event(m)
        raise r.SourceFailure(r.failure_detail(MemoryUnavailable('MEMORY_LIMIT_HIT'),'SOURCE_MEMORY_CHECK'),dict(source_group_closed=False,child_reaped=True,failures=[]))
    source.run=run;out=launch.execute()
    assert out['finalisation']=={'state':'NOT_LATCHED'} and not m.finalisation_only
    assert r.finish(launch,journal,out,tmp_path)==1
    value=final(tmp_path)
    assert value['final_publication']=='UNCERTAIN_OR_HELD' and value['owned_group_closure']=='NOT_VERIFIED' and source.calls==[1]


def test_live_child_or_socket_holds_finalisation_export(kworld,tmp_path,monkeypatch):
    reg,api,m,source,launch,journal=kworld
    out=launch.execute();before=len(api.calls)
    monkeypatch.setattr('psutil.Process',lambda:type('Process',(),{'children':lambda self,recursive:[object()]})())
    assert r.finish(launch,journal,out,tmp_path)==1
    value=final(tmp_path)
    assert value['final_publication']=='UNCERTAIN_OR_HELD' and not mutations(api,before)
    assert value['child_socket_closure']=='UNCERTAIN' and value['cleanup']=='UNCERTAIN'


@pytest.mark.parametrize('fault',['publication','lost_ack','cancel','expiry'])
def test_finalisation_publication_failure_cancel_or_expiry_never_retries(kworld,tmp_path,fault):
    reg,api,m,source,launch,journal=kworld
    out=launch.execute();before=len(api.calls)
    if fault=='publication':api.fail=lambda method,path:method=='POST'
    elif fault=='lost_ack':api.lost=True
    elif fault=='cancel':
        def cancel(method,path):
            if method=='POST':launch.cancelled=True;raise r.Stop('OPERATOR_CANCELLED')
        api.fail=cancel
    else:launch.wall=lambda:r.stamp(reg['expires_at'])
    assert r.finish(launch,journal,out,tmp_path)==1
    value=final(tmp_path)
    assert value['final_publication']=='UNCERTAIN_OR_HELD' and value['failure']['code']=='MEMORY_LIMIT_HIT'
    after=mutations(api,before)
    if fault=='expiry':assert not after
    elif fault=='lost_ack':assert after[-1][0]=='PATCH' and launch.github.mutation_uncertain  # ref effect, ACK lost, nothing after
    else:assert len(after)==1 and launch.github.mutation_uncertain  # first mutation fails; never retried
    assert source.calls==[1] and value['cleanup']=='UNCERTAIN' and value['source_outcome']=='UNVERIFIED'
    # Group removal is independent of export, but still gated by finalisation_check.
    assert value['owned_group_closure']=='CLOSED'
