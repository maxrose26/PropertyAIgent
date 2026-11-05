"""Fixed period-08 failed-run settlement candidate; no stop disposition or successor.

Reuses Attempt06 locking, owner privilege cleanup and abandoned-item SQL recovery.
No worker activation, evidence mutation, journal write or collection entry point.
"""
import copy
import hashlib
import json
import time
from . import attempt06_recovery as a06, intake_owner as op, period08_successor as predecessor

PERIOD='b-dbpilot-20261027-1102-08'
RUN='768e1bd059474281ae9dc5113db42a99'
JOB='job-dbmacl5g1s2s73civi60'
KEY='a22bac9985d0141d82a4adceaba2354eb3808280413bf7c3aad44d34de8515ad'
TAMESIDE='cfdd58f7cd0358819f4af28db7e09a74bf02ae34a1497d4f092102f9b23bfbc2'
AUTHORITY='INGESTION_CHAIN_MANCHESTER_CAPTURE_28383FD729DE'
BINDING=predecessor.BINDING
EVIDENCE={'capture-1/source.json':'4691339a26f8bd4e86ea6df92e6730bcd964304753fe2ce4760e69685a993fd3','capture-2/source.json':'d21c771f96138af731d05445b45e1a155c26d1306a7419a488c21feb559d3698','final/events-before-publication.json':'8fa7b51bbeb9a7f113b8b641908397e0c3e5509c699125e95826ffe4b271f2d3','final/result-before-publication.json':'03db3bcdfc8c3a4e2fdbc901bb1525c55d7932f9d878da3501af45826e6c7051'}
MARKER_SHA='0e3885f35230d37750cab20685b75962a614714bdec89717f0718fe8ce869347'
JOURNAL_SHA='6cd68c0f6fc43bfda8b884eb08ae9dc873e24e95ca10d4626d53da22af8d6d4f'
STOP10=dict(a06.STOP6,hard_stop_generation=10)
STOP11=dict(STOP10,hard_stop_generation=11,manual_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',last_hard_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP')
SCOPE=dict(kind='DISCOVERY_SCOPE',council='manchester',semantics='VALIDATED',start='2026-10-27',end='2026-11-02')


def require(ok,code):op.require(ok,'P08_SETTLEMENT_'+code)

def binding(db):
    from . import owner_pilot as pilot
    predecessor.configure()
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
    source=reports['capture-2/source.json'];final=reports['final/result-before-publication.json']
    require(source.get('requested_interval')==['2026-10-27','2026-11-02'] and source.get('date_semantics')=='VALIDATED' and source.get('failure')=='BROWSER_Error' and source.get('requests')==1 and source.get('responses')==0 and source.get('safety_failure') is True,'SOURCE_EVIDENCE')
    require(final.get('period')==PERIOD and final.get('run_id')==RUN and final.get('execution_binding')==BINDING and final.get('status')=='STOP_RECONCILE_NO_RETRY' and final.get('reason')=='SOURCE_SAFETY' and final.get('usage',{}).get('requests')==9 and final['usage'].get('requests_status')=='COMPLETE','FINAL_EVIDENCE')
    events=reports['final/events-before-publication.json']
    for council,count in [('tameside',8),('manchester',1)]:
        require([e['data']['metrics']['requests'] for e in events if e.get('event')=='source_closed' and e.get('data',{}).get('council')==council]==[count],'ACCOUNTING_EVIDENCE')

def all_other_work_sha(c):
    # Covers every other work item/attempt, including all accepted Tameside results.
    return c.execute("""SELECT encode(sha256(convert_to(jsonb_build_object(
      'items',(SELECT coalesce(jsonb_agg(to_jsonb(w) ORDER BY key),'[]') FROM ingestion_work_items w WHERE key<>ALL(%s)),
      'attempts',(SELECT coalesce(jsonb_agg(to_jsonb(a) ORDER BY work_key,fence),'[]') FROM ingestion_work_attempts a WHERE work_key<>%s)
      )::text,'UTF8')),'hex')""",([op.CONTROL,KEY],KEY)).fetchone()[0]

def protected_sha(c):
    # Receipt binds completed Tameside rows, not future unrelated registrations.
    return c.execute("""WITH protected AS (
      SELECT * FROM ingestion_work_items WHERE key=%s
       OR (task='SCREENING' AND dependencies::jsonb=jsonb_build_array(%s::text))
       OR (task='LISTING_METADATA' AND checkpoint::jsonb->'plan'->>'capture_key'=%s))
      SELECT encode(sha256(convert_to(jsonb_build_object(
       'items',(SELECT jsonb_agg(to_jsonb(w) ORDER BY key) FROM protected w),
       'attempts',(SELECT jsonb_agg(to_jsonb(a) ORDER BY work_key,fence) FROM ingestion_work_attempts a WHERE work_key IN (SELECT key FROM protected))
      )::text,'UTF8')),'hex')""",(TAMESIDE,TAMESIDE,TAMESIDE)).fetchone()[0]

def tameside(c):
    row=c.execute('SELECT state,phase,checkpoint::jsonb FROM ingestion_work_items WHERE key=%s',(TAMESIDE,)).fetchone()
    require(row is not None and row[:2]==('COMPLETE','FINISHED'),'TAMESIDE_CAPTURE')
    cp=row[2];archive=cp.get('durable_archive',{})
    require(cp.get('council')=='tameside' and len(cp.get('records',[]))==24 and archive.get('name')=='capture-1/source.json' and archive.get('sha256')==EVIDENCE['capture-1/source.json'] and archive.get('readback_verified') is True,'TAMESIDE_ARCHIVE')
    require(c.execute("SELECT count(*) FILTER(WHERE state='COMPLETE' AND phase='FINISHED'),count(*) FROM ingestion_work_items WHERE task='SCREENING' AND dependencies::jsonb=jsonb_build_array(%s::text)",(TAMESIDE,)).fetchone()==(24,24),'TAMESIDE_SCREENINGS')
    require(c.execute("SELECT count(*) FILTER(WHERE state='COMPLETE' AND phase='FINISHED'),count(*) FROM ingestion_work_items WHERE task='LISTING_METADATA' AND checkpoint::jsonb->'plan'->>'capture_key'=%s",(TAMESIDE,)).fetchone()==(5,5),'TAMESIDE_BATCHES')


def receipt(marker):
    require(a06.sha(marker)==MARKER_SHA,'MARKER_HASH')
    require(type(marker) is dict and marker.get('id')==RUN and marker.get('period')==PERIOD and marker.get('state')=='OPEN' and marker.get('day')=='2026-11-02' and marker.get('publication_path')==f'docs/design/ingestion-operational-execution-daily-intake/{PERIOD}/{RUN}/final/result-before-publication.json','MARKER')
    return dict(version='PERIOD08_FAILED_RECOVERY_V1',original_marker=copy.deepcopy(marker),period=PERIOD,run_id=RUN,job_id=JOB,execution_binding=BINDING,evidence=EVIDENCE,status='FAILED_RECONCILED',coverage='PARTIAL_TAMESIDE_ONLY',actual_requests=9,request_count_status='COMPLETE',tameside=dict(status='RETAINED_AND_SCREENED',requests=8,records=24,screenings=24,metadata_batches=5,capture_key=TAMESIDE),manchester=dict(status='COVERAGE_NOT_ESTABLISHED',requests=1,checkpoint=None,source_failure='BROWSER_Error',validation_failure='SOURCE_SAFETY',cause='UNKNOWN'),recovered_key=KEY,recovered_fence=2,source_or_write_replay_authorised=False,stop_before=STOP10,stop_after=STOP11)

def common(c,b,ctl):
    members=a06.baseline(c,b)
    owner=c.execute(op.OWNER_MEMBERS).fetchall()
    require(len(owner)==1 and owner[0][0]!='postgres' and owner[0][1:]==(True,False,False),'OWNER_ADMIN_ONLY')
    require(c.execute("SELECT NOT has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone()==(True,),'OWNER_SCHEMA_BASELINE')
    op.retained_cleanup(c,ctl)
    predecessor.history(c,ctl)
    require(op.json_equal(c,ctl['intake_periods'][predecessor.p07.PERIOD].get('failure_disposition'),predecessor.disposition()),'PRIOR_DISPOSITION')
    evidence(c);tameside(c)
    p=ctl.get('intake_periods',{}).get(PERIOD,{})
    require(p.get('execution_binding')==BINDING and p.get('evidence_backend')=='POSTGRES_PILOT_V1' and p.get('fixed_window')=={'start':'2026-10-27','end':'2026-11-02'} and p.get('max_runs')==1 and set(p.get('councils',{}))=={'tameside','manchester'} and p.get('days')=={'2026-11-02':{'tameside':TAMESIDE,'manchester':KEY}},'PERIOD')
    g=ctl.get('grants',{}).get(AUTHORITY,{})
    require(g.get('intake_run')==RUN and g.get('intake_period')==PERIOD and g.get('capture_key')==KEY and g.get('execution_binding')==BINDING and g.get('expires_at')==0,'AUTHORITY')
    require(not c.execute('SELECT pid FROM pg_stat_activity WHERE usename=ANY(%s)',(list(op.ROLES)+['ingestion_application_login','ingestion_recovery_login'],)).fetchall(),'SESSIONS')
    require(not any(type(g.get('expires_at')) not in (int,float) or g['expires_at']>time.time() for g in ctl.get('grants',{}).values()),'OTHER_AUTHORITY')
    require(c.execute("SELECT pg_has_role(current_user,'ingestion_recovery_operator','USAGE'),pg_has_role(current_user,'ingestion_recovery_operator','SET')").fetchone()==(False,False),'RECOVERY_PERMISSION')
    return members

def pending(c,ctl):
    require(op.stop_snapshot(ctl)==STOP10,'STOP_DRIFT')
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
    require(op.stop_snapshot(ctl)==STOP11 and 'intake_run' not in ctl,'SETTLED_CONTROL')
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
        op.enter_owner(c);want=copy.deepcopy(ctl);want.update(STOP11)
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
