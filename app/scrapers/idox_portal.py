"""Config-driven Idox Public Access scraper.

Ported from the prototype's auto_collect_months.py / extract_all_applications.py,
generalised so the base URL, search-form date field names, and results-per-page
handling all come from a CouncilConfig instead of being hardcoded per council.
"""
from __future__ import annotations

import calendar
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Page

from app.config import CouncilConfig
from app.scrapers.unit_filter import is_administrative_application_type, qualify

HEADERS = {"User-Agent": "Mozilla/5.0"}
WAIT_SECONDS = 1.0
REQUEST_DELAY_SECONDS = 0.4  # bumped from 0.25 after Stockport started 429'ing partway through a run
MAX_RETRIES = 4
BACKOFF_BASE_SECONDS = 5.0

RATE_LIMIT_PHRASES = [
    "too many requests",
    "unusual number of requests",
    "please try again in",
]

KEYVAL_RE = re.compile(r"keyVal=([^&]+)")


def generate_month_ranges(start_year: int, start_month: int, end_year: int, end_month: int) -> list[tuple[str, str]]:
    months = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        last_day = calendar.monthrange(year, month)[1]
        months.append((f"01/{month:02d}/{year}", f"{last_day:02d}/{month:02d}/{year}"))
        month += 1
        if month == 13:
            month = 1
            year += 1
    return months


def is_rate_limited(html_text: str) -> bool:
    lowered = html_text.lower()
    return any(phrase in lowered for phrase in RATE_LIMIT_PHRASES)


def get_with_retry(session: requests.Session, url: str, timeout: int = 30) -> requests.Response:
    """Some Idox instances (Stockport confirmed) start returning HTTP 429
    after a burst of requests, even at a modest request rate - retry with
    backoff (honouring Retry-After if the server sends one) rather than
    dropping the application entirely, which was silently losing hundreds
    of candidates on a single portal that just needed to be asked to slow down."""
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        response = session.get(url, timeout=timeout)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else BACKOFF_BASE_SECONDS * (attempt + 1)
            time.sleep(wait)
            last_error = requests.exceptions.HTTPError(f"429 after {attempt + 1} attempts: {url}")
            continue
        response.raise_for_status()
        return response
    raise last_error or requests.exceptions.HTTPError(f"Failed after {MAX_RETRIES} attempts: {url}")


def keyval_from_url(url: str) -> str | None:
    match = KEYVAL_RE.search(url)
    return match.group(1) if match else None


def extract_table_fields(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    data: dict[str, str] = {}
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) == 2:
            key = cells[0].get_text(strip=True)
            value = cells[1].get_text(strip=True)
            data[key] = value
    return data


def collect_result_links(page: Page, council: CouncilConfig, date_from: str, date_to: str) -> list[str]:
    """Run one date-range search on the advanced search form and page through
    all results, returning every applicationDetails.do summary URL found."""
    links: set[str] = set()

    page.goto(council.search_url, wait_until="networkidle", timeout=30000)
    page.fill(f'input[name="{council.date_start_field}"]', date_from)
    page.fill(f'input[name="{council.date_end_field}"]', date_to)
    page.click('input[value="Search"]')
    page.wait_for_load_state("networkidle", timeout=30000)

    try:
        page.select_option('select[name="searchCriteria.resultsPerPage"]', "100")
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(WAIT_SECONDS)
    except Exception:
        pass  # not all portals expose this control

    while True:
        html = page.content()
        if is_rate_limited(html):
            raise RuntimeError(f"Rate limited by portal while searching {date_from}-{date_to}")

        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            if "applicationDetails.do" in a["href"] and "keyVal=" in a["href"]:
                links.add(urljoin(page.url, a["href"]))

        next_links = page.locator("a", has_text="Next")
        if next_links.count() == 0:
            break
        try:
            next_links.first.click()
            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(WAIT_SECONDS)
        except Exception:
            break

    return sorted(links)


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


def fetch_application_detail(
    session: requests.Session, summary_url: str, unit_threshold: int, further_info_tab: str = "furtherInformation",
    request_delay_seconds: float = REQUEST_DELAY_SECONDS,
) -> ScrapedApplication:
    response = get_with_retry(session, summary_url)
    if is_rate_limited(response.text):
        raise RuntimeError(f"Rate limited fetching {summary_url}")

    fields = extract_table_fields(response.text)
    proposal = fields.get("Proposal", "")
    result = qualify(proposal, unit_threshold)

    further_info_url = summary_url.replace("activeTab=summary", f"activeTab={further_info_tab}")
    qualifies = result.qualifies
    classification = result.classification

    if result.qualifies:
        time.sleep(request_delay_seconds)
        fi_response = get_with_retry(session, further_info_url)
        fields.update(extract_table_fields(fi_response.text))

        # Second-stage check: the portal's own Application Type field is only
        # available now, and is a far more reliable "is this actually a new
        # development proposal" signal than proposal-text keyword matching -
        # overrides the first-stage decision if it says otherwise.
        if is_administrative_application_type(fields.get("Application Type")):
            qualifies = False
            classification = "Excluded - administrative application type"

    return ScrapedApplication(
        reference=fields.get("Reference"),
        fields=fields,
        summary_url=summary_url,
        further_info_url=further_info_url,
        keyval=keyval_from_url(summary_url),
        estimated_unit_count=result.unit_count,
        application_category=result.category,
        opportunity_classification=classification,
        qualifies=qualifies,
    )


def fetch_application_by_reference(
    page: Page, session: requests.Session, council: CouncilConfig, reference: str
) -> ScrapedApplication | None:
    """Targeted single-application lookup by exact reference, bypassing the
    normal date-range search - used to backfill a parent outline/full
    application a reserved matters filing cites when that parent predates
    our scraping window and was never scraped in its own right (see
    app.pipeline.run_weekly.stage_fetch_missing_parents). Confirmed real
    behaviour: Idox's reference search auto-redirects straight to the
    matching application's own detail page for an exact single match,
    rather than showing a results list - handled below, with a results-list
    fallback for anything that doesn't.

    Force-qualifies the result rather than trusting qualify() on the
    parent's own proposal text - we already know it's relevant because a
    confirmed qualifying scheme just cited it, and an outline permission's
    own wording ("Outline application (all matters reserved)") can
    legitimately have no unit count or REVIEW_KEYWORDS hit of its own."""
    page.goto(council.search_url, wait_until="networkidle", timeout=30000)
    page.fill('input[name="searchCriteria.reference"]', reference)
    page.click('input[value="Search"]')
    page.wait_for_load_state("networkidle", timeout=30000)

    # A single exact-reference match doesn't behave consistently across
    # council Idox instances - confirmed real cases both ways: Trafford
    # redirects straight to a clean applicationDetails.do URL, while Wigan
    # instead renders the single result INLINE on the advancedSearchResults
    # page itself, with every tab (Summary/Further Information/Contacts/...)
    # as a separate applicationDetails.do?activeTab=X link sharing the SAME
    # keyVal. Picking the alphabetically-first such link (e.g. "Contacts"
    # sorts before "Summary") silently returned an unrelated contacts-tab
    # page instead of the application - deduping by keyVal and explicitly
    # requesting activeTab=summary avoids that regardless of which tab
    # happened to sort first.
    keyval = keyval_from_url(page.url)
    if not keyval:
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        keyvals = {
            keyval_from_url(a["href"]) for a in soup.find_all("a", href=True)
            if "applicationDetails.do" in a["href"] and "keyVal=" in a["href"]
        }
        keyvals.discard(None)
        if not keyvals:
            return None
        keyval = sorted(keyvals)[0]
    summary_url = f"{council.base_url}/applicationDetails.do?activeTab=summary&keyVal={keyval}"

    detail = fetch_application_detail(
        session, summary_url, unit_threshold=0, further_info_tab=council.further_info_tab,
        request_delay_seconds=council.request_delay_seconds,
    )
    if not detail.qualifies:
        # further-info fields (Applicant, Agent, Application Type...) are
        # only fetched by fetch_application_detail when its own internal
        # qualify() passed - re-fetch with the same URL now that we're
        # forcing it through, so the parent record isn't left half-empty.
        time.sleep(council.request_delay_seconds)
        further_info_url = summary_url.replace("activeTab=summary", f"activeTab={council.further_info_tab}")
        fi_response = get_with_retry(session, further_info_url)
        detail.fields.update(extract_table_fields(fi_response.text))
    detail.qualifies = True
    return detail


def search_related_applications(page: Page, council: CouncilConfig, query: str) -> list[str]:
    """Free-text search across every application on the portal for
    citations of `query` (typically a verified parent reference like
    "DC/060928") - returns clean applicationDetails.do?activeTab=summary
    URLs for every distinct application found.

    NOT the same as Idox's own "Related Cases" tab (activeTab=relatedCases
    on a specific application) - that's officer-maintained and confirmed
    empty for real cases with a large, genuine family of linked filings
    (Stockport DC/060928: 0 official related cases, but ~30 applications
    found by searching its own reference, since child filings routinely
    name their parent in their own description - e.g. "Discharge of
    condition 24 of DC/060928", "Non-material amendment to planning
    permission DC/060928..."). This is how a large strategic site's full
    phase history - and therefore whether construction has actually started
    somewhere on it - gets discovered when the officer-maintained linking
    wasn't done.

    Playwright, not plain requests - confirmed the results-rendering step of
    this specific search flow returns 403 via a plain requests.Session even
    with a matching Referer (likely a session token only set via JS), while
    the identical flow works through a real browser (same as
    fetch_application_by_reference above). Reuses collect_result_links's
    proven link-extraction approach (match on the URL pattern, not a
    CSS class) rather than guessing brittle result-card selectors this
    function was never able to safely inspect (search itself triggered a
    portal-side "Too Many Requests" block during initial development -
    call this sparingly, at the same council.request_delay_seconds pace
    used everywhere else against this portal, and expect to sometimes
    need to back off further)."""
    simple_search_url = f"{council.base_url}/search.do?action=simple&searchType=Application"
    page.goto(simple_search_url, wait_until="networkidle", timeout=30000)
    page.fill('input[name="searchCriteria.simpleSearchString"]', query)
    page.click('input[type="submit"]')
    page.wait_for_load_state("networkidle", timeout=30000)

    keyvals: set[str] = set()
    while True:
        html = page.content()
        if is_rate_limited(html):
            raise RuntimeError(f"Rate limited by portal while searching for {query!r}")

        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            if "applicationDetails.do" in a["href"] and "keyVal=" in a["href"]:
                kv = keyval_from_url(a["href"])
                if kv:
                    keyvals.add(kv)

        next_links = page.locator("a", has_text="Next")
        if next_links.count() == 0:
            break
        try:
            next_links.first.click()
            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(WAIT_SECONDS)
        except Exception:
            break

    return [f"{council.base_url}/applicationDetails.do?activeTab=summary&keyVal={kv}" for kv in sorted(keyvals)]


def scrape_month(page: Page, council: CouncilConfig, date_from: str, date_to: str) -> list[ScrapedApplication]:
    """Full pipeline for one date range: search -> paginate -> fetch each
    application's detail fields -> apply the unit-count qualifying filter."""
    links = collect_result_links(page, council, date_from, date_to)

    session = requests.Session()
    session.headers.update(HEADERS)

    applications: list[ScrapedApplication] = []
    for i, url in enumerate(links, start=1):
        try:
            app = fetch_application_detail(
                session, url, council.unit_threshold, council.further_info_tab,
                request_delay_seconds=council.request_delay_seconds,
            )
            applications.append(app)
        except Exception as e:
            print(f"  [{i}/{len(links)}] error fetching {url}: {e}")
        time.sleep(council.request_delay_seconds)

    return applications
