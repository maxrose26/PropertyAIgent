"""Reconciliation: merge the regex housing-mix pass, the LLM affordable
classifier, and the LLM entity/site-intelligence extractions into the final
scheme_intelligence row.

Ported from build_planning_intelligence_master.py, including the
calculate_unit_reconciliation fix from fix_master_function.py (the version
here already has that fix applied - it skips the total/affordable/private
cross-check entirely for statuses in RESOLVED_AFFORDABLE_STATUSES, since
"no affordable required" etc. legitimately have no split to reconcile).
"""
from __future__ import annotations

import re

from app.extraction.housing_mix import HousingMixResult
from app.extraction.prompts import RESOLVED_AFFORDABLE_STATUSES
from app.scrapers.unit_filter import extract_external_consultation

# Statuses in RESOLVED_AFFORDABLE_STATUSES split into two different meanings:
# some mean "there genuinely is no on-site affordable requirement" (a real,
# derivable 0), others mean "this application stage doesn't determine
# affordable housing at all" (genuinely unknown, not zero). Conflating them
# was the root cause of a real bug: an EIA screening opinion correctly
# classified as not_expected_for_application_type still ended up with
# "180 affordable / 0 private" out of 180 total units, because the LLM
# inconsistently also populated affordable_percentage=100 in the same
# response, and the percentage-derivation fallback further down blindly
# trusted it with no awareness of the status.
NO_ONSITE_AFFORDABLE_STATUSES = {"no_affordable_required", "offsite_or_commuted_sum"}
UNKNOWN_SPLIT_STATUSES = {"not_expected_for_application_type", "parent_application_needed"}


def _first_not_none(*values):
    """`a or b` treats 0 as falsy, silently discarding a legitimate
    classifier-provided "zero affordable units" in favour of a regex
    fallback - confirmed a real case where this hid an explicit, correct 0
    behind a stale pre-viability-reduction regex figure. Checking for None
    specifically (not falsiness) preserves an intentional 0."""
    for value in values:
        if value is not None:
            return value
    return None


# Confirmed a real batch of "applicant" names from the portal's raw field
# that are individual people, not companies ("Mr A Tal", "Mr Mohanned
# Naoom"), plus a pure placeholder ("C/O Agent" - correspondence routed via
# the agent, not a name at all) - only ONE of six raw names checked was an
# actual company ("Crescent Investments LLC Limited"). Backfilling
# applicant_company with a person's name or a placeholder would be actively
# wrong, not just unhelpfully blank, so this must gate the fallback rather
# than accept any non-empty string.
_PERSONAL_TITLE_RE = re.compile(r"^(mr|mrs|miss|ms|mx|dr|prof|sir|dame|rev)\.?\s+", re.I)
_COMPANY_INDICATOR_RE = re.compile(
    r"\b(limited|ltd|llp|llc|plc|holdings?|group|homes|properties|developments?|"
    r"investments?|estates?|construction|housing|trust|partnership|inc|corp|company|co\.)\b",
    re.I,
)
_PLACEHOLDER_APPLICANT_NAMES = {"c/o agent", "care of agent", "n/a", "agent", "unknown", "applicant"}


def _normalise_name(name: str | None) -> str:
    return re.sub(r"[^\w\s]", "", (name or "").strip().lower())


def _names_match(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return _normalise_name(a) == _normalise_name(b)


def _looks_like_company_name(name: str | None) -> bool:
    if not name:
        return False
    stripped = name.strip()
    if stripped.lower() in _PLACEHOLDER_APPLICANT_NAMES:
        return False
    if _PERSONAL_TITLE_RE.match(stripped):
        return False
    return bool(_COMPANY_INDICATOR_RE.search(stripped))


def to_float_or_none(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int_like(value):
    number = to_float_or_none(value)
    if number is None:
        return None
    return int(number) if float(number).is_integer() else number


def calculate_unit_reconciliation(
    total: float | None, affordable: float | None, private: float | None,
    affordable_pct: float | None, affordable_status: str | None,
) -> dict:
    affordable_status = (affordable_status or "").strip().lower()

    unit_total_check = None
    unit_total_difference = None
    affordable_percentage_check = None
    issues: list[str] = []

    if affordable_status in RESOLVED_AFFORDABLE_STATUSES:
        return {
            "unit_total_check": None,
            "unit_total_difference": None,
            "affordable_percentage_check": None,
            "unit_reconciliation_status": "OK",
        }

    if total is None:
        issues.append("Missing total units")

    if affordable is not None and private is not None:
        unit_total_check = affordable + private
        if total is not None:
            unit_total_difference = total - unit_total_check
            if abs(unit_total_difference) > 1:
                issues.append("Private + affordable does not equal total")
    else:
        if total is not None:
            if total < 10:
                pass
            elif total < 25:
                issues.append("Missing affordable/private split (10-24 unit scheme)")
            else:
                issues.append("Missing affordable/private split (25+ unit scheme)")
        else:
            issues.append("Missing affordable/private split")

    if total is not None and affordable is not None and total > 0:
        affordable_percentage_check = round((affordable / total) * 100, 2)
        if affordable_pct is not None and abs(affordable_percentage_check - affordable_pct) > 1:
            issues.append("Affordable percentage mismatch")

    status = "OK" if not issues else "Needs manual review: " + " | ".join(issues)

    return {
        "unit_total_check": to_int_like(unit_total_check),
        "unit_total_difference": to_int_like(unit_total_difference),
        "affordable_percentage_check": affordable_percentage_check,
        "unit_reconciliation_status": status,
    }


def reconcile_scheme(
    housing_mix: HousingMixResult,
    affordable_classification: dict,
    entities: dict,
    site_intelligence: dict,
    portal_estimated_units: int | None,
    application_category: str | None = None,
    proposal: str | None = None,
    applicant_name_raw: str | None = None,
) -> dict:
    """Priority order for the *_final fields: LLM classifier > regex housing
    mix > portal-listing estimate. Mirrors build_planning_intelligence_master.py's
    build_council_rows()."""

    classified_affordable_units = affordable_classification.get("affordable_units")
    classified_affordable_pct = affordable_classification.get("affordable_percentage")
    affordable_data_status = (affordable_classification.get("affordable_data_status") or "").strip().lower()

    affordable_units_final = _first_not_none(classified_affordable_units, housing_mix.affordable_units)
    affordable_percentage_final = _first_not_none(classified_affordable_pct, housing_mix.affordable_percentage)
    # Kept alongside the status-driven overrides below, which reassign
    # affordable_percentage_final itself - this is the only place "was ANY
    # percentage signal found at all" (classifier's own field, or failing
    # that the independent regex housing-mix pass) survives to be checked
    # against a status that claims no affordable data exists.
    any_stated_affordable_pct = affordable_percentage_final
    private_units_final = _first_not_none(affordable_classification.get("private_units"), housing_mix.private_units)
    affordable_tenure_split_final = (
        affordable_classification.get("affordable_tenure_split") or housing_mix.affordable_tenure_split
    )
    total_units_final = _first_not_none(
        affordable_classification.get("total_units_context"), housing_mix.total_units, portal_estimated_units
    )

    if affordable_data_status == "viability_reduction":
        # The regex housing-mix pass can't distinguish a pre-reduction
        # policy ask from the actual post-reduction position - confirmed a
        # real case where a viability assessment reduced affordable housing
        # from 15 units (7.5%) to zero, but the regex still picked up the
        # original "15" from the viability summary discussing what was
        # being demonstrated unviable, and reconciliation used it as if it
        # were the final figure. Trust ONLY the classifier's own explicit
        # number for this status (per the prompt rule to state the actual
        # reduced position) - if it didn't give one, this is genuinely
        # unknown, not a regex guess.
        if classified_affordable_units is None:
            affordable_units_final = None
            private_units_final = None
            affordable_percentage_final = None
        else:
            affordable_units_final = classified_affordable_units
            affordable_percentage_final = classified_affordable_pct
            if total_units_final is not None:
                private_units_final = to_float_or_none(total_units_final) - classified_affordable_units

    if affordable_data_status == "all_units_affordable":
        # Force, don't fill-if-None: confirmed a real case where the
        # classifier correctly said "all units affordable" but
        # private_units_final still carried 80 from the regex housing-mix
        # pass, which had picked up an unrelated number elsewhere in the
        # documents. Once the status is confidently "all affordable", any
        # non-zero private figure IS the inconsistency, not a real signal -
        # the classifier's own explicit status is more trustworthy here than
        # a free-text regex match.
        affordable_units_final = total_units_final
        private_units_final = 0
        affordable_percentage_final = 100

    affordable_status_note = None
    if affordable_data_status in NO_ONSITE_AFFORDABLE_STATUSES:
        affordable_units_final = 0
        private_units_final = total_units_final
        affordable_percentage_final = 0
    elif affordable_data_status in UNKNOWN_SPLIT_STATUSES:
        # Not knowable at this application stage - discard any numbers the
        # LLM populated anyway (a screening opinion has no business reporting
        # a 100% affordable split) rather than let them flow into the
        # percentage-derivation fallback below.
        affordable_units_final = None
        private_units_final = None
        affordable_percentage_final = None

    if affordable_data_status in (NO_ONSITE_AFFORDABLE_STATUSES | UNKNOWN_SPLIT_STATUSES) and any_stated_affordable_pct:
        # Self-contradiction confirmed in real cases (PA/2026/0539, Riverside
        # Retail Park - the same underlying documents produced BOTH
        # "no_affordable_required" and "not_expected_for_application_type"
        # across different extraction runs, since the LLM's status choice
        # isn't perfectly deterministic): the classifier picked a status
        # implying no affordable data exists at this stage, while its OWN
        # affordable_percentage field was non-empty anyway - e.g. reason text
        # describing "a minimum of 20% affordable housing... proposed, but no
        # specific number... stated". That's a real commitment, just not yet
        # quantified into a unit count - very different from "genuinely no
        # requirement" or "genuinely not yet determinable", both of which
        # this status would otherwise resolve to a confident, unreviewed
        # "OK". Leave the split unresolved and flag for manual review
        # instead of deriving a unit count from the percentage - the
        # classifier's own reasoning says no such count has actually been
        # stated.
        affordable_units_final = None
        private_units_final = None
        affordable_percentage_final = None
        affordable_status_note = (
            f"A minimum of {any_stated_affordable_pct:.0f}% affordable housing is proposed but not "
            "yet confirmed as a specific unit count - flagged for manual review."
        )

    external_consultation_source = None
    if application_category == "external_consultation":
        # Our portal only holds the neighbouring authority's consultation
        # notice, not the real application's documents (S106, viability,
        # officer report) - any affordable split derived from what little
        # text we do have (or the classifier's best-effort guess with no
        # real evidence) isn't trustworthy. Force unknown rather than show a
        # confident-looking split, and surface where the real data lives.
        affordable_units_final = None
        private_units_final = None
        affordable_percentage_final = None
        consultation_match = extract_external_consultation(proposal)
        if consultation_match:
            council_name, reference = consultation_match
            external_consultation_source = f"{council_name} (ref {reference})"

    # A stated percentage (e.g. proposal text saying "including 40% affordable")
    # is common even when no document ever states the raw unit count - derive
    # it rather than leaving a known figure sitting unused as affordable_units=None.
    # Skipped for UNKNOWN_SPLIT_STATUSES and external_consultation - see above.
    if (
        affordable_units_final is None and affordable_percentage_final is not None and total_units_final
        and affordable_data_status not in UNKNOWN_SPLIT_STATUSES
        and application_category != "external_consultation"
    ):
        affordable_units_final = round(to_float_or_none(total_units_final) * to_float_or_none(affordable_percentage_final) / 100)

    # Final coherence pass: whenever both total and affordable are known,
    # private MUST be their difference - it's definitionally the remainder,
    # never an independently reliable figure. Two real cases confirmed this
    # matters: (1) a 675-unit/50%-affordable scheme where private_units_final
    # still held "3", a stray number the regex pass found on its own with no
    # matching affordable figure alongside it; (2) a 1450-unit scheme where
    # the classifier's own total (1450, its highest-priority source)
    # superseded the regex pass's smaller total (873), but private_units_final
    # kept the regex's 630 - correct for ITS total of 873, meaningless once
    # paired with the classifier's 1450. Recomputing here means total and
    # affordable (each independently prioritised/derived above, and
    # affordable already cross-checked against a stated percentage) are the
    # two trustworthy anchors, and private just follows - it can never be the
    # stale, orphaned figure that used to end up next to a total it was never
    # actually consistent with.
    if total_units_final is not None and affordable_units_final is not None:
        private_units_final = to_float_or_none(total_units_final) - to_float_or_none(affordable_units_final)

    total_units_final = to_int_like(total_units_final)
    affordable_units_final = to_int_like(affordable_units_final)
    private_units_final = to_int_like(private_units_final)
    affordable_percentage_final = to_float_or_none(affordable_percentage_final)

    # Self-contradiction confirmed in a real case (PA/2026/0187): the LLM's
    # own entity_relationship_notes said "RA Design & Project Management Ltd
    # is likely acting as the planning agent... on behalf of Mr Lookman
    # Patel" - correctly identifying it as the agent - yet the SAME response
    # also set developer to that exact name, contradicting its own
    # reasoning. The schema asks for many fields in one call and the model
    # doesn't always keep them internally consistent, so don't just trust
    # developer at face value - if it's an exact (normalised) match for the
    # agent/consultant it also named, that's the model's own evidence the
    # role is agent, not developer.
    developer_final = entities.get("developer")
    if _names_match(developer_final, entities.get("planning_agent")) or _names_match(
        developer_final, entities.get("planning_consultant")
    ):
        developer_final = None

    result = {
        "total_units": housing_mix.total_units,
        "affordable_units": housing_mix.affordable_units,
        "private_units": housing_mix.private_units,
        "affordable_percentage": housing_mix.affordable_percentage,
        "affordable_tenure_split": housing_mix.affordable_tenure_split,
        "housing_confidence": housing_mix.confidence,

        "affordable_data_status": affordable_classification.get("affordable_data_status"),
        "application_context_status": affordable_classification.get("application_context_status"),
        "affordable_classification_reason": affordable_classification.get("reason"),
        "affordable_classification_evidence": affordable_classification.get("evidence"),
        "affordable_classification_confidence": affordable_classification.get("confidence"),
        "affordable_status_note": affordable_status_note,

        "site_area_ha": site_intelligence.get("site_area_ha"),
        "density_dph": site_intelligence.get("density_dph"),
        "development_type": site_intelligence.get("development_type"),
        "housing_typology": site_intelligence.get("housing_typology"),
        "specialist_housing_type": site_intelligence.get("specialist_housing_type"),
        "allocation_status": site_intelligence.get("allocation_status"),
        "existing_use": site_intelligence.get("existing_use"),
        "proposed_use": site_intelligence.get("proposed_use"),
        "site_evidence": site_intelligence.get("evidence"),
        "site_confidence": site_intelligence.get("confidence"),

        # The portal's own "Applicant" field is a direct, reliable answer
        # the AI extraction shouldn't need to rediscover from documents -
        # confirmed a real case where it sat unused in applicant_name_raw
        # while the document-based extraction found nothing, showing
        # "Applicant company: None" despite the portal stating it outright.
        # Only backfills applicant_company (the field that corresponds
        # directly to the portal's own field), not developer - the two are
        # often, but not always, the same legal entity. Gated by
        # _looks_like_company_name - many applicants are private individuals
        # ("Mr A Tal"), not companies, and showing a person's name under
        # "Applicant company" would be wrong, not just unhelpfully blank.
        "applicant_company": _first_not_none(
            entities.get("applicant_company"),
            applicant_name_raw if _looks_like_company_name(applicant_name_raw) else None,
        ),
        "developer": developer_final,
        "landowner": entities.get("landowner"),
        "site_owner": entities.get("site_owner"),
        "planning_agent": entities.get("planning_agent"),
        "architect": entities.get("architect"),
        "housing_association": entities.get("housing_association"),
        "registered_provider": entities.get("registered_provider"),
        "registered_provider_status": entities.get("registered_provider_status"),
        "contractor": entities.get("contractor"),
        "entity_source_evidence": entities.get("source_evidence"),
        "entity_relationship_notes": entities.get("entity_relationship_notes"),
        "entity_confidence": entities.get("confidence"),

        "total_units_final": total_units_final,
        "affordable_units_final": affordable_units_final,
        "private_units_final": private_units_final,
        "affordable_percentage_final": affordable_percentage_final,
        "affordable_tenure_split_final": affordable_tenure_split_final,
        "external_consultation_source": external_consultation_source,
    }

    result.update(
        calculate_unit_reconciliation(
            to_float_or_none(total_units_final),
            to_float_or_none(affordable_units_final),
            to_float_or_none(private_units_final),
            affordable_percentage_final,
            affordable_data_status,
        )
    )
    if application_category == "external_consultation":
        # No real cross-check is possible without the actual application's
        # documents - an unresolved split here is expected, not a data
        # quality problem with OUR extraction.
        result["unit_reconciliation_status"] = "OK"

    units_float = to_float_or_none(total_units_final)
    result["large_scheme_50_plus_units"] = bool(units_float is not None and units_float >= 50)
    result["major_scheme_25_plus_units"] = bool(units_float is not None and units_float >= 25)
    result["major_scheme_10_plus_units"] = bool(units_float is not None and units_float >= 10)

    result["affordable_missing"] = bool(
        units_float is not None
        and units_float >= 25
        and affordable_data_status not in RESOLVED_AFFORDABLE_STATUSES
        and application_category != "external_consultation"
        and not affordable_units_final
    )
    result["developer_info_missing"] = not bool(result.get("developer") or result.get("applicant_company"))

    missing = []
    if not result.get("total_units_final"):
        missing.append("total_units_final")
    if result["affordable_missing"]:
        missing.append("affordable_manual_review")
    if affordable_status_note:
        missing.append(f"affordable_status_unconfirmed: {affordable_status_note}")
    if application_category == "external_consultation":
        missing.append(f"external_consultation_see_source: {external_consultation_source or 'unresolved reference'}")
    if result["developer_info_missing"]:
        missing.append("developer")
    if not result.get("development_type"):
        missing.append("development_type")
    if result["unit_reconciliation_status"] != "OK":
        missing.append("unit_reconciliation")

    result["data_quality_status"] = "OK" if not missing else "Missing/review: " + ", ".join(missing)
    result["core_intelligence_complete"] = not bool(missing)
    result["needs_manual_review"] = bool(missing)

    return result
