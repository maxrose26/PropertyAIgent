"""Restricted-runtime half of the stable-credential pipeline (see specifications/032-stage4-stable-credential-pipeline.md).

Runs in the single-use hosted job with the two restricted credentials ALONE: no administrative credential, no Owner, no credential change, no revocation. It reuses the accepted
capture/screening components unchanged (`Runner.slot`, `capture_once`, `screen`, `ControllerLedger`, `DatabaseBudget`, `batch_plans`, `process_batch`) by building a Runner whose "owner" is a
stand-in that can only (a) hand over the two restricted URLs and (b) wait for the OWNER-registered screening authority, which it never issues itself.

Order: admission -> bounded connection qualification (the reviewed Qualification, read-only introspection, before ANY ledger work) -> capture authority check (as the worker, read only) ->
capture and durable retention (evidence branch, fast-forward only, before the checkpoint is durable) -> wait for the owner's screening-authority marker (evidence branch poll; no database
connection while waiting) -> source-free queued screening -> sealed result published. There is no connection retry after qualification: a later connection failure is a stop, never a replay
of an uncertain effect."""
import base64,hashlib,json,os,subprocess,sys,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from app.ingestion.ledger import digest,DEFAULT_LIMITS,Denied
from . import stable_qualification as sq
from . import restricted_route as rr
from .connection_diagnostics import safe_failure,fixed_stop_reason
from .operational_controller import DatabaseBudget
from .operational_journal import Journal
from .operational_owner import item,SCOPE,ROLES
from .operational_preparation import Progress,resolve_addresses
from .operational_publication import GitHub,Uncertain,BRANCH,REPO,blob_bytes
from .operational_runner import Runner,CONTRACT,PIPELINE_AUTHORITY
from .tls_trust import verified_trust,owned_resources

PUBLICATION_RESERVE_REQUESTS=14      # the two-file publication is 10 requests (6 + 2x2); head reads take at most 4 more
PUBLICATION_RESERVE_SECONDS=90
HOSTED_AUTHORITY='AUTHORISE_INGESTION_STABLE_PIPELINE_HOSTED_ONCE_20261020'
EVIDENCE_DIRECTORY='docs/design/ingestion-operational-execution-stable-pipeline-20261020'
MANIFEST_PATH='docs/design/ingestion-stable-pipeline-20261020/MANIFEST.json'
# Hosted deadlines. Waiting for the owner counts as the administrative phase of the accepted accounting; runtime keeps the accepted 300 s aggregate.
HOSTED_DEADLINES=dict(job=1800,diagnostic_total=1860,diagnostic_window=40,admin_diagnostic=240,admin_pre=1700,admin_total=1790,runtime_total=300)
SCREENING_WAIT_SECONDS=480
REPROBES=3      # each distinct head is examined at most this many times (successive polls) so one transient 404 cannot hide a published file
EVIDENCE_ANCHOR='README.md'
POLL_SECONDS=15
FORBIDDEN_ENV=('DATABASE_URL','INGESTION_STORAGE_DATABASE_URL','GITHUB_TOKEN','PGPASSWORD','PGSERVICE','PGSERVICEFILE','GH_TOKEN','INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL')      # the secrets are read from stdin; none of these may be in the environment
SECRET_NAMES=tuple(sq.SECRET_ENV.values())


def admitted(env):
    """Single-use protected-environment admission. The restricted URLs and the evidence publisher's job token arrive on STDIN (see read_secrets), so none of them - nor any administrative credential - may be present in the environment, where a same-user child (the credential-free source worker parses untrusted pages) could read them from /proc."""
    sha=env.get('PIPELINE_REVIEWED_SHA','');head=env.get('PIPELINE_EVIDENCE_HEAD','')
    hexed=lambda v:len(v)==40 and all(ch in '0123456789abcdef' for ch in v)
    return (hexed(sha) and hexed(head) and env.get('GITHUB_SHA')==sha and env.get('GITHUB_WORKFLOW_SHA')==sha and env.get('GITHUB_REF')=='refs/heads/master'
            and env.get('GITHUB_RUN_NUMBER')=='1' and env.get('GITHUB_RUN_ATTEMPT')=='1' and env.get('GITHUB_ACTIONS')=='true' and env.get('RUNNER_ENVIRONMENT')=='github-hosted'
            and env.get('PIPELINE_AUTHORITY')==HOSTED_AUTHORITY and not any(env.get(k) for k in FORBIDDEN_ENV) and not any(k.startswith('PG') and env.get(k) for k in env))


# The execution binding the OWNER registered with the capture grant (revision, workflow_sha256 = the controller's hash, manifest_sha256), read by the worker. It is the registration's own binding,
# stored in the database authority, so the hosted job needs no other channel to learn what it is approved to run.
GRANT_BINDING_SQL=("SELECT outcome::jsonb->'grants'->CAST(:a AS text)->'execution_binding',"
                   "(outcome::jsonb->'grants'->CAST(:a AS text)->>'expires_at')::double precision>extract(epoch FROM statement_timestamp()) "
                   "FROM public.ingestion_work_items WHERE key=repeat('0',64)")


def _git(root,*args):
    done=subprocess.run(['git',*args],cwd=str(root),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL,timeout=30,env=dict(PATH='/usr/bin:/bin',HOME=os.environ.get('HOME','/'),GIT_CONFIG_NOSYSTEM='1',LC_ALL='C'))
    if done.returncode:raise Denied('CHECKOUT_BINDING_UNOBSERVABLE')
    return done.stdout.decode('utf-8','strict').strip()


def actual_checkout(root=None):
    """What this job is ACTUALLY running: the checked-out commit and tree, whether any tracked file differs from it, and the hashes of the controller module that is loaded and of the package manifest."""
    root=Path(root or Path.cwd()).resolve()
    from . import operational_runner as controller
    loaded=Path(controller.__file__).resolve()
    if root not in loaded.parents:raise Denied('CHECKOUT_BINDING_MISMATCH')      # the loaded controller is not the one in this checkout
    return dict(revision=_git(root,'rev-parse','HEAD'),tree=_git(root,'rev-parse','HEAD^{tree}'),tracked_files_modified=bool(_git(root,'status','--porcelain','--untracked-files=no')),
                controller_sha256=hashlib.sha256(loaded.read_bytes()).hexdigest(),manifest_sha256=hashlib.sha256((root/MANIFEST_PATH).read_bytes()).hexdigest())


def verify_checkout_binding(actual,binding,reviewed_sha,manifest_sha256):
    """The checkout must be exactly the approved one: clean tracked files, the commit the workflow pinned, and the revision, controller hash and manifest hash the owner registered with the grant. Any
    mismatch is a stop BEFORE any source request. Returns a credential-free summary."""
    ok=(isinstance(actual,dict) and isinstance(binding,dict) and set(binding)=={'revision','workflow_sha256','manifest_sha256'} and actual.get('tracked_files_modified') is False
        and actual.get('revision')==reviewed_sha==binding['revision'] and actual.get('controller_sha256')==binding['workflow_sha256']
        and actual.get('manifest_sha256')==binding['manifest_sha256']==manifest_sha256)
    if not ok:raise Denied('CHECKOUT_BINDING_MISMATCH')
    return dict(revision=actual['revision'],tree=actual['tree'],controller_sha256=actual['controller_sha256'],manifest_sha256=actual['manifest_sha256'],tracked_files_modified=False)


def bindings_for(items):
    return {x['key']:{k:x[k] for k in ('subject','task','contract','revision')} for x in items}


class HostedOwner:
    """The only 'owner' capabilities the restricted job has: its two URLs, a non-secret timeline, and a wait for the owner-registered screening authority. It cannot register anything."""
    def __init__(self,runner,urls):
        self.runner=runner;self.urls=dict(urls);self.timeline={};self.authorities=[]

    def accounting(self):
        return dict(connections=0,connections_opened=0,connections_closed=0,failed_native_connections=0,failed_native_finished=0,commands=0,returned_data_value_bytes=0,database_active_seconds=0,
                    uncertain_effect=False,administrative_credential='NOT_PRESENT')

    def register(self,items,authority,*,capture_key,source_calls,prepared=()):
        if source_calls!=0 or not authority.endswith('_SCREEN'):raise Denied('HOSTED_JOB_CANNOT_REGISTER_AUTHORITY')
        bindings=bindings_for([*items,*prepared])
        self.runner.publish_retained()      # the ledger checkpoint is durable now: tell the owner (it verifies in the database; this marker is not an authority)
        self.runner.await_marker(bindings)
        return bindings


class HostedRunner(Runner):
    """The accepted Runner methods, over a hosted shell. __init__ deliberately does not call Runner.__init__ (no registration, no administrative connector, no Owner)."""
    def __init__(self,urls,journal,github,source_reader,ssl,hostaddr,memory,*,evidence_head,manifest_sha256,revision,checkout_probe=None):
        self.r=dict(evidence_directory=EVIDENCE_DIRECTORY,manifest_sha256=manifest_sha256,mode='STABLE_PIPELINE_HOSTED')
        self.journal=journal;self.emit=journal.emit;self.source_reader=source_reader;self.github=github;self.ssl=ssl;self.memory=memory;self.hostaddr=hostaddr
        self.operation_phase='INITIALISATION';self.started=time.monotonic();self.phase='admin';self.phase_started=self.started;self.admin_seconds=0;self.runtime_seconds=0
        self.expiry=datetime.now(timezone.utc)+timedelta(seconds=HOSTED_DEADLINES['job']+60)
        self.settle_seconds=0;self.settle_sleep=time.sleep;self.route_name='POOLER';self.restricted_hostaddr=None;self.matrix_mode=False;self.matrix=None;self.pipeline_mode=False
        self.deadlines=dict(HOSTED_DEADLINES);self.authority=PIPELINE_AUTHORITY
        self.owner=HostedOwner(self,urls)
        self.source_attempts=0;self.source_resources={'status':'NOT_STARTED','attempted_requests':0,'received_body_bytes':0};self.receipts={};self.plans=[];self.capture=None;self.capture_key=None
        self.batch_bindings={};self.evidence_head=evidence_head;self.closed=True;self.diagnosing=False;self.baseline=owned_resources()
        identity=dict(subject=SCOPE,task='DISCOVERY',contract=CONTRACT,revision=manifest_sha256)
        root=item(identity,max_attempts=1,limits=dict(DEFAULT_LIMITS,requests=10,bytes=3000000,rows=60,pages=6))
        self.capture_key=root['key'];self.capture_bindings=bindings_for([root])
        self.initial_evidence_head=evidence_head;self.checkout_probe=checkout_probe or actual_checkout;self.checkout_binding=None
        self.execution=dict(revision=revision,manifest_sha256=manifest_sha256,capture_key=self.capture_key,initial_evidence_head=evidence_head,authority=PIPELINE_AUTHORITY)      # identical to the owner's pipeline_execution()
        self.pipeline_sleep=time.sleep;self.authority_check=None;self.retained_published=False

    def check(self):
        if sq._Cancellation.requested:raise Denied('CANCELLED')
        super().check()

    def head(self):
        return self.github.call('GET',REPO+'/git/ref/heads/'+BRANCH)['object']['sha']

    def capture_once(self):
        self.retained_published=False
        super().capture_once()
        self.publish_retained()      # also covers a capture with no screening batches or a blocked capture

    def publish_retained(self):
        """Idempotent. The raw source is archived on the evidence branch BEFORE the ledger checkpoint is made durable (accepted order). This second, non-authoritative marker says the checkpoint is
        complete; the owner then verifies it in the database before registering anything."""
        if self.retained_published or self.capture is None:return
        archive=self.capture.get('durable_archive') or {}
        marker=dict(execution=self.execution,capture_sha256=digest(self.capture),kind=self.capture.get('kind'),archive_sha256=archive.get('sha256'))
        self.evidence_head=self.github.publish({'retained.json':json.dumps(marker,sort_keys=True,separators=(',',':')).encode()},directory=EVIDENCE_DIRECTORY+'/capture-retained',expected_head=self.evidence_head)
        self.retained_published=True;self.emit('capture_retained_marker_published',dict(head=self.evidence_head))

    def await_marker(self,bindings):
        """Wait (no database connection) for the OWNER's screening-authority marker: presence-based at the current head of the evidence branch, each distinct head probed once. The marker is not an
        authority - the authority is in the database and is enforced there when the screening slot runs. A marker that disagrees with the locally recomputed bindings is UNCERTAIN. Timeout is a stop."""
        deadline=time.monotonic()+SCREENING_WAIT_SECONDS;probes={}
        self.emit('awaiting_owner_screening_authority',dict(from_head=self.evidence_head,seconds=SCREENING_WAIT_SECONDS))
        while True:
            self.check()
            head=self.head()
            if probes.get(head,0)<REPROBES:
                probes[head]=probes.get(head,0)+1
                blob=self.github.probe(REPO+'/contents/'+EVIDENCE_DIRECTORY+'/screening-authority/registered.json?ref='+head)
                if blob is not None:
                    try:marker=json.loads(blob_bytes(blob))
                    except ValueError:raise Uncertain('OWNER_MARKER_UNREADABLE') from None
                    if (not isinstance(marker,dict) or marker.get('execution')!=self.execution or marker.get('bindings_sha256')!=digest(bindings) or marker.get('capture_sha256')!=digest(self.capture)
                        or marker.get('authority')!=self.authority+'_SCREEN'):raise Uncertain('OWNER_MARKER_BINDING_MISMATCH')
                    self.evidence_head=head;self.emit('owner_screening_authority_marker_verified',dict(head=head));return
            if time.monotonic()>=deadline:raise Denied('OWNER_SCREENING_AUTHORITY_WAIT_EXPIRED')
            self.pipeline_sleep(POLL_SECONDS)

    def authority_present(self):
        """Read-only check as the worker, with its own small budget and no ledger mutation, BEFORE the single source request is even considered: an unexpired capture grant must exist AND this job's
        actual checkout must be exactly the approved one (the execution binding the owner registered with that grant)."""
        budget=DatabaseBudget(connections=1,statements=24,seconds=60,emit=self.emit,stop_file=self.journal.root/'STOP');closed=None      # the accepted per-connection profile check needs its own statements; this connection reads two rows
        engine=budget.engine(self.owner.urls['ingestion_worker_login'],ssl=self.ssl,hostaddr=self.restricted_address(),route=self.route_name)
        try:
            with engine.connect() as connection:
                from sqlalchemy import text
                count=connection.execute(text(sq.CONTROL_SQL)).fetchone()
                granted=connection.execute(text(GRANT_BINDING_SQL),{'a':self.authority+'_CAPTURE'}).fetchone()
        finally:closed=budget.close([engine])
        if closed.get('cleanup')!='CLOSED' or count is None or int(count[3])<1 or granted is None or granted[0] is None or granted[1] is not True:raise Denied('CAPTURE_AUTHORITY_NOT_REGISTERED')
        self.checkout_binding=verify_checkout_binding(self.checkout_probe(),granted[0],self.execution['revision'],self.execution['manifest_sha256'])      # a mismatch stops here: zero source requests
        self.emit('capture_authority_observed',dict(unexpired_grants=int(count[3]),client_closure=closed.get('cleanup'),checkout_binding=self.checkout_binding))
        return closed

    def hosted_result(self,qualification):
        from collections import Counter
        from app.ingestion.listing_screening import screen_row
        components=self.closure('RESTRICTED_RUNTIME_NO_ACCESS_CHANGE',memory_close=False)      # the memory scope keeps enforcing until the final result is published (finalise)
        screens=[screen_row(row) for row in self.capture.get('records',[])] if self.capture and self.capture.get('kind')=='LISTING_RECEIPT_V1' else []
        usable=sum(x['proposal_usable'] for x in screens)
        outcome='CAPTURED_PROCESSING_BLOCKED' if self.capture and self.capture.get('kind')!='LISTING_RECEIPT_V1' else 'STABLE_PIPELINE_CAPTURE_SCREENING_COMPLETED_RESTRICTED_RUNTIME_ONLY'
        if self.capture and self.capture.get('kind')=='LISTING_RECEIPT_V1':
            if not screens:outcome='DISCOVERY_EXPLICIT_ZERO_SCREENING_NOT_EXERCISED'
            elif usable<len(screens):outcome='PARTIAL_PROPOSAL_COVERAGE'
        return dict(status=outcome if components['overall'] in ('CLOSED','PENDING_MEMORY_SCOPE_CLOSURE') else 'STOP_RECONCILE_NO_RETRY',closure_stage='PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE',execution=self.execution,checkout_binding=self.checkout_binding,cleanup=components['overall'],closure_components=components,qualification=qualification,
                    rows=len((self.capture or {}).get('records',[])),batches=len(self.plans),capture_sha256=digest(self.capture) if self.capture else None,slot_receipts=self.receipts,
                    accounting=self.accounting(),authority_check_receipt=self.authority_check,usable_proposals=usable,screening_dispositions=dict(Counter(x['disposition'] for x in screens)),citation_leads=sum(len(x['citations']['occurrences']) for x in screens),
                    source_resources=(self.capture or {}).get('resources'),source_observations_attempted=self.source_attempts,application_writes=0,credential_changes=0,grants_issued=0,
                    client_closure_vs_server_session='CLIENT_SIDE_RECEIPTS_ONLY_SERVER_SESSIONS_ARE_AN_OWNER_READBACK',pipeline_retry='HELD',stage4='OPEN',historical_uncertainty_preserved=True,
                    memory_enforcement=dict(kind='CGROUP_V2_ACTUAL_MEMORY' if self.memory is not None else 'NOT_ESTABLISHED',aggregate_bytes=1536*1024**2 if self.memory is not None else None))

    def run(self):
        qualification=None
        try:
            self.operation_phase='CONNECTION_QUALIFICATION'
            q=sq.Qualification(self.owner.urls,emit=self.emit,ssl=self.ssl,hostaddr=self.hostaddr,stop_file=self.journal.root/'STOP')
            qualification=q.run()
            self.emit('connection_qualification_result',dict(status=qualification['status'],stop_reason=qualification.get('stop_reason'),attempts_total=qualification['attempts_total'],accounting=qualification['accounting']))
            if qualification['status']!='STABLE_CREDENTIALS_QUALIFIED':raise Denied('CONNECTION_QUALIFICATION_'+str(qualification.get('stop_reason')))
            qualification={k:qualification[k] for k in ('status','attempts_total','accounting','elapsed_seconds')}
            self.operation_phase='CAPTURE_AUTHORITY_CHECK';self.authority_check=self.authority_present()
            self.capture_once()
            if self.capture['kind']!='LISTING_RECEIPT_V1':
                self.emit('capture_processing_blocked',dict(checkpoint=self.capture))
            elif self.plans:self.screen()
            result=self.hosted_result(qualification)
        except BaseException as exc:
            result=self.hosted_failure(exc,qualification)
        return result

    def hosted_failure(self,exc,qualification):
        self.diagnosing=True;self.diagnostic_started=time.monotonic()
        try:components=self.closure('RESTRICTED_RUNTIME_NO_ACCESS_CHANGE',memory_close=False)
        except BaseException:components=dict(overall='UNCERTAIN')
        result=dict(status='STOP_RECONCILE_NO_RETRY',closure_stage='PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE',execution=self.execution,capture_sha256=digest(self.capture) if self.capture else None,cleanup=components['overall'],closure_components=components,failure=safe_failure(exc,'EXECUTION'),stop_reason=fixed_stop_reason(exc),checkout_binding=self.checkout_binding,operation_phase=self.operation_phase,qualification=qualification,
                    accounting=self.accounting(),source_observations_attempted=self.source_attempts,source_capture_retained=self.capture is not None,source_resources=self.source_resources,
                    application_writes=0,credential_changes=0,grants_issued=0,pipeline_retry='HELD',stage4='OPEN',historical_uncertainty_preserved=True)
        try:self.emit('stopped',result)
        except BaseException:result['audit_stop_record']='UNCERTAIN'
        return result

    def publish_completed(self,result):
        """The sealed execution chain and the result, on the evidence branch (the owner's signal that the restricted job is finished). Best effort on a failure path: the owner's own deadline and
        the grant lifetime bound the authority regardless."""
        self.journal.save('final-result.json',result)
        self.evidence_head=self.github.publish({'events.jsonl':self.journal.file.read_bytes(),'final-result.json':json.dumps(result,sort_keys=True,separators=(',',':')).encode()},directory=EVIDENCE_DIRECTORY+'/completed',expected_head=self.head())
        return self.evidence_head


    def finalise(self,result):
        """Publish the result for the owner INSIDE the enforced scope and a bounded reserve, THEN close the memory scope and seal the complete local record. The closed-envelope guard is untouched: after the
        scope is removed no GitHub call is admitted. A publication failure carries a fixed non-secret reason; the sealed local record (and the workflow artifact) remain authoritative."""
        publication='PUBLISHED';reason=None
        try:
            with self.github.reserve_scope(PUBLICATION_RESERVE_REQUESTS,PUBLICATION_RESERVE_SECONDS):self.publish_completed(result)
        except BaseException as exc:
            publication='UNCERTAIN_'+type(exc).__name__;reason=fixed_stop_reason(exc)
        try:final=self.closure('RESTRICTED_RUNTIME_NO_ACCESS_CHANGE',memory_close=True)
        except BaseException:final=dict(overall='UNCERTAIN')
        sealed=dict(result,closure_stage='FINAL_AFTER_PUBLICATION',cleanup=final['overall'],closure_components=final,publication=publication,publication_reason=reason,
                    status=result['status'] if final['overall']=='CLOSED' else 'STOP_RECONCILE_NO_RETRY',published_status=result['status'],published_cleanup=result.get('cleanup'))
        try:
            self.journal.emit('final_closure',dict(cleanup=final['overall'],publication=publication,publication_reason=reason));self.journal.save('final-result.json',sealed)
        except BaseException:sealed['audit_stop_record']='UNCERTAIN'
        return sealed


def stop_early(journal,reason,detail=None):
    result=dict(status='STOP_RECONCILE_NO_RETRY',stop_reason=reason,detail=detail,database_connections_attempted=0,application_writes=0,credential_changes=0)
    journal.emit('stopped',result);journal.save('final-result.json',result)
    print(json.dumps({'status':result['status'],'stop_reason':reason}));return result


def run_hosted(*,urls,journal,gh_runner,source_reader_factory,ssl,hostaddr,memory,evidence_head,manifest_sha256,revision,checkout_probe=None):
    """The hosted pipeline over INJECTED effects (the GitHub CLI runner, the source reader, the memory scope). Production passes the reviewed implementations from main(); the disposable rehearsal
    passes loopback fixtures. Returns (result, exit_code). Nothing else differs between the two."""
    holder={}
    github=GitHub(journal.emit,lambda:holder['runner'].check(),runner=gh_runner,bound=140)
    runner=HostedRunner(urls,journal,github,None,ssl,hostaddr,memory,evidence_head=evidence_head,manifest_sha256=manifest_sha256,revision=revision,checkout_probe=checkout_probe);holder['runner']=runner
    runner.source_reader=source_reader_factory(runner)
    if runner.head()!=evidence_head:return stop_early(journal,'EVIDENCE_HEAD_MOVED'),1
    if github.probe(REPO+'/contents/'+EVIDENCE_ANCHOR+'?ref='+evidence_head) is None:return stop_early(journal,'EVIDENCE_BRANCH_ANCHOR_MISSING'),1      # a 404 below means something only if the branch itself is readable
    result=runner.finalise(runner.run())      # publication first (scope still enforcing, bounded reserve), then the final closure
    print(json.dumps({k:result.get(k) for k in ('status','cleanup','rows','batches','publication','publication_reason')},sort_keys=True))
    return result,0 if result.get('cleanup')=='CLOSED' and result.get('status')!='STOP_RECONCILE_NO_RETRY' else 1


def read_secrets(stream):
    """The job token and the two restricted URLs, one per line, from the inherited stdin pipe (bounded). Nothing else is read and nothing is echoed."""
    raw=stream.read(16384)
    if not isinstance(raw,(bytes,bytearray)) or len(raw)>=16384:raise SystemExit('RESTRICTED_CREDENTIALS_REQUIRED')
    lines=raw.decode('utf-8','strict').split('\n')
    if len(lines)!=4 or lines[3]!='' or any(not x or x!=x.strip() or ' ' in x for x in lines[:3]):raise SystemExit('RESTRICTED_CREDENTIALS_REQUIRED')
    return lines[0],{'ingestion_worker_login':lines[1],'ingestion_effect_login':lines[2]}


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args(argv)
    if not admitted(os.environ):raise SystemExit('PIPELINE_NOT_ADMITTED')
    token,urls=read_secrets(sys.stdin.buffer)      # stdin only: the secrets are never in this process's environment
    journal=Journal(args.output);journal.emit('consumed',dict(authority=HOSTED_AUTHORITY,evidence_head=os.environ['PIPELINE_EVIDENCE_HEAD']))
    sq.install_cancellation()
    from .operational_memory import OperationalMemory
    try:memory=OperationalMemory()      # kernel-enforced ACTUAL memory (cgroup v2), established BEFORE any database connection; unavailable = stop here
    except Exception as exc:
        stop_early(journal,'ACTUAL_MEMORY_ENFORCEMENT_UNAVAILABLE',type(exc).__name__);raise SystemExit(1)
    journal.emit('actual_memory_enforcement_established',dict(kind='CGROUP_V2',aggregate_bytes=1536*1024**2,controller_bytes=256*1024**2,source_bytes=1024**3,swap=0))
    github_env=dict(PATH='/usr/bin:/bin',HOME=str(args.output.parent),GH_TOKEN=token,GH_HOST='github.com')
    progress=Progress()
    try:
        ca,_=verified_trust();hostaddr=resolve_addresses(progress)
    except BaseException as exc:
        stop_early(journal,'PREPARATION_FAILED',type(exc).__name__);raise SystemExit(1)
    from .operational_source import read
    def source_reader_factory(runner):
        return lambda _row:read('listing',dict(council='bolton',semantics='RECEIVED',start='2026-10-16',end='2026-10-16'),root=journal.root/'source',stop_file=journal.root/'STOP',memory_group=memory.source,observe=runner.observe_source)
    result,code=run_hosted(urls=urls,journal=journal,gh_runner=lambda command,**kw:subprocess.run(command,env=github_env,**kw),source_reader_factory=source_reader_factory,ssl={'sslmode':'verify-full','sslrootcert':str(ca)},
                           hostaddr=hostaddr,memory=memory,evidence_head=os.environ['PIPELINE_EVIDENCE_HEAD'],manifest_sha256=hashlib.sha256(Path(MANIFEST_PATH).read_bytes()).hexdigest(),revision=os.environ['PIPELINE_REVIEWED_SHA'])
    raise SystemExit(code)


if __name__=='__main__':main()
