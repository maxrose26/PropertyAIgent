"""The direct-route diagnostic package: the rendered registration is accepted by the runner's validator and binds exactly the finite diagnostic (no execution authority); every binding is
enforced; the owner script keeps its safety order and refuses to launch without an IPv4 address for the direct host."""
import hashlib,importlib.util,json,subprocess
from datetime import datetime,timezone,timedelta
from pathlib import Path
import pytest
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage.operational_runner import validate_registration

PACKAGE=Path('docs/design/ingestion-direct-route-diagnostic-20261020')
HEAD='7368d77b4908d1676023904ed0af6f0345ce0053'


def render(minutes=60,evidence_head=HEAD):
    spec=importlib.util.spec_from_file_location('render_direct_registration',PACKAGE/'render_registration.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.render(root=Path('.').resolve(),minutes=minutes,evidence_head=evidence_head)


def validate(reg):
    body=json.dumps(reg,sort_keys=True).encode()
    return validate_registration(body,hashlib.sha256(body).hexdigest())


@pytest.fixture
def clean_checkout(monkeypatch):
    real=subprocess.check_output
    monkeypatch.setattr(subprocess,'check_output',lambda cmd,**kw:'' if cmd[1]=='status' else real(cmd,**kw))


def test_rendered_registration_is_accepted_and_binds_the_finite_diagnostic(clean_checkout):
    reg=render();accepted=validate(reg)
    assert accepted['mode']==orr.DIRECT_MODE and accepted['authority']==orr.DIRECT_AUTHORITY and accepted['restricted_route']=='DIRECT' and accepted['execution_authority']=='NONE'
    assert accepted['risk_application']=='THIS_FINITE_DIRECT_ROUTE_DIAGNOSTIC_ONLY' and accepted['predecessor']==orr.DIRECT_PREDECESSOR and accepted['state_directory']==orr.DIRECT_STATE
    assert accepted['execution']==dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=orr.DIRECT_STATE)
    assert accepted['owner_limits']==dict(connections=list(orr.DIRECT_OWNER_LIMITS['connections']),commands=list(orr.DIRECT_OWNER_LIMITS['commands']))
    assert accepted['risk_acceptance']=='ACCEPT_POSSIBLE_PROVIDER_SCRAM_VERIFIER_RETENTION_WORKER_EFFECT_ONCE' and accepted['roles']==['ingestion_worker_login','ingestion_effect_login']
    assert accepted['limits']['grants']=={'authority':0,'bolton_exception':0} and accepted['limits']['source']=={'observations':0,'transport_requests':0}
    manifest=json.loads((PACKAGE/'MANIFEST.json').read_text())
    assert sorted(reg['hashes'])==sorted(manifest['bound_paths']) and all(Path(p).is_file() for p in manifest['bound_paths'])
    assert reg['manifest_sha256']==hashlib.sha256((PACKAGE/'MANIFEST.json').read_bytes()).hexdigest()


def test_the_limits_in_the_package_match_the_code_that_enforces_them():
    base=json.loads((PACKAGE/'base_constants.json').read_text())['limits']
    assert base['administration']=={'commands':list(orr.DIRECT_OWNER_LIMITS['commands']),'connections':list(orr.DIRECT_OWNER_LIMITS['connections'])}
    assert base['timing']=={'hidden_input_seconds':orr.MATRIX_TIMING['input_seconds'],'active_seconds':orr.MATRIX_TIMING['active_seconds'],'work_alarm_seconds':orr.MATRIX_TIMING['work_seconds'],'outer_seconds':orr.MATRIX_TIMING['outer_seconds'],'systemd_backstop_seconds':450}


@pytest.mark.parametrize('change',[
    dict(mode='CONNECTION_DIAGNOSTIC_ONLY'),dict(mode=orr.SETTLED_R2_MODE),dict(mode=orr.MATRIX_MODE),dict(mode=None),dict(authority=orr.AUTHORITY),dict(authority=orr.SETTLED_R2_AUTHORITY),dict(status='DRAFT'),
    dict(restricted_route='POOLER'),dict(restricted_route=None),dict(execution_authority='CAPTURE'),dict(execution_authority=None),dict(risk_application='ANY_FUTURE_USE'),
    dict(predecessor=None),dict(predecessor={**orr.DIRECT_PREDECESSOR,'run_3':{**orr.DIRECT_PREDECESSOR['run_3'],'events_sha256':'0'*64}}),dict(predecessor=orr.SETTLED_R2_PREDECESSOR),
    dict(state_directory=orr.SETTLED_R2_STATE),dict(state_directory=None),dict(execution=None),dict(execution=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=2,retry=False,state_directory=orr.DIRECT_STATE)),
    dict(owner_limits=dict(connections=[13,13],commands=[240,240,240])),dict(settling_seconds=30),dict(risk_acceptance='NONE'),dict(roles=['ingestion_worker_login']),dict(scope={'council':'salford'}),
    dict(reuse_accepted_operational_installation=False),dict(baseline_control_sha256='0'*64),dict(revision='0'*40),dict(tree='0'*40),dict(controller_sha256='0'*64),dict(evidence_directory='docs/design/elsewhere'),
    dict(expires_at=(datetime.now(timezone.utc)+timedelta(hours=3)).isoformat()),dict(expires_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()),
])
def test_any_change_to_a_binding_is_refused(clean_checkout,change):
    reg=render();reg.update(change)
    with pytest.raises(Exception):validate(reg)


def test_a_modified_bound_file_is_refused(clean_checkout):
    reg=render();reg['hashes'][sorted(reg['hashes'])[0]]='0'*64
    with pytest.raises(ValueError,match='REVIEWED_CONTENT_BINDING'):validate(reg)


def test_the_evidence_head_must_be_a_full_commit_hash():
    for bad in (None,'','abc','Z'*40):
        with pytest.raises(ValueError,match='EVIDENCE_HEAD_REQUIRED'):render(evidence_head=bad)


def test_owner_script_checks_everything_before_anything_is_consumed():
    text=(PACKAGE/'owner-run.sh').read_text()
    order=['VISIBLE_INTERACTIVE_TTY_REQUIRED','git rev-parse HEAD','sha256sum --check','direct_route_namespace_absent','RUN1_DIRECTORY/events.jsonl','SCOPE_STATE_UNKNOWN','DIRECT_HOST_HAS_NO_IPV4_ADDRESS','validate_registration','gh api user','systemd-run']
    positions=[text.index(x) for x in order]
    assert positions==sorted(positions)
    assert 'RuntimeMaxSec=450s' in text and 'MemoryMax=1610612736' in text and 'timeout 10s systemctl' in text and 'operational-direct-route-diagnostic-once-20261020' in text and 'operational-direct-route-registration-20261020.json' in text
    assert 'DIRECT_ROUTE_DIAGNOSTIC_ONLY' in text and '@@' not in text and 'pkill' not in text and 'kill -9' not in text and 'AF_INET6' not in text
    for h in (orr.DIRECT_PREDECESSOR['run_1']['events_sha256'],orr.DIRECT_PREDECESSOR['run_2']['events_sha256'],orr.DIRECT_PREDECESSOR['run_3']['events_sha256'],orr.DIRECT_PREDECESSOR['run_3']['final_result_sha256']):assert h in text
