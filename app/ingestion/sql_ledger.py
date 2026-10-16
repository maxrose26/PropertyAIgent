"""Restricted SQL coordinator client. No URL discovery, DDL or authority issuance.

Connections/credentials/supervision belong to the reviewed controller. Worker
and trusted effect broker use separate principals. Application engine is never
passed to the source worker; it is used only by the shared writer callback.
"""
from sqlalchemy import select,text
from .ledger import Claim,Denied,UncertainPersistence,bounded
from .schema import WorkItem as W


class SQLLedger:
    def __init__(self,worker_engine,*,owner,authority,bindings,application_engine=None,broker_engine=None):
        self.worker_engine=worker_engine;self.owner=owner;self.authority=authority
        self.bindings=bounded(bindings);self.engine=application_engine;self.broker_engine=broker_engine
        if worker_engine.dialect.name!='postgresql':raise Denied('POSTGRES_SQL_CAPABILITIES_REQUIRED')

    @staticmethod
    def _limits(c):
        c.execute(text("SET LOCAL statement_timeout='10s'"))
        c.execute(text("SET LOCAL lock_timeout='3s'"))

    def get(self,key):
        if key not in self.bindings:raise Denied('TASK_NOT_BOUND')
        with self.worker_engine.begin() as c:
            self._limits(c)
            return dict(c.execute(select(W).where(W.c.key==key)).mappings().one())

    def _step(self,op,key,fence=0,payload=None,connection=None):
        if key not in self.bindings:raise Denied('TASK_NOT_BOUND')
        import json
        params=dict(op=op,key=key,fence=fence,owner=self.owner,authority=self.authority,
            binding=json.dumps(self.bindings[key]),payload=json.dumps(bounded(payload or {})))
        statement=text('SELECT public.ingestion_worker_step(:op,:key,:fence,:owner,:authority,CAST(:binding AS jsonb),CAST(:payload AS jsonb))')
        if connection is not None:return connection.execute(statement,params).scalar_one()
        with self.worker_engine.begin() as c:
            self._limits(c)
            result=c.execute(statement,params).scalar_one()
        return result

    def claim(self,key,owner=None,authority=None,lease_seconds=120):
        if owner not in (None,self.owner) or authority not in (None,self.authority):raise Denied('CONTROLLER_BINDING')
        row=self._step('claim',key,payload={'lease_seconds':lease_seconds});return Claim(key,row['fence'],self.owner)

    def enqueue(self,subject,task,*,contract,revision,dependencies,priority,max_attempts,parent_claim):
        import json
        from .ledger import digest
        if self.broker_engine is None or task!='SCREENING' or contract!='listing-screen-v1' or dependencies!=[parent_claim.key] or max_attempts!=2:raise Denied('QUALIFIED_CHILD_ONLY')
        parent=self.get(parent_claim.key)
        record=next(r for r in parent['checkpoint']['records'] if r['reference']==subject['reference'])
        identity=dict(subject=subject,task=task,contract=contract,revision=revision);key=digest(identity)
        child=dict(identity,key=key,dependencies=dependencies,priority=priority,max_attempts=max_attempts,limits=parent['limits'])
        canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
        with self.broker_engine.begin() as c:
            self._limits(c)
            result=self._step('enqueue_child',parent_claim.key,parent_claim.fence,dict(child=child,record_json=canonical(record),identity_json=canonical(identity)),connection=c)
        self.bindings[result['key']]={k:result[k] for k in ('subject','task','contract','revision')}
        return result['key']

    def _claim(self,claim):
        if claim.owner!=self.owner:raise Denied('WORKER_IDENTITY')

    def checkpoint(self,claim,receipt):
        self._claim(claim);self._step('checkpoint',claim.key,claim.fence,receipt)

    def intent(self,claim,operation,*,cost=1):
        self._claim(claim)
        if operation not in {'source_calls','writes'}:raise Denied('OPERATION')
        self._step('begin_source' if operation=='source_calls' else 'begin_write',claim.key,claim.fence,{'cost':cost})

    def finish(self,claim,outcome,*,state='COMPLETE',reason=None,**kwargs):
        self._claim(claim)
        if kwargs:raise Denied('UNREVIEWED_SQL_TRANSITION')
        if state=='COMPLETE':return self._step('complete',claim.key,claim.fence,outcome)
        if state not in {'UNSUPPORTED_CONTRACT','SAFETY_BLOCKED'}:raise Denied('OPERATOR_TRANSITION_REQUIRED')
        return self._step('block',claim.key,claim.fence,dict(state=state,reason=reason,outcome=outcome))

    def stop(self,reason,**kwargs):
        with self.worker_engine.begin() as c:
            self._limits(c)
            c.execute(text('SELECT public.ingestion_raise_stop(:reason)'),{'reason':reason[:512]})

    def resolve_source(self,claim,receipt):
        self._claim(claim)
        if self.broker_engine is None:raise Denied('TRUSTED_SOURCE_BROKER_REQUIRED')
        with self.broker_engine.begin() as c:
            self._limits(c)
            self._step('fence_effect',claim.key,claim.fence,connection=c)
            self._step('resolve_effect',claim.key,claim.fence,receipt,connection=c)

    def fenced_effect(self,claim,writer):
        self._claim(claim)
        if self.broker_engine is None or self.engine is None:raise Denied('SEPARATE_TRUSTED_BROKER_REQUIRED')
        entered=False
        try:
            with self.broker_engine.begin() as c:
                self._limits(c)
                row=self._step('fence_effect',claim.key,claim.fence,connection=c);entered=True
                result=bounded(writer(row))
                # DB-only callback has returned after committed shared readback.
                receipt=dict(result,cleanup='CLOSED',accounting_complete=True)
                self._step('resolve_effect',claim.key,claim.fence,receipt,connection=c)
            return receipt
        except Exception as exc:
            if not entered:raise
            try:self.stop('UNCERTAIN_COMMIT_OR_READBACK')
            except Exception:pass
            raise UncertainPersistence('RECONCILE_BEFORE_ANY_WRITE') from exc
