import copy,json
from pathlib import Path
import pytest
from verification.ingestion_storage import owner_pilot as p,owner_pilot_continuation as step
SNAPSHOT={'ordinal':46,'bytes':29084,'sha256':'313352066984874f46af4f9cb767caab2cc17d220ac9d694127fee3b8bd51631'}
def closed():return json.loads((Path(__file__).parent/'fixtures/attempt04-closed-sanitized.json').read_text())
def test_closed_predecessor_binding_preserves_bytes_and_fixed_window():
    state=closed();before=copy.deepcopy(state);link=step.predecessor(state,snapshot=SNAPSHOT)
    assert state==before and link['period']==p.PREDECESSOR and link['execution_identity']==p.PERIOD and p.PERIOD!=p.PREDECESSOR
    assert p.WINDOW=={'start':'2026-10-27','end':'2026-11-02'}
    assert p.Journal(None).owner_period!=p.Journal(None,p.PREDECESSOR).owner_period
@pytest.mark.parametrize('drift',['job','handoff','open','snapshot','closure'])
def test_uncertain_or_source_started_predecessor_refuses(drift):
    state=closed();snapshot=copy.deepcopy(SNAPSHOT)
    if drift=='job':state['job']={'id':'unexpected'}
    if drift=='handoff':state['intents']['HANDOFF']={}
    if drift=='open':state['status']='OPEN'
    if drift=='snapshot':snapshot['sha256']='f'*64
    if drift=='closure':state['closure_receipt']['outcome']='UNKNOWN'
    with pytest.raises(p.op.Denied,match='CONTINUATION_PREDECESSOR'):step.predecessor(state,snapshot=snapshot)
