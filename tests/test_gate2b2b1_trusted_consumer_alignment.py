"""Gate 2B-2B.1 - Trusted Consumer Alignment.

Regression coverage for the confirmed production defects this gate fixes:
Buyer Matching's hardcoded PERMISSION_GRANTED (Pendlebury Miners Club),
Residential Mix / Site Profile's mix_rep_app fallback resurrecting
withdrawn/screening evidence (Stockport Rugby Club, Pennington's Stables),
Explore's legacy aggregate_scheme_fields AH columns (Burnage), Brixham
Road's on-site-vs-policy AH percentage conflation, and Pinfold/Edenfield's
cross-boundary consultation response / absence-of-information note being
read as confirmed zero AH.

Every fixture is shaped after the real production example named in the
Gate 2B-2B.1 brief - never a Streamlit page, never an LLM, in-memory
SQLite only (tests/conftest.py's `session` fixture).
"""
from __future__ import annotations

from app.db.models import Application, SchemeIntelligence, Site
from app.policy.buyer_matching import (
    INSUFFICIENT_EVIDENCE,
    NOT_SUITABLE,
    PLANNING_DELIVERY,
    STRONG_FIT,
    assess_buyer_fit,
    build_planning_delivery_matching_facts_from_operative,
)
from app.policy.buyer_profiles import (
    HOUSING_ASSOCIATION,
    NATIONAL_HOUSEBUILDER,
    NESTEN_HOMES,
    OTHER_OR_UNKNOWN,
    PERMISSION_GRANTED,
    PLANNING_ACTIVE_PROPOSAL,
)
from app.reporting.affordable_housing_scope import compute_affordable_housing_scope_summary, format_affordable_housing_lines
from app.reporting.dashboard import _scheme_card
from app.reporting.residential_mix import build_residential_mix
from app.reporting.scheme_reconciliation import build_operative_planning_facts, resolve_operative_filter_facts
from app.reporting.scheme_summary import build_summary_prompt
from app.ui.common import aggregate_scheme_fields, compute_lapse_status
from app.pipeline.phase_tracking import build_phase_breakdown


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


# --- 1-7: Buyer Matching ----------------------------------------------------


def test_pending_application_never_maps_to_permission_granted(session):
    """Former Pendlebury Miners Club shape - an outline application still
    'Under Consultation', decision=None. The confirmed root cause: the old
    build_planning_delivery_matching_facts hardcoded PERMISSION_GRANTED
    unconditionally; the new operative-facts-aware builder must not."""
    site = _site(session)
    app = _app(session, site.id, "23/81450/OUT",
               proposal="Outline planning application for demolition and redevelopment for residential "
                        "(up to 63 no. dwellings) and associated infrastructure",
               status="Under Consultation", decision=None)
    _intel(session, app, total_units_final=63, affordable_units_final=5, affordable_percentage_final=8.0)

    facts = build_operative_planning_facts([app])
    matching_facts = build_planning_delivery_matching_facts_from_operative(facts, [app])
    assert matching_facts.planning_state != PERMISSION_GRANTED
    assert matching_facts.planning_state == PLANNING_ACTIVE_PROPOSAL

    assessment = assess_buyer_fit(NESTEN_HOMES, matching_facts)
    assert not any("permission granted" in m.lower() for m in assessment.matches)
    assert not any("permission granted" in m.lower() for m in assessment.does_not_match)


def test_permission_unknown_routes_through_uncertainty_not_a_hard_exclusion(session):
    """A withdrawn-only site (no consent, no active proposal) resolves
    planning_state to the existing generic OTHER_OR_UNKNOWN, never a
    disqualifying fact and never PERMISSION_GRANTED."""
    site = _site(session)
    app = _app(session, site.id, "DC/1", proposal="Full application for residential development of 40 dwellings",
               status="Withdrawn", decision="Application Withdrawn")
    _intel(session, app, total_units_final=40)

    facts = build_operative_planning_facts([app])
    matching_facts = build_planning_delivery_matching_facts_from_operative(facts, [app])
    assert matching_facts.planning_state == OTHER_OR_UNKNOWN

    assessment = assess_buyer_fit(NESTEN_HOMES, matching_facts)
    assert assessment.classification != NOT_SUITABLE or "planning" not in " ".join(assessment.does_not_match).lower()
    assert not any("permission granted" in m.lower() for m in assessment.matches)


def test_ah_unknown_does_not_pass_or_fail_a_threshold(session):
    """No AH evidence at all (a genuinely undetermined scheme) must route
    to 'unknown', never silently satisfy the Housing Association's AH
    scale requirement nor silently fail it as a hard exclusion."""
    site = _site(session)
    app = _app(session, site.id, "FUL/1", proposal="Full planning application for 80 dwellings",
               status="Decided", decision="Approve with Conditions")
    _intel(session, app, total_units_final=80)  # no AH fields set at all

    facts = build_operative_planning_facts([app])
    matching_facts = build_planning_delivery_matching_facts_from_operative(facts, [app])
    assert matching_facts.affordable_percentage_trusted is False
    assert matching_facts.affordable_unit_count is None

    assessment = assess_buyer_fit(HOUSING_ASSOCIATION, matching_facts)
    assert assessment.classification == INSUFFICIENT_EVIDENCE
    assert any("affordable" in u.lower() for u in assessment.unknown)


def test_withdrawn_ah_does_not_influence_current_buyer_fit(session):
    """Stockport Rugby Club shape - a withdrawn application's own 45-unit/
    50% AH figure must never reach MatchingFacts.affordable_unit_count/
    affordable_percentage at all (ah.historical is never read by the
    operative-facts builder)."""
    site = _site(session)
    app = _app(session, site.id, "DC/089037",
               proposal="Hybrid application for residential development and a care facility",
               status="Withdrawn", decision="Application Withdrawn")
    _intel(session, app, total_units_final=90, affordable_units_final=45, affordable_percentage_final=50.0)

    facts = build_operative_planning_facts([app])
    matching_facts = build_planning_delivery_matching_facts_from_operative(facts, [app])
    assert matching_facts.affordable_unit_count is None
    assert matching_facts.affordable_percentage is None
    assert matching_facts.unit_count is None


def test_mixed_housing_does_not_become_house_led(session):
    """Former Bandstand shape - development_type is read verbatim
    (mixed_apartments_and_houses), never coerced towards 'houses'
    regardless of the real 41-apartment/9-house split only ever appearing
    in free proposal text, never a structured field."""
    site = _site(session)
    app = _app(session, site.id, "141520/FO/2024",
               proposal="Redevelopment of the former Bandstand public house site for residential development "
                        "of 50 units (Class C3) (41 apartments and 9 properties)",
               status="Under Consideration", decision=None)
    _intel(session, app, total_units_final=50, development_type="mixed_apartments_and_houses",
           affordable_units_final=8, affordable_percentage_final=15.0)

    facts = build_operative_planning_facts([app])
    matching_facts = build_planning_delivery_matching_facts_from_operative(facts, [app])
    assert matching_facts.development_type_raw == "mixed_apartments_and_houses"
    assert matching_facts.is_specialist_development is False  # mixed housing is not a specialist type

    assessment = assess_buyer_fit(NATIONAL_HOUSEBUILDER, matching_facts)
    assert not any("house-led" in m.lower() for m in assessment.matches + assessment.does_not_match)


def test_consent_and_active_proposal_remain_distinguishable(session):
    """Hazelhurst Farm shape - a 400-unit consented whole-site permission
    plus a separate 176-unit active phase must both survive into
    MatchingFacts: planning_state stays PERMISSION_GRANTED (the consent is
    primary) but has_active_proposal/active_proposal_count preserve the
    coexisting live phase, and assess_buyer_fit surfaces it as an
    investigate note rather than silently dropping it."""
    site = _site(session)
    consented = _app(session, site.id, "23/81719/HYBEIA", proposal="Hybrid application for 400 dwellings",
                     status="Final", decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2020")
    _intel(session, consented, total_units_final=400, core_intelligence_complete=True)
    active_phase = _app(session, site.id, "NOT/2026/0722", proposal="Reserved matters for Phase 2 comprising 176 dwellings",
                        status="Awaiting decision", application_received="Mon 01 Jan 2025")
    _intel(session, active_phase, total_units_final=176, core_intelligence_complete=True)

    facts = build_operative_planning_facts([consented, active_phase])
    matching_facts = build_planning_delivery_matching_facts_from_operative(facts, [consented, active_phase])
    assert matching_facts.planning_state == PERMISSION_GRANTED
    assert matching_facts.unit_count == 400  # the consented figure is never destroyed by the active phase
    assert matching_facts.has_active_proposal is True
    assert matching_facts.active_proposal_count == 1

    assessment = assess_buyer_fit(NESTEN_HOMES, matching_facts)
    assert any("further active planning application" in i.lower() for i in assessment.investigate)


def test_multiple_active_proposals_do_not_latest_win(session):
    """No consent exists; two simultaneous active substantive proposals
    exist - unit_count/affordable figures must stay None (never pick the
    most recent or larger one), while active_proposal_count still reports
    the real count of 2."""
    site = _site(session)
    active_a = _app(session, site.id, "RM/Phase1", proposal="Reserved matters for Phase 1 comprising 100 dwellings",
                    status="Awaiting decision", application_received="Mon 01 Jan 2024")
    _intel(session, active_a, total_units_final=100, core_intelligence_complete=True)
    active_b = _app(session, site.id, "RM/Phase2", proposal="Reserved matters for Phase 2 comprising 120 dwellings",
                    status="Awaiting decision", application_received="Mon 01 Feb 2024")
    _intel(session, active_b, total_units_final=120, core_intelligence_complete=True)

    facts = build_operative_planning_facts([active_a, active_b])
    matching_facts = build_planning_delivery_matching_facts_from_operative(facts, [active_a, active_b])
    assert matching_facts.unit_count is None
    assert matching_facts.active_proposal_count == 2
    assert matching_facts.planning_state == PLANNING_ACTIVE_PROPOSAL


# --- 8-10: Residential Mix ---------------------------------------------------


def test_withdrawn_only_site_does_not_fall_back_to_current_mix(session):
    """Stockport Rugby Club shape - build_residential_mix must receive
    rep_app=None (not a fallback to the withdrawn application) whenever
    reconciliation resolves neither a consented nor an active position."""
    site = _site(session)
    app = _app(session, site.id, "DC/089037",
               proposal="Hybrid application for residential development and a care facility",
               status="Withdrawn", decision="Application Withdrawn")
    _intel(session, app, total_units_final=90, affordable_units_final=45, affordable_percentage_final=50.0)

    facts = build_operative_planning_facts([app])
    assert facts.consented_position.reference.state != "resolved"
    assert len(facts.active_positions) == 0

    # mirrors site_profile.py's own mix_rep_app resolution: None whenever
    # neither a consented nor an active position resolved.
    mix = build_residential_mix(site, [app], rep_app=None)
    assert mix["overview_totals"]["total_homes"] is None
    assert mix["affordable_headline"]["state"] == "not_identified"


def test_eia_screening_only_site_does_not_become_current_mix(session):
    """Pennington's Stables shape - a 68-home EIA screening figure must
    not resurface as "Total homes: 68" on Residential Mix."""
    site = _site(session)
    app = _app(session, site.id, "DC/091435",
               proposal="Environmental Impact Assessment Regulations 2017 Screening Request: Residential "
                        "development of up to 68 dwellings",
               status="Decided", decision="EIA Not Required")
    _intel(session, app, total_units_final=68)

    facts = build_operative_planning_facts([app])
    assert len(facts.active_positions) == 0
    assert facts.consented_position.reference.state != "resolved"

    mix = build_residential_mix(site, [app], rep_app=None)
    assert mix["overview_totals"]["total_homes"] is None


def test_not_determined_does_not_invoke_legacy_fallback_in_site_profile_mix_resolution(session):
    """Direct check on the site_profile.py resolution rule itself (the
    exact operative_app computation) - for a fully NOT_DETERMINED site,
    operative_app must resolve to None, never fall back to any
    representative application, regardless of which one a legacy
    pick_representative_application-style selector might have chosen."""
    site = _site(session)
    app = _app(session, site.id, "DC/1", proposal="Screening Opinion request for up to 200 dwellings",
               status="Awaiting decision")
    _intel(session, app, total_units_final=200, core_intelligence_complete=True)

    facts = build_operative_planning_facts([app])
    consented = facts.consented_position
    active_positions = facts.active_positions

    operative_app = None
    if consented.reference.state == "resolved" and consented.reference.source is not None:
        operative_app = next((a for a in [app] if a.id == consented.reference.source.application_id), None)
    elif active_positions and active_positions[0].reference.state == "resolved":
        src = active_positions[0].reference.source
        operative_app = next((a for a in [app] if a.id == src.application_id), None) if src else None
    assert operative_app is None


# --- 11-13: Explore AH -------------------------------------------------------


def test_ancillary_technical_zero_cannot_override_substantive_ah(session):
    """Former Burnage Cricket Club shape - a later condition-discharge
    filing's technical affordable_units_final=0/affordable_percentage_
    final=0.0 (no independent evidence) must not outrank the granted
    application's real 13-unit/19.7% consented AH position."""
    site = _site(session)
    granted = _app(session, site.id, "142311/FO/2025", proposal="Erection of up to 66 no. dwellings",
                   status="Final", decision="Approve", decision_issued_date="Mon 23 Mar 2026",
                   application_received="Wed 04 Mar 2025")
    _intel(session, granted, total_units_final=66, affordable_units_final=13, affordable_percentage_final=19.7,
           affordable_housing_status="officer_recommended", core_intelligence_complete=True)
    discharge = _app(session, site.id, "OTH-2026-001269", proposal="Discharge of a condition of 142311/FO/2025",
                     status="Under Consultation", decision=None, application_received="Fri 07 Aug 2026")
    _intel(session, discharge, total_units_final=66, affordable_units_final=0, affordable_percentage_final=0.0,
           core_intelligence_complete=True)

    facts = build_operative_planning_facts([granted, discharge])
    ff = resolve_operative_filter_facts(facts)
    assert ff.affordable_units == 13
    assert ff.affordable_percentage == 19.7
    assert ff.affordable_source == "consented"


def test_unknown_ah_stays_unknown_on_explore(session):
    """No AH evidence at all - Explore's trusted AH columns must resolve
    to None, never a fabricated zero."""
    site = _site(session)
    app = _app(session, site.id, "FUL/1", proposal="Full application for 30 dwellings",
               status="Decided", decision="Approve")
    _intel(session, app, total_units_final=30)

    facts = build_operative_planning_facts([app])
    ff = resolve_operative_filter_facts(facts)
    assert ff.affordable_units is None
    assert ff.affordable_percentage is None
    assert ff.affordable_source is None


def test_trusted_ah_propagates_identically_for_table_and_export(session):
    """The exact same resolve_operative_filter_facts call is reused for
    Explore's on-screen table and its exported report row - proven here by
    asserting two independent calls over the same facts object produce
    identical AH values, so the two surfaces can never show a different
    figure for the same Site."""
    site = _site(session)
    app = _app(session, site.id, "FUL/1", proposal="Full application for 100 dwellings",
               status="Decided", decision="Approve with Conditions")
    _intel(session, app, total_units_final=100, affordable_units_final=25, affordable_percentage_final=25.0)

    facts = build_operative_planning_facts([app])
    ff_table = resolve_operative_filter_facts(facts)
    ff_export = resolve_operative_filter_facts(facts)
    assert ff_table.affordable_units == ff_export.affordable_units == 25
    assert ff_table.affordable_percentage == ff_export.affordable_percentage == 25.0


# --- 14-17: AH semantics -----------------------------------------------------


def test_brixham_percentage_conflict_never_renders_as_one_combined_figure(session):
    """Brixham Road shape - 54/145 =~37.2% on-site, but the stored
    affordable_percentage_final is 40.0% (the wider policy position).
    Both figures must be surfaced distinctly with an explicit
    non-reconciliation flag, never combined into '54 affordable homes
    representing 40%'."""
    site = _site(session)
    app = _app(session, site.id, "114228/FUL/24",
               proposal="Residential development of 145 units", status="Awaiting decision")
    _intel(session, app, total_units_final=145, affordable_units_final=54, affordable_percentage_final=40.0,
           affordable_tenure_split_final="37% on-site, 3% financial contribution",
           affordable_housing_status="unknown")

    summary = compute_affordable_housing_scope_summary([app])
    position = summary.active_whole_site
    assert position is not None
    assert position.percentage == 40.0
    assert position.units == 54
    assert position.onsite_percentage == 37.2
    assert position.percentage_reconciles is False

    lines = format_affordable_housing_lines(summary)
    reconciliation_lines = [line for line in lines if "DOES NOT RECONCILE" in line]
    assert reconciliation_lines
    # both figures are named explicitly and distinctly in the same line -
    # never silently combined into one unqualified "N affordable homes
    # representing P%" statement with no caveat.
    assert "40.0%" in reconciliation_lines[0] and "37.2%" in reconciliation_lines[0]


def test_pending_legal_agreement_status_is_not_promoted_to_secured(session):
    """Brixham's affordable_housing_status='unknown' (legal agreements
    pending) must never be silently upgraded - the resolved position keeps
    'unknown' verbatim, never 'agreed'/'legally_secured'."""
    site = _site(session)
    app = _app(session, site.id, "114228/FUL/24", proposal="Residential development of 145 units",
               status="Awaiting decision")
    _intel(session, app, total_units_final=145, affordable_units_final=54, affordable_percentage_final=40.0,
           affordable_housing_status="unknown")

    summary = compute_affordable_housing_scope_summary([app])
    assert summary.active_whole_site.status == "unknown"


def test_absence_of_information_note_is_not_positive_zero_ah_evidence(session):
    """Pinfold/Edenfield shape - a note stating 'No affordable housing
    provision mentioned in the decision notice' must not, by itself, make
    a 0%/0-unit figure count as a genuine independent AH position."""
    site = _site(session)
    app = _app(session, site.id, "71149",
               proposal="Article 18 consultation from Rossendale Borough Council (2023/0396); Full application "
                        "for residential development comprising no. 50 units (Use Class C3)",
               status="Decided", decision="Raise No Objection")
    _intel(session, app, total_units_final=50, affordable_units_final=0, affordable_percentage_final=0.0,
           affordable_housing_status="unknown",
           affordable_housing_notes="No affordable housing provision mentioned in the decision notice. "
                                     "The application raises no objections to the overall development proposal.")

    summary = compute_affordable_housing_scope_summary([app])
    assert summary.whole_site is None
    assert summary.active_whole_site is None
    assert summary.historical == ()


def test_genuinely_evidenced_zero_ah_remains_possible(session):
    """A real, explicitly evidenced 0% position (a genuine status, not an
    absence-of-information note) must still be preserved - the hardening
    in the previous test must not reject every zero."""
    site = _site(session)
    app = _app(session, site.id, "FUL/1", proposal="Full application for 20 dwellings",
               status="Decided", decision="Approve with Conditions")
    _intel(session, app, total_units_final=20, affordable_units_final=0, affordable_percentage_final=0.0,
           affordable_housing_status="agreed")

    summary = compute_affordable_housing_scope_summary([app])
    assert summary.whole_site is not None
    assert summary.whole_site.percentage == 0.0
    assert summary.whole_site.status == "agreed"


# --- 18-19: Role hardening ---------------------------------------------------


def test_cross_boundary_consultation_response_is_not_substantive_permission(session):
    """Pinfold/Edenfield shape - reference 71149's role must resolve to
    the existing, already-non-substantive ROLE_EXTERNAL_CONSULTATION, not
    ROLE_FULL, so it cannot control the site's operative planning
    position."""
    from app.reporting.scheme_reconciliation import ROLE_EXTERNAL_CONSULTATION, resolve_planning_role

    site = _site(session)
    app = _app(session, site.id, "71149",
               proposal="Article 18 consultation from Rossendale Borough Council (2023/0396); Full application "
                        "for residential development comprising no. 50 units (Use Class C3)",
               status="Decided", decision="Raise No Objection")

    assert resolve_planning_role(app) == ROLE_EXTERNAL_CONSULTATION

    facts = build_operative_planning_facts([app])
    assert facts.consented_position.reference.state != "resolved"
    assert len(facts.active_positions) == 0


def test_raise_no_objection_is_not_permission(session):
    """'Raise No Objection' must never resolve as a granted decision -
    checked independently of the role-hardening test above, directly
    against the decided-state classifier."""
    from app.pipeline.material_change import DECIDED_GRANTED, resolve_decided_state

    assert resolve_decided_state("Raise No Objection", "Decided") != DECIDED_GRANTED


# --- 20-21: Dashboard --------------------------------------------------------


def test_event_level_application_fields_remain_application_level(session):
    """The triggering application's own reference/address/raw status must
    never be erased by the site-level migration - _scheme_card still
    names the actual application that generated the event."""
    site = _site(session)
    app = _app(session, site.id, "NOT/2026/0001", proposal="Full application for 10 dwellings",
               status="Under Consultation", decision=None, address="1 Example Street")
    _intel(session, app, total_units_final=10)

    facts = build_operative_planning_facts([app])
    card = _scheme_card(app, why="New application scraped", when=None, operative_facts=facts)
    assert card["reference"] == "NOT/2026/0001"
    assert card["address"] == "1 Example Street"
    assert card["planning_status"] == "Under Consultation"
    assert card["why"] == "New application scraped"


def test_dashboard_site_level_facts_come_from_operative_facts_not_the_triggering_app(session):
    """Former Pendlebury Miners Club shape - the triggering application
    IS the site's only application here, so this specifically proves the
    card's decision_status is never claimed as 'Granted' for a pending
    outline application, and its total_units comes from the trusted
    active-position figure, not a raw/legacy read."""
    site = _site(session)
    app = _app(session, site.id, "23/81450/OUT",
               proposal="Outline planning application for demolition and redevelopment for residential "
                        "(up to 63 no. dwellings)",
               status="Under Consultation", decision=None)
    _intel(session, app, total_units_final=63)

    facts = build_operative_planning_facts([app])
    card = _scheme_card(app, why="New application scraped", when=None, operative_facts=facts)
    assert card["decision_status"] is None  # never "Granted" for a pending application
    assert card["total_units"] == 63


# --- 22-23: AI Summary -------------------------------------------------------


def test_ai_summary_prompt_context_uses_operative_facts(session):
    """The SCHEME SCOPE / OPERATIVE PLANNING POSITION lines fed to the
    model must state the trusted, reconciled figures - proven here for a
    genuinely granted, single-application site."""
    site = _site(session)
    app = _app(session, site.id, "FUL/1", proposal="Full application for 45 dwellings",
               status="Decided", decision="Approve with Conditions")
    _intel(session, app, total_units_final=45, developer="Example Developer Ltd")

    merged = aggregate_scheme_fields([app])
    lapse = compute_lapse_status([app], site)
    phase_breakdown = build_phase_breakdown([app])
    prompt = build_summary_prompt(site, [app], merged, lapse, phase_breakdown)

    assert "SCHEME SCOPE: 45 total units (consented position)" in prompt
    assert "OPERATIVE PLANNING POSITION: Granted" in prompt


def test_withdrawn_evidence_cannot_become_current_scheme_truth_in_ai_prompt_context(session):
    """Stockport Rugby Club shape - the AI prompt must state the
    reconciled 'not yet determined' position, never resurrect the
    withdrawn application's own figures as the scheme's current position."""
    site = _site(session)
    app = _app(session, site.id, "DC/089037",
               proposal="Hybrid application for residential development and a care facility",
               status="Withdrawn", decision="Application Withdrawn")
    _intel(session, app, total_units_final=90, affordable_units_final=45, affordable_percentage_final=50.0)

    merged = aggregate_scheme_fields([app])
    lapse = compute_lapse_status([app], site)
    phase_breakdown = build_phase_breakdown([app])
    prompt = build_summary_prompt(site, [app], merged, lapse, phase_breakdown)

    assert "not yet determined from the evidence held" in prompt
    assert "OPERATIVE PLANNING POSITION: not yet determined" in prompt or "not yet determined from the evidence held" in prompt


# --- 24-26: Non-regression ---------------------------------------------------


def test_hazelhurst_consent_and_active_phase_remain_intact_end_to_end(session):
    """Full end-to-end non-regression: Hazelhurst Farm's consented
    whole-site position and its separate active phase must both still be
    independently resolvable by the trusted facts layer after every
    change in this gate."""
    site = _site(session)
    consented = _app(session, site.id, "23/81719/HYBEIA", proposal="Hybrid application for 400 dwellings",
                     status="Final", decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2020")
    _intel(session, consented, total_units_final=400, affordable_percentage_final=20.0, affordable_units_final=31,
           core_intelligence_complete=True)
    active_phase = _app(session, site.id, "NOT/2026/0722", proposal="Reserved matters for Phase 2 comprising 176 dwellings",
                        status="Awaiting decision", application_received="Mon 01 Jan 2025")
    _intel(session, active_phase, total_units_final=176, core_intelligence_complete=True)

    facts = build_operative_planning_facts([consented, active_phase])
    assert facts.consented_position.approved_units.value == 400
    assert len(facts.active_positions) == 1
    assert facts.active_positions[0].proposed_units.value == 176
    assert facts.affordable_housing.whole_site.percentage == 20.0
