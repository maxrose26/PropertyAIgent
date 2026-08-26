"""Tests for Site Selection & Reporting V1 Gate 1's shortlist foundation
(app.ui.shortlist) - pure dict-in/dict-out functions, no Streamlit runtime
involved, matching this codebase's existing convention (see
tests/test_allocation_selector.py) of unit-testing the pure helpers a page
delegates to rather than the page script itself.

Page-level behaviour (shortlist surviving a Streamlit rerun/pagination/
navigation, the review page showing only shortlisted allocations, a stale
candidate rendering as "unavailable" rather than crashing) is not covered
by an automated UI test here - this codebase has no existing
streamlit.testing.v1.AppTest (or similar) harness for page scripts, and
inventing one is out of Gate 1's scope. That behaviour follows directly
from (a) Streamlit's own documented guarantee that st.session_state
persists across reruns and page navigation within one session, and (b) the
page code's own dict.get()-based lookup for stale candidates (see
app/ui/pages/3b_Shortlist.py) - verified by code review, not by a new test
harness.
"""
from __future__ import annotations

from app.ui.shortlist import (
    ReportCandidate,
    add_candidate,
    clear_shortlist,
    is_shortlisted,
    remove_candidate,
    shortlist_count,
    shortlist_items,
)

# --- A. add ---------------------------------------------------------------

def test_add_candidate_adds_a_new_entry():
    state = add_candidate({}, ReportCandidate("allocation", 1, "Northern Gateway"))
    assert is_shortlisted(state, "allocation", 1)
    assert shortlist_count(state) == 1


def test_add_candidate_does_not_mutate_the_input_dict():
    original: dict = {}
    add_candidate(original, ReportCandidate("allocation", 1, "Northern Gateway"))
    # The caller is responsible for storing the returned dict back into
    # st.session_state - the input must be left untouched, or a caller that
    # forgot to capture the return value would silently see no change.
    assert original == {}


# --- B. duplicate add does not create duplicate ----------------------------

def test_duplicate_add_of_the_same_candidate_does_not_create_a_duplicate():
    state = add_candidate({}, ReportCandidate("allocation", 1, "Northern Gateway"))
    state = add_candidate(state, ReportCandidate("allocation", 1, "Northern Gateway"))
    state = add_candidate(state, ReportCandidate("allocation", 1, "Northern Gateway"))
    assert shortlist_count(state) == 1


def test_re_adding_the_same_id_with_an_updated_display_name_overwrites_the_stored_label():
    state = add_candidate({}, ReportCandidate("allocation", 1, "Old Name"))
    state = add_candidate(state, ReportCandidate("allocation", 1, "New Name"))
    assert shortlist_count(state) == 1
    assert shortlist_items(state)[0].display_name == "New Name"


# --- C. remove --------------------------------------------------------------

def test_remove_candidate_removes_an_existing_entry():
    state = add_candidate({}, ReportCandidate("allocation", 1, "Northern Gateway"))
    state = remove_candidate(state, "allocation", 1)
    assert not is_shortlisted(state, "allocation", 1)
    assert shortlist_count(state) == 0


def test_remove_candidate_on_a_missing_entry_is_a_no_op_and_does_not_raise():
    state = remove_candidate({}, "allocation", 999)
    assert state == {}


def test_remove_candidate_does_not_mutate_the_input_dict():
    original = add_candidate({}, ReportCandidate("allocation", 1, "Northern Gateway"))
    remove_candidate(original, "allocation", 1)
    assert is_shortlisted(original, "allocation", 1)


# --- D. clear ----------------------------------------------------------------

def test_clear_shortlist_empties_a_populated_shortlist():
    state = {}
    for i in range(5):
        state = add_candidate(state, ReportCandidate("allocation", i, f"Allocation {i}"))
    assert shortlist_count(state) == 5
    state = clear_shortlist(state)
    assert state == {}
    assert shortlist_count(state) == 0


def test_clear_shortlist_on_an_already_empty_shortlist_is_a_no_op():
    assert clear_shortlist({}) == {}


# --- E. is_shortlisted --------------------------------------------------------

def test_is_shortlisted_true_for_a_present_candidate():
    state = add_candidate({}, ReportCandidate("allocation", 1, "Northern Gateway"))
    assert is_shortlisted(state, "allocation", 1) is True


def test_is_shortlisted_false_for_an_absent_candidate():
    assert is_shortlisted({}, "allocation", 1) is False


# --- F. shortlist_items -------------------------------------------------------

def test_shortlist_items_returns_every_candidate_when_no_type_filter_given():
    state = add_candidate({}, ReportCandidate("allocation", 1, "A"))
    state = add_candidate(state, ReportCandidate("allocation", 2, "B"))
    items = shortlist_items(state)
    assert {c.candidate_id for c in items} == {1, 2}


def test_shortlist_items_filters_by_candidate_type():
    state = add_candidate({}, ReportCandidate("allocation", 1, "A"))
    state = add_candidate(state, ReportCandidate("planning_site", 1, "B"))
    allocations_only = shortlist_items(state, "allocation")
    assert len(allocations_only) == 1
    assert allocations_only[0].candidate_type == "allocation"


def test_shortlist_items_returns_an_empty_list_for_an_empty_shortlist():
    assert shortlist_items({}) == []


# --- G. shortlist_count --------------------------------------------------------

def test_shortlist_count_matches_len_of_shortlist_items():
    state = add_candidate({}, ReportCandidate("allocation", 1, "A"))
    state = add_candidate(state, ReportCandidate("allocation", 2, "B"))
    state = add_candidate(state, ReportCandidate("planning_site", 1, "C"))
    assert shortlist_count(state) == len(shortlist_items(state))
    assert shortlist_count(state, "allocation") == len(shortlist_items(state, "allocation")) == 2


# --- H. mixed candidate types do not collide -----------------------------------

def test_mixed_candidate_types_coexist_independently():
    state = add_candidate({}, ReportCandidate("allocation", 1, "Allocation One"))
    state = add_candidate(state, ReportCandidate("planning_site", 1, "Planning Site One"))
    assert shortlist_count(state) == 2
    assert is_shortlisted(state, "allocation", 1)
    assert is_shortlisted(state, "planning_site", 1)


# --- I. same numeric id, different candidate_type, does not collide -------------

def test_removing_one_candidate_type_does_not_remove_the_other_sharing_the_same_numeric_id():
    state = add_candidate({}, ReportCandidate("allocation", 1, "Allocation One"))
    state = add_candidate(state, ReportCandidate("planning_site", 1, "Planning Site One"))
    state = remove_candidate(state, "allocation", 1)
    assert not is_shortlisted(state, "allocation", 1)
    assert is_shortlisted(state, "planning_site", 1)
    assert shortlist_count(state) == 1


# --- J. display label retained correctly ----------------------------------------

def test_display_name_is_retained_exactly_as_added():
    state = add_candidate({}, ReportCandidate("allocation", 1, "499 Chester Road, Old Trafford"))
    [item] = shortlist_items(state)
    assert item.display_name == "499 Chester Road, Old Trafford"


# --- Misc: ReportCandidate is a plain, comparable value object -------------------

def test_report_candidate_instances_are_equal_by_value_not_identity():
    a = ReportCandidate("allocation", 1, "Northern Gateway")
    b = ReportCandidate("allocation", 1, "Northern Gateway")
    assert a == b
    assert a is not b


# --- Gate 1A batch-add pattern (add_candidate looped over a selection) ------
# Gate 1A's table submits a BATCH of candidates in one action (looping
# add_candidate once per selected row, per app/ui/pages/3_Local_Plan_Sites.py)
# rather than Gate 1's one-candidate-per-click. These tests exercise that
# exact loop pattern directly, confirming batch-level idempotency and
# duplicate-freedom follow from add_candidate's already-proven per-call
# behaviour rather than assuming it.

def _batch_add(state: dict, candidates: list[ReportCandidate]) -> dict:
    """Mirrors the exact loop app/ui/pages/3_Local_Plan_Sites.py runs on
    "Add selected to shortlist" submit."""
    for candidate in candidates:
        state = add_candidate(state, candidate)
    return state


def test_batch_add_of_several_new_candidates_adds_them_all():
    batch = [ReportCandidate("allocation", i, f"Allocation {i}") for i in range(5)]
    state = _batch_add({}, batch)
    assert shortlist_count(state) == 5
    assert all(is_shortlisted(state, "allocation", i) for i in range(5))


def test_batch_add_is_idempotent_when_the_same_batch_is_submitted_twice():
    batch = [ReportCandidate("allocation", i, f"Allocation {i}") for i in range(5)]
    state = _batch_add({}, batch)
    state = _batch_add(state, batch)  # simulates a second, accidental submit of the same selection
    assert shortlist_count(state) == 5


def test_batch_add_does_not_duplicate_allocations_already_in_the_shortlist():
    state = add_candidate({}, ReportCandidate("allocation", 1, "Already Shortlisted"))
    batch = [
        ReportCandidate("allocation", 1, "Already Shortlisted"),
        ReportCandidate("allocation", 2, "New Addition"),
    ]
    state = _batch_add(state, batch)
    assert shortlist_count(state) == 2


def test_report_candidate_is_frozen():
    candidate = ReportCandidate("allocation", 1, "Northern Gateway")
    try:
        candidate.candidate_id = 2  # type: ignore[misc]
        raised = False
    except Exception:
        raised = True
    assert raised, "ReportCandidate must be frozen (immutable identity, not a mutable session-state record)"
