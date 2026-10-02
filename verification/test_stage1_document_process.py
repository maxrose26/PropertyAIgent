"""No child shutdown/GC/disposal is used to manufacture resource-release passes."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from app.security import document_process as dp


def frame(value):
    return json.dumps(value).encode()+b'\0'


def test_relay_split_response_and_reuse_rejection():
    relay=dp.Relay()
    command=frame({'id':1,'method':'Target.getTargets'})
    relay.accept(0,command[:7]);assert not relay.pending
    relay.accept(0,command[7:]);assert set(relay.pending)=={1}
    relay.accept(1,frame({'id':1,'result':{}}));assert not relay.pending
    with pytest.raises(dp.ContainmentError,match='Stale'):relay.accept(0,command)


@pytest.mark.parametrize('data',[b'[]\0',b'NaN\0',b'{invalid}\0',b'\xff\0'])
def test_malformed_ipc(data):
    with pytest.raises(dp.ContainmentError,match='Malformed'):dp.Relay().accept(0,data)


def test_mismatched_response():
    with pytest.raises(dp.ContainmentError,match='Mismatched'):dp.Relay().accept(1,frame({'id':44,'result':{}}))


def test_outstanding_request_bound():
    relay=dp.Relay()
    for key in range(1,dp.REQUEST_LIMIT+1):relay.accept(0,frame({'id':key,'method':'Fixture'}))
    with pytest.raises(dp.ContainmentError,match='request bound'):relay.accept(0,frame({'id':dp.REQUEST_LIMIT+1,'method':'Fixture'}))


def test_frame_bound():
    with pytest.raises(dp.ContainmentError,match='frame limit'):dp.Relay().accept(0,b'x'*(dp.FRAME_LIMIT+1))


def test_only_pinned_shutdown_reserved_id():
    relay=dp.Relay();relay.accept(0,frame({'id':-9999,'method':'Browser.close'}))
    assert relay.shutdown_requested
    with pytest.raises(dp.ContainmentError):dp.Relay().accept(0,frame({'id':-9999,'method':'Runtime.evaluate'}))


def test_failed_directory_creation_releases_slot(tmp_path):
    (tmp_path/'process').mkdir()
    for _ in range(2):
        with pytest.raises(FileExistsError):
            with dp.protected_browser(SimpleNamespace(),tmp_path):pytest.fail('Must not render')
    assert dp._document_slot.acquire(blocking=False)
    dp._document_slot.release() # Only test's own semaphore acquisition; no renderer/session cleanup.


def test_inaccessible_process_accounting_fails_closed(monkeypatch):
    monkeypatch.setattr(Path,'iterdir',lambda _:iter([Path('/proc/1')]))
    def denied(_):raise PermissionError('synthetic')
    monkeypatch.setattr(dp,'proc_info',denied)
    with pytest.raises(dp.ContainmentError,match='accounting denied'):dp.descendants(1)


def test_clean_shutdown_checks_resources_and_exit(monkeypatch):
    calls=[]
    monkeypatch.setattr(dp.os,'waitpid',lambda *_:(19,0))
    dp.wait_clean_exit(19,dp.time.monotonic()+5,lambda:calls.append('accounted'))
    assert calls==['accounted']


def test_crash_during_shutdown_not_success(monkeypatch):
    monkeypatch.setattr(dp.os,'waitpid',lambda *_:(19,9))
    with pytest.raises(dp.ContainmentError,match='crashed'):dp.wait_clean_exit(19,dp.time.monotonic()+5,lambda:None)


def test_live_child_shutdown_timeout(monkeypatch):
    ticks=iter([0,0,6])
    monkeypatch.setattr(dp.time,'monotonic',lambda:next(ticks))
    monkeypatch.setattr(dp.time,'sleep',lambda _:None)
    monkeypatch.setattr(dp.os,'waitpid',lambda *_:(0,0))
    with pytest.raises(dp.ContainmentError,match='incomplete'):dp.wait_clean_exit(19,10,lambda:None)


def test_shutdown_accounting_failure_propagates(monkeypatch):
    monkeypatch.setattr(dp.os,'waitpid',lambda *_:pytest.fail('Must check bounds before accepting exit'))
    def failed():raise dp.ContainmentError('memory')
    with pytest.raises(dp.ContainmentError,match='memory'):dp.wait_clean_exit(19,dp.time.monotonic()+5,failed)


def test_recycled_group_identity_never_signals(monkeypatch):
    monkeypatch.setattr(dp,'proc_info',lambda _:dict(start=999))
    monkeypatch.setattr(dp.os,'killpg',lambda *_:pytest.fail('Recycled group must not be signalled'))
    with pytest.raises(dp.ContainmentError,match='identity changed'):
        dp.signal_owned_group(dict(group_host=22,group_start=100,group=22))


def test_response_cannot_cross_cdp_sessions():
    relay=dp.Relay();relay.accept(0,frame({'id':1,'method':'Fetch.enable','sessionId':'A'}))
    with pytest.raises(dp.ContainmentError,match='Mismatched'):
        relay.accept(1,frame({'id':1,'result':{},'sessionId':'B'}))


def test_combined_queue_bound():
    relay=dp.Relay();payload='x'*(24*1024*1024)
    for key in (1,2):relay.accept(0,frame({'id':key,'method':'Fixture','params':{'body':payload}}))
    with pytest.raises(dp.ContainmentError,match='queue bound'):
        relay.accept(0,frame({'id':3,'method':'Fixture','params':{'body':payload}}))


def test_owned_cleanup_refuses_arbitrary_directory(tmp_path):
    directory=tmp_path/'process';directory.mkdir()
    with pytest.raises(dp.ContainmentError,match='ownership invalid'):
        dp.remove_owned_job(directory,dict(remove_on_parent_loss=True,job='1'*32))
    assert tmp_path.exists()

@pytest.mark.parametrize('script,match',[
    ('import time;time.sleep(30)','did not finish'),
    ('import os,time;os.write(1,b"x"*8192);time.sleep(30)','exceeded bound'),
    ('import os,time;os.write(2,b"x"*8192);time.sleep(30)','exceeded bound'),
])
def test_custodian_fault_is_reaped_and_pipes_closed(script,match):
    import subprocess,sys
    child=subprocess.Popen([sys.executable,'-I','-c',script],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    with pytest.raises(dp.ContainmentError,match=match):dp.collect_custodian(child)
    assert child.poll() is not None
    assert all(stream.closed for stream in (child.stdin,child.stdout,child.stderr))


def test_cleanup_postcondition_quarantines_retained_files(tmp_path):
    import io
    process=SimpleNamespace(poll=lambda:0,stdin=io.BytesIO(),stdout=io.BytesIO(),stderr=io.BytesIO())
    for stream in (process.stdin,process.stdout,process.stderr):stream.close()
    with pytest.raises(dp.ContainmentError,match='files remain; capacity quarantined'):
        dp.verify_cleanup(tmp_path/'process',None,process,[])


def test_cleanup_postcondition_rejects_live_owner(tmp_path):
    process=SimpleNamespace(poll=lambda:None)
    with pytest.raises(dp.ContainmentError,match='Custodian or descriptors remain'):
        dp.verify_cleanup(tmp_path/'process',None,process,[])


def test_cleanup_postcondition_rejects_open_pipe(tmp_path):
    import io
    process=SimpleNamespace(poll=lambda:0,stdin=io.BytesIO(),stdout=io.BytesIO(),stderr=io.BytesIO())
    with pytest.raises(dp.ContainmentError,match='descriptors remain'):
        dp.verify_cleanup(tmp_path/'process',None,process,[])
    for stream in (process.stdin,process.stdout,process.stderr):stream.close()


def test_cleanup_postcondition_rejects_unreaped_guardian(tmp_path,monkeypatch):
    import io
    process=SimpleNamespace(poll=lambda:0,stdin=io.BytesIO(),stdout=io.BytesIO(),stderr=io.BytesIO())
    for stream in (process.stdin,process.stdout,process.stderr):stream.close()
    monkeypatch.setattr(dp,'proc_info',lambda _:dict(start=42,state='Z'))
    with pytest.raises(dp.ContainmentError,match='guardian remains'):
        dp.verify_cleanup(tmp_path/'absent'/'process',dict(guardian_host=99,guardian_start=42),process,[])
