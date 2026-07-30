"""Companies House matching + officer lookup.

Ported from companies_house_enrichment.py / companies_house_officers_scraper.py.
This was the most reliable layer in the prototype - free-text applicant name
normalisation + fuzzy match against the official CH search API, then pull
active officers as director-name candidates for the contact-enrichment stage.
rapidfuzz replaces the prototype's hand-rolled substring/word-overlap scorer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import requests
from rapidfuzz import fuzz

CH_API_BASE = "https://api.company-information.service.gov.uk"

LEGAL_SUFFIXES = re.compile(
    r"\b(limited|ltd|llp|plc|holdings|group|homes|properties|developments?)\b", re.I
)


def normalise_name(name: str) -> str:
    name = (name or "").lower()
    name = re.sub(r"[^\w\s]", " ", name)
    name = LEGAL_SUFFIXES.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


_LTD_BOUNDARY_RE = re.compile(r"(?:ltd|limited|llp|plc)\b", re.I)


def split_joint_companies(applicant_name: str) -> list[str]:
    """Two distinct joint-applicant phrasings seen in practice: "X Ltd Y Ltd"
    with no conjunction (split right after each legal suffix, when followed
    by whitespace then a new capitalised word), and an explicit "X and Y"
    conjunction - confirmed a real case ("MCI Developments and JS Hennessey
    (1999) RBS") where treating the whole string as one company name meant
    Companies House/website lookups searched for a name matching no real
    single company, landing on an unrelated fuzzy CH match and a genealogy-
    site "website". The " and " split risks incorrectly breaking up a
    genuine single trading name that happens to contain "and" (e.g. "Turner
    and Townsend") - accepted as a real but rarer failure mode than silently
    mis-enriching every joint applicant, which was the status quo (this
    function existed but was never actually called anywhere - and its
    original regex would have raised a PatternError the first time it was,
    since Python's re module rejects variable-width lookbehind and "ltd"/
    "limited"/"llp"/"plc" are different lengths)."""
    boundaries = []
    for match in _LTD_BOUNDARY_RE.finditer(applicant_name):
        rest = applicant_name[match.end():]
        stripped = rest.lstrip()
        # A genuine boundary needs whitespace before the next name (not
        # "Ltd." glued straight onto punctuation) and that next name must
        # start with a capital letter.
        if stripped and stripped[0].isupper() and len(stripped) < len(rest):
            boundaries.append(match.end())
    if boundaries:
        parts = []
        start = 0
        for b in boundaries:
            parts.append(applicant_name[start:b].strip())
            start = b
        parts.append(applicant_name[start:].strip())
        parts = [p for p in parts if p]
        if len(parts) > 1:
            return parts
    parts = re.split(r"\s+and\s+", applicant_name, flags=re.I)
    return [p.strip() for p in parts if p.strip()]


def match_score(a: str, b: str) -> float:
    return fuzz.token_sort_ratio(normalise_name(a), normalise_name(b))


@dataclass
class CompanyMatch:
    company_number: str
    ch_name: str
    status: str | None
    incorporation_date: str | None
    registered_address: str | None
    confidence: float


def search_company(api_key: str, name: str) -> list[dict]:
    response = requests.get(
        f"{CH_API_BASE}/search/companies",
        params={"q": name, "items_per_page": 5},
        auth=(api_key, ""),
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("items", [])


def best_match(api_key: str, applicant_name: str, min_score: float = 60.0) -> CompanyMatch | None:
    candidates = search_company(api_key, applicant_name)
    if not candidates:
        return None

    scored = [(match_score(applicant_name, c.get("title", "")), c) for c in candidates]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    best_score, best = scored[0]

    if best_score < min_score:
        return None

    address_parts = best.get("address", {})
    address = ", ".join(
        str(address_parts.get(k, "")) for k in ("premises", "address_line_1", "address_line_2", "locality", "postal_code")
        if address_parts.get(k)
    )

    return CompanyMatch(
        company_number=best["company_number"],
        ch_name=best.get("title", ""),
        status=best.get("company_status"),
        incorporation_date=best.get("date_of_creation"),
        registered_address=address,
        confidence=best_score,
    )


@dataclass
class OfficerRecord:
    full_name: str
    role: str | None
    appointed_on: str | None
    resigned_on: str | None
    appointments_url: str | None = None  # cross-company appointments, see get_officer_other_appointments
    other_appointments: list[str] = field(default_factory=list)  # populated by enrich_company, if any found


def normalise_officer_name(ch_name: str) -> str:
    """CH officer names come as "SURNAME, Forename Middlename[, Title]" -
    e.g. "BOSTOCK, Nicholas Richard Swinford" or "DALY, Jennifer, Ms." -
    convert to a normal "Forename Middlename Surname" display form."""
    parts = [p.strip() for p in ch_name.split(",")]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return ch_name.strip()
    surname, forenames = parts[0], parts[1]
    return f"{forenames.title()} {surname.title()}"


def get_active_officers(api_key: str, company_number: str, limit: int = 10) -> list[OfficerRecord]:
    response = requests.get(
        f"{CH_API_BASE}/company/{company_number}/officers",
        params={"items_per_page": limit},
        auth=(api_key, ""),
        timeout=30,
    )
    response.raise_for_status()
    items = response.json().get("items", [])

    officers = []
    for item in items:
        if item.get("resigned_on"):
            continue
        officers.append(
            OfficerRecord(
                full_name=normalise_officer_name(item.get("name", "")),
                role=item.get("officer_role"),
                appointed_on=item.get("appointed_on"),
                resigned_on=item.get("resigned_on"),
                appointments_url=item.get("links", {}).get("officer", {}).get("appointments"),
            )
        )
    return officers


# A director isn't necessarily an owner - confirmed a real case: "Crescent
# Investments LLC Limited"'s only director (Mohammed Bilal Patel, appointed
# via nominee-style arrangement) owns 0% of it, while the actual PSC -
# Anisa Ahmed, 75-100% of shares/voting rights, right to appoint/remove
# directors - isn't listed as a director at all. PSC data answers "who
# actually owns/controls this" directly; officer role only answers "who's
# named as running it day-to-day", which is a materially different and
# sometimes misleading question for outreach purposes.
@dataclass
class PSCRecord:
    name: str
    kind: str  # individual | corporate-entity | legal-person | super-secure
    natures_of_control: list[str] = field(default_factory=list)
    ceased: bool = False
    # Only set when kind indicates a corporate/legal-entity PSC - the real
    # owner is another company, not a person, and can itself be looked up.
    identification_company_number: str | None = None


def get_persons_with_significant_control(api_key: str, company_number: str, limit: int = 10) -> list[PSCRecord]:
    response = requests.get(
        f"{CH_API_BASE}/company/{company_number}/persons-with-significant-control",
        params={"items_per_page": limit},
        auth=(api_key, ""),
        timeout=30,
    )
    if response.status_code == 404:
        return []  # some companies (esp. very new ones) have no PSC statement filed yet
    response.raise_for_status()
    items = response.json().get("items", [])

    records = []
    for item in items:
        kind_raw = item.get("kind", "")
        kind = kind_raw.replace("-person-with-significant-control", "")
        identification = item.get("identification", {})
        records.append(
            PSCRecord(
                name=item.get("name", "Unknown"),
                kind=kind,
                natures_of_control=item.get("natures_of_control", []),
                ceased=bool(item.get("ceased")),
                identification_company_number=identification.get("registration_number"),
            )
        )
    return records


def get_officer_other_appointments(api_key: str, appointments_url: str) -> list[dict]:
    """Cross-references one director across every company they're appointed
    to (via the officer.appointments link already present on each officer
    record from get_active_officers) - reveals SPV networks a single
    company lookup can't show, e.g. confirmed a real case where one
    director of a small applicant company turned out to also direct 4 other
    "Holdings"-style companies. Returns raw dicts (company_name,
    company_number, officer_role, resigned_on) - kept lightweight since this
    is investigative/on-demand, not persisted."""
    if not appointments_url:
        return []
    response = requests.get(f"{CH_API_BASE}{appointments_url}", auth=(api_key, ""), timeout=30)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    results = []
    for item in response.json().get("items", []):
        appointed_to = item.get("appointed_to", {})
        results.append({
            "company_name": appointed_to.get("company_name"),
            "company_number": appointed_to.get("company_number"),
            "officer_role": item.get("officer_role"),
            "resigned_on": item.get("resigned_on"),
        })
    return results
