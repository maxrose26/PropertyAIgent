"""Versioned browser source execution budgets (docs/design/execution-budget-20261026/SPEC.md).

`None` everywhere means the historical envelope, implemented by the unchanged literals at each
call site. `BROWSER_SOURCE_V2` is selected only by THREE_COUNCIL_SOURCE_RELEASE_V2 registrations.
Limits are kernel/supervisor ceilings, not reserved resources or a guarantee of fit.
"""
import time

# Public names stay byte-for-byte equivalent; application code owns the pure registry.
from app.ingestion.source_budget import MiB, HISTORICAL, BROWSER_SOURCE_V2, BUDGETS, select

STAGES = ('NAVIGATION', 'READY', 'CRITERIA', 'SEGMENT')
MAX_SEGMENT_TIMINGS = 6

class ObservationDeadline(Exception):
    """The single observation deadline left no (or too little) time for a wait."""


class Deadline:
    """One observation deadline; every wait is capped at min(step, remaining)."""

    def __init__(self, seconds, clock=time.monotonic, started=None):
        """started: an earlier origin on the same clock (the supervisor's start), never later."""
        if not 0 < seconds <= 600:
            raise ValueError('deadline seconds')
        self.clock = clock
        now = clock()
        if started is not None and not (type(started) is float and now - seconds <= started <= now):
            raise ValueError('deadline origin')
        self.started = now if started is None else started
        self.end = self.started + seconds
        self.truncated = False  # the most recent cap was shortened by the deadline

    def remaining(self):
        return max(0.0, self.end - self.clock())

    def cap(self, step_seconds):
        remaining = self.remaining()
        if remaining <= 0:
            raise ObservationDeadline('OBSERVATION_DEADLINE')
        self.truncated = remaining < step_seconds
        return min(step_seconds, remaining)

    def cap_ms(self, step_seconds):
        return max(1, int(self.cap(step_seconds) * 1000))

    def elapsed_ms(self, since):
        return max(0, int((self.clock() - since) * 1000))
