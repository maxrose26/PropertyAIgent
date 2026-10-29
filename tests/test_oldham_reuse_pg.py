"""Actual successor command, PG17, provider extension and reconciled-state fixture."""
import json,os,subprocess,sys
from pathlib import Path
import pytest
from tests.e2e_pg_world import settings
from tests.oldham_wrapper_fixture import packet
RESULTS=[]

def test_reconciled_disposable_setup_is_not_an_opaque_runner_failure(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from tests.oldham_wrapper_fixture import Backend
    settings()
    path,_=packet(tmp_path/'setup',records=5,nominees=0,single_page=True,accept=monkeypatch,reuse=True,tag='reuse_setup')
    monkeypatch.setenv('OLDHAM_WRAPPER_SCENARIO','reuse_zero')
    backend=Backend(path)
    try:
        backend.prepare('DISPOSABLE_FIXTURE_INPUT_ONLY',SimpleNamespace())
        assert backend.world['boot'].execute("SELECT count(*) FROM pg_roles WHERE rolname='ingestion_recovery_login'").fetchone()[0]==0
        assert backend.names=={'DATABASE_URL'}
    finally:backend.close()


@pytest.mark.parametrize('scenario,success',[
 ('reuse_zero',True),('reuse_nominee',True),('reuse_policy',False),('reuse_metadata',False),('reuse_worker_policy',False),('reuse_missing_policy',False),
 ('reuse_work',False),('reuse_counter',False),('reuse_target',False),('reuse_settings',False),('reuse_secret',False),('reuse_stop',False),('reuse_barrier',False),
 ('reuse_revoked',False),('reuse_cleanup_ack',False),('reuse_cleanup_readback',False),
])
def test_actual_installed_successor(tmp_path,monkeypatch,scenario,success):
    settings()
    path,h=packet(tmp_path/'inputs with spaces',records=5,nominees=int(scenario=='reuse_nominee'),single_page=True,accept=monkeypatch,reuse=True,tag=scenario)
    home=tmp_path/'home';home.mkdir()
    env={**os.environ,'HOME':str(home),'DATABASE_URL':'sqlite:///:memory:','PYTHONDONTWRITEBYTECODE':'1','OLDHAM_WRAPPER_SCENARIO':scenario}
    run=subprocess.run(['bash','docs/design/oldham-activation-correction-20261028/owner-run.sh',str(Path.cwd()),sys.executable,str(path),h,'--disposable-test'],env=env,capture_output=True,text=True,timeout=180)
    outputs=[json.loads(s) for s in run.stdout.splitlines() if s.startswith('{')]
    assert outputs,run.stderr[-1500:]
    v=outputs[-1];RESULTS.append(dict(scenario=scenario,result=v))
    root=home/'.local/state/propertyaigent'/('oldham-owner-test-'+scenario.replace('_','-'))
    events=[json.loads(s) for s in (root/'events.jsonl').read_text().splitlines()]
    names=[e['event'] for e in events]
    assert 'oldham_install_committed' not in names and 'oldham_retirement_closed' not in names
    assert v['source_listing_requests']==0 and v['detail_attempts']==0
    assert v['accounting']['administration'] is not None,(v,run.stderr[-2000:])
    assert v['accounting']['administration']['commands']<=240 and v['accounting']['administration']['connections']<=13
    assert 'INGESTION_APPLICATION_DATABASE_URL' not in (root/'events.jsonl').read_text()
    if success:
        assert run.returncode==0 and v['status']=='COMPLETED' and v['cleanup']=='CLOSED',v
        assert v['records']==5 and v['nominees']==int(scenario=='reuse_nominee')
        assert v['historical_cleanup']['readback']=='VERIFIED' and v['historical_cleanup']['grant_expiry_after']==0
        assert v['transition']['retirement']=='NOT_REPEATED' and v['transition']['installation']=='REUSED_VERIFIED'
        assert 'oldham_reuse_cleanup_verified' in names and 'oldham_two_login_teardown' in names
        assert names.index('oldham_reuse_cleanup_verified')<names.index('oldham_two_login_activation')
        assert v['admission']=='NOT_AUTHORISED' and v['application_engine']=='NOT_CREATED'
        assert v['access']=='DISABLED_VERIFIED' and v['coverage_advance'] is False
        assert v['process_closure']['live_children']==v['process_closure']['new_sockets']==0
        assert v['exported_bytes']<=2*1024**2
    else:
        assert v['status']=='STOP_RECONCILE_NO_RETRY' and v['cleanup']=='UNCERTAIN',v
        assert not any(n=='oldham_two_login_activation' for n in names)
        assert not any(e['event']=='oldham_authority_committed' for e in events)
        assert 'oldham_two_login_teardown' not in names
        assert 'oldham_reuse_cleanup_verified' not in names


def teardown_module():
    if os.environ.get('OLDHAM_REUSE_COST_PATH'):Path(os.environ['OLDHAM_REUSE_COST_PATH']).write_text(json.dumps(RESULTS,sort_keys=True))
