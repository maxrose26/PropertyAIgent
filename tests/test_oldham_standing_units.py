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


def test_runtime_export_exact_bound_and_overflow_before_publication(tmp_path):
    from verification.ingestion_storage.oldham_standing_runtime import StandingRunner
    r=object.__new__(StandingRunner);r.journal=SimpleNamespace(root=tmp_path);r.published=123;r.export_limit=2*1024**2
    (tmp_path/'events.jsonl').write_bytes(b'e'*17)
    remaining=2*1024**2-128*1024-140
    r.export_capacity(remaining)
    with pytest.raises(Denied,match='RUNTIME_EXPORT_RESERVE'):r.export_capacity(remaining+1)
    r.export_capacity(remaining-1,replacement=('events.jsonl',b'e'*18))
    with pytest.raises(Denied):r.export_capacity(remaining,replacement=('events.jsonl',b'e'*18))


def test_owner_artifact_capacity_exact_bound_and_overflow(tmp_path):
    from verification.ingestion_storage.oldham_standing_owner import StandingOperation
    r=object.__new__(StandingOperation);r.journal=SimpleNamespace(root=tmp_path);r.published=100;r.runtime_packet_bytes=100
    (tmp_path/'events.jsonl').write_bytes(b'e'*10)
    remaining=2*1024**2-8192-210
    r.artifact_capacity(remaining)
    with pytest.raises(Denied,match='ARTIFACT_EXPORT_RESERVE'):r.artifact_capacity(remaining+1)


def test_whole_publication_leaves_call_reserve_before_effects():
    from verification.ingestion_storage.standing_access import StandingGitHub
    g=StandingGitHub(lambda *a:None,lambda:None,runner=lambda *a,**k:pytest.fail('must not call'),bound=18)
    g.requests=11
    with pytest.raises(Denied,match='CAPACITY_BEFORE_EFFECTS'):g.publish({'one':b'{}'},directory='docs/design/ingestion-operational-execution-test',expected_head='1'*40)
    assert g.requests==11


@pytest.mark.parametrize('uncertain,attempts,stage,expected',[(False,0,'CAPTURE_RECEIPT','VERIFIED'),(False,None,'CAPTURE_ISSUANCE','VERIFIED'),(False,None,'CAPTURE_RECEIPT','RECONCILIATION_REQUIRED_NO_AUTOMATIC_MUTATION'),(True,0,'CAPTURE_RECEIPT','RECONCILIATION_REQUIRED_NO_AUTOMATIC_MUTATION')])
def test_failure_invalidation_only_for_certain_effects(uncertain,attempts,stage,expected):
    from verification.ingestion_storage.oldham_standing_owner import StandingOperation
    o=SimpleNamespace(authorities=['exact'],invalidation='REQUIRED',effect_uncertain=uncertain,awaiting_verification=False)
    def revoke():o.invalidation='VERIFIED'
    o.revoke=revoke
    r=object.__new__(StandingOperation);r.owner=o;r.stage=stage;r.hosted={'database_connections_attempted':attempts};r.github=SimpleNamespace(mutation_uncertain=False)
    assert r.failure_invalidation()==expected


def test_shared_export_reservation_cannot_exceed_original_envelope():
    for spent in (0,4096,500000):
        r=a.export_reservation(spent)
        assert a.validate_export_reservation(r)==r
        assert r['owner_limit']+3*r['runtime_limit']+r['zip_overhead']<=2*1024**2
        assert r['owner_limit']==spent+128*1024
        bad=dict(r,runtime_limit=r['runtime_limit']+1)
        with pytest.raises(Denied):a.validate_export_reservation(bad)
    with pytest.raises(Denied):a.export_reservation(2*1024**2)


def test_actual_final_export_respects_selected_share_before_effects(tmp_path):
    from verification.ingestion_storage.operational_outcome import finalise
    from verification.ingestion_storage.operational_journal import Journal
    from verification.ingestion_storage.operational_publication import canonical
    journal=Journal(tmp_path/'report');journal.emit('fixture',{'value':True})
    original={'status':'FIXTURE','padding':'x'*20000};outputs=[]
    result=finalise(journal,original,input_seconds=0,active_started=None,output=lambda value,**kw:outputs.append(value),export_limit=65536)
    assert result['status']=='FIXTURE'
    receipt=json.loads(outputs[-1]);actual=receipt['exported_bytes']
    assert actual<=65536-8192
    # Repeat at the exact projected total and one byte below it, with timing
    # frozen so the actual finalisation path exercises its exact boundary.
    import unittest.mock
    with unittest.mock.patch('verification.ingestion_storage.operational_outcome.time.monotonic',return_value=0):
        raw=dict(original);raw.pop('phase_timing',None)
        one=finalise(journal,raw,input_seconds=0,active_started=None,output=lambda value,**kw:None,export_limit=actual+8192)
        assert one['status']=='FIXTURE'
        two=finalise(journal,dict(raw),input_seconds=0,active_started=None,output=lambda value,**kw:None,export_limit=actual+8191)
        assert two['status']=='STOP_RECONCILE_NO_RETRY'


def test_screen_marker_binds_prepared_authority_not_mutable_root_state():
    r=SimpleNamespace(authority='exact',root_key='root',insert=[{'key':'batch','checkpoint':{'plan':'exact'}}],grant={'keys':['root','batch']},bindings={'root':{'revision':'a'*40}},rows=[{'fence':1,'lease_owner':'old'}])
    before=p.screening_authority_digest(r)
    r.rows[0].update(fence=2,lease_owner=None)
    assert p.screening_authority_digest(r)==before
    r.insert[0]['checkpoint']['plan']='substituted'
    assert p.screening_authority_digest(r)!=before


def test_stored_screening_package_projection_keeps_full_provenance():
    r=dict(kind='SCREENING',authority='exact',root_key='root',rows=[{'key':'root','fence':2,'outcome':{'outcome':'ENUMERATED_METADATA_RETAINED'}}],insert=[{'key':'batch'}],grant={'keys':['root','batch']},bindings={'root':{'revision':'a'*40}},targets={})
    expected=p.screening_authority_digest(r)
    r['rows'][0]['fence']=3
    assert p.screening_authority_digest(r)==expected
    r['grant']['keys'].append('unexpected')
    assert p.screening_authority_digest(r)!=expected
    r['targets']={'unexpected':{}}
    with pytest.raises(Denied):p.screening_authority_digest(r)
