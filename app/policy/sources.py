"""Registers MonitoredSource rows from data/configuration
(config/policy_sources.yaml), rather than embedding source URLs inside
monitoring logic itself (Sprint 1 CTO-review amendment, Part 3).

app.policy.monitor only ever reads MonitoredSource rows that already
exist - this module is how they get there. A council's Local Plan must
already be ingested (see ingest_local_plan.py) before its sources can be
registered; this module attaches watch targets to an existing plan, it
doesn't create one.

Stockport's sources are registered as a config/policy_sources.yaml entry
under councils.stockport, pointing at the same Local Plan PDF URL
ingest_local_plan.py already uses as --source-url. Registering it:

    python -m scripts.register_policy_sources --council stockport
"""
from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LocalPlan, MonitoredSource

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCES_YAML = PROJECT_ROOT / "config" / "policy_sources.yaml"


def load_source_config(path: Path = SOURCES_YAML) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def register_sources_for_council(session: Session, council_code: str, config: dict | None = None) -> list[MonitoredSource]:
    """Find-or-create every MonitoredSource listed for this council in
    config/policy_sources.yaml. Idempotent - already-registered sources
    (matched on local_plan_id + url) are returned as-is, never duplicated.
    Returns an empty list (not an error) if the council has no config
    entry, or if its LocalPlan hasn't been ingested yet - both are normal,
    expected states, not failures."""
    config = config if config is not None else load_source_config()
    entry = (config.get("councils") or {}).get(council_code)
    if not entry:
        return []

    plan = session.execute(
        select(LocalPlan).where(
            LocalPlan.council_code == council_code,
            LocalPlan.plan_name == entry["plan_name"],
            LocalPlan.plan_version == entry.get("plan_version"),
        )
    ).scalar_one_or_none()
    if plan is None:
        return []

    registered = []
    for source_entry in entry.get("sources", []):
        existing = session.execute(
            select(MonitoredSource).where(
                MonitoredSource.local_plan_id == plan.id, MonitoredSource.url == source_entry["url"],
            )
        ).scalar_one_or_none()
        if existing:
            registered.append(existing)
            continue
        source = MonitoredSource(
            local_plan_id=plan.id, url=source_entry["url"], source_type=source_entry["source_type"],
            title=source_entry.get("title"),
        )
        session.add(source)
        registered.append(source)
    session.commit()
    return registered
