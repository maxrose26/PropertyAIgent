"""Connected synthetic collectors -> production restricted SQL -> visible backlog.

Only registration INSERTs are disposable owner stand-ins. Uses the existing real
reader/parser fixtures and source supervisors; no council/production contact.
"""
import json
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


def setup_intake(world,tmp_path,family,tag,entries=None):
    chain=Chain(world,tmp_path,family,tag,entries).owner_reset().owner_registers_capture()
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
    with pytest.raises(Denied,match='INTAKE_NO_ADMISSION'):chain.caller.prepare(None)
    record_property('runtime_database',json.dumps(chain.caller.accounting,sort_keys=True))


def test_durable_capture_survives_screening_preparation_failure(world,tmp_path):
    chain,collect,prepare,calls=setup_intake(world,tmp_path,'idox','daily-preparation-failure')
    def unavailable(_):raise RuntimeError('SYNTHETIC_PREPARATION_UNAVAILABLE')
    with pytest.raises(RuntimeError):intake_slot(chain.caller,chain.root['key'],collect,chain.publisher,unavailable)
    held=backlog(chain.caller)
    assert all(r['processing_state']=='AWAITING_SCREENING' and r['screening_state']=='NOT_PREPARED' for r in held['records'])
    # Retry only the unattempted screening preparation, never the collection.
    result=intake_slot(chain.caller,chain.root['key'],collect,chain.publisher,prepare)
    assert calls==[1] and len(result['records'])==6


def test_changed_observations_have_distinct_assessment_identity(world,tmp_path):
    keys=[]
    for tag,proposal in [('first',SCHEME),('changed','Erection of 30 residential dwellings')]:
        chain,collect,prepare,_=setup_intake(world,tmp_path,'idox','daily-'+tag,[entry('E2E/1/26',proposal)])
        row=intake_slot(chain.caller,chain.root['key'],collect,chain.publisher,prepare)['records'][0]
        keys.append((row['capture_key'],row['screening_key'],row['capture_sha256']))
    assert all(a!=b for a,b in zip(*keys))


def test_shared_stop_prevents_persistence_and_publication(world,tmp_path):
    chain,collect,prepare,calls=setup_intake(world,tmp_path,'idox','daily-stop')
    chain.owner_sets_stop()
    # Preflight reads alone do not confer source authority: the release collector
    # is still an unavailable prerequisite, never inferred from these reads.
    with pytest.raises(Exception):intake_slot(chain.caller,chain.root['key'],collect,chain.publisher,prepare)
    assert calls==[]
    assert chain.publisher.calls==[]
    assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0
