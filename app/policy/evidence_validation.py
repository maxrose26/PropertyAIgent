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


def validate_fact(
    fact: dict, sibling_groups: list[list[str]] | None = None, source_text: str | None = None,
) -> dict:
    """fact: {"field", "value", "source_page", "source_excerpt", "confidence"}
    (see app.extraction.plan_evidence). Returns
    {"field", "parsed_value", "is_valid", "rejection_reason", "raw_fact"} -
    parsed_value is None whenever is_valid is False OR the source value
    itself was null (both are legitimate "nothing to propose" outcomes,
    distinguished by rejection_reason being set only for the former).

    sibling_groups, source_text (LPDI V1 Gate 2A, both optional, default
    None - fully backward compatible with every existing caller):
    sibling_groups is the target plan's known sibling plan identities (see
    app.policy.plan_identity.sibling_alias_groups); source_text is the
    full text of the pages this extraction pass read (see
    app.policy.extract_plan_evidence.run_extraction). When sibling_groups
    is given, a would-otherwise-be-accepted fact whose excerpt (or, when
    source_text is also given, whose excerpt's own sentence within
    source_text) explicitly names a sibling plan is rejected instead - see
    detect_sibling_plan_reference."""
    result = _validate_fact_fields(fact)
    if sibling_groups and result["is_valid"] and result["parsed_value"] is not None:
        reason = detect_sibling_plan_reference(fact.get("source_excerpt"), sibling_groups, source_text)
        if reason:
            return {"field": result["field"], "parsed_value": None, "is_valid": False, "rejection_reason": reason, "raw_fact": fact}
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
) -> list[dict]:
    """Runs validate_fact over a whole extraction pass's results, then
    applies the cross-field rules that can't be checked per-fact in
    isolation: plan_period_end must not precede plan_period_start, and the
    two must not be equal.

    sibling_groups, source_text: see validate_fact - both optional,
    default None, fully backward compatible."""
    results = [validate_fact(f, sibling_groups, source_text) for f in facts]

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
