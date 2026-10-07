"""Stage 2.5B V7C: provenance, independence, isolation and checkpoint cross-check of the TEMPORARY frozen v6 matcher oracle (verification/transition).

The oracle is the verbatim accepted v6 assess_buyer_fit; these tests make its provenance auditable, prove it cannot silently delegate to logic that changed between v6 and v7,
prove it is isolated from application runtime, and show it reproduces the recorded v6 classification/flag of every 14-case checkpoint entry whose reconstruction is complete.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

import app.policy.buyer_matching as bm
import verification.transition.frozen_v6_matcher as frozen
from app.policy.buyer_profiles import BUYER_PROFILES
from benchmark.v6_checkpoint import _reconstruct

ROOT = Path(__file__).resolve().parents[1]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def lf(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def definition_texts(source: str) -> dict:
    tree = ast.parse(source)
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            out[node.name] = ast.get_source_segment(source, node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = ast.get_source_segment(source, node)
    return out


# --- provenance ----------------------------------------------------------------------------------------------------------------------

def test_provenance_is_recorded_and_the_function_text_matches_its_immutable_hash():
    provenance = frozen.PROVENANCE
    assert provenance["source_commit"] == "3cce0815fd6d243993edf5ca511094ae3a795285"            # master immediately before the first V7A commit
    assert provenance["source_file"] == "app/policy/buyer_matching.py" and provenance["source_function"] == "assess_buyer_fit"
    assert provenance["source_blob"] == "2bb36a12d1b828d2b2bee3d9d58621cdb7057d50" and provenance["policy_version_at_source"] == 6
    source = lf(Path(frozen.__file__))
    function = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "assess_buyer_fit")
    text = ast.get_source_segment(source, function)
    assert sha256(text) == frozen.FUNCTION_SHA256 == provenance["function_sha256"]               # byte-for-byte the v6 function (any edit changes the hash)
    assert provenance["source_lines"] == (821, 1394) and len(text.splitlines()) == 574
    assert function.decorator_list == []


def test_the_module_states_its_transition_only_immutable_and_removal_contract():
    doc = frozen.__doc__
    for phrase in ("TRANSITION-ONLY, IMMUTABLE", "NOT application policy", "DO NOT MODIFY", "REMOVED in a dedicated cleanup", "rollback window",
                   "the application never imports"):
        assert phrase in doc, phrase


# --- independence: nothing the v6 body relies on has changed -------------------------------------------------------------------------------

def test_every_definition_the_v6_function_references_is_byte_identical_in_the_current_module():
    current = definition_texts(lf(ROOT / "app/policy/buyer_matching.py"))
    for name, pinned in frozen.DEPENDENCY_PINS.items():
        assert sha256(current[name]) == pinned, f"{name} changed since v6 - the oracle can no longer delegate to it; re-freeze it into the oracle"
    # B2MatchingContext is the ONLY referenced definition that changed in V7A (new OPTIONAL fields): the v6 body must read only the four v6 fields from it.
    tree = ast.parse(lf(Path(frozen.__file__)))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "assess_buyer_fit")
    read = {n.attr for n in ast.walk(function) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "context"}
    assert read <= {"council_code", "development_state", "control_facts", "development_state_scope_verified"}, read
    for new_field in ("acquisition_phasing", "subject_phase_scope_key", "subject_application_anchored"):
        assert new_field not in read


def test_the_supporting_modules_behind_the_imported_names_are_unchanged_since_v6():
    for path, pinned in frozen.SUPPORTING_MODULE_SHA256.items():
        assert sha256(lf(ROOT / path)) == pinned, path


def test_the_oracle_does_not_call_the_v7_matcher_or_its_changed_helpers():
    tree = ast.parse(lf(Path(frozen.__file__)))
    imported = {a.name for n in tree.body if isinstance(n, ast.ImportFrom) for a in n.names}
    assert "assess_buyer_fit" not in imported and "subject_is_self_scope" not in imported and "_phasing_tail" not in imported
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not called & {"subject_is_self_scope", "_phasing_tail", "_outside_reason", "derive_acquisition_phasing_evidence"}
    assert frozen.assess_buyer_fit is not bm.assess_buyer_fit


# --- isolation ---------------------------------------------------------------------------------------------------------------------------

def test_only_the_transition_script_and_tests_import_the_oracle_and_the_application_never_does():
    offenders = []
    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith(("tests/", "verification/transition/", ".venv", "node_modules")) or "/.venv/" in relative:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "verification.transition" in text or "frozen_v6_matcher" in text:
            offenders.append(relative)
    assert offenders == ["scripts/reonboard_stale_mandates.py"], offenders
    for path in (ROOT / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not any(m.startswith("verification") for m in imported), path
    parity = ast.parse(lf(ROOT / "verification/transition/v6_parity.py"))
    compared = {n.attr for n in ast.walk(parity) if isinstance(n, ast.Attribute)}
    assert {"classification", "is_investigative_exception"} <= compared and not compared & {"matches", "unknown", "investigate", "does_not_match"}   # reason text is never compared


# --- checkpoint cross-check ----------------------------------------------------------------------------------------------------------------

def test_the_frozen_oracle_reproduces_the_recorded_v6_checkpoint_for_every_completely_reconstructed_case():
    recorded = {r["case_id"]: r for r in json.loads((ROOT / "benchmark/checkpoints/v6_checkpoint.json").read_text(encoding="utf-8"))}
    assert len(recorded) == 14
    checked = []
    for path in sorted((ROOT / "benchmark/cases").glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        row = recorded[case["case_id"]]
        facts, context = _reconstruct(case)
        policy = BUYER_PROFILES[row["buyer"]]
        v6 = frozen.assess_buyer_fit(policy, facts, context=context)
        if row["reconstruction"] == "complete":
            assert (v6.classification, bool(v6.is_investigative_exception)) == (row["v6_classification"], row["v6_investigative"]), case["case_id"]
            checked.append(case["case_id"])
        else:
            # The one INCOMPLETE case (pd_hard_deterministic_exclusion): the frozen Layer A/B never recorded the terminal specialist-development exclusion, so the reconstructed facts
            # cannot reproduce NOT_SUITABLE. The checkpoint carries it as an INFERRED result; the oracle must NOT pretend the missing fact exists.
            assert case["case_id"] == "pd_hard_deterministic_exclusion" and row["v6_basis"] == "inferred_from_frozen_terminal_exclusion"
            assert v6.classification != "NOT_SUITABLE"
    assert len(checked) == 13


def test_the_recorded_v6_checkpoint_file_is_unchanged():
    assert sha256(lf(ROOT / "benchmark/checkpoints/v6_checkpoint.json")) == CHECKPOINT_SHA256


CHECKPOINT_SHA256 = "01f797d1c9991896e9ab5740192f0c878654f4cb27f3863735a368a372dd354e"   # sha256 (LF-normalised) of the checkpoint exactly as recorded in commit 2604590 under v6
