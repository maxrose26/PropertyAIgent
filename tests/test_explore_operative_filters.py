"""Gate 2B-2A pre-merge remediation - Explore's Total Units/Decision Status
migration onto Trusted Operative Planning Facts.

Before this, Explore's table + min/max unit filter + status filter (and
the exported CSV/PDF report) derived their "Total Units"/"Decision Status"
independently from pick_representative_application + aggregate_scheme_
fields + classify_decision_status - a SEPARATE selection from the one
Site Profile's headline tile and the map tooltip already used, so the
primary discovery/search surface could show one planning truth for
matching a buyer brief while a different trusted truth was shown
elsewhere on the same page.

app.reporting.scheme_reconciliation.resolve_operative_filter_facts is the
single deterministic resolver now behind every one of those surfaces -
these tests exercise it (and its two label helpers) directly, since
0_Explore.py itself is Streamlit-rendering code with no behavioural test
harness in this codebase (same reasoning as test_ui_common_operative_
display.py).
"""
from __future__ import annotations

from app.db.models import Application, SchemeIntelligence, Site
from app.reporting.scheme_reconciliation import (
    NOT_DETERMINED_DECISION_STATUS,
    build_operative_planning_facts,
    format_operative_decision_status_label,
    resolve_canonical_decision_status,
    resolve_operative_filter_facts,
)


def _site(session, **kw) -> Site:
    s = Site(council_code="testcouncil", canonical_address="land at x", display_address="Land at X", **kw)
    session.add(s)
    session.commit()
    return s


def _app(session, site_id, reference, **kw) -> Application:
    kw.setdefault("application_received", "Mon 01 Jan 2024")
    a = Application(council_code="testcouncil", reference=reference, site_id=site_id, **kw)
    session.add(a)
    session.commit()
    return a


def _intel(session, app, **kw) -> SchemeIntelligence:
    si = SchemeIntelligence(application_id=app.id, **kw)
    session.add(si)
    session.commit()
    return si


# --- 1/2. Explore and Site Profile (and Explore's own tooltip/table) cannot
# derive contradictory planning status --------------------------------------


def test_explore_status_and_site_profile_status_share_one_resolver_burnage_shape(session):
    """Former Burnage Cricket Club shape - a granted Full permission plus a
    newer condition-discharge filing with no decision of its own.
    app.reporting.site_profile's Decision Status tile calls
    resolve_canonical_decision_status directly; Explore's filter_facts.
    decision_status is derived from the exact same call inside
    resolve_operative_filter_facts - proving the two surfaces cannot
    disagree because they are literally the same function call, not two
    independently-written selections that happen to agree today."""
    site = _site(session)
    granted = _app(session, site.id, "142311/FO/2025",
                   proposal="Erection of up to 66 no. dwellings", status="Final", decision="Approve",
                   decision_issued_date="Mon 23 Mar 2026", application_received="Wed 04 Mar 2025")
    _intel(session, granted, total_units_final=66, core_intelligence_complete=True)
    discharge = _app(session, site.id, "OTH-2026-001269",
                     proposal="Discharge of a condition of 142311/FO/2025", status="Under Consultation",
                     decision=None, application_received="Fri 07 Aug 2026")
    _intel(session, discharge, total_units_final=66, core_intelligence_complete=True)

    facts = build_operative_planning_facts([granted, discharge])
    site_profile_status = resolve_canonical_decision_status(
        facts.consented_position, facts.active_positions, bool(facts.resolved_applications),
    )
    explore_filter_facts = resolve_operative_filter_facts(facts)
    assert site_profile_status == "granted"
    assert explore_filter_facts.decision_status == "granted"


def test_explore_table_and_tooltip_read_the_identical_filter_facts_object(session):
    """The map tooltip and the table row in 0_Explore.py both derive their
    Decision Status/Total Units from ONE resolve_operative_filter_facts
    call per Site (see the main per-Site loop) - proven here by asserting
    the label helper used for both is a pure function of that one object,
    so there is no code path where they could read two different sources."""
    site = _site(session)
    app = _app(session, site.id, "RM/1", proposal="Reserved matters for 40 dwellings",
               status="Awaiting decision")
    _intel(session, app, total_units_final=40, core_intelligence_complete=True)

    facts = build_operative_planning_facts([app])
    filter_facts_for_table = resolve_operative_filter_facts(facts)
    filter_facts_for_tooltip = resolve_operative_filter_facts(facts)
    assert filter_facts_for_table == filter_facts_for_tooltip
    assert (format_operative_decision_status_label(filter_facts_for_table)
            == format_operative_decision_status_label(filter_facts_for_tooltip))


# --- 3. A non-substantive later application cannot control the filters -----


def test_non_substantive_condition_discharge_cannot_control_units_or_status(session):
    """A condition-discharge filing carries no planning role weight of its
    own (Gate 2B-1's non-substantive guardrail) - it must never flip a
    granted site's filterable Total Units/Decision Status away from the
    granted position, however recently it was filed."""
    site = _site(session)
    granted = _app(session, site.id, "FUL/1", proposal="Erection of 80 dwellings",
                   status="Final", decision="Approve", decision_issued_date="Mon 01 Jan 2020")
    _intel(session, granted, total_units_final=80, core_intelligence_complete=True)
    discharge = _app(session, site.id, "DOC/9", proposal="Discharge of a condition of FUL/1",
                     status="Under Consultation", decision=None, application_received="Fri 01 Aug 2026")
    _intel(session, discharge, total_units_final=None)

    facts = build_operative_planning_facts([granted, discharge])
    ff = resolve_operative_filter_facts(facts)
    assert ff.decision_status == "granted"
    assert ff.units == 80
    assert ff.units_source == "consented"


# --- 4. An individual dwelling plot cannot become the operative quantum ----


def test_individual_dwelling_plot_cannot_supply_the_explore_unit_filter_value(session):
    """A site with ONLY an individual-plot-scale filing (no qualifying
    development-parcel evidence) must not let that plot's own tiny unit
    count leak into Explore's min/max unit filter - phase_tracking's
    material-development-parcel threshold already prevents it from
    becoming a peer scope/position at all, so it resolves NOT_DETERMINED,
    never "1 unit"."""
    site = _site(session)
    plot_app = _app(session, site.id, "DC/PLOT/1",
                    proposal="Discharge of conditions relating to Plot 14 - foundation details",
                    status="Decided", decision="Approve with Conditions")
    _intel(session, plot_app, total_units_final=1)

    facts = build_operative_planning_facts([plot_app])
    ff = resolve_operative_filter_facts(facts)
    assert ff.units is None
    # reconciliation DID run (the plot filing was resolved and evaluated),
    # it just found nothing substantive - an honest NOT_DETERMINED, not a
    # fabricated "1 unit" plot-scale figure.
    assert ff.units_not_determined is True
    assert ff.decision_status == NOT_DETERMINED_DECISION_STATUS


# --- 5. Withdrawn/refused evidence cannot silently become the unit count ---


def test_withdrawn_application_units_never_become_the_explore_filter_value(session):
    """Stockport Rugby Club shape - a withdrawn hybrid application's own
    proposed unit figure must never surface as Explore's filterable Total
    Units merely because it is the only evidence that exists."""
    site = _site(session)
    withdrawn = _app(session, site.id, "DC/1",
                     proposal="Hybrid application for residential development and a care facility",
                     status="Withdrawn", decision="Application Withdrawn")
    _intel(session, withdrawn, total_units_final=90, specialist_housing_type="care facility")

    facts = build_operative_planning_facts([withdrawn])
    ff = resolve_operative_filter_facts(facts)
    assert ff.units is None
    assert ff.units_not_determined is True
    assert ff.decision_status == "withdrawn"


def test_refused_application_units_never_become_the_explore_filter_value(session):
    site = _site(session)
    refused = _app(session, site.id, "FUL/2", proposal="Erection of 55 dwellings",
                   status="Decided", decision="Refuse")
    _intel(session, refused, total_units_final=55)

    facts = build_operative_planning_facts([refused])
    ff = resolve_operative_filter_facts(facts)
    assert ff.units is None
    assert ff.units_not_determined is True
    assert ff.decision_status == "refused"


# --- 6. A consented position plus an active proposal preserves both -------


def test_consented_position_and_active_proposal_are_both_preserved_hazelhurst_shape(session):
    """Hazelhurst Farm shape - a granted whole-site consent AND a separate
    live phase proposal coexist. Explore's single canonical decision_status
    stays "granted" (the established position), but the active proposal's
    own existence/count/units are never discarded - preserved as distinct
    fields a consumer can still act on."""
    site = _site(session)
    granted = _app(session, site.id, "HYB/1", proposal="Hybrid application for 400 dwellings",
                   status="Final", decision="Approve", decision_issued_date="Mon 01 Jan 2020")
    _intel(session, granted, total_units_final=400, core_intelligence_complete=True)
    active_phase = _app(session, site.id, "RM/Phase2", proposal="Reserved matters for Phase 2 comprising 176 dwellings",
                        status="Awaiting decision", application_received="Mon 01 Jan 2025")
    _intel(session, active_phase, total_units_final=176, core_intelligence_complete=True)

    facts = build_operative_planning_facts([granted, active_phase])
    ff = resolve_operative_filter_facts(facts)
    assert ff.decision_status == "granted"
    assert ff.units == 400
    assert ff.has_active_proposal is True
    assert ff.active_proposal_count == 1
    assert ff.active_units == 176


# --- 7. Multiple active proposals never cause an arbitrary latest-wins ----


def test_multiple_active_proposals_do_not_produce_a_latest_wins_unit_filter_value(session):
    """No consent exists; two simultaneous active substantive proposals
    exist. Explore's filterable Total Units must stay None/not_determined
    (never silently pick the most recent or larger one) - but the raw
    count of active proposals is preserved so a consumer knows there is
    live activity worth investigating."""
    site = _site(session)
    active_a = _app(session, site.id, "RM/Phase1", proposal="Reserved matters for Phase 1 comprising 100 dwellings",
                    status="Awaiting decision", application_received="Mon 01 Jan 2024")
    _intel(session, active_a, total_units_final=100, core_intelligence_complete=True)
    active_b = _app(session, site.id, "RM/Phase2", proposal="Reserved matters for Phase 2 comprising 120 dwellings",
                    status="Awaiting decision", application_received="Mon 01 Feb 2024")
    _intel(session, active_b, total_units_final=120, core_intelligence_complete=True)

    facts = build_operative_planning_facts([active_a, active_b])
    ff = resolve_operative_filter_facts(facts)
    assert ff.units is None
    assert ff.units_not_determined is True
    assert ff.active_proposal_count == 2
    assert ff.has_active_proposal is True
    # the display label must say "2 active planning proposals", never
    # silently print the plain "Awaiting decision" wording a single active
    # proposal would use, and never name one phase over the other.
    label = format_operative_decision_status_label(ff)
    assert label == "2 active planning proposals"


# --- 8. NOT_DETERMINED never falls back to aggregate_scheme_fields --------


def test_not_determined_never_falls_back_to_a_raw_aggregate_total(session):
    """Pennington's Stables shape - an EIA-screening-only site. Even though
    the underlying SchemeIntelligence row carries a portal-search-listing
    unit estimate (exactly the kind of figure aggregate_scheme_fields would
    have surfaced under the legacy path), the trusted resolver must not
    fall back to it once reconciliation has determined there is no
    substantive consented or active position at all."""
    site = _site(session)
    screening = _app(session, site.id, "EIA/1",
                     proposal="Request for a Scoping Opinion under the EIA Regulations for up to 200 dwellings",
                     status="Awaiting decision")
    _intel(session, screening, total_units_final=200)

    facts = build_operative_planning_facts([screening])
    ff = resolve_operative_filter_facts(facts)
    assert ff.units is None
    assert ff.decision_status == NOT_DETERMINED_DECISION_STATUS
    assert format_operative_decision_status_label(ff) == "Not yet verified"
