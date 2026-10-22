"""Policy v6 (ONE named, screening-only allowance for the retained Bolton capture) on a REAL disposable PostgreSQL 17 with the real installed ledger, the reviewed successor policy and then v3, v4 and v5 exactly as in
production. Verifies: the one name registers in the exact generation-3 stop state for the exact retained scope and the exact retained-world grant, and nothing else is admitted; the cap holds for every other name; a refused
registration leaves nothing behind; re-registration is impossible; history is untouched; only two function definitions change; the owner's two new inventory states equal what installation actually produces; and
rollback restores the previous inventory byte for byte. Loopback only. Nothing is installed anywhere but the disposable database."""
import copy
import json
import time
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from app.ingestion import listing_screening as ls
from app.ingestion.batching import batch_plans
from tests.test_discovery_ingestion_policy_generation2_pg import (ledger, payload, register, allowed, function_fingerprints, memberships, IDOX, STOP1_SHA, STOP2_SHA, BINDING, NAMED as PROBE)      # noqa: F401  (ledger is a fixture)
from tests.test_discovery_ingestion_window_allowance_policy_pg import generation3_exhausted, apply_v5, window_grant, CAP, SCR, G3, WEEK
from tests.test_discovery_ingestion_capture_allowance_policy_pg import CAP as OLDCAP
from tests.test_ingestion_retained_capture_reconciliation import CAPTURE_KEY, identities, item, retained
from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage import policy_screening_v3 as p
from verification.ingestion_storage import screening_v3_worker_sql as sv3

V3 = ls.ScreeningRule(ls.RULE_V3, unit_threshold=10, link_related=False)
NAME = p.NAME


def apply_v6(installer):
    with installer.connection() as c:
        installer.script(c, p.POLICY_FILE)


def apply_text(installer, tmp_path, text, name):
    path = tmp_path / name
    path.write_text(text)
    with installer.connection() as c:
        installer.script(c, path)


def insert_root(boot, *, state='COMPLETE', kind='LISTING_RECEIPT_V1'):
    _, receipt = retained()
    root = identities(receipt)[0]
    row = dict(root, state=state, phase='FINISHED', next_action='NONE', attempt_count=1, fence=1, checkpoint=dict(receipt, kind=kind), outcome=dict(outcome='ENUMERATED_METADATA_RETAINED', children=[], source_sha256=receipt['source_sha256']))
    boot.execute('INSERT INTO public.ingestion_work_items SELECT * FROM json_populate_record(NULL::public.ingestion_work_items,%s::json)', (json.dumps(row),))


def screening_grant():
    """The grant the owner would register for the retained assessment (59 bound keys), built by the real Owner.build_grant."""
    _, receipt = retained()
    root, children, _, batches, _ = identities(receipt)
    owner = object.__new__(oo.Owner)
    owner.expiry = owner.grant_expiry = datetime.now(timezone.utc) + timedelta(seconds=900)
    owner.bindings = dict(BINDING)
    batches3 = [item({k: q[k] for k in ('subject', 'task', 'contract', 'revision')}, dependencies=q['dependencies'], checkpoint=q['checkpoint']) for q in batch_plans(CAPTURE_KEY, receipt, V3)]
    children3 = [item(dict(subject=c['subject'], task='SCREENING', contract='listing-screen-v3', revision=ls.assessment_identity(r, V3)[3]), dependencies=[CAPTURE_KEY]) for c, r in zip(children, receipt['records'])]
    _, grant = owner.build_grant(batches3, [root, *children, *batches, *children3], capture_key=CAPTURE_KEY, source_calls=0, screening=V3)
    return grant


def put(control, set_control, grant, name=NAME):
    ctl = control()
    ctl['grants'][name] = grant
    set_control(ctl)


def production_now(boot, connector, installer, control, set_control):
    """The state production is in: v5 installed, the two window names registered and revoked (consumed), generation 3 untouched."""
    generation3_exhausted(boot, connector, installer, control, set_control)
    apply_v5(installer)
    for name, revision, calls in ((CAP, '7' * 64, 1), (SCR, '6' * 64, 0)):
        grant = window_grant(boot, control, set_control, name=name, revision=revision, calls=calls)
        register(boot, payload(grant, name=name, generation=3, sha=G3))
        ctl = control()
        ctl['grants'][name]['expires_at'] = 0
        ctl['bolton_exceptions'][name]['expires_at'] = 0
        set_control(ctl)
    assert len(control()['bolton_exceptions']) == 6 and control()['hard_stop_generation'] == 3
    return control()


def test_under_v5_the_new_name_is_refused(ledger):
    boot, connector, installer, control, set_control = ledger
    production_now(boot, connector, installer, control, set_control)
    insert_root(boot)
    grant = screening_grant()
    put(control, set_control, grant)
    with pytest.raises(psycopg.errors.Error, match='EXACT_SCOPED_DISPOSITION'):
        register(boot, payload(grant, name=NAME, generation=3, sha=G3))


def test_v6_registers_exactly_the_one_named_screening_only_allowance_and_touches_nothing_else(ledger):
    boot, connector, installer, control, set_control = ledger
    before = production_now(boot, connector, installer, control, set_control)
    before_fn, before_members = function_fingerprints(boot), memberships(boot)
    apply_v6(installer)
    after_fn = function_fingerprints(boot)
    assert sorted(k for k in before_fn if before_fn[k] != after_fn.get(k)) == ['ingestion_bolton_allowed', 'ingestion_register_bolton_exception'] and set(before_fn) == set(after_fn)
    assert memberships(boot) == before_members and control() == before      # installing the policy changes no record
    insert_root(boot)
    grant = screening_grant()
    put(control, set_control, grant)
    exception = register(boot, payload(grant, name=NAME, generation=3, sha=G3))
    assert exception['authority'] == NAME and exception['hard_stop_generation'] == 3
    ctl = control()
    assert allowed(boot, ctl, NAME) is True and len(ctl['bolton_exceptions']) == 7
    assert ctl['hard_stop_generation'] == 3 and ctl['manual_stop'] == IDOX and ctl['last_hard_stop'] == IDOX and ctl['global_stop'] == before['global_stop']      # stops and generation untouched
    for name in ('HISTORICAL_0', 'HISTORICAL_1', PROBE, OLDCAP, CAP, SCR):      # every historical and consumed entry is byte-identical
        assert ctl['bolton_exceptions'][name] == before['bolton_exceptions'][name] and ctl['grants'][name] == before['grants'][name]
        assert allowed(boot, ctl, name) is False      # and still dead
    with pytest.raises(psycopg.errors.Error, match='EXACT_SCOPED_DISPOSITION'):
        register(boot, payload(grant, name=NAME, generation=3, sha=G3))      # a name that exists can never be registered again


def refused(boot, control, set_control, mutate, *, root=None, match='EXACT_SCREENING_V3_ALLOWANCE'):
    insert_root(boot, **(root or {}))
    grant = screening_grant()
    mutate(grant)
    put(control, set_control, grant)
    with pytest.raises(psycopg.errors.Error, match=match):
        register(boot, payload(grant, name=NAME, generation=3, sha=G3))
    assert NAME not in control().get('bolton_exceptions', {})      # a refused registration leaves nothing behind


def drop_child_v3(grant):
    key = next(k for k, v in grant['bindings'].items() if v['contract'] == 'listing-screen-v3')
    grant['bindings'].pop(key)
    grant['keys'].remove(key)


def add_binding(grant):
    grant['bindings']['f' * 64] = dict(grant['bindings'][grant['keys'][0]])
    grant['keys'] = sorted(grant['keys'] + ['f' * 64])


MUTATIONS = {
    'source_calls': lambda g: g.__setitem__('source_calls', 1),
    'writes': lambda g: g.__setitem__('writes', 1),
    'no_configuration': lambda g: g.__setitem__('screening_configs', []),
    'two_configurations': lambda g: g.__setitem__('screening_configs', g['screening_configs'] + ['9' * 64]),
    'configuration_not_a_list': lambda g: g.__setitem__('screening_configs', 'x'),
    'one_key_fewer': drop_child_v3,
    'one_key_more': add_binding,
    'contract_missing': lambda g: g.__setitem__('contracts', [c for c in g['contracts'] if c != 'listing-screen-v1']),
    'contract_extra': lambda g: g.__setitem__('contracts', sorted(g['contracts'] + ['listing-screen-v9'])),
}


@pytest.mark.parametrize('label', sorted(MUTATIONS))
def test_v6_refuses_any_grant_that_is_not_exactly_the_retained_screening_world(ledger, label):
    boot, connector, installer, control, set_control = ledger
    production_now(boot, connector, installer, control, set_control)
    apply_v6(installer)
    refused(boot, control, set_control, MUTATIONS[label])


@pytest.mark.parametrize('root', [dict(state='QUEUED'), dict(kind='LISTING_OBSERVATION_V1')], ids=['root_not_complete', 'root_is_an_observation'])
def test_v6_refuses_a_root_that_is_not_a_complete_receipt(ledger, root):
    boot, connector, installer, control, set_control = ledger
    production_now(boot, connector, installer, control, set_control)
    apply_v6(installer)
    refused(boot, control, set_control, lambda g: None, root=root)


def test_v6_refuses_another_capture_and_a_missing_capture(ledger):
    boot, connector, installer, control, set_control = ledger
    production_now(boot, connector, installer, control, set_control)
    apply_v6(installer)
    grant = screening_grant()
    grant['capture_key'] = '0' * 64      # a capture that does not exist
    put(control, set_control, grant)
    with pytest.raises(psycopg.errors.Error):
        register(boot, payload(grant, name=NAME, generation=3, sha=G3))
    assert NAME not in control()['bolton_exceptions']
    other = window_grant(boot, control, set_control, name=NAME, revision='5' * 64, calls=0)      # a window-shaped capture root of the right scope but not THE retained capture
    other['screening_configs'] = ['1' * 64]
    put(control, set_control, other)
    with pytest.raises(psycopg.errors.Error, match='EXACT_SCREENING_V3_ALLOWANCE'):
        register(boot, payload(other, name=NAME, generation=3, sha=G3))


@pytest.mark.parametrize('state', ['generation_2', 'generation_4', 'generation_1', 'other_manual_stop', 'other_last_hard_stop', 'absent_manual_stop', 'absent_generation', 'absent_last_hard_stop', 'wrong_digest', 'generation_2_digest'])
def test_v6_refuses_the_name_in_any_stop_state_but_the_exact_generation_3_one(ledger, state):
    boot, connector, installer, control, set_control = ledger
    production_now(boot, connector, installer, control, set_control)
    apply_v6(installer)
    ctl = control()
    sha, generation = G3, 3
    if state == 'generation_2':
        ctl['hard_stop_generation'], generation, sha = 2, 2, STOP2_SHA
    if state == 'generation_4':
        ctl['hard_stop_generation'] = 4
    if state == 'generation_1':
        ctl['hard_stop_generation'], generation, sha = 1, 1, STOP1_SHA
    if state == 'other_manual_stop':
        ctl['manual_stop'] = 'SOMETHING_ELSE'
    if state == 'other_last_hard_stop':
        ctl['last_hard_stop'] = 'SOMETHING_ELSE'
    if state == 'absent_manual_stop':
        ctl.pop('manual_stop')
    if state == 'absent_generation':
        ctl.pop('hard_stop_generation')
    if state == 'absent_last_hard_stop':
        ctl.pop('last_hard_stop')
    if state == 'wrong_digest':
        sha = '0' * 64
    if state == 'generation_2_digest':
        sha = STOP2_SHA
    set_control(ctl)
    insert_root(boot)
    grant = screening_grant()
    put(control, set_control, grant)
    with pytest.raises(psycopg.errors.Error, match='EXACT_SCOPED_DISPOSITION'):
        register(boot, payload(grant, name=NAME, generation=generation, sha=sha))
    assert NAME not in control()['bolton_exceptions']


def test_v6_does_not_widen_the_cap_or_the_scope_for_any_other_name(ledger):
    boot, connector, installer, control, set_control = ledger
    production_now(boot, connector, installer, control, set_control)
    apply_v6(installer)
    grant = window_grant(boot, control, set_control, name='SOME_OTHER_ALLOWANCE', revision='4' * 64)
    with pytest.raises(psycopg.errors.Error, match='EXACT_SCOPED_DISPOSITION'):
        register(boot, payload(grant, name='SOME_OTHER_ALLOWANCE', generation=3, sha=G3))      # the cap is still exhausted for every other name
    ctl = control()
    ctl['bolton_exceptions'].clear()      # room under the cap: still refused by the stop predicate
    set_control(ctl)
    with pytest.raises(psycopg.errors.Error, match='EXACT_SCOPED_DISPOSITION'):
        register(boot, payload(grant, name='SOME_OTHER_ALLOWANCE', generation=3, sha=G3))


def test_v6_honours_the_exception_only_while_it_is_unexpired_and_the_state_is_exact(ledger):
    boot, connector, installer, control, set_control = ledger
    production_now(boot, connector, installer, control, set_control)
    apply_v6(installer)
    insert_root(boot)
    grant = screening_grant()
    put(control, set_control, grant)
    register(boot, payload(grant, name=NAME, generation=3, sha=G3))
    ctl = control()
    assert allowed(boot, ctl, NAME) is True
    ctl['bolton_exceptions'][NAME]['expires_at'] = 0
    assert allowed(boot, ctl, NAME) is False      # invalidated
    ctl = control()
    ctl['grants'][NAME]['expires_at'] = 0
    assert allowed(boot, ctl, NAME) is False
    ctl = control()
    ctl['hard_stop_generation'] = 4
    assert allowed(boot, ctl, NAME) is False      # a newer stop admits nothing
    ctl = control()
    ctl['manual_stop'] = 'SOMETHING_ELSE'
    assert allowed(boot, ctl, NAME) is False


def test_the_owner_inventory_states_equal_what_installation_produces_and_rollback_restores_the_previous_one(ledger, tmp_path):
    boot, connector, installer, control, set_control = ledger
    production_now(boot, connector, installer, control, set_control)
    names = sorted(oo.Owner.window_inventory())

    def installed():
        return {n: body for n, body in boot.execute("SELECT p.proname,p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname=ANY(%s)", (names,)).fetchall()}
    assert installed() == oo.Owner.window_inventory()      # production today
    apply_v6(installer)
    assert installed() == oo.Owner.screening_v3_policy_inventory()      # GENERATION3_SCREENING_V3_POLICY_APPLIED
    apply_text(installer, tmp_path, sv3.installation_script(), 'install_worker.sql')
    assert installed() == oo.Owner.screening_v3_inventory()      # GENERATION3_SCREENING_V3_APPLIED
    before_rows = boot.execute('SELECT count(*) FROM public.ingestion_work_items').fetchone()[0]
    apply_text(installer, tmp_path, sv3.rollback_script(), 'rollback_worker.sql')
    assert installed() == oo.Owner.screening_v3_policy_inventory()      # the function rolled back first
    apply_text(installer, tmp_path, p.v5_text()[p.v5_text().index('BEGIN;'):], 'rollback_policy.sql')
    assert installed() == oo.Owner.window_inventory()      # then the policy: the previous reviewed inventory, byte for byte
    assert boot.execute('SELECT count(*) FROM public.ingestion_work_items').fetchone()[0] == before_rows      # the ceremonies change no row
    with installer.connection() as c:      # the migration identity (not the bootstrap superuser) holds no transient owner capability after the ceremonies
        assert tuple(installer.q(c, sv3.READBACK_SQL['capability_absent'])[0]) == (False, False, False, False, False)
