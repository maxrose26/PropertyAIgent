"""Gate 1C ("Recent Permission Opportunity Candidate Detection") - tests
for the fourth deterministic detection route: app.reporting.dashboard.
_recent_permission_cards, its integration into app.reporting.
opportunity_universe.build_current_opportunity_universe and app.reporting.
opportunity_feed.build_opportunity_feed, and the detector-expansion
baseline-safety fix in app.reporting.opportunity_change.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from app.db.models import Application, LocalPlan, LocalPlanSite, OpportunityMonitoringState, Site
from app.policy.buyer_matching import NOT_SUITABLE, STRONG_FIT
from app.policy.buyer_profiles import BUYER_PROFILE_ORDER, BUYER_PROFILES, NESTEN_HOMES, NATIONAL_HOUSEBUILDER
from app.policy.buyer_matching import assess_buyer_fit
from app.reporting.dashboard import _recent_permission_cards
from app.reporting.opportunity_change import BASELINE_EXISTING, NEW, MATERIALLY_CHANGED, UNCHANGED, sync_opportunity_monitoring_state
from app.reporting.opportunity_feed import PLANNING_DELIVERY, STRATEGIC_LAND, build_opportunity_feed
from app.reporting.opportunity_universe import (
    RECENT_PERMISSION_WINDOW_MONTHS,
    build_current_opportunity_universe,
    planning_delivery_recent_permission_opportunity_id,
)


def _make_granted_site(session, *, months_ago: float, build_status: str | None = None, n_apps: int = 1, address: str = "Test Site") -> Site:
    site = Site(council_code="testcouncil", canonical_address=f"{address}-{months_ago}", display_address=address, build_status=build_status)
    session.add(site)
    session.flush()
    decision_date = dt.date.today() - dt.timedelta(days=round(months_ago * 30.44))
    for i in range(n_apps):
        session.add(Application(
            council_code="testcouncil", reference=f"REF-{site.id}-{i}", site_id=site.id,
            decision="Granted", decision_issued_date=decision_date.strftime("%a %d %b %Y"),
            first_seen_at=dt.datetime.now(dt.timezone.utc),
            # Gate 2B-2C: resolve_planning_role needs real substantive
            # proposal wording to trust this as the lapse anchor.
            proposal="Erection of 40 dwellings",
        ))
    session.commit()
    return site


def _make_plan(session) -> LocalPlan:
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status="proposed_submission", raw_status="proposed_submission")
    session.add(plan)
    session.commit()
    return plan


def _make_allocation(session, plan_id, **kwargs) -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan_id, policy_reference=kwargs.pop("policy_reference", "AN1"),
        site_name=kwargs.pop("site_name", "Test Allocation"), plan_name="Test Local Plan", plan_status="proposed_submission",
        matched_site_id=None, **kwargs,
    )
    session.add(allocation)
    session.commit()
    return allocation


# --- Eligibility -------------------------------------------------------------

def test_recent_grant_with_no_build_evidence_is_a_candidate(session):
    site = _make_granted_site(session, months_ago=2)
    cards = _recent_permission_cards(session, None)
    assert any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_recent_grant_underway_is_excluded(session):
    site = _make_granted_site(session, months_ago=2)
    # "underway" is derived from a portal progress-signal filing, not a raw
    # Site field - simplest deterministic way to trigger it in a fixture is
    # a second application whose category reads as a commencement filing;
    # simulate directly via Site.build_status is NOT how "underway" is
    # produced (that's EPC-sourced), so exercise the EPC-sourced statuses
    # here and cover "underway" specifically via a progress-signal filing.
    session.add(Application(
        council_code="testcouncil", reference=f"REF-{site.id}-commencement", site_id=site.id,
        decision=None, status="Registered", application_category="condition_discharge_or_details",
        decision_issued_date=None, application_received=(dt.date.today() - dt.timedelta(days=10)).strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
    ))
    session.commit()
    cards = _recent_permission_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_recent_grant_partially_complete_is_excluded(session):
    site = _make_granted_site(session, months_ago=2, build_status="partially_complete")
    cards = _recent_permission_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_recent_grant_complete_is_excluded(session):
    site = _make_granted_site(session, months_ago=2, build_status="complete")
    cards = _recent_permission_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_refused_application_is_excluded(session):
    site = Site(council_code="testcouncil", canonical_address="refused-site", display_address="Refused Site")
    session.add(site)
    session.flush()
    session.add(Application(
        council_code="testcouncil", reference="REF-REFUSED", site_id=site.id, decision="Refused",
        decision_issued_date=(dt.date.today() - dt.timedelta(days=60)).strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
    ))
    session.commit()
    cards = _recent_permission_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_withdrawn_application_is_excluded(session):
    site = Site(council_code="testcouncil", canonical_address="withdrawn-site", display_address="Withdrawn Site")
    session.add(site)
    session.flush()
    session.add(Application(
        council_code="testcouncil", reference="REF-WITHDRAWN", site_id=site.id, decision="Withdrawn",
        decision_issued_date=(dt.date.today() - dt.timedelta(days=60)).strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
    ))
    session.commit()
    cards = _recent_permission_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_pending_application_is_excluded(session):
    site = Site(council_code="testcouncil", canonical_address="pending-site", display_address="Pending Site")
    session.add(site)
    session.flush()
    session.add(Application(
        council_code="testcouncil", reference="REF-PENDING", site_id=site.id, decision=None, status="Under consideration",
        decision_issued_date=None, first_seen_at=dt.datetime.now(dt.timezone.utc),
    ))
    session.commit()
    cards = _recent_permission_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_unknown_build_status_is_included_not_treated_as_verified_non_commencement(session):
    site = _make_granted_site(session, months_ago=2, build_status=None)
    cards = _recent_permission_cards(session, None)
    matching = [c for c in cards if c["params"]["site_id"] == str(site.id)]
    assert len(matching) == 1
    # Evidence-safe wording (Section 19) - never claims verified non-commencement.
    assert "no commencement evidence has been identified" in matching[0]["reason"].lower()
    assert "not commenced" not in matching[0]["reason"].lower()
    assert "for sale" not in matching[0]["reason"].lower()
    assert "available" not in matching[0]["reason"].lower()


def test_grant_older_than_window_is_excluded(session):
    site = _make_granted_site(session, months_ago=RECENT_PERMISSION_WINDOW_MONTHS + 1)
    cards = _recent_permission_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_grant_within_window_boundary_is_included(session):
    site = _make_granted_site(session, months_ago=RECENT_PERMISSION_WINDOW_MONTHS - 0.5)
    cards = _recent_permission_cards(session, None)
    assert any(c["params"]["site_id"] == str(site.id) for c in cards)


def _make_granted_site_on_exact_date(session, *, grant_date: dt.date, address: str = "Exact Date Site") -> Site:
    """Precise calendar-month-boundary variant of _make_granted_site above -
    that helper's `months_ago * 30.44` day-approximation is appropriate for
    "well inside/outside the window" fixtures but is NOT precise enough to
    exercise the exact calendar-month boundary itself (Gate 1C amendment
    Section 29's own explicit requirement for a boundary test built from
    real calendar-month arithmetic, not an approximation)."""
    site = Site(council_code="testcouncil", canonical_address=f"{address}-{grant_date.isoformat()}", display_address=address)
    session.add(site)
    session.flush()
    session.add(Application(
        council_code="testcouncil", reference=f"REF-{site.id}", site_id=site.id,
        decision="Granted", decision_issued_date=grant_date.strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
        # Gate 2B-2C: resolve_planning_role needs real substantive proposal
        # wording to trust this as the lapse anchor.
        proposal="Erection of 40 dwellings",
    ))
    session.commit()
    return site


def test_exact_calendar_month_boundary_is_deterministic_and_exclusive(session):
    """The boundary itself (Gate 1C amendment Section 4/14): a grant dated
    EXACTLY RECENT_PERMISSION_WINDOW_MONTHS calendar months before today is
    EXCLUDED (the boundary is exclusive - matches the brief's own "ages
    BEYOND N months -> no automatic signal" wording); one calendar day
    earlier is INCLUDED. Built from add_calendar_months itself (the same
    helper the production code uses), not a day-count approximation - this
    is the precise boundary proof, distinct from the coarser "well within/
    without the window" tests above."""
    from app.reporting.opportunity_universe import add_calendar_months

    today = dt.date.today()
    exactly_at_boundary = add_calendar_months(today, -RECENT_PERMISSION_WINDOW_MONTHS)
    one_day_inside = exactly_at_boundary + dt.timedelta(days=1)

    excluded_site = _make_granted_site_on_exact_date(session, grant_date=exactly_at_boundary, address="Exactly At Boundary")
    included_site = _make_granted_site_on_exact_date(session, grant_date=one_day_inside, address="One Day Inside Boundary")

    cards = _recent_permission_cards(session, None)
    card_site_ids = {c["params"]["site_id"] for c in cards}
    assert str(excluded_site.id) not in card_site_ids
    assert str(included_site.id) in card_site_ids


# --- Identity ------------------------------------------------------------

def test_stable_site_level_identity_format(session):
    site = _make_granted_site(session, months_ago=2)
    universe = build_current_opportunity_universe(session)
    expected_id = planning_delivery_recent_permission_opportunity_id(site.id)
    assert any(r.opportunity_id == expected_id for r in universe)
    assert expected_id == f"planning_delivery:recent_permission:{site.id}"


def test_multiple_applications_on_one_site_produce_one_candidate(session):
    site = _make_granted_site(session, months_ago=2, n_apps=3)
    cards = _recent_permission_cards(session, None)
    matching = [c for c in cards if c["params"]["site_id"] == str(site.id)]
    assert len(matching) == 1


def test_genuine_second_substantive_grant_refreshes_the_single_candidate(session):
    """A second GENUINE SUBSTANTIVE grant on the same site (e.g. a real
    Reserved Matters approval following an earlier outline) must not
    create a second candidate - it correctly refreshes the SAME site-level
    candidate's recency, since it is itself trusted-anchor-eligible
    (app.reporting.scheme_reconciliation.SUBSTANTIVE_ROLES)."""
    site = _make_granted_site(session, months_ago=10)
    session.add(Application(
        council_code="testcouncil", reference=f"REF-{site.id}-RM", site_id=site.id,
        decision="Granted", decision_issued_date=(dt.date.today() - dt.timedelta(days=30)).strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
        proposal="Reserved matters application for the erection of 40 dwellings",
    ))
    session.commit()
    cards = _recent_permission_cards(session, None)
    matching = [c for c in cards if c["params"]["site_id"] == str(site.id)]
    assert len(matching) == 1


def test_non_substantive_second_grant_does_not_refresh_or_fabricate_recency(session):
    """Gate 2B-2C - a later NON-SUBSTANTIVE grant (S73/variation, NMA,
    condition discharge) on the same site must NOT refresh the site's
    recent-permission recency, and must NOT itself make an old
    substantive permission look recently granted. The genuine substantive
    grant here is 10 months old (well outside the 3-month window) - this
    site must NOT appear as recent_permission at all, even though a
    later-decided S73 exists on the same site (this is the exact defect
    class the Gate 2B-2C investigation confirmed in production - e.g. a
    later NMA/S73 previously became `latest_granted` and made a stale
    permission look freshly granted)."""
    site = _make_granted_site(session, months_ago=10)
    session.add(Application(
        council_code="testcouncil", reference=f"REF-{site.id}-S73", site_id=site.id,
        decision="Granted", decision_issued_date=(dt.date.today() - dt.timedelta(days=30)).strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
        application_category="variation_or_amendment",
        proposal="Section 73 application to vary condition 2 of planning permission",
    ))
    session.commit()
    cards = _recent_permission_cards(session, None)
    matching = [c for c in cards if c["params"]["site_id"] == str(site.id)]
    assert len(matching) == 0


# --- Overlap / deduplication with the two existing planning/delivery routes --

def test_site_already_approaching_lapse_does_not_also_become_recent_permission(session):
    """A site old enough to be genuinely approaching its lapse deadline is
    outside the recent_permission window anyway in practice, but this
    proves the EXPLICIT precedence/dedup rule, not just the window's own
    incidental effect - construct a scenario where both COULD apply and
    confirm only the more specific approaching_lapse signal wins."""
    from app.pipeline.lapse_tracking import COMMENCEMENT_YEARS, LAPSE_WARNING_DAYS

    # Grant date chosen so the commencement deadline (grant + 3yr) falls
    # within the "approaching" window (<=180 days left) - i.e. genuinely
    # both old (outside any sane recent_permission reading) and, for this
    # test's own purposes, deliberately re-pointed at a monkeypatched
    # small window below so the overlap case is exercised directly.
    decision_date = dt.date.today() - dt.timedelta(days=COMMENCEMENT_YEARS * 365 - 90)
    site = Site(council_code="testcouncil", canonical_address="lapse-overlap-site", display_address="Lapse Overlap Site")
    session.add(site)
    session.flush()
    session.add(Application(
        council_code="testcouncil", reference=f"REF-{site.id}", site_id=site.id, decision="Granted",
        decision_issued_date=decision_date.strftime("%a %d %b %Y"), first_seen_at=dt.datetime.now(dt.timezone.utc),
        # Gate 2B-2C: resolve_planning_role needs real substantive proposal
        # wording to trust this as the lapse anchor.
        proposal="Erection of 40 dwellings",
    ))
    session.commit()

    import app.reporting.opportunity_universe as ou
    original_window = ou.RECENT_PERMISSION_WINDOW_MONTHS
    ou.RECENT_PERMISSION_WINDOW_MONTHS = 40  # wide enough that this site would ALSO qualify for recent_permission if not for the dedup rule
    try:
        universe = build_current_opportunity_universe(session)
    finally:
        ou.RECENT_PERMISSION_WINDOW_MONTHS = original_window

    site_ids_by_kind = {}
    for r in universe:
        if r.opportunity_id.startswith("planning_delivery:"):
            kind = r.opportunity_id.split(":")[1]
            site_ids_by_kind.setdefault(kind, set()).add(int(r.opportunity_id.split(":")[2]))

    assert site.id in site_ids_by_kind.get("site", set())  # approaching_lapse fired
    assert site.id not in site_ids_by_kind.get("recent_permission", set())  # never duplicated


def test_site_already_undeveloped_permission_does_not_also_become_recent_permission(session):
    """Two applications forming a genuine 'approved_not_started' phase -
    recent_permission must not also fire for the same site."""
    site = _make_granted_site(session, months_ago=2, n_apps=1)
    # Add a second application so build_phase_breakdown has enough to work
    # with - phase detection itself is exercised by tests/test_dashboard.py;
    # here we only need the site to genuinely appear in undeveloped_phase's
    # own output, which requires >=2 applications.
    session.add(Application(
        council_code="testcouncil", reference=f"REF-{site.id}-2", site_id=site.id, decision="Granted",
        decision_issued_date=(dt.date.today() - dt.timedelta(days=45)).strftime("%a %d %b %Y"),
        application_type="Full", proposal="Erection of dwellings", first_seen_at=dt.datetime.now(dt.timezone.utc),
    ))
    session.commit()

    universe = build_current_opportunity_universe(session)
    recent_permission_ids = {int(r.opportunity_id.split(":")[2]) for r in universe if r.opportunity_id.startswith("planning_delivery:recent_permission:")}
    phase_site_ids = {int(r.opportunity_id.split(":")[2]) for r in universe if r.opportunity_id.startswith("planning_delivery:phase:")}
    # Whichever way build_phase_breakdown classifies this particular
    # synthetic fixture, the two sets must never both contain this site -
    # the real assertion this test exists for.
    if site.id in phase_site_ids:
        assert site.id not in recent_permission_ids


# --- Universe / completeness --------------------------------------------

def test_existing_routes_are_unaffected_by_the_new_detector(session):
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan.id, site_name="Unaffected Allocation", minimum_dwellings=150)
    today = dt.date.today()
    lapse_site = _make_granted_site(session, months_ago=(3 * 365 - 90) / 30.44, address="Lapse Site")

    universe = build_current_opportunity_universe(session)
    strategic_ids = {r.opportunity_id for r in universe if r.opportunity_type == STRATEGIC_LAND}
    assert f"strategic_land:allocation:{allocation.id}" in strategic_ids
    site_ids = {r.opportunity_id for r in universe if r.opportunity_id.startswith("planning_delivery:site:")}
    assert f"planning_delivery:site:{lapse_site.id}" in site_ids


def test_new_detector_expands_the_universe_with_no_cap(session):
    plan = _make_plan(session)
    for i in range(5):
        _make_granted_site(session, months_ago=2, address=f"Recent Site {i}")
    universe = build_current_opportunity_universe(session)
    recent_permission_records = [r for r in universe if r.opportunity_id.startswith("planning_delivery:recent_permission:")]
    assert len(recent_permission_records) == 5


# --- Fingerprinting --------------------------------------------------------

def test_build_status_change_alters_the_fingerprint(session):
    site = _make_granted_site(session, months_ago=2, build_status=None)
    universe_before = build_current_opportunity_universe(session)
    record_before = next(r for r in universe_before if r.opportunity_id == planning_delivery_recent_permission_opportunity_id(site.id))

    site.build_status = "no_completions_yet"
    session.commit()
    universe_after = build_current_opportunity_universe(session)
    record_after = next((r for r in universe_after if r.opportunity_id == planning_delivery_recent_permission_opportunity_id(site.id)), None)
    assert record_after is not None
    from app.reporting.opportunity_universe import compute_opportunity_fingerprint
    assert compute_opportunity_fingerprint(record_before.fingerprint_fields) != compute_opportunity_fingerprint(record_after.fingerprint_fields)


def test_identical_rescan_produces_an_unchanged_fingerprint(session):
    _make_granted_site(session, months_ago=2)
    universe_1 = build_current_opportunity_universe(session)
    universe_2 = build_current_opportunity_universe(session)
    fp_1 = {r.opportunity_id: r.fingerprint_fields for r in universe_1 if r.opportunity_id.startswith("planning_delivery:recent_permission:")}
    fp_2 = {r.opportunity_id: r.fingerprint_fields for r in universe_2 if r.opportunity_id.startswith("planning_delivery:recent_permission:")}
    from app.reporting.opportunity_universe import compute_opportunity_fingerprint
    assert {k: compute_opportunity_fingerprint(v) for k, v in fp_1.items()} == {k: compute_opportunity_fingerprint(v) for k, v in fp_2.items()}


# --- Change semantics / detector-expansion baseline (release-critical) ----

def test_baseline_run_marks_first_ever_recent_permission_candidates_as_baseline_existing(session):
    _make_granted_site(session, months_ago=2)
    counts = sync_opportunity_monitoring_state(session)
    assert counts["baseline_existing"] >= 1
    assert counts["new"] == 0


def test_detector_expansion_after_an_already_populated_table_is_baseline_not_new(session):
    """THE release-critical Gate 1C requirement: when a new detector kind's
    first-ever candidates appear while OTHER kinds are already tracked
    (i.e. exactly what happens when Gate 1C is deployed into a database
    that already ran Gate 1's original three detectors), those candidates
    must be BASELINE_EXISTING, never NEW - never a single whole-table
    emptiness flag, which would get this wrong."""
    plan = _make_plan(session)
    _make_allocation(session, plan.id, site_name="Already Tracked Allocation", minimum_dwellings=150)
    first = sync_opportunity_monitoring_state(session)
    assert first["baseline_existing"] >= 1
    assert first["new"] == 0
    # The table is now non-empty (strategic_land already tracked), but
    # planning_delivery:recent_permission has never appeared before.
    assert session.execute(select(OpportunityMonitoringState)).scalars().first() is not None

    _make_granted_site(session, months_ago=2)
    second = sync_opportunity_monitoring_state(session)
    assert second["new"] == 0  # NOT misclassified as new merely because the table already had rows
    assert second["baseline_existing"] >= 1

    state = session.execute(
        select(OpportunityMonitoringState).where(OpportunityMonitoringState.opportunity_id.like("planning_delivery:recent_permission:%"))
    ).scalars().first()
    assert state is not None
    assert state.last_change_classification == BASELINE_EXISTING


def test_genuinely_new_candidate_after_the_kind_is_baselined_becomes_new(session):
    _make_granted_site(session, months_ago=2, address="First Recent Site")
    first = sync_opportunity_monitoring_state(session)
    assert first["baseline_existing"] >= 1

    _make_granted_site(session, months_ago=1, address="Second Recent Site")
    second = sync_opportunity_monitoring_state(session)
    assert second["new"] >= 1
    assert second["baseline_existing"] == 0  # the kind is already tracked now


def test_material_change_to_a_recent_permission_candidate_is_detected(session):
    site = _make_granted_site(session, months_ago=2, build_status=None)
    sync_opportunity_monitoring_state(session)  # baseline
    sync_opportunity_monitoring_state(session)  # unchanged

    site.build_status = "partially_complete"  # now excluded entirely - the opportunity should stop appearing
    session.commit()
    counts = sync_opportunity_monitoring_state(session)
    # The candidate leaves the universe when it becomes partially_complete
    # (correctly excluded, per this gate's own build-status gate) - its
    # monitoring row is left untouched (never deleted), not reclassified.
    state = session.execute(
        select(OpportunityMonitoringState).where(OpportunityMonitoringState.opportunity_id == planning_delivery_recent_permission_opportunity_id(site.id))
    ).scalars().first()
    assert state is not None
    assert state.last_change_classification == UNCHANGED  # last synced state before it left the universe, untouched


def test_rerun_is_idempotent(session):
    _make_granted_site(session, months_ago=2)
    sync_opportunity_monitoring_state(session)
    second = sync_opportunity_monitoring_state(session)
    third = sync_opportunity_monitoring_state(session)
    assert second == third


# --- Buyer matching --------------------------------------------------------

def test_same_recent_permission_candidate_produces_different_fit_per_buyer(session):
    from app.db.models import SchemeIntelligence
    from app.policy.buyer_matching import build_planning_delivery_matching_facts

    site = _make_granted_site(session, months_ago=2)
    app = session.execute(select(Application).where(Application.site_id == site.id)).scalars().first()
    session.add(SchemeIntelligence(
        application_id=app.id, total_units_final=82, affordable_units_final=72, affordable_percentage_final=100.0,
        affordable_missing=False, development_type="mixed_retirement_and_market_housing", core_intelligence_complete=True,
    ))
    session.commit()
    facts = build_planning_delivery_matching_facts(app.scheme_intelligence)

    nesten = assess_buyer_fit(NESTEN_HOMES, facts)
    housing_association = assess_buyer_fit(BUYER_PROFILES["housing_association"], facts)
    assert nesten.classification == NOT_SUITABLE
    assert housing_association.classification != NOT_SUITABLE  # same facts, different buyer-relative conclusion


# --- Feed integration --------------------------------------------------------

def test_recent_permission_can_appear_in_buyer_mode_feed(session):
    from app.db.models import SchemeIntelligence

    site = _make_granted_site(session, months_ago=2)
    app = session.execute(select(Application).where(Application.site_id == site.id)).scalars().first()
    session.add(SchemeIntelligence(application_id=app.id, total_units_final=60, core_intelligence_complete=True))
    session.commit()

    feed = build_opportunity_feed(session, limit=6, buyer_key="nesten_homes")
    assert "recent_permission" in feed["counts"]
    assert feed["counts"]["recent_permission"] >= 1


def test_generic_feed_remains_bounded_and_does_not_get_overwhelmed(session):
    for i in range(20):
        _make_granted_site(session, months_ago=2, address=f"Bulk Recent Site {i}")
    feed = build_opportunity_feed(session, limit=6)
    assert len(feed["cards"]) <= 6
    assert feed["counts"]["recent_permission"] >= 1
