"""Allocation Discovery (Sprint 4.5) - the customer-facing, gallery-based
browsing experience for Local Plan allocations, built for developers, land
promoters, planning consultants and investors. Replaces the previous
"Local Plan Sites" table + single-select dropdown with a filterable,
searchable card gallery plus a dedicated allocation detail state - the same
customer-vs-administration separation CLAUDE.md and every other customer
surface in this app already follows: operational review/approval controls
(evidence approve/reject, relink, classification, source-health, ingestion)
live only in Administration, never here.

Data assembly lives in app.reporting.allocation_discovery (a pure, batched
view model) and app.visuals.site_view (batched VisualEvidence lookups) -
this file is presentation only, reusing app.ui.shell's design-system
components (CLAUDE.md: "keep business logic out of the UI").
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from app.reporting.allocation_discovery import (
    SORT_OPTIONS,
    apply_filters,
    build_allocation_discovery,
    build_summary_metrics,
    compute_categories,
    linked_application_help,
    matched_status_help,
    search_allocations,
    sort_cards,
)
from app.ui.common import PROGRESSION_SIGNAL_LABELS, bootstrap, credits_sidebar, get_db
from app.ui.shell import (
    allocation_card,
    empty_state,
    evidence_gap_panel,
    joint_plan_badge,
    page_header,
    section_header,
    stat_tile,
    status_badge,
    timeline,
    visual_evidence_gallery,
    wide_canvas,
)

PAGE_SIZE = 24
THIS_PAGE = "pages/3_Local_Plan_Sites.py"

bootstrap()
session, settings = get_db()

HOME_PAGE = Path(__file__).resolve().parents[1] / "pages" / "0_Explore.py"
st.page_link(HOME_PAGE, label="← Back to Explore", icon="🔙")

credits_sidebar(session, settings)
wide_canvas()


# --- Allocation detail state (Part 12 - a query-param selected state on
# this same page, chosen over a separate page file to keep one gallery +
# one detail experience together, consistent with how this page already
# worked before this sprint; chosen over an inline card expansion because
# docs/INTERACTION_DESIGN.md's selection rule is explicit that choosing one
# item from a gallery should navigate to a detail view, never expand
# in place). -----------------------------------------------------------------

def _render_detail(view: dict, allocation_id: int) -> None:
    card = next((c for c in view["cards"] if c["id"] == allocation_id), None)
    if st.button("← Back to Allocation Discovery", icon="🔙", key="alloc-detail-back"):
        st.query_params.clear()
        st.rerun()

    if card is None:
        empty_state(
            "Allocation not found",
            "That allocation id isn't recognised. Browse every allocation in Allocation Discovery.",
            icon="⚠️", cta_label="Browse Allocation Discovery", cta_page=THIS_PAGE,
        )
        return

    page_header(card["site_name"], icon="🗺️")
    caption_bits = [b for b in (card["policy_reference"], card["council_name"], card["plan_name"]) if b]
    st.caption(" · ".join(caption_bits))

    badge_cols = st.columns(3 if card["is_multi_authority"] else 2)
    with badge_cols[0]:
        status_badge(card["plan_status_chip_kind"], card["plan_status_label"])
    with badge_cols[1]:
        status_badge(card["review_status_badge_kind"], card["review_status_label"])
    if card["is_multi_authority"]:
        with badge_cols[2]:
            joint_plan_badge()

    # 1. Allocation overview
    section_header("Overview", icon="📋")
    st.markdown(f"**Why it matters:** {card['why_it_matters']}")
    if len(card["why_it_matters_reasons"]) > 1:
        for reason in card["why_it_matters_reasons"][1:]:
            st.caption(f"• {reason}")
    st.markdown(f"**Investigate next:** {card['investigate_next']}")

    # 2. Planning and policy status
    section_header("Planning and policy status", icon="🏛️")
    st.write(f"**Plan status:** {card['plan_status_label']} — {card['plan_name']}")
    if card["progression_signal"]:
        st.write(f"**Progression signal:** {PROGRESSION_SIGNAL_LABELS.get(card['progression_signal'], card['progression_signal'])}")
    st.write(f"**Allocation review state:** {card['review_status_label']}")
    if card["is_multi_authority"] and card["cross_boundary_councils"]:
        other_names = ", ".join(view["council_names"].get(c, c) for c in card["cross_boundary_councils"])
        st.caption(f"Cross-boundary: this Local Plan is also linked to {other_names}.")

    # 3. Capacity and intended use
    section_header("Capacity and intended use", icon="🏗️")
    cap_cols = st.columns(2)
    with cap_cols[0]:
        stat_tile("Intended use", card["intended_use_label"])
    with cap_cols[1]:
        stat_tile("Capacity", card["capacity"]["display"])
    if card["category"]:
        st.caption(f"Council grouping: {card['category']}")

    # 4. Visual evidence gallery
    section_header("Visual evidence", icon="🖼️")
    gallery = {
        "has_any": card["visual_primary"] is not None or bool(card["visual_others"]) or card["visual_fallback"] is not None,
        "primary": card["visual_primary"],
        "other_confirmed": [c for c in card["visual_others"] if c["review_status"] == "confirmed"],
        "needs_review": [c for c in card["visual_others"] if c["review_status"] != "confirmed"],
    }
    if not card["visual_primary"] and card["visual_fallback"]:
        st.info(
            "No allocation-specific image has been confirmed for this allocation. The council publishes "
            "allocation boundaries through one authority-wide Policies Map rather than a separate image per "
            "allocation - shown below for reference. This is not an allocation-specific boundary image."
        )
        gallery["primary"] = card["visual_fallback"]
        gallery["has_any"] = True
    visual_evidence_gallery(gallery)

    # 5. Matched Sites and Applications
    section_header("Matched Site and Applications", icon="🔗")
    st.caption(card["matched_summary"], help=card["matched_summary_help"])
    if card["matched"]:
        if card["matched_site_address"]:
            st.write(f"**Matched Site:** {card['matched_site_address']}")
        if card["match_confidence"] is not None:
            st.caption(f"Match confidence: {card['match_confidence']:.0f}%")
        st.page_link(
            "pages/1_Scheme_Detail.py", label="Open Site Profile →",
            query_params={"site_id": str(card["matched_site_id"])},
        )
    else:
        st.caption(
            "Open Council Intelligence or Explore to check whether an Application exists for this location "
            "under a different address or reference."
        )

    # 6. Progression / build evidence
    section_header("Progression and build evidence", icon="🏗️")
    if card["build_status_label"]:
        st.write(f"**Build status:** {card['build_status_label']}")
    else:
        st.caption("No build/commencement evidence available yet for this allocation.")
    if card["delivery_note"]:
        st.caption(card["delivery_note"])

    # 7. Source evidence and provenance
    section_header("Source evidence", icon="📄")
    source_link = card.get("plan_page_url") or card.get("source_document_url")
    if source_link:
        st.markdown(f"[Open source document]({source_link})")
    if card["last_checked"]:
        st.caption(f"Local Plan evidence last checked {card['last_checked'].strftime('%d %b %Y')}.")

    # 8. Evidence gaps
    gaps = []
    if card["capacity"]["kind"] == "unknown":
        gaps.append("No capacity figure (minimum, indicative or maximum) has been stated for this allocation.")
    if not card["matched"]:
        gaps.append("Not matched to a Site - no linked Application evidence is available in PropertyAIgent.")
    if card["visual_status"] == "none" and card["visual_fallback"] is None:
        gaps.append("No confirmed or suggested visual evidence has been extracted for this allocation.")
    if card["review_status"] == "needs_confirmation":
        gaps.append("This allocation's Site match or status is awaiting confirmation - see Administration.")
    section_header("Evidence gaps", icon="⚠️")
    evidence_gap_panel(gaps)

    # 9. Timeline (where supported) - AllocationVersion rows already carry
    # a deterministic change_reason + captured_at, so this is real,
    # already-stored evidence, not a new extraction pipeline.
    from app.db.models import LocalPlanSite

    allocation_row = session.get(LocalPlanSite, allocation_id)
    if allocation_row and allocation_row.versions:
        section_header("Timeline", icon="🕒")
        entries = [
            {
                "icon": "📝",
                "label": v.change_reason.replace("_", " ").title(),
                "when": v.captured_at,
            }
            for v in sorted(allocation_row.versions, key=lambda v: v.captured_at or 0, reverse=True)
        ]
        timeline(entries, key=f"alloc-timeline-{allocation_id}")


_allocation_id_param = st.query_params.get("allocation_id")
if _allocation_id_param and _allocation_id_param.isdigit():
    _view_for_detail = build_allocation_discovery(session)
    _render_detail(_view_for_detail, int(_allocation_id_param))
    st.stop()


# --- Gallery ------------------------------------------------------------

page_header(
    "Allocation Discovery",
    "Explore adopted and emerging Local Plan allocations, their development capacity, visual evidence and "
    "links to known planning activity.",
    icon="🗺️",
)

all_view = build_allocation_discovery(session)
all_cards = all_view["cards"]
if not all_cards:
    empty_state(
        "No Local Plan data yet",
        "Run ingest_local_plan.py for a council to add its Local Plan allocations.",
        icon="🗺️",
    )
    st.stop()

summary = build_summary_metrics(all_cards)
metric_cols = st.columns(5)
with metric_cols[0]:
    stat_tile("Total allocations", f"{summary['total_allocations']:,}")
with metric_cols[1]:
    stat_tile("Adopted", f"{summary['adopted_allocations']:,}")
with metric_cols[2]:
    stat_tile("Emerging", f"{summary['emerging_allocations']:,}")
with metric_cols[3]:
    stat_tile("With visual evidence", f"{summary['with_visual_evidence']:,}")
with metric_cols[4]:
    stat_tile("Matched to Sites", f"{summary['matched_to_sites']:,}")
st.caption(
    f"{summary['no_linked_application']:,} allocation(s) with no linked Application currently held by the "
    f"platform · {summary['needs_review']:,} awaiting review."
)

# --- Search ---------------------------------------------------------------

query = st.text_input(
    "Search allocations", key="alloc-search",
    placeholder="Search by allocation name, policy reference, council, Local Plan, intended use or matched Site...",
)

# --- Filters (Part 5 - a compact, contained panel, not a sidebar dump) ----

all_council_codes = all_view["all_council_codes"]
council_names = all_view["council_names"]
_council_param = st.query_params.get("council")
_default_councils = [_council_param] if _council_param in all_council_codes else []

with st.container(border=True):
    filter_top_cols = st.columns([3, 2])
    with filter_top_cols[0]:
        selected_councils = st.multiselect(
            "Council", all_council_codes, default=_default_councils,
            format_func=lambda code: council_names.get(code, code), key="alloc-filter-council",
        )
    with filter_top_cols[1]:
        selected_buckets = st.multiselect(
            "Plan status", ["adopted", "emerging", "other"], default=[],
            format_func=lambda b: {"adopted": "Adopted", "emerging": "Emerging", "other": "Other / uncertain"}[b],
            key="alloc-filter-bucket",
        )

    with st.expander("More filters"):
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            selected_uses = st.multiselect(
                "Intended use", ["residential", "employment", "mixed use"], default=[],
                format_func=lambda u: {"residential": "Residential", "employment": "Employment", "mixed use": "Mixed use"}[u],
                key="alloc-filter-use",
            )
            local_plan_options = all_view["all_local_plans"]
            selected_plan_ids = st.multiselect(
                "Local Plan", [pid for pid, _ in local_plan_options], default=[],
                format_func=lambda pid: dict(local_plan_options).get(pid, str(pid)), key="alloc-filter-plan",
            )
        with col_b:
            matched_choice = st.selectbox(
                "Matched Site", ["Any", "Matched", "Unmatched"], index=0, key="alloc-filter-matched",
                help=matched_status_help(),
            )
            application_choice = st.selectbox(
                "Planning activity", ["Any", "Linked Application", "No linked Application"], index=0,
                key="alloc-filter-application", help=linked_application_help(),
            )
        with col_c:
            visual_choice = st.selectbox(
                "Visual evidence", ["Any", "Confirmed visual", "Suggested visual", "No visual"], index=0,
                key="alloc-filter-visual",
            )
            review_choice = st.multiselect(
                "Review state", ["auto_applied", "needs_confirmation", "confirmed"], default=[],
                format_func=lambda r: {"auto_applied": "Auto-applied", "needs_confirmation": "Needs confirmation", "confirmed": "Confirmed"}[r],
                key="alloc-filter-review",
            )

        capacity_values = [c["capacity"]["value"] for c in all_cards if c["capacity"]["value"] is not None]
        capacity_range = None
        capacity_full_span = None
        if capacity_values:
            cap_min, cap_max = min(capacity_values), max(capacity_values)
            if cap_min < cap_max:
                capacity_full_span = (cap_min, cap_max)
                capacity_range = st.slider(
                    "Capacity range (homes)", min_value=cap_min, max_value=cap_max, value=(cap_min, cap_max),
                    key="alloc-filter-capacity",
                    help="An allocation with no stated capacity is only excluded once this is narrowed away "
                         "from the full range shown here.",
                )

        badge_cols = st.columns(2)
        with badge_cols[0]:
            joint_plan_only = st.checkbox("Joint Plan allocations only", value=False, key="alloc-filter-joint")
        with badge_cols[1]:
            cross_boundary_only = st.checkbox("Cross-boundary allocations only", value=False, key="alloc-filter-crossboundary")

    if st.button("Clear filters", key="alloc-filter-clear"):
        for key in (
            "alloc-filter-council", "alloc-filter-bucket", "alloc-filter-use", "alloc-filter-plan",
            "alloc-filter-matched", "alloc-filter-application", "alloc-filter-visual", "alloc-filter-review",
            "alloc-filter-capacity", "alloc-filter-joint", "alloc-filter-crossboundary", "alloc-search",
        ):
            st.session_state.pop(key, None)
        if "council" in st.query_params:
            del st.query_params["council"]
        st.rerun()

filters = {
    "councils": selected_councils or None,
    "plan_status_buckets": selected_buckets or None,
    "intended_uses": selected_uses or None,
    "local_plan_ids": selected_plan_ids or None,
    "matched": {"Matched": "matched", "Unmatched": "unmatched"}.get(matched_choice),
    "application_linkage": {"Linked Application": "linked", "No linked Application": "not_linked"}.get(application_choice),
    "visual_evidence": {"Confirmed visual": "confirmed", "Suggested visual": "suggested", "No visual": "none"}.get(visual_choice),
    "review_states": review_choice or None,
    "joint_plan_only": joint_plan_only,
    "cross_boundary_only": cross_boundary_only,
    # Only a constraint once the user has actually narrowed the slider away
    # from the full observed range - at its default (full-span) position
    # this must behave as "no constraint", never silently excluding every
    # allocation with an unstated capacity (apply_filters' capacity_min/max
    # only keeps cards with a KNOWN value once set - correct once a user
    # deliberately narrows the range, wrong as an always-on default).
    "capacity_min": capacity_range[0] if capacity_range and capacity_range != capacity_full_span else None,
    "capacity_max": capacity_range[1] if capacity_range and capacity_range != capacity_full_span else None,
}

filtered = search_allocations(all_cards, query)
filtered = apply_filters(filtered, filters)

if not filtered:
    empty_state(
        "No allocations match these filters",
        "Try clearing a filter or broadening your search - every allocation currently held by the platform "
        "is included above this point.",
        icon="🔍", cta_label="Clear filters", cta_page=THIS_PAGE,
    )
    st.stop()

# --- Discovery categories + sort (Parts 6 & 16) ---------------------------

sort_labels = [label for _, label in SORT_OPTIONS]
sort_choice_label = st.selectbox("Sort by", sort_labels, index=0, key="alloc-sort")
sort_key = {label: key for key, label in SORT_OPTIONS}[sort_choice_label]
st.caption(
    "Default sort: most recently updated evidence first, then adopted allocations, then emerging, then "
    "everything else - id is always the final tie-breaker, never an invented ranking."
)

categories = compute_categories(filtered)
tab_labels = [f"{c['label']} ({c['count']})" for c in categories]
tabs = st.tabs(tab_labels)

for tab, category in zip(tabs, categories):
    with tab:
        ordered = sort_cards(category["cards"], sort_key)
        show_key = f"alloc-show-{category['key']}"
        shown = st.session_state.get(show_key, PAGE_SIZE)
        page = ordered[:shown]

        cols = st.columns(3)
        for i, card in enumerate(page):
            with cols[i % 3]:
                allocation_card(card, key=f"{category['key']}-{card['id']}")

        if shown < len(ordered):
            st.caption(f"Showing {len(page)} of {len(ordered)} allocations.")
            if st.button("Show more", key=f"alloc-show-more-{category['key']}"):
                st.session_state[show_key] = shown + PAGE_SIZE
                st.rerun()
