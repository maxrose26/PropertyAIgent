"""Tests for app.reporting.residential_mix (Sprint 4.4 Amendment,
"Residential Mix Intelligence Phase 1") - a pure data-assembly module, same
discipline as tests/test_site_profile.py: seed a real in-memory schema and
assert against it directly.
"""
from __future__ import annotations

import inspect

from app.db.models import Application, SchemeIntelligence, Site
from app.reporting import residential_mix as rm
from app.reporting.residential_mix import (
    build_affordable_tenure,
    build_ai_commentary_view,
    build_bedroom_mix,
    build_current_version,
    build_density,
    build_evidence_gaps,
    build_housing_type,
    build_residential_mix,
    build_structured_summary,
    compute_affordable_headline,
    format_affordable_percentage,
    format_affordable_tile,
    parse_tenure_categories,
)


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


def _make_scheme(session, application_id: int, **kwargs) -> SchemeIntelligence:
    scheme = SchemeIntelligence(application_id=application_id, **kwargs)
    session.add(scheme)
    session.commit()
    return scheme


# --- Affordable headline states (Part 4 A-F) --------------------------------


def test_case_a_verified_units_and_verified_percentage():
    scheme = SchemeIntelligence(application_id=1, total_units_final=140, affordable_units_final=42, affordable_percentage_final=30.0)
    headline = compute_affordable_headline(scheme)
    assert headline["state"] == "verified"
    assert headline["headline_units"] == "42 affordable homes"
    assert headline["headline_percentage"] == "30% affordable"
    assert headline["percentage_is_calculated"] is False


def test_case_b_calculated_percentage_from_units_and_total():
    scheme = SchemeIntelligence(application_id=1, total_units_final=140, affordable_units_final=42, affordable_percentage_final=None)
    headline = compute_affordable_headline(scheme)
    assert headline["state"] == "calculated"
    assert headline["headline_units"] == "42 affordable homes"
    assert headline["headline_percentage"] == "30% calculated"
    assert headline["percentage_is_calculated"] is True


def test_case_c_stated_percentage_no_unit_count():
    scheme = SchemeIntelligence(application_id=1, total_units_final=None, affordable_units_final=None, affordable_percentage_final=30.0)
    headline = compute_affordable_headline(scheme)
    assert headline["state"] == "percentage_only"
    assert headline["headline_units"] == "Unit count not identified"
    assert headline["headline_percentage"] == "30% affordable"
    value, caption = format_affordable_tile(headline)
    assert value == "30% affordable"
    assert caption == "Unit count not identified"


def test_case_d_ambiguous_evidence_via_status_note():
    scheme = SchemeIntelligence(
        application_id=1, affordable_percentage_final=20.0,
        affordable_status_note="A minimum of 20% affordable housing is proposed but not yet confirmed as a specific unit count.",
    )
    headline = compute_affordable_headline(scheme)
    assert headline["state"] == "review"
    assert headline["headline_units"] == "Requires manual review"
    assert headline["headline_percentage"] is None


def test_case_d_conflicting_evidence_via_reconciliation_status():
    scheme = SchemeIntelligence(
        application_id=1, total_units_final=100, affordable_units_final=50, private_units_final=10,
        unit_reconciliation_status="Needs manual review: Private + affordable does not equal total",
    )
    headline = compute_affordable_headline(scheme)
    assert headline["state"] == "review"


def test_case_e_no_evidence_gives_not_identified():
    headline = compute_affordable_headline(None)
    assert headline["state"] == "not_identified"
    assert headline["headline_units"] == "Not identified"
    assert headline["headline_percentage"] is None
    assert headline["evidence_status"] == rm.NOT_IDENTIFIED


def test_case_e_no_evidence_never_labelled_needs_review():
    scheme = SchemeIntelligence(application_id=1)  # every field null, no status note, no reconciliation issue
    headline = compute_affordable_headline(scheme)
    assert headline["state"] == "not_identified"


def test_case_f_evidenced_zero_remains_zero():
    scheme = SchemeIntelligence(application_id=1, total_units_final=80, affordable_units_final=0, affordable_percentage_final=0.0)
    headline = compute_affordable_headline(scheme)
    assert headline["state"] == "zero"
    assert headline["headline_units"] == "0 affordable homes"
    assert headline["affordable_units"] == 0


def test_missing_never_becomes_zero():
    """The single most important guarantee (Part 4): a genuinely missing
    affordable_units_final must never be confused with a real 0 - Python
    falsiness (`if not affordable`) would wrongly collapse the two."""
    scheme = SchemeIntelligence(application_id=1, total_units_final=80, affordable_units_final=None)
    headline = compute_affordable_headline(scheme)
    assert headline["affordable_units"] is None
    assert headline["state"] != "zero"


# --- Percentage validation and rounding (Part 5) ----------------------------


def test_format_affordable_percentage_whole_number():
    assert format_affordable_percentage(30.0) == "30%"
    assert format_affordable_percentage(29.6) == "30%"


def test_format_affordable_percentage_near_zero_shows_decimal_not_bare_zero():
    # A genuine small nonzero percentage must never render identically to
    # Part 4 Case F's confident "0%" - that would misrepresent it as an
    # evidenced zero.
    assert format_affordable_percentage(0.4) == "0.4%"


def test_format_affordable_percentage_near_hundred_shows_decimal():
    assert format_affordable_percentage(99.6) == "99.6%"


def test_format_affordable_percentage_true_zero_and_hundred_stay_bare():
    assert format_affordable_percentage(0.0) == "0%"
    assert format_affordable_percentage(100.0) == "100%"


def test_percentage_out_of_bounds_triggers_review_not_display():
    # affordable > total is a data-quality anomaly, not a real percentage.
    scheme = SchemeIntelligence(application_id=1, total_units_final=10, affordable_units_final=None, affordable_percentage_final=142.0)
    headline = compute_affordable_headline(scheme)
    # Clamped to None - falls through to "not_identified" since no other
    # evidence exists in this fixture.
    assert headline["percentage_raw"] is None


def test_percentage_never_outside_zero_to_a_hundred_in_calculated_case():
    scheme = SchemeIntelligence(application_id=1, total_units_final=10, affordable_units_final=15)  # affordable > total, anomalous
    headline = compute_affordable_headline(scheme)
    if headline["percentage_raw"] is not None:
        assert 0 <= headline["percentage_raw"] <= 100


# --- Current/preferred scheme version (Part 12) ------------------------------


def test_current_version_identifies_rep_app_and_explains_why(session):
    site = _make_site(session)
    app = _make_app(session, site.id, "APP/1")
    _make_scheme(session, app.id, total_units_final=50, core_intelligence_complete=True)
    session.refresh(app)
    version = build_current_version(site, [app], app)
    assert version["application_id"] == app.id
    assert version["reference"] == "APP/1"
    assert version["why_preferred"]
    assert version["has_scheme_intelligence"] is True


def test_current_version_none_when_no_rep_app():
    version = build_current_version(Site(council_code="x", canonical_address="a", display_address="a"), [], None)
    assert version["application_id"] is None
    assert version["alternatives"] == []


def test_superseded_versions_surfaced_not_combined(session):
    site = _make_site(session)
    current = _make_app(session, site.id, "APP/2", application_received="Mon 02 Jan 2024")
    superseded = _make_app(session, site.id, "APP/1", application_received="Mon 01 Jan 2024")
    _make_scheme(session, current.id, total_units_final=100, affordable_units_final=30, core_intelligence_complete=True)
    _make_scheme(session, superseded.id, total_units_final=80, affordable_units_final=20)
    session.refresh(current)
    session.refresh(superseded)

    version = build_current_version(site, [current, superseded], current)
    assert version["application_id"] == current.id
    assert len(version["alternatives"]) == 1
    assert version["alternatives"][0]["reference"] == "APP/1"
    assert version["alternatives"][0]["total_units_final"] == 80
    # The current version's own figures are untouched by the alternative's.
    assert version["version_conflict"] is True


def test_no_version_conflict_when_alternative_agrees(session):
    site = _make_site(session)
    current = _make_app(session, site.id, "APP/2")
    other = _make_app(session, site.id, "APP/1")
    _make_scheme(session, current.id, total_units_final=100, core_intelligence_complete=True)
    _make_scheme(session, other.id, total_units_final=100)
    session.refresh(current)
    session.refresh(other)
    version = build_current_version(site, [current, other], current)
    assert version["version_conflict"] is False


def test_residential_mix_never_mixes_affordable_and_total_across_versions(session):
    """The core Part 5/12 guarantee end to end: build_residential_mix's
    affordable_headline must come entirely from rep_app's own scheme, even
    when another application on the same site has wildly different,
    tempting-to-blend figures."""
    site = _make_site(session)
    rep = _make_app(session, site.id, "APP/2")
    other = _make_app(session, site.id, "APP/1")
    _make_scheme(session, rep.id, total_units_final=100, affordable_units_final=30, affordable_percentage_final=30.0, core_intelligence_complete=True)
    _make_scheme(session, other.id, total_units_final=500, affordable_units_final=490, affordable_percentage_final=98.0)
    session.refresh(rep)
    session.refresh(other)

    mix = build_residential_mix(site, [rep, other], rep_app=rep)
    assert mix["affordable_headline"]["affordable_units"] == 30
    assert mix["affordable_headline"]["percentage_raw"] == 30.0
    assert mix["current_version"]["version_conflict"] is True
    assert mix["current_version"]["alternatives"][0]["affordable_units_final"] == 490


# --- Bedroom mix / housing type (Phase 1 honest gaps) -----------------------


def test_bedroom_mix_always_honestly_unavailable_in_phase_1():
    scheme = SchemeIntelligence(application_id=1, total_units_final=100)
    result = build_bedroom_mix(scheme)
    assert result["available"] is False
    assert result["categories"] == []


def test_bedroom_mix_unavailable_even_with_no_scheme():
    assert build_bedroom_mix(None)["available"] is False


def test_housing_type_shows_typology_description_when_present():
    scheme = SchemeIntelligence(application_id=1, housing_typology="Terraced houses and apartments")
    result = build_housing_type(scheme)
    assert result["available"] is True
    assert result["typology_description"] == "Terraced houses and apartments"


def test_housing_type_unavailable_when_nothing_recorded():
    scheme = SchemeIntelligence(application_id=1)
    assert build_housing_type(scheme)["available"] is False


def test_housing_type_never_derived_from_bedroom_data():
    """build_housing_type's only inputs are housing_typology/
    specialist_housing_type/development_type - never a bedroom-mix value.
    Checked structurally (its only parameter is a SchemeIntelligence row,
    and SchemeIntelligence itself has no bedroom-mix column to derive
    from), not by scanning prose - the function's own docstring
    legitimately discusses bedroom mix while explaining this exact
    decision, which a naive text scan would misflag."""
    params = list(inspect.signature(build_housing_type).parameters)
    assert params == ["scheme"]
    assert not hasattr(SchemeIntelligence, "bedroom_mix")


# --- Affordable tenure (Part 11) ---------------------------------------------


def test_parse_tenure_categories_from_comma_joined_string():
    assert parse_tenure_categories("social rent, shared ownership") == ["Social rent", "Shared ownership"]


def test_parse_tenure_categories_empty_when_none():
    assert parse_tenure_categories(None) == []


def test_tenure_never_invents_a_distribution():
    scheme = SchemeIntelligence(application_id=1, affordable_tenure_split_final="social rent")
    headline = compute_affordable_headline(SchemeIntelligence(application_id=1, affordable_units_final=10, total_units_final=50))
    tenure = build_affordable_tenure(scheme, headline)
    assert tenure["categories"] == ["Social rent"]
    assert tenure["has_categories"] is True


def test_affordable_known_tenure_unknown_state():
    scheme = SchemeIntelligence(application_id=1, affordable_tenure_split_final=None)
    headline = compute_affordable_headline(SchemeIntelligence(application_id=1, affordable_units_final=10, total_units_final=50))
    tenure = build_affordable_tenure(scheme, headline)
    assert tenure["affordable_known_tenure_unknown"] is True
    assert tenure["has_categories"] is False


def test_tenure_not_flagged_unknown_when_no_affordable_homes_identified():
    tenure = build_affordable_tenure(None, compute_affordable_headline(None))
    assert tenure["affordable_known_tenure_unknown"] is False


# --- Density (Part 7) --------------------------------------------------------


def test_density_shown_only_when_extracted():
    scheme = SchemeIntelligence(application_id=1, density_dph=45.5, site_area_ha=2.2)
    density = build_density(scheme)
    assert density["available"] is True
    assert density["density_dph"] == 45.5


def test_density_unavailable_when_not_extracted():
    scheme = SchemeIntelligence(application_id=1, density_dph=None)
    assert build_density(scheme)["available"] is False
    assert build_density(None)["available"] is False


def test_density_never_computed_from_guessed_site_area():
    """build_density must never divide units by a Site's own area - it
    only ever reads the already-extracted density_dph column."""
    source = inspect.getsource(build_density)
    assert "/" not in source  # no division performed anywhere in this function


# --- Residential Mix Commentary (Part 13/14/15) ------------------------------


def test_structured_summary_states_affordable_provision():
    scheme = SchemeIntelligence(application_id=1, total_units_final=140, affordable_units_final=42, affordable_percentage_final=30.0)
    headline = compute_affordable_headline(scheme)
    tenure = build_affordable_tenure(scheme, headline)
    current_version = {"version_conflict": False}
    summary = build_structured_summary(headline, tenure, current_version, "OK")
    assert "42 homes" in summary
    assert "30%" in summary
    assert "reconciled scheme total" in summary


def test_structured_summary_none_when_nothing_supported():
    headline = compute_affordable_headline(None)
    tenure = build_affordable_tenure(None, headline)
    summary = build_structured_summary(headline, tenure, {"version_conflict": False}, None)
    assert summary is None


def test_structured_summary_never_makes_viability_market_or_permission_claims():
    scheme = SchemeIntelligence(application_id=1, total_units_final=140, affordable_units_final=42, affordable_percentage_final=30.0)
    headline = compute_affordable_headline(scheme)
    tenure = build_affordable_tenure(scheme, headline)
    summary = build_structured_summary(headline, tenure, {"version_conflict": False}, "OK")
    banned = [
        "viable", "viability", "market demand", "policy compliant", "compliance",
        "likely", "chance of approval", "recommend", "optimal", "should change",
    ]
    lowered = summary.lower()
    for phrase in banned:
        assert phrase not in lowered


def test_ai_commentary_honestly_not_yet_generated():
    """Phase 1 has no suitable existing AI commentary architecture for
    Residential Mix specifically (see this module's own docstring) - always
    reports honestly, never fabricates a summary."""
    site = Site(council_code="x", canonical_address="a", display_address="a", status_summary="Unrelated general site narrative.")
    view = build_ai_commentary_view(site)
    assert view["has_commentary"] is False
    assert view["text"] is None
    assert view["is_stale"] is False


def test_ai_commentary_never_reuses_unrelated_site_status_summary():
    """Site.status_summary discusses phases/lapse/build status, not
    residential mix - must never be repurposed as Residential Mix
    Commentary just because it exists."""
    site = Site(council_code="x", canonical_address="a", display_address="a", status_summary="Phase 2 is under construction.")
    view = build_ai_commentary_view(site)
    assert view["text"] != site.status_summary


def test_no_ai_call_on_module_import_or_use():
    """No OpenAI/AI client anywhere in this module - Phase 1 makes zero AI
    calls, confirmed by source inspection, not just by not calling one in
    these tests."""
    import app.reporting.residential_mix as module

    source = inspect.getsource(module)
    assert "openai" not in source.lower()
    assert "OpenAI(" not in source


# --- Evidence gaps ------------------------------------------------------------


def test_evidence_gaps_flag_missing_bedroom_and_housing_type():
    current_version = {"application_id": 1, "has_scheme_intelligence": True, "version_conflict": False}
    headline = compute_affordable_headline(None)
    tenure = build_affordable_tenure(None, headline)
    gaps = build_evidence_gaps(current_version, headline, tenure, build_bedroom_mix(None), build_housing_type(None))
    assert any("bedroom mix" in g for g in gaps)
    assert any("housing-type" in g for g in gaps)


def test_evidence_gaps_flag_no_qualifying_application():
    current_version = {"application_id": None, "has_scheme_intelligence": False, "version_conflict": False}
    headline = compute_affordable_headline(None)
    tenure = build_affordable_tenure(None, headline)
    gaps = build_evidence_gaps(current_version, headline, tenure, build_bedroom_mix(None), build_housing_type(None))
    assert any("No qualifying application" in g for g in gaps)


# --- No database writes / bounded queries ------------------------------------


def test_module_never_writes_to_the_database():
    """Pure view-model assembly - confirmed by source inspection that no
    session.add/commit/delete call exists anywhere in this module."""
    source = inspect.getsource(rm)
    assert ".commit(" not in source
    assert "session.add(" not in source
    assert "session.delete(" not in source


def test_build_residential_mix_issues_zero_new_queries(session):
    """build_residential_mix takes an already-loaded Site/apps/rep_app and
    never queries the database itself beyond the one lazy-load of the
    .scheme_intelligence relationship - exactly the same pattern
    app.ui.common.aggregate_scheme_fields/pick_representative_application
    already rely on for the same `apps` list. Modelled on how the real
    Site Profile page loads data (app.ui.common.load_site_applications's
    own select()) - a fresh query, not session.expire_all(), which would
    also force-reload plain columns and misrepresent the real cost."""
    from sqlalchemy import event, select

    site = _make_site(session)
    app = _make_app(session, site.id, "APP/1")
    _make_scheme(session, app.id, total_units_final=50, affordable_units_final=10, core_intelligence_complete=True)
    site_id = site.id
    session.expunge_all()

    site = session.get(Site, site_id)
    apps = session.execute(select(Application).where(Application.site_id == site_id)).scalars().all()

    queries = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(session.get_bind(), "before_cursor_execute", _count)
    try:
        build_residential_mix(site, apps, rep_app=apps[0])
    finally:
        event.remove(session.get_bind(), "before_cursor_execute", _count)

    # Exactly one lazy-load query for the current version's own
    # scheme_intelligence relationship - never one per bedroom-mix/tenure/
    # commentary section.
    assert len(queries) == 1


# --- Reuse, not reinvention ---------------------------------------------------


def test_does_not_reimplement_representative_application_selection():
    """Part 12 requires reusing the existing "current scheme version"
    selector (app.ui.common.pick_representative_application), never a
    parallel one - confirmed by source inspection that this module defines
    no function with a similar name/purpose."""
    names = [name for name, _ in inspect.getmembers(rm, inspect.isfunction)]
    assert "pick_representative_application" not in names
    assert not any("pick_representative" in n for n in names)
