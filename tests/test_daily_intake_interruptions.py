"""Connected restricted PostgreSQL, local archive and actual killed processes."""
import json,os,signal,subprocess,sys,time
from pathlib import Path
import pytest
from tests.test_daily_intake_runtime import world,reset,authorise,env_and_sources,invoke


def control(world):
    return world['boot'].execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]


@pytest.mark.parametrize('fault',['registration','source_intent','archive','capture','screening','closure','publication','finish_ack'])
def test_sigkill_preserves_discoverable_run_and_refuses_replay(world,tmp_path,fault,record_property):
    reset(world);name='kill-'+fault;authorise(world,name)
    first=tmp_path/'first';first.mkdir();env,sources=env_and_sources(world,first)
    ready=first/'ready';output=first/'result';archive=first/'archive'
    command=[sys.executable,'-m','tests.intake_interrupt_fixture','--period',name,'--output',str(output),
        '--disposable-sources',str(sources),'--disposable-archive',str(archive),'--fault',fault,'--ready',str(ready)]
    process=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    try:
        deadline=time.monotonic()+30
        while not ready.exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.025)
        if not ready.exists():
            process.kill();out,err=process.communicate(timeout=5);pytest.fail(out+err)
        process.kill();out,err=process.communicate(timeout=5)
        assert process.returncode==-signal.SIGKILL and not (output/'final-result.json').exists()
    finally:
        if process.poll() is None:process.kill();process.communicate(timeout=5)
    marker=control(world)['intake_run']
    assert marker['state']==('VERIFIED' if fault=='finish_ack' else 'OPEN')
    assert marker['period']==name and marker['publication_path'].endswith('/final/result-before-publication.json')
    before=world['boot'].execute('SELECT count(*),sum(attempt_count) FROM ingestion_work_items').fetchone()
    # Read-only backlog exposes the unfinished run even without any captured rows.
    back=first/'backlog'
    read=[sys.executable,'-m','scripts.run_daily_councils','--period',name,'--output',str(back),'--backlog',
        '--disposable-sources',str(sources),'--disposable-archive',str(archive)]
    completed=subprocess.run(read,env=env,capture_output=True,text=True,timeout=20)
    assert completed.returncode==0,completed.stderr
    report=json.loads((back/'backlog.json').read_text())
    assert (report['unfinished_run'] is None)==(fault=='finish_ack')
    # A new period cannot bypass the global marker, including after expiry/date change.
    if fault!='finish_ack':
        with pytest.raises(Exception):authorise(world,'new-period-after-kill')
    second=tmp_path/'second';second.mkdir();run,result,_=invoke(world,second,name)
    assert result['status']==('RETAINED_AND_SCREENED' if fault=='finish_ack' else 'STOP_RECONCILE_NO_RETRY'),result
    assert result['usage']['requests']==0
    assert world['boot'].execute('SELECT count(*),sum(attempt_count) FROM ingestion_work_items').fetchone()==before
    assert control(world)['intake_run']==marker
    record_property('interruption',json.dumps(dict(fault=fault,marker=marker,status=result['status'])))


def test_verified_capture_does_not_hide_missing_screen_or_unfinished_batch(world,tmp_path):
    for task in ('SCREENING','LISTING_METADATA'):
        reset(world);name='missing-'+task.lower();authorise(world,name)
        first=tmp_path/task;first.mkdir();_,result,_=invoke(world,first,name)
        assert result['status']=='RETAINED_AND_SCREENED',result
        # Corrupt only this disposable state to exercise independent readback even
        # when a previously verified run marker claims completion.
        world['boot'].execute("UPDATE ingestion_work_items SET state='QUEUED' WHERE key=(SELECT key FROM ingestion_work_items WHERE task=%s LIMIT 1)",(task,))
        second=tmp_path/(task+'-repeat');second.mkdir();_,result,_=invoke(world,second,name)
        assert result['status']=='STOP_RECONCILE_NO_RETRY',result
        assert result['usage']['requests']==0
