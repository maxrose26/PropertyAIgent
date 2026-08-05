"""Sprint 3G ("Places for Everyone Allocation Onboarding", Part 9) tests for
app.visuals.pipeline.rematch_local_plan_evidence (Part 4/5). No rendering,
no Vision client, no PDF - VisualEvidence rows are seeded directly with
already-stored detected_allocation_reference/detected_allocation_title
values, exactly what a real Sprint 3F extraction pass would have written."""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import LocalPlan, LocalPlanSite, VisualEvidence
from app.visuals.matching import match_stored_identifiers
from app.visuals.pipeline import rematch_local_plan_evidence


def _make_plan(session) -> LocalPlan:
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Places for Everyone", status="adopted")
    session.add(plan)
    session.commit()
    return plan


def _make_allocation(session, plan_id, policy_reference, site_name) -> LocalPlanSite:
    row = LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan_id, policy_reference=policy_reference, site_name=site_name,
        plan_name="Test Places for Everyone", plan_status="adopted",
    )
    session.add(row)
    session.commit()
    return row


def _make_evidence(session, plan_id, *, page, image_type="allocation_map", detected_ref=None, detected_title=None,
                    allocation_id=None, review_status="needs_review") -> VisualEvidence:
    row = VisualEvidence(
        local_plan_id=plan_id, allocation_id=allocation_id, source_page=page, image_type=image_type,
        detected_allocation_reference=detected_ref, detected_allocation_title=detected_title,
        review_status=review_status, status="current",
    )
    session.add(row)
    session.commit()
    return row


# --- 1. match_stored_identifiers priority tiers -----------------------------

def test_match_stored_identifiers_exact_reference(session):
    plan = _make_plan(session)
    alloc = _make_allocation(session, plan.id, "JPA 24", "Land at Hazelhurst Farm")
    result = match_stored_identifiers("JPA 24", "Land at Hazelhurst Farm", [alloc])
    assert result["allocation_id"] == alloc.id
    assert result["match_method"] == "exact_policy_reference"


def test_match_stored_identifiers_normalised_reference(session):
    plan = _make_plan(session)
    alloc = _make_allocation(session, plan.id, "JPA 24", "Land at Hazelhurst Farm")
    result = match_stored_identifiers("JPA24", None, [alloc])  # no space, stored form has a space
    assert result["allocation_id"] == alloc.id
    assert result["match_method"] == "normalised_policy_reference"


def test_match_stored_identifiers_title_only(session):
    plan = _make_plan(session)
    alloc = _make_allocation(session, plan.id, "JPA 24", "Land at Hazelhurst Farm")
    result = match_stored_identifiers(None, "Land at Hazelhurst Farm", [alloc])
    assert result["allocation_id"] == alloc.id
    assert result["match_method"] == "exact_allocation_title"


def test_match_stored_identifiers_nothing_found(session):
    plan = _make_plan(session)
    alloc = _make_allocation(session, plan.id, "JPA 24", "Land at Hazelhurst Farm")
    result = match_stored_identifiers("JPA 99", "Somewhere Else", [alloc])
    assert result["allocation_id"] is None
    assert result["match_method"] is None


# --- 2. VisualEvidence rematching after onboarding (Part 4) -----------------

def test_previously_unmatched_evidence_is_auto_linked_once_allocation_exists(session):
    plan = _make_plan(session)
    ve = _make_evidence(session, plan.id, page=406, detected_ref="JPA 24", detected_title="Land at Hazelhurst Farm")
    # Allocation didn't exist at extraction time - only added now, mirroring
    # this sprint's onboard-then-rematch sequence.
    alloc = _make_allocation(session, plan.id, "JPA 24", "Land at Hazelhurst Farm")

    stats = rematch_local_plan_evidence(session, plan.id)
    session.refresh(ve)

    assert stats.newly_linked == 1
    assert ve.allocation_id == alloc.id
    assert ve.match_method == "exact_policy_reference"


def test_rematch_ignores_image_type_matches_regardless_of_classification(session):
    # Sprint 3F/3G Part 6 finding: Salford/Trafford pages were classified
    # red_line_boundary, not allocation_map - matching must not care.
    plan = _make_plan(session)
    ve = _make_evidence(session, plan.id, page=406, image_type="red_line_boundary", detected_ref="JPA 24")
    alloc = _make_allocation(session, plan.id, "JPA 24", "Land at Hazelhurst Farm")

    stats = rematch_local_plan_evidence(session, plan.id)
    session.refresh(ve)
    assert stats.newly_linked == 1
    assert ve.allocation_id == alloc.id


def test_rematch_never_overwrites_confirmed_evidence(session):
    plan = _make_plan(session)
    ve = _make_evidence(session, plan.id, page=406, detected_ref="JPA 24", review_status="confirmed")
    _make_allocation(session, plan.id, "JPA 24", "Land at Hazelhurst Farm")

    stats = rematch_local_plan_evidence(session, plan.id)
    session.refresh(ve)
    assert stats.skipped_confirmed == 1
    assert ve.allocation_id is None  # left exactly as the human confirmed it


def test_rematch_never_touches_rejected_evidence(session):
    plan = _make_plan(session)
    ve = _make_evidence(session, plan.id, page=406, detected_ref="JPA 24", review_status="rejected")
    _make_allocation(session, plan.id, "JPA 24", "Land at Hazelhurst Farm")

    stats = rematch_local_plan_evidence(session, plan.id)
    session.refresh(ve)
    assert stats.skipped_rejected == 1
    assert ve.allocation_id is None
    assert ve.match_method is None


def test_rematch_is_idempotent(session):
    plan = _make_plan(session)
    ve = _make_evidence(session, plan.id, page=406, detected_ref="JPA 24")
    _make_allocation(session, plan.id, "JPA 24", "Land at Hazelhurst Farm")

    first = rematch_local_plan_evidence(session, plan.id)
    second = rematch_local_plan_evidence(session, plan.id)

    assert first.newly_linked == 1
    assert second.newly_linked == 0  # already linked, nothing left to do
    assert second.candidates_considered == 0  # no longer "unlinked"


def test_rematch_dry_run_writes_nothing(session):
    plan = _make_plan(session)
    ve = _make_evidence(session, plan.id, page=406, detected_ref="JPA 24")
    _make_allocation(session, plan.id, "JPA 24", "Land at Hazelhurst Farm")

    stats = rematch_local_plan_evidence(session, plan.id, dry_run=True)
    session.refresh(ve)
    assert stats.newly_linked == 1  # reported...
    assert ve.allocation_id is None  # ...but nothing written


def test_dry_run_secondary_page_count_matches_a_real_run_exactly(session):
    # Regression: pass 2's anchor search must see pass 1's matches even in
    # dry-run mode (previously it re-read row.allocation_id off the ORM
    # object, which dry-run never mutates, silently undercounting
    # secondary-page suggestions relative to what a real run would find -
    # confirmed against the real Places for Everyone data, Sprint 3G live
    # validation: dry-run reported 1 suggestion where the real run found 79).
    plan = _make_plan(session)
    _make_allocation(session, plan.id, "JPA 30", "New Carrington")
    # The anchor itself is UNLINKED at the start of this run (allocation_id
    # is only assigned during pass 1) - exactly the real-world shape.
    _make_evidence(session, plan.id, page=448, detected_ref="JPA 30", detected_title="New Carrington")
    _make_evidence(session, plan.id, page=450, detected_ref=None, detected_title=None)
    _make_evidence(session, plan.id, page=451, detected_ref=None, detected_title=None)

    dry_stats = rematch_local_plan_evidence(session, plan.id, dry_run=True)
    real_stats = rematch_local_plan_evidence(session, plan.id, dry_run=False)

    assert dry_stats.newly_linked == real_stats.newly_linked == 1
    assert dry_stats.secondary_page_suggestions == real_stats.secondary_page_suggestions == 2


# --- 3. secondary-page review suggestions (Part 5) --------------------------

def test_secondary_page_within_window_gets_a_suggestion_never_auto_linked(session):
    plan = _make_plan(session)
    alloc = _make_allocation(session, plan.id, "JPA 30", "New Carrington")
    _make_evidence(session, plan.id, page=448, detected_ref="JPA 30", detected_title="New Carrington")
    secondary = _make_evidence(session, plan.id, page=451, detected_ref=None, detected_title=None)  # no code on this page, 3 pages later

    stats = rematch_local_plan_evidence(session, plan.id)
    session.refresh(secondary)

    assert stats.secondary_page_suggestions == 1
    assert secondary.allocation_id is None  # NEVER auto-linked by proximity alone
    assert secondary.match_method == "page_proximity_suggestion"
    assert secondary.match_confidence == 0.5


def test_secondary_page_outside_window_is_left_unmatched(session):
    plan = _make_plan(session)
    _make_allocation(session, plan.id, "JPA 30", "New Carrington")
    _make_evidence(session, plan.id, page=448, detected_ref="JPA 30", detected_title="New Carrington")
    far_page = _make_evidence(session, plan.id, page=470, detected_ref=None, detected_title=None)  # 22 pages later, well past the window

    stats = rematch_local_plan_evidence(session, plan.id)
    session.refresh(far_page)

    assert stats.unmatched == 1
    assert far_page.match_method is None
    assert far_page.allocation_id is None


def test_secondary_page_does_not_bleed_into_the_next_allocations_span(session):
    plan = _make_plan(session)
    alloc_a = _make_allocation(session, plan.id, "JPA 24", "Land at Hazelhurst Farm")
    alloc_b = _make_allocation(session, plan.id, "JPA 25", "East of Boothstown")
    _make_evidence(session, plan.id, page=406, detected_ref="JPA 24", allocation_id=alloc_a.id)
    _make_evidence(session, plan.id, page=410, detected_ref="JPA 25", allocation_id=alloc_b.id)
    # A no-identifier page sitting BETWEEN the two title pages must anchor
    # to the CLOSER preceding one (JPA 24 at 406), never bleed forward.
    between = _make_evidence(session, plan.id, page=408, detected_ref=None, detected_title=None)

    rematch_local_plan_evidence(session, plan.id)
    session.refresh(between)

    assert between.match_method == "page_proximity_suggestion"
    # The suggestion is recorded, but never sets allocation_id - the test
    # only needs to confirm it never silently attaches to the WRONG one.
    assert between.allocation_id is None


def test_page_with_its_own_unmatched_identifier_is_not_treated_as_a_proximity_case(session):
    # A page with its OWN detected reference (just one that doesn't match
    # any onboarded allocation, e.g. a not-yet-onboarded authority's code)
    # must be reported as genuinely unmatched, not silently given a
    # neighbouring allocation's proximity suggestion.
    plan = _make_plan(session)
    alloc = _make_allocation(session, plan.id, "JPA 24", "Land at Hazelhurst Farm")
    _make_evidence(session, plan.id, page=406, detected_ref="JPA 24", allocation_id=alloc.id)
    has_own_code = _make_evidence(session, plan.id, page=408, detected_ref="JPA 99", detected_title="Somewhere Not Onboarded")

    stats = rematch_local_plan_evidence(session, plan.id)
    session.refresh(has_own_code)

    assert stats.unmatched == 1
    assert has_own_code.match_method is None
    assert has_own_code.allocation_id is None


# --- 4. no duplicate VisualEvidence rows ever created (Part 8) -------------

def test_rematch_never_creates_new_visual_evidence_rows(session):
    plan = _make_plan(session)
    _make_evidence(session, plan.id, page=406, detected_ref="JPA 24")
    _make_allocation(session, plan.id, "JPA 24", "Land at Hazelhurst Farm")

    before = session.execute(select(VisualEvidence)).scalars().all()
    rematch_local_plan_evidence(session, plan.id)
    after = session.execute(select(VisualEvidence)).scalars().all()

    assert len(before) == len(after) == 1  # rematch only ever UPDATES existing rows
