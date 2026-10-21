"""Disposable-PostgreSQL rehearsal of the screening-v3 production connection (PR #173 section 5.3). Fixed loopback PG17 service only; skipped without it.

The ORIGINAL `ingestion_worker_step` is installed first (the production state), the v3 replacement is installed by the owner-terminal ceremony text (installation_script), and then the real SQL, the real SQLLedger and the
real controller function `assess_retained` screen the verified full retained Bolton capture (24 records). Nothing here contacts a council or a production database: the grant has source_calls = 0 and the test asserts no
source intent was ever recorded. Measured costs are printed and, if V3_REHEARSAL_TIMINGS names a file, written there as JSON."""
import copy
import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from app.db.models import Application, Base, Council
from app.ingestion import batching
from app.ingestion import listing_screening as ls
from app.ingestion import screening_history as sh
from app.ingestion.coordinator import Coordinator
from app.ingestion.ledger import DEFAULT_LIMITS, Denied, digest
from app.ingestion.schema import WorkAttempt as A, WorkItem as W
from app.ingestion.sql_ledger import SQLLedger
from tests.test_discovery_ingestion_provisioning_pg import PACKAGE, ROLES
from tests.test_ingestion_screening_v3_worker_sql import SPEC034
from tests.test_ingestion_retained_capture_reconciliation import CAPTURE_CHECKPOINT, CAPTURE_KEY, CON, SCOPE, identities, item, retained
from verification.ingestion_storage import screening_v3_worker_sql as sv3
from verification.ingestion_storage.operational_controller import ControllerLedger, assess_retained
from verification.ingestion_storage.operational_owner import Owner
from verification.ingestion_storage.screening_v3_grant import apply_screening

V3 = ls.ScreeningRule(ls.RULE_V3, unit_threshold=10, link_related=False)
AUTH = 'INGESTION_TEST_v3'
WORKER_NAME = 'required_once'
WORKER_SQL = Path('docs/design/ingestion-operational-20261016/worker.sql')


class AnyKey:
    """Rehearsal stand-in for DatabaseBudget.slot_key (one logical slot per batch): equal to every key."""
    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False


class Budget:
    """Minimal accounting stub. The real DatabaseBudget needs the TLS/route-bound engines of the owner run and is not part of this rehearsal; everything the batch and controller code read from it is here."""
    slot_key = AnyKey()
    previous = None
    capture_checkpoint_sha256 = None


class RehearsalLedger(ControllerLedger):
    """A ControllerLedger (so the controller's isinstance gate is the real one) over rehearsal engines, without the accounted-engine requirement."""
    def __init__(self, *args, budget, **kwargs):
        self.budget = budget
        SQLLedger.__init__(self, *args, **kwargs)


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def test_screening_v3_production_connection_rehearsal(record_property, tmp_path):
    raw = os.environ.get('INGESTION_PROVISIONING_TEST_URL')
    if not raw:
        pytest.skip('fixed disposable PG17 service required')
    info = psycopg.conninfo.conninfo_to_dict(raw)
    assert (info.get('host'), info.get('port'), info.get('dbname'), info.get('user')) == ('127.0.0.1', '5432', 'ingestion_provisioning_test', 'provisioning_bootstrap')
    extra = ['ingestion_application_writer', 'ingestion_effect_broker', 'ingestion_recovery_operator', 'ingestion_effect_login', 'ingestion_recovery_login', 'operational_untrusted', 'ingestion_application_login']
    logins = ['provisioning_migrator', 'ingestion_worker_login', 'ingestion_storage_login', 'ingestion_effect_login', 'ingestion_recovery_login', 'operational_untrusted', 'ingestion_application_login']
    passwords = {r: secrets.token_urlsafe(48) for r in logins}
    timings = {}

    def connect(role):
        return psycopg.connect(**{**info, 'user': role, 'password': passwords[role]}, autocommit=True, prepare_threshold=None, connect_timeout=3)

    def engine(role):
        return create_engine(URL.create('postgresql+psycopg', username=role, password=passwords.get(role, info['password']), host='127.0.0.1', port=5432, database=info['dbname']),
                             poolclass=NullPool, connect_args={'connect_timeout': 3, 'prepare_threshold': None})
    engines = []
    with psycopg.connect(raw, autocommit=True, connect_timeout=3) as boot:
        try:
            # ------------------------------------------------------------------ fixture: the production-shaped database (original worker function installed)
            boot.execute(sql.SQL('CREATE ROLE provisioning_migrator LOGIN NOSUPERUSER NOCREATEDB CREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}').format(sql.Literal(passwords['provisioning_migrator'])))
            boot.execute('GRANT USAGE,CREATE ON SCHEMA public TO provisioning_migrator WITH GRANT OPTION')
            boot.execute('GRANT CONNECT ON DATABASE ingestion_provisioning_test TO provisioning_migrator WITH GRANT OPTION')
            with connect('provisioning_migrator') as m:
                m.execute((PACKAGE / 'install.sql').read_text())
                m.execute(WORKER_SQL.read_text())
            app = engine('provisioning_bootstrap')
            engines.append(app)
            Base.metadata.create_all(app)
            writer_sql = Path('docs/design/ingestion-operational-acceptance-20261016/application-writer.sql').read_text()
            grants = '\n'.join(line for line in writer_sql.splitlines() if not line.startswith('CREATE ROLE ')).replace(' TO ingestion_application_writer', ' TO provisioning_migrator WITH GRANT OPTION')
            boot.execute(grants)
            with connect('provisioning_migrator') as migration:
                migration.execute(writer_sql)
                migration.execute(Path('docs/design/ingestion-operational-acceptance-20261016/runtime-mappings.sql').read_text())
            for role in logins[1:]:
                if role == 'operational_untrusted':
                    boot.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}').format(sql.Identifier(role), sql.Literal(passwords[role])))
                else:
                    boot.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(role), sql.Literal(passwords[role])))
            with connect('provisioning_migrator') as migration:
                migration.execute(Path('docs/design/ingestion-operational-acceptance-20261016/activate.sql').read_text())
            boot.execute('ALTER ROLE ingestion_storage_login LOGIN')
            boot.execute('ALTER ROLE ingestion_recovery_login LOGIN')
            worker, broker = engine('ingestion_worker_login'), engine('ingestion_effect_login')
            engines.extend([worker, broker])
            with Session(app) as s:
                s.add(Council(code='bolton', name='Bolton', base_url='https://paplanning.bolton.gov.uk', date_field_mode='received', doc_system='idox'))
                s.commit()
            # the disposable fixture alone clears the consumed global stop (as the existing rehearsals do); production stops are never touched by anything in this change
            boot.execute("UPDATE public.ingestion_work_items SET outcome=jsonb_set(outcome::jsonb,'{global_stop}','null')::json WHERE key=repeat('0',64)")

            # ------------------------------------------------------------------ helpers
            owner = object.__new__(Owner)
            owner.bindings = dict(revision='r' * 40, workflow_sha256='w' * 64, manifest_sha256='m' * 64)

            def set_expiry(seconds):
                owner.expiry = owner.grant_expiry = datetime.now(timezone.utc) + timedelta(seconds=seconds)

            def insert_rows(rows):
                for row in rows:
                    boot.execute('INSERT INTO public.ingestion_work_items SELECT * FROM json_populate_record(NULL::public.ingestion_work_items,%s::json)', (json.dumps(row),))

            def put_grant(authority, grant):
                boot.execute("UPDATE public.ingestion_work_items SET outcome=jsonb_set(outcome::jsonb,ARRAY['grants',%s],%s::jsonb)::json WHERE key=repeat('0',64)", (authority, json.dumps(grant)))

            def completed(row, **fields):
                return dict(row, state='COMPLETE', phase='FINISHED', next_action='NONE', attempt_count=1, fence=1, **fields)

            columns = ('key', 'subject', 'task', 'contract', 'revision', 'state', 'phase', 'checkpoint', 'outcome', 'attempt_count', 'fence')

            def rows(where, *params):
                query = 'SELECT ' + ','.join(columns) + ' FROM public.ingestion_work_items WHERE ' + where + ' ORDER BY key'
                return [dict(zip(columns, row)) for row in boot.execute(query, params).fetchall()]

            def count(where='true'):
                return boot.execute(f'SELECT count(*) FROM public.ingestion_work_items WHERE {where}').fetchone()[0]

            def plan_for(capture_key, capture, rule):
                """batch_plans without the receipt-kind check, so an observation parent can be presented to the SQL."""
                plans, previous = [], None
                for first in range(0, len(capture['records']), 5):
                    plan = dict(capture_key=capture_key, capture_sha256=digest(capture), first=first, last=min(first + 5, len(capture['records'])))
                    if rule is not None:
                        plan['screening'] = ls.screening_plan_binding(rule)[0]
                    identity = dict(subject={'kind': 'DISCOVERY_SCOPE', 'council': capture['council'], 'start': capture['interval'][0], 'end': capture['interval'][1], 'semantics': 'RECEIVED'}, task='LISTING_METADATA', contract='listing-batch-v1', revision=digest(plan))
                    key = digest(identity)
                    plans.append(dict(identity, key=key, dependencies=sorted([capture_key] + ([previous] if previous else [])), checkpoint={'kind': 'BATCH_PLAN_V1', 'plan': plan}, max_attempts=2))
                    previous = key
                return plans

            def synthetic(tag, i):
                """A record with its own reference, so a scenario never collides with the retained world's children (the SQL refuses a conflicting duplicate, correctly)."""
                r = copy.deepcopy(receipt['records'][i])
                r['reference'] = 'SYN/%s/%d' % (tag, i)
                r['source_record_id'] = 'SYN-%s-%d' % (tag, i)
                return r

            def scenario(name, n, rule, *, kind='LISTING_RECEIPT_V1', screening_grant=True, expiry=900, authority=None, source_calls=0, tag=None, extra_grant=None):
                """A synthetic capture of the first n retained records (COMPLETE, own root), its batch items inserted as the owner's registration does, and a grant."""
                capture = dict(receipt, records=[synthetic(tag or name, i) for i in range(n)], kind=kind)
                root = item(dict(subject=dict(SCOPE, semantics='RECEIVED', start='2026-09-28', end='2026-10-04'), task='DISCOVERY', contract=CON, revision='scenario-' + name), max_attempts=1, limits=dict(DEFAULT_LIMITS, requests=10, bytes=3000000, rows=60, pages=6))
                insert_rows([completed(root, checkpoint=capture, outcome=dict(outcome='ENUMERATED_METADATA_RETAINED', children=[], source_sha256=capture['source_sha256']))])
                plans = plan_for(root['key'], capture, rule)
                batches = [item({k: p[k] for k in ('subject', 'task', 'contract', 'revision')}, dependencies=p['dependencies'], checkpoint=p['checkpoint']) for p in plans]
                if rule is None:
                    children = [item(dict(subject=dict(kind='APPLICATION', council='bolton', reference=r['reference']), task='SCREENING', contract='listing-screen-v1', revision=digest(r)), dependencies=[root['key']]) for r in capture['records']]
                else:
                    children = [item(dict(subject=dict(kind='APPLICATION', council='bolton', reference=r['reference']), task='SCREENING', contract='listing-screen-v3', revision=ls.assessment_identity(r, rule)[3]), dependencies=[root['key']]) for r in capture['records']]
                set_expiry(expiry)
                bindings, grant = owner.build_grant(batches, [root, *children], capture_key=root['key'], source_calls=source_calls, screening=rule if (rule is not None and screening_grant) else None)
                if extra_grant:
                    grant.update(extra_grant)
                authority = authority or ('INGESTION_TEST_' + name)
                insert_rows(batches)
                put_grant(authority, grant)
                ledger = RehearsalLedger(worker, owner=WORKER_NAME, authority=authority, bindings=bindings, application_engine=app, broker_engine=broker, budget=Budget())
                return dict(root=root, capture=capture, plans=plans, batches=batches, children=children, bindings=bindings, grant=grant, ledger=ledger, authority=authority)

            def message(exc):
                return str(exc.value) + ' ' + str(getattr(exc.value, 'orig', ''))

            def first_batch_row(sc, record_index=0):
                ledger = sc['ledger']
                claim = ledger.claim(sc['batches'][0]['key'], lease_seconds=165)
                plan = sc['plans'][0]['checkpoint']['plan']
                return claim, ledger.batch_row(claim, plan, sc['capture'], sc['capture']['records'][record_index])

            _, receipt = retained()
            root0, v1_children, v1_plans, v1_batches, v1_bindings = identities(receipt)

            # ------------------------------------------------------------------ phase 1: the ORIGINAL function refuses v3 (production state today)
            original_body = boot.execute(sv3.READBACK_SQL['body_sha256']).fetchone()[0]
            original_acl = boot.execute(sv3.READBACK_SQL['acl']).fetchone()[0]
            original_owner = boot.execute(sv3.READBACK_SQL['owner']).fetchone()[0]
            assert original_owner == 'ingestion_storage_owner' and set(original_acl) >= {'ingestion_effect_broker:EXECUTE', 'ingestion_worker:EXECUTE'} and not any(x.startswith('PUBLIC') for x in original_acl)
            sc = scenario('orig_v3', 2, V3)
            claim = sc['ledger'].claim(sc['batches'][0]['key'], lease_seconds=165)
            with pytest.raises(Exception) as e:
                sc['ledger'].batch_row(claim, sc['plans'][0]['checkpoint']['plan'], sc['capture'], sc['capture']['records'][0])
            assert 'BATCH_ROW_TYPES' in message(e)      # the original function cannot create a v3 child
            assert count("task='SCREENING' AND contract='listing-screen-v3'") == 0

            # ------------------------------------------------------------------ the retained world: capture, 5 v1 batches, 24 v1 children, exactly as registered and completed on 2026-10-20
            v1_rule = ls.ScreeningRule(ls.RULE_V1)
            v1_rows = []
            for c, r in zip(v1_children, receipt['records']):
                result = dict(v1_rule.screen(r), source_url=r['source_url'], source_record_id=r['source_record_id'], source_sha256=receipt['source_sha256'], proposal=r['fields']['proposal'], application_type=r['fields']['application_type'])
                v1_rows.append(completed(c, checkpoint=result, outcome=dict(outcome=result['disposition'], retained=True)))
            child_keys = [c['key'] for c in v1_children]
            insert_rows([completed(root0, checkpoint=receipt, outcome=dict(outcome='ENUMERATED_METADATA_RETAINED', children=child_keys, source_sha256=receipt['source_sha256']))])
            insert_rows(v1_rows)
            insert_rows([completed(b, checkpoint=dict(kind='BATCH_PROGRESS_V1', plan=b['checkpoint']['plan'], next=b['checkpoint']['plan']['last'], children=[c['key'] for c in v1_children[b['checkpoint']['plan']['first']:b['checkpoint']['plan']['last']]]),
                                  outcome=dict(outcome='BATCH_SCREENED', children=[])) for b in v1_batches])
            preserved = [root0['key'], *child_keys, *[b['key'] for b in v1_batches]]
            snapshot_before = {r['key']: r for r in rows("key = ANY(%s)", preserved)}
            assert len(snapshot_before) == 30 and root0['key'] == CAPTURE_KEY
            assert boot.execute("SELECT encode(sha256(convert_to(checkpoint::text,'UTF8')),'hex') IS NOT NULL FROM public.ingestion_work_items WHERE key=%s", (CAPTURE_KEY,)).fetchone()[0]

            # ------------------------------------------------------------------ phase 2: the installation ceremony (disposable only), exact readbacks, capability absence
            t = time.perf_counter()
            with connect('provisioning_migrator') as m:
                m.execute(sv3.installation_script())
            timings['installation_ceremony_seconds'] = round(time.perf_counter() - t, 3)
            derived_body = sv3.replacement_function().split('$fn$', 2)[1]
            assert boot.execute(sv3.READBACK_SQL['body_sha256']).fetchone()[0] == hashlib.sha256(derived_body.encode()).hexdigest() != original_body
            assert boot.execute(sv3.READBACK_SQL['acl']).fetchone()[0] == original_acl and boot.execute(sv3.READBACK_SQL['owner']).fetchone()[0] == original_owner      # ownership and ACL preserved
            with connect('provisioning_migrator') as m:
                assert m.execute(sv3.READBACK_SQL['capability_absent']).fetchone() == (False, False, False, False, False)      # the temporary owner capability did not remain
            for role in ('ingestion_worker_login', 'ingestion_effect_login'):
                with connect(role) as c:      # a runtime login still cannot do what only the owner can
                    with pytest.raises(psycopg.Error) as e:
                        c.execute('SET ROLE ingestion_storage_owner')
                    assert e.value.sqlstate == '42501'

            # ------------------------------------------------------------------ phase 3: default OFF and observation refusal with the replacement installed
            sc = scenario('off', 2, V3, screening_grant=False)      # a v3 plan, but a grant WITHOUT screening_configs
            claim = sc['ledger'].claim(sc['batches'][0]['key'], lease_seconds=165)
            with pytest.raises(Exception) as e:
                sc['ledger'].batch_row(claim, sc['plans'][0]['checkpoint']['plan'], sc['capture'], sc['capture']['records'][0])
            assert 'BATCH_ROW_TYPES' in message(e)
            other = ls.ScreeningRule(ls.RULE_V3, unit_threshold=11, link_related=False)
            sc = scenario('wrongcfg', 2, V3)      # screening_configs lists V3's digest; the plan carries a different configuration
            bad_plan = dict(sc['plans'][0]['checkpoint']['plan'], screening=ls.screening_plan_binding(other)[0])
            # a plan the batch item does not hold is refused as not exact; to present a bad binding the SQL itself must judge, register a batch item that carries it
            bad_batch = item(dict(subject=sc['plans'][0]['subject'], task='LISTING_METADATA', contract='listing-batch-v1', revision=digest(bad_plan)), dependencies=sc['plans'][0]['dependencies'], checkpoint=dict(kind='BATCH_PLAN_V1', plan=bad_plan))
            insert_rows([bad_batch])
            bad_bindings, bad_grant = owner.build_grant([bad_batch], [sc['root']], capture_key=sc['root']['key'], source_calls=0, screening=V3)
            put_grant('INGESTION_TEST_wrongcfg2', bad_grant)
            ledger = RehearsalLedger(worker, owner=WORKER_NAME, authority='INGESTION_TEST_wrongcfg2', bindings=bad_bindings, application_engine=app, broker_engine=broker, budget=Budget())
            claim = ledger.claim(bad_batch['key'], lease_seconds=165)
            with pytest.raises(Exception) as e:
                ledger.batch_row(claim, bad_plan, sc['capture'], sc['capture']['records'][0])
            assert 'BATCH_ROW_TYPES' in message(e)      # the configuration is not on the grant's list
            obs = scenario('obs', 2, V3, kind='LISTING_OBSERVATION_V1')
            claim = obs['ledger'].claim(obs['batches'][0]['key'], lease_seconds=165)
            with pytest.raises(Exception) as e:
                obs['ledger'].batch_row(claim, obs['plans'][0]['checkpoint']['plan'], obs['capture'], obs['capture']['records'][0])
            assert 'CAPTURE_BINDING' in message(e) or 'BATCH_ROW_TYPES' in message(e)      # an observation parent never parents a v3 child
            assert count("task='SCREENING' AND contract='listing-screen-v3'") == 0

            # ------------------------------------------------------------------ phase 3b: the SQL's own defences, by direct calls with hand-built payloads (a consistent Python client never presents these)
            def canonical(x):
                return json.dumps(x, sort_keys=True, separators=(',', ':'), allow_nan=False)

            def raw_batch_row(ledger, claim, plan, capture, record, contract, revision):
                identity = dict(subject={'kind': 'APPLICATION', 'council': capture['council'], 'reference': record['reference']}, task='SCREENING', contract=contract, revision=revision)
                row = ledger.get(claim.key)
                child = dict(identity, key=digest(identity), dependencies=[plan['capture_key']], priority=row['priority'], max_attempts=2, limits=row['limits'])
                with ledger.broker_engine.begin() as c:
                    ledger._limits(c)
                    return ledger._step('batch_row', claim.key, claim.fence, dict(child=child, plan_json=canonical(plan), capture_json=canonical(capture), record_json=canonical(record), identity_json=canonical(identity)), connection=c)

            sc = scenario('craft', 2, V3)
            claim = sc['ledger'].claim(sc['batches'][0]['key'], lease_seconds=165)
            plan, capture, record = sc['plans'][0]['checkpoint']['plan'], sc['capture'], sc['capture']['records'][0]
            good_revision = ls.assessment_identity(record, V3)[3]
            with pytest.raises(Exception) as e:
                raw_batch_row(sc['ledger'], claim, plan, capture, record, 'listing-screen-v1', digest(record))      # a v1-contract child under a v3 plan
            assert 'BATCH_ROW_TYPES' in message(e)
            with pytest.raises(Exception) as e:
                raw_batch_row(sc['ledger'], claim, plan, capture, record, 'listing-screen-v3', digest(record))      # a v3 child carrying the plain record digest
            assert 'BATCH_ROW_IDENTITY' in message(e)
            with pytest.raises(Exception) as e:
                raw_batch_row(sc['ledger'], claim, plan, capture, record, 'listing-screen-v3', digest(dict(record_sha256=digest(record), config_sha256='2' * 64)))      # right shape, another configuration
            assert 'BATCH_ROW_IDENTITY' in message(e)
            sc1 = scenario('craft1', 2, None)
            claim1 = sc1['ledger'].claim(sc1['batches'][0]['key'], lease_seconds=165)
            with pytest.raises(Exception) as e:
                raw_batch_row(sc1['ledger'], claim1, sc1['plans'][0]['checkpoint']['plan'], sc1['capture'], sc1['capture']['records'][0], 'listing-screen-v3', good_revision)      # a v3 child under a plan with no screening binding
            assert 'BATCH_ROW_TYPES' in message(e)
            _, listed = ls.screening_plan_binding(V3)
            for label, binding in (('extra_key', dict(contract='listing-screen-v3', config_sha256=listed, extra=1)), ('bad_hex', dict(contract='listing-screen-v3', config_sha256='Z' * 64)),
                                   ('null', None), ('wrong_contract', dict(contract='listing-screen-v1', config_sha256=listed))):
                base = scenario('craft_' + label, 2, V3)
                bad_plan = dict(base['plans'][0]['checkpoint']['plan'], screening=binding)
                bad_batch = item(dict(subject=base['plans'][0]['subject'], task='LISTING_METADATA', contract='listing-batch-v1', revision=digest(bad_plan)), dependencies=base['plans'][0]['dependencies'], checkpoint=dict(kind='BATCH_PLAN_V1', plan=bad_plan))
                insert_rows([bad_batch])
                bindings_bad, grant_bad = owner.build_grant([bad_batch], [base['root']], capture_key=base['root']['key'], source_calls=0, screening=V3)
                put_grant('INGESTION_TEST_craft_' + label + '2', grant_bad)
                led = RehearsalLedger(worker, owner=WORKER_NAME, authority='INGESTION_TEST_craft_' + label + '2', bindings=bindings_bad, application_engine=app, broker_engine=broker, budget=Budget())
                cl = led.claim(bad_batch['key'], lease_seconds=165)
                with pytest.raises(Exception) as e:
                    raw_batch_row(led, cl, bad_plan, base['capture'], base['capture']['records'][0], 'listing-screen-v3', good_revision)
                assert 'BATCH_ROW_TYPES' in message(e), label      # a malformed or foreign screening binding creates nothing
            assert count("task='SCREENING' AND contract='listing-screen-v3'") == 0

            # an observation parent with specification 034's substitutions applied (installed here, disposable only): 034 admits the parent for v1, the v3 clause still refuses it
            variant = sv3.replacement_function()
            for old, new in SPEC034:
                assert variant.count(old) == 1
                variant = variant.replace(old, new)
            with connect('provisioning_migrator') as m:
                m.execute(sv3.CEREMONY_OPEN + variant + '\n' + sv3.CEREMONY_CLOSE)
            obs_extra = {'observation_councils': ['bolton']}
            ov1 = scenario('obs034v1', 2, None, kind='LISTING_OBSERVATION_V1', extra_grant=obs_extra)
            cl = ov1['ledger'].claim(ov1['batches'][0]['key'], lease_seconds=165)
            created, _ = ov1['ledger'].batch_row(cl, ov1['plans'][0]['checkpoint']['plan'], ov1['capture'], ov1['capture']['records'][0])
            assert rows("key=%s", created)[0]['contract'] == 'listing-screen-v1'      # control: with 034 applied an observation parent DOES parent a v1 child
            ov3 = scenario('obs034v3', 2, V3, kind='LISTING_OBSERVATION_V1', extra_grant=obs_extra)
            cl = ov3['ledger'].claim(ov3['batches'][0]['key'], lease_seconds=165)
            with pytest.raises(Exception) as e:
                ov3['ledger'].batch_row(cl, ov3['plans'][0]['checkpoint']['plan'], ov3['capture'], ov3['capture']['records'][0])
            assert 'BATCH_ROW_TYPES' in message(e)      # and the same parent can never parent a v3 child
            with connect('provisioning_migrator') as m:
                m.execute(sv3.installation_script())      # back to the v3 replacement alone
            assert boot.execute(sv3.READBACK_SQL['body_sha256']).fetchone()[0] == hashlib.sha256(derived_body.encode()).hexdigest()
            assert count("task='SCREENING' AND contract='listing-screen-v3'") == 0

            # ------------------------------------------------------------------ phase 4: v1 compatibility, duplicates, stripped/malformed receipts, expiry, recovery
            sc = scenario('v1compat', 3, None)
            claim, (key1, progress) = first_batch_row(sc)
            expected = sc['children'][0]
            assert key1 == expected['key'] and progress['next'] == 1      # the replacement creates the historical v1 child with the historical identity
            row = rows("key=%s", key1)[0]
            assert row['contract'] == 'listing-screen-v1' and row['revision'] == digest(sc['capture']['records'][0])
            sc3 = scenario('dup', 3, V3)
            claim, (key3, progress) = first_batch_row(sc3)
            child = rows("key=%s", key3)[0]
            assert child['contract'] == 'listing-screen-v3' and child['revision'] == ls.assessment_identity(sc3['capture']['records'][0], V3)[3] and child['revision'] != key3
            before = count("task='SCREENING'")
            with pytest.raises(Exception) as e:      # replaying row 0 on the same claim: the batch has moved on, so the supplied record is not the next one
                sc3['ledger'].batch_row(claim, sc3['plans'][0]['checkpoint']['plan'], sc3['capture'], sc3['capture']['records'][0])
            assert 'BATCH_ROW_IDENTITY' in message(e) and count("task='SCREENING'") == before
            dup = scenario('dup2', 3, V3, tag='dup')      # the same record under the same configuration, presented from a different capture parent
            dup_claim = dup['ledger'].claim(dup['batches'][0]['key'], lease_seconds=165)
            with pytest.raises(Exception) as e:
                dup['ledger'].batch_row(dup_claim, dup['plans'][0]['checkpoint']['plan'], dup['capture'], dup['capture']['records'][0])
            assert 'CONFLICTING_DUPLICATE' in message(e) and count("task='SCREENING'") == before      # never a second row, never a silent merge
            # a stripped or malformed v3 receipt is refused by SQL at checkpoint; a mismatching outcome at completion
            claim_child = None
            ledger3 = sc3['ledger']
            cc = ledger3.claim(key3, lease_seconds=165)
            good = V3.screen(sc3['capture']['records'][0])
            record_sha, config, config_sha, revision = ls.assessment_identity(sc3['capture']['records'][0], V3)
            payload = dict(good, record_sha256=record_sha, config=config, config_sha256=config_sha, assessment_revision=revision)
            for label, bad in (('no_authority', {k: v for k, v in payload.items() if k != 'routing_authority'}), ('no_rule_version', {k: v for k, v in payload.items() if k != 'rule_version'}),
                               ('no_assessment', {k: v for k, v in payload.items() if k != 'count_assessment'}), ('bad_admission', dict(payload, count_assessment=dict(payload['count_assessment'], admission='ADMITTED'))),
                               ('wrong_revision', dict(payload, assessment_revision='0' * 64)), ('stripped_config', {k: v for k, v in payload.items() if k != 'config_sha256'}),
                               ('other_config', dict(payload, config_sha256='1' * 64)), ('v1_shape', {k: v for k, v in payload.items() if k not in ('routing_authority', 'count_assessment', 'config_sha256')})):
                with pytest.raises(Exception) as e:
                    ledger3.checkpoint(cc, bad)
                assert 'SCREENING_V3_RECEIPT' in message(e), label
            ledger3.checkpoint(cc, payload)      # the genuine receipt is accepted
            with pytest.raises(Exception) as e:
                ledger3.finish(cc, dict(outcome='ADMIT_SCHEME' if good['count_assessment']['admission'] != 'ADMIT_SCHEME' else 'RETAIN_BELOW_THRESHOLD', retained=True))
            assert 'SCREENING_V3_OUTCOME' in message(e)
            ledger3.finish(cc, dict(outcome=good['count_assessment']['admission'], retained=True))
            assert rows("key=%s", key3)[0]['state'] == 'COMPLETE'
            # authority expiry: the grant lapses between operations
            sc4 = scenario('expiry', 2, V3)
            claim = sc4['ledger'].claim(sc4['batches'][0]['key'], lease_seconds=165)
            boot.execute("UPDATE public.ingestion_work_items SET outcome=jsonb_set(outcome::jsonb,ARRAY['grants',%s,'expires_at'],to_jsonb(extract(epoch FROM clock_timestamp())-1))::json WHERE key=repeat('0',64)", (sc4['authority'],))
            with pytest.raises(Exception) as e:
                sc4['ledger'].batch_row(claim, sc4['plans'][0]['checkpoint']['plan'], sc4['capture'], sc4['capture']['records'][0])
            assert 'EXACT_AUTHORITY_BINDING_REQUIRED' in message(e)
            assert count("task='SCREENING' AND subject::jsonb->>'reference'=%s AND contract='listing-screen-v3' AND dependencies::text LIKE %s" % ("'" + sc4['capture']['records'][0]['reference'] + "'", "'%" + sc4['root']['key'] + "%'")) == 0      # nothing was created after expiry
            # failure cleanup: a worker dies after materialising one row; recovery preserves progress, no duplicates
            sc5 = scenario('recover', 3, V3)
            claim, (k5, progress) = first_batch_row(sc5)
            boot.execute('UPDATE public.ingestion_work_items SET lease_until=0 WHERE key=%s', (sc5['batches'][0]['key'],))
            with connect('ingestion_recovery_login') as recovery:
                recovered = recovery.execute('SELECT public.ingestion_recover_abandoned(%s,%s,true)', (sc5['batches'][0]['key'], claim.fence)).fetchone()[0]
            assert recovered['state'] == 'DEFERRED' and recovered['checkpoint']['children'] == [k5]      # progress retained, nothing lost
            assert count("key=%s" % ("'" + k5 + "'")) == 1

            # ------------------------------------------------------------------ phase 5: the demonstration shape - the verified full retained capture, source-free, through the real controller path
            t = time.perf_counter()
            plans3 = batching.batch_plans(CAPTURE_KEY, receipt, V3)
            batches3 = [item({k: p[k] for k in ('subject', 'task', 'contract', 'revision')}, dependencies=p['dependencies'], checkpoint=p['checkpoint']) for p in plans3]
            children3 = [item(dict(subject=dict(kind='APPLICATION', council='bolton', reference=r['reference']), task='SCREENING', contract='listing-screen-v3', revision=ls.assessment_identity(r, V3)[3]), dependencies=[CAPTURE_KEY]) for r in receipt['records']]
            read_only = [root0, *v1_children, *v1_batches]      # named among the bindings so they can be READ (the capture and the earlier assessments); a binding is not a new permission: all are COMPLETE, so the existing claim/fence checks refuse any change
            set_expiry(900)      # the proposed authority lifetime
            bindings3, grant3 = owner.build_grant(batches3, [*read_only, *children3], capture_key=CAPTURE_KEY, source_calls=0, screening=V3)
            assert len(bindings3) == 59 and len(grant3['keys']) <= 74 and grant3['source_calls'] == 0 and grant3['writes'] == 0 and grant3['screening_configs'] == [digest(V3.config())]
            insert_rows(batches3)
            put_grant(AUTH, grant3)
            timings['registration_seconds'] = round(time.perf_counter() - t, 3)
            ledger = RehearsalLedger(worker, owner=WORKER_NAME, authority=AUTH, bindings=bindings3, application_engine=app, broker_engine=broker, budget=Budget())
            co = Coordinator(ledger, {}, screening_rules={ls.V3_CONTRACT: V3})
            per_batch = []
            original_process = batching.process_batch

            def timed(coordinator, key, **kw):
                started = time.perf_counter()
                try:
                    return original_process(coordinator, key, **kw)
                finally:
                    per_batch.append(round(time.perf_counter() - started, 3))
            batching.process_batch = timed
            try:
                t = time.perf_counter()
                result = assess_retained(co, CAPTURE_KEY, capture_sha256=CAPTURE_CHECKPOINT, batch_keys=[b['key'] for b in batches3], preserved_keys=preserved[1:])      # the 24 v1 children and 5 v1 batches
                timings['assessment_total_seconds'] = round(time.perf_counter() - t, 3)
            finally:
                batching.process_batch = original_process
            timings['per_batch_seconds'] = per_batch
            assert result['outcome'] == 'SCREENING_V3_ASSESSED' and result['application_writes'] == 0 and result['source_calls'] == 0 and len(result['assessments']) == 24 and len(per_batch) == 5
            routed = {}
            for a in result['assessments']:
                routed[a['admission']] = routed.get(a['admission'], 0) + 1
            assert routed == dict(RETAIN_NOT_RESIDENTIAL_SUPPLY=16, ROUTE_COUNT_UNCONFIRMED=4, RETAIN_RELATED_TO_PARENT=2, ADMIT_SCHEME=1, RETAIN_BELOW_THRESHOLD=1)      # a rehearsal result on the retained capture, not a production result
            assert [a['reference'] for a in result['assessments'] if a['eligible']] == ['01768/26']
            # preservation: every earlier row, including the capture, is byte-for-byte what it was
            assert {r['key']: r for r in rows("key = ANY(%s)", preserved)} == snapshot_before
            # exact effects: 24 new v3 children, no source intent anywhere, nothing in the application database
            assert count("task='SCREENING' AND contract='listing-screen-v3' AND dependencies::text LIKE %s" % ("'%" + CAPTURE_KEY + "%'")) == 24
            assert count("phase='SOURCE_INTENT' OR phase='WRITE_INTENT'") == 0
            attempts = boot.execute("SELECT count(*) FROM public.ingestion_work_attempts WHERE work_key = ANY(%s)", ([b['key'] for b in batches3] + [c['key'] for c in children3],)).fetchone()[0]
            assert attempts == 29      # one claim per item, far inside the 58 allowed by max_attempts
            with Session(app) as s:
                assert s.scalar(select(func.count()).select_from(Application)) == 0
            control = json.loads(boot.execute("SELECT outcome::text FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0])
            assert control['grants'][AUTH]['source_calls'] == 0 and control['grants'][AUTH]['writes'] == 0      # the allowances were never consumed
            timings['attempts_created'] = attempts
            timings['items_created'] = 5 + 24

            # ------------------------------------------------------------------ phase 6: bounded history over the real table
            subject = dict(kind='APPLICATION', council='bolton', reference='01768/26')
            record_sha = digest(next(r for r in receipt['records'] if r['reference'] == '01768/26'))
            page1 = sh.history_page(worker, subject, record_sha, page_size=1)
            page2 = sh.history_page(worker, subject, record_sha, cursor=page1['next_cursor'], page_size=1)
            keys = [i['key'] for i in page1['items'] + page2['items']]
            assert len(keys) == 2 and len(set(keys)) == 2 and keys == sorted(keys) and page2['next_cursor'] is None      # one v1 and one v3 assessment of the same record, no skip, no duplicate
            assert {i['contract'] for i in page1['items'] + page2['items']} == {'listing-screen-v1', 'listing-screen-v3'} and all(i['record_sha256'] == record_sha for i in page1['items'] + page2['items'])
            timings['history_page_size_1_pages'] = 2
            # mixed v1/v3 pagination over more than one page of matches in PostgreSQL (synthetic matches, fixture only)
            many = []
            fake_subject = dict(kind='APPLICATION', council='bolton', reference='HIST/1')
            fake_record = sha('hist-record')
            for i in range(130):
                base = item(dict(subject=fake_subject, task='SCREENING', contract='listing-screen-v1' if i == 0 else 'listing-screen-v3', revision=fake_record if i == 0 else sha('rev%d' % i)), dependencies=[sha('hist-parent')])
                many.append(completed(base, checkpoint=None if i == 0 else {'rule_version': ls.RULE_V3, 'record_sha256': fake_record, 'config_sha256': sha('cfg%d' % i)}, outcome=dict(outcome='X', retained=True)))
            many.append(completed(item(dict(subject=fake_subject, task='SCREENING', contract='listing-screen-v3', revision=sha('queued')), dependencies=[sha('hist-parent')]), checkpoint=None))      # unscreened: not listed
            insert_rows(many)
            seen, cursor, pages = [], None, 0
            started = time.perf_counter()
            while True:
                page = sh.history_page(worker, fake_subject, fake_record, cursor=cursor)
                pages += 1
                seen += [i['key'] for i in page['items']]
                cursor = page['next_cursor']
                if cursor is None:
                    break
            timings['history_130_matches_pages'] = pages
            timings['history_130_matches_seconds'] = round(time.perf_counter() - started, 3)
            expected_keys = sorted(r['key'] for r in many[:130])
            assert seen == expected_keys and pages == 6 and len(sh.history_page(worker, fake_subject, fake_record, page_size=500)['items']) == 50

            # ------------------------------------------------------------------ phase 7: invalidation, rollback ceremony, evidence preserved
            boot.execute("UPDATE public.ingestion_work_items SET outcome=jsonb_set(outcome::jsonb,ARRAY['grants',%s,'expires_at'],'0'::jsonb)::json WHERE key=repeat('0',64)", (AUTH,))
            with pytest.raises(Exception):
                ledger.claim(batches3[0]['key'], lease_seconds=165)      # an invalidated authority claims nothing
            with connect('provisioning_migrator') as m:
                m.execute(sv3.rollback_script())
            assert boot.execute(sv3.READBACK_SQL['body_sha256']).fetchone()[0] == original_body      # byte-for-byte the original function again
            assert boot.execute(sv3.READBACK_SQL['acl']).fetchone()[0] == original_acl and boot.execute(sv3.READBACK_SQL['owner']).fetchone()[0] == original_owner
            with connect('provisioning_migrator') as m:
                assert m.execute(sv3.READBACK_SQL['capability_absent']).fetchone() == (False, False, False, False, False)
            assert count("task='SCREENING' AND contract='listing-screen-v3' AND dependencies::text LIKE %s" % ("'%" + CAPTURE_KEY + "%'")) == 24      # the v3 assessments are preserved, inert
            assert len(sh.history_page(worker, subject, record_sha)['items']) == 2      # and still readable with the v1-only function installed
            sc6 = scenario('after_rollback', 2, V3)
            claim = sc6['ledger'].claim(sc6['batches'][0]['key'], lease_seconds=165)
            with pytest.raises(Exception) as e:
                sc6['ledger'].batch_row(claim, sc6['plans'][0]['checkpoint']['plan'], sc6['capture'], sc6['capture']['records'][0])
            assert 'BATCH_ROW_TYPES' in message(e)      # v3 is disabled again
            timings['note'] = 'rehearsal figures only: they exclude TLS and connection set-up and the real DatabaseBudget accounting; the retained production screening slots took 9.2-10.7 s of supervised elapsed time each'
            for key, value in timings.items():
                record_property(key, json.dumps(value))
            print('V3_REHEARSAL_TIMINGS ' + json.dumps(timings, sort_keys=True))
            if os.environ.get('V3_REHEARSAL_TIMINGS'):
                Path(os.environ['V3_REHEARSAL_TIMINGS']).write_text(json.dumps(timings, indent=1, sort_keys=True))
        finally:
            for e in engines:
                e.dispose()
            boot.execute('DROP TABLE IF EXISTS public.ingestion_work_attempts CASCADE')
            boot.execute('DROP TABLE IF EXISTS public.ingestion_work_items CASCADE')
            for e in engines:
                if e.url.username == 'provisioning_bootstrap':
                    Base.metadata.drop_all(e)
                    e.dispose()
            for role in [*extra, *ROLES, 'provisioning_migrator']:
                if boot.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
                    boot.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(role)))
            for role in [*extra, *ROLES, 'provisioning_migrator']:
                boot.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(role)))
