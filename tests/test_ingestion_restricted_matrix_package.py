"""The matrix through the real Runner/session wrapper and the release package: registration binding, mode wiring, failure handling, teardown, owner script.

The lifecycle's database-side steps (install, mapping, activation, teardown SQL, administrative accounting) are exercised against the restricted PG17 fixture in
test_discovery_ingestion_operational_wrapper_pg.py (matrix_* faults). Here those owner steps are replaced by recording fakes so that the REAL Runner.execute/failed/closure,
the REAL session controller and the REAL matrix run against a disposable server that logs every statement."""
import hashlib,importlib.util,json,os,subprocess,sys,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
import psycopg,pytest
from sqlalchemy.engine import make_url
from verification.ingestion_storage import operational_runner as orr, restricted_matrix as rm
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_outcome import session
from verification.ingestion_storage.operational_runner import Runner,validate_registration,MATRIX_MODE
from verification.ingestion_storage.tls_trust import owned_resources
from tests.test_ingestion_admin_connection_probe import cluster      # noqa: F401
from tests.test_ingestion_restricted_matrix import roles,WORKER,EFFECT,sessions   # noqa: F401

PACKAGE=Path('docs/design/ingestion-restricted-connection-matrix-20261018')
FAST=dict(input_seconds=2,active_seconds=30,work_seconds=25,diagnostic_seconds=5,report_seconds=2,outer_seconds=60)


def render(minutes=90):
    spec=importlib.util.spec_from_file_location('render_matrix_registration',PACKAGE/'render_registration.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.render(root=Path('.').resolve(),minutes=minutes)


def validate(reg,monkeypatch=None):
    body=json.dumps(reg,sort_keys=True).encode()
    return validate_registration(body,hashlib.sha256(body).hexdigest())


@pytest.fixture
def clean_checkout(monkeypatch):
    real=subprocess.check_output
    monkeypatch.setattr(subprocess,'check_output',lambda cmd,**kw:'' if cmd[1]=='status' else real(cmd,**kw))       # the working tree under test is not committed yet


# --- registration binding ---------------------------------------------------------------------------------------------------------------------------------

def test_rendered_registration_is_accepted_and_binds_the_finite_test(clean_checkout):
    reg=render()
    accepted=validate(reg)
    assert accepted['mode']==MATRIX_MODE and accepted['authority']==orr.MATRIX_AUTHORITY and accepted['execution_authority']=='NONE'
    assert accepted['matrix']==[list(e) for e in rm.ENTRIES] and accepted['matrix_limits']==rm.LIMITS and accepted['risk_application']=='THIS_FINITE_RESTRICTED_CONNECTION_MATRIX_ONLY'
    assert accepted['risk_acceptance']=='ACCEPT_POSSIBLE_PROVIDER_SCRAM_VERIFIER_RETENTION_WORKER_EFFECT_ONCE' and accepted['state_directory']==orr.MATRIX_STATE
    manifest=json.loads((PACKAGE/'MANIFEST.json').read_text())
    assert sorted(reg['hashes'])==sorted(manifest['bound_paths']) and all(Path(p).is_file() for p in manifest['bound_paths'])
    assert reg['manifest_sha256']==hashlib.sha256((PACKAGE/'MANIFEST.json').read_bytes()).hexdigest()


@pytest.mark.parametrize('change',[
    dict(matrix=[['ingestion_worker_login','NONE']]),dict(matrix=[['ingestion_worker_login','NONE'],['ingestion_worker_login','REVIEWED'],['ingestion_effect_login','REVIEWED'],['ingestion_effect_login','NONE']]),
    dict(matrix_limits={**rm.LIMITS,'connection_attempts':5}),dict(matrix_limits={**rm.LIMITS,'administrative_commands':65}),
    dict(owner_limits=dict(connections=[11,13],commands=[200,232,240])),dict(execution_authority='CAPTURE'),dict(execution_authority=None),
    dict(risk_application='ANY_FUTURE_USE'),dict(state_directory='operational-actionable-diagnostic-once-20261018'),
    dict(authority='AUTHORISE_INGESTION_ACTIONABLE_CONNECTION_DIAGNOSTIC_ONCE_20261018'),dict(mode='REQUIRED_CAPTURE_SCREENING'),
    dict(expires_at=(datetime.now(timezone.utc)+timedelta(hours=3)).isoformat()),dict(risk_acceptance='NONE'),dict(roles=['ingestion_worker_login']),
    dict(execution=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=2,retry=False,state_directory=orr.MATRIX_STATE)),dict(execution=None),
])
def test_registration_rejections(clean_checkout,change):
    reg={**render(),**change}
    with pytest.raises(ValueError):validate(reg)


def test_the_capture_registration_cannot_be_used_for_the_matrix_and_vice_versa(clean_checkout):
    reg=render();reg['mode']='CONNECTION_DIAGNOSTIC_ONLY'
    with pytest.raises(ValueError):validate(reg)            # authority is not the diagnostic authority


# --- the real Runner/session wrapper with recording owner fakes ---------------------------------------------------------------------------------------------

class FakeGitHub:
    requests=0;mutation_uncertain=False
    def call(self,method,path,body=None):return {'login':'maxrose26'}
    def names(self):return ['DATABASE_URL']
    def put_secret(self,name,value):self.requests+=1


def harness(cluster,tmp_path,*,connect=None,fail_at=None,unclean_teardown=False):
    reg={**render(),'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()}
    journal=Journal(tmp_path/('m%d'%time.monotonic_ns()))
    runner=Runner(reg,journal,lambda:None,source_reader=None,github=FakeGitHub(),url_factory=lambda r,p:None)
    calls=[]
    def preflight():
        calls.append('preflight')
        if fail_at=='preflight':raise RuntimeError('private text')
    def install():calls.append('install')
    def map_and_activate(github,*,url_factory):
        calls.append('map')
        runner.owner.urls={r:f'postgresql://{r}:synthetic@127.0.0.1:{cluster.port}/postgres' for r in (WORKER,EFFECT)}
        now=time.monotonic()
        for r in (WORKER,EFFECT):runner.owner.timeline[r]=dict(password_committed=now,mapped=now,activated=now)
        if fail_at=='map':raise ValueError('ADMIN_COMMAND_BOUND')
    def teardown(github):
        calls.append('teardown')
        if unclean_teardown:
            from verification.ingestion_storage.operational_publication import Uncertain
            raise Uncertain('TEARDOWN_RECONCILE')
        runner.owner.urls.clear()
    runner.owner.preflight=preflight;runner.owner.install=install;runner.owner.map_and_activate=map_and_activate;runner.owner.teardown=teardown
    runner.owner.diagnostics=lambda:{'completion':'FAKE'}
    original=rm.Matrix.__init__
    def patched(self,r,**kw):
        original(self,r,principal=lambda url,ssl:(make_url(url),make_url(url).username),**({'connect':connect} if connect else {}))
    rm.Matrix.__init__=patched
    return runner,journal,reg,calls,original


def run(cluster,tmp_path,monkeypatch,**kw):
    runner,journal,reg,calls,original=harness(cluster,tmp_path,**kw);lines=[]
    try:
        result=session(journal,reg['expires_at'],lambda:'disposable hidden input',lambda raw,started:runner,output=lambda line,**k:lines.append(line),timing=FAST)
    finally:rm.Matrix.__init__=original
    return result,runner,journal,calls,lines


def test_mode_wiring_uses_matrix_limits_deadlines_and_no_policy(cluster,tmp_path):
    runner,journal,reg,calls,original=harness(cluster,tmp_path);rm.Matrix.__init__=original
    assert runner.matrix_mode and runner.owner.limits==dict(connections=orr.MATRIX_OWNER_LIMITS['connections'],commands=orr.MATRIX_OWNER_LIMITS['commands']) and runner.owner.apply_policy is False
    assert runner.deadlines==orr.MATRIX_DEADLINES and runner.deadlines['job']<orr.DEFAULT_DEADLINES['job']
    assert orr.DEFAULT_DEADLINES==dict(job=450,diagnostic_total=475,diagnostic_window=25,admin_diagnostic=240,admin_pre=210,admin_total=240,runtime_total=300)       # capture-run defaults unchanged
    from verification.ingestion_storage.operational_owner import Owner
    assert Owner.DEFAULT_LIMITS==dict(connections=(11,13),commands=(200,232,240))


def test_complete_run_through_the_real_wrapper(cluster,roles,tmp_path,monkeypatch):
    result,runner,journal,calls,lines=run(cluster,tmp_path,monkeypatch)
    assert result['status']=='RESTRICTED_MATRIX_COMPLETED_ACCESS_DISABLED' and result['cleanup']=='CLOSED' and calls==['preflight','install','map','teardown']
    assert [e['outcome'] for e in result['matrix']['entries']]==['CONNECTED_IDENTITY_VERIFIED']*4 and result['execution_grants_created']==0 and result['source_observations_attempted']==0
    assert json.loads((journal.root/'final-result.json').read_bytes())==json.loads(json.dumps(result)) and len(lines)==1 and sessions(cluster)==0
    assert not runner.owner.authorities and 'synthetic' not in json.dumps(result) and 'synthetic' not in journal.file.read_text()


def test_global_stop_inside_the_matrix_still_attempts_teardown_and_reports_every_entry(cluster,roles,tmp_path,monkeypatch):
    real=psycopg.connect;count=[0]
    def connect(**k):
        count[0]+=1
        if count[0]==2:raise RuntimeError('private text')
        return real(**k)
    result,runner,journal,calls,lines=run(cluster,tmp_path,monkeypatch,connect=connect)
    assert result['status']=='STOP_RECONCILE_NO_RETRY' and calls==['preflight','install','map','teardown'] and result['access']=='DISABLED_VERIFIED'
    assert [e['outcome'] for e in result['matrix']['entries']]==['CONNECTED_IDENTITY_VERIFIED','FAILED_UNCLASSIFIED','SKIPPED_GLOBAL_STOP','SKIPPED_GLOBAL_STOP'] and result['matrix']['global_stop']=='UNCLASSIFIED_FAILURE'
    assert result['matrix']['accounting']['connection_attempts']['value']==2 and 'private text' not in json.dumps(result) and 'private text' not in journal.file.read_text()


def test_classified_failures_continue_and_complete_with_teardown(cluster,roles,tmp_path,monkeypatch):
    real=psycopg.connect;count=[0]
    def connect(**k):
        count[0]+=1
        if count[0] in (1,4):raise psycopg.errors.InvalidPassword('password authentication failed for user "x"')
        return real(**k)
    result,runner,journal,calls,lines=run(cluster,tmp_path,monkeypatch,connect=connect)
    assert result['status']=='RESTRICTED_MATRIX_COMPLETED_ACCESS_DISABLED' and calls[-1]=='teardown'
    assert [e['outcome'] for e in result['matrix']['entries']]==['FAILED_CLASSIFIED','CONNECTED_IDENTITY_VERIFIED','CONNECTED_IDENTITY_VERIFIED','FAILED_CLASSIFIED']
    assert result['matrix']['accounting']['entries_connected']['value']==2 and result['matrix']['accounting']['identity_statements']['value']==2


def test_lifecycle_failure_before_the_matrix_marks_all_entries_skipped(cluster,roles,tmp_path,monkeypatch):
    result,runner,journal,calls,lines=run(cluster,tmp_path,monkeypatch,fail_at='preflight')
    assert result['status']=='STOP_RECONCILE_NO_RETRY' and 'teardown' not in calls
    assert [e['outcome'] for e in result['matrix']['entries']]==['SKIPPED_GLOBAL_STOP']*4 and result['matrix']['global_stop']=='LIFECYCLE_STOP_BEFORE_MATRIX_COMPLETE'
    assert result['matrix']['accounting']['connection_attempts']['value']==0 and result['matrix']['accounting']['entries_not_attempted']['value']==4


def test_failure_after_credentials_exist_runs_teardown_and_never_the_matrix(cluster,roles,tmp_path,monkeypatch):
    result,runner,journal,calls,lines=run(cluster,tmp_path,monkeypatch,fail_at='map')
    assert calls==['preflight','install','map','teardown'] and result['access']=='DISABLED_VERIFIED'
    assert result['matrix']['accounting']['connection_attempts']['value']==0 and sessions(cluster)==0


def test_uncertain_teardown_is_reported_uncertain_not_closed(cluster,roles,tmp_path,monkeypatch):
    result,runner,journal,calls,lines=run(cluster,tmp_path,monkeypatch,unclean_teardown=True)
    assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['cleanup']=='UNCERTAIN' and result['access']!='DISABLED_VERIFIED'


def test_matrix_failure_results_leave_no_executable_authority(cluster,roles,tmp_path,monkeypatch):
    result,runner,journal,calls,lines=run(cluster,tmp_path,monkeypatch)
    assert result['execution_grants_created']==0 and result['application_writes']==0 and result['pipeline_retry']=='HELD' and result['stage4']=='OPEN'
    assert 'authorities' not in result or not result.get('authorities')


# --- release package ---------------------------------------------------------------------------------------------------------------------------------------------

def test_owner_script_refuses_without_a_terminal_and_with_bad_arguments(tmp_path):
    script=str(PACKAGE/'owner-run.sh');good=['a'*40,'b'*40,'c'*64];env={'PATH':'/usr/bin:/bin','HOME':str(tmp_path)}
    out=subprocess.run(['bash',script,*good],stdin=subprocess.DEVNULL,capture_output=True,text=True,env=env,timeout=30)
    assert out.returncode==2 and 'VISIBLE_INTERACTIVE_TTY_REQUIRED' in out.stdout+out.stderr
    for bad in ([],good[:2],['A'*40]+good[1:],good+['extra']):
        out=subprocess.run(['bash',script,*bad],stdin=subprocess.DEVNULL,capture_output=True,text=True,env=env,timeout=30)
        assert out.returncode==2 and 'USAGE' in out.stdout+out.stderr
    assert list(tmp_path.iterdir())==[]


def test_owner_script_has_only_the_one_read_only_github_call_and_no_credential_path():
    text=(PACKAGE/'owner-run.sh').read_text()
    assert '@@' not in text and text.index('VISIBLE_INTERACTIVE_TTY_REQUIRED')<text.index('systemd-run') and 'RuntimeMaxSec=450s' in text and 'timeout 10s systemctl' in text and 'controller_exit_status' in text
    gh_lines=[l for l in text.splitlines() if ' gh ' in l and not l.lstrip().startswith('#')]
    assert gh_lines==['test "$(timeout 15s gh api user --jq .login)" = maxrose26']
    for forbidden in ('secret set','curl','psql','read -s','getpass','PASSWORD','DATABASE_URL','git switch','operational_publication','--method'):assert forbidden not in text,forbidden
    assert subprocess.run(['bash','-n',str(PACKAGE/'owner-run.sh')]).returncode==0


def test_package_separates_the_diagnostic_allowance_from_execution_authority():
    text=(PACKAGE/'PACKAGE.md').read_text()
    for phrase in ('DIAGNOSTIC ALLOWANCE','EXECUTION AUTHORITY','NONE','does not establish','SU-511198','unsent'):assert phrase in text,phrase
    manifest=json.loads((PACKAGE/'MANIFEST.json').read_text())
    assert manifest['status']=='PREPARED_FOR_REVIEW_NOT_RELEASED' and manifest['execution_authority']=='NONE' and {'registration release','execution','credential generation','mapping','activation','connection'}<=set(manifest['forbidden_in_this_package'])


def test_deadlines_are_ordered_so_teardown_keeps_its_own_time(tmp_path):
    d=orr.MATRIX_DEADLINES;t=orr.MATRIX_TIMING
    assert d['admin_pre']<d['admin_total']<d['admin_diagnostic']
    # a Runner-detected stop at the job limit keeps its FULL failure window before the one-shot session work alarm ...
    assert d['job']+d['diagnostic_window']<=t['work_seconds']
    # ... and a stop caused by the alarm itself also keeps a full window before the runner's total and the hard active deadline
    assert t['work_seconds']+d['diagnostic_window']<=d['diagnostic_total']<=t['active_seconds']-t['report_seconds']
    assert t['input_seconds']+t['active_seconds']+t['report_seconds']<=t['outer_seconds'] and t['outer_seconds']+30<=450 and d['runtime_total']>=rm.LIMITS['matrix_seconds']
    assert d['admin_diagnostic']<=d['diagnostic_window']+d['admin_pre']+30+d['admin_total']      # administrative allowance is not the binding limit beyond the failure window


class _Clock:
    pass


def _runner_for_check(tmp_path):
    reg={**render(),'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()}
    j=Journal(tmp_path/('c%d'%time.monotonic_ns()))
    return Runner(reg,j,lambda:None,source_reader=None,github=FakeGitHub(),url_factory=lambda r,p:None)


def test_teardown_and_diagnostics_have_administrative_time_after_the_pre_teardown_allowance_is_spent(tmp_path):
    r=_runner_for_check(tmp_path);now=time.monotonic()
    # normal phase: the pre-teardown allowance is the protective limit
    r.started=now;r.phase='admin';r.phase_started=now;r.admin_seconds=59.0;r.check()
    r.admin_seconds=61.0
    with pytest.raises(Exception) as caught:r.check()
    assert 'ADMIN_TEARDOWN_RESERVE' in str(caught.value)
    # a failure arrived with the pre-teardown allowance fully consumed: teardown and diagnostics are still permitted inside their reserved time
    r.diagnosing=True;r.diagnostic_started=now;r.phase='teardown';r.phase_started=now;r.admin_seconds=60.0;r.started=now-60.0
    r.check()
    r.admin_seconds=orr.MATRIX_DEADLINES['admin_total']-1;r.check()
    r.admin_seconds=orr.MATRIX_DEADLINES['admin_diagnostic']-1;r.check()
    r.admin_seconds=orr.MATRIX_DEADLINES['admin_diagnostic']+1
    with pytest.raises(Exception) as caught:r.check()
    assert 'DIAGNOSTIC_RESERVE_EXHAUSTED' in str(caught.value)
    # the capture-run defaults were not touched
    d=Runner.__new__(Runner);assert d.deadlines['admin_pre']==210 and d.deadlines['admin_total']==240 and d.deadlines['job']==450
