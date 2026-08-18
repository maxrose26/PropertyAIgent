"""Stage 4B.2 ("Ownership & Control Intelligence - Customer-Facing UI")
tests - app.reporting.ownership_control, the read-only reporting/query
layer over ControlRelationship. Every test runs against the shared
in-memory SQLite `session` fixture (tests/conftest.py) - never the real
production database. Covers the 29 items from the task's own Section 17.
"""
from __future__ import annotations

import datetime as dt

from app.db.models import Application, Company, ControlRelationship, Site
from app.reporting.allocation_development_coverage import SiteActivitySummary
from app.reporting.ownership_control import (
    EMPTY_STATE_ALLOCATION_RESIDUAL,
    EMPTY_STATE_APPLICATION,
    EMPTY_STATE_SITE,
    EVIDENCE_SNIPPET_MAX_CHARS,
    SOURCE_NOTE,
    get_allocation_control_intelligence,
    get_application_control_intelligence,
    get_site_control_detail,
    get_site_control_intelligence,
)


def _make_site(session, council_code: str, address: str) -> Site:
    site = Site(council_code=council_code, canonical_address=address, display_address=address)
    session.add(site)
    session.flush()
    return site


def _make_application(session, council_code: str, reference: str, *, site_id: int | None = None) -> Application:
    app = Application(council_code=council_code, reference=reference, site_id=site_id)
    session.add(app)
    session.flush()
    return app


def _make_relationship(
    session, *, application_id: int | None = None, site_id: int | None = None,
    entity_name_raw: str, role: str, evidence_basis: str, evidence_category: str,
    confidence: str | None = "medium", review_status: str = "auto_applied",
    company_id: int | None = None, title_number: str | None = None,
    evidence_snippet: str | None = None, evidence_date: dt.datetime | None = None,
) -> ControlRelationship:
    row = ControlRelationship(
        application_id=application_id, site_id=site_id, entity_name_raw=entity_name_raw, role=role,
        evidence_basis=evidence_basis, evidence_category=evidence_category, extraction_method="deterministic_regex",
        confidence=confidence, review_status=review_status, company_id=company_id, title_number=title_number,
        evidence_snippet=evidence_snippet, evidence_date=evidence_date,
    )
    session.add(row)
    session.flush()
    return row


# ---------------------------------------------------------------------------
# Items 1/2 - Application scoping
# ---------------------------------------------------------------------------


def test_application_displays_own_relationships(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
    )
    session.commit()

    views = get_application_control_intelligence(session, app.id)
    assert len(views) == 1
    assert views[0].entity_name_raw == "ABC Developments Ltd"
    assert views[0].application_id == app.id


def test_application_does_not_display_another_applications_relationships(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app1 = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    app2 = _make_application(session, "testcouncil", "APP/2", site_id=site.id)
    _make_relationship(
        session, application_id=app1.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
    )
    session.commit()

    assert get_application_control_intelligence(session, app2.id) == []


# ---------------------------------------------------------------------------
# Items 3/4 - Site scoping
# ---------------------------------------------------------------------------


def test_site_aggregates_across_own_applications(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app1 = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    app2 = _make_application(session, "testcouncil", "APP/2", site_id=site.id)
    _make_relationship(
        session, application_id=app1.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
    )
    _make_relationship(
        session, application_id=app2.id, site_id=site.id, entity_name_raw="XYZ Bank Plc", role="MORTGAGEE",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_MORTGAGEE",
    )
    session.commit()

    groups = get_site_control_intelligence(session, site.id)
    names = {g.entity_name_raw for g in groups}
    assert names == {"ABC Developments Ltd", "XYZ Bank Plc"}


def test_site_does_not_inherit_from_another_site(session):
    site_a = _make_site(session, "testcouncil", "Site A")
    site_b = _make_site(session, "testcouncil", "Site B")
    app_a = _make_application(session, "testcouncil", "APP/A", site_id=site_a.id)
    _make_relationship(
        session, application_id=app_a.id, site_id=site_a.id, entity_name_raw="Site A Developer Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
    )
    session.commit()

    assert get_site_control_intelligence(session, site_b.id) == []


# ---------------------------------------------------------------------------
# Items 5/6/7/26 - Allocation Site-separation + North of Mosley Common
# ---------------------------------------------------------------------------


def test_allocation_keeps_evidence_separated_by_related_site(session):
    southern = _make_site(session, "testcouncil", "Southern Parcel")
    northern = _make_site(session, "testcouncil", "Northern Parcel")
    southern_app = _make_application(session, "testcouncil", "APP/SOUTH", site_id=southern.id)
    _make_relationship(
        session, application_id=southern_app.id, site_id=southern.id, entity_name_raw="Taylor Wimpey", role="DEVELOPER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_DEVELOPER",
    )
    session.commit()

    summaries = [
        SiteActivitySummary(site_id=southern.id, site=southern, applications=[southern_app], representative_application=southern_app, capacity_known=True, capacity=244),
        SiteActivitySummary(site_id=northern.id, site=northern, applications=[], representative_application=None, capacity_known=False, capacity=None),
    ]
    sections = get_allocation_control_intelligence(session, summaries, indicative_residual_capacity=None)

    assert len(sections) == 2
    southern_section = next(s for s in sections if s.site_id == southern.id)
    northern_section = next(s for s in sections if s.site_id == northern.id)
    assert {g.entity_name_raw for g in southern_section.groups} == {"Taylor Wimpey"}
    assert northern_section.groups == []


def test_allocation_multi_site_does_not_manufacture_a_single_owner(session):
    southern = _make_site(session, "testcouncil", "Southern Parcel")
    southern_app = _make_application(session, "testcouncil", "APP/SOUTH", site_id=southern.id)
    _make_relationship(
        session, application_id=southern_app.id, site_id=southern.id, entity_name_raw="Taylor Wimpey", role="DEVELOPER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_DEVELOPER",
    )
    session.commit()

    summaries = [
        SiteActivitySummary(site_id=southern.id, site=southern, applications=[southern_app], representative_application=southern_app, capacity_known=True, capacity=244),
    ]
    sections = get_allocation_control_intelligence(session, summaries, indicative_residual_capacity=856)

    # No section ever aggregates across every related Site into one figure -
    # exactly one section per Site plus the residual section, never fewer.
    assert len(sections) == 2
    residual = next(s for s in sections if s.is_residual)
    assert residual.groups == []


def test_residual_allocation_land_does_not_inherit_from_developed_phase(session):
    southern = _make_site(session, "testcouncil", "Southern Parcel")
    southern_app = _make_application(session, "testcouncil", "APP/SOUTH", site_id=southern.id)
    _make_relationship(
        session, application_id=southern_app.id, site_id=southern.id, entity_name_raw="Taylor Wimpey", role="DEVELOPER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_DEVELOPER",
    )
    session.commit()

    summaries = [
        SiteActivitySummary(site_id=southern.id, site=southern, applications=[southern_app], representative_application=southern_app, capacity_known=True, capacity=244),
    ]
    sections = get_allocation_control_intelligence(session, summaries, indicative_residual_capacity=856)

    residual = next(s for s in sections if s.is_residual)
    assert residual.label == "Residual allocation land"
    assert residual.site_id is None
    assert residual.groups == []
    assert "Taylor Wimpey" not in [g.entity_name_raw for g in residual.groups]


def test_north_of_mosley_common_regression(session):
    """The exact scenario this whole architecture exists to get right
    (Stage 4B's model docstring, Section 7 of this task): a 244-unit
    identified Southern Parcel scheme within a ~1,100-unit allocation
    (JPA 32), leaving ~856 units of residual allocation land. Taylor
    Wimpey's evidence must appear ONLY against the Southern Parcel
    section, never against the residual land."""
    southern = _make_site(session, "testcouncil", "North of Mosley Common - Southern Parcel")
    southern_app = _make_application(session, "testcouncil", "JPA32/SOUTH", site_id=southern.id)
    _make_relationship(
        session, application_id=southern_app.id, site_id=southern.id, entity_name_raw="Taylor Wimpey", role="DEVELOPER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_DEVELOPER",
    )
    session.commit()

    summaries = [
        SiteActivitySummary(site_id=southern.id, site=southern, applications=[southern_app], representative_application=southern_app, capacity_known=True, capacity=244),
    ]
    sections = get_allocation_control_intelligence(session, summaries, indicative_residual_capacity=856)

    assert len(sections) == 2
    southern_section, residual_section = sections
    assert southern_section.label == "North of Mosley Common - Southern Parcel"
    assert [g.entity_name_raw for g in southern_section.groups] == ["Taylor Wimpey"]
    assert residual_section.label == "Residual allocation land"
    assert residual_section.groups == []


# ---------------------------------------------------------------------------
# Items 8/9/10/11 - Customer-facing wording
# ---------------------------------------------------------------------------


def test_certificate_a_displays_as_planning_ownership_declaration(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
    )
    session.commit()

    [view] = get_application_control_intelligence(session, app.id)
    assert view.role_label == "Planning ownership declaration"
    assert "current owner" not in view.role_label.lower()
    assert view.evidence_source_label == "Planning Application Form — Certificate A"


def test_s106_owner_displays_distinctly(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER",
    )
    session.commit()

    [view] = get_application_control_intelligence(session, app.id)
    assert view.role_label == "S106 Owner"


def test_s106_mortgagee_displays_distinctly(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="XYZ Bank Plc", role="MORTGAGEE",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_MORTGAGEE",
    )
    session.commit()

    [view] = get_application_control_intelligence(session, app.id)
    assert view.role_label == "S106 Mortgagee"


def test_mortgagee_never_displayed_as_owner(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="XYZ Bank Plc", role="MORTGAGEE",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_MORTGAGEE",
    )
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER",
    )
    session.commit()

    views = get_application_control_intelligence(session, app.id)
    mortgagee = next(v for v in views if v.role == "MORTGAGEE")
    owner = next(v for v in views if v.role == "OWNER")
    assert mortgagee.role_label != owner.role_label
    assert "owner" not in mortgagee.role_label.lower()

    # Also never collapsed into the same display group at Site level.
    groups = get_site_control_intelligence(session, site.id)
    assert len(groups) == 2


# ---------------------------------------------------------------------------
# Items 12/13 - review_status handling
# ---------------------------------------------------------------------------


def test_needs_confirmation_clearly_marked(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
        review_status="needs_confirmation",
    )
    session.commit()

    [view] = get_application_control_intelligence(session, app.id)
    assert view.needs_review is True
    assert view.review_status == "needs_confirmation"


def test_rejected_excluded_from_accepted_summary(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="Rejected Co Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
        review_status="rejected",
    )
    session.commit()

    assert get_application_control_intelligence(session, app.id) == []
    assert get_site_control_intelligence(session, site.id) == []


# ---------------------------------------------------------------------------
# Item 14 - unresolved company_id still displayed
# ---------------------------------------------------------------------------


def test_unresolved_entity_still_displayed(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="Unresolved Entity Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
        company_id=None,
    )
    session.commit()

    [view] = get_application_control_intelligence(session, app.id)
    assert view.entity_name_raw == "Unresolved Entity Ltd"
    assert view.company_id is None


def test_resolved_company_id_also_displayed(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    company = Company(name_raw="ABC Developments Ltd", name_normalized="abc developments ltd")
    session.add(company)
    session.flush()
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
        company_id=company.id,
    )
    session.commit()

    [view] = get_application_control_intelligence(session, app.id)
    assert view.company_id == company.id


# ---------------------------------------------------------------------------
# Items 15/16/17 - title number / evidence date / bounded snippet
# ---------------------------------------------------------------------------


def test_title_number_displayed_only_where_present(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER", title_number="GM123456",
    )
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="XYZ Bank Plc", role="MORTGAGEE",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_MORTGAGEE",
    )
    session.commit()

    views = get_application_control_intelligence(session, app.id)
    owner = next(v for v in views if v.role == "OWNER")
    mortgagee = next(v for v in views if v.role == "MORTGAGEE")
    assert owner.title_number == "GM123456"
    assert mortgagee.title_number is None


def test_evidence_date_displayed_only_where_present(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    dated = _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="A", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER",
        evidence_date=dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc),
    )
    undated = _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="B", role="DEVELOPER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_DEVELOPER",
    )
    session.commit()

    views = get_application_control_intelligence(session, app.id)
    view_dated = next(v for v in views if v.id == dated.id)
    view_undated = next(v for v in views if v.id == undated.id)
    assert view_dated.evidence_date is not None
    assert view_undated.evidence_date is None


def test_evidence_snippet_remains_bounded(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    long_snippet = "A" * (EVIDENCE_SNIPPET_MAX_CHARS * 3)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
        evidence_snippet=long_snippet,
    )
    session.commit()

    [view] = get_application_control_intelligence(session, app.id)
    assert view.evidence_snippet is not None
    assert len(view.evidence_snippet) <= EVIDENCE_SNIPPET_MAX_CHARS + 1  # +1 for the trailing ellipsis char
    assert view.evidence_snippet != long_snippet


# ---------------------------------------------------------------------------
# Item 18 - empty-state wording
# ---------------------------------------------------------------------------


def test_empty_state_wording_exact(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    session.commit()

    assert get_application_control_intelligence(session, app.id) == []
    assert get_site_control_intelligence(session, site.id) == []
    assert EMPTY_STATE_APPLICATION == (
        "No ownership/control evidence has yet been identified from the planning documents held by PropertyAIgent."
    )
    assert EMPTY_STATE_SITE == (
        "No ownership/control evidence has yet been identified for this Site from linked planning Applications."
    )
    assert EMPTY_STATE_ALLOCATION_RESIDUAL == "No ownership/control evidence currently identified."
    assert "owner unknown" not in EMPTY_STATE_APPLICATION.lower()
    assert "owner unknown" not in EMPTY_STATE_SITE.lower()
    assert "owner unknown" not in EMPTY_STATE_ALLOCATION_RESIDUAL.lower()


# ---------------------------------------------------------------------------
# Items 19-23 - source note
# ---------------------------------------------------------------------------


def test_source_note_exact_wording():
    assert SOURCE_NOTE == (
        "Source note: Ownership and control information is extracted from planning documents held by "
        "PropertyAIgent, including planning application ownership certificates and Section 106 agreements. "
        "It may not reflect current registered ownership."
    )


def test_source_note_does_not_claim_land_registry_verification():
    assert "Land Registry" not in SOURCE_NOTE
    assert "verified" not in SOURCE_NOTE.lower()


def test_source_note_wired_into_all_three_ui_surfaces():
    """Static wiring check (Section 19's own instruction that passing unit
    tests alone is not sufficient is honoured separately via manual browser
    verification) - confirms the Site Profile page (which renders both the
    Application- and Site-level Ownership & Control sections in one tab)
    and the Allocation detail page both actually import and render
    SOURCE_NOTE, rather than only defining it and never using it."""
    site_profile_src = _read_source("app/ui/site_profile_view.py")
    allocation_src = _read_source("app/ui/pages/3_Local_Plan_Sites.py")
    assert "SOURCE_NOTE" in site_profile_src
    assert "SOURCE_NOTE" in allocation_src


def test_specific_evidence_source_remains_visible_alongside_source_note(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
    )
    session.commit()

    [view] = get_application_control_intelligence(session, app.id)
    # The specific evidence source label is independent of, and never
    # replaced by, the generic source note.
    assert view.evidence_source_label == "Planning Application Form — Certificate A"
    assert view.evidence_source_label != SOURCE_NOTE


def _read_source(relative_path: str) -> str:
    import pathlib
    return (pathlib.Path(__file__).resolve().parents[1] / relative_path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Items 24/25 - duplicate-evidence grouping never merges roles or Sites
# ---------------------------------------------------------------------------


def test_grouping_does_not_merge_different_roles_for_same_entity(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER",
    )
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="DEVELOPER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_DEVELOPER",
    )
    session.commit()

    groups = get_site_control_intelligence(session, site.id)
    assert len(groups) == 2
    assert {g.role for g in groups} == {"OWNER", "DEVELOPER"}


def test_grouping_does_merge_same_entity_role_across_multiple_documents(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app1 = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    app2 = _make_application(session, "testcouncil", "APP/2", site_id=site.id)
    _make_relationship(
        session, application_id=app1.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
    )
    _make_relationship(
        session, application_id=app2.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
    )
    session.commit()

    groups = get_site_control_intelligence(session, site.id)
    assert len(groups) == 1
    assert groups[0].supporting_evidence_count == 2
    assert set(groups[0].application_references) == {"APP/1", "APP/2"}
    # Both underlying rows remain inspectable - grouping is display-layer only.
    assert len(groups[0].items) == 2


def test_grouping_does_not_merge_different_evidence_classes_under_one_label(session):
    """A Certificate A declaration and an S106-defined role for the SAME
    nominal role must never collapse under one label - the exact
    Certificate-A-vs-S106 distinction Section 8 requires stays visible."""
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
    )
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER",
    )
    session.commit()

    groups = get_site_control_intelligence(session, site.id)
    assert len(groups) == 2
    labels = {g.role_label for g in groups}
    assert labels == {"Planning ownership declaration", "S106 Owner"}


def test_grouping_does_not_merge_across_different_sites(session):
    site_a = _make_site(session, "testcouncil", "Site A")
    site_b = _make_site(session, "testcouncil", "Site B")
    app_a = _make_application(session, "testcouncil", "APP/A", site_id=site_a.id)
    app_b = _make_application(session, "testcouncil", "APP/B", site_id=site_b.id)
    _make_relationship(
        session, application_id=app_a.id, site_id=site_a.id, entity_name_raw="Shared Developer Ltd", role="DEVELOPER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_DEVELOPER",
    )
    _make_relationship(
        session, application_id=app_b.id, site_id=site_b.id, entity_name_raw="Shared Developer Ltd", role="DEVELOPER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_DEVELOPER",
    )
    session.commit()

    groups_a = get_site_control_intelligence(session, site_a.id)
    groups_b = get_site_control_intelligence(session, site_b.id)
    assert len(groups_a) == 1
    assert len(groups_b) == 1
    assert groups_a[0].application_references == ["APP/A"]
    assert groups_b[0].application_references == ["APP/B"]


def test_needs_confirmation_visible_within_a_group_even_when_grouped_with_confirmed(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app1 = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    app2 = _make_application(session, "testcouncil", "APP/2", site_id=site.id)
    _make_relationship(
        session, application_id=app1.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
        review_status="confirmed",
    )
    _make_relationship(
        session, application_id=app2.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
        review_status="needs_confirmation",
    )
    session.commit()

    [group] = get_site_control_intelligence(session, site.id)
    assert group.needs_review is True
    assert group.supporting_evidence_count == 2


# ---------------------------------------------------------------------------
# get_site_control_detail - shared fetch used by the Site Profile UI
# ---------------------------------------------------------------------------


def test_site_control_detail_returns_both_grouped_and_per_application(session):
    site = _make_site(session, "testcouncil", "1 Test Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_relationship(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Developments Ltd", role="OWNER",
        evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
    )
    session.commit()

    groups, by_application = get_site_control_detail(session, site.id)
    assert len(groups) == 1
    assert app.id in by_application
    assert len(by_application[app.id]) == 1


# ---------------------------------------------------------------------------
# Items 27/28 - no OpenAI / external API calls anywhere in this module
# ---------------------------------------------------------------------------


def test_reporting_module_makes_no_ai_or_external_calls():
    src = _read_source("app/reporting/ownership_control.py")
    lowered = src.lower()
    assert "openai" not in lowered
    assert "requests" not in lowered
    assert "companies_house" not in lowered
    assert "land_registry" not in lowered
