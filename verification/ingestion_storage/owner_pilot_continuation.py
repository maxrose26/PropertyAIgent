"""Exact closed-qualification continuation; no replay, scheduler or new store."""
import hashlib
from . import intake_owner as op
from .database_evidence import OWNER_SQL,canonical,verify_inventory

def predecessor(state):
    op.require(type(state) is dict and state.get('period')=='b-dbpilot-20261027-1102-01'
        and state.get('status')=='CLOSED' and state.get('pipeline_status')=='NOT_VERIFIED'
        and state.get('failure',{}).get('phase')=='QUALIFY'
        and state.get('failure',{}).get('exception_class')=='Denied'
        and state.get('failure',{}).get('reason')=='UNKNOWN_FAILURE'
        and state.get('access',{}).get('state')=='DATABASE_CLOSURE_ACKNOWLEDGED'
        and state.get('closure_receipt',{}).get('outcome')=='COMMIT_ACKNOWLEDGED'
        and state.get('closure_receipt',{}).get('sessions')=='ABSENT'
        and state.get('closure_receipt',{}).get('temporary_owner')=='REMOVED'
        and state.get('final_service')==dict(suspended=True,configuration_equal=True,environment_equal=True)
        and not any(k in state for k in ('job','source_result','independent_result'))
        and not any(k in state.get('intents',{}) for k in ('HANDOFF','ONE_JOB')),
        'OWNER_CONTINUATION_PREDECESSOR')
    return {'period':state['period'],'state_sha256':hashlib.sha256(canonical(state)).hexdigest(),
        'closure_sha256':hashlib.sha256(canonical(state['closure_receipt'])).hexdigest(),
        'source_requests':'NOT_REACHED','execution_identity':'b-dbpilot-20261027-1102-02'}

def migrate_owner_namespace(c):
    """Atomic exact old→two-name interface; unchanged ACL, ledger and evidence."""
    new=OWNER_SQL.split('$owner_state$',2)[1]
    old=new.replace("p_period NOT IN ('b-dbpilot-20261027-1102-01_owner','b-dbpilot-20261027-1102-02_owner')", "p_period<>'b-dbpilot-20261027-1102-01_owner'")
    c.execute('BEGIN')
    try:
        op.identity(c);op.inventory(c);op.dormant(c);op.owner_absent(c)
        c.execute("SET LOCAL statement_timeout='10s';SET LOCAL lock_timeout='3s';SET LOCAL idle_in_transaction_session_timeout='20s'")
        c.execute('LOCK TABLE public.ingestion_run_evidence IN SHARE ROW EXCLUSIVE MODE')
        before=c.execute(op.MEMBERS).fetchall();ledger=op.ledger_sha(c)
        schema=c.execute("SELECT nspacl::text FROM pg_namespace WHERE nspname='public'").fetchone()
        snapshot=c.execute("SELECT count(*),md5(coalesce(string_agg(period||run_id||name||sha256,',' ORDER BY period,run_id,name),'')) FROM ingestion_run_evidence").fetchone()
        definition=c.execute("SELECT prosrc,proacl::text,proowner::regrole::text,prosecdef,proconfig FROM pg_proc WHERE oid='ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure").fetchone()
        op.require(definition[0] in (old,new) and definition[2:]==('ingestion_storage_owner',True,['search_path=pg_catalog']),'OWNER_CONTINUATION_MIGRATION')
        if definition[0]==old:
            c.execute('GRANT ingestion_storage_owner TO postgres WITH INHERIT FALSE,SET TRUE GRANTED BY postgres')
            c.execute('GRANT CREATE ON SCHEMA public TO ingestion_storage_owner')
            c.execute('SET LOCAL ROLE ingestion_storage_owner')
            c.execute(OWNER_SQL.split('REVOKE ALL ON FUNCTION',1)[0].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1))
            c.execute('RESET ROLE')
            c.execute('REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner')
            c.execute('REVOKE ingestion_storage_owner FROM postgres GRANTED BY postgres RESTRICT')
        after=c.execute("SELECT proacl::text FROM pg_proc WHERE oid='ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure").fetchone()
        op.require(after==(definition[1],) and c.execute(op.MEMBERS).fetchall()==before and op.ledger_sha(c)==ledger
            and c.execute("SELECT nspacl::text FROM pg_namespace WHERE nspname='public'").fetchone()==schema
            and c.execute("SELECT count(*),md5(coalesce(string_agg(period||run_id||name||sha256,',' ORDER BY period,run_id,name),'')) FROM ingestion_run_evidence").fetchone()==snapshot,'OWNER_CONTINUATION_PRESERVATION')
        verify_inventory(c);op.owner_absent(c);c.execute('COMMIT')
        verify_inventory(c);op.owner_absent(c)
    except BaseException:
        c.execute('ROLLBACK');raise
