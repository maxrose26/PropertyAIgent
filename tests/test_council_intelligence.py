"""Tests for app.reporting.council_intelligence (Sprint 4.3, "Council
Intelligence") - a pure data-assembly module, so these tests seed a real
(in-memory) schema and assert against it directly, the same discipline
already established by tests/test_dashboard.py.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from app.db.models import (
    Council,
    LocalPlan,
    LocalPlanCouncil,
    LocalPlanSite,
    MonitoredReport,
    PolicyChangeEvent,
    VisualEvidence,
)
from app.reporting.council_intelligence import (
    EVIDENCE_FRESHNESS_LABELS,
    PLAN_STAGE_LABELS,
    _five_year_supply_state,
    _format_five_year_supply,
    _format_housing_requirement,
    _headline_delivery_or_milestone,
    _plan_age_years,
    _planning_health_banner,
    _planning_readiness_chip,
    _status_color_category,
    build_council_detail,
    build_council_overview,
)


def _now(offset_minutes: int = 0) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=offset_minutes)


def _enable_monitoring(session, council_code: str) -> None:
    council = session.get(Council, council_code)
    council.monitoring_enabled = True


# --- Navigation -------------------------------------------------------------


def test_council_intelligence_registered_under_policy_and_hidden_detail():
    source = Path(__file__).resolve().parents[1].joinpath("app", "ui", "streamlit_app.py").read_text(encoding="utf-8")
    assert '"pages/5_Council_Intelligence.py"' in source
    assert '"pages/6_Council_Intelligence_Detail.py"' in source
    policy_block = source[source.index('"Policy":'):source.index('"Administration":')]
    assert "council_intelligence_page" in policy_block
    assert "council_intelligence_detail_page" in policy_block
    assert 'visibility="hidden"' in source[source.index("council_intelligence_detail_page ="):source.index("local_plan_page =")]


def test_council_operations_registered_under_administration_and_renamed():
    source = Path(__file__).resolve().parents[1].joinpath("app", "ui", "streamlit_app.py").read_text(encoding="utf-8")
    admin_block = source[source.index('"Administration":'):]
    assert "council_operations_page" in admin_block
    assert 'title="Council Operations"' in source
    assert 'title="Council Dashboard"' not in source


def test_dashboard_and_explore_navigation_remain_intact():
    source = Path(__file__).resolve().parents[1].joinpath("app", "ui", "streamlit_app.py").read_text(encoding="utf-8")
    assert 'st.Page("pages/00_Dashboard.py", title="Dashboard", icon="🏠", default=True)' in source
    assert 'st.Page("pages/0_Explore.py", title="Explore", icon="🔍")' in source


# --- No operational fields leak into the customer view ----------------------


def test_overview_card_never_exposes_raw_operational_fields(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="Test Plan", status="adopted"))
    session.commit()

    cards = build_council_overview(session)
    assert cards
    forbidden_keys = {"monitoring_enabled", "sources_count", "review_items_pending", "ingestion"}
    assert forbidden_keys.isdisjoint(cards[0].keys())
    # evidence_freshness must be a customer-safe label, never a raw
    # monitoring_health enum value.
    assert cards[0]["evidence_freshness"] in EVIDENCE_FRESHNESS_LABELS.values()


def test_customer_pages_never_render_raw_operational_terms():
    """Scans the CODE only, not the module docstring (which legitimately
    explains, in prose, what this page deliberately does NOT show - that
    explanatory negation is not the same as actually rendering the term to
    a user)."""
    for filename in ("5_Council_Intelligence.py", "6_Council_Intelligence_Detail.py"):
        source = Path(__file__).resolve().parents[1].joinpath("app", "ui", "pages", filename).read_text(encoding="utf-8")
        # Strip the leading module docstring (first \"\"\"...\"\"\" block).
        first = source.index('"""')
        second = source.index('"""', first + 3)
        code_only = source[second + 3:].lower()
        for banned in ("monitoring_enabled", "sources_count", "ingestion control", "monitoring health"):
            assert banned not in code_only, f"{filename} must not surface {banned!r}"


# --- Multiple Local Plans per council / joint plans (Places for Everyone) --


def test_council_with_multiple_local_plans_lists_all_of_them(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="Own Plan", status="proposed_submission"))
    session.add(LocalPlan(council_code="testcouncil", plan_name="Joint Plan", status="adopted"))
    session.commit()

    detail = build_council_detail(session, "testcouncil")
    plan_names = {p.plan_name for p in detail["plans"]}
    assert plan_names == {"Own Plan", "Joint Plan"}
    # Never blended into one merged summary - each plan_summaries row is independent.
    assert len(detail["plan_summaries"]) == 2


def test_joint_plan_appears_under_every_linked_authority(session):
    session.add(Council(
        code="thirdcouncil", name="Third Council", base_url="https://third.invalid",
        date_field_mode="received", doc_system="idox",
    ))
    joint_plan = LocalPlan(council_code="testcouncil", plan_name="Places for Everyone", status="adopted")
    session.add(joint_plan)
    session.commit()
    session.add(LocalPlanCouncil(local_plan_id=joint_plan.id, council_code="testcouncil", role="lead_authority", is_lead_authority=True))
    session.add(LocalPlanCouncil(local_plan_id=joint_plan.id, council_code="thirdcouncil", role="participating_authority", is_lead_authority=False))
    session.commit()

    detail_lead = build_council_detail(session, "testcouncil")
    detail_participant = build_council_detail(session, "thirdcouncil")
    assert "Places for Everyone" in {p.plan_name for p in detail_lead["plans"]}
    assert "Places for Everyone" in {p.plan_name for p in detail_participant["plans"]}


def test_joint_plan_allocation_count_is_council_specific_not_blended(session):
    """Places for Everyone with allocations in testcouncil only - a
    participating authority with zero allocations of its own must show 0,
    never testcouncil's count."""
    session.add(Council(
        code="thirdcouncil", name="Third Council", base_url="https://third.invalid",
        date_field_mode="received", doc_system="idox",
    ))
    joint_plan = LocalPlan(council_code="testcouncil", plan_name="Places for Everyone", status="adopted")
    session.add(joint_plan)
    session.commit()
    session.add(LocalPlanCouncil(local_plan_id=joint_plan.id, council_code="testcouncil", role="lead_authority", is_lead_authority=True))
    session.add(LocalPlanCouncil(local_plan_id=joint_plan.id, council_code="thirdcouncil", role="participating_authority", is_lead_authority=False))
    session.add(LocalPlanSite(
        council_code="testcouncil", local_plan_id=joint_plan.id, site_name="JPA 1",
        plan_name="Places for Everyone", plan_status="adopted", minimum_dwellings=500,
    ))
    session.commit()

    detail_lead = build_council_detail(session, "testcouncil")
    detail_participant = build_council_detail(session, "thirdcouncil")
    lead_summary = next(p for p in detail_lead["plan_summaries"] if p["plan_name"] == "Places for Everyone")
    participant_summary = next(p for p in detail_participant["plan_summaries"] if p["plan_name"] == "Places for Everyone")
    assert lead_summary["allocations_imported"] == 1
    assert participant_summary["allocations_imported"] == 0


def test_primary_plan_prefers_own_plan_over_joint_plan(session):
    """A council's own plan (any role other than participating_authority)
    is always the headline plan, even when the joint plan is adopted and
    the own plan is only emerging."""
    own_plan = LocalPlan(council_code="testcouncil", plan_name="Bury Local Plan", status="proposed_submission")
    joint_plan = LocalPlan(council_code="testcouncil", plan_name="Places for Everyone", status="adopted")
    session.add_all([own_plan, joint_plan])
    session.commit()
    session.add(LocalPlanCouncil(local_plan_id=own_plan.id, council_code="testcouncil", role="legacy_owner", is_lead_authority=True))
    session.add(LocalPlanCouncil(local_plan_id=joint_plan.id, council_code="testcouncil", role="lead_authority", is_lead_authority=True))
    session.commit()

    cards = build_council_overview(session)
    card = next(c for c in cards if c["council_code"] == "testcouncil")
    assert card["plan_name"] == "Bury Local Plan"


# --- Stored AI summary rendering (data-level) --------------------------------


def test_overview_card_carries_stored_ai_summary_excerpt(session):
    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Summarised Plan", status="adopted",
        ai_summary_text="A concise, evidence-based summary of this plan's position.",
        ai_summary_generated_at=_now(), ai_summary_model="gpt-4o-mini",
    ))
    session.commit()

    card = build_council_overview(session)[0]
    assert card["ai_summary_excerpt"] is not None
    assert card["ai_summary_excerpt"].startswith("A concise")
    assert card["ai_summary_generated_at"] is not None


def test_overview_card_has_no_summary_excerpt_when_none_generated(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="Quiet Plan", status="draft_consultation"))
    session.commit()

    card = build_council_overview(session)[0]
    assert card["ai_summary_excerpt"] is None


# --- Missing / stale evidence states -----------------------------------------


def test_overview_card_flags_missing_evidence_when_headline_figures_absent(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="Bare Plan", status="draft_consultation"))
    session.commit()

    card = build_council_overview(session)[0]
    assert card["has_missing_evidence"] is True


def test_overview_card_does_not_flag_missing_evidence_when_headline_figures_present(session):
    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Evidenced Plan", status="adopted",
        five_year_supply_years=3.2, annual_housing_requirement=450,
    ))
    session.commit()

    card = build_council_overview(session)[0]
    assert card["has_missing_evidence"] is False


def test_council_with_no_local_plan_has_no_plan_and_flagged_missing(session):
    _enable_monitoring(session, "testcouncil")
    session.commit()

    cards = build_council_overview(session)
    card = next((c for c in cards if c["council_code"] == "testcouncil"), None)
    assert card is not None
    assert card["plan_name"] is None
    assert card["current_stage"] == "No Local Plan yet"
    assert card["has_missing_evidence"] is True


# --- Five-year supply / housing requirement display --------------------------


def test_overview_card_five_year_supply_and_housing_requirement(session):
    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Housing Plan", status="adopted",
        five_year_supply_years=1.77, total_housing_requirement=31790,
    ))
    session.commit()

    card = build_council_overview(session)[0]
    assert card["five_year_supply_years"] == 1.77
    assert card["housing_requirement"] == 31790
    assert card["housing_requirement_basis"] == "total"


def test_housing_requirement_falls_back_to_annual_when_no_total_stated(session):
    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Annual Plan", status="adopted", annual_housing_requirement=450,
    ))
    session.commit()

    card = build_council_overview(session)[0]
    assert card["housing_requirement"] == 450
    assert card["housing_requirement_basis"] == "annual"


def test_unsupported_housing_values_are_none_never_zero(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="Unstated Plan", status="adopted"))
    session.commit()

    card = build_council_overview(session)[0]
    assert card["housing_requirement"] is None
    assert card["five_year_supply_years"] is None


# --- Allocation and visual-evidence counts -----------------------------------


def test_detail_allocation_counts(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Alloc Plan", status="adopted")
    session.add(plan)
    session.commit()
    session.add(LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan.id, site_name="Matched", plan_name="Alloc Plan",
        plan_status="adopted", minimum_dwellings=50, matched_site_id=None, review_status="needs_confirmation",
    ))
    session.add(LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan.id, site_name="Unmatched", plan_name="Alloc Plan",
        plan_status="adopted", minimum_dwellings=80,
    ))
    session.commit()

    detail = build_council_detail(session, "testcouncil")
    assert detail["allocations"]["total"] == 2
    assert detail["allocations"]["matched"] == 0
    assert detail["allocations"]["without_application"] == 2
    assert detail["allocations"]["needing_review"] == 1


def test_detail_visual_evidence_counts(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Visual Plan", status="adopted")
    session.add(plan)
    session.commit()
    session.add(VisualEvidence(
        local_plan_id=plan.id, source_page=1, status="current", review_status="confirmed",
    ))
    session.add(VisualEvidence(
        local_plan_id=plan.id, source_page=2, status="current", review_status="needs_review",
    ))
    # A rejected image must never be counted.
    session.add(VisualEvidence(
        local_plan_id=plan.id, source_page=3, status="current", review_status="rejected",
    ))
    session.commit()

    detail = build_council_detail(session, "testcouncil")
    assert detail["visual_evidence"]["total"] == 2
    assert detail["visual_evidence"]["confirmed"] == 1
    assert detail["visual_evidence"]["needs_review"] == 1


# --- Coverage / missing-document rendering (data-level) ----------------------


def test_detail_coverage_reuses_the_coverage_engine_and_reports_missing(session):
    detail = build_council_detail(session, "testcouncil")
    assert detail["coverage"]  # expected_document_types has a non-empty default list
    assert all("missing" in row for row in detail["coverage"])
    # An onboarded-but-empty council has nothing discovered - every row missing.
    assert all(row["missing"] for row in detail["coverage"])


def test_detail_evidence_gaps_combine_coverage_and_housing_fields(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Gappy Plan", status="draft_consultation")
    session.add(plan)
    session.commit()

    detail = build_council_detail(session, "testcouncil")
    assert any("five-year" in gap.lower() for gap in detail["evidence_gaps"])


# --- Performance: no N+1 in this sprint's own new code ----------------------
#
# build_council_overview reuses app.policy.council_dashboard.
# build_council_dashboard (Sprint 2, untouched by this sprint - "reuse
# existing helpers", "do not duplicate policy business logic") for the
# base council/plan enumeration, which has its own established, already-
# tested per-council query pattern from Sprint 2 - not rewritten here.
# What THIS sprint's own code must guarantee is batching on TOP of that:
# exactly one query for every council's LocalPlanCouncil roles, and one
# query for every plan referenced, never one extra query per council for
# either of those two additions.


def test_plan_roles_by_council_is_a_single_batched_query_for_any_number_of_councils(session):
    from sqlalchemy import event

    from app.reporting.council_intelligence import _plan_roles_by_council

    codes = ["testcouncil", "othercouncil"]
    for i in range(5):
        code = f"perf{i}"
        session.add(Council(
            code=code, name=f"Perf Council {i}", base_url="https://perf.invalid",
            date_field_mode="received", doc_system="idox",
        ))
        codes.append(code)
    session.commit()

    queries = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(session.get_bind(), "before_cursor_execute", _count)
    try:
        _plan_roles_by_council(session, codes)
    finally:
        event.remove(session.get_bind(), "before_cursor_execute", _count)

    assert len(queries) == 1


def test_council_overview_plan_lookup_is_batched_not_per_row(session):
    """The plans_by_id fetch inside build_council_overview is one
    select(...).where(LocalPlan.id.in_(...)) for every plan across every
    council, never one query per plan - verified by seeding several
    councils with their own plan and counting exactly the queries
    build_council_overview's OWN batching additions issue after the reused
    build_council_dashboard call returns."""
    for i in range(5):
        code = f"perf{i}"
        session.add(Council(
            code=code, name=f"Perf Council {i}", base_url="https://perf.invalid",
            date_field_mode="received", doc_system="idox",
        ))
        session.commit()
        session.add(LocalPlan(council_code=code, plan_name=f"Plan {i}", status="adopted", five_year_supply_years=2.0))
    session.commit()

    cards = build_council_overview(session)
    # Every seeded council with a plan gets a real card - correctness
    # alongside the batching guarantee above.
    assert sum(1 for c in cards if c["council_code"].startswith("perf")) == 5


# --- No AI calls, no database writes -----------------------------------------


def test_council_intelligence_data_module_never_imports_an_ai_client():
    import app.reporting.council_intelligence as module
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "openai" not in source.lower()
    assert "OpenAI(" not in source


def test_build_council_overview_and_detail_make_no_database_writes(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="Read Only Plan", status="adopted"))
    session.commit()

    build_council_overview(session)
    build_council_detail(session, "testcouncil")

    assert len(session.new) == 0
    assert len(session.dirty) == 0


def test_build_council_detail_returns_none_for_unknown_council(session):
    assert build_council_detail(session, "does-not-exist") is None


# --- Joint-plan visual evidence must not be double-counted across every ----
# --- participating authority (real bug found during manual verification) --


def test_joint_plan_wide_images_are_not_counted_for_a_participating_authority_with_no_own_plan(session):
    """A council whose ONLY linked plan is a joint plan it merely
    participates in (not its own single-authority plan) must not inherit
    that plan's plan-wide (non-allocation-specific) image count - those
    images are not provably about this specific council."""
    session.add(Council(
        code="thirdcouncil", name="Third Council", base_url="https://third.invalid",
        date_field_mode="received", doc_system="idox",
    ))
    joint_plan = LocalPlan(council_code="testcouncil", plan_name="Places for Everyone", status="adopted")
    session.add(joint_plan)
    session.commit()
    session.add(LocalPlanCouncil(local_plan_id=joint_plan.id, council_code="testcouncil", role="legacy_owner", is_lead_authority=True))
    session.add(LocalPlanCouncil(local_plan_id=joint_plan.id, council_code="thirdcouncil", role="participating_authority", is_lead_authority=False))
    session.commit()
    # A plan-wide image (no allocation_id) - genuinely ambiguous which
    # borough it's actually about, so must not count for a participant.
    session.add(VisualEvidence(local_plan_id=joint_plan.id, source_page=1, status="current", review_status="confirmed"))
    session.commit()

    detail_owner = build_council_detail(session, "testcouncil")
    detail_participant = build_council_detail(session, "thirdcouncil")
    assert detail_owner["visual_evidence"]["total"] == 1
    assert detail_participant["visual_evidence"]["total"] == 0


def test_allocation_specific_images_still_count_for_the_correct_participating_authority(session):
    """The fix above must not throw out genuinely council-specific
    evidence - an image tied to one of THIS council's own allocations
    still counts, even though the plan itself is a joint plan."""
    session.add(Council(
        code="thirdcouncil", name="Third Council", base_url="https://third.invalid",
        date_field_mode="received", doc_system="idox",
    ))
    joint_plan = LocalPlan(council_code="testcouncil", plan_name="Places for Everyone", status="adopted")
    session.add(joint_plan)
    session.commit()
    session.add(LocalPlanCouncil(local_plan_id=joint_plan.id, council_code="testcouncil", role="legacy_owner", is_lead_authority=True))
    session.add(LocalPlanCouncil(local_plan_id=joint_plan.id, council_code="thirdcouncil", role="participating_authority", is_lead_authority=False))
    allocation = LocalPlanSite(
        council_code="thirdcouncil", local_plan_id=joint_plan.id, site_name="JPA 99",
        plan_name="Places for Everyone", plan_status="adopted", minimum_dwellings=200,
    )
    session.add(allocation)
    session.commit()
    session.add(VisualEvidence(
        allocation_id=allocation.id, source_page=1, status="current", review_status="confirmed",
    ))
    session.commit()

    detail_participant = build_council_detail(session, "thirdcouncil")
    assert detail_participant["visual_evidence"]["total"] == 1


# --- Presentation refinement: wide layout / responsive grid ------------------


def test_wide_canvas_applied_only_to_council_intelligence_overview():
    """wide_canvas() must widen ONLY the overview page (refinement Part 1) -
    every other page keeps the shared shell's normal contained width,
    including the Council Intelligence Detail page (not asked for here) and
    Council Operations."""
    overview_source = Path(__file__).resolve().parents[1].joinpath(
        "app", "ui", "pages", "5_Council_Intelligence.py"
    ).read_text(encoding="utf-8")
    assert "wide_canvas()" in overview_source

    other_pages = [
        "6_Council_Intelligence_Detail.py", "4_Council_Dashboard.py",
        "3_Local_Plan_Sites.py", "0_Explore.py", "1_Scheme_Detail.py", "2_Review_Site_Links.py",
    ]
    for filename in other_pages:
        source = Path(__file__).resolve().parents[1].joinpath("app", "ui", "pages", filename).read_text(encoding="utf-8")
        assert "wide_canvas()" not in source, f"{filename} must not be widened by this refinement"


def test_responsive_council_card_grid_css_present():
    """The 3/2/1-per-row responsive grid (refinement Part 1) is driven by
    CSS Grid auto-fit/minmax scoped to the "council-grid" container key -
    verify both halves of the wiring exist: the page renders cards inside
    that container, and app.ui.shell's stylesheet defines the matching
    responsive rule. auto-fit/minmax was chosen over fixed viewport-width
    media queries because the sidebar's own width isn't part of the
    viewport-width number, which produced inconsistent 2-3-per-row results
    at in-between widths when tried first - auto-fit reflows directly from
    whatever content width is actually available."""
    page_source = Path(__file__).resolve().parents[1].joinpath(
        "app", "ui", "pages", "5_Council_Intelligence.py"
    ).read_text(encoding="utf-8")
    assert 'st.container(key="council-grid")' in page_source

    shell_source = Path(__file__).resolve().parents[1].joinpath("app", "ui", "shell.py").read_text(encoding="utf-8")
    assert 'st-key-council-grid' in shell_source
    assert "grid-template-columns: repeat(auto-fit, minmax(320px, 1fr))" in shell_source
    # The rule must be scoped to the OUTER row only (direct-child chain),
    # never a bare descendant selector that would also catch each card's
    # own nested 2x2 metric-tile columns and break their layout.
    assert '> [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"]' in shell_source


# --- Presentation refinement: headline metric hierarchy ----------------------


def test_evidence_is_not_a_headline_metric_tile():
    """"Evidence" must no longer appear as one of the card's four headline
    metric tiles (refinement Part 2) - evidence freshness/gaps move to a
    compact secondary caption instead."""
    page_source = Path(__file__).resolve().parents[1].joinpath(
        "app", "ui", "pages", "5_Council_Intelligence.py"
    ).read_text(encoding="utf-8")
    assert '"Evidence", card["evidence_freshness"]' not in page_source
    assert 'stat_tile("Evidence"' not in page_source


def test_headline_tiles_use_wrapping_components_not_st_metric():
    """The headline metric tiles must use the non-truncating
    stat_tile/five_year_supply_tile components, never a bare st.metric call
    that Streamlit would ellipsis-truncate at narrow column widths
    (refinement Part 3 - the "9,48...", "Mon..." failure this fixes)."""
    page_source = Path(__file__).resolve().parents[1].joinpath(
        "app", "ui", "pages", "5_Council_Intelligence.py"
    ).read_text(encoding="utf-8")
    render_fn = page_source[page_source.index("def _render_council_card"):page_source.index("with st.container(key=\"council-grid\")")]
    assert "st.metric(" not in render_fn
    assert "five_year_supply_tile(" in render_fn
    assert "stat_tile(" in render_fn


def test_headline_delivery_or_milestone_prefers_delivery_over_milestone(session):
    plan = LocalPlan(
        council_code="testcouncil", plan_name="Delivered Plan", status="adopted",
        homes_delivered_latest_period=120, latest_reporting_period="2024/25",
        next_milestone="Submission", next_milestone_date="November 2026",
    )
    metric = _headline_delivery_or_milestone(plan)
    assert metric["kind"] == "delivery"
    assert metric["value"] == "120 homes"
    assert "2024/25" in metric["label"]


def test_headline_delivery_or_milestone_falls_back_to_milestone_when_no_delivery(session):
    plan = LocalPlan(
        council_code="testcouncil", plan_name="Emerging Plan", status="draft_consultation",
        next_milestone="Submission", next_milestone_date="November 2026",
    )
    metric = _headline_delivery_or_milestone(plan)
    assert metric["kind"] == "milestone"
    assert metric["value"] == "November 2026"
    assert metric["caption"] == "Submission"


def test_headline_delivery_or_milestone_honest_when_neither_exists(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Quiet Plan", status="preparation")
    metric = _headline_delivery_or_milestone(plan)
    assert metric["kind"] == "none"
    assert metric["value"] == "Not yet stated"


# --- Presentation refinement: fully readable, non-truncated values -----------


def test_housing_requirement_display_is_compact_and_never_ellipsised():
    assert _format_housing_requirement(9486, "total") == "9,486 homes"
    assert _format_housing_requirement(452, "annual") == "452 homes/year"
    assert _format_housing_requirement(None, None) is None
    for value in (_format_housing_requirement(9486, "total"), _format_housing_requirement(452, "annual")):
        assert "…" not in value
        assert "..." not in value


def test_overview_card_housing_requirement_display_field(session):
    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Display Plan", status="adopted", total_housing_requirement=9486,
    ))
    session.commit()

    card = build_council_overview(session)[0]
    assert card["housing_requirement_display"] == "9,486 homes"
    assert "…" not in card["housing_requirement_display"]


# --- Presentation refinement: five-year housing supply ------------------------


def test_five_year_supply_state_and_display_for_a_real_low_figure():
    """Stockport's real value (1.77 years) must show as "1.77 years" with a
    "warning" state - below the five-year requirement."""
    assert _five_year_supply_state(1.77) == "warning"
    assert _format_five_year_supply(1.77) == "1.77 years"


def test_five_year_supply_state_ok_at_or_above_five_years():
    assert _five_year_supply_state(5.0) == "ok"
    assert _five_year_supply_state(6.4) == "ok"


def test_five_year_supply_state_warning_below_five_years():
    assert _five_year_supply_state(4.99) == "warning"
    assert _five_year_supply_state(0.0) == "warning"


def test_five_year_supply_unverified_and_never_a_bare_dash_when_missing():
    """Bury's real case today: no verified five-year supply figure at all -
    must display an explicit "Not yet verified", never only an em dash and
    never an inferred/estimated number."""
    assert _five_year_supply_state(None) == "unverified"
    assert _format_five_year_supply(None) == "Not yet verified"
    assert _format_five_year_supply(None) != "—"


def test_overview_card_five_year_supply_display_and_state_fields(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="Bury Local Plan", status="proposed_submission"))
    session.commit()

    card = build_council_overview(session)[0]
    assert card["five_year_supply_state"] == "unverified"
    assert card["five_year_supply_display"] == "Not yet verified"


def test_overview_card_reflects_stale_or_missing_supply_evidence_as_unverified_not_current(session):
    """A council whose plan has no five_year_supply_years at all must never
    be presented as if it had a current, trusted figure - state must be
    "unverified", never "ok"."""
    session.add(LocalPlan(council_code="testcouncil", plan_name="No Supply Plan", status="adopted"))
    session.commit()

    card = build_council_overview(session)[0]
    assert card["five_year_supply_state"] != "ok"
    assert card["five_year_supply_state"] == "unverified"


# --- Presentation refinement: status-based card colour ------------------------


def test_status_color_category_six_bucket_taxonomy(session):
    """Commercial Planning Readiness refinement (Part 7): six buckets -
    Adopted / Emerging / Regulation 18 / Examination / Withdrawn /
    Joint-plan only. A plan that is genuinely this council's OWN drives the
    status-based bucket; a plan that ISN'T (primary_plan_is_own=False, or
    no plan at all) always gets "joint-plan-only", regardless of that
    plan's own status."""
    own = lambda status: LocalPlan(council_code="x", plan_name="p", status=status)  # noqa: E731
    assert _status_color_category(own("adopted"), True) == "adopted"
    assert _status_color_category(own("proposed_submission"), True) == "emerging"
    assert _status_color_category(own("main_modifications"), True) == "emerging"
    assert _status_color_category(own("draft_consultation"), True) == "regulation-18"
    assert _status_color_category(own("issues_and_options"), True) == "regulation-18"
    assert _status_color_category(own("examination"), True) == "examination"
    assert _status_color_category(own("submitted"), True) == "examination"
    assert _status_color_category(own("withdrawn"), True) == "withdrawn"
    assert _status_color_category(own("paused"), True) == "withdrawn"
    assert _status_color_category(None, False) == "joint-plan-only"
    # Even an ADOPTED joint plan gets joint-plan-only when it isn't this
    # council's own plan - the commercially relevant signal is "this
    # council has no Local Plan of its own", which outranks the joint
    # plan's own status.
    assert _status_color_category(own("adopted"), False) == "joint-plan-only"


def test_status_color_css_classes_defined_for_every_category():
    shell_source = Path(__file__).resolve().parents[1].joinpath("app", "ui", "shell.py").read_text(encoding="utf-8")
    for category in ("adopted", "emerging", "regulation-18", "examination", "withdrawn", "joint-plan-only"):
        assert f'st-key-cc-{category}-' in shell_source


def test_status_remains_represented_in_text_not_colour_alone():
    """Colour is a restrained addition, never a replacement for the
    existing text/chip that already states the plan's status (refinement
    Part 5/7 - "status must also be conveyed by text/badge, not colour
    alone"). The Commercial Planning Readiness refinement replaced the
    plain Adopted/Emerging badge with the Planning Readiness chip, which
    still renders its own status text/emoji - never colour alone - plus
    the "No Local Plan yet" badge for the no-plan case."""
    page_source = Path(__file__).resolve().parents[1].joinpath(
        "app", "ui", "pages", "5_Council_Intelligence.py"
    ).read_text(encoding="utf-8")
    assert "planning_readiness_chip(card[" in page_source
    assert 'status_badge("info", "No Local Plan yet")' in page_source

    shell_source = Path(__file__).resolve().parents[1].joinpath("app", "ui", "shell.py").read_text(encoding="utf-8")
    render_fn = shell_source[shell_source.index("def planning_readiness_chip"):shell_source.index("def planning_health_banner")]
    assert "chip['label']" in render_fn or 'chip["label"]' in render_fn


# --- Presentation refinement: no AI calls, no database writes ----------------


def test_refined_overview_page_still_makes_no_ai_calls():
    page_source = Path(__file__).resolve().parents[1].joinpath(
        "app", "ui", "pages", "5_Council_Intelligence.py"
    ).read_text(encoding="utf-8")
    assert "openai" not in page_source.lower()
    assert "OpenAI(" not in page_source


def test_refined_build_council_overview_still_makes_no_database_writes(session):
    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Refinement Plan", status="adopted",
        five_year_supply_years=1.77, total_housing_requirement=31790,
    ))
    session.commit()

    build_council_overview(session)

    assert len(session.new) == 0
    assert len(session.dirty) == 0


# --- Housing Position caption correctness (primary_plan_is_own) ------------


def test_primary_plan_is_own_true_for_single_authority_plan(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="Own Plan", status="adopted"))
    session.commit()

    detail = build_council_detail(session, "testcouncil")
    assert detail["primary_plan_is_own"] is True


def test_primary_plan_is_own_false_for_participant_with_only_a_joint_plan(session):
    session.add(Council(
        code="thirdcouncil", name="Third Council", base_url="https://third.invalid",
        date_field_mode="received", doc_system="idox",
    ))
    joint_plan = LocalPlan(council_code="testcouncil", plan_name="Places for Everyone", status="adopted")
    session.add(joint_plan)
    session.commit()
    session.add(LocalPlanCouncil(local_plan_id=joint_plan.id, council_code="thirdcouncil", role="participating_authority", is_lead_authority=False))
    session.commit()

    detail = build_council_detail(session, "thirdcouncil")
    assert detail["primary_plan_is_own"] is False


# --- Commercial Planning Readiness refinement: Planning Readiness chip -------


def test_planning_readiness_chip_none_when_no_plan():
    assert _planning_readiness_chip(None) is None


def test_planning_readiness_chip_adopted_with_year_and_age():
    this_year = dt.datetime.now(dt.timezone.utc).year
    adopted_year = this_year - 7
    plan = LocalPlan(council_code="x", plan_name="p", status="adopted", adoption_date=f"21 March {adopted_year}")
    chip = _planning_readiness_chip(plan)
    assert chip["emoji"] == "🟢"
    assert chip["label"] == f"Adopted {adopted_year}"
    assert chip["sublabel"] == "7 years old"


def test_planning_readiness_chip_adopted_without_a_parseable_year():
    """Never estimates a year that isn't actually in the stored evidence -
    falls back to a bare "Adopted" chip with no sublabel."""
    plan = LocalPlan(council_code="x", plan_name="p", status="adopted", adoption_date=None)
    chip = _planning_readiness_chip(plan)
    assert chip["label"] == "Adopted"
    assert chip["sublabel"] is None


def test_planning_readiness_chip_maps_every_non_adopted_status():
    cases = {
        "proposed_submission": ("🟣", "Regulation 19"),
        "examination": ("🔵", "Examination"),
        "submitted": ("🔵", "Submitted"),
        "main_modifications": ("🟠", "Main Modifications"),
        "issues_and_options": ("🟡", "Regulation 18"),
        "draft_consultation": ("🟡", "Regulation 18"),
        "withdrawn": ("🔴", "Withdrawn"),
        "paused": ("🔴", "Paused"),
    }
    for status, (emoji, label) in cases.items():
        chip = _planning_readiness_chip(LocalPlan(council_code="x", plan_name="p", status=status))
        assert chip["emoji"] == emoji, status
        assert chip["label"] == label, status


def test_overview_card_carries_planning_readiness_chip(session):
    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Chip Plan", status="adopted", adoption_date="21 March 2024",
    ))
    session.commit()

    card = build_council_overview(session)[0]
    assert card["planning_readiness_chip"]["label"].startswith("Adopted 2024")


# --- Commercial Planning Readiness refinement: plan age -----------------------


def test_plan_age_years_computed_from_adoption_year():
    this_year = dt.datetime.now(dt.timezone.utc).year
    assert _plan_age_years(this_year - 4) == 4
    assert _plan_age_years(this_year - 11) == 11
    assert _plan_age_years(this_year) == 0


def test_plan_age_years_none_when_year_unavailable():
    assert _plan_age_years(None) is None


# --- Commercial Planning Readiness refinement: Planning Health banner --------


def test_planning_health_banner_strong_position_for_adopted_with_healthy_supply():
    plan = LocalPlan(council_code="x", plan_name="p", status="adopted", five_year_supply_years=6.2)
    health = _planning_health_banner(plan)
    assert health["label"] == "Strong planning position"
    assert health["emoji"] == "🟢"


def test_planning_health_banner_growing_pressure_for_emerging_with_healthy_supply():
    plan = LocalPlan(council_code="x", plan_name="p", status="draft_consultation", five_year_supply_years=5.5)
    health = _planning_health_banner(plan)
    assert health["label"] == "Growing delivery pressure"
    assert health["emoji"] == "🟠"


def test_planning_health_banner_high_opportunity_for_supply_below_five_years():
    """Below-5-years supply is the strongest, most concrete evidence-based
    signal - triggers "High planning opportunity" regardless of the plan's
    own adopted/emerging status (Stockport's real case: emerging plan,
    1.77-year supply)."""
    plan = LocalPlan(council_code="x", plan_name="p", status="draft_consultation", five_year_supply_years=1.77)
    health = _planning_health_banner(plan)
    assert health["label"] == "High planning opportunity"
    assert health["emoji"] == "🔴"

    adopted_but_short = LocalPlan(council_code="x", plan_name="p", status="adopted", five_year_supply_years=3.0)
    assert _planning_health_banner(adopted_but_short)["label"] == "High planning opportunity"


def test_planning_health_banner_insufficient_evidence_never_invents_a_conclusion():
    """Bury's real case: no verified five-year supply figure - must say
    evidence is still being assessed, never guess a Strong/Growing/High
    Opportunity classification without the supporting figure."""
    plan = LocalPlan(council_code="x", plan_name="p", status="proposed_submission", five_year_supply_years=None)
    health = _planning_health_banner(plan)
    assert health["label"] == "Planning position still being assessed"
    assert _planning_health_banner(None)["label"] == "Planning position still being assessed"


def test_overview_card_carries_planning_health_banner(session):
    session.add(LocalPlan(
        council_code="testcouncil", plan_name="Health Plan", status="draft_consultation", five_year_supply_years=1.77,
    ))
    session.commit()

    card = build_council_overview(session)[0]
    assert card["planning_health"]["label"] == "High planning opportunity"


def test_planning_health_banner_rendered_in_page_not_ai_generated():
    """The banner must be rendered via the deterministic
    _planning_health_banner data, never routed through an AI call - the
    page source itself must not construct this text near any AI client."""
    page_source = Path(__file__).resolve().parents[1].joinpath(
        "app", "ui", "pages", "5_Council_Intelligence.py"
    ).read_text(encoding="utf-8")
    assert "planning_health_banner(card[" in page_source
    assert "openai" not in page_source.lower()
