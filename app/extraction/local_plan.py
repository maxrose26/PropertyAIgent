"""Extraction of housing site allocations from a council's Local Plan
document - see app.db.models.LocalPlanSite for why this exists.

There's no portal equivalent for this (no Idox/Arcus, no consistent format
across councils), so unlike the rest of this project's scraping, ingestion
is necessarily semi-manual: someone finds the right document and page range
for a given council once, then this module does the actual extraction.
Grounded-numbers-then-narrate doesn't quite apply here since there's no
narration step - but the same discipline holds: the model only ever
structures what's literally printed in the source text, it never estimates
or invents a dwelling count.
"""
from __future__ import annotations

import json

import pdfplumber
from openai import OpenAI
from rapidfuzz import fuzz

from app.db.models import Site
from app.enrichment.epc_lookup import geocode_address
from app.pipeline.site_linking import normalise_address

MODEL = "gpt-4o-mini"

# Deliberately higher than site_linking's own FUZZY_SCORE_THRESHOLD (70) -
# a local plan site name is a short, terse label ("Sanderling Road") being
# matched against a full scraped address, which is inherently noisier than
# matching two addresses against each other, so a higher bar is needed to
# auto-link with any confidence. Anything below this is left unmatched
# (matched_site_id stays null) rather than guessed - a wrong auto-match here
# would misleadingly suggest an allocation already has an application when
# it doesn't, exactly the opposite of this feature's purpose.
MATCH_SCORE_THRESHOLD = 80.0

SCHEMA = {
    "name": "local_plan_site_allocations",
    "schema": {
        "type": "object",
        "properties": {
            "sites": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "policy_reference": {
                            "type": ["string", "null"],
                            # Nullable (Sprint 2, "Greater Manchester Policy
                            # Intelligence Framework" - onboarding Bury):
                            # confirmed a real fabrication case when this was
                            # a required string. Bury's own Local Plan
                            # narratively NAMES sites PfE allocates elsewhere
                            # ("PfE identifies several strategic housing
                            # allocations... at Seedfield, Walshaw...") with
                            # no policy code stated on that page at all - the
                            # model, previously forced to fill a required
                            # field, invented plausible-looking codes copying
                            # this very prompt's OWN example format ("HOM
                            # 2.30", Stockport's convention, not Bury's).
                            # Null is the honest, correct answer when a
                            # document genuinely doesn't print one.
                            "description": "The site's own policy code EXACTLY as printed against it, e.g. 'HOM 2.30' or 'JPA7' - "
                                           "not the parent policy code. Use null if no code is printed for this specific site anywhere "
                                           "in the source text - NEVER invent, infer, or reuse a code from this schema's own example.",
                        },
                        "site_name": {"type": "string"},
                        "minimum_dwellings": {
                            "type": ["integer", "null"],
                            "description": "The dwelling count printed against this specific site. Null if none is stated for it.",
                        },
                        "category": {
                            "type": "string",
                            "description": "The MOST SPECIFIC heading this site sits under, copied verbatim - if a list is split into lettered sub-groups (e.g. 'a. Previously developed land', 'b. Grey belt', 'c. Other') under a numbered list heading (e.g. 'List 2: sites outside the existing built-up area'), combine both as 'List 2: sites outside the existing built-up area - Grey belt', not just the outer list name alone. This distinction matters: grey belt/greenfield sites carry different planning risk to brownfield ones.",
                        },
                    },
                    "required": ["policy_reference", "site_name", "minimum_dwellings", "category"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["sites"],
        "additionalProperties": False,
    },
}


def extract_pdf_page_range(pdf_path: str, first_page: int, last_page: int) -> str:
    """1-indexed, inclusive - matches how a human would cite a page number
    when pointing this module at a new council's document."""
    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages[first_page - 1:last_page]
        return "\n\n".join(page.extract_text() or "" for page in pages)


def build_local_plan_prompt(source_text: str) -> str:
    return f"""
The text below is extracted from a UK council's Local Plan - specifically
the section listing individual sites allocated for housing development.
Extract every individual site listed, exactly as printed. Do not invent,
estimate, merge, or omit any site. Do not include list subtotals or the
overall total as sites. If a site's own dwelling count isn't stated, use
null rather than guessing one from context.

Only extract a site if THIS document is itself the one allocating/
designating it (it appears in a formal allocations list, schedule, or
table with its own entry). Do NOT extract a site that this text merely
NAMES or REFERENCES as being allocated by a DIFFERENT plan or authority
(e.g. "the Joint Plan identifies strategic sites at X, Y and Z" is a
cross-reference, not this document's own allocation - do not extract X, Y,
Z from a sentence like that).

Never invent a policy reference/code. If no code is printed for a specific
site anywhere in the source text, use null for policy_reference rather
than guessing, reusing an example format, or inferring one from a nearby
site's code.

SOURCE TEXT:
{source_text}
"""


def extract_local_plan_sites(client: OpenAI, source_text: str) -> list[dict]:
    prompt = build_local_plan_prompt(source_text)
    response = client.responses.create(
        model=MODEL, input=prompt,
        text={"format": {"type": "json_schema", "name": SCHEMA["name"], "schema": SCHEMA["schema"], "strict": True}},
    )
    return json.loads(response.output_text)["sites"]


_DIRECTIONS = {"north", "south", "east", "west"}


def _contradicting_direction(a: str, b: str) -> bool:
    """True if both names mention a compass direction in their OWN core
    name and they disagree - confirmed a real false-positive match: "HOM
    2.33 Heald Green West" (750 dwellings) scored 100/100 against an
    existing application literally named "Heald Green EAST" (675
    dwellings, a real but DIFFERENT site) - token_set_ratio is set-based,
    so it doesn't penalise one mismatched direction word when everything
    else overlaps this strongly.

    Only checks each string's first 5 tokens, not the whole thing - a
    scraped address routinely restates directions later as boundary
    description ("...Land North Of Stanley Road AND WEST OF THE A34..."),
    which isn't the site's own identity and would otherwise cause a false
    contradiction against a genuinely correct match. Confirmed real case:
    that exact address's full token set contains BOTH "east" (site 104's
    own name, "Heald Green East") and "west" (an unrelated boundary
    clause), so a whole-string check finds no disagreement at all and
    misses the false positive entirely.

    A wrong auto-match here is worse than no match at all (see
    match_to_existing_site's docstring), so this is checked as a hard
    veto, not folded into the score."""
    dirs_a = _DIRECTIONS & set(a.split()[:5])
    dirs_b = _DIRECTIONS & set(b.split()[:5])
    return bool(dirs_a) and bool(dirs_b) and dirs_a.isdisjoint(dirs_b)


def match_to_existing_site(site_name: str, candidates: list[Site]) -> tuple[Site | None, float]:
    """Best-scoring already-scraped Site whose address plausibly IS this
    allocation, restricted to candidates from the same council by the
    caller. No match (None, 0.0) is the expected, common, and USEFUL result -
    it means nobody has submitted a planning application for this allocation
    yet, which is exactly the pre-application opportunity this feature
    exists to surface. A match that turns out wrong is actively worse than
    no match: it would claim an allocation already has an application when
    it's really a different, adjacent site - so ties are broken toward NOT
    matching (_contradicting_direction), not toward the higher score."""
    if not candidates:
        return None, 0.0
    normalised_name = normalise_address(site_name)
    best_site, best_score = None, 0.0
    for site in candidates:
        if _contradicting_direction(normalised_name, site.canonical_address):
            continue
        score = fuzz.token_set_ratio(normalised_name, site.canonical_address)
        if score > best_score:
            best_site, best_score = site, score
    if best_score >= MATCH_SCORE_THRESHOLD:
        return best_site, best_score
    return None, 0.0


_COUNCIL_NAME_SUFFIXES = [
    " metropolitan borough council", " city council", " borough council", " council",
]


def _short_place_name(council_name: str) -> str:
    """Nominatim's free-text search matches a real place name ("Stockport")
    much more reliably than an administrative body's full formal name
    ("Stockport Metropolitan Borough Council") - confirmed real case:
    "Sanderling Road, Stockport Metropolitan Borough Council" returned no
    match at all, "Sanderling Road, Stockport" geocoded correctly first
    try."""
    lowered = council_name.lower()
    for suffix in _COUNCIL_NAME_SUFFIXES:
        if lowered.endswith(suffix):
            return council_name[: -len(suffix)]
    return council_name


def geocode_local_plan_site(site_name: str, council_name: str, matched_site: Site | None) -> tuple[float, float] | None:
    """A matched site already has coordinates from the normal scrape/geocode
    pipeline where available - reuse them rather than re-geocoding. But a
    matched site can itself still lack coordinates (confirmed real case:
    several already-scraped Stockport sites never got a postcode captured,
    so stage_geocode_sites had nothing to look up for them either) - in
    that case fall through to the same free-text fallback used for
    unmatched allocations, using the matched site's own full address
    (more specific than the allocation's bare site name, so tried first).
    An unmatched allocation has no scraped application to inherit from at
    all, and its own name alone ("Sanderling Road") has no postcode to
    look up - free-text geocoding via Nominatim (geocode_address) is the
    only option there, matched against the council's place name to
    disambiguate same-named streets elsewhere in the country."""
    if matched_site and matched_site.latitude and matched_site.longitude:
        return matched_site.latitude, matched_site.longitude

    if matched_site and matched_site.display_address:
        result = geocode_address(matched_site.display_address)
        if result:
            return result[0], result[1]

    result = geocode_address(f"{site_name}, {_short_place_name(council_name)}")
    return (result[0], result[1]) if result else None


def assess_delivery_scope(minimum_dwellings: int | None, matched_units: int | None) -> dict:
    """Compares an allocation's own stated dwelling count against the
    matched application's total, to answer the genuinely useful acquisition
    question: has this allocation been taken up in full, or does the live
    application only cover part of it (a phase, or a scaled-down scheme),
    leaving capacity not currently accounted for by identified planning
    activity? Confirmed real case: Land At Chester Road, Hazel Grove -
    allocated 300 dwellings (HOM 2.37), but its only application is for
    134 - a live example of a partial delivery worth knowing about, not
    obvious from either figure shown alone. Never asserts the unaccounted
    capacity is "available" - absence of identified planning activity is
    not evidence the land is available (Product Owner rule)."""
    if not minimum_dwellings or not matched_units:
        return {"status": "unknown", "note": "Can't compare - one or both unit counts aren't known."}

    ratio = matched_units / minimum_dwellings
    if ratio >= 0.9:
        return {
            "status": "full_site",
            "note": f"Application ({matched_units} units) covers essentially the whole allocation ({minimum_dwellings} units).",
        }
    if ratio <= 0.7:
        return {
            "status": "partial",
            "note": f"Application ({matched_units} units) covers only {ratio:.0%} of the {minimum_dwellings}-unit "
                    f"allocation - likely a phase or a scaled-down scheme. Approximately "
                    f"{minimum_dwellings - matched_units} units of allocation capacity are not currently "
                    f"accounted for by identified planning activity.",
        }
    return {
        "status": "roughly_matches",
        "note": f"Application ({matched_units} units) is close to the {minimum_dwellings}-unit allocation "
                f"({ratio:.0%}) - probably the full site, with a modest design change.",
    }
