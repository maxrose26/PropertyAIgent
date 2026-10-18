"""The administrative connection probe: one connection attempt, one fixed statement, no other capability.

Evidence is server-side where possible: a disposable PostgreSQL cluster logs EVERY statement, connection and disconnection, so "one statement, no rollback, no
startup query" is observed at the server rather than asserted from client counters. Synthetic credentials only; the cluster listens on loopback and is destroyed."""
import ast,glob,hashlib,json,os,re,shutil,socket,subprocess,sys,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.parse import quote
import psycopg,pytest
from verification.ingestion_storage import admin_connection_probe as ap
from verification.ingestion_storage import operational_outcome as oo
from verification.ingestion_storage.admin_connection_probe import ProbeRunner,ProbeDenied,prepare_probe,validate_probe_registration,LIMITS,STATEMENT,MODE,AUTHORITY
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_outcome import session,legacy_counts
from verification.ingestion_storage.operational_preparation import Progress,STARTUP_OPTIONS
from verification.ingestion_storage.tls_trust import owned_resources,PEM_SHA256

SECRET='Syn/thetic@Pass?x:#'
HOST='aws-0-eu-west-2.pooler.supabase.com'
FAST=dict(input_seconds=2,active_seconds=20,work_seconds=15,diagnostic_seconds=1,report_seconds=2,outer_seconds=30)
OK_DNS=dict(dns_command=[sys.executable,'-c','print("[\\"192.0.2.7\\"]")'])


def url(user='postgres.zcikcfgpblzuzpanpdqd'):return f'postgresql://{user}:{quote(SECRET,safe="")}@{HOST}:5432/postgres'


def probe_registration(**changes):
    r=dict(mode=MODE,authority=AUTHORITY,status=ap.STATUS,expires_at=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat(),revision='a'*40,tree='b'*40,hashes={},
           controller_sha256='c'*64,ca_sha256=PEM_SHA256,evidence_directory='docs/design/ingestion-admin-connection-probe-20261018',limits=dict(LIMITS),
           absent_capabilities=list(ap.ABSENT_CAPABILITIES),statement_sha256=hashlib.sha256(STATEMENT.encode()).hexdigest(),
           attempt=1,state_directory=ap.STATE,predecessor=None)
    r.update(changes);return r


class Memory:
    def __init__(self):self.source=object();self.closed=0
    def snapshot(self):return {}
    def close(self):self.closed+=1;return dict(memory={},owned_groups_removed=True,owned_survivors=0)


# --- disposable cluster that logs every statement ---------------------------------------------------------------------------------------------------------

def _bin(name):
    found=sorted(glob.glob(f'/usr/lib/postgresql/*/bin/{name}'))
    return found[-1] if found else None


@pytest.fixture(scope='module')
def cluster(tmp_path_factory):
    initdb=_bin('initdb')
    if initdb is None or os.geteuid()==0:
        if os.environ.get('INGESTION_REQUIRE_LOCAL_PG')=='1':pytest.fail('LOCAL_POSTGRES_REQUIRED_BUT_UNAVAILABLE')
        pytest.skip('no unprivileged local PostgreSQL binaries')
    root=tmp_path_factory.mktemp('probe-pg');data=root/'data';log=root/'server.log'
    subprocess.run([initdb,'-D',str(data),'-U','postgres','-A','trust','--no-sync'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    options=f"-c listen_addresses=127.0.0.1 -c port={port} -c unix_socket_directories={root} -c log_statement=all -c log_connections=on -c log_disconnections=on -c log_min_duration_statement=-1 -c fsync=off"
    subprocess.run([_bin('pg_ctl'),'-D',str(data),'-l',str(log),'-o',options,'-w','start'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        with psycopg.connect(host='127.0.0.1',port=port,dbname='postgres',user='postgres',autocommit=True) as c:c.execute('CREATE ROLE other LOGIN')
        class Cluster:pass
        k=Cluster();k.port=port;k.log=log
        def statements():
            text=log.read_text()
            return [m for m in re.findall(r'(?:statement|execute [^:]*): (.*)',text)]
        k.statements=statements
        k.count=lambda pat:len(re.findall(pat,log.read_text()))
        yield k
    finally:
        subprocess.run([_bin('pg_ctl'),'-D',str(data),'-m','immediate','stop'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def factory(cluster,user='postgres',port=None):
    return lambda:psycopg.connect(host='127.0.0.1',port=port or cluster.port,dbname='postgres',user=user,autocommit=True,prepare_threshold=None,options=STARTUP_OPTIONS,connect_timeout=3)


def run_probe(tmp_path,connect_factory,*,raw=None,memory=None,**seams):
    j=Journal(tmp_path/('p%d'%time.monotonic_ns()));progress=Progress();memory=memory or Memory();lines=[];reg=probe_registration();baseline=owned_resources()
    holder={}
    def prepare(value,started):
        holder['runner']=prepare_probe(reg,value,started,journal=j,memory=memory,progress=progress,baseline=baseline,connect_factory=connect_factory,**{**OK_DNS,**seams});return holder['runner']
    result=session(j,reg['expires_at'],lambda:raw or url(),prepare,memory=memory,output=lambda line,**kw:lines.append(line),timing=FAST,progress=progress,baseline=baseline)
    return result,j,lines,progress,holder.get('runner')


def secret_safe(j,lines,result):
    blob=j.file.read_text()+(j.root/'final-result.json').read_text()+''.join(lines)
    for forbidden in (SECRET,quote(SECRET,safe=''),'postgresql://','Traceback','private text',HOST+':5432','192.0.2.'):
        assert forbidden not in blob,forbidden
    assert json.loads((j.root/'final-result.json').read_bytes())==result


# --- the qualified path, observed at the server ----------------------------------------------------------------------------------------------------------

def test_qualified_probe_is_one_connection_one_statement_observed_by_the_server(tmp_path,cluster):
    before=(cluster.count(r'connection authorized'),cluster.count(r'disconnection:'),len(cluster.statements()))
    result,j,lines,progress,_=run_probe(tmp_path,factory(cluster))
    assert result['status']=='ADMIN_CONNECTION_QUALIFIED' and result['cleanup']=='CLOSED' and result['identity_observation']=='MATCHES_EXPECTED_ADMIN_ROLE'
    assert result['outcome']==dict(preparation='COMPLETED',administrative_connection='QUALIFIED',failure='NONE',closure='VERIFIED',scope='ADMIN_ROLE_CONNECTION_ONLY',
                                   worker_authentication_qualified=False,route_qualified_for_restricted_roles=False)
    after=(cluster.count(r'connection authorized'),cluster.count(r'disconnection:'),len(cluster.statements()))
    assert tuple(a-b for a,b in zip(after,before))==(1,1,1)                                            # ONE connection, ONE disconnection, ONE statement at the server
    assert cluster.statements()[-1].strip()==STATEMENT                                                # the reviewed constant, nothing else, no BEGIN/ROLLBACK/SET/startup query
    log=cluster.log.read_text();assert not re.search(r'statement: (BEGIN|ROLLBACK|COMMIT|SET|GRANT|CREATE|ALTER|INSERT|UPDATE|DELETE|SELECT 1)',log.split('CREATE ROLE other')[-1])
    a=result['accounting']['administration']
    assert (a['connection_attempts']['value'],a['connections_opened']['value'],a['connections_closed']['value'],a['driver_statements']['value'],a['rollbacks']['value'],a['commits']['value'])==(1,1,1,1,0,0)
    assert a['returned_data_value_bytes']=={'value':len('postgres'),'basis':'MEASURED'}
    for k in ('credential_generations','secret_mappings','role_changes','function_installations','grants_or_exceptions','queue_mutations','council_requests'):assert a[k]=={'value':0,'basis':'CAPABILITY_ABSENT'},k
    assert result['closure_components']['connections']['status']=='CLOSED' and result['closure_components']['process']['status']=='CLOSED' and result['application_writes']==0
    secret_safe(j,lines,result)


def test_startup_options_are_unchanged_from_the_reviewed_values():
    assert STARTUP_OPTIONS=='-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=20000'


def test_unexpected_identity_is_a_classified_failure_not_a_qualification(tmp_path,cluster):
    result,j,lines,_,_=run_probe(tmp_path,factory(cluster,user='other'))
    assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['failure']['reason_code']=='ADMIN_IDENTITY_UNEXPECTED' and result['outcome']['administrative_connection']=='FAILED_CLASSIFIED'
    assert result['outcome']['worker_authentication_qualified'] is False and result['identity_observation']=='DIFFERS_FROM_EXPECTED_ADMIN_ROLE'
    secret_safe(j,lines,result)


# --- failures are classified or honestly unclassified; closure stays separate ----------------------------------------------------------------------------

def test_real_refused_connection_is_classified_without_any_statement(tmp_path,cluster):
    with socket.socket() as s:s.bind(('127.0.0.1',0));dead=s.getsockname()[1]
    before=len(cluster.statements())
    result,j,lines,progress,_=run_probe(tmp_path,factory(cluster,port=dead))
    assert result['outcome']['administrative_connection']=='FAILED_CLASSIFIED' and result['failure']['reason_code']=='CONNECTION_REFUSED' and result['failure']['phase']=='DRIVER_CONNECT'
    a=result['accounting']['administration'];assert (a['connection_attempts']['value'],a['connections_opened']['value'],a['driver_statements']['value'])==(1,0,0)
    assert result['closure_components']['process']['new_socket_count']==0 and result['outcome']['closure']=='VERIFIED' and len(cluster.statements())==before
    secret_safe(j,lines,result)


@pytest.mark.parametrize('error,reason,classified',[
    (psycopg.errors.InvalidPassword('password authentication failed for user "x"'),'AUTHENTICATION_REJECTED',True),
    (psycopg.OperationalError('FATAL:  Tenant or user not found'),'ROUTING_IDENTITY_REJECTED',True),
    (psycopg.OperationalError('server certificate for "other" does not match host name "h"'),'TLS_HOSTNAME_MISMATCH',True),
    (psycopg.OperationalError('connection timeout expired'),'CONNECTION_TIMEOUT',True),
    (psycopg.errors.InsufficientPrivilege('permission denied for database "postgres"'),'PERMISSION_DENIED',True),
    (psycopg.OperationalError('private text arbitrary '+SECRET),'UNKNOWN',False),
    (RuntimeError('private text '+SECRET),'UNKNOWN',False),
])
def test_classified_and_unclassified_connection_failures(tmp_path,error,reason,classified):
    def boom():raise error
    result,j,lines,_,_=run_probe(tmp_path,boom)
    assert result['failure']['reason_code']==reason and result['outcome']['administrative_connection']==('FAILED_CLASSIFIED' if classified else 'FAILED_UNCLASSIFIED')
    assert result['outcome']['failure']==('CLASSIFIED' if classified else 'UNCLASSIFIED') and result['outcome']['preparation']=='COMPLETED'
    assert result['outcome']['worker_authentication_qualified'] is False and result['status']=='STOP_RECONCILE_NO_RETRY'
    secret_safe(j,lines,result)


def test_preparation_failure_reports_no_connection_attempted(tmp_path,cluster):
    result,j,lines,progress,_=run_probe(tmp_path,factory(cluster),raw=url(user='postgres'))
    assert result['failure']['stage']=='ROUTE_VALIDATION' and result['outcome']['preparation']=='FAILED' and result['outcome']['administrative_connection']=='NOT_ATTEMPTED'
    assert result['accounting']['administration']['connections']=={'value':0,'basis':'MEASURED'} and progress.database_connection_calls==0
    secret_safe(j,lines,result)


def test_closure_is_uncertain_when_a_socket_survives_or_memory_proof_is_missing(tmp_path,cluster):
    class Bad(Memory):
        def close(self):raise RuntimeError('private text')
    result,j,lines,_,_=run_probe(tmp_path,factory(cluster),memory=Bad())
    assert result['status']=='ADMIN_CONNECTION_QUALIFIED_CLOSURE_UNCERTAIN' and result['outcome']['administrative_connection']=='QUALIFIED' and result['outcome']['closure']=='UNCERTAIN' and result['cleanup']=='UNCERTAIN'
    secret_safe(j,lines,result)
    leaked=[]
    def leaky():
        leaked.append(socket.socket());raise psycopg.OperationalError('connection timeout expired')
    result,j,lines,_,_=run_probe(tmp_path,leaky)
    assert result['closure_components']['process']['new_socket_count']==1 and result['outcome']['closure']=='UNCERTAIN';[s.close() for s in leaked]


# --- budgets enforced in code ------------------------------------------------------------------------------------------------------------------------------

def _runner(tmp_path,connect):
    return ProbeRunner(Journal(tmp_path/('r%d'%time.monotonic_ns())),connect,Progress(),Memory(),baseline=owned_resources(),started=time.monotonic())


def test_second_connection_attempt_is_denied_before_any_connect(tmp_path,cluster):
    calls=[];real=factory(cluster)
    runner=_runner(tmp_path,lambda:calls.append(1) or real())
    first=runner.execute();assert first['status']=='ADMIN_CONNECTION_QUALIFIED' and len(calls)==1
    second=runner.execute()
    assert second['failure']['reason_code']=='CONNECTION_ATTEMPT_BOUND' and len(calls)==1 and second['accounting']['administration']['connection_attempts']['value']==1


def test_only_the_reviewed_statement_can_be_sent_and_only_once(tmp_path,cluster):
    runner=_runner(tmp_path,factory(cluster));connection=factory(cluster)()
    before=len(cluster.statements())
    with pytest.raises(ProbeDenied) as caught:runner.one_statement(connection,'DROP TABLE x')
    assert caught.value.code=='STATEMENT_UNEXPECTED' and len(cluster.statements())==before and runner.statements==0
    assert runner.one_statement(connection,STATEMENT)=='postgres'
    with pytest.raises(ProbeDenied) as caught:runner.one_statement(connection,STATEMENT)
    assert caught.value.code=='STATEMENT_BOUND' and len(cluster.statements())==before+1
    connection.close()


def test_oversized_or_misshapen_responses_are_bounded(tmp_path):
    class Result:
        ntuples=1;nfields=1
        def __init__(self,value):self.value=value
        def get_value(self,r,k):return self.value
    class Cursor:
        def __init__(self,rows,value):self.rows=rows;self.pgresult=Result(value)
        def fetchall(self):return self.rows
    class Conn:
        def __init__(self,rows,value):self.cursor=Cursor(rows,value)
        def execute(self,s):return self.cursor
    for rows,value,code in ((([('x'*500,)]),b'x'*500,'RESPONSE_BOUND'),([(1,)],b'1','RESPONSE_SHAPE'),([('a',),('b',)],b'a','RESPONSE_SHAPE')):
        runner=_runner(tmp_path,lambda:None)
        with pytest.raises(ProbeDenied) as caught:runner.one_statement(Conn(rows,value),STATEMENT)
        assert caught.value.code==code


def test_limits_are_consistent_with_the_reviewed_envelope():
    assert LIMITS['database_seconds']>=3+10 and LIMITS['dns_seconds']==3 and LIMITS['connection_attempts']==1 and LIMITS['driver_statements']==1 and LIMITS['rollbacks']==0
    assert ap.TIMING['input_seconds']+ap.TIMING['active_seconds']+ap.TIMING['report_seconds']<=ap.TIMING['outer_seconds']
    memory=Path('verification/ingestion_storage/operational_memory.py').read_text()
    assert str(LIMITS['controller_memory_bytes']//1024**2)+'*1024**2' in memory and str(LIMITS['aggregate_memory_bytes']//1024**2)+'*1024**2' in memory
    assert 'statement_timeout=10000' in STARTUP_OPTIONS


# --- mechanical absence of every forbidden capability ----------------------------------------------------------------------------------------------------

FORBIDDEN_MODULES=('operational_owner','credential_mapping','operational_runner','operational_source','operational_controller','storage_controller','app')


def test_probe_import_footprint_excludes_every_mutating_capability():
    code=("import sys;import verification.ingestion_storage.admin_connection_probe;"
          "bad=[m for m in sys.modules if m.split('.')[-1] in %r or m.startswith('app.') or m.startswith('verification.ingestion_storage.%s')];print(sorted(bad))")%(FORBIDDEN_MODULES,'operational_runner')
    out=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,env={'PATH':'/usr/bin:/bin','HOME':os.environ.get('HOME','/'),'DATABASE_URL':'sqlite:///:memory:'},timeout=60)
    assert out.returncode==0 and out.stdout.strip()=='[]',out.stdout+out.stderr


def test_probe_source_references_no_mutating_capability_names():
    tree=ast.parse(Path(ap.__file__).read_text());imported=set();names=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.ImportFrom):imported.add(node.module or '')|set() if False else imported.add(('.'*node.level)+(node.module or ''))
        elif isinstance(node,ast.Import):imported.update(a.name for a in node.names)
        elif isinstance(node,ast.Name):names.add(node.id)
        elif isinstance(node,ast.Attribute):names.add(node.attr)
    assert imported<={'argparse','getpass','hashlib','json','os','resource','subprocess','sys','time','warnings','datetime','pathlib','.connection_diagnostics','.operational_journal','.operational_outcome',
                      '.operational_preparation','.tls_trust','.operational_memory'},imported
    for forbidden in ('GitHub','Owner','put_secret','install_mapping','Runner','secure_migration_input','source_reader','apply_policy','invalidate_failure','teardown','register','map_and_activate'):
        assert forbidden not in names,forbidden


def test_no_external_effect_other_than_the_dns_child_and_the_loopback_connection(tmp_path,cluster,monkeypatch):
    seen=dict(subprocess=[],connect=[],resolve=[])
    real_connect=socket.socket.connect;real_resolve=socket.getaddrinfo;RealPopen=subprocess.Popen
    class SpyPopen(RealPopen):
        def __init__(self,cmd,*a,**k):
            seen['subprocess'].append(list(cmd)[:1] if isinstance(cmd,(list,tuple)) else cmd);super().__init__(cmd,*a,**k)
    monkeypatch.setattr(subprocess,'Popen',SpyPopen)
    monkeypatch.setattr(socket.socket,'connect',lambda self,addr:(seen['connect'].append(addr),real_connect(self,addr))[1])
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:(seen['resolve'].append(a[:2]),real_resolve(*a,**k))[1])
    result,j,lines,_,_=run_probe(tmp_path,factory(cluster))
    assert result['status']=='ADMIN_CONNECTION_QUALIFIED'
    assert all(c==[sys.executable] for c in seen['subprocess'])                                         # only the credential-free DNS child; no gh, no git, no curl
    assert all(isinstance(a,tuple) and a[0]=='127.0.0.1' and a[1]==cluster.port for a in seen['connect'] if a)       # the only socket connect is the disposable loopback server
    assert all(host=='127.0.0.1' for host,_ in seen['resolve'] if host not in (None,))


# --- registration -------------------------------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def bound(tmp_path,monkeypatch):
    f=tmp_path/'reviewed.txt';f.write_text('reviewed');monkeypatch.chdir(tmp_path)
    md=tmp_path/ap.EVIDENCE_DIRECTORY;md.mkdir(parents=True);(md/'MANIFEST.json').write_text(json.dumps(dict(bound_paths=['reviewed.txt'])))
    reg=probe_registration(hashes={'reviewed.txt':hashlib.sha256(b'reviewed').hexdigest()},controller_sha256=hashlib.sha256(Path(ap.__file__).read_bytes()).hexdigest())
    def fake_output(cmd,**kw):
        return {'rev-parse HEAD':reg['revision'],'rev-parse HEAD^{tree}':reg['tree'],'status --porcelain':''}[' '.join(cmd[1:])]
    monkeypatch.setattr(subprocess,'check_output',fake_output)
    return reg


def _validate(reg):
    body=json.dumps(reg).encode();return validate_probe_registration(body,hashlib.sha256(body).hexdigest())


def test_exact_registration_is_accepted(bound):
    assert _validate(bound)['mode']==MODE


@pytest.mark.parametrize('change,code',[
    (dict(mode='CONNECTION_DIAGNOSTIC_ONLY'),'EXACT_PROBE_APPROVAL_REQUIRED'),(dict(authority='AUTHORISE_INGESTION_ACTIONABLE_CONNECTION_DIAGNOSTIC_ONCE_20261018'),'EXACT_PROBE_APPROVAL_REQUIRED'),
    (dict(status='OWNER_APPROVED_REQUIRED_ONCE'),'EXACT_PROBE_APPROVAL_REQUIRED'),(dict(limits=dict(LIMITS,driver_statements=2)),'PROBE_LIMITS_OR_BOUNDARY_BINDING'),
    (dict(limits=dict(LIMITS,connection_attempts=2)),'PROBE_LIMITS_OR_BOUNDARY_BINDING'),(dict(absent_capabilities=['github_access']),'PROBE_LIMITS_OR_BOUNDARY_BINDING'),
    (dict(statement_sha256='0'*64),'PROBE_LIMITS_OR_BOUNDARY_BINDING'),(dict(expires_at=(datetime.now(timezone.utc)+timedelta(hours=3)).isoformat()),'PROBE_EXPIRY'),
    (dict(expires_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()),'PROBE_EXPIRY'),(dict(evidence_directory='docs/design/elsewhere'),'EVIDENCE_BINDING'),
    (dict(hashes={'reviewed.txt':'0'*64}),'REVIEWED_CONTENT_BINDING'),(dict(controller_sha256='0'*64),'CONTROLLER_CA_BINDING'),(dict(ca_sha256='0'*64),'CONTROLLER_CA_BINDING'),
])
def test_registration_rejections(bound,change,code):
    with pytest.raises(ValueError,match=code):_validate({**bound,**change})


def test_registration_requires_exact_keys_and_binding(bound,monkeypatch):
    with pytest.raises(ValueError,match='REGISTRATION_EXACT_KEYS'):_validate({**bound,'roles':['ingestion_worker_login']})
    with pytest.raises(ValueError,match='REGISTRATION_EXACT_KEYS'):_validate({k:v for k,v in bound.items() if k!='limits'})
    body=json.dumps(bound).encode()
    with pytest.raises(ValueError,match='REGISTRATION_SHA256'):validate_probe_registration(body,'0'*64)
    monkeypatch.setattr(subprocess,'check_output',lambda cmd,**kw:' M file\n' if cmd[1]=='status' else bound['revision'] if cmd[2]=='HEAD' else bound['tree'])
    with pytest.raises(ValueError,match='CLEAN_REVIEWED_CHECKOUT'):_validate(bound)


def test_authority_is_one_use_and_the_state_directory_is_exclusive(tmp_path):
    Journal(tmp_path/'state');
    with pytest.raises(FileExistsError):Journal(tmp_path/'state')


# --- the real main() entrypoint -------------------------------------------------------------------------------------------------------------------------------------

def _main_setup(tmp_path,monkeypatch,raw,reg):
    from verification.ingestion_storage import operational_memory
    body=json.dumps(reg).encode();digest=hashlib.sha256(body).hexdigest();path=tmp_path/'reg.json';path.write_bytes(body)
    for k in [k for k in os.environ if k.startswith('PG') or k in ('GH_TOKEN','GITHUB_TOKEN')]:monkeypatch.delenv(k)
    monkeypatch.setenv('HOME',str(tmp_path));monkeypatch.setattr(sys,'platform','linux');monkeypatch.setattr(sys.stdin,'isatty',lambda:True,raising=False);monkeypatch.setattr(sys.stderr,'isatty',lambda:True,raising=False)
    monkeypatch.setattr(ap,'validate_probe_registration',lambda b,sha:reg);monkeypatch.setattr(operational_memory,'OperationalMemory',Memory);monkeypatch.setattr(ap,'hidden_input',lambda:raw)
    monkeypatch.setattr(sys,'argv',['x','--registration',str(path),'--registration-sha256',digest])


def test_real_main_failure_exit_and_final_result(tmp_path,monkeypatch,capsys):
    _main_setup(tmp_path,monkeypatch,url(user='postgres'),probe_registration())
    with pytest.raises(SystemExit) as caught:ap.main()
    assert caught.value.code==1
    final=next((tmp_path/'.local/state/propertyaigent').glob('*/final-result.json'));result=json.loads(final.read_bytes())
    assert result['failure']['stage']=='ROUTE_VALIDATION' and result['outcome']['administrative_connection']=='NOT_ATTEMPTED' and result['accounting_schema']=='VALUE_BASIS_V2'
    out=capsys.readouterr();blob=final.read_text()+out.out+out.err
    assert SECRET not in blob and 'postgresql://' not in blob


def test_real_main_qualified_exit_zero(tmp_path,monkeypatch,cluster):
    _main_setup(tmp_path,monkeypatch,url(),probe_registration())
    original=ap.prepare_probe
    monkeypatch.setattr(ap,'prepare_probe',lambda *a,**k:original(*a,connect_factory=factory(cluster),**{**OK_DNS,**k}))
    with pytest.raises(SystemExit) as caught:ap.main()
    assert caught.value.code==0
    result=json.loads(next((tmp_path/'.local/state/propertyaigent').glob('*/final-result.json')).read_bytes())
    assert result['status']=='ADMIN_CONNECTION_QUALIFIED' and result['mode']==MODE and result['stage4']=='OPEN'


def test_main_refuses_github_credentials_and_pg_overrides(tmp_path,monkeypatch):
    _main_setup(tmp_path,monkeypatch,url(),probe_registration())
    monkeypatch.setenv('GH_TOKEN','x')
    with pytest.raises(SystemExit,match='NO_GITHUB_CREDENTIAL_PERMITTED_IN_PROBE'):ap.main()
    monkeypatch.delenv('GH_TOKEN');monkeypatch.setenv('PGHOST','x')
    with pytest.raises(SystemExit,match='LIBPQ_ENVIRONMENT_OVERRIDE'):ap.main()


# --- consumers of the value/basis schema ------------------------------------------------------------------------------------------------------------------------------

HISTORICAL=dict(administration=dict(commands=0,connections=0,returned_data_value_bytes=0),runtime=dict(slot_receipts={},supervised_seconds=0))


def test_historical_flat_accounting_passes_through_the_projection_unchanged():
    assert legacy_counts(HISTORICAL)==HISTORICAL and legacy_counts({})=={} and legacy_counts(None) is None


def test_value_basis_accounting_projects_to_flat_counts_with_unknown_as_none():
    flat=legacy_counts(dict(administration=dict(connections=dict(value=0,basis='MEASURED'),commands=dict(value=None,basis='UNKNOWN'),supervised_seconds=1.5),
                            runtime=dict(slot_receipts={},supervised_seconds=dict(value=0,basis='NOT_STARTED')),preparation=dict(state='x')))
    assert flat['administration']=={'connections':0,'commands':None,'supervised_seconds':1.5} and flat['runtime']['supervised_seconds']==0 and flat['preparation']=={'state':'x'}


def test_finalise_and_shared_session_accept_both_accounting_shapes(tmp_path):
    for accounting in (HISTORICAL,dict(administration=dict(connections=dict(value=0,basis='MEASURED')),runtime={})):
        j=Journal(tmp_path/('f%d'%time.monotonic_ns()));lines=[]
        result=oo.finalise(j,dict(status='STOP_RECONCILE_NO_RETRY',cleanup='UNCERTAIN',accounting=accounting),input_seconds=0,active_started=None,output=lambda l,**k:lines.append(l))
        assert json.loads((j.root/'final-result.json').read_bytes())['accounting']==accounting and len(lines)==1


# --- the release package: registration renderer, manifest and owner script ---------------------------------------------------------------------------------------

PACKAGE=Path('docs/design/ingestion-admin-connection-probe-20261018')


def test_rendered_registration_validates_against_the_actual_checkout(monkeypatch):
    import importlib.util
    spec=importlib.util.spec_from_file_location('render_registration',PACKAGE/'render_registration.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    reg=module.render(root=Path('.').resolve(),minutes=90)
    assert set(reg)==ap.REGISTRATION_KEYS and reg['limits']==LIMITS and reg['mode']==MODE
    manifest=json.loads((PACKAGE/'MANIFEST.json').read_text())
    assert sorted(reg['hashes'])==sorted(manifest['bound_paths']) and 'verification/ingestion_storage/trust/supabase-prod-ca-2021.crt' in reg['hashes']
    real=subprocess.check_output
    monkeypatch.setattr(subprocess,'check_output',lambda cmd,**kw:'' if cmd[1]=='status' else real(cmd,**kw))        # the working tree under test is not committed yet
    body=json.dumps(reg,sort_keys=True).encode();accepted=validate_probe_registration(body,hashlib.sha256(body).hexdigest())
    assert accepted['authority']==AUTHORITY
    with pytest.raises(SystemExit):
        monkeypatch.setattr(sys,'argv',['x','--minutes','121']);exec(compile((PACKAGE/'render_registration.py').read_text(),'r','exec'),{'__name__':'__main__','__file__':str((PACKAGE/'render_registration.py').resolve())})


def test_owner_script_takes_bound_arguments_requires_a_visible_tty_and_has_no_forbidden_capability():
    text=(PACKAGE/'owner-run.sh').read_text()
    assert '@@' not in text and 'USAGE: owner-run.sh <commit40> <tree40> <registration-sha256> <attempt>' in text                  # parameters are arguments, nothing is substituted into the script
    assert text.index('VISIBLE_INTERACTIVE_TTY_REQUIRED')<text.index('verify_predecessor')<text.index('systemd-run')               # TTY refusal and read-only checks precede anything that consumes the namespace
    for forbidden in ('gh ','gh api','secret set','curl','psql','operational_runner','credential_mapping','CONNECTION_DIAGNOSTIC_ONLY','read -s','getpass','PASSWORD','DATABASE_URL','git switch'):assert forbidden not in text,forbidden
    assert 'admin_connection_probe' in text and 'RuntimeMaxSec=200s' in text and 'MemoryMax=1610612736' in text and 'timeout 10s systemctl' in text and 'sha256sum' in text and 'controller_exit_status' in text
    assert subprocess.run(['bash','-n',str(PACKAGE/'owner-run.sh')]).returncode==0


def test_manifest_forbids_release_and_execution():
    manifest=json.loads((PACKAGE/'MANIFEST.json').read_text())
    assert manifest['status']=='PREPARED_FOR_REVIEW_NOT_RELEASED' and {'registration release','execution','merge','GitHub access'}<=set(manifest['forbidden_in_this_package'])
    assert all(Path(p).is_file() for p in manifest['bound_paths'])


# --- review round 3: admission denials, preparation scope, schema, hashes, the real connect closure ----------------------------------------------------------

def test_a_denial_before_any_attempt_is_not_a_connection_failure(tmp_path):
    j=Journal(tmp_path/'stop');(j.root/'STOP').touch()
    calls=[];runner=ProbeRunner(j,lambda:calls.append(1),Progress(),Memory(),baseline=owned_resources(),started=time.monotonic())
    result=runner.execute()
    assert not calls and result['failure']['reason_code']=='OWNER_STOP' and result['failure']['phase']=='PROBE_ADMISSION'
    assert result['outcome']['administrative_connection']=='NOT_ATTEMPTED' and result['accounting']['administration']['connection_attempts']=={'value':0,'basis':'MEASURED'}


def test_accounting_blocks_state_their_scope_and_basis_consistently(tmp_path,cluster):
    result,*_=run_probe(tmp_path,factory(cluster))
    a=result['accounting']
    assert a['preparation']=={'scope':'PREPARATION_ONLY','dns_subprocesses_spawned':{'value':1,'basis':'MEASURED','scope':'PREPARATION_DNS_CHILD_ONLY'}}      # no contradictory statement/connection claims
    assert a['administration']['driver_statements']['basis']=='CLIENT_COUNTED' and a['administration']['supervised_seconds']['basis']=='MEASURED'
    def every(node):
        for k,v in node.items():
            if isinstance(v,dict) and ('basis' in v or k in ('slot_receipts','preparation')):continue
            assert not isinstance(v,(int,float)) or isinstance(v,bool) is False and False,(k,v)
    every(a['administration'])                                                                                # every administration entry is a value/basis block


def test_the_real_connect_closure_reaches_the_server_with_one_statement(tmp_path,cluster,monkeypatch):
    """Runs the production `connect` closure itself; only the transport (host, TLS) is redirected to the disposable loopback server."""
    real=psycopg.connect;seen=[]
    def redirect(**k):
        seen.append(k)
        return real(host='127.0.0.1',port=cluster.port,dbname='postgres',user='postgres',autocommit=k['autocommit'],prepare_threshold=k['prepare_threshold'],options=k['options'],connect_timeout=k['connect_timeout'])
    monkeypatch.setattr(psycopg,'connect',redirect)
    before=(cluster.count(r'connection authorized'),len(cluster.statements()))
    result,j,lines,progress,_=run_probe(tmp_path,None)
    k=seen[0]
    assert (k['host'],k['port'],k['dbname'],k['user'],k['sslmode'],k['hostaddr'],k['password'],k['options'],k['autocommit'],k['prepare_threshold'],k['connect_timeout'])==(
        HOST,5432,'postgres','postgres.zcikcfgpblzuzpanpdqd','verify-full','192.0.2.7',SECRET,STARTUP_OPTIONS,True,None,3)
    assert result['status']=='ADMIN_CONNECTION_QUALIFIED' and (cluster.count(r'connection authorized'),len(cluster.statements()))==(before[0]+1,before[1]+1)
    assert cluster.statements()[-1].strip()==STATEMENT and progress.database_connection_calls==1
    secret_safe(j,lines,result)


def test_registration_hashes_must_equal_the_manifest(bound):
    with pytest.raises(ValueError,match='HASHES_MUST_EQUAL_MANIFEST'):_validate({**bound,'hashes':{**bound['hashes'],'extra.txt':'0'*64}})
    with pytest.raises(ValueError,match='EVIDENCE_BINDING'):_validate({**bound,'hashes':{}})


def test_early_outcome_derives_not_attempted_from_the_connection_count():
    closure=dict(overall='CLOSED')
    ok=Progress();assert oo.early_outcome(dict(reason_code='ROUTE_HOST_MISMATCH'),closure,ok)['administrative_connection']=='NOT_ATTEMPTED'
    ok.database_connection_calls=1;assert oo.early_outcome(dict(reason_code='ROUTE_HOST_MISMATCH'),closure,ok)['administrative_connection']=='UNKNOWN'
    assert oo.early_outcome(dict(reason_code='X'),closure,None)['administrative_connection']=='UNKNOWN'


# --- successor attempt: configurable but narrowly bound namespace, verified predecessor ---------------------------------------------------------------------------------

PREDECESSOR_FINAL=dict(status='STOP_RECONCILE_NO_RETRY',cleanup='CLOSED',failure=dict(stage='SESSION_INPUT'),outcome=dict(administrative_connection='NOT_ATTEMPTED'),closure_components=dict(overall='CLOSED'))


def make_predecessor(state_root,final=None):
    d=state_root/ap.ATTEMPTS[1]['state_directory'];d.mkdir(parents=True)
    (d/'events.jsonl').write_text('{"e":1}\n');(d/'final-result.json').write_text(json.dumps(final or PREDECESSOR_FINAL))
    return dict(attempt=1,state_directory=ap.STATE,events_sha256=hashlib.sha256((d/'events.jsonl').read_bytes()).hexdigest(),final_result_sha256=hashlib.sha256((d/'final-result.json').read_bytes()).hexdigest())


def successor(state_root,**changes):
    n=ap.probe_namespace(2);r=probe_registration(attempt=2,authority=n['authority'],state_directory=n['state_directory'],predecessor=make_predecessor(state_root))
    r.update(changes);return r


def test_namespaces_are_a_two_entry_table_and_distinct():
    assert set(ap.ATTEMPTS)=={1,2} and ap.probe_namespace(1)['state_directory']==ap.STATE and ap.probe_namespace(1)['authority']==AUTHORITY
    n=ap.probe_namespace(2);assert n['authority']!=AUTHORITY and n['state_directory']!=ap.STATE and n['state_directory'].startswith(ap.STATE) and n['predecessor']==1
    for bad in (0,3,-1,99):
        with pytest.raises(ValueError,match='PROBE_ATTEMPT_NOT_AUTHORISED'):ap.probe_namespace(bad)


def test_successor_registration_is_accepted_with_verified_predecessor(bound,tmp_path):
    reg=successor(tmp_path/'state',hashes=bound['hashes'],controller_sha256=bound['controller_sha256'],revision=bound['revision'],tree=bound['tree'])
    accepted=_validate(reg)
    assert accepted['attempt']==2 and accepted['state_directory']!=ap.STATE
    verified=ap.verify_predecessor(accepted,tmp_path/'state');assert verified['stage']=='SESSION_INPUT' and verified['closure']=='CLOSED'


@pytest.mark.parametrize('change,code',[
    (dict(attempt=3),'PROBE_ATTEMPT_NOT_AUTHORISED'),(dict(attempt=True),'PROBE_ATTEMPT_NOT_AUTHORISED'),(dict(attempt='2'),'PROBE_ATTEMPT_NOT_AUTHORISED'),
    (dict(authority=AUTHORITY),'EXACT_PROBE_APPROVAL_REQUIRED'),(dict(state_directory=ap.STATE),'EXACT_PROBE_APPROVAL_REQUIRED'),(dict(state_directory='elsewhere'),'EXACT_PROBE_APPROVAL_REQUIRED'),
    (dict(predecessor=None),'PREDECESSOR_BINDING'),(dict(predecessor={'attempt':1}),'PREDECESSOR_BINDING'),
])
def test_successor_registration_rejections(bound,tmp_path,change,code):
    reg=successor(tmp_path/'state',hashes=bound['hashes'],controller_sha256=bound['controller_sha256'],revision=bound['revision'],tree=bound['tree'])
    with pytest.raises(ValueError,match=code):_validate({**reg,**change})


def test_first_attempt_registration_cannot_claim_a_predecessor_or_the_successor_namespace(bound):
    n=ap.probe_namespace(2)
    with pytest.raises(ValueError,match='PREDECESSOR_BINDING'):_validate({**bound,'predecessor':dict(attempt=1,state_directory=ap.STATE,events_sha256='0'*64,final_result_sha256='0'*64)})
    with pytest.raises(ValueError,match='EXACT_PROBE_APPROVAL_REQUIRED'):_validate({**bound,'state_directory':n['state_directory']})


def test_predecessor_evidence_must_match_hash_and_recorded_outcome(tmp_path):
    root=tmp_path/'state';bound_pred=make_predecessor(root);reg=dict(probe_registration(),predecessor=bound_pred,attempt=2)
    assert ap.verify_predecessor(reg,root)['final_result_sha256']==bound_pred['final_result_sha256']
    (root/ap.STATE/'events.jsonl').write_text('tampered')
    with pytest.raises(ValueError,match='PREDECESSOR_EVIDENCE'):ap.verify_predecessor(reg,root)
    for label,final in (('connected',dict(PREDECESSOR_FINAL,outcome=dict(administrative_connection='QUALIFIED'))),('uncertain',dict(PREDECESSOR_FINAL,cleanup='UNCERTAIN')),
                        ('other-stage',dict(PREDECESSOR_FINAL,failure=dict(stage='DNS_RESOLUTION'))),('closure',dict(PREDECESSOR_FINAL,closure_components=dict(overall='UNCERTAIN')))):
        other=tmp_path/('s-'+label);pred=make_predecessor(other,final)
        with pytest.raises(ValueError,match='PREDECESSOR_OUTCOME'):ap.verify_predecessor(dict(reg,predecessor=pred),other)
    with pytest.raises(ValueError,match='PREDECESSOR_EVIDENCE'):ap.verify_predecessor(dict(reg,predecessor=bound_pred),tmp_path/'nowhere')
    assert ap.verify_predecessor(dict(reg,predecessor=None),tmp_path) is None


def test_real_main_uses_the_registered_namespace_and_verifies_the_predecessor(tmp_path,monkeypatch):
    state=tmp_path/'.local/state/propertyaigent';reg=successor(state)
    _main_setup(tmp_path,monkeypatch,url(user='postgres'),reg)
    with pytest.raises(SystemExit) as caught:ap.main()
    assert caught.value.code==1
    assert (state/reg['state_directory']/'final-result.json').exists() and 'attempt' in (state/reg['state_directory']/'events.jsonl').read_text()
    consumed=json.loads((state/ap.STATE/'final-result.json').read_text());assert consumed['cleanup']=='CLOSED'                 # the predecessor evidence is untouched
    monkeypatch.setattr(sys,'argv',sys.argv)
    with pytest.raises(FileExistsError):ap.main()                                                                             # second use of the successor namespace cannot start


def test_real_main_refuses_a_successor_when_the_predecessor_evidence_is_missing(tmp_path,monkeypatch):
    reg=successor(tmp_path/'elsewhere');_main_setup(tmp_path,monkeypatch,url(),reg)
    with pytest.raises(ValueError,match='PREDECESSOR_EVIDENCE'):ap.main()
    assert not (tmp_path/'.local/state/propertyaigent'/reg['state_directory']).exists()                                         # nothing consumed


# --- the hidden prompt really is non-echoing on a pseudo-terminal, including inside a systemd user scope -----------------------------------------------------------------

def _pty_run(argv,send,timeout=20):
    import pty,select
    pid,fd=pty.fork()
    if pid==0:
        os.execvp(argv[0],argv)
    out=b'';end=time.monotonic()+timeout;sent=False
    while time.monotonic()<end:
        ready,_,_=select.select([fd],[],[],0.2)
        if ready:
            try:chunk=os.read(fd,4096)
            except OSError:break
            if not chunk:break
            out+=chunk
            if not sent and b'hidden' in out:
                os.write(fd,send.encode()+b'\n');sent=True
        elif sent and out.count(b'RESULT=')>0:break
    try:os.close(fd)
    except OSError:pass
    _,status=os.waitpid(pid,0);return out.decode(errors='replace'),status


def test_hidden_input_does_not_echo_on_a_real_terminal():
    code="import sys;sys.path.insert(0,'.');from verification.ingestion_storage.admin_connection_probe import hidden_input;v=hidden_input();print('RESULT=%d'%len(v))"
    out,status=_pty_run([sys.executable,'-I','-B','-c',code],'PTY-SYNTHETIC-SECRET-VALUE')
    assert 'RESULT=26' in out and 'PTY-SYNTHETIC-SECRET-VALUE' not in out                                                   # received in full, never echoed to the terminal


@pytest.mark.skipif(shutil.which('systemd-run') is None or os.environ.get('INGESTION_OPERATIONAL_NATIVE')=='1',reason='user systemd scope required (not the hosted root scope)')
def test_hidden_input_inside_a_user_scope_keeps_the_terminal():
    code="import sys;sys.path.insert(0,'.');from verification.ingestion_storage.admin_connection_probe import hidden_input;print('TTY=%s%s'%(sys.stdin.isatty(),sys.stderr.isatty()));v=hidden_input();print('RESULT=%d'%len(v))"
    out,status=_pty_run(['systemd-run','--user','--scope','--quiet',f'--unit=propertyaigent-hidden-input-check-{os.getpid()}',sys.executable,'-I','-B','-c',code],'SCOPE-SYNTHETIC-SECRET')
    if 'Failed to connect' in out or 'Failed to start' in out:pytest.skip('no user systemd manager in this environment')
    assert 'TTY=TrueTrue' in out and 'RESULT=22' in out and 'SCOPE-SYNTHETIC-SECRET' not in out
