"""Stage 2.5B V7A pre-implementation checkpoint: the immediate pre-v7 (current v6) result for the 14 frozen benchmark cases.

Pure/offline. The checkpoint harness never touches a database, the network or a model, and never rewrites the frozen fixtures; the recorded checkpoint file must be
exactly what the harness regenerates (so it cannot drift silently). v4 -> v6 changes recorded here are NOT attributable to the v7 phasing delta.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import benchmark.v6_checkpoint as ckpt

ROOT = Path(__file__).resolve().parents[1]


def rows():
    return {r["case_id"]: r for r in ckpt.build_checkpoint()}


def test_current_matching_keeps_every_recorded_v6_classification_flag_and_scale_outcome():
    """The checkpoint was recorded under v6 (commit before the V7A policy change). The harness now runs CURRENT (v7) matching; V7A changes only reason WORDING, so
    classification, the investigative flag and the scale outcome of all 14 cases must equal the recorded v6 values (the Product Owner's 'flags equal accepted v6' pin)."""
    recorded = {r["case_id"]: r for r in json.loads((ROOT / "benchmark/checkpoints/v6_checkpoint.json").read_text(encoding="utf-8"))}
    current = rows()
    assert set(recorded) == set(current)
    for case_id, row in recorded.items():
        for field in ("v6_classification", "v6_investigative", "scale_outcome_v6", "buyer", "frozen_classification", "frozen_investigative",
                      "v7_phasing_delta_relevant", "v7_below_minimum_wording_relevant", "reconstruction"):
            assert current[case_id][field] == row[field], (case_id, field)


def test_all_fourteen_cases_are_covered_and_every_frozen_snapshot_is_v4():
    result = rows()
    assert len(result) == 14 and {r["frozen_policy_version"] for r in result.values()} == {4}


def test_reconstruction_is_complete_except_the_one_uncaptured_terminal_exclusion():
    incomplete = [k for k, r in rows().items() if r["reconstruction"] != "complete"]
    assert incomplete == ["pd_hard_deterministic_exclusion"]
    assert rows()["pd_hard_deterministic_exclusion"]["v6_basis"] == "inferred_from_frozen_terminal_exclusion"


def test_known_v6_results_for_the_phasing_and_strategic_relevant_cases():
    r = rows()
    for case in ("pd_wider_site_context_different_mandate", "xc_developer_identity_no_control"):   # oversized planning-delivery, no phasing evidence captured
        assert (r[case]["v6_classification"], r[case]["v6_investigative"], r[case]["scale_outcome_v6"]) == ("INSUFFICIENT_EVIDENCE", True, "above_discovery_max")
        assert r[case]["v7_phasing_delta_relevant"] and r[case]["changed_v4_to_v6"]
    strategic_route = r["sl_very_large_allocation_parcel_level"]
    assert strategic_route["scale_outcome_v6"] == "above_max_strategic_self_qualifying_route" and not strategic_route["v7_phasing_delta_relevant"]
    nhb_alloc = r["sl_matched_pair_national_housebuilder"]                                        # a strategic oversize case: already changed by v6, outside the v7 delta
    assert nhb_alloc["v6_classification"] == "INSUFFICIENT_EVIDENCE" and nhb_alloc["changed_v4_to_v6"] and not nhb_alloc["v7_phasing_delta_relevant"]


def test_below_minimum_cases_are_flagged_for_the_separate_wording_correction():
    r = rows()
    assert r["pd_recent_permission_seed"]["scale_outcome_v6"] == "below_discovery_min" and r["pd_recent_permission_seed"]["v7_below_minimum_wording_relevant"]
    assert r["pd_hard_deterministic_exclusion"]["v7_below_minimum_wording_relevant"]
    assert not any(row["v7_phasing_delta_relevant"] for row in r.values() if row["v7_below_minimum_wording_relevant"])


def test_the_harness_is_offline_and_model_free():
    source = inspect.getsource(ckpt)
    assert not any(token in source for token in ("openai", "requests", "httpx", "sqlalchemy", "get_db", "session"))
