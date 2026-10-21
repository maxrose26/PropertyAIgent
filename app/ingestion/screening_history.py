"""Bounded, read-only presentation of the stored assessments of ONE source record (proposal section 4).

Assessment execution never calls this; it is a separate read for people and reports. One request is one query and one page: default 25 rows, maximum 50, keyset-paginated on the unique `key`, scalar columns only (never a
checkpoint body). A v1 item's `revision` IS the record digest; a v3 item's record digest is the stored scalar `checkpoint.record_sha256`, so a queued or not-yet-screened v3 item (no checkpoint) is not an assessment
yet and is not listed. Nothing here marks an assessment current, latest, preferred or superseding, and nothing is written.

Keyset pagination is snapshot-free: a traversal never repeats a row, but a row created mid-traversal whose key (a sha256 digest) sorts below the cursor is missed by that traversal."""
import re
from sqlalchemy import text

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 50
HEX64 = re.compile('^[a-f0-9]{64}$')
FIELDS = ('key', 'contract', 'revision', 'state', 'outcome', 'rule_version', 'config_sha256', 'record_sha256')

_POSTGRESQL = """
SELECT key, contract, revision, state,
       outcome::jsonb->>'outcome'          AS outcome,
       checkpoint::jsonb->>'rule_version'  AS rule_version,
       checkpoint::jsonb->>'config_sha256' AS config_sha256,
       checkpoint::jsonb->>'record_sha256' AS record_sha256
FROM public.ingestion_work_items
WHERE task = 'SCREENING'
  AND subject::jsonb = CAST(:subject AS jsonb)
  AND (revision = :record_sha256 OR checkpoint::jsonb->>'record_sha256' = :record_sha256)
  AND (CAST(:cursor AS text) IS NULL OR key > CAST(:cursor AS text))
ORDER BY key
LIMIT :limit
"""

_SQLITE = """
SELECT key, contract, revision, state,
       json_extract(outcome, '$.outcome')          AS outcome,
       json_extract(checkpoint, '$.rule_version')  AS rule_version,
       json_extract(checkpoint, '$.config_sha256') AS config_sha256,
       json_extract(checkpoint, '$.record_sha256') AS record_sha256
FROM ingestion_work_items
WHERE task = 'SCREENING'
  AND json_extract(subject, '$.kind') = 'APPLICATION'
  AND json_extract(subject, '$.council') = :council AND json_extract(subject, '$.reference') = :reference
  AND (revision = :record_sha256 OR json_extract(checkpoint, '$.record_sha256') = :record_sha256)
  AND (:cursor IS NULL OR key > :cursor)
ORDER BY key
LIMIT :limit
"""


def clamp_page_size(page_size):
    """Default 25; larger values are clamped to 50 (not rejected); anything that is not a positive integer is refused."""
    if page_size is None:
        return DEFAULT_PAGE_SIZE
    if type(page_size) is not int or page_size < 1:
        raise ValueError('INVALID_PAGE_SIZE')
    return min(page_size, MAX_PAGE_SIZE)


def history_page(engine, subject, record_sha256, *, cursor=None, page_size=None):
    """One page of the assessments of one record: {'items': [...], 'next_cursor': key-or-None, 'page_size': n}. One query. Read-only."""
    if (not isinstance(subject, dict) or set(subject) != {'kind', 'council', 'reference'} or subject['kind'] != 'APPLICATION'
            or not all(isinstance(subject[k], str) and subject[k] for k in ('council', 'reference'))):
        raise ValueError('INVALID_SUBJECT')
    if not isinstance(record_sha256, str) or not HEX64.match(record_sha256):
        raise ValueError('INVALID_RECORD_DIGEST')
    if cursor is not None and (not isinstance(cursor, str) or not HEX64.match(cursor)):
        raise ValueError('INVALID_CURSOR')
    size = clamp_page_size(page_size)
    params = dict(record_sha256=record_sha256, cursor=cursor, limit=size + 1)
    with engine.connect() as c:
        if engine.dialect.name == 'postgresql':
            import json
            c.execute(text("SET LOCAL statement_timeout='10s'"))
            c.execute(text("SET LOCAL lock_timeout='3s'"))
            rows = c.execute(text(_POSTGRESQL), dict(params, subject=json.dumps(subject, sort_keys=True))).mappings().all()
        elif engine.dialect.name == 'sqlite':
            rows = c.execute(text(_SQLITE), dict(params, council=subject['council'], reference=subject['reference'])).mappings().all()
        else:
            raise ValueError('UNSUPPORTED_DIALECT')
    page = [{f: row[f] for f in FIELDS} for row in rows[:size]]
    for item in page:
        if item['record_sha256'] is None:
            item['record_sha256'] = item['revision']      # a v1 item: the revision is the record digest
    return dict(items=page, next_cursor=page[-1]['key'] if len(rows) > size else None, page_size=size)
