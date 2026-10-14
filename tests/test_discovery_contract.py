from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from app.pipeline.discovery_contract import (
    Literal, WindowEvidence, Completeness, account_identity, candidate_materiality,
    completed_through, latency_seconds, prospective_calendar,
)


def window(**changes):
    w = WindowEvidence('bolton', 'test', date(2026, 10, 1), date(2026, 10, 7),
                       date(2026, 10, 1), date(2026, 10, 7), 'RECEIVED',
                       'fixture-v1', 'date-labels', 'last-page', 2, 3, 3, 2000, 1.0)
    return replace(w, **changes)


@pytest.mark.parametrize('changes,expected', [
    ({}, 'COMPLETE'), ({'failure': 'navigation'}, 'INCOMPLETE'),
    ({'failure': 'connect', 'pages': 0}, 'FAILED'),
    ({'capped': True}, 'INCOMPLETE'), ({'accounting_complete': False}, 'INCOMPLETE'),
    ({'source_contract': None}, 'UNKNOWN'), ({'applied_evidence': None}, 'UNKNOWN'),
    ({'applied_end': date(2026, 10, 8)}, 'UNKNOWN'),
    ({'terminal_evidence': None}, 'INCOMPLETE'),
    ({'unique_references': 0}, 'UNKNOWN'),
    ({'unique_references': 0, 'explicit_zero': True}, 'COMPLETE'),
])
def test_completeness(changes, expected):
    assert window(**changes).outcome == expected


def test_gap_and_failed_watermark():
    later = window(requested_start=date(2026, 10, 9), requested_end=date(2026, 10, 15),
                   applied_start=date(2026, 10, 9), applied_end=date(2026, 10, 15))
    assert completed_through(date(2026, 9, 30), [later, window()], council='bolton', date_semantics='RECEIVED') == date(2026, 10, 7)
    assert completed_through(date(2026, 9, 30), [window(capped=True)], council='bolton', date_semantics='RECEIVED') == date(2026, 9, 30)


@pytest.mark.parametrize('text', ['', '2 dwellings', 'Reserved matters landscaping',
                                 'Discharge of condition', '100 dwellings', 'Warehouse'])
def test_no_false_negative_hard_filter(text):
    p = Literal('PRESENT_VALUE', text, 'proposal') if text else Literal('NOT_PRESENT', None, 'proposal')
    assert candidate_materiality(p)['outcome'] == 'POTENTIALLY_MATERIAL'


def test_identity_never_from_request():
    known = frozenset({('bolton', '123/26')})
    assert account_identity('bolton', (), known)[0] == 'WITHHELD_INSUFFICIENT_IDENTITY'
    assert account_identity('bolton', ('123/26', '124/26'), known)[0] == 'WITHHELD_CONFLICT'
    assert account_identity('bolton', ('123/26',), known)[0] == 'ALREADY_KNOWN'
    assert account_identity('bury', ('123/26',), known)[0] == 'NEW_CANDIDATE'
    with pytest.raises(ValueError): account_identity('trafford', ('123/26',), known)


@pytest.mark.parametrize('state', ['NOT_PRESENT', 'UNKNOWN', 'CONFLICTING', 'UNPARSEABLE'])
def test_unqualified_fields_cannot_carry_facts(state):
    with pytest.raises(ValueError): Literal(state, 'Granted', 'status')
    assert Literal(state, None, 'status').state == state


def test_calendar_and_no_substitute_latency():
    frozen = datetime(2026, 10, 14, 8, tzinfo=timezone.utc)
    cal = prospective_calendar(frozen)
    assert cal['week_one'] == (date(2026, 10, 19), date(2026, 10, 25))
    assert cal['week_two'] == (date(2026, 10, 26), date(2026, 11, 1))
    assert cal['backfill_audit_not_before'] == date(2026, 11, 9)
    assert latency_seconds(frozen, None) is None


def test_denominator_unknown_zero_and_unexplained_miss():
    from app.pipeline.discovery_contract import compare_denominator
    empty = frozenset()
    assert compare_denominator(None, empty, empty)['recall'] is None
    assert compare_denominator(empty, empty, empty)['recall'] is None
    refs = frozenset({('bolton', '123/26'), ('bolton', '124/26')})
    result = compare_denominator(refs, frozenset({('bolton', '123/26')}), empty)
    assert result['recall'] == 0.5
    assert result['missed'] == [('bolton', '124/26')]


def test_envelope_binds_identity_and_provenance():
    from app.pipeline.discovery_contract import DiscoveryEnvelope
    e = DiscoveryEnvelope('bolton', '123/26',
        'https://paplanning.bolton.gov.uk/online-applications/applicationDetails.do?keyVal=X',
        'X', datetime(2026, 10, 14, tzinfo=timezone.utc), window(), ('123/26',),
        'a' * 64, (('proposal', Literal('UNKNOWN', None, 'listing:proposal')),))
    assert e.audit(frozenset())['materiality']['outcome'] == 'POTENTIALLY_MATERIAL'
    with pytest.raises(ValueError): replace(e, displayed_references=('124/26',))
    with pytest.raises(ValueError): replace(e, site_relationship='EXISTING_SITE')
    with pytest.raises(ValueError): replace(e, body_sha256='unknown')


def test_omitted_proposal_is_unknown_not_source_absence():
    from app.pipeline.discovery_contract import DiscoveryEnvelope
    e = DiscoveryEnvelope('bolton', '123/26',
        'https://paplanning.bolton.gov.uk/online-applications/applicationDetails.do?keyVal=X',
        'X', datetime(2026, 10, 14, tzinfo=timezone.utc), window(), ('123/26',),
        'a' * 64, ())
    assert e.audit(frozenset())['materiality']['reason'] == 'UNKNOWN'
    inspected = replace(e, fields=(('proposal', Literal('NOT_PRESENT', None, 'listing:proposal')),))
    assert inspected.audit(frozenset())['materiality']['reason'] == 'NOT_PRESENT'
