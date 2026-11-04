"""Actual runtime authentication only; existing meter, route and strict TLS."""
import time
from datetime import datetime,timezone
from decimal import Decimal
from sqlalchemy import text
from .operational_controller import DatabaseBudget
from .owner_pilot import envelope,safe_result
from . import intake_owner as op

PROFILE_FIELDS=('current_user','session_user','capability_usage','statement_timeout','lock_timeout',
    'idle_in_transaction_session_timeout','worker_step_execute','registration_execute',
    'evidence_write_execute','evidence_read_execute','credential_deadline')

def exact_deadline_epoch(deadline):
    """Exact microsecond epoch of the same UTC datetime written by the owner."""
    delta=datetime.fromtimestamp(deadline,timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc)
    micros=(delta.days*86400+delta.seconds)*1000000+delta.microseconds
    return Decimal((int(micros<0),tuple(int(d) for d in str(abs(micros))),-6))

def profile_comparison(row,role,deadline):
    """Same exact guard, with fixed names/booleans only; no observed values."""
    op.require(role in op.ROLES,'OWNER_RESTRICTED_AUTHENTICATION_REFUSED')
    worker=role=='ingestion_worker_login'
    expected=(role,role,True,'10s','3s','20s',True,worker,worker,worker,
              exact_deadline_epoch(deadline))
    shape=isinstance(row,tuple) and len(row)==len(expected)
    checks={name:bool(shape and row[i]==expected[i]) for i,name in enumerate(PROFILE_FIELDS[:-1])}
    checks['credential_deadline']=bool(shape and type(row[10]) is Decimal and row[10].is_finite() and row[10]==expected[10])
    first=next((name for name,passed in checks.items() if not passed),None) if shape else 'ROW_SHAPE'
    return dict(version='RESTRICTED_PROFILE_COMPARISON_V1',row_shape=shape,checks=checks,
                first_mismatch=first,status='MATCH' if shape and all(checks.values()) else 'MISMATCH')

def qualify(runtime,deadline,*,budget_factory=DatabaseBudget):
    receipt=dict(version='RUNTIME_AUTHENTICATION_V1',period=runtime.args.period,execution_binding=runtime.binding,
        deadline=deadline,status='REFUSED',roles=[],attempts=[],source_requests=0,max_attempts_per_role=2)
    runtime.runtime_qualification=receipt
    try:
        op.require(deadline-time.time()>1500,'SETUP_TEN_MINUTE_BOUND')
        with envelope():
            for role,cap in op.ROLES.items():
                for attempt in (1,2):
                    budget=budget_factory(**runtime.run.database_limits(dict(statements=20,connections=1,returned_bytes=8192,seconds=12)))
                    runtime.run.budgets.append(budget);error=None;comparison=None;deadline_observation=None
                    try:
                        engine=budget.engine(runtime.urls[role],**runtime.options)
                        with engine.connect() as c:
                            diagnostic=getattr(runtime,"deadline_diagnostic",False)
                            query="""SELECT current_user,session_user,pg_has_role(current_user,:cap,'USAGE'),
                              current_setting('statement_timeout'),current_setting('lock_timeout'),current_setting('idle_in_transaction_session_timeout'),
                              has_function_privilege(current_user,'public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)','EXECUTE'),
                              has_function_privilege(current_user,'public.ingestion_register_bolton_exception(jsonb)','EXECUTE'),
                              has_function_privilege(current_user,'public.ingestion_intake_evidence_write(text,text,text,bytea)','EXECUTE'),
                              has_function_privilege(current_user,'public.ingestion_intake_evidence_read(text,text,text)','EXECUTE'),
                              (SELECT extract(epoch FROM rolvaliduntil) FROM pg_roles WHERE rolname=current_user)"""
                            if diagnostic:query+=", (SELECT extract(epoch FROM rolvaliduntil)::double precision FROM pg_roles WHERE rolname=current_user)"
                            raw=tuple(c.execute(text(query),dict(cap=cap)).one());row=raw[:11] if diagnostic else raw
                            if diagnostic:
                                from .deadline_evidence import deadline_evidence
                                deadline_observation=deadline_evidence(deadline,raw[11],row[10])
                                deadline_observation.update(qualification_comparison='EXACT_MICROSECOND_EPOCH_V1',qualification_expected_numeric_epoch=str(exact_deadline_epoch(deadline)),qualification_strict_equal=type(row[10]) is Decimal and row[10].is_finite() and row[10]==exact_deadline_epoch(deadline))
                                receipt.setdefault("deadline_observations",[]).append(dict(role=role,attempt=attempt,evidence=deadline_observation))
                            comparison=profile_comparison(row,role,deadline)
                            if comparison['status']!='MATCH':
                                # Store BEFORE cleanup can fail; subsequent failures
                                # cannot replace this first comparison evidence.
                                receipt.setdefault('first_qualification_failure',dict(role=role,attempt=attempt,comparison=comparison))
                            op.require(comparison['status']=='MATCH','OWNER_RESTRICTED_AUTHENTICATION_REFUSED')
                    except BaseException as exc:error=exc
                    finally:
                        closed=budget.close([])
                        record=dict(role=role,attempt=attempt,**{k:closed[k] for k in ('connection_attempts','driver_statements','returned_data_value_bytes','elapsed_seconds','connections_closed','cleanup','connection_diagnostics')})
                        if comparison is not None:record['profile_comparison']=comparison
                        if deadline_observation is not None:record['deadline_observation']=deadline_observation
                        receipt['attempts'].append(record)
                    op.require(closed['connections_closed'] and closed['cleanup']=='CLOSED','OWNER_RESTRICTED_CONNECTION_NOT_CLOSED')
                    if error is None:receipt['roles'].append(dict(role=role,identity='VERIFIED',interface='VERIFIED',connection_closed=True));break
                    diagnostic=closed['connection_diagnostics'][-1] if closed['connection_diagnostics'] else {}
                    # One immediate reconnect with the SAME stable secret is the
                    # documented refresh opportunity. Never retry SQL/effects,
                    # an open native connection, or a circuit-breaker refusal.
                    retry=(attempt==1 and closed['driver_statements']==0 and diagnostic.get('reason_code') in ('AUTHENTICATION_REJECTED','AUTH_SECRET_UNAVAILABLE')
                        and diagnostic.get('failed_native_connection_finished') is True)
                    if retry:continue
                    receipt['failure']=dict(safe_result(error),diagnostic=diagnostic);raise error
        op.require(len(receipt['roles'])==2 and deadline-time.time()>1500,'RUNTIME_AUTHENTICATION_REFUSED')
        receipt['status']='VERIFIED_BOTH_RESTRICTED_ROLES'
    except BaseException as exc:
        receipt.setdefault('failure',safe_result(exc))
    runtime.emit('runtime_authentication',receipt)
    return receipt
