"""Focused regressions discovered by the bounded buyer walkthrough."""
from dataclasses import replace
import datetime as dt
from app.policy.ah_assessment import AHAssessment, AHClaim, TenureClaim
from app.reporting.residential_mix import build_affordable_tenure
from app.db.models import SchemeIntelligence,Document
from app.enrichment.control_entities import create_control_relationship_if_absent
from app.reporting.ownership_control import get_application_control_intelligence
from tests.test_agent_ready_fact_foundation import _make_planning_delivery_site


def source():
    return AHClaim(value=72,qualifier='exact',state='verified',application_reference='LOCAL/variation',
        scope_type='component',scope_label='Retirement',stage='proposed (reported; stage unverified)',
        document_id='local-doc',document_date='2024-10-23',source_url='https://example.invalid/statement',
        passage='72 retirement homes proposed for social rent')


def test_tenure_claim_keeps_proposal_scope_date_and_source_over_stale_extraction():
    a=AHAssessment(count=source(),tenures=(TenureClaim('Social rent',source()),))
    legacy=SchemeIntelligence(application_id=1,affordable_tenure_split_final='OPSO')
    result=build_affordable_tenure(legacy,{'state':'review'},a)
    label=result['categories'][0]
    assert all(x in label for x in ('Social rent','72','Retirement','proposed','stage unverified','2024-10-23','local-doc'))
    assert 'OPSO' not in label
    assert legacy.affordable_tenure_split_final=='OPSO'


def test_qualified_count_without_tenure_does_not_claim_provision_unresolved():
    result=build_affordable_tenure(None,{'state':'review'},AHAssessment(count=source()))
    assert result['affordable_known_tenure_unknown']
    assert not result['has_categories']


def test_tenure_conflict_is_not_relabelled_as_verified():
    a=AHAssessment(count=source(),tenures=(TenureClaim('Social rent',replace(source(),state='conflicting')),))
    assert 'conflicting' in build_affordable_tenure(None,{'state':'review'},a)['categories'][0]


def test_document_roles_keep_source_date_and_application_without_ownership(session):
    site=_make_planning_delivery_site(session,unit_count=82)
    app=site.applications[0]
    doc=Document(application_id=app.id,document_name='Local acceptance statement',source_url='https://example.invalid/statement')
    session.add(doc);session.flush()
    for name,role,category in [('Westshield','DEVELOPER','DOCUMENT_DELIVERY_PARTY'),
                               ('Housing 21','OTHER','DOCUMENT_PROPOSED_OPERATOR')]:
        create_control_relationship_if_absent(session,entity_name_raw=name,role=role,
            evidence_category=category,evidence_basis='document_statement',extraction_method='manual',
            application_id=app.id,site_id=site.id,evidence_document_id=doc.id,
            evidence_date=dt.datetime(2024,10,23),evidence_snippet='Dated proposed delivery role, not seller authority.',review_status='confirmed')
    session.flush()
    views=get_application_control_intelligence(session,app.id)
    assert {v.role_label for v in views}=={'Developer / delivery party stated in document','Housing association / proposed operator stated in document'}
    assert all(v.evidence_date==dt.datetime(2024,10,23) and v.document_source_url==doc.source_url and v.application_reference==app.reference for v in views)
    assert all(v.company_id is None and v.role!='OWNER' for v in views)


def test_retirement_preference_is_explicit_and_does_not_override_other_rules():
    from app.policy.buyer_profiles import HOUSING_ASSOCIATION, NESTEN_HOMES
    from app.policy.buyer_matching import assess_buyer_fit
    from tests.test_buyer_matching import _facts
    a = AHAssessment(count=source())
    facts = _facts(unit_count=82, affordable_unit_count=72,
        affordable_assessment=a, development_type_raw='mixed_retirement_and_market_housing',
        is_specialist_development=True)
    policy = replace(HOUSING_ASSOCIATION, target_unit_max=None)
    assert a.search(minimum=50) == 'meets'
    assert assess_buyer_fit(policy, facts).classification == 'INSUFFICIENT_EVIDENCE'
    accepted = assess_buyer_fit(replace(policy, retirement_appetite='ACCEPT'), facts)
    assert accepted.classification == 'STRONG_FIT'
    assert any('explicitly accepts retirement' in x for x in accepted.matches)
    assert assess_buyer_fit(replace(policy, retirement_appetite='EXCLUDE'), facts).classification == 'NOT_SUITABLE'
    # Acceptance cannot waive a separately specified maximum, general specialist
    # exclusion, or unclassified planning status. Count remains independently qualified.
    over_max = assess_buyer_fit(replace(policy, retirement_appetite='ACCEPT', target_unit_max=50), facts)
    assert over_max.is_investigative_exception
    assert any('AH count assessment: does_not_meet' in x for x in over_max.investigate)
    assert assess_buyer_fit(replace(NESTEN_HOMES, retirement_appetite='ACCEPT'), facts).classification == 'NOT_SUITABLE'
    percentage_unknown = replace(facts, affordable_percentage=None, affordable_percentage_trusted=False)
    result = assess_buyer_fit(replace(policy, retirement_appetite='ACCEPT'), percentage_unknown)
    assert any('proportion has not been confirmed' in x for x in result.unknown)
    from app.policy.buyer_matching import OTHER_OR_UNKNOWN
    uncertain = replace(facts, planning_state=OTHER_OR_UNKNOWN)
    assert assess_buyer_fit(replace(policy, retirement_appetite='ACCEPT'), uncertain).classification == 'INSUFFICIENT_EVIDENCE'
    for product in ('care_home', 'student_accommodation', 'mixed_specialist_and_market_housing'):
        result = assess_buyer_fit(replace(policy, retirement_appetite='ACCEPT'), replace(facts, development_type_raw=product))
        assert result.classification == 'INSUFFICIENT_EVIDENCE'
    assert HOUSING_ASSOCIATION.retirement_appetite == NESTEN_HOMES.retirement_appetite == 'UNSPECIFIED'


def test_invalid_retirement_preference_fails_closed():
    import pytest
    from app.policy.buyer_profiles import HOUSING_ASSOCIATION
    with pytest.raises(ValueError, match='retirement_appetite'):
        replace(HOUSING_ASSOCIATION, retirement_appetite='yes')


def test_legacy_investigation_count_never_receives_approximate_leeway():
    from app.policy.ah_assessment import legacy_assessment
    from app.policy.buyer_profiles import HOUSING_ASSOCIATION
    from app.policy.buyer_matching import assess_buyer_fit
    from tests.test_buyer_matching import _facts
    for count in (0, 30, 45, 50, 55, 72, None):
        a = legacy_assessment(fields={'affordable_units_final':count}, application_reference='LEGACY/1')
        assert a.columns()['AH Reported Count'] == count
        assert not a.columns()['AH Qualified']
        assert a.search(minimum=50) == a.search(maximum=50) == 'unknown'
        if count is not None: assert 'reported; source and scope unverified' in a.label()
        facts = _facts(affordable_unit_count=count, affordable_assessment=a)
        assert assess_buyer_fit(HOUSING_ASSOCIATION, facts).classification == 'INSUFFICIENT_EVIDENCE'
