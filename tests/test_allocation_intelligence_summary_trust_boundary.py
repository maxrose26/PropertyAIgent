"""AI Allocation Intelligence Summary - Final Pre-Merge Amendment tests:
"needs_confirmation Trust Boundary". A needs_confirmation AllocationSite
Relationship (or a needs_review ControlRelationship attached to a Site
that only reached this allocation via a disputed relationship) must never
enter AllocationIntelligenceContext in the SAME Application/ownership-
shaped structure trusted evidence uses - not even hedged by a text label.
The deterministic context structure itself must enforce the distinction;
prompt wording is a second, reinforcing layer, never the only one.

No real OpenAI call anywhere - fake clients only, matching the
established pattern from tests/test_allocation_intelligence_summary.py."""
from __future__ import annotations

from app.db.models import (
    AllocationSiteRelationship, Application, Council, ControlRelationship, LocalPlan, LocalPlanSite,
    SchemeIntelligence, Site,
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


def _make_app(session, site_id, reference, *, units=None, status=None, decision=None, complete=True, council_code="testcouncil") -> Application:
    app = Application(council_code=council_code, reference=reference, site_id=site_id, status=status, decision=decision,
                       application_category="primary_residential")
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


# ---------------------------------------------------------------------------
# Item 1/2 - trusted (auto_applied / confirmed) relationship behaviour
# ---------------------------------------------------------------------------


def test_auto_applied_relationship_enters_factual_context(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="auto_applied")
    _make_app(session, site.id, "APP/1", units=100, status="Decided", decision="Granted")
    session.commit()

    context = build_allocation_context(session, allocation)
    site_entry = context.sites[0]
    assert site_entry.capacity_known is True
    assert site_entry.capacity == 100
    assert site_entry.representative_application is not None
    assert site_entry.representative_application.status == "Decided"
    assert site_entry.representative_application.decision == "Granted"

    fp_before = compute_context_fingerprint(context)
    app = session.query(Application).filter_by(reference="APP/1").one()
    app.decision = "Refuse"
    session.commit()
    fp_after = compute_context_fingerprint(build_allocation_context(session, allocation))
    assert fp_before != fp_after


def test_confirmed_relationship_same_trusted_behaviour(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="confirmed")
    _make_app(session, site.id, "APP/1", units=100, status="Under Consultation")
    session.commit()

    context = build_allocation_context(session, allocation)
    site_entry = context.sites[0]
    assert site_entry.representative_application is not None
    assert site_entry.representative_application.status == "Under Consultation"


# ---------------------------------------------------------------------------
# Item 3/4 - needs_confirmation relationship: structural exclusion
# ---------------------------------------------------------------------------


def test_needs_confirmation_relationship_excluded_from_factual_context(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="needs_confirmation")
    _make_app(session, site.id, "APP/DISPUTED", units=250, status="Under Consultation")
    session.commit()

    context = build_allocation_context(session, allocation)
    assert context.disputed_site_count == 1
    site_entry = context.sites[0]
    assert site_entry.relationship_review_status == "needs_confirmation"
    # Structural exclusion - not merely hedged text.
    assert site_entry.representative_application is None
    assert site_entry.other_applications_by_category == {}
    assert site_entry.capacity_known is False
    assert site_entry.capacity is None
    assert site_entry.application_references == []

    prompt = build_summary_prompt(context)
    assert "PENDING CONFIRMATION - do not present as settled" in prompt
    assert "APP/DISPUTED" not in prompt
    assert "250" not in prompt
    assert "Under Consultation" not in prompt
    assert "potential planning activity may exist" in prompt.lower()


def test_needs_confirmation_underlying_application_status_change_no_fingerprint_change(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="needs_confirmation")
    _make_app(session, site.id, "APP/DISPUTED", units=250, status="Under Consultation")
    session.commit()
    fp_before = compute_context_fingerprint(build_allocation_context(session, allocation))

    app = session.query(Application).filter_by(reference="APP/DISPUTED").one()
    app.status = "Decided"
    app.decision = "Granted"
    session.commit()
    fp_after = compute_context_fingerprint(build_allocation_context(session, allocation))
    assert fp_before == fp_after  # disputed facts changing underneath are not exposed, so no regeneration


# ---------------------------------------------------------------------------
# Item 5 - needs_confirmation -> trusted transition
# ---------------------------------------------------------------------------


def test_needs_confirmation_promoted_to_auto_applied_changes_context_and_fingerprint(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    rel = _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="needs_confirmation")
    _make_app(session, site.id, "APP/NOW-TRUSTED", units=100, status="Decided", decision="Granted")
    session.commit()

    fp_before = compute_context_fingerprint(build_allocation_context(session, allocation))
    context_before = build_allocation_context(session, allocation)
    assert context_before.sites[0].representative_application is None

    rel.review_status = "auto_applied"
    session.commit()

    context_after = build_allocation_context(session, allocation)
    assert context_after.sites[0].representative_application is not None
    assert context_after.sites[0].representative_application.reference == "APP/NOW-TRUSTED"
    assert context_after.disputed_site_count == 0
    fp_after = compute_context_fingerprint(context_after)
    assert fp_before != fp_after


# ---------------------------------------------------------------------------
# Item 6 - needs_confirmation -> rejected transition
# ---------------------------------------------------------------------------


def test_needs_confirmation_downgraded_to_rejected_removes_uncertainty_signal(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    rel = _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="needs_confirmation")
    _make_app(session, site.id, "APP/1", units=100)
    session.commit()

    fp_before = compute_context_fingerprint(build_allocation_context(session, allocation))
    context_before = build_allocation_context(session, allocation)
    assert context_before.disputed_site_count == 1

    rel.review_status = "rejected"
    session.commit()

    context_after = build_allocation_context(session, allocation)
    assert context_after.disputed_site_count == 0
    assert context_after.sites == []
    fp_after = compute_context_fingerprint(context_after)
    assert fp_before != fp_after


# ---------------------------------------------------------------------------
# Item 7 - rejected relationship: fully excluded, no fingerprint contribution
# ---------------------------------------------------------------------------


def test_rejected_relationship_absent_from_factual_and_uncertainty_context(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="rejected")
    _make_app(session, site.id, "APP/REJECTED", units=100, status="Decided", decision="Granted")
    session.commit()

    context = build_allocation_context(session, allocation)
    assert context.sites == []
    assert context.disputed_site_count == 0
    prompt = build_summary_prompt(context)
    assert "APP/REJECTED" not in prompt


def test_rejected_relationship_application_change_does_not_affect_fingerprint(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="rejected")
    _make_app(session, site.id, "APP/REJECTED", units=100, status="Under Consultation")
    session.commit()
    fp_before = compute_context_fingerprint(build_allocation_context(session, allocation))

    app = session.query(Application).filter_by(reference="APP/REJECTED").one()
    app.status = "Decided"
    app.decision = "Granted"
    session.commit()
    fp_after = compute_context_fingerprint(build_allocation_context(session, allocation))
    assert fp_before == fp_after


def test_unrelated_application_change_does_not_affect_fingerprint(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session, "Related Site")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    _make_app(session, site.id, "APP/1", units=100, status="Decided")
    session.commit()
    fp_before = compute_context_fingerprint(build_allocation_context(session, allocation))

    unrelated_site = _make_site(session, "Unrelated Site")
    unrelated_app = _make_app(session, unrelated_site.id, "APP/UNRELATED", units=999, status="Under Consultation")
    session.commit()
    unrelated_app.status = "Decided"
    unrelated_app.decision = "Granted"
    session.commit()
    fp_after = compute_context_fingerprint(build_allocation_context(session, allocation))
    assert fp_before == fp_after


# ---------------------------------------------------------------------------
# Item 8 - mixed allocation: one trusted + one disputed relationship
# ---------------------------------------------------------------------------


def test_mixed_trusted_and_disputed_relationships_do_not_contaminate_each_other(session):
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
    assert len(context.sites) == 2
    assert context.disputed_site_count == 1

    by_status = {s.relationship_review_status: s for s in context.sites}
    trusted_entry = by_status["auto_applied"]
    disputed_entry = by_status["needs_confirmation"]

    assert trusted_entry.representative_application is not None
    assert trusted_entry.representative_application.reference == "APP/TRUSTED"
    assert trusted_entry.capacity == 200

    assert disputed_entry.representative_application is None
    assert disputed_entry.capacity is None

    # The trusted Site's own capacity is unaffected by the disputed Site's
    # existence - development coverage arithmetic scope is untouched by
    # this amendment (Section 4).
    prompt = build_summary_prompt(context)
    assert "APP/TRUSTED" in prompt
    assert "APP/DISPUTED" not in prompt
    assert "500" not in prompt


# ---------------------------------------------------------------------------
# Item 9/10 - ownership/control trust boundary
# ---------------------------------------------------------------------------


def test_ownership_needs_confirmation_relationship_does_not_become_accepted_fact(session):
    """An accepted (auto_applied) ControlRelationship attached to a Site
    that only reached this allocation via a needs_confirmation
    AllocationSiteRelationship must NOT appear as factual ownership - the
    Site-level dispute overrides the ControlRelationship's own apparently-
    trusted status."""
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="needs_confirmation")
    app = _make_app(session, site.id, "APP/1", units=100)
    _make_control_relationship(session, site_id=site.id, application_id=app.id, entity_name_raw="Disputed Developer Ltd",
                                role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER", review_status="auto_applied")
    session.commit()

    context = build_allocation_context(session, allocation)
    assert context.ownership_entities == []
    assert context.ownership_review_pending_count == 1

    prompt = build_summary_prompt(context)
    assert "Disputed Developer Ltd" not in prompt


def test_rejected_control_relationship_remains_excluded(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="auto_applied")
    app = _make_app(session, site.id, "APP/1", units=100)
    _make_control_relationship(session, site_id=site.id, application_id=app.id, entity_name_raw="Rejected Entity Ltd",
                                role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER", review_status="rejected")
    session.commit()

    context = build_allocation_context(session, allocation)
    assert context.ownership_entities == []
    prompt = build_summary_prompt(context)
    assert "Rejected Entity Ltd" not in prompt


def test_trusted_site_ownership_still_accepted_when_site_is_trusted(session):
    """Regression - the fix must not over-correct: a genuinely trusted
    Site's accepted ControlRelationship must still surface normally."""
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="auto_applied")
    app = _make_app(session, site.id, "APP/1", units=100)
    _make_control_relationship(session, site_id=site.id, application_id=app.id, entity_name_raw="Trusted Developer Ltd",
                                role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER", review_status="auto_applied")
    session.commit()

    context = build_allocation_context(session, allocation)
    assert len(context.ownership_entities) == 1
    assert context.ownership_entities[0].entity_name_raw == "Trusted Developer Ltd"
    assert context.ownership_entities[0].role_label == "S106 Developer"

    prompt = build_summary_prompt(context)
    assert "Trusted Developer Ltd" in prompt
