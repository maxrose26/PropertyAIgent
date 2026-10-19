"""The operational acceptance run package: the rendered registration is accepted by the runner's validator and binds exactly the approved run; the owner script keeps its safety order."""
import hashlib,importlib.util,json,subprocess
from datetime import datetime,timezone,timedelta
from pathlib import Path
import pytest
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage.operational_runner import validate_registration

PACKAGE=Path('docs/design/ingestion-operational-capture-20261019')
HEAD='7368d77b4908d1676023904ed0af6f0345ce0053'


def render(minutes=90,evidence_head=HEAD):
    spec=importlib.util.spec_from_file_location('render_capture_registration',PACKAGE/'render_registration.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.render(root=Path('.').resolve(),minutes=minutes,evidence_head=evidence_head)


def validate(reg):
    body=json.dumps(reg,sort_keys=True).encode()
    return validate_registration(body,hashlib.sha256(body).hexdigest())


@pytest.fixture
def clean_checkout(monkeypatch):
    real=subprocess.check_output
    monkeypatch.setattr(subprocess,'check_output',lambda cmd,**kw:'' if cmd[1]=='status' else real(cmd,**kw))       # the working tree under test may not be committed yet


def test_rendered_registration_is_accepted_and_binds_the_approved_run(clean_checkout):
    reg=render();accepted=validate(reg)
    assert accepted['mode']=='REQUIRED_CAPTURE_SCREENING' and accepted['authority']==orr.AUTHORITY and accepted['evidence_head']==HEAD
    assert accepted['risk_acceptance']=='ACCEPT_POSSIBLE_PROVIDER_SCRAM_VERIFIER_RETENTION_WORKER_EFFECT_ONCE' and accepted['roles']==['ingestion_worker_login','ingestion_effect_login']
    assert accepted['limits']['source']=={'observations':1,'pages':6,'received_body_bytes':3000000,'rows':60,'screening_source_requests':0,'transport_requests':10}
    assert accepted['limits']['administration']=={'commands':240,'connections':13} and accepted['limits']['runtime']=={'connections':40,'seconds':300,'statements':1040}
    assert accepted['limits']['cancellation']=={'administrative':3,'runtime':8,'seconds_each':2} and accepted['limits']['role_settings']=={'idle_in_transaction_session_timeout':'20s','lock_timeout':'3s','statement_timeout':'10s'}
    assert accepted['execution']==dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory='operational-capture-queue-successor-once-20261018')
    manifest=json.loads((PACKAGE/'MANIFEST.json').read_text())
    assert sorted(reg['hashes'])==sorted(manifest['bound_paths']) and all(Path(p).is_file() for p in manifest['bound_paths'])
    assert reg['manifest_sha256']==hashlib.sha256((PACKAGE/'MANIFEST.json').read_bytes()).hexdigest()


def test_the_limits_match_the_code_that_enforces_them():
    from verification.ingestion_storage import operational_owner as oo,operational_controller as oc
    base=json.loads((PACKAGE/'base_constants.json').read_text())['limits']
    assert base['administration']['commands']==oo.Owner.DEFAULT_LIMITS['commands'][2] and base['administration']['connections']==oo.Owner.DEFAULT_LIMITS['connections'][1]
    assert base['cancellation']['runtime']==oc.CANCEL_RUN_ALLOWANCE['attempts'] and base['cancellation']['administrative']==oo.ADMIN_CANCEL_ALLOWANCE
    assert dict(oo.ROLE_SETTINGS)==base['role_settings']
    source=Path('verification/ingestion_storage/operational_runner.py').read_text()
    assert 'limits=dict(DEFAULT_LIMITS,requests=10,bytes=3000000,rows=60,pages=6)' in source


@pytest.mark.parametrize('change',[
    dict(mode='RESTRICTED_CONNECTION_MATRIX_ONLY'),dict(mode=None),dict(authority='AUTHORISE_INGESTION_RESTRICTED_CONNECTION_MATRIX_ONCE_20261018'),dict(status='DRAFT'),
    dict(risk_acceptance='NONE'),dict(roles=['ingestion_worker_login']),dict(scope={'council':'salford'}),dict(reuse_accepted_operational_installation=False),
    dict(baseline_control_sha256='0'*64),dict(revision='0'*40),dict(tree='0'*40),dict(expires_at=(datetime.now(timezone.utc)+timedelta(hours=25)).isoformat()),
    dict(expires_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()),dict(controller_sha256='0'*64),dict(evidence_directory='docs/design/elsewhere'),
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
    order=['VISIBLE_INTERACTIVE_TTY_REQUIRED','git rev-parse HEAD','sha256sum --check','capture_namespace_absent','validate_registration','gh api user','EVIDENCE_REF" --jq','systemd-run']
    positions=[text.index(x) for x in order]
    assert positions==sorted(positions)
    assert 'RuntimeMaxSec=810s' in text and 'MemoryMax=1610612736' in text and 'timeout 10s systemctl' in text and 'operational-capture-queue-successor-once-20261018' in text
    assert '@@' not in text and 'pkill' not in text and 'kill -9' not in text
