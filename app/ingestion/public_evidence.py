"""Allowlisted public summary for a prospective PA-D002 private evidence route.

This projection deliberately never traverses or copies arbitrary nested source,
backlog, event, paths, case details, addresses, proposal or failure diagnostics.
It is a pure offline helper; Git-backed finalisation and private archival still
require separate restricted runtime integration and exact readback.
"""
import hashlib
import json
import re

from .ledger import Denied
from app.pipeline.discovery_contract import COUNCILS

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
            or type(result.get('authority_closure')) is not str
            or result['authority_closure'] not in CLOSURE_STATUSES
            or type(result.get('scopes')) is not list
            or len(result['scopes']) > 2):
        raise Denied('PUBLIC_SUMMARY_INPUT_BOUND')
    # Bind published counts/status to the EXACT private bytes whose digest
    # appears in the public proof. Without this, two unrelated objects could
    # produce a plausible-looking yet irreconcilable public summary.
    # The runtime produces both inputs using the same strict canonical JSON.
    try:
        expected_result = json.dumps(result, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True, allow_nan=False).encode()
        event_list = json.loads(original_events)
        expected_events = json.dumps(event_list, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True, allow_nan=False).encode()
    except (TypeError, ValueError, UnicodeError):
        raise Denied('PUBLIC_SUMMARY_PRIVATE_BINDING') from None
    if (expected_result != original_raw or type(event_list) is not list
            or expected_events != original_events):
        raise Denied('PUBLIC_SUMMARY_PRIVATE_BINDING')
    scopes = []
    for scope in result['scopes']:
        if (type(scope) is not dict or type(scope.get('council')) is not str
                or scope['council'] not in COUNCILS
                or type(scope.get('status')) is not str or scope['status'] not in SCOPE_STATUSES
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
