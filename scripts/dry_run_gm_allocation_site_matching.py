"""GM Allocation <-> Site dry-run candidate matching report (Stage 2A, CLI).

READ ONLY. Makes zero database mutations - never calls session.add/flush/
commit, never sets matched_site_id/match_confidence/review_status/
latitude/longitude on anything. See app.policy.allocation_site_dry_run_matching
for the full design rationale (existing-matcher reuse, reporting-only
classification, multi-site safeguard).

    python -m scripts.dry_run_gm_allocation_site_matching
    python -m scripts.dry_run_gm_allocation_site_matching --council bolton
"""
from __future__ import annotations

import argparse

from app.db.session import get_session, init_db
from app.policy.allocation_site_dry_run_matching import (
    AMBIGUOUS,
    HIGH_CONFIDENCE_CANDIDATE,
    NO_CANDIDATE,
    REVIEW_CANDIDATE,
    run_dry_run_matching,
    summarize_results,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--council", action="append", default=None, help="Restrict to one council code (repeatable). Default: all councils.")
    parser.add_argument("--examples-per-category", type=int, default=10, help="How many result examples to print per classification (default 10).")
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
    init_db()
    session = get_session()

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
