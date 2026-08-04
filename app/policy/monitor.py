"""Standalone, idempotent monitoring pathway for Policy Intelligence sources
(Sprint 1 CTO-review amendment, Part 2).

Checks every active MonitoredSource for a council, hashes its current
content, and - if it's changed - queues a PolicyChangeEvent. It never
touches trusted LocalPlan/LocalPlanSite state itself: a raw content-hash
change says THAT a source changed, not WHAT changed within it (that needs
either a human to re-read it, or a future re-run of ingest_local_plan.py to
extract it properly), so every "changed" outcome is unconditionally
review_status="needs_review" - there is no "high-confidence" version of a
bare hash diff. See app.policy.review for how a queued change is later
resolved.

    python -m app.policy.monitor --council stockport [--timeout 15] [--force]

Not wired into any scheduled/unattended run yet - this is a manually
invoked command only, though it's written to be safe for Windows Task
Scheduler once one is set up (housing-supply monitoring amendment, "Add
monitored housing supply and delivery reports", Part 3): by default it
only checks sources actually due a recheck (MonitoredSource.next_check_due,
see app.policy.report_cadence), so scheduling it to run frequently is safe
- most invocations will find nothing due and do almost no work. --force
bypasses the due-date filter for a manual recheck.

Since that same amendment, this command also runs report discovery/
tracking (app.policy.report_discovery) for the same council in the same
pass - one command, not two to remember to schedule.
"""
from __future__ import annotations

import argparse
import datetime as dt

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MonitoredSource, PolicyChangeEvent
from app.policy.change_detection import classify_source_check, compute_content_hash
from app.policy.report_cadence import compute_next_check_due, is_due
from app.policy.report_discovery import REQUEST_HEADERS, check_reports_for_council, discover_reports_for_council

DEFAULT_TIMEOUT_SECONDS = 15
# A source that's been failing for at least this long (measured from its
# last SUCCESSFUL check) is reported "stale" rather than a fresh "error" -
# distinguishes "just had one bad request" from "hasn't actually been
# checkable in a while", which matters more for deciding whether to
# investigate.
STALE_AFTER_DAYS = 7


def _naive_utcnow() -> dt.datetime:
    # SQLite round-trips a stored tz-aware datetime as naive on read back in
    # a later process - the same fact app.pipeline.run_weekly's
    # stage_check_build_status documents and works around. Comparing
    # naive-to-naive throughout this module is correct, not a workaround
    # for a bug - both sides represent UTC wall-clock time regardless.
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _has_pending_change_event(session: Session, source: MonitoredSource) -> bool:
    return session.execute(
        select(PolicyChangeEvent).where(
            PolicyChangeEvent.monitored_source_id == source.id,
            PolicyChangeEvent.event_type == "source_content_changed",
            PolicyChangeEvent.review_status == "needs_review",
        )
    ).first() is not None


def check_source(session: Session, source: MonitoredSource, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Checks one source and updates its own monitoring fields. Returns one
    of "first_check", "unchanged", "changed", or "failed" - the per-source
    outcome, for the caller's run summary. Idempotent: calling this twice in
    a row against an unchanged source produces the same "unchanged" result
    both times and never queues a second event for the same still-pending
    change (see _has_pending_change_event)."""
    now = dt.datetime.now(dt.timezone.utc)
    source.last_checked = now

    try:
        response = requests.get(source.url, timeout=timeout, headers=REQUEST_HEADERS)
        response.raise_for_status()
    except requests.RequestException:
        last_ok = source.last_successful_check
        is_stale = last_ok is None or (_naive_utcnow() - last_ok.replace(tzinfo=None)) > dt.timedelta(days=STALE_AFTER_DAYS)
        source.monitoring_health = "stale" if is_stale else "error"
        return "failed"

    new_hash = compute_content_hash(response.text)
    outcome = classify_source_check(source.content_hash, new_hash)

    source.last_successful_check = now
    source.monitoring_health = "ok"
    if response.url and response.url != source.url:
        source.final_url = response.url

    if outcome == "changed":
        source.last_changed = now
        if not _has_pending_change_event(session, source):
            session.add(PolicyChangeEvent(
                local_plan_id=source.local_plan_id, monitored_source_id=source.id,
                event_type="source_content_changed", old_value=source.content_hash, new_value=new_hash,
                detail=f"Content hash changed for monitored source {source.url!r} - re-ingestion is needed to "
                       f"interpret what actually changed before anything is applied.",
                source_document_url=source.url,
                auto_applied=False, review_status="needs_review",
            ))

    source.content_hash = new_hash
    source.next_check_due = compute_next_check_due(source.source_type, source.expected_publication_window, now)
    return outcome


def run_monitor(session: Session, council_code: str, timeout: int = DEFAULT_TIMEOUT_SECONDS, force: bool = False) -> dict:
    # Filters on MonitoredSource.council_code directly (Sprint 2
    # generalisation), not via a join through LocalPlan - a council-level
    # source (a Local Plan landing page, registered before any plan exists
    # yet) has local_plan_id=None and would be silently skipped by an
    # inner join, exactly the kind of council-level watch this sprint's
    # source-registration generalisation exists to support.
    sources = session.execute(
        select(MonitoredSource).where(
            MonitoredSource.council_code == council_code, MonitoredSource.is_active.is_(True),
        )
    ).scalars().all()

    counts = {"checked": 0, "skipped_not_due": 0, "unchanged": 0, "changed": 0, "first_check": 0, "failed": 0, "queued": 0}
    for source in sources:
        if not force and not is_due(source.next_check_due):
            counts["skipped_not_due"] += 1
            continue
        had_pending = _has_pending_change_event(session, source)
        outcome = check_source(session, source, timeout=timeout)
        counts["checked"] += 1
        counts[outcome] += 1
        if outcome == "changed" and not had_pending:
            counts["queued"] += 1
        session.commit()

    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--council", required=True)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--force", action="store_true", help="Recheck every active source/report regardless of its due date")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    from app.db.session import get_session, init_db  # local import: keeps this module importable/testable without touching the real DB

    init_db()
    session = get_session()

    counts = run_monitor(session, args.council, timeout=args.timeout, force=args.force)
    print(
        f"[policy-monitor] {args.council}: checked {counts['checked']} source(s), skipped {counts['skipped_not_due']} "
        f"not-yet-due - {counts['unchanged']} unchanged, {counts['changed']} changed ({counts['queued']} newly "
        f"queued for review), {counts['first_check']} first-time check(s), {counts['failed']} failed"
    )

    discovery = discover_reports_for_council(session, args.council, timeout=args.timeout, force=args.force)
    print(
        f"[policy-monitor] {args.council}: report discovery - checked {discovery['sources_checked']} index "
        f"page(s), skipped {discovery['sources_skipped_not_due']} not-yet-due - {discovery['new_reports']} new "
        f"report(s) found ({discovery['auto_classified']} auto-classified, {discovery['needs_review']} needing "
        f"review), {discovery['failed']} failed"
    )

    report_checks = check_reports_for_council(session, args.council, timeout=args.timeout, force=args.force)
    print(
        f"[policy-monitor] {args.council}: report rechecks - checked {report_checks['reports_checked']}, skipped "
        f"{report_checks['reports_skipped_not_due']} not-yet-due - {report_checks['unchanged']} unchanged, "
        f"{report_checks['superseded']} superseded by a new edition, {report_checks['first_check']} first-time "
        f"check(s), {report_checks['failed']} failed"
    )


if __name__ == "__main__":
    main()
