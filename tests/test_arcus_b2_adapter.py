"""Synthetic exact-record fixtures; no source access or production qualification."""
import datetime as dt
import json

import pytest
from app.config import CouncilConfig
from verification.direct_reference.arcus_adapter import (
    from_response, representative_row, refresh_representative,
)
from verification.direct_reference.arcus_http_probe import FACT_FIELDS, PLANNING_OBJECT
from verification.direct_reference.refresh import admitted_row, BoundaryFailure
from tests.test_planning_status_verification import _add_application


def payload(case='manchester', **overrides):
    row = representative_row(case)
    values = dict(reference=row['reference'], status='Final', decision='Approve',
                  decision_date='2026-07-23')
    if case == 'rochdale':
        values.update(status='Decision Made', decision='Approve with Conditions', decision_date='2026-07-06')
    values.update(overrides)
    fields = {FACT_FIELDS[k]: {'value': v} for k, v in values.items()}
    record = {'id': row['source_identifier'], 'fields': fields}
    return {'actions': [{'id': '1;a', 'state': 'SUCCESS'}], 'context': {'globalValueProviders': [{'values': {'records': {
        row['source_identifier']: {PLANNING_OBJECT: {'record': record}}
    }}}]}}


def encode(data):
    return json.dumps(data).encode()


@pytest.mark.parametrize('case', ['manchester', 'rochdale'])
def test_shared_projection_qualified_pairs(case):
    observation = from_response(case, encode(payload(case)))
    assert observation.b2_eligible and observation.semantic_state == 'granted'
    assert set(observation.field_states.values()) == {'PRESENT_VALUE'}
    assert observation.literal_fields['Reference'] == representative_row(case)['reference']
    assert observation.verification_scope == 'COUPLED'
    with pytest.raises(BoundaryFailure):
        admitted_row(observation.application_id)  # no implicit production admission


@pytest.mark.parametrize('kind,expected', [('missing', 'NOT_PRESENT'), ('null', 'UNKNOWN'),
    ('blank', 'PRESENT_BLANK'), ('malformed', 'UNPARSEABLE'), ('conflict', 'CONFLICTING')])
def test_field_state_preserved(kind, expected):
    data = payload()
    fields = data['context']['globalValueProviders'][0]['values']['records'][
        representative_row('manchester')['source_identifier']][PLANNING_OBJECT]['record']['fields']
    key = FACT_FIELDS['decision']
    if kind == 'missing': del fields[key]
    elif kind == 'null': fields[key] = {'value': None}
    elif kind == 'blank': fields[key] = {'value': ''}
    elif kind == 'malformed': fields[key] = {'value': 12}
    else: fields[key]['displayValue'] = 'Refused'
    observation = from_response('manchester', encode(data))
    assert observation.field_states['decision'] == expected
    assert not observation.b2_eligible
    assert observation.fields['Decision'] is None


@pytest.mark.parametrize('bad', [b'{}', b'[]', b'not json', b'{"context":{},"context":{}}'])
def test_malformed_response_rejected(bad):
    with pytest.raises(BoundaryFailure): from_response('manchester', bad)


def test_wrong_identity_and_unqualified_literals():
    with pytest.raises(BoundaryFailure):
        from_response('manchester', encode(payload(reference='OTHER')))
    with pytest.raises(BoundaryFailure):
        from_response('salford', b'{}')
    observation = from_response('manchester_pending', encode(payload('manchester_pending',
        status='Recommendation Made', decision='Minded to Approve', decision_date=None)))
    assert not observation.b2_eligible
    assert observation.field_states['decision_date'] == 'UNKNOWN'
    assert observation.semantic_state == 'UNKNOWN_UNMAPPED'


def test_raw_date_without_display_still_validated():
    observation = from_response('manchester', encode(payload(decision_date='2026-99-99')))
    assert observation.field_states['decision_date'] == 'UNPARSEABLE'
    assert not observation.b2_eligible


@pytest.mark.parametrize('actions', [None, [], [{'id': '1;a', 'state': 'ERROR'}],
    [{'id': '1;a', 'state': 'SUCCESS'}, {'id': '2;a', 'state': 'SUCCESS'}]])
def test_cached_record_beside_failed_action_rejected(actions):
    data = payload()
    data['actions'] = actions
    with pytest.raises(BoundaryFailure):
        from_response('manchester', encode(data))


def test_transport_failure_never_enters_b2_success(session):
    row = representative_row('manchester')
    old = dt.datetime(2026, 9, 18, tzinfo=dt.timezone.utc)
    app = _add_application(session, id=row['application_id'], council_code=row['council'],
        reference=row['reference'], status='Awaiting decision', status_verified_at=old)
    config = CouncilConfig(code=row['council'], name=row['council'], base_url=row['source_url'],
        date_field_mode='received', doc_system='arcus', anite_base_url=None,
        unit_threshold=10, region='GM', country='England')
    def failed_transport():
        raise BoundaryFailure('TIMEOUT', 'Synthetic bounded transport failure')
    result = refresh_representative(session, app, config, 'manchester', retrieve_response=failed_transport)
    assert not result['accepted'] and result['outcome'] == 'TIMEOUT'
    assert app.status_verified_at.replace(tzinfo=dt.timezone.utc) == old
    assert app.status == 'Awaiting decision' and app.decision is None


@pytest.mark.parametrize('case', ['manchester', 'rochdale'])
@pytest.mark.parametrize('valid', [True, False])
def test_real_b2_disposable_handoff_and_failure_preservation(session, case, valid):
    row = representative_row(case)
    old = dt.datetime(2026, 9, 18, tzinfo=dt.timezone.utc)
    app = _add_application(session, id=row['application_id'], council_code=row['council'],
        reference=row['reference'], status='Awaiting decision', status_verified_at=old)
    config = CouncilConfig(code=row['council'], name=row['council'], base_url=row['source_url'],
        date_field_mode='received', doc_system='arcus', anite_base_url=None,
        unit_threshold=10, region='GM', country='England')
    body = encode(payload(case, **({} if valid else {'decision': None})))
    result = refresh_representative(session, app, config, case, retrieve_response=lambda: body)
    assert result['accepted'] is valid
    if valid:
        assert app.status_verified_at.replace(tzinfo=dt.timezone.utc) > old
        assert app.decision == ('Approve' if case == 'manchester' else 'Approve with Conditions')
        assert app.evidence_refresh_required
    else:
        assert app.status_verified_at.replace(tzinfo=dt.timezone.utc) == old
        assert app.status == 'Awaiting decision' and app.decision is None
