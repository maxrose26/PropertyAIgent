"""STOP15 remaining owner sequence, including justified stopped replacement.

The CLI is deliberately inactive without exact amendment/REVIEW references.
It reuses the frozen Database, Journal, access lifecycle and provider transport.
"""
import argparse, ast, copy, hashlib, importlib, importlib.util, json, os, re, sys, time
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from . import tameside_stop15 as plan
from . import tameside_owner_access as access_module
from . import tameside_owner_journal as journal_module
from .tameside_owner_database import database_type
from .tameside_preparation import pinned_modules, original_checkpoint, installed_journal, require
from .tameside_package import PERIOD
from .tameside_candidate import EXPIRY


RELEASE_ROOT='/tmp/pa-tam002-stop15-01'

@contextmanager
def working_directory(path):
    before=Path.cwd();os.chdir(path)
    try:yield
    finally:os.chdir(before)


def worker_modules(root):
    plan.worker_command(root,'import json;print(json.dumps(True))',{})
    name='_stop15_pinned_worker'
    path=Path(root).resolve()/'verification/ingestion_storage'
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,path/'__init__.py',submodule_search_locations=[str(path)])
        mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    require(Path(sys.modules[name].__file__).resolve()==path/'__init__.py','STOP15_WORKER_IMPORT')
    return importlib.import_module(name+'.operational_owner'),importlib.import_module(name+'.tameside_candidate')


class Continuation:
    def __init__(self, db, pinned, journal, state, *, runtime_root, frozen_root,
                 api_factory, observation, approval_ref, review_ref, sleep=time.sleep):
        require(re.fullmatch(r'https://github.com/maxrose26/PropertyAIgent/issues/214#issuecomment-[0-9]+',approval_ref),'STOP15_APPROVAL_REF')
        require(re.fullmatch(r'https://github.com/maxrose26/PropertyAIgent/pull/227#issuecomment-[0-9]+',review_ref),'STOP15_REVIEW_REF')
        self.db,self.pinned,self.journal,self.state=db,pinned,journal,copy.deepcopy(state)
        self.runtime_root,self.frozen_root=Path(runtime_root),Path(frozen_root)
        self.api_factory,self.observation,self.sleep=api_factory,observation,sleep
        self.approval_ref,self.review_ref=approval_ref,review_ref
        self.files=None;self.access=None;self.io=None
        self.provider_calls=0;self.provider_bytes=0;self.provider_active=0.0

    def save(self, *, cleanup=False):
        wanted=copy.deepcopy(self.state)
        if cleanup:self.journal.cleanup_mode=True
        try:self.journal.save(wanted)
        except Exception:require(plan.read_journal(self.journal)==wanted,'STOP15_JOURNAL_ACK_UNKNOWN')
        require(plan.read_journal(self.journal)==wanted,'STOP15_JOURNAL_READBACK')
        self.state=wanted

    def phase(self):
        self.provider_calls=0;self.provider_bytes=0;self.provider_active=0.0

    def transport(self):
        runner=self
        class Transport:
            @property
            def calls(self):return runner.provider_calls
            def call(self,*args):return runner.api(*args)
            def close(self):pass
        return Transport()

    def api(self, method, path='', body=None):
        api=self.api_factory()
        started=time.monotonic()
        require(self.provider_calls<40 and self.provider_active<40,'STOP15_PROVIDER_PHASE_BOUND')
        self.provider_calls+=1
        try:
            value=api.call(method,path,body)
            self.provider_bytes+=len(plan.canonical(value))
            require(self.provider_bytes<=786432,'STOP15_PROVIDER_BYTES')
            return value
        finally:
            self.provider_active+=time.monotonic()-started;api.close()
            require(self.provider_active<=40,'STOP15_PROVIDER_PHASE_BOUND')

    def read(self, fn):
        import signal
        with (nullcontext() if signal.getitimer(signal.ITIMER_REAL)[0] else self.pinned.envelope()),self.db.connection() as c:
            c.execute('BEGIN READ ONLY')
            try:return fn(c)
            finally:c.execute('ROLLBACK')

    def provider(self):
        s=self.api('GET');env=self.pinned.env_values(self.api('GET','/env-vars?limit=100'))
        jobs=self.pinned.complete_inventory(self.api('GET','/jobs?limit=100'),'job')
        deps=self.pinned.complete_inventory(self.api('GET','/deploys?limit=100'),'deploy')
        require(s.get('suspended')=='suspended' and self.pinned.service_guard(s)==self.state['original_guard']
            and env==self.state['original_environment'],'STOP15_PROVIDER_RESTORATION')
        live=[d for d in deps if d['status']=='live']
        require(len(live)==1 and live[0]['id']==self.state.get('deployment',plan.DEPLOYMENT) and live[0]['commit']['id']==(plan.RUNTIME if self.state.get('replacement_deployment') else plan.BASE_RUNTIME)
            and max(deps,key=lambda d:d['createdAt'])['id']==self.state.get('deployment',plan.DEPLOYMENT),'STOP15_DEPLOYMENT')
        return s,env,jobs,deps

    def inspect(self):
        """Dated receipts do not substitute for these current independent reads."""
        self.phase()
        current=plan.read_journal(self.journal)
        plan.retained_start(current,ordinal=self.journal.ordinal,sha256=self.journal.previous)
        require(current==self.state,'STOP15_JOURNAL_DRIFT')
        original=original_checkpoint(self.pinned,self.db)
        require(original['original_environment']==current['original_environment']
            and original['original_service']==current['original_service'],'STOP15_ORIGINAL_BASELINE')
        _,_,source=pinned_modules(self.frozen_root)
        require(installed_journal(self.db,source),'STOP15_NAMESPACE')
        proposal=json.loads((Path(__file__).parent.parent.parent/'docs/design/pa-tam001-transport/release-proposal.json').read_text())
        def observe(c):
            manifest=plan.release_candidate.manifest_from_readback(c,proposal,
                operational_review_ref='https://github.com/maxrose26/PropertyAIgent/pull/227#issuecomment-6962521367')
            require(manifest==current['manifest'],'STOP15_HISTORY_OR_CONTROLLER_DRIFT')
            ctl=c.execute("SELECT outcome::jsonb FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
            require(ctl.get('hard_stop_generation')==15 and ctl.get('global_stop')=={'reason':'DAILY_INTAKE_SHARED_FAILURE'}
                and ctl.get('manual_stop')=='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP'
                and not ctl.get('intake_run') and PERIOD not in ctl.get('intake_periods',{}),'STOP15_CURRENT_STOP')
            require(c.execute("SELECT to_regprocedure('public.ingestion_register_campaign_once(jsonb)')").fetchone()==(None,),'STOP15_CAMPAIGN_ALREADY_PRESENT')
            require(c.execute("SELECT count(*) FROM ingestion_work_items WHERE state IN ('CLAIMED','PERSISTENCE_UNCERTAIN') OR phase IN ('SOURCE_INTENT','WRITE_INTENT')").fetchone()==(0,),'STOP15_ACTIVE_WORK')
            require(c.execute("SELECT count(*) FROM pg_stat_activity WHERE usename IN ('ingestion_worker_login','ingestion_effect_login','ingestion_recovery_login','ingestion_application_login')").fetchone()==(0,),'STOP15_SESSIONS')
            require(c.execute("SELECT bool_and(NOT rolcanlogin) FROM pg_roles WHERE rolname IN ('ingestion_worker_login','ingestion_effect_login')").fetchone()==(True,),'STOP15_LOGIN')
            # Existing admin-only issuer capability is a prerequisite, never
            # manufactured by this continuation or a supplemental fixture grant.
            require(c.execute("SELECT EXISTS(SELECT 1 FROM pg_auth_members WHERE roleid='ingestion_barrier_releaser'::regrole AND member=current_user::regrole AND admin_option AND NOT inherit_option AND NOT set_option),pg_has_role(current_user,'ingestion_barrier_releaser','USAGE'),pg_has_role(current_user,'ingestion_barrier_releaser','SET')").fetchone()==(True,False,False),'STOP15_ISSUER_ADMIN_CAPABILITY')
            from app.ingestion.private_evidence import READ_FUNCTION_SHA256,WRITE_FUNCTION_SHA256
            require(c.execute("SELECT proname,encode(sha256(convert_to(prosrc,'UTF8')),'hex') FROM pg_proc WHERE oid IN ('ingestion_intake_evidence_read(text,text,text)'::regprocedure,'ingestion_intake_evidence_write(text,text,text,bytea)'::regprocedure) ORDER BY 1").fetchall()==[('ingestion_intake_evidence_read',READ_FUNCTION_SHA256),('ingestion_intake_evidence_write',WRITE_FUNCTION_SHA256)],'STOP15_PRIVATE_WRITER')
            return manifest
        manifest=self.read(observe);self.provider()
        return original,source,manifest

    def bind(self, bound_at=None):
        original,source,manifest=self.inspect()
        if bound_at is None:bound_at=time.time()
        require(time.time()-5<=bound_at<=time.time()+5 and bound_at+2100<=EXPIRY,'STOP15_FRESH_FINITE_TIME')
        self.files=plan.compile_remaining(self.runtime_root,manifest,bound_at=bound_at,owner_journal_source=source)
        policy=json.loads(self.files['policy.json'])
        # Immutable row18 remains the archive; do not duplicate its obsolete
        # policy/manifest/index and consume the original cleanup byte reserve.
        self.state['elapsed_package']=dict(ordinal=18,sha256=plan.CHECKPOINT,manifest_sha256=plan.OLD_MANIFEST,package_sha256=plan.OLD_INDEX,bound_at=plan.OLD_BOUND)
        self.state.update(policy=policy,manifest=manifest,bound_at=bound_at,
            package_index=json.loads(self.files['continuation.json']),status='STOP15_CONTINUATION_BOUND',
            continuation=dict(approval_ref=self.approval_ref,review_ref=self.review_ref))
        self.access=access_module.lifecycle(self.frozen_root,policy=policy,manifest=manifest)
        self.io=access_module.provider_io(self.frozen_root,self.access)
        stable=original['stable_credentials']
        b=dict(version='FINITE_INTAKE_OWNER_V1',period=PERIOD,route=policy['route'],hostaddr=policy['hostaddr'],owner_hostaddr=policy['hostaddr'],
            execution_binding=policy['execution_binding'],accepted_stop=policy['expected_stop'],evidence_backend='POSTGRES_PILOT_V1',
            credential_policy='STABLE_RESTRICTED_V1',credential_verifier_sha256=stable['verifier_sha256'],runtime_deadline=policy['expires_at'],
            valid_until=policy['expires_at']+185,render_config_sha256=self.state['original_guard'],retained_deployment=plan.DEPLOYMENT,
            timing_policy=dict(version='SEPARATE_EXPIRY_V2_RESERVE',bound_at=bound_at),release_root=RELEASE_ROOT,submission_intent_path=str(Path(RELEASE_ROOT)/'submission.intent'))
        self.state['binding']=b
        self.passwords=stable['passwords']
        # Caller must prove full projected remaining-state capacity before this
        # binding is durable. This is intentionally a fail-closed prerequisite.
        self.state['continuation_capacity']=self.capacity_projection()
        self.save()
        Path(b['release_root']).mkdir(mode=0o700,exist_ok=False)

    def replacement(self):
        from .stop15_replacement import operation
        op=operation(self)
        try:
            for _ in range(10):
                try:
                    with self.pinned.envelope():op.prepare()
                    break
                except ValueError as exc:
                    if str(exc)!='PREPARATION_EFFECT_UNKNOWN:STOP15_REPLACEMENT_ONE_RESUME_BUILD':raise
                    self.sleep(20)
            else:raise ValueError('STOP15_REPLACEMENT_BUILD_PENDING')
            self.state=plan.read_journal(op.journal);self.journal=op.journal
            require(self.state['status']=='STOPPED_BUILD_READY','STOP15_REPLACEMENT_UNKNOWN')
            self.phase();self.provider()
            self.state['binding']['retained_deployment']=self.state['deployment']
            require(time.time()<self.state['bound_at']+600 and time.time()+1145<self.state['binding']['valid_until'],'STOP15_POST_BUILD_TIME')
            self.save()
        except BaseException:
            self.state=plan.read_journal(op.journal);self.journal=op.journal
            # Existing containment inspects terminal deployments before restore;
            # a pending deployment stays UNKNOWN and must be inspected, not resumed.
            self.phase();op.contain();self.state=plan.read_journal(op.journal)
            raise

    def prepared(self):
        """Reopen the committed preparation; never renew its binding/deploy."""
        require(self.state.get('status')=='STOPPED_BUILD_READY' and not self.state.get('access') and not any(k.startswith('STOP15_') and not k.startswith('STOP15_REPLACEMENT_') for k in self.state['intents']),'STOP15_PREPARED_ONLY')
        require(self.state['continuation']==dict(approval_ref=self.approval_ref,review_ref=self.review_ref),'STOP15_ACCEPTANCE_DRIFT')
        require(time.time()<self.state['bound_at']+600 and time.time()+1145<self.state['binding']['valid_until'],'STOP15_PREPARED_TIME')
        original=original_checkpoint(self.pinned,self.db)
        _,_,source=pinned_modules(self.frozen_root)
        self.files=plan.compile_remaining(self.runtime_root,self.state['manifest'],bound_at=self.state['bound_at'],owner_journal_source=source)
        require(json.loads(self.files['continuation.json'])==self.state['package_index'],'STOP15_PREPARED_ARTIFACT_DRIFT')
        require(self.state['binding']['retained_deployment']==self.state['deployment'],'STOP15_PREPARED_DEPLOYMENT')
        self.phase();self.provider()
        self.access=access_module.lifecycle(self.frozen_root,policy=self.state['policy'],manifest=self.state['manifest'])
        self.io=access_module.provider_io(self.frozen_root,self.access)
        self.passwords=original['stable_credentials']['passwords']

    def capacity_projection(self):
        # Actual retained private fields and existing Journal codec. Conservative
        # remaining metadata projections; runtime saves enforce the same limits.
        from .restricted_route import url
        def baseline(c):
            settings=dict(c.execute("SELECT rolname,coalesce(rolconfig,ARRAY[]::text[]) FROM pg_roles WHERE rolname IN ('ingestion_worker_login','ingestion_effect_login') ORDER BY 1").fetchall())
            members=c.execute("SELECT r.rolname,m.rolname,g.rolname,a.admin_option,a.inherit_option,a.set_option FROM pg_auth_members a JOIN pg_roles r ON r.oid=a.roleid JOIN pg_roles m ON m.oid=a.member JOIN pg_roles g ON g.oid=a.grantor WHERE m.rolname IN ('ingestion_worker_login','ingestion_effect_login') ORDER BY 1,2,3").fetchall()
            return settings,members
        settings,members=self.read(baseline)
        projected=copy.deepcopy(self.state)
        expected={k:v for k,v in self.state['original_environment'].items() if k in ('PYTHONUNBUFFERED','LANG','TZ','OPENBLAS_NUM_THREADS')}
        for role,key in [('ingestion_worker_login','INGESTION_WORKER_DATABASE_URL'),('ingestion_effect_login','INGESTION_EFFECT_DATABASE_URL')]:
            expected[key]=url(self.state['binding']['route'],role,self.passwords[role])
        projected['access']=dict(version='FINITE_INTAKE_ACCESS_STATE_V1',binding=self.state['binding'],state='ACTIVATION_ACKNOWLEDGED',prior_settings=settings,original_memberships=[list(x) for x in members],passwords=self.passwords,
            render=dict(original=self.state['original_environment'],expected=expected,guard=self.state['original_guard'],state='PUT_ACKNOWLEDGED',publication_token=None,publication_state='NOT_REQUESTED',mapped_at=9999999999.999998,handoff_observation_sha256='f'*64,submission_state='SUBMISSION_INTENT_NO_RETRY'))
        for name in ('CAMPAIGN','RELEASE','PERIOD','JOB'):
            projected['intents']['STOP15_'+name]=dict(state='ACKNOWLEDGED',sql_sha256='f'*64,command_sha256='f'*64)
        projected['replacement_deployment']=dict(prior_revision=plan.BASE_RUNTIME,prior_deployment=plan.DEPLOYMENT,prior_deploy_ids=self.state['original_deploy_ids'],revision=plan.RUNTIME)
        projected['original_deploy_ids']=[d['id'] for d in self.provider()[3]]
        for name in ('BUILD_ENVIRONMENT','BUILD_CONFIGURATION','ONE_RESUME_BUILD','RESUSPEND','RESTORE_BUILD_CONFIGURATION','RESTORE_BUILD_ENVIRONMENT'):
            projected['intents']['STOP15_REPLACEMENT_'+name]=dict(state='ACKNOWLEDGED',at=9999999999.999998)
        projected['job']=dict(id='job-'+'z'*20,serviceId='crn-d9sv93vavr4c73f98rb0',status='succeeded',createdAt='2026-11-18T19:35:00.000000Z',startedAt='2026-11-18T19:35:00.000000Z',finishedAt='2026-11-18T19:50:00.000000Z')
        projected['job_terminal']=copy.deepcopy(projected['job'])
        # Bound the stored outcome summary separately; raw evidence stays in DB.
        projected['independent_result']={'bounded_projection':''.join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(16))}
        projected['continuation_capacity']={'projection':'x'*1024}
        proof=plan.capacity(self.journal,self.state,[copy.deepcopy(projected) for _ in range(29)])
        probe=copy.copy(self.journal);probe.state=copy.deepcopy(projected);probe.ordinal=47;probe.cleanup_mode=True
        for key,n in self.pinned.CLEANUP_RECORD_LIMITS.items():projected[key]='x'*(n-2)
        sizes=[]
        for _ in range(16):
            v=copy.deepcopy(projected);sizes.append(probe.save(v,validate_only=True));probe.ordinal+=1;probe.state=v;projected=v
        proof.update(complete_projection_verified=True,cleanup_ciphertext_bytes=sizes,projected_last_cleanup_ordinal=probe.ordinal)
        return proof

    def outcome(self):
        # Reuse the exact pinned finalisation algorithm with only its former
        # two-council expectation narrowed to this sole Tameside campaign.
        path=self.frozen_root/'verification/ingestion_storage/intake_owner.py'
        source=path.read_text()
        require(hashlib.sha256(source.encode()).hexdigest()==access_module.SOURCE_SHA,'STOP15_FINALISATION_PIN')
        tree=ast.parse(source);node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='finalisation')
        code=ast.get_source_segment(source,node)
        require(code.count("expected_councils={'tameside','manchester'}")==1,'STOP15_FINALISATION_ANCHOR')
        code=code.replace("expected_councils={'tameside','manchester'}","expected_councils={'tameside'}").replace("len(records) <= 60","len(records) <= 30").replace("council=='manchester' and receipt.get('explicit_zero')", "council=='tameside' and receipt.get('explicit_zero')")
        # The deployed private archive contract is distinct from the frozen
        # SQL writer acknowledgement. Keep exact names/shape and verify bytes
        # separately below; never relabel a private receipt as a SQL receipt.
        code=code.replace('from .database_evidence import validate_descriptor,canonical','')
        code=code.replace("archive.get('path','')", "archive.get('path',evidence_path(archive))")
        def evidence_path(v):
            return f"docs/design/ingestion-operational-execution-daily-intake/{v.get('period')}/{v.get('run_id')}/{v.get('name')}"
        def descriptor(v):
            fields={'backend','period','run_id','name','sha256','bytes','readback_verified'}
            require(type(v) is dict and set(v) in (fields,fields|{'path'}) and v.get('backend')=='PRIVATE_POSTGRES_V1','STOP15_PRIVATE_DESCRIPTOR')
            require(v.get('period')==self.state['policy']['period'] if 'period' in self.state['policy'] else v.get('period')==PERIOD,'STOP15_PRIVATE_PERIOD')
            require(re.fullmatch('[a-f0-9]{32}',v.get('run_id','')) and re.fullmatch('[a-f0-9]{64}',v.get('sha256','')) and v.get('readback_verified') is True,'STOP15_PRIVATE_IDENTITY')
            require(v.get('name') in ('capture-1/source.json','capture-2/source.json','final/result-before-publication.json','final/events-before-publication.json') and type(v.get('bytes')) is int and 0<v['bytes']<=(524288 if v['name'].startswith('capture-') else 2097152),'STOP15_PRIVATE_SIZE')
            require('path' not in v or v['path']==evidence_path(v),'STOP15_PRIVATE_PATH')
            return v
        frozen=importlib.import_module(self.pinned.__package__+'.intake_owner')
        scope=dict(vars(frozen),validate_binding=self.access.validate_binding,validate_descriptor=descriptor,evidence_path=evidence_path)
        exec(compile(code,str(path)+'[single-tameside]','exec'),scope)
        with self.db.connection() as c:
            c.execute('BEGIN READ ONLY')
            try:run=c.execute("SELECT outcome::jsonb->'intake_run' FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
            finally:c.execute('ROLLBACK')
            value=scope['finalisation'](c,self.state['binding'],dict(run_id=(run or {}).get('id'),publication=(run or {}).get('publication')))
        from sqlalchemy import create_engine,text
        from sqlalchemy.pool import NullPool
        from app.ingestion.sql_ledger import SQLLedger
        from app.ingestion.daily_intake import backlog_page
        from app.ingestion.listing_screening import ScreeningRule,RULE_V3
        current=[];prior=[];after=None
        with self.db.connection() as raw:
            engine=create_engine('postgresql+psycopg://',creator=lambda:raw,poolclass=NullPool)
            try:
                with engine.connect() as connection:
                    connection.execute(text('BEGIN READ ONLY'))
                    try:
                        ledger=SQLLedger(engine,owner='required_once',authority='',bindings={})
                        for _ in range(10):
                            page=backlog_page(ledger,['tameside'],[self.state['policy']['councils']['tameside']['contract']],ScreeningRule(RULE_V3,unit_threshold=10,link_related=False),after=after,connection=connection)
                            for record in page['records']:
                                (current if record['archive']['period']==PERIOD else prior).append(record)
                            if not page['more']:break
                            require(page['next_cursor']!=after,'STOP15_BACKLOG_CURSOR');after=page['next_cursor']
                        else:raise ValueError('STOP15_BACKLOG_COVERAGE_BOUND')
                    finally:connection.execute(text('ROLLBACK'))
            finally:engine.dispose()
        n=sum(x['record_count'] for x in value['captures'])
        require(len(current)==n and all(x['screening_state']=='COMPLETE' for x in current),'STOP15_BACKLOG_READBACK')
        from collections import Counter
        outcomes=dict(Counter(x['screening_outcome'] if x['screening_outcome'] is not None else 'UNKNOWN' for x in current))
        known={x['reference'] for x in prior}
        value.update(coverage=dict(plan.release_candidate.BATCH,status='COMPLETE_CAPTURE_READ_BACK'),screening_outcomes=outcomes,backlog_records=len(current),newly_retained_unique_references='UNPROVEN_WITHOUT_PRIOR_RETAINED_CENSUS',prior_backlog_overlap=sum(x['reference'] in known for x in current),updates='NOT_INFERRED_FROM_RECAPTURE',qualification='NOT_CONNECTED',saved_facts='NOT_CONNECTED')
        require(len(plan.canonical(value))<=4096,'STOP15_OUTCOME_SUMMARY_BOUND')
        return value

    def installed(self):
        def check(c):
            self.access.inventory(c)
            require(c.execute("SELECT pg_has_role(current_user,'ingestion_storage_owner','USAGE'),pg_has_role(current_user,'ingestion_storage_owner','SET'),has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone()==(False,False,False),'STOP15_INSTALL_PRIVILEGES')
            return True
        return self.read(check)

    def released(self):
        def check(c):
            ctl=c.execute("SELECT outcome::jsonb FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
            return all(ctl.get(k)==v for k,v in self.state['policy']['expected_stop'].items()) and ctl.get('owner_shared_stop_release',{}).get('manifest_binding_sha256')==self.state['manifest']['manifest_binding_sha256']
        return self.read(check)

    def register(self):
        """Run registration from the exact corrected worker checkout."""
        name='STOP15_PERIOD';policy=self.state['policy']
        def observed():
            def check(c):
                ctl=c.execute("SELECT outcome::jsonb FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
                value=ctl.get('intake_periods',{}).get(PERIOD,{})
                return {k:v for k,v in value.items() if k not in ('days','registered_at')}==policy
            return self.read(check)
        if name in self.state['intents']:
            require(observed(),'STOP15_PERIOD_UNKNOWN');return
        self.state['intents'][name]=dict(state='INTENT');self.save()
        owner_module,exe=worker_modules(self.runtime_root)
        try:
            with self.pinned.envelope(),working_directory(self.runtime_root),self.db.connection() as c:
                owner=owner_module.Owner(lambda:c,lambda *_:None,lambda:None,identity='postgres',
                    expiry=datetime.fromtimestamp(policy['expires_at'],timezone.utc),bindings=policy['execution_binding'])
                with exe.enabled(policy):owner.register_historical_campaign_period(PERIOD,policy,as_of=datetime.fromtimestamp(self.state['bound_at'],timezone.utc))
        except Exception:require(observed(),'STOP15_PERIOD_UNKNOWN')
        require(observed(),'STOP15_PERIOD_READBACK')
        self.state['intents'][name]['state']='ACKNOWLEDGED'  # persisted with next access intent; re-entry observes registration

    def access_save(self,value):
        self.state['access']=copy.deepcopy(value);self.save(cleanup=value.get('state') in ('ACCESS_DISABLED_ACKNOWLEDGED','DATABASE_CLOSURE_ACKNOWLEDGED') or getattr(self.journal,'cleanup_mode',False))

    def cleanup(self):
        require(self.access is not None,'STOP15_CLEANUP_CONTEXT_REQUIRED')
        self.phase()
        self.journal.cleanup_mode=True
        if self.state.get('access'):
            if self.state['access'].get('state')!='DATABASE_CLOSURE_ACKNOWLEDGED':
                with self.pinned.envelope(),self.db.connection() as c:self.access.close(c,self.state['access'],self.access_save)
            if self.state['access'].get('render'):
                api=self.transport()
                try:
                    r=self.state['access']['render']
                    if r.get('state')=='RESTORE_INTENT_NO_RETRY':
                        require(self.pinned.env_values(api.call('GET','/env-vars?limit=100'))==r['original'] and self.pinned.service_guard(api.call('GET'))==r['guard'],'STOP15_RESTORE_UNKNOWN')
                        r['state']='RESTORATION_VERIFIED_BY_READBACK';self.access_save(self.state['access'])
                    elif r.get('state') not in ('RESTORATION_ACKNOWLEDGED','RESTORATION_VERIFIED_BY_READBACK'):
                        if r.get('state')=='PUT_INTENT_NO_RETRY':self.io.reconcile_handoff(api,self.state['access'],self.access_save)
                        if 'STOP15_JOB' in self.state['intents'] and not self.state.get('job'):
                            jobs=api.call('GET','/jobs?limit=100')
                            require(isinstance(jobs,list) and len(jobs)<100,'STOP15_JOB_INVENTORY')
                            matches=[x.get('job',x) for x in jobs if hashlib.sha256(x.get('job',x).get('startCommand','').encode()).hexdigest()==self.state['intents']['STOP15_JOB']['command_sha256']]
                            require(len(matches)==1,'STOP15_SUBMISSION_UNKNOWN')
                            self.state['job']={k:matches[0].get(k) for k in ('id','serviceId','status','createdAt','startedAt','finishedAt')};self.save(cleanup=True)
                        if r.get('reconciliation')=='ORIGINAL':
                            r['state']='RESTORATION_VERIFIED_BY_READBACK';self.access_save(self.state['access'])
                        else:self.io.restore_handoff(api,self.state['access'],self.access_save,self.state.get('job',{}).get('id'))
                finally:api.close()
        self.provider()
        def closed(c):
            roles=c.execute("SELECT rolname,rolcanlogin,encode(sha256(convert_to(rolpassword,'UTF8')),'hex') FROM pg_authid WHERE rolname IN ('ingestion_worker_login','ingestion_effect_login') ORDER BY 1").fetchall()
            require(len(roles)==2 and all(not x[1] and x[2]==self.state['binding']['credential_verifier_sha256'][x[0]] for x in roles),'STOP15_CLOSURE_LOGIN_VERIFIER')
            require(c.execute("SELECT count(*) FROM pg_auth_members WHERE member IN ('ingestion_worker_login'::regrole,'ingestion_effect_login'::regrole)").fetchone()==(0,),'STOP15_CLOSURE_MEMBERSHIPS')
            require(c.execute("SELECT count(*) FROM pg_stat_activity WHERE usename IN ('ingestion_worker_login','ingestion_effect_login')").fetchone()==(0,),'STOP15_CLOSURE_SESSIONS')
            require(c.execute("SELECT pg_has_role(current_user,'ingestion_storage_owner','USAGE'),pg_has_role(current_user,'ingestion_storage_owner','SET'),pg_has_role(current_user,'ingestion_barrier_releaser','USAGE'),pg_has_role(current_user,'ingestion_barrier_releaser','SET'),has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone()==(False,False,False,False,False),'STOP15_CLOSURE_TEMPORARY_PRIVILEGES')
            ctl=c.execute("SELECT outcome::jsonb FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
            grants=[g for g in ctl.get('grants',{}).values() if g.get('intake_period')==PERIOD]
            require(len(grants)<=4 and all(g.get('expires_at')==0 for g in grants),'STOP15_CLOSURE_AUTHORITIES')
            if self.state.get('access'):
                settings=dict(c.execute("SELECT rolname,coalesce(rolconfig,ARRAY[]::text[]) FROM pg_roles WHERE rolname IN ('ingestion_worker_login','ingestion_effect_login') ORDER BY 1").fetchall())
                require({k:sorted(v) for k,v in settings.items()}=={k:sorted(v) for k,v in self.state['access']['prior_settings'].items()},'STOP15_CLOSURE_SETTINGS')
            return dict(status='INDEPENDENTLY_VERIFIED',sessions=0,access='CLOSED',settings='RESTORED',stop_generation=ctl.get('hard_stop_generation'))
        self.state['closure_verification']=self.read(closed)
        self.state['status']='CLOSED';self.save(cleanup=True)

    def run(self):
        require(self.files is not None,'STOP15_PACKAGE_NOT_BOUND')
        require('STOP15_JOB' not in self.state['intents'],'STOP15_SUBMISSION_NO_RETRY')
        try:
            for name,file,observe in [('CAMPAIGN','campaign-install.sql',self.installed),('RELEASE','conditional-release.sql',self.released)]:
                with self.pinned.envelope():plan.one_sql(self.db,self.journal,self.state,name=name,sql=self.files[file].decode(),observe=observe,defer_ack=True)
            self.register()
            with self.pinned.envelope(),self.db.connection() as c:
                prepared=self.access.prepare_activation(c,self.state['binding'],stable_credentials=self.passwords)
                self.access.activate(c,self.state['binding'],self.access_save,prepared=prepared)
            self.phase();api=self.transport()
            try:
                self.io.handoff(api,self.state['access'],self.access_save,None,observation=self.observation('HANDOFF',self.state['binding']))
                self.io.submission_check(api,self.state['access'],self.access_save,self.observation('SUBMISSION',self.state['binding']))
            finally:api.close()
            require('STOP15_JOB' not in self.state['intents'],'STOP15_SUBMISSION_NO_RETRY')
            command=self.files['job-command.txt'].decode()
            self.state['intents']['STOP15_JOB']=dict(state='INTENT',command_sha256=hashlib.sha256(command.encode()).hexdigest());self.save()
            self.phase()
            job=self.api('POST','/jobs',{'startCommand':command})
            require(job.get('serviceId')=='crn-d9sv93vavr4c73f98rb0' and job.get('startCommand')==command and re.fullmatch('job-[a-z0-9]{20}',job.get('id','')),'STOP15_SUBMISSION_UNKNOWN')
            self.state['job']={k:job.get(k) for k in ('id','serviceId','status','createdAt','startedAt','finishedAt')};self.state['intents']['STOP15_JOB']['state']='ACKNOWLEDGED';self.save()
            for _ in range(32):
                self.sleep(30);job=self.api('GET','/jobs/'+job['id'])
                if job.get('status') in ('succeeded','failed','canceled') and job.get('finishedAt'):break
            self.state['job_terminal']={k:job.get(k) for k in ('id','serviceId','status','createdAt','startedAt','finishedAt')};self.save()
            require(job.get('status')=='succeeded' and job.get('finishedAt'),'STOP15_JOB_NOT_SUCCESSFUL')
            result=self.outcome()
            self.state['independent_result']=dict(status=result['status'],run_id=result['run_id'],sha256=hashlib.sha256(plan.canonical(result)).hexdigest(),retained=sum(x['record_count'] for x in result['captures']),screened=sum(x['screening_complete'] for x in result['captures']),screening_outcomes=result['screening_outcomes'],backlog=result['backlog_records'],new_unique=result['newly_retained_unique_references'],qualification='NOT_CONNECTED',saved_facts='NOT_CONNECTED')
            require(len(plan.canonical(self.state['independent_result']))<=1024,'STOP15_JOURNAL_OUTCOME_BOUND')
            self.save()
            return result
        except BaseException as exc:
            self.state=plan.read_journal(self.journal)
            if 'first_failure' not in self.state:
                self.state['first_failure']=self.pinned.bounded_failure(exc,'RUN')
                self.save(cleanup=True)
            raise
        finally:
            try:self.cleanup()
            except BaseException as cleanup_error:
                self.state=plan.read_journal(self.journal)
                self.state['closure_failure']=self.pinned.bounded_failure(cleanup_error,'CLEANUP')
                self.state['status']='CONTAINMENT_REQUIRES_REVIEW';self.save(cleanup=True)
                raise


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--action',choices=('inspect','prepare','run','cleanup'),required=True)
    p.add_argument('--runtime-root',required=True);p.add_argument('--frozen-root',required=True)
    p.add_argument('--approval-ref',required=True);p.add_argument('--review-ref',required=True)
    p.add_argument('--observation-file',required=True)
    args=p.parse_args(argv)
    frozen,_,_=pinned_modules(args.frozen_root)
    db=database_type(args.frozen_root)()
    journal,state=journal_module.reconcile(frozen,db)
    def observation(operation,binding):
        # Existing trusted provider observation, not evidence inferred from DB
        # sessions. Must be freshly completed by the existing owner route.
        path=Path(args.observation_file)
        require(path.stat().st_size<=8192,'STOP15_PROVIDER_OBSERVATION_BOUND')
        value=json.loads(path.read_text())
        require(value.get('kind')=='VERIFIED_EXISTING_OWNER_PROVIDER_BOUNDARY' and value.get('source_ref'),'STOP15_PROVIDER_OBSERVATIONS')
        result={k:v for k,v in value.items() if k not in ('kind','source_ref')}
        result.update(version='FINITE_OPERATION_OBSERVATION_V1',operation=operation,binding_sha256=hashlib.sha256(plan.canonical(binding)).hexdigest())
        io=access_module.provider_io(args.frozen_root,access_module.lifecycle(args.frozen_root,policy=runner.state['policy'],manifest=runner.state['manifest']))
        return io.operation_observation(binding,result,operation)
    runner=Continuation(db,frozen,journal,state,runtime_root=args.runtime_root,frozen_root=args.frozen_root,
        api_factory=lambda:frozen.Render(os.environ['PROPERTYAIGENT_INTAKE_RENDER_API_KEY']),observation=observation,
        approval_ref=args.approval_ref,review_ref=args.review_ref)
    if args.action=='inspect':
        if state.get('continuation'):
            def current(c):
                ctl=c.execute("SELECT outcome::jsonb FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
                roles=c.execute("SELECT rolname,rolcanlogin FROM pg_roles WHERE rolname IN ('ingestion_worker_login','ingestion_effect_login') ORDER BY 1").fetchall()
                sessions=c.execute("SELECT count(*) FROM pg_stat_activity WHERE usename IN ('ingestion_worker_login','ingestion_effect_login')").fetchone()[0]
                return dict(stop={k:ctl.get(k) for k in ('global_stop','manual_stop','last_hard_stop','hard_stop_generation')},roles=roles,sessions=sessions,run_state=(ctl.get('intake_run') or {}).get('state'))
            print(json.dumps(dict(status='CONTINUATION_INSPECTED_READ_ONLY',ordinal=journal.ordinal,sha256=journal.previous,intents={k:v['state'] for k,v in state['intents'].items()},checkpoint_state=state.get('status'),first_failure=state.get('first_failure'),closure_failure=state.get('closure_failure'),closure_verification=state.get('closure_verification'),independent_result=state.get('independent_result'),database=runner.read(current))))
        else:
            runner.inspect();print(json.dumps(dict(status='STOP15_RECONCILED_READ_ONLY',ordinal=journal.ordinal,sha256=journal.previous)))
    elif args.action=='cleanup':
        if not state.get('access') and state.get('replacement_deployment') and state.get('status')!='STOPPED_BUILD_READY':
            from .stop15_replacement import operation
            op=operation(runner);op.contain();print(json.dumps(dict(status=op.state['status'])));return
        runner.access=access_module.lifecycle(args.frozen_root,policy=state['policy'],manifest=state['manifest'])
        runner.io=access_module.provider_io(args.frozen_root,runner.access)
        runner.cleanup();print(json.dumps(dict(status=runner.state['status'])))
    elif args.action=='prepare':
        runner.bind();runner.replacement()
        print(json.dumps(dict(status='STOP15_PREPARED_READBACK',ordinal=runner.journal.ordinal,sha256=runner.journal.previous,deployment=runner.state['deployment'],latest_submission=runner.state['bound_at']+600)))
    else:
        runner.prepared();result=runner.run()
        result.update(owner_cleanup=runner.state.get('closure_verification'),checkpoint=dict(ordinal=runner.journal.ordinal,sha256=runner.journal.previous,status=runner.state['status']))
        print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    try:main()
    except (Exception,KeyboardInterrupt) as exc:
        # Never emit driver SQL/parameters, URLs or credentials in a traceback.
        print(json.dumps(dict(status='STOP_RECONCILE',reason='STOP15_EXECUTION_REFUSED_OR_UNCERTAIN',exception_class=type(exc).__name__)))
        raise SystemExit(1) from None
