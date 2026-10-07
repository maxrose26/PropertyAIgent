"""Stage 2.5B G1 (spec 025): strict acquisition-subject identity grammar, parser and legacy-anchor compatibility.

Pure tests - no database, no production. They pin that EXISTING ids and anchors are unchanged, that unknown or
malformed ids fail closed (never WHOLE_SITE), that new-kind identities are delimiter-safe and length-capped, and
that no new kind is emit-capable.
"""
from __future__ import annotations

import pathlib

import pytest

import app.reporting.acquisition_subjects as subjects
from app.policy import agent_evaluation_persistence as persistence
from app.policy.agent_evaluation_persistence import WHOLE_ALLOCATION, WHOLE_SITE, resolve_acquisition_subject_key
from app.policy.buyer_matching import PLANNING_DELIVERY, STRATEGIC_LAND
from app.reporting.acquisition_subjects import (
    IdentityTooLong, MalformedOpportunityId, NewKindNotEmitCapable, UnknownOpportunityKind,
    build_new_kind_opportunity_id, decode_scope_key, encode_scope_key, family_identity, new_kind_anchor_scope_key,
    parse_opportunity_id,
)
from app.reporting.opportunity_universe import (
    planning_delivery_long_pending_application_opportunity_id, planning_delivery_phase_opportunity_id,
    planning_delivery_recent_permission_opportunity_id, planning_delivery_site_opportunity_id,
    strategic_land_opportunity_id,
)

UNPHASED = "Whole site / unphased"


def _previous_resolver(opportunity_id: str, opportunity_type: str):
    """VERBATIM copy of the resolver as it existed before G1 (master ca2f323) - the compatibility oracle."""
    parts = opportunity_id.split(":")
    kind = parts[1]
    anchor_id = int(parts[2])
    if opportunity_type == STRATEGIC_LAND:
        return (STRATEGIC_LAND, anchor_id, WHOLE_ALLOCATION)
    if kind == "phase":
        phase_code = parts[3]
        return (PLANNING_DELIVERY, anchor_id, phase_code)
    return (PLANNING_DELIVERY, anchor_id, WHOLE_SITE)


LEGACY_IDS = [
    (strategic_land_opportunity_id(1), STRATEGIC_LAND),
    (strategic_land_opportunity_id(213), STRATEGIC_LAND),
    (planning_delivery_site_opportunity_id(526), PLANNING_DELIVERY),
    (planning_delivery_long_pending_application_opportunity_id(61), PLANNING_DELIVERY),
    (planning_delivery_recent_permission_opportunity_id(460), PLANNING_DELIVERY),
    (planning_delivery_phase_opportunity_id(281, "1"), PLANNING_DELIVERY),
    (planning_delivery_phase_opportunity_id(67, "3B"), PLANNING_DELIVERY),
    (planning_delivery_phase_opportunity_id(149, UNPHASED), PLANNING_DELIVERY),
    (planning_delivery_phase_opportunity_id(329, "O1"), PLANNING_DELIVERY),
    (planning_delivery_phase_opportunity_id(10, "Phase A / B"), PLANNING_DELIVERY),
    (planning_delivery_phase_opportunity_id(11, "1-2"), PLANNING_DELIVERY),
    (planning_delivery_phase_opportunity_id(12, "Plot 7 - north"), PLANNING_DELIVERY),
    (planning_delivery_phase_opportunity_id(13, "A:1"), PLANNING_DELIVERY),        # code containing ':'
    (planning_delivery_phase_opportunity_id(14, "A:1:2"), PLANNING_DELIVERY),
]


def test_literals_match_the_rest_of_the_code_base():
    assert subjects.PLANNING_DELIVERY == PLANNING_DELIVERY and subjects.STRATEGIC_LAND == STRATEGIC_LAND
    assert subjects.WHOLE_SITE == WHOLE_SITE and subjects.WHOLE_ALLOCATION == WHOLE_ALLOCATION


# --- existing ids and anchors are unchanged -------------------------------------------------------------------------

def test_existing_id_constructors_are_byte_for_byte_unchanged():
    assert strategic_land_opportunity_id(57) == "strategic_land:allocation:57"
    assert planning_delivery_site_opportunity_id(526) == "planning_delivery:site:526"
    assert planning_delivery_long_pending_application_opportunity_id(61) == "planning_delivery:long_pending_application:61"
    assert planning_delivery_recent_permission_opportunity_id(460) == "planning_delivery:recent_permission:460"
    assert planning_delivery_phase_opportunity_id(281, "1") == "planning_delivery:phase:281:1"
    assert planning_delivery_phase_opportunity_id(149, UNPHASED) == "planning_delivery:phase:149:Whole site / unphased"


@pytest.mark.parametrize("opportunity_id,opportunity_type", LEGACY_IDS)
def test_every_existing_shape_resolves_to_exactly_the_previous_anchor(opportunity_id, opportunity_type):
    assert resolve_acquisition_subject_key(opportunity_id, opportunity_type) == _previous_resolver(opportunity_id, opportunity_type)


@pytest.mark.parametrize("opportunity_id,opportunity_type", LEGACY_IDS)
def test_every_existing_shape_parses_deterministically_and_is_legacy(opportunity_id, opportunity_type):
    parsed = parse_opportunity_id(opportunity_id)
    assert parsed == parse_opportunity_id(opportunity_id)
    assert parsed.is_legacy and parsed.domain == opportunity_type
    assert persistence._opportunity_kind(opportunity_id) == opportunity_id.split(":")[1]  # the old behaviour


def test_whole_site_phase_and_allocation_anchors_are_exactly_as_before():
    assert resolve_acquisition_subject_key("planning_delivery:site:61", PLANNING_DELIVERY) == (PLANNING_DELIVERY, 61, WHOLE_SITE)
    assert resolve_acquisition_subject_key("planning_delivery:phase:67:3B", PLANNING_DELIVERY) == (PLANNING_DELIVERY, 67, "3B")
    assert resolve_acquisition_subject_key("strategic_land:allocation:57", STRATEGIC_LAND) == (STRATEGIC_LAND, 57, WHOLE_ALLOCATION)


def test_lifecycle_kinds_share_one_whole_site_anchor():
    keys = {resolve_acquisition_subject_key(fn(61), PLANNING_DELIVERY) for fn in (
        planning_delivery_site_opportunity_id, planning_delivery_long_pending_application_opportunity_id,
        planning_delivery_recent_permission_opportunity_id)}
    assert keys == {(PLANNING_DELIVERY, 61, WHOLE_SITE)}


def test_phase_code_with_an_extra_colon_keeps_todays_truncating_anchor_pinned():
    """EXISTING behaviour, deliberately NOT repaired in G1: the anchor key is the text up to the next ':'.
    Fixing it would re-key existing history rows and needs its own migration decision."""
    assert resolve_acquisition_subject_key("planning_delivery:phase:13:A:1", PLANNING_DELIVERY) == (PLANNING_DELIVERY, 13, "A")
    assert resolve_acquisition_subject_key("planning_delivery:phase:14:A:1:2", PLANNING_DELIVERY) == (PLANNING_DELIVERY, 14, "A")
    parsed = parse_opportunity_id("planning_delivery:phase:13:A:1")
    assert parsed.scope_key == "A:1" and parsed.legacy_scope_key == "A"  # the parser keeps the full code


def test_spaces_slash_and_hyphen_in_legacy_phase_codes_are_preserved_verbatim():
    for code in (UNPHASED, "Phase A / B", "1-2", "Plot 7 - north"):
        assert resolve_acquisition_subject_key(f"planning_delivery:phase:9:{code}", PLANNING_DELIVERY) == (PLANNING_DELIVERY, 9, code)
        assert parse_opportunity_id(f"planning_delivery:phase:9:{code}").scope_key == code


# --- unknown kinds and malformed ids fail closed -----------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "planning_delivery:subject:61", "planning_delivery:bogus_kind:61:x", "planning_delivery:unknown:61",
    "planning_delivery:Site:61", "strategic_land:site:61", "strategic_land:subject:5", "other_domain:site:1",
])
def test_unknown_kinds_fail_closed(bad):
    domain = STRATEGIC_LAND if bad.startswith("strategic_land") else PLANNING_DELIVERY
    with pytest.raises(UnknownOpportunityKind):
        resolve_acquisition_subject_key(bad, domain)


def test_an_unknown_kind_can_never_become_whole_site():
    # The previous resolver anchored ANY other kind to WHOLE_SITE - this is the fail-open defect G1 removes.
    assert _previous_resolver("planning_delivery:subject:61", PLANNING_DELIVERY) == (PLANNING_DELIVERY, 61, WHOLE_SITE)
    with pytest.raises(UnknownOpportunityKind):
        resolve_acquisition_subject_key("planning_delivery:subject:61", PLANNING_DELIVERY)


@pytest.mark.parametrize("bad", [
    "", "planning_delivery", "planning_delivery:site", "planning_delivery:site:", "planning_delivery:site:abc",
    "planning_delivery:site:0", "planning_delivery:site:007", "planning_delivery:site:+5", "planning_delivery:site: 5",
    "planning_delivery:site:5 ", "planning_delivery:site:٣", "planning_delivery:site:1_0",
    "planning_delivery:site:99999999999", "planning_delivery:phase:281", "planning_delivery:phase:281:",
    "planning_delivery:site:61:extra", "planning_delivery:recent_permission:61:extra",
    "strategic_land:allocation", "strategic_land:allocation:5:extra", "strategic_land:allocation:x",
])
def test_malformed_ids_missing_or_extra_segments_are_rejected(bad):
    with pytest.raises(MalformedOpportunityId):
        parse_opportunity_id(bad)


def test_non_string_ids_are_rejected():
    for bad in (None, 61, b"planning_delivery:site:61"):
        with pytest.raises(MalformedOpportunityId):
            parse_opportunity_id(bad)


def test_an_id_type_mismatch_cannot_silently_anchor_onto_a_site():
    # Previously a strategic id with the planning type anchored onto Site 5's WHOLE_SITE subject.
    assert _previous_resolver("strategic_land:allocation:5", PLANNING_DELIVERY) == (PLANNING_DELIVERY, 5, WHOLE_SITE)
    with pytest.raises(MalformedOpportunityId):
        resolve_acquisition_subject_key("strategic_land:allocation:5", PLANNING_DELIVERY)
    with pytest.raises(MalformedOpportunityId):
        resolve_acquisition_subject_key("planning_delivery:site:5", STRATEGIC_LAND)


def test_a_malformed_child_id_cannot_resolve_to_its_parents_anchor():
    parent = resolve_acquisition_subject_key("planning_delivery:site:61", PLANNING_DELIVERY)
    for child in ("planning_delivery:component:61", "planning_delivery:component:61:x:y", "planning_delivery:component:61:",
                  "planning_delivery:component:061:abc", "planning_delivery:site:61:component"):
        with pytest.raises(subjects.SubjectIdentityError):
            assert resolve_acquisition_subject_key(child, PLANNING_DELIVERY) != parent


# --- new-kind grammar --------------------------------------------------------------------------------------------------

def test_scope_keys_are_delimiter_safe_deterministic_and_reversible():
    for raw in ("conventional", "Phase 1: north / retirement", UNPHASED, "naïve ☃", "a%b", "x" * 30):
        key = encode_scope_key(raw)
        assert key == encode_scope_key(raw)
        assert all(c not in key for c in ": /\t\n")
        assert decode_scope_key(key) == raw
    assert encode_scope_key("a:b") == "a%3Ab"


@pytest.mark.parametrize("key", ["a:b", "a b", "a/b", "", "a%zz", "a%41", "%c3", "a%3a"])
def test_non_canonical_or_unsafe_scope_keys_are_rejected(key):
    with pytest.raises(MalformedOpportunityId):
        decode_scope_key(key)


def test_new_kinds_have_explicit_mappings_and_namespaced_anchor_keys():
    assert subjects.NEW_KINDS == {"component": "MIXED_COMPONENT", "affordable_package": "AFFORDABLE_PACKAGE", "residual": "RESIDUAL_OPPORTUNITY"}
    assert new_kind_anchor_scope_key("component", "abc") == "component~abc"
    assert new_kind_anchor_scope_key("affordable_package", "abc") == "affordable~abc"


def test_new_kind_ids_round_trip_but_are_not_legacy():
    opportunity_id = build_new_kind_opportunity_id("component", 61, "Phase 1: conventional")
    assert opportunity_id == "planning_delivery:component:61:Phase%201%3A%20conventional"
    parsed = parse_opportunity_id(opportunity_id)
    assert (parsed.domain, parsed.kind, parsed.anchor_id, parsed.is_legacy) == (PLANNING_DELIVERY, "component", 61, False)
    assert decode_scope_key(parsed.scope_key) == "Phase 1: conventional"


def test_new_kind_ids_require_exactly_four_segments_and_a_safe_key():
    for bad in ("planning_delivery:component:61", "planning_delivery:component:61:a:b", "planning_delivery:component:61:a b",
                "planning_delivery:affordable_package:61:%zz"):
        with pytest.raises(MalformedOpportunityId):
            parse_opportunity_id(bad)


def test_over_length_new_identities_fail_closed():
    # 100-character anchor cap, reserved prefix included: 'component~' is 10 characters.
    assert len(new_kind_anchor_scope_key("component", "a" * 90)) == 100
    with pytest.raises(IdentityTooLong):
        new_kind_anchor_scope_key("component", "a" * 91)
    with pytest.raises(IdentityTooLong):
        build_new_kind_opportunity_id("component", 61, "é" * 40)  # percent-encoding inflates 3x
    with pytest.raises(IdentityTooLong):
        parse_opportunity_id("planning_delivery:component:61:" + "a" * 91)


def test_the_whole_id_cap_is_enforced():
    assert subjects.MAX_OPPORTUNITY_ID_LENGTH == 200 and subjects.MAX_ANCHOR_SCOPE_KEY_LENGTH == 100
    # an anchor-legal key can still make the full id too long only if the cap were exceeded; the guard exists:
    long_site = 2**31 - 1
    assert len(build_new_kind_opportunity_id("affordable_package", long_site, "a" * 80)) <= 200


def test_unrecognised_future_kinds_cannot_be_built():
    for kind in ("bogus_kind", "subject", "phase", "site"):
        with pytest.raises(UnknownOpportunityKind):
            build_new_kind_opportunity_id(kind, 61, "x")
    with pytest.raises(MalformedOpportunityId):
        build_new_kind_opportunity_id("component", 0, "x")


# --- the emission gate -------------------------------------------------------------------------------------------------

def test_new_kinds_are_not_emit_capable_and_cannot_resolve_to_the_parents_anchor():
    assert subjects.EMIT_CAPABLE_NEW_KINDS == frozenset()
    for kind in subjects.NEW_KINDS:
        opportunity_id = build_new_kind_opportunity_id(kind, 61, "abc")
        with pytest.raises(NewKindNotEmitCapable):
            resolve_acquisition_subject_key(opportunity_id, PLANNING_DELIVERY)


def test_when_the_gate_opens_a_child_anchor_is_distinct_from_the_parent(monkeypatch):
    monkeypatch.setattr(subjects, "EMIT_CAPABLE_NEW_KINDS", frozenset({"component"}))
    child = resolve_acquisition_subject_key(build_new_kind_opportunity_id("component", 61, "abc"), PLANNING_DELIVERY)
    parent = resolve_acquisition_subject_key("planning_delivery:site:61", PLANNING_DELIVERY)
    assert child == (PLANNING_DELIVERY, 61, "component~abc") and child != parent
    with pytest.raises(NewKindNotEmitCapable):  # affordable_package stays closed
        resolve_acquisition_subject_key(build_new_kind_opportunity_id("affordable_package", 61, "abc"), PLANNING_DELIVERY)


def test_nothing_outside_the_identity_module_emits_or_builds_new_kinds():
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in root.rglob("*.py"):
        if path.name in ("acquisition_subjects.py", "residual_opportunity.py"):   # residual_opportunity: the ONE sanctioned DERIVED (never persisted) builder, KIND_RESIDUAL only
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "build_new_kind_opportunity_id" in text or ":component:" in text or ":affordable_package:" in text:
            offenders.append(str(path.relative_to(root)))
    assert offenders == []
    derived = (root / "reporting" / "residual_opportunity.py").read_text(encoding="utf-8")
    assert "build_new_kind_opportunity_id(KIND_RESIDUAL" in derived and ":component:" not in derived and ":affordable_package:" not in derived


# --- strategic identity -------------------------------------------------------------------------------------------------

def test_strategic_allocation_identity_is_canonical_and_never_duplicated_per_site():
    parsed = parse_opportunity_id(strategic_land_opportunity_id(213))
    assert parsed.anchor_id == 213 and parsed.scope_key is None
    # The strategic family is the allocation itself: one identity, independent of any linked planning site.
    assert family_identity(parsed) == (STRATEGIC_LAND, 213)
    assert family_identity(parse_opportunity_id("planning_delivery:phase:281:1")) == (PLANNING_DELIVERY, 281)
    assert family_identity(parse_opportunity_id("planning_delivery:site:281")) == (PLANNING_DELIVERY, 281)
    assert resolve_acquisition_subject_key("strategic_land:allocation:213", STRATEGIC_LAND) == (STRATEGIC_LAND, 213, WHOLE_ALLOCATION)
