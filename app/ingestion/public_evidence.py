"""Allowlisted public summary for a prospective PA-D002 private evidence route.

This projection deliberately never traverses or copies arbitrary nested source,
backlog, event, paths, case details, addresses, proposal or failure diagnostics.
It is a pure offline helper; Git-backed finalisation and private archival still
require separate restricted runtime integration and exact readback.
"""
import hashlib
import re

from .ledger import Denied

PUBLIC_STATUSES = frozenset(('RETAINED_AND_SCREENED', 'INCOMPLETE', 'STOP_RECONCILE_NO_RETRY'))
SCOPE_STATUSES = frozenset(('RETAINED_AND_SCREENED', 'INCOMPLETE', 'ALREADY_RETAINED'))
CLOSURE_STATUSES = frozenset(('INVALIDATED', 'NOT_ISSUED', 'UNCERTAIN'))


def project_public_summary(result, *, original_raw, original_events):
    """Return strictly typed, non-personal status/count/hash-only metadata."""
    if (type(result) is not dict or type(result.get('status')) is not str
            or result['status'] not in PUBLIC_STATUSES
            or type(original_raw) is not bytes or type(original_events) is not bytes
            or len(original_raw) > 2 * 1024 * 1024 or len(original_events) > 128 * 1024
            or type(result.get('coverage_advance')) is not bool
            or result['coverage_advance'] is not False
            or result.get('authority_closure') not in CLOSURE_STATUSES
            or type(result.get('scopes')) is not list
            or len(result['scopes']) > 2):
        raise Denied('PUBLIC_SUMMARY_INPUT_BOUND')
    scopes = []
    for scope in result['scopes']:
        if (type(scope) is not dict or type(scope.get('council')) is not str
                or re.fullmatch(r'[a-z_]{1,32}', scope['council']) is None
                or scope.get('status') not in SCOPE_STATUSES
                or type(scope.get('records')) is not int
                or not 0 <= scope['records'] <= 60):
            raise Denied('PUBLIC_SUMMARY_SCOPE_BOUND')
        scopes.append(dict(council=scope['council'], status=scope['status'],
                           record_count=scope['records']))
    return dict(
        schema='INTAKE_PUBLIC_SUMMARY_V1', status=result['status'],
        scope_count=len(scopes), scopes=scopes,
        total_records=sum(s['record_count'] for s in scopes),
        coverage_advance=False, admission_connected=False,
        extraction_connected=False,
        authority_closure=result['authority_closure'],
        failure_present=bool(result.get('failure')),
        private_result_sha256=hashlib.sha256(original_raw).hexdigest(),
        private_events_sha256=hashlib.sha256(original_events).hexdigest(),
    )
