"""The ACTUAL operational preparation path (verification.ingestion_storage.operational_runner.prepare_runner) behind the REAL session controller.

Synthetic credentials and controlled local fixtures only: no production connection, no credential generation, no GitHub or council call. Local DNS fixtures are real
subprocesses (the real subprocess/timeout/exit-status machinery), the CA/route/import/construction stages are the real production code, and the Runner is the real Runner.
Every failure must (a) name the failing STAGE and a fixed REASON, (b) export complete accounting and a final result, (c) derive closure from positive evidence and
(d) never export the credential, URL, exception text or environment."""
import json,socket,subprocess,sys,time
from datetime import datetime,timezone,timedelta
from urllib.parse import quote
import psycopg,pytest
from verification.ingestion_storage import operational_runner as op
from verification.ingestion_storage import tls_trust
from verification.ingestion_storage.connection_diagnostics import PreparationFailure,safe_failure,STAGES
from verification.ingestion_storage.operational_outcome import session
from verification.ingestion_storage.operational_preparation import Progress,resolve_addresses
from verification.ingestion_storage.operational_runner import Journal,prepare_runner,restricted_url,Runner
from verification.ingestion_storage.tls_trust import owned_resources

SECRET='Syn/thetic@Pass?x:#'
HOST='aws-0-eu-west-2.pooler.supabase.com'
FAST=dict(input_seconds=2,active_seconds=6,work_seconds=5,diagnostic_seconds=1,report_seconds=1,outer_seconds=10)


def url(*,user='postgres.zcikcfgpblzuzpanpdqd',host=HOST,port=5432,db='postgres',query='',scheme='postgresql',password=quote(SECRET,safe='')):
    auth=user+(':'+password if password is not None else '')
    return f'{scheme}://{auth}@{host}:{port}/{db}{query}'


def registration(**changes):
    r=dict(expires_at=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat(),revision='a'*40,controller_sha256='b'*64,manifest_sha256='c'*64,evidence_head='1'*40,
           evidence_directory='docs/design/ingestion-operational-execution-fixture',mode='CONNECTION_DIAGNOSTIC_ONLY',reuse_accepted_operational_installation=True)
    r.update(changes);return {k:v for k,v in r.items() if v is not None}


class Memory:
    def __init__(self,fail_close=False):self.source=object();self.fail_close=fail_close;self.closed=0
    def snapshot(self):return {}
    def close(self):
        self.closed+=1
        if self.fail_close:raise RuntimeError('private close failure text')
        return dict(memory={},owned_groups_removed=True,owned_survivors=0)


def python_dns(code,**kw):return dict(dns_command=[sys.executable,'-c',code],**kw)
OK_DNS=python_dns('print("[\\"192.0.2.9\\",\\"192.0.2.7\\"]")')
FAKE_DNS_RUN=lambda timeout:(lambda cmd,**kw:subprocess.run(cmd,**{**kw,'timeout':timeout}))


def prepared(tmp_path,raw=None,reg=None,memory=None,progress=None,**seams):
    j=Journal(tmp_path/('j%d'%time.monotonic_ns()));progress=progress or Progress()
    return prepare_runner(reg or registration(),url() if raw is None else raw,time.monotonic(),journal=j,memory=memory or Memory(),progress=progress,**{**OK_DNS,**seams}),j,progress


def run_session(tmp_path,raw,*,reg=None,memory=None,**seams):
    """The REAL controller around the REAL preparation; only hidden input is replaced by the synthetic value."""
    j=Journal(tmp_path/('s%d'%time.monotonic_ns()));progress=Progress();memory=memory if memory is not None else Memory();lines=[]
    baseline=owned_resources();reg=reg or registration()
    result=session(j,reg['expires_at'],lambda:raw,lambda value,started:prepare_runner(reg,value,started,journal=j,memory=memory,progress=progress,**{**OK_DNS,**seams}),
                   memory=memory,output=lambda line,**kw:lines.append(line),timing=FAST,progress=progress,baseline=baseline)
    return result,j,lines,progress,memory


def assert_secret_safe(j,lines,result):
    blob=j.file.read_text()+(j.root/'final-result.json').read_text()+''.join(lines)
    for forbidden in (SECRET,quote(SECRET,safe=''),'Syn%2F','postgresql://','Traceback','private close failure text',HOST+':5432','192.0.2.'):
        assert forbidden not in blob,forbidden
    assert json.loads((j.root/'final-result.json').read_bytes())==result


# --- successful preparation ------------------------------------------------------------------------------------------------------------------

def test_successful_preparation_builds_the_real_runner_without_any_connection(tmp_path,monkeypatch):
    before=owned_resources();calls=[]
    real=psycopg.connect
    monkeypatch.setattr(psycopg,'connect',lambda *a,**k:calls.append(k) or real(*a,**k))
    runner,j,progress=prepared(tmp_path)
    assert isinstance(runner,Runner) and runner.hostaddr=='192.0.2.7' and runner.ssl['sslmode']=='verify-full' and runner.r['mode']=='CONNECTION_DIAGNOSTIC_ONLY'
    assert progress.completed==['REGISTRATION_EXPIRY','ROUTE_VALIDATION','PASSWORD_PRESENCE','CA_TRUST','DNS_RESOLUTION','DRIVER_IMPORT','RUNNER_COMPONENTS','RUNNER_CONSTRUCTION']
    assert progress.dns['subprocess_started'] and progress.dns['subprocess_completed'] and progress.dns['exit_code']==0 and progress.dns['address_count']==2
    assert progress.database_connection_calls==0 and not calls                                          # preparation never connects; `connect` is only a closure
    after=owned_resources();assert not after['socket_fds']-before['socket_fds'] and not after['children']     # the DNS child was reaped, no socket survives
    # the admin connector carries the exact decoded password and routing, but is NOT invoked here
    seen=[]
    monkeypatch.setattr(psycopg,'connect',lambda *a,**k:seen.append(k) or (_ for _ in ()).throw(psycopg.OperationalError('synthetic stop')))
    with pytest.raises(psycopg.OperationalError):runner.owner.connector()
    k=seen[0];assert k['password']==SECRET and k['user']=='postgres.zcikcfgpblzuzpanpdqd' and k['hostaddr']=='192.0.2.7' and k['host']==HOST and k['sslmode']=='verify-full'
    assert progress.database_connection_calls==1


# --- route, password, CA -------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('raw,reason',[
    (url(host='db.example.invalid'),'ROUTE_HOST_MISMATCH'),(url(port=6543),'ROUTE_PORT_MISMATCH'),(url(user='postgres'),'ROUTE_USERNAME_MISMATCH'),
    (url(db='other'),'ROUTE_DATABASE_MISMATCH'),(url(query='?sslmode=require'),'ROUTE_QUERY_FORBIDDEN'),(url(scheme='mysql'),'ROUTE_DRIVER_MISMATCH'),
    ('','ROUTE_MALFORMED_INPUT'),('not a url','ROUTE_MALFORMED_INPUT'),('x'*9000,'ROUTE_MALFORMED_INPUT'),(None,'ROUTE_MALFORMED_INPUT'),
])
def test_unsupported_or_malformed_route_reports_its_fixed_reason_not_a_generic_unknown(tmp_path,raw,reason):
    with pytest.raises(PreparationFailure) as caught:prepared(tmp_path,raw=raw if raw is not None else None) if raw is not None else prepare_runner(registration(),None,0,journal=Journal(tmp_path/'n'),memory=Memory(),progress=Progress(),**OK_DNS)
    assert (caught.value.stage,caught.value.reason)==('ROUTE_VALIDATION',reason)
    result,j,lines,progress,_=run_session(tmp_path,raw if raw is not None else '')
    f=result['failure'];assert (f['phase'],f['stage'],f['reason_code'],f['classification_source'])==('PREPARATION','ROUTE_VALIDATION',reason if raw is not None else 'ROUTE_MALFORMED_INPUT','FIXED_PREPARATION_CODE')
    assert not progress.dns['subprocess_started']                                                       # fails BEFORE the DNS subprocess
    assert_secret_safe(j,lines,result)


def test_the_previously_lost_route_code_is_the_defect_the_old_export_could_not_show():
    from verification.discovery.route_validation import RouteRejection
    old=safe_failure(RouteRejection('USERNAME_MISMATCH'),'ROUTE_VALIDATION')
    assert old['exception_kind']=='RouteRejection' and old['reason_code']=='UNKNOWN'                    # class now named; reason stays UNKNOWN for a bare exception (never guessed)


def test_missing_password_is_reported_without_touching_dns(tmp_path):
    result,j,lines,progress,_=run_session(tmp_path,url(password=None))
    assert (result['failure']['stage'],result['failure']['reason_code'])==('PASSWORD_PRESENCE','PASSWORD_ABSENT') and not progress.dns['subprocess_started']
    assert_secret_safe(j,lines,result)


@pytest.mark.parametrize('arrange,reason',[('missing','REVIEWED_CA_MISSING'),('hash','REVIEWED_CA_HASH_MISMATCH'),('der','REVIEWED_CA_DER_MISMATCH'),('validity','REVIEWED_CA_VALIDITY_REVIEW_REQUIRED')])
def test_ca_failures(tmp_path,monkeypatch,arrange,reason):
    if arrange=='missing':monkeypatch.setattr(tls_trust,'ROOT',tmp_path/'absent.crt')
    elif arrange=='hash':
        junk=tmp_path/'junk.crt';junk.write_bytes(b'not a certificate');monkeypatch.setattr(tls_trust,'ROOT',junk)
    elif arrange=='der':monkeypatch.setattr(tls_trust,'DER_SHA256','0'*64)
    else:
        real=tls_trust.timedelta;monkeypatch.setattr(tls_trust,'timedelta',lambda **k:real(days=100000))
    result,j,lines,progress,_=run_session(tmp_path,url())
    assert (result['failure']['stage'],result['failure']['reason_code'])==('CA_TRUST',reason) and not progress.dns['subprocess_started']
    assert_secret_safe(j,lines,result)


def test_unclassified_exception_keeps_its_stage_and_stays_unknown(tmp_path,monkeypatch):
    monkeypatch.setattr(op,'verified_trust',lambda:(_ for _ in ()).throw(RuntimeError('private text '+SECRET)))
    result,j,lines,_,_=run_session(tmp_path,url())
    f=result['failure'];assert (f['stage'],f['reason_code'],f['flags'])==('CA_TRUST','UNEXPECTED_EXCEPTION',{'exception_kind':'OTHER'})
    assert_secret_safe(j,lines,result)


# --- DNS subprocess: exit status is checked BEFORE output is parsed -----------------------------------------------------------------------------------------

@pytest.mark.parametrize('seams,reason,flags',[
    (python_dns('import sys;sys.exit(3)'),'DNS_NONZERO_EXIT',{'exit_code':3}),                              # the old code parsed empty stdout as JSON first (JSONDecodeError -> OTHER/UNKNOWN)
    (python_dns('import sys;print("[\\"192.0.2.7\\"]");sys.exit(2)'),'DNS_NONZERO_EXIT',{'exit_code':2}),
    (python_dns('pass'),'DNS_EMPTY_OUTPUT',{}),(python_dns('print("not json")'),'DNS_MALFORMED_OUTPUT',{}),(python_dns('print("{}")'),'DNS_MALFORMED_OUTPUT',{}),
    (python_dns('print("[1]")'),'DNS_MALFORMED_OUTPUT',{}),(python_dns('print("[]")'),'DNS_NO_ADDRESS',{}),
    (python_dns('print("[\\"192.0.2.%d\\"]"%1)'.replace('"[\\"192.0.2.%d\\"]"%1','"[%s]"%",".join(\'\\"192.0.2.%d\\"\'%i for i in range(33))')),'DNS_TOO_MANY_ADDRESSES',{}),
    (python_dns('print("[\\"999.1.1.1\\"]")'),'DNS_INVALID_ADDRESS',{}),(python_dns('print("[\\"2001:db8::1\\"]")'),'REVIEWED_IPV4_ONLY',{}),
    (python_dns('print("[\\""+"1"*5000+"\\"]")'),'DNS_OUTPUT_BOUND',{}),
    (dict(dns_command=['/nonexistent/dns-helper']),'DNS_SUBPROCESS_SPAWN_FAILED',{}),
    (python_dns('import time;time.sleep(10)',dns_run=FAKE_DNS_RUN(.3)),'DNS_TIMEOUT',{}),
])
def test_dns_subprocess_failures_have_exact_reasons(tmp_path,seams,reason,flags):
    result,j,lines,progress,_=run_session(tmp_path,url(),**seams)
    f=result['failure'];assert f['reason_code']==reason and f['flags']==flags and f['phase']=='PREPARATION'
    assert f['stage']=='DNS_RESOLUTION' and progress.dns['subprocess_started']
    assert result['accounting']['preparation']['dns_subprocesses_spawned']==dict(value=int(reason!='DNS_SUBPROCESS_SPAWN_FAILED'),basis='MEASURED',scope='PREPARATION_DNS_CHILD_ONLY')                                 # preparation DID work even though no runtime slot exists
    assert result['closure_components']['process']['status']=='CLOSED' and result['closure_components']['process']['live_child_count']==0   # the timed-out child was killed and reaped
    assert_secret_safe(j,lines,result)


# --- imports, construction ----------------------------------------------------------------------------------------------------------------------------

def test_import_and_construction_failures(tmp_path,monkeypatch):
    with monkeypatch.context() as m:
        m.setitem(sys.modules,'psycopg',None)
        r,j,lines,_,_=run_session(tmp_path,url());assert (r['failure']['stage'],r['failure']['reason_code'])==('DRIVER_IMPORT','DRIVER_IMPORT_FAILED');assert_secret_safe(j,lines,r)
    with monkeypatch.context() as m:
        m.setitem(sys.modules,'verification.ingestion_storage.operational_source',None)
        r,j,lines,_,_=run_session(tmp_path,url());assert (r['failure']['stage'],r['failure']['reason_code'])==('RUNNER_COMPONENTS','COMPONENT_IMPORT_FAILED');assert_secret_safe(j,lines,r)
    r,j,lines,progress,_=run_session(tmp_path,url(),reg=registration(revision=None))
    assert (r['failure']['stage'],r['failure']['reason_code'])==('RUNNER_CONSTRUCTION','RUNNER_CONSTRUCTION_FAILED') and progress.database_connection_calls==0;assert_secret_safe(j,lines,r)


def test_expired_registration_in_preparation_stage(tmp_path):
    reg=registration();past=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    with pytest.raises(PreparationFailure) as caught:prepared(tmp_path,reg=dict(reg,expires_at=past))
    assert (caught.value.stage,caught.value.reason)==('REGISTRATION_EXPIRY','REGISTRATION_EXPIRED')


# --- accounting and closure on every exit ---------------------------------------------------------------------------------------------------------------

def test_every_early_exit_exports_complete_accounting_and_separate_positive_closure(tmp_path):
    result,j,lines,progress,memory=run_session(tmp_path,url(user='postgres'))
    a=result['accounting'];adm=a['administration']
    assert adm['connections']==dict(value=0,basis='MEASURED')                                               # a measured zero: the connect closure was never called
    for k in ('commands','returned_data_value_bytes','failed_native_connections','failed_native_finished','credential_generations','secret_mappings','role_changes'):
        assert adm[k]==dict(value=0,basis='NOT_STARTED'),k                                                   # provably never reached, not "measured"
    assert a['runtime']['slot_receipts']=={} and a['runtime']['slot_state']=='NO_RUNTIME_SLOT_CREATED' and a['runtime']['supervised_seconds']==dict(value=0,basis='NOT_STARTED')
    pw=a['preparation'];assert pw['state']=='PREPARATION_ONLY_NO_DATABASE_GITHUB_OR_SOURCE_WORK' and pw['dns_subprocesses_spawned']==dict(value=0,basis='MEASURED',scope='PREPARATION_DNS_CHILD_ONLY') and a['historical_accounting_gaps']=='PRESERVED_NOT_RECONSTRUCTED'
    c=result['closure_components']
    assert c['access']['status']=='NOT_REQUIRED_NO_ACCESS_CREATED' and c['connections']['status']=='NO_CONNECTION_ATTEMPTED'
    assert c['process']['status']=='CLOSED' and c['process']['new_socket_count']==0 and c['outer_scope_removal']=='NOT_VERIFIABLE_BEFORE_CONTROLLER_EXIT'
    assert result['cleanup']=='CLOSED' and result['status']=='STOP_RECONCILE_NO_RETRY' and result['authority_invalidation']=='NOT_REQUIRED_NO_AUTHORITY' and result['access']=='NO_ACCESS_CREATED'
    assert result['application_writes']==0 and result['pipeline_retry']=='HELD' and result['stage4']=='OPEN' and memory.closed==1
    assert result['preparation']['current_stage']=='ROUTE_VALIDATION' and result['preparation']['completed_stages']==['REGISTRATION_EXPIRY']
    assert_secret_safe(j,lines,result)


def test_closure_is_uncertain_without_positive_evidence(tmp_path):
    # native memory proof unavailable
    result,j,lines,_,_=run_session(tmp_path,url(user='postgres'),memory=Memory(fail_close=True))
    assert result['cleanup']=='UNCERTAIN' and result['closure_components']['process']['status']=='UNCERTAIN';assert_secret_safe(j,lines,result)
    # a socket that survives preparation
    leaked=[]
    def leaking_run(cmd,**kw):leaked.append(socket.socket());raise subprocess.TimeoutExpired(cmd,1)
    result,j,lines,_,_=run_session(tmp_path,url(),dns_run=leaking_run)
    p=result['closure_components']['process']
    assert result['failure']['reason_code']=='DNS_TIMEOUT' and p['new_socket_count']==1 and p['status']=='UNCERTAIN' and result['cleanup']=='UNCERTAIN'
    [s.close() for s in leaked];assert_secret_safe(j,lines,result)
    # without a baseline nothing can be proven
    j2=Journal(tmp_path/'nobase');r=session(j2,registration()['expires_at'],lambda:'x',lambda raw,started:(_ for _ in ()).throw(RuntimeError('private')),memory=Memory(),output=lambda *a,**k:None,timing=FAST)
    assert r['cleanup']=='UNCERTAIN' and r['closure_components']['process']['status']=='UNCERTAIN'


def test_deadlines_keep_their_stage_and_session_input_failures_are_attributed(tmp_path):
    j=Journal(tmp_path/'input');r=session(j,registration()['expires_at'],lambda:(_ for _ in ()).throw(EOFError()),lambda *a:None,memory=Memory(),output=lambda *a,**k:None,timing=FAST,
                                          progress=Progress(),baseline=owned_resources())
    assert r['failure']['stage']=='SESSION_INPUT' and r['accounting']['runtime']['slot_state']=='NO_RUNTIME_SLOT_CREATED'
    past=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    j=Journal(tmp_path/'expired');r=session(j,past,lambda:'x',lambda *a:None,memory=Memory(),output=lambda *a,**k:None,timing=FAST,progress=Progress(),baseline=owned_resources())
    assert (r['failure']['stage'],r['failure']['reason_code'])==('REGISTRATION_EXPIRY','REGISTRATION_EXPIRED')


# --- the prepared Runner reaching its first administrative connection (real session, real Runner, real gh is covered by the PG/gh wrapper tests) --------------------------

class FakeGitHub:
    def __init__(self,emit,check):self.requests=0;self.mutation_uncertain=False
    def call(self,method,path,body=None):self.requests+=1;return {'login':'maxrose26'}
    def names(self):return ['DATABASE_URL']


@pytest.mark.parametrize('error,reason,sqlstate',[
    (psycopg.errors.InvalidPassword('password authentication failed for user "x"'),'AUTHENTICATION_REJECTED','28P01'),
    (psycopg.OperationalError('FATAL:  Tenant or user not found'),'ROUTING_IDENTITY_REJECTED',None),
    (psycopg.OperationalError('server certificate for "other" does not match host name "h"'),'TLS_HOSTNAME_MISMATCH',None),
    (psycopg.OperationalError('SSL error: certificate verify failed'),'TLS_CHAIN_REJECTED',None),
    (psycopg.OperationalError('connection timeout expired'),'CONNECTION_TIMEOUT',None),
    (psycopg.errors.InsufficientPrivilege('permission denied for database "postgres"'),'PERMISSION_DENIED','42501'),
    (psycopg.OperationalError('private arbitrary text '+SECRET),'UNKNOWN',None),
])
def test_prepared_runner_connection_failures_after_complete_preparation(tmp_path,monkeypatch,error,reason,sqlstate):
    monkeypatch.setattr(op,'GitHub',FakeGitHub)
    monkeypatch.setattr(psycopg,'connect',lambda *a,**k:(_ for _ in ()).throw(error))
    j=Journal(tmp_path/'e2e');progress=Progress();memory=Memory();lines=[];reg=registration();baseline=owned_resources()
    holder={}
    def prepare(raw,started):
        holder['runner']=prepare_runner(reg,raw,started,journal=j,memory=memory,progress=progress,**OK_DNS);return holder['runner']
    result=session(j,reg['expires_at'],lambda:url(),prepare,memory=memory,output=lambda line,**kw:lines.append(line),timing=FAST,progress=progress,baseline=baseline)
    assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['operation_phase']=='ADMIN_PREFLIGHT'
    f=result['failure'];assert (f['reason_code'],f['sqlstate'],f['phase'])==(reason,sqlstate,'EXECUTION')
    assert result["accounting"]["administration"]["connections"]==progress.database_connection_calls>=1 and result['accounting']['runtime']['slot_receipts']=={}
    assert not holder['runner'].owner.authorities                                                         # no executable authority exists after the early failure
    assert_secret_safe(j,lines,result)


# --- connection-path comparison: operational vs the previously successful storage path ----------------------------------------------------------------------

def test_operational_and_storage_connection_paths_differ_only_in_documented_options(tmp_path,monkeypatch):
    from verification.ingestion_storage.storage_controller import production_transport
    from verification.ingestion_storage.operational_controller import DatabaseBudget
    seen=[]
    def intercept(*a,**k):seen.append(k);raise psycopg.OperationalError('synthetic interception')
    monkeypatch.setattr(psycopg,'connect',intercept);monkeypatch.setattr(psycopg.Connection,'connect',classmethod(lambda cls,*a,**k:intercept(*a,**k)))
    ca,_=tls_trust.verified_trust();trust={'sslmode':'verify-full','sslrootcert':str(ca)}
    raw=url()
    with pytest.raises(psycopg.Error):production_transport(raw,'192.0.2.1',ca)('ingestion_worker_login','generated')                 # storage (previously accepted) path, restricted-login branch
    runner,_,_=prepared(tmp_path,raw=raw)
    with pytest.raises(psycopg.Error):runner.owner.connector()                                             # operational ADMIN path (migration identity)
    budget=DatabaseBudget();engine=budget.engine(restricted_url('ingestion_worker_login','generated'),ssl=trust,hostaddr='192.0.2.1')
    with pytest.raises(Exception):engine.connect()
    budget.close([])
    storage,admin,runtime=seen
    common={'host','hostaddr','port','dbname','user','password','sslmode','sslrootcert','connect_timeout','prepare_threshold','autocommit'}
    assert set(storage)==common and set(admin)==common|{'options'} and set(runtime)==common|{'options','cursor_factory'}
    for key in ('host','port','dbname','sslmode','sslrootcert','connect_timeout','prepare_threshold','autocommit'):assert storage[key]==admin[key]==runtime[key]
    assert storage['user']==runtime['user']=='ingestion_worker_login.zcikcfgpblzuzpanpdqd' and admin['user']=='postgres.zcikcfgpblzuzpanpdqd'
    assert admin['options']==runtime['options']=='-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=20000'   # the ONLY startup-parameter difference from the accepted storage path
    assert storage['password']=='generated'==runtime['password'] and admin['password']==SECRET


def test_unknown_basis_without_progress_record_claims_nothing(tmp_path):
    j=Journal(tmp_path/'unk');r=session(j,registration()['expires_at'],lambda:'x',lambda raw,started:(_ for _ in ()).throw(RuntimeError('private')),memory=Memory(),output=lambda *a,**k:None,timing=FAST)
    adm=r['accounting']['administration']
    assert adm['connections']=={'value':None,'basis':'UNKNOWN'} and r['accounting']['runtime']['slot_state']=='UNKNOWN' and r['cleanup']=='UNCERTAIN'


# --- the real main() entrypoint: argument/environment gates, registration binding, session wiring, exit status, final-result file ------------------------------------------

def test_real_main_wires_progress_and_exports_a_stage_attributed_final_result(tmp_path,monkeypatch,capsys):
    import hashlib,os
    from verification.ingestion_storage import operational_memory,credential_mapping
    reg=registration();body=json.dumps(reg).encode();digest=hashlib.sha256(body).hexdigest();path=tmp_path/'reg.json';path.write_bytes(body)
    for k in [k for k in os.environ if k.startswith('PG') or k in ('GH_TOKEN','GITHUB_TOKEN','GH_DEBUG','GH_HOST')]:monkeypatch.delenv(k)
    monkeypatch.setenv('HOME',str(tmp_path));monkeypatch.setattr(sys,'platform','linux');monkeypatch.setattr(sys.stdin,'isatty',lambda:True,raising=False);monkeypatch.setattr(sys.stderr,'isatty',lambda:True,raising=False)
    monkeypatch.setattr(op,'validate_registration',lambda b,sha:dict(reg,authority='synthetic-authority'))
    monkeypatch.setattr(operational_memory,'OperationalMemory',Memory)
    monkeypatch.setattr(credential_mapping,'secure_migration_input',lambda:url(host='db.example.invalid'))
    monkeypatch.setattr(sys,'argv',['x','--registration',str(path),'--registration-sha256',digest])
    with pytest.raises(SystemExit) as caught:op.main()
    assert caught.value.code==1                                                                             # a closed failure is still a failed execution
    final=next((tmp_path/'.local/state/propertyaigent').glob('*/final-result.json'))
    result=json.loads(final.read_bytes());f=result['failure']
    assert (f['phase'],f['stage'],f['reason_code']) == ('PREPARATION','ROUTE_VALIDATION','ROUTE_HOST_MISMATCH') and result['cleanup']=='CLOSED'
    assert result['accounting']['administration']['connections']==dict(value=0,basis='MEASURED') and result['preparation']['completed_stages']==['REGISTRATION_EXPIRY']
    blob=final.read_text()+(final.parent/'events.jsonl').read_text()+capsys.readouterr().out+capsys.readouterr().err
    for forbidden in (SECRET,'db.example.invalid','postgresql://','Traceback'):assert forbidden not in blob


# --- hosted-only: REAL native cgroup memory object under the systemd scope (skipped locally; runs in the restricted-provisioning wrapper step) ---------------------------

@pytest.mark.skipif(__import__('os').environ.get('INGESTION_OPERATIONAL_NATIVE')!='1',reason='requires the hosted systemd operational scope')
@pytest.mark.parametrize('fault',['route','dns_timeout','dns_exit'])
def test_native_memory_and_process_closure_on_early_failure(tmp_path,fault):
    from verification.ingestion_storage.operational_memory import OperationalMemory
    native=OperationalMemory()
    raw,seams={'route':(url(user='postgres'),{}),'dns_timeout':(url(),python_dns('import time;time.sleep(30)',dns_run=FAKE_DNS_RUN(.3))),'dns_exit':(url(),python_dns('import sys;sys.exit(4)'))}[fault]
    result,j,lines,progress,_=run_session(tmp_path,raw,memory=native,**seams)
    c=result['closure_components']
    assert result['failure']['phase']=='PREPARATION' and result['accounting']['administration']['connections']==dict(value=0,basis='MEASURED')
    assert c['process']['status']=='CLOSED' and c['process']['live_child_count']==0 and c['process']['new_socket_count']==0 and result['cleanup']=='CLOSED'
    m=c['process']['memory'];assert m['owned_groups_removed'] is True and m['owned_survivors']==0                 # positive kernel evidence, not an absence of errors
    assert_secret_safe(j,lines,result)


# --- review findings: the stage is recorded not inferred; the exporter cannot be the reason nothing is exported ---------------------------------------------------------

def test_interruption_between_stages_is_not_blamed_on_a_completed_stage(tmp_path):
    j=Journal(tmp_path/'between');progress=Progress()
    def prepare(raw,started):
        with progress.stage('ROUTE_VALIDATION'):pass
        raise KeyboardInterrupt()                                                                           # arrives after a stage completed and before the next begins
    r=session(j,registration()['expires_at'],lambda:'x',prepare,memory=Memory(),output=lambda *a,**k:None,timing=FAST,progress=progress,baseline=owned_resources())
    assert r['failure']['stage']=='AFTER_ROUTE_VALIDATION' and progress.current is None


def test_a_failing_exporter_still_yields_a_final_result_and_uncertain_closure(tmp_path,monkeypatch):
    from verification.ingestion_storage import operational_outcome as oo
    monkeypatch.setattr(oo,'safe_failure',lambda *a:(_ for _ in ()).throw(ImportError('driver unavailable '+SECRET)))
    result,j,lines,_,_=run_session(tmp_path,url(user='postgres'))
    assert result['cleanup']=='UNCERTAIN' and result['failure']['reason_code']=='FAILURE_EXPORT_UNAVAILABLE' and result['accounting']['administration']['connections']['basis']=='UNKNOWN'
    assert_secret_safe(j,lines,result)


def test_unclassifiable_early_exit_without_the_driver_still_exports(tmp_path,monkeypatch):
    monkeypatch.setitem(sys.modules,'psycopg',None)
    j=Journal(tmp_path/'nodriver')
    r=session(j,registration()['expires_at'],lambda:(_ for _ in ()).throw(EOFError()),lambda *a:None,memory=Memory(),output=lambda *a,**k:None,timing=FAST,progress=Progress(),baseline=owned_resources())
    assert (j.root/'final-result.json').exists() and r['status']=='STOP_RECONCILE_NO_RETRY'
