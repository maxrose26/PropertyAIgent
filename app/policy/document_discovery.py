"""Policy-page and policy-document discovery, download tracking, and the
Visual Evidence hand-off queue (Sprint 3D, "Policy Document Coverage &
Discovery", Parts 4/5/6/8).

Three distinct, deterministic responsibilities live here, none of them
AI-driven (Part 4: "Do not use AI to crawl. Use deterministic URL and
title matching"):

  1. discover_policy_pages / register_candidate_policy_sources (Part 4) -
     find NEW planning-policy SECTIONS on a council's own website
     ("Planning Policy", "Local Plan", "Evidence Base", "Interactive Map",
     "Policies Map", "Development Plan"...) that aren't yet a registered
     MonitoredSource at all, and register them - one level up from
     app.policy.report_discovery, which already finds DOCUMENTS under an
     index page that IS already registered.

  2. queue_ambiguous_policy_document / download_policy_document (Part 5) -
     when more than one plausible candidate exists for the same expected
     document type, this is queued for a human decision, never silently
     resolved by picking one (Part 5: "Do not silently ingest if
     confidence is low"). Downloading reuses
     app.extraction.pdf_text.download_document verbatim - the same
     collision-proof, safely-pathed downloader every other document in
     this platform already goes through, not a second implementation.

  3. queue_visual_evidence_candidates (Part 6) - a pure, read-only list of
     which newly-registered map-type documents have no VisualEvidence yet.
     Discovery only ever REGISTERS a document; it never triggers AI
     classification itself - that stays a deliberate, separate step
     through the existing app.visuals pipeline (Part 6: "Do not
     automatically classify every page. Reuse the existing candidate
     selection pipeline").
"""
from __future__ import annotations

import datetime as dt
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MonitoredReport, MonitoredSource, PolicyChangeEvent, VisualEvidence
from app.extraction.pdf_text import download_document
from app.policy.document_types import classify_policy_document_type

# Same honest, browser-like header app.policy.report_discovery/monitor
# already use - some council sites 403 the default python-requests agent.
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"}
DEFAULT_TIMEOUT_SECONDS = 15

# A link's own text/URL must contain at least one of these for it to be
# treated as a candidate PLANNING-POLICY page worth registering as a new
# MonitoredSource - Part 4's own example list, verbatim. Deliberately
# broader/coarser than app.policy.document_types' own document-level
# rules: this is about finding a SECTION worth watching, not classifying
# a specific document yet (that happens once app.policy.report_discovery
# or this module's own classify_policy_document_type looks at what's
# actually under the section).
POLICY_PAGE_KEYWORDS = (
    "planning policy",
    "planning policy documents",
    "local plan",
    "evidence base",
    "interactive map",
    "policies map",
    "development plan",
)

# Document types (app.policy.document_types.POLICY_DOCUMENT_TYPES) that
# are genuinely map/visual artefacts - Part 6's "newly discovered Policies
# Map or Allocation Map" - eligible for the Visual Evidence queue. A
# purely textual type (an AMR, a trajectory) is never queued here; there
# is nothing for app.visuals' page-candidate detection to usefully find
# in it.
MAP_LIKE_DOCUMENT_TYPES = frozenset({
    "policies_map", "interactive_map", "allocation_map",
    "development_plan_map", "inset_map", "masterplan",
})


def discover_policy_pages(html: str, base_url: str) -> list[dict]:
    """Deterministic title-keyword matching over every link on a page -
    Part 4's "review each council's planning-policy pages... use
    deterministic URL and title matching". Returns
    [{"url", "link_text", "matched_keyword"}, ...], deduped by URL. Not
    restricted to document-extension links the way
    app.policy.report_discovery.extract_document_links is - a policy
    SECTION is usually itself an ordinary webpage, not a PDF."""
    soup = BeautifulSoup(html, "html.parser")
    seen: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.lower().startswith(("mailto:", "javascript:")):
            continue
        text = a.get_text(strip=True)
        if not text:
            continue
        haystack = text.lower()
        matched = next((kw for kw in POLICY_PAGE_KEYWORDS if kw in haystack), None)
        if matched is None:
            continue
        absolute = urljoin(base_url, href)
        seen.setdefault(absolute, {"url": absolute, "link_text": text, "matched_keyword": matched})
    return list(seen.values())


def register_candidate_policy_sources(session: Session, council_code: str, candidates: list[dict]) -> list[MonitoredSource]:
    """Registers a new MonitoredSource for every candidate whose URL isn't
    already watched for this council - idempotent, matching
    app.policy.sources.register_sources_for_council's own find-or-create
    shape. A confident deterministic keyword match on the page's own link
    text is enough to register AND monitor a new index page (Part 4 draws
    the review-gate line at ambiguous DOCUMENT candidates, Part 5, not at
    discovering a new section worth watching)."""
    existing_urls = {
        s.url for s in session.execute(
            select(MonitoredSource).where(MonitoredSource.council_code == council_code)
        ).scalars()
    }
    registered = []
    for candidate in candidates:
        if candidate["url"] in existing_urls:
            continue
        policy_document_type, _ = classify_policy_document_type(candidate["link_text"], candidate["url"])
        source = MonitoredSource(
            council_code=council_code, url=candidate["url"],
            source_type="policy_document_library" if policy_document_type == "unknown" else policy_document_type,
            title=candidate["link_text"],
            policy_document_type=policy_document_type, policy_document_type_raw_label=candidate["link_text"],
        )
        session.add(source)
        registered.append(source)
        existing_urls.add(candidate["url"])
    session.commit()
    return registered


def discover_policy_pages_for_council(session: Session, council_code: str, start_url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict:
    """Fetches start_url (a council's own planning-policy landing page),
    finds candidate policy SECTIONS on it, and registers any genuinely
    new ones. Returns {"candidates_found", "new_sources_registered",
    "fetch_failed"}."""
    try:
        response = requests.get(start_url, timeout=timeout, headers=REQUEST_HEADERS)
        response.raise_for_status()
    except requests.RequestException:
        return {"candidates_found": 0, "new_sources_registered": 0, "fetch_failed": True}

    candidates = discover_policy_pages(response.text, response.url or start_url)
    registered = register_candidate_policy_sources(session, council_code, candidates)
    return {"candidates_found": len(candidates), "new_sources_registered": len(registered), "fetch_failed": False}


def queue_ambiguous_policy_document(session: Session, council_code: str, policy_document_type: str, candidates: list[dict]) -> PolicyChangeEvent:
    """Part 5: "If multiple candidate documents exist: queue for review" -
    never silently picks one. candidates: [{"url", "title"}, ...], at
    least two genuinely different plausible matches for the SAME expected
    document type. Creates one PolicyChangeEvent a human resolves by hand
    (registering whichever candidate is actually correct via the normal
    MonitoredSource/MonitoredReport registration path) - this function
    itself never registers anything."""
    if len(candidates) < 2:
        raise ValueError("queue_ambiguous_policy_document requires at least 2 genuinely different candidates")
    candidate_list = "; ".join(f"{c['title']!r} ({c['url']})" for c in candidates)
    event = PolicyChangeEvent(
        event_type="policy_document_candidates_ambiguous",
        old_value=None, new_value=policy_document_type,
        detail=(
            f"Found {len(candidates)} candidate documents for expected type {policy_document_type!r} for "
            f"{council_code} - not confidently resolvable to one, so none were auto-registered: {candidate_list}"
        ),
        auto_applied=False, review_status="needs_review",
        detected_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(event)
    session.commit()
    return event


def download_policy_document(session: Session, report: MonitoredReport) -> bool:
    """Downloads report.url to local disk via the SAME downloader every
    other document in this platform already uses
    (app.extraction.pdf_text.download_document) - never a second
    implementation. Sets report.local_path on success (Part 3's
    "Downloaded?" signal); leaves it untouched on failure, since a failed
    download is not the same as "we chose not to download this", and a
    caller retrying later should see the same null state, not a false
    "already tried and gave up" marker."""
    path = download_document(
        report.council_code, f"policy-{report.id}", report.title or "policy-document", report.url,
    )
    if path is None:
        return False
    report.local_path = str(path)
    session.commit()
    return True


def queue_visual_evidence_candidates(session: Session, council_code: str) -> list[MonitoredReport]:
    """Part 6: which current, map-type MonitoredReport documents for this
    council have not yet had ANY Visual Evidence extracted from them -
    the operator's actual to-do list, worked through by hand via the
    existing app.visuals.extract_site_plans CLI
    (--report-id <id> --pdf <local_path>), never triggered automatically
    from here. Only documents that have actually been downloaded
    (local_path set) are realistic candidates - nothing for the Visual
    Evidence pipeline to render from a document that's only a discovered
    URL so far."""
    reports = list(session.execute(
        select(MonitoredReport).where(
            MonitoredReport.council_code == council_code,
            MonitoredReport.status == "current",
            MonitoredReport.policy_document_type.in_(MAP_LIKE_DOCUMENT_TYPES),
            MonitoredReport.local_path.is_not(None),
        )
    ).scalars())
    if not reports:
        return []
    report_ids = {r.id for r in reports}
    already_extracted = {
        v.monitored_report_id for v in session.execute(
            select(VisualEvidence).where(
                VisualEvidence.monitored_report_id.in_(report_ids), VisualEvidence.status == "current",
            )
        ).scalars()
    }
    return [r for r in reports if r.id not in already_extracted]
