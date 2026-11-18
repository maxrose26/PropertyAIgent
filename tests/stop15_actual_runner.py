"""Actual STOP15 remaining runner on retained partial disposable state.

Synthetic ciphertext/provider/credentials/database name are explicit projections.
No production sockets or credentials are used. The deployed worker source is old.
"""
import copy, hashlib, importlib, json, os, shlex, time
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
import pytest


def exercise(w, prior, manifest, root):
    root.mkdir(exist_ok=True)
    fault=os.environ.get('S4_STOP15_FAULT','none')
    plan=importlib.import_module('_stop15_corrected_owner.tameside_stop15')
    run=importlib.import_module('_stop15_corrected_owner.tameside_stop15_run')
    prep=importlib.import_module('_stop15_corrected_owner.tameside_preparation')
    ja=importlib.import_module('_stop15_corrected_owner.tameside_owner_journal')
    access_mod=importlib.import_module('_stop15_corrected_owner.tameside_owner_access')
    pinned,_,source=prep.pinned_modules(os.environ['S4_BOLTON_PINNED_CHECKOUT'])
    class DB:
        key=hashlib.sha256(b'disposable-encryption-fixture-only').hexdigest()
        lose_install=True;install_calls=0;raw_mode=False;lose_journal=False;journal_lost=False
        upgrade_calls=0;upgrade_ack_lost=False;fail_upgrade_checkpoint=True
        @contextmanager
        def connection(self):
            with w['actor']() as c:
                if DB.raw_mode:
                    yield c;return
                class Projection:
                    def __getattr__(self,n):return getattr(c,n)
                    def execute(self,q,args=None):
                        if isinstance(q,str):q=q.replace("current_database() IS DISTINCT FROM 'postgres'","current_database() IS DISTINCT FROM 'ingestion_provisioning_test'")
                        if DB.fail_upgrade_checkpoint and isinstance(q,str) and 'ingestion_intake_owner_state' in q and args and len(args)==4 and args[3] is not None and DB.upgrade_calls:
                            DB.fail_upgrade_checkpoint=False
                            raise RuntimeError('DISPOSABLE_UPGRADE_CHECKPOINT_NOT_WRITTEN')
                        value=c.execute(q,args)
                        if isinstance(q,str) and 'DO $capacity_upgrade_guard$' in q:
                            DB.upgrade_calls+=1;DB.upgrade_ack_lost=True
                            raise RuntimeError('DISPOSABLE_UPGRADE_SQL_COMMIT_ACK_LOST')
                        if DB.lose_journal and isinstance(q,str) and 'ingestion_intake_owner_state' in q and args and len(args)==4 and args[3] is not None:
                            DB.lose_journal=False;DB.journal_lost=True;raise RuntimeError('DISPOSABLE_JOURNAL_ACK_LOST')
                        if isinstance(q,str) and 'CAMPAIGN_INSTALL_NOT_STOPPED' in q:
                            DB.install_calls+=1
                            if DB.lose_install:
                                DB.lose_install=False
                                raise RuntimeError('DISPOSABLE_INSTALL_COMMIT_ACK_LOST')
                        return value
                yield Projection()
    db=DB();journal=ja._bound_journal(pinned,db,capacity50=True);state=journal.load()
    # Materialise the actual already-completed dispositions/writer into the
    # same encrypted journal. Then close/reopen at the continuation boundary.
    for name in ('DISPOSITIONS','WRITER'):
        state['intents'][name]=dict(state='INTENT');journal.save(copy.deepcopy(state))
        state['intents'][name]['state']='ACKNOWLEDGED';journal.save(copy.deepcopy(state))
    old_bound=time.time()-3600
    old=plan.compile_remaining(os.environ['S4_TAMESIDE_RUNTIME_CHECKOUT'],manifest,bound_at=old_bound,owner_journal_source=source)
    # Retained production had a large historical deployment inventory, unlike
    # the former one-deployment disposable projection. Preserve 77 prior IDs
    # plus the current accepted deployment in the provider's 78-item inventory.
    history_ids=['dep-'+hashlib.sha256(('historic-'+str(i)).encode()).hexdigest()[:20] for i in range(77)]
    state['original_deploy_ids']=copy.deepcopy(history_ids)
    state.update(status='STOPPED_PACKAGE_SEALED',bound_at=old_bound,manifest=manifest,policy=json.loads(old['policy.json']),package_index=json.loads(old['continuation.json']))
    journal.save(copy.deepcopy(state))
    assert journal.ordinal==18,journal.ordinal
    original_journal=pinned.Journal(db,period=pinned.PERIOD)
    original_journal.period='b-bolton-20261103-1105-01';original_journal.owner_period=original_journal.period+'_owner';original_journal.owner_run=hashlib.sha256(original_journal.owner_period.encode()).hexdigest()[:32]
    original=original_journal.load();assert original_journal.ordinal==55
    # Only synthetic immutable identities differ from production constants.
    prep.CHECKPOINT_SHA=original_journal.previous
    run.original_checkpoint.__globals__['CHECKPOINT_SHA']=original_journal.previous
    plan.CHECKPOINT=journal.previous;plan.OLD_BOUND=old_bound;plan.OLD_MANIFEST=manifest['manifest_binding_sha256'];plan.OLD_INDEX=hashlib.sha256(json.dumps(state['package_index'],sort_keys=True,indent=2).encode()).hexdigest();plan.DEPLOYMENT='dep-synthetic'
    journal,state=ja.reconcile(pinned,db,capacity50=True)
    plan.retained_start(state,ordinal=journal.ordinal,sha256=journal.previous)
    all_history=w['boot'].execute('SELECT period,run_id,name,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()
    # Existing owner capability is explicit starting fixture data, installed
    # BEFORE runner inspection; installer never grants it.
    w['boot'].execute('GRANT ingestion_barrier_releaser TO postgres WITH ADMIN TRUE, INHERIT FALSE, SET FALSE GRANTED BY provisioning_bootstrap')
    w['boot'].execute('REVOKE EXECUTE ON FUNCTION ingestion_register_disposable_catchup(jsonb) FROM ingestion_worker')
    fixture=prior['preparation']['provider_fixture']
    class Provider:
        calls=0;posts=0;puts=0;restore_lost=False;pending_reads=0
        service=copy.deepcopy(fixture['service']);env=copy.deepcopy(fixture['environment']);jobs=[]
        deployments=([dict(deploy=dict(id=item,status='deactivated',commit=dict(id='historic-revision'),
                        createdAt='2026-11-16T21:00:00Z',finishedAt='2026-11-16T21:01:00Z'))
                     for item in history_ids]
                     +[dict(deploy=dict(id='dep-synthetic',status='live',commit=dict(id=plan.BASE_RUNTIME),
                        createdAt='2026-11-17T22:26:23Z',finishedAt='2026-11-17T22:27:13Z'))])
        def close(self):pass
        def call(self,method,path='',body=None):
            self.calls+=1
            if method=='PATCH':
                self.service['branch']=body['branch'];self.service['serviceDetails']['envSpecificDetails'].update(body['serviceDetails']['envSpecificDetails'])
                return copy.deepcopy(self.service)
            if method=='POST' and path=='/resume':
                self.service['suspended']='not_suspended'
                next(item for item in self.deployments if item['deploy']['status']=='live')['deploy']['status']='deactivated'
                self.deployments.append(dict(deploy=dict(id='dep-corrected',status='live',commit=dict(id=plan.RUNTIME),createdAt='2026-11-17T23:45:00Z',finishedAt='2026-11-17T23:46:00Z')))
                return None
            if method=='POST' and path=='/suspend':self.service['suspended']='suspended';return None
            if method=='PUT':
                self.puts+=1;self.env={x['key']:x['value'] for x in body}
                if fault=='submission_restore' and self.jobs and self.env==fixture['environment'] and not self.restore_lost:
                    self.restore_lost=True;raise RuntimeError('DISPOSABLE_RESTORE_ACK_LOST')
                return []
            if method=='GET':
                if path=='':return copy.deepcopy(self.service)
                if path=='/env-vars?limit=100':return [{'envVar':dict(key=k,value=v)} for k,v in self.env.items()]
                if path=='/jobs?limit=100':return copy.deepcopy(self.jobs)
                if path=='/deploys?limit=100':
                    rows=copy.deepcopy(self.deployments)
                    if fault=='submission_restore' and any(x['deploy']['id']=='dep-corrected' for x in rows) and self.pending_reads==0:
                        self.pending_reads+=1;rows[-1]['deploy']['status']='build_in_progress';rows[-1]['deploy']['finishedAt']=None
                    return rows
                if path.startswith('/jobs/'):return copy.deepcopy(self.jobs[0]['job'])
            assert method=='POST' and path=='/jobs',(method,path)
            assert 'STOP15_JOB' in ja.reconcile(pinned,db,capacity50=True)[1]['intents']
            self.posts+=1;assert self.posts==1
            if fault=='missing_job':raise RuntimeError('DISPOSABLE_SUBMISSION_UNKNOWN')
            source_runtime(body['startCommand'])
            now=datetime.now(timezone.utc).isoformat()
            job=dict(id='job-'+'a'*20,serviceId='crn-d9sv93vavr4c73f98rb0',startCommand=body['startCommand'],status='succeeded',createdAt=now,startedAt=now,finishedAt=now)
            self.jobs=[dict(job=job)]
            if fault=='submission_restore':raise RuntimeError('DISPOSABLE_SUBMISSION_ACK_LOST')
            return copy.deepcopy(job)
    provider=Provider()
    def observation(op,b):
        return dict(version='FINITE_OPERATION_OBSERVATION_V1',operation=op,binding_sha256=hashlib.sha256(plan.canonical(b)).hexdigest(),service_id='crn-d9sv93vavr4c73f98rb0',observed_at=time.time(),env_groups=[],secret_files=[],inherited_credential_names=[],reviewed=True,no_current_work=True,other_activity_stopped=True,deployment_id='dep-corrected',revision=plan.RUNTIME,suspended=True)
    runner=run.Continuation(db,pinned,journal,state,runtime_root=os.environ['S4_TAMESIDE_RUNTIME_CHECKOUT'],frozen_root=os.environ['S4_BOLTON_PINNED_CHECKOUT'],api_factory=lambda:provider,observation=observation,approval_ref='https://github.com/maxrose26/PropertyAIgent/issues/214#issuecomment-6962672279',review_ref='https://github.com/maxrose26/PropertyAIgent/pull/227#issuecomment-6962521367',sleep=lambda _:None)
    # The retained synthetic manifest uses synthetic historical fingerprints;
    # exact equality is independently tested by the existing release SQL.
    actual_inspect=runner.inspect
    proposal_path=Path(plan.release_candidate.__file__).parents[2]/'docs/design/pa-tam001-transport/release-proposal.json'
    # manifest_from_readback receives original proposal but fixture prior hashes
    # are projected exactly as the existing recovery test does.
    runner.inspect()
    run.RELEASE_ROOT=str(root/'owner')
    DB.lose_journal=fault=='submission_restore'
    # Synthetic-data-only diagnostic: measure the exact frozen-serializer
    # projected normal state before its mandatory refusal. Do not print values.
    if os.environ.get('S4_STOP15_SIZE_DIAGNOSTIC')=='1':
        original_capacity=plan.capacity
        def capacity_with_sizes(journal,starting,projections):
            try:return original_capacity(journal,starting,projections)
            except Exception as exc:
                if str(exc)!='OWNER_CLEANUP_RESERVE_BYTE_BOUND':raise
                future=projections[0]
                ceiling=pinned.cleanup_reserve_policy()['normal_plaintext_ceiling']
                observed=pinned.state_size(future)
                parts=sorted(((k,len(pinned.canonical(v))) for k,v in future.items()),
                             key=lambda pair:pair[1],reverse=True)
                report=dict(normal_ceiling=ceiling,projected_normal_bytes=observed,
                            excess_bytes=observed-ceiling,starting_state_bytes=pinned.state_size(starting),
                            top_fields_bytes=parts[:20],field_count=len(parts),
                            values_disclosed=False,synthetic_only=True)
                raise AssertionError('STOP15_SIZE_ONLY_DIAGNOSTIC '+json.dumps(report,sort_keys=True)) from exc
        plan.capacity=capacity_with_sizes
    cap=importlib.import_module('_stop15_corrected_owner.tameside_journal_capacity')
    # Actual SQL commits with lost ACK, then its journal ACK fails before write.
    # A newly opened reader proves the retained intent and installed function;
    # resumption must append ACK without repeating SQL or changing row18.
    with pytest.raises(ValueError,match='STOP15_JOURNAL_ACK_UNKNOWN'):
        cap.upgrade(runner,source)
    assert DB.upgrade_calls==1 and DB.upgrade_ack_lost
    reopened,retained=ja.reconcile(pinned,db,capacity50=True)
    assert reopened.ordinal==19 and retained['capacity_upgrade']['state']=='INTENT'
    old_intent_bytes=pinned.state_size(retained)
    assert old_intent_bytes<=pinned.cleanup_reserve_policy()['normal_plaintext_ceiling']
    assert cap.observe(db,source)
    runner.journal=reopened;runner.state=retained
    runner.inspect()
    cap.upgrade(runner,source)
    assert runner.journal.ordinal==20 and DB.upgrade_calls==1
    cap.upgrade(runner,source)  # already acknowledged: read-only, no duplicate
    assert runner.journal.ordinal==20 and DB.upgrade_calls==1
    # Real function limits, each transaction rolled back (no synthetic row
    # consumes the immutable history or normal allowance).
    def writer_probe(period,run_id,previous,n,reason=None):
        with db.connection() as c:
            c.execute('BEGIN')
            try:
                def call():return c.execute('SELECT * FROM public.ingestion_intake_owner_state(%s,%s,%s,%s)',(period,run_id,previous,b'x'*n)).fetchone()
                if reason:
                    with pytest.raises(Exception,match=reason):call()
                else:assert len(bytes(call()[1]))==n
            finally:c.execute('ROLLBACK')
    writer_probe(ja.JOURNAL,ja.RUN,runner.journal.previous,51200)
    writer_probe(ja.JOURNAL,ja.RUN,runner.journal.previous,51201,'OWNER_STATE_VAULT_BOUND')
    writer_probe(original_journal.owner_period,original_journal.owner_run,original_journal.previous,32769,'OWNER_STATE_VAULT_BOUND')
    writer_probe('unapproved_owner','0'*32,'',51200,'OWNER_STATE_EXACT_PILOT')
    assert cap.observe(db,source)
    runner.bind()
    runner.replacement()
    runner.state=plan.read_journal(runner.journal)
    historical=runner.state['replacement_deployment']
    assert 'prior_deploy_ids' not in historical
    assert historical['prior_deploy_ids_ref']==dict(
        ordinal=18,checkpoint_sha256=plan.CHECKPOINT,count=len(history_ids),
        members_sha256=hashlib.sha256(pinned.canonical(history_ids)).hexdigest())
    assert len(runner.state['original_deploy_ids'])==78
    runner.prepared()
    capacity=copy.deepcopy(runner.state['continuation_capacity'])
    production_policy=copy.deepcopy(runner.state['policy'])
    policy=copy.deepcopy(production_policy);policy.update(test_evidence=True,route='DISPOSABLE',hostaddr=None)
    assert {k for k in policy if policy[k]!=production_policy[k]}=={'test_evidence','route','hostaddr'}
    as_of=datetime.fromtimestamp(runner.state['bound_at'],timezone.utc)
    actual=plan.release_candidate.render_campaign(as_of=as_of,period=plan.PERIOD,policy=production_policy,release_manifest_sha256=manifest['manifest_binding_sha256'])
    projected=plan.release_candidate.installed_campaign_sql(plan.PERIOD,policy,as_of)
    runner.files['campaign-install.sql']=runner.files['campaign-install.sql'].replace(actual.encode(),projected.encode())
    runner.state['policy']=policy
    runner.state['binding'].update(route='DISPOSABLE',hostaddr=None,owner_hostaddr=None,release_root=str(root),submission_intent_path=str(root/'submission.intent'))
    # Compile the actual corrected lifecycle with the same existing disposable
    # route projection; source-derived production verification is not relaxed.
    text=Path(access_mod.__file__).read_text().replace("==policy['route']=='POOLER'","==policy['route']=='DISPOSABLE'")
    scope={'__package__':access_mod.__package__};exec(compile(text,'disposable-access','exec'),scope)
    def get_access():
        inventory=access_mod.expected_functions(production_policy)
        inventory['ingestion_register_campaign_once']['sha256']=hashlib.sha256(projected.split('$campaign$')[1].encode()).hexdigest() if '$campaign$' in projected else inventory['ingestion_register_campaign_once']['sha256']
        # Use actual source-derived projected SQL bodies, not observed hash.
        from verification.ingestion_storage.operational_owner import Owner
        # Existing fixture reinstalls current disposable policy SQL; production
        # retains its old registrar. Derive this explicit fixture body from its
        # source compiler, never from the observed installed catalogue.
        inventory['ingestion_register_bolton_exception']['sha256']=hashlib.sha256(Owner.daily_intake_inventory()['ingestion_register_bolton_exception'].encode()).hexdigest()
        body={m[1]:m[3] for m in Owner.FUNCTION_PATTERN.finditer(projected)}['ingestion_register_campaign_once']
        inventory['ingestion_register_campaign_once']['sha256']=hashlib.sha256(body.encode()).hexdigest()
        return scope['lifecycle'](os.environ['S4_BOLTON_PINNED_CHECKOUT'],policy=policy,manifest=manifest,expected_inventory=inventory)
    runner.access=get_access();runner.io=access_mod.provider_io(os.environ['S4_BOLTON_PINNED_CHECKOUT'],runner.access)
    runner.io.handoff.__globals__['url']=lambda route,role,password:w['urls'][role]
    from verification.ingestion_storage import daily_intake_runtime as runtime,tameside_candidate as exe
    from tests.test_daily_intake_runtime import env_and_sources
    from tests.test_source_profiles import synthetic_tameside_source_from_owned_child
    env,sources=env_and_sources(w,root,count=1,catchup_window=plan.release_candidate.BATCH)
    child=root/'source-child';child.mkdir()
    audit=synthetic_tameside_source_from_owned_child(child,1,row=dict(council='tameside',semantics='RECEIVED',start='2026-09-15',end='2026-09-21'))
    (sources/'tameside.json').write_text(json.dumps(audit))
    result_root=root/'runtime-result';actual_runtime=runtime.main
    def source_runtime(command):
        with pytest.MonkeyPatch.context() as m:
            for k,v in env.items():m.setenv(k,v)
            for k in ('DATABASE_URL','INGESTION_ADMIN_DATABASE_URL','INGESTION_APPLICATION_DATABASE_URL','SUPABASE_SERVICE_ROLE_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','PROPERTYAIGENT_INTAKE_RENDER_API_KEY','GH_TOKEN','GITHUB_TOKEN'):m.delenv(k,raising=False)
            m.setenv('RENDER_SERVICE_ID','crn-d9sv93vavr4c73f98rb0');m.setenv('RENDER_GIT_COMMIT',plan.RUNTIME)
            def transport(argv):return actual_runtime(['--period',plan.PERIOD,'--output',str(result_root),'--disposable-sources',str(sources),'--disposable-archive',str(root/'archive')])
            m.setattr(runtime,'main',transport)
            argv=shlex.split(command);assert exe.main(argv[argv.index('verification.ingestion_storage.tameside_candidate')+1:])==0

    check=runner.installed
    checked=[False]
    def acl_refusals():
        assert check()
        if not checked[0]:
            checked[0]=True
            for sql in ('REVOKE EXECUTE ON FUNCTION ingestion_register_campaign_once(jsonb) FROM postgres',
                'REVOKE EXECUTE ON FUNCTION ingestion_register_campaign_once(jsonb) FROM ingestion_worker',
                'GRANT EXECUTE ON FUNCTION ingestion_register_campaign_once(jsonb) TO PUBLIC',
                'GRANT EXECUTE ON FUNCTION ingestion_register_campaign_once(jsonb) TO ingestion_effect_broker',
                'GRANT EXECUTE ON FUNCTION ingestion_register_campaign_once(jsonb) TO postgres WITH GRANT OPTION'):
                w['boot'].execute('BEGIN')
                try:
                    w['boot'].execute(sql)
                    with pytest.raises(Exception,match='CAMPAIGN_ACCESS_ISSUER_ACL'):runner.access.inventory(w['boot'])
                finally:w['boot'].execute('ROLLBACK')
        return True
    runner.installed=acl_refusals
    final_refusals=[0]
    actual_outcome=runner.outcome
    def readback():
        DB.raw_mode=True
        try:
            value=actual_outcome()
            if fault=='none':
                for field,bad in [('backend','POSTGRES_PILOT_V1'),('sha256','0'*64),('bytes',1),('run_id','0'*32),('name','final/events-before-publication.json')]:
                    publication=copy.deepcopy(value['publication']);publication[field]=bad
                    payload=dict(operation='intake_finish',period=plan.PERIOD,run_id=value['run_id'],status='RETAINED_AND_SCREENED',publication=publication,execution_binding=policy['execution_binding'])
                    with __import__('psycopg').connect(w['urls']['ingestion_worker_login'].replace('postgresql+psycopg://','postgresql://'),autocommit=True,prepare_threshold=None) as c:
                        with pytest.raises(Exception,match='INTAKE_DATABASE_EVIDENCE_NOT_VERIFIED'):c.execute('SELECT public.ingestion_register_campaign_once(%s::jsonb)',(json.dumps(payload),))
                    final_refusals[0]+=1
            return value
        finally:DB.raw_mode=False
    runner.outcome=readback
    closes=[0];close=runner.access.close
    def close_count(*a,**kw):
        closes[0]+=1;return close(*a,**kw)
    runner.access.close=close_count
    if fault=='submission_restore':
        with pytest.raises(RuntimeError,match='DISPOSABLE_RESTORE_ACK_LOST'):runner.run()
        prepared_files=runner.files
        reopened,retained=ja.reconcile(pinned,db,capacity50=True)
        assert cap.observe(db,source);reopened.capacity_verified=True
        runner=run.Continuation(db,pinned,reopened,retained,runtime_root=os.environ['S4_TAMESIDE_RUNTIME_CHECKOUT'],frozen_root=os.environ['S4_BOLTON_PINNED_CHECKOUT'],api_factory=lambda:provider,observation=observation,approval_ref=runner.approval_ref,review_ref=runner.review_ref,sleep=lambda _:None)
        runner.files=prepared_files  # retain exact prior package only to prove duplicate refusal
        runner.access=get_access()  # same explicit disposable source-derived inventory
        runner.io=access_mod.provider_io(runner.frozen_root,runner.access)
        actual_outcome=runner.outcome;runner.outcome=readback
        before=provider.puts
        runner.cleanup()
        assert provider.puts==before and closes[0]==1 and provider.pending_reads==1 and DB.journal_lost
        result=runner.outcome()
    elif fault=='missing_job':
        with pytest.raises(ValueError,match='STOP15_SUBMISSION_UNKNOWN'):runner.run()
        assert provider.posts==1 and runner.state['status']=='CONTAINMENT_REQUIRES_REVIEW'
        with pytest.raises(ValueError,match='STOP15_SUBMISSION_NO_RETRY'):runner.run()
        assert w['boot'].execute("SELECT bool_and(NOT rolcanlogin) FROM pg_roles WHERE rolname IN ('ingestion_worker_login','ingestion_effect_login')").fetchone()==(True,)
        assert w['boot'].execute("SELECT count(*) FROM pg_auth_members WHERE member IN ('ingestion_worker_login'::regrole,'ingestion_effect_login'::regrole)").fetchone()==(0,)
        return dict(status='UNKNOWN_SUBMISSION_CONTAINED_NO_RETRY',provider_posts=provider.posts,worker_logins=False,live_requests=0,original_history_preserved=all(row in w['boot'].execute('SELECT period,run_id,name,sha256 FROM ingestion_run_evidence').fetchall() for row in all_history))
    else:result=runner.run()
    assert DB.install_calls==1
    with pytest.raises(ValueError,match='STOP15_SUBMISSION_NO_RETRY'):runner.run()
    assert provider.posts==1 and runner.state['status']=='CLOSED'
    assert runner.journal.ordinal<=63 and runner.state['cleanup_reserve']['cleanup_writes']<=16
    assert provider.env==fixture['environment'] and provider.service==fixture['service']
    after=w['boot'].execute('SELECT period,run_id,name,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()
    assert all(row in after for row in all_history)
    assert w['boot'].execute("SELECT count(*) FROM pg_auth_members WHERE member IN ('ingestion_worker_login'::regrole,'ingestion_effect_login'::regrole)").fetchone()==(0,)
    assert w['boot'].execute("SELECT bool_and(NOT rolcanlogin) FROM pg_roles WHERE rolname IN ('ingestion_worker_login','ingestion_effect_login')").fetchone()==(True,)
    assert result['captures'][0]['record_count']==result['captures'][0]['screening_complete']==1
    measured=[]
    for name,body in w['boot'].execute("SELECT name,body FROM ingestion_run_evidence WHERE period=%s AND run_id=%s AND name>='owner/state-018' ORDER BY name",(ja.JOURNAL,ja.RUN)):
        decoded=runner.journal._vault(raw=bytes(body));ordinal=int(name[-3:])
        measured.append(dict(ordinal=ordinal,serialized_bytes=pinned.state_size(decoded),ciphertext_bytes=len(body),cleanup_writes=decoded['cleanup_reserve']['cleanup_writes']))
        if ordinal>20:
            maximum=max(capacity['cleanup_ciphertext_bytes'] if decoded['cleanup_reserve']['cleanup_writes'] else capacity['projected_ciphertext_bytes'])
            assert len(body)<=maximum,(ordinal,len(body),maximum)
    capacity['actual_saved_states']=measured
    capacity['actual_report_serialized_bytes']=len(plan.canonical(runner.state.get('continuation_capacity',{})))
    capacity['total_remaining_normal_projections']=2+capacity['projected_normal_writes']
    capacity['upgrade_normal_projections']=[dict(ordinal=m['ordinal'],ciphertext_bytes=m['ciphertext_bytes']) for m in measured if m['ordinal'] in (19,20)]
    assert capacity['total_remaining_normal_projections']==29
    return dict(status='SYNTHETIC_RELEASE_RUNTIME_READBACK_PASSED',period=plan.PERIOD,synthetic_listing_records=1,screening='COMPLETE',backlog_records=1,cleanup='CLOSED',live_requests=0,continuation='ACTUAL_STOP15_RUNNER',partial_start_ordinal=18,final_ordinal=runner.journal.ordinal,cleanup_writes=runner.state['cleanup_reserve']['cleanup_writes'],fault=fault,private_final_refusals=final_refusals[0],capacity=capacity,upgrade_sql_calls=DB.upgrade_calls,upgrade_ack_lost_reconciled=DB.upgrade_ack_lost,old_intent_plaintext_bytes=old_intent_bytes,worker_revision=plan.RUNTIME,provider_posts=provider.posts,original_history_preserved=True)
