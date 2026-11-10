"""PA-D002 prospective private-evidence retention assessment (offline, NO delete).

Accepts only a trusted, pre-sanitised inventory. This module performs no SQL,
I/O, access changes or deletion, and does not confer deletion authority.
"""
from datetime import datetime, timedelta, timezone
import hmac
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
    'explicit_hold', 'hold_history_verified', 'hold_released_at', 'historical',
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


def assess_retention(entries, *, as_of, verified_run_index=None):
    """Return NON-EXECUTABLE potential dispositions for future owner review.

    resolution: VERIFIED, UNRESOLVED, or RECONCILED. A reconciled failure
    requires an independently established resolved_at; the later of the
    verified capture clock and resolution clock starts the further 90 days.
    Unknown, historical, unread, held and unfinished cases NEVER qualify.
    Trusted inventory must independently prove the complete hold history;
    a self-declared 'no current hold' is insufficient. A released hold
    restarts both retention clocks. `verified_run_index` must be produced from
    a separately authenticated *complete* run inventory and contain an exact
    frozenset of (name, sha256) pairs for each (period, run_id). It is a
    structural cross-check, not proof of its own trustworthiness. No deletion
    is ever performed here.
    The 365-day index is only an indicated minimum; no index deletion is planned.
    """
    now = _utc(as_of)
    # This is a structural check against an independently obtained COMPLETE
    # inventory. It does not authenticate the inventory's source or authorise
    # deletion. Missing/mismatched evidence identities must preserve the run.
    if verified_run_index is not None and type(verified_run_index) is not dict:
        raise ValueError('RETENTION_RUN_INDEX_SHAPE')
    if type(entries) is not list or len(entries) > 10000:
        raise ValueError('RETENTION_INVENTORY_BOUND')
    seen = set()
    results = []
    run_groups = {}
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
                or type(row['hold_history_verified']) is not bool
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
        hold_released = (_utc(row['hold_released_at'])
                         if row['hold_released_at'] is not None else None)
        if ((row['resolution'] == 'RECONCILED') != (resolved is not None)
                or resolved is not None and (resolved < captured or resolved > now)):
            raise ValueError('RETENTION_RESOLUTION_BOUND')
        if (hold_released is not None and
                (not row['hold_history_verified'] or row['explicit_hold']
                 or hold_released < captured or hold_released > now)):
            raise ValueError('RETENTION_HOLD_RELEASE_BOUND')
        # A supplied tag is NOT authentication: the future caller must verify
        # historical/prospective provenance against trusted database records.
        prospective = row['retention_tag'] == PROSPECTIVE_TAG and not row['historical']
        last_event = max(captured, resolved or captured, hold_released or captured)
        # An intake run is the recovery/stop boundary. A newer sibling,
        # unresolved sibling, or unverified sibling cannot be hidden by an
        # otherwise old and apparently eligible individual evidence row.
        run_groups.setdefault((period, run), []).append((len(results), last_event, row))
        index_until = last_event + timedelta(days=INDEX_DAYS)
        raw_until = last_event + timedelta(days=RAW_DAYS)
        if not prospective:
            reason = 'PRESERVE_HISTORICAL_OR_UNTAGGED'
        elif not row['readback_verified']:
            reason = 'PRESERVE_UNVERIFIED'
        elif not row['hold_history_verified']:
            reason = 'PRESERVE_UNVERIFIED_HOLD_HISTORY'
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
    # A truncated entry list must NEVER convert a single old capture into an
    # owner-review candidate. Every run (even a one-file run) needs a separately
    # supplied exact-identity manifest from a trusted complete inventory.
    # The manifest itself is NOT an authority signature: source authentication,
    # owner holds, resolution and any delete approval remain external gates.
    for siblings in run_groups.values():
        latest = max(clock for _, clock, _ in siblings)
        metadata = [row for _, _, row in siblings]
        if any(row['historical'] or row['retention_tag'] != PROSPECTIVE_TAG
               for row in metadata):
            reason = 'PRESERVE_RUN_PROVENANCE_UNVERIFIED'
        elif any(not row['readback_verified'] for row in metadata):
            reason = 'PRESERVE_RUN_READBACK_UNVERIFIED'
        elif any(not row['hold_history_verified'] for row in metadata):
            reason = 'PRESERVE_RUN_HOLD_HISTORY_UNVERIFIED'
        elif any(row['explicit_hold'] for row in metadata):
            reason = 'PRESERVE_RUN_EXPLICIT_HOLD'
        elif any(row['resolution'] == 'UNRESOLVED' for row in metadata):
            reason = 'PRESERVE_RUN_UNRESOLVED'
        elif len({(row['resolution'], row['resolved_at']) for row in metadata}) != 1:
            reason = 'PRESERVE_RUN_RESOLUTION_CONFLICT'
        elif (verified_run_index is None or
              verified_run_index.get((metadata[0]['period'], metadata[0]['run_id'])) !=
              frozenset((row['name'], row['sha256']) for row in metadata)):
            reason = 'PRESERVE_RUN_INVENTORY_UNVERIFIED'
        else:
            reason = None
        # Preserve the more specific single-row refusal reason; only the
        # missing exact-run manifest must override a previously eligible row.
        if len(siblings) == 1 and reason != 'PRESERVE_RUN_INVENTORY_UNVERIFIED':
            reason = None
        raw_until = latest + timedelta(days=RAW_DAYS)
        index_until = latest + timedelta(days=INDEX_DAYS)
        for position, _, _ in siblings:
            result = results[position]
            result['raw_not_before'] = raw_until.isoformat()
            result['index_keep_through_at_least'] = index_until.isoformat()
            if reason is not None:
                result['disposition'] = reason
            elif now < raw_until:
                result['disposition'] = 'PRESERVE_WITHIN_RETENTION'
    results.sort(key=lambda r: (r['period'], r['run_id'], r['name']))
    return {'schema': 'PA_D002_RETENTION_DRY_RUN_V1', 'as_of': now.isoformat(),
            'dry_run_only': True, 'sql_or_delete_operations': 0,
            'total': len(results), 'items': results}


SNAPSHOT_FIELDS = frozenset({
    'period', 'run_id', 'name', 'stored_sha256', 'actual_sha256',
    'bytes', 'created_at',
})


def assess_unverified_storage_snapshot(rows, *, as_of):
    """Fail-closed prospective retention *preview* from bounded SQL metadata.

    A table row's timestamp/hash does not authenticate prospective capture,
    legal holds or independent resolution. All entries remain PRESERVED and
    no deletion is proposed. Querying/role authentication is the caller's job;
    this function never connects to SQL or reads raw evidence.
    """
    if type(rows) is not list or len(rows) > 10000:
        raise ValueError('RETENTION_SNAPSHOT_BOUND')
    entries = []
    for row in rows:
        if type(row) is not dict or set(row) != SNAPSHOT_FIELDS:
            raise ValueError('RETENTION_SNAPSHOT_SHAPE')
        stored, actual = row['stored_sha256'], row['actual_sha256']
        if (type(stored) is not str or type(actual) is not str
                or re.fullmatch(r'[a-f0-9]{64}', stored) is None
                or re.fullmatch(r'[a-f0-9]{64}', actual) is None
                or not hmac.compare_digest(stored, actual)):
            raise ValueError('RETENTION_STORAGE_HASH_MISMATCH')
        entries.append({
            'period': row['period'], 'run_id': row['run_id'],
            'name': row['name'], 'sha256': stored, 'bytes': row['bytes'],
            'captured_at': row['created_at'],
            'retention_tag': 'UNVERIFIED_PROVENANCE',
            'readback_verified': False, 'resolution': 'UNRESOLVED',
            'resolved_at': None, 'explicit_hold': False,
            'hold_history_verified': False, 'hold_released_at': None,
            'historical': True,
        })
    return assess_retention(entries, as_of=as_of)
