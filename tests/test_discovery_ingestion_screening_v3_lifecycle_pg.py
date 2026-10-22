"""The complete screening-v3 RETAINED-WINDOW lifecycle against the disposable PG17, in the state production is in: policy v3, v4 and v5 installed by their real ceremonies, the consumed probe, capture and window entries revoked
(SIX exception keys, the cap exhausted), generation 3, the 30 retained rows present. Real owner controller (the new installation mode, then the new screening mode), the HOSTED half as a separate process with the standing
restricted credentials provisioned by the real provisioning mode, real accounting (DatabaseBudget slots, ControllerLedger, SQLLedger, the derived v3 worker function), the real Linux gh against the loopback fixture, the PRODUCTION
checkout reader against this checkout, and a stateful memory stand-in that drives the real publication-then-closure ordering. Loopback only; no production resource.

Simulation boundaries (explicit): the restricted pooler host is translated to the disposable server (no TLS to a provider); the GitHub evidence branch is the loopback fixture; the cgroup-v2 memory scope is a stateful
stand-in that drives the real guard (the real scope is proved by tests/hosted_scope_publication_proof.py in the hosted-memory-proof workflow); protected-environment approval and queueing are represented only by the order in which the
test starts the hosted process; there is no source reader, so any source call fails the run."""
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

from app.ingestion import listing_screening as ls
from app.ingestion.ledger import digest
from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage import retained_world as rw
from verification.ingestion_storage import stable_pipeline as sp
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_outcome import session
from verification.ingestion_storage.operational_publication import GitHub
from verification.ingestion_storage.operational_runner import Runner
from tests.storage_gh_fixture import real_gh_store
from tests.test_discovery_ingestion_form_probe_pg import world,run_policy,IDOX,PROBE_NAME
from tests.test_discovery_ingestion_capture_acceptance_pg import run_capture_policy
from tests.test_discovery_ingestion_window_demonstration_pg import run_window_policy,OwnerScope,OLDCAP,CAP as WINDOW_CAP,SCR as WINDOW_SCR

pytestmark=pytest.mark.parametrize('real_gh_store',['operational'],indirect=True)
ROOT=Path(__file__).resolve().parents[1]
G3=oo.GENERATION3_STOP
NAME=orr.SV3_AUTHORITY+'_SCREEN'
V3=ls.ScreeningRule(ls.RULE_V3,unit_threshold=10,link_related=False)
FAULTS=['success','hosted_fails','hosted_publication_fails','authority_expires','owner_publication_fails','ready_wait_expires','altered_row','missing_row','wrong_revision','wrong_controller']
EARLIER=('HISTORICAL_0','HISTORICAL_1',PROBE_NAME,OLDCAP,WINDOW_CAP,WINDOW_SCR)


def run_sv3_policy(w,name='sv3-policy'):
    journal=Journal(w.tmp_path/name);holder={}
    github=GitHub(journal.emit,lambda:holder['r'].check(),bound=0)
    r=Runner(dict(w.registration,mode=orr.SV3_POLICY_MODE),journal,w.connector,source_reader=lambda row:(_ for _ in ()).throw(AssertionError('no source request')),github=github,url_factory=None,identity=w.role,memory=None);holder['r']=r
    return r.execute(),r


def seed_retained_world(w):
    """The 30 retained rows exactly as the 20 October run left them: the capture, 24 earlier assessments and 5 batches, all COMPLETE."""
    _,receipt=rw.retained()
    root,children,plans,batches,_=rw.identities(receipt)
    v1=ls.ScreeningRule(ls.RULE_V1)
    def done(row,**fields):
        return dict(row,state='COMPLETE',phase='FINISHED',next_action='NONE',attempt_count=1,fence=1,**fields)
    rows=[done(root,checkpoint=receipt,outcome=dict(outcome='ENUMERATED_METADATA_RETAINED',children=[c['key'] for c in children],source_sha256=receipt['source_sha256']))]
    for child,record in zip(children,receipt['records']):
        result=dict(v1.screen(record),source_url=record['source_url'],source_record_id=record['source_record_id'],source_sha256=receipt['source_sha256'],proposal=record['fields']['proposal'],application_type=record['fields']['application_type'])
        rows.append(done(child,checkpoint=result,outcome=dict(outcome=result['disposition'],retained=True)))
    for batch in batches:
        lo,hi=batch['checkpoint']['plan']['first'],batch['checkpoint']['plan']['last']
        rows.append(done(batch,checkpoint=dict(kind='BATCH_PROGRESS_V1',plan=batch['checkpoint']['plan'],next=hi,children=[c['key'] for c in children[lo:hi]]),outcome=dict(outcome='BATCH_SCREENED',children=[])))
    for row in rows:
        w.boot.execute('INSERT INTO public.ingestion_work_items SELECT * FROM json_populate_record(NULL::public.ingestion_work_items,%s::json)',(json.dumps(row),))
    return [r['key'] for r in rows]


def retained_snapshot(w,keys):
    return {k:digest([state,json.dumps(cp,sort_keys=True),json.dumps(out,sort_keys=True),att,fence]) for k,state,cp,out,att,fence in w.boot.execute('SELECT key,state,checkpoint,outcome,attempt_count,fence FROM public.ingestion_work_items WHERE key=ANY(%s)',(keys,)).fetchall()}


@pytest.mark.parametrize('fault',FAULTS)
def test_screening_v3_lifecycle(world,fault,monkeypatch):
    w=world;tmp_path=w.tmp_path
    sv3_manifest=hashlib.sha256((ROOT/orr.SV3_MANIFEST_PATH).read_bytes()).hexdigest()
    # ---------------------------------------------------------------- production's state: v3, v4 and v5 installed by their real ceremonies; probe, capture and window entries consumed and revoked; generation 3
    policy,_=run_policy(w);assert policy['status']=='POLICY_GENERATION2_INSTALLED_CONTROL_RECORD_UNCHANGED'
    ctl=w.control()
    ctl['grants'][PROBE_NAME]=dict(keys=['k'],expires_at=0,source_calls=1,writes=0,login='ingestion_worker_login',bindings={'k':{}})
    ctl['bolton_exceptions'][PROBE_NAME]=dict(authority=PROBE_NAME,transport='REQUESTS_IDOX',grant_binding={},expires_at=0,hard_stop_generation=2)
    w.set_control(ctl)
    v4,_=run_capture_policy(w);assert v4['status']=='POLICY_CAPTURE_ALLOWANCE_INSTALLED_CONTROL_RECORD_UNCHANGED'
    ctl=w.control()
    ctl['grants'][OLDCAP]=dict(keys=['k'],expires_at=0,source_calls=1,writes=0,login='ingestion_worker_login',bindings={'k':{}})
    ctl['bolton_exceptions'][OLDCAP]=dict(authority=OLDCAP,transport='REQUESTS_IDOX',grant_binding={},expires_at=0,hard_stop_generation=2)
    ctl['hard_stop_generation']=3
    w.set_control(ctl)
    v5,_=run_window_policy(w);assert v5['status']=='POLICY_WINDOW_ALLOWANCE_INSTALLED_CONTROL_RECORD_UNCHANGED'
    ctl=w.control()
    for name in (WINDOW_CAP,WINDOW_SCR):      # the consumed window names, registered and revoked on 20 October
        ctl['grants'][name]=dict(keys=['k'],expires_at=0,source_calls=0,writes=0,login='ingestion_worker_login',bindings={'k':{}})
        ctl['bolton_exceptions'][name]=dict(authority=name,transport='REQUESTS_IDOX',grant_binding={},expires_at=0,hard_stop_generation=3)
    w.set_control(ctl)
    assert len(w.control()['bolton_exceptions'])==6
    retained_keys=seed_retained_world(w)
    functions_v5=w.functions()
    # ---------------------------------------------------------------- ceremony 1: policy v6 + the derived v3 worker function (its first step IS the observation that verifies the baseline)
    pol,prunner=run_sv3_policy(w)
    assert pol['status']=='POLICY_SCREENING_V3_INSTALLED_CONTROL_RECORD_UNCHANGED' and pol['cleanup']=='CLOSED' and pol['inventory_verified'] is True and pol['github_requests']==0 and pol['transient_owner_capability']=='ABSENT_READ_BACK'
    changed=sorted(k for k in functions_v5 if functions_v5[k]!=w.functions().get(k));assert changed==['ingestion_bolton_allowed','ingestion_register_bolton_exception','ingestion_worker_step']
    assert pol['control_sha256_before']==pol['control_sha256_after']==digest(w.control())
    assert prunner.owner.commands<=orr.SV3_POLICY_OWNER_LIMITS['commands'][0] and prunner.owner.connections<=orr.SV3_POLICY_OWNER_LIMITS['connections'][0],(prunner.owner.commands,prunner.owner.connections)
    # ---------------------------------------------------------------- ceremony 2: the screening-only assessment
    real_revision=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,stdout=subprocess.PIPE,check=True).stdout.decode().strip()
    real_tree=subprocess.run(['git','rev-parse','HEAD^{tree}'],cwd=ROOT,stdout=subprocess.PIPE,check=True).stdout.decode().strip()      # the owner binds the tree the hosted checkout reports
    registration=dict(w.registration,mode=orr.SV3_MODE,revision=real_revision,tree=real_tree,controller_sha256=hashlib.sha256((ROOT/'verification/ingestion_storage/operational_runner.py').read_bytes()).hexdigest(),
                      manifest_sha256=sv3_manifest,evidence_directory=orr.SV3_EVIDENCE_DIRECTORY,control_sha256=pol['control_sha256_after'],expires_at=(datetime.now(timezone.utc)+timedelta(minutes=100)).isoformat())
    if fault=='wrong_revision':registration['revision']='e'*40
    valid_until=min(r[3] for r in w.standing[0]).astimezone(timezone.utc).isoformat()
    monkeypatch.setitem(orr.SV3_BINDING,'valid_until',valid_until);monkeypatch.setitem(orr.SV3_BINDING,'poll_seconds',1.0)
    monkeypatch.setitem(orr.SV3_BINDING,'ready_wait_seconds',8 if fault in ('ready_wait_expires','wrong_revision') else 120)
    monkeypatch.setitem(orr.SV3_BINDING,'screening_wait_seconds',8 if fault in ('hosted_publication_fails',) else 150)
    monkeypatch.setitem(orr.SV3_BINDING,'execution_deadline_seconds',8 if fault in ('hosted_publication_fails',) else 150)
    monkeypatch.setitem(orr.SV3_BINDING,'grant_lifetime_seconds',5 if fault=='authority_expires' else 900)
    if fault=='altered_row':
        victim=[k for k in retained_keys if k!=rw.CAPTURE_KEY][3]
        w.boot.execute("UPDATE public.ingestion_work_items SET checkpoint=jsonb_set(checkpoint::jsonb,'{progress}','\"ALTERED\"')::json WHERE key=%s AND task='SCREENING'",(victim,))
    if fault=='missing_row':
        w.boot.execute("DELETE FROM public.ingestion_work_items WHERE key=%s",(retained_keys[-1],))
    ctl_before=w.control();snapshot_before=retained_snapshot(w,retained_keys);items_before=w.boot.execute('SELECT count(*) FROM public.ingestion_work_items').fetchone()[0]
    owner_journal=Journal(tmp_path/'owner');holder={}
    owner_scope=OwnerScope();after_close=[]
    def counted_cli(command,**kw):
        if owner_scope.closed:after_close.append(command)
        if fault=='owner_publication_fails' and any('/owner/' in str(part) for part in command):
            return subprocess.CompletedProcess(command,1,stdout=b'',stderr=b'rehearsal owner publication failure')
        return w.cli(command,**kw)
    github=GitHub(owner_journal.emit,lambda:holder['r'].check(),runner=counted_cli,bound=orr.PIPELINE_GITHUB_BOUND)
    orunner=Runner(registration,owner_journal,w.connector,source_reader=lambda row:(_ for _ in ()).throw(AssertionError('the owner never reads a source')),github=github,url_factory=w.uri,identity=w.role,memory=owner_scope);holder['r']=orunner
    orunner.pipeline_sleep=lambda s:time.sleep(min(s,1.0))
    stop_codes=[];original_failed=orunner.failed
    def failed_with_code(exc):
        text=exc.args[0] if getattr(exc,'args',None) and isinstance(exc.args[0],str) else ''
        stop_codes.append(dict(exception=type(exc).__name__,code=text if re.fullmatch(r'[A-Z][A-Z0-9_]{2,79}',text) else 'NOT_A_FIXED_CODE'))
        return original_failed(exc)
    orunner.failed=failed_with_code
    hosted_dir=tmp_path/'hosted-out';spawned=[]
    plan=dict(disposable='LOOPBACK_ONLY',fault=fault,dbname=w.info['dbname'],gh=w.metadata.gh,gh_env=w.metadata.fixture_env(),evidence_head=registration['evidence_head'],manifest_sha256=registration['manifest_sha256'],
              revision=registration['revision'],output=str(hosted_dir),lapse_seconds=7,marker_wait=6 if fault=='wrong_controller' else 60)
    plan_path=tmp_path/'plan.json';plan_path.write_text(json.dumps(plan))
    def start_hosted():
        env=dict(os.environ,INGESTION_ACCEPTANCE_DISPOSABLE='PG17_ONLY',REHEARSAL_URLS=json.dumps(w.urls),PYTHONPATH=str(Path.cwd()),PYTHONDONTWRITEBYTECODE='1')
        subprocess.run(['sh','-c','"$0" -B -m tests.screening_v3_rehearsal "$1" >"$2" 2>&1 &',sys.executable,str(plan_path),str(tmp_path/'hosted.log')],env=env,check=True,timeout=20)
        spawned.append(True)
    original_await=orunner.await_any
    def await_any(relatives,seconds):      # the restricted job is dispatched only after the owner verified the retained world, exactly as the production sequence
        if not spawned and fault not in ('ready_wait_expires',):start_hosted()
        return original_await(relatives,seconds)
    orunner.await_any=await_any
    lines=[]
    result=session(owner_journal,registration['expires_at'],lambda:'hidden fixture input',lambda raw_,started:orunner,output=lambda line,**kw:lines.append(line),timing=orr.PIPELINE_TIMING)
    if spawned:
        end=time.monotonic()+90
        while not (hosted_dir/'rehearsal-done').exists() and time.monotonic()<end:time.sleep(0.2)
    summary=dict(fault=fault,status=result.get('status'),cleanup=result.get('cleanup'),invalidation=result.get('authority_invalidation'),stop_codes=stop_codes,phase=result.get('operation_phase'),
                 commands=orunner.owner.commands,connections=orunner.owner.connections,github_requests=orunner.github.requests)
    print('SV3_OWNER_RESULT',json.dumps(summary,default=str,sort_keys=True))
    hosted_log=(tmp_path/'hosted.log').read_text() if (tmp_path/'hosted.log').exists() else ''
    hosted_final=json.loads((hosted_dir/'final-result.json').read_bytes()) if (hosted_dir/'final-result.json').exists() else None
    source_calls=int((hosted_dir/'rehearsal-source-calls').read_text()) if (hosted_dir/'rehearsal-source-calls').exists() else 0
    ctl_after=w.control()
    text=owner_journal.file.read_text()+json.dumps(result)+((hosted_dir/'events.jsonl').read_text() if (hosted_dir/'events.jsonl').exists() else '')
    assert 'postgresql://' not in text
    # ---------------------------------------------------------------- invariants on EVERY path
    assert ctl_after['global_stop']==ctl_before['global_stop'] and ctl_after['hard_stop_generation']==3 and ctl_after['manual_stop']==IDOX and ctl_after['last_hard_stop']==IDOX      # no stop is raised, released or advanced by a normal or refused run
    assert (w.roles_state(),w.memberships(),w.role_configs())==w.standing      # standing credentials: no password, membership or role-setting change
    for name in EARLIER:      # every historical grant and exception preserved byte-for-byte
        assert ctl_after['grants'][name]==ctl_before['grants'][name] and ctl_after['bolton_exceptions'][name]==ctl_before['bolton_exceptions'][name]
    ours=[a for a in ctl_after['grants'] if a==NAME]
    for a in ours:assert ctl_after['grants'][a]['expires_at']==0 and ctl_after['bolton_exceptions'][a]['expires_at']==0      # ended by invalidation, never merely by time
    assert owner_scope.closed and after_close==[]      # the owner's scope is closed exactly once, and nothing was sent to GitHub afterwards
    assert result['application_writes']==0 and result['stage4']=='OPEN' and result['pipeline_retry']=='HELD'
    assert source_calls==0 and (hosted_final is None or hosted_final.get('source_observations_attempted',0)==0)      # ZERO source calls on every path
    assert retained_snapshot(w,[k for k in retained_keys if w.boot.execute('SELECT 1 FROM public.ingestion_work_items WHERE key=%s',(k,)).fetchone()])=={k:v for k,v in snapshot_before.items() if w.boot.execute('SELECT 1 FROM public.ingestion_work_items WHERE key=%s',(k,)).fetchone()}      # the retained rows are byte-identical
    v3_count=w.boot.execute("SELECT count(*) FROM public.ingestion_work_items WHERE contract IN ('listing-screen-v3') OR (contract='listing-batch-v1' AND checkpoint::jsonb->'plan'->'screening' IS NOT NULL)").fetchone()[0]
    caps=orr.SV3_OWNER_LIMITS;ended_normally=result['status'].startswith('SCREENING_V3_RETAINED_COMPLETED')
    assert orunner.owner.opened==orunner.owner.closed and orunner.owner.connections<=(caps['connections'][0] if ended_normally else caps['connections'][1]) and orunner.owner.commands<=(caps['commands'][1] if ended_normally else caps['commands'][2]),summary
    if fault in ('altered_row','missing_row','ready_wait_expires','wrong_revision','wrong_controller'):      # refused BEFORE any authority: nothing issued, nothing created
        assert result['status']=='STOP_RECONCILE_NO_RETRY' and not ours and v3_count==0 and w.boot.execute('SELECT count(*) FROM public.ingestion_work_items').fetchone()[0]==items_before
        assert result['authority_invalidation']=='NOT_REQUIRED_NO_AUTHORITY' and len(ctl_after['bolton_exceptions'])==6 and set(ctl_after['grants'])==set(ctl_before['grants'])
        expected={'altered_row':'RETAINED_ASSESSMENT_ALTERED','missing_row':'RETAINED_ROW_MISSING','ready_wait_expires':'HOSTED_PUBLICATION_WAIT_EXPIRED','wrong_revision':'HOSTED_PUBLICATION_WAIT_EXPIRED','wrong_controller':'HOSTED_READY_BINDING'}[fault]
        assert stop_codes and stop_codes[0]['code']==expected,(stop_codes,hosted_log[-1200:])
        assert (fault in ('ready_wait_expires','altered_row','missing_row')) == (not spawned)
        return
    assert spawned and hosted_final is not None,hosted_log[-2500:]
    assert ours==[NAME] and ctl_after['bolton_exceptions'][NAME]['hard_stop_generation']==3 and len(ctl_after['bolton_exceptions'])==7 and ctl_after['grants'][NAME]['source_calls']==0 and ctl_after['grants'][NAME]['writes']==0      # the ONE name, registered through the named exemption only
    assert len(ctl_after['grants'][NAME]['keys'])==59 and ctl_after['grants'][NAME]['screening_configs']==[digest(V3.config())]
    if fault in ('hosted_publication_fails','hosted_fails','authority_expires'):
        assert result['authority_invalidation'] in ('ACKNOWLEDGED_READBACK','ALREADY_INVALIDATED_READBACK') and result['cleanup']=='CLOSED'
        if fault=='hosted_publication_fails':
            assert result['status']=='STOP_RECONCILE_NO_RETRY' and stop_codes[0]['code']=='HOSTED_PUBLICATION_WAIT_EXPIRED'
        else:
            assert hosted_final['status']=='STOP_RECONCILE_NO_RETRY' and result['status']=='SCREENING_V3_RETAINED_ENDED_INCOMPLETE_AUTHORITY_INVALIDATED' and result['screening']=='INCOMPLETE'
        if fault=='authority_expires':assert v3_count==0 or v3_count<29      # the lapsed allowance created at most what it covered, and nothing after expiry
        assert retained_snapshot(w,retained_keys)==snapshot_before
        return
    assert result['authority_invalidation']=='ACKNOWLEDGED_READBACK'
    assert v3_count==29 and w.boot.execute('SELECT count(*) FROM public.ingestion_work_items').fetchone()[0]==items_before+29      # exactly five new batch rows and 24 v3 children
    assert all(state=='COMPLETE' for _,state in w.items())
    admissions={}
    for (cp,) in w.boot.execute("SELECT checkpoint FROM public.ingestion_work_items WHERE contract='listing-screen-v3'").fetchall():
        a=cp['count_assessment']['admission'];admissions[a]=admissions.get(a,0)+1
    assert admissions==dict(RETAIN_NOT_RESIDENTIAL_SUPPLY=16,ROUTE_COUNT_UNCONFIRMED=4,RETAIN_RELATED_TO_PARENT=2,ADMIT_SCHEME=1,RETAIN_BELOW_THRESHOLD=1)      # a rehearsal result on the retained capture, not a production result
    assert hosted_final['status']=='SCREENING_V3_RETAINED_ASSESSED_RESTRICTED_RUNTIME_ONLY' and hosted_final['assessments']==24 and hosted_final['eligible']==['01768/26'] and hosted_final['cleanup']=='CLOSED'
    assert hosted_final['credential_changes']==0 and hosted_final['application_writes']==0 and hosted_final['identities_created']==0 and hosted_final['checkout_binding']['manifest_sha256']==sv3_manifest and hosted_final['checkout_binding']['tracked_files_modified'] is False
    assert int((hosted_dir/'rehearsal-memory-closed-after-gh-calls').read_text())==int((hosted_dir/'rehearsal-gh-calls-total').read_text())      # publication-before-closure on the hosted side, in the real publication path
    assert hosted_final['closure_stage']=='FINAL_AFTER_PUBLICATION' and hosted_final['publication']=='PUBLISHED' and hosted_final['published_cleanup']=='PENDING_MEMORY_SCOPE_CLOSURE'
    slots=hosted_final['slot_receipts'];totals=dict(statements=0,connections=0,returned_bytes=0,seconds=0.0)
    for r in slots.values():
        d=r['database'];totals['statements']+=d['driver_statements'];totals['connections']+=d['connection_attempts'];totals['returned_bytes']+=d['returned_data_value_bytes'];totals['seconds']+=r['supervised_seconds']
    assert len(slots)==6 and all(r['cleanup']=='CLOSED' for r in slots.values())      # the capture-slot (plan and verification) and five batch slots, each closed
    if fault=='success':
        assert result['status']=='SCREENING_V3_RETAINED_COMPLETED_AUTHORITY_INVALIDATED' and result['cleanup']=='CLOSED' and result['screening']=='COMPLETE' and result['credentials'].startswith('UNCHANGED')
        assert result['readback_after']['findings']==[] and result['readback_before']['findings']==[] and result['closure_stage']=='FINAL_AFTER_PUBLICATION' and result['publication']=='PUBLISHED'
        head=json.loads(w.metadata.cli(['gh','api','--method','GET',sp.REPO+'/git/ref/heads/'+sp.BRANCH]).stdout)['object']['sha']
        blob=json.loads(w.metadata.cli(['gh','api','--method','GET',sp.REPO+'/contents/'+orr.SV3_EVIDENCE_DIRECTORY+'/owner/final-result.json?ref='+head]).stdout)
        published=json.loads(base64.b64decode(blob['content']))
        assert published['closure_stage']=='PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE' and published['authority_invalidation']=='ACKNOWLEDGED_READBACK'
        print('SV3_LIFECYCLE_MEASURED',json.dumps(dict(owner_commands=orunner.owner.commands,owner_connections=orunner.owner.connections,owner_github_requests=orunner.github.requests,hosted_statements=totals['statements'],hosted_connections=totals['connections'],
                                                      hosted_returned_bytes=totals['returned_bytes'],hosted_supervised_seconds=round(totals['seconds'],2),policy_commands=prunner.owner.commands,policy_connections=prunner.owner.connections,hosted_elapsed=hosted_final['accounting'].get('database_active_seconds')),sort_keys=True))
    if fault=='owner_publication_fails':      # a reporting failure after confirmed invalidation: the invalidation is preserved, the publication is reported as uncertain
        assert result['authority_invalidation']=='ACKNOWLEDGED_READBACK' and result['publication'].startswith('UNCERTAIN') and result['status'].endswith('_PUBLICATION_UNCERTAIN') and ctl_after['grants'][NAME]['expires_at']==0
