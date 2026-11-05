"""Fixed period-07 failed-run settlement candidate; no stop disposition or successor.

Reuses Attempt06 locking, owner privilege cleanup and abandoned-item SQL recovery.
No worker activation, evidence mutation, journal write or collection entry point.
"""
import copy
import hashlib
import json
import time
from . import attempt06_recovery as a06, intake_owner as op

PERIOD='b-dbpilot-20261027-1102-07'
RUN='a3a3def1b87d411aa9b5754b4b168b12'
JOB='job-dbm7dqh42hec73dsgahg'
KEY='ef5afe887f3e5162212fc33f2cf4429d5cbb19cf11bede34e2d1156b09741bc5'
AUTHORITY='INGESTION_CHAIN_TAMESIDE_CAPTURE_C4DCC4619ADA'
BINDING=dict(revision='54700366bab5434a5cda30abc853e0dc6dcc5d33',workflow_sha256='e5289d43dbd05f2ffa051529c4feeb6aa32fb719c621de00df3638e077bf78e4',manifest_sha256='482e137a9a62fdd1007ee351845a4fc2c0825693dfc3472217c2ac8d4c3b74fc')
EVIDENCE={'capture-1/source.json':'08171942f8a8ddc5f125d3468f7df800eef7189d0a80cc92ebf0094bd8b3bdf8','final/events-before-publication.json':'4abd400c87f26ea09743ee355ec40c98ae3d157fb652012c796dcc94d8ae9e21','final/result-before-publication.json':'f1c1d65333ffee46af4c8c48c964ffcf5d3429cd10a5be653f63deac1565ac8b'}
MARKER_SHA='ba74765f7d35eb420a12f59e3ac8207d17778892108d3529ca8808324d6167fc'
JOURNAL_SHA='31e7d340047e37df0d0e4382374dce5ccc939b1eb819d1213f11e238fa69fdf2'
A06_RECEIPT_SHA='25470c04237b8cc167b4ceb6a10dc612601683108f27aebffab9ad61dd778b6e'
STOP8=dict(a06.STOP6,hard_stop_generation=8)
STOP9=dict(STOP8,hard_stop_generation=9,manual_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',last_hard_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP')

def require(ok,code):op.require(ok,'P07_'+code)

def binding(db):
    from . import owner_pilot as pilot
    a06.configure_successor()
    journal=pilot.Journal(db,PERIOD);s=journal.load()
    require(journal.previous==JOURNAL_SHA and journal.ordinal==56,'JOURNAL_BINDING')
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
    source=reports['capture-1/source.json'];final=reports['final/result-before-publication.json']
    require(source.get('council')=='tameside' and source.get('requested_interval')==['2026-10-27','2026-11-02'] and source.get('date_semantics')=='RECEIVED' and source.get('failure')=='CALIBRATION_NAVIGATION_AMBIGUOUS' and source.get('resource',{}).get('requests_attempted')==3,'SOURCE_EVIDENCE')
    require(final.get('period')==PERIOD and final.get('run_id')==RUN and final.get('execution_binding')==BINDING and final.get('status')=='STOP_RECONCILE_NO_RETRY' and final.get('reason')=='IDOX_PAGINATION_PROFILE_BINDING' and final.get('scopes')==[] and final.get('usage',{}).get('requests')==3 and final['usage'].get('requests_status')=='COMPLETE','FINAL_EVIDENCE')
    events=reports['final/events-before-publication.json']
    require(isinstance(events,list) and [e['data']['metrics']['requests'] for e in events if e.get('event')=='source_closed' and e.get('data',{}).get('council')=='tameside']==[3],'ACCOUNTING_EVIDENCE')

def receipt(marker):
    require(a06.sha(marker)==MARKER_SHA,'MARKER_HASH')
    require(type(marker) is dict and marker.get('id')==RUN and marker.get('period')==PERIOD and marker.get('state')=='OPEN' and marker.get('day')=='2026-11-02' and marker.get('publication_path')==f'docs/design/ingestion-operational-execution-daily-intake/{PERIOD}/{RUN}/final/result-before-publication.json','MARKER')
    return dict(version='PERIOD07_FAILED_RECOVERY_V1',original_marker=copy.deepcopy(marker),period=PERIOD,run_id=RUN,job_id=JOB,execution_binding=BINDING,evidence=EVIDENCE,status='FAILED_RECONCILED',coverage='NOT_ESTABLISHED',actual_requests=3,request_count_status='COMPLETE',source_failure='CALIBRATION_NAVIGATION_AMBIGUOUS',validation_failure='IDOX_PAGINATION_PROFILE_BINDING',exact_navigation_cause='UNPROVEN',manchester='NOT_ATTEMPTED',recovered_key=KEY,recovered_fence=2,source_or_write_replay_authorised=False,stop_before=STOP8,stop_after=STOP9)

def common(c,b,ctl):
    members=a06.baseline(c,b)
    owner=c.execute(op.OWNER_MEMBERS).fetchall()
    require(len(owner)==1 and owner[0][0]!='postgres' and owner[0][1:]==(True,False,False),'OWNER_ADMIN_ONLY')
    require(c.execute("SELECT NOT has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone()==(True,),'OWNER_SCHEMA_BASELINE')
    op.retained_cleanup(c,ctl)
    a06.history(c,ctl,disposed=True,expected_sha=A06_RECEIPT_SHA)
    evidence(c)
    p=ctl.get('intake_periods',{}).get(PERIOD,{})
    require(p.get('execution_binding')==BINDING and p.get('evidence_backend')=='POSTGRES_PILOT_V1' and p.get('fixed_window')=={'start':'2026-10-27','end':'2026-11-02'} and p.get('max_runs')==1 and set(p.get('councils',{}))=={'tameside','manchester'} and p.get('days')=={'2026-11-02':{'tameside':KEY}},'PERIOD')
    g=ctl.get('grants',{}).get(AUTHORITY,{})
    require(g.get('intake_run')==RUN and g.get('intake_period')==PERIOD and g.get('capture_key')==KEY and g.get('execution_binding')==BINDING and g.get('expires_at')==0,'AUTHORITY')
    require(not c.execute('SELECT pid FROM pg_stat_activity WHERE usename=ANY(%s)',(list(op.ROLES)+['ingestion_application_login','ingestion_recovery_login'],)).fetchall(),'SESSIONS')
    require(not any(type(g.get('expires_at')) not in (int,float) or g['expires_at']>time.time() for g in ctl.get('grants',{}).values()),'OTHER_AUTHORITY')
    require(c.execute("SELECT pg_has_role(current_user,'ingestion_recovery_operator','USAGE'),pg_has_role(current_user,'ingestion_recovery_operator','SET')").fetchone()==(False,False),'RECOVERY_PERMISSION')
    return members

def pending(c,ctl):
    require(op.stop_snapshot(ctl)==STOP8,'STOP_DRIFT')
    expected=receipt(ctl.get('intake_run'))
    require(not ctl['intake_periods'][PERIOD].get('failed_runs') and not ctl['intake_periods'][PERIOD].get('failure_disposition'),'PRIOR_SETTLEMENT')
    row=c.execute('SELECT authority,revision,state,phase,fence,attempt_count,checkpoint,lease_until<extract(epoch FROM clock_timestamp()),task,contract,subject::jsonb FROM public.ingestion_work_items WHERE key=%s',(KEY,)).fetchone()
    require(row==(AUTHORITY,PERIOD+'-2026-11-02-tameside','CLAIMED','SOURCE_INTENT',1,1,None,True,'DISCOVERY','tameside-screening-metadata-five-v1',a06.SCOPE),'ITEM')
    require(c.execute('SELECT fence,phase,finished_at,checkpoint,authority FROM public.ingestion_work_attempts WHERE work_key=%s',(KEY,)).fetchall()==[(1,'SOURCE_INTENT',None,None,AUTHORITY)],'ATTEMPT')
    require(c.execute("SELECT count(*) FROM public.ingestion_work_items WHERE key<>%s AND (phase IN ('SOURCE_INTENT','WRITE_INTENT') OR state='PERSISTENCE_UNCERTAIN' OR revision=%s OR authority=%s)",(KEY,PERIOD+'-2026-11-02-manchester',AUTHORITY)).fetchone()==(0,),'OTHER_WORK')
    role=c.execute("SELECT grantor::regrole::text,admin_option,inherit_option,set_option FROM pg_auth_members WHERE roleid='ingestion_recovery_operator'::regrole AND member=session_user::regrole").fetchall()
    require(len(role)==1 and role[0][0]!='postgres' and role[0][1:]==(True,False,False),'RECOVERY_ADMIN_ONLY')
    return expected

def settled(c,ctl):
    require(op.stop_snapshot(ctl)==STOP9 and 'intake_run' not in ctl,'SETTLED_CONTROL')
    r=ctl['intake_periods'][PERIOD].get('failed_runs',{}).get(RUN)
    require(type(r) is dict and op.json_equal(c,r,receipt(r.get('original_marker'))),'RECEIPT')
    require(c.execute('SELECT state,phase,fence,owner,lease_until,checkpoint,reason,next_action,outcome::jsonb FROM public.ingestion_work_items WHERE key=%s',(KEY,)).fetchone()==('SAFETY_BLOCKED','RECOVERED',2,None,None,None,'ABANDONED_SOURCE_INTENT','RECONCILE',{'outcome':'ABANDONED_SOURCE_INTENT','source_or_write_replay_authorised':False}),'RECOVERED_ITEM')
    require(c.execute('SELECT fence,phase,finished_at IS NOT NULL,checkpoint FROM public.ingestion_work_attempts WHERE work_key=%s',(KEY,)).fetchall()==[(1,'RECOVERED',True,None)],'RECOVERED_ATTEMPT')
    return r

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
        ctl=a06.lock(c);expected=pending(c,ctl)
        # Locks exclude a competing controller mutation; recheck evidence/history.
        evidence(c);a06.history(c,ctl,disposed=True,expected_sha=A06_RECEIPT_SHA)
        require(c.execute('SELECT name FROM public.ingestion_run_evidence WHERE period=%s AND run_id=%s ORDER BY name',(PERIOD,RUN)).fetchall()==[(n,) for n in sorted(EVIDENCE)],'ARCHIVE_INVENTORY')
        op.leave_owner(c)
        c.execute('GRANT ingestion_recovery_operator TO postgres WITH ADMIN FALSE,INHERIT TRUE,SET FALSE GRANTED BY postgres')
        c.execute('SELECT public.ingestion_recover_abandoned(%s,1,false)',(KEY,)).fetchone()
        c.execute('REVOKE ingestion_recovery_operator FROM postgres GRANTED BY postgres RESTRICT')
        op.enter_owner(c);want=copy.deepcopy(ctl);want.update(STOP9)
        require(op.json_equal(c,op.control(c),want),'RECOVERY_EFFECTS')
        want['intake_periods'][PERIOD]['failed_runs']={RUN:expected};del want['intake_run']
        c.execute('UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(want),op.CONTROL))
        settled(c,want);a06.history(c,want,disposed=True,expected_sha=A06_RECEIPT_SHA)
        a06.cleanup(c,members);c.execute('COMMIT')
    except BaseException:
        try:c.execute('ROLLBACK')
        except BaseException:pass
        raise
    return dict(status='COMMIT_ACKNOWLEDGED',receipt_sha256=a06.sha(expected),independent_readback_required=True)
