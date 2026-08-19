"""AI Allocation Intelligence Summary - Pre-Sample Amendment tests:
"Trusted Planning Application Status/Decision Context". Covers exposing
existing, trusted, portal-scraped Application status/decision/category
facts to AllocationIntelligenceContext (via the SAME representative
Application app.ui.common.pick_representative_application already selects
for capacity), the resulting prompt rules distinguishing planning ACTIVITY
from planning OUTCOME, bounded (never exhaustive) multi-Application
handling, and fingerprint sensitivity to material status/decision changes.

No real OpenAI call anywhere - fake clients only, matching the established
pattern from tests/test_allocation_intelligence_summary.py."""
from __future__ import annotations

from app.db.models import (
    AllocationSiteRelationship, Application, Council, LocalPlan, LocalPlanSite, SchemeIntelligence, Site,
)
from app.reporting.allocation_intelligence_summary import (
    build_allocation_context, build_summary_prompt, compute_context_fingerprint,
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
              application_category=None, proposal=None, complete=True, council_code="testcouncil") -> Application:
    app = Application(
        council_code=council_code, reference=reference, site_id=site_id, status=status, decision=decision,
        decision_issued_date=decision_issued_date, application_category=application_category, proposal=proposal,
    )
    session.add(app)
    session.commit()
    if units is not None:
        session.add(SchemeIntelligence(application_id=app.id, total_units_final=units, core_intelligence_complete=complete))
        session.commit()
    return app


# ---------------------------------------------------------------------------
# Existing Application fields exposed to context
# ---------------------------------------------------------------------------


def test_representative_application_detail_populated_from_trusted_fields(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    _make_app(
        session, site.id, "APP/1", units=282, status="Under Consultation", decision=None,
        decision_issued_date=None, application_category="primary_residential",
        proposal="Erection of 282 dwellings with associated infrastructure",
    )
    session.commit()

    context = build_allocation_context(session, allocation)
    rep = context.sites[0].representative_application
    assert rep is not None
    assert rep.reference == "APP/1"
    assert rep.status == "Under Consultation"
    assert rep.decision is None
    assert rep.application_category == "primary_residential"
    assert rep.proposal_summary.startswith("Erection of 282 dwellings")


def test_representative_application_is_the_same_one_used_for_capacity(session):
    """The representative Application exposed for status/decision must
    always be the SAME Application app.ui.common.pick_representative_
    application already selected for the Site's capacity figure - never a
    different Application describing a different capacity."""
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=1000)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    # An incomplete, withdrawn earlier attempt - not the capacity source.
    _make_app(session, site.id, "APP/OLD", units=999, status="Closed", decision="Withdrawn", complete=False)
    # The complete, current one - this should be selected as representative.
    _make_app(session, site.id, "APP/NEW", units=282, status="Under Consultation", decision=None, complete=True)
    session.commit()

    context = build_allocation_context(session, allocation)
    site_entry = context.sites[0]
    assert site_entry.capacity == 282
    assert site_entry.representative_application.reference == "APP/NEW"
    assert site_entry.representative_application.status == "Under Consultation"
    # The withdrawn one is still counted, just not individually narrated.
    assert site_entry.other_applications_by_category.get("uncategorized") == 1


# ---------------------------------------------------------------------------
# Multi-Application handling (Section 6) - Heald Green West regression
# ---------------------------------------------------------------------------


def test_many_applications_grouped_not_enumerated(session):
    _make_council(session)
    plan = _make_plan(session, status="draft")
    allocation = _make_allocation(session, plan, policy_reference="HOM 2.33", site_name="Heald Green West", minimum_dwellings=750)
    site = _make_site(session, "Land At Wilmslow Road Heald Green")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="confirmed")
    # The representative, substantive application.
    _make_app(session, site.id, "DC/084620", units=124, status="Decided", decision="Granted",
              application_category="primary_residential", complete=True)
    # ~29 secondary filings, mostly discharge-of-conditions, matching the
    # real Heald Green West shape.
    for i in range(25):
        _make_app(session, site.id, f"DC/0{80000+i}", status="Decided", decision="Discharge Of Conditions",
                   application_category="condition_discharge_or_details")
    for i in range(3):
        _make_app(session, site.id, f"DC/0{90000+i}", status="Decided", decision="Granted",
                   application_category="variation_or_amendment")
    _make_app(session, site.id, "DC/060928", status="Decided", decision="Refuse", application_category="primary_residential")
    session.commit()

    context = build_allocation_context(session, allocation)
    site_entry = context.sites[0]
    assert len(site_entry.application_references) == 30  # no trusted Application disappears
    assert site_entry.representative_application.reference == "DC/084620"
    assert site_entry.other_applications_by_category == {
        "condition_discharge_or_details": 25, "variation_or_amendment": 3, "primary_residential": 1,
    }

    prompt = build_summary_prompt(context)
    # The prompt must NOT contain a separate line for every secondary Application.
    for i in range(25):
        assert f"DC/0{80000+i}" not in prompt
    # But the representative one, and the bounded count, must both appear.
    assert "DC/084620" in prompt
    assert "29 further Application(s)" in prompt
    assert "do not narrate these individually" in prompt


def test_prompt_instructs_against_exhaustive_enumeration(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()
    context = build_allocation_context(session, allocation)
    prompt = build_summary_prompt(context)
    assert "never produce anything resembling a list of every Application" in prompt


# ---------------------------------------------------------------------------
# Planning activity vs planning outcome semantics (Section 4/5)
# ---------------------------------------------------------------------------


def test_prompt_distinguishes_activity_from_outcome(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()
    context = build_allocation_context(session, allocation)
    prompt = build_summary_prompt(context)
    assert "PLANNING ACTIVITY is never the same thing as PLANNING OUTCOME" in prompt
    assert "under construction, built, delivered, or completed" in prompt
    assert "Never infer an Application's status or decision from the identified/residual capacity" in prompt


def test_east_of_boothstown_style_pending_application_not_implied_consented(session):
    """East of Boothstown regression (Case A) - a substantial 282/300-home
    identified capacity figure must expose that the underlying Application
    is still under consultation, not silently imply it is consented."""
    _make_council(session, "salford")
    plan = _make_plan(session, council_code="salford")
    allocation = _make_allocation(session, plan, council_code="salford", policy_reference="JPA 25",
                                   site_name="East of Boothstown", minimum_dwellings=300)
    site = _make_site(session, "Land East Of Boothstown, Salford", council_code="salford")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    _make_app(session, site.id, "23/81742/HYBEIA", status="Closed", decision="Withdrawn",
              application_category="primary_residential", complete=False, council_code="salford")
    _make_app(session, site.id, "PA/2024/0749", units=282, status="Under Consultation", decision=None,
              application_category="primary_residential", complete=True, council_code="salford")
    session.commit()

    context = build_allocation_context(session, allocation)
    # Capacity arithmetic is unchanged by this amendment.
    assert context.identified_application_capacity == 282
    assert context.indicative_residual_capacity == 18
    assert context.allocation_capacity_value == 300

    site_entry = context.sites[0]
    assert site_entry.representative_application.reference == "PA/2024/0749"
    assert site_entry.representative_application.status == "Under Consultation"
    assert site_entry.representative_application.decision is None

    prompt = build_summary_prompt(context)
    assert "Under Consultation" in prompt
    assert "23/81742/HYBEIA" in prompt  # still present, not lost


# ---------------------------------------------------------------------------
# Case C - Beal Valley (rejected relationship stays excluded)
# ---------------------------------------------------------------------------


def test_beal_valley_style_rejected_relationship_leaks_no_application_status(session):
    _make_council(session, "oldham")
    plan = _make_plan(session, council_code="oldham")
    allocation = _make_allocation(session, plan, council_code="oldham", policy_reference="JPA 10",
                                   site_name="Beal Valley", minimum_dwellings=480)
    site = _make_site(session, "Land South Of Bullcote Lane, Oldham", council_code="oldham")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="rejected")
    _make_app(session, site.id, "FUL/355603/26", units=248, status="Decided", decision="Granted",
              application_category="primary_residential", council_code="oldham")
    session.commit()

    context = build_allocation_context(session, allocation)
    assert context.sites == []
    assert context.identified_application_capacity == 0
    assert context.indicative_residual_capacity == 480

    prompt = build_summary_prompt(context)
    assert "FUL/355603/26" not in prompt
    assert "248" not in prompt  # the rejected relationship's own capacity figure must not leak in either


# ---------------------------------------------------------------------------
# Case D - Britannia Mill (ownership evidence unaffected)
# ---------------------------------------------------------------------------


def test_britannia_mill_style_ownership_unaffected_by_status_context(session):
    from app.db.models import ControlRelationship

    _make_council(session, "tameside")
    plan = _make_plan(session, council_code="tameside", status="draft")
    allocation = _make_allocation(session, plan, council_code="tameside", policy_reference="HSP S2K:9",
                                   site_name="Britannia Mill", minimum_dwellings=136)
    site = _make_site(session, "Britannia New Mill Queen Street Mossley Tameside", council_code="tameside")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    app = _make_app(session, site.id, "26/00098/FUL", units=49, status="Awaiting decision", decision=None,
                     application_category="primary_residential", council_code="tameside")
    session.add(ControlRelationship(
        site_id=site.id, application_id=app.id, entity_name_raw="Holmpatrick Ltd", entity_type="company",
        role="OWNER", evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
        extraction_method="deterministic_regex", review_status="auto_applied",
    ))
    session.commit()

    context = build_allocation_context(session, allocation)
    assert len(context.ownership_entities) == 1
    o = context.ownership_entities[0]
    assert o.entity_name_raw == "Holmpatrick Ltd"
    assert o.role_label == "Planning ownership declaration"
    assert o.is_residual is False

    site_entry = context.sites[0]
    assert site_entry.representative_application.status == "Awaiting decision"

    prompt = build_summary_prompt(context)
    # The ownership line itself must use the correct label, never call the
    # entity a "current owner" (checking the OWNERSHIP/CONTROL EVIDENCE
    # section specifically - the RULES section legitimately mentions
    # "current owner" once, as a negative example of what NOT to write).
    ownership_lines = prompt.split("OWNERSHIP/CONTROL EVIDENCE")[1].split("RULES")[0]
    assert "Planning ownership declaration" in ownership_lines
    assert "current owner" not in ownership_lines.lower()


# ---------------------------------------------------------------------------
# Section 8 - fingerprint sensitivity (Cases A-E)
# ---------------------------------------------------------------------------


def _single_site_allocation_with_app(session, **app_kwargs):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    app = _make_app(session, site.id, "APP/1", units=100, **app_kwargs)
    session.commit()
    return allocation, app


def test_fingerprint_case_a_status_change_changes_fingerprint(session):
    allocation, app = _single_site_allocation_with_app(session, status="Under Consultation")
    fp_before = compute_context_fingerprint(build_allocation_context(session, allocation))
    app.status = "Decided"
    session.commit()
    fp_after = compute_context_fingerprint(build_allocation_context(session, allocation))
    assert fp_before != fp_after


def test_fingerprint_case_b_decision_change_changes_fingerprint(session):
    allocation, app = _single_site_allocation_with_app(session, status="Decided", decision=None)
    fp_before = compute_context_fingerprint(build_allocation_context(session, allocation))
    app.decision = "Granted"
    app.decision_issued_date = "12 Mar 2024"
    session.commit()
    fp_after = compute_context_fingerprint(build_allocation_context(session, allocation))
    assert fp_before != fp_after


def test_fingerprint_case_c_unrelated_application_status_change_no_effect(session):
    allocation, app = _single_site_allocation_with_app(session, status="Under Consultation")
    unrelated_site = _make_site(session, "Unrelated Site")
    unrelated_app = _make_app(session, unrelated_site.id, "APP/UNRELATED", units=999, status="Under Consultation")
    session.commit()
    fp_before = compute_context_fingerprint(build_allocation_context(session, allocation))

    unrelated_app.status = "Decided"
    unrelated_app.decision = "Granted"
    session.commit()
    fp_after = compute_context_fingerprint(build_allocation_context(session, allocation))
    assert fp_before == fp_after


def test_fingerprint_case_d_rejected_relationship_application_change_no_effect(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="rejected")
    app = _make_app(session, site.id, "APP/REJECTED", units=100, status="Under Consultation")
    session.commit()
    fp_before = compute_context_fingerprint(build_allocation_context(session, allocation))

    app.status = "Decided"
    app.decision = "Granted"
    session.commit()
    fp_after = compute_context_fingerprint(build_allocation_context(session, allocation))
    assert fp_before == fp_after


def test_fingerprint_case_e_needs_confirmation_status_hedged_not_silently_trusted(session):
    """A needs_confirmation Site's Application status DOES enter the
    context (so the prompt can still describe it, hedged) but must remain
    marked pending - never silently promoted to a settled fact - and a
    change to it still legitimately moves the fingerprint (it is real
    information a customer-facing summary should reflect, just always
    described as uncertain)."""
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="needs_confirmation")
    app = _make_app(session, site.id, "APP/PENDING", units=100, status="Under Consultation")
    session.commit()

    context = build_allocation_context(session, allocation)
    assert context.disputed_site_count == 1
    site_entry = context.sites[0]
    assert site_entry.relationship_review_status == "needs_confirmation"
    assert site_entry.representative_application.status == "Under Consultation"

    prompt = build_summary_prompt(context)
    assert "PENDING CONFIRMATION - do not present as settled" in prompt

    fp_before = compute_context_fingerprint(context)
    app.status = "Decided"
    app.decision = "Granted"
    session.commit()
    fp_after = compute_context_fingerprint(build_allocation_context(session, allocation))
    assert fp_before != fp_after


def test_fingerprint_stable_for_non_material_field_changes(session):
    """application_received and proposal wording are deliberately excluded
    from the fingerprint - neither changes what the summary would say."""
    allocation, app = _single_site_allocation_with_app(
        session, status="Decided", decision="Granted", proposal="Original wording.",
    )
    app.application_received = "01 Jan 2024"
    session.commit()
    fp_before = compute_context_fingerprint(build_allocation_context(session, allocation))

    app.application_received = "02 Jan 2024"  # a correction - non-material
    app.proposal = "Original wording, lightly corrected."
    session.commit()
    fp_after = compute_context_fingerprint(build_allocation_context(session, allocation))
    assert fp_before == fp_after
