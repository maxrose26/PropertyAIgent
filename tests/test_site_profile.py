"""Tests for app.reporting.site_profile (Sprint 4.4, "Flagship Site
Profile") - a pure data-assembly module, so these tests seed a real
(in-memory) schema and assert against it directly, the same discipline
already established by tests/test_dashboard.py and
tests/test_council_intelligence.py.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from app.db.models import (
    Application,
    LocalPlan,
    LocalPlanSite,
    PolicyChangeEvent,
    SchemeIntelligence,
    Site,
    VisualEvidence,
)
from app.pipeline.lapse_tracking import classify_decision_status, compute_lapse_status
from app.pipeline.phase_tracking import build_phase_breakdown
from app.policy.site_view import build_site_policy_intelligence
from app.reporting.residential_mix import compute_affordable_headline
from app.reporting.site_profile import (
    FIVE_YEAR_SUPPLY_WARNING_THRESHOLD,
    MAJOR_UNIT_THRESHOLD,
    _council_five_year_supply,
    build_ai_summary_view,
    build_evidence_gaps,
    build_headline_metrics,
    build_opportunity_position,
    build_policy_position,
    build_site_header,
    build_site_profile,
    build_site_timeline,
    build_visual_evidence_gallery,
    has_significant_missing_evidence,
)
from app.ui.common import aggregate_scheme_fields, pick_representative_application


def _now(offset_minutes: int = 0) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=offset_minutes)


def _make_site(session, **kwargs) -> Site:
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street", **kwargs)
    session.add(site)
    session.commit()
    return site


def _make_app(session, site_id: int, reference: str, **kwargs) -> Application:
    app = Application(council_code="testcouncil", reference=reference, site_id=site_id, **kwargs)
    session.add(app)
    session.commit()
    return app


# --- Headline metrics ---------------------------------------------------


def test_headline_metrics_are_four_consistent_tiles():
    merged = {"total_units_final": 45, "affordable_units_final": 12, "affordable_percentage_final": 26.7}
    lapse = {"build_status": "underway"}
    affordable_headline = compute_affordable_headline(None)
    metrics = build_headline_metrics(merged, lapse, "granted", affordable_headline)
    assert [m["label"] for m in metrics] == ["Total homes", "Affordable homes", "Decision status", "Build status"]


def test_headline_metrics_never_show_none_or_zero_for_missing_values():
    merged = {"total_units_final": None, "affordable_units_final": None}
    lapse = {"build_status": None}
    affordable_headline = compute_affordable_headline(None)
    metrics = build_headline_metrics(merged, lapse, None, affordable_headline)
    for m in metrics:
        assert m["value"] not in ("None", "0", None)
        assert "…" not in m["value"]
    assert metrics[0]["value"] == "Not yet verified"


def test_headline_metrics_estimated_units_labelled_not_silently_shown_as_confirmed():
    merged = {"total_units_final": 80, "total_units_is_estimated": True}
    affordable_headline = compute_affordable_headline(None)
    metrics = build_headline_metrics(merged, {"build_status": None}, None, affordable_headline)
    assert "(est.)" in metrics[0]["value"]


def test_headline_metrics_affordable_tile_sourced_from_single_scheme_version(session):
    """The Affordable homes tile must come from affordable_headline (one
    scheme version), never merged['affordable_units_final'] (which can be
    cross-application) - Sprint 4.4 Amendment Part 5's "never mix
    affordable units from one scheme version with total homes from
    another"."""
    site = _make_site(session)
    app = _make_app(session, site.id, "MIX/1")
    scheme = SchemeIntelligence(
        application_id=app.id, total_units_final=100, affordable_units_final=30, affordable_percentage_final=30.0,
    )
    session.add(scheme)
    session.commit()
    # merged deliberately disagrees with the scheme row, to prove it's ignored.
    merged = {"total_units_final": 999, "affordable_units_final": 999}
    affordable_headline = compute_affordable_headline(scheme)
    metrics = build_headline_metrics(merged, {"build_status": None}, None, affordable_headline)
    affordable_metric = next(m for m in metrics if m["label"] == "Affordable homes")
    assert affordable_metric["value"] == "30 affordable homes"
    assert affordable_metric["caption"] == "30% affordable"


# --- Opportunity Position -----------------------------------------------


def test_opportunity_position_flags_major_scheme():
    merged = {"total_units_final": MAJOR_UNIT_THRESHOLD + 50}
    lapse = {"status": "safe", "build_status": "unknown", "deadline": None}
    op = build_opportunity_position(
        merged=merged, lapse=lapse, phase_breakdown=[], policy_rows=[], council_supply=None, has_missing_evidence=False,
    )
    assert any("Major scheme" in r for r in op["reasons"])
    assert "permission likely" not in op["headline"].lower()
    assert "strong chance" not in op["headline"].lower()


def test_opportunity_position_never_uses_banned_permission_likelihood_wording():
    banned = ("planning permission likely", "strong chance of approval")
    merged = {"total_units_final": 500}
    lapse = {"status": "approaching", "build_status": None, "deadline": dt.date.today() + dt.timedelta(days=30)}
    op = build_opportunity_position(
        merged=merged, lapse=lapse, phase_breakdown=[], policy_rows=[], council_supply=None, has_missing_evidence=False,
    )
    full_text = " ".join([op["headline"], op["why_it_matters"], op["investigate_next"], *op["reasons"]]).lower()
    for phrase in banned:
        assert phrase not in full_text


def test_opportunity_position_approaching_lapse_flagged():
    merged = {"total_units_final": 20}
    deadline = dt.date.today() + dt.timedelta(days=30)
    lapse = {"status": "approaching", "build_status": None, "deadline": deadline}
    op = build_opportunity_position(
        merged=merged, lapse=lapse, phase_breakdown=[], policy_rows=[], council_supply=None, has_missing_evidence=False,
    )
    assert any("deadline" in r.lower() for r in op["reasons"])


def test_opportunity_position_undeveloped_phase_flagged():
    merged = {"total_units_final": 300}
    lapse = {"status": "underway", "build_status": "underway", "deadline": None}
    phase_breakdown = [
        {"status": "approved_not_started", "unit_count": 50, "kind": "phase", "code": "1"},
        {"status": "underway", "unit_count": 100, "kind": "phase", "code": "2"},
    ]
    op = build_opportunity_position(
        merged=merged, lapse=lapse, phase_breakdown=phase_breakdown, policy_rows=[], council_supply=None,
        has_missing_evidence=False,
    )
    assert any("undeveloped phase" in r.lower() for r in op["reasons"])
    assert op["why_it_matters"]
    assert op["investigate_next"]


def test_opportunity_position_low_five_year_supply_flagged_as_pressure_not_prediction():
    merged = {"total_units_final": 20}
    # status "not_granted" deliberately keeps the "not yet commenced"
    # fallback reason from also firing, so this test isolates the
    # five-year-supply signal specifically.
    lapse = {"status": "not_granted", "build_status": "unknown", "deadline": None}
    council_supply = {"plan_name": "Stockport Local Plan", "years": 1.77}
    op = build_opportunity_position(
        merged=merged, lapse=lapse, phase_breakdown=[], policy_rows=[], council_supply=council_supply,
        has_missing_evidence=False,
    )
    assert any("housing land supply below five years" in r.lower() for r in op["reasons"])
    assert "will receive permission" not in op["why_it_matters"].lower()
    assert "may increase pressure" in op["why_it_matters"].lower()


def test_opportunity_position_honest_when_no_signals_present():
    merged = {"total_units_final": 12}
    lapse = {"status": "not_granted", "build_status": "unknown", "deadline": None}
    op = build_opportunity_position(
        merged=merged, lapse=lapse, phase_breakdown=[], policy_rows=[], council_supply=None, has_missing_evidence=False,
    )
    assert op["reasons"] == []
    assert "no standout" in op["headline"].lower()


def test_opportunity_position_why_it_matters_and_investigate_next_always_present():
    for lapse_status in ("not_granted", "safe", "approaching", "lapsed", "underway"):
        op = build_opportunity_position(
            merged={"total_units_final": 20}, lapse={"status": lapse_status, "build_status": "unknown", "deadline": None},
            phase_breakdown=[], policy_rows=[], council_supply=None, has_missing_evidence=False,
        )
        assert op["why_it_matters"]
        assert op["investigate_next"]


# --- Policy Position -----------------------------------------------------


def test_policy_position_no_allocation_explains_not_matched_vs_not_allocated():
    policy = build_policy_position([], None)
    assert policy["allocations"] == []
    assert "not matched" not in policy["no_allocation_message"].lower() or "not allocated" in policy["no_allocation_message"].lower()
    assert "does not necessarily mean" in policy["no_allocation_message"]


def test_policy_position_with_allocation_carries_full_row_data(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Plan", status="adopted")
    session.add(plan)
    session.commit()
    site = _make_site(session)
    allocation = LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan.id, site_name="Allocation A", plan_name="Test Plan",
        plan_status="adopted", minimum_dwellings=100, matched_site_id=site.id, policy_reference="HOM 1.1",
    )
    session.add(allocation)
    session.commit()
    rows = build_site_policy_intelligence([allocation])
    policy = build_policy_position(rows, None)
    assert policy["no_allocation_message"] is None
    assert policy["allocations"][0]["allocation_reference"] == "HOM 1.1"


def test_council_five_year_supply_prefers_matched_plan(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="Plan A", status="adopted", five_year_supply_years=6.0))
    session.add(LocalPlan(council_code="testcouncil", plan_name="Plan B", status="adopted", five_year_supply_years=1.77))
    session.commit()
    policy_rows = [{"plan_name": "Plan B"}]
    result = _council_five_year_supply(session, "testcouncil", policy_rows)
    assert result["plan_name"] == "Plan B"
    assert result["years"] == 1.77


def test_council_five_year_supply_none_when_no_plan_has_a_verified_figure(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="Plan A", status="adopted"))
    session.commit()
    assert _council_five_year_supply(session, "testcouncil", []) is None


# --- Visual Evidence gallery ----------------------------------------------


def test_visual_evidence_gallery_confirmed_outranks_suggested(session):
    site = _make_site(session)
    session.add(VisualEvidence(
        site_id=site.id, source_page=1, status="current", review_status="confirmed", is_primary=True,
        image_type="site_location_plan",
    ))
    session.add(VisualEvidence(
        site_id=site.id, source_page=2, status="current", review_status="needs_review", image_type="masterplan",
    ))
    session.add(VisualEvidence(
        site_id=site.id, source_page=3, status="current", review_status="confirmed", image_type="allocation_map",
    ))
    session.commit()
    gallery = build_visual_evidence_gallery(session, site.id)
    assert gallery["has_any"] is True
    assert gallery["primary"]["is_primary"] is True
    assert len(gallery["other_confirmed"]) == 1
    assert len(gallery["needs_review"]) == 1


def test_visual_evidence_gallery_no_evidence_state(session):
    site = _make_site(session)
    gallery = build_visual_evidence_gallery(session, site.id)
    assert gallery["has_any"] is False
    assert gallery["primary"] is None


def test_visual_evidence_card_never_exposes_a_filesystem_path_as_a_label(session):
    """Confidence in the assertion below: the card dict's own "label" field
    must be the customer-facing image_type label, not image_path/
    thumbnail_path text - those are only ever returned under the
    "image_path" key, which app.ui.shell only ever passes to st.image, never
    renders as text (see shell._visual_evidence_card)."""
    site = _make_site(session)
    session.add(VisualEvidence(
        site_id=site.id, source_page=1, status="current", review_status="confirmed", is_primary=True,
        image_type="site_location_plan", image_path="C:\\secret\\local\\path.png",
    ))
    session.commit()
    gallery = build_visual_evidence_gallery(session, site.id)
    assert gallery["primary"]["label"] != gallery["primary"]["image_path"]
    assert "secret" not in gallery["primary"]["label"]


# --- Timeline --------------------------------------------------------------


def test_timeline_chronology_sorted_most_recent_first(session):
    site = _make_site(session)
    a1 = _make_app(session, site.id, "APP/1", application_received="Mon 01 Jan 2024")
    a2 = _make_app(session, site.id, "APP/2", application_received="Mon 01 Jan 2025")
    lapse = compute_lapse_status([a1, a2], site)
    entries = build_site_timeline(session, site, [a1, a2], lapse, [], None, None, 0)
    assert entries[0]["when"] > entries[-1]["when"]
    assert any("APP/2" in e["label"] for e in entries)
    assert any("APP/1" in e["label"] for e in entries)


def test_timeline_never_fabricates_a_date_for_an_undated_record(session):
    site = _make_site(session)
    app = _make_app(session, site.id, "APP/UNDATED")  # no application_received at all
    lapse = compute_lapse_status([app], site)
    entries = build_site_timeline(session, site, [app], lapse, [], None, None, 0)
    assert entries == []


def test_timeline_aggregates_repeated_progress_filings_into_one_entry(session):
    site = _make_site(session)
    app = _make_app(session, site.id, "APP/MAIN", application_received="Mon 01 Jan 2020", decision="Approve", decision_issued_date="Mon 01 Jan 2020")
    for i in range(4):
        session.add(Application(
            council_code="testcouncil", reference=f"APP/DISCHARGE-{i}", site_id=site.id,
            application_category="condition_discharge_or_details",
            application_received=f"Mon 0{i + 1} Feb 2020",
        ))
    session.commit()
    lapse = compute_lapse_status([app], site)
    entries = build_site_timeline(session, site, [app], lapse, [], None, None, 0)
    progress_entries = [e for e in entries if "progress filing" in e["label"]]
    assert len(progress_entries) == 1
    assert "4 commencement/progress filings" in progress_entries[0]["label"]


def test_timeline_includes_policy_events_scoped_to_this_sites_allocation(session):
    plan = LocalPlan(council_code="testcouncil", plan_name="Plan", status="adopted")
    session.add(plan)
    session.commit()
    site = _make_site(session)
    allocation = LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan.id, site_name="A", plan_name="Plan",
        plan_status="adopted", matched_site_id=site.id,
    )
    session.add(allocation)
    session.commit()
    session.add(PolicyChangeEvent(
        allocation_id=allocation.id, event_type="new_allocation", detected_at=_now(),
    ))
    session.commit()
    policy_rows = build_site_policy_intelligence([allocation])
    lapse = compute_lapse_status([], site)
    entries = build_site_timeline(session, site, [], lapse, policy_rows, None, None, 0)
    assert any("allocation" in e["label"].lower() for e in entries)


# --- AI Summary ------------------------------------------------------------


def test_ai_summary_view_honest_when_none_stored(session):
    site = _make_site(session)
    view = build_ai_summary_view(site)
    assert view["has_summary"] is False
    assert view["text"] is None


def test_ai_summary_view_shows_stored_text_and_timestamp(session):
    site = _make_site(session, status_summary="A concise status note.", status_summary_updated_at=_now())
    view = build_ai_summary_view(site)
    assert view["has_summary"] is True
    assert view["text"] == "A concise status note."
    assert view["generated_at"] is not None


# --- Evidence gaps -----------------------------------------------------------


def test_evidence_gaps_flags_missing_unit_count():
    gaps = build_evidence_gaps(
        {"total_units_final": None}, {"build_status": "unknown"}, [],
        {"has_any": False, "needs_review": []}, {"has_summary": False},
    )
    assert any("unit count" in g.lower() for g in gaps)
    assert any("visual evidence" in g.lower() for g in gaps)
    assert any("ai status summary" in g.lower() for g in gaps)


def test_has_significant_missing_evidence_true_when_units_missing():
    assert has_significant_missing_evidence({"total_units_final": None}, {"build_status": "underway"}, []) is True


def test_has_significant_missing_evidence_false_when_core_facts_present():
    assert has_significant_missing_evidence(
        {"total_units_final": 50, "total_units_is_estimated": False}, {"build_status": "underway"}, [],
    ) is False


# --- Header ------------------------------------------------------------------


def test_header_never_shows_none_placeholder_for_missing_badges(session):
    site = _make_site(session)
    header = build_site_header(
        site=site, merged={}, lapse={"status": "not_granted", "build_status": "unknown"}, decision_status=None,
        policy_rows=[], last_ai_summary_at=None, latest_visual_evidence_at=None,
    )
    assert header["decision_status_label"] is None
    assert header["build_status_label"] is None
    assert header["allocation_badge"] is None


def test_header_carries_allocation_badge_when_matched(session):
    site = _make_site(session)
    policy_rows = [{"allocation_reference": "HOM 1.1", "allocation_name": "Site A", "plan_status": "adopted"}]
    header = build_site_header(
        site=site, merged={}, lapse={"status": "not_granted", "build_status": "unknown"}, decision_status=None,
        policy_rows=policy_rows, last_ai_summary_at=None, latest_visual_evidence_at=None,
    )
    assert "HOM 1.1" in header["allocation_badge"]


# --- Full assembly / integration -------------------------------------------


def test_build_site_profile_full_assembly_multiple_applications(session):
    site = _make_site(session)
    a1 = _make_app(session, site.id, "APP/1", application_received="Mon 01 Jan 2024", decision="Approve", decision_issued_date="Mon 01 Jan 2024")
    a2 = _make_app(session, site.id, "APP/2", application_received="Mon 01 Jan 2025")
    session.add(SchemeIntelligence(application_id=a1.id, total_units_final=60, developer="Acme Ltd", core_intelligence_complete=True))
    session.commit()

    apps = [a1, a2]
    merged = aggregate_scheme_fields(apps)
    rep_app = pick_representative_application(apps)
    lapse = compute_lapse_status(site.applications, site)
    decision_status = classify_decision_status(rep_app.decision, rep_app.status)
    phase_breakdown = build_phase_breakdown(site.applications)

    view = build_site_profile(
        session, site, apps, merged=merged, rep_app=rep_app, lapse=lapse,
        phase_breakdown=phase_breakdown, decision_status=decision_status,
    )
    assert view["header"]["primary_reference"] is None or isinstance(view["header"]["primary_reference"], str)
    assert len(view["headline_metrics"]) == 4
    assert view["opportunity_position"]["headline"]
    assert view["policy_position"]["no_allocation_message"] is not None
    assert view["visual_evidence"]["has_any"] is False
    assert isinstance(view["timeline"], list)
    assert view["ai_summary"]["has_summary"] is False
    assert isinstance(view["evidence_gaps"], list)


def test_build_site_profile_allocation_and_joint_plan_handling(session):
    """A council-code lead/participant distinction shouldn't matter here -
    build_site_policy_intelligence already reuses the plan's own
    council_code/plan_name regardless of joint-plan role; this test just
    confirms the Site Profile view model surfaces whatever allocation rows
    are matched, without re-deriving or blending anything itself."""
    plan = LocalPlan(council_code="testcouncil", plan_name="Places for Everyone", status="adopted")
    session.add(plan)
    session.commit()
    site = _make_site(session)
    allocation = LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan.id, site_name="JPA 1", plan_name="Places for Everyone",
        plan_status="adopted", matched_site_id=site.id, minimum_dwellings=200,
    )
    session.add(allocation)
    session.commit()
    apps = [_make_app(session, site.id, "APP/JPA1")]
    merged = aggregate_scheme_fields(apps)
    lapse = compute_lapse_status(site.applications, site)

    view = build_site_profile(
        session, site, apps, merged=merged, rep_app=apps[0], lapse=lapse, phase_breakdown=[], decision_status=None,
    )
    assert view["policy_position"]["allocations"]
    assert view["policy_position"]["allocations"][0]["plan_name"] == "Places for Everyone"


def test_build_site_profile_low_five_year_supply_surfaces_in_opportunity_position(session):
    session.add(LocalPlan(council_code="testcouncil", plan_name="Stockport Local Plan", status="draft_consultation", five_year_supply_years=1.77))
    session.commit()
    site = _make_site(session)
    apps = [_make_app(session, site.id, "APP/1")]
    merged = aggregate_scheme_fields(apps)
    lapse = compute_lapse_status(site.applications, site)

    view = build_site_profile(
        session, site, apps, merged=merged, rep_app=apps[0], lapse=lapse, phase_breakdown=[], decision_status=None,
    )
    assert any("housing land supply" in r.lower() for r in view["opportunity_position"]["reasons"])


# --- No AI calls, no database writes -----------------------------------------


def test_site_profile_data_module_never_imports_an_ai_client():
    """Scans the CODE only, not the module docstring - the docstring
    legitimately explains, in prose, why this module avoids importing
    app.ui.common (which imports the OpenAI client), which is not the
    same as actually importing one itself."""
    source = Path("app/reporting/site_profile.py").read_text(encoding="utf-8")
    first = source.index('"""')
    second = source.index('"""', first + 3)
    code_only = source[second + 3:].lower()
    assert "openai" not in code_only
    assert "OpenAI(" not in source[second + 3:]


def test_build_site_profile_makes_no_database_writes(session):
    site = _make_site(session)
    apps = [_make_app(session, site.id, "APP/1")]
    merged = aggregate_scheme_fields(apps)
    lapse = compute_lapse_status(site.applications, site)

    build_site_profile(
        session, site, apps, merged=merged, rep_app=apps[0], lapse=lapse, phase_breakdown=[], decision_status=None,
    )
    assert len(session.new) == 0
    assert len(session.dirty) == 0


def test_build_site_profile_query_count_is_small_and_bounded(session):
    """Sprint 4.4, Part 15 - a small, bounded set of batched queries, never
    one query per card/image/timeline row. Documented approximate count:
    build_site_policy_intelligence's own allocation fetch, the visual-
    evidence gallery's own query, the extra "all images" query for the
    latest-extracted timestamp, the council five-year-supply query, and the
    timeline's own allocation-scoped PolicyChangeEvent query - a handful,
    not dozens, and independent of how many applications/images exist."""
    from sqlalchemy import event

    site = _make_site(session)
    for i in range(8):
        session.add(Application(council_code="testcouncil", reference=f"APP/{i}", site_id=site.id, application_received=f"Mon 0{i + 1} Jan 2024"))
    session.commit()
    apps = session.query(Application).filter_by(site_id=site.id).all()
    for i in range(6):
        session.add(VisualEvidence(site_id=site.id, source_page=i + 1, status="current", review_status="needs_review"))
    session.commit()

    merged = aggregate_scheme_fields(apps)
    lapse = compute_lapse_status(site.applications, site)

    queries = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(session.get_bind(), "before_cursor_execute", _count)
    try:
        build_site_profile(
            session, site, apps, merged=merged, rep_app=apps[0], lapse=lapse, phase_breakdown=[], decision_status=None,
        )
    finally:
        event.remove(session.get_bind(), "before_cursor_execute", _count)

    assert len(queries) < 10


# --- Empty and partial states -------------------------------------------


def test_empty_site_with_no_evidence_at_all_produces_honest_empty_states(session):
    site = _make_site(session)
    apps = [_make_app(session, site.id, "APP/1")]
    merged = aggregate_scheme_fields(apps)
    lapse = compute_lapse_status(site.applications, site)

    view = build_site_profile(
        session, site, apps, merged=merged, rep_app=apps[0], lapse=lapse, phase_breakdown=[], decision_status=None,
    )
    assert view["visual_evidence"]["has_any"] is False
    assert view["policy_position"]["no_allocation_message"] is not None
    assert view["ai_summary"]["has_summary"] is False
    assert view["evidence_gaps"]  # a real, non-empty list of honest gaps


# --- UI wiring / structural checks -------------------------------------------


def test_flagship_page_uses_wide_canvas_scoped_via_site_profile_view():
    source = Path("app/ui/site_profile_view.py").read_text(encoding="utf-8")
    assert "wide_canvas()" in source


def test_flagship_page_tab_order_matches_the_brief():
    """Sprint 4.4 Amendment, Part 2 - Residential Mix Intelligence sits as
    its own tab #4, between Policy Position and Visual Evidence."""
    source = Path("app/ui/site_profile_view.py").read_text(encoding="utf-8")
    tabs_line = source[source.index("st.tabs("):source.index(")", source.index("st.tabs("))]
    assert tabs_line.index('"Overview"') < tabs_line.index('"Planning Position"') < tabs_line.index('"Policy Position"')
    assert tabs_line.index('"Policy Position"') < tabs_line.index('"Residential Mix Intelligence"')
    assert tabs_line.index('"Residential Mix Intelligence"') < tabs_line.index('"Visual Evidence"') < tabs_line.index('"Timeline"')
    assert tabs_line.index('"Timeline"') < tabs_line.index('"AI Summary"')


def test_flagship_page_does_not_add_market_intelligence_or_development_economics_tabs():
    source = Path("app/ui/site_profile_view.py").read_text(encoding="utf-8")
    for banned in ("Market Intelligence", "Development Economics", "Nearby Development"):
        assert banned not in source


def test_overview_tab_does_not_render_the_full_residential_mix_breakdown():
    """Sprint 4.4 Amendment, Part 3 - the Overview tab must call only
    residential_mix_overview_excerpt (a short excerpt + a link to the full
    tab), never _render_residential_mix (the full bedroom/tenure/evidence
    breakdown), which is reserved for its own dedicated tab."""
    source = Path("app/ui/site_profile_view.py").read_text(encoding="utf-8")
    overview_block = source[source.index("with tab_overview:"):source.index("with tab_planning:")]
    assert "residential_mix_overview_excerpt(" in overview_block
    assert "_render_residential_mix(" not in overview_block
    assert "_bedroom_mix_section(" not in overview_block
    assert "_affordable_tenure_section(" not in overview_block


def test_residential_mix_tab_calls_the_dedicated_renderer():
    source = Path("app/ui/site_profile_view.py").read_text(encoding="utf-8")
    mix_block = source[source.index("with tab_mix:"):source.index("with tab_visual:")]
    assert "_render_residential_mix(view[\"residential_mix\"])" in mix_block


def test_residential_mix_never_makes_policy_market_viability_or_permission_claims():
    """Scope restriction: Residential Mix Intelligence must never assess
    policy compliance, market fit, viability or planning likelihood -
    scanned across both the pure module and its rendering."""
    module_source = Path("app/reporting/residential_mix.py").read_text(encoding="utf-8")
    view_source = Path("app/ui/site_profile_view.py").read_text(encoding="utf-8")
    banned = ["policy compliant", "policy-compliant", "viable", "market demand", "likely to be granted", "chance of approval"]
    for phrase in banned:
        assert phrase not in module_source.lower()
        assert phrase not in view_source.lower()


def test_explore_inline_scheme_detail_is_unchanged_by_this_sprint():
    """Scope restriction check: Explore's own inline row-expansion still
    calls the OLD render_scheme_detail, never the new flagship renderer -
    per this sprint's explicit "do not redesign Explore"."""
    source = Path("app/ui/pages/0_Explore.py").read_text(encoding="utf-8")
    assert "render_scheme_detail(" in source
    assert "render_site_profile(" not in source


def test_scheme_detail_page_uses_the_new_flagship_renderer():
    source = Path("app/ui/pages/1_Scheme_Detail.py").read_text(encoding="utf-8")
    assert "render_site_profile(session, settings, site, apps)" in source


def test_local_plan_sites_council_query_param_fails_safe_on_invalid_value():
    """Sprint 4.5 ("Allocation Discovery") rebuilt this page around a
    multiselect filter rather than the single-select dropdown this test was
    originally written against - an invalid/unknown council code still
    fails safe (the multiselect simply pre-selects nothing, which the new
    page's filter logic already treats as "no council constraint", i.e.
    every allocation shown - never an error, never crashing on a bad
    value), it just no longer needs to fall back to explicitly listing
    every council code by name to achieve that."""
    source = Path("app/ui/pages/3_Local_Plan_Sites.py").read_text(encoding="utf-8")
    assert '_council_param in all_council_codes' in source
    assert "_default_councils = [_council_param] if _council_param in all_council_codes else []" in source


def test_council_intelligence_detail_links_to_local_plan_sites_with_council_filter():
    source = Path("app/ui/pages/6_Council_Intelligence_Detail.py").read_text(encoding="utf-8")
    assert 'query_params={"council": detail["council_code"]}' in source


def test_no_ai_calls_in_site_profile_view():
    source = Path("app/ui/site_profile_view.py").read_text(encoding="utf-8")
    assert "openai" not in source.lower()
    assert "OpenAI(" not in source
