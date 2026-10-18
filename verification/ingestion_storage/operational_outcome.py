"""Finite input/work/reporting phases for the actual operational wrapper."""
from datetime import datetime,timezone
import hashlib,json,signal,time
from .operational_cleanup import HardDeadline,arm_deadline
from .operational_publication import canonical
from .connection_diagnostics import safe_failure

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

def session(journal,expiry,reader,prepare,*,memory=None,output=print,timing=TIMING):
    """Same production and disposable controller; no runtime timing override."""
    outer=time.monotonic();input_started=outer;active=None;worker=None;hard=None;raw=None;input_seconds=0
    try:
        arm_deadline(timing['input_seconds'],'SECURE_INPUT_DEADLINE')
        journal.emit('credential_input_started',dict(maximum_seconds=timing['input_seconds'],database_and_secret_operations_permitted=False))
        raw=reader();input_seconds=time.monotonic()-input_started
        if datetime.now(timezone.utc)>=datetime.fromisoformat(expiry):raise ValueError('REGISTRATION_EXPIRED_BEFORE_EFFECTS')
        journal.emit('credential_input_completed',dict(elapsed_seconds=input_seconds))
        active=time.monotonic();hard=HardDeadline(active+timing['active_seconds'])
        arm_deadline(timing['work_seconds'],'WORK_CLOSURE_RESERVE')
        worker=prepare(raw,active);raw=None
        result=worker.execute()
    except BaseException as exc:
        if active is None:input_seconds=time.monotonic()-input_started
        if worker is not None:result=worker.failed(exc)
        else:
            proof={'status':'UNKNOWN'}
            try:
                if memory is not None:proof=memory.close()
            except BaseException:pass
            result=dict(status='STOP_RECONCILE_NO_RETRY',cleanup='UNCERTAIN',failure=safe_failure(exc,'ROUTE_VALIDATION'),
                authority_invalidation='NOT_REQUIRED_NO_AUTHORITY',
                accounting=dict(administration=dict(connections=0,commands=0,returned_data_value_bytes=0),runtime=dict(slot_receipts={},supervised_seconds=0)),owned_cleanup=proof)
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
