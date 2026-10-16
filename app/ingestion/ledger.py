"""Database-backed bounded tasks. No source client, CLI, scheduler or DB URL lookup.

All mutations serialize on the control row. This intentionally favours a small,
inspectable implementation over throughput. Production activation is absent.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib,json,math,re,time
from sqlalchemy import select,update,text,func,cast,Text,LargeBinary
from .schema import WorkItem as W,WorkAttempt as A,CONTROL
MAX_PAYLOAD=128*1024
TASKS={'DISCOVERY','LISTING_METADATA','SCREENING','FACTUAL_REFRESH'}
BLOCKED={'UNSUPPORTED_CONTRACT','SAFETY_BLOCKED','PERSISTENCE_UNCERTAIN'}
DEFAULT_LIMITS={'requests':80,'bytes':20*1024**2,'worker_seconds':45,'outer_seconds':60,'source_rss':1024**3,'aggregate_rss':1536*1024**2,'audit_bytes':2*1024**2,'rows':60,'pages':6}


class Denied(ValueError):pass
class StaleClaim(Denied):pass
class UncertainPersistence(RuntimeError):pass


def bounded(value,limit=MAX_PAYLOAD):
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if len(raw)>limit:raise Denied('PAYLOAD_BOUND')
    return json.loads(raw)


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def disposable(engine):
    u=engine.url
    if u.get_backend_name()=='sqlite':
        if u.database not in (None,'',':memory:') and not str(u.database).startswith('/tmp/ingestion-test-'):raise Denied('DISPOSABLE_DATABASE_ONLY')
    elif not (u.get_backend_name()=='postgresql' and u.host=='127.0.0.1' and u.port==5432 and u.database=='stage4_discovery_test' and u.username=='discovery_test'):
        raise Denied('DISPOSABLE_DATABASE_ONLY')


@dataclass(frozen=True)
class Claim:
    key:str
    fence:int
    owner:str


class Ledger:
    def __init__(self,engine,clock=time.time):
        # Concrete delivery is offline/disposable only; no hidden activation flag.
        disposable(engine);self.engine=engine;self.clock=clock

    @contextmanager
    def tx(self):
        with self.engine.begin() as c:
            if self.engine.dialect.name=='postgresql':
                c.execute(text("SET LOCAL lock_timeout='3s'"));c.execute(text("SET LOCAL statement_timeout='10s'"))
                control=c.execute(select(W).where(W.c.key==CONTROL).with_for_update()).mappings().one()
            else:
                # Obtain SQLite's write reservation before any decisions/reads.
                c.execute(update(W).where(W.c.key==CONTROL).values(fence=W.c.fence+1))
                control=c.execute(select(W).where(W.c.key==CONTROL)).mappings().one()
            yield c,dict(control)
            # Whole-ledger ceiling, including append-only attempt evidence.
            total=0
            for table,cap in ((W,4096),(A,12288)):
                if c.scalar(select(func.count()).select_from(table))>cap:raise Denied('LEDGER_ROW_BOUND')
                for col in table.columns:
                    size=func.octet_length(cast(col,Text)) if self.engine.dialect.name=='postgresql' else func.length(cast(cast(col,Text),LargeBinary))
                    total+=c.scalar(select(func.coalesce(func.sum(size),0)))
            if total>32*1024**2:raise Denied('LEDGER_STORAGE_BOUND')

    def _control(self,c,control):c.execute(update(W).where(W.c.key==CONTROL).values(outcome=bounded(control['outcome'])))

    def grant(self,authority,keys,*,source_calls=0,writes=0,expires_at,contracts):
        """Explicit disposable allowance. Historical authority strings rejected."""
        if not re.fullmatch(r'INGESTION_TEST_[A-Za-z0-9_-]{1,70}',authority):raise Denied('NO_HISTORICAL_OR_LIVE_AUTHORITY')
        keys=sorted(set(keys));contracts=sorted(set(contracts))
        if not keys or len(keys)>1000 or any(not re.fullmatch('[0-9a-f]{64}',k) or k==CONTROL for k in keys):raise Denied('GRANT_KEYS')
        if any(type(x) is not int or not 0<=x<=1000 for x in (source_calls,writes)) or not math.isfinite(expires_at) or expires_at<=self.clock():raise Denied('GRANT_BOUNDS')
        value=bounded(dict(keys=keys,contracts=contracts,source_calls=source_calls,writes=writes,expires_at=expires_at))
        with self.tx() as (c,control):
            grants=control['outcome']['grants']
            if authority in grants:raise Denied('AUTHORITY_ALREADY_REGISTERED')
            if len(grants)>=32:raise Denied('GRANT_LEDGER_BOUND')
            grants[authority]=value;self._control(c,control)

    def enqueue(self,subject,task,*,contract,revision='v1',dependencies=(),priority=50,eligible_at=0,state='QUEUED',reason=None,max_attempts=2,limits=None,parent_claim=None):
        subject=bounded(subject,4096)
        if subject.get('kind') not in {'DISCOVERY_SCOPE','APPLICATION','SCHEME'} or task not in TASKS:raise Denied('SUBJECT_OR_TASK')
        if not isinstance(subject.get('council'),str) or not re.fullmatch('[a-z]{2,30}',subject['council']):raise Denied('COUNCIL')
        if subject['council']=='trafford':raise Denied('OUT_OF_SCOPE')
        if subject['kind']=='DISCOVERY_SCOPE':
            from datetime import date
            if subject.get('semantics') not in {'VALIDATED','RECEIVED'} or date.fromisoformat(subject['start'])>date.fromisoformat(subject['end']):raise Denied('DISCOVERY_SCOPE')
            if task not in {'DISCOVERY','LISTING_METADATA'}:raise Denied('SCOPE_TASK')
        elif not isinstance(subject.get('reference' if subject['kind']=='APPLICATION' else 'scheme_id'),str):raise Denied('SUBJECT_IDENTITY')
        if not isinstance(contract,str) or not 1<=len(contract)<=100 or not isinstance(revision,str) or not 1<=len(revision)<=100:raise Denied('VERSION_BOUND')
        if state not in {'QUEUED','DEFERRED','UNSUPPORTED_CONTRACT','SAFETY_BLOCKED','PERSISTENCE_UNCERTAIN'}:raise Denied('INITIAL_STATE')
        if state!='QUEUED' and not reason:raise Denied('BLOCK_REASON_REQUIRED')
        if type(priority) is not int or not 0<=priority<=100 or type(max_attempts) is not int or not 1<=max_attempts<=3 or not math.isfinite(eligible_at):raise Denied('TASK_BOUNDS')
        lim=dict(DEFAULT_LIMITS if limits is None else limits)
        if set(lim)!=set(DEFAULT_LIMITS) or any(type(v) is not int or not 0<v<=DEFAULT_LIMITS[k] for k,v in lim.items()):raise Denied('RESOURCE_LIMITS')
        deps=sorted(set(dependencies))
        if len(deps)>32:raise Denied('DEPENDENCY_BOUND')
        key=digest(dict(subject=subject,task=task,contract=contract,revision=revision))
        with self.tx() as (c,control):
            if parent_claim is not None:
                self._owned(c,control,parent_claim)
                if parent_claim.key not in deps:raise Denied('CHILD_DEPENDENCY')
            old=c.execute(select(W).where(W.c.key==key)).mappings().first()
            if old:
                if old['limits']!=lim or old['max_attempts']!=max_attempts:raise Denied('CONFLICTING_DUPLICATE_TASK')
                if old['dependencies']!=deps and not (parent_claim is not None and task=='SCREENING'):raise Denied('CONFLICTING_DUPLICATE_TASK')
                return key
            if any(k==key or c.execute(select(W.c.key).where(W.c.key==k)).first() is None for k in deps):raise Denied('DEPENDENCIES_MUST_EXIST')
            c.execute(W.insert().values(key=key,subject=subject,task=task,contract=contract,revision=revision,dependencies=deps,priority=priority,eligible_at=eligible_at,state=state,reason=reason,next_action='REVIEW' if state in BLOCKED else 'CLAIM_WHEN_AUTHORISED',limits=lim,authority=None,attempt_count=0,max_attempts=max_attempts,fence=0,owner=None,lease_until=None,phase='IDLE',checkpoint=None,outcome=None))
        return key

    def get(self,key):
        with self.engine.connect() as c:return dict(c.execute(select(W).where(W.c.key==key)).mappings().one())

    def _permit(self,control,row,authority,operation=None,c=None):
        if control['outcome']['global_stop']:raise Denied('GLOBAL_STOP')
        if row['task'] in {'DISCOVERY','LISTING_METADATA'} and row['subject']['kind']=='DISCOVERY_SCOPE' and control['outcome'].get('council_deferred_until',{}).get(row['subject']['council'],0)>self.clock():raise Denied('COUNCIL_DEFERRED')
        if c is not None and c.execute(select(W.c.key).where(W.c.key!=row['key'],W.c.phase=='WRITE_INTENT')).first():raise Denied('UNRESOLVED_WRITE_BARRIER')
        g=control['outcome']['grants'].get(authority)
        if not g or row['key'] not in g['keys'] or row['contract'] not in g['contracts'] or self.clock()>=g['expires_at']:raise Denied('NO_APPLICABLE_AUTHORITY')
        if operation and g[operation]<=0:raise Denied('AUTHORITY_EXHAUSTED')
        return g

    def claim(self,key,owner,authority,lease_seconds=120):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',owner) or not 1<=lease_seconds<=480:raise Denied('CLAIM_BOUND')
        with self.tx() as (c,control):
            row=dict(c.execute(select(W).where(W.c.key==key)).mappings().one());self._permit(control,row,authority,c=c)
            if row['state'] not in {'QUEUED','DEFERRED'} or row['eligible_at']>self.clock() or row['attempt_count']>=row['max_attempts']:raise Denied('NOT_ELIGIBLE')
            for dep in row['dependencies']:
                if c.execute(select(W.c.state).where(W.c.key==dep)).scalar_one()!='COMPLETE':raise Denied('DEPENDENCY_UNFINISHED')
            fence=row['fence']+1
            c.execute(update(W).where(W.c.key==key).values(state='CLAIMED',owner=owner,authority=authority,fence=fence,lease_until=self.clock()+lease_seconds,attempt_count=row['attempt_count']+1,phase='CLAIMED',reason=None,next_action='EXECUTE_APPROVED_STAGE'))
            c.execute(A.insert().values(work_key=key,fence=fence,owner=owner,authority=authority,started_at=self.clock(),phase='CLAIMED',checkpoint=row['checkpoint']))
        return Claim(key,fence,owner)

    def claim_next(self,owner,authority):
        # Finite authorised candidate scan; every chosen key is atomically claimed.
        with self.tx() as (c,control):
            grant=control['outcome']['grants'].get(authority)
            if not grant:raise Denied('NO_APPLICABLE_AUTHORITY')
            keys=list(c.execute(select(W.c.key).where(W.c.key.in_(grant['keys']),W.c.state.in_(['QUEUED','DEFERRED']),W.c.eligible_at<=self.clock(),W.c.attempt_count<W.c.max_attempts).order_by(W.c.priority.desc(),W.c.eligible_at,W.c.key).limit(1000)).scalars())
        for key in keys:
            try:return self.claim(key,owner,authority)
            except Denied:continue
        return None

    def _owned(self,c,control,claim):
        row=dict(c.execute(select(W).where(W.c.key==claim.key)).mappings().one())
        if row['state']!='CLAIMED' or row['fence']!=claim.fence or row['owner']!=claim.owner or row['lease_until']<=self.clock():raise StaleClaim('STALE_WORKER')
        self._permit(control,row,row['authority'],c=c);return row

    def checkpoint(self,claim,evidence):
        evidence=bounded(evidence)
        with self.tx() as (c,control):
            row=self._owned(c,control,claim)
            if row['phase']=='WRITE_INTENT':raise Denied('WRITE_READBACK_REQUIRED')
            if row['phase']=='SOURCE_INTENT':
                from .coordinator import validate_outer
                if evidence.get('cleanup')!='CLOSED' or evidence.get('accounting_complete') is not True:raise Denied('SOURCE_CLOSURE_REQUIRED')
                validate_outer(evidence.get('outer_supervisor',{}),row['limits'])
            c.execute(update(W).where(W.c.key==claim.key).values(checkpoint=evidence,phase='CHECKPOINTED'))
            c.execute(update(A).where(A.c.work_key==claim.key,A.c.fence==claim.fence).values(checkpoint=evidence,phase='CHECKPOINTED'))

    def intent(self,claim,operation,*,cost=1):
        if operation not in {'source_calls','writes'} or type(cost) is not int or not 1<=cost<=2 or (cost==2 and operation!='writes'):raise Denied('OPERATION')
        with self.tx() as (c,control):
            row=self._owned(c,control,claim)
            if row['phase'] not in {'CLAIMED','CHECKPOINTED'}:raise Denied('UNRESOLVED_INTENT')
            if operation=='writes' and row['task']!='FACTUAL_REFRESH':raise Denied('TASK_OPERATION')
            if operation=='source_calls' and (row['task'] not in {'DISCOVERY','LISTING_METADATA'} or row['subject']['kind']!='DISCOVERY_SCOPE'):raise Denied('TASK_OPERATION')
            g=self._permit(control,row,row['authority'],operation,c=c);
            if g[operation]<cost:raise Denied('AUTHORITY_EXHAUSTED')
            g[operation]-=cost;self._control(c,control)
            phase='SOURCE_INTENT' if operation=='source_calls' else 'WRITE_INTENT'
            c.execute(update(W).where(W.c.key==claim.key).values(phase=phase))
            c.execute(update(A).where(A.c.work_key==claim.key,A.c.fence==claim.fence).values(phase=phase))

    def finish(self,claim,outcome,*,state='COMPLETE',reason=None,delay=0,resolved_receipt=None,council_defer_seconds=0):
        outcome=bounded(outcome)
        if state not in {'COMPLETE','DEFERRED',*BLOCKED} or not 0<=delay<=86400 or not 0<=council_defer_seconds<=86400:raise Denied('OUTCOME_STATE')
        if state!='COMPLETE' and not reason:raise Denied('OUTCOME_REASON')
        with self.tx() as (c,control):
            row=self._owned(c,control,claim)
            if resolved_receipt is not None:
                receipt=bounded(resolved_receipt)
                if row['phase']=='WRITE_INTENT':raise Denied('WRITE_READBACK_REQUIRED')
                if row['phase']=='SOURCE_INTENT':
                    from .coordinator import validate_outer
                    if receipt.get('cleanup')!='CLOSED' or receipt.get('accounting_complete') is not True:raise Denied('SOURCE_CLOSURE_REQUIRED')
                    validate_outer(receipt.get('outer_supervisor',{}),row['limits'])
                c.execute(update(W).where(W.c.key==claim.key).values(checkpoint=receipt))
                c.execute(update(A).where(A.c.work_key==claim.key,A.c.fence==claim.fence).values(checkpoint=receipt))
                row['phase']='CHECKPOINTED'
            if row['phase'] in {'SOURCE_INTENT','WRITE_INTENT'}:raise Denied('UNRESOLVED_INTENT')
            if council_defer_seconds:
                deferred=control['outcome'].setdefault('council_deferred_until',{})
                council=row['subject']['council'];deferred[council]=max(deferred.get(council,0),self.clock()+council_defer_seconds);self._control(c,control)
            if state=='PERSISTENCE_UNCERTAIN':
                control['outcome']['global_stop']={'reason':'UNCERTAIN_PERSISTENCE'};self._control(c,control)
            c.execute(update(W).where(W.c.key==claim.key).values(state=state,reason=reason,outcome=outcome,eligible_at=self.clock()+delay,owner=None,lease_until=None,phase='FINISHED',next_action='NONE' if state=='COMPLETE' else 'REVIEW' if state in BLOCKED else 'WAIT_THEN_RECHECK_AUTHORITY'))
            c.execute(update(A).where(A.c.work_key==claim.key,A.c.fence==claim.fence).values(finished_at=self.clock(),phase='FINISHED',outcome=outcome))

    def defer_council(self,council,until):
        if not self.clock()<until<=self.clock()+86400:raise Denied('COUNCIL_DEFER_BOUND')
        with self.tx() as (c,control):
            deferred=control['outcome'].setdefault('council_deferred_until',{})
            deferred[council]=max(deferred.get(council,0),until);self._control(c,control)

    def stop(self,reason,*,claim=None,persistence_uncertain=False):
        with self.tx() as (c,control):
            control['outcome']['global_stop']=bounded({'reason':reason},4096);self._control(c,control)
            if claim is not None:
                row=c.execute(select(W).where(W.c.key==claim.key)).mappings().one()
                if row['state']=='CLAIMED' and row['fence']==claim.fence and row['owner']==claim.owner:
                    outcome={'outcome':'PERSISTENCE_UNCERTAIN' if persistence_uncertain else 'SAFETY_BLOCKED','reason':reason}
                    c.execute(update(W).where(W.c.key==claim.key).values(state=outcome['outcome'],reason=reason,outcome=outcome,owner=None,lease_until=None,fence=row['fence']+1,next_action='RECONCILE'))
                    c.execute(update(A).where(A.c.work_key==claim.key,A.c.fence==claim.fence).values(finished_at=self.clock(),outcome=outcome))

    def recover(self,claim,*,cleanup_closed):
        """Expiry never grants replay permission. No automatic unblock interface."""
        with self.tx() as (c,control):
            row=dict(c.execute(select(W).where(W.c.key==claim.key)).mappings().one())
            if row['state']!='CLAIMED' or row['fence']!=claim.fence or row['owner']!=claim.owner or row['lease_until']>self.clock():raise Denied('RECOVERY_BOUNDARY')
            phase=row['phase'];uncertain=phase=='WRITE_INTENT'
            state='PERSISTENCE_UNCERTAIN' if uncertain else 'SAFETY_BLOCKED' if phase=='SOURCE_INTENT' or not cleanup_closed else 'DEFERRED'
            if uncertain or phase=='SOURCE_INTENT' or not cleanup_closed:
                control['outcome']['global_stop']={'reason':'ABANDONED_EFFECT_OR_UNCERTAIN_ACCOUNTING_CLEANUP','work_key':claim.key};self._control(c,control)
            outcome={'outcome':'ABANDONED_'+phase,'source_or_write_replay_authorised':False,'cleanup_closed':cleanup_closed}
            c.execute(update(W).where(W.c.key==claim.key).values(state=state,reason=outcome['outcome'],owner=None,lease_until=None,fence=row['fence']+1,outcome=outcome,next_action='RECONCILE' if state in BLOCKED else 'CLAIM_OFFLINE_CHECKPOINT_ONLY',phase='RECOVERED'))
            c.execute(update(A).where(A.c.work_key==claim.key,A.c.fence==claim.fence).values(finished_at=self.clock(),phase='RECOVERED',outcome=outcome))

    def fenced_effect(self,claim,writer):
        """Serialize guarded shared writer; durable WRITE_INTENT precedes entry.

        If acknowledgement is lost at ANY boundary, keep intent and stop. No
        exactly-once claim across separate writer/ledger transactions.
        """
        entered=False
        try:
            with self.tx() as (c,control):
                row=self._owned(c,control,claim)
                if row['phase']!='WRITE_INTENT':raise Denied('WRITE_INTENT_REQUIRED')
                entered=True
                value=bounded(writer(row))
                c.execute(update(W).where(W.c.key==claim.key).values(checkpoint=value,phase='CHECKPOINTED'))
                c.execute(update(A).where(A.c.work_key==claim.key,A.c.fence==claim.fence).values(checkpoint=value,phase='CHECKPOINTED'))
            return value
        except Exception as exc:
            if not entered:raise
            try:self.stop('UNCERTAIN_COMMIT_OR_READBACK',claim=claim,persistence_uncertain=True)
            except Exception:pass # durable WRITE_INTENT still requires recovery reconciliation
            raise UncertainPersistence('RECONCILE_BEFORE_ANY_WRITE') from exc
