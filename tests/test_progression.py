import datetime as dt

from app.policy.progression import SIGNALS, classify_progression


def test_all_signals_are_the_seven_from_the_spec():
    assert set(SIGNALS) == {
        "early_stage", "progressing", "advanced", "adopted", "stalled", "removed", "unknown",
    }


def test_early_stage():
    signal, reasons = classify_progression("preparation", "under_consideration")
    assert signal == "early_stage"
    assert reasons


def test_progressing():
    signal, reasons = classify_progression("proposed_submission", None)
    assert signal == "progressing"
    assert reasons


def test_advanced():
    signal, reasons = classify_progression("examination", "submitted_allocation")
    assert signal == "advanced"
    assert reasons


def test_adopted_requires_both_plan_and_allocation_confirmed():
    signal, reasons = classify_progression("adopted", "adopted_allocation")
    assert signal == "adopted"
    assert reasons


def test_adopted_plan_with_unconfirmed_allocation_is_not_claimed_adopted():
    # The critical negative case: a plan being adopted must NEVER, by
    # itself, cause an allocation to be reported as adopted - its own
    # status has to independently confirm that.
    signal, _ = classify_progression("adopted", "draft_allocation")
    assert signal != "adopted"
    assert signal == "unknown"


def test_stalled_on_withdrawn_plan():
    signal, reasons = classify_progression("withdrawn", "draft_allocation")
    assert signal == "stalled"
    assert "withdrawn" in reasons[0].lower()


def test_stalled_on_paused_plan():
    signal, _ = classify_progression("paused", "draft_allocation")
    assert signal == "stalled"


def test_stalled_when_expected_adoption_date_has_passed():
    signal, reasons = classify_progression(
        "examination", "submitted_allocation",
        expected_adoption_date=dt.date(2020, 1, 1), today=dt.date(2026, 1, 1),
    )
    assert signal == "stalled"
    assert reasons


def test_removed_on_allocation_status():
    for status in ("removed", "rejected"):
        signal, reasons = classify_progression("examination", status)
        assert signal == "removed"
        assert reasons


def test_removed_when_absent_from_latest_version():
    signal, reasons = classify_progression("examination", "submitted_allocation", present_in_latest_version=False)
    assert signal == "removed"
    assert "not present" in reasons[0].lower()


def test_unknown_when_nothing_matches():
    signal, reasons = classify_progression(None, None)
    assert signal == "unknown"
    assert reasons


def test_explicit_adoption_evidence_applies_automatically():
    # The one positive case: BOTH the plan and the allocation's own status
    # explicitly say adopted - this is the only combination classify_
    # progression is allowed to report as "adopted".
    signal, reasons = classify_progression("adopted", "adopted_allocation")
    assert signal == "adopted"
    assert reasons


def test_adopted_plan_does_not_adopt_removed_allocations():
    signal, reasons = classify_progression("adopted", "removed")
    assert signal == "removed"
    assert signal != "adopted"
    assert reasons


def test_adopted_plan_does_not_adopt_rejected_allocations():
    signal, _ = classify_progression("adopted", "rejected")
    assert signal == "removed"
    assert signal != "adopted"


def test_adopted_plan_does_not_adopt_allocations_with_no_confirmed_status():
    # An allocation that predates independent confirmation (still whatever
    # app.policy.status.derive_allocation_status_from_plan_status defaulted
    # it to) must not inherit "adopted" just because the plan around it now
    # is - see test_status.py's matching derive_allocation_status_from_plan_status test.
    for unconfirmed_status in ("draft_allocation", "under_consideration", "proposed_submission_allocation", None):
        signal, _ = classify_progression("adopted", unconfirmed_status)
        assert signal != "adopted"


def test_never_predicts_certainty_language():
    # No branch of the classifier should ever produce a reason claiming a
    # future outcome is certain (Part 7: "Never claim an allocation will
    # definitely be adopted").
    forbidden = ("will be adopted", "guaranteed", "certain to", "definitely")
    for plan_status in ("preparation", "proposed_submission", "examination", "adopted", "withdrawn", "paused"):
        for allocation_status in (None, "under_consideration", "draft_allocation", "submitted_allocation", "adopted_allocation", "removed"):
            _, reasons = classify_progression(plan_status, allocation_status)
            joined = " ".join(reasons).lower()
            for phrase in forbidden:
                assert phrase not in joined
