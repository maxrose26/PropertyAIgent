"""Stage 2.5B V8-A: provenance, independence, isolation of the TEMPORARY frozen v7 matcher oracle, and the v7/v8 differential gate (expected strategic deltas vs unexpected regressions)."""
from __future__ import annotations

import ast
import dataclasses
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.policy.buyer_matching as bm
import verification.transition.frozen_v7_matcher as frozen
from app.policy.buyer_profiles import BUYER_PROFILES
from verification.transition.v7_parity import EQUAL, EXPECTED_STRATEGIC_DELTA, UNEXPECTED_REGRESSION, differential_category, v7_oracle_facts

ROOT = Path(__file__).resolve().parents[1]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def lf(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def definition_texts(source: str) -> dict:
    out = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            out[node.name] = ast.get_source_segment(source, node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = ast.get_source_segment(source, node)
    return out


def test_provenance_and_function_hash():
    p = frozen.PROVENANCE
    assert p["source_commit"] == "60dcbd99649d4d1e8506590257416ef7741e5939" and p["policy_version_at_source"] == 7
    source = lf(Path(frozen.__file__))
    function = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "assess_buyer_fit")
    assert sha256(ast.get_source_segment(source, function)) == frozen.FUNCTION_SHA256 == p["function_sha256"]
    assert "DO NOT MODIFY" in frozen.__doc__ and "the application never imports" in frozen.__doc__


def test_pinned_definitions_unchanged_and_function_reads_only_existing_facts_fields():
    current = definition_texts(lf(ROOT / "app/policy/buyer_matching.py"))
    for name, pinned in frozen.DEPENDENCY_PINS.items():
        assert sha256(current[name]) == pinned, name
    tree = ast.parse(lf(Path(frozen.__file__)))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "assess_buyer_fit")
    facts_read = {n.attr for n in ast.walk(function) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "facts"}
    assert facts_read <= {f.name for f in dataclasses.fields(bm.MatchingFacts)}
    for path, pinned in frozen.SUPPORTING_MODULE_SHA256.items():
        assert sha256(lf(ROOT / path)) == pinned, path
    assert frozen.assess_buyer_fit is not bm.assess_buyer_fit


def _alloc(minimum, indicative, maximum):
    return SimpleNamespace(minimum_dwellings=minimum, indicative_capacity=indicative, maximum_capacity=maximum, intended_use="residential",
                           local_plan=SimpleNamespace(status="adopted"), plan_status="adopted", matched_site_id=None)


def _strategic_facts(minimum, indicative, maximum):
    return dataclasses.replace(bm.build_strategic_land_matching_facts(_alloc(minimum, indicative, maximum), None, None), has_identified_planning_activity=False)


def _category(buyer, figures):
    policy, facts = BUYER_PROFILES[buyer], _strategic_facts(*figures)
    return differential_category(policy, facts, None, bm.assess_buyer_fit(policy, facts))[0]


def test_oracle_adapter_strips_strategic_count_semantics_only():
    facts = _strategic_facts(150, None, 210)
    assert facts.count_assessment is not None and v7_oracle_facts(facts).count_assessment is None
    planning = dataclasses.replace(facts, opportunity_type=bm.PLANNING_DELIVERY)
    assert v7_oracle_facts(planning) is planning


@pytest.mark.parametrize("buyer,figures,expected", [
    ("nesten_homes", (150, None, 150), EQUAL),
    ("nesten_homes", (2000, None, 2000), EQUAL),
    ("nesten_homes", (150, None, None), EXPECTED_STRATEGIC_DELTA),
    ("nesten_homes", (None, None, 150), EXPECTED_STRATEGIC_DELTA),
    ("strategic_land_buyer", (2000, None, 2000), EQUAL),
    ("strategic_land_buyer", (1500, None, 2500), EQUAL),      # preserved large-allocation route: no delta
    ("strategic_land_buyer", (2000, None, None), EQUAL),      # preserved: lower bound above discovery max
])
def test_differential_categories_for_strategic_cases(buyer, figures, expected):
    assert _category(buyer, figures) == expected


def test_planning_delivery_difference_is_always_unexpected():
    policy = BUYER_PROFILES["nesten_homes"]
    facts = dataclasses.replace(_strategic_facts(150, None, 150), opportunity_type=bm.PLANNING_DELIVERY, count_assessment=None)
    v8 = bm.assess_buyer_fit(policy, facts)
    forged = dataclasses.replace(v8, classification=bm.NOT_SUITABLE if v8.classification != bm.NOT_SUITABLE else bm.STRONG_FIT)
    assert differential_category(policy, facts, None, forged)[0] == UNEXPECTED_REGRESSION


def test_exact_strategic_difference_is_unexpected_and_preserved_route_difference_is_unexpected():
    policy = BUYER_PROFILES["nesten_homes"]
    facts = _strategic_facts(150, None, 150)
    v8 = bm.assess_buyer_fit(policy, facts)
    forged = dataclasses.replace(v8, classification=bm.NOT_SUITABLE if v8.classification != bm.NOT_SUITABLE else bm.STRONG_FIT)
    assert differential_category(policy, facts, None, forged)[0] == UNEXPECTED_REGRESSION
    slb = BUYER_PROFILES["strategic_land_buyer"]
    facts = _strategic_facts(1500, None, 2500)
    v8 = bm.assess_buyer_fit(slb, facts)
    forged = dataclasses.replace(v8, classification=bm.INSUFFICIENT_EVIDENCE)
    assert differential_category(slb, facts, None, forged)[0] == UNEXPECTED_REGRESSION
