"""Offline properties of the stable-credential pipeline: the pure owner readback evaluation, the hosted admission, the owner/hosted agreement on keys and bindings, the marker handshake and the
static properties of the hosted workflow. No network, no database."""
import base64,json,re
from datetime import datetime,timezone
from pathlib import Path
import pytest
from app.ingestion.ledger import digest,Denied
from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage import stable_pipeline as sp
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_publication import Uncertain,REPO,BRANCH

VALID='2027-01-17T16:14:12+00:00'
EXPECTED=dict(identity='postgres',hard_stop_generation=1,valid_until=VALID)
UNTIL=datetime.fromisoformat(VALID)
WF=Path('.github/workflows/stage4-stable-pipeline-once.yml')


def good(**over):
    obs=dict(identity=('postgres','postgres',False,True,True,True,False,False,False,False,True,True),
             control=dict(global_stop=oo.STOP,manual_stop='STORAGE_TEST_STOP',hard_stop_generation=1,unexpired_grants=0),
             roles=[('ingestion_effect_login',True,True,UNTIL,1,False,False,False,False,False),('ingestion_storage_login',False,False,None,-1,False,False,False,False,False),
                    ('ingestion_worker_login',True,True,UNTIL,1,False,False,False,False,False)],
             memberships=[('ingestion_effect_login','ingestion_effect_broker'),('ingestion_worker_login','ingestion_worker')],
             role_settings={r:['statement_timeout=10s','lock_timeout=3s','idle_in_transaction_session_timeout=20s'] for r in oo.ROLES},sessions=[],inventory_recognised=True)
    obs.update(over);return obs


def test_the_accepted_standing_state_has_no_findings():
    assert oo.evaluate_pipeline_readback(good(),EXPECTED)==([],[])


@pytest.mark.parametrize('field,value,finding',[
    ('control',dict(global_stop=oo.STOP,manual_stop='STORAGE_TEST_STOP',hard_stop_generation=1,unexpired_grants=1),'UNEXPIRED_GRANT_PRESENT'),
    ('control',dict(global_stop=None,manual_stop='STORAGE_TEST_STOP',hard_stop_generation=1,unexpired_grants=0),'GLOBAL_STOP_CHANGED'),
    ('control',dict(global_stop=oo.STOP,manual_stop=None,hard_stop_generation=1,unexpired_grants=0),'MANUAL_STOP_CHANGED'),
    ('control',dict(global_stop=oo.STOP,manual_stop='STORAGE_TEST_STOP',hard_stop_generation=2,unexpired_grants=0),'HARD_STOP_GENERATION_CHANGED'),
    ('control',None,'CONTROL_STATE_UNAVAILABLE'),
    ('memberships',[('ingestion_worker_login','ingestion_worker')],'MEMBERSHIPS_CHANGED'),
    ('memberships',[('ingestion_effect_login','ingestion_effect_broker'),('ingestion_worker_login','ingestion_worker'),('ingestion_worker_login','ingestion_storage_owner')],'MEMBERSHIPS_CHANGED'),
    ('role_settings',{r:['statement_timeout=10s'] for r in oo.ROLES},'ROLE_SETTINGS_CHANGED'),
    ('inventory_recognised',False,'INSTALLED_FUNCTIONS_NOT_RECOGNISED'),
    ('sessions',None,'SESSIONS_NOT_OBSERVED'),
    ('identity',('postgres','postgres',False,True,True,True,True,False,False,False,True,True),'TEMPORARY_OWNER_OR_RELEASER_CAPABILITY_PRESENT'),
    ('identity',('other','other',False,True,True,True,False,False,False,False,True,True),'MIGRATION_IDENTITY'),
    ('identity',('postgres','postgres',False,True,True,True,False,False,False,False,False,True),'SESSION_VISIBILITY_NOT_PROVEN')])
def test_every_mismatch_or_uncertainty_is_a_fixed_finding_that_blocks_issuance(field,value,finding):
    findings,_=oo.evaluate_pipeline_readback(good(**{field:value}),EXPECTED)
    assert finding in findings


@pytest.mark.parametrize('mutate,finding',[
    (lambda r:(r[0][0],False)+r[0][2:],'LOGIN_NOT_ENABLED'),
    (lambda r:r[0][:2]+(False,)+r[0][3:],'PASSWORD_NOT_PRESENT'),
    (lambda r:r[0][:3]+(datetime.fromisoformat('2027-01-18T00:00:00+00:00'),)+r[0][4:],'VALID_UNTIL_MISMATCH'),
    (lambda r:r[0][:3]+(None,)+r[0][4:],'VALID_UNTIL_MISMATCH'),
    (lambda r:r[0][:4]+(5,)+r[0][5:],'CONNECTION_LIMIT_CHANGED'),
    (lambda r:r[0][:5]+(True,)+r[0][6:],'PRIVILEGE_FLAG_CHANGED')])
def test_a_restricted_login_that_differs_from_the_provisioned_state_blocks(mutate,finding):
    roles=good()['roles'];roles[0]=mutate(roles)
    assert finding in oo.evaluate_pipeline_readback(good(roles=roles),EXPECTED)[0]


def test_the_accepted_storage_login_must_stay_disabled_without_a_password():
    roles=good()['roles'];roles[1]=('ingestion_storage_login',True,True,None,-1,False,False,False,False,False)
    assert 'ACCEPTED_STORAGE_ACCESS_CHANGED' in oo.evaluate_pipeline_readback(good(roles=roles),EXPECTED)[0]
    assert 'RESTRICTED_OR_STORAGE_LOGIN_MISSING' in oo.evaluate_pipeline_readback(good(roles=roles[:2]),EXPECTED)[0]


def test_an_idle_pooled_backend_is_reported_accurately_and_is_not_a_leak_or_a_block():
    idle=[(101,'ingestion_worker_login','idle',datetime.now(timezone.utc),'client backend')]
    findings,notes=oo.evaluate_pipeline_readback(good(sessions=idle),EXPECTED)
    assert findings==[] and notes==['IDLE_POOLED_BACKENDS_OBSERVED_NOT_CLASSIFIED_AS_A_LEAK']


@pytest.mark.parametrize('row,finding',[
    ((101,'ingestion_worker_login','active',datetime.now(timezone.utc),'client backend'),'ROLE_SESSION_NOT_IDLE'),
    ((101,'ingestion_effect_login','idle in transaction',datetime.now(timezone.utc),'client backend'),'ROLE_SESSION_NOT_IDLE'),
    ((101,None,None,None,'client backend'),'UNATTRIBUTABLE_CLIENT_BACKEND'),
    ((101,'someone_else','idle',datetime.now(timezone.utc),'client backend'),'UNATTRIBUTABLE_CLIENT_BACKEND')])
def test_a_non_idle_or_unattributable_session_blocks(row,finding):
    findings,_=oo.evaluate_pipeline_readback(good(sessions=[row]),EXPECTED)
    assert finding in findings


def test_the_readback_statements_are_fixed_read_only_and_never_select_secrets_or_query_text():
    for sql_text in (oo.PIPELINE_ROLES_SQL,oo.PIPELINE_IDENTITY_SQL,oo.PIPELINE_SESSIONS_SQL):
        lowered=sql_text.lower()
        assert 'rolpassword is not null' in lowered or 'rolpassword' not in lowered      # presence only, never the verifier
        assert 'query' not in lowered.replace('backend_type','') and 'insert' not in lowered and 'update' not in lowered and 'grant ' not in lowered
    assert re.search(r'a\.rolpassword\s+IS NOT NULL',oo.PIPELINE_ROLES_SQL) and 'pg_authid' in oo.PIPELINE_ROLES_SQL
    source=Path(oo.__file__).read_text()
    block=source[source.index('def pipeline_readback'):source.index('def read_items')]
    code=block.split('"""')[2]      # after the docstring
    assert "'BEGIN READ ONLY'" in code and 'GRANT' not in code and 'effect=True' not in code      # read-only transaction, no effect statements
    assert code.count('self.q(c,')<=oo.Owner.PIPELINE_MAX_STATEMENTS


# --------------------------------------------------------------------------- hosted admission
def env(**over):
    base=dict(PIPELINE_REVIEWED_SHA='a'*40,PIPELINE_EVIDENCE_HEAD='b'*40,GITHUB_SHA='a'*40,GITHUB_WORKFLOW_SHA='a'*40,GITHUB_REF='refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',
              GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',PIPELINE_AUTHORITY=sp.HOSTED_AUTHORITY,GH_TOKEN='t')
    base.update(over);return base


def test_hosted_admission_is_single_use_pinned_and_credential_separated():
    assert sp.admitted(env())
    for bad in (dict(GITHUB_RUN_NUMBER='2'),dict(GITHUB_RUN_ATTEMPT='2'),dict(GITHUB_REF='refs/heads/x'),dict(GITHUB_SHA='c'*40),dict(PIPELINE_AUTHORITY='NOT_AUTHORISED'),dict(PIPELINE_EVIDENCE_HEAD='zz'),
                dict(GH_TOKEN=''),dict(DATABASE_URL='postgresql://x'),dict(PGPASSWORD='x'),dict(INGESTION_STORAGE_DATABASE_URL='x'),dict(RUNNER_ENVIRONMENT='self-hosted')):
        assert not sp.admitted(env(**bad)),bad


# --------------------------------------------------------------------------- owner/hosted agreement
class FakeGitHub:
    def __init__(self,heads,files=None):
        self.heads=list(heads);self.files=files or {};self.requests=0;self.ref_calls=0
    def call(self,method,path,body=None):
        self.requests+=1
        if '/git/ref/heads/' in path:
            head=self.heads[min(self.ref_calls,len(self.heads)-1)];self.ref_calls+=1;return {'object':{'sha':head}}
        if '/contents/' in path:return {'type':'file','content':base64.b64encode(self.files[path.split('/contents/')[1].split('?')[0]]).decode()}
        raise AssertionError(path)


def hosted(tmp_path,github):
    urls={r:'postgresql://%s:x@h/db'%r for r in oo.ROLES}
    Path(tmp_path).mkdir(parents=True,exist_ok=True)
    return sp.HostedRunner(urls,Journal(tmp_path/'j'),github,None,{},'192.0.2.1',None,evidence_head='1'*40,manifest_sha256='c'*64)


def test_hosted_and_owner_compute_the_same_capture_key_and_bindings(tmp_path):
    runner=hosted(tmp_path,FakeGitHub(['1'*40]))
    identity=dict(subject=oo.SCOPE,task='DISCOVERY',contract=orr.CONTRACT,revision='c'*64)
    root=oo.item(identity,max_attempts=1,limits=dict(oo.DEFAULT_LIMITS,requests=10,bytes=3000000,rows=60,pages=6))
    assert runner.capture_key==root['key'] and runner.capture_bindings==sp.bindings_for([root])


def test_the_hosted_job_cannot_register_any_authority(tmp_path):
    runner=hosted(tmp_path,FakeGitHub(['1'*40]))
    with pytest.raises(Denied):runner.owner.register([],runner.authority+'_CAPTURE',capture_key='k',source_calls=1)
    with pytest.raises(Denied):runner.owner.register([],runner.authority+'_SCREEN',capture_key='k',source_calls=1)
    assert runner.owner.authorities==[]


MARKER_PATH=sp.EVIDENCE_DIRECTORY+'/screening-authority/registered.json'
CAPTURE=dict(kind='LISTING_RECEIPT_V1',records=[])
BINDINGS={'k':{'subject':{},'task':'t','contract':'c','revision':'r'}}


def marker_runner(tmp_path,marker):
    runner=hosted(tmp_path,FakeGitHub(['1'*40,'2'*40],{MARKER_PATH:json.dumps(marker).encode()}))
    runner.capture=CAPTURE;runner.pipeline_sleep=lambda s:None
    return runner


def test_the_owner_marker_must_match_the_locally_recomputed_bindings(tmp_path):
    good_marker=dict(authority=orr.PIPELINE_AUTHORITY+'_SCREEN',bindings_sha256=digest(BINDINGS),capture_sha256=digest(CAPTURE))
    runner=marker_runner(tmp_path/'good',good_marker);runner.await_marker(BINDINGS)
    assert runner.evidence_head=='2'*40
    for n,bad in enumerate((dict(good_marker,bindings_sha256='0'*64),dict(good_marker,capture_sha256='0'*64),dict(good_marker,authority='OTHER'))):
        with pytest.raises(Uncertain):marker_runner(tmp_path/('bad%d'%n),bad).await_marker(BINDINGS)


def test_the_wait_for_the_owner_is_bounded_and_a_timeout_is_a_stop(tmp_path,monkeypatch):
    runner=hosted(tmp_path,FakeGitHub(['1'*40]));runner.capture=dict(kind='LISTING_RECEIPT_V1',records=[]);runner.pipeline_sleep=lambda s:None
    monkeypatch.setattr(sp,'SCREENING_WAIT_SECONDS',0)
    with pytest.raises(Denied,match='OWNER_SCREENING_AUTHORITY_WAIT_EXPIRED'):runner.await_marker({})


# --------------------------------------------------------------------------- the hosted workflow (static)
def test_the_workflow_references_only_the_two_restricted_secrets_and_a_scoped_token():
    t=WF.read_text()
    assert sorted(set(re.findall(r'secrets\.([A-Z_]+)',t)))==['INGESTION_EFFECT_DATABASE_URL','INGESTION_WORKER_DATABASE_URL']
    assert 'DATABASE_URL: ${{' in t and 'secrets.DATABASE_URL' not in t
    assert re.search(r'^permissions:\n  contents: write\n',t,re.M) and t.count('permissions:')==1      # the one disclosed write capability
    assert 'github.token' in t and t.count('github.token')==1


def test_the_workflow_is_manual_single_use_and_pinned_to_the_reviewed_revision():
    t=WF.read_text()
    assert 'workflow_dispatch' in t and 'pull_request' not in t and 'schedule' not in t and 'push:' not in t
    assert 'GITHUB_RUN_NUMBER" == 1 && "$GITHUB_RUN_ATTEMPT" == 1' in t and 'refs/heads/master' in t and '"$PIN" == "$WF" && "$PIN" == "$GITHUB_SHA"' in t
    assert 'AUTHORISE_INGESTION_STABLE_PIPELINE_HOSTED_ONCE_20261020' in t and 'environment: stage4-production-canary' in t and 'persist-credentials: false' in t
    assert set(re.findall(r'uses: ([\w./-]+@[\w.]+)',t))=={'actions/checkout@v4','actions/upload-artifact@v4'}


def test_actual_memory_is_kernel_enforced_and_an_address_space_limit_is_not_claimed_to_be_it():
    t=WF.read_text()
    assert 'hosted_memory_scope.sh' in t and 'sudo -E bash verification/ingestion_storage/hosted_memory_scope.sh' in t and t.count('sudo')==1
    assert 'ulimit -v' not in t and 'ulimit -c 0; ulimit -n 128; ulimit -f 4096' in t
    assert 'timeout --kill-after=15s 2100s' in t and 'timeout-minutes: 40' in t
    script=Path('verification/ingestion_storage/hosted_memory_scope.sh').read_text()
    for needle in ('1610612736','memory.swap.max','memory.oom.group','propertyaigent-operational-once.scope','mapfile -t members','exec setpriv','ACTUAL_MEMORY_ENFORCEMENT_UNAVAILABLE'):assert needle in script
    assert '\r' not in script


def test_secrets_reach_the_job_only_through_the_environment_never_a_file_or_an_argument():
    t=WF.read_text()
    assert 'GH_TOKEN="$GH_TOKEN"' in t
    for line in t.splitlines():
        if 'secrets.' in line:assert re.match(r'\s+INGESTION_(WORKER|EFFECT)_DATABASE_URL: \$\{\{ secrets\.',line)
    assert 'echo' not in ' '.join(l for l in t.splitlines() if 'DATABASE_URL' in l or 'GH_TOKEN' in l)


def test_pipeline_deadline_ordering_invariants_hold_for_the_actual_constants():
    d=orr.PIPELINE_DEADLINES;t=orr.PIPELINE_TIMING;b=orr.PIPELINE_BINDING
    assert d['job']+d['diagnostic_window']<=t['work_seconds']                                         # a stop detected at the job limit still has its full failure window before the one-shot work alarm
    assert t['work_seconds']+d['diagnostic_window']<=d['diagnostic_total']<=t['active_seconds']-t['report_seconds']
    assert d['admin_pre']<d['admin_total']<d['admin_diagnostic']<=d['diagnostic_total']
    assert t['active_seconds']<t['outer_seconds']<orr.PIPELINE_BACKSTOP_SECONDS
    assert b['capture_wait_seconds']+b['retention_wait_seconds']+b['screening_wait_seconds']+600<=d['admin_pre']                    # both bounded waits plus the fixed phases fit the administrative allowance
    assert b['grant_minutes']*60<d['job'] and b['screening_grant_minutes']<b['grant_minutes']          # the authority always ends before the controller's own limit
    assert 'RuntimeMaxSec=%ds'%orr.PIPELINE_BACKSTOP_SECONDS in Path('docs/design/ingestion-stable-pipeline-20261020/owner-run.sh').read_text()
    assert sp.HOSTED_DEADLINES['job']+240<=2100 and 40*60>2100                                          # the hosted hard kill (2,100 s) lies inside the 40-minute job limit and above the hosted job deadline


def test_the_retained_marker_is_published_once_after_the_checkpoint_and_carries_no_authority(tmp_path):
    published=[]
    class Pub(FakeGitHub):
        def publish(self,files,*,directory,expected_head):
            published.append((directory,sorted(files)));return '3'*40
    runner=hosted(tmp_path,Pub(['1'*40]));runner.capture=dict(kind='LISTING_RECEIPT_V1',records=[])
    runner.publish_retained();runner.publish_retained()
    assert published==[(sp.EVIDENCE_DIRECTORY+'/capture-retained',['retained.json'])] and runner.evidence_head=='3'*40
    empty=hosted(tmp_path/'none',Pub(['1'*40]));empty.publish_retained()
    assert len(published)==1      # nothing is published without a capture
