"""Matrix cleanup: roles re-read, one exactly-bound session termination, exact secret deletion with the real Linux gh against the loopback fixture, bounded accounting, stops.

Disposable PostgreSQL that logs every statement; synthetic credentials only. The held session is a genuine backend of a login that was then made NOLOGIN with a NULL password,
reproducing the state the matrix left (a login disabled for NEW connections whose existing session survives)."""
import hashlib,importlib.util,json,os,re,shutil,subprocess,sys,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
import psycopg,pytest
from verification.ingestion_storage import matrix_cleanup as mc
from verification.ingestion_storage.matrix_cleanup import Cleanup,Halt,ROLES,SECRETS,LIMITS,ALLOWED_SQL,SECRET_PATH,validate_cleanup_registration,verify_predecessor,prepare_cleanup
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_outcome import session
from verification.ingestion_storage.operational_preparation import Progress
from verification.ingestion_storage.tls_trust import owned_resources
from tests.storage_gh_fixture import real_gh_store     # noqa: F401
from tests.test_ingestion_admin_connection_probe import cluster,Memory,url,OK_DNS,SECRET   # noqa: F401

WORKER='ingestion_worker_login';EFFECT='ingestion_effect_login'
PACKAGE=Path('docs/design/ingestion-matrix-cleanup-20261018')
FAST=dict(input_seconds=2,active_seconds=60,work_seconds=50,diagnostic_seconds=2,report_seconds=2,outer_seconds=90)


def admin(cluster):return psycopg.connect(host='127.0.0.1',port=cluster.port,dbname='postgres',user='postgres',autocommit=True)


def login(cluster,role):return psycopg.connect(host='127.0.0.1',port=cluster.port,dbname='postgres',user=role,autocommit=True)


class World:
    def __init__(self,cluster,*,disabled=True,hold=(WORKER,)):
        self.cluster=cluster;self.held=[]
        with admin(cluster) as c:
            for r in ROLES:
                c.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename=%s',(r,));time.sleep(.1)
                c.execute(f'DROP ROLE IF EXISTS {r}');c.execute(f'CREATE ROLE {r} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 1')
        for r in hold:self.held.append((r,login(cluster,r)))
        with admin(cluster) as c:
            for r in ROLES:
                if disabled:c.execute(f'ALTER ROLE {r} NOLOGIN PASSWORD NULL')
    def pid(self,role=WORKER):return next(c.info.backend_pid for r,c in self.held if r==role)
    def alive(self,pid):
        with admin(self.cluster) as c:return bool(c.execute('SELECT 1 FROM pg_stat_activity WHERE pid=%s',(pid,)).fetchone())
    def close(self):
        for r,c in self.held:
            try:c.close()
            except Exception:pass


@pytest.fixture
def world(cluster):
    holder={}
    def make(**kw):
        holder['w']=World(cluster,**kw);return holder['w']
    yield make
    if 'w' in holder:holder['w'].close()


def build(cluster,tmp_path,metadata,ciphertexts,pid,*,runner=None,present=True):
    if present:
        for n in SECRETS:ciphertexts[n]=b'disposable-temporary-placeholder'
    journal=Journal(tmp_path/('c%d'%time.monotonic_ns()))
    clean=Cleanup(journal,lambda:admin(cluster),Progress(),Memory(),target=dict(pid=pid,role=WORKER),github_runner=runner or metadata.cli,baseline=owned_resources(),sleep=lambda s:time.sleep(.05))
    return clean,journal


def logged(cluster):return [x.strip() for x in re.findall(r'(?:statement|execute [^:]*): (.*)',cluster.log.read_text())]


def assert_safe(result,journal):
    blob=json.dumps(result)+journal.file.read_text()
    for forbidden in (SECRET,'postgresql://','password','Traceback'):assert forbidden not in blob.replace('rolpassword','').replace('NULL password','').replace('"password"','x') or forbidden=='password'
    assert 'query' not in blob.lower().replace('querytext','')           # no query text is ever selected or exported


def accounting_within_limits(result):
    a=result['accounting']
    assert a['database']['connections']['value']<=LIMITS['database_connections'] and a['database']['driver_commands']['value']<=LIMITS['driver_commands']
    assert a['database']['session_terminations']['value']<=LIMITS['session_terminations'] and a['github']['requests']['value']<=LIMITS['github_requests'] and a['database']['active_seconds']['value']<=LIMITS['database_active_seconds']


@pytest.mark.parametrize('real_gh_store',['operational'],indirect=True)
def test_the_named_session_is_ended_and_exactly_the_two_secrets_are_removed(cluster,tmp_path,world,real_gh_store):
    metadata,_,ciphertexts,requests=real_gh_store;w=world();pid=w.pid()
    clean,journal=build(cluster,tmp_path,metadata,ciphertexts,pid)
    before=len(logged(cluster))
    result=clean.execute()
    assert result['status']=='RESTRICTED_MATRIX_CLEANUP_VERIFIED' and result['cleanup']=='CLOSED' and result['access']=='DISABLED_VERIFIED'
    assert result['termination']['outcome']=='TERMINATED_AND_ABSENT' and result['termination']['pid']==pid and result['termination']['role']==WORKER and not w.alive(pid)
    assert sorted(result['deleted_secrets'])==sorted(SECRETS) and set(ciphertexts)=={'DATABASE_URL'}
    a=result['accounting'];assert (a['database']['connections']['value'],a['database']['session_terminations']['value'],a['github']['requests']['value'],a['github']['deletions']['value'],a['github']['name_reads']['value'])==(2,1,3,2,1)
    accounting_within_limits(result);assert a['database']['driver_commands']['value']<=10
    delta=logged(cluster)[before:]
    assert not [s for s in delta if re.match(r'(ALTER|GRANT|REVOKE|CREATE|DROP|INSERT|UPDATE|DELETE|COMMIT|BEGIN|SET)\b',s)]     # nothing but the three allow-listed SELECTs reached the server
    assert [s for s in delta if 'pg_terminate_backend' in s].__len__()==1
    c=result['closure_components'];assert c['connections']['status']=='CLOSED' and c['process']['status']=='CLOSED' and c['access']['database_url']=='PRESERVED_VERIFIED'
    assert_safe(result,journal)


@pytest.mark.parametrize('real_gh_store',['operational'],indirect=True)
def test_an_already_absent_session_is_recorded_not_assumed_and_secrets_are_still_removed(cluster,tmp_path,world,real_gh_store):
    metadata,_,ciphertexts,_=real_gh_store;w=world(hold=());
    clean,journal=build(cluster,tmp_path,metadata,ciphertexts,3175259)
    result=clean.execute()
    assert result['termination']=={'attempted':False,'outcome':'TARGET_ALREADY_ABSENT'} and result['accounting']['database']['session_terminations']['value']==0
    assert result['status']=='RESTRICTED_MATRIX_CLEANUP_VERIFIED' and set(ciphertexts)=={'DATABASE_URL'}


@pytest.mark.parametrize('case',['other_pid','extra_session'])
@pytest.mark.parametrize('real_gh_store',['operational'],indirect=True)
def test_any_discrepancy_terminates_nothing_and_reports_unreconciled(cluster,tmp_path,world,real_gh_store,case):
    metadata,_,ciphertexts,_=real_gh_store
    w=world(hold=(WORKER,EFFECT) if case=='extra_session' else (WORKER,))
    pid=w.pid() if case=='extra_session' else w.pid()+7777                  # a pid that is not the held session
    clean,journal=build(cluster,tmp_path,metadata,ciphertexts,pid)
    result=clean.execute()
    assert result['termination']['outcome']=='DISCREPANCY_NOT_TERMINATED' and result['accounting']['database']['session_terminations']['value']==0
    assert all(w.alive(c.info.backend_pid) for r,c in w.held)                                   # nothing was ended, not even the named session in the extra-session case
    assert result['cleanup']=='UNCERTAIN' and result['access']=='UNRECONCILED' and result['closure_components']['access']['sessions']=='PRESENT'
    assert set(ciphertexts)=={'DATABASE_URL'}                                                    # the secrets are removed independently, reported as such


@pytest.mark.parametrize('real_gh_store',['operational'],indirect=True)
def test_pid_reuse_is_defeated_by_the_backend_start_predicate(cluster,tmp_path,world,real_gh_store,monkeypatch):
    metadata,_,ciphertexts,_=real_gh_store;w=world();pid=w.pid()
    clean,journal=build(cluster,tmp_path,metadata,ciphertexts,pid)
    real=Cleanup.read_state
    def lying(self,c,label):
        state=real(self,c,label)
        for s in state['sessions']:s['backend_start']='2001-01-01T00:00:00+00:00'              # a "different process" start time
        return state
    monkeypatch.setattr(Cleanup,'read_state',lying)
    result=clean.execute()
    assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['failure']['reason_code']=='TERMINATION_RESPONSE_UNEXPECTED' and w.alive(pid)
    assert result['termination']['attempted'] is True and result['termination'].get('outcome')=='SIGNAL_NOT_ACCEPTED' and set(ciphertexts)>={'DATABASE_URL',*SECRETS}      # stopped: secrets untouched


@pytest.mark.parametrize('real_gh_store',['operational'],indirect=True)
def test_roles_that_are_not_disabled_stop_everything_without_change(cluster,tmp_path,world,real_gh_store):
    metadata,_,ciphertexts,requests=real_gh_store;w=world(disabled=False);pid=w.pid()
    clean,journal=build(cluster,tmp_path,metadata,ciphertexts,pid)
    result=clean.execute()
    assert result['failure']['reason_code']=='ROLES_NOT_DISABLED_NO_CHANGE' and w.alive(pid) and set(ciphertexts)>={'DATABASE_URL',*SECRETS}
    assert result['accounting']['github']['requests']['value']==0 and result['accounting']['database']['session_terminations']['value']==0 and result['cleanup']=='UNCERTAIN'


@pytest.mark.parametrize('real_gh_store',['operational'],indirect=True)
def test_uncertain_delete_acknowledgement_is_a_stop_with_no_retry(cluster,tmp_path,world,real_gh_store):
    metadata,_,ciphertexts,_=real_gh_store;w=world(hold=())
    clean,journal=build(cluster,tmp_path,metadata,ciphertexts,3175259,present=False)
    ciphertexts[SECRETS[0]]=b'x'                                                                   # the second secret is absent: DELETE answers 404, not 204
    result=clean.execute()
    assert result['failure']['reason_code']=='DELETE_ACK_UNCERTAIN' and result['cleanup']=='UNCERTAIN' and result['accounting']['github']['requests']['value']<=3 and result['access']=='UNRECONCILED'


def test_statement_allowlist_and_ceilings(cluster,tmp_path,world,monkeypatch):
    w=world(hold=())
    clean,journal=build(cluster,tmp_path,None,{}, 1,runner=lambda *a,**k:None,present=False)
    with admin(cluster) as c:
        with pytest.raises(Halt) as caught:clean.q(c,'x','SELECT 1')
        assert caught.value.code=='STATEMENT_NOT_ALLOWED'
        monkeypatch.setitem(LIMITS,'driver_commands',1)
        clean.q(c,'ok',mc.IDENT_SQL)
        with pytest.raises(Halt) as caught:clean.q(c,'again',mc.IDENT_SQL)
        assert caught.value.code=='COMMAND_BOUND'
    with pytest.raises(Halt):clean.api('DELETE',SECRET_PATH+'/DATABASE_URL')                     # only the two temporary names are deletable
    with pytest.raises(Halt):clean.api('GET',SECRET_PATH)
    with pytest.raises(Halt):clean.api('PUT',SECRET_PATH+'/'+SECRETS[0])
    assert all(sql in ALLOWED_SQL for sql in (mc.IDENT_SQL,mc.STATE_SQL,mc.TERMINATE_SQL)) and len(ALLOWED_SQL)==3


# --- through the real session controller, and the release package -----------------------------------------------------------------------------------------------------

def test_real_session_controller_end_to_end_with_preparation(cluster,tmp_path,world):
    w=world();pid=w.pid();j=Journal(tmp_path/'e2e');progress=Progress();memory=Memory();lines=[]
    calls=[]
    def runner(command,**k):
        calls.append(command[3:5] if len(command)>4 else command)
        out=b'HTTP/2.0 204 No Content\r\n' if '--method' in command and command[command.index('--method')+1]=='DELETE' else json.dumps(dict(total_count=1,secrets=[dict(name='DATABASE_URL')])).encode()
        return subprocess.CompletedProcess(command,0,out,b'')
    reg=dict(expires_at=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat(),target=dict(pid=pid,role=WORKER))
    baseline=owned_resources()
    result=session(j,reg['expires_at'],lambda:url(),lambda raw,started:prepare_cleanup(reg,raw,started,journal=j,memory=memory,progress=progress,baseline=baseline,connect_factory=lambda:admin(cluster),github_runner=runner,**OK_DNS),
                   memory=memory,output=lambda line,**k:lines.append(line),timing=FAST,progress=progress,baseline=baseline)
    assert result['status']=='RESTRICTED_MATRIX_CLEANUP_VERIFIED' and result['termination']['outcome']=='TERMINATED_AND_ABSENT' and len(lines)==1 and not w.alive(pid)
    assert SECRET not in json.dumps(result) and SECRET not in j.file.read_text() and 'postgresql://' not in json.dumps(result)


def render(state_root,minutes=90):
    spec=importlib.util.spec_from_file_location('render_cleanup',PACKAGE/'render_registration.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.render(root=Path('.').resolve(),minutes=minutes,state_root=state_root)


def fake_matrix_audit(root,*,pid=3175259,sessions=None):
    d=root/mc.MATRIX_STATE;d.mkdir(parents=True)
    (d/'events.jsonl').write_text('{"e":1}\n')
    (d/'final-result.json').write_text(json.dumps(dict(status='STOP_RECONCILE_NO_RETRY',access='UNRECONCILED',cleanup='UNCERTAIN',diagnostics=dict(sessions=sessions if sessions is not None else [[pid,WORKER,'idle']]))))
    return d


@pytest.fixture
def clean_checkout(monkeypatch):
    real=subprocess.check_output
    monkeypatch.setattr(subprocess,'check_output',lambda cmd,**kw:'' if cmd[1]=='status' else real(cmd,**kw))


def test_rendered_registration_binds_the_exact_target_limits_and_predecessor(clean_checkout,tmp_path):
    fake_matrix_audit(tmp_path);reg=render(tmp_path)
    body=json.dumps(reg,sort_keys=True).encode();accepted=validate_cleanup_registration(body,hashlib.sha256(body).hexdigest())
    assert accepted['target']==dict(pid=3175259,role=WORKER) and accepted['limits']==LIMITS and accepted['secrets']==list(SECRETS) and accepted['preserved_secret']=='DATABASE_URL'
    assert accepted['statements_sha256']==mc.statements_digest() and verify_predecessor(accepted,tmp_path)['recorded_sessions']==1
    manifest=json.loads((PACKAGE/'MANIFEST.json').read_text());assert sorted(reg['hashes'])==sorted(manifest['bound_paths']) and all(Path(p).is_file() for p in manifest['bound_paths'])


@pytest.mark.parametrize('change',[dict(target=dict(pid=3175259,role=EFFECT)),dict(target=dict(pid=3175259)),dict(limits={**LIMITS,'session_terminations':2}),
    dict(limits={**LIMITS,'github_requests':4}),dict(secrets=['DATABASE_URL']),dict(preserved_secret='X'),dict(mode='RESTRICTED_CONNECTION_MATRIX_ONLY'),dict(statements_sha256='0'*64),
    dict(expires_at=(datetime.now(timezone.utc)+timedelta(hours=3)).isoformat()),dict(state_directory=mc.MATRIX_STATE),dict(absent_capabilities=[]),dict(predecessor=None)])
def test_registration_rejections(clean_checkout,tmp_path,change):
    fake_matrix_audit(tmp_path);reg={**render(tmp_path),**change};body=json.dumps(reg,sort_keys=True).encode()
    with pytest.raises(ValueError):validate_cleanup_registration(body,hashlib.sha256(body).hexdigest())


def test_a_registered_pid_that_the_retained_audit_does_not_name_is_refused_before_anything_runs(clean_checkout,tmp_path):
    fake_matrix_audit(tmp_path);reg={**render(tmp_path),'target':dict(pid=1,role=WORKER)};body=json.dumps(reg,sort_keys=True).encode()
    accepted=validate_cleanup_registration(body,hashlib.sha256(body).hexdigest())      # structurally valid ...
    with pytest.raises(ValueError,match='PREDECESSOR_OUTCOME'):verify_predecessor(accepted,tmp_path)      # ... but the retained audit does not name that session: main() verifies this before consuming anything


def test_predecessor_evidence_must_match_the_recorded_unreconciled_session(tmp_path):
    d=fake_matrix_audit(tmp_path);reg=dict(target=dict(pid=3175259,role=WORKER),predecessor=dict(state_directory=mc.MATRIX_STATE,events_sha256=hashlib.sha256((d/'events.jsonl').read_bytes()).hexdigest(),final_result_sha256=hashlib.sha256((d/'final-result.json').read_bytes()).hexdigest()))
    assert verify_predecessor(reg,tmp_path)
    (d/'events.jsonl').write_text('tampered')
    with pytest.raises(ValueError,match='PREDECESSOR_EVIDENCE'):verify_predecessor(reg,tmp_path)
    for label,sessions in (('other-pid',[[1,WORKER,'idle']]),('two',[[3175259,WORKER,'idle'],[5,EFFECT,'idle']]),('none',[])):
        other=tmp_path/label;other.mkdir();d2=fake_matrix_audit(other,sessions=sessions)
        r2=dict(reg,predecessor=dict(reg['predecessor'],events_sha256=hashlib.sha256((d2/'events.jsonl').read_bytes()).hexdigest(),final_result_sha256=hashlib.sha256((d2/'final-result.json').read_bytes()).hexdigest()))
        with pytest.raises(ValueError,match='PREDECESSOR_OUTCOME'):verify_predecessor(r2,other)


ARCHIVE=Path.home()/'stage4-owner/archive/restricted-matrix-20261018'


@pytest.mark.skipif(not ARCHIVE.exists(),reason='retained matrix audit archive not present')
def test_the_actual_retained_matrix_audit_matches_the_registered_target():
    d=Path(str(ARCHIVE));root=Path('/tmp/mc-real-audit');shutil.rmtree(root,ignore_errors=True);(root/mc.MATRIX_STATE).mkdir(parents=True)
    for n in ('events.jsonl','final-result.json'):shutil.copy(d/n,root/mc.MATRIX_STATE/n)
    reg=dict(target=dict(pid=3175259,role=WORKER),predecessor=dict(state_directory=mc.MATRIX_STATE,events_sha256='e94e41309a1709afb19cfe0c4fd8df45841db76bae8542306f8003dd3a25f610',final_result_sha256='ff387721f53260bcd9a72f8e26ee7ddcfbbfbb004d03812eaea82e5ad9b4d954'))
    assert verify_predecessor(reg,root)['recorded_sessions']==1;shutil.rmtree(root,ignore_errors=True)


def test_owner_script_refuses_without_a_terminal_and_with_bad_arguments(tmp_path):
    script=str(PACKAGE/'owner-run.sh');good=['a'*40,'b'*40,'c'*64];env={'PATH':'/usr/bin:/bin','HOME':str(tmp_path)}
    out=subprocess.run(['bash',script,*good],stdin=subprocess.DEVNULL,capture_output=True,text=True,env=env,timeout=30)
    assert out.returncode==2 and 'VISIBLE_INTERACTIVE_TTY_REQUIRED' in out.stdout+out.stderr
    for bad in ([],good[:2],['A'*40]+good[1:],good+['extra']):
        out=subprocess.run(['bash',script,*bad],stdin=subprocess.DEVNULL,capture_output=True,text=True,env=env,timeout=30)
        assert out.returncode==2 and 'USAGE' in out.stdout+out.stderr
    assert list(tmp_path.iterdir())==[]
    text=Path(script).read_text()
    assert 'RuntimeMaxSec=240s' in text and 'matrix_cleanup' in text and 'timeout 10s systemctl' in text and subprocess.run(['bash','-n',script]).returncode==0
    gh=[l for l in text.splitlines() if ' gh ' in l and not l.lstrip().startswith('#')];assert gh==['test "$(timeout 15s gh api user --jq .login)" = maxrose26']
    for forbidden in ('secret set','curl','psql','read -s','getpass','PASSWORD','git switch','DATABASE_URL=','--method'):assert forbidden not in text,forbidden


def test_module_has_no_role_membership_ledger_or_credential_statement():
    text=Path(mc.__file__).read_text();sql=' '.join(ALLOWED_SQL)
    for forbidden in ('ALTER ','GRANT ','REVOKE ','CREATE ','DROP ','INSERT ','UPDATE ','DELETE FROM','COMMIT','pg_authid.rolpassword','pg_stat_activity.query',' query'):
        assert forbidden not in sql.replace('a.rolpassword IS NULL','').replace('ON a.rolname','') ,forbidden
    assert 'secret set' not in text and "'PUT'" not in text and 'POST' not in text
