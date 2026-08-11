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

    def record_primary_scrape_attempt(self) -> None:
        self.primary_scrape_attempted = True

    def record_primary_scrape_completed(self) -> None:
        self.primary_scrape_completed = True

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

    def classify(self) -> str:
        """Returns "success" | "partial" | "failed" - approved policy,
        amended (Render Daily Discovery Portal Resilience & Truthful Run
        Health, "Pre-Merge Health Classification Amendment"):

        FAILED - the primary/current-period scrape was attempted but did
        not complete (this is the Trafford scenario: a silently swallowed
        Playwright timeout must never look identical to a genuine,
        successful zero-application day - see PARTIAL/SUCCESS below for
        why that distinction is preserved).

        PARTIAL - the primary scrape completed, but ONE OR MORE attempted
        CORE supporting acquisition operations (parent lookup, document
        discovery) exhausted their retry budget and ultimately failed.
        Any single unresolved failure is enough - this is deliberately
        NOT a "100% failure of the whole stage" rule (the original design
        here, replaced by this amendment: 49 of 50 document-discovery
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
        excluded, unchanged - this amendment only lowers classify()'s own
        threshold, not what counts as a recorded failure in the first
        place).

        SUCCESS - the primary scrape completed and every attempted core
        supporting acquisition operation ultimately succeeded (i.e. zero
        unresolved failures recorded).

        Still deliberately NOT a percentage/ratio threshold - no
        production evidence yet justifies picking one (unchanged
        rationale from the original design, reaffirmed by this
        amendment). The conservative direction has simply flipped from
        "only total failure counts" to "any known unresolved failure
        counts", to avoid the false-SUCCESS risk the original threshold
        allowed."""
        if self.primary_scrape_attempted and not self.primary_scrape_completed:
            return "failed"

        if self.parents_failed > 0 or self.documents_applications_failed > 0:
            return "partial"

        return "success"

    def summary_line(self) -> str:
        """One deterministic, single-line, machine-parseable summary -
        scripts.run_daily_councils parses this by its "[run-health]"
        prefix and `status=` field, never by scraping arbitrary
        human-readable log text (Part 4's explicit requirement)."""
        return (
            f"[run-health] status={self.classify()} "
            f"primary_scrape_attempted={int(self.primary_scrape_attempted)} "
            f"primary_scrape_completed={int(self.primary_scrape_completed)} "
            f"parents_attempted={self.parents_attempted} "
            f"parents_succeeded={self.parents_succeeded} "
            f"parents_failed={self.parents_failed} "
            f"documents_applications_attempted={self.documents_applications_attempted} "
            f"documents_applications_succeeded={self.documents_applications_succeeded} "
            f"documents_applications_failed={self.documents_applications_failed}"
        )
