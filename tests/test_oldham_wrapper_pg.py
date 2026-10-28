"""Actual command + restricted disposable PG + real source child; synthetic API and input provider."""
import json,os,subprocess,sys
from pathlib import Path
import pytest
from tests.e2e_pg_world import settings
from tests.oldham_wrapper_fixture import packet

CASES=[]

@pytest.mark.parametrize('scenario,records,nominees,status,cleanup',[
    ('success',2,1,'COMPLETED','CLOSED'),('five',6,5,'COMPLETED','CLOSED'),('zero',11,0,'COMPLETED','CLOSED'),('zero19',19,0,'COMPLETED','CLOSED'),
    ('hold',6,6,'COMPLETED','CLOSED'),('cancel',2,1,'STOP_RECONCILE_NO_RETRY','CLOSED'),
    ('stop',2,1,'STOP_RECONCILE_NO_RETRY','CLOSED'),('expiry',2,1,'STOP_RECONCILE_NO_RETRY','CLOSED'),
    ('existing',2,1,'COMPLETED','CLOSED'),
    ('export_boundary',2,1,'STOP_RECONCILE_NO_RETRY','UNCERTAIN'),('export_overflow',2,1,'STOP_RECONCILE_NO_RETRY','UNCERTAIN'),
    ('deadline',2,1,'STOP_RECONCILE_NO_RETRY','UNCERTAIN'),
    ('application_uncertain',2,1,'STOP_RECONCILE_NO_RETRY','UNCERTAIN'),('ledger_ack_uncertain',2,1,'STOP_RECONCILE_NO_RETRY','UNCERTAIN'),('b2_uncertain',2,1,'STOP_RECONCILE_NO_RETRY','UNCERTAIN'),
    ('publication_uncertain',2,1,'STOP_RECONCILE_NO_RETRY','UNCERTAIN'),('uncertain_commit',2,1,'STOP_RECONCILE_NO_RETRY','UNCERTAIN'),
    ('accepted_zero',5,0,'COMPLETED','CLOSED'),('accepted_success',3,1,'COMPLETED','CLOSED')])      # owner-accepted single page (specification 037): the V2 package, a TEST-ONLY acceptance installed by the disposable backend
def test_actual_owner_command(tmp_path,scenario,records,nominees,status,cleanup,monkeypatch):
    settings() # refuses anything except the existing fixed loopback fixture
    accepted=scenario.startswith('accepted')
    path,sha=packet(tmp_path/'input',records=records,nominees=nominees,tag=scenario,single_page=accepted,accept=monkeypatch if accepted else None)
    home=tmp_path/'home';home.mkdir()
    env={**os.environ,'HOME':str(home),'DATABASE_URL':'sqlite:///:memory:','PYTHONDONTWRITEBYTECODE':'1','OLDHAM_WRAPPER_SCENARIO':scenario}
    command=[sys.executable,'-m','verification.ingestion_storage.oldham_owner_once','--package',str(path),'--package-sha256',sha,'--disposable-test']
    run=subprocess.run(command,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=180)
    assert 'Traceback' not in run.stdout+run.stderr,run.stderr[-1000:]
    lines=[json.loads(l) for l in run.stdout.splitlines() if l.startswith('{')];assert lines,run.stderr[-1000:]
    result=lines[-1]
    CASES.append(dict(scenario=scenario,result=result)) # retain failures as well as successes
    assert result.get('status')==status and result.get('cleanup')==cleanup,result
    assert run.returncode==(0 if status=='COMPLETED' and cleanup=='CLOSED' else 1),result
    assert result.get('source_listing_requests')==0
    assert result['exported_bytes']<=2*1024**2
    assert result['exported_bytes']==result['persisted_evidence_bytes']+result['terminal_json_bytes']+result.get('attempted_publication_bytes',0)
    assert result['accounting']['github_requests']<=40
    assert result['accounting']['total_command_seconds']>=result['accounting']['preflight_seconds']>=0
    if scenario in ('success','accepted_success'):assert len(result['nominee_results'])==1 and result['nominee_results'][0]['application_id'] is not None
    if accepted:
        assert json.loads(path.read_bytes())['version']=='OLDHAM_OWNER_WRAPPER_V2' and result['source_listing_requests']==0
    admin=result['accounting']['administration'];assert admin['commands']<=240 and admin['connections']<=13 and admin['returned_data_value_bytes']<=1024**2
    runtime=result['accounting']['runtime'];assert runtime['commands']<=1040 and runtime['connections']<=40 and runtime['returned_bytes']<=4*1024**2
    if scenario in ('export_boundary','export_overflow'):
        assert result['accounting_injection']=='SYNTHETIC_EXPORT_BOUNDARY'
        assert result['access']=='DISABLED_VERIFIED' and result['detail_attempts']==0
        assert result['process_closure']['live_children']==result['process_closure']['new_sockets']==0
        assert result['publication']=='UNCERTAIN_OR_HELD'
    if scenario=='existing':assert result['nominee_results'][0]['application_id'] is not None and result['detail_attempts']==0
    if scenario in ('application_uncertain','ledger_ack_uncertain','b2_uncertain'):
        assert result['runtime_effect_uncertain'] and result['access']=='UNCERTAIN'
        assert result['outcome']=='ADMISSION_PROCESSING_IN_PROGRESS'
    if scenario in ('success','five'):
        source=result['accounting']['source']
        assert source['status']=='COMPLETE' and len(source['receipts'])==result['detail_attempts']
        assert source['totals']['requests']==result['detail_attempts'] and source['totals']['received_body_bytes']>0
        assert all(x['source_outcome']=='PROJECTED_OBSERVATION' and len(x['target_sha256'])==64 for x in source['receipts'])
        assert all(x['worker']['requests']==1 and x['worker']['received_body_bytes']>0 and x['worker']['cleanup_state']=='CLOSED' for x in source['receipts'])
    if scenario=='five':assert result['detail_attempts']==5 and len(result['nominee_results'])==5 and all(n['application_id'] is not None for n in result['nominee_results'])
    if scenario in ('zero','zero19','accepted_zero'):
        assert result['outcome']=='SCREENING_COMPLETE_NO_ADMISSION_REQUIRED' and result['detail_attempts']==0
        assert result['accounting']['source']['status']=='NOT_STARTED' and result['accounting']['source']['attempts']==0
        assert result['accounting']['source']['totals']['requests']==0
    if scenario=='hold':assert result['outcome']=='SCREENING_COMPLETED_ADMISSION_HELD_CAPACITY' and result['detail_attempts']==0
    if cleanup=='CLOSED':assert result['access']=='DISABLED_VERIFIED' and result['process_closure']['live_children']==result['process_closure']['new_sockets']==0
    state=home/'.local/state/propertyaigent'/('oldham-owner-test-'+scenario.replace('_','-'))
    assert (state/'final-result.json').is_file() and (state/'events.jsonl').is_file()
    if scenario=='success':
        again=subprocess.run(command,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=20)
        assert again.returncode==1 and json.loads(again.stdout.splitlines()[-1])['credential_requested'] is False


def teardown_module():
    if os.environ.get('OLDHAM_WRAPPER_COST_PATH'):Path(os.environ['OLDHAM_WRAPPER_COST_PATH']).write_text(json.dumps(CASES,sort_keys=True))
