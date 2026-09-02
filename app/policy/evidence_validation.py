"""Deterministic validation for plan-level evidence facts (Sprint 3B, "AI
Local Plan Evidence Extraction", Part 6) - runs BEFORE any extracted fact
is allowed to become a PolicyChangeEvent proposal. Nothing here calls an
LLM; every check is a plain, explainable rule, so a rejection can always be
explained in one sentence.

"Housing need and requirement must remain separately labelled" (Part 6) is
enforced by design, not by a check in this module - app.extraction.
plan_evidence keeps them as distinct field names end-to-end, and nothing
in this pipeline ever merges one into the other.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass

from app.policy.status import normalise_plan_status

# Fields expected to be non-negative whole numbers of dwellings/years.
_NON_NEGATIVE_INT_FIELDS = frozenset({
    "annual_housing_requirement", "total_plan_housing_requirement",
    "housing_need_annual", "housing_need_total", "unmet_need",
    "homes_delivered_latest_period", "cumulative_homes_delivered",
    "delivery_requirement_for_period", "trajectory_remaining_requirement",
    "deliverable_supply_dwellings", "five_year_requirement_dwellings",
})
# Allowed to be negative (a shortfall is a real, meaningful negative number).
_SIGNED_INT_FIELDS = frozenset({"delivery_surplus_or_shortfall", "five_year_shortfall_or_surplus_dwellings"})
_YEAR_FIELDS = frozenset({"plan_period_start", "plan_period_end"})
_SUPPLY_YEARS_FIELDS = frozenset({"five_year_supply_years"})
_PERCENTAGE_FIELDS = frozenset({"buffer_percentage"})
_DATE_FIELDS = frozenset({
    "publication_date", "submission_date", "inspector_report_date", "adoption_date",
    "expected_adoption_date", "next_milestone_date", "five_year_supply_base_date",
    "five_year_supply_publication_date",
})
_NUMERIC_FIELDS = _NON_NEGATIVE_INT_FIELDS | _SIGNED_INT_FIELDS | _YEAR_FIELDS | _SUPPLY_YEARS_FIELDS | _PERCENTAGE_FIELDS

# Fields that state a PER-YEAR figure for one authority - genuinely
# implausible above a few thousand for any single English/Welsh council
# (the whole of London's combined annual target is in the tens of
# thousands, split across 33 boroughs). Kept separate from the TOTAL
# plan-period fields (total_housing_requirement, housing_need_total,
# unmet_need, cumulative_homes_delivered), which are legitimately allowed
# to run into the tens of thousands.
_ANNUAL_FIGURE_FIELDS = frozenset({
    "annual_housing_requirement", "housing_need_annual",
    "homes_delivered_latest_period", "delivery_requirement_for_period",
})
_MAX_PLAUSIBLE_ANNUAL_FIGURE = 10_000

_MIN_PLAUSIBLE_YEAR = 1990
_MAX_PLAUSIBLE_YEAR = 2100
_MAX_PLAUSIBLE_SUPPLY_YEARS = 20.0


def _strip_thousands_separators(value: str) -> str:
    return value.replace(",", "").strip()


def _parse_int(value: str) -> int | None:
    try:
        return int(_strip_thousands_separators(value))
    except ValueError:
        return None


def _parse_float(value: str) -> float | None:
    try:
        return float(_strip_thousands_separators(value))
    except ValueError:
        return None


def _excerpt_supports_number(excerpt: str, number: int | float) -> bool:
    """A real pilot run against the actual Stockport Local Plan surfaced a
    genuine hallucination this validator's earlier "excerpt has SOME
    digit" check missed entirely: housing_need_annual=1035 was proposed
    with the excerpt "...ratio of median house prices to median incomes
    is 8.6691..." - a real number, just not THIS number, about something
    else entirely. Requiring the excerpt to actually contain the claimed
    value (comma/whitespace-normalised) is a much stronger, still cheap,
    anti-hallucination check."""
    normalised_excerpt = re.sub(r"[,\s]", "", excerpt)
    if isinstance(number, float) and number == int(number):
        candidates = {str(int(number)), f"{number:g}"}
    else:
        candidates = {str(number)}
    return any(candidate in normalised_excerpt for candidate in candidates)


def _looks_like_a_plausible_date(value: str) -> bool:
    """Every date field in this platform is stored as free text, not a
    real Date column - councils state dates in genuinely inconsistent
    formats/precision ("2027", "Q1 2027", "Spring 2027", "14 March 2027"),
    and forcing strict parsing would reject a lot of real, useful evidence.
    The bar here is deliberately low: does this contain a 4-digit year that
    isn't obviously nonsense - not "is this a fully-formed calendar date"."""
    match = re.search(r"(19|20)\d{2}", value)
    if not match:
        return False
    year = int(match.group(0))
    return _MIN_PLAUSIBLE_YEAR <= year <= _MAX_PLAUSIBLE_YEAR


def _sentence_span_containing(text: str, needle: str) -> str | None:
    """The single sentence within text that contains needle (case-
    insensitive substring search), bounded by the nearest '.', '!', or '?'
    on either side (or the start/end of text) - deliberately simple,
    single-sentence-only string bounding, never full NLP sentence
    splitting and never a fuzzy/semantic match. Returns None if needle
    isn't found in text at all (e.g. the model paraphrased its own
    excerpt rather than quoting verbatim - a known, real, separately
    documented limitation, not something this function can recover)."""
    if not text or not needle:
        return None
    lowered = text.lower()
    idx = lowered.find(needle.lower())
    if idx == -1:
        return None
    start = 0
    for m in re.finditer(r"[.!?]\s+", text[:idx]):
        start = m.end()
    end_match = re.search(r"[.!?](\s+|$)", text[idx:])
    end = idx + end_match.end() if end_match else len(text)
    return text[start:end]


def detect_sibling_plan_reference(
    excerpt: str | None, sibling_groups: list[list[str]], source_text: str | None = None,
) -> str | None:
    """LPDI V1 Gate 2A ("Multi-Plan Attribution & Same-Plan Evidence
    Validation Hardening") - generic, config-driven check: does the fact's
    supporting context explicitly name a different, sibling plan identity?
    Returns a human-readable rejection reason when it does, else None.

    Checks the excerpt itself PLUS - when source_text is given (the full
    text of the pages this extraction pass actually read) - the single
    SENTENCE within source_text containing that excerpt. This second check
    exists because a real, live controlled extraction run (specifications/
    018's Gate 2A section) demonstrated the model's own returned excerpt
    can be trimmed to just the value-supporting fragment ("adopted on 18
    January 2023"), silently dropping the surrounding clause that actually
    names the sibling plan ("...the Salford Local Plan: Development
    Management Policies and Designations (SLP:DMP), which was adopted on
    18 January 2023.") - even though both clauses are literally one
    sentence in the source. Bounded to the SAME SENTENCE only, deliberately
    not a wider paragraph/page/document window - a second real, live run
    (the same finding's Bury Local Plan regression case) demonstrated a
    document can legitimately mention a sibling plan (Places for Everyone)
    in a NEARBY but different sentence while still correctly stating ITS
    OWN plan's genuine figure (Bury's own housing requirement, sourced from
    but not mis-attributed to PfE) - a page/paragraph-wide check would have
    wrongly blocked that genuine evidence, which the sentence boundary
    avoids.

    Deliberately asymmetric (Gate 2A's own Section 12): the ABSENCE of the
    target plan's own name near a fact does NOT itself indicate a problem -
    only an EXPLICIT reference to a different, KNOWN sibling plan's own
    name/alias does. sibling_groups (see
    app.policy.plan_identity.sibling_alias_groups) already excludes the
    target plan's own aliases, so this function never needs to know what
    the target plan itself is called - only what its known siblings are
    called. Text that happens to ALSO mention the target plan's own name
    alongside a sibling's is still blocked, not treated as resolved in the
    target's favour - genuinely ambiguous context is not silently guessed
    either way."""
    if not sibling_groups:
        return None

    texts_to_check = []
    if excerpt:
        texts_to_check.append(excerpt)
    if source_text and excerpt:
        sentence = _sentence_span_containing(source_text, excerpt)
        if sentence:
            texts_to_check.append(sentence)

    for text in texts_to_check:
        lowered = text.lower()
        for group in sibling_groups:
            for alias in group:
                if alias and alias.lower() in lowered:
                    return f"supporting evidence explicitly references a different Local Plan ({alias!r})"
    return None


# --- LPDI V1 Gate 3A ("Deterministic Evidence Citation Verification") ----------
#
# Gate 2B's own real, controlled-validation finding: source_page is model-
# generated text, supplied with correct [PAGE N] markers but never checked
# against the actual page-bounded document text - and the UI turns
# source_page straight into a clickable PDF deep-link (#page=N). 3 of 43
# sampled auto-applied facts (~7%) carried a demonstrably wrong page
# citation, though every sampled VALUE was itself correct - a genuine,
# user-facing provenance defect distinct from a value-correctness one.
#
# The trust chain this closes: model-extracted fact + excerpt -> DETERMINISTIC
# citation verification (this section, no LLM involved) -> existing
# validation/review pathway. The LLM identifies evidence; the application
# verifies where it came from.

# A short/generic excerpt for a FREE-TEXT field ("new", a bare word or two)
# proved capable of trivially "matching" hundreds of pages in Gate 2B's real
# sample (running headers/footers, boilerplate legal text) - not real
# evidence of anything. NUMERIC/DATE fields are exempt from this floor: they
# already carry an independent, existing value-presence guarantee
# (_excerpt_supports_number / _looks_like_a_plausible_date, enforced in
# _validate_fact_fields before citation verification ever runs) that a
# short free-text excerpt has no equivalent of - "Total 3,847" is short but
# is genuinely anchored to a specific real number, not boilerplate.
_MIN_SIGNIFICANT_EXCERPT_WORDS = 4
_MIN_SIGNIFICANT_EXCERPT_CHARS = 15


def _normalise_for_citation(text: str) -> str:
    """Conservative normalisation for CITATION matching only - deliberately
    much less aggressive than could be imagined, so genuinely different
    text never becomes a false match. Handles only the specific harmless
    extraction/quoting differences Gate 2B directly demonstrated in real
    documents: typographic vs straight quotes, dash variants, thousands-
    separator commas, surrounding parentheses, and line-wrap/whitespace
    differences. Does NOT strip general punctuation, does NOT touch word
    order, does NOT drop words - this is a substring-match normaliser, not
    a bag-of-words/fuzzy scorer."""
    text = unicodedata.normalize("NFKD", text)
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    # Dash variants (hyphen, non-breaking hyphen, figure/en/em/horizontal-
    # bar dashes, U+2010-U+2015) -> plain ASCII hyphen.
    text = re.sub(r"[‐-―]", "-", text)
    # Thousands separators: a comma directly between two digits is a
    # formatting artefact, not meaningful punctuation - stripped only
    # there, never elsewhere, so a genuine clause-separating comma
    # anywhere else still distinguishes different text.
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    # "(November 2027)" vs "November 2027" is the same evidence with
    # different bracketing, not different evidence - parentheses are
    # dropped as bare punctuation; their CONTENTS are always kept.
    text = text.replace("(", "").replace(")", "")
    # Line-wrapping / general whitespace: pdfplumber inserts a newline at
    # every wrapped line break - collapse any run of whitespace to one
    # space so a wrapped quote still matches its unwrapped source.
    text = re.sub(r"\s+", " ", text)
    return text.lower().strip()


def _strip_trailing_sentence_punctuation(text: str) -> str:
    """A real, live controlled extraction (specifications/018's Gate 2A
    section) showed the model's own "verbatim" excerpt ending with a
    period the source text does not actually have at that exact position
    (closing its own quotation like a sentence, mid-clause in the real
    text). Stripped ONLY from the excerpt's own trailing edge, never
    mid-string and never from the page text being searched - this can
    only ever make a match MORE permissive at the boundary, never
    anywhere else in the comparison."""
    return text.rstrip(".,;:")


def _is_significant_excerpt(field: str, normalised_excerpt: str) -> bool:
    if field in _NUMERIC_FIELDS or field in _DATE_FIELDS:
        return True
    words = normalised_excerpt.split()
    return len(words) >= _MIN_SIGNIFICANT_EXCERPT_WORDS and len(normalised_excerpt) >= _MIN_SIGNIFICANT_EXCERPT_CHARS


@dataclass(frozen=True)
class CitationVerification:
    # "not_checked" (no page-bounded text supplied - every existing caller
    # before Gate 3A) | "verified" (excerpt confirmed on the cited page) |
    # "corrected" (not on the cited page, but uniquely findable elsewhere -
    # source_page deterministically corrected) | "ambiguous" (credibly
    # findable on more than one page - never guessed) | "unverified" (not
    # found anywhere, or the excerpt was too short/generic to trust either
    # way).
    status: str
    verified_page: int | None
    note: str | None


def verify_citation(
    field: str, source_page: int | None, source_excerpt: str | None, pages: list[tuple[int, str]] | None,
) -> CitationVerification:
    """Deterministically verifies - or corrects, or flags as unresolved - a
    fact's page citation against the ACTUAL page-bounded text the model was
    given (pages: [(page_number, text), ...], the same structure
    app.extraction.plan_evidence.extract_pdf_pages already returns - see
    app.policy.extract_plan_evidence.run_extraction for where it's threaded
    through). Never calls an LLM; every outcome is a plain substring search
    over conservatively normalised text - like every other check in this
    module, explainable in one sentence.

    page_number throughout is the PHYSICAL PDF page index (1-indexed from
    the start of the file) - the same numbering extract_pdf_pages already
    uses and the UI's own "#page=N" PDF deep-link requires. This function
    never attempts to interpret or convert a document's own printed/footer
    page number (Gate 2B found these can differ from the PDF's physical
    index by a constant offset) - only the physical index is ever compared
    or returned.

    pages=None (every caller before Gate 3A) means "no page-bounded text
    available to verify against" - status "not_checked", source_page
    returned unchanged, fully backward compatible."""
    if pages is None or not source_excerpt:
        return CitationVerification("not_checked", source_page, None)

    normalised_excerpt = _strip_trailing_sentence_punctuation(_normalise_for_citation(source_excerpt))
    if not _is_significant_excerpt(field, normalised_excerpt):
        return CitationVerification(
            "unverified", None,
            f"supporting evidence excerpt is too short/generic to verify a citation deterministically ({source_excerpt!r})",
        )

    page_lookup = {page_number: _normalise_for_citation(text) for page_number, text in pages}

    if source_page in page_lookup and normalised_excerpt in page_lookup[source_page]:
        return CitationVerification("verified", source_page, None)

    matches = sorted(page_number for page_number, text in page_lookup.items() if normalised_excerpt in text)

    if len(matches) == 1:
        return CitationVerification(
            "corrected", matches[0],
            f"model cited page {source_page}, deterministically verified on page {matches[0]} instead",
        )
    if len(matches) > 1:
        return CitationVerification(
            "ambiguous", None,
            f"supporting evidence citation is ambiguous across multiple pages {matches}",
        )
    return CitationVerification(
        "unverified", None,
        "supporting evidence citation could not be verified against the source document",
    )


# --- LPDI V1 Gate 3D ("Structured Evidence Semantic Safety") -------------------
#
# Gate 3C's own real, controlled production finding: a free-text fact
# (requirement_notes) whose excerpt was genuinely on the correct, Gate-3A-
# citation-verified page, and whose individual numbers were genuinely
# present in the source, still encoded a WRONG relationship between table
# periods and values - a column-shift misattribution, independently
# re-confirmed via pdfplumber's own word-level bounding-box coordinates
# (specifications/018's Gate 3C section). Nothing in the validation
# architecture above catches this: the free-text passthrough branch of
# _validate_fact_fields only confirms PRESENCE (value/excerpt non-empty),
# never that a period/label is correctly paired with its value (SEMANTIC
# RELATIONSHIP) - a materially different, harder question this module has
# never attempted, and still does not attempt to SOLVE here. The
# objective is safe abstention, not table understanding: a free-text
# "notes" field that states MULTIPLE period/label -> value relationships
# is routed to needs_review instead of trusted, because the application
# has no way to verify those specific pairings from linearised page text
# alone. Deliberately NOT a hard rejection (the proposal, excerpt and
# citation are all preserved) - a semantic-structure problem is not
# necessarily a value problem, the same principle Gate 3A already
# established for citation verification.

# The real risk surface, not "every free-text field": these four fields
# share an identical extraction-schema description across all four
# categories - "Any other short, materially useful nuance...that the
# fields above can't capture" (app.extraction.plan_evidence) - an
# explicit catch-all for content that doesn't fit a single-purpose field,
# exactly where an unrelated multi-value table fragment would land. A
# narrow, single-purpose label field (plan_name, requirement_basis,
# calculation_method, next_milestone...) is not in this set - even given
# a risky-looking value, it is never held up by this check.
_STRUCTURED_TEXT_RISK_FIELDS = frozenset({
    "status_notes", "requirement_notes", "delivery_notes", "supply_position_notes",
})

_NUMBER_RE = re.compile(r"\d[\d,]*")
# A year-range: two 4-digit years joined by a dash variant - the exact
# shape the real Gate 3C finding's own table used ("2022-2025",
# "2025–2030"...).
_YEAR_RANGE_RE = re.compile(r"(?:19|20)\d{2}\s*[-‐‑‒–—―]\s*(?:19|20)\d{2}")
# An enumerated "label: number" pair - a colon directly followed by a
# number, the generic shape of a label -> value list (e.g. "Core Growth
# Area: 1,500, Inner Area: 900").
_LABEL_VALUE_RE = re.compile(r"[A-Za-z][\w /]{1,40}:\s*\d[\d,]*")
_STRUCTURED_TEXT_PROXIMITY_CHARS = 25


def _has_number_nearby(text: str, span: tuple[int, int], window: int = _STRUCTURED_TEXT_PROXIMITY_CHARS) -> bool:
    """Is there a number within `window` characters immediately before or
    after the given span (a year-range match's own position)? A bare date
    mention with no number anywhere near it isn't a period->value claim
    at all - the ABSENCE of a nearby number must never itself be treated
    as risky (mirrors detect_sibling_plan_reference's own asymmetric
    principle: absence is not evidence of a problem, only an explicit
    positive signal is)."""
    start, end = span
    return bool(_NUMBER_RE.search(text[max(0, start - window):start]) or _NUMBER_RE.search(text[end:end + window]))


def classify_structured_text_risk(field: str, value: str) -> str:
    """Conservative, deterministic classification of a free-text VALUE's
    own internal structure: "SIMPLE_TEXT" (safe to trust on the same
    terms as any other free-text field) or "STRUCTURED_TEXT" (states 2+
    period/label -> value relationships that cannot be verified from
    linearised source text alone).

    Only ever returns "STRUCTURED_TEXT" for the narrow, evidenced risk
    surface (_STRUCTURED_TEXT_RISK_FIELDS) - the same value for any other
    field is always "SIMPLE_TEXT", since a genuinely single-purpose field
    has nowhere for an unrelated multi-value table fragment to land.

    Deliberately targets STRUCTURE, not raw number count: a sentence with
    two or more genuinely UNRELATED numbers, or exactly one period/value
    pair (no ambiguity about which number belongs to it), is still
    SIMPLE_TEXT - only multiple DISTINCT period-or-label markers each
    with a number nearby trips this."""
    if field not in _STRUCTURED_TEXT_RISK_FIELDS or not value:
        return "SIMPLE_TEXT"

    year_range_pairs = sum(1 for m in _YEAR_RANGE_RE.finditer(value) if _has_number_nearby(value, m.span()))
    label_value_pairs = len(_LABEL_VALUE_RE.findall(value))

    if year_range_pairs >= 2 or label_value_pairs >= 2:
        return "STRUCTURED_TEXT"
    return "SIMPLE_TEXT"


def _structured_text_review_reason(field: str) -> str:
    return (
        f"structured multi-value evidence in {field!r} cannot be safely verified from linearised source text - "
        f"the relationship between individual periods/labels and their values cannot be deterministically "
        f"established, so this proposal requires human review rather than being trusted automatically"
    )


# --- LPDI V1 Gate 3K ("Numeric Scope & Multi-Section Evidence Safety") --------
#
# Gate 3J's own real, controlled production finding: Oldham's
# total_plan_housing_requirement was proposed as 1,310 with excerpt
# "TOTAL 1310" - the number IS genuinely on the cited page (Gate 3A's
# citation check passes; there is nothing to correct or flag), and the
# excerpt genuinely contains the claimed digits (the ordinary numeric-
# presence check above passes too). But the document's own page 14 is a
# "Housing Land Release - Phase 1" schedule (policy H1.1), and its page 17
# - within the SAME processed page range - is a SEPARATE "Housing Land
# Release - Phase 2" schedule (policy H1.2) with its own "TOTAL 451". The
# stored value silently presented a Phase 1 SUBTOTAL as the definitive
# whole-plan total, omitting Phase 2's additional 451 dwellings entirely.
# Neither citation verification (the page is correct) nor the numeric-
# presence check (the excerpt states 1,310) nor Gate 3D's structured-text
# classifier (this is a single plain integer field, not one of the four
# free-text notes fields Gate 3D targets) can catch this - it is a
# genuinely different failure shape: not a WRONG number, not a
# MISATTRIBUTED period/value pairing, but an INCOMPLETE claim of scope -
# the number is real, but nothing establishes it covers the whole plan
# rather than one of several separately-totalled sections.
#
# Per Gate 3K's own explicit product decision: the system must NOT attempt
# to reconstruct or sum the true total (1,310 + 451 = 1,761 is never
# computed or asserted anywhere below) - only to recognise, deterministically
# and narrowly, when a candidate whole-plan total's own evidence gives no
# reason to trust it covers the whole plan AND the surrounding processed
# text shows a genuine multi-section/multi-phase structure for the same
# concept. The safe outcome is abstention (needs_review), exactly the same
# non-rejecting "force existing review pathway" pattern Gate 3A/3D already
# established - the proposal, its citation and its excerpt are all still
# preserved untouched.

# The real risk surface, evidenced by exactly one production finding so
# far: total_plan_housing_requirement (app.extraction.plan_evidence's own
# field name for LocalPlan.total_housing_requirement - see
# app.policy.extract_plan_evidence.EXTRACTION_FIELD_TO_MODEL_FIELD).
# Deliberately NOT annual_housing_requirement - Oldham's own real evidence
# proves an annual "required building rate" figure can remain genuinely
# singular and correct even when the same document's allocation schedule
# is phased (270 dwellings/year was the one, unambiguous, correct annual
# figure governing BOTH phases) - broadening this set without a second
# real, evidenced failure would be exactly the "manufacture further gates
# from theoretical risks" this gate's own task explicitly warns against.
_NUMERIC_SCOPE_RISK_FIELDS = frozenset({"total_plan_housing_requirement"})

# Whole-plan SCOPE-QUALIFYING language - if a candidate's own excerpt
# already ties the number to the whole plan (a plan-period year range, or
# an explicit "housing requirement"/"total need"/"net additional dwellings
# ... delivered" phrase), that is real, positive evidence of whole-plan
# scope and the candidate is trusted on that basis alone, regardless of
# what else the wider document contains - real evidence from every
# authority processed so far (Bury "total housing requirement of 9,486
# ... from 2022 - 2043", Stockport "total need of 31,790" "for the plan
# period 2025-2042", Trafford "minimum of 19,077 ... in the plan period
# (April 2022 - March 2039)", Bolton "10,738 for the period 2012-2026")
# confirms every genuinely correct, already-trusted total in this
# codebase carries this kind of qualifying language, while Oldham's bare
# "TOTAL 1310" carries none of it. Reuses _YEAR_RANGE_RE (already defined
# above for Gate 3D) rather than a second near-duplicate pattern.
_WHOLE_PLAN_SCOPE_PHRASES_RE = re.compile(
    r"housing requirement|total need|net additional dwellings|plan period", re.I,
)

# An explicit, repeated phase label - Oldham's own real evidence ("Housing
# Land Release - Phase 1" / "... Phase 2"). Requires TWO OR MORE distinct
# phase labels to count as a genuine multi-section signal (a document that
# merely mentions "Phase 1" once, with no "Phase 2" anywhere, is not
# evidence of a competing untotalled section - the same "only a positive,
# multi-occurrence signal counts" discipline Gate 3D's own
# _has_number_nearby already established for year-range/label-value pairs).
_PHASE_RE = re.compile(r"\bPhase\s+(?:One|Two|Three|Four|1|2|3|4)\b", re.I)

# A bare "TOTAL <number>" table-style label, deliberately distinct from the
# rich, qualified language above - exactly Oldham's own "TOTAL 1310"/
# "TOTAL 451" shape. Reused both to classify the candidate's OWN excerpt
# (unqualified -> proceed to the phase/competing-total check below) and to
# search the wider processed text for a DIFFERING total near a phase label.
_BARE_TOTAL_RE = re.compile(r"\bTOTAL\b[:\s]*([\d,]+)", re.I)

# How close a "TOTAL <number>" must appear to a "Phase N" mention on the
# SAME page to count as that phase's own total, rather than an unrelated
# figure elsewhere on a page that also happens to mention a phase in
# passing - Oldham's real pages have the phase heading immediately above
# its own schedule's total (a few hundred characters at most).
_PHASE_TOTAL_PROXIMITY_CHARS = 800


def classify_numeric_scope_risk(
    field: str, value: int | float, source_page: int | None, source_excerpt: str | None,
    pages: list[tuple[int, str]] | None,
) -> str:
    """"SINGLE_SCOPE" (safe to trust on the same terms as any other numeric
    fact) or "MULTI_SCOPE" (the candidate's own evidence gives no reason to
    believe it covers the whole plan, and the processed document shows a
    genuine repeated-phase/multi-section structure for the same concept -
    see this section's own module comment for the real Oldham finding this
    exists for).

    Only ever returns "MULTI_SCOPE" for the narrow, evidenced risk surface
    (_NUMERIC_SCOPE_RISK_FIELDS) with pages actually supplied - with no
    page-bounded text to inspect (every caller before Gate 3K, or a
    citation that never resolved to a real page), there is nothing to
    safely check against, so the field is left exactly as every other
    check already leaves it: not this classifier's business to guess.

    Deliberately does NOT attempt to determine, compute, or suggest the
    correct total - it only ever answers "is there a reason to distrust
    this claim's SCOPE", never "what is the right number"."""
    if field not in _NUMERIC_SCOPE_RISK_FIELDS or not pages or source_page is None:
        return "SINGLE_SCOPE"

    if source_excerpt and _WHOLE_PLAN_SCOPE_PHRASES_RE.search(source_excerpt):
        return "SINGLE_SCOPE"
    if source_excerpt and _YEAR_RANGE_RE.search(source_excerpt):
        return "SINGLE_SCOPE"

    # The candidate's own excerpt carries none of the whole-plan
    # qualifying language above - exactly the bare "TOTAL <number>" shape.
    # Only now is it worth checking whether the wider processed text shows
    # a genuine multi-phase structure with a DIFFERING total near another
    # phase mention.
    phase_pages: dict[int, list[re.Match]] = {}
    for page_number, text in pages:
        matches = list(_PHASE_RE.finditer(text))
        if matches:
            phase_pages[page_number] = matches

    distinct_phase_labels = {
        _normalise_for_citation(m.group(0)) for matches in phase_pages.values() for m in matches
    }
    if len(distinct_phase_labels) < 2:
        return "SINGLE_SCOPE"

    for page_number, phase_matches in phase_pages.items():
        page_text = dict(pages)[page_number]
        for total_match in _BARE_TOTAL_RE.finditer(page_text):
            competing_value = _parse_int(total_match.group(1))
            if competing_value is None or competing_value == value:
                continue
            for phase_match in phase_matches:
                if abs(total_match.start() - phase_match.start()) <= _PHASE_TOTAL_PROXIMITY_CHARS:
                    return "MULTI_SCOPE"

    return "SINGLE_SCOPE"


def _numeric_scope_review_reason(field: str, value) -> str:
    return (
        f"{field!r}={value!r} is not clearly qualified as the whole-plan total in its own supporting evidence, "
        f"and the processed document shows a repeated-phase/multi-section structure with another, differing total - "
        f"this proposal requires human review to confirm it represents the complete whole-plan figure rather than "
        f"one of several sections/phases"
    )


def validate_fact(
    fact: dict, sibling_groups: list[list[str]] | None = None, source_text: str | None = None,
    pages: list[tuple[int, str]] | None = None,
) -> dict:
    """fact: {"field", "value", "source_page", "source_excerpt", "confidence"}
    (see app.extraction.plan_evidence). Returns
    {"field", "parsed_value", "is_valid", "rejection_reason", "raw_fact"} -
    parsed_value is None whenever is_valid is False OR the source value
    itself was null (both are legitimate "nothing to propose" outcomes,
    distinguished by rejection_reason being set only for the former).

    Also returns (Gate 3A, always present, "not_checked"/original page when
    pages isn't given - fully backward compatible): "citation_status" (see
    CitationVerification.status), "verified_source_page" (the page a
    caller should actually WRITE - equal to the model's own source_page
    unless status is "corrected"), "citation_note" (a human-readable
    explanation, set whenever status isn't "verified"/"not_checked").

    sibling_groups, source_text (LPDI V1 Gate 2A, both optional, default
    None - fully backward compatible with every existing caller):
    sibling_groups is the target plan's known sibling plan identities (see
    app.policy.plan_identity.sibling_alias_groups); source_text is the
    full text of the pages this extraction pass read (see
    app.policy.extract_plan_evidence.run_extraction). When sibling_groups
    is given, a would-otherwise-be-accepted fact whose excerpt (or, when
    source_text is also given, whose excerpt's own sentence within
    source_text) explicitly names a sibling plan is rejected instead - see
    detect_sibling_plan_reference.

    pages (LPDI V1 Gate 3A, optional, default None - fully backward
    compatible): the same page-bounded [(page_number, text), ...] the
    extraction pass itself read - see verify_citation. When given, a fact
    that is otherwise valid is additionally checked for citation integrity;
    an ambiguous or unverifiable citation does NOT reject the fact (a
    citation problem is not necessarily a VALUE problem - see verify_
    citation's own docstring) - it is surfaced via citation_status/
    citation_note for the caller (app.policy.extract_plan_evidence.
    run_extraction) to force into the existing needs_review pathway.

    Also always returns (LPDI V1 Gate 3D): "structured_text_risk" (see
    classify_structured_text_risk - "not_applicable" for a null/rejected
    fact) and "force_review_reason" (set, alongside "STRUCTURED_TEXT",
    when a free-text fact in the narrow risk surface states multiple
    period/label -> value relationships that cannot be verified from
    linearised source text - not a rejection, the proposal/citation are
    still preserved; the caller forces this into the existing
    needs_review pathway exactly as it already does for an ambiguous/
    unverified citation).

    Also always returns (LPDI V1 Gate 3K): "numeric_scope_risk" (see
    classify_numeric_scope_risk - "not_applicable" for a null/rejected
    fact or a field outside the narrow risk surface) and
    "numeric_scope_review_reason" (set, alongside "MULTI_SCOPE", when a
    whole-plan numeric total's own evidence doesn't establish whole-plan
    scope and the processed document shows a repeated-phase/multi-section
    structure - same non-rejecting, force-into-review pattern as Gate 3A/
    3D above)."""
    result = _validate_fact_fields(fact)
    if sibling_groups and result["is_valid"] and result["parsed_value"] is not None:
        reason = detect_sibling_plan_reference(fact.get("source_excerpt"), sibling_groups, source_text)
        if reason:
            return {
                "field": result["field"], "parsed_value": None, "is_valid": False, "rejection_reason": reason,
                "raw_fact": fact, "citation_status": "not_checked", "verified_source_page": fact.get("source_page"),
                "citation_note": None, "structured_text_risk": "not_applicable", "force_review_reason": None,
                "numeric_scope_risk": "not_applicable", "numeric_scope_review_reason": None,
            }

    result = dict(result)
    original_page = fact.get("source_page")
    if result["is_valid"] and result["parsed_value"] is not None:
        citation = verify_citation(result["field"], original_page, fact.get("source_excerpt"), pages)
    else:
        citation = CitationVerification("not_checked", original_page, None)

    result["citation_status"] = citation.status
    result["verified_source_page"] = citation.verified_page if citation.status == "corrected" else original_page
    result["citation_note"] = citation.note

    structured_risk = "not_applicable"
    force_review_reason = None
    if result["is_valid"] and result["parsed_value"] is not None:
        structured_risk = classify_structured_text_risk(result["field"], str(result["parsed_value"]))
        if structured_risk == "STRUCTURED_TEXT":
            force_review_reason = _structured_text_review_reason(result["field"])
    result["structured_text_risk"] = structured_risk
    result["force_review_reason"] = force_review_reason

    numeric_scope_risk = "not_applicable"
    numeric_scope_review_reason = None
    if result["is_valid"] and result["parsed_value"] is not None:
        numeric_scope_risk = classify_numeric_scope_risk(
            result["field"], result["parsed_value"], result["verified_source_page"], fact.get("source_excerpt"), pages,
        )
        if numeric_scope_risk == "MULTI_SCOPE":
            numeric_scope_review_reason = _numeric_scope_review_reason(result["field"], result["parsed_value"])
    result["numeric_scope_risk"] = numeric_scope_risk
    result["numeric_scope_review_reason"] = numeric_scope_review_reason
    return result


def _validate_fact_fields(fact: dict) -> dict:
    field = fact["field"]
    value = fact.get("value")
    excerpt = fact.get("source_excerpt")

    if value is None:
        return {"field": field, "parsed_value": None, "is_valid": True, "rejection_reason": None, "raw_fact": fact}

    if not isinstance(value, str) or not value.strip():
        return {"field": field, "parsed_value": None, "is_valid": False, "rejection_reason": "empty or non-string value", "raw_fact": fact}

    # Part 5 / Part 6: never accept a fact with a real value but no
    # supporting excerpt - "adopted status requires explicit evidence" and
    # "five-year supply years require explicit source wording" are both
    # instances of this same general rule, not special-cased separately.
    if not excerpt or not excerpt.strip():
        return {"field": field, "parsed_value": None, "is_valid": False, "rejection_reason": "no supporting excerpt for a non-null value", "raw_fact": fact}

    # A numeric claim with an excerpt that contains no digit at all is a
    # strong sign the "excerpt" doesn't actually support the number -
    # a cheap, generic anti-hallucination check for every numeric field.
    # The much stronger check - does the excerpt contain THIS number, not
    # just some digit - runs per-branch below, once the value is parsed.
    if field in _NUMERIC_FIELDS and not re.search(r"\d", excerpt):
        return {"field": field, "parsed_value": None, "is_valid": False, "rejection_reason": "excerpt contains no digits to support a numeric value", "raw_fact": fact}

    if field in _NON_NEGATIVE_INT_FIELDS:
        parsed = _parse_int(value)
        if parsed is None:
            return {"field": field, "parsed_value": None, "is_valid": False, "rejection_reason": f"{value!r} is not a valid integer", "raw_fact": fact}
        if parsed < 0:
            return {"field": field, "parsed_value": None, "is_valid": False, "rejection_reason": f"{parsed} must not be negative", "raw_fact": fact}
        if field in _ANNUAL_FIGURE_FIELDS and parsed > _MAX_PLAUSIBLE_ANNUAL_FIGURE:
            return {"field": field, "parsed_value": None, "is_valid": False, "rejection_reason": f"{parsed} is not a plausible single-authority annual figure - likely a plan-period total mislabelled as annual", "raw_fact": fact}
        if not _excerpt_supports_number(excerpt, parsed):
            return {"field": field, "parsed_value": None, "is_valid": False, "rejection_reason": f"excerpt does not appear to state the value {parsed}", "raw_fact": fact}
        return {"field": field, "parsed_value": parsed, "is_valid": True, "rejection_reason": None, "raw_fact": fact}

    if field in _SIGNED_INT_FIELDS:
        parsed = _parse_int(value)
        if parsed is None:
            return {"field": field, "parsed_value": None, "is_valid": False, "rejection_reason": f"{value!r} is not a valid integer", "raw_fact": fact}
        if not _excerpt_supports_number(excerpt, parsed):
            return {"field": field, "parsed_value": None, "is_valid": False, "rejection_reason": f"excerpt does not appear to state the value {parsed}", "raw_fact": fact}
        return {"field": field, "parsed_value": parsed, "is_valid": True, "rejection_reason": None, "raw_fact": fact}

    if field in _YEAR_FIELDS:
        parsed = _parse_int(value)
        if parsed is None or not (_MIN_PLAUSIBLE_YEAR <= parsed <= _MAX_PLAUSIBLE_YEAR):
            return {"field": field, "parsed_value": None, "is_valid": False, "rejection_reason": f"{value!r} is not a plausible plan-period year", "raw_fact": fact}
        if not _excerpt_supports_number(excerpt, parsed):
            return {"field": field, "parsed_value": None, "is_valid": False, "rejection_reason": f"excerpt does not appear to state the year {parsed}", "raw_fact": fact}
        return {"field": field, "parsed_value": parsed, "is_valid": True, "rejection_reason": None, "raw_fact": fact}

    if field in _SUPPLY_YEARS_FIELDS:
        parsed = _parse_float(value)
        if parsed is None or not (0 <= parsed <= _MAX_PLAUSIBLE_SUPPLY_YEARS):
            return {"field": field, "parsed_value": None, "is_valid": False, "rejection_reason": f"{value!r} is not a plausible number of years of supply", "raw_fact": fact}
        if not _excerpt_supports_number(excerpt, parsed):
            return {"field": field, "parsed_value": None, "is_valid": False, "rejection_reason": f"excerpt does not appear to state the value {parsed}", "raw_fact": fact}
        return {"field": field, "parsed_value": parsed, "is_valid": True, "rejection_reason": None, "raw_fact": fact}

    if field in _PERCENTAGE_FIELDS:
        parsed = _parse_float(value.replace("%", ""))
        if parsed is None or not (0 <= parsed <= 100):
            return {"field": field, "parsed_value": None, "is_valid": False, "rejection_reason": f"{value!r} is not a valid percentage (0-100)", "raw_fact": fact}
        if not _excerpt_supports_number(excerpt, parsed):
            return {"field": field, "parsed_value": None, "is_valid": False, "rejection_reason": f"excerpt does not appear to state the value {parsed}", "raw_fact": fact}
        return {"field": field, "parsed_value": parsed, "is_valid": True, "rejection_reason": None, "raw_fact": fact}

    if field in _DATE_FIELDS:
        if not _looks_like_a_plausible_date(value):
            return {"field": field, "parsed_value": None, "is_valid": False, "rejection_reason": f"{value!r} does not look like a valid date", "raw_fact": fact}
        return {"field": field, "parsed_value": value.strip(), "is_valid": True, "rejection_reason": None, "raw_fact": fact}

    if field == "raw_plan_status":
        normalised = normalise_plan_status(value)
        if normalised == "adopted" and (not excerpt or not excerpt.strip()):
            # Redundant with the universal excerpt check above in practice,
            # but kept explicit - Part 6 names this exact case by name, and
            # this is the one place a false negative would be worst.
            return {"field": field, "parsed_value": None, "is_valid": False, "rejection_reason": "adopted status claimed with no supporting excerpt", "raw_fact": fact}
        return {"field": field, "parsed_value": value.strip(), "is_valid": True, "rejection_reason": None, "raw_fact": fact}

    # Free-text fields (plan_name, plan_version, requirement_basis, notes
    # fields, etc.) - no numeric/date shape to validate, just pass through.
    return {"field": field, "parsed_value": value.strip(), "is_valid": True, "rejection_reason": None, "raw_fact": fact}


def validate_facts(
    facts: list[dict], sibling_groups: list[list[str]] | None = None, source_text: str | None = None,
    pages: list[tuple[int, str]] | None = None,
) -> list[dict]:
    """Runs validate_fact over a whole extraction pass's results, then
    applies the cross-field rules that can't be checked per-fact in
    isolation: plan_period_end must not precede plan_period_start, and the
    two must not be equal.

    sibling_groups, source_text, pages: see validate_fact - all optional,
    default None, fully backward compatible."""
    results = [validate_fact(f, sibling_groups, source_text, pages) for f in facts]

    by_field = {r["field"]: r for r in results}
    start = by_field.get("plan_period_start")
    end = by_field.get("plan_period_end")
    if start and end and start["is_valid"] and end["is_valid"] and start["parsed_value"] is not None and end["parsed_value"] is not None:
        if end["parsed_value"] < start["parsed_value"]:
            end["is_valid"] = False
            end["rejection_reason"] = f"plan_period_end ({end['parsed_value']}) precedes plan_period_start ({start['parsed_value']})"
            end["parsed_value"] = None
        elif end["parsed_value"] == start["parsed_value"]:
            # A real, live pilot run against the actual Stockport Local
            # Plan surfaced this: the source text only stated "...to
            # 2042" (an end year), but with no explicit start year visible
            # on the page the model echoed the same figure into both
            # fields, citing the identical excerpt for each. A Local Plan
            # period is never a single year, so this is always implausible
            # - rejecting plan_period_start specifically (not end) matches
            # how these documents are conventionally phrased ("to YYYY"
            # names the end year, never the start).
            start["is_valid"] = False
            start["rejection_reason"] = (
                f"plan_period_start equals plan_period_end ({start['parsed_value']}) - a Local Plan period is "
                f"never a single year; likely the source only stated the end year and this was echoed for the start."
            )
            start["parsed_value"] = None

    return results
