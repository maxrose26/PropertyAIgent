import copy
import pytest
from verification.ingestion_storage import owner_pilot as p,owner_pilot_continuation as step

def closed():
    return dict(period=p.PREDECESSOR,status='CLOSED',pipeline_status='NOT_VERIFIED',failure=dict(phase='QUALIFY',exception_class='Denied',reason='UNKNOWN_FAILURE'),
        access={'state':'DATABASE_CLOSURE_ACKNOWLEDGED'},closure_receipt=dict(outcome='COMMIT_ACKNOWLEDGED',sessions='ABSENT',temporary_owner='REMOVED'),
        final_service=dict(suspended=True,configuration_equal=True,environment_equal=True),intents={'RELEASE':{},'QUALIFY':{}})

def test_closed_predecessor_binding_preserves_bytes_and_fixed_window():
    state=closed();before=copy.deepcopy(state);link=step.predecessor(state)
    assert state==before and link['period']==p.PREDECESSOR and link['execution_identity']==p.PERIOD and p.PERIOD!=p.PREDECESSOR
    assert p.WINDOW=={'start':'2026-10-27','end':'2026-11-02'}
    assert p.Journal(None).owner_period!=p.Journal(None,p.PREDECESSOR).owner_period

@pytest.mark.parametrize('drift',['job','handoff','open','failure','closure'])
def test_uncertain_or_source_started_predecessor_refuses(drift):
    state=closed()
    if drift=='job':state['job']={'id':'previous'}
    if drift=='handoff':state['intents']['HANDOFF']={}
    if drift=='open':state['status']='OPEN'
    if drift=='failure':state['failure']['phase']='ONE_JOB'
    if drift=='closure':state['closure_receipt']['outcome']='UNKNOWN'
    with pytest.raises(p.op.Denied,match='CONTINUATION_PREDECESSOR'):step.predecessor(state)
