"""Deterministic validation for Local Plan SITE ALLOCATION facts (Gate 4A,
"Controlled Residential Allocation Intelligence Extraction") - the
allocation-level counterpart to app.policy.evidence_validation, inheriting
the same three trust principles the LPDI gates already established for
plan-level facts, applied to the different (array-of-sites) shape
app.extraction.local_plan.extract_local_plan_sites returns:

  Gate 3A (citation):      is this allocation's claimed evidence actually
                            on the claimed physical PDF page?
  Gate 3D (relationship):  does a claimed value (capacity, hectares)
                            actually belong to THIS site, not an adjacent
                            row/site sharing the same page?
  Gate 3K (numeric scope): a locally-correct, correctly-associated number
                            can still be the wrong SCOPE (a phase, a wider
                            masterplan total) rather than this site's own
                            plan-period capacity.

Deliberately a SIBLING module, not a shoehorned extension of validate_fact
- a single free-text/numeric FACT and an array of structured allocation
records are different enough shapes that reusing the same function would
make both harder to read, not smaller. Every technique below (substring
citation search, proximity-based association, qualifying-language
scope checks) is the SAME kind of plain, explainable, deterministic check
evidence_validation.py already uses - nothing here calls an LLM, and
nothing here reconstructs a table."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# --- Gate 3A inheritance: allocation citation verification -------------------


@dataclass(frozen=True)
class AllocationCitationVerification:
    # "not_checked" (no page-bounded text supplied) | "verified" (the
    # site's own identity is found on the claimed page) | "corrected" (not
    # on the claimed page, but uniquely findable on exactly one other page)
    # | "ambiguous" (findable on more than one page) | "unverified" (not
    # findable anywhere, or no identity strong enough to search for).
    status: str
    verified_page: int | None
    note: str | None


def _normalise_for_search(text: str) -> str:
    """Same conservative normalisation discipline as
    evidence_validation._normalise_for_citation - handles only the
    harmless PDF-extraction differences (dash variants, thousands-comma,
    whitespace/line-wrap) that would otherwise cause a false non-match,
    never touches word order or drops words."""
    text = unicodedata.normalize("NFKD", text)
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"[‐-―]", "-", text)
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.lower().strip()


def verify_allocation_citation(
    policy_reference: str | None, site_name: str, source_page: int | None, pages: list[tuple[int, str]] | None,
) -> AllocationCitationVerification:
    """A trusted allocation must have a physical source page that actually
    contains enough identifying evidence (its own policy_reference, or its
    own site_name) to establish this really is the claimed allocation's
    own page - not merely a page somewhere within the processed range.

    Prefers policy_reference (a short, largely unique code - "AN4") over
    site_name (which can coincidentally recur, e.g. a road name mentioned
    in a neighbouring site's own boundary description) when both are
    available; falls back to site_name only when no policy_reference was
    extracted at all."""
    if pages is None:
        return AllocationCitationVerification("not_checked", source_page, None)

    identity = policy_reference or site_name
    normalised_identity = _normalise_for_search(identity) if identity else ""
    # policy_reference is a formal code ("AN1", "AS4") - trustworthy as a
    # search term at any length, since it's structured, not arbitrary
    # prose (real Trafford codes are as short as 3 characters). Only a
    # site_name FALLBACK (free text, genuinely ambiguous when short - a
    # bare word or two could coincidentally match unrelated text) needs
    # evidence_validation's own excerpt-significance-style floor.
    min_length = 3 if policy_reference else 8
    if not normalised_identity or len(normalised_identity) < min_length:
        return AllocationCitationVerification(
            "unverified", None, f"no identity strong enough to verify a citation deterministically ({identity!r})",
        )

    page_lookup = {page_number: _normalise_for_search(text) for page_number, text in pages}

    if source_page in page_lookup and normalised_identity in page_lookup[source_page]:
        return AllocationCitationVerification("verified", source_page, None)

    matches = sorted(page_number for page_number, text in page_lookup.items() if normalised_identity in text)
    if len(matches) == 1:
        return AllocationCitationVerification(
            "corrected", matches[0], f"model cited page {source_page}, deterministically verified on page {matches[0]} instead",
        )
    if len(matches) > 1:
        return AllocationCitationVerification(
            "ambiguous", None, f"allocation identity {identity!r} is findable on more than one page {matches}",
        )
    return AllocationCitationVerification(
        "unverified", None, f"allocation identity {identity!r} could not be found on any processed page",
    )


# --- Gate 3D inheritance: field-to-allocation association safety -------------

_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def classify_field_association_risk(
    value_text: str, identity: str, page_text: str | None, other_identities_on_page: tuple[str, ...] = (),
) -> str:
    """"ASSOCIATED" (this value is genuinely closer to THIS site's own
    identity string than to any other site's identity on the same page)
    or "UNASSOCIATED" (no occurrence of the value exists near this
    identity at all, or another site's identity is actually the nearer
    one - the value likely belongs to that other row instead).

    Deliberately "nearest identity wins" rather than a fixed character
    window: a real per-site detail page (one identity, several hundred
    characters of prose before its own capacity figure) and a real dense
    multi-column summary table (several identities packed within a few
    hundred characters of each other) have genuinely different natural
    scales - proven directly against Trafford's own real text (this
    module's own Gate 4A ground-truth investigation): on AN1's own detail
    page, "AN1" sits ~300 characters from its own "8,400" capacity
    figure; on the summary table page, AN1's identity sits only ~280
    characters from AN3's OWN (different site's) hectares figure - a
    single fixed threshold cannot safely separate both shapes at once,
    but "which identity is nearest" does, without ever attempting to
    parse the table's actual row/column structure.

    other_identities_on_page is optional (defaults to none, e.g. when a
    caller only has one site's own extraction result in hand) - omitting
    it degrades safely to a generous single-identity proximity check,
    never the reverse (never MORE permissive with more information)."""
    if not page_text or not identity or not value_text:
        return "UNASSOCIATED"

    normalised_page = _normalise_for_search(page_text)
    normalised_identity = _normalise_for_search(identity)
    normalised_value = _normalise_for_search(value_text)

    identity_positions = [m.start() for m in re.finditer(re.escape(normalised_identity), normalised_page)]
    value_positions = [m.start() for m in re.finditer(re.escape(normalised_value), normalised_page)]
    if not identity_positions or not value_positions:
        return "UNASSOCIATED"

    other_positions = [
        m.start()
        for other in other_identities_on_page
        if other and _normalise_for_search(other) != normalised_identity
        for m in re.finditer(re.escape(_normalise_for_search(other)), normalised_page)
    ]

    for vpos in value_positions:
        own_distance = min(abs(vpos - ipos) for ipos in identity_positions)
        other_distance = min((abs(vpos - opos) for opos in other_positions), default=None)
        if other_distance is None or own_distance < other_distance:
            return "ASSOCIATED"
    return "UNASSOCIATED"


# --- Gate 3K inheritance: allocation capacity scope safety -------------------

# Real Trafford evidence (this gate's own ground-truth sample) - every site
# that states two dwelling figures qualifies the smaller one with this
# exact kind of phrase ("15,000 dwellings (8,400 in plan period)", "3,200
# dwellings with around 2,050 dwellings in plan period"). Mirrors
# evidence_validation._WHOLE_PLAN_SCOPE_PHRASES_RE's own "does the
# candidate's own evidence already qualify it" pattern, at allocation
# scale instead of plan scale.
_PLAN_PERIOD_QUALIFIER_RE = re.compile(r"in (the )?plan period", re.I)
_DWELLING_FIGURE_RE = re.compile(r"\d[\d,]*\s+dwellings", re.I)
_SCOPE_QUALIFIER_PROXIMITY_CHARS = 60


def classify_capacity_scope_risk(minimum_dwellings: int, source_excerpt: str | None) -> str:
    """"SINGLE_SCOPE" (safe to trust) or "MULTI_SCOPE" (the excerpt states
    more than one dwelling-shaped figure and the claimed minimum_dwellings
    value is not clearly anchored to a plan-period qualifier near it - the
    figure may actually be the wider comprehensive/masterplan total, or
    vice versa). A single dwelling figure in the excerpt is always
    SINGLE_SCOPE regardless of qualifying language - there is nothing else
    it could be confused with locally. Deliberately does not attempt to
    determine which of several figures is "correct" - only whether THIS
    one is safely distinguishable."""
    if not source_excerpt:
        return "SINGLE_SCOPE"

    figures = list(_DWELLING_FIGURE_RE.finditer(source_excerpt))
    if len(figures) < 2:
        return "SINGLE_SCOPE"

    target = re.sub(r"[,\s]", "", str(minimum_dwellings))
    for m in figures:
        figure_digits = re.sub(r"[,\s]", "", _NUMBER_RE.search(m.group(0)).group(0))
        if figure_digits != target:
            continue
        window = source_excerpt[max(0, m.start() - _SCOPE_QUALIFIER_PROXIMITY_CHARS):
                                 m.end() + _SCOPE_QUALIFIER_PROXIMITY_CHARS]
        if _PLAN_PERIOD_QUALIFIER_RE.search(window):
            return "SINGLE_SCOPE"
    return "MULTI_SCOPE"


# --- Green Belt classification (Gate 4A's own narrow, evidence-backed rule) --

# Deliberately three DISTINCT meanings, not a Boolean - real Trafford
# evidence (this gate's own ground-truth sample, AS4 Dairyhouse Lane:
# "is bounded by the Green Belt... to the west") demonstrates that
# "adjacent to" and "released from" the Green Belt are different claims a
# single true/false would silently conflate. Order matters below - release
# language is checked first since a sentence could in principle mention
# both a release and an adjacent remaining boundary.
_GREEN_BELT_RELEASE_RE = re.compile(r"releas\w* (from|of) the green belt|remov\w* from the green belt", re.I)
_GREEN_BELT_WITHIN_RE = re.compile(r"within the green belt|currently (in |within )?(the )?green belt", re.I)
_GREEN_BELT_ADJACENT_RE = re.compile(r"adjacent to the green belt|bound\w* by (the )?green belt|green belt boundary", re.I)


def classify_green_belt_status(green_belt_excerpt: str | None) -> str | None:
    """None (no Green Belt evidence at all - the ordinary case) or one of
    "green_belt_release" / "within_green_belt" / "adjacent_to_green_belt".
    An excerpt that mentions "Green Belt" without matching any of these
    three specific patterns returns None too - a genuine but unclear
    mention is exactly the "review/unknown" case Gate 4A's own task
    requires, not a guessed bucket."""
    if not green_belt_excerpt:
        return None
    if _GREEN_BELT_RELEASE_RE.search(green_belt_excerpt):
        return "green_belt_release"
    if _GREEN_BELT_WITHIN_RE.search(green_belt_excerpt):
        return "within_green_belt"
    if _GREEN_BELT_ADJACENT_RE.search(green_belt_excerpt):
        return "adjacent_to_green_belt"
    return None
