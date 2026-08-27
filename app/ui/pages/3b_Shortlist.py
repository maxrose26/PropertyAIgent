"""Shortlist review + CSV/PDF export (Site Selection & Reporting V1 Gates 2-4)
- shows the allocations added to the session-only shortlist (app.ui.shortlist)
together, so a user can review them as a group and export a deterministic
opportunity dataset, optionally enriched with Gate 4's AI Executive
Intelligence.

Deliberately NOT a full report or an analytics dashboard: no new scoring,
ranking, or charts - concise party-evidence signal only (Applicant/Developer/
a count of other ownership evidence), with full per-allocation detail
remaining one click away on Allocation Detail, exactly as Gate 1 already
established.

Data reuse (Gate 2/3): consumes app.reporting.allocation_report.
build_allocation_report_context - the SAME deterministic report context the
CSV export, the Gate 3 deterministic PDF, AND Gate 4's AI Executive
Intelligence (app.reporting.allocation_report_pdf.render_allocation_report_pdf)
all read from - rather than a separate query path per surface (see that
module's own docstring). Replaces Gate 1's build_allocation_discovery +
per-card get_allocation_summary reuse now that the batched, purpose-built
report-context builder exists; party/ownership evidence (omitted in Gate 1
because the underlying batching didn't exist yet) is now shown, backed by
app.reporting.ownership_control.get_allocations_control_intelligence's
batched entrypoint - a single query across every shortlisted allocation's
related Sites, never one query per allocation. The PDF renderer itself
performs zero additional queries - context is built exactly once above and
drives review, CSV, and both PDF variants alike.

Gate 4 UX (Section 24) - AI Executive Intelligence is NEVER generated
automatically on page load/rerun; it requires an explicit "Generate AI
Intelligence Report" click (Section 24's own instruction). The deterministic
Gate 3 PDF button above stays completely independent and always available,
regardless of whether AI generation has ever been run or whether it failed -
see the AI section's own try/except-free reliance on generate_cross_site_
intelligence's own internal never-raises contract."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st
from openai import OpenAI

from app.config import load_councils
from app.reporting.allocation_discovery import ALLOCATION_REVIEW_STATUS_META, PLAN_STATUS_META
from app.reporting.allocation_report import build_allocation_report_context, to_csv_bytes
from app.reporting.allocation_report_pdf import allocation_report_pdf_filename, render_allocation_report_pdf
from app.reporting.allocation_web_research import build_allocation_web_research_context
from app.reporting.cross_site_intelligence import generate_cross_site_intelligence
from app.ui.common import bootstrap, credits_sidebar, get_db
from app.ui.shell import empty_state, page_header, stat_tile, status_badge_row, wide_canvas
from app.ui.shortlist import SHORTLIST_SESSION_KEY, clear_shortlist, remove_candidate, shortlist_items

# Session-state key for the last-generated Gate 4 result (Section 24 - "keep
# it simple... do not introduce complex caching architecture"). Holds a
# plain dict {allocation_ids, result, web_evidence} or is absent entirely -
# never persisted, never survives a browser refresh/new session, exactly
# like the shortlist itself (app.ui.shortlist).
AI_INTELLIGENCE_SESSION_KEY = "_shortlist_ai_intelligence"


def _council_domains_for(context) -> frozenset[str]:
    """Best-effort council domain set for app.reporting.allocation_web_
    research's official-source tier classification - built from app.config.
    load_councils()'s own already-configured website/base_url fields for
    every council represented in this shortlist. Never fetched over the
    network, never guessed - a council with neither field configured simply
    contributes nothing (the generic .gov.uk/planningportal.co.uk suffix
    check in allocation_web_research still applies regardless)."""
    from urllib.parse import urlparse

    councils = load_councils()
    domains: set[str] = set()
    for code in {e.council_code for e in context.entries}:
        council = councils.get(code)
        if not council:
            continue
        for raw_url in (council.website, council.base_url):
            if not raw_url:
                continue
            netloc = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}").netloc.lower()
            netloc = netloc[4:] if netloc.startswith("www.") else netloc
            if netloc:
                domains.add(netloc)
    return frozenset(domains)

bootstrap()
session, settings = get_db()

credits_sidebar(session, settings)
wide_canvas()

LOCAL_PLAN_PAGE = Path(__file__).resolve().parent / "3_Local_Plan_Sites.py"
st.page_link(LOCAL_PLAN_PAGE, label="← Back to Allocation Discovery", icon="🔙")

page_header(
    "Shortlist",
    "Allocations you've added to your shortlist this session, together in one place.",
    icon="⭐",
)

st.session_state.setdefault(SHORTLIST_SESSION_KEY, {})
candidates = shortlist_items(st.session_state[SHORTLIST_SESSION_KEY], "allocation")
# Deterministic display order (allocation_selector.py precedent: never rely
# on dict-insertion order as if it were meaningful) - alphabetical by the
# display_name captured at add-time, id as the final tie-breaker.
candidates = sorted(candidates, key=lambda c: (c.display_name.lower(), c.candidate_id))

if not candidates:
    empty_state(
        "No allocations shortlisted yet",
        "Add opportunities from Allocation Discovery - open Local Plan Sites, filter to a population you're "
        "interested in, and use \"Add to shortlist\" on any allocation card or its detail page.",
        icon="⭐", cta_label="Browse Allocation Discovery", cta_page="pages/3_Local_Plan_Sites.py",
    )
    st.stop()

st.caption(f"{len(candidates)} allocation{'s' if len(candidates) != 1 else ''} shortlisted.")

# Site Selection & Reporting V1 Gate 2 - ONE deterministic report context,
# built fresh from current trusted data, powers both this review surface
# and the CSV export below - never a separate query path per consumer (see
# app.reporting.allocation_report's own module docstring).
context = build_allocation_report_context(session, [c.candidate_id for c in candidates])
entries_by_id = {entry.allocation_id: entry for entry in context.entries}

action_col1, action_col2, action_col3 = st.columns(3)
with action_col1:
    if st.button("Clear shortlist", key="shortlist-clear-all"):
        st.session_state[SHORTLIST_SESSION_KEY] = clear_shortlist(st.session_state[SHORTLIST_SESSION_KEY])
        st.rerun()
with action_col2:
    # Gate 2 CSV UX (Section 23) - a clear, deterministic export action; the
    # user downloads exactly the currently shortlisted allocation set, no
    # more, no less (context.entries is built from these exact candidate
    # ids).
    st.download_button(
        f"Download shortlist CSV ({len(context.entries)} allocation{'s' if len(context.entries) != 1 else ''})",
        data=to_csv_bytes(context), file_name="allocation_shortlist.csv", mime="text/csv",
        key="shortlist-download-csv", use_container_width=True,
    )
with action_col3:
    # Gate 3 PDF report - rendered from the SAME `context` object already
    # built above for this page and the CSV export, never a second query
    # path (app.reporting.allocation_report_pdf's own module docstring: a
    # pure renderer, zero database queries). Deliberately un-cached, same
    # as the CSV button above - render_allocation_report_pdf performs no
    # I/O of its own (pure in-memory ReportLab layout over already-fetched
    # data), so it costs nothing extra beyond what building `context`
    # already cost; adding a caching layer here would be complexity this
    # gate has no measured need for.
    st.download_button(
        "Download shortlist PDF report",
        data=render_allocation_report_pdf(context), file_name=allocation_report_pdf_filename(context),
        mime="application/pdf", key="shortlist-download-pdf", use_container_width=True,
    )

# Site Selection & Reporting V1 Gate 4 - AI Executive Intelligence (Section
# 24). Deliberately behind an explicit button, never run on page load/
# rerun - bounded web research + one cross-site synthesis call cost real
# time and OpenAI spend, unlike the CSV/deterministic-PDF buttons above.
with st.expander("🧠 Generate AI Intelligence Report", expanded=False):
    st.caption(
        "Runs bounded external web research across this shortlist, then one AI synthesis call comparing the "
        "allocations as a whole. Supplements - never replaces - the deterministic report above; always re-verify "
        "against primary sources before an acquisition or planning decision."
    )
    current_allocation_ids = tuple(sorted(entry.allocation_id for entry in context.entries))

    if st.button("Generate AI Intelligence Report", key="shortlist-generate-ai-intelligence"):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            st.error("OPENAI_API_KEY not set in .env.")
        else:
            client = OpenAI(api_key=api_key)
            with st.spinner("Researching public web evidence and generating executive intelligence…"):
                council_domains = _council_domains_for(context)
                web_evidence = build_allocation_web_research_context(client, context, council_domains=council_domains)
                ai_result = generate_cross_site_intelligence(client, context, web_evidence)
            st.session_state[AI_INTELLIGENCE_SESSION_KEY] = {
                "allocation_ids": current_allocation_ids, "result": ai_result, "web_evidence": web_evidence,
            }
            st.rerun()

    cached = st.session_state.get(AI_INTELLIGENCE_SESSION_KEY)
    if cached is None:
        st.caption("Not yet generated for this shortlist.")
    elif cached["allocation_ids"] != current_allocation_ids:
        st.info("The shortlist has changed since AI Executive Intelligence was last generated - click above to regenerate.")
    else:
        ai_result, web_evidence = cached["result"], cached["web_evidence"]
        if ai_result.status == "ok":
            evidence_count = len(web_evidence.all_evidence())
            st.success(
                f"AI Executive Intelligence generated - {evidence_count} external web source"
                f"{'s' if evidence_count != 1 else ''} found."
                + (f" ({len(web_evidence.failures)} research step(s) did not return results.)" if web_evidence.failures else "")
            )
            st.markdown(f"**Executive summary:** {ai_result.intelligence.executive_summary}")
            st.download_button(
                "Download AI Intelligence PDF report",
                data=render_allocation_report_pdf(context, executive_intelligence=ai_result.intelligence, web_evidence=web_evidence),
                file_name=allocation_report_pdf_filename(context, ai_enhanced=True),
                mime="application/pdf", key="shortlist-download-ai-pdf", use_container_width=True,
            )
        elif ai_result.status == "rejected":
            # Grounding validation failed (Section 35) - never publish an
            # ungrounded AI section, never expose the raw rejection reasons
            # (internal validator detail) to the customer-facing UI; the
            # deterministic PDF above remains fully available regardless.
            st.warning(
                "AI Executive Intelligence could not be generated safely for this shortlist this time - the "
                "deterministic PDF report above remains fully available. You can try generating again."
            )
        else:  # status == "error" - an API/network failure, never a raw exception string shown to the user
            st.warning(
                "AI Executive Intelligence generation did not complete (a temporary issue) - the deterministic "
                "PDF report above remains fully available. You can try generating again."
            )

st.divider()

for candidate in candidates:
    entry = entries_by_id.get(candidate.candidate_id)

    if entry is None:
        # Stale/missing candidate (Gate 1 Section 10, unchanged) - never
        # crash, never silently drop it from the shortlist on our own
        # initiative; show it as unavailable and let the user remove it
        # explicitly. Driven by context.excluded now rather than a missing
        # build_allocation_discovery card, same user-facing behaviour.
        with st.container(border=True, key=f"shortlist-missing-{candidate.candidate_id}"):
            st.markdown(f"**{candidate.display_name}**")
            st.caption("This allocation is no longer available - it may have been removed or reclassified.")
            if st.button("Remove from shortlist", key=f"shortlist-remove-missing-{candidate.candidate_id}"):
                st.session_state[SHORTLIST_SESSION_KEY] = remove_candidate(
                    st.session_state[SHORTLIST_SESSION_KEY], "allocation", candidate.candidate_id,
                )
                st.rerun()
        continue

    with st.container(border=True, key=f"shortlist-card-{entry.allocation_id}"):
        header_cols = st.columns([5, 1])
        with header_cols[0]:
            st.markdown(f"##### {entry.allocation_name}")
            context_bits = [b for b in (entry.council_name, entry.local_plan_name, entry.allocation_reference) if b]
            st.caption(" · ".join(str(b) for b in context_bits))
        with header_cols[1]:
            if st.button("Remove", key=f"shortlist-remove-{entry.allocation_id}", use_container_width=True):
                st.session_state[SHORTLIST_SESSION_KEY] = remove_candidate(
                    st.session_state[SHORTLIST_SESSION_KEY], "allocation", entry.allocation_id,
                )
                st.rerun()

        status_badge_row([
            (PLAN_STATUS_META.get(entry.plan_status, PLAN_STATUS_META[None])["chip_kind"], entry.plan_status_label),
            (ALLOCATION_REVIEW_STATUS_META.get(entry.review_status, ALLOCATION_REVIEW_STATUS_META[None])["badge_kind"], entry.review_status_label),
        ])

        info_cols = st.columns(4)
        with info_cols[0]:
            stat_tile("Intended use", entry.intended_use_label)
        with info_cols[1]:
            stat_tile("Capacity", entry.capacity_display)
        with info_cols[2]:
            stat_tile(
                "Development coverage",
                f"{entry.development_coverage_percentage:.0%}" if entry.development_coverage_percentage is not None else "Not determined",
            )
        with info_cols[3]:
            stat_tile(
                "Indicative residual",
                f"~{entry.indicative_residual_capacity:,}" if entry.indicative_residual_capacity else "Not determined",
            )

        # Evidence-bounded wording (Gate 1 Section 14, unchanged) - no
        # warning/error styling solely because no application is linked;
        # no linked Application is a valid intelligence state.
        if entry.linked_application_count:
            st.caption(f"{entry.linked_application_count} linked planning application(s) identified.")
        else:
            st.caption("No linked planning application has been identified.")

        # Gate 2 - concise party-evidence signal only (Section 18: "keep
        # the page concise... full detail remains in Allocation Detail").
        # Applicant and Developer are always shown as separate, never
        # conflated - Applicant-only evidence is never promoted to
        # Developer (Section 10).
        applicant_names = sorted({e.entity_name for e in entry.applicant_evidence})
        if applicant_names:
            st.caption(f"**Applicant:** {', '.join(applicant_names)}")

        # Pre-merge semantic hardening (Gate 2 amendment) - trusted and
        # needs_review Developer evidence are never shown on the same line.
        # A needs_review "Developer" claim must not read as settled fact
        # merely because it shares the bolded "Developer:" caption with a
        # trusted one (Section 6/7) - it gets its own, plainly-worded,
        # unbolded line instead.
        trusted_developer_names = sorted(
            {e.entity_name_raw for e in entry.trusted_ownership_evidence if e.role == "DEVELOPER"}
        )
        if trusted_developer_names:
            st.caption(f"**Developer:** {', '.join(trusted_developer_names)}")

        pending_developer_names = sorted(
            {e.entity_name_raw for e in entry.review_pending_ownership_evidence if e.role == "DEVELOPER"}
        )
        if pending_developer_names:
            st.caption(f"Developer evidence pending confirmation: {', '.join(pending_developer_names)}")

        other_ownership_count = sum(1 for e in entry.ownership_evidence if e.role != "DEVELOPER")
        if other_ownership_count:
            st.caption(
                f"{other_ownership_count} other ownership/control evidence item(s) identified - "
                "see Allocation Detail for full evidence."
            )

        if entry.ai_intelligence.available:
            st.markdown(f"**AI Allocation Intelligence:** {entry.ai_intelligence.headline}")
        else:
            st.caption("AI allocation summary not yet generated.")

        st.page_link(
            "pages/3_Local_Plan_Sites.py", label="Open full allocation detail →",
            query_params={"allocation_id": str(entry.allocation_id)},
        )
