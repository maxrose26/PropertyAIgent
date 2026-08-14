"""Complete GM Local Plan Baseline - production ingestion runner tests.

Two kinds of coverage here:
1. Tests against the REAL frozen manifests in config/gm_local_plan_baseline/
   (counts, shape, dry-run-only) - these never touch the database beyond
   read-only SELECTs (dry_run=True makes zero mutations by construction).
2. Tests against a small SYNTHETIC manifest (a temp directory, passed via
   the manifest_dir parameter) to exercise the actual write/idempotency/
   rollback/deterministic-targeting logic in isolation, using the existing
   session fixture's "bury"/"stockport" rows - never the real
   207-row manifest, which would be far too heavy for a unit test and
   would require seeding real GM council FK rows.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.db.models import Council, LocalPlan, LocalPlanSite
from app.policy import gm_baseline_ingestion as gbi
from app.policy.gm_baseline_ingestion import (
    EXPECTED_FINAL_COUNT,
    EXPECTED_NEW_COUNT,
    EXPECTED_UPDATE_COUNT,
    STRING_COLUMN_LENGTHS,
    ingest_gm_baseline,
    load_manifest,
    resolve_update_target,
    validate_new_rows,
    validate_update_rows,
)

# ---------------------------------------------------------------------------
# Real frozen manifest - counts, shape, no-OpenAI-dependency
# ---------------------------------------------------------------------------


def test_real_manifest_recognises_207_new_rows():
    rows = load_manifest(gbi.NEW_SITES_FILE)
    assert len(rows) == 207 == EXPECTED_NEW_COUNT


def test_real_manifest_recognises_38_updates():
    updates = load_manifest(gbi.UPDATES_FILE)
    assert len(updates) == 38 == EXPECTED_UPDATE_COUNT
    pfe_corrections = [u for u in updates if u["update_type"] == "pfe_status_correction"]
    assert len(pfe_corrections) == 36
    assert any(u["update_type"] == "council_reattribution" for u in updates)
    assert any(u["update_type"] == "capacity_and_use_correction" for u in updates)


def test_real_manifest_new_rows_pass_model_constraint_validation():
    rows = load_manifest(gbi.NEW_SITES_FILE)
    problems = validate_new_rows(rows)
    assert problems == []


def test_real_manifest_updates_pass_model_constraint_validation():
    updates = load_manifest(gbi.UPDATES_FILE)
    problems = validate_update_rows(updates)
    assert problems == []


def test_string_column_lengths_derived_from_model_metadata_match_known_schema():
    # Locks in the exact LocalPlanSite VARCHAR limits this hotfix validates
    # against - if a future migration changes any of these, this test (not
    # a silent StringDataRightTruncation in production) is what should
    # break first.
    assert STRING_COLUMN_LENGTHS == {
        "council_code": 50,
        "policy_reference": 50,
        "site_name": 300,
        "intended_use": 200,
        "category": 300,
        "allocation_status": 50,
        "raw_allocation_status": 300,
        "plan_name": 300,
        "plan_status": 50,
        "source_document_url": 500,
        "confirmed_by": 100,
        "review_status": 30,
        "duplicate_classification": 30,
        "progression_signal": 20,
    }


def test_oldham_plan_status_fix_preserved_all_12_rows_with_shortened_value():
    # Regression guard for the exact bug that broke the earlier production
    # attempt: 12 Oldham rows had plan_stage = "Adopted (saved UDP,
    # expiring at Local Plan adoption ~Spring 2027)" (65 chars), which
    # overflowed plan_status (String(50)) only after being derived via
    # LocalPlan.raw_status. The fix must be a semantic shortening, not a
    # dropped row - still 12 Oldham rows, still recognisably "Adopted
    # (saved UDP)", never truncated mid-word.
    rows = load_manifest(gbi.NEW_SITES_FILE)
    oldham_rows = [r for r in rows if r["council"] == "oldham"]
    assert len(oldham_rows) == 12
    stages = {r.get("plan_stage") for r in oldham_rows}
    assert stages == {"Adopted (saved UDP)"}
    assert len("Adopted (saved UDP)") <= STRING_COLUMN_LENGTHS["plan_status"]


def test_expected_final_count_is_287():
    assert EXPECTED_FINAL_COUNT == 80 + 207 == 287


def test_module_has_no_openai_dependency():
    import app.policy.gm_baseline_ingestion as module
    source = open(module.__file__, encoding="utf-8").read()
    assert "import openai" not in source.lower()
    assert "OpenAI()" not in source
    assert "from openai" not in source.lower()


def test_relationship_and_ah_sidecar_manifests_are_never_loaded_by_this_module():
    import app.policy.gm_baseline_ingestion as module
    source = open(module.__file__, encoding="utf-8").read()
    # The module must reference these filenames only in comments/constants
    # explaining they're skipped, never pass them to load_manifest.
    assert 'load_manifest("gm_local_plan_relationship_review.json"' not in source
    assert 'load_manifest("gm_local_plan_ah_sidecar.json"' not in source
    assert "gm_local_plan_relationship_review.json" in source  # mentioned, but only as "not loaded"
    assert "gm_local_plan_ah_sidecar.json" in source


def test_dry_run_against_real_manifest_makes_zero_mutations(session):
    before = session.execute(select(LocalPlanSite)).scalars().all()
    before_plans = session.execute(select(LocalPlan)).scalars().all()

    result = ingest_gm_baseline(session, dry_run=True)

    after = session.execute(select(LocalPlanSite)).scalars().all()
    after_plans = session.execute(select(LocalPlan)).scalars().all()
    assert len(after) == len(before)
    assert len(after_plans) == len(before_plans)
    assert result["dry_run"] is True
    assert result["created"] == 0
    assert result["updated"] == 0


def test_dry_run_against_real_manifest_reports_create_and_update_totals(session):
    result = ingest_gm_baseline(session, dry_run=True)
    assert result["create"]["total"] == 207
    assert result["update"]["total"] == 38
    assert result["update"]["pfe_status_corrections"] == 36
    assert result["update"]["medipark_correction"] is True
    assert result["update"]["heywood_pilsworth_correction"] is True
    assert sum(result["create"]["by_council"].values()) == 207


def test_manual_review_and_excluded_are_reported_but_not_gating(session):
    result = ingest_gm_baseline(session, dry_run=True)
    # Reported for visibility...
    assert result["skipped_review_only"]["manual_review"] == 6
    assert result["skipped_review_only"]["excluded"] == 18
    # ...but every one of the 207 create-candidates is still counted -
    # nothing was silently dropped because of a manual-review flag embedded
    # on individual rows.
    assert result["create"]["total"] == 207


def test_relationships_and_ah_sidecar_reported_as_not_loaded(session):
    result = ingest_gm_baseline(session, dry_run=True)
    assert "not_loaded_by_this_module" in result["skipped_review_only"]["relationships"]
    assert "not_loaded_by_this_module" in result["skipped_review_only"]["ah_sidecar"]


def test_baseline_mismatch_against_real_manifest_is_not_ready(session):
    # The in-memory test session starts empty (0 rows), which genuinely
    # mismatches the manifest's assumed baseline of 80 - this IS the
    # fail-closed path, exercised naturally without needing to fabricate it.
    result = ingest_gm_baseline(session, dry_run=True)
    assert result["baseline"]["actual"] == 0
    assert result["baseline"]["matches"] is False
    assert result["ready"] is False


def test_production_mode_raises_before_any_write_on_baseline_mismatch(session):
    with pytest.raises(RuntimeError, match="aborted before any write"):
        ingest_gm_baseline(session, dry_run=False)
    assert session.execute(select(LocalPlanSite)).scalars().all() == []


# ---------------------------------------------------------------------------
# Synthetic manifest - exercises actual writes, idempotency, deterministic
# update targeting, and rollback in isolation.
# ---------------------------------------------------------------------------


@pytest.fixture()
def synthetic_manifest_dir(tmp_path):
    new_sites = [
        {"council": "bury", "plan_name": "Test Local Plan", "plan_stage": "Regulation 18 draft",
         "policy_reference": "REF1", "site_name": "Site One", "category": None, "intended_use": "residential",
         "allocation_status": "draft_allocation", "raw_allocation_status": "Regulation 18",
         "minimum_dwellings": 50, "indicative_capacity": None, "maximum_capacity": None,
         "source_document_url": "https://example.invalid/plan.pdf", "source_page": 1,
         "review_status": "auto_applied"},
        {"council": "stockport", "plan_name": "Other Local Plan", "plan_stage": "Regulation 19 Publication",
         "policy_reference": "REF2", "site_name": "Site Two", "category": None, "intended_use": "mixed_use",
         "allocation_status": "proposed_submission_allocation", "raw_allocation_status": "Regulation 19",
         "minimum_dwellings": 100, "indicative_capacity": None, "maximum_capacity": None,
         "source_document_url": "https://example.invalid/plan2.pdf", "source_page": 5,
         "review_status": "needs_confirmation"},
    ]
    updates = [
        {"update_type": "pfe_status_correction", "council": "bury",
         "plan_name": "Places for Everyone Joint Development Plan (Bury allocations)",
         "policy_reference": "JPA 99", "field": "allocation_status",
         "from_value": "submitted_allocation", "to_value": "adopted_allocation",
         "evidence": "test fixture", "review_status": "needs_confirmation"},
    ]
    for name, data in (
        (gbi.NEW_SITES_FILE, new_sites),
        (gbi.UPDATES_FILE, updates),
        (gbi.MANUAL_REVIEW_FILE, []),
        (gbi.EXCLUDED_FILE, []),
    ):
        (tmp_path / name).write_text(json.dumps(data), encoding="utf-8")
    return tmp_path


def _seed_pfe_target(session):
    # "bury"/"stockport" are real council codes (config/councils.yaml) used
    # by the synthetic manifest above - the session fixture only pre-seeds
    # "testcouncil"/"othercouncil", so add real Council rows here too.
    for code, name in (("bury", "Bury"), ("stockport", "Stockport")):
        if session.get(Council, code) is None:
            session.add(Council(code=code, name=name, base_url="https://example.invalid",
                                 date_field_mode="received", doc_system="idox"))

    plan = LocalPlan(council_code="bury", plan_name="Places for Everyone Joint Development Plan (Bury allocations)",
                      plan_version="2022-2039", status="adopted", raw_status="Adopted (with effect from 21 March 2024)")
    session.add(plan)
    session.flush()
    row = LocalPlanSite(council_code="bury", local_plan_id=plan.id, policy_reference="JPA 99",
                         site_name="Test PfE Site", plan_name=plan.plan_name, plan_status="adopted",
                         allocation_status="submitted_allocation")
    session.add(row)
    session.commit()
    return row


def test_synthetic_dry_run_zero_mutations(session, synthetic_manifest_dir):
    _seed_pfe_target(session)
    before_count = len(session.execute(select(LocalPlanSite)).scalars().all())

    result = ingest_gm_baseline(session, manifest_dir=synthetic_manifest_dir, dry_run=True)

    after_count = len(session.execute(select(LocalPlanSite)).scalars().all())
    assert after_count == before_count
    assert result["created"] == 0


def test_synthetic_production_write_creates_and_updates(session, synthetic_manifest_dir, monkeypatch):
    _seed_pfe_target(session)
    monkeypatch.setattr(gbi, "EXPECTED_BASELINE_COUNT", 1)  # matches the 1 seeded row

    result = ingest_gm_baseline(session, manifest_dir=synthetic_manifest_dir, dry_run=False)

    assert result["ready"] is True
    assert result["created"] == 2
    assert result["updated"] == 1

    site1 = session.execute(select(LocalPlanSite).where(LocalPlanSite.policy_reference == "REF1")).scalar_one()
    assert site1.council_code == "bury"
    assert site1.minimum_dwellings == 50
    site2 = session.execute(select(LocalPlanSite).where(LocalPlanSite.policy_reference == "REF2")).scalar_one()
    assert site2.council_code == "stockport"

    pfe_row = session.execute(select(LocalPlanSite).where(LocalPlanSite.policy_reference == "JPA 99")).scalar_one()
    assert pfe_row.allocation_status == "adopted_allocation"


def test_synthetic_manual_review_row_still_gets_ingested(session, synthetic_manifest_dir, monkeypatch):
    # REF2's review_status is "needs_confirmation" (a manual-review flag on
    # the row itself) - it must still be created, not skipped, per
    # Requirement 7.
    _seed_pfe_target(session)
    monkeypatch.setattr(gbi, "EXPECTED_BASELINE_COUNT", 1)

    ingest_gm_baseline(session, manifest_dir=synthetic_manifest_dir, dry_run=False)

    site2 = session.execute(select(LocalPlanSite).where(LocalPlanSite.policy_reference == "REF2")).scalar_one()
    assert site2.review_status == "needs_confirmation"
    assert site2.id is not None  # it exists - was not skipped


def test_synthetic_idempotent_creation_running_twice(session, synthetic_manifest_dir, monkeypatch):
    _seed_pfe_target(session)
    monkeypatch.setattr(gbi, "EXPECTED_BASELINE_COUNT", 1)

    first = ingest_gm_baseline(session, manifest_dir=synthetic_manifest_dir, dry_run=False)
    assert first["created"] == 2

    monkeypatch.setattr(gbi, "EXPECTED_BASELINE_COUNT", 3)  # 1 seeded + 2 just created
    second = ingest_gm_baseline(session, manifest_dir=synthetic_manifest_dir, dry_run=False)
    assert second["created"] == 0
    assert second["already_existed"] == 2
    assert second["already_applied"] == 1  # the PfE correction is a deterministic set, already applied

    all_sites = session.execute(select(LocalPlanSite)).scalars().all()
    assert len(all_sites) == 3  # 1 seeded + 2 created, never 5 or 4 - no duplicates


def test_deterministic_update_targeting_resolves_by_council_and_reference(session):
    row = _seed_pfe_target(session)
    update = {"update_type": "pfe_status_correction", "council": "bury", "policy_reference": "JPA 99"}
    resolved = resolve_update_target(session, update)
    assert resolved is not None
    assert resolved.id == row.id


def test_deterministic_update_targeting_returns_none_for_unresolvable_reference(session):
    _seed_pfe_target(session)
    update = {"update_type": "pfe_status_correction", "council": "bury", "policy_reference": "NOT-A-REAL-REF"}
    assert resolve_update_target(session, update) is None


def test_unresolved_update_target_fails_closed(session, synthetic_manifest_dir, monkeypatch):
    # No PfE row seeded at all this time - JPA 99 cannot resolve.
    monkeypatch.setattr(gbi, "EXPECTED_BASELINE_COUNT", 0)

    with pytest.raises(RuntimeError, match="unresolved_update_targets"):
        ingest_gm_baseline(session, manifest_dir=synthetic_manifest_dir, dry_run=False)

    assert session.execute(select(LocalPlanSite)).scalars().all() == []


# ---------------------------------------------------------------------------
# VARCHAR length validation hotfix - dry-run must catch what production's
# own StringDataRightTruncation previously caught only at session.flush().
# ---------------------------------------------------------------------------


@pytest.fixture()
def synthetic_manifest_dir_with_overlength_new_row(tmp_path):
    overlength_site_name = "X" * 301  # site_name is String(300)
    new_sites = [
        {"council": "bury", "plan_name": "Test Local Plan", "plan_stage": "Regulation 18 draft",
         "policy_reference": "REF1", "site_name": overlength_site_name, "category": None,
         "intended_use": "residential", "allocation_status": "draft_allocation",
         "raw_allocation_status": "Regulation 18", "minimum_dwellings": 50, "indicative_capacity": None,
         "maximum_capacity": None, "source_document_url": "https://example.invalid/plan.pdf", "source_page": 1,
         "review_status": "auto_applied"},
    ]
    for name, data in (
        (gbi.NEW_SITES_FILE, new_sites),
        (gbi.UPDATES_FILE, []),
        (gbi.MANUAL_REVIEW_FILE, []),
        (gbi.EXCLUDED_FILE, []),
    ):
        (tmp_path / name).write_text(json.dumps(data), encoding="utf-8")
    return tmp_path


@pytest.fixture()
def synthetic_manifest_dir_with_overlength_update(tmp_path):
    overlength_status = "Y" * 51  # allocation_status is String(50)
    updates = [
        {"update_type": "pfe_status_correction", "council": "bury",
         "plan_name": "Places for Everyone Joint Development Plan (Bury allocations)",
         "policy_reference": "JPA 99", "field": "allocation_status",
         "from_value": "submitted_allocation", "to_value": overlength_status,
         "evidence": "test fixture", "review_status": "needs_confirmation"},
    ]
    for name, data in (
        (gbi.NEW_SITES_FILE, []),
        (gbi.UPDATES_FILE, updates),
        (gbi.MANUAL_REVIEW_FILE, []),
        (gbi.EXCLUDED_FILE, []),
    ):
        (tmp_path / name).write_text(json.dumps(data), encoding="utf-8")
    return tmp_path


def test_validate_new_rows_rejects_overlength_string_field():
    rows = [{"council": "bury", "plan_name": "Test Plan", "policy_reference": "REF1",
             "site_name": "X" * 301}]
    problems = validate_new_rows(rows)
    assert len(problems) == 1
    assert "site_name" in problems[0]
    assert "301" in problems[0]
    assert "300" in problems[0]


def test_validate_new_rows_rejects_overlength_plan_status_derived_from_plan_stage():
    overlength_stage = "Adopted (saved UDP, expiring at Local Plan adoption ~Spring 2027)"
    rows = [{"council": "oldham", "plan_name": "Test Plan", "policy_reference": "HLA0029",
             "site_name": "Ashton Road, Woodhouses", "plan_stage": overlength_stage}]
    problems = validate_new_rows(rows)
    assert len(problems) == 1
    assert "plan_status" in problems[0]
    assert "plan_stage" in problems[0]
    assert str(len(overlength_stage)) in problems[0]
    assert "50" in problems[0]


def test_validate_update_rows_rejects_overlength_target_value():
    updates = [{"update_type": "pfe_status_correction", "council": "bury", "policy_reference": "JPA 99",
                "to_value": "Y" * 51}]
    problems = validate_update_rows(updates)
    assert len(problems) == 1
    assert "allocation_status" in problems[0]
    assert "51" in problems[0]
    assert "50" in problems[0]


def test_validate_update_rows_rejects_overlength_capacity_and_use_field():
    updates = [{"update_type": "capacity_and_use_correction", "council": "bury", "policy_reference": "REF1",
                "fields": {"intended_use": {"from": "residential", "to": "Z" * 201}}}]
    problems = validate_update_rows(updates)
    assert len(problems) == 1
    assert "intended_use" in problems[0]


def test_validate_update_rows_accepts_council_reattribution_within_limit():
    updates = [{"update_type": "council_reattribution", "council": "bury", "policy_reference": "REF1",
                "to_value": "manchester"}]
    assert validate_update_rows(updates) == []


def test_synthetic_dry_run_reports_overlength_new_row_as_not_ready(session, synthetic_manifest_dir_with_overlength_new_row):
    result = ingest_gm_baseline(session, manifest_dir=synthetic_manifest_dir_with_overlength_new_row, dry_run=True)
    assert result["ready"] is False
    assert len(result["validation"]["invalid_rows"]) == 1
    assert "site_name" in result["validation"]["invalid_rows"][0]


def test_synthetic_dry_run_reports_overlength_update_as_not_ready(session, synthetic_manifest_dir_with_overlength_update):
    _seed_pfe_target(session)
    result = ingest_gm_baseline(session, manifest_dir=synthetic_manifest_dir_with_overlength_update, dry_run=True)
    assert result["ready"] is False
    assert len(result["validation"]["invalid_updates"]) == 1
    assert "allocation_status" in result["validation"]["invalid_updates"][0]


def test_production_mode_fails_closed_before_any_write_on_overlength_new_row(session, synthetic_manifest_dir_with_overlength_new_row, monkeypatch):
    monkeypatch.setattr(gbi, "EXPECTED_BASELINE_COUNT", 0)
    with pytest.raises(RuntimeError, match="invalid_rows=1"):
        ingest_gm_baseline(session, manifest_dir=synthetic_manifest_dir_with_overlength_new_row, dry_run=False)
    assert session.execute(select(LocalPlanSite)).scalars().all() == []
    assert session.execute(select(LocalPlan)).scalars().all() == []


def test_production_mode_fails_closed_before_any_write_on_overlength_update(session, synthetic_manifest_dir_with_overlength_update, monkeypatch):
    row = _seed_pfe_target(session)
    monkeypatch.setattr(gbi, "EXPECTED_BASELINE_COUNT", 1)
    with pytest.raises(RuntimeError, match="invalid_updates=1"):
        ingest_gm_baseline(session, manifest_dir=synthetic_manifest_dir_with_overlength_update, dry_run=False)
    # The seeded PfE row must be completely untouched - no partial write.
    session.refresh(row)
    assert row.allocation_status == "submitted_allocation"
    assert len(session.execute(select(LocalPlanSite)).scalars().all()) == 1


def test_rollback_on_failure_leaves_no_partial_writes(session, synthetic_manifest_dir, monkeypatch):
    _seed_pfe_target(session)
    monkeypatch.setattr(gbi, "EXPECTED_BASELINE_COUNT", 1)

    # Force a failure partway through the update-application loop by
    # breaking _apply_update for this run only.
    def _broken_apply(row, update):
        raise ValueError("simulated failure during update application")

    monkeypatch.setattr(gbi, "_apply_update", _broken_apply)

    with pytest.raises(ValueError, match="simulated failure"):
        ingest_gm_baseline(session, manifest_dir=synthetic_manifest_dir, dry_run=False)

    # The two new sites must NOT have been left committed even though they
    # were staged before the failing update - one controlled transaction,
    # full rollback, never a partially-ingested baseline.
    all_sites = session.execute(select(LocalPlanSite)).scalars().all()
    assert len(all_sites) == 1  # only the originally-seeded PfE row remains
    assert session.execute(select(LocalPlanSite).where(LocalPlanSite.policy_reference == "REF1")).scalar_one_or_none() is None
