"""Actual owner command/PG/children, synthetic source/API/private-inspection stand-ins."""
import json,os,subprocess,sys
from pathlib import Path
import pytest
from tests.e2e_pg_world import settings
from tests.oldham_wrapper_fixture import packet

RESULTS=[]

@pytest.mark.parametrize('scenario,nominees,status,cleanup',[
    ('cs_zero',0,'COMPLETED','CLOSED'),('cs_nominees',1,'COMPLETED','CLOSED'),
    ('cs_barrier',0,'STOP_RECONCILE_NO_RETRY','UNCERTAIN'),
    ('cs_predecessor',0,'STOP_RECONCILE_NO_RETRY','UNCERTAIN'),
    ('cs_secret_ack',0,'STOP_RECONCILE_NO_RETRY','UNCERTAIN'),
    ('cs_retire_ack',0,'STOP_RECONCILE_NO_RETRY','UNCERTAIN'),
    ('cs_install_ack',0,'STOP_RECONCILE_NO_RETRY','UNCERTAIN'),
    ('cs_install_readback',0,'STOP_RECONCILE_NO_RETRY','UNCERTAIN'),
])
def test_command_transition(tmp_path,monkeypatch,scenario,nominees,status,cleanup):
    settings()
    path,sha=packet(tmp_path/'input',records=5,nominees=nominees,tag=scenario,single_page=True,accept=monkeypatch,transition=True)
    home=tmp_path/'home';home.mkdir()
    env={**os.environ,'HOME':str(home),'DATABASE_URL':'sqlite:///:memory:','PYTHONDONTWRITEBYTECODE':'1','OLDHAM_WRAPPER_SCENARIO':scenario}
    run=subprocess.run([sys.executable,'-m','verification.ingestion_storage.oldham_owner_once','--package',str(path),'--package-sha256',sha,'--disposable-test'],env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=180)
    lines=[json.loads(s) for s in run.stdout.splitlines() if s.startswith('{')]
    assert lines,run.stderr[-1000:]
    result=lines[-1];RESULTS.append(dict(scenario=scenario,result=result))
    assert result['status']==status and result['cleanup']==cleanup,result
    assert result['detail_attempts']==0 and result['source_listing_requests']==0
    assert result['accounting']['source']['attempts']==0
    assert result['accounting']['administration']['connections']<=13 and result['accounting']['administration']['commands']<=240
    assert result['exported_bytes']<=2*1024**2
    state=home/'.local/state/propertyaigent'/('oldham-owner-test-'+scenario.replace('_','-'))
    audit=(state/'events.jsonl').read_text()
    events=[json.loads(s) for s in audit.splitlines()]
    assert 'INGESTION_APPLICATION_DATABASE_URL' not in audit and 'oldham_three_login_activation' not in audit
    # Active mode receives no application URL, and the fixture's url_factory asserts this.
    if status=='COMPLETED':
        assert result['records']==5 and result['nominees']==nominees and result['access']=='DISABLED_VERIFIED'
        assert result['outcome']==('SCREENING_COMPLETE_NO_ADMISSION_REQUIRED' if not nominees else 'SCREENING_COMPLETE_ADMISSION_HELD_OPERATION_SCOPE')
        assert result['process_closure']['live_children']==result['process_closure']['new_sockets']==0
        assert 'oldham_install_committed' in audit and 'oldham_retirement_closed' in audit
        assert all(not any(e['payload']['flags']) for e in events if e['event']=='oldham_install_capabilities')
        assert any(e['event']=='oldham_two_login_teardown' and e['payload']['cleanup']=='CLOSED' for e in events)
    else:
        assert 'oldham_install_committed' not in audit
        assert not any(e['event']=='oldham_two_login_activation' for e in events)
        # No compensating rollback, issuance or replay after an uncertain effect.
        assert not any(e['event']=='oldham_install_committed' for e in events)


def teardown_module():
    if os.environ.get('OLDHAM_TRANSITION_COST_PATH'):Path(os.environ['OLDHAM_TRANSITION_COST_PATH']).write_text(json.dumps(RESULTS,sort_keys=True))
