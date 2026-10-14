"""Closed Arcus transport using the existing credential-free supervised worker.

Only minimized planning observations cross the process boundary. Database work
is owned by the caller's existing B2 transaction; this module has no DB access.
"""
import contextlib
import json
import math
import os
from pathlib import Path
import tempfile

from .arcus_manifest import admitted_row
from .arcus_adapter import from_observed_record
from .instrumented_probe import supervised, MAX_BYTES, MAX_REQUESTS, MAX_SECONDS, origin
from verification.stage26b_l1.request_boundary import BoundaryFailure


def empty_audit():
    return dict(requests='UNKNOWN', redirects='UNKNOWN', retries=0,
                received_body_bytes='UNKNOWN', encoded_body_bytes='UNKNOWN',
                elapsed_seconds='UNKNOWN', worker_seconds='UNKNOWN',
                peak_owned_rss='UNKNOWN', owned_processes_seen='UNKNOWN',
                live_owned_survivors='UNKNOWN', navigations='UNKNOWN', pages='UNKNOWN',
                cleanup_state='UNKNOWN', budget_state='UNKNOWN', source_sha256=None)


def qualify_worker(application_id, audit):
    """Optional denied actions cannot conceal a later sticky safety failure."""
    row = admitted_row(application_id)
    return _qualify_row(application_id, audit, row, 'arcus_' + str(application_id),
                        lambda source: from_observed_record(application_id, source))


def _qualify_row(application_id, audit, row, case, projector):
    """Common resource/identity boundary; caller admission stays separate."""
    compact = empty_audit()
    if not isinstance(audit, dict):
        return dict(observation=None, audit=compact, failure='INVALID_ARTIFACT')
    copied = {'requests': 'requests', 'redirects': 'redirects',
              'received_body_bytes': 'decoded_bytes', 'encoded_body_bytes': 'encoded_bytes',
              'elapsed_seconds': 'supervisor_seconds', 'worker_seconds': 'elapsed_seconds',
              'peak_owned_rss': 'peak_owned_rss', 'owned_processes_seen': 'owned_processes_seen',
              'live_owned_survivors': 'live_owned_survivors', 'navigations': 'navigations', 'pages': 'pages'}
    # Never return arbitrary worker text in numeric audit positions.
    for target, source in copied.items():
        value = audit.get(source)
        if type(value) in (int, float) and math.isfinite(value) and value >= 0:
            compact[target] = value
    def failure(code):
        return dict(observation=None, audit=compact, failure=code)
    if (audit.get('case') != case
            or audit.get('application_id') != application_id
            or audit.get('reference') != row['reference']
            or audit.get('destination') != row['source_url']
            or audit.get('persistence') is not False):
        return failure('AMBIGUOUS_SOURCE_RESULT')
    integer_bounds = {'requests': (0, MAX_REQUESTS), 'redirects': (0, MAX_REQUESTS),
                      'decoded_bytes': (0, MAX_BYTES), 'encoded_bytes': (0, MAX_BYTES),
                      'pages': (0, 1), 'navigations': (0, 2), 'local_frames': (0, 2),
                      'peak_owned_rss': (0, 1024**3), 'owned_processes_seen': (0, 256),
                      'live_owned_survivors': (0, 0)}
    bounded = all(type(audit.get(k)) is int and low <= audit[k] <= high
                  for k, (low, high) in integer_bounds.items())
    bounded = bounded and all(type(audit.get(k)) in (int, float) and math.isfinite(audit[k])
        and 0 <= audit[k] <= MAX_SECONDS for k in ('elapsed_seconds', 'supervisor_seconds'))
    compact['budget_state'] = 'WITHIN_LIMITS' if bounded and audit.get('supervisor_limit_hit') is False else 'EXHAUSTED'
    closed = (audit.get('process_cleanup') == 'CLOSED' and audit.get('cleanup') in ('CONTEXT_BROWSER_CLOSED', 'NOT_STARTED')
              and audit.get('live_owned_survivors') == 0)
    compact['cleanup_state'] = 'CLOSED' if closed else 'FAILED'
    if not closed:
        return failure('CLEANUP_FAILURE')
    if not bounded or audit.get('supervisor_limit_hit') is not False:
        return failure('ACCOUNTING_FAILURE')
    allowed = origin(row['source_url'])
    if (audit.get('requested_origins') not in ([], [allowed])
            or audit.get('navigated_origins') not in ([], [allowed])
            or audit.get('navigation_mismatch') is not None):
        return failure('SCOPE_ESCAPE')
    if audit.get('safety_failure') is not False or audit.get('safety_events') != []:
        events = audit.get('safety_events')
        if not isinstance(events, list) or any(not isinstance(event, str) for event in events):
            return failure('INVALID_ARTIFACT')
        if any(event in {'UNADMITTED_ORIGIN', 'UNADMITTED_NAVIGATION', 'DOCUMENT_DENIED',
                         'DOWNLOAD_DENIED', 'FRAME_DENIED', 'WEBSOCKET_DENIED',
                         'WORKER_DENIED', 'ROUTE_ERROR'} for event in events):
            return failure('SCOPE_ESCAPE')
        if any(event in {'BYTE_LIMIT', 'REQUEST_LIMIT', 'HTTP_BUDGET_UNAVAILABLE',
                         'HTTP_AGGREGATE_BOUND', 'FRAME_LIMIT', 'NAVIGATION_LIMIT',
                         'PAGE_LIMIT', 'INVALID_CONTENT_LENGTH'} for event in events):
            return failure('ACCOUNTING_FAILURE')
        if any('Timeout' in event or event == 'TIMEOUT' for event in events):
            return failure('TIMEOUT')
        return failure('SOURCE_UNAVAILABLE')
    if audit.get('failure') not in (None, 'UNREVIEWED_METHOD'):
        return failure('SOURCE_UNAVAILABLE')
    source = audit.get('record_http_probe')
    if not isinstance(source, dict):
        return failure('SOURCE_UNAVAILABLE')
    if (audit.get('cleanup') != 'CONTEXT_BROWSER_CLOSED' or audit['pages'] != 1
            or audit['navigations'] < 1 or audit['requests'] < 1 or audit['decoded_bytes'] < 1
            or audit['requested_origins'] != [allowed] or audit['navigated_origins'] != [allowed]):
        return failure('ACCOUNTING_FAILURE')
    try:
        observation = projector(source)
    except BoundaryFailure as exc:
        return failure(exc.outcome)
    except (ValueError, TypeError, KeyError):
        return failure('PARSER_FAILURE')
    compact['source_sha256'] = observation.body_sha256
    return dict(observation=observation, audit=compact, failure=None)


def retrieve(application_id, *, runner=supervised):
    """One fresh frozen-reference run, no retry and no cached evidence reuse."""
    admitted_row(application_id)
    with tempfile.TemporaryDirectory(prefix='stage4-arcus-transport-') as directory:
        output = Path(directory) / 'audit.json'
        try:
            # Supervision writes its own bounded audit; do not duplicate it in
            # the enclosing production worker's output.
            with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink):
                runner('arcus_' + str(application_id), output)
            if not output.is_file() or output.stat().st_size >= 65536:
                raise ValueError('MISSING_BOUNDED_AUDIT')
            audit = json.loads(output.read_bytes())
        except Exception:
            return dict(observation=None, audit=empty_audit(), failure='INVALID_ARTIFACT')
        return qualify_worker(application_id, audit)
