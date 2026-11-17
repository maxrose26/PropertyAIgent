"""Inactive single-namespace extension of the existing encrypted owner journal.
No new table, credential, crypto, byte limit, history limit or retry mechanism.
"""
import hashlib
from pathlib import Path
from contextlib import contextmanager
from .tameside_package import PERIOD
SOURCE_SHA='dffed8afd34e9ac379fd69177ef85b9cfbaaad921f6f103cad61d413fe9d9f2f'
BODY_SHA='adadf1970a5156c5b02b3b0db193376bf71767b04cf29c1557c94d58c185aacb'
JOURNAL=PERIOD+'_owner'
RUN=hashlib.sha256(JOURNAL.encode()).hexdigest()[:32]


def render_install(source):
    from .inactive_owner_writer_install import PRELUDE,EPILOGUE
    if hashlib.sha256(source.encode()).hexdigest()!=SOURCE_SHA:
        raise ValueError('TAMESIDE_OWNER_JOURNAL_SOURCE')
    marker=" IF p_period NOT IN ("
    if source.count(marker)!=1:raise ValueError('TAMESIDE_OWNER_JOURNAL_ANCHOR')
    revised=source.replace(marker,marker+"'"+JOURNAL+"',",1).replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1)
    checks="""
DO $tameside_journal_guard$
DECLARE ctl jsonb;

BEGIN
 IF has_schema_privilege('ingestion_storage_owner','public','CREATE') THEN RAISE EXCEPTION 'TAMESIDE_JOURNAL_SCHEMA_BASELINE'; END IF;
 LOCK TABLE public.ingestion_work_items,public.ingestion_run_evidence IN SHARE ROW EXCLUSIVE MODE;
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE;
 IF (ctl->>'hard_stop_generation')::integer IS DISTINCT FROM 15
 OR ctl->'global_stop' IS DISTINCT FROM '{"reason":"DAILY_INTAKE_SHARED_FAILURE"}'::jsonb
 OR coalesce(ctl->>'manual_stop','') NOT IN ('DAILY_INTAKE_SHARED_FAILURE','ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP')
 THEN RAISE EXCEPTION 'TAMESIDE_JOURNAL_STOP15'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_proc WHERE oid='public.ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure AND proowner='ingestion_storage_owner'::regrole AND prosecdef AND proconfig=ARRAY['search_path=pg_catalog']) THEN RAISE EXCEPTION 'TAMESIDE_JOURNAL_FUNCTION_BOUNDARY'; END IF;
 IF (SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex') FROM pg_proc WHERE oid='public.ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure) IS DISTINCT FROM '__BODY__'
 THEN RAISE EXCEPTION 'TAMESIDE_JOURNAL_INSTALLED_DRIFT'; END IF;
 IF EXISTS(SELECT 1 FROM public.ingestion_run_evidence WHERE period='__PERIOD__')
 THEN RAISE EXCEPTION 'TAMESIDE_JOURNAL_USED'; END IF;
END $tameside_journal_guard$;
GRANT CREATE ON SCHEMA public TO ingestion_storage_owner;
SET LOCAL ROLE ingestion_storage_owner;
""".replace('__BODY__',BODY_SHA).replace('__PERIOD__',JOURNAL)
    # Only the original owner-state function changes; no evidence is rewritten.
    return PRELUDE+checks+revised+'\nRESET ROLE;\nREVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner;\nDO $restored$ BEGIN IF has_schema_privilege(\'ingestion_storage_owner\',\'public\',\'CREATE\') THEN RAISE EXCEPTION \'TAMESIDE_JOURNAL_SCHEMA_REMAINS\'; END IF; END $restored$;\n'+EPILOGUE


def _bound_journal(pinned_owner_module,db):
    """Existing Vault codec and CAS journal, separate new operation namespace.

    Caller verifies exact pinned module/build and installed function before use.
    No old checkpoint is reset, appended to, or copied wholesale.
    """
    if hashlib.sha256(Path(pinned_owner_module.__file__).read_bytes()).hexdigest()!='f33439807df02e14fec167e7f3782a36af5e12e52949404c2388b610d1e61981':
        raise ValueError('TAMESIDE_PINNED_JOURNAL_CODEC')
    journal=pinned_owner_module.Journal(db,period=pinned_owner_module.PERIOD)
    journal.period=PERIOD;journal.owner_period=JOURNAL;journal.owner_run=RUN
    return journal


def fresh(pinned_owner_module,db):
    journal=_bound_journal(pinned_owner_module,db)
    if journal.load() is not None:raise ValueError('TAMESIDE_OWNER_JOURNAL_USED')
    return journal


def reconcile(pinned_owner_module,db):
    """Independent decrypting read after uncertain ACK; never repeats a write.

    Compare returned state with the retained intended state before any next
    action. Missing state is UNKNOWN, not permission to start another operation.
    """
    journal=_bound_journal(pinned_owner_module,db)
    class ReadOnly:
        key=db.key
        @contextmanager
        def connection(self):
            with db.connection() as connection:
                connection.execute('BEGIN READ ONLY')
                try:yield connection
                finally:connection.execute('ROLLBACK')
    journal.db=ReadOnly()
    try:state=journal.load()
    finally:journal.db=db
    if state is None:raise ValueError('TAMESIDE_OWNER_JOURNAL_OUTCOME_UNKNOWN')
    return journal,state
