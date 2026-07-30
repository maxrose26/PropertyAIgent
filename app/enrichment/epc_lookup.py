"""Build-status detection + postcode geocoding.

Neither of these needed a scraper rewrite - both are free/cheap UK open-data
lookups keyed off the site's postcode:

- EPC Open Data register: new dwellings get an Energy Performance
  Certificate registered around practical completion, so counting EPCs
  registered at a site's postcode after its decision date is a reasonable
  proxy for "how much of this has actually been built" - register for a
  free API key at https://get-energy-performance-data.communities.gov.uk
  and add EPC_API_KEY to .env (a bearer token - the service migrated off
  the old epc.opendatacommunities.org domain and its email+key Basic Auth;
  confirmed the old domain now just redirects to this new one's HTML
  frontend rather than erroring, so a stale old-style key silently returns
  a webpage instead of JSON rather than failing loudly).
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

COMPLETION_TOLERANCE = 0.9  # count as "complete" once EPCs found >= 90% of expected units

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
    status: str  # no_completions_yet | partially_complete | complete | unknown
    epc_count: int
    checked_at: dt.datetime


def check_build_status(
    api_key: str | None, postcode: str | None,
    expected_units: int | None, decided_after: dt.date | None = None,
) -> BuildStatusResult:
    now = dt.datetime.now(dt.timezone.utc)

    if not api_key or not postcode:
        return BuildStatusResult(status="unknown", epc_count=0, checked_at=now)

    try:
        rows = search_epcs(api_key, postcode)
    except Exception:
        return BuildStatusResult(status="unknown", epc_count=0, checked_at=now)

    if decided_after:
        filtered = []
        for row in rows:
            registered = row.get("registrationDate")
            try:
                if registered and dt.date.fromisoformat(registered) >= decided_after:
                    filtered.append(row)
            except ValueError:
                continue
        rows = filtered or rows  # if date filtering wipes everything out, fall back to unfiltered count

    epc_count = len(rows)

    if epc_count == 0:
        # NOT "not_started" - an EPC is only lodged near practical
        # completion (when a unit is ready to occupy/sell), so it lags the
        # actual start of construction by potentially a year or more. Zero
        # EPCs only proves "nothing has finished yet" - a site that broke
        # ground 18 months ago and is mid-build looks identical here to one
        # that's genuinely untouched. classify_build_status's portal-filing
        # check is the signal that can positively confirm "underway"; this
        # value means neither signal fired, not that we've confirmed
        # nothing has happened.
        status = "no_completions_yet"
    elif expected_units and epc_count >= expected_units * COMPLETION_TOLERANCE:
        status = "complete"
    else:
        status = "partially_complete"

    return BuildStatusResult(status=status, epc_count=epc_count, checked_at=now)
