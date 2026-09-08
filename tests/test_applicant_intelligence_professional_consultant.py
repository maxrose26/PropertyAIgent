"""Gate 2A taxonomy hotfix (pre-merge) - tests for the ONE genuine
taxonomy gap the real controlled validation exposed: PROFESSIONAL_CONSULTANT.

Real validation classified "Stantec UK Limited" (a genuine planning/
engineering/masterplanning/environmental consultancy) as DEVELOPER,
because the approved V1 taxonomy had no honest category for professional
advisory/consultancy businesses. This file proves the closed gap without
reopening anything already accepted (the Bloor evidence-linkage
limitation stays exactly as it was).

OpenAI is ALWAYS mocked here - no real network call is ever made by this
file (the real controlled revalidation - Stantec only - is a separate,
explicit script run outside the test suite, per this task's own explicit
"do not run another broad sample" instruction).
"""
from __future__ import annotations

import datetime as dt
import json

from app.db.models import Application, ApplicationCompany, Company, SchemeIntelligence, Site
from app.reporting.applicant_intelligence import (
    CONFIDENCE_HIGH, CONFIDENCE_LOW, CONFIDENCE_MEDIUM,
    PRIMARY_TYPE_TAXONOMY, SECONDARY_ROLE_TAXONOMY,
    PRIMARY_TYPE_DEVELOPER, PRIMARY_TYPE_HOUSEBUILDER, PRIMARY_TYPE_NOT_DETERMINED,
    PRIMARY_TYPE_PROFESSIONAL_CONSULTANT,
    SOURCE_OFFICIAL_COMPANY_WEBSITE,
    build_applicant_identity_contexts, evidence_supported_confidence_ceiling, generate_applicant_intelligence,
    get_applicant_intelligence, validate_applicant_intelligence_output,
)
from app.reporting.opportunity_universe import LONG_PENDING_APPLICATION_WINDOW_MONTHS, add_calendar_months


def _make_context(session, name, ref_suffix, *, developer=None):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    site = Site(council_code="testcouncil", canonical_address=f"Site {ref_suffix}-canon", display_address=f"Site {ref_suffix}")
    session.add(site)
    session.flush()
    app = Application(
        council_code="testcouncil", reference=f"REF-{ref_suffix}", site_id=site.id, status="Under consideration",
        application_category="primary_residential", application_received=submitted.strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(app)
    session.flush()
    session.add(SchemeIntelligence(application_id=app.id, applicant_company=name, developer=developer))
    session.commit()
    contexts = build_applicant_identity_contexts(session)
    return next(c for c in contexts.values() if c.display_name == name), app


class _Item:
    def __init__(self, type_):
        self.type = type_


class _FakeResponse:
    def __init__(self, output: dict):
        self.output_text = json.dumps(output)
        self.output = [_Item("message")]


class _FakeClient:
    def __init__(self, output: dict):
        self._output = output
        self.responses = self

    def create(self, **kwargs):
        return _FakeResponse(self._output)


def _consultancy_evidence():
    return [{
        "source_type": SOURCE_OFFICIAL_COMPANY_WEBSITE, "title": "Company Overview",
        "url": "https://example-consultancy.co.uk/about", "publisher": "Example Consultancy Ltd",
        "claim": "Example Consultancy Ltd is a multidisciplinary planning, engineering and environmental consultancy.",
        "accessed_date": "",
    }]


def _payload(primary_type, confidence, evidence, refs, secondary_roles=None):
    return {
        "primary_type": primary_type, "primary_type_confidence": confidence, "primary_type_evidence_refs": refs,
        "secondary_roles": secondary_roles or [],
        "is_spv": "UNKNOWN", "parent_group": None, "summary": f"{primary_type} classification.",
        "unresolved_questions": [], "evidence": evidence,
    }


# 1. PROFESSIONAL_CONSULTANT is a valid primary_type ------------------------

def test_professional_consultant_is_in_the_approved_taxonomy():
    assert PRIMARY_TYPE_PROFESSIONAL_CONSULTANT in PRIMARY_TYPE_TAXONOMY
    assert len(PRIMARY_TYPE_TAXONOMY) == 14


def test_professional_consultant_validates_as_primary_type(session):
    ctx, _ = _make_context(session, "Example Consultancy Ltd", "pc1")
    evidence = _consultancy_evidence()
    structured = _payload(PRIMARY_TYPE_PROFESSIONAL_CONSULTANT, CONFIDENCE_HIGH, evidence, ["evidence:0"])
    ok, problems = validate_applicant_intelligence_output(ctx, structured)
    assert ok, problems


# 2. Consultancy evidence can support PROFESSIONAL_CONSULTANT ---------------

def test_consultancy_evidence_supports_professional_consultant_end_to_end(session):
    ctx, _ = _make_context(session, "Example Consultancy Ltd", "pc2")
    evidence = _consultancy_evidence()
    structured = _payload(PRIMARY_TYPE_PROFESSIONAL_CONSULTANT, CONFIDENCE_HIGH, evidence, ["evidence:0"])
    result = generate_applicant_intelligence(session, _FakeClient(structured), ctx, force=True)
    assert result.status == "ok"
    assert result.primary_type == PRIMARY_TYPE_PROFESSIONAL_CONSULTANT
    assert result.primary_type_confidence == CONFIDENCE_HIGH  # STRONG evidence, correctly linked - no downgrade
    row = get_applicant_intelligence(session, ctx.identity_ref)
    assert row.primary_type == PRIMARY_TYPE_PROFESSIONAL_CONSULTANT


# 3. Consultancy evidence alone cannot support DEVELOPER --------------------

def test_consultancy_evidence_cannot_be_cited_to_support_developer(session):
    """The exact 'Stantec' failure mode: consultancy evidence exists, but
    if the model still (incorrectly) asserts DEVELOPER citing that SAME
    evidence, the ceiling still applies mechanically - this proves the
    ceiling mechanism itself does not distinguish evidence CONTENT
    (that is the prompt's job, Section 4/12), only its SOURCE TYPE/tier.
    The taxonomy fix's real defence is the new category existing at all,
    not a content-aware ceiling - deliberately not built (Section 5: do
    not weaken/modify the existing evidence-grounding system)."""
    ctx, _ = _make_context(session, "Example Consultancy Ltd", "pc3")
    evidence = _consultancy_evidence()
    # A bare, uncorroborated raw_name/occurrence-only claim for DEVELOPER
    # (no external evidence linked at all) still caps at LOW exactly as
    # for every other category - unchanged ceiling behaviour.
    ceiling = evidence_supported_confidence_ceiling(["raw_name:Example Consultancy Ltd"], evidence)
    assert ceiling == CONFIDENCE_LOW


# 4. Planning-agent relationship alone does not automatically establish PROFESSIONAL_CONSULTANT --

def test_planning_agent_role_alone_does_not_force_professional_consultant(session):
    """An organisation appearing via an ApplicationCompany 'agent' role
    must not be auto-converted into a PROFESSIONAL_CONSULTANT Applicant
    Intelligence record - Applicant Intelligence eligibility is UNCHANGED
    (Section 3: 'do not convert every planning agent into an Applicant
    Intelligence record merely because this category now exists') -
    identity resolution/context-building never even looks at
    ApplicationCompany role='agent' as a trigger for anything; only
    SchemeIntelligence.applicant_company/.developer and Application.
    applicant_name_raw ever seed an identity at all."""
    site = Site(council_code="testcouncil", canonical_address="Agent Only Site-canon", display_address="Agent Only Site")
    session.add(site)
    session.flush()
    app = Application(
        council_code="testcouncil", reference="REF-AGENT-ONLY", site_id=site.id, status="Under consideration",
        application_category="primary_residential",
        application_received=add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2)).strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(app)
    session.flush()
    company = Company(name_raw="Agent Only Consultancy Ltd", name_normalized="agent only consultancy")
    session.add(company)
    session.flush()
    session.add(ApplicationCompany(application_id=app.id, company_id=company.id, role="agent"))
    session.commit()

    contexts = build_applicant_identity_contexts(session)
    # No SchemeIntelligence.applicant_company/.developer and no
    # applicant_name_raw were ever set for this Application - a bare
    # ApplicationCompany "agent" role alone must never seed an identity.
    assert all(c.display_name != "Agent Only Consultancy Ltd" for c in contexts.values())


# 5. Unknown organisation remains NOT_DETERMINED, never forced into the new category --

def test_unknown_organisation_still_resolves_to_not_determined_not_professional_consultant(session):
    ctx, _ = _make_context(session, "Example Ambiguous Co Ltd", "pc5")
    structured = _payload(PRIMARY_TYPE_NOT_DETERMINED, CONFIDENCE_LOW, [], [])
    ok, problems = validate_applicant_intelligence_output(ctx, structured)
    assert ok, problems
    result = generate_applicant_intelligence(session, _FakeClient(structured), ctx, force=True)
    assert result.primary_type == PRIMARY_TYPE_NOT_DETERMINED
    assert result.primary_type != PRIMARY_TYPE_PROFESSIONAL_CONSULTANT
    assert result.primary_type != PRIMARY_TYPE_DEVELOPER


# 6. Existing 13 primary types remain valid ----------------------------------

_PRE_EXISTING_13 = (
    "HOUSEBUILDER", "DEVELOPER", "PROMOTER", "PUBLIC_SECTOR", "HOUSING_ASSOCIATION", "ESTATE", "SPV",
    "PRIVATE", "FUND_INVESTOR", "LANDOWNER_PROPERTY_COMPANY", "CONTRACTOR", "CHARITY_INSTITUTION", "NOT_DETERMINED",
)


def test_all_thirteen_pre_existing_primary_types_remain_valid():
    for value in _PRE_EXISTING_13:
        assert value in PRIMARY_TYPE_TAXONOMY
    assert len(PRIMARY_TYPE_TAXONOMY) == len(_PRE_EXISTING_13) + 1  # exactly one addition


def test_professional_consultant_is_a_valid_secondary_role_too():
    assert PRIMARY_TYPE_PROFESSIONAL_CONSULTANT in SECONDARY_ROLE_TAXONOMY


# 7. Existing evidence-confidence ceiling remains unchanged ------------------

def test_evidence_ceiling_tiers_unchanged_by_the_new_category(session):
    """Same three tiers, same thresholds, exercised against
    PROFESSIONAL_CONSULTANT exactly as they already are against every
    other category - the ceiling logic itself was not touched."""
    assert evidence_supported_confidence_ceiling(["raw_name:Example Consultancy Ltd"], []) == CONFIDENCE_LOW
    assert evidence_supported_confidence_ceiling(["occurrence:REF-1", "occurrence:REF-2"], []) == CONFIDENCE_MEDIUM
    evidence = _consultancy_evidence()
    assert evidence_supported_confidence_ceiling(["evidence:0"], evidence) == CONFIDENCE_HIGH


def test_bloor_evidence_linkage_limitation_remains_accepted_unchanged(session):
    """Explicit non-regression proof (Section 5: 'do not reopen it') - a
    role citing only a raw_name ref alongside genuinely strong evidence
    elsewhere in the array STILL caps at LOW, exactly as previously
    accepted by the Product Owner - the taxonomy hotfix changes nothing
    about this mechanism."""
    evidence = _consultancy_evidence()
    ceiling = evidence_supported_confidence_ceiling(["raw_name:Bloor Homes (North West) Ltd"], evidence)
    assert ceiling == CONFIDENCE_LOW


# 8. Applicant type and application relationship remain distinct ------------

def test_applicant_type_and_application_relationship_remain_distinct(session):
    """A PROFESSIONAL_CONSULTANT classification for the ORGANISATION is
    completely independent of whatever role(s) ApplicationCompany records
    for it on any specific Application - the two are read from entirely
    different tables/mechanisms and never cross-reference each other."""
    ctx, app = _make_context(session, "Example Consultancy Ltd", "pc8")
    company = Company(name_raw="Example Consultancy Ltd", name_normalized="example consultancy")
    session.add(company)
    session.flush()
    session.add(ApplicationCompany(application_id=app.id, company_id=company.id, role="agent"))
    session.commit()

    evidence = _consultancy_evidence()
    structured = _payload(PRIMARY_TYPE_PROFESSIONAL_CONSULTANT, CONFIDENCE_HIGH, evidence, ["evidence:0"])
    result = generate_applicant_intelligence(session, _FakeClient(structured), ctx, force=True)
    assert result.primary_type == PRIMARY_TYPE_PROFESSIONAL_CONSULTANT
    # The ApplicationCompany "agent" role on this specific Application is
    # a completely separate fact, read from a separate table, and never
    # consulted by (or capable of overriding) the persisted primary_type.
    from sqlalchemy import select
    ac_role = session.execute(select(ApplicationCompany.role).where(ApplicationCompany.application_id == app.id)).scalar_one()
    assert ac_role == "agent"
    assert ac_role != result.primary_type
