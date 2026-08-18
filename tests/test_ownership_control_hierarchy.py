"""Stage 4B.3 ("Local Plan Ownership & Control Hierarchy UI Refinement")
tests - covers the 21 items from the task's own Section 13. This is a
presentation refinement over Stage 4B.2's existing
app.reporting.ownership_control - these tests focus on the NEW hierarchy
fields (SiteControlSection.applications/capacity_known/capacity/
residual_capacity/show_ownership_intelligence_gap_cue) and the North Leigh
Park regression; Stage 4B.2's own scoping/wording guarantees are already
covered by tests/test_ownership_control_reporting.py and are not
duplicated wholesale here. Every test runs against the shared in-memory
SQLite `session` fixture (tests/conftest.py) - never the real production
database.
"""
from __future__ import annotations

import pathlib

from app.db.models import Application, ControlRelationship, Site
from app.reporting.allocation_development_coverage import SiteActivitySummary
from app.reporting.ownership_control import (
    EMPTY_STATE_ALLOCATION_RESIDUAL,
    EMPTY_STATE_ALLOCATION_SITE,
    OWNERSHIP_INTELLIGENCE_GAP_CUE,
    SOURCE_NOTE,
    get_allocation_control_intelligence,
)


def _make_site(session, council_code: str, address: str) -> Site:
    site = Site(council_code=council_code, canonical_address=address, display_address=address)
    session.add(site)
    session.flush()
    return site


def _make_application(
    session, council_code: str, reference: str, *, site_id: int | None = None,
    status: str | None = None, decision: str | None = None,
) -> Application:
    app = Application(council_code=council_code, reference=reference, site_id=site_id, status=status, decision=decision)
    session.add(app)
    session.flush()
    return app


def _make_relationship(
    session, *, application_id: int, site_id: int, entity_name_raw: str, role: str,
    evidence_basis: str, evidence_category: str, review_status: str = "auto_applied",
) -> ControlRelationship:
    row = ControlRelationship(
        application_id=application_id, site_id=site_id, entity_name_raw=entity_name_raw, role=role,
        evidence_basis=evidence_basis, evidence_category=evidence_category, extraction_method="deterministic_regex",
        confidence="medium", review_status=review_status,
    )
    session.add(row)
    session.flush()
    return row


def _read_source(relative_path: str) -> str:
    return (pathlib.Path(__file__).resolve().parents[1] / relative_path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Items 1/5 - one distinct card per related Site, never a single allocation-
# wide owner
# ---------------------------------------------------------------------------


def test_one_distinct_section_per_related_site_never_fewer(session):
    site_a = _make_site(session, "testcouncil", "Site A")
    site_b = _make_site(session, "testcouncil", "Site B")
    site_c = _make_site(session, "testcouncil", "Site C")
    app_a = _make_application(session, "testcouncil", "APP/A", site_id=site_a.id)
    _make_relationship(
        session, application_id=app_a.id, site_id=site_a.id, entity_name_raw="Owner A Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
    )
    session.commit()

    summaries = [
        SiteActivitySummary(site_id=site_a.id, site=site_a, applications=[app_a], representative_application=app_a, capacity_known=True, capacity=10),
        SiteActivitySummary(site_id=site_b.id, site=site_b, applications=[], representative_application=None, capacity_known=False, capacity=None),
        SiteActivitySummary(site_id=site_c.id, site=site_c, applications=[], representative_application=None, capacity_known=False, capacity=None),
    ]
    sections = get_allocation_control_intelligence(session, summaries, indicative_residual_capacity=100)

    site_sections = [s for s in sections if not s.is_residual]
    assert len(site_sections) == 3
    assert {s.site_id for s in site_sections} == {site_a.id, site_b.id, site_c.id}
    # No section anywhere aggregates every related Site's evidence together.
    assert len(sections) == 4  # 3 Sites + 1 residual, never merged into fewer


# ---------------------------------------------------------------------------
# Items 2/3/18 - North Leigh Park-shaped regression: two Sites each with
# their OWN distinct owner, never crossing into each other
# ---------------------------------------------------------------------------


def test_north_leigh_park_regression(session):
    """Generic (not hardcoded) regression mirroring the real production
    North Leigh Park allocation structure: three related Sites - one with
    no evidence, one with a Morris Homes/Persimmon-style joint declaration,
    one with a CLS-UK-style single declaration - plus positive residual
    capacity. Neither owner may ever appear against the other Site, the
    third (evidence-free) Site, or the residual section."""
    north_leigh_site = _make_site(session, "testcouncil", "North Leigh Development Site")
    rectory_lane_site = _make_site(session, "testcouncil", "Land South Of Rectory Lane")
    king_street_site = _make_site(session, "testcouncil", "35-45 King Street")

    north_leigh_app = _make_application(session, "testcouncil", "A/24/96937/NMAS", site_id=north_leigh_site.id, status="Unknown", decision="Agreed")
    rectory_app = _make_application(session, "testcouncil", "A/26/100539/MAJOR", site_id=rectory_lane_site.id, status="Registered")
    king_street_app = _make_application(session, "testcouncil", "A/26/100631/MAJOR", site_id=king_street_site.id, status="Registered")

    _make_relationship(
        session, application_id=rectory_app.id, site_id=rectory_lane_site.id,
        entity_name_raw="Morris Homes (North) Limited & Persimmon Homes (North West) Limited", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
    )
    _make_relationship(
        session, application_id=king_street_app.id, site_id=king_street_site.id,
        entity_name_raw="CLS-UK", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
    )
    session.commit()

    summaries = [
        SiteActivitySummary(site_id=north_leigh_site.id, site=north_leigh_site, applications=[north_leigh_app], representative_application=north_leigh_app, capacity_known=True, capacity=2),
        SiteActivitySummary(site_id=rectory_lane_site.id, site=rectory_lane_site, applications=[rectory_app], representative_application=rectory_app, capacity_known=True, capacity=136),
        SiteActivitySummary(site_id=king_street_site.id, site=king_street_site, applications=[king_street_app], representative_application=king_street_app, capacity_known=True, capacity=18),
    ]
    sections = get_allocation_control_intelligence(session, summaries, indicative_residual_capacity=1244)

    by_site = {s.site_id: s for s in sections if not s.is_residual}
    residual = next(s for s in sections if s.is_residual)

    # Item 4 - the evidence-free Site shows no evidence of its own.
    assert by_site[north_leigh_site.id].groups == []

    # Items 2/3 - each owner stays scoped to its own Site.
    rectory_names = {g.entity_name_raw for g in by_site[rectory_lane_site.id].groups}
    king_street_names = {g.entity_name_raw for g in by_site[king_street_site.id].groups}
    assert rectory_names == {"Morris Homes (North) Limited & Persimmon Homes (North West) Limited"}
    assert king_street_names == {"CLS-UK"}
    assert "CLS-UK" not in rectory_names
    assert "Morris Homes (North) Limited & Persimmon Homes (North West) Limited" not in king_street_names

    # Neither owner appears against the third Site or the residual section.
    assert by_site[north_leigh_site.id].groups == []
    assert residual.groups == []

    # Item 6 - Application reference shown where available.
    assert by_site[rectory_lane_site.id].representative_application_reference == "A/26/100539/MAJOR"
    assert by_site[king_street_site.id].representative_application_reference == "A/26/100631/MAJOR"

    # Item 7/8 - capacity reused verbatim from Stage 3A, never recomputed.
    assert by_site[rectory_lane_site.id].capacity_known is True
    assert by_site[rectory_lane_site.id].capacity == 136
    assert by_site[king_street_site.id].capacity == 18

    # Item 9/12 - positive residual capacity gets its own section with the
    # restrained investigation cue, never an availability/opportunity claim.
    assert residual.residual_capacity == 1244
    assert residual.show_ownership_intelligence_gap_cue is True


# ---------------------------------------------------------------------------
# Item 19 - North of Mosley Common regression, re-verified through the new
# hierarchy fields
# ---------------------------------------------------------------------------


def test_north_of_mosley_common_regression_hierarchy_fields(session):
    southern = _make_site(session, "testcouncil", "North of Mosley Common - Southern Parcel")
    southern_app = _make_application(session, "testcouncil", "JPA32/SOUTH", site_id=southern.id, status="Decided", decision="Approved")
    _make_relationship(
        session, application_id=southern_app.id, site_id=southern.id, entity_name_raw="Taylor Wimpey", role="DEVELOPER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_DEVELOPER",
    )
    session.commit()

    summaries = [
        SiteActivitySummary(site_id=southern.id, site=southern, applications=[southern_app], representative_application=southern_app, capacity_known=True, capacity=244),
    ]
    sections = get_allocation_control_intelligence(session, summaries, indicative_residual_capacity=856)

    southern_section, residual_section = sections
    assert southern_section.capacity == 244
    assert southern_section.representative_application_reference == "JPA32/SOUTH"
    assert [g.entity_name_raw for g in southern_section.groups] == ["Taylor Wimpey"]

    assert residual_section.is_residual is True
    assert residual_section.residual_capacity == 856
    assert residual_section.groups == []
    assert "Taylor Wimpey" not in [g.entity_name_raw for g in residual_section.groups]
    assert residual_section.show_ownership_intelligence_gap_cue is True


# ---------------------------------------------------------------------------
# Item 4 - Site-specific empty state wording
# ---------------------------------------------------------------------------


def test_site_specific_empty_state_wording_exact():
    assert EMPTY_STATE_ALLOCATION_SITE == (
        "No ownership/control evidence currently identified for this Site from linked planning Applications."
    )
    assert "owner unknown" not in EMPTY_STATE_ALLOCATION_SITE.lower()


# ---------------------------------------------------------------------------
# Items 6/7/8 - Application reference + capacity shown only from existing
# safe data, no new capacity calculation
# ---------------------------------------------------------------------------


def test_application_reference_and_representative_shown(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app1 = _make_application(session, "testcouncil", "APP/1", site_id=site.id, status="Registered")
    app2 = _make_application(session, "testcouncil", "APP/2", site_id=site.id, status="Decided", decision="Approved")
    session.commit()

    summaries = [
        SiteActivitySummary(site_id=site.id, site=site, applications=[app1, app2], representative_application=app2, capacity_known=False, capacity=None),
    ]
    [section] = get_allocation_control_intelligence(session, summaries, indicative_residual_capacity=None)

    assert section.representative_application_reference == "APP/2"
    assert len(section.applications) == 2
    rep = next(a for a in section.applications if a.is_representative)
    other = next(a for a in section.applications if not a.is_representative)
    assert rep.reference == "APP/2"
    assert other.reference == "APP/1"


def test_capacity_omitted_when_not_safely_available(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    session.commit()

    summaries = [
        SiteActivitySummary(site_id=site.id, site=site, applications=[app], representative_application=app, capacity_known=False, capacity=None),
    ]
    [section] = get_allocation_control_intelligence(session, summaries, indicative_residual_capacity=None)

    assert section.capacity_known is False
    assert section.capacity is None


def test_capacity_reused_verbatim_never_summed_across_applications(session):
    """Item 8 - a Site with TWO Applications must still show the ONE safe
    per-Site capacity figure Stage 3A already computed (SiteActivitySummary.
    capacity), never a sum of both Applications' own unit counts."""
    site = _make_site(session, "testcouncil", "1 Test Street")
    app1 = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    app2 = _make_application(session, "testcouncil", "APP/2", site_id=site.id)
    session.commit()

    summaries = [
        SiteActivitySummary(site_id=site.id, site=site, applications=[app1, app2], representative_application=app1, capacity_known=True, capacity=136),
    ]
    [section] = get_allocation_control_intelligence(session, summaries, indicative_residual_capacity=None)

    assert section.capacity == 136  # not 272 (would imply a naive per-app sum)


# ---------------------------------------------------------------------------
# Items 9/10/11 - residual section separation + empty-state wording
# ---------------------------------------------------------------------------


def test_positive_residual_capacity_gets_separate_section(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    summaries = [
        SiteActivitySummary(site_id=site.id, site=site, applications=[], representative_application=None, capacity_known=False, capacity=None),
    ]
    sections = get_allocation_control_intelligence(session, summaries, indicative_residual_capacity=500)
    residual_sections = [s for s in sections if s.is_residual]
    assert len(residual_sections) == 1
    assert residual_sections[0].residual_capacity == 500


def test_zero_or_none_residual_capacity_shows_no_residual_section(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    summaries = [
        SiteActivitySummary(site_id=site.id, site=site, applications=[], representative_application=None, capacity_known=False, capacity=None),
    ]
    for residual in (None, 0):
        sections = get_allocation_control_intelligence(session, summaries, indicative_residual_capacity=residual)
        assert not any(s.is_residual for s in sections)


def test_residual_section_never_inherits_site_evidence(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
    )
    session.commit()

    summaries = [
        SiteActivitySummary(site_id=site.id, site=site, applications=[app], representative_application=app, capacity_known=True, capacity=50),
    ]
    sections = get_allocation_control_intelligence(session, summaries, indicative_residual_capacity=200)
    residual = next(s for s in sections if s.is_residual)
    assert residual.groups == []


def test_residual_empty_state_wording_exact():
    assert EMPTY_STATE_ALLOCATION_RESIDUAL == "No ownership/control evidence currently identified."


# ---------------------------------------------------------------------------
# Item 12 - investigation cue never claims availability/opportunity
# ---------------------------------------------------------------------------


def test_investigation_cue_never_claims_availability_or_opportunity():
    forbidden_terms = [
        "available land", "available capacity", "remaining land for sale", "uncontrolled land",
        "owner unknown", "land opportunity", "available opportunity", "jv opportunity",
    ]
    lowered = OWNERSHIP_INTELLIGENCE_GAP_CUE.lower()
    for term in forbidden_terms:
        assert term not in lowered
    assert OWNERSHIP_INTELLIGENCE_GAP_CUE == "Ownership intelligence gap — investigate"


def test_investigation_cue_only_set_on_residual_section(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
    )
    session.commit()

    summaries = [
        SiteActivitySummary(site_id=site.id, site=site, applications=[app], representative_application=app, capacity_known=True, capacity=50),
    ]
    sections = get_allocation_control_intelligence(session, summaries, indicative_residual_capacity=200)

    site_section = next(s for s in sections if not s.is_residual)
    residual_section = next(s for s in sections if s.is_residual)
    assert site_section.show_ownership_intelligence_gap_cue is False
    assert residual_section.show_ownership_intelligence_gap_cue is True


# ---------------------------------------------------------------------------
# Items 13/14/15/16 - Certificate A / S106 wording, needs_confirmation,
# rejected behaviour unchanged
# ---------------------------------------------------------------------------


def test_certificate_a_and_s106_wording_unchanged(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="Cert A Co", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
    )
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="S106 Owner Co", role="APPLICANT",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER",
    )
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="S106 Bank Plc", role="MORTGAGEE",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_MORTGAGEE",
    )
    session.commit()

    summaries = [
        SiteActivitySummary(site_id=site.id, site=site, applications=[app], representative_application=app, capacity_known=False, capacity=None),
    ]
    [section] = get_allocation_control_intelligence(session, summaries, indicative_residual_capacity=None)
    labels = {g.entity_name_raw: g.role_label for g in section.groups}
    assert labels["Cert A Co"] == "Planning ownership declaration"
    assert labels["S106 Owner Co"] == "S106 Owner"
    assert labels["S106 Bank Plc"] == "S106 Mortgagee"


def test_needs_confirmation_still_flagged_within_hierarchy(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
        review_status="needs_confirmation",
    )
    session.commit()

    summaries = [
        SiteActivitySummary(site_id=site.id, site=site, applications=[app], representative_application=app, capacity_known=False, capacity=None),
    ]
    [section] = get_allocation_control_intelligence(session, summaries, indicative_residual_capacity=None)
    assert section.groups[0].needs_review is True


def test_rejected_still_excluded_within_hierarchy(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="Rejected Co", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
        review_status="rejected",
    )
    session.commit()

    summaries = [
        SiteActivitySummary(site_id=site.id, site=site, applications=[app], representative_application=app, capacity_known=False, capacity=None),
    ]
    [section] = get_allocation_control_intelligence(session, summaries, indicative_residual_capacity=None)
    assert section.groups == []


# ---------------------------------------------------------------------------
# Item 17 - source note preserved
# ---------------------------------------------------------------------------


def test_source_note_preserved_exact():
    assert SOURCE_NOTE == (
        "Source note: Ownership and control information is extracted from planning documents held by "
        "PropertyAIgent, including planning application ownership certificates and Section 106 agreements. "
        "It may not reflect current registered ownership."
    )


def test_source_note_wired_into_allocation_ui():
    src = _read_source("app/ui/pages/3_Local_Plan_Sites.py")
    assert "SOURCE_NOTE" in src


# ---------------------------------------------------------------------------
# Item 21 - no OpenAI / external API calls anywhere in the touched code
# ---------------------------------------------------------------------------


def test_no_ai_or_external_calls_in_reporting_or_ui():
    for path in ("app/reporting/ownership_control.py", "app/ui/pages/3_Local_Plan_Sites.py"):
        lowered = _read_source(path).lower()
        assert "openai" not in lowered
        assert "companies_house" not in lowered
        assert "land_registry" not in lowered
