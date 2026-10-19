"""The stable-credential owner package: rendered registrations are accepted by the runner's validator and bind exactly the provisioning or the revocation ceremony (no execution authority); every
binding is enforced; the owner script keeps its safety order."""
import hashlib,importlib.util,json,subprocess
from datetime import datetime,timezone,timedelta
from pathlib import Path
import pytest
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage.operational_runner import validate_registration

PACKAGE=Path('docs/design/ingestion-stable-credentials-20261020')
HEAD='7368d77b4908d1676023904ed0af6f0345ce0053'
MODES={'provisioning':orr.STABLE_PROVISION_MODE,'revocation':orr.STABLE_REVOKE_MODE}


def render(mode='provisioning',minutes=60,evidence_head=HEAD):
    spec=importlib.util.spec_from_file_location('render_stable_registration',PACKAGE/'render_registration.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.render(mode,root=Path('.').resolve(),minutes=minutes,evidence_head=evidence_head)


def validate(reg):
    body=json.dumps(reg,sort_keys=True).encode()
    return validate_registration(body,hashlib.sha256(body).hexdigest())


@pytest.fixture
def clean_checkout(monkeypatch):
    real=subprocess.check_output
    monkeypatch.setattr(subprocess,'check_output',lambda cmd,**kw:'' if cmd[1]=='status' else real(cmd,**kw))


@pytest.mark.parametrize('mode',['provisioning','revocation'])
def test_rendered_registration_is_accepted_and_binds_the_ceremony(clean_checkout,mode):
    reg=render(mode);accepted=validate(reg);authority,state,risk=orr.STABLE_MODES[MODES[mode]]
    assert accepted['mode']==MODES[mode] and accepted['authority']==authority and accepted['state_directory']==state and accepted['risk_application']==risk and accepted['execution_authority']=='NONE'
    assert accepted['predecessor']==orr.DIRECT_PREDECESSOR and accepted['execution']==dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=state)
    assert accepted['owner_limits']==dict(connections=list(orr.STABLE_OWNER_LIMITS['connections']),commands=list(orr.STABLE_OWNER_LIMITS['commands']))
    assert accepted.get('validity_days')==(orr.STABLE_VALIDITY_DAYS if mode=='provisioning' else None) and 'restricted_route' not in accepted and 'settling_seconds' not in accepted
    assert accepted['limits']['grants']=={'authority':0,'bolton_exception':0} and accepted['limits']['validity']['initial_days']==90 and accepted['roles']==['ingestion_worker_login','ingestion_effect_login']
    manifest=json.loads((PACKAGE/'MANIFEST.json').read_text())
    assert sorted(reg['hashes'])==sorted(manifest['bound_paths']) and all(Path(p).is_file() for p in manifest['bound_paths'])
    assert reg['manifest_sha256']==hashlib.sha256((PACKAGE/'MANIFEST.json').read_bytes()).hexdigest()


def test_the_limits_in_the_package_match_the_code_that_enforces_them():
    base=json.loads((PACKAGE/'base_constants.json').read_text())['limits']
    assert base['administration']=={'commands':list(orr.STABLE_OWNER_LIMITS['commands']),'connections':list(orr.STABLE_OWNER_LIMITS['connections'])}
    from verification.ingestion_storage import stable_qualification as sq
    assert base['qualification']['attempts_per_role']==sq.MAX_PER_ROLE and base['qualification']['attempts_total']==sq.MAX_TOTAL and base['qualification']['spacing_seconds']==list(sq.SPACING_SECONDS) and base['qualification']['overall_seconds']==sq.OVERALL_SECONDS
    assert base['validity']['initial_days']==orr.STABLE_VALIDITY_DAYS and base['timing']['systemd_backstop_seconds']==450


@pytest.mark.parametrize('mode',['provisioning','revocation'])
@pytest.mark.parametrize('change',[
    dict(mode='CONNECTION_DIAGNOSTIC_ONLY'),dict(mode=orr.DIRECT_MODE),dict(mode=orr.SETTLED_R2_MODE),dict(mode=None),dict(authority=orr.AUTHORITY),dict(authority=orr.DIRECT_AUTHORITY),dict(status='DRAFT'),
    dict(execution_authority='CAPTURE'),dict(execution_authority=None),dict(risk_application='ANY_FUTURE_USE'),dict(predecessor=None),dict(predecessor=orr.SETTLED_R2_PREDECESSOR),
    dict(state_directory=orr.DIRECT_STATE),dict(state_directory=None),dict(execution=None),dict(owner_limits=dict(connections=[13,13],commands=[240,240,240])),
    dict(restricted_route='DIRECT'),dict(settling_seconds=0),dict(risk_acceptance='NONE'),dict(roles=['ingestion_worker_login']),dict(scope={'council':'salford'}),
    dict(reuse_accepted_operational_installation=False),dict(baseline_control_sha256='0'*64),dict(revision='0'*40),dict(tree='0'*40),dict(controller_sha256='0'*64),dict(evidence_directory='docs/design/elsewhere'),
    dict(expires_at=(datetime.now(timezone.utc)+timedelta(hours=3)).isoformat()),dict(expires_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()),
])
def test_any_change_to_a_binding_is_refused(clean_checkout,mode,change):
    reg=render(mode);reg.update(change)
    with pytest.raises(Exception):validate(reg)


@pytest.mark.parametrize('days',[None,0,30,89,91,365,True,90.0])
def test_the_validity_period_is_bound_exactly_for_provisioning(clean_checkout,days):
    reg=render('provisioning');reg['validity_days']=days
    with pytest.raises(Exception):validate(reg)


def test_a_revocation_registration_cannot_carry_a_validity_period(clean_checkout):
    reg=render('revocation');reg['validity_days']=90
    with pytest.raises(ValueError):validate(reg)


def test_a_modified_bound_file_is_refused(clean_checkout):
    reg=render();reg['hashes'][sorted(reg['hashes'])[0]]='0'*64
    with pytest.raises(ValueError,match='REVIEWED_CONTENT_BINDING'):validate(reg)


def test_the_evidence_head_must_be_a_full_commit_hash():
    for bad in (None,'','abc','Z'*40):
        with pytest.raises(ValueError,match='EVIDENCE_HEAD_REQUIRED'):render(evidence_head=bad)
    with pytest.raises(ValueError):render('anything')


def test_owner_script_checks_everything_before_anything_is_consumed():
    text=(PACKAGE/'owner-run.sh').read_text()
    order=['VISIBLE_INTERACTIVE_TTY_REQUIRED','git rev-parse HEAD','sha256sum --check','stable_namespace_absent','RUN1_DIRECTORY/events.jsonl','SCOPE_STATE_UNKNOWN','validate_registration','gh api user','systemd-run']
    positions=[text.index(x) for x in order]
    assert positions==sorted(positions)
    assert 'RuntimeMaxSec=450s' in text and 'MemoryMax=1610612736' in text and 'timeout 10s systemctl' in text and '@@' not in text and 'pkill' not in text and 'kill -9' not in text
    assert 'operational-stable-provisioning-once-20261020' in text and 'operational-stable-revocation-once-20261020' in text and 'STABLE_CREDENTIAL_PROVISIONING' in text and 'STABLE_CREDENTIAL_REVOCATION' in text
    for h in (orr.DIRECT_PREDECESSOR['run_1']['events_sha256'],orr.DIRECT_PREDECESSOR['run_2']['events_sha256'],orr.DIRECT_PREDECESSOR['run_3']['events_sha256'],orr.DIRECT_PREDECESSOR['run_3']['final_result_sha256']):assert h in text
