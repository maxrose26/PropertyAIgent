"""Finite input/work/reporting phases for the actual operational wrapper."""
from datetime import datetime,timezone
import hashlib,json,signal,time
from .operational_cleanup import HardDeadline,arm_deadline
from .operational_publication import canonical
from .connection_diagnostics import safe_failure,PreparationFailure

ACCOUNTING_SCHEMA='VALUE_BASIS_V2'


def legacy_counts(accounting):
    """Project a value/basis accounting block to the historical flat-integer shape (None where the value is not known). Historical blocks pass through unchanged."""
    def flat(x):return x.get('value') if isinstance(x,dict) and 'basis' in x else x
    if not isinstance(accounting,dict):return accounting
    out={}
    for key,block in accounting.items():
        out[key]={k:flat(v) for k,v in block.items()} if isinstance(block,dict) and key in ('administration','runtime') else block
    return out


def early_outcome(failure,closure):
    """Truthful, separately stated outcome for an exit before any administrative connection could be attempted."""
    return dict(preparation='FAILED',administrative_connection='NOT_ATTEMPTED',failure=('CLASSIFIED' if failure.get('reason_code') not in (None,'UNKNOWN','UNEXPECTED_EXCEPTION','FAILURE_EXPORT_UNAVAILABLE') else 'UNCLASSIFIED'),
                closure='VERIFIED' if closure.get('overall')=='CLOSED' else 'UNCERTAIN',route_qualified=False,worker_authentication_qualified=False)


TIMING=dict(input_seconds=300,active_seconds=480,work_seconds=450,diagnostic_seconds=25,report_seconds=5,outer_seconds=790)

def finalise(journal,result,*,input_seconds,active_started,output=print):
    result['phase_timing']=dict(credential_input_seconds=input_seconds,
        active_seconds_before_reporting=0 if active_started is None else time.monotonic()-active_started)
    saved=False
    try:
        raw=canonical(result)
        current=sum(p.stat().st_size for p in journal.root.rglob('*') if p.is_file())
        prior=journal.root/'final-result.json'
        projected=current-(prior.stat().st_size if prior.exists() else 0)+len(raw)
        receipt=dict(result,audit=str(journal.file),audit_sha256=hashlib.sha256(journal.file.read_bytes()).hexdigest(),
            audit_chain_head=journal.head,result_sha256=hashlib.sha256(raw).hexdigest(),
            persisted_evidence_bytes=projected,terminal_json_bytes=0,exported_bytes=projected)
        for _ in range(10):
            line=json.dumps(receipt,sort_keys=True);size=len(line.encode())+1
            if receipt['terminal_json_bytes']==size:break
            receipt['terminal_json_bytes']=size;receipt['exported_bytes']=projected+size
        else:raise ValueError('OUTPUT_ACCOUNTING')
        if size>256*1024 or receipt['exported_bytes']>2*1024**2-8192:raise ValueError('COMBINED_OUTPUT_BOUND')
        # Both persisted replacement and terminal are checked before either effect.
        journal.save('final-result.json',result);saved=True
        output(line,flush=True)
    except BaseException:
        fallback=dict(status='STOP_RECONCILE_NO_RETRY',cleanup='UNCERTAIN',reason='FINAL_EVIDENCE_OR_OUTPUT_UNCERTAIN',
            accounting=result.get('accounting',{}),audit=str(journal.file))
        try:
            payload=json.dumps(fallback,sort_keys=True)
            current=sum(p.stat().st_size for p in journal.root.rglob('*') if p.is_file())
            prior=journal.root/'final-result.json'
            projected=current-(prior.stat().st_size if prior.exists() else 0)+len(canonical(fallback))
            if projected+len(payload.encode())+1>2*1024**2:raise ValueError('FALLBACK_BOUND')
            if not saved:journal.save('final-result.json',fallback)
            output(payload,flush=True)
        except BaseException:pass
        result=fallback
    return result

def early_accounting(progress,elapsed):
    """Complete preparation / administrative / runtime accounting for an exit BEFORE a Runner exists.

    Each counter carries its basis: MEASURED (observed by the progress record, so a zero is a measured zero), NOT_STARTED (the producing component was provably never
    reached because the measured connection count is zero) or UNKNOWN (no progress record, so nothing is claimed). "No runtime slot" is NOT "zero total work"."""
    if progress is None:
        unknown=dict(value=None,basis='UNKNOWN')
        return dict(administration={k:dict(unknown) for k in ('connections','commands','returned_data_value_bytes','failed_native_connections','failed_native_finished',
                                                               'credential_generations','secret_mappings','role_changes')}|dict(supervised_seconds=elapsed),
                    runtime=dict(slot_receipts=None,slot_state='UNKNOWN',supervised_seconds=dict(unknown)),preparation=dict(state='PREPARATION_PROGRESS_UNAVAILABLE'),
                    historical_accounting_gaps='PRESERVED_NOT_RECONSTRUCTED')
    calls=progress.database_connection_calls
    measured=lambda v:dict(value=v,basis='MEASURED');not_started=dict(value=0,basis='NOT_STARTED') if calls==0 else dict(value=None,basis='UNKNOWN')
    admin=dict(connections=measured(calls),supervised_seconds=elapsed)
    for k in ('commands','returned_data_value_bytes','failed_native_connections','failed_native_finished','credential_generations','secret_mappings','role_changes'):admin[k]=dict(not_started)
    return dict(administration=admin,runtime=dict(slot_receipts={},slot_state='NO_RUNTIME_SLOT_CREATED',supervised_seconds=dict(not_started)),
                preparation=progress.work(),historical_accounting_gaps='PRESERVED_NOT_RECONSTRUCTED')


def early_closure(baseline,proof,progress):
    """Overall closure derived from positive evidence only; each component is reported separately and an unknown stays UNCERTAIN."""
    process=dict(status='UNCERTAIN')
    try:
        from .tls_trust import owned_resources
        groups=proof.get('owned_groups_removed') is True and proof.get('owned_survivors')==0 if proof is not None else True   # no native memory (disposable only)
        after=owned_resources()
        if baseline is not None:
            new=len(after['socket_fds']-baseline['socket_fds']);children=len(after['children'])
            process.update(new_socket_count=new,live_child_count=children,memory=proof)
            if groups and new==0 and children==0:process['status']='CLOSED'
    except BaseException:pass
    attempted=progress.database_connection_calls if progress is not None else None
    connection=dict(status='NO_CONNECTION_ATTEMPTED' if attempted==0 else 'UNCERTAIN',database_connect_calls=attempted)
    access=dict(status='NOT_REQUIRED_NO_ACCESS_CREATED' if attempted==0 else 'UNCERTAIN')
    positive=connection['status']=='NO_CONNECTION_ATTEMPTED' and access['status']=='NOT_REQUIRED_NO_ACCESS_CREATED' and process['status']=='CLOSED'
    return dict(access=access,connections=connection,process=process,overall='CLOSED' if positive else 'UNCERTAIN',
                outer_scope_removal='NOT_VERIFIABLE_BEFORE_CONTROLLER_EXIT')


def session(journal,expiry,reader,prepare,*,memory=None,output=print,timing=TIMING,progress=None,baseline=None):
    """Same production and disposable controller; no runtime timing override."""
    outer=time.monotonic();input_started=outer;active=None;worker=None;hard=None;raw=None;input_seconds=0;where='SESSION_INPUT'
    try:
        arm_deadline(timing['input_seconds'],'SECURE_INPUT_DEADLINE')
        journal.emit('credential_input_started',dict(maximum_seconds=timing['input_seconds'],database_and_secret_operations_permitted=False))
        raw=reader();input_seconds=time.monotonic()-input_started
        where='REGISTRATION_EXPIRY'
        if datetime.now(timezone.utc)>=datetime.fromisoformat(expiry):raise PreparationFailure('REGISTRATION_EXPIRY','REGISTRATION_EXPIRED')
        journal.emit('credential_input_completed',dict(elapsed_seconds=input_seconds))
        active=time.monotonic();hard=HardDeadline(active+timing['active_seconds'])
        arm_deadline(timing['work_seconds'],'WORK_CLOSURE_RESERVE')
        worker=prepare(raw,active);raw=None
        result=worker.execute()
    except BaseException as exc:
        if active is None:input_seconds=time.monotonic()-input_started
        if worker is not None:result=worker.failed(exc)
        else:
            proof=None if memory is None else {'status':'UNKNOWN'}
            try:
                if memory is not None:proof=memory.close()
            except BaseException:pass
            elapsed=time.monotonic()-(active if active is not None else input_started)
            try:
                # The stage is RECORDED, never inferred: the stage in progress, else "between stages" after the last completed one, else where the session itself stopped.
                failure=safe_failure(exc,'PREPARATION')
                if 'stage' not in failure:
                    if progress is not None and progress.current:stage=progress.current
                    elif progress is not None and progress.completed:stage='AFTER_'+progress.completed[-1]
                    else:stage=where
                    failure=dict(failure,stage=stage)
                closure=early_closure(baseline,proof if (proof is None or proof.get('status')!='UNKNOWN') else dict(owned_groups_removed=False,owned_survivors=None),progress)
                result=dict(status='STOP_RECONCILE_NO_RETRY',cleanup=closure['overall'],closure_components=closure,failure=failure,
                    authority_invalidation='NOT_REQUIRED_NO_AUTHORITY',access='NO_ACCESS_CREATED',
                    preparation=progress.report() if progress is not None else None,
                    accounting=early_accounting(progress,elapsed),accounting_schema=ACCOUNTING_SCHEMA,outcome=early_outcome(failure,closure),owned_cleanup=closure['process'],
                    application_writes=0,pipeline_retry='HELD',stage4='OPEN',historical_uncertainty_preserved=True)
            except BaseException:
                # The exporter itself failed (for example the driver is unavailable to the classifier). A final result must still exist; nothing is claimed.
                result=dict(status='STOP_RECONCILE_NO_RETRY',cleanup='UNCERTAIN',failure=dict(phase='PREPARATION',stage=where,exception_kind='OTHER',sqlstate=None,reason_code='FAILURE_EXPORT_UNAVAILABLE',
                    classification_source='FIXED_PREPARATION_CODE',message_exported=False,flags={}),authority_invalidation='NOT_REQUIRED_NO_AUTHORITY',access='NO_ACCESS_CREATED',
                    accounting=early_accounting(None,elapsed),accounting_schema=ACCOUNTING_SCHEMA,outcome=dict(preparation='UNKNOWN',administrative_connection='UNKNOWN',failure='UNCLASSIFIED',closure='UNCERTAIN',route_qualified=False,worker_authentication_qualified=False),application_writes=0,pipeline_retry='HELD',stage4='OPEN',historical_uncertainty_preserved=True)
        try:journal.emit('stopped_before_runner',result)
        except BaseException:pass
    finally:raw=None
    end=min(outer+timing['outer_seconds'],time.monotonic()+timing['report_seconds'],(active+timing['active_seconds']) if active is not None else float('inf'))
    reporting_hard=HardDeadline(end)
    if hard is not None:hard.close()
    hard=reporting_hard
    try:
        arm_deadline(max(.001,end-time.monotonic()),'FINAL_REPORT_DEADLINE')
        return finalise(journal,result,input_seconds=input_seconds,active_started=active,output=output)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);hard.close()
