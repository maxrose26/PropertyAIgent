"""Report-level plan attribution (LPDI V1 Gate 2A, "Multi-Plan Attribution &
Same-Plan Evidence Validation Hardening").

Answers, for one discovered MonitoredReport: which specific LocalPlan (if
any) does this document's evidence belong to? Generalises the Gate 2
practical limitation - app.policy.extract_plan_evidence.resolve_plan(
council_code) treating ANY multi-plan council as unconditionally excluded -
into an evidence-aware decision that uses the same signals a human reviewer
would: an explicit trusted source configuration, or an explicit plan
name/alias in the report's own title (or its discovering source page's
title). Genuine ambiguity still results in AMBIGUOUS (review-required),
never a guess - this module adds a way to resolve MORE cases
deterministically, it does not lower the bar for what counts as
"deterministic".

resolve_plan() itself is intentionally left unchanged - it is a human-
operator-facing CLI tool (given only a council code, and a --plan-id to
disambiguate by hand) with a different, correct contract for its own use
case. attribute_report() is the automated-cohort-classification equivalent,
used to build a SAFE_TO_EXTRACT/AUTHORITY_WIDE/STILL_NEEDS_REVIEW cohort
without a human present for every report."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.db.models import LocalPlan, MonitoredReport, MonitoredSource
from app.policy.joint_plans import plans_for_council
from app.policy.plan_identity import aliases_for_plan

AttributionStatus = Literal["PLAN_MATCH", "AUTHORITY_WIDE", "AMBIGUOUS"]

# source_type values that conventionally carry authority-level monitoring
# evidence (annual completions, housing land supply, Housing Delivery Test
# figures) rather than plan-specific content - see
# app.policy.document_selection.DOCUMENT_TYPE_TO_CATEGORIES for the same
# source_type vocabulary used platform-wide. Kept as a small, explicit,
# generic set (not a per-authority rule) - a report of one of these types
# is a candidate for AUTHORITY_WIDE treatment only once no other signal
# (trusted source config, title alias) has already resolved it to one
# specific plan.
AUTHORITY_WIDE_CAPABLE_SOURCE_TYPES = frozenset({
    "annual_monitoring_report", "authority_monitoring_report",
    "housing_delivery_statement", "housing_delivery_report", "housing_trajectory",
    "five_year_supply_statement", "housing_land_supply_statement",
})


@dataclass(frozen=True)
class AttributionResult:
    status: AttributionStatus
    plan: LocalPlan | None
    reason: str


def _title_alias_match(title: str | None, candidates: list[LocalPlan]) -> list[LocalPlan]:
    """Every candidate plan whose configured alias (or its own plan_name,
    the guaranteed fallback - see app.policy.plan_identity.aliases_for_plan)
    appears as a substring of title. Case-insensitive; purely config-driven
    (no candidate's name is special-cased in this function)."""
    if not title:
        return []
    lowered = title.lower()
    matches = []
    for plan in candidates:
        for alias in aliases_for_plan(plan):
            if alias and alias.lower() in lowered:
                matches.append(plan)
                break
    return matches


def attribute_report(session: Session, report: MonitoredReport) -> AttributionResult:
    """Deterministic attribution only - never a guess, never an LLM call.
    See the module docstring for the tiered signal order."""
    candidates = plans_for_council(session, report.council_code)

    if not candidates:
        return AttributionResult("AMBIGUOUS", None, f"no LocalPlan exists yet for council {report.council_code!r}")

    if len(candidates) == 1:
        return AttributionResult("PLAN_MATCH", candidates[0], "single-plan authority - no ambiguity possible")

    # Tier 1 - explicit trusted source configuration: the MonitoredSource
    # that discovered this report may already have been registered with a
    # config-driven plan_name/plan_version (app.policy.sources.
    # _resolve_local_plan_id), copied onto the report at discovery time
    # (app.policy.report_discovery.discover_reports). This is the
    # strongest available signal - a human already told the platform which
    # plan this SOURCE belongs to.
    if report.local_plan_id is not None:
        matched = next((p for p in candidates if p.id == report.local_plan_id), None)
        if matched is not None:
            return AttributionResult("PLAN_MATCH", matched, "explicit trusted source configuration (MonitoredSource.local_plan_id)")

    # Tier 2 - explicit plan identity alias in the report's own title.
    matches = _title_alias_match(report.title, candidates)
    unique = {p.id: p for p in matches}
    if len(unique) == 1:
        plan = next(iter(unique.values()))
        return AttributionResult("PLAN_MATCH", plan, f"report title contains an explicit identity alias for {plan.plan_name!r}")
    if len(unique) > 1:
        names = ", ".join(p.plan_name for p in unique.values())
        return AttributionResult("AMBIGUOUS", None, f"report title names more than one candidate plan: {names}")

    # Tier 2b - the discovering source PAGE's own title may itself be
    # scoped to one specific plan (e.g. a Local Plan's own Regulation 19
    # consultation landing page), even though the individual document
    # discovered from it doesn't repeat the plan's name in its own title
    # (a "Viability Assessment" or "Schedule of responses" rarely restates
    # which plan it belongs to explicitly). Only used once the document's
    # OWN title gave no signal at all - an explicit, contradictory signal
    # on the document's own title (handled above) always wins.
    source = session.get(MonitoredSource, report.monitored_source_id) if report.monitored_source_id else None
    source_matches = _title_alias_match(source.title if source else None, candidates)
    unique_source = {p.id: p for p in source_matches}
    if len(unique_source) == 1:
        plan = next(iter(unique_source.values()))
        return AttributionResult("PLAN_MATCH", plan, f"discovering source page title identifies this specific plan ({plan.plan_name!r})")
    if len(unique_source) > 1:
        names = ", ".join(p.plan_name for p in unique_source.values())
        return AttributionResult("AMBIGUOUS", None, f"discovering source page title names more than one candidate plan: {names}")

    # Tier 3 - authority-wide monitoring content: not tied to one plan by
    # any signal above, but its own source_type is one that conventionally
    # carries authority-level (not plan-specific) evidence.
    if report.source_type in AUTHORITY_WIDE_CAPABLE_SOURCE_TYPES:
        return AttributionResult(
            "AUTHORITY_WIDE", None,
            f"source_type {report.source_type!r} conventionally carries authority-level evidence; "
            f"no explicit signal ties it to one specific plan",
        )

    return AttributionResult(
        "AMBIGUOUS", None,
        "council has more than one LocalPlan and no explicit signal (trusted source config, report "
        "title alias, or source page title alias) identifies which one this report belongs to",
    )
