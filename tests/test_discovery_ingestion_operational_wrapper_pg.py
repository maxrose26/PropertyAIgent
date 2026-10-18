"""Actual owner wrapper, PG17 restricted logins and real Linux gh, loopback only."""
import json,os,secrets,time,subprocess
from datetime import datetime,timezone,timedelta
from pathlib import Path
import psycopg,pytest
from psycopg import sql
from sqlalchemy.engine import URL
from verification.ingestion_storage.operational_runner import Runner,Journal
from verification.ingestion_storage.operational_owner import ROLES,STOP
from verification.ingestion_storage.operational_publication import GitHub,Uncertain
from tests.storage_gh_fixture import real_gh_store

@pytest.mark.parametrize('real_gh_store',['operational'],indirect=True)
@pytest.mark.parametrize('fault',['success','mapping_lost_ack','teardown_lost_ack','closure_failure','worker_connect','post_grant_connect','invalidation_commit_unknown','source_raises','mapping_second_lost_ack','reuse_installed_success'])
def test_complete_required_wrapper_sixty_rows_pause_resume_and_teardown(tmp_path,record_property,real_gh_store,fault,monkeypatch):
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
        boot.execute('CREATE SCHEMA extensions')
        boot.execute("CREATE EXTENSION pg_stat_statements WITH SCHEMA extensions VERSION '1.11'")
        boot.execute(sql.SQL('GRANT USAGE ON SCHEMA extensions TO {}').format(sql.Identifier(role)))
        try:
            # Accepted storage state is fixture setup only, not another storage
            # acceptance suite or production installation.
            with connector() as c:
                c.execute((PACKAGE/'install.sql').read_text())
                c.execute('REVOKE ingestion_worker FROM ingestion_worker_login')
                c.execute('REVOKE ingestion_storage_operator FROM ingestion_storage_login')
            boot.execute("SELECT public.ingestion_raise_stop('STORAGE_TEST_STOP')")
            journal=Journal(tmp_path/'actual-wrapper');holder={}
            injected=[]
            def cli(command,**kwargs):
                response=metadata.cli(command,**kwargs)
                if not injected and ((fault=='mapping_lost_ack' and command[1:3]==['secret','set']) or (fault=='teardown_lost_ack' and '--method' in command and command[command.index('--method')+1]=='DELETE')):
                    injected.append(True);raise subprocess.TimeoutExpired(['gh','DISPOSABLE_ACK_LOSS'],1)
                return response
            github=GitHub(journal.emit,lambda:holder['runner'].check(),runner=cli)
            def uri(r,p):return URL.create('postgresql+psycopg',username=r,password=p,host='127.0.0.1',port=5432,database=info['dbname']).render_as_string(hide_password=False)
            native=None
            if os.environ.get('INGESTION_OPERATIONAL_NATIVE')=='1':
                from verification.ingestion_storage.operational_memory import OperationalMemory
                native=OperationalMemory()
            runner=Runner(registration,journal,connector,source_reader=source,github=github,url_factory=uri,identity=role,memory=native);holder['runner']=runner
            original_install=runner.owner.install
            def install_with_ambient_negatives():
                original_install()
                negatives=[
                  ('GRANT TRUNCATE ON public.ingestion_work_items TO PUBLIC','REVOKE TRUNCATE ON public.ingestion_work_items FROM PUBLIC','RUNTIME_DIRECT_LEDGER_MUTATION'),
                  ('GRANT UPDATE (outcome) ON public.ingestion_work_items TO PUBLIC','REVOKE UPDATE (outcome) ON public.ingestion_work_items FROM PUBLIC','RUNTIME_DIRECT_LEDGER_MUTATION'),
                  ('GRANT SELECT ON public.ingestion_work_items TO ingestion_effect_login','REVOKE SELECT ON public.ingestion_work_items FROM ingestion_effect_login','BROKER_DIRECT_LEDGER_READ'),
                  ('GRANT USAGE ON SCHEMA extensions TO PUBLIC','REVOKE USAGE ON SCHEMA extensions FROM PUBLIC','STATISTICS_BASELINE_BOUNDARY')]
                activation=Path('docs/design/ingestion-operational-required-20261018/activate.sql').read_text()
                for mutation,undo,reason in negatives:
                    boot.execute(mutation)
                    try:
                        with connector() as c:
                            with pytest.raises(psycopg.Error,match=reason):c.execute(activation)
                    finally:boot.execute(undo)
            runner.owner.install=install_with_ambient_negatives
            if fault=='reuse_installed_success':
                # Fixture constructs the already-installed/access-disabled
                # generation-1 state. Production remains bound to the actual
                # accepted cleanup control hash, never this fixture hash.
                original_install()
                boot.execute('ALTER ROLE ingestion_worker_login NOLOGIN PASSWORD NULL')
                boot.execute('ALTER ROLE ingestion_effect_login NOLOGIN PASSWORD NULL')
                boot.execute('REVOKE ingestion_worker FROM ingestion_worker_login')
                boot.execute('REVOKE ingestion_effect_broker FROM ingestion_effect_login')
                ctl=boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
                ctl['hard_stop_generation']=1;ctl['last_hard_stop']='OPERATIONAL_FIRST_CONNECTION_FAILURE_CLEANUP_20261018'
                boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
                runner.owner.reuse_installed=True
                from app.ingestion.ledger import digest
                runner.owner.baseline_control_sha256=digest(ctl)
            if fault in {'worker_connect','post_grant_connect','invalidation_commit_unknown','source_raises','mapping_second_lost_ack'}:
                from verification.ingestion_storage.operational_outcome import session
                from verification.ingestion_storage.tls_trust import verified_trust
                # Production-shaped kwargs reach the real psycopg Connection
                # factory. Only the disposable transport boundary translates
                # tenant routing/TLS to local PG17; this does NOT claim that
                # managed Supavisor accepted these custom role credentials.
                ca,_=verified_trust();observed_routes=[]
                original_connect=psycopg.Connection.connect.__func__
                def route(cls,conninfo='',**kwargs):
                    if kwargs.get('host')=='aws-0-eu-west-2.pooler.supabase.com':
                        assert kwargs['user'].endswith('.zcikcfgpblzuzpanpdqd')
                        assert kwargs['port']==5432 and kwargs['dbname']=='postgres'
                        assert kwargs['sslmode']=='verify-full' and kwargs['sslrootcert']==str(ca)
                        assert kwargs['hostaddr']=='192.0.2.1' and kwargs['prepare_threshold'] is None
                        observed_routes.append(kwargs['user'].split('.')[0])
                        kwargs=dict(kwargs,host='127.0.0.1',dbname=info['dbname'],user=kwargs['user'].split('.')[0])
                        for field in ('sslmode','sslrootcert','hostaddr'):kwargs.pop(field,None)
                    return original_connect(cls,conninfo,**kwargs)
                monkeypatch.setattr(psycopg.Connection,'connect',classmethod(route))
                runner.url_factory=lambda r,p:URL.create('postgresql',username=r+'.zcikcfgpblzuzpanpdqd',password=p,host='aws-0-eu-west-2.pooler.supabase.com',port=5432,database='postgres').render_as_string(hide_password=False)
                runner.ssl={'sslmode':'verify-full','sslrootcert':str(ca)};runner.hostaddr='192.0.2.1'
                if fault=='worker_connect':
                    original_map=runner.owner.map_and_activate
                    def map_then_deny(*args,**kwargs):
                        original_map(*args,**kwargs);boot.execute('ALTER ROLE ingestion_worker_login NOLOGIN')
                    runner.owner.map_and_activate=map_then_deny
                if fault in {'post_grant_connect','invalidation_commit_unknown'}:
                    original_setup=runner.setup
                    def setup_then_deny():
                        original_setup();boot.execute('ALTER ROLE ingestion_worker_login NOLOGIN')
                    runner.setup=setup_then_deny
                if fault=='invalidation_commit_unknown':
                    original_q=runner.owner.q
                    def lost_commit(c,statement,*args,**kwargs):
                        result=original_q(c,statement,*args,**kwargs)
                        if statement=='COMMIT' and runner.owner.invalidation=='UNCERTAIN_RECONCILE':
                            runner.owner.effect_uncertain=True;raise Uncertain('DISPOSABLE_LOST_COMMIT_ACK')
                        return result
                    runner.owner.q=lost_commit
                if fault=='source_raises':
                    def failed_source(row):source_calls.append(row['key']);raise RuntimeError('private connection URL must never escape')
                    runner.source_reader=failed_source
                if fault=='mapping_second_lost_ack':
                    def second_lost(command,**kwargs):
                        response=metadata.cli(command,**kwargs)
                        if command[1:4]==['secret','set','INGESTION_EFFECT_DATABASE_URL']:raise subprocess.TimeoutExpired(['gh','DISPOSABLE'],1)
                        return response
                    github.runner=second_lost
                lines=[]
                result=session(journal,registration['expires_at'],lambda:'disposable hidden input',lambda raw,started:runner,output=lambda line,**kw:lines.append(line))
                assert result['status']=='STOP_RECONCILE_NO_RETRY'
                saved=json.loads((journal.root/'final-result.json').read_bytes());assert saved==result and len(lines)==1
                assert 'private connection URL' not in journal.file.read_text() and 'disposable hidden input' not in lines[0]
                assert result['accounting']['administration']['connections_opened']==result['accounting']['administration']['connections_closed']
                ctl=boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
                if fault=='mapping_second_lost_ack':
                    assert github.mutation_uncertain and not ctl['grants'] and not ctl.get('bolton_exceptions')
                    assert not source_calls and not any(m=='DELETE' for m,p in requests)
                    assert not result['accounting']['runtime']['slot_receipts']
                elif fault=='worker_connect':
                    assert not ctl['grants'] and not ctl.get('bolton_exceptions') and not source_calls
                    assert observed_routes==['ingestion_worker_login']
                    assert set(ciphertexts)=={'DATABASE_URL'}
                elif fault=='invalidation_commit_unknown':
                    assert result['authority_invalidation']=='UNCERTAIN_RECONCILE' and not any(m=='DELETE' for m,p in requests)
                    assert not source_calls
                else:
                    assert result['authority_invalidation']=='ACKNOWLEDGED_READBACK'
                    assert all(g['expires_at']==0 for g in ctl['grants'].values())
                    assert all(g['expires_at']==0 for g in ctl['bolton_exceptions'].values())
                    assert set(ciphertexts)=={'DATABASE_URL'}
                if fault=='source_raises':assert result['source_observations_attempted']==1 and result['source_capture_retained'] is False and result['source_resources']['status']=='ATTEMPTED_ACCOUNTING_UNCERTAIN'
                else:assert result['source_observations_attempted']==0
                record_property('operational_failure',json.dumps(dict(fault=fault,accounting=result['accounting'],routes=observed_routes,invalidation=result['authority_invalidation'],status=result['status'],safe_message_export=False),sort_keys=True))
                return
            if fault=='mapping_lost_ack':
                with pytest.raises(Uncertain):runner.setup()
                diag=runner.owner.diagnostics()
                assert all(row[1] is False for row in diag['roles']) and not source_calls
                assert set(ciphertexts)=={'DATABASE_URL','INGESTION_WORKER_DATABASE_URL'}
                assert not (journal.root/'final-result.json').exists()
                record_property('required_failure',json.dumps(dict(fault=fault,source_calls=0,mapping_calls=sum(m=='PUT' for m,p in requests),actual_roles=diag['roles'],subsequent_mutations=False)))
                return
            runner.setup();runner.capture_once()
            effective_denials=0
            from sqlalchemy.engine import make_url
            for runtime in runner.owner.urls.values():
                u=make_url(runtime)
                with psycopg.connect(host=u.host,port=u.port,dbname=u.database,user=u.username,password=u.password,autocommit=True) as restricted:
                    for statement in ['SELECT 1 FROM extensions.pg_stat_statements LIMIT 0','SELECT 1 FROM extensions.pg_stat_statements_info LIMIT 0','SELECT extensions.pg_stat_statements(false)','SELECT extensions.pg_stat_statements_reset(0::oid,0::oid,0::bigint,false)',"UPDATE public.ingestion_work_items SET outcome='{}'",'SET ROLE ingestion_storage_owner','SET ROLE ingestion_authority_issuer','SET ROLE ingestion_barrier_releaser']:
                        with pytest.raises(psycopg.Error) as denial:restricted.execute(statement)
                        assert denial.value.sqlstate=='42501';effective_denials+=1
            assert len(source_calls)==1 and len(runner.capture['records'])==60 and len(runner.plans)==12
            assert runner.screen(pause_after=1)=='PAUSED_CLOSED_NO_SOURCE_REPLAY'
            checkpoint=(journal.root/'progress.json').read_bytes()
            # Reconstruct a fresh controller from the verified durable state;
            # credential/administrative counters remain in the living trusted
            # owner's RAM, not a file or a new credential mapping invocation.
            state=json.loads(checkpoint);assert state['capture_sha256']==__import__('app.ingestion.ledger',fromlist=['digest']).digest(runner.capture)
            prior_capture=runner.receipts[runner.capture_key]
            runner=Runner.resume(runner);holder['runner']=runner
            carried=runner.receipts[runner.capture_key]
            assert all(carried['database'][k]>=prior_capture['database'][k] for k in ('driver_statements','connection_attempts','returned_data_value_bytes','elapsed_seconds'))
            assert carried['supervised_seconds']>=prior_capture['supervised_seconds']
            assert runner.screen()=='SCREENING_COMPLETE' and len(source_calls)==1
            if fault=='teardown_lost_ack':
                with pytest.raises(Uncertain):runner.finish()
                diag=runner.owner.diagnostics()
                assert all(row[1:3]==(False,True) for row in diag['roles']) and not diag['memberships'] and not diag['sessions']
                assert set(ciphertexts)=={'DATABASE_URL','INGESTION_EFFECT_DATABASE_URL'}
                assert sum(m=='DELETE' for m,p in requests)==1 and not (journal.root/'final-result.json').exists()
                record_property('required_failure',json.dumps(dict(fault=fault,source_calls=len(source_calls),delete_requests=1,actual_roles=diag['roles'],subsequent_mutations=False)))
                return
            if fault=='closure_failure':
                class FailedMemory:
                    def snapshot(self):return {}
                    def close(self):raise Uncertain('DISPOSABLE_CLOSURE_FAILURE')
                runner.memory=FailedMemory()
                with pytest.raises(Uncertain):runner.finish()
                assert json.loads((journal.root/'final-result.json').read_bytes())['cleanup']=='CLOSURE_PENDING'
                assert set(ciphertexts)=={'DATABASE_URL'} and len(source_calls)==1
                record_property('required_failure',json.dumps(dict(fault=fault,durable_cleanup='CLOSURE_PENDING',false_closed=False)))
                return
            result=runner.finish()
            assert result['status']=='REQUIRED_CAPTURE_SCREENING_ACCEPTED_ACCESS_DISABLED' and result['cleanup']=='CLOSED'
            assert set(ciphertexts)=={'DATABASE_URL'}
            ctl=boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
            assert ctl['global_stop']==STOP and ctl['manual_stop']=='STORAGE_TEST_STOP'
            if fault=='reuse_installed_success':assert ctl['hard_stop_generation']==1
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
            record_property('required_wrapper',json.dumps(dict(aggregate=aggregate,admin=result['admin'],runtime_supervised_seconds=runner.runtime_seconds,admin_supervised_seconds=runner.admin_seconds,source_observations=len(source_calls),audit_bytes=journal.file.stat().st_size,github_cli_invocations=github.requests,status=result['status'],effective_denials=effective_denials,stored_query_text_retrieved=False),sort_keys=True))
        finally:
            if 'native' in locals() and native is not None and native.controller.exists():native.close()
            boot.execute('DROP TABLE IF EXISTS public.ingestion_work_attempts,public.ingestion_work_items CASCADE')
            boot.execute('DROP EXTENSION IF EXISTS pg_stat_statements')
            boot.execute('DROP SCHEMA IF EXISTS extensions')
            for r in [*extra,*base_roles,role]:
                if boot.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(r,)).fetchone():boot.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(r)))
            for r in [*extra,*base_roles,role]:boot.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(r)))
