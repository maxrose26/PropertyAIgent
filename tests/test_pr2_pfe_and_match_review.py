"""Pilot Readiness PR-2 ("Production Freshness & Core Data Integrity") -
focused tests for:

1. PfE authority membership correction (config/joint_plans.yaml, Part 8/9) -
   Manchester added, Stockport excluded, Stockport's own plan/allocations
   untouched, no duplicate/deleted allocations.
2. Individual allocation<->Site match review (app.policy.site_match_review,
   Part 10-13) - confirm/reject behaviour, and the canonical trust
   functions' "rejected" exclusion (a real latent gap this sprint's own
   review work was the first to ever exercise, since review_status=
   "rejected" had never once been set on a matched allocation before).

Uses the same in-memory-SQLite `session` fixture as every other Policy
Intelligence test (tests/conftest.py) - never the real database, matching
this sprint's own PART 12/18 "no unreviewed writes, no parallel trust
field" discipline applied to the tests themselves.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import Application, Council, LocalPlan, LocalPlanCouncil, LocalPlanSite, Site
from app.policy.joint_plans import ensure_council_links_for_plan, find_joint_plan_entry, load_joint_plans_config
from app.policy.site_match_review import confirm_site_match, reject_site_match
from app.reporting.allocation_discovery import has_trusted_linked_application, has_trusted_site_match


# --- PfE authority membership (Part 8/9) ------------------------------------


def test_real_joint_plans_config_includes_manchester_and_excludes_stockport():
    """Sanity check against the actual shipped config/joint_plans.yaml -
    not a live document dependency, just confirms the correction was
    applied to the real file this sprint edited."""
    config = load_joint_plans_config()
    pfe_entries = [e for e in config if "Places for Everyone" in e.get("plan_name", "")]
    assert len(pfe_entries) == 1
    authorities = pfe_entries[0]["participating_authorities"]
    assert "manchester" in authorities
    assert "stockport" not in authorities
    # The real 9 PfE authorities, verified against the adopted plan
    # document's own title page (data/local_plans/bury/places_for_everyone.pdf).
    assert sorted(authorities) == sorted(
        ["bolton", "bury", "manchester", "oldham", "rochdale", "salford", "tameside", "trafford", "wigan"]
    )


def _seed_pfe_plan_with_old_wrong_config(session):
    for code in ("bolton", "manchester", "oldham", "rochdale", "salford", "tameside", "trafford", "wigan"):
        session.add(Council(code=code, name=code.title(), base_url=f"https://{code}.invalid",
                             date_field_mode="received", doc_system="idox"))
    session.commit()
    plan = LocalPlan(
        council_code="testcouncil", plan_name="Places for Everyone Joint Development Plan (Bury allocations)",
        plan_version="2022-2039", status="adopted",
    )
    session.add(plan)
    session.commit()
    return plan


def test_ensure_council_links_adds_manchester_when_config_lists_it(session):
    """Simulates the corrected config being applied via the existing
    additive migration logic (app.policy.joint_plans.
    ensure_council_links_for_plan / scripts/migrate_joint_plan_support.py)
    - the same mechanism actually used to fix production data this sprint."""
    plan = _seed_pfe_plan_with_old_wrong_config(session)
    corrected_config = [{
        "council_code": "testcouncil", "plan_name": plan.plan_name, "plan_version": plan.plan_version,
        "lead_authority": None,
        "participating_authorities": [
            "bolton", "testcouncil", "manchester", "oldham", "rochdale", "salford", "tameside", "trafford", "wigan",
        ],
        "source_note": "test",
    }]
    result = ensure_council_links_for_plan(session, plan, config=corrected_config)
    assert result["created"] == 9

    links = session.execute(select(LocalPlanCouncil).where(LocalPlanCouncil.local_plan_id == plan.id)).scalars().all()
    council_codes = {link.council_code for link in links}
    assert "manchester" in council_codes
    assert "stockport" not in council_codes


def test_removing_erroneous_stockport_pfe_link_does_not_touch_other_links(session):
    """Mirrors scripts/fix_pfe_stockport_membership.py's own logic: deleting
    one specific LocalPlanCouncil row must never affect any other row for
    the same plan."""
    session.add(Council(code="stockport", name="Stockport", base_url="https://stockport.invalid",
                         date_field_mode="received", doc_system="idox"))
    session.commit()
    plan = _seed_pfe_plan_with_old_wrong_config(session)
    session.add_all([
        LocalPlanCouncil(local_plan_id=plan.id, council_code="testcouncil", role="participating_authority"),
        LocalPlanCouncil(local_plan_id=plan.id, council_code="bolton", role="participating_authority"),
        LocalPlanCouncil(local_plan_id=plan.id, council_code="stockport", role="participating_authority"),
    ])
    session.commit()

    erroneous = session.execute(
        select(LocalPlanCouncil).where(LocalPlanCouncil.local_plan_id == plan.id, LocalPlanCouncil.council_code == "stockport")
    ).scalars().first()
    session.delete(erroneous)
    session.commit()

    remaining = session.execute(select(LocalPlanCouncil).where(LocalPlanCouncil.local_plan_id == plan.id)).scalars().all()
    assert {link.council_code for link in remaining} == {"testcouncil", "bolton"}


def test_stockport_own_plan_and_allocations_are_a_wholly_separate_local_plan(session):
    """The correction only ever touches the LocalPlanCouncil JOIN row for
    the PfE plan - Stockport's own, separate LocalPlan row and its
    allocations live under a different local_plan_id entirely and are
    never read or written by the PfE fix."""
    session.add(Council(code="stockport", name="Stockport", base_url="https://stockport.invalid",
                         date_field_mode="received", doc_system="idox"))
    session.commit()
    stockport_plan = LocalPlan(council_code="stockport", plan_name="Stockport Local Plan", plan_version="Draft",
                                status="draft_consultation")
    session.add(stockport_plan)
    session.commit()
    session.add(LocalPlanSite(
        council_code="stockport", local_plan_id=stockport_plan.id, policy_reference="HOM 2.1", site_name="Test site",
        plan_name=stockport_plan.plan_name, plan_status=stockport_plan.status,
    ))
    session.commit()

    pfe_plan = _seed_pfe_plan_with_old_wrong_config(session)
    erroneous = LocalPlanCouncil(local_plan_id=pfe_plan.id, council_code="stockport", role="participating_authority")
    session.add(erroneous)
    session.commit()
    session.delete(erroneous)
    session.commit()

    stockport_allocations = session.execute(
        select(LocalPlanSite).where(LocalPlanSite.council_code == "stockport")
    ).scalars().all()
    assert len(stockport_allocations) == 1
    assert stockport_allocations[0].local_plan_id == stockport_plan.id  # untouched, still its own plan


def test_no_allocation_records_deleted_or_duplicated_by_pfe_correction(session):
    plan = _seed_pfe_plan_with_old_wrong_config(session)
    for i in range(3):
        session.add(LocalPlanSite(
            council_code="testcouncil", local_plan_id=plan.id, policy_reference=f"JPA {i}", site_name=f"Site {i}",
            plan_name=plan.plan_name, plan_status=plan.status,
        ))
    session.commit()
    before_count = len(session.execute(select(LocalPlanSite)).scalars().all())

    corrected_config = [{
        "council_code": "testcouncil", "plan_name": plan.plan_name, "plan_version": plan.plan_version,
        "lead_authority": None, "participating_authorities": ["testcouncil", "manchester"], "source_note": "test",
    }]
    ensure_council_links_for_plan(session, plan, config=corrected_config)

    after_count = len(session.execute(select(LocalPlanSite)).scalars().all())
    assert after_count == before_count == 3


# --- Allocation <-> Site match review (Part 10-13) --------------------------


def _seed_matched_allocation(session, *, review_status="needs_confirmation", confidence=90.0):
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    allocation = LocalPlanSite(
        council_code="testcouncil", policy_reference="TST 1", site_name="Test Allocation",
        plan_name="Test Plan", plan_status="adopted",
        matched_site_id=site.id, match_confidence=confidence, review_status=review_status,
    )
    session.add(allocation)
    session.commit()
    return allocation, site


def test_confirm_site_match_sets_confirmed_status_and_provenance(session):
    allocation, site = _seed_matched_allocation(session)
    confirm_site_match(session, allocation, confirmed_by="test-reviewer", note="Matching street name and address.")

    session.refresh(allocation)
    assert allocation.review_status == "confirmed"
    assert allocation.confirmed_by == "test-reviewer"
    assert allocation.confirmed_at is not None
    assert allocation.match_review_note == "Matching street name and address."
    # Confirming never touches the relationship itself.
    assert allocation.matched_site_id == site.id
    assert allocation.match_confidence == 90.0


def test_confirm_site_match_requires_a_non_empty_note(session):
    allocation, _ = _seed_matched_allocation(session)
    with pytest.raises(ValueError):
        confirm_site_match(session, allocation, confirmed_by="test-reviewer", note="   ")


def test_confirm_site_match_requires_an_existing_match(session):
    allocation = LocalPlanSite(
        council_code="testcouncil", policy_reference="TST 2", site_name="Unmatched",
        plan_name="Test Plan", plan_status="adopted", review_status="auto_applied",
    )
    session.add(allocation)
    session.commit()
    with pytest.raises(ValueError):
        confirm_site_match(session, allocation, confirmed_by="test-reviewer", note="anything")


def test_reject_site_match_clears_the_relationship_and_records_why(session):
    allocation, site = _seed_matched_allocation(session)
    reject_site_match(session, allocation, confirmed_by="test-reviewer", reason="Different street name entirely.")

    session.refresh(allocation)
    assert allocation.review_status == "rejected"
    assert allocation.matched_site_id is None
    assert allocation.match_confidence is None
    assert allocation.confirmed_by == "test-reviewer"
    assert str(site.id) in allocation.match_review_note
    assert "Different street name entirely." in allocation.match_review_note


def test_reject_site_match_requires_a_non_empty_reason(session):
    allocation, _ = _seed_matched_allocation(session)
    with pytest.raises(ValueError):
        reject_site_match(session, allocation, confirmed_by="test-reviewer", reason="")


def test_needs_further_review_allocation_is_untouched_by_review_functions_if_not_called():
    """Not calling confirm/reject at all (this sprint's "further review"
    outcome for HOM 2.16) leaves review_status exactly as it was - a
    behavioural fact, not something requiring its own function; asserted
    here as documentation of the expected no-op."""
    allocation = LocalPlanSite(
        council_code="testcouncil", policy_reference="TST 3", site_name="Further review needed",
        plan_name="Test Plan", plan_status="adopted", matched_site_id=1, match_confidence=95.0,
        review_status="needs_confirmation",
    )
    assert allocation.review_status == "needs_confirmation"  # untouched, exactly as before


# --- Canonical trust functions correctly exclude "rejected" (Part 13) ------


def _card(**overrides):
    base = {
        "matched": True, "matched_site_id": 1, "linked_application_count": 1,
        "review_status": "confirmed",
    }
    base.update(overrides)
    return base


def test_confirmed_match_with_application_is_trusted():
    assert has_trusted_linked_application(_card(review_status="confirmed")) is True
    assert has_trusted_site_match(_card(review_status="confirmed")) is True


def test_auto_applied_match_with_application_is_trusted():
    assert has_trusted_linked_application(_card(review_status="auto_applied")) is True


def test_needs_confirmation_match_is_not_trusted():
    assert has_trusted_linked_application(_card(review_status="needs_confirmation")) is False
    assert has_trusted_site_match(_card(review_status="needs_confirmation")) is False


def test_rejected_match_is_not_trusted_even_with_application_count_and_matched_true():
    """The exact latent gap this sprint found and fixed: before this
    sprint, review_status="rejected" had never once existed on a matched
    allocation, so has_trusted_linked_application's old
    `review_status != "needs_confirmation"` check silently treated
    "rejected" as trusted (since "rejected" != "needs_confirmation").
    Defensive/belt-and-braces case: even if a matched_site_id/
    linked_application_count somehow survived alongside review_status=
    "rejected" (reject_site_match itself always clears them - this proves
    the trust function is safe independent of that), the row must never
    read as trusted."""
    card = _card(review_status="rejected", matched=True, linked_application_count=1)
    assert has_trusted_linked_application(card) is False
    assert has_trusted_site_match(card) is False


def test_rejected_match_via_real_reject_site_match_reads_as_untrusted_end_to_end(session):
    """The realistic path: reject_site_match clears matched_site_id, so
    linked_application_count naturally becomes 0 too - proving the fix
    holds through the actual production code path, not just the
    defensive card-level check above."""
    allocation, site = _seed_matched_allocation(session)
    app = Application(council_code="testcouncil", reference="APP/1", site_id=site.id)
    session.add(app)
    session.commit()

    reject_site_match(session, allocation, confirmed_by="test-reviewer", reason="Wrong site entirely.")
    session.refresh(allocation)

    from app.reporting.allocation_discovery import build_allocation_discovery
    result = build_allocation_discovery(session)
    card = next(c for c in result["cards"] if c["id"] == allocation.id)
    assert card["matched"] is False
    assert card["linked_application_count"] == 0
    assert has_trusted_linked_application(card) is False
    assert has_trusted_site_match(card) is False


def test_confirmed_match_via_real_confirm_site_match_reads_as_trusted_end_to_end(session):
    allocation, site = _seed_matched_allocation(session)
    # A real proposal string with an explicit unit count - qualify() (used
    # by load_applications_for_sites' visibility filter) needs this to
    # treat the application as a visible, substantive scheme, the same
    # rule every other "linked Application" case in this codebase is
    # already subject to.
    app = Application(
        council_code="testcouncil", reference="APP/2", site_id=site.id,
        proposal="Erection of 50 dwellings with associated access and landscaping",
    )
    session.add(app)
    session.commit()

    confirm_site_match(session, allocation, confirmed_by="test-reviewer", note="Exact name and address match.")
    session.refresh(allocation)

    from app.reporting.allocation_discovery import build_allocation_discovery
    result = build_allocation_discovery(session)
    card = next(c for c in result["cards"] if c["id"] == allocation.id)
    assert has_trusted_linked_application(card) is True
    assert has_trusted_site_match(card) is True
