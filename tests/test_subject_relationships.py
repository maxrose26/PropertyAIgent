"""Stage 2.5B G2: evidence-qualified CONTAINED_IN relationships (spec 025, 'G2').

Pure tests - no database, no production. Every gate of the qualified direct-parent rule is exercised, plus the rejected shapes,
ambiguity, reference safety, parent identity, the no-chain rule, and the site 281 captured wording (which must NOT yield a relationship).
"""
from __future__ import annotations

import dataclasses
import inspect
from types import SimpleNamespace

import pytest

import app.reporting.subject_relationships as sr
from app.reporting.residential_count import CountAssessment
from app.reporting.subject_relationships import (
    CONTAINED_IN, derive_containment, normalise_reference, scan_parent_citations,
)

RM, OUTLINE, VARIATION, NMA, DISCHARGE = "reserved_matters", "outline", "nmc_amendment", "nmc_amendment", "condition_discharge"
SITE = 281
CHILD_ID = f"site:{SITE}:phase:Phase 1"
PARENT_ID = f"site:{SITE}:whole_site:Whole site"
QUALIFIED_TEXT = "Reserved matters application for Phase 1 of a residential development pursuant to outline planning permission OUT/1"


def app(reference, role, proposal="", *, site=SITE, council="testcouncil"):
    return SimpleNamespace(reference=reference, role=role, proposal=proposal, site_id=site, council_code=council)


def count(subject_id, scope_type, refs, *, precision="EXACT", basis="consented", metric="total_residential", label="x"):
    exact = precision == "EXACT"
    return CountAssessment(
        scope_type=scope_type, scope_label=label, subject_id=subject_id, metric=metric, precision=precision,
        value=140 if exact else 140, lower=140 if exact else None, upper=140 if exact else None, resolution="agreement",
        confidence="high", sources=tuple(SimpleNamespace(application_reference=r) for r in refs), basis=basis)


def child(refs=("RES/2",), **kw):
    return count(CHILD_ID, "phase", refs, label="Phase 1", **kw)


def parent(refs=("OUT/1",), **kw):
    kw.setdefault("label", "Whole site")
    return count(kw.pop("subject_id", PARENT_ID), kw.pop("scope_type", "whole_site"), refs, **kw)


def standard_apps(proposal=QUALIFIED_TEXT, rm_role=RM):
    return [app("OUT/1", OUTLINE, "Outline application for 400 dwellings"), app("RES/2", rm_role, proposal)]


def derive(proposal=QUALIFIED_TEXT, *, child_count=None, parents=None, apps=None):
    return derive_containment(child_count or child(), parents if parents is not None else [parent()],
                              apps if apps is not None else standard_apps(proposal))


def assert_none(result, reason):
    assert result.relationship is None and result.reason == reason and reason in sr.REASONS


def _code_identifiers_and_imports():
    """Names and imports that appear in the module's CODE (docstrings and comments excluded)."""
    import ast
    tree = ast.parse(inspect.getsource(sr))
    identifiers, imports = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add((node.module or "").split(".")[0])
    return identifiers, imports


# --- 1-2. qualified -------------------------------------------------------------------------------------------------------------------

def test_01_qualified_reserved_matters_with_a_direct_exact_parent_citation_is_contained_in():
    result = derive()
    assert result.reason == sr.REASON_QUALIFIED
    rel = result.relationship
    assert rel.relationship == CONTAINED_IN and rel.child_subject_id == CHILD_ID and rel.parent_subject_id == PARENT_ID
    assert rel.child_application_reference == "RES/2" and rel.parent_application_reference == "OUT/1"
    assert rel.basis == sr.BASIS_RM_DIRECT_PARENT_CITATION and "OUT/1" in rel.provenance and "pursuant to" in rel.provenance.lower()


@pytest.mark.parametrize("phrase", [
    "pursuant to outline application OUT/1",
    "Pursuant To Outline Planning Application OUT/1",
    "pursuant to hybrid application OUT/1",
    "pursuant to outline planning permission OUT/1",
    "pursuant to planning permission ref. OUT/1",
    "pursuant to approval OUT/1",
    "following outline approval OUT/1",
    "following approval reference: OUT/1",
])
def test_02_each_accepted_phrase_qualifies_when_every_other_gate_passes(phrase):
    result = derive(f"Reserved matters for Phase 1 {phrase}")
    assert result.reason == sr.REASON_QUALIFIED and result.relationship.parent_application_reference == "OUT/1"


def test_02b_the_phrase_alone_is_never_sufficient():
    # authorised phrase, but the cited application does not exist -> no relationship
    assert_none(derive("Reserved matters pursuant to outline application OUT/999"), sr.REASON_CITED_APPLICATION_NOT_FOUND)
    # authorised phrase, exact application, but not a parent count source
    assert_none(derive(parents=[parent(refs=("SOMETHING/ELSE",))]), sr.REASON_CITED_NOT_PARENT_COUNT_SOURCE)


# --- 3-9. insufficient citation shapes ----------------------------------------------------------------------------------------------------

def test_03_bare_digit_citation_is_none():
    assert_none(derive("Reserved matters Phase 1 following outline approval 103844"), sr.REASON_BARE_DIGIT_CITATION)
    assert_none(derive("Reserved matters Phase 1 pursuant to planning permission 103844"), sr.REASON_BARE_DIGIT_CITATION)


def test_04_relating_to_is_none():
    assert_none(derive("Reserved matters for Phase 1 relating to application OUT/1"), sr.REASON_UNSPECIFIED_RELATION)
    assert_none(derive("Reserved matters for Phase 1 relating to approved app no. OUT/1"), sr.REASON_UNSPECIFIED_RELATION)


def test_05_in_association_with_is_none():
    assert_none(derive("Reserved matters for Phase 1 in association with application OUT/1"), sr.REASON_UNSPECIFIED_RELATION)


@pytest.mark.parametrize("role", [VARIATION, NMA, DISCHARGE, "other_substantive", "full", "outline"])
def test_06_08_variation_nma_discharge_and_other_children_are_none_under_the_rm_child_rule(role):
    assert_none(derive(apps=standard_apps(rm_role=role)), sr.REASON_NOT_RESERVED_MATTERS)


def test_09_a_false_parenthesised_number_is_none():
    assert_none(derive("Reserved matters Phase 2 (12345) landscaping"), sr.REASON_BARE_DIGIT_CITATION)


def test_no_citation_at_all_is_none():
    assert_none(derive("Reserved matters for Phase 1 of the scheme"), sr.REASON_NO_CITATION)
    assert_none(derive(""), sr.REASON_NO_CITATION)
    assert_none(derive(None), sr.REASON_NO_CITATION)


# --- 10-12. the cited application ---------------------------------------------------------------------------------------------------------

def test_10_a_citation_of_an_absent_application_is_none():
    assert_none(derive(apps=[app("RES/2", RM, QUALIFIED_TEXT)]), sr.REASON_CITED_APPLICATION_NOT_FOUND)


def test_11_an_application_on_another_site_or_council_does_not_count():
    other_site = [app("OUT/1", OUTLINE, site=999), app("RES/2", RM, QUALIFIED_TEXT)]
    assert_none(derive(apps=other_site), sr.REASON_CITED_APPLICATION_NOT_FOUND)
    other_council = [app("OUT/1", OUTLINE, council="othercouncil"), app("RES/2", RM, QUALIFIED_TEXT)]
    assert_none(derive(apps=other_council), sr.REASON_CITED_APPLICATION_NOT_FOUND)


def test_12_a_cited_application_that_does_not_support_the_parent_count_is_none():
    apps = standard_apps() + [app("OUT/OTHER", OUTLINE)]
    assert_none(derive(parents=[parent(refs=("OUT/OTHER",))], apps=apps), sr.REASON_CITED_NOT_PARENT_COUNT_SOURCE)
    assert_none(derive(parents=[]), sr.REASON_CITED_NOT_PARENT_COUNT_SOURCE)


# --- 13-15. the parent CountAssessment ------------------------------------------------------------------------------------------------------

def test_13_an_approximate_parent_is_none():
    assert_none(derive(parents=[parent(precision="APPROXIMATE")]), sr.REASON_PARENT_NOT_EXACT_OPERATIVE)


def test_14_an_unclear_or_phase_parent_scope_is_none():
    assert_none(derive(parents=[parent(scope_type="unclear", subject_id=f"site:{SITE}:unclear:Whole site (scope not confirmed)")]),
                sr.REASON_PARENT_SCOPE_NOT_WHOLE_SITE)
    assert_none(derive(parents=[parent(scope_type="phase", subject_id=f"site:{SITE}:phase:Phase 9")]),
                sr.REASON_PARENT_SCOPE_NOT_WHOLE_SITE)


def test_15_a_non_operative_parent_is_none():
    for basis in ("active", "superseded", None):
        assert_none(derive(parents=[parent(basis=basis)]), sr.REASON_PARENT_NOT_EXACT_OPERATIVE)


def test_incompatible_metric_and_site_mismatch_are_none():
    assert_none(derive(parents=[parent(metric="all_use_units")]), sr.REASON_METRIC_NOT_COMPATIBLE)
    assert_none(derive(child_count=child(metric="all_use_units")), sr.REASON_METRIC_NOT_COMPATIBLE)
    assert_none(derive(parents=[parent(subject_id="site:999:whole_site:Whole site")]), sr.REASON_PARENT_SITE_MISMATCH)


def test_the_child_must_be_a_phase_scope_with_a_source_and_identity():
    assert_none(derive(child_count=count(CHILD_ID, "whole_site", ("RES/2",))), sr.REASON_CHILD_NOT_PHASE_SCOPE)
    assert_none(derive(child_count=count("not-a-subject-id", "phase", ("RES/2",))), sr.REASON_SUBJECT_IDENTITY_UNAVAILABLE)
    assert_none(derive(child_count=child(refs=("UNKNOWN/APP",))), sr.REASON_NO_CHILD_SOURCE)


# --- 16-17. ambiguity ------------------------------------------------------------------------------------------------------------------------------

def test_16_two_distinct_qualifying_citations_are_ambiguous_and_never_pick_one():
    text = ("Reserved matters pursuant to outline planning permission OUT/1 and also following approval OUT/2")
    apps = standard_apps(text) + [app("OUT/2", OUTLINE)]
    assert_none(derive(parents=[parent(), parent(refs=("OUT/2",), subject_id=f"site:{SITE}:whole_site:Whole site 2")], apps=apps),
                sr.REASON_AMBIGUOUS_CITATIONS)
    # reversing the textual order changes nothing: no first-match, newest, oldest or highest-count choice
    text2 = "Reserved matters following approval OUT/2 and pursuant to outline planning permission OUT/1"
    assert_none(derive(parents=[parent()], apps=standard_apps(text2) + [app("OUT/2", OUTLINE)]), sr.REASON_AMBIGUOUS_CITATIONS)


def test_17_the_same_citation_repeated_is_one_unique_citation():
    text = QUALIFIED_TEXT + " (pursuant to outline planning permission OUT/1) pursuant to outline application OUT/1"
    result = derive(text)
    assert result.reason == sr.REASON_QUALIFIED and result.relationship.parent_application_reference == "OUT/1"
    assert [c.reference for c in scan_parent_citations(text).qualifying] == ["OUT/1"]


def test_multiple_reserved_matters_sources_with_different_citations_are_ambiguous():
    apps = [app("OUT/1", OUTLINE), app("OUT/2", OUTLINE),
            app("RES/2", RM, "Reserved matters pursuant to outline planning permission OUT/1"),
            app("RES/3", RM, "Reserved matters pursuant to outline planning permission OUT/2")]
    assert_none(derive(child_count=child(refs=("RES/2", "RES/3")), apps=apps), sr.REASON_AMBIGUOUS_CITATIONS)


def test_multiple_qualifying_parent_assessments_never_silently_choose_one():
    parents = [parent(), parent(subject_id=f"site:{SITE}:whole_site:Whole site (alt)")]
    assert_none(derive(parents=parents), sr.REASON_MULTIPLE_PARENT_ASSESSMENTS)
    assert_none(derive(parents=list(reversed(parents))), sr.REASON_MULTIPLE_PARENT_ASSESSMENTS)


# --- 18. no chain traversal -----------------------------------------------------------------------------------------------------------------

def test_18_rm_cites_var_which_cites_out_is_not_traversed():
    apps = [app("OUT/1", OUTLINE, "Outline application for 400 dwellings"),
            app("VAR/9", VARIATION, "Variation of conditions pursuant to outline planning permission OUT/1"),
            app("RES/2", RM, "Reserved matters Phase 1 pursuant to outline application VAR/9")]
    # the parent whole-site count is sourced by the OUT only: the child cites the VAR, which is not a parent source -> no chain
    assert_none(derive(parents=[parent(refs=("OUT/1",))], apps=apps), sr.REASON_CITED_NOT_PARENT_COUNT_SOURCE)
    # a variation can be the DIRECT parent only if it independently satisfies the parent count requirements
    result = derive(parents=[parent(refs=("VAR/9",))], apps=apps)
    assert result.reason == sr.REASON_QUALIFIED and result.relationship.parent_application_reference == "VAR/9"
    assert result.relationship.provenance.endswith("VAR/9")


# --- reference safety ---------------------------------------------------------------------------------------------------------------------------

def test_exact_reference_equality_is_mandatory_no_fuzzy_no_case_folding_no_inferred_parts():
    assert_none(derive("Reserved matters pursuant to outline planning permission out/1"), sr.REASON_CITED_APPLICATION_NOT_FOUND)
    assert_none(derive("Reserved matters pursuant to outline planning permission OUT/1/22",
                       apps=[app("OUT/1/22X", OUTLINE), app("RES/2", RM, "Reserved matters pursuant to outline planning permission OUT/1/22")]),
                sr.REASON_CITED_APPLICATION_NOT_FOUND)
    assert_none(derive("Reserved matters pursuant to outline planning permission OUT/1",
                       apps=[app("OUT/1/22", OUTLINE), app("RES/2", RM, "Reserved matters pursuant to outline planning permission OUT/1")]),
                sr.REASON_CITED_APPLICATION_NOT_FOUND)  # 'OUT/1' is not completed to 'OUT/1/22'


def test_normalisation_is_only_trailing_punctuation_and_whitespace():
    assert normalise_reference("  OUT/1. ") == "OUT/1" and normalise_reference("(OUT/1)") == "OUT/1" and normalise_reference("OUT/1;") == "OUT/1"
    assert normalise_reference("out/1") == "out/1"  # no case change
    result = derive("Reserved matters pursuant to outline planning permission (OUT/1).")
    assert result.reason == sr.REASON_QUALIFIED


def test_a_hyphenated_non_reference_captured_by_the_formatted_pattern_cannot_qualify():
    # the formatted pattern can capture hyphenated words; the exact-equality gate against existing references is what protects us
    scan = scan_parent_citations("Reserved matters pursuant to approval 3-bedroom-houses layout")
    assert [c.reference for c in scan.qualifying] == ["3-bedroom-houses"]
    assert_none(derive("Reserved matters pursuant to approval 3-bedroom-houses layout"), sr.REASON_CITED_APPLICATION_NOT_FOUND)


def test_the_scanner_returns_all_distinct_citations_sorted_not_by_position():
    scan = scan_parent_citations("following approval ZZ/9 then pursuant to outline planning permission AA/1")
    assert [c.reference for c in scan.qualifying] == ["AA/1", "ZZ/9"]


# --- 19. parent identity ------------------------------------------------------------------------------------------------------------------------

def test_19_parent_identity_is_the_exact_count_assessment_subject_id_not_merely_a_site():
    parents = [parent(subject_id=f"site:{SITE}:whole_site:Whole site", refs=("OUT/1",)),
               parent(subject_id=f"site:{SITE}:whole_site:Other whole-site scope", refs=("SOMETHING/ELSE",))]
    result = derive(parents=parents)
    assert result.relationship.parent_subject_id == f"site:{SITE}:whole_site:Whole site"
    assert result.relationship.parent_subject_id != f"site:{SITE}"
    assert result.relationship.child_subject_id == CHILD_ID


# --- 20-22. boundaries ---------------------------------------------------------------------------------------------------------------------------

def test_20_no_non_overlap_relationship_exists_or_is_emitted():
    assert sr.RELATIONSHIPS == frozenset({"CONTAINED_IN"})
    assert not hasattr(sr, "NOT_OVERLAPPING") and "NOT_OVERLAPPING" not in inspect.getsource(sr).replace("never inferred", "")  # type: ignore[arg-type]
    result = derive()
    assert result.relationship.relationship == CONTAINED_IN
    assert not any("overlap" in f.name for f in dataclasses.fields(sr.SubjectRelationshipEvidence))


def test_21_no_residual_arithmetic_or_unit_fields():
    names = {f.name for f in dataclasses.fields(sr.SubjectRelationshipEvidence)} | {f.name for f in dataclasses.fields(sr.ContainmentResult)}
    assert not any(term in name for name in names for term in ("unit", "total", "residual", "capacity", "sum"))
    identifiers, imports = _code_identifiers_and_imports()
    for forbidden in ("residual_capacity", "evidenced_pairs", "sum", "extract_parent_reference", "site_linking", "assess_residual_planning_capacity"):
        assert forbidden not in identifiers and forbidden not in imports


def test_22_the_model_is_pure_unpersisted_and_has_no_id_or_confidence():
    identifiers, imports = _code_identifiers_and_imports()
    assert imports <= {"re", "dataclasses", "typing", "__future__"}   # only the standard library: no db, network, feed or UI import
    for forbidden in ("session", "open", "execute", "commit", "requests"):
        assert forbidden not in identifiers
    names = {f.name for f in dataclasses.fields(sr.SubjectRelationshipEvidence)}
    assert names == {"relationship", "child_subject_id", "parent_subject_id", "child_application_reference",
                     "parent_application_reference", "basis", "provenance"}
    with pytest.raises(dataclasses.FrozenInstanceError):
        derive().relationship.basis = "x"


def test_role_literal_matches_the_platform_constant_and_a_real_application_resolves_to_it():
    from app.db.models import Application
    from app.reporting.scheme_reconciliation import ROLE_RESERVED_MATTERS, resolve_planning_role
    assert sr.ROLE_RESERVED_MATTERS == ROLE_RESERVED_MATTERS
    application = Application(reference="RES/2", council_code="testcouncil", proposal=QUALIFIED_TEXT, application_type="Reserved Matters")
    assert resolve_planning_role(application) == ROLE_RESERVED_MATTERS


def test_derivation_is_deterministic_and_input_order_independent():
    apps = standard_apps()
    first = derive(apps=apps)
    assert derive(apps=list(reversed(apps))) == first
    assert derive(parents=[parent(), parent(refs=("ZZ",), subject_id=f"site:{SITE}:whole_site:Whole site 2")]) == first


# --- site 281 (captured evidence; no production read) ----------------------------------------------------------------------------------------

CAPTURED_281_RM_TEXT = ("Reserved matters application for the Appearance, Landscaping, Layout, and Scale of Phase 1 of a residential "
                        "development pursuant to outline application VAR/3496")   # the capture was truncated at 160 characters


def _site_281_apps(rm_text):
    return [app("OUT/345898/20", OUTLINE, "Outline planning permission (with all matters reserved except for access) is sought for ..."),
            app("VAR/349651/22", VARIATION, "Variation of conditions to allow for phased development, including revised site drainage proposals"),
            app("RES/350957/23", RM, rm_text)]


def _site_281_counts(parent_refs):
    child_count = count(f"site:281:phase:Phase 1", "phase", ("RES/350957/23",), label="Phase 1")
    parent_count = count("site:281:whole_site:Whole site", "whole_site", parent_refs, label="Whole site")
    return child_count, parent_count


def test_site_281_captured_truncated_wording_yields_no_relationship():
    scan = scan_parent_citations(CAPTURED_281_RM_TEXT)
    assert [c.reference for c in scan.qualifying] == ["VAR/3496"]   # a truncated fragment, NOT an existing application reference
    child_count, parent_count = _site_281_counts(("OUT/345898/20",))
    result = derive_containment(child_count, [parent_count], _site_281_apps(CAPTURED_281_RM_TEXT))
    assert_none(result, sr.REASON_CITED_APPLICATION_NOT_FOUND)


def test_site_281_a_synthetic_full_phrase_citing_the_variation_needs_the_variation_to_be_a_parent_source():
    full = CAPTURED_281_RM_TEXT.replace("VAR/3496", "VAR/349651/22")
    child_count, parent_count = _site_281_counts(("OUT/345898/20",))
    # the RM cites the VAR; the whole-site count is sourced by the OUT -> no chain traversal, no relationship
    assert_none(derive_containment(child_count, [parent_count], _site_281_apps(full)), sr.REASON_CITED_NOT_PARENT_COUNT_SOURCE)
    # only if the VAR independently supports the exact consented whole-site count is it a valid DIRECT parent (synthetic)
    child_count, parent_count = _site_281_counts(("VAR/349651/22",))
    result = derive_containment(child_count, [parent_count], _site_281_apps(full))
    assert result.reason == sr.REASON_QUALIFIED and result.relationship.parent_application_reference == "VAR/349651/22"


# --- hardening: D1 reference length safety, D3 operative-basis drift, D4 real-object adapter -------------------------------------------

def test_d1_a_supported_length_reference_still_matches():
    for ref in ("OUT/1", "A/1/2", "A/1/2/3", "A/1/2/3/4"):
        assert [c.reference for c in scan_parent_citations(f"pursuant to approval {ref}").qualifying] == [ref]


@pytest.mark.parametrize("over_long", ["OUT/1/2/3/4/5", "OUT/1/2/3/4/5/6", "OUT/1/2/3/4/55", "OUT-1-2-3-4-5"])
def test_d1_an_over_long_reference_is_rejected_not_truncated_to_a_shorter_prefix(over_long):
    scan = scan_parent_citations(f"Reserved matters pursuant to outline permission {over_long}")
    assert scan.qualifying == ()
    prefix = "/".join(over_long.split("/")[:5]) if "/" in over_long else "-".join(over_long.split("-")[:5])
    assert prefix not in [c.reference for c in scan.qualifying]


def test_d1_an_over_long_reference_cannot_contain_into_a_real_shorter_reference():
    apps = [app("OUT/1/2/3/4", OUTLINE, "Outline"), app("RES/2", RM, "Reserved matters pursuant to outline permission OUT/1/2/3/4/5")]
    result = derive_containment(child(), [parent(refs=("OUT/1/2/3/4",))], apps)
    assert_none(result, sr.REASON_NO_CITATION)


def test_d1_exact_equality_remains_mandatory():
    apps = [app("OUT/1/2/3/4", OUTLINE, "Outline"), app("RES/2", RM, QUALIFIED_TEXT.replace("OUT/1", "out/1/2/3/4"))]
    assert_none(derive_containment(child(), [parent(refs=("OUT/1/2/3/4",))], apps), sr.REASON_CITED_APPLICATION_NOT_FOUND)


def test_d3_the_operative_basis_assumption_is_bound_to_the_canonical_constant():
    from app.reporting.residual_capacity import OPERATIVE_APPROVED_BASIS
    assert sr.BASIS_CONSENTED == OPERATIVE_APPROVED_BASIS == "consented"
    # and the real producer of operative counts still stamps that basis
    import app.reporting.scheme_reconciliation as rec
    assert 'basis="consented"' in inspect.getsource(rec) or "OPERATIVE_APPROVED_BASIS" in inspect.getsource(rec)


def test_d4_real_repository_objects_supply_everything_g2_consumes():
    """Real Application ORM objects (transient - no database), real ResolvedApplication, real FactPosition and a CountAssessment built by
    the real assess_positions producer: the runtime shape exposes reference, site_id, council_code, proposal, role and source references."""
    from app.db.models import Application
    from app.reporting.residential_count import assess_positions
    from app.reporting.residual_capacity import OPERATIVE_APPROVED_BASIS
    from app.reporting.scheme_reconciliation import (
        FactPosition, ResolvedApplication, resolve_planning_role, ROLE_RESERVED_MATTERS,
    )
    outline = Application(id=1, council_code="testcouncil", reference="OUT/345898/20", site_id=SITE, application_type="Outline",
                          proposal="Outline application for up to 400 dwellings", status="Decided", decision="Approved")
    rm = Application(id=2, council_code="testcouncil", reference="RES/2", site_id=SITE,
                     application_type="Approval of Reserved Matters",
                     proposal="Reserved matters for Phase 1 pursuant to outline planning permission OUT/345898/20",
                     status="Decided", decision="Approved")
    resolved = [ResolvedApplication(application=a, role=resolve_planning_role(a), decided_state="approved", scope_type="whole_site",
                                    scope_label="Whole site") for a in (outline, rm)]
    assert resolved[1].role == ROLE_RESERVED_MATTERS == sr.ROLE_RESERVED_MATTERS

    def position(res, scope, label, value):
        return FactPosition(value=value, application_id=res.id, application_reference=res.reference, planning_role=res.role,
                            decided_state=res.decided_state, scope_type=scope, scope_label=label, decision_date=None,
                            status_verified_at=None, independently_verified=False, relationship_level="exact", relationship_method=None)

    parent_count = assess_positions([position(resolved[0], "whole_site", "Whole site", 400)], scope_type="whole_site",
                                    scope_label="Whole site", subject_id=f"site:{SITE}:whole_site:Whole site", basis=OPERATIVE_APPROVED_BASIS)
    child_count = assess_positions([position(resolved[1], "phase", "Phase 1", 140)], scope_type="phase", scope_label="Phase 1",
                                   subject_id=f"site:{SITE}:phase:Phase 1", basis=OPERATIVE_APPROVED_BASIS)
    # the adapter reads these from the REAL shapes (ResolvedApplication delegates to the nested ORM Application)
    assert sr._field(resolved[1], "site_id") == SITE and sr._field(resolved[1], "council_code") == "testcouncil"
    assert "pursuant" in sr._field(resolved[1], "proposal") and sr._field(resolved[1], "reference") == "RES/2"
    result = derive_containment(child_count, [parent_count], resolved)
    assert result.reason == sr.REASON_QUALIFIED
    assert result.relationship.parent_subject_id == f"site:{SITE}:whole_site:Whole site"
    assert result.relationship.parent_application_reference == "OUT/345898/20"
