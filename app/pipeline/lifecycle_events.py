"""Gate 2B-0B ("Application Lifecycle Intelligence") Phase B - Application
Lifecycle Event writing.

This module is the ONE shared writer every call site that wants to record
an ApplicationLifecycleEvent goes through - mirrors app.policy.history's
own "one shared helper module, called explicitly from the few places that
genuinely need it" precedent, rather than a generic ORM before_update hook
or a new event-sourcing framework.

Deliberately NOT a change-detection module - every function here takes an
ALREADY-COMPUTED result from an existing, already-proven deterministic
detector (app.pipeline.material_change.detect_material_application_change,
app.scrapers.unit_filter.classify_application_category) and only decides
how to RECORD it. No detection logic is duplicated or re-derived here.

Architecture-investigation / Product-Owner-amendment provenance: this
module implements exactly the "P0 - Application lifecycle history" item
of the amended Gate 2B-0B V1 (see docs/PRODUCT_ROADMAP.md, "Gate 2B-0B -
Application Lifecycle Intelligence"), using the narrow ApplicationLifecycleEvent
model (app.db.models) the investigation recommended.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import ApplicationLifecycleEvent
from app.pipeline.material_change import (
    REASON_DECISION_GRANTED,
    REASON_DECISION_REFUSED,
    REASON_DECISION_WITHDRAWN,
    REASON_UNIT_COUNT_CHANGED,
    MaterialChangeResult,
)

# --- Bounded event_type vocabulary --------------------------------------
# Plain strings, not a DB enum column (Application.evidence_refresh_
# trigger's own "a future PR can add new values without a schema change"
# precedent) - every value below is actually written by this module today,
# backed by an existing, already-proven deterministic detector.
EVENT_STATUS_CHANGED = "status_changed"
EVENT_DECISION_GRANTED = "decision_granted"
EVENT_DECISION_REFUSED = "decision_refused"
EVENT_DECISION_WITHDRAWN = "decision_withdrawn"
EVENT_UNITS_CHANGED = "units_changed"
EVENT_NEW_RELATED_APPLICATION = "new_related_application"
EVENT_RESERVED_MATTERS_FOUND = "reserved_matters_found"
EVENT_CONDITION_DISCHARGE_FOUND = "condition_discharge_found"

# Extensibility only (Gate 2B-0B investigation §I / roadmap "Event-model
# extensibility") - NOT implemented, NOT written anywhere in this module.
# Recorded here in one place so a future PR extends this same vocabulary
# rather than inventing a second event-type scheme:
#   OFFICER_RECOMMENDATION_CHANGED, COMMITTEE_DATE_ADDED,
#   COMMITTEE_REPORT_ADDED, COMMITTEE_RESOLUTION_ADDED,
#   RESOLUTION_SUBJECT_TO_S106, S106_EXECUTED, DECISION_NOTICE_ADDED,
#   S73_FOUND, NMA_FOUND.
# S73_FOUND/NMA_FOUND specifically are NOT a "not yet built" gap the same
# way the committee/S106 events are - see the KNOWN LIMITATION note on
# _CATEGORY_TO_SPECIFIC_EVENT below for why they are deliberately withheld
# rather than approximated.

# --- Authoritative-source vocabulary ------------------------------------
# Same plain-string-not-enum precedent as event_type above.
SOURCE_SCRAPE = "scrape"
SOURCE_STATUS_VERIFICATION = "status_verification"
SOURCE_RELATED_APPLICATION_DISCOVERY = "related_application_discovery"

_REASON_TO_EVENT_TYPE = {
    REASON_DECISION_GRANTED: EVENT_DECISION_GRANTED,
    REASON_DECISION_REFUSED: EVENT_DECISION_REFUSED,
    REASON_DECISION_WITHDRAWN: EVENT_DECISION_WITHDRAWN,
}


@dataclass
class LifecycleEventStats:
    """One instance per top-level run/invocation (mirrors app.pipeline.
    material_change.MaterialChangeStats's own established pattern) - exists
    purely so the Gate 2B-0B "P0 - Bounded downstream reassessment" trigger
    (app.pipeline.run_weekly.main) can ask "did ANYTHING genuinely change
    this run" once, at the very end, rather than re-syncing the opportunity
    universe once per individual event."""

    written: int = 0

    def record(self, count: int) -> None:
        self.written += count

    @property
    def any_written(self) -> bool:
        return self.written > 0


def _write_event(
    session: Session, *, application_id: int, event_type: str, authoritative_source: str,
    field_name: str | None = None, old_value: object = None, new_value: object = None,
    evidence_document_id: int | None = None, detected_at: dt.datetime | None = None,
) -> None:
    session.add(ApplicationLifecycleEvent(
        application_id=application_id,
        event_type=event_type,
        field_name=field_name,
        old_value=None if old_value is None else str(old_value),
        new_value=None if new_value is None else str(new_value),
        detected_at=detected_at or dt.datetime.now(dt.timezone.utc),
        authoritative_source=authoritative_source,
        evidence_document_id=evidence_document_id,
    ))


def record_material_change_events(
    session: Session, *, application_id: int, result: MaterialChangeResult, authoritative_source: str,
    stats: LifecycleEventStats | None = None,
) -> int:
    """Translates an already-computed app.pipeline.material_change.
    MaterialChangeResult into append-only ApplicationLifecycleEvent rows.
    Writes nothing when result.changed is False - an unchanged re-check
    (VERIFIED_UNCHANGED, or an ordinary scrape resurfacing with no material
    change) is a verification EVENT, never a lifecycle CHANGE, the same
    distinction Application.status_verified_at's own docstring already
    draws for exactly this reason. Never called on a failed/portal-
    unavailable fetch - those outcomes never reach a `result` at all,
    since detect_material_application_change is only ever invoked after a
    genuinely completed fetch+parse (see app.pipeline.run_weekly.
    _upsert_scraped_application and app.pipeline.status_verification.
    verify_application_status, this function's only two callers).

    Returns the number of events written (0 if result.changed is False),
    for the caller's own LifecycleEventStats bookkeeping."""
    if not result.changed:
        return 0

    written = 0
    for reason in result.reasons:
        if reason == REASON_UNIT_COUNT_CHANGED:
            _write_event(
                session, application_id=application_id, event_type=EVENT_UNITS_CHANGED,
                authoritative_source=authoritative_source, field_name="estimated_unit_count",
                old_value=result.old.estimated_unit_count, new_value=result.new.estimated_unit_count,
            )
            written += 1
            continue

        # Every other reason is a planning-state transition (decision
        # granted/refused/withdrawn, or one of the recommendation/status
        # transitions material_change.py does not give its own named
        # event - all recorded as the generic EVENT_STATUS_CHANGED, per
        # this Gate's own "do not fabricate committee/S106 events when the
        # underlying capability does not yet exist" instruction: nothing
        # here invents a finer classification than detect_material_
        # application_change itself already computed). Whichever of
        # status/decision actually differs is the field this event
        # describes - never guessed, always read directly off the
        # ALREADY-COMPUTED old/new ApplicationState.
        event_type = _REASON_TO_EVENT_TYPE.get(reason, EVENT_STATUS_CHANGED)
        if result.old.decision != result.new.decision:
            field_name, old_value, new_value = "decision", result.old.decision, result.new.decision
        else:
            field_name, old_value, new_value = "status", result.old.status, result.new.status
        _write_event(
            session, application_id=application_id, event_type=event_type,
            authoritative_source=authoritative_source, field_name=field_name,
            old_value=old_value, new_value=new_value,
        )
        written += 1

    if stats is not None:
        stats.record(written)
    return written


# Only the two categories app.scrapers.unit_filter.classify_application_
# category can UNAMBIGUOUSLY distinguish are mapped to their own specific
# event type - see the KNOWN LIMITATION note below for why
# "variation_or_amendment" is deliberately NOT split into S73_FOUND/
# NMA_FOUND.
_CATEGORY_TO_SPECIFIC_EVENT = {
    "reserved_matters": EVENT_RESERVED_MATTERS_FOUND,
    "condition_discharge_or_details": EVENT_CONDITION_DISCHARGE_FOUND,
}

# KNOWN LIMITATION (Gate 2B-0B implementation, Phase B) - app.scrapers.
# unit_filter.classify_application_category deliberately collapses a
# genuine Section 73 variation, a non-material amendment, and a deed of
# variation into ONE "variation_or_amendment" category (see that
# function's own docstring - this is an intentional structural label, not
# an oversight). The only other existing signal, is_administrative_
# application_type, returns a single collapsed boolean ("is this ANY
# administrative type" - it also covers screening opinions, adjoining-
# authority consultations, etc.) and does not report WHICH keyword
# matched. There is therefore no existing deterministic signal in this
# codebase that reliably distinguishes a genuine S73 from an NMA from a
# deed of variation. The Gate 2B-0B architecture investigation verified
# only the COMBINED category exists (see docs/PRODUCT_ROADMAP.md, Gate
# 2B-0B's own event taxonomy table: "S73_FOUND / NMA_FOUND - Partially
# supported"); building a new S73-vs-NMA text classifier here would be new
# classification heuristic work never authorised by that investigation,
# and exactly the kind of "fabricate an event the underlying capability
# does not yet exist for" the Product Owner's implementation prompt (§5,
# §25) explicitly rules out - mislabelling a genuine NMA as S73_FOUND (or
# vice versa) would be confidently wrong, which this codebase's own
# "Unknown Must Remain Unknown" design principle (docs/DESIGN_PRINCIPLES.md)
# treats as strictly worse than not distinguishing them at all.
# EVENT_S73_FOUND/EVENT_NMA_FOUND are therefore NOT implemented in this
# phase - every "variation_or_amendment" discovery is recorded as
# NEW_RELATED_APPLICATION only, with the raw category preserved as this
# event's own new_value so it remains inspectable. Splitting them safely
# is flagged as a follow-up requiring its own narrow investigation (a
# proposal-text/Application-Type classifier that can tell "section 73"
# apart from "non-material amendment" apart from "deed of variation"), not
# solved here.


def record_related_application_discovery_event(
    session: Session, *, application_id: int, category: str, stats: LifecycleEventStats | None = None,
) -> int:
    """Called once per genuinely NEW Application row discovered by
    app.pipeline.run_weekly.stage_fetch_related_applications - never for an
    application that already existed (both the idox and arcus branches of
    that stage already skip an existing reference/keyval BEFORE reaching
    the upsert that would otherwise call this). Always records
    NEW_RELATED_APPLICATION; additionally records the specific category
    event where classify_application_category's own category is one of the
    two this module can safely, unambiguously map (see the KNOWN
    LIMITATION note above for why S73/NMA are not split out).

    Returns the number of events written, for the caller's own
    LifecycleEventStats bookkeeping."""
    _write_event(
        session, application_id=application_id, event_type=EVENT_NEW_RELATED_APPLICATION,
        authoritative_source=SOURCE_RELATED_APPLICATION_DISCOVERY,
        field_name="application_category", old_value=None, new_value=category,
    )
    written = 1

    specific = _CATEGORY_TO_SPECIFIC_EVENT.get(category)
    if specific is not None:
        _write_event(
            session, application_id=application_id, event_type=specific,
            authoritative_source=SOURCE_RELATED_APPLICATION_DISCOVERY,
            field_name="application_category", old_value=None, new_value=category,
        )
        written += 1

    if stats is not None:
        stats.record(written)
    return written
