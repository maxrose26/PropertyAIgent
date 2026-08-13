"""Site Summary affordable-housing scope aggregation
(app.reporting.affordable_housing_scope) - focused tests for:

1. Site 519 production regression: a technical/condition child application
   (0% / 0 / unknown) must never suppress a credible positive
   affordable-housing position evidenced by a sibling application.
2. Different scopes (whole-site vs named phase/plot) coexist rather than
   being treated as conflicting values.
3. Genuine same-scope conflicts (two credible, equally-authoritative,
   disagreeing positions for the SAME scope) are surfaced, never silently
   resolved.
4. Affordable positions remain coherent records - percentage/units/tenure/
   status/notes always read together from ONE application, never mixed
   across applications.
5. Legal-security status stays scoped - a phase's legally_secured status
   never implies the whole site is, and vice versa.
6. app.reporting.scheme_summary.build_summary_prompt receives the new
   structured, scope-aware facts, and non-affordable-housing prompt
   sections are unaffected.

Uses the same in-memory-SQLite `session` fixture as the rest of this suite
(tests/conftest.py). No OpenAI call anywhere.
"""
from __future__ import annotations

from app.db.models import Application, SchemeIntelligence, Site
from app.pipeline.lapse_tracking import compute_lapse_status
from app.pipeline.phase_tracking import build_phase_breakdown
from app.reporting.affordable_housing_scope import (
    SCOPE_PHASE,
    SCOPE_PLOT,
    SCOPE_UNCLEAR,
    SCOPE_WHOLE_SITE,
    compute_affordable_housing_scope_summary,
    format_affordable_housing_lines,
)
from app.reporting.scheme_summary import build_summary_prompt
from app.ui.common import aggregate_scheme_fields


def _make_site(session, **kwargs) -> Site:
    site = Site(council_code="testcouncil", canonical_address="Land south of Churchill Way", display_address="Land South of Churchill Way, Pendleton", **kwargs)
    session.add(site)
    session.commit()
    return site


def _make_app(session, site_id: int, reference: str, **kwargs) -> Application:
    kwargs.setdefault("application_received", "Mon 01 Jan 2024")
    app = Application(council_code="testcouncil", reference=reference, site_id=site_id, **kwargs)
    session.add(app)
    session.commit()
    return app


def _make_intel(session, app: Application, **kwargs) -> SchemeIntelligence:
    intel = SchemeIntelligence(application_id=app.id, **kwargs)
    session.add(intel)
    session.commit()
    return intel


# --- 1/2. Site 519 production regression ------------------------------------


def test_site_519_regression_positive_position_not_collapsed_to_zero(session):
    site = _make_site(session)
    app_1204 = _make_app(session, site.id, "OTH/2025/1786", proposal="Reserved matters application for residential development")
    _make_intel(
        session, app_1204,
        affordable_percentage_final=20.0, affordable_units_final=97,
        affordable_tenure_split_final="Affordable Rent, Shared Ownership",
        affordable_housing_status="conditioned",
        affordable_housing_notes="Condition 15 concerning affordable housing has not yet been fully discharged.",
    )
    app_1208 = _make_app(session, site.id, "OTH/2025/1790", proposal="Discharge of condition 22 (contamination remediation)")
    _make_intel(session, app_1208, affordable_percentage_final=0, affordable_units_final=0, affordable_housing_status="unknown")

    summary = compute_affordable_housing_scope_summary([app_1204, app_1208])

    assert summary.whole_site is not None
    assert summary.whole_site.percentage == 20.0
    assert summary.whole_site.units == 97
    assert summary.whole_site.application_reference == "OTH/2025/1786"
    assert summary.conflicts == ()


def test_technical_zero_application_does_not_suppress_positive_position(session):
    site = _make_site(session)
    positive = _make_app(session, site.id, "APP/POS")
    _make_intel(session, positive, affordable_percentage_final=20.0, affordable_units_final=97, affordable_housing_status="conditioned")
    technical = _make_app(session, site.id, "APP/TECH")
    _make_intel(session, technical, affordable_percentage_final=0, affordable_units_final=0, affordable_housing_status="unknown")

    summary = compute_affordable_housing_scope_summary([positive, technical])

    assert summary.whole_site is not None
    assert summary.whole_site.application_reference == "APP/POS"
    assert summary.whole_site.percentage == 20.0


# --- 3. Explicit phase-level zero is preserved -------------------------------


def test_explicit_phase_level_zero_is_preserved(session):
    site = _make_site(session)
    outline = _make_app(session, site.id, "APP/OUTLINE", proposal="Outline application for up to 400 dwellings")
    _make_intel(session, outline, affordable_percentage_final=50.0, affordable_units_final=200, affordable_housing_status="agreed")
    phase2 = _make_app(session, site.id, "APP/PHASE2", proposal="Reserved matters application for Phase 2")
    _make_intel(
        session, phase2, affordable_percentage_final=0, affordable_units_final=0, affordable_housing_status="agreed",
        affordable_housing_notes="No affordable housing is provided within Phase 2.",
    )
    # A second named phase so build_phase_breakdown treats this as genuinely
    # multi-phase (matches Part 14's own fixture shape).
    phase1 = _make_app(session, site.id, "APP/PHASE1", proposal="Reserved matters application for Phase 1")
    _make_intel(session, phase1, affordable_percentage_final=100.0, affordable_units_final=200, affordable_housing_status="agreed")

    summary = compute_affordable_housing_scope_summary([outline, phase1, phase2])

    phase2_position = next(p for p in summary.phases if p.scope_label == "Phase 2")
    assert phase2_position.percentage == 0
    assert phase2_position.units == 0
    assert phase2_position.notes == "No affordable housing is provided within Phase 2."


# --- 4/5. Whole site + phase positions coexist, no false conflict -----------


def test_whole_site_and_phase_positions_coexist_without_false_conflict(session):
    site = _make_site(session)
    whole = _make_app(session, site.id, "APP/OUTLINE", proposal="Outline permission for up to 1000 dwellings")
    _make_intel(session, whole, affordable_percentage_final=50.0, affordable_units_final=500, affordable_housing_status="agreed")
    phase1 = _make_app(session, site.id, "APP/PHASE1", proposal="Reserved matters application for Phase 1")
    _make_intel(session, phase1, affordable_percentage_final=100.0, affordable_units_final=200, affordable_housing_status="agreed")
    phase2 = _make_app(session, site.id, "APP/PHASE2", proposal="Reserved matters application for Phase 2")
    _make_intel(
        session, phase2, affordable_percentage_final=0, affordable_units_final=0, affordable_housing_status="agreed",
        affordable_housing_notes="No affordable housing is provided within Phase 2.",
    )

    summary = compute_affordable_housing_scope_summary([whole, phase1, phase2])

    assert summary.whole_site.scope_type == SCOPE_WHOLE_SITE
    assert summary.whole_site.percentage == 50.0
    assert summary.whole_site.units == 500
    labels = {p.scope_label: p for p in summary.phases}
    assert labels["Phase 1"].percentage == 100.0
    assert labels["Phase 2"].percentage == 0
    assert summary.conflicts == ()  # differing scopes are not conflicting evidence


# --- 6/7. Same-scope conflict vs authoritative supersession ------------------


def test_same_scope_conflicting_values_flagged_not_silently_resolved(session):
    site = _make_site(session)
    a = _make_app(session, site.id, "APP/DECISION")
    _make_intel(session, a, affordable_percentage_final=35.0, affordable_units_final=350, affordable_housing_status="conditioned")
    b = _make_app(session, site.id, "APP/S106")
    _make_intel(session, b, affordable_percentage_final=20.0, affordable_units_final=200, affordable_housing_status="conditioned")

    summary = compute_affordable_housing_scope_summary([a, b])

    assert summary.whole_site is None
    assert len(summary.conflicts) == 1
    conflict = summary.conflicts[0]
    percentages = {p.percentage for p in conflict.positions}
    assert percentages == {35.0, 20.0}


def test_higher_authority_status_supersedes_without_flagging_conflict(session):
    site = _make_site(session)
    proposed = _make_app(session, site.id, "APP/PROPOSED")
    _make_intel(session, proposed, affordable_percentage_final=35.0, affordable_units_final=350, affordable_housing_status="proposed")
    secured = _make_app(session, site.id, "APP/S106")
    _make_intel(session, secured, affordable_percentage_final=20.0, affordable_units_final=200, affordable_housing_status="legally_secured")

    summary = compute_affordable_housing_scope_summary([proposed, secured])

    assert summary.conflicts == ()
    assert summary.whole_site is not None
    assert summary.whole_site.percentage == 20.0
    assert summary.whole_site.status == "legally_secured"
    assert summary.whole_site.application_reference == "APP/S106"


# --- 8. Coherent record - no cross-application field mixing -----------------


def test_position_fields_are_never_mixed_across_applications(session):
    site = _make_site(session)
    winner = _make_app(session, site.id, "APP/WINNER", application_received="Mon 01 Jan 2025")
    _make_intel(
        session, winner, affordable_percentage_final=30.0, affordable_units_final=90,
        affordable_tenure_split_final="Social Rent 70 / Shared Ownership 30", affordable_housing_status="legally_secured",
        affordable_housing_notes="Executed S106 secures 30% affordable housing.",
    )
    other = _make_app(session, site.id, "APP/OTHER", application_received="Mon 01 Jan 2020")
    _make_intel(
        session, other, affordable_percentage_final=30.0, affordable_units_final=90,
        affordable_tenure_split_final="Affordable Rent only", affordable_housing_status="proposed",
        affordable_housing_notes="An earlier proposal suggested a different tenure mix.",
    )

    summary = compute_affordable_housing_scope_summary([winner, other])

    # Same percentage -> no conflict path; the winner (more complete/recent)
    # is picked whole, never a blend of winner's percentage with other's tenure.
    assert summary.whole_site.application_id == winner.id
    assert summary.whole_site.tenure == "Social Rent 70 / Shared Ownership 30"
    assert summary.whole_site.notes == "Executed S106 secures 30% affordable housing."
    assert summary.whole_site.status == "legally_secured"


# --- 9/10. Legal-security status stays scoped --------------------------------


def test_phase_legally_secured_does_not_imply_whole_site_secured(session):
    site = _make_site(session)
    whole = _make_app(session, site.id, "APP/OUTLINE", proposal="Outline permission for up to 400 dwellings")
    _make_intel(session, whole, affordable_percentage_final=50.0, affordable_units_final=200, affordable_housing_status="conditioned")
    phase1 = _make_app(session, site.id, "APP/PHASE1", proposal="Reserved matters application for Phase 1")
    _make_intel(session, phase1, affordable_percentage_final=100.0, affordable_units_final=200, affordable_housing_status="legally_secured")
    phase2 = _make_app(session, site.id, "APP/PHASE2", proposal="Reserved matters application for Phase 2")
    _make_intel(session, phase2, affordable_percentage_final=0, affordable_units_final=0, affordable_housing_status="agreed", affordable_housing_notes="No affordable housing in Phase 2.")

    summary = compute_affordable_housing_scope_summary([whole, phase1, phase2])

    assert summary.whole_site.status == "conditioned"
    phase1_position = next(p for p in summary.phases if p.scope_label == "Phase 1")
    assert phase1_position.status == "legally_secured"


# --- 11. Genuine whole-site explicit zero (no phases) ------------------------


def test_single_application_explicit_zero_still_reported_correctly(session):
    site = _make_site(session)
    app = _make_app(session, site.id, "APP/NOAFFORDABLE")
    _make_intel(
        session, app, affordable_percentage_final=0, affordable_units_final=0, affordable_housing_status="policy_required",
        affordable_housing_notes="Policy assessment confirms no affordable housing is required for this scheme.",
    )

    summary = compute_affordable_housing_scope_summary([app])

    assert summary.whole_site is not None
    assert summary.whole_site.percentage == 0
    assert summary.whole_site.units == 0
    assert summary.whole_site.status == "policy_required"


def test_application_with_no_ah_evidence_at_all_yields_no_position(session):
    site = _make_site(session)
    app = _make_app(session, site.id, "APP/TECHONLY")
    _make_intel(session, app, affordable_percentage_final=0, affordable_units_final=0, affordable_housing_status="unknown")

    summary = compute_affordable_housing_scope_summary([app])

    assert summary.whole_site is None
    assert summary.phases == ()
    assert summary.conflicts == ()


# --- Plot scope distinct from phase ------------------------------------------


def test_plot_scope_type_distinct_from_phase(session):
    site = _make_site(session)
    plot_app = _make_app(session, site.id, "APP/PLOT5", proposal="Discharge of conditions for Plot 5")
    _make_intel(session, plot_app, affordable_percentage_final=0, affordable_units_final=0, affordable_housing_status="agreed", affordable_housing_notes="Plot 5 is a private market dwelling.")
    other_app = _make_app(session, site.id, "APP/OTHER", proposal="Discharge of conditions for Plot 9")
    _make_intel(session, other_app, affordable_percentage_final=100, affordable_units_final=1, affordable_housing_status="agreed")

    summary = compute_affordable_housing_scope_summary([plot_app, other_app])

    plot5 = next(p for p in summary.phases if p.scope_label == "Plot 5")
    assert plot5.scope_type == SCOPE_PLOT


# --- Prospective-override atomicity parity -----------------------------------


def test_prospective_overrides_are_reflected_not_stale_db_values(session):
    site = _make_site(session)
    app = _make_app(session, site.id, "APP/1")
    _make_intel(session, app, affordable_percentage_final=10.0, affordable_units_final=10, affordable_housing_status="proposed")

    override = {
        app.id: {
            "affordable_percentage_final": 40.0, "affordable_units_final": 40,
            "affordable_tenure_split_final": "Affordable Rent", "affordable_housing_status": "legally_secured",
            "affordable_housing_notes": "Executed S106 secures 40% affordable housing.",
        }
    }
    summary = compute_affordable_housing_scope_summary([app], prospective_overrides=override)

    assert summary.whole_site.percentage == 40.0
    assert summary.whole_site.status == "legally_secured"


# --- format_affordable_housing_lines -----------------------------------------


def test_format_lines_qualifies_unclear_scope(session):
    site = _make_site(session)
    app = _make_app(session, site.id, "OTH/2025/1786")
    _make_intel(session, app, affordable_percentage_final=20.0, affordable_units_final=97, affordable_housing_status="conditioned")

    summary = compute_affordable_housing_scope_summary([app])
    lines = format_affordable_housing_lines(summary)
    text = "\n".join(lines)

    assert "20.0%" in text or "20%" in text
    assert "97 affordable homes" in text
    assert "manual review" in text.lower()  # unclear-scope qualifier


def test_format_lines_reports_conflict_as_manual_review(session):
    site = _make_site(session)
    a = _make_app(session, site.id, "APP/A")
    _make_intel(session, a, affordable_percentage_final=35.0, affordable_units_final=350, affordable_housing_status="conditioned")
    b = _make_app(session, site.id, "APP/B")
    _make_intel(session, b, affordable_percentage_final=20.0, affordable_units_final=200, affordable_housing_status="conditioned")

    summary = compute_affordable_housing_scope_summary([a, b])
    lines = format_affordable_housing_lines(summary)
    text = "\n".join(lines)

    assert "MANUAL REVIEW RECOMMENDED" in text
    assert "CONFLICT" in text


# --- 12/13. build_summary_prompt integration ---------------------------------


def test_prompt_receives_structured_scope_aware_facts(session):
    site = _make_site(session)
    app_1204 = _make_app(session, site.id, "OTH/2025/1786", proposal="Reserved matters residential development", status="Registered", decision=None)
    _make_intel(
        session, app_1204, affordable_percentage_final=20.0, affordable_units_final=97,
        affordable_tenure_split_final="Affordable Rent, Shared Ownership", affordable_housing_status="conditioned",
        affordable_housing_notes="Condition 15 concerning affordable housing has not yet been fully discharged.",
    )
    app_1208 = _make_app(session, site.id, "OTH/2025/1790", proposal="Discharge of condition 22", status="Approve", decision="Approve")
    _make_intel(session, app_1208, affordable_percentage_final=0, affordable_units_final=0, affordable_housing_status="unknown")
    apps = [app_1204, app_1208]

    merged = aggregate_scheme_fields(apps)
    lapse = compute_lapse_status(apps, site)
    phase_breakdown = build_phase_breakdown(apps)
    prompt = build_summary_prompt(site, apps, merged, lapse, phase_breakdown)

    assert "97 affordable homes" in prompt
    assert "20.0%" in prompt
    # The old flattened tuple must never claim 0% / 0 units for this scheme.
    assert "0% / 0 units" not in prompt


def test_non_affordable_prompt_sections_unchanged(session):
    site = _make_site(session)
    app = _make_app(
        session, site.id, "APP/1", proposal="Outline application for 45 dwellings",
        status="Approve", decision="Approve", application_received="Mon 01 Jan 2024",
    )
    _make_intel(session, app, total_units_final=45, developer="Example Developer Ltd", recommendation_direction="approval")

    merged = aggregate_scheme_fields([app])
    lapse = compute_lapse_status([app], site)
    phase_breakdown = build_phase_breakdown([app])
    prompt = build_summary_prompt(site, [app], merged, lapse, phase_breakdown)

    assert "SCHEME SCOPE: 45 total units, developer Example Developer Ltd" in prompt
    assert "RECOMMENDATION DIRECTION: approval" in prompt
    assert "ALL 1 LINKED APPLICATIONS ON THIS SITE" in prompt
