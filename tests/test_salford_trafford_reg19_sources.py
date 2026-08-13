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
