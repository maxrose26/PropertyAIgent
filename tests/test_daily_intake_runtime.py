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
    return dict(hostaddr=None,route='DISPOSABLE',expires_at=time.time()+3600,max_runs=7,overlap_days=7,expected_stop=stop_snapshot(ctl),
                execution_binding=execution_binding(),test_evidence=True,screening_config=digest(RULE.config()),
                councils={c:dict(contract='daily-intake-'+c,qualification_sha256=TEST_QUALIFICATION) for c in ('tameside','manchester')})


def authorise(world,name,p=None):
    owner=Owner(lambda:world['connect']('provisioning_migrator'),lambda *_:None,lambda:None,
                identity='provisioning_migrator',expiry=datetime.now(timezone.utc)+timedelta(hours=1),bindings=execution_binding())
    return owner.register_intake_period(name,p or policy(world))


def env_and_sources(world,tmp_path,*,failed=False,count=1):
    rows=current_windows(datetime.now(timezone.utc),['tameside','manchester'])
    directory=tmp_path/'sources';directory.mkdir()
    for row in rows:
        start,end=date.fromisoformat(row['start']),date.fromisoformat(row['end'])
        records=[entry('DAILY/'+str(i)+'/26',SCHEME) for i in range(count)]
        if row['council']=='tameside':
            audit=idox_audit('tameside',records,start,end)
            if failed:
                audit.update(failure='SOURCE_CONTRACT_REJECTED',completeness='FAILED',
                             failure_diagnostic=dict(transport=dict(http_status=503 if failed==503 else 429)))
        else:
            chunks=[arcus_audit('manchester',records[i:i+10],start,end,budget='BROWSER_SOURCE_V2') for i in range(0,len(records),10)]
            audit=chunks[0];all_rows=[r for a in chunks for r in a['listing_records']]
            audit['listing_segments']=[dict(ordinal=i+1,first=i*10+1,last=min((i+1)*10,count),total=count,
                evidence_sha256=__import__('hashlib').sha256(json.dumps(all_rows[i*10:(i+1)*10],sort_keys=True).encode()).hexdigest()) for i in range(len(chunks))]
            audit['listing_records']=all_rows
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


def invoke(world,tmp_path,name,*,failed=False,count=1):
    env,sources=env_and_sources(world,tmp_path,failed=failed,count=count)
    output=tmp_path/'result'
    command=['timeout','--signal=INT','--kill-after=5s','960s',sys.executable,'-m','scripts.run_daily_councils','--period',name,'--output',str(output),
             '--disposable-sources',str(sources),'--disposable-archive',str(tmp_path/'archive')]
    run=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60)
    result=json.loads((output/'final-result.json').read_bytes()) if (output/'final-result.json').exists() else dict(stdout=run.stdout,stderr=run.stderr)
    return run,result,command


@pytest.mark.parametrize('failed',[False,429,503])
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
    # Actual retained checkpoints supply nomination inputs. Do NOT run an
    # admission writer: its current validator still expects unbound revisions.
    from app.ingestion.nomination import derive_nominees
    captures=[r[0] for r in world['boot'].execute("SELECT checkpoint FROM ingestion_work_items WHERE task='DISCOVERY' AND state='COMPLETE'").fetchall()]
    nominees=derive_nominees(captures,RULE,allow_test_evidence=True)
    assert len(nominees.nominees)==(1 if failed else 2)
    assert all(n.source_url and n.source_record_id and n.capture_sha256 for n in nominees.nominees)
    for n in nominees.nominees:
        actual=world['boot'].execute("SELECT revision FROM ingestion_work_items WHERE task='SCREENING' AND subject->>'council'=%s AND subject->>'reference'=%s",(n.council,n.reference)).fetchone()[0]
        assert actual!=n.screening_revision  # documented, still-disconnected consumer contract
    control=world['boot'].execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
    assert control['global_stop'] is None and control['manual_stop'] is None
    assert all(g['expires_at']==0 for g in control['grants'].values())
    if failed:
        settled=world['boot'].execute("SELECT state,checkpoint FROM ingestion_work_items WHERE task='DISCOVERY' AND subject->>'council'='tameside'").fetchone()
        assert settled[0]=='DEFERRED' and settled[1]['failure']==('SOURCE_UNAVAILABLE' if failed==503 else 'RATE_LIMIT') and settled[1]['durable_archive']['readback_verified']
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



def test_initial_28_day_overlap_is_not_supported_by_current_rolling_issuer(world):
    """Characterise the release blocker; never treat a seven-day pass as initial 28-day coverage."""
    reset(world)
    reference=datetime(2026,11,7,tzinfo=timezone.utc)
    initial=current_windows(reference,['tameside'],overlap_days=28)[0]
    recurring=current_windows(reference,['tameside'])[0]
    assert (initial['start'],initial['end'])==('2026-10-10','2026-11-06')
    assert (recurring['start'],recurring['end'])==('2026-10-31','2026-11-06')
    before=snapshot(world['boot'])
    candidate=policy(world)
    candidate['overlap_days']=28
    with pytest.raises(Exception,match='ADMIN_EFFECT_UNCERTAIN'):
        authorise(world,'initial-overlap-28',candidate)
    assert snapshot(world['boot'])==before
    assert restricted_sessions(world['boot'])==0


@pytest.mark.parametrize('fault',['date','initial_overlap_28','council','writes','expiry','run_limit','publication_path'])
def test_trusted_sql_issuer_refuses_widened_or_consumed_work_before_insert(world,tmp_path,fault):
    from app.ingestion.ledger import DEFAULT_LIMITS
    from verification.ingestion_storage.chain_registration import capture_registration
    from verification.ingestion_storage.scope_binding import binding_for
    from tests.e2e_connection_support import idox_contract
    reset(world);name='boundary-'+fault;p=authorise(world,name)
    row=current_windows(datetime.now(timezone.utc),['tameside'])[0]
    contract=idox_contract('tameside',date.fromisoformat(row['start']),date.fromisoformat(row['end']),name=p['councils']['tameside']['contract'])
    owner=Owner(None,lambda *_:None,lambda:None,expiry=datetime.now(timezone.utc)+timedelta(minutes=20),bindings=execution_binding())
    reg=capture_registration(owner,binding_for('tameside'),contract,row['start'],row['end'],revision='boundary',item_limits=DEFAULT_LIMITS)
    request=registration_payload(name,reg,execution_binding())
    if fault=='publication_path':request['publication_path']=request['publication_path'].replace(name,'foreign-period')
    if fault=='date':request['rows'][0]['subject']['start']='2000-01-01'
    if fault=='initial_overlap_28':
        # A valid 7-day owner period must not permit the 28-day first-pass window
        # through the restricted capture issuer. This is NOT initial-overlap support.
        request['rows'][0]['subject']['start']=(date.fromisoformat(row['end'])-timedelta(days=27)).isoformat()
    if fault=='council':request['rows'][0]['subject']['council']='oldham'
    if fault=='writes':request['grant']['writes']=1
    if fault=='expiry':request['grant']['expires_at']=time.time()+1900
    if fault=='run_limit':
        world['boot'].execute("UPDATE ingestion_work_items SET outcome=jsonb_set(outcome::jsonb,ARRAY['intake_periods',%s,'days'],%s::jsonb)::json WHERE key=repeat('0',64)",(name,json.dumps({str(date(2000,1,1)+timedelta(days=i)):{} for i in range(7)})))
    # The 28-day case must specifically reach the trusted SQL date-window
    # refusal, not merely fail an unrelated grant or identity precondition.
    refusal='INTAKE_ROLLING_SCOPE_OR_CONSUMED' if fault=='initial_overlap_28' else 'INTAKE_(GRANT_BOUND|ROLLING_SCOPE_OR_CONSUMED|RUN_IDENTITY)'
    with world['connect']('ingestion_worker_login') as c:
        with pytest.raises(Exception,match=refusal):
            c.execute('SELECT public.ingestion_register_bolton_exception(%s::jsonb)',(json.dumps(request),))
    assert world['boot'].execute('SELECT count(*) FROM ingestion_work_items').fetchone()[0]==1
    ctl=world['boot'].execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
    assert ctl['grants']=={} and ctl['global_stop'] is None


def test_run_budget_refuses_before_unfit_scope_and_preserves_closure():
    run=IntakeRun();run.used['requests']=11
    with pytest.raises(Denied,match='SCOPE_CANNOT_FIT:requests'):run.before_scope('arcus')
    run=IntakeRun();run.used['github_calls']=51
    with pytest.raises(Denied,match='PUBLICATION_RESERVE'):run.publication(1,10)
    assert run.used['github_calls']==51
    run.closing=True;run.publication(1,10)
    assert run.used['github_calls']==61
    run=IntakeRun();run.budgets=[SimpleNamespace(statements=2040,attempts=84,returned_bytes=0,opened=[],prior_cancel_attempts=0,hard_deadline_events=[])]
    with pytest.raises(Denied,match='DATABASE_RESERVE'):run.database_limits({})
    run.closing=True
    assert run.database_limits({})['connections']==4


@pytest.mark.parametrize('fault',['cleanup_null','missing_delay','missing_hash','unknown_reason','wrong_http_status'])
def test_trusted_failure_settlement_rejects_incomplete_or_unrecognised_receipt(world,tmp_path,fault):
    from sqlalchemy import create_engine
    from app.ingestion.sql_ledger import SQLLedger
    from app.ingestion.ledger import DEFAULT_LIMITS
    from verification.ingestion_storage.chain_registration import capture_registration
    from verification.ingestion_storage.scope_binding import binding_for
    from tests.e2e_connection_support import idox_contract
    reset(world);name='bad-settlement-'+fault;p=authorise(world,name)
    row=current_windows(datetime.now(timezone.utc),['tameside'])[0]
    contract=idox_contract('tameside',date.fromisoformat(row['start']),date.fromisoformat(row['end']),name=p['councils']['tameside']['contract'])
    owner=Owner(None,lambda *_:None,lambda:None,expiry=datetime.now(timezone.utc)+timedelta(minutes=20),bindings=execution_binding())
    reg=capture_registration(owner,binding_for('tameside'),contract,row['start'],row['end'],revision='settlement',item_limits=DEFAULT_LIMITS)
    request=registration_payload(name,reg,execution_binding())
    with world['connect']('ingestion_worker_login') as c:
        c.execute('SELECT public.ingestion_register_bolton_exception(%s::jsonb)',(json.dumps(request),))
    engines=[create_engine(world['urls'][r]) for r in ('ingestion_worker_login','ingestion_effect_login')]
    try:
        ledger=SQLLedger(engines[0],owner='required_once',authority=reg.authority,bindings=reg.bindings,broker_engine=engines[1])
        claim=ledger.claim(reg.root_key);ledger.intent(claim,'source_calls')
        receipt=dict(cleanup='CLOSED',accounting_complete=True,failure='RATE_LIMIT',source_sha256='a'*64,
                     durable_archive=dict(readback_verified=True,sha256='a'*64),
                     source_audit=dict(failure_diagnostic=dict(transport=dict(http_status=429))))
        payload=dict(outcome=dict(outcome='RATE_LIMIT'),state='DEFERRED',reason='RATE_LIMIT',delay=3600,council_defer_seconds=3600,resolved_receipt=receipt)
        if fault=='cleanup_null':receipt['cleanup']=None
        if fault=='missing_delay':payload.pop('delay')
        if fault=='missing_hash':receipt.pop('source_sha256');receipt['durable_archive'].pop('sha256')
        if fault=='unknown_reason':payload['reason']=receipt['failure']=payload['outcome']['outcome']='UNSUPPORTED_CONTRACT'
        if fault=='wrong_http_status':receipt['source_audit']['failure_diagnostic']['transport']['http_status']=500
        # Call the actual trusted operation: the client intentionally rejects a
        # missing kwarg even earlier, so test the SQL boundary directly as well.
        with engines[1].begin() as c:
            with pytest.raises(Exception,match='INTAKE_FAILURE_SETTLEMENT'):
                ledger._step('settle_failure',claim.key,claim.fence,payload,connection=c)
        assert ledger.get(claim.key)['phase']=='SOURCE_INTENT'
    finally:
        for engine in engines:engine.dispose()


def test_budget_never_resets_between_councils():
    run=IntakeRun();run.source(dict(requests=10,source_bytes=3000000,source_seconds=45,supervised_seconds=60))
    run.source(dict(requests=80,source_bytes=20971520,source_seconds=75,supervised_seconds=90))
    assert run.used['requests']==90
    with pytest.raises(Denied,match='SOURCE_BOUND'):run.source(dict(requests=1,source_bytes=0,source_seconds=0,supervised_seconds=0))


def test_intake_reuses_only_the_existing_qualified_manchester_zero():
    import hashlib
    from dataclasses import replace
    from tests.e2e_connection_support import arcus_contract,outer
    from app.ingestion.ledger import DEFAULT_LIMITS
    start,end=date(2026,10,22),date(2026,10,28)
    source=arcus_audit('manchester',[entry('ZERO/1',SCHEME)],start,end)
    source['listing_records']=[]
    source['listing_segments']=[dict(ordinal=1,first=0,last=0,total=0,evidence_sha256=hashlib.sha256(b'No results found').hexdigest())]
    source['explicit_zero_evidence']='EXACT_VISIBLE_ZERO_AND_RETAINED_CRITERIA_NO_ROWS_OR_NEXT'
    contract=arcus_contract('manchester',start,end)
    with pytest.raises(Denied,match='EMPTY_WINDOW'):contract.project(source,outer(),DEFAULT_LIMITS)
    receipt=replace(contract,retain_explicit_zero=True).project(source,outer(),DEFAULT_LIMITS)
    assert receipt['records']==[] and receipt['explicit_zero'] is True
    source['explicit_zero_evidence']=''
    with pytest.raises(Denied):replace(contract,retain_explicit_zero=True).project(source,outer(),DEFAULT_LIMITS)


def test_compact_arcus_projection_preserves_fields_and_raw_archive_identity():
    from dataclasses import replace
    from tests.e2e_connection_support import arcus_contract,outer
    from app.ingestion.ledger import DEFAULT_LIMITS
    from verification.ingestion_storage.daily_intake_runtime import require_source_context
    start,end=date(2026,10,22),date(2026,10,28)
    audit=arcus_audit('manchester',[entry('DAILY/1/26',SCHEME)],start,end)
    contract=arcus_contract('manchester',start,end)
    full=contract.project(audit,outer(),DEFAULT_LIMITS)
    compact=replace(contract,compact_retained=True).project(audit,outer(),DEFAULT_LIMITS)
    assert compact['source_sha256']==full['source_sha256']==digest(audit)
    assert compact['records']==[{k:v for k,v in full['records'][0].items() if k!='assessment_capture'}]
    assert audit['listing_records'][0]['assessment_capture']  # unchanged original, archived by Coordinator
    assert RULE.screen(compact['records'][0])==RULE.screen(full['records'][0])
    require_source_context(['tameside','manchester'],disposable=True)
    require_source_context(['tameside'],disposable=False)
    with pytest.raises(Denied,match='ARCUS_INTAKE_EXECUTION_CONTEXT_UNSUPPORTED'):
        require_source_context(['tameside','manchester'],disposable=False)


def test_invoked_two_scope_maximum_sixty_each_has_one_shared_envelope(world,tmp_path,record_property):
    reset(world);authorise(world,'maximum-two-scopes')
    before=snapshot(world['boot']);run,result,command=invoke(world,tmp_path,'maximum-two-scopes',count=60)
    assert result['status']=='RETAINED_AND_SCREENED',json.dumps(result)
    assert run.returncode==0 and len(result['backlog']['records'])==120
    assert result['usage']['driver_statements']<=LIMITS['driver_statements']
    assert result['usage']['connection_attempts']<=LIMITS['connection_attempts']
    assert result['usage']['returned_bytes']<=LIMITS['returned_bytes'] and result['usage']['all_connections_closed']
    assert changed_tables(before,snapshot(world['boot']))==[] and restricted_sessions(world['boot'])==0
    record_property('maximum_two_scope_usage',json.dumps(result['usage'],sort_keys=True))


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
    assert all(r['screening_state']=='COMPLETE' and r['extraction_complete'] is None and r['downstream_state']=='NOT_TRACKED_BY_INTAKE' for r in seen)



def test_backlog_rejects_cross_council_contract_pair_even_when_both_values_are_allowlisted(world,tmp_path):
    """A council and another council's approved contract are not a valid pair.

    The intentionally mismatched historical row is inserted by the disposable
    fixture owner only; the restricted backlog command is still read-only.
    """
    reset(world);period='paired-backlog';authorise(world,period)
    capture=tmp_path/'capture';capture.mkdir()
    run,result,_=invoke(world,capture,period)
    assert run.returncode==0 and result['status']=='RETAINED_AND_SCREENED',json.dumps(result)
    initial=world['boot'].execute("SELECT subject->>'council',contract FROM ingestion_work_items WHERE task='DISCOVERY'").fetchall()
    assert {tuple(r) for r in initial}=={('manchester','daily-intake-manchester'),('tameside','daily-intake-tameside')}
    # Simulate a historical/misbound row whose contract name is otherwise on
    # the allowed list. Old independent IN filters would silently include it.
    world['boot'].execute("UPDATE ingestion_work_items SET contract='daily-intake-tameside' WHERE task='DISCOVERY' AND subject->>'council'='manchester'")
    target=tmp_path/'reader';target.mkdir();env,sources=env_and_sources(world,target)
    output=target/'page'
    command=[sys.executable,'-m','scripts.run_daily_councils','--period',period,'--output',str(output),
             '--backlog','--page-size','3','--disposable-sources',str(sources),'--disposable-archive',str(target/'archive')]
    check=subprocess.run(command,env=env,capture_output=True,text=True,timeout=30)
    assert check.returncode==0,check.stderr
    page=json.loads((output/'backlog.json').read_bytes())
    assert page['status']=='BACKLOG_READ' and not page['more'] and page['next_cursor'] is None
    assert {x['council'] for x in page['captures']}=={'tameside'}
    assert {x['council'] for x in page['records']}=={'tameside'}
    assert len(page['records'])==1 and page['source_calls']==page['registrations']==0
    assert restricted_sessions(world['boot'])==0


def test_changed_stop_prevents_supported_registration_and_preserves_history(world,tmp_path):
    reset(world);authorise(world,'stop-guard')
    with world['connect']('ingestion_worker_login') as c:c.execute("SELECT public.ingestion_raise_stop('DISPOSABLE_NEW_STOP')")
    target=tmp_path/'stopped';target.mkdir();_,result,_=invoke(world,target,'stop-guard')
    assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['scopes']==[]
    ctl=world['boot'].execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
    assert ctl['manual_stop']=='DISPOSABLE_NEW_STOP' and ctl['grants']=={}
    assert result['usage']['requests']==0


def test_policy_preserves_historical_registration_branch_text():
    from verification.ingestion_storage.operational_owner import GENERATION3_SCREENING_V3_POLICY
    old=GENERATION3_SCREENING_V3_POLICY.read_text();start=old.index(" IF NOT pg_has_role(session_user,'ingestion_barrier_releaser','USAGE') THEN")
    finish=old.index('END $register$;',start)
    assert old[start:finish] in intake_policy.policy_sql()


def test_cumulative_intake_lifetime_keeps_historical_batch_reservation():
    from verification.ingestion_storage.limit_reconciliation import pending_grant_problems
    assert pending_grant_problems(1500,phase='SCREENING',batches=12)
    assert pending_grant_problems(1500,phase='SCREENING',batches=12,cumulative_screening=True)==[]
    assert pending_grant_problems(329,phase='SCREENING',batches=12,cumulative_screening=True)


@pytest.mark.parametrize('fault',['unknown_source_failure','publication_failure'])
def test_shared_failure_stops_next_council_and_never_claims_capture(world,tmp_path,fault):
    reset(world);authorise(world,'shared-failure')
    env,sources=env_and_sources(world,tmp_path,failed=fault=='unknown_source_failure')
    if fault=='unknown_source_failure':
        file=sources/'tameside.json';audit=json.loads(file.read_text());audit['failure_diagnostic']['transport']['http_status']=500;file.write_text(json.dumps(audit))
    archive=tmp_path/'archive'
    if fault=='publication_failure':archive.write_text('existing file refuses archive directory')
    output=tmp_path/'result'
    command=[sys.executable,'-m','scripts.run_daily_councils','--period','shared-failure','--output',str(output),
             '--disposable-sources',str(sources),'--disposable-archive',str(archive)]
    run=subprocess.run(command,env=env,capture_output=True,text=True,timeout=30)
    result=json.loads((output/'final-result.json').read_text())
    assert run.returncode==1 and result['status']=='STOP_RECONCILE_NO_RETRY'
    assert result['effect_reconciliation_required'] and result['cleanup']=='CLOSED'
    assert not (output/'manchester-source.json').exists()
    assert world['boot'].execute("SELECT count(*) FROM ingestion_work_items WHERE task='DISCOVERY' AND state='COMPLETE'").fetchone()[0]==0
    assert restricted_sessions(world['boot'])==0


def test_stop_during_owned_source_closes_worker_and_preserves_original_stop(world,tmp_path):
    reset(world);authorise(world,'attended-stop');env,sources=env_and_sources(world,tmp_path)
    file=sources/'tameside.json';audit=json.loads(file.read_text());audit['_test_delay_seconds']=4;file.write_text(json.dumps(audit))
    output=tmp_path/'result'
    command=[sys.executable,'-m','scripts.run_daily_councils','--period','attended-stop','--output',str(output),
             '--disposable-sources',str(sources),'--disposable-archive',str(tmp_path/'archive')]
    process=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        end=time.monotonic()+10
        while not (output/'tameside-owned').exists() and time.monotonic()<end:time.sleep(.025)
        assert (output/'tameside-owned').exists()
        # Separate disposable owner acts as the attended stop operator. Opening
        # another worker login would itself violate the real one-connection cap.
        world['boot'].execute("SELECT public.ingestion_raise_stop('DISPOSABLE_ATTENDED_STOP')")
        process.communicate(timeout=20)
    finally:
        if process.poll() is None:process.kill();process.communicate(timeout=5)
    result=json.loads((output/'final-result.json').read_text())
    assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['cleanup']=='CLOSED'
    assert restricted_sessions(world['boot'])==0 and not (output/'manchester-source.json').exists()
    control=world['boot'].execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
    assert control['manual_stop']=='DISPOSABLE_ATTENDED_STOP'

def test_invalid_disposable_source_audit_never_reports_zero_requests_or_continues(world,tmp_path):
    # A supervised source failure has no trustworthy physical request count,
    # even if the synthetic worker did not return a usable audit.
    reset(world);authorise(world,'unaccounted-source')
    env,sources=env_and_sources(world,tmp_path)
    (sources/'tameside.json').write_text('{not-json')
    output=tmp_path/'result'
    command=[sys.executable,'-m','scripts.run_daily_councils','--period','unaccounted-source','--output',str(output),
             '--disposable-sources',str(sources),'--disposable-archive',str(tmp_path/'archive')]
    completed=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60)
    result=json.loads((output/'final-result.json').read_bytes())
    assert completed.returncode==1,completed.stderr
    assert result['status']=='STOP_RECONCILE_NO_RETRY',json.dumps(result,sort_keys=True)
    assert result['usage']['requests'] is None
    assert result['usage']['requests_status']=='UNKNOWN'
    assert result['usage']['requests_accounted']==0
    assert result['coverage_advance'] is False
    assert not (output/'manchester-source.json').exists()
    assert world['boot'].execute("SELECT count(*) FROM ingestion_work_items WHERE task='DISCOVERY' AND state='COMPLETE'").fetchone()[0]==0
    assert restricted_sessions(world['boot'])==0


@pytest.mark.parametrize('count',[22,30,31])
def test_counted_tameside_synthetic_audit_through_disposable_issuer_and_pg(world,tmp_path,count):
    """Exercise counted navigation -> the real daily command/issuer/retention/screening.

    Synthetic dispatch generates the source audit outside the credential-free
    source subprocess, which then reads it as a disposable fixture. This does
    NOT prove source-worker live transport or production Tameside authority.
    """
    from datetime import timedelta
    from tests.test_discovery_idox_window import page as old_page, Response
    from verification.bolton_recon.fixtures import FORM
    from verification.discovery.pagination_calibration import run_counted_window, COUNTED_MODE
    from verification.discovery.idox_window import WindowConfig
    from verification.discovery.source_profiles import profile,bind_audit
    from verification.discovery.four_council_proof import manifest_scope
    from app.pipeline.discovery_screening import retain_screening

    row=current_windows(datetime.now(timezone.utc),['tameside'])[0]
    start,end=map(date.fromisoformat,(row['start'],row['end']))
    config=WindowConfig('tameside','RECEIVED',start,end,0,60)
    selected=profile(row,'SCREENING_METADATA',idox_pagination=COUNTED_MODE)
    literal=(start+timedelta(days=3)).strftime('%a %d %b %Y').encode()
    begin=start.strftime('%d/%m/%Y').encode()
    finish=end.strftime('%d/%m/%Y').encode()
    echo=FORM.replace(b'name="date(applicationReceivedStart)" value=""',
                      b'name="date(applicationReceivedStart)" value="'+begin+b'"').replace(
                      b'name="date(applicationReceivedEnd)" value=""',
                      b'name="date(applicationReceivedEnd)" value="'+finish+b'"')

    def counted_page(number,take):
        refs=tuple(f'{(number-1)*5+i+1:03}/26' for i in range(take))
        body=old_page(refs=refs,pager=False).replace(b'Mon 28 Sep 2026',literal)
        for i in reversed(range(take)):
            body=body.replace(f'keyVal=K{i}'.encode(),f'keyVal=P{number}K{i}'.encode())
        body=body.replace(b'value="10" selected>10',b'value="5" selected>5')
        body=body.replace(b'name="action" value="order"',b'name="action" value="page"')
        body=body.replace(b'name="searchCriteria.page" value="1"',
                          f'name="searchCriteria.page" value="{number}"'.encode())
        first=(number-1)*5+1
        nav=f'<div class="pagination"><span class="current">{number}</span><p class="pager">Showing {first}-{first+take-1} of {count}</p>'
        if number*5<count:
            nav+=f'<a rel="next" href="pagedSearchResults.do?action=page&amp;searchCriteria.page={number+1}">Next</a>'
        return body.replace(b'</html>',(nav+'</div></html>').encode())

    first=counted_page(1,5)
    search=first.replace(b'<option value="5" selected>5</option>',
                         b'<option value="5">5</option><option value="10" selected>10</option>')
    bodies=[FORM,search,*[counted_page(n,min(5,count-5*(n-1))) for n in range(1,min((count+4)//5,6)+1)]]
    if count<=30:bodies.append(echo)
    calls=[]
    def transport(method,url,**kwargs):
        calls.append((method,url))
        assert len(calls)<=len(bodies),'UNEXPECTED_SOURCE_REQUEST'
        return Response(bodies[len(calls)-1])

    with manifest_scope(row,selected):
        source=run_counted_window(transport,config)
    source=retain_screening(bind_audit(selected,source))
    assert source['pagination_mode']==COUNTED_MODE
    if count>30:
        # Six pages are retained, but a seventh page and criteria refinement are refused.
        # This is evidence of an incomplete source, never permission to infer coverage.
        assert source['failure']=='CALIBRATION_PAGE_CAP'
        assert source['completeness']=='FAILED' and source['capped'] is True
        assert source['enumeration_evidence']!='COUNT_RECONCILED'
        assert len(calls)==8 and len(source['records'])==30
    else:
        assert source['failure'] is None and source['enumeration_evidence']=='COUNT_RECONCILED'
        assert len(calls)==3+(count+4)//5
        assert len(source['records'])==count

    # The disposable issuer accepts a test-only binding, independently of
    # whether any corresponding installed production policy is authorised.
    reset(world)
    period=f'counted-disposable-{count}'
    permitted=policy(world)
    permitted['councils']['tameside']['contract']='tameside-screening-metadata-five-v1'
    authorise(world,period,permitted)
    env,sources=env_and_sources(world,tmp_path)
    (sources/'tameside.json').write_text(json.dumps(source))
    output=tmp_path/'result'
    command=[sys.executable,'-m','scripts.run_daily_councils',
             '--period',period,'--output',str(output),
             '--disposable-sources',str(sources),
             '--disposable-archive',str(tmp_path/'archive')]
    run=subprocess.run(command,env=env,capture_output=True,text=True,timeout=75)
    result=json.loads((output/'final-result.json').read_bytes()) if (output/'final-result.json').exists() else {}
    if count>30:
        # The real disposable issuer/worker must not turn 30 retained partial
        # observations into a successful 31-record complete source capture.
        assert run.returncode!=0,(run.stderr,result)
        assert result['status'] in {'INCOMPLETE','STOP_RECONCILE_NO_RETRY'},result
        assert result['coverage_advance'] is False and result['admission_connected'] is False
        assert result['cleanup']=='CLOSED'
        assert not any(r.get('council')=='tameside' for r in result.get('backlog',{}).get('records',[]))
        assert world['boot'].execute(
            "SELECT count(*) FROM ingestion_work_items WHERE task='DISCOVERY' AND state='COMPLETE' AND subject->>'council'='tameside'"
        ).fetchone()[0]==0
        assert restricted_sessions(world['boot'])==0
        return
    assert run.returncode==0,(run.stderr,result)
    assert result['status']=='RETAINED_AND_SCREENED',result
    assert result['coverage_advance'] is False and result['admission_connected'] is False
    assert result['cleanup']=='CLOSED' and result['authority_closure']=='INVALIDATED'
    assert result['publication']=='TEST_LOCAL_ARCHIVE'
    assert len(result['backlog']['records'])==count+1
    checkpoint=world['boot'].execute(
        "SELECT checkpoint FROM ingestion_work_items WHERE task='DISCOVERY' AND state='COMPLETE' AND subject->>'council'='tameside'"
    ).fetchone()[0]
    assert checkpoint['pagination_mode']==COUNTED_MODE
    assert len(checkpoint['records'])==count
    assert restricted_sessions(world['boot'])==0

@pytest.mark.parametrize('count',[22,31])
def test_owned_tameside_child_audit_reaches_disposable_pg_intake_without_false_coverage(world,tmp_path,count):
    """Actual owned source worker/finite child audit -> existing disposable intake.

    A socket-denied synthetic HTTP shim runs inside the genuine finite child;
    the produced source-worker output (not a separately constructed audit) is
    handed to the unmodified disposable source fixture and then the real
    restricted SQL issuer/worker, archive and PostgreSQL path. This is an
    offline test-level handoff, NOT an unmodified production child-to-PG run
    or live source qualification.
    """
    from tests.test_source_profiles import synthetic_tameside_source_from_owned_child

    row=current_windows(datetime.now(timezone.utc),['tameside'])[0]
    source=synthetic_tameside_source_from_owned_child(tmp_path,count,row=row)
    assert source['requested_interval']==[row['start'],row['end']]
    assert source['pagination_mode']=='TAMESIDE_FIVE_COUNT_V1'
    assert len(source['records'])==(30 if count==31 else count)

    reset(world)
    period=f'owned-child-to-disposable-pg-{count}'
    permitted=policy(world)
    permitted['councils']['tameside']['contract']='tameside-screening-metadata-five-v1'
    authorise(world,period,permitted)
    env,sources=env_and_sources(world,tmp_path)
    (sources/'tameside.json').write_text(json.dumps(source))
    output=tmp_path/'result'
    command=[sys.executable,'-m','scripts.run_daily_councils',
             '--period',period,'--output',str(output),
             '--disposable-sources',str(sources),
             '--disposable-archive',str(tmp_path/'archive')]
    run=subprocess.run(command,env=env,capture_output=True,text=True,timeout=75)
    final=output/'final-result.json'
    assert final.is_file(),(run.returncode,run.stderr)
    result=json.loads(final.read_bytes())
    assert result['cleanup']=='CLOSED' and result['coverage_advance'] is False
    assert result['admission_connected'] is False
    assert restricted_sessions(world['boot'])==0

    if count==31:
        assert source['failure']=='CALIBRATION_PAGE_CAP'
        assert source['completeness']=='FAILED'
        assert run.returncode!=0,(run.stderr,result)
        assert result['status'] in {'INCOMPLETE','STOP_RECONCILE_NO_RETRY'},result
        assert not any(r.get('council')=='tameside' for r in result.get('backlog',{}).get('records',[]))
        assert world['boot'].execute(
            "SELECT count(*) FROM ingestion_work_items WHERE task='DISCOVERY' AND state='COMPLETE' AND subject->>'council'='tameside'"
        ).fetchone()[0]==0
    else:
        assert source['failure'] is None and source['enumeration_evidence']=='COUNT_RECONCILED'
        assert run.returncode==0,(run.stderr,result)
        assert result['status']=='RETAINED_AND_SCREENED',result
        assert result['authority_closure']=='INVALIDATED'
        assert result['publication']=='TEST_LOCAL_ARCHIVE'
        assert len(result['backlog']['records'])==count+1
        checkpoint=world['boot'].execute(
            "SELECT checkpoint FROM ingestion_work_items WHERE task='DISCOVERY' AND state='COMPLETE' AND subject->>'council'='tameside'"
        ).fetchone()[0]
        assert checkpoint['pagination_mode']=='TAMESIDE_FIVE_COUNT_V1'
        assert len(checkpoint['records'])==count
