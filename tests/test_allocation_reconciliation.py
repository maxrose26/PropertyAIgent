"""Sprint 3E ("Joint Plan Support and Bury Allocation Reconciliation") Part
5/6/9 tests. Uses an in-test fixture config shaped like config/bury_
allocation_reconciliation.yaml, exercising app.policy.allocation_
reconciliation directly against seeded LocalPlanSite rows - never reads a
live website or even the real PDF (routine tests must not depend on either).
A separate sanity test checks the real shipped config file's structure.
"""
from __future__ import annotations

import json

from sqlalchemy import select

from app.db.models import AllocationRelationship, LocalPlan, LocalPlanSite, PolicyChangeEvent
from app.policy.allocation_reconciliation import load_reconciliation_config, propose_reconciliations
from app.policy.review import approve_change

# A fixture excerpt standing in for the real Bury Local Plan page 22 text -
# same shape/style as the real primary-source finding, without depending on
# the actual PDF being present in the test environment.
FIXTURE_EXCERPT = (
    "PfE identifies several strategic housing allocations on land that was "
    "previously designated as Green Belt at Fixtureham, Testley, and Sampleford."
)


def _seed_bury_style_plans_and_allocations(session):
    bury_plan = LocalPlan(council_code="testcouncil", plan_name="Bury Local Plan", status="proposed_submission")
    pfe_plan = LocalPlan(
        council_code="testcouncil", plan_name="Places for Everyone Joint Development Plan (Bury allocations)",
        plan_version="2022-2039", status="adopted",
    )
    session.add_all([bury_plan, pfe_plan])
    session.commit()

    fixtureham_bury = LocalPlanSite(
        council_code="testcouncil", local_plan_id=bury_plan.id, policy_reference=None, site_name="Fixtureham",
        plan_name="Bury Local Plan", plan_status="proposed_submission",
    )
    fixtureham_pfe = LocalPlanSite(
        council_code="testcouncil", local_plan_id=pfe_plan.id, policy_reference="JPA 7", site_name="Fixtureham",
        plan_name="Places for Everyone Joint Development Plan (Bury allocations)", plan_status="adopted",
    )
    sampleford_bury = LocalPlanSite(
        council_code="testcouncil", local_plan_id=bury_plan.id, policy_reference=None, site_name="Sampleford",
        plan_name="Bury Local Plan", plan_status="proposed_submission",
    )
    northern_gateway = LocalPlanSite(
        council_code="testcouncil", local_plan_id=bury_plan.id, policy_reference="JPA1.1", site_name="Northern Gateway",
        plan_name="Bury Local Plan", plan_status="proposed_submission",
    )
    session.add_all([fixtureham_bury, fixtureham_pfe, sampleford_bury, northern_gateway])
    session.commit()
    return {
        "bury_plan": bury_plan, "pfe_plan": pfe_plan,
        "fixtureham_bury": fixtureham_bury, "fixtureham_pfe": fixtureham_pfe,
        "sampleford_bury": sampleford_bury, "northern_gateway": northern_gateway,
    }


def _fixture_config():
    return [
        {
            "council_code": "testcouncil", "plan_name": "Bury Local Plan", "site_name": "Fixtureham",
            "policy_reference": None, "classification": "duplicate_of_other_plan",
            "relationship_type": "same_physical_site",
            "to_plan_name": "Places for Everyone Joint Development Plan (Bury allocations)",
            "to_site_name": "Fixtureham", "to_policy_reference": "JPA 7",
            "confidence": 0.95, "note": "Same physical site as the genuine JPA7 allocation.",
            "source_document_url": "https://example.invalid/bury-local-plan.pdf",
            "source_page": 22, "source_excerpt": FIXTURE_EXCERPT,
        },
        {
            # Contextual-only, no matching "to" allocation exists at all -
            # mirrors the real Castle Road (Unsworth) finding.
            "council_code": "testcouncil", "plan_name": "Bury Local Plan", "site_name": "Sampleford",
            "policy_reference": None, "classification": "contextual_reference",
            "relationship_type": "referenced_by",
            "to_plan_name": "Bury Local Plan", "to_site_name": "Northern Gateway", "to_policy_reference": "JPA1.1",
            "confidence": 0.8, "note": "Sub-parcel described within the Northern Gateway allocation narrative.",
            "source_document_url": "https://example.invalid/bury-local-plan.pdf",
            "source_page": 22, "source_excerpt": FIXTURE_EXCERPT,
        },
    ]


def test_page_evidence_classification_creates_correctly_typed_proposals(session):
    seeds = _seed_bury_style_plans_and_allocations(session)
    result = propose_reconciliations(session, config=_fixture_config())

    assert result["proposals_created"] == 2
    assert result["allocations_not_found"] == []

    event = session.execute(
        select(PolicyChangeEvent).where(PolicyChangeEvent.allocation_id == seeds["fixtureham_bury"].id)
    ).scalar_one()
    assert event.event_type == "duplicate_name_reconciliation_proposed"
    assert event.review_status == "needs_review"
    proposed = json.loads(event.proposed_data)
    assert proposed["duplicate_classification"] == "duplicate_of_other_plan"

    contextual_event = session.execute(
        select(PolicyChangeEvent).where(PolicyChangeEvent.allocation_id == seeds["sampleford_bury"].id)
    ).scalar_one()
    assert json.loads(contextual_event.proposed_data)["duplicate_classification"] == "contextual_reference"


def test_reconciliation_preserves_provenance(session):
    seeds = _seed_bury_style_plans_and_allocations(session)
    propose_reconciliations(session, config=_fixture_config())

    event = session.execute(
        select(PolicyChangeEvent).where(PolicyChangeEvent.allocation_id == seeds["fixtureham_bury"].id)
    ).scalar_one()
    assert event.source_document_url == "https://example.invalid/bury-local-plan.pdf"
    assert event.source_page == 22
    assert event.source_excerpt == FIXTURE_EXCERPT
    assert event.extraction_method == "manual_primary_source_review"
    assert event.confidence == 0.95

    relationship = session.execute(
        select(AllocationRelationship).where(AllocationRelationship.from_allocation_id == seeds["fixtureham_bury"].id)
    ).scalar_one()
    assert relationship.source_excerpt == FIXTURE_EXCERPT
    assert relationship.source_page == 22
    assert relationship.relationship_type == "same_physical_site"
    assert relationship.to_allocation_id == seeds["fixtureham_pfe"].id


def test_relationship_supports_null_to_allocation_for_contextual_only_finding(session):
    seeds = _seed_bury_style_plans_and_allocations(session)
    config = _fixture_config()
    config[1]["to_site_name"] = None  # simulate: no matching row exists anywhere, unlike the Northern Gateway case
    propose_reconciliations(session, config=config)

    relationship = session.execute(
        select(AllocationRelationship).where(AllocationRelationship.from_allocation_id == seeds["sampleford_bury"].id)
    ).scalar_one()
    assert relationship.to_allocation_id is None
    assert relationship.relationship_type == "referenced_by"


def test_reconciliation_does_not_touch_trusted_data_until_approved(session):
    seeds = _seed_bury_style_plans_and_allocations(session)
    propose_reconciliations(session, config=_fixture_config())

    session.refresh(seeds["fixtureham_bury"])
    session.refresh(seeds["sampleford_bury"])
    assert seeds["fixtureham_bury"].duplicate_classification is None
    assert seeds["sampleford_bury"].duplicate_classification is None
    # Also never touches site_name, capacity, or the counterpart allocation.
    assert seeds["fixtureham_bury"].site_name == "Fixtureham"
    session.refresh(seeds["fixtureham_pfe"])
    assert seeds["fixtureham_pfe"].site_name == "Fixtureham"


def test_reconciliation_is_idempotent(session):
    _seed_bury_style_plans_and_allocations(session)
    config = _fixture_config()
    first = propose_reconciliations(session, config=config)
    second = propose_reconciliations(session, config=config)

    assert first["proposals_created"] == 2
    assert second["proposals_created"] == 0
    assert second["skipped_already_proposed"] == 2

    all_events = session.execute(
        select(PolicyChangeEvent).where(PolicyChangeEvent.event_type == "duplicate_name_reconciliation_proposed")
    ).scalars().all()
    assert len(all_events) == 2  # not 4


def test_no_automatic_deletion_or_merge_of_duplicate_name_records(session):
    seeds = _seed_bury_style_plans_and_allocations(session)
    before_count = len(session.execute(select(LocalPlanSite)).scalars().all())

    propose_reconciliations(session, config=_fixture_config())

    after_count = len(session.execute(select(LocalPlanSite)).scalars().all())
    assert after_count == before_count  # no row deleted, none merged away

    # Both the "duplicate" Bury-side row and its PfE counterpart still
    # independently exist, each queryable on its own terms.
    still_there = session.get(LocalPlanSite, seeds["fixtureham_bury"].id)
    still_there_pfe = session.get(LocalPlanSite, seeds["fixtureham_pfe"].id)
    assert still_there is not None
    assert still_there_pfe is not None
    assert still_there.id != still_there_pfe.id


def test_allocation_not_found_is_reported_not_raised(session):
    _seed_bury_style_plans_and_allocations(session)
    config = _fixture_config()
    config.append({
        "council_code": "testcouncil", "plan_name": "Bury Local Plan", "site_name": "Nonexistent Site",
        "policy_reference": None, "classification": "uncertain_needs_review", "relationship_type": "uncertain",
        "note": "Does not exist in this fixture.",
    })
    result = propose_reconciliations(session, config=config)
    assert result["proposals_created"] == 2  # the two real ones
    assert "testcouncil/Bury Local Plan/Nonexistent Site" in result["allocations_not_found"]


def test_approving_reconciliation_applies_classification_via_existing_review_flow(session):
    seeds = _seed_bury_style_plans_and_allocations(session)
    propose_reconciliations(session, config=_fixture_config())

    event = session.execute(
        select(PolicyChangeEvent).where(PolicyChangeEvent.allocation_id == seeds["fixtureham_bury"].id)
    ).scalar_one()
    approve_change(session, event, note="Confirmed against primary source.")

    session.refresh(seeds["fixtureham_bury"])
    assert seeds["fixtureham_bury"].duplicate_classification == "duplicate_of_other_plan"
    assert "genuine JPA7 allocation" in seeds["fixtureham_bury"].duplicate_classification_note
    assert event.review_status == "confirmed"


def test_real_shipped_reconciliation_config_is_well_formed():
    # Sanity check on the actual config/bury_allocation_reconciliation.yaml
    # shipped with this sprint - structure only, not a live-data test.
    entries = load_reconciliation_config()
    assert len(entries) == 5
    site_names = {e["site_name"] for e in entries}
    assert site_names == {"Seedfield", "Walshaw", "Elton Reservoir", "Castle Road (Unsworth)", "Simister"}
    classifications = {e["site_name"]: e["classification"] for e in entries}
    assert classifications["Seedfield"] == "duplicate_of_other_plan"
    assert classifications["Walshaw"] == "duplicate_of_other_plan"
    assert classifications["Elton Reservoir"] == "duplicate_of_other_plan"
    assert classifications["Castle Road (Unsworth)"] == "contextual_reference"
    assert classifications["Simister"] == "contextual_reference"
    for entry in entries:
        assert entry.get("source_excerpt"), f"{entry['site_name']} is missing its evidence excerpt"
        assert entry.get("source_page"), f"{entry['site_name']} is missing its source page"
