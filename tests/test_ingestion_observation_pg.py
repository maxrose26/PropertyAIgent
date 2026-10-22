"""Restricted PostgreSQL observation path; RECONSTRUCTED markup, never council contact."""
import copy
import json
import time
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.test_ingestion_v3_admission_pg import pg
from tests.test_ingestion_listing_observation import single_page_audit, multi_page_audit, contract, LIMITS, T1
from tests.test_discovery_ingestion_ledger import outer
from app.ingestion.ledger import Denied, digest
from app.ingestion.batching import batch_plans, process_batch, capture_once
from app.ingestion.coordinator import Coordinator
from app.ingestion.listing_screening import ScreeningRule, RULE_V1, RULE_V3, V3_CONTRACT, assessment_identity, code_binding, ROUTING_VOCABULARY
from app.ingestion.observation_screening import retained_history
from verification.ingestion_storage.observation_controller import retain_observation
from app.ingestion.observation_history import empty_history, append
from verification.ingestion_storage import observation_worker_sql as ow, screening_v3_worker_sql as v3
from verification.ingestion_storage.operational_controller import ControllerLedger, DatabaseBudget, AcceptanceBinding, execute, resume_capture, assessment_plan
from verification.ingestion_storage.retained_world import item
from verification.ingestion_storage.v3_admission import V3AdmissionBinding
from app.config import get_council
from tests.test_discovery_admission import envelope


@pytest.fixture
def world(pg, request, record_property):
    import os
    tmp_path=Path(os.environ['TMPDIR'])/('fixture-'+digest(request.node.nodeid)[:16])
    tmp_path.mkdir()
    before=dict(pg['fixture_costs'])
    boot=pg['boot']
    boot.execute('ALTER ROLE ingestion_recovery_login LOGIN')  # existing mapped restricted capability, fixture only
    with pg['connect']('provisioning_migrator') as c:c.execute(ow.installation_script())
    boot.execute('DELETE FROM ingestion_work_attempts')
    boot.execute("DELETE FROM ingestion_work_items WHERE key<>repeat('0',64)")
    boot.execute('TRUNCATE applications CASCADE')
    control=copy.deepcopy(pg['control']);control['grants']={}
    boot.execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(control),))
    all_costs=[];bound={};grant=None;audit=single_page_audit();reads=[];archives=[]
    rule=ScreeningRule(RULE_V3,unit_threshold=10,link_related=False)
    def archive(raw):
        path=tmp_path/(digest(json.loads(raw))+'.json');path.write_bytes(raw)
        assert path.read_bytes()==raw
        archives.append(path)
        return dict(commit='a'*40,path='docs/design/RECONSTRUCTED/'+path.name,sha256=digest(json.loads(path.read_bytes())),bytes=len(raw),readback_verified=True)
    def seed(tag='one', enable=True, capture_only=True):
        nonlocal grant
        cfg=contract().config
        root=item(dict(subject=dict(kind='DISCOVERY_SCOPE',council='bolton',start=cfg.start.isoformat(),end=cfg.end.isoformat(),semantics='RECEIVED'),task='DISCOVERY',contract='controller-idox',revision=tag))
        boot.execute('INSERT INTO ingestion_work_items SELECT * FROM json_populate_record(NULL::ingestion_work_items,%s::json)',(json.dumps(root),))
        bound[root['key']]={k:root[k] for k in ('subject','task','contract','revision')}
        grant=dict(keys=list(bound),contracts=['controller-idox','listing-batch-v1','listing-screen-v1',V3_CONTRACT],bindings=bound,expires_at=time.time()+600,source_calls=1,writes=0,login='ingestion_worker_login',effect_login='ingestion_effect_login',workers=['one'],screening_configs=[digest(rule.config())],capture_only=capture_only,completion_outcomes={'DISCOVERY':['ENUMERATED_METADATA_RETAINED'],'LISTING_METADATA':['BATCH_SCREENED'],'SCREENING':['ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT','ROUTE_COUNT_UNCONFIRMED','RETAIN_RELATED_TO_PARENT','RETAIN_NOT_RESIDENTIAL_SUPPLY','RETAIN_BELOW_THRESHOLD','INSUFFICIENT_EVIDENCE']})
        if enable:grant['observation_councils']=['bolton']
        save()
        return root
    def save():
        grant['completion_outcomes']['SCREENING']=sorted(set(ROUTING_VOCABULARY[RULE_V1])|set(ROUTING_VOCABULARY[RULE_V3]))
        ctl=boot.execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
        ctl['grants']['INGESTION_TEST_observation']=grant
        boot.execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
    def client(key, enabled=True, previous=None, selected=None):
        budget=DatabaseBudget(slot_key=key,previous=previous)
        worker,broker=[budget.engine(pg['urls'][r]) for r in ['ingestion_worker_login','ingestion_effect_login']]
        ledger=ControllerLedger(worker,budget=budget,owner='one',authority='INGESTION_TEST_observation',bindings=bound,broker_engine=broker)
        co=Coordinator(ledger,{'controller-idox':contract()},screening_rules={(selected or rule).contract():selected or rule},observation_councils=('bolton',) if enabled else ())
        return co,budget
    def close(budget):
        costs=budget.close([])
        prior=budget.previous or {}
        increments={k:costs[k]-prior.get(k,0) for k in ('driver_statements','connection_attempts','returned_data_value_bytes','elapsed_seconds')}
        all_costs.append(dict(receipt=costs,prior_receipt_sha256=digest(prior) if prior else None,incremental=increments))
        assert costs['cleanup']=='CLOSED' and costs['connections_opened']==costs['connections_closed_count']
        return costs
    def reader(_):reads.append(1);return audit,outer()
    def batches(root, obs, selected=None):
        selected=selected or rule
        plans=batch_plans(root['key'],obs,selected if selected.rule_version!=RULE_V1 else None,observation_councils=('bolton',))
        for p in plans:
            row=item({k:p[k] for k in ('subject','task','contract','revision')},dependencies=p['dependencies'],checkpoint=p['checkpoint'])
            boot.execute('INSERT INTO ingestion_work_items SELECT * FROM json_populate_record(NULL::ingestion_work_items,%s::json)',(json.dumps(row),))
            bound[row['key']]={k:row[k] for k in ('subject','task','contract','revision')}
            grant['keys'].append(row['key'])
            for r in obs['records'][p['checkpoint']['plan']['first']:p['checkpoint']['plan']['last']]:
                from app.ingestion.observation_screening import observation_revision
                rev=digest(r) if selected.rule_version==RULE_V1 else assessment_identity(r,selected)[3]
                if obs['kind']=='LISTING_OBSERVATION_V1':rev=observation_revision(rev,digest(obs))
                ident=dict(subject=dict(kind='APPLICATION',council='bolton',reference=r['reference']),task='SCREENING',contract=selected.contract(),revision=rev)
                k=digest(ident);bound[k]=ident;grant['keys'].append(k)
        grant['bindings']=bound;save();return plans
    value=dict(pg=pg,boot=boot,seed=seed,client=client,close=close,reader=reader,archive=archive,reads=reads,batches=batches,save=save,audit=audit,rule=rule,bound=bound,archives=archives)
    yield value
    assert boot.execute('SELECT count(*) FROM applications').fetchone()[0]==0
    assert boot.execute('SELECT count(*) FROM sites').fetchone()[0]==0
    record_property('measured',json.dumps(dict(runtime=all_costs,retained_archive_bytes=sum(p.stat().st_size for p in set(archives)),fixture_cursor_calls=pg['fixture_costs']['cursor_calls']-before['cursor_calls'],fixture_connections=pg['fixture_costs']['connection_attempts']-before['connection_attempts']),sort_keys=True))


def retain(w,root,**kw):
    co,b=w['client'](root['key'],**kw)
    try:return retain_observation(co,root['key'],w['reader'],w['archive'],check=b.check)
    finally:w['close'](b)


def test_capture_screen_repeat_and_history(world):
    w=world;root=w['seed']();obs=retain(w,root)
    assert obs['kind']=='LISTING_OBSERVATION_V1' and obs['window_claim']=='NONE'
    assert obs['source_sha256']==obs['durable_archive']['sha256']
    original=copy.deepcopy(obs);assert retain(w,root)==obs and w['reads']==[1]
    plans=w['batches'](root,obs)
    for p in plans:
        co,b=w['client'](p['key'])
        try:
            result=process_batch(co,p['key'],check=b.check)
            assert process_batch(co,p['key'],check=b.check)['outcome']=='BATCH_ALREADY_COMPLETE'
            for key in result['children']:
                row=co.ledger.get(key);cp=row['checkpoint']
                assert cp['source_kind']==obs['kind'] and cp['window_claim']=='NONE' and cp['observation_digest']==digest(obs)
                assert cp['observed_at']==obs['observed_at'] and cp['config']==w['rule'].config()
                assert cp['assessment_revision']==row['revision'] and cp['record_sha256'] in {digest(r) for r in obs['records']}
        finally:w['close'](b)
    other=w['seed']('later');later=retain(w,other)
    assert later['observed_at']!=obs['observed_at']
    p=w['batches'](other,later)[0];co,b=w['client'](p['key'])
    try:
        process_batch(co,p['key'],check=b.check)
        history=retained_history(co.ledger,[root['key'],other['key']])
        assert all(len(a['observations'])==2 for a in history['applications'].values())
        assert append(append(empty_history(),obs),obs)==append(empty_history(),obs)
        assert co.ledger.get(root['key'])['checkpoint']==original
    finally:w['close'](b)
    assert len(w['reads'])==2


@pytest.mark.parametrize('failure',['controller_off','grant_off','grant_off_non_capture','archive','full_page','next_link','bad_scope','wrong_config','changed_record'])
def test_refusals_and_stops(world,failure):
    w=world;root=w['seed'](enable=failure not in {'grant_off','grant_off_non_capture'},capture_only=failure!='grant_off_non_capture')
    if failure=='full_page':w['audit'].update(single_page_audit(10))
    if failure=='next_link':w['audit']['pages'][0]['terminal']='NEXT_LINK'
    if failure=='bad_scope':w['audit']['council']='bury'
    if failure=='archive':w['archive']=lambda raw:dict(sha256='0'*64,bytes=len(raw),readback_verified=True,commit='a'*40,path='docs/design/bad')
    if failure in {'wrong_config','changed_record'}:
        obs=retain(w,root);p=w['batches'](root,obs)[0]
        selected=ScreeningRule(RULE_V3,unit_threshold=11,link_related=False) if failure=='wrong_config' else None
        co,b=w['client'](p['key'],selected=selected)
        try:
            if failure=='changed_record':
                claim=co.ledger.claim(p['key']);bad=copy.deepcopy(obs['records'][0]);bad['reference']='FORGED'
                with pytest.raises(DBAPIError):co.ledger.batch_row(claim,p['checkpoint']['plan'],obs,bad)
            else:
                with pytest.raises(Denied):process_batch(co,p['key'],check=b.check)
        finally:w['close'](b)
    else:
        with pytest.raises((Denied,DBAPIError)):retain(w,root,enabled=failure!='controller_off')
        assert w['boot'].execute('SELECT checkpoint FROM ingestion_work_items WHERE key=%s',(root['key'],)).fetchone()[0] is None


def test_partial_rejected_by_complete_admission_and_resume(world):
    w=world;root=w['seed']();obs=retain(w,root);p=w['batches'](root,obs)[0]
    co,b=w['client'](p['key'])
    try:
        with pytest.raises(Denied):capture_once(co,root['key'],lambda _:pytest.fail('refetch'),w['archive'])
        with pytest.raises(Denied,match='RETAINED_CAPTURE_BINDING'):assessment_plan(co,root['key'],capture_sha256=digest(obs),batch_keys=[p['key']],preserved_keys=[root['key']])
        nominee=AcceptanceBinding(root['key'],'s'*64,'f'*64,obs['records'][0]['reference'],'url','key','0'*64,digest(obs),'0'*64,p['key'])
        binding=V3AdmissionBinding(nominee,'bolton','controller-idox','one',digest(w['rule'].config()),digest(code_binding()),'fact','one','0'*64)
        with pytest.raises(Denied,match='V3_COMPLETE_IDOX_CAPTURE_REQUIRED'):execute(co,binding,listing_reader=lambda _:pytest.fail('refetch'),detail_reader=lambda _:pytest.fail('detail'),envelope=envelope(),council=get_council('bolton'))
        b.capture_checkpoint_sha256=digest(co.ledger.get(root['key'])['checkpoint'])
    finally:prior=w['close'](b)
    co,b=w['client'](p['key'],previous=prior)
    try:
        with pytest.raises(Denied,match='RETAINED_CAPTURE_BINDING'):resume_capture(co,root['key'],checkpoint_sha256=digest(obs),prior_accounting_sha256=digest(prior),screening_keys=[])
    finally:w['close'](b)


def test_function_rollback_and_runtime_install_denied(world):
    w=world;pg=w['pg'];boot=w['boot']
    before=boot.execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
    def flags():return boot.execute("SELECT proowner,proacl,proconfig,prosrc FROM pg_proc WHERE oid='public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'::regprocedure").fetchone()
    installed=flags()
    with pg['connect']('ingestion_worker_login') as c:
        import psycopg
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute(ow.installation_script())
        c.execute('ROLLBACK')
    with pg['connect']('provisioning_migrator') as c:c.execute(ow.rollback_script())
    reverted=flags();assert reverted[:3]==installed[:3]
    import re
    body=lambda script:re.search(r'AS \$fn\$(.*?)\$fn\$;',script,re.S).group(1)
    assert installed[3]==body(ow.installation_script())
    assert reverted[3]==body(ow.rollback_script())
    assert reverted[3]!=installed[3]
    assert boot.execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]==before
    root=w['seed']()
    with pytest.raises(Denied,match='OBSERVATION_WORKER_NOT_INSTALLED'):retain(w,root)
    assert not w['reads']
    assert boot.execute('SELECT checkpoint FROM ingestion_work_items WHERE key=%s',(root['key'],)).fetchone()[0] is None


def test_uncertain_resolution_does_not_replay(world,monkeypatch):
    w=world;root=w['seed']();co,b=w['client'](root['key'])
    real=co.ledger._step
    def lost(op,*a,**kw):
        result=real(op,*a,**kw)
        if op=='resolve_effect':raise RuntimeError('injected acknowledgement loss before broker commit')
        return result
    monkeypatch.setattr(co.ledger,'_step',lost)
    try:
        with pytest.raises(RuntimeError):retain_observation(co,root['key'],w['reader'],w['archive'])
        with pytest.raises(Denied):retain_observation(co,root['key'],lambda _:pytest.fail('refetch'),w['archive'])
        assert co.ledger.get(root['key'])['phase']=='SOURCE_INTENT'
        ctl=w['boot'].execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
        assert ctl['global_stop'] is not None
    finally:w['close'](b)


@pytest.mark.parametrize('capture_only',[False,None])
@pytest.mark.parametrize('operation',['checkpoint','resolve_source'])
def test_direct_sql_cannot_bypass_enablement(world,capture_only,operation):
    w=world;root=w['seed'](enable=False,capture_only=capture_only);co,b=w['client'](root['key'])
    obs=contract().observe(w['audit'],outer(),LIMITS,observed_at=T1)
    try:
        claim=co.ledger.claim(root['key'])
        if operation=='resolve_source':co.ledger.intent(claim,'source_calls')
        with pytest.raises(DBAPIError):getattr(co.ledger,operation)(claim,obs)
        assert co.ledger.get(root['key'])['checkpoint'] is None
    finally:w['close'](b)


@pytest.mark.parametrize('version',[RULE_V1,RULE_V3])
def test_complete_and_v1_behavior_under_combined_function(world,version):
    w=world;root=w['seed']();w['audit'].update(multi_page_audit())
    rule=ScreeningRule(RULE_V1) if version==RULE_V1 else w['rule']
    co,b=w['client'](root['key'],selected=rule,enabled=False)
    try:
        co.idox_source(co.ledger.claim(root['key']),w['reader'],materialize=False,archive=w['archive'])
        receipt=co.ledger.get(root['key'])['checkpoint'];assert receipt['kind']=='LISTING_RECEIPT_V1'
    finally:w['close'](b)
    for p in w['batches'](root,receipt,selected=rule):
        co,b=w['client'](p['key'],selected=rule,enabled=False)
        try:
            result=process_batch(co,p['key'],check=b.check)
            for child in result['children']:
                cp=co.ledger.get(child)['checkpoint']
                assert 'window_claim' not in cp and 'observation_digest' not in cp
                assert cp['rule_version']==version
        finally:w['close'](b)


def recover(w,key,fence):
    # Clock expiry is injected by fixture only; the recovery effect uses the
    # existing restricted recovery login, not bootstrap or worker authority.
    w['boot'].execute('UPDATE ingestion_work_items SET lease_until=0 WHERE key=%s',(key,))
    co,b=w['client'](key);recovery=b.engine(w['pg']['urls']['ingestion_recovery_login'])
    try:
        with recovery.begin() as c:
            row=c.execute(text('SELECT public.ingestion_recover_abandoned(:key,:fence,true)'),dict(key=key,fence=fence)).scalar_one()
        assert row['state']=='DEFERRED'
    finally:w['close'](b)


def test_capture_checkpoint_recovery_and_stale_fence(world,monkeypatch):
    w=world;root=w['seed']();co,b=w['client'](root['key'])
    def interrupted(*a,**k):raise KeyboardInterrupt('fixture crash after committed checkpoint')
    monkeypatch.setattr(co.ledger,'finish',interrupted)
    try:
        with pytest.raises(KeyboardInterrupt):retain_observation(co,root['key'],w['reader'],w['archive'])
        row=co.ledger.get(root['key']);assert row['phase']=='CHECKPOINTED'
    finally:prior=w['close'](b)
    recover(w,root['key'],row['fence'])
    co,b=w['client'](root['key'],previous=prior)
    try:
        result=retain_observation(co,root['key'],lambda _:pytest.fail('refetch'),w['archive'],prior_accounting_sha256=digest(prior))
        assert result['kind']=='LISTING_OBSERVATION_V1' and w['reads']==[1]
        from app.ingestion.ledger import Claim
        with pytest.raises(DBAPIError):co.ledger.checkpoint(Claim(root['key'],row['fence'],'one'),result)
    finally:w['close'](b)


def test_batch_interruption_preserves_atomic_progress(world):
    w=world;root=w['seed']();obs=retain(w,root);p=w['batches'](root,obs)[0]
    co,b=w['client'](p['key'])
    try:
        def crash(_):raise KeyboardInterrupt('fixture crash after one committed row')
        with pytest.raises(KeyboardInterrupt):process_batch(co,p['key'],check=b.check,after_row=crash)
        row=co.ledger.get(p['key']);assert row['checkpoint']['next']==1
        child=row['checkpoint']['children'][0]
    finally:prior=w['close'](b)
    recover(w,p['key'],row['fence'])
    co,b=w['client'](p['key'],previous=prior)
    try:
        process_batch(co,p['key'],check=b.check,prior_accounting_sha256=digest(prior))
        assert co.ledger.get(p['key'])['checkpoint']['children'].count(child)==1
        assert w['reads']==[1]
    finally:w['close'](b)


@pytest.mark.parametrize('field',['window_claim','observed_at','observation_digest','source_kind'])
def test_sql_screening_provenance_is_not_worker_assertion(world,field,monkeypatch):
    w=world;root=w['seed']();obs=retain(w,root);p=w['batches'](root,obs)[0]
    co,b=w['client'](p['key']);real=co.ledger.checkpoint
    def forged(claim,receipt):
        receipt=copy.deepcopy(receipt)
        if field=='source_kind':receipt.pop(field)
        else:receipt[field]='FORGED'
        return real(claim,receipt)
    monkeypatch.setattr(co.ledger,'checkpoint',forged)
    try:
        with pytest.raises(DBAPIError,match='OBSERVATION_SCREEN_BINDING|SCREENING_V3_RECEIPT'):
            process_batch(co,p['key'],check=b.check)
    finally:w['close'](b)


def test_committed_checkpoint_acknowledgement_loss_is_not_auto_resumed(world,monkeypatch):
    w=world;root=w['seed']();co,b=w['client'](root['key']);real=co.ledger.resolve_source
    def lost(*a,**kw):
        real(*a,**kw)  # real broker transaction committed; caller loses acknowledgement
        raise RuntimeError('injected postcommit acknowledgement loss')
    monkeypatch.setattr(co.ledger,'resolve_source',lost)
    try:
        with pytest.raises(RuntimeError):retain_observation(co,root['key'],w['reader'],w['archive'])
        row=co.ledger.get(root['key']);assert row['phase']=='CHECKPOINTED' and row['state']=='CLAIMED'
        assert row['checkpoint']['kind']=='LISTING_OBSERVATION_V1'
        with pytest.raises(Denied):retain_observation(co,root['key'],lambda _:pytest.fail('refetch'),w['archive'])
        ctl=w['boot'].execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
        assert ctl['global_stop'] is not None
        assert w['reads']==[1]
    finally:w['close'](b)


def test_direct_shared_coordinator_is_disabled_by_rollback(world):
    w=world;root=w['seed']()
    with w['pg']['connect']('provisioning_migrator') as c:c.execute(ow.rollback_script())
    co,b=w['client'](root['key'])
    try:
        claim=co.ledger.claim(root['key'])
        with pytest.raises(Denied,match='OBSERVATION_WORKER_NOT_INSTALLED'):
            co.idox_source(claim,w['reader'],materialize=False,archive=w['archive'])
        assert co.ledger.get(root['key'])['phase']=='CLAIMED'
        assert not w['reads']
    finally:w['close'](b)
