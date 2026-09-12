"""Gate 2B-2B.2 pre-merge remediation ("Pre-Merge Monitoring Transition") -
a narrow, explicit, dry-run-first mechanism for correcting
app.db.models.OpportunityMonitoringState identity/fingerprint state after
a SOFTWARE change to how opportunities are scoped or how their facts are
attributed - never for ordinary ongoing monitoring, which remains
entirely app.reporting.opportunity_change.sync_opportunity_monitoring_
state's own, completely unmodified job.

WHY THIS EXISTS: Gate 2B-2B.2 corrects two things that were never real
planning-evidence events - (1) which opportunity identity a scope of
applications is attributed to (a false plot identity retiring in favour
of a legitimate whole-site identity for the SAME underlying evidence),
and (2) which unit_count value an existing, still-live phase opportunity
carries (a software fact-attribution bug, not a change on the ground).
Left to the ordinary sync alone, (1) would report the replacement
identity as NEW ("newly discovered opportunity") and (2) would report
MATERIALLY_CHANGED ("unit_count_changed") - both technically true of the
STORED snapshot, but false of the real world: nothing changed on site: a
correction to this platform's own arithmetic. This module is the one-time
maintenance step that reconciles the monitoring table with the corrected
software model FIRST, so the very next ordinary sync sees the world
exactly as this module's own before/after diff already explained it
should, and reports it correctly (UNCHANGED / stops refreshing).

DELIBERATELY NARROW - not a generic rebaseline framework:
- No schema change. Only `fingerprint`/`fingerprint_fields` on an
  ALREADY-existing row are ever touched (rebaseline_ids); a replacement
  row is created with the exact same shape sync_opportunity_monitoring_
  state already creates for a new row (mirrors that function's own
  creation branch verbatim, using BASELINE_EXISTING - the constant
  app.reporting.opportunity_change already defines for exactly this
  "already existed, not a new discovery" case - never a new
  classification constant).
- No implicit ID discovery. Every opportunity_id this module can ever
  touch must appear, explicitly, in a MonitoringTransitionManifest the
  CALLER builds from a specific gate's own reviewed before/after diff
  (never "all phase opportunities", never inferred from a naming
  pattern). The manifest is a plain, hand-reviewed value - never
  hard-coded inside this module.
- Fails CLOSED, as a whole, not per-ID: if ANY id in the manifest does
  not match the CURRENT live universe/tracked-state shape this module
  expects for its own category (Section 3 of this module's own
  docstring below), `TransitionReport.ok` is False and NO write happens
  at all, dry-run or not - a stale manifest (production data drifted
  since it was reviewed) must never partially apply.
- `dry_run=True` is the default and performs zero writes; the caller
  must pass `dry_run=False` explicitly to commit anything.

CATEGORIES (MonitoringTransitionManifest):
  A. retired_ids       - opportunity_ids the gate's fix correctly stops
                          emitting. This module does NOT write anything
                          for these - it only CONFIRMS each one is
                          genuinely absent from the current live universe
                          (a stale manifest claiming something is retired
                          when it is, in fact, still live is exactly the
                          kind of drift this module must refuse to
                          proceed past). Their historical
                          OpportunityMonitoringState rows are left
                          completely untouched, exactly as ordinary
                          sync_opportunity_monitoring_state already
                          leaves any row for an opportunity that
                          disappears from the universe: last-known state
                          simply stops being refreshed.
  B. replacement_ids   - opportunity_ids that are newly live as a DIRECT
                          consequence of this gate's fix (the same real
                          evidence, now correctly attributed) and have
                          NEVER been tracked before. Baselined with a
                          freshly-created row carrying the CURRENT
                          (post-fix) fingerprint and
                          last_change_classification=BASELINE_EXISTING,
                          so the next ordinary sync finds a matching
                          fingerprint and reports UNCHANGED, never NEW.
                          first_seen_at is the actual moment this
                          transition runs - never fabricated earlier.
  C. rebaseline_ids    - opportunity_ids that are STILL live under the
                          SAME identity, but whose fingerprint was
                          computed from an incorrect fact (e.g. a
                          borrowed whole-site unit_count) before this
                          gate's fix. Their EXISTING row's `fingerprint`/
                          `fingerprint_fields` are updated to the
                          CURRENT (post-fix) values so the next ordinary
                          sync reports UNCHANGED rather than
                          MATERIALLY_CHANGED. `first_seen_at`,
                          `last_change_at`, `last_change_classification`,
                          and `last_change_reasons` are left completely
                          untouched - this is a snapshot correction, not
                          a genuine change event.
"""
from __future__ import annotations

import json

from dataclasses import dataclass

from sqlalchemy import select

from app.db.models import OpportunityMonitoringState
from app.reporting.opportunity_change import BASELINE_EXISTING
from app.reporting.opportunity_universe import build_current_opportunity_universe, compute_opportunity_fingerprint


@dataclass(frozen=True)
class MonitoringTransitionManifest:
    """An explicit, hand-reviewed set of opportunity_ids ONE controlled
    transition run is authorised to touch - built by the caller from a
    specific gate's own reviewed before/after opportunity-universe diff
    (see that gate's implementation report), never inferred or hard-coded
    inside this module. Recompute/re-review immediately before use if
    production data may have drifted since the manifest was built."""
    retired_ids: frozenset[str] = frozenset()
    replacement_ids: frozenset[str] = frozenset()
    rebaseline_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class TransitionFieldWrite:
    """One field write this transition applied (or, in a dry run, would
    apply) to one opportunity_id - printable/loggable evidence of exactly
    what changed, since no new schema exists to store a "reason" column."""
    opportunity_id: str
    field: str
    old_value: str | None
    new_value: str | None
    reason: str


@dataclass(frozen=True)
class TransitionReport:
    dry_run: bool
    ok: bool  # False if ANY safety check below failed - no write was (or would be) applied when False

    current_total_opportunities: int
    current_planning_delivery_opportunities: int

    # A. Retired
    retired_confirmed_absent: tuple[str, ...] = ()
    retired_unexpectedly_live: tuple[str, ...] = ()  # STOP condition

    # B. Replacement
    replacement_baselined: tuple[str, ...] = ()
    replacement_missing_from_universe: tuple[str, ...] = ()  # STOP condition - manifest drift
    replacement_already_tracked: tuple[str, ...] = ()  # STOP condition - not actually a fresh identity

    # C. Rebaseline
    rebaseline_applied: tuple[str, ...] = ()
    rebaseline_missing_from_universe: tuple[str, ...] = ()  # STOP condition - manifest drift
    rebaseline_not_currently_tracked: tuple[str, ...] = ()  # STOP condition - nothing to rebaseline

    # Manifest self-consistency (an id must belong to exactly one category)
    ids_in_multiple_categories: tuple[str, ...] = ()  # STOP condition

    writes: tuple[TransitionFieldWrite, ...] = ()

    def summary_line(self) -> str:
        mode = "DRY-RUN" if self.dry_run else "APPLIED"
        status = "OK" if self.ok else "FAILED-CLOSED (no writes applied)"
        return (
            f"[gate2b2b2-monitoring-transition] {mode} {status} - "
            f"universe_total={self.current_total_opportunities} "
            f"planning_delivery={self.current_planning_delivery_opportunities} - "
            f"retired_confirmed={len(self.retired_confirmed_absent)} "
            f"replacement_baselined={len(self.replacement_baselined)} "
            f"rebaseline_applied={len(self.rebaseline_applied)} "
            f"writes={len(self.writes)}"
        )


_TRANSITION_REASON = (
    "Gate 2B-2B.2 controlled monitoring transition - software scope/fact "
    "correction, not new planning evidence"
)


def apply_monitoring_transition(
    session, manifest: MonitoringTransitionManifest, *, dry_run: bool = True,
) -> TransitionReport:
    """Validates `manifest` against the CURRENT live opportunity universe
    and CURRENT OpportunityMonitoringState rows, and - only if every
    check passes (`TransitionReport.ok`) - applies (or, if `dry_run`,
    would apply) exactly the writes described in this module's own
    docstring. Fails closed as a whole: if any check fails, `ok` is
    False and NOT ONE write is applied, dry-run or not.

    Never touches any opportunity_id outside the manifest. Never deletes
    a row. Never touches `first_seen_at` on an existing row. Only ever
    writes `fingerprint`/`fingerprint_fields` (and, for a brand-new
    replacement row, the same fields sync_opportunity_monitoring_state's
    own creation branch already writes)."""
    ids_by_category = {
        "retired": manifest.retired_ids, "replacement": manifest.replacement_ids, "rebaseline": manifest.rebaseline_ids,
    }
    seen: dict[str, str] = {}
    ids_in_multiple_categories: list[str] = []
    for category, ids in ids_by_category.items():
        for oid in ids:
            if oid in seen:
                ids_in_multiple_categories.append(oid)
            else:
                seen[oid] = category
    ids_in_multiple_categories = tuple(sorted(set(ids_in_multiple_categories)))

    universe = build_current_opportunity_universe(session)
    universe_by_id = {r.opportunity_id: r for r in universe}
    live_ids = set(universe_by_id)
    planning_delivery_count = sum(1 for r in universe if r.opportunity_type == "planning_delivery")

    all_manifest_ids = manifest.retired_ids | manifest.replacement_ids | manifest.rebaseline_ids
    tracked_rows = {
        row.opportunity_id: row
        for row in session.execute(
            select(OpportunityMonitoringState).where(OpportunityMonitoringState.opportunity_id.in_(all_manifest_ids))
        ).scalars()
    } if all_manifest_ids else {}

    retired_confirmed_absent = tuple(sorted(oid for oid in manifest.retired_ids if oid not in live_ids))
    retired_unexpectedly_live = tuple(sorted(oid for oid in manifest.retired_ids if oid in live_ids))

    replacement_missing_from_universe = tuple(sorted(oid for oid in manifest.replacement_ids if oid not in live_ids))
    replacement_already_tracked = tuple(sorted(oid for oid in manifest.replacement_ids if oid in tracked_rows))
    replacement_ok_ids = sorted(
        oid for oid in manifest.replacement_ids if oid in live_ids and oid not in tracked_rows
    )

    rebaseline_missing_from_universe = tuple(sorted(oid for oid in manifest.rebaseline_ids if oid not in live_ids))
    rebaseline_not_currently_tracked = tuple(sorted(oid for oid in manifest.rebaseline_ids if oid not in tracked_rows))
    rebaseline_ok_ids = sorted(
        oid for oid in manifest.rebaseline_ids if oid in live_ids and oid in tracked_rows
    )

    ok = not any([
        ids_in_multiple_categories, retired_unexpectedly_live,
        replacement_missing_from_universe, replacement_already_tracked,
        rebaseline_missing_from_universe, rebaseline_not_currently_tracked,
    ])

    writes: list[TransitionFieldWrite] = []
    replacement_baselined: list[str] = []
    rebaseline_applied: list[str] = []

    if ok:
        for oid in replacement_ok_ids:
            record = universe_by_id[oid]
            fingerprint = compute_opportunity_fingerprint(record.fingerprint_fields)
            fields_json = json.dumps(record.fingerprint_fields, sort_keys=True, default=str)
            writes.append(TransitionFieldWrite(oid, "fingerprint", None, fingerprint, _TRANSITION_REASON))
            writes.append(TransitionFieldWrite(oid, "fingerprint_fields", None, fields_json, _TRANSITION_REASON))
            if not dry_run:
                session.add(OpportunityMonitoringState(
                    opportunity_id=oid, opportunity_type=record.opportunity_type,
                    fingerprint=fingerprint, fingerprint_fields=fields_json,
                    last_change_at=None, last_change_classification=BASELINE_EXISTING, last_change_reasons=None,
                ))
            replacement_baselined.append(oid)

        for oid in rebaseline_ok_ids:
            record = universe_by_id[oid]
            row = tracked_rows[oid]
            fingerprint = compute_opportunity_fingerprint(record.fingerprint_fields)
            fields_json = json.dumps(record.fingerprint_fields, sort_keys=True, default=str)
            writes.append(TransitionFieldWrite(oid, "fingerprint", row.fingerprint, fingerprint, _TRANSITION_REASON))
            writes.append(TransitionFieldWrite(
                oid, "fingerprint_fields", row.fingerprint_fields, fields_json, _TRANSITION_REASON,
            ))
            if not dry_run:
                row.fingerprint = fingerprint
                row.fingerprint_fields = fields_json
            rebaseline_applied.append(oid)

        if not dry_run:
            session.commit()

    return TransitionReport(
        dry_run=dry_run, ok=ok,
        current_total_opportunities=len(universe), current_planning_delivery_opportunities=planning_delivery_count,
        retired_confirmed_absent=retired_confirmed_absent, retired_unexpectedly_live=retired_unexpectedly_live,
        replacement_baselined=tuple(replacement_baselined),
        replacement_missing_from_universe=replacement_missing_from_universe,
        replacement_already_tracked=replacement_already_tracked,
        rebaseline_applied=tuple(rebaseline_applied),
        rebaseline_missing_from_universe=rebaseline_missing_from_universe,
        rebaseline_not_currently_tracked=rebaseline_not_currently_tracked,
        ids_in_multiple_categories=ids_in_multiple_categories,
        writes=tuple(writes),
    )
