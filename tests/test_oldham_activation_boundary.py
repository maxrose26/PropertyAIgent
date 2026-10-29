"""Pure derivation and actual lifecycle ordering; no production or source calls."""
from types import SimpleNamespace
from contextlib import nullcontext
from unittest.mock import patch
import pytest,psycopg
from app.ingestion.ledger import Denied
from verification.ingestion_storage import activation_boundary as b
from verification.ingestion_storage.oldham_lifecycle import Lifecycle,activation_gate,ACTIVATION


def test_historical_three_login_gate_byte_unchanged():
    assert activation_gate()==ACTIVATION.read_text().split('ALTER ROLE ingestion_worker_login LOGIN;')[0]+'ROLLBACK;'
    assert 'STATISTICS_BASELINE_BOUNDARY' not in activation_gate()
    gate=activation_gate(True)
    assert 'STATISTICS_BASELINE_BOUNDARY' in gate and 'pg_stat_statements' in gate
    assert "NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='ingestion_recovery_login'" not in gate
    assert "recovery_session.usename='ingestion_recovery_login'" in gate and 'recovery_session.usesysid IS NOT NULL' in gate
    assert 'pg_read_all_stats' in gate and "e.extversion='1.11'" in gate


def test_control_volatility_from_authoritative_sql():
    assert b.reviewed_control_attributes()==dict(language='sql',volatility='v',security_definer=True)


@pytest.mark.parametrize('message,state,expected',[
    ('AMBIENT_UNRELATED_TABLE_ACCESS','P0001','AMBIENT_UNRELATED_TABLE_ACCESS'),
    ('RECOVERY_MUST_REMAIN_DORMANT','P0001','RECOVERY_MUST_REMAIN_DORMANT'),
    ('STATISTICS_FUNCTION_BOUNDARY','P0001','STATISTICS_FUNCTION_BOUNDARY'),
    ('PRIVATE MESSAGE with secret','P0001',None),
    ('STATISTICS_FUNCTION_BOUNDARY extra','P0001',None),
    ('STATISTICS_FUNCTION_BOUNDARY','42501',None),
])
def test_fixed_primary_code_only(message,state,expected):
    class Native(psycopg.Error):
        sqlstate=state
        @property
        def diag(self):return SimpleNamespace(message_primary=message)
    assert b.fixed_gate_reason(Native('PRIVATE_EXCEPTION_DETAIL'))==expected
    assert b.fixed_gate_reason(RuntimeError(message)) is None


@pytest.mark.parametrize('reason',sorted(b.GATE_CODES))
def test_gate_failure_precedes_password_and_mapping(reason):
    class Native(psycopg.Error):
        sqlstate='P0001'
        @property
        def diag(self):return SimpleNamespace(message_primary=reason)
    events=[]
    from datetime import datetime,timezone,timedelta
    o=SimpleNamespace(effect_uncertain=False,authorities=['a'],invalidation='REQUIRED',awaiting_verification=False,
        valid_until=datetime.now(timezone.utc)+timedelta(minutes=5),expiry=None,admin_phase=lambda:nullcontext(),connection=lambda:nullcontext(object()),emit=lambda *x:events.append(x))
    def q(c,query,*a,**kw):
        if isinstance(query,str) and query.startswith('SELECT outcome'):return [({'oldham_allowances':{'a':{'revoked':False,'expires_at':o.valid_until.timestamp()}}},)]
        if isinstance(query,str) and query.lstrip().startswith('DO '):raise Native('PRIVATE_EXCEPTION_DETAIL')
        return []
    o.q=q
    life=Lifecycle(o,SimpleNamespace(names=lambda:['DATABASE_URL'],put_secret=lambda *a:pytest.fail('MAPPING_BEFORE_GATE')),capture_screening_only=True)
    life.observed=lambda c:dict(roles=[(r,False,True,None,False,False,False,False,False,1) for r in life.roles],memberships=[],sessions=[])
    with patch('verification.ingestion_storage.oldham_lifecycle.verify_inventory'),patch('verification.ingestion_storage.oldham_authority.stop_identity'),patch('verification.ingestion_storage.oldham_lifecycle.secrets.token_urlsafe',side_effect=AssertionError('MINT_BEFORE_GATE')):
        with pytest.raises(Denied,match='^'+reason+'$'):life.activate(url_factory=lambda *a:pytest.fail('URL_BEFORE_GATE'))
    assert life.state=='UNCERTAIN'
    assert events==[('activation_gate_refused',dict(reason_code=reason,message_exported=False))]


def test_actual_diagnostic_patch_predicate_and_changed_attributes():
    from pathlib import Path
    patch=Path('docs/design/oldham-activation-correction-20261028/reconciliation-volatility.patch').read_text()
    before=next(line[1:].strip() for line in patch.splitlines() if line.startswith('-        safe='))
    after=next(line[1:].strip() for line in patch.splitlines() if line.startswith('+        safe='))
    assert before.replace("r[9]=='s'", "r[9]=='v'")==after
    expected='a'*64
    good=['ingestion_acceptance_control',expected,'ingestion_storage_owner',['search_path=pg_catalog'],True,'',False,False,'sql','v']
    def check(row):
        namespace=dict(funcs=[row],expected=expected)
        exec(compile(after,'corrected-diagnostic-control','exec'),namespace)
        return namespace['safe']
    assert check(good)
    for field,value in ((9,'s'),(9,'i'),(8,'plpgsql'),(4,False),(2,'OTHER_OWNER'),(1,'b'*64),(3,[])):
        changed=list(good);changed[field]=value
        assert not check(changed)


def test_search_path_pin_is_confined_to_the_provider_block_and_adds_nothing_else():
    gate=activation_gate(True);pin="PERFORM set_config('search_path','pg_catalog',true);";restore="PERFORM set_config('search_path',stats_path,true);"
    assert gate.count(pin)==1 and gate.count(restore)==1 and gate.count("stats_path:=current_setting('search_path');")==1 and 'stats_path text;' in gate
    start,end=gate.index("stats_path:=current_setting('search_path');"),gate.index(restore)+len(restore)
    block=gate[start:end]
    assert "md5(pg_get_viewdef(stats.oid,true))<>stats.expected" in block and "RAISE EXCEPTION 'STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED'" in block and "RAISE EXCEPTION 'STATISTICS_FUNCTION_BOUNDARY'" in block
    assert "RAISE EXCEPTION 'STATISTICS_BASELINE_BOUNDARY'" in block and gate.count('pg_get_viewdef')==1      # the only search_path-sensitive construct is inside the pinned block
    outside=gate[:start]+gate[end:]
    assert "set_config(" not in outside and 'pg_get_viewdef' not in outside and 'search_path' not in outside.replace("current_setting('search_path')",'')
    assert "e.extversion='1.11'" in block and 'ad1495ce5b4c54e4501e907a1f6aae8c' in block and '1807985dc152d2828720e1272d549775' in block      # reviewed hashes unchanged, none added
    assert gate.count('md5(')==1 and gate.count('ad1495ce5b4c54e4501e907a1f6aae8c')==1 and gate.count('1807985dc152d2828720e1272d549775')==1


def test_pin_does_not_alter_the_other_gate_codes_or_the_historical_gates():
    import re
    gate=activation_gate(True)
    for code in ('LOGIN_FLAGS_OR_PARTIAL_ACTIVATION','EXACT_RUNTIME_MEMBERSHIP','FORBIDDEN_RUNTIME_MEMBERSHIP','AMBIENT_SCHEMA_CREATE','AMBIENT_UNRELATED_TABLE_ACCESS','AMBIENT_UNRELATED_SEQUENCE','AMBIENT_UNREVIEWED_DEFINER',
                 'WORKER_DIRECT_LEDGER_MUTATION','REQUIRED_RUNTIME_FUNCTION_MISSING','RECOVERY_MUST_REMAIN_DORMANT','STATISTICS_BASELINE_BOUNDARY','STATISTICS_OBJECT_OR_PRIVILEGE_CHANGED','STATISTICS_FUNCTION_BOUNDARY'):
        assert "RAISE EXCEPTION '%s'"%code in gate,code
    unpinned=re.sub(r"  stats_path:=current_setting\('search_path'\);\n  PERFORM set_config\('search_path','pg_catalog',true\);\n",'',gate).replace("  PERFORM set_config('search_path',stats_path,true);\n",'').replace(' stats_path text;','')
    assert 'set_config' not in unpinned and 'stats_path' not in unpinned and len(gate)-len(unpinned)<400      # removing exactly the pin yields the previous gate text
    assert activation_gate()==ACTIVATION.read_text().split('ALTER ROLE ingestion_worker_login LOGIN;')[0]+'ROLLBACK;'      # the historical three-login gate is byte-unchanged
