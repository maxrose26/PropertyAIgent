"""Gate 2B-1/2B-2A - Trusted Operative Planning Facts.

app.reporting.scheme_reconciliation.build_operative_planning_facts.
Deterministic, computed, non-persisted, fact-level reconciliation.

Covers:
- planning_role resolution + decided-state overlay (distinct from
  application_category);
- phase/scope resolution, including Gate 2B-2A's material-development-
  parcel distinction (individual dwelling plots never become peer scopes);
- CONSENTED position vs ACTIVE position(s) kept structurally separate
  (never collapsed; zero/one/many active positions supported);
- SAFEGUARD: residential-only quantum is not a new inference;
- SAFEGUARD: S73/variation authority is fact-specific;
- non-substantive guardrail (EIA screening/scoping, condition discharge);
- relationship confidence (site_link_method/confidence) and evidence
  freshness (status_verified_at, never last_seen_at) on every resolved
  fact's provenance;
- same-scope conflict surfacing;
- the real Astra regression cases.

In-memory-SQLite `session` fixture (tests/conftest.py). No OpenAI call.
"""
from __future__ import annotations

from app.db.models import Application, SchemeIntelligence, Site
from app.pipeline.material_change import DECIDED_GRANTED, DECIDED_RECOMMENDATION_ONLY, DECIDED_UNDETERMINED
from app.reporting.scheme_reconciliation import (
    FACT_CONFLICT,
    FACT_NOT_DETERMINED,
    FACT_RESOLVED,
    RELATIONSHIP_HIGH,
    RELATIONSHIP_REVIEW_REQUIRED,
    RELATIONSHIP_UNKNOWN,
    ROLE_CONDITION_DISCHARGE,
    ROLE_EIA_SCOPING,
    ROLE_EIA_SCREENING,
    ROLE_FULL,
    ROLE_NMC_AMENDMENT,
    ROLE_OUTLINE,
    ROLE_RESERVED_MATTERS,
    ROLE_S73_VARIATION,
    SCOPE_PHASE,
    SCOPE_PLOT,
    SCOPE_UNCLEAR,
    SCOPE_WHOLE_SITE,
    build_operative_planning_facts,
    resolve_decided_state,
    resolve_planning_role,
    resolve_relationship_confidence,
)


def _site(session, **kw) -> Site:
    s = Site(council_code="testcouncil", canonical_address="land at x", display_address="Land at X", **kw)
    session.add(s)
    session.commit()
    return s


def _app(session, site_id, reference, *, proposal="", application_type=None, status=None,
         decision=None, decision_issued_date=None, application_received="Mon 01 Jan 2024",
         estimated_unit_count=None, site_link_method="exact_address", site_link_confidence=None,
         status_verified_at=None) -> Application:
    a = Application(
        council_code="testcouncil", reference=reference, site_id=site_id, proposal=proposal,
        application_type=application_type, status=status, decision=decision,
        decision_issued_date=decision_issued_date, application_received=application_received,
        estimated_unit_count=estimated_unit_count, site_link_method=site_link_method,
        site_link_confidence=site_link_confidence, status_verified_at=status_verified_at,
    )
    session.add(a)
    session.commit()
    return a


def _intel(session, app, **kw) -> SchemeIntelligence:
    si = SchemeIntelligence(application_id=app.id, **kw)
    session.add(si)
    session.commit()
    return si


# --- 1. planning_role resolution (distinct from application_category) ------


def test_planning_role_covers_the_lifecycle_vocabulary(session):
    site = _site(session)
    cases = {
        "OUT/1": ("Outline application for up to 100 dwellings", None, ROLE_OUTLINE),
        "FUL/1": ("Erection of 120 dwellings", None, ROLE_FULL),
        "RM/1": ("Application for approval of reserved matters for 80 dwellings", None, ROLE_RESERVED_MATTERS),
        "S73/1": ("Variation of condition 2 of permission A/1", None, ROLE_S73_VARIATION),
        "NMA/1": ("Non-material amendment to permission A/1", None, ROLE_NMC_AMENDMENT),
        "DOC/1": ("Discharge of condition 5 attached to outline permission A/1", None, ROLE_CONDITION_DISCHARGE),
        "SCR/1": ("Request for an EIA screening opinion for residential development", None, ROLE_EIA_SCREENING),
    }
    for ref, (proposal, at, expected) in cases.items():
        a = _app(session, site.id, ref, proposal=proposal, application_type=at)
        assert resolve_planning_role(a) == expected, ref


def test_eia_screening_recognised_from_screening_request_wording(session):
    """Gate 2B-1 Defect 1 - Pennington's Stables (DC/091435)."""
    site = _site(session)
    a = _app(session, site.id, "DC/091435",
             proposal="Town and Country Planning (Environmental Impact Assessment) Regulations 2017 "
                      "Screening Request: Residential development of up to 68 dwellings",
             decision="EIA Not Required", status="Decided")
    assert resolve_planning_role(a) == ROLE_EIA_SCREENING


def test_eia_screening_recognised_from_decision_value_alone(session):
    site = _site(session)
    a = _app(session, site.id, "DC/097770",
             proposal="Residential development for up to 250 dwellings with associated access, open space "
                      "and biodiversity net gain",
             decision="EIA Not Required", status="Decided")
    assert resolve_planning_role(a) == ROLE_EIA_SCREENING


def test_eia_scoping_recognised_and_distinguished_from_screening(session):
    site = _site(session)
    a = _app(session, site.id, "DC/086169",
             proposal="Environmental Impact Assessment (EIA) Scoping Opinion request - Development of a "
                      "24.12ha site comprising maximum 180 dwellings",
             decision="Scoping Opinion", status="Decided")
    assert resolve_planning_role(a) == ROLE_EIA_SCOPING


def test_non_eia_screening_word_is_not_misclassified(session):
    site = _site(session)
    a = _app(session, site.id, "26/00082/PLCOND",
             proposal="Full Discharge Of Condition 22 (Television Reception Screening) Of Planning "
                      "Reference 24/00655/FUL",
             application_type="Approval of details reserved by a condition", status="Awaiting decision")
    assert resolve_planning_role(a) == ROLE_CONDITION_DISCHARGE


def test_decided_state_overlay_never_collapses_recommendation_into_grant(session):
    site = _site(session)
    a = _app(session, site.id, "R/1", proposal="Erection of 50 dwellings",
             status="Recommendation Made", decision="Officer Recommendation: Approve")
    assert resolve_decided_state(a) == DECIDED_RECOMMENDATION_ONLY
    b = _app(session, site.id, "G/1", proposal="Erection of 50 dwellings",
             status="Decided", decision="Granted")
    assert resolve_decided_state(b) == DECIDED_GRANTED


# --- 2. relationship confidence (Gate 2B-2A, "essential now") -------------


def test_relationship_confidence_high_for_deterministic_link_methods(session):
    site = _site(session)
    for method in ("exact_address", "parent_reference", "created"):
        a = _app(session, site.id, f"REF/{method}", proposal="Erection of 40 dwellings", site_link_method=method)
        level, m, numeric = resolve_relationship_confidence(a)
        assert level == RELATIONSHIP_HIGH, method
        assert m == method
        assert numeric is None


def test_relationship_confidence_review_required_for_suggested_fuzzy(session):
    site = _site(session)
    a = _app(session, site.id, "REF/fuzzy", proposal="Erection of 40 dwellings",
             site_link_method="suggested_fuzzy", site_link_confidence=0.72)
    level, method, numeric = resolve_relationship_confidence(a)
    assert level == RELATIONSHIP_REVIEW_REQUIRED
    assert numeric == 0.72


def test_relationship_confidence_unknown_when_no_link_method_recorded(session):
    site = _site(session)
    a = _app(session, site.id, "REF/none", proposal="Erection of 40 dwellings", site_link_method=None)
    level, method, numeric = resolve_relationship_confidence(a)
    assert level == RELATIONSHIP_UNKNOWN


def test_resolved_fact_provenance_carries_relationship_and_freshness(session):
    import datetime as dt
    site = _site(session)
    verified_at = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
    a = _app(session, site.id, "FUL/1", proposal="Erection of 70 dwellings",
             status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2024",
             site_link_method="suggested_fuzzy", site_link_confidence=0.9, status_verified_at=verified_at)
    _intel(session, a, total_units_final=70)
    facts = build_operative_planning_facts([a])
    src = facts.consented_position.reference.source
    assert src.relationship_level == RELATIONSHIP_REVIEW_REQUIRED
    assert src.relationship_method == "suggested_fuzzy"
    assert src.status_verified_at == verified_at
    assert src.independently_verified is True


def test_resolved_fact_freshness_honest_when_never_verified(session):
    """last_seen_at must never be substituted for status_verified_at."""
    site = _site(session)
    a = _app(session, site.id, "FUL/1", proposal="Erection of 70 dwellings",
             status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2024")
    _intel(session, a, total_units_final=70)
    facts = build_operative_planning_facts([a])
    src = facts.consented_position.reference.source
    assert src.status_verified_at is None
    assert src.independently_verified is False


# --- 3. CONSENTED vs ACTIVE - never collapsed ------------------------------


def test_operative_selection_prefers_granted_substantive_over_newer_non_substantive(session):
    site = _site(session)
    granted = _app(session, site.id, "FUL/2020", proposal="Erection of 90 dwellings",
                   status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2020",
                   application_received="Mon 01 Jan 2019")
    _intel(session, granted, total_units_final=90, core_intelligence_complete=True)
    doc = _app(session, site.id, "DOC/2025", proposal="Discharge of conditions 3-7 of permission FUL/2020",
               status="Decided", decision="Approved", application_received="Mon 01 Jan 2025")
    _intel(session, doc, total_units_final=90, core_intelligence_complete=True)

    facts = build_operative_planning_facts([granted, doc])
    c = facts.consented_position
    assert c.reference.value == "FUL/2020"
    assert c.planning_status.value == "Permission granted"
    assert c.approved_units.value == 90
    assert facts.active_positions == ()


def test_consented_and_active_coexist_and_are_never_merged(session):
    """World of Pets shape, simplified: a granted permission AND a live
    proposal on the SAME site must both be exposed, never collapsed into
    one 'current scheme'."""
    site = _site(session)
    granted = _app(session, site.id, "FUL/2019", proposal="Erection of 50 dwellings",
                   status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2020")
    _intel(session, granted, total_units_final=50)
    live = _app(session, site.id, "FUL/2025", proposal="Erection of 62 dwellings (resubmission)",
                status="Awaiting decision", application_received="Mon 01 Jan 2025")
    _intel(session, live, total_units_final=62)
    facts = build_operative_planning_facts([granted, live])
    assert facts.consented_position.approved_units.value == 50
    assert len(facts.active_positions) == 1
    assert facts.active_positions[0].proposed_units.value == 62
    assert facts.active_positions[0].reference.value == "FUL/2025"


def test_multiple_simultaneous_active_positions_are_not_reduced_to_one(session):
    """Section 7: zero, ONE, OR MULTIPLE active positions - 'latest
    application wins' must not be replaced with 'latest ACTIVE application
    wins'. Two independent live full applications in different scopes."""
    site = _site(session)
    outline = _app(session, site.id, "OUT/1", proposal="Outline application for up to 400 dwellings",
                   status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2020")
    _intel(session, outline, total_units_final=400)
    live_a = _app(session, site.id, "RM/Phase1", proposal="Reserved matters for Phase 1 comprising 100 dwellings",
                  status="Awaiting decision", application_received="Mon 01 Jan 2024")
    _intel(session, live_a, total_units_final=100)
    live_b = _app(session, site.id, "RM/Phase2", proposal="Reserved matters for Phase 2 comprising 120 dwellings",
                  status="Awaiting decision", application_received="Mon 01 Feb 2024")
    _intel(session, live_b, total_units_final=120)

    facts = build_operative_planning_facts([outline, live_a, live_b])
    assert len(facts.active_positions) == 2
    labels = {p.scope_label: p.proposed_units.value for p in facts.active_positions}
    assert labels == {"Phase 1": 100, "Phase 2": 120}


def test_no_active_position_when_nothing_is_live(session):
    site = _site(session)
    granted = _app(session, site.id, "FUL/1", proposal="Erection of 60 dwellings",
                   status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2020")
    _intel(session, granted, total_units_final=60)
    facts = build_operative_planning_facts([granted])
    assert facts.active_positions == ()


def test_recency_is_only_a_tie_break_between_equivalent_sources(session):
    site = _site(session)
    older = _app(session, site.id, "FUL/A", proposal="Erection of 40 dwellings",
                 status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2020",
                 application_received="Mon 01 Jan 2019")
    _intel(session, older, total_units_final=40)
    newer = _app(session, site.id, "FUL/B", proposal="Erection of 44 dwellings",
                 status="Decided", decision="Granted", decision_issued_date="Fri 01 Jan 2021",
                 application_received="Mon 01 Jan 2020")
    _intel(session, newer, total_units_final=44)
    facts = build_operative_planning_facts([older, newer])
    assert facts.consented_position.approved_units.value == 44
    assert any(p.value == 40 for p in facts.consented_position.superseded_units)


# --- 4. non-substantive guardrail (G1, G2) --------------------------------


def test_eia_screening_cannot_establish_permission_or_units(session):
    """Pennington's Stables."""
    site = _site(session)
    scr = _app(session, site.id, "SCR/1",
               proposal="Request for a screening opinion under the EIA Regulations for residential development of 60 homes",
               status="Decision Made", decision="EIA not required", decision_issued_date="Wed 01 Jan 2025")
    _intel(session, scr, total_units_final=60, core_intelligence_complete=True)
    facts = build_operative_planning_facts([scr])
    c = facts.consented_position
    assert c.reference.state == FACT_NOT_DETERMINED
    assert c.planning_status.state == FACT_NOT_DETERMINED
    assert c.approved_units.state == FACT_NOT_DETERMINED
    assert facts.active_positions == ()


def test_condition_discharge_never_overwrites_the_underlying_unit_count(session):
    site = _site(session)
    perm = _app(session, site.id, "FUL/1", proposal="Erection of 100 dwellings",
                status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2022")
    _intel(session, perm, total_units_final=100)
    doc = _app(session, site.id, "DOC/1", proposal="Discharge of condition 12 (landscaping) of FUL/1",
               status="Decided", decision="Approved", application_received="Mon 01 Jan 2024")
    _intel(session, doc, total_units_final=8)
    facts = build_operative_planning_facts([perm, doc])
    assert facts.consented_position.approved_units.value == 100
    assert facts.consented_position.approved_units.source.application_reference == "FUL/1"


# --- 5. residential-only safeguard, S73 safeguard (unchanged from 2B-1) ---


def test_stockport_rugby_club_declines_residential_only_where_specialist_component(session):
    site = _site(session)
    app = _app(session, site.id, "HYB/1",
               proposal="Hybrid application: up to 60 dwellings plus a 70-bed extra care facility and associated works",
               status="Awaiting decision", application_received="Mon 01 Jan 2025")
    _intel(session, app, total_units_final=130, specialist_housing_type="Extra care (Use Class C2)",
           core_intelligence_complete=True)
    facts = build_operative_planning_facts([app])
    active = facts.active_positions[0]
    assert active.residential_only_units.state == FACT_NOT_DETERMINED
    assert "specialist" in active.residential_only_units.reason.lower()
    assert active.all_use_total_units.value == 130


def test_s73_without_ah_evidence_does_not_control_affordable_housing(session):
    site = _site(session)
    perm = _app(session, site.id, "FUL/2020", proposal="Erection of 100 dwellings including 30% affordable housing",
                status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2020")
    _intel(session, perm, total_units_final=100, affordable_units_final=30, affordable_percentage_final=30.0,
           affordable_housing_status="legally_secured",
           affordable_housing_notes="30% secured via S106 dated 2020.")
    s73 = _app(session, site.id, "FUL/2024", proposal="Variation of condition 2 (approved plans) of FUL/2020 to amend house types and layout",
               status="Decided", decision="Granted", decision_issued_date="Mon 01 Jan 2024",
               application_received="Mon 01 Jun 2023")
    _intel(session, s73, core_intelligence_complete=True)
    facts = build_operative_planning_facts([perm, s73])
    ah = facts.affordable_housing
    assert ah.whole_site is not None
    assert ah.whole_site.application_reference == "FUL/2020"
    assert facts.consented_position.approved_units.value == 100
    assert facts.consented_position.approved_units.source.application_reference == "FUL/2020"


def test_s73_with_its_own_unit_figure_may_control_approved_units(session):
    site = _site(session)
    perm = _app(session, site.id, "FUL/2020", proposal="Erection of 100 dwellings",
                status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2020")
    _intel(session, perm, total_units_final=100)
    s73 = _app(session, site.id, "FUL/2024",
               proposal="Section 73 variation of FUL/2020 to increase the number of dwellings to 108",
               status="Decided", decision="Granted", decision_issued_date="Mon 01 Jan 2024",
               application_received="Mon 01 Jun 2023")
    _intel(session, s73, total_units_final=108)
    facts = build_operative_planning_facts([perm, s73])
    assert facts.consented_position.approved_units.value == 108
    assert any(p.value == 100 for p in facts.consented_position.superseded_units)


# --- 6. Burnage / Brixham / Hazelhurst / London Road ----------------------


def test_burnage_technical_zero_never_silently_supplies_affordable_housing(session):
    site = _site(session)
    perm = _app(session, site.id, "FUL/1", proposal="Erection of 45 dwellings",
                status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2023")
    _intel(session, perm, total_units_final=45, affordable_units_final=13, affordable_percentage_final=29.0,
           affordable_housing_status="conditioned",
           affordable_housing_notes="13 affordable homes secured by condition.")
    doc = _app(session, site.id, "DOC/1", proposal="Discharge of condition 8 (drainage) of FUL/1",
               status="Decided", decision="Approved", application_received="Mon 01 Jan 2024")
    _intel(session, doc, affordable_units_final=0, affordable_percentage_final=0, affordable_housing_status="unknown")
    facts = build_operative_planning_facts([perm, doc])
    assert facts.affordable_housing.whole_site.units == 13
    assert facts.affordable_housing.whole_site.application_reference == "FUL/1"


def test_brixham_road_coherent_active_ah_position(session):
    site = _site(session)
    a = _app(session, site.id, "114228/FUL/24",
             proposal="Residential-led mixed use scheme comprising 145 dwellings and a commercial unit",
             status="Awaiting decision")
    _intel(session, a, total_units_final=145, affordable_units_final=54, affordable_percentage_final=40.0,
           affordable_housing_status="unknown")
    facts = build_operative_planning_facts([a])
    assert facts.consented_position.approved_units.state == FACT_NOT_DETERMINED
    assert facts.active_positions[0].proposed_units.value == 145
    assert facts.affordable_housing.active_whole_site.units == 54
    assert facts.affordable_housing.whole_site is None  # never a consented AH position from a pending app


def test_hazelhurst_farm_consented_and_active_ah_and_phase_stay_distinct(session):
    site = _site(session)
    outline = _app(session, site.id, "OUT/1", proposal="Outline application for up to 300 dwellings across the site",
                   status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2020")
    _intel(session, outline, total_units_final=300, affordable_percentage_final=30.0, affordable_units_final=90,
           affordable_housing_status="legally_secured")
    ph1 = _app(session, site.id, "RM/1", proposal="Reserved matters for Phase 1 comprising 100 dwellings",
               status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2022")
    _intel(session, ph1, total_units_final=100, affordable_percentage_final=100.0, affordable_units_final=100,
           affordable_housing_status="conditioned")
    facts = build_operative_planning_facts([outline, ph1])
    ah = facts.affordable_housing
    assert ah.whole_site.percentage == 30.0
    assert any(p.percentage == 100.0 for p in ah.phases)


def test_london_road_operative_state_not_generic_recency(session):
    site = _site(session)
    perm = _app(session, site.id, "FUL/2021", proposal="Erection of 109 dwellings",
                status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2022",
                application_received="Mon 01 Jan 2021")
    _intel(session, perm, total_units_final=109, core_intelligence_complete=True)
    nma = _app(session, site.id, "NMA/2025", proposal="Non-material amendment to FUL/2021 (window alterations)",
               status="Decided", decision="Approved", application_received="Mon 01 Jun 2025")
    _intel(session, nma, core_intelligence_complete=True)
    facts = build_operative_planning_facts([perm, nma])
    assert facts.consented_position.reference.value == "FUL/2021"
    assert facts.consented_position.planning_status.value == "Permission granted"
    assert facts.consented_position.approved_units.value == 109


# --- 7. general guardrails -----------------------------------------------


def test_not_determined_where_no_substantive_application_exists(session):
    site = _site(session)
    doc = _app(session, site.id, "DOC/1", proposal="Discharge of condition 4 of an unknown permission",
               status="Decided", decision="Approved")
    nma = _app(session, site.id, "NMA/1", proposal="Non-material amendment", status="Decided", decision="Approved")
    facts = build_operative_planning_facts([doc, nma])
    assert facts.consented_position.planning_status.state == FACT_NOT_DETERMINED
    assert facts.consented_position.approved_units.state == FACT_NOT_DETERMINED
    assert facts.consented_position.reference.state == FACT_NOT_DETERMINED
    assert facts.active_positions == ()


def test_every_resolved_fact_carries_provenance_and_reason(session):
    site = _site(session)
    a = _app(session, site.id, "FUL/1", proposal="Erection of 70 dwellings",
             status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2024")
    _intel(session, a, total_units_final=70)
    facts = build_operative_planning_facts([a])
    c = facts.consented_position
    for fact in (c.reference, c.planning_status, c.approved_units, c.residential_only_units):
        if fact.state == FACT_RESOLVED:
            assert fact.source is not None
            assert fact.source.application_reference
            assert fact.source.planning_role
            assert fact.reason
            assert fact.confidence in ("high", "medium", "low")
            assert fact.source.relationship_level in (RELATIONSHIP_HIGH, RELATIONSHIP_REVIEW_REQUIRED, RELATIONSHIP_UNKNOWN)


def test_reconciliation_does_not_touch_application_category(session):
    site = _site(session)
    a = _app(session, site.id, "FUL/1", proposal="Erection of 70 dwellings", status="Awaiting decision")
    a.application_category = "primary_residential"
    session.commit()
    build_operative_planning_facts([a])
    session.refresh(a)
    assert a.application_category == "primary_residential"


# --- 8. Phase vs plot (Gate 2B-2A) -----------------------------------------


def test_genuine_development_phase_remains_independently_scoped(session):
    """Requirement 1: a genuine phase remains its own peer scope."""
    site = _site(session)
    a = _app(session, site.id, "RM/EV1", proposal="Reserved Matters application for Phase EV1 comprising 80 dwellings",
             status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2024")
    _intel(session, a, total_units_final=80)
    facts = build_operative_planning_facts([a])
    assert facts.consented_position.reference.source.scope_type == SCOPE_PHASE
    assert facts.consented_position.reference.source.scope_label == "Phase EV1"


def test_individual_dwelling_plot_does_not_create_a_peer_scope(session):
    """Requirement 2: an individual plot citation (a condition-discharge
    filing with no independent unit count of its own) must not create its
    own acquisition-level scope - it folds into whole-site."""
    site = _site(session)
    perm = _app(session, site.id, "FUL/1", proposal="Erection of 60 dwellings",
                status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2020")
    _intel(session, perm, total_units_final=60)
    plot_doc = _app(session, site.id, "DOC/1",
                    proposal="Condition Discharge application for gas validation certificates for plots 45, 46, 49 and 67",
                    status="Decided", decision="Agreed", application_received="Mon 01 Jan 2021")
    facts = build_operative_planning_facts([perm, plot_doc])
    # the plot-labelled discharge never becomes its own scope
    scopes = {r.scope_type for r in facts.resolved_applications}
    assert SCOPE_PLOT not in scopes
    plot_doc_scope = next(r for r in facts.resolved_applications if r.reference == "DOC/1").scope_type
    assert plot_doc_scope in (SCOPE_WHOLE_SITE, SCOPE_UNCLEAR)


def test_range_of_individual_plots_does_not_create_multiple_apparent_phases(session):
    """Requirement 3."""
    site = _site(session)
    perm = _app(session, site.id, "FUL/1", proposal="Erection of 60 dwellings",
                status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2020")
    _intel(session, perm, total_units_final=60)
    docs = []
    for i, plots in enumerate(["1-40, 50-66 and 85-87", "41-44, 47-48, 67"], start=1):
        d = _app(session, site.id, f"DOC/{i}",
                 proposal=f"Condition Discharge application for gas validation for plots {plots}",
                 status="Decided", decision="Agreed", application_received=f"Mon 0{i} Jan 2021")
        docs.append(d)
    facts = build_operative_planning_facts([perm] + docs)
    plot_scopes = {r.scope_label for r in facts.resolved_applications if r.scope_type == SCOPE_PLOT}
    assert plot_scopes == set()  # no apparent phases/opportunities fabricated from plot ranges


def test_material_development_parcel_remains_independently_scoped(session):
    """Requirement 4: a 'plot' group backed by its own genuine, qualifying-
    scale unit count (a real development parcel, not an individual house)
    DOES remain its own peer scope."""
    site = _site(session)
    perm = _app(session, site.id, "HYB/1",
                proposal="Hybrid planning application for the redevelopment of Plot 1 comprising 45 dwellings",
                status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2024")
    _intel(session, perm, total_units_final=45)
    facts = build_operative_planning_facts([perm])
    assert facts.consented_position.reference.source.scope_type == SCOPE_PLOT
    assert facts.consented_position.approved_units.value == 45


def test_uncertain_plot_wording_produces_uncertainty_not_fabricated_phase(session):
    """Requirement 5: a 'plot' group with no qualifying-scale unit evidence
    of its own (even if it's the ONLY application on the site) is not
    manufactured into a development phase - it resolves as whole-site."""
    site = _site(session)
    a = _app(session, site.id, "DOC/1",
             proposal="Discharge of condition 4 (landscaping) on Plot 6",
             status="Decided", decision="Agreed")
    facts = build_operative_planning_facts([a])
    r = facts.resolved_applications[0]
    assert r.scope_type != SCOPE_PLOT


def test_individual_plot_does_not_fragment_affordable_housing(session):
    """Requirement 6 - the Gate 2B-2A fix to the original Plot 5 defect:
    an individual dwelling plot must not create its own AH scope entry."""
    site = _site(session)
    perm = _app(session, site.id, "FUL/1", proposal="Erection of 60 dwellings",
                status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2020")
    _intel(session, perm, total_units_final=60, affordable_percentage_final=20.0, affordable_units_final=12,
           affordable_housing_status="legally_secured")
    plot_app = _app(session, site.id, "DOC/PLOT5", proposal="Discharge of conditions for Plot 5",
                    status="Decided", decision="Agreed")
    _intel(session, plot_app, affordable_percentage_final=0, affordable_units_final=0, affordable_housing_status="agreed")
    facts = build_operative_planning_facts([perm, plot_app])
    ah = facts.affordable_housing
    assert not any(p.scope_label == "Plot 5" for p in ah.phases)
    assert ah.whole_site.units == 12  # the technical plot filing's 0 never contaminates the whole-site position


def test_source_evidence_preserved_when_plot_suppressed_from_operative_scope(session):
    """Requirement 7: the plot-labelled application itself is still fully
    present in resolved_applications - only its SCOPE resolution changes,
    nothing is deleted."""
    site = _site(session)
    perm = _app(session, site.id, "FUL/1", proposal="Erection of 60 dwellings",
                status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2020")
    _intel(session, perm, total_units_final=60)
    plot_doc = _app(session, site.id, "DOC/1", proposal="Discharge of conditions for Plot 9",
                    status="Decided", decision="Agreed")
    facts = build_operative_planning_facts([perm, plot_doc])
    refs = {r.reference for r in facts.resolved_applications}
    assert refs == {"FUL/1", "DOC/1"}
