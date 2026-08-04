"""Policy document coverage engine (Sprint 3D, "Policy Document Coverage &
Discovery", Part 3) - for a council, and for every document type
app.policy.expected_documents says SHOULD exist, works out exactly how
far that document has actually got through the platform's pipeline:

    Expected -> Discovered -> Downloaded -> Registered -> Current ->
    Superseded -> Ingested -> Visual Evidence extracted ->
    Policy evidence extracted

Every stage is read from data that already exists elsewhere
(MonitoredSource, MonitoredReport, LocalPlan, VisualEvidence) - this
module never writes anything, only reports. A few stages collapse onto
the same underlying signal where the platform genuinely has no separate
tracking for them yet (see the docstring on build_coverage_inventory) -
documented honestly rather than presented as independently verified when
they aren't.

Batched throughout: every council's reports/sources/plans/visual evidence
are loaded once each, then grouped in Python by document type - never one
query per expected document type (the same discipline
app.ui.allocation_selector's image-status lookup already established).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Council, LocalPlan, MonitoredReport, MonitoredSource, VisualEvidence
from app.policy.document_types import POLICY_DOCUMENT_TYPE_LABELS
from app.policy.expected_documents import expected_document_types


def _rows_by_document_type(rows: list, key: str = "policy_document_type") -> dict[str, list]:
    grouped: dict[str, list] = {}
    for row in rows:
        doc_type = getattr(row, key)
        if doc_type is None:
            continue
        grouped.setdefault(doc_type, []).append(row)
    return grouped


def build_coverage_inventory(session: Session, council_code: str) -> list[dict]:
    """One row per document type app.policy.expected_documents.
    expected_document_types(council_code) says should exist for this
    council. Every row has this shape:

        {
            "policy_document_type", "label",
            "expected": True,
            "discovered", "registered",   # collapsed onto one signal - see below
            "downloaded", "current", "superseded", "ingested",
            "visual_evidence_extracted", "policy_evidence_extracted",
            "monitoring_active", "missing",
            "discovered_count", "current_count", "superseded_count",
        }

    Honest simplifications, not independently verified stages:
      - "discovered" and "registered" are the SAME underlying signal here
        (at least one MonitoredReport or directly-classified
        MonitoredSource row of this type exists) - this platform has no
        separate "we're watching for it but haven't found it yet" state
        for an individual document type today, only for the INDEX PAGE
        that might eventually yield one (which isn't itself "this
        document type" until something is actually found under it).
      - "ingested" is an OR-rollup of "visual_evidence_extracted",
        "policy_evidence_extracted", and (for local_plan specifically)
        "a LocalPlan row exists for this council" - Part 3 lists it before
        those two more specific stages, consistent with it meaning "has
        this document been brought into the platform's structured
        knowledge at all, via whichever pathway applies to its type."
    """
    council = session.get(Council, council_code)
    monitoring_enabled = bool(council.monitoring_enabled) if council else False

    reports = list(session.execute(select(MonitoredReport).where(MonitoredReport.council_code == council_code)).scalars())
    sources = list(session.execute(select(MonitoredSource).where(MonitoredSource.council_code == council_code)).scalars())
    plans = list(session.execute(select(LocalPlan).where(LocalPlan.council_code == council_code)).scalars())

    report_ids = {r.id for r in reports}
    plan_ids = {p.id for p in plans}
    visual_evidence = list(session.execute(
        select(VisualEvidence).where(VisualEvidence.status == "current")
    ).scalars()) if (report_ids or plan_ids) else []
    visual_evidence_report_ids = {
        v.monitored_report_id for v in visual_evidence
        if v.monitored_report_id is not None and v.monitored_report_id in report_ids
    }
    visual_evidence_plan_ids = {
        v.local_plan_id for v in visual_evidence
        if v.local_plan_id is not None and v.local_plan_id in plan_ids
    }

    reports_by_type = _rows_by_document_type(reports)
    sources_by_type = _rows_by_document_type(sources)

    inventory = []
    for doc_type in expected_document_types(council_code):
        type_reports = reports_by_type.get(doc_type, [])
        type_sources = sources_by_type.get(doc_type, [])

        current_reports = [r for r in type_reports if r.status == "current"]
        superseded_reports = [r for r in type_reports if r.status == "superseded"]

        discovered = bool(type_reports or type_sources)
        downloaded = any(r.local_path for r in current_reports)
        current = bool(current_reports) or bool(type_sources)
        superseded = bool(superseded_reports)

        visual_evidence_extracted = any(r.id in visual_evidence_report_ids for r in current_reports) or (
            doc_type == "local_plan" and any(p.id in visual_evidence_plan_ids for p in plans)
        )
        policy_evidence_extracted = any(r.last_extracted_at is not None for r in current_reports)
        ingested = (
            visual_evidence_extracted
            or policy_evidence_extracted
            or (doc_type == "local_plan" and bool(plans))
        )

        monitoring_active = monitoring_enabled and (
            any(r.monitoring_health != "never_checked" for r in current_reports)
            or any(s.is_active and s.monitoring_health != "never_checked" for s in type_sources)
        )

        inventory.append({
            "policy_document_type": doc_type,
            "label": POLICY_DOCUMENT_TYPE_LABELS.get(doc_type, doc_type),
            "expected": True,
            "discovered": discovered,
            "registered": discovered,
            "downloaded": downloaded,
            "current": current,
            "superseded": superseded,
            "ingested": ingested,
            "visual_evidence_extracted": visual_evidence_extracted,
            "policy_evidence_extracted": policy_evidence_extracted,
            "monitoring_active": monitoring_active,
            "missing": not discovered,
            "discovered_count": len(type_reports) + len(type_sources),
            "current_count": len(current_reports),
            "superseded_count": len(superseded_reports),
        })

    return inventory


def missing_document_types(session: Session, council_code: str) -> list[str]:
    """The subset of expected_document_types this council has nothing
    discovered for yet - the coverage engine's direct answer to "what are
    we missing" (Part 3/Part 7's own framing)."""
    return [row["policy_document_type"] for row in build_coverage_inventory(session, council_code) if row["missing"]]
