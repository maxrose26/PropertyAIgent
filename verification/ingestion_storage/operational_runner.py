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
from .operational_controller import DatabaseBudget,ControllerLedger,batch_allocation,run_cancel_used
from .operational_publication import GitHub,Uncertain,canonical,BRANCH,blob_bytes
from .operational_journal import Journal
from .operational_owner import Owner,item,SCOPE,ROLES,SECRETS
from .tls_trust import verified_trust,owned_resources,PEM_SHA256
from .connection_diagnostics import PreparationFailure,fixed_stop_reason
from .operational_preparation import Progress,prepare_connection

AUTHORITY='AUTHORISE_BOLTON_CAPTURE_QUEUE_SUCCESSOR_ONCE_20261018'
DIAGNOSTIC_AUTHORITY='AUTHORISE_INGESTION_ACTIONABLE_CONNECTION_DIAGNOSTIC_ONCE_20261018'
DIAGNOSTIC_STATE='operational-actionable-diagnostic-once-20261018'
MATRIX_MODE='RESTRICTED_CONNECTION_MATRIX_ONLY'
MATRIX_AUTHORITY='AUTHORISE_INGESTION_RESTRICTED_CONNECTION_MATRIX_ONCE_20261018'
MATRIX_STATE='operational-restricted-connection-matrix-once-20261018'
# Settled successor of the consumed 2026-10-19 operational run: identical lifecycle plus ONE fixed settling period between activation and the first restricted contact.
SETTLED_MODE='REQUIRED_CAPTURE_SCREENING_SETTLED'
SETTLED_AUTHORITY='AUTHORISE_BOLTON_CAPTURE_QUEUE_SETTLED_ONCE_20261019'
SETTLED_STATE='operational-capture-queue-settled-once-20261019'
SETTLE_SECONDS=30          # an experimental interval, NOT a provider guarantee
# The consumed predecessor, preserved: its registration and complete audit are bound by hash and are never reused.
SETTLED_PREDECESSOR=dict(state_directory='operational-capture-queue-successor-once-20261018',registration_sha256='1034c92ee3e654bc4ccf1f37b6c5e20d0b15d1cce3f3982a3dfbdae2a402455c',
                         events_sha256='2af82ca9247366d5ada8e0873ea97abaab84cdeb8dfb81c3f3efb146708059b0',final_result_sha256='ffedfe33c342f6e808376a1617ac14a1895b863f87e4958d4edbdeaa346c5609')
# Second settled generation (corrected preflight). The first settled generation above is CONSUMED (its run stopped in preflight) and is kept only so that its record and registration
# remain recognisable; its namespace exists and can never be reused.
SETTLED_R2_MODE='REQUIRED_CAPTURE_SCREENING_SETTLED_R2'
SETTLED_R2_AUTHORITY='AUTHORISE_BOLTON_CAPTURE_QUEUE_SETTLED_R2_ONCE_20261019'
SETTLED_R2_STATE='operational-capture-queue-settled-r2-once-20261019'
SETTLED_R2_PREDECESSOR=dict(
    run_1=SETTLED_PREDECESSOR,
    run_2=dict(state_directory=SETTLED_STATE,registration_sha256='fa3a94c8b27b32e0ab07119530caf001632768f7c88a3e0ff87fc385434b4634',
               events_sha256='c4dc12776784ca678f5a1a0558f421ba405d0a243df52f5e78008a9ef66fb6cc',final_result_sha256='8116e06698669fb03a9550860ced87685fa4e483a9f93921989a40f295f528c3'))
# mode -> (authority, state directory, bound predecessor); every settled mode applies the one fixed settling period.
DIRECT_MODE='DIRECT_ROUTE_DIAGNOSTIC_ONLY'
DIRECT_AUTHORITY='AUTHORISE_INGESTION_DIRECT_RESTRICTED_ROUTE_DIAGNOSTIC_ONCE_20261020'
DIRECT_STATE='operational-direct-route-diagnostic-once-20261020'
# The direct-route diagnostic binds all three consumed runs by hash; it applies no policy and accepts only the retained successor-policy installation.
DIRECT_PREDECESSOR=dict(SETTLED_R2_PREDECESSOR,run_3=dict(state_directory=SETTLED_R2_STATE,registration_sha256='4186c88fb6ce36c73b3eac03e6ad54d4c0f6aa6c9ca81d286789777e98261e8c',
                        events_sha256='945b1b500676ab0a43e6982e0a65fb849e75637e89e915d790182e91c284e159',final_result_sha256='389d4623f0b86be450123b9255ac84c2d1184882c2797e6834b3ab47410bd40f'))
DIAGNOSTIC_MODES=('CONNECTION_DIAGNOSTIC_ONLY',DIRECT_MODE)
# Stable restricted credentials: the OWNER provisions them once (and can revoke them) with the administrative credential; the restricted RUNTIME later qualifies them with the restricted
# credentials alone (stable_qualification.py). Neither mode issues a grant, exception, source request or application write.
STABLE_PROVISION_MODE='STABLE_CREDENTIAL_PROVISIONING'
STABLE_PROVISION_AUTHORITY='AUTHORISE_INGESTION_STABLE_CREDENTIAL_PROVISIONING_ONCE_20261020'
STABLE_PROVISION_STATE='operational-stable-provisioning-once-20261020'
STABLE_REVOKE_MODE='STABLE_CREDENTIAL_REVOCATION'
STABLE_REVOKE_AUTHORITY='AUTHORISE_INGESTION_STABLE_CREDENTIAL_REVOCATION_ONCE_20261020'
STABLE_REVOKE_STATE='operational-stable-revocation-once-20261020'
STABLE_VALIDITY_DAYS=90      # initial password validity; renewal extends VALID UNTIL only (no password change)
STABLE_MODES={STABLE_PROVISION_MODE:(STABLE_PROVISION_AUTHORITY,STABLE_PROVISION_STATE,'THIS_FINITE_STABLE_CREDENTIAL_PROVISIONING_ONLY'),
              STABLE_REVOKE_MODE:(STABLE_REVOKE_AUTHORITY,STABLE_REVOKE_STATE,'THIS_FINITE_STABLE_CREDENTIAL_REVOCATION_ONLY')}
# Stable-credential pipeline OWNER controller: fixed read-only readback -> capture authority -> (restricted hosted job retains the capture) -> screening authority -> (hosted job screens) ->
# authority invalidation -> final readback. It never holds the restricted passwords and never changes a credential; the restricted job never holds the administrative credential.
PIPELINE_MODE='STABLE_PIPELINE_AUTHORITY'
PIPELINE_AUTHORITY='AUTHORISE_INGESTION_STABLE_PIPELINE_AUTHORITY_ONCE_20261020'
PIPELINE_STATE='operational-stable-pipeline-once-20261020'
PIPELINE_BINDING=dict(
    valid_until='2027-01-17T16:14:12+00:00',hard_stop_generation=1,grant_minutes=55,screening_grant_minutes=30,poll_seconds=30,capture_wait_seconds=2700,screening_wait_seconds=600,
    provisioning=dict(registration_sha256='b7e00b48d659b4fa83cd72d14efe734846c2d9d2e699f6998e509e3c3f280264',events_sha256='a26f9d1f51d8e908431cfdebf2bf20f6362b7bcbcecb35717a13935017155a19',
                      final_result_sha256='51aea5d5ce0a3515b369b0d098a5c3da73a210ff86034f1f9e368d654274d3e6'),
    qualification=dict(run_id=39284253302,artifact_id=12212818855,artifact_zip_sha256='b02da6fcf1658f627f4935db0a998fb3764498b3e15b6d57ad2ab135ba15db58',revision='46b9356d352efcde39df9e1505db582543adecee'),
    hosted_workflow='.github/workflows/stage4-stable-pipeline-once.yml')
# Finite owner totals (normal, through invalidation and the final readback, including failure diagnostics). MEASURED, not estimated: the real Owner methods run against a scripted connection
# (tests/test_ingestion_pipeline_invalidation.py) count 52 statements / 5 connections on the normal path (readback 9, capture authority 11, ledger read 5, screening authority 22 for the
# maximum 12 batches, ledger read 5), 73 / 7 through the end-of-run invalidation (12) and final readback (9), and at most 71 when a failure at the very end of the normal path is followed by
# the reserved invalidation (12) and diagnostics (7). The allowances keep a reserve so that ENDING an authority and diagnosing can never be refused for want of capacity. The earlier
# placeholder (48 / 60 / 72) was exhausted by the normal path (52 > 48), which is how the invalidation was left undone in the first rehearsal.
PIPELINE_OWNER_LIMITS=dict(connections=(8,10),commands=(56,80,96))
# GitHub requests (owner): the worst case is itemised and asserted in tests/test_ingestion_stable_pipeline.py::owner_worst_case_github_requests (polls of the two bounded waits at 30 s, each distinct head
# examined up to three times, the freshness and anchor probes, both publications with their readbacks, the account check and the failure-path read); the bound keeps a reserve above it.
PIPELINE_GITHUB_BOUND=180
# Ordering invariants (tested, as for the other modes): job + diagnostic_window <= work alarm; work alarm + diagnostic_window <= diagnostic_total <= active window - reporting; admin_pre < admin_total <
# admin_diagnostic. Waiting for the restricted job counts as the administrative phase, so the administrative allowances are sized from the two bounded waits plus the fixed phases.
PIPELINE_TIMING=dict(input_seconds=120,active_seconds=4380,work_seconds=4260,diagnostic_seconds=40,report_seconds=20,outer_seconds=4500)
PIPELINE_DEADLINES=dict(job=4200,diagnostic_total=4320,diagnostic_window=60,admin_diagnostic=4300,admin_pre=4100,admin_total=4180,runtime_total=1)
PIPELINE_BACKSTOP_SECONDS=4600
# Control observation (read the control record, commit nothing, issue no authority, make no source request). Finite: one connection, 12 statements (the observation uses 6), 20 database-active
# seconds, 30 supervised-active seconds after the hidden input. Ordering invariants as for every mode: job + window <= work alarm; work alarm + window <= diagnostic_total <= active - reporting.
OBSERVER_MODE='CONTROL_OBSERVATION'
OBSERVER_AUTHORITY='AUTHORISE_INGESTION_CONTROL_OBSERVATION_ONCE_20261021'
OBSERVER_STATE='operational-control-observation-once-20261021'
OBSERVER_OWNER_LIMITS=dict(connections=(1,1),commands=(12,12,12))
OBSERVER_TIMING=dict(input_seconds=120,active_seconds=30,work_seconds=24,diagnostic_seconds=3,report_seconds=2,outer_seconds=180)
OBSERVER_DEADLINES=dict(job=20,diagnostic_total=27,diagnostic_window=3,admin_diagnostic=25,admin_pre=8,admin_total=18,runtime_total=1)
# Structural ceiling on database-active time: connect (3 s) + the last statement that can start (no new statement starts after admin_pre = 8 s) with its own 4 s deadline + one 2 s cancel + a 1 s close
# = 18 s <= 20 s. The cancel, if a statement hangs, is a bounded separate network request (at most the owner's cancel allowance); it is not a second session.
OBSERVER_STATEMENT_SECONDS=4
OBSERVER_BACKSTOP_SECONDS=240
OBSERVER_PREDECESSOR=dict(consumed_run=dict(run_id=39388007668,artifact_id=12248515861,artifact_zip_sha256='934a798296e7beba6bd5bb0860a820a5ef3104c7b0c18b111c81c616b3c0ee22'),
                          owner_events_sha256='35dedf6a87c3b10d4e23af54590c49bb5af4393358dd79ee9f95675be5035449',owner_final_result_sha256='8c26067b366efc208fec0bbb7affdaed80ab355b0e50c867a6d538dad7a26381',
                          pipeline_registration_sha256='8ae69f3ce95c4285ba2138ddb815953c3b68f85e790101d07a323cdabb4de5c0',integrated_corrective_revision='895fcbe8ea412213ebc795c7800ea635c8260585')
SETTLED_MODES={SETTLED_MODE:(SETTLED_AUTHORITY,SETTLED_STATE,SETTLED_PREDECESSOR),SETTLED_R2_MODE:(SETTLED_R2_AUTHORITY,SETTLED_R2_STATE,SETTLED_R2_PREDECESSOR)}
# Finite diagnostic allowance. Administrative commands/connections are TOTAL ceilings including failure handling and teardown; deadlines replace the capture-run defaults.
MATRIX_OWNER_LIMITS=dict(connections=(4,5),commands=(44,58,64))
# Direct-route diagnostic: finite administrative TOTALS (normal, teardown, diagnostic); pinned from the disposable rehearsal below plus a small margin.
DIRECT_OWNER_LIMITS=dict(connections=(5,6),commands=(60,80,92))
# Stable-credential provisioning / revocation: finite administrative TOTALS (normal, through teardown, including failure diagnostics). Measured on the disposable server: provisioning
# 50 commands / 4 connections, revocation 21 / 2; the ceiling also covers the failure path (provisioning fails after the credentials exist -> disable, restore settings, diagnostics).
STABLE_OWNER_LIMITS=dict(connections=(6,8),commands=(60,92,104))
# Ordering invariants (tested): job + diagnostic_window <= work alarm (session), so a Runner-detected stop at the job limit still has its full failure window before the one-shot work alarm;
# work alarm + diagnostic_window <= diagnostic_total <= active window - reporting, so a stop CAUSED by the alarm also keeps a full window; admin_pre < admin_total < admin_diagnostic, so a stop at the
# very end of the pre-teardown allowance still leaves teardown and failure diagnostics their own administrative time.
MATRIX_DEADLINES=dict(job=170,diagnostic_total=255,diagnostic_window=40,admin_diagnostic=130,admin_pre=60,admin_total=100,runtime_total=60)
DEFAULT_DEADLINES=dict(job=450,diagnostic_total=475,diagnostic_window=25,admin_diagnostic=240,admin_pre=210,admin_total=240,runtime_total=300)
MATRIX_TIMING=dict(input_seconds=120,active_seconds=270,work_seconds=215,diagnostic_seconds=25,report_seconds=5,outer_seconds=420)
QUALIFICATION='1833eb7349dda9b1dceb0924abd7380b2f24e591e13ad34ec37dd8e4763df3f2'
CONTRACT='bolton-received-idox-coordinator-v1'

def restricted_url(role,password):
    """Same in-memory value goes to protected mapping and native URL parser."""
    if role not in ROLES:raise ValueError('EXACT_OPERATIONAL_MAPPING_ROLE')
    return 'postgresql://'+quote(role+'.zcikcfgpblzuzpanpdqd',safe='')+':'+quote(password,safe='')+'@aws-0-eu-west-2.pooler.supabase.com:5432/postgres'

def hosted_finished(hosted_summary,incomplete):
    """Whether the restricted job's PUBLISHED result is a completed run. The job publishes while its memory scope is still enforcing, so a success is published as `PENDING_MEMORY_SCOPE_CLOSURE`
    (accepted only together with `closure_stage == PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE`); the complete closure is in the sealed workflow artifact, which is the authority for it. A stop is never completed."""
    cleanup=hosted_summary.get('cleanup')
    closed=cleanup in ('CLOSED',None) or (cleanup=='PENDING_MEMORY_SCOPE_CLOSURE' and hosted_summary.get('closure_stage')=='PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE')
    return not incomplete and closed and hosted_summary.get('status') not in ('STOP_RECONCILE_NO_RETRY',)


class Runner:
    """Injected IO enables the actual wrapper to be rehearsed without sources."""
    deadlines=DEFAULT_DEADLINES;matrix_mode=False;matrix=None;pipeline_mode=False;observer_mode=False      # class defaults: unchanged capture/diagnostic behaviour for any Runner not built in matrix mode
    def __init__(self,registration,journal,connector,*,source_reader,github,
                 url_factory,identity='postgres',ssl=None,memory=None,hostaddr=None,started=None):
        self.r=registration;self.journal=journal;self.emit=journal.emit;self.source_reader=source_reader;self.github=github;self.url_factory=url_factory;self.ssl=ssl;self.memory=memory
        self.operation_phase='INITIALISATION';self.started=started if started is not None else time.monotonic();self.phase='admin';self.phase_started=self.started;self.admin_seconds=0;self.runtime_seconds=0;self.hostaddr=hostaddr
        self.expiry=datetime.fromisoformat(registration['expires_at'])
        self.bindings=dict(revision=registration['revision'],workflow_sha256=registration['controller_sha256'],manifest_sha256=registration['manifest_sha256'])
        self.matrix_mode=registration.get('mode')==MATRIX_MODE
        settled=registration.get('mode') in SETTLED_MODES
        self.pipeline_mode=registration.get('mode')==PIPELINE_MODE
        self.observer_mode=registration.get('mode')==OBSERVER_MODE
        self.authority=SETTLED_MODES[registration['mode']][0] if settled else PIPELINE_AUTHORITY if self.pipeline_mode else AUTHORITY
        self.settle_seconds=SETTLE_SECONDS if settled else 0;self.settle_sleep=time.sleep
        direct=registration.get('mode')==DIRECT_MODE
        stable=registration.get('mode') in STABLE_MODES
        self.route_name='DIRECT' if direct else 'POOLER';self.restricted_hostaddr=None
        self.deadlines=dict(OBSERVER_DEADLINES if self.observer_mode else PIPELINE_DEADLINES if self.pipeline_mode else MATRIX_DEADLINES if (self.matrix_mode or direct or stable) else DEFAULT_DEADLINES)
        self.owner=Owner(connector,self.emit,self.check,identity=identity,expiry=self.expiry,bindings=self.bindings,limits=OBSERVER_OWNER_LIMITS if self.observer_mode else MATRIX_OWNER_LIMITS if self.matrix_mode else PIPELINE_OWNER_LIMITS if self.pipeline_mode else STABLE_OWNER_LIMITS if stable else DIRECT_OWNER_LIMITS if direct else None)
        if direct or stable or self.pipeline_mode or self.observer_mode:self.owner.permitted_policy_states=('SUCCESSOR_POLICY_APPLIED',)
        if self.observer_mode:self.owner.statement_hard_seconds=OBSERVER_STATEMENT_SECONDS
        if self.pipeline_mode:self.owner.expected_generation=PIPELINE_BINDING['hard_stop_generation']
        if registration.get('mode')==STABLE_REVOKE_MODE:self.owner.stable_state=True
        self.owner.reuse_installed=registration.get('reuse_accepted_operational_installation',False)
        self.owner.apply_policy=registration.get('mode') not in (*DIAGNOSTIC_MODES,MATRIX_MODE,PIPELINE_MODE,OBSERVER_MODE,*STABLE_MODES)
        self.matrix=None
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
            if now-self.started>=self.deadlines['diagnostic_total'] or now-self.diagnostic_started>=self.deadlines['diagnostic_window'] or admin_now>=self.deadlines['admin_diagnostic']:raise Denied('DIAGNOSTIC_RESERVE_EXHAUSTED')
            return
        if datetime.now(timezone.utc)>=self.expiry or now-self.started>=self.deadlines['job']:raise Denied('EXPIRY_OR_JOB_CLOSURE_RESERVE')
        if self.phase=='admin' and self.admin_seconds+now-self.phase_started>=self.deadlines['admin_pre']:raise Denied('ADMIN_TEARDOWN_RESERVE')
        if self.phase=='teardown' and self.admin_seconds+now-self.phase_started>=self.deadlines['admin_total']:raise Denied('ADMIN_TOTAL_BOUND')
        if self.phase=='runtime' and self.runtime_seconds+now-self.phase_started>=self.deadlines['runtime_total']:raise Denied('RUNTIME_TOTAL_BOUND')
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
        cancel_used=run_cancel_used({k:v for k,v in self.receipts.items() if k!=key})      # every slot already closed in this run, including this key's earlier use
        budget=DatabaseBudget(cancel_used=cancel_used,slot_key=key,previous=prior.get('database'),connections=min(16,remaining['connection_attempts']),statements=min(120,remaining['driver_statements']),seconds=min(165,remaining['supervised_seconds']),returned_bytes=remaining['returned_data_value_bytes'],emit=self.emit,stop_file=self.journal.root/'STOP')
        engines=[];started=time.monotonic();success=False
        budget.timeline=self.owner.timeline;budget.settle_seconds=self.settle_seconds      # non-secret elapsed-interval recording at first contact
        budget.hard_stop_at=self.started+self.deadlines['job']      # no driver wait may run past the job limit: the failure window and teardown start after it
        try:
            engines=[budget.engine(self.owner.urls[r],ssl=self.ssl,hostaddr=self.restricted_address(),route=self.route_name) for r in ROLES]
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
        self.owner.apply_role_settings=True        # capture path only: the matrix path never changes role configuration
        self.operation_phase='ADMIN_PREFLIGHT';self.owner.preflight()
        self.operation_phase='ADMIN_INSTALL_OR_REUSE';self.owner.install()
        self.operation_phase='CREDENTIAL_MAPPING_ACTIVATION';self.owner.map_and_activate(self.github,url_factory=self.url_factory)
        self.settle()
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
        if self.r.get('mode') in DIAGNOSTIC_MODES:return
        self.operation_phase='AUTHORITY_REGISTRATION'
        self.capture_bindings=self.owner.register([root],self.authority+'_CAPTURE',capture_key=self.capture_key,source_calls=1)
        self.emit('required_setup_committed',dict(capture_key=self.capture_key))

    def stop_requested(self):
        if (self.journal.root/'STOP').exists():raise Denied('MANUAL_STOP_OR_CONTROLLER_DEADLINE')      # the owner STOP file, honoured at every step of the interval

    def restricted_address(self):
        """The pinned address for the restricted engines. A direct run uses ONLY the address resolved for the direct host; it never borrows the administrative (pooler) address."""
        if self.route_name=='DIRECT':
            if not self.restricted_hostaddr:raise Denied('DIRECT_ROUTE_ADDRESS_REQUIRED')
            return self.restricted_hostaddr
        return self.hostaddr

    def settle(self):
        """One fixed settling period after BOTH passwords and the activation are committed and BEFORE either restricted account is first contacted.

        Nothing connects as either restricted login here (administrative connections are closed, no polling, no probe). The wait is sliced into one-second steps, each checked against the
        stop file, the registration expiry and the job/administrative deadlines, so it cannot outlive any of them. It is inside the administrative phase allowance (admin_pre) and the job limit."""
        if not self.settle_seconds:return
        self.operation_phase='CREDENTIAL_SETTLING'
        began=time.monotonic()
        self.emit('settling_started',dict(planned_seconds=self.settle_seconds,interval_status='EXPERIMENTAL_NOT_A_PROVIDER_GUARANTEE',restricted_contacts_so_far=0))
        while True:
            left=self.settle_seconds-(time.monotonic()-began)
            if left<=0:break
            self.check();self.stop_requested();self.settle_sleep(min(1.0,left))
        self.check();self.stop_requested()
        self.emit('settling_completed',dict(planned_seconds=self.settle_seconds,elapsed_seconds=round(time.monotonic()-began,3)))

    def setup_matrix(self):
        """Accepted credential lifecycle up to restricted-connection qualification, then the four-entry matrix. No authority, grant, exception, source or queue step exists on this path."""
        from .restricted_matrix import Matrix
        self.matrix=Matrix(self)
        account=self.github.call('GET','user')
        if account.get('login')!='maxrose26':raise ValueError('EXACT_OWNER_GITHUB_ACCESS')
        self.operation_phase='ADMIN_PREFLIGHT';self.owner.preflight()
        self.operation_phase='ADMIN_INSTALL_OR_REUSE';self.owner.install()
        self.operation_phase='CREDENTIAL_MAPPING_ACTIVATION';self.owner.map_and_activate(self.github,url_factory=self.url_factory)
        self.operation_phase='RESTRICTED_CONNECTION_MATRIX'
        with self.phase_as('runtime'):self.matrix.run()
        self.emit('restricted_matrix_completed',dict(accounting=self.matrix.accounting()))

    def capture_once(self):
        self.operation_phase='SOURCE_CAPTURE_RETENTION'
        if self.capture is not None:raise Denied('CAPTURE_ALREADY_RETAINED_NO_SOURCE_REPLAY')
        with self.phase_as('runtime'):
            with self.slot(self.capture_key,self.capture_bindings,self.authority+'_CAPTURE') as (co,budget):
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
            self.batch_bindings=self.owner.register(batches,self.authority+'_SCREEN',capture_key=self.capture_key,source_calls=0,prepared=[root_binding,*prepared])
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
                with self.slot(key,self.batch_bindings,self.authority+'_SCREEN') as (co,budget):
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
            with current.slot(current.capture_key,current.capture_bindings,current.authority+'_CAPTURE') as (co,budget):
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

    def closure(self,access,*,memory_close=True):
        """Same positive checks on success/failure; no automatic process kill.

        This is controller/owned-resource closure, not evidence that the outer
        systemd scope has disappeared after this process exits.
        """
        process=dict(status='UNCERTAIN',native_memory_proof=self.memory is not None);memory_pending=False
        try:
            if self.memory is not None and not memory_close and not hasattr(self,'memory_closure'):
                # Deferred: the scope keeps enforcing while the final result is published inside its bounded reserve; it is removed by the final closure, after which no further GitHub call is admitted.
                memory_pending=True;process['memory']='ENFORCED_PENDING_CLOSURE';group_closed=True
            elif self.memory is not None:
                if not hasattr(self,'memory_closure'):self.memory_closure=self.memory.close()
                proof=self.memory_closure
                process['memory']=proof
                group_closed=proof.get('owned_groups_removed') is True and proof.get('owned_survivors')==0
            else:group_closed=True # disposable-only; production requires native memory at entry
            after=owned_resources()
            process.update(new_socket_count=len(after['socket_fds']-self.baseline['socket_fds']),live_child_count=len(after['children']))
            if group_closed and process['new_socket_count']==0 and process['live_child_count']==0:process['status']='PENDING_MEMORY_SCOPE_CLOSURE' if memory_pending else 'CLOSED'
        except BaseException:pass
        a=self.owner.accounting()
        failed_admin_closed=(a.get('failed_native_connections',0)==a.get('failed_native_finished',0) or process.get('new_socket_count')==0)
        connection_closed=(failed_admin_closed and a['connections_opened']==a['connections_closed'] and self.closed and (getattr(self,"matrix",None) is None or self.matrix.closed_ok()) and
            all(x['database'].get('cleanup')=='CLOSED' and x['database'].get('connections_closed') is True for x in self.receipts.values()))
        connection=dict(status='CLOSED' if connection_closed else 'UNCERTAIN',administrative_opened=a['connections_opened'],administrative_closed=a['connections_closed'],failed_administrative_attempts=a.get('failed_native_connections',0),failed_administrative_closed=failed_admin_closed,runtime_slots=len(self.receipts))
        safe=access in ('DISABLED_VERIFIED','AUTHORITY_INVALIDATED_STANDING_CREDENTIALS_UNCHANGED','NO_AUTHORITY_ISSUED_STANDING_CREDENTIALS_UNCHANGED','RESTRICTED_RUNTIME_NO_ACCESS_CHANGE') and not a['uncertain_effect'] and not self.github.mutation_uncertain
        overall='CLOSED' if safe and connection_closed and process['status']=='CLOSED' else ('PENDING_MEMORY_SCOPE_CLOSURE' if safe and connection_closed and process['status']=='PENDING_MEMORY_SCOPE_CLOSURE' else 'UNCERTAIN')
        return dict(access=access,connections=connection,process=process,overall=overall,outer_scope_removal='NOT_VERIFIABLE_BEFORE_CONTROLLER_EXIT')

    def failed(self,exc):
        """Shared production/rehearsal exit, independent of ledger construction."""
        if self.observer_mode:return self.observer_failed(exc)
        from .connection_diagnostics import safe_failure
        self.diagnosing=True;self.diagnostic_started=time.monotonic()
        failed_phase=self.operation_phase
        diagnostics={};invalidation='UNCERTAIN_RECONCILE';access='UNRECONCILED'
        # A known failure may invoke the fixed safety disposition. An uncertain
        # admin mutation is never automatically replayed or compensated.
        try:
            if self.github.mutation_uncertain and not self.pipeline_mode:      # in pipeline mode the revocation is database-only and is attempted regardless (an uncertain GitHub publication must never leave an authority live)
                invalidation='UNCERTAIN_RECONCILE' if self.owner.authorities else 'NOT_REQUIRED_NO_AUTHORITY'
                raise Uncertain('PRIOR_GITHUB_MUTATION_UNCERTAIN')
            if self.pipeline_mode:
                self.owner.diagnostic_mode=True      # the reserved failure allowance: ending an authority must never be refused for want of administrative capacity
                invalidation=self.owner.invalidate_authorities()      # revocation-only: independent of every stop-state; credentials, memberships and secrets are untouched
                if invalidation in ('ACKNOWLEDGED_READBACK','ALREADY_INVALIDATED_READBACK'):access='AUTHORITY_INVALIDATED_STANDING_CREDENTIALS_UNCHANGED'
                elif invalidation=='NOT_REQUIRED_NO_AUTHORITY':access='NO_AUTHORITY_ISSUED_STANDING_CREDENTIALS_UNCHANGED'
            else:
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
            failure=safe_failure(exc,'EXECUTION'),stop_reason=fixed_stop_reason(exc),preflight=dict(getattr(self.owner,'preflight_report',dict(reason_code='NOT_REACHED',policy_state='NOT_EVALUATED',permitted_states=[]))),operation_phase=failed_phase,authority_invalidation=invalidation,
            access=access,diagnostics=diagnostics,owned_cleanup=components['process'],
            accounting=self.accounting(),source_observations_attempted=self.source_attempts,source_capture_retained=self.capture is not None,source_resources=self.source_resources,
            application_writes=0,pipeline_retry='HELD',stage4='OPEN',historical_uncertainty_preserved=True)
        if getattr(self,"matrix",None) is not None:result["matrix"]=self.matrix.finalise()
        try:self.emit('stopped',result)
        except BaseException:result['audit_stop_record']='UNCERTAIN'
        return result

    def provision(self):
        """OWNER provisioning of the stable restricted credentials. Effects: capability memberships (kept), role-level timeouts (kept), a fresh password with VALID UNTIL on each restricted
        login, two protected environment secrets, LOGIN enabled on both logins - and then NOTHING is torn down: access stays enabled by design until revoked. No grant, exception, source
        request, queue row or application write. Any failure after the credentials exist falls into the ordinary failure path, which disables and removes them."""
        account=self.github.call('GET','user')
        if account.get('login')!='maxrose26':raise ValueError('EXACT_OWNER_GITHUB_ACCESS')
        self.owner.apply_role_settings=True
        self.owner.valid_until=datetime.now(timezone.utc).replace(microsecond=0)+timedelta(days=STABLE_VALIDITY_DAYS)
        self.operation_phase='ADMIN_PREFLIGHT';self.owner.preflight()
        self.operation_phase='ADMIN_INSTALL_OR_REUSE';self.owner.install()
        self.operation_phase='CREDENTIAL_MAPPING_ACTIVATION';self.owner.map_and_activate(self.github,url_factory=self.url_factory)
        self.operation_phase='STABLE_STATE_READBACK';standing=self.owner.stable_readback()
        names=self.github.names()
        if not all(n in names for n in SECRETS.values()) or 'DATABASE_URL' not in names:raise Uncertain('STABLE_SECRET_NAMES_NOT_VERIFIED')
        self.owner.urls.clear()          # the in-memory URLs are not needed again: the only copy is the protected secret store
        components=self.closure('STABLE_LOGIN_ENABLED_BY_DESIGN')
        closed=components['connections']['status']=='CLOSED' and components['process']['status']=='CLOSED'
        if not closed:raise Uncertain('OWNED_PROCESS_OR_SOCKET_CLOSURE')
        return dict(status='STABLE_CREDENTIALS_PROVISIONED_LOGIN_ENABLED',cleanup='CLOSED',access='LOGIN_ENABLED_BY_DESIGN',retained_access=dict(logins=sorted(ROLES),valid_until=standing['valid_until'],memberships=standing['memberships'],
                    secrets=sorted(SECRETS.values()),revoke='STABLE_CREDENTIAL_REVOCATION'),closure_components=components,accounting=self.accounting(),owned_cleanup=components['process'],
                    owner_verifications_required=['NO_OTHER_SESSIONS_OF_THE_TWO_LOGINS','NO_UNEXPIRED_GRANT_IN_THE_CONTROL_ROW'],
                    source_observations_attempted=0,execution_grants_created=0,application_writes=0,pipeline_retry='HELD',stage4='OPEN',historical_uncertainty_preserved=True)

    def revoke(self):
        """OWNER emergency or planned revocation through the reviewed privileged path: the ordinary teardown (NOLOGIN, NULL password, memberships revoked, bounded session policy, secret deletion)."""
        account=self.github.call('GET','user')
        if account.get('login')!='maxrose26':raise ValueError('EXACT_OWNER_GITHUB_ACCESS')
        self.operation_phase='ADMIN_PREFLIGHT';self.owner.preflight()
        with self.phase_as('teardown'):self.owner.teardown(self.github)
        components=self.closure('DISABLED_VERIFIED')
        if components['overall']!='CLOSED':raise Uncertain('OWNED_PROCESS_OR_SOCKET_CLOSURE')
        return dict(status='STABLE_CREDENTIALS_REVOKED_ACCESS_DISABLED',cleanup='CLOSED',access='DISABLED_VERIFIED',closure_components=components,accounting=self.accounting(),owned_cleanup=components['process'],
                    role_settings='LEFT_IN_PLACE_REVIEWED_VALUES',source_observations_attempted=0,execution_grants_created=0,application_writes=0,pipeline_retry='HELD',stage4='OPEN',historical_uncertainty_preserved=True)

    EVIDENCE_CONTENTS='repos/maxrose26/PropertyAIgent/contents/'
    EVIDENCE_REF='repos/maxrose26/PropertyAIgent/git/ref/heads/'

    def evidence_head_now(self):
        return self.github.call('GET',self.EVIDENCE_REF+BRANCH)['object']['sha']

    def evidence_file(self,head,relative):
        """The file in the evidence directory AT the given commit, verified by its git blob identity; None if it is not there (HTTP 404)."""
        blob=self.github.probe(self.EVIDENCE_CONTENTS+self.r['evidence_directory']+'/'+relative+'?ref='+head)
        if blob is None:return None
        blob_bytes(blob);return blob

    EVIDENCE_ANCHOR='README.md'      # a file that exists on the evidence branch; a 404 for the evidence files means something only if the same read of the branch finds this one
    REPROBES=3      # each distinct head is examined at most this many times (on successive polls): a just-published commit can briefly answer 404 from another replica

    def require_evidence_anchor(self,head):
        if self.github.probe(self.EVIDENCE_CONTENTS+self.EVIDENCE_ANCHOR+'?ref='+head) is None:raise Uncertain('EVIDENCE_BRANCH_ANCHOR_MISSING')

    def require_fresh_evidence_directory(self):
        """The two restricted-job markers must not exist yet: a leftover from any earlier run would otherwise be mistaken for this run's publication."""
        head=self.evidence_head_now()
        if head!=self.evidence_head:raise Uncertain('EVIDENCE_HEAD_MOVED')
        self.require_evidence_anchor(head)
        for relative in ('capture/source.json','capture-retained/retained.json','completed/final-result.json'):
            if self.evidence_file(head,relative) is not None:raise Uncertain('EVIDENCE_DIRECTORY_NOT_FRESH')

    def pipeline_execution(self):
        """The identity of THIS execution that every marker and result must carry: the reviewed revision, the manifest, the capture root it concerns, the evidence head it was registered against, and its authority.
        A file that merely exists is never accepted; its content must name this execution."""
        return dict(revision=self.r['revision'],manifest_sha256=self.r['manifest_sha256'],capture_key=self.capture_key,initial_evidence_head=self.r['evidence_head'],authority=self.authority)

    def verify_retained_marker(self,blob,checkpoint,source_raw):
        """The restricted job's retained marker must name this execution and exactly this capture: the checkpoint the DATABASE holds (digest and kind) and the archive bytes on the evidence branch."""
        try:marker=json.loads(blob_bytes(blob))
        except ValueError:raise Uncertain('HOSTED_MARKER_UNREADABLE') from None
        archive=checkpoint['durable_archive']
        if (not isinstance(marker,dict) or marker.get('execution')!=self.pipeline_execution() or marker.get('capture_sha256')!=digest(checkpoint) or marker.get('kind')!=checkpoint.get('kind')
            or marker.get('archive_sha256')!=hashlib.sha256(source_raw).hexdigest() or marker.get('archive_sha256')!=archive.get('sha256')):raise Uncertain('HOSTED_MARKER_BINDING')
        return marker

    def verify_hosted_result(self,blob,*,require_capture=True):
        """The restricted job's result must name this execution and, once a capture exists, exactly this capture (after the screening authority was registered the capture digest is required)."""
        raw=blob_bytes(blob)
        try:result=json.loads(raw)
        except ValueError:raise Uncertain('HOSTED_RESULT_UNREADABLE') from None
        if not isinstance(result,dict) or result.get('execution')!=self.pipeline_execution() or (require_capture and result.get('capture_sha256')!=digest(self.capture)):raise Uncertain('HOSTED_RESULT_BINDING')
        return raw,result

    def await_any(self,relatives,seconds):
        """Bounded wait until one of `relatives` EXISTS in the evidence directory at the CURRENT head of the evidence branch (earlier entries take priority when several exist). Presence-based, never
        change-based: the restricted job publishes several commits within seconds and a poll at a coarse interval may see only the latest, which still contains every earlier file (a change-based wait would
        miss the one it is waiting for). Each distinct head is examined at most REPROBES times (on successive polls, so one transient 404 cannot hide a published file); the first examination is of the head as it stands. Timeout is a stop (no retry, no replay). Returns (head, relative, blob)."""
        deadline=time.monotonic()+seconds;probes={}
        while True:
            self.check();self.stop_requested()
            head=self.evidence_head_now()
            if probes.get(head,0)<self.REPROBES:
                probes[head]=probes.get(head,0)+1
                for relative in relatives:
                    blob=self.evidence_file(head,relative)
                    if blob is not None:return head,relative,blob
            if time.monotonic()>=deadline:raise Denied('HOSTED_PUBLICATION_WAIT_EXPIRED')
            getattr(self,'pipeline_sleep',time.sleep)(PIPELINE_BINDING['poll_seconds'])

    def await_file(self,relative,seconds):
        head,_,blob=self.await_any((relative,),seconds);return head,blob

    def pipeline(self):
        """Owner side of the stable-credential pipeline (see specifications/032-stage4-stable-credential-pipeline.md). Never touches a credential, membership, role setting or secret."""
        pb=PIPELINE_BINDING
        account=self.github.call('GET','user')
        if account.get('login')!='maxrose26':raise ValueError('EXACT_OWNER_GITHUB_ACCESS')
        expected=dict(identity=self.owner.identity,hard_stop_generation=pb['hard_stop_generation'],valid_until=pb['valid_until'])
        self.operation_phase='PIPELINE_READBACK_BEFORE_GRANT'
        before=self.owner.pipeline_readback(expected,label='BEFORE_ANY_GRANT')
        identity=dict(subject=SCOPE,task='DISCOVERY',contract=CONTRACT,revision=self.r['manifest_sha256'])
        root=item(identity,max_attempts=1,limits=dict(DEFAULT_LIMITS,requests=10,bytes=3000000,rows=60,pages=6))
        self.capture_key=root['key']
        self.operation_phase='PIPELINE_CAPTURE_AUTHORITY'
        self.require_fresh_evidence_directory()
        self.owner.grant_expiry=min(self.expiry,datetime.now(timezone.utc)+timedelta(minutes=pb['grant_minutes']))
        self.owner.require_control_sha256=self.owner.baseline_control_sha256
        self.capture_bindings=self.owner.register([root],self.authority+'_CAPTURE',capture_key=self.capture_key,source_calls=1)
        self.owner.require_control_sha256=None
        self.emit('pipeline_capture_authority_registered',dict(capture_key=self.capture_key,grant_expires_at=self.owner.grant_expiry.isoformat(),restricted_job='WAITING_FOR_DISPATCH_OR_RUNNING'))
        self.operation_phase='PIPELINE_AWAIT_DURABLE_RETENTION'
        # The restricted job archives the raw source BEFORE the ledger checkpoint is durable (accepted order) and then publishes the retained marker: that marker (which implies the archive) is what is awaited.
        head,relative,retained=self.await_any(('capture-retained/retained.json','completed/final-result.json'),pb['capture_wait_seconds'])
        self.evidence_head=head
        if relative!='capture-retained/retained.json':      # the restricted job ended WITHOUT retaining a capture: its (execution-bound) result is read, and the ceremony ends now rather than at the end of the retention window
            _,ended=self.verify_hosted_result(retained,require_capture=False)
            self.emit('pipeline_hosted_ended_before_retention',dict(status=ended.get('status'),phase=ended.get('operation_phase'),failure=ended.get('failure')))
            raise Denied('HOSTED_ENDED_BEFORE_RETENTION')
        blob=self.evidence_file(head,'capture/source.json')
        if blob is None:raise Uncertain('HOSTED_ARCHIVE_MISSING')
        rows=self.owner.read_items([self.capture_key])
        state,checkpoint=rows.get(self.capture_key,(None,None))
        archive=(checkpoint or {}).get('durable_archive') if isinstance(checkpoint,dict) else None
        if state!='COMPLETE' or not isinstance(checkpoint,dict) or checkpoint.get('kind')!='LISTING_RECEIPT_V1' or not archive:raise Uncertain('CAPTURE_NOT_DURABLY_RETAINED')
        if archive.get('sha256')!=hashlib.sha256(blob_bytes(blob)).hexdigest() or archive.get('path')!=self.r['evidence_directory']+'/capture/source.json':raise Uncertain('CAPTURE_ARCHIVE_BINDING')
        self.verify_retained_marker(retained,checkpoint,blob_bytes(blob))      # existence is not acceptance: the marker names this execution and exactly this capture
        self.capture=checkpoint
        if len(self.capture.get('records',[]))>60:raise Uncertain('CAPTURE_ROW_BOUND')      # the accepted capture ceiling, enforced by the owner itself before anything further is registered
        self.plans=batch_plans(self.capture_key,self.capture)
        self.emit('pipeline_capture_retained',dict(capture_sha256=digest(self.capture),rows=len(self.capture.get('records',[])),batches=len(self.plans),archive_sha256=archive['sha256']))
        if self.plans:
            self.operation_phase='PIPELINE_SCREENING_AUTHORITY'
            self.owner.grant_expiry=min(self.expiry,datetime.now(timezone.utc)+timedelta(minutes=pb['screening_grant_minutes']))
            prepared=[]
            for record in self.capture['records']:
                prepared.append(item(dict(subject=dict(kind='APPLICATION',council='bolton',reference=record['reference']),task='SCREENING',contract='listing-screen-v1',revision=digest(record)),dependencies=[self.capture_key]))
            batches=[item({k:p[k] for k in ('subject','task','contract','revision')},dependencies=p['dependencies'],checkpoint=p['checkpoint']) for p in self.plans]
            root_binding=item(dict(subject=SCOPE,task='DISCOVERY',contract=CONTRACT,revision=self.r['manifest_sha256']))
            self.batch_bindings=self.owner.register(batches,self.authority+'_SCREEN',capture_key=self.capture_key,source_calls=0,prepared=[root_binding,*prepared])
            self.emit('pipeline_screening_authority_registered',dict(batches=len(self.plans),children_prepared=len(prepared)))
            # The restricted job waits on the evidence branch (no database connection) for this marker. It is NOT an authority - the authority is the database grant registered above.
            marker=dict(execution=self.pipeline_execution(),authority=self.authority+'_SCREEN',bindings_sha256=digest(self.batch_bindings),capture_sha256=digest(self.capture))
            self.evidence_head=self.github.publish({'registered.json':canonical(marker)},directory=self.r['evidence_directory']+'/screening-authority',expected_head=self.evidence_head)
            self.operation_phase='PIPELINE_AWAIT_SCREENING'
            head,blob=self.await_file('completed/final-result.json',pb['screening_wait_seconds'])
            self.evidence_head=head
            raw,hosted=self.verify_hosted_result(blob)
            hosted_summary=dict(sha256=hashlib.sha256(raw).hexdigest(),status=hosted.get('status'),cleanup=hosted.get('cleanup'),closure_stage=hosted.get('closure_stage'),rows=hosted.get('rows'),batches=hosted.get('batches'))
            done=self.owner.read_items([p['key'] for p in self.plans])
            incomplete=sorted(k for k in (p['key'] for p in self.plans) if done.get(k,(None,))[0]!='COMPLETE')
            self.emit('pipeline_screening_state',dict(batches=len(self.plans),complete=len(self.plans)-len(incomplete),incomplete=incomplete,hosted=hosted_summary))
        else:      # an explicit zero: there is nothing to screen, but the restricted job may still be finishing - its (execution- and capture-bound) result is awaited before the readbacks
            self.operation_phase='PIPELINE_AWAIT_SCREENING'
            head,blob=self.await_file('completed/final-result.json',pb['screening_wait_seconds'])
            self.evidence_head=head
            raw,hosted=self.verify_hosted_result(blob)
            hosted_summary=dict(sha256=hashlib.sha256(raw).hexdigest(),status=hosted.get('status'),cleanup=hosted.get('cleanup'),closure_stage=hosted.get('closure_stage'),rows=hosted.get('rows'),batches=hosted.get('batches'));incomplete=[]
            self.emit('pipeline_screening_state',dict(batches=0,complete=0,incomplete=[],reason='EXPLICIT_ZERO_ROWS',hosted=hosted_summary))
        self.operation_phase='PIPELINE_INVALIDATION'
        self.owner.tearing_down=True      # the invalidation and the final readback run on the reserved end-of-run allowance
        invalidation=self.owner.invalidate_authorities()
        after=self.owner.pipeline_readback(expected,label='AFTER_INVALIDATION')
        components=self.closure('AUTHORITY_INVALIDATED_STANDING_CREDENTIALS_UNCHANGED')
        if invalidation not in ('ACKNOWLEDGED_READBACK','ALREADY_INVALIDATED_READBACK') or components['overall']!='CLOSED':raise Uncertain('PIPELINE_INVALIDATION_OR_CLOSURE')
        finished=hosted_finished(hosted_summary,incomplete)
        result=dict(status='STABLE_PIPELINE_AUTHORITY_COMPLETED_AUTHORITY_INVALIDATED' if finished else 'STABLE_PIPELINE_ENDED_INCOMPLETE_AUTHORITY_INVALIDATED',authority_invalidation=invalidation,screening='COMPLETE' if not incomplete else 'INCOMPLETE',hosted=hosted_summary,cleanup=components['overall'],access='AUTHORITY_INVALIDATED_STANDING_CREDENTIALS_UNCHANGED',closure_components=components,
                    readback_before=dict(statements=before['statements'],findings=before['findings'],notes=before['notes']),readback_after=dict(statements=after['statements'],findings=after['findings'],notes=after['notes']),
                    capture_sha256=digest(self.capture),batches=len(self.plans),accounting=self.accounting(),owned_cleanup=components['process'],credentials='UNCHANGED_RETAINED_UNTIL_THE_OWNER_REVOKES_OR_THEY_EXPIRE',
                    source_observations_attempted=1,application_writes=0,pipeline_retry='HELD',stage4='OPEN',historical_uncertainty_preserved=True)
        self.emit('pipeline_owner_result',result);self.journal.save('final-result.json',result)
        self.evidence_head=self.github.publish({'events.jsonl':self.journal.file.read_bytes(),'final-result.json':canonical(result)},directory=self.r['evidence_directory']+'/owner',expected_head=self.evidence_head)
        result.update(evidence_commit=self.evidence_head,audit_sha256=hashlib.sha256(self.journal.file.read_bytes()).hexdigest(),audit_chain_head=self.journal.head)
        self.journal.save('final-result.json',result)
        return result

    def observe(self):
        """One fixed control observation and a closure. No grant, exception, stop, credential, membership, role setting, secret or source request exists on this path, and no GitHub request is admitted."""
        self.operation_phase='CONTROL_OBSERVATION'
        record=self.owner.control_observation()
        components=self.closure('NO_AUTHORITY_ISSUED_STANDING_CREDENTIALS_UNCHANGED')
        if components['overall']!='CLOSED':raise Uncertain('OWNED_PROCESS_OR_SOCKET_CLOSURE')
        return dict(status='CONTROL_OBSERVED_NO_COMMITTED_MUTATION',cleanup='CLOSED',closure_components=components,accounting=self.accounting(),observation=record,owned_cleanup=components['process'],access='NO_AUTHORITY_ISSUED_STANDING_CREDENTIALS_UNCHANGED',
                    source_observations_attempted=0,execution_grants_created=0,application_writes=0,committed_writes=0,github_requests=self.github.requests,pipeline_retry='HELD',stage4='OPEN',historical_uncertainty_preserved=True)

    def observer_failed(self,exc):
        """Read-only failure path: report and close. Never an invalidation, a teardown, a GitHub request or a retry."""
        from .connection_diagnostics import safe_failure
        self.diagnosing=True;self.diagnostic_started=time.monotonic()
        try:components=self.closure('NO_AUTHORITY_ISSUED_STANDING_CREDENTIALS_UNCHANGED')
        except BaseException:components=dict(overall='UNCERTAIN',process=dict(status='UNCERTAIN'))
        return dict(status='STOP_RECONCILE_NO_RETRY',cleanup=components['overall'],closure_components=components,failure=safe_failure(exc,'EXECUTION'),stop_reason=fixed_stop_reason(exc),operation_phase=self.operation_phase,
                    accounting=self.accounting(),access='NO_AUTHORITY_ISSUED_STANDING_CREDENTIALS_UNCHANGED',authority_invalidation='NOT_REQUIRED_NO_AUTHORITY',source_observations_attempted=0,execution_grants_created=0,application_writes=0,committed_writes=0,
                    transient_owner_capability='UNVERIFIED_TRANSACTION_ABORTED_BY_DISCONNECT_ABSENCE_NOT_READ_BACK',pipeline_retry='HELD',stage4='OPEN',historical_uncertainty_preserved=True)

    def execute(self):
        try:
            if self.observer_mode:return self.observe()
            if self.pipeline_mode:return self.pipeline()
            if self.matrix_mode:
                self.setup_matrix()
                with self.phase_as('teardown'):self.owner.teardown(self.github)
                components=self.closure('DISABLED_VERIFIED')
                if components['overall']!='CLOSED':raise Uncertain('OWNED_PROCESS_OR_SOCKET_CLOSURE')
                return dict(status='RESTRICTED_MATRIX_COMPLETED_ACCESS_DISABLED',cleanup='CLOSED',closure_components=components,accounting=self.accounting(),matrix=self.matrix.finalise(),owned_cleanup=components['process'],
                            source_observations_attempted=0,execution_grants_created=0,application_writes=0,pipeline_retry='HELD',stage4='OPEN',historical_uncertainty_preserved=True)
            if self.r.get('mode')==STABLE_PROVISION_MODE:return self.provision()
            if self.r.get('mode')==STABLE_REVOKE_MODE:return self.revoke()
            self.setup()
            if self.r.get('mode') in DIAGNOSTIC_MODES:
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
    direct=r.get('mode')==DIRECT_MODE
    from . import restricted_route as rr
    prepared=prepare_connection(r,raw,progress=progress,dns_run=dns_run,dns_command=dns_command,restricted_host=rr.ROUTES['DIRECT']['host'] if direct else None)
    ca,selected,connect=prepared.ca,prepared.hostaddr,prepared.connect
    with progress.stage('RUNNER_COMPONENTS'):
        holder={}
        try:from .operational_source import read
        except ImportError:raise PreparationFailure('RUNNER_COMPONENTS','COMPONENT_IMPORT_FAILED') from None
        github=GitHub(journal.emit,lambda:holder['runner'].check(),**(dict(bound=PIPELINE_GITHUB_BOUND) if r.get('mode')==PIPELINE_MODE else dict(bound=0) if r.get('mode')==OBSERVER_MODE else {}))
        def reader(_):return read('listing',dict(council='bolton',semantics='RECEIVED',start='2026-10-16',end='2026-10-16'),root=journal.root/'source',stop_file=journal.root/'STOP',memory_group=memory.source,observe=holder['runner'].observe_source)
    with progress.stage('RUNNER_CONSTRUCTION'):
        try:runner=Runner(r,journal,connect,source_reader=reader,github=github,url_factory=(lambda role,password:rr.url('DIRECT',role,password)) if direct else restricted_url,ssl={'sslmode':'verify-full','sslrootcert':str(ca)},memory=memory,hostaddr=selected,started=started)
        except (KeyError,TypeError,ValueError,AttributeError):raise PreparationFailure('RUNNER_CONSTRUCTION','RUNNER_CONSTRUCTION_FAILED') from None
        runner.restricted_hostaddr=prepared.restricted_hostaddr
        holder['runner']=runner
    return runner


def validate_registration(body,sha):
    if hashlib.sha256(body).hexdigest()!=sha:raise ValueError('REGISTRATION_SHA256')
    r=json.loads(body)
    expected_authority={'REQUIRED_CAPTURE_SCREENING':AUTHORITY,'CONNECTION_DIAGNOSTIC_ONLY':DIAGNOSTIC_AUTHORITY,MATRIX_MODE:MATRIX_AUTHORITY,**{m:v[0] for m,v in SETTLED_MODES.items()},DIRECT_MODE:DIRECT_AUTHORITY,**{m:v[0] for m,v in STABLE_MODES.items()},PIPELINE_MODE:PIPELINE_AUTHORITY,OBSERVER_MODE:OBSERVER_AUTHORITY}.get(r.get('mode'))
    if expected_authority is None or r.get('authority')!=expected_authority or r.get('status')!='OWNER_APPROVED_REQUIRED_ONCE' or r.get('scope')!=SCOPE or r.get('roles')!=list(ROLES) or r.get('risk_acceptance')!='ACCEPT_POSSIBLE_PROVIDER_SCRAM_VERIFIER_RETENTION_WORKER_EFFECT_ONCE':raise ValueError('EXACT_OPERATIONAL_APPROVAL_REQUIRED')
    if r.get('reuse_accepted_operational_installation') is not True or r.get('baseline_control_sha256')!='0d829597f1422fef0af13920d5749c5751adf6d896588f379c400db7b3fa27cf' or r.get('accepted_cleanup_evidence')!='8dc4a36bc5565318e138d192bf2f7e96906f048f':raise ValueError('ACCEPTED_INSTALLED_STATE_REQUIRED')
    if r.get('mode')==MATRIX_MODE:
        from .restricted_matrix import ENTRIES,LIMITS as MX
        # The residual-risk acceptance is applied to THIS finite test only and carries no execution authority.
        if (r.get('matrix')!=[list(e) for e in ENTRIES] or r.get('matrix_limits')!=MX or r.get('execution_authority')!='NONE' or r.get('risk_application')!='THIS_FINITE_RESTRICTED_CONNECTION_MATRIX_ONLY'
            or r.get('execution')!=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=MATRIX_STATE)
            or r.get('owner_limits')!=dict(connections=list(MATRIX_OWNER_LIMITS['connections']),commands=list(MATRIX_OWNER_LIMITS['commands'])) or r.get('state_directory')!=MATRIX_STATE):raise ValueError('MATRIX_BINDING')
    if r.get('mode')==DIRECT_MODE:
        if (r.get('restricted_route')!='DIRECT' or r.get('predecessor')!=DIRECT_PREDECESSOR or r.get('execution_authority')!='NONE' or r.get('risk_application')!='THIS_FINITE_DIRECT_ROUTE_DIAGNOSTIC_ONLY'
            or r.get('execution')!=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=DIRECT_STATE) or r.get('state_directory')!=DIRECT_STATE
            or r.get('owner_limits')!=dict(connections=list(DIRECT_OWNER_LIMITS['connections']),commands=list(DIRECT_OWNER_LIMITS['commands'])) or not (r.get('settling_seconds') is None or (type(r.get('settling_seconds')) is int and r['settling_seconds']==0))):raise ValueError('DIRECT_ROUTE_BINDING')
    if r.get('mode') in STABLE_MODES:
        _,stable_state,stable_risk=STABLE_MODES[r['mode']]
        if (r.get('predecessor')!=DIRECT_PREDECESSOR or r.get('execution_authority')!='NONE' or r.get('risk_application')!=stable_risk or r.get('state_directory')!=stable_state
            or r.get('execution')!=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=stable_state)
            or r.get('owner_limits')!=dict(connections=list(STABLE_OWNER_LIMITS['connections']),commands=list(STABLE_OWNER_LIMITS['commands']))
            or not ((type(r.get('validity_days')) is int and r['validity_days']==STABLE_VALIDITY_DAYS) if r['mode']==STABLE_PROVISION_MODE else 'validity_days' not in r) or 'restricted_route' in r or 'settling_seconds' in r):raise ValueError('STABLE_CREDENTIAL_BINDING')
    if r.get('mode')==PIPELINE_MODE:
        if (r.get('pipeline')!=PIPELINE_BINDING or r.get('predecessor')!=DIRECT_PREDECESSOR or r.get('execution_authority')!='OWNER_GRANT_AND_EXCEPTION_FOR_THE_HOSTED_RESTRICTED_JOB' or r.get('risk_application')!='THIS_FINITE_STABLE_PIPELINE_ONCE'
            or r.get('state_directory')!=PIPELINE_STATE or r.get('execution')!=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=PIPELINE_STATE)
            or r.get('owner_limits')!=dict(connections=list(PIPELINE_OWNER_LIMITS['connections']),commands=list(PIPELINE_OWNER_LIMITS['commands'])) or 'restricted_route' in r or 'settling_seconds' in r or 'validity_days' in r):raise ValueError('STABLE_PIPELINE_BINDING')
    if r.get('mode')==OBSERVER_MODE:
        if (r.get('predecessor')!=OBSERVER_PREDECESSOR or r.get('execution_authority')!='NONE' or r.get('risk_application')!='THIS_FINITE_CONTROL_OBSERVATION_ONLY'
            or r.get('state_directory')!=OBSERVER_STATE or r.get('execution')!=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=OBSERVER_STATE)
            or r.get('owner_limits')!=dict(connections=list(OBSERVER_OWNER_LIMITS['connections']),commands=list(OBSERVER_OWNER_LIMITS['commands'])) or r.get('observation')!=dict(statements=12,database_active_seconds=20,supervised_active_seconds=30,connections=1)
            or 'restricted_route' in r or 'settling_seconds' in r or 'validity_days' in r or 'pipeline' in r):raise ValueError('CONTROL_OBSERVATION_BINDING')
    if r.get('mode') in SETTLED_MODES:
        _,settled_state,settled_predecessor=SETTLED_MODES[r['mode']]
        if (r.get('settling_seconds')!=SETTLE_SECONDS or r.get('predecessor')!=settled_predecessor or r.get('execution')!=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=settled_state)
            or r.get('state_directory')!=settled_state):raise ValueError('SETTLED_BINDING')
    expiry=datetime.fromisoformat(r['expires_at']);now=datetime.now(timezone.utc)
    if expiry.tzinfo is None or not now<expiry<=now+(timedelta(minutes=30) if r.get('mode')==OBSERVER_MODE else timedelta(hours=2) if r.get('mode') in (MATRIX_MODE,DIRECT_MODE,PIPELINE_MODE,*SETTLED_MODES,*STABLE_MODES) else timedelta(hours=24)):raise ValueError('ORIGINAL_OPERATIONAL_EXPIRY')
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
    journal=Journal(state/(OBSERVER_STATE if r['mode']==OBSERVER_MODE else PIPELINE_STATE if r['mode']==PIPELINE_MODE else STABLE_MODES[r['mode']][1] if r['mode'] in STABLE_MODES else DIRECT_STATE if r['mode']==DIRECT_MODE else SETTLED_MODES[r['mode']][1] if r['mode'] in SETTLED_MODES else MATRIX_STATE if r['mode']==MATRIX_MODE else DIAGNOSTIC_STATE if r['mode']=='CONNECTION_DIAGNOSTIC_ONLY' else 'operational-capture-queue-successor-once-20261018'))
    journal.emit('consumed',dict(authority=r['authority'],registration_sha256=a.registration_sha256))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    from .credential_mapping import secure_migration_input
    from .operational_outcome import session
    progress=Progress()
    baseline=owned_resources()
    prepare=lambda raw,started:prepare_runner(r,raw,started,journal=journal,memory=memory,progress=progress)
    result=session(journal,r['expires_at'],secure_migration_input,prepare,memory=memory,progress=progress,baseline=baseline,**(dict(timing=OBSERVER_TIMING) if r['mode']==OBSERVER_MODE else dict(timing=PIPELINE_TIMING) if r['mode']==PIPELINE_MODE else dict(timing=MATRIX_TIMING) if r['mode'] in (MATRIX_MODE,DIRECT_MODE,*STABLE_MODES) else {}))
    # A cleanly closed failure remains a failed execution; never signal success
    # or permit an owner to confuse cleanup with route qualification.
    raise SystemExit(0 if result.get('cleanup')=='CLOSED' and result.get('status')!='STOP_RECONCILE_NO_RETRY' else 1)

if __name__=='__main__':main()
