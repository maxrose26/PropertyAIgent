"""Gate 2B-2B.2 ("Acquisition Opportunity Scope Alignment") - tests for the
narrow migration of undeveloped-phase acquisition-opportunity generation
onto Gate 2B-2A's existing operative-scope semantics
(group_applications_by_operative_scope / is_material_development_parcel),
plus the accompanying phase-specific unit_count correction in
app.reporting.opportunity_universe._planning_delivery_universe.

Two confirmed production defects are covered here (read-only architecture
investigation, then this implementation):

1. An individual dwelling plot citation (almost always a
   variation_or_amendment/NMA filing naming one or more specific plot
   numbers) could become its own standalone acquisition opportunity,
   inheriting the WHOLE SITE's own unit_count as if it were that plot's
   own quantum (confirmed real cases: Lacy Street "Plot 25" inheriting the
   site's 53 homes, Barton Road "Plot 10"/"Plot 43" inheriting 57, World
   of Pets "Plot 12", Church Wharf "Plot O1", Strawberry Hill "Plot A5",
   Enterprise Centre "Plot 2").

2. Even a GENUINE, named development phase's own acquisition opportunity
   carried the whole site's rep-derived unit_count rather than that
   phase's own deterministically-supported quantum (confirmed real case:
   a Reserved-Matters-documented 140-unit "Phase 1" whose live opportunity
   nonetheless carried an unrelated 26-unit whole-site-derived figure).

Fixtures below are synthetic (never real production data), shaped to
reproduce each confirmed real-world pattern exactly, including the
specific application_category / application_received timing that decides
whether a folded whole-site scope reads "approved_not_started" (Lacy
Street's own shape - the false plot's own NMA predates its site's grant,
so folding it in doesn't inject a fresh progress signal) or "underway"
(Barton Road's own shape - the false plot's own NMA postdates the grant,
so folding it in correctly surfaces evidence the whole site has, in fact,
already started - resolving the "underway-vs-plot" contradiction rather
than merely suppressing it).

Uses the same in-memory-SQLite `session` fixture as the rest of this
suite (tests/conftest.py). No OpenAI call anywhere.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from app.db.models import Application, OpportunityMonitoringState, Site, SchemeIntelligence
from app.pipeline.phase_tracking import (
    UNPHASED_LABEL,
    build_acquisition_scope_breakdown,
    build_phase_breakdown,
    group_applications_by_operative_scope,
    is_material_development_parcel,
)
from app.policy.buyer_matching import assess_buyer_fit
from app.policy.buyer_profiles import NESTEN_HOMES
from app.reporting.dashboard import _undeveloped_phase_cards
from app.reporting.opportunity_change import sync_opportunity_monitoring_state
from app.reporting.opportunity_universe import (
    build_current_opportunity_universe,
    planning_delivery_phase_opportunity_id,
)


def _site(session, **kw) -> Site:
    kw.setdefault("display_address", "Land at Test Site")
    kw.setdefault("canonical_address", "land at test site")
    s = Site(council_code="testcouncil", **kw)
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


def _phase_card(cards: list[dict], suffix: str) -> dict | None:
    return next((c for c in cards if c["id"].endswith(f"-{suffix}") or c["id"].rsplit("-", 1)[-1] == suffix), None)


# --- 1/6. Lacy Street shape: false plot removed, replaced by a legitimate --
#          whole-site "approved, not started" opportunity (the plot's own
#          NMA predates the site's grant, so folding it injects no fresh
#          progress evidence) --------------------------------------------


def test_lacy_street_shape_plot_25_does_not_survive_as_its_own_opportunity(session):
    site = _site(session, display_address="Lacy Street shape")
    main = _app(
        session, site.id, "FUL/1",
        proposal="Erection of 53 dwellings", decision="Approve with Conditions",
        decision_issued_date="Mon 01 Apr 2024", application_received="Mon 01 Jan 2024",
    )
    _intel(session, main, total_units_final=53, core_intelligence_complete=True)
    _app(
        session, site.id, "NMA/1", application_category="variation_or_amendment",
        proposal="Non-material amendment for the omission of Plot 25, end unit of Block 8",
        decision="Approve with Conditions", decision_issued_date="Mon 01 Feb 2024",
        application_received="Mon 01 Jan 2024",  # BEFORE the whole-site grant - no fresh progress signal
    )

    cards = _undeveloped_phase_cards(session, None)
    assert not _phase_card(cards, "25"), "Plot 25 must not survive as its own acquisition-scope card"

    universe = build_current_opportunity_universe(session)
    ids = {r.opportunity_id for r in universe}
    assert planning_delivery_phase_opportunity_id(site.id, "25") not in ids


def test_lacy_street_shape_folds_into_a_legitimate_whole_site_opportunity_instead(session):
    """The false plot identity disappears, but the site's own genuine
    "approved, not started" status - previously invisible, hidden behind
    the false Plot 25 identity - correctly surfaces as its own, valid
    whole-site opportunity (Section 6's own "IDs replaced by different
    valid scope IDs" expectation)."""
    site = _site(session, display_address="Lacy Street shape")
    main = _app(
        session, site.id, "FUL/1",
        proposal="Erection of 53 dwellings", decision="Approve with Conditions",
        decision_issued_date="Mon 01 Apr 2024", application_received="Mon 01 Jan 2024",
    )
    _intel(session, main, total_units_final=53, core_intelligence_complete=True)
    _app(
        session, site.id, "NMA/1", application_category="variation_or_amendment",
        proposal="Non-material amendment for the omission of Plot 25, end unit of Block 8",
        decision="Approve with Conditions", decision_issued_date="Mon 01 Feb 2024",
        application_received="Mon 01 Jan 2024",
    )

    cards = _undeveloped_phase_cards(session, None)
    whole_site_card = _phase_card(cards, UNPHASED_LABEL)
    assert whole_site_card is not None
    assert whole_site_card["params"]["site_id"] == str(site.id)

    universe = build_current_opportunity_universe(session)
    by_id = {r.opportunity_id: r for r in universe}
    whole_site_id = planning_delivery_phase_opportunity_id(site.id, UNPHASED_LABEL)
    assert whole_site_id in by_id
    # "Whole site / unphased" keeps the existing rep-derived unit_count -
    # there is only one real scope on this site, so 53 IS correctly this
    # opportunity's own quantum, not an inherited figure from elsewhere.
    assert by_id[whole_site_id].fingerprint_fields["unit_count"] == 53


# --- 2. Barton Road shape: false plot removed, whole-site "underway" -------
#        state preserved and never contradicted (the plot's own NMA
#        postdates the grant, so folding it correctly surfaces real
#        evidence the site has already started) -----------------------------


def test_barton_road_shape_plot_10_does_not_survive_and_underway_state_is_never_contradicted(session):
    site = _site(session, display_address="Barton Road shape")
    main = _app(
        session, site.id, "FUL/1",
        proposal="Erection of 57 dwellings", decision="Approve with Conditions",
        decision_issued_date="Mon 01 Jan 2024", application_received="Mon 01 Dec 2023",
    )
    _intel(session, main, total_units_final=57, core_intelligence_complete=True)
    _app(
        session, site.id, "NMA/1", application_category="variation_or_amendment",
        proposal="Non-material amendment to the planning layout to include a re-sited bin store, plot 10",
        decision="Approve with Conditions", decision_issued_date="Mon 01 Jun 2024",
        application_received="Mon 01 Jun 2024",
    )
    # A separate, genuine post-grant condition-discharge filing - real
    # evidence the WHOLE SITE has started, independent of the plot-10
    # citation above (mirrors Barton Road's own real 11-application shape,
    # where several later condition-discharge filings exist alongside the
    # plot-citing NMA).
    _app(
        session, site.id, "CND/1", application_category="condition_discharge_or_details",
        proposal="Full discharge of conditions", decision="Full discharge of conditions",
        decision_issued_date="Mon 01 Aug 2024", application_received="Mon 01 Aug 2024",
    )

    cards = _undeveloped_phase_cards(session, None)
    assert not _phase_card(cards, "10"), "Plot 10 must not survive as its own acquisition-scope card"
    # No replacement whole-site "undeveloped" card either - the site's own
    # resolved status is genuinely underway, so it correctly produces NO
    # undeveloped_phase card at all, never a contradiction of that state.
    assert not any(c["params"]["site_id"] == str(site.id) for c in cards)

    universe = build_current_opportunity_universe(session)
    ids = {r.opportunity_id for r in universe}
    assert planning_delivery_phase_opportunity_id(site.id, "10") not in ids
    assert planning_delivery_phase_opportunity_id(site.id, UNPHASED_LABEL) not in ids


# --- 3. Barton Road latent "Plot 43" shape: a single application citing ----
#        two distinct plot codes - neither may surface standalone under
#        the acquisition-scope grouping, regardless of the existing
#        single-card-per-site display limitation (explicitly deferred,
#        Section V/17 - not addressed by this gate) -------------------------


def test_barton_road_latent_plot_43_shape_neither_code_survives_under_operative_scope(session):
    site = _site(session, display_address="Barton Road latent Plot 43 shape")
    main = _app(
        session, site.id, "FUL/1", proposal="Erection of 57 dwellings",
        decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024",
    )
    _intel(session, main, total_units_final=57, core_intelligence_complete=True)
    nma = _app(
        session, site.id, "NMA/1", application_category="variation_or_amendment",
        proposal="Amendments to the planning layout to include a re-sited bin store, plot 10; "
                 "and reconfiguration works affecting plot 43",
        decision="Approve with Conditions", decision_issued_date="Mon 01 Jun 2024",
    )

    groups = group_applications_by_operative_scope([main, nma])
    assert ("10", "plot") not in groups
    assert ("43", "plot") not in groups

    breakdown = build_acquisition_scope_breakdown([main, nma])
    codes = {row["code"] for row in breakdown}
    assert "10" not in codes
    assert "43" not in codes


# --- 4/5/7. World of Pets / Church Wharf / Enterprise Centre shapes: -------
#            a single non-material plot citation folds and never becomes
#            its own standalone acquisition opportunity ---------------------


def test_world_of_pets_shape_multi_plot_citation_folds_not_standalone(session):
    site = _site(session, display_address="World of Pets shape")
    main = _app(session, site.id, "FUL/1", proposal="Erection of 8 dwellings",
                decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024")
    _intel(session, main, total_units_final=8, core_intelligence_complete=True)
    _app(session, site.id, "NMA/1", application_category="variation_or_amendment",
         proposal="Non-material amendment for Plots 21-24 drives", decision="Approve with Conditions",
         decision_issued_date="Mon 01 Feb 2024", application_received="Mon 01 Jan 2024")

    cards = _undeveloped_phase_cards(session, None)
    assert not _phase_card(cards, "21")
    universe = build_current_opportunity_universe(session)
    ids = {r.opportunity_id for r in universe}
    assert planning_delivery_phase_opportunity_id(site.id, "21") not in ids


def test_church_wharf_shape_lettered_plot_code_folds_not_standalone(session):
    site = _site(session, display_address="Church Wharf shape")
    main = _app(session, site.id, "FUL/1", proposal="Erection of 398 dwellings",
                decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024")
    _intel(session, main, total_units_final=398, core_intelligence_complete=True)
    _app(session, site.id, "NMA/1", application_category="variation_or_amendment",
         proposal="Non-material amendment - reconfiguration of four ground floor residential units, plot O1",
         decision="Approve with Conditions", decision_issued_date="Mon 01 Feb 2024",
         application_received="Mon 01 Jan 2024")

    cards = _undeveloped_phase_cards(session, None)
    assert not _phase_card(cards, "O1")
    universe = build_current_opportunity_universe(session)
    ids = {r.opportunity_id for r in universe}
    assert planning_delivery_phase_opportunity_id(site.id, "O1") not in ids


def test_enterprise_centre_shape_plot_folds_not_standalone(session):
    site = _site(session, display_address="Enterprise Centre shape")
    main = _app(session, site.id, "FUL/1", proposal="Erection of 23 dwellings",
                decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024")
    _intel(session, main, total_units_final=23, core_intelligence_complete=True)
    _app(session, site.id, "NMA/1", application_category="variation_or_amendment",
         proposal="Non-material amendment to amend the siting of the local plot 2 bin store",
         decision="Approve with Conditions", decision_issued_date="Mon 01 Feb 2024",
         application_received="Mon 01 Jan 2024")

    cards = _undeveloped_phase_cards(session, None)
    assert not _phase_card(cards, "2")
    universe = build_current_opportunity_universe(session)
    ids = {r.opportunity_id for r in universe}
    assert planning_delivery_phase_opportunity_id(site.id, "2") not in ids


# --- 8/9. Beal Lane shape: genuine documented phase survives with the ------
#          SAME opportunity ID and its OWN phase-specific unit_count,
#          never the whole site's unrelated rep-derived figure --------------


def test_beal_lane_shape_phase_1_survives_with_its_own_140_unit_quantum_not_26(session):
    site = _site(session, display_address="Beal Lane shape")
    outline = _app(session, site.id, "OUT/1", proposal="Outline application for up to 400 dwellings",
                    decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2023")
    _intel(session, outline, total_units_final=26, core_intelligence_complete=True)  # unrelated whole-site rep figure
    rm_phase1 = _app(session, site.id, "RES/1", application_category="reserved_matters",
                      proposal="Reserved matters application for Phase 1 of a residential scheme",
                      decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024",
                      application_received="Mon 15 Dec 2023")
    _intel(session, rm_phase1, total_units_final=140)

    cards = _undeveloped_phase_cards(session, None)
    phase1_card = _phase_card(cards, "1")
    assert phase1_card is not None
    assert phase1_card["phase_unit_count"] == 140

    universe = build_current_opportunity_universe(session)
    by_id = {r.opportunity_id: r for r in universe}
    phase1_id = planning_delivery_phase_opportunity_id(site.id, "1")
    assert phase1_id in by_id
    assert by_id[phase1_id].fingerprint_fields["unit_count"] == 140
    assert by_id[phase1_id].fingerprint_fields["unit_count"] != 26
    assert by_id[phase1_id].matching_facts.unit_count == 140


# --- 10/11. Woodford shape: two genuine documented phases on the same ------
#            site both survive, each with its OWN phase-specific quantum ---


def test_woodford_shape_two_documented_phases_both_survive_with_their_own_quantum(session):
    """Reproduces the real Woodford Aerodrome shape as two SEPARATE Site
    rows (confirmed in production: opportunities `phase:62:H4` and
    `phase:67:3B` belong to two different site_ids, not two phases of one
    site) - each site has its own single documented phase, and
    _undeveloped_phase_cards' existing one-card-per-site behaviour (Section
    17's own "Multi-phase opportunity completeness", explicitly deferred
    and unchanged by this gate) is therefore not in play here at all."""
    site_h4 = _site(session, display_address="Woodford Aerodrome shape - H4")
    outline_h4 = _app(session, site_h4.id, "OUT/H4", proposal="Outline permission for the wider masterplan",
                       decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2020")
    _intel(session, outline_h4, total_units_final=None, core_intelligence_complete=True)
    rm_h4 = _app(session, site_h4.id, "DC/H4", application_category="reserved_matters",
                 proposal="Reserved matters approval for infrastructure phase H4",
                 decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024",
                 application_received="Mon 15 Dec 2023")
    _intel(session, rm_h4, total_units_final=372)

    site_3b = _site(session, display_address="Woodford Aerodrome shape - 3B")
    outline_3b = _app(session, site_3b.id, "OUT/3B", proposal="Outline permission for the wider masterplan",
                       decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2020")
    _intel(session, outline_3b, total_units_final=None, core_intelligence_complete=True)
    rm_3b = _app(session, site_3b.id, "DC/3B", application_category="reserved_matters",
                 proposal="Reserved Matters approval pursuant to outline permission for phase 3B",
                 decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024",
                 application_received="Mon 15 Dec 2023")
    _intel(session, rm_3b, total_units_final=295)

    universe = build_current_opportunity_universe(session)
    by_id = {r.opportunity_id: r for r in universe}
    h4_id = planning_delivery_phase_opportunity_id(site_h4.id, "H4")
    b3_id = planning_delivery_phase_opportunity_id(site_3b.id, "3B")
    assert h4_id in by_id and by_id[h4_id].fingerprint_fields["unit_count"] == 372
    assert b3_id in by_id and by_id[b3_id].fingerprint_fields["unit_count"] == 295


# --- 12. Acceptance case: a genuine material development parcel named -----
#         "Plot" survives as its own acquisition opportunity ----------------


def test_genuine_material_development_parcel_with_plot_wording_survives(session):
    site = _site(session, display_address="Material parcel shape")
    outline = _app(session, site.id, "OUT/1", proposal="Outline permission for the wider masterplan",
                    decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2020")
    _intel(session, outline, total_units_final=None, core_intelligence_complete=True)
    material_plot = _app(session, site.id, "FUL/PLOT1", application_category="primary_residential",
                          proposal="Hybrid application for Plot 1 - erection of 120 dwellings",
                          decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024",
                          application_received="Mon 15 Dec 2023")
    _intel(session, material_plot, total_units_final=120)

    apps = [outline, material_plot]
    groups = group_applications_by_operative_scope(apps)
    assert ("1", "plot") in groups
    assert is_material_development_parcel(groups[("1", "plot")]) is True

    cards = _undeveloped_phase_cards(session, None)
    plot_card = _phase_card(cards, "1")
    assert plot_card is not None
    assert plot_card["phase_unit_count"] == 120

    universe = build_current_opportunity_universe(session)
    by_id = {r.opportunity_id: r for r in universe}
    plot_id = planning_delivery_phase_opportunity_id(site.id, "1")
    assert plot_id in by_id
    assert by_id[plot_id].fingerprint_fields["unit_count"] == 120


# --- 13. A genuine phase with an unknown own quantum receives None, -------
#         never the parent scheme's total ------------------------------------


def test_genuine_phase_with_unknown_own_quantum_receives_none_not_parent_total(session):
    site = _site(session, display_address="Unknown-quantum phase shape")
    outline = _app(session, site.id, "OUT/1", proposal="Outline permission for 267 dwellings",
                    decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2020")
    _intel(session, outline, total_units_final=267, core_intelligence_complete=True)
    # A genuine, single-labelled Phase 1 Reserved Matters GRANT (its own
    # real approval, not a fallback progress-signal filing) that states no
    # unit count of its own anywhere - and carries no SchemeIntelligence at
    # all, so _phase_unit_count's document-based and portal-text branches
    # both correctly find nothing (mirrors the real Mount Road/Wilmslow
    # Road production shapes, where several genuine phases carry no
    # independent documented figure at all).
    rm_phase1 = _app(session, site.id, "RES/1", application_category="reserved_matters",
                      proposal="Reserved matters application relating to Phase 1 - landscaping and external "
                               "appearance only",
                      decision="Approve with Conditions", decision_issued_date="Mon 01 Jun 2024",
                      application_received="Mon 01 May 2024")

    cards = _undeveloped_phase_cards(session, None)
    phase1_card = _phase_card(cards, "1")
    assert phase1_card is not None
    assert phase1_card["phase_unit_count"] is None

    universe = build_current_opportunity_universe(session)
    by_id = {r.opportunity_id: r for r in universe}
    phase1_id = planning_delivery_phase_opportunity_id(site.id, "1")
    assert phase1_id in by_id
    assert by_id[phase1_id].fingerprint_fields["unit_count"] is None
    assert by_id[phase1_id].fingerprint_fields["unit_count"] != 267
    assert by_id[phase1_id].matching_facts.unit_count is None


# --- 14. Whole-site/unphased opportunities remain unaffected ---------------


def test_whole_site_unphased_opportunity_unaffected_when_plot_citations_are_non_material(session):
    """Mirrors the real "Land Off Crabtree Lane" production shape (Site
    484): a whole-site scheme plus two non-material plot citations. The
    RAW grouping already has >=2 groups (so this site was always a
    candidate for this detector, both before and after this gate), and
    after folding, the resolved whole-site bucket's own status/unit_count
    is completely unaffected - this confirms the fix restores full
    backward compatibility for this shape, not just avoids regressing it."""
    site = _site(session, display_address="Genuinely unphased site")
    main = _app(session, site.id, "FUL/1", proposal="Erection of 194 dwellings",
                decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024",
                application_received="Mon 01 Dec 2023")
    _intel(session, main, total_units_final=194, core_intelligence_complete=True)
    _app(session, site.id, "NMA/17", application_category="variation_or_amendment",
         proposal="Non-material amendment relating to plot 17 boundary treatment",
         decision="Approve with Conditions", decision_issued_date="Mon 01 Feb 2024",
         application_received="Mon 01 Jan 2024")
    _app(session, site.id, "NMA/18", application_category="variation_or_amendment",
         proposal="Non-material amendment relating to plot 18 boundary treatment",
         decision="Approve with Conditions", decision_issued_date="Mon 01 Feb 2024",
         application_received="Mon 01 Jan 2024")

    cards = _undeveloped_phase_cards(session, None)
    whole_site_card = _phase_card(cards, UNPHASED_LABEL)
    assert whole_site_card is not None

    universe = build_current_opportunity_universe(session)
    by_id = {r.opportunity_id: r for r in universe}
    whole_site_id = planning_delivery_phase_opportunity_id(site.id, UNPHASED_LABEL)
    assert whole_site_id in by_id
    assert by_id[whole_site_id].fingerprint_fields["unit_count"] == 194


# --- 15. Removing a false plot never changes a surviving sibling's --------
#         fingerprint ---------------------------------------------------------


def test_removing_false_plot_does_not_change_a_surviving_genuine_phase_sibling_fingerprint(session):
    site = _site(session, display_address="Sibling fingerprint independence shape")
    outline = _app(session, site.id, "OUT/1", proposal="Outline permission for the wider masterplan",
                    decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2020")
    _intel(session, outline, total_units_final=None, core_intelligence_complete=True)
    rm_phase1 = _app(session, site.id, "RES/1", application_category="reserved_matters",
                      proposal="Reserved matters application for Phase 1 of a residential scheme",
                      decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024",
                      application_received="Mon 15 Dec 2023")
    _intel(session, rm_phase1, total_units_final=140)

    universe_before = build_current_opportunity_universe(session)
    phase1_id = planning_delivery_phase_opportunity_id(site.id, "1")
    fp_before = next(r.fingerprint_fields for r in universe_before if r.opportunity_id == phase1_id)

    # Now add a false, non-material plot citation to the SAME site - not
    # yet decided, so it cannot shift compute_lapse_status's own whole-
    # site "latest grant" pick (a pre-existing, unrelated sensitivity of
    # that function to ANY new grant on the site, not something this
    # gate changes) - isolating this test to the one thing it is actually
    # checking: fingerprint independence between sibling opportunity IDs.
    _app(session, site.id, "NMA/PLOT9", application_category="variation_or_amendment",
         proposal="Non-material amendment relating to plot 9 bin store", decision="Awaiting decision",
         decision_issued_date=None, application_received="Mon 15 Dec 2023")

    universe_after = build_current_opportunity_universe(session)
    plot9_id = planning_delivery_phase_opportunity_id(site.id, "9")
    assert plot9_id not in {r.opportunity_id for r in universe_after}  # confirms it never became live at all
    fp_after = next(r.fingerprint_fields for r in universe_after if r.opportunity_id == phase1_id)
    assert fp_after == fp_before


# --- 16. No unrelated planning_delivery opportunity kind is affected -------


def test_site_kind_opportunity_fingerprint_has_no_phase_specific_fields(session):
    """A pure sanity/regression check on the code structure itself: only
    the "phase" tag branch in _planning_delivery_universe ever sets
    phase_code/applies the phase-specific unit_count override - "site"
    kind (app.reporting.dashboard._approaching_lapse_cards) is untouched
    by this gate's change, and its fingerprint_fields must never carry a
    phase_code key regardless of what plot/phase citations exist
    elsewhere on the same site."""
    site = _site(session, display_address="Approaching lapse + plot citation shape")
    # Chosen so the 3-year commencement deadline lands 90 days from today -
    # inside LAPSE_WARNING_DAYS (180), so compute_lapse_status resolves to
    # "approaching" (the one status _approaching_lapse_cards accepts).
    target_deadline = dt.date.today() + dt.timedelta(days=90)
    decision_date = target_deadline.replace(year=target_deadline.year - 3)
    grant_date = decision_date.strftime("%a %d %b %Y")
    received_before_grant = (decision_date - dt.timedelta(days=30)).strftime("%a %d %b %Y")
    main = _app(session, site.id, "FUL/1", proposal="Erection of 30 dwellings",
                decision="Approve with Conditions", decision_issued_date=grant_date,
                application_received=received_before_grant)
    _intel(session, main, total_units_final=30, core_intelligence_complete=True)
    # Not yet decided, and received BEFORE the grant - a plot citation that
    # cannot itself read as post-grant progress evidence and flip the
    # whole site to "underway" (classify_build_status's own, unrelated
    # sensitivity to any post-grant progress-signal filing).
    _app(session, site.id, "NMA/1", application_category="variation_or_amendment",
         proposal="Non-material amendment relating to plot 4", decision="Awaiting decision",
         decision_issued_date=None, application_received=received_before_grant)

    universe = build_current_opportunity_universe(session)
    site_id_opp = next((r for r in universe if r.opportunity_id == f"planning_delivery:site:{site.id}"), None)
    assert site_id_opp is not None
    assert "phase_code" not in site_id_opp.fingerprint_fields


# --- 17. OpportunityMonitoringState rows are never deleted by universe -----
#         construction, even for a false plot that stops being emitted -----


def test_opportunity_monitoring_state_rows_are_never_deleted_for_a_removed_false_plot(session):
    site = _site(session, display_address="Monitoring history shape")
    main = _app(session, site.id, "FUL/1", proposal="Erection of 53 dwellings",
                decision="Approve with Conditions", decision_issued_date="Mon 01 Apr 2024")
    _intel(session, main, total_units_final=53, core_intelligence_complete=True)
    nma = _app(session, site.id, "NMA/1", application_category="variation_or_amendment",
               proposal="Non-material amendment for the omission of Plot 25",
               decision="Approve with Conditions", decision_issued_date="Mon 01 Feb 2024",
               application_received="Mon 01 Jan 2024")

    # Simulate a HISTORICAL sync from before this gate's fix, where the
    # false plot was still live and monitored.
    fake_fingerprint = "0" * 64
    session.add(OpportunityMonitoringState(
        opportunity_id=planning_delivery_phase_opportunity_id(site.id, "25"),
        opportunity_type="planning_delivery", fingerprint=fake_fingerprint,
        first_seen_at=dt.datetime.now(dt.timezone.utc), last_seen_at=dt.datetime.now(dt.timezone.utc),
    ))
    session.commit()

    stats = sync_opportunity_monitoring_state(session)

    row = session.execute(
        select(OpportunityMonitoringState).where(
            OpportunityMonitoringState.opportunity_id == planning_delivery_phase_opportunity_id(site.id, "25")
        )
    ).scalar_one_or_none()
    assert row is not None, "the historical monitoring row must never be deleted"
    assert row.fingerprint == fake_fingerprint, "a row for an opportunity no longer live must stop refreshing, not be rewritten"


# --- Buyer Matching impact: the corrected phase-specific unit_count -------
#     (or None) reaches Buyer Matching, never the whole-site figure --------


def test_buyer_matching_receives_the_corrected_phase_specific_unit_count(session):
    site = _site(session, display_address="Buyer matching impact shape")
    outline = _app(session, site.id, "OUT/1", proposal="Outline permission for the wider masterplan",
                    decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2020")
    _intel(session, outline, total_units_final=26, core_intelligence_complete=True)
    rm_phase1 = _app(session, site.id, "RES/1", application_category="reserved_matters",
                      proposal="Reserved matters application for Phase 1 of a residential scheme",
                      decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024",
                      application_received="Mon 15 Dec 2023")
    _intel(session, rm_phase1, total_units_final=140)

    universe = build_current_opportunity_universe(session)
    phase1_id = planning_delivery_phase_opportunity_id(site.id, "1")
    record = next(r for r in universe if r.opportunity_id == phase1_id)

    assert record.matching_facts.unit_count == 140
    assessment = assess_buyer_fit(NESTEN_HOMES, record.matching_facts)
    assert assessment is not None  # the corrected fact reaches buyer fit reasoning without error
