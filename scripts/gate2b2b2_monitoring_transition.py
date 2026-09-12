"""Gate 2B-2B.2 pre-merge remediation - the ONE-TIME controlled
monitoring transition for THIS gate specifically (app.reporting.
opportunity_monitoring_transition is the generic, reusable engine; this
script is the narrow, gate-specific manifest + invocation).

    python -m scripts.gate2b2b2_monitoring_transition            # dry-run (default, no writes)
    python -m scripts.gate2b2b2_monitoring_transition --execute   # applies the transition

NOT run against production by this task - Product Owner instruction
(Gate 2B-2B.2 Pre-Merge Monitoring Transition Remediation, Section 10):
"DO NOT execute this transition against production in this task...
The eventual merge/deployment prompt will explicitly authorise the
controlled production transition after deployed SHA is verified."

The manifest below is the Gate 2B-2B.2 implementation report's own
reviewed before/after diff (Sections K/L/M of that report), current as
of feature branch commit a140302d3939e35575bf292f9bf0cc9ed65190d1 -
RE-VERIFY it (re-run the same before/after diff against whatever SHA is
actually about to be deployed) before ever passing --execute, since
production data may have drifted since this was written (Section 2 of
the Pre-Merge Monitoring Transition brief: "must be recomputed
immediately before any future production transition"). This script
intentionally does not recompute the manifest for you - re-deriving it
silently would defeat the whole point of a hand-reviewed, explicit
transition input (see app.reporting.opportunity_monitoring_transition's
own "DELIBERATELY NARROW" docstring section).
"""
from __future__ import annotations

import argparse

from app.db.session import get_session
from app.reporting.opportunity_monitoring_transition import MonitoringTransitionManifest, apply_monitoring_transition

MANIFEST = MonitoringTransitionManifest(
    retired_ids=frozenset({
        "planning_delivery:phase:149:Whole site / unphased",
        "planning_delivery:phase:248:12",
        "planning_delivery:phase:249:25",
        "planning_delivery:phase:265:10",
        "planning_delivery:phase:329:O1",
        "planning_delivery:phase:371:A5",
        "planning_delivery:phase:544:2",
    }),
    replacement_ids=frozenset({
        "planning_delivery:phase:248:Whole site / unphased",
        "planning_delivery:phase:249:Whole site / unphased",
        "planning_delivery:phase:371:Whole site / unphased",
        "planning_delivery:phase:544:Whole site / unphased",
    }),
    rebaseline_ids=frozenset({
        "planning_delivery:phase:281:1",
        "planning_delivery:phase:556:1",
        "planning_delivery:phase:74:2",
    }),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true",
        help="Apply the transition. Without this flag, runs as a dry-run (no writes) and prints what would happen.",
    )
    args = parser.parse_args()

    session = get_session()
    try:
        report = apply_monitoring_transition(session, MANIFEST, dry_run=not args.execute)
    finally:
        session.close()

    print(report.summary_line())
    if not report.ok:
        print("[gate2b2b2-monitoring-transition] FAILED-CLOSED - manifest does not match current data. No writes applied.")
        if report.ids_in_multiple_categories:
            print(f"  ids_in_multiple_categories: {list(report.ids_in_multiple_categories)}")
        if report.retired_unexpectedly_live:
            print(f"  retired_unexpectedly_live: {list(report.retired_unexpectedly_live)}")
        if report.replacement_missing_from_universe:
            print(f"  replacement_missing_from_universe: {list(report.replacement_missing_from_universe)}")
        if report.replacement_already_tracked:
            print(f"  replacement_already_tracked: {list(report.replacement_already_tracked)}")
        if report.rebaseline_missing_from_universe:
            print(f"  rebaseline_missing_from_universe: {list(report.rebaseline_missing_from_universe)}")
        if report.rebaseline_not_currently_tracked:
            print(f"  rebaseline_not_currently_tracked: {list(report.rebaseline_not_currently_tracked)}")
        raise SystemExit(1)

    print(f"  retired_confirmed_absent: {list(report.retired_confirmed_absent)}")
    print(f"  replacement_baselined: {list(report.replacement_baselined)}")
    print(f"  rebaseline_applied: {list(report.rebaseline_applied)}")
    for w in report.writes:
        print(f"  WRITE {w.opportunity_id} .{w.field}: {w.old_value!r} -> {w.new_value!r} ({w.reason})")


if __name__ == "__main__":
    main()
