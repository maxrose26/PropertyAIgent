"""Synthetic offline tests; no retained planning fact is invented here."""
import json
import socket
import subprocess
from types import SimpleNamespace
import pytest
from sqlalchemy import text, select
from app.db.models import Application, Site, BuyerMandate
from verification.buyer_dependency.safety import guarded_window, ObservationFailure
from verification.gate_b.safety import ReadOnlyViolation
from verification.buyer_dependency.observe import observe, encode, LIMITS
from tests.test_gate_b_validation import seed
from tests.test_buyer_family_feed import World
from tests.test_family_dashboard import treat_portal_estimates_as_exact
SHA='183570e0c940d28b51b9f05a5dbf47f56dff37b2'

@pytest.fixture
def populated(session,monkeypatch):
    treat_portal_estimates_as_exact(monkeypatch)
    world=World(session,monkeypatch)
    seed(world)
    for _ in range(7): world.site(outline_age=365*3-60,parent='I',units_out=50)
    world.allocation(capacity=100,fit='I')
    session.rollback()
    return session

def test_complete_actual_family_traversal(populated):
    artifact=observe(populated,code_sha=SHA,synthetic=True)
    assert artifact['execution_status']=='COMPLETE'
    assert artifact['counts']['buyers']==4
    assert artifact['counts']['families']>24
    assert artifact['counts']['MEMBER']>0
    assert artifact['counts']['REPRESENTATIVE']==artifact['counts']['families']
    assert len({r['buyer_id'] for r in artifact['records']})==4
    assert any(r['allocation_id'] and r['dependency_type']=='UNKNOWN' for r in artifact['records'])
    payload=encode(artifact)
    assert all(x not in payload for x in ['preferred_min','preferred_max','extracted_text','entity_name','canonical_address','display_name'])

@pytest.mark.parametrize('attempt',[
    lambda s:s.execute(text('DELETE FROM sites')),
    lambda s:s.execute(text('CREATE TABLE forbidden (id int)')),
    lambda s:s.execute(text('SELECT pg_sleep(20)')),
    lambda s:s.commit(),
    lambda s:(s.add(Site(council_code='testcouncil',canonical_address='x')),s.flush()),
    lambda s:socket.socket(),
    lambda s:subprocess.run(['true']),
    lambda s:__import__('openai'),
])
def test_prohibited_paths(session,attempt):
    session.rollback()
    with pytest.raises((ObservationFailure,ReadOnlyViolation)):
        with guarded_window(session,synthetic=True): attempt(session)

@pytest.mark.parametrize('mode',['rollback_read','rollback_only','query_overflow','deadline'])
def test_abort_paths(session,mode):
    session.rollback()
    with pytest.raises(ObservationFailure):
        with guarded_window(session,synthetic=True,max_queries=1 if mode=='query_overflow' else 30,seconds=.05 if mode=='deadline' else 2):
            if mode=='rollback_read': session.rollback(); session.execute(select(Site))
            elif mode=='rollback_only': session.rollback()
            elif mode=='query_overflow': session.execute(select(Site)); session.execute(select(Site))
            else:
                import time
                time.sleep(.1)
    assert not session.in_transaction()

def test_missing_mandate_fail_closed(populated):
    populated.query(BuyerMandate).filter(BuyerMandate.id==1).delete()
    populated.commit()
    with pytest.raises(ObservationFailure): observe(populated,code_sha=SHA,synthetic=True)

def test_output_overflow():
    with pytest.raises(ObservationFailure): encode({'records':['x'*LIMITS['bytes']]})

def test_buyer_scope_expectations(populated):
    with pytest.raises(ObservationFailure):
        observe(populated,code_sha=SHA,synthetic=True,expected_buyer_ids={1,2,3,4,5})

def test_textual_select_expression_denied(session):
    from sqlalchemy import literal_column
    session.rollback()
    with pytest.raises(ReadOnlyViolation):
        with guarded_window(session,synthetic=True): session.execute(select(literal_column('pg_sleep(20)')))

def test_preloaded_model_constructor_denied(session):
    import sys
    cls=sys.modules['openai'].OpenAI
    session.rollback()
    with pytest.raises(ObservationFailure):
        with guarded_window(session,synthetic=True): cls(api_key='SYNTHETIC_NOT_A_CREDENTIAL')

def test_extra_transaction_control_denied(session):
    session.rollback()
    with pytest.raises(ReadOnlyViolation):
        with guarded_window(session,synthetic=True): session.execute(text("SET LOCAL lock_timeout = '2s'; SELECT 1"))
