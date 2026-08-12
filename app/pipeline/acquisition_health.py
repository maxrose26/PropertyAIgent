"""Daily Discovery acquisition-health tracking (Render Daily Discovery
Portal Resilience & Truthful Run Health).

Tracks, for ONE council's app.pipeline.run_weekly invocation, whether the
actual DATA ACQUISITION materially succeeded - a question distinct from
"did the Python process crash" (scripts.run_daily_councils' own
return_code check, unaffected by this module). A production run found
Trafford's current-period scrape silently timing out (Playwright
navigation timeout), the exception caught and swallowed by run_weekly.py's
own per-month try/except (by design - one bad month must not abort every
other stage), and the subprocess exiting 0 regardless - reported as
"trafford: OK (+0 applications)", indistinguishable from a genuinely
healthy run that happened to find nothing new. This module exists to make
that distinction possible without changing the failure-isolation behaviour
itself.

Deliberately minimal - counts, not per-item state, and no schema/database
involvement at all (see this project's own portal-resilience audit,
"capture raw attempted/succeeded/failed counts... conservative
deterministic rules for clearly material failure cases"). NOT a general
metrics framework - one AcquisitionHealth instance lives for the duration
of one council's run_weekly.py process and is discarded when it exits.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AcquisitionHealth:
    """See this module's own docstring. `classify()` returns "success" |
    "partial" | "failed" - the ONLY three values scripts.run_daily_councils
    ever writes to the existing ScrapeRun.status column (Part 4/5 of the
    approved design - no schema migration)."""

    primary_scrape_attempted: bool = False
    primary_scrape_completed: bool = False

    parents_attempted: int = 0
    parents_succeeded: int = 0
    parents_failed: int = 0

    documents_applications_attempted: int = 0
    documents_applications_succeeded: int = 0
    documents_applications_failed: int = 0

    # Hotfix second pre-merge amendment ("Circuit Breaker Must Affect Run
    # Health") - a narrowly-scoped, independent classification input: was
    # this council's app.pipeline.portal_circuit_breaker.
    # CouncilPortalCircuitBreaker ever open by the end of this run, and if
    # so, which stage's 3rd consecutive host-level failure opened it.
    # Deliberately NOT folded into parents_failed/documents_applications_
    # failed - those counters mean "this many attempted operations
    # ultimately failed", a different, already-correct fact that must not
    # be inflated just to force a status. This is its own independent
    # signal: "supporting network acquisition was deliberately ABORTED
    # because the portal circuit opened", which can be true even for
    # stages (stage_fetch_related_applications, stage_confirm_units) that
    # have never recorded a pass/fail count here at all - see classify()'s
    # own docstring for why a circuit-open must still guarantee at least
    # PARTIAL regardless of which stage tripped it.
    portal_circuit_opened: bool = False
    portal_circuit_opened_stage: str | None = None

    # PR B2 (Targeted Evidence Refresh), Part 21 - a narrow, independent
    # signal for evidence-refresh SUPPORTING work only, deliberately NOT
    # folded into parents_failed/documents_applications_failed (those two
    # counters mean "primary/document-discovery acquisition failed", a
    # different, already-correct fact). A council whose primary scrape
    # completed cleanly but whose evidence-refresh backlog hit a portal_
    # unavailable/acquisition_incomplete outcome must report PARTIAL, never
    # FAILED (Part 21: "Primary scrape failure -> existing FAILED semantics
    # still win") and never a false SUCCESS either.
    evidence_refresh_attempted: int = 0
    evidence_refresh_succeeded: int = 0
    evidence_refresh_failed: int = 0

    def record_primary_scrape_attempt(self) -> None:
        self.primary_scrape_attempted = True

    def record_primary_scrape_completed(self) -> None:
        self.primary_scrape_completed = True

    def record_portal_unavailable(self, stage: str) -> None:
        """The ONE central call site for this (app.pipeline.run_weekly.
        main(), once, right before the final [run-health] line is
        printed - checking breaker.is_open at that point already reflects
        the circuit's final state for the whole run, since it never
        closes again once open) - deliberately not scattered across every
        individual stage's own except block, which already has its own
        breaker.record_failure() call for the circuit's OWN bookkeeping;
        this is a single, separate integration point translating that
        into health's third status axis."""
        self.portal_circuit_opened = True
        self.portal_circuit_opened_stage = stage

    def record_parent_lookup(self, *, succeeded: bool) -> None:
        self.parents_attempted += 1
        if succeeded:
            self.parents_succeeded += 1
        else:
            self.parents_failed += 1

    def record_document_discovery(self, *, succeeded: bool) -> None:
        """One call per APPLICATION whose document discovery was
        attempted (not per document) - matches stage_documents' own
        application-level loop structure and the approved design's own
        "document discovery: applications attempted/succeeded/failed"
        framing. A single failed document within an otherwise-successful
        application's discovery is not recorded here as a failure - that
        is the separate, deliberately-not-fixed-in-this-branch
        partial-document-reprocessing gap (see run_weekly.py's own
        stage_documents docstring / the portal-resilience audit's Part
        8 for that distinct, known issue)."""
        self.documents_applications_attempted += 1
        if succeeded:
            self.documents_applications_succeeded += 1
        else:
            self.documents_applications_failed += 1

    def record_evidence_refresh(self, *, succeeded: bool) -> None:
        """One call per Application a targeted evidence refresh actually
        attempted (app.pipeline.evidence_refresh.refresh_material_evidence)
        - succeeded means the check itself genuinely completed (outcome
        NEW_MATERIAL_EVIDENCE or CHECKED_NO_NEW_EVIDENCE, whichever way the
        finding went); PORTAL_UNAVAILABLE/ACQUISITION_INCOMPLETE count as
        not succeeded here, same "did the acquisition attempt itself
        resolve" framing as record_document_discovery above."""
        self.evidence_refresh_attempted += 1
        if succeeded:
            self.evidence_refresh_succeeded += 1
        else:
            self.evidence_refresh_failed += 1

    def classify(self) -> str:
        """Returns "success" | "partial" | "failed" - approved policy,
        amended twice (Render Daily Discovery Portal Resilience & Truthful
        Run Health, "Pre-Merge Health Classification Amendment"; Hotfix
        second pre-merge amendment, "Circuit Breaker Must Affect Run
        Health"):

        FAILED - the primary/current-period scrape was attempted but did
        not complete (this is the Trafford scenario: a silently swallowed
        Playwright timeout must never look identical to a genuine,
        successful zero-application day - see PARTIAL/SUCCESS below for
        why that distinction is preserved). Includes the case where the
        portal circuit was already open before the primary scrape was
        even attempted (app.pipeline.run_weekly.main() then never calls
        record_primary_scrape_completed() for it) - "could not
        meaningfully complete because the portal circuit opened" is still
        exactly this same condition, not a separate one.

        PARTIAL - the primary scrape completed, but EITHER (a) one or
        more attempted CORE supporting acquisition operations (parent
        lookup, document discovery) exhausted their retry budget and
        ultimately failed, OR (b) the portal circuit opened at any point
        during supporting acquisition (record_portal_unavailable was
        called) - a council whose remaining supporting network work was
        deliberately ABORTED because the portal was unavailable must
        never report SUCCESS, even if that abort happened entirely inside
        a stage (stage_fetch_related_applications, stage_confirm_units)
        that has never itself recorded a parents_failed/documents_
        applications_failed count. These two conditions are independent -
        (b) never inflates the (a) counters, and (a) is unaffected by
        whether the circuit ever opened. Any single unresolved failure
        (whichever condition) is enough - this is deliberately NOT a
        "100% failure of the whole stage" rule (the original design here,
        replaced by an earlier amendment: 49 of 50 document-discovery
        failures previously still classified SUCCESS, which conflicts
        with "SUCCESS must not imply known completeness where core
        planning-data acquisition actually failed"). A transient error
        that succeeds within its own retry budget - see get_with_retry/
        _goto_with_retry in app.scrapers.idox_portal - is NOT a failure
        by the time it reaches here: record_parent_lookup/
        record_document_discovery are only ever called with
        succeeded=False in run_weekly.py's own except blocks, which only
        run AFTER that retry budget is already exhausted (429 -> retry ->
        success, ConnectTimeout -> retry -> success, and a Playwright
        navigation timeout -> retry -> success are therefore already
        excluded, unchanged).

        SUCCESS - the primary scrape completed, every attempted core
        supporting acquisition operation ultimately succeeded (zero
        unresolved failures recorded), AND the portal circuit never
        opened.

        Still deliberately NOT a percentage/ratio threshold - no
        production evidence yet justifies picking one. The conservative
        direction has simply flipped from "only total failure counts" to
        "any known unresolved failure counts OR a deliberate portal-
        outage abort", to avoid the false-SUCCESS risk a narrower rule
        would allow."""
        if self.primary_scrape_attempted and not self.primary_scrape_completed:
            return "failed"

        if (
            self.parents_failed > 0 or self.documents_applications_failed > 0
            or self.portal_circuit_opened or self.evidence_refresh_failed > 0
        ):
            return "partial"

        return "success"

    def summary_line(self) -> str:
        """One deterministic, single-line, machine-parseable summary -
        scripts.run_daily_councils parses this by its "[run-health]"
        prefix and `status=` field, never by scraping arbitrary
        human-readable log text (Part 4's explicit requirement). The two
        portal_circuit_* fields are appended at the end, after every
        pre-existing field - the stable status=/existing-field contract
        that parser depends on is unchanged, this is purely additive
        diagnostic detail (never a secret or a raw URL - just the stage
        name already passed to CouncilPortalCircuitBreaker.record_failure
        elsewhere in this same run's own [circuit] log lines)."""
        return (
            f"[run-health] status={self.classify()} "
            f"primary_scrape_attempted={int(self.primary_scrape_attempted)} "
            f"primary_scrape_completed={int(self.primary_scrape_completed)} "
            f"parents_attempted={self.parents_attempted} "
            f"parents_succeeded={self.parents_succeeded} "
            f"parents_failed={self.parents_failed} "
            f"documents_applications_attempted={self.documents_applications_attempted} "
            f"documents_applications_succeeded={self.documents_applications_succeeded} "
            f"documents_applications_failed={self.documents_applications_failed} "
            f"portal_circuit_opened={int(self.portal_circuit_opened)} "
            f"portal_circuit_opened_stage={self.portal_circuit_opened_stage or 'none'} "
            f"evidence_refresh_attempted={self.evidence_refresh_attempted} "
            f"evidence_refresh_succeeded={self.evidence_refresh_succeeded} "
            f"evidence_refresh_failed={self.evidence_refresh_failed}"
        )
