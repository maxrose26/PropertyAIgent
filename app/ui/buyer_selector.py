"""Buyer Profiles V1 - the shared "active buyer" selector, reused by both
the Dashboard and the Opportunity Profile page rather than each page
inventing its own selection state (the same pattern app.ui.shortlist
already establishes for the session-only Shortlist selection). The
SELECTION itself remains session-only, exactly like Shortlist - no
production write, no per-user persistence beyond the current browser
session (Gate 1's own brief: "No new workspace selector. No
authentication. No account UI.").

Gate 1 (Acquisition Monitoring Substrate) amendment: the list of AVAILABLE
buyer options now comes from app.policy.buyer_profile_store.
list_active_buyer_options - persisted, Workspace-owned BuyerProfile rows
once scripts.bootstrap_acquisition_monitoring has run, falling back to the
same four in-memory pilot templates (in the same order) otherwise, so this
selector's own visible behaviour is unchanged in every environment,
bootstrapped or not.
"""
from __future__ import annotations

import streamlit as st

from app.policy.buyer_profile_store import list_active_buyer_options

ACTIVE_BUYER_SESSION_KEY = "active_buyer_key"
GENERIC_OPTION_LABEL = "Generic / No buyer"


def active_buyer_key() -> str | None:
    """The currently-selected buyer's key, or None for generic mode -
    never queries anything itself, a plain session_state read."""
    return st.session_state.get(ACTIVE_BUYER_SESSION_KEY)


def buyer_selector(*, key: str, session) -> str | None:
    """Renders the "Viewing opportunities for: [ ... ]" selector and
    returns the active buyer key (None for generic). Deliberately a single
    shared component - the same pilot profiles, the same generic option,
    wherever this is rendered. `session` is required from Gate 1 onward
    (list_active_buyer_options reads persisted Buyer Profiles) - every
    caller already has a DB session in scope from app.ui.common.get_db()."""
    options = list_active_buyer_options(session)
    labels = [GENERIC_OPTION_LABEL] + [display_name for _, display_name in options]
    label_by_key = dict(options)
    current = st.session_state.get(ACTIVE_BUYER_SESSION_KEY)
    current_label = label_by_key.get(current, GENERIC_OPTION_LABEL)
    chosen_label = st.selectbox(
        "Viewing opportunities for", labels, index=labels.index(current_label), key=f"buyer-selector-{key}",
    )
    if chosen_label == GENERIC_OPTION_LABEL:
        st.session_state[ACTIVE_BUYER_SESSION_KEY] = None
        return None
    chosen_key = next(k for k, display_name in options if display_name == chosen_label)
    st.session_state[ACTIVE_BUYER_SESSION_KEY] = chosen_key
    return chosen_key
