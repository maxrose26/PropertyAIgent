"""Explicit v3 options in the batch plans, the SQL ledger client and the owner grant (proposal sections 2.2 and 2.3). Offline: no database, network or council. v1 output is compared byte-for-byte with the registered historical identities."""
import json
from datetime import datetime, timezone

import pytest

from app.ingestion import listing_screening as ls
from app.ingestion.batching import batch_plans, _process_batch
from app.ingestion.ledger import Denied, digest
from app.ingestion.sql_ledger import SQLLedger
from tests.test_ingestion_retained_capture_reconciliation import CAPTURE_KEY, E, identities, retained
from verification.ingestion_storage.screening_v3_grant import apply_screening

V3 = ls.ScreeningRule(ls.RULE_V3, unit_threshold=10, link_related=False)
V1_OUTCOMES = ['SCREENED', 'ALREADY_KNOWN', 'INSUFFICIENT_EVIDENCE', 'SUPPORTED_PROCESSING_PRIORITY', 'RELATED_APPLICATION_FOLLOW_THROUGH', 'DEEPER_PROCESSING_EXCLUDED_FOR_THIS_SLICE']


def test_a_plan_without_screening_is_byte_identical_to_the_registered_v1_plans():
    _, receipt = retained()
    recorded = json.loads((E / 'reconciliation.json').read_bytes())['batches']
    plans = batch_plans(CAPTURE_KEY, receipt)
    assert [(p['key'], p['revision']) for p in plans] == [(b['key'], b['revision']) for b in recorded]      # the five registered batches, key for key
    assert all('screening' not in p['checkpoint']['plan'] for p in plans)
    assert batch_plans(CAPTURE_KEY, receipt, None) == plans


def test_an_explicit_v3_plan_has_new_identities_and_never_touches_the_v1_batches():
    _, receipt = retained()
    v1 = batch_plans(CAPTURE_KEY, receipt)
    v3 = batch_plans(CAPTURE_KEY, receipt, V3)
    assert len(v3) == len(v1) == 5
    assert not {p['key'] for p in v1} & {p['key'] for p in v3}      # distinct batch items: nothing is resumed, overwritten or shared
    binding, config_sha256 = ls.screening_plan_binding(V3)
    for a, b in zip(v1, v3):
        plan = b['checkpoint']['plan']
        assert plan['screening'] == binding == dict(contract='listing-screen-v3', config_sha256=config_sha256)
        assert b['revision'] == digest(plan) and b['contract'] == 'listing-batch-v1' and b['task'] == 'LISTING_METADATA'
        assert {k: v for k, v in plan.items() if k != 'screening'} == a['checkpoint']['plan']      # same capture, same rows
    assert v3[0]['dependencies'] == [CAPTURE_KEY] and v3[1]['dependencies'] == sorted([CAPTURE_KEY, v3[0]['key']])      # a chain among the new items only
    other = batch_plans(CAPTURE_KEY, receipt, ls.ScreeningRule(ls.RULE_V3, unit_threshold=11))
    assert not {p['key'] for p in v3} & {p['key'] for p in other}      # a different configuration is a different set of batches


def test_only_a_v3_rule_may_be_a_screening_selection():
    _, receipt = retained()
    for bad in (ls.ScreeningRule(ls.RULE_V1), 'listing-screen-v3', {'contract': 'listing-screen-v3'}, 3):
        with pytest.raises(ValueError, match='V3_SCREENING_RULE_REQUIRED'):
            batch_plans(CAPTURE_KEY, receipt, bad)


class Recorder(SQLLedger):
    """A SQLLedger whose database calls are replaced, to inspect exactly what batch_row sends to ingestion_worker_step."""
    def __init__(self):
        class Engine:
            class dialect:
                name = 'postgresql'

            def begin(self):
                import contextlib
                return contextlib.nullcontext(object())
        self.worker_engine, self.broker_engine, self.owner, self.authority, self.bindings, self.engine = Engine(), Engine(), 'w', 'a', {}, None
        self.sent = []

    def get(self, key):
        return dict(priority=50, limits={'rows': 60})

    def _limits(self, c):
        pass

    def _step(self, op, key, fence=0, payload=None, connection=None):
        self.sent.append((op, payload))
        return dict(checkpoint={'kind': 'BATCH_PROGRESS_V1'})


class Claim:
    key, fence, owner = 'b' * 64, 1, 'w'


def test_batch_row_builds_the_historical_v1_identity_without_a_binding_and_the_v3_identity_with_one():
    _, receipt = retained()
    capture, record = receipt, receipt['records'][3]
    plan1 = batch_plans(CAPTURE_KEY, receipt)[0]['checkpoint']['plan']
    plan3 = batch_plans(CAPTURE_KEY, receipt, V3)[0]['checkpoint']['plan']
    ledger = Recorder()
    key1, _ = ledger.batch_row(Claim, plan1, capture, record)
    child1 = ledger.sent[-1][1]['child']
    assert (child1['contract'], child1['revision'], key1) == ('listing-screen-v1', digest(record), child1['key'])
    expected1 = next(c for c in identities(receipt)[1] if c['subject']['reference'] == record['reference'])
    assert key1 == expected1['key']      # the key the owner registered for the v1 child
    key3, _ = ledger.batch_row(Claim, plan3, capture, record)
    child3 = ledger.sent[-1][1]['child']
    record_sha, config_sha = digest(record), plan3['screening']['config_sha256']
    assert child3['contract'] == 'listing-screen-v3' and child3['revision'] == digest(dict(record_sha256=record_sha, config_sha256=config_sha))
    assert key3 == child3['key'] == digest(dict(subject=child3['subject'], task='SCREENING', contract='listing-screen-v3', revision=child3['revision'])) and key3 != key1
    # the revision the python side sends is what assessment_identity gives the coordinator
    assert child3['revision'] == ls.assessment_identity(record, V3)[3]
    assert ledger.bindings[key3]['contract'] == 'listing-screen-v3' and ledger.bindings[key1]['contract'] == 'listing-screen-v1'
    for bad in (dict(contract='listing-screen-v1', config_sha256=config_sha), dict(contract='listing-screen-v3', config_sha256='xyz'), dict(contract='listing-screen-v3', config_sha256=config_sha, extra=1), 'v3'):
        with pytest.raises(Denied, match='SCREENING_PLAN_BINDING'):
            ledger.batch_row(Claim, dict(plan3, screening=bad), capture, record)


class StubCoordinator:
    def __init__(self, rule):
        self.screening_rule = rule

        class L:
            def get(inner, key):
                return self.row
        self.ledger = L()
        self.row = None


def batch_row(plan):
    return dict(contract='listing-batch-v1', task='LISTING_METADATA', state='QUEUED', revision=digest(plan), checkpoint=dict(kind='BATCH_PLAN_V1', plan=plan))


def test_process_batch_refuses_a_plan_whose_selection_differs_from_the_registered_rule():
    _, receipt = retained()
    plan1 = batch_plans(CAPTURE_KEY, receipt)[0]['checkpoint']['plan']
    plan3 = batch_plans(CAPTURE_KEY, receipt, V3)[0]['checkpoint']['plan']
    plan3_other = batch_plans(CAPTURE_KEY, receipt, ls.ScreeningRule(ls.RULE_V3, unit_threshold=11))[0]['checkpoint']['plan']
    for rule, plan in ((V3, plan1), (ls.ScreeningRule(ls.RULE_V1), plan3), (V3, plan3_other)):
        co = StubCoordinator(rule)
        co.row = batch_row(plan)
        with pytest.raises(Denied, match='BATCH_RULE_MISMATCH'):
            _process_batch(co, 'k')
    # the matching selections pass the check and stop later (no budget on the stub), proving the check is not over-eager
    for rule, plan in ((ls.ScreeningRule(ls.RULE_V1), plan1), (V3, plan3)):
        co = StubCoordinator(rule)
        co.row = batch_row(plan)
        with pytest.raises(Denied, match='LOGICAL_BATCH_BUDGET_REQUIRED'):
            _process_batch(co, 'k')


def test_a_v1_grant_is_untouched_and_a_v3_grant_adds_exactly_the_config_list_and_the_admission_vocabulary():
    grant = dict(completion_outcomes={'DISCOVERY': ['ENUMERATED_METADATA_RETAINED'], 'LISTING_METADATA': ['BATCH_SCREENED'], 'SCREENING': list(V1_OUTCOMES)})
    before = json.loads(json.dumps(grant))
    out = apply_screening(grant, V3)
    assert out is grant and set(grant) == {'completion_outcomes', 'screening_configs'}
    assert grant['screening_configs'] == [digest(V3.config())]
    assert grant['completion_outcomes']['SCREENING'][:6] == V1_OUTCOMES      # the v1 vocabulary is never reordered or reduced
    assert set(grant['completion_outcomes']['SCREENING']) - set(V1_OUTCOMES) == set(ls.ROUTING_VOCABULARY[ls.RULE_V3])
    assert grant['completion_outcomes']['DISCOVERY'] == before['completion_outcomes']['DISCOVERY'] and grant['completion_outcomes']['LISTING_METADATA'] == before['completion_outcomes']['LISTING_METADATA']
    with pytest.raises(ValueError, match='SCREENING_CONFIGS_ALREADY_SET'):
        apply_screening(grant, V3)
    for bad in (ls.ScreeningRule(ls.RULE_V1), None, 'v3'):
        with pytest.raises(ValueError, match='V3_SCREENING_RULE_REQUIRED'):
            apply_screening(json.loads(json.dumps(before)), bad)


def test_owner_register_builds_the_historical_grant_without_screening_and_the_v3_grant_with_it():
    pytest.importorskip('resource')      # the owner module imports the Linux-only `resource` module; this runs in the Linux CI job
    from verification.ingestion_storage.operational_owner import Owner, item
    owner = object.__new__(Owner)
    owner.expiry = owner.grant_expiry = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
    owner.bindings = dict(revision='r' * 40, workflow_sha256='w' * 64, manifest_sha256='m' * 64)
    _, receipt = retained()
    root, children, _, _, _ = identities(receipt)
    batches = [item({k: p[k] for k in ('subject', 'task', 'contract', 'revision')}, dependencies=p['dependencies'], checkpoint=p['checkpoint']) for p in batch_plans(CAPTURE_KEY, receipt)]
    b1, g1 = owner.build_grant(batches, [root, *children], capture_key=CAPTURE_KEY, source_calls=0)
    assert 'screening_configs' not in g1 and g1['completion_outcomes']['SCREENING'] == V1_OUTCOMES and g1['source_calls'] == 0 and g1['writes'] == 0
    b3_items = [item({k: p[k] for k in ('subject', 'task', 'contract', 'revision')}, dependencies=p['dependencies'], checkpoint=p['checkpoint']) for p in batch_plans(CAPTURE_KEY, receipt, V3)]
    v3_children = [item(dict(subject=c['subject'], task='SCREENING', contract='listing-screen-v3', revision=ls.assessment_identity(r, V3)[3]), dependencies=[CAPTURE_KEY]) for c, r in zip(children, receipt['records'])]
    b3, g3 = owner.build_grant(b3_items, [root, *v3_children], capture_key=CAPTURE_KEY, source_calls=0, screening=V3)
    assert g3['screening_configs'] == [digest(V3.config())] and set(g3['contracts']) == {'listing-batch-v1', 'listing-screen-v3', 'bolton-received-idox-coordinator-v1'}
    assert len(b3) == 30 and g3['source_calls'] == 0 and g3['writes'] == 0
    assert set(b1) & set(b3) == {root['key']}      # only the root capture binding is shared; every batch and child key differs from the registered v1 ones
    assert {k: v for k, v in g3.items() if k not in ('keys', 'contracts', 'bindings', 'completion_outcomes', 'screening_configs')} == {k: v for k, v in g1.items() if k not in ('keys', 'contracts', 'bindings', 'completion_outcomes')}
