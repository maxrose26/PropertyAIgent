"""Shared application shell — branding, global styling, and the reusable
presentation components (cards, badges, alerts, empty states, footer)
specified in docs/UI_DESIGN_SYSTEM.md.

This module is presentation-only by design (Sprint 4.1, "Application
Shell, Branding & Design System") - it never queries the database, never
touches business logic, and every dynamic value passed into a component
here is rendered through Streamlit's own escaping (st.markdown without
unsafe_allow_html, st.write, st.badge's own label handling) except the
handful of small, entirely static CSS/HTML snippets below, which never
interpolate caller-supplied text into raw HTML - the same discipline
already established in app.ui.common (see render_visual_evidence's own
docstring). Component call sites choose WHERE to render something;
this module never decides WHAT is true.
"""
from __future__ import annotations

import datetime as dt
import os

import streamlit as st

PRODUCT_NAME = "PropertyAIgent"
APP_VERSION = "0.4.2"
APP_ENVIRONMENT = os.getenv("PROPERTYAIGENT_ENV", "development")

# One definition, used everywhere a status/evidence/review/AI signal is
# shown (docs/UI_DESIGN_SYSTEM.md's "Icons" table) - never re-invented
# per call site.
_BADGE_KIND_STYLE = {
    "confirmed": {"color": "green", "icon": "✅", "label": "Confirmed"},
    "success": {"color": "green", "icon": "✅", "label": "Success"},
    "review": {"color": "orange", "icon": "⚠", "label": "Needs review"},
    "pending": {"color": "gray", "icon": "🕗", "label": "Pending"},
    "new_evidence": {"color": "blue", "icon": "🆕", "label": "New evidence"},
    "rejected": {"color": "red", "icon": "🚫", "label": "Rejected"},
    "error": {"color": "red", "icon": "🚫", "label": "Error"},
    "ai": {"color": "violet", "icon": "🤖", "label": "AI-generated"},
    "info": {"color": "blue", "icon": "ℹ", "label": "Info"},
}

# Alert kinds native Streamlit already renders well - never reimplemented.
_NATIVE_ALERT_KINDS = {"info", "success", "warning", "error"}

# Alert kinds this platform needs that Streamlit has no built-in for
# (docs/UI_DESIGN_SYSTEM.md's "Alert Styling" / Part 7 of this sprint) -
# each maps to a left-border accent colour on a bordered container, kept
# visually consistent with the badge palette above.
_CUSTOM_ALERT_STYLE = {
    "review": {"color": "#B7791F", "icon": "⚠", "label": "Review required"},
    "ai": {"color": "#6B4FA0", "icon": "🤖", "label": "AI-generated"},
    "evidence_missing": {"color": "#3B5773", "icon": "📄", "label": "Evidence missing"},
}


def inject_global_styles() -> None:
    """Called once, from the app entrypoint only. A static CSS string with
    no interpolated dynamic content - safe to render with
    unsafe_allow_html=True (see module docstring). Targets only stable,
    Streamlit-documented testids/semantic tags, never internal class names
    that could change between Streamlit releases."""
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1200px;
        }
        h1 { font-weight: 700; letter-spacing: -0.01em; }
        h2 { font-weight: 600; margin-top: 1.75rem; }
        h3 { font-weight: 600; }
        [data-testid="stSidebar"] .block-container { padding-top: 1.5rem; }
        [data-testid="stMetricValue"] { font-weight: 700; }
        .pig-page-subtitle { color: #5B6B7C; margin-top: -0.5rem; margin-bottom: 1rem; }
        .pig-footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #E4E8EC;
                      color: #8A97A3; font-size: 0.85rem; }
        .pig-empty-state { text-align: center; padding: 2.5rem 1.5rem; }
        .pig-empty-state-icon { font-size: 2.5rem; margin-bottom: 0.5rem; }

        /* Live Intelligence Leaderboard (Sprint 4.2 amendment) */
        .pig-live-dot {
            display: inline-block; width: 8px; height: 8px; border-radius: 50%;
            background-color: #D0342C; margin-right: 5px; vertical-align: middle;
            animation: pig-pulse 2s ease-in-out infinite;
        }
        @keyframes pig-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
        .pig-live-label { font-weight: 600; font-size: 0.85rem; color: #5B6B7C;
                           letter-spacing: 0.03em; text-transform: uppercase; }
        /* ARIA role/state selectors, not internal class names - stable
           across Streamlit versions since they're accessibility semantics,
           not implementation detail. */
        [data-testid="stTabs"] button[role="tab"] {
            border-radius: 999px; padding: 0.3rem 1rem; margin-right: 0.25rem;
            transition: background-color 0.15s ease;
        }
        [data-testid="stTabs"] button[aria-selected="true"] {
            background-color: rgba(31, 58, 95, 0.1); font-weight: 600;
        }
        /* Best-effort: animates Streamlit's own tab-underline element if
           present in the installed version; a harmless no-op otherwise. */
        [data-testid="stTabs"] [data-baseweb="tab-highlight"] {
            transition: left 0.25s ease, width 0.25s ease;
        }
        .pig-rank { font-weight: 700; color: #8A97A3; font-size: 1rem; }
        .pig-leaderboard-time { color: #8A97A3; font-size: 0.85rem; text-align: right; }
        [class*="st-key-lb-row-"] {
            border-radius: 6px; padding: 0.25rem 0.4rem; margin: 0 -0.4rem;
            transition: background-color 0.12s ease;
        }
        [class*="st-key-lb-row-"]:hover { background-color: #F4F6F8; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str | None = None, *, icon: str | None = None) -> None:
    """Standard page heading (Part 2, "standard page headings") - replaces
    the ad hoc st.title()/st.caption() pairs previously repeated per page."""
    st.title(f"{icon} {title}" if icon else title)
    if subtitle:
        st.markdown(f'<p class="pig-page-subtitle">{_escape(subtitle)}</p>', unsafe_allow_html=True)


def section_header(title: str, *, icon: str | None = None) -> None:
    """Standard subsection heading, consistent spacing above every named
    section of a page (docs/UI_DESIGN_SYSTEM.md's Typography rules)."""
    st.header(f"{icon} {title}" if icon else title)


def metric_card(label: str, value, *, help: str | None = None) -> None:
    """A single Stat Tile (docs/UI_DESIGN_SYSTEM.md's "Cards" section) -
    st.container(border=True) wrapping a native st.metric, never a
    hand-rolled HTML box, so it inherits Streamlit's own theming/
    accessibility for free."""
    with st.container(border=True):
        st.metric(label, value if value not in (None, "") else "—", help=help)


def metric_row(items: list[tuple[str, object, str | None]]) -> None:
    """A row of Stat Tiles - items is a list of (label, value, help)."""
    cols = st.columns(len(items))
    for col, (label, value, help_text) in zip(cols, items):
        with col:
            metric_card(label, value, help=help_text)


def status_badge(kind: str, label: str | None = None, *, help: str | None = None) -> None:
    """A Status Badge (docs/UI_DESIGN_SYSTEM.md) - kind is one of
    _BADGE_KIND_STYLE's keys. label overrides the default text for that
    kind (e.g. a specific decision status) while keeping its colour/icon."""
    style = _BADGE_KIND_STYLE.get(kind, _BADGE_KIND_STYLE["info"])
    st.badge(label or style["label"], icon=style["icon"], color=style["color"], help=help)


def evidence_badge(source_label: str, *, help: str | None = None) -> None:
    """An Evidence Badge - always adjacent to the fact it supports, never
    hidden in a separate expander (docs/UI_DESIGN_SYSTEM.md)."""
    st.badge(source_label, icon="📄", color="blue", help=help)


def review_badge(confidence: float | None = None, *, confirmed: bool = False) -> None:
    """A Review Badge - confirmed facts show a plain confirmed badge;
    AI-derived/unconfirmed facts always show their confidence alongside
    the "needs review" signal (docs/UI_DESIGN_SYSTEM.md's Review Badges -
    "never shown for a deterministically-derived fact")."""
    if confirmed:
        status_badge("confirmed", "Confirmed by a human reviewer")
        return
    label = f"Needs review · {confidence:.0%} confidence" if confidence is not None else "Needs review"
    status_badge("review", label)


def ai_badge() -> None:
    """Marks AI-generated content specifically - never used for a
    deterministic fact (docs/UI_DESIGN_SYSTEM.md's Icons table)."""
    status_badge("ai", "AI-generated")


def render_alert(kind: str, message: str, *, title: str | None = None, key: str | None = None) -> None:
    """One consistent alert style across Information / Success / Warning /
    Review Required / AI-generated / Evidence Missing (Part 7). The four
    native kinds reuse Streamlit's own alert boxes unchanged; the three
    kinds Streamlit has no equivalent for get a bordered-card treatment
    with a matching accent colour, built from a static per-kind style
    dict - message/title are rendered via st.markdown/st.write (never
    unsafe_allow_html), so caller-supplied text is always safely escaped
    regardless of its source (see module docstring)."""
    if kind in _NATIVE_ALERT_KINDS:
        getattr(st, kind)(f"**{title}**  \n{message}" if title else message)
        return

    style = _CUSTOM_ALERT_STYLE.get(kind)
    if style is None:
        st.info(message)
        return

    container_key = key or f"alert-{kind}-{abs(hash(title or message)) % 100000}"
    with st.container(border=True, key=container_key):
        st.markdown(f"{style['icon']} **{title or style['label']}**")
        st.write(message)
    st.markdown(
        f'<style>.st-key-{container_key} {{ border-left: 4px solid {style["color"]} !important; }}</style>',
        unsafe_allow_html=True,
    )


def ai_summary_card(
    text: str, *, generated_at: str | None = None, model: str | None = None,
    prompt_version: str | None = None, key: str | None = None,
) -> None:
    """The AI-Generated Content treatment (docs/UI_DESIGN_SYSTEM.md) - a
    purple-accented card, always carrying its generation timestamp/model
    (never presented as an unattributed claim), for any narrative content
    synthesised from this platform's own verified evidence."""
    container_key = key or "ai-summary-card"
    with st.container(border=True, key=container_key):
        st.markdown("🤖 **AI Summary**")
        st.write(text)
        meta_bits = [b for b in (
            f"Generated {generated_at}" if generated_at else None,
            model,
            f"prompt {prompt_version}" if prompt_version else None,
        ) if b]
        if meta_bits:
            st.caption(" · ".join(meta_bits) + " — built from evidence already verified by this platform.")
    st.markdown(
        f'<style>.st-key-{container_key} {{ border-left: 4px solid {_CUSTOM_ALERT_STYLE["ai"]["color"]} !important; }}</style>',
        unsafe_allow_html=True,
    )


def empty_state(
    title: str, message: str, *, icon: str = "🔍",
    cta_label: str | None = None, cta_page: str | None = None,
    show_home_link: bool = True,
) -> None:
    """A meaningful empty state (Part 6) - always explains what's needed
    and always offers a real way forward, never a bare sentence with no
    next step. cta_page, when given, is a path passed straight to
    st.page_link (e.g. "pages/0_Explore.py")."""
    with st.container(border=True):
        st.markdown(
            f'<div class="pig-empty-state"><div class="pig-empty-state-icon">{icon}</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"#### {title}")
        st.write(message)
        if cta_page and cta_label:
            st.page_link(cta_page, label=cta_label, icon="🔍")
        elif show_home_link:
            st.page_link("pages/0_Explore.py", label="Browse all sites in Explore", icon="🔍")


def quick_action_card(icon: str, title: str, description: str, *, page: str) -> None:
    """A live, clickable Quick Action (Part 8) - a bordered card whose
    entire purpose is the page_link beneath it. Used only for destinations
    that genuinely exist today - never for a future capability (see
    locked_card below for that)."""
    with st.container(border=True):
        st.markdown(f"**{icon} {title}**")
        st.caption(description)
        st.page_link(page, label="Open →")


def locked_card(icon: str, title: str, note: str = "Coming soon") -> None:
    """A visually locked placeholder for a future capability (Part 8's
    "future pages should appear visually locked") - deliberately
    non-interactive (no page_link, no button) so a user can never click
    through to something that doesn't exist yet, per this platform's
    "never expose unfinished functionality" discipline."""
    with st.container(border=True):
        st.markdown(f"**🔒 {icon} {title}**")
        st.caption(note)


def _leaderboard_row(rank: int, row: dict, *, key: str) -> None:
    """One ranked row - number, title (linked where a real destination
    exists, plain text otherwise so a row is never a dead click), an
    optional compact badge, and a right-aligned relative timestamp. The
    container's key is prefixed "lb-row-" so inject_global_styles's single
    shared hover rule (a substring attribute selector) covers every row on
    the page without one style tag per row."""
    with st.container(key=f"lb-row-{key}"):
        col_rank, col_main, col_time = st.columns([1, 7, 3], vertical_alignment="center")
        with col_rank:
            st.markdown(f'<span class="pig-rank">{rank:02d}</span>', unsafe_allow_html=True)
        with col_main:
            if row.get("page"):
                st.page_link(row["page"], label=row["title"], query_params=row.get("params") or {})
            else:
                st.markdown(f"**{_escape(row['title'])}**")
            bits = [b for b in (row.get("subtitle"), row.get("badge")) if b]
            if bits:
                st.caption(" · ".join(bits))
        with col_time:
            st.markdown(f'<div class="pig-leaderboard-time">{relative_time(row.get("when"))}</div>', unsafe_allow_html=True)


def live_leaderboard(tabs: dict[str, list[dict]], *, key: str) -> None:
    """The Live Intelligence Leaderboard (Sprint 4.2 amendment) - one
    reusable, tabbed component surfacing the platform's most recent
    cross-cutting activity, ranked by recency. tabs is
    app.reporting.dashboard.build_leaderboard's own output - a tab absent
    from that dict has no supporting data and is never rendered here
    (never an empty tab created just to match a fixed design), per that
    module's own docstring. Selecting a tab is Streamlit's own native
    st.tabs behaviour - content is replaced in place, no extra state
    management needed."""
    if not tabs:
        st.caption("No live activity to show yet.")
        return

    st.markdown('<span class="pig-live-dot"></span><span class="pig-live-label">Live</span>', unsafe_allow_html=True)
    tab_labels = list(tabs.keys())
    rendered_tabs = st.tabs(tab_labels)
    for rendered_tab, label in zip(rendered_tabs, tab_labels):
        with rendered_tab:
            rows = tabs[label]
            if not rows:
                st.caption("Nothing here right now.")
                continue
            for i, row in enumerate(rows, start=1):
                _leaderboard_row(i, row, key=f"{key}-{label}-{row['id']}")


def render_footer() -> None:
    """A lightweight footer (Part 8) - product name, version, environment
    only, no clutter."""
    env_bit = f" · {APP_ENVIRONMENT}" if APP_ENVIRONMENT != "production" else ""
    st.markdown(
        f'<div class="pig-footer">{PRODUCT_NAME} · v{APP_VERSION}{env_bit}</div>',
        unsafe_allow_html=True,
    )


def relative_time(value: dt.datetime | None) -> str:
    """A small, purely presentational "n minutes/hours/days ago" formatter -
    no timezone assumptions beyond normalising to naive-for-subtraction
    (the same defensive handling app.reporting.dashboard's own merge/sort
    needs, since not every timestamp column round-trips through SQLite
    with the same tzinfo state). Returns "unknown" rather than guessing
    when there's genuinely no timestamp - never fabricated."""
    if value is None:
        return "unknown"
    now = dt.datetime.now(dt.timezone.utc) if value.tzinfo else dt.datetime.now()
    delta = now - value
    seconds = delta.total_seconds()
    if seconds < 0:
        return value.strftime("%d %b %Y")
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    if seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    if seconds < 86400 * 14:
        days = int(seconds // 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"
    return value.strftime("%d %b %Y")


def _escape(text: str) -> str:
    """Minimal HTML-escaping for the handful of small static-template
    snippets above that interpolate a caller-supplied string directly into
    an HTML attribute-free text node (never used for anything rendered as
    markup itself)."""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;").replace("'", "&#39;")
    )
