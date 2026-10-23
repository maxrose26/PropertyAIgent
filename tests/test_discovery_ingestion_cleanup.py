import json,subprocess,time
from pathlib import Path
from types import SimpleNamespace
import pytest
from verification.ingestion_storage.operational_cleanup import Cleanup,Journal,Stop,SECRETS,SECRET_PATH

def test_journal_once_bound_and_chain(tmp_path):
    from verification.ingestion_storage.operational_cleanup import digest
    j=Journal(tmp_path/'once');j.emit('consumed',{'scope':'cleanup_only'})
    with pytest.raises(FileExistsError):Journal(j.root)
    row=json.loads(j.file.read_bytes());sha=row.pop('sha256')
    assert digest(row)==sha and row['sequence']==0 and row['previous_sha256']=='0'*64
    result=j.save({'cleanup':'UNCERTAIN'});assert result['exported_bytes']<524288

def test_uncertain_delete_stops_without_next_request(tmp_path):
    calls=[]
    def lost(command,**kwargs):calls.append(command);raise subprocess.TimeoutExpired(command,1)
    worker=Cleanup(lambda:None,Journal(tmp_path/'lost'),github_runner=lost)
    with pytest.raises(Stop,match='GITHUB_ACK_UNCERTAIN'):worker.api('DELETE',SECRET_PATH+'/'+SECRETS[0])
    assert worker.deletes==1 and len(calls)==1 and worker.secret_deletions==[]

def test_limits_and_complete_names_are_fail_closed(tmp_path):
    worker=Cleanup(lambda:None,Journal(tmp_path/'bounds'),github_runner=lambda *a,**k:SimpleNamespace(returncode=0,stdout=b'{"total_count":2,"secrets":[{"name":"DATABASE_URL"}]}',stderr=b''))
    with pytest.raises(Stop,match='INCOMPLETE_SECRET_NAMES'):worker.names()
    with pytest.raises(Stop,match='EXACT_DELETE_BOUND'):worker.api('DELETE',SECRET_PATH+'/DATABASE_URL')
    worker.commands=32
    with pytest.raises(Stop,match='COMMAND_BOUND'):worker.q(None,'blocked','SELECT 1')
    worker.connections=2
    with pytest.raises(Stop,match='CONNECTION_BOUND'):
        with worker.connection():pass
    assert worker.deletes==0

def test_returned_value_cap_stops_before_next_effect(tmp_path):
    class PG:
        ntuples=1;nfields=1
        def get_value(self,*a):return b'x'*(1048576+1)
    c=SimpleNamespace(execute=lambda *a:SimpleNamespace(pgresult=PG()))
    worker=Cleanup(lambda:None,Journal(tmp_path/'bytes'))
    with pytest.raises(Stop,match='RETURNED_DATA_VALUE_BOUND'):worker.q(c,'read','SELECT retained_state')
    assert worker.commands==1 and worker.returned==1048577

def test_no_new_authorities_credentials_or_effect_routes():
    import inspect
    from verification.ingestion_storage import operational_cleanup as module
    source=inspect.getsource(module)
    assert 'secret\',\'set' not in source and 'CREATE ROLE ' not in source
    assert 'pg_terminate_backend' not in source and 'ingestion_worker_step(' not in source
    assert 'source_reader' not in source and 'verify-full' in source

def test_expiry_after_startup_blocks_next_database_and_secret_effect(tmp_path):
    from datetime import datetime,timezone,timedelta
    called=[]
    worker=Cleanup(lambda:called.append('connect'),Journal(tmp_path/'expiry'),
        github_runner=lambda *a,**k:called.append('github'),expiry=datetime.now(timezone.utc)-timedelta(seconds=1))
    with pytest.raises(Stop,match='CLEANUP_EXPIRED'):worker.q(None,'blocked','ALTER ROLE ingestion_worker_login NOLOGIN',effect=True)
    with pytest.raises(Stop,match='CLEANUP_EXPIRED'):worker.api('DELETE',SECRET_PATH+'/'+SECRETS[0])
    assert not called and worker.commands==worker.deletes==0

def test_delayed_input_does_not_spend_active_budget_or_permit_effects(tmp_path):
    from datetime import datetime,timezone,timedelta
    from verification.ingestion_storage.operational_cleanup import run_session
    calls=[];printed=[];j=Journal(tmp_path/'delayed')
    def reader():
        time.sleep(.08);assert not calls;return 'hidden-fixture-value'
    def prepare(value,started):
        assert time.monotonic()-started<.03
        calls.append('prepare');raise Stop('DISPOSABLE_BEFORE_EFFECTS')
    result=run_session(j,None,datetime.now(timezone.utc)+timedelta(minutes=1),reader,prepare,
        timing=dict(credential_input_seconds=.2,active_seconds=.1,work_seconds=.05,outer_seconds=1),
        output=lambda line,**_:printed.append(json.loads(line)))
    assert result['phase_timing']['credential_input_seconds']>=.08 and calls==['prepare']
    assert result['accounting']['connections']==result['accounting']['commands']==result['accounting']['deletes']==0
    assert len(printed)==1 and json.loads((j.root/'final-result.json').read_bytes())==result
    terminal=json.dumps(printed[0],sort_keys=True)+'\n'
    assert printed[0]['terminal_json_bytes']==len(terminal.encode())
    assert printed[0]['exported_bytes']==printed[0]['persisted_evidence_bytes']+len(terminal.encode())
    assert 'hidden-fixture-value' not in j.file.read_text()

def test_input_timeout_saves_and_displays_without_connecting(tmp_path):
    from datetime import datetime,timezone,timedelta
    from verification.ingestion_storage.operational_cleanup import run_session
    calls=[];printed=[];j=Journal(tmp_path/'input-timeout')
    result=run_session(j,None,datetime.now(timezone.utc)+timedelta(minutes=1),lambda:time.sleep(1),
        lambda *_:calls.append('forbidden'),
        timing=dict(credential_input_seconds=.03,active_seconds=.2,work_seconds=.1,outer_seconds=1),
        output=lambda line,**_:printed.append(json.loads(line)))
    assert not calls and result['reason']=='SECURE_INPUT_DEADLINE' and len(printed)==1
    assert result['phase']=='SECURE_CREDENTIAL_INPUT' and result['database_commit']=='NOT_ATTEMPTED'
    assert result['accounting']['connections']==result['accounting']['names_reads']==0
    assert json.loads((j.root/'final-result.json').read_bytes())==result

def test_expiry_during_input_never_prepares_worker(tmp_path):
    from datetime import datetime,timezone,timedelta
    from verification.ingestion_storage.operational_cleanup import run_session
    calls=[]
    result=run_session(Journal(tmp_path/'input-expiry'),None,datetime.now(timezone.utc)+timedelta(seconds=.01),
        lambda:time.sleep(.03),lambda *_:calls.append('forbidden'),output=lambda *_a,**_k:None)
    assert not calls and result['reason']=='CLEANUP_EXPIRED'

def test_finalisation_deadline_has_bounded_fallback_without_second_exception(tmp_path):
    from verification.ingestion_storage.operational_cleanup import finalise,zero_accounting
    class LateJournal:
        file=tmp_path/'events.jsonl'
        def save(self,_):raise Stop('FINALISATION_DEADLINE')
    printed=[]
    result=finalise(LateJournal(),{'status':'STOP_RECONCILE_NO_RETRY','accounting':zero_accounting()},
        outer_started=time.monotonic(),active_started=None,input_seconds=.1,
        output=lambda line,**_:printed.append(json.loads(line)))
    assert result['reason']=='FINAL_EVIDENCE_OR_OUTPUT_UNCERTAIN' and len(printed)==1

def deadline_child(tmp_path,name,script,timeout=10):
    """Run a deadline-bearing session in a child, as the neighbouring tests do, so its hard deadline
    (os._exit(124)) cannot terminate pytest. A timeout, any non-zero exit, a traceback or a missing
    receipt fails the calling test; it is never treated as the session's result."""
    import sys
    try:
        child=subprocess.run([sys.executable,'-B','-c',script,str(tmp_path/name)],capture_output=True,timeout=timeout)
    except subprocess.TimeoutExpired:
        pytest.fail('DEADLINE_CHILD_TIMEOUT')
    if child.returncode!=0:pytest.fail(f'DEADLINE_CHILD_EXIT_{child.returncode}')
    if b'Traceback' in child.stderr:pytest.fail('DEADLINE_CHILD_TRACEBACK')
    receipt=tmp_path/name/'final-result.json'
    if not receipt.is_file():pytest.fail('DEADLINE_CHILD_RECEIPT_MISSING')
    return json.loads(child.stdout),json.loads(receipt.read_bytes())

ACTIVE_DEADLINE_SESSION='''
import json,sys,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
from verification.ingestion_storage.operational_cleanup import Journal,run_session
printed=[]
def prepare(*_):time.sleep(1)
result=run_session(Journal(Path(sys.argv[1])),None,datetime.now(timezone.utc)+timedelta(minutes=1),
    lambda:'fixture',prepare,timing=dict(credential_input_seconds=.1,active_seconds=.2,work_seconds=.03,outer_seconds=1),
    output=lambda line,**_:printed.append(json.loads(line)))
sys.stdout.write(json.dumps(dict(result=result,printed=printed)))
'''

def test_active_deadline_reserves_finalisation_and_exports_complete_zeros(tmp_path):
    value,receipt=deadline_child(tmp_path,'active-timeout',ACTIVE_DEADLINE_SESSION)
    result,printed=value['result'],value['printed']
    assert result['reason']=='ACTIVE_WORK_DEADLINE' and len(printed)==1
    assert result['accounting']['connections']==result['accounting']['commands']==0
    assert receipt['reason']=='ACTIVE_WORK_DEADLINE'

@pytest.mark.parametrize('ending,code',[
    ('import os;os._exit(124)','DEADLINE_CHILD_EXIT_124'),        # hard deadline fired in the child
    ('import os;os._exit(0)','DEADLINE_CHILD_RECEIPT_MISSING'),    # clean exit without a receipt
    ('raise RuntimeError("x")','DEADLINE_CHILD_EXIT_1'),           # unexpected exception
    ('import time;time.sleep(30)','DEADLINE_CHILD_TIMEOUT')])      # child never finishes
def test_deadline_child_unexpected_termination_never_passes(tmp_path,ending,code):
    with pytest.raises(pytest.fail.Exception,match=code):
        deadline_child(tmp_path,'unexpected',ending,timeout=2)

@pytest.mark.parametrize('provide_input',[True,False])
def test_real_hidden_tty_delayed_input_and_timeout(tmp_path,provide_input):
    import os,pty,select,sys,errno
    from datetime import datetime,timezone
    script='''
import json,sys
from pathlib import Path
from datetime import datetime,timezone,timedelta
from verification.ingestion_storage.operational_cleanup import Journal,Stop,run_session
from verification.ingestion_storage.credential_mapping import secure_migration_input
def prepare(*_):raise Stop('DISPOSABLE_INPUT_COMPLETE')
run_session(Journal(Path(sys.argv[1])),None,datetime.now(timezone.utc)+timedelta(minutes=1),
    secure_migration_input,prepare,timing=dict(credential_input_seconds=.5,active_seconds=.5,work_seconds=.2,outer_seconds=2))
'''
    master,slave=pty.openpty()
    def tty():
        import fcntl,termios
        os.setsid();fcntl.ioctl(0,termios.TIOCSCTTY,0)
    child=subprocess.Popen([sys.executable,'-B','-c',script,str(tmp_path/'tty-once')],
        stdin=slave,stdout=slave,stderr=slave,preexec_fn=tty)
    os.close(slave);raw=bytearray();sent=False;deadline=time.monotonic()+5
    try:
        while time.monotonic()<deadline:
            ready,_,_=select.select([master],[],[],.02)
            if ready:
                try:b=os.read(master,4096)
                except OSError as exc:
                    if exc.errno==errno.EIO:break
                    raise
                if not b:break
                raw.extend(b);assert len(raw)<16384
                if provide_input and not sent and b'never paste into chat' in raw:
                    time.sleep(.1);os.write(master,b'disposable-hidden-tty-value\n');sent=True
        assert child.wait(timeout=1)==0
    finally:
        if child.poll() is None:child.kill();child.wait(timeout=1)
        os.close(master)
    result=json.loads((tmp_path/'tty-once/final-result.json').read_bytes())
    assert result['reason']==('DISPOSABLE_INPUT_COMPLETE' if provide_input else 'SECURE_INPUT_DEADLINE')
    assert b'disposable-hidden-tty-value' not in raw and b'Traceback' not in raw
    assert b'"status": "STOP_RECONCILE_NO_RETRY"' in raw
    assert result['accounting']['connections']==result['accounting']['deletes']==0

def test_blocked_final_output_cannot_extend_active_deadline(tmp_path):
    import sys
    script='''
import sys,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
from verification.ingestion_storage.operational_cleanup import Journal,Stop,run_session
def prepare(*_):raise Stop('DISPOSABLE_BEFORE_EFFECTS')
def output(*_a,**_k):time.sleep(10)
run_session(Journal(Path(sys.argv[1])),None,datetime.now(timezone.utc)+timedelta(minutes=1),
    lambda:'fixture',prepare,timing=dict(credential_input_seconds=.2,active_seconds=.2,work_seconds=.05,outer_seconds=2),output=output)
'''
    result=subprocess.run([sys.executable,'-B','-c',script,str(tmp_path/'blocked-output')],
        capture_output=True,timeout=3)
    assert result.returncode==124 and b'Traceback' not in result.stderr

