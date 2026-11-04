"""One approved qualification-only diagnostic over the existing owner mechanisms."""
import copy,hashlib,json,os,re,time
from pathlib import Path
from . import owner_pilot as p,intake_owner as op
from .database_evidence import canonical
from .intake_owner_io import handoff,submission_check,env_values,service_guard
from .owner_pilot_continuation import migrate_owner_namespace

IDENTITY='b-qualification-20261104-02'
PREDECESSOR='b-qualification-20261104-01'
CONTEXT='b-dbpilot-20261027-1102-05'
CANDIDATE='dc679ef23323701fe5a7963604f22e0ade45fedc'
# Globals are confined to this dedicated existing owner's child process.

class Qualification(p.Pilot):
    def __init__(self,*a,**kw):
        # Pilot's default Journal argument was fixed to CONTEXT at import.
        # Construct without loading it, then bind the exact fresh journal.
        p.PERIOD=IDENTITY;p.PREDECESSOR=CONTEXT
        try:super().__init__(*a,**kw)
        finally:p.PREDECESSOR=PREDECESSOR
        self.journal=p.Journal(self.db,IDENTITY)
    def prepare(self):
        prior=p.Journal(self.db,PREDECESSOR);old=prior.load()
        op.require(old and old['status']=='CLOSED' and old.get('closure_verification',{}).get('status')=='VERIFIED' and old.get('job',{}).get('id')=='job-dbll9futlv9c73c2tjrg','OWNER_CONTINUATION_PREDECESSOR')
        link=dict(period=PREDECESSOR,sha256=prior.previous,ordinal=prior.ordinal)
        with p.envelope(),self.db.connection() as c:migrate_owner_namespace(c,stable_verifiers=old['stable_credentials']['verifier_sha256'],deadline=True)
        op.require(prior.load()==old and prior.previous==link['sha256'],'OWNER_CONTINUATION_PRESERVATION')
        op.require(self.journal.load() is None,'OWNER_CONTINUATION_DUPLICATE')
        release=json.loads(os.environ['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE'])
        op.require(release['execution_binding']['revision']==CANDIDATE,'OWNER_CODE_BINDING')
        self.state=dict(version='OWNER_QUALIFICATION_ONLY_V1',period=IDENTITY,status='PREPARING',intents={},predecessor=link,
            stable_credentials=copy.deepcopy(old['stable_credentials']),stable_configuration=copy.deepcopy(old['stable_configuration']),source_requests=0)
        self.save()
        try:
            self.build();self.state['status']='ARTIFACT_READY';self.save()
        except BaseException as exc:
            self.state['failure']=p.safe_result(exc);self.state['status']='PREPARATION_REFUSED';self.save();self.recover_build();raise
    def binding(self):
        release=json.loads(os.environ['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE']);release['deployment']=self.state['deployment']
        # Period05 is only source context. No collection registration is called.
        p.PERIOD=CONTEXT
        try:b,_=p.fixed_binding(release,self.state['profile'],self.db.address,self.state['original_guard'])
        finally:p.PERIOD=IDENTITY
        folder=Path('/tmp/propertyaigent-owner-'+IDENTITY)
        b.update(release_root=str(folder),submission_intent_path=str(folder/'submission.intent.json'),credential_policy='STABLE_RESTRICTED_V1',credential_verifier_sha256=self.state['stable_credentials']['verifier_sha256'])
        op.validate_binding(b,opening=True);return b
    def verify_deadline_capacity(self,b,*,report_only=False):
        # Same journal codec and normal ceiling; reserve worst bounded evidence
        # before activation, including the access copy and provider/job records.
        op.require(self.journal.ordinal+24+16<64,'OWNER_CLEANUP_ROW_BOUND')
        projected=self.reserved_candidate();projected['binding']=copy.deepcopy(b)
        import random
        rng=random.Random(2026110402)
        noise=lambda n:''.join(rng.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(n))
        projected['owner_deadline_observations']=noise(2048)
        projected['runtime_qualification']=noise(6144)
        projected['job_command']=noise(512)
        projected['job']=noise(1024);projected['job_terminal']=noise(1024)
        with p.envelope(),self.db.connection() as c:
            projected['access']=op.prepare_activation(c,b,stable_credentials=self.state['stable_credentials']['passwords'])
        original=self.state['original_environment'];expected={k:v for k,v in original.items() if k in p.KEEP}
        expected['INGESTION_RENDER_PROFILE']=canonical(b['render_profile']).decode()
        for role,name in (('ingestion_worker_login','INGESTION_WORKER_DATABASE_URL'),('ingestion_effect_login','INGESTION_EFFECT_DATABASE_URL')):expected[name]=p.url(b['route'],role,projected['access']['passwords'][role])
        projected['access']['render']=dict(original=copy.deepcopy(original),expected=expected,guard=b['render_config_sha256'],state='PUT_ACKNOWLEDGED',publication_token=None,publication_state='NOT_REQUESTED',mapped_at=9999999999.999998,handoff_observation_sha256='f'*64)
        for name in ('RELEASE','ACTIVATE','HANDOFF','ONE_JOB'):projected['intents'][name]=dict(at=9999999999.999998,state='ACKNOWLEDGED')
        projected['activation_receipt']=dict(outcome='COMMIT_ACKNOWLEDGED',runtime_roles=sorted(op.ROLES),credentials='ENCRYPTED_LOCAL_ONLY',valid_until=b['valid_until'])
        projected['handoff_receipt']=noise(512)
        projected['observations']={name:dict(provider_observation=dict(version='FINITE_OPERATION_OBSERVATION_V1',operation=name,binding_sha256='f'*64,service_id=p.SERVICE,observed_at=9999999999.999998,env_groups=[],secret_files=[],inherited_credential_names=[],reviewed=True,no_current_work=True,other_activity_stopped=True,deployment_id=b['retained_deployment'],revision=b['execution_binding']['revision'],suspended=True),owner_boundary_confirmed_at=9999999999.999998) for name in ('HANDOFF','SUBMISSION')}

        plain=p.state_size(projected);cipher=p.ciphertext_size(plain);policy=p.cleanup_reserve_policy()
        report=dict(version='DEADLINE_CAPACITY_MEASUREMENT_V1',journal_sha256=self.journal.previous,
            starting_ciphertext_bytes=self.journal.ciphertext_bytes,starting_ordinal=self.journal.ordinal,
            projected_plaintext_bytes=plain,projected_ciphertext_bytes=cipher,normal_ciphertext_ceiling=22152,
            normal_plaintext_ceiling=policy['normal_plaintext_ceiling'],normal_headroom_bytes=22152-cipher,
            cleanup_growth_plaintext=policy['growth_bytes'],cleanup_margin_plaintext=p.CLEANUP_MARGIN,
            worst_cleanup_ciphertext_bytes=p.ciphertext_size(plain+policy['growth_bytes']+p.CLEANUP_MARGIN),
            hard_ciphertext_ceiling=32768,normal_snapshots_reserved=24,cleanup_snapshots_reserved=16,
            worst_final_ordinal=self.journal.ordinal+24+16,maximum_ordinal=63,
            component_plaintext_bytes={k:len(canonical(v)) for k,v in projected.items()},
            component_removal_ciphertext_savings={k:cipher-p.ciphertext_size(p.state_size({n:v for n,v in projected.items() if n!=k})) for k in projected})
        try:
            self.journal.save(projected,validate_only=True)
            report['status']='CAPACITY_VERIFIED_READ_ONLY'
        except op.Denied as exc:
            if str(exc) not in ('OWNER_CLEANUP_RESERVE_BYTE_BOUND','VAULT_32K_BOUND','OWNER_CLEANUP_ROW_BOUND'):raise
            report.update(status='CAPACITY_REFUSED_READ_ONLY',reason=str(exc))
            if not report_only:
                print('DEADLINE_DIAGNOSTIC_CAPACITY '+json.dumps(report,sort_keys=True),flush=True)
                raise
        if not report_only:print('DEADLINE_DIAGNOSTIC_CAPACITY '+json.dumps(report,sort_keys=True),flush=True)
        return report
    def inspect(self):
        result=super().inspect()
        if result.get('workflow_status')=='ARTIFACT_READY' and not result.get('release_intent_present'):
            prior=(self.journal.previous,self.journal.ordinal,copy.deepcopy(self.state))
            result['deadline_capacity']=self.verify_deadline_capacity(self.binding(),report_only=True)
            observed=self.journal.load()
            op.require((self.journal.previous,self.journal.ordinal,observed)==prior,'OWNER_CONTINUATION_PRESERVATION')
            result['capacity_journal_unchanged']=True
        return result
    def run(self,checked_at):
        op.require(type(checked_at) in (int,float) and 0<=time.time()-checked_at<=300,'OWNER_INHERITED_BOUNDARY_REQUIRED')
        self.state=self.journal.load()
        op.require(self.state and self.state['status']=='ARTIFACT_READY' and 'RELEASE' not in self.state['intents'],'OWNER_PRIOR_INTENT_RECONCILE')
        self.preflight()
        with self.api() as api:
            op.require(service_guard(api.call('GET'))==self.state['original_guard'] and env_values(api.call('GET','/env-vars?limit=100'))==self.state['original_environment'],'OWNER_PREBUILD_DRIFT')
        b=self.binding();self.verify_deadline_capacity(b);self.arm_cleanup_reserve();self.state['binding']=b;self.intent('RELEASE')
        try:
            Path(b['release_root']).mkdir(mode=0o700)
            self.intent('ACTIVATE')
            with p.envelope(),self.db.connection() as c:
                prepared=op.prepare_activation(c,b,stable_credentials=self.state['stable_credentials']['passwords'])
                self.state['access']=copy.deepcopy(prepared);self.journal.save(self.state,connection=c)
                opening=copy.deepcopy(self.state);opening['access']['state']='ACTIVATION_ACKNOWLEDGED'
                self.journal.save(opening,validate_only=True)
                def saved(v):
                    self.state['access']=copy.deepcopy(v)
                    if v.get('state')=='ACTIVATION_ACKNOWLEDGED':self.journal.save(self.state,connection=c)
                self.state['owner_deadline_observations']={}
                self.state['activation_receipt']=op.activate(c,b,saved,prepared=prepared,deadline_observations=self.state['owner_deadline_observations'])
            op.require(len(canonical(self.state['owner_deadline_observations']))<=2048,'DEADLINE_EVIDENCE_BOUND')
            self.ack('ACTIVATE')
            observation=self.observation('HANDOFF',checked_at);self.intent('HANDOFF')
            with self.api() as api:self.state['handoff_receipt']=handoff(api,self.state['access'],self.access_save,None,observation=observation)
            self.ack('HANDOFF');observation=self.observation('SUBMISSION',checked_at)
            with self.api() as api:submission_check(api,self.state['access'],self.access_save,observation)
            command='/usr/bin/timeout --signal=INT --kill-after=5s 90s python -u -m scripts.owner_pilot_job --period '+CONTEXT+' --hostaddr '+b['hostaddr']+' --deadline '+str(b['valid_until'])+' --qualification-only'
            self.state['job_command']=command;self.intent('ONE_JOB')
            with self.api() as api:
                op.validate_binding(b,opening=True);job=api.call('POST','/jobs',{'startCommand':command})
            op.require(isinstance(job,dict) and re.fullmatch('job-[a-z0-9]{20}',job.get('id','')) and job.get('serviceId')==p.SERVICE and job.get('startCommand')==command,'OWNER_JOB_ACK_UNCERTAIN')
            self.state['job']=job;self.ack('ONE_JOB')
            for _ in range(32):
                self.sleep(15)
                with self.api() as api:job=api.call('GET','/jobs/'+job['id'])
                if job.get('status') in p.TERMINAL and job.get('finishedAt'):break
            op.require(job.get('status') in p.TERMINAL and job.get('finishedAt'),'OWNER_OPEN_OR_UNVERIFIED')
            self.state['job_terminal']=job;self.save()
            with self.api() as api:value=api.call('GET','qualification:'+job['id'])
            op.require(value.get('hasMore') is False and len(value.get('logs',[]))==1,'RUNTIME_QUALIFICATION_EVIDENCE')
            line=value['logs'][0]['message'];prefix='DATABASE_PILOT_RUNTIME_QUALIFICATION '
            op.require(line.startswith(prefix),'RUNTIME_QUALIFICATION_EVIDENCE');receipt=json.loads(line[len(prefix):])
            op.require(receipt.get('period')==CONTEXT and receipt.get('execution_binding')==b['execution_binding'] and receipt.get('deadline')==b['valid_until'] and receipt.get('source_requests')==0,'RUNTIME_QUALIFICATION_EVIDENCE')
            op.require(len(canonical(receipt))<=6144,'DEADLINE_EVIDENCE_BOUND')
            self.state['runtime_qualification']=receipt;self.state['pipeline_status']='QUALIFICATION_ONLY_'+receipt['status'];self.save()
            if receipt['status']!='VERIFIED_BOTH_RESTRICTED_ROLES':raise op.Denied('OWNER_RESTRICTED_AUTHENTICATION_REFUSED')
        except BaseException as exc:self.record_first_failure(exc)
        finally:self.cleanup()
        return self.summary()
    def summary(self):
        value=super().summary();value.update(diagnostic_only=True,source_context=CONTEXT,collection_period_issued=False,source_requests=0,owner_deadline_observations=self.state.get('owner_deadline_observations'),worker_deadline_argument=(self.state.get('binding') or {}).get('valid_until'))
        return value
    def reconcile_submission(self):
        """GET-only discovery after uncertain POST; never creates another job."""
        self.state=self.journal.load()
        if self.state.get('job') or 'ONE_JOB' not in self.state.get('intents',{}):return
        from datetime import datetime
        with self.api() as api:rows=api.call('GET','/jobs?limit=100')
        op.require(isinstance(rows,list) and len(rows)<100,'OWNER_COMPLETE_INVENTORY_REQUIRED')
        matches=[]
        for item in rows:
            job=item.get('job',item)
            op.require(isinstance(job,dict) and job.get('status') in ('pending','running','succeeded','failed','canceled') and job.get('createdAt'),'OWNER_COMPLETE_INVENTORY_REQUIRED')
            if job.get('startCommand')==self.state.get('job_command'):
                op.require(job.get('serviceId')==p.SERVICE and datetime.fromisoformat(job['createdAt'].replace('Z','+00:00')).timestamp()>=self.state['intents']['ONE_JOB']['at'],'OWNER_JOB_ACK_UNCERTAIN')
                matches.append(job)
        op.require(len(matches)<=1,'OWNER_JOB_ACK_UNCERTAIN')
        if matches:
            self.state['job']=matches[0]
            if matches[0]['status'] in p.TERMINAL and matches[0].get('finishedAt'):self.state['job_terminal']=matches[0]
            self.state['submission_reconciliation']='MATCHED_EXISTING_JOB'
        else:self.state['submission_reconciliation']='NO_MATCH_IN_COMPLETE_INVENTORY_NO_RESUBMISSION'
        with self.cleanup_writes():self.save()
    def recover(self):
        self.reconcile_submission()
        return super().recover()
