"""Tests for app.reporting.dashboard (Sprint 4.2, "Intelligence Dashboard") -
every function is a pure data assembly over real tables, so these tests
seed a real (in-memory) schema and assert against it directly, never a
mock - consistent with the "never fabricate metrics" discipline the module
itself follows.
"""
from __future__ import annotations

import datetime as dt

from app.db.models import (
    Application,
    LocalPlan,
    LocalPlanSite,
    MonitoredReport,
    MonitoredSource,
    PolicyChangeEvent,
    Site,
    VisualEvidence,
)
from app.reporting.dashboard import (
    LEADERBOARD_TAB_ORDER,
    build_dashboard,
    build_kpi_row,
    build_leaderboard,
    build_leaderboard_evidence_and_ai,
    build_leaderboard_needs_attention,
    build_leaderboard_new_applications,
    build_leaderboard_policy_updates,
    build_leaderboard_updated_schemes,
    build_opportunities,
    build_planning_intelligence,
    build_policy_intelligence,
    build_recent_activity,
    build_review_queue_counts,
)


def _now(offset_minutes: int = 0) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=offset_minutes)


def test_kpi_row_on_empty_database_is_all_zero_not_an_error(session):
    kpis = build_kpi_row(session)
    labels = {k["label"] for k in kpis}
    assert labels == {
        "Councils", "Local Plans", "Allocations", "Applications",
        "Visual Evidence", "AI summaries", "Review queue",
    }
    assert all(k["value"] == 0 for k in kpis)
    assert all(k["live"] is True for k in kpis)


def test_kpi_row_counts_real_rows(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="Test Plan", status="adopted"))
    session.add(LocalPlanSite(
        council_code="testcouncil", site_name="Land off Test Road", plan_name="Test Plan", plan_status="adopted",
    ))
    session.add(Application(council_code="testcouncil", reference="APP/1"))
    session.commit()

    kpis = {k["label"]: k["value"] for k in build_kpi_row(session)}
    assert kpis["Local Plans"] == 1
    assert kpis["Allocations"] == 1
    assert kpis["Applications"] == 1


def test_review_queue_counts_never_double_counts_across_categories(session):
    app = Application(
        council_code="testcouncil", reference="APP/2", site_link_method="suggested_fuzzy", site_id=None,
    )
    session.add(app)
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Plan")
    session.add(plan)
    session.commit()
    session.add(PolicyChangeEvent(local_plan_id=plan.id, event_type="status_changed", review_status="needs_review"))
    session.add(VisualEvidence(
        local_plan_id=plan.id, source_page=1, status="current", review_status="needs_review",
    ))
    # A confirmed image must never be counted as pending review.
    session.add(VisualEvidence(
        local_plan_id=plan.id, source_page=2, status="current", review_status="confirmed",
    ))
    session.commit()

    counts = build_review_queue_counts(session)
    assert counts["suggested_links"] == 1
    assert counts["policy_changes"] == 1
    assert counts["visual_evidence"] == 1
    assert counts["total"] == 3


def test_planning_intelligence_orders_most_recent_first(session):
    session.add(Application(
        council_code="testcouncil", reference="OLD", first_seen_at=_now(offset_minutes=60),
    ))
    session.add(Application(
        council_code="testcouncil", reference="NEW", first_seen_at=_now(offset_minutes=1),
    ))
    session.commit()

    panel = build_planning_intelligence(session, limit=5)
    assert [a["reference"] for a in panel["recent_applications"]] == ["NEW", "OLD"]


def test_planning_intelligence_excludes_excluded_sites_from_recent_schemes(session):
    session.add(Site(
        council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street",
        excluded=True,
    ))
    session.commit()

    panel = build_planning_intelligence(session)
    assert panel["recently_updated_schemes"] == []


def test_opportunities_low_supply_sorted_ascending(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="High Supply Plan", five_year_supply_years=8.0))
    session.add(LocalPlan(council_code="othercouncil", plan_name="Low Supply Plan", five_year_supply_years=1.5))
    # No stated supply at all - must never appear as a fabricated 0.
    session.add(LocalPlan(council_code="testcouncil", plan_name="Unknown Supply Plan"))
    session.commit()

    opportunities = build_opportunities(session)
    names = [row["plan_name"] for row in opportunities["low_supply_authorities"]]
    assert names == ["Low Supply Plan", "High Supply Plan"]


def test_opportunities_large_unmatched_allocations_excludes_matched_sites(session):
    site = Site(council_code="testcouncil", canonical_address="matched site", display_address="Matched Site")
    session.add(site)
    session.commit()
    session.add(LocalPlanSite(
        council_code="testcouncil", site_name="Matched Allocation", plan_name="P", plan_status="adopted",
        minimum_dwellings=500, matched_site_id=site.id,
    ))
    session.add(LocalPlanSite(
        council_code="testcouncil", site_name="Unmatched Small", plan_name="P", plan_status="adopted",
        minimum_dwellings=50,
    ))
    session.add(LocalPlanSite(
        council_code="testcouncil", site_name="Unmatched Large", plan_name="P", plan_status="adopted",
        minimum_dwellings=400,
    ))
    session.commit()

    opportunities = build_opportunities(session)
    names = [row["site_name"] for row in opportunities["large_unmatched_allocations"]]
    assert names == ["Unmatched Large", "Unmatched Small"]


def test_opportunities_emerging_plans_excludes_adopted_and_unknown(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="Adopted Plan", status="adopted"))
    session.add(LocalPlan(council_code="testcouncil", plan_name="Draft Plan", status="draft_consultation"))
    session.add(LocalPlan(council_code="testcouncil", plan_name="Unknown Plan", status="unknown"))
    session.commit()

    names = [row["plan_name"] for row in build_opportunities(session)["emerging_plans"]]
    assert names == ["Draft Plan"]


def test_policy_intelligence_plans_awaiting_review_groups_by_plan(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Reviewed Plan")
    session.add(plan)
    session.commit()
    session.add(PolicyChangeEvent(local_plan_id=plan.id, event_type="a", review_status="needs_review"))
    session.add(PolicyChangeEvent(local_plan_id=plan.id, event_type="b", review_status="needs_review"))
    session.add(PolicyChangeEvent(local_plan_id=plan.id, event_type="c", review_status="confirmed"))
    session.commit()

    panel = build_policy_intelligence(session)
    assert panel["plans_awaiting_review"] == [
        {"plan_name": "Reviewed Plan", "council_code": "testcouncil", "pending": 2}
    ]


def test_recent_activity_merges_and_sorts_across_every_stream(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Plan", updated_at=_now(offset_minutes=5))
    session.add(plan)
    session.commit()
    session.add(VisualEvidence(
        local_plan_id=plan.id, source_page=1, status="current",
        created_at=_now(offset_minutes=1), updated_at=_now(offset_minutes=1),
    ))
    session.add(MonitoredReport(
        council_code="testcouncil", url="https://example.invalid/report", discovered_at=_now(offset_minutes=10),
    ))
    session.commit()

    activity = build_recent_activity(session, limit=10)
    categories = [e["category"] for e in activity]
    # Most recent (visual evidence, 1 min ago) first, oldest (report, 10 min
    # ago) last - proves cross-stream merging is genuinely sorted, not just
    # concatenated per-stream.
    assert categories[0] == "Visual Evidence"
    assert categories[-1] == "Policy Intelligence"
    def _naive(value):
        return value.replace(tzinfo=None) if value.tzinfo else value

    assert all(_naive(activity[i]["when"]) >= _naive(activity[i + 1]["when"]) for i in range(len(activity) - 1))


def test_recent_activity_respects_limit(session):
    for i in range(5):
        session.add(MonitoredReport(
            council_code="testcouncil", url=f"https://example.invalid/{i}", discovered_at=_now(offset_minutes=i),
        ))
    session.commit()

    assert len(build_recent_activity(session, limit=2)) == 2


def test_build_dashboard_returns_every_section_without_error_on_empty_db(session):
    result = build_dashboard(session)
    assert set(result.keys()) == {
        "kpis", "planning", "policy", "opportunities", "activity", "leaderboard", "generated_at",
    }
    assert result["activity"] == []
    assert result["planning"]["recent_applications"] == []
    assert result["leaderboard"] == {}


# --- Live Intelligence Leaderboard (Sprint 4.2 amendment) -------------------


def test_leaderboard_new_applications_orders_by_recency_then_stable_id_tiebreak(session):
    same_time = _now(offset_minutes=30)
    session.add(Application(council_code="testcouncil", reference="APP-A", first_seen_at=same_time))
    session.add(Application(council_code="testcouncil", reference="APP-B", first_seen_at=same_time))
    session.add(Application(council_code="testcouncil", reference="APP-NEWEST", first_seen_at=_now(offset_minutes=1)))
    session.commit()

    rows = build_leaderboard_new_applications(session, limit=8)
    assert [r["title"] for r in rows] == ["APP-NEWEST", "APP-B", "APP-A"]

    # Same input, called again, must produce the exact same order - a real
    # stable tie-break, not accidental/DB-order-dependent.
    rows_again = build_leaderboard_new_applications(session, limit=8)
    assert [r["id"] for r in rows_again] == [r["id"] for r in rows]


def test_leaderboard_new_applications_links_only_when_a_site_exists(session):
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.commit()
    session.add(Application(council_code="testcouncil", reference="LINKED", site_id=site.id))
    session.add(Application(council_code="testcouncil", reference="UNLINKED"))
    session.commit()

    rows = {r["title"]: r for r in build_leaderboard_new_applications(session)}
    assert rows["LINKED"]["page"] == "pages/1_Scheme_Detail.py"
    assert rows["LINKED"]["params"] == {"site_id": str(site.id)}
    # No Site exists for this application yet - never a dead link.
    assert rows["UNLINKED"]["page"] is None


def test_leaderboard_updated_schemes_always_links_and_excludes_excluded_sites(session):
    session.add(Site(
        council_code="testcouncil", canonical_address="visible", display_address="Visible Site",
    ))
    session.add(Site(
        council_code="testcouncil", canonical_address="hidden", display_address="Excluded Site", excluded=True,
    ))
    session.commit()

    rows = build_leaderboard_updated_schemes(session)
    assert len(rows) == 1
    assert rows[0]["title"] == "Visible Site"
    assert rows[0]["page"] == "pages/1_Scheme_Detail.py"


def test_leaderboard_policy_updates_merges_plans_and_documents_without_duplicates(session):
    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Plan A", status="adopted", updated_at=_now(offset_minutes=5),
    ))
    session.add(MonitoredReport(
        council_code="testcouncil", url="https://example.invalid/r1", discovered_at=_now(offset_minutes=1),
    ))
    session.commit()

    rows = build_leaderboard_policy_updates(session)
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "no row should appear twice"
    assert [r["title"] for r in rows] == ["https://example.invalid/r1", "Plan A"]


def test_leaderboard_evidence_and_ai_links_visual_evidence_to_its_site(session):
    site = Site(council_code="testcouncil", canonical_address="s", display_address="S")
    session.add(site)
    session.commit()
    session.add(VisualEvidence(site_id=site.id, source_page=1, status="current"))
    session.commit()

    rows = build_leaderboard_evidence_and_ai(session)
    assert len(rows) == 1
    assert rows[0]["page"] == "pages/1_Scheme_Detail.py"
    assert rows[0]["params"] == {"site_id": str(site.id)}
    assert rows[0]["badge"] == "AI"


def test_leaderboard_needs_attention_matches_review_queue_counts_exactly(session):
    session.add(Application(
        council_code="testcouncil", reference="SUGGESTED", site_link_method="suggested_fuzzy", site_id=None,
    ))
    plan = LocalPlan(council_code="testcouncil", plan_name="P")
    session.add(plan)
    session.commit()
    session.add(PolicyChangeEvent(local_plan_id=plan.id, event_type="status_changed", review_status="needs_review"))
    session.add(VisualEvidence(local_plan_id=plan.id, source_page=1, status="current", review_status="needs_review"))
    session.add(VisualEvidence(local_plan_id=plan.id, source_page=2, status="current", review_status="confirmed"))
    session.commit()

    rows = build_leaderboard_needs_attention(session)
    counts = build_review_queue_counts(session)
    assert len(rows) == counts["total"] == 3
    # A confirmed image must never surface as "needs attention".
    assert all(r["badge"] == "Needs review" for r in rows)


def test_leaderboard_row_ids_are_unique_within_each_tab(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="P", ai_summary_generated_at=_now())
    session.add(plan)
    session.add(Application(council_code="testcouncil", reference="A1"))
    session.add(Site(council_code="testcouncil", canonical_address="s", display_address="S"))
    session.commit()
    session.add(VisualEvidence(local_plan_id=plan.id, source_page=1, status="current"))
    session.commit()

    for tab_rows in build_leaderboard(session).values():
        ids = [r["id"] for r in tab_rows]
        assert len(ids) == len(set(ids))


def test_leaderboard_hides_tabs_with_no_supporting_data(session):
    # Only an application exists - only "New Applications" should appear.
    session.add(Application(council_code="testcouncil", reference="ONLY-ONE"))
    session.commit()

    tabs = build_leaderboard(session)
    assert list(tabs.keys()) == ["New Applications"]


def test_leaderboard_empty_database_returns_no_tabs_at_all(session):
    assert build_leaderboard(session) == {}


def test_leaderboard_tab_order_is_always_the_documented_order(session):
    session.add(Application(council_code="testcouncil", reference="A1"))
    session.add(Site(council_code="testcouncil", canonical_address="s", display_address="S"))
    plan = LocalPlan(council_code="testcouncil", plan_name="P", ai_summary_generated_at=_now())
    session.add(plan)
    session.add(Application(
        council_code="testcouncil", reference="SUGGESTED", site_link_method="suggested_fuzzy", site_id=None,
    ))
    session.commit()

    tabs = build_leaderboard(session)
    expected_order = [name for name in LEADERBOARD_TAB_ORDER if name in tabs]
    assert list(tabs.keys()) == expected_order


def test_leaderboard_respects_limit_per_tab(session):
    for i in range(12):
        session.add(Application(council_code="testcouncil", reference=f"APP-{i}", first_seen_at=_now(offset_minutes=i)))
    session.commit()

    rows = build_leaderboard_new_applications(session, limit=3)
    assert len(rows) == 3
