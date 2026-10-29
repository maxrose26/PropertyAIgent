"""The fixed Oldham read-only inspection against a disposable PostgreSQL with the real reviewed installations. Synthetic credentials; the fixed disposable service only; nothing production.

State is observed from outside the inspected connection by the bootstrap superuser (catalogue fingerprints, session list), and every statement the inspection sends is recorded at the driver."""
import hashlib,json,re,time
from pathlib import Path
import pytest
from verification.ingestion_storage import oldham_inspection as oi
from verification.ingestion_storage import admin_connection_probe as ap
from verification.ingestion_storage import oldham_policy
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_owner import PKG,GENERATION3_SCREENING_V3_POLICY
from verification.ingestion_storage.operational_preparation import Progress
from verification.ingestion_storage.tls_trust import owned_resources
from tests.e2e_pg_world import disposable_world
from tests.test_ingestion_admin_connection_probe import Memory

MIGRATOR='provisioning_migrator'


@pytest.fixture
def world():
    yield from disposable_world()


def admin(world,script):
    with world['connect'](MIGRATOR) as c:c.execute(script)


def install_v3(world):
    admin(world,(PKG/'successor-policy.sql').read_text());admin(world,GENERATION3_SCREENING_V3_POLICY.read_text())


def install_oldham(world):
    install_v3(world);admin(world,oldham_policy.installation_script())


def visibility(world):
    boot=world['boot']
    boot.execute('GRANT SELECT (rolname,rolpassword) ON pg_authid TO provisioning_migrator');boot.execute('GRANT pg_read_all_stats TO provisioning_migrator WITH INHERIT TRUE, SET FALSE')


class Recording:
    """A driver-level recorder: every statement text and parameters, the close, and an optional injected failure."""
    def __init__(self,connection,log,fail_on=None,close_first=False,slow=0):
        self.connection=connection;self.log=log;self.fail_on=fail_on;self.close_first=close_first;self.slow=slow
    def execute(self,statement,params=None):
        self.log.append(statement)
        if self.slow:time.sleep(self.slow)
        if self.fail_on and statement==self.fail_on:
            if self.close_first:self.connection.close()
            raise RuntimeError('injected failure with private text postgresql://u:SECRETVALUE@h/db')
        return self.connection.execute(statement,params) if params is not None else self.connection.execute(statement)
    def close(self):self.connection.close()
    @property
    def closed(self):return self.connection.closed


def run(world,tmp_path,*,fail_on=None,close_first=False,bound=None,monkeypatch=None,slow=0):
    log=[];holder={}
    def connect():
        holder['raw']=world['connect'](MIGRATOR);holder['rec']=Recording(holder['raw'],log,fail_on,close_first,slow);return holder['rec']
    j=Journal(tmp_path/('i%d'%time.monotonic_ns()))
    runner=oi.InspectionRunner(j,connect,Progress(),Memory(),baseline=owned_resources(),started=time.monotonic())
    if bound and monkeypatch:
        for k,v in bound.items():monkeypatch.setitem(oi.BOUND,k,v)
    return runner.execute(),log,j,holder


def fingerprint(world):
    boot=world['boot']
    queries=["SELECT md5(string_agg(p.oid::text||p.proname||md5(p.prosrc)||coalesce(p.proacl::text,'')||p.proowner::text||coalesce(p.proconfig::text,''),',' ORDER BY p.oid)) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'",
             "SELECT md5(string_agg(r::text,',' ORDER BY rolname)) FROM pg_roles r","SELECT md5(string_agg(a.rolname||coalesce(a.rolpassword,''),',' ORDER BY a.rolname)) FROM pg_authid a",
             "SELECT md5(coalesce(string_agg(m::text,',' ORDER BY roleid,member),'')) FROM pg_auth_members m","SELECT md5(coalesce(string_agg(c.relname||coalesce(c.relacl::text,''),',' ORDER BY c.oid),'')) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'",
             "SELECT md5(coalesce(string_agg(s::text,',' ORDER BY setrole),'')) FROM pg_db_role_setting s","SELECT count(*) FROM public.ingestion_work_items","SELECT md5(coalesce(string_agg(w::text,',' ORDER BY key),'')) FROM public.ingestion_work_items w"]
    return [boot.execute(q).fetchone()[0] for q in queries]


def test_a_recognised_pre_oldham_installation_is_reported_exactly_and_unchanged(world,tmp_path):
    install_v3(world);before=fingerprint(world)
    result,log,j,_=run(world,tmp_path)
    inspection=result['inspection']
    assert result['status']=='OLDHAM_READONLY_INSPECTION_COMPLETE' and result['cleanup']=='CLOSED'
    f=inspection['functions'];assert (f['state'],f['recognised'],f['is_the_retained_v3_state'],f['oldham_helper_present'])==('RECOGNISED_PRE_OLDHAM','GENERATION3_SCREENING_V3_APPLIED',True,False)
    assert inspection['privileges']['discrepancies']==[] and fingerprint(world)==before


def test_the_exact_reviewed_oldham_installation_is_recognised_and_runtime_logins_have_no_execute(world,tmp_path):
    install_oldham(world)
    result,*_=run(world,tmp_path);f=result['inspection']['functions']
    assert (f['state'],f['recognised'],f['oldham_helper_signature_and_definer_as_reviewed'])==('OLDHAM_EXACT_INSTALLATION','OLDHAM_EXACT',True)
    helper=[r for r in result['inspection']['privileges']['function_execute'] if r[0]=='ingestion_oldham_allowed']
    assert sorted(r[1] for r in helper)==sorted(oi.RUNTIME_LOGINS) and all(r[2] is False for r in helper) and result['inspection']['privileges']['discrepancies']==[]


def test_the_fixture_default_installation_is_not_a_reviewed_state_and_is_not_silently_accepted(world,tmp_path):
    result,*_=run(world,tmp_path)
    assert result['inspection']['functions']['state']=='UNEXPECTED_OR_MIXED'


def variant(world,statements,*,install=install_oldham):
    install(world)
    for sql in statements:world['boot'].execute(sql)


@pytest.mark.parametrize('name,statements,install,state',[
    ('missing_function',["DROP FUNCTION public.ingestion_register_bolton_exception(jsonb)"],install_v3,'MISSING_OBJECTS'),
    ('helper_dropped_worker_substituted',["DROP FUNCTION public.ingestion_oldham_allowed(jsonb,text,text,jsonb) CASCADE"],install_oldham,'MISSING_OBJECTS'),
    ('owner_changed',["ALTER FUNCTION public.ingestion_oldham_allowed(jsonb,text,text,jsonb) OWNER TO provisioning_bootstrap"],install_oldham,'UNEXPECTED_OR_MIXED'),
    ('search_path_changed',["ALTER FUNCTION public.ingestion_oldham_allowed(jsonb,text,text,jsonb) SET search_path=public"],install_oldham,'UNEXPECTED_OR_MIXED'),
    ('overload_added',["CREATE FUNCTION public.ingestion_oldham_allowed(x integer) RETURNS boolean LANGUAGE sql AS 'SELECT true'"],install_oldham,'UNEXPECTED_OR_MIXED'),
    ('body_edited',["CREATE OR REPLACE FUNCTION public.ingestion_bolton_allowed(ctl jsonb, authority text, subject jsonb) RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog AS 'SELECT true'"],install_v3,'UNEXPECTED_OR_MIXED'),
])
def test_unexpected_and_partial_installations_are_named_not_blended(world,tmp_path,name,statements,install,state):
    variant(world,statements,install=install)
    result,*_=run(world,tmp_path);f=result['inspection']['functions']
    assert f['state']==state,f
    assert result['status']=='OLDHAM_READONLY_INSPECTION_COMPLETE'      # a discrepancy is a report, never a failure and never an installation


def test_privilege_discrepancies_are_reported_as_fixed_codes(world,tmp_path):
    install_oldham(world);boot=world['boot']
    boot.execute('GRANT EXECUTE ON FUNCTION public.ingestion_oldham_allowed(jsonb,text,text,jsonb) TO ingestion_worker_login')
    boot.execute('GRANT INSERT ON public.applications TO ingestion_application_writer')
    boot.execute('GRANT SELECT ON public.application_lifecycle_events TO ingestion_worker')
    result,*_=run(world,tmp_path)
    assert result['inspection']['privileges']['discrepancies']==['EXECUTE_DIFFERS:ingestion_oldham_allowed:ingestion_worker_login','TABLE_PRIVILEGE_DIFFERS:ingestion_application_login:applications',
                                                                 'TABLE_PRIVILEGE_DIFFERS:ingestion_worker_login:application_lifecycle_events']


def test_missing_catalogue_and_session_visibility_is_reported_as_unknown_not_guessed(world,tmp_path):
    install_v3(world)
    result,*_=run(world,tmp_path);i=result['inspection']
    assert i['sessions']['visibility']=='UNKNOWN' and i['identity']['pg_read_all_stats'] is False and i['identity']['pg_authid_password_presence_visible'] is False
    assert {l['password_present'] for l in i['logins'] if l['exists']}=={'UNKNOWN'}


def test_with_visibility_granted_by_the_owner_the_same_facts_are_observed(world,tmp_path):
    install_v3(world);visibility(world)
    with world['connect']('ingestion_worker_login') as idle:      # one visible idle runtime session
        idle.execute('SELECT 1')
        result,*_=run(world,tmp_path);i=result['inspection']
    assert i['sessions']['visibility']=='PROVEN_BY_PG_READ_ALL_STATS' and ['ingestion_worker_login','idle',1] in i['sessions']['by_login_and_state']
    by={l['login']:l for l in i['logins']};assert by['ingestion_worker_login']['password_present'] is True and by['ingestion_storage_login']['can_login'] is False


def test_the_control_function_is_reported_with_its_limits(world,tmp_path):
    install_v3(world)
    result,*_=run(world,tmp_path);c=result['inspection']['control']
    assert c['status']=='OBSERVED' and c['exposed_fields']==list(oi.CONTROL_FIELDS) and c['absence_of_uncertainty_barriers']=='NOT_ESTABLISHED_BY_THIS_INSPECTION'
    world['boot'].execute('REVOKE EXECUTE ON FUNCTION public.ingestion_acceptance_control() FROM provisioning_migrator')
    result,log,*_=run(world,tmp_path);c=result['inspection']['control']
    assert c['status']=='UNKNOWN' and c['reason']=='CONTROL_FUNCTION_NOT_EXECUTABLE_BY_THIS_IDENTITY' and oi.CONTROL not in log


def test_read_only_the_exact_statements_in_order_with_begin_and_rollback_and_no_mutation(world,tmp_path):
    install_oldham(world);visibility(world);before=fingerprint(world)
    result,log,j,holder=run(world,tmp_path)
    names=[n for n,_,_ in oi.planned()]
    assert log==[s for _,s,_ in oi.planned()] and result['accounting']['administration']['driver_statements']['names']==names
    assert log[0]=='BEGIN READ ONLY' and log[-1]=='ROLLBACK' and set(log)<=oi.allowed() and len(log)==11<=oi.BOUND['driver_statements']
    assert not [s for s in log if re.match(r'\s*(GRANT|REVOKE|SET|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|COMMIT)\b',s,re.I)]
    a=result['accounting']['administration'];assert (a['rollbacks']['value'],a['commits']['value'],a['connection_attempts']['value'],a['connections_opened']['value'],a['connections_closed']['value'])==(1,0,1,1,1)
    assert holder['raw'].closed and fingerprint(world)==before
    assert world['boot'].execute("SELECT count(*) FROM pg_stat_activity WHERE usename='provisioning_migrator'").fetchone()[0]==0      # positively gone at the server


def test_the_read_only_transaction_really_refuses_writes_on_this_server(world):
    with world['connect'](MIGRATOR) as c:
        c.execute('BEGIN READ ONLY')
        for write in ('CREATE TABLE public.inspection_must_not_exist(x int)','GRANT SELECT ON public.applications TO ingestion_worker_login','CREATE TEMP TABLE t(x int)'):
            with pytest.raises(Exception,match='read-only transaction'):c.execute(write)
            c.execute('ROLLBACK');c.execute('BEGIN READ ONLY')
        c.execute('ROLLBACK')


def test_statement_and_output_and_time_bounds_are_enforced_before_the_overrun(world,tmp_path,monkeypatch):
    install_v3(world)
    result,log,*_=run(world,tmp_path,bound=dict(driver_statements=4),monkeypatch=monkeypatch)
    assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['failure']['reason_code']=='STATEMENT_BOUND' and len(log)<=4
    monkeypatch.undo()
    result,*_=run(world,tmp_path,bound=dict(returned_data_value_bytes=200),monkeypatch=monkeypatch)
    assert result['failure']['reason_code']=='RESPONSE_BOUND'
    monkeypatch.undo()
    result,*_=run(world,tmp_path,bound=dict(database_seconds=0),monkeypatch=monkeypatch)
    assert result['failure']['reason_code']=='ACTIVE_WINDOW_EXHAUSTED'
    monkeypatch.undo()
    result,log,*_=run(world,tmp_path,bound=dict(database_seconds=0.5),monkeypatch=monkeypatch,slow=0.3)      # a real overrun: each statement takes 0.3 s, the bound trips partway through
    assert result['failure']['reason_code']=='ACTIVE_WINDOW_EXHAUSTED' and 2<=len([x for x in log if x!='ROLLBACK'])<=6
    monkeypatch.undo()
    assert oi.BOUND['driver_statements']==12 and oi.BOUND['planned_statements']==11


def test_a_failure_mid_inspection_rolls_back_counts_it_and_closes_the_connection(world,tmp_path):
    install_v3(world);before=fingerprint(world)
    result,log,j,holder=run(world,tmp_path,fail_on=oi.FUNCTIONS)
    assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['cleanup']=='CLOSED' and log[-1]=='ROLLBACK' and log.count('ROLLBACK')==1
    a=result['accounting']['administration'];assert a['driver_statements']['names'][-1]=='rollback_after_failure' and a['rollbacks']['value']==1 and a['driver_statements']['value']==len(log)<=12
    assert holder['raw'].closed and fingerprint(world)==before
    blob=j.file.read_text()+(j.root/'final-result.json').read_text() if (j.root/'final-result.json').exists() else j.file.read_text()
    assert 'SECRETVALUE' not in blob and 'postgresql://' not in blob


def test_a_broken_connection_is_not_asked_to_roll_back_and_is_still_disposed(world,tmp_path):
    install_v3(world)
    result,log,j,holder=run(world,tmp_path,fail_on=oi.FUNCTIONS,close_first=True)
    assert result['status']=='STOP_RECONCILE_NO_RETRY' and 'ROLLBACK' not in log[-1:] and holder['raw'].closed
    assert world['boot'].execute("SELECT count(*) FROM pg_stat_activity WHERE usename='provisioning_migrator'").fetchone()[0]==0


def test_no_secret_value_verifier_or_query_text_appears_in_any_output(world,tmp_path):
    install_oldham(world);visibility(world);boot=world['boot']
    boot.execute("ALTER ROLE ingestion_worker_login PASSWORD 'canary-password-4f9a'")
    result,log,j,_=run(world,tmp_path)
    blob=json.dumps(result,default=str)+j.file.read_text()
    verifier=boot.execute("SELECT rolpassword FROM pg_authid WHERE rolname='ingestion_worker_login'").fetchone()[0]
    for forbidden in ('canary-password-4f9a',verifier,'SCRAM-SHA-256','postgresql://','prosrc','CREATE FUNCTION','SELECT p.proname'):assert forbidden not in blob,forbidden
    assert next(l for l in result['inspection']['logins'] if l['login']=='ingestion_worker_login')['password_present'] is True      # a boolean only


def test_the_result_has_only_the_fixed_fields(world,tmp_path):
    install_v3(world)
    result,*_=run(world,tmp_path);i=result['inspection']
    assert set(i)=={'identity','control','logins','sessions','functions','privileges'}
    assert set(i['identity'])=={'current_user','session_user','is_the_expected_administrative_migration_account','superuser','createrole','createdb','bypassrls','holds_ingestion_storage_owner','holds_ingestion_barrier_releaser',
                                'pg_read_all_stats','pg_signal_backend','pg_authid_password_presence_visible','character'}
    assert i['identity']['is_the_expected_administrative_migration_account'] is False and i['identity']['current_user']=='OTHER_ACCOUNT'      # the disposable account is not 'postgres'; the report says so and does not echo the name
    assert 'READ_ONLY_IS_A_PER_TRANSACTION_GUARD' in i['identity']['character'] and 'NOT_A_RESTRICTED_ACCOUNT' in i['identity']['character']


def test_the_fingerprint_is_able_to_see_a_change_so_the_unchanged_assertions_are_not_vacuous(world):
    install_v3(world);before=fingerprint(world)
    world['boot'].execute('ALTER ROLE ingestion_worker_login CONNECTION LIMIT 2')
    assert fingerprint(world)!=before
    world['boot'].execute('ALTER ROLE ingestion_worker_login CONNECTION LIMIT 1');before=fingerprint(world)
    world['boot'].execute('GRANT SELECT ON public.applications TO ingestion_worker_login');assert fingerprint(world)!=before


def test_the_whole_session_path_hidden_input_to_final_result_uses_the_disposable_connection_and_leaks_nothing(world,tmp_path):
    from tests.test_ingestion_admin_connection_probe import url,SECRET,OK_DNS,FAST
    from tests.test_oldham_inspection_units import registration
    from verification.ingestion_storage.operational_outcome import session
    install_oldham(world)
    j=Journal(tmp_path/'session');progress=Progress();memory=Memory();lines=[];reg=registration();baseline=owned_resources();log=[]
    def factory():
        raw=world['connect'](MIGRATOR);return Recording(raw,log)
    prepare=lambda value,started:oi.prepare_inspection(reg,value,started,journal=j,memory=memory,progress=progress,baseline=baseline,connect_factory=factory,**OK_DNS)
    result=session(j,reg['expires_at'],lambda:url(),prepare,memory=memory,output=lambda line,**kw:lines.append(line),timing=FAST,progress=progress,baseline=baseline)
    assert result['status']=='OLDHAM_READONLY_INSPECTION_COMPLETE' and result['cleanup']=='CLOSED' and result['mode']==oi.MODE and result['application_writes']==0
    assert result['inspection']['functions']['state']=='OLDHAM_EXACT_INSTALLATION' and log[0]=='BEGIN READ ONLY' and log[-1]=='ROLLBACK'
    assert result['outcome']['tls_verification'].startswith('PERFORMED_BY_THE_EXISTING_ROUTE_MECHANISM') and result['outcome']['worker_authentication_qualified'] is False
    blob=j.file.read_text()+(j.root/'final-result.json').read_text()+''.join(lines)
    for forbidden in (SECRET,'postgresql://','Traceback','192.0.2.','aws-0-eu-west-2.pooler.supabase.com:5432'):assert forbidden not in blob,forbidden


def test_the_twelve_statement_ceiling_holds_when_the_last_select_fails(world,tmp_path):
    install_v3(world);visibility(world)      # the full 11-statement variant: 10 sent before the last SELECT fails, plus the one counted rollback
    result,log,*_=run(world,tmp_path,fail_on=oi.TABLE_PRIVILEGES)
    assert result['status']=='STOP_RECONCILE_NO_RETRY' and len(log)==11 and log[-1]=='ROLLBACK' and result['accounting']['administration']['driver_statements']['value']==11<=oi.BOUND['driver_statements']


def test_an_absent_control_sentinel_is_a_report_not_a_lost_inspection(world,tmp_path):
    install_v3(world);world['boot'].execute("DELETE FROM public.ingestion_work_items WHERE key=repeat('0',64)")
    result,*_=run(world,tmp_path)
    assert result['status']=='OLDHAM_READONLY_INSPECTION_COMPLETE' and result['inspection']['control']['status']=='SENTINEL_ABSENT' and result['inspection']['control']['absence_of_uncertainty_barriers']=='NOT_ESTABLISHED_BY_THIS_INSPECTION'


def test_partial_pg_authid_visibility_falls_back_instead_of_losing_the_run(world,tmp_path):
    install_v3(world);world['boot'].execute('GRANT SELECT (rolpassword) ON pg_authid TO provisioning_migrator')
    result,*_=run(world,tmp_path)
    assert result['status']=='OLDHAM_READONLY_INSPECTION_COMPLETE' and result['inspection']['identity']['pg_authid_password_presence_visible'] is False
    assert {l['password_present'] for l in result['inspection']['logins'] if l['exists']}=={'UNKNOWN'}


def test_database_free_text_never_reaches_the_report_or_the_journal(world,tmp_path):
    install_v3(world);boot=world['boot']
    boot.execute("ALTER ROLE ingestion_worker_login SET application_name='canary-setting-77'")
    boot.execute('CREATE ROLE "canary-role-88" NOLOGIN');boot.execute('GRANT "canary-role-88" TO ingestion_worker_login')
    try:
        result,log,j,_=run(world,tmp_path)
        blob=json.dumps(result,default=str)+j.file.read_text()
        assert 'canary' not in blob
    finally:
        boot.execute('REVOKE "canary-role-88" FROM ingestion_worker_login');boot.execute('DROP ROLE "canary-role-88"')


@pytest.mark.parametrize('timeout',[False,True])
def test_fixed_provider_profile_real_readonly_connection(world,tmp_path,timeout):
    """Real PG + fixed SQL; absent provider extension yields INCOMPLETE, not MATCH.

    The local-only role matches the production identity check. No fixture result
    claims to identify the production mismatch. Driver failure is a real server
    statement timeout injected before the selected fixed query completes.
    """
    import psycopg
    from psycopg import sql
    from tests.e2e_pg_world import settings
    raw,info,_,_=settings();boot=world['boot'];password='provider_fixture_only'
    assert not boot.execute("SELECT 1 FROM pg_roles WHERE rolname='postgres'").fetchall()
    boot.execute(sql.SQL('CREATE ROLE postgres SUPERUSER LOGIN PASSWORD {}').format(sql.Literal(password)))
    log=[];holder={}
    try:
        def connect():
            c=psycopg.connect(**dict(info,user='postgres',password=password,connect_timeout=3),autocommit=True,prepare_threshold=None,
                options='-c search_path=pg_catalog -c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000 -c idle_in_transaction_session_timeout=5000')
            holder['raw']=c
            rec=Recording(c,log)
            if timeout:
                execute=rec.execute
                def timed(statement,params=None):
                    if statement==dict((n,q) for n,q,_ in oi.provider_plan())['views']:
                        # Test-only timeout acceleration; production remains5s.
                        c.execute("SET LOCAL statement_timeout='10ms'")
                        c.execute('SELECT pg_sleep(1)')
                    return execute(statement,params)
                rec.execute=timed
            return rec
        runner=oi.ProviderInspection(oi.ProviderJournal(tmp_path/'provider-pg'),connect,Progress(),Memory(),baseline=owned_resources(),started=time.monotonic())
        result=runner.execute()
        assert holder['raw'].closed and runner.attempts==1 and runner.statements<=16
        assert log[-1]=='ROLLBACK'
        assert result['status']=='PROVIDER_COMPARISON_INCOMPLETE'
        if timeout:assert result['failure']['sqlstate']=='57014'
        else:assert result['inspection']['status']=='INCOMPLETE' and any('MISSING' in x for x in result['inspection']['incomplete'])
    finally:boot.execute('DROP ROLE postgres')
