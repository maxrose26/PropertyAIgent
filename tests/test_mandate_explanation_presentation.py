from types import SimpleNamespace

from app.policy.buyer_matching import BuyerFitAssessment
from app.reporting.mandate_explanation import mandate_fit_label, present_mandate_explanation


def entry(reason, role, contributed=False):
    return SimpleNamespace(reason=reason, role=role, contributed=contributed, rule_id="scale")


def test_legacy_positive_remains_verbatim_and_partial_without_guessed_cause():
    fit = BuyerFitAssessment("POSSIBLE_FIT", False, ["100–102 total homes; outside preferred range"])
    view = present_mandate_explanation(fit)
    assert view.positives == tuple(fit.matches)
    assert not view.classification_causes
    assert view.coverage == "partial recorded explanation"
    assert view.coverage_notice == "Possible Mandate Fit — classification explanation not fully available"


def test_empty_legacy_has_unavailable_matching_explanation():
    view = present_mandate_explanation(BuyerFitAssessment("STRONG_FIT", False))
    assert view.coverage == "matching explanation unavailable"
    assert not view.positives and not view.classification_causes
    assert "Ownership/control is not verified by this mandate assessment" in view.contextual_limitations


def test_labels_do_not_change_internal_classifications():
    assert mandate_fit_label("STRONG_FIT") == "Strong Mandate Fit"
    assert mandate_fit_label("POSSIBLE_FIT") == "Possible Mandate Fit"
    assert mandate_fit_label("INSUFFICIENT_EVIDENCE", True) == "Investigate"


def test_complete_trace_only_contributing_causes_and_all_positives_are_retained():
    fit = SimpleNamespace(classification="POSSIBLE_FIT", matches=["first", "second", "third"],
        unknown=["control unknown"], does_not_match=[], investigate=["check approved plans"],
        explanation_trace=(entry("scale qualification", "classification_affecting", True),
                           entry("overridden rule", "classification_affecting"),
                           entry("control unknown", "contextual")), explanation_coverage="complete")
    view = present_mandate_explanation(fit, {"application_reference": "APP-1"})
    assert view.positives == ("first", "second", "third")
    assert view.classification_causes == ("scale qualification",)
    assert "control unknown" in view.contextual_limitations
    assert view.coverage == "complete recorded assessment"
    assert view.evidence_context == ("Supporting application: APP-1", "Evidence date unavailable", "Evidence version unavailable", "Source link unavailable")


def test_blocking_unknown_is_not_duplicated_as_context():
    fit = SimpleNamespace(classification="INSUFFICIENT_EVIDENCE", matches=[], unknown=["scale unknown"],
        does_not_match=[], investigate=[], explanation_coverage="complete",
        explanation_trace=(entry("scale unknown", "classification_affecting", True), entry("scale unknown", "contextual")))
    view = present_mandate_explanation(fit)
    assert view.classification_causes == ("scale unknown",)
    assert "scale unknown" not in view.contextual_limitations


def test_existing_subject_count_and_provenance_are_qualified_not_invented():
    from app.reporting.residential_count import CountAssessment
    count = CountAssessment("phase", "Phase 1", metric="affordable", precision="APPROXIMATE",
                            value=30, lower=29, upper=31, confidence="medium",
                            sources=(SimpleNamespace(application_reference="PHASE-1"),))
    fit = BuyerFitAssessment("STRONG_FIT", False, ["Recorded affordable metric reason"])
    view = present_mandate_explanation(fit, {
        "count_assessment": count, "application_reference": "PHASE-1",
        "source_date": "2026-01-01", "source_version": "approved revision B",
        "source_url": "https://example.org/planning/phase-1",
    })
    assert "Count scope: Phase 1 (phase); metric: affordable" in view.evidence_context
    assert "Reported estimate; exact scale unverified." in view.evidence_context
    assert "Evidence date: 2026-01-01" in view.evidence_context
    assert "Evidence version: approved revision B" in view.evidence_context
    assert view.source_link == "https://example.org/planning/phase-1"
    assert view.classification_causes == ()
    assert present_mandate_explanation(fit, {"source_url": "https://user:secret@example.org"}).source_link is None
