"""AI Allocation Intelligence Summary (Phase 1 Local Plan Intelligence) CLI -
the explicit, operator-invoked generation/refresh runner for
app.reporting.allocation_intelligence_summary.

Orchestrates ONLY that module's own generate_allocation_intelligence_summary
- no independent context-building, prompt, or persistence logic here,
mirroring scripts/cleanup_allocation_site_relationships.py's own "thin CLI
wrapper" shape.

Dry-run (the default, no flags needed) is READ ONLY - makes zero database
mutations and calls OpenAI zero times:

    python -m scripts.generate_allocation_intelligence_summaries
    python -m scripts.generate_allocation_intelligence_summaries --allocation-id 51
    python -m scripts.generate_allocation_intelligence_summaries --allocation-ids 51,53,73
    python -m scripts.generate_allocation_intelligence_summaries --stale
    python -m scripts.generate_allocation_intelligence_summaries --all-eligible

Production write mode (which DOES call OpenAI) requires BOTH flags together
(same deliberate-friction pattern as every other Stage 2/3/4 write-capable
script in this codebase):

    python -m scripts.generate_allocation_intelligence_summaries --stale --execute --confirm YES-GENERATE-ALLOCATION-INTELLIGENCE-SUMMARIES

FAIL CLOSED: any other value for --confirm (missing, misspelled, or simply
absent) with --execute given refuses to write/call OpenAI and exits
non-zero.

TARGETING (--stale is the default when no explicit target is given -
deliberately the narrowest, cheapest default, never --all-eligible):
  --allocation-id N       exactly one allocation
  --allocation-ids N,N,N  a specific set of allocations
  --stale                 every allocation whose summary is missing or
                           whose live context has moved since last
                           generated (is_allocation_summary_stale / no
                           AllocationIntelligenceSummary row yet)
  --all-eligible          every allocation with at least one related Site
                           OR a stated allocation capacity (the same
                           "insufficient context" gate the dry-run report
                           itself uses) - the broadest, most expensive
                           target; --execute --all-eligible is deliberately
                           NOT run anywhere in this codebase's own tooling
                           without a separate, explicit Product Owner
                           decision to batch-generate the full corpus."""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.db.models import LocalPlanSite
from app.db.session import get_session, init_db
from app.reporting.allocation_intelligence_summary import (
    PROMPT_VERSION,
    generate_allocation_intelligence_summary,
    get_allocation_summary,
    has_sufficient_context_for_summary,
    is_allocation_summary_stale,
)

CONFIRM_PHRASE = "YES-GENERATE-ALLOCATION-INTELLIGENCE-SUMMARIES"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--allocation-id", type=int, default=None, help="Target exactly one allocation by id.")
    target.add_argument("--allocation-ids", type=str, default=None, help="Comma-separated allocation ids to target.")
    target.add_argument("--stale", action="store_true", help="Target every allocation with a missing or stale summary (the default target).")
    target.add_argument("--all-eligible", action="store_true", help="Target every allocation with sufficient context, regardless of freshness.")
    parser.add_argument("--execute", action="store_true", help="Call OpenAI and write to production. Requires --confirm with the exact phrase below as well.")
    parser.add_argument("--confirm", default=None, help=f"Must exactly equal '{CONFIRM_PHRASE}' to actually execute. Ignored unless --execute is also given.")
    return parser.parse_args()


def _select_targets(session, args: argparse.Namespace) -> list[LocalPlanSite]:
    if args.allocation_id is not None:
        allocation = session.get(LocalPlanSite, args.allocation_id)
        return [allocation] if allocation is not None else []
    if args.allocation_ids is not None:
        ids = [int(x) for x in args.allocation_ids.split(",") if x.strip()]
        return [a for a in (session.get(LocalPlanSite, i) for i in ids) if a is not None]
    if args.all_eligible:
        return list(session.execute(select(LocalPlanSite)).scalars().all())
    # --stale is the default target whether or not the flag was passed explicitly.
    return list(session.execute(select(LocalPlanSite)).scalars().all())


def _classify(session, allocation: LocalPlanSite, *, only_stale: bool) -> str:
    """One of: missing | fresh | stale | insufficient_context | would_generate -
    the SINGLE eligibility decision both _run_dry_run and _run_execute call
    (V7 Quality Hardening Amendment - previously _run_execute hand-wrote its
    own separate already_fresh/only_stale skip check that had DRIFTED from
    this function's own classification: when only_stale is False (an
    explicit --allocation-id/--allocation-ids/--all-eligible target),
    _run_execute's own "if only_stale and already_fresh: skip" is a no-op -
    it attempts EVERY sufficient-context target regardless of freshness -
    but this function used to report an already-fresh target as "fresh"
    (not counted as "would generate") REGARDLESS of only_stale, so dry-run
    under-reported exactly what a real --allocation-ids execute run would
    actually attempt. Confirmed against real production behaviour: a
    controlled --allocation-ids 51,32,66,196 dry-run reported "fresh: 1,
    would generate: 3" immediately before an execute run that attempted
    all four and regenerated allocation 51. Fixed by making the classifier
    itself the single source of truth for "would this be attempted" -
    when only_stale is False, every sufficient-context target is always
    "would_generate", exactly mirroring _run_execute's real skip logic;
    _run_execute now calls this SAME function instead of re-deriving the
    decision inline, so the two paths can never drift apart again."""
    if not has_sufficient_context_for_summary(session, allocation):
        return "insufficient_context"
    if not only_stale:
        # An explicit target list or --all-eligible is a "generate/refresh
        # these specific allocations" request - real execute behaviour
        # attempts every one of them regardless of freshness (see
        # _run_execute's own classification-driven skip below), so dry-run
        # must report the same thing, never "fresh".
        return "would_generate"
    summary = get_allocation_summary(session, allocation.id)
    if summary is None or summary.headline is None:
        return "missing"
    if is_allocation_summary_stale(session, allocation):
        return "stale"
    return "fresh"


def _run_dry_run(session, args: argparse.Namespace) -> None:
    print("[generate-allocation-intelligence-summaries] DRY RUN - zero database mutations, zero OpenAI calls\n")
    only_stale = not (args.allocation_id is not None or args.allocation_ids is not None or args.all_eligible)
    targets = _select_targets(session, args)
    print(f"targets considered: {len(targets)}")

    counts = {"missing": 0, "fresh": 0, "stale": 0, "would_generate": 0, "insufficient_context": 0}
    would_generate_ids: list[int] = []
    for allocation in targets:
        classification = _classify(session, allocation, only_stale=only_stale)
        counts[classification] = counts.get(classification, 0) + 1
        if classification in ("stale", "missing", "would_generate"):
            would_generate_ids.append(allocation.id)
            print(f"  [{classification}] allocation={allocation.id} ({allocation.policy_reference}) {allocation.site_name}")

    print("\n=== SUMMARY ===")
    print(f"eligible: {len(targets) - counts['insufficient_context']}")
    print(f"missing summary: {counts['missing']}")
    print(f"fresh: {counts['fresh']}")
    print(f"stale: {counts['stale']}")
    print(f"would generate: {len(would_generate_ids)}")
    print(f"insufficient context: {counts['insufficient_context']}")
    print(f"errors: 0 (dry run never calls OpenAI)")
    print(f"\nprompt version: {PROMPT_VERSION}")
    print("\n=== RESULT ===")
    print("DRY RUN COMPLETE - NO WRITES MADE, NO OPENAI CALLS MADE")


def _run_execute(session, args: argparse.Namespace) -> None:
    from openai import OpenAI

    print("[generate-allocation-intelligence-summaries] EXECUTE MODE - this WILL call OpenAI and write to production\n")
    only_stale = not (args.allocation_id is not None or args.allocation_ids is not None or args.all_eligible)
    targets = _select_targets(session, args)
    print(f"targets considered: {len(targets)}")

    client = OpenAI()  # reads OPENAI_API_KEY from the environment, same convention as every other AI call site in this codebase

    generated = regenerated_count = skipped = errors = rejected = 0
    for allocation in targets:
        # V7 Quality Hardening Amendment - calls the SAME _classify used by
        # _run_dry_run, rather than a separately hand-written freshness
        # check, so dry-run's reporting and execute's real behaviour can
        # never drift apart again (see _classify's own comment for the
        # real production symptom this fixes).
        classification = _classify(session, allocation, only_stale=only_stale)
        if classification in ("insufficient_context", "fresh"):
            skipped += 1
            continue
        try:
            result = generate_allocation_intelligence_summary(session, client, allocation)
        except Exception as e:
            errors += 1
            print(f"  [error] allocation={allocation.id}: {e}")
            continue
        if result.rejected:
            rejected += 1
            print(f"  [rejected] allocation={allocation.id}: {result.rejection_reason}")
        elif result.regenerated:
            generated += 1
            regenerated_count += 1
            print(f"  [generated] allocation={allocation.id}: {result.headline}")
        else:
            skipped += 1

    print("\n=== EXECUTE RESULT ===")
    print(f"generated: {generated}")
    print(f"rejected (ungrounded output, last valid summary retained): {rejected}")
    print(f"skipped (already fresh or insufficient context): {skipped}")
    print(f"errors: {errors}")
    print("\n=== RESULT ===")
    print("EXECUTE COMPLETE")


def main() -> None:
    args = parse_args()

    production_mode = args.execute
    if production_mode and args.confirm != CONFIRM_PHRASE:
        print(
            f"[generate-allocation-intelligence-summaries] --execute requires --confirm '{CONFIRM_PHRASE}' exactly - refusing to run.",
            file=sys.stderr,
        )
        sys.exit(2)

    init_db()
    session = get_session()

    if production_mode:
        _run_execute(session, args)
        return

    _run_dry_run(session, args)


if __name__ == "__main__":
    main()
