"""Stage 2E.1 ("Allocation<->Site Relationship Matcher Integrity Fix")
tests - covers the 33 items from the task's own Section 19. Every test
runs against the shared in-memory SQLite `session` fixture
(tests/conftest.py) - never the real production database, and never
mutates AllocationSiteRelationship in production (this whole task is
code-fix + read-only revalidation + cleanup-PLAN preparation only).
"""
from __future__ import annotations

import pathlib

from app.db.models import AllocationSiteRelationship, Application, Council, Document, LocalPlanSite, Site
from app.policy.allocation_document_evidence import (
    CONTRADICTORY_REFERENCE,
    EXPLICIT_REFERENCE,
    NAME_AND_POLICY_CONTEXT,
    STRONG_CONTEXTUAL_REFERENCE,
    WEAK_REFERENCE,
    find_document_evidence_for_allocation,
)
from app.policy.allocation_evidence_scan import _AUTO_CREATE_CATEGORIES, scan_council_for_allocation_evidence
from app.policy.allocation_site_relationships import (
    AllocationEvidenceResult,
    plan_document_evidence_relationships,
)
from app.policy.relationship_cleanup_plan import build_cleanup_plan, revalidate_before_write


# ---------------------------------------------------------------------------
# Fixtures (matching tests/test_allocation_document_evidence.py's own style)
# ---------------------------------------------------------------------------


def _make_council(session, code: str) -> None:
    if session.get(Council, code) is None:
        session.add(Council(code=code, name=code.title(), base_url="https://example.invalid",
                             date_field_mode="received", doc_system="idox"))


def _make_allocation(session, council_code: str, site_name: str, policy_reference: str | None, **kwargs) -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code=council_code, policy_reference=policy_reference, site_name=site_name,
        minimum_dwellings=kwargs.get("minimum_dwellings", 100), plan_name="Test Local Plan", plan_status="adopted",
    )
    session.add(allocation)
    session.flush()
    return allocation


def _make_application(session, council_code: str, reference: str, site_id: int | None = None) -> Application:
    app = Application(council_code=council_code, reference=reference, site_id=site_id)
    session.add(app)
    session.flush()
    return app


def _make_document(session, application_id: int, doc_type: str, text: str) -> Document:
    doc = Document(application_id=application_id, doc_type=doc_type, extracted_text=text, text_extracted=True)
    session.add(doc)
    session.flush()
    return doc


def _make_site(session, council_code: str, address: str) -> Site:
    site = Site(council_code=council_code, canonical_address=address, display_address=address)
    session.add(site)
    session.flush()
    return site


def _make_relationship(
    session, *, allocation_id: int, site_id: int, evidence_basis: str = "document_confirmed_site",
    evidence_category: str | None = None, review_status: str = "auto_applied",
) -> AllocationSiteRelationship:
    rel = AllocationSiteRelationship(
        allocation_id=allocation_id, site_id=site_id, evidence_basis=evidence_basis,
        evidence_category=evidence_category, review_status=review_status,
    )
    session.add(rel)
    session.flush()
    return rel


def _best_category(positive_hits, site_id):
    order = {WEAK_REFERENCE: 0, NAME_AND_POLICY_CONTEXT: 1, STRONG_CONTEXTUAL_REFERENCE: 2, EXPLICIT_REFERENCE: 3}
    site_hits = [h for h in positive_hits if h.site_id == site_id]
    if not site_hits:
        return None
    return max(site_hits, key=lambda h: order.get(h.category, 0)).category


def _read_source(relative_path: str) -> str:
    return (pathlib.Path(__file__).resolve().parents[1] / relative_path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Items 1/2/3 - bare generic reference(s) never establish membership
# ---------------------------------------------------------------------------


def test_bare_h3_generic_reference_does_not_establish_membership(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "35 - 45 King Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "design_access",
                    "4.10 policy h3 confirms that development across the plan area should seek to incorporate a range of dwelling types.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)
    assert _best_category(positive, site.id) == WEAK_REFERENCE


def test_bare_h4_generic_reference_does_not_establish_membership(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "South Hindley", "H4")
    site = _make_site(session, "testcouncil", "35 - 45 King Street")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "design_access",
                    "4.11 policy h4 indicates that new housing development should be delivered at a density.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)
    assert _best_category(positive, site.id) == WEAK_REFERENCE


def test_generic_policy_list_does_not_establish_membership(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "Land South Of Rectory Lane")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "planning_statement",
                    "policy h3 - accessibility to sustainable transport/bus routes. policy h4 - affordable housing provision.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)
    assert _best_category(positive, site.id) == WEAK_REFERENCE


# ---------------------------------------------------------------------------
# Items 4/5 - allocation name corroboration restores membership evidence
# ---------------------------------------------------------------------------


def test_allocation_name_plus_h3_establishes_membership(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "North Leigh Development Site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "planning_statement",
                    "north leigh park : planning statement. background 1.2 north leigh park is the only strategic allocation h3 in the adopted core strategy.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)
    assert _best_category(positive, site.id) in (STRONG_CONTEXTUAL_REFERENCE, EXPLICIT_REFERENCE)


def test_explicit_forms_part_of_named_allocation_h3_is_explicit(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "North Leigh Park", "H3")
    site = _make_site(session, "testcouncil", "North Leigh Development Site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "planning_statement",
                    "The application site forms part of allocation H3, North Leigh Park, and is allocated for residential development.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)
    assert _best_category(positive, site.id) == EXPLICIT_REFERENCE


# ---------------------------------------------------------------------------
# Item 6 - unique/distinctive references remain unaffected (no over-correction)
# ---------------------------------------------------------------------------


def test_distinctive_non_generic_reference_still_supported_without_name(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "New Carrington", "JPA 30")
    site = _make_site(session, "testcouncil", "Land West Of Warburton Lane")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "planning_statement",
                    "the emerging jpa 30 allocation is a large strategic site with significant infrastructure needs.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)
    # No allocation-name corroboration present anywhere, yet this is a
    # NON-generic reference (>4 alphanumeric chars) - unaffected by the fix.
    assert _best_category(positive, site.id) == STRONG_CONTEXTUAL_REFERENCE


# ---------------------------------------------------------------------------
# Item 7 - negative/adjacent language still overrides
# ---------------------------------------------------------------------------


def test_negative_adjacent_language_still_overrides(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "Beal Valley", "JPA 10")
    site = _make_site(session, "testcouncil", "Land South Of Bullcote Lane")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "planning_statement",
                    "the application site is adjacent to the allocation (jpa 10) and lies outside the allocation boundary.")
    session.commit()

    positive, contradictory = find_document_evidence_for_allocation(session, allocation)
    assert any(h.category == CONTRADICTORY_REFERENCE and h.site_id == site.id for h in contradictory)


# ---------------------------------------------------------------------------
# Items 8/9 - multi-allocation collision guard
# ---------------------------------------------------------------------------


def _fake_evidence_result(allocation_id, council, policy_reference, allocation_name, positive_hits):
    from app.policy.allocation_document_evidence import DOCUMENT_CONFIRMED_SITE
    result = AllocationEvidenceResult(
        allocation_id=allocation_id, council=council, policy_reference=policy_reference,
        allocation_name=allocation_name, stage2a_classification="NO_CANDIDATE", stage2a_candidate_site_ids=[],
        positive_hits=positive_hits, contradictory_hits=[],
    )
    result.recommended_outcome = DOCUMENT_CONFIRMED_SITE
    return result


class _Hit:
    def __init__(self, site_id, category, document_id=1, application_id=1, application_reference="APP/1", snippet="snip", weight=1):
        self.site_id = site_id
        self.category = category
        self.document_id = document_id
        self.application_id = application_id
        self.application_reference = application_reference
        self.snippet = snippet
        self.weight = weight


def test_ambiguous_strong_contextual_collision_cannot_auto_create(session):
    """Item 8 - one Site independently matching several allocations, with
    ONLY STRONG_CONTEXTUAL_REFERENCE (never EXPLICIT_REFERENCE) for either,
    must never auto-create both - each is downgraded to needs_confirmation."""
    site_id = 999
    result_a = _fake_evidence_result(1, "testcouncil", "H3", "North Leigh Park", [_Hit(site_id, STRONG_CONTEXTUAL_REFERENCE)])
    result_b = _fake_evidence_result(2, "testcouncil", "H4", "South Hindley", [_Hit(site_id, STRONG_CONTEXTUAL_REFERENCE)])

    planned, _ = plan_document_evidence_relationships([result_a, result_b])
    statuses = {p.allocation_id: p.review_status for p in planned}
    assert statuses[1] == "needs_confirmation"
    assert statuses[2] == "needs_confirmation"


def test_independently_evidenced_multi_allocation_case_not_prohibited(session):
    """Item 9 - a Site with its OWN EXPLICIT_REFERENCE evidence for each of
    two allocations is a legitimate multi-allocation relationship, never
    blocked by the collision guard."""
    site_id = 999
    result_a = _fake_evidence_result(1, "testcouncil", "JPA 5", "Chequerbent North", [_Hit(site_id, EXPLICIT_REFERENCE)])
    result_b = _fake_evidence_result(2, "testcouncil", "JPA 6", "Adjoining Strategic Site", [_Hit(site_id, EXPLICIT_REFERENCE)])

    planned, _ = plan_document_evidence_relationships([result_a, result_b])
    statuses = {p.allocation_id: p.review_status for p in planned}
    assert statuses[1] == "auto_applied"
    assert statuses[2] == "auto_applied"


# ---------------------------------------------------------------------------
# Items 10/11 - Stage 3B forward-scan threshold unchanged
# ---------------------------------------------------------------------------


def test_stage_3b_auto_create_threshold_still_explicit_reference_only():
    assert _AUTO_CREATE_CATEGORIES == (EXPLICIT_REFERENCE,)


def test_strong_contextual_reference_remains_review_only_in_forward_scan(session):
    _make_council(session, "testcouncil")
    allocation = _make_allocation(session, "testcouncil", "New Carrington", "JPA 30")
    site = _make_site(session, "testcouncil", "Land West Of Warburton Lane")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    _make_document(session, app.id, "planning_statement",
                    "the emerging jpa 30 allocation is a large strategic site with significant infrastructure needs.")
    session.commit()

    report = scan_council_for_allocation_evidence(session, "testcouncil")
    assert report.new_strong_candidates == []
    assert any(w.site_id == site.id and w.category == STRONG_CONTEXTUAL_REFERENCE for w in report.weak_evidence)


# ---------------------------------------------------------------------------
# Items 12-17 - mandatory Wigan false-positive regressions
# ---------------------------------------------------------------------------


def test_king_street_h3_regression(session):
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "North Leigh Park", "H3", minimum_dwellings=1400)
    site = _make_site(session, "wigan", "35 - 45 King Street Wigan WN1 1DY")
    app = _make_application(session, "wigan", "A/26/100631/MAJOR", site_id=site.id)
    _make_document(session, app.id, "design_access",
                    "4.10 policy h3 confirms that development across the plan area should seek to incorporate a range of dwelling types and sizes.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)
    assert _best_category(positive, site.id) != EXPLICIT_REFERENCE
    assert _best_category(positive, site.id) != STRONG_CONTEXTUAL_REFERENCE


def test_king_street_h4_regression(session):
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "South Hindley", "H4")
    site = _make_site(session, "wigan", "35 - 45 King Street Wigan WN1 1DY")
    app = _make_application(session, "wigan", "A/26/100631/MAJOR", site_id=site.id)
    _make_document(session, app.id, "design_access",
                    "4.11 policy h4 indicates that new housing development should be delivered at a density appropriate to the location.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)
    assert _best_category(positive, site.id) != EXPLICIT_REFERENCE
    assert _best_category(positive, site.id) != STRONG_CONTEXTUAL_REFERENCE


def test_rectory_lane_h3_regression(session):
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "North Leigh Park", "H3", minimum_dwellings=1400)
    site = _make_site(session, "wigan", "Land South Of Rectory Lane Standish")
    app = _make_application(session, "wigan", "A/26/100539/MAJOR", site_id=site.id)
    _make_document(session, app.id, "viability_affordable_housing",
                    "policy h2: new developments to meet local housing need. policy h3: accessibility to sustainable transport/bus routes.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)
    assert _best_category(positive, site.id) not in (EXPLICIT_REFERENCE, STRONG_CONTEXTUAL_REFERENCE)


def test_rectory_lane_h4_regression(session):
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "South Hindley", "H4")
    site = _make_site(session, "wigan", "Land South Of Rectory Lane Standish")
    app = _make_application(session, "wigan", "A/26/100539/MAJOR", site_id=site.id)
    _make_document(session, app.id, "viability_affordable_housing",
                    "policy h4: affordable housing provision in standish. policy h6: major housing developments.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)
    assert _best_category(positive, site.id) not in (EXPLICIT_REFERENCE, STRONG_CONTEXTUAL_REFERENCE)


def test_rectory_lane_h5_regression(session):
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "Remaining land South of Atherton", "H5")
    site = _make_site(session, "wigan", "Land South Of Rectory Lane Standish")
    app = _make_application(session, "wigan", "A/26/100539/MAJOR", site_id=site.id)
    _make_document(session, app.id, "viability_affordable_housing",
                    "those allocations listed in policy h5 are built-out and are no longer adequate for addressing identified future requirements.")
    session.commit()

    positive, contradictory = find_document_evidence_for_allocation(session, allocation)
    assert _best_category(positive, site.id) not in (EXPLICIT_REFERENCE, STRONG_CONTEXTUAL_REFERENCE)


def test_rectory_lane_h6_regression(session):
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "East of Atherton", "H6")
    site = _make_site(session, "wigan", "Land South Of Rectory Lane Standish")
    app = _make_application(session, "wigan", "A/26/100539/MAJOR", site_id=site.id)
    _make_document(session, app.id, "viability_affordable_housing",
                    "policy h6: major housing developments to provide air quality assessment and mitigation measures.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)
    assert _best_category(positive, site.id) not in (EXPLICIT_REFERENCE, STRONG_CONTEXTUAL_REFERENCE)


# ---------------------------------------------------------------------------
# Items 18-22 - genuine relationships survive
# ---------------------------------------------------------------------------


def test_genuine_north_leigh_park_relationship_survives(session):
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "North Leigh Park", "H3", minimum_dwellings=1400)
    site = _make_site(session, "wigan", "North Leigh Development Site")
    app = _make_application(session, "wigan", "A/26/100520/RMMAJ", site_id=site.id)
    _make_document(session, app.id, "planning_statement",
                    "north leigh park : planning statement. background 1.2 north leigh park is the only strategic "
                    "allocation h3 in the adopted core strategy.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)
    assert _best_category(positive, site.id) in (EXPLICIT_REFERENCE, STRONG_CONTEXTUAL_REFERENCE)


def test_north_of_mosley_common_survives(session):
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "North of Mosley Common", "JPA 32", minimum_dwellings=1100)
    site = _make_site(session, "wigan", "Land North Of Mosley Common")
    app = _make_application(session, "wigan", "A/25/099409/RMMAJ", site_id=site.id)
    _make_document(session, app.id, "planning_statement",
                    "allocated for residential development in the places for everyone joint plan for greater manchester (pfe policy jpa 32).")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)
    assert _best_category(positive, site.id) == EXPLICIT_REFERENCE


def test_genuine_east_of_atherton_survives_despite_distant_name_mention(session):
    """Item 20 - the real production case: an officer report names 'East
    of Atherton' repeatedly throughout, but the ONE bare 'policy h6'
    phrasing is far (>180 chars) from the nearest name mention. Same-
    document (not narrow-window) corroboration must still recognise this
    as genuine evidence."""
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "East of Atherton", "H6")
    site = _make_site(session, "wigan", "Land At Douglas Road Atherton")
    app = _make_application(session, "wigan", "A/25/098899/MAJOR", site_id=site.id)
    filler = "x" * 400
    text = (
        "the council's site allocation, 'east of atherton', is a well-established location for growth. "
        f"{filler} "
        "it is important to acknowledge the continuation of the allocation, under emerging policy h6, "
        "which proposes to increase the number of houses to be delivered."
    )
    _make_document(session, app.id, "officer_report", text)
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)
    assert _best_category(positive, site.id) in (EXPLICIT_REFERENCE, STRONG_CONTEXTUAL_REFERENCE)


def test_new_carrington_survives(session):
    _make_council(session, "trafford")
    allocation = _make_allocation(session, "trafford", "New Carrington", "JPA 30")
    site = _make_site(session, "trafford", "Land West Of Warburton Lane")
    app = _make_application(session, "trafford", "115154/FUL/24", site_id=site.id)
    _make_document(session, app.id, "planning_statement",
                    "the site is allocated for development under the strategic places for everyone (pfe) plan - new carrington allocation (jpa 30).")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)
    assert _best_category(positive, site.id) == EXPLICIT_REFERENCE


def test_south_of_hyde_survives(session):
    _make_council(session, "tameside")
    allocation = _make_allocation(session, "tameside", "South of Hyde", "JPA 29")
    site = _make_site(session, "tameside", "Land South Of Hyde")
    app = _make_application(session, "tameside", "25/00173/OUT", site_id=site.id)
    _make_document(session, app.id, "planning_statement",
                    "it is clear that the principle of residential development on land south of hyde conforms with policy jpa 29 and its requirements.")
    session.commit()

    positive, _ = find_document_evidence_for_allocation(session, allocation)
    assert _best_category(positive, site.id) in (EXPLICIT_REFERENCE, STRONG_CONTEXTUAL_REFERENCE)


# ---------------------------------------------------------------------------
# Item 23 - legacy relationships not silently upgraded
# ---------------------------------------------------------------------------


def test_legacy_relationship_not_silently_upgraded(session):
    _make_council(session, "stockport")
    allocation = _make_allocation(session, "stockport", "High Lane", "HOM 2.16")
    site = _make_site(session, "stockport", "Land East Of Windlehurst Road High Lane Stockport")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, evidence_basis="legacy_matched_site_id_backfill", evidence_category=None)
    session.commit()

    plan = build_cleanup_plan(session)
    needs_confirmation_pairs = {(t.allocation_id, t.site_id) for t in plan.needs_confirmation_candidates}
    reject_pairs = {(t.allocation_id, t.site_id) for t in plan.reject_candidates}
    unchanged_pairs = {(t.allocation_id, t.site_id) for t in plan.unchanged}
    assert (allocation.id, site.id) in needs_confirmation_pairs
    assert (allocation.id, site.id) not in reject_pairs
    assert (allocation.id, site.id) not in unchanged_pairs


# ---------------------------------------------------------------------------
# Items 24-27 - cleanup plan mechanics
# ---------------------------------------------------------------------------


def test_cleanup_plan_uses_semantic_identifiers_not_hardcoded_row_ids(session):
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "North Leigh Park", "H3", minimum_dwellings=1400)
    site = _make_site(session, "wigan", "35 - 45 King Street Wigan WN1 1DY")
    app = _make_application(session, "wigan", "A/26/100631/MAJOR", site_id=site.id)
    _make_document(session, app.id, "design_access", "4.10 policy h3 confirms that development across the plan area should seek to incorporate a range of dwelling types.")
    rel = _make_relationship(session, allocation_id=allocation.id, site_id=site.id, evidence_category=STRONG_CONTEXTUAL_REFERENCE)
    session.commit()

    plan = build_cleanup_plan(session, confirmed_false_positive_pairs={(allocation.id, site.id)})
    assert len(plan.reject_candidates) == 1
    target = plan.reject_candidates[0]
    assert target.allocation_id == allocation.id
    assert target.site_id == site.id
    # The relationship_id is carried for traceability only, never the
    # lookup key a future write would use.
    assert target.relationship_id == rel.id


def test_cleanup_plan_revalidation_reject_still_valid(session):
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "North Leigh Park", "H3", minimum_dwellings=1400)
    site = _make_site(session, "wigan", "35 - 45 King Street Wigan WN1 1DY")
    app = _make_application(session, "wigan", "A/26/100631/MAJOR", site_id=site.id)
    _make_document(session, app.id, "design_access", "4.10 policy h3 confirms that development across the plan area should seek to incorporate a range of dwelling types.")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, evidence_category=STRONG_CONTEXTUAL_REFERENCE)
    session.commit()

    result = revalidate_before_write(session, allocation.id, site.id, expected_action="reject")
    assert result.still_matches_plan is True


def test_cleanup_plan_revalidation_reject_no_longer_valid_when_new_evidence_appears(session):
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "North Leigh Park", "H3", minimum_dwellings=1400)
    site = _make_site(session, "wigan", "North Leigh Development Site")
    app = _make_application(session, "wigan", "A/26/100520/RMMAJ", site_id=site.id)
    _make_document(session, app.id, "planning_statement",
                    "north leigh park : planning statement. north leigh park is the only strategic allocation h3 in the area.")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, evidence_category=WEAK_REFERENCE)
    session.commit()

    result = revalidate_before_write(session, allocation.id, site.id, expected_action="reject")
    assert result.still_matches_plan is False


def test_cleanup_plan_revalidation_already_confirmed_never_overwritten(session):
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "North Leigh Park", "H3", minimum_dwellings=1400)
    site = _make_site(session, "wigan", "35 - 45 King Street")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="confirmed")
    session.commit()

    result = revalidate_before_write(session, allocation.id, site.id, expected_action="reject")
    assert result.still_matches_plan is False
    assert result.current_review_status == "confirmed"


def test_cleanup_plan_revalidation_missing_relationship(session):
    result = revalidate_before_write(session, 99999, 99999, expected_action="reject")
    assert result.relationship_exists is False
    assert result.still_matches_plan is False


def test_cleanup_plan_is_idempotent(session):
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "North Leigh Park", "H3", minimum_dwellings=1400)
    site = _make_site(session, "wigan", "35 - 45 King Street Wigan WN1 1DY")
    app = _make_application(session, "wigan", "A/26/100631/MAJOR", site_id=site.id)
    _make_document(session, app.id, "design_access", "4.10 policy h3 confirms that development across the plan area should seek to incorporate a range of dwelling types.")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, evidence_category=STRONG_CONTEXTUAL_REFERENCE)
    session.commit()

    plan1 = build_cleanup_plan(session, confirmed_false_positive_pairs={(allocation.id, site.id)})
    plan2 = build_cleanup_plan(session, confirmed_false_positive_pairs={(allocation.id, site.id)})
    pairs1 = {(t.allocation_id, t.site_id) for t in plan1.reject_candidates}
    pairs2 = {(t.allocation_id, t.site_id) for t in plan2.reject_candidates}
    assert pairs1 == pairs2 == {(allocation.id, site.id)}


def test_cleanup_plan_marks_rejected_never_deletes():
    """Item 27 - structural check: the cleanup-plan module never deletes
    anything, and its own targets represent a review_status change, not a
    row deletion."""
    src = _read_source("app/policy/relationship_cleanup_plan.py")
    assert "session.delete" not in src
    assert ".delete(" not in src


# ---------------------------------------------------------------------------
# Items 28/29 - rejected relationships excluded from coverage/ownership
# ---------------------------------------------------------------------------


def test_rejected_relationship_excluded_from_coverage(session):
    from app.reporting.allocation_development_coverage import compute_development_coverage, summarise_site_activity

    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "South Hindley", "H4", minimum_dwellings=2000)
    site = _make_site(session, "wigan", "35 - 45 King Street")
    app = _make_application(session, "wigan", "A/26/100631/MAJOR", site_id=site.id)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="rejected")
    session.commit()

    # The SAME filter Stage 3A's own coverage caller applies in production
    # (review_status != "rejected") - a rejected relationship contributes
    # no SiteActivitySummary, so coverage sees zero related Sites.
    coverage = compute_development_coverage(allocation, [])
    assert coverage.number_of_related_sites == 0
    assert coverage.capacity_accounting_status == "no_activity"


def test_no_ai_or_external_calls_in_matcher_fix_modules():
    """Item 33 - the deterministic matcher fix and cleanup-plan preparation
    are 100% deterministic; AI availability (or its absence, as in Stage
    2E's own 401 finding) can never change their behaviour, because they
    never call AI in the first place."""
    for path in (
        "app/policy/allocation_document_evidence.py",
        "app/policy/allocation_site_relationships.py",
        "app/policy/allocation_evidence_scan.py",
        "app/policy/relationship_cleanup_plan.py",
    ):
        lowered = _read_source(path).lower()
        assert "import openai" not in lowered
        assert "from openai" not in lowered


def test_no_production_writes_in_cleanup_plan_module():
    """Item 31 - build_cleanup_plan/revalidate_before_write never write."""
    src = _read_source("app/policy/relationship_cleanup_plan.py")
    assert "session.add(" not in src
    assert "session.commit(" not in src
    assert "review_status =" not in src


def test_control_relationship_never_referenced_by_matcher_fix():
    """Item 30 - the matcher fix and cleanup plan never touch
    ControlRelationship (ownership/control evidence) at all."""
    for path in (
        "app/policy/allocation_document_evidence.py",
        "app/policy/allocation_site_relationships.py",
        "app/policy/relationship_cleanup_plan.py",
    ):
        assert "ControlRelationship" not in _read_source(path)
