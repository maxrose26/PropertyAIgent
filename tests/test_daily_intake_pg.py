"""Connected synthetic collectors -> production restricted SQL -> visible backlog.

Only registration INSERTs are disposable owner stand-ins. Uses the existing real
reader/parser fixtures and source supervisors; no council/production contact.
"""
import json
import time
from datetime import datetime, timezone
import pytest
from app.ingestion.daily_intake import intake_slot, backlog
from app.ingestion.ledger import Denied
from tests.e2e_pg_world import disposable_world
from tests.e2e_chain_caller import Chain, snapshot, changed_tables, restricted_sessions
from tests.e2e_connection_support import entry, SCHEME
from verification.ingestion_storage.chain_registration import screening_registration


@pytest.fixture(scope='module')
def world():
    yield from disposable_world()


def setup_intake(world,tmp_path,family,tag,entries=None,*,reset=True):
    chain=Chain(world,tmp_path,family,tag,entries)
    if reset:chain.owner_reset()
    chain.owner_registers_capture()
    chain.caller.intake_only=True
    chain.caller.urls={r:u for r,u in chain.caller.urls.items() if r!='ingestion_application_login'}
    calls=[]
    def collect(_):
        calls.append(1)
        source,outer=chain.supervised_source()
        return source,dict(outer,observed_at=datetime.now(timezone.utc).isoformat())
    def prepare(receipt):
        reg=screening_registration(chain._owner(1800),chain.binding,chain.contract,dict(chain.root,checkpoint=receipt),receipt,
                                   chain.rule,revision=chain.revision,item_limits=chain.item_limits,allow_test_evidence=True)
        chain._install(reg)
        chain.chain_registration=reg
        return reg
    return chain,collect,prepare,calls


@pytest.mark.parametrize('family',['idox','arcus'])
def test_connected_capture_screen_backlog_duplicate_and_no_application_effects(world,tmp_path,family,record_property):
    chain,collect,prepare,calls=setup_intake(world,tmp_path,family,'daily-'+family)
    before=snapshot(world['boot'])
    result=intake_slot(chain.caller,chain.root['key'],collect,chain.publisher,prepare)
    assert len(result['records'])==6 and not result['coverage_advance']
    assert all(r['observed_at'] and r['capture_sha256'] and r['archive']['readback_verified'] for r in result['records'])
    assert {r['screening_outcome'] for r in result['records']}=={'ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT','ROUTE_COUNT_UNCONFIRMED',
                                                            'RETAIN_NOT_RESIDENTIAL_SUPPLY','RETAIN_BELOW_THRESHOLD','RETAIN_RELATED_TO_PARENT'}
    assert all(not r['application_admitted'] and not r['extraction_complete'] for r in result['records'])
    assert intake_slot(chain.caller,chain.root['key'],collect,chain.publisher,prepare)==result
    assert calls==[1] and len(chain.publisher.calls)==1
    assert changed_tables(before,snapshot(world['boot']))==[]
    assert restricted_sessions(world['boot'])==0
    assert 'ingestion_application_login' not in chain.caller.urls
    assert chain.caller.nominees().nominees  # retained inputs reach existing nomination, no admission
    with pytest.raises(Denied,match='INTAKE_NO_ADMISSION'):chain.caller.prepare(None)
    record_property('runtime_database',json.dumps(chain.caller.accounting,sort_keys=True))
    totals=dict(driver_statements=sum(b.statements for b in chain.caller.budgets),
                connection_attempts=sum(b.attempts for b in chain.caller.budgets),
                returned_data_value_bytes=sum(b.returned_bytes for b in chain.caller.budgets),
                elapsed_seconds=time.monotonic()-chain.caller.intake_started,
                all_connections_closed=all(c.closed for b in chain.caller.budgets for c in b.opened),
                delivered_records=len(result['records']),same_root_deliveries=2,source_invocations=len(calls))
    assert totals['driver_statements']<=1040 and totals['connection_attempts']<=40
    assert totals['returned_data_value_bytes']<=4*1024**2 and totals['elapsed_seconds']<300 and totals['all_connections_closed']
    record_property('intake_cumulative',json.dumps(totals,sort_keys=True))


def test_durable_capture_survives_screening_preparation_failure(world,tmp_path):
    chain,collect,prepare,calls=setup_intake(world,tmp_path,'idox','daily-preparation-failure')
    def unavailable(_):raise RuntimeError('SYNTHETIC_PREPARATION_UNAVAILABLE')
    with pytest.raises(RuntimeError):intake_slot(chain.caller,chain.root['key'],collect,chain.publisher,unavailable)
    held=backlog(chain.caller)
    assert all(r['processing_state']=='AWAITING_SCREENING' and r['screening_state']=='NOT_PREPARED' for r in held['records'])
    # Retry only the unattempted screening preparation, never the collection.
    result=intake_slot(chain.caller,chain.root['key'],collect,chain.publisher,prepare)
    assert calls==[1] and len(result['records'])==6


def test_attempted_screening_failure_is_visible_and_never_recollects(world,tmp_path,monkeypatch):
    chain,collect,prepare,calls=setup_intake(world,tmp_path,'idox','daily-screen-failure')
    from app.ingestion.coordinator import Coordinator
    def fail(*_):raise RuntimeError('SYNTHETIC_SCREENING_FAILURE')
    with monkeypatch.context() as m:
        m.setattr(Coordinator,'screening',fail)
        with pytest.raises(RuntimeError):intake_slot(chain.caller,chain.root['key'],collect,chain.publisher,prepare)
    result=backlog(chain.caller)
    assert any(t['state']=='CLAIMED' for t in result['tasks'])
    assert all(r['processing_state']=='AWAITING_SCREENING' for r in result['records'])
    with pytest.raises(Denied,match='RECOVERY_REQUIRES_RECONCILIATION'):
        intake_slot(chain.caller,chain.root['key'],collect,chain.publisher,prepare)
    assert calls==[1] and len(chain.publisher.calls)==1


def test_required_publication_failure_leaves_no_completed_capture(world,tmp_path):
    chain,collect,prepare,calls=setup_intake(world,tmp_path,'idox','daily-publish-failure')
    chain.publisher.mode='raises'
    with pytest.raises(OSError):intake_slot(chain.caller,chain.root['key'],collect,chain.publisher,prepare)
    row=chain.caller.read_intake_items([chain.root['key']])[0]
    assert row['checkpoint'] is None and row['state']!='COMPLETE'
    with pytest.raises(Denied,match='RECONCILE_NO_SOURCE_REPLAY'):
        intake_slot(chain.caller,chain.root['key'],collect,chain.publisher,prepare)
    assert calls==[1]


def test_changed_observations_have_distinct_assessment_identity(world,tmp_path):
    keys=[]
    for tag,proposal in [('first',SCHEME),('changed','Erection of 30 residential dwellings')]:
        chain,collect,prepare,_=setup_intake(world,tmp_path,'idox','daily-'+tag,[entry('E2E/1/26',proposal)],reset=tag=='first')
        row=intake_slot(chain.caller,chain.root['key'],collect,chain.publisher,prepare)['records'][0]
        keys.append((row['capture_key'],row['screening_key'],row['capture_sha256']))
    assert all(a!=b for a,b in zip(*keys))
    assert world['boot'].execute("SELECT count(*) FROM ingestion_work_items WHERE task='SCREENING'").fetchone()[0]==2


def test_unchanged_record_in_another_capture_exposes_existing_parent_binding_gap(world,tmp_path):
    """Document the exact blocker; do not hide it behind a fixture reset/rekey.

    The accepted v3 task identity binds record/config while its dependency binds
    one capture. A new capture of identical metadata collides with that dependency.
    Changing this SQL-backed identity requires a reviewed compatibility decision.
    """
    original=None
    for n in range(2):
        chain,collect,prepare,calls=setup_intake(world,tmp_path,'idox','daily-overlap-'+str(n),[entry('E2E/1/26',SCHEME)],reset=n==0)
        if n==0:
            original=intake_slot(chain.caller,chain.root['key'],collect,chain.publisher,prepare)
        else:
            with pytest.raises(Exception,match='CONFLICTING_DUPLICATE'):
                intake_slot(chain.caller,chain.root['key'],collect,chain.publisher,prepare)
            assert calls==[1] and chain.caller.read_capture()['records']
            assert world['boot'].execute("SELECT count(*) FROM ingestion_work_items WHERE task='SCREENING' AND state='COMPLETE'").fetchone()[0]==1
    assert original['records'][0]['screening_outcome']=='ADMIT_SCHEME'


def test_shared_stop_prevents_persistence_and_publication(world,tmp_path):
    chain,collect,prepare,calls=setup_intake(world,tmp_path,'idox','daily-stop')
    chain.owner_sets_stop()
    # Preflight reads alone do not confer source authority: the release collector
    # is still an unavailable prerequisite, never inferred from these reads.
    with pytest.raises(Exception):intake_slot(chain.caller,chain.root['key'],collect,chain.publisher,prepare)
    assert calls==[]
    assert chain.publisher.calls==[]
    assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0
