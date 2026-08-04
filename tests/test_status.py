from app.policy.status import (
    derive_allocation_status_from_plan_status,
    normalise_allocation_status,
    normalise_plan_status,
)


def test_normalise_plan_status_known_variants():
    assert normalise_plan_status("Adopted") == "adopted"
    assert normalise_plan_status("Adopted Local Plan (2024)") == "adopted"
    assert normalise_plan_status("Regulation 18 Issues and Options") == "issues_and_options"
    assert normalise_plan_status("Regulation 19 Proposed Submission") == "proposed_submission"
    assert normalise_plan_status("Submitted for examination") in ("proposed_submission", "submitted", "examination")
    assert normalise_plan_status("Examination in Public") == "examination"
    assert normalise_plan_status("Main Modifications consultation") == "main_modifications"
    assert normalise_plan_status("Withdrawn") == "withdrawn"
    assert normalise_plan_status("Paused pending further evidence") == "paused"


def test_normalise_plan_status_never_guesses():
    assert normalise_plan_status(None) == "unknown"
    assert normalise_plan_status("") == "unknown"
    assert normalise_plan_status("some unrecognised council-specific phrase") == "unknown"


def test_normalise_allocation_status_draft_never_becomes_adopted():
    assert normalise_allocation_status("Draft allocation") == "draft_allocation"
    assert normalise_allocation_status("Draft") == "draft_allocation"
    assert normalise_allocation_status("Draft allocation") != "adopted_allocation"


def test_normalise_allocation_status_adopted_requires_explicit_wording():
    assert normalise_allocation_status("Adopted site allocation") == "adopted_allocation"
    assert normalise_allocation_status("Removed from the plan") == "removed"
    assert normalise_allocation_status("Rejected at examination") == "rejected"
    assert normalise_allocation_status("Safeguarded land") == "safeguarded"


def test_derive_allocation_status_never_defaults_to_adopted():
    # Even when the PLAN is adopted, an allocation with no status of its own
    # must not be silently promoted to "adopted_allocation" - its own status
    # can lag the plan's (Part 6/7 of the sprint brief).
    status, note = derive_allocation_status_from_plan_status("adopted")
    assert status != "adopted_allocation"
    assert "plan adopted" in note.lower() or "not independently confirmed" in note.lower()


def test_derive_allocation_status_draft_plan():
    status, note = derive_allocation_status_from_plan_status("draft")
    assert status == "draft_allocation"
    assert "draft" in note.lower()
