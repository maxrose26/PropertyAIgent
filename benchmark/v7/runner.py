"""Deterministic OFFLINE runner for the v7 benchmark: real matcher -> real family grouping -> real family presentation label, compared with benchmark/v7/cases.py.

No database, no network, no model call (nothing here constructs a session, a client or a prompt that is sent anywhere). The runner never edits an expectation: any disagreement is a FAILURE to be
reported, not reconciled.
"""
from __future__ import annotations

import json
import re

from app.policy.agent_evaluation_persistence import AGENT_EVALUATION_INPUT_FINGERPRINT_VERSION
from app.policy.agent_evaluation_result import AGENT_EVALUATION_POLICY_VERSION
from app.policy.buyer_matching import BUYER_MATCHING_POLICY_VERSION, AcquisitionPhasingEvidence, B2MatchingContext, MatchingFacts, assess_buyer_fit, phasing_is_acquisition_relevant
from app.policy.buyer_profiles import BUYER_PROFILES
from app.reporting.family_presentation import phasing_context
from app.reporting.opportunity_families import group_into_families, subject_from_opportunity_id
from benchmark.v7 import V7_BENCHMARK_VERSION
from benchmark.v7.cases import APPROVED_BY_PRODUCT_OWNER, CASES

# Forbidden inferences: nothing a subject (or the family label) says may claim any of these. (The approved phrase "Availability is unverified." is a DISCLAIMER and is not matched.)
FORBIDDEN_INFERENCES = {
    "availability": r"\b(site|land|phase|scheme|parcel|opportunity|development|homes) (is|are|will be|may be|could be|now) available\b|available (for|to) (sale|acquisition|purchase|buy)|for sale\b|on the market",
    "willingness_to_sell": r"willing|keen to sell|looking to sell|seeking (a )?(buyer|purchaser)|motivated seller",
    "ownership_or_control": r"\b(owns|owned by|is owned|under (the )?control of|controlled by)\b",
    "residual_or_remaining": r"residual|remaining (parcel|land|phase|homes|units|capacity)|unbuilt|balance of the",
    "another_phase": r"another (buyer-sized |conventional |suitable )?phase|other (buyer-sized )?phases (exist|are|will)|further phases (exist|are|will)",
    "non_overlap": r"non-overlap|do(es)? not overlap|without overlap|no overlap",
    "subdivision_because_large": r"subdivi|can be split|could be split|likely to be (phased|split)|probably (phased|split|contain)",
    "affordable_package_from_total": r"affordable package|package of affordable",
}


def _context(subject) -> B2MatchingContext:
    return B2MatchingContext(acquisition_phasing=AcquisitionPhasingEvidence(subject.phasing) if subject.phasing else None, subject_phase_scope_key=subject.phase_scope_key)


def _reasons(assessment) -> list:
    return [*assessment.matches, *assessment.unknown, *assessment.investigate, *assessment.does_not_match]


def run_case(case) -> dict:
    policy = BUYER_PROFILES[case.buyer]
    failures, family_subjects, rows = [], [], []
    for subject in case.subjects:
        assessment = assess_buyer_fit(policy, MatchingFacts(**subject.facts), context=_context(subject))
        text = " ".join(_reasons(assessment))
        row = {"subject": subject.opportunity_id, "classification": assessment.classification, "investigative": bool(assessment.is_investigative_exception),
               "reasons": _reasons(assessment)}
        rows.append(row)
        if assessment.classification != subject.expect_fit:
            failures.append(f"{subject.opportunity_id}: classification {assessment.classification} != expected {subject.expect_fit}")
        if bool(assessment.is_investigative_exception) != subject.expect_investigative:
            failures.append(f"{subject.opportunity_id}: investigative {bool(assessment.is_investigative_exception)} != expected {subject.expect_investigative}")
        failures += [f"{subject.opportunity_id}: missing required wording {p!r}" for p in subject.must_say if p not in text]
        failures += [f"{subject.opportunity_id}: forbidden wording {p!r} present" for p in subject.must_not_say if p.lower() in text.lower()]
        failures += [f"{subject.opportunity_id}: forbidden inference [{name}] in {m.group(0)!r}" for name, pattern in FORBIDDEN_INFERENCES.items()
                     for m in [re.search(pattern, text, re.I)] if m]
        evidence = AcquisitionPhasingEvidence(subject.phasing) if subject.phasing else None
        relevant = phasing_is_acquisition_relevant(policy, MatchingFacts(**subject.facts), _context(subject))
        family_subjects.append(subject_from_opportunity_id(subject.opportunity_id, fit=assessment.classification, investigative=bool(assessment.is_investigative_exception),
                                                           source={"acquisition_phasing": evidence, "acquisition_phasing_relevant": relevant}))
    families = group_into_families(family_subjects)
    if len(families) != 1:
        failures.append(f"expected exactly one family, got {len(families)}")
    family = families[0]
    label = phasing_context(family)
    representative = family.representative
    if representative.subject_key != case.expect_representative:
        failures.append(f"representative {representative.subject_key} != expected {case.expect_representative}")
    if representative.fit != case.expect_family_fit:
        failures.append(f"family fit {representative.fit} != expected {case.expect_family_fit}")
    if representative.investigative != case.expect_family_investigative:
        failures.append(f"family investigative {representative.investigative} != expected {case.expect_family_investigative}")
    if label != case.expect_label:
        failures.append(f"family phasing label {label!r} != expected {case.expect_label!r}")
    if label:
        failures += [f"family label: forbidden inference [{name}]" for name, pattern in FORBIDDEN_INFERENCES.items() if re.search(pattern, label, re.I)]
    return {"case_id": case.case_id, "buyer": case.buyer, "subjects": rows, "family_representative": representative.subject_key, "family_fit": representative.fit,
            "family_investigative": representative.investigative, "phasing_label": label, "failures": failures, "passed": not failures}


def run_benchmark() -> dict:
    results = [run_case(case) for case in CASES]
    return {
        "benchmark_version": V7_BENCHMARK_VERSION,
        "buyer_matching_policy_version": BUYER_MATCHING_POLICY_VERSION,
        "agent_evaluation_input_fingerprint_version": AGENT_EVALUATION_INPUT_FINGERPRINT_VERSION,
        "agent_evaluation_policy_version": AGENT_EVALUATION_POLICY_VERSION,
        "approved_by_product_owner": APPROVED_BY_PRODUCT_OWNER,
        "offline": {"database_calls": 0, "network_calls": 0, "model_calls": 0},
        "cases": results,
        "passed": all(r["passed"] for r in results),
    }


def expectation_table() -> str:
    """The reviewable Product Owner expectation table, generated from the EXPECTATIONS only (never from an implementation result)."""
    lines = ["| Case | Buyer | Key facts | Subject expectations | Family representative | Family fit | Investigative | Phasing label | Why an acquisition professional should get this |",
             "|---|---|---|---|---|---|---|---|---|"]
    for case in CASES:
        subjects = "<br>".join(f"`{s.opportunity_id}` -> {s.expect_fit}{' + investigative' if s.expect_investigative else ''}" for s in case.subjects)
        lines.append(f"| {case.case_id}{' (optional)' if case.optional else ''} | {case.buyer} | {case.key_facts} | {subjects} | `{case.expect_representative}` | {case.expect_family_fit} | "
                     f"{'yes' if case.expect_family_investigative else 'no'} | {case.expect_label or 'none'} | {case.why} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(json.dumps(run_benchmark(), indent=2, sort_keys=True))
