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


def test_inactive_preparation_enforces_existing_bounds_before_read(tmp_path):
    import runpy
    module=runpy.run_path('docs/design/oldham-activation-correction-20261028/prepare_inactive.py')
    path=tmp_path/'oversized'
    with path.open('wb') as f:f.truncate(1024**2+1)
    with pytest.raises(SystemExit,match='INPUT_FILE_BOUND'):module['checked_file'](path,1024**2)
    target=tmp_path/'link';target.symlink_to(path)
    with pytest.raises(SystemExit,match='INPUT_FILE_BOUND'):module['checked_file'](target,2*1024**2)


def test_actual_preparation_argument_flow_refuses_symlink(tmp_path,monkeypatch):
    import runpy
    from pathlib import Path
    module=runpy.run_path('docs/design/oldham-activation-correction-20261028/prepare_inactive.py')
    original=p.git;monkeypatch.setattr(p,'git',lambda *a:'' if a==('status','--porcelain') else original(*a))
    assets=tmp_path/'assets';assets.mkdir();(assets/'failed-claim.json').write_text('{}')
    target=tmp_path/'result.json';target.write_text('{}');link=tmp_path/'result-link.json';link.symlink_to(target)
    out=tmp_path/'unused'
    with pytest.raises(SystemExit,match='INPUT_FILE_BOUND'):
        module['main'](['--checkout',str(Path.cwd()),'--assets',str(assets),'--original-result',str(link),'--original-audit',str(target),'--reconciliation',str(target),'--output',str(out),'--evidence-head','a'*40,'--release-id','oldham-owner-inactive-test'])
    assert link.is_symlink() and not out.exists()


def test_fixture_keeps_reviewed_history_key_separate_from_synthetic_work(inputs):
    from tests.oldham_wrapper_fixture import Backend
    from types import SimpleNamespace
    from app.ingestion import owner_acceptance
    path,_=inputs;backend=Backend(path)
    assert backend.p['owner_acceptance']!='OLDHAM_RECEIVED_20261015_20261021_V1'
    assert owner_acceptance.require(backend.p['owner_acceptance']).key==backend.p['owner_acceptance']
    grant,allowance=r.expected_historical(SimpleNamespace(q=lambda *a:[('p'*64,)]),None)
    assert allowance['evidence']['registration_sha256']==r.REGISTRATION and grant['source_calls']==0


def test_reuse_failure_export_uses_existing_fixed_codes_without_raw_text():
    from types import SimpleNamespace
    from verification.ingestion_storage.oldham_owner_once import Operation
    for exc,expected in ((Denied('OLDHAM_REUSE_POLICY_ATTRIBUTES'),'OLDHAM_REUSE_POLICY_ATTRIBUTES'),(RuntimeError('PRIVATE_RAW_DETAIL'), 'UNKNOWN')):
        obj=SimpleNamespace(installed_reuse=True,stage='INSTALLED_POLICY_CLEANUP',caller=None,owner=None,life=None,runtime_uncertain=False,github=SimpleNamespace(bound=0,mutation_uncertain=False),result={})
        obj.finish=lambda:obj.result
        value=Operation.failed(obj,exc)
        assert value['failure']['reason_code']==expected and value['failure']['message_exported'] is False
        assert 'PRIVATE_RAW_DETAIL' not in str(value) and value['cleanup']=='UNCERTAIN'


def test_provider_presence_uses_catalogue_without_schema_usage():
    from verification.ingestion_storage.oldham_lifecycle import activation_gate
    gate=activation_gate(capture_screening_only=True)
    assert "to_regclass('extensions." not in gate
    assert "n.nspname='extensions' AND c.relname IN ('pg_stat_statements','pg_stat_statements_info')" in gate
    assert 'STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED' in gate

def test_historical_cleanup_required_for_successor_closure():
    from pathlib import Path
    reuse=Path('verification/ingestion_storage/oldham_reuse.py').read_text()
    assert reuse.index("self.life.state='UNCERTAIN'") < reuse.index('names=self.op.github.names()')
    owner=Path('verification/ingestion_storage/oldham_owner_once.py').read_text()
    assert "historical_closed=not self.installed_reuse or self.result.get('historical_cleanup',{}).get('readback')=='VERIFIED'" in owner
