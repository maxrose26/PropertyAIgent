"""Exact closed-qualification continuation; no replay, scheduler or new store."""
import hashlib
from . import intake_owner as op
from .database_evidence import OWNER_SQL,canonical,verify_inventory

def predecessor04(state, *, snapshot):
    op.require(snapshot=={'ordinal':46,'bytes':29084,'sha256':'313352066984874f46af4f9cb767caab2cc17d220ac9d694127fee3b8bd51631'}
        and type(state) is dict and state.get('period')=='b-dbpilot-20261027-1102-04' and state.get('status')=='CLOSED'
        and state.get('pipeline_status','NOT_RUN')=='NOT_RUN' and not state.get('job') and 'ONE_JOB' not in state.get('intents',{})
        and state.get('deployment')=='dep-dblhmq3m8hqs739auu5g'
        and state.get('binding',{}).get('execution_binding',{}).get('revision')=='938f3f18d8b75c6467290461139b03bf9b95a338'
        and state.get('access',{}).get('state')=='DATABASE_CLOSURE_ACKNOWLEDGED'
        and state['access'].get('render',{}).get('state')=='RESTORATION_ACKNOWLEDGED'
        and hashlib.sha256(canonical(state.get('closure_receipt'))).hexdigest()=='c8eaff0e5ebce43e8be31ebd092b17161cf321024a8ec686a8dafcdfd7d23f3c'
        and state.get('final_service')==dict(suspended=True,configuration_equal=True,environment_equal=True)
        and state.get('stable_credentials',{}).get('version')=='STABLE_RESTRICTED_V1'
        and set(state['stable_credentials'].get('passwords',{}))==set(op.ROLES)
        and set(state['stable_credentials'].get('verifier_sha256',{}))==set(op.ROLES)
        and state.get('runtime_qualification') is None and state.get('source_result') is None and state.get('independent_result') is None
        and all(state.get('intents',{}).get(k,{}).get('state')=='ACKNOWLEDGED' for k in ('PERIOD','ACTIVATE','HANDOFF')),
        'OWNER_CONTINUATION_PREDECESSOR')
    return {'period':state['period'],'state_sha256':hashlib.sha256(canonical(state)).hexdigest(),
        'closure_sha256':hashlib.sha256(canonical(state['closure_receipt'])).hexdigest(),
        'snapshot':snapshot,'source_requests':'NOT_REACHED_NO_INTAKE_JOB',
        'closure_evidence_sha256':'0547e7ba14ae750fcc002de9454f4c162bccf01e757ee2e288f2935088918790',
        'execution_identity':'b-dbpilot-20261027-1102-05'}

def predecessor(state, *, snapshot):
    op.require(type(snapshot) is dict and snapshot.get('ordinal')==54 and
        snapshot.get('sha256')=='1db4809eeaaddb353244542ccd7a021cb34b8af8eccc3702a0c735731d9be01e' and
        type(snapshot.get('bytes')) is int and 0<snapshot['bytes']<=32768 and
        type(state) is dict and state.get('period')=='b-dbpilot-20261027-1102-05' and state.get('status')=='CLOSED' and
        state.get('job',{}).get('id')=='job-dblke3bm8hqs739hgmmg' and
        state.get('access',{}).get('state')=='DATABASE_CLOSURE_ACKNOWLEDGED' and
        state['access'].get('render',{}).get('state')=='RESTORATION_ACKNOWLEDGED' and
        state.get('closure_verification')==dict(status='VERIFIED',authorities_closed=True,configuration_equal=True,environment_equal=True,runtime_memberships=0,sessions=0,stable_verifiers='MATCH',suspended=True,temporary_owner_absent=True) and
        state.get('closure_receipt',{}).get('outcome')=='COMMIT_ACKNOWLEDGED' and not state['closure_receipt'].get('open_run_requires_reconciliation',True) and
        state.get('final_service')==dict(suspended=True,configuration_equal=True,environment_equal=True) and
        state.get('stable_credentials',{}).get('version')=='STABLE_RESTRICTED_V1' and
        set(state['stable_credentials'].get('passwords',{}))==set(op.ROLES) and
        set(state['stable_credentials'].get('verifier_sha256',{}))==set(op.ROLES),'OWNER_CONTINUATION_PREDECESSOR')
    return dict(period=state['period'],state_sha256=hashlib.sha256(canonical(state)).hexdigest(),
        closure_sha256=hashlib.sha256(canonical(state['closure_receipt'])).hexdigest(),snapshot=snapshot,
        execution_identity='b-dbpilot-20261027-1102-06',source_requests='ZERO_VERIFIED_JOB_RECEIPT',
        job_id='job-dblke3bm8hqs739hgmmg')

def diagnostic02_closed(state, *, snapshot, stable_credentials):
    op.require(snapshot==dict(ordinal=44,bytes=14280,sha256='4f9f08eed67e11420b5df197be90340973ced669afb840e98f1977ba3cc6dc96') and
        state.get('period')=='b-qualification-20261104-02' and state.get('status')=='CLOSED' and
        state.get('job',{}).get('id')=='job-dblphcp5efls73adq1h0' and
        state.get('closure_verification',{}).get('status')=='VERIFIED' and
        state.get('final_service')==dict(suspended=True,configuration_equal=True,environment_equal=True) and
        state.get('runtime_qualification',{}).get('source_requests')==0 and
        state.get('stable_credentials')==stable_credentials,'OWNER_CONTINUATION_PREDECESSOR')
    return dict(period=state['period'],snapshot=snapshot,closure_sha256=hashlib.sha256(canonical(state['closure_receipt'])).hexdigest())

def migrate_owner_namespace(c, *, stable_verifiers=None, qualification=False,deadline=False,diagnostic_cap=False,attempt06=False,attempt07=False,attempt08=False,binding08=None,attempt09=False,binding09=None,attempt10=False,binding10=None):
    """Exact04→05 namespace addition; unchanged ACL, ledger and evidence."""
    new=OWNER_SQL.split('$owner_state$',2)[1]
    old=new.replace(",'b-dbpilot-20261027-1102-05_owner'",'')
    if qualification:
        from .database_evidence import QUALIFICATION_OWNER_SQL
        old=new;new=QUALIFICATION_OWNER_SQL.split('$owner_state$',2)[1]
    if deadline:
        from .database_evidence import QUALIFICATION_OWNER_SQL,DEADLINE_OWNER_SQL
        old=QUALIFICATION_OWNER_SQL.split('$owner_state$',2)[1];new=DEADLINE_OWNER_SQL.split('$owner_state$',2)[1]
    if diagnostic_cap:
        from .database_evidence import DEADLINE_OWNER_SQL,DIAGNOSTIC02_CAP_OWNER_SQL
        old=DEADLINE_OWNER_SQL.split('$owner_state$',2)[1];new=DIAGNOSTIC02_CAP_OWNER_SQL.split('$owner_state$',2)[1]
    if attempt06:
        from .database_evidence import DIAGNOSTIC02_CAP_OWNER_SQL,ATTEMPT06_OWNER_SQL
        old=DIAGNOSTIC02_CAP_OWNER_SQL.split('$owner_state$',2)[1];new=ATTEMPT06_OWNER_SQL.split('$owner_state$',2)[1]
    if attempt07:
        from .database_evidence import ATTEMPT06_OWNER_SQL,ATTEMPT07_OWNER_SQL
        old=ATTEMPT06_OWNER_SQL.split('$owner_state$',2)[1];new=ATTEMPT07_OWNER_SQL.split('$owner_state$',2)[1]
    if attempt08:
        from .database_evidence import ATTEMPT07_OWNER_SQL,ATTEMPT08_OWNER_SQL
        old=ATTEMPT07_OWNER_SQL.split('$owner_state$',2)[1];new=ATTEMPT08_OWNER_SQL.split('$owner_state$',2)[1]
    if attempt09:
        from .database_evidence import ATTEMPT08_OWNER_SQL,ATTEMPT09_OWNER_SQL
        old=ATTEMPT08_OWNER_SQL.split('$owner_state$',2)[1];new=ATTEMPT09_OWNER_SQL.split('$owner_state$',2)[1]
    if attempt10:
        from .database_evidence import ATTEMPT09_OWNER_SQL,ATTEMPT10_OWNER_SQL
        old=ATTEMPT09_OWNER_SQL.split('$owner_state$',2)[1];new=ATTEMPT10_OWNER_SQL.split('$owner_state$',2)[1]
    c.execute('BEGIN')
    try:
        op.identity(c);op.inventory(c);op.dormant(c,stable_verifiers=stable_verifiers);op.owner_absent(c)
        c.execute("SET LOCAL statement_timeout='10s';SET LOCAL lock_timeout='3s';SET LOCAL idle_in_transaction_session_timeout='20s'")
        if attempt07:
            from .attempt06_recovery import successor_guard,SUCCESSOR,ACCEPTED
            import os,json
            h=json.loads(os.environ['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE']).get('attempt06_receipt_sha256')
            ctl=op.control(c);op.no_hazards(c,ctl);op.retained_cleanup(c,ctl)
            op.require(SUCCESSOR not in ctl.get('intake_periods',{}),'PERIOD_ALREADY_EXISTS_NO_RETRY')
            successor_guard(c,dict(period=SUCCESSOR,evidence_backend='POSTGRES_PILOT_V1',accepted_stop=ACCEPTED,attempt06_receipt_sha256=h),op.control(c))
        if attempt08:
            from . import period08_successor as p08
            ctl=op.control(c);p08.successor_guard(c,binding08,ctl);p08.unused(c,ctl,journal=True)
            op.no_hazards(c,ctl);op.retained_cleanup(c,ctl)
        if attempt09:
            from . import period09_successor as p09
            ctl=op.control(c);p09.successor_guard(c,binding09,ctl);p09.unused(c,ctl,journal=True)
            op.no_hazards(c,ctl);op.retained_cleanup(c,ctl)
        if attempt10:
            from . import period10_successor as p10
            ctl=op.control(c);p10.successor_guard(c,binding10,ctl);p10.unused(c,ctl,journal=True)
            op.no_hazards(c,ctl);op.retained_cleanup(c,ctl)
        before=c.execute(op.MEMBERS).fetchall();ledger=op.ledger_sha(c)
        schema=c.execute("SELECT nspacl::text FROM pg_namespace WHERE nspname='public'").fetchone()
        definition=c.execute("SELECT prosrc,proacl::text,proowner::regrole::text,prosecdef,proconfig FROM pg_proc WHERE oid='ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure").fetchone()
        op.require(definition[0] in (old,new) and definition[2:]==('ingestion_storage_owner',True,['search_path=pg_catalog']),'OWNER_CONTINUATION_MIGRATION')
        registrar=None
        if attempt09:
            registrar=c.execute("SELECT prosrc,proacl::text,proowner,prosecdef,proconfig FROM pg_proc WHERE oid='public.ingestion_register_bolton_exception(jsonb)'::regprocedure").fetchone()
            old_reg=op.Owner.daily_intake_inventory()['ingestion_register_bolton_exception']
            new_reg=p09.registration_sql().split('$register$',2)[1]
            op.require(registrar[0] in (old_reg,new_reg),'P09_REGISTRAR_BASELINE')
        if attempt10:
            registrar=c.execute("SELECT prosrc,proacl::text,proowner,prosecdef,proconfig FROM pg_proc WHERE oid='public.ingestion_register_bolton_exception(jsonb)'::regprocedure").fetchone()
            old_reg=p10.settlement.predecessor.registration_sql().split('$register$',2)[1]
            new_reg=p10.registration_sql().split('$register$',2)[1]
            op.require(registrar[0] in (old_reg,new_reg),'P10_REGISTRAR_BASELINE')
        if definition[0]==new:
            if attempt09:p09.namespace(c,migrated=True)
            if attempt10:p10.namespace(c,migrated=True)
            verify_inventory(c);op.owner_absent(c);c.execute('COMMIT');return dict(status='ALREADY_EXACT_READBACK',function_sha256=hashlib.sha256(new.encode()).hexdigest(),mutation=False)
        c.execute('GRANT ingestion_storage_owner TO postgres WITH INHERIT FALSE,SET TRUE GRANTED BY postgres')
        c.execute('GRANT CREATE ON SCHEMA public TO ingestion_storage_owner')
        c.execute('SET LOCAL ROLE ingestion_storage_owner')
        c.execute('LOCK TABLE public.ingestion_run_evidence IN SHARE ROW EXCLUSIVE MODE')
        snapshot=c.execute("SELECT count(*),md5(coalesce(string_agg(period||run_id||name||sha256,',' ORDER BY period,run_id,name),'')) FROM ingestion_run_evidence").fetchone()
        source=ATTEMPT10_OWNER_SQL if attempt10 else ATTEMPT09_OWNER_SQL if attempt09 else ATTEMPT08_OWNER_SQL if attempt08 else ATTEMPT07_OWNER_SQL if attempt07 else ATTEMPT06_OWNER_SQL if attempt06 else DIAGNOSTIC02_CAP_OWNER_SQL if diagnostic_cap else DEADLINE_OWNER_SQL if deadline else QUALIFICATION_OWNER_SQL if qualification else OWNER_SQL
        c.execute(source.split('REVOKE ALL ON FUNCTION',1)[0].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1))
        if attempt09 or attempt10:
            c.execute('LOCK TABLE public.ingestion_work_items,public.ingestion_work_attempts IN SHARE ROW EXCLUSIVE MODE')
            c.execute(p10.registration_sql() if attempt10 else p09.registration_sql())
            readback=c.execute("SELECT prosrc,proacl::text,proowner,prosecdef,proconfig FROM pg_proc WHERE oid='public.ingestion_register_bolton_exception(jsonb)'::regprocedure").fetchone()
            op.require(readback==(new_reg,*registrar[1:]),'P09_REGISTRAR_READBACK')
        op.require(c.execute("SELECT count(*),md5(coalesce(string_agg(period||run_id||name||sha256,',' ORDER BY period,run_id,name),'')) FROM ingestion_run_evidence").fetchone()==snapshot,'OWNER_CONTINUATION_PRESERVATION')
        c.execute('RESET ROLE')
        c.execute('REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner')
        c.execute('REVOKE ingestion_storage_owner FROM postgres GRANTED BY postgres RESTRICT')
        after=c.execute("SELECT proacl::text FROM pg_proc WHERE oid='ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure").fetchone()
        op.require(after==(definition[1],) and c.execute(op.MEMBERS).fetchall()==before and op.ledger_sha(c)==ledger
            and c.execute("SELECT nspacl::text FROM pg_namespace WHERE nspname='public'").fetchone()==schema,'OWNER_CONTINUATION_PRESERVATION')
        verify_inventory(c);op.owner_absent(c);c.execute('COMMIT')
        verify_inventory(c);op.owner_absent(c)
        observed=c.execute("SELECT prosrc FROM pg_proc WHERE oid='ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure").fetchone()
        op.require(observed==(new,),'OWNER_CONTINUATION_MIGRATION')
        return dict(status='COMMIT_ACKNOWLEDGED_AND_READ_BACK',function_sha256=hashlib.sha256(new.encode()).hexdigest(),mutation=True,evidence_rows=snapshot[0],evidence_inventory_md5=snapshot[1],ledger_sha256=ledger,permissions_restored=True)
    except BaseException:
        c.execute('ROLLBACK');raise
