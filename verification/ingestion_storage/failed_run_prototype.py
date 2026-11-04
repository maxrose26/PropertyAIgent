"""Disposable-only retirement prototype. No live entry point or stop clearance."""
import copy,json
from . import intake_owner as op

def retire(c, *, period, run_id, key, expected_control, expected_item, evidence, fault=lambda:None):
    # Deliberately unavailable on a production destination until lifecycle review.
    op.require(c.info.host=='127.0.0.1' and c.info.port==5432 and c.info.dbname=='ingestion_provisioning_test','DISPOSABLE_ONLY')
    c.execute('BEGIN')
    try:
        c.execute("SET LOCAL statement_timeout='15s'; SET LOCAL lock_timeout='2s'")
        ctl=op.control(c,locked=True)
        op.require(ctl==expected_control,'CONTROL_DRIFT')
        marker=ctl.get('intake_run',{})
        op.require(marker.get('id')==run_id and marker.get('period')==period and marker.get('state')=='OPEN','RUN_IDENTITY')
        op.require(op.stop_snapshot(ctl)==dict(global_stop={'reason':'DAILY_INTAKE_SHARED_FAILURE'},manual_stop='DAILY_INTAKE_SHARED_FAILURE',last_hard_stop='DAILY_INTAKE_SHARED_FAILURE',hard_stop_generation=6),'STOP_DRIFT')
        item=c.execute('SELECT to_jsonb(w) FROM public.ingestion_work_items w WHERE key=%s FOR UPDATE',(key,)).fetchone()[0]
        op.require(item==expected_item and item['state']=='CLAIMED' and item['phase']=='SOURCE_INTENT' and item['fence']==1 and item['checkpoint'] is None,'ITEM_DRIFT')
        attempts=c.execute('SELECT fence,phase,finished_at,checkpoint FROM public.ingestion_work_attempts WHERE work_key=%s FOR UPDATE',(key,)).fetchall()
        op.require(attempts==[(1,'SOURCE_INTENT',None,None)],'ATTEMPT_DRIFT')
        actual=c.execute("SELECT name,sha256,sha256=encode(sha256(body),'hex') FROM public.ingestion_run_evidence WHERE period=%s AND run_id=%s ORDER BY name FOR SHARE",(period,run_id)).fetchall()
        op.require(actual==[(n,h,True) for n,h in sorted(evidence.items())] and len(actual)==2,'EVIDENCE_DRIFT')
        members=c.execute(op.MEMBERS).fetchall()
        op.require(not c.execute("SELECT pg_has_role(current_user,'ingestion_recovery_operator','USAGE')").fetchone()[0],'RECOVERY_BASELINE')
        c.execute('GRANT ingestion_recovery_operator TO CURRENT_USER WITH ADMIN FALSE, INHERIT TRUE, SET FALSE')
        result=c.execute('SELECT public.ingestion_recover_abandoned(%s,1,false)',(key,)).fetchone()[0]
        op.require(result['state']=='SAFETY_BLOCKED' and result['phase']=='RECOVERED' and result['fence']==2,'RECOVERY_POSTCONDITION')
        after=op.control(c)
        op.require(op.stop_snapshot(after)==dict(global_stop=ctl['global_stop'],manual_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',last_hard_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',hard_stop_generation=7),'GENERATION_POSTCONDITION')
        history=after['intake_periods'][period].setdefault('failed_runs',{})
        op.require(run_id not in history,'HISTORY_EXISTS')
        history[run_id]=dict(original_marker=copy.deepcopy(marker),status='FAILED_RECONCILED',actual_requests=None,request_count_status='UNKNOWN',historical_cause='UNKNOWN',manchester='NOT_ATTEMPTED',evidence=evidence,recovered_key=key,recovered_fence=2,source_or_write_replay_authorised=False)
        del after['intake_run']
        c.execute('UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(after),op.CONTROL))
        c.execute('REVOKE ingestion_recovery_operator FROM CURRENT_USER GRANTED BY CURRENT_USER RESTRICT')
        op.require(c.execute(op.MEMBERS).fetchall()==members,'PERMISSION_CLEANUP')
        fault()
        c.execute('COMMIT')
        return after
    except BaseException:
        c.execute('ROLLBACK')
        raise
