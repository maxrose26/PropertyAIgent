"""Injected failure reproduction, not a diagnosis of the historical root cause."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from verification.discovery import four_council_release as r
from verification.ingestion_storage.operational_memory import OperationalMemory
from verification.ingestion_storage.memory_enforcement import MemoryUnavailable
from tests.test_discovery_three_council_isolation import world


def journalled(launch,root):
    journal=r.Journal(root/'events.jsonl')
    launch.emit=journal.emit;launch.github.emit=journal.emit
    return journal


def final(root):return json.loads((root/'final-result.json').read_bytes())


def test_persistent_gate_failure_reproduces_missing_result_export_and_closure(world,tmp_path):
    reg,api,memory,source,launch,_=world;journal=journalled(launch,tmp_path)
    def broken(index,check):
        source.calls.append(index)
        for _ in range(3):check()
        def reject():raise MemoryUnavailable('MEMORY_LIMIT_HIT')
        memory.snapshot=reject
        raise r.SourceFailure(r.failure_detail(MemoryUnavailable('MEMORY_LIMIT_HIT'),'SOURCE_MEMORY_CHECK'),
            dict(source_group_closed=True,child_reaped=True,failures=[]))
    source.run=broken
    out=launch.execute();calls=launch.github.requests
    assert out['reason']=='MEMORY_LIMIT_HIT' and source.calls==[1]
    assert r.finish(launch,journal,out,tmp_path)==1
    value=final(tmp_path)
    assert value['failure']==dict(stage='SOURCE_MEMORY_CHECK',code='MEMORY_LIMIT_HIT',kind='MEMORY',message_exported=False)
    assert value['source_outcome']=='UNVERIFIED' and value['accounting_status']=='PARTIAL_SOURCE_USAGE_UNKNOWN'
    assert value['child_socket_closure']=='CLOSED' and value['containment_status']=='UNCERTAIN'
    assert value['cleanup']=='UNCERTAIN' and value['outer_scope_observation']=='NOT_OBSERVED_FROM_INSIDE_SCOPE'
    assert value['final_publication']=='UNCERTAIN_OR_HELD' and launch.github.requests==calls
    assert value['owned_group_closure']=='CLOSED'  # fixture close succeeds; still cannot override enforcement uncertainty
    assert value['local_evidence_packet']['status']=='PRESERVED'
    for name,digest in json.loads((tmp_path/'HASHES.json').read_bytes()).items():assert r.sha((tmp_path/name).read_bytes())==digest
    r.verify_chain((tmp_path/'events.jsonl').read_bytes())
    assert len(value['not_attempted'])==2 and not value['results']
    assert not value['coverage_advance'] and value['database_connections']==value['application_writes']==0


@pytest.mark.parametrize('failure_at',['observation','audit_event','audit_close','publication_journal_close','audit_read','packet_write','publication','lost_ack','group_close','socket_read'])
def test_reporting_failures_preserve_primary_and_do_not_replay(world,tmp_path,monkeypatch,failure_at):
    reg,api,memory,source,launch,_=world;journal=journalled(launch,tmp_path)
    def broken(index,check):
        source.calls.append(index);raise r.SourceFailure(r.failure_detail(OSError('PRIVATE_URL_PASSWORD'),'SOURCE_OUTPUT_READ'),
            dict(source_group_closed=True,child_reaped=True,failures=[]))
    source.run=broken;out=launch.execute()
    if failure_at=='observation':memory.observe=lambda:(_ for _ in ()).throw(OSError('PRIVATE'))
    elif failure_at=='audit_event':journal.emit=lambda *_:(_ for _ in ()).throw(OSError('PRIVATE'))
    elif failure_at in ('audit_close','publication_journal_close'):
        original=r.Journal.close
        def close(log):
            original(log)
            if log.path.name==('events.jsonl' if failure_at=='audit_close' else 'publication-events.jsonl'):raise OSError('PRIVATE')
        monkeypatch.setattr(r.Journal,'close',close)
    elif failure_at=='audit_read':
        original=Path.read_bytes
        monkeypatch.setattr(Path,'read_bytes',lambda p:(_ for _ in ()).throw(OSError('PRIVATE')) if p==journal.path else original(p))
    elif failure_at=='packet_write':
        original=r.write_new
        monkeypatch.setattr(r,'write_new',lambda p,raw:(_ for _ in ()).throw(OSError('PRIVATE')) if p.name=='HASHES.json' else original(p,raw))
    elif failure_at=='publication':api.fail=lambda method,path:method=='POST'
    elif failure_at=='lost_ack':api.lost=True
    elif failure_at=='group_close':memory.close=lambda:(_ for _ in ()).throw(PermissionError('PRIVATE'))
    elif failure_at=='socket_read':monkeypatch.setattr(r,'sockets',lambda:(_ for _ in ()).throw(OSError('PRIVATE')))
    assert r.finish(launch,journal,out,tmp_path)==1
    value=final(tmp_path)
    assert value['reason']=='LOCAL_IO_FAILURE' and value['failure']['stage']=='SOURCE_OUTPUT_READ'
    assert value['status']=='STOP_RECONCILE_NO_RETRY' and source.calls==[1]
    assert 'PRIVATE' not in json.dumps(value)
    if failure_at in ('observation','audit_event','audit_close','publication_journal_close','group_close','socket_read'):
        assert value['final_publication']=='VERIFIED'
    else:assert value['final_publication']=='UNCERTAIN_OR_HELD'
    if failure_at in ('lost_ack','publication'):
        first=max(i for i,(m,p) in enumerate(api.calls) if m!='GET')
        assert not any(m!='GET' for m,p in api.calls[first+1:])
    if failure_at in ('observation','audit_close','publication_journal_close','group_close','socket_read','lost_ack','publication'):assert value['cleanup']=='UNCERTAIN'
    if failure_at=='group_close':assert value['child_socket_closure']=='CLOSED' and value['owned_group_closure']=='NOT_VERIFIED'
    if failure_at in ('audit_close','publication_journal_close'):
        assert value['reporting_resource_closure']=='UNCERTAIN' and value['owned_group_closure']=='CLOSED'
    if failure_at=='audit_event':
        assert value['controller_audit_status']=='PARTIAL'
        retained=json.loads((tmp_path/'result-before-publication.json').read_bytes())
        assert retained['controller_audit_status']=='PARTIAL' and retained['audit_chain_validated'] is True


@pytest.mark.parametrize('error,code',[
    (MemoryUnavailable('MEMORY_LIMIT_HIT'),'MEMORY_LIMIT_HIT'),
    (MemoryUnavailable('PRIVATE'),'MEMORY_FAILURE_UNCLASSIFIED'),
    (MemoryUnavailable(['PRIVATE']),'MEMORY_FAILURE_UNCLASSIFIED'),
    (PermissionError('PRIVATE'),'LOCAL_PERMISSION_DENIED'),
    (FileNotFoundError('PRIVATE'),'LOCAL_PATH_UNAVAILABLE'),
    (RuntimeError('PRIVATE'),'UNCLASSIFIED_FAILURE'),
    (r.Uncertain('PRIVATE'),'PUBLICATION_UNCERTAIN'),
])
def test_safe_failure_codes(error,code):
    value=r.failure_detail(error,'SOURCE_PROCESS_START')
    assert value['code']==code and not value['message_exported'] and 'PRIVATE' not in json.dumps(value)


def kernel(tmp_path):
    m=OperationalMemory.__new__(OperationalMemory);m.root=tmp_path/'scope';m.controller=m.root/'controller';m.source=m.root/'source'
    for path,limit in [(m.root,1536*1024**2),(m.controller,256*1024**2),(m.source,1024**3)]:
        path.mkdir(parents=True,exist_ok=True)
        fields={'memory.max':str(limit),'memory.swap.max':'0','memory.oom.group':'1','memory.current':'100','memory.peak':'200','memory.events':'low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\noom_group_kill 0\n','memory.events.local':'low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\noom_group_kill 0\n','memory.stat':'anon 10\nfile 60\nkernel 30\nsock 0\nshmem 0\nfile_mapped 5\nunlisted 7\n','cgroup.events':'populated 0\nfrozen 0\n','cgroup.procs':''}
        for name,value in fields.items():(path/name).write_text(value)
    return m


def test_kernel_observation_retains_limit_events_but_cannot_authorise(world,tmp_path):
    m=kernel(tmp_path);(m.source/'memory.events').write_text('max 4\noom 1\noom_kill 1\n')
    value=m.observe();assert value['status']=='OBSERVED' and value['execution_authority'] is False
    assert value['groups']['source']['memory.events']['max']==4
    with pytest.raises(MemoryUnavailable,match='MEMORY_LIMIT_HIT'):m.snapshot()
    assert m.observe()==value


@pytest.mark.parametrize('raw',['garbage','max 0\n','x'*4097])
def test_partial_kernel_observation_never_fabricates_zero(tmp_path,raw):
    m=kernel(tmp_path);(m.source/'memory.events').write_text(raw)
    value=m.observe();assert value['status']=='PARTIAL' and value['failures']
    assert 'memory.events' not in value['groups']['source'] and not value['execution_authority']


@pytest.mark.parametrize('fault',['memory-failure','reporting-failure','publication-failure'])
def test_actual_cli_injected_failure_preserves_packet_without_external_contact(tmp_path,fault):
    import subprocess,sys
    process=subprocess.run([sys.executable,'-m','tests.four_council_release_fixture_cli','--successor','--root',str(tmp_path/fault),'--fault',fault],cwd=r.ROOT,capture_output=True,text=True,timeout=30)
    assert process.returncode==0,(process.stdout,process.stderr)

@pytest.mark.parametrize('cleanup_fault',[False,True])
def test_actual_source_boundary_keeps_first_failure_and_cleanup_failure(tmp_path,monkeypatch,cleanup_fault):
    from types import SimpleNamespace
    group=tmp_path/'source';group.mkdir();(group/'cgroup.kill').write_text('');(group/'cgroup.events').write_text('populated 0\n')
    def reject():
        if cleanup_fault:(group/'cgroup.events').unlink()
        raise MemoryUnavailable('MEMORY_LIMIT_HIT')
    memory=SimpleNamespace(source=group,snapshot=reject)
    class Child:
        returncode=None
        def poll(self):return self.returncode
        def wait(self,timeout):self.returncode=-9;return -9
    monkeypatch.setattr(r.subprocess,'Popen',lambda *a,**kw:Child())
    source=r.Source(memory,{'version':r.SUCCESSOR_VERSION},tmp_path)
    with pytest.raises(r.SourceFailure) as caught:source.run(1,lambda:None)
    failure=caught.value
    assert failure.primary['stage']=='SOURCE_MEMORY_CHECK' and failure.primary['code']=='MEMORY_LIMIT_HIT'
    assert failure.closure['child_reaped']
    if cleanup_fault:
        assert failure.closure['failures'][0]['stage']=='SOURCE_GROUP_READBACK'
        assert failure.closure['source_group_closed'] is False
    else:assert failure.closure['source_group_closed'] is True


def test_published_partial_packet_never_exports_invalid_source_body(world,tmp_path):
    reg,api,memory,source,launch,_=world;journal=journalled(launch,tmp_path)
    source.values[1]={'private_invalid_source_body':'DO_NOT_EXPORT_ARBITRARY_BODY'}
    out=launch.execute();assert source.calls==[1]
    assert r.finish(launch,journal,out,tmp_path)==1
    value=final(tmp_path)
    assert value['source_outcome']=='UNVERIFIED' and not value['accounting_complete']
    assert value['source_usage']==dict(requests=None,mixed_bytes=None,worker_seconds=None)
    assert value['returned_evidence'][0]['export']=='HELD_UNVALIDATED'
    assert b'DO_NOT_EXPORT_ARBITRARY_BODY' in (tmp_path/'returned-0.json').read_bytes()
    import base64
    assert all(b'DO_NOT_EXPORT_ARBITRARY_BODY' not in base64.b64decode(blob['content']) for blob in api.blobs.values())


def test_failed_validation_does_not_double_count_completed_source_time(world):
    reg,api,memory,source,launch,_=world
    tick=[0.0];launch.clock=lambda:tick[0];launch.start=0.0
    def invalid(index,check):
        source.calls.append(index);tick[0]=4.0
        return {'malformed':True},dict(source_group_closed=True,child_reaped=True,failures=[])
    source.run=invalid
    out=launch.execute()
    assert out['accounting']['active_seconds']==4.0 and source.calls==[1]
    assert not out['accounting_complete'] and out['status']=='STOP_RECONCILE_NO_RETRY'
