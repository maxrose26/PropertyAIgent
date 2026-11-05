"""Exact owner-only Attempt06 disposition. No source, deployment or worker bypass."""
import copy
import hashlib
import json
import re
from . import intake_owner as op
from .database_evidence import canonical, verify_inventory

PERIOD='b-dbpilot-20261027-1102-06'
SUCCESSOR='b-dbpilot-20261027-1102-07'
SCOPE=dict(kind='DISCOVERY_SCOPE',council='tameside',start='2026-10-27',end='2026-11-02',semantics='RECEIVED')
RUN='f0afadd31d56467580ce61b51bbf19a3'
JOB='job-dblr422jnfac73d8eaeg'
KEY='dc8ae276a9c3f697b9905adf0ec8835398009769b69e788e4fd70e13216ee6fc'
AUTHORITY='INGESTION_CHAIN_TAMESIDE_CAPTURE_6111B8A8125C'
BINDING=dict(revision='da8959d06bea35da5104fe6638aa566952004853',workflow_sha256='5b87c6cbef2944fa05468314fc6daefc19b785644b04e04d1ff382b0596cadea',manifest_sha256='6e223d11ad74799688a9c18d3b245d3d2908abc4f806dc5507eb5c5ccab2c77a')
EVIDENCE={'final/result-before-publication.json':'3386dfb045fe64cd149faea835a0b377b7d25e3733eb53e31fd6687644de1e11','final/events-before-publication.json':'8a23b2641ce84002f7c726aa9de6681570b7d12ce8f874fc639910cf03ee0294'}
STOP6=dict(global_stop={'reason':'DAILY_INTAKE_SHARED_FAILURE'},manual_stop='DAILY_INTAKE_SHARED_FAILURE',last_hard_stop='DAILY_INTAKE_SHARED_FAILURE',hard_stop_generation=6)
STOP7=dict(STOP6,manual_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',last_hard_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',hard_stop_generation=7)
ACCEPTED=dict(STOP7,global_stop=None,manual_stop=None)
ROLE='ingestion_recovery_operator'

def sha(value):return hashlib.sha256(canonical(value)).hexdigest()

def marker_valid(marker):
    op.require(type(marker) is dict and marker.get('id')==RUN and marker.get('period')==PERIOD and marker.get('state')=='OPEN' and marker.get('day')=='2026-11-02' and marker.get('publication_path')=='docs/design/ingestion-operational-execution-daily-intake/'+PERIOD+'/'+RUN+'/final/result-before-publication.json','A06_RUN_IDENTITY')

def receipt(marker):
    marker_valid(marker)
    return dict(version='ATTEMPT06_RECOVERY_V1',original_marker=copy.deepcopy(marker),period=PERIOD,run_id=RUN,job_id=JOB,
        execution_binding=BINDING,evidence=EVIDENCE,successor=SUCCESSOR,status='FAILED_RECONCILED',actual_requests=None,
        request_count_status='UNKNOWN',historical_cause='UNKNOWN',manchester='NOT_ATTEMPTED',recovered_key=KEY,
        recovered_fence=2,source_or_write_replay_authorised=False,stop_before=STOP6,stop_after=STOP7)

def check_evidence(c):
    for name,h in EVIDENCE.items():
        observed=c.execute("SELECT encode(sha256(public.ingestion_intake_evidence_read(%s,%s,%s)),'hex')",(PERIOD,RUN,name)).fetchone()[0]
        op.require(observed==h,'A06_EVIDENCE')

def history(c,ctl,*,disposed=False,expected_sha=None):
    p=ctl.get('intake_periods',{}).get(PERIOD,{})
    r=p.get('failed_runs',{}).get(RUN)
    op.require(type(r) is dict and op.json_equal(c,r,receipt(r.get('original_marker'))),'A06_RECEIPT')
    if expected_sha is not None:op.require(sha(r)==expected_sha,'A06_RECEIPT_BINDING')
    op.require(p.get('execution_binding')==BINDING and p.get('evidence_backend')=='POSTGRES_PILOT_V1' and p.get('fixed_window')=={'start':'2026-10-27','end':'2026-11-02'} and p.get('max_runs')==1 and set(p.get('councils',{}))=={'tameside','manchester'} and p.get('days')=={'2026-11-02':{'tameside':KEY}},'A06_PERIOD_BINDING')
    check_evidence(c)
    row=c.execute('SELECT state,phase,fence,owner,lease_until,reason,next_action,checkpoint,outcome::jsonb FROM public.ingestion_work_items WHERE key=%s',(KEY,)).fetchone()
    op.require(row==('SAFETY_BLOCKED','RECOVERED',2,None,None,'ABANDONED_SOURCE_INTENT','RECONCILE',None,{'outcome':'ABANDONED_SOURCE_INTENT','source_or_write_replay_authorised':False}),'A06_RECOVERED_ITEM')
    op.require(c.execute('SELECT fence,phase,finished_at IS NOT NULL,checkpoint FROM public.ingestion_work_attempts WHERE work_key=%s',(KEY,)).fetchall()==[(1,'RECOVERED',True,None)],'A06_RECOVERED_ATTEMPT')
    if disposed:op.require(p.get('failure_disposition')==disposition(sha(r)),'A06_DISPOSITION')
    return r

def disposition(receipt_sha):return dict(version='ATTEMPT06_DISPOSITION_V1',receipt_sha256=receipt_sha,successor=SUCCESSOR,before=STOP7,after=ACCEPTED)

def successor_guard(c,b,ctl):
    if b.get('period')!=SUCCESSOR:return
    op.require(type(b.get('attempt06_receipt_sha256')) is str and re.fullmatch('[a-f0-9]{64}',b['attempt06_receipt_sha256']),'A06_RECEIPT_BINDING')
    op.require(b.get('evidence_backend')=='POSTGRES_PILOT_V1' and b.get('accepted_stop')==ACCEPTED,'A06_SUCCESSOR_BINDING')
    history(c,ctl,disposed=True,expected_sha=b.get('attempt06_receipt_sha256'))
    op.require(op.stop_snapshot(ctl)==ACCEPTED,'A06_STOP_DRIFT')

def baseline(c,b):
    op.identity(c);op.inventory(c);verify_inventory(c);op.owner_absent(c)
    return op.dormant(c,stable_verifiers=b.get('credential_verifier_sha256') if b.get('credential_policy')=='STABLE_RESTRICTED_V1' else None)

def lock(c):
    op.enter_owner(c)
    c.execute('LOCK TABLE public.ingestion_work_items,public.ingestion_work_attempts IN SHARE ROW EXCLUSIVE MODE')
    c.execute('LOCK TABLE public.ingestion_run_evidence IN SHARE MODE')
    return op.control(c,locked=True)

def cleanup(c,members):
    op.leave_owner(c)
    op.require(c.execute(op.MEMBERS).fetchall()==members,'A06_PERMISSION_CLEANUP')

def recover(c,b):
    """Single mutation attempt. Any COMMIT exception requires readback, never retry."""
    op.validate_binding(b);op.require(b['period']==SUCCESSOR,'A06_SUCCESSOR_BINDING')
    op.begin(c)
    try:
        members=baseline(c,b);ctl=lock(c);op.retained_cleanup(c,ctl)
        op.require(op.json_equal(c,op.stop_snapshot(ctl),STOP6),'A06_STOP_DRIFT')
        marker=ctl.get('intake_run');marker_valid(marker)
        p=ctl.get('intake_periods',{}).get(PERIOD,{})
        op.require(p.get('execution_binding')==BINDING and p.get('evidence_backend')=='POSTGRES_PILOT_V1' and p.get('fixed_window')=={'start':'2026-10-27','end':'2026-11-02'} and p.get('max_runs')==1 and set(p.get('councils',{}))=={'tameside','manchester'} and p.get('days')=={'2026-11-02':{'tameside':KEY}} and not p.get('failed_runs') and not p.get('failure_disposition') and SUCCESSOR not in ctl.get('intake_periods',{}),'A06_PERIOD_BINDING')
        g=ctl.get('grants',{}).get(AUTHORITY,{})
        op.require(g.get('intake_run')==RUN and g.get('intake_period')==PERIOD and g.get('capture_key')==KEY and g.get('execution_binding')==BINDING and type(g.get('expires_at')) is int and g['expires_at']==0,'A06_GRANT_BINDING')
        op.require(not c.execute("SELECT pid FROM pg_stat_activity WHERE usename=ANY(%s)",(list(op.ROLES)+['ingestion_application_login','ingestion_recovery_login'],)).fetchall(),'EXISTING_PIPELINE_SESSION')
        op.require(not any(type(v.get('expires_at')) not in (int,float) or v['expires_at']>__import__('time').time() for v in ctl.get('grants',{}).values()),'UNEXPIRED_OR_UNREADABLE_AUTHORITY')
        row=c.execute('SELECT authority,revision,state,phase,fence,attempt_count,checkpoint,lease_until<extract(epoch FROM clock_timestamp()),task,contract,subject::jsonb FROM public.ingestion_work_items WHERE key=%s',(KEY,)).fetchone()
        op.require(row==(AUTHORITY,PERIOD+'-2026-11-02-tameside','CLAIMED','SOURCE_INTENT',1,1,None,True,'DISCOVERY','tameside-screening-metadata-five-v1',SCOPE),'A06_ITEM_BINDING')
        op.require(c.execute('SELECT fence,phase,finished_at,checkpoint,authority FROM public.ingestion_work_attempts WHERE work_key=%s',(KEY,)).fetchall()==[(1,'SOURCE_INTENT',None,None,AUTHORITY)],'A06_ATTEMPT_BINDING')
        op.require(c.execute("SELECT count(*) FROM public.ingestion_work_items WHERE key<>%s AND (phase IN ('SOURCE_INTENT','WRITE_INTENT') OR state='PERSISTENCE_UNCERTAIN' OR revision=%s OR authority=%s)",(KEY,PERIOD+'-2026-11-02-manchester',AUTHORITY)).fetchone()==(0,),'A06_OTHER_WORK')
        op.require(c.execute("SELECT name FROM public.ingestion_run_evidence WHERE period=%s AND run_id=%s ORDER BY name",(PERIOD,RUN)).fetchall()==[(n,) for n in sorted(EVIDENCE)],'A06_EVIDENCE')
        check_evidence(c)
        expected=receipt(marker);op.require(sha(expected)==b['attempt06_receipt_sha256'],'A06_RECEIPT_BINDING')
        op.leave_owner(c)
        rows=c.execute("SELECT grantor::regrole::text,admin_option,inherit_option,set_option FROM pg_auth_members WHERE roleid=%s::regrole AND member=current_user::regrole",(ROLE,)).fetchall()
        op.require(len(rows)==1 and rows[0][0]!='postgres' and rows[0][1:]==(True,False,False),'A06_RECOVERY_ADMIN_ONLY')
        c.execute('GRANT ingestion_recovery_operator TO postgres WITH ADMIN FALSE,INHERIT TRUE,SET FALSE GRANTED BY postgres')
        c.execute('SELECT public.ingestion_recover_abandoned(%s,1,false)',(KEY,)).fetchone()
        c.execute('REVOKE ingestion_recovery_operator FROM postgres GRANTED BY postgres RESTRICT')
        op.enter_owner(c);after=op.control(c)
        want=copy.deepcopy(ctl);want.update(STOP7)
        op.require(op.json_equal(c,after,want),'A06_RECOVERY_EFFECTS')
        want['intake_periods'][PERIOD]['failed_runs']={RUN:expected};del want['intake_run']
        c.execute('UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(want),op.CONTROL))
        history(c,want,expected_sha=b['attempt06_receipt_sha256']);op.no_hazards(c,want)
        cleanup(c,members);c.execute('COMMIT')
    except BaseException:
        try:c.execute('ROLLBACK')
        except BaseException:pass
        raise
    return dict(status='COMMIT_ACKNOWLEDGED',phase='recovery',receipt_sha256=sha(expected),independent_readback_required=True)

def dispose(c,b):
    op.validate_binding(b);op.require(b['period']==SUCCESSOR,'A06_SUCCESSOR_BINDING');op.begin(c)
    try:
        members=baseline(c,b);ctl=lock(c);op.retained_cleanup(c,ctl);op.no_hazards(c,ctl)
        op.require(op.json_equal(c,op.stop_snapshot(ctl),STOP7) and SUCCESSOR not in ctl.get('intake_periods',{}) and 'intake_run' not in ctl,'A06_STOP_DRIFT')
        history(c,ctl,expected_sha=b['attempt06_receipt_sha256'])
        op.require('failure_disposition' not in ctl['intake_periods'][PERIOD],'A06_ALREADY_DISPOSED')
        after=copy.deepcopy(ctl);after.update(global_stop=None,manual_stop=None)
        after['intake_periods'][PERIOD]['failure_disposition']=disposition(b['attempt06_receipt_sha256'])
        before_ledger=op.ledger_sha(c,after)
        c.execute('UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(after),op.CONTROL))
        op.require(op.ledger_sha(c)==before_ledger,'A06_DISPOSITION_EFFECTS')
        successor_guard(c,b,after);cleanup(c,members);c.execute('COMMIT')
    except BaseException:
        try:c.execute('ROLLBACK')
        except BaseException:pass
        raise
    return dict(status='COMMIT_ACKNOWLEDGED',phase='disposition',independent_readback_required=True)

def readback(c,b,phase):
    """Separate connection, genuinely read-only; no grant/revoke even temporarily."""
    op.validate_binding(b);op.require(phase in ('recovery','disposition'),'A06_READBACK_PHASE')
    c.execute('BEGIN READ ONLY')
    try:
        members=baseline(c,b);ctl=op.control(c);op.retained_cleanup(c,ctl);op.no_hazards(c,ctl)
        # Evidence table has no postgres table ACL. Use its existing owner-only reader.
        check_evidence(c)
        r=ctl.get('intake_periods',{}).get(PERIOD,{}).get('failed_runs',{}).get(RUN)
        op.require(type(r) is dict and op.json_equal(c,r,receipt(r.get('original_marker'))) and sha(r)==b['attempt06_receipt_sha256'],'A06_RECEIPT_BINDING')
        op.require('intake_run' not in ctl and op.stop_snapshot(ctl)==(STOP7 if phase=='recovery' else ACCEPTED),'A06_STOP_DRIFT')
        if phase=='disposition':op.require(ctl['intake_periods'][PERIOD].get('failure_disposition')==disposition(sha(r)),'A06_DISPOSITION')
        item=c.execute('SELECT state,phase,fence,owner,lease_until FROM public.ingestion_work_items WHERE key=%s',(KEY,)).fetchone()
        op.require(item==('SAFETY_BLOCKED','RECOVERED',2,None,None),'A06_RECOVERED_ITEM')
        op.require(c.execute('SELECT fence,phase,finished_at IS NOT NULL FROM public.ingestion_work_attempts WHERE work_key=%s',(KEY,)).fetchall()==[(1,'RECOVERED',True)],'A06_RECOVERED_ATTEMPT')
        op.require(c.execute("SELECT pg_has_role(current_user,'ingestion_recovery_operator','USAGE'),pg_has_role(current_user,'ingestion_recovery_operator','SET')").fetchone()==(False,False),'A06_PERMISSION_CLEANUP')
        return dict(status='COMMITTED_STATE_VERIFIED_READ_ONLY',phase=phase,receipt_sha256=sha(r),stop=op.stop_snapshot(ctl),retry=False)
    finally:c.execute('ROLLBACK')

def predecessor06(state,*,snapshot):
    """Reuse existing encrypted credentials only from the exact closed Attempt06 job."""
    op.require(type(state) is dict and state.get('period')==PERIOD and state.get('status')=='CLOSED' and state.get('job',{}).get('id')==JOB
        and state.get('binding',{}).get('period')==PERIOD and state['binding'].get('execution_binding')==BINDING
        and state.get('access',{}).get('state')=='DATABASE_CLOSURE_ACKNOWLEDGED'
        and state['access'].get('render',{}).get('state')=='RESTORATION_ACKNOWLEDGED'
        and state.get('closure_verification',{}).get('status')=='VERIFIED'
        and state.get('closure_verification',{}).get('authorities_closed') is True
        and state.get('closure_verification',{}).get('sessions')==0
        and state.get('final_service')==dict(suspended=True,configuration_equal=True,environment_equal=True)
        and state.get('stable_credentials',{}).get('version')=='STABLE_RESTRICTED_V1'
        and set(state['stable_credentials'].get('passwords',{}))==set(op.ROLES)
        and set(state['stable_credentials'].get('verifier_sha256',{}))==set(op.ROLES),'A06_PREDECESSOR_CLOSURE')
    return dict(period=PERIOD,job_id=JOB,snapshot=snapshot,state_sha256=sha(state),source_requests='UNKNOWN',manchester='NOT_ATTEMPTED',execution_identity=SUCCESSOR)

def configure_successor():
    from . import owner_pilot as pilot
    pilot.PERIOD=SUCCESSOR;pilot.PREDECESSOR=PERIOD
    pilot.OWNER_PERIOD=SUCCESSOR+'_owner';pilot.OWNER_RUN=hashlib.sha256(pilot.OWNER_PERIOD.encode()).hexdigest()[:32]

def binding_from_saved_state(db):
    """No fresh secret, copied credential, policy write or expiry extension."""
    from .owner_pilot import Journal,envelope
    prior=Journal(db,PERIOD);old=prior.load()
    predecessor06(old,snapshot=dict(ordinal=prior.ordinal,bytes=prior.ciphertext_bytes,sha256=prior.previous))
    with envelope(),db.connection() as c:
        c.execute('BEGIN READ ONLY')
        try:
            ctl=op.control(c)
            marker=ctl.get('intake_run')
            if not marker or marker.get('id')!=RUN:marker=ctl.get('intake_periods',{}).get(PERIOD,{}).get('failed_runs',{}).get(RUN,{}).get('original_marker')
            h=sha(receipt(marker))
        finally:c.execute('ROLLBACK')
    return dict(version='FINITE_INTAKE_OWNER_V1',period=SUCCESSOR,route='POOLER',hostaddr=db.address,owner_hostaddr=db.address,
        execution_binding=op.reviewed_application_binding(),evidence_backend='POSTGRES_PILOT_V1',fixed_window={'start':'2026-10-27','end':'2026-11-02'},accepted_stop=ACCEPTED,
        attempt06_receipt_sha256=h,credential_policy='STABLE_RESTRICTED_V1',credential_verifier_sha256=old['stable_credentials']['verifier_sha256'])
