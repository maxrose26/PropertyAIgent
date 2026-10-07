"""Gate B validation runner (specification 026): ONE read-only window -> ONE non-secret artifact. Offline-proven; production execution needs separate authority.

Reuses the accepted architecture only (load_buyer_family_inputs / evaluate_buyer_families, the shared phasing fact, family_presentation, the legacy buyer feed as comparator). It adds no
opportunity logic, no ranking, no extraction, never sums unit counts and never claims availability or residual capacity.
"""
from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import json
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone

from app.policy.agent_evaluation_persistence import AGENT_EVALUATION_INPUT_FINGERPRINT_VERSION
from app.policy.agent_evaluation_result import AGENT_EVALUATION_POLICY_VERSION
from app.policy.buyer_matching import (
    AFFORDABLE_UNITS, BUYER_MATCHING_POLICY_VERSION, PHASING_CURRENT_EVIDENCED_PHASE, PHASING_CURRENTNESS_UNKNOWN, PHASING_HISTORICAL_ONLY, PHASING_NONE_IDENTIFIED, discovery_bounds,
)
from app.security.access import AccessDenied
from app.reporting.buyer_family_feed import UnknownBuyerProfile, evaluate_buyer_families, load_buyer_family_inputs
from app.reporting.family_presentation import _subject_label, phasing_context
from app.pipeline.phase_tracking import UNPHASED_LABEL
from app.reporting.opportunity_families import SLOT_LIFECYCLE, SLOT_PHASE, STRATEGIC_LAND, fit_rank, subject_from_feed_card
from verification.gate_b.safety import read_only_window

ARTIFACT_VERSION = 1
PRIMARY_BUYER = "nesten_homes"
OTHER_BUYERS = ("national_housebuilder", "strategic_land_buyer", "housing_association")
STATES = (PHASING_CURRENT_EVIDENCED_PHASE, PHASING_CURRENTNESS_UNKNOWN, PHASING_HISTORICAL_ONLY, PHASING_NONE_IDENTIFIED)
COHORT_SAMPLE = 25
# The Nesten mandate values BEFORE the accepted correction (spec 027 / commit f8e1c9b). Used ONLY for the labelled counterfactual (same universe, same facts, only these two matching rules differ) so the
# MANDATE-CHANGE EFFECT can be separated from UNIVERSE DRIFT. Never used for validation results.
COUNTERFACTUAL_OLD_NESTEN = {"target_unit_max": 100, "wholly_affordable_is_exclusion": True}
NEWLY_SURFACED, BETTER_REPRESENTED, DEDUPLICATED, COMPARABLE, OUTSIDE_NEW_WINDOW = "NEWLY_SURFACED", "BETTER_REPRESENTED", "DEDUPLICATED", "COMPARABLE", "OUTSIDE_NEW_WINDOW"
COMPARISON_CAVEAT = ("Relative to the legacy flat feed WINDOW of the same size only. NEWLY_SURFACED means absent from that window, not 'undiscoverable' (the legacy candidate pool is not re-derived). "
                     "Order within a fit bucket is lexical and non-commercial; no position is a market ranking.")

DEFINITIONS = {
    "phase_subject": "a family member whose slot is a named phase (an opportunity subject)",
    "qualified_phasing_evidence": "the shared AcquisitionPhasingEvidence state of the development (CURRENT_EVIDENCED_PHASE, PHASE_EVIDENCE_CURRENTNESS_UNKNOWN, HISTORICAL_PHASE_ONLY, NONE_IDENTIFIED); distinct from phase-subject existence",
    "unqualified_phase_subject": "a family with a phase subject whose qualified state is NONE_IDENTIFIED (address-only label or no substantive granted anchor; the two are not separated without new extraction)",
    "oversized_wider_family": "a family with a wider (non-self-phase) planning-delivery subject for which phasing_is_acquisition_relevant holds for the buyer (above the mandate's discovery maximum, total-units mandate)",
    "comparable_legacy_window": "build_opportunity_feed in buyer mode called with the same limit N as the family shortlist (the legacy candidate pool is not re-derived)",
    NEWLY_SURFACED: "in the new top-N, and the legacy window of the same size holds NO card for that site/allocation",
    BETTER_REPRESENTED: "the legacy window holds card(s) for the site/allocation, but the new representative is a different, strictly better-fit subject",
    DEDUPLICATED: "the legacy window held SEVERAL cards for the site/allocation which now collapse into one family, without a better representative (less duplication; no better discovery is claimed)",
    COMPARABLE: "the legacy window already presents the same representative, or a different one of equal fit (no improvement is claimed)",
    OUTSIDE_NEW_WINDOW: "the family is not within the new top-N window (reported with its legacy presence)",
    "ordering": "the existing v7 family order (fit bucket, then lexical family key). Ties are NON-COMMERCIAL; this is not a market ranking and no new ranking is introduced",
    "legacy_limits": "only absence from / presence in the legacy WINDOW can be established; whether the legacy candidate pool contained the subject is not re-derived",
    "counterfactual_old_nesten": "an in-memory evaluation of the SAME families/facts with target_unit_max=100 and wholly_affordable_is_exclusion=True (the pre-correction rules), reported only to separate the mandate-change effect from universe drift; the validation results always use the stored mandate",
    "family_index": "every Nesten family with every subject's identity, exact/approximate scale and fit; no totals, residuals or availability claims",
    "no_inference": "no unit counts are summed, no residual/remaining capacity, availability, ownership, willingness or subdivision is inferred",
}


def resolve_code_sha(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    for variable in ("RENDER_GIT_COMMIT", "GITHUB_SHA"):
        if os.getenv(variable):
            return os.environ[variable]
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except Exception:  # noqa: BLE001 - the SHA is metadata; never fail the validation for it
        return "unknown"


def mandate_digest(policy) -> str:
    """Non-secret identifier of the exact mandate semantics used (sha256 of the policy dataclass; no credentials or personal data are part of it)."""
    def default(value):
        return sorted(value) if isinstance(value, (set, frozenset)) else str(value)
    return hashlib.sha256(json.dumps(dataclasses.asdict(policy), sort_keys=True, default=default).encode()).hexdigest()[:16]


def _count_record(card: dict) -> dict:
    assessment = card.get("count_assessment")
    if assessment is None:
        return {"display": None, "precision": None, "value": None, "lower": None, "upper": None, "scope": None}
    return {"display": assessment.label(), "precision": assessment.precision, "value": assessment.value, "lower": assessment.lower, "upper": assessment.upper, "scope": assessment.scope_type}


def subject_record(member) -> dict:
    card = member.source
    fit = card["buyer_fit"]
    record = {"subject_key": member.subject_key, "slot": member.slot, "named_phase": _is_named_phase(member), "label": _subject_label(member, card), "fit": fit.classification,
              "investigative": bool(fit.is_investigative_exception), "phasing_relevant": card.get("acquisition_phasing_relevant"),
              "reasons": {"matches": list(fit.matches), "unknown": list(fit.unknown), "investigate": list(fit.investigate), "does_not_match": list(fit.does_not_match)}}
    record.update({"count": _count_record(card)})
    return record


def family_state(family) -> str | None:
    for member in family.members:
        evidence = (member.source or {}).get("acquisition_phasing")
        if evidence is not None:
            return evidence.state
    return None


def _is_named_phase(member) -> bool:
    """A NAMED phase subject (the unphased 'Wider permission' bucket shares the PHASE slot but is the wider subject, not a phase)."""
    return member.slot == SLOT_PHASE and (member.source or {}).get("phase_code") != UNPHASED_LABEL


def analyse_family(family) -> dict:
    members = family.members
    slots = ["PHASE" if _is_named_phase(m) else "OTHER" for m in members]
    state = family_state(family)
    relevant = any((m.source or {}).get("acquisition_phasing_relevant") is True for m in members)
    phase_members = [m for m in members if _is_named_phase(m)]
    return {"family": family, "domain": family.family_key[0], "state": state, "has_phase_subject": bool(phase_members), "phase_only": bool(members) and all(s == "PHASE" for s in slots),
            "oversized_wider": relevant, "label": phasing_context(family), "phase_members": phase_members,
            "buyer_sized_phase": [m for m in phase_members if m.fit in ("STRONG_FIT", "POSSIBLE_FIT")]}


def fit_bucket(family) -> str:
    rep = family.representative
    if rep.fit == "STRONG_FIT":
        return "STRONG_FIT"
    if rep.fit == "POSSIBLE_FIT":
        return "POSSIBLE_FIT"
    if rep.fit == "INSUFFICIENT_EVIDENCE":
        return "INSUFFICIENT_INVESTIGATIVE" if rep.investigative else "INSUFFICIENT"
    return "NOT_SUITABLE"


def phasing_population(analyses: list[dict]) -> dict:
    planning = [a for a in analyses if a["domain"] != STRATEGIC_LAND]
    by_state = Counter(a["state"] or "FACT_MISSING" for a in planning)
    phase_by_state = Counter(a["state"] or "FACT_MISSING" for a in planning if a["has_phase_subject"])
    return {"planning_delivery_families_assessed": len(planning), "families_with_any_phase_subject": sum(a["has_phase_subject"] for a in planning),
            "qualified_phasing_state": {s: by_state.get(s, 0) for s in (*STATES, "FACT_MISSING")},
            "families_with_phase_subject_by_qualified_state": {s: phase_by_state.get(s, 0) for s in (*STATES, "FACT_MISSING")},
            "phase_subject_without_qualified_phasing_evidence": phase_by_state.get(PHASING_NONE_IDENTIFIED, 0)}


def _legacy_index(cards: list) -> dict:
    """family_key -> {'subjects': [subject_key...], 'best_rank': int|None} from the legacy window's cards (the G3a feed-card adapter; malformed cards are counted, never guessed)."""
    index, malformed = {}, 0
    for card in cards:
        try:
            subject = subject_from_feed_card(card)
        except Exception:  # noqa: BLE001
            malformed += 1
            continue
        fit = card.get("buyer_fit")
        rank = fit_rank(fit.classification, bool(fit.is_investigative_exception)) if fit is not None else None
        entry = index.setdefault(subject.family_key, {"subjects": [], "best_rank": None})
        entry["subjects"].append(subject.subject_key)
        if rank is not None and (entry["best_rank"] is None or rank < entry["best_rank"]):
            entry["best_rank"] = rank
    return {"index": index, "malformed_legacy_cards": malformed}


def compare_with_legacy(family, in_new_window: bool, legacy: dict | None) -> dict:
    if legacy is None:
        return {"comparison": None, "legacy_cards_for_family": None}
    entry = legacy["index"].get(family.family_key)
    present = entry["subjects"] if entry else []
    if not in_new_window:
        return {"comparison": OUTSIDE_NEW_WINDOW, "legacy_cards_for_family": len(present)}
    if not present:
        return {"comparison": NEWLY_SURFACED, "legacy_cards_for_family": 0}
    rep = family.representative
    better = rep.subject_key not in present and entry["best_rank"] is not None and fit_rank(rep.fit, rep.investigative) < entry["best_rank"]
    label = BETTER_REPRESENTED if better else (DEDUPLICATED if len(present) > 1 else COMPARABLE)
    return {"comparison": label, "legacy_cards_for_family": len(present)}


def _site_context(sites: dict, family) -> dict:
    if family.family_key[0] == STRATEGIC_LAND:
        card = family.representative.source or {}
        return {"site_id": None, "allocation_id": family.family_key[1], "council_code": None, "title": card.get("title")}
    site = sites.get(family.family_key[1])
    return {"site_id": family.family_key[1], "allocation_id": None, "council_code": getattr(site, "council_code", None), "title": getattr(site, "display_address", None)}


def family_record(analysis: dict, sites: dict, comparison: dict, position: int | None) -> dict:
    family = analysis["family"]
    ordered = [family.representative, *[r.subject for r in family.related]]
    return {"position_in_order": position, "family_id": f"{family.family_key[0]}:{family.family_key[1]}", **_site_context(sites, family),
            "family_fit": family.representative.fit, "family_investigative": family.representative.investigative, "representative": family.representative.subject_key,
            "qualified_phasing_state": analysis["state"], "has_phase_subject": analysis["has_phase_subject"], "oversized_wider": analysis["oversized_wider"],
            "phasing_badge": analysis["label"], "overlap": "MAY_OVERLAP_DO_NOT_ADD" if len(ordered) > 1 else "SINGLE_SUBJECT",
            "comparison": comparison["comparison"], "legacy_cards_for_family": comparison["legacy_cards_for_family"],
            "subjects": [subject_record(m) for m in ordered]}


def _precision_unknown(member) -> bool:
    record = (member.source or {}).get("count_assessment")
    return record is None or record.precision != "EXACT"


def cohort_groups(analyses: list[dict]) -> dict:
    planning = [a for a in analyses if a["domain"] != STRATEGIC_LAND]
    groups = {
        "oversized_wider_without_qualified_phasing": [a for a in planning if a["oversized_wider"] and a["state"] == PHASING_NONE_IDENTIFIED],
        "phase_subject_without_qualified_phasing_evidence": [a for a in planning if a["has_phase_subject"] and a["state"] == PHASING_NONE_IDENTIFIED],
        "currentness_unknown_phasing": [a for a in planning if a["state"] == PHASING_CURRENTNESS_UNKNOWN],
        "phase_subject_without_exact_count": [a for a in planning if any(_precision_unknown(m) for m in a["phase_members"])],
        "no_buyer_relevant_acquisition_scope": [a for a in analyses if fit_bucket(a["family"]) == "INSUFFICIENT_INVESTIGATIVE" and not a["buyer_sized_phase"]],
    }
    return groups


def negative_cohort(groups: dict, sites: dict) -> dict:
    def sample(items):
        return [{"family_id": f"{a['family'].family_key[0]}:{a['family'].family_key[1]}", "qualified_phasing_state": a["state"], "family_fit": a["family"].representative.fit,
                 **{k: v for k, v in _site_context(sites, a["family"]).items() if k != "allocation_id"}} for a in items[:COHORT_SAMPLE]]
    return {name: {"total": len(items), "sample": sample(items), "sample_limit": COHORT_SAMPLE} for name, items in groups.items()}


def _is_wider(member) -> bool:
    return member.slot == SLOT_LIFECYCLE or (member.source or {}).get("phase_code") == UNPHASED_LABEL


def _scale_unestablished(member) -> bool:
    """True when the accepted count evidence cannot place this subject relative to ANY range (no count, UNKNOWN, or an unbounded estimate): the matcher - correctly - manufactures no scale position."""
    assessment = (member.source or {}).get("count_assessment")
    if assessment is None or assessment.precision == "UNKNOWN":
        return True
    return assessment.precision != "EXACT" and (assessment.lower is None or assessment.upper is None)


def population(analyses: list[dict]) -> dict:
    buckets = Counter(fit_bucket(a["family"]) for a in analyses)
    planning = [a for a in analyses if a["domain"] != STRATEGIC_LAND]
    oversized = [a for a in planning if a["oversized_wider"]]
    by_state = Counter(a["state"] or "FACT_MISSING" for a in oversized)
    return {"families_evaluated": len(analyses), "strategic_families": len(analyses) - len(planning), "planning_delivery_families": len(planning),
            "fit": {b: buckets.get(b, 0) for b in ("STRONG_FIT", "POSSIBLE_FIT", "INSUFFICIENT_INVESTIGATIVE", "INSUFFICIENT", "NOT_SUITABLE")},
            "phase_only_families": sum(a["phase_only"] for a in analyses), "oversized_wider_families": len(oversized),
            "oversized_wider_by_qualified_phasing_state": {s: by_state.get(s, 0) for s in (*STATES, "FACT_MISSING")},
            "oversized_wider_with_buyer_sized_current_phase": sum(1 for a in oversized if a["state"] == PHASING_CURRENT_EVIDENCED_PHASE and a["buyer_sized_phase"]),
            "families_showing_phasing_badge": sum(a["label"] is not None for a in analyses),
            "planning_families_whose_wider_subject_scale_is_unestablished": sum(1 for a in planning if any(_is_wider(m) and _scale_unestablished(m) for m in a["family"].members)),
            "planning_families_with_a_wider_subject": sum(1 for a in planning if any(_is_wider(m) for m in a["family"].members))}


def _fit_label_of(subject: dict) -> str:
    return subject["fit"] + ("+investigative" if subject["investigative"] else "")


ATTRIBUTION_EITHER, ATTRIBUTION_SCALE, ATTRIBUTION_AFFORDABLE, ATTRIBUTION_NOT_ISOLATED = "EITHER_FACTOR_SUFFICIENT", "SCALE_100_VS_200", "WHOLLY_AFFORDABLE_EXCLUSION", "CAUSE_NOT_ISOLATED"


def attribute_difference(current: str, full_old: str, scale_only: str | None, affordable_only: str | None) -> str | None:
    """Why does the full counterfactual (both pre-correction rules) differ from the CURRENT corrected result? Decided only from two single-factor counterfactual evaluations of the same facts:
    a factor is the cause only if applying it ALONE reproduces the full counterfactual fit. If neither does alone (an interaction) the answer is CAUSE_NOT_ISOLATED - never a guess."""
    if full_old == current:
        return None
    scale_ok, affordable_ok = scale_only == full_old, affordable_only == full_old
    if scale_ok and affordable_ok:
        return ATTRIBUTION_EITHER
    if scale_ok:
        return ATTRIBUTION_SCALE
    if affordable_ok:
        return ATTRIBUTION_AFFORDABLE
    return ATTRIBUTION_NOT_ISOLATED


def index_record(analysis: dict, sites: dict, old: dict | None = None, scale_only: dict | None = None, affordable_only: dict | None = None) -> dict:
    """A compact record of EVERY subject of a family (the Nesten family index): identity, scale/precision, fit; with the counterfactual fit when supplied. No totals, no residuals."""
    family = analysis["family"]
    subjects = [subject_record(m) for m in (family.representative, *[r.subject for r in family.related])]
    old_subjects = {} if old is None else {s["subject_key"]: s for s in old["subjects"]}
    scale_subjects = {} if scale_only is None else {s["subject_key"]: s for s in scale_only["subjects"]}
    affordable_subjects = {} if affordable_only is None else {s["subject_key"]: s for s in affordable_only["subjects"]}
    representative = family.representative.subject_key
    record = {"family_id": f"{family.family_key[0]}:{family.family_key[1]}", **{k: v for k, v in _site_context(sites, family).items() if k != "allocation_id"},
              "family_fit": _fit_label_of({"fit": family.representative.fit, "investigative": family.representative.investigative}), "family_classification": family.representative.fit,
              "family_investigative": bool(family.representative.investigative), "representative": representative,
              "qualified_phasing_state": analysis["state"], "oversized_wider": analysis["oversized_wider"], "has_phase_subject": analysis["has_phase_subject"],
              "subjects": [{"subject_key": s["subject_key"], "slot": s["slot"], "named_phase": s["named_phase"], "label": s["label"], "fit": _fit_label_of(s), "classification": s["fit"],
                            "investigative": s["investigative"], "is_family_representative": s["subject_key"] == representative, "count": s["count"],
                            **({"counterfactual_fit": _fit_label_of(old_subjects[s["subject_key"]]),
                                "counterfactual_attribution": attribute_difference(_fit_label_of(s), _fit_label_of(old_subjects[s["subject_key"]]),
                                                                                   _fit_label_of(scale_subjects[s["subject_key"]]) if s["subject_key"] in scale_subjects else None,
                                                                                   _fit_label_of(affordable_subjects[s["subject_key"]]) if s["subject_key"] in affordable_subjects else None)}
                               if s["subject_key"] in old_subjects else {})} for s in subjects]}
    if old is not None:
        record["counterfactual_family_fit"] = old["family_fit"]
        record["counterfactual_representative"] = old["representative"]
        record["counterfactual_family_attribution"] = attribute_difference(record["family_fit"], old["family_fit"], None if scale_only is None else scale_only["family_fit"],
                                                                           None if affordable_only is None else affordable_only["family_fit"])
    return record


def _old_view(analysis: dict, sites: dict) -> dict:
    family = analysis["family"]
    return {"family_fit": _fit_label_of({"fit": family.representative.fit, "investigative": family.representative.investigative}), "representative": family.representative.subject_key,
            "subjects": [subject_record(m) for m in (family.representative, *[r.subject for r in family.related])]}


def scale_bands(policy, old_max: int) -> list:
    """Analysis bands DERIVED from the stored mandate (preferred/discovery bounds) and the pre-correction maximum - never hard-coded numbers. Contiguous and exhaustive."""
    lo, hi = policy.target_unit_min, policy.target_unit_max
    dmin, dmax = discovery_bounds(lo, hi)
    _, old_dmax = discovery_bounds(lo, old_max)
    edges = [("below_discovery_minimum", None, dmin - 1), ("discovery_minimum_to_preferred_minimum", dmin, lo - 1), ("preferred_range_before_correction", lo, old_max),
             ("old_discovery_envelope_only", old_max + 1, old_dmax), ("preferred_range_added_by_correction", old_dmax + 1, hi), ("discovery_envelope_above_preferred", hi + 1, dmax),
             ("above_discovery_maximum", dmax + 1, None)]
    return [{"band": name, "low": low, "high": high} for name, low, high in edges if low is None or high is None or low <= high]


def scale_band(value, bands) -> str | None:
    if value is None:
        return None
    for band in bands:
        if (band["low"] is None or value >= band["low"]) and (band["high"] is None or value <= band["high"]):
            return band["band"]
    return None


def nesten_scale_cohorts(index: list, policy, old_max: int) -> dict:
    """Subjects with an EXACT count in the commercially important bands (derived from the mandate: above the old preferred maximum up to the new preferred maximum, and above the new preferred
    maximum up to the new discovery maximum), taken from the index (no new rules)."""
    bands_def = scale_bands(policy, old_max)
    cohort_a = (old_max + 1, policy.target_unit_max)
    cohort_b = (policy.target_unit_max + 1, discovery_bounds(policy.target_unit_min, policy.target_unit_max)[1])
    bands = Counter()
    cohorts = {"exact_above_old_preferred_max_to_new_preferred_max": [], "exact_above_new_preferred_max_to_discovery_max": []}
    for record in index:
        for subject in record["subjects"]:
            count = subject["count"]
            if count["precision"] != "EXACT" or count["value"] is None:
                continue
            band = scale_band(count["value"], bands_def)
            bands[band] += 1
            row = {"family_id": record["family_id"], "council_code": record["council_code"], "title": record["title"], "subject_key": subject["subject_key"], "slot": subject["slot"],
                   "named_phase": subject["named_phase"], "scale": count["display"], "scope": count["scope"], "fit": subject["fit"], "counterfactual_fit": subject.get("counterfactual_fit"),
                   "is_family_representative": subject["subject_key"] == record["representative"], "family_fit": record["family_fit"]}
            if cohort_a[0] <= count["value"] <= cohort_a[1]:
                cohorts["exact_above_old_preferred_max_to_new_preferred_max"].append(row)
            elif cohort_b[0] <= count["value"] <= cohort_b[1]:
                cohorts["exact_above_new_preferred_max_to_discovery_max"].append(row)
    return {"bands": bands_def, "cohort_ranges": {"exact_above_old_preferred_max_to_new_preferred_max": cohort_a, "exact_above_new_preferred_max_to_discovery_max": cohort_b},
            "exact_count_band_totals": {b["band"]: bands.get(b["band"], 0) for b in bands_def}, **{k: {"total": len(v), "subjects": v} for k, v in cohorts.items()}}


def counterfactual_delta(index: list) -> dict:
    families, subjects, changed = Counter(), Counter(), []
    family_attribution, subject_attribution = Counter(), Counter()
    for record in index:
        if "counterfactual_family_fit" not in record:
            continue
        families[f"{record['counterfactual_family_fit']} -> {record['family_fit']}"] += 1
        if record.get("counterfactual_family_attribution"):
            family_attribution[record["counterfactual_family_attribution"]] += 1
        moved = [{"subject_key": s["subject_key"], "label": s["label"], "scale": s["count"]["display"], "precision": s["count"]["precision"], "counterfactual_fit": s["counterfactual_fit"], "attribution": s.get("counterfactual_attribution"), "fit": s["fit"]}
                 for s in record["subjects"] if s.get("counterfactual_fit") not in (None, s["fit"])]
        for s in record["subjects"]:
            if "counterfactual_fit" in s:
                subjects[f"{s['counterfactual_fit']} -> {s['fit']}"] += 1
                if s.get("counterfactual_attribution"):
                    subject_attribution[s["counterfactual_attribution"]] += 1
        if record["counterfactual_family_fit"] != record["family_fit"] or record["counterfactual_representative"] != record["representative"] or moved:
            changed.append({"family_id": record["family_id"], "council_code": record["council_code"], "title": record["title"], "counterfactual_family_fit": record["counterfactual_family_fit"],
                            "family_fit": record["family_fit"], "counterfactual_representative": record["counterfactual_representative"], "representative": record["representative"],
                            "family_attribution": record.get("counterfactual_family_attribution"), "subjects_changed": moved})
    return {"family_fit_matrix": dict(sorted(families.items())), "subject_fit_matrix": dict(sorted(subjects.items())), "changed_families_total": len(changed), "changed_families": changed,
            "family_difference_attribution": dict(sorted(family_attribution.items())), "subject_difference_attribution": dict(sorted(subject_attribution.items())),
            "attribution_method": "single-factor counterfactual evaluations of the same facts: a factor is named only if applying it alone reproduces the full counterfactual; otherwise EITHER_FACTOR_SUFFICIENT or CAUSE_NOT_ISOLATED"}


def _legacy_window(session, buyer_key: str, window: int):
    from app.reporting.opportunity_feed import build_opportunity_feed
    return build_opportunity_feed(session, limit=window, buyer_key=buyer_key)


def run_validation(session, *, real: bool, code_sha: str | None = None, shortlist_size: int = 20, statement_timeout_ms: int = 60000, max_queries: int | None = None, include_legacy: bool = True,
                   nesten_index: bool = False, counterfactual_old_nesten: bool = False, clock=lambda: datetime.now(timezone.utc), buyers: tuple = (PRIMARY_BUYER, *OTHER_BUYERS)) -> dict:
    """The whole validation inside one read-only window. Returns the artifact dict (call write_artifact to persist it)."""
    from sqlalchemy import select

    from app.db.models import Site
    from app.policy.buyer_profile_store import get_buyer_profile_dataclass

    with read_only_window(session, real=real, statement_timeout_ms=statement_timeout_ms, max_queries=max_queries) as (instrument, safety):
        inputs = load_buyer_family_inputs(session)
        instrument.snapshot("load_subject_inputs")
        contexts: dict = {}                       # B2 site contexts are buyer-independent: built once, shared across buyers
        results, profiles = {}, {}
        for buyer in buyers:
            try:
                profiles[buyer] = get_buyer_profile_dataclass(session, buyer)
                results[buyer] = evaluate_buyer_families(session, buyer, inputs, 10 ** 9, contexts=contexts, include_excluded=True)
            except (UnknownBuyerProfile, AccessDenied) as error:           # a missing / out-of-scope buyer is recorded, never fatal to the one read window
                results[buyer] = {"error": f"{type(error).__name__}: buyer {buyer!r} could not be evaluated"}
            instrument.snapshot(f"evaluate:{buyer}")
        legacy = None
        primary = results.get(PRIMARY_BUYER)
        if include_legacy and primary is not None and "error" not in primary:
            legacy_feed = _legacy_window(session, PRIMARY_BUYER, shortlist_size)
            legacy = {"window": shortlist_size, **_legacy_index(legacy_feed["cards"]), "cards_returned": len(legacy_feed["cards"])}
            instrument.snapshot("legacy_feed_window")

        buyer_sections, nesten = {}, None
        all_analyses = {}
        for buyer, result in results.items():
            if "error" in result:
                buyer_sections[buyer] = {"error": result["error"]}
                continue
            families = [*result["families"], *result["excluded_families"]]
            analyses = [analyse_family(f) for f in families]
            all_analyses[buyer] = analyses
            policy = profiles[buyer]
            lo, hi = policy.target_unit_min, policy.target_unit_max
            dmin, dmax = discovery_bounds(lo, hi)
            section = {"mandate": {"digest": mandate_digest(policy), "scale_metric": policy.scale_metric, "preferred_min": lo, "preferred_max": hi, "discovery_min": dmin, "discovery_max": dmax},
                       "population": population(analyses), "subject_counts": result["counts"]}
            if policy.scale_metric == AFFORDABLE_UNITS:
                section["total_site_phasing_is_not_affordable_package_evidence"] = {
                    "families_with_current_qualified_phasing": sum(a["state"] == PHASING_CURRENT_EVIDENCED_PHASE for a in analyses),
                    "families_showing_phasing_badge": section["population"]["families_showing_phasing_badge"], "required_badge_count": 0,
                    "holds": section["population"]["families_showing_phasing_badge"] == 0}
            buyer_sections[buyer] = section

        sites = {}
        if PRIMARY_BUYER in all_analyses:
            analyses = all_analyses[PRIMARY_BUYER]
            shown_keys = [f.family_key for f in primary["families"][:shortlist_size]]
            review = [a for a in analyses if a["oversized_wider"] and a["state"] == PHASING_CURRENT_EVIDENCED_PHASE and a["buyer_sized_phase"]]
            groups = cohort_groups(analyses)
            sampled = [a for items in groups.values() for a in items[:COHORT_SAMPLE]]
            shown = [a for a in analyses if a["family"].family_key in shown_keys]
            wanted = {a["family"].family_key[1] for a in (*review, *shown, *sampled) if a["domain"] != STRATEGIC_LAND}      # ONE site-context query for every family the artifact describes
            if nesten_index:
                wanted |= {a["family"].family_key[1] for a in analyses if a["domain"] != STRATEGIC_LAND}
            if wanted:
                sites = {s.id: s for s in session.execute(select(Site).where(Site.id.in_(sorted(wanted)))).scalars()}
            instrument.snapshot("site_context")
            order = {f.family_key: i + 1 for i, f in enumerate(primary["families"])}
            window = set(shown_keys)
            by_key = {a["family"].family_key: a for a in analyses}
            shortlist = [family_record(by_key[k], sites, compare_with_legacy(by_key[k]["family"], True, legacy), order[k]) for k in shown_keys]
            review_records = [family_record(a, sites, compare_with_legacy(a["family"], a["family"].family_key in window, legacy), order.get(a["family"].family_key)) for a in review]
            counts = Counter(r["comparison"] for r in shortlist)
            nesten = {"population": buyer_sections[PRIMARY_BUYER]["population"], "oversized_wider_with_buyer_sized_current_phase": review_records, "shortlist": shortlist,
                      "shortlist_size": shortlist_size, "shortlist_ordering": DEFINITIONS["ordering"],
                      "comparison_counts_in_new_window": {k: counts.get(k, 0) for k in (NEWLY_SURFACED, BETTER_REPRESENTED, DEDUPLICATED, COMPARABLE)}, "comparison_caveat": COMPARISON_CAVEAT,
                      "legacy_window": None if legacy is None else {"window": legacy["window"], "cards_returned": legacy["cards_returned"], "malformed_legacy_cards": legacy["malformed_legacy_cards"]}}
            if nesten_index or counterfactual_old_nesten:
                old_views, scale_views, affordable_views = {}, {}, {}
                if counterfactual_old_nesten:                       # same universe, same facts, same contexts: only the pre-correction matching rules differ (labelled counterfactual)
                    def counterfactual_views(rules):
                        result = evaluate_buyer_families(session, PRIMARY_BUYER, inputs, 10 ** 9, contexts=contexts, include_excluded=True,
                                                         profile=dataclasses.replace(profiles[PRIMARY_BUYER], **rules))
                        found = [analyse_family(f) for f in [*result["families"], *result["excluded_families"]]]
                        return found, {a["family"].family_key: _old_view(a, sites) for a in found}
                    old_analyses, old_views = counterfactual_views(COUNTERFACTUAL_OLD_NESTEN)
                    _, scale_views = counterfactual_views({"target_unit_max": COUNTERFACTUAL_OLD_NESTEN["target_unit_max"]})                               # scale alone (affordable exclusion stays corrected)
                    _, affordable_views = counterfactual_views({"wholly_affordable_is_exclusion": COUNTERFACTUAL_OLD_NESTEN["wholly_affordable_is_exclusion"]})   # exclusion alone (scale stays corrected)
                    instrument.snapshot("counterfactual_old_nesten")
                index = [index_record(a, sites, old_views.get(a["family"].family_key), scale_views.get(a["family"].family_key), affordable_views.get(a["family"].family_key)) for a in analyses]
                nesten["result_basis"] = {"validation_result": "the stored corrected Nesten mandate exactly as read from the database (buyers.nesten_homes.mandate): the ONLY validation / production / current result",
                                          "counterfactual_fields": "every field or section prefixed counterfactual_ (and nesten.counterfactual_old_nesten) is COUNTERFACTUAL ONLY - NOT A VALIDATION RESULT"}
                nesten["family_index"] = index
                nesten["scale_cohorts"] = nesten_scale_cohorts(index, profiles[PRIMARY_BUYER], COUNTERFACTUAL_OLD_NESTEN["target_unit_max"])
                if counterfactual_old_nesten:
                    nesten["counterfactual_old_nesten"] = {"label": "COUNTERFACTUAL ONLY - NOT A VALIDATION RESULT: the same universe and facts evaluated with the pre-correction Nesten rules; isolates the mandate-change effect from universe drift",
                                                           "assumed_old_rules": COUNTERFACTUAL_OLD_NESTEN, "population": population(old_analyses), **counterfactual_delta(index)}
            cohort = negative_cohort(groups, sites)
            phasing = phasing_population(analyses)
        else:
            cohort, phasing = {}, {}
        instrument.snapshot("assemble")
        efficiency = instrument.report()

    artifact = {
        "artifact_version": ARTIFACT_VERSION,
        "run_metadata": {"code_sha": resolve_code_sha(code_sha), "matcher_policy_version": BUYER_MATCHING_POLICY_VERSION,
                         "agent_evaluation_input_fingerprint_version": AGENT_EVALUATION_INPUT_FINGERPRINT_VERSION, "agent_evaluation_policy_version": AGENT_EVALUATION_POLICY_VERSION,
                         "benchmark_version": __import__("benchmark.v7", fromlist=["V7_BENCHMARK_VERSION"]).V7_BENCHMARK_VERSION,
                         "timestamp_utc": clock().astimezone(timezone.utc).isoformat(), "primary_buyer": PRIMARY_BUYER, "production_read_safety": safety,
                         "mandate_digests": {b: s.get("mandate", {}).get("digest") for b, s in buyer_sections.items()}},
        "aggregates": {"phasing_population": phasing, "family_fit_population": {b: s.get("population") for b, s in buyer_sections.items()},
                       "comparison_counts_in_new_window": (nesten or {}).get("comparison_counts_in_new_window"), "comparison_caveat": COMPARISON_CAVEAT},
        "buyers": buyer_sections, "nesten": nesten, "negative_cohort": cohort, "efficiency": efficiency, "definitions": DEFINITIONS,
    }
    return artifact


CSV_COLUMNS = ("order_position_non_commercial", "family_id", "council_code", "title", "representative", "family_fit", "investigative", "qualified_phasing_state", "phasing_badge", "comparison",
               "representative_scale", "buyer_sized_phase_scale")


def shortlist_csv(artifact: dict) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for row in (artifact.get("nesten") or {}).get("shortlist", []):
        by_key = {s["subject_key"]: s for s in row["subjects"]}
        phase = next((s for s in row["subjects"] if s["named_phase"] and s["fit"] in ("STRONG_FIT", "POSSIBLE_FIT")), None)
        writer.writerow([row["position_in_order"], row["family_id"], row["council_code"], row["title"], row["representative"], row["family_fit"], row["family_investigative"],
                         row["qualified_phasing_state"], row["phasing_badge"], row["comparison"], by_key[row["representative"]]["count"]["display"], phase["count"]["display"] if phase else ""])
    return out.getvalue()


def artifact_json(artifact: dict) -> str:
    return json.dumps(artifact, indent=2, sort_keys=True, default=str) + "\n"
