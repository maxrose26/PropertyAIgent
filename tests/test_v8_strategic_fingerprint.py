"""Stage 2.5B V8: the strategic opportunity fingerprint distinguishes capacity KIND where it matters, and leaves exact capacities (and every planning fingerprint) unchanged."""
from __future__ import annotations

import dataclasses
from types import SimpleNamespace

from app.policy.buyer_matching import build_strategic_land_matching_facts
from app.reporting.opportunity_universe import compute_opportunity_fingerprint, strategic_capacity_fingerprint_fields


def facts(minimum, indicative, maximum):
    allocation = SimpleNamespace(minimum_dwellings=minimum, indicative_capacity=indicative, maximum_capacity=maximum, intended_use="residential",
                                 local_plan=SimpleNamespace(status="adopted"), plan_status="adopted", matched_site_id=None)
    return build_strategic_land_matching_facts(allocation, None, None)


def fingerprint(f):
    base = {"opportunity_type": f.opportunity_type, "unit_count": f.unit_count, "planning_state": f.planning_state, "site_area_hectares": 10.0}
    base.update(strategic_capacity_fingerprint_fields(f))
    return compute_opportunity_fingerprint(base)


def test_exact_capacity_keeps_its_pre_v8_fingerprint_fields_unchanged():
    assert strategic_capacity_fingerprint_fields(facts(150, None, 150)) == {}                  # no new key: byte-for-byte the previous fingerprint
    assert strategic_capacity_fingerprint_fields(dataclasses.replace(facts(150, None, 150), count_assessment=None)) == {}


def test_exact_150_and_minimum_only_150_no_longer_fingerprint_identically():
    exact, floor, ceiling = facts(150, None, 150), facts(150, None, None), facts(None, None, 150)
    assert exact.unit_count == floor.unit_count == ceiling.unit_count == 150                    # the legacy scalar cannot tell them apart
    assert len({fingerprint(exact), fingerprint(floor), fingerprint(ceiling)}) == 3


def test_range_indicative_and_bound_changes_move_the_fingerprint_and_equal_evidence_does_not():
    assert fingerprint(facts(80, None, 150)) != fingerprint(facts(100, None, 150))              # lower bound changes with the same maximum scalar
    assert fingerprint(facts(None, 160, None)) != fingerprint(facts(None, 170, None))           # indicative-only value (the legacy scalar ignores it)
    assert fingerprint(facts(80, None, 150)) == fingerprint(facts(80, None, 150))
    assert strategic_capacity_fingerprint_fields(facts(300, None, 100))["capacity_semantics"]["precision"] == "UNKNOWN"      # malformed fails closed and is visible
