"""Complete GM Local Plan Baseline - production ingestion runner (core
logic). Reuses the exact same primitives every other Local Plan ingestion
path in this codebase already uses:

  - app.policy.status.normalise_plan_status for a LocalPlan's own status
  - app.policy.progression.classify_progression for each new allocation's
    progression_signal, same as ingest_local_plan.py and
    app.policy.pfe_allocation_onboarding both already do
  - app.db.models.LocalPlan/LocalPlanSite directly, no new tables

Input is the frozen manifests in config/gm_local_plan_baseline/ - this
module never performs web research, never calls OpenAI, and never
recomputes what those manifests already decided. It only turns them into
LocalPlan/LocalPlanSite rows, deterministically and idempotently.

Deliberately narrower than app.policy.pfe_allocation_onboarding /
ingest_local_plan.py in one respect: this is a one-time controlled backfill
of already-researched, human-reviewed data, not an ongoing extraction
pipeline, so it does NOT run AI-based diffing (app.policy.change_detection)
or site-matching/geocoding (app.extraction.local_plan) - those exist to
protect against an uncertain future re-extraction disagreeing with trusted
state, which does not apply here: every field in the manifest already
carries its own human-reviewed provenance, and updates are targeted by
exact (council_code, policy_reference) within the correct LocalPlan, never
inferred.

Two manifests are intentionally NEVER read by this module -
gm_local_plan_relationship_review.json (AllocationRelationship creation is
explicitly deferred, Product Owner decision) and gm_local_plan_ah_sidecar
.json (no schema field exists to hold it) - and gm_local_plan_excluded.json
/ gm_local_plan_manual_review.json are read only for reporting, never for
gating: a manual-review flag lives on the row's own review_status field
inside gm_local_plan_new_sites.json itself, it never causes a row to be
silently dropped from processing.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from sqlalchemy import String, func, select
from sqlalchemy.orm import Session

from app.config import get_council
from app.db.models import LocalPlan, LocalPlanSite
from app.policy.progression import classify_progression
from app.policy.status import ALLOCATION_STATUSES, normalise_plan_status

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DIR = PROJECT_ROOT / "config" / "gm_local_plan_baseline"

# Derived from SQLAlchemy model metadata (Requirement 5/12) rather than a
# hand-maintained duplicate table - if a column's declared length ever
# changes, this map changes with it automatically. This is exactly what a
# real production run needed and didn't have: the Oldham plan_status
# overflow (String(50), a 65-char value) was never caught before
# session.flush() hit the real database's own constraint.
STRING_COLUMN_LENGTHS: dict[str, int] = {
    col.name: col.type.length
    for col in LocalPlanSite.__table__.columns
    if isinstance(col.type, String) and col.type.length
}

# manifest field name (in gm_local_plan_new_sites.json) -> the LocalPlanSite
# column it is actually persisted into, per the row-construction code below.
# "council" -> council_code and plan_stage -> plan_status (via
# LocalPlan.raw_status, see _find_or_create_local_plan) are the two
# non-identity mappings - every other field shares its manifest name with
# its column name.
NEW_ROW_FIELD_TO_COLUMN: dict[str, str] = {
    "council": "council_code",
    "policy_reference": "policy_reference",
    "site_name": "site_name",
    "category": "category",
    "intended_use": "intended_use",
    "allocation_status": "allocation_status",
    "raw_allocation_status": "raw_allocation_status",
    "plan_name": "plan_name",
    "source_document_url": "source_document_url",
    "review_status": "review_status",
}

# The frozen manifest's own assumptions about production state - encoded
# here (not re-derived from the manifest files) so a manifest file being
# silently edited can never quietly change what "safe to proceed" means.
EXPECTED_BASELINE_COUNT = 80
EXPECTED_NEW_COUNT = 207
EXPECTED_UPDATE_COUNT = 38
EXPECTED_FINAL_COUNT = EXPECTED_BASELINE_COUNT + EXPECTED_NEW_COUNT

PFE_PLAN_NAME = "Places for Everyone Joint Development Plan (Bury allocations)"

# Manifests this module reads and processes.
NEW_SITES_FILE = "gm_local_plan_new_sites.json"
UPDATES_FILE = "gm_local_plan_updates.json"
# Read for reporting only - never processed/ingested.
MANUAL_REVIEW_FILE = "gm_local_plan_manual_review.json"
EXCLUDED_FILE = "gm_local_plan_excluded.json"
# Deliberately never loaded by this module at all:
#   gm_local_plan_relationship_review.json (deferred, Product Owner decision)
#   gm_local_plan_ah_sidecar.json (no schema field to hold it)


def load_manifest(name: str, manifest_dir: Path = MANIFEST_DIR) -> list[dict]:
    path = manifest_dir / name
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Manifest {name} must be a JSON list, got {type(data).__name__}")
    return data


def validate_baseline(session: Session) -> dict:
    """Fail-closed check (Requirement 10): the manifest's assumptions about
    current production state must hold before any write is attempted."""
    actual = session.execute(select(func.count()).select_from(LocalPlanSite)).scalar_one()
    return {
        "expected": EXPECTED_BASELINE_COUNT,
        "actual": actual,
        "matches": actual == EXPECTED_BASELINE_COUNT,
    }


def validate_new_rows(rows: list[dict]) -> list[str]:
    """Validates every proposed new row against LocalPlanSite model
    constraints (Requirement 11) before any write is attempted. Returns a
    list of human-readable problems; empty list means all rows are valid."""
    problems: list[str] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for i, row in enumerate(rows):
        label = f"row {i} ({row.get('council')!r}/{row.get('policy_reference')!r})"

        if not row.get("council"):
            problems.append(f"{label}: missing council")
            continue
        try:
            get_council(row["council"])
        except KeyError:
            problems.append(f"{label}: unknown council code {row['council']!r}")

        if not row.get("site_name"):
            problems.append(f"{label}: missing site_name")
        if not row.get("plan_name"):
            problems.append(f"{label}: missing plan_name")
        if not row.get("policy_reference"):
            problems.append(f"{label}: missing policy_reference")

        status = row.get("allocation_status")
        if status is not None and status not in ALLOCATION_STATUSES:
            problems.append(f"{label}: invalid allocation_status {status!r}, not in ALLOCATION_STATUSES")

        for field in ("minimum_dwellings", "indicative_capacity", "maximum_capacity"):
            value = row.get(field)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                problems.append(f"{label}: {field} must be a non-negative integer or null, got {value!r}")

        # Duplicate-within-manifest check - (council, plan_name,
        # policy_reference) must be unique in the manifest itself, or the
        # find-or-create idempotency key below can't tell two proposed rows
        # apart.
        key = (row["council"], row.get("plan_name", ""), row.get("policy_reference", ""))
        if key in seen_keys:
            problems.append(f"{label}: duplicate (council, plan_name, policy_reference) within the manifest itself")
        seen_keys.add(key)

        problems.extend(_check_row_string_lengths(row, label))

    return problems


def _check_row_string_lengths(row: dict, label: str) -> list[str]:
    """Checks every manifest field that is persisted as a LocalPlanSite
    string column against that column's actual declared length. This is
    what production's real StringDataRightTruncation error should have been
    caught by during dry-run - it wasn't, because no such check previously
    existed here."""
    problems: list[str] = []
    for manifest_field, column in NEW_ROW_FIELD_TO_COLUMN.items():
        value = row.get(manifest_field)
        if not isinstance(value, str):
            continue
        limit = STRING_COLUMN_LENGTHS.get(column)
        if limit and len(value) > limit:
            problems.append(
                f"{label}: field {manifest_field!r} (column {column!r}) is {len(value)} chars, "
                f"exceeds max length {limit} - value={value!r}"
            )

    # plan_status is never a manifest field directly - it's derived from
    # plan_stage via LocalPlan.raw_status/status at ingestion time (see
    # _find_or_create_local_plan), so it needs its own check rather than
    # being covered by NEW_ROW_FIELD_TO_COLUMN.
    plan_stage = row.get("plan_stage")
    if isinstance(plan_stage, str):
        limit = STRING_COLUMN_LENGTHS.get("plan_status")
        if limit and len(plan_stage) > limit:
            problems.append(
                f"{label}: field 'plan_stage' (column 'plan_status', derived via LocalPlan.raw_status) is "
                f"{len(plan_stage)} chars, exceeds max length {limit} - value={plan_stage!r}"
            )
    return problems


def validate_update_rows(updates: list[dict]) -> list[str]:
    """Validates every proposed update record's target string values against
    LocalPlanSite model constraints (Requirement 6) before any write is
    attempted - mirrors _check_row_string_lengths but for the update path,
    using the same _apply_update field mapping so both paths can never
    silently diverge. Returns a list of human-readable problems; empty list
    means all updates are valid. Does not require a resolved target row -
    the column being written is fully determined by update_type/fields, so
    this check can run purely against the manifest data itself."""
    problems: list[str] = []

    for i, update in enumerate(updates):
        label = f"update {i} ({update.get('council')!r}/{update.get('policy_reference')!r})"
        update_type = update.get("update_type")

        fields_to_check: dict[str, object] = {}
        if update_type == "pfe_status_correction":
            fields_to_check["allocation_status"] = update.get("to_value")
        elif update_type == "council_reattribution":
            fields_to_check["council_code"] = update.get("to_value")
        elif update_type == "capacity_and_use_correction":
            for field, change in (update.get("fields") or {}).items():
                fields_to_check[field] = change.get("to") if isinstance(change, dict) else None
        else:
            problems.append(f"{label}: unknown update_type {update_type!r}")
            continue

        for column, value in fields_to_check.items():
            if not isinstance(value, str):
                continue
            limit = STRING_COLUMN_LENGTHS.get(column)
            if limit and len(value) > limit:
                problems.append(
                    f"{label}: target field {column!r} is {len(value)} chars, "
                    f"exceeds max length {limit} - value={value!r}"
                )

    return problems


def _find_or_create_local_plan(session: Session, council: str, plan_name: str, plan_stage: str, *, dry_run: bool) -> LocalPlan | None:
    """Idempotent find-or-create, matching LocalPlan's own
    UniqueConstraint("council_code", "plan_name", "plan_version"). plan_stage
    is used as plan_version - it's already the closest thing the manifest
    has to a stable version label for these plans. A brand-new plan has no
    existing trusted value to protect (same reasoning as
    ingest_local_plan.py / pfe_allocation_onboarding.py) - safe to write
    immediately, never queued for review."""
    existing = session.execute(
        select(LocalPlan).where(
            LocalPlan.council_code == council,
            LocalPlan.plan_name == plan_name,
            LocalPlan.plan_version == plan_stage,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    if dry_run:
        return None

    plan = LocalPlan(
        council_code=council, plan_name=plan_name, plan_version=plan_stage,
        status=normalise_plan_status(plan_stage), raw_status=plan_stage,
    )
    session.add(plan)
    session.flush()  # assigns plan.id
    return plan


def _existing_site(session: Session, local_plan_id: int, policy_reference: str) -> LocalPlanSite | None:
    return session.execute(
        select(LocalPlanSite).where(
            LocalPlanSite.local_plan_id == local_plan_id,
            LocalPlanSite.policy_reference == policy_reference,
        )
    ).scalar_one_or_none()


def resolve_update_target(session: Session, update: dict) -> LocalPlanSite | None:
    """Deterministic target resolution (Requirement 9) - exact
    (council_code, policy_reference) within the Places for Everyone
    LocalPlan specifically, never loose site-name matching. Returns None if
    zero or more-than-one rows match (ambiguous == unresolved, never
    guessed)."""
    council = update.get("council")
    ref = update.get("policy_reference")
    if not council or not ref:
        return None

    rows = session.execute(
        select(LocalPlanSite).where(
            LocalPlanSite.council_code == council,
            LocalPlanSite.policy_reference == ref,
            LocalPlanSite.plan_name == PFE_PLAN_NAME,
        )
    ).scalars().all()
    if len(rows) != 1:
        return None
    return rows[0]


def _apply_update(row: LocalPlanSite, update: dict) -> None:
    update_type = update["update_type"]
    if update_type == "pfe_status_correction":
        row.allocation_status = update["to_value"]
    elif update_type == "council_reattribution":
        row.council_code = update["to_value"]
    elif update_type == "capacity_and_use_correction":
        for field, change in update["fields"].items():
            setattr(row, field, change["to"])
    else:
        raise ValueError(f"Unknown update_type: {update_type!r}")


def ingest_gm_baseline(session: Session, manifest_dir: Path = MANIFEST_DIR, dry_run: bool = True) -> dict:
    """Runs the full Complete GM Local Plan Baseline ingestion.

    dry_run=True (the safe default): makes ZERO database mutations -
    every session.add/flush/commit call is skipped, only read-only SELECTs
    run, so the result dict describes exactly what WOULD happen.

    dry_run=False: writes everything in one controlled transaction - if
    baseline validation fails, or any new row fails model-constraint
    validation, or any update's target can't be resolved, NOTHING is
    written at all (fail closed, Requirement 10/12) - the function raises
    RuntimeError before touching the session, or rolls back and re-raises
    if a write itself fails partway through.

    Returns a result dict matching the required dry-run report shape.
    """
    new_rows = load_manifest(NEW_SITES_FILE, manifest_dir)
    updates = load_manifest(UPDATES_FILE, manifest_dir)
    manual_review = load_manifest(MANUAL_REVIEW_FILE, manifest_dir)
    excluded = load_manifest(EXCLUDED_FILE, manifest_dir)

    baseline = validate_baseline(session)
    row_problems = validate_new_rows(new_rows)
    update_length_problems = validate_update_rows(updates)

    unresolved_updates: list[dict] = []
    resolved_targets: dict[int, LocalPlanSite] = {}
    for idx, update in enumerate(updates):
        target = resolve_update_target(session, update)
        if target is None:
            unresolved_updates.append(update)
        else:
            resolved_targets[idx] = target

    ready = (
        baseline["matches"]
        and not row_problems
        and not update_length_problems
        and not unresolved_updates
    )

    result = {
        "dry_run": dry_run,
        "baseline": baseline,
        "create": {
            "total": len(new_rows),
            "by_council": _count_by_council(new_rows),
        },
        "update": {
            "total": len(updates),
            "pfe_status_corrections": len([u for u in updates if u["update_type"] == "pfe_status_correction"]),
            "medipark_correction": any(u["update_type"] == "council_reattribution" for u in updates),
            "heywood_pilsworth_correction": any(u["update_type"] == "capacity_and_use_correction" for u in updates),
        },
        "skipped_review_only": {
            "relationships": "not_loaded_by_this_module (deferred, Product Owner decision)",
            "ah_sidecar": "not_loaded_by_this_module (no schema field)",
            "manual_review": len(manual_review),
            "excluded": len(excluded),
        },
        "validation": {
            "baseline_matches": baseline["matches"],
            "invalid_rows": row_problems,
            "invalid_updates": update_length_problems,
            "unresolved_update_targets": [f"{u['council']}/{u.get('policy_reference')}" for u in unresolved_updates],
            "expected_final_count": EXPECTED_FINAL_COUNT,
        },
        "ready": ready,
        "created": 0,
        "already_existed": 0,
        "updated": 0,
        "already_applied": 0,
    }

    if dry_run:
        return result

    if not ready:
        raise RuntimeError(
            "GM baseline ingestion aborted before any write - "
            f"baseline_matches={baseline['matches']}, "
            f"invalid_rows={len(row_problems)}, "
            f"invalid_updates={len(update_length_problems)}, "
            f"unresolved_update_targets={len(unresolved_updates)}"
        )

    try:
        created = 0
        already_existed = 0
        for row in new_rows:
            plan = _find_or_create_local_plan(session, row["council"], row["plan_name"], row.get("plan_stage") or "unknown", dry_run=False)
            existing = _existing_site(session, plan.id, row["policy_reference"])
            if existing is not None:
                already_existed += 1
                continue

            site = LocalPlanSite(
                council_code=row["council"], local_plan_id=plan.id,
                policy_reference=row["policy_reference"], site_name=row["site_name"],
                category=row.get("category"), intended_use=row.get("intended_use") or "residential",
                allocation_status=row.get("allocation_status"), raw_allocation_status=row.get("raw_allocation_status"),
                minimum_dwellings=row.get("minimum_dwellings"), indicative_capacity=row.get("indicative_capacity"),
                maximum_capacity=row.get("maximum_capacity"),
                plan_name=row["plan_name"], plan_status=plan.raw_status or plan.status,
                source_document_url=row.get("source_document_url"), source_page=row.get("source_page"),
                review_status=row.get("review_status") or "auto_applied",
            )
            session.add(site)
            session.flush()  # assigns site.id
            signal, reasons = classify_progression(plan.status, site.allocation_status, present_in_latest_version=True)
            site.progression_signal = signal
            site.progression_reasons = json.dumps(reasons)
            site.progression_computed_at = dt.datetime.now(dt.timezone.utc)
            created += 1

        updated = 0
        already_applied = 0
        for idx, update in enumerate(updates):
            target = resolved_targets[idx]
            before = {
                field: getattr(target, field)
                for field in ("allocation_status", "council_code", "intended_use", "minimum_dwellings")
            }
            _apply_update(target, update)
            after = {
                field: getattr(target, field)
                for field in ("allocation_status", "council_code", "intended_use", "minimum_dwellings")
            }
            if before == after:
                already_applied += 1
            else:
                updated += 1

        session.commit()
    except Exception:
        session.rollback()
        raise

    result["created"] = created
    result["already_existed"] = already_existed
    result["updated"] = updated
    result["already_applied"] = already_applied
    return result


def _count_by_council(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        council = row.get("council", "unknown")
        counts[council] = counts.get(council, 0) + 1
    return counts
