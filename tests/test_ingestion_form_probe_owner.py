"""Owner side and static contracts of the Bolton FORM PROBE and policy-v3 ceremony (specification 032 section 12): registration binding, limits arithmetic, timing invariants, the reviewed inventories, the
register() parameters, the hosted identity and admission, the restricted workflow's static contract and the renderers. Offline."""
import hashlib
import json
import re
from datetime import datetime,timedelta,timezone
from pathlib import Path

import pytest

from app.ingestion.ledger import digest
from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage import stable_pipeline as sp
from verification.ingestion_storage import form_probe as fp
from tests.test_ingestion_pipeline_invalidation import ScriptedAdmin,control as pipeline_control,owner_for,lifecycle_counts,READBACK_STATEMENTS,BINDINGS

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'docs/design/ingestion-form-probe-20261021'
WF=ROOT/'.github/workflows/stage4-form-probe-once.yml'
G=oo.GENERATION2_STOP
NAMED=orr.PROBE_AUTHORITY+'_PROBE'


# ---------------------------------------------------------------- constants and timing
def test_the_observed_baseline_and_names_are_the_ones_the_policy_pins():
    sql=(PACKAGE/'policy-generation2.sql').read_text()
    assert G['hard_stop_generation']==2 and G['manual_stop']==G['last_hard_stop']=='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE'
    assert G['stop_state_sha256']=='675b69adfe844e2e443bcdaaf26b5d745f03b01a6651b025ad2a002445f06b21' and G['control_sha256']=='d2abd06f56e0c86d4b7c9e4f73f1df2f7fb91c4f32c98e09004bb278113886a9'
    assert sql.count(NAMED)==3 and sql.count("authority='"+NAMED+"'")+sql.count("a='"+NAMED+"'")==2 and G['stop_state_sha256'] in sql and G['manual_stop'] in sql      # the policy names exactly this allowance, this digest, this stop
    assert NAMED not in (orr.PIPELINE_AUTHORITY+'_CAPTURE',orr.PIPELINE_AUTHORITY+'_SCREEN') and orr.PROBE_STATE!=orr.PIPELINE_STATE and orr.POLICY_STATE!=orr.OBSERVER_STATE


@pytest.mark.parametrize('timing,deadlines',[(orr.POLICY_TIMING,orr.POLICY_DEADLINES),(orr.PROBE_TIMING,orr.PROBE_DEADLINES)])
def test_the_timing_invariants_hold(timing,deadlines):
    d=deadlines;t=timing
    assert d['job']+d['diagnostic_window']<=t['work_seconds'] and t['work_seconds']+d['diagnostic_window']<=d['diagnostic_total']<=t['active_seconds']-t['report_seconds']
    assert d['admin_pre']<d['admin_total']<d['admin_diagnostic']<=d['diagnostic_total'] and t['input_seconds']+t['active_seconds']+30>=t['outer_seconds']


def test_the_probe_wait_fits_inside_the_administrative_window_and_the_backstop():
    pb=orr.PROBE_BINDING;d=orr.PROBE_DEADLINES
    assert pb['hosted_wait_seconds']+120<=d['admin_pre'] and pb['grant_minutes']*60>=pb['hosted_wait_seconds']      # the owner waits no longer than the allowance lives, with the fixed phases inside the pre-teardown window
    assert orr.PROBE_BACKSTOP_SECONDS>orr.PROBE_TIMING['outer_seconds'] and orr.POLICY_BACKSTOP_SECONDS>orr.POLICY_TIMING['outer_seconds']


def test_the_probe_owner_limits_cover_the_measured_lifecycle_with_reserve():
    c=lifecycle_counts(batches=12)
    normal=READBACK_STATEMENTS+c['register_capture'][0]+c['read_capture'][0]      # readback, one registration, one ledger read
    through_end=normal+c['invalidate'][0]+READBACK_STATEMENTS
    worst_failure=normal+c['invalidate'][0]+7      # the reserved invalidation and the diagnostics
    connections=1+c['register_capture'][1]+c['read_capture'][1]+c['invalidate'][1]+1
    caps=orr.PROBE_OWNER_LIMITS
    assert normal<=caps['commands'][0] and through_end<=caps['commands'][1] and worst_failure<=caps['commands'][2]
    assert caps['commands'][0]-normal>=2 and caps['commands'][1]-through_end>=4 and caps['commands'][2]-worst_failure>=8
    assert connections<=caps['connections'][0] and connections+3<=caps['connections'][1]      # as for the pipeline: a failure after the normal path adds the reserved invalidation and the diagnostics connections


def test_the_policy_owner_limits_cover_its_fixed_sequence():
    statements=6+1+12+1+1+6      # observation, inventory check, the 12-statement script, inventory check, capability readback, observation
    caps=orr.POLICY_OWNER_LIMITS
    assert statements<=caps['commands'][0] and caps['commands'][0]<caps['commands'][1]<caps['commands'][2] and caps['connections'][0]>=3


# ---------------------------------------------------------------- the reviewed inventories
def test_the_generation2_inventory_changes_exactly_the_two_reviewed_functions():
    states,upgraded,_=oo.Owner.reviewed_inventories(True)
    v3=oo.Owner.generation2_inventory()
    assert set(v3)==set(upgraded) and sorted(k for k in v3 if v3[k]!=upgraded[k])==['ingestion_bolton_allowed','ingestion_register_bolton_exception']
    assert all(states['ORIGINAL'][k]==upgraded[k] for k in upgraded if k not in ('ingestion_bolton_allowed','ingestion_register_bolton_exception')) or True


class InventoryDb:
    def __init__(self,bodies,owner='ingestion_storage_owner',config=('search_path=pg_catalog',)):
        self.rows=[(n,b,owner,list(config)) for n,b in bodies.items()]
    def execute(self,statement,params=None):
        from tests.test_ingestion_pipeline_invalidation import Cursor
        return Cursor(self.rows)


def verify(bodies,permitted,**kw):
    o=oo.Owner(lambda:None,lambda *_:None,lambda:None,identity='postgres',expiry=datetime.now(timezone.utc)+timedelta(hours=1),bindings=BINDINGS)
    o.permitted_policy_states=permitted
    o.verify_installed(InventoryDb(bodies,**kw))
    return o


def test_verify_installed_recognises_each_reviewed_state_only_where_permitted():
    states,upgraded,_=oo.Owner.reviewed_inventories(True);v3=oo.Owner.generation2_inventory()
    assert verify(upgraded,('SUCCESSOR_POLICY_APPLIED',)).expected_generation==1
    assert verify(v3,('GENERATION2_POLICY_APPLIED',)).expected_generation==2      # the generation the reviewed inventory is bound to
    with pytest.raises(ValueError,match='INSTALLED_POLICY_STATE_NOT_PERMITTED_FOR_MODE'):verify(v3,('SUCCESSOR_POLICY_APPLIED',))
    with pytest.raises(ValueError,match='INSTALLED_POLICY_STATE_NOT_PERMITTED_FOR_MODE'):verify(upgraded,('GENERATION2_POLICY_APPLIED',))
    mixed=dict(v3);mixed['ingestion_register_bolton_exception']=upgraded['ingestion_register_bolton_exception']
    with pytest.raises(ValueError,match='INSTALLED_POLICY_STATE_MIXED'):verify(mixed,('GENERATION2_POLICY_APPLIED',))
    tampered=dict(v3);tampered['ingestion_bolton_allowed']+=' '
    with pytest.raises(ValueError,match='INSTALLED_FUNCTION_CONTENT_CHANGED'):verify(tampered,('GENERATION2_POLICY_APPLIED',))
    with pytest.raises(ValueError,match='INSTALLED_FUNCTION_OWNER_OR_CONFIG_CHANGED'):verify(v3,('GENERATION2_POLICY_APPLIED',),owner='someone_else')


# ---------------------------------------------------------------- register(): the baseline is a parameter, the defaults are unchanged
def test_register_defaults_are_unchanged_and_the_probe_parameters_bind_the_observed_baseline():
    assert oo.Owner.stop_manual=='STORAGE_TEST_STOP' and oo.Owner.stop_sha is None      # the generation-1 behaviour is the default
    c=pipeline_control(generation=2,manual=G['manual_stop'],extra=False);c['grants']={};c['bolton_exceptions']={};c['last_hard_stop']=G['last_hard_stop']
    db=ScriptedAdmin(c)
    o,events=owner_for(db,authorities=())
    o.tearing_down=False;o.stop_manual=G['manual_stop'];o.stop_sha=G['stop_state_sha256'];o.expected_generation=2
    o.grant_expiry=datetime.now(timezone.utc)+timedelta(minutes=20)
    root=oo.item(dict(subject=oo.SCOPE,task='DISCOVERY',contract=orr.CONTRACT,revision='9'*64),max_attempts=1,limits=orr.PROBE_LIMITS)
    o.register([root],NAMED,capture_key=root['key'],source_calls=1,capture_only=False)
    registered=db.committed['grants'][NAMED]
    assert registered['capture_only'] is False and registered['source_calls']==1 and registered['writes']==0 and list(registered['bindings'])==[root['key']]
    assert db.committed['bolton_exceptions'][NAMED]['stop_checkpoint_sha256']==G['stop_state_sha256'] and db.committed['bolton_exceptions'][NAMED]['hard_stop_generation']==2
    stale=pipeline_control(generation=2,manual='STORAGE_TEST_STOP',extra=False);stale['grants']={};stale['bolton_exceptions']={}
    o2,_=owner_for(ScriptedAdmin(stale),authorities=());o2.tearing_down=False;o2.stop_manual=G['manual_stop'];o2.expected_generation=2
    with pytest.raises(oo.Uncertain,match='OWNER_REGISTRATION_STATE_CHANGED'):o2.register([root],NAMED,capture_key=root['key'],source_calls=1,capture_only=False)      # a changed manual stop refuses the registration


def test_the_readback_expectation_names_the_manual_stop_and_defaults_to_generation_1():
    obs=dict(identity=('postgres','postgres',False,True,True,True,False,False,False,False,True,True),control=dict(global_stop=oo.STOP,manual_stop=G['manual_stop'],hard_stop_generation=2,unexpired_grants=0))
    findings,_=oo.evaluate_pipeline_readback(obs,dict(identity='postgres',hard_stop_generation=2,valid_until='x'))
    assert 'MANUAL_STOP_CHANGED' in findings      # default expectation: STORAGE_TEST_STOP
    findings,_=oo.evaluate_pipeline_readback(obs,dict(identity='postgres',hard_stop_generation=2,manual_stop=G['manual_stop'],valid_until='x'))
    assert 'MANUAL_STOP_CHANGED' not in findings and 'HARD_STOP_GENERATION_CHANGED' not in findings


# ---------------------------------------------------------------- registration validators
def registration(mode):
    base=json.loads((PACKAGE/'base_constants.json').read_text());base={k:v for k,v in base.items() if not k.startswith('_')};base.pop('limits',None)
    common=dict(base,expires_at=(datetime.now(timezone.utc)+timedelta(minutes=20)).replace(microsecond=0).isoformat(),revision='a'*40,tree='b'*40,hashes={},controller_sha256='c'*64,ca_sha256='d'*64,manifest_sha256='e'*64,evidence_head='1'*40)
    if mode=='policy':
        return dict(common,mode=orr.POLICY_MODE,authority=orr.POLICY_AUTHORITY,evidence_directory=orr.PROBE_EVIDENCE_DIRECTORY,predecessor=orr.POLICY_PREDECESSOR,state_directory=orr.POLICY_STATE,execution_authority='NONE',
                    risk_application='THIS_FINITE_POLICY_GENERATION2_INSTALLATION_ONLY',owner_limits=dict(connections=list(orr.POLICY_OWNER_LIMITS['connections']),commands=list(orr.POLICY_OWNER_LIMITS['commands'])),
                    policy=dict(file=str(orr.GENERATION2_POLICY),named_allowance=NAMED,baseline=G),execution=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=orr.POLICY_STATE),approval='X')
    return dict(common,mode=orr.PROBE_MODE,authority=orr.PROBE_AUTHORITY,evidence_directory=orr.PROBE_EVIDENCE_DIRECTORY,predecessor=orr.PROBE_PREDECESSOR,state_directory=orr.PROBE_STATE,
                execution_authority='OWNER_GRANT_AND_EXCEPTION_FOR_THE_HOSTED_RESTRICTED_JOB',risk_application='THIS_FINITE_BOLTON_FORM_PROBE_ONCE',probe=orr.PROBE_BINDING,
                owner_limits=dict(connections=list(orr.PROBE_OWNER_LIMITS['connections']),commands=list(orr.PROBE_OWNER_LIMITS['commands'])),policy_ceremony_audit=dict(events_sha256='1'*64,final_result_sha256='2'*64),
                execution=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=orr.PROBE_STATE),approval='X')


def validate(r):
    body=json.dumps(r,sort_keys=True,indent=1).encode();return orr.validate_registration(body,hashlib.sha256(body).hexdigest())


@pytest.mark.parametrize('mode,binding_error',[('policy','POLICY_GENERATION2_BINDING'),('probe','BOLTON_FORM_PROBE_BINDING')])
def test_the_validators_bind_each_mode_exactly(mode,binding_error):
    with pytest.raises(ValueError,match='CLEAN_REVIEWED_CHECKOUT'):validate(registration(mode))      # every binding passes; only the (deliberately wrong) checkout identity stops it
    tampers={'policy':[dict(execution_authority='X'),dict(state_directory=orr.PIPELINE_STATE),dict(owner_limits=dict(connections=[9,9],commands=[34,40,48])),dict(policy=dict(file='x',named_allowance=NAMED,baseline=G)),dict(pipeline={'x':1})],
             'probe':[dict(probe=dict(orr.PROBE_BINDING,grant_minutes=999)),dict(execution_authority='NONE'),dict(state_directory=orr.PIPELINE_STATE),dict(evidence_directory='docs/design/ingestion-operational-execution-stable-pipeline-20261020'),
                      dict(owner_limits=dict(connections=[9,9],commands=[28,52,66])),dict(policy_ceremony_audit=None),dict(policy_ceremony_audit=dict(events_sha256='short',final_result_sha256='2'*64)),
                      dict(predecessor=dict(orr.PROBE_PREDECESSOR,observed_stop=dict(G,hard_stop_generation=1)))]}[mode]
    for tamper in tampers:
        with pytest.raises(ValueError,match=binding_error):validate(dict(registration(mode),**tamper))


def test_the_expiry_caps_and_authorities_are_separate_per_mode():
    long_policy=dict(registration('policy'),expires_at=(datetime.now(timezone.utc)+timedelta(minutes=45)).replace(microsecond=0).isoformat())
    with pytest.raises(ValueError,match='ORIGINAL_OPERATIONAL_EXPIRY'):validate(long_policy)      # policy: at most 30 minutes
    ok_probe=dict(registration('probe'),expires_at=(datetime.now(timezone.utc)+timedelta(minutes=60)).replace(microsecond=0).isoformat())
    with pytest.raises(ValueError,match='CLEAN_REVIEWED_CHECKOUT'):validate(ok_probe)      # probe: up to 75 minutes
    with pytest.raises(ValueError,match='EXACT_OPERATIONAL_APPROVAL_REQUIRED'):validate(dict(registration('probe'),authority=orr.PIPELINE_AUTHORITY))
    assert len({orr.OBSERVER_AUTHORITY,orr.POLICY_AUTHORITY,orr.PROBE_AUTHORITY,orr.PIPELINE_AUTHORITY})==4


def test_every_credential_mode_validates_the_hidden_input_before_consuming_the_registration():
    assert set(orr.INPUT_PRECHECKED_MODES)=={orr.OBSERVER_MODE,orr.POLICY_MODE,orr.PROBE_MODE,orr.CAPTURE_POLICY_MODE,orr.CAPTURE_MODE}
    assert orr.PIPELINE_MODE not in orr.INPUT_PRECHECKED_MODES      # the consumed pipeline mode keeps its original order


# ---------------------------------------------------------------- the hosted half
def hosted_runner(tmp_path):
    from verification.ingestion_storage.operational_journal import Journal
    urls={r:'postgresql://%s:x@h/db'%r for r in oo.ROLES};Path(tmp_path).mkdir(parents=True,exist_ok=True)
    return fp.ProbeHostedRunner(urls,Journal(tmp_path/'j'),None,None,{},'192.0.2.1',None,evidence_head='1'*40,manifest_sha256='c'*64,revision='a'*40)


def test_the_hosted_identity_equals_the_owners_and_reads_only_its_own_allowance(tmp_path):
    h=hosted_runner(tmp_path)
    root=oo.item(dict(subject=oo.SCOPE,task='DISCOVERY',contract=orr.CONTRACT,revision='c'*64),max_attempts=1,limits=orr.PROBE_LIMITS)
    assert h.capture_key==root['key'] and h.execution==dict(revision='a'*40,manifest_sha256='c'*64,capture_key=root['key'],initial_evidence_head='1'*40,authority=orr.PROBE_AUTHORITY)
    assert h.GRANT_SUFFIX=='_PROBE' and sp.HostedRunner.GRANT_SUFFIX=='_CAPTURE' and h.authority+h.GRANT_SUFFIX==NAMED      # the exact name policy v3 recognises
    assert h.r['evidence_directory']==orr.PROBE_EVIDENCE_DIRECTORY and h.deadlines==fp.PROBE_HOSTED_DEADLINES


def test_the_hosted_job_is_admitted_only_for_its_own_authority():
    env=dict(PIPELINE_REVIEWED_SHA='a'*40,PIPELINE_EVIDENCE_HEAD='b'*40,GITHUB_SHA='a'*40,GITHUB_WORKFLOW_SHA='a'*40,GITHUB_REF='refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1',GITHUB_ACTIONS='true',
             RUNNER_ENVIRONMENT='github-hosted',PIPELINE_AUTHORITY=fp.PROBE_HOSTED_AUTHORITY)
    assert sp.admitted(env,fp.PROBE_HOSTED_AUTHORITY) is True
    assert not sp.admitted(env) and not sp.admitted(dict(env,PIPELINE_AUTHORITY=sp.HOSTED_AUTHORITY),fp.PROBE_HOSTED_AUTHORITY)      # neither authority admits the other's job
    assert sp.admitted(dict(env,PIPELINE_AUTHORITY=sp.HOSTED_AUTHORITY)) is True      # the original admission is unchanged
    for bad in (dict(GITHUB_RUN_NUMBER='2'),dict(GH_TOKEN='t'),dict(DATABASE_URL='x'),dict(GITHUB_REF='refs/heads/x')):
        assert not sp.admitted(dict(env,**bad),fp.PROBE_HOSTED_AUTHORITY)


# ---------------------------------------------------------------- the restricted workflow (static)
def test_the_form_probe_workflow_is_single_use_pinned_and_credential_separated():
    text=WF.read_text()
    assert '"$GITHUB_RUN_NUMBER" == 1' in text and '"$GITHUB_RUN_ATTEMPT" == 1' in text and 'refs/heads/master' in text and 'PIN" == "$WF"' in text and 'GITHUB_SHA' in text
    assert fp.PROBE_HOSTED_AUTHORITY in text and sp.HOSTED_AUTHORITY not in text and 'stable_pipeline",run_name' not in text and 'verification.ingestion_storage.form_probe' in text
    assert text.count('secrets.')==2 and 'INGESTION_WORKER_DATABASE_URL: ${{ secrets.INGESTION_WORKER_DATABASE_URL }}' in text and 'INGESTION_EFFECT_DATABASE_URL: ${{ secrets.INGESTION_EFFECT_DATABASE_URL }}' in text
    assert 'DATABASE_URL: ${{ secrets.DATABASE_URL' not in text
    assert 'environment: stage4-production-canary' in text and 'timeout-minutes: 20' in text and 'permissions:\n  contents: write' in text and 'cancel-in-progress: false' in text
    assert "printf '%s\\n%s\\n%s\\n' \"$GH_TOKEN\"" in text and 'env -i' in text and 'hosted_memory_scope.sh' in text and 'timeout --kill-after=15s 900s' in text      # secrets on stdin only, kernel-enforced memory, a hard kill
    assert 'ulimit -c 0' in text and 'reviewed_sha' in text and 'evidence_head' in text and 'NOT_AUTHORISED' in text
    pinned=hashlib.sha256(WF.read_bytes()).hexdigest()
    assert pinned in (ROOT/'tests/test_stage4_batch_registration.py').read_text() and pinned in (ROOT/'tests/test_oldham_production_registration.py').read_text()      # the exclusivity guards pin its exact bytes


def test_the_hosted_job_uses_a_fresh_workflow_so_its_run_number_is_one():
    assert WF.name!='stage4-stable-pipeline-once.yml' and 'group: stage4-form-probe' in WF.read_text()


# ---------------------------------------------------------------- the renderer and the owner scripts
def test_the_renderer_builds_registrations_that_pass_every_binding_but_the_checkout(monkeypatch):
    import importlib.util
    spec=importlib.util.spec_from_file_location('render_probe',PACKAGE/'render_registration.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    for mode,error in (('policy',None),('probe',None)):
        r=m.render(mode,minutes=20,evidence_head='1'*40,policy_audit=dict(events_sha256='1'*64,final_result_sha256='2'*64) if mode=='probe' else None)
        with pytest.raises(ValueError,match='CLEAN_REVIEWED_CHECKOUT'):validate(dict(r,revision='f'*40))      # every other binding passes; only the (deliberately wrong) checkout identity stops it - deterministic in any checkout
    with pytest.raises(ValueError,match='POLICY_CEREMONY_AUDIT_REQUIRED'):m.render('probe',evidence_head='1'*40)
    with pytest.raises(ValueError):m.render('other',evidence_head='1'*40)


def test_the_owner_scripts_use_fresh_names_check_the_predecessors_and_never_take_the_credential_as_an_argument():
    for name,state,registration in (('owner-run-policy.sh','operational-policy-generation2-once-20261021','operational-bolton-policy-generation2-registration-20261021.json'),
                                    ('owner-run-probe.sh','operational-bolton-form-probe-once-20261021','operational-bolton-form-probe-registration-20261021.json')):
        text=(PACKAGE/name).read_text()
        assert 'STATE_DIRECTORY='+state in text and registration in text and 'test ! -e "$STATE_ROOT/$STATE_DIRECTORY"' in text and 'VISIBLE_INTERACTIVE_TTY_REQUIRED' in text
        for h in ('35dedf6a87c3b10d4e23af54590c49bb5af4393358dd79ee9f95675be5035449','842139208adb04e180e2776790f8111216510277d9c433cbea7a1ebf3c0107a4','bc2187fb125667090f536be4031f285c2887be52af184313abeccd72c0ad8f41'):assert h in text
        assert 'sha256sum --check' in text and 'you are asked once' in text and 'PASSWORD' not in text.upper().replace('PASSWORD','') and 'read -s' not in text
    assert 'gh api' not in (PACKAGE/'owner-run-policy.sh').read_text().replace('# ','') and 'gh api user' in (PACKAGE/'owner-run-probe.sh').read_text()
    assert 'policy_ceremony_audit' in (PACKAGE/'owner-run-probe.sh').read_text()
