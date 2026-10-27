"""Offline unit proof for the bounded end-to-end connection: no database server, no network, no council. Synthetic fixtures only (see e2e_connection_support).

These tests prove the new connections one by one against the in-memory ledger. The integrated chain through restricted PostgreSQL roles is `test_e2e_connection_pg.py`.
A passing unit test is never reported as admission proof, and synthetic contract tests qualify no real council markup.
"""
import copy
import json
from dataclasses import replace
from datetime import date

import pytest
from sqlalchemy import create_engine

from app.ingestion.arcus_adapter import ArcusListingContract
from app.ingestion.batching import archive_capture, batch_plans
from app.ingestion.coordinator import Coordinator, ListingContract
from app.ingestion.idox_adapter import IdoxListingContract
from app.ingestion.ledger import DEFAULT_LIMITS, Denied, Ledger, digest
from app.ingestion.listing_screening import IDENTITY_ELIGIBLE, RULE_V1, RULE_V3, ScreeningRule, routing_of
from app.ingestion.nomination import derive_nominees
from app.ingestion.schema import install
from app.pipeline.discovery_contract import COUNCILS
from tests.e2e_connection_support import (ARCUS_COUNCILS, ASSESS, BELOW, EXTENSION, IDOX_COUNCILS, LABEL, NO_COUNT, PARENT, SCHEME, TEST_QUALIFICATION, IsolatedTestPublisher,
                                          arcus_audit, arcus_contract, arcus_detail_audit, arcus_detail_target, entry, idox_audit, idox_contract, outer)
from verification.discovery.finite_acceptance import SEMANTICS, digest as manifest_digest, manifest, select_rows
from verification.ingestion_storage.new_identity_contract import accepted_arcus_new_identity, accepted_idox_new_identity, project_arcus
from verification.ingestion_storage.v3_admission import factual_binding

START, END = date(2026, 11, 9), date(2026, 11, 15)
RULE = ScreeningRule(RULE_V3, unit_threshold=10, link_related=False)
ALL = [entry('E2E/1/26', SCHEME), entry('E2E/2/26', ASSESS), entry('E2E/3/26', NO_COUNT), entry('E2E/4/26', EXTENSION), entry('E2E/5/26', BELOW), entry('E2E/6/26', PARENT)]
FAMILIES = [('idox', 'tameside'), ('arcus', 'manchester')]
EXPECTED = {'E2E/1/26': 'ADMIT_SCHEME', 'E2E/2/26': 'ADMIT_FOR_ASSESSMENT', 'E2E/3/26': 'ROUTE_COUNT_UNCONFIRMED', 'E2E/4/26': 'RETAIN_NOT_RESIDENTIAL_SUPPLY',
            'E2E/5/26': 'RETAIN_BELOW_THRESHOLD', 'E2E/6/26': 'RETAIN_RELATED_TO_PARENT'}


def build(family, council, entries=ALL, budget=None):
    if family == 'idox':
        return idox_contract(council, START, END), idox_audit(council, entries, START, END)
    return arcus_contract(council, START, END, budget=budget), arcus_audit(council, entries, START, END, budget=budget)


def project(family, council, entries=ALL):
    contract, audit = build(family, council, entries)
    receipt = contract.project(audit, outer(), DEFAULT_LIMITS)
    receipt.pop('window')
    return contract, audit, receipt


def archived(receipt, audit, tmp_path):
    receipt['durable_archive'] = archive_capture(audit, IsolatedTestPublisher(tmp_path))
    return receipt


@pytest.fixture
def ledger():
    engine = create_engine('sqlite:///:memory:')
    install(engine)
    yield Ledger(engine, clock=lambda: 1000.0)
    engine.dispose()


def discovery_task(ledger, contract):
    key = ledger.enqueue(contract.scope(), 'DISCOVERY', contract=contract.name)
    ledger.grant('INGESTION_TEST_e2e', [key], expires_at=100000, contracts=[contract.name], source_calls=0, writes=0)
    return key


def spend_spy(ledger):
    spent = []
    real = ledger.intent
    def intent(claim, operation, **kwargs):
        spent.append(operation)
        return real(claim, operation, **kwargs)
    ledger.intent = intent
    return spent


# ------------------------------------------------------------------------------------------------------------------------- date basis
@pytest.mark.parametrize('council', sorted(COUNCILS))
def test_date_basis_nine_councils(council, tmp_path):
    """Manifest row, contract scope, receipt and batch identity agree for each of the nine councils. Stockport (VALIDATED) could not batch before this correction:
    the batch identity named RECEIVED while the root task is VALIDATED, so the SQL batch binding (subject equality) refused it."""
    row = select_rows(plan := manifest(START.isoformat(), END.isoformat(), 'PROSPECTIVE'), manifest_digest(plan), [council])[0]
    family = 'arcus' if council in ARCUS_COUNCILS else 'idox'
    contract, audit, receipt = project(family, council)
    assert row['semantics'] == SEMANTICS[council] == contract.scope()['semantics']
    if family == 'idox':
        assert audit['date_semantics'] == row['semantics']      # the production reader's own audit agrees
    assert receipt.get('date_semantics', 'RECEIVED') == row['semantics']
    if row['semantics'] != 'RECEIVED':
        assert receipt['date_semantics'] == row['semantics']
    capture = archived(receipt, audit, tmp_path)
    plans = batch_plans(digest(contract.scope()), capture, RULE)
    assert plans and all(p['subject'] == contract.scope() for p in plans)


def test_batch_identity_refuses_an_unknown_date_basis(tmp_path):
    contract, audit, receipt = project('idox', 'tameside')
    receipt['date_semantics'] = 'PUBLICATION'
    with pytest.raises(Denied, match='DATE_SEMANTICS'):
        batch_plans('k' * 64, archived(receipt, audit, tmp_path), RULE)


def test_historical_receipts_without_a_date_basis_keep_the_received_identity(tmp_path):
    contract, audit, receipt = project('idox', 'bolton')
    assert 'date_semantics' not in receipt      # historical digests are pinned: a RECEIVED capture is unchanged by this slice
    assert batch_plans('k' * 64, archived(receipt, audit, tmp_path), RULE)[0]['subject']['semantics'] == 'RECEIVED'


# --------------------------------------------------------------------------------------------------------------------- manifest rows
def test_manifest_selection_regenerates_and_selects_only_named_councils():
    plan = manifest('2026-11-09', '2026-11-22', 'PROSPECTIVE')
    rows = select_rows(plan, manifest_digest(plan), ['stockport', 'tameside'])
    assert {r['council'] for r in rows} == {'stockport', 'tameside'} and len(rows) == 4
    assert {r['council']: r['semantics'] for r in rows} == {'stockport': 'VALIDATED', 'tameside': 'RECEIVED'}


@pytest.mark.parametrize('change', ['rows', 'start', 'drop_row', 'hash'])
def test_manifest_selection_refuses_anything_not_canonical(change):
    plan = manifest('2026-11-09', '2026-11-15', 'PROSPECTIVE')
    expected = manifest_digest(plan)
    bad = copy.deepcopy(plan)
    if change == 'rows':
        bad['rows'][0]['semantics'] = 'VALIDATED'
    if change == 'start':
        bad['start'] = '2026-11-10'
    if change == 'drop_row':
        bad['rows'].pop()
    if change == 'hash':
        expected = '0' * 64
    with pytest.raises(ValueError, match='unreviewed manifest'):
        select_rows(bad, expected, ['tameside'])


@pytest.mark.parametrize('councils', [[], ['tameside', 'tameside'], ['trafford'], ['tameside', 'nowhere']])
def test_manifest_selection_refuses_empty_duplicate_or_out_of_scope_councils(councils):
    plan = manifest('2026-11-09', '2026-11-15', 'PROSPECTIVE')
    with pytest.raises(ValueError, match='council selection'):
        select_rows(plan, manifest_digest(plan), councils)


# --------------------------------------------------------------------------------------------------------------- retained capture
@pytest.mark.parametrize('family,council', FAMILIES)
def test_retained_capture_makes_no_listing_request_and_spends_no_source_call(family, council, ledger, tmp_path):
    contract, audit = build(family, council)
    key = discovery_task(ledger, contract)
    spent = spend_spy(ledger)
    publisher = IsolatedTestPublisher(tmp_path)
    co = Coordinator(ledger, {contract.name: contract})
    receipt = co.retained_capture(ledger.claim(key, 'worker', 'INGESTION_TEST_e2e'), audit, outer(), publisher, expected_source_sha256=digest(audit), evidence_label=LABEL)
    row = ledger.get(key)
    assert spent == [] and row['state'] == 'COMPLETE' and digest(row['checkpoint']) == digest(receipt)
    assert receipt['kind'] == 'LISTING_RECEIPT_V1' and receipt['evidence_label'] == LABEL and receipt['date_semantics'] == SEMANTICS[council]
    assert receipt['durable_archive']['label'] == LABEL and receipt['durable_archive']['readback_verified'] is True
    assert receipt['durable_archive']['sha256'] == digest(audit) == receipt['source_sha256'] and 'window' not in receipt
    assert len(publisher.calls) == 1 and len(receipt['records']) == len(ALL)
    assert row['outcome']['outcome'] == 'ENUMERATED_METADATA_RETAINED'


@pytest.mark.parametrize('family,council', FAMILIES)
@pytest.mark.parametrize('mode', ['corrupt_write', 'wrong_sha', 'wrong_bytes', 'raises'])
def test_archive_or_readback_failure_stops_before_any_checkpoint(family, council, mode, ledger, tmp_path):
    contract, audit = build(family, council)
    key = discovery_task(ledger, contract)
    co = Coordinator(ledger, {contract.name: contract})
    expected = OSError if mode == 'raises' else Denied
    with pytest.raises(expected):
        co.retained_capture(ledger.claim(key, 'worker', 'INGESTION_TEST_e2e'), audit, outer(), IsolatedTestPublisher(tmp_path, mode), expected_source_sha256=digest(audit))
    row = ledger.get(key)
    assert row['checkpoint'] is None and row['state'] != 'COMPLETE'


@pytest.mark.parametrize('family,council', FAMILIES)
def test_tampered_audit_is_refused_and_never_archived(family, council, ledger, tmp_path):
    contract, audit = build(family, council)
    key = discovery_task(ledger, contract)
    co = Coordinator(ledger, {contract.name: contract})
    claim = ledger.claim(key, 'worker', 'INGESTION_TEST_e2e')
    publisher = IsolatedTestPublisher(tmp_path)
    forged = copy.deepcopy(audit)
    records = forged['records'] if family == 'idox' else forged['listing_records']
    records[0]['fields']['proposal']['value'] = 'Erection of 99 residential dwellings'
    with pytest.raises(Denied, match='RETAINED_AUDIT_BINDING'):
        co.retained_capture(claim, forged, outer(), publisher, expected_source_sha256=digest(audit))      # the publisher recorded the real hash
    with pytest.raises(TypeError):
        co.retained_capture(claim, forged, outer(), publisher)      # the recorded hash is mandatory, never optional
    # A forger who also recomputes the hash: an Arcus contract re-derives each row from its own capture and refuses; an Idox audit binds page hashes but not each record's
    # text (the raw pages are not retained), so a consistent text edit is NOT detectable by the contract. Only the publisher-recorded hash defends it, which is why it is mandatory.
    if family == 'arcus':
        with pytest.raises(Denied):
            co.retained_capture(claim, forged, outer(), publisher, expected_source_sha256=digest(forged))
        assert publisher.calls == [] and ledger.get(key)['checkpoint'] is None
    structural = copy.deepcopy(audit)      # a structural edit with a recomputed hash is refused by both contracts
    (structural['pages'] if family == 'idox' else structural['listing_segments'])[0]['total'] += 1
    with pytest.raises(Denied):
        co.retained_capture(claim, structural, outer(), publisher, expected_source_sha256=digest(structural))
    assert publisher.calls == [] and ledger.get(key)['checkpoint'] is None


@pytest.mark.parametrize('family,council', FAMILIES)
def test_retained_capture_is_not_replayable_and_is_scope_bound(family, council, ledger, tmp_path):
    contract, audit = build(family, council)
    key = discovery_task(ledger, contract)
    co = Coordinator(ledger, {contract.name: contract})
    co.retained_capture(ledger.claim(key, 'worker', 'INGESTION_TEST_e2e'), audit, outer(), IsolatedTestPublisher(tmp_path), expected_source_sha256=digest(audit))
    with pytest.raises(Denied):
        co.retained_capture(ledger.claim(key, 'worker', 'INGESTION_TEST_e2e'), audit, outer(), IsolatedTestPublisher(tmp_path), expected_source_sha256=digest(audit))
    other = idox_contract('oldham', START, END) if family == 'idox' else arcus_contract('salford', START, END)
    foreign = ledger.enqueue(contract.scope(), 'DISCOVERY', contract=other.name, revision='foreign')
    ledger.grant('INGESTION_TEST_e2f', [foreign], expires_at=100000, contracts=[other.name])
    co2 = Coordinator(ledger, {other.name: other})
    with pytest.raises(Denied, match='RETAINED_TASK_SCOPE'):
        co2.retained_capture(ledger.claim(foreign, 'worker', 'INGESTION_TEST_e2f'), audit, outer(), IsolatedTestPublisher(tmp_path), expected_source_sha256=digest(audit))


def test_retained_capture_refuses_an_unsupported_contract_and_a_bad_label(ledger, tmp_path):
    contract, audit = build('idox', 'tameside')
    key = discovery_task(ledger, contract)
    claim = ledger.claim(key, 'worker', 'INGESTION_TEST_e2e')
    with pytest.raises(Denied, match='UNSUPPORTED_RETAINED_CONTRACT'):
        Coordinator(ledger, {contract.name: object()}).retained_capture(claim, audit, outer(), IsolatedTestPublisher(tmp_path), expected_source_sha256=digest(audit))
    with pytest.raises(Denied, match='EVIDENCE_LABEL'):
        Coordinator(ledger, {contract.name: contract}).retained_capture(claim, audit, outer(), IsolatedTestPublisher(tmp_path), expected_source_sha256=digest(audit), evidence_label='not a label!')


# ------------------------------------------------------------------------------------------------------------------- Arcus contract
def test_arcus_contract_builds_a_receipt_with_provenance_and_a_complete_window():
    contract, audit = build('arcus', 'manchester')
    receipt = contract.project(audit, outer(), DEFAULT_LIMITS)
    assert receipt['kind'] == 'LISTING_RECEIPT_V1' and receipt['date_semantics'] == 'VALIDATED' and receipt['source_sha256'] == digest(audit)
    assert receipt['window']['source_contract'] == contract.name and receipt['qualification_sha256'] == TEST_QUALIFICATION
    assert all(len(r['provenance']['body_sha256']) == 64 and r['provenance']['row_ordinal'] == n for n, r in enumerate(receipt['records'], 1))
    window = contract.admission_window(receipt, 'manchester')
    from app.pipeline.discovery_contract import Completeness
    assert window.outcome == Completeness.COMPLETE and window.date_semantics == 'VALIDATED'


def test_arcus_contract_accepts_the_declared_execution_budget_and_refuses_a_mismatch():
    contract, audit = build('arcus', 'rochdale', budget='BROWSER_SOURCE_V2')
    assert contract.project(audit, outer(), DEFAULT_LIMITS)['kind'] == 'LISTING_RECEIPT_V1'
    historical = arcus_contract('rochdale', START, END, budget=None)
    with pytest.raises(Denied, match='ARCUS_AUDIT_REJECTED'):
        historical.project(audit, outer(), DEFAULT_LIMITS)      # an audit that declares a budget is refused under the historical envelope
    declared = arcus_contract('rochdale', START, END, budget='BROWSER_SOURCE_V2')
    with pytest.raises(Denied, match='ARCUS_AUDIT_REJECTED'):
        declared.project(arcus_audit('rochdale', ALL, START, END), outer(), DEFAULT_LIMITS)      # and a budgeted contract refuses an audit that declares none


def test_arcus_contract_ignores_the_release_screening_annotation_but_not_a_changed_row():
    contract, audit = build('arcus', 'manchester')
    annotated = copy.deepcopy(audit)
    for row in annotated['listing_records']:
        row['processing_screen'] = {'rule_version': 'stage4-retained-screen-v1'}
    receipt = contract.project(annotated, outer(), DEFAULT_LIMITS)
    assert all('processing_screen' not in r for r in receipt['records'])
    forged = copy.deepcopy(audit)
    forged['listing_records'][0]['fields']['address']['value'] = 'Elsewhere'
    with pytest.raises(Denied):
        contract.project(forged, outer(), DEFAULT_LIMITS)


@pytest.mark.parametrize('change', [dict(live_owned_survivors=1), dict(safety_failure=True, safety_events=['BYTE_LIMIT']), dict(requested_interval=['2026-11-09', '2026-11-14']),
                                    dict(enumeration_evidence='TOTAL_UNKNOWN'), dict(completeness='COMPLETE'), dict(persistence=True), dict(failure='X'), dict(case='discovery_salford_ui_window')])
def test_arcus_contract_refuses_unsafe_or_unbound_audits(change):
    contract, audit = build('arcus', 'manchester')
    audit.update(change)
    with pytest.raises(Denied):
        contract.project(audit, outer(), DEFAULT_LIMITS)


def test_arcus_contract_refuses_identity_only_non_arcus_and_bad_qualification():
    cfg = arcus_contract('manchester', START, END).config
    with pytest.raises(Denied, match='ARCUS_ASSESSMENT_METADATA_REQUIRED'):
        ArcusListingContract('x', replace(cfg, assessment_metadata=False), 'c', lambda *a, **k: None, lambda *a, **k: None, TEST_QUALIFICATION)
    with pytest.raises(Denied, match='ARCUS_COUNCIL'):
        ArcusListingContract('x', replace(cfg, council='bolton'), 'c', lambda *a, **k: None, lambda *a, **k: None, TEST_QUALIFICATION)
    with pytest.raises(Denied, match='EXACT_ARCUS_QUALIFICATION_REQUIRED'):
        ArcusListingContract('x', cfg, 'c', lambda *a, **k: None, lambda *a, **k: None, 'short')


def test_arcus_contract_refuses_resource_overruns_and_an_empty_window():
    contract, audit = build('arcus', 'manchester')
    with pytest.raises(Denied):
        contract.project(audit, outer(), dict(DEFAULT_LIMITS, requests=5))
    with pytest.raises(Denied):
        contract.project(audit, dict(outer(), live_owned_survivors=1), DEFAULT_LIMITS)
    empty = arcus_audit('manchester', [entry('E2E/9/26', SCHEME)], START, END)
    empty['listing_records'], empty['listing_segments'] = [], [dict(ordinal=1, first=0, last=0, total=0, evidence_sha256='0' * 64)]
    with pytest.raises(Denied):
        contract.project(empty, outer(), DEFAULT_LIMITS)


# ---------------------------------------------------------------------------------------------------------------------------- nominees
@pytest.mark.parametrize('family,council', FAMILIES)
def test_nominees_follow_the_frozen_v3_table_exactly(family, council, tmp_path):
    contract, audit, receipt = project(family, council)
    nominees = derive_nominees([archived(receipt, audit, tmp_path)], RULE)
    assert [n.outcome for n in nominees.nominees] == ['ADMIT_SCHEME', 'ADMIT_FOR_ASSESSMENT']
    assert {n.outcome for n in nominees.nominees} <= IDENTITY_ELIGIBLE[RULE_V3]
    assert {ref: out for _, ref, out in nominees.retained} == {k: v for k, v in EXPECTED.items() if v not in IDENTITY_ELIGIBLE[RULE_V3]}
    assert nominees.conflicts == () and len(nominees.sha256) == 64
    again = derive_nominees([receipt], RULE)
    assert again.sha256 == nominees.sha256 and again.nominees == nominees.nominees      # deterministic


def test_nominees_ignore_input_order_and_bind_identical_observations_to_one_capture(tmp_path):
    _, audit_a, a = project('idox', 'tameside')
    _, audit_b, b = project('idox', 'tameside')
    for r in b['records']:
        r['provenance'] = dict(r['provenance'], body_sha256='1' * 64)      # a second capture of the same observations differs only in provenance
    archived(a, audit_a, tmp_path), archived(b, audit_b, tmp_path)
    assert digest(a) != digest(b)
    one, two = derive_nominees([a, b], RULE), derive_nominees([b, a], RULE)
    assert one.sha256 == two.sha256 and len(one.nominees) == 2 and one.conflicts == ()
    assert {n.capture_sha256 for n in one.nominees} == {min(digest(a), digest(b))}


def test_conflicting_observations_of_one_reference_are_withheld_not_resolved(tmp_path):
    _, audit_a, a = project('arcus', 'manchester', [entry('E2E/1/26', SCHEME)])
    _, audit_b, b = project('arcus', 'manchester', [entry('E2E/1/26', ASSESS)])      # same reference, different proposal
    nominees = derive_nominees([archived(a, audit_a, tmp_path), archived(b, audit_b, tmp_path)], RULE)
    assert nominees.nominees == () and len(nominees.conflicts) == 1 and nominees.conflicts[0]['reference'] == 'E2E/1/26'
    assert len(nominees.conflicts[0]['observations']) == 2


@pytest.mark.parametrize('family,council', FAMILIES)
def test_unusable_metadata_is_never_nominated_but_unknown_address_and_type_are_not_unusable(family, council, tmp_path):
    entries = [entry('E2E/1/26', ASSESS, address=None if family == 'arcus' else ''), entry('E2E/2/26', None if family == 'arcus' else '')]
    if family == 'arcus':
        entries += [dict(entry('E2E/3/26', SCHEME), both_labels=True), entry('E2E/4/26', 'x' * 9000)]
    _, audit, receipt = project(family, council, entries)
    nominees = derive_nominees([archived(receipt, audit, tmp_path)], RULE)
    outcomes = {ref: out for _, ref, out in nominees.retained} | {n.reference: n.outcome for n in nominees.nominees}
    assert outcomes['E2E/1/26'] == 'ADMIT_FOR_ASSESSMENT'      # unknown address and type do not gate the frozen routing
    assert outcomes['E2E/2/26'] == 'RETAIN_UNUSABLE_PROPOSAL'
    if family == 'arcus':
        assert outcomes['E2E/3/26'] == 'RETAIN_UNUSABLE_PROPOSAL'      # two aliases: CONFLICTING
        assert outcomes['E2E/4/26'] == 'RETAIN_UNUSABLE_PROPOSAL'      # truncated at the capture limit


def test_nomination_requires_the_frozen_v3_rule_and_an_archived_receipt(tmp_path):
    _, audit, receipt = project('idox', 'tameside')
    with pytest.raises(Denied, match='RETAINED_CAPTURE_REQUIRED'):
        derive_nominees([receipt], RULE)      # no durable archive
    with pytest.raises(Denied, match='V3_RULE_REQUIRED'):
        derive_nominees([archived(receipt, audit, tmp_path)], ScreeningRule(RULE_V1))


# ------------------------------------------------------------------------------------------------------------------- Arcus factual
def arcus_target_and_audit(tmp_path=None, **kw):
    _, _, receipt = project('arcus', 'manchester')
    target = arcus_detail_target('manchester', receipt['records'][0])
    return target, arcus_detail_audit(target, **kw)


def test_arcus_projector_uses_the_existing_initial_status_scope():
    target, detail = arcus_target_and_audit()
    packet = project_arcus(target, detail)
    assert packet['failure'] is None and packet['observation'].b2_eligible and packet['observation'].verification_scope == 'INITIAL_STATUS_ONLY'
    assert packet['observation'].application_id is None and packet['audit']['cleanup_state'] == 'CLOSED'


@pytest.mark.parametrize('change,failure', [(dict(live_owned_survivors=1), 'CLEANUP_FAILURE'), (dict(requested_origins=['https://wrong.invalid']), 'SCOPE_ESCAPE'),
                                            (dict(reference='OTHER'), 'AMBIGUOUS_SOURCE_RESULT'), (dict(record_http_probe=None), 'SOURCE_UNAVAILABLE'),
                                            (dict(supervisor_limit_hit=True), 'ACCOUNTING_FAILURE')])
def test_arcus_projector_failures_withhold_the_observation(change, failure):
    target, detail = arcus_target_and_audit()
    detail.update(change)
    packet = project_arcus(target, detail)
    assert packet['observation'] is None and packet['failure'] == failure


def test_arcus_projector_does_not_invent_support_for_other_statuses():
    target, detail = arcus_target_and_audit(status='Decided')
    packet = project_arcus(target, detail)
    assert packet['observation'] is None or not packet['observation'].b2_eligible      # not an initial status: no admission scope is claimed


def test_factual_binding_accepts_only_the_two_reviewed_families():
    idox_target = dict(case='c', council='tameside', reference='R', source_identifier='K1', source_url='https://publicaccess.tameside.gov.uk/online-applications/applicationDetails.do?activeTab=summary&keyVal=K1',
                       admission='ADMITTED_DIRECT_ROUTE', platform_family='IDOX', application_id=None)
    arcus_target, _ = arcus_target_and_audit()
    idox, arcus = accepted_idox_new_identity('f-idox', idox_target), accepted_arcus_new_identity('f-arcus', arcus_target)
    assert factual_binding(idox) != factual_binding(arcus) and factual_binding(arcus) == factual_binding(accepted_arcus_new_identity('f-arcus', arcus_target))
    unknown = replace(arcus, projector=lambda row, source: {'observation': None, 'audit': {}, 'failure': 'X'})
    with pytest.raises(Denied, match='V3_FACTUAL_COMPONENT_UNSUPPORTED'):
        factual_binding(unknown)
    with pytest.raises(Denied, match='V3_FACTUAL_CONTRACT_REQUIRED'):
        factual_binding(object())


def test_idox_factual_binding_is_unchanged_by_the_generalisation():
    """The Idox hash is recomputed here by the original algorithm; a change would orphan every existing V3AdmissionBinding."""
    import hashlib, importlib, inspect
    from pathlib import Path
    row = dict(case='c', council='tameside', reference='R', source_identifier='K1', admission='ADMITTED_DIRECT_ROUTE', platform_family='IDOX', application_id=None,
               source_url='https://publicaccess.tameside.gov.uk/online-applications/applicationDetails.do?activeTab=summary&keyVal=K1')
    contract = accepted_idox_new_identity('f-idox', row)
    modules = {getattr(contract, n).__module__ for n in ('projector', 'handoff', 'coupled_gate')} | {'verification.ingestion_storage.new_identity_contract'}
    hashes = {n: hashlib.sha256(Path(inspect.getsourcefile(importlib.import_module(n))).read_bytes()).hexdigest() for n in sorted(modules)}
    assert factual_binding(contract) == digest(dict(name=contract.name, row=contract.row, verification_scope=contract.verification_scope, modules=hashes))
