import json

from app.db.models import LocalPlan, LocalPlanSite, Site
from app.policy.site_view import build_site_policy_intelligence


def _make_site(session):
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    return site


def test_site_policy_display_carries_full_source_traceability(session):
    site = _make_site(session)
    plan = LocalPlan(
        council_code="testcouncil", plan_name="Test Local Plan", status="examination", raw_status="Examination in Public",
        last_checked=None,
    )
    session.add(plan)
    session.commit()

    allocation = LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan.id, matched_site_id=site.id,
        policy_reference="HOM 2.30", site_name="Sanderling Road", minimum_dwellings=40,
        indicative_capacity=45, maximum_capacity=50, category="List 2: Grey belt",
        plan_name="Test Local Plan", plan_status="examination",
        allocation_status="submitted_allocation", raw_allocation_status="Submitted allocation",
        source_document_url="https://example.invalid/plan.pdf", source_page=112,
        match_confidence=92.0, progression_signal="advanced",
        progression_reasons=json.dumps(["Local Plan stage is 'examination'."]),
    )
    session.add(allocation)
    session.commit()

    [row] = build_site_policy_intelligence([allocation])

    # Every field Part 12 asks the Site page to show:
    assert row["plan_name"] == "Test Local Plan"
    assert row["plan_status"] == "examination"
    assert row["allocation_reference"] == "HOM 2.30"
    assert row["allocation_status"] == "submitted_allocation"
    assert row["progression_signal"] == "advanced"
    assert row["progression_reasons"] == ["Local Plan stage is 'examination'."]
    assert row["minimum_dwellings"] == 40
    assert row["indicative_capacity"] == 45
    assert row["maximum_capacity"] == 50

    # Part 13 - source traceability, never detached from evidence:
    assert row["source_page"] == 112
    assert row["source_document_url"] == "https://example.invalid/plan.pdf"
    assert row["match_confidence"] == 92.0
    assert row["policy_reference"] == "HOM 2.30"


def test_site_policy_display_falls_back_gracefully_without_a_local_plan_link(session):
    # An allocation that predates this sprint's migration (local_plan_id
    # still null) must still render something sensible, not crash.
    site = _make_site(session)
    allocation = LocalPlanSite(
        council_code="testcouncil", matched_site_id=site.id,
        policy_reference="HOM 2.31", site_name="Legacy Site",
        plan_name="Legacy Local Plan", plan_status="draft",
    )
    session.add(allocation)
    session.commit()

    [row] = build_site_policy_intelligence([allocation])
    assert row["plan_name"] == "Legacy Local Plan"
    assert row["plan_raw_status"] == "draft"
    assert row["progression_reasons"] == []


def test_site_policy_display_handles_no_allocations():
    assert build_site_policy_intelligence([]) == []
