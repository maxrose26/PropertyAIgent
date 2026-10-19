"""Complete stable-credential pipeline against the disposable PG17: real owner controller (separate process state: this one), the HOSTED half as a separate process, restricted logins provisioned
by the real provisioning mode, the real Linux gh against the loopback fixture. Owner preflight -> grant/exception -> capture -> durable evidence -> screening -> authority invalidation, with the
standing credentials retained and unchanged. Loopback only; no production resource."""
import json,os,secrets,subprocess,sys,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
import psycopg,pytest
from psycopg import sql
from sqlalchemy.engine import URL
from app.ingestion.ledger import digest
from verification.ingestion_storage import operational_runner as orr,stable_pipeline as sp,restricted_route as rr
from verification.ingestion_storage.operational_runner import Runner
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_owner import ROLES,Owner
from verification.ingestion_storage.operational_outcome import session
from verification.ingestion_storage.operational_publication import GitHub
from verification.ingestion_storage.tls_trust import verified_trust
from tests.storage_gh_fixture import real_gh_store

WORKER='ingestion_worker_login';EFFECT='ingestion_effect_login'
FAULTS=['success','idle_pooled_session','active_session_blocks','unexpired_grant_blocks','valid_until_mismatch_blocks','source_raises','screening_stops','owner_wait_expires','wrong_revision','wrong_executable']


@pytest.mark.parametrize('real_gh_store',['operational'],indirect=True)
@pytest.mark.parametrize('fault',FAULTS)
def test_stable_pipeline_lifecycle(tmp_path,record_property,real_gh_store,fault,monkeypatch):
    raw=os.environ.get('INGESTION_PROVISIONING_TEST_URL')
    if not raw:pytest.skip('fixed disposable PG17 required')
    info=psycopg.conninfo.conninfo_to_dict(raw)
    assert (info['host'],info['port'],info['dbname'],info['user'])==('127.0.0.1','5432','ingestion_provisioning_test','provisioning_bootstrap')
    password=secrets.token_urlsafe(48);role='provisioning_migrator'
    metadata,secret,ciphertexts,requests=real_gh_store
    def connector():return psycopg.connect(**{**info,'user':role,'password':password},autocommit=True,prepare_threshold=None,connect_timeout=3)
    registration=dict(expires_at=(datetime.now(timezone.utc)+timedelta(minutes=100)).isoformat(),revision='a'*40,controller_sha256='b'*64,manifest_sha256='c'*64,evidence_head='1'*40,
                      evidence_directory=sp.EVIDENCE_DIRECTORY)
    from tests.test_discovery_ingestion_provisioning_pg import ROLES as base_roles,PACKAGE
    extra=['ingestion_effect_login','ingestion_effect_broker','ingestion_recovery_operator']
    mapped_values={}
    def cli(command,**kwargs):
        if command[1:3]==['secret','set']:mapped_values[command[3]]=kwargs['input'].decode()
        if command[1:4]==['api','--method','GET']:kwargs['allow_failure']=True      # reads return their exit status and stderr (the production runner does), so a probe can tell a 404 from any other failure
        return metadata.cli(command,**kwargs)
    with psycopg.connect(raw,autocommit=True) as boot:
        boot.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER CREATEROLE CREATEDB BYPASSRLS NOINHERIT PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
        boot.execute(sql.SQL('GRANT USAGE,CREATE ON SCHEMA public TO {} WITH GRANT OPTION').format(sql.Identifier(role)))
        boot.execute(sql.SQL('GRANT CONNECT ON DATABASE ingestion_provisioning_test TO {} WITH GRANT OPTION').format(sql.Identifier(role)))
        boot.execute(sql.SQL('GRANT SELECT(rolname,rolpassword) ON pg_catalog.pg_authid TO {}').format(sql.Identifier(role)))
        boot.execute(sql.SQL('GRANT pg_read_all_stats TO {} WITH INHERIT TRUE').format(sql.Identifier(role)))      # the monitoring privilege the session readback needs; its absence blocks (tested in the pure evaluation)
        boot.execute('CREATE SCHEMA extensions')
        boot.execute("CREATE EXTENSION pg_stat_statements WITH SCHEMA extensions VERSION '1.11'")
        boot.execute(sql.SQL('GRANT USAGE ON SCHEMA extensions TO {}').format(sql.Identifier(role)))
        try:
            with connector() as c:
                c.execute((PACKAGE/'install.sql').read_text())
                c.execute('REVOKE ingestion_worker FROM ingestion_worker_login')
                c.execute('REVOKE ingestion_storage_operator FROM ingestion_storage_login')
            boot.execute("SELECT public.ingestion_raise_stop('STORAGE_TEST_STOP')")
            # ---------------------------------------------------------------- fixture: the already-installed, access-disabled generation-1 state, then REAL provisioning
            prov_journal=Journal(tmp_path/'provisioning');holder={}
            github=GitHub(prov_journal.emit,lambda:holder['runner'].check(),runner=cli)
            def uri(r,p):return rr.url('POOLER',r,p)
            runner=Runner(dict(registration,mode=orr.STABLE_PROVISION_MODE),prov_journal,connector,source_reader=lambda row:None,github=github,url_factory=uri,identity=role,memory=None);holder['runner']=runner
            installer=Owner(connector,lambda *_:None,lambda:None,identity=role,expiry=runner.expiry,bindings=runner.bindings)
            installer.install()
            boot.execute('ALTER ROLE ingestion_worker_login NOLOGIN PASSWORD NULL');boot.execute('ALTER ROLE ingestion_effect_login NOLOGIN PASSWORD NULL')
            with connector() as migration:
                migration.execute('REVOKE ingestion_worker FROM ingestion_worker_login GRANTED BY CURRENT_USER');migration.execute('REVOKE ingestion_effect_broker FROM ingestion_effect_login GRANTED BY CURRENT_USER')
            ctl=boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
            ctl['hard_stop_generation']=1;ctl['last_hard_stop']='OPERATIONAL_FIRST_CONNECTION_FAILURE_CLEANUP_20261018'
            boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
            runner.owner.reuse_installed=True;baseline=digest(ctl);runner.owner.baseline_control_sha256=baseline
            with installer.connection() as c_:installer.script(c_,Path('docs/design/ingestion-operational-required-20261018/successor-policy.sql'))
            prov=session(prov_journal,registration['expires_at'],lambda:'hidden fixture input',lambda raw_,started:runner,output=lambda *a,**k:None,timing=orr.MATRIX_TIMING)
            assert prov['status']=='STABLE_CREDENTIALS_PROVISIONED_LOGIN_ENABLED' and prov['cleanup']=='CLOSED'
            urls={WORKER:mapped_values['INGESTION_WORKER_DATABASE_URL'],EFFECT:mapped_values['INGESTION_EFFECT_DATABASE_URL']}
            from sqlalchemy.engine import make_url
            passwords={r:make_url(u).password for r,u in urls.items()}
            def roles_state():
                return boot.execute("SELECT rolname,rolcanlogin,rolpassword IS NOT NULL,rolvaliduntil,rolconnlimit FROM pg_authid WHERE rolname=ANY(%s) ORDER BY rolname",([WORKER,EFFECT],)).fetchall()
            def memberships():
                return [tuple(m) for m in boot.execute("SELECT member::regrole::text,roleid::regrole::text FROM pg_auth_members WHERE member=ANY(%s::regrole[]) ORDER BY 1",([WORKER,EFFECT],)).fetchall()]
            def role_configs():
                return {r:sorted(c or []) for r,c in boot.execute('SELECT rolname,rolconfig FROM pg_roles WHERE rolname=ANY(%s)',([WORKER,EFFECT],)).fetchall()}
            def control():
                return boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
            def items():
                return boot.execute("SELECT key,state FROM public.ingestion_work_items WHERE key<>repeat('0',64) ORDER BY key").fetchall()
            def role_sessions():
                return boot.execute("SELECT count(*) FROM pg_stat_activity WHERE usename=ANY(%s)",([WORKER,EFFECT],)).fetchone()[0]
            standing_before=(roles_state(),memberships(),role_configs());valid_until=min(r[3] for r in standing_before[0]).astimezone(timezone.utc).isoformat()
            ctl_before=control();assert ctl_before==ctl and digest(ctl_before)==baseline
            monkeypatch.setitem(orr.PIPELINE_BINDING,'valid_until',valid_until);monkeypatch.setitem(orr.PIPELINE_BINDING,'poll_seconds',1.0)      # polling is bounded by the request allowance; a 0.1 s interval would exhaust it long before the hosted job finishes
            monkeypatch.setitem(orr.PIPELINE_BINDING,'capture_wait_seconds',3 if fault=='owner_wait_expires' else 120);monkeypatch.setitem(orr.PIPELINE_BINDING,'screening_wait_seconds',120)

            # ---------------------------------------------------------------- fault set-up that must be visible to the FIXED READ-ONLY owner phase
            held=[]
            def role_connection(role_name,kind):
                u=make_url(urls[role_name])
                conn=psycopg.connect(host='127.0.0.1',port=5432,dbname=info['dbname'],user=role_name,password=u.password,autocommit=True,connect_timeout=3)
                held.append(conn);return conn
            if fault=='idle_pooled_session':role_connection(WORKER,'idle').execute('SELECT 1')      # an idle pooled backend: reported accurately, NOT a leak, does not block
            if fault=='active_session_blocks':
                c=role_connection(WORKER,'tx');c.autocommit=False;c.execute('SELECT 1')      # idle in transaction
            if fault=='unexpired_grant_blocks':
                odd=json.loads(json.dumps(ctl));odd['grants']['EARLIER_UNEXPIRED']=dict(expires_at=time.time()+3600)
                boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(odd),))
                ctl_before=odd
            if fault=='valid_until_mismatch_blocks':boot.execute("ALTER ROLE ingestion_worker_login VALID UNTIL '2030-01-01 00:00:00+00'")

            # ---------------------------------------------------------------- the OWNER controller (pipeline mode)
            owner_journal=Journal(tmp_path/'owner');holder2={}
            github_o=GitHub(owner_journal.emit,lambda:holder2['runner'].check(),runner=cli,bound=orr.PIPELINE_GITHUB_BOUND)
            orunner=Runner(dict(registration,mode=orr.PIPELINE_MODE),owner_journal,connector,source_reader=lambda row:(_ for _ in ()).throw(AssertionError('owner never reads a source')),github=github_o,url_factory=uri,identity=role,memory=None);holder2['runner']=orunner
            orunner.owner.reuse_installed=True;orunner.owner.baseline_control_sha256=baseline
            orunner.pipeline_sleep=lambda s:time.sleep(min(s,1.0))
            import re as re_
            stop_codes=[];FIXED_CODE=re_.compile(r'[A-Z][A-Z0-9_]{2,79}')
            original_failed=orunner.failed
            def failed_with_code(exc):      # rehearsal only: the exception's message when (and only when) it is one of the fixed reason codes of the controllers; anything else is never exported
                text=exc.args[0] if getattr(exc,'args',None) and isinstance(exc.args[0],str) else ''
                stop_codes.append(dict(exception=type(exc).__name__,code=text if FIXED_CODE.fullmatch(text) else 'NOT_A_FIXED_CODE'))
                return original_failed(exc)
            orunner.failed=failed_with_code
            ca,_=verified_trust()
            hosted_dir=tmp_path/'hosted-out';spawned=[]
            plan=dict(disposable='LOOPBACK_ONLY',fault=fault,dbname=info['dbname'],gh=metadata.gh,gh_env=metadata.fixture_env(),evidence_head=registration['evidence_head'],manifest_sha256=registration['manifest_sha256'],controller_sha256=registration['controller_sha256'],revision=registration['revision'],output=str(hosted_dir))
            plan_path=tmp_path/'plan.json';plan_path.write_text(json.dumps(plan))
            def start_hosted():
                env=dict(os.environ,INGESTION_ACCEPTANCE_DISPOSABLE='PG17_ONLY',REHEARSAL_URLS=json.dumps(urls),PYTHONPATH=str(Path.cwd()),PYTHONDONTWRITEBYTECODE='1')
                # detached (not a child of this process), as the hosted job is a different machine in production
                subprocess.run(['sh','-c','"$0" -B -m tests.stable_pipeline_rehearsal "$1" >"$2" 2>&1 &',sys.executable,str(plan_path),str(tmp_path/'hosted.log')],env=env,check=True,timeout=20)
                spawned.append(True)
            original_register=orunner.owner.register
            def register(items_,authority,**kw):
                out=original_register(items_,authority,**kw)
                if authority.endswith('_CAPTURE') and fault!='owner_wait_expires':
                    for conn in held:      # the pooler recycles an idle backend; with a connection limit of 1 a held backend would otherwise be the role's only slot
                        conn.close()
                    held.clear();start_hosted()      # the restricted job is dispatched only after the owner registered the capture authority
                return out
            orunner.owner.register=register
            # the rehearsal compares process-level resource baselines; the hosted job is a different process
            lines=[]
            try:
                result=session(owner_journal,registration['expires_at'],lambda:'hidden fixture input',lambda raw_,started:orunner,output=lambda line,**kw:lines.append(line),timing=orr.PIPELINE_TIMING)
                if spawned:
                    end=time.monotonic()+60
                    while not (hosted_dir/'rehearsal-done').exists() and time.monotonic()<end:time.sleep(0.2)
            finally:
                for conn in held:
                    try:conn.close()
                    except Exception:pass
            owner_summary=dict(fault=fault,status=result.get('status'),cleanup=result.get('cleanup'),access=result.get('access'),invalidation=result.get('authority_invalidation'),phase=result.get('operation_phase'),
                               failure=result.get('failure'),stop_codes=stop_codes,hosted_stop_code=(json.loads((hosted_dir/'rehearsal-stop-code').read_text()) if (hosted_dir/'rehearsal-stop-code').exists() else None),accounting=orunner.owner.accounting(),owner_connections=orunner.owner.connections,owner_commands=orunner.owner.commands,github_requests=orunner.github.requests)
            print('PIPELINE_OWNER_RESULT',json.dumps(owner_summary,default=str,sort_keys=True))      # before any assertion can hide it
            record_property('pipeline_owner_result',json.dumps(owner_summary,default=str,sort_keys=True))
            hosted_log=(tmp_path/'hosted.log').read_text() if (tmp_path/'hosted.log').exists() else ''
            hosted_final=json.loads((hosted_dir/'final-result.json').read_bytes()) if (hosted_dir/'final-result.json').exists() else None
            source_calls=int((hosted_dir/'rehearsal-source-calls').read_text()) if (hosted_dir/'rehearsal-source-calls').exists() else 0
            ctl_after=control()
            if fault in ('success','idle_pooled_session') and hosted_final and hosted_final['status']=='STOP_RECONCILE_NO_RETRY':
                events_=[json.loads(l) for l in (hosted_dir/'events.jsonl').read_text().splitlines()] if (hosted_dir/'events.jsonl').exists() else []
                pytest.fail(json.dumps(dict(owner_stop_codes=stop_codes,hosted_stop_code=(hosted_dir/'rehearsal-stop-code').read_text() if (hosted_dir/'rehearsal-stop-code').exists() else None,hosted=dict(operation_phase=hosted_final.get('operation_phase'),failure=hosted_final.get('failure')),qualification=hosted_final.get('qualification'),
                            events=[(e['event'],e['payload'] if e['event'] in ('stopped','source_invocation_returned','capture_authority_observed') and len(json.dumps(e['payload']))<1500 else None) for e in events_][-14:],log=hosted_log[-1500:],rehearsal_exception=(hosted_dir/'rehearsal-exception').read_text() if (hosted_dir/'rehearsal-exception').exists() else None,steps=(hosted_dir/'rehearsal-steps').read_text() if (hosted_dir/'rehearsal-steps').exists() else None,control=json.dumps({k:v for k,v in control().items() if k!='grants'},default=str)[:600],grants=json.dumps({a:dict(expires=g.get('expires_at'),source_calls=g.get('source_calls')) for a,g in control().get('grants',{}).items()},default=str)[:600],exceptions=json.dumps({a:dict(expires=e.get('expires_at'),gen=e.get('hard_stop_generation')) for a,e in control().get('bolton_exceptions',{}).items()},default=str)[:600]),default=str)[:9000])
            text=owner_journal.file.read_text()+json.dumps(result)+((hosted_dir/'events.jsonl').read_text() if (hosted_dir/'events.jsonl').exists() else '')
            for r,p in passwords.items():assert p and p not in text and p not in hosted_log      # no password or verifier value in any audit, result or log
            assert 'postgresql://' not in text
            # ---------------------------------------------------------------- invariants on EVERY path: stops preserved, credentials untouched, execution authority ended or never issued
            assert ctl_after['global_stop']==ctl['global_stop'] and (ctl_after.get('hard_stop_generation')==1 or (fault=='source_raises' and ctl_after.get('hard_stop_generation')==2))      # a failed source request raises the accepted fail-safe stop, which advances the generation
            if fault!='source_raises':assert ctl_after['manual_stop']=='STORAGE_TEST_STOP'      # a failed source request raises the accepted fail-safe stop (the owner reconciles it); every other path preserves it exactly
            standing_after=(roles_state(),memberships(),role_configs())
            if fault!='valid_until_mismatch_blocks':assert standing_after==standing_before      # no password change, no membership change, no role-setting change, no secret change
            assert set(ciphertexts)=={'DATABASE_URL','INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL'} and not orunner.owner.urls
            ours=[a for a in ctl_after.get('grants',{}) if a.startswith(orr.PIPELINE_AUTHORITY)]      # exactly the authorities THIS execution registered
            for a in ours:      # every one of them is explicitly ENDED (expiry zero), on success and on every failure - never merely left to time out
                assert ctl_after['grants'][a]['expires_at']==0 and ctl_after.get('bolton_exceptions',{}).get(a,{}).get('expires_at',0)==0,(a,owner_summary)
            assert {a:g for a,g in ctl_after.get('grants',{}).items() if a not in ours}==ctl_before.get('grants',{})      # unrelated grants (expired or live) are untouched
            assert {a:e for a,e in ctl_after.get('bolton_exceptions',{}).items() if a not in ours}==ctl_before.get('bolton_exceptions',{})
            if fault not in ('source_raises',):assert {k:ctl_after.get(k) for k in ('global_stop','manual_stop','hard_stop_generation','last_hard_stop')}=={k:ctl_before.get(k) for k in ('global_stop','manual_stop','hard_stop_generation','last_hard_stop')}      # the stops and the generation are exactly as they were
            if fault=='source_raises':      # the NEWER stop raised by the failed source request is preserved, never rolled back by the invalidation
                assert ctl_after['manual_stop']=='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE' and ctl_after['hard_stop_generation']==2 and ctl_after['global_stop']==ctl_before['global_stop']
            caps=orr.PIPELINE_OWNER_LIMITS;ended_normally=result['status'].startswith('STABLE_PIPELINE_AUTHORITY_COMPLETED')
            assert orunner.owner.opened==orunner.owner.closed and orunner.owner.connections<=(caps['connections'][0] if ended_normally else caps['connections'][1]) and orunner.owner.commands<=(caps['commands'][1] if ended_normally else caps['commands'][2]),owner_summary
            if fault in ('source_raises','owner_wait_expires','screening_stops'):assert result['authority_invalidation'] in ('ACKNOWLEDGED_READBACK','ALREADY_INVALIDATED_READBACK'),owner_summary      # a failure still ends the authority and says so only after a readback
            assert result['application_writes']==0 and result['stage4']=='OPEN' and result['pipeline_retry']=='HELD'
            if fault in ('active_session_blocks','unexpired_grant_blocks','valid_until_mismatch_blocks'):
                # the fixed read-only phase found a mismatch: NOTHING was issued, nothing started, nothing mutated
                assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['authority_invalidation']=='NOT_REQUIRED_NO_AUTHORITY' and not spawned and not items() and source_calls==0
                assert ctl_after==ctl_before and not orunner.owner.authorities
                expected_finding={'active_session_blocks':'ROLE_SESSION_NOT_IDLE','unexpired_grant_blocks':'UNEXPIRED_GRANT_PRESENT','valid_until_mismatch_blocks':'VALID_UNTIL_MISMATCH'}[fault]
                events=[json.loads(l) for l in owner_journal.file.read_text().splitlines()];readbacks=[e['payload'] for e in events if e['event']=='pipeline_readback']
                assert len(readbacks)==1 and expected_finding in readbacks[0]['findings'] and readbacks[0]['query_text_read'] is False and readbacks[0]['password_values_read'] is False
                assert readbacks[0]['statements']<=12
                return
            events=[json.loads(l) for l in owner_journal.file.read_text().splitlines()];names=[e['event'] for e in events]
            readbacks=[e['payload'] for e in events if e['event']=='pipeline_readback']
            assert names.index('pipeline_readback')<names.index('owner_registration_committed')      # persisted BEFORE any grant mutation
            assert readbacks[0]['label']=='BEFORE_ANY_GRANT' and readbacks[0]['findings']==[] and readbacks[0]['statements']==9
            if fault=='idle_pooled_session':assert readbacks[0]['notes']==['IDLE_POOLED_BACKENDS_OBSERVED_NOT_CLASSIFIED_AS_A_LEAK'] and readbacks[0]['sessions'] and readbacks[0]['sessions'][0][2]=='idle'
            capture_grants=[a for a in ctl_after['grants'] if a.endswith('_CAPTURE')]
            assert capture_grants and ctl_after['grants'][capture_grants[0]]['expires_at']==0      # invalidated (never merely expired by time)
            if fault=='owner_wait_expires':
                assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['authority_invalidation']=='ACKNOWLEDGED_READBACK' and result['access']=='AUTHORITY_INVALIDATED_STANDING_CREDENTIALS_UNCHANGED' and not spawned and source_calls==0
                return
            if not (spawned and (hosted_dir/'rehearsal-done').exists()):
                pytest.fail(json.dumps(dict(owner=dict(status=result.get('status'),failure=result.get('failure'),stop_codes=stop_codes,phase=result.get('operation_phase'),invalidation=result.get('authority_invalidation')),owner_events=[e['event'] for e in events][-25:],hosted_log=hosted_log[-1500:],hosted_files=sorted(p.name for p in hosted_dir.iterdir()) if hosted_dir.exists() else None),default=str)[:6000])
            if fault in ('wrong_revision','wrong_executable'):      # the hosted job refuses to run an unapproved checkout: ZERO source requests, a fixed reason, authorities ended
                assert source_calls==0 and hosted_final['status']=='STOP_RECONCILE_NO_RETRY' and hosted_final['stop_reason']=='CHECKOUT_BINDING_MISMATCH'
                assert result['authority_invalidation'] in ('ACKNOWLEDGED_READBACK','ALREADY_INVALIDATED_READBACK')
                return
            if fault=='source_raises':
                assert source_calls==1 and hosted_final['status']=='STOP_RECONCILE_NO_RETRY'      # one source request; NO replay
                assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['authority_invalidation']=='ACKNOWLEDGED_READBACK' and not [a for a in ctl_after['grants'] if a.endswith('_SCREEN')]
                return
            assert source_calls==1,json.dumps(dict(hosted=hosted_final and {k:hosted_final.get(k) for k in ('status','operation_phase','failure')},qualification=hosted_final and hosted_final.get('qualification'),log=hosted_log[-1500:]),default=str)[:6000]
            screen_grants=[a for a in ctl_after['grants'] if a.endswith('_SCREEN')];assert screen_grants and ctl_after['grants'][screen_grants[0]]['expires_at']==0
            if fault=='screening_stops':
                assert hosted_final['status']=='STOP_RECONCILE_NO_RETRY' and result['status']=='STABLE_PIPELINE_ENDED_INCOMPLETE_AUTHORITY_INVALIDATED' and result['screening']=='INCOMPLETE' and result['cleanup']=='CLOSED'
                assert any(state!='COMPLETE' for _,state in items())      # the retained capture is preserved; screening is incomplete and is reported as such, not as success
                return
            # ---------------------------------------------------------------- success
            assert result['authority_invalidation']=='ACKNOWLEDGED_READBACK' and result['status']=='STABLE_PIPELINE_AUTHORITY_COMPLETED_AUTHORITY_INVALIDATED' and result['cleanup']=='CLOSED' and result['screening']=='COMPLETE' and result['credentials'].startswith('UNCHANGED')
            assert hosted_final['status'] in ('STABLE_PIPELINE_CAPTURE_SCREENING_COMPLETED_RESTRICTED_RUNTIME_ONLY','PARTIAL_PROPOSAL_COVERAGE') and hosted_final['cleanup']=='CLOSED'
            assert hosted_final['qualification']['status']=='STABLE_CREDENTIALS_QUALIFIED' and hosted_final['qualification']['accounting']['client_closure']['status']=='VERIFIED_FOR_EVERY_ATTEMPT'
            assert hosted_final['rows']==60 and hosted_final['batches']==12 and hosted_final['credential_changes']==0 and hosted_final['grants_issued']==0 and hosted_final['application_writes']==0
            assert result['readback_after']['findings']==[] and result['readback_before']['findings']==[]
            assert all(state=='COMPLETE' for _,state in items() if state)
            end=time.monotonic()+10
            while role_sessions() and time.monotonic()<end:time.sleep(0.2)
            assert role_sessions()==0      # the hosted job's client closure is confirmed by a server observation here (a rehearsal observation; production leaves this to the owner readback)
            print('ROLLUP_PIPELINE owner_connections',orunner.owner.connections,'owner_commands',orunner.owner.commands,'github_requests',orunner.github.requests,
                  'hosted_runtime',json.dumps({k:v for k,v in hosted_final['accounting']['runtime'].items() if k!='slot_receipts'}),'hosted_slots',len(hosted_final['slot_receipts']))
            record_property('pipeline_rollup',json.dumps(dict(owner_connections=orunner.owner.connections,owner_commands=orunner.owner.commands)))
        finally:
            boot.execute('DROP TABLE IF EXISTS public.ingestion_work_attempts,public.ingestion_work_items CASCADE')
            boot.execute('DROP EXTENSION IF EXISTS pg_stat_statements')
            boot.execute('DROP SCHEMA IF EXISTS extensions')
            for r in [*extra,*base_roles,role]:
                if boot.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(r,)).fetchone():boot.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(r)))
            for r in [*extra,*base_roles,role]:boot.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(r)))
