"""One-off, idempotent application of Pilot Readiness PR-2's ("Existing
Allocation <-> Site Matches") individual manual review of every allocation
that was in needs_confirmation at the start of the sprint (11 rows).

Each decision below was reached by reading the allocation's name/policy
reference against the matched Site's actual address AND its linked
Application(s)' address/proposal text (see the sprint's own PR-2 report for
the full evidentiary reasoning per allocation) - never confidence alone
(Part 11: "Confidence is evidence, not authority").

Safe to run more than once: each allocation is only acted on if it is
still in its expected starting state (matched_site_id equal to what this
script expects AND review_status == "needs_confirmation") - a rerun after
the first successful run finds nothing left to do and changes nothing.

    python -m scripts.apply_pr2_allocation_match_review [--dry-run]
"""
from __future__ import annotations

import argparse

from app.db.models import LocalPlanSite
from app.db.session import get_session, init_db
from app.policy.site_match_review import confirm_site_match, reject_site_match

REVIEWED_BY = "PR-2 audit (Pilot Readiness, Product Owner-directed manual review)"

# allocation_id -> (expected matched_site_id, "confirm" | "reject" | "skip", note)
# "skip" = HOM 2.16 (High Lane), left in needs_confirmation - Part 11 allows
# a REQUIRES FURTHER REVIEW outcome; this script explicitly does nothing to
# it rather than defaulting it either way.
DECISIONS: dict[int, tuple[int, str, str]] = {
    1: (69, "reject",
        "Allocation name 'John Street, Hazel Grove' names a different street than the matched Site's actual "
        "address (Old Grove House, 13 VINE Street) - only the generic locality 'Hazel Grove' overlaps, which "
        "Part 11 explicitly treats as insufficient alone. The linked application (DC/082962) is itself a "
        "discharge-of-conditions filing on an existing building (plant/visibility-splay/footway conditions), "
        "not evidence of a new 109-home residential scheme matching this allocation's stated capacity."),
    3: (40, "confirm",
        "Same street name (Station Road) and same locality (Reddish) as the matched Site. Linked application "
        "DC/096126 proposes 'approx 200 new homes', closely matching this allocation's 180-home capacity."),
    13: (102, "confirm",
        "Exact, distinctive multi-word name match between the allocation ('Woodford Garden Village Extension') "
        "and the matched Site's own name - not a generic place name. Linked application DC/094533 is an outline "
        "residential-led scheme at the same address."),
    14: (112, "confirm",
        "Exact, distinctive street-name match ('Hall Moss Lane') between allocation and matched Site. Linked "
        "application DC/097442 explicitly proposes a residential development at this address."),
    15: (115, "further_review",
        "'High Lane' alone names a whole village, not a distinctive site - the allocation name shares no other "
        "identifying detail with the matched Site's actual address (Windlehurst Road). The linked application "
        "(DC/097770) proposes only 250 dwellings against this allocation's stated ~1,000-home capacity - a "
        "genuine partial/phased delivery is plausible (an established, accepted pattern elsewhere in this "
        "platform) but cannot be confirmed with confidence from the evidence available here. Left in "
        "needs_confirmation rather than guessed either way."),
    16: (123, "confirm",
        "Exact, highly distinctive multi-word name match ('Hyde Bank Meadows') between allocation and matched "
        "Site. Linked application DC/098795 is an EIA screening-opinion request for an outline planning "
        "application at this exact named site - the correct, genuine early-stage evidence type for a "
        "not-yet-submitted allocation."),
    18: (85, "confirm",
        "Allocation name ('Jacksons Lane West') shares the distinctive street name with the matched Site's own "
        "address ('...Land To South Of Jacksons Lane'). One physical Site legitimately spanning multiple "
        "allocation halves (West/East) is explicitly anticipated by PR-2 Part 11 as a legitimate outcome, not "
        "a matching error."),
    19: (85, "confirm",
        "Same reasoning as HOM 2.19 (allocation 18) - 'Jacksons Lane East' shares the same distinctive street "
        "name with the same matched Site, the other half of one physical site legitimately split across two "
        "allocation references."),
    27: (88, "reject",
        "Allocation name explicitly references 'Mill Lane', a DIFFERENT street from the matched Site's actual "
        "address ('...Land South Of JACKSONS LANE'), sharing only the generic locality 'Hazel Grove'. This same "
        "underlying Site (Stockport RUFC) is already correctly matched, via the genuinely shared 'Jacksons Lane' "
        "name, to two OTHER allocations (HOM 2.19/HOM 2.20) - strong evidence this specific match is a "
        "false-positive confusion between a real Mill Lane allocation and the unrelated Jacksons Lane site. The "
        "linked application (DC/089037) was also withdrawn."),
    32: (74, "confirm",
        "Allocation ('Heald Green West') and matched Site ('Land At Wilmslow Road Heald Green') share both "
        "locality and arterial road name. Two separate, real, GRANTED Reserved Matters applications on this "
        "Site (DC/084620: 124 dwellings; DC/078180: 202 dwellings - 326 total) provide direct, substantial "
        "residential-development evidence at the named road, consistent with partial/phased delivery of this "
        "allocation's larger stated capacity."),
    36: (117, "confirm",
        "Allocation name ('...Chester Road (Hazel Grove)') and matched Site address ('Land At Chester Road, "
        "Hazel Grove') share the distinctive street name explicitly. Linked application DC/097985 proposes 134 "
        "dwellings at this exact address."),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def apply(session, dry_run: bool = False) -> dict:
    confirmed, rejected, skipped_not_pending, further_review = 0, 0, 0, 0
    for allocation_id, (expected_site_id, verdict, note) in DECISIONS.items():
        allocation = session.get(LocalPlanSite, allocation_id)
        if allocation is None:
            print(f"  [skip] allocation {allocation_id} not found")
            continue

        if verdict == "further_review":
            further_review += 1
            print(f"  [further-review] allocation {allocation_id} ({allocation.policy_reference}) left as-is: {note[:80]}...")
            continue

        if allocation.review_status != "needs_confirmation" or allocation.matched_site_id != expected_site_id:
            skipped_not_pending += 1
            print(
                f"  [skip] allocation {allocation_id} not in expected starting state "
                f"(review_status={allocation.review_status!r}, matched_site_id={allocation.matched_site_id}) "
                f"- already processed by an earlier run, or state changed since this script was written."
            )
            continue

        if dry_run:
            print(f"  [would {verdict}] allocation {allocation_id} ({allocation.policy_reference})")
            if verdict == "confirm":
                confirmed += 1
            else:
                rejected += 1
            continue

        if verdict == "confirm":
            confirm_site_match(session, allocation, confirmed_by=REVIEWED_BY, note=note)
            confirmed += 1
            print(f"  [confirmed] allocation {allocation_id} ({allocation.policy_reference})")
        elif verdict == "reject":
            reject_site_match(session, allocation, confirmed_by=REVIEWED_BY, reason=note)
            rejected += 1
            print(f"  [rejected] allocation {allocation_id} ({allocation.policy_reference})")

    return {
        "confirmed": confirmed, "rejected": rejected,
        "skipped_not_pending": skipped_not_pending, "further_review": further_review,
    }


def main() -> None:
    args = parse_args()
    init_db()
    session = get_session()

    print(f"[apply-pr2-allocation-match-review] processing {len(DECISIONS)} reviewed allocation(s)...")
    result = apply(session, dry_run=args.dry_run)
    print(f"[apply-pr2-allocation-match-review] confirmed={result['confirmed']} rejected={result['rejected']} "
          f"further_review(untouched)={result['further_review']} skipped(already processed)={result['skipped_not_pending']}")
    if args.dry_run:
        print("[apply-pr2-allocation-match-review] --dry-run: no changes were written")


if __name__ == "__main__":
    main()
