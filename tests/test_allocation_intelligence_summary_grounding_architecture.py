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

from sqlalchemy import select

from app.db.models import (
    AllocationSiteRelationship, Application, Council, ControlRelationship, LocalPlan, LocalPlanSite,
    SchemeIntelligence, Site,
)
from app.reporting.allocation_intelligence_summary import (
    build_allocation_context, build_summary_prompt, compute_context_fingerprint, generate_allocation_intelligence_summary,
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
              application_category=None, complete=True, council_code="testcouncil", applicant_name_raw=None) -> Application:
    app = Application(council_code=council_code, reference=reference, site_id=site_id, status=status, decision=decision,
                       decision_issued_date=decision_issued_date, application_category=application_category,
                       applicant_name_raw=applicant_name_raw)
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


# ---------------------------------------------------------------------------
# I. Applicant party evidence (Allocation Party Evidence Amendment)
# ---------------------------------------------------------------------------


def _applicant_fixture(session, *, applicant_name_raw, site_review_status="auto_applied", council_code="testcouncil"):
    _make_council(session, council_code)
    plan = _make_plan(session, council_code=council_code)
    allocation = _make_allocation(session, plan, council_code=council_code, minimum_dwellings=300)
    site = _make_site(session, council_code=council_code)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status=site_review_status)
    _make_app(session, site.id, "APP/APPLICANT", units=100, status="Decided", decision="Granted",
              applicant_name_raw=applicant_name_raw, council_code=council_code)
    session.commit()
    return allocation


def test_applicant_reaches_allocation_intelligence_context(session):
    """A/B/H/I/J from the investigation - the raw, deterministic Application.
    applicant_name_raw genuinely reaches AllocationIntelligenceContext now,
    via context.applicant_evidence (aggregated across the Site's trusted
    linked Applications, not scoped to RepresentativeApplicationDetail -
    Multi-Application Party Intelligence)."""
    allocation = _applicant_fixture(session, applicant_name_raw="Bloor Homes North West")
    context = build_allocation_context(session, allocation)
    assert len(context.applicant_evidence) == 1
    evidence = context.applicant_evidence[0]
    assert evidence.entity_name == "Bloor Homes North West"
    assert evidence.application_references == ["APP/APPLICANT"]
    # The representative Application itself carries no applicant field at
    # all any more - capacity/status/decision stay its sole responsibility
    # (Section 2).
    assert not hasattr(context.sites[0].representative_application, "applicant_name")


def test_applicant_placeholder_value_cleaned_to_none(session):
    """Direct regression for real production data - DC/060928 on the Heald
    Green West sample carries the literal portal placeholder "Not
    Available", which must not be treated as a real applicant name."""
    allocation = _applicant_fixture(session, applicant_name_raw="Not Available")
    context = build_allocation_context(session, allocation)
    assert context.applicant_evidence == []


def test_non_representative_applicant_reaches_party_context(session):
    """Section 1's own reported product weakness, directly reproduced:
    Heald Green West's representative Application has a blank applicant,
    but a DIFFERENT trusted linked Application on the SAME Site names
    Bloor Homes North West - that evidence must now reach context even
    though it is never the representative Application."""
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=750)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    # Representative (largest/most authoritative) Application - blank applicant.
    _make_app(session, site.id, "DC/084620", units=124, status="Decided", decision="Granted",
              application_category="reserved_matters", applicant_name_raw=None)
    # A different, non-representative, trusted Application on the SAME Site.
    _make_app(session, site.id, "DC/078180", status="Decided", decision="Granted",
              application_category="reserved_matters", applicant_name_raw="Bloor Homes North West")
    session.commit()

    context = build_allocation_context(session, allocation)
    assert context.sites[0].representative_application.reference == "DC/084620"
    assert len(context.applicant_evidence) == 1
    evidence = context.applicant_evidence[0]
    assert evidence.entity_name == "Bloor Homes North West"
    assert evidence.application_references == ["DC/078180"]


def test_same_applicant_across_multiple_applications_deduplicates(session):
    """Section 5 - Bloor Homes North West appearing on three Applications
    for the same Site must be ONE entity with three supporting references,
    not three unrelated entries."""
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    _make_app(session, site.id, "APP/1", units=100, applicant_name_raw="Bloor Homes North West")
    _make_app(session, site.id, "APP/2", applicant_name_raw="Bloor Homes North West")
    _make_app(session, site.id, "APP/3", applicant_name_raw="Bloor Homes North West")
    session.commit()

    context = build_allocation_context(session, allocation)
    assert len(context.applicant_evidence) == 1
    evidence = context.applicant_evidence[0]
    assert evidence.entity_name == "Bloor Homes North West"
    assert evidence.application_references == ["APP/1", "APP/2", "APP/3"]
    assert evidence.application_count == 3


def test_different_applicants_on_same_site_remain_separate(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    _make_app(session, site.id, "APP/1", units=100, applicant_name_raw="Bloor Homes North West")
    _make_app(session, site.id, "APP/2", applicant_name_raw="Persimmon Homes Ltd")
    session.commit()

    context = build_allocation_context(session, allocation)
    names = {e.entity_name for e in context.applicant_evidence}
    assert names == {"Bloor Homes North West", "Persimmon Homes Ltd"}
    by_name = {e.entity_name: e.application_references for e in context.applicant_evidence}
    assert by_name["Bloor Homes North West"] == ["APP/1"]
    assert by_name["Persimmon Homes Ltd"] == ["APP/2"]


def test_applicant_remains_applicant_regardless_of_frequency(session):
    """Section 3 - appearing on 10 Applications is still only Applicant
    evidence, never promoted by frequency alone."""
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    for i in range(10):
        _make_app(session, site.id, f"APP/{i}", applicant_name_raw="Frequent Applicant Ltd")
    session.commit()

    context = build_allocation_context(session, allocation)
    assert len(context.applicant_evidence) == 1
    evidence = context.applicant_evidence[0]
    assert evidence.application_count == 10
    output = {
        "headline": "x", "overview": "Frequent Applicant Ltd is named as applicant on 10 linked applications.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{
            "name": "Frequent Applicant Ltd", "role": "Applicant", "site_scope": 'Site "Test Site"',
            "application_reference": "",
        }],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems
    # Promoting it to Developer, however many Applications it appears on, is still rejected.
    promoted = dict(output)
    promoted["referenced_entities"] = [{
        "name": "Frequent Applicant Ltd", "role": "S106 Developer", "site_scope": 'Site "Test Site"',
        "application_reference": "",
    }]
    is_valid, problems = validate_summary_output(context, promoted)
    assert is_valid is False


def test_specific_application_reference_claim_must_match_evidence(session):
    """Section 8 - a self-report naming ONE specific supporting Application
    for an applicant claim must genuinely be one of its own references."""
    allocation = _applicant_fixture(session, applicant_name_raw="Bloor Homes North West")
    context = build_allocation_context(session, allocation)
    good = {
        "headline": "x", "overview": "Bloor Homes North West is named as applicant on APP/APPLICANT.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "APP/APPLICANT", "claimed_status": "", "claimed_decision": ""}],
        "referenced_entities": [{
            "name": "Bloor Homes North West", "role": "Applicant", "site_scope": 'Site "Test Site"',
            "application_reference": "APP/APPLICANT",
        }],
    }
    is_valid, problems = validate_summary_output(context, good)
    assert is_valid is True, problems

    bad = dict(good)
    bad["referenced_entities"] = [{
        "name": "Bloor Homes North West", "role": "Applicant", "site_scope": 'Site "Test Site"',
        "application_reference": "APP/DOES-NOT-EXIST",
    }]
    is_valid, problems = validate_summary_output(context, bad)
    assert is_valid is False


def test_applicant_role_label_is_exactly_applicant(session):
    """Section 5's mandated exact wording - not "Applicant evidence" (the
    unrelated app.reporting.ownership_control fallback label used only if a
    ControlRelationship APPLICANT-role row ever exists - a separate,
    still-hypothetical pathway with no real writer today)."""
    allocation = _applicant_fixture(session, applicant_name_raw="Bloor Homes North West")
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "Bloor Homes North West is named as applicant for the identified Site.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "Bloor Homes North West", "role": "Applicant", "site_scope": 'Site "Test Site"'}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_applicant_cannot_become_developer_without_evidence(session):
    """Section 5/9's central requirement - a real applicant, with no
    separate Developer-role evidence for the same entity, must be rejected
    if self-reported as Developer. The entity name AND the role string
    "S106 Developer" both independently exist in the platform's vocabulary
    - only the exact (name, role, scope) triple is checked."""
    allocation = _applicant_fixture(session, applicant_name_raw="Bloor Homes North West")
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "Bloor Homes North West", "role": "S106 Developer", "site_scope": 'Site "Test Site"'}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_agent_cannot_become_developer(session):
    """A ControlRelationship AGENT-role row (schema-supported, no real
    writer in production today - see investigation D/M) grounds as "Agent
    evidence" only; self-reporting the same entity as Developer must be
    rejected."""
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    app = _make_app(session, site.id, "APP/AGENT", units=100)
    _make_control_relationship(session, site_id=site.id, application_id=app.id, entity_name_raw="Some Agent LLP",
                                role="AGENT", evidence_category="UNMODELLED_AGENT_EVIDENCE")
    session.commit()
    context = build_allocation_context(session, allocation)
    real_role = context.ownership_entities[0].role_label
    assert real_role == "Agent evidence"
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "Some Agent LLP", "role": "S106 Developer", "site_scope": 'Site "Test Site"'}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_explicit_promoter_evidence_grounds_correctly(session):
    """PROMOTER is reserved vocabulary (investigation D/M) with no real
    writer today - proves the SAME validation mechanism grounds it
    correctly if/when evidence exists, with no promoter-specific code
    required."""
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    app = _make_app(session, site.id, "APP/PROMOTER", units=100)
    _make_control_relationship(session, site_id=site.id, application_id=app.id, entity_name_raw="Land Promotions Ltd",
                                role="PROMOTER", evidence_category="UNMODELLED_PROMOTER_EVIDENCE")
    session.commit()
    context = build_allocation_context(session, allocation)
    real_role = context.ownership_entities[0].role_label
    assert real_role == "Promoter evidence"
    output = {
        "headline": "x", "overview": "Land Promotions Ltd is named as promoter for the identified Site.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "Land Promotions Ltd", "role": "Promoter evidence", "site_scope": 'Site "Test Site"'}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_applicant_and_developer_can_coexist_for_different_entities(session):
    """The SAME Site can legitimately show one entity as Applicant and a
    DIFFERENT entity as S106 Developer - both ground correctly, neither
    borrows the other's role."""
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    app = _make_app(session, site.id, "APP/BOTH", units=100, status="Decided", decision="Granted",
                     applicant_name_raw="Volume Housebuilder Ltd")
    _make_control_relationship(session, site_id=site.id, application_id=app.id, entity_name_raw="Deed Developer Ltd",
                                role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    session.commit()
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [
            {"name": "Volume Housebuilder Ltd", "role": "Applicant", "site_scope": 'Site "Test Site"'},
            {"name": "Deed Developer Ltd", "role": "S106 Developer", "site_scope": 'Site "Test Site"'},
        ],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems
    # Swapping the roles between the two entities must still be rejected.
    swapped = dict(output)
    swapped["referenced_entities"] = [
        {"name": "Volume Housebuilder Ltd", "role": "S106 Developer", "site_scope": 'Site "Test Site"'},
        {"name": "Deed Developer Ltd", "role": "Applicant", "site_scope": 'Site "Test Site"'},
    ]
    is_valid, problems = validate_summary_output(context, swapped)
    assert is_valid is False


def test_applicant_site_scope_cannot_be_swapped(session):
    """Two Sites, two different applicants - claiming one applicant for
    the OTHER Site's scope must be rejected, exactly like ownership/control
    scope-swapping."""
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=1000)
    site_a = _make_site(session, "Site A")
    site_b = _make_site(session, "Site B")
    _make_relationship(session, allocation_id=allocation.id, site_id=site_a.id)
    _make_relationship(session, allocation_id=allocation.id, site_id=site_b.id)
    _make_app(session, site_a.id, "APP/A", units=100, applicant_name_raw="Applicant A Ltd")
    _make_app(session, site_b.id, "APP/B", units=100, applicant_name_raw="Applicant B Ltd")
    session.commit()

    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "Applicant A Ltd", "role": "Applicant", "site_scope": 'Site "Site B"'}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_applicant_excluded_for_disputed_site_relationship(session):
    """Section 7 trust boundary - a needs_confirmation AllocationSite
    Relationship must withhold applicant evidence STRUCTURALLY (None at
    construction), the same guarantee status/decision already has, not
    merely hedged in prompt text."""
    allocation = _applicant_fixture(session, applicant_name_raw="Should Not Appear Ltd", site_review_status="needs_confirmation")
    context = build_allocation_context(session, allocation)
    assert context.sites[0].representative_application is None
    # And the entity name is nowhere in the allow-set - self-reporting it
    # anyway, however hedged, is still rejected.
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "Should Not Appear Ltd", "role": "Applicant", "site_scope": 'Site "Test Site"'}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_applicant_change_alters_fingerprint(session):
    """Test #15 - a materially different applicant name must change the
    fingerprint (otherwise a corrected/newly-discovered applicant would
    never trigger regeneration)."""
    allocation_1 = _applicant_fixture(session, applicant_name_raw="Original Applicant Ltd", council_code="council1")
    fp_1 = compute_context_fingerprint(build_allocation_context(session, allocation_1))

    allocation_2 = _applicant_fixture(session, applicant_name_raw="Different Applicant Ltd", council_code="council2")
    fp_2 = compute_context_fingerprint(build_allocation_context(session, allocation_2))

    assert fp_1 != fp_2


def test_placeholder_applicant_variants_do_not_alter_fingerprint(session):
    """Test #16 - "Not Available" and a genuinely blank applicant both
    clean to None, so they must produce the SAME fingerprint (an
    irrelevant portal wording difference must never force a costly
    regeneration). Mutates the SAME underlying Application row (same
    site_id, same everything else) rather than comparing two separate
    fixtures, so site_id/allocation_id differences can never confound the
    comparison."""
    allocation = _applicant_fixture(session, applicant_name_raw="Not Available")
    fp_placeholder = compute_context_fingerprint(build_allocation_context(session, allocation))

    app = session.execute(select(Application).where(Application.reference == "APP/APPLICANT")).scalar_one()
    app.applicant_name_raw = None
    session.commit()
    fp_blank = compute_context_fingerprint(build_allocation_context(session, allocation))

    assert fp_placeholder == fp_blank


# ---------------------------------------------------------------------------
# J. Generalised trusted-identifier numeric grounding (Section 10)
# ---------------------------------------------------------------------------


def _regulation_18_fixture(session):
    """Reproduces the EXACT reported symptom: allocation reference "HOM
    2.33" and plan status label "Draft consultation (Regulation 18)" are
    both rendered verbatim in the prompt, and the model is expected to
    echo them - proving the root cause is general (any allocation whose
    own reference/plan-stage wording contains digits), not specific to one
    allocation."""
    _make_council(session, "stockport")
    plan = _make_plan(session, council_code="stockport", status="draft_consultation")
    allocation = _make_allocation(session, plan, council_code="stockport", policy_reference="HOM 2.33",
                                   site_name="Heald Green West", minimum_dwellings=750)
    site = _make_site(session, "Land At Wilmslow Road Heald Green Stockport", council_code="stockport")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="confirmed")
    _make_app(session, site.id, "DC/084620", units=124, status="Decided", decision="Granted",
              application_category="reserved_matters", council_code="stockport")
    session.commit()
    return allocation


def test_own_policy_reference_and_plan_stage_no_longer_falsely_rejected(session):
    allocation = _regulation_18_fixture(session)
    context = build_allocation_context(session, allocation)
    assert context.allocation_reference == "HOM 2.33"
    assert "Regulation 18" in context.plan_status_label
    output = {
        "headline": "x",
        "overview": (
            f"This is allocation HOM 2.33, currently at Draft consultation (Regulation 18) stage, "
            f"with 124 of its 750 homes identified via DC/084620."
        ),
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/084620", "claimed_status": "Decided", "claimed_decision": "Granted"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_invented_policy_stage_number_still_rejected(session):
    """The masking fix must not become a blanket numeric exemption - a
    fabricated figure sharing no relationship to the allocation's own
    reference/plan-stage wording is still rejected."""
    allocation = _regulation_18_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "This allocation is expected to deliver 42 additional phases beyond those identified.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


# ---------------------------------------------------------------------------
# K. Final Grounding Hardening Amendment - trusted-label SUB-PHRASE masking
#
# Real v5 production rejection, allocation 32 (Heald Green West):
# generation_error "unsupported numbers: 18" - the whole-label mask fixed
# "HOM 2.33" (context.allocation_reference, matched as prior tests in
# section J already prove) but NOT a model narrating just "Regulation 18"
# on its own, since that partial phrase never matches the FULL literal
# "Draft consultation (Regulation 18)" string that was masked. This
# section proves the root cause and the fix precisely.
# ---------------------------------------------------------------------------


def test_plan_stage_subphrase_alone_accepted(session):
    """Direct regression for the real "unsupported numbers: 18" rejection
    - the model narrates ONLY the parenthetical qualifier "Regulation 18",
    never repeating "Draft consultation", which is exactly the shape a
    real production generation used."""
    allocation = _regulation_18_fixture(session)
    context = build_allocation_context(session, allocation)
    assert context.plan_status_label == "Draft consultation (Regulation 18)"
    output = {
        "headline": "x",
        "overview": "This allocation's Local Plan is currently at Regulation 18 stage, with no adoption yet.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def _proposed_submission_fixture(session):
    """A DIFFERENT plan-stage label with its own parenthetical qualifier
    ("Regulation 19", not 18) - proves the fix generalises to the label
    SHAPE, not a hardcoded "Regulation 18" special case."""
    _make_council(session, "genericcouncil")
    plan = _make_plan(session, council_code="genericcouncil", status="proposed_submission")
    allocation = _make_allocation(session, plan, council_code="genericcouncil", policy_reference="GEN 4.1",
                                   site_name="Generic Allocation", minimum_dwellings=200)
    session.commit()
    return allocation


def test_different_plan_stage_subphrase_also_accepted(session):
    allocation = _proposed_submission_fixture(session)
    context = build_allocation_context(session, allocation)
    assert context.plan_status_label == "Proposed submission (Regulation 19)"
    output = {
        "headline": "x", "overview": "The Local Plan is at Regulation 19 stage, ahead of examination.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_invented_regulation_number_still_rejected(session):
    """The sub-phrase masking fix must not accept an INVENTED Regulation
    number that does not match the allocation's own trusted label."""
    allocation = _regulation_18_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "This Local Plan is already at Regulation 25 stage.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


# ---------------------------------------------------------------------------
# L. Null / absence decision claims (Final Grounding Hardening Amendment)
#
# Real v5 production rejection, allocation 66 (East of Boothstown):
# generation_error "unsupported decision claim for PA/2024/0749: no
# decision recorded yet" - the model made a genuinely TRUE, grounded
# absence claim (decision really is None) but had no way to self-report
# it other than putting prose into claimed_decision, which was then
# checked against the trusted decision value and failed since the trusted
# value is "" (None), not "no decision recorded yet".
# ---------------------------------------------------------------------------


def test_decision_absent_claim_grounded_when_decision_none(session):
    allocation = _boothstown_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "PA/2024/0749 remains under consultation; no decision has yet been recorded.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{
            "reference": "PA/2024/0749", "claimed_status": "Under Consultation", "claimed_decision": "",
            "decision_claim_mode": "absent",
        }],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_multiple_absence_phrasings_all_pass(session):
    """Rule 15/Section 9 - the validator grounds the MEANING of an
    absence claim, not a fixed sentence; several natural phrasings of the
    same self-reported decision_claim_mode="absent" must all pass."""
    allocation = _boothstown_style_fixture(session)
    context = build_allocation_context(session, allocation)
    phrasings = [
        "no decision has yet been issued for PA/2024/0749",
        "PA/2024/0749 remains undetermined",
        "a decision on PA/2024/0749 is still pending",
        "no formal decision has been reached on this application",
    ]
    for phrase in phrasings:
        output = {
            "headline": "x", "overview": phrase,
            "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
            "referenced_applications": [{
                "reference": "PA/2024/0749", "claimed_status": "", "claimed_decision": "",
                "decision_claim_mode": "absent",
            }],
            "referenced_entities": [],
        }
        is_valid, problems = validate_summary_output(context, output)
        assert is_valid is True, (phrase, problems)


def test_decision_absent_claim_rejected_when_decision_granted(session):
    allocation = _heald_green_style_fixture(session)  # DC/084620 decision="Granted"
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "DC/084620 has no decision recorded yet.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{
            "reference": "DC/084620", "claimed_status": "", "claimed_decision": "", "decision_claim_mode": "absent",
        }],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_decision_absent_claim_rejected_when_decision_refused(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    _make_app(session, site.id, "APP/REFUSED", units=100, status="Decided", decision="Refuse")
    session.commit()
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "APP/REFUSED is still pending a decision.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{
            "reference": "APP/REFUSED", "claimed_status": "", "claimed_decision": "", "decision_claim_mode": "absent",
        }],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_decision_absent_claim_rejected_when_decision_withdrawn(session):
    allocation = _boothstown_style_fixture(session)  # 23/81742/HYBEIA decision="Withdrawn"
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "23/81742/HYBEIA is still awaiting determination.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{
            "reference": "23/81742/HYBEIA", "claimed_status": "", "claimed_decision": "", "decision_claim_mode": "absent",
        }],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_decision_value_claim_backward_compatible_without_mode(session):
    """A legacy self-report with NO decision_claim_mode key at all (every
    real v4/v5 generation, and every pre-v6 test in this file) must keep
    behaving exactly as before: a non-empty claimed_decision is still
    checked as a positive value claim."""
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    good = {
        "headline": "x", "overview": "DC/084620 was granted.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/084620", "claimed_status": "Decided", "claimed_decision": "Granted"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, good)
    assert is_valid is True, problems

    bad = dict(good)
    bad["referenced_applications"] = [{"reference": "DC/084620", "claimed_status": "", "claimed_decision": "Refused"}]
    is_valid, problems = validate_summary_output(context, bad)
    assert is_valid is False


# ---------------------------------------------------------------------------
# M. Exact real-production-rejection regressions
# ---------------------------------------------------------------------------


def test_heald_green_west_real_v5_rejection_now_passes(session):
    """Direct regression for the exact real production generation_error:
    "unsupported numbers: 18" on allocation 32."""
    allocation = _regulation_18_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "Heald Green West shows partial coverage at an early plan stage",
        "overview": (
            "This allocation's Local Plan is currently at Regulation 18 stage, meaning it is not yet adopted. "
            "124 of the allocation's 750 homes are accounted for via DC/084620, which was granted."
        ),
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/084620", "claimed_status": "Decided", "claimed_decision": "Granted"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_east_of_boothstown_real_v5_rejection_now_passes(session):
    """Direct regression for the exact real production generation_error:
    "unsupported decision claim for PA/2024/0749: no decision recorded
    yet" on allocation 66."""
    allocation = _boothstown_style_fixture(session)
    context = build_allocation_context(session, allocation)
    assert context.indicative_residual_capacity == 18
    output = {
        "headline": "Substantial identified activity for East of Boothstown, decision pending",
        "overview": (
            "282 of the allocation's 300 homes are identified via PA/2024/0749, which remains under "
            "consultation - no decision has yet been recorded. 18 homes remain indicative residual capacity."
        ),
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{
            "reference": "PA/2024/0749", "claimed_status": "Under Consultation", "claimed_decision": "",
            "decision_claim_mode": "absent",
        }],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def _britannia_mill_style_fixture(session):
    """Mirrors the real Britannia Mill production case: single trusted
    linked Application, 26/00098/FUL, status "Awaiting decision", decision
    None; a Certificate A ownership declaration for Holmpatrick Ltd."""
    _make_council(session, "tameside")
    plan = _make_plan(session, council_code="tameside", status="preferred_options")
    allocation = _make_allocation(session, plan, council_code="tameside", policy_reference="HSP S2K: Allocation 9",
                                   site_name="Britannia Mill", minimum_dwellings=136)
    site = _make_site(session, "Britannia New Mill Queen Street Mossley Tameside OL5 9AQ", council_code="tameside")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    app = _make_app(session, site.id, "26/00098/FUL", units=49, status="Awaiting decision", decision=None,
                     application_category="primary_residential", council_code="tameside")
    _make_control_relationship(session, site_id=site.id, application_id=app.id, entity_name_raw="Holmpatrick Ltd",
                                role="OWNER", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION")
    session.commit()
    return allocation


def test_britannia_mill_fabricated_capacity_breakdown_still_rejected(session):
    """Direct regression for the real production generation_error
    "unsupported numbers: 17, 32" on allocation 196 - investigated and
    found NOT to be a masking gap (no trusted string in this allocation's
    context contains "17" or "32" in any form; 17+32=49 exactly equals
    identified_application_capacity, consistent with the model having
    fabricated a two-way split of that single figure that this context
    gives no basis for - there is only ONE linked Application, not two).
    This is correctly, deliberately still rejected - the amendment does
    NOT special-case these digits, exactly as instructed."""
    allocation = _britannia_mill_style_fixture(session)
    context = build_allocation_context(session, allocation)
    assert context.identified_application_capacity == 49
    output = {
        "headline": "x",
        "overview": "Of the 49 identified homes, 17 relate to the residential element and 32 to supporting uses.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_britannia_mill_grounded_output_still_validates(session):
    """The SAME real Britannia Mill context, narrated without inventing a
    breakdown, validates cleanly - proving the rejection above is about
    the fabricated split, not the allocation's own real figures."""
    allocation = _britannia_mill_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "Partial coverage identified for Britannia Mill",
        "overview": (
            "49 of this allocation's 136 homes are identified via 26/00098/FUL, still awaiting a decision. "
            "87 homes remain indicative residual capacity. Holmpatrick Ltd is named under a planning "
            "ownership declaration for the identified Site."
        ),
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{
            "reference": "26/00098/FUL", "claimed_status": "Awaiting decision", "claimed_decision": "",
            "decision_claim_mode": "absent",
        }],
        "referenced_entities": [{
            "name": "Holmpatrick Ltd", "role": "Planning ownership declaration",
            "site_scope": 'Site "Britannia New Mill Queen Street Mossley Tameside OL5 9AQ"',
            "application_reference": "",
        }],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_beal_valley_negative_control_unaffected(session):
    """Beal Valley already generated successfully under v5 - confirms the
    v6 amendment changes nothing about a zero-evidence allocation."""
    _make_council(session, "oldham")
    plan = _make_plan(session, council_code="oldham")
    allocation = _make_allocation(session, plan, council_code="oldham", policy_reference="JPA 10",
                                   site_name="Beal Valley", minimum_dwellings=480)
    session.commit()
    context = build_allocation_context(session, allocation)
    assert context.number_of_related_sites == 0
    assert context.applicant_evidence == []
    assert context.ownership_entities == []
    output = {
        "headline": "No identified planning activity for Beal Valley",
        "overview": "No trusted planning applications or ownership evidence have been identified for this allocation.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


# ---------------------------------------------------------------------------
# N. V7 Quality Hardening Amendment - Heald Green party-attribution prompt
# clarity (real v6 production rejection: "unsupported application reference
# for entity claim: Bloor Homes North West / Applicant / DC/084620" - the
# VALIDATOR correctly caught the model attributing Bloor Homes' evidence to
# the representative Application DC/084620 instead of the different,
# secondary DC/078180 it is actually evidenced on; this section proves the
# context/prompt now states that distinction explicitly, and that every
# correct/incorrect self-report shape is still handled correctly).
# ---------------------------------------------------------------------------


def _heald_green_with_bloor_homes_fixture(session):
    """Extends the base Heald Green shape with the real DC/078180 (Bloor
    Homes North West, applicant) alongside representative DC/084620 -
    mirrors the exact real production case."""
    allocation = _heald_green_style_fixture(session)
    site = session.execute(select(Site).where(Site.display_address == "Land At Wilmslow Road Heald Green Stockport")).scalars().first()
    _make_app(session, site.id, "DC/078180", status="Decided", decision="Granted",
              application_category="reserved_matters", council_code="stockport",
              applicant_name_raw="Bloor Homes North West")
    session.commit()
    return allocation


def test_applicant_evidence_states_it_is_not_the_representative_application(session):
    """The prompt-level fix itself - Bloor Homes' evidence line must now
    explicitly say it is NOT the representative Application."""
    allocation = _heald_green_with_bloor_homes_fixture(session)
    context = build_allocation_context(session, allocation)
    prompt = build_summary_prompt(context)
    assert "Bloor Homes North West" in prompt
    assert "DC/078180" in prompt
    # The applicant evidence line for Bloor Homes must call out that
    # DC/078180 is not the representative Application (DC/084620).
    bloor_line = next(line for line in prompt.splitlines() if "Bloor Homes North West" in line)
    assert "NOT the representative Application" in bloor_line


def test_a_bloor_homes_described_as_applicant_associated_with_site_generally(session):
    """Test A - the safe, general form (no specific Application cited)
    always grounds correctly."""
    allocation = _heald_green_with_bloor_homes_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x",
        "overview": "Bloor Homes North West is named as applicant in planning activity linked to the Site.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{
            "name": "Bloor Homes North West", "role": "Applicant", "site_scope": 'Site "Land At Wilmslow Road Heald Green Stockport"',
            "application_reference": "",
        }],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_b_bloor_homes_associated_specifically_with_dc078180(session):
    """Test B - the CORRECT specific-Application claim grounds."""
    allocation = _heald_green_with_bloor_homes_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        # DC/078180 is not the Site's representative Application, so it
        # carries no groundable status/decision fact of its own (only the
        # bare, already-trusted reference) - this claim is deliberately
        # reference-only, matching the established rule that only a
        # representative Application's status/decision can be grounded.
        "headline": "x", "overview": "Bloor Homes North West is named as applicant on DC/078180.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/078180", "claimed_status": "", "claimed_decision": ""}],
        "referenced_entities": [{
            "name": "Bloor Homes North West", "role": "Applicant", "site_scope": 'Site "Land At Wilmslow Road Heald Green Stockport"',
            "application_reference": "DC/078180",
        }],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_c_bloor_homes_cannot_be_associated_with_dc084620(session):
    """Test C - direct regression for the exact real v6 rejection: the
    WRONG specific-Application claim must still be rejected."""
    allocation = _heald_green_with_bloor_homes_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "Bloor Homes North West is named as applicant on DC/084620.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/084620", "claimed_status": "Decided", "claimed_decision": "Granted"}],
        "referenced_entities": [{
            "name": "Bloor Homes North West", "role": "Applicant", "site_scope": 'Site "Land At Wilmslow Road Heald Green Stockport"',
            "application_reference": "DC/084620",
        }],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_d_bloor_homes_cannot_become_developer(session):
    allocation = _heald_green_with_bloor_homes_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "Bloor Homes North West is the developer of this Site.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{
            "name": "Bloor Homes North West", "role": "S106 Developer", "site_scope": 'Site "Land At Wilmslow Road Heald Green Stockport"',
            "application_reference": "",
        }],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_e_bloor_homes_cannot_become_owner(session):
    allocation = _heald_green_with_bloor_homes_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "Bloor Homes North West owns this Site.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{
            "name": "Bloor Homes North West", "role": "Planning ownership declaration",
            "site_scope": 'Site "Land At Wilmslow Road Heald Green Stockport"', "application_reference": "",
        }],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_f_bloor_homes_cannot_become_promoter(session):
    allocation = _heald_green_with_bloor_homes_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "Bloor Homes North West is promoting this Site.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{
            "name": "Bloor Homes North West", "role": "Promoter evidence",
            "site_scope": 'Site "Land At Wilmslow Road Heald Green Stockport"', "application_reference": "",
        }],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


# ---------------------------------------------------------------------------
# O. V7 Quality Hardening Amendment - unsupported/derived numbers remain
# rejected (real v6 Heald Green rejection: "unsupported numbers: 83" -
# investigated and found to be AI-derived arithmetic, 100% - 17% coverage,
# never a trusted deterministic value or a masking gap - correctly and
# deliberately still rejected, never allow-listed).
# ---------------------------------------------------------------------------


def test_g_derived_complement_percentage_still_rejected(session):
    """Direct regression for the exact real production generation_error -
    100% minus the trusted 17% coverage figure is AI-DERIVED arithmetic,
    never a number PropertyAIgent itself computed or exposed - must
    remain rejected, exactly as it correctly was in real production."""
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "83% of this allocation's capacity remains unaccounted for by identified planning activity.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_h_trusted_allocation_and_status_numbers_still_work(session):
    """Companion positive case - the same allocation's genuinely trusted
    figures (capacity, identified, coverage %) still validate cleanly."""
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x",
        "overview": "124 of this allocation's 750 homes are identified, a 17% coverage rate, via the granted DC/084620.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/084620", "claimed_status": "Decided", "claimed_decision": "Granted"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


# ---------------------------------------------------------------------------
# P. V7 Quality Hardening Amendment - Britannia/Holmpatrick role-boundary
# prompt clarity (real v6 output: "Holmpatrick Ltd has submitted a planning
# application for redevelopment" - not supported by its only trusted fact,
# "Planning ownership declaration"; this section proves the reworded
# ownership-evidence rendering and Rule 2's concrete counter-example are
# present, and that the correct/incorrect self-report shapes are still
# handled correctly by the validator).
# ---------------------------------------------------------------------------


def test_ownership_evidence_rendering_does_not_imply_submission(session):
    allocation = _ownership_fixture(session, role="OWNER", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION")
    context = build_allocation_context(session, allocation)
    prompt = build_summary_prompt(context)
    entity_line = next(line for line in prompt.splitlines() if "Test Entity Ltd" in line and "role:" in line)
    assert "does NOT mean" in entity_line
    assert "submitted" in entity_line


def test_k_britannia_holmpatrick_correct_role_claim_passes(session):
    allocation = _ownership_fixture(session, role="OWNER", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
                                     entity_name_raw="Holmpatrick Ltd")
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "Holmpatrick Ltd is named under a planning ownership declaration for the identified Site.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{
            "name": "Holmpatrick Ltd", "role": "Planning ownership declaration", "site_scope": 'Site "Test Site"',
            "application_reference": "",
        }],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_l_britannia_holmpatrick_unsupported_applicant_claim_rejected(session):
    """Direct regression for the real v6 output - if the model DOES
    self-report Holmpatrick Ltd as Applicant (rather than omitting the
    self-report entirely, as the real generation did), the validator
    correctly rejects it, since no independent Applicant-role evidence
    exists for this entity."""
    allocation = _ownership_fixture(session, role="OWNER", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
                                     entity_name_raw="Holmpatrick Ltd")
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "Holmpatrick Ltd has submitted a planning application for redevelopment.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{
            "name": "Holmpatrick Ltd", "role": "Applicant", "site_scope": 'Site "Test Site"', "application_reference": "",
        }],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


# ---------------------------------------------------------------------------
# Q. V7 Quality Hardening Amendment - absence-of-evidence prompt guidance
# (real v6 Beal Valley output over-claimed real-world absence: "no efforts
# have been made to develop the site", "a further barrier to any potential
# development", "a distinctly cautious commercial outlook" - none supported
# by "no identified planning activity"/"no ownership evidence identified").
# This is a prompt-guidance change, not a new validator check - free prose
# is deliberately never restricted to fixed tokens - so these tests prove
# the guidance text is present and that grounded absence framing still
# validates cleanly (there is no deterministic way to reject an over-claim
# purely in free prose without reintroducing token-level restrictions,
# which is explicitly out of scope).
# ---------------------------------------------------------------------------


def test_i_j_absence_of_evidence_guidance_present_in_prompt(session):
    allocation = _boothstown_style_fixture(session)
    context = build_allocation_context(session, allocation)
    prompt = build_summary_prompt(context)
    assert "NOT EVIDENCE OF ABSENCE" in prompt
    assert "investigation signal" in prompt.lower()


def test_grounded_absence_framing_as_investigation_signal_validates(session):
    """The Product Owner's own example wording (paraphrased, proving
    natural-language freedom, not a template) validates cleanly."""
    _make_council(session, "oldham")
    plan = _make_plan(session, council_code="oldham")
    allocation = _make_allocation(session, plan, council_code="oldham", policy_reference="JPA 10",
                                   site_name="Beal Valley", minimum_dwellings=480)
    session.commit()
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "Beal Valley allocation with no currently identified planning activity",
        "overview": (
            "No linked planning activity or ownership/control evidence has currently been identified for this "
            "allocation, leaving the full approximately 480-home capacity apparently unaccounted for on this "
            "platform's own records - a potential investigation opportunity."
        ),
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


# ---------------------------------------------------------------------------
# R. V7 Quality Hardening Amendment - dry-run/execute parity (real
# production symptom: --allocation-ids dry-run reported "fresh: 1, would
# generate: 3" immediately before an execute run that attempted all four
# and regenerated allocation 51 - CLI-level tests live in
# tests/test_generate_allocation_intelligence_summaries_cli.py; this
# section only proves the underlying is_allocation_summary_stale/
# should_regenerate_allocation_summary parity the CLI now relies on).
# ---------------------------------------------------------------------------


def test_stale_check_detects_prompt_version_drift(session):
    """Direct regression for the real parity bug's OTHER half - a summary
    whose fingerprint has NOT changed but whose prompt_version has must
    now be reported stale (previously only fingerprint was checked)."""
    from app.reporting.allocation_intelligence_summary import is_allocation_summary_stale
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    fingerprint = compute_context_fingerprint(context)
    summary = get_allocation_summary(session, allocation.id)
    if summary is None:
        from app.db.models import AllocationIntelligenceSummary
        summary = AllocationIntelligenceSummary(allocation_id=allocation.id)
        session.add(summary)
    summary.headline = "Existing summary"
    summary.context_fingerprint = fingerprint
    summary.prompt_version = "allocation-intelligence-summary-v1-stale-on-purpose"
    summary.status = "ok"
    session.commit()

    assert is_allocation_summary_stale(session, allocation) is True


def test_stale_check_false_when_fingerprint_and_prompt_version_both_current(session):
    from app.reporting.allocation_intelligence_summary import PROMPT_VERSION, is_allocation_summary_stale
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    fingerprint = compute_context_fingerprint(context)
    summary = get_allocation_summary(session, allocation.id)
    if summary is None:
        from app.db.models import AllocationIntelligenceSummary
        summary = AllocationIntelligenceSummary(allocation_id=allocation.id)
        session.add(summary)
    summary.headline = "Existing summary"
    summary.context_fingerprint = fingerprint
    summary.prompt_version = PROMPT_VERSION
    summary.status = "ok"
    session.commit()

    assert is_allocation_summary_stale(session, allocation) is False


# ---------------------------------------------------------------------------
# S. Natural-language freedom preserved (Test R from the task's own matrix)
# ---------------------------------------------------------------------------


def test_natural_language_variation_remains_free_after_v7_prompt_changes(session):
    """The v7 prompt-guidance changes add framing, not sentence templates -
    several very differently-worded, equally-grounded summaries must all
    still pass."""
    allocation = _boothstown_style_fixture(session)
    context = build_allocation_context(session, allocation)
    variants = [
        "This allocation's identified activity, via PA/2024/0749, covers the large majority of its 300-home "
        "capacity - 282 homes - though the application remains under consultation, so this should not be read "
        "as consented. Roughly 18 homes have no identified planning activity against them.",

        "282 of 300 homes at East of Boothstown sit behind an active but undetermined application (PA/2024/0749); "
        "a modest 18-home slice remains unaccounted for on this platform's own records.",
    ]
    for overview_text in variants:
        output = {
            "headline": "x", "overview": overview_text,
            "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
            "referenced_applications": [{"reference": "PA/2024/0749", "claimed_status": "Under Consultation", "claimed_decision": ""}],
            "referenced_entities": [],
        }
        is_valid, problems = validate_summary_output(context, output)
        assert is_valid is True, (overview_text, problems)


# ---------------------------------------------------------------------------
# T. V8 Reliability Hardening Amendment - inert empty self-report entries
# (real V7 platform-wide audit: 72 of 102 rejected allocations, ~71%, had
# this as their primary root cause - a placeholder entry with all fields
# blank, self-reported instead of an empty array, which the pre-v8
# validator read as a CLAIMED empty Application reference / entity name).
# ---------------------------------------------------------------------------


def _zero_activity_fixture(session, *, council_code="testcouncil", policy_reference="ZERO-1", minimum_dwellings=480):
    _make_council(session, council_code)
    plan = _make_plan(session, council_code=council_code)
    allocation = _make_allocation(session, plan, council_code=council_code, policy_reference=policy_reference,
                                   site_name="Zero Activity Allocation", minimum_dwellings=minimum_dwellings)
    session.commit()
    return allocation


def test_1_referenced_applications_empty_list_passes_where_no_applications_exist(session):
    allocation = _zero_activity_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "No linked planning activity has currently been identified for this allocation.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_2_inert_empty_application_entry_treated_as_equivalent_to_empty_list(session):
    """Direct regression for the dominant real V7 rejection shape - an
    application entry that is entirely blank (the exact structural shape
    observed in real production generation_error text: "unsupported
    application reference: ")."""
    allocation = _zero_activity_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "No linked planning activity has currently been identified for this allocation.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "", "claimed_status": "", "claimed_decision": "", "decision_claim_mode": "none"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_3_empty_reference_with_material_status_claim_still_rejected(session):
    """Safety guard - an empty reference must NOT become a mechanism for
    attaching an unsupported status claim "for free"."""
    allocation = _zero_activity_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "", "claimed_status": "Decided", "claimed_decision": "", "decision_claim_mode": "none"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_4_empty_reference_with_material_decision_claim_still_rejected(session):
    """decision_claim_mode="value" is NEVER inert, even with reference and
    claimed_decision both blank - "value" itself asserts a concrete
    decision was stated, which cannot be attached to no Application."""
    allocation = _zero_activity_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "", "claimed_status": "", "claimed_decision": "Granted", "decision_claim_mode": "value"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False

    value_mode_empty_text = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "", "claimed_status": "", "claimed_decision": "", "decision_claim_mode": "value"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, value_mode_empty_text)
    assert is_valid is False


def test_5_fabricated_non_empty_application_reference_still_rejected(session):
    allocation = _zero_activity_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "DC/999999 accounts for this allocation's capacity.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/999999", "claimed_status": "", "claimed_decision": "", "decision_claim_mode": "none"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_6_wrong_real_application_reference_remains_rejected(session):
    """A reference that IS real somewhere on the platform but not for
    THIS allocation's own context remains rejected."""
    allocation = _boothstown_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "DC/084620 accounts for this allocation's capacity.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/084620", "claimed_status": "", "claimed_decision": "", "decision_claim_mode": "none"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_7_valid_grounded_application_claim_still_passes(session):
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "DC/084620 was granted.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/084620", "claimed_status": "Decided", "claimed_decision": "Granted", "decision_claim_mode": "value"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_8_no_linked_application_narrative_validates_without_provenance_claim(session):
    """The Product Owner's own example wording, paraphrased - no
    Application provenance is required to state the opportunity signal."""
    allocation = _zero_activity_fixture(session, policy_reference="JPA 10", minimum_dwellings=480)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "Beal Valley shows no currently identified planning activity",
        "overview": (
            "No linked planning application has been identified in PropertyAIgent's current evidence, leaving "
            "the allocation's approximately 480-home capacity currently unaccounted for by identified planning "
            "activity and highlighting a potential development opportunity for further investigation."
        ),
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_9_referenced_entities_empty_list_passes_where_no_entity_evidence_exists(session):
    allocation = _zero_activity_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "No ownership/control evidence has currently been identified for this allocation.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_10_inert_empty_entity_entry_treated_as_equivalent_to_empty_list(session):
    """Direct regression for allocation 179's real production shape - an
    entity entry with name="" but a real role/scope attached to nothing."""
    allocation = _zero_activity_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "No ownership/control evidence has currently been identified for this allocation.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "", "role": "", "site_scope": "", "application_reference": ""}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_11_empty_entity_name_cannot_smuggle_material_role_claim(session):
    allocation = _zero_activity_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "", "role": "Planning ownership declaration", "site_scope": "", "application_reference": ""}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_12_empty_entity_name_cannot_smuggle_material_scope_claim(session):
    allocation = _zero_activity_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "", "role": "", "site_scope": "the allocation's residual (unaccounted-for) capacity", "application_reference": ""}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_13_invented_non_empty_entity_still_rejects(session):
    allocation = _zero_activity_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "Invented Developer Ltd controls this allocation.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "Invented Developer Ltd", "role": "S106 Developer", "site_scope": "", "application_reference": ""}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_14_applicant_to_developer_promotion_still_rejects(session):
    allocation = _heald_green_with_bloor_homes_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "Bloor Homes North West is the developer.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{
            "name": "Bloor Homes North West", "role": "S106 Developer",
            "site_scope": 'Site "Land At Wilmslow Road Heald Green Stockport"', "application_reference": "",
        }],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_15_wrong_site_scope_still_rejects(session):
    allocation = _ownership_fixture(session, role="OWNER", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION")
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "Test Entity Ltd", "role": "Planning ownership declaration", "site_scope": "the allocation", "application_reference": ""}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_16_valid_grounded_applicant_claim_still_passes(session):
    allocation = _heald_green_with_bloor_homes_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "Bloor Homes North West is named as applicant associated with planning activity on the Site.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{
            "name": "Bloor Homes North West", "role": "Applicant",
            "site_scope": 'Site "Land At Wilmslow Road Heald Green Stockport"', "application_reference": "",
        }],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


# ---------------------------------------------------------------------------
# U. V8 Reliability Hardening Amendment - case-insensitive trusted-label
# masking (real V7 audit: 9 of 25 "unsupported numbers" rejections traced
# exactly to this - "Regulation 18" masked correctly, "regulation 18" not).
# ---------------------------------------------------------------------------


def test_17_lowercase_regulation_18_narration_now_accepted(session):
    allocation = _regulation_18_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "This Local Plan is currently at regulation 18 stage, not yet adopted.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_18_mixed_and_upper_case_regulation_18_variants_all_accepted(session):
    allocation = _regulation_18_fixture(session)
    context = build_allocation_context(session, allocation)
    for phrase in ["REGULATION 18", "Regulation 18", "ReGuLaTiOn 18"]:
        output = {
            "headline": "x", "overview": f"This Local Plan is currently at {phrase} stage.",
            "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
            "referenced_applications": [], "referenced_entities": [],
        }
        is_valid, problems = validate_summary_output(context, output)
        assert is_valid is True, (phrase, problems)


def test_19_parenthetical_subphrase_behaviour_remains_supported(session):
    """The FULL literal label (with the phase prefix) still masks too -
    this generalised fix did not regress the prior whole-label masking."""
    allocation = _regulation_18_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "This allocation's plan is at Draft consultation (Regulation 18) stage.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_20_invented_regulation_number_remains_rejected(session):
    allocation = _regulation_18_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "This Local Plan is already at Regulation 25 stage.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_21_genuinely_invented_unrelated_number_remains_rejected(session):
    allocation = _regulation_18_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "This allocation is expected to deliver 42 additional phases.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


# ---------------------------------------------------------------------------
# V. V8 Reliability Hardening Amendment - placeholder decision normalisation
# (real production case: allocation 13/DC/094533's Application.decision is
# literally the string "Not Available" - confirmed the ONLY placeholder-
# shaped value among 60+ real distinct decision values in production).
# ---------------------------------------------------------------------------


def _placeholder_decision_fixture(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=200)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    _make_app(session, site.id, "DC/PLACEHOLDER", units=100, status="Registered", decision="Not Available")
    session.commit()
    return allocation


def test_22_recognised_placeholder_decision_treated_as_absence(session):
    allocation = _placeholder_decision_fixture(session)
    context = build_allocation_context(session, allocation)
    rep = context.sites[0].representative_application
    assert rep.decision is None  # cleaned away, not the literal placeholder string


def test_23_decision_claim_mode_absent_passes_for_recognised_placeholder(session):
    """Direct regression for the real production rejection: a genuinely
    reasonable "no decision recorded" claim, against an Application whose
    raw decision field is the portal placeholder "Not Available"."""
    allocation = _placeholder_decision_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "DC/PLACEHOLDER has no decision recorded yet.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/PLACEHOLDER", "claimed_status": "", "claimed_decision": "", "decision_claim_mode": "absent"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_24_genuine_granted_decision_rejects_absent_claim(session):
    allocation = _heald_green_style_fixture(session)  # DC/084620 decision="Granted"
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "DC/084620 has no decision recorded yet.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/084620", "claimed_status": "", "claimed_decision": "", "decision_claim_mode": "absent"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_25_genuine_refused_decision_rejects_absent_claim(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    _make_app(session, site.id, "APP/REFUSED2", units=100, status="Decided", decision="Refuse")
    session.commit()
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "APP/REFUSED2 has no decision recorded yet.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "APP/REFUSED2", "claimed_status": "", "claimed_decision": "", "decision_claim_mode": "absent"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_26_genuine_withdrawn_decision_rejects_absent_claim(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    _make_app(session, site.id, "APP/WITHDRAWN2", units=100, status="Closed", decision="Withdrawn")
    session.commit()
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "APP/WITHDRAWN2 has no decision recorded yet.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "APP/WITHDRAWN2", "claimed_status": "", "claimed_decision": "", "decision_claim_mode": "absent"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_27_placeholder_normalisation_does_not_erase_genuine_decision_text(session):
    """A genuine, substantive decision value is completely unaffected by
    the placeholder cleaner - "Granted" still grounds a real value claim."""
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    rep = context.sites[0].representative_application
    assert rep.decision == "Granted"
    output = {
        "headline": "x", "overview": "DC/084620 was granted.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/084620", "claimed_status": "", "claimed_decision": "Granted", "decision_claim_mode": "value"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


# ---------------------------------------------------------------------------
# W. V9 Final Pilot Reliability Amendment - Fix A: untargeted absence claims
# now inert (real V8 production audit: "empty_application_reference" was
# STILL the dominant failure family after V8's own fix - 35 of 55, ~64% -
# root-caused precisely by replaying allocation 193's real trusted context
# through validate_summary_output: a model narrating the no-linked-
# Application product principle naturally wants to add "no decision has
# been recorded" as a companion fact, and with no real Application to
# attach it to, sets decision_claim_mode="absent" on an otherwise fully
# blank entry - V8's boundary treated any non-"none" mode as automatically
# material, so this fell through to "unsupported application reference: ").
# ---------------------------------------------------------------------------


def test_a_untargeted_absent_decision_claim_now_inert(session):
    """Direct regression for the exact real production shape reproduced
    against allocation 193's real trusted context this task's own
    investigation confirmed."""
    allocation = _zero_activity_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "No decision has been recorded for this allocation's planning activity.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "", "claimed_status": "", "claimed_decision": "", "decision_claim_mode": "absent"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_b_blank_reference_with_material_status_still_rejects_alongside_absent(session):
    """Safety guard - decision_claim_mode="absent" widening must not leak
    into claimed_status: any real status text still rejects."""
    allocation = _zero_activity_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "", "claimed_status": "Awaiting decision", "claimed_decision": "", "decision_claim_mode": "absent"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_c_blank_reference_value_mode_still_rejects(session):
    allocation = _zero_activity_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "", "claimed_status": "", "claimed_decision": "Granted", "decision_claim_mode": "value"}],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_d_blank_reference_absent_claim_on_real_representative_still_fine_when_genuinely_no_decision(session):
    """D - a blank-reference absent claim cannot bypass Application-
    specific grounding: it is inert (asserts nothing checkable), it does
    NOT retroactively ground anything about a REAL Application - a
    separate, correctly-targeted absent claim for a real Application
    whose decision is genuinely recorded must still fail."""
    allocation = _heald_green_style_fixture(session)  # DC/084620 decision="Granted"
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "No decision has been recorded. DC/084620 has no decision recorded yet.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [
            {"reference": "", "claimed_status": "", "claimed_decision": "", "decision_claim_mode": "absent"},
            {"reference": "DC/084620", "claimed_status": "", "claimed_decision": "", "decision_claim_mode": "absent"},
        ],
        "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


# ---------------------------------------------------------------------------
# X. V9 Final Pilot Reliability Amendment - Fix B: trusted allocation_name/
# local_plan_name substring masking, and the allocation_capacity_display
# range figure (real V8 production audit: 17 of 17 investigated
# "unsupported numbers" rejections traced to one of these three sources -
# never a genuine hallucination).
# ---------------------------------------------------------------------------


def _address_named_allocation_fixture(session, *, site_name, council_code="testcouncil", policy_reference="ADDR-1"):
    _make_council(session, council_code)
    plan = _make_plan(session, council_code=council_code)
    allocation = _make_allocation(session, plan, council_code=council_code, policy_reference=policy_reference,
                                   site_name=site_name, minimum_dwellings=50)
    session.commit()
    return allocation


def test_e_trusted_site_name_digits_validate_as_part_of_full_name(session):
    """Direct regression for real allocation 142 ("499 Chester Road, Old
    Trafford") - the full trusted name narrated verbatim validates."""
    allocation = _address_named_allocation_fixture(session, site_name="499 Chester Road, Old Trafford")
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "This site, 499 Chester Road, Old Trafford, has no identified planning activity.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_f_multiple_address_formats_validate(session):
    """F - several distinct real production address shapes, each
    narrating only the STREET portion (not the full comma-suffixed name) -
    proves comma-segment masking, not just whole-string masking."""
    addresses = [
        "88-118 Chorlton Road, Old Trafford",
        "Rear 61-83 Palace Road, Ashton-under-Lyne",
        "Former Two Trees School, 101 Two Trees Lane, Denton",
        "Site of River Mill, 6-32 Waggon Road, Mossley",
    ]
    for i, addr in enumerate(addresses):
        allocation = _address_named_allocation_fixture(session, site_name=addr, policy_reference=f"ADDR-{i}")
        context = build_allocation_context(session, allocation)
        street_portion = addr.split(",")[-2].strip() if addr.count(",") >= 1 else addr
        # Narrate only ONE comma-separated segment, never the full string.
        segment = [p.strip() for p in addr.split(",")][-2] if addr.count(",") >= 1 else addr
        output = {
            "headline": "x", "overview": f"This allocation, {segment}, has no identified planning activity.",
            "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
            "referenced_applications": [], "referenced_entities": [],
        }
        is_valid, problems = validate_summary_output(context, output)
        assert is_valid is True, (addr, problems)


def test_g_invented_number_still_rejected_on_address_named_allocation(session):
    allocation = _address_named_allocation_fixture(session, site_name="499 Chester Road, Old Trafford")
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "This allocation is expected to deliver 777 additional units.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def _local_plan_year_fixture(session):
    """Direct regression for real allocations 155-160 - a Local Plan name
    with its own embedded target year, rendered verbatim."""
    _make_council(session, "manchestertest")
    plan = LocalPlan(council_code="manchestertest", plan_name="Draft Manchester Local Plan (September 2025)",
                      status="draft_consultation", raw_status="draft_consultation")
    session.add(plan)
    session.commit()
    allocation = _make_allocation(session, plan, council_code="manchestertest", policy_reference="H1 (Test)",
                                   site_name="Test Manchester Allocation", minimum_dwellings=500)
    session.commit()
    return allocation


def test_local_plan_name_year_validates(session):
    allocation = _local_plan_year_fixture(session)
    context = build_allocation_context(session, allocation)
    assert context.local_plan_name == "Draft Manchester Local Plan (September 2025)"
    output = {
        "headline": "x", "overview": "This allocation sits under the Draft Manchester Local Plan (September 2025).",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_local_plan_name_year_validates_without_trailing_parenthetical(session):
    """Proves the paren-stripped-prefix masking, not just the whole
    string - narrating "...to 2040" without repeating "(Initial Draft)"."""
    _make_council(session, "wigantest")
    plan = LocalPlan(council_code="wigantest", plan_name="Wigan Borough Local Plan: Planning for the Future to 2040 (Initial Draft)",
                      status="draft_consultation", raw_status="draft_consultation")
    session.add(plan)
    session.commit()
    allocation = _make_allocation(session, plan, council_code="wigantest", policy_reference="H5",
                                   site_name="Test Wigan Allocation", minimum_dwellings=300)
    session.commit()
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x",
        "overview": "This allocation sits under the Wigan Borough Local Plan: Planning for the Future to 2040.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def _range_capacity_fixture(session):
    """Direct regression for real allocations 136/139 - a "range"-kind
    capacity whose own lower bound is rendered verbatim in
    allocation_capacity_display ("8,400-15,000 homes") but was never in
    allocation_capacity_value (which reports only the upper bound)."""
    _make_council(session)
    plan = _make_plan(session)
    allocation = LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan.id, policy_reference="RANGE-1", site_name="Range Test Allocation",
        plan_name="Test Local Plan", plan_status="adopted", minimum_dwellings=8400, maximum_capacity=15000,
        intended_use="mixed_use",
    )
    session.add(allocation)
    session.commit()
    return allocation


def test_range_capacity_lower_bound_validates(session):
    allocation = _range_capacity_fixture(session)
    context = build_allocation_context(session, allocation)
    assert context.allocation_capacity_kind == "range"
    assert "8,400" in context.allocation_capacity_display
    output = {
        "headline": "x", "overview": f"This allocation has an indicative range of {context.allocation_capacity_display}.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


# ---------------------------------------------------------------------------
# Y. V9 Final Pilot Reliability Amendment - remaining V8-behaviour
# regressions (H-O from the task's own matrix - largely already covered
# elsewhere in this file; re-asserted here explicitly against the V9 code)
# ---------------------------------------------------------------------------


def test_h_derived_arithmetic_still_rejected_after_v9(session):
    allocation = _heald_green_style_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "x", "overview": "83% of this allocation's capacity remains unaccounted for.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_i_j_k_wrong_role_scope_and_attribution_still_rejected_after_v9(session):
    allocation = _heald_green_with_bloor_homes_fixture(session)
    context = build_allocation_context(session, allocation)
    wrong_role = {
        "headline": "x", "overview": "Bloor Homes North West is the developer.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "Bloor Homes North West", "role": "S106 Developer", "site_scope": 'Site "Land At Wilmslow Road Heald Green Stockport"', "application_reference": ""}],
    }
    assert validate_summary_output(context, wrong_role)[0] is False
    wrong_scope = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "Bloor Homes North West", "role": "Applicant", "site_scope": "the allocation", "application_reference": ""}],
    }
    assert validate_summary_output(context, wrong_scope)[0] is False
    wrong_attribution = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/084620", "claimed_status": "", "claimed_decision": "", "decision_claim_mode": "none"}],
        "referenced_entities": [{"name": "Bloor Homes North West", "role": "Applicant", "site_scope": 'Site "Land At Wilmslow Road Heald Green Stockport"', "application_reference": "DC/084620"}],
    }
    assert validate_summary_output(context, wrong_attribution)[0] is False


def test_l_no_linked_application_allocation_produces_valid_grounded_summary(session):
    allocation = _zero_activity_fixture(session)
    context = build_allocation_context(session, allocation)
    output = {
        "headline": "No identified planning activity for this allocation",
        "overview": (
            "No linked planning application has been identified in PropertyAIgent's current evidence, leaving "
            "the allocation's capacity currently unaccounted for by identified planning activity and "
            "highlighting a potential development opportunity for further investigation."
        ),
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is True, problems


def test_n_needs_confirmation_boundary_unchanged_after_v9(session):
    allocation = _applicant_fixture(session, applicant_name_raw="Should Not Appear Ltd", site_review_status="needs_confirmation")
    context = build_allocation_context(session, allocation)
    assert context.sites[0].representative_application is None
    output = {
        "headline": "x", "overview": "x", "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [],
        "referenced_entities": [{"name": "Should Not Appear Ltd", "role": "Applicant", "site_scope": 'Site "Test Site"', "application_reference": ""}],
    }
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False


def test_o_failure_preserves_last_valid_summary_after_v9(session):
    allocation = _heald_green_style_fixture(session)
    good_output = {
        "headline": "Reserved matters granted for part of the allocation",
        "overview": "DC/084620 was granted on 11 Jan 2024, covering 124 of the allocation's 750 homes.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [{"reference": "DC/084620", "claimed_status": "Decided", "claimed_decision": "Granted"}],
        "referenced_entities": [],
    }
    client = _fake_client(good_output)
    result = generate_allocation_intelligence_summary(session, client, allocation)
    assert result.regenerated is True, result.rejection_reason
    summary = get_allocation_summary(session, allocation.id)
    assert summary.headline == good_output["headline"]

    bad_output = {
        "headline": "x", "overview": "This allocation could deliver up to 99999 homes.",
        "key_points": [], "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }
    client2 = _fake_client(bad_output)
    result2 = generate_allocation_intelligence_summary(session, client2, allocation, force=True)
    assert result2.rejected is True
    summary2 = get_allocation_summary(session, allocation.id)
    assert summary2.headline == good_output["headline"]  # last valid summary preserved
    assert summary2.status == "error"
