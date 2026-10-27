"""Offline unit proof for connecting the owner/runner tooling to the integrated chain: scope bindings, limit reconciliation, owner grant preparation and genuine outer-supervisor evidence.

No database server, no network, no council. Nothing here issues, registers or runs live authority. The integrated chain through restricted PostgreSQL roles is `test_e2e_connection_pg.py`;
a unit test is never reported as admission proof, and synthetic fixtures qualify no real council markup.
"""
import copy
import json
import time
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.ingestion.coordinator import validate_outer
from app.ingestion.ledger import DEFAULT_LIMITS, Denied, digest
from app.ingestion.listing_screening import RULE_V3, ScreeningRule
from app.ingestion.nomination import derive_nominees
from tests.e2e_connection_support import (TEST_QUALIFICATION, arcus_audit, arcus_contract, arcus_detail_target, arcus_slot_supervised, entry, idox_audit, idox_contract, idox_detail_target,
                                          idox_supervised, outer)
from tests.test_e2e_connection_units import ALL, END, RULE, START, archived
from verification.discovery.outer_evidence import KEYS, observe_group, outer_from_slot_receipt, outer_supervisor
from verification.ingestion_storage import operational_owner
from verification.ingestion_storage.chain_registration import authority_name, capture_registration, chain_registration
from verification.ingestion_storage.limit_reconciliation import BROWSER_SOURCE_V2_ITEM_LIMITS, layers, reconcile, reconcile_items, required_grant_seconds
from verification.ingestion_storage.operational_owner import Owner, item
from verification.ingestion_storage.scope_binding import CHAIN_BINDINGS, MAX_WINDOW_DAYS, ScopeBinding, binding_for, check_contract, check_detail_target, scope_for

OWNER_BINDINGS = dict(revision='a' * 40, workflow_sha256='b' * 64, manifest_sha256='c' * 64)
S, E = START.isoformat(), END.isoformat()
FAMILIES = [('idox', 'tameside'), ('arcus', 'manchester')]


def owner(ttl=1800):
    return Owner(None, lambda *_: None, lambda: None, expiry=datetime.fromtimestamp(time.time() + ttl, timezone.utc), bindings=dict(OWNER_BINDINGS))


def limits_for(binding):
    return BROWSER_SOURCE_V2_ITEM_LIMITS if binding.execution_budget else DEFAULT_LIMITS


def contract_and_audit(family, council):
    binding = binding_for(council)
    if family == 'idox':
        return idox_contract(council, START, END), idox_audit(council, ALL, START, END)
    return arcus_contract(council, START, END, budget=binding.execution_budget), arcus_audit(council, ALL, START, END, budget=binding.execution_budget)


def rooted(cap, receipt):
    """The root row as the owner would read it back after the capture: with the saved capture as its checkpoint."""
    return dict(cap.rows[0], checkpoint=receipt)


def prepared(family, council, tmp_path, *, ttl=1800):
    """(binding, contract, capture registration, saved receipt, nominees, targets) for one family, all through the production preparation."""
    binding = binding_for(council)
    contract, audit = contract_and_audit(family, council)
    reg = capture_registration(owner(), binding, contract, S, E, revision='unit', item_limits=limits_for(binding))
    receipt = archived(contract.project(audit, outer(), limits_for(binding)), audit, tmp_path)
    receipt.pop('window', None)
    nominees = derive_nominees([receipt], RULE, allow_test_evidence=True)
    make = idox_detail_target if family == 'idox' else arcus_detail_target
    targets = {r['reference']: make(council, r) for r in receipt['records']}
    return binding, contract, reg, receipt, nominees, targets


# ------------------------------------------------------------------------------------------------------------------ scope bindings
def test_the_registry_is_closed_and_each_binding_matches_the_platform_configuration():
    assert set(CHAIN_BINDINGS) == {'tameside','manchester','bury','oldham','stockport'}
    for council in CHAIN_BINDINGS:
        assert binding_for(council) == CHAIN_BINDINGS[council]
    assert binding_for('tameside').semantics == 'RECEIVED' and binding_for('manchester').semantics == 'VALIDATED'
    assert binding_for('manchester').execution_budget == 'BROWSER_SOURCE_V2' and binding_for('tameside').execution_budget is None


@pytest.mark.parametrize('council,code', [('bolton', 'SCOPE_HISTORICAL_ONLY'), ('rochdale', 'SCOPE_ROCHDALE_INITIAL_STATUS_UNQUALIFIED'), ('salford', 'SCOPE_NOT_BOUND'),
                                          ('wigan','SCOPE_NOT_BOUND'), ('nowhere', 'SCOPE_NOT_BOUND'), ('', 'SCOPE_NOT_BOUND')])
def test_unbound_historical_and_unqualified_councils_are_refused_with_the_exact_reason(council, code):
    with pytest.raises(Denied) as exc:
        binding_for(council)
    assert str(exc.value) == code


def test_historical_bolton_constants_are_untouched():
    assert operational_owner.SCOPE == dict(kind='DISCOVERY_SCOPE', council='bolton', start='2026-10-16', end='2026-10-16', semantics='RECEIVED')
    assert operational_owner.WINDOW_SCOPE == dict(kind='DISCOVERY_SCOPE', council='bolton', start='2026-09-28', end='2026-10-04', semantics='RECEIVED')


@pytest.mark.parametrize('start,end', [('2026-11-15', '2026-11-09'), ('2026-11-09', '2026-11-16'), ('2026-13-01', '2026-13-02'), ('2026/11/09', '2026-11-12'), (20261109, '2026-11-12'), (None, None),
                                       ('2026-11-09 ', '2026-11-12')])
def test_a_window_must_be_an_ordered_iso_range_of_at_most_seven_days(start, end):
    with pytest.raises(Denied, match='SCOPE_WINDOW'):
        scope_for(binding_for('tameside'), start, end)
    assert MAX_WINDOW_DAYS == 7


def test_a_forged_binding_is_not_a_binding():
    forged = replace(binding_for('tameside'), semantics='VALIDATED')
    with pytest.raises(Denied, match='SCOPE_NOT_BOUND'):
        scope_for(forged, S, E)
    with pytest.raises(Denied, match='SCOPE_NOT_BOUND'):
        scope_for(ScopeBinding('bolton', 'idox', 'RECEIVED', 'IDOX_REQUESTS', None, 'accepted_idox_new_identity'), S, E)


def test_a_contract_must_be_the_families_own_for_exactly_this_scope_and_budget():
    tame, manc = binding_for('tameside'), binding_for('manchester')
    assert check_contract(tame, idox_contract('tameside', START, END), S, E) == scope_for(tame, S, E)
    assert check_contract(manc, arcus_contract('manchester', START, END, budget='BROWSER_SOURCE_V2'), S, E)['semantics'] == 'VALIDATED'
    with pytest.raises(Denied, match='SCOPE_CONTRACT_MISMATCH'):
        check_contract(tame, arcus_contract('manchester', START, END, budget='BROWSER_SOURCE_V2'), S, E)      # wrong family
    with pytest.raises(Denied, match='SCOPE_CONTRACT_MISMATCH'):
        check_contract(tame, idox_contract('oldham', START, END), S, E)      # another council
    with pytest.raises(Denied, match='SCOPE_CONTRACT_MISMATCH'):
        check_contract(tame, idox_contract('tameside', START, END), S, '2026-11-14')      # another window
    with pytest.raises(Denied, match='SCOPE_BUDGET_MISMATCH'):
        check_contract(manc, arcus_contract('manchester', START, END), S, E)      # no declared budget
    with pytest.raises(Denied, match='SCOPE_CONTRACT_MISMATCH'):
        check_contract(manc, arcus_contract('rochdale', START, END, budget='BROWSER_SOURCE_V2'), S, E)


@pytest.mark.parametrize('change', [dict(council='bury'), dict(reference='OTHER/1/26'), dict(source_url='https://example.invalid/x'), dict(source_identifier='K999')])
def test_a_detail_target_must_name_exactly_the_nominated_record(change):
    binding = binding_for('tameside')
    record = dict(reference='E2E/1/26', source_url='https://u/1', source_record_id='K1')
    target = idox_detail_target('tameside', record)
    assert check_detail_target(binding, record, target) is target
    with pytest.raises(Denied, match='SCOPE_DETAIL_TARGET_MISMATCH'):
        check_detail_target(binding, record, dict(target, **change))
    with pytest.raises(Denied, match='SCOPE_DETAIL_TARGET_MISMATCH'):
        check_detail_target(binding, record, None)


# ------------------------------------------------------------------------------------------------------------ limit reconciliation
def test_default_ledger_limits_are_compatible_with_the_historical_envelope_and_the_reviewed_v2_limits_with_v2():
    assert reconcile_items(binding_for('tameside'), DEFAULT_LIMITS)['supervisor'] == dict(source_deadline_seconds=45, controller_deadline_seconds=165)
    layered = reconcile_items(binding_for('manchester'), BROWSER_SOURCE_V2_ITEM_LIMITS)
    assert layered['reader']['worker_seconds'] == 75 and layered['reader']['source_outer_seconds'] == 80
    assert layered['supervisor'] == dict(source_deadline_seconds=80, slot_active_seconds=90, source_memory_bytes=1536 * 1024 ** 2)
    assert layered['ledger']['worker_seconds'] == 75 and layered['ledger']['outer_seconds'] == 90


def test_the_v2_budget_with_default_ledger_limits_is_refused_naming_every_violated_field_and_changes_nothing():
    limits = dict(DEFAULT_LIMITS)
    with pytest.raises(Denied) as exc:
        reconcile_items(binding_for('manchester'), limits)
    assert str(exc.value) == 'LIMIT_INCOMPATIBLE:ledger.worker_seconds,ledger.outer_seconds,ledger.source_rss,ledger.item_limits_not_reviewed'
    assert limits == DEFAULT_LIMITS      # nothing was raised, clamped or substituted


@pytest.mark.parametrize('field,value', [('worker_seconds', 74), ('outer_seconds', 80), ('source_rss', 1536 * 1024 ** 2 - 1), ('aggregate_rss', 1536 * 1024 ** 2 - 1)])
def test_each_ledger_limit_is_checked_at_its_exact_boundary(field, value):
    with pytest.raises(Denied, match='ledger.' + field):
        reconcile_items(binding_for('manchester'), dict(BROWSER_SOURCE_V2_ITEM_LIMITS, **{field: value}))


def test_a_browser_budget_cannot_be_selected_for_the_requests_supervisor():
    forged = ScopeBinding('tameside', 'idox', 'RECEIVED', 'IDOX_REQUESTS', 'BROWSER_SOURCE_V2', 'accepted_idox_new_identity')
    with pytest.raises(Denied, match='reader.execution_budget_not_supported_by_supervisor'):
        reconcile_items(forged, DEFAULT_LIMITS)


def test_the_grant_lifetime_must_cover_the_worst_case_sequential_work_and_not_exceed_the_sql_cap():
    binding = binding_for('manchester')
    need = required_grant_seconds(binding, batches=2, nominees=2)
    assert need == 90 + 165 * 4
    assert reconcile(binding, BROWSER_SOURCE_V2_ITEM_LIMITS, lifetime_seconds=need, batches=2, nominees=2)['grant']['maximum_seconds'] == 86400
    for lifetime in (need - 1, 0, -5, 86401, None, 'x'):
        with pytest.raises(Denied, match='grant.lifetime_seconds'):
            reconcile(binding, BROWSER_SOURCE_V2_ITEM_LIMITS, lifetime_seconds=lifetime, batches=2, nominees=2)


def test_the_layers_record_states_which_limit_applies_where():
    record = layers(binding_for('tameside'), DEFAULT_LIMITS, lifetime_seconds=900)
    assert set(record) == {'reader', 'supervisor', 'ledger', 'grant'} and record['grant']['lifetime_seconds'] == 900


# --------------------------------------------------------------------------------------------------------------- owner grant preparation
def test_the_historical_owner_grant_is_byte_identical():
    """`build_grant` gained default-off parameters; a call that passes none produces exactly the grant the historical ceremonies produced (digests pinned from before the change)."""
    when = datetime(2030, 1, 1, tzinfo=timezone.utc)
    o = Owner(None, lambda *a: None, lambda: None, expiry=when, bindings=dict(OWNER_BINDINGS))
    root = item(dict(subject=dict(kind='DISCOVERY_SCOPE', council='bolton', start='2026-10-16', end='2026-10-16', semantics='RECEIVED'), task='DISCOVERY', contract='c', revision='r'))
    bindings, grant = o.build_grant([root], [], capture_key=root['key'], source_calls=3)
    assert digest(grant) == '6b4c9809db11ce36c753ac8e876e06fc768b771333160b865c8e3464bf081185' and digest(bindings) == 'd9fd3b41be72292ac9869a9507941ccb4614fe80ca15003574a1c2e715570ed7'
    _, v3 = o.build_grant([root], [], capture_key=root['key'], source_calls=3, screening=ScreeningRule(RULE_V3, unit_threshold=10, link_related=False))
    assert digest(v3) == '5435bc9d7d5b877abe2550c9c639f625416cbd4950b2dc0ff004bb38a226f929'
    assert grant['writes'] == 0 and grant['detail_source_keys'] == []


@pytest.mark.parametrize('family,council', FAMILIES)
def test_the_capture_registration_is_exactly_one_scope_and_spends_no_source_call(family, council):
    binding = binding_for(council)
    contract, _ = contract_and_audit(family, council)
    reg = capture_registration(owner(), binding, contract, S, E, revision='unit', item_limits=limits_for(binding))
    root = reg.rows[0]
    assert reg.kind == 'CAPTURE' and reg.insert == [root] and root['subject'] == scope_for(binding, S, E) and root['task'] == 'DISCOVERY' and root['limits'] == limits_for(binding)
    g = reg.grant
    assert g['keys'] == [root['key']] and g['contracts'] == [contract.name] and g['capture_key'] == root['key'] and g['source_calls'] == 0 and g['writes'] == 0
    assert g['capture_only'] is False and g['completion_outcomes']['DISCOVERY'] == ['ENUMERATED_METADATA_RETAINED'] and g['execution_binding'] == OWNER_BINDINGS and g['workers'] == ['required_once']
    assert reg.authority == authority_name(binding, 'CAPTURE', 'unit') and reg.authority.startswith('INGESTION_CHAIN_') and len(reg.authority) <= 100


def test_a_capture_registration_with_an_incompatible_selection_is_refused_before_anything_is_prepared():
    binding = binding_for('manchester')
    contract, _ = contract_and_audit('arcus', 'manchester')
    with pytest.raises(Denied, match='LIMIT_INCOMPATIBLE'):
        capture_registration(owner(), binding, contract, S, E, revision='unit', item_limits=DEFAULT_LIMITS)
    with pytest.raises(Denied, match='SCOPE_BUDGET_MISMATCH'):
        capture_registration(owner(), binding, arcus_contract('manchester', START, END), S, E, revision='unit', item_limits=BROWSER_SOURCE_V2_ITEM_LIMITS)
    with pytest.raises(Denied, match='SCOPE_CONTRACT_MISMATCH'):
        capture_registration(owner(), binding_for('tameside'), contract, S, E, revision='unit', item_limits=DEFAULT_LIMITS)


@pytest.mark.parametrize('family,council', FAMILIES)
def test_the_chain_registration_derives_every_key_counter_and_outcome_from_the_capture_and_nominees(family, council, tmp_path):
    binding, contract, cap, receipt, nominees, targets = prepared(family, council, tmp_path)
    reg = chain_registration(owner(), binding, contract, rooted(cap, receipt), receipt, nominees.nominees, RULE, targets, revision='unit', item_limits=limits_for(binding), allow_test_evidence=True)
    n = len(nominees.nominees)
    assert n == 2 and reg.kind == 'CHAIN' and len(reg.batches) == 2 and len(reg.screens) == 6 and len(reg.facts) == 2
    g = reg.grant
    assert g['source_calls'] == n and g['writes'] == 2 * n and g['capture_key'] == cap.root_key and g['capture_only'] is False
    assert g['detail_source_keys'] == sorted(f['key'] for f in reg.facts.values())
    assert set(g['keys']) == {r['key'] for r in reg.rows} == set(g['bindings']) and set(reg.bindings) == set(g['keys'])
    assert [r['key'] for r in reg.insert] == [r['key'] for r in [*reg.batches, *reg.facts.values()]]      # the root is already registered; screening children are created by the batch step
    assert g['completion_outcomes']['FACTUAL_REFRESH'] == ['SUPPORTED_FACTS_VERIFIED', 'ALREADY_KNOWN'] and 'ADMIT_SCHEME' in g['completion_outcomes']['SCREENING']
    assert len(g['screening_configs']) == 1
    assert {r['limits']['worker_seconds'] for r in reg.rows} == {limits_for(binding)['worker_seconds']}
    assert reg.authority == authority_name(binding, 'CHAIN', 'unit') != cap.authority
    again = chain_registration(owner(), binding, contract, rooted(cap, receipt), receipt, nominees.nominees, RULE, targets, revision='unit', item_limits=limits_for(binding), allow_test_evidence=True)
    assert [r['key'] for r in again.rows] == [r['key'] for r in reg.rows]      # deterministic: the same inputs give the same keys


@pytest.mark.parametrize('family,council', FAMILIES)
def test_the_chain_registration_refuses_foreign_underived_or_mistargeted_inputs(family, council, tmp_path):
    binding, contract, cap, receipt, nominees, targets = prepared(family, council, tmp_path)
    kw = dict(revision='unit', item_limits=limits_for(binding), allow_test_evidence=True)
    root = rooted(cap, receipt)

    def go(**override):
        args = dict(owner=owner(), binding=binding, contract=contract, root=root, receipt=receipt, nominees=nominees.nominees, rule=RULE, detail_targets=targets)
        args.update(override)
        return chain_registration(args['owner'], args['binding'], args['contract'], args['root'], args['receipt'], args['nominees'], args['rule'], args['detail_targets'], **kw)
    assert go().kind == 'CHAIN'
    with pytest.raises(Denied, match='CHAIN_FOREIGN_CAPTURE'):
        go(root=dict(root, subject=dict(root['subject'], council='bury')))
    with pytest.raises(Denied, match='CHAIN_FOREIGN_CAPTURE'):
        go(receipt=dict(receipt, council='bury'))
    with pytest.raises(Denied, match='CHAIN_NOMINEES_NOT_DERIVED'):
        go(nominees=nominees.nominees[:1])      # a subset is not what the capture yields
    with pytest.raises(Denied, match='CHAIN_NOMINEES_NOT_DERIVED'):
        go(nominees=tuple(reversed(nominees.nominees)) if len(nominees.nominees) > 1 else ())
    with pytest.raises(Denied, match='CHAIN_NOMINEES_NOT_DERIVED'):
        go(nominees=(*nominees.nominees, replace(nominees.nominees[0], reference='E2E/9/26')))
    with pytest.raises(Denied, match='SCOPE_DETAIL_TARGET_MISMATCH'):
        go(detail_targets=dict(targets, **{nominees.nominees[0].reference: dict(targets[nominees.nominees[0].reference], source_url='https://example.invalid/other')}))
    with pytest.raises(Denied, match='SCOPE_DETAIL_TARGET_MISMATCH'):
        go(detail_targets={})
    with pytest.raises(Denied, match='TEST_EVIDENCE_NOT_LIVE'):
        chain_registration(owner(), binding, contract, dict(root, checkpoint=dict(receipt, evidence_label='TEST_ARCHIVE_NOT_LIVE_EVIDENCE')), dict(receipt, evidence_label='TEST_ARCHIVE_NOT_LIVE_EVIDENCE'), nominees.nominees, RULE, targets, revision='unit', item_limits=limits_for(binding),
                           )      # labelled receipt, no opt-in


def test_the_chain_registration_refuses_limits_that_do_not_fit_the_selected_budget(tmp_path):
    binding, contract, cap, receipt, nominees, targets = prepared('arcus', 'manchester', tmp_path)
    with pytest.raises(Denied, match='LIMIT_INCOMPATIBLE:ledger.worker_seconds,ledger.outer_seconds,ledger.source_rss,ledger.item_limits_not_reviewed'):
        chain_registration(owner(), binding, contract, rooted(cap, receipt), receipt, nominees.nominees, RULE, targets, revision='unit', item_limits=DEFAULT_LIMITS, allow_test_evidence=True)


@pytest.mark.parametrize('family,council', FAMILIES)
def test_an_expired_or_too_short_authority_is_refused_at_preparation(family, council, tmp_path):
    binding, contract, cap, receipt, nominees, targets = prepared(family, council, tmp_path)
    need = required_grant_seconds(binding, batches=2, nominees=2)
    for ttl in (-5, 0, need - 60):
        with pytest.raises(Denied, match='grant.lifetime_seconds'):
            chain_registration(owner(ttl), binding, contract, rooted(cap, receipt), receipt, nominees.nominees, RULE, targets, revision='unit', item_limits=limits_for(binding), allow_test_evidence=True)
    assert chain_registration(owner(need + 60), binding, contract, rooted(cap, receipt), receipt, nominees.nominees, RULE, targets, revision='unit', item_limits=limits_for(binding),
                              allow_test_evidence=True).kind == 'CHAIN'


def test_another_council_cannot_borrow_a_registration(tmp_path):
    binding, contract, cap, receipt, nominees, targets = prepared('idox', 'tameside', tmp_path)
    (tmp_path / 'other').mkdir()
    other_binding, other_contract, other_cap, *_ = prepared('arcus', 'manchester', tmp_path / 'other')
    assert cap.authority != other_cap.authority and cap.root_key != other_cap.root_key
    with pytest.raises(Denied, match='CHAIN_FOREIGN_CAPTURE'):
        chain_registration(owner(), other_binding, other_contract, rooted(cap, receipt), receipt, nominees.nominees, RULE, targets, revision='unit', item_limits=limits_for(other_binding),
                           allow_test_evidence=True)


# ------------------------------------------------------------------------------------------------- genuine outer-supervisor evidence
def group(tmp_path, *, peak='4096\n', procs=''):
    d = tmp_path / 'g'
    d.mkdir()
    if peak is not None:
        (d / 'memory.peak').write_text(peak)
    if procs is not None:
        (d / 'cgroup.procs').write_text(procs)
    return d


CLOSED = dict(source_group_closed=True, child_reaped=True, failures=[])


def test_observe_group_reads_only_what_is_there(tmp_path):
    assert observe_group(group(tmp_path)) == (4096, 0)
    assert observe_group(tmp_path / 'absent') == (None, None)


@pytest.mark.parametrize('peak,procs,expected', [('x\n', '', (None, 0)), ('-1\n', '', (None, 0)), ('4096\n', '12\n34\n', (4096, 2)), (None, '', (None, 0)), ('4096\n', None, (4096, None))])
def test_unreadable_or_odd_group_files_become_missing_observations_never_defaults(tmp_path, peak, procs, expected):
    assert observe_group(group(tmp_path, peak=peak, procs=procs)) == expected


def test_a_fully_observed_closed_slot_is_the_only_closed_outer_object():
    good = outer_supervisor(exit_code=0, elapsed_seconds=3.5, closure=CLOSED, peak_owned_rss=4096, live_owned_survivors=0, deadline_seconds=80)
    assert set(good) == set(KEYS) and good['cleanup'] == 'CLOSED' and good['limit_hit'] is None and good['expired'] is False
    validate_outer(good, DEFAULT_LIMITS)
    bad = {
        'missing_peak': dict(exit_code=0, elapsed_seconds=3, closure=CLOSED, peak_owned_rss=None, live_owned_survivors=0, deadline_seconds=80),
        'missing_survivors': dict(exit_code=0, elapsed_seconds=3, closure=CLOSED, peak_owned_rss=1, live_owned_survivors=None, deadline_seconds=80),
        'missing_exit': dict(exit_code=None, elapsed_seconds=3, closure=CLOSED, peak_owned_rss=1, live_owned_survivors=0, deadline_seconds=80),
        'survivor': dict(exit_code=0, elapsed_seconds=3, closure=CLOSED, peak_owned_rss=1, live_owned_survivors=1, deadline_seconds=80),
        'group_open': dict(exit_code=0, elapsed_seconds=3, closure=dict(CLOSED, source_group_closed=False), peak_owned_rss=1, live_owned_survivors=0, deadline_seconds=80),
        'not_reaped': dict(exit_code=0, elapsed_seconds=3, closure=dict(CLOSED, child_reaped=False), peak_owned_rss=1, live_owned_survivors=0, deadline_seconds=80),
        'cleanup_failure': dict(exit_code=0, elapsed_seconds=3, closure=dict(CLOSED, failures=[{'code': 'X'}]), peak_owned_rss=1, live_owned_survivors=0, deadline_seconds=80),
        'deadline': dict(exit_code=0, elapsed_seconds=80, closure=CLOSED, peak_owned_rss=1, live_owned_survivors=0, deadline_seconds=80),
        'nonzero_exit': dict(exit_code=1, elapsed_seconds=3, closure=CLOSED, peak_owned_rss=1, live_owned_survivors=0, deadline_seconds=80),
    }
    for name, kwargs in bad.items():
        built = outer_supervisor(**kwargs)
        assert (built['cleanup'] == 'CLOSED') == (name in {'deadline', 'nonzero_exit'}), name      # those two close cleanly and are refused for exit code / deadline
        with pytest.raises(Denied, match='OUTER_SAFETY'):
            validate_outer(built, DEFAULT_LIMITS)
    assert outer_supervisor(**bad['missing_peak'])['cleanup'] == 'UNKNOWN' and outer_supervisor(**bad['survivor'])['cleanup'] == 'FAILED'


def test_a_real_v2_slot_yields_observed_evidence_that_the_ledger_accepts(tmp_path):
    scope = scope_for(binding_for('manchester'), S, E)
    _, audit = contract_and_audit('arcus', 'manchester')
    source, got, receipt = arcus_slot_supervised(tmp_path, audit, scope)
    assert source == audit and got == receipt['outer_supervisor'] and 'outer_supervisor' not in receipt['owned_cleanup']
    assert got['cleanup'] == 'CLOSED' and got['exit_code'] == 0 and got['peak_owned_rss'] == 123456789 and got['live_owned_survivors'] == 0 and got['deadline_seconds'] == 80
    assert 0 <= got['elapsed_seconds'] < 80 and got['evidence'] == 'SOURCE_CGROUP_READBACK'
    validate_outer(got, BROWSER_SOURCE_V2_ITEM_LIMITS)
    with pytest.raises(Denied, match='OUTER_SAFETY'):
        validate_outer(got, DEFAULT_LIMITS | {'outer_seconds': 0})


def test_a_surviving_group_member_or_unreadable_peak_is_never_reported_closed(tmp_path):
    scope = scope_for(binding_for('manchester'), S, E)
    _, audit = contract_and_audit('arcus', 'manchester')
    (tmp_path / 'a').mkdir()
    _, survivor, _ = arcus_slot_supervised(tmp_path / 'a', audit, scope, mode='member')
    assert survivor['live_owned_survivors'] == 1 and survivor['cleanup'] == 'FAILED'
    with pytest.raises(Denied, match='OUTER_SAFETY'):
        validate_outer(survivor, BROWSER_SOURCE_V2_ITEM_LIMITS)
    (tmp_path / 'b').mkdir()
    _, unknown, _ = arcus_slot_supervised(tmp_path / 'b', audit, scope, peak_text='not a number')
    assert unknown['peak_owned_rss'] is None and unknown['cleanup'] == 'UNKNOWN'
    with pytest.raises(Denied, match='OUTER_SAFETY'):
        validate_outer(unknown, BROWSER_SOURCE_V2_ITEM_LIMITS)


def test_a_failed_source_child_produces_no_outer_object_and_no_success(tmp_path):
    from verification.discovery.four_council_release import SourceFailure
    scope = scope_for(binding_for('manchester'), S, E)
    _, audit = contract_and_audit('arcus', 'manchester')
    with pytest.raises(SourceFailure) as exc:
        arcus_slot_supervised(tmp_path, audit, scope, mode='exit1')
    assert 'outer_supervisor' not in exc.value.closure and exc.value.closure.get('worker_exit') is not None


def test_historical_release_versions_keep_their_slot_receipt_shape(tmp_path):
    from verification.discovery.four_council_release import SUCCESSOR_VERSION, VERSION
    scope = scope_for(binding_for('manchester'), S, E)
    _, audit = contract_and_audit('arcus', 'manchester')
    for n, version in enumerate((VERSION, SUCCESSOR_VERSION)):
        (tmp_path / str(n)).mkdir()
        with pytest.raises(ValueError, match='OUTER_EVIDENCE_ABSENT_OR_UNBOUND'):
            arcus_slot_supervised(tmp_path / str(n), audit, scope, version=version)      # the receipt is built, carries no outer object, and is refused as outer evidence
    from verification.discovery import four_council_release as r
    assert r.VERSION_LIMITS[r.VERSION].get('execution_budget') is None and r.VERSION_LIMITS[r.SUCCESSOR_VERSION].get('execution_budget') is None


def test_a_slot_receipt_is_only_outer_evidence_for_the_source_it_describes(tmp_path):
    scope = scope_for(binding_for('manchester'), S, E)
    _, audit = contract_and_audit('arcus', 'manchester')
    _, _, receipt = arcus_slot_supervised(tmp_path, audit, scope)
    other = copy.deepcopy(audit)
    other['requests'] += 1
    for bad_receipt, bad_audit in ((receipt, other), ({k: v for k, v in receipt.items() if k != 'outer_supervisor'}, audit), (dict(receipt, outer_supervisor=dict(receipt['outer_supervisor'], extra=1)), audit),
                                   (dict(receipt, outer_supervisor=dict(receipt['outer_supervisor'], evidence='ASSUMED')), audit), (None, audit)):
        with pytest.raises(ValueError, match='OUTER_EVIDENCE_ABSENT_OR_UNBOUND'):
            outer_from_slot_receipt(bad_receipt, bad_audit)


def test_the_idox_envelope_produces_a_compliant_outer_object_from_a_real_child(tmp_path):
    audit = idox_audit('tameside', ALL, START, END)
    source, got = idox_supervised(tmp_path, audit)
    assert source == audit and got['exit_code'] == 0 and got['cleanup'] == 'CLOSED' and got['live_owned_survivors'] == 0 and got['accounting_complete'] is True and got['limit_hit'] is None
    validate_outer(got, DEFAULT_LIMITS)


# ----------------------------------------------------------------------------------------------- review findings (limits, scope of receipt, preflight)
@pytest.mark.parametrize('change', [dict(requests=0), dict(bytes=1), dict(audit_bytes=1), dict(rows=0), dict(pages=0), dict(worker_seconds=100000), dict(outer_seconds=10 ** 9)])
def test_item_limits_must_be_exactly_the_reviewed_value_not_merely_large_enough(change):
    for council, base in (('tameside', DEFAULT_LIMITS), ('manchester', BROWSER_SOURCE_V2_ITEM_LIMITS)):
        with pytest.raises(Denied, match='ledger.item_limits_not_reviewed'):
            reconcile_items(binding_for(council), dict(base, **change))


@pytest.mark.parametrize('broken', [lambda d: {k: v for k, v in d.items() if k != 'rows'}, lambda d: dict(d, worker_seconds=True), lambda d: dict(d, rows=1.5), lambda d: dict(d, rows=-1), lambda d: dict(d, extra=1), lambda d: None])
def test_malformed_item_limits_are_a_denial_not_a_crash(broken):
    with pytest.raises(Denied, match='ledger.item_limits_malformed'):
        reconcile_items(binding_for('tameside'), broken(dict(DEFAULT_LIMITS)))


@pytest.mark.parametrize('family,council', FAMILIES)
def test_the_receipt_must_be_the_stored_roots_capture_for_exactly_this_scope(family, council, tmp_path):
    binding, contract, cap, receipt, nominees, targets = prepared(family, council, tmp_path)
    kw = dict(revision='unit', item_limits=limits_for(binding), allow_test_evidence=True)
    root = rooted(cap, receipt)
    assert chain_registration(owner(), binding, contract, root, receipt, nominees.nominees, RULE, targets, **kw).kind == 'CHAIN'
    for name, bad_receipt, bad_root in (('other_week', dict(receipt, interval=['2026-11-02', '2026-11-08']), root), ('other_contract', dict(receipt, contract='other'), root),
                                         ('other_basis', dict(receipt, date_semantics='RECEIVED' if family == 'arcus' else 'VALIDATED'), root), ('root_without_checkpoint', receipt, cap.rows[0]),
                                         ('root_with_other_checkpoint', receipt, dict(root, checkpoint=dict(receipt, source_sha256='0' * 64)))):
        with pytest.raises(Denied, match='CHAIN_FOREIGN_CAPTURE'):
            chain_registration(owner(), binding, contract, bad_root, bad_receipt, nominees.nominees, RULE, targets, **kw)


@pytest.mark.parametrize('budget,seconds,rss,code', [
    (None, 45, 1024**3, None),
    (None, 45.001, 100000, 'UI resource bound'),
    (None, 5, 1024**3 + 1, 'SOURCE_RSS'),
    ('BROWSER_SOURCE_V2', 75, 1536 * 1024**2, None),
    ('BROWSER_SOURCE_V2', 75.001, 100000, 'UI resource bound'),
    ('BROWSER_SOURCE_V2', 5, 1536 * 1024**2 + 1, 'SOURCE_RSS'),
])
def test_listing_contract_exact_selected_budget_and_historical_boundaries(budget, seconds, rss, code):
    # Actual qualified validator and adapter, synthetic counters only.
    contract = arcus_contract('manchester', START, END, budget=budget)
    audit = arcus_audit('manchester', ALL, START, END, budget=budget)
    audit.update(supervisor_seconds=seconds, peak_owned_rss=rss)
    if code:
        with pytest.raises((Denied, ValueError), match=code):
            contract._listing().validate(audit)
    else:
        contract._listing().validate(audit)


def test_listing_budget_is_selected_by_contract_not_self_declared_by_audit():
    audit = arcus_audit('manchester', ALL, START, END, budget='BROWSER_SOURCE_V2')
    with pytest.raises(ValueError, match='UI execution budget'):
        arcus_contract('manchester', START, END)._listing().validate(audit)
    audit.pop('execution_budget')
    with pytest.raises(ValueError, match='UI execution budget'):
        arcus_contract('manchester', START, END, budget='BROWSER_SOURCE_V2')._listing().validate(audit)



def test_reader_and_capture_share_one_exact_budget_registry_without_verification_imports():
    from app.ingestion import source_budget
    from verification.discovery import execution_budget
    assert source_budget.select is execution_budget.select
    assert source_budget.HISTORICAL is execution_budget.HISTORICAL
    assert source_budget.BROWSER_SOURCE_V2 is execution_budget.BROWSER_SOURCE_V2
    from verification.discovery import four_council_release as release
    assert 'app/ingestion/source_budget.py' in release.SUCCESSOR_V2_DEPENDENCIES
    assert 'app/ingestion/source_budget.py' not in release.DEPENDENCIES
    assert 'app/ingestion/source_budget.py' not in release.SUCCESSOR_DEPENDENCIES
