"""Tests for feature/allocation-image-discovery-ui: the Local Plan Sites
"Allocation detail" selector fix.

Root cause being tested: the selector previously defaulted (Streamlit's
own index=0 behaviour) to the first LocalPlanSite an UNORDERED SQL SELECT
happened to return - reliably an allocation with no image, silently
burying the one allocation that actually had a confirmed map. These
tests cover the pure ordering/labelling/filtering/coverage logic
(app.ui.allocation_selector) plus the batched image-status lookup
(app.visuals.site_view.build_allocation_image_status) that the fix is
built on - no Streamlit runtime involved, matching this codebase's
existing convention (see tests/test_site_headline.py) of unit-testing
the pure helpers a page delegates to rather than the page script itself.
"""
from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import event

from app.db.models import LocalPlanSite, VisualEvidence
from app.ui.allocation_selector import (
    FILTER_ALL,
    FILTER_CHOICES,
    coverage_message,
    filter_allocations_by_image_status,
    format_allocation_option,
    sort_allocations,
)
from app.visuals.site_view import build_allocation_image_status, build_allocation_visual_evidence


def _alloc(id, council_code, policy_reference, site_name):
    return SimpleNamespace(id=id, council_code=council_code, policy_reference=policy_reference, site_name=site_name)


def _make_local_plan(session, council_code="testcouncil"):
    from app.db.models import LocalPlan

    plan = LocalPlan(council_code=council_code, plan_name="Test Local Plan", status="adopted", raw_status="Adopted")
    session.add(plan)
    session.commit()
    return plan


def _make_allocation(session, local_plan_id, council_code="testcouncil", policy_reference="HOM 1.1", site_name="Land off Test Road"):
    allocation = LocalPlanSite(
        council_code=council_code, local_plan_id=local_plan_id, policy_reference=policy_reference, site_name=site_name,
        plan_name="Test Local Plan", plan_status="adopted",
    )
    session.add(allocation)
    session.commit()
    return allocation


# --- 1. deterministic allocation ordering -----------------------------

def test_sort_allocations_orders_by_council_name_then_reference_then_name_then_id():
    council_names = {"bury": "Bury Metropolitan Borough Council", "stockport": "Stockport Metropolitan Borough Council"}
    stockport_first = _alloc(1, "stockport", "HOM 2.1", "John Street, Hazel Grove")
    bury_ref_1 = _alloc(38, "bury", "JPA1.1", "Northern Gateway")
    bury_ref_2 = _alloc(39, "bury", "JPA1.2", "Northern Gateway")
    bury_no_ref = _alloc(40, "bury", None, "Seedfield")

    ordered = sort_allocations([stockport_first, bury_no_ref, bury_ref_2, bury_ref_1], council_names)

    # Bury (alphabetically before Stockport) comes first; within Bury,
    # allocations WITH a reference sort before the one without; among the
    # two with a reference, JPA1.1 sorts before JPA1.2.
    assert [a.id for a in ordered] == [38, 39, 40, 1]


def test_sort_allocations_is_stable_and_deterministic_across_repeated_calls():
    council_names = {"testcouncil": "Test Council"}
    allocations = [_alloc(i, "testcouncil", "HOM 1.1", "Same Name") for i in [5, 3, 4, 1, 2]]
    first_run = [a.id for a in sort_allocations(allocations, council_names)]
    second_run = [a.id for a in sort_allocations(allocations, council_names)]
    # Identical reference/name across every row - id is the only thing
    # left to break the tie, and it must do so identically every time.
    assert first_run == second_run == [1, 2, 3, 4, 5]


def test_sort_allocations_falls_back_to_council_code_when_name_unknown():
    # No council_names entry for "unknowncouncil" - must not raise, and
    # must still produce a deterministic order using the raw code.
    a = _alloc(1, "unknowncouncil", "REF", "Name")
    ordered = sort_allocations([a], {})
    assert ordered == [a]


# --- 2. placeholder / no-selection state --------------------------------

def test_filter_can_return_an_empty_list_which_is_what_the_placeholder_state_needs():
    # When a filter matches nothing, st.selectbox(options=[], index=None,
    # placeholder=...) must be handed an empty list without error - this
    # is the exact input state the placeholder path exists to handle.
    allocations = [_alloc(1, "testcouncil", "HOM 1.1", "Only Allocation")]
    result = filter_allocations_by_image_status(allocations, {1: "none"}, "Allocations with confirmed maps")
    assert result == []


def test_sort_allocations_handles_an_empty_list():
    assert sort_allocations([], {}) == []


# --- 3/4. option labelling for allocations with and without an image ----

def test_format_allocation_option_with_confirmed_image():
    allocation = _alloc(38, "bury", "JPA1.1", "Northern Gateway")
    assert format_allocation_option(allocation, "confirmed") == "Northern Gateway — JPA1.1 — Map available"


def test_format_allocation_option_with_no_image():
    allocation = _alloc(1, "stockport", "HOM 2.1", "John Street, Hazel Grove")
    assert format_allocation_option(allocation, "none") == "John Street, Hazel Grove — HOM 2.1 — No confirmed map"


def test_format_allocation_option_awaiting_review():
    allocation = _alloc(39, "bury", "JPA1.2", "Northern Gateway")
    assert format_allocation_option(allocation, "needs_review") == "Northern Gateway — JPA1.2 — Awaiting review"


def test_format_allocation_option_handles_missing_reference():
    allocation = _alloc(40, "bury", None, "Seedfield")
    assert format_allocation_option(allocation, "none") == "Seedfield — (no ref) — No confirmed map"


# --- 5. batched availability lookup (one query, not one per allocation) -

def test_build_allocation_image_status_returns_correct_status_per_allocation(session):
    plan = _make_local_plan(session)
    confirmed_alloc = _make_allocation(session, plan.id, policy_reference="REF-CONFIRMED")
    review_alloc = _make_allocation(session, plan.id, policy_reference="REF-REVIEW")
    empty_alloc = _make_allocation(session, plan.id, policy_reference="REF-EMPTY")

    session.add(VisualEvidence(
        allocation_id=confirmed_alloc.id, source_page=1, image_type="allocation_map",
        review_status="confirmed", status="current",
    ))
    session.add(VisualEvidence(
        allocation_id=review_alloc.id, source_page=1, image_type="allocation_map",
        review_status="needs_review", status="current",
    ))
    session.commit()

    result = build_allocation_image_status(session, [confirmed_alloc.id, review_alloc.id, empty_alloc.id])

    assert result == {confirmed_alloc.id: "confirmed", review_alloc.id: "needs_review", empty_alloc.id: "none"}


def test_build_allocation_image_status_ignores_rejected_and_superseded_rows(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    session.add(VisualEvidence(
        allocation_id=allocation.id, source_page=1, image_type="allocation_map",
        review_status="rejected", status="current",
    ))
    session.add(VisualEvidence(
        allocation_id=allocation.id, source_page=2, image_type="allocation_map",
        review_status="confirmed", status="superseded",
    ))
    session.commit()

    result = build_allocation_image_status(session, [allocation.id])
    assert result == {allocation.id: "none"}


def test_build_allocation_image_status_prefers_confirmed_over_needs_review_for_the_same_allocation(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id)
    session.add(VisualEvidence(
        allocation_id=allocation.id, source_page=1, image_type="allocation_map",
        review_status="needs_review", status="current",
    ))
    session.add(VisualEvidence(
        allocation_id=allocation.id, source_page=2, image_type="allocation_map",
        review_status="confirmed", status="current",
    ))
    session.commit()

    result = build_allocation_image_status(session, [allocation.id])
    assert result == {allocation.id: "confirmed"}


def test_build_allocation_image_status_empty_input_returns_empty_dict_without_querying(session):
    assert build_allocation_image_status(session, []) == {}


def test_build_allocation_image_status_issues_exactly_one_query_regardless_of_allocation_count(session):
    plan = _make_local_plan(session)
    allocations = [_make_allocation(session, plan.id, policy_reference=f"REF-{i}") for i in range(8)]

    engine = session.get_bind()
    statements = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        build_allocation_image_status(session, [a.id for a in allocations])
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    assert len(statements) == 1


# --- 6. coverage message -------------------------------------------------

def test_coverage_message_singular_confirmed():
    allocations = [_alloc(1, "c", "R1", "A"), _alloc(2, "c", "R2", "B")]
    message = coverage_message(allocations, {1: "confirmed", 2: "none"})
    assert message == "1 of 2 allocations currently has a confirmed map image."


def test_coverage_message_plural_confirmed():
    allocations = [_alloc(i, "c", f"R{i}", "A") for i in range(1, 4)]
    message = coverage_message(allocations, {1: "confirmed", 2: "confirmed", 3: "none"})
    assert message == "2 of 3 allocations currently have a confirmed map image."


def test_coverage_message_zero_confirmed():
    allocations = [_alloc(1, "c", "R1", "A")]
    message = coverage_message(allocations, {1: "none"})
    assert message == "0 of 1 allocation currently have a confirmed map image."


# --- 7. filtering by image status ----------------------------------------

def test_filter_all_allocations_is_a_no_op():
    allocations = [_alloc(1, "c", "R1", "A"), _alloc(2, "c", "R2", "B")]
    result = filter_allocations_by_image_status(allocations, {1: "confirmed", 2: "none"}, FILTER_ALL)
    assert result == allocations


def test_filter_confirmed_only():
    allocations = [_alloc(1, "c", "R1", "A"), _alloc(2, "c", "R2", "B"), _alloc(3, "c", "R3", "C")]
    status = {1: "confirmed", 2: "needs_review", 3: "none"}
    result = filter_allocations_by_image_status(allocations, status, "Allocations with confirmed maps")
    assert [a.id for a in result] == [1]


def test_filter_awaiting_review_only():
    allocations = [_alloc(1, "c", "R1", "A"), _alloc(2, "c", "R2", "B"), _alloc(3, "c", "R3", "C")]
    status = {1: "confirmed", 2: "needs_review", 3: "none"}
    result = filter_allocations_by_image_status(allocations, status, "Allocations awaiting visual review")
    assert [a.id for a in result] == [2]


def test_filter_no_visual_evidence_only():
    allocations = [_alloc(1, "c", "R1", "A"), _alloc(2, "c", "R2", "B"), _alloc(3, "c", "R3", "C")]
    status = {1: "confirmed", 2: "needs_review", 3: "none"}
    result = filter_allocations_by_image_status(allocations, status, "Allocations with no visual evidence")
    assert [a.id for a in result] == [3]


def test_all_filter_choices_are_handled():
    # Every declared choice must be a recognised filter (either the no-op
    # FILTER_ALL or a real status key) - a typo in FILTER_CHOICES silently
    # falling through to "no-op" would be a real, easy-to-miss bug.
    allocations = [_alloc(1, "c", "R1", "A")]
    status = {1: "confirmed"}
    for choice in FILTER_CHOICES:
        filter_allocations_by_image_status(allocations, status, choice)  # must not raise


# --- 8. selecting Northern Gateway returns the confirmed image ----------

def test_selecting_the_allocation_with_a_confirmed_image_returns_it(session):
    plan = _make_local_plan(session, council_code="bury")
    no_image_alloc = _make_allocation(session, plan.id, council_code="bury", policy_reference="HOM 2.1", site_name="John Street, Hazel Grove")
    northern_gateway = _make_allocation(session, plan.id, council_code="bury", policy_reference="JPA1.1", site_name="Northern Gateway")

    confirmed_image = VisualEvidence(
        allocation_id=northern_gateway.id, source_page=260, image_type="allocation_map",
        review_status="confirmed", status="current", is_primary=True,
    )
    session.add(confirmed_image)
    session.commit()

    # The ordering/labelling step a real page run would perform first -
    # confirms Northern Gateway is both correctly labelled AND that
    # selecting it (by id, exactly what the selectbox hands back) resolves
    # to the confirmed image, not the no-image allocation sorted elsewhere
    # in the list.
    council_names = {"bury": "Bury Metropolitan Borough Council"}
    ordered = sort_allocations([no_image_alloc, northern_gateway], council_names)
    image_status = build_allocation_image_status(session, [a.id for a in ordered])
    assert image_status[northern_gateway.id] == "confirmed"
    assert format_allocation_option(northern_gateway, image_status[northern_gateway.id]) == "Northern Gateway — JPA1.1 — Map available"

    evidence = build_allocation_visual_evidence(session, northern_gateway.id)
    assert evidence["primary"] is not None
    assert evidence["primary"].id == confirmed_image.id
    assert evidence["primary"].review_status == "confirmed"
