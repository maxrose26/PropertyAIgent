"""Canonical material planning-application change detection (PR B1:
"Material Application-State Detection + Persisted Refresh Signal" - the
first stage of PR B's overall intelligence-freshness architecture, see
specifications/ for the full TRIGGER -> TARGETED EVIDENCE REFRESH -> ...
flow this is designed to feed into later, without implementing any of the
downstream stages here).

B1 answers exactly one question: "has this EXISTING planning application's
decision/status/unit-count state materially changed since PropertyAIgent
last saw it?" - not whether its underlying EVIDENCE (documents) has
changed, which is a distinct, later concern (PR B2/B3) this module
deliberately does not touch. A scheme can remain "Granted subject to
S106" for months while the executed S106 itself is uploaded later with no
application-state change at all - B1 cannot and does not detect that.

Planning-state model (PR B1 amendment, "Planning Recommendations, Decision
States & Future AI Summary Behaviour"): a richer, evidence-grounded state
set than app.pipeline.lapse_tracking.classify_decision_status's original
4-way bucket (granted/refused/withdrawn/not_yet_decided). A READ-ONLY
production audit (SELECT-only, ~1,387 Application rows across 9 Idox/
Arcus councils) found:

- status='Recommendation Made' (Manchester, 6 rows) with decision=NULL -
  a genuine officer-recommendation event, but the RAW DATA DOES NOT STATE
  A DIRECTION (approve vs refuse) for any of these 6 real rows. This
  module therefore recognises a DIRECTIONLESS "recommendation_made" state
  as the evidence-grounded default, and ALSO implements keyword matching
  for directional phrasing ("Officer Recommendation: Approve",
  "Recommended for Refusal", etc. - the task's own named candidate
  vocabulary) for councils/future scrapes that DO state a direction -
  zero real matches for the directional form exist in this snapshot, but
  matching it is not "inventing" since the task itself named these exact
  strings as expected vocabulary to recognise.
- 6 real rows (Rochdale 5, Salford 1) where status is 'Decided'/'Decision
  Made' but decision is NULL/blank, plus 5 real rows (Bolton) where
  status='Decided' and decision='Determined' (a genuinely non-directional
  decision value) - both confirm a real "decided but outcome not stated"
  case, recognised here as "decision_outcome_unknown". Deliberately
  scoped to the STATUS signal only (status contains "decided"/"decision
  made"), NOT "any non-empty unrecognised decision text" - a broader rule
  was considered and rejected after finding it would misclassify
  Salford's 108 'Condition Request determined' rows (status='Closed', an
  unrelated administrative-filing concept) as a decided-but-unknown
  planning outcome, which they are not.

CRITICAL ordering requirement: "recommend" keyword matching happens
BEFORE app.pipeline.lapse_tracking.is_granted_decision's own check
- "Officer Recommendation: Approve" contains the substring "approve",
which would otherwise be wrongly classified as a formal grant by
is_granted_decision's own GRANTED_KEYWORDS=["approve", "grant"] list.
Recommendation states must never collapse into terminal decision buckets
- this is the single most important invariant this module enforces (see
this module's own test file for the two tests that exist specifically to
prove it never regresses).

Scope, deliberately conservative:
- proposal/description text is NEVER compared - portal formatting noise
  (whitespace, punctuation, minor rewording) would create constant false
  refresh events; reliable proposal-change detection is explicitly
  deferred to a later PR.
- administrative/scrape-process metadata (last_seen_at, updated_at, scrape
  timestamps) is never part of the comparison at all.
- a unit-count change only counts if BOTH the old and new counts are
  already known (non-None) - NULL -> 100 is treated as "the count simply
  became known", not a material change, distinct from the decision/status
  rule, where a never-known decision becoming a real terminal one
  (None -> "Granted") IS treated as material.
- a TERMINAL state (granted/refused/withdrawn) regressing to
  not_yet_decided is deliberately NOT treated as material on its own -
  this is portal noise or a data-quality inconsistency (a field that
  temporarily disappeared or was mis-scraped), not a genuine new planning
  event. Every OTHER transition (including a terminal state changing to a
  DIFFERENT terminal state, or a recommendation direction reversing) is
  still material.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.pipeline.lapse_tracking import is_granted_decision

# --- Planning-state vocabulary (PR B1 amendment) ------------------------------
# Not "decision buckets" any more - a genuinely richer state than app.
# pipeline.lapse_tracking.classify_decision_status's original 4-way split,
# which remains completely UNCHANGED (still used, unmodified, by its own
# existing callers - app.search.query_parser, app.reporting.dashboard).
STATE_NOT_YET_DECIDED = "not_yet_decided"
STATE_RECOMMENDATION_MADE = "recommendation_made"
STATE_RECOMMENDED_FOR_APPROVAL = "recommended_for_approval"
STATE_RECOMMENDED_FOR_REFUSAL = "recommended_for_refusal"
STATE_DECISION_OUTCOME_UNKNOWN = "decision_outcome_unknown"
STATE_GRANTED = "granted"
STATE_REFUSED = "refused"
STATE_WITHDRAWN = "withdrawn"

# Formal, final planning outcomes - see this module's own docstring for
# why a regression FROM one of these TO not_yet_decided is deliberately
# not treated as material on its own (likely portal noise), while every
# other transition (including terminal -> different terminal) still is.
TERMINAL_STATES = frozenset({STATE_GRANTED, STATE_REFUSED, STATE_WITHDRAWN})

# Deterministic reason codes (PR B design, Part J: "prefer deterministic
# reason codes over free-form-only text") - the ONLY values
# detect_material_application_change ever returns in `reasons`. Named
# constants, not string literals scattered at each call site.
REASON_DECISION_GRANTED = "decision_granted"
REASON_DECISION_REFUSED = "decision_refused"
REASON_DECISION_WITHDRAWN = "decision_withdrawn"
REASON_RECOMMENDED_FOR_APPROVAL = STATE_RECOMMENDED_FOR_APPROVAL
REASON_RECOMMENDED_FOR_REFUSAL = STATE_RECOMMENDED_FOR_REFUSAL
REASON_RECOMMENDATION_MADE = STATE_RECOMMENDATION_MADE
REASON_DECISION_OUTCOME_UNKNOWN = STATE_DECISION_OUTCOME_UNKNOWN
# Any OTHER planning-state transition not covered by a named reason above
# - e.g. a recommendation/decision-outcome-unknown state reverting to
# not_yet_decided (not suppressed - see this module's own docstring: the
# suppression rule is scoped to TERMINAL_STATES only, not these earlier
# states too). Still genuinely material, just not one of the specific,
# higher-value transitions worth their own named reason.
REASON_STATUS_TRANSITION = "status_transition"
REASON_UNIT_COUNT_CHANGED = "unit_count_changed"

# Maps a NEW planning state to its reason code, when that state is reached
# via a genuine transition (old != new). Every state with real product
# meaning gets its own named reason so a future PR (B2/B3) can route
# refresh depth by reason without re-deriving the state itself - see this
# module's own docstring, "REFRESH DEPTH MUST DEPEND ON EVENT TYPE".
_REASON_BY_NEW_STATE = {
    STATE_GRANTED: REASON_DECISION_GRANTED,
    STATE_REFUSED: REASON_DECISION_REFUSED,
    STATE_WITHDRAWN: REASON_DECISION_WITHDRAWN,
    STATE_RECOMMENDED_FOR_APPROVAL: REASON_RECOMMENDED_FOR_APPROVAL,
    STATE_RECOMMENDED_FOR_REFUSAL: REASON_RECOMMENDED_FOR_REFUSAL,
    STATE_RECOMMENDATION_MADE: REASON_RECOMMENDATION_MADE,
    STATE_DECISION_OUTCOME_UNKNOWN: REASON_DECISION_OUTCOME_UNKNOWN,
}

# Trigger provenance (PR B design, Part I) - the value Application.
# evidence_refresh_trigger is set to whenever THIS module is what set
# evidence_refresh_required. Future PRs will introduce sibling values
# ("periodic_staleness", "manual", "system_recovery") written by their
# own trigger sources into the SAME field - deliberately a plain string
# column, not an enum, so those can be added without a schema change.
# B1 only ever writes this one value.
TRIGGER_MATERIAL_CHANGE = "material_change"


def _classify_planning_state(decision: str | None, status: str | None) -> str:
    """The ONE canonical planning-state classifier for material-change
    purposes - reads raw, un-vocabularied portal text (see this module's
    own docstring for the production audit backing every branch below).
    Deliberately NOT app.pipeline.lapse_tracking.classify_decision_status
    - that function's own 4-way bucket is too coarse for B1's amendment
    (it would collapse "Officer Recommendation: Approve" into "granted"
    via is_granted_decision's own keyword match, and has no representation
    for "decided but outcome not yet known" at all) - left completely
    unmodified for its own existing callers.

    Ordering is load-bearing: "withdraw" is checked first (an
    unambiguous, rare signal); "recommend" is checked BEFORE
    is_granted_decision/refuse, specifically to stop a recommendation's
    own "approve"/"refuse" wording from being misread as a formal
    decision; only once neither matches do the formal terminal checks
    run; "decided"/"decision made" status text is the last, narrowest
    fallback, checked only against `status` (not any non-empty decision
    text - see this module's own docstring for the real production case,
    Salford's 'Condition Request determined', that rejected a broader
    rule)."""
    decision_lower = (decision or "").lower()
    status_lower = (status or "").lower()
    combined = f"{decision_lower} {status_lower}"

    if "withdraw" in decision_lower or "withdraw" in status_lower:
        return STATE_WITHDRAWN

    if "recommend" in combined:
        if "refus" in combined:
            return STATE_RECOMMENDED_FOR_REFUSAL
        if "approv" in combined or "grant" in combined:
            return STATE_RECOMMENDED_FOR_APPROVAL
        return STATE_RECOMMENDATION_MADE

    if is_granted_decision(decision):
        return STATE_GRANTED
    if "refuse" in decision_lower:
        return STATE_REFUSED

    if "decided" in status_lower or "decision made" in status_lower:
        return STATE_DECISION_OUTCOME_UNKNOWN

    return STATE_NOT_YET_DECIDED


@dataclass(frozen=True)
class ApplicationState:
    """The narrow slice of Application state B1 ever compares old-vs-new
    - deliberately NOT the whole row. Callers build one of these from an
    Application's CURRENT field values; app.pipeline.run_weekly's own
    _upsert_scraped_application snapshots one of these before its
    existing FIELD_MAP mutation loop overwrites the row in place (that
    session uses expire_on_commit=False - the ORM object is mutated
    directly, not replaced, so there is no later point at which the OLD
    values would still be recoverable)."""

    status: str | None
    decision: str | None
    estimated_unit_count: int | None


@dataclass(frozen=True)
class MaterialChangeResult:
    """Structured output (PR B design, Part E: "prefer structured output
    rather than only boolean") - `changed` is the single boolean a caller
    needs to decide whether to persist the refresh signal at all;
    `reasons` (always deterministically ordered: the planning-state
    reason before the unit-count reason, never dict/set iteration order)
    is what PR B1's own observability and evidence_refresh_reason
    persistence use. `old_planning_state`/`new_planning_state` are
    included purely for logging/auditability - the same
    _classify_planning_state() values the comparison itself was based
    on, not a second, separately-derived value."""

    changed: bool
    reasons: tuple[str, ...]
    old: ApplicationState
    new: ApplicationState
    old_planning_state: str
    new_planning_state: str


def detect_material_application_change(old: ApplicationState, new: ApplicationState) -> MaterialChangeResult:
    """The ONE canonical material-change classifier (PR B design, Part E:
    "do not scatter comparison logic throughout council scrapers") -
    every caller in this codebase must go through this function rather
    than re-implementing any part of this comparison itself.

    Planning-state rule: classify BOTH old and new via
    _classify_planning_state (see that function's own docstring for the
    full state machine and the production evidence behind it). A state
    change is material EXCEPT a TERMINAL state (granted/refused/
    withdrawn) regressing to not_yet_decided, which is deliberately
    suppressed - see this module's own top-level docstring for why. A
    raw-text-only change that still lands in the SAME state (e.g.
    "Approved" -> "Granted", both STATE_GRANTED) is correctly NOT
    material - this is what "normalization prevents false changes" means
    in practice.

    Unit-count rule: only material when BOTH old and new counts are
    already known (non-None) and they differ - see this module's own
    docstring for why a never-known -> known transition is deliberately
    NOT treated the same way the planning-state rule treats it."""
    reasons: list[str] = []

    old_state = _classify_planning_state(old.decision, old.status)
    new_state = _classify_planning_state(new.decision, new.status)
    if old_state != new_state:
        if old_state in TERMINAL_STATES and new_state == STATE_NOT_YET_DECIDED:
            # A formal outcome regressing to "nothing decided yet" is
            # portal noise or a data-quality inconsistency, not a new
            # material planning event - deliberately suppressed (see this
            # module's own docstring).
            pass
        else:
            reasons.append(_REASON_BY_NEW_STATE.get(new_state, REASON_STATUS_TRANSITION))

    if (
        old.estimated_unit_count is not None
        and new.estimated_unit_count is not None
        and old.estimated_unit_count != new.estimated_unit_count
    ):
        reasons.append(REASON_UNIT_COUNT_CHANGED)

    return MaterialChangeResult(
        changed=bool(reasons), reasons=tuple(reasons), old=old, new=new,
        old_planning_state=old_state, new_planning_state=new_state,
    )


@dataclass
class MaterialChangeStats:
    """Deliberately separate from app.pipeline.acquisition_health.
    AcquisitionHealth (PR B design, Part Y) - that module is scoped
    specifically to NETWORK/portal acquisition health (Render Daily
    Discovery Portal Resilience & Truthful Run Health's own explicit
    "NOT a general metrics framework" scope), and material-change
    detection is a pure in-process comparison, not a network operation.
    One instance per council per run_weekly.py process, held by whichever
    stage calls _upsert_scraped_application for EXISTING applications
    (currently stage_scrape; stage_fetch_missing_parents may also pass
    one for consistency, though its own upserts are typically brand-new
    parent rows)."""

    compared: int = 0
    material_changes: int = 0
    reason_counts: dict[str, int] | None = None

    def __post_init__(self) -> None:
        if self.reason_counts is None:
            self.reason_counts = {}

    def record(self, result: MaterialChangeResult) -> None:
        self.compared += 1
        if not result.changed:
            return
        self.material_changes += 1
        for reason in result.reasons:
            self.reason_counts[reason] = self.reason_counts.get(reason, 0) + 1

    def summary_line(self, council_code: str) -> str:
        """Deliberately only ever printed ONCE per stage run (never per
        application - PR B design, Part Y: "Do not log every unchanged
        application"), summarising the whole batch this stats instance
        observed."""
        reason_part = " ".join(f"{reason}={count}" for reason, count in sorted(self.reason_counts.items()))
        line = f"[material-change] council={council_code} summary compared={self.compared} material_changes={self.material_changes}"
        return f"{line} {reason_part}" if reason_part else line
