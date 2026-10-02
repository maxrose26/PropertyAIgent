"""Audit commands and preserve fresh authority through flush, commit and return."""
from functools import wraps
import hashlib
import inspect
import json
import logging
import secrets
import weakref
from sqlalchemy import event
from app.security import access

_log=logging.getLogger('propertyaigent.access')
_owned=weakref.WeakKeyDictionary()
PAID_LIMITS={
    'visual.classify':(1,32 * 1024 * 1024), 'contacts.enrich':(8,120000), 'plan.summary':(1,300000),
    'allocation.summary':(2,300000), 'shortlist.intelligence':(2,300000),
    'shortlist.research':(24,300000), 'search.parse':(1,20000),
    'report.narrative':(1,300000), 'evaluation.run':(2,300000),
    'pipeline.processing':(100,300000), 'pipeline.extract':(3,300000),
    'pipeline.refresh':(3,300000), 'plan.extract':(1,300000),
    'scheme.summary':(1,300000), 'applicant.intelligence':(2,300000),
}


def _size(value):
    if isinstance(value,str):return len(value)
    if isinstance(value,dict):return sum(_size(k)+_size(v) for k,v in value.items())
    if isinstance(value,(list,tuple)):return sum(_size(v) for v in value)
    return 0


class _Provider:
    def __init__(self,client,action,budget=None):
        self._client=client;self._action=action;self._budget=budget if budget is not None else [0]
        self.responses=self
    def create(self,*args,**kwargs):
        access.require_operator(self._action,paid=True)
        calls,chars=PAID_LIMITS[self._action]
        if self._budget[0] >= calls or _size(args)+_size(kwargs)>chars:
            raise access.AccessDenied('Paid action limit exceeded.')
        self._budget[0]+=1
        result=self._client.responses.create(*args,**kwargs)
        access.require_operator(self._action,paid=True)
        return result

    def with_options(self, *, timeout):
        # Preserve the existing per-search timeout while keeping every clone
        # on the same authority and call budget. No endpoint/header overrides.
        import math
        access.require_operator(self._action,paid=True)
        if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not math.isfinite(timeout) or not 0<timeout<=300:
            raise access.AccessDenied('Unsupported provider timeout.')
        return _Provider(self._client.with_options(timeout=timeout),self._action,self._budget)


def protect_session(session,actor):
    if session in _owned:
        if _owned[session] is not actor:raise access.AccessDenied('Session authority changed.')
        return
    _owned[session]=actor
    def check(*unused):
        if access.current_actor() is not actor or actor.role!='operator':
            raise access.AccessDenied('Session authority changed.')
    def check_private_writes(*unused):
        check()
        from app.db.models import Buyer,BuyerMandate,AgentEvaluationHistory,AgentEvaluationClaim,CurrentBuyerOpportunityState
        from app.services.authorised_reads import mandate_by_id
        from sqlalchemy import select, inspect as sa_inspect
        pending=list(session.new)+list(session.dirty)+list(session.deleted)
        new_buyers={row.id:row for row in session.new if isinstance(row,Buyer)}
        for row in pending:
            # Check persisted ownership as well as proposed foreign keys: a
            # detached/dirty object must not be reparented to launder access.
            state=sa_inspect(row)
            if state.persistent and isinstance(row,(Buyer,BuyerMandate,AgentEvaluationHistory,AgentEvaluationClaim,CurrentBuyerOpportunityState)):
                model=type(row)
                with session.no_autoflush:
                    if isinstance(row,Buyer):
                        original=session.execute(select(Buyer.workspace_id,Buyer.id).where(Buyer.id==state.identity[0])).one()
                        access.require_buyer(*original)
                    elif isinstance(row,BuyerMandate):
                        allowed=session.execute(select(Buyer.id).join(BuyerMandate,BuyerMandate.buyer_id==Buyer.id).where(BuyerMandate.id==state.identity[0],Buyer.workspace_id==actor.workspace_id,Buyer.id.in_(actor.buyer_ids))).first()
                        if not allowed:raise access.AccessDenied('Access denied.')
                    else:
                        original=session.execute(select(model.buyer_mandate_id).where(model.id==state.identity[0])).scalar_one()
                        mandate_by_id(session,original)
            if isinstance(row,Buyer):
                access.require_buyer(row.workspace_id,row.id)
            elif isinstance(row,BuyerMandate):
                if row.buyer_id in new_buyers:
                    buyer=new_buyers[row.buyer_id]
                    access.require_buyer(buyer.workspace_id,buyer.id)
                else:
                    with session.no_autoflush:
                        allowed=session.execute(select(Buyer.id).where(Buyer.id==row.buyer_id,Buyer.workspace_id==actor.workspace_id,Buyer.id.in_(actor.buyer_ids))).first()
                    if not allowed:raise access.AccessDenied('Access denied.')
            elif isinstance(row,(AgentEvaluationHistory,AgentEvaluationClaim,CurrentBuyerOpportunityState)):
                mandate_by_id(session,row.buyer_mandate_id)
    event.listen(session,'before_flush',check_private_writes)
    event.listen(session,'before_commit',check)


def command(action,*,paid=False):
    def decorate(function):
        signature=inspect.signature(function)
        @wraps(function)
        def invoke(*args,**kwargs):
            correlation=secrets.token_hex(12);principal=None;revision=None
            try:
                actor=access.require_operator(action,paid=paid)
                principal=access.actor_label();revision=actor.revision
                bound=signature.bind(*args,**kwargs)
                session=bound.arguments.get('session')
                if session is not None:protect_session(session,actor)
                if paid:
                    if action not in PAID_LIMITS:raise access.AccessDenied('Unknown paid action.')
                    if _size(bound.arguments)>PAID_LIMITS[action][1]:raise access.AccessDenied('Paid action input limit exceeded.')
                    for key in ('client','openai_client'):
                        if bound.arguments.get(key) is not None:
                            bound.arguments[key]=_Provider(bound.arguments[key],action)
                result=function(*bound.args,**bound.kwargs)
                access.require_operator(action,paid=paid)
            except BaseException as exc:
                _log.info(json.dumps(dict(action=action,outcome='denied' if isinstance(exc,access.AccessDenied) else 'failed',principal=principal,revision=revision,correlation=correlation)))
                raise
            targets={k:v for k,v in bound.arguments.items() if k.endswith('_id') and isinstance(v,int) and not isinstance(v,bool)}
            _log.info(json.dumps(dict(action=action,outcome='completed',principal=principal,revision=revision,correlation=correlation,targets=targets)))
            return result
        return invoke
    return decorate


def bounded_provider(client, action):
    """Apply the same boundary to clients constructed inside a command."""
    access.require_operator(action, paid=True)
    if action not in PAID_LIMITS:
        raise access.AccessDenied('Unknown paid action.')
    return client if isinstance(client, _Provider) and client._action == action else _Provider(client, action)
