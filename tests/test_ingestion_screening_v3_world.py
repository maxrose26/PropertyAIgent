"""The owner's pre-authority verification of the 30 retained rows against the pinned evidence (screening-v3 activation). Pure and offline: the rows are the ledger rows the retained run left, modelled as {key: (state, checkpoint)}
exactly as `Owner.read_items` returns them."""
import copy

import pytest

from app.ingestion import listing_screening as ls
from verification.ingestion_storage import retained_world as rw

V3 = ls.ScreeningRule(ls.RULE_V3, unit_threshold=10, link_related=False)
V1 = ls.ScreeningRule(ls.RULE_V1)


@pytest.fixture(scope='module')
def world():
    _, receipt = rw.retained()
    root, children, plans, batches, _ = rw.identities(receipt)
    rows = {root['key']: ('COMPLETE', copy.deepcopy(receipt))}
    for child, record in zip(children, receipt['records']):
        rows[child['key']] = ('COMPLETE', dict(V1.screen(record), source_url=record['source_url']))
    for batch in batches:
        rows[batch['key']] = ('COMPLETE', dict(kind='BATCH_PROGRESS_V1', plan=batch['checkpoint']['plan'], next=batch['checkpoint']['plan']['last'], children=[]))
    return receipt, rows


def test_the_untouched_retained_world_verifies_and_names_exactly_the_thirty_rows(world):
    receipt, rows = world
    keys = rw.verify_world(rows, receipt)
    assert len(keys) == 30 and len(set(keys)) == 30 and keys[0] == rw.CAPTURE_KEY
    new_keys = rw.verify_no_v3_rows(rows, receipt, V3)
    assert len(new_keys) == 29 and not set(new_keys) & set(keys)      # five new batch items and 24 v3 children, none of them a retained row


def mutated(world, key_index, change):
    receipt, rows = world
    rows = copy.deepcopy(rows)
    key = list(rows)[key_index]
    state, checkpoint = rows[key]
    rows[key] = change(state, checkpoint)
    return receipt, rows


@pytest.mark.parametrize('label,index,change,reason', [
    ('capture_missing', 0, lambda s, c: (None, None), 'RETAINED_ROW_MISSING'),
    ('capture_not_complete', 0, lambda s, c: ('QUEUED', c), 'RETAINED_CAPTURE_ALTERED'),
    ('capture_checkpoint_altered', 0, lambda s, c: (s, dict(c, cleanup='UNKNOWN')), 'RETAINED_CAPTURE_ALTERED'),
    ('capture_record_altered', 0, lambda s, c: (s, dict(c, records=[dict(c['records'][0], reference='X/1'), *c['records'][1:]])), 'RETAINED_CAPTURE_ALTERED'),
    ('assessment_missing', 1, lambda s, c: (None, None), 'RETAINED_ROW_MISSING'),
    ('assessment_not_complete', 5, lambda s, c: ('CLAIMED', c), 'RETAINED_ASSESSMENT_ALTERED'),
    ('assessment_disposition_altered', 7, lambda s, c: (s, dict(c, disposition='SUPPORTED_PROCESSING_PRIORITY' if c['disposition'] != 'SUPPORTED_PROCESSING_PRIORITY' else 'INSUFFICIENT_EVIDENCE')), 'RETAINED_ASSESSMENT_ALTERED'),
    ('assessment_checkpoint_empty', 9, lambda s, c: (s, {}), 'RETAINED_ASSESSMENT_ALTERED'),
    ('batch_missing', 25, lambda s, c: (None, None), 'RETAINED_ROW_MISSING'),
    ('batch_not_complete', 26, lambda s, c: ('DEFERRED', c), 'RETAINED_BATCH_ALTERED'),
    ('batch_plan_altered', 27, lambda s, c: (s, dict(c, plan=dict(c['plan'], first=c['plan']['first'] + 1))), 'RETAINED_BATCH_ALTERED'),
])
def test_a_missing_or_altered_retained_row_stops_the_run_before_any_authority(world, label, index, change, reason):
    receipt, rows = mutated(world, index, change)
    with pytest.raises(rw.WorldMismatch, match=reason):
        rw.verify_world(rows, receipt)


def test_existing_v3_rows_stop_the_run_so_it_is_made_once(world):
    receipt, rows = world
    _, batches, children = rw.v3_items(receipt, V3)
    for victim in (batches[0], children[0], children[-1]):
        with_victim = dict(rows)
        with_victim[victim['key']] = ('QUEUED', None)
        with pytest.raises(rw.WorldMismatch, match='V3_ROWS_ALREADY_PRESENT'):
            rw.verify_no_v3_rows(with_victim, receipt, V3)


def test_the_evidence_pin_is_checked_before_anything_is_rebuilt(monkeypatch, tmp_path):
    (tmp_path / 'capture').mkdir()
    for name in rw.PINS:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((rw.EVIDENCE / name).read_bytes())
    monkeypatch.setattr(rw, 'EVIDENCE', tmp_path)
    assert rw.retained()[1]['kind'] == 'LISTING_RECEIPT_V1'
    (tmp_path / 'capture/source.json').write_bytes((tmp_path / 'capture/source.json').read_bytes() + b' ')
    with pytest.raises(rw.WorldMismatch, match='EVIDENCE_FILE_NOT_AT_PINNED_HASH'):
        rw.retained()
