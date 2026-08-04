"""Pure helpers for resolving which Site a map click, or a page's site_id
query parameter, refers to (Sprint 3A, "Map Navigation and Site UX",
Parts 3 & 4). Kept free of Streamlit/DB access so the selection logic
itself - distinct from rendering it - is directly unit-testable, per the
sprint's own guidance: "Where Streamlit UI interaction is difficult to
unit test, isolate and test the selection and formatting logic
separately."
"""
from __future__ import annotations


def resolve_selected_site_id(selected_objects: list[dict]) -> int | None:
    """Given the list of marker payloads pydeck's on_select event reports
    for the "sites" layer (see app.ui.streamlit_app's map_event handling),
    returns the site_id to navigate to, or None if nothing usable was
    selected. Always keys off site_id - never a name/address - so two
    Sites that happen to share a display name are never confused with each
    other (Part 3: "work for Sites with duplicate or similar names")."""
    if not selected_objects:
        return None
    raw = selected_objects[0].get("site_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def parse_site_id_param(raw: str | None) -> int | None:
    """Parses the site_id query parameter the same way
    app.ui.pages.1_Scheme_Detail needs to - extracted here so it's covered
    by a fast unit test rather than only ever exercised by a live browser
    session. Returns None for a missing or non-integer value; whether that
    id actually exists in the database is a separate check the caller
    still has to make (see app.db.models.Site)."""
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None
