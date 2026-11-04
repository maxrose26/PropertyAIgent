"""Exact closed-qualification continuation; no replay, scheduler or new store."""
import hashlib
from . import intake_owner as op
from .database_evidence import OWNER_SQL,canonical,verify_inventory

def predecessor(state, *, snapshot):
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

def migrate_owner_namespace(c, *, stable_verifiers=None):
    """Exact04→05 namespace addition; unchanged ACL, ledger and evidence."""
    new=OWNER_SQL.split('$owner_state$',2)[1]
    old=new.replace(",'b-dbpilot-20261027-1102-05_owner'",'')
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
