"""Stage 2.5B Gate A: the deterministic offline v7 benchmark (12 cases) - runner, preservation of v4/v6, negative-inference checks, offline guarantee, approval status."""
from __future__ import annotations

import glob
import hashlib
import socket
from pathlib import Path

import pytest

import benchmark.v7.cases as cases_module
from benchmark.v7 import V7_BENCHMARK_VERSION
from benchmark.v7.cases import CASES
from benchmark.v7.runner import FORBIDDEN_INFERENCES, expectation_table, run_benchmark, run_case

ROOT = Path(__file__).resolve().parents[1]
V4_CASES_SHA256 = "b80f61b3217668ad136e6e383dead4bedf1b68a106534139e2c2f65f53bfa029"      # sha256 of the 14 frozen v4 case files (LF-normalised, sorted by name), unchanged since V7C


def test_all_twelve_cases_match_the_product_owner_expectations():
    report = run_benchmark()
    failures = {c["case_id"]: c["failures"] for c in report["cases"] if c["failures"]}
    assert not failures and report["passed"] and len(report["cases"]) == 12
    ids = [c.case_id for c in CASES]
    assert [i[0] for i in ids if not next(c for c in CASES if c.case_id == i).optional] == list("ABCDEFGHIJ")
    assert sorted(c.case_id[0] for c in CASES if c.optional) == ["K", "M"]


def test_versions_are_recorded_and_expectations_are_not_self_approved():
    report = run_benchmark()
    assert (report["benchmark_version"], report["buyer_matching_policy_version"], report["agent_evaluation_input_fingerprint_version"], report["agent_evaluation_policy_version"]) == (
        V7_BENCHMARK_VERSION, 7, 3, 2)
    assert report["approved_by_product_owner"] is False and cases_module.APPROVED_BY_PRODUCT_OWNER is False
    assert report["offline"] == {"database_calls": 0, "network_calls": 0, "model_calls": 0}


def test_the_v4_fixtures_and_the_v6_checkpoint_are_preserved():
    digest = hashlib.sha256()
    files = sorted(glob.glob(str(ROOT / "benchmark/cases/*.json")))
    assert len(files) == 14
    for path in files:
        digest.update(Path(path).read_text(encoding="utf-8").replace("\r\n", "\n").encode())
    assert digest.hexdigest() == V4_CASES_SHA256
    assert not (ROOT / "benchmark/v7/cases").exists()                                   # the v7 set is code-defined; it never writes into the v4 case directory
    # the v6 checkpoint hash is pinned by tests/test_v7c_frozen_v6_oracle.py::test_the_recorded_v6_checkpoint_file_is_unchanged


def test_the_benchmark_is_offline(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network/database access attempted by the offline benchmark")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    import sqlalchemy.engine as engine
    monkeypatch.setattr(engine.Engine, "connect", refuse)
    assert run_benchmark()["passed"]
    source = (ROOT / "benchmark/v7/runner.py").read_text(encoding="utf-8") + (ROOT / "benchmark/v7/cases.py").read_text(encoding="utf-8")
    for forbidden in ("openai", "anthropic", "requests", "httpx", "SessionLocal", "get_session", "sessionmaker", "evaluate_frozen_input", "acquisition_evaluate"):
        assert forbidden not in source, forbidden


def test_the_negative_inference_checker_actually_catches_each_forbidden_claim():
    samples = {
        "availability": "The phase is available for acquisition.", "willingness_to_sell": "The owner is willing to sell.", "ownership_or_control": "The land is owned by the applicant.",
        "residual_or_remaining": "The residual homes could be acquired.", "another_phase": "Another buyer-sized phase exists.", "non_overlap": "The phases do not overlap.",
        "subdivision_because_large": "A scheme this large can be split.", "affordable_package_from_total": "An affordable package is implied.",
    }
    import re
    assert set(samples) == set(FORBIDDEN_INFERENCES)
    for name, text in samples.items():
        assert re.search(FORBIDDEN_INFERENCES[name], text, re.I), name
    for approved in ("Availability is unverified.", "No trusted affordable-unit count is available to assess against this buyer's target range.",
                     "Establish whether a suitable development parcel/phase could become available within this buyer's target range."):
        assert not any(re.search(p, approved, re.I) for p in FORBIDDEN_INFERENCES.values()), approved


def test_a_disagreement_is_reported_not_reconciled(monkeypatch):
    import dataclasses
    wrong = dataclasses.replace(CASES[0], expect_family_fit="POSSIBLE_FIT")
    assert run_case(wrong)["passed"] is False


def test_the_expectation_table_is_generated_from_expectations_only_and_covers_every_case():
    table = expectation_table()
    for case in CASES:
        assert case.case_id in table
    assert table.count("\n| ") == len(CASES)
    committed = ROOT / "benchmark/v7/EXPECTATIONS.md"
    assert committed.read_text(encoding="utf-8").replace("\r\n", "\n").endswith(table)


def test_the_key_expectations_are_the_product_owner_intent():
    by_id = {c.case_id[0]: c for c in CASES}
    assert by_id["I"].expect_label is None and by_id["J"].expect_label is None          # the original Product Owner expectations, retained unchanged
    assert by_id["A"].expect_label == "Phased delivery evidenced." and by_id["A"].expect_representative.endswith("phase:101:1")
    assert by_id["E"].subjects[1].expect_fit == "NOT_SUITABLE" and by_id["E"].expect_family_fit == "INSUFFICIENT_EVIDENCE" and by_id["E"].expect_family_investigative is True
    assert by_id["H"].expect_label is None and by_id["H"].subjects[0].expect_fit == "STRONG_FIT"
    assert by_id["M"].expect_label is None
