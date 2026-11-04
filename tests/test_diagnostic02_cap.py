"""Scoped real journal/Vault guards; no external effects."""
import copy,hashlib
import pytest
from verification.ingestion_storage import owner_pilot as p,owner_qualification as q
from verification.ingestion_storage.intake_owner_io import Vault
from verification.ingestion_storage.database_evidence import DEADLINE_OWNER_SQL,DIAGNOSTIC02_CAP_OWNER_SQL
from tests.test_attempt04_cleanup_capacity import MemoryDB

def journal(monkeypatch,version=None):
    monkeypatch.setattr(p,'PERIOD',q.IDENTITY);monkeypatch.setattr(p,'PREDECESSOR',q.PREDECESSOR)
    db=MemoryDB();j=p.Journal(db,q.IDENTITY)
    s=dict(period=q.IDENTITY,status='ARTIFACT_READY',intents={},access={},cleanup_reserve=dict(p.cleanup_reserve_policy(q.IDENTITY,version),cleanup_writes=0))
    raw=j._vault(value=s);db.rows=[(17,raw,hashlib.sha256(raw).hexdigest())];j.load();return j,s

def test_scoped_policy_and_historical_immutability(monkeypatch):
    old=p.cleanup_reserve_policy();new=p.cleanup_reserve_policy(q.IDENTITY)
    assert old['normal_plaintext_ceiling']==16534 and new['normal_plaintext_ceiling']==19606
    assert all(old[k]==new[k] for k in old if k not in ('version','normal_plaintext_ceiling'))
    assert p.cleanup_reserve_policy(q.PREDECESSOR)==old
    j,s=journal(monkeypatch,'CLEANUP_RESERVE_V1');before=copy.deepcopy(j.db.rows)
    s['cleanup_reserve']=dict(new,cleanup_writes=0)
    with pytest.raises(p.op.Denied,match='IMMUTABLE'):j.save(s)
    assert j.db.rows==before and j.load()['cleanup_reserve']['version']=='CLEANUP_RESERVE_V1'

def test_actual_journal_bound_roundtrip_and_full_cleanup(monkeypatch):
    j,s=journal(monkeypatch);s['padding']='';s['padding']='x'*(19606-p.state_size(s))
    assert j.save(s,validate_only=True)==26248
    j.save(s);old=copy.deepcopy(j.db.rows)
    too=copy.deepcopy(s);too['padding']+='x'
    with pytest.raises(p.op.Denied,match='RESERVE_BYTE_BOUND'):j.save(too)
    assert j.db.rows==old
    for k,n in p.CLEANUP_RECORD_LIMITS.items():
        v={'padding':''};v['padding']='x'*(n-len(p.canonical(v)));s[k]=v
    j.cleanup_mode=True
    for _ in range(16):j.save(s)
    assert j.load()==s and j.db.rows[:len(old)]==old
    assert max(len(r[1]) for r in j.db.rows)<=36864
    with pytest.raises(p.op.Denied,match='ROW_BOUND'):j.save(s)
    print('CAP_MAX',max(len(r[1]) for r in j.db.rows),'FINAL_ORDINAL',j.ordinal)

def test_other_vaults_stay_32k(tmp_path):
    v=Vault(tmp_path/'legacy','x'*32,create=True)
    with pytest.raises(p.op.Denied,match='32K'):v.save({'padding':'x'*26000})

def test_sql_amendment_is_only_scoped_limit():
    assert DIAGNOSTIC02_CAP_OWNER_SQL==DEADLINE_OWNER_SQL.replace('BETWEEN 1 AND 32768',"BETWEEN 1 AND (CASE WHEN p_period='b-qualification-20261104-02_owner' THEN 36864 ELSE 32768 END)")
    assert 'IF n>=64' in DIAGNOSTIC02_CAP_OWNER_SQL

def test_migration_refuses_changed_journal_before_external_mutation(monkeypatch):
    obj=object.__new__(q.Qualification);j,s=journal(monkeypatch);obj.journal=j
    obj.preflight=lambda:pytest.fail('REACHED_PREFLIGHT')
    with pytest.raises(p.op.Denied,match='PRIOR_INTENT'):obj.amend_capacity()

def test_scoped_oversize_diagnostic(monkeypatch):
    j,s=journal(monkeypatch);s['padding']='x'*30000
    with pytest.raises(p.op.Denied,match='VAULT_36K_BOUND') as caught:j._vault(value=s)
    assert p.safe_result(caught.value)['reason']=='VAULT_36K_BOUND'

def test_cap_action_dispatch_is_bounded_and_not_run(monkeypatch):
    from app import owner_intake_control as control
    monkeypatch.setenv('PROPERTYAIGENT_INTAKE_PREPARE_ONCE','QUALIFICATION-CAP:'+q.IDENTITY)
    monkeypatch.setattr(control,'_process',None)
    calls=[]
    monkeypatch.setattr(control.subprocess,'Popen',lambda command,**kw:calls.append(command))
    control.start('qualification-cap',server_prepare=True)
    assert len(calls)==1 and '60s' in calls[0] and calls[0][-1]=='qualification-cap' and '--owner-checked-at' not in calls[0]
