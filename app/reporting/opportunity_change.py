"""Gate 1 (Acquisition Monitoring Substrate) - deterministic NEW /
MATERIALLY_CHANGED / UNCHANGED classification for one opportunity, plus
the sync function that keeps app.db.models.OpportunityMonitoringState
current. This is the "objective opportunity change is GLOBAL" half of the
approved Workspace & Ownership Architecture Investigation's own boundary -
nothing here is buyer-relative; app.policy.buyer_matching.assess_buyer_fit
is a completely separate, later step over the SAME opportunity facts.

Relationship to app.pipeline.material_change: that module answers a
narrower, Application-STATE-only question ("has this existing planning
application's decision/status/unit-count materially changed") and is the
authority for that specific comparison - it is not duplicated or
contradicted here. This module answers the broader "has this OPPORTUNITY
(strategic land OR planning/delivery) materially changed" question, using
app.reporting.opportunity_universe's own fingerprint fact set, which is
built from the same buyer-matching-relevant facts app.policy.
buyer_matching.MatchingFacts already carries. A future refinement could
route the planning_state/decision fields specifically through app.
pipeline.material_change's own richer state machine instead of a raw
string-equality check - not done in this gate, since MatchingFacts.
planning_state is already a coarser, buyer-matching-specific bucket
(permission_granted/adopted_allocation/emerging_allocation/other_or_
unknown) that a change to raw decision/status text does not necessarily
move at all (see build_planning_delivery_matching_facts - planning_state
is always PERMISSION_GRANTED for every planning/delivery card, since every
such card is already gated on a granted decision upstream); this module's
own fingerprint separately includes raw `decision`/`status` precisely so a
genuine change there (e.g. a later refusal-on-appeal) is still caught even
though it wouldn't move MatchingFacts.planning_state itself.

BASELINE ESTABLISHMENT vs. ONGOING DISCOVERY (Gate 1 amendment, Product
Owner review; refined by Gate 1C, Section 16): the very first time
monitoring is ever established against an already-populated Property
AIgent database, every opportunity already in the current universe is
HISTORICAL/EXISTING baseline - it must never be persisted, or later read
by Gate 2, as if it had just been "discovered". `BASELINE_EXISTING` is the
distinct, persisted classification for exactly this - never NEW. This is
not derived from timestamp ordering or from which script happened to run
first ("do NOT rely solely on ordering/timestamp luck"): sync_opportunity_
monitoring_state below determines, PER DETECTOR KIND (see
_opportunity_kind_prefix), whether THIS call is establishing that kind's
own baseline for the first time - has ANY opportunity of that exact
detector kind ever been tracked before, regardless of whether OTHER kinds
already have. An empty table trivially means every kind is untracked
(the original Gate 1 case, unchanged); Gate 1C's own recent_permission
detector being added LATER to an already-populated table is the second,
genuinely different case this scoping exists for - see sync_opportunity_
monitoring_state's own "DETECTOR-EXPANSION BASELINING" docstring section
for why a single whole-table flag cannot safely handle that case. Once a
detector kind has at least one tracked row, every subsequent call is
ordinary ongoing monitoring for that kind, where a genuinely new
opportunity_id correctly becomes NEW.
"""
from __future__ import annotations

import json

from dataclasses import dataclass

from sqlalchemy import select

from app.db.models import OpportunityMonitoringState, utcnow
from app.reporting.opportunity_universe import (
    OpportunityRecord,
    build_current_opportunity_universe,
    compute_opportunity_fingerprint,
)

# Persisted classifications. BASELINE_EXISTING is distinct from NEW -
# see this module's own "BASELINE ESTABLISHMENT vs. ONGOING DISCOVERY"
# docstring section above. Gate 2's own future "what's new for this
# buyer" query must treat BASELINE_EXISTING as historical, never as a
# discovery event.
BASELINE_EXISTING = "BASELINE_EXISTING"
NEW = "NEW"
MATERIALLY_CHANGED = "MATERIALLY_CHANGED"
UNCHANGED = "UNCHANGED"

# Deterministic reason codes (Gate 1 brief, Section 15: "prefer
# deterministic reason codes... only implement reason codes supported by
# real data") - every one of these can genuinely fire given app.reporting.
# opportunity_universe's own current fingerprint_fields dicts; none are
# speculative.
REASON_UNIT_COUNT_CHANGED = "unit_count_changed"
REASON_AFFORDABLE_UNIT_COUNT_CHANGED = "affordable_unit_count_changed"
REASON_DEVELOPMENT_TYPE_CHANGED = "development_type_changed"
REASON_PLANNING_STATUS_CHANGED = "planning_status_changed"
REASON_DECISION_CHANGED = "decision_changed"
REASON_PLANNING_ACTIVITY_CHANGED = "planning_activity_changed"
REASON_PHASING_EVIDENCE_CHANGED = "phasing_evidence_changed"
REASON_ALLOCATION_STATUS_CHANGED = "allocation_status_changed"
REASON_LAPSE_STATUS_CHANGED = "lapse_status_changed"
REASON_BUILD_STATUS_CHANGED = "build_status_changed"
REASON_OWNERSHIP_EVIDENCE_CHANGED = "ownership_evidence_changed"
REASON_GREEN_BELT_STATUS_CHANGED = "green_belt_status_changed"
REASON_SITE_AREA_CHANGED = "site_area_changed"
# Only reached if a fingerprint_fields key this module hasn't named below
# ever changes - an honest fallback, never a silently unexplained
# MATERIALLY_CHANGED (see classify_opportunity_change's own docstring).
REASON_OTHER_FACT_CHANGED = "other_fact_changed"

# Maps a fingerprint_fields KEY to the reason code fired when that key's
# value differs between the previous and current snapshot. Deliberately
# one explicit entry per key app.reporting.opportunity_universe actually
# writes, rather than a single generic "something changed" reason.
_REASON_BY_FIELD = {
    "unit_count": REASON_UNIT_COUNT_CHANGED,
    "affordable_unit_count": REASON_AFFORDABLE_UNIT_COUNT_CHANGED,
    "development_type_raw": REASON_DEVELOPMENT_TYPE_CHANGED,
    "is_specialist_development": REASON_DEVELOPMENT_TYPE_CHANGED,
    "planning_state": REASON_PLANNING_STATUS_CHANGED,
    "plan_status_bucket": REASON_ALLOCATION_STATUS_CHANGED,
    "has_identified_planning_activity": REASON_PLANNING_ACTIVITY_CHANGED,
    "has_phasing_evidence": REASON_PHASING_EVIDENCE_CHANGED,
    "decision": REASON_DECISION_CHANGED,
    "status": REASON_PLANNING_STATUS_CHANGED,
    "lapse_status": REASON_LAPSE_STATUS_CHANGED,
    "deadline": REASON_LAPSE_STATUS_CHANGED,
    "build_status": REASON_BUILD_STATUS_CHANGED,
    "ownership_evidence_count": REASON_OWNERSHIP_EVIDENCE_CHANGED,
    "green_belt_status": REASON_GREEN_BELT_STATUS_CHANGED,
    "site_area_hectares": REASON_SITE_AREA_CHANGED,
    "matched_to_site": REASON_OWNERSHIP_EVIDENCE_CHANGED,
}


@dataclass(frozen=True)
class OpportunityChangeResult:
    classification: str  # BASELINE_EXISTING | NEW | MATERIALLY_CHANGED | UNCHANGED
    reasons: tuple[str, ...]
    fingerprint: str


def _diff_reasons(old_fields: dict, new_fields: dict) -> tuple[str, ...]:
    reasons: list[str] = []
    seen: set[str] = set()
    for key in sorted(set(old_fields) | set(new_fields)):
        if old_fields.get(key) == new_fields.get(key):
            continue
        reason = _REASON_BY_FIELD.get(key, REASON_OTHER_FACT_CHANGED)
        if reason not in seen:
            reasons.append(reason)
            seen.add(reason)
    return tuple(reasons)


def classify_opportunity_change(
    record: OpportunityRecord, previous_state: OpportunityMonitoringState | None, *, is_baseline_run: bool = False,
) -> OpportunityChangeResult:
    """The ONE canonical classifier - every caller (sync_opportunity_
    monitoring_state below, and Gate 2's own future "what changed since I
    last looked" query) must go through this rather than re-implementing
    the fingerprint comparison. `previous_state` is None for an opportunity
    identity never tracked before - BASELINE_EXISTING when `is_baseline_run`
    is True (monitoring has never been established before at all - see
    this module's own "BASELINE ESTABLISHMENT vs. ONGOING DISCOVERY"
    docstring section), otherwise NEW (ordinary ongoing monitoring found a
    genuinely new opportunity_id) - either way with no reasons (nothing to
    diff against). An identical fingerprint -> UNCHANGED. Otherwise the
    per-field diff above names every reason it can - REASON_OTHER_FACT_
    CHANGED only fires if this module's own field-to-reason map has
    drifted out of date with app.reporting.opportunity_universe's actual
    fingerprint_fields keys, which the module docstring flags as a bug to
    fix here, not a real "unknown" opportunity state."""
    fingerprint = compute_opportunity_fingerprint(record.fingerprint_fields)
    if previous_state is None:
        classification = BASELINE_EXISTING if is_baseline_run else NEW
        return OpportunityChangeResult(classification=classification, reasons=(), fingerprint=fingerprint)
    if previous_state.fingerprint == fingerprint:
        return OpportunityChangeResult(classification=UNCHANGED, reasons=(), fingerprint=fingerprint)

    old_fields = json.loads(previous_state.fingerprint_fields) if previous_state.fingerprint_fields else {}
    reasons = _diff_reasons(old_fields, record.fingerprint_fields) or (REASON_OTHER_FACT_CHANGED,)
    return OpportunityChangeResult(classification=MATERIALLY_CHANGED, reasons=reasons, fingerprint=fingerprint)


def _opportunity_kind_prefix(opportunity_id: str) -> str:
    """The detector-FAMILY portion of a stable identity string - e.g.
    "strategic_land:allocation", "planning_delivery:site",
    "planning_delivery:phase", "planning_delivery:recent_permission" (the
    numeric/site-specific final segment stripped). Used ONLY to answer
    "has ANY opportunity this detector kind ever produced been tracked
    before" - see sync_opportunity_monitoring_state's own "DETECTOR-
    EXPANSION BASELINING" docstring section for why this, not a single
    whole-table flag, is the correct baseline signal. Never persisted as
    its own column - always recomputed from opportunity_id, which already
    carries this information verbatim."""
    return opportunity_id.rsplit(":", 1)[0]


def sync_opportunity_monitoring_state(session, *, page_size: int | None = None) -> dict[str, int]:
    """Rebuilds the COMPLETE current opportunity universe (see app.
    reporting.opportunity_universe's own "COMPLETENESS" docstring section -
    this never silently truncates, however large the universe grows) and
    reconciles app.db.models.OpportunityMonitoringState against it - the
    one function a future bounded cron stage (Gate 2's own trigger
    mechanism) calls. Deterministic, idempotent, no OpenAI call. Never
    deletes a row for an opportunity that has disappeared from the live
    candidate universe (per the approved investigation's own "an
    opportunity that vanishes from the read model is itself meaningful
    information, not an error requiring cleanup" - its last-known state
    simply stops being refreshed, which is the correct, non-destructive
    behaviour here).

    DETECTOR-EXPANSION BASELINING (Gate 1C, Section 16 - release-critical):
    baseline detection is scoped PER DETECTOR KIND (see
    _opportunity_kind_prefix above), never a single whole-table flag. The
    original Gate 1 mechanism ("is OpportunityMonitoringState currently
    empty") only ever correctly handles the very first sync against a
    brand-new table - it does NOT handle a genuinely different later
    scenario: a NEW detector (e.g. Gate 1C's own recent_permission) being
    added to an ALREADY-populated table. Without this refinement, every
    one of that new detector's own first-ever candidates would have
    `previous_state is None` while the table itself is non-empty, and
    would be misclassified NEW - exactly the false-discovery bug this
    section exists to prevent. Scoping "has this been established before"
    to the detector-kind prefix instead (has ANY "planning_delivery:
    recent_permission:*" row ever existed, independent of whether
    "planning_delivery:site:*"/"strategic_land:allocation:*" rows already
    have) fixes this for both the original Gate 1 case (an empty table -
    every kind prefix is untracked, identical prior behaviour, verified by
    test) AND Gate 1C's own detector-expansion case, using only data
    opportunity_id already carries - no schema change, no new column, a
    pure code-level fix (Section 16's own "prefer a code-level baseline
    mechanism if safe").

    Returns a plain counts dict (never a numeric score) - one line an
    operator or a future cron log can print, mirroring app.pipeline.
    material_change.MaterialChangeStats.summary_line's own convention."""
    kwargs = {} if page_size is None else {"page_size": page_size}

    universe = build_current_opportunity_universe(session, **kwargs)

    # Every opportunity_id ever tracked (lightweight - id strings only,
    # not full rows) - the pre-sync state this run's baseline detection is
    # scoped against. At current/near-term scale (hundreds of rows) this
    # is a trivial single query; a future high-volume gate could narrow
    # this to distinct kind-prefixes directly if it ever needs to.
    tracked_kind_prefixes = {
        _opportunity_kind_prefix(oid)
        for oid in session.execute(select(OpportunityMonitoringState.opportunity_id)).scalars()
    }

    existing_by_id = {
        s.opportunity_id: s
        for s in session.execute(
            select(OpportunityMonitoringState).where(
                OpportunityMonitoringState.opportunity_id.in_([r.opportunity_id for r in universe])
            )
        ).scalars()
    } if universe else {}

    counts = {BASELINE_EXISTING: 0, NEW: 0, MATERIALLY_CHANGED: 0, UNCHANGED: 0}
    for record in universe:
        previous = existing_by_id.get(record.opportunity_id)
        is_baseline_run_for_this_kind = _opportunity_kind_prefix(record.opportunity_id) not in tracked_kind_prefixes
        result = classify_opportunity_change(record, previous, is_baseline_run=is_baseline_run_for_this_kind)
        counts[result.classification] += 1

        if previous is None:
            session.add(OpportunityMonitoringState(
                opportunity_id=record.opportunity_id, opportunity_type=record.opportunity_type,
                fingerprint=result.fingerprint, fingerprint_fields=json.dumps(record.fingerprint_fields, sort_keys=True, default=str),
                # last_change_at stays None for a freshly-created row
                # regardless of BASELINE_EXISTING/NEW - it records when the
                # fingerprint of an ALREADY-tracked opportunity genuinely
                # moved, not when the row was first created (first_seen_at,
                # set by the column default, is that signal instead).
                last_change_at=None, last_change_classification=result.classification, last_change_reasons=None,
            ))
        else:
            previous.fingerprint = result.fingerprint
            previous.fingerprint_fields = json.dumps(record.fingerprint_fields, sort_keys=True, default=str)
            previous.last_change_classification = result.classification
            if result.classification == MATERIALLY_CHANGED:
                previous.last_change_at = utcnow()
                previous.last_change_reasons = ",".join(result.reasons)
            # UNCHANGED: last_change_at/last_change_reasons deliberately
            # left untouched - they record the most recent GENUINE change,
            # never reset by a routine check that found nothing new (same
            # "truthful timestamp" discipline as Application.evidence_
            # refresh_last_checked_at).

    session.commit()
    return {
        "opportunities_considered": len(universe),
        "baseline_existing": counts[BASELINE_EXISTING],
        "new": counts[NEW],
        "materially_changed": counts[MATERIALLY_CHANGED],
        "unchanged": counts[UNCHANGED],
    }
