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
from verification.ingestion_storage.operational_publication import Uncertain,REPO,BRANCH,GitHub,blob_bytes

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
    """A scripted evidence branch. `timeline` is a list of (head, {path: bytes}) where each entry's files are CUMULATIVE (as a real commit's tree is). Each ref read advances along the timeline."""
    def __init__(self,heads,files=None,*,timeline=None):
        self.requests=0;self.ref_calls=0;self.mutation_uncertain=False
        self.timeline=timeline if timeline is not None else [(h,dict(files or {})) for h in heads]
    def call(self,method,path,body=None):
        self.requests+=1
        if '/git/ref/heads/' in path:
            head=self.timeline[min(self.ref_calls,len(self.timeline)-1)][0];self.ref_calls+=1;return {'object':{'sha':head}}
        raise AssertionError(path)
    transient_404=None      # {(relative, head): n} - the first n probes of that file at that head answer 404 although it is there (a replica that has not caught up)
    def probe(self,path):
        self.requests+=1
        relative,head=path.split('/contents/')[1].split('?ref=')
        files=dict(self.timeline)[head]
        key=(relative.split(sp.EVIDENCE_DIRECTORY+'/')[-1],head)
        if self.transient_404 and self.transient_404.get(key,0)>0:
            self.transient_404[key]-=1;return None
        return blob_response(files[relative]) if relative in files else None


def hosted(tmp_path,github):
    urls={r:'postgresql://%s:x@h/db'%r for r in oo.ROLES}
    Path(tmp_path).mkdir(parents=True,exist_ok=True)
    return sp.HostedRunner(urls,Journal(tmp_path/'j'),github,None,{},'192.0.2.1',None,evidence_head='1'*40,manifest_sha256='c'*64,revision='a'*40)


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


MARKER_RELATIVE='screening-authority/registered.json'
CAPTURE_KEY=oo.item(dict(subject=oo.SCOPE,task='DISCOVERY',contract=orr.CONTRACT,revision='c'*64),max_attempts=1,limits=dict(oo.DEFAULT_LIMITS,requests=10,bytes=3000000,rows=60,pages=6))['key']
EXECUTION=dict(revision='a'*40,manifest_sha256='c'*64,capture_key=CAPTURE_KEY,initial_evidence_head='1'*40,authority=orr.PIPELINE_AUTHORITY)
CAPTURE=dict(kind='LISTING_RECEIPT_V1',records=[])
BINDINGS={'k':{'subject':{},'task':'t','contract':'c','revision':'r'}}


def marker_runner(tmp_path,marker,*,heads=('1'*40,'2'*40)):
    timeline=[(heads[0],{})]+[(h,{sp.EVIDENCE_DIRECTORY+'/'+MARKER_RELATIVE:json.dumps(marker).encode()}) for h in heads[1:]]
    runner=hosted(tmp_path,FakeGitHub(None,timeline=timeline))
    runner.capture=CAPTURE;runner.pipeline_sleep=lambda s:None
    return runner


def good_marker(runner=None):
    return dict(execution=EXECUTION,authority=orr.PIPELINE_AUTHORITY+'_SCREEN',bindings_sha256=digest(BINDINGS),capture_sha256=digest(CAPTURE))


def test_the_owner_marker_must_match_the_locally_recomputed_bindings(tmp_path):
    runner=marker_runner(tmp_path/'good',good_marker());runner.await_marker(BINDINGS)
    assert runner.evidence_head=='2'*40
    others=[dict(good_marker(),execution=dict(EXECUTION,**{k:('f'*40 if k in ('revision','initial_evidence_head') else 'f'*64 if k=='manifest_sha256' else 'OTHER')})) for k in EXECUTION]      # a marker that names ANOTHER execution in any single field
    for n,bad in enumerate((dict(good_marker(),bindings_sha256='0'*64),dict(good_marker(),capture_sha256='0'*64),dict(good_marker(),authority='OTHER'),{k:v for k,v in good_marker().items() if k!='execution'},*others)):
        with pytest.raises(Uncertain):marker_runner(tmp_path/('bad%d'%n),bad).await_marker(BINDINGS)


def test_the_hosted_wait_finds_the_marker_even_when_later_heads_were_published_meanwhile(tmp_path):
    # the marker was published at head 2; by the time of the first poll the branch is already at head 3 (cumulative: it still contains the marker)
    runner=marker_runner(tmp_path,good_marker(),heads=('1'*40,'3'*40));runner.await_marker(BINDINGS)
    assert runner.evidence_head=='3'*40


def test_the_wait_for_the_owner_is_bounded_and_a_timeout_is_a_stop(tmp_path,monkeypatch):
    runner=hosted(tmp_path,FakeGitHub(['1'*40]));runner.capture=CAPTURE;runner.pipeline_sleep=lambda s:None
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
    assert b['capture_wait_seconds']+b['screening_wait_seconds']+600<=d['admin_pre']                    # both bounded waits plus the fixed phases fit the administrative allowance
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


def owner_stub(github,*,evidence_head='1'*40):
    runner=object.__new__(orr.Runner)
    runner.github=github;runner.r=dict(evidence_directory=sp.EVIDENCE_DIRECTORY);runner.check=lambda:None;runner.stop_requested=lambda:None;runner.pipeline_sleep=lambda s:None;runner.evidence_head=evidence_head
    return runner


def blob_response(raw,**extra):
    import hashlib
    return dict(content=base64.b64encode(raw).decode(),sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),**extra)


def cumulative(*steps,anchor=True):
    """steps: [(head, {relative: bytes})] - each commit ADDS files; every later head contains all earlier ones, as a real tree does. The branch's README.md anchor is in every commit."""
    out=[];files={'README.md':b'anchor'} if anchor else {}
    for head,added in steps:
        files=dict(files,**{sp.EVIDENCE_DIRECTORY+'/'+k:v for k,v in added.items()});out.append((head,dict(files)))
    return out


def test_the_owner_wait_is_presence_based_and_finds_the_file_when_the_poll_only_sees_a_later_head():
    """Reproduced defect: the restricted job publishes the archive (head A) and, seconds later, the retained marker (head B). A coarse poll may see only B. A change-based wait would take B as
    its baseline and wait for a further head that never comes (the next publication is the owner's own). Presence at the current head finds it."""
    timeline=cumulative(('1'*40,{}),('a'*40,{'capture/source.json':b'{"raw":1}'}),('b'*40,{'capture-retained/retained.json':b'{"m":1}'}))
    github=FakeGitHub(None,timeline=timeline);github.ref_calls=2      # the first poll already finds the branch at head B: head A was never observed
    runner=owner_stub(github)
    head,blob=runner.await_file('capture-retained/retained.json',5)
    assert head=='b'*40 and blob_bytes(blob)==b'{"m":1}'
    assert blob_bytes(runner.evidence_file(head,'capture/source.json'))==b'{"raw":1}'      # the archive written before the marker is still there at head B


def test_the_owner_wait_examines_each_head_a_bounded_number_of_times_and_is_bounded():
    github=FakeGitHub(None,timeline=cumulative(('1'*40,{})));probes=[]
    original=github.probe;github.probe=lambda path:(probes.append(path),original(path))[1]
    runner=owner_stub(github);sleeps=[]
    def sleeper(seconds):
        sleeps.append(seconds)
        if len(sleeps)==6:raise Denied('TEST_STOP_AFTER_SIX_POLLS')
    runner.pipeline_sleep=sleeper
    with pytest.raises(Denied,match='TEST_STOP_AFTER_SIX_POLLS'):runner.await_file('capture-retained/retained.json',3600)
    assert len(probes)==orr.Runner.REPROBES==3 and github.ref_calls==6      # an unchanged head is examined REPROBES times, then only the cheap ref read continues
    zero=FakeGitHub(None,timeline=cumulative(('1'*40,{})))
    with pytest.raises(Denied,match='HOSTED_PUBLICATION_WAIT_EXPIRED'):owner_stub(zero).await_file('capture-retained/retained.json',0)      # a zero-second wait still examines the head once, then stops


def test_a_transient_404_for_a_published_file_at_the_current_head_does_not_hide_it():
    timeline=cumulative(('1'*40,{}),('b'*40,{'capture-retained/retained.json':b'{"m":1}'}))
    github=FakeGitHub(None,timeline=timeline);github.ref_calls=1      # the branch stands at head B throughout
    github.transient_404={('capture-retained/retained.json','b'*40):2}      # the first two probes answer 404 although the file is there
    head,blob=owner_stub(github).await_file('capture-retained/retained.json',3600)
    assert head=='b'*40 and blob_bytes(blob)==b'{"m":1}'
    never=FakeGitHub(None,timeline=timeline);never.ref_calls=1;never.transient_404={('capture-retained/retained.json','b'*40):99}
    r=owner_stub(never);slept=[]
    def stop(seconds):
        slept.append(1)
        if len(slept)==8:raise Denied('TEST_STOP')
    r.pipeline_sleep=stop
    with pytest.raises(Denied,match='TEST_STOP'):r.await_file('capture-retained/retained.json',3600)      # a persistent 404 is bounded: three examinations, then waiting for a NEW head (or the wait bound)


def test_the_owner_wait_refuses_a_file_whose_identity_does_not_match_its_content():
    bad=dict(blob_response(b'{"x":1}'),sha='0'*40)
    github=FakeGitHub(None,timeline=[('1'*40,{})]);github.probe=lambda path:bad
    with pytest.raises(Uncertain,match='PUBLICATION_BLOB_IDENTITY'):owner_stub(github).await_file('capture-retained/retained.json',5)
    github.probe=lambda path:{'type':'file'}      # a response without content is never accepted merely because it says `file`
    with pytest.raises(Uncertain):owner_stub(github).await_file('capture-retained/retained.json',5)


def test_the_owner_requires_a_fresh_evidence_directory_before_it_issues_anything():
    clean=FakeGitHub(None,timeline=cumulative(('1'*40,{})));owner_stub(clean).require_fresh_evidence_directory()
    for leftover in ('capture/source.json','capture-retained/retained.json','completed/final-result.json'):
        dirty=FakeGitHub(None,timeline=cumulative(('1'*40,{leftover:b'{}'})))
        with pytest.raises(Uncertain,match='EVIDENCE_DIRECTORY_NOT_FRESH'):owner_stub(dirty).require_fresh_evidence_directory()
    moved=FakeGitHub(None,timeline=[('9'*40,{'README.md':b'a'})])
    with pytest.raises(Uncertain,match='EVIDENCE_HEAD_MOVED'):owner_stub(moved).require_fresh_evidence_directory()
    unreadable=FakeGitHub(None,timeline=cumulative(('1'*40,{}),anchor=False))      # the branch cannot be read at all (wrong ref/path): a vacuous 404 must not pass the freshness check
    with pytest.raises(Uncertain,match='EVIDENCE_BRANCH_ANCHOR_MISSING'):owner_stub(unreadable).require_fresh_evidence_directory()


def test_probe_accepts_only_the_final_404_line_and_never_an_empty_answer_as_absence():
    import subprocess
    def runner_for(returncode,stdout=b'',stderr=b''):
        return lambda command,**kw:subprocess.CompletedProcess(command,returncode,stdout,stderr)
    for stderr in (b'gh: Not Found (HTTP 404)',b'gh: Not Found (HTTP 404)\n'):
        assert GitHub(lambda *a:None,lambda:None,runner=runner_for(1,stderr=stderr)).probe('p') is None
    for stderr in (b'error contacting proxy: HTTP 404 from upstream cache',b'gh: Bad Gateway (HTTP 502) while reading HTTP 404 fixture',b'HTTP 404 retry later'):
        with pytest.raises(Uncertain):GitHub(lambda *a:None,lambda:None,runner=runner_for(1,stderr=stderr)).probe('p')      # a message that merely mentions 404 is not a 404
    with pytest.raises(Uncertain):GitHub(lambda *a:None,lambda:None,runner=runner_for(0,stdout=b'')).probe('p')      # success with no content is not evidence of absence
    events=[]
    GitHub(lambda e,p=None:events.append((e,p)),lambda:None,runner=runner_for(1,stderr=b'gh: Not Found (HTTP 404)')).probe('p')
    GitHub(lambda e,p=None:events.append((e,p)),lambda:None,runner=runner_for(0,stdout=b'{"content":"","sha":"s"}')).probe('p')
    assert [p['result'] for e,p in events if e=='github_ack']==['ABSENT_HTTP_404','PRESENT']      # the audit records what was answered


def test_probe_treats_http_404_as_absent_and_every_other_failure_as_uncertain():
    import subprocess
    def runner_for(returncode,stdout=b'',stderr=b''):
        return lambda command,**kw:subprocess.CompletedProcess(command,returncode,stdout,stderr)
    events=[]
    gh=GitHub(lambda e,p=None:events.append(e),lambda:None,runner=runner_for(1,stderr=b'gh: Not Found (HTTP 404)'))
    assert gh.probe('repos/x/contents/y?ref=z') is None
    assert GitHub(lambda *a:None,lambda:None,runner=runner_for(0,stdout=b'{"content":"","sha":"s"}')).probe('p')=={'content':'','sha':'s'}
    for rc,err in ((1,b'gh: Internal Server Error (HTTP 500)'),(1,b'connection reset'),(4,b'')):
        with pytest.raises(Uncertain):GitHub(lambda *a:None,lambda:None,runner=runner_for(rc,stderr=err)).probe('p')
    with pytest.raises(Uncertain):GitHub(lambda *a:None,lambda:None,runner=lambda command,**kw:(_ for _ in ()).throw(subprocess.TimeoutExpired(command,5))).probe('p')
    bounded=GitHub(lambda *a:None,lambda:None,runner=runner_for(1,stderr=b'gh: Not Found (HTTP 404)'),bound=1);bounded.probe('p')
    with pytest.raises(ValueError,match='GITHUB_REQUEST_BOUND'):bounded.probe('p')



def test_production_polling_is_the_documented_constants_and_the_rehearsal_override_is_test_only():
    assert orr.PIPELINE_BINDING['poll_seconds']==30 and sp.POLL_SECONDS==15      # production values; the rehearsal overrides them with monkeypatch on its own copy
    source=Path('tests/test_discovery_ingestion_stable_pipeline_pg.py').read_text()
    assert "monkeypatch.setitem(orr.PIPELINE_BINDING,'poll_seconds'" in source      # the override lives only in the disposable rehearsal
    for path in ('verification/ingestion_storage/operational_runner.py','verification/ingestion_storage/stable_pipeline.py'):
        assert 'monkeypatch' not in Path(path).read_text()


def test_the_invalidation_field_of_a_result_is_the_owners_actual_readback_disposition():
    source=Path('verification/ingestion_storage/operational_runner.py').read_text()
    a=source.index('    def pipeline(self):');b=source.index('    def execute(self):')
    body=source[a:b]
    assert "invalidation=self.owner.invalidate_authorities()" in body and "authority_invalidation=invalidation" in body      # no literal status is written into the result
    assert "'ACKNOWLEDGED_READBACK'" not in body.replace("invalidation not in ('ACKNOWLEDGED_READBACK','ALREADY_INVALIDATED_READBACK')","")      # only the two readback-confirmed values are accepted, by name, in one comparison


# ------------------------------------------------------------------ markers must belong to THIS execution and THIS capture: existence is never acceptance
def retained_fixture(**over):
    import hashlib
    source=b'{"raw":"listing"}'
    checkpoint=dict(kind='LISTING_RECEIPT_V1',records=[],durable_archive=dict(sha256=hashlib.sha256(source).hexdigest(),path=sp.EVIDENCE_DIRECTORY+'/capture/source.json'))
    marker=dict(execution=EXECUTION,capture_sha256=digest(checkpoint),kind='LISTING_RECEIPT_V1',archive_sha256=checkpoint['durable_archive']['sha256'])
    marker.update(over);return checkpoint,source,marker


def owner_with_execution():
    runner=owner_stub(FakeGitHub(None,timeline=[('1'*40,{})]))
    runner.r=dict(evidence_directory=sp.EVIDENCE_DIRECTORY,revision='a'*40,manifest_sha256='c'*64,evidence_head='1'*40);runner.capture_key=CAPTURE_KEY;runner.authority=orr.PIPELINE_AUTHORITY
    return runner


def test_the_owner_accepts_a_retained_marker_only_when_it_names_this_execution_and_exactly_this_capture():
    runner=owner_with_execution();checkpoint,source,marker=retained_fixture()
    assert runner.pipeline_execution()==EXECUTION
    assert runner.verify_retained_marker(blob_response(json.dumps(marker).encode()),checkpoint,source)==marker
    for label,bad in (('another revision',dict(marker,execution=dict(EXECUTION,revision='f'*40))),('another manifest',dict(marker,execution=dict(EXECUTION,manifest_sha256='f'*64))),
                      ('another capture root',dict(marker,execution=dict(EXECUTION,capture_key='f'*64))),('another registered head',dict(marker,execution=dict(EXECUTION,initial_evidence_head='f'*40))),
                      ('another authority',dict(marker,execution=dict(EXECUTION,authority='OTHER'))),('no execution',{k:v for k,v in marker.items() if k!='execution'}),
                      ('another capture digest',dict(marker,capture_sha256='0'*64)),('another kind',dict(marker,kind='CAPTURE_BLOCKED_V1')),('another archive digest',dict(marker,archive_sha256='0'*64))):
        with pytest.raises(Uncertain,match='HOSTED_MARKER_BINDING'):runner.verify_retained_marker(blob_response(json.dumps(bad).encode()),checkpoint,source),label
    other_source=b'{"raw":"different bytes"}'      # the archive on the branch must be the bytes the marker and the database checkpoint name
    with pytest.raises(Uncertain,match='HOSTED_MARKER_BINDING'):runner.verify_retained_marker(blob_response(json.dumps(marker).encode()),checkpoint,other_source)
    with pytest.raises(Uncertain,match='HOSTED_MARKER_UNREADABLE'):runner.verify_retained_marker(blob_response(b'not json'),checkpoint,source)
    with pytest.raises(Uncertain,match='PUBLICATION_BLOB_IDENTITY'):runner.verify_retained_marker(dict(blob_response(json.dumps(marker).encode()),sha='0'*40),checkpoint,source)


def test_the_owner_accepts_the_hosted_result_only_for_this_execution_and_capture():
    runner=owner_with_execution();checkpoint,_,_=retained_fixture();runner.capture=checkpoint
    good=dict(status='X',execution=EXECUTION,capture_sha256=digest(checkpoint))
    assert runner.verify_hosted_result(blob_response(json.dumps(good).encode()))[1]==good
    for bad in (dict(good,execution=dict(EXECUTION,revision='f'*40)),dict(good,capture_sha256='0'*64),{k:v for k,v in good.items() if k!='execution'},{k:v for k,v in good.items() if k!='capture_sha256'}):
        with pytest.raises(Uncertain,match='HOSTED_RESULT_BINDING'):runner.verify_hosted_result(blob_response(json.dumps(bad).encode()))
    early=dict(status='STOP_RECONCILE_NO_RETRY',execution=EXECUTION,capture_sha256=None)      # a job that ended before any capture: the execution is still checked, the capture cannot be
    assert runner.verify_hosted_result(blob_response(json.dumps(early).encode()),require_capture=False)[1]==early
    with pytest.raises(Uncertain,match='HOSTED_RESULT_BINDING'):runner.verify_hosted_result(blob_response(json.dumps(dict(early,execution=dict(EXECUTION,authority='OTHER'))).encode()),require_capture=False)


def test_the_owner_does_not_hold_the_ceremony_open_when_the_restricted_job_ended_without_retaining():
    timeline=cumulative(('1'*40,{}),('c'*40,{'completed/final-result.json':json.dumps(dict(status='STOP_RECONCILE_NO_RETRY',execution=EXECUTION,capture_sha256=None)).encode()}))
    github=FakeGitHub(None,timeline=timeline);github.ref_calls=1
    head,relative,blob=owner_stub(github).await_any(('capture-retained/retained.json','completed/final-result.json'),5)
    assert (head,relative)==('c'*40,'completed/final-result.json')      # found at once; not after the retention window
    both=cumulative(('1'*40,{}),('d'*40,{'capture-retained/retained.json':b'{}','completed/final-result.json':b'{}'}))
    g2=FakeGitHub(None,timeline=both);g2.ref_calls=1
    assert owner_stub(g2).await_any(('capture-retained/retained.json','completed/final-result.json'),5)[1]=='capture-retained/retained.json'      # the retained marker takes priority


def test_the_publication_guards_are_unchanged():
    source=Path('verification/ingestion_storage/operational_publication.py').read_text()
    for needle in ("if current['object']['sha']!=expected_head:raise Uncertain('EVIDENCE_HEAD_MOVED_RECONCILE')","force=False","PUBLICATION_PATH","PUBLICATION_BYTES","PUBLICATION_BYTES_READBACK","docs/design/ingestion-operational-execution-"):assert needle in source
    runner=Path('verification/ingestion_storage/operational_runner.py').read_text()
    assert runner.count("expected_head=self.evidence_head")>=2 and "self.require_fresh_evidence_directory()" in runner and "CAPTURE_ARCHIVE_BINDING" in runner and "CAPTURE_NOT_DURABLY_RETAINED" in runner


# ------------------------------------------------------------------ the worst-case GitHub request counts, derived from the constants and the publisher's own request structure
def publish_requests(files):
    return 6+2*files      # GET ref, GET commit, one POST per blob, POST tree, POST commit, PATCH ref, GET ref, one GET per file read back


def owner_worst_case_github_requests():
    b=orr.PIPELINE_BINDING
    polls=lambda wait:-(-wait//b['poll_seconds'])+1      # one ref read per poll plus the boundary poll
    retained_heads=3;result_heads=3      # distinct evidence heads per wait (initial, archive, retained marker / marker, result, owner publication)
    examinations=orr.Runner.REPROBES      # each distinct head is examined at most this many times
    account=1
    fresh=1+1+3                                                 # one ref read, the README anchor, three absent-file probes, before anything is issued
    retained_wait=polls(b['capture_wait_seconds'])+retained_heads*2*examinations      # ref reads plus up to two files (retained marker, early result) per examination of each observed head
    archive_probe=1+1                                           # source.json at the retained head and the retained marker's own re-read
    marker_publication=publish_requests(1)
    result_wait=polls(b['screening_wait_seconds'])+result_heads*examinations
    owner_publication=publish_requests(2)                       # events.jsonl and final-result.json
    failure_reads=1                                             # secret names on the failure path
    return account+fresh+retained_wait+archive_probe+marker_publication+result_wait+owner_publication+failure_reads


def test_the_owner_request_calculation_includes_freshness_probes_publications_and_readbacks_and_fits_the_bound():
    total=owner_worst_case_github_requests()
    assert publish_requests(1)==8 and publish_requests(2)==10      # matches GitHub.publish: 2 + n blobs + tree + commit + patch + ref + n contents
    source=Path('verification/ingestion_storage/operational_publication.py').read_text()
    block=source[source.index('    def publish('):source.index('        return new[')]
    assert block.count("self.call('GET'")==4 and block.count("self.call('POST'")==3 and block.count("self.call('PATCH'")==1      # GET ref, GET commit, GET ref, GET contents (per file); POST blob (per file), tree, commit; PATCH
    print('OWNER_WORST_CASE_GITHUB_REQUESTS',total,'of',orr.PIPELINE_GITHUB_BOUND)
    assert total+10<=orr.PIPELINE_GITHUB_BOUND      # a reserve of at least ten requests


def test_the_hosted_request_calculation_fits_its_bound():
    wait=sp.SCREENING_WAIT_SECONDS;polls=-(-wait//sp.POLL_SECONDS)+1
    total=1+1+publish_requests(1)+publish_requests(1)+polls+3*sp.REPROBES+publish_requests(2)+1      # evidence-head check, anchor, archive, retained marker, owner-marker wait (3 heads x REPROBES examinations), result publication (+its head read)
    assert total+40<=140


def test_the_raw_source_is_below_the_contents_api_size_limit_the_readback_depends_on():
    """The contents API returns the file body inline only up to 1 MB; the archive readback (the accepted publisher's own) and the owner's identity check depend on that. The accepted source worker bounds
    the audit it produces (and therefore the archived raw source) at 512 KiB."""
    assert 'len(raw)>512*1024' in Path('verification/ingestion_storage/operational_source.py').read_text() and 512*1024<1024**2
