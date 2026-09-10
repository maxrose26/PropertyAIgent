"""Gate 2B-1 - Scheme / Application / Phase Reconciliation (V1).

Deterministic, computed, non-persisted fact-level reconciliation:
app.reporting.scheme_reconciliation.reconcile_scheme.

Covers:
- planning_role resolution + decided-state overlay (distinct from
  application_category);
- phase/scope resolution (reused from phase_tracking);
- lead application / operative permission / operative planning status
  selection by role + decided-state (recency tie-break only);
- approved / proposed / superseded residential quantum kept separate;
- SAFEGUARD G9: residential-only quantum is not a new inference;
- SAFEGUARD G10: S73/variation authority is fact-specific;
- non-substantive guardrail (G1, G2);
- same-scope conflict surfacing;
- the real Astra regression cases.

In-memory-SQLite `session` fixture (tests/conftest.py). No OpenAI call.
"""
from __future__ import annotations

from app.db.models import Application, SchemeIntelligence, Site
from app.reporting.scheme_reconciliation import (
    DECIDED_GRANTED,
    DECIDED_RECOMMENDATION_ONLY,
    DECIDED_UNDETERMINED,
    FACT_CONFLICT,
    FACT_NOT_DETERMINED,
    FACT_RESOLVED,
    ROLE_CONDITION_DISCHARGE,
    ROLE_EIA_SCOPING,
    ROLE_EIA_SCREENING,
    ROLE_FULL,
    ROLE_NMC_AMENDMENT,
    ROLE_OUTLINE,
    ROLE_RESERVED_MATTERS,
    ROLE_S73_VARIATION,
    reconcile_scheme,
    resolve_decided_state,
    resolve_planning_role,
)


def _site(session, **kw) -> Site:
    s = Site(council_code="testcouncil", canonical_address="land at x", display_address="Land at X", **kw)
    session.add(s)
    session.commit()
    return s


def _app(session, site_id, reference, *, proposal="", application_type=None, status=None,
         decision=None, decision_issued_date=None, application_received="Mon 01 Jan 2024",
         estimated_unit_count=None) -> Application:
    a = Application(
        council_code="testcouncil", reference=reference, site_id=site_id, proposal=proposal,
        application_type=application_type, status=status, decision=decision,
        decision_issued_date=decision_issued_date, application_received=application_received,
        estimated_unit_count=estimated_unit_count,
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
    """Gate 2B-1 Defect 1 - Pennington's Stables (DC/091435): the proposal
    says 'Screening Request', not 'Screening Opinion', so the portal's own
    opinion-only classifier misses it and the residential wording would
    otherwise make it `full`."""
    site = _site(session)
    a = _app(session, site.id, "DC/091435",
             proposal="Town and Country Planning (Environmental Impact Assessment) Regulations 2017 "
                      "Screening Request: Residential development of up to 68 dwellings",
             decision="EIA Not Required", status="Decided")
    assert resolve_planning_role(a) == ROLE_EIA_SCREENING


def test_eia_screening_recognised_from_decision_value_alone(session):
    """A residential-worded proposal with no screening/scoping wording, but
    the formal decision 'EIA Not Required' - a value a substantive
    application never receives."""
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
    """The bare word 'screening' in an unrelated condition-discharge
    filing ('Television Reception Screening') must NOT be read as EIA
    screening."""
    site = _site(session)
    a = _app(session, site.id, "26/00082/PLCOND",
             proposal="Full Discharge Of Condition 22 (Television Reception Screening) Of Planning "
                      "Reference 24/00655/FUL",
             application_type="Approval of details reserved by a condition", status="Awaiting decision")
    assert resolve_planning_role(a) == ROLE_CONDITION_DISCHARGE


def test_penningtons_stables_screening_barred_from_all_substantive_facts(session):
    """The full Pennington's Stables shape: the screening request must not
    supply an operative permission, planning status, or residential
    quantum."""
    site = _site(session)
    scr = _app(session, site.id, "DC/091435",
               proposal="Town and Country Planning (Environmental Impact Assessment) Regulations 2017 "
                        "Screening Request: Residential development of up to 68 dwellings - Pennington's Stables",
               decision="EIA Not Required", status="Decided", decision_issued_date="Fri 03 May 2024")
    _intel(session, scr, total_units_final=68, core_intelligence_complete=True)
    r = reconcile_scheme([scr])
    assert [ra.role for ra in r.resolved_applications] == [ROLE_EIA_SCREENING]
    assert r.lead_application.state == FACT_NOT_DETERMINED
    assert r.operative_planning_status.state == FACT_NOT_DETERMINED
    assert r.operative_permission.state == FACT_NOT_DETERMINED
    assert r.residential.approved.state == FACT_NOT_DETERMINED
    assert r.residential.proposed.state == FACT_NOT_DETERMINED
    assert r.residential.residential_only.state == FACT_NOT_DETERMINED


def test_portal_application_type_field_is_authoritative(session):
    site = _site(session)
    # Proposal text alone looks like a full application; the portal's own
    # Application Type field says Reserved Matters.
    a = _app(session, site.id, "X/1", proposal="Erection of 200 dwellings with associated works",
             application_type="Reserved Matters")
    assert resolve_planning_role(a) == ROLE_RESERVED_MATTERS


def test_decided_state_overlay_never_collapses_recommendation_into_grant(session):
    site = _site(session)
    a = _app(session, site.id, "R/1", proposal="Erection of 50 dwellings",
             status="Recommendation Made", decision="Officer Recommendation: Approve")
    assert resolve_decided_state(a) == DECIDED_RECOMMENDATION_ONLY
    b = _app(session, site.id, "G/1", proposal="Erection of 50 dwellings",
             status="Decided", decision="Granted")
    assert resolve_decided_state(b) == DECIDED_GRANTED


# --- 2. lead / permission / status selection (not "most recent") ----------


def test_operative_selection_prefers_granted_substantive_over_newer_non_substantive(session):
    site = _site(session)
    granted = _app(session, site.id, "FUL/2020", proposal="Erection of 90 dwellings",
                   status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2020",
                   application_received="Mon 01 Jan 2019")
    _intel(session, granted, total_units_final=90, core_intelligence_complete=True)
    # A newer, fully-extracted discharge-of-conditions filing.
    doc = _app(session, site.id, "DOC/2025", proposal="Discharge of conditions 3-7 of permission FUL/2020",
               status="Decided", decision="Approved", application_received="Mon 01 Jan 2025")
    _intel(session, doc, total_units_final=90, core_intelligence_complete=True)

    r = reconcile_scheme([granted, doc])
    assert r.lead_application.value == "FUL/2020"
    assert r.operative_permission.value == "FUL/2020"
    assert r.operative_planning_status.value == "Permission granted"
    assert r.operative_planning_status.source.application_reference == "FUL/2020"


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
    r = reconcile_scheme([older, newer])
    # Both granted substantive; the later grant is operative, the earlier retained as superseded.
    assert r.operative_permission.value == "FUL/B"
    assert r.residential.approved.value == 44
    assert any(p.value == 40 for p in r.residential.superseded)


# --- 3. non-substantive guardrail (G1, G2) --------------------------------


def test_eia_screening_cannot_establish_permission_or_units(session):
    """Pennington's Stables."""
    site = _site(session)
    scr = _app(session, site.id, "SCR/1",
               proposal="Request for a screening opinion under the EIA Regulations for residential development of 60 homes",
               status="Decision Made", decision="EIA not required", decision_issued_date="Wed 01 Jan 2025")
    _intel(session, scr, total_units_final=60, core_intelligence_complete=True)
    r = reconcile_scheme([scr])
    assert r.lead_application.state == FACT_NOT_DETERMINED
    assert r.operative_planning_status.state == FACT_NOT_DETERMINED
    assert r.operative_permission.state == FACT_NOT_DETERMINED
    assert r.residential.approved.state == FACT_NOT_DETERMINED
    assert r.residential.proposed.state == FACT_NOT_DETERMINED


def test_condition_discharge_never_overwrites_the_underlying_unit_count(session):
    site = _site(session)
    perm = _app(session, site.id, "FUL/1", proposal="Erection of 100 dwellings",
                status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2022")
    _intel(session, perm, total_units_final=100)
    # A discharge filing whose own (misleadingly extracted) figure is different.
    doc = _app(session, site.id, "DOC/1", proposal="Discharge of condition 12 (landscaping) of FUL/1",
               status="Decided", decision="Approved", application_received="Mon 01 Jan 2024")
    _intel(session, doc, total_units_final=8)
    r = reconcile_scheme([perm, doc])
    assert r.residential.approved.value == 100
    assert r.residential.approved.source.application_reference == "FUL/1"


# --- 4. approved / proposed / superseded kept separate --------------------


def test_world_of_pets_superseded_figure_does_not_override_operative(session):
    """World of Pets: historic/wider 116 vs later approved 76."""
    site = _site(session)
    old = _app(session, site.id, "OUT/2016", proposal="Outline application for up to 116 dwellings",
               status="Decided", decision="Granted", decision_issued_date="Fri 01 Jan 2016",
               application_received="Mon 01 Jun 2015")
    _intel(session, old, total_units_final=116)
    new = _app(session, site.id, "FUL/2023", proposal="Erection of 76 dwellings",
               status="Decided", decision="Granted", decision_issued_date="Mon 02 Jan 2023",
               application_received="Mon 01 Jun 2022")
    _intel(session, new, total_units_final=76)
    r = reconcile_scheme([old, new])
    assert r.residential.approved.value == 76
    assert r.residential.approved.source.application_reference == "FUL/2023"
    assert [p.value for p in r.residential.superseded] == [116]


def test_proposed_and_approved_are_reported_independently(session):
    site = _site(session)
    granted = _app(session, site.id, "FUL/2019", proposal="Erection of 50 dwellings",
                   status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2020")
    _intel(session, granted, total_units_final=50)
    live = _app(session, site.id, "FUL/2025", proposal="Erection of 62 dwellings (resubmission)",
                status="Awaiting decision", application_received="Mon 01 Jan 2025")
    _intel(session, live, total_units_final=62)
    r = reconcile_scheme([granted, live])
    assert r.residential.approved.value == 50
    assert r.residential.proposed.value == 62
    assert r.residential.proposed.source.application_reference == "FUL/2025"


# --- 5. SAFEGUARD G9 - residential-only is not a new inference ------------


def test_stockport_rugby_club_declines_residential_only_where_specialist_component(session):
    """Stockport Rugby Club: ~60 homes + care/extra-care; never present an
    undifferentiated wider total as the housing opportunity, and never
    infer the split."""
    site = _site(session)
    app = _app(session, site.id, "HYB/1",
               proposal="Hybrid application: up to 60 dwellings plus a 70-bed extra care facility and associated works",
               status="Awaiting decision", application_received="Mon 01 Jan 2025")
    _intel(session, app, total_units_final=130, specialist_housing_type="Extra care (Use Class C2)",
           core_intelligence_complete=True)
    r = reconcile_scheme([app])
    assert r.residential.residential_only.state == FACT_NOT_DETERMINED
    assert "specialist" in r.residential.residential_only.reason.lower()
    # The wider all-use figure is preserved, not dropped.
    assert r.residential.all_use_total.state == FACT_RESOLVED
    assert r.residential.all_use_total.value == 130


def test_residential_only_resolves_when_no_specialist_component_evidenced(session):
    site = _site(session)
    app = _app(session, site.id, "FUL/1", proposal="Erection of 85 dwellings",
               status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2024")
    _intel(session, app, total_units_final=85)
    r = reconcile_scheme([app])
    assert r.residential.residential_only.state == FACT_RESOLVED
    assert r.residential.residential_only.value == 85


def test_no_new_inference_path_exists_for_residential_only(session):
    """The safeguard: a proposal that mentions a numeric care-bed figure
    inline must NOT trigger a derived subtraction - the module has no
    parser for that. It declines instead."""
    site = _site(session)
    app = _app(session, site.id, "FUL/1",
               proposal="Development comprising 90 houses and 25 extra care apartments",
               status="Awaiting decision")
    _intel(session, app, total_units_final=115)
    r = reconcile_scheme([app])
    assert r.residential.residential_only.state == FACT_NOT_DETERMINED


# --- 6. SAFEGUARD G10 - S73 authority is fact-specific -------------------


def test_s73_without_ah_evidence_does_not_control_affordable_housing(session):
    site = _site(session)
    perm = _app(session, site.id, "FUL/2020", proposal="Erection of 100 dwellings including 30% affordable housing",
                status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2020")
    _intel(session, perm, total_units_final=100, affordable_units_final=30, affordable_percentage_final=30.0,
           affordable_housing_status="legally_secured",
           affordable_housing_notes="35% secured via S106 dated 2020.")
    # Later S73 changes layout only - no AH figures extracted from it.
    s73 = _app(session, site.id, "FUL/2024", proposal="Variation of condition 2 (approved plans) of FUL/2020 to amend house types and layout",
               status="Decided", decision="Granted", decision_issued_date="Mon 01 Jan 2024",
               application_received="Mon 01 Jun 2023")
    _intel(session, s73, core_intelligence_complete=True)  # no total_units_final, no AH fields
    r = reconcile_scheme([perm, s73])
    ah = r.affordable_housing
    assert ah.whole_site is not None
    assert ah.whole_site.application_reference == "FUL/2020"
    assert ah.whole_site.status == "legally_secured"
    # S73 also does not control the approved unit count (no unit figure of its own).
    assert r.residential.approved.value == 100
    assert r.residential.approved.source.application_reference == "FUL/2020"


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
    r = reconcile_scheme([perm, s73])
    assert r.residential.approved.value == 108
    assert r.residential.approved.source.application_reference == "FUL/2024"
    assert any(p.value == 100 for p in r.residential.superseded)


# --- 7. affordable housing (reuse) + Burnage + Brixham + Hazelhurst ------


def test_burnage_technical_zero_never_silently_supplies_affordable_housing(session):
    """Former Burnage Cricket Club: platform showed 0 AH; permission
    evidence stated 13. A condition-discharge filing carrying 0 must not
    be the operative AH source."""
    site = _site(session)
    perm = _app(session, site.id, "FUL/1", proposal="Erection of 45 dwellings",
                status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2023")
    _intel(session, perm, total_units_final=45, affordable_units_final=13, affordable_percentage_final=29.0,
           affordable_housing_status="conditioned",
           affordable_housing_notes="13 affordable homes secured by condition.")
    doc = _app(session, site.id, "DOC/1", proposal="Discharge of condition 8 (drainage) of FUL/1",
               status="Decided", decision="Approved", application_received="Mon 01 Jan 2024")
    _intel(session, doc, affordable_units_final=0, affordable_percentage_final=0, affordable_housing_status="unknown")
    r = reconcile_scheme([perm, doc])
    assert r.affordable_housing.whole_site is not None
    assert r.affordable_housing.whole_site.units == 13
    assert r.affordable_housing.whole_site.application_reference == "FUL/1"


def test_brixham_road_same_scope_ah_conflict_is_surfaced(session):
    """Brixham Road: two credible same-scope AH positions that disagree
    and cannot be ranked -> surfaced, never silently picked."""
    site = _site(session)
    a = _app(session, site.id, "FUL/A", proposal="Erection of 100 dwellings",
             status="Awaiting decision")
    _intel(session, a, total_units_final=100, affordable_percentage_final=54.0, affordable_units_final=54,
           affordable_housing_status="proposed")
    b = _app(session, site.id, "FUL/B", proposal="Erection of 100 dwellings (revised)",
             status="Awaiting decision", application_received="Mon 02 Jan 2024")
    _intel(session, b, total_units_final=100, affordable_percentage_final=40.0, affordable_units_final=40,
           affordable_housing_status="proposed")
    r = reconcile_scheme([a, b])
    assert r.affordable_housing.conflicts, "expected a surfaced same-scope AH conflict"


def test_hazelhurst_farm_phase_and_whole_site_ah_stay_distinct(session):
    """Hazelhurst Farm: phase-specific vs wider-site AH obligation must
    not be flattened."""
    site = _site(session)
    outline = _app(session, site.id, "OUT/1", proposal="Outline application for up to 300 dwellings across the site",
                   status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2020")
    _intel(session, outline, total_units_final=300, affordable_percentage_final=30.0, affordable_units_final=90,
           affordable_housing_status="legally_secured")
    ph1 = _app(session, site.id, "RM/1", proposal="Reserved matters for Phase 1 comprising 100 dwellings",
               status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2022")
    _intel(session, ph1, total_units_final=100, affordable_percentage_final=100.0, affordable_units_final=100,
           affordable_housing_status="conditioned")
    r = reconcile_scheme([outline, ph1])
    ah = r.affordable_housing
    assert ah.whole_site is not None
    assert any(p.scope_label.lower().startswith("phase 1") for p in ah.phases)
    # distinct positions, not one flattened headline
    assert ah.whole_site.percentage == 30.0
    assert any(p.percentage == 100.0 for p in ah.phases)


# --- 8. general guardrails -----------------------------------------------


def test_not_determined_where_no_substantive_application_exists(session):
    site = _site(session)
    doc = _app(session, site.id, "DOC/1", proposal="Discharge of condition 4 of an unknown permission",
               status="Decided", decision="Approved")
    nma = _app(session, site.id, "NMA/1", proposal="Non-material amendment", status="Decided", decision="Approved")
    r = reconcile_scheme([doc, nma])
    assert r.operative_planning_status.state == FACT_NOT_DETERMINED
    assert r.residential.approved.state == FACT_NOT_DETERMINED
    assert r.lead_application.state == FACT_NOT_DETERMINED


def test_every_resolved_fact_carries_provenance_and_reason(session):
    site = _site(session)
    a = _app(session, site.id, "FUL/1", proposal="Erection of 70 dwellings",
             status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2024")
    _intel(session, a, total_units_final=70)
    r = reconcile_scheme([a])
    for fact in (r.lead_application, r.operative_planning_status, r.operative_permission,
                 r.residential.approved, r.residential.residential_only):
        if fact.state == FACT_RESOLVED:
            assert fact.source is not None
            assert fact.source.application_reference
            assert fact.source.planning_role
            assert fact.reason
            assert fact.confidence in ("high", "medium", "low")


def test_reconciliation_does_not_touch_application_category(session):
    """planning_role is derived, application_category is untouched."""
    site = _site(session)
    a = _app(session, site.id, "FUL/1", proposal="Erection of 70 dwellings", status="Awaiting decision")
    a.application_category = "primary_residential"
    session.commit()
    reconcile_scheme([a])
    session.refresh(a)
    assert a.application_category == "primary_residential"


def test_london_road_operative_state_not_generic_recency(session):
    """London Road / Victoria House / Hopes Carr shape: the newest, most
    fully-extracted application is a non-substantive amendment; the
    operative planning state must come from the substantive permission."""
    site = _site(session)
    perm = _app(session, site.id, "FUL/2021", proposal="Erection of 109 dwellings",
                status="Decided", decision="Granted", decision_issued_date="Wed 01 Jan 2022",
                application_received="Mon 01 Jan 2021")
    _intel(session, perm, total_units_final=109, core_intelligence_complete=True)
    nma = _app(session, site.id, "NMA/2025", proposal="Non-material amendment to FUL/2021 (window alterations)",
               status="Decided", decision="Approved", application_received="Mon 01 Jun 2025")
    _intel(session, nma, core_intelligence_complete=True)
    r = reconcile_scheme([perm, nma])
    assert r.lead_application.value == "FUL/2021"
    assert r.operative_planning_status.value == "Permission granted"
    assert r.residential.approved.value == 109
