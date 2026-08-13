"""Salford + Trafford Regulation 19 Local Plan Allocation Ingestion task -
INVESTIGATE phase. This task made no code changes to the ingestion
pipeline, extraction schema, or database models - the only new artefact is
the config/policy_sources.yaml registration for both councils (Section 7).
These tests lock the two things that are genuinely new/at risk:

1. The Salford and Trafford source entries parse and register correctly
   through the EXISTING app.policy.sources architecture, without disturbing
   the pre-existing Stockport/Bury entries (Section 7's explicit
   constraint).
2. The specific Regulation 19 status wording these two councils' documents
   actually use maps, through the EXISTING app.policy.status architecture,
   to "proposed_submission_allocation" - never "adopted_allocation" -
   which is Section 4's central data-safety requirement for this task.

No schema change, no new ingestion module, no new status vocabulary was
introduced - see the task's own Section 6 constraint against doing so.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.db.models import MonitoredSource
from app.policy.sources import load_source_config, register_sources_for_council
from app.policy.status import derive_allocation_status_from_plan_status, normalise_plan_status

REAL_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "policy_sources.yaml"


def _real_config() -> dict:
    return load_source_config(REAL_CONFIG_PATH)


def test_salford_source_config_is_registered_with_correct_types():
    config = _real_config()
    salford = config["councils"]["salford"]["sources"]
    assert len(salford) == 2

    landing = next(s for s in salford if s["source_type"] == "landing_page")
    assert "salford.gov.uk" in landing["url"]
    assert "plan_name" not in landing or landing.get("plan_name") is None

    plan_doc = next(s for s in salford if s["source_type"] == "emerging_plan")
    assert plan_doc["url"].endswith(".pdf")
    assert plan_doc["plan_name"] == "Salford Local Plan: Core Strategy and Allocations"


def test_trafford_source_config_is_registered_with_correct_types():
    config = _real_config()
    trafford = config["councils"]["trafford"]["sources"]
    assert len(trafford) == 2

    landing = next(s for s in trafford if s["source_type"] == "landing_page")
    assert "trafford.gov.uk" in landing["url"]

    plan_doc = next(s for s in trafford if s["source_type"] == "emerging_plan")
    assert plan_doc["url"].endswith(".pdf")
    assert plan_doc["plan_name"] == "Trafford Local Plan"


def test_stockport_and_bury_source_config_unchanged_by_this_task():
    config = _real_config()
    stockport = config["councils"]["stockport"]["sources"]
    bury = config["councils"]["bury"]["sources"]
    assert len(stockport) == 2
    assert len(bury) == 3
    assert {s["source_type"] for s in stockport} == {"emerging_plan", "policies_map"}
    assert {s["source_type"] for s in bury} == {"landing_page", "emerging_plan", "adopted_plan"}


def test_salford_and_trafford_register_without_a_local_plan_existing_yet(session):
    config = _real_config()
    salford_sources = register_sources_for_council(session, "salford", config=config)
    trafford_sources = register_sources_for_council(session, "trafford", config=config)

    assert len(salford_sources) == 2
    assert len(trafford_sources) == 2
    # Neither council has had its Regulation 19 plan ingested in this
    # task (INVESTIGATE only) - both plan-tied sources must resolve to no
    # LocalPlan yet, exactly like Bury's did before Bury was first onboarded.
    assert all(s.local_plan_id is None for s in salford_sources)
    assert all(s.local_plan_id is None for s in trafford_sources)


def test_registering_salford_and_trafford_does_not_disturb_bury_or_stockport(session):
    config = _real_config()
    bury_before = register_sources_for_council(session, "bury", config=config)
    stockport_before = register_sources_for_council(session, "stockport", config=config)

    register_sources_for_council(session, "salford", config=config)
    register_sources_for_council(session, "trafford", config=config)

    bury_after = session.execute(select(MonitoredSource).where(MonitoredSource.council_code == "bury")).scalars().all()
    stockport_after = session.execute(select(MonitoredSource).where(MonitoredSource.council_code == "stockport")).scalars().all()

    assert {s.id for s in bury_after} == {s.id for s in bury_before}
    assert {s.id for s in stockport_after} == {s.id for s in stockport_before}
    assert len(bury_after) == 3
    assert len(stockport_after) == 2


def test_regulation_19_raw_status_maps_to_proposed_submission_never_adopted():
    # The exact raw-status wording both documents actually use (confirmed
    # via direct primary-source reading during this task's investigation):
    # Salford's own consultation page calls it "Publication Local Plan
    # consultation (August 2026 to September 2026)"; Trafford's calls it
    # "Regulation 19 Publication Stage". Both must land on the same
    # pre-Reg19-adoption allocation status.
    for raw_status in (
        "Regulation 19 Publication (July 2026)",
        "Publication Local Plan consultation (August 2026 to September 2026)",
        "Regulation 19 Publication Stage",
    ):
        plan_status = normalise_plan_status(raw_status)
        assert plan_status == "proposed_submission", raw_status
        assert plan_status != "adopted"

        allocation_status, _note = derive_allocation_status_from_plan_status(raw_status)
        assert allocation_status == "proposed_submission_allocation", raw_status
        assert allocation_status != "adopted_allocation"


def test_regulation_19_never_derives_adopted_even_with_adopted_flag_choice():
    # ingest_local_plan.py's --plan-status flag only accepts
    # draft/emerging/examination/adopted (never free text) - if a future
    # ingestion run for Salford/Trafford were mistakenly invoked with
    # --plan-status adopted (instead of the correct "emerging"), the
    # allocation status derivation must still refuse to label allocations
    # "adopted_allocation" outright, per Section 4/module docstring intent.
    allocation_status, note = derive_allocation_status_from_plan_status("adopted")
    assert allocation_status == "submitted_allocation"
    assert allocation_status != "adopted_allocation"
    assert "not independently confirmed" in note


# ---------------------------------------------------------------------------
# FINAL PRE-MERGE DATA AMENDMENT - the Product-Owner-locked proposed dataset
# (dry-run only, never written to production by these tests). Field names
# match app.db.models.LocalPlanSite exactly. This is a plain data fixture,
# not a new ingestion path - nothing here is imported or executed by
# ingest_local_plan.py; it exists solely so the two amended product
# decisions below have an executable, versioned specification instead of
# living only in a chat transcript:
#
# 1. Trafford's own Regulation 19 document states "22 allocations" (para
#    15.2) while its own Table of Contents and Table 15-1 identify exactly
#    21 - exhaustively investigated, no reconciling explanation found.
#    Product Owner decision: proceed on the evidenced 21, record the
#    mismatch as a non-blocking, explicit source discrepancy - never
#    fabricate a 22nd record.
# 2. Salford Allocation 2 (~35 gypsy/traveller pitches) must never write a
#    pitch count into a dwelling-capacity field, and must not have that
#    figure smuggled into an unrelated field (category) either. With no
#    schema field semantically correct for a non-dwelling capacity figure,
#    the row relies purely on source_document_url/source_page/
#    policy_reference/site_name for provenance - the pitch figure itself is
#    not persisted anywhere on the row. A capacity_value/capacity_unit pair
#    is noted as a future schema backlog item only.
TRAFFORD_SOURCE_DISCREPANCY_NOTE = (
    "Trafford Regulation 19 paragraph 15.2 states 22 allocations, while the "
    "plan's authoritative allocation schedule and policy sequence identify "
    "21. PropertyAIgent records the 21 identifiable allocations and retains "
    "the discrepancy for manual review."
)

FINAL_SALFORD_ALLOCATIONS = [
    {"policy_reference": "Development allocation 1", "site_name": "Cheltenham Crescent, Kersal and Broughton Park",
     "category": "SS3B Part B) - Kersal and Broughton Park", "intended_use": "residential",
     "minimum_dwellings": 20, "indicative_capacity": None, "maximum_capacity": None,
     "source_page": 38, "manual_review": None},
    {"policy_reference": "Development allocation 2", "site_name": "Land at Duchy Road, Pendleton and Charlestown",
     "category": "SS3D Part B) - Pendleton and Charlestown", "intended_use": "gypsy_traveller_accommodation",
     "minimum_dwellings": None, "indicative_capacity": None, "maximum_capacity": None,
     "source_page": 48, "manual_review": "needs_confirmation"},
    {"policy_reference": "Development allocation 3", "site_name": "Orchard Street, Pendleton and Charlestown",
     "category": "SS3D Part B) - Pendleton and Charlestown", "intended_use": "residential",
     "minimum_dwellings": 470, "indicative_capacity": None, "maximum_capacity": None,
     "source_page": 50, "manual_review": None},
    {"policy_reference": "Development allocation 4", "site_name": "Land east of Langley Road and south of Agecroft Cemetery, Pendleton and Charlestown",
     "category": "SS3D Part B) - Pendleton and Charlestown", "intended_use": "residential",
     "minimum_dwellings": 100, "indicative_capacity": None, "maximum_capacity": None,
     "source_page": 52, "manual_review": None},
    {"policy_reference": "Development allocation 5", "site_name": "East of Langley Road, Pendleton and Charlestown",
     "category": "SS3D Part B) - Pendleton and Charlestown", "intended_use": "residential",
     "minimum_dwellings": 100, "indicative_capacity": None, "maximum_capacity": None,
     "source_page": 54, "manual_review": None},
    {"policy_reference": "Development allocation 6", "site_name": "Land off Hayes Road and Green Lane, Cadishead and Lower Irlam",
     "category": "SS4A Part B) - Cadishead and Lower Irlam", "intended_use": "residential",
     "minimum_dwellings": 160, "indicative_capacity": None, "maximum_capacity": None,
     "source_page": 65, "manual_review": None},
    {"policy_reference": "Development allocation 8", "site_name": "Land north of Rothwell Crescent, Little Hulton",
     "category": "SS4B Part B) - Little Hulton", "intended_use": "residential",
     "minimum_dwellings": 50, "indicative_capacity": None, "maximum_capacity": None,
     "source_page": 71, "manual_review": None},
    {"policy_reference": "Development allocation 9", "site_name": "Fereday Street, Walkden North",
     "category": "SS4B Part B) - Walkden North", "intended_use": "residential",
     "minimum_dwellings": 15, "indicative_capacity": None, "maximum_capacity": None,
     "source_page": 73, "manual_review": None},
    {"policy_reference": "Development allocation 10", "site_name": "Kestrel Avenue / Falcon Drive, Walkden North",
     "category": "SS4B Part B) - Walkden North", "intended_use": "residential",
     "minimum_dwellings": 40, "indicative_capacity": None, "maximum_capacity": None,
     "source_page": 74, "manual_review": None},
    {"policy_reference": "Development allocation 11", "site_name": "Land south of Moss Lane, Walkden North",
     "category": "SS4B Part B) - Walkden North", "intended_use": "residential",
     "minimum_dwellings": 80, "indicative_capacity": None, "maximum_capacity": None,
     "source_page": 76, "manual_review": None},
    {"policy_reference": "Development allocation 12", "site_name": "Land at Ladywell Avenue, Little Hulton",
     "category": "SS4B Part B) - Little Hulton", "intended_use": "residential",
     "minimum_dwellings": 40, "indicative_capacity": None, "maximum_capacity": None,
     "source_page": 78, "manual_review": None},
    {"policy_reference": "Development allocation 13", "site_name": "Aspinall Crescent, Little Hulton",
     "category": "SS4B Part B) - Little Hulton", "intended_use": "residential",
     "minimum_dwellings": 45, "indicative_capacity": None, "maximum_capacity": None,
     "source_page": 79, "manual_review": None},
    {"policy_reference": "Development allocation 14", "site_name": "Crescent Drive, Walkden North",
     "category": "SS4B Part B) - Walkden North", "intended_use": "residential",
     "minimum_dwellings": 10, "indicative_capacity": None, "maximum_capacity": None,
     "source_page": 81, "manual_review": None},
    {"policy_reference": "Development allocation 15", "site_name": "Former St Ambrose Barlow High School, Swinton and Wardley",
     "category": "SS4C Part B) - Swinton and Wardley", "intended_use": "residential",
     "minimum_dwellings": 130, "indicative_capacity": None, "maximum_capacity": None,
     "source_page": 86, "manual_review": None},
    {"policy_reference": "Development allocation 16", "site_name": "Little Moss and Wyndam Avenue, Pendlebury and Clifton",
     "category": "SS4B Part B) - Pendlebury and Clifton", "intended_use": "residential",
     "minimum_dwellings": 65, "indicative_capacity": None, "maximum_capacity": None,
     "source_page": 88, "manual_review": None},
]

FINAL_TRAFFORD_ALLOCATIONS = [
    {"policy_reference": "AN1", "site_name": "Wharfside", "intended_use": "mixed_use",
     "minimum_dwellings": 8400, "indicative_capacity": None, "maximum_capacity": 15000, "source_page": 294},
    {"policy_reference": "AN2", "site_name": "Civic Quarter", "intended_use": "mixed_use",
     "minimum_dwellings": 4000, "indicative_capacity": None, "maximum_capacity": None, "source_page": 313},
    {"policy_reference": "AN3", "site_name": "Trafford Waters", "intended_use": "mixed_use",
     "minimum_dwellings": 3000, "indicative_capacity": None, "maximum_capacity": None, "source_page": 325},
    {"policy_reference": "AN4", "site_name": "Pomona", "intended_use": "mixed_use",
     "minimum_dwellings": 1950, "indicative_capacity": None, "maximum_capacity": 3200, "source_page": 331},
    {"policy_reference": "AN5", "site_name": "Site of the former Stretford Mall, Chester Road, Stretford", "intended_use": "mixed_use",
     "minimum_dwellings": 750, "indicative_capacity": None, "maximum_capacity": None, "source_page": 336},
    {"policy_reference": "AN6", "site_name": "Land west of Skerton Road, Old Trafford", "intended_use": "residential",
     "minimum_dwellings": 540, "indicative_capacity": None, "maximum_capacity": None, "source_page": 341},
    {"policy_reference": "AN7", "site_name": "499 Chester Road, Old Trafford", "intended_use": "residential",
     "minimum_dwellings": 285, "indicative_capacity": None, "maximum_capacity": None, "source_page": 345},
    {"policy_reference": "AN8", "site_name": "88-118 Chorlton Road, Old Trafford", "intended_use": "residential",
     "minimum_dwellings": 188, "indicative_capacity": None, "maximum_capacity": None, "source_page": 348},
    {"policy_reference": "AN9", "site_name": "Land on Brixham Road, Old Trafford", "intended_use": "residential",
     "minimum_dwellings": 145, "indicative_capacity": None, "maximum_capacity": None, "source_page": 351},
    {"policy_reference": "AN10", "site_name": "Lacy Street, Stretford", "intended_use": "residential",
     "minimum_dwellings": 52, "indicative_capacity": None, "maximum_capacity": None, "source_page": 354},
    {"policy_reference": "AN11", "site_name": "Empress Mill, Former Trafford Press, Veno Building and Adjacent Land", "intended_use": "residential",
     "minimum_dwellings": 146, "indicative_capacity": None, "maximum_capacity": None, "source_page": 357},
    {"policy_reference": "AN12", "site_name": "Land at Thomas Street, Stretford", "intended_use": "residential",
     "minimum_dwellings": 180, "indicative_capacity": None, "maximum_capacity": None, "source_page": 360},
    {"policy_reference": "AS1", "site_name": "Land at Oakfield Road, Altrincham", "intended_use": "mixed_use",
     "minimum_dwellings": 100, "indicative_capacity": None, "maximum_capacity": None, "source_page": 370},
    {"policy_reference": "AS2", "site_name": "Land at New Street, Altrincham", "intended_use": "residential",
     "minimum_dwellings": 88, "indicative_capacity": None, "maximum_capacity": None, "source_page": 373},
    {"policy_reference": "AS3", "site_name": "Land at Moss Lane, Balmoral Road, Altrincham", "intended_use": "residential",
     "minimum_dwellings": 60, "indicative_capacity": None, "maximum_capacity": None, "source_page": 376},
    {"policy_reference": "AC1", "site_name": "Land at Stanley Square, Sale", "intended_use": "residential",
     "minimum_dwellings": 75, "indicative_capacity": None, "maximum_capacity": None, "source_page": 383},
    {"policy_reference": "AC2", "site_name": "Land at Sale Lido / Oaklands Drive, Sale", "intended_use": "residential",
     "minimum_dwellings": 50, "indicative_capacity": None, "maximum_capacity": None, "source_page": 387},
]

TRAFFORD_EMPLOYMENT_EXCLUDED = ("AN13", "AN14", "AN15", "AS4")  # not in FINAL_TRAFFORD_ALLOCATIONS


def test_final_salford_dataset_has_exactly_fifteen_qualifying_allocations():
    assert len(FINAL_SALFORD_ALLOCATIONS) == 15
    refs = [a["policy_reference"] for a in FINAL_SALFORD_ALLOCATIONS]
    assert len(refs) == len(set(refs))
    assert "Development allocation 7" not in refs  # employment-only, excluded


def test_salford_allocation_2_dwelling_capacity_fields_are_all_null():
    allocation_2 = next(a for a in FINAL_SALFORD_ALLOCATIONS if a["policy_reference"] == "Development allocation 2")
    assert allocation_2["minimum_dwellings"] is None
    assert allocation_2["indicative_capacity"] is None
    assert allocation_2["maximum_capacity"] is None
    # The pitch count must not be smuggled into category either - category
    # stays a clean policy/neighbourhood classification, matching every
    # other Salford row's category shape exactly (no digits, no "pitch").
    assert "pitch" not in allocation_2["category"].lower()
    assert "35" not in allocation_2["category"]
    assert allocation_2["category"] == "SS3D Part B) - Pendleton and Charlestown"
    # intended_use IS the semantically correct field for what the site is
    # allocated for - using it here is not a capacity workaround.
    assert allocation_2["intended_use"] == "gypsy_traveller_accommodation"
    assert allocation_2["manual_review"] == "needs_confirmation"


def test_salford_categories_are_all_semantically_clean_policy_headings():
    # Every Salford category is "<neighbourhood policy code> Part B) -
    # <neighbourhood name>" - policy codes like "SS3B"/"SS4A" legitimately
    # contain digits, but no category should ever carry a capacity figure
    # (a dwelling/pitch count) - that's exactly the workaround Allocation 2
    # must not use, checked here for every row, not just Allocation 2.
    for allocation in FINAL_SALFORD_ALLOCATIONS:
        assert "Part B)" in allocation["category"]
        assert "pitch" not in allocation["category"].lower()
        assert "dwelling" not in allocation["category"].lower()
        assert "house" not in allocation["category"].lower()


def test_final_trafford_dataset_has_exactly_seventeen_qualifying_allocations():
    assert len(FINAL_TRAFFORD_ALLOCATIONS) == 17
    refs = {a["policy_reference"] for a in FINAL_TRAFFORD_ALLOCATIONS}
    assert len(refs) == 17
    # 17 qualifying + 4 employment-excluded = 21 evidenced allocations -
    # never 22 (the unreconciled narrative figure) and never a fabricated
    # AN16/AS5/AC3 code.
    all_referenced = refs | set(TRAFFORD_EMPLOYMENT_EXCLUDED)
    assert len(all_referenced) == 21
    for fabricated in ("AN16", "AS5", "AC3", "AW1"):
        assert fabricated not in all_referenced


def test_trafford_source_discrepancy_note_is_recorded_and_non_blocking():
    assert "22 allocations" in TRAFFORD_SOURCE_DISCREPANCY_NOTE
    assert "21" in TRAFFORD_SOURCE_DISCREPANCY_NOTE
    assert "manual review" in TRAFFORD_SOURCE_DISCREPANCY_NOTE.lower()
    # Non-blocking: the locked dataset still contains all 17 qualifying
    # records - the discrepancy is documented, not gating.
    assert len(FINAL_TRAFFORD_ALLOCATIONS) == 17


def test_final_dataset_known_dwelling_capacity_totals():
    salford_known = [a["minimum_dwellings"] for a in FINAL_SALFORD_ALLOCATIONS if a["minimum_dwellings"] is not None]
    trafford_known = [a["minimum_dwellings"] for a in FINAL_TRAFFORD_ALLOCATIONS if a["minimum_dwellings"] is not None]
    assert len(salford_known) == 14  # 15 qualifying minus Allocation 2 (null)
    assert len(trafford_known) == 17  # all 17 have a known figure
    assert sum(salford_known) == 1325
    assert sum(trafford_known) == 20009
