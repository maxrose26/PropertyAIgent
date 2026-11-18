"""Scoped 50KiB amendment of the existing owner journal; no new storage.

Old rows/codecs remain immutable. A small old-contract intent precedes the
transactional function upgrade. Every upgraded reader verifies the same marker.
"""
import time
import copy
import hashlib
import inspect
import textwrap

from . import tameside_owner_journal as ja
from . import tameside_stop15 as plan
from .tameside_preparation import require
from .inactive_owner_writer_install import PRELUDE, EPILOGUE

LIMIT = 51200
VERSION = 'TAMESIDE_OWNER_50K_V1'
FIELD = 'checkpoint_capacity'


def policy(pinned):
    value = pinned.cleanup_reserve_policy()
    reserve = value['growth_bytes'] + value['margin_bytes']
    value['normal_plaintext_ceiling'] = max(n for n in range(LIMIT + 1)
        if pinned.ciphertext_size(n + reserve) <= LIMIT)
    return value


def marker():
    return dict(version=VERSION, ciphertext_limit=LIMIT, journal=ja.JOURNAL,
                original_ordinal=18, original_sha256=plan.CHECKPOINT)


def definitions(source):
    ja.render_install(source)  # unchanged pinned-source verification
    old = source.replace(" IF p_period NOT IN (", " IF p_period NOT IN ('" + ja.JOURNAL + "',", 1)
    needle = 'IF octet_length(p_body) NOT BETWEEN 1 AND '
    require(old.count(needle) == 1, 'CAPACITY_SQL_ANCHOR')
    start = old.index(needle) + len(needle)
    end = old.index(" THEN RAISE EXCEPTION 'OWNER_STATE_VAULT_BOUND'", start)
    bound = old[start:end]
    new = old[:start] + "(CASE WHEN p_period='" + ja.JOURNAL + "' THEN 51200 ELSE " + bound + " END)" + old[end:]
    return old, new


def fingerprint(source):
    return hashlib.sha256(source.split('$owner_state$')[1].encode()).hexdigest()


def observe(db, source):
    old, new = definitions(source)
    with db.connection() as c:
        c.execute('BEGIN READ ONLY')
        try:
            row = c.execute("SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex'),proowner='ingestion_storage_owner'::regrole,prosecdef,proconfig FROM pg_proc WHERE oid='public.ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure").fetchone()
            require(row and row[1:] == (True, True, ['search_path=pg_catalog']), 'CAPACITY_FUNCTION_BOUNDARY')
            acl = c.execute("SELECT pg_get_userbyid(x.grantee),x.privilege_type,x.is_grantable FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x WHERE p.oid='public.ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure AND x.grantee<>p.proowner ORDER BY 1").fetchall()
            require(acl == [('postgres', 'EXECUTE', False)], 'CAPACITY_FUNCTION_ACL')
            require(row[0] in (fingerprint(old), fingerprint(new)), 'CAPACITY_FUNCTION_DRIFT')
            restored = c.execute("SELECT pg_has_role(current_user,'ingestion_storage_owner','USAGE'),pg_has_role(current_user,'ingestion_storage_owner','SET'),has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone()
            require(restored == (False, False, False), 'CAPACITY_PERMISSIONS_NOT_RESTORED')
            membership = c.execute("SELECT count(*),coalesce(bool_and(grantor<>'postgres'::regrole AND admin_option AND NOT inherit_option AND NOT set_option),false) FROM pg_auth_members WHERE member='postgres'::regrole AND roleid='ingestion_storage_owner'::regrole").fetchone()
            require(membership == (1, True), 'CAPACITY_MEMBERSHIP_NOT_RESTORED')
            return row[0] == fingerprint(new)
        finally:
            c.execute('ROLLBACK')


def journal_type(pinned):
    """Isolate adapted method globals; never mutate the frozen module or Vault."""
    # ja._bound_journal validates the entire pinned Journal module first.
    original_vault = pinned.Vault
    vault_scope = dict(original_vault.__init__.__globals__, VAULT_LIMIT=LIMIT)
    exec(compile(textwrap.dedent(inspect.getsource(original_vault)), '<scoped-tameside-vault>', 'exec'), vault_scope)
    vault = vault_scope['Vault']
    methods = dict(pinned.Journal._vault.__globals__, Vault=vault)
    exec(compile(textwrap.dedent(inspect.getsource(pinned.Journal._vault)), '<scoped-tameside-journal>', 'exec'), methods)
    adapted_vault = methods['_vault']
    saves = dict(pinned.Journal.save.__globals__, cleanup_reserve_policy=lambda: policy(pinned))
    exec(compile(textwrap.dedent(inspect.getsource(pinned.Journal.save)), '<scoped-tameside-reserve>', 'exec'), saves)
    adapted_save = saves['save']

    class ScopedJournal(pinned.Journal):
        capacity_verified = False

        def _vault(self, raw=None, value=None):
            require(self.owner_period == ja.JOURNAL and self.period == plan.PERIOD,
                    'CAPACITY_NAMESPACE')
            if value is not None and FIELD not in value:
                return super()._vault(raw=raw, value=value)
            result = adapted_vault(self, raw=raw, value=value)
            if raw is not None:
                if FIELD in result:
                    require(result[FIELD] == marker(), 'CAPACITY_MARKER')
                    require(all(result['cleanup_reserve'].get(k) == v for k, v in policy(pinned).items()), 'CAPACITY_RESERVE')
                else:
                    require(len(raw) <= 32768, 'CAPACITY_UNMARKED_LARGE_ROW')
            return result

        def save(self, state, connection=None, *, validate_only=False):
            if FIELD not in state:
                require(not self.state or FIELD not in self.state, 'CAPACITY_DOWNGRADE')
                return super().save(state, connection, validate_only=validate_only)
            require(state[FIELD] == marker(), 'CAPACITY_MARKER')
            require(validate_only or self.capacity_verified, 'CAPACITY_INSTALL_READBACK_REQUIRED')
            return adapted_save(self, state, connection, validate_only=validate_only)

    return ScopedJournal


def archive(journal):
    with journal.db.connection() as c:
        c.execute('BEGIN READ ONLY')
        try:
            row = c.execute("SELECT body,sha256 FROM public.ingestion_run_evidence WHERE period=%s AND run_id=%s AND name='owner/state-018'", (ja.JOURNAL, ja.RUN)).fetchone()
            require(row and row[1] == plan.CHECKPOINT and hashlib.sha256(bytes(row[0])).hexdigest() == plan.CHECKPOINT, 'CAPACITY_ORIGINAL_CHECKPOINT')
            return journal._vault(raw=bytes(row[0]))
        finally:
            c.execute('ROLLBACK')


def intent(source, approval_ref, review_ref):
    old, new = definitions(source)
    return dict(version=VERSION, state='INTENT', original_ordinal=18,
        original_sha256=plan.CHECKPOINT, old_function_sha256=fingerprint(old),
        new_function_sha256=fingerprint(new), approval_ref=approval_ref, review_ref=review_ref)


def prebind_state(journal, state, source, approval_ref, review_ref):
    """Verify any durable pre-bind upgrade against immutable row18, not a count."""
    if 'capacity_upgrade' not in state:
        plan.retained_start(state, ordinal=journal.ordinal, sha256=journal.previous)
        return state
    baseline = archive(journal)
    plan.retained_start(baseline, ordinal=18, sha256=plan.CHECKPOINT)
    wanted = intent(source, approval_ref, review_ref)
    wanted['state'] = state['capacity_upgrade']['state']
    require(wanted['state'] in ('INTENT', 'ACKNOWLEDGED') and state['capacity_upgrade'] == wanted,
            'CAPACITY_UPGRADE_INTENT_DRIFT')
    expected = copy.deepcopy(baseline)
    expected['capacity_upgrade'] = wanted
    if wanted['state'] == 'ACKNOWLEDGED':
        expected[FIELD] = marker()
        expected['cleanup_reserve'] = dict(policy(journal.pinned), cleanup_writes=0)
    require(state == expected and journal.ordinal == (19 if wanted['state']=='INTENT' else 20),
            'CAPACITY_UPGRADE_STATE_DRIFT')
    return baseline


def upgrade_sql(source, *, journal_sha):
    old, new = definitions(source)
    guard = """
DO $capacity_upgrade_guard$
DECLARE ctl jsonb;
BEGIN
 IF has_schema_privilege('ingestion_storage_owner','public','CREATE') THEN RAISE EXCEPTION 'CAPACITY_SCHEMA_BASELINE'; END IF;
 IF NOT pg_try_advisory_xact_lock(1886547824,20261103) THEN RAISE EXCEPTION 'OWNER_STATE_BUSY'; END IF;
 LOCK TABLE public.ingestion_work_items,public.ingestion_run_evidence IN SHARE ROW EXCLUSIVE MODE;
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE;
 IF (ctl->>'hard_stop_generation')::integer IS DISTINCT FROM 15
 OR ctl->'global_stop' IS DISTINCT FROM '{"reason":"DAILY_INTAKE_SHARED_FAILURE"}'::jsonb
 OR ctl->>'manual_stop' IS DISTINCT FROM 'ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP'
 OR ctl ? 'intake_run' THEN RAISE EXCEPTION 'CAPACITY_STOP15'; END IF;
 IF EXISTS(SELECT 1 FROM public.ingestion_work_items WHERE state IN ('CLAIMED','PERSISTENCE_UNCERTAIN') OR phase IN ('SOURCE_INTENT','WRITE_INTENT')) THEN RAISE EXCEPTION 'CAPACITY_ACTIVE_WORK'; END IF;
 IF EXISTS(SELECT 1 FROM pg_stat_activity WHERE usename IN ('ingestion_worker_login','ingestion_effect_login','ingestion_recovery_login','ingestion_application_login')) THEN RAISE EXCEPTION 'CAPACITY_ACTIVE_SESSION'; END IF;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN ('ingestion_worker_login','ingestion_effect_login') AND rolcanlogin) THEN RAISE EXCEPTION 'CAPACITY_LOGIN'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.ingestion_run_evidence WHERE period='__PERIOD__' AND run_id='__RUN__' AND name='owner/state-018' AND sha256='__ORIGINAL__' AND encode(sha256(body),'hex')=sha256)
 OR (SELECT name FROM public.ingestion_run_evidence WHERE period='__PERIOD__' AND run_id='__RUN__' ORDER BY name DESC LIMIT 1) IS DISTINCT FROM 'owner/state-019'
 OR (SELECT sha256 FROM public.ingestion_run_evidence WHERE period='__PERIOD__' AND run_id='__RUN__' AND name='owner/state-019' AND encode(sha256(body),'hex')=sha256) IS DISTINCT FROM '__INTENT__'
 THEN RAISE EXCEPTION 'CAPACITY_CHECKPOINT_DRIFT'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_proc WHERE oid='public.ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure AND proowner='ingestion_storage_owner'::regrole AND prosecdef AND proconfig=ARRAY['search_path=pg_catalog'] AND encode(sha256(convert_to(prosrc,'UTF8')),'hex')='__OLD__') THEN RAISE EXCEPTION 'CAPACITY_FUNCTION_DRIFT'; END IF;
END $capacity_upgrade_guard$;
GRANT CREATE ON SCHEMA public TO ingestion_storage_owner;
SET LOCAL ROLE ingestion_storage_owner;
"""
    for key, value in dict(PERIOD=ja.JOURNAL, RUN=ja.RUN, ORIGINAL=plan.CHECKPOINT,
                           INTENT=journal_sha, OLD=fingerprint(old)).items():
        require(all(ch in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for ch in value), 'CAPACITY_SQL_LITERAL')
        guard = guard.replace('__'+key+'__', value)
    restore = "\nRESET ROLE; REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner;\n"
    restore += "DO $capacity_schema_restore$ BEGIN IF has_schema_privilege('ingestion_storage_owner','public','CREATE') THEN RAISE EXCEPTION 'CAPACITY_SCHEMA_REMAINS'; END IF; END $capacity_schema_restore$;\n"
    return PRELUDE + guard + new.replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1) + restore + EPILOGUE


def upgrade(runner, source):
    """One old-contract intent, read-before-repeat SQL, independent ACK journal."""
    runner.inspect()  # full original restoration/current STOP15 checks
    if FIELD in runner.state:
        require(observe(runner.db, source), 'CAPACITY_INSTALL_LOST')
        runner.journal.capacity_verified = True
        return
    # Preserve at least the complete finite execution/cleanup window.
    # Inspection/cleanup remain available after this first-effect deadline.
    from .tameside_candidate import EXPIRY
    require(time.time() + 2100 <= EXPIRY, 'CAPACITY_OPERATIONAL_WINDOW_ELAPSED')
    if 'capacity_upgrade' not in runner.state:
        runner.state['capacity_upgrade'] = intent(source, runner.approval_ref, runner.review_ref)
        runner.save()  # old contract must fit before SQL can run
    prebind_state(runner.journal, runner.state, source, runner.approval_ref, runner.review_ref)
    if not observe(runner.db, source):
        sql = upgrade_sql(source, journal_sha=runner.journal.previous)
        try:
            with runner.db.connection() as c:
                c.execute(sql)
        except Exception:
            require(observe(runner.db, source), 'CAPACITY_SQL_OUTCOME_UNKNOWN')
    require(observe(runner.db, source), 'CAPACITY_INSTALL_READBACK')
    # Never append larger state until the exact installed writer is known.
    runner.journal.capacity_verified = True
    runner.state[FIELD] = marker()
    runner.state['cleanup_reserve'] = dict(policy(runner.pinned), cleanup_writes=0)
    runner.state['capacity_upgrade']['state'] = 'ACKNOWLEDGED'
    runner.save()
