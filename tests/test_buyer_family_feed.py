"""Stage 2.5B G3b Slice 1 (spec 025): the complete buyer-FAMILY feed data model.

Buyer fit is driven by a deterministic FAKE evaluator keyed by subject scope (parent/lifecycle, phase, strategic capacity), so every scenario
states the fit it needs and the tests exercise exactly the completeness/grouping/limit/precedence behaviour under review. Real Application,
Site, LocalPlanSite rows and the real detectors/reshaping/matching-facts steps are used. The ORACLE is an independent, brute-force, unbounded
re-derivation (own enumeration from the raw detectors, own exclusion chain, own grouping/order); it never calls the production family builder.
"""
from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import inspect
import random
import socket
import sys
import time

import pytest

import app.policy.buyer_matching_b2_context as b2
import app.reporting.buyer_family_feed as bff
import app.reporting.opportunity_families as fam
from app.db.models import Application, AllocationSiteRelationship, LocalPlan, LocalPlanSite, Site
from app.policy.buyer_matching import INSUFFICIENT_EVIDENCE, NOT_SUITABLE, POSSIBLE_FIT, STRONG_FIT, BuyerFitAssessment
from app.reporting.opportunity_feed import (
    PLANNING_DELIVERY, STRATEGIC_LAND, _attach_planning_delivery_matching_facts, _planning_delivery_cards,
    _reshape_signal_card, _strategic_land_cards, build_opportunity_feed,
)

BUYER = "housing_association"
CODES = {"S": (STRONG_FIT, False), "P": (POSSIBLE_FIT, False), "X": (INSUFFICIENT_EVIDENCE, True),
         "I": (INSUFFICIENT_EVIDENCE, False), "N": (NOT_SUITABLE, False)}
RANK = {"S": 0, "P": 1, "X": 2, "I": 3, "N": 4}
ROLE_OF = {"S": fam.ROLE_ALSO_STRONG_FIT, "P": fam.ROLE_ALSO_POSSIBLE_FIT, "X": fam.ROLE_INSUFFICIENT_INVESTIGATIVE,
           "I": fam.ROLE_INSUFFICIENT, "N": fam.ROLE_NOT_SUITABLE}
TODAY = dt.date.today()


def portal(days_ago: int) -> str:
    return (TODAY - dt.timedelta(days=days_ago)).strftime("%a %d %b %Y")


LAPSE_AGE = 365 * 3 - 60   # grant age that puts a site in "approaching lapse"


class World:
    """Fixture builder + the deterministic fit table (patched in place of evaluate_buyer_fit for BOTH the legacy and the family path)."""

    def __init__(self, session, monkeypatch):
        self.session = session
        self.parent, self.phase, self.alloc = {}, {}, {}
        self.n = 0
        monkeypatch.setattr(b2, "evaluate_buyer_fit", self.evaluate)

    # -- fits -----------------------------------------------------------------------------------------------------------------------
    def code_of(self, facts) -> str:
        if facts.opportunity_type == STRATEGIC_LAND:
            return self.alloc[facts.unit_count]
        assessment = facts.count_assessment
        assert assessment is not None, "planning facts without a count assessment"
        site_id = int(assessment.subject_id.split(":")[1])
        return (self.phase if assessment.scope_type == "phase" else self.parent).get(site_id, "I")

    def evaluate(self, session, profile, facts, *, context=None, **kw):
        classification, investigative = CODES[self.code_of(facts)]
        return BuyerFitAssessment(classification=classification, is_investigative_exception=investigative)

    # -- rows -----------------------------------------------------------------------------------------------------------------------
    def site(self, *, outline_age=None, rm_age=None, rm_phase="Phase 2", pending_age=None, parent="I", phase="I", units_out=40, units_rm=30):
        self.n += 1
        i = self.n
        s = Site(council_code="testcouncil", canonical_address=f"site-{i}", display_address=f"Site {i}")
        self.session.add(s)
        self.session.flush()
        if outline_age is not None:
            self.session.add(Application(council_code="testcouncil", reference=f"OUT/{i}", site_id=s.id, decision="Granted",
                                         decision_issued_date=portal(outline_age), application_received=portal(outline_age + 120),
                                         proposal=f"Outline erection of {units_out} dwellings", estimated_unit_count=units_out))
        if rm_age is not None:
            self.session.add(Application(council_code="testcouncil", reference=f"RM/{i}", site_id=s.id, decision="Granted",
                                         decision_issued_date=portal(rm_age), application_received=portal(rm_age + 90),
                                         proposal=f"Reserved matters for {rm_phase} of {units_rm} dwellings pursuant to outline permission OUT/{i}",
                                         estimated_unit_count=units_rm))
        if pending_age is not None:
            self.session.add(Application(council_code="testcouncil", reference=f"PEN/{i}", site_id=s.id, decision=None, status="Pending consideration",
                                         application_received=portal(pending_age), proposal="Erection of 25 dwellings", estimated_unit_count=25))
        self.session.commit()
        self.parent[s.id], self.phase[s.id] = parent, phase
        return s

    def allocation(self, *, capacity, fit="I", name=None, **kw):
        plan = self.session.query(LocalPlan).first()
        if plan is None:
            plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status="proposed_submission", raw_status="proposed_submission")
            self.session.add(plan)
            self.session.commit()
        a = LocalPlanSite(council_code="testcouncil", local_plan_id=plan.id, policy_reference=f"AN{capacity}", site_name=name or f"Allocation {capacity}",
                          plan_name="Test Local Plan", plan_status="proposed_submission", matched_site_id=kw.pop("matched_site_id", None),
                          minimum_dwellings=kw.pop("minimum_dwellings", capacity), maximum_capacity=capacity, site_area_hectares=10.0, **kw)
        self.session.add(a)
        self.session.commit()
        self.alloc[capacity] = fit
        return a


@pytest.fixture
def world(session, monkeypatch):
    return World(session, monkeypatch)


# --- the independent unbounded ORACLE --------------------------------------------------------------------------------------------------

def oracle(world, limit):
    """Brute force, no pool, no paging, no memoisation, no production family builder. Enumerates every subject from the raw detectors with its own
    precedence chain, evaluates fit via the same fit table, groups with its own dictionary algorithm and orders by (fit rank, family key)."""
    from app.reporting.dashboard import (
        _approaching_lapse_cards, _long_pending_application_cards, _recent_permission_cards, _undeveloped_phase_cards,
    )
    session = world.session
    lapse = _approaching_lapse_cards(session, None)
    phase = _undeveloped_phase_cards(session, None)
    covered = {int(c["params"]["site_id"]) for c in (*lapse, *phase)}
    recent = _recent_permission_cards(session, None, exclude_site_ids=frozenset(covered))
    covered |= {int(c["params"]["site_id"]) for c in recent}
    pending = _long_pending_application_cards(session, None, exclude_site_ids=frozenset(covered))
    delivery = [_reshape_signal_card(c, opportunity_type=PLANNING_DELIVERY, extra_tags=[]) for c in (*lapse, *phase, *recent, *pending)]
    _attach_planning_delivery_matching_facts(session, delivery)
    strategic = _strategic_land_cards(session, 10 ** 6)   # the legacy shaping with an effectively infinite SQL window
    subjects = []   # (family_key, id, code, evidence_rank)
    for card in (*strategic, *delivery):
        facts = card.get("matching_facts")
        if facts is None:
            continue
        precision = getattr(card.get("count_assessment"), "precision", None)
        evidence = 0 if precision == "EXACT" else 1 if precision in ("APPROXIMATE", "RANGE") else 2
        if card["opportunity_type"] == STRATEGIC_LAND:
            key = ("strategic_land", int(card["params"]["allocation_id"]))
        else:
            key = ("planning_delivery", int(card["params"]["site_id"]))
        subjects.append((key, card["id"], world.code_of(facts), evidence))
    families = {}
    for key, cid, code, evidence in subjects:
        families.setdefault(key, []).append((RANK[code], evidence, cid, code))
    result = []
    for key, members in families.items():
        members.sort()
        rep = members[0]
        result.append({"key": key, "rep": rep[2], "code": rep[3],
                       "related": tuple(sorted((m[2], ROLE_OF[m[3]]) for m in members[1:])), "excluded": rep[3] == "N"})
    result.sort(key=lambda f: (RANK[f["code"]], f["key"]))
    shown = [f for f in result if not f["excluded"]][:limit]
    return {"shown": shown, "excluded": sorted(f["key"] for f in result if f["excluded"]),
            "families_considered": len(result), "subjects_considered": len(subjects)}


def summarise(result):
    code_of = {(fit, inv): code for code, (fit, inv) in CODES.items()}
    shown = []
    for f in result["families"]:
        shown.append({"key": f.family_key, "rep": f.representative.subject_key,
                      "code": code_of[(f.representative.fit, f.representative.investigative)],
                      "related": tuple(sorted((r.subject.subject_key, r.role) for r in f.related)),
                      "excluded": f.is_terminally_excluded})
    return {"shown": shown, "excluded": sorted(result["excluded_family_keys"]),
            "families_considered": result["counts"]["families_considered"], "subjects_considered": result["counts"]["subjects_considered"]}


def build(world, limit=6, **kw):
    return bff.build_buyer_opportunity_families(world.session, BUYER, limit, **kw)


def assert_equals_oracle(world, limit=6):
    assert summarise(build(world, limit)) == oracle(world, limit)


def family_of(result, site):
    return next(f for f in result["families"] if f.family_key == ("planning_delivery", site.id))


# --- A-D. the core correctness cases -------------------------------------------------------------------------------------------------

def test_a_parent_insufficient_with_a_strong_phase_is_one_strong_family_headed_by_the_phase(world):
    s = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="I", phase="S")
    result = build(world)
    family = family_of(result, s)
    assert len(result["families"]) == 1 and family.fit == STRONG_FIT
    assert family.representative.slot == fam.SLOT_PHASE and family.representative.source["phase_code"] != "Whole site / unphased"
    assert {r.subject.subject_key for r in family.related} >= {f"opp-lapse-{s.id}"}
    assert family.overlap_state == fam.OVERLAP_MAY_OVERLAP
    assert_equals_oracle(world)


def test_b_parent_not_suitable_with_a_possible_phase_is_one_possible_family(world):
    s = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="N", phase="P")
    result = build(world)
    family = family_of(result, s)
    assert family.fit == POSSIBLE_FIT and not family.is_terminally_excluded
    assert {r.role for r in family.related} >= {fam.ROLE_NOT_SUITABLE}
    assert result["counts"]["families_excluded_not_suitable"] == 0
    assert_equals_oracle(world)


def test_c_parent_strong_and_phase_strong_is_one_family_one_representative_both_retained(world):
    s = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="S", phase="S")
    result = build(world)
    family = family_of(result, s)
    assert len(result["families"]) == 1 and family.fit == STRONG_FIT
    assert {m.subject_key for m in family.members} >= {f"opp-lapse-{s.id}", family.representative.subject_key}
    assert any(r.role == fam.ROLE_ALSO_STRONG_FIT for r in family.related)
    assert_equals_oracle(world)


def test_d_phase_only_family_is_complete_and_has_no_invented_whole_site_subject(world):
    s = world.site(rm_age=400, rm_phase="Phase 1", phase="S")
    result = build(world)
    family = family_of(result, s)
    assert family.fit == STRONG_FIT
    assert all(m.slot == fam.SLOT_PHASE for m in family.members) and not any(m.subject_key == f"opp-lapse-{s.id}" for m in family.members)
    assert_equals_oracle(world)


# --- G-H. terminal exclusion + counts -----------------------------------------------------------------------------------------------

def test_g_h_a_family_is_excluded_only_if_every_subject_is_not_suitable(world):
    allx = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="N", phase="N")
    mixed = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="N", phase="I")
    result = build(world)
    assert [f.family_key for f in result["families"]] == [("planning_delivery", mixed.id)]
    assert result["excluded_family_keys"] == (("planning_delivery", allx.id),)
    counts = result["counts"]
    assert counts["families_considered"] == 2 and counts["families_shown"] == 1 and counts["families_excluded_not_suitable"] == 1
    assert counts["subjects_considered"] == 6 and "subjects_without_matching_facts" not in counts
    assert_equals_oracle(world)


# --- I. strategic ------------------------------------------------------------------------------------------------------------------

def test_i_an_allocation_linked_to_several_sites_is_exactly_one_strategic_family(world):
    s1, s2, s3 = (world.site() for _ in range(3))   # sites without applications: the allocation stays feed-eligible
    a = world.allocation(capacity=8400, fit="S")
    for s in (s1, s2, s3):
        world.session.add(AllocationSiteRelationship(allocation_id=a.id, site_id=s.id, evidence_basis="document_confirmed_site"))
    world.session.commit()
    result = build(world)
    strategic = [f for f in result["families"] if f.family_key[0] == "strategic_land"]
    assert [f.family_key for f in strategic] == [("strategic_land", a.id)] and len(strategic[0].members) == 1
    assert result["counts"]["strategic_land"] == 1
    assert_equals_oracle(world)


def test_strategic_read_is_complete_beyond_the_legacy_sql_window_and_preserves_eligibility(world):
    allocations = [world.allocation(capacity=1000 + i, fit="I", name=f"Alloc {i}") for i in range(14)]
    smallest = min(allocations, key=lambda a: a.maximum_capacity)
    world.allocation(capacity=500, fit="I", name="Matched elsewhere", matched_site_id=world.site(outline_age=900).id)   # not a candidate
    world.allocation(capacity=300, fit="I", name="No minimum", minimum_dwellings=None)                              # not a candidate
    legacy_window = {c["id"] for c in _strategic_land_cards(world.session, 4)}               # SQL window max(3*4, 12) = 12 of 14
    assert f"opp-feed-alloc-{smallest.id}" not in legacy_window
    expected = {c["id"] for c in _strategic_land_cards(world.session, 10 ** 6)}
    assert len(expected) == 14
    for page_size in (1, 3, 500):                                                             # paging never changes the population
        assert {c["id"] for c in bff._complete_strategic_cards(world.session, page_size=page_size)} == expected
    assert len({c["id"] for c in bff._complete_strategic_cards(world.session, page_size=3)}) == len(bff._complete_strategic_cards(world.session, page_size=3))


# --- E, F, M, N. the old pool boundary, adversarial ----------------------------------------------------------------------------------

def _boundary_world(world):
    """45 filler sites with RECENT reserved-matters grants fill the legacy 40-card phase slice (newest grant first); the target is phase-only with an
    OLDER grant, so the legacy pool never sees it. Fillers are INSUFFICIENT, the target's phase is STRONG."""
    for k in range(45):
        world.site(outline_age=700, rm_age=2 + k)
    target = world.site(rm_age=300, rm_phase="Phase 1", phase="S")
    return target


def test_e_f_m_the_legacy_bounded_feed_differs_from_the_oracle_and_the_new_path_equals_it(world):
    target = _boundary_world(world)
    legacy = build_opportunity_feed(world.session, limit=1, buyer_key=BUYER)
    legacy_sites = {int(c["params"]["site_id"]) for c in legacy["cards"] if c["opportunity_type"] == PLANNING_DELIVERY}
    assert target.id not in legacy_sites                                   # the old pool omitted the stronger family
    expected = oracle(world, 1)
    assert expected["shown"][0]["key"] == ("planning_delivery", target.id) and expected["shown"][0]["code"] == "S"
    assert summarise(build(world, 1)) == expected                          # N: the new implementation equals the oracle
    assert_equals_oracle(world, 3)


def test_e_several_phases_crossing_the_old_boundary_are_in_one_family(world):
    for k in range(45):
        world.site(outline_age=700, rm_age=2 + k)
    s = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, rm_phase="Phase 3", phase="P", parent="I")
    result = build(world, limit=40)
    family = family_of(result, s)
    phase_members = [m for m in family.members if m.slot == fam.SLOT_PHASE]
    assert len(phase_members) == 2 and any(m.slot == fam.SLOT_LIFECYCLE for m in family.members)   # phase + unphased + the lapse subject
    assert_equals_oracle(world, 40)


# --- precedence regression -------------------------------------------------------------------------------------------------------------

def _ids(cards):
    return {c["id"] for c in cards}


def test_precedence_case_1_a_phase_outside_the_old_slice_still_suppresses_recent_permission(world):
    for k in range(45):
        world.site(outline_age=700, rm_age=2 + k)
    x = world.site(outline_age=700, rm_age=60)                                  # recent grant; its phase cards rank beyond the old 40 slice
    *_, delivery = _planning_delivery_cards(world.session, 40)
    assert f"opp-recent-permission-{x.id}" in _ids(delivery) and not any(i.startswith(f"opp-phase-{x.id}-") for i in _ids(delivery))   # the quirk
    result = build(world, limit=100)
    subjects = {m.subject_key for f in result["families"] for m in f.members}
    assert not any(k == f"opp-recent-permission-{x.id}" for k in subjects)
    assert any(k.startswith(f"opp-phase-{x.id}-") for k in subjects)
    assert_equals_oracle(world, 100)


def test_precedence_case_2_a_lapse_outside_the_old_slice_still_suppresses_long_pending(world):
    for k in range(45):
        world.site(outline_age=LAPSE_AGE + 1 + k)                                # earlier (still approaching) deadlines fill the old 40 lapse slice
    y = world.site(outline_age=LAPSE_AGE, pending_age=400)                       # later deadline: outside the old slice; also has a long-pending filing
    *_, delivery = _planning_delivery_cards(world.session, 40)
    assert f"opp-long-pending-{y.id}" in _ids(delivery) and f"opp-lapse-{y.id}" not in _ids(delivery)                                   # the quirk
    result = build(world, limit=100)
    subjects = {m.subject_key for f in result["families"] for m in f.members}
    assert f"opp-lapse-{y.id}" in subjects and f"opp-long-pending-{y.id}" not in subjects
    assert_equals_oracle(world, 100)


def test_precedence_case_3_a_phase_only_family_outside_the_old_pool_is_discoverable(world):
    target = _boundary_world(world)
    result = build(world, limit=1)
    assert [f.family_key for f in result["families"]] == [("planning_delivery", target.id)]


# --- J, K, L. no summation, overlap, input order ------------------------------------------------------------------------------------

def test_j_k_no_unit_summation_and_overlap_state_is_preserved(world):
    multi = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="S", phase="S")
    single = world.site(rm_age=300, rm_phase="Phase 1", phase="S")
    result = build(world)
    by_key = {f.family_key[1]: f for f in result["families"]}
    assert by_key[multi.id].overlap_state == fam.OVERLAP_MAY_OVERLAP and len(by_key[multi.id].members) >= 2
    assert fam.OVERLAP_WARNING == "Related subjects may overlap — do not add unit counts."
    assert by_key[single.id].overlap_state in (fam.OVERLAP_SINGLE_SUBJECT, fam.OVERLAP_MAY_OVERLAP)
    names = {f.name for f in dataclasses.fields(fam.OpportunityFamily)} | {f.name for f in dataclasses.fields(fam.FamilySubject)}
    assert not {n for n in names if "unit" in n or "total" in n or "sum" in n}
    assert not {k for k in result["counts"] if "unit" in k}


def test_l_input_order_is_irrelevant(world, monkeypatch):
    for fits in (("S", "I"), ("P", "N"), ("I", "S")):
        world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent=fits[0], phase=fits[1])
    world.site(rm_age=300, rm_phase="Phase 1", phase="X")
    baseline = summarise(build(world))
    real = fam.group_into_families
    for transform in (lambda s: list(reversed(s)), lambda s: random.Random(7).sample(s, len(s))):
        monkeypatch.setattr(bff, "group_into_families", lambda subjects, t=transform: real(t(list(subjects))))
        assert summarise(build(world)) == baseline


# --- oracle equivalence over generated worlds -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("seed", range(6))
def test_generated_worlds_equal_the_unbounded_oracle_for_several_limits(world, seed):
    rng = random.Random(seed)
    for _ in range(rng.randint(8, 16)):
        kind = rng.choice(["lapse_phase", "lapse_only", "phase_only", "recent", "pending"])
        fit = lambda: rng.choice("SPXIN")   # noqa: E731
        if kind == "lapse_phase":
            world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent=fit(), phase=fit())
        elif kind == "lapse_only":
            world.site(outline_age=LAPSE_AGE + rng.randint(0, 80), parent=fit())
        elif kind == "phase_only":
            world.site(rm_age=rng.randint(100, 600), rm_phase=f"Phase {rng.randint(1, 3)}", phase=fit(), parent=fit())
        elif kind == "recent":
            world.site(outline_age=rng.randint(5, 60), parent=fit())
        else:
            world.site(pending_age=rng.randint(250, 700), parent=fit())
    for cap in rng.sample(range(100, 900), 3):
        world.allocation(capacity=cap, fit=rng.choice("SPXIN"))
    for limit in (1, 2, 3, 100):
        assert_equals_oracle(world, limit)


# --- fail closed ---------------------------------------------------------------------------------------------------------------------

def _wrap_delivery(monkeypatch, mutate):
    real = bff._planning_delivery_cards

    def wrapped(session, pool_limit):
        lapse, phase, recent, pending, delivery = real(session, pool_limit)
        return lapse, phase, recent, pending, mutate(list(delivery))
    monkeypatch.setattr(bff, "_planning_delivery_cards", wrapped)


def _legacy_still_works(world):
    assert set(build_opportunity_feed(world.session, limit=6, buyer_key=BUYER)) == {"cards", "counts", "buyer_key"}


def test_fail_closed_conflicting_lifecycle_representations(world, monkeypatch):
    s = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE)

    def add_second_lifecycle(cards):
        lapse = next(c for c in cards if c["id"] == f"opp-lapse-{s.id}")
        return [*cards, {**lapse, "id": f"opp-recent-permission-{s.id}"}]
    _wrap_delivery(monkeypatch, add_second_lifecycle)
    with pytest.raises(fam.ConflictingLifecycleRepresentations):
        build(world)
    _legacy_still_works(world)


def test_fail_closed_conflicting_strategic_subjects(world, monkeypatch):
    world.allocation(capacity=8400, fit="S")
    real = bff._complete_strategic_cards

    def doubled(session, **kw):
        cards = real(session, **kw)
        twin = dict(cards[0], matching_facts=dataclasses.replace(cards[0]["matching_facts"], unit_count=cards[0]["matching_facts"].unit_count))
        world.alloc[8401] = "N"
        twin["matching_facts"] = dataclasses.replace(twin["matching_facts"], unit_count=8401)
        return [*cards, twin]
    monkeypatch.setattr(bff, "_complete_strategic_cards", doubled)
    with pytest.raises(fam.ConflictingSubjectInput):
        build(world)
    _legacy_still_works(world)


def test_fail_closed_mixed_identity_systems(world, monkeypatch):
    s = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE)
    real = bff.subject_from_feed_card

    def mixed(card):
        subject = real(card)
        if card["id"] == f"opp-lapse-{s.id}":
            return fam.subject_from_opportunity_id(f"planning_delivery:site:{s.id}", fit=subject.fit)
        return subject
    monkeypatch.setattr(bff, "subject_from_feed_card", mixed)
    with pytest.raises(fam.MixedIdentitySystems):
        build(world)
    _legacy_still_works(world)


def test_fail_closed_malformed_adapter_identity_and_unknown_buyer(world, monkeypatch):
    s = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE)
    with monkeypatch.context() as scoped:
        _wrap_delivery(scoped, lambda cards: [dict(c, id=c["id"].replace(f"opp-lapse-{s.id}", f"opp-lapse-0{s.id}")) for c in cards])
        with pytest.raises(fam.UnsupportedSubject):
            build(world)
    import app.policy.buyer_profile_store as store
    from app.security.access import AccessDenied
    with monkeypatch.context() as scoped:
        scoped.setattr(store, "get_buyer_profile_dataclass", lambda session, key: None)
        with pytest.raises(bff.UnknownBuyerProfile):
            build(world)
    with pytest.raises(AccessDenied):   # a buyer outside the caller's grants is refused by the Stage 1 boundary, never degraded to an empty/legacy result
        bff.build_buyer_opportunity_families(world.session, "no_such_buyer", 6)
    _legacy_still_works(world)


# --- generic / non-buyer preservation, additivity ----------------------------------------------------------------------------------

def test_generic_and_legacy_buyer_modes_never_construct_families(world, monkeypatch):
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="S", phase="S")
    world.allocation(capacity=8400, fit="S")
    expected_generic = build_opportunity_feed(world.session, limit=6)

    def boom(*a, **k):
        raise AssertionError("family construction must not run in the legacy feed")
    monkeypatch.setattr(fam, "group_into_families", boom)
    monkeypatch.setattr(bff, "group_into_families", boom)
    assert [c["id"] for c in build_opportunity_feed(world.session, limit=6)["cards"]] == [c["id"] for c in expected_generic["cards"]]
    legacy = build_opportunity_feed(world.session, limit=6, buyer_key=BUYER)
    assert set(legacy["counts"]) >= {"strategic_land", "approaching_lapse", "undeveloped_phase", "recent_permission", "long_pending_application",
                                     "excluded_not_suitable"}   # legacy card counts untouched
    assert "families" not in legacy


def test_the_dashboard_and_ui_do_not_reference_the_family_feed():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    for path in (root / "app" / "ui").rglob("*.py"):
        assert "buyer_family_feed" not in path.read_text(encoding="utf-8")


# --- G2 not consumed ------------------------------------------------------------------------------------------------------------------

def test_g2_is_not_required_and_no_relationship_is_emitted(world, monkeypatch):
    s = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="I", phase="S")
    monkeypatch.setitem(sys.modules, "app.reporting.subject_relationships", None)   # any import of G2 would now raise ImportError
    result = build(world)
    assert family_of(result, s).fit == STRONG_FIT
    tree = ast.parse(inspect.getsource(bff))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any("subject_relationships" in (m or "") for m in imported)
    assert not {n for n in {f.name for f in dataclasses.fields(fam.OpportunityFamily)} if "relationship" in n or "contain" in n}
    assert "relationship" not in " ".join(result["counts"])


# --- memoisation, performance, no model/paid calls ----------------------------------------------------------------------------------

def test_request_scoped_memoisation_reduces_context_builds_and_preserves_results(world, monkeypatch):
    for _ in range(4):
        world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="S", phase="I")
    world.allocation(capacity=8400, fit="P")
    calls = {"n": 0}
    real_site, real_alloc = b2.build_b2_context_for_planning_delivery, b2.build_b2_context_for_strategic_land

    def counting(fn):
        def inner(*a, **k):
            calls["n"] += 1
            return fn(*a, **k)
        return inner
    monkeypatch.setattr(b2, "build_b2_context_for_planning_delivery", counting(real_site))
    monkeypatch.setattr(b2, "build_b2_context_for_strategic_land", counting(real_alloc))
    t0 = time.perf_counter(); on = build(world); t_on = time.perf_counter() - t0
    builds_on, calls["n"] = calls["n"], 0
    t0 = time.perf_counter(); off = build(world, memoise_context=False); t_off = time.perf_counter() - t0
    builds_off = calls["n"]
    assert summarise(on) == summarise(off) == oracle(world, 6)
    assert builds_on == 5 and builds_off > builds_on            # one context per site (4) + one per allocation (1), versus one per subject
    print(f"\nG3b informational timing: memoised {t_on:.3f}s ({builds_on} contexts) / unmemoised {t_off:.3f}s ({builds_off} contexts)")
    assert not any(hasattr(bff, name) for name in ("_CACHE", "CACHE", "_cache"))   # no module-level cache; the dict dies with the call


def test_no_model_paid_or_network_calls_in_family_construction(world, monkeypatch):
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="S", phase="I")
    world.allocation(capacity=8400, fit="P")

    def no_network(*a, **k):
        raise AssertionError("family construction attempted a network connection")
    monkeypatch.setattr(socket.socket, "connect", no_network)
    assert build(world)["counts"]["families_considered"] == 2
    source = inspect.getsource(bff)
    assert not any(token in source.lower() for token in ("anthropic", "openai", "httpx", "requests.", "llm", "urllib"))


def test_family_limit_applies_to_families_not_cards(world):
    for _ in range(5):
        world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="S", phase="S")
    result = build(world, limit=2)
    assert len(result["families"]) == 2 and result["counts"]["families_considered"] == 5 and result["counts"]["subjects_considered"] == 15
    assert result["counts"]["families_shown"] == 2


# --- missing matching facts fail closed (Product Owner decision 1) ---------------------------------------------------------------------

def _strip_facts(monkeypatch, predicate):
    real = bff._attach_planning_delivery_matching_facts

    def attach(session, cards):
        real(session, cards)
        for card in cards:
            if predicate(card):
                card["matching_facts"] = None
    monkeypatch.setattr(bff, "_attach_planning_delivery_matching_facts", attach)


def test_missing_facts_on_a_lifecycle_subject_fail_closed(world, monkeypatch):
    s = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="I", phase="S")
    _strip_facts(monkeypatch, lambda c: c["id"] == f"opp-lapse-{s.id}")
    with pytest.raises(bff.MissingFamilySubjectMatchingFacts) as caught:
        build(world)
    assert caught.value.subject_id == f"opp-lapse-{s.id}" and caught.value.subject_type == PLANNING_DELIVERY


def test_missing_facts_on_a_phase_subject_fail_closed_and_no_partial_family_is_returned(world, monkeypatch):
    s = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="I", phase="S")
    healthy = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="S", phase="S")
    _strip_facts(monkeypatch, lambda c: c["id"].startswith(f"opp-phase-{s.id}-") and c.get("phase_code") != "Whole site / unphased")
    result = None
    with pytest.raises(bff.MissingFamilySubjectMatchingFacts) as caught:
        result = build(world)                    # a STRONG phase was the family's best subject: it must not be dropped silently
    assert caught.value.subject_id.startswith(f"opp-phase-{s.id}-")
    assert result is None and healthy.id         # nothing partial (not even the healthy family) is returned


def test_missing_facts_on_a_strategic_subject_fail_closed(world, monkeypatch):
    a = world.allocation(capacity=8400, fit="S")
    real = bff._complete_strategic_cards
    monkeypatch.setattr(bff, "_complete_strategic_cards", lambda session, **kw: [dict(c, matching_facts=None) for c in real(session, **kw)])
    with pytest.raises(bff.MissingFamilySubjectMatchingFacts) as caught:
        build(world)
    assert caught.value.subject_id == f"opp-feed-alloc-{a.id}" and caught.value.subject_type == STRATEGIC_LAND


def test_missing_facts_do_not_fall_back_to_the_legacy_feed_and_legacy_keeps_its_skip_behaviour(world, monkeypatch):
    s = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="S", phase="S")
    import app.reporting.opportunity_feed as legacy_feed
    called = {"legacy": 0}
    real_legacy = legacy_feed.build_opportunity_feed
    real_attach = legacy_feed._attach_planning_delivery_matching_facts

    def counting_legacy(*a, **k):
        called["legacy"] += 1
        return real_legacy(*a, **k)

    def strip_all(session, cards):
        real_attach(session, cards)
        for card in cards:
            card["matching_facts"] = None
    monkeypatch.setattr(legacy_feed, "build_opportunity_feed", counting_legacy)
    with monkeypatch.context() as scoped:
        scoped.setattr(bff, "_attach_planning_delivery_matching_facts", strip_all)
        with pytest.raises(bff.MissingFamilySubjectMatchingFacts):
            build(world)
    assert called["legacy"] == 0                 # no silent legacy fallback
    with monkeypatch.context() as scoped:        # legacy buyer feed: cards without facts are skipped, no error (unchanged behaviour)
        scoped.setattr(legacy_feed, "_attach_planning_delivery_matching_facts", strip_all)
        legacy = real_legacy(world.session, limit=6, buyer_key=BUYER)
    assert legacy["cards"] == [] and s.id
