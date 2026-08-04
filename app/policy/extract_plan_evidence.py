"""Runnable command wiring app.extraction.plan_evidence (AI extraction),
app.policy.document_selection (routing) and app.policy.evidence_validation
(deterministic checks) into real PolicyChangeEvent proposals (Sprint 3B,
"AI Local Plan Evidence Extraction", Part 9).

    python -m app.policy.extract_plan_evidence --council stockport \\
        --pdf data/local_plans/stockport/LocalPlan.pdf --pages 1-20 \\
        --source-type adopted_plan --title "Stockport Local Plan" \\
        --source-url "https://.../LocalPlan.pdf"

This mirrors ingest_local_plan.py's own "one document per invocation"
shape (Part 9: "one source document") rather than inventing an automated
document-fetch pipeline this codebase doesn't otherwise have -
MonitoredSource records WHAT to watch, but nothing here downloads a
council's PDF on your behalf; --pdf is always a file you already have
locally.

Like ingest_local_plan.py, this never silently overwrites an EXISTING
trusted LocalPlan field. Every accepted fact becomes its own
PolicyChangeEvent; a fact is only auto-applied when the field was
genuinely null beforehand AND the extraction itself reported "high"
confidence (see classify_evidence_confidence) - anything that would CHANGE
an already-known value, or that was extracted at anything less than high
confidence, is always queued for review. Re-running against an unchanged
document is idempotent: a fact whose extracted value already matches the
current trusted value creates no event at all, unless --reprocess-unchanged
is passed explicitly.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LocalPlan, PolicyChangeEvent
from app.extraction.plan_evidence import (
    CATEGORIES,
    MODEL,
    PROMPT_VERSION,
    extract_pdf_pages,
    extract_plan_evidence,
    format_pages_for_prompt,
)
from app.policy.document_selection import DOCUMENT_TYPE_TO_CATEGORIES
from app.policy.evidence_validation import validate_facts
from app.policy.history import snapshot_field

# app.extraction.plan_evidence field names that don't match their LocalPlan
# column name 1:1 - the extraction schema's names were chosen to read
# clearly inside a prompt; app.policy.review._RESOLVABLE_FIELDS_PLAN (and
# every existing LocalPlan column) use the model's own established names.
# Every other extraction field name matches its LocalPlan column exactly.
EXTRACTION_FIELD_TO_MODEL_FIELD = {
    "raw_plan_status": "raw_status",
    "total_plan_housing_requirement": "total_housing_requirement",
}

# gpt-4o-mini pricing per 1M tokens, as of this sprint - a best-effort
# estimate for Part 9's "total model usage/estimated cost where available",
# not a billing-accurate figure. OpenAI's own usage dashboard is the source
# of truth for actual spend.
_INPUT_COST_PER_1M = 0.15
_OUTPUT_COST_PER_1M = 0.60


def _model_field(extraction_field: str) -> str:
    return EXTRACTION_FIELD_TO_MODEL_FIELD.get(extraction_field, extraction_field)


def classify_evidence_confidence(current_value, extraction_confidence: str | None) -> str:
    """"auto_applied" or "needs_review". A fact is only safe to auto-apply
    when BOTH: the field was genuinely empty before (so there is no
    existing trusted value it could silently overwrite or contradict) AND
    the extraction itself reported "high" confidence. Anything that would
    change an already-known value, or that was reported at anything less
    than high confidence, is queued for review - matching Part 7's own
    examples ("annual housing requirement changed", "confidence below
    threshold"), and deliberately more conservative than strictly
    necessary, the same reasoning as
    app.policy.change_detection._AUTO_APPLY_EVENT_TYPES."""
    if current_value is not None:
        return "needs_review"
    if extraction_confidence != "high":
        return "needs_review"
    return "auto_applied"


def _confidence_to_float(label: str | None) -> float | None:
    return {"high": 0.9, "medium": 0.6, "low": 0.3}.get(label)


def _estimate_cost(usage_events: list) -> tuple[int, int, float]:
    input_tokens = sum(getattr(u, "input_tokens", 0) or 0 for u in usage_events)
    output_tokens = sum(getattr(u, "output_tokens", 0) or 0 for u in usage_events)
    cost = (input_tokens / 1_000_000) * _INPUT_COST_PER_1M + (output_tokens / 1_000_000) * _OUTPUT_COST_PER_1M
    return input_tokens, output_tokens, cost


def _find_pending_proposal(session: Session, local_plan_id: int, field: str, value) -> PolicyChangeEvent | None:
    """An auto-applied fact's idempotency is covered for free by comparing
    against plan's own current value (once applied, current_value ==
    parsed_value on the next run). A needs_review fact never touches the
    trusted field though, so without this check the SAME still-pending
    proposal would be re-created on every single re-run against an
    unchanged document - exactly the duplicate-event outcome Part 9
    prohibits. Mirrors app.policy.monitor._has_pending_change_event's own
    "don't queue a second event for something already queued" pattern."""
    pending = session.execute(
        select(PolicyChangeEvent).where(
            PolicyChangeEvent.local_plan_id == local_plan_id,
            PolicyChangeEvent.event_type == "plan_evidence_proposed",
            PolicyChangeEvent.review_status == "needs_review",
        )
    ).scalars().all()
    for event in pending:
        if not event.proposed_data:
            continue
        if json.loads(event.proposed_data).get(field) == value:
            return event
    return None


def resolve_plan(session: Session, council_code: str, plan_id: int | None) -> LocalPlan:
    if plan_id is not None:
        plan = session.get(LocalPlan, plan_id)
        if plan is None or plan.council_code != council_code:
            raise ValueError(f"No LocalPlan {plan_id} found for council {council_code!r}")
        return plan

    plans = session.execute(select(LocalPlan).where(LocalPlan.council_code == council_code)).scalars().all()
    if len(plans) == 1:
        return plans[0]
    if not plans:
        raise ValueError(f"No LocalPlan records exist yet for council {council_code!r} - run ingest_local_plan.py first.")
    options = ", ".join(f"{p.id} ({p.plan_name} / {p.plan_version})" for p in plans)
    raise ValueError(f"Council {council_code!r} has more than one LocalPlan - pass --plan-id to disambiguate: {options}")


def run_extraction(
    session: Session,
    client: OpenAI,
    plan: LocalPlan,
    pdf_path: str,
    first_page: int,
    last_page: int,
    source_type: str,
    category_override: str | None = None,
    source_title: str | None = None,
    source_url: str | None = None,
    dry_run: bool = False,
    reprocess_unchanged: bool = False,
) -> dict:
    """Runs every extraction category eligible for source_type (or just
    category_override, if given) against pdf_path[first_page:last_page],
    validates every fact, and turns each accepted one into a
    PolicyChangeEvent - or, in dry_run mode, just reports what it would
    have done without writing anything to the database or committing.

    Returns a stats dict covering every count Part 9 asks the CLI to
    print: categories/passes run, facts extracted/rejected, events
    created/auto-applied/needing review, facts skipped as unchanged
    (idempotency), and token usage/estimated cost."""
    if category_override:
        if category_override not in CATEGORIES:
            raise ValueError(f"Unknown category {category_override!r} - expected one of {sorted(CATEGORIES)}")
        categories = [category_override]
    else:
        categories = sorted(DOCUMENT_TYPE_TO_CATEGORIES.get(source_type, frozenset()))

    stats = {
        "categories": categories, "passes_run": 0,
        "facts_extracted": 0, "facts_rejected": 0, "unchanged_skipped": 0,
        "events_created": 0, "auto_applied": 0, "needs_review": 0,
        "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0,
        "proposals": [],
    }
    if not categories:
        return stats

    pages = extract_pdf_pages(pdf_path, first_page, last_page)
    source_text = format_pages_for_prompt(pages)
    now = dt.datetime.now(dt.timezone.utc)
    usage_events: list = []

    for category in categories:
        stats["passes_run"] += 1
        raw_facts = extract_plan_evidence(client, category, source_text, usage_sink=usage_events)
        validated = validate_facts(raw_facts)

        for result in validated:
            if not result["is_valid"]:
                if result["rejection_reason"] is not None:
                    stats["facts_rejected"] += 1
                continue
            if result["parsed_value"] is None:
                continue  # genuinely "not found" in the source - nothing to propose

            stats["facts_extracted"] += 1
            model_field = _model_field(result["field"])
            current_value = getattr(plan, model_field, None)
            parsed_value = result["parsed_value"]

            if current_value == parsed_value and not reprocess_unchanged:
                stats["unchanged_skipped"] += 1
                continue

            if not reprocess_unchanged and _find_pending_proposal(session, plan.id, model_field, parsed_value) is not None:
                stats["unchanged_skipped"] += 1
                continue

            raw_fact = result["raw_fact"]
            classification = classify_evidence_confidence(current_value, raw_fact.get("confidence"))
            stats["proposals"].append({
                "field": model_field, "old_value": current_value, "new_value": parsed_value,
                "classification": classification, "source_page": raw_fact.get("source_page"),
            })

            if not dry_run:
                if classification == "auto_applied":
                    snapshot_field(session, plan, field_name=model_field, old_value=current_value,
                                    new_value=parsed_value, change_reason="plan_evidence_proposed")
                    setattr(plan, model_field, parsed_value)

                session.add(PolicyChangeEvent(
                    local_plan_id=plan.id, event_type="plan_evidence_proposed",
                    old_value=None if current_value is None else str(current_value),
                    new_value=str(parsed_value),
                    detail=f"{model_field} proposed from {source_title or pdf_path} (category={category}).",
                    proposed_data=json.dumps({model_field: parsed_value}),
                    source_document_url=source_url, source_page=raw_fact.get("source_page"),
                    confidence=_confidence_to_float(raw_fact.get("confidence")),
                    source_document_title=source_title, source_excerpt=raw_fact.get("source_excerpt"),
                    extraction_method="ai_structured_extraction", extraction_model=MODEL,
                    extraction_prompt_version=PROMPT_VERSION, extracted_at=now,
                    auto_applied=classification == "auto_applied", review_status=classification,
                ))

            stats["events_created"] += 1
            stats[classification] += 1

    stats["input_tokens"], stats["output_tokens"], stats["estimated_cost_usd"] = _estimate_cost(usage_events)

    if not dry_run:
        plan.last_checked = now
        session.commit()

    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--council", required=True)
    parser.add_argument("--plan-id", type=int, default=None, help="Disambiguates when a council has more than one LocalPlan")
    parser.add_argument("--pdf", required=True, help="Path to the downloaded policy document")
    parser.add_argument("--pages", default=None, help="1-indexed inclusive page range, e.g. 1-20 (default: whole document)")
    parser.add_argument("--source-type", required=True,
                         help="MonitoredSource.source_type - determines which extraction categories run "
                              "(see app.policy.document_selection.DOCUMENT_TYPE_TO_CATEGORIES); a source type "
                              "with no eligible category means this run does nothing, by design.")
    parser.add_argument("--category", default=None, choices=sorted(CATEGORIES),
                         help="Force a single extraction category instead of --source-type's full eligible set")
    parser.add_argument("--title", default=None, help="Human-readable document title, stored as evidence")
    parser.add_argument("--source-url", default=None, help="Document URL, stored as evidence")
    parser.add_argument("--dry-run", action="store_true", help="Extract and validate but write nothing to the database")
    parser.add_argument("--reprocess-unchanged", action="store_true",
                         help="Create a change event even when the extracted value equals the current trusted "
                              "value (off by default - re-running unchanged inputs must not create duplicate events)")
    return parser.parse_args()


def _resolve_page_range(pdf_path: str, pages_arg: str | None) -> tuple[int, int]:
    if pages_arg:
        first, last = (int(p) for p in pages_arg.split("-"))
        return first, last
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        return 1, len(pdf.pages)


def main() -> None:
    args = parse_args()
    load_dotenv(override=True)
    from app.db.session import get_session, init_db  # local import: keeps this module importable/testable without touching the real DB

    init_db()
    session = get_session()
    client = OpenAI()

    plan = resolve_plan(session, args.council, args.plan_id)
    first_page, last_page = _resolve_page_range(args.pdf, args.pages)

    stats = run_extraction(
        session, client, plan, args.pdf, first_page, last_page, args.source_type,
        category_override=args.category, source_title=args.title, source_url=args.source_url,
        dry_run=args.dry_run, reprocess_unchanged=args.reprocess_unchanged,
    )

    mode = "DRY RUN - nothing written" if args.dry_run else "applied"
    print(f"[plan-evidence] {args.council} plan {plan.id} ({plan.plan_name!r}), pages {first_page}-{last_page} [{mode}]")
    print(f"  categories run: {stats['categories'] or '(none - source-type has no eligible category)'}")
    print(f"  extraction passes: {stats['passes_run']}")
    print(f"  facts extracted: {stats['facts_extracted']} | rejected by validation: {stats['facts_rejected']} | "
          f"unchanged (skipped): {stats['unchanged_skipped']}")
    print(f"  change events: {stats['events_created']} ({stats['auto_applied']} auto-applied, "
          f"{stats['needs_review']} needing review)")
    print(f"  model usage: {stats['input_tokens']} input / {stats['output_tokens']} output tokens - "
          f"est. cost ${stats['estimated_cost_usd']:.4f}")
    for p in stats["proposals"]:
        print(f"    - {p['field']}: {p['old_value']!r} -> {p['new_value']!r} [{p['classification']}] (page {p['source_page']})")


if __name__ == "__main__":
    main()
