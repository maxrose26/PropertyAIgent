"""Offline L0 typing/truth/invariance; no production/council/model dependencies."""
import json
from pathlib import Path
import pytest
from verification.stage26b_l0.dependencies import (
    DIRECT, CONTEXT, DISCOVERY, edge, establishes_fact,
    material_fields_changed, risk_cohort, priority_key)


def app(id=42, ref='FUL/355686/26', site=28, verified=None):
    return dict(id=id, site_id=site, reference=ref, council_code='oldham',
                status='Awaiting decision', decision=None, decision_issued_date=None,
                status_verified_at=verified)


def dependency(kind=DIRECT, application=None, truth='RETAINED_HISTORICAL_FACT'):
    return edge(subject_key='fixture-subject', site_id=28, application=application or app(),
                dependency_type=kind, fields=['planning_status'], consumers=['planning_presentation'],
                reason='Fixture source attribution', truth=truth)


@pytest.mark.parametrize('kind,truth,accepted', [
    (DIRECT,'RETAINED_HISTORICAL_FACT',True), (CONTEXT,'RETAINED_HISTORICAL_FACT',False),
    (DISCOVERY,'DISCOVERY_CANDIDATE',False), (DIRECT,'MOCKED_EXPECTATION',False),
    (DIRECT,'UNRESOLVED',False)])
def test_only_direct_qualified_source_establishes_fact(kind, truth, accepted):
    assert establishes_fact(dependency(kind,truth=truth),'planning_status',
                            application_id=42,reference='FUL/355686/26') is accepted


def test_parent_cannot_certify_child():
    parent=dependency(CONTEXT,app(7,'PARENT/7',verified='2026-10-08T00:00:00+00:00'))
    child=dependency(application=app(8,'CHILD/8'))
    assert not establishes_fact(parent,'planning_status',application_id=8,reference='CHILD/8')
    assert child['verification_state']=='UNKNOWN' and child['status_verified_at'] is None
    with pytest.raises(ValueError,match='attribution'):
        edge(subject_key='child',site_id=28,application=app(8,'CHILD/8'),
             dependency_type=DIRECT,fields=['planning_status'],consumers=['profile'],
             reason='bad transfer',verification_observation=app(7,'PARENT/7'))


def test_timestamp_only_non_material():
    before=app();after={**before,'status_verified_at':'2026-10-09T00:00:00+00:00'}
    assert material_fields_changed(before,after)==()


def test_failsworth_prospective_refusal():
    before=app();after={**before,'status':'Decided','decision':'Refused','decision_issued_date':'25/09/2026'}
    assert material_fields_changed(before,after)==('planning_status','decision_issued_date')


def test_southlink_pending_unchanged():
    before=app(29,'FUL/355201/25',25);after={**before,'status_verified_at':'2026-10-09T00:00:00+00:00'}
    assert material_fields_changed(before,after)==()


def test_missing_not_stale_or_current():
    assert dependency()['verification_state']=='UNKNOWN'


def test_discovery_cannot_be_promoted_by_label():
    with pytest.raises(ValueError,match='Discovery'):
        dependency(DISCOVERY)


def test_no_rank_score_or_model_inputs():
    result=risk_cohort(contradiction=True,buyer_facing=True)
    assert result=={'cohort':1,'reasons':['authoritative_contradiction']}
    assert not any(x in result for x in ('score','fit','price','model','valuation'))
    with pytest.raises(TypeError):risk_cohort(acquisition_score=99)


def test_oldest_tie_break_is_not_global_expiry():
    old=dict(cohort=4,council='oldham',reference='A',application_id=1,status_verified_at='2020-01-01T00:00:00+00:00')
    pending={**old,'cohort':2,'status_verified_at':'2026-10-08T00:00:00+00:00'}
    assert priority_key(pending)<priority_key(old)


def test_fresh_metadata_cannot_certify_changed_fact():
    with pytest.raises(ValueError,match='Different retained planning fact'):
        edge(subject_key='x',site_id=28,application=app(),dependency_type=DIRECT,
             fields=['planning_status'],consumers=['profile'],reason='bad',
             verification_observation={**app(),'decision':'Refused'})
