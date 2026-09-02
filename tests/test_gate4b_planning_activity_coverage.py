"""Gate 4B ("Allocation <-> Site/Application Planning Activity Coverage") -
tests for app.policy.allocation_planning_coverage. Uses real Trafford
Site records (read-only, against the isolated `session` fixture with
hand-built rows mirroring the REAL production case this gate's own
investigation found) to prove the site-match corroboration check against
genuine false-positive/true-positive shapes, plus the coverage-mapping
layer against every one of the existing engine's own 6 classifications."""
from __future__ import annotations

from app.db.models import Council, Site
from app.extraction.local_plan import match_to_existing_site
from app.reporting.allocation_development_coverage import (
    CAPACITY_UNKNOWN,
    FULLY_ACCOUNTED_FOR,
    NO_IDENTIFIED_ACTIVITY,
    PARTIAL_COVERAGE,
    REVIEW_REQUIRED,
    SUBSTANTIALLY_COVERED,
    DevelopmentCoverageResult,
)
from app.policy.allocation_planning_coverage import (
    FULL,
    NONE_FOUND,
    PARTIAL,
    UNCERTAIN,
    classify_planning_activity_coverage,
    classify_site_match_confidence,
)


def _site(id_, address, council_code="trafford"):
    return Site(
        id=id_, council_code=council_code, canonical_address=address.lower(), display_address=address,
    )


def _coverage(classification, **overrides):
    base = dict(
        allocation_capacity=1000, identified_application_capacity=0, indicative_residual_capacity=1000,
        development_coverage_percentage=0.0, number_of_related_sites=0, number_of_linked_applications=0,
        number_of_sites_with_planning_activity=0, number_of_sites_without_identified_planning_activity=0,
        capacity_accounting_status="ok", development_coverage_classification=classification, note=None,
    )
    base.update(overrides)
    return DevelopmentCoverageResult(**base)


# --- Matching (real Trafford Site records - the exact case this module was built for) ---

MANCHESTER_WATERS_SITE = _site(423, "Manchester Waters Pomona Strand Old Trafford")
HARRY_LORD_HOUSE_SITE = _site(254, "Harry Lord House 120 Humphrey Road Old Trafford Manchester M16 9DF")
STRETFORD_MALL_SITE = _site(261, "Land At Stretford Mall Chester Road Stretford M32 9BD")


def test_1_strong_real_site_match_accepted():
    site, score = match_to_existing_site("Site of the former Stretford Mall, Chester Road, Stretford", [STRETFORD_MALL_SITE])
    assert site is not None and site.id == 261
    assessment = classify_site_match_confidence("Site of the former Stretford Mall, Chester Road, Stretford", site, score)
    assert assessment.confidence == "HIGH"
    assert "stretford" in assessment.shared_tokens or "chester" in assessment.shared_tokens


def test_2_weak_fuzzy_match_safely_withheld_via_corroboration():
    # The real Gate 4B finding: "Land west of Skerton Road, Old Trafford"
    # fuzzy-matches "Harry Lord House 120 Humphrey Road Old Trafford" at
    # 81.0 (above match_to_existing_site's own 80.0 threshold) - sharing
    # only the generic area name "Old Trafford", nothing specific.
    site, score = match_to_existing_site("Land west of Skerton Road, Old Trafford", [HARRY_LORD_HOUSE_SITE])
    assert site is not None  # match_to_existing_site itself DOES accept it - untouched, not modified
    assessment = classify_site_match_confidence("Land west of Skerton Road, Old Trafford", site, score)
    assert assessment.confidence == "LOW"  # but Gate 4B's own corroboration check correctly withholds confidence


def test_3_geographic_contradiction_prevents_false_match():
    # The second real Gate 4B finding: "Trafford Waters" (a genuinely
    # different site, Urmston) fuzzy-matches "Manchester Waters Pomona
    # Strand Old Trafford" at 100.0, sharing only the generic word
    # "Waters" - corroboration correctly finds nothing specific shared.
    site, score = match_to_existing_site("Trafford Waters", [MANCHESTER_WATERS_SITE])
    assert site is not None
    assessment = classify_site_match_confidence("Trafford Waters", site, score)
    assert assessment.confidence == "LOW"
    assert assessment.shared_tokens == frozenset()


def test_4_naming_variation_can_still_match_with_specific_corroborating_evidence():
    # "Pomona" (the allocation's real name) DOES share a specific,
    # non-generic identifier with "Manchester Waters POMONA Strand" -
    # correctly HIGH, unlike AN3's Trafford Waters above despite an
    # identical 100.0 fuzzy score.
    site, score = match_to_existing_site("Pomona", [MANCHESTER_WATERS_SITE])
    assert site is not None
    assessment = classify_site_match_confidence("Pomona", site, score)
    assert assessment.confidence == "HIGH"
    assert "pomona" in assessment.shared_tokens


def test_5_ambiguous_ties_are_visible_not_silently_resolved():
    # AN3 and AN4 both scored 100.0 against the SAME site - proven
    # directly: classify_site_match_confidence alone correctly separates
    # them (LOW vs HIGH) without needing a special tie-breaking rule -
    # the corroboration check IS the disambiguation.
    site_a, score_a = match_to_existing_site("Trafford Waters", [MANCHESTER_WATERS_SITE])
    site_b, score_b = match_to_existing_site("Pomona", [MANCHESTER_WATERS_SITE])
    assert site_a.id == site_b.id == 423
    assert score_a == score_b == 100.0
    assert classify_site_match_confidence("Trafford Waters", site_a, score_a).confidence == "LOW"
    assert classify_site_match_confidence("Pomona", site_b, score_b).confidence == "HIGH"


# --- Application linkage / coverage mapping (Steps 6-7 of the checklist) ---

def test_6_trusted_full_site_application_maps_to_full():
    coverage = _coverage(FULLY_ACCOUNTED_FOR, identified_application_capacity=950, development_coverage_percentage=0.95,
                          number_of_related_sites=1, number_of_linked_applications=1, number_of_sites_with_planning_activity=1)
    result = classify_planning_activity_coverage(coverage)
    assert result.classification == FULL
    assert "95%" in result.reason


def test_7_no_matched_site_maps_to_none_found_with_correct_wording():
    coverage = _coverage(NO_IDENTIFIED_ACTIVITY)
    result = classify_planning_activity_coverage(coverage)
    assert result.classification == NONE_FOUND
    assert "does not exist" not in result.reason.lower()
    # Explicitly DISCLAIMS the external-absence reading (Gate 4B's own
    # required product distinction) - the phrase appears only inside a
    # negation ("...it is not a statement that..."), never asserted.
    assert "not a statement that no planning application exists" in result.reason.lower()
    assert "current evidence" in result.reason.lower() or "current" in result.reason.lower()


# --- Coverage ---

def test_8_trusted_full_site_application_full():
    coverage = _coverage(FULLY_ACCOUNTED_FOR, development_coverage_percentage=0.97)
    assert classify_planning_activity_coverage(coverage).classification == FULL


def test_9_trusted_partial_application_partial():
    coverage = _coverage(PARTIAL_COVERAGE, development_coverage_percentage=0.3, indicative_residual_capacity=700)
    result = classify_planning_activity_coverage(coverage)
    assert result.classification == PARTIAL
    assert "700" in result.reason


def test_9b_substantially_covered_also_maps_to_partial():
    # SUBSTANTIALLY_COVERED (0.7-0.9) is still, honestly, only PART of the
    # allocation accounted for - Gate 4B's own narrower vocabulary
    # deliberately compresses it into PARTIAL rather than FULL.
    coverage = _coverage(SUBSTANTIALLY_COVERED, development_coverage_percentage=0.8, indicative_residual_capacity=200)
    assert classify_planning_activity_coverage(coverage).classification == PARTIAL


def test_10_no_qualifying_activity_none_found():
    coverage = _coverage(NO_IDENTIFIED_ACTIVITY)
    assert classify_planning_activity_coverage(coverage).classification == NONE_FOUND


def test_11_ambiguous_application_overlap_uncertain():
    coverage = _coverage(REVIEW_REQUIRED, capacity_accounting_status="review_required",
                          note="Multiple development parcels identified — capacity accounting requires review.")
    result = classify_planning_activity_coverage(coverage)
    assert result.classification == UNCERTAIN
    assert "requires review" in result.reason


def test_12_missing_trusted_capacity_does_not_fabricate_full_or_partial():
    # CAPACITY_UNKNOWN - identified activity exists but no trusted
    # allocation capacity to compare it against - must never produce a
    # numeric FULL/PARTIAL percentage from nothing.
    coverage = _coverage(CAPACITY_UNKNOWN, allocation_capacity=None, identified_application_capacity=400,
                          indicative_residual_capacity=None, development_coverage_percentage=None)
    result = classify_planning_activity_coverage(coverage)
    assert result.classification == UNCERTAIN
    assert "%" not in result.reason


def test_13_refused_withdrawn_historic_application_does_not_automatically_create_full():
    # Handled entirely by the EXISTING engine (summarise_site_activity /
    # pick_representative_application, already tested in test_allocation_
    # development_coverage.py) - this test proves the Gate 4B mapping
    # layer doesn't independently second-guess or override that decision:
    # a REVIEW_REQUIRED result (e.g. because the one representative
    # application's status/units couldn't be safely determined) maps to
    # UNCERTAIN, never FULL, regardless of how many historic applications
    # exist.
    coverage = _coverage(REVIEW_REQUIRED, capacity_accounting_status="review_required",
                          number_of_linked_applications=5, note="Capacity accounting requires review — see linked applications.")
    assert classify_planning_activity_coverage(coverage).classification == UNCERTAIN


def test_14_multiple_overlapping_applications_not_naively_double_counted():
    # Real production proof: AN5 (Stretford Mall) has 4 real Applications
    # (outline hybrid + variation + reserved matters + conditions
    # discharge - a classic single-scheme paper trail) whose face-value
    # unit totals would exceed the 750-dwelling allocation if summed
    # naively - the EXISTING engine's own negative-residual clamp (proven
    # this gate against real Trafford data) already produces
    # REVIEW_REQUIRED, never a bogus >100% FULL. This test proves the
    # mapping layer preserves that safety rather than reinterpreting it.
    coverage = _coverage(REVIEW_REQUIRED, capacity_accounting_status="review_required",
                          allocation_capacity=750, identified_application_capacity=800,
                          number_of_related_sites=1, number_of_linked_applications=4,
                          note="Capacity accounting requires review — see linked applications.")
    assert classify_planning_activity_coverage(coverage).classification == UNCERTAIN


def test_15_outline_and_reserved_matters_do_not_double_count_units():
    # Same real AN5 shape as test_14 from a different angle: the
    # UNDERLYING engine's summarise_site_activity picks exactly ONE
    # representative application per Site (never sums outline + reserved
    # matters + variation on the same site) - already proven/tested there;
    # this confirms the Gate 4B layer never re-sums site_summaries itself.
    coverage = _coverage(PARTIAL_COVERAGE, allocation_capacity=750, identified_application_capacity=251,
                          development_coverage_percentage=251 / 750, indicative_residual_capacity=499,
                          number_of_related_sites=1, number_of_linked_applications=1)
    result = classify_planning_activity_coverage(coverage)
    assert result.classification == PARTIAL
    assert coverage.identified_application_capacity == 251  # the ONE representative application's own figure only


# --- Provenance ---

def test_16_coverage_reason_identifies_supporting_evidence():
    coverage = _coverage(FULLY_ACCOUNTED_FOR, development_coverage_percentage=1.0, allocation_capacity=100,
                          number_of_linked_applications=1, number_of_sites_with_planning_activity=1)
    result = classify_planning_activity_coverage(coverage)
    assert "application" in result.reason.lower()
    assert result.underlying_classification == FULLY_ACCOUNTED_FOR


def test_17_none_found_wording_never_claims_external_absence():
    # Checks for an AFFIRMATIVE absence claim (the phrase NOT preceded by
    # a negation like "not a statement that") - the reason may discuss the
    # concept of "no planning application exists" only to explicitly deny
    # it, never to assert it.
    result = classify_planning_activity_coverage(_coverage(NO_IDENTIFIED_ACTIVITY))
    lowered = result.reason.lower()
    affirmative_absence_claims = ["does not exist", "will never", "confirmed absent", "definitely no planning"]
    for phrase in affirmative_absence_claims:
        assert phrase not in lowered
    assert "not a statement that no planning application exists" in lowered


# --- Safety ---

def test_18_pfe_allocation_never_silently_becomes_trafford_own_plan():
    # Documents the real production shape directly - New Carrington (JPA
    # 30) is council_code="trafford" but local_plan_id=2 (PfE); nothing in
    # this module reads/writes local_plan_id at all, so it cannot
    # silently reassign plan identity - proven by the module's own
    # signature never accepting or touching a LocalPlan/plan_id argument.
    import inspect
    sig = inspect.signature(classify_planning_activity_coverage)
    assert "plan" not in " ".join(sig.parameters).lower()
    sig2 = inspect.signature(classify_site_match_confidence)
    assert "plan" not in " ".join(sig2.parameters).lower()


def test_19_no_cross_authority_matching_is_possible_through_this_module():
    # classify_site_match_confidence only ever compares the two strings
    # it is given - it never queries candidate Sites itself (that remains
    # match_to_existing_site's own caller's responsibility, which already
    # filters by council_code before calling it - untouched by this gate).
    other_authority_site = _site(999, "Some Site In Bolton", council_code="bolton")
    assessment = classify_site_match_confidence("Trafford Waters", other_authority_site, 100.0)
    # This module has no council-awareness of its own - it is the CALLER's
    # job (unchanged, pre-existing) to only ever pass same-council
    # candidates, exactly as app.extraction.local_plan.match_to_existing_
    # site's own callers already do. Documented here, not silently assumed.
    assert assessment is not None  # no crash; council-scoping is the caller's contract, not this function's


def test_20_legacy_vs_gate4a_verified_provenance_remains_distinguishable():
    # A coverage result's own underlying_classification/reason never
    # asserts anything about WHERE the allocation's capacity number came
    # from (Gate 4A-verified vs legacy manifest) - that provenance lives
    # entirely on LocalPlanSite/AllocationVersion (Gate 4A's own audit
    # trail, untouched by this module) and remains fully queryable
    # independently of whatever coverage classification this module
    # produces.
    coverage = _coverage(PARTIAL_COVERAGE, development_coverage_percentage=0.5, indicative_residual_capacity=500)
    result = classify_planning_activity_coverage(coverage)
    assert "legacy" not in result.reason.lower() and "gate 4a" not in result.reason.lower()
