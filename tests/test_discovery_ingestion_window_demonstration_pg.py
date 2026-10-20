"""The complete Bolton WINDOW DEMONSTRATION lifecycle against the disposable PG17, in the state production is in: policy v3 then v4 installed by their real ceremonies, the consumed probe and 22 October capture entries
revoked (FOUR exception keys: the cap exhausted), generation 3. Real owner controller (policy-v5 ceremony, then the window ceremony), the HOSTED half as a separate process, restricted logins provisioned by the real
provisioning mode, the real Linux gh against the loopback fixture, and the PRODUCTION checkout reader (no injected fake) against this checkout, the window manifest and the registration's own bindings. The synthetic source is
the observed shape: 22 references over three pages with an explicit total (six of the ten allowed requests). Loopback only; no production resource."""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime,timedelta,timezone
from pathlib import Path

import pytest

from app.ingestion.ledger import digest
from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage import stable_pipeline as sp
from verification.ingestion_storage import window_demonstration as wd
from verification.ingestion_storage import capture_acceptance as cap_mod
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_outcome import session
from verification.ingestion_storage.operational_publication import GitHub
from verification.ingestion_storage.operational_runner import Runner
from tests.storage_gh_fixture import real_gh_store
from tests.test_discovery_ingestion_form_probe_pg import world,run_policy,real_bindings,IDOX,PROBE_NAME
from tests.test_discovery_ingestion_capture_acceptance_pg import run_capture_policy

pytestmark=pytest.mark.parametrize('real_gh_store',['operational'],indirect=True)
ROOT=Path(__file__).resolve().parents[1]
OLDCAP=orr.CAPTURE_AUTHORITY+'_CAPTURE'
CAP=orr.WINDOW_AUTHORITY+'_CAPTURE'
SCR=orr.WINDOW_AUTHORITY+'_SCREEN'
G3=oo.GENERATION3_STOP
FAULTS=['success','source_raises','screening_stops','owner_wait_expires','wrong_revision','wrong_manifest','wrong_executable','baseline_changed_blocks','baseline_digest_differs_blocks']


def run_window_policy(w,name='window-policy'):
    journal=Journal(w.tmp_path/name);holder={}
    github=GitHub(journal.emit,lambda:holder['r'].check(),bound=0)
    r=Runner(dict(w.registration,mode=orr.WINDOW_POLICY_MODE),journal,w.connector,source_reader=lambda row:(_ for _ in ()).throw(AssertionError('no source request')),github=github,url_factory=None,identity=w.role,memory=None);holder['r']=r
    return r.execute(),r


@pytest.mark.parametrize('fault',FAULTS)
def test_window_demonstration_lifecycle(world,fault,monkeypatch):
    w=world;tmp_path=w.tmp_path
    capture_manifest=hashlib.sha256((ROOT/cap_mod.CAPTURE_MANIFEST_PATH).read_bytes()).hexdigest()
    window_manifest=hashlib.sha256((ROOT/wd.WINDOW_MANIFEST_PATH).read_bytes()).hexdigest()
    # ---------------------------------------------------------------- production's state: v3 and v4 installed by their real ceremonies, the consumed entries revoked, then the capture's stop (generation 3)
    policy,_=run_policy(w)
    assert policy['status']=='POLICY_GENERATION2_INSTALLED_CONTROL_RECORD_UNCHANGED'
    ctl=w.control()
    ctl['grants'][PROBE_NAME]=dict(keys=['k'],expires_at=0,source_calls=1,writes=0,login='ingestion_worker_login',bindings={'k':{}})
    ctl['bolton_exceptions'][PROBE_NAME]=dict(authority=PROBE_NAME,transport='REQUESTS_IDOX',grant_binding={},expires_at=0,hard_stop_generation=2)
    w.set_control(ctl)
    v4,_=run_capture_policy(w)
    assert v4['status']=='POLICY_CAPTURE_ALLOWANCE_INSTALLED_CONTROL_RECORD_UNCHANGED'
    ctl=w.control()
    ctl['grants'][OLDCAP]=dict(keys=['k'],expires_at=0,source_calls=1,writes=0,login='ingestion_worker_login',bindings={'k':{}})
    ctl['bolton_exceptions'][OLDCAP]=dict(authority=OLDCAP,transport='REQUESTS_IDOX',grant_binding={},expires_at=0,hard_stop_generation=2)
    ctl['hard_stop_generation']=3      # the consumed capture's fail-safe stop; the reason (and so both stop fields) is unchanged in value
    if fault=='baseline_changed_blocks':ctl['last_hard_stop']='SOMETHING_ELSE'      # the derived last_hard_stop is WRONG: the observation must refuse before anything is installed
    if fault=='baseline_digest_differs_blocks':ctl['hard_stop_generation']=4
    w.set_control(ctl)
    assert len(w.control()['bolton_exceptions'])==4
    functions_v4=w.functions()
    # ---------------------------------------------------------------- ceremony 1: policy v5 (its first step IS the observation that verifies the derived generation-3 state)
    pol,prunner=run_window_policy(w)
    if fault in ('baseline_changed_blocks','baseline_digest_differs_blocks'):
        assert pol['status']=='STOP_RECONCILE_NO_RETRY' and pol['stop_reason']=='OBSERVED_BASELINE_CHANGED' and pol['committed_writes']==0 and w.functions()==functions_v4      # nothing installed
        return
    assert oo.Owner.project_control(w.control(),time.time())['stop_state_sha256']==G3['stop_state_sha256']      # the derived digest equals the digest of the state this ceremony verified
    assert pol['status']=='POLICY_WINDOW_ALLOWANCE_INSTALLED_CONTROL_RECORD_UNCHANGED' and pol['cleanup']=='CLOSED' and pol['inventory_verified'] is True and pol['github_requests']==0 and pol['transient_owner_capability']=='ABSENT_READ_BACK'
    changed=sorted(k for k in functions_v4 if functions_v4[k]!=w.functions().get(k));assert changed==['ingestion_bolton_allowed','ingestion_register_bolton_exception']
    assert pol['control_sha256_before']==pol['control_sha256_after']==digest(w.control())
    assert prunner.owner.commands<=orr.WINDOW_POLICY_OWNER_LIMITS['commands'][0] and prunner.owner.connections<=orr.WINDOW_POLICY_OWNER_LIMITS['connections'][0]
    # ---------------------------------------------------------------- ceremony 2: the window demonstration
    registration=dict(w.registration,mode=orr.WINDOW_MODE,manifest_sha256=window_manifest,evidence_directory=orr.WINDOW_EVIDENCE_DIRECTORY,control_sha256=pol['control_sha256_after'],
                      expires_at=(datetime.now(timezone.utc)+timedelta(minutes=100)).isoformat())
    if fault=='wrong_revision':registration['revision']='e'*40
    if fault=='wrong_manifest':registration['manifest_sha256']=capture_manifest      # the OTHER mode's manifest was registered; the reader hashes THIS mode's
    if fault=='wrong_executable':registration['controller_sha256']='b'*64
    valid_until=min(r[3] for r in w.standing[0]).astimezone(timezone.utc).isoformat()
    monkeypatch.setitem(orr.WINDOW_BINDING,'valid_until',valid_until);monkeypatch.setitem(orr.WINDOW_BINDING,'poll_seconds',1.0)
    monkeypatch.setitem(orr.WINDOW_BINDING,'capture_wait_seconds',3 if fault=='owner_wait_expires' else 120);monkeypatch.setitem(orr.WINDOW_BINDING,'screening_wait_seconds',120)
    ctl_before=w.control()
    owner_journal=Journal(tmp_path/'owner');holder={}
    github=GitHub(owner_journal.emit,lambda:holder['r'].check(),runner=w.cli,bound=orr.PIPELINE_GITHUB_BOUND)
    orunner=Runner(registration,owner_journal,w.connector,source_reader=lambda row:(_ for _ in ()).throw(AssertionError('owner never reads a source')),github=github,url_factory=w.uri,identity=w.role,memory=None);holder['r']=orunner
    orunner.pipeline_sleep=lambda s:time.sleep(min(s,1.0))
    stop_codes=[];original_failed=orunner.failed
    def failed_with_code(exc):
        text=exc.args[0] if getattr(exc,'args',None) and isinstance(exc.args[0],str) else ''
        stop_codes.append(dict(exception=type(exc).__name__,code=text if re.fullmatch(r'[A-Z][A-Z0-9_]{2,79}',text) else 'NOT_A_FIXED_CODE'))
        return original_failed(exc)
    orunner.failed=failed_with_code
    hosted_dir=tmp_path/'hosted-out';spawned=[]
    plan=dict(disposable='LOOPBACK_ONLY',fault=fault,dbname=w.info['dbname'],gh=w.metadata.gh,gh_env=w.metadata.fixture_env(),evidence_head=registration['evidence_head'],manifest_sha256=registration['manifest_sha256'],
              controller_sha256=registration['controller_sha256'],revision=registration['revision'],output=str(hosted_dir))
    plan_path=tmp_path/'plan.json';plan_path.write_text(json.dumps(plan))
    def start_hosted():
        env=dict(os.environ,INGESTION_ACCEPTANCE_DISPOSABLE='PG17_ONLY',REHEARSAL_URLS=json.dumps(w.urls),PYTHONPATH=str(Path.cwd()),PYTHONDONTWRITEBYTECODE='1')
        subprocess.run(['sh','-c','"$0" -B -m tests.window_demonstration_rehearsal "$1" >"$2" 2>&1 &',sys.executable,str(plan_path),str(tmp_path/'hosted.log')],env=env,check=True,timeout=20)
        spawned.append(True)
    original_register=orunner.owner.register
    def register(items_,authority,**kw):
        out=original_register(items_,authority,**kw)
        if authority.endswith('_CAPTURE') and fault!='owner_wait_expires':start_hosted()      # the restricted job is dispatched only after the owner registered the capture allowance
        return out
    orunner.owner.register=register
    lines=[]
    result=session(owner_journal,registration['expires_at'],lambda:'hidden fixture input',lambda raw_,started:orunner,output=lambda line,**kw:lines.append(line),timing=orr.PIPELINE_TIMING)
    if spawned:
        end=time.monotonic()+90
        while not (hosted_dir/'rehearsal-done').exists() and time.monotonic()<end:time.sleep(0.2)
    summary=dict(fault=fault,status=result.get('status'),cleanup=result.get('cleanup'),invalidation=result.get('authority_invalidation'),stop_codes=stop_codes,phase=result.get('operation_phase'),
                 commands=orunner.owner.commands,connections=orunner.owner.connections,github_requests=orunner.github.requests)
    print('WINDOW_OWNER_RESULT',json.dumps(summary,default=str,sort_keys=True))
    hosted_log=(tmp_path/'hosted.log').read_text() if (tmp_path/'hosted.log').exists() else ''
    hosted_final=json.loads((hosted_dir/'final-result.json').read_bytes()) if (hosted_dir/'final-result.json').exists() else None
    source_calls=int((hosted_dir/'rehearsal-source-calls').read_text()) if (hosted_dir/'rehearsal-source-calls').exists() else 0
    ctl_after=w.control()
    text=owner_journal.file.read_text()+json.dumps(result)+((hosted_dir/'events.jsonl').read_text() if (hosted_dir/'events.jsonl').exists() else '')
    assert 'postgresql://' not in text
    # ---------------------------------------------------------------- invariants on EVERY path
    assert ctl_after['global_stop']==ctl_before['global_stop']
    assert (w.roles_state(),w.memberships(),w.role_configs())==w.standing      # standing credentials: no password, membership or role-setting change
    for name in ('HISTORICAL_0','HISTORICAL_1',PROBE_NAME,OLDCAP):      # every historical grant and exception preserved byte-for-byte
        assert ctl_after['grants'][name]==ctl_before['grants'][name] and ctl_after['bolton_exceptions'][name]==ctl_before['bolton_exceptions'][name]
    ours=[a for a in ctl_after['grants'] if a.startswith(orr.WINDOW_AUTHORITY)]
    for a in ours:assert ctl_after['grants'][a]['expires_at']==0 and ctl_after['bolton_exceptions'][a]['expires_at']==0      # ended by invalidation, never merely by time
    assert set(ours)<={CAP,SCR} and CAP in ours and ctl_after['bolton_exceptions'][CAP]['hard_stop_generation']==3
    caps=orr.PIPELINE_OWNER_LIMITS;ended_normally=result['status'].startswith('STABLE_PIPELINE_AUTHORITY_COMPLETED')
    assert orunner.owner.opened==orunner.owner.closed and orunner.owner.connections<=(caps['connections'][0] if ended_normally else caps['connections'][1]) and orunner.owner.commands<=(caps['commands'][1] if ended_normally else caps['commands'][2]),summary
    assert result['application_writes']==0 and result['stage4']=='OPEN' and result['pipeline_retry']=='HELD'
    if hosted_final is not None and (hosted_dir/'rehearsal-done').exists():      # publication-before-closure, in the real publication path
        assert int((hosted_dir/'rehearsal-memory-closed-after-gh-calls').read_text())==int((hosted_dir/'rehearsal-gh-calls-total').read_text())
        assert hosted_final['closure_stage']=='FINAL_AFTER_PUBLICATION' and hosted_final['publication']=='PUBLISHED' and hosted_final['cleanup']=='CLOSED' and hosted_final['published_cleanup']=='PENDING_MEMORY_SCOPE_CLOSURE'
        head_now=json.loads(w.metadata.cli(['gh','api','--method','GET',sp.REPO+'/git/ref/heads/'+sp.BRANCH]).stdout)['object']['sha']
        blob_now=json.loads(w.metadata.cli(['gh','api','--method','GET',sp.REPO+'/contents/'+orr.WINDOW_EVIDENCE_DIRECTORY+'/completed/final-result.json?ref='+head_now]).stdout)
        published=json.loads(base64.b64decode(blob_now['content']))
        assert published['closure_stage']=='PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE' and published['execution']==hosted_final['execution'] and published['execution']['authority']==orr.WINDOW_AUTHORITY
    assert result['authority_invalidation'] in ('ACKNOWLEDGED_READBACK','ALREADY_INVALIDATED_READBACK'),summary
    if fault=='owner_wait_expires':
        assert result['status']=='STOP_RECONCILE_NO_RETRY' and not spawned and source_calls==0 and list(ours)==[CAP] and ctl_after['hard_stop_generation']==3
        return
    assert spawned and hosted_final is not None,hosted_log[-1500:]
    if fault in ('wrong_revision','wrong_manifest','wrong_executable'):      # the PRODUCTION reader found the checkout is not the registered one: ZERO source requests, a fixed reason, authority ended, no stop raised
        assert source_calls==0 and hosted_final['status']=='STOP_RECONCILE_NO_RETRY' and hosted_final['stop_reason']=='CHECKOUT_BINDING_MISMATCH' and hosted_final['source_observations_attempted']==0
        assert result['status']=='STOP_RECONCILE_NO_RETRY' and stop_codes[0]['code']=='HOSTED_ENDED_BEFORE_RETENTION' and list(ours)==[CAP]
        assert ctl_after['hard_stop_generation']==3 and ctl_after['manual_stop']==IDOX
        return
    if fault=='source_raises':      # one source request, no replay; an unaccountable outcome raises the ACCEPTED fail-safe stop (generation 4, which policy v5 does not recognise)
        assert source_calls==1 and hosted_final['status']=='STOP_RECONCILE_NO_RETRY' and result['status']=='STOP_RECONCILE_NO_RETRY' and list(ours)==[CAP] and SCR not in ctl_after['grants']
        assert ctl_after['hard_stop_generation']==4 and ctl_after['manual_stop']==IDOX and ctl_after['last_hard_stop']==IDOX
        return
    assert source_calls==1 and sorted(ours)==sorted([CAP,SCR]) and len(ctl_after['bolton_exceptions'])==6      # both new names registered through the named exemption only, with FOUR keys already present
    assert ctl_after['hard_stop_generation']==3 and ctl_after['manual_stop']==IDOX      # a normal run raises no stop
    if fault=='screening_stops':
        assert hosted_final['status']=='STOP_RECONCILE_NO_RETRY' and result['status']=='STABLE_PIPELINE_ENDED_INCOMPLETE_AUTHORITY_INVALIDATED' and result['screening']=='INCOMPLETE' and result['cleanup']=='CLOSED'
        assert any(state!='COMPLETE' for _,state in w.items())      # the retained capture is preserved; screening is reported as incomplete, not as success
        return
    assert result['status']=='STABLE_PIPELINE_AUTHORITY_COMPLETED_AUTHORITY_INVALIDATED' and result['cleanup']=='CLOSED' and result['screening']=='COMPLETE' and result['credentials'].startswith('UNCHANGED')
    assert hosted_final['status'] in ('STABLE_PIPELINE_CAPTURE_SCREENING_COMPLETED_RESTRICTED_RUNTIME_ONLY','PARTIAL_PROPOSAL_COVERAGE') and hosted_final['cleanup']=='CLOSED'
    assert hosted_final['checkout_binding']['manifest_sha256']==window_manifest and hosted_final['checkout_binding']['tracked_files_modified'] is False      # what the production reader actually verified
    assert result['hosted']['cleanup']=='PENDING_MEMORY_SCOPE_CLOSURE' and hosted_final['rows']==22 and hosted_final['batches']==5 and hosted_final['credential_changes']==0 and hosted_final['application_writes']==0
    assert result['readback_after']['findings']==[] and result['readback_before']['findings']==[]
    assert all(state=='COMPLETE' for _,state in w.items() if state)
    root=oo.item(dict(subject=oo.WINDOW_SCOPE,task='DISCOVERY',contract=orr.CONTRACT,revision=window_manifest),max_attempts=1,limits=dict(oo.DEFAULT_LIMITS,requests=10,bytes=3000000,rows=60,pages=6))
    assert any(key==root['key'] for key,_ in w.items())      # the retained root is the WINDOW scope's, not the day's
