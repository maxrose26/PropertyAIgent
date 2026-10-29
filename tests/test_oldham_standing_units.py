"""No production, source, credentials or expiry rendering."""
import io,json
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from app.ingestion.ledger import Denied,digest
from verification.ingestion_storage import standing_access as a,oldham_standing_plan as p
from verification.ingestion_storage.oldham_standing_owner import standing_gate
from verification.ingestion_storage.oldham_authority import authority_revision


def test_exact_combined_capacity():
    assert a.GITHUB['owner']==a.GITHUB['owner_work']+a.GITHUB['owner_closure']
    assert a.GITHUB['runtime']==a.GITHUB['runtime_work']+a.GITHUB['runtime_closure']
    assert a.GITHUB['combined']==a.GITHUB['owner']+a.GITHUB['runtime']==100
    assert (a.POLL_ATTEMPTS,a.POLL_SECONDS)==(3,60)

@pytest.mark.parametrize('data',[b'',b'token\na\nb',b'token\na\nb\nextra\n',b'x'*16384])
def test_stdin_shape_refuses(data):
    with pytest.raises((SystemExit,Denied)):a.credentials(io.BytesIO(data))

@pytest.mark.parametrize('role',['postgres','ingestion_application_login','ingestion_effect_login'])
def test_wrong_worker_refuses(role):
    raw=f'token\npostgresql://{role}:synthetic@127.0.0.1:5432/ingestion_provisioning_test\npostgresql://ingestion_effect_login:synthetic@127.0.0.1:5432/ingestion_provisioning_test\n'.encode()
    with pytest.raises(Denied):a.credentials(io.BytesIO(raw),disposable=True)

def test_exact_standing_gate_preserves_provider_and_recovery_checks():
    from verification.ingestion_storage.oldham_lifecycle import activation_gate
    old=activation_gate(True);new=standing_gate()
    assert new==old.replace('WHERE rolname=login AND NOT rolcanlogin','WHERE rolname=login AND rolcanlogin')
    assert 'STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED' in new and 'RECOVERY_MUST_REMAIN_DORMANT' in new
    assert 'ALTER ROLE' not in new

@pytest.mark.parametrize('value',[[],[{}],[dict(cleanup='UNCERTAIN')],[dict(cleanup='CLOSED',connections_closed=True,driver_statements=None,connection_attempts=1,returned_data_value_bytes=0)]])
def test_uncertain_or_missing_phase_receipt_refuses(value):
    with pytest.raises(Denied):a.require_closure(value)

def test_positive_closure_does_not_claim_authority():
    assert a.require_closure([dict(cleanup='CLOSED',connections_closed=True,driver_statements=4,connection_attempts=1,returned_data_value_bytes=0)]) is True

def test_namespace_legacy_unchanged_and_new_bound():
    old=SimpleNamespace(bindings={});assert authority_revision(old,'a'*40)=='a'*40
    x=SimpleNamespace(standing_capture_screening=True,capture_screening_only=True,bindings={'manifest_sha256':'b'*64})
    assert authority_revision(x,'a'*40)=='b'*64
    x.bindings['manifest_sha256']='arbitrary'
    with pytest.raises(Denied):authority_revision(x,'a'*40)

def test_artifact_binary_boundary_before_call():
    from verification.ingestion_storage.operational_publication import GitHub,REPO
    g=GitHub(lambda *a:None,lambda:None,runner=lambda *a,**k:pytest.fail('must not call'))
    for method,path in [('POST',REPO+'/actions/artifacts/1/zip'),('GET','https://arbitrary.invalid'),('GET',REPO+'/secrets')]:
        with pytest.raises(ValueError):g.call(method,path,binary=True)
    assert g.requests==0

def test_publisher_cost_lower_bound_and_40_refusal():
    from tests.test_discovery_four_council_release import API
    from verification.ingestion_storage.operational_publication import GitHub,REPO,BRANCH
    api=object.__new__(API);api.head='1'*40;api.trees={'2'*40:{}};api.commits={api.head:'2'*40};api.blobs={};api.calls=[];api.fail=None;api.lost=False;api.ref_moved=False
    g=GitHub(lambda *a:None,lambda:None,runner=api.runner,bound=40);counts=[]
    for i,n in enumerate((1,1,1,2)):
        before=g.requests;g.publish({f'{j}.json':b'{}' for j in range(n)},directory=f'docs/design/ingestion-operational-execution-standing-cost/phase-{i}',expected_head=api.head);counts.append(g.requests-before)
    assert counts==[8,8,8,10]
    for _ in range(6):g.call('GET',REPO+'/git/ref/heads/'+BRANCH)
    with pytest.raises(ValueError,match='GITHUB_REQUEST_BOUND'):g.call('GET',REPO+'/git/ref/heads/'+BRANCH)
    assert g.requests==40
