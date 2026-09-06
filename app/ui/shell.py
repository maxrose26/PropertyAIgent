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
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import streamlit as st

PRODUCT_NAME = "PropertyAIgent"
APP_VERSION = "0.4.5"
APP_ENVIRONMENT = os.getenv("PROPERTYAIGENT_ENV", "development")


def _detect_commit_hash() -> str | None:
    """Live Deployment Integrity audit (Part 2) - APP_VERSION above is a
    hand-maintained string that in practice hasn't been bumped across three
    merged sprints, so it can't tell a stale deployment apart from a current
    one (both show "0.4.2"). A short commit hash can. Render sets
    RENDER_GIT_COMMIT on every service automatically - checked first so
    this never shells out in the deployed environment. The `git`
    fallback is for local dev, where no such env var exists; it's wrapped
    in a broad except because a missing `.git` dir, no git binary, or a
    slim/exported copy of the repo must degrade to "no commit known", never
    crash the app shell over a cosmetic footer detail."""
    env_commit = os.getenv("RENDER_GIT_COMMIT")
    if env_commit:
        return env_commit[:7]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2,
            cwd=Path(__file__).resolve().parent,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


APP_COMMIT = _detect_commit_hash()

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
    # Residential Mix Intelligence (Sprint 4.4 Amendment, Part 16) - the
    # three evidence-state words that vocabulary didn't already cover.
    # "auto_applied" already exists as a distinct kind above under a
    # different key name ("info" is used for it via evidence_confidence_
    # badge) - these three are additions, not renames, so nothing already
    # calling status_badge("review"/"pending"/...) changes meaning.
    "calculated": {"color": "blue", "icon": "🧮", "label": "Calculated"},
    "conflicting": {"color": "red", "icon": "⚠", "label": "Conflicting"},
    "not_identified": {"color": "gray", "icon": "❔", "label": "Not identified"},
    "stale": {"color": "orange", "icon": "🕗", "label": "Stale"},
    "superseded": {"color": "gray", "icon": "🗂", "label": "Superseded"},
    # Allocation Discovery (Sprint 4.5, Part 8) - the plan-status chip
    # vocabulary, restrained/text-first per that sprint's colour treatment
    # rules: Adopted green, Emerging/Regulation 19 purple, Regulation
    # 18/consultation amber, Examination blue, Withdrawn/superseded red,
    # Unknown/insufficient evidence slate/gray. Distinct from the generic
    # "confirmed"/"review" kinds above - a plan's status is never the same
    # signal as an evidence-review state, so it gets its own kinds rather
    # than reusing "confirmed" for "adopted".
    "plan_adopted": {"color": "green", "icon": "✅", "label": "Adopted"},
    "plan_emerging": {"color": "violet", "icon": "🟣", "label": "Emerging"},
    "plan_consultation": {"color": "orange", "icon": "🟠", "label": "Consultation"},
    "plan_examination": {"color": "blue", "icon": "🔵", "label": "Examination"},
    "plan_withdrawn": {"color": "red", "icon": "🛑", "label": "Withdrawn / superseded"},
    "plan_unknown": {"color": "gray", "icon": "❔", "label": "Unknown"},
    # Sprint 4.5b ("Entity Search + Allocation Card Refinement", Part 2) -
    # the compact positive replacement for the old card-level "no linked
    # application" panel; green like "confirmed" since a genuinely linked
    # Application is exactly that - confirmed, real evidence - never shown
    # for a fuzzy/suggested match (see build_allocation_card's own
    # show_linked_application_tag, computed only from a real
    # linked_application_count).
    "linked_application": {"color": "green", "icon": "🔗", "label": "Planning application linked"},
    # Sprint 4.5b Product Owner amendment (Part 21) - Development Type
    # badges for the Explore mobile card view, built from app.ui.
    # housing_type.classify_housing_type's existing, already-deterministic
    # bucketing of the REAL stored development_type/housing_typology
    # fields (not a new taxonomy - see that module's own docstring).
    # Deliberately a different colour set from the plan_* kinds above, per
    # the explicit requirement that "Planning-status colours and
    # Development-Type colours represent different concepts and must
    # remain distinguishable" - every one of these still carries its own
    # visible text label too, never colour alone.
    "dev_type_houses": {"color": "orange", "icon": "🏠", "label": "Houses"},
    "dev_type_apartments": {"color": "blue", "icon": "🏢", "label": "Apartments"},
    "dev_type_mixed": {"color": "violet", "icon": "🏘️", "label": "Mixed (houses & apartments)"},
    "dev_type_other": {"color": "gray", "icon": "🏗️", "label": "Other/specialist"},
    # A different icon from plan_unknown's "❔" (even though both
    # deliberately share the "gray = uncertain" colour language already
    # established across this design system) - the two badge kinds never
    # actually appear on the same card (dev_type_* is Explore-only,
    # plan_* is Allocation Discovery-only), but keeping them visually
    # distinct removes any ambiguity regardless.
    "dev_type_unknown": {"color": "gray", "icon": "◻️", "label": "Unknown"},
    # Opportunity Experience V2 - the opportunity-signal badge shown on the
    # unified Opportunities feed and the Opportunity Profile header.
    # Deliberately blue/gray (the same neutral, informational colour family
    # as "info"/"plan_examination" above), never green ("confirmed"/
    # "success") or a "hot deal" colour - this is a deterministic evidence
    # signal, not an endorsement (that product distinction is explicit in
    # the Opportunity Experience V2 brief: "prominent but not resemble an
    # investment recommendation").
    "signal_investigate": {"color": "blue", "icon": "🔎", "label": "Investigate"},
    "signal_monitor": {"color": "gray", "icon": "👁", "label": "Monitor"},
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
                      color: #8A97A3; font-size: 0.85rem; line-height: 1.6; }
        .pig-empty-state { text-align: center; padding: 2.5rem 1.5rem; }
        .pig-empty-state-icon { font-size: 2.5rem; margin-bottom: 0.5rem; }

        /* Opportunity Experience V2 - reason/tag pills on the unified
           Opportunities feed and Opportunity Profile header. Muted/neutral
           (not the signal badge's own colour) since a tag here is
           supporting context (opportunity type, plan stage, planning
           activity state), never a second competing signal. */
        .pig-opp-tag {
            display: inline-block; background-color: #EEF1F4; color: #445264;
            border-radius: 999px; padding: 0.15rem 0.65rem; margin: 0 0.3rem 0.3rem 0;
            font-size: 0.78rem; font-weight: 500;
        }

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

        /* Explore Development Site results (Sprint 4.5b Product Owner
           amendment, Part 20) - CSS-only table/card switching, never a
           JavaScript viewport check, timer, or other responsive hack. Both
           the desktop table (st-key-explore-desktop-table) and the mobile
           card list (st-key-explore-mobile-cards) are always rendered;
           only one is ever visible, purely via a standard CSS media query
           at a single breakpoint - the same "let CSS reflow it" approach
           already proven by the council-grid rule above, not a new
           technique. Scoped to these two container keys only, which exist
           on no other page, so this can't affect anything elsewhere. */
        @media (max-width: 640px) {
            [class*="st-key-explore-desktop-table"] { display: none !important; }
        }
        @media (min-width: 641px) {
            [class*="st-key-explore-mobile-cards"] { display: none !important; }
        }
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


OPPORTUNITY_SIGNAL_BADGE_KIND = {"INVESTIGATE": "signal_investigate", "MONITOR": "signal_monitor"}


def opportunity_feed_card(card: dict, *, key: str) -> None:
    """One card in the unified Opportunities feed (Opportunity Experience
    V2) - card is app.reporting.opportunity_feed.build_opportunity_feed's
    own output; this only renders it. Deliberately a single shape for both
    opportunity types (strategic land / planning-delivery) - `signal` is
    None for a planning/delivery card (that type never had a build_
    opportunity_signal classification computed for it - see that module's
    own docstring on why this never invents one) so only strategic-land
    cards show the signal badge; every card shows its own real
    headline_reason regardless of type, so the "why surfaced" story is
    never missing just because a type lacks a formal signal."""
    with st.container(border=True, key=f"opp-feed-{key}-{card['id']}"):
        st.markdown(f"##### {_escape(card['title'])}")
        st.caption(card["subtitle"])
        if card.get("signal"):
            status_badge(OPPORTUNITY_SIGNAL_BADGE_KIND.get(card["signal"], "info"), card.get("signal_label") or card["signal"])
        if card.get("headline_reason"):
            st.write(card["headline_reason"])

        if card.get("metrics"):
            cols = st.columns(len(card["metrics"]))
            for col, (label, value) in zip(cols, card["metrics"]):
                with col:
                    stat_tile(label, value)

        if card.get("tags"):
            st.markdown(
                " ".join(f'<span class="pig-opp-tag">{_escape(t)}</span>' for t in card["tags"]),
                unsafe_allow_html=True,
            )

        if card.get("page"):
            st.page_link(card["page"], label="View opportunity →", query_params=card.get("params") or {})


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
def site_profile_header(header: dict) -> None:
    """The Site Profile executive header (Sprint 4.4, Part 2) - address,
    primary application reference, and every status badge that's actually
    available, laid out for a ~30-second read. header is
    app.reporting.site_profile.build_site_header's own output - every
    field is either a real fact or None, and this renders ONLY the
    fields that are present, never "None" or an unsupported zero."""
    st.title(header["address"])
    caption_bits = [header["council_code"]]
    if header["primary_reference"]:
        caption_bits.append(header["primary_reference"])
    st.caption(" · ".join(caption_bits))

    badges = []
    if header["planning_status_label"]:
        badges.append(("info", header["planning_status_label"]))
    if header["decision_status_label"]:
        kind = "confirmed" if header["decision_status_label"] == "Granted" else (
            "rejected" if header["decision_status_label"] == "Refused" else "pending"
        )
        badges.append((kind, header["decision_status_label"]))
    if header["build_status_label"]:
        badges.append(("info", header["build_status_label"]))
    if header["lapse_status_label"] and header["lapse_status_label"] not in ("OK", "Not yet granted"):
        badges.append(("review", header["lapse_status_label"]))
    if header["allocation_badge"]:
        badges.append(("info", f"📋 {header['allocation_badge']}"))

    if badges:
        # Equal-width columns clip a long badge (e.g. the build-status
        # label's "(0 EPCs - may still be under construction)" detail)
        # with Streamlit's native badge ellipsis - width each column by
        # its own label length instead, so a long badge gets the room it
        # needs and short ones stay compact.
        cols = st.columns([max(len(label), 10) for _, label in badges])
        for col, (kind, label) in zip(cols, badges):
            with col:
                status_badge(kind, label)

    if header["latest_evidence_update"]:
        st.caption(f"Evidence last updated {relative_time(header['latest_evidence_update'])}")


def opportunity_position_card(op: dict) -> None:
    """The Opportunity Position section (Sprint 4.4, Part 4) - a
    deterministic, evidence-grounded explanation of why a scheme is
    currently noteworthy, never a planning-permission prediction. op is
    app.reporting.site_profile.build_opportunity_position's own output -
    this only renders it, never re-derives or embellishes the wording."""
    with st.container(border=True):
        st.markdown("**🎯 Opportunity Position**")
        st.write(op["headline"])
        if len(op["reasons"]) > 1:
            for reason in op["reasons"][1:]:
                st.caption(f"• {reason}")
        st.markdown(f"**Why it matters:** {op['why_it_matters']}")
        st.markdown(f"**Investigate next:** {op['investigate_next']}")


def evidence_gap_panel(gaps: list[str]) -> None:
    """A short, honest list of what's missing (Sprint 4.4, Part 12/14) -
    kept visible but secondary to headline information, never a reason to
    hide a tab."""
    if not gaps:
        st.caption("No significant evidence gaps identified for this site.")
        return
    with st.container(border=True):
        st.markdown("**⚠ Evidence gaps**")
        for gap in gaps:
            st.caption(f"• {gap}")


def _control_relationship_evidence_bits(item) -> list[str]:
    bits = []
    if item.confidence:
        bits.append(f"{item.confidence.title()} confidence")
    if item.title_number:
        bits.append(f"Title: {item.title_number}")
    if item.evidence_date:
        bits.append(f"Evidence date: {item.evidence_date.strftime('%d %b %Y')}")
    return bits


def control_relationship_group_card(group) -> None:
    """Stage 4B.2 - one entity/role card for a Site- or allocation-Site-
    scoped Ownership & Control aggregate (app.reporting.ownership_control.
    ControlRelationshipGroup). Display-layer grouping only - the reporting
    layer never merges the underlying ControlRelationship rows, so every
    supporting evidence record stays inspectable in the expander below
    regardless of how many are grouped together on this one card. Accepts
    the dataclass directly (duck-typed, not imported here, to keep this
    presentation-only module decoupled from the reporting layer's own
    types - see module docstring)."""
    with st.container(border=True):
        st.markdown(f"**{group.entity_name_raw}**")
        st.write(group.role_label)
        if group.needs_review:
            status_badge("review", "Evidence requires review")
        if group.company_id:
            st.caption("Matched to a known company record")
        if group.supporting_evidence_count > 1:
            st.caption(f"{group.supporting_evidence_count} supporting planning documents")
        else:
            st.caption(group.items[0].evidence_source_label)
            bits = _control_relationship_evidence_bits(group.items[0])
            if bits:
                st.caption(" · ".join(bits))
        if group.application_references:
            st.caption("Application: " + ", ".join(group.application_references))
        with st.expander(f"View {group.supporting_evidence_count} supporting evidence record(s)"):
            for item in group.items:
                st.markdown(f"- **{item.evidence_source_label}** ({item.application_reference or 'application not linked'})")
                bits = _control_relationship_evidence_bits(item)
                if bits:
                    st.caption(" · ".join(bits))
                if item.needs_review:
                    status_badge("review", "Evidence requires review")
                if item.evidence_snippet:
                    st.caption(f"“{item.evidence_snippet}”")
                if item.document_source_url:
                    st.markdown(f"[Open source document]({item.document_source_url})")


def control_relationship_view_card(view) -> None:
    """Stage 4B.2 - one ControlRelationship row, full fidelity, un-grouped
    (app.reporting.ownership_control.ControlRelationshipView) - used for the
    Application-level breakdown, which shows exactly one Application's own
    evidence, never aggregated."""
    with st.container(border=True):
        st.markdown(f"**{view.entity_name_raw}**")
        st.write(view.role_label)
        if view.needs_review:
            status_badge("review", "Evidence requires review")
        st.caption(view.evidence_source_label)
        bits = _control_relationship_evidence_bits(view)
        if bits:
            st.caption(" · ".join(bits))
        if view.company_id:
            st.caption("Matched to a known company record")
        if view.evidence_snippet:
            st.caption(f"“{view.evidence_snippet}”")
        if view.document_source_url:
            st.markdown(f"[Open source document]({view.document_source_url})")


def _visual_evidence_card(card: dict, *, width: int = 200) -> None:
    if card.get("image_path") and os.path.exists(card["image_path"]):
        st.image(card["image_path"], width=width)
    detail = card["label"]
    if card.get("source_title"):
        detail += f" — {card['source_title']}"
    if card.get("source_page"):
        detail += f", page {card['source_page']}"
    st.caption(detail)
    review_badge(card.get("confidence"), confirmed=card.get("review_status") == "confirmed")
    if card.get("source_url"):
        st.caption(f"[View source document]({card['source_url']})")


def visual_evidence_gallery(gallery: dict) -> None:
    """The Visual Evidence tab's gallery (Sprint 4.4, Part 9) - confirmed
    evidence always outranks suggested evidence in the layout (primary
    first, other confirmed second, needs-review last, clearly labelled),
    never a local filesystem path shown as text (image_path is only ever
    passed to st.image as a source - see app.reporting.site_profile's own
    docstring on this)."""
    if not gallery["has_any"]:
        st.info("No confirmed or suggested visual evidence has been extracted for this site yet.")
        return

    if gallery["primary"]:
        st.markdown("**Primary evidence**")
        _visual_evidence_card(gallery["primary"], width=360)

    if gallery["other_confirmed"]:
        st.markdown(f"**Other confirmed evidence ({len(gallery['other_confirmed'])})**")
        cols = st.columns(min(len(gallery["other_confirmed"]), 4))
        for i, card in enumerate(gallery["other_confirmed"]):
            with cols[i % len(cols)]:
                _visual_evidence_card(card)

    if gallery["needs_review"]:
        st.markdown(f"**Suggested evidence awaiting review ({len(gallery['needs_review'])})**")
        st.caption("AI-suggested, not yet confirmed by a reviewer - shown here so nothing useful is hidden.")
        cols = st.columns(min(len(gallery["needs_review"]), 4))
        for i, card in enumerate(gallery["needs_review"]):
            with cols[i % len(cols)]:
                _visual_evidence_card(card)


def status_badge_row(badges: list[tuple[str, str]]) -> None:
    """A row of status_badge calls, each column proportionally sized to its
    own label length (Sprint 4.5a, "Commercial Polish", Part 8: "badge text
    must not truncate at common laptop widths") - the same fix already
    proven on site_profile_header's own badge row, reused here (and by any
    other page needing a multi-badge row) rather than invented per call
    site. Equal-width st.columns clips a long label with Streamlit's
    native badge ellipsis well before a typical laptop's column width
    runs out; sizing each column to len(label) instead gives a long badge
    the room it needs and keeps short ones compact."""
    cols = st.columns([max(len(label), 10) for _, label in badges])
    for col, (kind, label) in zip(cols, badges):
        with col:
            status_badge(kind, label)


def allocation_card(card: dict, *, key: str, in_shortlist: bool = False) -> bool:
    """One Allocation Discovery gallery card (Sprint 4.5, Part 7; commercial
    presentation refined in Sprint 4.5a, Part 1) - card is
    app.reporting.allocation_discovery.build_allocation_card's own output;
    this only renders it, never re-derives or embellishes any fact. Layout
    follows Sprint 4.5a's specified scan order - name, development type,
    capacity, planning status, why it matters, actions - with the policy
    reference demoted to a small caption alongside council/plan context
    rather than leading the card (Part 1: "avoid presenting policy
    references as the primary information"). Every card renders with
    identical size/border/emphasis regardless of capacity - larger
    allocations are never made visually more prominent (Sprint 4.5a's
    product principle: PropertyAIgent never decides what the "best" site
    is; only the descriptive wording, never the visual weight, varies with
    scale). Reuses _visual_evidence_card for the thumbnail, status_badge/
    joint_plan_badge for badges, and render_alert for the "no linked
    application" commercial signal - no new badge/image/alert rendering
    invented here beyond registering that one new render_alert kind.

    Site Selection & Reporting V1 Gate 1 - `in_shortlist` is a plain
    already-computed bool the caller passes in (this module never touches
    st.session_state itself, per its own "presentation-only" module
    docstring); the return value is just this render's button click,
    letting the page script decide what to do about it (add/remove via
    app.ui.shortlist) rather than this component owning that decision."""
    with st.container(border=True, key=f"alloc-card-{key}"):
        # 1. Allocation name
        st.markdown(f"##### {_escape(card['site_name'])}")
        # 2. Development type - a concise commercial description, omitted
        # honestly when no existing evidence supports one.
        if card.get("development_type"):
            st.caption(f"🏘️ {_escape(card['development_type'])}")

        context_bits = [b for b in (card["council_name"], card["plan_name"], card.get("policy_reference")) if b]
        st.caption(" · ".join(_escape(str(b)) for b in context_bits))

        # 3. Capacity - a natural sentence fragment, not a bare field/value pair.
        st.markdown(f"**{_escape(card['capacity']['display'])}**")

        # 4. Planning status - the linked-application tag (Sprint 4.5b,
        # Part 2) sits in the same badge row as plan/review status, only
        # when a real linked Application relationship exists.
        badges = [(card["plan_status_chip_kind"], card["plan_status_label"]), (card["review_status_badge_kind"], card["review_status_label"])]
        if card.get("show_linked_application_tag"):
            badges.append(("linked_application", card["linked_application_tag_label"]))
        status_badge_row(badges)
        if card["is_multi_authority"]:
            joint_plan_badge()

        visual = card["visual_primary"] or card["visual_fallback"]
        if visual:
            _visual_evidence_card(visual, width=280)
            if card["visual_fallback"] and not card["visual_primary"]:
                st.caption(
                    "Published as part of the council's authority-wide Policies Map, not a boundary image "
                    "specific to this allocation."
                )
        else:
            st.caption("🖼 No confirmed or suggested visual evidence yet.")

        # Sprint 4.5b, Part 1 - the old "no linked planning application"
        # panel is gone from the card entirely (moved to Allocation Detail,
        # Part 3); this plain caption is the only card-level statement of
        # match/link status now, regardless of whether a link exists.
        st.caption(card["matched_summary"], help=card["matched_summary_help"])
        if card.get("build_status_label"):
            st.caption(card["build_status_label"])
        if card.get("delivery_note"):
            st.caption(card["delivery_note"])

        # 4a. Stage 3A development coverage - concise, evidence-only
        # signal (never "available land/units"). Already-formatted by
        # app.reporting.allocation_discovery.build_allocation_card (this
        # component stays a pure reader of card dict keys, like every
        # other field above - no app.reporting import here). None when
        # this card has no relationship data at all.
        coverage_summary = card.get("development_coverage_summary")
        if coverage_summary and (coverage_summary["headline"] or coverage_summary["lines"]):
            st.markdown(f"**{_escape(coverage_summary['headline'])}**")
            for line in coverage_summary["lines"]:
                st.caption(_escape(line))

        # 5. Why it matters
        st.caption(f"**Why it matters:** {card['why_it_matters']}")
        st.caption(f"**Investigate next:** {card['investigate_next']}")

        # 6. Actions - the primary action stands alone, secondary
        # navigation links follow, the external source link (smallest,
        # least important) last - a simple visual hierarchy rather than
        # four identical, undifferentiated links in a row.
        st.divider()
        # Site Selection & Reporting V1 Gate 1 - the shortlist toggle sits
        # above the navigation links, as its own full-width button (a
        # mutation, not a navigation - kept visually distinct from the
        # page_links below rather than folded into the same row).
        shortlist_clicked = st.button(
            "✓ Shortlisted — remove" if in_shortlist else "☆ Add to shortlist",
            key=f"alloc-shortlist-toggle-{key}", use_container_width=True,
        )
        st.page_link(
            "pages/3_Local_Plan_Sites.py", label="Open Allocation →",
            query_params={"allocation_id": str(card["id"])},
        )
        if card["matched_site_id"]:
            st.page_link(
                "pages/1_Scheme_Detail.py", label="Open Site Profile →",
                query_params={"site_id": str(card["matched_site_id"])},
            )
        st.page_link(
            "pages/6_Council_Intelligence_Detail.py", label="Open Council Intelligence →",
            query_params={"council": card["council_code"]},
        )
        source_link = card.get("plan_page_url") or card.get("source_document_url")
        if source_link:
            st.caption(f"[Open source document →]({source_link})")

    return shortlist_clicked


def entity_search_result_row(result, *, key: str) -> None:
    """One Entity Search hit (Sprint 4.5b, Part 8/9) - `result` is an
    app.reporting.entity_search.SearchResult, accessed by attribute only
    (never imported - this module stays free of app.* imports by design,
    see its own docstring). Renders identically regardless of entity_type
    except for the destination label/link - the two entity types are never
    visually merged into one ambiguous row shape, and matched_entity_label
    (Part 8's "Linked to allocation JPA 8" / "Linked planning Site"
    indicator) is only ever shown when the caller already found a real
    matched_site_id relationship - never inferred here."""
    with st.container(border=True, key=key):
        st.markdown(f"**{_escape(result.title)}**")
        if result.subtitle:
            st.caption(_escape(result.subtitle))
        meta_bits = [b for b in (result.status, result.capacity_or_units) if b]
        if meta_bits:
            st.caption(" · ".join(_escape(str(b)) for b in meta_bits))
        if result.matched_entity_label:
            st.caption(f"🔗 {_escape(result.matched_entity_label)}")
        label = "Open Allocation →" if result.entity_type == "allocation" else "Open Site →"
        st.page_link(result.destination_page, label=label, query_params=result.destination_params)


def entity_search_results_panel(results, *, key_prefix: str) -> None:
    """`results` is an app.reporting.entity_search.EntitySearchResults -
    grouped, never-merged sections (Part 8), each entity type in its own
    labelled subsection so a user can never mistake an Allocation result
    for a Development Site result or vice versa.

    "Development Sites" is the Sprint 4.5b Product Owner amendment's
    customer-facing rename of the entity_type="planning_site" group (Part
    2) - the underlying Site/Application domain model and internal names
    (entity_type value, results.planning_sites attribute,
    search_planning_site_entities) are deliberately unchanged, since this
    is a terminology change, not a domain-model rewrite."""
    if results.is_empty:
        empty_state(
            "No matches found",
            f"No Development Sites or Allocations matched \"{results.query}\" - try a shorter search term.",
            icon="🔍", show_home_link=False,
        )
        return
    if results.allocations:
        st.markdown(f"###### 🗺️ Allocations ({len(results.allocations)})")
        for i, result in enumerate(results.allocations):
            entity_search_result_row(result, key=f"{key_prefix}-alloc-{i}-{result.entity_id}")
    if results.planning_sites:
        st.markdown(f"###### 📍 Development Sites ({len(results.planning_sites)})")
        for i, result in enumerate(results.planning_sites):
            entity_search_result_row(result, key=f"{key_prefix}-site-{i}-{result.entity_id}")


def ai_status_summary_view(ai_summary: dict) -> None:
    """The AI Summary tab (Sprint 4.4, Part 11) - reuses the existing
    stored Site status summary via ai_summary_card, never regenerates it.
    Site.status_summary has no separately-stored Key Changes/Evidence
    Gaps/Suggested Investigation subsections (unlike LocalPlan's own AI
    summary) - see app.reporting.site_profile.build_ai_summary_view's own
    docstring for why this shows the whole stored text as one "Current
    position" block rather than fabricating a split the stored output
    doesn't support, and why model/prompt version are omitted rather than
    asserted without a stored per-row value."""
    if not ai_summary["has_summary"]:
        st.info("No AI status summary has been generated yet for this site.")
        return
    ai_summary_card(
        ai_summary["text"],
        generated_at=ai_summary["generated_at"].strftime("%d %b %Y") if ai_summary["generated_at"] else None,
        key="site-ai-summary",
    )
    st.caption(
        "This is the site's full stored status summary (Current position) - no separate Key Changes/"
        "Evidence Gaps/Suggested Investigation subsections are stored for site-level summaries."
    )


def render_footer() -> None:
    """A lightweight footer (Part 8; extended by the Live Deployment
    Integrity audit, Part 2) - product name, version, commit and
    environment, each on its own line, no clutter. The commit hash is the
    reliable drift-detection signal (see _detect_commit_hash's docstring) -
    APP_VERSION alone can't distinguish deployments that never bumped it.
    Environment is always shown, including "Production" - earlier this was
    suppressed for production to reduce clutter, but that meant production
    and an unconfigured environment looked identical here, which defeats
    the point of a drift-detection footer."""
    commit_display = APP_COMMIT or "unknown"
    st.markdown(
        f'<div class="pig-footer">'
        f'<div>{PRODUCT_NAME}</div>'
        f'<div>Version: v{APP_VERSION}</div>'
        f'<div>Commit: {commit_display}</div>'
        f'<div>Environment: {APP_ENVIRONMENT.capitalize()}</div>'
        f'</div>',
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


def arrow_safe_count(value: int | None, placeholder: str = "—") -> str:
    """Render an optional integer count as a plain display string, for any
    table column where some rows carry a known count and others fall back
    to a placeholder - e.g. Planning Position's phase/plot Units column.
    A pandas column built from a mix of raw int values and str placeholders
    across different rows gets dtype "object", which PyArrow's
    Table.from_pandas can't reliably infer a single Arrow type for and
    raises ArrowInvalid on. Always returning a string here keeps the
    column's dtype uniform regardless of which rows have a known value, so
    st.dataframe can serialize it without relying on Streamlit's own
    internal Arrow-incompatibility fallback. Treats a count of 0 the same
    as "unknown" (falls back to the placeholder) - matches the truthiness
    check the call sites already used before this helper existed."""
    return str(value) if value else placeholder


def clean_display_text(value: object) -> str | None:
    """Normalises an optional free-text presentation value (e.g. a mobile
    card's Developer/status caption) to either a real, non-empty string or
    None - never a value that renders as the literal text "nan". A column
    built from a mix of str and Python None (e.g. via pd.DataFrame(rows))
    silently coerces None to a pandas/numpy float NaN even when every other
    value is a string, so a bare `if value:`/`str(value)` check is truthy
    for that NaN and prints "nan" - the same class of bug
    app.ui.housing_type.format_affordable_display exists to avoid for the
    Affordable column. pd.isna() catches NaN, pandas.NA and None uniformly;
    a str() coercion first is required because pd.isna() raises on some
    non-scalar inputs, which a free-text presentation value should never be
    here, but this keeps the check unconditionally safe regardless. Genuine
    empty-string or whitespace-only text is treated as equally absent."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _escape(text: str) -> str:
    """Minimal HTML-escaping for the handful of small static-template
    snippets above that interpolate a caller-supplied string directly into
    an HTML attribute-free text node (never used for anything rendered as
    markup itself)."""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;").replace("'", "&#39;")
    )
