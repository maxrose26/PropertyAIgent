"""Tests for app.reporting.dashboard (Sprint 4.2, "Intelligence Dashboard") -
every function is a pure data assembly over real tables, so these tests
seed a real (in-memory) schema and assert against it directly, never a
mock - consistent with the "never fabricate metrics" discipline the module
itself follows.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from app.db.models import (
    Application,
    LocalPlan,
    LocalPlanSite,
    MonitoredReport,
    MonitoredSource,
    PolicyChangeEvent,
    SchemeIntelligence,
    Site,
    VisualEvidence,
)
from app.reporting.dashboard import (
    LEADERBOARD_TAB_ORDER,
    SCHEME_STACK_TAB_ORDER,
    build_activity_events,
    build_ai_summary_carousel_items,
    build_ai_summary_rail,
    build_dashboard,
    build_grouped_activity,
    build_kpi_row,
    build_leaderboard,
    build_leaderboard_evidence_and_ai,
    build_leaderboard_needs_attention,
    build_leaderboard_new_applications,
    build_leaderboard_policy_updates,
    build_leaderboard_updated_schemes,
    build_opportunities,
    build_opportunity_cards,
    build_opportunity_categories,
    build_planning_intelligence,
    build_policy_intelligence,
    build_recent_activity,
    build_review_queue_counts,
    build_scheme_stack,
    group_activity_events,
)


def _now(offset_minutes: int = 0) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=offset_minutes)


def test_kpi_row_on_empty_database_is_all_zero_not_an_error(session):
    kpis = build_kpi_row(session)
    labels = {k["label"] for k in kpis}
    assert labels == {
        "Councils", "Local Plans", "Allocations", "Applications",
        "Visual Evidence", "AI Summaries", "Reviews",
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
        "kpis", "planning", "policy", "opportunities", "opportunity_cards", "activity",
        "activity_grouped", "leaderboard", "ai_summary_carousel",
        "scheme_stack", "opportunity_categories", "ai_summary_rail", "generated_at",
    }
    assert result["activity"] == []
    assert result["planning"]["recent_applications"] == []
    assert result["leaderboard"] == {}
    assert result["opportunity_cards"] == []
    assert result["activity_grouped"] == []
    assert result["ai_summary_carousel"] == []
    assert result["scheme_stack"] == {}
    assert result["ai_summary_rail"] == []
    assert len(result["opportunity_categories"]) == 7
    assert all(cat["count"] == 0 and cat["cards"] == [] for cat in result["opportunity_categories"])


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
    # Only an application exists - only "New Apps" should appear.
    session.add(Application(council_code="testcouncil", reference="ONLY-ONE"))
    session.commit()

    tabs = build_leaderboard(session)
    assert list(tabs.keys()) == ["New Apps"]


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


# --- Dashboard hierarchy revision --------------------------------------------


def test_leaderboard_tab_labels_are_concise(session):
    assert LEADERBOARD_TAB_ORDER == ("New Apps", "Scheme Updates", "Policy", "Evidence & AI", "Attention")
    assert all(len(label) <= len("Scheme Updates") for label in LEADERBOARD_TAB_ORDER)


def test_dashboard_page_section_order_matches_the_revised_hierarchy():
    """Ordering is a rendering concern, not something build_dashboard's
    data layer can express - this reads the page's own source and checks
    that each section marker appears in the documented order: sidebar
    Quick Actions -> sidebar Credits -> KPI strip -> AI Daily Brief -> main
    column (Planning Intelligence scheme stack, Opportunities, Policy
    Intelligence, Recent Activity) -> right rail (AI Summary rail) - a
    structural proxy for the Dashboard layout correction, without needing a
    full browser-driven UI test."""
    page_source = (Path(__file__).resolve().parents[1] / "app" / "ui" / "pages" / "00_Dashboard.py").read_text(encoding="utf-8")
    markers = [
        "quick_actions_panel(",
        "credits_sidebar(",
        "metric_row(",
        "ai_daily_brief_placeholder()",
        "scheme_stack(",
        "opportunity_category_section(",
        "section_container(",
        "activity_timeline(",
        "ai_summary_rail(",
    ]
    positions = [page_source.index(marker) for marker in markers]
    assert positions == sorted(positions), "sections must appear in the documented hierarchy order"


def test_quick_actions_rendered_inside_the_native_sidebar_before_credits(session):
    """Dashboard layout correction, Part 2: Quick Actions must render
    through st.sidebar (not a body-level column) and must appear before
    the credits_sidebar() call, so the native sidebar's own top-to-bottom
    order is Quick Actions then Credits."""
    page_source = (Path(__file__).resolve().parents[1] / "app" / "ui" / "pages" / "00_Dashboard.py").read_text(encoding="utf-8")
    sidebar_index = page_source.index("with st.sidebar:")
    quick_actions_index = page_source.index("quick_actions_panel(")
    credits_index = page_source.index("credits_sidebar(session, settings)")
    assert sidebar_index < quick_actions_index < credits_index, \
        "Quick Actions must be inside st.sidebar and precede the Credits sidebar call"


def test_quick_actions_panel_is_called_exactly_once(session):
    """Part 8: Quick Actions must never appear twice (body + sidebar, or
    duplicated within the sidebar itself)."""
    page_source = (Path(__file__).resolve().parents[1] / "app" / "ui" / "pages" / "00_Dashboard.py").read_text(encoding="utf-8")
    assert page_source.count("quick_actions_panel(") == 1


def test_dashboard_page_has_no_body_level_left_column(session):
    """Part 3: "Do not create an extra left column inside the main body" -
    the page must declare only a two-way split (main/right), never a
    three-way left/main/right split, now that Quick Actions live in the
    native sidebar."""
    page_source = (Path(__file__).resolve().parents[1] / "app" / "ui" / "pages" / "00_Dashboard.py").read_text(encoding="utf-8")
    assert "left_col" not in page_source
    assert "main_col, right_col = st.columns(" in page_source


def test_dashboard_page_applies_the_wide_canvas_override(session):
    """Part 1: confirms the page-scoped width override is actually wired
    in, not just present in shell.py unused."""
    page_source = (Path(__file__).resolve().parents[1] / "app" / "ui" / "pages" / "00_Dashboard.py").read_text(encoding="utf-8")
    assert "wide_canvas()" in page_source


def test_dashboard_kpi_strip_splits_into_two_legible_rows(session):
    """Part 4: seven-across was tried and measurably failed "ensure labels
    remain legible" at a standard laptop width (~1000px) - every label
    truncated. Four-then-three is the deliberate, documented alternative;
    this test guards against silently reverting to the illegible variant."""
    page_source = (Path(__file__).resolve().parents[1] / "app" / "ui" / "pages" / "00_Dashboard.py").read_text(encoding="utf-8")
    assert "kpis[:4]" in page_source and "kpis[4:]" in page_source


def test_opportunity_cards_ordering_is_deterministic_and_category_grouped(session):
    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Low Supply Plan", five_year_supply_years=1.2,
    ))
    session.add(LocalPlanSite(
        council_code="testcouncil", site_name="Big Site", plan_name="P", plan_status="adopted",
        minimum_dwellings=900,
    ))
    session.commit()

    cards = build_opportunity_cards(session)
    categories = [c["category"] for c in cards]
    # low_supply must always precede large_unmatched - _OPPORTUNITY_CATEGORY_ORDER,
    # never an interleaved/scored ranking.
    assert categories.index("low_supply") < categories.index("large_unmatched")

    # Same input, called again, produces the exact same order.
    cards_again = build_opportunity_cards(session)
    assert [c["id"] for c in cards_again] == [c["id"] for c in cards]


def test_opportunity_card_badges_are_real_categories_not_invented_scores(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="P", five_year_supply_years=2.0))
    session.commit()

    cards = build_opportunity_cards(session)
    assert cards[0]["badge"] == "Low housing supply"
    assert "priority" not in cards[0]
    assert "score" not in cards[0]


def test_activity_grouping_aggregates_repeated_events_from_the_same_source(session):
    # A pre-existing plan (updated well outside this test's own activity
    # window) so the only fresh event stream is the 8 visual-evidence rows -
    # isolates the grouping behaviour under test from the real, separate
    # "plan_updated" event a LocalPlan row's own presence would otherwise
    # also generate.
    plan = LocalPlan(council_code="testcouncil", plan_name="Stockport Local Plan", updated_at=_now(offset_minutes=999))
    session.add(plan)
    session.commit()
    for i in range(8):
        session.add(VisualEvidence(
            local_plan_id=plan.id, source_page=i, status="current",
            source_document_title="Stockport Local Plan", created_at=_now(offset_minutes=i),
        ))
    session.commit()

    grouped = build_grouped_activity(session)
    visual_group = next(g for g in grouped if g["id"] == "group-visual_evidence_extracted-Stockport Local Plan")
    assert visual_group["count"] == 8
    assert visual_group["label"] == "8 visual-evidence pages extracted from Stockport Local Plan"
    # The plan's own single "plan_updated" event must be a distinct row,
    # never merged into the visual-evidence group just because they share
    # a source name.
    assert len(grouped) == 2


def test_activity_grouping_never_merges_unrelated_activity(session):
    plan_a = LocalPlan(council_code="testcouncil", plan_name="Plan A", updated_at=_now(offset_minutes=1))
    plan_b = LocalPlan(council_code="othercouncil", plan_name="Plan B", updated_at=_now(offset_minutes=2))
    session.add(plan_a)
    session.add(plan_b)
    session.add(MonitoredReport(
        council_code="testcouncil", url="https://example.invalid/r", discovered_at=_now(offset_minutes=3),
    ))
    session.commit()

    grouped = build_grouped_activity(session)
    # Three genuinely different (action, source) combinations - never
    # collapsed into fewer rows just because they share a council.
    assert len(grouped) == 3
    assert len({row["id"] for row in grouped}) == 3


def test_activity_grouping_singular_vs_plural_labels(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Solo Plan", updated_at=_now(offset_minutes=999))
    session.add(plan)
    session.commit()
    session.add(VisualEvidence(
        local_plan_id=plan.id, source_page=1, status="current", source_document_title="Solo Plan",
    ))
    session.commit()

    grouped = build_grouped_activity(session)
    visual_group = next(g for g in grouped if g["id"] == "group-visual_evidence_extracted-Solo Plan")
    assert visual_group["label"] == "1 visual-evidence page extracted from Solo Plan"
    assert "pages" not in visual_group["label"]


def test_activity_grouping_plan_updated_uses_a_natural_singular_phrase(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="My Plan"))
    session.commit()

    grouped = build_grouped_activity(session)
    assert grouped[0]["label"] == "My Plan updated"


def test_build_activity_events_never_writes_to_the_database(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="P")
    session.add(plan)
    session.commit()
    before = session.query(LocalPlan).count()
    build_activity_events(session)
    group_activity_events(build_activity_events(session))
    session.commit()
    assert session.query(LocalPlan).count() == before


def test_ai_summary_carousel_selects_only_stored_summaries_ordered_deterministically(session):
    session.add(LocalPlan(
        council_code="testcouncil", plan_name="No Summary Plan",
    ))
    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Older Summary Plan",
        ai_summary_text="Older.", ai_summary_generated_at=_now(offset_minutes=10), ai_summary_model="gpt-4o-mini",
    ))
    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Newer Summary Plan",
        ai_summary_text="Newer.", ai_summary_generated_at=_now(offset_minutes=1), ai_summary_model="gpt-4o-mini",
    ))
    session.add(Site(
        council_code="testcouncil", canonical_address="s", display_address="S",
        status_summary="Site summary text.", status_summary_updated_at=_now(offset_minutes=5),
    ))
    session.commit()

    items = build_ai_summary_carousel_items(session)
    # Only the 3 with a real generated timestamp - the plan with no summary
    # is never included, let alone with a fabricated excerpt.
    assert len(items) == 3
    assert [it["name"] for it in items] == ["Newer Summary Plan", "S", "Older Summary Plan"]

    items_again = build_ai_summary_carousel_items(session)
    assert [it["id"] for it in items_again] == [it["id"] for it in items]


def test_ai_summary_carousel_empty_and_single_item_states(session):
    assert build_ai_summary_carousel_items(session) == []

    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Only Plan",
        ai_summary_text="Text.", ai_summary_generated_at=_now(), ai_summary_model="gpt-4o-mini",
    ))
    session.commit()
    items = build_ai_summary_carousel_items(session)
    assert len(items) == 1
    assert items[0]["name"] == "Only Plan"


def test_ai_summary_carousel_excerpt_never_exceeds_the_configured_length(session):
    long_text = "word " * 200
    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Long Plan",
        ai_summary_text=long_text, ai_summary_generated_at=_now(), ai_summary_model="gpt-4o-mini",
    ))
    session.commit()

    items = build_ai_summary_carousel_items(session)
    assert len(items[0]["excerpt"]) <= 182  # 180 + ellipsis allowance


def test_dashboard_module_never_imports_an_ai_client():
    """A static guarantee, not just a runtime one - the carousel and every
    other Sprint 4.2 hierarchy-revision function reads already-persisted
    text only. If an AI client were ever imported here, this import-level
    check would fail before any test exercising real behaviour even runs."""
    import app.reporting.dashboard as dashboard_module
    source = Path(dashboard_module.__file__).read_text(encoding="utf-8")
    assert "openai" not in source.lower()
    assert "OpenAI(" not in source


# --- Dashboard refinement - Planning Intelligence scheme stack -------------


def test_scheme_stack_only_includes_populated_categories(session):
    assert build_scheme_stack(session) == {}

    session.add(Application(council_code="testcouncil", reference="APP-1", first_seen_at=_now()))
    session.commit()
    tabs = build_scheme_stack(session)
    assert set(tabs.keys()) == {"New Applications"}
    assert list(tabs.keys())[0] in SCHEME_STACK_TAB_ORDER


def test_scheme_stack_new_applications_orders_by_recency_then_id(session):
    same_time = _now(offset_minutes=30)
    session.add(Application(council_code="testcouncil", reference="APP-A", first_seen_at=same_time))
    session.add(Application(council_code="testcouncil", reference="APP-B", first_seen_at=same_time))
    session.add(Application(council_code="testcouncil", reference="APP-NEWEST", first_seen_at=_now(offset_minutes=1)))
    session.commit()

    rows = build_scheme_stack(session)["New Applications"]
    assert [r["reference"] for r in rows] == ["APP-NEWEST", "APP-B", "APP-A"]


def test_scheme_stack_card_omits_fields_with_no_evidence(session):
    """No SchemeIntelligence row at all - total_units/affordable_units/
    developer must be None, never a fabricated 0 or empty string."""
    session.add(Application(council_code="testcouncil", reference="APP-BARE", first_seen_at=_now()))
    session.commit()

    row = build_scheme_stack(session)["New Applications"][0]
    assert row["total_units"] is None
    assert row["affordable_units"] is None
    assert row["affordable_percentage"] is None
    assert row["developer"] is None


def test_scheme_stack_card_shows_units_status_and_developer_from_scheme_intelligence(session):
    app = Application(council_code="testcouncil", reference="APP-RICH", status="Under consideration", first_seen_at=_now())
    session.add(app)
    session.flush()
    session.add(SchemeIntelligence(
        application_id=app.id, total_units_final=120, affordable_units_final=30,
        affordable_percentage_final=25.0, developer="Acme Developments Ltd",
    ))
    session.commit()

    row = build_scheme_stack(session)["New Applications"][0]
    assert row["total_units"] == 120
    assert row["affordable_units"] == 30
    assert row["affordable_percentage"] == 25.0
    assert row["developer"] == "Acme Developments Ltd"
    assert row["planning_status"] == "Under consideration"


def test_scheme_stack_links_to_site_profile_when_linked_else_no_dead_click(session):
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street")
    session.add(site)
    session.flush()
    linked = Application(council_code="testcouncil", reference="APP-LINKED", site_id=site.id, first_seen_at=_now())
    unlinked = Application(council_code="testcouncil", reference="APP-UNLINKED", first_seen_at=_now(offset_minutes=1))
    session.add_all([linked, unlinked])
    session.commit()

    rows = build_scheme_stack(session)["New Applications"]
    by_ref = {r["reference"]: r for r in rows}
    assert by_ref["APP-LINKED"]["page"] == "pages/1_Scheme_Detail.py"
    assert by_ref["APP-LINKED"]["params"] == {"site_id": str(site.id)}
    assert by_ref["APP-UNLINKED"]["page"] is None


# --- Dashboard refinement - Opportunity categories --------------------------


def test_opportunity_categories_returns_all_seven_available_categories_in_order(session):
    categories = build_opportunity_categories(session)
    assert [c["key"] for c in categories] == [
        "approaching_lapse", "low_supply", "undeveloped_phase", "allocations_without_application",
        "emerging_policy", "recent_policy_activity", "recently_adopted",
    ]
    assert all(c["available"] is True and c["unavailable_reason"] is None for c in categories)
    assert all(c["count"] == 0 and c["cards"] == [] for c in categories)


def _granted_site_with_decision(session, *, decision_date: dt.date, decision: str = "Granted") -> Site:
    site = Site(
        council_code="testcouncil", canonical_address=f"site-{decision_date.isoformat()}",
        display_address=f"Site decided {decision_date.isoformat()}",
    )
    session.add(site)
    session.flush()
    session.add(Application(
        council_code="testcouncil", reference=f"APP-{site.id}", site_id=site.id,
        decision=decision, decision_issued_date=decision_date.strftime("%a %d %b %Y"), first_seen_at=_now(),
    ))
    return site


def test_approaching_lapse_only_includes_permissions_within_the_warning_window(session):
    today = dt.date.today()
    # Deadline ~100 days away (within the 180-day warning window) - approaching.
    approaching_site = _granted_site_with_decision(session, decision_date=today - dt.timedelta(days=3 * 365 - 100))
    # Deadline ~2 years away - safe, must not appear.
    safe_site = _granted_site_with_decision(session, decision_date=today - dt.timedelta(days=30))
    # Deadline already passed - lapsed, must not appear in "approaching" either.
    lapsed_site = _granted_site_with_decision(session, decision_date=today - dt.timedelta(days=3 * 365 + 30))
    session.commit()

    category = build_opportunity_categories(session)[0]
    assert category["key"] == "approaching_lapse"
    titles = [c["title"] for c in category["cards"]]
    assert approaching_site.display_address in titles
    assert safe_site.display_address not in titles
    assert lapsed_site.display_address not in titles


def test_low_supply_category_only_includes_plans_below_five_years(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="Tight Supply Plan", five_year_supply_years=1.77))
    session.add(LocalPlan(council_code="othercouncil", plan_name="Comfortable Supply Plan", five_year_supply_years=6.2))
    session.commit()

    category = next(c for c in build_opportunity_categories(session) if c["key"] == "low_supply")
    titles = [c["title"] for c in category["cards"]]
    assert "Tight Supply Plan" in titles
    assert "Comfortable Supply Plan" not in titles


def test_undeveloped_phase_only_surfaces_for_multiphase_sites_with_an_approved_not_started_phase(session):
    multi_phase_site = Site(council_code="testcouncil", canonical_address="multi-phase", display_address="Multi-Phase Site")
    single_app_site = Site(council_code="testcouncil", canonical_address="single-app", display_address="Single Application Site")
    session.add_all([multi_phase_site, single_app_site])
    session.flush()

    grant_date = dt.date.today() - dt.timedelta(days=200)
    session.add(Application(
        council_code="testcouncil", reference="PH1", site_id=multi_phase_site.id,
        proposal="Reserved Matters for Phase 1", decision="Granted",
        decision_issued_date=grant_date.strftime("%a %d %b %Y"), first_seen_at=_now(),
    ))
    session.add(Application(
        council_code="testcouncil", reference="PH2", site_id=multi_phase_site.id,
        proposal="Reserved Matters for Phase 2", first_seen_at=_now(),
    ))
    # A single-application site can never produce a phase breakdown (needs 2+ groups) - must not appear.
    session.add(Application(
        council_code="testcouncil", reference="SINGLE", site_id=single_app_site.id,
        proposal="Full planning permission", decision="Granted",
        decision_issued_date=grant_date.strftime("%a %d %b %Y"), first_seen_at=_now(),
    ))
    session.commit()

    category = next(c for c in build_opportunity_categories(session) if c["key"] == "undeveloped_phase")
    titles = [c["title"] for c in category["cards"]]
    assert any("Multi-Phase Site" in t for t in titles)
    assert not any("Single Application Site" in t for t in titles)


def test_allocations_without_application_matches_unmatched_large_allocations(session):
    session.add(LocalPlanSite(
        council_code="testcouncil", site_name="Unmatched Big Site", plan_name="Plan", plan_status="adopted",
        minimum_dwellings=500, matched_site_id=None,
    ))
    session.commit()

    category = next(c for c in build_opportunity_categories(session) if c["key"] == "allocations_without_application")
    assert category["cards"][0]["title"] == "Unmatched Big Site"
    assert "no linked planning application" in category["cards"][0]["reason"]


def test_emerging_policy_excludes_adopted_plans(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="Draft Plan", status="draft_consultation"))
    session.add(LocalPlan(council_code="othercouncil", plan_name="Settled Plan", status="adopted"))
    session.commit()

    category = next(c for c in build_opportunity_categories(session) if c["key"] == "emerging_policy")
    titles = [c["title"] for c in category["cards"]]
    assert "Draft Plan" in titles
    assert "Settled Plan" not in titles


# --- Dashboard refinement - AI Summary rail relevance ------------------------


def test_ai_summary_rail_empty_and_single_item_states(session):
    assert build_ai_summary_rail(session) == []

    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Only Plan",
        ai_summary_text="Text.", ai_summary_generated_at=_now(), ai_summary_model="gpt-4o-mini",
    ))
    session.commit()
    items = build_ai_summary_rail(session)
    assert len(items) == 1
    assert "relevance" in items[0]


def test_ai_summary_rail_ordering_matches_the_underlying_carousel_items(session):
    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Older", ai_summary_text="A",
        ai_summary_generated_at=_now(offset_minutes=100), ai_summary_model="gpt-4o-mini",
    ))
    session.add(LocalPlan(
        council_code="othercouncil", plan_name="Newer", ai_summary_text="B",
        ai_summary_generated_at=_now(offset_minutes=1), ai_summary_model="gpt-4o-mini",
    ))
    session.commit()

    carousel_ids = [it["id"] for it in build_ai_summary_carousel_items(session)]
    rail_ids = [it["id"] for it in build_ai_summary_rail(session)]
    assert rail_ids == carousel_ids


def test_ai_summary_rail_relevance_prefers_low_supply_over_generic_fallback(session):
    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Stretched Council Plan", five_year_supply_years=1.5,
        ai_summary_text="Text.", ai_summary_generated_at=_now(), ai_summary_model="gpt-4o-mini",
    ))
    session.commit()

    item = build_ai_summary_rail(session)[0]
    assert "below the five-year threshold" in item["relevance"]


def test_ai_summary_rail_relevance_falls_back_to_generic_statement_when_no_signal_applies(session):
    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Quiet Plan", status="unknown",
        ai_summary_text="Text.", ai_summary_generated_at=_now(), ai_summary_model="gpt-4o-mini",
    ))
    session.commit()

    item = build_ai_summary_rail(session)[0]
    assert item["relevance"] == "Generated recently from verified evidence"


def test_ai_summary_rail_never_alters_the_persisted_summary_text(session):
    plan = LocalPlan(
        council_code="testcouncil", plan_name="Untouched Plan", ai_summary_text="Original text.",
        ai_summary_generated_at=_now(), ai_summary_model="gpt-4o-mini",
    )
    session.add(plan)
    session.commit()

    build_ai_summary_rail(session)
    session.refresh(plan)
    assert plan.ai_summary_text == "Original text."


# --- Dashboard refinement - no AI calls, no database writes -----------------


def test_dashboard_refinement_functions_make_no_database_writes(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="A Plan", five_year_supply_years=2.0, status="draft_consultation"))
    session.add(Application(council_code="testcouncil", reference="APP-X", first_seen_at=_now()))
    session.commit()

    build_scheme_stack(session)
    build_opportunity_categories(session)
    build_ai_summary_rail(session)

    assert len(session.new) == 0
    assert len(session.dirty) == 0


def test_dashboard_page_declares_main_before_right_column():
    """Dashboard layout correction: with Quick Actions moved out of the
    body into the native sidebar, only two body columns remain
    (main_col, right_col). Declaring main_col first means Streamlit's own
    narrow-width stacking naturally puts the main column first and the AI
    rail second - a structural regression here would silently change both
    the desktop layout AND the narrow-width fallback."""
    page_source = (Path(__file__).resolve().parents[1] / "app" / "ui" / "pages" / "00_Dashboard.py").read_text(encoding="utf-8")
    assert "main_col, right_col = st.columns(" in page_source


def test_ai_summary_rail_stays_in_the_right_column_separate_from_main_content():
    """Part 6: the AI rail must remain visually separate from the scheme
    stack/opportunities - i.e. rendered inside the `with right_col:` block,
    after the main column's own `with main_col:` block closes."""
    page_source = (Path(__file__).resolve().parents[1] / "app" / "ui" / "pages" / "00_Dashboard.py").read_text(encoding="utf-8")
    right_col_index = page_source.index("with right_col:")
    rail_index = page_source.index("ai_summary_rail(")
    scheme_stack_index = page_source.index("scheme_stack(")
    assert scheme_stack_index < right_col_index < rail_index
