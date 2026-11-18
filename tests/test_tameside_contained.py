"""Exact contained-phase codec and first/secondary error reporting, offline only."""
import copy
from types import SimpleNamespace
import pytest
from tests.test_tameside_journal_capacity import frozen,journal,state
from verification.ingestion_storage import tameside_contained as cc
from verification.ingestion_storage import tameside_stop15_run as run


def resumed(p):
    j=journal(p);v=state(p,upgraded=True)
    v['cleanup_reserve'].update(cleanup_writes=7,cleanup_base_bytes=1000,cleanup_base_access_bytes=2)
    j.state=copy.deepcopy(v);j.ordinal=34;j.previous=cc.CHECKPOINT
    r=SimpleNamespace(state=v,journal=j,approval_ref='approved',review_ref='reviewed')
    v['bound_at']=123;v['binding']={'old':'binding'}
    cc.admit(r)
    return j,v


def test_scoped_resume_preserves_counter_and_closes_permanently(frozen):
    p,_,_=frozen;j,v=resumed(p)
    old=copy.deepcopy(j.state)
    j.save(v,validate_only=True)
    assert v['cleanup_reserve']['cleanup_writes']==7
    assert old['cleanup_reserve']==j.state['cleanup_reserve']
    # Independently durable normal-state projection, not enlarged cleanup input.
    v['access']={'synthetic':'x'*1000}
    j.ordinal=35;j.state=copy.deepcopy(v);j.cleanup_mode=True
    end=copy.deepcopy(v);j.save(end,validate_only=True)
    assert end['cleanup_reserve']['cleanup_writes']==8
    assert end['cleanup_reserve']['cleanup_base_bytes']==p.state_size(v)
    assert end['cleanup_reserve']['cleanup_base_access_bytes']==len(p.canonical(v['access']))
    assert end[cc.FIELD]['phase']=='CLEANUP'
    j.state=copy.deepcopy(end);j.ordinal=36
    again=copy.deepcopy(end);j.save(again,validate_only=True)
    assert again['cleanup_reserve']['cleanup_writes']==9
    assert again['cleanup_reserve']['cleanup_base_bytes']==end['cleanup_reserve']['cleanup_base_bytes']
    j.cleanup_mode=False
    with pytest.raises(Exception,match='OWNER_NO_NORMAL_AFTER_CLEANUP'):j.save(again,validate_only=True)


def test_wrong_predecessor_and_mutated_marker_refuse(frozen):
    p,_,_=frozen;j,v=resumed(p);j.previous='0'*64
    with pytest.raises(Exception,match='OWNER_NO_NORMAL_AFTER_CLEANUP'):j.save(v,validate_only=True)
    j.previous=cc.CHECKPOINT;j.save(v,validate_only=True);j.state=copy.deepcopy(v);j.ordinal=35
    bad=copy.deepcopy(v);bad[cc.FIELD]['deployment']='dep-other'
    with pytest.raises(Exception,match='OWNER_NO_NORMAL_AFTER_CLEANUP'):j.save(bad,validate_only=True)


def test_original_exception_not_masked_and_secret_not_reported(monkeypatch,frozen):
    p,_,_=frozen
    from verification.ingestion_storage import stop15_replacement
    initial=RuntimeError('credential=SECRET_MUST_NOT_APPEAR')
    secondary=RuntimeError('other-secret')
    class Op:
        journal=object()
        def prepare(self):raise initial
        def contain(self):raise secondary
    op=Op();r=object.__new__(run.Continuation)
    r.pinned=p;r.sleep=lambda _:None;r.phase=lambda:None
    monkeypatch.setattr(stop15_replacement,'operation',lambda _:op)
    monkeypatch.setattr(run.plan,'read_journal',lambda _:dict(intents={}))
    with pytest.raises(RuntimeError) as caught:r.replacement()
    assert caught.value is initial
    assert initial.preparation_failure['exception_class']=='RuntimeError'
    assert initial.containment_failure['phase']=='CLEANUP'
    assert 'secret' not in str(initial.preparation_failure).lower()
    assert 'SECRET_MUST_NOT_APPEAR' not in str(initial.preparation_failure)
