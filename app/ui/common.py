"""Shared helpers between the site-list home page and the scheme detail page.

Both pages need the same DB session bootstrap and the same site/application
merge logic, so it lives here rather than being duplicated across the
Streamlit multi-page app's separate script files (each page file runs as its
own top-level script under Streamlit's pages/ convention).
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import load_councils
from app.db.models import (
    Application,
    ApplicationCompany,
    Company,
    Contact,
    LocalPlanSite,
    Officer,
    PersonWithSignificantControl,
    Site,
)
from app.db.session import get_session, get_settings, init_db
from app.enrichment import companies_house
from app.enrichment.contact_pipeline import enrich_company, upsert_company_from_enrichment
from app.pipeline.lapse_tracking import (
    BUILD_STATUS_LABELS,
    COMMENCEMENT_YEARS,
    GRANTED_KEYWORDS,
    LAPSE_STATUS_LABELS,
    LAPSE_WARNING_DAYS,
    compute_lapse_status,
    is_granted_decision,
    parse_portal_date,
)
from app.extraction.local_plan import assess_delivery_scope
from app.pipeline.phase_tracking import PHASE_STATUS_LABELS, build_phase_breakdown, summarize_phase_units
from app.policy.site_view import build_site_policy_intelligence
from app.scrapers.unit_filter import classify_application_category, qualify
from app.visuals import IMAGE_TYPE_LABELS
from app.visuals.site_view import build_site_visual_evidence

PROGRESSION_SIGNAL_LABELS = {
    "early_stage": "🌱 Early stage",
    "progressing": "➡️ Progressing",
    "advanced": "🔶 Advanced",
    "adopted": "✅ Adopted",
    "stalled": "⏸️ Stalled",
    "removed": "❌ Removed / no longer listed",
    "unknown": "❔ Unknown",
    None: "❔ Not yet classified",
}

# Fields pulled from scheme_intelligence and merged across every application
# linked to a site (not just one "representative" application) - a detail
# like the developer name might only have been extracted from a sibling
# application's documents, not the primary outline application's own.
MERGED_SCHEME_FIELDS = [
    "total_units_final", "affordable_units_final", "private_units_final", "affordable_percentage_final",
    "affordable_tenure_split_final", "development_type", "housing_typology", "developer", "applicant_company",
    "landowner", "site_owner", "planning_agent", "architect", "housing_association", "registered_provider",
    "registered_provider_status", "external_consultation_source", "affordable_status_note",
    "data_quality_status", "affordable_classification_reason", "affordable_classification_evidence",
    "site_evidence", "entity_relationship_notes",
]


@st.cache_resource
def bootstrap():
    """Runs once per server process - DB init and the councils config don't
    change between reruns/pages, so there's no need to redo it on every
    script execution the way the plain session/settings lookups below do."""
    load_dotenv(override=True)
    init_db()
    return load_councils()


def get_db():
    """Session + settings need a fresh look-up per rerun (settings.credits_remaining
    can change from user actions), unlike bootstrap() above."""
    session = get_session()
    settings = get_settings(session)
    return session, settings


def load_site_applications(session, site_id: int) -> list[Application]:
    """Every application linked to a site, minus any that would now be
    excluded by unit_filter's rules (screening/scoping opinions, external
    consultation notices, likely single-unit change-of-use applications,
    under-threshold schemes...) - re-evaluated fresh here rather than
    trusting each Application's stored application_category, which was set
    once at scrape time and can go stale whenever the classifier rules are
    tightened afterwards. Confirmed real cases: 18 screening/scoping opinion
    applications, and separately a handful of stale under-threshold/
    single-unit rows (e.g. a 2-dwelling outline application, a dance-studio
    change of use with no residential content at all) were already sitting
    in the DB - persisted back when the rules that would now exclude them
    didn't exist yet - showing up as full qualifying schemes. Re-evaluating
    live means a classifier fix alone is enough to clean up results, with no
    need to edit or delete the underlying scraped rows.

    Once an application HAS been through full AI extraction, its
    total_units_final (drawn from the actual documents) is trusted over a
    fresh qualify() re-run on the proposal text alone - the portal's own
    one-line summary can under- or over-state the true count (e.g. "up to 8
    dwellings" in the summary, revised to 12 in the full application), and
    re-deriving from that stale text alone could wrongly hide a genuine,
    already-verified scheme."""
    apps = session.execute(select(Application).where(Application.site_id == site_id)).scalars().all()
    council = load_councils().get(apps[0].council_code) if apps else None
    threshold = council.unit_threshold if council else 10
    return _filter_visible_applications(apps, threshold)


def _filter_visible_applications(apps: list[Application], threshold: int) -> list[Application]:
    """The per-application "is this actually a visible qualifying scheme"
    rule, shared by load_site_applications (one site, one query) and
    load_applications_for_sites (many sites, one batched query) below - a
    single implementation so the two can never drift out of sync with each
    other."""
    visible = []
    for a in apps:
        si = a.scheme_intelligence
        if si and si.total_units_final is not None:
            if si.total_units_final < threshold:
                continue
            visible.append(a)
            continue
        # A dedicated confirm-units pass (real Application Form/Planning
        # Statement text, or a resolved parent outline for reserved
        # matters filings - see stage_resolve_reserved_matters) already
        # ran and failed to find qualifying evidence - stronger signal
        # than the generic REVIEW_KEYWORDS proposal-text guess below, which
        # e.g. treats ANY "reserved matters"/"outline application" wording
        # as qualifying regardless of the scheme's actual size. Confirmed
        # real case: a reserved matters filing for a single dwelling whose
        # own boilerplate text ("access, scale, layout, appearance and
        # landscape") carries no unit count of its own, staying visible in
        # the main results despite already being marked undetermined here.
        if a.unit_confirmation_status in ("undetermined", "confirmed_disqualified"):
            continue
        if not qualify(a.proposal, threshold).qualifies:
            continue
        visible.append(a)
    return visible


def load_applications_for_sites(session, site_ids: list[int]) -> dict[int, list[Application]]:
    """Batched sibling of load_site_applications - ONE query for every
    given site_id instead of one query per Site, then the same per-
    application visibility rule (_filter_visible_applications) applied per
    group. Built for the map/table home page, which otherwise queries once
    per Site on every page load (Sprint 3A, "Map Navigation and Site UX",
    Part 6: "avoid one database query per marker"). Returns every requested
    site_id, even ones with no visible applications (an empty list, not a
    missing key), so callers can index the result without a .get() default."""
    if not site_ids:
        return {}
    # selectinload, not the default lazy load - _filter_visible_applications
    # reads a.scheme_intelligence for every application, which would
    # otherwise fire one extra query PER application (confirmed by a real
    # query-count test) - exactly the same "one query per marker" problem
    # this whole function exists to eliminate, just one join deeper. This
    # keeps the total query count at 2 (applications + their
    # scheme_intelligence, batched) no matter how many Sites or
    # Applications are involved.
    apps = session.execute(
        select(Application).where(Application.site_id.in_(site_ids)).options(selectinload(Application.scheme_intelligence))
    ).scalars().all()

    by_site: dict[int, list[Application]] = {site_id: [] for site_id in site_ids}
    for a in apps:
        by_site.setdefault(a.site_id, []).append(a)

    councils = load_councils()
    result: dict[int, list[Application]] = {}
    for site_id, site_apps in by_site.items():
        council = councils.get(site_apps[0].council_code) if site_apps else None
        threshold = council.unit_threshold if council else 10
        result[site_id] = _filter_visible_applications(site_apps, threshold)
    return result


def load_watchlist_applications(session) -> list[Application]:
    """Screening/scoping opinions aren't qualifying schemes in their own
    right (no real applicant/documents behind them yet), so they're
    correctly excluded from the main results by load_site_applications - but
    they're still a genuine early signal a real scheme is likely coming.
    Re-classified live (same reasoning as load_site_applications) rather
    than trusting each row's stored application_category/
    unit_confirmation_status, so this also picks up legacy rows scraped
    before the "screening_or_scoping_opinion" category or its
    "watchlist_only" unit_confirmation_status existed."""
    apps = session.execute(select(Application)).scalars().all()
    return [a for a in apps if classify_application_category(a.proposal) == "screening_or_scoping_opinion"]


def pick_representative_application(applications: list[Application]) -> Application | None:
    """The one application whose proposal/status/decision/portal-link best
    represents the site as a whole - prefer complete AI extraction, then the
    most recently received application."""
    def sort_key(a: Application):
        complete = bool(a.scheme_intelligence and a.scheme_intelligence.core_intelligence_complete)
        return (complete, parse_portal_date(a.application_received))

    return max(applications, key=sort_key, default=None)


def aggregate_scheme_fields(applications: list[Application]) -> dict:
    """First non-null value per field, scanning applications in the same
    priority order as pick_representative_application."""
    with_scheme = [a for a in applications if a.scheme_intelligence]
    ordered = sorted(
        with_scheme,
        key=lambda a: (a.scheme_intelligence.core_intelligence_complete, parse_portal_date(a.application_received)),
        reverse=True,
    )
    merged = {field: None for field in MERGED_SCHEME_FIELDS}
    for field in MERGED_SCHEME_FIELDS:
        for app in ordered:
            value = getattr(app.scheme_intelligence, field)
            if value not in (None, ""):
                merged[field] = value
                break
    merged["core_intelligence_complete"] = any(a.scheme_intelligence.core_intelligence_complete for a in ordered)

    # Fallback: if no linked application's AI extraction ever determined a
    # total unit count (either extraction hasn't run yet - no useful
    # documents found - or genuinely found none in the documents), fall back
    # to the portal search-listing's own regex-estimated count instead of
    # showing nothing. Confirmed real cases where a real number sat right in
    # the proposal text ("Construction of approx 200 new homes", "up to 200
    # dwellings") but the site showed a bare blank simply because no
    # document-level extraction had run for it yet. Less trustworthy than a
    # verified AI-extracted figure - hence the separate is_estimated flag so
    # the UI can caveat it - but a real, sourced number beats showing
    # nothing for a site the user is trying to evaluate.
    merged["total_units_is_estimated"] = False
    if merged["total_units_final"] is None:
        by_estimate = sorted(
            [a for a in applications if a.estimated_unit_count is not None],
            key=lambda a: parse_portal_date(a.application_received), reverse=True,
        )
        if by_estimate:
            merged["total_units_final"] = by_estimate[0].estimated_unit_count
            merged["total_units_is_estimated"] = True

    return merged


def credits_sidebar(session, settings) -> None:
    with st.sidebar:
        st.header("Credits")
        st.metric("Remaining", settings.credits_remaining)
        top_up = st.number_input("Add credits", min_value=0, value=0, step=10, label_visibility="collapsed")
        if st.button("Add credits") and top_up:
            settings.credits_remaining += top_up
            session.commit()
            st.rerun()
        st.caption("Personal spend-throttle for Apollo/Hunter/Companies House lookups - not real billing.")
        st.divider()


def render_visual_evidence(evidence: dict, *, missing_message: str, expander_label: str) -> None:
    """Shared rendering for both the Site Profile (Part 11) and Allocation
    (Part 12) "Visual Evidence" sections - evidence is the dict returned by
    app.visuals.site_view's build_site_visual_evidence/
    build_allocation_visual_evidence. Never prints a local file path (Part
    17) - image_path/thumbnail_path are only ever passed to st.image as a
    source, never shown as text - and never renders unsafe HTML (no
    unsafe_allow_html=True anywhere here, so an AI-written "reason" string
    can never inject markup)."""
    primary = evidence["primary"]
    if primary is None:
        st.caption(missing_message)
        return

    if primary.thumbnail_path and os.path.exists(primary.thumbnail_path):
        st.image(primary.thumbnail_path, width=320)
    # No broken-image placeholder (Part 11) - if the file is missing on
    # disk, the caption/metadata below still renders, just without the
    # image itself, rather than Streamlit's own broken-image icon.

    label = IMAGE_TYPE_LABELS.get(primary.image_type, primary.image_type)
    detail = label
    if primary.source_document_title:
        detail += f" — {primary.source_document_title}"
    if primary.source_page:
        detail += f", page {primary.source_page}"
    st.caption(detail)

    if primary.review_status == "confirmed":
        st.caption("✓ Confirmed by a human reviewer")
    else:
        confidence = f"{primary.extraction_confidence:.0%}" if primary.extraction_confidence is not None else "unknown"
        st.caption(f"⚠️ Not yet reviewed - AI classification confidence {confidence}")

    if primary.source_document_url:
        st.caption(f"[View source document]({primary.source_document_url})")

    others = evidence["others"]
    if others:
        with st.expander(f"{expander_label} ({len(others)})"):
            cols = st.columns(min(len(others), 4))
            for i, image in enumerate(others):
                with cols[i % len(cols)]:
                    if image.thumbnail_path and os.path.exists(image.thumbnail_path):
                        st.image(image.thumbnail_path, width=150)
                    other_label = IMAGE_TYPE_LABELS.get(image.image_type, image.image_type)
                    st.caption(other_label + (" ✓" if image.review_status == "confirmed" else " (unreviewed)"))


def render_scheme_detail(session, settings, site: Site, apps: list[Application]) -> None:
    """Full scheme detail block - application history, proposal/scheme
    fields, evidence, companies & contacts with on-demand unlock. Shared
    between the dedicated Scheme Detail page (app/ui/pages/1_Scheme_Detail.py)
    and the home page's inline expansion when a table row is clicked, so the
    two don't drift out of sync with each other."""
    rep_app = pick_representative_application(apps)
    merged = aggregate_scheme_fields(apps)
    has_scheme = any(a.scheme_intelligence for a in apps)

    st.subheader(site.display_address)
    st.caption(f"{site.council_code} — {len(apps)} linked application(s)")

    if site.excluded:
        st.error(
            f"🚫 Excluded from results — {site.excluded_reason or 'marked not a genuine residential scheme'} "
            f"({site.excluded_at.strftime('%d %b %Y') if site.excluded_at else 'date unknown'})"
        )
        if st.button("Un-exclude — restore to results"):
            site.excluded = False
            site.excluded_reason = None
            site.excluded_at = None
            session.commit()
            st.rerun()

    # Policy Intelligence (Part 12 of the Policy Intelligence Foundation
    # sprint) - every fact shown here carries its own source page/document
    # link (Part 13 traceability), never a summary detached from where it
    # came from. build_site_policy_intelligence is a pure function (see
    # app.policy.site_view) so this exact assembly is covered by
    # tests/test_site_policy_display.py independently of Streamlit.
    local_plan_entries = session.execute(
        select(LocalPlanSite).where(LocalPlanSite.matched_site_id == site.id)
    ).scalars().all()
    for entry, policy_row in zip(local_plan_entries, build_site_policy_intelligence(local_plan_entries)):
        confidence_bit = f" (match confidence {policy_row['match_confidence']:.0f}%)" if policy_row["match_confidence"] else ""
        page_link = (
            f" [Open plan page {policy_row['source_page']}]({policy_row['source_document_url']}#page={policy_row['source_page']})"
            if policy_row["source_document_url"] and policy_row["source_page"] else ""
        )
        capacity_bits = [
            f"{policy_row[k]} {label}" for k, label in (
                ("minimum_dwellings", "min"), ("indicative_capacity", "indicative"), ("maximum_capacity", "max"),
            ) if policy_row[k]
        ]
        capacity_text = " / ".join(capacity_bits) if capacity_bits else "dwelling count not stated"
        plan_status_text = policy_row["plan_raw_status"] or policy_row["plan_status"] or "status unknown"
        st.info(
            f"📋 Allocated in the **{policy_row['plan_name']}** ({plan_status_text}) as "
            f"**{policy_row['allocation_reference']} {policy_row['allocation_name']}** — {capacity_text}, "
            f"{policy_row['category'] or 'no category given'}{confidence_bit}.{page_link}"
        )
        st.caption(
            f"{PROGRESSION_SIGNAL_LABELS.get(policy_row['progression_signal'], PROGRESSION_SIGNAL_LABELS[None])}"
            + (f" — {'; '.join(policy_row['progression_reasons'])}" if policy_row["progression_reasons"] else "")
            + (f" · allocation status: {policy_row['allocation_raw_status'] or policy_row['allocation_status']}"
               if policy_row["allocation_status"] else "")
            + (f" · plan checked {policy_row['last_checked'].strftime('%d %b %Y')}" if policy_row["last_checked"] else "")
        )
        scope = assess_delivery_scope(entry.minimum_dwellings, merged.get("total_units_final"))
        if scope["status"] == "partial":
            st.warning(f"🔍 {scope['note']}")
        elif scope["status"] in ("full_site", "roughly_matches"):
            st.caption(f"✓ {scope['note']}")

    # site.applications (raw relationship), not the display-filtered `apps`
    # parameter - that filter drops administrative applications (condition
    # discharge, variation of condition) as noise for the "Application
    # history" list below, but those are exactly the evidence
    # classify_build_status's portal-filing signal (and phase_tracking's own
    # per-phase progress check) depend on to detect "underway". Confirmed a
    # real case: a site with 30 linked applications (10+ real condition-
    # discharge filings spanning years) showed "Permission may have lapsed"
    # here because compute_lapse_status never saw any of that evidence -
    # only the applications that survived the qualifying-scheme filter.
    lapse = compute_lapse_status(site.applications, site)
    phase_breakdown = build_phase_breakdown(site.applications)
    unstarted_phase_count = sum(1 for p in phase_breakdown if p["status"] == "approved_not_started")

    lapse_label = LAPSE_STATUS_LABELS[lapse["status"]]
    if lapse["deadline"]:
        granted_ref = lapse["granted_app"].reference if lapse["granted_app"] else "?"
        st.markdown(
            f"**Commencement status:** {lapse_label} — 3-year deadline "
            f"{lapse['deadline'].strftime('%d %b %Y')} (from {granted_ref}'s decision)"
        )
    else:
        st.markdown(f"**Commencement status:** {lapse_label}")

    st.markdown("**Site Plans and Visual Evidence**")
    render_visual_evidence(
        build_site_visual_evidence(session, site.id),
        missing_message="No confirmed Site plan image has been extracted yet.",
        expander_label="Other visual evidence",
    )

    if site.status_summary:
        # Weekly AI synthesis across every linked application - see
        # app.pipeline.run_weekly.stage_generate_scheme_summaries. Purely a
        # narrative layer over data already shown elsewhere on this page
        # (phase breakdown, application history, planning stage, expected
        # decision date).
        st.markdown("**AI status summary:**")
        st.markdown(site.status_summary)
        if site.status_summary_updated_at:
            st.caption(f"Generated {site.status_summary_updated_at.strftime('%d %b %Y')} from every linked application at the time.")

        # Both the expanded state and any pending result message are tracked
        # in session_state, not just returned inline - confirmed a real bug:
        # st.expander defaults to collapsed on every rerun, so a message
        # rendered inline inside it (the obvious first approach) gets
        # rendered then immediately hidden the instant st.rerun() fires,
        # since the expander snaps shut again before the user ever sees it.
        # Storing the message and reading+clearing it on the NEXT render
        # (with expanded forced True whenever one is pending) means it
        # actually survives the rerun that was needed to refresh the page's
        # other data (site.excluded, application history) after the change.
        expanded_key = f"review_expanded_{site.id}"
        message_key = f"review_message_{site.id}"
        pending_message = st.session_state.pop(message_key, None)
        with st.expander("Review this scheme", expanded=st.session_state.pop(expanded_key, False)):
            if pending_message:
                level, text = pending_message
                getattr(st, level)(text)
            st.caption(
                "Reading the summary above shows this isn't actually what it looks like on paper? "
                "Correct it here rather than leaving a wrong entry in the results."
            )
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Not a genuine residential scheme**")
                exclude_reason = st.text_area(
                    "Why", key=f"exclude_reason_{site.id}", label_visibility="collapsed",
                    placeholder="e.g. commercial-only despite portal keyword match",
                )
                if st.button("Exclude from results", key=f"exclude_btn_{site.id}"):
                    site.excluded = True
                    site.excluded_reason = exclude_reason or None
                    site.excluded_at = dt.datetime.now(dt.timezone.utc)
                    session.commit()
                    st.session_state[expanded_key] = True
                    st.session_state[message_key] = ("success", "Excluded - won't show up in results anymore.")
                    st.rerun()
            with col2:
                st.markdown("**Actually part of a different scheme**")
                parent_ref = st.text_input(
                    "Parent application reference", key=f"parent_ref_{site.id}", label_visibility="collapsed",
                    placeholder="e.g. A/12/76665 - must already be in the database",
                )
                if st.button("Link to that scheme", key=f"link_btn_{site.id}") and parent_ref:
                    st.session_state[expanded_key] = True
                    target = session.execute(
                        select(Application).where(
                            Application.council_code == site.council_code, Application.reference == parent_ref.strip(),
                        )
                    ).scalar_one_or_none()
                    if not target:
                        st.session_state[message_key] = ("error", f"No application {parent_ref!r} found for {site.council_code} - it needs to already be scraped.")
                    elif not target.site_id:
                        st.session_state[message_key] = ("error", f"{parent_ref} exists but isn't linked to a site itself yet - can't merge into it.")
                    elif target.site_id == site.id:
                        st.session_state[message_key] = ("warning", "That application is already part of this same site.")
                    else:
                        for a in site.applications:
                            a.site_id = target.site_id
                            a.site_link_method = "manual"
                        session.commit()
                        st.session_state[message_key] = ("success", f"Linked to {parent_ref}'s site.")
                    st.rerun()

    if phase_breakdown:
        unit_summary = summarize_phase_units(phase_breakdown)

        def _bucket_text(bucket: dict) -> str:
            n = bucket["phase_count"]
            if n == 0:
                return None
            phase_word = f"{n} phase{'s' if n != 1 else ''}"
            if bucket["units"]:
                unit_bit = f"{bucket['units']} units"
                if bucket["phases_with_known_units"] < n:
                    unit_bit += f" across {bucket['phases_with_known_units']} of {n} phases"
                    return f"{unit_bit} ({phase_word} total)"
                return f"{unit_bit} across {phase_word}"
            return f"{phase_word} (unit count not confirmed)"

        underway_text = _bucket_text(unit_summary["underway"])
        available_text = _bucket_text(unit_summary["approved_not_started"])
        awaiting_text = _bucket_text(unit_summary["not_yet_approved"])

        if underway_text:
            st.markdown(f"🏗️ **Under construction:** {underway_text}")
        if available_text:
            st.markdown(f"🎯 **Approved, not yet started:** {available_text}")
        if awaiting_text:
            st.markdown(f"⏳ **Awaiting decision:** {awaiting_text}")

        if unit_summary["approved_not_started"]["phase_count"]:
            # A single material operation anywhere on the site saves the
            # WHOLE permission from lapsing under UK planning law - there's
            # then no statutory deadline forcing the developer to start the
            # rest. That cuts both ways: it means "Build underway" is not a
            # signal the whole site is progressing, and - because there's no
            # legal urgency left pushing the developer to build out the
            # remaining phases - an unstarted phase can sit indefinitely
            # without them ever being forced to act, which if anything makes
            # it a more durable acquisition opportunity, not a
            # time-pressured one.
            st.info(
                "🎯 The phase(s) above with full planning permission but no start of works are a "
                "potential land-buying opportunity - and because a single material operation elsewhere "
                "on the site already protects the whole permission from lapsing, there's no legal "
                "deadline forcing the current developer to act on them. They could remain available "
                "indefinitely (see Phase & plot breakdown below for details)."
            )

    if merged.get("external_consultation_source"):
        st.warning(
            f"📋 This is a boundary consultation notice, not the substantive application — "
            f"the real scheme (including affordable housing details) is application "
            f"**{merged['external_consultation_source']}**, on that council's own planning portal. "
            f"Figures below are unresolved (not a genuine zero) until checked there."
        )

    if merged.get("affordable_status_note"):
        st.warning(f"⚠️ **Manual review needed:** {merged['affordable_status_note']}")

    if any(a.application_category == "reserved_matters" for a in apps):
        # Reaching reserved matters (detailed layout/scale/appearance/
        # landscaping) means someone has already committed real design cost
        # for this scheme - that essentially never happens speculatively
        # before land control is settled, so it's a strong signal the land
        # has already changed hands (or the original promoter is building it
        # out themselves). The pure land-acquisition opportunity is
        # therefore likely gone - but this is exactly the stage at which
        # forward-funding deals happen instead: registered providers
        # routinely acquire S106 affordable blocks, and PRS/BTR investors
        # forward-fund private blocks, once the detailed design is locked.
        # Reframe rather than hide the scheme.
        st.info(
            "🏗️ **Land opportunity likely closed** — this scheme has reached Reserved Matters stage, which "
            "means detailed design work has already been committed to (essentially never done speculatively "
            "before land control is settled). But this is exactly the stage at which forward-funding deals "
            "happen: affordable unit blocks are often available to registered providers, and private blocks "
            "to PRS/BTR investors, once the detailed design is locked."
        )

    with st.expander(f"Application history ({len(apps)})", expanded=len(apps) > 1):
        history_rows = [{
            "Reference": a.reference, "Type": a.application_type, "Status": a.status,
            "Decision": a.decision, "Received": a.application_received,
            "Link method": a.site_link_method, "Portal URL": a.summary_url,
        } for a in sorted(apps, key=lambda a: parse_portal_date(a.application_received), reverse=True)]
        st.dataframe(
            pd.DataFrame(history_rows), use_container_width=True,
            column_config={"Portal URL": st.column_config.LinkColumn()},
        )

    if phase_breakdown:
        phase_count = sum(1 for p in phase_breakdown if p["kind"] == "phase" and p["code"] != "Whole site / unphased")
        plot_count = sum(1 for p in phase_breakdown if p["kind"] == "plot")
        label_bits = []
        if phase_count:
            label_bits.append(f"{phase_count} phase{'s' if phase_count != 1 else ''}")
        if plot_count:
            label_bits.append(f"{plot_count} named plot{'s' if plot_count != 1 else ''}")
        label = f"Phase & plot breakdown ({', '.join(label_bits)}"
        label += f", {unstarted_phase_count} not yet started)" if unstarted_phase_count else ")"
        with st.expander(label, expanded=bool(unstarted_phase_count)):
            if unstarted_phase_count:
                st.info(
                    f"🎯 {unstarted_phase_count} group(s) have full planning permission but no "
                    f"commencement/discharge-of-conditions filing since - the main developer "
                    f"hasn't started these yet, a potential acquisition opportunity."
                )
            phase_rows = []
            for phase in phase_breakdown:
                grant = phase["latest_grant"]
                progress = phase["progress_filing"]
                units = phase.get("unit_count")
                units_display = str(units) if units else ("—" if phase["kind"] == "phase" else "")
                phase_rows.append({
                    "Phase / plot": phase["label"],
                    "Units": units_display,
                    "Status": PHASE_STATUS_LABELS[phase["status"]],
                    "Latest grant": f"{grant.reference} ({grant.decision_issued_date})" if grant else None,
                    "Latest progress filing": f"{progress.reference} ({progress.application_received})" if progress else None,
                    "Applications": len(phase["applications"]),
                })
            st.dataframe(pd.DataFrame(phase_rows), use_container_width=True, hide_index=True)
            if any(p.get("unit_count_source") == "portal_text" for p in phase_breakdown):
                st.caption(
                    "Units sourced from a phase application's own portal listing text where no "
                    "document extraction has run yet for it; — means no application in that "
                    "phase states its own unit count directly."
                )

    if not has_scheme:
        st.info("No AI extraction yet for this site's applications.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Address:** {site.display_address}")
            st.markdown(f"**Proposal:** {rep_app.proposal}")
            st.markdown(f"**Status / Decision:** {rep_app.status} / {rep_app.decision}")
            total_units_display = merged["total_units_final"]
            if merged.get("total_units_is_estimated") and total_units_display is not None:
                total_units_display = f"~{total_units_display} (est.)"
            st.markdown(f"**Total / Affordable / Private units:** {total_units_display} / "
                        f"{merged['affordable_units_final']} / {merged['private_units_final']}")
            if merged.get("total_units_is_estimated"):
                st.caption(
                    "ℹ️ No AI-verified unit count yet (no useful documents processed) - this is the portal "
                    "search listing's own estimate from the proposal text, not confirmed against the full application."
                )
            if merged["affordable_units_final"] in (0, None) and merged.get("affordable_classification_reason"):
                # A bare "0" reads as "no affordable housing required" - but
                # confirmed a real case where 0 actually meant "viability
                # assessment may reduce a stated 20% obligation to zero", a
                # very different (and less certain) situation. Blank/None
                # deserves the same treatment - confirmed a real case
                # (PA/2026/0539) where a stated-but-unconfirmed 20% target
                # was left unresolved rather than shown as a confident 0 (see
                # the manual-review warning above), and the reason explains
                # why. The reason is already captured (see Evidence below)
                # but was easy to miss sitting in a collapsed expander below
                # the figure it explains - surface it right next to the
                # number instead.
                st.caption(f"ℹ️ {merged['affordable_classification_reason']}")
            st.markdown(f"**Affordable tenure split:** {merged['affordable_tenure_split_final']}")
            st.markdown(f"**Development type:** {merged['development_type']}")
            st.markdown(f"**Build status:** {BUILD_STATUS_LABELS[lapse['build_status']]}")
            if lapse["build_status"] == "no_completions_yet":
                st.caption(
                    "ℹ️ An EPC is only lodged near practical completion, so this only means no unit here has "
                    "finished yet - construction could genuinely be well underway with no EPCs lodged and no "
                    "portal filing on record. Treat this as \"not confirmed complete\", not \"confirmed unstarted\"."
                )
            if merged["affordable_units_final"] and merged["total_units_final"]:
                st.markdown(f"**Affordable %:** {merged['affordable_percentage_final']}%")
            if lapse["granted_app"] and lapse["granted_app"].decision_issued_date:
                st.markdown(f"**Decision date:** {lapse['granted_app'].decision_issued_date}")
            if rep_app.summary_url:
                st.markdown(f"[View on planning portal]({rep_app.summary_url})")
        with col2:
            st.markdown(f"**Developer:** {merged['developer']}")
            if not merged["developer"] and merged.get("entity_relationship_notes"):
                # Applicant != developer in general (very often the
                # "applicant" on a portal is just the planning agent/
                # consultant submitting on someone else's behalf) - a blank
                # Developer field with no context reads as "not found" when
                # it might actually be "checked the documents, genuinely
                # couldn't verify who's building this, here's why".
                st.caption(f"ℹ️ {merged['entity_relationship_notes']}")
            st.markdown(f"**Applicant company:** {merged['applicant_company']}")
            st.markdown(f"**Landowner:** {merged['landowner']}")
            st.markdown(f"**Planning agent:** {merged['planning_agent']}")
            rp_display = merged["registered_provider"]
            if not rp_display:
                # A blank RP field alone can't distinguish "no RP involved"
                # from "an RP is promised but hasn't been named yet" - the
                # documents often just say "to be transferred to a
                # Registered Provider" with the actual RP confirmed later
                # via the S106's nomination procedure, which reads very
                # differently to a lead-sourcing user.
                rp_note = {
                    "not_yet_confirmed": "Not yet confirmed — nomination procedure only",
                    "not_applicable": "N/A — no affordable housing component",
                }.get(merged["registered_provider_status"])
                rp_display = rp_note or "None"
            st.markdown(f"**Housing association / RP:** {merged['housing_association'] or 'None'} / {rp_display}")
            st.markdown(f"**Data quality:** {merged['data_quality_status']}")

        with st.expander("Evidence"):
            st.markdown(f"**Affordable classification reason:** {merged['affordable_classification_reason']}")
            st.markdown(f"**Affordable evidence:** {merged['affordable_classification_evidence']}")
            st.markdown(f"**Site evidence:** {merged['site_evidence']}")

    st.divider()
    st.subheader("Companies & contacts")

    app_ids = [a.id for a in apps]
    links = session.execute(
        select(ApplicationCompany, Company).join(Company).where(ApplicationCompany.application_id.in_(app_ids))
    ).all()

    # Keyed by (role, normalised company name) rather than just role - a
    # joint applicant splits into multiple candidates under the SAME role
    # below, and a plain per-role dict would only ever surface one of them
    # once enriched (setdefault silently drops every company after the
    # first found for that role).
    enriched_by_key: dict[tuple[str, str], Company] = {}
    for link, company in links:
        enriched_by_key.setdefault((link.role, companies_house.normalise_name(company.name_raw)), company)

    # Candidates come from the AI-extracted names on the merged scheme, not
    # just already-enriched links - enrichment is on-demand, so most sites
    # will have a candidate name here with no Company row yet until you
    # unlock it. Each name is split into separate joint-applicant candidates
    # (see split_joint_companies) - confirmed a real case ("MCI Developments
    # and JS Hennessey (1999) RBS") where treating a joint applicant as one
    # company name meant CH/website lookups searched for a name matching no
    # real single company, silently mis-enriching both.
    ROLE_FIELDS = [
        ("applicant", "applicant_company"), ("developer", "developer"), ("landowner", "landowner"),
        ("housing_association", "housing_association"), ("registered_provider", "registered_provider"),
    ]
    seen_names = set()
    candidates = []
    for role, field in ROLE_FIELDS:
        name = merged.get(field)
        if not name:
            continue
        for split_name in companies_house.split_joint_companies(name):
            if split_name.strip().lower() in seen_names:
                continue
            seen_names.add(split_name.strip().lower())
            candidates.append((role, split_name))

    if not candidates:
        st.info("No applicant/developer/landowner names extracted yet for this site.")

    for role, name in candidates:
        company = enriched_by_key.get((role, companies_house.normalise_name(name)))
        st.markdown(f"#### {name}  —  _{role}_")

        if company is None:
            if settings.credits_remaining <= 0:
                st.warning("No contacts unlocked yet. Add credits in the sidebar to unlock.")
            elif st.button("Unlock contacts (1 credit)", key=f"unlock_{site.id}_{role}_{name}"):
                ch_key = os.getenv("CH_API_KEY")
                if not ch_key:
                    st.error("CH_API_KEY not set in .env.")
                else:
                    with st.spinner(f"Enriching {name}..."):
                        openai_key = os.getenv("OPENAI_API_KEY")
                        result = enrich_company(
                            name, ch_key, os.getenv("SERPAPI_KEY"), os.getenv("APOLLO_API_KEY"), os.getenv("HUNTER_API_KEY"),
                            openai_client=OpenAI(api_key=openai_key) if openai_key else None,
                            site_address=site.display_address, proposal_summary=rep_app.proposal if rep_app else None,
                        )
                        company = upsert_company_from_enrichment(session, name, result)
                        session.add(ApplicationCompany(application_id=rep_app.id, company_id=company.id, role=role))
                        settings.credits_remaining -= 1
                        session.commit()
                    st.rerun()
            continue

        if company.domain_matched_via_parent and (company.domain_source or "").endswith("_officer"):
            domain_note = f" via director's other company {company.domain_matched_via_parent!r}"
        elif company.domain_matched_via_parent:
            domain_note = f" via parent {company.domain_matched_via_parent!r}"
        else:
            domain_note = ""
        source_note = f", source={company.domain_source}" if company.domain_source else ""
        st.caption(
            f"Companies House: {company.ch_company_number or 'not matched'} "
            f"({company.ch_status or 'n/a'}) | Website: {company.verified_domain or 'not found'} "
            f"({company.domain_verification_status or 'n/a'}{domain_note}{source_note})"
        )

        pscs = session.execute(
            select(PersonWithSignificantControl).where(
                PersonWithSignificantControl.company_id == company.id,
                PersonWithSignificantControl.ceased.is_(False),
            )
        ).scalars().all()
        if pscs:
            # PSC = who actually owns/controls the company (Companies House's
            # own beneficial-ownership register) - a materially different,
            # more authoritative question than "who is a named director".
            # Confirmed a real case: the only director owned 0% of the
            # company; the real owner (75-100% shares/voting rights, right
            # to appoint/remove directors) wasn't a director at all.
            st.markdown("**Owner (Persons with Significant Control):**")
            for psc in pscs:
                if psc.kind == "individual":
                    st.write(f"👤 {psc.name} — {psc.natures_of_control or 'nature of control not stated'}")
                else:
                    # Corporate/legal-entity PSC - the owner is itself a
                    # company, which could be looked up in turn to trace the
                    # chain further (not done automatically here).
                    extra = f" (CH# {psc.identification_company_number})" if psc.identification_company_number else ""
                    st.write(f"🏢 {psc.name}{extra} — {psc.natures_of_control or 'nature of control not stated'}")

        contacts = session.execute(select(Contact).where(Contact.company_id == company.id)).scalars().all()
        if not contacts:
            # Apollo/Hunter search by verified DOMAIN and can come back
            # empty (wrong/unverifiable domain, no web presence, etc.) even
            # when Companies House already gave us a real name to work with
            # - officers are fetched during every enrichment regardless of
            # domain status, so show them as a fallback lead rather than a
            # dead-end "no contacts found" with nothing actionable.
            officers = session.execute(select(Officer).where(Officer.company_id == company.id)).scalars().all()
            if officers:
                if company.verified_domain and company.domain_verification_status != "verified":
                    # Confirmed a real case (Peel Land Developments Limited,
                    # matched to vat-search.co.uk): "review" status means the
                    # website match itself wasn't trusted, so Apollo/Hunter
                    # were deliberately never searched at all (see
                    # contact_pipeline.enrich_company) - a director later
                    # turned out to be easily findable on LinkedIn by hand,
                    # proving the gap was a wrong domain match, not an
                    # absence of real contacts. Saying "no contacts found"
                    # here would misrepresent a skipped search as a completed
                    # one that came up empty.
                    st.write(
                        f"Website match for this company wasn't confident enough to search "
                        f"(\"{company.verified_domain}\" — {company.domain_verification_status}), so "
                        f"Apollo/Hunter were skipped rather than searched against a possibly-wrong domain. "
                        f"Companies House lists these officers:"
                    )
                else:
                    st.write("No Apollo/Hunter contacts found, but Companies House lists these officers:")
                officer_rows = [{
                    "Name": o.full_name, "Role": o.role,
                    "Appointed": o.appointed_on, "Resigned": o.resigned_on or "current",
                    "Also director of": o.other_appointments or "",
                } for o in officers if not o.resigned_on]
                if officer_rows:
                    st.dataframe(pd.DataFrame(officer_rows), use_container_width=True, hide_index=True)
                else:
                    st.write("(All listed officers have since resigned.)")
            else:
                st.write("Unlocked, but no contacts or officers were found for this company.")
        else:
            contact_rows = [{
                "id": c.id, "Name": c.full_name, "Title": c.job_title, "Email": c.email, "Phone": c.phone,
                "LinkedIn": c.linkedin_url, "Source": c.source, "Source URL": c.source_url,
                "Match score": c.match_score, "Verification": c.verification_status,
                "Outreach status": c.outreach_status or "not_contacted", "Suppressed": c.suppressed,
                "Context": c.source_context,
            } for c in contacts]

            edited = st.data_editor(
                pd.DataFrame(contact_rows).set_index("id"),
                key=f"contacts_{site.id}_{company.id}",
                use_container_width=True,
                column_config={
                    "LinkedIn": st.column_config.LinkColumn(display_text="View profile"),
                    "Source URL": st.column_config.LinkColumn(display_text="View source"),
                    "Outreach status": st.column_config.SelectboxColumn(
                        options=["not_contacted", "contacted", "interested", "rejected"]
                    ),
                    "Suppressed": st.column_config.CheckboxColumn(),
                },
                disabled=["Name", "Title", "Email", "Phone", "LinkedIn", "Source", "Source URL",
                          "Match score", "Verification"],
            )

            if st.button("Save changes", key=f"save_{site.id}_{company.id}"):
                for contact_id, row in edited.iterrows():
                    contact = session.get(Contact, int(contact_id))
                    contact.outreach_status = row["Outreach status"]
                    contact.suppressed = bool(row["Suppressed"])
                session.commit()
                st.success("Saved.")
                st.rerun()
