"""Registers MonitoredSource rows from data/configuration
(config/policy_sources.yaml), rather than embedding source URLs inside
monitoring logic itself (Sprint 1 CTO-review amendment, Part 3; generalised
in Sprint 2 - "Greater Manchester Policy Intelligence Framework" - Part 3).

Sprint 1 only allowed registering a source once a specific LocalPlan
already existed in the database, which meant a council-level watch (a
Local Plan landing page, a consultation portal - exactly the source types
Sprint 2's brief names) couldn't be registered until AFTER a plan had
already been manually ingested - backwards for a source whose whole
purpose is detecting that a plan exists or has changed stage in the first
place. Sources are now registered per COUNCIL; a source entry optionally
names the plan_name/plan_version it belongs to, and gets linked to that
LocalPlan's id if (and once) it exists - if it doesn't yet, the source is
still registered, just with local_plan_id left null until a later call
(after ingestion) resolves it.

    python -m scripts.register_policy_sources --council bury
"""
from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LocalPlan, MonitoredSource
from app.policy.document_types import classify_policy_document_type

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCES_YAML = PROJECT_ROOT / "config" / "policy_sources.yaml"


def load_source_config(path: Path = SOURCES_YAML) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _resolve_local_plan_id(session: Session, council_code: str, source_entry: dict) -> int | None:
    """A source entry MAY name the specific plan it belongs to
    (plan_name/plan_version) - if it does and that plan has already been
    ingested, link to it. A source with no plan_name at all (a council-
    level landing page or consultation portal) always resolves to None,
    which is a valid, expected steady state, not a placeholder waiting to
    be filled in."""
    plan_name = source_entry.get("plan_name")
    if not plan_name:
        return None
    plan = session.execute(
        select(LocalPlan).where(
            LocalPlan.council_code == council_code,
            LocalPlan.plan_name == plan_name,
            LocalPlan.plan_version == source_entry.get("plan_version"),
        )
    ).scalar_one_or_none()
    return plan.id if plan else None


def register_sources_for_council(session: Session, council_code: str, config: dict | None = None) -> list[MonitoredSource]:
    """Find-or-create every MonitoredSource listed for this council in
    config/policy_sources.yaml. Idempotent - already-registered sources
    (matched on council_code + url) are found, not duplicated; if a
    matching LocalPlan has since been ingested where one didn't exist
    before, this call also resolves the now-findable local_plan_id onto
    the existing row. Returns an empty list (not an error) if the council
    has no config entry - a normal, expected state for any council not yet
    onboarded, not a failure."""
    config = config if config is not None else load_source_config()
    entry = (config.get("councils") or {}).get(council_code)
    if not entry:
        return []

    registered = []
    for source_entry in entry.get("sources", []):
        existing = session.execute(
            select(MonitoredSource).where(
                MonitoredSource.council_code == council_code, MonitoredSource.url == source_entry["url"],
            )
        ).scalar_one_or_none()
        local_plan_id = _resolve_local_plan_id(session, council_code, source_entry)
        # Sprint 3D ("Policy Document Coverage & Discovery", Part 2) - a
        # source registered directly here (the actual Local Plan PDF, a
        # Policies Map registered by hand rather than found via
        # app.policy.report_discovery's link-scraping) still needs a
        # policy_document_type or app.policy.coverage would never see it
        # as "discovered" at all, wrongly reporting a document the
        # platform has genuinely already ingested as still missing.
        policy_document_type, _ = classify_policy_document_type(source_entry.get("title"), source_entry["url"])

        if existing:
            if existing.local_plan_id is None and local_plan_id is not None:
                existing.local_plan_id = local_plan_id
            if existing.policy_document_type is None:
                existing.policy_document_type = policy_document_type
                existing.policy_document_type_raw_label = source_entry.get("title")
            registered.append(existing)
            continue

        source = MonitoredSource(
            council_code=council_code, local_plan_id=local_plan_id,
            url=source_entry["url"], source_type=source_entry["source_type"],
            title=source_entry.get("title"),
            policy_document_type=policy_document_type, policy_document_type_raw_label=source_entry.get("title"),
            monitoring_frequency_days=int(source_entry.get("monitoring_frequency_days", 7)),
        )
        session.add(source)
        registered.append(source)
    session.commit()
    return registered
