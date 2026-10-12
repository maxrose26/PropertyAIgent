import copy
import json
from pathlib import Path
import pytest
from verification.direct_reference.frozen_acceptance import *

@pytest.fixture(autouse=True)
def disposable(monkeypatch):
    monkeypatch.setenv('B20_DISPOSABLE','YES_SYNTHETIC_ONLY');monkeypatch.delenv('DATABASE_URL',raising=False)


def test_exact_live_artifact():
    a=load_live()
    assert a['totals']==dict(requests=3,redirects=0,retries=0,received_body_bytes=118664)
    assert [x['application_id'] for x in a['results']]==[202,42,78]
    assert PROVENANCE['qualification']=='LIVE_SOURCE_OBSERVATION'
    assert PROVENANCE['exact_retrieval_timestamp'] is None


@pytest.mark.parametrize('i,state,eligible',[(202,'UNKNOWN_UNMAPPED',False),(42,'refused',True),(78,'granted',True)])
def test_translation(i,state,eligible):
    o=frozen_observation(i)
    row=next(x for x in load_live()['results'] if x['application_id']==i)
    assert o.fields==row['normalized_facts'] and o.field_states==row['field_states']
    assert o.literal_fields==row['literal_facts'] and o.semantic_state==state and o.b2_eligible is eligible
    assert o.body_sha256 is None
    assert frozen_observation(i)==o


def test_guard_rejects_production_and_unguarded_replay(monkeypatch):
    monkeypatch.delenv('B20_DISPOSABLE')
    with pytest.raises(ValueError):frozen_observation(42)
    monkeypatch.setenv('B20_DISPOSABLE','YES_SYNTHETIC_ONLY');monkeypatch.setenv('DATABASE_URL','postgresql://not-used')
    with pytest.raises(ValueError):frozen_observation(42)


def sample():
    f={'status':'Awaiting decision','decision':None,'decision_date':None}
    return dict(application_id=42,reference='FUL/355686/26',source_provenance=PROVENANCE,
      retrieval_started_at=None,retrieval_completed_at=None,outcome='PARTIAL_RETRIEVAL',
      before=f,qualified_incoming=f,after=f,verification_watermark_before=None,
      verification_watermark_after=None,material_change='UNKNOWN',transaction_result='REJECTED_NO_WRITE',
      lifecycle_before=[],lifecycle_after=[],refresh_signal_before={'required':False,'reason':None,'trigger':None,'requested_at':None},
      refresh_signal_after={'required':False,'reason':None,'trigger':None,'requested_at':None},error_qualification='WITHHELD_PARTIAL')


def test_audit_privacy():
    a=sample();validate_persistence_audit(a)
    for key in ('raw_html','cookies','headers','applicant','DATABASE_URL'):
        bad=copy.deepcopy(a);bad[key]='forbidden'
        with pytest.raises(ValueError):validate_persistence_audit(bad)
    bad=copy.deepcopy(a);bad['before']['proposal']='private'
    with pytest.raises(ValueError):validate_persistence_audit(bad)
    bad=copy.deepcopy(a);bad['error_qualification']='raw database credential'
    with pytest.raises(ValueError):validate_persistence_audit(bad)


def test_fixture_tampering_rejected(monkeypatch):
    original=Path.read_bytes
    def tamper(p):
        b=original(p)
        return b.replace(b'Deposited',b'Pending') if p.name=='live-observations-38310507094.json' else b
    monkeypatch.setattr(Path,'read_bytes',tamper)
    with pytest.raises(ValueError):load_live()
