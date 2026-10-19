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
@pytest.mark.parametrize('fault',['success','mapping_lost_ack','teardown_lost_ack','closure_failure','worker_connect','post_grant_connect','invalidation_commit_unknown','source_raises','mapping_second_lost_ack','reuse_installed_success','diagnostic_only','matrix_success','matrix_classified_continue','matrix_unclassified_stop','matrix_tls_stop','matrix_identity_stop','matrix_budget_stop','matrix_admin_bound_reserve','matrix_close_uncertain','session_survives_privileged','session_survives_unprivileged','blocked_query','exhausted_normal_budget','role_settings_success','role_settings_partial_install','role_settings_failed_qualification','role_settings_uncertain_restoration','first_session_query_fails'])
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
        if fault=='session_survives_privileged':boot.execute(sql.SQL('GRANT pg_signal_backend, pg_read_all_stats TO {} WITH INHERIT TRUE').format(sql.Identifier(role)))      # emulates a migration identity that already holds them
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
            if fault=='role_settings_success':boot.execute("ALTER ROLE ingestion_worker_login SET work_mem='5MB'");boot.execute("ALTER ROLE ingestion_worker_login SET statement_timeout='7s'")      # prior configuration to be preserved and restored
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
            if fault.startswith('role_settings_') or fault=='first_session_query_fails':
                real_connect=psycopg.Connection.connect.__func__
                def options_ignored(cls,conninfo='',**kw):
                    kw.pop('options',None);return real_connect(cls,conninfo,**kw)          # a pooler that ignores startup options, as observed live
                monkeypatch.setattr(psycopg.Connection,'connect',classmethod(options_ignored))
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
            if fault in {'reuse_installed_success','diagnostic_only'} or fault.startswith('matrix_'):
                # Fixture constructs the already-installed/access-disabled
                # generation-1 state. Production remains bound to the actual
                # accepted cleanup control hash, never this fixture hash.
                from verification.ingestion_storage.operational_owner import Owner
                installer=Owner(connector,lambda *_:None,lambda:None,identity=role,expiry=runner.expiry,bindings=runner.bindings)
                installer.install()
                record_property('fixture_installation',json.dumps(installer.accounting()))
                boot.execute('ALTER ROLE ingestion_worker_login NOLOGIN PASSWORD NULL')
                boot.execute('ALTER ROLE ingestion_effect_login NOLOGIN PASSWORD NULL')
                with connector() as migration:
                    migration.execute('REVOKE ingestion_worker FROM ingestion_worker_login GRANTED BY CURRENT_USER')
                    migration.execute('REVOKE ingestion_effect_broker FROM ingestion_effect_login GRANTED BY CURRENT_USER')
                ctl=boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
                ctl['hard_stop_generation']=1;ctl['last_hard_stop']='OPERATIONAL_FIRST_CONNECTION_FAILURE_CLEANUP_20261018'
                boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
                runner.owner.reuse_installed=True
                from app.ingestion.ledger import digest
                runner.owner.baseline_control_sha256=digest(ctl)
                for mutation,undo,expected in [
                  ('ALTER ROLE ingestion_effect_login BYPASSRLS','ALTER ROLE ingestion_effect_login NOBYPASSRLS','REUSED_RUNTIME_FLAGS_CHANGED'),
                  ('GRANT ingestion_authority_issuer TO ingestion_effect_login','REVOKE ingestion_authority_issuer FROM ingestion_effect_login GRANTED BY CURRENT_USER','REUSED_RUNTIME_MEMBERSHIPS_CHANGED')]:
                    probe=Owner(connector,lambda *_:None,lambda:None,identity=role,expiry=runner.expiry,bindings=runner.bindings)
                    probe.reuse_installed=True;probe.baseline_control_sha256=digest(ctl)
                    before_requests=list(requests);boot.execute(mutation)
                    try:
                        with pytest.raises(ValueError,match=expected):probe.preflight()
                        assert requests==before_requests
                    finally:boot.execute(undo)
                    record_property('fixture_negative_preflight',json.dumps(probe.accounting()))

                if fault.startswith('matrix_'):
                    from verification.ingestion_storage import operational_runner as orr, restricted_matrix as rm
                    from verification.ingestion_storage.operational_outcome import session
                    runner.r['mode']=orr.MATRIX_MODE;runner.matrix_mode=True;runner.deadlines=dict(orr.MATRIX_DEADLINES)
                    runner.owner.limits=dict(orr.MATRIX_OWNER_LIMITS);runner.owner.apply_policy=False
                    real_connect=psycopg.connect;calls=[];leaked=[]
                    plan={'matrix_classified_continue':{1:psycopg.errors.InvalidPassword('password authentication failed for user "x"'),3:psycopg.OperationalError('connection timeout expired')},
                          'matrix_unclassified_stop':{2:RuntimeError('private text must never escape')},'matrix_tls_stop':{1:psycopg.OperationalError('SSL error: certificate verify failed')}}.get(fault,{})
                    def guarded(*a,**k):
                        if k.get('user') not in ROLES:return real_connect(*a,**k)
                        calls.append((k['user'],k.get('options')))
                        if len(calls) in plan:raise plan[len(calls)]
                        connection=real_connect(*a,**k)
                        if fault=='matrix_close_uncertain' and len(calls)==1:
                            leaked.append(connection)
                            class Leaky:
                                closed=False
                                def execute(self,statement):return connection.execute(statement)
                                def close(self):pass
                            return Leaky()
                        return connection
                    monkeypatch.setattr(psycopg,'connect',guarded)
                    if fault=='matrix_identity_stop':monkeypatch.setattr(rm,'EXPECTED_FLAGS',(True,True,False,False,False,False))
                    if fault=='matrix_budget_stop':monkeypatch.setitem(rm.LIMITS,'connection_attempts',2)
                    if fault=='matrix_admin_bound_reserve':
                        original_map=runner.owner.map_and_activate
                        def map_then_exhaust(*a,**k):
                            original_map(*a,**k);runner.owner.commands=runner.owner.limits['commands'][0];raise ValueError('ADMIN_COMMAND_BOUND')
                        runner.owner.map_and_activate=map_then_exhaust
                    measured_admin={'matrix_success':(4,46),'matrix_classified_continue':(4,46),'matrix_unclassified_stop':(5,52),'matrix_tls_stop':(5,52),'matrix_identity_stop':(5,52),'matrix_budget_stop':(5,52),'matrix_admin_bound_reserve':(5,59),'matrix_close_uncertain':(5,56)}[fault]
                    expected={'matrix_success':('RESTRICTED_MATRIX_COMPLETED_ACCESS_DISABLED',['CONNECTED_IDENTITY_VERIFIED']*4,None,4),
                              'matrix_classified_continue':('RESTRICTED_MATRIX_COMPLETED_ACCESS_DISABLED',['FAILED_CLASSIFIED','CONNECTED_IDENTITY_VERIFIED','FAILED_CLASSIFIED','CONNECTED_IDENTITY_VERIFIED'],None,4),
                              'matrix_unclassified_stop':('STOP_RECONCILE_NO_RETRY',['CONNECTED_IDENTITY_VERIFIED','FAILED_UNCLASSIFIED','SKIPPED_GLOBAL_STOP','SKIPPED_GLOBAL_STOP'],'UNCLASSIFIED_FAILURE',2),
                              'matrix_tls_stop':('STOP_RECONCILE_NO_RETRY',['FAILED_CLASSIFIED']+['SKIPPED_GLOBAL_STOP']*3,'SECURITY_CLASS_FAILURE',1),
                              'matrix_identity_stop':('STOP_RECONCILE_NO_RETRY',['IDENTITY_UNEXPECTED']+['SKIPPED_GLOBAL_STOP']*3,'UNEXPECTED_IDENTITY',1),
                              'matrix_budget_stop':('STOP_RECONCILE_NO_RETRY',['CONNECTED_IDENTITY_VERIFIED']*2+['SKIPPED_GLOBAL_STOP']*2,'CONNECTION_BUDGET_EXHAUSTED',2),
                              'matrix_admin_bound_reserve':('STOP_RECONCILE_NO_RETRY',['SKIPPED_GLOBAL_STOP']*4,'LIFECYCLE_STOP_BEFORE_MATRIX_COMPLETE',0),
                              'matrix_close_uncertain':('STOP_RECONCILE_NO_RETRY',['CLOSURE_UNCERTAIN']+['SKIPPED_GLOBAL_STOP']*3,'CLOSURE_UNCERTAIN',1)}[fault]
                    lines=[]
                    result=session(journal,registration['expires_at'],lambda:'disposable hidden input',lambda raw,started:runner,output=lambda line,**kw:lines.append(line),timing=orr.MATRIX_TIMING)
                    status,outcomes,stop,attempted=expected
                    try:
                        assert result['status']==status and [e['outcome'] for e in result['matrix']['entries']]==outcomes and result['matrix']['global_stop']==stop and len(calls)==attempted
                        assert result['matrix']['accounting']['connection_attempts']['value']==attempted
                        assert result['matrix']['interpretation']['execution_authority']=='NONE' and 'CREDENTIAL_CACHING' in result['matrix']['interpretation']['not_established']
                        assert json.loads((journal.root/'final-result.json').read_bytes())==json.loads(json.dumps(result)) and len(lines)==1
                        assert 'private text must never escape' not in json.dumps(result) and 'private text must never escape' not in journal.file.read_text() and 'postgresql://' not in json.dumps(result)
                        # No authority, grant, exception, source call, queue row or application write on ANY path.
                        assert not runner.owner.authorities and not source_calls and result['application_writes']==0 and result['pipeline_retry']=='HELD' and result['stage4']=='OPEN'
                        actual=boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
                        assert actual==ctl and boot.execute("SELECT count(*) FROM public.ingestion_work_attempts").fetchone()[0]==0
                        assert boot.execute("SELECT count(*) FROM public.ingestion_work_items WHERE key<>repeat('0',64)").fetchone()[0]==0
                        # Administrative allowance: TOTAL connections/commands across lifecycle, failure handling and teardown never exceed the proposed 5 / 64.
                        assert runner.owner.connections<=orr.MATRIX_OWNER_LIMITS['connections'][1] and runner.owner.commands<=orr.MATRIX_OWNER_LIMITS['commands'][2]
                        assert runner.owner.opened==runner.owner.closed
                        assert (runner.owner.connections,runner.owner.commands)==measured_admin       # pinned measurements: drift in the lifecycle fails here, it does not pass silently
                        # Every non-completed entry kept its own closure; teardown disabled access (unless closure was deliberately made uncertain).
                        if fault=='matrix_close_uncertain':
                            assert result['cleanup']=='UNCERTAIN' and result['access']!='DISABLED_VERIFIED'
                        else:
                            assert result['cleanup']=='CLOSED' and set(ciphertexts)=={'DATABASE_URL'}
                            assert boot.execute("SELECT rolname,rolcanlogin,rolpassword IS NULL FROM pg_catalog.pg_authid WHERE rolname=ANY(%s) ORDER BY rolname",(list(ROLES),)).fetchall()==[('ingestion_effect_login',False,True),('ingestion_worker_login',False,True)]
                            assert not boot.execute("SELECT 1 FROM pg_auth_members WHERE member=ANY(%s::regrole[])",(list(ROLES),)).fetchall() and not boot.execute("SELECT 1 FROM pg_stat_activity WHERE usename=ANY(%s)",(list(ROLES),)).fetchall()
                            if status=='STOP_RECONCILE_NO_RETRY':assert result['access']=='DISABLED_VERIFIED'
                        if fault=='matrix_success':
                            assert runner.owner.connections==4                                                    # preflight, install, mapping/activation, teardown
                            assert [c[1] for c in calls]==[None,rm.STARTUP_OPTIONS,None,rm.STARTUP_OPTIONS] and [c[0] for c in calls]==['ingestion_worker_login']*2+['ingestion_effect_login']*2
                            stamps=[e['intervals_at_attempt'] for e in result['matrix']['entries']]
                            assert all(s['since_password_committed_seconds']>=s['since_mapping_acknowledged_seconds']>=s['since_activation_committed_seconds']>=0 for s in stamps)
                            assert result['matrix']['accounting']['identity_statements']['value']==4 and result['matrix']['accounting']['rollbacks']['value']==0
                    finally:
                        [c.close() for c in leaked]
                    record_property('restricted_matrix',json.dumps(dict(fault=fault,status=result['status'],outcomes=outcomes,global_stop=stop,admin_connections=runner.owner.connections,admin_commands=runner.owner.commands,
                                    admin_opened=runner.owner.opened,admin_closed=runner.owner.closed,matrix_accounting=result['matrix']['accounting'],access=result.get("access"),cleanup=result["cleanup"])))
                    print('MATRIX_MEASURE',fault,'admin_connections',runner.owner.connections,'admin_commands',runner.owner.commands,"cleanup",result["cleanup"],"access",result.get("access"))
                    return

                if fault=='diagnostic_only':
                    from verification.ingestion_storage.operational_outcome import session
                    runner.r['mode']='CONNECTION_DIAGNOSTIC_ONLY';runner.owner.apply_policy=False
                    lines=[]
                    result=session(journal,registration['expires_at'],lambda:'hidden fixture input',lambda raw,started:runner,output=lambda line,**kw:lines.append(line))
                    assert result['status']=='RESTRICTED_ROUTE_QUALIFIED_ACCESS_DISABLED' and result['cleanup']=='CLOSED'
                    actual=boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
                    assert actual==ctl and not runner.owner.authorities and not source_calls
                    assert set(ciphertexts)=={'DATABASE_URL'}
                    assert not boot.execute("SELECT count(*) FROM public.ingestion_work_attempts").fetchone()[0]
                    assert boot.execute("SELECT count(*) FROM public.ingestion_work_items WHERE key<>repeat('0',64)").fetchone()[0]==0
                    record_property('restricted_route_diagnostic',json.dumps(dict(accounting=result['accounting'],status=result['status'],execution_grants=0,source_calls=0,ledger_changed=False)))
                    return

            if fault in {'worker_connect','post_grant_connect','invalidation_commit_unknown','source_raises','mapping_second_lost_ack','blocked_query','exhausted_normal_budget','role_settings_partial_install','role_settings_failed_qualification','role_settings_uncertain_restoration'}:
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
                if fault=='blocked_query':
                    from verification.ingestion_storage import operational_controller as oc
                    monkeypatch.setattr(oc,'STATEMENT_HARD_SECONDS',1)
                    locks=[];original_capture=runner.capture_once;original_failed=runner.failed
                    def locked_capture():
                        lock=psycopg.connect(raw,autocommit=True);lock.execute('BEGIN');lock.execute('LOCK TABLE public.ingestion_work_items IN ACCESS EXCLUSIVE MODE');locks.append(lock)
                        return original_capture()                                              # the first ledger statement now blocks on the server, whatever its timeouts
                    def release_then_failed(exc):
                        for lock in locks:lock.execute('ROLLBACK');lock.close()
                        return original_failed(exc)
                    runner.capture_once=locked_capture;runner.failed=release_then_failed
                if fault=='role_settings_partial_install':
                    real_q=runner.owner.q;set_seen=[]
                    def partial_q(c,statement,params=None,*,effect=False):
                        if isinstance(statement,sql.Composed) and ' SET ' in statement.as_string(c):
                            set_seen.append(1)
                            if len(set_seen)==4:raise Uncertain('DISPOSABLE_PARTIAL_ROLE_SETTINGS')      # half of the six statements were issued; the transaction never commits
                        return real_q(c,statement,params,effect=effect)
                    runner.owner.q=partial_q
                if fault=='role_settings_failed_qualification':
                    original_map_rs=runner.owner.map_and_activate
                    def map_then_unset(*a,**k):
                        original_map_rs(*a,**k);boot.execute('ALTER ROLE ingestion_worker_login RESET statement_timeout')      # applied, then not reflected for the worker
                    runner.owner.map_and_activate=map_then_unset
                if fault=='role_settings_uncertain_restoration':
                    original_map_ur=runner.owner.map_and_activate
                    def map_then_deny_ur(*a,**k):
                        original_map_ur(*a,**k);boot.execute('ALTER ROLE ingestion_worker_login NOLOGIN')      # qualification fails, teardown runs
                    runner.owner.map_and_activate=map_then_deny_ur
                    real_q_ur=runner.owner.q;commits_ur=[]
                    def restoration_lost(c,statement,params=None,*,effect=False):
                        if statement=='COMMIT' and runner.owner.tearing_down:
                            commits_ur.append(1)
                            if len(commits_ur)==2:raise Uncertain('DISPOSABLE_RESTORATION_NOT_REACHED')      # the second teardown transaction is the restoration
                        return real_q_ur(c,statement,params,effect=effect)
                    runner.owner.q=restoration_lost
                if fault=='exhausted_normal_budget':
                    original_map_budget=runner.owner.map_and_activate
                    def map_then_exhaust(*a,**k):
                        original_map_budget(*a,**k);runner.owner.commands=runner.owner.limits['commands'][0]-1;raise ValueError('ADMIN_COMMAND_BOUND')
                    runner.owner.map_and_activate=map_then_exhaust
                lines=[]
                result=session(journal,registration['expires_at'],lambda:'disposable hidden input',lambda raw,started:runner,output=lambda line,**kw:lines.append(line))
                assert result['status']=='STOP_RECONCILE_NO_RETRY'
                saved=json.loads((journal.root/'final-result.json').read_bytes());assert saved==json.loads(json.dumps(result)) and len(lines)==1
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
                elif fault.startswith('role_settings_'):
                    assert not ctl['grants'] and not ctl.get('bolton_exceptions') and not source_calls and set(ciphertexts)=={'DATABASE_URL'} and result['operation_phase'] in ('RESTRICTED_CONNECTION_QUALIFICATION','CREDENTIAL_MAPPING_ACTIVATION')
                    cfg={r:sorted(c or []) for r,c in boot.execute('SELECT rolname,rolconfig FROM pg_roles WHERE rolname=ANY(%s)',(['ingestion_worker_login','ingestion_effect_login'],)).fetchall()}
                    admin=result['accounting']['administration']
                    if fault=='role_settings_uncertain_restoration':
                        assert admin['role_settings']['state']=='RESTORATION_UNCERTAIN' and admin['teardown_residuals']==['ROLE_SETTINGS_UNRESTORED'] and cfg['ingestion_worker_login']!=[] and cfg['ingestion_effect_login']!=[]
                        assert boot.execute("SELECT rolcanlogin,rolpassword IS NULL FROM pg_authid WHERE rolname='ingestion_worker_login'").fetchone()==(False,True)      # disabled regardless; the residual is reported, never hidden
                    elif fault=='role_settings_partial_install':
                        assert admin['role_settings']['state']=='APPLYING' and cfg=={'ingestion_effect_login':[],'ingestion_worker_login':[]} and result['access']=='UNRECONCILED'      # one transaction: nothing applied, no automatic compensation, reported
                        assert sorted(result['diagnostics']['role_config'])==[('ingestion_effect_login',None),('ingestion_worker_login',None)]
                    else:
                        assert result['access']=='DISABLED_VERIFIED' and admin['role_settings']['state']=='RESTORED_VERIFIED' and cfg=={'ingestion_effect_login':[],'ingestion_worker_login':[]}
                    print('ROLLUP_ROLE_SETTINGS',fault,admin['commands'],admin['connections'],admin['role_settings']['state'])
                elif fault=='exhausted_normal_budget':
                    # the NORMAL administrative command allowance was spent right after mapping; the reserved teardown allowance still disables access and removes the secrets
                    assert result['access']=='DISABLED_VERIFIED' and result['cleanup']=='CLOSED' and set(ciphertexts)=={'DATABASE_URL'} and not source_calls and not ctl['grants'] and not ctl.get('bolton_exceptions')
                    assert runner.owner.commands>runner.owner.limits['commands'][0] and runner.owner.commands<=runner.owner.limits['commands'][1]
                else:
                    assert result['authority_invalidation']=='ACKNOWLEDGED_READBACK'
                    assert all(g['expires_at']==0 for g in ctl['grants'].values())
                    assert all(g['expires_at']==0 for g in ctl['bolton_exceptions'].values())
                    assert set(ciphertexts)=={'DATABASE_URL'}
                if fault=='blocked_query':
                    receipts=result['accounting']['runtime']['slot_receipts'];events=[e for r in receipts.values() for e in r['database']['hard_deadline_events']]
                    assert events and events[0]['cancel_outcome'] in ('CANCEL_SENT','CANCEL_FAILED','CANCEL_FAILED_TIMEOUT') and events[0]['backend_closure']=='NOT_ESTABLISHED' and events[0]['client_closed'] is True
                    assert all(r['database']['cleanup']=='CLOSED' and r['database']['connections_closed'] is True for r in receipts.values()) and result['cleanup']=='CLOSED'
                    print('ROLLUP_BLOCKED_QUERY',len(events),events[0]['cancel_outcome'],events[0]['hard_seconds'])
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
            runner.setup()
            if fault=='reuse_installed_success':
                from copy import deepcopy
                control=boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
                authority=runner.owner.authorities[-1]
                allowed=lambda state,subject:boot.execute('SELECT public.ingestion_bolton_allowed(%s::jsonb,%s,%s::jsonb)',(json.dumps(state),authority,json.dumps(subject))).fetchone()[0]
                from verification.ingestion_storage.operational_owner import SCOPE
                assert allowed(control,SCOPE) is True
                assert allowed(control,dict(SCOPE,council='salford')) is False
                stopped=deepcopy(control);stopped['hard_stop_generation']+=1
                assert allowed(stopped,SCOPE) is False
                record_property('fixture_policy_assertion_commands','4')
            runner.capture_once()
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
            survivors=[];survivor_pids=[]
            if fault in {'session_survives_privileged','session_survives_unprivileged'}:
                original_teardown=runner.owner.teardown
                def with_survivor(gh):
                    ru=make_url(runner.owner.urls['ingestion_worker_login'])
                    survivors.append(psycopg.connect(host=ru.host,port=ru.port,dbname=ru.database,user=ru.username,password=ru.password,autocommit=True,connect_timeout=3));survivor_pids.append(survivors[0].info.backend_pid)      # a session that outlives the disable
                    try:return original_teardown(gh)
                    finally:
                        if fault=='session_survives_privileged':survivors[0].close()          # the test process is the client: release its socket so process closure measures the controller, not the fixture
                runner.owner.teardown=with_survivor
            if fault=='first_session_query_fails':
                real_q_fs=runner.owner.q;first_read=[]
                def first_session_read_fails(c,statement,params=None,*,effect=False):
                    if statement==__import__("verification.ingestion_storage.operational_owner",fromlist=["x"]).SESSIONS_SQL and not first_read:
                        first_read.append(1);c.close();raise Uncertain('ADMIN_STATEMENT_HARD_DEADLINE')      # what a deadline does to the connection and the call
                    return real_q_fs(c,statement,params,effect=effect)
                runner.owner.q=first_session_read_fails
                with pytest.raises(Uncertain):runner.finish()
                assert first_read and runner.owner.session_disposition=='UNVERIFIED' and set(ciphertexts)=={'DATABASE_URL'}      # access disabled by readback, so the secrets are gone although the session state is unverified
                assert boot.execute("SELECT count(*) FROM pg_authid WHERE rolname=ANY(%s) AND (rolcanlogin OR rolpassword IS NOT NULL)",(['ingestion_worker_login','ingestion_effect_login'],)).fetchone()[0]==0
                assert runner.owner.role_settings_state=='RESTORED_VERIFIED' and all(c is None for r,c in boot.execute('SELECT rolname,rolconfig FROM pg_roles WHERE rolname=ANY(%s)',(['ingestion_worker_login','ingestion_effect_login'],)).fetchall())
                print('ROLLUP_FIRST_SESSION_QUERY_FAILS',runner.owner.commands,runner.owner.connections,runner.owner.teardown_residuals)
                return
            if fault=='session_survives_unprivileged':
                with pytest.raises(Uncertain):runner.finish()
                assert runner.owner.session_disposition=='UNRESOLVED_PRIVILEGE_NOT_PROVEN' and runner.owner.terminations==0 and set(ciphertexts)=={'DATABASE_URL'}      # unresolved, reported, secrets removed independently
                pid=survivors[0].info.backend_pid
                assert boot.execute('SELECT count(*) FROM pg_stat_activity WHERE pid=%s',(pid,)).fetchone()[0]==1
                survivors[0].close()
                print('ROLLUP_SURVIVOR_UNPRIVILEGED',runner.owner.session_disposition,runner.owner.commands)
                return
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
            expected_cfg={'ingestion_effect_login':[],'ingestion_worker_login':['statement_timeout=7s','work_mem=5MB'] if fault=='role_settings_success' else []}
            assert {r:sorted(c or []) for r,c in boot.execute('SELECT rolname,rolconfig FROM pg_roles WHERE rolname=ANY(%s)',(['ingestion_worker_login','ingestion_effect_login'],)).fetchall()}==expected_cfg and runner.owner.role_settings_state=='RESTORED_VERIFIED' and runner.owner.teardown_residuals==[]
            print('ROLLUP_ADMIN_COMPLETE',fault,runner.owner.commands,runner.owner.connections)
            if fault=='session_survives_privileged':
                pid=survivor_pids[0]
                assert runner.owner.session_disposition=='TERMINATED_VERIFIED_ABSENT' and runner.owner.terminations==1 and boot.execute('SELECT count(*) FROM pg_stat_activity WHERE pid=%s',(pid,)).fetchone()[0]==0
                print('ROLLUP_SURVIVOR_PRIVILEGED',runner.owner.session_disposition,runner.owner.commands,runner.owner.connections)
            record_property('required_wrapper',json.dumps(dict(aggregate=aggregate,admin=result['admin'],runtime_supervised_seconds=runner.runtime_seconds,admin_supervised_seconds=runner.admin_seconds,source_observations=len(source_calls),audit_bytes=journal.file.stat().st_size,github_cli_invocations=github.requests,status=result['status'],effective_denials=effective_denials,stored_query_text_retrieved=False),sort_keys=True))
        finally:
            if 'native' in locals() and native is not None and native.controller.exists():native.close()
            boot.execute('DROP TABLE IF EXISTS public.ingestion_work_attempts,public.ingestion_work_items CASCADE')
            boot.execute('DROP EXTENSION IF EXISTS pg_stat_statements')
            boot.execute('DROP SCHEMA IF EXISTS extensions')
            for r in [*extra,*base_roles,role]:
                if boot.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(r,)).fetchone():boot.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(r)))
            for r in [*extra,*base_roles,role]:boot.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(r)))
