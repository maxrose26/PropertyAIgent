"""Complete finite controller against fixed loopback PostgreSQL17 only.

Bootstrap creates/destroys fixture only. Installation uses non-superuser
CREATEROLE; storage checks authenticate as the two real restricted logins.
Only the protected secret-store boundary is mocked; no production access.
"""
import hashlib,json,os,secrets
from datetime import datetime,timezone,timedelta
from pathlib import Path
import psycopg
from psycopg import sql
import pytest
from tests.test_discovery_ingestion_memory_native import memory_group
from verification.ingestion_storage import storage_controller as c
ROLES=['ingestion_storage_owner','ingestion_storage_operator','ingestion_worker',
       'ingestion_authority_issuer','ingestion_barrier_releaser',*c.ROLE_NAMES]


@pytest.fixture
def fixture():
    raw=os.environ.get('INGESTION_PROVISIONING_TEST_URL')
    if not raw:pytest.skip('fixed disposable PostgreSQL17 required')
    info=psycopg.conninfo.conninfo_to_dict(raw)
    assert (info.get('host'),info.get('port'),info.get('dbname'),info.get('user'))==('127.0.0.1','5432','ingestion_provisioning_test','provisioning_bootstrap')
    password=secrets.token_urlsafe(48)
    with psycopg.connect(raw,autocommit=True,prepare_threshold=None) as boot:
        assert boot.info.server_version>=170000
        boot.execute('CREATE TABLE public.applications(id integer PRIMARY KEY,address text)')
        boot.execute("INSERT INTO public.applications VALUES(1504,'PRESERVED'),(1505,'PRESERVED'),(1506,'PRESERVED'),(1507,'PENDING'),(1508,'PENDING')")
        boot.execute(sql.SQL('CREATE ROLE provisioning_migrator LOGIN NOSUPERUSER NOCREATEDB CREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}').format(sql.Literal(password)))
        boot.execute('GRANT USAGE,CREATE ON SCHEMA public TO provisioning_migrator WITH GRANT OPTION')
        boot.execute('GRANT CONNECT ON DATABASE ingestion_provisioning_test TO provisioning_migrator WITH GRANT OPTION')
        def connect(role,credential):
            name='provisioning_migrator' if role=='migration' else role
            return psycopg.connect(**{**info,'user':name,'password':password if role=='migration' else credential},
                autocommit=True,connect_timeout=3,prepare_threshold=None)
        registration={'revision':'a'*40,'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
                      'hashes':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in c.FILES},
                      'authority':c.AUTHORITY,'risk_acceptance':c.mapping.RISK,'roles':list(c.ROLE_NAMES),
                      'endpoint':'aws-0-eu-west-2.pooler.supabase.com:5432/postgres','project':'zcikcfgpblzuzpanpdqd',
                      'environment':c.mapping.ENVIRONMENT,'method':'CLIENT_GENERATED_SCRAM_SHA_256_MEMORY_TO_PROTECTED_SECRET'}
        store={};secret_calls=[]
        def secret_operation(operation,name,value):
            secret_calls.append((operation,name))
            if operation=='set':store[name]=value
            elif operation=='delete':del store[name]
            elif operation=='verify_absent':assert not store
            else:raise AssertionError('unknown operation')
        try:yield boot,connect,registration,secret_operation,store,secret_calls
        finally:
            # Never a production rollback: test-only disposable data destruction.
            assert boot.execute('SELECT id,address FROM public.applications ORDER BY id').fetchall()==[(1504,'PRESERVED'),(1505,'PRESERVED'),(1506,'PRESERVED'),(1507,'PENDING'),(1508,'PENDING')]
            boot.execute('DROP TABLE IF EXISTS public.ingestion_work_attempts,public.ingestion_work_items CASCADE')
            boot.execute('DROP FUNCTION IF EXISTS public.ingestion_seed_storage_test(),public.ingestion_raise_stop(text)')
            for role in [*ROLES,'provisioning_migrator']:
                if boot.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():boot.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(role)))
            for role in [*ROLES,'provisioning_migrator']:boot.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(role)))
            boot.execute('DROP TABLE public.applications')


def test_complete_controller_real_logins_and_finite_accounting(fixture,tmp_path,record_property):
    boot,connect,registration,secrets_boundary,store,calls=fixture
    journal=c.Journal(tmp_path/'full-controller','b'*64)
    budget=c.execute_sequence(connect,secrets_boundary,registration,journal.append,migration_identity='provisioning_migrator')
    journal.close()
    assert budget.connections==7 and budget.storage_connections==4
    assert budget.storage_commands==40 and budget.teardown_commands==10
    assert budget.storage_active<30 and budget.clock()-budget.started<240
    assert not store and calls==[('set',c.SECRETS[0]),('set',c.SECRETS[1]),('delete',c.SECRETS[0]),('delete',c.SECRETS[1]),('verify_absent',None)]
    assert boot.execute('SELECT count(*) FROM public.ingestion_work_items').fetchone()==(4,)
    assert boot.execute('SELECT count(*) FROM public.ingestion_work_attempts').fetchone()==(0,)
    assert boot.execute("SELECT count(*) FROM pg_authid WHERE rolname=ANY(%s) AND NOT rolcanlogin AND rolpassword IS NULL",(list(c.ROLE_NAMES),)).fetchone()==(2,)
    for role in c.ROLE_NAMES:
        with pytest.raises(psycopg.OperationalError):connect(role,'disposable_wrong_password')
    record_property('controller_usage',json.dumps(budget.snapshot(),sort_keys=True))
    record_property('controller_audit_bytes',journal.bytes)
    record_property('controller_journal_sha256',hashlib.sha256((journal.root/'events.jsonl').read_bytes()).hexdigest())
    record_property('real_restricted_logins',2);record_property('denials_42501',8)
    record_property('applications_1504_1508_preserved',True)
    record_property('source_calls',0);record_property('production_connections',0)


@pytest.mark.parametrize('phase,state',[('installation','COMMITTED'),('mapping','MAPPED_NOLOGIN'),('first_seed','COMMITTED'),('revocation','INTENT')])
def test_interrupted_phase_preserved_no_following_effect(fixture,tmp_path,phase,state):
    boot,connect,registration,secrets_boundary,store,calls=fixture
    journal=c.Journal(tmp_path/'interrupted-controller','b'*64)
    def interrupt(p,s):
        if (p,s)==(phase,state):raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):c.execute_sequence(connect,secrets_boundary,registration,journal.append,fault=interrupt,migration_identity='provisioning_migrator')
    journal.close()
    entries=[json.loads(x) for x in (journal.root/'events.jsonl').read_text().splitlines()]
    assert entries[-1]['event']=='stop'
    assert not any(x[0]=='delete' for x in calls)
    if phase=='installation':assert not store
    if phase in ('first_seed','revocation'):assert boot.execute('SELECT count(*) FROM public.ingestion_work_items').fetchone()==(4,)
    assert boot.execute('SELECT count(*) FROM public.ingestion_work_attempts').fetchone()==(0,)
    with pytest.raises(FileExistsError):c.Journal(journal.root,'b'*64)


@pytest.mark.parametrize('operation',['set','delete'])
def test_uncertain_secret_store_stops_without_compensation(fixture,tmp_path,operation):
    boot,connect,registration,secrets_boundary,store,calls=fixture
    journal=c.Journal(tmp_path/'secret-uncertain','b'*64)
    def ambiguous(op,name,value):
        secrets_boundary(op,name,value)
        if op==operation:raise TimeoutError('disposable acknowledgement lost')
    with pytest.raises(TimeoutError):c.execute_sequence(connect,ambiguous,registration,journal.append,migration_identity='provisioning_migrator')
    journal.close()
    if operation=='set':
        assert calls==[('set',c.SECRETS[0])]
        assert boot.execute('SELECT rolcanlogin FROM pg_roles WHERE rolname=ANY(%s)',(list(c.ROLE_NAMES),)).fetchall()==[(False,),(False,)]
    else:
        assert calls==[('set',c.SECRETS[0]),('set',c.SECRETS[1]),('delete',c.SECRETS[0])]
        assert boot.execute('SELECT rolcanlogin FROM pg_roles WHERE rolname=ANY(%s)',(list(c.ROLE_NAMES),)).fetchall()==[(False,),(False,)]
    events=[json.loads(line) for line in (journal.root/'events.jsonl').read_text().splitlines()]
    assert events[-1]['event']=='stop'
    intent=[e for e in events if e['event']=='effect_intent'][-1]
    assert intent['payload']['effect']=='secret_'+operation
    assert not any(e['event']=='effect_ack' and e['sequence']>intent['sequence'] for e in events)


def test_unknown_install_commit_prevents_mapping(fixture,tmp_path):
    boot,connect,registration,secrets_boundary,store,calls=fixture
    class LostAck:
        def __init__(self,native):self.native=native
        def __getattr__(self,key):return getattr(self.native,key)
        def execute(self,statement,params=None):
            result=self.native.execute(statement,params)
            if isinstance(statement,str) and statement.strip()=='COMMIT;':raise psycopg.OperationalError('disposable commit acknowledgement lost')
            return result
    journal=c.Journal(tmp_path/'commit-uncertain','b'*64)
    with pytest.raises(psycopg.OperationalError):c.execute_sequence(lambda role,pw:LostAck(connect(role,pw)),secrets_boundary,registration,journal.append,migration_identity='provisioning_migrator')
    journal.close()
    assert not calls and not store
    assert boot.execute('SELECT count(*) FROM public.ingestion_work_items').fetchone()==(1,)
    assert boot.execute('SELECT count(*) FROM public.ingestion_work_attempts').fetchone()==(0,)


def test_process_death_leaves_durable_seed_checkpoint_and_no_replay(fixture,tmp_path):
    boot,connect,registration,secrets_boundary,store,calls=fixture
    # Parent fixture connection must not be used by child; child opens fresh
    # non-superuser/restricted clients through the exact coordinator.
    root=tmp_path/'process-death';pid=os.fork()
    if pid==0:
        journal=c.Journal(root,'b'*64)
        def crash(phase,state):
            if (phase,state)==('first_seed','COMMITTED'):os._exit(19)
        try:c.execute_sequence(connect,secrets_boundary,registration,journal.append,fault=crash,migration_identity='provisioning_migrator')
        finally:os._exit(20)
    _,status=os.waitpid(pid,0)
    assert os.waitstatus_to_exitcode(status)==19
    events=[json.loads(line) for line in (root/'events.jsonl').read_text().splitlines()]
    assert events[-1]['event']=='checkpoint' and events[-1]['payload']['phase']=='first_seed' and events[-1]['payload']['state']=='COMMITTED'
    assert boot.execute('SELECT count(*) FROM public.ingestion_work_items').fetchone()==(4,)
    assert boot.execute('SELECT count(*) FROM public.ingestion_work_attempts').fetchone()==(0,)
    with pytest.raises(FileExistsError):c.Journal(root,'b'*64)


def test_uncertain_revocation_commit_does_not_delete_secrets(fixture,tmp_path):
    boot,connect,registration,secrets_boundary,store,calls=fixture
    class LostRevocation:
        def __init__(self,native):self.native=native;self.revoking=False
        def __getattr__(self,key):return getattr(self.native,key)
        def execute(self,statement,params=None):
            if isinstance(statement,str) and 'ALTER ROLE ingestion_worker_login NOLOGIN PASSWORD NULL' in statement:self.revoking=True
            result=self.native.execute(statement,params)
            if self.revoking and isinstance(statement,str) and statement.strip()=='COMMIT;':raise psycopg.OperationalError('disposable revocation acknowledgement lost')
            return result
    journal=c.Journal(tmp_path/'revocation-uncertain','b'*64)
    with pytest.raises(psycopg.OperationalError):c.execute_sequence(lambda role,pw:LostRevocation(connect(role,pw)),secrets_boundary,registration,journal.append,migration_identity='provisioning_migrator')
    journal.close()
    assert calls==[('set',c.SECRETS[0]),('set',c.SECRETS[1])]
    assert len(store)==2 and boot.execute('SELECT count(*) FROM public.ingestion_work_items').fetchone()==(4,)
    events=[json.loads(line) for line in (journal.root/'events.jsonl').read_text().splitlines()]
    assert not any(e['event']=='checkpoint' and e['payload']['phase']=='revocation' and e['payload']['state']=='VERIFIED' for e in events)


def test_supervised_complete_postgres_path(fixture,tmp_path,monkeypatch,record_property,memory_group):
    boot,connect,registration,secrets_boundary,store,calls=fixture
    # Exercise the real worker process, resource limits, private pipe protocol
    # and supervisor. Only source-free fixture transport/secret boundaries and
    # fixed fixture principal differ; no production DNS/GitHub/DB is contacted.
    real_sequence=c.execute_sequence
    def fixture_sequence(*args,**kwargs):
        return real_sequence(*args,**kwargs,migration_identity='provisioning_migrator')
    monkeypatch.setattr(c,'execute_sequence',fixture_sequence)
    monkeypatch.setattr(c,'local_preflight',lambda:None)
    monkeypatch.setattr(c,'production_transport',lambda raw,address,root:connect)
    monkeypatch.setattr(c,'production_secrets',secrets_boundary)
    monkeypatch.setattr(c.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',5432))])
    journal=c.Journal(tmp_path/'supervised-controller','b'*64)
    result=c.supervise('postgresql://postgres.zcikcfgpblzuzpanpdqd:DISPOSABLE_FIXTURE_ONLY@aws-0-eu-west-2.pooler.supabase.com:5432/postgres',registration,journal)
    journal.close()
    assert result['status']=='STORAGE_ACCEPTED_ACCESS_DISABLED' and result['cleanup']=='CLOSED'
    assert boot.execute('SELECT count(*) FROM public.ingestion_work_items').fetchone()==(4,)
    assert boot.execute('SELECT count(*) FROM public.ingestion_work_attempts').fetchone()==(0,)
    assert boot.execute("SELECT count(*) FROM pg_authid WHERE rolname=ANY(%s) AND NOT rolcanlogin AND rolpassword IS NULL",(list(c.ROLE_NAMES),)).fetchone()==(2,)
    record_property('supervised_controller_result',json.dumps(result,sort_keys=True))
