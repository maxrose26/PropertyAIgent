"""Shared Arcus exact-record projection into the existing B2 handoff.

No network, database credentials, runtime route admission or second writer.
The closed representative set is usable by disposable rehearsals; production
batch admission remains unchanged until the integrated transport is qualified.
"""
import datetime as dt
import hashlib
import json
from urllib.parse import urlsplit

from .arcus_http_probe import MAX_BODY, record_observation, unique_object
from .instrumented_probe import CASES
from .refresh import Observation, _refresh_row, fail
from verification.stage26b_l1.bolton_literal import semantic_state
from verification.stage26b_l1.request_boundary import BoundaryFailure

CASES_ALLOWED = ('manchester', 'manchester_pending', 'rochdale')
LABELS = {'reference': 'Reference', 'status': 'Status', 'decision': 'Decision',
          'decision_date': 'Decision Issued Date'}
# Literal pairs already qualified in the retained source-family observations.
# Reuse the existing semantic classifier; do not extend its vocabulary here.
QUALIFIED_PAIRS = {('Final', 'Approve'), ('Decision Made', 'Approve with Conditions')}


def representative_row(case):
    if case not in CASES_ALLOWED:
        fail('UNSUPPORTED_ROUTE', 'Arcus representative not qualified')
    application_id, reference, source_url = CASES[case]
    return dict(application_id=application_id, reference=reference, source_url=source_url,
                council='manchester' if case.startswith('manchester') else 'rochdale',
                source_identifier=urlsplit(source_url).path.rsplit('/', 1)[-1],
                platform_family='ARCUS', admission='OFFLINE_REPRESENTATIVE_ONLY')


def from_response(case, body):
    """Parse fresh response bytes supplied by an independently bounded transport.

    Hash exactly those bytes, retain the source literals, and preserve all six
    states. No successful transport or freshness claim follows from this parser.
    """
    row = representative_row(case)
    if not isinstance(body, bytes) or not body or len(body) > MAX_BODY:
        fail('PARTIAL_RETRIEVAL', 'Arcus response size/type')
    try:
        data = json.loads(body.decode('utf-8'), object_pairs_hook=unique_object)
        if not isinstance(data, dict):
            raise ValueError('RESPONSE_SHAPE')
        actions = data.get('actions')
        # Transport must additionally match this action's id to its request.
        # Cached record context beside an error/absent action is not evidence.
        if (not isinstance(actions, list) or len(actions) != 1
                or not isinstance(actions[0], dict) or actions[0].get('state') != 'SUCCESS'
                or not isinstance(actions[0].get('id'), str) or not actions[0]['id']):
            raise ValueError('RESPONSE_ACTION')
        source = record_observation(data, row['source_identifier'], row['reference'])
    except (ValueError, TypeError, AttributeError, KeyError):
        fail('PARSER_FAILURE', 'Arcus exact-record response rejected')
    fields, states, literals = {}, {}, {}
    for key, label in LABELS.items():
        item = source['record_field_states'][key]
        state, value = item['state'], item['value']
        if key == 'decision_date' and state == 'PRESENT_VALUE':
            try:
                if dt.date.fromisoformat(value).isoformat() != value:
                    raise ValueError('NON_CANONICAL_DATE')
            except (ValueError, TypeError):
                state = 'UNPARSEABLE'
        states[key] = state
        fields[label] = value if state == 'PRESENT_VALUE' else None
        if state in {'PRESENT_VALUE', 'PRESENT_BLANK'}:
            literals[label] = value
    semantic = 'UNKNOWN_UNMAPPED'
    complete = all(s in {'PRESENT_VALUE', 'PRESENT_BLANK'} for s in states.values())
    if complete and (fields['Status'], fields['Decision']) in QUALIFIED_PAIRS:
        try:
            semantic = semantic_state(fields)
        except BoundaryFailure:
            pass
    return Observation(row['application_id'], row['reference'], row['source_url'],
                       fields, states, semantic, hashlib.sha256(body).hexdigest(), literals,
                       b2_eligible=complete and semantic != 'UNKNOWN_UNMAPPED')


def refresh_representative(session, application, council, case, *, retrieve_response):
    """Disposable integration through the sole existing B2 writer.

    Retrieval is deferred until B2 captures prior facts, as in the Idox path.
    No command, batch registration or production invocation is added here.
    """
    row = representative_row(case)
    if application.id != row['application_id']:
        fail('AMBIGUOUS_SOURCE_RESULT', 'Arcus application identity mismatch')
    return _refresh_row(session, application, council, row,
                        retrieve_evidence=lambda: from_response(case, retrieve_response()))
