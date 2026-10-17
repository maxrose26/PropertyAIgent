"""Native disposable process supervision; run outside network-denied wrapper."""
import json,os
from pathlib import Path
import pytest
from verification.ingestion_storage.storage_controller import canonical

def _supervisor_probe(pipe, raw, registration, aggregate_started):
    import os,time,subprocess,sys
    os.setsid()
    def emit(event,payload):
        pipe.send_bytes(canonical({'event':event,'payload':payload}))
        assert pipe.recv_bytes(16)==b'DURABLE'
    if registration['mode']=='success':
        emit('result',{'status':'STORAGE_SEQUENCE_VERIFIED_CLOSURE_PENDING'})
        emit('worker_closed',{'cleanup':'CLOSED'})
    elif registration['mode']=='orphan':
        subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'])
        emit('result',{'status':'STORAGE_SEQUENCE_VERIFIED_CLOSURE_PENDING'})
        emit('worker_closed',{'cleanup':'CLOSED'})
    else:
        emit('worker_ready',{'pid':os.getpid()})
        time.sleep(20)
    pipe.close()


@pytest.mark.parametrize('mode',['success','deadline','stop','orphan'])
def test_supervisor_closure_deadline_owner_stop_and_orphan_fence(monkeypatch,tmp_path,mode):
    from verification.ingestion_storage import storage_controller as c
    import os
    if int(Path('/proc/self/stat').read_text().split(' ',1)[0])!=os.getpid():
        pytest.skip('hosted native Linux process namespace required; local /proc differs')
    monkeypatch.setattr(c,'worker',_supervisor_probe)
    monkeypatch.setattr(c,'SUPERVISED_SECONDS',2.5)
    journal=c.Journal(tmp_path/mode,'a'*64)
    if mode=='stop':(journal.root/'STOP').touch()
    result=c.supervise('not-a-credential',{'mode':mode},journal)
    journal.close()
    assert result['elapsed_seconds']<2.5
    if mode=='success':assert result['status']=='STORAGE_ACCEPTED_ACCESS_DISABLED' and result['cleanup']=='CLOSED'
    else:assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['cleanup']=='UNCERTAIN'
    if mode=='deadline':assert result['reason']=='SUPERVISED_DEADLINE'
    if mode=='stop':assert result['reason']=='OWNER_STOP'

