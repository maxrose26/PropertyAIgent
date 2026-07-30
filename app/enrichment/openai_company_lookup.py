"""Web-search-grounded developer/website confirmation via OpenAI's Responses
API, tried BEFORE the SerpAPI heuristic scorer in contact_pipeline.enrich_company.

The SerpAPI approach only scores a result's title/snippet text against the
company name - it can't tell a company-lookup aggregator (whose SERP snippet
naturally repeats the company's own name) from the company's real site.
Confirmed real failures: "Crescent Investments LLC Limited" -> okredo.co.uk,
"Peel Land Developments Limited" -> vat-search.co.uk, then checkfree.co.uk
(a DIFFERENT, unrelated company entirely) on the next-best candidate. A model
with a web-search tool can read a result's actual page content, not just
score snippet text, and correctly found peelland.co.uk for the Peel case on
the first try. Companies House matching (see contact_pipeline.enrich_company)
stays the fallback/safety net if this doesn't produce a confident answer, not
the primary path.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from openai import OpenAI

MODEL = "gpt-4o-mini"

_SCHEMA = {
    "type": "object",
    "properties": {
        "confirmed_developer_name": {"type": ["string", "null"]},
        "website_domain": {"type": ["string", "null"]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "reasoning": {"type": "string"},
    },
    "required": ["confirmed_developer_name", "website_domain", "confidence", "reasoning"],
    "additionalProperties": False,
}


@dataclass
class AiCompanyLookupResult:
    confirmed_developer_name: str | None
    website_domain: str | None
    confidence: str  # high | medium | low
    reasoning: str


def confirm_developer_and_website(
    client: OpenAI, company_name: str, ch_company_number: str | None = None
) -> AiCompanyLookupResult:
    company_ref = f'"{company_name}"'
    if ch_company_number:
        company_ref += f" (Companies House number {ch_company_number})"

    prompt = f"""
Identify the REAL corporate website for the UK company {company_ref}.

Rules:
- website_domain must be the company's OWN official site - never a company-lookup, VAT-lookup, credit-check, or
  business-directory aggregator (e.g. companieshouse.gov.uk, endole.co.uk, companycheck.co.uk, vat-search.co.uk,
  checkfree.co.uk, bymetric.com, okredo.co.uk, zoominfo.com, dnb.com, or any similar site that just republishes
  public company data rather than being the company's own site).
- Many property-development applicants are single-site SPVs (e.g. "Riverside Developments (No.3) Limited") with no
  website of their own. If so, identify the actual parent developer/group behind it (check Companies House's
  persons-with-significant-control data, news coverage, or the group's own site listing its subsidiaries) and give
  confirmed_developer_name as that parent, with website_domain as the PARENT's own official site.
- If confirmed_developer_name is the same entity as the company above (not a different parent), just repeat the
  company name.
- If you cannot confidently identify a real, non-aggregator website, set website_domain to null and confidence to
  low rather than guessing.
- Give the domain only (e.g. "example.co.uk"), not a full URL.
"""
    response = client.responses.create(
        model=MODEL,
        input=prompt,
        tools=[{"type": "web_search_preview"}],
        text={"format": {"type": "json_schema", "name": "company_lookup", "schema": _SCHEMA, "strict": True}},
    )
    data = json.loads(response.output_text)
    return AiCompanyLookupResult(**data)


_LINKEDIN_SCHEMA = {
    "type": "object",
    "properties": {
        "linkedin_url": {"type": ["string", "null"]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "reasoning": {"type": "string"},
    },
    "required": ["linkedin_url", "confidence", "reasoning"],
    "additionalProperties": False,
}


@dataclass
class AiLinkedinResult:
    linkedin_url: str | None
    confidence: str  # high | medium | low
    reasoning: str


def confirm_linkedin_profile(
    client: OpenAI, full_name: str, company_name: str, job_title: str | None = None
) -> AiLinkedinResult:
    """Tried before website_finder.find_person_linkedin's SerpAPI-based
    lookup (see contact_pipeline) - that approach only checks whether the
    person's surname appears in a search result's title, which confirmed a
    real false positive (a completely unrelated LinkedIn profile accepted
    for "Sebastian Burrow" purely because the surname check hadn't been
    added yet) and, once that guard was added, several genuine real
    profiles going unmatched instead (too strict a net once results don't
    happen to rank in the top few). A model that can read a candidate
    profile's actual content - job history, current employer - and
    cross-check it against other sources (confirmed: it corroborated one
    real match against theorg.com's org-chart data) is a stronger signal
    than a single title-substring check either way."""
    role_line = f", {job_title}" if job_title else ""
    prompt = (
        f"Find the LinkedIn profile URL for {full_name}{role_line} at {company_name}. Only give a URL if you can "
        "confirm it is genuinely this specific person (matching name AND role/employer, cross-checking other "
        "sources if the profile itself is ambiguous) - if unsure or not found, set linkedin_url to null rather "
        "than guessing."
    )
    response = client.responses.create(
        model=MODEL,
        input=prompt,
        tools=[{"type": "web_search_preview"}],
        text={"format": {"type": "json_schema", "name": "linkedin_lookup", "schema": _LINKEDIN_SCHEMA, "strict": True}},
    )
    data = json.loads(response.output_text)
    return AiLinkedinResult(**data)
