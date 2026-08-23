"""Site Selection & Reporting V1 Gate 1 - pure shortlist helper functions.

Mirrors app.ui.allocation_selector's existing pattern: no Streamlit runtime
dependency, small, pure, independently unit-testable without a Streamlit
runtime. A page script owns the actual st.session_state dict (stored under
SHORTLIST_SESSION_KEY) and passes it into these functions; each function
returns a new dict for the caller to store back into st.session_state -
never mutated in place, so a caller can't accidentally rely on aliasing.

The shortlist stores identity only (ReportCandidate: candidate_type,
candidate_id, display_name) - never a snapshot of planning data. Current
trusted data must always be reloaded from the database when rendering the
shortlist or a report; display_name exists purely so the shortlist can show
something before that reload happens, and is never treated as authoritative.

V1 only ever adds candidate_type="allocation" entries. Other values (e.g. a
future "planning_site") are supported by this shape without any change to
it - see specifications/011-allocation-shortlist-v1-gate-1.md.
"""
from __future__ import annotations

from dataclasses import dataclass

SHORTLIST_SESSION_KEY = "_shortlist"


@dataclass(frozen=True)
class ReportCandidate:
    candidate_type: str
    candidate_id: int
    display_name: str


def _key(candidate_type: str, candidate_id: int) -> tuple[str, int]:
    return (candidate_type, candidate_id)


def add_candidate(state: dict[tuple[str, int], ReportCandidate], candidate: ReportCandidate) -> dict:
    """Adding an already-shortlisted candidate again overwrites the same
    dict key with an equal value - a structural no-op, not something a
    caller has to check for first. The (candidate_type, candidate_id) key
    means a numeric id colliding across two different candidate types
    (e.g. allocation 5 and, one day, planning_site 5) can never collide
    with each other."""
    state = dict(state)
    state[_key(candidate.candidate_type, candidate.candidate_id)] = candidate
    return state


def remove_candidate(state: dict[tuple[str, int], ReportCandidate], candidate_type: str, candidate_id: int) -> dict:
    state = dict(state)
    state.pop(_key(candidate_type, candidate_id), None)
    return state


def clear_shortlist(state: dict[tuple[str, int], ReportCandidate]) -> dict:
    return {}


def is_shortlisted(state: dict[tuple[str, int], ReportCandidate], candidate_type: str, candidate_id: int) -> bool:
    return _key(candidate_type, candidate_id) in state


def shortlist_items(
    state: dict[tuple[str, int], ReportCandidate], candidate_type: str | None = None,
) -> list[ReportCandidate]:
    """Insertion order is not guaranteed (plain dict values()) - callers
    that need a stable display order (e.g. the review page) sort by
    whatever field makes sense for them, the same way sort_allocations
    already does in app.ui.allocation_selector, rather than this module
    inventing its own ordering opinion."""
    items = list(state.values())
    if candidate_type is not None:
        items = [c for c in items if c.candidate_type == candidate_type]
    return items


def shortlist_count(state: dict[tuple[str, int], ReportCandidate], candidate_type: str | None = None) -> int:
    return len(shortlist_items(state, candidate_type))
