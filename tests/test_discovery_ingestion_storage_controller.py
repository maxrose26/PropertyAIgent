"""Pure controller fences; no production routes, credentials or network."""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
import pytest
from verification.ingestion_storage.storage_controller import Budget,Journal,Stop,split_sql,FILES,validate_registration,canonical


def test_sql_boundaries_preserve_every_reviewed_statement():
    p=Path('docs/design/ingestion-provisioning-20261016')
    assert len(split_sql((p/'revoke.sql').read_text()))==8
    assert len(split_sql((p/'storage-readback.sql').read_text()))==6
    assert len(split_sql((p/'activate.sql').read_text()))==8
    statements=split_sql((p/'install.sql').read_text())
    assert len(statements)>40
    assert sum('CREATE FUNCTION' in s for s in statements)==2
    assert split_sql("SELECT ';'; DO $x$ BEGIN PERFORM ';'; END $x$; -- end")==["SELECT ';';", " DO $x$ BEGIN PERFORM ';'; END $x$;"]
    with pytest.raises(Stop): split_sql('SELECT 1')


def test_cumulative_limits_and_closure_reserves():
    now=[0.0];events=[]
    b=Budget(lambda *x:events.append(x),clock=lambda:now[0],started=0)
    for _ in range(4): b.before('connect')
    with pytest.raises(Stop,match='PROVISION_CONNECTION_LIMIT'): b.before('connect')
    b.enter('storage')
    for _ in range(8): b.before('connect')
    with pytest.raises(Stop): b.before('connect')
    for _ in range(40): b.before('command')
    with pytest.raises(Stop,match='STORAGE_COMMAND_LIMIT'): b.before('command')
    b.enter('teardown');b.before('connect')
    assert b.connections==13
    with pytest.raises(Stop,match='CONNECTION_LIMIT'): b.before('connect')
    for _ in range(10): b.before('command')
    with pytest.raises(Stop,match='TEARDOWN_COMMAND_LIMIT'): b.before('command')
    assert b.storage_commands==40 and b.commands==50
    b.phase_started=210;now[0]=238
    with pytest.raises(Stop,match='DEADLINE'):b.check()


def test_no_connection_stacking_and_storage_active_bound():
    now=[0.0];b=Budget(lambda *x:None,clock=lambda:now[0],started=0)
    b.open_connections=1
    with pytest.raises(Stop,match='CONNECTION_STACKING'):b.before('connect')
    b.open_connections=0;b.enter('storage');now[0]=30.1
    with pytest.raises(Stop,match='STORAGE_ACTIVE_LIMIT'):b.duration(0)


def test_journal_is_exclusive_durable_hash_chained_and_bounded(tmp_path):
    root=tmp_path/'once';j=Journal(root,'a'*64)
    j.append('checkpoint',{'phase':'installation','state':'INTENT'});j.close()
    previous='0'*64
    for index,line in enumerate((root/'events.jsonl').read_bytes().splitlines()):
        row=json.loads(line);digest=row.pop('sha256')
        assert row['sequence']==index and row['previous_sha256']==previous
        assert hashlib.sha256(canonical(row)).hexdigest()==digest;previous=digest
    with pytest.raises(FileExistsError):Journal(root,'a'*64)
    other=Journal(tmp_path/'bound','a'*64)
    with pytest.raises(Stop,match='AUDIT_BOUND'):other.append('oversize',{'data':'x'*17000})
    other.close()


def test_registration_rejects_expiry_scope_and_hash_drift():
    from verification.ingestion_storage import storage_controller as c
    registration=dict(authority=c.AUTHORITY,controller=c.CONTROLLER,risk_acceptance=c.mapping.RISK,
        roles=list(c.ROLE_NAMES),endpoint='aws-0-eu-west-2.pooler.supabase.com:5432/postgres',
        project='zcikcfgpblzuzpanpdqd',environment=c.mapping.ENVIRONMENT,
        method='CLIENT_GENERATED_SCRAM_SHA_256_MEMORY_TO_PROTECTED_SECRET',revision='a'*40,
        limits=c.LIMITS,retired_mapping_sha256=c.RETIRED_BINDING,
        expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
        hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in FILES})
    assert validate_registration(canonical(registration),'a'*40)==registration
    for key,value in [('controller',c.mapping.CONTROLLER),('roles',['unreviewed']),('limits',{}),
                      ('expires_at',(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()),
                      ('hashes',{p:'0'*64 for p in FILES})]:
        changed={**registration,key:value}
        with pytest.raises(Stop): validate_registration(canonical(changed),'a'*40)


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


def test_safe_failure_never_exports_raw_driver_message():
    from verification.ingestion_storage.storage_controller import safe_failure
    assert safe_failure(ValueError('postgresql://secret-credential'))=={'reason':'CONTROLLER_EXCEPTION','sqlstate':None}
    assert safe_failure(Stop('OWNER_STOP'))['reason']=='OWNER_STOP'
