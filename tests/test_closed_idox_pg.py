"""Restricted PG caller + real private detail worker. Sources/API are synthetic, never council qualification."""
import json,os,sys,time
from pathlib import Path
from unittest.mock import patch
import psycopg
import pytest
from sqlalchemy.orm import Session
from app.db.models import Application
from app.ingestion.ledger import Denied
from tests.e2e_pg_world import disposable_world,settings,RESTRICTED
from tests.e2e_chain_caller import Chain,application,snapshot,changed_tables
from tests.e2e_connection_support import entry,EXTENSION,LABEL
from tests.test_e2e_connection_pg import assert_closed,assert_confined,EXPECTED
from verification.direct_reference.fixtures import summary
from verification.ingestion_storage import operational_supervisor

COUNCILS=('bury','oldham','stockport')
COSTS=[]

@pytest.fixture(scope='module')
def world():
    gen=disposable_world();w=next(gen)
    yield w
    with pytest.raises(StopIteration):next(gen)
    with psycopg.connect(settings()[0],autocommit=True) as c:
        assert c.execute('SELECT count(*) FROM pg_roles WHERE rolname=ANY(%s)',(RESTRICTED,)).fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM pg_stat_activity WHERE usename=ANY(%s)',(RESTRICTED,)).fetchone()[0]==0
    value=dict(server_version=w['server_version'],setup_seconds=w['setup_seconds'],database_costs='RESTRICTED_BUDGET_DELTAS_EXCLUDING_SETUP_AND_ASSERTIONS',timing='REHEARSAL_WALL_INCLUDES_ASSERTIONS',setup_costs=w['setup_costs'],
        disposable_registration='EXPLICIT_OWNER_INSERTION_STAND_IN_NOT_PRODUCTION_AUTHORITY',credential_teardown='ROLES_AND_SESSIONS_ABSENT',cases=COSTS)
    if os.environ.get('CLOSED_IDOX_COST_PATH'):Path(os.environ['CLOSED_IDOX_COST_PATH']).write_text(json.dumps(value,sort_keys=True))


def staged(world,tmp,c,tag,entries=None):
    chain=Chain(world,tmp,'idox',tag,entries,council=c).owner_reset().owner_registers_capture()
    chain.capture();chain.read_capture();ns=chain.nominees();chain.owner_registers_chain(ns.nominees);chain.screen()
    return chain,ns


def admit_fixture(chain,n,tmp,*,status='Decided',decision='Approve',ref=None):
    adm=chain.caller.prepare(n)
    body=tmp/('detail-'+n.reference.replace('/','_')+'.html')
    body.write_bytes(summary(ref or n.reference,status=status,decision=decision,date='Mon 28 Sep 2026' if decision else ''))
    root=tmp/('detail-process-'+n.reference.replace('/','_'));observations=[]
    reader=chain.caller.closed_idox_detail(adm,root=root,observe=lambda *x:observations.append(x))
    actual=operational_supervisor.subprocess.Popen
    calls=[]
    def launch(command,**kw):
        assert command[1:3]==['-m','verification.ingestion_storage.operational_source'] and '--closed-idox-target' in command
        assert not any('DATABASE' in k or 'TOKEN' in k or 'PASSWORD' in k for k in kw['env'])
        calls.append(1)
        # Only replace the module entry with a fixture that injects synthetic HTTP responses,
        # then calls the SAME operational_source.main; guards/parser/supervisor remain real.
        return actual([command[0],'-m','tests.closed_idox_source_fixture',*command[3:],'--fixture-html',str(body)],**kw)
    with patch.object(operational_supervisor.subprocess,'Popen',launch):
        result=chain.caller.admit(adm,reader)
    if (root/'worker-result.json').exists():
        measured=json.loads((root/'worker-result.json').read_bytes())
        observations.append(('synthetic_detail_metrics',{k:measured.get(k) for k in ('requests','received_body_bytes','elapsed_seconds')}))
    return result,calls,observations


@pytest.mark.parametrize('c',COUNCILS)
def test_full_closed_caller_commit_readback_and_confinement(world,tmp_path,c):
    chain,ns=staged(world,tmp_path,c,'complete-'+c);boot=world['boot'];receipt=chain.capture_receipt
    assert receipt['durable_archive']['readback_verified'] and receipt['evidence_label']==LABEL
    assert receipt['qualification_sha256']==chain.contract.qualification_sha256 and receipt['outer_supervisor']==chain.outer
    assert receipt.get('date_semantics','RECEIVED')==('VALIDATED' if c=='stockport' else 'RECEIVED')
    assert {r:chain.screening_outcome(r) for r in EXPECTED}==EXPECTED
    before=snapshot(boot);started=time.monotonic();source=[]
    for n in ns.nominees:
        result,calls,observations=admit_fixture(chain,n,tmp_path)
        assert result['outcome']=='SUPPORTED_FACTS_VERIFIED' and result['factual']['verification_scope']=='COUPLED'
        assert calls==[1]
        supervisor=next(v for k,v in observations if k=='source_supervisor_observed')
        assert supervisor['cleanup']=='CLOSED' and supervisor['exit_code']==0 and supervisor['live_owned_survivors']==0
        source.append(dict(supervisor=supervisor,synthetic_detail_metrics=next(v for k,v in observations if k=='synthetic_detail_metrics')))
        row=application(boot,c,n.reference)
        assert row['status']=='Decided' and row['decision']=='Approve' and row['status_verified_at']
        assert row['site_id'] is None and row['unit_confirmation_status']=='discovery_pending'
    assert len(ns.nominees)==2 and chain.listing_requests==[]
    assert_confined(world,'idox',before,admitted=True);assert_closed(world,chain)
    bs=chain.caller.budgets
    COSTS.append(dict(council=c,commands=sum(x.statements-x.previous.get('driver_statements',0) for x in bs),connection_attempts=sum(x.attempts-x.previous.get('connection_attempts',0) for x in bs),
        returned_data_value_bytes=sum(x.returned_bytes-x.previous.get('returned_data_value_bytes',0) for x in bs),rehearsal_admission_wall_seconds_including_assertions=time.monotonic()-started,source_supervisors=source,
        audit_archive_bytes=(chain.publisher.root/(receipt['durable_archive']['sha256']+'.json')).stat().st_size,identities=2,factual_deliveries=2,withheld=0,accounting=chain.accounting,aggregate_method='PER_BUDGET_DELTA_EXCLUDING_CARRIED_PRIOR'))


@pytest.mark.parametrize('c',COUNCILS)
def test_existing_identity_and_zero_eligible_are_valid(world,tmp_path,c):
    chain,ns=staged(world,tmp_path,c,'existing-'+c)
    with Session(world['app']) as s:s.add(Application(council_code=c,reference=ns.nominees[0].reference,status='PRESERVED'));s.commit()
    before=snapshot(world['boot'])
    result,calls,_=admit_fixture(chain,ns.nominees[0],tmp_path)
    assert result['outcome']=='DISCOVERY_SCREENING_ONLY_ALREADY_KNOWN' and calls==[]
    assert application(world['boot'],c,ns.nominees[0].reference)['status']=='PRESERVED'
    assert snapshot(world['boot'])==before
    assert_closed(world,chain)
    zero,ns=staged(world,tmp_path,c,'zero-'+c,[entry('ZERO/1',EXTENSION)])
    assert ns.nominees==() and zero.facts=={} and zero.chain_registration.grant['source_calls']==zero.chain_registration.grant['writes']==0
    assert_closed(world,zero)


@pytest.mark.parametrize('c',COUNCILS)
@pytest.mark.parametrize('kind',('unsupported','identity'))
def test_fresh_unsupported_or_wrong_identity_creates_nothing(world,tmp_path,c,kind):
    chain,ns=staged(world,tmp_path,c,kind+c)
    before=snapshot(world['boot'])
    result,calls,_=admit_fixture(chain,ns.nominees[0],tmp_path,status='Deposited' if kind=='unsupported' else 'Decided',decision='' if kind=='unsupported' else 'Approve',ref='OTHER/1' if kind=='identity' else None)
    assert result['outcome']=='FACTS_WITHHELD' and calls==[1] and snapshot(world['boot'])==before
    assert_closed(world,chain)


@pytest.mark.parametrize('c',COUNCILS)
@pytest.mark.parametrize('kind',('missing','expired','insufficient'))
def test_restricted_authority_refusal_stores_no_application(world,tmp_path,c,kind):
    chain,ns=staged(world,tmp_path,c,kind+c);control=chain._control()
    if kind=='missing':del control['grants'][chain.auth_chain]
    elif kind=='expired':control['grants'][chain.auth_chain]['expires_at']=0
    else:control['grants'][chain.auth_chain]['writes']=0
    chain._write_control(control)
    with pytest.raises(Exception) as exc:admit_fixture(chain,ns.nominees[0],tmp_path)
    assert not isinstance(exc.value,(AssertionError,TypeError,KeyError,AttributeError))
    assert application(world['boot'],c,ns.nominees[0].reference) is None
    assert_closed(world,chain)

@pytest.mark.parametrize('field,value',[('council','tameside'),('source_url','https://example.org/'),('source_record_id','OTHER'),('capture_sha256','f'*64),('screening_revision','f'*64),('outcome','ADMIT_FOR_ASSESSMENT')])
def test_substituted_nominee_refuses_before_prepare_or_source(world,tmp_path,field,value):
 from dataclasses import replace
 chain,ns=staged(world,tmp_path,'bury','nominee-'+field)
 with pytest.raises(Denied,match='CLOSED_IDOX_NOMINEE_BINDING'):chain.caller.prepare(replace(ns.nominees[0],**{field:value}))
 assert application(world['boot'],'bury',ns.nominees[0].reference) is None
 assert_closed(world,chain)

@pytest.mark.parametrize('c',COUNCILS)
@pytest.mark.parametrize('kind',('identity_only','partial'))
def test_complete_caller_refuses_non_metadata_or_partial_sources(world,tmp_path,c,kind):
 from app.ingestion.ledger import digest
 from verification.discovery.source_profiles import profile
 chain=Chain(world,tmp_path,'idox','badcapture-'+kind+c,council=c).owner_reset().owner_registers_capture()
 source,_=chain.supervised_source();source=json.loads(json.dumps(source))
 if kind=='identity_only':source['collection_profile']=profile(dict(council=c,semantics=chain.binding.semantics,start=chain.contract.scope()['start'],end=chain.contract.scope()['end']),'IDENTITY_ONLY')
 else:source['enumeration_evidence']='TOTAL_UNKNOWN'
 with pytest.raises(Denied):chain.capture(source=source,expected=digest(source))
 assert chain.publisher.calls==[] and world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0
 assert_closed(world,chain)

@pytest.mark.parametrize('c',COUNCILS)
@pytest.mark.parametrize('field',('qualification_sha256','outer_supervisor','kind'))
def test_saved_capture_binding_refused_through_restricted_readback(world,tmp_path,c,field):
 chain=Chain(world,tmp_path,'idox','saved-'+field+c,council=c).owner_reset().owner_registers_capture()
 chain.capture()
 chain.tamper(chain.root['key'],[field],None)
 with pytest.raises(Denied):chain.read_capture()
 assert world['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==0
 assert_closed(world,chain)
