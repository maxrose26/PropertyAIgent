"""Pure input seals and unchanged legacy selection. No source/DB/credentials."""
import json
from copy import deepcopy
import pytest
from app.ingestion.ledger import Denied,digest
from verification.ingestion_storage import oldham_owner_package as p,oldham_reuse as r
from verification.ingestion_storage.oldham_lifecycle import Lifecycle,activation_gate,ACTIVATION
from tests.oldham_wrapper_fixture import packet

@pytest.fixture
def inputs(tmp_path,monkeypatch):
    original=p.git;monkeypatch.setattr(p,'git',lambda *a:'' if a==('status','--porcelain') else original(*a))
    return packet(tmp_path/'reuse',records=5,nominees=0,single_page=True,accept=monkeypatch,reuse=True,supervised=False)


def test_explicit_installed_shape_and_original_modes(inputs):
    path,h=inputs;v=p.validate(path,h,disposable=True)
    assert v['package']['version']==p.VERSION_INSTALLED and 'transition' not in v['package']
    assert len(v['source']['records'])==5
    files=r.original_files(v['package'],path.parent)
    assert set(files)==set(r.FILES)
    assert activation_gate()==ACTIVATION.read_text().split('ALTER ROLE ingestion_worker_login LOGIN;')[0]+'ROLLBACK;'


@pytest.mark.parametrize('key,value',[('authority','OTHER'),('registration_sha256','0'*64),('failed_package_sha256','0'*64),('failed_release_id','OTHER'),('role_settings',[])])
def test_closed_historical_target_refuses(inputs,key,value):
    path,_=inputs;v=json.loads(path.read_bytes());v['reuse'][key]=value;raw=p.canonical(v);path.write_bytes(raw)
    with pytest.raises(Denied,match='REUSE_BINDING'):p.validate(path,p.sha(raw),disposable=True)


@pytest.mark.parametrize('change',[lambda x:x.update(version=p.VERSION_CAPTURE_SCREENING),lambda x:x.update(operation='ADMISSION'),lambda x:x.update(transition={}),lambda x:x.update(release_id=r.FAILED_RELEASE)])
def test_mode_cannot_auto_fallback(inputs,change):
    path,_=inputs;v=json.loads(path.read_bytes());change(v);raw=p.canonical(v);path.write_bytes(raw)
    with pytest.raises(Denied):p.validate(path,p.sha(raw),disposable=True)


def test_original_files_hash_failure_is_precredential(inputs):
    path,h=inputs;v=json.loads(path.read_bytes());f=path.parent/v['reuse']['original_result']['name'];f.write_bytes(b'changed')
    with pytest.raises(Denied,match='INPUT_HASH'):p.validate(path,h,disposable=True)


def test_atomic_gate_not_silently_enabled_for_historical_mode():
    assert Lifecycle(None,None).atomic_gate is False
    with pytest.raises(Denied):Lifecycle(None,None,atomic_gate=True)
    assert Lifecycle(None,None,capture_screening_only=True,atomic_gate=True).atomic_gate is True


def test_reviewed_historical_registration_is_exact_and_zero_source_calls():
    from types import SimpleNamespace
    g,a=r.expected_historical(SimpleNamespace(q=lambda *args:[('p'*64,)]),None)
    assert g['source_calls']==g['writes']==a['source_cap']==a['write_cap']==0
    assert a['evidence']['registration_sha256']==r.REGISTRATION
    assert digest(a['package']['registration'])==r.REGISTRATION


def test_atomic_gate_sends_no_transaction_controls():
    from types import SimpleNamespace
    sent=[]
    life=Lifecycle(SimpleNamespace(q=lambda c,q:sent.append(q)),None,capture_screening_only=True,atomic_gate=True)
    life.gate(None,inside_transaction=True)
    assert len(sent)==3 and sent[-1].lstrip().startswith('DO $gate$')
    assert all('BEGIN;' not in s[:10] and s.strip()!='ROLLBACK;' for s in sent)


@pytest.mark.parametrize('key',['source','outer','qualification','origin','owner_acceptance'])
def test_live_packet_guard_refuses_same_window_substitution(key):
    old={k:{'name':k+'.json','sha256':'a'*64} for k in ('source','outer','qualification')}
    old.update(origin={'commit':'a'*40},owner_acceptance='ACCEPTED_FIXED_WINDOW',scope={'start':'2026-10-15','end':'2026-10-21'})
    fresh=deepcopy(old)
    r.require_retained_packet(fresh,old) # same function called exclusively by LIVE validation; fixture hashes are not qualification
    if key in ('source','outer','qualification'):fresh[key]['sha256']='b'*64
    else:fresh[key]='SUBSTITUTED'
    with pytest.raises(Denied,match='RETAINED_PACKET'):r.require_retained_packet(fresh,old)
