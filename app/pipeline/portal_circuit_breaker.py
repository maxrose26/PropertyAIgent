"""Council-scoped, run-scoped portal circuit breaker (Hotfix: Recovery-First
Council Processing + Portal Circuit Breaker).

Production evidence: once a council's portal host is genuinely unreachable
(Trafford confirmed repeatedly hitting ERR_CONNECTION_TIMED_OUT/
ConnectTimeoutError/"Max retries exceeded"), Property AIgent could spend many
minutes retrying that same unavailable host across many different
applications before a council's run finally ended - app.scrapers.idox_portal's
own get_with_retry/_goto_with_retry already retry ONE request a bounded
number of times (MAX_RETRIES=4 / GOTO_MAX_ATTEMPTS=3), but nothing above that
noticed "the last several DIFFERENT applications all failed for the same
host-unavailable reason" and stopped trying further ones.

This module is deliberately the smallest thing that fixes that: one small
object, held for the duration of ONE council's app.pipeline.run_weekly
process (same lifetime as app.pipeline.acquisition_health.AcquisitionHealth -
constructed once in main(), discarded when the process exits). It tracks
CONSECUTIVE host-level failures across whatever per-application network
calls a caller feeds it; once PORTAL_CIRCUIT_FAILURE_THRESHOLD is reached
without an intervening success, the circuit opens and stays open for the
rest of that process - there is no cross-run persistence, no database
column, and no separate retry scheduler. The next Daily Discovery run
constructs a brand new instance (a fresh subprocess per council, per
scripts.run_daily_councils's own existing architecture), so the breaker
resets automatically - the existing daily Cron IS the next retry
opportunity, exactly as directed.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

# Small enough to fail fast (stop burning run time on an unreachable host),
# large enough not to react to one transient request - matches the Product
# Owner's own starting hypothesis, confirmed reasonable against the real
# call flow: app.scrapers.idox_portal.get_with_retry/_goto_with_retry each
# already retry ONE request internally (4 / 3 attempts) before ever raising
# - by the time an exception reaches this breaker at all, it has already
# survived that whole internal retry budget and still failed, so 3
# consecutive occurrences of THAT is a much stronger signal than 3 raw
# request attempts would be. A single named constant, not a literal
# scattered through the pipeline.
PORTAL_CIRCUIT_FAILURE_THRESHOLD = 3


def is_portal_host_failure(exc: BaseException) -> bool:
    """The one canonical answer to "does this exception indicate the
    portal HOST is unavailable" (as opposed to a live-but-rate-limiting or
    live-but-erroring portal). Deliberately reuses exactly the exception
    types app.scrapers.idox_portal's own get_with_retry/_goto_with_retry
    already treat as connection-level failures - not a new, separately
    invented classification:

    - requests.exceptions.ConnectTimeout / requests.exceptions.ConnectionError
      - a real connection-establishment failure (confirmed Trafford
      production behaviour: "Max retries exceeded... Connection timed
      out") - no HTTP response is ever received to inspect a status code
      on. ConnectTimeout is itself a subclass of ConnectionError; both are
      named explicitly for clarity, matching get_with_retry's own style.
    - playwright.sync_api.TimeoutError - a Playwright navigation timeout
      (ERR_CONNECTION_TIMED_OUT and equivalent), the same exception
      _goto_with_retry already retries internally.

    Deliberately does NOT match:
    - requests.exceptions.HTTPError (429, 404, 500, ...) - a real HTTP
      response WAS received, so the portal/host is demonstrably up; a 429
      is the portal explicitly rate-limiting (existing Retry-After/backoff
      pacing in get_with_retry already handles this, unchanged), and a
      404/500 is a permanent, application-level error, not evidence of a
      host outage.
    - any other exception (e.g. a parsing/extraction error on one
      malformed document) - not host-level evidence either way."""
    return isinstance(exc, (
        requests.exceptions.ConnectTimeout,
        requests.exceptions.ConnectionError,
        PlaywrightTimeoutError,
    ))


@dataclass
class CouncilPortalCircuitBreaker:
    """One instance per council per run_weekly.py process - see this
    module's own docstring for the full lifetime/reset rationale.
    Deliberately no global mutable state, no cross-run persistence, no new
    dependency: a single dataclass a caller holds and passes into whichever
    stage functions make per-application network calls."""

    council_code: str
    threshold: int = PORTAL_CIRCUIT_FAILURE_THRESHOLD
    consecutive_host_failures: int = 0
    open_reason: str | None = None
    _open: bool = False

    @property
    def is_open(self) -> bool:
        return self._open

    def record_success(self) -> None:
        """A successful portal round-trip resets the CONSECUTIVE
        host-failure count - "3 consecutive failures", not "3 failures
        accumulated anywhere during a long run" (an intermittent timeout
        followed by genuine successes must not eventually trip the
        circuit through pure noise). No-op once the circuit is already
        open: every caller is expected to check is_open before attempting
        further network work, so a stray record_success() reaching here
        after that point is defensive, not a real path - and an open
        circuit must stay open for the rest of the run regardless."""
        if self._open:
            return
        self.consecutive_host_failures = 0

    def record_failure(self, exc: BaseException, *, stage: str) -> bool:
        """Classifies exc via is_portal_host_failure - only a genuine
        host-level failure counts toward the circuit. Anything else (an
        HTTP 429/404, a single malformed document, ...) is silently
        ignored here: neither increments nor resets the consecutive
        count, since it is neither new evidence of a host outage nor
        evidence the host is fine.

        Returns True if THIS call caused the circuit to open, so a caller
        can react immediately within the same loop iteration rather than
        waiting for its next is_open check."""
        if self._open:
            return False
        if not is_portal_host_failure(exc):
            return False

        self.consecutive_host_failures += 1
        print(
            f"[circuit] council={self.council_code} "
            f"host_failure={self.consecutive_host_failures}/{self.threshold} stage={stage}"
        )
        if self.consecutive_host_failures >= self.threshold:
            self._open = True
            self.open_reason = "portal_unavailable"
            print(f"[circuit] council={self.council_code} OPEN reason={self.open_reason}")
            return True
        return False
