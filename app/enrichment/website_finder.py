"""Company website discovery + verification.

The prototype had ~5 overlapping passes here (DuckDuckGo search, AI query
builder, LinkedIn cross-check, multiple scoring scripts). This collapses
that into one linear search -> score -> verify function, keeping the part
that actually made results trustworthy: requiring 2+ significant company-
name terms to appear in the candidate domain before accepting it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import requests

BAD_DOMAINS = {
    "linkedin.com", "facebook.com", "twitter.com", "x.com", "instagram.com",
    "find-and-update.company-information.service.gov.uk", "companieshouse.gov.uk",
    "endole.co.uk", "duedil.com", "yell.com", "checkacompany.co.uk", "opencorporates.com",
    "bloomberg.com", "zoominfo.com", "crunchbase.com", "wikipedia.org", "gov.uk",
    "planning.bury.gov.uk", "planning.stockport.gov.uk",
    # Company-information aggregators - same problem as endole/duedil/
    # checkacompany above, just not caught yet: confirmed a real case,
    # "Crescent Investments LLC Limited" resolved to okredo.co.uk (a CH data
    # re-publisher, not the company's own site), which Apollo/Hunter then
    # searched for contacts and unsurprisingly found nobody at.
    "okredo.co.uk", "companycheck.co.uk", "companiesintheuk.co.uk", "creditsafe.com",
    "markerstudy.com", "thecompanycheck.com", "dnb.com", "cylex-uk.co.uk", "192.com",
    # VAT/company-number lookup aggregators - same failure mode as
    # okredo/companycheck above: confirmed a real case, "Peel Land
    # Developments Limited" resolved to vat-search.co.uk (whose SERP
    # snippet naturally repeats the company's own name, scoring well on
    # title/snippet term-matching despite zero name terms in the domain
    # itself) rather than the company's real site - correctly scored
    # "review" (not "verified"), so Apollo/Hunter were never actually
    # searched, but a director later turned out to be easily findable on
    # LinkedIn by hand, confirming the domain match itself was the failure,
    # not an absence of real contacts.
    "vat-search.co.uk", "vatsearch.co.uk", "check-vat-number.co.uk", "vatcheck.co.uk",
    # Confirmed immediately after fixing vat-search.co.uk above: the next-
    # highest-scoring candidate for the same company ("Peel Land
    # Developments Limited") was checkfree.co.uk - and not even a page about
    # the right company, but an unrelated one ("Cammell Laird
    # Shiprepairers..."), still ranking well purely on generic
    # company-lookup-site title/snippet text. This is proving to be a
    # recurring class of problem (several such aggregators found and added
    # here across multiple real cases now), not a one-off.
    "checkfree.co.uk",
}

STOPWORDS = {"the", "and", "of", "for", "group", "holdings", "homes", "properties", "developments", "development"}


def normalise_domain(url_or_domain: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url_or_domain.strip().lower()).split("/")[0]


def is_bad_domain(url_or_domain: str) -> bool:
    """Shared blocklist check - used both by the SerpAPI-based scorer below
    and by openai_company_lookup's web-search-grounded lookup, as a defensive
    backstop in case the model cites/echoes an aggregator's page instead of
    the company's own site despite being told not to."""
    domain = normalise_domain(url_or_domain)
    return any(bad in domain for bad in BAD_DOMAINS)


def _significant_terms(company_name: str) -> list[str]:
    name = re.sub(r"[^\w\s]", " ", company_name.lower())
    name = re.sub(r"\b(limited|ltd|llp|plc)\b", "", name)
    return [w for w in name.split() if len(w) > 2 and w not in STOPWORDS]


def _score_result(company_name: str, title: str, snippet: str, url: str) -> int:
    domain = normalise_domain(url)
    if is_bad_domain(domain):
        return -100

    score = 0
    if domain.endswith(".co.uk"):
        score += 3

    terms = _significant_terms(company_name)
    haystack = f"{title} {snippet}".lower()
    for term in terms:
        if term in haystack:
            score += 5
        if term in domain:
            score += 8

    score -= domain.count("/") * 1  # prefer shallow/homepage-like URLs
    return score


def search_candidates(serpapi_key: str, company_name: str) -> list[dict]:
    response = requests.get(
        "https://serpapi.com/search",
        params={"q": f'"{company_name}" official website', "engine": "google", "num": 10, "api_key": serpapi_key},
        timeout=30,
    )
    response.raise_for_status()
    results = response.json().get("organic_results", [])
    return [{"title": r.get("title", ""), "snippet": r.get("snippet", ""), "url": r.get("link", "")} for r in results]


@dataclass
class WebsiteResult:
    domain: str | None
    url: str | None
    status: str  # verified | review | not_found


def find_and_verify_website(serpapi_key: str, company_name: str) -> WebsiteResult:
    candidates = search_candidates(serpapi_key, company_name)
    if not candidates:
        return WebsiteResult(None, None, "not_found")

    scored = sorted(
        candidates,
        key=lambda c: _score_result(company_name, c["title"], c["snippet"], c["url"]),
        reverse=True,
    )
    best = scored[0]
    best_score = _score_result(company_name, best["title"], best["snippet"], best["url"])
    if best_score <= 0:
        return WebsiteResult(None, None, "not_found")

    domain = normalise_domain(best["url"])
    terms = _significant_terms(company_name)
    matches_in_domain = sum(1 for t in terms if t in domain)

    if len(terms) >= 2:
        status = "verified" if matches_in_domain >= 2 else "review"
    else:
        status = "verified" if matches_in_domain >= 1 else "review"

    return WebsiteResult(domain=domain, url=best["url"], status=status)


def find_person_linkedin(serpapi_key: str, full_name: str, company_name: str) -> str | None:
    """Apollo returns a LinkedIn URL directly per person - this is only for
    contacts sourced from Hunter/news search (neither of which do), so used
    sparingly."""
    name = full_name.strip()
    if not name:
        return None
    # Google's quoted-phrase match on the name isn't always exact -
    # confirmed a real case ("Sebastian Burrow") where the top result was a
    # completely different, unrelated person ("Bet Walters"). LinkedIn
    # profile result titles are consistently "FirstName LastName - Job -
    # Company | LinkedIn", so requiring the person's own (most distinctive)
    # surname to actually appear in the title is a cheap, effective guard
    # against accepting a wrong profile.
    last_name = name.split()[-1].lower()

    response = requests.get(
        "https://serpapi.com/search",
        params={
            "q": f'site:linkedin.com/in "{name}" "{company_name}"',
            "engine": "google", "num": 5, "api_key": serpapi_key,
        },
        timeout=30,
    )
    response.raise_for_status()
    results = response.json().get("organic_results", [])

    for result in results:
        url = result.get("link", "")
        if "linkedin.com/in/" not in url:
            continue
        if last_name not in result.get("title", "").lower():
            continue
        return url.split("?")[0]  # drop tracking params
    return None
