"""Focused offline contract tests, synthetic data and frozen owner codec."""
import copy
import hashlib
import os
from pathlib import Path

import pytest

from verification.ingestion_storage import tameside_journal_capacity as cap
from verification.ingestion_storage import tameside_owner_journal as ja
from verification.ingestion_storage.tameside_preparation import pinned_modules


@pytest.fixture
def frozen():
    root=os.environ.get('S4_BOLTON_PINNED_CHECKOUT')
    if not root:pytest.skip('exact frozen checkout required')
    return pinned_modules(Path(root))


def journal(p):
    class DB:
        key=hashlib.sha256(b'synthetic-offline-key-only').hexdigest()
    return ja._bound_journal(p,DB(),capacity50=True)


def state(p, upgraded=False):
    value=dict(period=cap.plan.PERIOD,cleanup_reserve=dict(p.cleanup_reserve_policy(),cleanup_writes=0))
    if upgraded:
        value[cap.FIELD]=cap.marker()
        value['cleanup_reserve']=dict(cap.policy(p),cleanup_writes=0)
    return value


def test_exact_policy_preserves_cleanup(frozen):
    p,_,_=frozen
    old=p.cleanup_reserve_policy();new=cap.policy(p)
    assert {k for k in old if old[k]!=new[k]}=={'normal_plaintext_ceiling'}
    assert new['reserved_snapshots']==16 and new['growth_bytes']==6937 and new['margin_bytes']==1024
    n=new['normal_plaintext_ceiling']
    assert p.ciphertext_size(n+7961)<=51200<p.ciphertext_size(n+7962)


def test_codec_old_compatibility_and_larger_reopen(frozen):
    p,_,_=frozen;j=journal(p)
    old=state(p);raw=j._vault(value=old)
    assert j._vault(raw=raw)==old
    larger=state(p,True);larger['synthetic_uncompressed']='x'*27000
    encoded=j._vault(value=larger)
    assert 32768<len(encoded)<=51200
    assert journal(p)._vault(raw=encoded)==larger
    assert j._vault(raw=raw)==old
    original=p.Journal(j.db,period=p.PERIOD)
    with pytest.raises(Exception,match='PRIVATE_VAULT_REQUIRED'):original._vault(raw=encoded)


def test_scope_marker_and_install_refusals(frozen):
    p,_,_=frozen;j=journal(p);s=state(p,True)
    with pytest.raises(Exception,match='CAPACITY_INSTALL_READBACK_REQUIRED'):j.save(s)
    bad=copy.deepcopy(s);bad[cap.FIELD]['ciphertext_limit']=65536
    with pytest.raises(Exception,match='CAPACITY_MARKER'):j.save(bad,validate_only=True)
    j.state=s
    with pytest.raises(Exception,match='CAPACITY_DOWNGRADE'):j.save(state(p),validate_only=True)
    j.owner_period='another_owner'
    with pytest.raises(Exception,match='CAPACITY_NAMESPACE'):j._vault(value=s)


def test_normal_and_cleanup_boundaries(frozen):
    p,_,_=frozen;j=journal(p);s=state(p,True);s['padding']=''
    n=cap.policy(p)['normal_plaintext_ceiling']
    s['padding']='x'*(n-p.state_size(s))
    assert p.state_size(s)==n
    j.ordinal=20;j.state=copy.deepcopy(s)
    assert j.save(copy.deepcopy(s),validate_only=True)<=51200
    large=copy.deepcopy(s);large['padding']+='x'
    with pytest.raises(Exception,match='OWNER_CLEANUP_RESERVE_BYTE_BOUND'):j.save(large,validate_only=True)
    j.ordinal=47;j.cleanup_mode=True
    for k,limit in p.CLEANUP_RECORD_LIMITS.items():s[k]='x'*(limit-2)
    for _ in range(16):
        value=copy.deepcopy(s);assert j.save(value,validate_only=True)<=51200
        j.ordinal+=1;j.state=value;s=value
    with pytest.raises(Exception,match='OWNER_CLEANUP_ROW_BOUND'):j.save(copy.deepcopy(s),validate_only=True)


def test_sql_only_changes_exact_namespace_and_guarded_used_upgrade(frozen):
    _,_,source=frozen;old,new=cap.definitions(source)
    assert new.replace("(CASE WHEN p_period='"+ja.JOURNAL+"' THEN 51200 ELSE ", '',1).replace(' END) THEN RAISE EXCEPTION \'OWNER_STATE_VAULT_BOUND\'', ' THEN RAISE EXCEPTION \'OWNER_STATE_VAULT_BOUND\'',1)==old
    assert 'THEN 36864 ELSE 32768' in new  # historical exception unchanged
    sql=cap.upgrade_sql(source,journal_sha='a'*64)
    assert 'owner/state-018' in sql and 'owner/state-019' in sql
    assert 'CREATE OR REPLACE FUNCTION' in sql and 'OWNER_WRITER_CAPABILITY_REMAINS' in sql
    assert "n>=64" in sql and 'OWNER_STATE_CONCURRENT_OR_UNCERTAIN' in sql


def test_expired_upgrade_refuses_before_intent_or_sql(monkeypatch):
    class Runner:
        state={}
        def inspect(self):return None
        def save(self):raise AssertionError('unexpected write')
    monkeypatch.setattr(cap.time,'time',lambda:10**12)
    with pytest.raises(ValueError,match='CAPACITY_OPERATIONAL_WINDOW_ELAPSED'):
        cap.upgrade(Runner(),'not reached')
