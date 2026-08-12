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
application-state change at all - B1 cannot and does not detect that; see
this module's own module-level docstring in the wider PR B design report
for why application-state freshness and evidence freshness are kept as
two separate concepts from the start.

Deliberately reuses app.pipeline.lapse_tracking.classify_decision_status
- the ONE existing decision/status bucket vocabulary in this codebase
(granted/refused/withdrawn/not_yet_decided) - rather than inventing a
second, competing classification. A full audit (PR B design report, Part
C) confirmed there is no richer normalized vocabulary anywhere in this
project to compare against instead (status/decision are raw, un-
vocabularied portal text that varies per council/vendor) - reusing the
existing 4-way bucket is also what keeps this module from needing its own
keyword lists that could drift out of sync with is_granted_decision's own.

Scope, deliberately conservative (see the PR B design report, Part F, for
the full reasoning behind each exclusion):
- proposal/description text is NEVER compared - portal formatting noise
  (whitespace, punctuation, minor rewording) would create constant false
  refresh events; reliable proposal-change detection is explicitly
  deferred to a later PR.
- administrative/scrape-process metadata (last_seen_at, updated_at, scrape
  timestamps) is never part of the comparison at all.
- a unit-count change only counts if BOTH the old and new counts are
  already known (non-None) - NULL -> 100 is treated as "the count simply
  became known", not a material change (the conservative rule the task
  itself specifies), distinct from the decision/status rule, where a
  never-known decision becoming a real terminal one (None -> "Granted")
  IS treated as material - these two fields have different starting
  assumptions and deliberately are not handled identically.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.pipeline.lapse_tracking import classify_decision_status

# Deterministic reason codes (PR B design, Part J: "prefer deterministic
# reason codes over free-form-only text") - the ONLY values
# detect_material_application_change ever returns in `reasons`. Named
# constants, not string literals scattered at each call site.
REASON_DECISION_GRANTED = "decision_granted"
REASON_DECISION_REFUSED = "decision_refused"
REASON_DECISION_WITHDRAWN = "decision_withdrawn"
# Any OTHER decision-bucket transition not covered by the three named
# reasons above - e.g. a terminal decision reverting to not_yet_decided,
# or a correction from one terminal bucket straight to a different one
# (refused -> granted). Still genuinely material (the application's
# known state changed), just not one of the three specific, higher-
# value transitions worth their own named reason.
REASON_STATUS_TRANSITION = "status_transition"
REASON_UNIT_COUNT_CHANGED = "unit_count_changed"

# Trigger provenance (PR B design, Part I) - the value Application.
# evidence_refresh_trigger is set to whenever THIS module is what set
# evidence_refresh_required. Future PRs will introduce sibling values
# ("periodic_staleness", "manual", "system_recovery") written by their
# own trigger sources into the SAME field - deliberately a plain string
# column, not an enum, so those can be added without a schema change.
# B1 only ever writes this one value.
TRIGGER_MATERIAL_CHANGE = "material_change"


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
    `reasons` (always deterministically ordered: decision/status reasons
    before the unit-count reason, never dict/set iteration order) is what
    PR B1's own observability and evidence_refresh_reason persistence use.
    `old_decision_bucket`/`new_decision_bucket` are included purely for
    logging/auditability - the same classify_decision_status() buckets
    the comparison itself was based on, not a second, separately-derived
    value."""

    changed: bool
    reasons: tuple[str, ...]
    old: ApplicationState
    new: ApplicationState
    old_decision_bucket: str
    new_decision_bucket: str


def detect_material_application_change(old: ApplicationState, new: ApplicationState) -> MaterialChangeResult:
    """The ONE canonical material-change classifier (PR B design, Part E:
    "do not scatter comparison logic throughout council scrapers") -
    every caller in this codebase must go through this function rather
    than re-implementing any part of this comparison itself.

    Decision/status rule: classify BOTH old and new via the existing
    classify_decision_status(decision, status) bucket (granted/refused/
    withdrawn/not_yet_decided - see this module's own docstring for why
    this reuses that function rather than inventing a second
    vocabulary). A bucket change is material; a raw-text-only change that
    still lands in the SAME bucket (e.g. "Approved" -> "Granted", or one
    council's "Awaiting Decision" phrasing vs another's "Pending
    Decision") is correctly NOT material - this is what "normalization
    prevents false changes" means in practice, and is exactly why this
    doesn't do its own naive decision/status string-equality check.

    Unit-count rule: only material when BOTH old and new counts are
    already known (non-None) and they differ - see this module's own
    docstring for why a never-known -> known transition is deliberately
    NOT treated the same way the decision/status rule treats it."""
    reasons: list[str] = []

    old_bucket = classify_decision_status(old.decision, old.status)
    new_bucket = classify_decision_status(new.decision, new.status)
    if old_bucket != new_bucket:
        if new_bucket == "granted":
            reasons.append(REASON_DECISION_GRANTED)
        elif new_bucket == "refused":
            reasons.append(REASON_DECISION_REFUSED)
        elif new_bucket == "withdrawn":
            reasons.append(REASON_DECISION_WITHDRAWN)
        else:
            reasons.append(REASON_STATUS_TRANSITION)

    if (
        old.estimated_unit_count is not None
        and new.estimated_unit_count is not None
        and old.estimated_unit_count != new.estimated_unit_count
    ):
        reasons.append(REASON_UNIT_COUNT_CHANGED)

    return MaterialChangeResult(
        changed=bool(reasons), reasons=tuple(reasons), old=old, new=new,
        old_decision_bucket=old_bucket, new_decision_bucket=new_bucket,
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
