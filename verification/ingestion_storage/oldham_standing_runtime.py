"""Oldham retained capture/screening adapter for spec032's restricted runtime.

No administrative connector, issuance, provisioning, revocation or source reader.
Owner phases use the existing immutable markers; all work uses FiniteCaller.
"""
import argparse,json,os,sys,time,re
from datetime import datetime,timezone
from pathlib import Path
from sqlalchemy import text
from app.ingestion.ledger import Denied,digest,DEFAULT_LIMITS
from . import oldham_standing_plan as plan
from .standing_access import GITHUB,POLL_ATTEMPTS,POLL_SECONDS,credentials,require_closure,StandingGitHub
from .stable_pipeline import HostedRunner,HostedOwner,stop_early
from .operational_publication import GitHub,canonical,blob_bytes,REPO,BRANCH,Uncertain
from .operational_journal import Journal
from .oldham_allocation import Allocation,FiniteCaller
from .oldham_authority import derive,registration_value,stop_identity
from .tls_trust import owned_resources,verified_trust

AUTHORITY='OLDHAM_STANDING_CAPTURE_SCREENING_V1_OWNER_APPROVED'


def admitted(env,data):
    p=data['package'];sha=p['revision']
    return (env.get('GITHUB_ACTIONS')=='true' and env.get('RUNNER_ENVIRONMENT')=='github-hosted' and env.get('GITHUB_REF')=='refs/heads/master'
            and env.get('GITHUB_SHA')==env.get('GITHUB_WORKFLOW_SHA')==sha and env.get('GITHUB_RUN_ATTEMPT')=='1'
            and env.get('GITHUB_RUN_NUMBER')==str(data['manifest']['runtime_admission']['run_number']) and env.get('OLDHAM_STANDING_AUTHORITY')==AUTHORITY
            and not any(env.get(k) for k in ('DATABASE_URL','INGESTION_STORAGE_DATABASE_URL','INGESTION_APPLICATION_DATABASE_URL','INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL','GH_TOKEN','GITHUB_TOKEN','PYTHONPATH','INGESTION_PROVISIONING_TEST_URL'))
            and not any(k.startswith('PG') and env.get(k) for k in env))


class StandingRunner(HostedRunner):
    """Reuse standing publication/closure; no Bolton capture or screening path."""
    def __init__(self,data,urls,journal,github,*,memory,ssl,hostaddr=None,disposable=False,check_extra=None,sleep=time.sleep):
        self.export_limit=data['export']['runtime_limit'];self.data=data;self.p=data['package'];self.journal=journal;self.emit=journal.emit;self.github=github;self.memory=memory;self.ssl=ssl;self.hostaddr=hostaddr
        self.started=time.monotonic();self.phase='admin';self.phase_started=self.started;self.admin_seconds=0;self.runtime_seconds=0;self.expiry=datetime.fromisoformat(self.p['expires_at'])
        self.deadlines=dict(job=450,diagnostic_total=480,diagnostic_window=30,admin_diagnostic=240,admin_pre=210,admin_total=240,runtime_total=300)
        self.operation_phase='INITIALISATION';self.diagnosing=False;self.baseline=owned_resources();self.closed=True;self.matrix=None
        self.owner=HostedOwner(self,urls);self.receipts={};self.source_attempts=0;self.source_resources=dict(status='NOT_STARTED',attempted_requests=0,received_body_bytes=0)
        self.published=0;self.workflow_run_id=None;self.capture=None;self.plans=[];self.batch_bindings={};self.route_name=None if disposable else 'POOLER';self.settle_seconds=0;self.check_extra=check_extra;self.pipeline_sleep=sleep
        self.EVIDENCE='docs/design/ingestion-operational-execution-'+self.p['release_id'];self.evidence_head=self.p['evidence_head'];self.r=dict(evidence_directory=self.EVIDENCE,mode=plan.VERSION,manifest_sha256=data['seal'])
        self.execution=dict(revision=self.p['revision'],manifest_sha256=data['seal'],capture_key=data['capture'].root_key,initial_evidence_head=self.p['evidence_head'],authority=data['capture'].authority)
        elapsed=(datetime.now(timezone.utc)-data['started']).total_seconds();self.started-=elapsed;self.phase_started=self.started
        self.allocation=Allocation(package_started=self.started)
        options={} if disposable else dict(ssl=ssl,route='POOLER',hostaddr=hostaddr)
        reg=data['capture'];self.capture_key=reg.root_key
        self.caller=FiniteCaller(data['binding'],data['contract'],data['rule'],urls,revision=self.p['revision'],bindings=dict(reg.bindings),capture_authority=reg.authority,chain_authority='',
                                 stop_file=journal.root/'STOP',allow_test_evidence=disposable,engine_options=options,capture_screening_only=True,allocation=self.allocation)
        self.disposable=disposable;self.checkpoint_probe=None

    def check(self):
        super().check()
        self.export_capacity()
        if self.check_extra:self.check_extra()
        if not self.diagnosing:self.allocation.check()

    def export_capacity(self,additional=0,*,replacement=None):
        # Project local replacements and attempted publication before effects.
        persisted=sum(p.stat().st_size for p in self.journal.root.rglob('*') if p.is_file())
        if replacement is not None:
            name,raw=replacement;prior=self.journal.root/name
            persisted+=len(raw)-(prior.stat().st_size if prior.exists() else 0)
        if self.published+persisted+additional>self.export_limit-128*1024:raise Denied('OLDHAM_STANDING_RUNTIME_EXPORT_RESERVE')

    def _phase_receipts(self):
        values=[]
        for key,value in self.caller.accounting.items():
            for i,v in enumerate(value if isinstance(value,list) else [value]):
                self.receipts[f'{key}-{i}']=dict(database=v);values.append(v)
        if self.caller.prior:
            self.receipts['capture_readback']=dict(database=self.caller.prior);values.append(self.caller.prior)
        self.closed=all(v.get('cleanup')=='CLOSED' and v.get('connections_closed') is True for v in values)
        return values

    def grant_present(self,reg):
        """Read-only exact grant observation; claims still enforce SQL policy/fencing."""
        b=self.caller._budget();engine=b.engine(self.owner.urls['ingestion_worker_login'],**self.caller.engine_options)
        try:
            with engine.connect() as c:
                ctl=c.execute(text("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)")).scalar_one()
            stop_identity(ctl);g=ctl.get('grants',{}).get(reg.authority);a=ctl.get('oldham_allowances',{}).get(reg.authority)
            if not g or not a or any(g.get(k)!=v for k,v in reg.grant.items()) or a.get('revoked') is not False or a.get('expires_at',0)<=time.time():raise Denied('OLDHAM_STANDING_AUTHORITY')
            if a.get('grant_binding')!={k:v for k,v in g.items() if k not in ('source_calls','writes')} or a.get('evidence',{}).get('registration_sha256')!=digest(registration_value(reg)):raise Denied('OLDHAM_STANDING_AUTHORITY_BINDING')
        finally:
            receipt=b.close([]);self.caller.accounting.setdefault('authority_reads',[]).append(receipt)
        require_closure([receipt])

    def archive(self,raw):
        if raw!=self.data['source_raw']:raise Denied('OLDHAM_ARCHIVE_SOURCE_BINDING')
        origin=self.p['origin'];blob=self.github.call('GET',REPO+'/contents/'+origin['source_path']+'?ref='+origin['commit'])
        if blob_bytes(blob)!=raw:raise Denied('OLDHAM_ARCHIVE_READBACK_CHANGED')
        from .oldham_owner_package import sha
        result=dict(commit=origin['commit'],path=origin['source_path'],sha256=sha(raw),bytes=len(raw),readback_verified=True)
        if self.disposable:result['label']='TEST_ARCHIVE_NOT_LIVE_EVIDENCE'
        return result

    def await_screen(self,reg):
        # No database connection remains open while waiting.
        for attempt in range(POLL_ATTEMPTS):
            self.check();head=self.head();blob=self.github.probe(REPO+'/contents/'+self.EVIDENCE+'/screening-authority/registered.json?ref='+head)
            if blob is not None:
                m=json.loads(blob_bytes(blob));expected=dict(execution=self.execution,capture_sha256=digest(self.capture),registration_sha256=digest(registration_value(reg)),authority=reg.authority)
                if m!=expected:raise Uncertain('OLDHAM_STANDING_SCREEN_MARKER')
                self.evidence_head=head;self.grant_present(reg);return
            if attempt+1<POLL_ATTEMPTS:self.pipeline_sleep(POLL_SECONDS)
        raise Denied('OLDHAM_STANDING_SCREEN_WAIT_EXHAUSTED')

    def accounting(self):
        return dict(runtime=self.allocation.totals(),runtime_receipts=self.caller.accounting,github_requests=self.github.requests,credential_changes=0,source_requests=0,administrative_connections=0,export_reservation=self.data['export'])

    def run(self):
        try:
            self.check();reg=self.data['capture'];self.operation_phase='CAPTURE_AUTHORITY_CHECK';self.grant_present(reg)
            self.caller.preflight(reg.root_key);self.operation_phase='CAPTURE';self.caller.capture(self.data['source'],self.data['outer'],expected_source_sha256=digest(self.data['source']),evidence_label='QUALIFIED_ACCEPTED_RETAINED_AUDIT',archive=self.archive)
            self.capture=self.caller.read_capture();receipts=self._phase_receipts();require_closure(receipts)
            after=owned_resources()
            if after['children'] or after['socket_fds']-self.baseline['socket_fds']:raise Uncertain('OLDHAM_STANDING_CAPTURE_PROCESS_CLOSURE')
            marker=dict(execution=self.execution,capture_sha256=digest(self.capture),phase_receipts=receipts,allocation=self.allocation.totals(),phase_closure=dict(children=0,new_sockets=0))
            self.export_capacity(len(canonical(marker)))
            self.published+=len(canonical(marker))
            self.evidence_head=self.github.publish({'retained.json':canonical(marker)},directory=self.EVIDENCE+'/capture-retained',expected_head=self.evidence_head)
            root=dict(reg.rows[0],state='COMPLETE',checkpoint=self.capture)
            screen=derive(self.data['description'],self.data['binding'],self.data['contract'],revision=self.p['revision'],item_limits=DEFAULT_LIMITS,phase='SCREENING',root=root,receipt=self.capture,rule=self.data['rule'],allow_test_evidence=self.disposable)
            self.operation_phase='SCREENING_AUTHORITY_WAIT';self.await_screen(screen)
            self.caller.bindings.update(screen.bindings);self.caller.use(screen);self.operation_phase='SCREENING';self.caller.screen();rows=self.caller.read_screening();nominees=self.caller.nominees()
            require_closure(self._phase_receipts())
            closure=self.closure('RESTRICTED_RUNTIME_NO_ACCESS_CHANGE',memory_close=False)
            return dict(status='OLDHAM_STANDING_CAPTURE_SCREENING_COMPLETE',workflow_run_id=self.workflow_run_id,execution=self.execution,records=len(self.capture['records']),nominees=len(nominees.nominees),
                        outcome='SCREENING_COMPLETE_ADMISSION_HELD_OPERATION_SCOPE' if nominees.nominees else 'SCREENING_COMPLETE_NO_ADMISSION_REQUIRED',capture_sha256=digest(self.capture),screening_sha256=digest(rows),
                        cleanup=closure['overall'],closure_components=closure,closure_stage='PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE',accounting=self.accounting(),credential_changes=0,
                        application_writes=0,source_observations_attempted=0,detail_requests=0,application_engine='NOT_CREATED',admission='NOT_AUTHORISED',coverage_advance=False,
                        authority_invalidation='OWNER_REQUIRED',pipeline_retry='HELD',stage4='OPEN')
        except BaseException as exc:
            self.diagnosing=True;self.diagnostic_started=time.monotonic();self._phase_receipts()
            from .connection_diagnostics import safe_failure,fixed_stop_reason
            return dict(status='STOP_RECONCILE_NO_RETRY',execution=self.execution,capture_sha256=digest(self.capture) if self.capture else None,cleanup='UNCERTAIN',operation_phase=self.operation_phase,
                        failure=safe_failure(exc,'EXECUTION'),stop_reason=fixed_stop_reason(exc),accounting=self.accounting(),credential_changes=0,application_writes=0,source_observations_attempted=0,stage4='OPEN')


    def publish_completed(self,result):
        raw=canonical(result);files={'events.jsonl':self.journal.file.read_bytes(),'final-result.json':raw}
        self.export_capacity(sum(map(len,files.values())),replacement=('final-result.json',raw))
        self.journal.save('final-result.json',result)
        self.published+=sum(map(len,files.values()))
        self.evidence_head=self.github.publish(files,directory=self.EVIDENCE+'/completed',expected_head=self.head())
        return self.evidence_head

    def finalise(self,result):
        sealed=super().finalise(result)
        if self.allocation.failed or not self.closed:sealed['cleanup']='UNCERTAIN';sealed['status']='STOP_RECONCILE_NO_RETRY'
        sealed['accounting']=self.accounting()
        sealed['accounting']['attempted_publication_bytes']=self.published
        sealed['local_audit_path']=str(self.journal.file)
        from .operational_outcome import finalise
        return finalise(self.journal,sealed,input_seconds=0,active_started=self.started,external_bytes=self.published)


def run_claim(claim,urls,journal,github,*,memory,ssl,hostaddr=None,disposable=False,sleep=time.sleep,check_extra=None,claim_head=None):
    data=plan.runtime_inputs(claim,disposable=disposable)
    runner=StandingRunner(data,urls,journal,github,memory=memory,ssl=ssl,hostaddr=hostaddr,disposable=disposable,sleep=sleep,check_extra=check_extra)
    if claim_head is not None:runner.evidence_head=claim_head
    runner.workflow_run_id=int(os.environ.get('GITHUB_RUN_ID','0')) if os.environ.get('GITHUB_RUN_ID','0').isdigit() else None
    github.check=runner.check;github.bound=GITHUB['runtime_work']
    if runner.head()!=runner.evidence_head:raise Denied('OLDHAM_STANDING_EVIDENCE_HEAD')
    if github.probe(REPO+'/contents/README.md?ref='+runner.evidence_head) is None:raise Denied('OLDHAM_STANDING_EVIDENCE_ANCHOR')
    result=runner.run();github.bound=GITHUB['runtime'];return runner.finalise(result)


def main(argv=None,*,effects=None):
    a=argparse.ArgumentParser();a.add_argument('--output',type=Path,required=True);a.add_argument('--claim-commit',required=True);a.add_argument('--release-id',required=True);a.add_argument('--manifest-sha256',required=True);x=a.parse_args(argv)
    if not re.fullmatch('[a-f0-9]{40}',x.claim_commit) or not re.fullmatch('[a-f0-9]{64}',x.manifest_sha256) or not re.fullmatch('oldham-owner-[a-z0-9-]{1,60}',x.release_id):raise SystemExit('OLDHAM_STANDING_INPUT_BOUNDARY')
    journal=Journal(x.output)
    from .stable_qualification import install_cancellation
    install_cancellation()
    from .operational_memory import OperationalMemory
    disposable=effects is not None
    if disposable and (getattr(effects,'fixed_disposable',False) is not True or os.environ.get('INGESTION_ACCEPTANCE_DISPOSABLE')!='PG17_ONLY'):raise SystemExit('STANDING_DISPOSABLE_ONLY')
    memory=effects.memory if disposable else OperationalMemory() # no live fallback
    try:token,urls=credentials(sys.stdin.buffer,disposable=disposable)
    except BaseException:
        proof=memory.close() if memory is not None else None
        early=dict(status='STOP_RECONCILE_NO_RETRY',cleanup='UNCERTAIN',stop_reason='OLDHAM_STANDING_CREDENTIAL_INPUT_REFUSED',database_connections_attempted=0,owned_cleanup=proof,accounting=dict(github_requests=0),credential_changes=0,application_writes=0)
        journal.save('final-result.json',early);print(json.dumps(early));return 1
    from .operational_preparation import Progress,resolve_addresses
    ca,hostaddr=(None,None) if disposable else (verified_trust()[0],resolve_addresses(Progress()))
    import subprocess
    env=dict(PATH='/usr/bin:/bin',HOME=str(x.output.parent),GH_TOKEN=token,GH_HOST='github.com')
    github=StandingGitHub(journal.emit,(memory.snapshot if memory else lambda:None),bound=GITHUB['runtime_work'],runner=effects.gh_runner if disposable else lambda c,**kw:subprocess.run(c,env=env,**kw))
    try:
        path='docs/design/ingestion-operational-execution-'+x.release_id+'/claim/claim.json'
        claim=json.loads(blob_bytes(github.call('GET',REPO+'/contents/'+path+'?ref='+x.claim_commit)))
        if disposable:effects.acceptance(claim)
        data=plan.runtime_inputs(claim,disposable=disposable)
        if data['seal']!=x.manifest_sha256 or data['package']['release_id']!=x.release_id or not admitted(os.environ,data):raise Denied('OLDHAM_STANDING_RUNTIME_ADMISSION')
        result=run_claim(claim,urls,journal,github,memory=memory,ssl=None if disposable else {'sslmode':'verify-full','sslrootcert':str(ca)},hostaddr=hostaddr,claim_head=x.claim_commit,disposable=disposable,sleep=effects.sleep if disposable else time.sleep)
        return 0 if result.get('cleanup')=='CLOSED' and result.get('status')=='OLDHAM_STANDING_CAPTURE_SCREENING_COMPLETE' else 1
    except BaseException:
        try:
            if memory is not None:memory.close()
        except BaseException:pass
        failed=dict(status='STOP_RECONCILE_NO_RETRY',cleanup='UNCERTAIN',stop_reason='OLDHAM_STANDING_ENTRY_REFUSED',database_connections_attempted='UNKNOWN',accounting=dict(github_requests=github.requests),credential_changes=0,application_writes=0)
        journal.save('final-result.json',failed);print(json.dumps(failed));return 1

if __name__=='__main__':raise SystemExit(main())
