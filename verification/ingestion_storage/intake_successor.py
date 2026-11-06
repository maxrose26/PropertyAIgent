"""Success continuation on the existing owner lifecycle, selected by scope policy.

No stop disposition, recovery algorithm, new role or new evidence store.
"""
import copy, hashlib, json, os
from . import intake_owner as op, period10_successor as prior
from .intake_scope_policy import BOLTON, reviewed
from .database_evidence import canonical

SCOPE = BOLTON
PREDECESSOR = prior.SUCCESSOR
RUN = '6e0cb337843748f08bbfcec71d5e87fc'
JOB = 'job-dbmnmpjm8hqs73avo5j0'
JOURNAL_SHA = '433c2e912f6f5f7cad698d9245f2ba7fb12f4f72b8ff490b57c201c4259f74bb'
FINAL_SHA = 'f6cdf32b52a27285c49bb5fc38a829fa108f9bf4eb4cb01650e62ff6ff7a5b29'
CAPTURE = '5399b97ac4f03fe6d4d9051c89602d5ce959f0e087f53d883f371b286f214f10'
CAPTURE_SHA = 'bf62b953e98360ab327044e73aef54769f5dc5dccd6e5610068afc707f701af4'
SOURCE_SHA = '9aae860861680ef0bdf3317277b005d87dbfccf8c90dd7e0474c681391bcc09f'
ACCEPTED = prior.ACCEPTED
BRANCH = prior.BRANCH
# Owner pin; the sealed scraper keeps identical scope SQL and runtime files.
BINDING = dict(revision='d497758212a6e73ed5f77632167ddd4033133607', workflow_sha256='946258265cf2e7f346ef57b18c7a7bb5056600581cf51ba4b595459c12c367b9', manifest_sha256='cb1aa1b01cbd5ff17d1b4a17f369046c1116b3d14edb80cc530745624196dd9f')
TREE = '2c14b68b2ba6d98ffb9cf170db2277bd9fada2e9'

def require(ok, code): op.require(ok, 'SCOPE_'+code)
def sha(value): return hashlib.sha256(canonical(value)).hexdigest()

def release(value):
    require(BINDING['revision'] != '0'*40 and value.get('execution_binding') == BINDING
        and value.get('tree') == TREE and value.get('branch') == BRANCH, 'RELEASE_BINDING')
    return value

def validate_binding(b):
    require(b.get('period') == SCOPE.period and b.get('scope_policy_sha256') == SCOPE.fingerprint()
        and b.get('execution_binding') == BINDING and b.get('fixed_window') == SCOPE.window()
        and b.get('accepted_stop') == ACCEPTED and b.get('evidence_backend') == 'POSTGRES_PILOT_V1'
        and not any(k in b for k in ('attempt06_receipt_sha256','period07_receipt_sha256','period08_receipt_sha256','period09_receipt_sha256')), 'BINDING')

def success(c, ctl):
    prior.history(c, ctl)
    marker = ctl.get('intake_periods', {}).get(PREDECESSOR, {}).get('verified_run') or ctl.get('intake_run', {})
    require(marker.get('id') == RUN and marker.get('period') == PREDECESSOR and marker.get('state') == 'VERIFIED'
        and marker.get('status') == 'RETAINED_AND_SCREENED', 'PREDECESSOR_MARKER')
    body = c.execute('SELECT body,sha256 FROM public.ingestion_run_evidence WHERE period=%s AND run_id=%s AND name=%s',
        (PREDECESSOR,RUN,'final/result-before-publication.json')).fetchone()
    require(body and body[1] == FINAL_SHA and hashlib.sha256(bytes(body[0])).hexdigest() == FINAL_SHA, 'PREDECESSOR_EVIDENCE')
    row=c.execute("SELECT state,checkpoint::jsonb FROM public.ingestion_work_items WHERE key=%s",(CAPTURE,)).fetchone()
    require(row and row[0]=='COMPLETE' and sha(row[1])==CAPTURE_SHA and row[1].get('source_sha256')==SOURCE_SHA
        and len(row[1].get('records',[]))==35, 'PREDECESSOR_CAPTURE')
    from .chain_registration import _screen_items, completed_screening, Registration
    from .scope_binding import binding_for
    from app.ingestion.listing_screening import ScreeningRule,RULE_V3
    root=c.execute('SELECT to_jsonb(w) FROM public.ingestion_work_items w WHERE key=%s',(CAPTURE,)).fetchone()[0]
    batches,screens=_screen_items(binding_for('manchester'),root,row[1],ScreeningRule(RULE_V3,unit_threshold=10,link_related=False),root['limits'],capture_bound=True)
    keys=[x['key'] for x in [*batches,*screens.values()]]
    rows=[r[0] for r in c.execute('SELECT to_jsonb(w) FROM public.ingestion_work_items w WHERE key=ANY(%s)',(keys,)).fetchall()]
    require(len(batches)==7 and len(screens)==35,'PREDECESSOR_SCREENING')
    completed_screening(Registration('SCREENING','',[],[],{}, {},CAPTURE,batches=batches,screens=screens),row[1],ScreeningRule(RULE_V3,unit_threshold=10,link_related=False),rows)
    return marker

def guard(c,b,ctl,*,require_namespace=False):
    if not reviewed(b.get('period')): return
    validate_binding(b);success(c,ctl)
    require(op.json_equal(c,op.stop_snapshot(ctl),ACCEPTED),'STOP_DRIFT')
    if require_namespace: namespace(c, migrated=True)

def unused(c,ctl,*,journal=True):
    require(SCOPE.period not in ctl.get('intake_periods',{}),'PERIOD_USED')
    require(c.execute('SELECT count(*) FROM public.ingestion_work_items WHERE revision LIKE %s',(SCOPE.period+'-%',)).fetchone()==(0,),'PERIOD_USED')
    periods=[SCOPE.period,SCOPE.period+'_owner'] if journal else [SCOPE.period]
    require(c.execute('SELECT count(*) FROM public.ingestion_run_evidence WHERE period=ANY(%s)',(periods,)).fetchone()==(0,),'PERIOD_USED')

def owner_sql():
    from .database_evidence import ATTEMPT10_OWNER_SQL
    return ATTEMPT10_OWNER_SQL.replace("'"+PREDECESSOR+"_owner'", "'"+PREDECESSOR+"_owner','"+SCOPE.period+"_owner'")

def registration_sql():
    source=prior.registration_sql()
    def replace(old,new):
        nonlocal source
        require(source.count(old)==1,'REGISTRATION_ANCHOR');source=source.replace(old,new)
    lit=lambda value: "'"+json.dumps(value,sort_keys=True).replace("'","''")+"'::jsonb"
    exact="a='"+SCOPE.period+"'"
    replace("OR (e->'councils')-ARRAY['tameside','manchester']<>'{}'::jsonb",
        "OR (CASE WHEN "+exact+" THEN e->'councils' IS DISTINCT FROM "+lit(SCOPE.councils())+" ELSE (e->'councils')-ARRAY['tameside','manchester']<>'{}'::jsonb END)")
    replace("CASE WHEN a IN ('b-dbpilot-20261027-1102-09','b-dbpilot-20261027-1102-10') THEN",
        "CASE WHEN "+exact+" THEN e->'councils' IS DISTINCT FROM "+lit(SCOPE.councils())+" WHEN a IN ('b-dbpilot-20261027-1102-09','b-dbpilot-20261027-1102-10') THEN")
    replace("OR e->'fixed_window' IS DISTINCT FROM '{\"start\":\"2026-10-27\",\"end\":\"2026-11-02\"}'::jsonb",
        "OR e->'fixed_window' IS DISTINCT FROM (CASE WHEN "+exact+" THEN "+lit(SCOPE.window())+" ELSE '{\"start\":\"2026-10-27\",\"end\":\"2026-11-02\"}'::jsonb END)")
    anchor="   e:=e||jsonb_build_object('registered_at',t,'days','{}'::jsonb);"
    checks="""   IF __EXACT__ THEN
    IF e->'expected_stop' IS DISTINCT FROM __STOP__
     OR ctl->'intake_run'->>'id' IS DISTINCT FROM '__RUN__'
     OR ctl->'intake_run'->>'period' IS DISTINCT FROM '__PRIOR__'
     OR ctl->'intake_run'->>'state' IS DISTINCT FROM 'VERIFIED'
     OR ctl->'intake_run'->>'status' IS DISTINCT FROM 'RETAINED_AND_SCREENED'
     OR ctl->'intake_run'->'publication'->>'sha256' IS DISTINCT FROM '__FINAL__'
     OR ctl->'intake_periods'->'__PRIOR__' ? 'verified_run'
    THEN RAISE EXCEPTION 'SCOPE_SUCCESS_PREDECESSOR'; END IF;
    ctl:=jsonb_set(ctl,ARRAY['intake_periods','__PRIOR__','verified_run'],ctl->'intake_run');
   END IF;
""".replace('__EXACT__',exact).replace('__BINDING__',lit(BINDING)).replace('__STOP__',lit(ACCEPTED)).replace('__RUN__',RUN).replace('__PRIOR__',PREDECESSOR).replace('__FINAL__',FINAL_SHA)
    replace(anchor,checks+anchor)
    # Preserve all finish checks; admit the same exact Bolton audit identity
    # already required at the evidence write boundary.
    replace("AND w.subject::jsonb->>'council'='tameside') OR (w.subject::jsonb->>'council'='manchester'",
        "AND (w.subject::jsonb->>'council'='tameside' OR ("+exact+
        " AND w.subject::jsonb->>'council'='bolton' AND w.subject::jsonb->>'semantics'='RECEIVED'"
        " AND (convert_from(d.body,'UTF8')::jsonb)->>'date_semantics'='RECEIVED'"
        " AND e->'fixed_window'="+lit(SCOPE.window())+"))) OR (w.subject::jsonb->>'council'='manchester'")
    return source

def evidence_write_sql():
    from .database_evidence import WRITE_SQL
    anchor="OR (w.subject::jsonb->>'council'='manchester'"
    require(WRITE_SQL.count(anchor)==1,'EVIDENCE_ANCHOR')
    clause=("OR (p_period='"+SCOPE.period+"' AND policy->'fixed_window'="
        "'"+json.dumps(SCOPE.window(),sort_keys=True)+"'::jsonb"
        " AND w.subject::jsonb->>'council'='bolton'"
        " AND w.subject::jsonb->>'semantics'='RECEIVED'"
        " AND (convert_from(p_body,'UTF8')::jsonb)->>'council'='bolton'"
        " AND (convert_from(p_body,'UTF8')::jsonb)->>'date_semantics'='RECEIVED')\n ")
    return WRITE_SQL.replace(anchor,clause+anchor)


def function_inventory():
    return dict(op.Owner.daily_intake_inventory(), ingestion_register_bolton_exception=registration_sql().split('$register$',2)[1])

def namespace(c,*,migrated=None):
    from .database_evidence import ATTEMPT10_OWNER_SQL
    current=c.execute("SELECT prosrc FROM pg_proc WHERE oid='public.ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure").fetchone()[0]
    old,new=ATTEMPT10_OWNER_SQL.split('$owner_state$',2)[1],owner_sql().split('$owner_state$',2)[1]
    require(current in ([new] if migrated is True else [old] if migrated is False else [old,new]),'NAMESPACE')
    from .database_evidence import WRITE_SQL
    writer=evidence_write_sql() if current==new else WRITE_SQL
    require(c.execute("SELECT prosrc FROM pg_proc WHERE oid='public.ingestion_intake_evidence_write(text,text,text,bytea)'::regprocedure").fetchone()==(writer.split('$evidence_write$',2)[1],),'EVIDENCE_WRITER')
    expected=registration_sql() if current==new else prior.registration_sql()
    require(c.execute("SELECT prosrc FROM pg_proc WHERE oid='public.ingestion_register_bolton_exception(jsonb)'::regprocedure").fetchone()==(expected.split('$register$',2)[1],),'REGISTRAR')

def inspect(c,b):
    validate_binding(b);c.execute('BEGIN READ ONLY')
    try:
        op.identity(c);op.inventory(c);op.owner_absent(c)
        op.dormant(c,stable_verifiers=b['credential_verifier_sha256'])
        ctl=op.control(c);guard(c,b,ctl);op.no_hazards(c,ctl);op.retained_cleanup(c,ctl);namespace(c)
        if SCOPE.period not in ctl.get('intake_periods',{}):
            unused(c,ctl,journal=False);status='UNUSED_SUCCESSOR_VERIFIED'
        else:status='REGISTERED_READBACK_NO_RETRY'
        return dict(status=status,period=SCOPE.period,scope_policy_sha256=SCOPE.fingerprint(),stop=op.stop_snapshot(ctl),transaction='ROLLED_BACK')
    finally:c.execute('ROLLBACK')

def predecessor(state,*,snapshot):
    require(snapshot.get('ordinal')==55 and snapshot.get('sha256')==JOURNAL_SHA,'JOURNAL_BINDING')
    require(state.get('period')==PREDECESSOR and state.get('status')=='CLOSED'
        and state.get('job',{}).get('id')==JOB and state.get('job_terminal',{}).get('status')=='succeeded'
        and state.get('binding',{}).get('execution_binding')==prior.BINDING,'PREDECESSOR_BINDING')
    require(state.get('closure_verification')==dict(status='VERIFIED',runtime_memberships=0,sessions=0,temporary_owner_absent=True,stable_verifiers='MATCH',suspended=True,configuration_equal=True,environment_equal=True,authorities_closed=True)
        and state.get('final_service')==dict(suspended=True,configuration_equal=True,environment_equal=True),'PREDECESSOR_CLOSURE')
    require(state.get('stable_credentials',{}).get('version')=='STABLE_RESTRICTED_V1'
        and set(state['stable_credentials'].get('passwords',{}))==set(op.ROLES)
        and set(state['stable_credentials'].get('verifier_sha256',{}))==set(op.ROLES),'PREDECESSOR_CREDENTIALS')
    return dict(period=PREDECESSOR,job_id=JOB,snapshot=snapshot,state_sha256=sha(state),execution_identity=SCOPE.period,coverage='VERIFIED',source_requests=34)

def configure():
    from . import owner_pilot as p
    p.PERIOD=SCOPE.period;p.PREDECESSOR=PREDECESSOR;p.WINDOW=SCOPE.window()
    p.OWNER_PERIOD=SCOPE.period+'_owner';p.OWNER_RUN=hashlib.sha256(p.OWNER_PERIOD.encode()).hexdigest()[:32]

def binding_from_saved_state(db):
    from .owner_pilot import Journal
    release(json.loads(os.environ['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE']))
    journal=Journal(db,PREDECESSOR);state=journal.load()
    predecessor(state,snapshot=dict(ordinal=journal.ordinal,bytes=journal.ciphertext_bytes,sha256=journal.previous))
    return dict(version='FINITE_INTAKE_OWNER_V1',period=SCOPE.period,route='POOLER',hostaddr=db.address,owner_hostaddr=db.address,
        execution_binding=BINDING,evidence_backend='POSTGRES_PILOT_V1',fixed_window=SCOPE.window(),accepted_stop=ACCEPTED,
        scope_policy_sha256=SCOPE.fingerprint(),credential_policy='STABLE_RESTRICTED_V1',credential_verifier_sha256=state['stable_credentials']['verifier_sha256'])
