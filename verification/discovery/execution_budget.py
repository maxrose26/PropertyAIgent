"""Versioned browser source execution budgets (docs/design/execution-budget-20261026/SPEC.md).

`None` everywhere means the historical envelope, implemented by the unchanged literals at each
call site. `BROWSER_SOURCE_V2` is selected only by THREE_COUNCIL_SOURCE_RELEASE_V2 registrations.
Limits are kernel/supervisor ceilings, not reserved resources or a guarantee of fit.
"""
import time

MiB = 1024 ** 2
# Mirrors four_council_release.HISTORICAL_BUDGET plus the supervisor keys; tests keep them equal.
HISTORICAL = dict(name=None, worker_seconds=45, source_outer_seconds=49, slot_active_seconds=60,
                  source_memory_bytes=1024 ** 3, aggregate_memory_bytes=1536 * MiB,
                  controller_memory_bytes=256 * MiB, rss_ceiling_bytes=1024 ** 3)
BROWSER_SOURCE_V2 = dict(name='BROWSER_SOURCE_V2', navigation_seconds=25, ready_seconds=20,
                         criteria_seconds=10, segment_poll_seconds=8, segment_click_seconds=3,
                         worker_seconds=75, finalisation_reserve_seconds=5, source_outer_seconds=80,
                         slot_active_seconds=90, source_memory_bytes=1536 * MiB,
                         aggregate_memory_bytes=2048 * MiB, controller_memory_bytes=256 * MiB,
                         rss_ceiling_bytes=1536 * MiB)
BUDGETS = {'BROWSER_SOURCE_V2': BROWSER_SOURCE_V2}
STAGES = ('NAVIGATION', 'READY', 'CRITERIA', 'SEGMENT')
MAX_SEGMENT_TIMINGS = 6


def select(name):
    """Budget for an explicit name; None selects the historical envelope."""
    if name is None:
        return HISTORICAL
    if name not in BUDGETS:
        raise ValueError('EXECUTION_BUDGET')
    return BUDGETS[name]


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
