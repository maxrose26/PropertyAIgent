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
@pytest.mark.parametrize('fault',['success','mapping_lost_ack','teardown_lost_ack','closure_failure','worker_connect','post_grant_connect','invalidation_commit_unknown','source_raises','mapping_second_lost_ack','reuse_installed_success','diagnostic_only','matrix_success','matrix_classified_continue','matrix_unclassified_stop','matrix_tls_stop','matrix_identity_stop','matrix_budget_stop','matrix_admin_bound_reserve','matrix_close_uncertain','session_survives_privileged','session_survives_unprivileged','blocked_query','exhausted_normal_budget','role_settings_success','role_settings_partial_install','role_settings_failed_qualification','role_settings_uncertain_restoration','first_session_query_fails','settled_success','settled_first_connection_rejected','settled_stop_during_interval','policy_lifecycle','settled_success_retained','settled_first_connection_rejected_retained','settled_stop_during_interval_retained','direct_diagnostic_success','direct_first_connection_rejected','direct_route_fallback_refused','direct_address_missing','direct_effect_rejected','stable_lifecycle','stable_provision_failure','stable_revoke_survivor'])
def test_complete_required_wrapper_sixty_rows_pause_resume_and_teardown(tmp_path,record_property,real_gh_store,fault,monkeypatch):
    retained=fault.endswith('_retained');fault=fault[:-len('_retained')] if retained else fault      # same scenario, started from the RETAINED upgraded installation of a previous run
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
            mapped_values={}
            def cli(command,**kwargs):
                if command[1:3]==['secret','set']:mapped_values[command[3]]=kwargs['input'].decode()      # what the protected mapping receives
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
            if fault.startswith('settled_'):
                from verification.ingestion_storage.operational_runner import SETTLED_R2_MODE
                registration['mode']=SETTLED_R2_MODE
            if fault.startswith('direct_'):
                from verification.ingestion_storage.operational_runner import DIRECT_MODE
                registration['mode']=DIRECT_MODE
            if fault.startswith('stable_'):
                from verification.ingestion_storage.operational_runner import STABLE_PROVISION_MODE
                registration['mode']=STABLE_PROVISION_MODE
            runner=Runner(registration,journal,connector,source_reader=source,github=github,url_factory=uri,identity=role,memory=native);holder['runner']=runner
            contacts=[]
            if fault.startswith('settled_'):
                from verification.ingestion_storage.operational_runner import SETTLE_SECONDS
                assert runner.settle_seconds==SETTLE_SECONDS==30 and runner.authority.endswith('SETTLED_R2_ONCE_20261019')      # the production interval; a short one is substituted below only to keep CI short
                runner.settle_seconds=0.6
                original_settle=runner.settle;settled_at=[]
                def recording_settle():
                    original_settle();settled_at.append(time.monotonic())
                runner.settle=recording_settle
                contact_connect=psycopg.Connection.connect.__func__
                def recording_connect(cls,conninfo='',**kw):
                    contacts.append((time.monotonic(),str(kw.get('user'))));return contact_connect(cls,conninfo,**kw)
                monkeypatch.setattr(psycopg.Connection,'connect',classmethod(recording_connect))
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
            if fault in {'reuse_installed_success','diagnostic_only','policy_lifecycle'} or fault.startswith('matrix_') or retained or fault.startswith('direct_') or fault.startswith('stable_'):
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
                if retained or fault.startswith('direct_') or fault.startswith('stable_'):
                    with installer.connection() as c_:installer.script(c_,Path('docs/design/ingestion-operational-required-20261018/successor-policy.sql'))      # the state a previous run leaves behind
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

                if fault=='policy_lifecycle':
                    import re as re_
                    from app.ingestion.ledger import digest as digest_
                    from tests.test_ingestion_preflight_policy_state import legacy_verify
                    def fresh(apply_policy=True):
                        o=Owner(connector,lambda *_:None,lambda:None,identity=role,expiry=runner.expiry,bindings=runner.bindings)
                        o.reuse_installed=True;o.baseline_control_sha256=digest_(ctl);o.apply_policy=apply_policy;return o
                    policy_file=Path('docs/design/ingestion-operational-required-20261018/successor-policy.sql')
                    def function_statement(name):
                        m=re_.search(r'CREATE (?:OR REPLACE )?FUNCTION public\.'+name+r'\(.*?\$(\w*)\$.*?\$\1\$;',Path('docs/design/ingestion-operational-20261016/worker.sql').read_text(),re_.S)
                        statement_=re_.sub(r'^CREATE (OR REPLACE )?FUNCTION','CREATE OR REPLACE FUNCTION',m[0])      # worker.sql creates; the rehearsal replaces
                        return statement_,'$'+m[1]+'$;'
                    # 1. original installed state, preflight by a controller
                    first=fresh();first.preflight();assert first.preflight_report['policy_state']=='ORIGINAL'
                    # 2. the real installation path applies the reviewed successor policy; the lifecycle then completes with a verified teardown
                    first.install();first.map_and_activate(runner.github,url_factory=uri);first.teardown(runner.github)
                    assert set(ciphertexts)=={'DATABASE_URL'} and boot.execute("SELECT count(*) FROM pg_authid WHERE rolname=ANY(%s) AND (rolcanlogin OR rolpassword IS NOT NULL)",(['ingestion_worker_login','ingestion_effect_login'],)).fetchone()[0]==0
                    # 3. a FRESH controller: the predecessor logic fails on the retained state (the observed failure) and the corrected logic passes
                    with monkeypatch.context() as m_:
                        m_.setattr(Owner,'verify_installed',legacy_verify)
                        with pytest.raises(ValueError,match='INSTALLED_FUNCTION_CONTENT_CHANGED'):fresh().preflight()
                    ok=fresh();ok.preflight();assert ok.preflight_report=={'reason_code':'POLICY_STATE_RECOGNISED','policy_state':'SUCCESSOR_POLICY_APPLIED','permitted_states':['ORIGINAL','SUCCESSOR_POLICY_APPLIED']}
                    fresh().preflight()                                                                   # the already-upgraded starting state, repeatedly
                    with pytest.raises(ValueError,match='INSTALLED_POLICY_STATE_NOT_PERMITTED_FOR_MODE'):fresh(False).preflight()      # a mode that does not apply the policy refuses it
                    # 4. a mixed inventory (one function back at its original body) is refused, then repaired through the real policy path
                    stmt,_end=function_statement('ingestion_bolton_allowed');boot.execute(stmt)
                    probe=fresh()
                    with pytest.raises(ValueError,match='INSTALLED_POLICY_STATE_MIXED'):probe.preflight()
                    assert probe.preflight_report['policy_state']=='UNRECOGNISED' and probe.preflight_report['reason_code']=='INSTALLED_POLICY_STATE_MIXED'
                    with first.connection() as c_:first.script(c_,policy_file)
                    fresh().preflight()
                    # 5. an altered body, and an altered search path, are refused in the upgraded state
                    stmt,end=function_statement('ingestion_raise_stop');boot.execute(stmt[:-len(end)]+' '+end)
                    with pytest.raises(ValueError,match='INSTALLED_FUNCTION_CONTENT_CHANGED'):fresh().preflight()
                    boot.execute(stmt)
                    fresh().preflight()
                    proc=boot.execute("SELECT oid::regprocedure::text FROM pg_proc WHERE proname='ingestion_raise_stop' AND pronamespace='public'::regnamespace").fetchone()[0]
                    boot.execute('ALTER FUNCTION '+proc+' SET search_path=public')
                    with pytest.raises(ValueError,match='INSTALLED_FUNCTION_OWNER_OR_CONFIG_CHANGED'):fresh().preflight()
                    boot.execute('ALTER FUNCTION '+proc+' SET search_path=pg_catalog')
                    fresh().preflight()
                    print('ROLLUP_POLICY_LIFECYCLE ok')
                    return

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

                if fault.startswith('stable_'):
                    from verification.ingestion_storage.operational_outcome import session
                    from verification.ingestion_storage.tls_trust import verified_trust
                    from verification.ingestion_storage import restricted_route as rr_, operational_runner as orr_, stable_qualification as sq_
                    from verification.ingestion_storage.operational_publication import GitHub as GitHub_
                    from verification.ingestion_storage.operational_journal import Journal as Journal_
                    from app.ingestion.ledger import digest as digest_
                    from sqlalchemy.engine import make_url as mk_
                    from verification.ingestion_storage.operational_controller import DatabaseBudget as DatabaseBudget_
                    ca,_=verified_trust();WORKER_='ingestion_worker_login';EFFECT_='ingestion_effect_login'
                    pooler_users=[]
                    real_connect=psycopg.Connection.connect.__func__
                    def route_pooler(cls,conninfo='',**kw):
                        if kw.get('host')==rr_.ROUTES['POOLER']['host']:           # the restricted RUNTIME's route; translated to the disposable server
                            assert kw['user'].endswith('.'+rr_.REF) and kw['sslmode']=='verify-full' and kw['hostaddr']=='192.0.2.1'
                            pooler_users.append(kw['user'].split('.')[0])
                            kw=dict(kw,host='127.0.0.1',dbname=info['dbname'],user=kw['user'].split('.')[0])
                            for field in ('sslmode','sslrootcert','hostaddr'):kw.pop(field,None)
                        return real_connect(cls,conninfo,**kw)
                    monkeypatch.setattr(psycopg.Connection,'connect',classmethod(route_pooler))
                    runner.url_factory=lambda r_,p_:rr_.url('POOLER',r_,p_)         # the restricted secrets carry the reviewed pooler form
                    runner.ssl={'sslmode':'verify-full','sslrootcert':str(ca)};runner.hostaddr='192.0.2.1'
                    def roles_state():
                        return boot.execute("SELECT rolname,rolcanlogin,rolpassword IS NULL,rolvaliduntil IS NOT NULL FROM pg_authid WHERE rolname=ANY(%s) ORDER BY rolname",([WORKER_,EFFECT_],)).fetchall()
                    def sessions_of_roles():
                        return boot.execute("SELECT count(*) FROM pg_stat_activity WHERE usename=ANY(%s)",([WORKER_,EFFECT_],)).fetchone()[0]
                    def role_configs():
                        return {r_:sorted(c_ or []) for r_,c_ in boot.execute('SELECT rolname,rolconfig FROM pg_roles WHERE rolname=ANY(%s)',([WORKER_,EFFECT_],)).fetchall()}
                    reviewed_cfg=sorted(['statement_timeout=10s','lock_timeout=3s','idle_in_transaction_session_timeout=20s'])
                    if fault=='stable_provision_failure':
                        original_readback=runner.owner.stable_readback
                        def failing_readback():
                            original_readback();raise Uncertain('DISPOSABLE_READBACK_FAILURE')      # fails AFTER the credentials exist
                        runner.owner.stable_readback=failing_readback
                    lines=[]
                    prov=session(journal,registration['expires_at'],lambda:'hidden fixture input',lambda raw_,started:runner,output=lambda line,**kw:lines.append(line),timing=orr_.MATRIX_TIMING)
                    actual=boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
                    assert actual==ctl and not source_calls and not runner.owner.authorities      # provisioning never touches the control row and issues no grant
                    assert boot.execute("SELECT count(*) FROM public.ingestion_work_items WHERE key<>repeat('0',64)").fetchone()[0]==0 and not boot.execute("SELECT count(*) FROM public.ingestion_work_attempts").fetchone()[0]
                    if fault=='stable_provision_failure':
                        assert prov['status']=='STOP_RECONCILE_NO_RETRY' and prov['access']=='DISABLED_VERIFIED' and prov['cleanup']=='CLOSED',(prov.get('failure'),prov.get('operation_phase'),prov.get('authority_invalidation'),prov['accounting']['administration'].get('teardown_residuals'),prov['accounting']['administration'].get('role_settings'),prov.get('diagnostics'))      # a failure after the credentials exist falls into the ordinary disabling path
                        assert roles_state()==[(EFFECT_,False,True,True),(WORKER_,False,True,True)] and set(ciphertexts)=={'DATABASE_URL'}
                        print('ROLLUP_STABLE',fault,prov['accounting']['administration']['commands'],prov['accounting']['administration']['connections'])
                        return
                    assert prov['status']=='STABLE_CREDENTIALS_PROVISIONED_LOGIN_ENABLED' and prov['cleanup']=='CLOSED' and prov['access']=='LOGIN_ENABLED_BY_DESIGN' and prov['execution_grants_created']==0 and prov['source_observations_attempted']==0 and prov['application_writes']==0
                    assert roles_state()==[(EFFECT_,True,False,True),(WORKER_,True,False,True)] and role_configs()=={WORKER_:reviewed_cfg,EFFECT_:reviewed_cfg}      # login enabled, password present, validity set, reviewed settings kept
                    validity=boot.execute("SELECT min(rolvaliduntil)-now() FROM pg_authid WHERE rolname=ANY(%s)",([WORKER_,EFFECT_],)).fetchone()[0]
                    assert timedelta(days=89,hours=23)<validity<=timedelta(days=90,minutes=5)
                    assert [tuple(m_) for m_ in boot.execute("SELECT member::regrole::text,roleid::regrole::text FROM pg_auth_members WHERE member=ANY(%s::regrole[]) ORDER BY 1",([WORKER_,EFFECT_],)).fetchall()]==[(EFFECT_,'ingestion_effect_broker'),(WORKER_,'ingestion_worker')]
                    assert {'INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL','DATABASE_URL'}==set(ciphertexts) and not runner.owner.urls and prov['owner_verifications_required']
                    secret_urls={WORKER_:mapped_values['INGESTION_WORKER_DATABASE_URL'],EFFECT_:mapped_values['INGESTION_EFFECT_DATABASE_URL']}
                    assert mk_(secret_urls[WORKER_]).username==WORKER_+'.'+rr_.REF and mk_(secret_urls[WORKER_]).password not in journal.file.read_text() and mk_(secret_urls[EFFECT_]).password not in json.dumps(prov)
                    def direct_conn(role_):
                        u_=mk_(secret_urls[role_]);return psycopg.connect(host='127.0.0.1',port=5432,dbname=info['dbname'],user=role_,password=u_.password,autocommit=True,connect_timeout=3)
                    ledger='public.ingestion_work_items'
                    def attempt_sql(conn_,statement,*params):
                        try:conn_.execute(statement,params or None);return 'OK'
                        except psycopg.Error as exc_:return exc_.sqlstate or 'ERR'
                    def step(conn_,op,key,authority='AUTH'):
                        return attempt_sql(conn_,"SELECT public.ingestion_worker_step(%s,%s,0,'probe-owner',%s,'{}'::jsonb,'{}'::jsonb)",op,key,authority)
                    def access_matrix(granted_key=None):
                        out={};w_=direct_conn(WORKER_);e_=direct_conn(EFFECT_)
                        try:
                            out['worker_read_ledger']=attempt_sql(w_,'SELECT count(*) FROM '+ledger)
                            for verb,sql_ in (('insert',"INSERT INTO "+ledger+" (key) VALUES ('probe')"),('update',"UPDATE "+ledger+" SET state='X' WHERE false"),('delete',"DELETE FROM "+ledger+" WHERE false"),('truncate',"TRUNCATE "+ledger)):
                                out['worker_'+verb]=attempt_sql(w_,sql_);out['effect_'+verb]=attempt_sql(e_,sql_)
                            out['effect_read_ledger']=attempt_sql(e_,'SELECT count(*) FROM '+ledger)
                            key=granted_key or 'f'*64
                            for op in ('claim','checkpoint','complete','begin_source','begin_write','block'):out['worker_'+op]=step(w_,op,key)
                            for op in ('fence_effect','resolve_effect','enqueue_child','batch_row','batch_reseal'):out['worker_broker_'+op]=step(w_,op,key);out['effect_'+op]=step(e_,op,key)
                            for op in ('claim','checkpoint','complete','begin_source','begin_write','block'):out['effect_worker_'+op]=step(e_,op,key)
                            w_.execute('BEGIN')
                            out['worker_can_raise_stop']=attempt_sql(w_,"SELECT public.ingestion_raise_stop('probe-stop')");w_.execute('ROLLBACK')      # fail-safe disruption; rolled back here
                            out['effect_can_raise_stop']=attempt_sql(e_,"SELECT public.ingestion_raise_stop('probe-stop')")
                            out['worker_grant_functions']=attempt_sql(w_,"SELECT public.ingestion_register_bolton_exception('{}'::jsonb)")
                            out['worker_acceptance_control']=attempt_sql(w_,"SELECT public.ingestion_acceptance_control()")
                        finally:w_.close();e_.close()
                        return out
                    def assert_matrix(m_,granted):
                        assert m_['worker_read_ledger']=='OK' and m_['effect_read_ledger']=='42501'                       # the worker can READ the ledger (incl. the control row); the effect login cannot
                        for verb in ('insert','update','delete','truncate'):assert m_['worker_'+verb]=='42501' and m_['effect_'+verb]=='42501'      # neither can mutate a table directly, with or without a grant
                        assert all(m_['worker_'+op]!='OK' for op in ('claim','checkpoint','complete','begin_source','begin_write','block'))
                        assert all(m_['worker_broker_'+op]=='42501' for op in ('fence_effect','resolve_effect','enqueue_child','batch_row','batch_reseal'))      # the worker cannot use broker operations
                        assert all(m_['effect_'+op]!='OK' for op in ('fence_effect','resolve_effect','enqueue_child','batch_row','batch_reseal'))
                        assert all(m_['effect_worker_'+op]=='42501' for op in ('claim','checkpoint','complete','begin_source','begin_write','block'))      # the effect login cannot use worker operations
                        assert m_['worker_can_raise_stop']=='OK' and m_['effect_can_raise_stop']=='42501'                  # a compromised worker could PAUSE operations (fail-safe); the effect login cannot
                        assert m_['worker_grant_functions']!='OK' and m_['worker_acceptance_control']=='42501'             # neither login can create grants/exceptions or read the owner-only control view
                    # 1. access WITHOUT a grant
                    no_grant=access_matrix();assert_matrix(no_grant,False)
                    # 2. qualification, invocation 1 (restricted credentials ONLY; no admin object exists in the module) - then a SEPARATE invocation reusing the same credentials
                    def qualify(urls_,budget_factory=None,spacing=(0.0,0.0)):
                        monkeypatch.setattr(sq_,'SPACING_SECONDS',spacing)
                        q_=sq_.Qualification(urls_,emit=lambda e_,p_:None,ssl={'sslmode':'verify-full','sslrootcert':str(ca)},hostaddr='192.0.2.1',**({'budget_factory':budget_factory} if budget_factory else {}))
                        return q_.run()
                    q1=qualify(secret_urls);q2=qualify(dict(secret_urls))
                    for q_ in (q1,q2):
                        assert q_['status']=='STABLE_CREDENTIALS_QUALIFIED' and q_['attempts_total']==2 and q_['use_blocked'] is False and q_['grants_issued']==0 and q_['administrative_credential_present'] is False
                    wprobe=q1['roles'][WORKER_]['attempts'][0]['probe'];assert wprobe['valid_days_remaining']>=89 and wprobe['memberships']==['ingestion_worker'] and wprobe['control_row']['unexpired_grants']==0 and wprobe['control_row']['global_stop_set'] is True
                    assert q1['roles'][EFFECT_]['attempts'][0]['probe']['control_row'] is None and pooler_users==[WORKER_,EFFECT_,WORKER_,EFFECT_]       # one attempt per role per invocation; same credentials
                    assert sessions_of_roles()==0 and secret_urls[WORKER_]==mapped_values['INGESTION_WORKER_DATABASE_URL']                               # (the server-side session readback here is the disposable test's own, not the runtime's)
                    # 3. access DURING an active grant (registered through the owner path), then after its expiry
                    from verification.ingestion_storage.operational_owner import Owner as Owner_
                    from verification.ingestion_storage.operational_runner import item as item_,SCOPE as SCOPE_,CONTRACT as CONTRACT_
                    from app.ingestion.ledger import DEFAULT_LIMITS as DL_
                    granter=Owner_(connector,lambda *_:None,lambda:None,identity=role,expiry=datetime.now(timezone.utc)+timedelta(minutes=30),bindings=runner.bindings)
                    granter.reuse_installed=True;granter.baseline_control_sha256=digest_(ctl);granter.apply_policy=False;granter.permitted_policy_states=('SUCCESSOR_POLICY_APPLIED',)
                    granter.stable_state=True;granter.preflight()
                    root_=item_(dict(subject=SCOPE_,task='DISCOVERY',contract=CONTRACT_,revision='c'*64),max_attempts=1,limits=dict(DL_,requests=10,bytes=3000000,rows=60,pages=6))
                    granter.register([root_],'AUTHORISE_STABLE_ACCESS_PROBE',capture_key=root_['key'],source_calls=1)
                    unexpired=sum(1 for g in boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]['grants'].values() if g['expires_at']>time.time())
                    assert unexpired==1
                    active=access_matrix(root_['key']);assert_matrix(active,True)              # even with a grant: nothing outside the exact binding, no direct mutation, no grant creation
                    controlled=boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
                    for g in controlled['grants'].values():g['expires_at']=0
                    for g in controlled.get('bolton_exceptions',{}).values():g['expires_at']=0
                    boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(controlled),))
                    assert_matrix(access_matrix(),False)
                    # 4. failed qualification: the effect credential no longer matches -> three rejections, stop, retained access reported, nothing disabled by the runtime
                    boot.execute("ALTER ROLE ingestion_effect_login PASSWORD 'a-different-password'")
                    q3=qualify(secret_urls)
                    assert q3['status']=='QUALIFICATION_STOPPED' and q3['stop_reason']=='AUTH_REJECTED_EXHAUSTED' and q3['attempts_total']==4 and q3['roles'][WORKER_]['qualified'] is True and q3['use_blocked'] is True
                    assert [a['reason_code'] for a in q3['roles'][EFFECT_]['attempts']]==['AUTHENTICATION_REJECTED']*3 and all(a['client_closure_verified'] for a in q3['roles'][EFFECT_]['attempts'])
                    assert q3['retained_access'].startswith('BOTH_LOGINS_REMAIN_ENABLED') and roles_state()[0][1] is True and roles_state()[1][1] is True       # the runtime cannot disable: reported, not hidden
                    # 5. uncertain closure stops after a single rejection
                    class UncertainBudget(DatabaseBudget_):
                        def close(self,engines):
                            r_=super().close(engines);r_['cleanup']='UNCERTAIN';r_['connections_closed']=False;return r_
                    q4=qualify(secret_urls,budget_factory=UncertainBudget)
                    assert q4['stop_reason']=='UNCERTAIN_CLOSURE' and q4['attempts_total']==1 and q4['status']=='QUALIFICATION_STOPPED'
                    # 6. a survivor session (documented: expiry and disabling stop NEW logins only)
                    survivor=None
                    if fault=='stable_revoke_survivor':
                        survivor=direct_conn(WORKER_)
                    # 7. the privileged revocation path, as a separate invocation
                    journal2=Journal_(tmp_path/'revoke-run')
                    github2=GitHub_(journal2.emit,lambda:holder['runner'].check(),runner=cli)
                    reg2=dict(registration,mode=orr_.STABLE_REVOKE_MODE)
                    runner2=Runner(reg2,journal2,connector,source_reader=source,github=github2,url_factory=uri,identity=role,memory=None);holder['runner']=runner2
                    runner2.owner.reuse_installed=True;runner2.owner.baseline_control_sha256=digest_(boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0])
                    assert runner2.owner.stable_state is True and runner2.owner.apply_policy is False
                    revoke=session(journal2,registration['expires_at'],lambda:'hidden fixture input',lambda raw_,started:runner2,output=lambda line,**kw:lines.append(line),timing=orr_.MATRIX_TIMING)
                    if survivor is not None:
                        alive=sessions_of_roles()
                        try:
                            assert alive==1 and revoke['status']=='STOP_RECONCILE_NO_RETRY' and revoke['accounting']['administration']['session_disposition'].startswith('UNRESOLVED')       # unprivileged owner: the session is REPORTED, never called closed
                        finally:survivor.close()
                        assert roles_state()==[(EFFECT_,False,True,True),(WORKER_,False,True,True)] and set(ciphertexts)=={'DATABASE_URL'}
                        print('ROLLUP_STABLE',fault,revoke['accounting']['administration']['commands'],revoke['accounting']['administration']['connections'])
                        return
                    assert revoke['status']=='STABLE_CREDENTIALS_REVOKED_ACCESS_DISABLED' and revoke['access']=='DISABLED_VERIFIED' and revoke['cleanup']=='CLOSED' and revoke['execution_grants_created']==0
                    assert roles_state()==[(EFFECT_,False,True,True),(WORKER_,False,True,True)] and set(ciphertexts)=={'DATABASE_URL'} and sessions_of_roles()==0
                    assert not boot.execute("SELECT 1 FROM pg_auth_members WHERE member=ANY(%s::regrole[])",([WORKER_,EFFECT_],)).fetchall() and role_configs()=={WORKER_:reviewed_cfg,EFFECT_:reviewed_cfg}      # settings left in place by design
                    final_ctl=boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
                    assert final_ctl['global_stop']==ctl['global_stop'] and final_ctl['manual_stop']==ctl['manual_stop'] and final_ctl.get('hard_stop_generation')==ctl.get('hard_stop_generation')      # stops intact
                    q5=qualify(secret_urls)
                    assert q5['status']=='QUALIFICATION_STOPPED' and q5['attempts_total']==3 and q5['stop_reason']=='AUTH_REJECTED_EXHAUSTED' and q5['roles'][WORKER_]['qualified'] is False and q5['roles'][EFFECT_]['attempts']==[]          # revoked credentials are rejected (NULL password): the finite sequence ends within its limits
                    print('ROLLUP_STABLE',fault,prov['accounting']['administration']['commands'],prov['accounting']['administration']['connections'],revoke['accounting']['administration']['commands'],revoke['accounting']['administration']['connections'])
                    return

                if fault.startswith('direct_'):
                    from verification.ingestion_storage.operational_outcome import session
                    from verification.ingestion_storage.tls_trust import verified_trust
                    from verification.ingestion_storage import restricted_route as rr_, operational_runner as orr_
                    ca,_=verified_trust();restricted_contacts=[];pooler_restricted=[]
                    real_connect=psycopg.Connection.connect.__func__
                    def route_direct(cls,conninfo='',**kw):
                        user=str(kw.get('user'))
                        if kw.get('host')==rr_.ROUTES['DIRECT']['host']:
                            assert kw['hostaddr']=='198.51.100.20' and kw['port']==5432 and kw['dbname']=='postgres' and kw['sslmode']=='verify-full' and kw['sslrootcert']==str(ca) and kw['prepare_threshold'] is None
                            assert user in ('ingestion_worker_login','ingestion_effect_login')      # the plain role, never the pooler form
                            restricted_contacts.append(user)
                            kw=dict(kw,host='127.0.0.1',dbname=info['dbname'])
                            for field in ('sslmode','sslrootcert','hostaddr'):kw.pop(field,None)
                        elif kw.get('host')==rr_.ROUTES['POOLER']['host'] or user.startswith('ingestion_'):
                            pooler_restricted.append(user)                                       # any restricted contact outside the direct route would be a fallback
                        return real_connect(cls,conninfo,**kw)
                    monkeypatch.setattr(psycopg.Connection,'connect',classmethod(route_direct))
                    runner.url_factory=(lambda r_,p_:rr_.url('POOLER',r_,p_)) if fault=='direct_route_fallback_refused' else (lambda r_,p_:rr_.url('DIRECT',r_,p_))
                    runner.ssl={'sslmode':'verify-full','sslrootcert':str(ca)};runner.hostaddr='192.0.2.1'      # the ADMINISTRATIVE (pooler) address: must never be used for the restricted engines
                    runner.restricted_hostaddr=None if fault=='direct_address_missing' else '198.51.100.20'
                    if fault in {'direct_first_connection_rejected','direct_effect_rejected'}:
                        original_map_d=runner.owner.map_and_activate
                        def map_then_deny_d(*a,**k):
                            original_map_d(*a,**k);boot.execute('ALTER ROLE '+('ingestion_worker_login' if fault=='direct_first_connection_rejected' else 'ingestion_effect_login')+' NOLOGIN')
                        runner.owner.map_and_activate=map_then_deny_d
                    lines=[]
                    result=session(journal,registration['expires_at'],lambda:'hidden fixture input',lambda raw_,started:runner,output=lambda line,**kw:lines.append(line),timing=orr_.MATRIX_TIMING)
                    adm=result['accounting']['administration'];limits=orr_.DIRECT_OWNER_LIMITS
                    actual=boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
                    assert actual==ctl and not runner.owner.authorities and not source_calls and not pooler_restricted      # control row untouched, no grant, no source, no restricted contact outside the direct route
                    assert boot.execute("SELECT count(*) FROM public.ingestion_work_items WHERE key<>repeat('0',64)").fetchone()[0]==0 and not boot.execute("SELECT count(*) FROM public.ingestion_work_attempts").fetchone()[0]
                    assert set(ciphertexts)=={'DATABASE_URL'} and adm['preflight']['policy_state']=='SUCCESSOR_POLICY_APPLIED' and adm['preflight']['permitted_states']==['SUCCESSOR_POLICY_APPLIED']
                    assert boot.execute("SELECT rolname,rolcanlogin,rolpassword IS NULL FROM pg_authid WHERE rolname=ANY(%s) ORDER BY rolname",(['ingestion_worker_login','ingestion_effect_login'],)).fetchall()==[('ingestion_effect_login',False,True),('ingestion_worker_login',False,True)]
                    assert not boot.execute("SELECT 1 FROM pg_auth_members WHERE member=ANY(%s::regrole[])",(['ingestion_worker_login','ingestion_effect_login'],)).fetchall() and not boot.execute("SELECT 1 FROM pg_stat_activity WHERE usename=ANY(%s)",(['ingestion_worker_login','ingestion_effect_login'],)).fetchall()
                    assert adm['role_settings']['state']=='RESTORED_VERIFIED' and {r_:c_ for r_,c_ in boot.execute('SELECT rolname,rolconfig FROM pg_roles WHERE rolname=ANY(%s)',(['ingestion_worker_login','ingestion_effect_login'],)).fetchall()}=={'ingestion_worker_login':None,'ingestion_effect_login':None}
                    assert adm['connections']<=limits['connections'][1] and adm['commands']<=limits['commands'][2] and adm['connections_opened']==adm['connections_closed'] and adm['teardown_residuals']==[]
                    assert result['closure_components']['connections']['status']=='CLOSED' and result['closure_components']['process']['status']=='CLOSED' and result['access']=='DISABLED_VERIFIED' if fault!='direct_diagnostic_success' else True
                    if fault=='direct_diagnostic_success':
                        assert result['status']=='RESTRICTED_ROUTE_QUALIFIED_ACCESS_DISABLED' and result['cleanup']=='CLOSED' and restricted_contacts==['ingestion_worker_login','ingestion_effect_login']      # one attempt per role, worker first
                        slot=list(result['accounting']['runtime']['slot_receipts'].values())[0]['database']
                        assert slot['connection_attempts']==2 and slot['cleanup']=='CLOSED' and slot['connections_closed'] is True and adm['commands']<=limits['commands'][1]
                        assert result['closure_components']['access']=='DISABLED_VERIFIED' and set(adm['first_connection_intervals'])=={'ingestion_worker_login','ingestion_effect_login'}
                    elif fault=='direct_first_connection_rejected':
                        assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['operation_phase']=='RESTRICTED_CONNECTION_QUALIFICATION' and restricted_contacts==['ingestion_worker_login']      # effect never attempted, nothing retried
                    elif fault=='direct_effect_rejected':
                        assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['operation_phase']=='RESTRICTED_CONNECTION_QUALIFICATION' and restricted_contacts==['ingestion_worker_login','ingestion_effect_login']      # the worker connected once, the effect was attempted once and refused; teardown still disabled everything
                    else:
                        assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['operation_phase']=='RESTRICTED_CONNECTION_QUALIFICATION' and restricted_contacts==[]      # refused before ANY restricted contact
                    print('ROLLUP_DIRECT',fault,adm['commands'],adm['connections'],result['status'],result['cleanup'])
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

            if fault in {'worker_connect','post_grant_connect','invalidation_commit_unknown','source_raises','mapping_second_lost_ack','blocked_query','exhausted_normal_budget','role_settings_partial_install','role_settings_failed_qualification','role_settings_uncertain_restoration','settled_first_connection_rejected','settled_stop_during_interval'}:
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
                if fault in {'worker_connect','settled_first_connection_rejected'}:
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
                if fault=='settled_stop_during_interval':
                    def stop_during_interval(seconds):
                        (journal.root/'STOP').write_text('stop');time.sleep(0.01)      # an owner STOP during the settling period
                    runner.settle_sleep=stop_during_interval
                if fault=='exhausted_normal_budget':
                    original_map_budget=runner.owner.map_and_activate
                    def map_then_exhaust(*a,**k):
                        original_map_budget(*a,**k);runner.owner.commands=runner.owner.limits['commands'][0]-1;raise ValueError('ADMIN_COMMAND_BOUND')
                    runner.owner.map_and_activate=map_then_exhaust
                lines=[]
                result=session(journal,registration['expires_at'],lambda:'disposable hidden input',lambda raw,started:runner,output=lambda line,**kw:lines.append(line))
                assert result['status']=='STOP_RECONCILE_NO_RETRY'
                if retained:assert result['preflight']=={'reason_code':'POLICY_STATE_RECOGNISED','policy_state':'SUCCESSOR_POLICY_APPLIED','permitted_states':['ORIGINAL','SUCCESSOR_POLICY_APPLIED']}      # the retained state is recognised, with fixed codes only
                saved=json.loads((journal.root/'final-result.json').read_bytes());assert saved==json.loads(json.dumps(result)) and len(lines)==1
                assert 'private connection URL' not in journal.file.read_text() and 'disposable hidden input' not in lines[0]
                assert result['accounting']['administration']['connections_opened']==result['accounting']['administration']['connections_closed']
                ctl=boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
                if fault=='mapping_second_lost_ack':
                    assert github.mutation_uncertain and not ctl['grants'] and not ctl.get('bolton_exceptions')
                    assert not source_calls and not any(m=='DELETE' for m,p in requests)
                    assert not result['accounting']['runtime']['slot_receipts']
                elif fault in {'worker_connect','settled_first_connection_rejected'}:
                    assert not ctl['grants'] and not ctl.get('bolton_exceptions') and not source_calls
                    assert observed_routes==['ingestion_worker_login']      # exactly ONE restricted contact: the worker; the effect login is never attempted, nothing is polled or retried
                    if fault=='settled_first_connection_rejected':
                        lines_=[json.loads(l) for l in journal.file.read_text().splitlines()];names_=[e['event'] for e in lines_]
                        assert names_.index('settling_started')<names_.index('settling_completed')<names_.index('runtime_connection_intent')
                        assert [e for e in names_ if e=='runtime_connection_intent'].__len__()==1 and result['operation_phase']=='RESTRICTED_CONNECTION_QUALIFICATION' and result['access']=='DISABLED_VERIFIED'
                        intent_=[e['payload'] for e in lines_ if e['event']=='runtime_connection_intent'][0]
                        assert intent_['role']=='ingestion_worker_login' and intent_['attempt']==1 and intent_['first_contact'] is True and intent_['since_activation_seconds']>=0.6 and intent_['since_password_commit_seconds']>=intent_['since_activation_seconds']
                        iv_=result['accounting']['administration']['first_connection_intervals']
                        assert iv_['ingestion_worker_login']['attempt']==1 and iv_['ingestion_effect_login'] is None
                        assert not [u for t,u in contacts if u.startswith('ingestion_') and t<settled_at[0]]
                        assert [u for t,u in contacts if u.startswith('ingestion_')]==['ingestion_worker_login']
                    assert set(ciphertexts)=={'DATABASE_URL'}
                elif fault=='invalidation_commit_unknown':
                    assert result['authority_invalidation']=='UNCERTAIN_RECONCILE' and not any(m=='DELETE' for m,p in requests)
                    assert not source_calls
                elif fault=='settled_stop_during_interval':
                    assert result['operation_phase']=='CREDENTIAL_SETTLING' and result['access']=='DISABLED_VERIFIED' and result['cleanup']=='CLOSED' and not observed_routes      # no restricted contact at all
                    assert not ctl['grants'] and not ctl.get('bolton_exceptions') and not source_calls and set(ciphertexts)=={'DATABASE_URL'} and not result['accounting']['runtime']['slot_receipts']
                    names_=[json.loads(l)['event'] for l in journal.file.read_text().splitlines()];assert 'settling_started' in names_ and 'settling_completed' not in names_ and 'runtime_connection_intent' not in names_
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
                if fault in {'settled_first_connection_rejected','settled_stop_during_interval'}:
                    adm_=result['accounting']['administration']
                    assert adm_['role_settings']['state']=='RESTORED_VERIFIED' and adm_['teardown_residuals']==[] and adm_['session_disposition'] in ('NONE','NOT_EVALUATED') and result['access']=='DISABLED_VERIFIED'
                    assert {r_:c_ for r_,c_ in boot.execute('SELECT rolname,rolconfig FROM pg_roles WHERE rolname=ANY(%s)',(['ingestion_worker_login','ingestion_effect_login'],)).fetchall()}=={'ingestion_worker_login':None,'ingestion_effect_login':None}
                    assert result['closure_components']['connections']['status']=='CLOSED' and result['closure_components']['process']['status']=='CLOSED' and result['cleanup']=='CLOSED'
                    print('ROLLUP_SETTLED_FAILURE',fault,retained,adm_['commands'],adm_['connections'])
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
            if fault=='settled_success':
                for r_,n_ in (('ingestion_worker_login','INGESTION_WORKER_DATABASE_URL'),('ingestion_effect_login','INGESTION_EFFECT_DATABASE_URL')):assert mapped_values[n_]==runner.owner.urls[r_]
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
            print('ROLLUP_ADMIN_COMPLETE',fault,retained,runner.owner.commands,runner.owner.connections)
            if retained:assert runner.owner.preflight_report['policy_state']=='SUCCESSOR_POLICY_APPLIED' and runner.owner.preflight_report['reason_code']=='POLICY_STATE_RECOGNISED'
            if fault=='settled_success':
                lines_=[json.loads(l) for l in journal.file.read_text().splitlines()];names_=[e['event'] for e in lines_]
                assert names_.index('secret_mapping_ack')<names_.index('settling_started')<names_.index('settling_completed')<names_.index('runtime_connection_intent')
                restricted_=[(t,u) for t,u in contacts if u.startswith('ingestion_')];assert restricted_ and min(t for t,u in restricted_)>=settled_at[0]      # nothing contacted either role before the interval ended
                firsts_=[e['payload'] for e in lines_ if e['event']=='runtime_connection_intent' and e['payload'].get('first_contact')]
                assert [f['role'] for f in firsts_]==['ingestion_worker_login','ingestion_effect_login'] and all(f['since_activation_seconds']>=0.6 and f['since_password_commit_seconds']>=f['since_activation_seconds'] for f in firsts_)
                assert result['admin']['first_connection_intervals']['ingestion_worker_login']['attempt']==1
                from sqlalchemy.engine import make_url as mk
                for r_,n_ in (('ingestion_worker_login','INGESTION_WORKER_DATABASE_URL'),('ingestion_effect_login','INGESTION_EFFECT_DATABASE_URL')):
                    assert mapped_values[n_]==runner.owner.urls.get(r_,mapped_values[n_])      # the mapped secret and the qualification URL are the same value (urls are cleared at teardown)
                    password_=mk(mapped_values[n_]).password
                    assert password_ not in journal.file.read_text() and password_ not in json.dumps(result)      # never exposed in the audit or the result
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
