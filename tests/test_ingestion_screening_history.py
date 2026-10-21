"""Bounded, read-only, keyset-paginated history of one record's assessments (proposal section 4). SQLite here; the same function runs against the disposable PostgreSQL in test_ingestion_screening_v3_pg.py."""
import hashlib
import json

import pytest
from sqlalchemy import create_engine, event

from app.ingestion import screening_history as sh
from app.ingestion.ledger import DEFAULT_LIMITS
from app.ingestion.schema import WorkItem as W, install

SUBJECT = dict(kind='APPLICATION', council='bolton', reference='01768/26')
OTHER_SUBJECT = dict(kind='APPLICATION', council='bolton', reference='01757/26')
RECORD = hashlib.sha256(b'record-a').hexdigest()
OTHER_RECORD = hashlib.sha256(b'record-b').hexdigest()


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def row(key, *, subject=SUBJECT, contract='listing-screen-v3', revision=None, checkpoint=None, state='COMPLETE', outcome=None):
    return dict(key=key, subject=subject, task='SCREENING', contract=contract, revision=revision or sha('rev' + key), dependencies=[], priority=50, eligible_at=0, state=state, reason=None, next_action='NONE',
                limits=DEFAULT_LIMITS, authority=None, attempt_count=1, max_attempts=2, fence=1, owner=None, lease_until=None, phase='FINISHED', checkpoint=checkpoint, outcome=outcome)


def v1(n, record=RECORD, subject=SUBJECT):
    return row(sha('v1-%s-%s-%d' % (record[:6], subject['reference'], n)), subject=subject, contract='listing-screen-v1', revision=record, checkpoint={'rule_version': 'manchester-listing-screen-assessment-v1', 'disposition': 'INSUFFICIENT_EVIDENCE'}, outcome=dict(outcome='INSUFFICIENT_EVIDENCE', retained=True))


def v3(n, record=RECORD, subject=SUBJECT, screened=True):
    cp = {'rule_version': 'manchester-listing-screen-assessment-v3', 'record_sha256': record, 'config_sha256': sha('cfg%d' % n)} if screened else None
    return row(sha('v3-%s-%s-%s-%d' % (record[:6], subject['reference'], screened, n)), subject=subject, checkpoint=cp, outcome=dict(outcome='ADMIT_SCHEME', retained=True) if screened else None, state='COMPLETE' if screened else 'QUEUED')


@pytest.fixture
def engine():
    e = create_engine('sqlite:///:memory:')
    install(e)
    yield e
    e.dispose()


def seed(engine, rows):
    with engine.begin() as c:
        for r in rows:
            c.execute(W.insert().values(**r))


def traverse(engine, record=RECORD, subject=SUBJECT, page_size=None, between=None):
    pages, cursor = [], None
    while True:
        page = sh.history_page(engine, subject, record, cursor=cursor, page_size=page_size)
        pages.append(page)
        if between:
            between(len(pages))
        cursor = page['next_cursor']
        if cursor is None:
            return pages


def test_mixed_v1_and_v3_assessments_are_all_returned_without_skips_or_duplicates_across_pages(engine):
    matching = [v1(i) for i in range(7)] + [v3(i) for i in range(113)]      # 120 matches: three pages of 50 plus a remainder
    noise = [v1(i, OTHER_RECORD) for i in range(30)] + [v3(i, OTHER_RECORD) for i in range(30)] + [v1(i, RECORD, OTHER_SUBJECT) for i in range(5)] + [v3(i, screened=False) for i in range(5)]
    seed(engine, matching + noise)
    pages = traverse(engine, page_size=50)
    got = [item['key'] for page in pages for item in page['items']]
    assert sorted(got) == got      # ascending by key on every page and across pages
    assert len(got) == len(set(got)) == 120 and set(got) == {r['key'] for r in matching}      # no duplicate, no missing, no noise
    assert [len(p['items']) for p in pages] == [50, 50, 20] and pages[-1]['next_cursor'] is None
    assert {item['contract'] for page in pages for item in page['items']} == {'listing-screen-v1', 'listing-screen-v3'}
    for page in pages:
        for item in page['items']:
            assert item['record_sha256'] == RECORD      # v1 from the revision, v3 from the stored scalar
            assert set(item) == set(sh.FIELDS)      # scalars only; no checkpoint body
            assert not {'supersedes', 'current', 'latest', 'preferred'} & set(item)


def test_default_page_is_25_and_the_maximum_is_50_and_larger_values_are_clamped(engine):
    seed(engine, [v3(i) for i in range(80)])
    first = sh.history_page(engine, SUBJECT, RECORD)
    assert len(first['items']) == 25 and first['page_size'] == 25 and first['next_cursor'] == first['items'][-1]['key']
    assert sh.history_page(engine, SUBJECT, RECORD, page_size=500)['page_size'] == 50
    assert len(sh.history_page(engine, SUBJECT, RECORD, page_size=500)['items']) == 50
    for bad in (0, -1, True, 2.5, '10'):
        with pytest.raises(ValueError, match='INVALID_PAGE_SIZE'):
            sh.history_page(engine, SUBJECT, RECORD, page_size=bad)


@pytest.mark.parametrize('count,size', [(25, 25), (50, 50), (1, 25), (0, 25), (51, 50)])
def test_the_exact_page_boundary_gives_a_null_cursor_only_when_nothing_follows(engine, count, size):
    seed(engine, [v3(i) for i in range(count)])
    pages = traverse(engine, page_size=size)
    assert sum(len(p['items']) for p in pages) == count
    assert pages[-1]['next_cursor'] is None and all(p['next_cursor'] for p in pages[:-1])
    if count and count % size == 0:
        assert len(pages) == count // size      # exactly page_size matches: one page, null cursor (no empty trailing page)


def test_a_cursor_beyond_the_last_key_returns_an_empty_page_and_a_null_cursor(engine):
    seed(engine, [v3(i) for i in range(5)])
    page = sh.history_page(engine, SUBJECT, RECORD, cursor='f' * 64)
    assert page['items'] == [] and page['next_cursor'] is None


def test_unscreened_v3_items_have_no_assessment_yet_and_are_not_listed(engine):
    seed(engine, [v3(0), v3(1, screened=False), v1(0)])
    items = sh.history_page(engine, SUBJECT, RECORD)['items']
    assert len(items) == 2 and all(i['state'] == 'COMPLETE' for i in items)


def test_a_traversal_never_repeats_a_row_and_a_row_created_mid_traversal_may_be_missed(engine):
    seed(engine, [v3(i) for i in range(60)])
    late = [v3(1000 + i) for i in range(40)]

    def add_late(page_number):
        if page_number == 1:
            seed(engine, late)
    pages = traverse(engine, page_size=25, between=add_late)
    got = [i['key'] for p in pages for i in p['items']]
    assert len(got) == len(set(got)) and sorted(got) == got      # never a repeat, always ascending
    initial = {v3(i)['key'] for i in range(60)}
    assert initial <= set(got)      # the original rows are all seen (they were present before the traversal began)
    cursor_after_first = pages[0]['next_cursor']
    new_keys = {r['key'] for r in late}
    assert {k for k in new_keys if k > cursor_after_first} <= set(got)      # rows above the cursor are picked up
    assert not {k for k in new_keys if k <= cursor_after_first} & set(got)      # rows below it are missed by this traversal (snapshot-free keyset semantics, stated)


def test_one_request_is_exactly_one_query_and_one_page(engine):
    seed(engine, [v3(i) for i in range(200)])
    statements = []

    @event.listens_for(engine, 'before_cursor_execute')
    def count(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    page = sh.history_page(engine, SUBJECT, RECORD, page_size=50)
    assert len(statements) == 1 and statements[0].lstrip().upper().startswith('SELECT')      # read-only
    assert len(page['items']) == 50 and page['next_cursor']      # no automatic traversal: the caller must ask again


def test_inputs_are_validated_before_any_query(engine):
    for subject in (None, {}, dict(SUBJECT, kind='DISCOVERY_SCOPE'), dict(SUBJECT, extra=1), dict(SUBJECT, reference='')):
        with pytest.raises(ValueError, match='INVALID_SUBJECT'):
            sh.history_page(engine, subject, RECORD)
    for record in (None, 'abc', 'A' * 64, RECORD + 'a'):
        with pytest.raises(ValueError, match='INVALID_RECORD_DIGEST'):
            sh.history_page(engine, SUBJECT, record)
    for cursor in ('', 'zz', 'A' * 64, 7):
        with pytest.raises(ValueError, match='INVALID_CURSOR'):
            sh.history_page(engine, SUBJECT, RECORD, cursor=cursor)


def test_the_module_never_writes(engine):
    import inspect
    source = inspect.getsource(sh)
    sql = sh._POSTGRESQL.upper() + sh._SQLITE.upper()
    for word in ('INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'GRANT'):
        assert word not in sql      # the two statements are SELECTs
    assert 'ORDER BY KEY' in sql and 'LIMIT' in sql and '.commit(' not in source and 'begin(' not in source
