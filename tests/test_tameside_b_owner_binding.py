"""Pure dependent-pin checks. TEST-NET addresses are synthetic, never proposals."""
from pathlib import Path
import copy,hashlib,json
import pytest
from app.ingestion.ledger import Denied,digest
from verification.ingestion_storage import intake_owner as owner
from verification.ingestion_storage.daily_intake_runtime import BOUND_FILES


def test_owner_pin_matches_exact_separate_application_candidate():
    b=json.loads(Path('docs/design/tameside-b-connection-20261101/application-binding.json').read_bytes())
    assert owner.APPLICATION_BINDING==b and b['revision']=='db05f5d48ce0c70c048c99f538d8765dae669c17'
    assert b['workflow_sha256']==hashlib.sha256(Path('.github/workflows/stage4-discovery-offline.yml').read_bytes()).hexdigest()
    assert b['manifest_sha256']==digest({n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in BOUND_FILES})

def test_owner_validates_new_binding_and_refuses_old_revision():
    b=dict(version='FINITE_INTAKE_OWNER_V1',period='offline-only-test',route='DIRECT',hostaddr='192.0.2.10',owner_hostaddr='192.0.2.11',execution_binding=copy.deepcopy(owner.APPLICATION_BINDING),accepted_stop=owner.ACCEPTED_STOP)
    assert owner.validate_binding(b)==b
    b['execution_binding']['revision']='62fad2f67b3a20d921cf7d8b8c4410baaefde4e1'
    with pytest.raises(Denied,match='EXACT_REVIEWED_APPLICATION_REQUIRED'):owner.validate_binding(b)

def test_owner_refuses_stale_runtime_manifest():
    b=dict(version='FINITE_INTAKE_OWNER_V1',period='offline-only-test',route='DIRECT',hostaddr='192.0.2.10',owner_hostaddr='192.0.2.11',execution_binding=copy.deepcopy(owner.APPLICATION_BINDING),accepted_stop=owner.ACCEPTED_STOP)
    b['execution_binding']['manifest_sha256']='d2b6f77ba9d658436184114487b05dc0d11ab33f0dd9c2bf114fad45b81aad38'
    with pytest.raises(Denied,match='EXACT_REVIEWED_APPLICATION_REQUIRED'):owner.validate_binding(b)
