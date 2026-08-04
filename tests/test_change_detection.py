from app.policy.change_detection import (
    classify_confidence,
    classify_source_check,
    compute_content_hash,
    diff_allocations,
    diff_plan,
)


def test_hash_is_stable_for_identical_content():
    assert compute_content_hash("Site HOM 2.30 - 40 dwellings") == compute_content_hash("Site HOM 2.30 - 40 dwellings")


def test_hash_ignores_incidental_whitespace():
    a = compute_content_hash("Site HOM 2.30 - 40 dwellings")
    b = compute_content_hash("Site  HOM 2.30 -\n40   dwellings\t")
    assert a == b


def test_hash_changes_for_different_content():
    a = compute_content_hash("40 dwellings")
    b = compute_content_hash("42 dwellings")
    assert a != b


def test_classify_source_check_first_check_is_not_a_change():
    assert classify_source_check(None, "abc123") == "first_check"


def test_classify_source_check_unchanged():
    assert classify_source_check("abc123", "abc123") == "unchanged"


def test_classify_source_check_changed():
    assert classify_source_check("abc123", "def456") == "changed"


def test_diff_plan_first_time_is_new_plan_version():
    events = diff_plan(None, {"plan_version": "Regulation 18", "status": "issues_and_options"})
    assert len(events) == 1
    assert events[0]["event_type"] == "new_plan_version"


def test_diff_plan_no_change_produces_no_events():
    snapshot = {"plan_version": "Regulation 18", "status": "issues_and_options"}
    assert diff_plan(snapshot, dict(snapshot)) == []


def test_diff_plan_stage_transition():
    old = {"plan_version": "Regulation 18", "status": "issues_and_options"}
    new = {"plan_version": "Regulation 18", "status": "draft_consultation"}
    events = diff_plan(old, new)
    assert len(events) == 1
    assert events[0]["event_type"] == "stage_change"


def test_diff_plan_adoption_is_its_own_event_type():
    old = {"plan_version": "Adopted 2024", "status": "examination"}
    new = {"plan_version": "Adopted 2024", "status": "adopted"}
    events = diff_plan(old, new)
    assert events[0]["event_type"] == "adoption"


def test_diff_plan_withdrawal_is_its_own_event_type():
    old = {"plan_version": None, "status": "examination"}
    new = {"plan_version": None, "status": "withdrawn"}
    events = diff_plan(old, new)
    assert events[0]["event_type"] == "withdrawal"


def _allocation(ref, dwellings=40, status="draft_allocation"):
    return {
        "policy_reference": ref, "minimum_dwellings": dwellings,
        "indicative_capacity": None, "maximum_capacity": None, "allocation_status": status,
    }


def test_diff_allocations_new_allocation():
    events = diff_allocations([], [_allocation("HOM 2.30")])
    assert len(events) == 1
    assert events[0]["event_type"] == "new_allocation"


def test_diff_allocations_removed_allocation_is_never_silently_dropped():
    events = diff_allocations([_allocation("HOM 2.30")], [])
    assert len(events) == 1
    assert events[0]["event_type"] == "allocation_removed"


def test_diff_allocations_retained_when_unchanged():
    row = _allocation("HOM 2.30")
    events = diff_allocations([row], [dict(row)])
    assert len(events) == 1
    assert events[0]["event_type"] == "allocation_retained"


def test_diff_allocations_capacity_changed():
    old = _allocation("HOM 2.30", dwellings=40)
    new = _allocation("HOM 2.30", dwellings=55)
    events = diff_allocations([old], [new])
    assert len(events) == 1
    assert events[0]["event_type"] == "capacity_changed"


def test_diff_allocations_status_changed():
    old = _allocation("HOM 2.30", status="draft_allocation")
    new = _allocation("HOM 2.30", status="submitted_allocation")
    events = diff_allocations([old], [new])
    assert len(events) == 1
    assert events[0]["event_type"] == "allocation_amended"


def test_diff_allocations_can_report_both_capacity_and_status_change():
    old = _allocation("HOM 2.30", dwellings=40, status="draft_allocation")
    new = _allocation("HOM 2.30", dwellings=55, status="submitted_allocation")
    events = diff_allocations([old], [new])
    event_types = {e["event_type"] for e in events}
    assert event_types == {"capacity_changed", "allocation_amended"}


def test_classify_confidence_safe_changes_auto_apply():
    assert classify_confidence("new_allocation") == "auto_applied"
    assert classify_confidence("allocation_retained") == "auto_applied"


def test_classify_confidence_ambiguous_changes_need_review():
    for event_type in ("allocation_removed", "allocation_amended", "capacity_changed", "adoption", "withdrawal", "stage_change", "new_plan_version"):
        assert classify_confidence(event_type) == "needs_review"
