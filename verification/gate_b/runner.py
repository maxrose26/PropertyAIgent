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
    BUYER_MATCHING_POLICY_VERSION, PHASING_CURRENT_EVIDENCED_PHASE, PHASING_CURRENTNESS_UNKNOWN, PHASING_HISTORICAL_ONLY, PHASING_NONE_IDENTIFIED, discovery_bounds,
)
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
NEWLY_SURFACED, BETTER_REPRESENTED, COMPARABLE, OUTSIDE_NEW_WINDOW = "NEWLY_SURFACED", "BETTER_REPRESENTED", "COMPARABLE", "OUTSIDE_NEW_WINDOW"

DEFINITIONS = {
    "phase_subject": "a family member whose slot is a named phase (an opportunity subject)",
    "qualified_phasing_evidence": "the shared AcquisitionPhasingEvidence state of the development (CURRENT_EVIDENCED_PHASE, PHASE_EVIDENCE_CURRENTNESS_UNKNOWN, HISTORICAL_PHASE_ONLY, NONE_IDENTIFIED); distinct from phase-subject existence",
    "unqualified_phase_subject": "a family with a phase subject whose qualified state is NONE_IDENTIFIED (address-only label or no substantive granted anchor; the two are not separated without new extraction)",
    "oversized_wider_family": "a family with a wider (non-self-phase) planning-delivery subject for which phasing_is_acquisition_relevant holds for the buyer (above the mandate's discovery maximum, total-units mandate)",
    "comparable_legacy_window": "build_opportunity_feed in buyer mode called with the same limit N as the family shortlist (the legacy candidate pool is not re-derived)",
    NEWLY_SURFACED: "in the new top-N, and the legacy window of the same size holds NO card for that site/allocation",
    BETTER_REPRESENTED: "the legacy window holds card(s) for the site/allocation, but the new representative is a different, strictly better-fit subject, or several legacy cards collapse into one family",
    COMPARABLE: "the legacy window already presents the same representative, or a different one of equal fit (no improvement is claimed)",
    OUTSIDE_NEW_WINDOW: "the family is not within the new top-N window (reported with its legacy presence)",
    "ordering": "the existing v7 family order (fit bucket, then lexical family key). Ties are NON-COMMERCIAL; this is not a market ranking and no new ranking is introduced",
    "legacy_limits": "only absence from / presence in the legacy WINDOW can be established; whether the legacy candidate pool contained the subject is not re-derived",
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
    better = len(present) > 1 or (rep.subject_key not in present and entry["best_rank"] is not None and fit_rank(rep.fit, rep.investigative) < entry["best_rank"])
    return {"comparison": BETTER_REPRESENTED if better else COMPARABLE, "legacy_cards_for_family": len(present)}


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


def _legacy_window(session, buyer_key: str, window: int):
    from app.reporting.opportunity_feed import build_opportunity_feed
    return build_opportunity_feed(session, limit=window, buyer_key=buyer_key)


def run_validation(session, *, real: bool, code_sha: str | None = None, shortlist_size: int = 20, statement_timeout_ms: int = 60000, max_queries: int | None = None,
                   clock=lambda: datetime.now(timezone.utc), buyers: tuple = (PRIMARY_BUYER, *OTHER_BUYERS)) -> dict:
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
            except UnknownBuyerProfile as error:
                results[buyer] = {"error": str(error)}
            instrument.snapshot(f"evaluate:{buyer}")
        legacy = None
        primary = results.get(PRIMARY_BUYER)
        if primary is not None and "error" not in primary:
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
            if buyer == "housing_association":
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
                      "comparison_counts_in_new_window": {k: counts.get(k, 0) for k in (NEWLY_SURFACED, BETTER_REPRESENTED, COMPARABLE)},
                      "legacy_window": None if legacy is None else {"window": legacy["window"], "cards_returned": legacy["cards_returned"], "malformed_legacy_cards": legacy["malformed_legacy_cards"]}}
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
                       "comparison_counts_in_new_window": (nesten or {}).get("comparison_counts_in_new_window")},
        "buyers": buyer_sections, "nesten": nesten, "negative_cohort": cohort, "efficiency": efficiency, "definitions": DEFINITIONS,
    }
    return artifact


CSV_COLUMNS = ("position", "family_id", "council_code", "title", "representative", "family_fit", "investigative", "qualified_phasing_state", "phasing_badge", "comparison",
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
