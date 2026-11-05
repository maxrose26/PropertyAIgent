"""Fixed period-09 failed-run settlement candidate; no stop disposition or successor.

Reuses Attempt06 locking, owner privilege cleanup and abandoned-item SQL recovery.
No worker activation, evidence mutation, journal write or collection entry point.
"""
import copy
import hashlib
import json
import time
from . import attempt06_recovery as a06, intake_owner as op, period09_successor as predecessor, period08_settlement as prior

PERIOD='b-dbpilot-20261027-1102-09'
RUN='bc4a50f3e4f44262a41a1b4036c3392b'
JOB='job-dbmfo1t6e07s73c68ee0'
KEY='21330c060171f6f95286a8f31131bda00fa3c081a21ebfc0f418b10706e510e4'
AUTHORITY='INGESTION_CHAIN_MANCHESTER_CAPTURE_BD391719411D'
BINDING=predecessor.BINDING
EVIDENCE={'final/events-before-publication.json':'121be5065c3b29b23dc367661f04cd6f888c7ebb8f27b62966bc11670d3324ff','final/result-before-publication.json':'e423763cd0338d4c62839e07f263f5f61ecf353b68b1743760717bc286519725'}
MARKER_SHA='d5126cf9628f2365119fcb1ed73e19a301f2dec4fa74d35af8eda653d0e5f4cb'
JOURNAL_SHA='32f6a6cbc2419570dfce518afd40862ec6b3cb2913b40b32e97ef1cec2205d56'
STOP12=dict(a06.STOP6,hard_stop_generation=12)
STOP13=dict(STOP12,hard_stop_generation=13,manual_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',last_hard_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP')
SCOPE=dict(kind='DISCOVERY_SCOPE',council='manchester',semantics='VALIDATED',start='2026-10-27',end='2026-11-02')


def require(ok,code):op.require(ok,'P09_SETTLEMENT_'+code)

def binding(db):
    from . import owner_pilot as pilot
    predecessor.configure()
    journal=pilot.Journal(db,PERIOD);s=journal.load()
    require(journal.previous==JOURNAL_SHA and journal.ordinal==55,'JOURNAL_BINDING')
    require(s.get('period')==PERIOD and s.get('status')=='CLOSED' and s.get('job',{}).get('id')==JOB and s.get('job_terminal',{}).get('status')=='failed' and s.get('binding',{}).get('execution_binding')==BINDING,'EXECUTION_BINDING')
    require(s.get('closure_verification')==dict(status='VERIFIED',runtime_memberships=0,sessions=0,temporary_owner_absent=True,stable_verifiers='MATCH',suspended=True,configuration_equal=True,environment_equal=True,authorities_closed=True),'CLOSURE')
    require(s.get('final_service')==dict(suspended=True,configuration_equal=True,environment_equal=True),'RESTORATION')
    return dict(credential_policy='STABLE_RESTRICTED_V1',credential_verifier_sha256=s['stable_credentials']['verifier_sha256'])

def evidence(c):
    reports={}
    # Existing owner-only reader; never grant table access to read the evidence.
    for name,expected in EVIDENCE.items():
        raw=bytes(c.execute('SELECT public.ingestion_intake_evidence_read(%s,%s,%s)',(PERIOD,RUN,name)).fetchone()[0])
        require(hashlib.sha256(raw).hexdigest()==expected,'EVIDENCE_HASH');reports[name]=json.loads(raw)
    final=reports['final/result-before-publication.json']
    require(final.get('period')==PERIOD and final.get('run_id')==RUN and final.get('execution_binding')==BINDING and final.get('status')=='STOP_RECONCILE_NO_RETRY' and final.get('reason')=='SOURCE_OR_CLEANUP_UNCERTAIN_NO_REPLAY' and final.get('usage',{}).get('requests') is None and final['usage'].get('requests_status')=='UNKNOWN' and final['usage'].get('requests_accounted')==0 and final.get('scopes')==[],'FINAL_EVIDENCE')
    events=reports['final/events-before-publication.json']
    require([e.get('event') for e in events]==['runtime_authentication','supported_registration'],'EVENT_EVIDENCE')
    require(c.execute('SELECT name FROM public.ingestion_run_evidence WHERE period=%s AND run_id=%s ORDER BY name',(PERIOD,RUN)).fetchall()==[(n,) for n in sorted(EVIDENCE)],'ARCHIVE_INVENTORY')

def all_other_work_sha(c):
    # Covers every other work item/attempt, including all accepted Tameside results.
    return c.execute("""SELECT encode(sha256(convert_to(jsonb_build_object(
      'items',(SELECT coalesce(jsonb_agg(to_jsonb(w) ORDER BY key),'[]') FROM ingestion_work_items w WHERE key<>ALL(%s)),
      'attempts',(SELECT coalesce(jsonb_agg(to_jsonb(a) ORDER BY work_key,fence),'[]') FROM ingestion_work_attempts a WHERE work_key<>%s)
      )::text,'UTF8')),'hex')""",([op.CONTROL,KEY],KEY)).fetchone()[0]

# Preserve and validate the already accepted period08 work using its original verifier.
protected_sha=prior.protected_sha
tameside=prior.tameside

def receipt(marker):
    require(a06.sha(marker)==MARKER_SHA,'MARKER_HASH')
    require(type(marker) is dict and marker.get('id')==RUN and marker.get('period')==PERIOD and marker.get('state')=='OPEN' and marker.get('day')=='2026-11-02' and marker.get('publication_path')==f'docs/design/ingestion-operational-execution-daily-intake/{PERIOD}/{RUN}/final/result-before-publication.json','MARKER')
    return dict(version='PERIOD09_FAILED_RECOVERY_V1',original_marker=copy.deepcopy(marker),period=PERIOD,run_id=RUN,job_id=JOB,execution_binding=BINDING,evidence=EVIDENCE,status='FAILED_RECONCILED',coverage='NOT_ESTABLISHED',actual_requests=None,request_count_status='UNKNOWN',requests_accounted=0,tameside=dict(status='NOT_RECOLLECTED_PRIOR_PERIOD08_PRESERVED',period=prior.PERIOD,capture_key=prior.TAMESIDE,records=24),manchester=dict(status='COVERAGE_NOT_ESTABLISHED',requests=None,checkpoint=None,validation_failure='SOURCE_OR_CLEANUP_UNCERTAIN_NO_REPLAY',cause='UNKNOWN'),recovered_key=KEY,recovered_fence=2,source_or_write_replay_authorised=False,stop_before=STOP12,stop_after=STOP13)

def common(c,b,ctl):
    members=a06.baseline(c,b)
    owner=c.execute(op.OWNER_MEMBERS).fetchall()
    require(len(owner)==1 and owner[0][0]!='postgres' and owner[0][1:]==(True,False,False),'OWNER_ADMIN_ONLY')
    require(c.execute("SELECT NOT has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone()==(True,),'OWNER_SCHEMA_BASELINE')
    op.retained_cleanup(c,ctl)
    predecessor.history(c,ctl)
    require(op.json_equal(c,ctl['intake_periods'][prior.PERIOD].get('failure_disposition'),predecessor.disposition()),'PRIOR_DISPOSITION')
    evidence(c);tameside(c)
    p=ctl.get('intake_periods',{}).get(PERIOD,{})
    require(p.get('execution_binding')==BINDING and p.get('evidence_backend')=='POSTGRES_PILOT_V1' and p.get('fixed_window')=={'start':'2026-10-27','end':'2026-11-02'} and p.get('max_runs')==1 and set(p.get('councils',{}))=={'manchester'} and p.get('days')=={'2026-11-02':{'manchester':KEY}},'PERIOD')
    g=ctl.get('grants',{}).get(AUTHORITY,{})
    require(g.get('intake_run')==RUN and g.get('intake_period')==PERIOD and g.get('capture_key')==KEY and g.get('execution_binding')==BINDING and g.get('expires_at')==0,'AUTHORITY')
    require(not c.execute('SELECT pid FROM pg_stat_activity WHERE usename=ANY(%s)',(list(op.ROLES)+['ingestion_application_login','ingestion_recovery_login'],)).fetchall(),'SESSIONS')
    require(not any(type(g.get('expires_at')) not in (int,float) or g['expires_at']>time.time() for g in ctl.get('grants',{}).values()),'OTHER_AUTHORITY')
    require(c.execute("SELECT pg_has_role(current_user,'ingestion_recovery_operator','USAGE'),pg_has_role(current_user,'ingestion_recovery_operator','SET')").fetchone()==(False,False),'RECOVERY_PERMISSION')
    return members

def pending(c,ctl):
    require(op.stop_snapshot(ctl)==STOP12,'STOP_DRIFT')
    expected=receipt(ctl.get('intake_run'));expected['protected_work_sha256']=protected_sha(c)
    require(not ctl['intake_periods'][PERIOD].get('failed_runs') and not ctl['intake_periods'][PERIOD].get('failure_disposition'),'PRIOR_SETTLEMENT')
    row=c.execute('SELECT authority,revision,state,phase,fence,attempt_count,checkpoint,lease_until<extract(epoch FROM clock_timestamp()),task,contract,subject::jsonb FROM public.ingestion_work_items WHERE key=%s',(KEY,)).fetchone()
    require(row==(AUTHORITY,PERIOD+'-2026-11-02-manchester','CLAIMED','SOURCE_INTENT',1,1,None,True,'DISCOVERY','manchester-screening-metadata-v1',SCOPE),'ITEM')
    require(c.execute('SELECT fence,phase,finished_at,checkpoint,authority FROM public.ingestion_work_attempts WHERE work_key=%s',(KEY,)).fetchall()==[(1,'SOURCE_INTENT',None,None,AUTHORITY)],'ATTEMPT')
    require(c.execute("SELECT count(*) FROM public.ingestion_work_items WHERE key<>%s AND (phase IN ('SOURCE_INTENT','WRITE_INTENT') OR state='PERSISTENCE_UNCERTAIN' OR authority=%s)",(KEY,AUTHORITY)).fetchone()==(0,),'OTHER_WORK')
    role=c.execute("SELECT grantor::regrole::text,admin_option,inherit_option,set_option FROM pg_auth_members WHERE roleid='ingestion_recovery_operator'::regrole AND member=session_user::regrole").fetchall()
    require(len(role)==1 and role[0][0]!='postgres' and role[0][1:]==(True,False,False),'RECOVERY_ADMIN_ONLY')
    return expected

def history(c,ctl):
    # Historical receipt/item checks also remain valid after a reviewed disposition.
    r=ctl['intake_periods'][PERIOD].get('failed_runs',{}).get(RUN)
    require(type(r) is dict and op.json_equal(c,{k:v for k,v in r.items() if k!='protected_work_sha256'},receipt(r.get('original_marker'))) and r.get('protected_work_sha256')==protected_sha(c),'RECEIPT')
    require(c.execute('SELECT state,phase,fence,owner,lease_until,checkpoint,reason,next_action,outcome::jsonb FROM public.ingestion_work_items WHERE key=%s',(KEY,)).fetchone()==('SAFETY_BLOCKED','RECOVERED',2,None,None,None,'ABANDONED_SOURCE_INTENT','RECONCILE',{'outcome':'ABANDONED_SOURCE_INTENT','source_or_write_replay_authorised':False}),'RECOVERED_ITEM')
    require(c.execute('SELECT fence,phase,finished_at IS NOT NULL,checkpoint FROM public.ingestion_work_attempts WHERE work_key=%s',(KEY,)).fetchall()==[(1,'RECOVERED',True,None)],'RECOVERED_ATTEMPT')
    return r

def settled(c,ctl):
    require(op.stop_snapshot(ctl)==STOP13 and 'intake_run' not in ctl,'SETTLED_CONTROL')
    return history(c,ctl)

def inspect(c,b):
    c.execute('BEGIN READ ONLY')
    try:
        ctl=op.control(c);common(c,b,ctl)
        done=RUN in ctl['intake_periods'][PERIOD].get('failed_runs',{})
        r=settled(c,ctl) if done else pending(c,ctl)
        return dict(status='COMMITTED_STATE_VERIFIED_READ_ONLY' if done else 'READY_FOR_REVIEW_NOT_AUTHORISED',period=PERIOD,run_id=RUN,receipt_sha256=a06.sha(r),stop=op.stop_snapshot(ctl),retry=False,transaction='ROLLED_BACK')
    finally:c.execute('ROLLBACK')

def recover(c,b):
    """One transaction only. On any uncertain acknowledgement call inspect, never retry."""
    op.begin(c)
    try:
        ctl=op.control(c);members=common(c,b,ctl)
        ctl=a06.lock(c);expected=pending(c,ctl);untouched=all_other_work_sha(c)
        # Locks exclude a competing controller mutation; recheck evidence/history.
        evidence(c);predecessor.history(c,ctl);tameside(c)
        require(c.execute('SELECT name FROM public.ingestion_run_evidence WHERE period=%s AND run_id=%s ORDER BY name',(PERIOD,RUN)).fetchall()==[(n,) for n in sorted(EVIDENCE)],'ARCHIVE_INVENTORY')
        op.leave_owner(c)
        c.execute('GRANT ingestion_recovery_operator TO postgres WITH ADMIN FALSE,INHERIT TRUE,SET FALSE GRANTED BY postgres')
        c.execute('SELECT public.ingestion_recover_abandoned(%s,1,false)',(KEY,)).fetchone()
        c.execute('REVOKE ingestion_recovery_operator FROM postgres GRANTED BY postgres RESTRICT')
        op.enter_owner(c);want=copy.deepcopy(ctl);want.update(STOP13)
        require(op.json_equal(c,op.control(c),want),'RECOVERY_EFFECTS')
        want['intake_periods'][PERIOD]['failed_runs']={RUN:expected};del want['intake_run']
        c.execute('UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(want),op.CONTROL))
        settled(c,want);predecessor.history(c,want);tameside(c)
        require(all_other_work_sha(c)==untouched,'UNRELATED_WORK_CHANGED')
        a06.cleanup(c,members);c.execute('COMMIT')
    except BaseException:
        try:c.execute('ROLLBACK')
        except BaseException:pass
        raise
    return dict(status='COMMIT_ACKNOWLEDGED',receipt_sha256=a06.sha(expected),independent_readback_required=True)
