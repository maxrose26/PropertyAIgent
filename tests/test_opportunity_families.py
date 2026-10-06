"""Stage 2.5B G3a: pure opportunity-family grouping (spec 025, 'Opportunity-family decisions').

Pure tests - no database, no production. They pin: families are groupings (not subjects), planning and strategic family identity,
the representative order (fit > evidence quality > [no G2 specificity] > stable key), nothing hidden, family NOT_SUITABLE only when
all members are, no unit arithmetic, no containment claim, no new kinds, input-order independence.
"""
from __future__ import annotations

import dataclasses
import inspect
import itertools
from types import SimpleNamespace

import pytest

import app.reporting.opportunity_families as fam
from app.policy import buyer_matching as bm
from app.reporting.opportunity_families import (
    ConflictingLifecycleRepresentations, ConflictingSubjectInput, FamilySubject, OVERLAP_MAY_OVERLAP, OVERLAP_SINGLE_SUBJECT,
    OVERLAP_WARNING, UnsupportedSubject, group_into_families, subject_from_feed_card, subject_from_opportunity_id,
)
from app.reporting.opportunity_universe import (
    planning_delivery_long_pending_application_opportunity_id as pending_id,
    planning_delivery_phase_opportunity_id as phase_id,
    planning_delivery_recent_permission_opportunity_id as recent_id,
    planning_delivery_site_opportunity_id as site_id,
    strategic_land_opportunity_id as allocation_id,
)

S, P, I, N = fam.STRONG_FIT, fam.POSSIBLE_FIT, fam.INSUFFICIENT_EVIDENCE, fam.NOT_SUITABLE


def subj(opportunity_id, fit, *, inv=False, precision=None):
    return subject_from_opportunity_id(opportunity_id, fit=fit, investigative=inv, count_precision=precision)


def one(subjects):
    families = group_into_families(subjects)
    assert len(families) == 1
    return families[0]


def test_classification_literals_match_buyer_matching():
    assert (fam.STRONG_FIT, fam.POSSIBLE_FIT, fam.INSUFFICIENT_EVIDENCE, fam.NOT_SUITABLE) == (
        bm.STRONG_FIT, bm.POSSIBLE_FIT, bm.INSUFFICIENT_EVIDENCE, bm.NOT_SUITABLE)
    assert (fam.PLANNING_DELIVERY, fam.STRATEGIC_LAND) == (bm.PLANNING_DELIVERY, bm.STRATEGIC_LAND)


# --- family identity and grouping ----------------------------------------------------------------------------------------

def test_planning_family_identity_is_domain_and_site_id():
    family = one([subj(site_id(281), I, inv=True), subj(phase_id(281, "1"), S)])
    assert family.family_key == ("planning_delivery", 281)


def test_lifecycle_card_plus_phase_cards_are_one_planning_family():
    family = one([subj(site_id(5), I), subj(phase_id(5, "1"), P), subj(phase_id(5, "2"), I, inv=True)])
    assert len(family.members) == 3 and family.family_key == ("planning_delivery", 5)


def test_multiple_phase_cards_are_one_family_and_different_sites_are_different_families():
    families = group_into_families([subj(phase_id(5, "1"), S), subj(phase_id(5, "2"), S), subj(phase_id(6, "1"), S)])
    assert [f.family_key for f in families] == [("planning_delivery", 5), ("planning_delivery", 6)]
    assert len(families[0].members) == 2 and len(families[1].members) == 1


def test_a_phase_only_site_is_a_valid_family_and_no_whole_site_subject_is_synthesised():
    family = one([subj(phase_id(9, "1"), S), subj(phase_id(9, "2"), P)])
    assert [m.slot for m in family.members] == [fam.SLOT_PHASE, fam.SLOT_PHASE]
    assert not any(m.slot == fam.SLOT_LIFECYCLE for m in family.members)
    assert {m.subject_key for m in family.members} == {phase_id(9, "1"), phase_id(9, "2")}  # nothing added


def test_a_family_is_not_a_subject_and_claims_nothing_about_a_whole_site():
    family = one([subj(phase_id(9, "1"), S)])
    assert not isinstance(family, FamilySubject)
    assert family.family_key == ("planning_delivery", 9) and len(family.members) == 1
    assert not any(hasattr(family, name) for name in ("whole_site", "units", "total", "residual", "contained_in", "parent"))


def test_grouping_does_not_infer_containment_or_hierarchy_between_members():
    family = one([subj(site_id(5), I), subj(phase_id(5, "1"), S)])
    for member in family.members:
        assert not any(hasattr(member, name) for name in ("parent", "contained_in", "children"))
    assert all(not hasattr(r, "contained_in") for r in family.related)


# --- lifecycle de-duplication (fail closed) --------------------------------------------------------------------------------------

def test_lapse_style_lifecycle_card_and_phase_cards_may_coexist():
    family = one([subj(site_id(5), I), subj(phase_id(5, "1"), S)])
    assert len(family.members) == 2


@pytest.mark.parametrize("a,b", [
    (site_id(5), recent_id(5)), (site_id(5), pending_id(5)), (recent_id(5), pending_id(5)),
])
def test_conflicting_lifecycle_representations_fail_closed(a, b):
    with pytest.raises(ConflictingLifecycleRepresentations):
        group_into_families([subj(a, S), subj(b, P)])


def test_conflicting_lifecycle_feed_cards_fail_closed():
    with pytest.raises(ConflictingLifecycleRepresentations):
        group_into_families([subject_from_feed_card(_card("opp-lapse-5", site=5)),
                             subject_from_feed_card(_card("opp-recent-permission-5", site=5))])


# --- strategic family ---------------------------------------------------------------------------------------------------------------

def test_strategic_family_is_canonical_by_allocation_id():
    family = one([subj(allocation_id(213), S, precision="EXACT")])
    assert family.family_key == ("strategic_land", 213) and len(family.members) == 1


def test_duplicate_link_input_cannot_duplicate_an_allocation_family():
    """Several relationship rows / linked planning sites may each supply the same allocation: exactly ONE family results."""
    duplicates = [subj(allocation_id(213), S, precision="EXACT") for _ in range(5)]
    family = one(duplicates)
    assert len(family.members) == 1 and family.family_key == ("strategic_land", 213)


def test_strategic_and_planning_families_are_separate_identities():
    families = group_into_families([subj(allocation_id(7), S), subj(site_id(7), S)])
    assert {f.family_key for f in families} == {("strategic_land", 7), ("planning_delivery", 7)}


def test_an_allocation_cannot_have_two_distinct_subjects():
    a = FamilySubject("strategic_land", 213, "strategic_land:allocation:213", fam.SLOT_ALLOCATION, S)
    b = FamilySubject("strategic_land", 213, "another-key-for-213", fam.SLOT_ALLOCATION, S)
    with pytest.raises(ConflictingSubjectInput):
        group_into_families([a, b])


def test_conflicting_duplicate_of_one_subject_key_fails_closed():
    with pytest.raises(ConflictingSubjectInput):
        group_into_families([subj(site_id(5), S), subj(site_id(5), I)])


# --- representative order ---------------------------------------------------------------------------------------------------------

def test_fit_precedence_strong_possible_investigative_insufficient_not_suitable():
    members = [subj(phase_id(5, "5"), N), subj(phase_id(5, "4"), I), subj(phase_id(5, "3"), I, inv=True),
               subj(phase_id(5, "2"), P), subj(phase_id(5, "1"), S)]
    family = one(members)
    assert [m.fit for m in family.members] == [S, P, I, I, N]
    assert [m.investigative for m in family.members] == [False, False, True, False, False]
    assert family.representative.subject_key == phase_id(5, "1")


def test_investigative_exception_outranks_plain_insufficient():
    family = one([subj(phase_id(5, "1"), I), subj(phase_id(5, "2"), I, inv=True)])
    assert family.representative.subject_key == phase_id(5, "2")


def test_evidence_quality_breaks_a_fit_tie_exact_before_approximate_before_unknown():
    family = one([subj(phase_id(5, "1"), S, precision="UNKNOWN"), subj(phase_id(5, "2"), S, precision="APPROXIMATE"),
                  subj(phase_id(5, "3"), S, precision="EXACT"), subj(phase_id(5, "4"), S, precision="RANGE"),
                  subj(phase_id(5, "5"), S, precision=None)])
    assert [m.subject_key for m in family.members] == [phase_id(5, c) for c in ("3", "2", "4", "1", "5")]


def test_fit_outranks_evidence_quality():
    family = one([subj(phase_id(5, "1"), P, precision="EXACT"), subj(phase_id(5, "2"), S, precision="UNKNOWN")])
    assert family.representative.subject_key == phase_id(5, "2")


def test_stable_key_is_the_final_tie_break_and_has_no_kind_preference():
    """With identical fit and evidence, ONLY the key decides - a lifecycle subject beats a phase subject under one id system and loses
    under another, so no subject-kind preference exists."""
    a = [subject_from_feed_card(_card("opp-lapse-5", site=5)), subject_from_feed_card(_card("opp-phase-5-1", site=5, phase="1"))]
    assert group_into_families(a)[0].representative.subject_key == "opp-lapse-5"      # 'opp-l' < 'opp-p'
    b = [subj(site_id(5), S), subj(phase_id(5, "1"), S)]
    assert group_into_families(b)[0].representative.subject_key == phase_id(5, "1")   # 'planning_delivery:p' < 'planning_delivery:s'


def test_no_parent_child_specificity_is_applied_without_a_relationship():
    family = one([subj(site_id(5), S, precision="EXACT"), subj(phase_id(5, "1"), S, precision="EXACT")])
    # the phase wins only because its KEY sorts first, never because it is 'more specific'
    assert family.representative.subject_key == phase_id(5, "1")
    family2 = one([subj("planning_delivery:site:5", S, precision="EXACT"), subj("planning_delivery:phase:5:z", S, precision="EXACT")])
    assert family2.representative.subject_key == "planning_delivery:phase:5:z"  # still key order, 'p' < 's'


def test_input_order_never_changes_the_result():
    members = [subj(site_id(5), I, inv=True), subj(phase_id(5, "1"), S, precision="EXACT"), subj(phase_id(5, "2"), S, precision="EXACT"),
               subj(phase_id(5, "3"), P), subj(phase_id(5, "4"), N)]
    expected = group_into_families(members)
    for permutation in itertools.permutations(members):
        assert group_into_families(list(permutation)) == expected


def test_representative_selection_is_buyer_specific_through_the_supplied_fit():
    nesten = one([subj(site_id(5), I, inv=True), subj(phase_id(5, "1"), S)])
    housebuilder = one([subj(site_id(5), S), subj(phase_id(5, "1"), I, inv=True)])
    assert nesten.representative.subject_key == phase_id(5, "1")
    assert housebuilder.representative.subject_key == site_id(5)


# --- related subjects --------------------------------------------------------------------------------------------------------------

def test_every_subject_is_retained_and_roles_are_explicit():
    members = [subj(phase_id(5, "1"), S), subj(phase_id(5, "2"), S), subj(phase_id(5, "3"), P), subj(phase_id(5, "4"), I, inv=True),
               subj(phase_id(5, "5"), I), subj(phase_id(5, "6"), N)]
    family = one(members)
    assert len(family.members) == 6 and {m.subject_key for m in family.members} == {m.subject_key for m in members}
    assert [r.role for r in family.related] == [fam.ROLE_ALSO_STRONG_FIT, fam.ROLE_ALSO_POSSIBLE_FIT,
                                                 fam.ROLE_INSUFFICIENT_INVESTIGATIVE, fam.ROLE_INSUFFICIENT, fam.ROLE_NOT_SUITABLE]


def test_a_parent_is_not_hidden_because_a_child_won_a_tie_nor_the_reverse():
    for first, second in ((site_id(5), phase_id(5, "1")), (phase_id(5, "1"), site_id(5))):
        family = one([subj(first, S), subj(second, S)])
        assert len(family.members) == 2
        assert family.related[0].role == fam.ROLE_ALSO_STRONG_FIT


# --- family fit ---------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("other,expected", [(S, S), (P, P), (I, I)])
def test_not_suitable_plus_another_fit_is_not_terminally_excluded(other, expected):
    family = one([subj(phase_id(5, "1"), N), subj(phase_id(5, "2"), other)])
    assert family.fit == expected and not family.is_terminally_excluded


def test_a_family_is_terminally_excluded_only_when_every_member_is_not_suitable():
    family = one([subj(phase_id(5, "1"), N), subj(phase_id(5, "2"), N)])
    assert family.fit == N and family.is_terminally_excluded
    assert not one([subj(phase_id(5, "1"), N), subj(phase_id(5, "2"), I)]).is_terminally_excluded


def test_family_fit_follows_the_representative_including_the_investigative_flag():
    family = one([subj(phase_id(5, "1"), I, inv=True), subj(phase_id(5, "2"), I)])
    assert family.fit == I and family.investigative is True


# --- no unit arithmetic / no containment ---------------------------------------------------------------------------------------------

def test_the_model_has_no_unit_field_so_no_total_or_residual_can_exist():
    names = {f.name for f in dataclasses.fields(FamilySubject)} | {f.name for f in dataclasses.fields(fam.OpportunityFamily)}
    assert not any(term in name for name in names for term in ("unit", "total", "residual", "sum", "capacity", "contained"))


def test_a_500_parent_and_125_phase_produce_no_total_or_residual():
    parent = subject_from_opportunity_id(site_id(5), fit=I, investigative=True, count_precision="EXACT", source={"units": 500})
    phase = subject_from_opportunity_id(phase_id(5, "1"), fit=S, count_precision="EXACT", source={"units": 125})
    family = one([parent, phase])
    rendered = repr(family) + repr(sorted(vars(family))) + repr(dir(family))
    assert "625" not in rendered and "375" not in rendered
    assert not any(hasattr(family, name) for name in ("total_units", "units", "residual", "residual_units"))
    assert family.overlap_state == OVERLAP_MAY_OVERLAP and "do not add unit counts" in OVERLAP_WARNING


def test_overlap_state_for_single_and_multiple_subjects():
    assert one([subj(phase_id(5, "1"), S)]).overlap_state == OVERLAP_SINGLE_SUBJECT
    assert one([subj(phase_id(5, "1"), S), subj(phase_id(5, "2"), S)]).overlap_state == OVERLAP_MAY_OVERLAP
    assert OVERLAP_WARNING == "Related subjects may overlap — do not add unit counts."


def test_the_module_contains_no_arithmetic_over_subject_counts_or_containment_logic():
    source = inspect.getsource(fam)
    for forbidden in ("pursuant", "CONTAINED_IN", "extract_parent_reference", "residual_capacity", "evidenced_pairs", "sum("):
        assert forbidden not in source


# --- ordering across families ---------------------------------------------------------------------------------------------------------

def test_families_are_ordered_by_fit_bucket_then_family_key():
    families = group_into_families([subj(phase_id(9, "1"), I), subj(phase_id(3, "1"), S), subj(phase_id(7, "1"), S),
                                    subj(allocation_id(2), P), subj(phase_id(1, "1"), N)])
    assert [(f.family_key, f.fit) for f in families] == [
        (("planning_delivery", 3), S), (("planning_delivery", 7), S), (("strategic_land", 2), P),
        (("planning_delivery", 9), I), (("planning_delivery", 1), N)]


# --- existing ids / no new kinds ---------------------------------------------------------------------------------------------------------

def test_existing_ids_are_used_unchanged_as_the_subject_key():
    for opportunity_id in (site_id(5), pending_id(5), recent_id(5), phase_id(5, "1"), phase_id(5, "Whole site / unphased"),
                           phase_id(5, "A:1"), allocation_id(5)):
        assert subject_from_opportunity_id(opportunity_id, fit=S).subject_key == opportunity_id


def test_new_kinds_are_not_supported_and_none_is_emitted():
    from app.reporting import acquisition_subjects as subjects
    for kind in subjects.NEW_KINDS:
        with pytest.raises(UnsupportedSubject):
            subject_from_opportunity_id(subjects.build_new_kind_opportunity_id(kind, 5, "abc"), fit=S)
    family = one([subj(site_id(5), S)])
    assert all(m.subject_key.split(":")[1] in ("site", "phase", "recent_permission", "long_pending_application", "allocation")
               for m in family.members)


def test_malformed_ids_and_bad_inputs_fail_closed():
    with pytest.raises(subjects_error()):
        subject_from_opportunity_id("planning_delivery:mystery:5", fit=S)
    for kwargs in ({"fit": "MAYBE"}, {"fit": S, "count_precision": "PRECISE"}):
        with pytest.raises(UnsupportedSubject):
            subject_from_opportunity_id(site_id(5), **kwargs)
    with pytest.raises(UnsupportedSubject):
        FamilySubject("planning_delivery", 5, "k", fam.SLOT_ALLOCATION, S)       # wrong slot for the domain
    with pytest.raises(UnsupportedSubject):
        FamilySubject("strategic_land", 5, "k", fam.SLOT_PHASE, S)
    with pytest.raises(UnsupportedSubject):
        group_into_families([object()])


def subjects_error():
    from app.reporting.acquisition_subjects import SubjectIdentityError
    return SubjectIdentityError


def test_model_objects_are_immutable():
    family = one([subj(phase_id(5, "1"), S)])
    with pytest.raises(dataclasses.FrozenInstanceError):
        family.representative = None
    with pytest.raises(dataclasses.FrozenInstanceError):
        family.representative.fit = N


# --- feed-card adapter -----------------------------------------------------------------------------------------------------------------

def _card(card_id, *, site=None, allocation=None, phase=None, fit=S, inv=False, precision="EXACT", otype=None):
    params = {"site_id": str(site)} if site is not None else {"allocation_id": str(allocation)}
    return {
        "id": card_id, "opportunity_type": otype or ("planning_delivery" if site is not None else "strategic_land"),
        "params": params, "phase_code": phase,
        "buyer_fit": SimpleNamespace(classification=fit, is_investigative_exception=inv),
        "count_assessment": SimpleNamespace(precision=precision),
    }


def test_feed_cards_map_to_stable_subjects_keyed_by_card_id():
    assert subject_from_feed_card(_card("opp-lapse-5", site=5)).slot == fam.SLOT_LIFECYCLE
    assert subject_from_feed_card(_card("opp-recent-permission-5", site=5)).slot == fam.SLOT_LIFECYCLE
    assert subject_from_feed_card(_card("opp-long-pending-5", site=5)).slot == fam.SLOT_LIFECYCLE
    phase = subject_from_feed_card(_card("opp-phase-5-Whole site / unphased", site=5, phase="Whole site / unphased"))
    assert phase.slot == fam.SLOT_PHASE and phase.subject_key == "opp-phase-5-Whole site / unphased" and phase.anchor_id == 5
    allocation = subject_from_feed_card(_card("opp-feed-alloc-213", allocation=213))
    assert allocation.slot == fam.SLOT_ALLOCATION and allocation.family_key == ("strategic_land", 213)


@pytest.mark.parametrize("bad", [
    _card("opp-mystery-5", site=5), _card("opp-lapse-5", site=6), _card("opp-phase-5-1", site=5, phase=None),
    _card("opp-feed-alloc-5", allocation=6), _card("opp-lapse-5", site=5, otype="strategic_land"),
    {"id": 5}, {**_card("opp-lapse-5", site=5), "buyer_fit": None},
])
def test_unrecognised_or_inconsistent_feed_cards_fail_closed(bad):
    with pytest.raises(UnsupportedSubject):
        subject_from_feed_card(bad)


# --- repository examples (captured evidence and fixtures only; no production read) -----------------------------------------------------

def test_site_281_groups_the_existing_phase_subject_without_asserting_a_whole_site_or_containment():
    # The captured evidence exposes the existing phase opportunity planning_delivery:phase:281:1 (National Housebuilder: INSUFFICIENT,
    # investigative, EXACT 140). No whole-site subject is asserted: the current feed/universe does not provably create one here.
    family = one([subj(phase_id(281, "1"), I, inv=True, precision="EXACT")])
    assert family.family_key == ("planning_delivery", 281) and len(family.members) == 1
    assert family.overlap_state == OVERLAP_SINGLE_SUBJECT and not family.related


def test_site_526_is_a_family_of_one_with_no_decomposition():
    family = one([subj(site_id(526), I, inv=True, precision="EXACT")])
    assert len(family.members) == 1 and family.related == () and family.overlap_state == OVERLAP_SINGLE_SUBJECT


def test_strategic_allocation_213_is_exactly_one_strategic_family_for_either_buyer():
    families = group_into_families([subj(allocation_id(213), S, precision="EXACT"), subj(allocation_id(213), S, precision="EXACT")])
    assert [f.family_key for f in families] == [("strategic_land", 213)]


def test_synthetic_parent_plus_phase_are_related_by_family_only():
    family = one([subj(site_id(100), I, inv=True, precision="EXACT"), subj(phase_id(100, "1"), S, precision="EXACT")])
    assert family.representative.subject_key == phase_id(100, "1")
    assert [r.subject.subject_key for r in family.related] == [site_id(100)]
    assert family.overlap_state == OVERLAP_MAY_OVERLAP
