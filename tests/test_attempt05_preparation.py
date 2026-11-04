import copy,json
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from verification.ingestion_storage import owner_pilot as p,owner_pilot_continuation as step
from tests.test_owner_pilot_continuation import closed,SNAPSHOT

def test_successor_copies_only_stable_credentials_and_small_predecessor_reference(monkeypatch,capsys):
    old=closed();old['stable_configuration']={'outcome':'COMMIT_ACKNOWLEDGED'};old['large_closed_state']='x'*20000
    before=copy.deepcopy(old);events=[]
    @contextmanager
    def connection():yield object()
    pilot=object.__new__(p.Pilot);pilot.db=SimpleNamespace(connection=connection)
    pilot.journal=SimpleNamespace(load=lambda:None,ordinal=1,ciphertext_bytes=1600,previous='b'*64)
    monkeypatch.setattr(p,'Journal',lambda *a:SimpleNamespace(load=lambda:old,ordinal=SNAPSHOT['ordinal'],ciphertext_bytes=SNAPSHOT['bytes'],previous=SNAPSHOT['sha256']))
    monkeypatch.setattr(step,'migrate_owner_namespace',lambda *a,**kw:events.append('namespace'))
    pilot.save=lambda:None;pilot.build=lambda:events.append('build');pilot.startup_preflight=lambda:events.append('startup')
    pilot.verify_release_binding=lambda:events.append('readonly_binding') or {'status':'READ_ONLY'}
    pilot.prepare_continuation()
    assert events==['namespace','build','startup','readonly_binding'] and old==before
    assert 'large_closed_state' not in pilot.state and pilot.state['stable_credentials']==old['stable_credentials']
    assert pilot.state['predecessor']['snapshot']==SNAPSHOT and p.PERIOD=='b-dbpilot-20261027-1102-05'
    assert 'INITIAL_JOURNAL' in capsys.readouterr().out

@pytest.mark.parametrize('period',['b-dbpilot-20261027-1102-01','b-dbpilot-20261027-1102-02','b-dbpilot-20261027-1102-03','b-dbpilot-20261027-1102-04','b-dbpilot-20261027-1102-05'])
def test_closed_attempts_refuse_before_preflight_or_effect(period):
    obj=object.__new__(p.Pilot);obj.journal=SimpleNamespace(load=lambda:{'period':period,'status':'CLOSED','intents':{'RELEASE':{}}})
    obj.preflight=lambda:pytest.fail('CONSUMED_PREFLIGHT')
    with pytest.raises(p.op.Denied,match='PRIOR_ATTEMPT'):obj.release_preflight()
