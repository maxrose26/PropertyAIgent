"""AI-narrated synthesis of one LocalPlan's own trusted/pending evidence
(Sprint 3B.1, "AI Local Plan Summary").

Same grounded-numbers-then-narrate principle as app.reporting.
scheme_summary: every fact fed to the model is computed/looked up in
Python first from already-verified data (app.policy.plan_evidence_view,
the same assembly the Council Dashboard's own evidence section renders
from) - the model only ever writes the connective prose synthesising facts
it's given. It never calculates a figure, never decides adopted-vs-
emerging, and never turns a proposed change into a settled fact - all of
that is decided deterministically in this module before the model ever
sees the payload.

Persisted on the LocalPlan row itself (not regenerated on every page
view) and gated by an evidence fingerprint - see should_regenerate.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections import Counter

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Council, LocalPlan, LocalPlanSite
from app.policy.plan_evidence_view import build_plan_evidence_view, get_conflicting_fields

MODEL = "gpt-4o-mini"
# Bumped whenever the prompt or schema changes in a way that could change
# the generated summary - stored on every persisted summary (Part 6) and
# checked by should_regenerate, so a version bump alone (without an
# explicit --force/Refresh) doesn't retroactively invalidate an already-
# generated summary until it's actually next regenerated.
PROMPT_VERSION = "local-plan-summary-v1"

# Every fact field the summary payload carries, in the order Part 1 lists
# them, paired with a human label used both in the prompt and (where
# useful) the UI. "plan period" itself is represented by the pair below,
# not a single field - see build_summary_payload.
FACT_FIELDS: list[tuple[str, str]] = [
    ("annual_housing_requirement", "Annual housing requirement"),
    ("total_housing_requirement", "Total plan housing requirement"),
    ("housing_need_annual", "Housing need (annual, from a need study - distinct from the plan's own requirement)"),
    ("housing_need_total", "Housing need (total, from a need study)"),
    ("unmet_need", "Unmet need"),
    ("latest_reporting_period", "Latest housing delivery reporting period"),
    ("homes_delivered_latest_period", "Homes delivered in that period"),
    ("delivery_requirement_for_period", "Delivery requirement for that period"),
    ("delivery_surplus_or_shortfall", "Delivery surplus/shortfall for that period"),
    ("five_year_supply_years", "Five-year housing land supply (years)"),
    ("five_year_supply_base_date", "Five-year supply base date"),
    ("deliverable_supply_dwellings", "Deliverable supply (dwellings)"),
    ("five_year_requirement_dwellings", "Five-year requirement (dwellings)"),
    ("five_year_shortfall_or_surplus_dwellings", "Five-year supply shortfall/surplus (dwellings)"),
    ("buffer_percentage", "NPPF buffer applied (%)"),
]
# Plan-identity/status fields, kept as a separate list since they're
# rendered into the payload's own top-level identity block rather than the
# generic numeric "facts" dict (their trust/staleness still comes from the
# exact same evidence machinery either way).
STATUS_FACT_FIELDS: list[tuple[str, str]] = [
    ("status", "Plan status (normalised)"),
    ("raw_status", "Plan status (council's own wording)"),
    ("next_milestone", "Next milestone"),
    ("next_milestone_date", "Next milestone date"),
    ("expected_adoption_date", "Expected adoption date"),
]

_ALL_FACT_FIELDS = STATUS_FACT_FIELDS + FACT_FIELDS


def _fact_entries(session: Session, plan: LocalPlan) -> dict[str, dict]:
    """Every FACT_FIELDS/STATUS_FACT_FIELDS field, carrying its trust
    state, staleness, any conflicting pending values, and source
    title/page - built directly from app.policy.plan_evidence_view's own
    evidence assembly (the exact same data the Council Dashboard's
    detailed evidence section already renders from), not re-derived."""
    view = build_plan_evidence_view(session, plan)
    by_field = {
        entry["field"]: entry
        for section in ("status", "requirement", "delivery", "five_year_supply")
        for entry in view[section]
    }
    conflicts = get_conflicting_fields(session, plan.id)

    facts: dict[str, dict] = {}
    for field_name, label in _ALL_FACT_FIELDS:
        entry = by_field.get(field_name)
        if entry is None:
            continue
        facts[field_name] = {
            "label": label,
            "value": entry["value"],
            "trust": entry["trust"],
            "is_stale": entry["is_stale"],
            "has_conflict": field_name in conflicts,
            "conflicting_values": conflicts.get(field_name, []),
            "proposed_value": entry["pending_value"],
            "source_title": entry["source_document_title"],
            "source_page": entry["source_page"],
        }
    return facts


def build_summary_payload(session: Session, plan: LocalPlan) -> dict:
    """The deterministic, structured payload the AI model receives - Part
    1's own field list. Never includes raw document text or a PDF - every
    value here is already a short, discrete fact or count."""
    council = session.get(Council, plan.council_code)
    allocations = session.execute(
        select(LocalPlanSite).where(LocalPlanSite.local_plan_id == plan.id)
    ).scalars().all()
    progression_counts = Counter(a.progression_signal or "unknown" for a in allocations)

    facts = _fact_entries(session, plan)
    stale_fields = [f for f, e in facts.items() if e["is_stale"]]
    pending_fields = [f for f, e in facts.items() if e["proposed_value"] is not None]
    conflicting_fields = [f for f, e in facts.items() if e["has_conflict"]]

    return {
        "council_code": plan.council_code,
        "council_name": council.name if council else plan.council_code,
        "plan_id": plan.id,
        "plan_name": plan.plan_name,
        # Deterministic - status == "adopted" is the ONLY state that counts
        # as adopted (app.policy.status.PLAN_STATUSES); every other stage
        # is "emerging". Never left for the model to infer (Part 4: "Do
        # not claim an emerging allocation is adopted").
        "adopted_or_emerging": "adopted" if plan.status == "adopted" else "emerging",
        "plan_period_start": plan.plan_period_start,
        "plan_period_end": plan.plan_period_end,
        "facts": facts,
        "allocation_count": len(allocations),
        "matched_site_count": sum(1 for a in allocations if a.matched_site_id is not None),
        "progression_status_counts": dict(progression_counts),
        "last_checked": plan.last_checked.isoformat() if plan.last_checked else None,
        "stale_fields": stale_fields,
        "pending_fields": pending_fields,
        "conflicting_fields": conflicting_fields,
    }


def compute_evidence_fingerprint(payload: dict) -> str:
    """sha256 over only the narrative-relevant portion of the payload -
    fact values/trust-state/staleness/conflicts plus allocation and
    progression counts. Deliberately excludes last_checked, council_name,
    and source titles/pages: none of those change what the summary would
    actually SAY, so including them would force a regeneration (and AI
    cost) on every routine monitoring pass even when nothing a reader
    would notice has changed (Part 6: "use an evidence fingerprint so
    unchanged evidence does not incur repeated AI cost")."""
    fingerprint_source = {
        "adopted_or_emerging": payload["adopted_or_emerging"],
        "plan_period_start": payload["plan_period_start"],
        "plan_period_end": payload["plan_period_end"],
        "facts": {
            field: {
                "value": entry["value"], "trust": entry["trust"], "is_stale": entry["is_stale"],
                "has_conflict": entry["has_conflict"], "proposed_value": entry["proposed_value"],
            }
            for field, entry in payload["facts"].items()
        },
        "allocation_count": payload["allocation_count"],
        "matched_site_count": payload["matched_site_count"],
        "progression_status_counts": payload["progression_status_counts"],
    }
    canonical = json.dumps(fingerprint_source, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def should_regenerate(plan: LocalPlan, fingerprint: str, force: bool = False) -> bool:
    """Part 6's exact regeneration triggers: an explicit force (the UI's
    Refresh button), no summary has ever been generated, the trusted
    evidence has genuinely changed since the last generation, or the
    prompt/model version has moved on. Nothing else - in particular, a
    routine monitoring check that finds nothing new must NOT trigger this."""
    if force:
        return True
    if plan.ai_summary_text is None:
        return True
    if plan.ai_summary_evidence_fingerprint != fingerprint:
        return True
    if plan.ai_summary_prompt_version != PROMPT_VERSION:
        return True
    return False


def is_summary_stale(session: Session, plan: LocalPlan) -> bool:
    """True when the plan's LIVE evidence has moved since its summary was
    last generated, without generating anything or calling the AI - Part
    7's "stale-summary warning where the underlying evidence has changed".
    False (not stale) when there's no summary at all yet - that's a
    "missing" state for the UI to handle separately, not a staleness one."""
    if plan.ai_summary_text is None:
        return False
    payload = build_summary_payload(session, plan)
    return compute_evidence_fingerprint(payload) != plan.ai_summary_evidence_fingerprint


def _fmt_value(value) -> str:
    if value is None:
        return "not stated"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _render_fact_line(field_name: str, entry: dict) -> str:
    label = entry["label"]
    trust = entry["trust"]
    if trust == "missing":
        line = f"- {label}: UNAVAILABLE (no evidence found)"
    else:
        trust_label = {
            "confirmed": "confirmed by review",
            "auto_applied": "auto-applied (high-confidence extraction, not independently reviewed)",
        }.get(trust, trust)
        stale_bit = " [STALE - evidence may be out of date]" if entry["is_stale"] else ""
        source_bit = f" (source: {entry['source_title']}, page {entry['source_page']})" if entry["source_title"] else ""
        line = f"- {label}: {_fmt_value(entry['value'])} [{trust_label}]{stale_bit}{source_bit}"

    if entry["has_conflict"]:
        values = ", ".join(_fmt_value(v) for v in entry["conflicting_values"])
        line += f"\n  CONFLICTING PROPOSED VALUES awaiting review: {values} - do not treat any of these as settled."
    elif entry["proposed_value"] is not None:
        line += f"\n  PROPOSED (awaiting review, NOT yet trusted): {_fmt_value(entry['proposed_value'])}"
    return line


def build_summary_prompt(payload: dict) -> str:
    fact_lines = "\n".join(_render_fact_line(f, e) for f, e in payload["facts"].items())
    progression_lines = "\n".join(
        f"- {k}: {v}" for k, v in sorted(payload["progression_status_counts"].items())
    ) or "- (no allocations)"

    return f"""
You are writing a concise internal briefing on ONE UK council's Local Plan
for a residential land/planning acquisition professional, using ONLY the
verified PropertyAIgent evidence given below. Every fact below has already
been extracted and validated by this platform - restate and synthesise it,
never invent a figure, date, or status that isn't given here.

COUNCIL: {payload['council_name']} ({payload['council_code']})
PLAN: {payload['plan_name']}
STATUS: {payload['adopted_or_emerging'].upper()} (this is the ONLY trusted classification of this plan's stage - never describe this plan, or any of its allocations, as adopted unless this literally says ADOPTED)
PLAN PERIOD: {payload['plan_period_start'] or 'not stated'} to {payload['plan_period_end'] or 'not stated'}
LAST CHECKED: {payload['last_checked'] or 'never'}

FACTS (each tagged with its trust state - "confirmed by review" means a
human approved it; "auto-applied" means the pipeline applied it
automatically at high confidence without independent human review;
UNAVAILABLE means no evidence exists for this fact at all):
{fact_lines}

ALLOCATIONS: {payload['allocation_count']} total, {payload['matched_site_count']} matched to an existing scraped Site.
ALLOCATION PROGRESSION STATUS COUNTS:
{progression_lines}

RULES - follow every one of these exactly:
1. Never invent a number, date, or fact not given above.
2. Never perform arithmetic yourself - if a shortfall, surplus, percentage,
   or total isn't given directly above, do not calculate or estimate one.
3. A "PROPOSED (awaiting review...)" or "CONFLICTING PROPOSED VALUES" fact
   is NOT settled - describe it as a proposed/pending update awaiting
   review, never as the plan's current confirmed position. Where values
   conflict, say plainly that sources disagree and a decision is pending -
   never pick one yourself.
4. Never describe this plan, or any of its allocations, as adopted unless
   the STATUS line above literally says ADOPTED. An emerging plan stays
   emerging throughout the summary.
5. Where a fact is UNAVAILABLE, say it is unavailable/not stated - never
   guess or infer a plausible-sounding figure.
6. Where a fact is marked [STALE - evidence may be out of date], mention
   that this evidence may be out of date - do not present it as fresh.
7. "Housing need" and "housing requirement" are different concepts, not
   the same number under two names - if both are given and differ, say
   they are two distinct figures (need is what a study identifies;
   requirement is what the plan itself commits to), never describe either
   as wrong or in need of reconciliation.
8. key_risks and key_opportunities must each be short statements, each
   DIRECTLY traceable to a specific fact given above - never include one
   that isn't grounded in a fact from this payload.
9. evidence_gaps should name the specific UNAVAILABLE, stale, or pending
   items above that limit confidence in this summary - be specific, not
   generic.

Write:
- summary_text: 150-250 words, plain prose, no markdown headers, covering:
  current plan stage; adopted vs emerging; expected next step; housing
  requirement/need position; housing delivery position; five-year supply
  position; major risks or shortfalls SUPPORTED BY THE EVIDENCE ABOVE;
  number of allocations and matched Sites; evidence gaps/caveats.
- key_risks: a short list of evidence-supported risk statements (empty
  list if none are supported by the facts above).
- key_opportunities: a short list of evidence-supported opportunity
  statements (empty list if none are supported).
- evidence_gaps: a short list naming specific missing/stale/pending items.
"""


SUMMARY_SCHEMA = {
    "name": "local_plan_summary",
    "schema": {
        "type": "object",
        "properties": {
            "summary_text": {"type": "string"},
            "key_risks": {"type": "array", "items": {"type": "string"}},
            "key_opportunities": {"type": "array", "items": {"type": "string"}},
            "evidence_gaps": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary_text", "key_risks", "key_opportunities", "evidence_gaps"],
        "additionalProperties": False,
    },
}

# The decimal-point group only matches when at least one digit actually
# follows it. A real pilot run against live Stockport/Bury data surfaced
# why this matters: a year at the end of a sentence ("...adoption expected
# in 2027.") was being captured AS "2027." (trailing full stop included),
# which then never matched the allowed set's plain "2027" - a false-
# positive rejection of a perfectly well-supported figure, not a real
# hallucination. Requiring \d+ after the "\." means a genuine decimal like
# "1.77" still matches whole, while sentence-ending punctuation after a
# bare integer is correctly left outside the match.
_NUMBER_PATTERN = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers_in(text: str) -> set[str]:
    return {m.replace(",", "") for m in _NUMBER_PATTERN.findall(text)}


def _allowed_numbers(payload: dict) -> set[str]:
    """Every numeric token that legitimately appears anywhere in the
    payload the model was given - the only numbers its own output is
    allowed to contain (see validate_summary_output)."""
    allowed: set[str] = set()

    def _add(value) -> None:
        if value is None:
            return
        allowed.update(_numbers_in(str(value)))
        if isinstance(value, float) and value == int(value):
            allowed.add(str(int(value)))

    _add(payload.get("plan_period_start"))
    _add(payload.get("plan_period_end"))
    _add(payload.get("allocation_count"))
    _add(payload.get("matched_site_count"))
    for count in payload.get("progression_status_counts", {}).values():
        _add(count)
    for entry in payload["facts"].values():
        _add(entry["value"])
        _add(entry["proposed_value"])
        for v in entry.get("conflicting_values", []):
            _add(v)
    return allowed


def validate_summary_output(payload: dict, structured_output: dict) -> tuple[bool, list[str]]:
    """Deterministic post-generation check (Part 4/Part 8: "AI output
    cannot introduce unsupported figures") - every numeric token of two or
    more digits anywhere in the model's own output must be traceable to a
    value actually present in the payload it was given. Single-digit
    numbers are excused (routine phrasing like "a 5-year supply" or "one
    allocation" would otherwise fail every summary on harmless boilerplate
    that isn't really a claimed figure). Returns (is_valid, unsupported) -
    a non-empty list means the output must be rejected, never persisted."""
    allowed = _allowed_numbers(payload)
    all_text = " ".join([
        structured_output.get("summary_text", ""),
        *structured_output.get("key_risks", []),
        *structured_output.get("key_opportunities", []),
        *structured_output.get("evidence_gaps", []),
    ])
    found = _numbers_in(all_text)
    unsupported = sorted(n for n in found if len(n.lstrip("0")) >= 2 and n not in allowed)
    return len(unsupported) == 0, unsupported


def _persisted_summary_result(plan: LocalPlan, *, regenerated: bool, rejected: bool, rejection_reason: list[str] | None) -> dict:
    return {
        "regenerated": regenerated, "rejected": rejected, "rejection_reason": rejection_reason,
        "summary_text": plan.ai_summary_text,
        "key_risks": json.loads(plan.ai_summary_key_risks) if plan.ai_summary_key_risks else [],
        "key_opportunities": json.loads(plan.ai_summary_key_opportunities) if plan.ai_summary_key_opportunities else [],
        "evidence_gaps": json.loads(plan.ai_summary_evidence_gaps) if plan.ai_summary_evidence_gaps else [],
        "generated_at": plan.ai_summary_generated_at,
        "model": plan.ai_summary_model, "prompt_version": plan.ai_summary_prompt_version,
    }


def generate_local_plan_summary(session: Session, client: OpenAI, plan: LocalPlan, force: bool = False) -> dict:
    """Returns a dict with "regenerated"/"rejected"/"rejection_reason" plus
    the summary content itself (freshly generated, or - when regeneration
    wasn't due, or the model's output failed validation - whatever is
    already persisted on the plan, never silently replaced by an
    unsupported output). Only calls the AI model when should_regenerate
    says a real trigger applies (Part 6) - an unchanged plan re-viewed or
    re-checked with no new evidence costs nothing."""
    payload = build_summary_payload(session, plan)
    fingerprint = compute_evidence_fingerprint(payload)

    if not should_regenerate(plan, fingerprint, force=force):
        return _persisted_summary_result(plan, regenerated=False, rejected=False, rejection_reason=None)

    prompt = build_summary_prompt(payload)
    response = client.responses.create(
        model=MODEL, input=prompt,
        text={"format": {"type": "json_schema", "name": SUMMARY_SCHEMA["name"], "schema": SUMMARY_SCHEMA["schema"], "strict": True}},
    )
    structured = json.loads(response.output_text)

    is_valid, unsupported = validate_summary_output(payload, structured)
    if not is_valid:
        # Never persist a rejected output - the plan keeps whatever
        # summary (or absence of one) it already had.
        return _persisted_summary_result(plan, regenerated=False, rejected=True, rejection_reason=unsupported)

    now = dt.datetime.now(dt.timezone.utc)
    plan.ai_summary_text = structured["summary_text"]
    plan.ai_summary_key_risks = json.dumps(structured["key_risks"])
    plan.ai_summary_key_opportunities = json.dumps(structured["key_opportunities"])
    plan.ai_summary_evidence_gaps = json.dumps(structured["evidence_gaps"])
    plan.ai_summary_generated_at = now
    plan.ai_summary_evidence_fingerprint = fingerprint
    plan.ai_summary_model = MODEL
    plan.ai_summary_prompt_version = PROMPT_VERSION
    session.commit()

    return {
        "regenerated": True, "rejected": False, "rejection_reason": None,
        "summary_text": structured["summary_text"], "key_risks": structured["key_risks"],
        "key_opportunities": structured["key_opportunities"], "evidence_gaps": structured["evidence_gaps"],
        "generated_at": now, "model": MODEL, "prompt_version": PROMPT_VERSION,
    }
