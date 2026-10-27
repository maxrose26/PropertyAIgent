"""Outer-supervisor evidence for a release slot, built ONLY from what the outer supervisor actually observed.

The ledger's `validate_outer` accepts an outer object only when every field is a positively observed, compliant value. This module never fills a field from a default, from the child's
exit status alone, or from the absence of an error: an observation that could not be made is `None` and the cleanup state is then `UNKNOWN`, which `validate_outer` refuses.
Pure; no I/O except the two bounded cgroup readbacks in `observe_group`.
"""
import hashlib
from pathlib import Path

KEYS = ('exit_code', 'peak_owned_rss', 'elapsed_seconds', 'cleanup', 'live_owned_survivors', 'expired', 'limit_hit', 'deadline_seconds', 'evidence')
EVIDENCE = 'SOURCE_CGROUP_READBACK'


def observe_group(group):
    """(peak_owned_rss, live_owned_survivors) read back from the source cgroup after termination; either is None when it could not be read as a plain non-negative integer."""
    group = Path(group)
    try:
        peak = int(group.joinpath('memory.peak').read_text().strip())
        peak = peak if peak >= 0 else None
    except (OSError, ValueError):
        peak = None
    try:
        survivors = len(group.joinpath('cgroup.procs').read_text().split())
    except OSError:
        survivors = None
    return peak, survivors


def outer_supervisor(*, exit_code, elapsed_seconds, closure, peak_owned_rss, live_owned_survivors, deadline_seconds):
    """The outer object of one slot. `cleanup` is CLOSED only when the cgroup was read back empty, the child was reaped, no cleanup step failed and zero survivors were observed."""
    observed = type(exit_code) is int and type(peak_owned_rss) is int and type(live_owned_survivors) is int
    closed = (closure.get('source_group_closed') is True and closure.get('child_reaped') is True and not closure.get('failures') and live_owned_survivors == 0)
    expired = isinstance(elapsed_seconds, (int, float)) and elapsed_seconds >= deadline_seconds
    return dict(exit_code=exit_code if type(exit_code) is int else None, peak_owned_rss=peak_owned_rss if type(peak_owned_rss) is int else None,
                elapsed_seconds=elapsed_seconds, cleanup='CLOSED' if (observed and closed) else 'UNKNOWN' if not observed else 'FAILED',
                live_owned_survivors=live_owned_survivors if type(live_owned_survivors) is int else None, expired=expired,
                limit_hit='OUTER_DEADLINE' if expired else None, deadline_seconds=deadline_seconds, evidence=EVIDENCE)


def outer_from_slot_receipt(receipt, source_audit):
    """The outer object of a published slot receipt, bound to the source audit it describes. A receipt without one (every historical receipt), for a different source, or whose
    object is not exactly this module's shape is refused: there is no fallback and nothing is synthesised."""
    from verification.ingestion_storage.operational_publication import canonical      # the release's own serialiser: the slot receipt's source_sha256 is its hash
    raw = canonical(source_audit)
    owned = receipt.get('owned_cleanup') if isinstance(receipt, dict) else None
    outer = owned.get('outer_supervisor') if isinstance(owned, dict) else None
    if (not isinstance(outer, dict) or set(outer) != set(KEYS) or outer.get('evidence') != EVIDENCE
            or receipt.get('source_sha256') != hashlib.sha256(raw).hexdigest()):
        raise ValueError('OUTER_EVIDENCE_ABSENT_OR_UNBOUND')
    return dict(outer)
