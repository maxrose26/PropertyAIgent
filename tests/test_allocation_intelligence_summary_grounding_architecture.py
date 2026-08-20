"""AI Allocation Intelligence Summary - Evidence-Grounded Validation
Architecture Amendment tests.

Proves the validator now distinguishes MATERIAL FACTUAL CLAIMS (numbers,
Application references, statuses, decisions, entities, roles, Site scope)
from ordinary AI synthesis/connective language - and that it validates
PAIRED claims (reference+status+decision, name+role+site_scope), not
three independent flat allow-lists, so a genuinely fabricated or
mismatched pairing is still rejected.

Root-cause regression: fragments such as "084620" (from Application
reference "DC/084620") and "2024" (from "PA/2024/0749" or a decision
date) were previously rejected as "unsupported numbers" purely because
they are digit-substrings of an already-grounded string. This file
proves that no longer happens, while an actually-invented number/
reference/entity/role/decision is still rejected.

No real OpenAI call anywhere - fake structured_output dicts stand in for
a model response, matching the established pattern from
tests/test_allocation_intelligence_summary.py."""
from __future__ import annotations

from app.db.models import (
    AllocationSiteRelationship, Application, Council, ControlRelationship, LocalPlan, LocalPlanSite,
    SchemeIntelligence, Site,
)
from app.reporting.allocation_intelligence_summary import (
    build_allocation_context, build_summary_prompt, generate_allocation_intelligence_summary,
    get_allocation_summary, validate_summary_output,
)


def _make_council(session, code="testcouncil") -> None:
    if session.get(Council, code) is None:
        session.add(Council(code=code, name=code.title(), base_url="https://example.invalid",
                             date_field_mode="received", doc_system="idox"))
        session.commit()


def _make_plan(session, council_code="testcouncil", status="adopted") -> LocalPlan:
    plan = LocalPlan(council_code=council_code, plan_name="Test Local Plan", status=status, raw_status=status)
    session.add(plan)
    session.commit()
    return plan


def _make_allocation(session, plan, *, council_code="testcouncil", policy_reference="REF-1",
                      site_name="Test Allocation", minimum_dwellings=300) -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code=council_code, local_plan_id=plan.id, policy_reference=policy_reference, site_name=site_name,
        plan_name="Test Local Plan", plan_status="adopted", minimum_dwellings=minimum_dwellings, intended_use="residential",
    )
    session.add(allocation)
    session.commit()
    return allocation


def _make_site(session, address="Test Site", council_code="testcouncil") -> Site:
    site = Site(council_code=council_code, canonical_address=address.lower(), display_address=address)
    session.add(site)
    session.commit()
    return site


def _make_relationship(session, *, allocation_id, site_id, review_status="auto_applied") -> AllocationSiteRelationship:
    rel = AllocationSiteRelationship(allocation_id=allocation_id, site_id=site_id, evidence_basis="document_confirmed_site", review_status=review_status)
    session.add(rel)
    session.commit()
    return rel


def _make_app(session, site_id, reference, *, units=None, status=None, decision=None, decision_issued_date=None,
              application_category=None, complete=True, council_code="testcouncil") -> Application:
    app = Application(council_code=council_code, reference=reference, site_id=site_id, status=status, decision=decision,
                       decision_issued_date=decision_issued_date, application_category=application_category)
    session.add(app)
    session.commit()
    if units is not None:
        session.add(SchemeIntelligence(application_id=app.id, total_units_final=units, core_intelligence_complete=complete))
        session.commit()
    return app


def _make_control_relationship(session, *, site_id, application_id, entity_name_raw, role="OWNER",
                                evidence_category="S106_DEFINED_OWNER", review_status="auto_applied") -> ControlRelationship:
    cr = ControlRelationship(
        site_id=site_id, application_id=application_id, entity_name_raw=entity_name_raw, entity_type="company",
        role=role, evidence_basis="s106_defined_role", evidence_category=evidence_category,
        extraction_method="deterministic_regex", review_status=review_status,
    )
    session.add(cr)
    session.commit()
    return cr


class _FakeResponse:
    def __init__(self, output_text: str):
        import json
        self.output_text = json.dumps(output_text) if isinstance(output_text, dict) else output_text


def _fake_client(structured_output: dict):
    class _Responses:
        def create(self, model, input, text):
            return _FakeResponse(structured_output)
    client = type("FakeClient", (), {})()
    client.responses = _Responses()
    return client


def _heald_green_style_fixture(session):
    """Mirrors the real Heald Green West production case that surfaced
    the original bug reports: representative Application DC/084620,
    granted, with a decision date containing "2024", plus other grouped
    Applications."""
    _make_council(session, "stockport")
    plan = _make_plan(session, council_code="stockport", status="draft")
    allocation = _make_allocation(session, plan, council_code="stockport", policy_reference="HOM 2.33",
                                   site_name="Heald Green West", minimum_dwellings=750)
    site = _make_site(session, "Land At Wilmslow Road Heald Green Stockport", council_code="stockport")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="confirmed")
    _make_app(session, site.id, "DC/084620", units=124, status="Decided", decision="Granted",
              decision_issued_date="Thu 11 Jan 2024", application_category="reserved_matters", council_code="stockport")
    for i in range(3):
        _make_app(session, site.id, f"DC/09000{i}", status="Decided", decision="Discharge Of Conditions",
                   application_category="condition_discharge_or_details", council_code="stockport")
    session.commit()
    return allocation


def _boothstown_style_fixture(session):
    """Mirrors the real East of Boothstown production case: representative
    Application PA/2024/0749, still under consultation, decision None."""
    _make_council(session, "salford")
    plan = _make_plan(session, council_code="salford")
    allocation = _make_allocation(session, plan, council_code="salford", policy_reference="JPA 25",
                                   site_name="East of Boothstown", minimum_dwellings=300)
    site = _make_site(session, "Land East Of Boothstown, Salford", council_code="salford")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    _make_app(session, site.id, "23/81742/HYBEIA", status="Closed", decision="Withdrawn",
              application_category="primary_residential", complete=False, council_code="salford")
    _make_app(session, site.id, "PA/2024/0749", units=282, status="Under Consultation", decision=None,
              application_category="outline_application", council_code="salford")
    session.commit()
    return allocation


# ---------------------------------------------------------------------------
# A. Grounded natural language / AI freedom
# ---------------------------------------------------------------------------


def test_synthesis_with_words_not_in_context_is_not_rejected(session):
    allocation = _boothstown_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "Substantial identified activity, but permission not yet secured",
        "overview": (
            "This allocation shows limited certainty despite an apparently high level of identified "
            "activity. The current evidence suggests planning activity is at an early stage, and further "
            "investigation should focus on monitoring the outcome of the pending application before "
            "treating this capacity as reliably deliverable."
        ),
        "key_points": ["Planning activity is well advanced relative to the allocation's scale.",
                       "This is a material point for a land buyer to investigate."],
        "key_uncertainties": ["The available evidence indicates the outcome remains undetermined."],
        "investigation_priorities": ["Monitor progress of the application referenced above."],
        "referenced_applications": [
            {"reference": "PA/2024/0749", "claimed_status": "Under Consultation", "claimed_decision": ""},
        ],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_investigation_priority_language_generated_naturally_passes(session):
    allocation = _boothstown_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "Notable planning activity identified",
        "overview": "The allocation has attracted meaningful attention from a promoter.",
        "key_points": ["A live planning application is under consideration."],
        "key_uncertainties": [],
        "investigation_priorities": [
            "Establish whether the outline consent, once determined, will proceed to reserved matters promptly.",
            "Confirm whether any conditions attached to a future grant would affect deliverable timescales.",
        ],
        "referenced_applications": [{"reference": "PA/2024/0749", "claimed_status": "", "claimed_decision": ""}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_several_semantically_equivalent_summaries_all_pass(session):
    """Section 19H - the same grounded facts, phrased very differently
    each time, must all pass. This proves the validator checks facts, not
    sentence templates."""
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)

    variants = [
        "Of the allocation's 750-home capacity, 124 homes are already accounted for via a granted reserved "
        "matters consent, leaving 626 homes as indicative residual capacity not yet linked to any identified scheme.",

        "This allocation totals approximately 750 homes. Identified planning activity - principally a granted "
        "application for 124 units - covers only a modest share of that figure, so a substantial 626-home "
        "portion remains outside any confirmed planning activity.",

        "With 124 of the allocation's 750 homes already the subject of a granted permission, the remaining "
        "626 homes have no linked planning activity identified against them at this stage.",
    ]
    for overview_text in variants:
        output = {
            "headline": "Partial coverage, majority of capacity remains unlinked",
            "overview": overview_text,
            "key_points": ["124 homes are covered by a granted application.", "626 homes remain indicative residual."],
            "key_uncertainties": [],
            "investigation_priorities": [],
            "referenced_applications": [{"reference": "DC/084620", "claimed_status": "Decided", "claimed_decision": "Granted"}],
            "referenced_entities": [],
        }
        is_valid, problems = validate_summary_output(context, output)
        assert is_valid is True, (overview_text, problems)


# ---------------------------------------------------------------------------
# B. Application references (the reported bug's own regression tests)
# ---------------------------------------------------------------------------


def test_heald_green_representative_reference_accepted_in_prose(session):
    """Direct regression for the reported "084620" false rejection - the
    reference appears literally in the overview PROSE text (not just the
    structured self-report), and must not be flagged."""
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "Reserved matters granted for part of the allocation",
        "overview": "Application DC/084620 was granted, covering 124 of the allocation's 750 homes.",
        "key_points": ["DC/084620 was granted."],
        "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/084620", "claimed_status": "Decided", "claimed_decision": "Granted"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_boothstown_representative_reference_with_year_accepted_in_prose(session):
    """Direct regression for the reported "2024"/"0749" false rejections."""
    allocation = _boothstown_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "Outline application under consultation",
        "overview": "PA/2024/0749 remains under consultation and has not yet been determined.",
        "key_points": ["PA/2024/0749 is under consultation."],
        "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "PA/2024/0749", "claimed_status": "Under Consultation", "claimed_decision": ""}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_multiple_grounded_references_accepted(session):
    """PA/2024/0749 is the Site's representative Application (complete
    scheme intelligence, most recent) and so carries a groundable status/
    decision; 23/81742/HYBEIA is a secondary, non-representative
    reference - its bare reference is trusted (application_references),
    but no PER-REFERENCE status/decision fact exists in context for it
    to ground a status/decision CLAIM against (see build_allocation_
    context's own representative-Application design) - so it is only
    referenced by its bare reference here, with no status/decision
    claimed for it."""
    allocation = _boothstown_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "Two applications relate to this Site",
        "overview": "23/81742/HYBEIA was an earlier application; PA/2024/0749, a replacement outline application, remains under consultation.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [
            {"reference": "23/81742/HYBEIA", "claimed_status": "", "claimed_decision": ""},
            {"reference": "PA/2024/0749", "claimed_status": "Under Consultation", "claimed_decision": ""},
        ],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_invented_reference_rejected(session):
    allocation = _boothstown_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "PA/2099/9999", "claimed_status": "", "claimed_decision": ""}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False
    assert any("PA/2099/9999" in p for p in problems)


def test_subtly_altered_reference_rejected(session):
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/084621", "claimed_status": "", "claimed_decision": ""}],  # off by one
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False
    assert any("DC/084621" in p for p in problems)


def test_reference_belonging_only_to_rejected_relationship_rejected(session):
    _make_council(session, "oldham")
    plan = _make_plan(session, council_code="oldham")
    allocation = _make_allocation(session, plan, council_code="oldham", policy_reference="JPA 10",
                                   site_name="Beal Valley", minimum_dwellings=480)
    site = _make_site(session, "Land South Of Bullcote Lane, Oldham", council_code="oldham")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="rejected")
    _make_app(session, site.id, "FUL/355603/26", units=248, status="Decided", decision="Granted", council_code="oldham")
    session.commit()

    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "FUL/355603/26", "claimed_status": "Decided", "claimed_decision": "Granted"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False
    assert any("FUL/355603/26" in p for p in problems)


def test_reference_belonging_only_to_needs_confirmation_evidence_rejected(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="needs_confirmation")
    _make_app(session, site.id, "APP/DISPUTED", units=250, status="Under Consultation")
    session.commit()

    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "APP/DISPUTED", "claimed_status": "Under Consultation", "claimed_decision": ""}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False
    assert any("APP/DISPUTED" in p for p in problems)


def test_unrelated_allocation_application_reference_rejected(session):
    allocation = _boothstown_style_fixture(session)
    unrelated_site = _make_site(session, "Somewhere Else Entirely")
    _make_app(session, unrelated_site.id, "UNRELATED/1/1", units=999, status="Decided", decision="Granted")
    session.commit()

    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "UNRELATED/1/1", "claimed_status": "", "claimed_decision": ""}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False
    assert any("UNRELATED/1/1" in p for p in problems)


# ---------------------------------------------------------------------------
# C. Numbers
# ---------------------------------------------------------------------------


def test_grounded_capacities_accepted(session):
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x",
        "overview": "The allocation totals 750 homes; 124 are identified, leaving 626 as indicative residual.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_other_applications_by_category_counts_accepted(session):
    """Regression: the bounded "Plus N further Application(s)..." counts
    were not previously in the allowed-numbers set at all."""
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x",
        "overview": "A further 3 applications relate to this Site, all discharge-of-conditions filings.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_decision_date_digits_accepted(session):
    """Regression: "2024" from a decision_issued_date narrated in prose."""
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x",
        "overview": "The representative application was granted on 11 Jan 2024.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_invented_number_rejected(session):
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "This allocation could deliver up to 12345 homes.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False
    assert any("12345" in p for p in problems)


def test_changed_residual_capacity_rejected(session):
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    # Real residual is 626 - claim a different, wrong figure.
    output = {
        "headline": "x", "overview": "The indicative residual allocation capacity is 555 homes.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False
    assert any("555" in p for p in problems)


def test_ai_cannot_silently_recompute_contradictory_residual(session):
    """750 - 124 = 626 is the correct, given residual. An AI-recomputed
    value that happens to look plausible but does not match the
    deterministic figure must still be rejected."""
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "750 minus 124 leaves approximately 620 homes unaccounted for.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False
    assert any("620" in p for p in problems)


# ---------------------------------------------------------------------------
# D. Status / decision grounding
# ---------------------------------------------------------------------------


def test_grounded_status_and_decision_accepted(session):
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "DC/084620 was decided and granted.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/084620", "claimed_status": "Decided", "claimed_decision": "Granted"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_invented_permission_rejected(session):
    """The Boothstown application's real decision is None (still under
    consultation) - claiming "Granted" must be rejected."""
    allocation = _boothstown_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "PA/2024/0749 has been granted permission.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "PA/2024/0749", "claimed_status": "", "claimed_decision": "Granted"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False
    assert any("Granted" in p and "PA/2024/0749" in p for p in problems)


def test_under_consultation_cannot_become_granted(session):
    allocation = _boothstown_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "PA/2024/0749", "claimed_status": "Granted", "claimed_decision": ""}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_refused_cannot_become_granted(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    _make_app(session, site.id, "APP/REFUSED", units=100, status="Decided", decision="Refuse")
    session.commit()

    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "APP/REFUSED", "claimed_status": "", "claimed_decision": "Granted"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_withdrawn_cannot_become_live_permission(session):
    allocation = _boothstown_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "23/81742/HYBEIA", "claimed_status": "", "claimed_decision": "Granted"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_status_claim_for_non_representative_reference_rejected(session):
    """A status/decision fact can only be grounded for the ONE
    representative Application per Site - a claim attached to a
    secondary (grouped-count-only) reference has nothing to ground it
    against, even though the bare reference itself might be trusted
    elsewhere."""
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    # DC/090000 is one of the "other" (non-representative) Applications -
    # its reference is trusted, but no per-reference status exists for it.
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/090000", "claimed_status": "Decided", "claimed_decision": ""}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


# ---------------------------------------------------------------------------
# E. Entity / role grounding
# ---------------------------------------------------------------------------


def _ownership_fixture(session, *, role, evidence_category, entity_name_raw="Test Entity Ltd"):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    app = _make_app(session, site.id, "APP/ROLE", units=100)
    _make_control_relationship(session, site_id=site.id, application_id=app.id, entity_name_raw=entity_name_raw,
                                role=role, evidence_category=evidence_category)
    session.commit()
    return allocation


def test_grounded_entity_and_role_accepted(session):
    allocation = _ownership_fixture(session, role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "Test Entity Ltd is named as S106 Developer for the identified Site.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "Test Entity Ltd", "role": "S106 Developer", "site_scope": 'Site "Test Site"'}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_invented_entity_rejected(session):
    allocation = _ownership_fixture(session, role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "Completely Invented Ltd", "role": "S106 Developer", "site_scope": 'Site "Test Site"'}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_applicant_not_promoted_to_developer(session):
    """The entity's real role_label is "Applicant evidence" - self-
    reporting the SAME entity with role "S106 Developer" must be
    rejected, even though both the entity name AND the role string
    independently exist somewhere in context for OTHER entities/roles."""
    allocation = _ownership_fixture(session, role="APPLICANT", evidence_category="SOME_OTHER_CATEGORY")
    context = build_allocation_context(session, allocation)
    real_role = context.ownership_entities[0].role_label
    assert real_role == "Applicant evidence"
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "Test Entity Ltd", "role": "S106 Developer", "site_scope": 'Site "Test Site"'}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_planning_ownership_declaration_not_promoted_to_current_owner(session):
    allocation = _ownership_fixture(session, role="OWNER", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION")
    context = build_allocation_context(session, allocation)
    real_role = context.ownership_entities[0].role_label
    assert real_role == "Planning ownership declaration"
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "Test Entity Ltd", "role": "current owner", "site_scope": 'Site "Test Site"'}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_site_scope_widened_to_allocation_rejected(session):
    """The entity is evidenced only for a named Site - self-reporting a
    generic "the allocation" scope (or any scope other than the exact
    one given) must be rejected."""
    allocation = _ownership_fixture(session, role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "Test Entity Ltd", "role": "S106 Developer", "site_scope": "the allocation"}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_site_scope_swapped_to_wrong_site_rejected(session):
    """Two Sites, two entities, each with their OWN correct role and
    scope - swapping which Site an entity is claimed for must be
    rejected even though every individual string (both entity names,
    both roles, both scopes) independently exists in context."""
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=1000)
    site_a = _make_site(session, "Site A")
    site_b = _make_site(session, "Site B")
    _make_relationship(session, allocation_id=allocation.id, site_id=site_a.id)
    _make_relationship(session, allocation_id=allocation.id, site_id=site_b.id)
    app_a = _make_app(session, site_a.id, "APP/A", units=100)
    app_b = _make_app(session, site_b.id, "APP/B", units=100)
    _make_control_relationship(session, site_id=site_a.id, application_id=app_a.id, entity_name_raw="Company A Ltd",
                                role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    _make_control_relationship(session, site_id=site_b.id, application_id=app_b.id, entity_name_raw="Company B Ltd",
                                role="OWNER", evidence_category="S106_DEFINED_OWNER")
    session.commit()

    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        # Company A Ltd really belongs to Site A, not Site B.
        "referenced_entities": [{"name": "Company A Ltd", "role": "S106 Developer", "site_scope": 'Site "Site B"'}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_council_and_local_plan_name_self_reported_as_entity_not_rejected(session):
    """Direct regression for a REAL bug found in production evidence
    during this amendment's own investigation: a genuine prior generation
    attempt self-reported "Oldham Council" and "Places for Everyone Joint
    Development Plan" as if they were ownership entities - both are true,
    already-given context facts, just mis-bucketed, not a hallucination.
    Must not cause rejection."""
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [
            {"name": context.council_name, "role": "", "site_scope": ""},
            {"name": context.local_plan_name, "role": "", "site_scope": ""},
        ],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


# ---------------------------------------------------------------------------
# F. Trust boundary at the validator level
# ---------------------------------------------------------------------------


def test_needs_confirmation_ownership_cannot_be_grounded(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="needs_confirmation")
    app = _make_app(session, site.id, "APP/1", units=100)
    _make_control_relationship(session, site_id=site.id, application_id=app.id, entity_name_raw="Disputed Developer Ltd",
                                role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    session.commit()

    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "Disputed Developer Ltd", "role": "S106 Developer", "site_scope": 'Site "Test Site"'}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_mixed_trusted_and_disputed_only_trusted_reference_grounds(session):
    allocation_id_context = None
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=1000)
    trusted_site = _make_site(session, "Trusted Site")
    disputed_site = _make_site(session, "Disputed Site")
    _make_relationship(session, allocation_id=allocation.id, site_id=trusted_site.id, review_status="auto_applied")
    _make_relationship(session, allocation_id=allocation.id, site_id=disputed_site.id, review_status="needs_confirmation")
    _make_app(session, trusted_site.id, "APP/TRUSTED", units=200, status="Decided", decision="Granted")
    _make_app(session, disputed_site.id, "APP/DISPUTED", units=500, status="Under Consultation")
    session.commit()

    context = build_allocation_context(session, allocation)

    trusted_only = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "APP/TRUSTED", "claimed_status": "Decided", "claimed_decision": "Granted"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, trusted_only)
    assert is_valid is True, problems

    both = dict(trusted_only)
    both["referenced_applications"] = trusted_only["referenced_applications"] + [
        {"reference": "APP/DISPUTED", "claimed_status": "Under Consultation", "claimed_decision": ""}
    ]
    is_valid, problems = validate_summary_output(context, both)
    assert is_valid is False


# ---------------------------------------------------------------------------
# G. Failure / preservation behaviour (full orchestration, not just the validator)
# ---------------------------------------------------------------------------


def test_genuinely_unsupported_claim_rejects_via_full_orchestration(session):
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    bad_output = {
        "headline": "x", "overview": "This allocation could deliver up to 99999 homes.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    client = _fake_client(bad_output)
    result = generate_allocation_intelligence_summary(session, client, allocation)
    assert result.rejected is True
    summary = get_allocation_summary(session, allocation.id)
    assert summary.headline is None  # never published
    assert summary.status == "error"


def test_grounded_claim_with_paired_status_decision_persists_via_full_orchestration(session):
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    good_output = {
        "headline": "Reserved matters granted for part of the allocation",
        "overview": "DC/084620 was granted on 11 Jan 2024, covering 124 of the allocation's 750 homes; "
                    "626 homes remain indicative residual, and a further 3 applications relate to this Site.",
        "key_points": ["124 homes are covered by a granted application."],
        "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/084620", "claimed_status": "Decided", "claimed_decision": "Granted"}],
        "referenced_entities": [],
    }
    client = _fake_client(good_output)
    result = generate_allocation_intelligence_summary(session, client, allocation)
    assert result.regenerated is True, result.rejection_reason
    summary = get_allocation_summary(session, allocation.id)
    assert summary.headline == good_output["headline"]
    assert summary.status == "ok"


# ---------------------------------------------------------------------------
# Prompt sanity - the new self-report structure and AI-freedom framing
# ---------------------------------------------------------------------------


def test_prompt_grants_explicit_synthesis_freedom(session):
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    prompt = build_summary_prompt(context)
    assert "genuine synthesis" in prompt.lower()
    assert "not restricted to a fixed vocabulary" in prompt.lower()


def test_prompt_describes_paired_self_report_structure(session):
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    prompt = build_summary_prompt(context)
    assert "referenced_applications" in prompt
    assert "referenced_entities" in prompt
    assert "claimed_status" in prompt
    assert "site_scope" in prompt
