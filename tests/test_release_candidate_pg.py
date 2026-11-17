"""Actual PostgreSQL execution of candidate SQL; synthetic state, no sources.

Identity projection is explicit: local database name/bootstrap executor in the
release body only. Existing restricted-owner tests cover the unchanged lifecycle.
These tests do NOT claim the connected recovery/runtime gate has passed.
"""
import copy
import json
import time
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import psycopg
from tests.e2e_pg_world import settings

from tests.test_inactive_stop_release_pg import (
    isolated_world, _seed, _manifest, _seal_manifest, _control, _run,
)
from tests.test_inactive_tameside_first_issuer import _inactive_owner_policy_fixture
from verification.ingestion_storage import release_candidate as candidate
from verification.ingestion_storage.bolton_recovery_guard import OLD, NEW


def test_pinned_guard_actual_recovery_entrypoint(tmp_path):
    pin = os.environ.get('S4_BOLTON_PINNED_CHECKOUT')
    if not pin:
        pytest.skip('separate pinned #213 checkout required')
    pin = Path(pin).resolve()
    assert subprocess.check_output(['git', '-C', str(pin), 'rev-parse', 'HEAD'], text=True).strip() == 'f027ba28af69ae70208eab5ed047e4a8a81c6337'
    helper = tmp_path / 'guard_stage.py'
    helper.write_bytes(Path('tests/pinned_bolton_guard_stage.py').read_bytes())
    env = dict(os.environ, PYTHONPATH=str(pin), S4_SUCCESSOR_ROOT=str(Path.cwd()))
    result = subprocess.run([sys.executable, '-m', 'pytest', str(helper), '--rootdir', str(pin),
                             '--import-mode=importlib', '-q', '-p', 'no:cacheprovider',
                             '--basetemp', str(tmp_path/'pinned')], cwd=pin, env=env,
                            capture_output=True, text=True, timeout=150)
    assert result.returncode == 0, result.stdout[-12000:] + result.stderr[-4000:]


def release_script(w, *, expiry=None):
    manifest = _manifest(w)
    manifest['expires_at'] = expiry if expiry is not None else time.time() + 600
    _seal_manifest(w, manifest)
    source = candidate.render_release(manifest, expires_at=manifest['expires_at'])
    # Preserve the candidate's actual body, manifest and expiry; substitute only
    # fixture identity and unchanged capability block (covered in old tests).
    import re
    for start, end in (('-- OWNER_CAPABILITY_BEGIN', '-- OWNER_CAPABILITY_END'),
                       ('-- OWNER_CAPABILITY_CLEANUP_BEGIN', '-- OWNER_CAPABILITY_CLEANUP_END')):
        source = re.sub(re.escape(start)+r'.*?'+re.escape(end)+r'\n', '', source, flags=re.S)
    source = source.replace("current_database() IS DISTINCT FROM 'postgres'",
                            "current_database() IS DISTINCT FROM 'ingestion_provisioning_test'")
    source = source.replace("session_user IS DISTINCT FROM 'postgres'",
                            "session_user IS DISTINCT FROM 'provisioning_bootstrap'")
    source = source.replace("current_user IS DISTINCT FROM 'postgres'",
                            "current_user IS DISTINCT FROM 'provisioning_bootstrap'")
    return manifest, source


def test_release_candidate_expiry_rollback_and_independent_readback(isolated_world):
    w = isolated_world
    _seed(w)
    w['boot'].execute(candidate.RELEASE_PATH.with_name('private_evidence_writer_transition.sql').read_text())
    before = _control(w)
    _, expired = release_script(w, expiry=time.time()-1)
    with pytest.raises(Exception, match='OWNER_RELEASE_EXPIRED'):
        _run(w, expired)
    assert _control(w) == before
    manifest, source = release_script(w)
    _run(w, source, rollback=True)
    assert _control(w) == before
    _run(w, source)
    with psycopg.connect(settings()[0], autocommit=True) as separate:
        separate.execute('BEGIN READ ONLY')
        state = separate.execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
        separate.execute('ROLLBACK')
    assert state['hard_stop_generation'] == 16
    assert state['global_stop'] is None and state['manual_stop'] is None
    assert state['owner_shared_stop_release']['manifest_binding_sha256'] == manifest['manifest_binding_sha256']
    with pytest.raises(Exception, match='OWNER_RELEASE_STOP_CAS'):
        _run(w, source)


def test_compiled_campaign_exact_policy_positive_and_drift(isolated_world):
    w = isolated_world
    _, period, policy, stop, binding = _inactive_owner_policy_fixture()
    now = datetime.now(timezone.utc)
    from verification.ingestion_storage.inactive_tameside_first_issuer import prepare_inactive_campaign_owner_batch
    preview = prepare_inactive_campaign_owner_batch(now, 'tameside', '2026-09-15', '2026-09-21')
    period = preview['period']
    policy['campaign_source_plan_sha256'] = preview['campaign_source_plan_sha256']
    policy['expires_at'] = time.time()+600
    sql = candidate.render_campaign(as_of=now, period=period, policy=policy,
                                    release_manifest_sha256='1'*64)
    sql = sql.replace("current_database() IS DISTINCT FROM 'postgres'",
                      "current_database() IS DISTINCT FROM 'ingestion_provisioning_test'")
    w['boot'].execute(sql)
    w['boot'].execute('ALTER FUNCTION ingestion_register_campaign_once(jsonb) OWNER TO ingestion_storage_owner')
    ctl = _control(w)
    ctl.update(stop)
    ctl['owner_shared_stop_release'] = dict(manifest_binding_sha256='1'*64)
    w['boot'].execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)", (json.dumps(ctl),))
    query = 'SELECT ingestion_register_campaign_once(%s::jsonb)'
    for mutation in ('window', 'expiry', 'binding', 'source_plan', 'council'):
        changed = copy.deepcopy(policy)
        if mutation == 'window': changed['campaign_batch']['end'] = '2026-09-20'
        elif mutation == 'expiry': changed['expires_at'] += 1
        elif mutation == 'binding': changed['execution_binding']['revision'] = 'f'*40
        elif mutation == 'source_plan': changed['campaign_source_plan_sha256'] = 'f'*64
        else: changed['campaign_batch']['council'] = 'manchester'
        with pytest.raises(Exception):
            w['boot'].execute(query, (json.dumps(dict(operation='intake_period', period=period, policy=changed)),))
        assert _control(w) == ctl
    result = w['boot'].execute(query, (json.dumps(dict(operation='intake_period', period=period, policy=policy)),)).fetchone()[0]
    assert result['campaign_batch'] == candidate.BATCH and result['max_runs'] == 1
    with pytest.raises(Exception):
        w['boot'].execute(query, (json.dumps(dict(operation='intake_period', period=period, policy=policy)),))


def test_unrelated_claimed_predicate_under_table_lock(isolated_world):
    w = isolated_world
    w['boot'].execute("INSERT INTO ingestion_work_items SELECT (jsonb_populate_record(NULL::ingestion_work_items,to_jsonb(w)||%s::jsonb)).* FROM ingestion_work_items w WHERE key=repeat('0',64)",
                      (json.dumps(dict(key='f'*64, state='CLAIMED', phase='IDLE', authority='unrelated')),))
    w['boot'].execute('BEGIN')
    try:
        w['boot'].execute('LOCK TABLE ingestion_work_items,ingestion_work_attempts IN SHARE ROW EXCLUSIVE MODE')
        assert w['boot'].execute(OLD, ('a'*64, 'expected')).fetchone() == (0,)
        assert w['boot'].execute(NEW, ('a'*64, 'expected')).fetchone() == (1,)
        with w['connect']('provisioning_migrator') as other:
            other.execute("SET lock_timeout='50ms'")
            with pytest.raises(Exception, match='lock timeout'):
                other.execute("UPDATE ingestion_work_items SET state='DEFERRED' WHERE key=%s", ('f'*64,))
    finally:
        w['boot'].execute('ROLLBACK')


def test_disposition_preserves_originals_and_refuses_changed_preimage(isolated_world):
    w = isolated_world
    _seed(w)
    proposal = json.loads(Path('docs/design/pa-tam001-transport/release-proposal.json').read_text())
    original = candidate.render_dispositions(proposal)
    # Fixture data substitutes for the actual retained historical rows. Never
    # label these generated digests as observed production fingerprints.
    fixture = copy.deepcopy(proposal)
    before = {}
    for key in proposal['prior_fingerprints']:
        if key.startswith('d9d8'): continue
        w['boot'].execute("UPDATE ingestion_work_items SET state='SAFETY_BLOCKED',phase='RECOVERED',next_action='RECONCILE' WHERE key=%s", (key,))
        row = w['boot'].execute('SELECT to_jsonb(w) FROM ingestion_work_items w WHERE key=%s', (key,)).fetchone()[0]
        attempts = w['boot'].execute('SELECT jsonb_agg(to_jsonb(a) ORDER BY fence) FROM ingestion_work_attempts a WHERE work_key=%s', (key,)).fetchone()[0]
        before[key] = (row, attempts)
        fixture['prior_fingerprints'][key] = w['boot'].execute("SELECT encode(sha256(convert_to(jsonb_build_object('work',%s::jsonb,'attempts',%s::jsonb)::text,'UTF8')),'hex')", (json.dumps(row), json.dumps(attempts))).fetchone()[0]
    # Execute the generated body unchanged; only fixture payload and principal
    # projection differ, as in the original release fixture.
    source = original.replace(candidate._literal(proposal), candidate._literal(fixture))
    from verification.ingestion_storage.inactive_owner_writer_install import PRELUDE, EPILOGUE
    source = source.removeprefix(PRELUDE).removesuffix(EPILOGUE)
    source = 'BEGIN;\n' + source + '\nCOMMIT;\n'
    key = next(iter(before))
    w['boot'].execute("UPDATE ingestion_work_items SET reason='CHANGED' WHERE key=%s", (key,))
    changed = w['boot'].execute('SELECT key,to_jsonb(w) FROM ingestion_work_items w ORDER BY key').fetchall()
    with pytest.raises(Exception, match='DISPOSITION_ORIGINAL_DRIFT'):
        _run(w, source)

    assert w['boot'].execute('SELECT key,to_jsonb(w) FROM ingestion_work_items w ORDER BY key').fetchall() == changed
    w['boot'].execute('UPDATE ingestion_work_items SET reason=%s WHERE key=%s', (before[key][0]['reason'], key))
    _run(w, source)
    for key, (old, attempts) in before.items():
        row = w['boot'].execute('SELECT to_jsonb(w) FROM ingestion_work_items w WHERE key=%s', (key,)).fetchone()[0]
        assert row['checkpoint']['original_work'] == old
        assert row['checkpoint']['original_attempts'] == attempts
        assert row['outcome']['coverage'] == 'UNKNOWN'
        assert row['outcome']['source_or_write_replay_authorised'] is False
        assert row['next_action'] == 'PRESERVE_HISTORY_NO_REPLAY'
        assert w['boot'].execute('SELECT jsonb_agg(to_jsonb(a) ORDER BY fence) FROM ingestion_work_attempts a WHERE work_key=%s', (key,)).fetchone()[0] == attempts
    with pytest.raises(Exception, match='DISPOSITION_ORIGINAL_DRIFT'):
        _run(w, source)


def test_candidate_installs_stopped_as_real_restricted_owner(isolated_world):
    from psycopg import sql
    import secrets
    w = isolated_world
    _seed(w)
    now = datetime.now(timezone.utc)
    _, _, policy, _, _ = _inactive_owner_policy_fixture()
    from verification.ingestion_storage.inactive_tameside_first_issuer import prepare_inactive_campaign_owner_batch
    preview = prepare_inactive_campaign_owner_batch(now, 'tameside', '2026-09-15', '2026-09-21')
    policy['campaign_source_plan_sha256'] = preview['campaign_source_plan_sha256']
    policy['expires_at'] = time.time()+1800
    source = candidate.render_campaign_install(as_of=now, period=preview['period'], policy=policy, release_manifest_sha256='1'*64)
    source = source.replace("current_database() IS DISTINCT FROM 'postgres'", "current_database() IS DISTINCT FROM 'ingestion_provisioning_test'")
    password = secrets.token_urlsafe(32)
    w['boot'].execute(sql.SQL('ALTER ROLE postgres LOGIN NOSUPERUSER CREATEROLE CREATEDB BYPASSRLS INHERIT PASSWORD {}').format(sql.Literal(password)))
    w['boot'].execute('GRANT ingestion_storage_owner TO postgres WITH ADMIN TRUE, INHERIT FALSE, SET FALSE GRANTED BY provisioning_bootstrap')
    w['boot'].execute('GRANT USAGE,CREATE ON SCHEMA public TO postgres WITH GRANT OPTION')
    name = 'public.ingestion_register_campaign_once(jsonb)'
    _, info, _, _ = settings()
    def connect():
        return psycopg.connect(**{**info, 'user':'postgres', 'password':password}, autocommit=True)
    try:
        assert w['boot'].execute("SELECT has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone() == (False,)
        before = _control(w)
        with connect() as owner:
            owner.execute(source.replace('\nCOMMIT;\n', '\nROLLBACK;\n'))
        assert w['boot'].execute('SELECT to_regprocedure(%s)', (name,)).fetchone() == (None,)
        with connect() as owner:
            owner.execute(source)
        assert _control(w) == before
        assert w['boot'].execute("SELECT has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone() == (False,)
        assert w['boot'].execute("SELECT pg_has_role('postgres','ingestion_storage_owner','USAGE'),pg_has_role('postgres','ingestion_storage_owner','SET')").fetchone() == (False, False)
        assert w['boot'].execute("SELECT has_function_privilege('postgres',%s,'EXECUTE')", (name,)).fetchone() == (True,)
        assert w['boot'].execute("SELECT has_function_privilege('ingestion_worker_login',%s,'EXECUTE')", (name,)).fetchone() == (False,)
    finally:
        w['boot'].execute('REVOKE EXECUTE ON FUNCTION '+name+' FROM postgres')
        w['boot'].execute('REVOKE ALL PRIVILEGES ON SCHEMA public FROM postgres')
        w['boot'].execute('REVOKE ingestion_storage_owner FROM postgres GRANTED BY provisioning_bootstrap RESTRICT')
        w['boot'].execute('ALTER ROLE postgres NOLOGIN NOCREATEROLE NOCREATEDB NOBYPASSRLS PASSWORD NULL')
