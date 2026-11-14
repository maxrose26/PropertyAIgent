"""Ten-council OFFLINE source-profile inventory for PA-D004 v1.2.

Pure reconciliation of the existing nine-council finite caller and its
independently unqualified Trafford parser hint. It cannot issue a child,
fetch a portal, persist a record, grant SQL authority or certify coverage.
Never substitute this inventory for finite_acceptance.manifest().
"""
from datetime import datetime

from app.pipeline.discovery_contract import COUNCILS, SOURCE_ROOTS
from . import campaign_manifest as campaign, finite_acceptance as finite
from . import source_profiles

VERSION = 'TEN_COUNCIL_PROFILE_INVENTORY_OFFLINE_V1'
NINE = frozenset({'bolton', 'bury', 'manchester', 'oldham', 'rochdale',
                  'salford', 'stockport', 'tameside', 'wigan'})
TEN = NINE | {'trafford'}


def build(as_of):
    """One immutable-as-of proposal with 9 source *shapes* and one unqualified gap.

    Profiles below do not mean that the live source/date/terminal contracts
    have been independently qualified. Existing nine-council manifest hashes
    and the <=2-row package reservations are preserved byte-for-byte.
    """
    if type(as_of) is not datetime or as_of.utcoffset() is None:
        raise ValueError('TEN_COUNCIL_AWARE_CLOCK')
    if COUNCILS != NINE or set(finite.SEMANTICS) != NINE or campaign.REVIEWED_NINE != NINE:
        raise ValueError('TEN_COUNCIL_HISTORICAL_REGISTRY_DRIFT')
    if SOURCE_ROOTS.get('trafford') != ('pa.trafford.gov.uk', '/online-applications/'):
        raise ValueError('TRAFFORD_HINT_CHANGED_REVIEW_REQUIRED')
    gap = campaign.shutdown_gap_source_packages(as_of)
    windows = []
    for w in gap['windows']:
        plan = w['finite_manifest']
        canonical = finite.manifest(w['start'], w['end'], 'SUSPENSION_CATCHUP')
        if plan != canonical or finite.digest(plan) != w['finite_manifest_sha256']:
            raise ValueError('TEN_COUNCIL_NINE_PLAN_UNVERIFIED')
        if {r['council'] for r in plan['rows']} != NINE or len(plan['rows']) != 9:
            raise ValueError('TEN_COUNCIL_NINE_ROWS_UNVERIFIED')
        expected_tenth = {
            'council': 'trafford', 'start': w['start'], 'end': w['end'],
            'configured_date_basis': 'RECEIVED_NOT_QUALIFIED',
            'status': 'SOURCE_CONTRACT_AND_SQL_SCOPE_UNQUALIFIED'
        }
        if w['unqualified_tenth'] != expected_tenth:
            raise ValueError('TEN_COUNCIL_TRAFFORD_NOT_BOUND')
        entries = []
        for row in plan['rows']:
            profile = source_profiles.profile(row, 'SCREENING_METADATA')
            source_profiles.validate(profile, row)
            entries.append(dict(row=dict(row), profile=profile,
                state='EXISTING_NINE_SOURCE_SHAPE_ONLY',
                source_contract_qualified=False, sql_issuer_qualified=False))
        entries.append(dict(
            row=dict(council='trafford', start=w['start'], end=w['end'],
                     semantics='UNKNOWN_NOT_QUALIFIED'),
            profile=None, state='TRAFFORD_PARSER_HINT_ONLY',
            host_hint=SOURCE_ROOTS['trafford'][0],
            path_hint=SOURCE_ROOTS['trafford'][1],
            missing_evidence=['OFFICIAL_DATE_BASIS', 'SOURCE_TERMINAL_AND_TOTAL',
                              'CANONICAL_PROFILE', 'OWNER_BOUND_SQL_ISSUER'],
            source_contract_qualified=False, sql_issuer_qualified=False))
        if len(entries) != 10 or {e['row']['council'] for e in entries} != TEN:
            raise ValueError('TEN_COUNCIL_SCOPE_UNVERIFIED')
        windows.append(dict(start=w['start'], end=w['end'],
            original_nine_manifest_sha256=w['finite_manifest_sha256'],
            original_nine_packages=w['packages'],
            profiles=sorted(entries, key=lambda e: e['row']['council']),
            last_day_not_yet_complete=w['end_day_incomplete']))
    if len(windows)*10 != gap['total_date_scopes'] or len(windows)*5 != sum(
        len(w['original_nine_packages']) for w in windows):
        raise ValueError('TEN_COUNCIL_CAPACITY_RECONCILIATION')
    return dict(version=VERSION, as_of_london=gap['as_of_london'],
        fallback_start=gap['fallback_start'], endpoint_date=gap['endpoint_date'],
        fallback_is_verified_shutdown=False, source_only_synthetic_preview=True,
        required_councils=sorted(TEN), window_count=len(windows),
        scope_count=10*len(windows), source_shape_count=9*len(windows),
        trafford_unqualified_count=len(windows), windows=windows,
        source_contracts_qualified=False, sql_issuer_qualified=False,
        collection_authorised=False, persisted_records_verified=False,
        backlog_populated=False, prospective_coverage_proven=False)


def validate(value):
    """Reject changes to counts, inherited nine hashes, Trafford or as-of time."""
    try:
        if not isinstance(value, dict) or value != build(datetime.fromisoformat(value['as_of_london'])):
            raise ValueError()
    except (TypeError, KeyError, ValueError, OverflowError):
        raise ValueError('TEN_COUNCIL_INVENTORY_UNVERIFIED') from None
    return value
