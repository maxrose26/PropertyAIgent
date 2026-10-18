"""Focused cleanup of accepted-storage/failed-setup fixture, no source calls."""
from copy import deepcopy
from datetime import datetime
import json,os,secrets,subprocess,time
from datetime import timedelta,timezone
from pathlib import Path
import psycopg,pytest
from psycopg import sql
from tests.storage_gh_fixture import real_gh_store
from verification.ingestion_storage.operational_cleanup import (Cleanup,Journal,Stop,Memory,ROLES,
    CAPTURE_KEY,CAPTURE_AUTHORITY,GRANT_SHA256,REVISION,SECRETS,digest,run_session)

def grant_fixture():
    from verification.ingestion_storage.operational_owner import item,SCOPE
    from app.ingestion.ledger import DEFAULT_LIMITS
    manifest='8d9c2028bbe3c0af93122d6e35a917a87c87fa1600186098d855c167ffb12ca3'
    root=item(dict(subject=SCOPE,task='DISCOVERY',contract='bolton-received-idox-coordinator-v1',revision=manifest),max_attempts=1,limits=dict(DEFAULT_LIMITS,requests=10,bytes=3000000,rows=60,pages=6))
    assert root['key']==CAPTURE_KEY
    binding={root['key']:{k:root[k] for k in ('subject','task','contract','revision')}}
    execution=dict(revision=REVISION,workflow_sha256='2ee4ceb436b8e26cfd4c31fedf6fb4a21f67bb3627da04e8f7868c7dfdea626c',manifest_sha256=manifest)
    g=dict(keys=sorted(binding),contracts=['bolton-received-idox-coordinator-v1'],expires_at=datetime.fromisoformat('2026-10-18T22:00:00+00:00').timestamp(),source_calls=1,writes=0,login='ingestion_worker_login',effect_login='ingestion_effect_login',workers=['required_once'],bindings=binding,detail_source_keys=[],capture_key=CAPTURE_KEY,capture_only=True,execution_binding=execution,
           completion_outcomes={'DISCOVERY':['ENUMERATED_METADATA_RETAINED'],'LISTING_METADATA':['BATCH_SCREENED'],'SCREENING':['SCREENED','ALREADY_KNOWN','INSUFFICIENT_EVIDENCE','SUPPORTED_PROCESSING_PRIORITY','RELATED_APPLICATION_FOLLOW_THROUGH','DEEPER_PROCESSING_EXCLUDED_FOR_THIS_SLICE']})
    assert digest(g)==GRANT_SHA256
    e=dict(authority=CAPTURE_AUTHORITY,transport='REQUESTS_IDOX',grant_binding={k:v for k,v in g.items() if k not in {'source_calls','writes'}},stop_checkpoint_sha256='a2345cf136fc92abf13bb55772f5c14a7a299b7f2b9cb0b89fe6037ccdb8a10e',expires_at=g['expires_at'],**execution)
    return root,g,e

@pytest.mark.parametrize('real_gh_store',['operational'],indirect=True)
@pytest.mark.parametrize('fault',['success','changed_grant','connection_failure','commit_lost_ack','delete_lost_ack','associated_session'])
def test_revoke_only_non_superuser_native_cleanup(tmp_path,record_property,real_gh_store,fault):
    raw=os.environ.get('INGESTION_PROVISIONING_TEST_URL')
    if not raw:pytest.skip('disposable PostgreSQL17 required')
    info=psycopg.conninfo.conninfo_to_dict(raw)
    assert (info['host'],info['port'],info['dbname'],info['user'])==('127.0.0.1','5432','ingestion_provisioning_test','provisioning_bootstrap')
    metadata,_,ciphertexts,requests=real_gh_store
    for name in SECRETS:ciphertexts[name]=b'disposable-existing-placeholder'
    password=secrets.token_urlsafe(48);role='cleanup_migrator'
    def connect():return psycopg.connect(**{**info,'user':role,'password':password},autocommit=True,connect_timeout=3,prepare_threshold=None)
    from tests.test_discovery_ingestion_provisioning_pg import ROLES as base_roles,PACKAGE
    extra=['ingestion_effect_login','ingestion_effect_broker','ingestion_recovery_operator']
    with psycopg.connect(raw,autocommit=True) as boot:
        boot.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER CREATEROLE CREATEDB BYPASSRLS NOINHERIT PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
        boot.execute(sql.SQL('GRANT USAGE,CREATE ON SCHEMA public TO {} WITH GRANT OPTION').format(sql.Identifier(role)))
        boot.execute(sql.SQL('GRANT CONNECT ON DATABASE ingestion_provisioning_test TO {} WITH GRANT OPTION').format(sql.Identifier(role)))
        boot.execute(sql.SQL('GRANT SELECT(rolname,rolpassword) ON pg_catalog.pg_authid TO {}').format(sql.Identifier(role)))
        held=None
        try:
            # Fixture only: represent already accepted storage and its retained
            # three blocked records. No storage acceptance suite is repeated.
            with connect() as c:
                c.execute((PACKAGE/'install.sql').read_text())
                c.execute('REVOKE ingestion_worker FROM ingestion_worker_login')
                c.execute('REVOKE ingestion_storage_operator FROM ingestion_storage_login')
                c.execute(Path('docs/design/ingestion-operational-20261016/worker.sql').read_text())
                c.execute("CREATE ROLE ingestion_effect_login LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS NOREPLICATION CONNECTION LIMIT 1 PASSWORD 'disposable-only'")
                c.execute("ALTER ROLE ingestion_worker_login LOGIN PASSWORD 'disposable-only'")
                c.execute('GRANT ingestion_worker TO ingestion_worker_login WITH ADMIN FALSE, INHERIT TRUE, SET FALSE')
                c.execute('GRANT ingestion_effect_broker TO ingestion_effect_login WITH ADMIN FALSE, INHERIT TRUE, SET FALSE')
            boot.execute('SELECT public.ingestion_seed_storage_test()')
            root,g,e=grant_fixture()
            if fault=='changed_grant':g=deepcopy(g);g['source_calls']=0
            ctl={'global_stop':{'reason':'CONSUMED_SALFORD_GLOBAL_STOP','run':'38884069913'},'manual_stop':'STORAGE_TEST_STOP','grants':{CAPTURE_AUTHORITY:g},'bolton_exceptions':{CAPTURE_AUTHORITY:e}}
            boot.execute('INSERT INTO public.ingestion_work_items SELECT * FROM json_populate_record(NULL::public.ingestion_work_items,%s::json)',(json.dumps(root),))
            boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
            if fault=='associated_session':
                held=psycopg.connect(**{**info,'user':'ingestion_worker_login','password':'disposable-only'},autocommit=True)
            injected=[]
            class Connection:
                def __init__(self):
                    if fault=='connection_failure':
                        # Real failed PostgreSQL handshake, disposable login only.
                        # This chosen fixture failure says nothing about the
                        # historical production connection's unknown cause.
                        psycopg.connect(**{**info,'user':role,'password':'disposable-intentionally-wrong'},
                            autocommit=True,connect_timeout=3,prepare_threshold=None)
                        raise AssertionError('DISPOSABLE_BAD_PASSWORD_WAS_ACCEPTED')
                    self.c=connect()
                @property
                def closed(self):return self.c.closed
                def close(self):self.c.close()
                def execute(self,statement,params=None):
                    result=self.c.execute(statement,params)
                    if fault=='commit_lost_ack' and statement=='COMMIT' and not injected:
                        injected.append(True);raise psycopg.OperationalError('DISPOSABLE_ACK_LOST')
                    return result
            def cli(command,**kwargs):
                result=metadata.cli(command,**kwargs)
                if fault=='delete_lost_ack' and '--method' in command and command[command.index('--method')+1]=='DELETE' and not injected:
                    injected.append(True);raise subprocess.TimeoutExpired(['gh','DISPOSABLE_ACK_LOSS'],1)
                return result
            memory=Memory() if os.environ.get('INGESTION_CLEANUP_NATIVE')=='1' else None
            journal=Journal(tmp_path/'cleanup-once');holder=[]
            def reader():
                count=len(requests)
                time.sleep(.04)
                assert len(requests)==count and not holder
                return 'disposable-input-never-exported'
            def prepare(credential,started):
                worker=Cleanup(Connection,journal,github_runner=cli,identity=role,memory=memory,started=started)
                holder.append(worker);return worker
            result=run_session(journal,memory,datetime.now(timezone.utc)+timedelta(minutes=5),reader,prepare)
            worker=holder[0]
            saved=json.loads((journal.root/'final-result.json').read_bytes())
            assert saved==result and saved['phase_timing']['credential_input_seconds']>=.04
            assert 'disposable-input-never-exported' not in journal.file.read_text()
            if fault=='success':
                assert worker.connections==2 and worker.commands<=32 and worker.returned<=1048576
                assert worker.deletes==2 and worker.reads==2 and worker.opened==worker.closed==2
                assert set(ciphertexts)=={'DATABASE_URL'}
                assert result['status']=='SAFETY_CLEANUP_ACCESS_DISABLED'
                after=boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
                assert after['global_stop']==ctl['global_stop'] and after['manual_stop']=='STORAGE_TEST_STOP' and after['hard_stop_generation']==1
                assert after['grants'][CAPTURE_AUTHORITY]['expires_at']==after['bolton_exceptions'][CAPTURE_AUTHORITY]['expires_at']==0
                assert boot.execute('SELECT count(*) FROM public.ingestion_work_items').fetchone()[0]==5
                assert boot.execute('SELECT count(*) FROM public.ingestion_work_attempts').fetchone()[0]==0
            else:
                assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['cleanup']=='UNCERTAIN'
                if fault=='connection_failure':
                    assert worker.connections==1 and worker.commands==worker.deletes==0
                    assert worker.opened==worker.closed==0 and result['phase']=='DATABASE_CONNECT_1'
                if fault in {'changed_grant','associated_session'}:
                    assert worker.connections==1 and worker.deletes==0
                    assert all(row[0] for row in boot.execute('SELECT rolcanlogin FROM pg_roles WHERE rolname=ANY(%s)',(ROLES,)))
                if fault=='commit_lost_ack':assert worker.connections==1 and worker.deletes==0 and len(injected)==1
                if fault=='delete_lost_ack':
                    assert worker.deletes==1 and worker.reads==1 and len(injected)==1
                    assert set(ciphertexts)=={'DATABASE_URL',SECRETS[1]}
            record_property('cleanup_result',json.dumps(dict(fault=fault,accounting=worker.accounting(),memory=memory.close() if memory else None,deleted=worker.secret_deletions,readbacks=worker.readbacks,phase_timing=result['phase_timing'],status=result['status']),sort_keys=True))
        finally:
            if held:held.close()
            boot.execute('DROP TABLE IF EXISTS public.ingestion_work_attempts,public.ingestion_work_items CASCADE')
            for r in [*extra,*base_roles,role]:
                if boot.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(r,)).fetchone():boot.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(r)))
            for r in [*extra,*base_roles,role]:boot.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(r)))
