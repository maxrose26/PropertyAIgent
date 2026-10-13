"""Synthetic transport audits: no live portal requests or database operations."""
import copy
import hashlib
import json
import datetime as dt
from collections import Counter

import pytest
from verification.direct_reference.arcus_manifest import rows, admitted_row, case_definitions
from verification.direct_reference.arcus_http_probe import record_observation, FACT_FIELDS, PLANNING_OBJECT
from verification.direct_reference.arcus_transport import qualify_worker, retrieve


def worker(application_id=688):
    row = admitted_row(application_id)
    values = dict(reference=row['reference'], status='Final', decision='Approve', decision_date='2026-07-23')
    if row['council'] == 'rochdale':
        values.update(status='Decision Made', decision='Approve with Conditions')
    if row['council'] == 'salford':
        values = dict(reference=row['reference'], decision_date='2026-08-20')
    fields = {FACT_FIELDS[k]: {'value': v} for k, v in values.items()}
    data = {'context': {'globalValueProviders': [{'values': {'records': {
        row['source_identifier']: {PLANNING_OBJECT: {'record': {'id': row['source_identifier'], 'fields': fields}}}
    }}}]}}
    body = json.dumps(data).encode()
    source = record_observation(data, row['source_identifier'], row['reference'])
    source.update(attempted=True, outcome='GUEST_JSON_OBSERVED', http_status=200,
                  received_bytes=len(body), response_sha256=hashlib.sha256(body).hexdigest())
    origin = row['source_url'].split('/pr/')[0]
    return dict(case='arcus_' + str(application_id), application_id=application_id,
        reference=row['reference'], destination=row['source_url'], persistence=False,
        requests=40, redirects=1, decoded_bytes=10000000, encoded_bytes=3000000,
        pages=1, navigations=2, local_frames=0, peak_owned_rss=800000000,
        owned_processes_seen=8, live_owned_survivors=0, elapsed_seconds=14,
        supervisor_seconds=15, supervisor_limit_hit=False, process_cleanup='CLOSED',
        cleanup='CONTEXT_BROWSER_CLOSED', requested_origins=[origin], navigated_origins=[origin],
        navigation_mismatch=None, safety_failure=False, safety_events=[],
        failure='UNREVIEWED_METHOD', record_http_probe=source)


def test_frozen_policy_scope_and_manual_candidate():
    assert Counter(r['council'] for r in rows()) == {'manchester': 22, 'rochdale': 18, 'salford': 17}
    assert len(case_definitions()) == 57
    for identifier in [1100, 296, 696, 698, 290]:
        with pytest.raises(ValueError): admitted_row(identifier)


@pytest.mark.parametrize('identifier', [688, 295, 252])
def test_exact_proven_read_shared_projection(identifier):
    result = qualify_worker(identifier, worker(identifier))
    assert result['failure'] is None
    observation = result['observation']
    assert observation.b2_eligible
    if identifier == 252:
        assert observation.verification_scope == 'FIELD_LEVEL_DATE_ONLY'
        assert observation.field_states['status'] == observation.field_states['decision'] == 'NOT_PRESENT'
        assert observation.fields['Status'] is None and observation.fields['Decision'] is None
    else:
        assert observation.verification_scope == 'COUPLED'


@pytest.mark.parametrize('changes', [dict(safety_failure=True, safety_events=['BYTE_LIMIT']),
    dict(live_owned_survivors=1), dict(cleanup='UNKNOWN'), dict(requests=81),
    dict(decoded_bytes=21*1024*1024), dict(supervisor_seconds=46), dict(pages=2),
    dict(navigations=3), dict(requested_origins=['https://wrong.invalid']),
    dict(reference='OTHER'), dict(failure='BROWSER_TIMEOUT'), dict(safety_events=['ROUTE_ERROR']),
    dict(supervisor_limit_hit=True), dict(record_http_probe=None)])
def test_failures_do_not_get_overridden_by_optional_action(changes):
    audit = worker(); audit.update(changes)
    result = qualify_worker(688, audit)
    assert result['failure'] is not None and result['observation'] is None


def test_reference_and_partial_states_not_replaced_by_retained_values():
    audit = worker(252)
    audit['record_http_probe']['record_field_states']['reference']['value'] = 'OTHER'
    assert qualify_worker(252, audit)['failure'] == 'AMBIGUOUS_SOURCE_RESULT'
    audit = worker(252)
    audit['record_http_probe']['record_field_states']['decision_date'].update(state='UNKNOWN', value=None)
    result = qualify_worker(252, audit)
    assert result['failure'] is None
    assert not result['observation'].b2_eligible
    assert result['observation'].field_states['decision_date'] == 'UNKNOWN'


def test_fresh_runner_called_once_and_cleaned_up():
    paths = []
    def runner(case, output):
        assert case == 'arcus_688'
        paths.append(output)
        output.write_text(json.dumps(worker()))
        return 1  # Optional denied action is diagnosed from evidence, not exit alone.
    result = retrieve(688, runner=runner)
    assert result['failure'] is None and len(paths) == 1
    assert not paths[0].exists()


def test_missing_worker_audit_retains_unknown_accounting():
    result = retrieve(688, runner=lambda *args: 1)
    assert result['failure'] == 'INVALID_ARTIFACT'
    assert result['audit']['requests'] == 'UNKNOWN'
    assert result['audit']['received_body_bytes'] == 'UNKNOWN'


def test_accounted_timeout_without_bytes_is_source_failure():
    audit = worker()
    audit.update(decoded_bytes=0, encoded_bytes=0, navigations=0,
        navigated_origins=[], failure='BROWSER_TimeoutError', safety_failure=True,
        safety_events=['BROWSER_TimeoutError'], record_http_probe=None)
    result = qualify_worker(688, audit)
    assert result['failure'] == 'TIMEOUT'
    assert result['audit']['received_body_bytes'] == 0
    assert result['audit']['cleanup_state'] == 'CLOSED'


@pytest.mark.parametrize('companion_status', [None, 'Under Consultation'])
def test_salford_transport_to_existing_b2_field_scope(session, companion_status):
    from app.config import CouncilConfig
    from tests.test_planning_status_verification import _add_application
    from verification.direct_reference.refresh import _refresh_row
    row = admitted_row(252)
    old = dt.datetime(2026, 9, 18, tzinfo=dt.timezone.utc)
    app = _add_application(session, id=252, council_code='salford', reference=row['reference'],
        status='Retained status', decision='Retained decision', status_verified_at=old)
    config = CouncilConfig(code='salford', name='Salford', base_url=row['source_url'],
        date_field_mode='received', doc_system='arcus', anite_base_url=None,
        unit_threshold=10, region='GM', country='England')
    audit = worker(252)
    if companion_status is not None:
        audit['record_http_probe']['record_field_states']['status'].update(state='PRESENT_VALUE', value=companion_status)
    observation = qualify_worker(252, audit)['observation']
    result = _refresh_row(session, app, config, row, retrieve_evidence=lambda: observation)
    assert result['accepted'] and result['outcome'] == 'FIELD_LEVEL_VERIFIED'
    assert app.status == 'Retained status' and app.decision == 'Retained decision'
    assert app.decision_issued_date == '2026-08-20'
    assert app.status_verified_at.replace(tzinfo=dt.timezone.utc) == old
