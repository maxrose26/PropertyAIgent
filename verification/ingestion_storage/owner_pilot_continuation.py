"""Exact closed-qualification continuation; no replay, scheduler or new store."""
import hashlib
from . import intake_owner as op
from .database_evidence import OWNER_SQL,canonical,verify_inventory

def predecessor(state):
    op.require(type(state) is dict and state.get('period')=='b-dbpilot-20261027-1102-03'
        and state.get('status')=='CLOSED' and state.get('pipeline_status')=='NOT_VERIFIED'
        and state.get('failure')==dict(phase='ONE_JOB',exception_class='ReadTimeout',reason='UNKNOWN_FAILURE',sqlstate=None,status='RECONCILIATION_REQUIRED')
        and state.get('job',{}).get('id')=='job-dbl7bs7b9u1s73dp48sg'
        and state.get('job_terminal',{}).get('status')=='failed'
        and state.get('deployment')=='dep-dbl6kfdbedkc7385k7t0'
        and state.get('binding',{}).get('execution_binding',{}).get('revision')=='681f1a1cc886eb09efe70020dd34829f15e3817d'
        and state.get('access',{}).get('state')=='DATABASE_CLOSURE_ACKNOWLEDGED'
        and state.get('closure_receipt',{}).get('outcome')=='COMMIT_ACKNOWLEDGED'
        and state['closure_receipt'].get('sessions')=='ABSENT'
        and state['closure_receipt'].get('temporary_owner')=='REMOVED'
        and state['closure_receipt'].get('password_verifiers')=='RETAINED'
        and state.get('final_service')==dict(suspended=True,configuration_equal=True,environment_equal=True)
        and state.get('stable_credentials',{}).get('version')=='STABLE_RESTRICTED_V1'
        and set(state['stable_credentials'].get('passwords',{}))==set(op.ROLES)
        and set(state['stable_credentials'].get('verifier_sha256',{}))==set(op.ROLES)
        and state.get('runtime_qualification') is None and state.get('source_result') is None and state.get('independent_result') is None
        and all(state.get('intents',{}).get(k,{}).get('state')=='ACKNOWLEDGED' for k in ('PERIOD','ACTIVATE','HANDOFF','ONE_JOB')),
        'OWNER_CONTINUATION_PREDECESSOR')
    return {'period':state['period'],'state_sha256':hashlib.sha256(canonical(state)).hexdigest(),
        'closure_sha256':hashlib.sha256(canonical(state['closure_receipt'])).hexdigest(),
        'source_requests':'NOT_REACHED_IN_RETAINED_RUNTIME_TRACE','predecessor_job':'job-dbl7bs7b9u1s73dp48sg',
        'trace_evidence_sha256':'ae69bb02adff11c3187ee2e8690858d3aa9f8f7ba2c402748043160709655f96',
        'execution_identity':'b-dbpilot-20261027-1102-04'}

def migrate_owner_namespace(c, *, stable_verifiers=None):
    """Exact03→04 namespace addition; unchanged ACL, ledger and evidence."""
    new=OWNER_SQL.split('$owner_state$',2)[1]
    old=new.replace(",'b-dbpilot-20261027-1102-04_owner'",'')
    c.execute('BEGIN')
    try:
        op.identity(c);op.inventory(c);op.dormant(c,stable_verifiers=stable_verifiers);op.owner_absent(c)
        c.execute("SET LOCAL statement_timeout='10s';SET LOCAL lock_timeout='3s';SET LOCAL idle_in_transaction_session_timeout='20s'")
        before=c.execute(op.MEMBERS).fetchall();ledger=op.ledger_sha(c)
        schema=c.execute("SELECT nspacl::text FROM pg_namespace WHERE nspname='public'").fetchone()
        definition=c.execute("SELECT prosrc,proacl::text,proowner::regrole::text,prosecdef,proconfig FROM pg_proc WHERE oid='ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure").fetchone()
        op.require(definition[0] in (old,new) and definition[2:]==('ingestion_storage_owner',True,['search_path=pg_catalog']),'OWNER_CONTINUATION_MIGRATION')
        if definition[0]==new:
            verify_inventory(c);c.execute('COMMIT');return
        c.execute('GRANT ingestion_storage_owner TO postgres WITH INHERIT FALSE,SET TRUE GRANTED BY postgres')
        c.execute('GRANT CREATE ON SCHEMA public TO ingestion_storage_owner')
        c.execute('SET LOCAL ROLE ingestion_storage_owner')
        c.execute('LOCK TABLE public.ingestion_run_evidence IN SHARE ROW EXCLUSIVE MODE')
        snapshot=c.execute("SELECT count(*),md5(coalesce(string_agg(period||run_id||name||sha256,',' ORDER BY period,run_id,name),'')) FROM ingestion_run_evidence").fetchone()
        c.execute(OWNER_SQL.split('REVOKE ALL ON FUNCTION',1)[0].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1))
        op.require(c.execute("SELECT count(*),md5(coalesce(string_agg(period||run_id||name||sha256,',' ORDER BY period,run_id,name),'')) FROM ingestion_run_evidence").fetchone()==snapshot,'OWNER_CONTINUATION_PRESERVATION')
        c.execute('RESET ROLE')
        c.execute('REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner')
        c.execute('REVOKE ingestion_storage_owner FROM postgres GRANTED BY postgres RESTRICT')
        after=c.execute("SELECT proacl::text FROM pg_proc WHERE oid='ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure").fetchone()
        op.require(after==(definition[1],) and c.execute(op.MEMBERS).fetchall()==before and op.ledger_sha(c)==ledger
            and c.execute("SELECT nspacl::text FROM pg_namespace WHERE nspname='public'").fetchone()==schema,'OWNER_CONTINUATION_PRESERVATION')
        verify_inventory(c);op.owner_absent(c);c.execute('COMMIT')
        verify_inventory(c);op.owner_absent(c)
    except BaseException:
        c.execute('ROLLBACK');raise
