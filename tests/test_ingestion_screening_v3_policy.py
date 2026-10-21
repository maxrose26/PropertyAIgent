"""Policy v6 (one named, screening-only allowance for the retained Bolton capture) and the two new owner inventory states. Offline: static derivation and inventory checks. The behaviour on a real PostgreSQL is in
test_discovery_ingestion_screening_v3_policy_pg.py. Nothing here installs or registers anything."""
import re
from pathlib import Path

import pytest

pytest.importorskip('resource')      # the owner module imports the Linux-only `resource` module (CI is Linux)

from app.ingestion import listing_screening as ls
from app.ingestion.batching import batch_plans
from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage import policy_screening_v3 as p
from verification.ingestion_storage import screening_v3_worker_sql as sv3
from tests.test_ingestion_retained_capture_reconciliation import CAPTURE_KEY, identities, item, retained

ROOT = Path(__file__).resolve().parents[1]
V3 = ls.ScreeningRule(ls.RULE_V3, unit_threshold=10, link_related=False)


def text_of(path):
    return Path(ROOT / path).read_bytes().decode('utf-8').replace('\r\n', '\n')


def test_the_committed_v6_body_is_the_mechanical_derivation_of_v5():
    v5 = p.v5_text()
    assert text_of(p.POLICY_FILE) == p.derive(v5)      # regenerate and require byte equality
    v6 = text_of(p.POLICY_FILE)
    assert v6[v6.index('BEGIN;'):].count('CREATE OR REPLACE FUNCTION') == 2      # exactly the two policy functions
    assert sorted(re.findall(r'CREATE OR REPLACE FUNCTION public\.(\w+)', v6)) == ['ingestion_bolton_allowed', 'ingestion_register_bolton_exception']
    body5, body6 = v5[v5.index('BEGIN;'):], v6[v6.index('BEGIN;'):]
    removed = [line for line in body5.split('\n') if line not in body6.split('\n')]
    assert 1 <= len(removed) <= 5      # v6 extends the scope list and the cap-exemption lines of v5 in place; the stop and baseline predicates and the exact check are inserted; no other v5 line is removed
    assert all('sc:=CASE WHEN a IN' in line or 'hard_stop_generation' in line or 'stop_checkpoint_sha256' in line or 'manual_stop' in line for line in removed)


def test_v6_adds_one_name_and_no_general_mechanism():
    v6 = text_of(p.POLICY_FILE)
    assert not re.search(r"LIKE|~\s*'.*AUTHORISE|authority\s+~", v6)      # no pattern matching on names
    assert v6.count("a = '%s'" % p.NAME) == 3 and v6.count("authority = '%s'" % p.NAME) == 1      # exactly the four sites: scope is a list entry, the other three are equality tests
    assert ">=3 AND NOT" in v6 or ")>=3 AND NOT" in v6      # the cap of three is unchanged
    assert 'EXACT_SCREENING_V3_ALLOWANCE' in v6 and p.CAPTURE_KEY in v6 and 'source_calls' in v6
    assert p.NAME.endswith('_SCREEN') and 'CAPTURE' not in p.NAME.replace('RETAINED_WINDOW', '')      # screening only, never a capture name
    assert p.G3_SHA in v6 and "'IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE'" in v6      # the reviewed stop baseline, nothing more permissive


def test_the_exact_grant_check_matches_what_the_owner_builds_for_the_retained_world():
    _, receipt = retained()
    root, children, plans, batches, bindings = identities(receipt)
    assert root['key'] == p.CAPTURE_KEY == CAPTURE_KEY
    owner = object.__new__(oo.Owner)
    owner.expiry = owner.grant_expiry = __import__('datetime').datetime(2026, 10, 30, tzinfo=__import__('datetime').timezone.utc)
    owner.bindings = dict(revision='r' * 40, workflow_sha256='w' * 64, manifest_sha256='m' * 64)
    batches3 = [item({k: q[k] for k in ('subject', 'task', 'contract', 'revision')}, dependencies=q['dependencies'], checkpoint=q['checkpoint']) for q in batch_plans(CAPTURE_KEY, receipt, V3)]
    children3 = [item(dict(subject=c['subject'], task='SCREENING', contract='listing-screen-v3', revision=ls.assessment_identity(r, V3)[3]), dependencies=[CAPTURE_KEY]) for c, r in zip(children, receipt['records'])]
    read_only = [root, *children, *batches]
    _, grant = owner.build_grant(batches3, [*read_only, *children3], capture_key=CAPTURE_KEY, source_calls=0, screening=V3)
    assert len(grant['keys']) == p.EXPECTED_KEYS and grant['contracts'] == p.EXPECTED_CONTRACTS and grant['capture_key'] == p.CAPTURE_KEY
    assert len(grant['screening_configs']) == 1 and grant['source_calls'] == 0 and grant['writes'] == 0
    by = {}
    for b in grant['bindings'].values():
        by[(b['task'], b['contract'])] = by.get((b['task'], b['contract']), 0) + 1
    assert by == {('DISCOVERY', 'bolton-received-idox-coordinator-v1'): 1, ('LISTING_METADATA', 'listing-batch-v1'): 10, ('SCREENING', 'listing-screen-v1'): 24, ('SCREENING', 'listing-screen-v3'): 24}


def test_the_two_new_inventory_states_differ_from_their_predecessors_in_exactly_the_reviewed_functions():
    window, policy, full = oo.Owner.window_inventory(), oo.Owner.screening_v3_policy_inventory(), oo.Owner.screening_v3_inventory()
    assert sorted(k for k in policy if policy[k] != window[k]) == ['ingestion_bolton_allowed', 'ingestion_register_bolton_exception']
    assert sorted(k for k in full if full[k] != policy[k]) == ['ingestion_worker_step']
    assert full['ingestion_worker_step'] == sv3.replacement_function().split('$fn$', 2)[1]
    assert set(window) == set(policy) == set(full)
    # a policy-only or function-only state is not a recognised state: installation is policy first, then function
    original = oo.Owner.reviewed_inventories(True)[0]['ORIGINAL']
    mixed = {**window, 'ingestion_worker_step': full['ingestion_worker_step']}
    assert all(mixed != inv for inv in (window, policy, full, original))


def test_the_new_states_are_known_to_verification_and_bound_to_generation_3_and_only_the_screening_v3_modes_select_them():
    source = text_of('verification/ingestion_storage/operational_owner.py')
    assert "'GENERATION3_SCREENING_V3_POLICY_APPLIED':self.screening_v3_policy_inventory()" in source and "'GENERATION3_SCREENING_V3_APPLIED':self.screening_v3_inventory()" in source
    assert "'GENERATION3_SCREENING_V3_POLICY_APPLIED','GENERATION3_SCREENING_V3_APPLIED')" in source      # generation 3
    runner = text_of('verification/ingestion_storage/operational_runner.py')
    assert runner.count("permitted_policy_states=('GENERATION3_SCREENING_V3_APPLIED',)") == 2      # the execution mode's construction and the installation mode's final verification: nothing else selects the final state
    assert runner.count("permitted_policy_states=('GENERATION3_SCREENING_V3_POLICY_APPLIED',)") == 1      # the installation mode's intermediate verification
    assert 'if self.sv3_mode:' in runner and 'if self.sv3_policy_mode:' in runner
