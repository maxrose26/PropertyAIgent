import copy
import pytest
from verification.ingestion_storage import owner_pilot as p,owner_pilot_continuation as step

def closed():
    from verification.ingestion_storage import intake_owner as op
    return dict(period=p.PREDECESSOR,status='CLOSED',pipeline_status='NOT_VERIFIED',
        failure=dict(phase='ONE_JOB',exception_class='ReadTimeout',reason='UNKNOWN_FAILURE',sqlstate=None,status='RECONCILIATION_REQUIRED'),
        job={'id':'job-dbl7bs7b9u1s73dp48sg'},job_terminal={'status':'failed'},deployment='dep-dbl6kfdbedkc7385k7t0',
        binding={'execution_binding':{'revision':'681f1a1cc886eb09efe70020dd34829f15e3817d'}},
        access={'state':'DATABASE_CLOSURE_ACKNOWLEDGED'},
        closure_receipt=dict(outcome='COMMIT_ACKNOWLEDGED',sessions='ABSENT',temporary_owner='REMOVED',password_verifiers='RETAINED'),
        stable_credentials=dict(version='STABLE_RESTRICTED_V1',passwords={r:'SYNTHETIC_ONLY' for r in op.ROLES},verifier_sha256={r:'a'*64 for r in op.ROLES}),
        final_service=dict(suspended=True,configuration_equal=True,environment_equal=True),
        intents={k:{'state':'ACKNOWLEDGED'} for k in ('PERIOD','ACTIVATE','HANDOFF','ONE_JOB')})

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
    if drift=='failure':state['failure']['phase']='QUALIFY'
    if drift=='closure':state['closure_receipt']['outcome']='UNKNOWN'
    with pytest.raises(p.op.Denied,match='CONTINUATION_PREDECESSOR'):step.predecessor(state)
