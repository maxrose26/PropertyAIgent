"""Actual owner wrapper, PG17 restricted logins and real Linux gh, loopback only."""
import json,os,secrets,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
import psycopg,pytest
from psycopg import sql
from sqlalchemy.engine import URL
from verification.ingestion_storage.operational_runner import Runner,Journal
from verification.ingestion_storage.operational_owner import ROLES,STOP
from verification.ingestion_storage.operational_publication import GitHub
from tests.storage_gh_fixture import real_gh_store

@pytest.mark.parametrize('real_gh_store',['operational'],indirect=True)
def test_complete_required_wrapper_sixty_rows_pause_resume_and_teardown(tmp_path,record_property,real_gh_store):
    raw=os.environ.get('INGESTION_PROVISIONING_TEST_URL')
    if not raw:pytest.skip('fixed disposable PG17 required')
    info=psycopg.conninfo.conninfo_to_dict(raw)
    assert (info['host'],info['port'],info['dbname'],info['user'])==('127.0.0.1','5432','ingestion_provisioning_test','provisioning_bootstrap')
    password=secrets.token_urlsafe(48);role='provisioning_migrator'
    metadata,secret,ciphertexts,requests=real_gh_store
    from tests.test_discovery_ingestion_batching import sixty_rows
    from tests.test_discovery_ingestion_ledger import outer
    cfg,audit=sixty_rows();source_calls=[]
    def source(row):source_calls.append(row['key']);return audit,outer()
    def connector():return psycopg.connect(**{**info,'user':role,'password':password},autocommit=True,prepare_threshold=None,connect_timeout=3)
    registration=dict(expires_at=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat(),revision='a'*40,controller_sha256='b'*64,manifest_sha256='c'*64,evidence_head='1'*40,evidence_directory='docs/design/ingestion-operational-execution-fixture')
    extra=['ingestion_effect_login','ingestion_effect_broker','ingestion_recovery_operator']
    from tests.test_discovery_ingestion_provisioning_pg import ROLES as base_roles,PACKAGE
    with psycopg.connect(raw,autocommit=True) as boot:
        boot.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER CREATEROLE CREATEDB BYPASSRLS NOINHERIT PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
        boot.execute(sql.SQL('GRANT USAGE,CREATE ON SCHEMA public TO {} WITH GRANT OPTION').format(sql.Identifier(role)))
        boot.execute(sql.SQL('GRANT CONNECT ON DATABASE ingestion_provisioning_test TO {} WITH GRANT OPTION').format(sql.Identifier(role)))
        # Match the existing, accepted production read-only reconciliation
        # capability: only boolean password-removal checks are ever selected.
        boot.execute(sql.SQL('GRANT SELECT(rolname,rolpassword) ON pg_catalog.pg_authid TO {}').format(sql.Identifier(role)))
        try:
            # Accepted storage state is fixture setup only, not another storage
            # acceptance suite or production installation.
            with connector() as c:
                c.execute((PACKAGE/'install.sql').read_text())
                c.execute('REVOKE ingestion_worker FROM ingestion_worker_login')
                c.execute('REVOKE ingestion_storage_operator FROM ingestion_storage_login')
            boot.execute("SELECT public.ingestion_raise_stop('STORAGE_TEST_STOP')")
            journal=Journal(tmp_path/'actual-wrapper');holder={}
            github=GitHub(journal.emit,lambda:holder['runner'].check(),runner=metadata.cli)
            def uri(r,p):return URL.create('postgresql+psycopg',username=r,password=p,host='127.0.0.1',port=5432,database=info['dbname']).render_as_string(hide_password=False)
            runner=Runner(registration,journal,connector,source_reader=source,github=github,url_factory=uri,identity=role);holder['runner']=runner
            runner.setup();runner.capture_once()
            assert len(source_calls)==1 and len(runner.capture['records'])==60 and len(runner.plans)==12
            assert runner.screen(pause_after=1)=='PAUSED_CLOSED_NO_SOURCE_REPLAY'
            checkpoint=(journal.root/'progress.json').read_bytes()
            # Reconstruct a fresh controller from the verified durable state;
            # credential/administrative counters remain in the living trusted
            # owner's RAM, not a file or a new credential mapping invocation.
            state=json.loads(checkpoint);assert state['capture_sha256']==__import__('app.ingestion.ledger',fromlist=['digest']).digest(runner.capture)
            runner=Runner.resume(runner);holder['runner']=runner
            assert runner.screen()=='SCREENING_COMPLETE' and len(source_calls)==1
            result=runner.finish()
            assert result['status']=='REQUIRED_CAPTURE_SCREENING_ACCEPTED_ACCESS_DISABLED' and result['cleanup']=='CLOSED'
            assert set(ciphertexts)=={'DATABASE_URL'}
            ctl=boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
            assert ctl['global_stop']==STOP and ctl['manual_stop']=='STORAGE_TEST_STOP'
            assert all(g['expires_at']==0 for g in ctl['grants'].values())
            assert boot.execute("SELECT count(*) FROM public.ingestion_work_items WHERE task='SCREENING' AND state='COMPLETE'").fetchone()[0]==60
            assert boot.execute("SELECT count(*) FROM public.ingestion_work_items WHERE task='FACTUAL_REFRESH'").fetchone()[0]==0
            # Real worker cannot create grants, release stops or mutate tables;
            # these core denials are reused from accepted PG fixtures, while
            # this wrapper establishes lifecycle and absence of writer roles.
            assert boot.execute("SELECT count(*) FROM pg_roles WHERE rolname='ingestion_application_login'").fetchone()[0]==0
            aggregate={k:sum(r['database'][k] for r in runner.receipts.values()) for k in ('driver_statements','connection_attempts','returned_data_value_bytes')}
            assert aggregate['driver_statements']<=1040 and aggregate['connection_attempts']<=40 and aggregate['returned_data_value_bytes']<=4*1024**2
            assert runner.owner.connections<=13 and runner.owner.commands<=240
            record_property('required_wrapper',json.dumps(dict(aggregate=aggregate,admin=result['admin'],runtime_supervised_seconds=runner.runtime_seconds,admin_supervised_seconds=runner.admin_seconds,source_observations=len(source_calls),audit_bytes=journal.file.stat().st_size,github_cli_invocations=github.requests,status=result['status']),sort_keys=True))
        finally:
            boot.execute('DROP TABLE IF EXISTS public.ingestion_work_attempts,public.ingestion_work_items CASCADE')
            for r in [*extra,*base_roles,role]:
                if boot.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(r,)).fetchone():boot.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(r)))
            for r in [*extra,*base_roles,role]:boot.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(r)))
