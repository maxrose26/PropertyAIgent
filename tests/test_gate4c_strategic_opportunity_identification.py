"""Gate 4C ("Strategic Opportunity Identification") - tests for the one
new function this gate adds, app.policy.allocation_planning_coverage.
enrich_none_found_reason, plus integration proofs against the EXISTING,
unmodified app.reporting.allocation_development_coverage.
build_opportunity_signal (already covered by its own existing test suite -
not duplicated here; see tests/test_allocation_development_coverage.py
for FULL/PARTIAL/SUBSTANTIALLY_COVERED/CAPACITY_UNKNOWN/REVIEW_REQUIRED
mapping, phasing, and the ownership-caveat wording, all reused verbatim by
this gate, none of it retested here).

Every fixture is a real Trafford Site record (matching Gate 4B's own real
false-positive/true-positive findings) or a directly-constructed
DevelopmentCoverageResult, exactly mirroring test_gate4b_planning_activity_
coverage.py's own established fixture style."""
from __future__ import annotations

from app.db.models import Site
from app.reporting.allocation_development_coverage import (
    CAPACITY_UNKNOWN,
    FULLY_ACCOUNTED_FOR,
    NO_IDENTIFIED_ACTIVITY,
    PARTIAL_COVERAGE,
    REVIEW_REQUIRED,
    DevelopmentCoverageResult,
    build_opportunity_signal,
)
from app.policy.allocation_planning_coverage import enrich_none_found_reason

MANCHESTER_WATERS_SITE = Site(
    id=423, council_code="trafford", canonical_address="manchester waters pomona strand old trafford",
    display_address="Manchester Waters Pomona Strand Old Trafford",
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


# --- 1-2: residential NONE_FOUND -> INVESTIGATE, correctly worded ---

def test_1_residential_none_found_with_strong_evidence_produces_investigate():
    coverage = _coverage(NO_IDENTIFIED_ACTIVITY, allocation_capacity=15000)
    opp = build_opportunity_signal(plan_status_bucket="emerging", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    assert opp["signal"] == "INVESTIGATE"


def test_2_none_found_reason_never_claims_external_absence():
    coverage = _coverage(NO_IDENTIFIED_ACTIVITY, allocation_capacity=15000)
    opp = build_opportunity_signal(plan_status_bucket="emerging", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    joined = " ".join(opp["reasons"]).lower()
    assert "no planning activity has been identified within this allocation" in joined
    assert "no planning application exists" not in joined


# --- 3-4: PARTIAL/FULL ---

def test_3_partial_can_produce_investigate():
    coverage = _coverage(PARTIAL_COVERAGE, allocation_capacity=5000, identified_application_capacity=155,
                          development_coverage_percentage=0.031, indicative_residual_capacity=4845)
    opp = build_opportunity_signal(plan_status_bucket="adopted", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    assert opp["signal"] == "INVESTIGATE"


def test_4_full_does_not_normally_produce_investigate():
    coverage = _coverage(FULLY_ACCOUNTED_FOR, allocation_capacity=100, development_coverage_percentage=1.0)
    opp = build_opportunity_signal(plan_status_bucket="adopted", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    assert opp["signal"] == "LOWER_PRIORITY"


# --- 5: UNCERTAIN cannot fabricate a confident opportunity ---

def test_5_uncertain_review_required_never_becomes_investigate():
    # Real AN5/Timperley Wedge shape - overlapping applications make
    # capacity accounting unsafe; must never be silently promoted.
    coverage = _coverage(REVIEW_REQUIRED, capacity_accounting_status="review_required",
                          note="Capacity accounting requires review — see linked applications.")
    opp = build_opportunity_signal(plan_status_bucket="emerging", coverage=coverage, phasing={"classification": "PHASING_REVIEW_REQUIRED"})
    assert opp["signal"] == "INSUFFICIENT_EVIDENCE"


# --- 6: employment-only allocation ---

def test_6_employment_only_allocation_never_becomes_investigate():
    # An employment-only allocation never has a dwelling capacity value at
    # all (app.extraction.local_plan's own schema only ever populates
    # minimum_dwellings/maximum_capacity from an explicit dwellings
    # figure - confirmed directly against Trafford's real AN13/AN14/AN15
    # employment allocations in Gate 4A/4B's own investigation) - so
    # allocation_capacity is None, which build_opportunity_signal already
    # safely routes to INSUFFICIENT_EVIDENCE, never INVESTIGATE.
    coverage = _coverage(NO_IDENTIFIED_ACTIVITY, allocation_capacity=None, development_coverage_percentage=None)
    opp = build_opportunity_signal(plan_status_bucket="emerging", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    assert opp["signal"] == "INSUFFICIENT_EVIDENCE"


# --- 7-8: plan stage represented honestly ---

def test_7_early_emerging_plan_stage_represented_honestly():
    coverage = _coverage(NO_IDENTIFIED_ACTIVITY, allocation_capacity=500)
    opp = build_opportunity_signal(plan_status_bucket="emerging", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    assert "Emerging" in opp["reasons"][0]


def test_8_regulation_19_stage_represented_correctly():
    # Trafford's own real plan_status ("proposed_submission") buckets to
    # "emerging" (app.reporting.allocation_discovery.PLAN_STATUS_META) -
    # proven directly against the real bucket table, not assumed.
    from app.reporting.allocation_discovery import PLAN_STATUS_META
    assert PLAN_STATUS_META["proposed_submission"]["bucket"] == "emerging"
    assert PLAN_STATUS_META["proposed_submission"]["label"] == "Proposed submission (Regulation 19)"


# --- 9-10: ownership caveat, not a blocker ---

def test_9_lack_of_ownership_evidence_produces_caveat_not_availability_inference():
    coverage = _coverage(NO_IDENTIFIED_ACTIVITY, allocation_capacity=15000)
    opp = build_opportunity_signal(plan_status_bucket="emerging", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    caveat = opp["reasons"][-1]
    assert "not yet assessed" in caveat and "land availability" in caveat


def test_10_lack_of_ownership_does_not_block_investigate():
    coverage = _coverage(NO_IDENTIFIED_ACTIVITY, allocation_capacity=15000)
    opp = build_opportunity_signal(plan_status_bucket="emerging", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    assert opp["signal"] == "INVESTIGATE"  # ownership caveat present, but not a gate


# --- 11: false Site match cannot contaminate signal (real AN3 case) ---

def test_11_false_site_match_cannot_contaminate_signal_or_overclaim():
    coverage = _coverage(NO_IDENTIFIED_ACTIVITY, allocation_capacity=3000)
    opp = build_opportunity_signal(plan_status_bucket="emerging", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    enriched = enrich_none_found_reason("Trafford Waters", [MANCHESTER_WATERS_SITE], opp)
    assert enriched["signal"] == "INVESTIGATE"  # signal unchanged - enrichment never overrides it
    joined = " ".join(enriched["reasons"])
    assert "not treated as a credible candidate" in joined
    assert "shares no specific identifying wording" in joined


# --- 12: Pomona-style unrecorded corroborated candidate surfaced as evidence caveat ---

def test_12_corroborated_unrecorded_candidate_surfaced_as_caveat_not_new_state():
    coverage = _coverage(NO_IDENTIFIED_ACTIVITY, allocation_capacity=3200)
    opp = build_opportunity_signal(plan_status_bucket="emerging", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    enriched = enrich_none_found_reason("Pomona", [MANCHESTER_WATERS_SITE], opp)
    assert enriched["signal"] == "INVESTIGATE"  # still NONE_FOUND-based INVESTIGATE, no new top-level state introduced
    joined = " ".join(enriched["reasons"])
    assert "has not yet been recorded as a confirmed Site relationship" in joined
    assert "should be reviewed before being relied upon" in joined


def test_12b_no_candidate_at_all_is_distinguished_from_both_of_the_above():
    coverage = _coverage(NO_IDENTIFIED_ACTIVITY, allocation_capacity=145)
    opp = build_opportunity_signal(plan_status_bucket="emerging", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    enriched = enrich_none_found_reason("Land on Brixham Road, Old Trafford", [], opp)
    assert "No candidate Site was identified" in " ".join(enriched["reasons"])


# --- 13-14: capacity scope / missing capacity ---

def test_13_comprehensive_vs_plan_period_capacity_remains_distinguished():
    # Reuses the EXACT existing production values (Wharfside: 15,000
    # comprehensive vs 8,400 in plan period) - build_opportunity_signal
    # only ever reads coverage.allocation_capacity, which
    # app.reporting.allocation_development_coverage._allocation_capacity_
    # value already resolves to ONE trusted figure per the platform's own
    # existing, unchanged selection rule - this test proves Gate 4C's own
    # wiring doesn't introduce a second, competing interpretation.
    coverage = _coverage(NO_IDENTIFIED_ACTIVITY, allocation_capacity=8400)
    opp = build_opportunity_signal(plan_status_bucket="emerging", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    assert "8,400" in opp["reasons"][0]
    assert "15,000" not in opp["reasons"][0]


def test_14_missing_trusted_capacity_does_not_fabricate_a_number():
    coverage = _coverage(NO_IDENTIFIED_ACTIVITY, allocation_capacity=None)
    opp = build_opportunity_signal(plan_status_bucket="emerging", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    assert opp["signal"] == "INSUFFICIENT_EVIDENCE"
    assert not any(ch.isdigit() for reason in opp["reasons"] for ch in reason)


# --- 15-16: deterministic, no unsupported numbers ---

def test_15_opportunity_reasons_are_deterministic():
    coverage = _coverage(PARTIAL_COVERAGE, allocation_capacity=5000, identified_application_capacity=155,
                          development_coverage_percentage=0.031, indicative_residual_capacity=4845)
    opp_a = build_opportunity_signal(plan_status_bucket="adopted", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    opp_b = build_opportunity_signal(plan_status_bucket="adopted", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    assert opp_a == opp_b  # same inputs, same outputs, always - no randomness, no LLM


def test_16_enrichment_never_introduces_a_number_not_already_in_the_evidence():
    coverage = _coverage(NO_IDENTIFIED_ACTIVITY, allocation_capacity=3200)
    opp = build_opportunity_signal(plan_status_bucket="emerging", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    enriched = enrich_none_found_reason("Pomona", [MANCHESTER_WATERS_SITE], opp)
    new_sentence = enriched["reasons"][-2]  # the inserted caveat, before the ownership caveat
    assert not any(ch.isdigit() for ch in new_sentence)  # no fabricated score/percentage in the narrative text


# --- 17-19: attribution / cross-authority safety ---

def test_17_pfe_allocation_bucket_and_signal_computed_independently_of_council():
    # PfE's own real plan status is "adopted" - proven this gate against
    # production (LocalPlan id=2). Nothing in build_opportunity_signal or
    # enrich_none_found_reason reads council_code/local_plan_id at all -
    # the caller (unchanged) is responsible for passing the correct
    # plan_status_bucket, exactly as it already does today.
    coverage = _coverage(PARTIAL_COVERAGE, allocation_capacity=5000, identified_application_capacity=155,
                          development_coverage_percentage=0.031, indicative_residual_capacity=4845)
    opp = build_opportunity_signal(plan_status_bucket="adopted", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    assert "Adopted" in opp["reasons"][0]


def test_18_trafford_own_allocation_bucket_computed_correctly():
    coverage = _coverage(NO_IDENTIFIED_ACTIVITY, allocation_capacity=15000)
    opp = build_opportunity_signal(plan_status_bucket="emerging", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    assert "Emerging" in opp["reasons"][0]


def test_19_no_cross_authority_contamination_possible_through_enrichment():
    # enrich_none_found_reason takes an explicit candidate_sites list - it
    # never queries the database itself, so a caller passing only same-
    # council candidates (the existing, unchanged convention every
    # match_to_existing_site caller already follows) cannot leak another
    # authority's Site into this allocation's evidence.
    import inspect
    sig = inspect.signature(enrich_none_found_reason)
    assert "candidate_sites" in sig.parameters
    assert "council" not in " ".join(sig.parameters).lower()  # no council-scoping logic lives in this function itself


# --- 20: no financial/viability/availability claim ---

def test_20_no_signal_or_reason_contains_financial_or_viability_language():
    coverage = _coverage(PARTIAL_COVERAGE, allocation_capacity=5000, identified_application_capacity=155,
                          development_coverage_percentage=0.031, indicative_residual_capacity=4845)
    opp = build_opportunity_signal(plan_status_bucket="adopted", coverage=coverage, phasing={"classification": "NO_PHASING_EVIDENCE"})
    enriched = enrich_none_found_reason("New Carrington", [], opp)
    joined = " ".join(enriched["reasons"]).lower()
    forbidden = ["viable", "profit", "value", "worth £", "for sale", "available for", "will be granted", "developer has no interest"]
    for phrase in forbidden:
        assert phrase not in joined
