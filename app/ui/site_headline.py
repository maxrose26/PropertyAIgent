"""Builds compact, presentation-ready "headline" information for a Site -
used by the map hover tooltip (Sprint 3A, "Map Navigation and Site UX") and
reusable anywhere else a short Site summary is needed (search results,
future dashboards). Kept separate from tooltip-string formatting
(format_site_tooltip) and from Streamlit itself, so both halves are
testable independently of rendering - the same pattern app.policy.site_view
already established for the Site Profile's Policy Intelligence section.

Neither function here queries the database. build_site_headline takes
already-computed aggregation results (merged scheme fields, lapse/build
status, decision status, an optional Local Plan allocation summary), so
building a headline for many Sites at once costs zero additional queries
per Site - see app.ui.common.load_applications_for_sites for the batched
fetch this is meant to be paired with, and CLAUDE.md's "keep business logic
out of the UI" principle for why this lives outside app.ui.streamlit_app.
"""
from __future__ import annotations

import re

from app.pipeline.lapse_tracking import BUILD_STATUS_LABELS, DECISION_STATUS_LABELS

# Fields the map tooltip - and any future compact Site summary - are
# allowed to show, in display order. Kept as an explicit tuple so a test
# can assert the headline never grows an untracked field silently.
HEADLINE_FIELDS = (
    "site_id", "address", "council", "total_units", "units_estimated",
    "affordable_units", "affordable_percentage", "decision_status_label",
    "developer", "build_status_label", "local_plan_status",
)


def build_site_headline(
    *,
    site_id: int,
    address: str | None,
    council_label: str | None,
    merged: dict,
    lapse: dict,
    decision_status: str | None,
    local_plan_status: str | None = None,
) -> dict:
    """Pure - shapes already-computed values into a stable headline dict.
    Every field is either a real value or None - never a placeholder string
    like "None"/"N/A"/"Unknown" for something genuinely unknown - so a
    formatter can cleanly decide what to omit (Part 2: "do not show empty
    labels... omit rather than showing misleading defaults").

    merged: the dict returned by app.ui.common.aggregate_scheme_fields.
    lapse: the dict returned by app.pipeline.lapse_tracking.compute_lapse_status.
    decision_status: the key returned by
        app.pipeline.lapse_tracking.classify_decision_status (or None if
        there's no representative application to classify at all).
    local_plan_status: an already-formatted one-line summary (e.g.
        "Allocated (JPA7, adopted)"), or None if this Site isn't matched to
        any Local Plan allocation - callers build this string themselves
        (see app.ui.streamlit_app) since it depends on Policy Intelligence
        data this module has no business reaching into directly.
    """
    build_status = lapse.get("build_status")
    return {
        "site_id": site_id,
        "address": address or None,
        "council": council_label or None,
        "total_units": merged.get("total_units_final"),
        "units_estimated": bool(merged.get("total_units_is_estimated")),
        "affordable_units": merged.get("affordable_units_final"),
        "affordable_percentage": merged.get("affordable_percentage_final"),
        "decision_status_label": DECISION_STATUS_LABELS.get(decision_status) if decision_status else None,
        "developer": merged.get("developer") or merged.get("applicant_company") or None,
        # "unknown" carries no information over omitting the field entirely
        # (Part 2) - every other build_status value (including
        # "no_completions_yet", which reads as a real caveated fact, not a
        # blank) is kept.
        "build_status_label": BUILD_STATUS_LABELS.get(build_status) if build_status not in (None, "unknown") else None,
        "local_plan_status": local_plan_status or None,
    }


# Characters that could be misread as pydeck's own {ColumnName} template
# tokens, or that would break a single-line tooltip layout if they made it
# through from scraped/AI-extracted text (a stray newline in an address, a
# tab in a company name). Defensive, not a response to a proven
# vulnerability - the map tooltip is deliberately plain TEXT, not HTML (see
# module docstring / app.ui.streamlit_app), so there is no HTML/script
# injection surface here at all. This is the same "never trust scraped text
# verbatim" discipline the rest of the platform already applies, extended
# to a plain-text rendering context.
_UNSAFE_CHARS = re.compile(r"[{}\r\n\t]")


def clean_tooltip_text(value: str, max_length: int) -> str:
    """Public so any plain-text pydeck tooltip built elsewhere (e.g. the
    home page map's separate Local Plan allocation layer, which shares one
    global tooltip template with the Site layer - see
    app.ui.streamlit_app) can apply the same defensive cleanup without
    duplicating this regex."""
    cleaned = _UNSAFE_CHARS.sub(" ", value).strip()
    if len(cleaned) > max_length:
        cleaned = cleaned[: max_length - 1].rstrip() + "…"
    return cleaned


_clean_text = clean_tooltip_text  # short internal alias used below


def format_site_tooltip(headline: dict) -> str:
    """Turns a build_site_headline() dict into the actual pydeck tooltip
    text - one line per available field, nothing printed for a missing one.
    Domain values in, a ready-to-render string out; no aggregation logic
    lives here."""
    lines: list[str] = []

    if headline.get("address"):
        lines.append(_clean_text(headline["address"], max_length=70))
    if headline.get("council"):
        lines.append(_clean_text(headline["council"], max_length=50))

    if headline.get("total_units") is not None:
        n = headline["total_units"]
        text = f"{n} unit{'s' if n != 1 else ''}"
        if headline.get("units_estimated"):
            text += " (est.)"
        lines.append(text)

    if headline.get("affordable_units") is not None:
        pct = headline.get("affordable_percentage")
        pct_text = f" ({pct:.0f}%)" if pct is not None else ""
        lines.append(f"Affordable: {headline['affordable_units']}{pct_text}")

    if headline.get("developer"):
        lines.append(f"Developer: {_clean_text(headline['developer'], max_length=50)}")

    if headline.get("decision_status_label"):
        lines.append(f"Status: {headline['decision_status_label']}")

    if headline.get("build_status_label"):
        lines.append(f"Build: {headline['build_status_label']}")

    if headline.get("local_plan_status"):
        lines.append(f"Local Plan: {_clean_text(headline['local_plan_status'], max_length=60)}")

    lines.append("Click to open scheme details")
    return "\n".join(lines)
