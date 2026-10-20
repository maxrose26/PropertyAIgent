"""Owner side and static contracts of the Bolton CAPTURE ACCEPTANCE and policy-v4 ceremony (specification 032 section 13): the mechanical derivation of policy v4, registration binding, the mode's
configuration, the hosted identity and admission, the REAL checkout reader against each mode's own manifest, the restricted workflow's static contract, the renderer and the owner scripts. Offline."""
import difflib
import hashlib
import json
import re
import subprocess
from datetime import datetime,timedelta,timezone
from pathlib import Path

import pytest

from app.ingestion.ledger import Denied
from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage import stable_pipeline as sp
from verification.ingestion_storage import form_probe as fp
from verification.ingestion_storage import capture_acceptance as ca
from verification.ingestion_storage.operational_journal import Journal

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'docs/design/ingestion-capture-acceptance-20261022'
PROBE_PACKAGE=ROOT/'docs/design/ingestion-form-probe-20261021'
WF=ROOT/'.github/workflows/stage4-capture-acceptance-once.yml'
G=oo.GENERATION2_STOP
PROBE=orr.PROBE_AUTHORITY+'_PROBE'
CAP=orr.CAPTURE_AUTHORITY+'_CAPTURE'
SCR=orr.CAPTURE_AUTHORITY+'_SCREEN'


def render_module():
    import importlib.util
    spec=importlib.util.spec_from_file_location('render_capture',PACKAGE/'render_registration.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


# ---------------------------------------------------------------- policy v4 is v3 plus exactly the two names and the cap exemption for ONLY those names
def derive_v4(v3):
    header_end=v3.index('BEGIN;')
    out=v3
    out=out.replace("  OR (authority='%s'\n"%PROBE,"  OR (authority IN ('%s','%s','%s')\n"%(PROBE,CAP,SCR))
    out=out.replace("OR coalesce(a='%s' AND"%PROBE,"OR coalesce(a IN ('%s','%s','%s') AND"%(PROBE,CAP,SCR))
    out=out.replace("OR ctl->'bolton_exceptions' ? a OR (SELECT count(*) FROM jsonb_object_keys(coalesce(ctl->'bolton_exceptions','{}'::jsonb)))>=3\n",
                    "OR ctl->'bolton_exceptions' ? a OR ((SELECT count(*) FROM jsonb_object_keys(coalesce(ctl->'bolton_exceptions','{}'::jsonb)))>=3 AND NOT coalesce(a IN ('%s','%s') AND (ctl->>'hard_stop_generation')::integer=2,false))\n"%(CAP,SCR))
    return out[header_end:]


def test_policy_v4_body_is_the_mechanical_derivation_of_v3_and_differs_in_exactly_three_lines():
    v3=(PROBE_PACKAGE/'policy-generation2.sql').read_text();v4=(PACKAGE/'policy-capture-allowance.sql').read_text()
    assert v4[v4.index('BEGIN;'):]==derive_v4(v3)
    changed=[l for l in difflib.unified_diff(v3[v3.index('BEGIN;'):].splitlines(),v4[v4.index('BEGIN;'):].splitlines(),lineterm='',n=0) if l[:1] in '+-' and l[:3] not in ('+++','---')]
    assert len(changed)==6      # three lines removed, three added: nothing else differs
    body=v4[v4.index('BEGIN;'):]      # the header comment names the allowances too; the executable body is what is counted
    assert body.count(CAP)==body.count(SCR)==3 and body.count(PROBE)==2 and G['stop_state_sha256'] in body and G['manual_stop'] in body
    assert "AND NOT coalesce(a IN ('%s','%s') AND (ctl->>'hard_stop_generation')::integer=2,false)"%(CAP,SCR) in body and '>=3' in body      # the cap stays, with an exemption for exactly these two names


def test_the_two_new_names_are_distinct_from_every_historical_authority_and_the_inventories_differ_by_exactly_the_two_functions():
    assert len({PROBE,CAP,SCR,orr.PIPELINE_AUTHORITY+'_CAPTURE',orr.PIPELINE_AUTHORITY+'_SCREEN'})==5
    v3=oo.Owner.generation2_inventory();v4=oo.Owner.capture_inventory()
    assert set(v3)==set(v4) and sorted(k for k in v3 if v3[k]!=v4[k])==['ingestion_bolton_allowed','ingestion_register_bolton_exception']


# ---------------------------------------------------------------- constants and timing
def test_the_capture_binding_is_the_accepted_pipelines_with_only_the_generation_2_stop_state_changed():
    cb=orr.CAPTURE_BINDING;pb=orr.PIPELINE_BINDING
    for k in ('valid_until','grant_minutes','screening_grant_minutes','poll_seconds','capture_wait_seconds','screening_wait_seconds','qualification'):assert cb[k]==pb[k]
    assert cb['hard_stop_generation']==2 and cb['manual_stop']==G['manual_stop'] and cb['last_hard_stop']==G['last_hard_stop'] and cb['stop_state_sha256']==G['stop_state_sha256']
    assert cb['hosted_workflow']==orr.CAPTURE_WORKFLOW and cb['hosted_authority']==orr.CAPTURE_HOSTED_AUTHORITY
    assert cb['source']['form_requests']==1 and cb['source']['total_requests']==10 and cb['source']['redirects']==0 and cb['source']['retries']==0
    assert orr.CAPTURE_STATE not in (orr.PIPELINE_STATE,orr.PROBE_STATE) and orr.CAPTURE_POLICY_STATE not in (orr.POLICY_STATE,orr.OBSERVER_STATE)


def test_the_pipeline_timing_invariants_apply_unchanged_to_the_capture_mode():
    d=orr.PIPELINE_DEADLINES;t=orr.PIPELINE_TIMING
    assert d['job']+d['diagnostic_window']<=t['work_seconds'] and t['work_seconds']+d['diagnostic_window']<=d['diagnostic_total']<=t['active_seconds']-t['report_seconds']
    assert d['admin_pre']<d['admin_total']<d['admin_diagnostic']<=d['diagnostic_total'] and t['input_seconds']+t['active_seconds']+30>=t['outer_seconds']
    cb=orr.CAPTURE_BINDING
    assert cb['capture_wait_seconds']+cb['screening_wait_seconds']+120<=d['admin_pre'] and cb['grant_minutes']*60>=cb['capture_wait_seconds']


# ---------------------------------------------------------------- registration validators
def registration(mode):
    base=json.loads((PACKAGE/'base_constants.json').read_text());base={k:v for k,v in base.items() if not k.startswith('_')};base.pop('limits',None)
    common=dict(base,expires_at=(datetime.now(timezone.utc)+timedelta(minutes=20)).replace(microsecond=0).isoformat(),revision='a'*40,tree='b'*40,hashes={},controller_sha256='c'*64,ca_sha256='d'*64,manifest_sha256='e'*64,evidence_head='1'*40)
    if mode=='policy':
        return dict(common,mode=orr.CAPTURE_POLICY_MODE,authority=orr.CAPTURE_POLICY_AUTHORITY,evidence_directory=orr.CAPTURE_EVIDENCE_DIRECTORY,predecessor=orr.CAPTURE_POLICY_PREDECESSOR,state_directory=orr.CAPTURE_POLICY_STATE,
                    execution_authority='NONE',risk_application='THIS_FINITE_POLICY_CAPTURE_ALLOWANCE_INSTALLATION_ONLY',owner_limits=dict(connections=list(orr.CAPTURE_POLICY_OWNER_LIMITS['connections']),commands=list(orr.CAPTURE_POLICY_OWNER_LIMITS['commands'])),
                    policy=dict(file=str(oo.GENERATION2_CAPTURE_POLICY),named_allowances=[CAP,SCR],baseline=G,cap='UNCHANGED_EXCEPT_FOR_THE_TWO_NAMED_ALLOWANCES'),
                    execution=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=orr.CAPTURE_POLICY_STATE),approval='X')
    return dict(common,mode=orr.CAPTURE_MODE,authority=orr.CAPTURE_AUTHORITY,evidence_directory=orr.CAPTURE_EVIDENCE_DIRECTORY,predecessor=orr.CAPTURE_PREDECESSOR,state_directory=orr.CAPTURE_STATE,
                execution_authority='OWNER_GRANT_AND_EXCEPTION_FOR_THE_HOSTED_RESTRICTED_JOB',risk_application='THIS_FINITE_BOLTON_CAPTURE_ACCEPTANCE_ONCE',capture=orr.CAPTURE_BINDING,
                owner_limits=dict(connections=list(orr.PIPELINE_OWNER_LIMITS['connections']),commands=list(orr.PIPELINE_OWNER_LIMITS['commands'])),policy_ceremony_audit=dict(events_sha256='1'*64,final_result_sha256='2'*64),control_sha256='3'*64,
                execution=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=orr.CAPTURE_STATE),approval='X')


def validate(r):
    body=json.dumps(r,sort_keys=True,indent=1).encode();return orr.validate_registration(body,hashlib.sha256(body).hexdigest())


@pytest.mark.parametrize('mode,binding_error',[('policy','BOLTON_CAPTURE_POLICY_BINDING'),('capture','BOLTON_CAPTURE_ACCEPTANCE_BINDING')])
def test_the_validators_bind_each_mode_exactly(mode,binding_error):
    with pytest.raises(ValueError,match='CLEAN_REVIEWED_CHECKOUT'):validate(registration(mode))      # every binding passes; only the (deliberately wrong) checkout identity stops it
    tampers={'policy':[dict(execution_authority='X'),dict(state_directory=orr.PIPELINE_STATE),dict(owner_limits=dict(connections=[9,9],commands=[34,40,48])),dict(policy=dict(file='x',named_allowances=[CAP,SCR],baseline=G)),
                       dict(policy=dict(file=str(oo.GENERATION2_CAPTURE_POLICY),named_allowances=[CAP,SCR,'ANY_OTHER'],baseline=G,cap='UNCHANGED_EXCEPT_FOR_THE_TWO_NAMED_ALLOWANCES')),dict(pipeline={'x':1}),dict(capture=orr.CAPTURE_BINDING)],
             'capture':[dict(capture=dict(orr.CAPTURE_BINDING,grant_minutes=999)),dict(capture=dict(orr.CAPTURE_BINDING,hard_stop_generation=1)),dict(execution_authority='NONE'),dict(state_directory=orr.PIPELINE_STATE),
                        dict(evidence_directory=orr.PROBE_EVIDENCE_DIRECTORY),dict(owner_limits=dict(connections=[9,9],commands=[56,80,96])),dict(policy_ceremony_audit=None),dict(policy_ceremony_audit=dict(events_sha256='short',final_result_sha256='2'*64)),
                        dict(control_sha256='short'),dict(control_sha256=None),dict(predecessor=dict(orr.CAPTURE_PREDECESSOR,observed_stop=dict(G,hard_stop_generation=1))),dict(pipeline=orr.PIPELINE_BINDING),dict(probe=orr.PROBE_BINDING)]}[mode]
    for tamper in tampers:
        with pytest.raises(ValueError,match=binding_error):validate(dict(registration(mode),**tamper))


def test_the_expiry_caps_and_authorities_are_separate_per_mode():
    long_policy=dict(registration('policy'),expires_at=(datetime.now(timezone.utc)+timedelta(minutes=45)).replace(microsecond=0).isoformat())
    with pytest.raises(ValueError,match='ORIGINAL_OPERATIONAL_EXPIRY'):validate(long_policy)      # policy: at most 30 minutes
    two_hours=dict(registration('capture'),expires_at=(datetime.now(timezone.utc)+timedelta(minutes=110)).replace(microsecond=0).isoformat())
    with pytest.raises(ValueError,match='CLEAN_REVIEWED_CHECKOUT'):validate(two_hours)      # capture: up to two hours, as the pipeline
    three_hours=dict(registration('capture'),expires_at=(datetime.now(timezone.utc)+timedelta(minutes=190)).replace(microsecond=0).isoformat())
    with pytest.raises(ValueError,match='ORIGINAL_OPERATIONAL_EXPIRY'):validate(three_hours)
    for other in (orr.PIPELINE_AUTHORITY,orr.PROBE_AUTHORITY,orr.CAPTURE_POLICY_AUTHORITY):
        with pytest.raises(ValueError,match='EXACT_OPERATIONAL_APPROVAL_REQUIRED'):validate(dict(registration('capture'),authority=other))
    with pytest.raises(ValueError,match='EXACT_OPERATIONAL_APPROVAL_REQUIRED'):validate(dict(registration('policy'),authority=orr.POLICY_AUTHORITY))


def runner_for(mode,tmp_path):
    r=registration(mode);Path(tmp_path).mkdir(parents=True,exist_ok=True)
    return orr.Runner(r,Journal(Path(tmp_path)/mode),lambda:None,source_reader=None,github=None,url_factory=None)


def test_the_capture_mode_runner_is_bound_to_the_v4_inventory_the_generation_2_stop_and_the_pipelines_limits(tmp_path):
    r=runner_for('capture',tmp_path)
    assert r.pipeline_mode and r.capture_mode and not r.probe_mode and not r.policy_mode and r.authority==orr.CAPTURE_AUTHORITY
    o=r.owner
    assert o.permitted_policy_states==('GENERATION2_CAPTURE_POLICY_APPLIED',) and o.stop_manual==G['manual_stop'] and o.stop_sha==G['stop_state_sha256'] and o.expected_generation==2 and o.apply_policy is False
    assert r.deadlines==orr.PIPELINE_DEADLINES and o.limits==orr.PIPELINE_OWNER_LIMITS
    p=runner_for('policy',tmp_path)
    assert p.policy_mode and p.capture_policy_mode and not p.pipeline_mode and p.deadlines==orr.POLICY_DEADLINES and p.owner.limits==orr.POLICY_OWNER_LIMITS and p.owner.apply_policy is False
    stable=orr.Runner(dict(registration('capture'),mode=orr.PIPELINE_MODE),Journal(Path(tmp_path)/'stable'),lambda:None,source_reader=None,github=None,url_factory=None)
    assert stable.capture_mode is False and stable.authority==orr.PIPELINE_AUTHORITY and stable.owner.expected_generation==1 and stable.owner.stop_manual=='STORAGE_TEST_STOP' and stable.owner.permitted_policy_states==('SUCCESSOR_POLICY_APPLIED',)


def test_the_post_probe_baseline_requires_the_consumed_probe_entries_revoked_and_neither_new_name_present(tmp_path):
    r=runner_for('policy',tmp_path)
    def record(**over):
        ctl=dict(global_stop=oo.STOP,manual_stop=G['manual_stop'],last_hard_stop=G['last_hard_stop'],hard_stop_generation=2,
                 grants={PROBE:dict(expires_at=0)},bolton_exceptions={PROBE:dict(expires_at=0,transport='REQUESTS_IDOX',hard_stop_generation=2,grant_binding={})})
        ctl.update(over)
        p=oo.Owner.project_control(ctl,1.0e9);p['stop_state_sha256']=G['stop_state_sha256'];return dict(projection=p)
    assert r.require_post_probe_baseline(record())['hard_stop_generation']==2
    for bad in (dict(manual_stop='OTHER'),dict(hard_stop_generation=3),dict(grants={}),dict(grants={PROBE:dict(expires_at=2.0e9)}),dict(bolton_exceptions={}),dict(grants={PROBE:dict(expires_at=0),CAP:dict(expires_at=0)}),
                dict(bolton_exceptions={PROBE:dict(expires_at=0),SCR:dict(expires_at=0)}),dict(global_stop={})):
        with pytest.raises(Exception,match='OBSERVED_BASELINE_CHANGED'):r.require_post_probe_baseline(record(**bad))
    stale=record();stale['projection']['stop_state_sha256']='0'*64
    with pytest.raises(Exception,match='OBSERVED_BASELINE_CHANGED'):r.require_post_probe_baseline(stale)


def test_every_credential_mode_validates_the_hidden_input_before_consuming_the_registration():
    assert orr.CAPTURE_POLICY_MODE in orr.INPUT_PRECHECKED_MODES and orr.CAPTURE_MODE in orr.INPUT_PRECHECKED_MODES


# ---------------------------------------------------------------- the hosted half
def hosted_runner(tmp_path):
    urls={r:'postgresql://%s:x@h/db'%r for r in oo.ROLES};Path(tmp_path).mkdir(parents=True,exist_ok=True)
    return ca.CaptureHostedRunner(urls,Journal(Path(tmp_path)/'j'),None,None,{},'192.0.2.1',None,evidence_head='1'*40,manifest_sha256='c'*64,revision='a'*40)


def test_the_hosted_identity_equals_the_owners_and_reads_only_its_own_allowance(tmp_path):
    h=hosted_runner(tmp_path)
    root=oo.item(dict(subject=oo.SCOPE,task='DISCOVERY',contract=orr.CONTRACT,revision='c'*64),max_attempts=1,limits=dict(oo.DEFAULT_LIMITS,requests=10,bytes=3000000,rows=60,pages=6))
    assert h.capture_key==root['key'] and h.execution==dict(revision='a'*40,manifest_sha256='c'*64,capture_key=root['key'],initial_evidence_head='1'*40,authority=orr.CAPTURE_AUTHORITY)
    assert h.GRANT_SUFFIX=='_CAPTURE' and h.authority+h.GRANT_SUFFIX==CAP      # the exact name policy v4 recognises
    assert h.r['evidence_directory']==orr.CAPTURE_EVIDENCE_DIRECTORY and h.MANIFEST==ca.CAPTURE_MANIFEST_PATH and h.deadlines==sp.HOSTED_DEADLINES
    assert sp.HostedRunner.AUTHORITY==orr.PIPELINE_AUTHORITY and sp.HostedRunner.EVIDENCE==sp.EVIDENCE_DIRECTORY and sp.HostedRunner.MANIFEST==sp.MANIFEST_PATH      # the accepted pipeline is unchanged


def test_the_hosted_job_is_admitted_only_for_its_own_authority():
    env=dict(PIPELINE_REVIEWED_SHA='a'*40,PIPELINE_EVIDENCE_HEAD='b'*40,GITHUB_SHA='a'*40,GITHUB_WORKFLOW_SHA='a'*40,GITHUB_REF='refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',GITHUB_ACTIONS='true',
             RUNNER_ENVIRONMENT='github-hosted',PIPELINE_AUTHORITY=orr.CAPTURE_HOSTED_AUTHORITY)
    assert sp.admitted(env,orr.CAPTURE_HOSTED_AUTHORITY) is True and not sp.admitted(env) and not sp.admitted(env,fp.PROBE_HOSTED_AUTHORITY)
    assert not sp.admitted(dict(env,PIPELINE_AUTHORITY=sp.HOSTED_AUTHORITY),orr.CAPTURE_HOSTED_AUTHORITY) and not sp.admitted(dict(env,PIPELINE_AUTHORITY=fp.PROBE_HOSTED_AUTHORITY),orr.CAPTURE_HOSTED_AUTHORITY)
    for bad in (dict(GITHUB_RUN_NUMBER='2'),dict(GH_TOKEN='t'),dict(DATABASE_URL='x'),dict(GITHUB_REF='refs/heads/x')):assert not sp.admitted(dict(env,**bad),orr.CAPTURE_HOSTED_AUTHORITY)


# ---------------------------------------------------------------- the REAL checkout reader, each mode's own manifest
def clean_tree():
    return not subprocess.run(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,stdout=subprocess.PIPE).stdout.strip()


def test_the_real_reader_passes_the_rendered_capture_binding_and_stops_every_wrong_binding_before_any_source_request():
    if not clean_tree():pytest.skip('the real reader requires a clean tracked tree (CI checkout)')
    m=render_module();rendered=m.render('capture',minutes=20,evidence_head='1'*40,policy_audit=dict(events_sha256='1'*64,final_result_sha256='2'*64),control_sha256='3'*64)
    binding=dict(revision=rendered['revision'],workflow_sha256=rendered['controller_sha256'],manifest_sha256=rendered['manifest_sha256'])      # exactly what the owner stores with the grant
    manifest=hashlib.sha256((ROOT/ca.CAPTURE_MANIFEST_PATH).read_bytes()).hexdigest()
    actual=sp.actual_checkout(ROOT,manifest_path=ca.CAPTURE_MANIFEST_PATH)
    assert binding['manifest_sha256']==manifest==actual['manifest_sha256'] and actual['revision']==binding['revision']
    assert sp.verify_checkout_binding(actual,binding,rendered['revision'],manifest)['manifest_sha256']==manifest
    other=lambda path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
    for bad,reviewed,job_manifest in ((dict(binding,manifest_sha256=other(sp.MANIFEST_PATH)),rendered['revision'],manifest),
                                      (dict(binding,manifest_sha256=other(fp.PROBE_MANIFEST_PATH)),rendered['revision'],manifest),
                                      (binding,rendered['revision'],other(sp.MANIFEST_PATH)),
                                      (dict(binding,revision='e'*40),rendered['revision'],manifest),(binding,'e'*40,manifest),
                                      (dict(binding,workflow_sha256='b'*64),rendered['revision'],manifest),(dict(binding,extra=1),rendered['revision'],manifest)):
        with pytest.raises(Denied,match='CHECKOUT_BINDING_MISMATCH'):sp.verify_checkout_binding(actual,bad,reviewed,job_manifest)
    for wrong_reader in (sp.actual_checkout(ROOT),sp.actual_checkout(ROOT,manifest_path=fp.PROBE_MANIFEST_PATH)):      # a hosted job that hashed another mode's manifest
        with pytest.raises(Denied,match='CHECKOUT_BINDING_MISMATCH'):sp.verify_checkout_binding(wrong_reader,binding,rendered['revision'],manifest)
    with pytest.raises(Denied,match='CHECKOUT_BINDING_MISMATCH'):sp.verify_checkout_binding(dict(actual,tracked_files_modified=True),binding,rendered['revision'],manifest)


def test_the_capture_hosted_runner_defaults_to_its_own_manifest_reader(tmp_path,monkeypatch):
    h=hosted_runner(tmp_path);seen=[]
    monkeypatch.setattr(sp,'actual_checkout',lambda root=None,manifest_path=None:seen.append(manifest_path) or {})
    h.checkout_probe();assert seen==[ca.CAPTURE_MANIFEST_PATH]
    stable=sp.HostedRunner({r:'postgresql://%s:x@h/db'%r for r in oo.ROLES},Journal(Path(tmp_path)/'s'),None,None,{},'192.0.2.1',None,evidence_head='1'*40,manifest_sha256='c'*64,revision='a'*40)
    seen.clear();stable.checkout_probe();assert seen==[sp.MANIFEST_PATH]      # the stable pipeline keeps reading its own


# ---------------------------------------------------------------- the restricted workflow (static)
def test_the_capture_workflow_is_single_use_pinned_and_credential_separated():
    text=WF.read_text()
    assert '"$GITHUB_RUN_NUMBER" == 1' in text and '"$GITHUB_RUN_ATTEMPT" == 1' in text and 'refs/heads/master' in text and 'PIN" == "$WF"' in text and 'GITHUB_SHA' in text
    assert orr.CAPTURE_HOSTED_AUTHORITY in text and sp.HOSTED_AUTHORITY not in text and fp.PROBE_HOSTED_AUTHORITY not in text and 'verification.ingestion_storage.capture_acceptance' in text and 'stable_pipeline",run_name' not in text
    assert text.count('secrets.')==2 and 'INGESTION_WORKER_DATABASE_URL: ${{ secrets.INGESTION_WORKER_DATABASE_URL }}' in text and 'INGESTION_EFFECT_DATABASE_URL: ${{ secrets.INGESTION_EFFECT_DATABASE_URL }}' in text
    assert 'DATABASE_URL: ${{ secrets.DATABASE_URL' not in text and 'environment: stage4-production-canary' in text and 'permissions:\n  contents: write' in text and 'cancel-in-progress: false' in text
    assert "printf '%s\\n%s\\n%s\\n' \"$GH_TOKEN\"" in text and 'env -i' in text and 'hosted_memory_scope.sh' in text and 'timeout --kill-after=15s' in text and 'ulimit -c 0' in text and 'NOT_AUTHORISED' in text
    assert 'group: stage4-bolton-capture-acceptance' in text and WF.name not in ('stage4-stable-pipeline-once.yml','stage4-form-probe-once.yml')      # a fresh workflow, so its run number is one
    pinned=hashlib.sha256(WF.read_bytes()).hexdigest()
    assert pinned in (ROOT/'tests/test_stage4_batch_registration.py').read_text() and pinned in (ROOT/'tests/test_oldham_production_registration.py').read_text()      # the exclusivity guards pin its exact bytes
    stable_text=(ROOT/'.github/workflows/stage4-stable-pipeline-once.yml').read_text()
    assert hashlib.sha256((ROOT/'.github/workflows/stage4-stable-pipeline-once.yml').read_bytes()).hexdigest()=='8e7ed37afc870ed993bcd6aae8e4b1f59982309ae188926d1d9d25343d577b20' and 'capture_acceptance' not in stable_text


# ---------------------------------------------------------------- the renderer, the manifest and the owner scripts
def test_the_renderer_builds_registrations_that_pass_every_binding_but_the_checkout():
    m=render_module()
    for mode in ('policy','capture'):
        r=m.render(mode,minutes=20,evidence_head='1'*40,policy_audit=dict(events_sha256='1'*64,final_result_sha256='2'*64) if mode=='capture' else None,control_sha256='3'*64 if mode=='capture' else None)
        with pytest.raises(ValueError,match='CLEAN_REVIEWED_CHECKOUT'):validate(dict(r,revision='f'*40))
    with pytest.raises(ValueError,match='POLICY_CEREMONY_AUDIT_REQUIRED'):m.render('capture',evidence_head='1'*40,control_sha256='3'*64)
    with pytest.raises(ValueError,match='CONTROL_SHA256_REQUIRED'):m.render('capture',evidence_head='1'*40,policy_audit=dict(events_sha256='1'*64,final_result_sha256='2'*64))
    with pytest.raises(ValueError):m.render('probe',evidence_head='1'*40)


def test_the_manifest_binds_every_file_the_capture_acceptance_depends_on():
    manifest=json.loads((PACKAGE/'MANIFEST.json').read_text())
    assert manifest['execution_authority']=='NONE' and manifest['modes']==[orr.CAPTURE_POLICY_MODE,orr.CAPTURE_MODE] and manifest['entrypoint']=='verification.ingestion_storage.operational_runner'
    bound=set(manifest['bound_paths'])
    for p in ('.github/workflows/stage4-capture-acceptance-once.yml','verification/ingestion_storage/capture_acceptance.py','verification/ingestion_storage/stable_pipeline.py','verification/ingestion_storage/operational_runner.py','verification/ingestion_storage/operational_owner.py',
              'docs/design/ingestion-capture-acceptance-20261022/policy-capture-allowance.sql','docs/design/ingestion-capture-acceptance-20261022/render_registration.py','docs/design/ingestion-capture-acceptance-20261022/owner-run-capture.sh',
              'docs/design/ingestion-capture-acceptance-20261022/owner-run-policy.sh','docs/design/ingestion-capture-acceptance-20261022/base_constants.json','docs/design/ingestion-form-probe-20261021/policy-generation2.sql',
              'docs/design/ingestion-operational-required-20261018/successor-policy.sql','tests/capture_acceptance_rehearsal.py','specifications/032-stage4-stable-credential-pipeline.md'):
        assert p in bound and (ROOT/p).is_file()
    assert all((ROOT/p).is_file() for p in bound) and 'docs/design/ingestion-capture-acceptance-20261022/MANIFEST.json' not in bound      # a manifest never binds itself


def test_the_owner_scripts_use_fresh_names_check_the_predecessors_and_never_take_the_credential_as_an_argument():
    for name,state,registration_file,mode in (('owner-run-policy.sh','operational-policy-capture-allowance-once-20261022','operational-bolton-policy-capture-allowance-registration-20261022.json','BOLTON_POLICY_CAPTURE_ALLOWANCE'),
                                              ('owner-run-capture.sh','operational-bolton-capture-acceptance-once-20261022','operational-bolton-capture-acceptance-registration-20261022.json','BOLTON_CAPTURE_ACCEPTANCE')):
        text=(PACKAGE/name).read_text()
        assert 'STATE_DIRECTORY='+state in text and registration_file in text and mode in text and 'test ! -e "$STATE_ROOT/$STATE_DIRECTORY"' in text and 'VISIBLE_INTERACTIVE_TTY_REQUIRED' in text
        for h in ('35dedf6a87c3b10d4e23af54590c49bb5af4393358dd79ee9f95675be5035449','842139208adb04e180e2776790f8111216510277d9c433cbea7a1ebf3c0107a4','bc2187fb125667090f536be4031f285c2887be52af184313abeccd72c0ad8f41',
                  orr.FORM_PROBE_OUTCOME['owner_events_sha256'],orr.FORM_PROBE_OUTCOME['owner_final_result_sha256'],'e961467e5d62bfe7cdbba780ba5b9b4e4c55b630179068aabb09faa9e75edd17','508c8ffb9325b24aa7de79888799dfdb79c3afff852c26f375e79922d5e7a2ea'):assert h in text
        assert 'sha256sum --check' in text and 'you are asked once' in text and 'read -s' not in text
    cap=(PACKAGE/'owner-run-capture.sh').read_text()
    assert 'gh api user' in cap and 'policy_ceremony_audit' in cap and 'RuntimeMaxSec=4600s' in cap and 'operational-policy-capture-allowance-once-20261022' in cap
    assert 'gh api' not in (PACKAGE/'owner-run-policy.sh').read_text().replace('# ','')
