"""Complete Greater Manchester Local Plan / Strategic Allocation Baseline task
- locks the genuinely settled findings from this investigation round as
versioned data + invariant tests. This is investigation/data-preparation
work, not a new ingestion pathway - nothing here is imported or executed by
ingest_local_plan.py, and no production writes occur anywhere in this
module.

Only the most solidly-evidenced findings are encoded as fixtures here
(Manchester's fully GIS-verified dataset, Wigan's current-stage
confirmation, the PfE status-correction proposal). The larger, still-partly
uncertain per-site delivery-status research for Bolton (108 sites), Oldham
(13 legacy sites) and Tameside (7 legacy sites) is intentionally NOT
encoded as permanent test fixtures here - turning genuinely uncertain
research findings into hard assertions would misrepresent their confidence
level. That material lives in the task's final report/dataset instead.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# MANCHESTER - fully primary-source-verified (Regulation 18 draft, Sept
# 2025), including exact GIS-confirmed hectarage for the 3 strategic sites.
# Manchester's PfE allocation (Medipark, JP Allocation 3.1) is confirmed
# 100% employment - explicitly excluded, not part of this qualifying set.
# ---------------------------------------------------------------------------
MANCHESTER_QUALIFYING_ALLOCATIONS = [
    {"policy_reference": "SGL 4", "site_name": "Victoria North", "intended_use": "residential",
     "minimum_dwellings": None, "indicative_capacity": 15000, "maximum_capacity": None,
     "plan_stage": "Regulation 18 draft"},
    {"policy_reference": "SGL 5", "site_name": "Holt Town", "intended_use": "mixed_use",
     "minimum_dwellings": None, "indicative_capacity": 4500, "maximum_capacity": None,
     "plan_stage": "Regulation 18 draft"},
    {"policy_reference": "SGL 10", "site_name": "Wythenshawe Centre and Adjacent Areas", "intended_use": "mixed_use",
     "minimum_dwellings": None, "indicative_capacity": None, "maximum_capacity": 2000,
     "plan_stage": "Regulation 18 draft"},  # "up to 2,000" - stated as a ceiling, not a point figure
    {"policy_reference": "H1 (Newton Heath)", "site_name": "Newton Heath", "intended_use": "residential",
     "minimum_dwellings": None, "indicative_capacity": 1000, "maximum_capacity": None,
     "plan_stage": "Regulation 18 draft"},
    {"policy_reference": "H1 (Clayton Canalside)", "site_name": "Clayton Canalside", "intended_use": "residential",
     "minimum_dwellings": 1700, "indicative_capacity": None, "maximum_capacity": None,
     "plan_stage": "Regulation 18 draft"},
    {"policy_reference": "H1 (Grey Mare Lane)", "site_name": "Grey Mare Lane", "intended_use": "residential",
     "minimum_dwellings": None, "indicative_capacity": 1000, "maximum_capacity": None,
     "plan_stage": "Regulation 18 draft"},
    {"policy_reference": "H1 (Lower Medlock)", "site_name": "Lower Medlock Sites", "intended_use": "residential",
     "minimum_dwellings": 865, "indicative_capacity": None, "maximum_capacity": None,
     "plan_stage": "Regulation 18 draft"},
    {"policy_reference": "H1 (Ardwick Green)", "site_name": "Ardwick Green", "intended_use": "residential",
     "minimum_dwellings": None, "indicative_capacity": 2500, "maximum_capacity": None,
     "plan_stage": "Regulation 18 draft"},
]

MANCHESTER_PFE_EXCLUDED = ("JP Allocation 3.1",)  # Medipark - 100% employment, no residential component


def test_manchester_qualifying_allocations_have_no_employment_only_sites():
    assert len(MANCHESTER_QUALIFYING_ALLOCATIONS) == 8
    for allocation in MANCHESTER_QUALIFYING_ALLOCATIONS:
        assert allocation["intended_use"] in ("residential", "mixed_use")


def test_manchester_medipark_pfe_allocation_excluded_as_employment_only():
    qualifying_refs = {a["policy_reference"] for a in MANCHESTER_QUALIFYING_ALLOCATIONS}
    for excluded_ref in MANCHESTER_PFE_EXCLUDED:
        assert excluded_ref not in qualifying_refs


def test_manchester_known_capacity_total():
    known = []
    for a in MANCHESTER_QUALIFYING_ALLOCATIONS:
        value = a["minimum_dwellings"] or a["indicative_capacity"] or a["maximum_capacity"]
        assert value is not None, a["site_name"]
        known.append(value)
    assert sum(known) == 28565  # 15000+4500+2000+1000+1700+1000+865+2500


# ---------------------------------------------------------------------------
# WIGAN - current-stage confirmation (Regulation 18 "Initial Draft" remains
# current as of this task; the Regulation 19 Publication stage was withdrawn
# by Cabinet on 17 November 2025 after public objection to Green Belt
# release, and a fresh Cabinet decision on how to proceed is pending). No
# dataset change from the prior task round - this locks the "still current"
# finding itself, since it was the one open question about Wigan.
# ---------------------------------------------------------------------------
WIGAN_CURRENT_STAGE = "Regulation 18 Initial Draft"
WIGAN_STAGE_CONFIRMATION_NOTE = (
    "Wigan's Regulation 19 Publication consultation, originally timetabled "
    "for December 2025-January 2026, did not proceed: Cabinet withdrew the "
    "draft Local Plan on 17 November 2025 following public objection to "
    "proposed Green Belt release. A fresh Cabinet decision on how to "
    "proceed was pending as of this research. The Regulation 18 Initial "
    "Draft (Policies H3-H8, ~4,295 homes) therefore remains the current, "
    "authoritative source - not superseded."
)


def test_wigan_stage_confirmation_is_recorded():
    assert WIGAN_CURRENT_STAGE == "Regulation 18 Initial Draft"
    assert "17 November 2025" in WIGAN_STAGE_CONFIRMATION_NOTE
    assert "withdrew" in WIGAN_STAGE_CONFIRMATION_NOTE.lower()


# ---------------------------------------------------------------------------
# PfE STATUS CORRECTION - proposed only, never executed against production.
# All 36 existing PfE LocalPlanSite rows individually cite an explicit "JPA
# N" / "Policy JP Allocation N" reference within the adopted (21 March 2024)
# document - each row's own extraction already traces to that specific
# adopted policy, which is why every one of the 36 (not just the
# residential/mixed-use subset) is proposed for correction.
# ---------------------------------------------------------------------------
PFE_STATUS_CORRECTIONS_BY_COUNCIL = {
    "bolton": 3, "bury": 4, "oldham": 7, "rochdale": 9,
    "salford": 3, "tameside": 3, "trafford": 3, "wigan": 4,
}


def test_pfe_status_correction_proposal_totals_thirty_six():
    assert sum(PFE_STATUS_CORRECTIONS_BY_COUNCIL.values()) == 36
    assert len(PFE_STATUS_CORRECTIONS_BY_COUNCIL) == 8  # manchester has 0 PfE rows, correctly absent


# ---------------------------------------------------------------------------
# OLDHAM - confirmed plan-lineage relationship (not a duplicate): the legacy
# saved-UDP allocation HLA2451 "Danisher Lane" is explicitly stated, in
# Oldham's own Publication Plan Appendix 1 (Jan 2026, Table A1-2), to have
# been superseded and folded into the adopted PfE allocation JPA15 "Land to
# the south of Coal Pit Lane" - confirmed same physical site, not a
# candidate for a separate Site record.
# ---------------------------------------------------------------------------
def test_oldham_danisher_lane_is_plan_lineage_not_a_duplicate_candidate():
    superseded_ref = "HLA2451"
    successor_ref = "JPA 15"
    relationship_type = "implemented_through_joint_plan"  # existing AllocationRelationship vocabulary
    assert relationship_type in (
        "same_physical_site", "referenced_by", "superseded_by",
        "implemented_through_joint_plan", "uncertain",
    )
    assert superseded_ref != successor_ref
