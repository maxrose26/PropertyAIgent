"""Gate 2A final taxonomy amendment - tests for the approved V1 primary
applicant-type taxonomy (13 values), primary_type/secondary_roles
semantics, SPV parent/group treatment, and the relationship-separation
guarantees (applicant type != site ownership / planning agent / control
relationship).

OpenAI is ALWAYS mocked here - no real network call is ever made by this
file (the real controlled revalidation is a separate, explicit script run
outside the test suite - see this task's own final report).
"""
from __future__ import annotations

import datetime as dt
import json

from app.db.models import Application, ApplicantIntelligence, ControlRelationship, SchemeIntelligence, Site
from app.reporting.applicant_intelligence import (
    CONFIDENCE_HIGH, CONFIDENCE_LOW, CONFIDENCE_MEDIUM,
    PRIMARY_TYPE_TAXONOMY, SECONDARY_ROLE_TAXONOMY, PARENT_TYPE_UNKNOWN,
    PRIMARY_TYPE_HOUSEBUILDER, PRIMARY_TYPE_DEVELOPER, PRIMARY_TYPE_PROMOTER, PRIMARY_TYPE_PUBLIC_SECTOR,
    PRIMARY_TYPE_HOUSING_ASSOCIATION, PRIMARY_TYPE_ESTATE, PRIMARY_TYPE_SPV, PRIMARY_TYPE_PRIVATE,
    PRIMARY_TYPE_FUND_INVESTOR, PRIMARY_TYPE_LANDOWNER_PROPERTY_COMPANY, PRIMARY_TYPE_CONTRACTOR,
    PRIMARY_TYPE_CHARITY_INSTITUTION, PRIMARY_TYPE_NOT_DETERMINED,
    SOURCE_OFFICIAL_COMPANY_WEBSITE,
    build_applicant_identity_contexts, evidence_supported_confidence_ceiling, generate_applicant_intelligence,
    get_applicant_intelligence, is_planning_opportunity_linked, validate_applicant_intelligence_output,
)
from app.reporting.opportunity_universe import LONG_PENDING_APPLICATION_WINDOW_MONTHS, add_calendar_months


def _make_long_pending_opportunity(session, *, address, applicant_company, ref, council="testcouncil"):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    site = Site(council_code=council, canonical_address=f"{address}-canon", display_address=address)
    session.add(site)
    session.flush()
    app = Application(
        council_code=council, reference=ref, site_id=site.id, status="Under consideration",
        application_category="primary_residential", application_received=submitted.strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(app)
    session.flush()
    session.add(SchemeIntelligence(application_id=app.id, applicant_company=applicant_company))
    session.commit()
    return site, app


def _make_context(session, name, ref_suffix):
    _make_long_pending_opportunity(session, address=f"Site {ref_suffix}", applicant_company=name, ref=f"REF-{ref_suffix}")
    contexts = build_applicant_identity_contexts(session)
    return next(c for c in contexts.values() if c.display_name == name)


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


def _payload(primary_type, confidence, evidence, refs=None, secondary_roles=None, is_spv="UNKNOWN", parent_group=None):
    refs = refs if refs is not None else ([f"evidence:{i}" for i in range(len(evidence))] or ["fact:application_count"])
    return {
        "primary_type": primary_type, "primary_type_confidence": confidence, "primary_type_evidence_refs": refs,
        "secondary_roles": secondary_roles or [],
        "is_spv": is_spv, "parent_group": parent_group, "summary": f"{primary_type} classification.",
        "unresolved_questions": [], "evidence": evidence,
    }


def _official_evidence(claim="Evidenced organisation."):
    return [{
        "source_type": SOURCE_OFFICIAL_COMPANY_WEBSITE, "title": "Official Site", "url": "https://example.co.uk",
        "publisher": "Example Org", "claim": claim, "accessed_date": "",
    }]


# --- Every primary category round-trips correctly ---------------------------

_CATEGORY_CASES = [
    (PRIMARY_TYPE_HOUSEBUILDER, "Example Homes Builder Ltd"),
    (PRIMARY_TYPE_DEVELOPER, "Example General Developer Ltd"),
    (PRIMARY_TYPE_PROMOTER, "Example Strategic Land Co"),
    (PRIMARY_TYPE_PUBLIC_SECTOR, "Example Borough Council"),
    (PRIMARY_TYPE_HOUSING_ASSOCIATION, "Example Housing Trust"),
    (PRIMARY_TYPE_ESTATE, "Example Family Estate"),
    (PRIMARY_TYPE_SPV, "Example Project Vehicle No1 Ltd"),
    (PRIMARY_TYPE_FUND_INVESTOR, "Example Capital Partners Fund"),
    (PRIMARY_TYPE_LANDOWNER_PROPERTY_COMPANY, "Example Landholding Co"),
    (PRIMARY_TYPE_CONTRACTOR, "Example Building Contractors Ltd"),
    (PRIMARY_TYPE_CHARITY_INSTITUTION, "Example Foundation Trust"),
    (PRIMARY_TYPE_NOT_DETERMINED, "Example Ambiguous Entity Ltd"),
]


def test_every_primary_category_round_trips(session):
    for i, (primary_type, name) in enumerate(_CATEGORY_CASES):
        ctx = _make_context(session, name, f"cat{i}")
        evidence = [] if primary_type == PRIMARY_TYPE_NOT_DETERMINED else _official_evidence()
        confidence = CONFIDENCE_LOW if primary_type == PRIMARY_TYPE_NOT_DETERMINED else CONFIDENCE_HIGH
        refs = [] if primary_type == PRIMARY_TYPE_NOT_DETERMINED else ["evidence:0"]
        structured = _payload(primary_type, confidence, evidence, refs=refs)
        ok, problems = validate_applicant_intelligence_output(ctx, structured)
        assert ok, (primary_type, problems)

        result = generate_applicant_intelligence(session, _FakeClient(structured), ctx, force=True)
        assert result.status == "ok", (primary_type, result.generation_error)
        assert result.primary_type == primary_type
        row = get_applicant_intelligence(session, ctx.identity_ref)
        assert row.primary_type == primary_type


def test_private_is_distinct_from_not_determined(session):
    """Section 3's own explicit instruction: PRIVATE and NOT_DETERMINED
    mean different things - PRIVATE is the confident-individual outcome
    (zero AI cost, status=not_researched); NOT_DETERMINED is an
    organisation whose type could not be established from evidence
    (status=ok, a genuine attempted-and-inconclusive classification)."""
    person_ctx = _make_context(session, "Rowan Fielding", "person")  # bare 2-word name, no structural evidence
    from app.reporting.applicant_intelligence import is_person_shaped_identity
    assert is_person_shaped_identity(person_ctx) is True
    person_result = generate_applicant_intelligence(session, _FakeClient({}), person_ctx)
    assert person_result.primary_type == PRIMARY_TYPE_PRIVATE
    assert person_result.status == "not_researched"

    org_ctx = _make_context(session, "Example Ambiguous Org Ltd", "notdet")
    structured = _payload(PRIMARY_TYPE_NOT_DETERMINED, CONFIDENCE_LOW, [], refs=[])
    org_result = generate_applicant_intelligence(session, _FakeClient(structured), org_ctx, force=True)
    assert org_result.primary_type == PRIMARY_TYPE_NOT_DETERMINED
    assert org_result.status == "ok"  # a real, attempted classification - not a skipped one
    assert org_result.primary_type != person_result.primary_type


# --- Negative "name alone does not establish X" tests -----------------------

def test_homes_in_name_does_not_establish_housebuilder_alone(session):
    ceiling = evidence_supported_confidence_ceiling(["raw_name:Example Homes Ltd"], [])
    assert ceiling == CONFIDENCE_LOW


def test_land_in_name_does_not_establish_promoter_alone(session):
    ceiling = evidence_supported_confidence_ceiling(["raw_name:Example Land Holdings"], [])
    assert ceiling == CONFIDENCE_LOW


def test_developments_in_name_does_not_establish_developer_alone(session):
    ceiling = evidence_supported_confidence_ceiling(["raw_name:Example Developments Ltd"], [])
    assert ceiling == CONFIDENCE_LOW


def test_ltd_does_not_establish_spv_alone(session):
    """is_spv is validated as a schema enum (TRUE/FALSE/UNKNOWN) - the
    platform enforces no code-level inference from 'Ltd' at all; UNKNOWN
    is always a valid, accepted output regardless of the raw name."""
    ctx = _make_context(session, "Example Numbered Co 12 Ltd", "spvname")
    structured = _payload(PRIMARY_TYPE_NOT_DETERMINED, CONFIDENCE_LOW, [], refs=[], is_spv="UNKNOWN")
    ok, problems = validate_applicant_intelligence_output(ctx, structured)
    assert ok, problems


def test_application_submission_alone_does_not_establish_developer(session):
    """A bare occurrence ref (planning ACTIVITY only) caps at LOW - the
    same ceiling mechanism that already protects every other category."""
    ceiling = evidence_supported_confidence_ceiling(["occurrence:REF-1"], [])
    assert ceiling == CONFIDENCE_LOW


def test_applicant_does_not_establish_site_ownership(session):
    """ControlRelationship uses its OWN, entirely separate role vocabulary
    (OWNER/MORTGAGEE/...) - never any value from PRIMARY_TYPE_TAXONOMY -
    so an applicant's commercial type can never be confused with a
    site-ownership claim at the data-model level."""
    assert "OWNER" not in PRIMARY_TYPE_TAXONOMY
    assert "MORTGAGEE" not in PRIMARY_TYPE_TAXONOMY

    site, app = _make_long_pending_opportunity(session, address="Ownership Site", applicant_company="Example Developer Co Ltd", ref="REF-OWN")
    session.add(ControlRelationship(
        application_id=app.id, site_id=site.id, entity_name_raw="A Completely Different Owner Ltd", entity_type="company",
        role="OWNER", evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
        extraction_method="deterministic_regex",
    ))
    session.commit()
    contexts = build_applicant_identity_contexts(session)
    ctx = next(c for c in contexts.values() if c.display_name == "Example Developer Co Ltd")
    # The applicant's own context carries NO control evidence for a
    # DIFFERENT named owner - applicant identity and site ownership stay
    # two independent facts, never merged.
    assert len(ctx.control_evidence) == 0


# --- SPV parent/group treatment ----------------------------------------------

def test_spv_can_retain_parent_group_with_a_different_type(session):
    """Section 3's own worked example: 'ABC Manchester Developments Ltd'
    (SPV) / parent 'XYZ Homes plc' (HOUSEBUILDER) - the SPV's own primary
    type and its parent's type are independently recorded, never
    conflated."""
    ctx = _make_context(session, "ABC Manchester Developments Ltd", "spvparent")
    evidence = _official_evidence("A project-specific subsidiary of XYZ Homes plc, a housebuilder.")
    structured = _payload(
        PRIMARY_TYPE_SPV, CONFIDENCE_MEDIUM, evidence, refs=["evidence:0"],
        parent_group={"name": "XYZ Homes plc", "type": PRIMARY_TYPE_HOUSEBUILDER, "confidence": CONFIDENCE_MEDIUM, "evidence_refs": ["evidence:0"]},
    )
    ok, problems = validate_applicant_intelligence_output(ctx, structured)
    assert ok, problems
    result = generate_applicant_intelligence(session, _FakeClient(structured), ctx, force=True)
    assert result.primary_type == PRIMARY_TYPE_SPV
    assert result.parent_group["name"] == "XYZ Homes plc"
    assert result.parent_group["type"] == PRIMARY_TYPE_HOUSEBUILDER
    assert result.parent_group["type"] != PRIMARY_TYPE_SPV


def test_spv_parent_type_may_be_unknown(session):
    ctx = _make_context(session, "Project SPV Two Ltd", "spvunknown")
    evidence = _official_evidence("A subsidiary vehicle; parent structure not disclosed.")
    structured = _payload(
        PRIMARY_TYPE_SPV, CONFIDENCE_LOW, evidence, refs=["evidence:0"],
        parent_group={"name": "Undisclosed Parent Group", "type": PARENT_TYPE_UNKNOWN, "confidence": CONFIDENCE_LOW, "evidence_refs": ["evidence:0"]},
    )
    ok, problems = validate_applicant_intelligence_output(ctx, structured)
    assert ok, problems


# --- Secondary role retention -----------------------------------------------

def test_housing_association_can_retain_developer_as_secondary_role(session):
    ctx = _make_context(session, "Example Regional Housing Association", "harole")
    evidence = _official_evidence("A registered housing association with its own in-house development arm.")
    structured = _payload(
        PRIMARY_TYPE_HOUSING_ASSOCIATION, CONFIDENCE_HIGH, evidence, refs=["evidence:0"],
        secondary_roles=[{"role": PRIMARY_TYPE_DEVELOPER, "confidence": CONFIDENCE_MEDIUM, "evidence_refs": ["evidence:0"]}],
    )
    ok, problems = validate_applicant_intelligence_output(ctx, structured)
    assert ok, problems
    result = generate_applicant_intelligence(session, _FakeClient(structured), ctx, force=True)
    assert result.primary_type == PRIMARY_TYPE_HOUSING_ASSOCIATION
    assert result.secondary_roles[0]["role"] == PRIMARY_TYPE_DEVELOPER


def test_housebuilder_can_retain_developer_as_secondary_role(session):
    ctx = _make_context(session, "Example National Housebuilder Plc", "hbrole")
    evidence = _official_evidence("A national housebuilder with wider mixed-use development activity.")
    structured = _payload(
        PRIMARY_TYPE_HOUSEBUILDER, CONFIDENCE_HIGH, evidence, refs=["evidence:0"],
        secondary_roles=[{"role": PRIMARY_TYPE_DEVELOPER, "confidence": CONFIDENCE_MEDIUM, "evidence_refs": ["evidence:0"]}],
    )
    result = generate_applicant_intelligence(session, _FakeClient(structured), ctx, force=True)
    assert result.primary_type == PRIMARY_TYPE_HOUSEBUILDER
    assert any(r["role"] == PRIMARY_TYPE_DEVELOPER for r in result.secondary_roles)


def test_secondary_roles_reject_private_and_not_determined(session):
    """PRIVATE and NOT_DETERMINED are terminal, whole-identity outcomes -
    never a valid secondary role alongside some other primary type."""
    assert PRIMARY_TYPE_PRIVATE not in SECONDARY_ROLE_TAXONOMY
    assert PRIMARY_TYPE_NOT_DETERMINED not in SECONDARY_ROLE_TAXONOMY


# --- Promoter is not silently generalised to Developer -----------------------

def test_promoter_persists_as_promoter_not_generalised_to_developer(session):
    """No code-level hierarchy exists that could silently prefer generic
    DEVELOPER over a more specific, evidenced PROMOTER classification -
    primary_type is persisted and returned exactly as the model (here, the
    fake client standing in for it) provided, unmodified by anything in
    the pipeline other than the confidence ceiling."""
    ctx = _make_context(session, "Example Land Promotions Co", "promoter")
    evidence = _official_evidence("A specialist land promoter securing planning consents on behalf of landowners.")
    structured = _payload(PRIMARY_TYPE_PROMOTER, CONFIDENCE_HIGH, evidence, refs=["evidence:0"])
    result = generate_applicant_intelligence(session, _FakeClient(structured), ctx, force=True)
    assert result.primary_type == PRIMARY_TYPE_PROMOTER
    assert result.primary_type != PRIMARY_TYPE_DEVELOPER


# --- Regression re-confirmation (Sections 15/16/17/18 of this amendment) ----

def test_strategic_land_only_still_does_not_trigger_applicant_intelligence(session):
    from app.db.models import LocalPlan, LocalPlanSite
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Plan", status="adopted", raw_status="adopted")
    session.add(plan)
    session.commit()
    session.add(LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan.id, policy_reference="TAX1", site_name="Strategic Only Allocation",
        plan_name="Test Plan", plan_status="adopted", minimum_dwellings=100, matched_site_id=None,
    ))
    session.commit()
    contexts = build_applicant_identity_contexts(session)
    assert len(contexts) == 0


def test_gate_1c_universe_and_buyer_matching_unaffected_by_taxonomy_change(session):
    from app.policy.buyer_matching import assess_buyer_fit, build_planning_delivery_matching_facts
    from app.policy.buyer_profiles import BUYER_PROFILES
    from app.reporting.opportunity_universe import build_current_opportunity_universe

    _make_long_pending_opportunity(session, address="Regression Site", applicant_company="Regression Org Ltd", ref="REF-REGR")
    universe_before = build_current_opportunity_universe(session)
    build_applicant_identity_contexts(session)  # exercise the taxonomy module
    universe_after = build_current_opportunity_universe(session)
    assert len(universe_before) == len(universe_after)

    facts = build_planning_delivery_matching_facts(None)
    assessment = assess_buyer_fit(BUYER_PROFILES["nesten_homes"], facts)
    assert assessment.classification is not None
