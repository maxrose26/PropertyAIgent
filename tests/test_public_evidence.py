"""No raw source, field, event or path may reach a PA-D002 public summary."""
import json

import pytest

from app.ingestion.ledger import Denied
from app.ingestion.public_evidence import project_public_summary

SECRET = 'private-address-and-raw-proposal-MUST-NOT-PUBLISH'
PAYLOAD = {
    'status': 'RETAINED_AND_SCREENED', 'coverage_advance': False,
    'authority_closure': 'INVALIDATED',
    'scopes': [{'council': 'tameside', 'status': 'RETAINED_AND_SCREENED',
                'records': 21, 'raw': SECRET}],
    'backlog': {'records': [{'address': SECRET, 'source_url': SECRET}]},
    'failure': None, 'events': [{'full': SECRET}], 'path': SECRET,
}
EVENTS = [{'source_body': SECRET, 'path': SECRET, 'credentials': SECRET}]
RAW = json.dumps(PAYLOAD).encode()
EVENT_RAW = json.dumps(EVENTS).encode()


def test_summary_is_status_counts_digests_only_and_never_contains_private_fields():
    result = project_public_summary(PAYLOAD, original_raw=RAW, original_events=EVENT_RAW)
    body = json.dumps(result, sort_keys=True)
    assert SECRET not in body
    for field in ('backlog', 'events', 'path', 'raw', 'source_url', 'address', 'failure'):
        assert field not in body
    assert result['total_records'] == 21 and result['scope_count'] == 1
    assert result['coverage_advance'] is False
    assert result['private_result_sha256'] and result['private_events_sha256']
    assert len(result['private_result_sha256']) == 64


@pytest.mark.parametrize('status', [
    'INCOMPLETE', 'STOP_RECONCILE_NO_RETRY',
])
def test_blocked_or_incomplete_never_promotes_coverage(status):
    value = {**PAYLOAD, 'status': status, 'failure': SECRET}
    result = project_public_summary(value, original_raw=RAW, original_events=EVENT_RAW)
    assert result['status'] == status and result['failure_present'] is True
    assert result['coverage_advance'] is False


@pytest.mark.parametrize('mutate', [
    lambda p: {**p, 'status': SECRET},
    lambda p: {**p, 'coverage_advance': True},
    lambda p: {**p, 'coverage_advance': 0},
    lambda p: {**p, 'authority_closure': SECRET},
    lambda p: {**p, 'scopes': [{'council': SECRET, 'status': 'INCOMPLETE', 'records': 5}]},
    lambda p: {**p, 'scopes': [{'council': 'tameside', 'status': SECRET, 'records': 5}]},
    lambda p: {**p, 'scopes': [{'council': 'tameside', 'status': 'INCOMPLETE', 'records': True}]},
    lambda p: {**p, 'scopes': [{'council': 'tameside', 'status': 'INCOMPLETE', 'records': 61}]},
    lambda p: {**p, 'scopes': [*p['scopes']] * 3},
])
def test_unknown_or_injected_metadata_is_refused(mutate):
    with pytest.raises(Denied):
        project_public_summary(mutate(PAYLOAD), original_raw=RAW, original_events=EVENT_RAW)


@pytest.mark.parametrize('raw,events', [
    (b'x' * (2 * 1024 * 1024 + 1), EVENT_RAW),
    (RAW, b'x' * (128 * 1024 + 1)),
    ('not-bytes', EVENT_RAW),
])
def test_bounded_private_digest_inputs(raw, events):
    with pytest.raises(Denied, match='PUBLIC_SUMMARY_INPUT_BOUND'):
        project_public_summary(PAYLOAD, original_raw=raw, original_events=events)
