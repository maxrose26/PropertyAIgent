"""Owner side and static contracts of the Bolton WINDOW DEMONSTRATION and policy-v5 ceremony (specification 032 section 14): the mechanical derivation of policy v5, the derived generation-3 stop state and how it is
verified, registration binding, the mode's configuration and unchanged ceilings, the hosted identity and admission, the REAL checkout reader against this mode's own manifest, the restricted workflow's static contract,
the renderer, the manifest and the owner scripts. Offline."""
import difflib
import hashlib
import json
import re
import subprocess
from datetime import date,datetime,timedelta,timezone
from pathlib import Path

import pytest

from app.ingestion.ledger import Denied
from verification.discovery.idox_window import WindowConfig
from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage import stable_pipeline as sp
from verification.ingestion_storage import capture_acceptance as cap_mod
from verification.ingestion_storage import window_demonstration as wd
from verification.ingestion_storage.operational_journal import Journal

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'docs/design/ingestion-window-demonstration-20261023'
CAPTURE_PACKAGE=ROOT/'docs/design/ingestion-capture-acceptance-20261022'
WF=ROOT/'.github/workflows/stage4-window-demonstration-once.yml'
SPEC=ROOT/'specifications/032-stage4-stable-credential-pipeline.md'
G2=oo.GENERATION2_STOP
G3=oo.GENERATION3_STOP
IDOX='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE'
PROBE=orr.PROBE_AUTHORITY+'_PROBE'
OLDCAP=orr.CAPTURE_AUTHORITY+'_CAPTURE'
OLDSCR=orr.CAPTURE_AUTHORITY+'_SCREEN'
CAP=orr.WINDOW_AUTHORITY+'_CAPTURE'
SCR=orr.WINDOW_AUTHORITY+'_SCREEN'
DAY='{"kind":"DISCOVERY_SCOPE","council":"bolton","start":"2026-10-16","end":"2026-10-16","semantics":"RECEIVED"}'
WEEK='{"kind":"DISCOVERY_SCOPE","council":"bolton","start":"2026-09-28","end":"2026-10-04","semantics":"RECEIVED"}'


def render_module():
    import importlib.util
    spec=importlib.util.spec_from_file_location('render_window',PACKAGE/'render_registration.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


# ---------------------------------------------------------------- policy v5 is v4 plus exactly the generation-3 admission for one scope
def derive_v5(v4):
    out=v4[v4.index('BEGIN;'):]
    def swap(old,new):
        nonlocal out
        assert out.count(old)==1,old[:80];out=out.replace(old,new)
    swap("  AND ctl->>'manual_stop'='%s' AND ctl->>'last_hard_stop'='%s'))\n AND subject->>'council'='bolton'"%(IDOX,IDOX),
         "  AND ctl->>'manual_stop'='%s' AND ctl->>'last_hard_stop'='%s')\n  OR (authority IN ('%s','%s')\n   AND (ctl->>'hard_stop_generation')::integer=3 AND (ctl->'bolton_exceptions'->authority->>'hard_stop_generation')::integer=3\n   AND ctl->>'manual_stop'='%s' AND ctl->>'last_hard_stop'='%s'))\n AND subject->>'council'='bolton'"%(IDOX,IDOX,CAP,SCR,IDOX,IDOX))
    swap("e jsonb; t double precision; root public.ingestion_work_items%ROWTYPE;\n","e jsonb; t double precision; sc jsonb; root public.ingestion_work_items%ROWTYPE;\n")
    swap(" a:=p->>'authority';g:=ctl->'grants'->a;t:=extract(epoch FROM clock_timestamp());\n"," a:=p->>'authority';g:=ctl->'grants'->a;t:=extract(epoch FROM clock_timestamp());\n sc:=CASE WHEN a IN ('%s','%s') THEN '%s'::jsonb ELSE '%s'::jsonb END;      -- the exact scope this allowance may concern\n"%(CAP,SCR,WEEK,DAY))
    swap("   AND p->>'stop_checkpoint_sha256'='%s',false))      -- NULL (an absent stop field) is FALSE here, never a widening"%G2['stop_state_sha256'],
         "   AND p->>'stop_checkpoint_sha256'='%s',false)\n  OR coalesce(a IN ('%s','%s') AND (ctl->>'hard_stop_generation')::integer=3 AND (p->>'hard_stop_generation')::integer=3\n   AND ctl->>'manual_stop'='%s' AND ctl->>'last_hard_stop'='%s'\n   AND p->>'stop_checkpoint_sha256'='%s',false))      -- NULL (an absent stop field) is FALSE here, never a widening"%(G2['stop_state_sha256'],CAP,SCR,IDOX,IDOX,G3['stop_state_sha256']))
    swap("AND NOT coalesce(a IN ('%s','%s') AND (ctl->>'hard_stop_generation')::integer=2,false))"%(OLDCAP,OLDSCR),
         "AND NOT coalesce((a IN ('%s','%s') AND (ctl->>'hard_stop_generation')::integer=2) OR (a IN ('%s','%s') AND (ctl->>'hard_stop_generation')::integer=3),false))"%(OLDCAP,OLDSCR,CAP,SCR))
    swap("root.subject::jsonb IS DISTINCT FROM '%s'::jsonb"%DAY,"root.subject::jsonb IS DISTINCT FROM sc")
    swap("item->'subject' IS DISTINCT FROM '%s'::jsonb THEN"%DAY,"item->'subject' IS DISTINCT FROM sc THEN")
    return out


def test_policy_v5_body_is_the_mechanical_derivation_of_v4_and_changes_exactly_five_lines():
    v4=(CAPTURE_PACKAGE/'policy-capture-allowance.sql').read_text();v5=(PACKAGE/'policy-window-allowance.sql').read_text()
    assert v5[v5.index('BEGIN;'):]==derive_v5(v4)
    diff=list(difflib.unified_diff(v4[v4.index('BEGIN;'):].splitlines(),v5[v5.index('BEGIN;'):].splitlines(),lineterm='',n=0))
    removed=[l for l in diff if l[:1]=='-' and l[:3]!='---']
    assert len(removed)==5      # five v4 lines are modified (the allowed-branch addition re-uses the v4 line ending); everything else is byte-identical
    body=v5[v5.index('BEGIN;'):]
    assert body.count(CAP)==body.count(SCR)==4 and G3['stop_state_sha256'] in body and body.count(WEEK)==1 and body.count(DAY)==1      # the week scope appears once (the exact-scope selector); the day scope remains for every other name
    assert "(a IN ('%s','%s') AND (ctl->>'hard_stop_generation')::integer=3)"%(CAP,SCR) in body      # the cap exemption is conditioned on generation 3


def test_the_five_inventories_differ_as_reviewed_and_the_new_names_are_distinct_from_every_historical_authority():
    v4=oo.Owner.capture_inventory();v5=oo.Owner.window_inventory()
    assert set(v4)==set(v5) and sorted(k for k in v4 if v4[k]!=v5[k])==['ingestion_bolton_allowed','ingestion_register_bolton_exception']
    assert len({PROBE,OLDCAP,OLDSCR,CAP,SCR,orr.PIPELINE_AUTHORITY+'_CAPTURE',orr.PIPELINE_AUTHORITY+'_SCREEN'})==7


# ---------------------------------------------------------------- the derived generation-3 stop state, and how it is verified
def test_the_derived_stop_digest_is_the_same_computation_that_reproduced_the_observed_generation_2_digest():
    def digest_for(generation):
        ctl=dict(global_stop=oo.STOP,manual_stop=IDOX,last_hard_stop=IDOX,hard_stop_generation=generation,grants={},bolton_exceptions={})
        return oo.Owner.project_control(ctl,1.0)['stop_state_sha256']
    assert digest_for(2)==G2['stop_state_sha256']      # the OBSERVED production digest, reproduced by this code
    assert digest_for(3)==G3['stop_state_sha256'] and G3['hard_stop_generation']==3 and G3['manual_stop']==G3['last_hard_stop']==IDOX


def test_the_derivation_of_last_hard_stop_rests_on_the_code_that_raises_the_stop():
    coordinator=(ROOT/'app/ingestion/coordinator.py').read_text();worker=(ROOT/'docs/design/ingestion-operational-20261016/worker.sql').read_text()
    assert "self.ledger.stop('IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE',claim=claim)" in coordinator
    assert "jsonb_build_object('manual_stop',p_reason,'last_hard_stop',p_reason,'hard_stop_generation'" in worker      # both fields take the same reason; the generation increments


def test_the_spec_states_what_is_observed_what_is_derived_and_what_success_would_not_mean():
    text=SPEC.read_text()
    section=text[text.index('## 14.'):].replace('**','')
    for needle in ('recognised `p.pager` element was absent','not evidence that every possible count or pagination signal was absent','observed pattern across two observations, not proven council design',
                   'Derived, not yet observed:','refuses before touching anything','would not resolve sparse-day coverage','would not advance Stage 4','would not authorise scheduling',
                   'Separate product requirement, not implemented here: sparse-day acquisition','nothing in this candidate implements or pre-empts it','Resource ceilings are unchanged','the ceilings are not expanded'):
        assert needle in section,needle


# ---------------------------------------------------------------- scope and ceilings
def test_the_window_scope_is_the_observed_multi_page_window_and_only_the_scope_and_stop_state_differ_from_the_capture_binding():
    assert oo.WINDOW_SCOPE==dict(kind='DISCOVERY_SCOPE',council='bolton',start='2026-09-28',end='2026-10-04',semantics='RECEIVED') and json.dumps(oo.WINDOW_SCOPE,separators=(',',':'),sort_keys=False)==WEEK
    cb=orr.CAPTURE_BINDING;wb=orr.WINDOW_BINDING
    different={k for k in wb if wb[k]!=cb.get(k)}
    assert different=={'hard_stop_generation','stop_state_sha256','hosted_workflow','hosted_authority','scope'}      # nothing else, including every ceiling and every wait
    assert wb['source']==cb['source']==dict(form_requests=1,listing_requests_after_a_valid_form=9,total_requests=10,redirects=0,retries=0,bytes=3000000,rows=60,pages=6,body_retained='RAW_ARCHIVED_BEFORE_CHECKPOINT')
    config=WindowConfig('bolton','RECEIVED',date(2026,9,28),date(2026,10,4),0)
    assert (config.end-config.start).days==6<=27 and config.max_transport_retries==0
    assert wd.WindowHostedRunner.scope==oo.WINDOW_SCOPE and wd.WindowHostedRunner.window_config==config and orr.Runner.scope==oo.SCOPE and sp.HostedRunner.scope==oo.SCOPE      # the accepted modes keep the day scope


def test_the_ceilings_are_the_accepted_pipelines_stated_in_full():
    from verification.discovery.idox_window import WindowBoundary
    b=WindowBoundary(lambda *a,**k:None,wd.WindowHostedRunner.window_config)
    assert (b.budget.requests,b.budget.total_bytes,b.budget.response_bytes,b.budget.seconds,b.max_retries)==(10,3_000_000,500_000,45,0)
    assert orr.PIPELINE_OWNER_LIMITS==dict(connections=(8,10),commands=(56,80,96)) and orr.PIPELINE_GITHUB_BOUND==180 and sp.HOSTED_DEADLINES['job']==1800
    wb=orr.WINDOW_BINDING
    assert (wb['grant_minutes'],wb['screening_grant_minutes'],wb['capture_wait_seconds'],wb['screening_wait_seconds'],wb['poll_seconds'])==(55,30,2700,600,30)
    assert orr.WINDOW_POLICY_OWNER_LIMITS==dict(connections=(3,4),commands=(34,40,48))
    item=oo.item(dict(subject=oo.WINDOW_SCOPE,task='DISCOVERY',contract=orr.CONTRACT,revision='c'*64),max_attempts=1,limits=dict(oo.DEFAULT_LIMITS,requests=10,bytes=3000000,rows=60,pages=6))
    assert item['limits']['requests']==10 and item['limits']['bytes']==3000000 and item['limits']['rows']==60 and item['limits']['pages']==6
    day=oo.item(dict(subject=oo.SCOPE,task='DISCOVERY',contract=orr.CONTRACT,revision='c'*64),max_attempts=1,limits=dict(oo.DEFAULT_LIMITS,requests=10,bytes=3000000,rows=60,pages=6))
    assert item['key']!=day['key']      # a different scope is a different capture root


# ---------------------------------------------------------------- registration validators
def registration(mode):
    base=json.loads((PACKAGE/'base_constants.json').read_text());base={k:v for k,v in base.items() if not k.startswith('_')};base.pop('limits',None)
    common=dict(base,expires_at=(datetime.now(timezone.utc)+timedelta(minutes=20)).replace(microsecond=0).isoformat(),revision='a'*40,tree='b'*40,hashes={},controller_sha256='c'*64,ca_sha256='d'*64,manifest_sha256='e'*64,evidence_head='1'*40)
    if mode=='policy':
        return dict(common,mode=orr.WINDOW_POLICY_MODE,authority=orr.WINDOW_POLICY_AUTHORITY,evidence_directory=orr.WINDOW_EVIDENCE_DIRECTORY,predecessor=orr.WINDOW_POLICY_PREDECESSOR,state_directory=orr.WINDOW_POLICY_STATE,
                    execution_authority='NONE',risk_application='THIS_FINITE_POLICY_WINDOW_ALLOWANCE_INSTALLATION_ONLY',owner_limits=dict(connections=list(orr.WINDOW_POLICY_OWNER_LIMITS['connections']),commands=list(orr.WINDOW_POLICY_OWNER_LIMITS['commands'])),
                    policy=dict(file=str(oo.GENERATION3_WINDOW_POLICY),named_allowances=[CAP,SCR],baseline=G3,scope=oo.WINDOW_SCOPE,cap='UNCHANGED_EXCEPT_FOR_THE_TWO_NAMED_ALLOWANCES'),
                    execution=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=orr.WINDOW_POLICY_STATE),approval='X')
    return dict(common,mode=orr.WINDOW_MODE,authority=orr.WINDOW_AUTHORITY,evidence_directory=orr.WINDOW_EVIDENCE_DIRECTORY,predecessor=orr.WINDOW_PREDECESSOR,state_directory=orr.WINDOW_STATE,
                execution_authority='OWNER_GRANT_AND_EXCEPTION_FOR_THE_HOSTED_RESTRICTED_JOB',risk_application='THIS_FINITE_BOLTON_WINDOW_DEMONSTRATION_ONCE',window=orr.WINDOW_BINDING,
                owner_limits=dict(connections=list(orr.PIPELINE_OWNER_LIMITS['connections']),commands=list(orr.PIPELINE_OWNER_LIMITS['commands'])),policy_ceremony_audit=dict(events_sha256='1'*64,final_result_sha256='2'*64),control_sha256='3'*64,
                execution=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=orr.WINDOW_STATE),approval='X')


def validate(r):
    body=json.dumps(r,sort_keys=True,indent=1).encode();return orr.validate_registration(body,hashlib.sha256(body).hexdigest())


@pytest.mark.parametrize('mode,binding_error',[('policy','BOLTON_WINDOW_POLICY_BINDING'),('window','BOLTON_WINDOW_DEMONSTRATION_BINDING')])
def test_the_validators_bind_each_mode_exactly(mode,binding_error):
    with pytest.raises(ValueError,match='CLEAN_REVIEWED_CHECKOUT'):validate(registration(mode))      # every binding passes; only the (deliberately wrong) checkout identity stops it
    tampers={'policy':[dict(execution_authority='X'),dict(state_directory=orr.PIPELINE_STATE),dict(owner_limits=dict(connections=[9,9],commands=[34,40,48])),dict(policy=dict(file='x',named_allowances=[CAP,SCR],baseline=G3,scope=oo.WINDOW_SCOPE)),
                       dict(policy=dict(file=str(oo.GENERATION3_WINDOW_POLICY),named_allowances=[CAP,SCR,'ANY_OTHER'],baseline=G3,scope=oo.WINDOW_SCOPE,cap='UNCHANGED_EXCEPT_FOR_THE_TWO_NAMED_ALLOWANCES')),
                       dict(policy=dict(file=str(oo.GENERATION3_WINDOW_POLICY),named_allowances=[CAP,SCR],baseline=G2,scope=oo.WINDOW_SCOPE,cap='UNCHANGED_EXCEPT_FOR_THE_TWO_NAMED_ALLOWANCES')),
                       dict(policy=dict(file=str(oo.GENERATION3_WINDOW_POLICY),named_allowances=[CAP,SCR],baseline=G3,scope=oo.SCOPE,cap='UNCHANGED_EXCEPT_FOR_THE_TWO_NAMED_ALLOWANCES')),dict(window=orr.WINDOW_BINDING)],
             'window':[dict(window=dict(orr.WINDOW_BINDING,grant_minutes=999)),dict(window=dict(orr.WINDOW_BINDING,hard_stop_generation=2)),dict(window=dict(orr.WINDOW_BINDING,scope=oo.SCOPE)),dict(window=orr.CAPTURE_BINDING),dict(execution_authority='NONE'),
                       dict(state_directory=orr.CAPTURE_STATE),dict(evidence_directory=orr.CAPTURE_EVIDENCE_DIRECTORY),dict(owner_limits=dict(connections=[9,9],commands=[56,80,96])),dict(policy_ceremony_audit=None),
                       dict(policy_ceremony_audit=dict(events_sha256='short',final_result_sha256='2'*64)),dict(control_sha256='short'),dict(control_sha256=None),dict(predecessor=orr.CAPTURE_PREDECESSOR),
                       dict(predecessor=dict(orr.WINDOW_PREDECESSOR,derived_stop=dict(G3,hard_stop_generation=2))),dict(capture=orr.CAPTURE_BINDING),dict(pipeline=orr.PIPELINE_BINDING),dict(probe=orr.PROBE_BINDING)]}[mode]
    for tamper in tampers:
        with pytest.raises(ValueError,match=binding_error):validate(dict(registration(mode),**tamper))
    with pytest.raises(ValueError,match='EXACT_OPERATIONAL_APPROVAL_REQUIRED'):validate(dict(registration(mode),scope=oo.SCOPE))      # the registration's own scope must be the window scope


def test_the_capture_acceptance_registrations_no_longer_validate_for_the_window_and_the_window_ones_do_not_validate_as_captures():
    for other in (orr.CAPTURE_AUTHORITY,orr.PIPELINE_AUTHORITY,orr.PROBE_AUTHORITY,orr.CAPTURE_POLICY_AUTHORITY):
        with pytest.raises(ValueError,match='EXACT_OPERATIONAL_APPROVAL_REQUIRED'):validate(dict(registration('window'),authority=other))
    with pytest.raises(ValueError,match='EXACT_OPERATIONAL_APPROVAL_REQUIRED'):validate(dict(registration('policy'),authority=orr.WINDOW_AUTHORITY))
    long_policy=dict(registration('policy'),expires_at=(datetime.now(timezone.utc)+timedelta(minutes=45)).replace(microsecond=0).isoformat())
    with pytest.raises(ValueError,match='ORIGINAL_OPERATIONAL_EXPIRY'):validate(long_policy)
    three_hours=dict(registration('window'),expires_at=(datetime.now(timezone.utc)+timedelta(minutes=190)).replace(microsecond=0).isoformat())
    with pytest.raises(ValueError,match='ORIGINAL_OPERATIONAL_EXPIRY'):validate(three_hours)
    two_hours=dict(registration('window'),expires_at=(datetime.now(timezone.utc)+timedelta(minutes=110)).replace(microsecond=0).isoformat())
    with pytest.raises(ValueError,match='CLEAN_REVIEWED_CHECKOUT'):validate(two_hours)


def runner_for(mode,tmp_path):
    r=registration(mode);Path(tmp_path).mkdir(parents=True,exist_ok=True)
    return orr.Runner(r,Journal(Path(tmp_path)/mode),lambda:None,source_reader=None,github=None,url_factory=None)


def test_the_window_mode_runner_is_bound_to_the_v5_inventory_the_generation_3_stop_the_window_scope_and_the_pipelines_limits(tmp_path):
    r=runner_for('window',tmp_path);o=r.owner
    assert r.pipeline_mode and r.capture_mode and r.window_mode and not r.probe_mode and not r.policy_mode and r.authority==orr.WINDOW_AUTHORITY
    assert o.permitted_policy_states==('GENERATION3_WINDOW_POLICY_APPLIED',) and o.stop_manual==IDOX and o.stop_sha==G3['stop_state_sha256'] and o.expected_generation==3 and o.apply_policy is False
    assert r.scope==oo.WINDOW_SCOPE and r.window_config==wd.WindowHostedRunner.window_config and r.deadlines==orr.PIPELINE_DEADLINES and o.limits==orr.PIPELINE_OWNER_LIMITS
    p=runner_for('policy',tmp_path)
    assert p.policy_mode and p.window_policy_mode and not p.capture_policy_mode and not p.pipeline_mode and p.deadlines==orr.POLICY_DEADLINES and p.owner.limits==orr.POLICY_OWNER_LIMITS and p.owner.apply_policy is False
    capture=orr.Runner(dict(registration('window'),mode=orr.CAPTURE_MODE),Journal(Path(tmp_path)/'c'),lambda:None,source_reader=None,github=None,url_factory=None)
    assert capture.window_mode is False and capture.scope==oo.SCOPE and capture.owner.expected_generation==2 and capture.authority==orr.CAPTURE_AUTHORITY      # the consumed mode keeps its own scope and stop state
    stable=orr.Runner(dict(registration('window'),mode=orr.PIPELINE_MODE),Journal(Path(tmp_path)/'s'),lambda:None,source_reader=None,github=None,url_factory=None)
    assert stable.capture_mode is False and stable.scope==oo.SCOPE and stable.owner.expected_generation==1 and stable.authority==orr.PIPELINE_AUTHORITY


def test_the_post_capture_baseline_is_the_derived_state_verified_by_observation_and_refuses_everything_else(tmp_path):
    r=runner_for('policy',tmp_path)
    def record(**over):
        ctl=dict(global_stop=oo.STOP,manual_stop=IDOX,last_hard_stop=IDOX,hard_stop_generation=3,
                 grants={PROBE:dict(expires_at=0),OLDCAP:dict(expires_at=0)},bolton_exceptions={PROBE:dict(expires_at=0,transport='REQUESTS_IDOX',hard_stop_generation=2,grant_binding={}),OLDCAP:dict(expires_at=0,transport='REQUESTS_IDOX',hard_stop_generation=2,grant_binding={})})
        ctl.update(over)
        return dict(projection=oo.Owner.project_control(ctl,1.0e9))
    assert r.require_post_capture_baseline(record())['hard_stop_generation']==3
    for bad in (dict(manual_stop='OTHER'),dict(last_hard_stop='OTHER'),dict(hard_stop_generation=2),dict(hard_stop_generation=4),dict(grants={PROBE:dict(expires_at=0)}),dict(grants={PROBE:dict(expires_at=0),OLDCAP:dict(expires_at=2.0e9)}),
                dict(bolton_exceptions={PROBE:dict(expires_at=0),OLDCAP:dict(expires_at=2.0e9)}),dict(grants={PROBE:dict(expires_at=0),OLDCAP:dict(expires_at=0),CAP:dict(expires_at=0)}),
                dict(bolton_exceptions={PROBE:dict(expires_at=0),OLDCAP:dict(expires_at=0),SCR:dict(expires_at=0)}),dict(grants={PROBE:dict(expires_at=0),OLDCAP:dict(expires_at=0),OLDSCR:dict(expires_at=0)}),dict(global_stop={})):
        with pytest.raises(Exception,match='OBSERVED_BASELINE_CHANGED'):r.require_post_capture_baseline(record(**bad))


def test_every_credential_mode_validates_the_hidden_input_before_consuming_the_registration():
    assert orr.WINDOW_POLICY_MODE in orr.INPUT_PRECHECKED_MODES and orr.WINDOW_MODE in orr.INPUT_PRECHECKED_MODES


# ---------------------------------------------------------------- the hosted half
def hosted_runner(tmp_path):
    urls={r:'postgresql://%s:x@h/db'%r for r in oo.ROLES};Path(tmp_path).mkdir(parents=True,exist_ok=True)
    return wd.WindowHostedRunner(urls,Journal(Path(tmp_path)/'j'),None,None,{},'192.0.2.1',None,evidence_head='1'*40,manifest_sha256='c'*64,revision='a'*40)


def test_the_hosted_identity_equals_the_owners_and_reads_only_its_own_allowance(tmp_path):
    h=hosted_runner(tmp_path)
    root=oo.item(dict(subject=oo.WINDOW_SCOPE,task='DISCOVERY',contract=orr.CONTRACT,revision='c'*64),max_attempts=1,limits=dict(oo.DEFAULT_LIMITS,requests=10,bytes=3000000,rows=60,pages=6))
    assert h.capture_key==root['key'] and h.execution==dict(revision='a'*40,manifest_sha256='c'*64,capture_key=root['key'],initial_evidence_head='1'*40,authority=orr.WINDOW_AUTHORITY)
    assert h.GRANT_SUFFIX=='_CAPTURE' and h.authority+h.GRANT_SUFFIX==CAP and h.r['evidence_directory']==orr.WINDOW_EVIDENCE_DIRECTORY and h.MANIFEST==wd.WINDOW_MANIFEST_PATH and h.deadlines==sp.HOSTED_DEADLINES
    other=cap_mod.CaptureHostedRunner({r:'postgresql://%s:x@h/db'%r for r in oo.ROLES},Journal(Path(tmp_path)/'k'),None,None,{},'192.0.2.1',None,evidence_head='1'*40,manifest_sha256='c'*64,revision='a'*40)
    assert other.capture_key!=h.capture_key and other.scope==oo.SCOPE      # the consumed mode is untouched


def test_the_hosted_job_is_admitted_only_for_its_own_authority():
    env=dict(PIPELINE_REVIEWED_SHA='a'*40,PIPELINE_EVIDENCE_HEAD='b'*40,GITHUB_SHA='a'*40,GITHUB_WORKFLOW_SHA='a'*40,GITHUB_REF='refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',GITHUB_ACTIONS='true',
             RUNNER_ENVIRONMENT='github-hosted',PIPELINE_AUTHORITY=orr.WINDOW_HOSTED_AUTHORITY)
    assert sp.admitted(env,orr.WINDOW_HOSTED_AUTHORITY) is True and not sp.admitted(env) and not sp.admitted(env,orr.CAPTURE_HOSTED_AUTHORITY)
    assert not sp.admitted(dict(env,PIPELINE_AUTHORITY=orr.CAPTURE_HOSTED_AUTHORITY),orr.WINDOW_HOSTED_AUTHORITY) and not sp.admitted(dict(env,PIPELINE_AUTHORITY=sp.HOSTED_AUTHORITY),orr.WINDOW_HOSTED_AUTHORITY)
    for bad in (dict(GITHUB_RUN_NUMBER='2'),dict(GH_TOKEN='t'),dict(DATABASE_URL='x'),dict(GITHUB_REF='refs/heads/x')):assert not sp.admitted(dict(env,**bad),orr.WINDOW_HOSTED_AUTHORITY)


# ---------------------------------------------------------------- the REAL checkout reader, this mode's own manifest
def clean_tree():
    return not subprocess.run(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,stdout=subprocess.PIPE).stdout.strip()


def test_the_real_reader_passes_the_rendered_window_binding_and_stops_every_wrong_binding_before_any_source_request():
    if not clean_tree():pytest.skip('the real reader requires a clean tracked tree (CI checkout)')
    m=render_module();rendered=m.render('window',minutes=20,evidence_head='1'*40,policy_audit=dict(events_sha256='1'*64,final_result_sha256='2'*64),control_sha256='3'*64)
    binding=dict(revision=rendered['revision'],workflow_sha256=rendered['controller_sha256'],manifest_sha256=rendered['manifest_sha256'])
    manifest=hashlib.sha256((ROOT/wd.WINDOW_MANIFEST_PATH).read_bytes()).hexdigest()
    actual=sp.actual_checkout(ROOT,manifest_path=wd.WINDOW_MANIFEST_PATH)
    assert binding['manifest_sha256']==manifest==actual['manifest_sha256'] and actual['revision']==binding['revision']
    assert sp.verify_checkout_binding(actual,binding,rendered['revision'],manifest)['manifest_sha256']==manifest
    other=lambda path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
    for bad,reviewed,job_manifest in ((dict(binding,manifest_sha256=other(sp.MANIFEST_PATH)),rendered['revision'],manifest),(dict(binding,manifest_sha256=other(cap_mod.CAPTURE_MANIFEST_PATH)),rendered['revision'],manifest),
                                      (binding,rendered['revision'],other(cap_mod.CAPTURE_MANIFEST_PATH)),(dict(binding,revision='e'*40),rendered['revision'],manifest),(binding,'e'*40,manifest),
                                      (dict(binding,workflow_sha256='b'*64),rendered['revision'],manifest),(dict(binding,extra=1),rendered['revision'],manifest)):
        with pytest.raises(Denied,match='CHECKOUT_BINDING_MISMATCH'):sp.verify_checkout_binding(actual,bad,reviewed,job_manifest)
    for wrong_reader in (sp.actual_checkout(ROOT),sp.actual_checkout(ROOT,manifest_path=cap_mod.CAPTURE_MANIFEST_PATH)):
        with pytest.raises(Denied,match='CHECKOUT_BINDING_MISMATCH'):sp.verify_checkout_binding(wrong_reader,binding,rendered['revision'],manifest)
    with pytest.raises(Denied,match='CHECKOUT_BINDING_MISMATCH'):sp.verify_checkout_binding(dict(actual,tracked_files_modified=True),binding,rendered['revision'],manifest)


def test_the_window_hosted_runner_defaults_to_its_own_manifest_reader(tmp_path,monkeypatch):
    h=hosted_runner(tmp_path);seen=[]
    monkeypatch.setattr(sp,'actual_checkout',lambda root=None,manifest_path=None:seen.append(manifest_path) or {})
    h.checkout_probe();assert seen==[wd.WINDOW_MANIFEST_PATH]


# ---------------------------------------------------------------- the restricted workflow (static)
def test_the_window_workflow_is_single_use_pinned_and_credential_separated():
    text=WF.read_text()
    assert '"$GITHUB_RUN_NUMBER" == 1' in text and '"$GITHUB_RUN_ATTEMPT" == 1' in text and 'refs/heads/master' in text and 'PIN" == "$WF"' in text and 'GITHUB_SHA' in text
    assert orr.WINDOW_HOSTED_AUTHORITY in text and orr.CAPTURE_HOSTED_AUTHORITY not in text and sp.HOSTED_AUTHORITY not in text and 'verification.ingestion_storage.window_demonstration' in text and 'capture_acceptance' not in text and 'stable_pipeline",run_name' not in text
    assert text.count('secrets.')==2 and 'INGESTION_WORKER_DATABASE_URL: ${{ secrets.INGESTION_WORKER_DATABASE_URL }}' in text and 'INGESTION_EFFECT_DATABASE_URL: ${{ secrets.INGESTION_EFFECT_DATABASE_URL }}' in text
    assert 'DATABASE_URL: ${{ secrets.DATABASE_URL' not in text and 'environment: stage4-production-canary' in text and 'permissions:\n  contents: write' in text and 'cancel-in-progress: false' in text
    assert "printf '%s\\n%s\\n%s\\n' \"$GH_TOKEN\"" in text and 'env -i' in text and 'hosted_memory_scope.sh' in text and 'timeout --kill-after=15s 2100s' in text and 'timeout-minutes: 40' in text and 'ulimit -c 0' in text and 'NOT_AUTHORISED' in text
    assert 'group: stage4-bolton-window-demonstration' in text and WF.name not in ('stage4-stable-pipeline-once.yml','stage4-form-probe-once.yml','stage4-capture-acceptance-once.yml')
    pinned=hashlib.sha256(WF.read_bytes()).hexdigest()
    assert pinned in (ROOT/'tests/test_stage4_batch_registration.py').read_text() and pinned in (ROOT/'tests/test_oldham_production_registration.py').read_text()
    for name,h in (('stage4-stable-pipeline-once.yml','8e7ed37afc870ed993bcd6aae8e4b1f59982309ae188926d1d9d25343d577b20'),('stage4-capture-acceptance-once.yml','5ea2106486e8aecb793fbf894b190cdc0af16611fa5c86f2595df022056a312a'),('stage4-form-probe-once.yml','6a947476c83928ce0cb9c70d7edcf6626f448ae468eb2bba53d93fe36ab47828')):
        assert hashlib.sha256((ROOT/'.github/workflows'/name).read_bytes()).hexdigest()==h      # the consumed workflows are byte-for-byte unchanged


# ---------------------------------------------------------------- the renderer, the manifest and the owner scripts
def test_the_renderer_builds_registrations_that_pass_every_binding_but_the_checkout():
    m=render_module()
    for mode in ('policy','window'):
        r=m.render(mode,minutes=20,evidence_head='1'*40,policy_audit=dict(events_sha256='1'*64,final_result_sha256='2'*64) if mode=='window' else None,control_sha256='3'*64 if mode=='window' else None)
        assert r['scope']==oo.WINDOW_SCOPE
        with pytest.raises(ValueError,match='CLEAN_REVIEWED_CHECKOUT'):validate(dict(r,revision='f'*40))
    with pytest.raises(ValueError,match='POLICY_CEREMONY_AUDIT_REQUIRED'):m.render('window',evidence_head='1'*40,control_sha256='3'*64)
    with pytest.raises(ValueError,match='CONTROL_SHA256_REQUIRED'):m.render('window',evidence_head='1'*40,policy_audit=dict(events_sha256='1'*64,final_result_sha256='2'*64))
    with pytest.raises(ValueError):m.render('capture',evidence_head='1'*40)


def test_the_manifest_binds_every_file_the_window_demonstration_depends_on():
    manifest=json.loads((PACKAGE/'MANIFEST.json').read_text())
    assert manifest['execution_authority']=='NONE' and manifest['modes']==[orr.WINDOW_POLICY_MODE,orr.WINDOW_MODE] and manifest['entrypoint']=='verification.ingestion_storage.operational_runner'
    bound=set(manifest['bound_paths'])
    for p in ('.github/workflows/stage4-window-demonstration-once.yml','verification/ingestion_storage/window_demonstration.py','verification/ingestion_storage/stable_pipeline.py','verification/ingestion_storage/operational_runner.py','verification/ingestion_storage/operational_owner.py',
              'docs/design/ingestion-window-demonstration-20261023/policy-window-allowance.sql','docs/design/ingestion-window-demonstration-20261023/render_registration.py','docs/design/ingestion-window-demonstration-20261023/owner-run-window.sh',
              'docs/design/ingestion-window-demonstration-20261023/owner-run-policy.sh','docs/design/ingestion-window-demonstration-20261023/base_constants.json','docs/design/ingestion-capture-acceptance-20261022/policy-capture-allowance.sql',
              'docs/design/ingestion-operational-required-20261018/successor-policy.sql','tests/window_demonstration_rehearsal.py','specifications/032-stage4-stable-credential-pipeline.md','app/ingestion/idox_adapter.py','app/scrapers/discovery_idox.py'):
        assert p in bound and (ROOT/p).is_file(),p
    assert all((ROOT/p).is_file() for p in bound) and 'docs/design/ingestion-window-demonstration-20261023/MANIFEST.json' not in bound


def test_the_owner_scripts_use_fresh_names_check_every_predecessor_and_never_take_the_credential_as_an_argument():
    for name,state,registration_file,mode in (('owner-run-policy.sh','operational-policy-window-allowance-once-20261023','operational-bolton-policy-window-allowance-registration-20261023.json','BOLTON_POLICY_WINDOW_ALLOWANCE'),
                                              ('owner-run-window.sh','operational-bolton-window-demonstration-once-20261023','operational-bolton-window-demonstration-registration-20261023.json','BOLTON_WINDOW_DEMONSTRATION')):
        text=(PACKAGE/name).read_text()
        assert 'STATE_DIRECTORY='+state in text and registration_file in text and mode in text and 'test ! -e "$STATE_ROOT/$STATE_DIRECTORY"' in text and 'VISIBLE_INTERACTIVE_TTY_REQUIRED' in text
        for h in ('35dedf6a87c3b10d4e23af54590c49bb5af4393358dd79ee9f95675be5035449','842139208adb04e180e2776790f8111216510277d9c433cbea7a1ebf3c0107a4','bc2187fb125667090f536be4031f285c2887be52af184313abeccd72c0ad8f41',
                  orr.FORM_PROBE_OUTCOME['owner_events_sha256'],orr.FORM_PROBE_OUTCOME['owner_final_result_sha256'],'e961467e5d62bfe7cdbba780ba5b9b4e4c55b630179068aabb09faa9e75edd17','508c8ffb9325b24aa7de79888799dfdb79c3afff852c26f375e79922d5e7a2ea',
                  orr.CAPTURE_ACCEPTANCE_OUTCOME['owner_events_sha256'],orr.CAPTURE_ACCEPTANCE_OUTCOME['owner_final_result_sha256'],'1daeb6b44e617855a43d4a5fdb2d3af48ba1128769a51f19f0ce3f1baf66c88f','4ca0a7eccfe5bc51cc3b70c2df1f52822160e6f87fb31917be826e80d48dd888'):assert h in text
        assert 'sha256sum --check' in text and 'you are asked once' in text and 'read -s' not in text
    window=(PACKAGE/'owner-run-window.sh').read_text()
    assert 'gh api user' in window and 'policy_ceremony_audit' in window and 'RuntimeMaxSec=4600s' in window and 'operational-policy-window-allowance-once-20261023' in window
    assert 'gh api' not in (PACKAGE/'owner-run-policy.sh').read_text().replace('# ','')
