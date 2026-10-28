"""Pure bindings; no DB/network/kernel proof. Inspection/source stand-ins are labelled."""
import json
from types import SimpleNamespace
import pytest
from app.ingestion.ledger import Denied
from tests.oldham_wrapper_fixture import packet
from verification.ingestion_storage import oldham_owner_package as pkg,oldham_transition as t,oldham_policy
from verification.ingestion_storage.oldham_lifecycle import activation_gate,ACTIVATION,Lifecycle
from verification.ingestion_storage.operational_publication import canonical


@pytest.fixture
def inputs(tmp_path,monkeypatch):
    original=pkg.git
    monkeypatch.setattr(pkg,'git',lambda *a:'' if a==('status','--porcelain') else original(*a))
    return packet(tmp_path/'inputs',records=5,nominees=0,single_page=True,accept=monkeypatch,transition=True,supervised=False)


def rewritten(path,p):
    raw=canonical(p);path.write_bytes(raw);return pkg.sha(raw)


def test_sealed_two_login_packet(inputs):
    path,sha=inputs;d=pkg.validate(path,sha,disposable=True)
    assert d['package']['operation']==t.OPERATION and len(d['source']['records'])==5
    assert d['package']['risk_acceptance']==t.RISK


@pytest.mark.parametrize('mutation',[
    lambda p:p.update(operation='ADMISSION'),
    lambda p:p['transition'].update(predecessor='COMBINED_V3_PARTIAL'),
    lambda p:p['transition'].update(retire_standing=False),
    lambda p:p['transition'].update(external_consumers_confirmed=False),
    lambda p:p['transition'].update(installation_sha256='0'*64),
    lambda p:p['transition'].update(rollback_sha256='0'*64),
    lambda p:p.update(risk_acceptance=pkg.RISK),
])
def test_substitutions_refuse_before_credentials(inputs,mutation):
    path,_=inputs;p=json.loads(path.read_bytes());mutation(p)
    with pytest.raises((Denied,ValueError)):pkg.validate(path,rewritten(path,p),disposable=True)


def test_invalid_private_inspection_refuses(inputs):
    path,_=inputs;p=json.loads(path.read_bytes());value=json.loads((path.parent/'inspection.json').read_bytes())
    value['outcome']['closure']='UNCERTAIN';raw=canonical(value);(path.parent/'inspection.json').write_bytes(raw)
    p['transition']['inspection']['sha256']=pkg.sha(raw)
    with pytest.raises(Denied,match='COMPLETED_INSPECTION'):pkg.validate(path,rewritten(path,p),disposable=True)


def test_exact_predecessor_rollback_and_unchanged_default():
    from verification.ingestion_storage import screening_v3_worker_sql as v3,observation_worker_sql as obs
    _,rollback=t.texts(t.PREDECESSOR)
    extract=lambda s:s.split('AS $fn$',1)[1].split('$fn$;',1)[0]
    assert extract(rollback)==extract(v3.replacement_function())
    assert extract(oldham_policy.rollback_script())==extract(v3.original_function(obs.combined()))
    assert extract(rollback)!=extract(oldham_policy.rollback_script())


def test_activation_gate_is_narrower_without_changing_legacy():
    assert activation_gate()==ACTIVATION.read_text().split('ALTER ROLE ingestion_worker_login LOGIN;')[0]+'ROLLBACK;'
    two=activation_gate(True)
    assert "('ingestion_application_login','ingestion_application_writer')" not in two
    assert 'APPLICATION_COLUMN_EXPANSION' not in two
    assert all(x in two for x in ('AMBIENT_UNREVIEWED_DEFINER','WORKER_DIRECT_LEDGER_MUTATION','FORBIDDEN_RUNTIME_MEMBERSHIP','REQUIRED_RUNTIME_FUNCTION_MISSING'))
    life=Lifecycle(None,None,capture_screening_only=True)
    assert set(life.roles)=={'ingestion_worker_login','ingestion_effect_login'}
    assert set(life.secrets.values())=={'INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL'}


def test_caller_constructs_only_two_engines_and_refuses_admission():
    from verification.ingestion_storage.chain_caller import ChainCaller
    from app.ingestion.listing_screening import ScreeningRule,RULE_V3
    caller=ChainCaller(SimpleNamespace(council='oldham'),None,ScreeningRule(RULE_V3,unit_threshold=10,link_related=False),
        {'ingestion_worker_login':'worker','ingestion_effect_login':'effect'},revision='1'*40,bindings={},capture_authority='capture',chain_authority='',capture_screening_only=True)
    from unittest.mock import patch
    seen=[]
    budget=SimpleNamespace(engine=lambda url,**kw:seen.append(url) or object())
    with patch('verification.ingestion_storage.chain_caller.ControllerLedger'),patch('verification.ingestion_storage.chain_caller.Coordinator'):
        caller._coordinator(budget,'authority',{})
    assert seen==['worker','effect']
    for f,args in [(caller.prepare,(None,)),(caller.admit,(None,None)),(caller.closed_idox_detail,(None,))]:
        with pytest.raises(Denied,match='CAPTURE_SCREENING_NO_'):f(*args,**({'root':None} if f==caller.closed_idox_detail else {}))
