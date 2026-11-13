"""Actual daily command -> supported issuer -> restricted PG -> supervised fixtures.

No production/source contact. Only fixture installation and expiring PERIOD
preauthorisation use the disposable migration principal; daily rows/grants are
issued by the production SQL function on the restricted worker connection.
"""
import copy,json,os,subprocess,sys,time
from datetime import datetime,timedelta,timezone,date
from pathlib import Path
from types import SimpleNamespace
from contextlib import nullcontext
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


def test_screening_only_owner_projection_preserves_every_authoritative_route():
    """A retained screening route is not a verified scheme or buyer opportunity."""
    from app.ingestion.daily_intake import _screening_only_state
    from app.ingestion.listing_screening import ROUTING_VOCABULARY
    for version,outcomes in ROUTING_VOCABULARY.items():
        for route in outcomes:
            result=dict(rule_version=version)
            if version==RULE_V3:
                result.update(routing_authority='count_assessment',
                              count_assessment=dict(admission=route))
            else:
                result['disposition']=route
            assert _screening_only_state(result)=='SCREENING_ONLY_'+route
    with pytest.raises(ValueError,match='ROUTING_OUTCOME_NOT_IN_VOCABULARY'):
        _screening_only_state(dict(rule_version=RULE_V3,routing_authority='count_assessment',
                                   count_assessment=dict(admission='VERIFIED_BUYER_OPPORTUNITY')))



@pytest.fixture(scope='module')
def world():
    for world in disposable_world():
        with world['connect']('provisioning_migrator') as c:c.execute(intake_policy.installation_script(disposable_catchup=True))
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


def env_and_sources(world,tmp_path,*,failed=False,count=1,catchup_window=None):
    rows=([dict(council=c,start=catchup_window['start'],end=catchup_window['end'])
           for c in ('tameside','manchester')] if catchup_window is not None
          else current_windows(datetime.now(timezone.utc),['tameside','manchester']))
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


def invoke(world,tmp_path,name,*,failed=False,count=1,catchup_window=None):
    env,sources=env_and_sources(world,tmp_path,failed=failed,count=count,catchup_window=catchup_window)
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
    # The immediate collector output and persisted owner page describe the same
    # screening-only route; neither is a verified scheme or factual admission.
    for item in result['backlog']['records']:
        if item['screening_state']=='COMPLETE':
            assert item['processing_state']=='SCREENING_ONLY_'+item['screening_outcome']
        else:
            assert item['processing_state']=='AWAITING_SCREENING'
        # This final command emits the cross-run owner page, which cannot
        # independently observe the downstream Application/extraction system.
        # Null is intentional: do not turn 'not tracked' into verified False.
        assert item['application_admitted'] is None and item['extraction_complete'] is None
        assert item['downstream_state']=='NOT_TRACKED_BY_INTAKE'
    # Owner-side exact SQL inventory: one committed readback per council.
    # Unknown/failed roots cannot be silently dropped before nomination.
    from verification.ingestion_storage.chain_registration import persisted_council_capture_inventory
    with nullcontext(world['boot']) as inventory_db:
        verified_m = persisted_council_capture_inventory(inventory_db, 'manchester')
        assert len(verified_m) == 1 and verified_m[0]['checkpoint']['council'] == 'manchester'
        if failed:
            with pytest.raises(Denied, match='CAPTURE_INVENTORY_UNRESOLVED'):
                persisted_council_capture_inventory(inventory_db, 'tameside')
        else:
            verified_t = persisted_council_capture_inventory(inventory_db, 'tameside')
            assert len(verified_t) == 1 and verified_t[0]['checkpoint']['council'] == 'tameside'
        # Trafford is a configured read-only inventory scope, not a qualified source.
        with pytest.raises(Denied, match='CAPTURE_INVENTORY_EMPTY_OR_BOUND'):
            persisted_council_capture_inventory(inventory_db, 'trafford')
        with pytest.raises(Denied, match='CAPTURE_INVENTORY_SCOPE'):
            persisted_council_capture_inventory(inventory_db, 'not-a-council')
        with pytest.raises(Denied, match='CAPTURE_INVENTORY_EMPTY_OR_BOUND'):
            persisted_council_capture_inventory(inventory_db, 'oldham')
        with pytest.raises(Denied, match='CAPTURE_INVENTORY_SCOPE'):
            persisted_council_capture_inventory(inventory_db, 'tameside', max_roots=0)
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



def test_disposable_backlog_refuses_corrupt_complete_capture_evidence(world,tmp_path):
    """Read the actual disposable saved backlog; roll back tampered evidence.

    A COMPLETE flag is insufficient for an unverified archive or contradictory
    terminal receipt. This runs only against the existing disposable PG fixture.
    """
    from sqlalchemy import text
    reset(world)
    name='backlog-durable-proof'
    authorise(world,name)
    run,result,_=invoke(world,tmp_path,name)
    assert run.returncode==0 and result['status']=='RETAINED_AND_SCREENED'
    before=snapshot(world['boot'])
    # Reuse the fixture's bootstrap engine; no new credentials or privileges.
    engine=world['app']
    reader=SimpleNamespace(_limits=lambda _connection: None)
    def read(connection):
        return backlog_page(reader,['tameside'],['daily-intake-tameside'],RULE,connection=connection)
    alterations=(
        "checkpoint=jsonb_set(checkpoint::jsonb,'{durable_archive,sha256}',to_jsonb(repeat('0',64)))::json",
        "checkpoint=jsonb_set(checkpoint::jsonb,'{durable_archive,readback_verified}','false'::jsonb)::json",
        "outcome=jsonb_set(outcome::jsonb,'{source_sha256}',to_jsonb(repeat('1',64)))::json",
        "checkpoint=jsonb_set(checkpoint::jsonb,'{accounting_complete}','false'::jsonb)::json",
        "checkpoint=jsonb_set(checkpoint::jsonb,'{date_semantics}',to_jsonb('VALIDATED'::text))::json",
        "checkpoint=(checkpoint::jsonb-'date_semantics')::json",
    )
    try:
        with engine.connect() as conn:
            baseline=read(conn)
            assert len(baseline['records'])==1 and baseline['records'][0]['council']=='tameside'
            root_key=conn.execute(text(
                "SELECT key FROM public.ingestion_work_items WHERE task='DISCOVERY' "
                "AND subject->>'council'='tameside'")).scalar_one()
            conn.rollback()
        for clause in alterations:
            with engine.connect() as conn:
                transaction=conn.begin()
                try:
                    conn.execute(text("UPDATE public.ingestion_work_items SET "+clause+" WHERE key=:key"),
                                 {'key':root_key})
                    with pytest.raises(Denied,match='BACKLOG_CAPTURE_PROVENANCE'):
                        read(conn)
                finally:
                    transaction.rollback()
        assert snapshot(world['boot'])==before
    finally:
        assert snapshot(world['boot'])==before


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


def _catchup_fixture(world):
    from zoneinfo import ZoneInfo
    from verification.discovery.finite_acceptance import manifest,digest as manifest_digest
    scope=dict(start='2026-09-15',end='2026-09-21',
               execution_day=datetime.now(timezone.utc).astimezone(ZoneInfo('Europe/London')).date().isoformat(),
               source_plan_sha256=manifest_digest(manifest('2026-09-15','2026-09-21','SUSPENSION_CATCHUP')))
    p=policy(world);p['max_runs']=1;p['catchup_scope']=scope
    return p,scope


def test_disposable_catchup_rejects_forged_source_manifest_before_issuer(world):
    reset(world);p,_=_catchup_fixture(world)
    p['catchup_scope']['source_plan_sha256']='f'*64
    with pytest.raises(ValueError,match='CATCHUP_SOURCE_PLAN_MISMATCH'):
        _catchup_owner(world).register_intake_period('forged-manifest',p,disposable_catchup=True)
    assert world['boot'].execute("SELECT count(*) FROM ingestion_work_items").fetchone()[0]==1


def _catchup_owner(world):
    return Owner(lambda:world['connect']('provisioning_migrator'),lambda *_:None,lambda:None,
                 identity='provisioning_migrator',expiry=datetime.now(timezone.utc)+timedelta(hours=1),
                 bindings=execution_binding())


def test_disposable_catchup_installed_sql_refuses_other_database_identity(world):
    """Read the effective installed SQL issuer, not just the Python source.

    The positive end-to-end test below executes this exact disposable route.
    No live or remote database is contacted to test the refusal predicate.
    """
    reset(world)
    with world['connect']('provisioning_migrator') as c:
        db,host,body=c.execute(
            "SELECT current_database(),inet_server_addr()::text,prosrc "
            "FROM pg_proc WHERE oid='public.ingestion_register_disposable_catchup(jsonb)'::regprocedure"
        ).fetchone()
    assert db=='ingestion_provisioning_test'
    # The server container reports its own bridge address; the client uses the
    # independently validated 127.0.0.1 disposable transport.
    assert host is not None
    assert "current_database() IS DISTINCT FROM 'ingestion_provisioning_test'" in body
    assert "INTAKE_CATCHUP_DISPOSABLE_ONLY" in body
    assert "intake_catchup_period" in body
    frozen=world['boot'].execute("SELECT prosrc FROM pg_proc WHERE oid='public.ingestion_register_bolton_exception(jsonb)'::regprocedure").fetchone()[0]
    assert "intake_catchup_period" not in frozen


def test_disposable_historical_issuer_actual_daily_command_and_committed_readback(world,tmp_path):
    reset(world);p,scope=_catchup_fixture(world);name='synthetic-catchup-window'
    issued=_catchup_owner(world).register_intake_period(name,p,disposable_catchup=True)
    assert issued['mode']=='DISPOSABLE_SHUTDOWN_GAP_V1'
    run,result,_=invoke(world,tmp_path,name,catchup_window=scope)
    assert run.returncode==0,(run.stderr,result)
    assert result['status']=='RETAINED_AND_SCREENED'
    assert result['coverage_advance'] is False and result['admission_connected'] is False
    assert result['cleanup']=='CLOSED' and result['authority_closure']=='INVALIDATED'
    assert len(result['scopes'])==2 and len(result['backlog']['records'])==2
    assert {s['council'] for s in result['scopes']}=={'tameside','manchester'}
    saved=world['boot'].execute("SELECT subject FROM ingestion_work_items WHERE task='DISCOVERY' AND state='COMPLETE'").fetchall()
    assert len(saved)==2
    assert all(s[0]['start']==scope['start'] and s[0]['end']==scope['end'] for s in saved)

    # The historical disposable issuer must feed the SAME capture-bound
    # persisted-screening admission preparation as the ordinary intake.
    # This is read-only preparation: it neither issues an admission grant nor
    # creates an Application, and is not evidence of real catch-up population.
    from app.ingestion.nomination import derive_nominees
    from verification.ingestion_storage.chain_registration import (
        persisted_council_capture_inventory, prepare_admission_from_persisted_captures)
    from verification.ingestion_storage.scope_binding import binding_for
    from tests.e2e_connection_support import idox_contract
    before=snapshot(world['boot'])
    retained=persisted_council_capture_inventory(world['boot'],'tameside')
    assert len(retained)==1 and retained[0]['state']=='COMPLETE'
    root=retained[0]
    derived=derive_nominees([root['checkpoint']],RULE,allow_test_evidence=True,
                            capture_bound=True)
    assert len(derived.nominees)==1
    nominee=derived.nominees[0]
    from tests.e2e_connection_support import idox_detail_target
    record=next(r for r in root['checkpoint']['records'] if r['reference']==nominee.reference)
    target=idox_detail_target('tameside',record,
                             case='chain_idox_tameside_'+digest(record))
    contract=idox_contract('tameside',date.fromisoformat(scope['start']),
                           date.fromisoformat(scope['end']),name=root['contract'])
    owner=Owner(None,lambda *_:None,lambda:None,
                expiry=datetime.now(timezone.utc)+timedelta(minutes=25),
                bindings=execution_binding())
    prepared,saved_nominees=prepare_admission_from_persisted_captures(
        world['boot'],owner,binding_for('tameside'),contract,root['key'],RULE,
        {nominee.reference:target},revision='offline-historical-prepare-only',
        item_limits=root['limits'],allow_test_evidence=True)
    assert prepared.kind=='ADMISSION' and len(prepared.facts)==1
    assert saved_nominees.sha256==derived.sha256
    assert prepared.facts[nominee.reference]['dependencies']
    assert snapshot(world['boot'])==before  # preparation never issues or writes facts

    # A historical catch-up screening child changed after retention must
    # fail closed before preparing factual admission; rollback proves this
    # test never changes a committed fixture or production database.
    world['boot'].execute('BEGIN')
    try:
        world['boot'].execute(
            "UPDATE ingestion_work_items SET checkpoint = "
            "jsonb_set(checkpoint::jsonb, '{capture_checkpoint_sha256}', "
            "to_jsonb(repeat('0',64)))::json "
            "WHERE task='SCREENING' AND subject->>'council'='tameside'")
        with pytest.raises(Denied,match='STAGED_ASSESSMENT_CHECKPOINT'):
            prepare_admission_from_persisted_captures(
                world['boot'],owner,binding_for('tameside'),contract,root['key'],
                RULE,{nominee.reference:target},
                revision='offline-historical-prepare-only',
                item_limits=root['limits'],allow_test_evidence=True)
    finally:
        world['boot'].execute('ROLLBACK')
    assert snapshot(world['boot'])==before



def test_shutdown_gap_sql_ledger_reads_exact_retained_screening_without_claiming_coverage(world,tmp_path):
    """Existing real disposable catch-up command -> all-ten interval SQL readback.

    Missing windows remain explicit, and tampered saved screening never upgrades
    a persisted discovery into verified screening or a buyer Application.
    """
    from verification.ingestion_storage.chain_registration import shutdown_gap_sql_readback
    reset(world)
    p,_ = _catchup_fixture(world)
    name = 'sql-gap-readback'
    _catchup_owner(world).register_intake_period(name,p,disposable_catchup=True)
    run,result,_ = invoke(world,tmp_path,name,catchup_window=p['catchup_scope'])
    assert run.returncode == 0 and result['status'] == 'RETAINED_AND_SCREENED', (run.stderr,result)
    before = snapshot(world['boot'])
    as_of = datetime(2026,11,10,12,tzinfo=timezone.utc)
    ledger = shutdown_gap_sql_readback(world['boot'],as_of)
    assert ledger['required_date_scopes'] == 90 and len(ledger['entries']) == 90
    assert ledger['sql_readback_scopes'] == 2
    assert ledger['sql_readback_screened_records'] == 2
    # A metadata-route census of two re-derived SQL scopes is not real
    # ten-council qualification or a saved buyer opportunity count.
    saved_routes = [row[0]['outcome'] for row in world['boot'].execute(
        "SELECT outcome FROM ingestion_work_items "
        "WHERE task='SCREENING' AND subject->>'council' IN ('tameside','manchester')"
    ).fetchall()]
    assert len(saved_routes) == 2
    expected_routes = {route: saved_routes.count(route) for route in sorted(set(saved_routes))}
    assert ledger['metadata_route_counts_for_readback_scopes'] == expected_routes
    inventory = {row['council']: row for row in ledger['persisted_receipt_inventory']}
    assert len(inventory) == 10
    for council in ('manchester','tameside'):
        assert inventory[council]['state'] == 'SQL_RECEIPT_METADATA_READBACK_ONLY'
        assert inventory[council]['distinct_references'] == 1
        assert inventory[council]['receipt_rows'] == 1
        assert inventory[council]['duplicate_reference_rows'] == 0
    assert inventory['bolton']['state'] == 'NO_COMPLETE_SQL_CAPTURE'
    assert inventory['bolton']['distinct_references'] is None
    assert inventory['trafford']['state'] == 'NO_COMPLETE_SQL_CAPTURE'
    assert inventory['trafford']['distinct_references'] is None
    first = [x for x in ledger['entries'] if x['start']=='2026-09-15' and x['end']=='2026-09-21']
    assert {x['council'] for x in first if x['state']=='SQL_CAPTURE_AND_SCREENING_READBACK'} == {'manchester','tameside'}
    for entry in first:
        if entry['council'] in ('manchester','tameside'):
            assert sum(entry['metadata_route_counts'].values()) == 1
        else:
            assert entry['metadata_route_counts'] is None
    assert next(x for x in first if x['council']=='trafford')['state'] == 'NO_EXACT_PERSISTED_SQL_CAPTURE'
    assert all(x['source_coverage']=='UNKNOWN' and x['source_qualified'] is False and
               x['factual_qualifications'] is None and x['newly_added'] is None and
               x['saved_key_facts'] is None and x['buyer_backlog'] is None for x in ledger['entries'])
    assert snapshot(world['boot']) == before
    world['boot'].execute('BEGIN')
    try:
        world['boot'].execute(
            "UPDATE ingestion_work_items SET checkpoint = "
            "jsonb_set(checkpoint::jsonb, '{capture_checkpoint_sha256}', "
            "to_jsonb(repeat('0',64)))::json "
            "WHERE task='SCREENING' AND subject->>'council'='tameside'")
        altered=shutdown_gap_sql_readback(world['boot'],as_of)
        changed=next(x for x in altered['entries'] if x['council']=='tameside' and x['start']=='2026-09-15')
        assert changed['state']=='SQL_CAPTURE_SCREENING_UNVERIFIED'
        assert changed['screened_sql_records'] is None
        assert changed['metadata_route_counts'] is None
        assert altered['sql_readback_scopes']==1
        assert sum(altered['metadata_route_counts_for_readback_scopes'].values()) == 1
    finally:
        world['boot'].execute('ROLLBACK')
    assert snapshot(world['boot'])==before
    # A forged route must be rejected even when the row remains COMPLETE.
    world['boot'].execute('BEGIN')
    try:
        world['boot'].execute(
            "UPDATE ingestion_work_items SET outcome = "
            "jsonb_set(outcome::jsonb, '{outcome}', to_jsonb('FORGED_ADMISSION'::text))::json "
            "WHERE task='SCREENING' AND subject->>'council'='tameside'")
        forged = shutdown_gap_sql_readback(world['boot'], as_of)
        tameside = next(x for x in forged['entries']
                        if x['council']=='tameside' and x['start']=='2026-09-15')
        assert tameside['state']=='SQL_CAPTURE_SCREENING_UNVERIFIED'
        assert tameside['metadata_route_counts'] is None
    finally:
        world['boot'].execute('ROLLBACK')
    assert snapshot(world['boot'])==before
    # A saved readback flag and matching source hash cannot upgrade failed,
    # incomplete, foreign-contract or wrong-date-basis source metadata.
    for tamper_sql in (
        "UPDATE ingestion_work_items SET outcome="
        "jsonb_set(outcome::jsonb, '{outcome}', to_jsonb('RATE_LIMIT'::text))::json "
        "WHERE task='DISCOVERY' AND subject->>'council'='tameside'",
        "UPDATE ingestion_work_items SET checkpoint="
        "jsonb_set(checkpoint::jsonb, '{accounting_complete}', 'false'::jsonb)::json "
        "WHERE task='DISCOVERY' AND subject->>'council'='tameside'",
        "UPDATE ingestion_work_items SET checkpoint="
        "jsonb_set(checkpoint::jsonb, '{cleanup}', to_jsonb('OPEN'::text))::json "
        "WHERE task='DISCOVERY' AND subject->>'council'='tameside'",
        "UPDATE ingestion_work_items SET checkpoint="
        "jsonb_set(checkpoint::jsonb, '{contract}', to_jsonb('foreign-contract'::text))::json "
        "WHERE task='DISCOVERY' AND subject->>'council'='tameside'",
        "UPDATE ingestion_work_items SET checkpoint="
        "jsonb_set(checkpoint::jsonb, '{date_semantics}', to_jsonb('UNKNOWN'::text))::json "
        "WHERE task='DISCOVERY' AND subject->>'council'='tameside'",
    ):
        world['boot'].execute('BEGIN')
        try:
            world['boot'].execute(tamper_sql)
            refused = shutdown_gap_sql_readback(world['boot'], as_of)
            tameside = next(x for x in refused['persisted_receipt_inventory']
                            if x['council'] == 'tameside')
            assert tameside['state'] == 'SQL_RECEIPT_METADATA_UNVERIFIED'
            assert tameside['distinct_references'] is None
            assert tameside['receipt_rows'] is None
            assert refused['sql_readback_scopes'] == 1
        finally:
            world['boot'].execute('ROLLBACK')
        assert snapshot(world['boot']) == before

    # An overlapping but non-identical retained root is an unresolved gap,
    # not proof that the canonical seven-day window was fully covered.
    world['boot'].execute('BEGIN')
    try:
        world['boot'].execute(
            "UPDATE ingestion_work_items SET subject = "
            "jsonb_set(subject::jsonb, '{start}', to_jsonb('2026-09-16'::text))::json "
            "WHERE task='DISCOVERY' AND subject->>'council'='tameside'")
        overlapping=shutdown_gap_sql_readback(world['boot'],as_of)
        changed=next(x for x in overlapping['entries'] if x['council']=='tameside' and x['start']=='2026-09-15')
        assert changed['state']=='OVERLAP_OR_CONFLICT_REQUIRES_REVIEW'
        assert changed['screened_sql_records'] is None
        assert overlapping['sql_readback_scopes']==1
        # A contradictory receipt interval must not create a usable count.
        tameside = next(x for x in overlapping['persisted_receipt_inventory']
                        if x['council']=='tameside')
        assert tameside['state']=='SQL_RECEIPT_METADATA_UNVERIFIED'
        assert tameside['distinct_references'] is None
    finally:
        world['boot'].execute('ROLLBACK')
    assert snapshot(world['boot'])==before
    # A stored readback flag alone does not overcome a conflicting archive
    # digest. Refuse the retained-count claim; leave all original rows intact.
    world['boot'].execute('BEGIN')
    try:
        world['boot'].execute(
            "UPDATE ingestion_work_items SET checkpoint = "
            "jsonb_set(checkpoint::jsonb, '{durable_archive,sha256}', "
            "to_jsonb(repeat('f',64)))::json "
            "WHERE task='DISCOVERY' AND subject->>'council'='tameside'")
        inconsistent=shutdown_gap_sql_readback(world['boot'],as_of)
        value=next(x for x in inconsistent['persisted_receipt_inventory']
                   if x['council']=='tameside')
        assert value['state']=='SQL_RECEIPT_METADATA_UNVERIFIED'
        assert value['distinct_references'] is None
        assert inconsistent['sql_readback_scopes']==1
    finally:
        world['boot'].execute('ROLLBACK')
    assert snapshot(world['boot'])==before


@pytest.mark.parametrize('fault',['rolling_smuggle','live_mode','too_long','unfinished_day','changed_capture'])
def test_disposable_historical_issuer_refuses_unapproved_scope(world,fault):
    from zoneinfo import ZoneInfo
    from app.ingestion.ledger import DEFAULT_LIMITS
    from verification.ingestion_storage.chain_registration import capture_registration
    from verification.ingestion_storage.scope_binding import binding_for
    from tests.e2e_connection_support import idox_contract
    reset(world);p,scope=_catchup_fixture(world);name='catchup-refuse-'+fault
    if fault in ('rolling_smuggle','live_mode','too_long','unfinished_day'):
        if fault=='live_mode':p['test_evidence']=False
        if fault=='too_long':scope['end']='2026-09-22'
        if fault=='unfinished_day':scope['end']=datetime.now(timezone.utc).astimezone(ZoneInfo('Europe/London')).date().isoformat()
        expected=ValueError if fault in ('too_long','unfinished_day','rolling_smuggle') else Exception
        message=('INTAKE_ROLLING_SCOPE_ONLY' if fault=='rolling_smuggle' else
                 'CATCHUP_SOURCE_PLAN_MISMATCH' if expected is ValueError else 'ADMIN_EFFECT_UNCERTAIN')
        with pytest.raises(expected,match=message):
            _catchup_owner(world).register_intake_period(name,p,disposable_catchup=fault!='rolling_smuggle')
        assert world['boot'].execute("SELECT count(*) FROM ingestion_work_items").fetchone()[0]==1
        return
    _catchup_owner(world).register_intake_period(name,p,disposable_catchup=True)
    start,end=date(2026,9,16),date(2026,9,21)
    contract=idox_contract('tameside',start,end,name=p['councils']['tameside']['contract'])
    source_owner=Owner(None,lambda *_:None,lambda:None,expiry=datetime.now(timezone.utc)+timedelta(minutes=20),bindings=execution_binding())
    reg=capture_registration(source_owner,binding_for('tameside'),contract,start.isoformat(),end.isoformat(),
                             revision='catchup-refusal',item_limits=DEFAULT_LIMITS)
    with world['connect']('ingestion_worker_login') as c:
        with pytest.raises(Exception,match='INTAKE_ROLLING_SCOPE_OR_CONSUMED'):
            c.execute('SELECT public.ingestion_register_disposable_catchup(%s::jsonb)',
                      (json.dumps(registration_payload(name,reg,execution_binding())),))
    assert world['boot'].execute("SELECT count(*) FROM ingestion_work_items").fetchone()[0]==1


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


@pytest.mark.parametrize('anchor',['register','allowed'])
@pytest.mark.parametrize('disposable_catchup',[False,True])
def test_sql_issuer_rejects_reviewed_template_anchor_drift(monkeypatch,tmp_path,anchor,disposable_catchup):
    """A changed reviewed insertion point must never emit a fallback issuer.

    This tests refusal without contacting a database or enabling a grant.
    """
    from verification.ingestion_storage import operational_owner
    source=operational_owner.GENERATION3_SCREENING_V3_POLICY.read_text()
    if anchor=='register':
        original="BEGIN\n IF NOT pg_has_role"
        expected='INTAKE_SQL_ISSUER_ANCHOR_DRIFT'
    else:
        original=' SELECT coalesce('
        expected='INTAKE_SQL_ALLOWED_ANCHOR_DRIFT'
    assert source.count(original)==1
    candidate=tmp_path/'policy-with-anchor-drift.sql'
    candidate.write_text(source.replace(original,original.replace(' ', '  ', 1),1))
    monkeypatch.setattr(operational_owner,'GENERATION3_SCREENING_V3_POLICY',candidate)
    with pytest.raises(ValueError,match=expected):
        intake_policy.policy_sql(disposable_catchup=disposable_catchup)


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
        assert all(item['processing_state']=='SCREENING_ONLY_'+item['screening_outcome']
                   and item['application_admitted'] is None
                   and item['extraction_complete'] is None
                   and item['downstream_state']=='NOT_TRACKED_BY_INTAKE'
                   for item in result['backlog']['records'])
        checkpoint=world['boot'].execute(
            "SELECT checkpoint FROM ingestion_work_items WHERE task='DISCOVERY' AND state='COMPLETE' AND subject->>'council'='tameside'"
        ).fetchone()[0]
        assert checkpoint['pagination_mode']=='TAMESIDE_FIVE_COUNT_V1'
        assert len(checkpoint['records'])==count


def test_persisted_capture_bound_screening_prepares_exact_offline_admission_without_effect(world,tmp_path):
    """Actual disposable intake -> committed SQL readback -> exact bound admission preparation.

    Preparation is pure: the existing worker has NO admission issuance or factual write
    permission here. A successful metadata screening is not a verified buyer fact.
    """
    from app.ingestion.nomination import derive_nominees
    from verification.ingestion_storage.chain_registration import admission_registration
    from verification.ingestion_storage.scope_binding import binding_for
    from tests.e2e_connection_support import idox_contract
    from app.ingestion.observation_screening import observation_revision

    reset(world)
    name='handoff-capture-bound'
    authorise(world,name)
    run,result,_=invoke(world,tmp_path,name)
    assert run.returncode==0 and result['status']=='RETAINED_AND_SCREENED'
    all_rows=[row[0] for row in world['boot'].execute(
        "SELECT row_to_json(w) FROM ingestion_work_items w WHERE key<>repeat('0',64)").fetchall()]
    from verification.ingestion_storage.chain_registration import persisted_council_capture_inventory
    with nullcontext(world['boot']) as inventory_db:
        roots=persisted_council_capture_inventory(inventory_db,'tameside')
    assert len(roots)==1 and roots[0]['state']=='COMPLETE'
    root=roots[0]
    receipt=root['checkpoint']
    selected=[r for r in all_rows if r['task'] in ('LISTING_METADATA','SCREENING') and r['subject']['council']=='tameside']
    assert len(selected)==2 and all(r['state']=='COMPLETE' for r in selected)
    screen=next(r for r in selected if r['task']=='SCREENING')
    ordinary=derive_nominees([receipt],RULE,allow_test_evidence=True)
    candidates=derive_nominees([receipt],RULE,allow_test_evidence=True,capture_bound=True)
    assert len(candidates.nominees)==1 and candidates.sha256!=ordinary.sha256
    nominee=candidates.nominees[0]
    assert nominee.screening_revision==screen['revision']
    assert screen['revision']==observation_revision(ordinary.nominees[0].screening_revision,digest(receipt))
    from tests.e2e_connection_support import idox_detail_target
    record=next(r for r in root['checkpoint']['records'] if r['reference']==nominee.reference)
    target=idox_detail_target('tameside',record,
                             case='chain_idox_tameside_'+digest(record))
    contract=idox_contract('tameside',date.fromisoformat(root['subject']['start']),
                           date.fromisoformat(root['subject']['end']),name=root['contract'])
    owner=Owner(None,lambda *_:None,lambda:None,
                expiry=datetime.now(timezone.utc)+timedelta(minutes=25),bindings=execution_binding())
    before=snapshot(world['boot'])
    kwargs=dict(revision='offline-prepare-only',item_limits=root['limits'],
                screening_rows=selected,allow_test_evidence=True,capture_bound=True)
    # Source reference and URL alone are insufficient to prepare a usable
    # official-summary detail read. This must fail before any owner issuance.
    with pytest.raises(Denied,match='SCOPE_DETAIL_TARGET_MISMATCH'):
        admission_registration(owner,binding_for('tameside'),contract,
            root,receipt,candidates.nominees,RULE,
            {nominee.reference:dict(council='tameside',reference=nominee.reference,
                                    source_url=nominee.source_url,
                                    source_identifier=nominee.source_record_id)},
            **dict(kwargs,other_receipts=tuple(r['checkpoint'] for r in roots if r['key']!=root['key'])))
    registration=admission_registration(owner,binding_for('tameside'),contract,
        root,receipt,candidates.nominees,RULE,{nominee.reference:target},
        **dict(kwargs,other_receipts=tuple(r['checkpoint'] for r in roots if r['key']!=root['key'])))
    assert registration.kind=='ADMISSION' and len(registration.facts)==1
    assert registration.screens[nominee.reference]['key']==screen['key']
    assert registration.facts[nominee.reference]['dependencies']==[screen['key']]
    assert registration.grant['source_calls']==1
    from verification.ingestion_storage.chain_registration import prepare_admission_from_persisted_captures
    prepared, independently_derived = prepare_admission_from_persisted_captures(
        world['boot'], owner, binding_for('tameside'), contract, root['key'],
        RULE, {nominee.reference:target}, revision='offline-prepare-only',
        item_limits=root['limits'], allow_test_evidence=True)
    assert independently_derived.sha256 == candidates.sha256
    assert prepared.facts == registration.facts
    assert prepared.screens[nominee.reference]['key'] == screen['key']
    # Execute the EXISTING Idox detail parser and projector with an injected
    # synthetic response using the very target saved by owner preparation.
    # This demonstrates an actual compatible detail contract, not a B2 write,
    # live source qualification, or an approved factual task.
    from tests.e2e_connection_support import idox_detail
    from verification.direct_reference.fixtures import summary
    from verification.discovery.material_qualification import project_idox
    from verification.ingestion_storage.new_identity_contract import qualified_coupled_observation
    source=idox_detail(target,summary(nominee.reference,status='Decided',
                                     decision='Approve',date='Mon 28 Sep 2026'))
    detail=project_idox(target,source)
    assert detail['failure'] is None
    assert detail['observation'].verification_scope=='COUPLED'
    assert qualified_coupled_observation(detail['observation'],target)
    assert snapshot(world['boot']) == before  # no task or B2 effect
    from unittest.mock import patch
    import verification.ingestion_storage.chain_registration as chain_module
    with patch.object(chain_module, 'persisted_council_capture_inventory',
                      side_effect=[roots, tuple()]):
        with pytest.raises(Denied, match='PERSISTED_ADMISSION_INVENTORY_CHANGED'):
            prepare_admission_from_persisted_captures(
                world['boot'], owner, binding_for('tameside'), contract, root['key'],
                RULE, {nominee.reference:target}, revision='offline-prepare-only',
                item_limits=root['limits'], allow_test_evidence=True)
    assert snapshot(world['boot']) == before
    # Neither a caller's invented root nor a tampered persisted assessment
    # can be admitted through the owner-side inventory preparation.
    with pytest.raises(Denied, match='PERSISTED_ADMISSION_ROOT_NOT_FOUND'):
        prepare_admission_from_persisted_captures(
            world['boot'], owner, binding_for('tameside'), contract, 'f'*64, RULE,
            {nominee.reference:target}, revision='offline-prepare-only',
            item_limits=root['limits'], allow_test_evidence=True)
    world['boot'].execute('BEGIN')
    try:
        world['boot'].execute(
            "UPDATE ingestion_work_items SET checkpoint = "
            "jsonb_set(checkpoint::jsonb, '{capture_checkpoint_sha256}', "
            "to_jsonb(repeat('0',64)))::json "
            "WHERE task='SCREENING' AND subject->>'council'='tameside'")
        with pytest.raises(Denied, match='STAGED_ASSESSMENT_CHECKPOINT'):
            prepare_admission_from_persisted_captures(
                world['boot'], owner, binding_for('tameside'), contract, root['key'],
                RULE, {nominee.reference:target}, revision='offline-prepare-only',
                item_limits=root['limits'], allow_test_evidence=True)
    finally:
        world['boot'].execute('ROLLBACK')
    assert snapshot(world['boot']) == before
    # A completed screening row may change after preparation's first read.
    # Inject a real disposable-PG change inside a rolled-back transaction and
    # require the optimistic saved-child fence to refuse the stale result.
    world['boot'].execute('BEGIN')
    try:
        original_admission = chain_module.admission_registration
        def concurrent_screen_change(*args, **kwargs):
            candidate = original_admission(*args, **kwargs)
            world['boot'].execute(
                "UPDATE ingestion_work_items SET checkpoint = "
                "jsonb_set(checkpoint::jsonb, '{source_sha256}', "
                "to_jsonb(repeat('2',64)))::json "
                "WHERE task='SCREENING' AND subject->>'council'='tameside'")
            return candidate
        with patch.object(chain_module, 'admission_registration',
                          side_effect=concurrent_screen_change):
            with pytest.raises(Denied, match='PERSISTED_ADMISSION_SCREENING_CHANGED'):
                prepare_admission_from_persisted_captures(
                    world['boot'], owner, binding_for('tameside'), contract, root['key'],
                    RULE, {nominee.reference: target}, revision='offline-prepare-only',
                    item_limits=root['limits'], allow_test_evidence=True)
    finally:
        world['boot'].execute('ROLLBACK')
    assert snapshot(world['boot']) == before
    # A corrupt committed archive readback must not be accepted as a complete
    # candidate merely because the underlying root state still says COMPLETE.
    # Change only a disposable transaction and roll it back before exit.
    with nullcontext(world['boot']) as inventory_db:
        # The disposable bootstrap connection is autocommit. Explicitly
        # bound this negative mutation to a transaction and always rollback.
        inventory_db.execute('BEGIN')
        try:
            inventory_db.execute(
                "UPDATE ingestion_work_items SET checkpoint = "
                "jsonb_set(checkpoint::jsonb, '{durable_archive,readback_verified}', 'false'::jsonb)::json "
                "WHERE task='DISCOVERY' AND subject->>'council'='tameside'"
            )
            with pytest.raises(Denied, match='CAPTURE_INVENTORY_UNVERIFIED'):
                persisted_council_capture_inventory(inventory_db, 'tameside')
        finally:
            inventory_db.execute('ROLLBACK')
    # The complete root's terminal source hash, receipt and durable archive
    # must independently agree. Neither a COMPLETE flag nor a claimed readback
    # can upgrade a conflicting persisted capture into admission evidence.
    for sql in (
        "UPDATE ingestion_work_items SET checkpoint = "
        "jsonb_set(checkpoint::jsonb, '{durable_archive,sha256}', "
        "to_jsonb(repeat('0',64)))::json "
        "WHERE task='DISCOVERY' AND subject->>'council'='tameside'",
        "UPDATE ingestion_work_items SET outcome = "
        "jsonb_set(outcome::jsonb, '{source_sha256}', "
        "to_jsonb(repeat('1',64)))::json "
        "WHERE task='DISCOVERY' AND subject->>'council'='tameside'",
    ):
        world['boot'].execute('BEGIN')
        try:
            world['boot'].execute(sql)
            with pytest.raises(Denied, match='CAPTURE_INVENTORY_UNVERIFIED'):
                persisted_council_capture_inventory(world['boot'], 'tameside')
        finally:
            world['boot'].execute('ROLLBACK')
        assert snapshot(world['boot'])==before
    assert snapshot(world['boot'])==before  # no issuer/grant/work-item/learnt fact changed
    with pytest.raises(Denied):
        admission_registration(owner,binding_for('tameside'),contract,root,receipt,
            ordinary.nominees,RULE,{nominee.reference:target},
            revision='offline-prepare-only',item_limits=root['limits'],
            screening_rows=selected,allow_test_evidence=True)
    damaged=copy.deepcopy(selected)
    next(r for r in damaged if r['task']=='SCREENING')['checkpoint']['capture_checkpoint_sha256']='0'*64
    with pytest.raises(Denied,match='STAGED_ASSESSMENT_CHECKPOINT'):
        admission_registration(owner,binding_for('tameside'),contract,root,receipt,
            candidates.nominees,RULE,{nominee.reference:target},
            **dict(kwargs,screening_rows=damaged))
    assert snapshot(world['boot'])==before

    # A later/overlapping retained observation that disagrees is never
    # silently admitted when included in the bounded evidence candidate.
    # The caller must independently supply complete relevant history;
    # this guard cannot prove history enumeration.
    conflicting=copy.deepcopy(receipt)
    conflicting['records'][0]['source_record_id']+='-DIFFERENT'
    with pytest.raises(Denied,match='CHAIN_NOMINEES_NOT_DERIVED'):
        admission_registration(owner,binding_for('tameside'),contract,root,receipt,
            candidates.nominees,RULE,{nominee.reference:target},
            **dict(kwargs,other_receipts=(conflicting,)))
    assert snapshot(world['boot'])==before

def test_backlog_does_not_duplicate_or_promote_historical_v1_v3_screenings(world,tmp_path):
    """Disposable SQL regression for actual Bolton-style dual history.

    A v1 receipt plus one capture-bound v3 receipt is one unique listing. If
    the v3 is unbound, keep the listing discoverable but do not claim a verified
    screening outcome. Unknown/competing contracts remain fail-closed.
    """
    from sqlalchemy import text
    from verification.ingestion_storage.retained_world import item

    reset(world)
    authorise(world,'dual-historical-screening')
    run,result,_=invoke(world,tmp_path,'dual-historical-screening')
    assert run.returncode==0 and result['status']=='RETAINED_AND_SCREENED'
    actual=world['boot'].execute(
        "SELECT row_to_json(w) FROM ingestion_work_items w "
        "WHERE task='SCREENING' AND subject->>'council'='tameside'").fetchone()[0]
    assert actual['contract']=='listing-screen-v3'
    assert actual['state']=='COMPLETE' and actual['checkpoint']['capture_bound'] is True
    legacy=item(dict(subject=actual['subject'],task='SCREENING',
                     contract='listing-screen-v1',revision='historical-unbound-v1'),
                dependencies=actual['dependencies'])
    legacy.update(state='COMPLETE',phase='FINISHED',checkpoint=dict(
        outcome='INSUFFICIENT_EVIDENCE'),outcome=dict(outcome='LEGACY_EVIDENCE_ONLY'))
    world['boot'].execute(
        'INSERT INTO ingestion_work_items SELECT * FROM '
        'json_populate_record(NULL::ingestion_work_items,%s::json)',(json.dumps(legacy),))

    reader=SimpleNamespace(_limits=lambda _connection:None)
    def read(conn):
        return backlog_page(reader,['tameside'],['daily-intake-tameside'],RULE,connection=conn)

    with world['app'].connect() as conn:
        modern=read(conn)['records']
        assert len(modern)==1
        assert modern[0]['screening_key']==actual['key']
        assert modern[0]['screening_state']=='COMPLETE'
        assert modern[0]['historical_screening_items']==2
        assert modern[0]['screening_outcome'] is not None
        assert modern[0]['processing_state']==('SCREENING_ONLY_'+modern[0]['screening_outcome'])
        assert modern[0]['application_admitted'] is None
        assert modern[0]['extraction_complete'] is None
        conn.rollback()
    # Retain old screening rows, but do not silently qualify unbound results.
    with world['app'].connect() as conn:
        trans=conn.begin()
        try:
            conn.execute(text(
                "UPDATE ingestion_work_items SET checkpoint="
                "(checkpoint::jsonb-'capture_bound')::json WHERE key=:key"),
                dict(key=actual['key']))
            historical=read(conn)['records']
            assert len(historical)==1
            assert historical[0]['screening_state']=='HISTORICAL_UNBOUND_REQUIRES_RESCREENING'
            assert historical[0]['historical_screening_items']==2
            assert historical[0]['screening_key'] is None
            assert historical[0]['screening_outcome'] is None
            assert historical[0]['processing_state']=='HISTORICAL_RESCREENING_REQUIRED'
            assert historical[0]['application_admitted'] is None
        finally:
            trans.rollback()
    # A third unknown assessment type cannot be silently dropped to make a
    # backlog look available. Everything in this block rolls back.
    other=item(dict(subject=actual['subject'],task='SCREENING',
                    contract='unreviewed-screen-v999',revision='not-qualified'),
               dependencies=actual['dependencies'])
    other.update(state='COMPLETE',phase='FINISHED',checkpoint=dict(
        outcome='UNKNOWN'),outcome=dict(outcome='UNKNOWN'))
    with world['app'].connect() as conn:
        trans=conn.begin()
        try:
            conn.execute(text(
                'INSERT INTO ingestion_work_items SELECT * FROM '
                'json_populate_record(NULL::ingestion_work_items,CAST(:payload AS json))'),
                dict(payload=json.dumps(other)))
            with pytest.raises(Denied,match='BACKLOG_UNKNOWN_ASSESSMENT_CONTRACT'):
                read(conn)
        finally:
            trans.rollback()

def test_pinned_bolton_dual_screenings_remain_unqualified_discoverable_backlog(world):
    """Read-only backlog over 24 pinned Bolton listing receipts and 48 v1/v3 rows.

    Pinned source/archive proof is reproduced from the existing reviewed
    historical fixture; test inserts are disposable only. Neither the legacy
    v1 nor its unbound v3 successor is allowed to claim a current screening
    or create an Application, even where v3 routes ADMIT_SCHEME.
    """
    from verification.ingestion_storage.retained_world import retained,identities,v3_items
    from app.ingestion.listing_screening import ScreeningRule,RULE_V1

    reset(world)
    _,receipt=retained()
    root,v1,_,_,_=identities(receipt)
    _,_,v3=v3_items(receipt,RULE)
    assert len(receipt['records'])==len(v1)==len(v3)==24
    assert receipt['source_sha256']=='5525be5a6b5fc3fdfac43849bc502cd05c0c9023da1440627b975672fe55013a'
    assert 'date_semantics' not in receipt  # immutable RECEIVED-v1 legacy shape
    root.update(state='COMPLETE',phase='FINISHED',checkpoint=receipt,
                outcome=dict(outcome='ENUMERATED_METADATA_RETAINED',
                             source_sha256=receipt['source_sha256']))
    v1_rule=ScreeningRule(RULE_V1)
    for record,old,new in zip(receipt['records'],v1,v3):
        old_checkpoint=v1_rule.screen(record)
        new_checkpoint=RULE.screen(record)
        old.update(state='COMPLETE',phase='FINISHED',checkpoint=old_checkpoint,
                   outcome=dict(outcome=old_checkpoint['disposition']))
        new.update(state='COMPLETE',phase='FINISHED',checkpoint=new_checkpoint,
                   outcome=dict(outcome=new_checkpoint['count_assessment']['admission']))
    assert sum(x['outcome']['outcome']=='ADMIT_SCHEME' for x in v3)==1
    for item_record in (root,*v1,*v3):
        world['boot'].execute(
            'INSERT INTO ingestion_work_items SELECT * FROM '
            'json_populate_record(NULL::ingestion_work_items,%s::json)',
            (json.dumps(item_record),))
    # The same pinned Bolton RECEIVED-v1 root must be inventory-readable
    # by the owner-side admission-preparation path, not only backlog_page.
    # This does NOT make either unbound historical assessment admissible.
    from verification.ingestion_storage.chain_registration import persisted_council_capture_inventory
    baseline = snapshot(world['boot'])
    inventory = persisted_council_capture_inventory(world['boot'], 'bolton')
    assert len(inventory) == 1 and inventory[0]['key'] == root['key']
    assert inventory[0]['checkpoint']['source_sha256'] == receipt['source_sha256']
    for tamper_sql in (
        "UPDATE ingestion_work_items SET checkpoint="
        "jsonb_set(checkpoint::jsonb,'{date_semantics}',"
        "to_jsonb('VALIDATED'::text))::json WHERE key=%s",
        "UPDATE ingestion_work_items SET subject="
        "jsonb_set(subject::jsonb,'{semantics}',"
        "to_jsonb('VALIDATED'::text))::json WHERE key=%s",
    ):
        world['boot'].execute('BEGIN')
        try:
            world['boot'].execute(tamper_sql, (root['key'],))
            with pytest.raises(Denied, match='CAPTURE_INVENTORY_UNVERIFIED'):
                persisted_council_capture_inventory(world['boot'], 'bolton')
        finally:
            world['boot'].execute('ROLLBACK')
        assert snapshot(world['boot']) == baseline
    reader=SimpleNamespace(_limits=lambda _connection:None)
    with world['app'].connect() as conn:
        observed=backlog_page(reader,['bolton'],[root['contract']],RULE,connection=conn)
        conn.rollback()
    assert len(observed['captures'])==1 and observed['captures'][0]['record_count']==24
    assert len(observed['records'])==24
    assert len({r['reference'] for r in observed['records']})==24
    assert all(r['historical_screening_items']==2
               and r['screening_state']=='HISTORICAL_UNBOUND_REQUIRES_RESCREENING'
               and r['screening_outcome'] is None
               and r['application_admitted'] is None
               and r['processing_state']=='HISTORICAL_RESCREENING_REQUIRED'
               and r['source_sha256']==receipt['source_sha256']
               for r in observed['records'])
    assert not observed['coverage_advance'] and not observed['extraction_consumer_connected']
    assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0



def test_pinned_bolton_triple_screen_history_bounded_without_factual_promotion(world):
    """72 persisted screening versions, 24 identities, zero factual admissions."""
    from sqlalchemy import text
    from app.ingestion.listing_screening import RULE_V1,assessment_identity
    from app.ingestion.observation_screening import observation_revision
    from verification.ingestion_storage.retained_world import retained,identities,v3_items,item
    reset(world)
    _,receipt=retained()
    root,v1,_,_,_=identities(receipt)
    _,_,v3=v3_items(receipt,RULE)
    root.update(state='COMPLETE',phase='FINISHED',checkpoint=receipt,
                outcome=dict(outcome='ENUMERATED_METADATA_RETAINED',
                             source_sha256=receipt['source_sha256']))
    rows=[root];legacy_rule=ScreeningRule(RULE_V1);first=None
    for record,old,unbound in zip(receipt['records'],v1,v3):
        legacy=legacy_rule.screen(record);prior=RULE.screen(record)
        old.update(state='COMPLETE',phase='FINISHED',checkpoint=legacy,
                   outcome=dict(outcome=legacy['disposition']))
        unbound.update(state='COMPLETE',phase='FINISHED',checkpoint=prior,
                       outcome=dict(outcome=prior['count_assessment']['admission']))
        record_sha,config,config_sha,base=assessment_identity(record,RULE)
        revision=observation_revision(base,digest(receipt))
        checked=dict(prior,record_sha256=record_sha,config=config,
                     config_sha256=config_sha,capture_bound=True,
                     capture_checkpoint_sha256=digest(receipt),
                     assessment_revision=revision,
                     source_sha256=receipt['source_sha256'])
        bound=item(dict(subject=old['subject'],task='SCREENING',
                        contract='listing-screen-v3',revision=revision),
                   dependencies=[root['key']])
        bound.update(state='COMPLETE',phase='FINISHED',checkpoint=checked,
                     outcome=dict(outcome=prior['count_assessment']['admission']))
        if first is None:first=bound
        rows.extend((old,unbound,bound))
    assert len(rows)==73
    for row in rows:
        world['boot'].execute(
            'INSERT INTO ingestion_work_items SELECT * FROM '
            'json_populate_record(NULL::ingestion_work_items,%s::json)',
            (json.dumps(row),))
    reader=SimpleNamespace(_limits=lambda _conn:None)
    def read(conn):
        return backlog_page(reader,['bolton'],[root['contract']],RULE,connection=conn)
    with world['app'].connect() as conn:
        result=read(conn);conn.rollback()
    assert len(result['records'])==24 and len(result['captures'])==1
    assert len({r['reference'] for r in result['records']})==24
    assert all(r['historical_screening_items']==3
               and r['screening_state']=='COMPLETE'
               and r['screening_matches_current_rule'] is True
               and r['application_admitted'] is None
               and r['extraction_complete'] is None for r in result['records'])
    assert result['coverage_advance'] is False
    assert result['extraction_consumer_connected'] is False
    assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0
    assert world['boot'].execute(
        "SELECT count(*) FROM ingestion_work_items WHERE task='SCREENING'").fetchone()[0]==72
    conflicting=item(dict(subject=first['subject'],task='SCREENING',
                          contract='listing-screen-v3',revision='contradictory-bound-v3'),
                     dependencies=[root['key']])
    conflicting.update(state='COMPLETE',phase='FINISHED',
                       checkpoint=first['checkpoint'],outcome=first['outcome'])
    with world['app'].connect() as conn:
        tx=conn.begin()
        try:
            conn.execute(text('INSERT INTO ingestion_work_items SELECT * FROM '
                'json_populate_record(NULL::ingestion_work_items,CAST(:payload AS json))'),
                dict(payload=json.dumps(conflicting)))
            with pytest.raises(Denied,match='BACKLOG_MULTIPLE_ASSESSMENTS'):read(conn)
        finally:tx.rollback()
    with world['app'].connect() as conn:
        tx=conn.begin()
        try:
            conn.execute(text(
                "UPDATE ingestion_work_items SET checkpoint="
                "jsonb_set(checkpoint::jsonb,'{source_sha256}',"
                "to_jsonb(repeat('0',64)))::json WHERE key=:key"),
                dict(key=first['key']))
            with pytest.raises(Denied,match='BACKLOG_SCREENING_PROVENANCE'):read(conn)
        finally:tx.rollback()
    assert world['boot'].execute(
        "SELECT count(*) FROM ingestion_work_items WHERE task='SCREENING'").fetchone()[0]==72


@pytest.mark.parametrize('stop_field,stop_value', [
    ('global_stop', {'reason': 'BOLTON_SOURCE_EFFECT_UNKNOWN', 'run': 'test-only-bolton'}),
    ('manual_stop', 'BOLTON_SOURCE_EFFECT_UNKNOWN'),
])
def test_tameside_period_cannot_bypass_unrelated_shared_stop(world, stop_field, stop_value):
    """First-batch safety: matching a stopped snapshot cannot isolate a council.

    The test modifies only disposable PostgreSQL fixture control. No council
    request, live stop clearance, production grant or recovery is exercised.
    """
    reset(world)
    control = copy.deepcopy(world['boot'].execute(
        "SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)"
    ).fetchone()[0])
    control[stop_field] = stop_value
    world['boot'].execute(
        "UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",
        (json.dumps(control),),
    )
    before = snapshot(world['boot'])
    candidate = policy(world)
    assert candidate['expected_stop'][stop_field] == stop_value
    with pytest.raises(Exception, match='ADMIN_EFFECT_UNCERTAIN'):
        authorise(world, 'tameside-only-after-bolton-'+stop_field, candidate)
    assert snapshot(world['boot']) == before
    assert restricted_sessions(world['boot']) == 0


def test_unresolved_bolton_source_intent_blocks_new_tameside_period(world):
    """A clear stop snapshot cannot make another council's uncertain effect safe.

    The Bolton row is a disposable database fixture, not the historical run:
    no source is contacted and this does not settle or clear real stops.
    """
    from verification.ingestion_storage.operational_owner import item
    from app.ingestion.ledger import DEFAULT_LIMITS
    reset(world)
    identity = dict(subject=dict(kind='DISCOVERY_SCOPE', council='bolton',
                                 start='2026-11-03', end='2026-11-05',
                                 semantics='RECEIVED'), task='DISCOVERY',
                    contract='bolton-test-only', revision='unresolved-intent')
    orphan = item(identity, limits=dict(DEFAULT_LIMITS))
    orphan.update(state='CLAIMED', phase='SOURCE_INTENT', fence=1,
                  attempt_count=1, owner='dead-fixture-worker', lease_until=0)
    world['boot'].execute(
        'INSERT INTO ingestion_work_items SELECT * FROM json_populate_record('
        'NULL::ingestion_work_items,%s::json)', (json.dumps(orphan),),
    )
    candidate = policy(world)
    assert candidate['expected_stop']['global_stop'] is None
    assert candidate['expected_stop']['manual_stop'] is None
    before = snapshot(world['boot'])
    with pytest.raises(Exception, match='ADMIN_EFFECT_UNCERTAIN'):
        authorise(world, 'tameside-after-unresolved-bolton', candidate)
    assert snapshot(world['boot']) == before
    assert restricted_sessions(world['boot']) == 0


def test_factual_backlog_distinguishes_blocked_uncertain_and_deferred_work_from_pending():
    """S4-03: an unresolved owner task is not an executable pending admission."""
    from app.ingestion.ledger import Denied
    from verification.ingestion_storage.v3_admission import readback_committed_v3_facts_page

    names = ('QUEUED', 'DEFERRED', 'CLAIMED', 'UNSUPPORTED_CONTRACT',
             'SAFETY_BLOCKED', 'PERSISTENCE_UNCERTAIN')
    keys = [f'{n:064x}' for n in range(1, 7)]
    rows = [(key, dict(kind='APPLICATION', council='tameside',
                       reference=f'TAM/26/{i}'), state)
            for i, (key, state) in enumerate(zip(keys, names), 1)]

    class Cursor:
        def __init__(self, result): self.result = result
        def fetchall(self): return self.result

    class Reader:
        def __init__(self, result): self.result = result
        def execute(self, sql, params):
            assert "task='FACTUAL_REFRESH'" in sql
            assert params == ('tameside', '', 11)
            return Cursor(self.result)

    result = readback_committed_v3_facts_page(
        Reader(rows), object(), council='tameside', limit=10)
    assert [x['state'] for x in result['records']] == [
        'FACTUAL_TASK_NOT_VERIFIED', 'FACTUAL_TASK_DEFERRED',
        'FACTUAL_TASK_CLAIM_UNVERIFIED', 'FACTUAL_TASK_BLOCKED',
        'FACTUAL_TASK_BLOCKED', 'FACTUAL_TASK_UNCERTAIN']
    assert 'work_state' not in result['records'][0]
    assert [x['work_state'] for x in result['records'][1:]] == list(names[1:])
    assert all(x['saved_key_facts'] is None for x in result['records'])
    assert result['buyer_opportunities_proven'] is False
    assert result['source_coverage'] == 'UNKNOWN'
    assert result['more'] is False and result['next_cursor'] is None
    # No invented/novel ledger state can silently become "pending".
    with pytest.raises(Denied, match='FACT_BACKLOG_WORK_STATE'):
        readback_committed_v3_facts_page(
            Reader([(keys[0], rows[0][1], 'INVENTED_STATE')]),
            object(), council='tameside', limit=10)


def test_disposable_daily_capture_owner_fenced_admission_and_independent_fact_readback(world,tmp_path):
    """S4-03 offline: the actual daily command's saved screen can feed a DIFFERENT owner.

    The live collector remains screening-only. Only the disposable bootstrap
    inserts the separately prepared owner grant/fact item; production has no
    such Tameside issuer. The accepted factual projector, restricted roles,
    ledger and Application writer do the real disposable execution/readback.
    """
    from dataclasses import replace
    from app.config import get_council
    from app.ingestion.coordinator import Coordinator
    from app.ingestion.listing_screening import V3_CONTRACT,code_binding
    from app.ingestion.nomination import derive_nominees
    from app.pipeline.discovery_contract import DiscoveryEnvelope,WindowEvidence
    from tests.e2e_connection_support import idox_contract,idox_detail_target,idox_detail,outer
    from verification.direct_reference.fixtures import summary
    from verification.ingestion_storage.chain_caller import WORKER
    from verification.ingestion_storage.chain_registration import (
        persisted_council_capture_inventory,prepare_admission_from_persisted_captures)
    from verification.ingestion_storage.operational_controller import (
        AcceptanceBinding,ControllerLedger,DatabaseBudget)
    from verification.ingestion_storage.scope_binding import binding_for
    from verification.ingestion_storage.v3_admission import (
        V3AdmissionBinding,execute_retained_v3,factual_binding,readback_committed_v3_facts,
        readback_committed_v3_facts_page)

    reset(world)
    name='daily-separate-factual-owner'
    authorise(world,name)
    run,result,_=invoke(world,tmp_path,name)
    assert run.returncode==0 and result['status']=='RETAINED_AND_SCREENED',(run.stderr,result)
    assert result['admission_connected'] is False and result['coverage_advance'] is False
    assert world['boot'].execute("SELECT count(*) FROM applications").fetchone()[0]==0
    assert world['boot'].execute("SELECT count(*) FROM ingestion_work_items WHERE task='FACTUAL_REFRESH'").fetchone()[0]==0

    roots=persisted_council_capture_inventory(world['boot'],'tameside')
    assert len(roots)==1
    root=roots[0];receipt=root['checkpoint'];record=receipt['records'][0]
    nomination=derive_nominees([receipt],RULE,allow_test_evidence=True,capture_bound=True)
    assert len(nomination.nominees)==1
    nominee=nomination.nominees[0]
    assert nominee.reference==record['reference']
    target=idox_detail_target('tameside',record,case='chain_idox_tameside_'+digest(record))
    contract=idox_contract('tameside',date.fromisoformat(root['subject']['start']),
                           date.fromisoformat(root['subject']['end']),name=root['contract'])
    owner=Owner(None,lambda *_:None,lambda:None,
                expiry=datetime.now(timezone.utc)+timedelta(minutes=25),
                bindings=execution_binding())
    registration,saved_nominees=prepare_admission_from_persisted_captures(
        world['boot'],owner,binding_for('tameside'),contract,root['key'],
        RULE,{nominee.reference:target},revision='disposable-separate-owner-facts',
        item_limits=root['limits'],allow_test_evidence=True)
    assert registration.kind=='ADMISSION' and len(registration.insert)==1
    assert saved_nominees.sha256==nomination.sha256
    assert registration.grant['writes']==2 and registration.grant['source_calls']==1
    assert registration.grant['detail_source_keys']==[registration.facts[nominee.reference]['key']]
    assert world['boot'].execute("SELECT count(*) FROM ingestion_work_items WHERE task='FACTUAL_REFRESH'").fetchone()[0]==0

    # The production owner registration policy has no live Tameside admission
    # exception. This ONE disposable fixture simulates only its insertion:
    # it does not change the daily runtime, its expired grant, or SQL privileges.
    control=world['boot'].execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
    assert control['global_stop'] is None and control['manual_stop'] is None
    assert registration.authority not in control['grants']
    assert all(g['expires_at']==0 for g in control['grants'].values())
    control['grants'][registration.authority]=registration.grant
    for row in registration.insert:
        world['boot'].execute(
            'INSERT INTO ingestion_work_items SELECT * FROM json_populate_record(NULL::ingestion_work_items,%s::json)',
            (json.dumps(row),))
    world['boot'].execute(
        "UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(control),))

    # The owner-only page must show a registered FACTUAL_REFRESH as pending,
    # NOT as saved facts or a buyer opportunity before factual execution.
    pending_page=readback_committed_v3_facts_page(
        world['boot'],world['app'],council='tameside')
    assert pending_page['records']==[dict(
        council='tameside',reference=nominee.reference,
        factual_key=registration.facts[nominee.reference]['key'],
        state='FACTUAL_TASK_NOT_VERIFIED',saved_key_facts=None)]
    assert pending_page['more'] is False and pending_page['next_cursor'] is None
    assert pending_page['source_coverage']=='UNKNOWN'
    assert pending_page['buyer_opportunities_proven'] is False

    worker_url=world['urls']['ingestion_worker_login']
    effect_url=world['urls']['ingestion_effect_login']
    application_url=world['urls']['ingestion_application_login']
    def controller(budget):
        worker=budget.engine(worker_url)
        broker=budget.engine(effect_url)
        application=budget.engine(application_url)
        ledger=ControllerLedger(
            worker,budget=budget,owner=WORKER,authority=registration.authority,
            bindings=registration.bindings,broker_engine=broker,application_engine=application)
        fact_contract=registration.factual_contracts[nominee.reference]
        return Coordinator(ledger,{contract.name:contract,fact_contract.name:fact_contract},
                           screening_rules={V3_CONTRACT:RULE},capture_bound_screening=True)

    first=DatabaseBudget()
    try:
        independently_saved=controller(first).ledger.get(root['key'])['checkpoint']
        assert independently_saved==receipt
        first.capture_checkpoint_sha256=digest(independently_saved)
    finally:
        prior=first.close([])
    budget=DatabaseBudget(previous=prior)
    coordinator=controller(budget)
    fact=registration.facts[nominee.reference]
    screen=registration.screens[nominee.reference]
    batch=registration.batches[0]
    fc=registration.factual_contracts[nominee.reference]
    nominated=AcceptanceBinding(
        root['key'],screen['key'],fact['key'],record['reference'],record['source_url'],
        record['source_record_id'],digest(record),digest(receipt),digest(prior),batch['key'])
    binding=V3AdmissionBinding(
        nominated,'tameside',contract.name,root['revision'],digest(RULE.config()),
        digest(code_binding()),fc.name,fact['revision'],factual_binding(fc))
    start=date.fromisoformat(root['subject']['start'])
    end=date.fromisoformat(root['subject']['end'])
    placeholder=WindowEvidence('tameside','offline',start,end,start,end,'RECEIVED',
                               'disposable','date-labels','terminal-count',1,1,2,2000,1)
    envelope=DiscoveryEnvelope(
        'tameside',nominee.reference,record['source_url'],record['source_record_id'],
        datetime.now(timezone.utc),placeholder,(nominee.reference,),'a'*64,())
    calls=[]
    def detail(_):
        calls.append(nominee.reference)
        return idox_detail(target,summary(nominee.reference,status='Decided',
                                          decision='Approve',date='Mon 28 Sep 2026')),outer()
    try:
        with pytest.raises(Denied,match='V3_CONFIGURATION_OR_CAPTURE_BINDING'):
            execute_retained_v3(
                coordinator,replace(binding,screening_config_sha256='0'*64),
                detail_reader=detail,envelope=envelope,council=get_council('tameside'),
                check=budget.check,allow_test_evidence=True)
        assert calls==[]
        assert world['boot'].execute("SELECT count(*) FROM applications").fetchone()[0]==0
        result=execute_retained_v3(
            coordinator,binding,detail_reader=detail,envelope=envelope,
            council=get_council('tameside'),check=budget.check,allow_test_evidence=True)
        assert result['outcome']=='SUPPORTED_FACTS_VERIFIED'
        assert calls==[nominee.reference]
        # The disposable provisioning migrator intentionally has NO table
        # SELECT. Independently verify through the fixture's pre-existing
        # bootstrap read connection, separate from every restricted writer;
        # never expand migrator/worker privileges for a readback test.
        assert world['boot'].info.user=='provisioning_bootstrap'
        # Default owner reads refuse test-labelled evidence, even where an
        # isolated fixture has committed an authentic B2-shaped database row.
        with pytest.raises(Denied,match='FACT_READBACK_TEST_EVIDENCE'):
            readback_committed_v3_facts(
                world['boot'],world['app'],fact['key'],council='tameside',
                reference=nominee.reference)
        with pytest.raises(Denied,match='FACT_READBACK_TEST_EVIDENCE'):
            readback_committed_v3_facts_page(world['boot'],world['app'],council='tameside')
        proof=readback_committed_v3_facts(
            world['boot'],world['app'],fact['key'],council='tameside',
            reference=nominee.reference,allow_test_evidence=True)
        assert proof['state']=='COMMITTED_B2_FACTS_READ_BACK'
        assert proof['verification_scope']=='COUPLED'
        assert proof['saved_key_facts']['status']=='Decided'
        assert proof['saved_key_facts']['decision']=='Approve'
        assert proof['unit_count_verified'] is False
        assert proof['buyer_opportunity_qualified'] is False
        assert proof['source_completeness']=='UNKNOWN'
        # Discover committed facts without knowing their task key.
        # The page independently revalidates capture, screening and B2;
        # neither readback certifies a qualified buyer site.
        saved_page=readback_committed_v3_facts_page(
            world['boot'],world['app'],council='tameside',allow_test_evidence=True)
        assert saved_page['records']==[proof]
        assert saved_page['more'] is False and saved_page['next_cursor'] is None
        assert saved_page['source_coverage']=='UNKNOWN'
        assert saved_page['unit_counts_verified'] is False
        assert saved_page['buyer_opportunities_proven'] is False
        assert world['boot'].execute(
            "SELECT count(*) FROM applications WHERE council_code='tameside' AND reference=%s",
            (nominee.reference,)).fetchone()[0]==1
        assert world['boot'].execute(
            "SELECT count(*) FROM applications WHERE site_id IS NOT NULL OR estimated_unit_count IS NOT NULL "
            "OR opportunity_classification IS NOT NULL").fetchone()[0]==0
    finally:
        costs=budget.close([])
        assert costs['cleanup']=='CLOSED' and costs['connections_opened']==costs['connections_closed_count']
        # Module-scoped disposable fixture must leave no Application for other
        # daily-intake scenarios; this cleanup touches only disposable PG17.
        world['boot'].execute('TRUNCATE applications CASCADE')


# S4-04: DISPOSABLE ONLY proof of a generation-bound successor AFTER the distinct
# Bolton settlement. This does not install a live clearance path or authorise a
# source request. A real independent release review is still mandatory.
_RECOVERY_KEY='d9d8d667eef5fb012c74cdd28f5c55c6b577f749e7dc69d9179a6c032853d252'
_RECOVERY_RUN='ee7cf0d9bc714f56951527b940937054'
_RECOVERY_PERIOD='b-bolton-20261103-1105-01'



def _historical_salford_seed():
    """Reuse the original immutable audited migration row, never a mock subset."""
    source=(Path(__file__).resolve().parents[1] /
            'docs/design/ingestion-readiness-20261016/migration.sql').read_text()
    marker='"key":"c1f526eed20e392382001cad4d28eb5bc16e5d1c0f92adb282fe7b1cc775f3f3"'
    location=source.index(marker)
    start=source.rindex("expected := '",0,location)+len("expected := '")
    finish=source.index("'::jsonb;",location)
    seed=json.loads(source[start:finish])
    assert seed['key']=='c1f526eed20e392382001cad4d28eb5bc16e5d1c0f92adb282fe7b1cc775f3f3'
    assert seed['state']=='SAFETY_BLOCKED' and seed['phase']=='IDLE'
    assert seed['authority'] is None and seed['attempt_count']==0
    assert seed['checkpoint']['live_allowance']==dict(source_calls=0,writes=0)
    return seed


def _settled_fixture(world):
    from verification.ingestion_storage.operational_owner import item
    reset(world)
    scope=dict(kind='DISCOVERY_SCOPE',council='bolton',semantics='RECEIVED',
               start='2026-11-03',end='2026-11-05')
    identity=dict(subject=scope,task='DISCOVERY',contract='bolton-received-intake-v1',
                  revision=_RECOVERY_PERIOD+'-2026-11-05-bolton')
    root=item(identity)
    assert root['key']==_RECOVERY_KEY
    root.update(state='SAFETY_BLOCKED',phase='RECOVERED',fence=2,attempt_count=1,
                owner=None,lease_until=None,checkpoint=None,reason='ABANDONED_SOURCE_INTENT',
                next_action='RECONCILE',
                outcome=dict(outcome='ABANDONED_SOURCE_INTENT',source_or_write_replay_authorised=False))
    c=world['boot']
    c.execute('INSERT INTO public.ingestion_work_items SELECT * FROM json_populate_record(NULL::public.ingestion_work_items,%s::json)',
              (json.dumps(root),))
    c.execute("""INSERT INTO public.ingestion_work_attempts
      (work_key,fence,owner,started_at,finished_at,authority,phase,outcome,checkpoint)
      VALUES (%s,1,'required_once',0,100,'INGESTION_CHAIN_BOLTON_CAPTURE_34518B29848D','RECOVERED',NULL,NULL)""",
              (_RECOVERY_KEY,))
    ctl=copy.deepcopy(world['control'])
    ctl.update(global_stop=dict(reason='DAILY_INTAKE_SHARED_FAILURE'),
               manual_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',
               last_hard_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',hard_stop_generation=15,
               grants={})
    ctl.pop('intake_run',None)
    # Exact seed from the reviewed 16 Oct migration; preserve this
    # historical audit marker unchanged during every recovery test.
    salford=_historical_salford_seed()
    c.execute('INSERT INTO public.ingestion_work_items SELECT * FROM '
              'json_populate_record(NULL::public.ingestion_work_items,%s::json)',
              (json.dumps(salford),))
    marker=dict(id=_RECOVERY_RUN,period=_RECOVERY_PERIOD,state='OPEN')
    receipt=dict(version='BOLTON01_FAILED_RECOVERY_V1',status='FAILED_RECONCILED',
                 coverage='UNKNOWN',period=_RECOVERY_PERIOD,run_id=_RECOVERY_RUN,
                 original_marker=marker,recovered_key=_RECOVERY_KEY,recovered_fence=2,
                 source_or_write_replay_authorised=False,stop_after=stop_snapshot(ctl))
    ctl['intake_periods']={_RECOVERY_PERIOD:dict(expires_at=0,failed_runs={_RECOVERY_RUN:receipt})}
    c.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",
              (json.dumps(ctl),))
    return ctl


def _disposable_release(world,payload,*,rollback=False):
    # Mimics the existing owner period issuer's TRANSACTIONAL temporary role.
    with world['connect']('provisioning_migrator') as c:
        c.execute('BEGIN')
        try:
            c.execute('GRANT ingestion_barrier_releaser TO CURRENT_USER WITH INHERIT TRUE, SET TRUE')
            result=c.execute('SELECT public.ingestion_disposable_shared_stop_release(%s::jsonb)',
                             (json.dumps(payload),)).fetchone()[0]
            c.execute('REVOKE ingestion_barrier_releaser FROM CURRENT_USER GRANTED BY CURRENT_USER')
            c.execute('ROLLBACK' if rollback else 'COMMIT')
            return result
        except BaseException:
            c.execute('ROLLBACK')
            raise


def _recovery_control(world):
    return world['boot'].execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]


def test_shared_stop_successor_is_disposable_only_and_has_no_live_issuer():
    normal=intake_policy.policy_sql()
    test_sql=intake_policy.policy_sql(disposable_catchup=True)
    assert 'ingestion_disposable_shared_stop_release' not in normal
    assert 'ingestion_disposable_shared_stop_release' in test_sql
    assert 'current_database() IS DISTINCT FROM' in test_sql


def test_shared_stop_recovery_exact_settlement_rollback_and_period_registration(world):
    ctl=_settled_fixture(world)
    payload=dict(operation='S4_DISPOSABLE_BOLTON_STOP_RELEASE_V1',
                 expected_stop=stop_snapshot(ctl))
    assert _disposable_release(world,payload,rollback=True)['no_work_issued'] is True
    assert _recovery_control(world)==ctl
    result=_disposable_release(world,payload)
    assert result==dict(status='DISPOSABLE_ONLY_STOP_RELEASED',hard_stop_generation=16,
                        work_key=_RECOVERY_KEY,no_work_issued=True)
    after=_recovery_control(world)
    assert after['global_stop'] is None and after['manual_stop'] is None
    assert after['hard_stop_generation']==16
    assert after['last_hard_stop']=='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP'
    assert after['intake_periods']==ctl['intake_periods']
    assert after['disposable_shared_stop_release']['test_only'] is True
    assert world['boot'].execute("SELECT state,phase,fence,checkpoint FROM ingestion_work_items WHERE key=%s",
                                 (_RECOVERY_KEY,)).fetchone()==('SAFETY_BLOCKED','RECOVERED',2,None)
    with pytest.raises(Exception,match='DISPOSABLE_STOP_GENERATION_OR_MARKER'):
        _disposable_release(world,payload)
    assert _recovery_control(world)==after
    # A separate existing period-registration operation is possible ONLY after
    # the test release, with a newly bound exact current generation-16 snapshot.
    registered=authorise(world,'after-test-stop-recovery')
    assert registered['expected_stop']['hard_stop_generation']==16
    assert _recovery_control(world)['global_stop'] is None


@pytest.mark.parametrize('drift',[
    'unsettled_generation','wrong_stop','missing_receipt','false_coverage',
    'open_run','active_claim','unrecovered_attempt','other_grant',
    'other_active_period','bad_expected_snapshot'
])
def test_shared_stop_recovery_refuses_unresolved_effects_atomically(world,drift):
    ctl=_settled_fixture(world)
    c=world['boot']
    payload=dict(operation='S4_DISPOSABLE_BOLTON_STOP_RELEASE_V1',
                 expected_stop=stop_snapshot(ctl))
    if drift=='unsettled_generation':
        ctl['hard_stop_generation']=14
    elif drift=='wrong_stop':
        ctl['manual_stop']='DAILY_INTAKE_SHARED_FAILURE'
    elif drift=='missing_receipt':
        ctl['intake_periods'][_RECOVERY_PERIOD]['failed_runs']={}
    elif drift=='false_coverage':
        ctl['intake_periods'][_RECOVERY_PERIOD]['failed_runs'][_RECOVERY_RUN]['coverage']='COMPLETE'
    elif drift=='open_run':
        ctl['intake_run']=dict(state='OPEN',id=_RECOVERY_RUN)
    elif drift=='active_claim':
        c.execute("UPDATE ingestion_work_items SET state='CLAIMED',phase='SOURCE_INTENT' WHERE key=%s",(_RECOVERY_KEY,))
    elif drift=='unrecovered_attempt':
        c.execute("UPDATE ingestion_work_attempts SET phase='SOURCE_INTENT' WHERE work_key=%s",(_RECOVERY_KEY,))
    elif drift=='other_grant':
        ctl['grants']={'other':dict(expires_at=time.time()+3600)}
    elif drift=='other_active_period':
        ctl['intake_periods']['other']=dict(expires_at=time.time()+3600)
    elif drift=='bad_expected_snapshot':
        payload['expected_stop']['hard_stop_generation']=11
    c.execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",
              (json.dumps(ctl),))
    before=_recovery_control(world)
    with pytest.raises(Exception,match='DISPOSABLE_'):
        _disposable_release(world,payload)
    assert _recovery_control(world)==before


@pytest.mark.parametrize('number_of_other_intents',[6,7])
def test_shared_stop_recovery_refuses_other_abandoned_source_intents_without_disposition(
        world,number_of_other_intents):
    # Synthetic analogue of the six historical Bolton/Manchester/Tameside
    # effect markers. The seventh marker proves no fixed-count bypass exists.
    from verification.ingestion_storage.operational_owner import item
    ctl=_settled_fixture(world)
    c=world['boot']
    other_keys=[]
    councils=('bolton','bolton','manchester','manchester','tameside','tameside','rochdale')
    for i,council in enumerate(councils[:number_of_other_intents]):
        scope=dict(kind='DISCOVERY_SCOPE',council=council,semantics='RECEIVED',
                   start='2026-09-15',end=f'2026-09-{16+i:02d}')
        identity=dict(subject=scope,task='DISCOVERY',contract='synthetic-abandoned-v1',
                      revision=f'disposable-unresolved-{i}')
        row=item(identity)
        row.update(state='SAFETY_BLOCKED',phase='RECOVERED',fence=2,attempt_count=1,
                   owner=None,lease_until=None,checkpoint=None,
                   reason='ABANDONED_SOURCE_INTENT',next_action='RECONCILE',
                   outcome=dict(outcome='ABANDONED_SOURCE_INTENT',
                                source_or_write_replay_authorised=False))
        other_keys.append(row['key'])
        c.execute('INSERT INTO public.ingestion_work_items SELECT * FROM '
                  'json_populate_record(NULL::public.ingestion_work_items,%s::json)',
                  (json.dumps(row),))
        c.execute("""INSERT INTO public.ingestion_work_attempts
          (work_key,fence,owner,started_at,finished_at,authority,phase,outcome,checkpoint)
          VALUES (%s,1,'required_once',0,100,'SYNTHETIC_NO_LIVE_AUTHORITY',
                  'RECOVERED',NULL,NULL)""",(row['key'],))
    before=_recovery_control(world)
    assert before==ctl
    assert c.execute("SELECT count(*) FROM ingestion_work_items WHERE key=ANY(%s)",
                     (other_keys,)).fetchone()[0]==number_of_other_intents
    payload=dict(operation='S4_DISPOSABLE_BOLTON_STOP_RELEASE_V1',
                 expected_stop=stop_snapshot(ctl))
    with pytest.raises(Exception,match='DISPOSABLE_OUTSTANDING_EFFECT_OR_AUTHORITY'):
        _disposable_release(world,payload)
    # The failed SQL call rolls back, retaining all original markers/attempts
    # and both hard stops; expiration or mere RECOVERED state is not clearance.
    assert _recovery_control(world)==before
    assert c.execute("SELECT count(*) FROM ingestion_work_items WHERE key=ANY(%s) "
                     "AND state='SAFETY_BLOCKED' AND phase='RECOVERED' "
                     "AND reason='ABANDONED_SOURCE_INTENT' AND next_action='RECONCILE'",
                     (other_keys,)).fetchone()[0]==number_of_other_intents
    assert c.execute("SELECT count(*) FROM ingestion_work_attempts "
                     "WHERE work_key=ANY(%s) AND phase='RECOVERED'",
                     (other_keys,)).fetchone()[0]==number_of_other_intents


@pytest.mark.parametrize('hidden',['unsettled_attempt','unfinished_attempt','relabelled_abandoned'])
def test_shared_stop_disposable_release_refuses_hidden_historical_effects(world, hidden):
    """Full SQL refusal despite a terminal-looking OTHER work row.

    A future reviewed disposition needs independent attempt and source-effect
    evidence. This fixture does not endorse any real historical disposal.
    """
    from verification.ingestion_storage.operational_owner import item
    ctl=_settled_fixture(world)
    c=world['boot']
    identity=dict(subject=dict(kind='DISCOVERY_SCOPE',council='manchester',
                               semantics='VALIDATED',start='2026-10-27',
                               end='2026-11-02'),task='DISCOVERY',
                  contract='offline-hidden-effect-v1',revision='unreviewed')
    row=item(identity)
    row.update(state='DEFERRED',phase='FINISHED',fence=2,attempt_count=1,
               owner=None,lease_until=None,checkpoint=None,
               reason='HISTORICAL_REVIEW_NOT_PROVEN',next_action='REVIEW_ONLY',
               outcome=dict(outcome='ABANDONED_SOURCE_INTENT'
                            if hidden=='relabelled_abandoned' else
                            'SYNTHETIC_NOT_DISPOSED',
                            source_or_write_replay_authorised=False))
    c.execute('INSERT INTO public.ingestion_work_items SELECT * FROM '
              'json_populate_record(NULL::public.ingestion_work_items,%s::json)',
              (json.dumps(row),))
    phase=('SOURCE_INTENT' if hidden=='unsettled_attempt' else 'FINISHED')
    finished=(None if hidden=='unfinished_attempt' else 100)
    c.execute("""INSERT INTO public.ingestion_work_attempts
      (work_key,fence,owner,started_at,finished_at,authority,phase,outcome,checkpoint)
      VALUES (%s,1,'required_once',0,%s,'SYNTHETIC_NO_LIVE_AUTHORITY',%s,NULL,NULL)""",
      (row['key'],finished,phase))
    before=_recovery_control(world)
    assert before==ctl
    payload=dict(operation='S4_DISPOSABLE_BOLTON_STOP_RELEASE_V1',
                 expected_stop=stop_snapshot(ctl))
    with pytest.raises(Exception,match='DISPOSABLE_OUTSTANDING_EFFECT_OR_AUTHORITY'):
        _disposable_release(world,payload)
    assert _recovery_control(world)==before
    assert c.execute('SELECT state,phase FROM public.ingestion_work_items WHERE key=%s',
                     (row['key'],)).fetchone()==('DEFERRED','FINISHED')
    assert c.execute('SELECT phase,finished_at FROM public.ingestion_work_attempts WHERE work_key=%s',
                     (row['key'],)).fetchone()[0]==phase


def test_shared_stop_worker_cannot_call_owner_recovery(world):
    import psycopg
    ctl=_settled_fixture(world)
    payload=dict(operation='S4_DISPOSABLE_BOLTON_STOP_RELEASE_V1',
                 expected_stop=stop_snapshot(ctl))
    with world['connect']('ingestion_worker_login') as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute('SELECT public.ingestion_disposable_shared_stop_release(%s::jsonb)',
                      (json.dumps(payload),))
    assert _recovery_control(world)==ctl


@pytest.mark.parametrize('drift',[
    'salford_absent','salford_checkpoint_changed',
    'salford_authority_changed','salford_attempt_created',
])
def test_shared_stop_release_requires_exact_preserved_salford_audit(world,drift):
    """No changed/missing historical audit marker may become an implicit bypass."""
    ctl=_settled_fixture(world)
    key=_historical_salford_seed()['key']
    c=world['boot']
    before=copy.deepcopy(ctl)
    if drift=='salford_absent':
        c.execute("DELETE FROM public.ingestion_work_items WHERE key=%s",(key,))
    elif drift=='salford_checkpoint_changed':
        c.execute("UPDATE public.ingestion_work_items SET checkpoint = "
                  "jsonb_set(checkpoint::jsonb,'{live_allowance,source_calls}','1'::jsonb)::json "
                  "WHERE key=%s",(key,))
    elif drift=='salford_authority_changed':
        c.execute("UPDATE public.ingestion_work_items SET authority='FORGED_REPLAY' WHERE key=%s",(key,))
    else:
        c.execute("""INSERT INTO public.ingestion_work_attempts
          (work_key,fence,owner,started_at,finished_at,authority,phase,outcome,checkpoint)
          VALUES (%s,1,'forged-fixture',0,1,'FORGED_REPLAY','RECOVERED',NULL,NULL)""",(key,))
    payload=dict(operation='S4_DISPOSABLE_BOLTON_STOP_RELEASE_V1',
                 expected_stop=stop_snapshot(ctl))
    with pytest.raises(Exception,match='DISPOSABLE_OUTSTANDING_EFFECT_OR_AUTHORITY'):
        _disposable_release(world,payload)
    assert _recovery_control(world)==before
    # Neither refusal nor rollback rewrites the altered source fixture.
    assert c.execute("SELECT count(*) FROM public.ingestion_work_items WHERE key=%s",(key,)).fetchone()[0]==(0 if drift=='salford_absent' else 1)


def test_shared_stop_release_preserves_exact_salford_after_rollback_and_success(world):
    """The independent historical classification has no source/replay authority."""
    ctl=_settled_fixture(world)
    key=_historical_salford_seed()['key']
    c=world['boot']
    before=c.execute("SELECT to_jsonb(w) FROM public.ingestion_work_items w WHERE key=%s",(key,)).fetchone()[0]
    assert before==_historical_salford_seed()
    assert c.execute("SELECT count(*) FROM public.ingestion_work_attempts WHERE work_key=%s",(key,)).fetchone()[0]==0
    payload=dict(operation='S4_DISPOSABLE_BOLTON_STOP_RELEASE_V1',
                 expected_stop=stop_snapshot(ctl))
    _disposable_release(world,payload,rollback=True)
    assert _recovery_control(world)==ctl
    result=_disposable_release(world,payload)
    assert result['no_work_issued'] is True
    assert c.execute("SELECT to_jsonb(w) FROM public.ingestion_work_items w WHERE key=%s",(key,)).fetchone()[0]==before
    assert c.execute("SELECT count(*) FROM public.ingestion_work_attempts WHERE work_key=%s",(key,)).fetchone()[0]==0
