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
    for _ in range(3): b.before('connect')
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
    assert b.storage_commands==40 and b.commands==54
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
        consumed_controller_sha256=c.CONSUMED_CONTROLLER_BINDING,
        memory_enforcement='CGROUP_V2_FROM_EXEC_256M_SWAP_ZERO',
        prior_audit_sha256=c.PRIOR_AUDIT_SHA256,
        prior_supervised_seconds=c.PRIOR_SUPERVISED_SECONDS,
        prior_export_reserved_bytes=c.PRIOR_EXPORT_RESERVED_BYTES,
        prior_attempts=c.PRIOR_ATTEMPTS,prior_connections=c.PRIOR_CONNECTIONS,
        prior_commands=c.PRIOR_COMMANDS,prior_db_active_seconds=c.PRIOR_DB_ACTIVE_SECONDS,
        prior_returned_bytes=c.PRIOR_RETURNED_BYTES,migration_flags=c.MIGRATION_FLAGS,
        expires_at=c.ORIGINAL_EXPIRY,
        hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in FILES})
    assert validate_registration(canonical(registration),'a'*40)==registration
    for key,value in [('controller',c.mapping.CONTROLLER),('roles',['unreviewed']),('limits',{}),
                      ('expires_at',(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()),
                      ('hashes',{p:'0'*64 for p in FILES})]:
        changed={**registration,key:value}
        with pytest.raises(Stop): validate_registration(canonical(changed),'a'*40)


def test_safe_failure_never_exports_raw_driver_message():
    from verification.ingestion_storage.storage_controller import safe_failure
    assert safe_failure(ValueError('postgresql://secret-credential'))=={'reason':'CONTROLLER_EXCEPTION','sqlstate':None}
    assert safe_failure(Stop('OWNER_STOP'))['reason']=='OWNER_STOP'


def test_production_transport_requires_explicit_password_no_fallback():
    from verification.ingestion_storage import storage_controller as c
    with pytest.raises(Stop,match='MIGRATION_PASSWORD_REQUIRED'):
        c.production_transport('postgresql://postgres.zcikcfgpblzuzpanpdqd@aws-0-eu-west-2.pooler.supabase.com:5432/postgres','127.0.0.1','not-opened')


def test_metadata_preflight_rejects_environment_and_existing_later_page_secret(monkeypatch):
    from verification.ingestion_storage import storage_controller as c
    for name in ('GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN','GH_DEBUG','PGSERVICE','PGSERVICEFILE','PGOPTIONS','PGPASSFILE','PGPASSWORD','PGSSLCERT','PGSSLKEY'):
        monkeypatch.delenv(name,raising=False)
    calls=[]
    def metadata(command,seconds=10):
        calls.append(command)
        if 'user' in command:return b'maxrose26\n'
        assert '--paginate' in command
        return b'UNRELATED\nINGESTION_WORKER_DATABASE_URL\n'
    monkeypatch.setattr(c,'metadata_command',metadata)
    with pytest.raises(Stop,match='OWNER_ACCESS_OR_PREEXISTING_SECRET'):c.local_preflight()
    assert len(calls)==2
    monkeypatch.setenv('GH_TOKEN','DISPOSABLE_TEST_SENTINEL')
    with pytest.raises(Stop,match='KEYRING_AUTH_REQUIRED'):c.local_preflight()


@pytest.mark.parametrize('index,value',[(0,'other'),(1,'other'),(2,True),(3,False),(4,False),(5,False),(3,1),(5,None)])
def test_migration_profile_records_safe_flags_then_denies_drift(index,value):
    from verification.ingestion_storage import storage_controller as c
    row=['postgres','postgres',False,True,True,True,*([True]*6)]
    row[index]=value
    class Cursor:
        def fetchone(self):return tuple(row)
    class Connection:
        def execute(self,statement):
            assert statement.lstrip().startswith('SELECT')
            return Cursor()
    events=[]
    with pytest.raises(Stop,match='MIGRATION_IDENTITY'):
        c.migration_gate(Connection(),lambda k,v:events.append((k,v)))
    assert events[0][0]=='migration_identity'
    assert events[0][1]['rolbypassrls']==(value if index==5 and type(value)is bool else None if index==5 else True)


@pytest.mark.parametrize('index',range(6,12))
def test_grouped_migration_prerequisites_deny_before_install(index):
    from verification.ingestion_storage import storage_controller as c
    row=['postgres','postgres',False,True,True,True,*([True]*6)];row[index]=False
    class Cursor:
        def fetchone(self):return tuple(row)
    class Connection:
        def execute(self,statement):return Cursor()
    events=[]
    with pytest.raises(Stop,match='MIGRATION_PREREQUISITES'):
        c.migration_gate(Connection(),lambda k,v:events.append((k,v)))
    assert False in events[0][1].values()


def test_migration_evidence_never_exports_unexpected_values():
    from verification.ingestion_storage import storage_controller as c
    sentinel='postgresql://SECRET_VALUE'
    class Connection:
        def execute(self,statement):return self
        def fetchone(self):return (sentinel,'postgres',False,True,True,True,*([True]*6))
    events=[]
    with pytest.raises(Stop):c.migration_gate(Connection(),lambda k,v:events.append(v))
    assert sentinel not in json.dumps(events)
