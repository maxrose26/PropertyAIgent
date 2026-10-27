"""Exact reviewed source-budget registry shared by readers and retained-capture validation.

None preserves the historical envelope. No caller-supplied limits or inferred selection.
"""
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


def select(name):
    """Budget for an explicit name; None selects the historical envelope."""
    if name is None:
        return HISTORICAL
    if name not in BUDGETS:
        raise ValueError('EXECUTION_BUDGET')
    return BUDGETS[name]
