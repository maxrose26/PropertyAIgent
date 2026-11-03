"""Finite manual controller, injected bindings only; no secret loader or live CLI.

Application runtime never imports verification. Trusted controller owns the
qualified parsers, screening and broker; an arbitrary future worker is excluded.
"""
from dataclasses import dataclass
import json,time
from pathlib import Path
from sqlalchemy import create_engine,event
from sqlalchemy.pool import QueuePool
from app.ingestion.ledger import Denied,digest,bounded,Ledger
from app.ingestion.sql_ledger import SQLLedger
from app.ingestion.listing_screening import screen_row,identity_admission_eligible,assessment_identity,qualifier_output_of,RULE_V1
from app.ingestion import owner_acceptance


def runtime_principal(url, ssl, route=None):
    """Bind the routing identity separately from the restricted SQL role. `route`, when given, is the ONE route the run is registered for; any other reviewed route is refused (no fallback)."""
    from sqlalchemy.engine import make_url
    from . import restricted_route as rr
    u=make_url(url)
    roles={'ingestion_worker_login','ingestion_effect_login','ingestion_application_login'}
    if (u.host,u.port,u.database)==('127.0.0.1',5432,'ingestion_provisioning_test'):
        if u.username not in roles|{'ingestion_recovery_login'}:raise Denied('FIXED_DISPOSABLE_PRINCIPAL')
        return u,u.username
    from .tls_trust import verified_trust
    ca,_=verified_trust()
    found=rr.identify(u)
    if found is None:
        if u.host in {s['host'] for s in rr.ROUTES.values()}:raise Denied('NO_MIGRATION_OR_STRONGER_RUNTIME_PRINCIPAL')
        raise Denied('REVIEWED_TLS_ENDPOINT_REQUIRED')
    name,role=found
    if route is not None and name!=route:raise Denied('RESTRICTED_ROUTE_MISMATCH')
    if ssl!={'sslmode':'verify-full','sslrootcert':str(ca)}:raise Denied('REVIEWED_TLS_ENDPOINT_REQUIRED')
    if u.drivername not in {'postgresql','postgresql+psycopg'} or u.query:raise Denied('REVIEWED_CONNECTION_CONFIGURATION_REQUIRED')
    return u,role


def batch_allocation(slot_keys,receipts,*,sealed_sha256,slot_key):
    """Finite manual acceptance allocation, not a scheduler or authority issuer.

    Durable receipt collection and its expected digest belong to the trusted
    controller's reviewed evidence handoff. Replacing a logical slot must carry
    its previous CLOSED counters; never sum both versions or reset a slot.
    """
    if (not 1<=len(slot_keys)<=13 or len(set(slot_keys))!=len(slot_keys)
        or slot_key not in slot_keys or digest(receipts)!=sealed_sha256
        or not isinstance(receipts,dict) or set(receipts)-set(slot_keys)):raise Denied('SEALED_ALLOCATION_REQUIRED')
    bounded(receipts,128*1024)
    totals=dict(driver_statements=0,connection_attempts=0,returned_data_value_bytes=0,supervised_seconds=0)
    for key,r in receipts.items():
        a=r['database']
        if a.get('slot_key')!=key or a.get('cleanup')!='CLOSED' or a.get('connections_closed') is not True or r.get('cleanup')!='CLOSED':raise Denied('ALLOCATION_CLOSURE_REQUIRED')
        for name in ('driver_statements','connection_attempts','returned_data_value_bytes'):
            if type(a.get(name)) is not int or a[name]<0:raise Denied('ALLOCATION_ACCOUNTING')
            totals[name]+=a[name]
        if type(r.get('supervised_seconds')) not in (int,float) or not 0<=r['supervised_seconds']<=300:raise Denied('ALLOCATION_ACCOUNTING')
        totals['supervised_seconds']+=r['supervised_seconds']
    caps=dict(driver_statements=1040,connection_attempts=40,returned_data_value_bytes=4*1024**2,supervised_seconds=300)
    if any(totals[k]>caps[k] for k in caps):raise Denied('AGGREGATE_ALLOCATION_EXHAUSTED')
    # Return the total logical-slot allowance, including that slot's prior use.
    current=receipts.get(slot_key,{});a=current.get('database',{})
    remaining={k:caps[k]-totals[k]+(current.get(k,0) if k=='supervised_seconds' else a.get(k,0)) for k in caps}
    return dict(totals=totals,remaining=remaining)


# Deadline levels (see PROPOSAL / RELEASE_PACKAGE): PER-WAIT = STATEMENT_HARD_SECONDS (12 s, above the 10 s server statement_timeout, which stays primary when reflected);
# COMPLETE OPERATION = up to WAITS_PER_OPERATION waits (BEGIN + statement on a non-autocommit login) + one bounded cancel + close; AGGREGATE = the slot budget (<=165 s) and the runner job limit.
STATEMENT_HARD_SECONDS=12
WAITS_PER_OPERATION=2
CANCEL_ALLOWANCE=dict(attempts=4,seconds_each=2.0)       # explicit finite allowance for cancel connections per budget; they are not logins and are accounted separately
CANCEL_RUN_ALLOWANCE=dict(attempts=8)                    # AGGREGATE ceiling across every slot of one run (capture + all batches, carried through pause/resume receipts); a new budget never starts from zero


def run_cancel_used(receipts):
    """Cancel attempts already spent by every slot of this run (carried in the receipts through pause/resume); the aggregate ceiling is CANCEL_RUN_ALLOWANCE."""
    total=0
    for r in receipts.values():
        n=r.get("database",{}).get("cancel_attempts",0)
        if type(n) is not int or n<0:raise Denied("CANCEL_RUN_ALLOWANCE_BOUND")
        total+=n
    return total


class DatabaseBudget:
    """Counts attempts before connect and every cursor/internal driver command.

    Includes SQLAlchemy initialization, BEGIN/COMMIT/ROLLBACK. Records operation
    kinds only, never SQL parameters, URLs, credentials or row values.
    """
    def __init__(self,*,connections=16,statements=120,seconds=165,stop_file=None,previous=None,slot_key=None,returned_bytes=4*1024**2,emit=None,cancel_used=0):
        if type(cancel_used) is not int or not 0<=cancel_used<=CANCEL_RUN_ALLOWANCE['attempts']:raise Denied('CANCEL_RUN_ALLOWANCE_BOUND')
        self.cancel_used=cancel_used;self.prior_cancel_attempts=(previous or {}).get('cancel_attempts',0);self.prior_cancel_seconds=(previous or {}).get('cancel_seconds',0.0);self.prior_cancel_failures=(previous or {}).get('cancel_failures',0)
        if not (1<=connections<=16 and 20<=statements<=120 and 0<seconds<=165):raise Denied('CONTROLLER_CEILING')
        self.emit=emit or (lambda *_:None);self.connection_diagnostics=list((previous or {}).get('connection_diagnostics',[]))
        self.failed_native_closed=True;self.hard_deadline_events=[];self.hard_stop_at=None;self.timeline=None;self.settle_seconds=None
        from .tls_trust import owned_resources
        self.socket_baseline=owned_resources()['socket_fds']
        self.connection_cap=connections;self.statement_cap=statements;self.seconds=seconds
        if type(returned_bytes) is not int or not 0<returned_bytes<=4*1024**2:raise Denied('DATABASE_BYTE_CEILING')
        self.returned_cap=returned_bytes
        previous=bounded(previous or {},16384)
        self.slot_key=slot_key or previous.get('slot_key')
        if previous.get('slot_key') not in (None,self.slot_key):raise Denied('LOGICAL_SLOT_BINDING')
        self.previous=previous;self.capture_checkpoint_sha256=previous.get('capture_checkpoint_sha256')
        attempts=previous.get('connection_attempts',0);statements=previous.get('driver_statements',0);elapsed=previous.get('elapsed_seconds',0)
        if type(attempts) is not int or not 0<=attempts<=connections or type(statements) is not int or not 0<=statements<=self.statement_cap or type(elapsed) not in (int,float) or not 0<=elapsed<seconds:raise Denied('PRIOR_ACCOUNTING_BOUND')
        if previous and (previous.get('cleanup')!='CLOSED' or previous.get('connections_closed') is not True):raise Denied('PRIOR_CLOSURE_REQUIRED')
        self.returned_bytes=previous.get("returned_data_value_bytes",0)
        if type(self.returned_bytes) is not int or not 0<=self.returned_bytes<=self.returned_cap:raise Denied("PRIOR_BYTES_BOUND")
        self.previous_elapsed=elapsed
        self.started=time.monotonic();self.attempts=attempts;self.statements=statements;self.kinds=dict(previous.get('statement_kinds',{}));self.opened=[];self.engines=[];self.previous_opened=previous.get('connections_opened',0);self.connection_seconds=previous.get('connection_active_seconds',0.0);self.stop_file=Path(stop_file) if stop_file else None
    def first_contact(self,role):
        """Non-secret elapsed intervals (password commit, mapping, activation -> now) recorded ONCE per role at its first connection attempt."""
        tl=self.timeline.get(role) if isinstance(self.timeline,dict) else None
        if tl is None or 'first_contact_intervals' in tl:return {}
        now=time.monotonic()
        iv={k:round(now-tl[s],3) for k,s in (('since_password_commit_seconds','password_committed'),('since_mapping_seconds','mapped'),('since_activation_seconds','activated')) if s in tl}
        tl['first_contact_intervals']=dict(iv,settle_seconds_planned=self.settle_seconds or 0,attempt=self.attempts)
        return dict(first_contact=True,**iv)
    def check(self):
        if time.monotonic()-self.started+self.previous_elapsed>=self.seconds or (self.stop_file and self.stop_file.exists()):raise Denied('MANUAL_STOP_OR_CONTROLLER_DEADLINE')
    def guarded(self,connection,call):
        """Run one blocking driver wait under a CLIENT-side hard deadline that does not depend on the server honouring any timeout.

        Each wait is bounded by min(STATEMENT_HARD_SECONDS, remaining slot budget, time left before `hard_stop_at`), so no wait can run past the execution reserve the runner set. On expiry the call is
        interrupted, a bounded cancel is attempted within the explicit cancellation allowance, the connection is closed, the event is accounted (attempts, seconds, outcome) and the call is denied.
        A cancel acknowledgement never establishes that the backend ended."""
        from .hard_deadline import hard_deadline,abandon,DeadlineExceeded
        now=time.monotonic()
        remaining=min(STATEMENT_HARD_SECONDS,self.seconds-self.previous_elapsed-(now-self.started))
        if self.hard_stop_at is not None:remaining=min(remaining,self.hard_stop_at-now)
        if remaining<=0:raise Denied('EXECUTION_RESERVE_REACHED')
        if remaining<.5:raise Denied('EXECUTION_RESERVE_REACHED')      # never widen a wait past the reserve (a sub-half-second wait is refused, not stretched)
        try:
            with hard_deadline(remaining,'STATEMENT_HARD_DEADLINE'):return call()
        except DeadlineExceeded:
            attempts=sum(e.get('cancel_attempts',0) for e in self.hard_deadline_events)
            if attempts>=CANCEL_ALLOWANCE['attempts'] or self.cancel_used+self.prior_cancel_attempts+attempts>=CANCEL_RUN_ALLOWANCE['attempts']:
                event=dict(cancel_requested=False,cancel_outcome='CANCEL_SKIPPED_ALLOWANCE_EXHAUSTED',cancel_attempts=0,cancel_seconds=0.0,backend_closure='NOT_ESTABLISHED')
                try:connection.close()
                except BaseException:pass
                event['client_closed']=bool(getattr(connection,'closed',False))
            else:event=abandon(connection)
            event['hard_seconds']=round(remaining,3);self.hard_deadline_events.append(event)
            self.connection_seconds+=event.get('cancel_seconds',0.0)+event.get('close_seconds',0.0)
            raise Denied('STATEMENT_HARD_DEADLINE') from None
    def tick(self,kind,*,cleanup=False):
        if not cleanup:self.check()
        # Reserve eight slots for finite rollback/closure; no commit after stop.
        if self.statements>=self.statement_cap-(0 if cleanup else 8):raise Denied('DRIVER_STATEMENT_BOUND')
        self.statements+=1;self.kinds[kind]=self.kinds.get(kind,0)+1
    def engine(self,url,*,ssl=None,hostaddr=None,route=None):
        import psycopg
        u,role=runtime_principal(url,ssl) if route is None else runtime_principal(url,ssl,route)
        if any(k.startswith('PG') for k in __import__('os').environ):raise Denied('LIBPQ_ENVIRONMENT_OVERRIDE')
        if u.host!='127.0.0.1':
            import ipaddress
            if not hostaddr or ipaddress.ip_address(hostaddr).version!=4:raise Denied('PINNED_REVIEWED_ADDRESS_REQUIRED')
        budget=self
        class Cursor(psycopg.Cursor):
            def execute(self,query,params=None,**kwargs):
                budget.tick('cursor',cleanup=str(query).strip().startswith('SELECT public.ingestion_raise_stop('));result=super().execute(query,params,**kwargs)
                if self.pgresult is not None:
                    budget.returned_bytes+=sum(len(self.pgresult.get_value(r,c) or b'') for r in range(self.pgresult.ntuples) for c in range(self.pgresult.nfields))
                    if budget.returned_bytes>budget.returned_cap:raise Denied('DATABASE_RETURNED_VALUE_BOUND')
                return result
            def executemany(self,*a,**kw):raise Denied('BULK_FORBIDDEN')
        class Connection(psycopg.Connection):
            def _exec_command(self,command,*a,**kw):
                raw=command if isinstance(command,bytes) else str(command).encode()
                rollback=raw.strip().upper().startswith(b'ROLLBACK')
                budget.tick('driver_internal',cleanup=rollback)
                return super()._exec_command(command,*a,**kw)
            def wait(self,gen,interval=0.1,timeout=None):
                # EVERY blocking driver wait of this connection (statements, BEGIN, COMMIT, ROLLBACK, pool reset) runs under the client hard deadline. _exec_command is a generator,
                # so wrapping its construction would bound nothing; the wait is where the call actually blocks. Connection establishment is bounded by connect_timeout instead.
                return budget.guarded(self,lambda:super(Connection,self).wait(gen,interval,timeout))
        def creator():
            budget.check()
            if budget.attempts>=budget.connection_cap:raise Denied('CONNECTION_BOUND')
            budget.attempts+=1
            from .connection_diagnostics import safe_failure
            budget.emit('runtime_connection_intent',dict(role=role,attempt=budget.attempts,phase='DRIVER_CONNECT',tls='verify-full' if ssl else 'DISPOSABLE',**budget.first_contact(role)))
            began=time.monotonic();phase='DRIVER_CONNECT';c=None
            try:
                c=Connection.connect(host=u.host,port=u.port,dbname=u.database,user=u.username,password=u.password,
                connect_timeout=3,prepare_threshold=None,cursor_factory=Cursor,autocommit=True,
                options='-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=20000',**({'hostaddr':hostaddr} if hostaddr else {}),**(ssl or {}))
            except BaseException as exc:
                observation=dict(role=role,attempt=budget.attempts,**safe_failure(exc,phase))
                budget.failed_native_closed &= observation['failed_native_connection_finished']
                budget.connection_diagnostics.append(observation);budget.emit('runtime_connection_failed',observation)
                # A timeout traceback can retain psycopg's suspended connect
                # generator and its native socket. Keep diagnostics, not that
                # traceback/context. Closure is still measured, never assumed.
                exc.__context__=None;exc.__cause__=None
                raise exc.with_traceback(None) from None
            finally:budget.connection_seconds+=time.monotonic()-began
            budget.opened.append(c);budget.emit('runtime_connection_open',dict(role=role,attempt=budget.attempts))
            try:
                with c.cursor() as q:
                    q.execute("SELECT current_setting('statement_timeout'),current_setting('lock_timeout'),current_setting('idle_in_transaction_session_timeout'),current_user,session_user,rolcanlogin,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls,rolreplication FROM pg_catalog.pg_roles WHERE rolname=current_user")
                    row=q.fetchone()
                    expected=('10s','3s','20s',role,role,True,False,False,False,False,False)
                    if row!=expected:
                        # the gate refuses (unchanged), but WHAT was observed is recorded, bounded and allow-listed, with identity and timeouts reported separately
                        import re
                        setting=lambda x:x if isinstance(x,str) and re.fullmatch(r'0|[0-9]{1,6}(?:us|ms|s|min|h|d)?',x) else 'NON_ALLOWLISTED_VALUE'
                        ok=isinstance(row,tuple) and len(row)==11
                        budget.emit('runtime_qualification_observation',dict(role=role,attempt=budget.attempts,identity_and_flags_match=ok and tuple(row[3:])==expected[3:],
                            observed_timeouts=[setting(x) for x in row[:3]] if ok else None,timeouts_match_reviewed=ok and tuple(row[:3])==expected[:3]))
                        raise Denied('SERVER_TIMEOUT_OR_RESTRICTED_IDENTITY_PROFILE')
                c.rollback();return c
            except BaseException as exc:
                observation=dict(role=role,attempt=budget.attempts,**safe_failure(exc,'SERVER_IDENTITY'))
                budget.connection_diagnostics.append(observation);budget.emit('runtime_connection_failed',observation)
                c.close();raise
        e=create_engine('postgresql+psycopg://',creator=creator,poolclass=QueuePool,pool_size=1,max_overflow=0,pool_timeout=3,hide_parameters=True,skip_autocommit_rollback=role=='ingestion_worker_login',isolation_level='AUTOCOMMIT' if role=='ingestion_worker_login' else 'READ COMMITTED')
        @event.listens_for(e,'checkout')
        def mode_guard(connection,record,proxy):
            if connection.autocommit!=(role=='ingestion_worker_login'):raise Denied('RUNTIME_TRANSACTION_MODE')
        self.engines.append(e);return e
    def close(self,engines):
        errors=[]
        for e in self.engines:
            try:e.dispose()
            except Exception:errors.append('DISPOSE')
        for c in self.opened:
            try:c.close()
            except Exception:errors.append('CLOSE')
        # libpq timeouts may carry no FinishedPGconn snapshot. In that case a
        # positive /proc socket comparison is required, not a vacuous empty list.
        socket_proof='UNCERTAIN'
        try:
            from .tls_trust import owned_resources
            if not (owned_resources()['socket_fds']-self.socket_baseline):socket_proof='NO_NEW_OWNED_SOCKETS'
        except BaseException:pass
        failed_closed=self.failed_native_closed or socket_proof=='NO_NEW_OWNED_SOCKETS'
        return dict(connection_diagnostics=self.connection_diagnostics,connection_active_seconds=self.connection_seconds,connections_opened=self.previous_opened+len(self.opened),connections_closed_count=self.previous_opened+sum(bool(c.closed) for c in self.opened),slot_key=self.slot_key,returned_data_value_bytes=self.returned_bytes,connection_attempts=self.attempts,driver_statements=self.statements,statement_kinds=self.kinds,
            failed_native_connections_closed=failed_closed,socket_closure=socket_proof,hard_deadline_events=list(self.hard_deadline_events),cancel_attempts=self.prior_cancel_attempts+sum(e.get('cancel_attempts',0) for e in self.hard_deadline_events),
            cancel_failures=self.prior_cancel_failures+sum(1 for e in self.hard_deadline_events if e.get('cancel_outcome') not in ('CANCEL_SENT',)),cancel_seconds=round(self.prior_cancel_seconds+sum(e.get('cancel_seconds',0.0) for e in self.hard_deadline_events),3),
            cancel_allowance=dict(CANCEL_ALLOWANCE),cancel_run_allowance=dict(CANCEL_RUN_ALLOWANCE),cancel_used_before=self.cancel_used,
            connections_closed=failed_closed and all(c.closed for c in self.opened),cleanup='CLOSED' if not errors and failed_closed and all(c.closed for c in self.opened) else 'UNCERTAIN',
            errors=errors,capture_checkpoint_sha256=self.capture_checkpoint_sha256,elapsed_seconds=round(time.monotonic()-self.started+self.previous_elapsed,3))


class ControllerLedger(SQLLedger):
    def resolve_source(self,claim,receipt):
        super().resolve_source(claim,receipt)
        if receipt.get('kind') in ('LISTING_RECEIPT_V1','LISTING_OBSERVATION_V1'):
            self.budget.capture_checkpoint_sha256=digest(receipt)

    @staticmethod
    def _limits(c):
        # Every physical connection was verified by DatabaseBudget.creator.
        # This class may only receive engines created by that fixed factory.
        pass
    def __init__(self,*args,budget,**kwargs):
        for e in (args[0],kwargs.get('broker_engine'),kwargs.get('application_engine')):
            if e is not None and e not in getattr(budget,'engines',[]):raise Denied('ACCOUNTED_ENGINE_REQUIRED')
        self.budget=budget
        super().__init__(*args,**kwargs)


@dataclass(frozen=True)
class AcceptanceBinding:
    discovery_key:str
    screening_key:str
    factual_key:str
    reference:str
    source_url:str
    source_record_id:str
    # Binds the nominated retained row; changed row = HOLD, never forced match.
    listing_revision:str
    retained_capture_sha256:str|None=None
    prior_accounting_sha256:str|None=None
    screening_batch_key:str|None=None


def execute(coordinator,binding,*,listing_reader,detail_reader,envelope,council,check=lambda:None,allow_test_evidence=False):
    # Real SQL v3 admission requires the complete retained nomination binding.
    # Historical v1 and disposable Ledger callers keep their existing defaults.
    from .v3_admission import V3AdmissionBinding,execute_retained_v3
    if isinstance(binding,V3AdmissionBinding):
        return execute_retained_v3(coordinator,binding,detail_reader=detail_reader,envelope=envelope,council=council,check=check,allow_test_evidence=allow_test_evidence)
    from app.ingestion.listing_screening import RULE_V3
    if isinstance(coordinator.ledger,ControllerLedger) and coordinator.screening_rule.rule_version==RULE_V3:
        raise Denied('V3_RETAINED_NOMINATION_REQUIRED')
    return _execute(coordinator,binding,listing_reader=listing_reader,detail_reader=detail_reader,envelope=envelope,council=council,check=check)


def _execute(coordinator,binding,*,listing_reader,detail_reader,envelope,council,check=lambda:None):
    """One observation, one nominated absent-DB identity, no substitution.

    All task bindings/allowances must already exist. No issue/grant/barrier API.
    Other rows are retained and cheaply screened offline; they receive no effects.
    """
    l=coordinator.ledger;rule=coordinator.screening_rule      # v1 unless the coordinator was explicitly built with a registered v3 rule
    if not isinstance(l,(ControllerLedger,Ledger)):raise Denied('REVIEWED_ACCOUNTED_CONTROLLER_REQUIRED')
    if binding.retained_capture_sha256 and isinstance(l,ControllerLedger):
        prior=l.budget.previous
        if not prior or not binding.prior_accounting_sha256 or digest(prior)!=binding.prior_accounting_sha256 or prior.get('capture_checkpoint_sha256')!=binding.retained_capture_sha256:raise Denied('SEALED_PRIOR_ACCOUNTING_REQUIRED')
    check()
    if (binding.reference,binding.source_url,binding.source_record_id)!=(envelope.reference,envelope.source_url,envelope.source_record_id):raise Denied('NOMINATED_IDENTITY_BINDING')
    root=l.get(binding.discovery_key)
    if root['state']=='COMPLETE':
        receipt=root['checkpoint']
        if not binding.retained_capture_sha256 or digest(receipt)!=binding.retained_capture_sha256:raise Denied('CONSUMED_OBSERVATION_NO_REPLAY')
        children=root['outcome']['children']
        if binding.screening_batch_key:
            batch=l.get(binding.screening_batch_key);progress=batch['checkpoint'] or {};plan=progress.get('plan',{})
            if (batch['state']!='COMPLETE' or batch['task']!='LISTING_METADATA' or batch['contract']!='listing-batch-v1'
                or batch['subject']!=root['subject'] or binding.discovery_key not in batch['dependencies']
                or progress.get('kind')!='BATCH_PROGRESS_V1' or plan.get('capture_key')!=binding.discovery_key
                or plan.get('capture_sha256')!=digest(receipt) or batch['revision']!=digest(plan)
                or progress.get('next')!=plan.get('last')):raise Denied('NOMINATED_COMPLETED_BATCH_REQUIRED')
            children=progress['children']
    else:
        if binding.retained_capture_sha256:raise Denied('RETAINED_CAPTURE_NOT_COMPLETE')
        def listing(row):check();return listing_reader(row)
        children=coordinator.idox_source(l.claim(binding.discovery_key,lease_seconds=165),listing)
        check();receipt=l.get(binding.discovery_key)['checkpoint']
    contract=coordinator.contracts.get(root['contract'])
    from app.ingestion.idox_adapter import IdoxListingContract
    from app.ingestion.arcus_adapter import ArcusListingContract
    if not isinstance(contract,(IdoxListingContract,ArcusListingContract)):raise Denied('BOUND_IDOX_CONTRACT')      # the two known listing families only (the code is kept for the historical refusal)
    scope=contract.scope()
    if root['subject']!=scope or receipt['contract']!=root['contract'] or receipt['interval']!=[scope['start'],scope['end']] or receipt['applied_interval']!=receipt['interval']:raise Denied('RETAINED_SCOPE_BINDING')
    if isinstance(l,ControllerLedger):l.budget.capture_checkpoint_sha256=digest(receipt)
    # Recompute every disposition in trusted controller memory. A worker's
    # assertion is not used as evidence for selecting expensive effects.
    screens=[dict(reference=r['reference'],**rule.screen(r)) for r in receipt['records']]
    matches=[r for r in receipt['records'] if r['reference']==binding.reference]
    owner_basis=receipt.get('completeness_basis')      # an owner-accepted single page is never reported as a source-complete enumeration
    if owner_basis is not None:
        accepted=getattr(contract,'owner_acceptance',None)
        if accepted is None or receipt.get('owner_acceptance')!=owner_acceptance.require(accepted).binding():raise Denied('OWNER_ACCEPTANCE_RECEIPT_BINDING')      # the label is only ever taken from a receipt this contract's own registry entry vouches for
    result=dict(enumeration='COMPLETE_METADATA_RETAINED' if not owner_basis else owner_basis+'_METADATA_RETAINED',screening=screens,admission='NOT_ATTEMPTED',b2='NOT_ATTEMPTED',other_candidates_retrieved=0,
                **(dict(completeness_basis=owner_basis,owner_acceptance=receipt['owner_acceptance']) if owner_basis else {}))
    if not matches:return dict(result,outcome='DISCOVERY_SCREENING_ONLY_NOMINEE_NOT_RETURNED')
    r=matches[0]
    if digest(r)!=binding.listing_revision or binding.screening_key not in children:return dict(result,outcome='HOLD_CHANGED_ROW_OR_UNBOUND_TASK')
    if (r['source_url'],r['source_record_id'])!=(binding.source_url,binding.source_record_id):raise Denied('ROW_IDENTITY')
    expected=rule.screen(r)
    if not identity_admission_eligible(expected):return dict(result,outcome='DISCOVERY_SCREENING_ONLY_INSUFFICIENT_OR_EXCLUDED')      # the ONE authoritative routing outcome decides (v1 dispositions, or v3 ADMIT_SCHEME / ADMIT_FOR_ASSESSMENT)
    want_revision=digest(r) if rule.rule_version==RULE_V1 else assessment_identity(r,rule)[3]
    if rule.rule_version!=RULE_V1:
        record_sha,config,config_sha,revision=assessment_identity(r,rule)
        expected=dict(expected,record_sha256=record_sha,config=config,config_sha256=config_sha,assessment_revision=revision,assessment_sha256=digest(expected['count_assessment']),qualifier_output_sha256=digest(qualifier_output_of(expected)))
    check();screen_task=l.get(binding.screening_key)
    if binding.screening_batch_key and (screen_task['state']!='COMPLETE' or screen_task['dependencies']!=[binding.discovery_key]
        or screen_task['revision']!=want_revision or screen_task['subject']!={'kind':'APPLICATION','council':receipt['council'],'reference':r['reference']}
        or screen_task['task']!='SCREENING' or screen_task['contract']!=coordinator.screening_contract):raise Denied('EXACT_COMPLETED_SCREENING_REQUIRED')
    sc=screen_task['checkpoint'] if screen_task['state']=='COMPLETE' else coordinator.screening(l.claim(binding.screening_key,lease_seconds=165))
    if any(sc[k]!=v for k,v in expected.items()):raise Denied('FORGED_SCREENING_RECEIPT')
    if not identity_admission_eligible(sc,l.get(binding.screening_key)):raise Denied('FORGED_SCREENING_RECEIPT')      # the stored item must itself be the registered rule's eligible item
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app.db.models import Application
    with Session(l.engine) as s:
        known=s.scalar(select(Application.id).where(Application.council_code==envelope.council,Application.reference==binding.reference).limit(1))
    if known:return dict(result,outcome='DISCOVERY_SCREENING_ONLY_ALREADY_KNOWN',application_id=known)
    # Admission proof is rebuilt from the exact retained qualified listing,
    # never borrowed from a caller's different date window.
    from dataclasses import replace
    from datetime import date
    w=contract.admission_window(receipt,envelope.council)      # the contract that validated the capture re-derives its window proof
    envelope=replace(envelope,window=w,body_sha256=contract.record_body_sha256(r))
    # Exact task dependency was prepared before execution, never created by
    # the controller as a side effect of queue membership.
    fact=l.get(binding.factual_key)
    if fact['dependencies']!=[binding.screening_key]:raise Denied('FACTUAL_DEPENDENCY_BINDING')
    check()
    def detail(row):check();return detail_reader(row)
    outcome=coordinator.new_identity_source(l.claim(binding.factual_key,lease_seconds=165),envelope=envelope,council=council,supervised_reader=detail)
    check()
    return dict(result,outcome=outcome['outcome'],admission=outcome['identity'],b2=outcome.get('verification_scope','WITHHELD'),factual=outcome)


def capture(coordinator,key,*,listing_reader,check=lambda:None):
    """Discovery-only first phase; nominate nothing and issue no authority.

    A subsequent manifest may bind one retained record and its exact hash.
    Completed discovery is then consumed as evidence, never re-observed.
    """
    if not isinstance(coordinator.ledger,(ControllerLedger,Ledger)):raise Denied('REVIEWED_ACCOUNTED_CONTROLLER_REQUIRED')
    check();children=coordinator.idox_source(coordinator.ledger.claim(key,lease_seconds=165),listing_reader)
    check();receipt=coordinator.ledger.get(key)['checkpoint']
    if isinstance(coordinator.ledger,ControllerLedger):coordinator.ledger.budget.capture_checkpoint_sha256=digest(receipt)
    return dict(outcome='DISCOVERY_SCREENING_ONLY',admission='NOT_ATTEMPTED',b2='NOT_ATTEMPTED',
        source_sha256=receipt['source_sha256'],checkpoint_sha256=digest(receipt),children=children,
        screening=[dict(reference=r['reference'],**screen_row(r)) for r in receipt['records']])


def resume_capture(coordinator,key,*,checkpoint_sha256,prior_accounting_sha256,screening_keys,check=lambda:None):
    """Source-free retained materialisation/screening under new exact authority.

    Recovery of the old fence is a separate owner action; this cannot recover,
    issue authority or release a barrier. Completed children are never replayed.
    """
    l=coordinator.ledger
    if not isinstance(l,ControllerLedger):raise Denied('REVIEWED_ACCOUNTED_CONTROLLER_REQUIRED')
    prior=l.budget.previous
    if (not prior or digest(prior)!=prior_accounting_sha256
        or prior.get('capture_checkpoint_sha256')!=checkpoint_sha256):raise Denied('SEALED_PRIOR_ACCOUNTING_REQUIRED')
    check();root=l.get(key);receipt=root['checkpoint']
    if not receipt or digest(receipt)!=checkpoint_sha256 or receipt.get('kind')!='LISTING_RECEIPT_V1':raise Denied('RETAINED_CAPTURE_BINDING')
    rule=coordinator.screening_rule
    expected=[digest(dict(subject={'kind':'APPLICATION','council':receipt['council'],'reference':r['reference']},task='SCREENING',contract=coordinator.screening_contract,revision=digest(r) if rule.rule_version==RULE_V1 else assessment_identity(r,rule)[3])) for r in receipt['records']]
    if set(expected)!=set(screening_keys) or len(expected)!=len(screening_keys):raise Denied('EXACT_SCREENING_BATCH')
    if root['state']=='COMPLETE':children=root['outcome']['children']
    else:children=coordinator.resume_listing(l.claim(key,lease_seconds=165))
    if set(children)!=set(screening_keys) or len(children)!=len(screening_keys):raise Denied('EXACT_SCREENING_BATCH')
    results=[]
    for child in screening_keys:
        check();row=l.get(child)
        if row['state']=='COMPLETE':results.append(row['checkpoint'])
        else:results.append(coordinator.screening(l.claim(child,lease_seconds=165)))
    return dict(outcome='DISCOVERY_SCREENING_ONLY',checkpoint_sha256=checkpoint_sha256,children=children,screening=results,admission='NOT_ATTEMPTED',b2='NOT_ATTEMPTED')


def assessment_plan(coordinator,capture_key,*,capture_sha256,batch_keys,preserved_keys,check=lambda:None):
    """Stage 1 of a retained v3 assessment: verify the explicit v3 rule, the named preserved rows, the COMPLETE capture and its pinned checkpoint digest, recompute the exact v3 batch plans and require `batch_keys` to be
    exactly those, and snapshot the rows that must not change. Returns (receipt, plans, snapshot). Reads only."""
    from app.ingestion.batching import batch_plans
    l=coordinator.ledger;rule=coordinator.screening_rule
    if not isinstance(l,(ControllerLedger,Ledger)):raise Denied('REVIEWED_ACCOUNTED_CONTROLLER_REQUIRED')
    if rule.rule_version==RULE_V1:raise Denied('V3_RULE_REQUIRED')
    if not preserved_keys or len(set(preserved_keys))!=len(preserved_keys):raise Denied('PRESERVED_KEYS_REQUIRED')      # the earlier assessments and batches the run must prove unchanged; they must be named among the registered bindings so they can be read (a binding is not a new permission: they are COMPLETE, so the existing claim/fence checks already refuse any change)
    check();root=l.get(capture_key);receipt=root['checkpoint']
    if (root['state']!='COMPLETE' or root['task']!='DISCOVERY' or not isinstance(receipt,dict) or receipt.get('kind')!='LISTING_RECEIPT_V1'
        or digest(receipt)!=capture_sha256 or not receipt.get('durable_archive')):raise Denied('RETAINED_CAPTURE_BINDING')
    plans=batch_plans(capture_key,receipt,rule)
    if len(set(batch_keys))!=len(batch_keys) or set(batch_keys)!={p['key'] for p in plans}:raise Denied('EXACT_SCREENING_BATCH')
    return receipt,plans,{k:digest(l.get(k)) for k in (capture_key,*preserved_keys)}


def verify_assessed(coordinator,capture_key,receipt,*,capture_sha256,preserved_keys,snapshot,check=lambda:None):
    """Stage 3: recompute EVERY assessment in trusted memory and compare it (and the coordinator-added fields) with the stored receipt, then prove the capture and the named earlier rows byte-identical to `snapshot`.
    A forged or mismatched receipt, or any changed earlier row, stops the run. Returns the per-record assessments. Reads only."""
    l=coordinator.ledger;rule=coordinator.screening_rule;assessments=[]
    for record in receipt['records']:
        check();record_sha,config,config_sha,revision=assessment_identity(record,rule)
        key=digest(dict(subject={'kind':'APPLICATION','council':receipt['council'],'reference':record['reference']},task='SCREENING',contract=coordinator.screening_contract,revision=revision))
        item=l.get(key);stored=item['checkpoint'] or {}
        expected=dict(rule.screen(record),record_sha256=record_sha,config=config,config_sha256=config_sha,assessment_revision=revision,
                      source_url=record['source_url'],source_record_id=record['source_record_id'],source_sha256=receipt['source_sha256'],proposal=record['fields']['proposal'],application_type=record['fields']['application_type'])      # the fields the coordinator adds are compared too
        expected['assessment_sha256']=digest(expected['count_assessment']);expected['qualifier_output_sha256']=digest(qualifier_output_of(expected))
        if (item['state']!='COMPLETE' or item['task']!='SCREENING' or item['contract']!=coordinator.screening_contract or item['revision']!=revision or item['dependencies']!=[capture_key]
            or any(stored.get(k)!=v for k,v in expected.items()) or stored.get('capture_key')!=capture_key or stored.get('capture_checkpoint_sha256')!=capture_sha256
            or item['outcome']!=dict(outcome=expected['count_assessment']['admission'],retained=True)):raise Denied('FORGED_OR_MISMATCHED_ASSESSMENT')
        assessments.append(dict(reference=record['reference'],key=key,admission=expected['count_assessment']['admission'],eligible=identity_admission_eligible(stored,item)))
    if {k:digest(l.get(k)) for k in (capture_key,*preserved_keys)}!=snapshot:raise Denied('PRESERVED_ROWS_CHANGED')
    return assessments


def assess_retained(coordinator,capture_key,*,capture_sha256,batch_keys,preserved_keys,check=lambda:None):
    """Source-free v3 assessment of a retained, COMPLETE capture under an explicitly registered v3 rule (proposal section 2.4): `assessment_plan`, then each batch through the existing `process_batch`, then
    `verify_assessed`. No source client, no council, no application database, no identity. (The hosted run performs the same three stages with one accounted database slot per batch.)"""
    from app.ingestion.batching import process_batch
    receipt,plans,snapshot=assessment_plan(coordinator,capture_key,capture_sha256=capture_sha256,batch_keys=batch_keys,preserved_keys=preserved_keys,check=check)
    for plan in plans:
        check();done=process_batch(coordinator,plan['key'],check=check)
        if done['outcome'] not in {'BATCH_SCREENED','BATCH_ALREADY_COMPLETE'}:raise Denied('SCREENING_OUTCOME')
    assessments=verify_assessed(coordinator,capture_key,receipt,capture_sha256=capture_sha256,preserved_keys=preserved_keys,snapshot=snapshot,check=check)
    return dict(outcome='SCREENING_V3_ASSESSED',assessments=assessments,admission='NOT_ATTEMPTED',b2='NOT_ATTEMPTED',application_writes=0,source_calls=0)
