"""GM Allocation <-> Site dry-run candidate matching report (Stage 2A),
extended with a controlled production write mode (Stage 2B, CLI).

Dry-run (the default, no flags needed) is READ ONLY - makes zero database
mutations. See app.policy.allocation_site_dry_run_matching for the full
design rationale (existing-matcher reuse, reporting-only classification,
multi-site safeguard, and the write-mode semantics below).

    python -m scripts.dry_run_gm_allocation_site_matching
    python -m scripts.dry_run_gm_allocation_site_matching --council bolton

Production write mode requires BOTH flags together - --execute alone does
nothing but print an error (same deliberate-friction pattern as
scripts.ingest_gm_local_plan_baseline). Only HIGH_CONFIDENCE_CANDIDATE
allocations are written - an ACCEPTED related-Site relationship, per the
semantic invariant in app.policy.allocation_site_dry_run_matching's own
docstring. REVIEW_CANDIDATE, AMBIGUOUS, and NO_CANDIDATE all produce ZERO
persistence here: a REVIEW_CANDIDATE only ever gets written via a human's
explicit, revalidated Confirm action in the Allocation Match Review UI
(app.policy.allocation_site_dry_run_matching.confirm_review_candidate):

    python -m scripts.dry_run_gm_allocation_site_matching --execute --confirm YES-WRITE-GM-ALLOCATION-SITE-MATCHES
"""
from __future__ import annotations

import argparse
import sys

from app.db.session import get_session, init_db
from app.policy.allocation_site_dry_run_matching import (
    AMBIGUOUS,
    HIGH_CONFIDENCE_CANDIDATE,
    NO_CANDIDATE,
    REVIEW_CANDIDATE,
    run_controlled_write,
    run_dry_run_matching,
    summarize_results,
)

CONFIRM_PHRASE = "YES-WRITE-GM-ALLOCATION-SITE-MATCHES"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--council", action="append", default=None, help="Restrict to one council code (repeatable). Default: all councils.")
    parser.add_argument("--examples-per-category", type=int, default=10, help="How many result examples to print per classification (default 10).")
    parser.add_argument("--execute", action="store_true", help="Write HIGH_CONFIDENCE_CANDIDATE/REVIEW_CANDIDATE matches to production. Requires --confirm with the exact phrase below as well.")
    parser.add_argument("--confirm", default=None, help=f"Must exactly equal '{CONFIRM_PHRASE}' to actually write. Ignored unless --execute is also given.")
    return parser.parse_args()


def _print_candidate(candidate, indent: str = "      ") -> None:
    print(f"{indent}Site {candidate.site_id}: {candidate.site_name!r} "
          f"(score={candidate.score:.1f}, total_units={candidate.total_units}, "
          f"applications={candidate.application_count})")


def _print_result(result) -> None:
    print(f"  [{result.classification}] allocation {result.allocation_id} "
          f"({result.council}/{result.policy_reference!r}) {result.allocation_name!r} "
          f"capacity={result.allocation_capacity} review_status={result.current_review_status!r}")
    print(f"      reason: {result.reason}")
    for candidate in result.candidates:
        _print_candidate(candidate)
    for candidate in result.near_miss_candidates:
        _print_candidate(candidate, indent="      (near-miss) ")


def main() -> None:
    args = parse_args()

    production_mode = args.execute
    if production_mode and args.confirm != CONFIRM_PHRASE:
        print(f"[gm-allocation-site-match] --execute requires --confirm '{CONFIRM_PHRASE}' exactly - refusing to write.", file=sys.stderr)
        sys.exit(2)

    init_db()
    session = get_session()

    if production_mode:
        print("[gm-allocation-site-match] PRODUCTION WRITE MODE - this WILL write to the database\n")
        print("Only HIGH_CONFIDENCE_CANDIDATE allocations are written automatically. REVIEW_CANDIDATE")
        print("produces zero persistence here - it is only ever written via a human's explicit,")
        print("revalidated Confirm action in the Allocation Match Review UI.\n")
        write_result = run_controlled_write(session, council_codes=args.council)
        print("=== WRITE RESULT ===")
        print(f"written HIGH_CONFIDENCE_CANDIDATE: {len(write_result['written_high_confidence'])} -> {write_result['written_high_confidence']}")
        print(f"skipped (production drift): {len(write_result['skipped_drift'])} -> {write_result['skipped_drift']}")
        print(f"REVIEW_CANDIDATE untouched (zero persistence): {len(write_result['review_candidates_untouched'])}")
        print(f"AMBIGUOUS not written: {len(write_result['ambiguous_not_written'])}")
        print(f"NO_CANDIDATE untouched: {len(write_result['no_candidate_untouched'])}")
        print("\n=== RESULT ===")
        print("PRODUCTION WRITE COMPLETE")
        return

    print("[gm-allocation-site-match] DRY RUN - zero database mutations will be made\n")
    dry_run = run_dry_run_matching(session, council_codes=args.council)
    summary = summarize_results(dry_run)

    print("=== MATCHING BASIS ===")
    print(dry_run["matching_basis"])

    print("\n=== BASELINE ===")
    print(f"total allocations: {summary['total_allocations']}")
    print(f"already matched: {summary['already_matched']}")
    print(f"unmatched evaluated: {summary['unmatched_evaluated']}")

    print("\n=== CLASSIFICATION COUNTS ===")
    print(f"HIGH_CONFIDENCE_CANDIDATE: {summary['high_confidence_candidates']}")
    print(f"REVIEW_CANDIDATE: {summary['review_candidates']}")
    print(f"AMBIGUOUS: {summary['ambiguous_candidates']}")
    print(f"NO_CANDIDATE: {summary['no_candidate']}")

    print("\n=== BY COUNCIL ===")
    for council, counts in sorted(summary["by_council"].items()):
        print(f"  {council}: {counts}")

    print("\n=== MATCH-SCORE DISTRIBUTION (all candidate + near-miss scores) ===")
    for bucket, count in summary["score_distribution"].items():
        print(f"  {bucket}: {count}")

    for label, code in (
        ("HIGH_CONFIDENCE_CANDIDATE", HIGH_CONFIDENCE_CANDIDATE),
        ("REVIEW_CANDIDATE", REVIEW_CANDIDATE),
        ("AMBIGUOUS", AMBIGUOUS),
        ("NO_CANDIDATE", NO_CANDIDATE),
    ):
        matching = [r for r in dry_run["results"] if r.classification == code]
        print(f"\n=== {label} examples ({len(matching)} total) ===")
        for result in matching[: args.examples_per_category]:
            _print_result(result)

    print("\n=== RESULT ===")
    print("DRY RUN COMPLETE - NO WRITES MADE")


if __name__ == "__main__":
    main()
