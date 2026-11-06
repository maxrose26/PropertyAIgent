"""Exact settled09 -> Manchester-only10 owner continuation; no replay or generic recovery."""
import copy
import hashlib
import json
from . import attempt06_recovery as a06, period09_settlement as settlement, intake_owner as op

SUCCESSOR='b-dbpilot-20261027-1102-10'
RECEIPT_SHA='2549b1cde3f78f38b338a980003231ff8c9bc375de6720b40d05d4053afd0f1d'
# Exact scraper release; owner pin does not change its bound source files.
BINDING=dict(revision='3ac568376685f448a8fa353ac82e24862302786b',workflow_sha256='946258265cf2e7f346ef57b18c7a7bb5056600581cf51ba4b595459c12c367b9',manifest_sha256='65c6f54b7339bd2abe5fc337c1e82bd919c6385ecac2a00e80b642d22a7775da')
TREE='3c7d854691dca7f758ee222594c851f535d1fdad'
BRANCH='prep/b-timing-pg17-current-20261103'
ACCEPTED=dict(settlement.STOP13,global_stop=None,manual_stop=None)

def require(ok,code):op.require(ok,'P10_'+code)

def validate_binding(b):
    require(type(b) is dict and b.get('period')==SUCCESSOR and b.get('evidence_backend')=='POSTGRES_PILOT_V1'
        and b.get('execution_binding')==BINDING and b.get('period09_receipt_sha256')==RECEIPT_SHA
        and b.get('accepted_stop')==ACCEPTED and 'attempt06_receipt_sha256' not in b and 'period07_receipt_sha256' not in b and 'period08_receipt_sha256' not in b,'SUCCESSOR_BINDING')

def release(value):
    require(type(value) is dict and value.get('execution_binding')==BINDING and value.get('tree')==TREE and value.get('branch')==BRANCH,'RELEASE_BINDING')
    return value

def disposition():
    return dict(version='PERIOD09_DISPOSITION_V1',receipt_sha256=RECEIPT_SHA,successor=SUCCESSOR,
        execution_binding=BINDING,tree=TREE,branch=BRANCH,councils=['manchester'],before=settlement.STOP13,after=ACCEPTED)

def history(c,ctl):
    settlement.predecessor.history(c,ctl);settlement.evidence(c);settlement.tameside(c)
    r=settlement.history(c,ctl);require(a06.sha(r)==RECEIPT_SHA,'RECEIPT_BINDING')
    require(op.json_equal(c,ctl['intake_periods'][settlement.prior.PERIOD].get('failure_disposition'),settlement.predecessor.disposition()),'PRIOR_DISPOSITION')
    return r


def unused(c,ctl,*,journal):
    require(SUCCESSOR not in ctl.get('intake_periods',{}) and 'intake_run' not in ctl,'SUCCESSOR_USED')
    require(c.execute('SELECT count(*) FROM public.ingestion_work_items WHERE revision LIKE %s',(SUCCESSOR+'-%',)).fetchone()==(0,),'SUCCESSOR_USED')
    periods=[SUCCESSOR,SUCCESSOR+'_owner'] if journal else [SUCCESSOR]
    require(c.execute('SELECT count(*) FROM public.ingestion_run_evidence WHERE period=ANY(%s)',(periods,)).fetchone()==(0,),'SUCCESSOR_USED')

def namespace(c,*,migrated=None):
    from .database_evidence import ATTEMPT09_OWNER_SQL,ATTEMPT10_OWNER_SQL
    old=hashlib.sha256(ATTEMPT09_OWNER_SQL.split('$owner_state$',2)[1].encode()).hexdigest()
    new=hashlib.sha256(ATTEMPT10_OWNER_SQL.split('$owner_state$',2)[1].encode()).hexdigest()
    actual=c.execute("SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex') FROM pg_proc WHERE oid='public.ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure").fetchone()[0]
    require(actual in ({new} if migrated is True else {old} if migrated is False else {old,new}),'JOURNAL_NAMESPACE')
    row=c.execute("SELECT prosrc FROM pg_proc WHERE oid='public.ingestion_register_bolton_exception(jsonb)'::regprocedure").fetchone()
    expected=registration_sql().split('$register$',2)[1] if actual==new else settlement.predecessor.registration_sql().split('$register$',2)[1]
    require(row==(expected,),'REGISTRAR_BINDING')
    return actual

def successor_guard(c,b,ctl,*,require_namespace=False):
    if b.get('period')!=SUCCESSOR:return
    validate_binding(b);history(c,ctl)
    if require_namespace:namespace(c,migrated=True)
    require(ctl['intake_periods'][settlement.PERIOD].get('failure_disposition')==disposition(),'DISPOSITION')
    require(op.json_equal(c,op.stop_snapshot(ctl),ACCEPTED),'STOP_DRIFT')

def inspect(c,b):
    validate_binding(b);c.execute('BEGIN READ ONLY')
    try:
        ctl=op.control(c);settlement.common(c,b,ctl);history(c,ctl);op.no_hazards(c,ctl)
        d=ctl['intake_periods'][settlement.PERIOD].get('failure_disposition')
        if d is None:
            require(op.json_equal(c,op.stop_snapshot(ctl),settlement.STOP13),'STOP_DRIFT');unused(c,ctl,journal=True)
            namespace(c,migrated=False);status='PRE_DISPOSITION_VERIFIED'
        else:
            successor_guard(c,b,ctl);namespace(c);unused(c,ctl,journal=False);status='DISPOSITION_COMMITTED_VERIFIED'
        return dict(status=status,period=SUCCESSOR,receipt_sha256=RECEIPT_SHA,stop=op.stop_snapshot(ctl),transaction='ROLLED_BACK',retry=False)
    finally:c.execute('ROLLBACK')

def dispose(c,b):
    validate_binding(b);op.validate_binding(b);op.begin(c)
    try:
        ctl=op.control(c);members=settlement.common(c,b,ctl);namespace(c,migrated=False)
        ctl=a06.lock(c);history(c,ctl);unused(c,ctl,journal=True);op.no_hazards(c,ctl)
        require(op.json_equal(c,op.stop_snapshot(ctl),settlement.STOP13),'STOP_DRIFT')
        require('failure_disposition' not in ctl['intake_periods'][settlement.PERIOD],'ALREADY_DISPOSED')
        require(c.execute('SELECT name FROM public.ingestion_run_evidence WHERE period=%s AND run_id=%s ORDER BY name',(settlement.PERIOD,settlement.RUN)).fetchall()==[(n,) for n in sorted(settlement.EVIDENCE)],'ARCHIVE_INVENTORY')
        after=copy.deepcopy(ctl);after.update(global_stop=None,manual_stop=None)
        after['intake_periods'][settlement.PERIOD]['failure_disposition']=disposition()
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
    pilot.PERIOD=SUCCESSOR;pilot.PREDECESSOR=settlement.PERIOD
    pilot.OWNER_PERIOD=SUCCESSOR+'_owner';pilot.OWNER_RUN=hashlib.sha256(pilot.OWNER_PERIOD.encode()).hexdigest()[:32]

def predecessor(state,*,snapshot):
    require(snapshot.get('ordinal')==55 and snapshot.get('sha256')==settlement.JOURNAL_SHA,'JOURNAL_BINDING')
    require(state.get('period')==settlement.PERIOD and state.get('status')=='CLOSED' and state.get('job',{}).get('id')==settlement.JOB
        and state.get('job_terminal',{}).get('status')=='failed' and state.get('binding',{}).get('execution_binding')==settlement.BINDING,'PREDECESSOR_BINDING')
    require(state.get('closure_verification')==dict(status='VERIFIED',runtime_memberships=0,sessions=0,temporary_owner_absent=True,stable_verifiers='MATCH',suspended=True,configuration_equal=True,environment_equal=True,authorities_closed=True)
        and state.get('final_service')==dict(suspended=True,configuration_equal=True,environment_equal=True),'PREDECESSOR_CLOSURE')
    require(state.get('stable_credentials',{}).get('version')=='STABLE_RESTRICTED_V1'
        and set(state['stable_credentials'].get('passwords',{}))==set(op.ROLES)
        and set(state['stable_credentials'].get('verifier_sha256',{}))==set(op.ROLES),'PREDECESSOR_CREDENTIALS')
    return dict(period=settlement.PERIOD,job_id=settlement.JOB,snapshot=snapshot,state_sha256=a06.sha(state),
        receipt_sha256=RECEIPT_SHA,source_requests=None,request_count_status='UNKNOWN',coverage='NOT_ESTABLISHED',manchester='COVERAGE_NOT_ESTABLISHED',execution_identity=SUCCESSOR)

def binding_from_saved_state(db):
    from .owner_pilot import Journal
    import os
    release(json.loads(os.environ['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE']))
    prior=Journal(db,settlement.PERIOD);old=prior.load()
    predecessor(old,snapshot=dict(ordinal=prior.ordinal,bytes=prior.ciphertext_bytes,sha256=prior.previous))
    return dict(version='FINITE_INTAKE_OWNER_V1',period=SUCCESSOR,route='POOLER',hostaddr=db.address,owner_hostaddr=db.address,
        execution_binding=BINDING,evidence_backend='POSTGRES_PILOT_V1',fixed_window={'start':'2026-10-27','end':'2026-11-02'},accepted_stop=ACCEPTED,
        period09_receipt_sha256=RECEIPT_SHA,credential_policy='STABLE_RESTRICTED_V1',credential_verifier_sha256=old['stable_credentials']['verifier_sha256'])


def councils():
    from .intake_owner_operations import COUNCILS
    return {'manchester':COUNCILS['manchester']}


def registration_sql():
    """Retain period09 guard verbatim; add only exact receipt-bound period10."""
    source=settlement.predecessor.registration_sql()
    old="CASE WHEN a='b-dbpilot-20261027-1102-09' THEN"
    require(source.count(old)==1,'REGISTRATION_ANCHOR')
    source=source.replace(old,"CASE WHEN a IN ('b-dbpilot-20261027-1102-09','b-dbpilot-20261027-1102-10') THEN")
    anchor="   e:=e||jsonb_build_object('registered_at',t,'days','{}'::jsonb);"
    guard="""   IF a='b-dbpilot-20261027-1102-10' AND (
      ctl->>'hard_stop_generation' IS DISTINCT FROM '13'
      OR ctl->>'last_hard_stop' IS DISTINCT FROM 'ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP'
      OR ctl->'intake_periods'->'b-dbpilot-20261027-1102-09'->'failure_disposition'->>'successor' IS DISTINCT FROM a
      OR ctl->'intake_periods'->'b-dbpilot-20261027-1102-09'->'failure_disposition'->>'receipt_sha256' IS DISTINCT FROM '__RECEIPT__'
      OR ctl->'intake_periods'->'b-dbpilot-20261027-1102-09'->'failure_disposition'->'execution_binding' IS DISTINCT FROM e->'execution_binding'
      OR ctl->'intake_periods'->'b-dbpilot-20261027-1102-09'->'failure_disposition'->'councils' IS DISTINCT FROM '["manchester"]'::jsonb
     ) THEN RAISE EXCEPTION 'PERIOD10_RECEIPT_BOUND_DISPOSITION'; END IF;
""".replace('__RECEIPT__',RECEIPT_SHA)
    require(source.count(anchor)==1,'REGISTRATION_ANCHOR')
    return source.replace(anchor,guard+anchor)


def function_inventory():
    expected=op.Owner.daily_intake_inventory()
    body=registration_sql().split('$register$',2)[1]
    return dict(expected,ingestion_register_bolton_exception=body)
