"""Actual daily command on hosted PG17 only, synthetic active fixture roles.

Mocked source-worker -> finite reader output is handed unchanged into existing
supervised disposable-source path; never a council/production DB connection.
"""
import json,subprocess,sys,hashlib
from datetime import datetime,timezone
import pytest
from app.ingestion.daily_intake import current_windows
from app.ingestion.ledger import digest
from tests.test_daily_intake_runtime import world,reset,policy,authorise,env_and_sources
from tests.test_tameside_b_connection import connected_source,COUNTED_CONTRACT,QUAL
from tests.e2e_chain_caller import snapshot,changed_tables,restricted_sessions

@pytest.mark.parametrize('failure',[None,'503','wrong-page'],ids=['nine-complete','contained-503','layout-refusal'])
def test_actual_daily_command_retains_screens_backlog_or_settles(world,tmp_path,monkeypatch,failure,record_property):
    assert 170000<=world['server_version']<180000,'PG17_REQUIRED'
    reset(world);name='five-'+('complete' if failure is None else failure)
    p=policy(world);p['max_runs']=1;p['councils']['tameside']=dict(contract=COUNTED_CONTRACT,qualification_sha256=QUAL);authorise(world,name,p)
    env,sources=env_and_sources(world,tmp_path,count=1)
    source_dir=tmp_path/'source-preparation';source_dir.mkdir();row=current_windows(datetime.now(timezone.utc),['tameside'])[0]
    source,calls=connected_source(source_dir,monkeypatch,row,failure)
    (sources/'tameside.json').write_text(json.dumps(source))
    before=snapshot(world['boot']);out=tmp_path/'result'
    command=[sys.executable,'-B','-m','scripts.run_daily_councils','--period',name,'--output',str(out),'--disposable-sources',str(sources),'--disposable-archive',str(tmp_path/'archive')]
    run=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60)
    assert (out/'final-result.json').exists(),run.stdout+run.stderr
    result=json.loads((out/'final-result.json').read_bytes())
    assert result['cleanup']=='CLOSED' and result['authority_closure']=='INVALIDATED' and result['usage']['all_connections_closed']
    assert changed_tables(before,snapshot(world['boot']))==[] and restricted_sessions(world['boot'])==0
    roots=world['boot'].execute("SELECT state,checkpoint FROM ingestion_work_items WHERE task='DISCOVERY' AND subject->>'council'='tameside'").fetchall()
    assert len(roots)==1
    screens=world['boot'].execute("SELECT checkpoint FROM ingestion_work_items WHERE task='SCREENING' AND subject->>'council'='tameside' AND state='COMPLETE'").fetchall()
    ctl=world['boot'].execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
    assert all(g['expires_at']==0 for g in ctl['grants'].values())
    if failure is None:
        assert run.returncode==0 and result['status']=='RETAINED_AND_SCREENED'
        capture=roots[0][1];assert roots[0][0]=='COMPLETE' and capture['kind']=='LISTING_RECEIPT_V1' and len(capture['records'])==9
        assert capture['source_sha256']==digest(source) and capture['qualification_sha256']==QUAL and capture['pagination_mode']=='TAMESIDE_FIVE_COUNT_V1'
        assert len(screens)==9 and all(v[0]['capture_bound'] is True and v[0]['capture_checkpoint_sha256']==digest(capture) for v in screens)
        rows=[r for r in result['backlog']['records'] if r['council']=='tameside'];assert len(rows)==9
        assert all(r['screening_state']=='COMPLETE' and r['fields']['application_type']['state']=='UNKNOWN' and r['archive']['readback_verified'] and not r['application_admitted'] and not r['extraction_complete'] for r in rows)
        assert ctl['intake_run']['state']=='VERIFIED' and len(calls)==5
        assert world['boot'].execute("SELECT count(*) FROM ingestion_work_items WHERE task='LISTING_METADATA' AND subject->>'council'='tameside' AND state='COMPLETE'").fetchone()[0]==2
    elif failure=='503':
        assert run.returncode==1 and result['status']=='INCOMPLETE' and roots[0][0]=='DEFERRED' and not screens
        assert roots[0][1]['failure']=='SOURCE_UNAVAILABLE' and roots[0][1]['durable_archive']['readback_verified']
        assert ctl['intake_run']['state']=='VERIFIED' and len(calls)==1
    else:
        assert run.returncode==1 and result['status']=='STOP_RECONCILE_NO_RETRY' and roots[0][0]!='COMPLETE' and not screens
        assert ctl['global_stop'] is not None and ctl['intake_run']['state']=='OPEN' and len(calls)==4
    record_property('result',json.dumps(dict(status=result['status'],cleanup=result['cleanup'],authority_closure=result['authority_closure'],source_invocations=1,mocked_physical_requests=len(calls),complete_tameside_screens=len(screens),application_tables_changed=[],restricted_sessions_after=0,server_version=world['server_version']),sort_keys=True))
