"""Buyer Profiles V1 - the shared "active buyer" selector, reused by both
the Dashboard and the Opportunity Profile page rather than each page
inventing its own selection state (the same pattern app.ui.shortlist
already establishes for the session-only Shortlist selection). Session-
only, exactly like Shortlist - no production write, no per-user
persistence beyond the current browser session.
"""
from __future__ import annotations

import streamlit as st

from app.policy.buyer_profiles import BUYER_PROFILE_ORDER, BUYER_PROFILES

ACTIVE_BUYER_SESSION_KEY = "active_buyer_key"
GENERIC_OPTION_LABEL = "Generic / No buyer"


def active_buyer_key() -> str | None:
    """The currently-selected buyer's key, or None for generic mode -
    never queries anything itself, a plain session_state read."""
    return st.session_state.get(ACTIVE_BUYER_SESSION_KEY)


def buyer_selector(*, key: str) -> str | None:
    """Renders the "Viewing opportunities for: [ ... ]" selector and
    returns the active buyer key (None for generic). Deliberately a single
    shared component - the same three pilot profiles, the same generic
    option, wherever this is rendered."""
    labels = [GENERIC_OPTION_LABEL] + [BUYER_PROFILES[k].display_name for k in BUYER_PROFILE_ORDER]
    current = st.session_state.get(ACTIVE_BUYER_SESSION_KEY)
    current_label = BUYER_PROFILES[current].display_name if current in BUYER_PROFILES else GENERIC_OPTION_LABEL
    chosen_label = st.selectbox(
        "Viewing opportunities for", labels, index=labels.index(current_label), key=f"buyer-selector-{key}",
    )
    if chosen_label == GENERIC_OPTION_LABEL:
        st.session_state[ACTIVE_BUYER_SESSION_KEY] = None
        return None
    chosen_key = next(k for k in BUYER_PROFILE_ORDER if BUYER_PROFILES[k].display_name == chosen_label)
    st.session_state[ACTIVE_BUYER_SESSION_KEY] = chosen_key
    return chosen_key
