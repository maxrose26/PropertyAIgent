"""Document discovery + download adapters.

Idox portals expose documents two different ways, controlled by
CouncilConfig.doc_system:

  "idox"        - documents are listed directly on the portal via
                   activeTab=documents, with plain <a href="..."> links to
                   the file (Stockport and most other councils). Discovery
                   and download are separate steps: this module returns
                   DocumentRow objects with a source_url, and
                   app.extraction.pdf_text.download_document fetches them.

  "idox_anite"  - the portal only links out to a separate legacy document
                   system ("Anite", Bury's setup). The link list is a
                   JS-rendered DataTable and each row's "download" control
                   is a client-side click handler (href="#"), not a real
                   URL - the actual document URL is only generated once you
                   click it and the browser starts a download. So for this
                   doc_system, discovery and download happen together,
                   driven by Playwright, and this module returns
                   CollectedDocument objects with a local_path already
                   populated (no separate download step needed).

  "arcus"       - Salford's Salesforce Experience Cloud portal (see
                   app.scrapers.arcus_portal). Direct-download links like
                   "idox" (confirmed plain-requests-fetchable, no session
                   needed) - the document rows themselves are already
                   collected by arcus_portal.fetch_application_detail while
                   on the Files tab, so this just wraps that list into
                   CollectedDocument for a uniform interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Page

from app.config import CouncilConfig
from app.extraction.pdf_text import USEFUL_DOC_TYPES, sanitise_filename, standardise_document_type

HEADERS = {"User-Agent": "Mozilla/5.0"}


@dataclass
class CollectedDocument:
    document_name: str
    doc_type_raw: str
    source_url: str | None = None  # set for "idox" - caller must download it
    local_path: Path | None = None  # set for "idox_anite" - already downloaded
    referer: str | None = None  # some portals (Oldham confirmed) 404 direct file requests without this


def _column_index_map(table) -> dict[str, int]:
    """Idox's documents table always leads with a "Select this document"
    checkbox column, so cells[0]/cells[1] are NOT the document name/type -
    confirmed every Oldham document got saved with the literal name "Select
    this document" (the checkbox's accessible label), which then collided
    every single document in an application onto one shared filename and
    silently destroyed all but the first download. Read the real column
    order from the header row instead of assuming a fixed position."""
    header_row = table.find("tr")
    if not header_row:
        return {}
    headers = [c.get_text(strip=True).lower() for c in header_row.find_all(["th", "td"])]
    return {name: i for i, name in enumerate(headers)}


def _find_document_links(soup: BeautifulSoup, base_url: str, referer: str) -> list[CollectedDocument]:
    rows: list[CollectedDocument] = []
    for table in soup.find_all("table"):
        columns = _column_index_map(table)
        name_idx = columns.get("description")
        type_idx = columns.get("document type")

        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            link = row.find("a", href=True)
            if not link or link["href"] in ("#", ""):
                continue

            doc_type = cells[type_idx].get_text(strip=True) if type_idx is not None and type_idx < len(cells) else ""
            doc_name = cells[name_idx].get_text(strip=True) if name_idx is not None and name_idx < len(cells) else ""
            if not doc_name:
                doc_name = doc_type or link.get_text(strip=True) or "document"

            rows.append(
                CollectedDocument(
                    document_name=doc_name,
                    doc_type_raw=doc_type,
                    source_url=urljoin(base_url, link["href"]),
                    referer=referer,
                )
            )
    return rows


def get_idox_documents(session: requests.Session, summary_url: str) -> list[CollectedDocument]:
    """Direct-listing councils: activeTab=documents on the main portal."""
    docs_url = summary_url.replace("activeTab=summary", "activeTab=documents")
    response = session.get(docs_url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    return _find_document_links(soup, docs_url, referer=docs_url)


def _find_anite_search_url(session: requests.Session, summary_url: str) -> str | None:
    docs_tab_url = summary_url.replace("activeTab=summary", "activeTab=externalDocuments")
    response = session.get(docs_tab_url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    link = soup.find("a", string=lambda t: t and "View associated documents" in t)
    return link["href"] if link else None


def get_anite_documents(page: Page, session: requests.Session, summary_url: str, dest_dir: Path) -> list[CollectedDocument]:
    """Bury-style councils. Downloads happen inline here (see module docstring).

    The document list is a jQuery DataTable that defaults to showing 10 rows
    per page - confirmed one real application actually had 111 documents,
    so without paging through, the vast majority (including the ones that
    actually matter: application form, planning statement, viability
    statement) were silently never downloaded. Bump the page size and walk
    every page."""
    search_url = _find_anite_search_url(session, summary_url)
    if not search_url:
        return []

    page.goto(search_url, wait_until="networkidle", timeout=30000)
    try:
        page.wait_for_selector("#searchResult tbody tr", timeout=10000)
    except Exception:
        return []  # no documents lodged for this application yet

    try:
        page.select_option('select[name="searchResult_length"]', "100")
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(500)
    except Exception:
        pass  # length selector not present - table is short enough to not paginate anyway

    dest_dir.mkdir(parents=True, exist_ok=True)
    collected: list[CollectedDocument] = []
    seen: set[tuple[str, str]] = set()

    while True:
        rows = page.query_selector_all("#searchResult tbody tr")
        for i, row in enumerate(rows):
            cells = row.query_selector_all("td.dataTableColumnPadding")
            cell_texts = [c.inner_text().strip() for c in cells]
            doc_type_raw = cell_texts[0] if cell_texts else ""
            doc_name = cell_texts[4] if len(cell_texts) > 4 and cell_texts[4] else (doc_type_raw or f"document_{i}")
            extension = cell_texts[-1] if cell_texts and cell_texts[-1].startswith(".") else ".pdf"

            dedupe_key = (doc_type_raw, doc_name)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            # Classify from the table cell text (already have it, no extra
            # request) before clicking to download - same reasoning as the
            # idox path in stage_documents: site plans/drawings/technical
            # reports are never read by extraction, no reason to download them.
            if standardise_document_type(doc_name, doc_type_raw) not in USEFUL_DOC_TYPES:
                continue

            link = row.query_selector("a.viewDocument")
            if not link:
                continue

            try:
                with page.expect_download(timeout=15000) as dl_info:
                    link.click()
                download = dl_info.value
                dest_path = dest_dir / f"{sanitise_filename(doc_name)}{extension}"
                download.save_as(dest_path)
                collected.append(CollectedDocument(document_name=doc_name, doc_type_raw=doc_type_raw, local_path=dest_path))
            except Exception as e:
                print(f"    could not download '{doc_name}': {e}")
                continue

        next_button = page.query_selector("#searchResult_next")
        if not next_button or "disabled" in (next_button.get_attribute("class") or ""):
            break
        try:
            next_button.click()
            page.wait_for_load_state("networkidle", timeout=10000)
            page.wait_for_timeout(500)
        except Exception:
            break

    return collected


def get_arcus_documents(page: Page, summary_url: str) -> list[CollectedDocument]:
    """Salford-style: navigate to the detail page (summary_url IS the full
    detail-page URL for this doc_system, unlike Idox's separate
    activeTab=documents convention), click the Files tab, read the rows."""
    from app.scrapers.arcus_portal import parse_document_rows  # local import: avoids a scrapers-internal cycle

    page.goto(summary_url, wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(1000)
    try:
        page.get_by_text("Files", exact=True).click()
        page.wait_for_timeout(1000)
    except Exception:
        return []
    rows = parse_document_rows(page)
    return [
        CollectedDocument(document_name=r.document_name, doc_type_raw="", source_url=r.source_url)
        for r in rows
    ]


def discover_documents(
    page: Page, session: requests.Session, council: CouncilConfig, summary_url: str, dest_dir: Path
) -> list[CollectedDocument]:
    if council.doc_system == "idox_anite":
        return get_anite_documents(page, session, summary_url, dest_dir)
    if council.doc_system == "arcus":
        return get_arcus_documents(page, summary_url)
    return get_idox_documents(session, summary_url)
