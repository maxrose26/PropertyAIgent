"""Sprint 3G ("Places for Everyone Allocation Onboarding", Part 9) tests for
app.policy.pfe_allocation_onboarding. Uses an in-test fixture config shaped
like config/pfe_allocation_onboarding.yaml - never reads the real PDF or a
live website. A separate sanity test checks the real shipped config file's
structure only (no live dependency)."""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import AllocationRelationship, Council, LocalPlan, LocalPlanSite
from app.policy.pfe_allocation_onboarding import load_onboarding_config, onboard_pfe_allocations


def _add_council(session, code: str) -> Council:
    council = Council(
        code=code, name=code.title(), base_url=f"https://{code}.invalid",
        date_field_mode="received", doc_system="idox",
    )
    session.add(council)
    session.commit()
    return council


def _seed_pfe_plan(session) -> LocalPlan:
    plan = LocalPlan(
        council_code="bury", plan_name="Test Places for Everyone", plan_version="2022-2039",
        status="adopted", raw_status="Adopted (with effect from 21 March 2024)",
    )
    session.add(plan)
    session.commit()
    return plan


def _seed_bury_existing_allocations(session, plan: LocalPlan) -> list[LocalPlanSite]:
    """Mirrors the real, already-existing JPA 7/8/9 rows this module must
    never touch or recreate."""
    rows = [
        LocalPlanSite(
            council_code="bury", local_plan_id=plan.id, policy_reference=ref, site_name=name,
            plan_name=plan.plan_name, plan_status=plan.status,
        )
        for ref, name in [("JPA 7", "Elton Reservoir"), ("JPA 8", "Seedfield"), ("JPA 9", "Walshaw")]
    ]
    session.add_all(rows)
    session.commit()
    return rows


def _seed_bury_own_local_plan_northern_gateway(session) -> LocalPlanSite:
    bury_plan = LocalPlan(council_code="bury", plan_name="Bury Local Plan", status="proposed_submission")
    session.add(bury_plan)
    session.commit()
    row = LocalPlanSite(
        council_code="bury", local_plan_id=bury_plan.id, policy_reference="JPA1.1", site_name="Northern Gateway",
        plan_name="Bury Local Plan", plan_status="proposed_submission",
    )
    session.add(row)
    session.commit()
    return row


def _fixture_config():
    return {
        "plan_name": "Test Places for Everyone",
        "plan_version": "2022-2039",
        "single_authority_allocations": [
            {"policy_reference": "JPA 10", "site_name": "Beal Valley", "council_code": "oldham",
             "intended_use": "residential", "minimum_dwellings": 480, "category": "Strategic housing allocation",
             "source_page": 330},
            {"policy_reference": "JPA 24", "site_name": "Land at Hazelhurst Farm", "council_code": "salford",
             "intended_use": "residential", "minimum_dwellings": 400, "category": "Strategic housing allocation",
             "source_page": 406},
            {"policy_reference": "JPA 30", "site_name": "New Carrington", "council_code": "trafford",
             "intended_use": "mixed use", "minimum_dwellings": 5000, "category": "Mixed use", "source_page": 448},
        ],
        "cross_boundary_allocations": [
            {"policy_reference": "JPA 1.1", "site_name": "Heywood / Pilsworth (Northern Gateway)",
             "council_code": "rochdale", "intended_use": "employment", "minimum_dwellings": None,
             "category": "Cross Boundary", "source_page": 260, "review_status": "needs_confirmation",
             "confidence_note": "Attributed to Rochdale on place-name evidence.",
             "link_to_bury_local_plan_site": "Northern Gateway", "sibling_reference": "JPA 1.2"},
            {"policy_reference": "JPA 1.2", "site_name": "Simister and Bowlee (Northern Gateway)",
             "council_code": "bury", "intended_use": "residential", "minimum_dwellings": 1550,
             "category": "Cross Boundary", "source_page": 269, "review_status": "needs_confirmation",
             "confidence_note": "Corroborated by Bury's own Local Plan.",
             "link_to_bury_local_plan_site": "Northern Gateway", "sibling_reference": "JPA 1.1"},
        ],
    }


def _seed_all_councils(session):
    for code in ("oldham", "salford", "trafford", "rochdale", "bolton", "tameside", "wigan"):
        _add_council(session, code)


# --- 1. remaining authority onboarding (Part 1/2) ---------------------------

def test_onboards_single_authority_allocations_with_full_provenance(session):
    _seed_all_councils(session)
    plan = _seed_pfe_plan(session)
    _seed_bury_existing_allocations(session, plan)

    result = onboard_pfe_allocations(session, config=_fixture_config())

    assert result["created"] == 5  # 3 single-authority + 2 cross-boundary
    assert result["by_council"]["oldham"] == 1
    assert result["by_council"]["salford"] == 1
    assert result["by_council"]["trafford"] == 1

    beal_valley = session.execute(select(LocalPlanSite).where(LocalPlanSite.policy_reference == "JPA 10")).scalar_one()
    assert beal_valley.council_code == "oldham"
    assert beal_valley.site_name == "Beal Valley"
    assert beal_valley.minimum_dwellings == 480
    assert beal_valley.intended_use == "residential"
    assert beal_valley.source_page == 330
    assert beal_valley.source_document_url is not None
    assert beal_valley.local_plan_id == plan.id
    assert beal_valley.plan_name == plan.plan_name
    # Allocation status/progression are derived, never invented or defaulted to "adopted"
    assert beal_valley.allocation_status == "submitted_allocation"
    assert beal_valley.progression_signal == "unknown"


def test_bury_existing_allocations_are_never_touched_or_recreated(session):
    _seed_all_councils(session)
    plan = _seed_pfe_plan(session)
    bury_rows = _seed_bury_existing_allocations(session, plan)
    original_ids = {r.id for r in bury_rows}

    onboard_pfe_allocations(session, config=_fixture_config())

    all_bury_rows = session.execute(
        select(LocalPlanSite).where(LocalPlanSite.local_plan_id == plan.id, LocalPlanSite.council_code == "bury")
    ).scalars().all()
    # 3 original JPA7/8/9 + 1 new JPA1.2 (cross-boundary, correctly Bury) = 4
    assert len(all_bury_rows) == 4
    assert original_ids.issubset({r.id for r in all_bury_rows})
    for row in bury_rows:
        session.refresh(row)
        assert row.site_name in ("Elton Reservoir", "Seedfield", "Walshaw")  # untouched


# --- 2. cross-boundary allocations (Part 3) ---------------------------------

def test_cross_boundary_allocations_created_with_needs_confirmation(session):
    _seed_all_councils(session)
    plan = _seed_pfe_plan(session)
    _seed_bury_existing_allocations(session, plan)

    onboard_pfe_allocations(session, config=_fixture_config())

    jpa1_1 = session.execute(select(LocalPlanSite).where(LocalPlanSite.policy_reference == "JPA 1.1")).scalar_one()
    jpa1_2 = session.execute(select(LocalPlanSite).where(LocalPlanSite.policy_reference == "JPA 1.2")).scalar_one()
    assert jpa1_1.council_code == "rochdale"
    assert jpa1_1.review_status == "needs_confirmation"
    assert jpa1_2.council_code == "bury"
    assert jpa1_2.review_status == "needs_confirmation"


def test_northern_gateway_relationship_links_both_new_rows_and_bury_local_plan(session):
    _seed_all_councils(session)
    plan = _seed_pfe_plan(session)
    _seed_bury_existing_allocations(session, plan)
    bury_northern_gateway = _seed_bury_own_local_plan_northern_gateway(session)

    result = onboard_pfe_allocations(session, config=_fixture_config())
    assert result["relationships_created"] == 4  # 2x same_physical_site (1.1 and 1.2 each -> Bury row) + 2x sibling (1.1<->1.2, both directions counted once each entry)

    jpa1_1 = session.execute(select(LocalPlanSite).where(LocalPlanSite.policy_reference == "JPA 1.1")).scalar_one()
    jpa1_2 = session.execute(select(LocalPlanSite).where(LocalPlanSite.policy_reference == "JPA 1.2")).scalar_one()

    same_site_rels = session.execute(
        select(AllocationRelationship).where(AllocationRelationship.relationship_type == "same_physical_site")
    ).scalars().all()
    targets = {(r.from_allocation_id, r.to_allocation_id) for r in same_site_rels}
    assert (jpa1_1.id, bury_northern_gateway.id) in targets
    assert (jpa1_2.id, bury_northern_gateway.id) in targets

    sibling_rels = session.execute(
        select(AllocationRelationship).where(AllocationRelationship.relationship_type == "implemented_through_joint_plan")
    ).scalars().all()
    assert len(sibling_rels) >= 1  # JPA1.1 <-> JPA1.2 linked as siblings of the same MDZ


def test_bury_local_plan_row_is_never_duplicated_only_linked(session):
    _seed_all_councils(session)
    plan = _seed_pfe_plan(session)
    _seed_bury_existing_allocations(session, plan)
    _seed_bury_own_local_plan_northern_gateway(session)

    onboard_pfe_allocations(session, config=_fixture_config())

    bury_local_plan_rows = session.execute(
        select(LocalPlanSite).where(LocalPlanSite.plan_name == "Bury Local Plan", LocalPlanSite.site_name == "Northern Gateway")
    ).scalars().all()
    assert len(bury_local_plan_rows) == 1  # still exactly one - never duplicated


# --- 3. duplicate prevention / idempotent reruns (Part 8/9) -----------------

def test_rerun_creates_no_duplicate_local_plan_site_rows(session):
    _seed_all_councils(session)
    plan = _seed_pfe_plan(session)
    _seed_bury_existing_allocations(session, plan)
    config = _fixture_config()

    first = onboard_pfe_allocations(session, config=config)
    second = onboard_pfe_allocations(session, config=config)

    assert first["created"] == 5
    assert second["created"] == 0
    assert second["already_existed"] == 5

    all_rows = session.execute(select(LocalPlanSite).where(LocalPlanSite.local_plan_id == plan.id)).scalars().all()
    assert len(all_rows) == 3 + 5  # Bury's 3 existing + 5 new, not 3+10


def test_rerun_creates_no_duplicate_relationships(session):
    _seed_all_councils(session)
    plan = _seed_pfe_plan(session)
    _seed_bury_existing_allocations(session, plan)
    bury_northern_gateway = _seed_bury_own_local_plan_northern_gateway(session)
    config = _fixture_config()

    onboard_pfe_allocations(session, config=config)
    onboard_pfe_allocations(session, config=config)  # rerun

    all_rels = session.execute(select(AllocationRelationship)).scalars().all()
    # Same count as after the FIRST run - a rerun adds nothing new.
    jpa1_1 = session.execute(select(LocalPlanSite).where(LocalPlanSite.policy_reference == "JPA 1.1")).scalar_one()
    rels_from_jpa1_1 = [r for r in all_rels if r.from_allocation_id == jpa1_1.id]
    same_site = [r for r in rels_from_jpa1_1 if r.relationship_type == "same_physical_site"]
    assert len(same_site) == 1  # not duplicated on rerun


def test_dry_run_writes_nothing(session):
    _seed_all_councils(session)
    plan = _seed_pfe_plan(session)
    _seed_bury_existing_allocations(session, plan)

    result = onboard_pfe_allocations(session, config=_fixture_config(), dry_run=True)
    assert result["created"] == 5

    all_rows = session.execute(select(LocalPlanSite).where(LocalPlanSite.local_plan_id == plan.id)).scalars().all()
    assert len(all_rows) == 3  # only Bury's pre-existing rows - nothing written
    assert session.execute(select(AllocationRelationship)).scalars().all() == []


def test_plan_not_found_reported_not_raised(session):
    result = onboard_pfe_allocations(session, config=_fixture_config())
    assert result["plan_not_found"] is True
    assert result["created"] == 0


# --- 4. real shipped config sanity check (structure only, no live dependency) -

def test_real_shipped_config_is_well_formed():
    config = load_onboarding_config()
    single = config["single_authority_allocations"]
    cross = config["cross_boundary_allocations"]
    assert len(single) == 28  # Bolton 3 + Oldham 7 + Rochdale 7 + Salford 3 + Tameside 3 + Trafford 1 + Wigan 4
    assert len(cross) == 5  # JPA1.1, JPA1.2, JPA2, JPA3.1, JPA3.2

    councils_seen = {e["council_code"] for e in single}
    assert councils_seen == {"bolton", "oldham", "rochdale", "salford", "tameside", "trafford", "wigan"}

    for entry in single + cross:
        assert entry.get("policy_reference")
        assert entry.get("site_name")
        assert entry.get("council_code")
        assert entry.get("source_page")
        assert entry.get("intended_use") in ("residential", "employment", "mixed use")

    for entry in cross:
        assert entry.get("review_status") == "needs_confirmation"
        assert entry.get("confidence_note")

    references = {e["policy_reference"] for e in single + cross}
    assert "JPA 7" not in references  # Bury's existing allocations never recreated
    assert "JPA 8" not in references
    assert "JPA 9" not in references
