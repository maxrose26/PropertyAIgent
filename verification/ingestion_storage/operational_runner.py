"""One manual capture-once/retained-screening acceptance, not a consumer.

Production entrypoint requires an exact, separately owner-released registration.
The required path never imports or enables an Application writer.
"""
import argparse,hashlib,json,os,resource,signal,socket,subprocess,sys,time
from contextlib import contextmanager
from datetime import date,datetime,timezone,timedelta
from pathlib import Path
from urllib.parse import quote
from app.ingestion.ledger import digest,DEFAULT_LIMITS,Denied
from app.ingestion.coordinator import Coordinator
from app.ingestion.idox_adapter import IdoxListingContract
from app.ingestion.batching import capture_once,batch_plans,process_batch
from verification.discovery.idox_window import WindowConfig
from .operational_controller import DatabaseBudget,ControllerLedger,batch_allocation
from .operational_publication import GitHub,Uncertain,canonical,BRANCH
from .operational_journal import Journal
from .operational_owner import Owner,item,SCOPE,ROLES,SECRETS
from .tls_trust import verified_trust,owned_resources,PEM_SHA256
from .connection_diagnostics import PreparationFailure
from .operational_preparation import Progress,prepare_connection

AUTHORITY='AUTHORISE_BOLTON_CAPTURE_QUEUE_SUCCESSOR_ONCE_20261018'
DIAGNOSTIC_AUTHORITY='AUTHORISE_INGESTION_ACTIONABLE_CONNECTION_DIAGNOSTIC_ONCE_20261018'
DIAGNOSTIC_STATE='operational-actionable-diagnostic-once-20261018'
QUALIFICATION='1833eb7349dda9b1dceb0924abd7380b2f24e591e13ad34ec37dd8e4763df3f2'
CONTRACT='bolton-received-idox-coordinator-v1'

def restricted_url(role,password):
    """Same in-memory value goes to protected mapping and native URL parser."""
    if role not in ROLES:raise ValueError('EXACT_OPERATIONAL_MAPPING_ROLE')
    return 'postgresql://'+quote(role+'.zcikcfgpblzuzpanpdqd',safe='')+':'+quote(password,safe='')+'@aws-0-eu-west-2.pooler.supabase.com:5432/postgres'

class Runner:
    """Injected IO enables the actual wrapper to be rehearsed without sources."""
    def __init__(self,registration,journal,connector,*,source_reader,github,
                 url_factory,identity='postgres',ssl=None,memory=None,hostaddr=None,started=None):
        self.r=registration;self.journal=journal;self.emit=journal.emit;self.source_reader=source_reader;self.github=github;self.url_factory=url_factory;self.ssl=ssl;self.memory=memory
        self.operation_phase='INITIALISATION';self.started=started if started is not None else time.monotonic();self.phase='admin';self.phase_started=self.started;self.admin_seconds=0;self.runtime_seconds=0;self.hostaddr=hostaddr
        self.expiry=datetime.fromisoformat(registration['expires_at'])
        self.bindings=dict(revision=registration['revision'],workflow_sha256=registration['controller_sha256'],manifest_sha256=registration['manifest_sha256'])
        self.owner=Owner(connector,self.emit,self.check,identity=identity,expiry=self.expiry,bindings=self.bindings)
        self.owner.reuse_installed=registration.get('reuse_accepted_operational_installation',False)
        self.owner.apply_policy=registration.get('mode')!='CONNECTION_DIAGNOSTIC_ONLY'
        self.source_attempts=0;self.source_resources={'status':'NOT_STARTED','attempted_requests':0,'received_body_bytes':0};self.receipts={};self.plans=[];self.capture=None;self.capture_key=None;self.batch_bindings={};self.evidence_head=registration['evidence_head'];self.closed=True;self.diagnosing=False;self.baseline=owned_resources()

    def check(self):
        # Diagnosis may use its reporting reserve, never a weaker memory group.
        # Once native groups are removed, only local final reporting is allowed.
        if self.memory is not None:
            if hasattr(self,'memory_closure'):raise Denied('RESOURCE_ENVELOPE_CLOSED_NO_MORE_OPERATIONS')
            self.memory.snapshot()
        now=time.monotonic()
        if self.diagnosing:
            admin_now=self.admin_seconds+(now-self.phase_started if self.phase!='runtime' else 0)
            if now-self.started>=475 or now-self.diagnostic_started>=25 or admin_now>=240:raise Denied('DIAGNOSTIC_RESERVE_EXHAUSTED')
            return
        if datetime.now(timezone.utc)>=self.expiry or now-self.started>=450:raise Denied('EXPIRY_OR_JOB_CLOSURE_RESERVE')
        if self.phase=='admin' and self.admin_seconds+now-self.phase_started>=210:raise Denied('ADMIN_TEARDOWN_RESERVE')
        if self.phase=='teardown' and self.admin_seconds+now-self.phase_started>=240:raise Denied('ADMIN_TOTAL_BOUND')
        if self.phase=='runtime' and self.runtime_seconds+now-self.phase_started>=300:raise Denied('RUNTIME_TOTAL_BOUND')
        if (self.journal.root/'STOP').exists():raise Denied('OWNER_STOP')
        size=sum(p.stat().st_size for p in self.journal.root.rglob('*') if p.is_file())
        if size>2*1024**2-128*1024:raise Denied('COMBINED_OUTPUT_CLOSURE_RESERVE')

    @contextmanager
    def phase_as(self,name):
        old=self.phase;now=time.monotonic()
        if old=='runtime':self.runtime_seconds+=now-self.phase_started
        else:self.admin_seconds+=now-self.phase_started
        self.phase=name;self.phase_started=now
        try:self.check();yield
        finally:
            now=time.monotonic()
            if name=='runtime':self.runtime_seconds+=now-self.phase_started
            else:self.admin_seconds+=now-self.phase_started
            self.phase=old;self.phase_started=now

    def archive(self,raw):
        sha=hashlib.sha256(raw).hexdigest();directory=self.r['evidence_directory']+'/capture'
        self.evidence_head=self.github.publish({'source.json':raw},directory=directory,expected_head=self.evidence_head)
        return dict(commit=self.evidence_head,path=directory+'/source.json',sha256=sha,bytes=len(raw),readback_verified=True)

    @contextmanager
    def slot(self,key,bindings,authority):
        slots=[self.capture_key]+[p['key'] for p in self.plans]
        allocation=batch_allocation(slots,self.receipts,sealed_sha256=digest(self.receipts),slot_key=key)
        remaining=allocation['remaining']
        if remaining['driver_statements']<80 or remaining['connection_attempts']<2:raise Denied('INSUFFICIENT_NEXT_SLOT_RESERVATION')
        prior=self.receipts.get(key,{})
        budget=DatabaseBudget(slot_key=key,previous=prior.get('database'),connections=min(16,remaining['connection_attempts']),statements=min(120,remaining['driver_statements']),seconds=min(165,remaining['supervised_seconds']),returned_bytes=remaining['returned_data_value_bytes'],emit=self.emit,stop_file=self.journal.root/'STOP')
        engines=[];started=time.monotonic();success=False
        try:
            engines=[budget.engine(self.owner.urls[r],ssl=self.ssl,hostaddr=self.hostaddr) for r in ROLES]
            ledger=ControllerLedger(engines[0],budget=budget,owner='required_once',authority=authority,bindings=bindings,broker_engine=engines[1])
            yield Coordinator(ledger,{CONTRACT:IdoxListingContract(CONTRACT,WindowConfig('bolton','RECEIVED',date(2026,10,16),date(2026,10,16),0),QUALIFICATION)}),budget
            success=True
        finally:
            account=budget.close(engines);elapsed=time.monotonic()-started
            receipt=dict(database=account,supervised_seconds=prior.get('supervised_seconds',0)+elapsed,cleanup=account['cleanup'])
            self.receipts[key]=receipt;self.emit('slot_closed',dict(key=key,receipt=receipt,success=success))
            if account['cleanup']!='CLOSED':self.closed=False;raise Uncertain('RUNTIME_DATABASE_CLOSURE')
            batch_allocation(slots,self.receipts,sealed_sha256=digest(self.receipts),slot_key=key)

    def setup(self):
        account=self.github.call('GET','user')
        if account.get('login')!='maxrose26':raise ValueError('EXACT_OWNER_GITHUB_ACCESS')
        self.operation_phase='ADMIN_PREFLIGHT';self.owner.preflight()
        self.operation_phase='ADMIN_INSTALL_OR_REUSE';self.owner.install()
        self.operation_phase='CREDENTIAL_MAPPING_ACTIVATION';self.owner.map_and_activate(self.github,url_factory=self.url_factory)
        identity=dict(subject=SCOPE,task='DISCOVERY',contract=CONTRACT,revision=self.r['manifest_sha256'])
        root=item(identity,max_attempts=1,limits=dict(DEFAULT_LIMITS,requests=10,bytes=3000000,rows=60,pages=6))
        self.capture_key=root['key']
        # Validate BOTH real restricted logins before any source grant exists.
        # This slot's counters carry into capture; it cannot reset allowances.
        self.operation_phase='RESTRICTED_CONNECTION_QUALIFICATION'
        with self.phase_as('runtime'):
            with self.slot(self.capture_key,{},'NO_EXECUTION_AUTHORITY') as (_,budget):
                for engine in budget.engines:
                    with engine.connect():pass
        self.emit('restricted_connections_verified_before_authority',dict(capture_key=self.capture_key))
        if self.r.get('mode')=='CONNECTION_DIAGNOSTIC_ONLY':return
        self.operation_phase='AUTHORITY_REGISTRATION'
        self.capture_bindings=self.owner.register([root],AUTHORITY+'_CAPTURE',capture_key=self.capture_key,source_calls=1)
        self.emit('required_setup_committed',dict(capture_key=self.capture_key))

    def capture_once(self):
        self.operation_phase='SOURCE_CAPTURE_RETENTION'
        if self.capture is not None:raise Denied('CAPTURE_ALREADY_RETAINED_NO_SOURCE_REPLAY')
        with self.phase_as('runtime'):
            with self.slot(self.capture_key,self.capture_bindings,AUTHORITY+'_CAPTURE') as (co,budget):
                def read(row):
                    self.check();self.source_attempts+=1
                    self.source_resources={'status':'ATTEMPTED_ACCOUNTING_UNCERTAIN','attempted_requests':None,'received_body_bytes':None}
                    self.emit('source_invocation_intent',dict(ordinal=self.source_attempts))
                    observed=self.source_reader(row)
                    self.source_resources=dict(status='RETURNED',worker=observed[0].get('resource'),supervisor=observed[1])
                    self.emit('source_invocation_returned',dict(ordinal=self.source_attempts,resources=self.source_resources))
                    return observed
                self.capture=capture_once(co,self.capture_key,read,self.archive,self.check)
        if self.capture['kind']!='LISTING_RECEIPT_V1':
            self.emit('capture_processing_blocked',dict(checkpoint=self.capture));return
        self.plans=batch_plans(self.capture_key,self.capture)
        if self.plans:
            prepared=[]
            for record in self.capture['records']:
                prepared.append(item(dict(subject=dict(kind='APPLICATION',council='bolton',reference=record['reference']),task='SCREENING',contract='listing-screen-v1',revision=digest(record)),dependencies=[self.capture_key]))
            batches=[item({k:p[k] for k in ('subject','task','contract','revision')},dependencies=p['dependencies'],checkpoint=p['checkpoint']) for p in self.plans]
            # The completed capture is also bound for exact retained-parent
            # reads; it is not inserted or granted another source allowance.
            root_binding=item(dict(subject=SCOPE,task='DISCOVERY',contract=CONTRACT,revision=self.r['manifest_sha256']))
            self.batch_bindings=self.owner.register(batches,AUTHORITY+'_SCREEN',capture_key=self.capture_key,source_calls=0,prepared=[root_binding,*prepared])
        self.save_progress()

    def save_progress(self):
        state=dict(capture_key=self.capture_key,capture_sha256=digest(self.capture),plans=self.plans,receipts=self.receipts,receipts_sha256=digest(self.receipts),evidence_head=self.evidence_head)
        self.journal.save('progress.json',state);self.emit('progress_saved',dict(sha256=digest(state)))

    def screen(self,*,pause_after=None):
        self.operation_phase='RETAINED_QUEUE_SCREENING'
        # A planned pause is an offline rehearsal injection, not a production
        # CLI option. Resume verifies durable progress and uses no source client.
        saved=self.journal.progress()
        if saved['capture_sha256']!=digest(self.capture) or saved['receipts_sha256']!=digest(self.receipts) or saved['receipts']!=self.receipts:raise Uncertain('DURABLE_PROGRESS_BINDING')
        delivered=0
        for plan in self.plans:
            key=plan['key']
            if key in self.receipts:continue
            with self.phase_as('runtime'):
                with self.slot(key,self.batch_bindings,AUTHORITY+'_SCREEN') as (co,budget):
                    result=process_batch(co,key,check=lambda:(self.check(),budget.check()))
            if result['outcome'] not in {'BATCH_SCREENED','BATCH_ALREADY_COMPLETE'}:raise Uncertain('SCREENING_OUTCOME')
            self.emit('batch_outcome',dict(key=key,outcome=result['outcome'],children=result.get('children',[])))
            delivered+=1;self.save_progress()
            if pause_after is not None and delivered==pause_after:return 'PAUSED_CLOSED_NO_SOURCE_REPLAY'
        return 'SCREENING_COMPLETE'

    @classmethod
    def resume(cls,previous):
        """Fresh bounded queue execution with an existing secure RAM handoff.

        The finite owner supervisor remains alive. Losing that supervisor or
        its credentials is reconciliation-required, never remapping/replay.
        """
        import copy
        previous.check();state=previous.journal.progress()
        if not previous.closed or state['receipts']!=previous.receipts or not previous.owner.urls:raise Uncertain('RESUME_CLOSURE_ACCOUNTING_OR_CREDENTIAL_HANDOFF')
        current=object.__new__(cls);current.__dict__=previous.__dict__.copy()
        current.owner=copy.copy(previous.owner);current.owner.check=current.check;current.github.check=current.check
        current.receipts=json.loads(json.dumps(state['receipts']))
        def no_source(_):raise Denied('RETAINED_EXECUTION_CANNOT_REFETCH')
        current.source_reader=no_source
        with current.phase_as('runtime'):
            with current.slot(current.capture_key,current.capture_bindings,AUTHORITY+'_CAPTURE') as (co,budget):
                root=co.ledger.get(current.capture_key)
                if root['state']!='COMPLETE' or digest(root['checkpoint'])!=state['capture_sha256']:raise Uncertain('CAPTURE_CHECKPOINT_IDENTITY')
                current.capture=root['checkpoint']
        current.plans=batch_plans(current.capture_key,current.capture)
        if current.plans!=state['plans']:raise Uncertain('EXACT_RECOVERED_BATCH_MEMBERSHIP')
        current.emit('retained_execution_reconstructed',dict(capture_sha256=state['capture_sha256'],source_calls=0,counters_carried=True))
        current.save_progress();return current

    def finish(self):
        self.operation_phase='TEARDOWN_PUBLICATION_CLOSURE'
        with self.phase_as('teardown'):self.owner.teardown(self.github)
        self.emit('required_access_disabled',dict(roles=list(ROLES),authorities=self.owner.authorities))
        self.check()
        outcome='CAPTURED_PROCESSING_BLOCKED' if self.capture['kind']!='LISTING_RECEIPT_V1' else 'REQUIRED_CAPTURE_SCREENING_ACCEPTED_ACCESS_DISABLED'
        result=dict(status='ACCESS_DISABLED_FINAL_CLOSURE_PENDING',rows=len(self.capture.get('records',[])),batches=len(self.plans),capture_sha256=digest(self.capture),slot_receipts=self.receipts,admin=self.owner.accounting(),unit_facts='UNKNOWN_OUTSIDE_SCOPE',application_writes=0,source_observations=1,cleanup='CLOSURE_PENDING',historical_uncertainty_preserved=True)
        self.emit('required_result',result)
        # The sealed execution chain is archived separately from the publisher's
        # acknowledgement suffix; final owner output supplies that suffix hash.
        self.journal.save('final-result.json',result)
        self.evidence_head=self.github.publish({'events.jsonl':self.journal.file.read_bytes(),'final-result.json':canonical(result)},directory=self.r['evidence_directory']+'/completed',expected_head=self.evidence_head)
        components=self.closure('DISABLED_VERIFIED')
        result.update(closure_components=components)
        if components['overall']!='CLOSED':raise Uncertain('OWNED_PROCESS_OR_SOCKET_CLOSURE')
        result.update(status=outcome,cleanup='CLOSED',native_memory_proof=self.memory is not None)
        from collections import Counter
        from app.ingestion.listing_screening import screen_row
        screens=[screen_row(row) for row in self.capture.get('records',[])]
        usable=sum(x['proposal_usable'] for x in screens)
        if self.capture['kind']=='LISTING_RECEIPT_V1':
            if not screens:outcome='DISCOVERY_EXPLICIT_ZERO_ACCESS_DISABLED_SCREENING_NOT_EXERCISED'
            elif usable<len(screens):outcome='PARTIAL_PROPOSAL_COVERAGE_ACCESS_DISABLED'
        result.update(status=outcome,usable_proposals=usable,screening_dispositions=dict(Counter(x['disposition'] for x in screens)),citation_leads=sum(len(x['citations']['occurrences']) for x in screens),source_resources=self.capture.get('resources'),supervised_seconds=time.monotonic()-self.started,runtime_supervised_seconds=self.runtime_seconds,github_cli_invocations=self.github.requests)
        self.emit('final_closure_verified',dict(status=outcome,cleanup='CLOSED',native_memory_proof=self.memory is not None,new_sockets=0,live_children=0))
        result.update(evidence_commit=self.evidence_head,audit_sha256=hashlib.sha256(self.journal.file.read_bytes()).hexdigest(),audit_chain_head=self.journal.head)
        self.journal.save('final-result.json',result)
        return result

    def observe_source(self,event,payload):
        if event not in {'source_supervisor_observed','source_worker_resource_observed'}:raise ValueError('SOURCE_RESOURCE_EVENT')
        self.source_resources[event]=payload
        self.emit(event,{'actual':payload})

    def accounting(self):
        now=time.monotonic()
        admin=self.admin_seconds+(now-self.phase_started if self.phase!='runtime' else 0)
        runtime=self.runtime_seconds+(now-self.phase_started if self.phase=='runtime' else 0)
        return dict(administration=dict(self.owner.accounting(),supervised_seconds=admin),
                    runtime=dict(slot_receipts=self.receipts,supervised_seconds=runtime),
                    github_cli_invocations=self.github.requests,
                    active_seconds=now-self.started,
                    historical_accounting_gaps='PRESERVED_NOT_RECONSTRUCTED')

    def closure(self,access):
        """Same positive checks on success/failure; no automatic process kill.

        This is controller/owned-resource closure, not evidence that the outer
        systemd scope has disappeared after this process exits.
        """
        process=dict(status='UNCERTAIN',native_memory_proof=self.memory is not None)
        try:
            if self.memory is not None:
                if not hasattr(self,'memory_closure'):self.memory_closure=self.memory.close()
                proof=self.memory_closure
                process['memory']=proof
                group_closed=proof.get('owned_groups_removed') is True and proof.get('owned_survivors')==0
            else:group_closed=True # disposable-only; production requires native memory at entry
            after=owned_resources()
            process.update(new_socket_count=len(after['socket_fds']-self.baseline['socket_fds']),live_child_count=len(after['children']))
            if group_closed and process['new_socket_count']==0 and process['live_child_count']==0:process['status']='CLOSED'
        except BaseException:pass
        a=self.owner.accounting()
        failed_admin_closed=(a.get('failed_native_connections',0)==a.get('failed_native_finished',0) or process.get('new_socket_count')==0)
        connection_closed=(failed_admin_closed and a['connections_opened']==a['connections_closed'] and self.closed and
            all(x['database'].get('cleanup')=='CLOSED' and x['database'].get('connections_closed') is True for x in self.receipts.values()))
        connection=dict(status='CLOSED' if connection_closed else 'UNCERTAIN',administrative_opened=a['connections_opened'],administrative_closed=a['connections_closed'],failed_administrative_attempts=a.get('failed_native_connections',0),failed_administrative_closed=failed_admin_closed,runtime_slots=len(self.receipts))
        safe=access=='DISABLED_VERIFIED' and not a['uncertain_effect'] and not self.github.mutation_uncertain
        overall='CLOSED' if safe and connection_closed and process['status']=='CLOSED' else 'UNCERTAIN'
        return dict(access=access,connections=connection,process=process,overall=overall,outer_scope_removal='NOT_VERIFIABLE_BEFORE_CONTROLLER_EXIT')

    def failed(self,exc):
        """Shared production/rehearsal exit, independent of ledger construction."""
        from .connection_diagnostics import safe_failure
        self.diagnosing=True;self.diagnostic_started=time.monotonic()
        failed_phase=self.operation_phase
        diagnostics={};invalidation='UNCERTAIN_RECONCILE';access='UNRECONCILED'
        # A known failure may invoke the fixed safety disposition. An uncertain
        # admin mutation is never automatically replayed or compensated.
        try:
            if self.github.mutation_uncertain:
                invalidation='UNCERTAIN_RECONCILE' if self.owner.authorities else 'NOT_REQUIRED_NO_AUTHORITY'
                raise Uncertain('PRIOR_GITHUB_MUTATION_UNCERTAIN')
            invalidation=self.owner.invalidate_failure()
            if (invalidation=='ACKNOWLEDGED_READBACK' or (not self.owner.authorities and self.owner.urls and not self.owner.effect_uncertain)):
                with self.phase_as('teardown'):self.owner.teardown(self.github)
                access='DISABLED_VERIFIED'
        except BaseException:
            if not self.github.mutation_uncertain:invalidation=self.owner.invalidation
        try:
            diagnostics=self.owner.diagnostics()
            names=self.github.names()
            self.emit('failure_secret_names_observed',dict(names={n:n in names for n in SECRETS.values()},database_url_present='DATABASE_URL' in names))
        except BaseException:
            diagnostics['completion']='INCOMPLETE_RECONCILE'
        components=self.closure(access)
        result=dict(status='STOP_RECONCILE_NO_RETRY',cleanup=components['overall'],closure_components=components,
            failure=safe_failure(exc,'EXECUTION'),operation_phase=failed_phase,authority_invalidation=invalidation,
            access=access,diagnostics=diagnostics,owned_cleanup=components['process'],
            accounting=self.accounting(),source_observations_attempted=self.source_attempts,source_capture_retained=self.capture is not None,source_resources=self.source_resources,
            application_writes=0,pipeline_retry='HELD',stage4='OPEN',historical_uncertainty_preserved=True)
        try:self.emit('stopped',result)
        except BaseException:result['audit_stop_record']='UNCERTAIN'
        return result

    def execute(self):
        try:
            self.setup()
            if self.r.get('mode')=='CONNECTION_DIAGNOSTIC_ONLY':
                with self.phase_as('teardown'):self.owner.teardown(self.github)
                components=self.closure('DISABLED_VERIFIED')
                if components['overall']!='CLOSED':raise Uncertain('OWNED_PROCESS_OR_SOCKET_CLOSURE')
                return dict(status='RESTRICTED_ROUTE_QUALIFIED_ACCESS_DISABLED',cleanup='CLOSED',closure_components=components,accounting=self.accounting(),owned_cleanup=components['process'],source_observations_attempted=0,execution_grants_created=0,application_writes=0,pipeline_retry='HELD')
            self.capture_once()
            if self.plans:self.screen()
            result=self.finish();result['accounting']=self.accounting();return result
        except BaseException as exc:return self.failed(exc)


def prepare_runner(r,raw,started,*,journal,memory,progress,dns_run=subprocess.run,dns_command=None):
    """The actual credential-dependent preparation of the Runner, in explicit stages. Raises PreparationFailure (fixed stage + fixed reason) and nothing else.

    No database connection is made here: `connect` is only a closure handed to the Runner. Seams (`dns_run`, `dns_command`) exist solely so the real stage code can be
    exercised against controlled local fixtures; production passes neither."""
    prepared=prepare_connection(r,raw,progress=progress,dns_run=dns_run,dns_command=dns_command)
    ca,selected,connect=prepared.ca,prepared.hostaddr,prepared.connect
    with progress.stage('RUNNER_COMPONENTS'):
        holder={}
        try:from .operational_source import read
        except ImportError:raise PreparationFailure('RUNNER_COMPONENTS','COMPONENT_IMPORT_FAILED') from None
        github=GitHub(journal.emit,lambda:holder['runner'].check())
        def reader(_):return read('listing',dict(council='bolton',semantics='RECEIVED',start='2026-10-16',end='2026-10-16'),root=journal.root/'source',stop_file=journal.root/'STOP',memory_group=memory.source,observe=holder['runner'].observe_source)
    with progress.stage('RUNNER_CONSTRUCTION'):
        try:runner=Runner(r,journal,connect,source_reader=reader,github=github,url_factory=restricted_url,ssl={'sslmode':'verify-full','sslrootcert':str(ca)},memory=memory,hostaddr=selected,started=started)
        except (KeyError,TypeError,ValueError,AttributeError):raise PreparationFailure('RUNNER_CONSTRUCTION','RUNNER_CONSTRUCTION_FAILED') from None
        holder['runner']=runner
    return runner


def validate_registration(body,sha):
    if hashlib.sha256(body).hexdigest()!=sha:raise ValueError('REGISTRATION_SHA256')
    r=json.loads(body)
    expected_authority={'REQUIRED_CAPTURE_SCREENING':AUTHORITY,'CONNECTION_DIAGNOSTIC_ONLY':DIAGNOSTIC_AUTHORITY}.get(r.get('mode'))
    if expected_authority is None or r.get('authority')!=expected_authority or r.get('status')!='OWNER_APPROVED_REQUIRED_ONCE' or r.get('scope')!=SCOPE or r.get('roles')!=list(ROLES) or r.get('risk_acceptance')!='ACCEPT_POSSIBLE_PROVIDER_SCRAM_VERIFIER_RETENTION_WORKER_EFFECT_ONCE':raise ValueError('EXACT_OPERATIONAL_APPROVAL_REQUIRED')
    if r.get('reuse_accepted_operational_installation') is not True or r.get('baseline_control_sha256')!='0d829597f1422fef0af13920d5749c5751adf6d896588f379c400db7b3fa27cf' or r.get('accepted_cleanup_evidence')!='8dc4a36bc5565318e138d192bf2f7e96906f048f':raise ValueError('ACCEPTED_INSTALLED_STATE_REQUIRED')
    expiry=datetime.fromisoformat(r['expires_at']);now=datetime.now(timezone.utc)
    if expiry.tzinfo is None or not now<expiry<=now+timedelta(hours=24):raise ValueError('ORIGINAL_OPERATIONAL_EXPIRY')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if revision!=r['revision'] or subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip()!=r['tree'] or subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise ValueError('CLEAN_REVIEWED_CHECKOUT')
    for path,digest_ in r['hashes'].items():
        p=Path(path)
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest_:raise ValueError('REVIEWED_CONTENT_BINDING')
    controller=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if r['controller_sha256']!=controller or r['ca_sha256']!=PEM_SHA256 or not r['evidence_directory'].startswith('docs/design/ingestion-operational-execution-'):raise ValueError('CONTROLLER_CA_EVIDENCE_BINDING')
    return r

def main():
    p=argparse.ArgumentParser();p.add_argument('--registration',type=Path,required=True);p.add_argument('--registration-sha256',required=True);a=p.parse_args()
    if sys.platform!='linux' or not sys.stdin.isatty() or not sys.stderr.isatty():raise SystemExit('OWNER_LINUX_SECURE_TTY_REQUIRED')
    if any(os.environ.get(k) for k in ('GH_TOKEN','GITHUB_TOKEN','GH_DEBUG','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN')):raise SystemExit('EXISTING_KEYRING_AUTH_ONLY')
    if os.environ.get('GH_HOST','github.com')!='github.com' or any(os.environ.get(k) for k in ('GH_CONFIG_DIR','GH_HTTP_UNIX_SOCKET','SSL_CERT_FILE','SSL_CERT_DIR','HTTPS_PROXY','https_proxy','HTTP_PROXY','http_proxy','ALL_PROXY','all_proxy')):raise SystemExit('UNREVIEWED_GITHUB_ROUTE_OR_TRUST_OVERRIDE')
    if any(k.startswith('PG') for k in os.environ):raise SystemExit('LIBPQ_ENVIRONMENT_OVERRIDE')
    if a.registration.is_symlink() or a.registration.stat().st_size>32768:raise SystemExit('REGISTRATION_BOUND')
    r=validate_registration(a.registration.read_bytes(),a.registration_sha256)
    from .operational_memory import OperationalMemory
    memory=OperationalMemory() # Positive kernel enforcement BEFORE credentials.
    state=Path.home()/'.local/state/propertyaigent';state.mkdir(mode=0o700,exist_ok=True,parents=True)
    journal=Journal(state/(DIAGNOSTIC_STATE if r['mode']=='CONNECTION_DIAGNOSTIC_ONLY' else 'operational-capture-queue-successor-once-20261018'))
    journal.emit('consumed',dict(authority=r['authority'],registration_sha256=a.registration_sha256))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    from .credential_mapping import secure_migration_input
    from .operational_outcome import session
    progress=Progress()
    baseline=owned_resources()
    prepare=lambda raw,started:prepare_runner(r,raw,started,journal=journal,memory=memory,progress=progress)
    result=session(journal,r['expires_at'],secure_migration_input,prepare,memory=memory,progress=progress,baseline=baseline)
    # A cleanly closed failure remains a failed execution; never signal success
    # or permit an owner to confuse cleanup with route qualification.
    raise SystemExit(0 if result.get('cleanup')=='CLOSED' and result.get('status')!='STOP_RECONCILE_NO_RETRY' else 1)

if __name__=='__main__':main()
