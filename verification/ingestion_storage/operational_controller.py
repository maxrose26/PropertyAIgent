"""Finite manual controller, injected bindings only; no secret loader or live CLI.

Application runtime never imports verification. Trusted controller owns the
qualified parsers, screening and broker; an arbitrary future worker is excluded.
"""
from dataclasses import dataclass
import json,time
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool
from app.ingestion.ledger import Denied,digest
from app.ingestion.sql_ledger import SQLLedger
from app.ingestion.listing_screening import screen_row


class DatabaseBudget:
    """Counts attempts before connect and every cursor/internal driver command.

    Includes SQLAlchemy initialization, BEGIN/COMMIT/ROLLBACK. Records operation
    kinds only, never SQL parameters, URLs, credentials or row values.
    """
    def __init__(self,*,connections=16,statements=120,seconds=165,stop_file=None):
        if not (1<=connections<=16 and 20<=statements<=120 and 0<seconds<=165):raise Denied('CONTROLLER_CEILING')
        self.connection_cap=connections;self.statement_cap=statements;self.seconds=seconds
        self.started=time.monotonic();self.attempts=0;self.statements=0;self.kinds={};self.opened=[];self.engines=[];self.stop_file=Path(stop_file) if stop_file else None
    def check(self):
        if time.monotonic()-self.started>=self.seconds or (self.stop_file and self.stop_file.exists()):raise Denied('MANUAL_STOP_OR_CONTROLLER_DEADLINE')
    def tick(self,kind,*,cleanup=False):
        if not cleanup:self.check()
        # Reserve eight slots for finite rollback/closure; no commit after stop.
        if self.statements>=self.statement_cap-(0 if cleanup else 8):raise Denied('DRIVER_STATEMENT_BOUND')
        self.statements+=1;self.kinds[kind]=self.kinds.get(kind,0)+1
    def engine(self,url,*,ssl=None):
        import psycopg
        from sqlalchemy.engine import make_url
        u=make_url(url)
        disposable=(u.host=='127.0.0.1' and u.port==5432 and u.database=='ingestion_provisioning_test')
        if not disposable:
            from .tls_trust import verified_trust
            ca,_=verified_trust()
            if (u.host,u.port,u.database)!=('aws-0-eu-west-2.pooler.supabase.com',5432,'postgres') or ssl!={'sslmode':'verify-full','sslrootcert':str(ca)}:raise Denied('REVIEWED_TLS_ENDPOINT_REQUIRED')
        budget=self
        class Cursor(psycopg.Cursor):
            def execute(self,query,params=None,**kwargs):
                budget.tick('cursor');return super().execute(query,params,**kwargs)
            def executemany(self,*a,**kw):raise Denied('BULK_FORBIDDEN')
        class Connection(psycopg.Connection):
            def _exec_command(self,command,*a,**kw):
                raw=command if isinstance(command,bytes) else str(command).encode()
                rollback=raw.strip().upper().startswith(b'ROLLBACK')
                budget.tick('driver_internal',cleanup=rollback)
                return super()._exec_command(command,*a,**kw)
        def creator():
            budget.check()
            if budget.attempts>=budget.connection_cap:raise Denied('CONNECTION_BOUND')
            budget.attempts+=1
            c=Connection.connect(host=u.host,port=u.port,dbname=u.database,user=u.username,password=u.password,
                connect_timeout=3,prepare_threshold=None,cursor_factory=Cursor,
                options='-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=20000',**(ssl or {}))
            budget.opened.append(c)
            try:
                with c.cursor() as q:
                    q.execute("SELECT current_setting('statement_timeout'),current_setting('lock_timeout'),current_setting('idle_in_transaction_session_timeout')")
                    if q.fetchone()!=('10s','3s','20s'):raise Denied('SERVER_TIMEOUT_PROFILE')
                c.rollback();return c
            except BaseException:c.close();raise
        e=create_engine('postgresql+psycopg://',creator=creator,poolclass=QueuePool,pool_size=1,max_overflow=0,pool_timeout=3,hide_parameters=True,isolation_level='AUTOCOMMIT' if u.username=='ingestion_worker_login' else 'READ COMMITTED')
        self.engines.append(e);return e
    def close(self,engines):
        errors=[]
        for e in engines:
            try:e.dispose()
            except Exception:errors.append('DISPOSE')
        for c in self.opened:
            try:c.close()
            except Exception:errors.append('CLOSE')
        return dict(connection_attempts=self.attempts,driver_statements=self.statements,statement_kinds=self.kinds,
            connections_closed=all(c.closed for c in self.opened),cleanup='CLOSED' if not errors and all(c.closed for c in self.opened) else 'UNCERTAIN',
            errors=errors,elapsed_seconds=round(time.monotonic()-self.started,3))


class ControllerLedger(SQLLedger):
    @staticmethod
    def _limits(c):
        # Every physical connection was verified by DatabaseBudget.creator.
        # This class may only receive engines created by that fixed factory.
        pass
    def __init__(self,*args,budget,**kwargs):
        for e in (args[0],kwargs.get('broker_engine'),kwargs.get('application_engine')):
            if e is not None and e not in getattr(budget,'engines',[]):raise Denied('ACCOUNTED_ENGINE_REQUIRED')
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


def execute(coordinator,binding,*,listing_reader,detail_reader,envelope,council,check=lambda:None):
    """One observation, one nominated absent-DB identity, no substitution.

    All task bindings/allowances must already exist. No issue/grant/barrier API.
    Other rows are retained and cheaply screened offline; they receive no effects.
    """
    l=coordinator.ledger;check()
    if (binding.reference,binding.source_url,binding.source_record_id)!=(envelope.reference,envelope.source_url,envelope.source_record_id):raise Denied('NOMINATED_IDENTITY_BINDING')
    root=l.get(binding.discovery_key)
    if root['state']=='COMPLETE':raise Denied('CONSUMED_OBSERVATION_NO_REPLAY')
    capture=[]
    def listing(row):
        check();value=listing_reader(row);capture.append(value);return value
    children=coordinator.idox_source(l.claim(binding.discovery_key,lease_seconds=165),listing)
    check();receipt=l.get(binding.discovery_key)['checkpoint']
    # Recompute every disposition in trusted controller memory. A worker's
    # assertion is not used as evidence for selecting expensive effects.
    screens=[dict(reference=r['reference'],**screen_row(r)) for r in receipt['records']]
    matches=[r for r in receipt['records'] if r['reference']==binding.reference]
    result=dict(enumeration='COMPLETE_METADATA_RETAINED',screening=screens,admission='NOT_ATTEMPTED',b2='NOT_ATTEMPTED',other_candidates_retrieved=0)
    if not matches:return dict(result,outcome='DISCOVERY_SCREENING_ONLY_NOMINEE_NOT_RETURNED')
    r=matches[0]
    if digest(r)!=binding.listing_revision or binding.screening_key not in children:return dict(result,outcome='HOLD_CHANGED_ROW_OR_UNBOUND_TASK')
    if (r['source_url'],r['source_record_id'])!=(binding.source_url,binding.source_record_id):raise Denied('ROW_IDENTITY')
    expected=screen_row(r)
    if expected['disposition'] not in {'SUPPORTED_PROCESSING_PRIORITY','RELATED_APPLICATION_FOLLOW_THROUGH'}:return dict(result,outcome='DISCOVERY_SCREENING_ONLY_INSUFFICIENT_OR_EXCLUDED')
    check();sc=coordinator.screening(l.claim(binding.screening_key,lease_seconds=165))
    if any(sc[k]!=v for k,v in expected.items()):raise Denied('FORGED_SCREENING_RECEIPT')
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app.db.models import Application
    with Session(l.engine) as s:
        known=s.scalar(select(Application.id).where(Application.council_code==envelope.council,Application.reference==binding.reference).limit(1))
    if known:return dict(result,outcome='DISCOVERY_SCREENING_ONLY_ALREADY_KNOWN',application_id=known)
    # Exact task dependency was prepared before execution, never created by
    # the controller as a side effect of queue membership.
    fact=l.get(binding.factual_key)
    if fact['dependencies']!=[binding.screening_key]:raise Denied('FACTUAL_DEPENDENCY_BINDING')
    check()
    def detail(row):check();return detail_reader(row)
    outcome=coordinator.new_identity_source(l.claim(binding.factual_key,lease_seconds=165),envelope=envelope,council=council,supervised_reader=detail)
    check()
    return dict(result,outcome=outcome['outcome'],admission=outcome['identity'],b2=outcome.get('verification_scope','WITHHELD'),factual=outcome)
