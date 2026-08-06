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
from contextlib import contextmanager

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
        [class*="st-key-lb-row-"], [class*="st-key-act-row-"] {
            border-radius: 6px; padding: 0.25rem 0.4rem; margin: 0 -0.4rem;
            transition: background-color 0.12s ease;
        }
        [class*="st-key-lb-row-"]:hover, [class*="st-key-act-row-"]:hover { background-color: #F4F6F8; }

        /* Dashboard hierarchy revision */
        [class*="st-key-policy-section"] { background-color: #F3F6FA; border-color: #D7E1EC !important; }
        [class*="st-key-opp-card-"] { border-width: 1.5px !important; }
        [class*="st-key-opp-card-"]:hover { border-color: #1F3A5F !important; }
        .pig-opportunity-dot {
            display: inline-block; width: 6px; height: 6px; border-radius: 50%;
            background-color: #1F3A5F; margin-right: 5px; vertical-align: middle;
            animation: pig-pulse 2.4s ease-in-out infinite;
        }
        @media (prefers-reduced-motion: reduce) {
            .pig-live-dot, .pig-opportunity-dot { animation: none; opacity: 1; }
        }
        .pig-carousel-dots { text-align: center; margin-top: 0.5rem; letter-spacing: 3px; color: #C3CBD4; }
        .pig-carousel-dots .pig-dot-active { color: #1F3A5F; }

        /* Dashboard refinement - scheme stack (layered/stacked cards) */
        [class*="st-key-scheme-card-"] {
            margin-top: -6px; transition: transform 0.12s ease, box-shadow 0.12s ease;
        }
        [class*="st-key-scheme-card-"]:first-child { margin-top: 0; }
        [class*="st-key-scheme-card-"]:hover {
            transform: translateY(-2px); box-shadow: 0 4px 10px rgba(31, 58, 95, 0.12); border-color: #1F3A5F !important;
        }
        .pig-scheme-rank {
            display: inline-block; min-width: 1.6rem; font-weight: 700; color: #8A97A3; font-size: 0.9rem;
        }
        .pig-scheme-why { color: #6B4FA0; font-size: 0.82rem; }

        /* Dashboard refinement - opportunity category sections */
        [class*="st-key-opp-cat-card-"] { transition: border-color 0.12s ease; }
        [class*="st-key-opp-cat-card-"]:hover { border-color: #1F3A5F !important; }

        /* Dashboard refinement - right-hand AI summary rail: a purely
           CSS-driven "live" highlight that steps down the rail over time -
           no JS timer, no st.rerun(), so it never disrupts interaction
           elsewhere on the page. Each card's animation-delay is set inline
           per-card (a small, static, developer-controlled offset - not
           caller-supplied text) so the highlight visits one card at a time. */
        @keyframes pig-rail-pulse {
            0%, 88%, 100% { border-left-color: #E4E8EC; background-color: transparent; }
            4% { border-left-color: #6B4FA0; background-color: rgba(107, 79, 160, 0.05); }
        }
        [class*="st-key-rail-card-"] {
            border-left: 4px solid #E4E8EC !important;
            animation: pig-rail-pulse var(--pig-rail-cycle, 40s) ease-in-out infinite;
        }
        @media (prefers-reduced-motion: reduce) {
            [class*="st-key-rail-card-"] { animation: none; border-left-color: #E4E8EC !important; }
        }

        /* Council Intelligence overview refinement - responsive card grid.
           Scoped to the "council-grid" container key only used on
           pages/5_Council_Intelligence.py, so no other page's st.columns
           layout is affected. Python still declares a fixed 3-per-row
           chunk size; CSS Grid's auto-fit/minmax reflows that into
           however many 320px+ cards actually fit the AVAILABLE content
           width (viewport minus the sidebar, whichever way the user has
           it) - 3 on a large desktop, 2 on a standard laptop, 1 on
           mobile, self-adjusting rather than guessing from viewport-width
           breakpoints alone (a fixed-pixel media query on window width
           was tried first and produced inconsistent 2-3-per-row results,
           since the sidebar's own width isn't part of that number).
           The selector chain below (">" direct-child combinators,
           matching Streamlit's actual DOM: council-grid's own
           stVerticalBlock > stLayoutWrapper > stHorizontalBlock > stColumn)
           deliberately targets ONLY that top-level row, never the nested
           stHorizontalBlock/stColumn pairs each card renders internally
           for its own 2x2 metric-tile grid - a plain descendant selector
           here would also catch those nested columns and force them into
           the same grid, breaking every card's internal layout. */
        [data-testid="stVerticalBlock"][class*="st-key-council-grid"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {
            display: grid !important;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 1.25rem;
        }
        [data-testid="stVerticalBlock"][class*="st-key-council-grid"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            width: 100% !important; min-width: 0;
        }

        /* Council Intelligence overview refinement - restrained,
           status-based card colour (Sprint 4.3a, Part 3): Adopted /
           Emerging / Regulation 18 / Examination / Withdrawn / no plan at
           all. Colour ALWAYS reflects the displayed plan's own status -
           joint-plan participation no longer overrides it (that's now a
           separate, neutral "Joint Plan" badge - see joint_plan_badge
           below); status is also always shown as text/a badge/chip on
           the card itself, colour is never the only signal. */
        [class*="st-key-cc-adopted-"] { background-color: #F1FAF4 !important; border-color: #BFE3C9 !important; }
        [class*="st-key-cc-emerging-"] { background-color: #F5F0FB !important; border-color: #D9C8ED !important; }
        [class*="st-key-cc-regulation-18-"] { background-color: #FBF3E3 !important; border-color: #ECD9A6 !important; }
        [class*="st-key-cc-examination-"] { background-color: #EFF5FC !important; border-color: #C9DCF0 !important; }
        [class*="st-key-cc-withdrawn-"] { background-color: #FBEEEE !important; border-color: #EFC3C3 !important; }
        [class*="st-key-cc-no-plan-"] { background-color: #F4F5F7 !important; border-color: #DEE2E7 !important; }
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


def ai_daily_brief_placeholder() -> None:
    """The AI Daily Brief (Dashboard hierarchy revision, Part 1) - deliberately
    still a placeholder (no combined-dashboard AI summary exists yet, and
    this component never calls an AI client or generates one), but styled
    to look like an intentional, restrained product surface rather than an
    afterthought: heading, an "Evidence-based briefing" badge, a concise
    explanation, and an explicit not-yet-generated state - the same purple
    AI accent as ai_summary_card, so it reads as the same design language
    once real content lands here."""
    container_key = "ai-daily-brief"
    with st.container(border=True, key=container_key):
        col_title, col_badge = st.columns([3, 2], vertical_alignment="center")
        with col_title:
            st.markdown("🤖 **AI Daily Brief**")
        with col_badge:
            st.badge("Evidence-based briefing", icon="📄", color="violet")
        st.write(
            "A short, plain-English summary of what changed across every council and Site this platform "
            "tracks - written only from evidence already verified elsewhere on this Dashboard, never invented."
        )
        st.caption("Not yet generated — daily briefing will become available once dashboard aggregation is implemented.")
    st.markdown(
        f'<style>.st-key-{container_key} {{ border-left: 4px solid {_CUSTOM_ALERT_STYLE["ai"]["color"]} !important; }}</style>',
        unsafe_allow_html=True,
    )


@contextmanager
def section_container(title: str, subtitle: str | None = None, *, icon: str | None = None, key: str):
    """A visually contained section (Dashboard hierarchy revision, Part 2) -
    a single outer bordered/tinted container so a group of related cards
    reads as one deliberate product component rather than loose content
    scattered down the page. Usage:

        with section_container("Policy Intelligence", "...", icon="📋", key="policy-section"):
            ...cards...

    The tint itself is applied via CSS scoped to this container's own
    st-key-derived class (see inject_global_styles's ".st-key-policy-
    section" rule) - callers don't choose a colour here, keeping every
    section's palette centrally defined in one place."""
    with st.container(border=True, key=key):
        st.markdown(f"#### {icon + ' ' if icon else ''}{title}")
        if subtitle:
            st.caption(subtitle)
        yield


def opportunity_card(card: dict, *, key: str) -> None:
    """A prominent Opportunity card (Dashboard hierarchy revision, Part 3) -
    a stronger border, a subtle pulsing status dot (never a flashing full
    card - reduced-motion respected via inject_global_styles's
    prefers-reduced-motion override), and a category badge that is always
    the real, deterministic signal the card came from, never an invented
    urgency score (see app.reporting.dashboard.build_opportunity_cards)."""
    container_key = f"opp-card-{key}"
    with st.container(border=True, key=container_key):
        st.markdown(
            f'<span class="pig-opportunity-dot"></span>**{_escape(card["title"])}**', unsafe_allow_html=True,
        )
        st.caption(f"{card['subtitle']} · {card['reason']}")
        col_metric, col_badge = st.columns([2, 2])
        with col_metric:
            st.markdown(f"**{_escape(str(card['metric']))}**")
        with col_badge:
            st.badge(card["badge"], color="blue")
        if card.get("page"):
            st.page_link(card["page"], label="View →", query_params=card.get("params") or {})


def _activity_group_row(row: dict, *, key: str) -> None:
    """One grouped Recent Activity row - icon, grouped label (already
    aggregated by app.reporting.dashboard.group_activity_events, e.g.
    "8 visual-evidence pages extracted from Stockport Local Plan"), and a
    right-aligned "most recent" timestamp. Presentation only - the grouping
    itself already happened at the data layer."""
    with st.container(key=f"act-row-{key}"):
        col_icon, col_main, col_time = st.columns([1, 7, 3], vertical_alignment="center")
        with col_icon:
            st.markdown(f"<div style='font-size:1.1rem'>{row['icon']}</div>", unsafe_allow_html=True)
        with col_main:
            if row.get("page"):
                st.page_link(row["page"], label=row["label"], query_params=row.get("params") or {})
            else:
                st.markdown(f"**{_escape(row['label'])}**")
        with col_time:
            st.markdown(
                f'<div class="pig-leaderboard-time">Most recent: {relative_time(row.get("latest_when"))}</div>',
                unsafe_allow_html=True,
            )


def activity_timeline(rows: list[dict], *, key: str, empty_message: str = "Nothing to show yet.") -> None:
    """The aggregated Recent Activity timeline (Dashboard hierarchy
    revision, Part 5) - rows is already-grouped output from
    app.reporting.dashboard.group_activity_events; this function only
    renders it."""
    if not rows:
        st.caption(empty_message)
        return
    for row in rows:
        _activity_group_row(row, key=f"{key}-{row['id']}")


def ai_summary_carousel(items: list[dict], *, key: str) -> None:
    """The Recent AI Summaries carousel (Dashboard hierarchy revision, Part
    6) - reads only already-persisted summaries (see
    app.reporting.dashboard.build_ai_summary_carousel_items), never
    generates one. Auto-advance is deliberately NOT implemented: a native
    Streamlit timer would require a sleep-triggered st.rerun() loop, which
    forces a full-page rerun and disrupts whatever the user is doing
    elsewhere on the page - exactly what this component must avoid. A
    stable, manually-controlled carousel (Previous/Next + position dots) is
    the documented, deliberate trade-off instead - see the Sprint 4.2
    hierarchy-revision completion report for the full explanation."""
    if not items:
        st.caption("No AI summaries generated yet.")
        return

    index_key = f"{key}-carousel-index"
    if index_key not in st.session_state:
        st.session_state[index_key] = 0
    # Clamp defensively - the underlying item count can shrink between
    # reruns (e.g. a different filtered dashboard load), and an out-of-range
    # index must never raise instead of just clamping back to the last item.
    st.session_state[index_key] = min(st.session_state[index_key], len(items) - 1)
    index = st.session_state[index_key]
    item = items[index]

    container_key = f"{key}-carousel-card"
    with st.container(border=True, key=container_key):
        col_type, col_badge = st.columns([3, 2], vertical_alignment="center")
        with col_type:
            st.markdown(f"**{_escape(item['type'])} — {_escape(item['name'])}**")
        with col_badge:
            st.badge(item["model"] or "AI", icon="🤖", color="violet")
        st.caption(item["council_code"])
        st.write(item["excerpt"])
        meta_bits = [b for b in (f"Generated {relative_time(item['generated_at'])}",) if b]
        st.caption(" · ".join(meta_bits) + " — built from evidence already verified by this platform.")
        if item.get("page"):
            st.page_link(item["page"], label="View source →", query_params=item.get("params") or {})

        if len(items) > 1:
            col_prev, col_dots, col_next = st.columns([1, 4, 1])
            with col_prev:
                if st.button("‹ Prev", key=f"{key}-carousel-prev", width="stretch"):
                    st.session_state[index_key] = (index - 1) % len(items)
                    st.rerun()
            with col_dots:
                dots = "".join(
                    f'<span class="{"pig-dot-active" if i == index else ""}">●</span> ' for i in range(len(items))
                )
                st.markdown(f'<div class="pig-carousel-dots">{dots}</div>', unsafe_allow_html=True)
            with col_next:
                if st.button("Next ›", key=f"{key}-carousel-next", width="stretch"):
                    st.session_state[index_key] = (index + 1) % len(items)
                    st.rerun()
    st.markdown(
        f'<style>.st-key-{container_key} {{ border-left: 4px solid {_CUSTOM_ALERT_STYLE["ai"]["color"]} !important; }}</style>',
        unsafe_allow_html=True,
    )


def quick_actions_panel(items: list[dict]) -> None:
    """The compact Quick Actions side panel (Dashboard hierarchy revision,
    Part 4) - a narrow vertical stack rather than the wide 5-card grid
    Sprint 4.2's first pass used, since this now lives in a ~25-30% side
    column alongside the main content instead of its own full-width row.
    items: [{"icon","title","description","page"|None (locked if absent)}]."""
    with st.container(border=True):
        st.markdown("**⚡ Quick Actions**")
        for item in items:
            st.divider()
            if item.get("page"):
                st.markdown(f"{item['icon']} **{item['title']}**")
                st.caption(item["description"])
                st.page_link(item["page"], label="Open →")
            else:
                st.markdown(f"🔒 {item['icon']} **{item['title']}**")
                st.caption(item.get("description", "Coming soon"))


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


def _scheme_stack_card(card: dict, *, rank: int, key: str) -> None:
    """One Planning Intelligence scheme card (Dashboard refinement, Part 3) -
    a layered/stacked look (negative margin-top + hover-lift, see
    inject_global_styles) rather than a plain leaderboard row. Every field
    is optional and simply omitted when absent - "do not show None/zero for
    missing facts" is enforced here, at render time, not upstream."""
    with st.container(border=True, key=f"scheme-card-{key}"):
        col_rank, col_main, col_time = st.columns([1, 7, 3], vertical_alignment="center")
        with col_rank:
            st.markdown(f'<span class="pig-scheme-rank">{rank:02d}</span>', unsafe_allow_html=True)
        with col_main:
            title = card.get("reference") or card.get("address") or "Scheme"
            if card.get("page"):
                st.page_link(card["page"], label=title, query_params=card.get("params") or {})
            else:
                st.markdown(f"**{_escape(title)}**")
            subtitle_bits = [b for b in (card.get("council_code"), card.get("address")) if b]
            if subtitle_bits and card.get("reference"):
                st.caption(" · ".join(_escape(str(b)) for b in subtitle_bits))
        with col_time:
            st.markdown(f'<div class="pig-leaderboard-time">{relative_time(card.get("when"))}</div>', unsafe_allow_html=True)

        badge_cols = st.columns(4)
        badge_fields = [
            ("total_units", lambda v: f"{v} units"),
            ("affordable_units", lambda v: f"{v} affordable"),
            ("affordable_percentage", lambda v: f"{v:.0f}% affordable"),
            ("decision_status", lambda v: v),
            ("build_status", lambda v: v),
            ("planning_status", lambda v: v),
        ]
        shown = [(field, fmt) for field, fmt in badge_fields if card.get(field) not in (None, "", 0)]
        for col, (field, fmt) in zip(badge_cols, shown[:4]):
            with col:
                st.caption(fmt(card[field]))

        if card.get("developer"):
            st.caption(f"Developer: {card['developer']}")
        if card.get("why"):
            st.markdown(f'<div class="pig-scheme-why">{_escape(card["why"])}</div>', unsafe_allow_html=True)


def scheme_stack(tabs: dict[str, list[dict]], *, key: str) -> None:
    """The Planning Intelligence scheme stack (Dashboard refinement, Parts 3
    & 4) - tabs is app.reporting.dashboard.build_scheme_stack's own output;
    a tab absent from that dict has no supporting data and is never
    rendered (never an empty tab invented to match a fixed design)."""
    if not tabs:
        st.caption("No live scheme activity to show yet.")
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
                _scheme_stack_card(row, rank=i, key=f"{key}-{label}-{row['id']}")


def opportunity_category_section(category: dict, *, key: str) -> None:
    """One Opportunities category (Dashboard refinement, Parts 5 & 6) -
    heading, a short explanation, a real count, and a grid of cards. Shows
    an honest empty/unavailable state rather than fabricating a card -
    category["available"] is False only for a category this platform
    genuinely cannot compute yet (none exist today, see
    app.reporting.dashboard.build_opportunity_categories)."""
    with st.container(border=True, key=f"opp-cat-{key}-{category['key']}"):
        col_heading, col_count = st.columns([5, 1], vertical_alignment="center")
        with col_heading:
            st.markdown(f"**{_escape(category['heading'])}**")
        with col_count:
            st.badge(str(category["count"]), color="blue")
        st.caption(category["explanation"])

        if not category["available"]:
            st.caption(f"Not yet available - {category['unavailable_reason']}")
            return
        if not category["cards"]:
            st.caption("Nothing in this category right now.")
            return

        cols = st.columns(2)
        for i, card in enumerate(category["cards"]):
            with cols[i % 2]:
                with st.container(border=True, key=f"opp-cat-card-{key}-{card['id']}"):
                    st.markdown(f"**{_escape(card['title'])}**")
                    st.caption(f"{card['subtitle']} · {card['reason']}")
                    st.markdown(f"**{_escape(str(card['metric']))}**")
                    if card.get("page"):
                        st.page_link(card["page"], label="View →", query_params=card.get("params") or {})


def ai_summary_rail(items: list[dict], *, key: str, cycle_seconds: int = 40) -> None:
    """The right-hand Recent AI Summaries rail (Dashboard refinement, Parts
    7-9) - a static vertical stack (every item visible at once, no
    Prev/Next state), with a purely CSS-driven highlight that steps from
    card to card via animation-delay (see inject_global_styles's
    pig-rail-pulse keyframe) - never a sleep()+st.rerun() loop, so this can
    never disrupt whatever else the user is doing on the page. Each item's
    relevance line comes from app.reporting.dashboard.build_ai_summary_rail
    - already a deterministic explanation grounded in real fields, never
    invented here."""
    if not items:
        st.caption("No AI summaries generated yet.")
        return

    st.markdown('<span class="pig-live-dot"></span><span class="pig-live-label">Live</span>', unsafe_allow_html=True)
    per_card_seconds = max(cycle_seconds, len(items) * 4) / len(items)
    for i, item in enumerate(items):
        container_key = f"rail-card-{key}-{item['id']}"
        with st.container(border=True, key=container_key):
            st.markdown(f"**{_escape(item['type'])}**")
            st.caption(_escape(item["name"]))
            st.write(item["excerpt"])
            st.caption(f"Why now: {item['relevance']}")
            meta_col, badge_col = st.columns([3, 2], vertical_alignment="center")
            with meta_col:
                st.caption(f"Generated {relative_time(item['generated_at'])}")
            with badge_col:
                st.badge(item["model"] or "AI", icon="🤖", color="violet")
            if item.get("page"):
                st.page_link(item["page"], label="View →", query_params=item.get("params") or {})
        total_cycle = per_card_seconds * len(items)
        st.markdown(
            f'<style>.st-key-{container_key} {{ '
            f'animation-delay: {i * per_card_seconds:.2f}s; '
            f'--pig-rail-cycle: {total_cycle:.2f}s; }}</style>',
            unsafe_allow_html=True,
        )


def wide_canvas(max_width: str = "94%") -> None:
    """A page-scoped override of inject_global_styles's own .block-container
    max-width (Dashboard layout correction) - Streamlit re-runs a page's
    entire script from scratch on navigation, so a page that calls this
    widens only ITS OWN render; every other page keeps the shared shell's
    default 1200px contained width untouched (deliberately not changed in
    inject_global_styles itself, per this task's "do not make every page
    edge-to-edge" instruction). Call once, early, from a page that
    genuinely benefits from more horizontal room - today, only the
    Dashboard, whose KPI strip, scheme stack and AI rail were all reading
    as cramped inside the shared shell's normal contained width."""
    st.markdown(
        f'<style>.block-container {{ max-width: {max_width} !important; }}</style>',
        unsafe_allow_html=True,
    )


def evidence_confidence_badge(trust: str, *, source_label: str | None = None) -> None:
    """Sprint 4.3 ("Council Intelligence") - the evidence-confidence signal
    Part 6 asks every housing-position figure to carry, built from
    app.policy.plan_evidence_view's own trust vocabulary ("confirmed" - a
    human approved it; "auto_applied" - the pipeline applied it
    automatically at high confidence, not yet independently reviewed;
    "pending" - a value is proposed but not yet trusted). Reuses the
    existing Status/Review/Evidence badge vocabulary rather than inventing
    a fourth badge kind - never shown at all for "missing" (nothing to
    have confidence about)."""
    if trust == "confirmed":
        review_badge(confirmed=True)
    elif trust == "auto_applied":
        status_badge("info", "Auto-extracted, not yet reviewed")
    elif trust == "pending":
        status_badge("pending", "Proposed, awaiting review")
    if source_label:
        evidence_badge(source_label)


def housing_stat_card(label: str, value, *, help: str | None = None, trust: str | None = None, source_label: str | None = None) -> None:
    """A Stat Tile (docs/UI_DESIGN_SYSTEM.md) extended with an inline
    evidence-confidence badge beneath the figure (Sprint 4.3, Part 6:
    "each value should display its evidence confidence") - metric_card
    itself stays untouched (still used everywhere a plain figure with no
    evidence-tracking is shown) since not every Stat Tile in the product
    has a trust state to display."""
    with st.container(border=True):
        st.metric(label, value if value not in (None, "") else "—", help=help)
        if trust is not None and value not in (None, ""):
            evidence_confidence_badge(trust, source_label=source_label)


def stat_tile(label: str, value: str, *, caption: str | None = None, help: str | None = None) -> None:
    """A wrapping, non-truncating Stat Tile (Sprint 4.3 refinement, Part 3 -
    "no headline value may appear as truncated text"). Unlike metric_card
    (built on st.metric, which single-lines and ellipsis-truncates long
    values at narrow column widths - the exact "9,48...", "Mon..." failure
    this refinement fixes), this wraps a long value onto a second line
    instead of cutting it off. Used for any headline figure that might run
    longer than a plain 3-4 digit number (e.g. "9,486 homes",
    "November 2027")."""
    with st.container(border=True):
        st.caption(label, help=help)
        st.markdown(
            f'<div style="font-size:1.35rem;font-weight:700;line-height:1.25;'
            f'overflow-wrap:break-word;">{_escape(str(value))}</div>',
            unsafe_allow_html=True,
        )
        if caption:
            st.caption(caption)


# Fixed, non-caller-controlled style per five-year-supply state (refinement
# Part 4) - safe to interpolate into a static CSS/HTML snippet since these
# three dicts are never built from user- or database-supplied text (see
# module docstring's "static CSS/HTML snippets" carve-out).
_SUPPLY_STATE_STYLE: dict[str, dict] = {
    "warning": {"color": "#B7431F", "icon": "⚠", "note": "Below five-year requirement"},
    "ok": {"color": "#1F7A4C", "icon": "✅", "note": None},
    "unverified": {"color": "#5B6B7C", "icon": "❔", "note": None},
}


def five_year_supply_tile(display: str, state: str, *, base_date: str | None = None) -> None:
    """The Five-Year Housing Supply headline tile (Sprint 4.3 refinement,
    Part 4) - a warning-accented tile below the five-year threshold, a
    plain positive tile at/above it, and an explicit "Not yet verified"
    tile (never a bare em dash) when this council has no trusted supply
    figure extracted yet. display/state are computed entirely by
    app.reporting.council_intelligence from real extracted evidence - this
    component only chooses how to present them, never infers or estimates
    a number itself."""
    style = _SUPPLY_STATE_STYLE.get(state, _SUPPLY_STATE_STYLE["unverified"])
    with st.container(border=True):
        st.caption("Five-year supply")
        st.markdown(
            f'<div style="font-size:1.35rem;font-weight:700;color:{style["color"]}">'
            f'{style["icon"]} {_escape(display)}</div>',
            unsafe_allow_html=True,
        )
        if style["note"]:
            st.caption(style["note"])
        elif base_date:
            st.caption(f"Base date {base_date}")


def planning_readiness_chip(chip: dict) -> None:
    """The Planning Readiness chip (Commercial Planning Readiness
    refinement, Part 2) - replaces the plain Adopted/Emerging badge with a
    finer-grained, colour-dotted label (e.g. "🟢 Adopted 2018" with a
    "7 years old" sub-line). chip is app.reporting.council_intelligence.
    _planning_readiness_chip's own output - this renders it, never
    computes or estimates any part of it itself."""
    st.markdown(f"**{chip['emoji']} {_escape(chip['label'])}**")
    if chip.get("sublabel"):
        st.caption(chip["sublabel"])


def joint_plan_badge() -> None:
    """A neutral "Joint Plan" badge (Sprint 4.3a, Part 3) - shown
    alongside the Planning Readiness chip whenever the card's displayed
    plan is NOT this council's own (app.reporting.council_intelligence's
    primary_plan_is_own), communicating that fact separately from the
    card's status colour/chip instead of overriding them - joint-plan
    participation and the plan's own status are two different pieces of
    information and must not replace one another."""
    st.badge("Joint Plan", icon="⬜", color="gray")


def planning_outlook_banner(outlook: dict) -> None:
    """The Planning Outlook banner (Sprint 4.3a, Part 1 - renamed from
    "Planning Health", reworded so it never reads as "more likely to get
    planning permission") - a short, deterministic classification (never
    AI-generated) computed by app.reporting.council_intelligence.
    _planning_outlook from evidence already stored; renders it as a single
    compact line, coloured by the SAME emoji already carried in outlook
    (never a separate colour decision)."""
    st.markdown(f"{outlook['emoji']} **{_escape(outlook['label'])}**")


def why_it_matters_line(text: str) -> None:
    """"Why it matters" (Sprint 4.3a, Part 2) - a short, deterministic
    (never AI-generated) sentence directly beneath the Planning Outlook
    banner, explaining what that outlook means in plain English. text is
    app.reporting.council_intelligence._why_it_matters's own output -
    this only renders it."""
    st.caption(text)


def timeline(entries: list[dict], *, key: str, empty_message: str = "Nothing to show yet.") -> None:
    """A generic activity timeline (Sprint 4.3, Part 10/Part 12) - icon,
    label, right-aligned relative time. Distinct from Dashboard's own
    activity_timeline (which renders already-GROUPED, count-bearing rows
    from app.reporting.dashboard specifically) - this is the plain,
    ungrouped chronological form any page can reuse, e.g. entries: [{"icon",
    "label", "when"}, ...]."""
    if not entries:
        st.caption(empty_message)
        return
    for i, entry in enumerate(entries):
        with st.container(key=f"{key}-timeline-{i}"):
            col_icon, col_main, col_time = st.columns([1, 7, 3], vertical_alignment="center")
            with col_icon:
                st.markdown(f"<div style='font-size:1.1rem'>{entry['icon']}</div>", unsafe_allow_html=True)
            with col_main:
                st.markdown(f"**{_escape(entry['label'])}**")
            with col_time:
                st.markdown(
                    f'<div class="pig-leaderboard-time">{relative_time(entry.get("when"))}</div>',
                    unsafe_allow_html=True,
                )
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
