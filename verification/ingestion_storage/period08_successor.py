"""Exact consumed07 -> unused08 owner continuation; no replay or generic recovery."""
import copy
import hashlib
import json
from . import attempt06_recovery as a06, period07_settlement as p07, intake_owner as op

SUCCESSOR='b-dbpilot-20261027-1102-08'
RECEIPT_SHA='b461d84c45aadbea3bab1960273cedcf55f75a19b967b5d71a205d587ba8fb44'
BINDING=dict(revision='3adb65d06d0492d3b8f9b798e49e3be20699b082',workflow_sha256='a111c858189389df02d3fa2360c5d5d31520c472e85402ed2eab12993d90f2c2',manifest_sha256='4cc667f3727fc1f27fc0b305a4186174fcc2590185d1b7bd9384932dd96ee5ad')
TREE='62b685ac7a2e826ad1f14bc4bb8ba98e42fe15eb'
BRANCH='prep/b-timing-pg17-current-20261103'
ACCEPTED=dict(p07.STOP9,global_stop=None,manual_stop=None)

def require(ok,code):op.require(ok,'P08_'+code)

def validate_binding(b):
    require(type(b) is dict and b.get('period')==SUCCESSOR and b.get('evidence_backend')=='POSTGRES_PILOT_V1'
        and b.get('execution_binding')==BINDING and b.get('period07_receipt_sha256')==RECEIPT_SHA
        and b.get('accepted_stop')==ACCEPTED and 'attempt06_receipt_sha256' not in b,'SUCCESSOR_BINDING')

def release(value):
    require(type(value) is dict and value.get('execution_binding')==BINDING and value.get('tree')==TREE and value.get('branch')==BRANCH,'RELEASE_BINDING')
    return value

def disposition():
    return dict(version='PERIOD07_DISPOSITION_V1',receipt_sha256=RECEIPT_SHA,successor=SUCCESSOR,
        execution_binding=BINDING,tree=TREE,branch=BRANCH,before=p07.STOP9,after=ACCEPTED)

def history(c,ctl):
    a06.history(c,ctl,disposed=True,expected_sha=p07.A06_RECEIPT_SHA)
    p07.evidence(c)
    r=p07.history(c,ctl);require(a06.sha(r)==RECEIPT_SHA,'RECEIPT_BINDING')
    p=ctl['intake_periods'][p07.PERIOD]
    require(p.get('execution_binding')==p07.BINDING and p.get('evidence_backend')=='POSTGRES_PILOT_V1'
        and p.get('fixed_window')=={'start':'2026-10-27','end':'2026-11-02'} and p.get('max_runs')==1
        and set(p.get('councils',{}))=={'tameside','manchester'} and p.get('days')=={'2026-11-02':{'tameside':p07.KEY}},'PERIOD_HISTORY')
    return r

def unused(c,ctl,*,journal):
    require(SUCCESSOR not in ctl.get('intake_periods',{}) and 'intake_run' not in ctl,'SUCCESSOR_USED')
    require(c.execute('SELECT count(*) FROM public.ingestion_work_items WHERE revision LIKE %s',(SUCCESSOR+'-%',)).fetchone()==(0,),'SUCCESSOR_USED')
    periods=[SUCCESSOR,SUCCESSOR+'_owner'] if journal else [SUCCESSOR]
    require(c.execute('SELECT count(*) FROM public.ingestion_run_evidence WHERE period=ANY(%s)',(periods,)).fetchone()==(0,),'SUCCESSOR_USED')

def namespace(c,*,migrated=None):
    from .database_evidence import ATTEMPT07_OWNER_SQL,ATTEMPT08_OWNER_SQL
    old=hashlib.sha256(ATTEMPT07_OWNER_SQL.split('$owner_state$',2)[1].encode()).hexdigest()
    new=hashlib.sha256(ATTEMPT08_OWNER_SQL.split('$owner_state$',2)[1].encode()).hexdigest()
    actual=c.execute("SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex') FROM pg_proc WHERE oid='public.ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure").fetchone()[0]
    require(actual in ({new} if migrated is True else {old} if migrated is False else {old,new}),'JOURNAL_NAMESPACE')
    return actual

def successor_guard(c,b,ctl,*,require_namespace=False):
    if b.get('period')!=SUCCESSOR:return
    validate_binding(b);history(c,ctl)
    if require_namespace:namespace(c,migrated=True)
    require(ctl['intake_periods'][p07.PERIOD].get('failure_disposition')==disposition(),'DISPOSITION')
    require(op.json_equal(c,op.stop_snapshot(ctl),ACCEPTED),'STOP_DRIFT')

def inspect(c,b):
    validate_binding(b);c.execute('BEGIN READ ONLY')
    try:
        ctl=op.control(c);p07.common(c,b,ctl);history(c,ctl);op.no_hazards(c,ctl)
        d=ctl['intake_periods'][p07.PERIOD].get('failure_disposition')
        if d is None:
            require(op.json_equal(c,op.stop_snapshot(ctl),p07.STOP9),'STOP_DRIFT');unused(c,ctl,journal=True)
            namespace(c,migrated=False);status='PRE_DISPOSITION_VERIFIED'
        else:
            successor_guard(c,b,ctl);namespace(c);unused(c,ctl,journal=False);status='DISPOSITION_COMMITTED_VERIFIED'
        return dict(status=status,period=SUCCESSOR,receipt_sha256=RECEIPT_SHA,stop=op.stop_snapshot(ctl),transaction='ROLLED_BACK',retry=False)
    finally:c.execute('ROLLBACK')

def dispose(c,b):
    validate_binding(b);op.validate_binding(b);op.begin(c)
    try:
        ctl=op.control(c);members=p07.common(c,b,ctl);namespace(c,migrated=False)
        ctl=a06.lock(c);history(c,ctl);unused(c,ctl,journal=True);op.no_hazards(c,ctl)
        require(op.json_equal(c,op.stop_snapshot(ctl),p07.STOP9),'STOP_DRIFT')
        require('failure_disposition' not in ctl['intake_periods'][p07.PERIOD],'ALREADY_DISPOSED')
        require(c.execute('SELECT name FROM public.ingestion_run_evidence WHERE period=%s AND run_id=%s ORDER BY name',(p07.PERIOD,p07.RUN)).fetchall()==[(n,) for n in sorted(p07.EVIDENCE)],'ARCHIVE_INVENTORY')
        after=copy.deepcopy(ctl);after.update(global_stop=None,manual_stop=None)
        after['intake_periods'][p07.PERIOD]['failure_disposition']=disposition()
        expected=op.ledger_sha(c,after)
        c.execute('UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=%s',(json.dumps(after),op.CONTROL))
        require(op.ledger_sha(c)==expected,'DISPOSITION_EFFECTS')
        successor_guard(c,b,after);a06.cleanup(c,members);c.execute('COMMIT')
    except BaseException:
        try:c.execute('ROLLBACK')
        except BaseException:pass
        raise
    return dict(status='COMMIT_ACKNOWLEDGED',independent_readback_required=True)

def configure():
    from . import owner_pilot as pilot
    pilot.PERIOD=SUCCESSOR;pilot.PREDECESSOR=p07.PERIOD
    pilot.OWNER_PERIOD=SUCCESSOR+'_owner';pilot.OWNER_RUN=hashlib.sha256(pilot.OWNER_PERIOD.encode()).hexdigest()[:32]

def predecessor(state,*,snapshot):
    require(snapshot.get('ordinal')==56 and snapshot.get('sha256')==p07.JOURNAL_SHA,'JOURNAL_BINDING')
    require(state.get('period')==p07.PERIOD and state.get('status')=='CLOSED' and state.get('job',{}).get('id')==p07.JOB
        and state.get('job_terminal',{}).get('status')=='failed' and state.get('binding',{}).get('execution_binding')==p07.BINDING,'PREDECESSOR_BINDING')
    require(state.get('closure_verification')==dict(status='VERIFIED',runtime_memberships=0,sessions=0,temporary_owner_absent=True,stable_verifiers='MATCH',suspended=True,configuration_equal=True,environment_equal=True,authorities_closed=True)
        and state.get('final_service')==dict(suspended=True,configuration_equal=True,environment_equal=True),'PREDECESSOR_CLOSURE')
    require(state.get('stable_credentials',{}).get('version')=='STABLE_RESTRICTED_V1'
        and set(state['stable_credentials'].get('passwords',{}))==set(op.ROLES)
        and set(state['stable_credentials'].get('verifier_sha256',{}))==set(op.ROLES),'PREDECESSOR_CREDENTIALS')
    return dict(period=p07.PERIOD,job_id=p07.JOB,snapshot=snapshot,state_sha256=a06.sha(state),
        receipt_sha256=RECEIPT_SHA,source_requests=3,request_count_status='COMPLETE',coverage='NOT_ESTABLISHED',manchester='NOT_ATTEMPTED',execution_identity=SUCCESSOR)

def binding_from_saved_state(db):
    from .owner_pilot import Journal
    import os
    release(json.loads(os.environ['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE']))
    prior=Journal(db,p07.PERIOD);old=prior.load()
    predecessor(old,snapshot=dict(ordinal=prior.ordinal,bytes=prior.ciphertext_bytes,sha256=prior.previous))
    return dict(version='FINITE_INTAKE_OWNER_V1',period=SUCCESSOR,route='POOLER',hostaddr=db.address,owner_hostaddr=db.address,
        execution_binding=BINDING,evidence_backend='POSTGRES_PILOT_V1',fixed_window={'start':'2026-10-27','end':'2026-11-02'},accepted_stop=ACCEPTED,
        period07_receipt_sha256=RECEIPT_SHA,credential_policy='STABLE_RESTRICTED_V1',credential_verifier_sha256=old['stable_credentials']['verifier_sha256'])
