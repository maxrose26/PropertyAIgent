"""Actual daily command -> supported issuer -> restricted PG -> supervised fixtures.

No production/source contact. Only fixture installation and expiring PERIOD
preauthorisation use the disposable migration principal; daily rows/grants are
issued by the production SQL function on the restricted worker connection.
"""
import copy,json,os,subprocess,sys,time
from datetime import datetime,timedelta,timezone,date
from pathlib import Path
from types import SimpleNamespace
import pytest
from app.ingestion.daily_intake import current_windows,backlog_page
from app.ingestion.ledger import Denied,digest
from app.ingestion.listing_screening import ScreeningRule,RULE_V3
from tests.e2e_pg_world import disposable_world
from tests.e2e_connection_support import idox_audit,arcus_audit,entry,SCHEME,TEST_QUALIFICATION
from tests.e2e_chain_caller import snapshot,changed_tables,restricted_sessions
from verification.ingestion_storage import intake_policy
from verification.ingestion_storage.daily_intake_runtime import execution_binding,stop_snapshot,registration_payload
from verification.ingestion_storage.intake_budget import IntakeRun,LIMITS,RESERVE
from verification.ingestion_storage.operational_owner import Owner

RULE=ScreeningRule(RULE_V3,unit_threshold=10,link_related=False)

@pytest.fixture(scope='module')
def world():
    for world in disposable_world():
        with world['connect']('provisioning_migrator') as c:c.execute(intake_policy.installation_script())
        yield world


def reset(world):
    world['boot'].execute('DELETE FROM ingestion_work_attempts')
    world['boot'].execute("DELETE FROM ingestion_work_items WHERE key<>repeat('0',64)")
    world['boot'].execute('UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat(\'0\',64)',(json.dumps(world['control']),))


def policy(world):
    ctl=world['boot'].execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
    return dict(expires_at=time.time()+3600,max_runs=7,overlap_days=7,expected_stop=stop_snapshot(ctl),
                execution_binding=execution_binding(),test_evidence=True,screening_config=digest(RULE.config()),
                councils={c:dict(contract='daily-intake-'+c,qualification_sha256=TEST_QUALIFICATION) for c in ('tameside','manchester')})


def authorise(world,name,p=None):
    owner=Owner(lambda:world['connect']('provisioning_migrator'),lambda *_:None,lambda:None,
                identity='provisioning_migrator',expiry=datetime.now(timezone.utc)+timedelta(hours=1),bindings=execution_binding())
    return owner.register_intake_period(name,p or policy(world))


def env_and_sources(world,tmp_path,*,failed=False):
    rows=current_windows(datetime.now(timezone.utc),['tameside','manchester'])
    directory=tmp_path/'sources';directory.mkdir()
    for row in rows:
        start,end=date.fromisoformat(row['start']),date.fromisoformat(row['end'])
        records=[entry('DAILY/1/26',SCHEME)]
        if row['council']=='tameside':
            audit=idox_audit('tameside',records,start,end)
            if failed:
                audit.update(failure='SOURCE_CONTRACT_REJECTED',completeness='FAILED',
                             failure_diagnostic=dict(transport=dict(http_status=429)))
        else:audit=arcus_audit('manchester',records,start,end,budget='BROWSER_SOURCE_V2')
        (directory/(row['council']+'.json')).write_text(json.dumps(audit))
    issuer='http://127.0.0.1:8765'
    machine=dict(version=1,enabled=True,environment='local',issuer=issuer,client_id='local-test',web_processes=1,web_replicas=1,
                 owner_subject='owner',principals=[dict(issuer=issuer,subject='owner',role='operator',enabled=True,workspace_id=1,buyer_ids=[])],
                 machines={'daily':dict(enabled=True,workspace_id=1,buyer_ids=[],actions=['launch:run_daily_councils'])})
    path=tmp_path/'machine.json';path.write_text(json.dumps(machine))
    env=dict(os.environ,INGESTION_WORKER_DATABASE_URL=world['urls']['ingestion_worker_login'],
             INGESTION_EFFECT_DATABASE_URL=world['urls']['ingestion_effect_login'],PROPERTYAIGENT_COMMAND_IDENTITY='daily',
             PROPERTYAIGENT_ACCESS_POLICY=str(path),DATABASE_URL='sqlite:///:memory:')
    return env,directory


def invoke(world,tmp_path,name,*,failed=False):
    env,sources=env_and_sources(world,tmp_path,failed=failed)
    output=tmp_path/'result'
    command=[sys.executable,'-m','scripts.run_daily_councils','--period',name,'--output',str(output),
             '--disposable-sources',str(sources),'--disposable-archive',str(tmp_path/'archive')]
    run=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60)
    result=json.loads((output/'final-result.json').read_bytes()) if (output/'final-result.json').exists() else dict(stdout=run.stdout,stderr=run.stderr)
    return run,result,command


@pytest.mark.parametrize('failed',[False,True])
def test_invoked_command_supported_issuer_collect_capture_screen_backlog_close(world,tmp_path,failed,record_property):
    reset(world);name='command-contained' if failed else 'command-complete';authorise(world,name)
    before=snapshot(world['boot'])
    run,result,command=invoke(world,tmp_path,name,failed=failed)
    expected='INCOMPLETE' if failed else 'RETAINED_AND_SCREENED'
    assert result['status']==expected,json.dumps(result,sort_keys=True)
    assert run.returncode==(1 if failed else 0),run.stderr
    assert result['cleanup']=='CLOSED' and result['authority_closure']=='INVALIDATED'
    assert result['usage']['all_connections_closed'] and result['publication']=='TEST_LOCAL_ARCHIVE'
    assert result['coverage_advance'] is False and result['admission_connected'] is False
    assert len(result['backlog']['records'])==(1 if failed else 2)
    assert all(r['fields'] and r['source_url'] and r['source_record_id'] and r['archive']['readback_verified'] for r in result['backlog']['records'])
    assert changed_tables(before,snapshot(world['boot']))==[] and restricted_sessions(world['boot'])==0
    control=world['boot'].execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
    assert control['global_stop'] is None and control['manual_stop'] is None
    assert all(g['expires_at']==0 for g in control['grants'].values())
    if failed:
        settled=world['boot'].execute("SELECT state,checkpoint FROM ingestion_work_items WHERE task='DISCOVERY' AND subject->>'council'='tameside'").fetchone()
        assert settled[0]=='DEFERRED' and settled[1]['failure']=='RATE_LIMIT' and settled[1]['durable_archive']['readback_verified']
        assert any(s['council']=='manchester' and s['status']=='RETAINED_AND_SCREENED' for s in result['scopes'])
    record_property('command',json.dumps(command));record_property('usage',json.dumps(result['usage'],sort_keys=True))


def test_supported_issuer_refuses_period_widening_and_runtime_self_authorisation(world,tmp_path):
    reset(world)
    p=policy(world);p['councils']['oldham']=p['councils']['tameside']
    with pytest.raises(Exception,match='ADMIN_EFFECT_UNCERTAIN'):authorise(world,'too-wide',p)
    p=policy(world);p['expires_at']=time.time()+604900
    with pytest.raises(Exception,match='ADMIN_EFFECT_UNCERTAIN'):authorise(world,'too-long',p)
    with world['connect']('ingestion_worker_login') as c:
        with pytest.raises(Exception,match='OWNER_DISPOSITION_REQUIRED'):
            c.execute('SELECT public.ingestion_register_bolton_exception(%s::jsonb)',(json.dumps(dict(operation='intake_period',period='self',policy=policy(world))),))


def test_run_budget_refuses_before_unfit_scope_and_preserves_closure():
    run=IntakeRun();run.used['requests']=11
    with pytest.raises(Denied,match='SCOPE_CANNOT_FIT:requests'):run.before_scope('arcus')
    run=IntakeRun();run.used['github_calls']=51
    with pytest.raises(Denied,match='PUBLICATION_RESERVE'):run.publication(1,10)
    assert run.used['github_calls']==51
    run.closing=True;run.publication(1,10)
    assert run.used['github_calls']==61
    run=IntakeRun();run.budgets=[SimpleNamespace(statements=2040,attempts=76,returned_bytes=0,opened=[])]
    with pytest.raises(Denied,match='DATABASE_RESERVE'):run.database_limits({})
    run.closing=True
    assert run.database_limits({})['connections']==4


def test_budget_never_resets_between_councils():
    run=IntakeRun();run.source(dict(requests=10,source_bytes=3000000,source_seconds=45,supervised_seconds=60))
    run.source(dict(requests=80,source_bytes=20971520,source_seconds=75,supervised_seconds=90))
    assert run.used['requests']==90
    with pytest.raises(Denied,match='SOURCE_BOUND'):run.source(dict(requests=1,source_bytes=0,source_seconds=0,supervised_seconds=0))


def test_consumed_daily_invocation_does_not_recollect_or_duplicate_work(world,tmp_path):
    reset(world);authorise(world,'duplicate-command')
    first=tmp_path/'first';first.mkdir();run,result,_=invoke(world,first,'duplicate-command')
    assert result['status']=='RETAINED_AND_SCREENED',json.dumps(result)
    before=world['boot'].execute('SELECT count(*),sum(attempt_count) FROM ingestion_work_items').fetchone()
    second=tmp_path/'second';second.mkdir();run,result,_=invoke(world,second,'duplicate-command')
    assert result['status']=='RETAINED_AND_SCREENED',json.dumps(result)
    assert all(s['status']=='ALREADY_RETAINED' for s in result['scopes'])
    assert result['usage']['requests']==0 and result['authority_closure']=='NOT_ISSUED'
    assert world['boot'].execute('SELECT count(*),sum(attempt_count) FROM ingestion_work_items').fetchone()==before


def test_paginated_cross_run_backlog_survives_period_expiry(world,tmp_path):
    reset(world)
    for i in range(2):
        name='history-'+str(i);authorise(world,name);target=tmp_path/name;target.mkdir()
        _,result,_=invoke(world,target,name)
        assert result['status']=='RETAINED_AND_SCREENED',json.dumps(result)
    # Simulate elapsed expiry in the fixture only; no production clock override.
    world['boot'].execute("UPDATE ingestion_work_items SET outcome=jsonb_set(outcome::jsonb,'{intake_periods,history-1,expires_at}','0'::jsonb)::json WHERE key=repeat('0',64)")
    target=tmp_path/'read';target.mkdir();env,sources=env_and_sources(world,target)
    cursor=None;seen=[]
    for i in range(5):
        output=target/('page-'+str(i))
        command=[sys.executable,'-m','scripts.run_daily_councils','--period','history-1','--output',str(output),'--backlog','--page-size','1',
                 '--disposable-sources',str(sources),'--disposable-archive',str(target/'archive')]
        if cursor:command+=['--after',cursor]
        run=subprocess.run(command,env=env,capture_output=True,text=True,timeout=30)
        assert run.returncode==0,run.stderr
        page=json.loads((output/'backlog.json').read_bytes());seen.extend(page['records'])
        assert page['source_calls']==page['registrations']==0 and page['usage']['all_connections_closed']
        cursor=page['next_cursor']
        if cursor is None:break
    assert len(seen)==4 and len({(r['capture_key'],r['reference']) for r in seen})==4
    assert all(r['screening_state']=='COMPLETE' and r['extraction_complete'] is False for r in seen)


def test_changed_stop_prevents_supported_registration_and_preserves_history(world,tmp_path):
    reset(world);authorise(world,'stop-guard')
    with world['connect']('ingestion_worker_login') as c:c.execute("SELECT public.ingestion_raise_stop('DISPOSABLE_NEW_STOP')")
    target=tmp_path/'stopped';target.mkdir();_,result,_=invoke(world,target,'stop-guard')
    assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['scopes']==[]
    ctl=world['boot'].execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
    assert ctl['manual_stop']=='DISPOSABLE_NEW_STOP' and ctl['grants']=={}
    assert result['usage']['requests']==0


def test_policy_preserves_historical_registration_branch_text():
    from verification.ingestion_storage import screening_v3_worker_sql as v3
    old=v3.original_text();start=old.index(" IF NOT pg_has_role(session_user,'ingestion_barrier_releaser','USAGE') THEN")
    finish=old.index('END $register$;',start)
    assert old[start:finish] in intake_policy.policy_sql()
