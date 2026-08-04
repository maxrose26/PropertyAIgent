"""Scraper for Arcus/Salesforce Experience Cloud planning portals.

Salford migrated off Idox to this system entirely - different vendor,
different rendering (Salesforce Lightning Web Components, heavily
JS-driven), so none of app.scrapers.idox_portal's HTML-form/BeautifulSoup
approach applies. Two things make this workable:

  - The ENTIRE search request (date range, filters) is a base64-encoded JSON
    blob in the URL's `c__q` param - discovered by filling the advanced
    search form once by hand and reading the URL it produced. build_search_url
    reconstructs this directly, so - unlike Idox - no form-filling is needed
    at all, just navigating straight to a constructed URL per date range.
  - Lightning components render inside shadow DOM, which breaks plain
    `document.querySelector` traversal in page.evaluate() (confirmed: it
    silently returns null where Playwright's own selector engine, e.g.
    eval_on_selector_all, finds the same element fine - only Playwright's
    own APIs pierce shadow boundaries). So result-list and detail-page
    extraction both parse Playwright's page.inner_text('body') output
    instead of hand-rolled DOM traversal - confirmed reliable, and both
    listing rows and detail-page fields render as clean, consistently
    labelled text blocks (detail-page fields are literally tab-separated
    "Label\\tValue" lines).

Document downloads ARE plain-requests-fetchable with no session/cookie
requirement (confirmed) - only discovery needs a browser, same shape as
Idox's "idox" doc_system, not Bury's click-to-download Anite adapter.
"""
from __future__ import annotations

import base64
import json
import re
import time
import urllib.parse
from dataclasses import dataclass

from playwright.sync_api import Page

from app.config import CouncilConfig
from app.scrapers.unit_filter import is_administrative_application_type, qualify

REGISTER_NAME = "Arcus_BE_Public_Register"
WAIT_SECONDS = 1.0
MAX_PAGES_PER_SEARCH = 60  # safety cap - a genuinely dense month tops out well under this


def build_search_url(base_url: str, date_from_iso: str, date_to_iso: str) -> str:
    """date_*_iso: "YYYY-MM-DD". "Valid Date" is this portal's equivalent of
    Idox's applicationValidated/Received date field."""
    payload = {
        "register": REGISTER_NAME,
        "requests": [{
            "registerName": REGISTER_NAME,
            "searchType": "advanced",
            "searchName": "Planning_Applications",
            "advancedSearchName": "PA_ADV_All",
            "searchFilters": [
                {"fieldName": "Salf_Site_Address__c", "fieldValue": "", "fieldDeveloperName": "PA_ADV_SiteAddress"},
                {"fieldName": "arcusbuiltenv__Proposal__c", "fieldValue": "", "fieldDeveloperName": "PA_ADV_Proposal"},
                {"fieldName": "arcusbuiltenv__Status__c", "fieldValue": "", "fieldDeveloperName": "PA_ADV_ApplicationStatus"},
                {"fieldName": "arcusbuiltenv__Wards__c", "fieldValue": "", "fieldDeveloperName": "PA_ADV_Ward"},
                {"fieldName": "arcusbuiltenv__PS_Scale__c", "fieldValue": "", "fieldDeveloperName": "PA_ADV_Application_Group"},
                {"fieldName": "arcusbuiltenv__Type__c", "fieldValue": "", "fieldDeveloperName": "PA_ADV_ApplicationType"},
                {"fieldName": "arcusbuiltenv__Valid_Date__c", "fieldValue": date_from_iso, "fieldDeveloperName": "PA_ADV_DateValidFrom"},
                {"fieldName": "arcusbuiltenv__Valid_Date__c", "fieldValue": date_to_iso, "fieldDeveloperName": "PA_ADV_DateValidTo"},
                {"fieldName": "arcusbuiltenv__Decision_Notice_Sent_Date_Manual__c", "fieldValue": "", "fieldDeveloperName": "PA_ADV_DecisionNoticeSentDateFrom"},
                {"fieldName": "arcusbuiltenv__Decision_Notice_Sent_Date_Manual__c", "fieldValue": "", "fieldDeveloperName": "PA_ADV_DecisionNoticeSentDateTo"},
            ],
        }],
    }
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    q = urllib.parse.quote(encoded, safe="")
    return f"{base_url}/s/register-view?c__q={q}&c__r={REGISTER_NAME}"


_RECORD_START_RE = re.compile(r"(?=Reference\s*\n)", re.I)
_REFERENCE_RE = re.compile(r"Reference\s*\n(\S+)", re.I)


def _field(chunk: str, label: str, until: str | None = None) -> str | None:
    """Looks up ONE field within a single record's text chunk, independently
    of every other field - deliberately not one long sequential regex over
    the whole record. Confirmed real, DIFFERENT template quirks across
    three councils, each of which broke a strict end-to-end sequence:
    Salford has no separate "Decision" line and always shows "Decision
    date"; Rochdale adds a "Decision\\n{outcome}\\n" line only once decided,
    and capitalises it "Decision Date"; Manchester omits the "Decision
    date" line ENTIRELY for undecided applications rather than leaving it
    blank. Matching each field independently means a missing/reordered/
    differently-cased line only costs that one field, not the whole record."""
    if until:
        m = re.search(rf"{label}\s*\n(.*?)\n\s*{until}\s*\n", chunk, re.I | re.S)
    else:
        m = re.search(rf"{label}\s*\n([^\n]*)", chunk, re.I)
    return m.group(1).strip() if m else None


def _parse_result_page(body_text: str, ref_to_url: dict[str, str]) -> list[dict]:
    rows = []
    for chunk in _RECORD_START_RE.split(body_text):
        ref_match = _REFERENCE_RE.match(chunk)
        if not ref_match:
            continue
        reference = ref_match.group(1).strip()
        row = {
            "reference": reference,
            "application_type": _field(chunk, "Application type"),
            # Salford's addresses render as one line, but Rochdale's/
            # Manchester's split street/town/postcode onto separate lines -
            # lazy multi-line capture up to the next known header handles both.
            "address": _field(chunk, "Site address", until="Description"),
            "description": _field(chunk, "Description", until="Status"),
            "status": _field(chunk, "Status"),
            # Negative lookahead avoids this ALSO matching "Decision date" -
            # "Decision" alone is only present once a decision has been made.
            "decision": _field(chunk, r"Decision(?! date)"),
            "decision_date": _field(chunk, "Decision date"),
        }
        row["detail_url"] = ref_to_url.get(reference)
        rows.append(row)
    return rows


def _walk_result_pages(page: Page) -> list[dict]:
    """Walks every page of results (Next link) on the CURRENTLY LOADED
    results page and returns one dict per application - shared by
    collect_result_rows (date-range advanced search) and
    search_related_applications (quick search) below, which only differ in
    how they construct the URL navigated to before calling this."""
    rows: list[dict] = []
    seen_refs: set[str] = set()

    for _ in range(MAX_PAGES_PER_SEARCH):
        text = page.inner_text("body")
        links = page.eval_on_selector_all(
            "a",
            "els => els.map(e => ({text: e.innerText.trim(), href: e.href}))"
            ".filter(l => l.href.includes('/detail/'))",
        )
        ref_to_url = {l["text"]: l["href"] for l in links}
        for row in _parse_result_page(text, ref_to_url):
            if row["reference"] in seen_refs:
                continue
            seen_refs.add(row["reference"])
            rows.append(row)

        # exact=True fails here: the pagination link's accessible text is
        # "Next" plus a visually-hidden ("slds-hide") suffix span reading
        # "set of pages" for screen readers, so its full text content is
        # never exactly "Next" - confirmed a real case where this silently
        # stopped pagination after page 1 every time, with no error.
        next_link = page.locator("a.pr-pagination__link", has_text="Next")
        if next_link.count() == 0:
            break
        try:
            classes = next_link.first.evaluate("el => el.className") or ""
        except Exception:
            break
        if "disabled" in classes:
            break
        try:
            next_link.first.click()
            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_timeout(WAIT_SECONDS * 1000)
        except Exception:
            break

    return rows


def collect_result_rows(page: Page, council: CouncilConfig, date_from_iso: str, date_to_iso: str) -> list[dict]:
    """Full pipeline for one date range: build the search URL, walk every
    results page (Next link), return one dict per application (reference,
    application_type, address, description, status, decision_date, detail_url)."""
    url = build_search_url(council.base_url, date_from_iso, date_to_iso)
    page.goto(url, wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(WAIT_SECONDS * 1000)
    return _walk_result_pages(page)


def build_quick_search_url(base_url: str, query: str) -> str:
    """Arcus's "quick search" (a single free-text box, distinct from the
    date-range advanced search build_search_url constructs) - confirmed real
    payload shape by submitting the quick-search box by hand and reading the
    resulting URL. Matches build_search_url's own base64-JSON-in-c__q
    pattern, just with searchType "quick" and a single searchTerm instead of
    the advanced form's date-range filters."""
    payload = {
        "register": REGISTER_NAME,
        "requests": [{
            "registerName": REGISTER_NAME, "searchType": "quick",
            "searchTerm": query, "searchName": "Planning_Applications",
        }],
    }
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    q = urllib.parse.quote(encoded, safe="")
    return f"{base_url}/s/register-view?c__q={q}&c__r={REGISTER_NAME}"


def search_related_applications(page: Page, council: CouncilConfig, query: str) -> list[dict]:
    """Free-text search across every application on the portal for
    citations of `query` (typically a verified reference) - the Arcus
    equivalent of app.scrapers.idox_portal.search_related_applications,
    using the same "quick search" mechanism fetch_application_by_reference
    below uses for an exact-reference lookup. Unlike that function, which
    discards every row except the one whose OWN reference matches exactly,
    this keeps every result the search returns and walks every results page
    - a citing application's own reference is obviously different from the
    one being searched for, and a genuinely well-cited parent can have many
    more results than fit on one page (confirmed on the Idox side: Wigan's
    North Leigh site alone returned 31)."""
    url = build_quick_search_url(council.base_url, query)
    page.goto(url, wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(WAIT_SECONDS * 1000)
    return _walk_result_pages(page)


DETAIL_FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z /]*?)\t\s*(.*?)\s*$")


def _parse_detail_fields(body_text: str) -> dict[str, str]:
    # Keys lowercased - different councils on this same Arcus/Salesforce
    # platform render otherwise-identical fields with different casing
    # (confirmed real case: Manchester's "Valid date" vs Rochdale/Salford's
    # "Valid Date"), so an exact-case lookup silently missed it for
    # Manchester specifically - see _detail_field() below.
    fields: dict[str, str] = {}
    for line in body_text.split("\n"):
        m = DETAIL_FIELD_RE.match(line)
        if m:
            fields[m.group(1).strip().lower()] = m.group(2).strip()
    return fields


def _detail_field(detail_fields: dict[str, str], *labels: str) -> str:
    """First non-empty value among several accepted label variants for the
    same field - confirmed real case: Manchester labels its decision date
    "Decision notice sent date" where Rochdale/Salford use "Decision date"
    for the same concept, which silently left decision_issued_date empty
    for all 79 of Manchester's decided applications (every lapse/
    commencement-deadline calculation, phase "latest grant" selection, and
    "most recent first" sort depends on this field).

    Named distinctly from the OTHER _field() above (chunk-based, for
    result-list rows) rather than reusing that name - confirmed a real
    regression from doing exactly that once already: this function silently
    shadowed the result-list one in the module namespace, so
    _parse_result_page's own _field(chunk, "Application type") calls
    silently started calling THIS one instead, passing a plain string where
    a dict was expected - breaking every date-range scrape (collect_result_rows)
    and related-application search (search_related_applications) for all
    three Arcus councils until caught by a full 3-year Rochdale backfill."""
    for label in labels:
        value = detail_fields.get(label.lower())
        if value:
            return value
    return ""


@dataclass
class ArcusDocumentRow:
    document_name: str
    date: str
    source_url: str


MAX_FILE_PAGES = 20  # safety cap - a genuinely huge application (100+ docs) tops out well under this


def parse_document_rows(page: Page) -> list[ArcusDocumentRow]:
    """Walks every Files-tab page (Next link) - confirmed a real case where
    a 126-unit scheme showed only 1 of its real 111 documents (the default
    page size is 20), because this previously only ever read the current
    page. Application Form, Planning Statement, Decision Notice etc. -
    everything the extraction pipeline actually reads - were silently lost
    for any Salford application with more than one page of files, which at
    this portal's document volumes is most of them."""
    row_re = re.compile(r"^(\d{1,2}/\d{1,2}/\d{4})\t(.+?)\tDownload", re.M)
    docs: list[ArcusDocumentRow] = []
    seen_urls: set[str] = set()

    for _ in range(MAX_FILE_PAGES):
        links = page.eval_on_selector_all(
            "a",
            "els => els.map(e => ({text: e.innerText.trim(), href: e.href}))"
            ".filter(l => l.href.includes('/servlet.shepherd/'))",
        )
        text = page.inner_text("body")
        # Each file row renders as "date\tdescription\tDownload (...)" on one
        # line, in the same order as the filtered download links above.
        descriptions = row_re.findall(text)
        for i, link in enumerate(links):
            if link["href"] in seen_urls:
                continue
            seen_urls.add(link["href"])
            date, desc = descriptions[i] if i < len(descriptions) else ("", "")
            docs.append(ArcusDocumentRow(document_name=desc or f"document_{i}", date=date, source_url=link["href"]))

        next_link = page.locator("a.pr-pagination__link", has_text="Next")
        if next_link.count() == 0:
            break
        try:
            classes = next_link.first.evaluate("el => el.className") or ""
        except Exception:
            break
        if "disabled" in classes:
            break
        try:
            next_link.first.click()
            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_timeout(1000)
        except Exception:
            break

    return docs


@dataclass
class ScrapedApplication:
    reference: str | None
    fields: dict[str, str]
    summary_url: str
    further_info_url: str
    keyval: str | None
    estimated_unit_count: int | None
    application_category: str
    opportunity_classification: str
    qualifies: bool
    documents: list[ArcusDocumentRow]


def fetch_application_detail(
    page: Page, row: dict, unit_threshold: int, force_qualify: bool = False
) -> ScrapedApplication:
    """force_qualify: used by fetch_application_by_reference below to pull
    full detail (Applicant/Agent/Documents...) for a parent application
    cited by a reserved matters filing, regardless of what its own
    proposal text would otherwise qualify() as - an outline permission's
    own wording can legitimately have no unit count or REVIEW_KEYWORDS hit,
    but we already know it's relevant because a confirmed qualifying scheme
    just cited it."""
    proposal = row.get("description", "")
    result = qualify(proposal, unit_threshold)

    fields = {
        "Reference": row["reference"],
        "Address": row.get("address", ""),
        "Proposal": proposal,
        "Application Type": row.get("application_type", ""),
        "Status": row.get("status", ""),
    }
    documents: list[ArcusDocumentRow] = []
    qualifies = result.qualifies or force_qualify
    classification = result.classification

    if qualifies and row.get("detail_url"):
        page.goto(row["detail_url"], wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(WAIT_SECONDS * 1000)
        detail_text = page.inner_text("body")
        detail_fields = _parse_detail_fields(detail_text)
        fields.update({
            "Application Type": _detail_field(detail_fields, "Application type") or fields["Application Type"],
            "Applicant Name": _detail_field(detail_fields, "Applicant"),
            "Status": _detail_field(detail_fields, "Status") or fields["Status"],
            "Agent": _detail_field(detail_fields, "Agent"),
            "Decision Issued Date": _detail_field(detail_fields, "Decision date", "Decision notice sent date"),
            "Decision": _detail_field(detail_fields, "Decision"),
            "Application Received": _detail_field(detail_fields, "Valid Date"),
            "Ward": _detail_field(detail_fields, "Ward"),
            # Statutory target decision date - confirmed present on all 3
            # Arcus councils, but under two different labels (Manchester/
            # Salford: "Target decision date", Rochdale: "Decision Date
            # Due"). Idox portals don't expose an equivalent public field -
            # see lapse_tracking.estimate_statutory_decision_date for the
            # computed fallback used there instead.
            "Expected Decision Date": _detail_field(detail_fields, "Target decision date", "Decision Date Due"),
        })

        if is_administrative_application_type(fields.get("Application Type")):
            qualifies = False
            classification = "Excluded - administrative application type"
        else:
            try:
                page.get_by_text("Files", exact=True).click()
                page.wait_for_timeout(WAIT_SECONDS * 1000)
                documents = parse_document_rows(page)
            except Exception:
                documents = []

    return ScrapedApplication(
        reference=fields.get("Reference"),
        fields=fields,
        summary_url=row.get("detail_url") or "",
        further_info_url=row.get("detail_url") or "",
        keyval=None,
        estimated_unit_count=result.unit_count,
        application_category=result.category,
        opportunity_classification=classification,
        qualifies=qualifies,
        documents=documents,
    )


def fetch_application_by_reference(page: Page, council: CouncilConfig, reference: str) -> ScrapedApplication | None:
    """Targeted single-application lookup by exact reference via Arcus's
    "quick search" (a single free-text box, distinct from the date-range
    advanced search build_search_url constructs) - used to backfill a
    parent outline/full application a reserved matters filing cites when
    that parent predates our scraping window and was never scraped in its
    own right (see app.pipeline.run_weekly.stage_fetch_missing_parents).
    Confirmed real payload shape by submitting the quick-search box by hand
    and reading the resulting URL - matches build_search_url's own
    base64-JSON-in-c__q pattern, just with searchType "quick" and a single
    searchTerm instead of the advanced form's date-range filters."""
    url = build_quick_search_url(council.base_url, reference)
    page.goto(url, wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(WAIT_SECONDS * 1000)

    text = page.inner_text("body")
    links = page.eval_on_selector_all(
        "a",
        "els => els.map(e => ({text: e.innerText.trim(), href: e.href}))"
        ".filter(l => l.href.includes('/detail/'))",
    )
    ref_to_url = {l["text"]: l["href"] for l in links}
    rows = _parse_result_page(text, ref_to_url)
    matching = [r for r in rows if r["reference"].strip().upper() == reference.strip().upper()]
    if not matching:
        return None

    return fetch_application_detail(page, matching[0], unit_threshold=0, force_qualify=True)


def scrape_month(page: Page, council: CouncilConfig, date_from_iso: str, date_to_iso: str) -> list[ScrapedApplication]:
    rows = collect_result_rows(page, council, date_from_iso, date_to_iso)
    applications: list[ScrapedApplication] = []
    for i, row in enumerate(rows, start=1):
        try:
            app = fetch_application_detail(page, row, council.unit_threshold)
            applications.append(app)
        except Exception as e:
            print(f"  [{i}/{len(rows)}] error fetching {row.get('reference')}: {e}")
        time.sleep(WAIT_SECONDS)
    return applications
