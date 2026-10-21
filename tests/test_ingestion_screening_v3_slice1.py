"""Screening rule v3, slice 1 (PR #171): explicit selection, configuration-bound assessment identity, version-aware identity eligibility, history and investigation-requirement projections, offline.

Everything runs against the disposable ledger and the disposable application database. Nothing here touches production SQL, grants, the operational controller, Phase B or any council."""
import copy
import hashlib
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.config import get_council
from app.db.models import Application
from app.ingestion import listing_screening as ls
from app.ingestion import screening_projection as sp
from app.ingestion.coordinator import Coordinator
from app.ingestion.ledger import Ledger, Denied, digest
from app.ingestion.schema import install, WorkItem as W
from tests.test_discovery_admission import engine, envelope
from tests.test_discovery_initial_application_contract import projected
from verification.direct_reference.fixtures import summary
from verification.ingestion_storage.new_identity_contract import accepted_idox_new_identity

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/bolton_window_24_listing.json'
PROVENANCE = ROOT / 'tests/fixtures/bolton_window_24_listing.PROVENANCE.json'
EXAMPLES = json.loads((ROOT / 'specifications/035-residential-count-examples.json').read_text(encoding='utf-8'))['examples']
V1 = ls.V1_CONTRACT
V3 = ls.V3_CONTRACT


def field(value):
    return dict(state='PRESENT_VALUE', value=value, locator='fixture', truncated=False)


def record(reference, proposal, address='1 Test Street Bolton', **over):
    out = dict(reference=reference, source_url='https://example.invalid/bolton/' + reference.replace('/', '-'), source_record_id=reference,
               fields=dict(proposal=field(proposal), address=field(address), application_type=dict(state='UNKNOWN', value=None, locator='fixture', truncated=False)))
    out.update(over)
    return out


def bolton_records():
    return [record(r['reference'], r['proposal'], r['address']) for r in json.loads(FIXTURE.read_text(encoding='utf-8'))]


def v3_rule(threshold=10):
    return ls.ScreeningRule(ls.RULE_V3, unit_threshold=threshold)


def registry(rule=None):
    rule = rule or ls.ScreeningRule(ls.RULE_V1)
    return {rule.contract(): rule}


def receipt_for(records):
    return dict(kind='LISTING_RECEIPT_V1', source_sha256=hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest(), council='bolton', records=records, cleanup='CLOSED', accounting_complete=True)


def scope(n):
    return dict(kind='DISCOVERY_SCOPE', council='bolton', start='2026-10-12', end='2026-10-18', semantics='RECEIVED', n=n)


def capture(ledger, records, n=0):
    """A claimed, checkpointed listing capture the coordinator can materialise screening items from. Returns (claim, receipt)."""
    key = ledger.enqueue(scope(n), 'LISTING_METADATA', contract='fixture-listing')
    ledger.grant('INGESTION_TEST_capture%d' % n, [key], contracts=['fixture-listing'], expires_at=ledger.clock() + 600)
    claim = ledger.claim(key, 'worker', 'INGESTION_TEST_capture%d' % n)
    receipt = receipt_for(records)
    ledger.checkpoint(claim, receipt)
    return claim, receipt


def screen_all(ledger, co, children, tag='s'):
    """Grant (one authority, the ledger bounds the number of authorities) and run every screening child under the coordinator's contract; returns {item_key: checkpoint}."""
    authority = 'INGESTION_TEST_' + tag
    ledger.grant(authority, children, contracts=[co.screening_contract], expires_at=ledger.clock() + 600)
    return {key: co.screening(ledger.claim(key, 'screener', authority)) for key in children}


def run(ledger, records, rule=None, n=0):
    co = Coordinator(ledger, {}, screening_rules=registry(rule))
    claim, receipt = capture(ledger, records, n)
    children = co._materialize(claim, receipt)
    return co, children, screen_all(ledger, co, children, 's%d' % n)


@pytest.fixture
def ledger(engine):
    install(engine)
    return Ledger(engine)


def items(ledger):
    return sp.screening_items(ledger)


# ------------------------------------------------------------------ compatibility: v1 stays the default and is unchanged
def test_the_default_coordinator_screens_with_v1_exactly_as_before_over_the_bolton_window(ledger):
    records = bolton_records()
    co, children, results = run(ledger, records)
    assert co.screening_contract == V1 and co.screening_rule.rule_version == ls.RULE_V1
    rows = {k: ledger.get(k) for k in children}
    assert Counter(r['checkpoint']['disposition'] for r in rows.values()) == Counter(INSUFFICIENT_EVIDENCE=20, RELATED_APPLICATION_FOLLOW_THROUGH=3, SUPPORTED_PROCESSING_PRIORITY=1)
    for r in rows.values():
        record_ = next(x for x in records if x['reference'] == r['subject']['reference'])
        assert r['contract'] == V1 and r['revision'] == digest(record_)      # the historical identity, byte for byte
        assert r['state'] == 'COMPLETE' and r['outcome'] == dict(outcome=r['checkpoint']['disposition'], retained=True)
        assert not {'record_sha256', 'config', 'config_sha256', 'assessment_revision', 'assessment_sha256', 'related_assessments', 'count_assessment'} & set(r['checkpoint'])
        expected = ls.screen_row(record_)
        assert {k: v for k, v in r['checkpoint'].items() if k in expected} == expected      # screen_row's own result, untouched


def test_the_default_registry_cannot_run_a_v3_item_and_an_unknown_contract_is_still_a_task_error(ledger):
    claim, receipt = capture(ledger, [record('01768/26', 'Erection of 49 dwellings')])
    co3 = Coordinator(ledger, {}, screening_rules=registry(v3_rule()))
    (child,) = co3._materialize(claim, receipt)
    co1 = Coordinator(ledger, {})      # default: v1 only
    ledger.grant('INGESTION_TEST_x', [child], contracts=[V3], expires_at=ledger.clock() + 600)
    with pytest.raises(Denied, match='SCREENING_CONTRACT_NOT_REGISTERED'):
        co1.screening(ledger.claim(child, 'w', 'INGESTION_TEST_x'))
    other = ledger.enqueue(dict(kind='APPLICATION', council='bolton', reference='01768/26'), 'SCREENING', contract='listing-screen-v9', revision='r', dependencies=[claim.key])
    ledger.grant('INGESTION_TEST_y', [other], contracts=['listing-screen-v9'], expires_at=ledger.clock() + 600)
    with pytest.raises(Denied, match='SCREENING_TASK'):
        co1.screening(ledger.claim(other, 'w', 'INGESTION_TEST_y'))


def test_a_v1_item_is_refused_by_a_v3_coordinator(ledger):
    claim, receipt = capture(ledger, [record('01768/26', 'Erection of 49 dwellings')])
    (child,) = Coordinator(ledger, {})._materialize(claim, receipt)
    co3 = Coordinator(ledger, {}, screening_rules=registry(v3_rule()))
    ledger.grant('INGESTION_TEST_x', [child], contracts=[V1], expires_at=ledger.clock() + 600)
    with pytest.raises(Denied, match='SCREENING_CONTRACT_NOT_REGISTERED'):
        co3.screening(ledger.claim(child, 'w', 'INGESTION_TEST_x'))


# ------------------------------------------------------------------ explicit selection and one contract per run
def test_selection_is_explicit_validated_and_one_contract_per_run():
    assert ls.ScreeningRule(ls.RULE_V1).config() is None and ls.ScreeningRule(ls.RULE_V1).contract() == V1
    assert v3_rule().contract() == V3
    for bad in (dict(unit_threshold=10), dict(council='bolton')):
        with pytest.raises(ValueError, match='RULE_V1_TAKES_NO_THRESHOLD'):
            ls.ScreeningRule(ls.RULE_V1, **bad)
    with pytest.raises(ValueError, match='EXACTLY_ONE'):
        ls.ScreeningRule(ls.RULE_V3)
    with pytest.raises(ValueError, match='EXACTLY_ONE'):
        ls.ScreeningRule(ls.RULE_V3, unit_threshold=10, council='bolton')
    for threshold in (0, -1, True, 10.0, '10', None):
        if threshold is None:
            continue
        with pytest.raises(ValueError, match='INVALID_SCREENING_THRESHOLD'):
            ls.ScreeningRule(ls.RULE_V3, unit_threshold=threshold)
    with pytest.raises(ValueError, match='UNKNOWN_SCREENING_RULE_VERSION'):
        ls.ScreeningRule('manchester-listing-screen-assessment-v2')
    engine_stub = object()
    with pytest.raises(ValueError, match='ONE_SCREENING_CONTRACT_PER_RUN'):
        Coordinator(engine_stub, {}, screening_rules={V1: ls.ScreeningRule(ls.RULE_V1), V3: v3_rule()})
    with pytest.raises(ValueError, match='SCREENING_CONTRACT_RULE_MISMATCH'):
        Coordinator(engine_stub, {}, screening_rules={V1: v3_rule()})
    with pytest.raises(ValueError, match='SCREENING_CONTRACT_RULE_MISMATCH'):
        Coordinator(engine_stub, {}, screening_rules={V3: ls.ScreeningRule(ls.RULE_V1)})
    with pytest.raises(ValueError, match='SCREENING_CONTRACT_RULE_MISMATCH'):
        Coordinator(engine_stub, {}, screening_rules={'anything': v3_rule()})
    assert Coordinator(engine_stub, {}).screening_contract == V1      # nothing selected: v1


def test_the_council_threshold_is_frozen_at_construction_and_recorded_in_the_binding(ledger, monkeypatch):
    rule = ls.ScreeningRule(ls.RULE_V3, council='bolton')
    assert rule.unit_threshold == get_council('bolton').unit_threshold == 10
    monkeypatch.setattr(ls, 'council_unit_threshold', lambda council: 99)      # the configuration changes after the run was built
    co, children, results = run(ledger, [record('01768/26', 'Erection of 49 dwellings')], rule)
    (checkpoint,) = results.values()
    assert checkpoint['count_assessment_threshold'] == 10 and checkpoint['config']['unit_threshold'] == 10
    assert ls.ScreeningRule(ls.RULE_V3, council='bolton').unit_threshold == 99      # a NEW run reads the new value, and gets a different identity


# ------------------------------------------------------------------ configuration-bound identity and persistence
def test_a_v3_item_stores_the_binding_and_routes_by_the_count_assessment(ledger):
    rec = record('01768/26', 'DEMOLITION OF 4 NO. BUILDINGS AND ERECTION OF 4 NO. APARTMENT BLOCKS COMPRISING OF NO. 49 SELF CONTAINED APARTMENTS')
    co, (child,), results = run(ledger, [rec], v3_rule())
    row = ledger.get(child)
    cp = row['checkpoint']
    record_sha = digest(rec)
    config = dict(rule_version=ls.RULE_V3, count_spec_version='residential-count-v2', assessor='count_assessment', unit_threshold=10, max_text_chars=8192, code_binding=ls.code_binding(), digest_probe=ls.digest_probe())
    assert row['contract'] == V3 and row['task'] == 'SCREENING'
    assert cp['record_sha256'] == record_sha and cp['config'] == config and cp['config_sha256'] == digest(config)
    assert row['revision'] == cp['assessment_revision'] == digest(dict(record_sha256=record_sha, config_sha256=digest(config)))
    assert cp['assessment_sha256'] == digest(cp['count_assessment'])
    assert cp['capture_key'] == row['dependencies'][0] and cp['capture_sha256'] == ledger.get(cp['capture_key'])['checkpoint']['source_sha256']
    assert cp['rule_version'] == ls.RULE_V3 and cp['routing_authority'] == 'count_assessment' and ls.routing_of(cp) == ('count_assessment', 'ADMIT_SCHEME')
    assert row['outcome'] == dict(outcome='ADMIT_SCHEME', retained=True)      # the ledger outcome is the routing outcome, not the informational v1 disposition
    assert (cp['source_url'], cp['source_record_id'], cp['proposal'], cp['application_type']) == (rec['source_url'], rec['source_record_id'], rec['fields']['proposal'], rec['fields']['application_type'])
    assert cp['count_assessment']['proposed_total'] == 49 and cp['count_assessment']['approved_total'] == 'NOT_ESTABLISHED'


def test_the_same_record_under_the_same_configuration_is_one_item_and_a_changed_threshold_is_another(ledger):
    records = [record('01768/26', 'Erection of 49 dwellings')]
    co_a, kids_a, res_a = run(ledger, records, v3_rule(10), n=0)
    claim, receipt = capture(ledger, records, n=1)
    again = co_a._materialize(claim, receipt)      # a second capture of the identical record under the identical configuration
    assert again == kids_a      # idempotent: the stable key is the same item
    co_b = Coordinator(ledger, {}, screening_rules=registry(v3_rule(60)))
    claim2, receipt2 = capture(ledger, records, n=2)
    (other,) = co_b._materialize(claim2, receipt2)
    assert other != kids_a[0]      # a different threshold is a different assessment identity
    screen_all(ledger, co_b, [other], 'b')
    a, b = ledger.get(kids_a[0]), ledger.get(other)
    assert a['checkpoint']['record_sha256'] == b['checkpoint']['record_sha256']      # the source record revision stays separately identifiable
    assert a['checkpoint']['config_sha256'] != b['checkpoint']['config_sha256'] and a['revision'] != b['revision']
    assert ls.routing_of(a['checkpoint'])[1] == 'ADMIT_SCHEME' and ls.routing_of(b['checkpoint'])[1] == 'RETAIN_BELOW_THRESHOLD'      # both kept, both explicable
    with ledger.engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(W).where(W.c.task == 'SCREENING')) == 2


def test_a_changed_record_is_a_different_item_even_under_the_same_configuration(ledger):
    co, kids1, _ = run(ledger, [record('01768/26', 'Erection of 49 dwellings')], v3_rule(), n=0)
    claim, receipt = capture(ledger, [record('01768/26', 'Erection of 50 dwellings')], n=1)
    kids2 = co._materialize(claim, receipt)
    assert kids1 != kids2


@pytest.mark.parametrize('tamper', ['revision', 'threshold', 'record'])
def test_screening_denies_an_item_whose_stored_identity_is_not_the_one_this_run_derives(ledger, tamper):
    rec = record('01768/26', 'Erection of 49 dwellings')
    claim, receipt = capture(ledger, [rec])
    co = Coordinator(ledger, {}, screening_rules=registry(v3_rule(10)))
    if tamper == 'revision':
        child = ledger.enqueue(dict(kind='APPLICATION', council='bolton', reference='01768/26'), 'SCREENING', contract=V3, revision=digest(rec), dependencies=[claim.key])      # v1-style revision under the v3 contract
        ledger.finish(claim, dict(outcome='ENUMERATED_METADATA_RETAINED', children=[child], source_sha256=receipt['source_sha256']))
    elif tamper == 'threshold':
        child = Coordinator(ledger, {}, screening_rules=registry(v3_rule(60)))._materialize(claim, receipt)[0]      # made under another threshold
    else:
        child = co._materialize(claim, receipt)[0]
        other = copy.deepcopy(receipt)
        other['records'][0]['fields']['proposal']['value'] = 'Erection of 4 dwellings'
        with ledger.engine.begin() as c:      # the retained capture no longer matches the record the item was made from
            c.execute(W.update().where(W.c.key == claim.key).values(checkpoint=other))
    ledger.grant('INGESTION_TEST_t', [child], contracts=[V3], expires_at=ledger.clock() + 600)
    with pytest.raises(Denied, match='SCREENING_CONFIG_BINDING'):
        co.screening(ledger.claim(child, 'w', 'INGESTION_TEST_t'))
    assert ledger.get(child)['checkpoint'] is None      # nothing was stored for a refused item


# ------------------------------------------------------------------ history: other assessments are linked, never superseded
def test_related_assessments_link_every_other_assessment_of_the_same_record_and_nothing_is_superseded(ledger):
    rec = record('01768/26', 'Erection of 49 dwellings')
    co1, kids1, _ = run(ledger, [rec], None, n=0)      # v1
    snapshot_v1 = copy.deepcopy(ledger.get(kids1[0]))
    co3a, kids3a, _ = run(ledger, [rec], v3_rule(10), n=1)
    snapshot_v3a = copy.deepcopy(ledger.get(kids3a[0]))
    co3b, kids3b, _ = run(ledger, [rec], v3_rule(60), n=2)
    cp_b = ledger.get(kids3b[0])['checkpoint']
    related = {e['item_key']: e for e in cp_b['related_assessments']}
    assert set(related) == {kids1[0], kids3a[0]}      # every OTHER assessment of the same record, not itself
    assert all(e['relation'] == 'OTHER_ASSESSMENT_OF_SAME_RECORD' for e in related.values())
    assert related[kids1[0]]['rule_version'] == ls.RULE_V1 and related[kids3a[0]]['rule_version'] == ls.RULE_V3
    assert related[kids3a[0]]['config_sha256'] == ledger.get(kids3a[0])['checkpoint']['config_sha256']
    blob = json.dumps(cp_b['related_assessments']).lower() + json.dumps(sp.assessment_history(items(ledger), cp_b['related_assessments'] and ledger.get(kids3b[0])['subject'], cp_b['record_sha256'])).lower()
    for word in ('supersed', 'current', 'latest', 'preferred', 'replaced', 'obsolete'):
        assert word not in blob
    assert ledger.get(kids1[0]) == snapshot_v1 and ledger.get(kids3a[0]) == snapshot_v3a      # earlier items are byte-for-byte untouched by a later assessment


def test_assessment_history_is_stable_unordered_by_time_and_scoped_to_one_record_and_subject(ledger):
    a, b = record('01768/26', 'Erection of 49 dwellings'), record('01757/26', 'ERECTION OF TWO STOREY RESIDENTIAL BUILDING COMPRISING 6 SELF CONTAINED FLATS')
    run(ledger, [a, b], None, n=0)
    run(ledger, [a, b], v3_rule(10), n=1)
    run(ledger, [a], v3_rule(60), n=2)
    subject = dict(kind='APPLICATION', council='bolton', reference='01768/26')
    hist = sp.assessment_history(items(ledger), subject, digest(a))
    assert [(h['rule_version'], h['config_sha256'] or '') for h in hist] == sorted((h['rule_version'], h['config_sha256'] or '') for h in hist)
    assert len(hist) == 3 and Counter(h['rule_version'] for h in hist) == Counter({ls.RULE_V1: 1, ls.RULE_V3: 2})
    assert sp.assessment_history(list(reversed(items(ledger))), subject, digest(a)) == hist      # the order does not depend on storage order
    assert len(sp.assessment_history(items(ledger), dict(subject, reference='01757/26'), digest(b))) == 2
    assert sp.assessment_history(items(ledger), subject, digest(b)) == []      # another record's digest never matches
    assert all(set(h) == {'item_key', 'contract', 'rule_version', 'config_sha256', 'record_sha256', 'routing_authority', 'routing_outcome', 'relation'} for h in hist)


def test_a_newer_screening_version_does_not_touch_stored_factual_evidence(ledger):
    """A FACTUAL_REFRESH item's checkpoint (the factual evidence) is not rewritten when a later screening version assesses the same record."""
    rec = record('01768/26', 'Erection of 49 dwellings')
    co1, kids1, _ = run(ledger, [rec], None, n=0)
    fact = ledger.enqueue(dict(kind='APPLICATION', council='bolton', reference='01768/26'), 'FACTUAL_REFRESH', contract='fixture-fact', dependencies=[kids1[0]])
    ledger.grant('INGESTION_TEST_f', [fact], contracts=['fixture-fact'], expires_at=ledger.clock() + 600)
    fc = ledger.claim(fact, 'w', 'INGESTION_TEST_f')
    ledger.checkpoint(fc, dict(kind='DETAIL_RECEIPT_V1', evidence='retained'))
    before = copy.deepcopy(ledger.get(fact))
    run(ledger, [rec], v3_rule(), n=1)
    assert ledger.get(fact) == before


# ------------------------------------------------------------------ eligibility: the two identity gates
def test_eligibility_helper_is_version_aware_and_fails_closed():
    v3 = lambda adm: dict(rule_version=ls.RULE_V3, routing_authority='count_assessment', count_assessment=dict(admission=adm), disposition='SUPPORTED_PROCESSING_PRIORITY')
    assert [adm for adm in sorted(ls.ROUTING_VOCABULARY[ls.RULE_V3]) if ls.identity_admission_eligible(v3(adm))] == ['ADMIT_FOR_ASSESSMENT', 'ADMIT_SCHEME']
    v1 = lambda d, **extra: dict(rule_version=ls.RULE_V1, disposition=d, **extra)
    assert [d for d in sorted(ls.ROUTING_VOCABULARY[ls.RULE_V1]) if ls.identity_admission_eligible(v1(d))] == ['RELATED_APPLICATION_FOLLOW_THROUGH', 'SUPPORTED_PROCESSING_PRIORITY']
    assert ls.identity_admission_eligible(dict(disposition='SUPPORTED_PROCESSING_PRIORITY'))      # the legacy checkpoint shape the existing tests build is read as v1
    for bad in (None, {}, [], 'ADMIT_SCHEME', dict(disposition='INSUFFICIENT_EVIDENCE'), dict(rule_version='other', disposition='SUPPORTED_PROCESSING_PRIORITY'),
                dict(rule_version=ls.RULE_V3, disposition='SUPPORTED_PROCESSING_PRIORITY'),      # v3 without its authority label: the informational v1 disposition must not route
                dict(rule_version=ls.RULE_V3, routing_authority='disposition', count_assessment=dict(admission='ADMIT_SCHEME')),
                dict(rule_version=ls.RULE_V3, routing_authority='count_assessment', count_assessment=dict(admission='ADMIT_SCHEMES')),
                dict(rule_version=ls.RULE_V3, routing_authority='count_assessment', count_assessment=dict(admission=['ADMIT_SCHEME'])),
                dict(rule_version=ls.RULE_V1, disposition='ADMIT_SCHEME'), v1('SUPPORTED_PROCESSING_PRIORITY', routing_authority='count_assessment'),
                dict(rule_version=ls.RULE_V3, routing_authority='count_assessment', count_assessment=dict(admission='SUPPORTED_PROCESSING_PRIORITY'))):
        assert ls.identity_admission_eligible(bad) is False, bad


def gate_setup(engine, proposal, *, rule=None, supported=True):
    """The existing new-identity path (tests/test_discovery_ingestion_operational.py::setup_new), with the parent SCREENING item produced by the REAL coordinator under `rule`."""
    install(engine)
    l = Ledger(engine)
    target, raw, packet = projected(summary('01780/26', status='Decided', decision='Approve', date='Mon 28 Sep 2026') if supported else summary('01780/26', status='Awaiting decision', omit=('Decision', 'Decision Issued Date')))
    e = replace(envelope(), reference=target['reference'], displayed_references=(target['reference'],), source_url=target['source_url'], source_record_id=target['source_identifier'])
    rec = record(e.reference, proposal, source_url=e.source_url, source_record_id=e.source_record_id)
    contract = accepted_idox_new_identity('bolton-existing-coupled-new', target)
    co = Coordinator(l, {contract.name: contract}, screening_rules=registry(rule))
    claim, receipt = capture(l, [rec])
    (parent,) = co._materialize(claim, receipt)
    (screen,) = screen_all(l, co, [parent]).values()
    key = l.enqueue(dict(kind='APPLICATION', council='bolton', reference=e.reference), 'FACTUAL_REFRESH', contract=contract.name, dependencies=[parent])
    l.grant('INGESTION_TEST_new', [key], contracts=[contract.name], expires_at=l.clock() + 600, writes=2)
    return l, co, key, e, raw, parent, screen


@pytest.mark.parametrize('proposal,admission', [('Erection of 49 dwellings', 'ADMIT_SCHEME'), ('Outline application for up to 50 dwellings', 'ADMIT_FOR_ASSESSMENT')])
def test_both_v3_admission_outcomes_create_only_a_pending_identity_through_the_existing_path(engine, proposal, admission):
    l, co, k, e, raw, parent, screen = gate_setup(engine, proposal, rule=v3_rule())
    assert ls.routing_of(screen) == ('count_assessment', admission)
    result = co.new_identity(l.claim(k, 'worker', 'INGESTION_TEST_new'), envelope=e, council=get_council('bolton'), source=raw)
    assert result['outcome'] == 'SUPPORTED_FACTS_VERIFIED' and result['unit_facts'] == 'NOT_WRITTEN'      # the existing factual-admission gate still ran and still decided
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Application)) == 1
        a = s.scalar(select(Application))
        assert a.estimated_unit_count is None and a.site_id is None and a.status_verified_at is not None      # no count written, no qualification confirmed, no Site link
        assert a.unit_confirmation_status != 'CONFIRMED'
    assert l.get(parent)['checkpoint']['count_assessment']['proposed_total'] in (49, 'UP_TO:50')      # the assessment stays on the screening item; it is not copied onto the Application
    with pytest.raises(Denied):
        l.claim(k, 'duplicate', 'INGESTION_TEST_new')


@pytest.mark.parametrize('proposal', ['Erection of 5 dwellings',                      # RETAIN_BELOW_THRESHOLD
                                      'Erection of 36 dwellings, 18 houses and 18 flats',      # ROUTE_COUNT_UNCONFIRMED (v1: SUPPORTED_PROCESSING_PRIORITY)
                                      'Reserved matters pursuant to outline 91352/14 for 120 dwellings',      # ROUTE_COUNT_UNCONFIRMED (v1: RELATED_APPLICATION_FOLLOW_THROUGH)
                                      'Non material amendment to application 00284/26 to amend fenestration',      # RETAIN_RELATED_TO_PARENT
                                      'Installation of 1 no. air handling unit and ducting',      # RETAIN_NOT_RESIDENTIAL_SUPPLY
                                      'Residential development of land at Mill Lane'])      # ROUTE_COUNT_UNCONFIRMED (v1: SUPPORTED_PROCESSING_PRIORITY)
def test_a_v3_result_that_is_not_admitted_never_creates_an_identity_even_when_its_v1_disposition_would_have(engine, proposal):
    l, co, k, e, raw, parent, screen = gate_setup(engine, proposal, rule=v3_rule())
    assert ls.routing_of(screen)[1] not in ('ADMIT_SCHEME', 'ADMIT_FOR_ASSESSMENT')
    claim = l.claim(k, 'worker', 'INGESTION_TEST_new')
    calls = []
    with pytest.raises(Denied, match='SELECTIVE_SCREENING_REQUIRED'):
        co.new_identity_source(claim, envelope=e, council=get_council('bolton'), supervised_reader=lambda row: calls.append(row))      # the gate before any source call
    assert calls == []      # no source call was made
    with pytest.raises(Denied, match='SELECTIVE_SCREENING_REQUIRED'):
        co.new_identity(claim, envelope=e, council=get_council('bolton'), source=raw)      # and the gate in new_identity.execute
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Application)) == 0


def test_every_existing_admission_check_still_applies_to_a_v3_admitted_item(engine):
    # unsupported source: the factual gate refuses even though screening admitted the item
    l, co, k, e, raw, parent, screen = gate_setup(engine, 'Erection of 49 dwellings', rule=v3_rule(), supported=False)
    assert ls.routing_of(screen)[1] == 'ADMIT_SCHEME'
    result = co.new_identity(l.claim(k, 'worker', 'INGESTION_TEST_new'), envelope=e, council=get_council('bolton'), source=raw)
    assert result['identity'] == 'NOT_CREATED' and l.get(k)['state'] == 'UNSUPPORTED_CONTRACT'
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Application)) == 0


@pytest.mark.parametrize('break_it', ['source_url', 'source_record_id', 'parent_state', 'subject'])
def test_source_binding_and_parent_checks_are_unchanged_for_v3(engine, break_it):
    l, co, k, e, raw, parent, screen = gate_setup(engine, 'Erection of 49 dwellings', rule=v3_rule())
    claim = l.claim(k, 'worker', 'INGESTION_TEST_new')
    with l.engine.begin() as c:
        if break_it == 'parent_state':
            c.execute(W.update().where(W.c.key == parent).values(state='QUEUED'))
        elif break_it == 'subject':
            c.execute(W.update().where(W.c.key == parent).values(subject=dict(kind='APPLICATION', council='bolton', reference='OTHER/26')))
        else:
            c.execute(W.update().where(W.c.key == parent).values(checkpoint=dict(screen, **{break_it: 'OTHER'})))      # the screening result is v3-admitted, but bound to a different source
    refused = 'SELECTIVE_SCREENING_REQUIRED|SCREENING_SOURCE_BINDING'      # either existing denial; both are older than v3 and both still fire
    with pytest.raises(Denied, match=refused):
        co.new_identity_source(claim, envelope=e, council=get_council('bolton'), supervised_reader=lambda row: pytest.fail('source called'))
    with pytest.raises(Denied, match=refused):
        co.new_identity(claim, envelope=e, council=get_council('bolton'), source=raw)
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Application)) == 0


def test_a_v1_screened_item_still_reaches_the_same_identity_path_unchanged(engine):
    l, co, k, e, raw, parent, screen = gate_setup(engine, 'Erection of 49 dwellings', rule=None)
    assert screen['rule_version'] == ls.RULE_V1 and screen['disposition'] == 'SUPPORTED_PROCESSING_PRIORITY'
    result = co.new_identity(l.claim(k, 'worker', 'INGESTION_TEST_new'), envelope=e, council=get_council('bolton'), source=raw)
    assert result['outcome'] == 'SUPPORTED_FACTS_VERIFIED'


# ------------------------------------------------------------------ investigation requirements: recorded, non-executable, complete
def stored_examples(ledger):
    recs = [record('EX/%03d' % i, e['proposal']) for i, e in enumerate(e for e in EXAMPLES if 'records' not in e)]
    return recs, run(ledger, recs, v3_rule(10), n=0)


def test_every_unconfirmed_and_every_qualified_maximum_result_has_a_non_executable_requirement(ledger):
    recs = bolton_records()
    reserved = [record('RM/%d' % i, t) for i, t in enumerate(['Reserved matters pursuant to outline 91352/14 for 120 dwellings', 'Approval of reserved matters pursuant to 91352/14'])]
    qualified = [record('UP/1', 'Outline application for up to 50 dwellings')]
    ex_recs, _ = stored_examples(ledger)
    run(ledger, recs + reserved + qualified, v3_rule(10), n=1)
    stored = items(ledger)
    reqs = sp.investigation_requirements(stored)
    expected = set()
    for it in stored:
        cp = it['checkpoint']
        if cp and cp.get('rule_version') == ls.RULE_V3 and cp['count_assessment']['admission'] in ('ROUTE_COUNT_UNCONFIRMED', 'ADMIT_FOR_ASSESSMENT'):
            expected.add(it['key'])
    assert len(expected) >= 4 + 2 + 1      # the four Bolton unknowns, the reserved matters and the qualified maximum, plus the examples
    unusable = [record('UN/1', ''), record('UN/2', 'x' * 9000)]
    run(ledger, unusable, v3_rule(10), n=2)
    stored = items(ledger)
    reqs = sp.investigation_requirements(stored)
    for it in stored:
        cp = it['checkpoint']
        if cp and cp.get('rule_version') == ls.RULE_V3 and cp['count_assessment']['admission'] == 'RETAIN_UNUSABLE_PROPOSAL':
            expected.add(it['key'])
    assert {r['assessment_item'] for r in reqs if r['requirement_kind'] == 'PROPOSAL_REFETCH_OR_REVIEW'} == {k for k in expected if ls.routing_of(ledger.get(k)['checkpoint'])[1] == 'RETAIN_UNUSABLE_PROPOSAL'} and len(unusable) == 2
    assert {r['assessment_item'] for r in reqs} == expected      # set equality: nothing uncertain is dropped, nothing certain is added
    assert reqs and all(r['executable'] is False and r['executor'] == 'NONE' and r['note'] == sp.NOTE for r in reqs)
    for r in reqs:
        assert 'no executor exists' in r['note'] and r['requirement_kind']
    kinds = Counter(r['requirement_kind'] for r in reqs)
    assert kinds['PARENT_REFERENCE_RESOLUTION'] >= 2 and kinds['COUNT_FROM_PHASE_DOCUMENTS'] >= 2 and kinds['TARGETED_DOCUMENT_EXTRACTION'] >= 1 and kinds['COUNT_CONFIRMATION'] >= 4
    by_item = {}
    for r in reqs:
        by_item.setdefault(r['assessment_item'], set()).add(r['requirement_kind'])
    for it in stored:
        cp = it['checkpoint']
        if cp and cp.get('rule_version') == ls.RULE_V3 and cp['count_assessment']['reason'] == 'RESERVED_MATTERS_WITHOUT_STATED_COUNT':
            assert by_item[it['key']] == {'PARENT_REFERENCE_RESOLUTION', 'COUNT_FROM_PHASE_DOCUMENTS'}


def test_requirements_never_copy_a_parent_figure_into_a_total_and_recording_them_changes_nothing(ledger):
    reserved = record('RM/1', 'Reserved matters pursuant to outline 91352/14 for 120 dwellings')
    run(ledger, [reserved], v3_rule(10))
    before = items(ledger)
    reqs = sp.investigation_requirements(before)
    after = items(ledger)
    assert before == after      # projection is read-only: nothing was written, scheduled or executed
    for r in reqs:
        cp = next(i['checkpoint'] for i in before if i['key'] == r['assessment_item'])
        assert cp['count_assessment']['proposed_total'] == 'NOT_ESTABLISHED' and cp['count_assessment']['approved_total'] == 'NOT_ESTABLISHED'
        assert 'count' not in r and 'proposed_total' not in r and 'total' not in r
        if r['parent_context']:
            assert r['parent_context']['relation'] == 'CONTEXT_ONLY'
    with ledger.engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(W).where(W.c.task.in_(['DISCOVERY', 'FACTUAL_REFRESH']))) == 0      # recording a requirement created no investigation work


def test_unlisted_reason_codes_still_produce_a_requirement_and_v1_items_produce_none(ledger):
    run(ledger, [record('A/1', 'Erection of apartments')], None, n=0)
    assert sp.investigation_requirements(items(ledger)) == []      # v1 results carry no count assessment: nothing is invented for them
    co, kids, res = run(ledger, [record('A/1', 'Erection of apartments')], v3_rule(), n=1)
    forged = [dict(it) for it in items(ledger) if it['key'] in kids]
    forged[0]['checkpoint'] = copy.deepcopy(forged[0]['checkpoint'])
    forged[0]['checkpoint']['count_assessment']['reason'] = 'A_REASON_NOBODY_LISTED'
    (req,) = sp.investigation_requirements(forged)
    assert req['requirement_kind'] == 'REVIEW_REQUIRED' and req['executable'] is False


def test_every_reason_the_assessor_gives_for_an_unconfirmed_count_has_a_requirement_kind():
    from app.ingestion import count_assessment as ca
    reasons = set()
    for e in EXAMPLES:
        if 'records' in e:
            continue
        a = ca.assess_proposal(e['proposal'], proposal_state=e['proposal_state'])
        if a['admission'] == 'ROUTE_COUNT_UNCONFIRMED':
            reasons.add(a['reason'])
    assert reasons and reasons <= set(sp.REQUIREMENT_KINDS)      # a new unconfirmed reason that the table does not know about is caught here, not silently generalised


# ------------------------------------------------------------------ the verified Bolton fixture and provenance
def test_the_bolton_fixture_is_the_verified_projection_and_reproduces_the_recorded_v1_aggregate():
    prov = json.loads(PROVENANCE.read_text(encoding='utf-8'))
    raw = FIXTURE.read_bytes().replace(bytes([13,10]), bytes([10]))      # the blob is LF; a Windows autocrlf checkout must hash the same
    assert hashlib.sha256(raw).hexdigest() == prov['fixture_sha256'] == '9f45362584672f41d4b0a76fe01a5b081bc5120123b11108bd879f733846a268'
    recs = json.loads(raw)
    assert len(recs) == prov['record_count'] == 24 and all(set(r) == {'reference', 'proposal', 'address'} for r in recs) and len({r['reference'] for r in recs}) == 24
    agg = Counter(ls.screen_row(r)['disposition'] for r in bolton_records())
    recorded = prov['recorded_v1_aggregate']
    assert agg == Counter({k: recorded[k] for k in ('INSUFFICIENT_EVIDENCE', 'RELATED_APPLICATION_FOLLOW_THROUGH', 'SUPPORTED_PROCESSING_PRIORITY')})
    assert sum(len(ls.screen_row(r)['citations']['occurrences']) for r in bolton_records()) == recorded['citation_occurrences'] == 3
    assert sum(1 for r in bolton_records() if ls.screen_row(r)['proposal_usable']) == recorded['proposal_usable'] == 24
    assert prov['origin']['capture_file_sha256'] == '5525be5a6b5fc3fdfac43849bc502cd05c0c9023da1440627b975672fe55013a'


def test_bolton_window_stored_under_v3_is_traceable_and_routes_each_record_once(ledger):
    records = bolton_records()
    co, children, results = run(ledger, records, v3_rule(10))
    assert len(children) == 24 and len(set(children)) == 24
    routed = Counter(ls.routing_of(cp)[1] for cp in results.values())
    assert routed == Counter(RETAIN_NOT_RESIDENTIAL_SUPPLY=16, ROUTE_COUNT_UNCONFIRMED=4, RETAIN_RELATED_TO_PARENT=2, ADMIT_SCHEME=1, RETAIN_BELOW_THRESHOLD=1)
    assert sum(ls.identity_admission_eligible(cp) for cp in results.values()) == 1      # only the 49-dwelling scheme may proceed to a pending identity
    for key, cp in results.items():
        row = ledger.get(key)
        assert row['state'] == 'COMPLETE' and cp['record_sha256'] == digest(next(r for r in records if r['reference'] == row['subject']['reference']))
        assert cp['config_sha256'] == digest(v3_rule(10).config())


# ------------------------------------------------------------------ rollback and containment
def test_switching_back_to_v1_keeps_every_v3_assessment_and_history_readable(ledger):
    rec = record('01768/26', 'Erection of 49 dwellings')
    co3, kids3, _ = run(ledger, [rec], v3_rule(), n=0)
    snapshot = copy.deepcopy(ledger.get(kids3[0]))
    co1, kids1, _ = run(ledger, [rec], None, n=1)      # the next run simply registers nothing: v1
    assert ledger.get(kids3[0]) == snapshot and kids1 != kids3
    hist = sp.assessment_history(items(ledger), snapshot['subject'], digest(rec))
    assert {h['item_key'] for h in hist} == {kids1[0], kids3[0]}


# Slice 1 allowed the disposable coordinator and the read-only projections. The offline production connection (PR #173 implementation) adds exactly these explicit, default-off consumers; the runner (which prepares and
# registers real work) and the installed worker.sql (the original definition; the replacement exists only as derived text) still know nothing about v3.
FILES_THAT_MAY_SELECT_OR_READ_V3 = {'app/ingestion/coordinator.py', 'app/ingestion/screening_projection.py', 'app/ingestion/sql_ledger.py', 'verification/ingestion_storage/operational_controller.py',
                                    'verification/ingestion_storage/operational_owner.py', 'verification/ingestion_storage/screening_v3_grant.py', 'verification/ingestion_storage/screening_v3_worker_sql.py'}
HELD = ['verification/ingestion_storage/operational_runner.py', 'docs/design/ingestion-operational-20261016/worker.sql']


def test_only_the_slice_one_files_reference_v3_and_every_held_production_path_is_untouched_by_it():
    import re
    pattern = re.compile(r'RULE_V3|screening-assessment-v3|listing-screen-v3|identity_admission_eligible|screening_projection|ScreeningRule|routing_of|ingestion\.count_(?:assessment|evidence)')
    offenders = set()
    for path in list((ROOT / 'app').rglob('*.py')) + list((ROOT / 'verification').rglob('*.py')):
        if path.name in ('listing_screening.py', 'count_assessment.py', 'count_evidence.py'):
            continue
        if pattern.search(path.read_text(encoding='utf-8', errors='ignore')):
            offenders.add(path.relative_to(ROOT).as_posix())
    assert offenders <= FILES_THAT_MAY_SELECT_OR_READ_V3 | {'app/ingestion/new_identity.py'}, offenders
    for held in HELD:
        text = (ROOT / held).read_text(encoding='utf-8', errors='ignore')
        assert not pattern.search(text) and 'listing-screen-v3' not in text, held      # production SQL, grants, controller and owner knowledge of v3: none
    assert "contract='listing-screen-v1'" not in (ROOT / 'app/ingestion/coordinator.py').read_text(encoding='utf-8')      # the hard-coded contract is gone from the disposable path


# ------------------------------------------------------------------ review hardening
def test_a_screening_rule_is_frozen_after_construction():
    rule = v3_rule(10)
    for name in ('unit_threshold', 'rule_version', '_config', 'extra'):
        with pytest.raises(AttributeError):
            setattr(rule, name, 99)
    assert rule.config()['unit_threshold'] == 10
    rule.config()['unit_threshold'] = 99      # a returned copy cannot change the frozen binding
    assert rule.config()['unit_threshold'] == 10


def test_eligibility_checks_the_item_it_is_given_against_the_result(ledger):
    co, (child,), (cp,) = (lambda r: (r[0], r[1], list(r[2].values())))(run(ledger, [record('01768/26', 'Erection of 49 dwellings')], v3_rule()))
    item = ledger.get(child)
    assert ls.identity_admission_eligible(cp, item)
    assert not ls.identity_admission_eligible(cp, dict(item, contract=V1))      # contract disagrees with the result's rule version
    assert not ls.identity_admission_eligible(cp, dict(item, revision='0' * 64))      # revision disagrees with the recorded assessment revision
    assert not ls.identity_admission_eligible(dict(disposition=['SUPPORTED_PROCESSING_PRIORITY']))      # unhashable legacy value: a clean False


def test_related_assessments_are_capped_and_report_the_true_total(ledger, monkeypatch):
    import app.ingestion.coordinator as cm
    monkeypatch.setattr(cm, 'RELATED_ASSESSMENTS_CAP', 2)
    rec = record('01768/26', 'Erection of 49 dwellings')
    for n, t in enumerate((10, 20, 30, 40)):
        co, kids, res = run(ledger, [rec], v3_rule(t), n=n)
    (cp,) = res.values()
    assert len(cp['related_assessments']) == 2 and cp['related_assessments_total'] == 3


# ------------------------------------------------------------------ legacy fallback cannot be used to launder a v3 item
def stripped(cp, *fields):
    return {k: v for k, v in cp.items() if k not in fields}


def test_a_v3_item_with_its_version_and_authority_fields_removed_is_ineligible_but_historical_v1_still_works(ledger):
    co, (child,), (cp,) = (lambda r: (r[0], r[1], list(r[2].values())))(run(ledger, [record('01768/26', 'Erection of 49 dwellings')], v3_rule()))
    item = ledger.get(child)
    assert cp['disposition'] == 'SUPPORTED_PROCESSING_PRIORITY'      # the informational v1 disposition looks eligible
    for fields in (('rule_version', 'routing_authority'), ('rule_version',), ('routing_authority', 'count_assessment')):
        forged = stripped(cp, *fields)
        assert not ls.identity_admission_eligible(forged, item), fields
    legacy = stripped(cp, 'rule_version', 'routing_authority', 'count_assessment')
    assert not ls.identity_admission_eligible(legacy, item)      # v3 contract + legacy shape
    assert not ls.identity_admission_eligible(legacy, dict(item, contract='listing-screen-v9'))
    assert ls.identity_admission_eligible(legacy, dict(item, contract=V1))      # a valid v1 item
    for unknown in ('fixture-screen', 'retained-fixture-v1', 'listing-screen-v1 ', 'LISTING-SCREEN-V1', 'screen', '', None, 7):
        assert not ls.identity_admission_eligible(legacy, dict(item, contract=unknown)), unknown      # arbitrary or unknown contracts, inside or outside the listing-screen family, are refused
    assert ls.identity_admission_eligible(legacy)      # no item supplied: unchanged helper behaviour


@pytest.mark.parametrize('fields', [('rule_version', 'routing_authority'), ('rule_version',), ('routing_authority', 'count_assessment')])
def test_both_identity_gates_refuse_a_v3_item_whose_version_fields_were_removed(engine, fields):
    l, co, k, e, raw, parent, screen = gate_setup(engine, 'Erection of 49 dwellings', rule=v3_rule())
    assert screen['disposition'] == 'SUPPORTED_PROCESSING_PRIORITY'
    claim = l.claim(k, 'worker', 'INGESTION_TEST_new')
    with l.engine.begin() as c:
        c.execute(W.update().where(W.c.key == parent).values(checkpoint=stripped(screen, *fields)))
    calls = []
    with pytest.raises(Denied, match='SELECTIVE_SCREENING_REQUIRED'):
        co.new_identity_source(claim, envelope=e, council=get_council('bolton'), supervised_reader=lambda row: calls.append(row))
    assert calls == []
    with pytest.raises(Denied, match='SELECTIVE_SCREENING_REQUIRED'):
        co.new_identity(claim, envelope=e, council=get_council('bolton'), source=raw)
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Application)) == 0
