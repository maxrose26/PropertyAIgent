"""PA-D002 prospective private-evidence retention assessment (offline, NO delete).

Accepts only a trusted, pre-sanitised inventory. This module performs no SQL,
I/O, access changes or deletion, and does not confer deletion authority.
"""
from datetime import datetime, timedelta, timezone
import re

RAW_DAYS = 90
INDEX_DAYS = 365
PROSPECTIVE_TAG = 'PA_D002_PROSPECTIVE_V1'
NAMES = frozenset({
    'capture-1/source.json', 'capture-2/source.json',
    'final/result-before-publication.json', 'final/events-before-publication.json',
})
SHAPE = frozenset({
    'period', 'run_id', 'name', 'sha256', 'bytes', 'captured_at',
    'retention_tag', 'readback_verified', 'resolution', 'resolved_at',
    'explicit_hold', 'historical',
})


def _utc(value):
    if type(value) is not str:
        raise ValueError('RETENTION_TIME_INVALID')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('RETENTION_TIME_INVALID') from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('RETENTION_TIME_INVALID')
    return parsed.astimezone(timezone.utc)


def assess_retention(entries, *, as_of):
    """Return NON-EXECUTABLE potential dispositions for future owner review.

    resolution: VERIFIED, UNRESOLVED, or RECONCILED. A reconciled failure
    requires an independently established resolved_at; the later of the
    verified capture clock and resolution clock starts the further 90 days.
    Unknown, historical, unread, held and unfinished cases NEVER qualify.
    The 365-day index is only an indicated minimum; no index deletion is planned.
    """
    now = _utc(as_of)
    if type(entries) is not list or len(entries) > 10000:
        raise ValueError('RETENTION_INVENTORY_BOUND')
    seen = set()
    results = []
    for row in entries:
        if type(row) is not dict or set(row) != SHAPE:
            raise ValueError('RETENTION_INVENTORY_SHAPE')
        period, run, name = row['period'], row['run_id'], row['name']
        if (type(period) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', period)
                or type(run) is not str or not re.fullmatch(r'[a-f0-9]{32}', run)
                or name not in NAMES or type(name) is not str
                or type(row['sha256']) is not str or not re.fullmatch(r'[a-f0-9]{64}', row['sha256'])
                or type(row['bytes']) is not int or not 1 <= row['bytes'] <= 2097152
                or (name.startswith('capture-') and row['bytes'] > 524288)
                or type(row['readback_verified']) is not bool
                or type(row['explicit_hold']) is not bool
                or type(row['historical']) is not bool
                or type(row['retention_tag']) is not str
                or row['resolution'] not in ('VERIFIED', 'UNRESOLVED', 'RECONCILED')):
            raise ValueError('RETENTION_INVENTORY_VALUE')
        identity = (period, run, name)
        if identity in seen:
            raise ValueError('RETENTION_DUPLICATE_IDENTITY')
        seen.add(identity)
        captured = _utc(row['captured_at'])
        if captured > now:
            raise ValueError('RETENTION_FUTURE_CAPTURE')
        resolved = _utc(row['resolved_at']) if row['resolved_at'] is not None else None
        if ((row['resolution'] == 'RECONCILED') != (resolved is not None)
                or resolved is not None and (resolved < captured or resolved > now)):
            raise ValueError('RETENTION_RESOLUTION_BOUND')
        # A supplied tag is NOT authentication: the future caller must verify
        # historical/prospective provenance against trusted database records.
        prospective = row['retention_tag'] == PROSPECTIVE_TAG and not row['historical']
        index_until = captured + timedelta(days=INDEX_DAYS)
        raw_until = max(captured, resolved or captured) + timedelta(days=RAW_DAYS)
        if not prospective:
            reason = 'PRESERVE_HISTORICAL_OR_UNTAGGED'
        elif not row['readback_verified']:
            reason = 'PRESERVE_UNVERIFIED'
        elif row['explicit_hold']:
            reason = 'PRESERVE_EXPLICIT_HOLD'
        elif row['resolution'] == 'UNRESOLVED':
            reason = 'PRESERVE_UNRESOLVED'
        elif now < raw_until:
            reason = 'PRESERVE_WITHIN_RETENTION'
        else:
            reason = 'FUTURE_OWNER_REVIEW_CANDIDATE'
        results.append({
            'period': period, 'run_id': run, 'name': name,
            'sha256': row['sha256'], 'bytes': row['bytes'],
            'raw_not_before': raw_until.isoformat(),
            'index_keep_through_at_least': index_until.isoformat(),
            'disposition': reason,
            'may_delete_now': False,
        })
    results.sort(key=lambda r: (r['period'], r['run_id'], r['name']))
    return {'schema': 'PA_D002_RETENTION_DRY_RUN_V1', 'as_of': now.isoformat(),
            'dry_run_only': True, 'sql_or_delete_operations': 0,
            'total': len(results), 'items': results}
