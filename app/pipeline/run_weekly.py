"""Weekly pipeline entrypoint.

    python -m app.pipeline.run_weekly --council bury

Runs, in order, for one council:
  1. Scrape stage        - search the portal for a date range, filter to
                           qualifying (10+ unit) applications, upsert into `applications`.
  2. Parent-lookup stage - for any reserved matters filing citing a parent
                           outline/full permission we haven't scraped (often
                           because it predates our scraping window), fetch
                           that ONE application by exact reference so its own
                           documents (S106, affordable housing statement...)
                           are available to merge in via site-linking.
  3. Site-link stage     - consolidate applications that refer to the same
                           physical site (see app.pipeline.site_linking).
  4. Document stage      - for any qualifying application with no documents yet,
                           discover + download + extract text.
  5. Extraction stage    - for any application with documents but no
                           scheme_intelligence yet, run the AI extraction pipeline.
  6. Geocode stage        - plot any un-geocoded site's postcode to lat/lon
                           (postcodes.io, free, no key) for the map view.
  7. Build-status stage   - for decided/approved sites, check EPC Open Data
                           for signs of completion (needs EPC_API_KEY).
  8. Enrichment stage    - OFF by default. Contact enrichment (Companies
                           House + website + Apollo/Hunter) is meant to be
                           triggered on demand from the Streamlit "Unlock
                           contacts" button now, not run blind against every
                           scraped scheme - pass --enrich to still do it here.

Each stage only processes what the previous run didn't finish, so re-running
this command is always safe and makes forward progress (resumable).
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import time
from collections import Counter

import requests
from dotenv import load_dotenv
from openai import OpenAI
from playwright.sync_api import sync_playwright
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import CouncilConfig, get_council
from app.db.models import Application, ApplicationCompany, Council, Document, SchemeIntelligence, Site
from app.db.session import get_session, init_db
from app.enrichment.contact_pipeline import enrich_company, upsert_company_from_enrichment
from app.enrichment.epc_lookup import NOMINATIM_MIN_INTERVAL_SECONDS, check_build_status, geocode_address, geocode_postcode
from app.extraction.pdf_text import (
    USEFUL_DOC_TYPES,
    clean_document_text,
    document_dir,
    download_document,
    extract_document_text,
    name_is_uninformative,
    sniff_document_type_from_text,
    standardise_document_type,
)
from app.extraction.run_extraction import run_extraction_for_application
from app.pipeline.lapse_tracking import PROGRESS_SIGNAL_CATEGORIES, is_granted_decision
from app.pipeline.site_linking import extract_parent_reference, link_application_to_site
from app.scrapers.documents import discover_documents
from app.scrapers.arcus_portal import fetch_application_by_reference as fetch_application_by_reference_arcus
from app.scrapers.arcus_portal import scrape_month as scrape_month_arcus
from app.scrapers.idox_portal import HEADERS, generate_month_ranges, keyval_from_url
from app.scrapers.idox_portal import fetch_application_by_reference as fetch_application_by_reference_idox
from app.scrapers.idox_portal import fetch_application_detail, search_related_applications
from app.scrapers.idox_portal import scrape_month as scrape_month_idox
from app.scrapers.unit_filter import classify_application_category, extract_unit_counts, qualify

# Applications only reach stage_documents/stage_extraction if their unit
# count was either confirmed by the portal-text regex at scrape time
# (unit_confirmation_status left null) or confirmed by stage_confirm_units
# (set to confirmed_qualifying) - never confirmed_disqualified/undetermined.
UNIT_GATE_PASSED = or_(
    Application.unit_confirmation_status.is_(None),
    Application.unit_confirmation_status == "confirmed_qualifying",
)

MONTH_COOLDOWN_SECONDS = 10  # pause between months on a multi-month backfill, some portals rate-limit hard

FIELD_MAP = {
    "reference": "Reference",
    "alternative_reference": "Alternative Reference",
    "address": "Address",
    "proposal": "Proposal",
    "application_type": "Application Type",
    "status": "Status",
    "decision": "Decision",
    "decision_issued_date": "Decision Issued Date",
    "application_received": "Application Received",
    "application_validated": "Application Validated",
    "ward": "Ward",
    "case_officer": "Case Officer",
    "applicant_name_raw": "Applicant Name",
    "applicant_address_raw": "Applicant Address",
}


def ensure_council_row(session: Session, council: CouncilConfig) -> None:
    existing = session.get(Council, council.code)
    if existing:
        return
    session.add(
        Council(
            code=council.code, name=council.name, base_url=council.base_url,
            date_field_mode=council.date_field_mode, doc_system=council.doc_system,
            anite_base_url=council.anite_base_url, unit_threshold=council.unit_threshold,
            region=council.region, country=council.country,
        )
    )
    session.commit()


def _scrape_month_for_council(page, council: CouncilConfig, date_from: str, date_to: str):
    if council.doc_system == "arcus":
        # month_ranges are always produced as DD/MM/YYYY (Idox's own form
        # format) - Arcus's URL-encoded search filter needs ISO YYYY-MM-DD.
        iso_from = dt.datetime.strptime(date_from, "%d/%m/%Y").strftime("%Y-%m-%d")
        iso_to = dt.datetime.strptime(date_to, "%d/%m/%Y").strftime("%Y-%m-%d")
        return scrape_month_arcus(page, council, iso_from, iso_to)
    return scrape_month_idox(page, council, date_from, date_to)


def stage_scrape(session: Session, page, council: CouncilConfig, date_from: str, date_to: str, batch_id: str) -> int:
    print(f"\n[scrape] {council.code} {date_from} -> {date_to}")
    scraped = _scrape_month_for_council(page, council, date_from, date_to)
    qualifying = [a for a in scraped if a.qualifies and a.reference]

    # condition_discharge_or_details applications (discharge of conditions,
    # commencement notices...) are correctly excluded as qualifying schemes
    # in their own right - they're not new development proposals - but a
    # developer doesn't discharge pre-commencement conditions for a phase
    # they have no intention of starting imminently, so they're the clearest
    # portal-native evidence available that construction has actually begun
    # on a phase of an already-tracked site. Only capture them when they cite
    # a reference we already track, so this doesn't flood the DB with
    # irrelevant admin filings for sites we don't care about.
    known_refs = {
        row[0] for row in session.execute(
            select(Application.reference).where(Application.council_code == council.code)
        ).all()
    }
    progress_signals = [
        a for a in scraped
        if not a.qualifies and a.reference
        and a.application_category == "condition_discharge_or_details"
        and extract_parent_reference(a.fields.get("Proposal", "")) in known_refs
    ]

    # A screening/scoping opinion isn't a qualifying scheme in its own right
    # (no real applicant/documents behind it yet - see unit_filter's
    # EXCLUDE_CATEGORIES) so it's correctly excluded from the main results,
    # but it's still a genuine early signal that a real scheme is likely
    # coming - confirmed real cases where a screening opinion preceded a
    # site's actual qualifying application by months. Saved with
    # unit_confirmation_status="watchlist_only" (same treatment as
    # progress-signal filings) so it never enters document download/AI
    # extraction, but stays discoverable for the UI's "Ones to watch" list
    # rather than being discarded at scrape time entirely.
    watchlist = [a for a in scraped if not a.qualifies and a.reference and a.application_category == "screening_or_scoping_opinion"]

    print(f"[scrape] {len(scraped)} applications checked, {len(qualifying)} qualify, "
          f"{len(progress_signals)} progress-signal filings for known sites, "
          f"{len(watchlist)} screening/scoping opinions saved to watchlist")

    for app in qualifying + progress_signals + watchlist:
        if app in progress_signals:
            status = "progress_signal_only"
        elif app in watchlist:
            status = "watchlist_only"
        else:
            status = None
        _upsert_scraped_application(session, council, app, batch_id, unit_confirmation_status=status)

    session.commit()
    return len(qualifying)


def _upsert_scraped_application(
    session: Session, council: CouncilConfig, app, batch_id: str | None, unit_confirmation_status: str | None = None,
) -> Application:
    """Shared by stage_scrape and stage_fetch_missing_parents - both end up
    writing the same shape of scraper result (idox_portal/arcus_portal's
    ScrapedApplication) into an applications row, just discovered via a
    different search (date-range vs a single targeted reference lookup)."""
    existing = session.execute(
        select(Application).where(Application.council_code == council.code, Application.reference == app.reference)
    ).scalar_one_or_none()

    if existing is None:
        existing = Application(council_code=council.code, reference=app.reference)
        session.add(existing)

    for model_field, portal_field in FIELD_MAP.items():
        value = app.fields.get(portal_field)
        if value:
            setattr(existing, model_field, value)

    existing.summary_url = app.summary_url
    existing.further_info_url = app.further_info_url
    existing.keyval = app.keyval
    existing.estimated_unit_count = app.estimated_unit_count
    existing.application_category = app.application_category
    existing.opportunity_classification = app.opportunity_classification
    existing.scrape_batch_id = batch_id
    if unit_confirmation_status:
        # Excluded from UNIT_GATE_PASSED on purpose - this row exists purely
        # as a phase-progress signal or parent-context backfill, not to go
        # through document download/AI extraction as its own scheme in its
        # own right.
        existing.unit_confirmation_status = unit_confirmation_status
    elif existing.estimated_unit_count is not None:
        # Portal proposal text already gave a confident unit count - no need
        # for the confirm-units gate below.
        existing.unit_confirmation_status = "confirmed_qualifying"
    return existing


def stage_fetch_missing_parents(session: Session, page, council: CouncilConfig) -> int:
    """Reserved matters applications routinely cite a parent outline/full
    permission that predates our scraping window and was never scraped in
    its own right (confirmed real case: Wigan's North Leigh 1491-dwelling
    reserved matters filing citing outline permission A/12/76665, granted
    in 2013 - years before this council was ever scraped). Left alone, that
    parent reference sits as a dead citation and the reserved matters
    filing's own thin documents (layout/scale/appearance only) can't answer
    "what's the affordable housing position/who's the developer" - the real
    answer usually lives in the PARENT's own documents (planning statement,
    S106, officer report), which is exactly the site-level detail the
    parent-reference site-linking tier already knows how to merge in, once
    the parent actually exists as an application in its own right.

    Also resolves the reserved matters filing's OWN qualification against
    its parent's real content - REVIEW_KEYWORDS treats "reserved matters"
    as unambiguously relevant regardless of scheme size (needed to catch
    genuine housing-phase filings with no unit count of their own), which
    means a reserved matters filing for a single dwelling slips through
    exactly the same way a 200-unit one does. Confirmed real case: Oldham
    RES/355397/25 ("Reserved Matters application for the access, scale,
    layout, appearance and landscape relating to app no. OUT/350210/22"),
    whose parent OUT/350210/22 turned out to be outline permission for one
    2-storey dwellinghouse. An explicit low unit count on the parent is
    treated as a confident disqualification; a parent with no stated count
    at all (genuinely vague outline text, e.g. "comprehensive mixed use
    redevelopment") is left exactly as before, since that vagueness is just
    as common on large legitimate schemes and shouldn't be penalised.

    Targeted single-reference lookup (see idox_portal/arcus_portal's
    fetch_application_by_reference) rather than a full date-range scrape -
    the parent could be from any year, so there's no sensible month to
    search instead.
    """
    candidates = session.execute(
        select(Application).where(
            Application.council_code == council.code,
            # Not just reserved_matters - confirmed real cases (Trafford
            # 119012/VLA/26, Oldham VAR/349651/22) of variation_or_amendment
            # and condition_discharge_or_details applications citing a
            # parent that's missing from the DB too, previously invisible
            # to this stage entirely since it only ever scanned
            # reserved_matters. The qualification-override logic below
            # still only meaningfully applies to reserved_matters (the
            # other two categories already have their own
            # unit_confirmation_status resolved elsewhere and simply no-op
            # past it) - what matters for them here is recovering the
            # missing parent itself, which feeds stage_link_sites'
            # parent_reference tier and, from there,
            # stage_fetch_related_applications.
            Application.application_category.in_(
                ["reserved_matters", "variation_or_amendment", "condition_discharge_or_details"]
            ),
        )
    ).scalars().all()

    ref_to_id = {
        row[0]: row[1] for row in session.execute(
            select(Application.reference, Application.id).where(Application.council_code == council.code)
        ).all()
    }

    fetched = 0
    for application in candidates:
        parent_ref = extract_parent_reference(application.proposal or "")
        if not parent_ref:
            continue

        parent = session.get(Application, ref_to_id[parent_ref]) if parent_ref in ref_to_id else None

        if parent is None:
            print(f"  [parent-lookup] {application.reference} cites {parent_ref!r} - not in DB, fetching")
            try:
                if council.doc_system == "arcus":
                    result = fetch_application_by_reference_arcus(page, council, parent_ref)
                else:
                    requests_session = requests.Session()
                    requests_session.headers.update(HEADERS)
                    result = fetch_application_by_reference_idox(page, requests_session, council, parent_ref)
            except Exception as e:
                print(f"    error fetching parent {parent_ref}: {e}")
                continue

            if not result or not result.reference:
                print(f"    parent {parent_ref} not found on the portal")
                continue

            parent_qualify = qualify(result.fields.get("Proposal", ""), council.unit_threshold)
            # Force confirmed_qualifying by default rather than leaving it
            # for stage_confirm_units - confirmed a real case (A/12/76665,
            # vague outline text with no unit count) where that would
            # otherwise land on "undetermined" and get silently excluded,
            # despite already being confirmed relevant as the cited parent
            # of a real qualifying scheme. Only overridden by a confident
            # negative signal on the parent's OWN text: either an explicit
            # low unit count, or a genuine non-residential match (confirmed
            # real cases: a storage/distribution warehouse outline, a green
            # hydrogen production facility). Deliberately NOT overridden by
            # EXCLUDE_CATEGORIES matches (e.g. "variation_or_amendment") -
            # that's a structural label ("this filing isn't itself a new
            # development"), not a size signal - confirmed a real case
            # (Oldham VAR/349651/22) where the cited "parent" was itself a
            # variation of conditions on a further-removed genuine outline
            # scheme, so treating it as disqualifying would have been wrong.
            parent_status = (
                "confirmed_disqualified"
                if (parent_qualify.unit_count is not None and parent_qualify.unit_count < council.unit_threshold)
                or parent_qualify.classification == "Excluded - non-residential"
                else "confirmed_qualifying"
            )
            parent = _upsert_scraped_application(
                session, council, result, batch_id=None, unit_confirmation_status=parent_status,
            )
            ref_to_id[result.reference] = parent.id
            session.commit()
            fetched += 1
            print(f"    fetched {result.reference} ({parent_status}): {(result.fields.get('Proposal') or '')[:80]}")

        if application.unit_confirmation_status not in (None, "undetermined"):
            continue
        parent_qualify = qualify(parent.proposal or "", council.unit_threshold)
        parent_confidently_disqualified = (
            (parent_qualify.unit_count is not None and parent_qualify.unit_count < council.unit_threshold)
            or parent_qualify.classification == "Excluded - non-residential"
        )
        if parent_confidently_disqualified:
            application.unit_confirmation_status = "confirmed_disqualified"
            application.opportunity_classification = (
                f"Excluded - parent {parent_ref} confirmed {parent_qualify.unit_count} unit(s)"
                if parent_qualify.unit_count is not None
                else f"Excluded - parent {parent_ref} is non-residential"
            )
            session.commit()
            print(f"  [parent-lookup] {application.reference}: parent {parent_ref} confirmed disqualified - excluded")
        elif parent_qualify.unit_count is not None and parent_qualify.unit_count >= council.unit_threshold:
            application.estimated_unit_count = parent_qualify.unit_count
            application.unit_confirmation_status = "confirmed_qualifying"
            application.opportunity_classification = f"Confirmed - {parent_qualify.unit_count} units (via parent {parent_ref})"
            session.commit()
            print(f"  [parent-lookup] {application.reference}: parent {parent_ref} confirms {parent_qualify.unit_count} units")

    print(f"\n[parent-lookup] {len(candidates)} reserved matters applications checked, {fetched} parent(s) fetched")
    return fetched


def stage_fetch_related_applications(session: Session, page, council: CouncilConfig) -> int:
    """Once a parent application is verified (site_link_method ==
    "parent_reference" - either auto-detected from a child's own citation,
    or fetched by stage_fetch_missing_parents above), search the portal for
    every OTHER application that names it by reference (see
    app.scrapers.idox_portal.search_related_applications).

    This is deliberately NOT the same thing as Idox's own "Related Cases"
    tab - confirmed a real case (Stockport DC/060928, a hybrid outline for a
    325-dwelling masterplan) with 0 entries there despite ~30 real linked
    filings (phase-specific reserved matters, discharge of conditions,
    non-material amendments) only discoverable by searching its own
    reference, since child filings routinely name their parent in their own
    description rather than through the portal's officer-maintained linking.
    This is how a large site's full phase history - and therefore whether
    construction has actually started somewhere on it, even where no single
    application says so on its own - gets built up.

    Each found application is linked straight to the parent's own site
    rather than left for stage_link_sites' regex-based citation parsing,
    which routinely can't (e.g. "Discharge of condition 24 of DC/060928"
    doesn't match any pursuant-to/following/relating-to phrasing
    extract_parent_reference recognises) - we already KNOW the relationship
    from the search itself, no need to re-derive it independently and risk
    it landing as an orphaned new site instead. Administrative/progress-
    signal filings (discharge of conditions, variations) are captured for
    the phase-tracking/lapse-status "underway" signal but not treated as
    their own independently-reportable qualifying scheme, matching
    stage_scrape's own progress_signal_only convention.

    Idox only (search_related_applications isn't implemented for Arcus).
    Not time-bounded like stage_check_build_status's 30-day cooldown - a
    parent's family of filings grows slowly and unpredictably as a scheme
    progresses, with no natural "recently checked" cutoff. Re-running this
    against an already-searched parent mostly just re-finds already-known
    applications (harmless - upserts in place) plus occasionally a
    genuinely new one."""
    if council.doc_system == "arcus":
        return 0

    verified_parents = session.execute(
        select(Application).where(
            Application.council_code == council.code,
            Application.site_link_method == "parent_reference",
            Application.site_id.is_not(None),
        )
    ).scalars().all()
    print(f"\n[related-applications] {len(verified_parents)} verified parent application(s) to search")

    requests_session = requests.Session()
    requests_session.headers.update(HEADERS)

    found_total = 0
    for parent in verified_parents:
        try:
            summary_urls = search_related_applications(page, council, parent.reference)
        except Exception as e:
            print(f"  [related-applications] error searching for {parent.reference}: {e}")
            continue
        time.sleep(council.request_delay_seconds)

        new_this_parent = 0
        for summary_url in summary_urls:
            keyval = keyval_from_url(summary_url)
            existing = session.execute(
                select(Application).where(Application.council_code == council.code, Application.keyval == keyval)
            ).scalar_one_or_none() if keyval else None
            if existing:
                continue
            try:
                result = fetch_application_detail(
                    requests_session, summary_url, unit_threshold=council.unit_threshold,
                    further_info_tab=council.further_info_tab, request_delay_seconds=council.request_delay_seconds,
                )
            except Exception as e:
                print(f"    error fetching {summary_url}: {e}")
                continue

            proposal = result.fields.get("Proposal", "")
            category = classify_application_category(proposal)
            is_progress_signal = category in PROGRESS_SIGNAL_CATEGORIES
            status = "progress_signal_only" if is_progress_signal else (
                "confirmed_qualifying" if result.qualifies else None
            )

            application = _upsert_scraped_application(
                session, council, result, batch_id=None, unit_confirmation_status=status,
            )
            application.site_id = parent.site_id
            application.site_link_method = "related_search"
            session.commit()

            new_this_parent += 1
            found_total += 1
            tag = "progress signal" if is_progress_signal else ("qualifying" if result.qualifies else "not independently qualifying")
            print(f"    {parent.reference} -> found {result.reference} ({tag}): {proposal[:80]}")
            time.sleep(council.request_delay_seconds)

        print(f"  [related-applications] {parent.reference}: {len(summary_urls)} search result(s), {new_this_parent} new")

    return found_total


def stage_link_sites(session: Session, council: CouncilConfig) -> int:
    pending = session.execute(
        select(Application).where(
            Application.council_code == council.code,
            Application.site_link_method.is_(None),
        )
    ).scalars().all()
    print(f"\n[site-link] {len(pending)} applications need site linking")

    for application in pending:
        link_application_to_site(session, application)
        if application.site_link_method == "suggested_fuzzy":
            print(f"  [site-link] {application.reference}: suggested match "
                  f"(confidence={application.site_link_confidence}) - awaiting review")
        else:
            print(f"  [site-link] {application.reference}: {application.site_link_method} -> site {application.site_id}")

    session.commit()
    return len(pending)


def _pick_confirmed_unit_count(text: str, threshold: int) -> int | None:
    """The real total unit count in a planning statement is typically
    restated many times over (summary, conclusion, benefits section,
    consultation letter...), while unrelated numbers that happen to sit near
    unit-count language - a borough-wide housing delivery target, a draft
    site-allocation capacity, a parking-space count - usually appear once or
    twice. Confirmed against a real case: "149 dwellings" appeared 14 times
    in one planning statement against a next-highest unrelated number
    appearing 6 times, a clear margin, while an application form with no
    real unit count only produced two candidates appearing once each - no
    margin, correctly rejected.

    Filters out anything below the qualifying threshold first, which removes
    bedroom-count noise like "2, 3 and 4 bed dwellings" from ever competing."""
    candidates = [c for c in extract_unit_counts(text) if c >= threshold]
    if not candidates:
        return None
    counts = Counter(candidates).most_common()
    top_value, top_count = counts[0]
    runner_up_count = counts[1][1] if len(counts) > 1 else 0
    return top_value if top_count > runner_up_count else None


def stage_confirm_units(session: Session, page, council: CouncilConfig) -> int:
    """Cheap confirmation gate for applications that only qualified via a
    REVIEW_KEYWORDS guess in the proposal text (no unit count stated
    anywhere, e.g. "erection of a residential development... access from
    Butterworth Lane") - checks just the Application Form, then the Planning
    Statement if the form doesn't have it, before the application is allowed
    anywhere near the full document-download + 3-LLM extraction pipeline.
    Applications whose count the portal-text regex already confirmed at
    scrape time never reach this (unit_confirmation_status was set to
    confirmed_qualifying there and estimated_unit_count is not None).

    Only applies to doc_system="idox" councils - for idox_anite (Bury),
    document *discovery* already downloads every file in one Playwright pass
    (see app.scrapers.documents.get_anite_documents), so there's no cheaper
    subset to check first; those applications proceed to stage_documents
    exactly as before.
    """
    if council.doc_system != "idox":
        return 0

    pending = session.execute(
        select(Application).where(
            Application.council_code == council.code,
            Application.estimated_unit_count.is_(None),
            Application.unit_confirmation_status.is_(None),
        )
    ).scalars().all()
    print(f"\n[confirm-units] {len(pending)} applications need unit-count confirmation")

    requests_session = requests.Session()
    requests_session.headers.update(HEADERS)

    confirmed_qualifying = 0
    for application in pending:
        if not application.summary_url:
            continue

        dest_dir = document_dir(council.code, application.reference)
        try:
            rows = discover_documents(page, requests_session, council, application.summary_url, dest_dir)
        except Exception as e:
            print(f"  [confirm-units] error discovering docs for {application.reference}: {e}")
            continue

        by_type = {}
        for row in rows:
            doc_type = standardise_document_type(row.document_name, row.doc_type_raw)
            if doc_type in ("application_form", "planning_statement") and doc_type not in by_type:
                by_type[doc_type] = row

        found_count = None
        checked = []
        for doc_type in ("application_form", "planning_statement"):
            row = by_type.get(doc_type)
            if not row or not row.source_url:
                continue
            checked.append(doc_type)
            try:
                # Downloads to the application's real document folder (same
                # path stage_documents will use) so if this confirms
                # qualifying, the full download pass below re-fetches
                # everything except this one file for free (already on disk).
                local_path = download_document(
                    council.code, application.reference, row.document_name, row.source_url,
                    session=requests_session, referer=row.referer,
                )
                text = extract_document_text(local_path) if local_path else ""
            except Exception as e:
                print(f"  [confirm-units] download/extract failed for {row.document_name}: {e}")
                continue
            # Unlike the fuzzy REVIEW_KEYWORDS bucket (low stakes - just
            # means "download everything and let the LLM stages sort it
            # out"), a wrong call here either wrongly excludes a real scheme
            # or wrongly admits one straight to "confirmed qualifying" with
            # no further scrutiny - see _pick_confirmed_unit_count.
            found_count = _pick_confirmed_unit_count(text, council.unit_threshold)
            if found_count is not None:
                break

        if found_count is not None and found_count >= council.unit_threshold:
            application.estimated_unit_count = found_count
            application.unit_confirmation_status = "confirmed_qualifying"
            application.opportunity_classification = f"Confirmed - {council.unit_threshold}+ units ({'/'.join(checked)})"
            confirmed_qualifying += 1
            print(f"  [confirm-units] {application.reference}: confirmed {found_count} units - proceeding to full extraction")
        elif found_count is not None:
            application.unit_confirmation_status = "confirmed_disqualified"
            application.opportunity_classification = (
                f"Excluded - confirmed {found_count} units, under {council.unit_threshold} ({'/'.join(checked)})"
            )
            print(f"  [confirm-units] {application.reference}: confirmed only {found_count} units - excluded")
        else:
            application.unit_confirmation_status = "undetermined"
            where = "/".join(checked) if checked else "no application form or planning statement found"
            print(f"  [confirm-units] {application.reference}: no unit count found in {where} - flagged for manual review")

        session.commit()

    return confirmed_qualifying


def stage_documents(session: Session, page, council: CouncilConfig) -> int:
    pending = session.execute(
        select(Application).where(
            Application.council_code == council.code, ~Application.documents.any(), UNIT_GATE_PASSED
        )
    ).scalars().all()
    print(f"\n[documents] {len(pending)} applications need document download")

    requests_session = requests.Session()
    requests_session.headers.update(HEADERS)

    processed = 0
    for application in pending:
        if not application.summary_url:
            continue
        dest_dir = document_dir(council.code, application.reference)
        try:
            rows = discover_documents(page, requests_session, council, application.summary_url, dest_dir)
        except Exception as e:
            print(f"  [documents] error discovering docs for {application.reference}: {e}")
            continue

        skipped = 0
        sniffed = 0
        for row in rows:
            # Classify from the listing metadata (already fetched, no extra
            # request) BEFORE downloading - site plans, CAD drawings, ecology/
            # drainage/transport reports etc. are never read by extraction
            # (see build_combined_priority_text), so there's no reason to
            # fetch and text-extract them at all.
            doc_type = standardise_document_type(row.document_name, row.doc_type_raw)
            uninformative_name = doc_type == "other" and name_is_uninformative(row.document_name)
            if doc_type not in USEFUL_DOC_TYPES and not uninformative_name:
                skipped += 1
                continue

            local_path = row.local_path
            if local_path is None and row.source_url:
                try:
                    local_path = download_document(
                        council.code, application.reference, row.document_name, row.source_url,
                        session=requests_session, referer=row.referer,
                    )
                except Exception as e:
                    print(f"  [documents] download failed for {row.document_name}: {e}")
                    continue

            text = extract_document_text(local_path) if local_path else ""

            if uninformative_name:
                # Name gave no signal (confirmed real case: Manchester's
                # Arcus portal stores the council's own document ID as the
                # "name" for most uploads - "805570.pdf") - now that it's
                # downloaded anyway to check, look at what the document
                # itself actually opens with instead of discarding it.
                doc_type = sniff_document_type_from_text(text)
                if doc_type not in USEFUL_DOC_TYPES:
                    skipped += 1
                    continue
                sniffed += 1

            session.add(
                Document(
                    application_id=application.id,
                    doc_type=doc_type,
                    document_name=row.document_name,
                    source_url=row.source_url,
                    local_path=str(local_path) if local_path else None,
                    text_extracted=bool(text),
                    extracted_text=clean_document_text(text) if text else None,
                    downloaded_at=dt.datetime.now(dt.timezone.utc),
                )
            )
        session.commit()
        processed += 1
        print(f"  [documents] {application.reference}: {len(rows) - skipped} documents downloaded, "
              f"{skipped} skipped (not a useful document type), {sniffed} classified by content (name was uninformative)")

    return processed


def stage_extraction(session: Session, client: OpenAI, council: CouncilConfig) -> int:
    pending = session.execute(
        select(Application).where(
            Application.council_code == council.code,
            Application.scheme_intelligence == None,  # noqa: E711
            UNIT_GATE_PASSED,
        )
    ).scalars().all()
    print(f"\n[extraction] {len(pending)} applications need AI extraction")

    processed = 0
    for application in pending:
        try:
            fields = run_extraction_for_application(client, application)
        except Exception as e:
            print(f"  [extraction] error on {application.reference}: {e}")
            continue

        if not fields:
            print(f"  [extraction] {application.reference}: no usable document text, skipped")
            continue

        session.add(SchemeIntelligence(application_id=application.id, **fields))
        session.commit()
        processed += 1
        print(f"  [extraction] {application.reference}: total_units={fields.get('total_units_final')} "
              f"affordable={fields.get('affordable_units_final')} developer={fields.get('developer')}")

    return processed


def stage_geocode_sites(session: Session, council: CouncilConfig) -> int:
    pending = session.execute(
        select(Site).where(Site.council_code == council.code, Site.latitude.is_(None))
    ).scalars().all()
    print(f"\n[geocode] {len(pending)} sites need geocoding")

    for site in pending:
        if site.postcode:
            try:
                coords = geocode_postcode(site.postcode)
            except Exception as e:
                print(f"  [geocode] error for {site.postcode}: {e}")
                continue
            if coords:
                site.latitude, site.longitude = coords
                print(f"  [geocode] {site.postcode} -> {coords}")
        else:
            # No postcode in the address text at all (common for vacant/
            # greenfield land - see epc_lookup.geocode_address) - fall back
            # to free-text address geocoding via Nominatim, rate-limited to
            # 1 req/sec per its usage policy.
            try:
                result = geocode_address(site.display_address)
            except Exception as e:
                print(f"  [geocode] error for {site.display_address!r}: {e}")
                time.sleep(NOMINATIM_MIN_INTERVAL_SECONDS)
                continue
            if result:
                site.latitude, site.longitude, postcode = result
                if postcode:
                    site.postcode = postcode
                print(f"  [geocode] {site.display_address!r} -> ({site.latitude}, {site.longitude})"
                      f"{f', postcode {postcode}' if postcode else ''}")
            time.sleep(NOMINATIM_MIN_INTERVAL_SECONDS)
        session.commit()

    return len(pending)


def stage_check_build_status(session: Session, council: CouncilConfig, epc_key: str | None) -> int:
    # Naive comparison throughout, not just a naive cutoff: SQLite has no
    # real timezone-aware storage, so a freshly-set (tz-aware, same Python
    # session) build_status_checked_at compares fine the first time, but
    # reading it back in any LATER session/process (e.g. a subsequent
    # pipeline run) round-trips it through SQLite as naive - confirmed a
    # real crash on a site checked once already, then re-encountered in a
    # later backfill run: "can't compare offset-naive and offset-aware
    # datetimes". Both sides represent UTC wall-clock time regardless, so
    # comparing naive-to-naive is correct here, not just a workaround.
    cutoff = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(days=30)
    sites = session.execute(select(Site).where(Site.council_code == council.code)).scalars().all()

    candidates = []
    for site in sites:
        # Uses the same is_granted_decision() check as lapse_tracking, not a
        # local startswith("approve") - confirmed a real gap: "Granted" (the
        # single most common UK planning decision wording after "Approve
        # with Conditions") doesn't start with "approve", so every site
        # whose only decided application said exactly "Granted" was silently
        # never eligible for a build-status check at all, across every
        # council, independent of whether an EPC key was configured.
        decided_apps = [a for a in site.applications if is_granted_decision(a.decision)]
        if not decided_apps:
            continue  # nothing approved yet - definitionally not built
        checked_at = site.build_status_checked_at
        if checked_at and checked_at.replace(tzinfo=None) > cutoff:
            continue  # checked recently, skip
        candidates.append((site, decided_apps))

    print(f"\n[build-status] {len(candidates)} sites need a build-status check")

    for site, decided_apps in candidates:
        expected_units = None
        for app in decided_apps:
            if app.scheme_intelligence and app.scheme_intelligence.total_units_final:
                expected_units = app.scheme_intelligence.total_units_final
                break

        decided_dates = [parse_uk_date(a.decision_issued_date) for a in decided_apps]
        decided_dates = [d for d in decided_dates if d]
        decided_after = min(decided_dates) if decided_dates else None

        result = check_build_status(epc_key, site.postcode, expected_units, decided_after)
        site.build_status = result.status
        site.build_status_checked_at = result.checked_at
        site.epc_dwellings_found = result.epc_count
        session.commit()
        print(f"  [build-status] site {site.id} ({site.display_address}): {result.status} ({result.epc_count} EPCs found)")

    return len(candidates)


def parse_uk_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.datetime.strptime(value.strip(), "%a %d %b %Y").date()
    except ValueError:
        return None


def stage_enrichment(
    session: Session, council: CouncilConfig, ch_key: str, serpapi_key, apollo_key, hunter_key,
    openai_client: OpenAI | None = None,
) -> int:
    scheme_rows = session.execute(
        select(SchemeIntelligence)
        .join(Application)
        .where(Application.council_code == council.code)
    ).scalars().all()

    processed = 0
    for scheme in scheme_rows:
        for role, name in (("applicant", scheme.applicant_company), ("developer", scheme.developer)):
            if not name or not name.strip():
                continue

            already_linked = session.execute(
                select(ApplicationCompany).where(
                    ApplicationCompany.application_id == scheme.application_id, ApplicationCompany.role == role
                )
            ).scalar_one_or_none()
            if already_linked:
                continue

            print(f"  [enrichment] {name} ({role}) for {scheme.application.reference}")
            site_address = scheme.application.site.display_address if scheme.application.site else None
            try:
                result = enrich_company(
                    name, ch_key, serpapi_key, apollo_key, hunter_key, openai_client=openai_client,
                    site_address=site_address, proposal_summary=scheme.application.proposal,
                )
            except Exception as e:
                print(f"    error: {e}")
                continue

            company = upsert_company_from_enrichment(session, name, result)
            session.add(ApplicationCompany(application_id=scheme.application_id, company_id=company.id, role=role))
            session.commit()
            processed += 1

    print(f"\n[enrichment] {processed} company/role links enriched")
    return processed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--council", required=True, help="Council code from config/councils.yaml, e.g. bury")
    parser.add_argument("--date-from", help="DD/MM/YYYY - defaults to the 1st of the current month")
    parser.add_argument("--date-to", help="DD/MM/YYYY - defaults to today")
    parser.add_argument(
        "--years-back", type=int, default=None,
        help="Backfill mode: scrape every month for the last N years instead of just the current month "
             "(e.g. --years-back 5). Ignored if --date-from is given.",
    )
    parser.add_argument("--skip-scrape", action="store_true")
    parser.add_argument("--skip-parent-lookup", action="store_true")
    parser.add_argument("--skip-site-link", action="store_true")
    parser.add_argument("--skip-related-applications", action="store_true")
    parser.add_argument("--skip-confirm-units", action="store_true")
    parser.add_argument("--skip-documents", action="store_true")
    parser.add_argument("--skip-extraction", action="store_true")
    parser.add_argument("--skip-geocode", action="store_true")
    parser.add_argument("--skip-build-status", action="store_true")
    parser.add_argument(
        "--enrich", action="store_true",
        help="Also run contact enrichment (Companies House/website/Apollo/Hunter) for every scheme found. "
             "Off by default - enrichment is meant to be triggered on demand from the Streamlit "
             "\"Unlock contacts\" button so you don't spend API credits on schemes you don't care about.",
    )
    parser.add_argument("--headless", action="store_true", default=True)
    return parser.parse_args()


def _resolve_month_ranges(args: argparse.Namespace) -> list[tuple[str, str]]:
    today = dt.date.today()

    if args.date_from:
        return [(args.date_from, args.date_to or today.strftime("%d/%m/%Y"))]

    if args.years_back:
        start = today.replace(year=today.year - args.years_back, day=1)
        return generate_month_ranges(start.year, start.month, today.year, today.month)

    # Default weekly cadence: just the current month.
    return [(today.replace(day=1).strftime("%d/%m/%Y"), today.strftime("%d/%m/%Y"))]


def main() -> None:
    args = parse_args()
    load_dotenv(override=True)  # this project's .env always wins over stray shell-exported vars

    init_db()
    session = get_session()
    council = get_council(args.council)
    ensure_council_row(session, council)

    month_ranges = _resolve_month_ranges(args)
    batch_id = f"{council.code}_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    if len(month_ranges) > 1:
        print(f"Backfill mode: {len(month_ranges)} months ({month_ranges[0][0]} -> {month_ranges[-1][1]})")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        # Playwright's default headless fingerprint (empty/automation-flagged
        # UA) gets outright WAF-blocked by some councils' portals - confirmed
        # a real case: Trafford returns "The URL you requested has been
        # blocked" for the exact same request a normal browser succeeds at.
        # This is the same public planning register a human visitor sees, so
        # a realistic desktop UA is a reasonable fix, not evasion of
        # anything access-restricted - and it's a safe no-op for councils
        # that were never blocking in the first place.
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        if not args.skip_scrape:
            for i, (date_from, date_to) in enumerate(month_ranges):
                if i > 0:
                    time.sleep(MONTH_COOLDOWN_SECONDS)  # courtesy pause between months on a backfill
                try:
                    stage_scrape(session, page, council, date_from, date_to, batch_id)
                except Exception as e:
                    # A single month failing (e.g. the portal rate-limits or blocks us
                    # mid-run) shouldn't lose every other month in a multi-year backfill -
                    # log it and keep going. Re-running later will pick up this month
                    # since applications already saved are untouched (upsert, not replace).
                    print(f"\n[scrape] FAILED for {date_from} -> {date_to}: {e}")
                    print("[scrape] continuing to next month...")

        if not args.skip_parent_lookup:
            # Runs after every month's scrape (so any newly-found reserved
            # matters filing is included) but before site-linking, so a
            # freshly-fetched parent is in the DB in time for the SAME run's
            # parent_reference site-linking tier to pick it up.
            stage_fetch_missing_parents(session, page, council)

        if not args.skip_site_link:
            stage_link_sites(session, council)

        if not args.skip_related_applications:
            # After stage_link_sites, not before - needs a parent's site_id
            # already set (site_link_method == "parent_reference") to know
            # what to search for and where to attach anything it finds.
            stage_fetch_related_applications(session, page, council)

        if not args.skip_confirm_units:
            stage_confirm_units(session, page, council)

        if not args.skip_documents:
            stage_documents(session, page, council)

        browser.close()

    if not args.skip_extraction:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set in .env")
        client = OpenAI(api_key=api_key)
        stage_extraction(session, client, council)

    if not args.skip_geocode:
        stage_geocode_sites(session, council)

    if not args.skip_build_status:
        stage_check_build_status(session, council, os.getenv("EPC_API_KEY"))

    if args.enrich:
        ch_key = os.getenv("CH_API_KEY")
        if not ch_key:
            raise RuntimeError("CH_API_KEY not set in .env")
        openai_key = os.getenv("OPENAI_API_KEY")
        stage_enrichment(
            session, council, ch_key,
            os.getenv("SERPAPI_KEY"), os.getenv("APOLLO_API_KEY"), os.getenv("HUNTER_API_KEY"),
            openai_client=OpenAI(api_key=openai_key) if openai_key else None,
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
