"""Actual owner preparation in the pinned #213 process and disposable PG.

Only provider IO is synthetic. Database name and original encrypted receipt
hash are explicitly projected fixture values; production constants stay exact.
"""
import copy
import hashlib
import importlib.util
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
import pytest


def exercise(w, recovery, tmp_path):
    from verification.ingestion_storage import owner_pilot as pinned
    # Earlier source-runtime fixtures rebind these globals. Restore the frozen
    # module's actual defaults before exercising its real Journal constructor.
    pinned.PERIOD='b-dbpilot-20261027-1102-05'
    pinned.PREDECESSOR='b-dbpilot-20261027-1102-04'
    from verification.ingestion_storage.intake_successor import owner_sql
    root=Path(os.environ['S4_SUCCESSOR_ROOT'])
    prefix='verification.ingestion_storage.'
    # These two modules contribute constants only to the preparation adapter.
    for name,key,value in [('tameside_package','PERIOD','S4_FINITE_677f555670666bcf21f45860'),
                           ('tameside_candidate','EXPIRY',1795032000.0)]:
        m=ModuleType(prefix+name);setattr(m,key,value);sys.modules[prefix+name]=m
    def load(name):
        spec=importlib.util.spec_from_file_location(prefix+name,root/'verification/ingestion_storage'/f'{name}.py')
        m=importlib.util.module_from_spec(spec);sys.modules[prefix+name]=m;spec.loader.exec_module(m);return m
    load('inactive_owner_writer_install')
    guard=load('bolton_recovery_guard');ja=load('tameside_owner_journal');prep=load('tameside_preparation')
    pinned,frozen_recovery,journal_source=prep.pinned_modules(os.environ['S4_BOLTON_PINNED_CHECKOUT'])
    # The existing failed_bolton fixture projects synthetic work/evidence hashes
    # into its recovery module and SQL inventory. Retain those explicit fixture
    # projections, while exercising the real isolated loader/Journal for IO.
    assert Path(frozen_recovery.__file__).read_bytes()==Path(recovery.__file__).read_bytes()
    frozen_recovery.predecessor.configure()  # same configuration as binding(db)
    assert journal_source==owner_sql()
    boot=w['boot']
    boot.execute('GRANT USAGE,CREATE ON SCHEMA public TO postgres WITH GRANT OPTION')
    class DB:
        key=hashlib.sha256(b'disposable-encryption-fixture-only').hexdigest()
        lose_commit=False;lose_journal=False;commits=0
        @contextmanager
        def connection(self):
            with w['actor']() as c:
                outer=self
                class Proxy:
                    def __getattr__(self,k):return getattr(c,k)
                    def execute(self,q,params=None):
                        if isinstance(q,str):
                            q=q.replace("current_database() IS DISTINCT FROM 'postgres'",
                                        "current_database() IS DISTINCT FROM 'ingestion_provisioning_test'")
                        result=c.execute(q,params)
                        if q=='COMMIT':
                            outer.commits+=1
                            if outer.lose_commit:
                                outer.lose_commit=False;raise RuntimeError('COMMIT_ACK_LOST')
                        if params and len(params)==4 and params[3] is not None and outer.lose_journal:
                            outer.lose_journal=False;raise RuntimeError('JOURNAL_ACK_LOST')
                        return result
                yield Proxy()
    db=DB()
    service=dict(id=pinned.SERVICE,ownerId=pinned.WORKSPACE,type='cron_job',autoDeploy='no',suspended='suspended',
        branch='master',serviceDetails=dict(plan='standard',schedule='0 5 * * *',
        envSpecificDetails=dict(startCommand='/bin/true',buildCommand='original harmless build')))
    environment={'DATABASE_URL':'SYNTHETIC_PRIVATE_OWNER_ROUTE','PYTHONUNBUFFERED':'1','PLAYWRIGHT_BROWSERS_PATH':'0'}
    # Build an authentic exhausted normal journal: 48 normal + eight cleanup
    # snapshots; actual frozen Vault, save limits, CAS and SQL, not a fake index.
    old=pinned.Journal(db,period=pinned.PERIOD);old.period=recovery.PERIOD;old.owner_period=old.period+'_owner'
    old.owner_run=hashlib.sha256(old.owner_period.encode()).hexdigest()[:32]
    state=dict(period=old.period,status='CLOSED',original_service=service,original_environment=environment,
        original_guard=pinned.service_guard(service),
        original_deploy_ids=[],build_guard=pinned.service_guard(service),
        build_environment={'PYTHONUNBUFFERED':'1'},build_receipt_created_at='2026-11-03T11:05:00Z',
        cleanup_reserve=dict(pinned.cleanup_reserve_policy(),cleanup_writes=0))
    state.update(binding={'render_config_sha256':state['original_guard']},
        access={'state':'DATABASE_CLOSURE_ACKNOWLEDGED','render':{
            'guard':state['original_guard'],'original':environment}},
        intents={k:{'state':'ACKNOWLEDGED'} for k in
            ('RESUSPEND','RESTORE_BUILD_CONFIGURATION','RESTORE_BUILD_ENVIRONMENT')})
    for n in range(23):
        state['sequence']=n;old.save(copy.deepcopy(state))
    # Invoke the frozen writer's actual compaction at the observed ordinal 22.
    # Ciphertext and private values are synthetic; shape/linkage are not flattened.
    pilot=pinned.Pilot.__new__(pinned.Pilot);pilot.journal=old;pilot.state=copy.deepcopy(old.state)
    pilot.reserve_closure_space()
    state=copy.deepcopy(old.state)
    assert state['closed_build_archive']['prior_ordinal']==22 and 'original_service' not in state
    for n in range(24,48):
        state['sequence']=n;old.save(copy.deepcopy(state))
    with pytest.raises(Exception,match='CLEANUP_ROW_BOUND'):old.save(copy.deepcopy(state))
    old.cleanup_mode=True
    for n in range(48,56):
        state=copy.deepcopy(old.state);state['sequence']=n;old.save(state)
    assert old.ordinal==55
    prep.CHECKPOINT_SHA=old.previous  # synthetic ciphertext, never production evidence
    checkpoint=dict(ordinal=55,sha256=old.previous)
    def history():
        return boot.execute('SELECT period,run_id,name,body,sha256 FROM ingestion_run_evidence WHERE period<>%s ORDER BY period,run_id,name',(ja.JOURNAL,)).fetchall()
    original_history=history()
    resolved=prep.original_checkpoint(pinned,db)
    assert resolved['original_service']==service and resolved['original_environment']==environment
    assert 'original_service' not in old.state and history()==original_history
    # Interrupted recovery is reconciled by actual inspector. The commit reply
    # is deliberately lost; there is one recovery commit across both entries.
    db.lose_commit=True
    def stop_at_recovery(boundary):
        if boundary=='RECOVERY_READBACK':raise InterruptedError(boundary)
    with pytest.raises(InterruptedError):
        prep.prepare_stopped(db,pinned=pinned,recovery=recovery,binding=w['binding'],journal_source=owner_sql(),
            api_factory=lambda:None,revision='1'*40,checkpoint=checkpoint,
            baseline=dict(service=service,environment=environment,deploy_ids=[]),interrupt=stop_at_recovery)
    assert db.commits==1
    def stop_at_install(boundary):
        if boundary=='JOURNAL_INSTALLED':raise InterruptedError(boundary)
    with pytest.raises(InterruptedError):
        prep.recover_and_install(db,recovery=recovery,binding=w['binding'],journal_source=owner_sql(),interrupt=stop_at_install)
    prep.recover_and_install(db,recovery=recovery,binding=w['binding'],journal_source=owner_sql())
    assert db.commits==1 and history()==original_history
    revision='1'*40
    baseline=dict(service=service,environment=environment,deploy_ids=[])
    class Provider:
        def __init__(self):
            self.service=copy.deepcopy(service);self.env=copy.deepcopy(environment);self.deploys=[]
            self.writes=[];self.lose=False
        def close(self):pass
        def call(self,method,path='',body=None):
            if method!='GET':
                # Every actual provider boundary reads a freshly decrypted DB
                # checkpoint from a different connection BEFORE mutating fixture.
                _,observed=ja.reconcile(pinned,db)
                assert any(x['state']=='INTENT' for x in observed['intents'].values())
                assert observed['original_environment']==environment
                self.writes.append((method,path,copy.deepcopy(body)))
            if method=='PUT':self.env={v['key']:v['value'] for v in body}
            elif method=='PATCH':
                self.service['branch']=body['branch']
                self.service['serviceDetails']['envSpecificDetails'].update(body['serviceDetails']['envSpecificDetails'])
            elif method=='POST' and path=='/resume':
                assert not any('DATABASE' in k for k in self.env)
                assert self.service['branch']=='pa-tam002/'+revision
                self.service['suspended']='not_suspended'
                self.deploys=[dict(id='dep-synthetic',commit=dict(id=revision),status='live',
                    createdAt='2026-11-17T20:00:00Z',finishedAt='2026-11-17T20:00:01Z')]
            elif method=='POST' and path=='/suspend':self.service['suspended']='suspended'
            if method!='GET' and self.lose:
                self.lose=False;raise RuntimeError('PROVIDER_ACK_LOST')
            if path=='/env-vars?limit=100':return [{'envVar':dict(key=k,value=v)} for k,v in self.env.items()]
            if path=='/deploys?limit=100':return [{'deploy':copy.deepcopy(d),'cursor':'synthetic'} for d in self.deploys]
            if path=='/jobs?limit=100':return []
            observed=copy.deepcopy(self.service)
            observed['updatedAt']='2026-11-17T20:30:00Z'  # not a configuration field
            return observed
    def new(api,hook=lambda _:None):
        return prep.StoppedDeployment(pinned,db,lambda:api,revision=revision,
            checkpoint=checkpoint,baseline=baseline,interrupt=hook)
    boundaries=['CHECKPOINT_READY']+[name+':'+point for name in
        ('BUILD_ENVIRONMENT','BUILD_CONFIGURATION','ONE_RESUME_BUILD','RESUSPEND',
         'RESTORE_BUILD_CONFIGURATION','RESTORE_BUILD_ENVIRONMENT') for point in ('INTENT','EFFECT','READBACK')]
    for boundary in boundaries:
        # Reset ONLY synthetic new namespace between independent fault scenarios.
        boot.execute('DELETE FROM ingestion_run_evidence WHERE period=%s',(ja.JOURNAL,))
        api=Provider()
        def interrupt(point):
            if point==boundary:raise InterruptedError(point)
        with pytest.raises(InterruptedError):new(api,interrupt).prepare()
        before=len(api.writes)
        resumed=new(api)
        if boundary.endswith(':INTENT'):
            with pytest.raises(ValueError,match='EFFECT_UNKNOWN'):resumed.prepare()
            assert len(api.writes)==before
            resumed.contain()
            assert resumed.state['status']=='PREPARATION_CONTAINED_NO_SUBMISSION'
        else:
            assert resumed.prepare()['status']=='STOPPED_BUILD_READY'
        assert api.env==environment and api.service==service
        assert sum(p=='/resume' for _,p,_ in api.writes)<=1
        assert history()==original_history
    # A changed live prerequisite between durable intent and dispatch refuses.
    for changed in ('stop','configuration','environment'):
        boot.execute('DELETE FROM ingestion_run_evidence WHERE period=%s',(ja.JOURNAL,))
        api=Provider()
        ctl=boot.execute("SELECT outcome::jsonb FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
        def drift(point):
            if point!='BUILD_ENVIRONMENT:INTENT':return
            if changed=='stop':
                value=copy.deepcopy(ctl);value['hard_stop_generation']=16
                boot.execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(value),))
            elif changed=='configuration':api.service['branch']='unexpected'
            else:api.env['UNREVIEWED']='fixture'
        with pytest.raises(ValueError,match='STOP15_CHANGED|PREWRITE_DRIFT'):
            new(api,drift).prepare()
        assert not api.writes
        boot.execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
        assert history()==original_history
    # Provider completion can outlive a browser/driver instance. A fresh driver
    # observes the existing deployment, never dispatches another resume/build.
    for terminal in ('live','build_failed'):
        boot.execute('DELETE FROM ingestion_run_evidence WHERE period=%s',(ja.JOURNAL,))
        api=Provider()
        original_call=api.call
        def pending(method,path='',body=None):
            result=original_call(method,path,body)
            if method=='POST' and path=='/resume':
                api.deploys[0]['status']='build_in_progress'
            return result
        api.call=pending
        with pytest.raises(ValueError,match='EFFECT_UNKNOWN:ONE_RESUME_BUILD'):
            new(api).prepare()
        assert sum(p=='/resume' for _,p,_ in api.writes)==1
        api.deploys[0]['status']=terminal
        if terminal=='live':assert new(api).prepare()['status']=='STOPPED_BUILD_READY'
        else:
            with pytest.raises(ValueError,match='EFFECT_UNKNOWN:ONE_RESUME_BUILD'):
                new(api).prepare()
            new(api).contain()
        assert api.env==environment and api.service==service
        assert sum(p=='/resume' for _,p,_ in api.writes)==1 and history()==original_history
    # Final happy path also loses journal and provider acknowledgements.
    boot.execute('DELETE FROM ingestion_run_evidence WHERE period=%s',(ja.JOURNAL,))
    api=Provider();db.lose_journal=True;api.lose=True
    assert prep.prepare_stopped(db,pinned=pinned,recovery=recovery,binding=w['binding'],
        journal_source=owner_sql(),api_factory=lambda:api,revision=revision,
        checkpoint=checkpoint,baseline=baseline)['status']=='STOPPED_BUILD_READY'
    driver=new(api)
    writes=len(api.writes);assert new(api).prepare()['status']=='STOPPED_BUILD_READY'
    assert len(api.writes)==writes and sum(p=='/resume' for _,p,_ in api.writes)==1
    assert driver.journal.ordinal<47 and history()==original_history
    assert boot.execute("SELECT pg_has_role('postgres','ingestion_storage_owner','USAGE'),pg_has_role('postgres','ingestion_storage_owner','SET'),has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone()==(False,False,False)
    return dict(boundaries=len(boundaries),drift_refusals=3,old_ordinal=55,normal_last_ordinal=47,
                recovery_readback=prep.recover_and_install(db,recovery=recovery,binding=w['binding'],journal_source=owner_sql()),
                recovery_commits=db.commits,provider_submissions=0,deployment_submissions=1,
                provider_fixture=dict(service=api.service,environment=api.env,deployment='dep-synthetic'),
                live_requests=0,original_history_preserved=True)
