"""Fixed Bolton canary failed-run settlement candidate; no stop disposition or successor.

Reuses Attempt06 locking, owner privilege cleanup and abandoned-item SQL recovery.
No worker activation, evidence mutation, journal write or collection entry point.
"""
import copy
import hashlib
import json
import time
from . import attempt06_recovery as a06, intake_owner as op, intake_successor as predecessor, period08_settlement as prior

PERIOD='b-bolton-20261103-1105-01'
RUN='ee7cf0d9bc714f56951527b940937054'
JOB='job-dbmq5qutlv9c73bn1rm0'
KEY='d9d8d667eef5fb012c74cdd28f5c55c6b577f749e7dc69d9179a6c032853d252'
AUTHORITY='INGESTION_CHAIN_BOLTON_CAPTURE_34518B29848D'
BINDING=predecessor.BINDING
EVIDENCE={'capture-1/source.json':'1ec89c559c2716d47336dbaf4e2e8c05e8641d0357f1646ee7c40eaeecb4dd78','final/events-before-publication.json':'284d5e34700dab4728b898c0ef629cdc89dce887deb611963e75ebec9cb6ac04','final/result-before-publication.json':'c0278ddc6e90199beb53fb0cc3ffe705685c9836d60ef0167f35a1332a62f4d1'}
MARKER_SHA='1cc12dd9115573308aaaed83676c04260750aab9a8c4d8ad0694a9731cae1f02'
JOURNAL_SHA='a5ba6be74c47eea89bd5068111bf3bc65198c8b4fd54c5036394a2c512f55c52'
STOP14=dict(a06.STOP6,hard_stop_generation=14)
STOP15=dict(STOP14,hard_stop_generation=15,manual_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',last_hard_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP')
SCOPE=dict(kind='DISCOVERY_SCOPE',council='bolton',semantics='RECEIVED',start='2026-11-03',end='2026-11-05')


def require(ok,code):op.require(ok,'BOLTON_SETTLEMENT_'+code)

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
    require(final.get('period')==PERIOD and final.get('run_id')==RUN and final.get('execution_binding')==BINDING and final.get('status')=='STOP_RECONCILE_NO_RETRY' and final.get('reason')=='IDOX_WINDOW_BINDING_OR_COMPLETENESS' and final.get('usage',{}).get('requests')==4 and final['usage'].get('requests_status')=='COMPLETE' and final['usage'].get('requests_accounted')==4 and final.get('scopes')==[],'FINAL_EVIDENCE')
    audit=reports['capture-1/source.json']
    require(audit.get('council')=='bolton' and audit.get('date_semantics')=='RECEIVED' and audit.get('requested_interval')==['2026-11-03','2026-11-05'] and audit.get('enumeration_evidence')=='TOTAL_UNKNOWN' and audit.get('resource',{}).get('requests_attempted')==4,'SOURCE_EVIDENCE')
    events=reports['final/events-before-publication.json']
    require([e.get('event') for e in events]==['runtime_authentication','supported_registration','source_closed'],'EVENT_EVIDENCE')
    require(c.execute('SELECT name FROM public.ingestion_run_evidence WHERE period=%s AND run_id=%s ORDER BY name',(PERIOD,RUN)).fetchall()==[(n,) for n in sorted(EVIDENCE)],'ARCHIVE_INVENTORY')

def all_other_work_sha(c):
    # Covers every other work item/attempt, including all accepted Tameside results.
    return c.execute("""SELECT encode(sha256(convert_to(jsonb_build_object(
      'items',(SELECT coalesce(jsonb_agg(to_jsonb(w) ORDER BY key),'[]') FROM ingestion_work_items w WHERE key<>ALL(%s)),
      'attempts',(SELECT coalesce(jsonb_agg(to_jsonb(a) ORDER BY work_key,fence),'[]') FROM ingestion_work_attempts a WHERE work_key<>%s)
      )::text,'UTF8')),'hex')""",([op.CONTROL,KEY],KEY)).fetchone()[0]

# Preserve and validate the already accepted period08 work using its original verifier.
HISTORICAL_BOLTON='d1ff23c04af746a5219e7c109255db0310d2a006c732bcac4f66f126b0240545'
def protected_sha(c):
    roots=[prior.TAMESIDE,predecessor.CAPTURE,HISTORICAL_BOLTON]
    return c.execute("""SELECT encode(sha256(convert_to(coalesce(jsonb_agg(to_jsonb(w) ORDER BY key),'[]')::text,'UTF8')),'hex')
      FROM ingestion_work_items w WHERE key=ANY(%s) OR dependencies::jsonb ?| %s
      OR checkpoint::jsonb->'plan'->>'capture_key'=ANY(%s)""",(roots,roots,roots)).fetchone()[0]
tameside=prior.tameside

def receipt(marker):
    require(a06.sha(marker)==MARKER_SHA,'MARKER_HASH')
    require(type(marker) is dict and marker.get('id')==RUN and marker.get('period')==PERIOD and marker.get('state')=='OPEN' and marker.get('day')=='2026-11-05' and marker.get('publication_path')==f'docs/design/ingestion-operational-execution-daily-intake/{PERIOD}/{RUN}/final/result-before-publication.json','MARKER')
    return dict(version='BOLTON01_FAILED_RECOVERY_V1',original_marker=copy.deepcopy(marker),period=PERIOD,run_id=RUN,job_id=JOB,execution_binding=BINDING,evidence=EVIDENCE,status='FAILED_RECONCILED',coverage='UNKNOWN',actual_requests=4,request_count_status='COMPLETE',requests_accounted=4,tameside=dict(status='NOT_RECOLLECTED_PRIOR_PERIOD08_PRESERVED',period=prior.PERIOD,capture_key=prior.TAMESIDE,records=24),bolton=dict(status='COVERAGE_UNKNOWN',requests=4,checkpoint=None,validation_failure='IDOX_WINDOW_BINDING_OR_COMPLETENESS',cause='TOTAL_AND_TERMINAL_UNPROVEN'),recovered_key=KEY,recovered_fence=2,source_or_write_replay_authorised=False,stop_before=STOP14,stop_after=STOP15)

def common(c,b,ctl):
    members=a06.baseline(c,b)
    owner=c.execute(op.OWNER_MEMBERS).fetchall()
    require(len(owner)==1 and owner[0][0]!='postgres' and owner[0][1:]==(True,False,False),'OWNER_ADMIN_ONLY')
    require(c.execute("SELECT NOT has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone()==(True,),'OWNER_SCHEMA_BASELINE')
    op.retained_cleanup(c,ctl)
    predecessor.success(c,ctl)
    evidence(c);tameside(c)
    p=ctl.get('intake_periods',{}).get(PERIOD,{})
    require(p.get('execution_binding')==BINDING and p.get('evidence_backend')=='POSTGRES_PILOT_V1' and p.get('fixed_window')=={'start':'2026-11-03','end':'2026-11-05'} and p.get('max_runs')==1 and set(p.get('councils',{}))=={'bolton'} and p.get('days')=={'2026-11-05':{'bolton':KEY}},'PERIOD')
    g=ctl.get('grants',{}).get(AUTHORITY,{})
    require(g.get('intake_run')==RUN and g.get('intake_period')==PERIOD and g.get('capture_key')==KEY and g.get('execution_binding')==BINDING and g.get('expires_at')==0,'AUTHORITY')
    require(not c.execute('SELECT pid FROM pg_stat_activity WHERE usename=ANY(%s)',(list(op.ROLES)+['ingestion_application_login','ingestion_recovery_login'],)).fetchall(),'SESSIONS')
    require(not any(type(g.get('expires_at')) not in (int,float) or g['expires_at']>time.time() for g in ctl.get('grants',{}).values()),'OTHER_AUTHORITY')
    require(c.execute("SELECT pg_has_role(current_user,'ingestion_recovery_operator','USAGE'),pg_has_role(current_user,'ingestion_recovery_operator','SET')").fetchone()==(False,False),'RECOVERY_PERMISSION')
    return members

def pending(c,ctl):
    require(op.stop_snapshot(ctl)==STOP14,'STOP_DRIFT')
    expected=receipt(ctl.get('intake_run'));expected['protected_work_sha256']=protected_sha(c)
    require(not ctl['intake_periods'][PERIOD].get('failed_runs') and not ctl['intake_periods'][PERIOD].get('failure_disposition'),'PRIOR_SETTLEMENT')
    row=c.execute('SELECT authority,revision,state,phase,fence,attempt_count,checkpoint,lease_until<extract(epoch FROM clock_timestamp()),task,contract,subject::jsonb FROM public.ingestion_work_items WHERE key=%s',(KEY,)).fetchone()
    require(row==(AUTHORITY,PERIOD+'-2026-11-05-bolton','CLAIMED','SOURCE_INTENT',1,1,None,True,'DISCOVERY','bolton-received-intake-v1',SCOPE),'ITEM')
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
    require(op.stop_snapshot(ctl)==STOP15 and 'intake_run' not in ctl,'SETTLED_CONTROL')
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
        evidence(c);predecessor.success(c,ctl);tameside(c)
        require(c.execute('SELECT name FROM public.ingestion_run_evidence WHERE period=%s AND run_id=%s ORDER BY name',(PERIOD,RUN)).fetchall()==[(n,) for n in sorted(EVIDENCE)],'ARCHIVE_INVENTORY')
        op.leave_owner(c)
        c.execute('GRANT ingestion_recovery_operator TO postgres WITH ADMIN FALSE,INHERIT TRUE,SET FALSE GRANTED BY postgres')
        c.execute('SELECT public.ingestion_recover_abandoned(%s,1,false)',(KEY,)).fetchone()
        c.execute('REVOKE ingestion_recovery_operator FROM postgres GRANTED BY postgres RESTRICT')
        op.enter_owner(c);want=copy.deepcopy(ctl);want.update(STOP15)
        require(op.json_equal(c,op.control(c),want),'RECOVERY_EFFECTS')
        want['intake_periods'][PERIOD]['failed_runs']={RUN:expected};del want['intake_run']
        c.execute('UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(want),op.CONTROL))
        settled(c,want);predecessor.success(c,want);tameside(c)
        require(all_other_work_sha(c)==untouched,'UNRELATED_WORK_CHANGED')
        a06.cleanup(c,members);c.execute('COMMIT')
    except BaseException:
        try:c.execute('ROLLBACK')
        except BaseException:pass
        raise
    return dict(status='COMMIT_ACKNOWLEDGED',receipt_sha256=a06.sha(expected),independent_readback_required=True)
