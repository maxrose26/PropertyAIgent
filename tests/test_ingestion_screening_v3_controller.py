"""Controller wiring for an explicitly registered v3 rule (proposal section 2.4): the nomination path keeps every existing identity and factual check, and `assess_retained` is a source-free, write-free,
verify-everything assessment of the retained capture. Disposable SQLite ledger and application database here; the real SQL and batch path is in test_ingestion_screening_v3_pg.py."""
from dataclasses import replace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_council
from app.db.models import Application
from app.ingestion import batching
from app.ingestion import listing_screening as ls
from app.ingestion.coordinator import Coordinator
from app.ingestion.idox_adapter import IdoxListingContract
from app.ingestion.ledger import DEFAULT_LIMITS, Denied, Ledger, digest
from app.ingestion.schema import install
from tests.test_discovery_admission import engine, envelope
from tests.test_discovery_idox_window import FORM, Response, page
from tests.test_discovery_ingestion_ledger import outer
from tests.test_discovery_initial_application_contract import projected
from tests.test_ingestion_retained_capture_reconciliation import CAPTURE_CHECKPOINT, CAPTURE_KEY, identities, retained
from verification.direct_reference.fixtures import summary
from verification.discovery.idox_window import WindowConfig, run
from verification.ingestion_storage.new_identity_contract import accepted_idox_new_identity
from verification.ingestion_storage.operational_controller import AcceptanceBinding, assess_retained, execute

V3 = ls.ScreeningRule(ls.RULE_V3, unit_threshold=10, link_related=False)


def listing_audit(target, proposal):
    cfg = WindowConfig(max_transport_retries=0)
    echo = FORM.replace(b'name="date(applicationReceivedStart)" value=""', b'name="date(applicationReceivedStart)" value="28/09/2026"').replace(b'name="date(applicationReceivedEnd)" value=""', b'name="date(applicationReceivedEnd)" value="04/10/2026"')
    refs = (target['reference'],)
    body = page(first=1, last=1, total=1, refs=refs).replace(b'keyVal=K0', ('keyVal=' + target['source_identifier']).encode()).replace(b'Outline residential development, scale unknown', proposal.encode())
    bodies = iter([FORM, body, body, echo])
    return run(lambda *a, **k: Response(next(bodies)), cfg)


class BoundLedger(Ledger):
    def claim(self, key, owner='controller', authority='INGESTION_TEST_controller', lease_seconds=165):
        return super().claim(key, owner, authority, lease_seconds)


def prepared(engine, proposal, rule):
    install(engine)
    ledger = BoundLedger(engine)
    target, raw, _ = projected(summary('01780/26', status='Decided', decision='Approve', date='Mon 28 Sep 2026'))
    cfg = WindowConfig(max_transport_retries=0)
    contract = IdoxListingContract('controller-idox', cfg, 'a' * 64)
    audit = listing_audit(target, proposal)
    record = contract.project(audit, outer(), DEFAULT_LIMITS)['records'][0]
    root = ledger.enqueue({'kind': 'DISCOVERY_SCOPE', 'council': 'bolton', 'start': cfg.start.isoformat(), 'end': cfg.end.isoformat(), 'semantics': 'RECEIVED'}, 'DISCOVERY', contract=contract.name)
    revision = digest(record) if rule.rule_version == ls.RULE_V1 else ls.assessment_identity(record, rule)[3]
    child = ledger.enqueue({'kind': 'APPLICATION', 'council': 'bolton', 'reference': record['reference']}, 'SCREENING', contract=rule.contract(), revision=revision, dependencies=[root])
    fact = ledger.enqueue({'kind': 'APPLICATION', 'council': 'bolton', 'reference': record['reference']}, 'FACTUAL_REFRESH', contract='controller-fact', dependencies=[child])
    ledger.grant('INGESTION_TEST_controller', [root, child, fact], contracts=[contract.name, rule.contract(), 'controller-fact'], expires_at=ledger.clock() + 600, source_calls=2, writes=2, detail_source_keys=[fact])
    co = Coordinator(ledger, {contract.name: contract, 'controller-fact': accepted_idox_new_identity('controller-fact', target)}, screening_rules={rule.contract(): rule})
    env = replace(envelope(), reference=record['reference'], displayed_references=(record['reference'],), source_url=record['source_url'], source_record_id=record['source_record_id'])
    binding = AcceptanceBinding(root, child, fact, record['reference'], record['source_url'], record['source_record_id'], digest(record))
    return ledger, co, binding, audit, raw, env


def count_applications(engine):
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(Application))


def test_a_v3_admitted_nomination_reaches_the_existing_pending_identity_path_and_writes_no_count(engine):
    ledger, co, b, audit, raw, env = prepared(engine, 'Erection of 20 residential dwellings', V3)
    seen = []

    def detail(row):
        assert ledger.get(b.factual_key)['phase'] == 'SOURCE_INTENT'      # the existing authority-before-detail ordering is unchanged
        seen.append(1)
        return raw, outer()
    result = execute(co, b, listing_reader=lambda _: (audit, outer()), detail_reader=detail, envelope=env, council=get_council('bolton'))
    assert result['outcome'] == 'SUPPORTED_FACTS_VERIFIED' and len(seen) == 1
    screen = ledger.get(b.screening_key)
    assert screen['contract'] == 'listing-screen-v3' and ls.routing_of(screen['checkpoint']) == ('count_assessment', 'ADMIT_SCHEME') and screen['outcome'] == dict(outcome='ADMIT_SCHEME', retained=True)
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Application)) == 1
        a = s.scalar(select(Application))
        assert a.estimated_unit_count is None and a.site_id is None and a.status_verified_at is not None      # no dwelling count, no Site, no qualified scheme
    with pytest.raises(Denied):
        execute(co, b, listing_reader=lambda _: pytest.fail('replay'), detail_reader=detail, envelope=env, council=get_council('bolton'))      # no replay


def test_a_proposal_v1_would_have_admitted_but_v3_does_not_is_never_nominated(engine):
    text = 'Erection of 36 dwellings, 18 houses and 18 flats'
    assert ls.screen_row(retained()[1]['records'][0] | {'fields': dict(retained()[1]['records'][0]['fields'], proposal=dict(state='PRESENT_VALUE', value=text, locator='x', truncated=False))})['disposition'] == 'SUPPORTED_PROCESSING_PRIORITY'
    ledger, co, b, audit, raw, env = prepared(engine, text, V3)
    calls = []
    result = execute(co, b, listing_reader=lambda _: (audit, outer()), detail_reader=lambda _: calls.append(1), envelope=env, council=get_council('bolton'))
    assert result['outcome'] == 'DISCOVERY_SCREENING_ONLY_INSUFFICIENT_OR_EXCLUDED' and calls == [] and count_applications(engine) == 0      # no detail request, no identity


def test_v1_remains_the_default_and_behaves_as_before(engine):
    ledger, co, b, audit, raw, env = prepared(engine, 'Erection of 20 residential dwellings', ls.ScreeningRule(ls.RULE_V1))
    assert co.screening_contract == 'listing-screen-v1'
    result = execute(co, b, listing_reader=lambda _: (audit, outer()), detail_reader=lambda _: (raw, outer()), envelope=env, council=get_council('bolton'))
    assert result['outcome'] == 'SUPPORTED_FACTS_VERIFIED' and ledger.get(b.screening_key)['contract'] == 'listing-screen-v1' and count_applications(engine) == 1


def test_a_forged_v3_screening_receipt_is_refused_before_any_detail_request(engine):
    ledger, co, b, audit, raw, env = prepared(engine, 'Erection of 20 residential dwellings', V3)
    claim = ledger.claim(b.discovery_key, 'controller', 'INGESTION_TEST_controller')      # complete the root so the nomination screens retained rows
    co.idox_source(claim, lambda row: (audit, outer()))
    result = co.screening(ledger.claim(b.screening_key))
    forged = dict(result, count_assessment=dict(result['count_assessment'], admission='ROUTE_COUNT_UNCONFIRMED'))
    with ledger.engine.begin() as c:
        from app.ingestion.schema import WorkItem as W
        c.execute(W.update().where(W.c.key == b.screening_key).values(checkpoint=forged))
    frozen = replace(b, retained_capture_sha256=digest(ledger.get(b.discovery_key)['checkpoint']))
    calls = []
    with pytest.raises(Denied):
        execute(co, frozen, listing_reader=lambda _: pytest.fail('no refetch'), detail_reader=lambda _: calls.append(1), envelope=env, council=get_council('bolton'))
    assert calls == [] and count_applications(engine) == 0


# ------------------------------------------------------------------ assess_retained
def retained_ledger(engine):
    install(engine)
    ledger = Ledger(engine)
    _, receipt = retained()
    root, children, _, _, _ = identities(receipt)
    assert root['key'] == CAPTURE_KEY
    key = ledger.enqueue(dict(kind='DISCOVERY_SCOPE', council='bolton', start='2026-09-28', end='2026-10-04', semantics='RECEIVED'), 'DISCOVERY', contract='fixture-capture')
    ledger.grant('INGESTION_TEST_cap', [key], contracts=['fixture-capture'], expires_at=ledger.clock() + 600)
    claim = ledger.claim(key, 'w', 'INGESTION_TEST_cap')
    ledger.checkpoint(claim, receipt)
    v1 = Coordinator(ledger, {})
    kids = v1._materialize(claim, receipt)      # the earlier v1 assessments, materialised and screened first, exactly as in the retained run
    ledger.grant('INGESTION_TEST_v1', kids, contracts=['listing-screen-v1'], expires_at=ledger.clock() + 600)
    for k in kids:
        v1.screening(ledger.claim(k, 'w', 'INGESTION_TEST_v1'))
    return ledger, key, receipt, kids


class FakeBatches:
    """Stands in for the SQL batch path (tested for real in the PostgreSQL rehearsal): creates and screens the children of each v3 plan through the real coordinator."""
    def __init__(self, ledger, key, receipt, mutate=None):
        self.ledger, self.key, self.receipt, self.mutate, self.calls = ledger, key, receipt, mutate, []

    def __call__(self, coordinator, batch_key, check=lambda: None):
        plans = {p['key']: p for p in batching.batch_plans(self.key, self.receipt, coordinator.screening_rule)}
        plan = plans[batch_key]['checkpoint']['plan']
        self.calls.append(batch_key)
        children = []
        for record in self.receipt['records'][plan['first']:plan['last']]:
            revision = ls.assessment_identity(record, coordinator.screening_rule)[3]
            children.append(self.ledger.enqueue({'kind': 'APPLICATION', 'council': 'bolton', 'reference': record['reference']}, 'SCREENING', contract='listing-screen-v3', revision=revision, dependencies=[self.key]))
        authority = 'INGESTION_TEST_a%d' % len(self.calls)
        self.ledger.grant(authority, children, contracts=['listing-screen-v3'], expires_at=self.ledger.clock() + 600)
        for child in children:
            result = coordinator.screening(self.ledger.claim(child, 'w', authority))
            if self.mutate:
                self.mutate(self.ledger, child, result)
        return dict(outcome='BATCH_SCREENED')


def run_assess(ledger, key, receipt, kids, monkeypatch, *, rule=V3, mutate=None, capture_sha=CAPTURE_CHECKPOINT, batch_keys=None):
    fake = FakeBatches(ledger, key, receipt, mutate)
    monkeypatch.setattr(batching, 'process_batch', fake)
    co = Coordinator(ledger, {}, screening_rules={rule.contract(): rule})
    keys = batch_keys if batch_keys is not None else [p['key'] for p in batching.batch_plans(key, receipt, V3)]
    return assess_retained(co, key, capture_sha256=capture_sha, batch_keys=keys, preserved_keys=kids), fake


def test_assess_retained_assesses_all_24_records_source_free_and_preserves_everything_earlier(engine, monkeypatch):
    ledger, key, receipt, kids = retained_ledger(engine)
    v1_before = {k: digest(ledger.get(k)) for k in kids}
    capture_before = digest(ledger.get(key))
    result, fake = run_assess(ledger, key, receipt, kids, monkeypatch)
    assert result['outcome'] == 'SCREENING_V3_ASSESSED' and result['admission'] == 'NOT_ATTEMPTED' and result['b2'] == 'NOT_ATTEMPTED' and result['application_writes'] == 0 and result['source_calls'] == 0
    assert len(result['assessments']) == 24 and len(fake.calls) == 5
    assert sum(a['eligible'] for a in result['assessments']) == 1 and next(a for a in result['assessments'] if a['eligible'])['reference'] == '01768/26'
    assert {k: digest(ledger.get(k)) for k in kids} == v1_before and digest(ledger.get(key)) == capture_before      # earlier v1 assessments and the capture are byte-identical
    assert count_applications(engine) == 0      # no application write, no identity


def test_assess_retained_requires_an_explicit_v3_rule_and_the_exact_retained_capture(engine, monkeypatch):
    ledger, key, receipt, kids = retained_ledger(engine)
    with pytest.raises(Denied, match='V3_RULE_REQUIRED'):
        run_assess(ledger, key, receipt, kids, monkeypatch, rule=ls.ScreeningRule(ls.RULE_V1))
    with pytest.raises(Denied, match='RETAINED_CAPTURE_BINDING'):
        run_assess(ledger, key, receipt, kids, monkeypatch, capture_sha='0' * 64)
    with pytest.raises(Denied, match='EXACT_SCREENING_BATCH'):
        run_assess(ledger, key, receipt, kids, monkeypatch, batch_keys=[digest('x')])
    plans = [p['key'] for p in batching.batch_plans(key, receipt, V3)]
    with pytest.raises(Denied, match='EXACT_SCREENING_BATCH'):
        run_assess(ledger, key, receipt, kids, monkeypatch, batch_keys=plans[:4])      # a partial batch set is not the registered one
    with pytest.raises(Denied, match='EXACT_SCREENING_BATCH'):
        run_assess(ledger, key, receipt, kids, monkeypatch, batch_keys=[p['key'] for p in batching.batch_plans(key, receipt)])      # the v1 batches are not the v3 ones
    assert count_applications(engine) == 0


def test_a_forged_assessment_stops_the_run(engine, monkeypatch):
    from app.ingestion.schema import WorkItem as W
    forged = []

    def forge(ledger, child, result):
        if not forged:      # forge the first stored v3 receipt: claim an admission the assessment did not give
            forged.append(child)
            bad = dict(result, count_assessment=dict(result['count_assessment'], admission='ADMIT_SCHEME'))
            with ledger.engine.begin() as c:
                c.execute(W.update().where(W.c.key == child).values(checkpoint=bad))
    ledger, key, receipt, kids = retained_ledger(engine)
    with pytest.raises(Denied, match='FORGED_OR_MISMATCHED_ASSESSMENT'):
        run_assess(ledger, key, receipt, kids, monkeypatch, mutate=forge)


def test_the_preserved_rows_must_be_named_and_a_forged_coordinator_field_is_caught(engine, monkeypatch):
    from app.ingestion.schema import WorkItem as W
    ledger, key, receipt, kids = retained_ledger(engine)
    co = Coordinator(ledger, {}, screening_rules={V3.contract(): V3})
    keys = [p['key'] for p in batching.batch_plans(key, receipt, V3)]
    for bad in ((), None, [kids[0], kids[0]]):
        with pytest.raises(Denied, match='PRESERVED_KEYS_REQUIRED'):
            assess_retained(co, key, capture_sha256=CAPTURE_CHECKPOINT, batch_keys=keys, preserved_keys=bad)
    forged = []

    def forge(ledger_, child, result):
        if not forged:      # a stored receipt with a wrong source URL: routing is unaffected, but the stored evidence is not what the capture says
            forged.append(child)
            with ledger_.engine.begin() as c:
                c.execute(W.update().where(W.c.key == child).values(checkpoint=dict(result, source_url='https://example.invalid/forged')))
    with pytest.raises(Denied, match='FORGED_OR_MISMATCHED_ASSESSMENT'):
        run_assess(ledger, key, receipt, kids, monkeypatch, mutate=forge)


def test_a_modified_earlier_row_stops_the_run(engine, monkeypatch):
    from app.ingestion.schema import WorkItem as W
    ledger, key, receipt, kids = retained_ledger(engine)

    def touch(ledger, child, result):
        with ledger.engine.begin() as c:
            c.execute(W.update().where(W.c.key == kids[0]).values(next_action='TAMPERED'))
    with pytest.raises(Denied, match='PRESERVED_ROWS_CHANGED'):
        run_assess(ledger, key, receipt, kids, monkeypatch, mutate=touch)
