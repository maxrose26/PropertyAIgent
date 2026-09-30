"""Bind Streamlit row offsets to the exact ordered result set that produced them."""
from numbers import Integral


def selection_widget_key(state, site_ids):
    identity = tuple(int(sid) for sid in site_ids)
    if state.get('_explore_result_identity') != identity:
        state['_explore_result_identity'] = identity
        state['_explore_selection_generation'] = state.get('_explore_selection_generation', 0) + 1
    return f"sites_table_{state['_explore_selection_generation']}"


def selected_site_ids(site_ids, rows):
    """Reject the entire malformed selection rather than silently select another row."""
    if not isinstance(rows, (list, tuple)):
        return []
    if any(isinstance(row, bool) or not isinstance(row, Integral) or row < 0 or row >= len(site_ids) for row in rows):
        return []
    return list(dict.fromkeys(int(site_ids[row]) for row in rows))
