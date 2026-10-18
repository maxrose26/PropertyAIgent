"""Fresh exact release tag; never rehabilitate consumed authority/audit paths."""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
import pytest
from verification.ingestion_storage import operational_runner as m

def registration():
    return dict(mode='CONNECTION_DIAGNOSTIC_ONLY',authority=m.DIAGNOSTIC_AUTHORITY,
        status='OWNER_APPROVED_REQUIRED_ONCE',scope=m.SCOPE,roles=list(m.ROLES),
        risk_acceptance='ACCEPT_POSSIBLE_PROVIDER_SCRAM_VERIFIER_RETENTION_WORKER_EFFECT_ONCE',
        reuse_accepted_operational_installation=True,
        baseline_control_sha256='0d829597f1422fef0af13920d5749c5751adf6d896588f379c400db7b3fa27cf',
        accepted_cleanup_evidence='8dc4a36bc5565318e138d192bf2f7e96906f048f',
        expires_at=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat(),
        revision='0'*40,tree='1'*40,hashes={},
        controller_sha256=hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest(),
        ca_sha256=m.PEM_SHA256,evidence_directory='docs/design/ingestion-operational-execution-actionable-20261018')

@pytest.mark.parametrize('authority',[
    'AUTHORISE_INGESTION_RESTRICTED_ROUTE_DIAGNOSTIC_ONCE_20261018',
    'AUTHORISE_BOLTON_CAPTURE_QUEUE_SUCCESSOR_ONCE_20261018',
    'AUTHORISE_INGESTION_ACTIONABLE_CONNECTION_DIAGNOSTIC_ONCE_20261019',
])
def test_consumed_or_unapproved_authority_rejected_before_checkout_or_access(monkeypatch,authority):
    r=registration();r['authority']=authority;b=json.dumps(r).encode()
    monkeypatch.setattr(m.subprocess,'check_output',lambda *a,**kw:pytest.fail('must reject before any subprocess/access'))
    with pytest.raises(ValueError,match='EXACT_OPERATIONAL_APPROVAL_REQUIRED'):m.validate_registration(b,hashlib.sha256(b).hexdigest())

def test_exact_new_binding_passes_readonly_validation(monkeypatch):
    r=registration();b=json.dumps(r).encode();values=iter(['0'*40,'1'*40,''])
    monkeypatch.setattr(m.subprocess,'check_output',lambda *a,**kw:next(values))
    assert m.validate_registration(b,hashlib.sha256(b).hexdigest())==r

def test_new_journal_one_use_and_old_audit_untouched(tmp_path):
    old=m.Journal(tmp_path/'operational-route-diagnostic-once-20261018')
    old.emit('consumed',{'authority':'historical'});original=old.file.read_bytes()
    new=m.Journal(tmp_path/m.DIAGNOSTIC_STATE)
    new.emit('consumed',{'authority':m.DIAGNOSTIC_AUTHORITY})
    assert old.file.read_bytes()==original and new.file.parent!=old.file.parent
    with pytest.raises(FileExistsError):m.Journal(tmp_path/m.DIAGNOSTIC_STATE)
