"""Build-status detection + postcode geocoding.

Neither of these needed a scraper rewrite - both are free/cheap UK open-data
lookups keyed off the site's postcode:

- EPC Open Data register: postcode-level certificates are investigative context,
  not scheme-matched completion evidence.
- postcodes.io: free, no API key, used purely to plot sites on the map.
- Nominatim (OpenStreetMap): free, no API key, fallback for sites with no
  postcode in their address at all - common for vacant/greenfield land,
  which often isn't assigned a postcode until near completion (confirmed:
  128 real sites, all large "Land At/Off X" parcels with no postcode
  substring anywhere in the source address text - not a regex-extraction
  bug, the source data genuinely has none). Rate-limited to 1 req/sec and
  requires an identifying User-Agent per Nominatim's usage policy.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import requests

EPC_SEARCH_URL = "https://api.get-energy-performance-data.communities.gov.uk/api/domestic/search"
POSTCODES_IO_URL = "https://api.postcodes.io/postcodes"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "UKPlanningDealFinder/1.0 (contact: maxrose26@gmail.com)"
NOMINATIM_MIN_INTERVAL_SECONDS = 1.1


# Same non-geocodable boilerplate app.pipeline.site_linking.normalise_address
# strips for site-matching purposes, reused here rather than duplicated -
# confirmed via direct testing that the raw "Land At X, council" phrasing
# returns zero Nominatim matches, while stripping the prefix resolves a
# majority of real cases (e.g. "Land At Southlink Oldham" -> "Southlink,
# Oldham" successfully resolves; a handful of very locally-known site names
# still don't resolve even stripped - a real, expected limit of free-text
# geocoding, not a bug).
_NOISE_PREFIXES = [
    "land adjacent to", "land to the rear of", "land to the front of",
    "land east of", "land west of", "land north of", "land south of",
    "land at", "site at", "site of", "the former", "former",
]


def _strip_noise_prefix(address: str) -> str:
    text = address.strip()
    lowered = text.lower()
    for prefix in _NOISE_PREFIXES:
        if lowered.startswith(prefix + " "):
            return text[len(prefix):].strip()
    return text


def geocode_postcode(postcode: str) -> tuple[float, float] | None:
    if not postcode:
        return None
    response = requests.get(f"{POSTCODES_IO_URL}/{postcode.strip().replace(' ', '')}", timeout=15)
    if response.status_code != 200:
        return None
    result = response.json().get("result")
    if not result:
        return None
    return result["latitude"], result["longitude"]


def geocode_address(address: str) -> tuple[float, float, str | None] | None:
    """Fallback for sites with no postcode at all - free-text geocode the
    display address via Nominatim instead. Returns (lat, lon, postcode) -
    postcode is whatever Nominatim's structured address details include for
    the match, if any (lets a successful geocode also backfill site.postcode
    for a later EPC build-status lookup, which is postcode-only)."""
    if not address:
        return None
    query = f"{_strip_noise_prefix(address)}, UK"
    response = requests.get(
        NOMINATIM_SEARCH_URL,
        params={"q": query, "format": "jsonv2", "addressdetails": 1, "countrycodes": "gb", "limit": 1},
        headers={"User-Agent": NOMINATIM_USER_AGENT},
        timeout=15,
    )
    if response.status_code != 200:
        return None
    results = response.json()
    if not results:
        return None
    result = results[0]
    postcode = (result.get("address") or {}).get("postcode")
    return float(result["lat"]), float(result["lon"]), postcode


def search_epcs(api_key: str, postcode: str) -> list[dict]:
    response = requests.get(
        EPC_SEARCH_URL,
        params={"postcode": postcode},
        headers={"Accept": "application/json", "Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    if response.status_code == 404:
        return []  # no EPCs found for this postcode - not an error
    response.raise_for_status()
    return response.json().get("data", [])


@dataclass
class BuildStatusResult:
    status: str
    epc_count: int
    checked_at: dt.datetime
    evidence: tuple[dict, ...] = ()
    evidence_note: str = "Postcode evidence is not matched to this scheme; completion is unverified."


def check_build_status(
    api_key: str | None, postcode: str | None,
    expected_units: int | None, decided_after: dt.date | None = None,
) -> BuildStatusResult:
    """Retain postcode certificates as leads, never as scheme completion proof.

    There is no accepted dwelling/phase identity contract at this boundary.
    Even post-grant certificates cannot establish this scheme's completion.
    Date-qualified distinct certificates are counted for investigation only.
    """
    now = dt.datetime.now(dt.timezone.utc)
    if not api_key or not postcode:
        return BuildStatusResult("unknown", 0, now)
    try:
        rows = search_epcs(api_key, postcode)
    except Exception:
        return BuildStatusResult("unknown", 0, now)
    if isinstance(decided_after, dt.datetime):
        decided_after = decided_after.date()
    evidence, seen, count = [], set(), 0
    for row in rows:
        if not isinstance(row, dict):
            evidence.append({"record": row, "reason": "invalid_record"})
            continue
        try:
            registered = dt.date.fromisoformat(row.get("registrationDate", ""))
        except (ValueError, TypeError):
            registered = None
        # Certificate identity where supplied; exact duplicate payload otherwise.
        import json
        identity = str(row.get("lmk-key") or row.get("lmkKey") or json.dumps(row, sort_keys=True))
        if identity in seen:
            reason = "duplicate_certificate"
        elif not isinstance(decided_after, dt.date) or registered is None:
            reason = "date_scope_unknown"
        elif registered < decided_after:
            reason = "pre_grant"
        else:
            reason = "post_grant_scheme_match_unverified"
            count += 1
        seen.add(identity)
        evidence.append({"record": row, "reason": reason})
    return BuildStatusResult("unknown", count, now, tuple(evidence))
