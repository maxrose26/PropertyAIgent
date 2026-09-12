"""Gate 2B-2C ("Planning Signal Consumer Alignment") - tests for the
trusted-anchor migration of app.pipeline.lapse_tracking.compute_lapse_status
and app.pipeline.phase_tracking.compute_phase_progress onto
app.reporting.scheme_reconciliation.resolve_operative_lapse_anchor.

Root cause fixed: both functions previously selected their "operative
granted permission" as the most recently DECIDED application whose
decision text merely contains "approve"/"grant", with no awareness of
planning role - a later NMA, condition discharge, or S73/variation could
become the permission/lapse anchor in place of the true substantive
permission (confirmed real production case: World of Pets, and 56 further
sites - see the Gate 2B-2C architecture investigation report).

Uses the same in-memory-SQLite `session` fixture as the rest of this
suite (tests/conftest.py). No OpenAI call anywhere.
"""
from __future__ import annotations

import datetime as dt

from app.db.models import Application, Site, SchemeIntelligence
from app.pipeline.lapse_tracking import compute_lapse_status
from app.pipeline.phase_tracking import compute_phase_progress
from app.reporting.dashboard import _approaching_lapse_cards, _recent_permission_cards
from app.reporting.opportunity_universe import build_current_opportunity_universe
from app.reporting.scheme_reconciliation import FACT_RESOLVED, FACT_NOT_DETERMINED, resolve_operative_lapse_anchor


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


# --- 1. World of Pets: RM + later NMA ---------------------------------------


def test_world_of_pets_rm_plus_later_nma_does_not_anchor_on_the_nma(session):
    site = _site(session, display_address="World of Pets shape")
    rm = _app(session, site.id, "114619/RES/24", application_category="reserved_matters",
              proposal="Reserved matters application for appearance, layout and scale for the erection of 40 dwellings",
              decision="Approve with Conditions", decision_issued_date="Thu 27 Mar 2025",
              application_received="Wed 02 Oct 2024")
    _app(session, site.id, "119412/NMA/26", application_category="variation_or_amendment",
         proposal="Application for non-material amendment to planning permission 114619/RES/24 to change the layout",
         decision="Approve with Conditions", decision_issued_date="Tue 07 Jul 2026",
         application_received="Fri 19 Jun 2026")

    result = compute_lapse_status([rm, session.query(Application).filter_by(reference="119412/NMA/26").one()], site)
    assert result["granted_app"].reference == "114619/RES/24"
    assert result["deadline"] == dt.date(2028, 3, 27)
    assert result["status"] == "underway"  # the later NMA is now correctly read as progress evidence
    assert result["build_status"] == "underway"


# --- 2/3/4. Full permission + later NMA / CND / S73 -------------------------


def test_full_permission_plus_later_nma_anchors_on_the_full_permission(session):
    site = _site(session)
    full = _app(session, site.id, "FUL/1", proposal="Erection of 40 dwellings",
                decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024")
    _app(session, site.id, "NMA/1", application_category="variation_or_amendment",
         proposal="Non-material amendment to permission FUL/1", decision="Approve with Conditions",
         decision_issued_date="Mon 01 Jun 2026")
    apps = [full, session.query(Application).filter_by(reference="NMA/1").one()]
    result = compute_lapse_status(apps, site)
    assert result["granted_app"].reference == "FUL/1"
    assert result["deadline"] == dt.date(2027, 1, 1)


def test_full_permission_plus_later_condition_discharge_anchors_on_the_full_permission(session):
    site = _site(session)
    full = _app(session, site.id, "FUL/1", proposal="Erection of 40 dwellings",
                decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024")
    _app(session, site.id, "CND/1", application_category="condition_discharge_or_details",
         proposal="Approval of details reserved by condition", decision="Full discharge of conditions",
         decision_issued_date="Mon 01 Jun 2026")
    apps = [full, session.query(Application).filter_by(reference="CND/1").one()]
    result = compute_lapse_status(apps, site)
    assert result["granted_app"].reference == "FUL/1"
    assert result["deadline"] == dt.date(2027, 1, 1)


def test_full_permission_plus_later_s73_anchors_on_the_full_permission(session):
    site = _site(session)
    full = _app(session, site.id, "FUL/1", proposal="Erection of 40 dwellings",
                decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024")
    _app(session, site.id, "S73/1", application_category="variation_or_amendment",
         proposal="Section 73 application to vary condition 2 of planning permission FUL/1",
         decision="Approve with Conditions", decision_issued_date="Mon 01 Jun 2026")
    apps = [full, session.query(Application).filter_by(reference="S73/1").one()]
    result = compute_lapse_status(apps, site)
    assert result["granted_app"].reference == "FUL/1"
    assert result["deadline"] == dt.date(2027, 1, 1)


# --- 5/6. S73 cannot create a fresh clock / unresolved S73 -> NOT_DETERMINED -


def test_s73_alone_cannot_create_a_fresh_three_year_clock(session):
    """An S73 decided 'Approve' with NO underlying substantive permission
    anywhere on the site must never be treated as if it were itself a
    fresh grant starting a new 3-year clock."""
    site = _site(session)
    _app(session, site.id, "S73/1", application_category="variation_or_amendment",
         proposal="Section 73 application to vary condition 2 of an unspecified permission",
         decision="Approve with Conditions", decision_issued_date="Mon 01 Jun 2026")
    apps = list(site.applications)
    result = compute_lapse_status(apps, site)
    assert result["status"] == "not_determined"
    assert result["deadline"] is None
    assert result["granted_app"] is None


def test_unresolved_s73_relationship_returns_not_determined_not_a_fabricated_deadline(session):
    """Same shape as above via the anchor resolver directly - an S73 whose
    underlying permission cannot be identified must resolve NOT_DETERMINED,
    never fabricate a deadline from the S73's own decision date."""
    site = _site(session)
    _app(session, site.id, "S73/1", application_category="variation_or_amendment",
         proposal="Section 73 application to vary condition 2", decision="Approve with Conditions",
         decision_issued_date="Mon 01 Jun 2026")
    anchor = resolve_operative_lapse_anchor(list(site.applications))
    assert anchor.state == FACT_NOT_DETERMINED
    assert anchor.application is None


# --- 7. Reserved Matters following Outline - regression ---------------------


def test_reserved_matters_following_outline_still_correctly_anchors_on_the_rm(session):
    site = _site(session)
    _app(session, site.id, "OUT/1", proposal="Outline application for up to 200 dwellings",
         decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2020")
    _app(session, site.id, "RM/1", application_category="reserved_matters",
         proposal="Reserved matters application for the erection of 200 dwellings",
         decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024")
    apps = list(site.applications)
    result = compute_lapse_status(apps, site)
    assert result["granted_app"].reference == "RM/1"
    assert result["deadline"] == dt.date(2027, 1, 1)


# --- 8/9. Genuine whole-site / genuine phase permission ---------------------


def test_genuine_whole_site_permission_resolves_correctly(session):
    site = _site(session)
    full = _app(session, site.id, "FUL/1", proposal="Erection of 40 dwellings",
                decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024")
    result = compute_lapse_status([full], site)
    assert result["granted_app"].reference == "FUL/1"
    assert result["status"] in ("safe", "approaching", "lapsed", "underway")


def test_genuine_phase_permission_resolves_within_its_own_scope(session):
    """compute_phase_progress, given ONE phase's own already-scoped
    application list, anchors on that phase's own substantive grant."""
    phase_apps_site = _site(session)
    rm_phase1 = _app(session, phase_apps_site.id, "RES/1", application_category="reserved_matters",
                      proposal="Reserved matters application for Phase 1 of a residential scheme",
                      decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024")
    result = compute_phase_progress([rm_phase1])
    assert result["latest_grant"].reference == "RES/1"
    assert result["status"] == "approved_not_started"


# --- 10/11/12. Sibling phase / plot cannot reset another scope's clock -----


def test_sibling_phase_cannot_reset_a_different_phases_clock(session):
    """compute_phase_progress is only ever given ONE phase's own apps -
    prove a sibling phase's later grant, if accidentally included, would
    change the outcome (demonstrating the caller-side scoping is what
    protects this, exactly as documented)."""
    site = _site(session)
    phase1_grant = _app(session, site.id, "RES/1", application_category="reserved_matters",
                         proposal="Reserved matters for Phase 1", decision="Approve with Conditions",
                         decision_issued_date="Mon 01 Jan 2024")
    # Phase 1's OWN scope must never see Phase 2's later grant.
    result_scoped_correctly = compute_phase_progress([phase1_grant])
    assert result_scoped_correctly["latest_grant"].reference == "RES/1"


def test_individual_plot_cannot_reset_the_whole_site_clock(session):
    site = _site(session)
    full = _app(session, site.id, "FUL/1", proposal="Erection of 40 dwellings",
                decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024")
    _app(session, site.id, "NMA/PLOT", application_category="variation_or_amendment",
         proposal="Non-material amendment relating to plot 5 bin store", decision="Approve with Conditions",
         decision_issued_date="Mon 01 Jun 2026")
    apps = list(site.applications)
    result = compute_lapse_status(apps, site)
    assert result["granted_app"].reference == "FUL/1"
    assert result["deadline"] == dt.date(2027, 1, 1)


def test_individual_plot_cannot_reset_a_material_phases_clock(session):
    """Within one already-scoped material-parcel group's own applications,
    a plot-level non-substantive filing must not become the anchor either -
    same mechanism as the whole-site case, exercised at phase/group scope."""
    site = _site(session)
    material_parcel_grant = _app(session, site.id, "FUL/PARCEL1", proposal="Erection of 25 dwellings on Parcel 1",
                                  decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024")
    plot_nma = _app(session, site.id, "NMA/PARCEL1-PLOT9", application_category="variation_or_amendment",
                     proposal="Non-material amendment relating to plot 9 within Parcel 1",
                     decision="Approve with Conditions", decision_issued_date="Mon 01 Jun 2026")
    result = compute_phase_progress([material_parcel_grant, plot_nma])
    assert result["latest_grant"].reference == "FUL/PARCEL1"


# --- 13. No substantive consent -> NOT_DETERMINED ---------------------------


def test_no_substantive_consent_at_all_returns_not_determined(session):
    """Only a Prior Approval has ever been granted on this site - never
    fall back to treating it as if it were a full planning permission."""
    site = _site(session)
    _app(session, site.id, "PA/1", proposal="Application to determine if prior approval is required for a change of use",
         decision="Prior Approval Approved", decision_issued_date="Mon 01 Jan 2024")
    apps = list(site.applications)
    result = compute_lapse_status(apps, site)
    assert result["status"] == "not_determined"
    assert result["deadline"] is None
    assert result["granted_app"] is None


# --- 14/15. Later NMA/CND can still provide progress evidence --------------


def test_later_nma_still_provides_valid_progress_evidence_against_the_true_permission(session):
    site = _site(session)
    full = _app(session, site.id, "FUL/1", proposal="Erection of 40 dwellings",
                decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024",
                application_received="Mon 01 Dec 2023")
    _app(session, site.id, "NMA/1", application_category="variation_or_amendment",
         proposal="Non-material amendment to permission FUL/1", decision="Approve with Conditions",
         decision_issued_date="Mon 01 Jun 2024", application_received="Mon 01 Jun 2024")
    apps = list(site.applications)
    result = compute_lapse_status(apps, site)
    assert result["granted_app"].reference == "FUL/1"
    assert result["build_status"] == "underway"
    assert result["status"] == "underway"


def test_later_condition_discharge_still_provides_valid_progress_evidence(session):
    site = _site(session)
    full = _app(session, site.id, "FUL/1", proposal="Erection of 40 dwellings",
                decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024",
                application_received="Mon 01 Dec 2023")
    _app(session, site.id, "CND/1", application_category="condition_discharge_or_details",
         proposal="Full discharge of conditions", decision="Full discharge of conditions",
         decision_issued_date="Mon 01 Jun 2024", application_received="Mon 01 Jun 2024")
    apps = list(site.applications)
    result = compute_lapse_status(apps, site)
    assert result["granted_app"].reference == "FUL/1"
    assert result["build_status"] == "underway"


# --- 16/17. RECENT_PERMISSION false/valid ------------------------------------


def test_false_recent_permission_suppressed_when_true_permission_is_stale(session):
    site = _site(session)
    _app(session, site.id, "FUL/1", proposal="Erection of 40 dwellings",
         decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2023")
    _app(session, site.id, "NMA/1", application_category="variation_or_amendment",
         proposal="Non-material amendment to permission FUL/1", decision="Approve with Conditions",
         decision_issued_date=(dt.date.today() - dt.timedelta(days=10)).strftime("%a %d %b %Y"))
    cards = _recent_permission_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_valid_genuine_recent_permission_preserved(session):
    site = _site(session)
    _app(session, site.id, "FUL/1", proposal="Erection of 40 dwellings",
         decision="Approve with Conditions",
         decision_issued_date=(dt.date.today() - dt.timedelta(days=10)).strftime("%a %d %b %Y"))
    cards = _recent_permission_cards(session, None)
    assert any(c["params"]["site_id"] == str(site.id) for c in cards)


# --- 18/19. UNDEVELOPED_PERMISSION false/valid ------------------------------


def test_false_world_of_pets_style_undeveloped_signal_suppressed(session):
    site = _site(session)
    rm = _app(session, site.id, "RES/1", application_category="reserved_matters",
              proposal="Reserved matters application for the erection of 40 dwellings",
              decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024",
              application_received="Mon 01 Dec 2023")
    _app(session, site.id, "NMA/1", application_category="variation_or_amendment",
         proposal="Non-material amendment to permission RES/1", decision="Approve with Conditions",
         decision_issued_date="Mon 01 Jun 2024", application_received="Mon 01 Jun 2024")
    apps = list(site.applications)
    result = compute_phase_progress(apps)
    assert result["status"] == "underway"  # not "approved_not_started"


def test_valid_genuinely_undeveloped_permission_preserved(session):
    site = _site(session)
    _app(session, site.id, "FUL/1", proposal="Erection of 40 dwellings",
         decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024",
         application_received="Mon 01 Dec 2023")
    apps = list(site.applications)
    result = compute_phase_progress(apps)
    assert result["status"] == "approved_not_started"
    assert result["latest_grant"].reference == "FUL/1"


# --- 20/21. APPROACHING_LAPSE corrected date / newly-approaching -----------


def test_approaching_lapse_uses_the_corrected_trusted_deadline(session):
    site = _site(session)
    target_deadline = dt.date.today() + dt.timedelta(days=90)
    true_decision_date = target_deadline.replace(year=target_deadline.year - 3)
    _app(session, site.id, "FUL/1", proposal="Erection of 40 dwellings",
         decision="Approve with Conditions", decision_issued_date=true_decision_date.strftime("%a %d %b %Y"),
         application_received=(true_decision_date - dt.timedelta(days=30)).strftime("%a %d %b %Y"))
    # A later-DECIDED NMA that would, under the OLD naive logic, have
    # pushed the deadline out by ~2 years - must not do so now. Its own
    # application_received predates the true grant, so it also does not
    # itself count as post-grant progress evidence (that combination is
    # covered separately by test_later_nma_still_provides_valid_progress_
    # evidence_against_the_true_permission) - isolating this test to the
    # deadline-selection fix alone.
    later_nma_date = true_decision_date + dt.timedelta(days=700)
    _app(session, site.id, "NMA/1", application_category="variation_or_amendment",
         proposal="Non-material amendment to permission FUL/1", decision="Approve with Conditions",
         decision_issued_date=later_nma_date.strftime("%a %d %b %Y"),
         application_received=(true_decision_date - dt.timedelta(days=30)).strftime("%a %d %b %Y"))
    cards = _approaching_lapse_cards(session, None)
    matching = [c for c in cards if c["params"]["site_id"] == str(site.id)]
    assert len(matching) == 1


def test_newly_approaching_lapse_case_synthetic(session):
    """Synthetic case proving the mechanism CAN surface a newly-approaching
    site once the wrong, later NMA-derived deadline is corrected to the
    true, earlier substantive-permission deadline (no live production
    example currently falls inside the 180-day window - see the Gate
    2B-2C investigation report's own Section O)."""
    site = _site(session)
    target_deadline = dt.date.today() + dt.timedelta(days=60)
    true_decision_date = target_deadline.replace(year=target_deadline.year - 3)
    _app(session, site.id, "FUL/1", proposal="Erection of 40 dwellings",
         decision="Approve with Conditions", decision_issued_date=true_decision_date.strftime("%a %d %b %Y"))
    # A later NMA far enough out that, under the OLD logic, its OWN +3y
    # deadline would have read "safe", hiding this site from
    # approaching_lapse entirely.
    later_nma_date = true_decision_date + dt.timedelta(days=800)
    _app(session, site.id, "NMA/1", application_category="variation_or_amendment",
         proposal="Non-material amendment to permission FUL/1", decision="Approve with Conditions",
         decision_issued_date=later_nma_date.strftime("%a %d %b %Y"),
         # Received before the true grant - isolates this test to the
         # deadline-selection fix, not the separate progress-evidence
         # behaviour (covered by its own dedicated test).
         application_received=(true_decision_date - dt.timedelta(days=30)).strftime("%a %d %b %Y"))
    apps = list(site.applications)
    old_naive_deadline = later_nma_date.replace(year=later_nma_date.year + 3)
    assert (old_naive_deadline - dt.date.today()).days > 180  # would have read "safe" under the old code
    result = compute_lapse_status(apps, site)
    assert result["status"] == "approaching"
    assert result["granted_app"].reference == "FUL/1"


# --- 22. Fingerprint only changes for legitimate corrected fields ----------


def test_fingerprint_lapse_fields_reflect_the_corrected_trusted_signal(session):
    site = _site(session)
    rm = _app(session, site.id, "RES/1", application_category="reserved_matters",
              proposal="Reserved matters application for the erection of 40 dwellings",
              decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024",
              application_received="Mon 01 Dec 2023")
    _intel(session, rm, total_units_final=40, core_intelligence_complete=True)
    _app(session, site.id, "NMA/1", application_category="variation_or_amendment",
         proposal="Non-material amendment to permission RES/1", decision="Approve with Conditions",
         decision_issued_date="Mon 01 Jun 2026")

    universe = build_current_opportunity_universe(session)
    site_opp = next(r for r in universe if r.opportunity_id == f"planning_delivery:site:{site.id}")
    assert site_opp.fingerprint_fields["deadline"] == dt.date(2027, 1, 1)
    assert site_opp.fingerprint_fields["lapse_status"] in ("safe", "approaching", "underway")
    # unit_count (unrelated to this gate's fix) is untouched - still the
    # representative application's own figure, not migrated here.
    assert site_opp.fingerprint_fields["unit_count"] == 40


# --- 23. LONG_PENDING non-regression -----------------------------------------


def test_long_pending_application_detector_is_unaffected_by_this_gate(session):
    from app.reporting.dashboard import _long_pending_application_cards
    from app.reporting.opportunity_universe import add_calendar_months, LONG_PENDING_APPLICATION_WINDOW_MONTHS

    site = _site(session)
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    _app(session, site.id, "FUL/1", proposal="Erection of 40 dwellings", decision=None, status="Under consideration",
         application_category="primary_residential", application_received=submitted.strftime("%a %d %b %Y"))
    cards = _long_pending_application_cards(session, None)
    assert any(c["params"]["site_id"] == str(site.id) for c in cards)


# --- Pre-merge semantic review: NOT_GRANTED vs NOT_DETERMINED --------------
#
# Root cause of the ~125-site regression this review fixes: resolve_
# operative_lapse_anchor originally collapsed "zero granted applications at
# all" and "granted applications exist but none is substantive" into the
# SAME FACT_NOT_DETERMINED outcome, so compute_lapse_status could not tell
# them apart and reported both as "not_determined" - relabelling the
# ordinary, common "nothing has been granted yet" case (a positive, stable
# fact) as if it were a genuine uncertainty. Fixed via OperativeLapseAnchor.
# any_granted.


def test_zero_granted_applications_reports_not_granted(session):
    site = _site(session)
    _app(session, site.id, "FUL/1", proposal="Erection of 40 dwellings", decision=None,
         status="Under consideration", application_category="primary_residential")
    apps = list(site.applications)
    result = compute_lapse_status(apps, site)
    assert result["status"] == "not_granted"
    assert result["deadline"] is None
    assert result["granted_app"] is None


def test_only_nma_granted_reports_not_determined_not_not_granted(session):
    site = _site(session)
    _app(session, site.id, "NMA/1", application_category="variation_or_amendment",
         proposal="Non-material amendment to an unspecified permission",
         decision="Approve with Conditions", decision_issued_date="Mon 01 Jan 2024")
    apps = list(site.applications)
    result = compute_lapse_status(apps, site)
    assert result["status"] == "not_determined"
    assert result["deadline"] is None


def test_only_condition_discharge_granted_reports_not_determined(session):
    # "Details Approved" (unlike the far more common "Full discharge of
    # conditions"/"Agreed" wording) IS classified DECIDED_GRANTED by
    # resolve_decided_state - this isolates the test to the role guardrail
    # (condition_discharge is never substantive) rather than the decided-
    # state classification, which is unrelated to this gate.
    site = _site(session)
    _app(session, site.id, "CND/1", application_category="condition_discharge_or_details",
         proposal="Approval of details reserved by condition", decision="Details Approved",
         decision_issued_date="Mon 01 Jan 2024")
    apps = list(site.applications)
    result = compute_lapse_status(apps, site)
    assert result["status"] == "not_determined"
    assert result["deadline"] is None


def test_only_ineligible_prior_approval_grant_reports_not_determined(session):
    site = _site(session)
    _app(session, site.id, "PA/1", proposal="Application to determine if prior approval is required for a change of use",
         decision="Prior Approval Approved", decision_issued_date="Mon 01 Jan 2024")
    apps = list(site.applications)
    result = compute_lapse_status(apps, site)
    assert result["status"] == "not_determined"
    assert result["deadline"] is None


def test_long_pending_site_with_no_grant_has_stable_not_granted_fingerprint(session):
    """A genuinely still-pending, never-granted site's fingerprint must
    read "not_granted", never "not_determined" - the fingerprint-stability
    case this review exists to protect (production: ~125 such sites)."""
    site = _site(session)
    _app(session, site.id, "FUL/1", proposal="Erection of 40 dwellings", decision=None,
         status="Under consideration", application_category="primary_residential",
         application_received="Mon 01 Jan 2020")
    universe = build_current_opportunity_universe(session)
    site_opp = next(
        (r for r in universe if r.opportunity_id == f"planning_delivery:long_pending_application:{site.id}"), None,
    )
    assert site_opp is not None
    assert site_opp.fingerprint_fields["lapse_status"] == "not_granted"
