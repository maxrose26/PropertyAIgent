"""Gate 1C amendment ("Planning Opportunity Triggers & Weekly Re-evaluation")
- tests for the new LONG_PENDING_APPLICATION detector: app.reporting.
dashboard._long_pending_application_cards, its integration into app.
reporting.opportunity_universe.build_current_opportunity_universe and app.
reporting.opportunity_feed.build_opportunity_feed, and the detector-
expansion baseline-safety fix (app.reporting.opportunity_change) as it
applies to this new detector kind specifically.

Companion to tests/test_recent_permission_opportunities.py - same
structural pattern, same fixtures style, deliberately not a parallel
re-implementation of shared helpers where an equivalent one already exists
there (this file defines its own site-builder since the eligibility axis
here is submission date + pending status, not grant date + build status).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from app.db.models import Application, OpportunityMonitoringState, Site
from app.policy.buyer_matching import NOT_SUITABLE
from app.policy.buyer_profiles import BUYER_PROFILE_ORDER, BUYER_PROFILES
from app.policy.buyer_matching import assess_buyer_fit
from app.reporting.dashboard import _long_pending_application_cards
from app.reporting.opportunity_change import BASELINE_EXISTING, NEW, sync_opportunity_monitoring_state
from app.reporting.opportunity_feed import build_opportunity_feed
from app.reporting.opportunity_universe import (
    LONG_PENDING_APPLICATION_WINDOW_MONTHS,
    add_calendar_months,
    build_current_opportunity_universe,
    planning_delivery_long_pending_application_opportunity_id,
)


def _make_pending_site(
    session, *, submitted_date: dt.date, status: str = "Under consideration", decision: str | None = None,
    application_category: str | None = "full_planning", address: str = "Pending Site",
) -> Site:
    site = Site(council_code="testcouncil", canonical_address=f"{address}-{submitted_date.isoformat()}", display_address=address)
    session.add(site)
    session.flush()
    session.add(Application(
        council_code="testcouncil", reference=f"REF-{site.id}", site_id=site.id,
        decision=decision, status=status, application_category=application_category,
        application_received=submitted_date.strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
    ))
    session.commit()
    return site


# --- Eligibility: age boundary -----------------------------------------

def test_pending_less_than_six_months_is_excluded(session):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS - 1))
    site = _make_pending_site(session, submitted_date=submitted, address="Too Recent")
    cards = _long_pending_application_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_pending_well_beyond_six_months_is_included(session):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 3))
    site = _make_pending_site(session, submitted_date=submitted, address="Well Beyond")
    cards = _long_pending_application_cards(session, None)
    assert any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_exact_six_month_boundary_is_deterministic_and_inclusive(session):
    """Gate 1C amendment Section 4/14: qualifies once `today >=
    add_calendar_months(submitted_date, 6)` - INCLUSIVE at the boundary,
    the deliberate opposite of recent_permission's exclusive boundary,
    each matching its own brief wording verbatim ("AT LEAST six months")."""
    today = dt.date.today()
    exactly_at_boundary = add_calendar_months(today, -LONG_PENDING_APPLICATION_WINDOW_MONTHS)
    one_day_short = exactly_at_boundary + dt.timedelta(days=1)

    included_site = _make_pending_site(session, submitted_date=exactly_at_boundary, address="Exactly At Six Months")
    excluded_site = _make_pending_site(session, submitted_date=one_day_short, address="One Day Short Of Six Months")

    cards = _long_pending_application_cards(session, None)
    card_site_ids = {c["params"]["site_id"] for c in cards}
    assert str(included_site.id) in card_site_ids
    assert str(excluded_site.id) not in card_site_ids


# --- Eligibility: status/decision exclusions -----------------------------

def test_granted_application_pending_six_months_is_excluded(session):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    site = _make_pending_site(session, submitted_date=submitted, decision="Granted", status="Decided", address="Granted Long Ago")
    cards = _long_pending_application_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_refused_application_is_excluded(session):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    site = _make_pending_site(session, submitted_date=submitted, decision="Refused", status="Decided", address="Refused")
    cards = _long_pending_application_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_withdrawn_application_is_excluded(session):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    site = _make_pending_site(session, submitted_date=submitted, decision=None, status="Withdrawn", address="Withdrawn")
    cards = _long_pending_application_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_decided_with_ambiguous_outcome_is_excluded_not_treated_as_pending(session):
    """A 'Decided'-labelled row whose decision text doesn't parse as
    granted/refused (STATE_DECISION_OUTCOME_UNKNOWN) - safer to exclude
    than to guess (brief: 'where ambiguous, prefer exclusion')."""
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    site = _make_pending_site(session, submitted_date=submitted, decision="", status="Decided", address="Ambiguous Decided")
    cards = _long_pending_application_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_recommendation_stage_application_is_still_included(session):
    """A recommendation is NOT a formal decision - must still count as
    pending (STATE_RECOMMENDATION_MADE/STATE_RECOMMENDED_FOR_APPROVAL are
    NOT in the terminal/ambiguous exclusion set)."""
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    site = _make_pending_site(
        session, submitted_date=submitted, decision=None, status="Officer Recommendation: Approve", address="Recommended",
    )
    cards = _long_pending_application_cards(session, None)
    assert any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_administrative_filing_category_is_excluded(session):
    """A condition-discharge/variation-style filing is not a substantive
    residential proposal - excluded via app.scrapers.unit_filter.
    EXCLUDE_CATEGORIES even though its status/decision alone would read as
    pending."""
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    site = _make_pending_site(
        session, submitted_date=submitted, application_category="condition_discharge_or_details", address="Admin Filing",
    )
    cards = _long_pending_application_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_unknown_category_is_excluded(session):
    """No confirmed substantive proposal category - excluded (added to
    EXCLUDE_CATEGORIES for this detector specifically per Section 7's own
    'prefer exclusion' instruction)."""
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    site = _make_pending_site(session, submitted_date=submitted, application_category="unknown", address="Unknown Category")
    cards = _long_pending_application_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in cards)


def test_closed_status_administrative_filing_is_still_excluded_by_category(session):
    """A council-specific 'Closed' status text is not recognised as
    terminal by either classify_decision_status or _classify_planning_state
    - this detector relies on application_category (not status text) to
    keep such administrative filings out, proving the category exclusion
    (not just the status classifier) is load-bearing."""
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    site = _make_pending_site(
        session, submitted_date=submitted, status="Closed", application_category="condition_discharge_or_details",
        address="Closed Admin Filing",
    )
    cards = _long_pending_application_cards(session, None)
    assert not any(c["params"]["site_id"] == str(site.id) for c in cards)


# --- Wording: commercially neutral, evidence-safe ------------------------

def test_wording_is_commercially_neutral(session):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    site = _make_pending_site(session, submitted_date=submitted, address="Neutral Wording Site")
    cards = _long_pending_application_cards(session, None)
    matching = [c for c in cards if c["params"]["site_id"] == str(site.id)]
    assert len(matching) == 1
    reason = matching[0]["reason"].lower()
    assert "awaiting determination" in reason
    assert "promoter" not in reason
    assert "sell" not in reason
    assert "available" not in reason


# --- Identity / dedup on multiple pending applications -------------------

def test_stable_site_level_identity_format(session):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    site = _make_pending_site(session, submitted_date=submitted, address="Identity Site")
    universe = build_current_opportunity_universe(session)
    expected_id = planning_delivery_long_pending_application_opportunity_id(site.id)
    assert any(r.opportunity_id == expected_id for r in universe)
    assert expected_id == f"planning_delivery:long_pending_application:{site.id}"


def test_two_separate_pending_applications_on_one_site_produce_one_candidate_using_the_oldest(session):
    """Edge case flagged by Gate 1C amendment Section 10: two genuinely
    separate, currently-pending residential applications on one Site (e.g.
    a full and an outline application filed independently) must still
    produce exactly ONE card - keyed to the OLDER submission date (the one
    that actually crosses the 6-month threshold first), not
    pick_representative_application's own (different) selection rule."""
    older_date = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 4))
    newer_date = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 1))
    site = _make_pending_site(session, submitted_date=older_date, address="Two Pending Apps Site")
    session.add(Application(
        council_code="testcouncil", reference=f"REF-{site.id}-outline", site_id=site.id,
        decision=None, status="Under consideration", application_category="outline_planning",
        application_received=newer_date.strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
    ))
    session.commit()

    cards = _long_pending_application_cards(session, None)
    matching = [c for c in cards if c["params"]["site_id"] == str(site.id)]
    assert len(matching) == 1
    assert older_date.strftime("%d %b %Y") in matching[0]["metric"]


# --- Overlap / precedence with the other three planning-delivery routes --

def test_site_already_recent_permission_never_also_becomes_long_pending(session):
    """A granted, recently-permitted site never also appears as
    long_pending_application - the precedence chain in
    _planning_delivery_universe excludes it before this detector runs."""
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    site = Site(council_code="testcouncil", canonical_address="granted-and-old-app", display_address="Granted And Old App")
    session.add(site)
    session.flush()
    # The original application that was eventually granted - submitted
    # long enough ago that, absent the precedence rule, it would ALSO
    # qualify as long_pending_application.
    session.add(Application(
        council_code="testcouncil", reference=f"REF-{site.id}", site_id=site.id, decision="Granted", status="Granted",
        application_received=submitted.strftime("%a %d %b %Y"),
        decision_issued_date=(dt.date.today() - dt.timedelta(days=10)).strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
        # Gate 2B-2C: resolve_planning_role needs real substantive proposal
        # wording to trust this as the lapse/recent-permission anchor.
        proposal="Erection of 40 dwellings",
    ))
    session.commit()

    universe = build_current_opportunity_universe(session)
    site_ids_by_kind: dict[str, set[int]] = {}
    for r in universe:
        if r.opportunity_id.startswith("planning_delivery:"):
            kind = r.opportunity_id.split(":")[1]
            site_ids_by_kind.setdefault(kind, set()).add(int(r.opportunity_id.split(":")[2]))

    assert site.id in site_ids_by_kind.get("recent_permission", set())
    assert site.id not in site_ids_by_kind.get("long_pending_application", set())


# --- Universe / completeness ---------------------------------------------

def test_new_detector_expands_the_universe_with_no_cap(session):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    for i in range(5):
        _make_pending_site(session, submitted_date=submitted, address=f"Bulk Pending Site {i}")
    universe = build_current_opportunity_universe(session)
    long_pending_records = [r for r in universe if r.opportunity_id.startswith("planning_delivery:long_pending_application:")]
    assert len(long_pending_records) == 5


# --- Fingerprinting --------------------------------------------------------

def test_identical_rescan_produces_an_unchanged_fingerprint(session):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    _make_pending_site(session, submitted_date=submitted, address="Rescan Site")
    universe_1 = build_current_opportunity_universe(session)
    universe_2 = build_current_opportunity_universe(session)
    fp_1 = {r.opportunity_id: r.fingerprint_fields for r in universe_1 if r.opportunity_id.startswith("planning_delivery:long_pending_application:")}
    fp_2 = {r.opportunity_id: r.fingerprint_fields for r in universe_2 if r.opportunity_id.startswith("planning_delivery:long_pending_application:")}
    from app.reporting.opportunity_universe import compute_opportunity_fingerprint
    assert {k: compute_opportunity_fingerprint(v) for k, v in fp_1.items()} == {k: compute_opportunity_fingerprint(v) for k, v in fp_2.items()}


def test_time_passing_alone_does_not_change_the_fingerprint(session):
    """TIME ITSELF MUST CHANGE ELIGIBILITY (universe membership) but must
    NEVER be baked into the fingerprint as a moving day-counter (Gate 1C
    amendment Section 12/20) - simulate the clock advancing (via a later
    submitted_date offset, since fixtures can't move dt.date.today() itself)
    by re-fingerprinting the SAME stable submitted_date twice; the
    fingerprint must be identical both times."""
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    site = _make_pending_site(session, submitted_date=submitted, address="Stable Fingerprint Site")
    universe = build_current_opportunity_universe(session)
    record = next(r for r in universe if r.opportunity_id == planning_delivery_long_pending_application_opportunity_id(site.id))
    assert record.fingerprint_fields.get("submitted_date") is not None
    # The fingerprint field carries the STABLE submitted_date, never a
    # "days pending" count that would silently increment every day.
    assert "days_pending" not in record.fingerprint_fields
    assert "months_pending" not in record.fingerprint_fields


# --- Change semantics / detector-expansion baseline (release-critical) ---

def test_baseline_run_marks_first_ever_long_pending_candidates_as_baseline_existing(session):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    _make_pending_site(session, submitted_date=submitted, address="Baseline Site")
    counts = sync_opportunity_monitoring_state(session)
    assert counts["baseline_existing"] >= 1
    assert counts["new"] == 0


def test_detector_expansion_after_recent_permission_already_baselined_is_baseline_not_new(session):
    """Same release-critical requirement as recent_permission's own test
    (test_recent_permission_opportunities.py), now proven for
    long_pending_application specifically: its first-ever candidates must
    be BASELINE_EXISTING even when OTHER kinds (recent_permission) are
    already tracked - never NEW merely because the table is non-empty."""
    from app.reporting.dashboard import _recent_permission_cards  # noqa: F401  (imported for clarity of intent)

    grant_date = dt.date.today() - dt.timedelta(days=30)
    granted_site = Site(council_code="testcouncil", canonical_address="already-tracked-grant", display_address="Already Tracked Grant")
    session.add(granted_site)
    session.flush()
    session.add(Application(
        council_code="testcouncil", reference=f"REF-{granted_site.id}", site_id=granted_site.id,
        decision="Granted", decision_issued_date=grant_date.strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
        # Gate 2B-2C: resolve_planning_role needs real substantive proposal
        # wording to trust this as the lapse/recent-permission anchor.
        proposal="Erection of 40 dwellings",
    ))
    session.commit()
    first = sync_opportunity_monitoring_state(session)
    assert first["baseline_existing"] >= 1
    assert first["new"] == 0
    assert session.execute(select(OpportunityMonitoringState)).scalars().first() is not None

    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    _make_pending_site(session, submitted_date=submitted, address="Newly Detected Long Pending Site")
    second = sync_opportunity_monitoring_state(session)
    assert second["new"] == 0  # NOT misclassified as new merely because the table already had rows
    assert second["baseline_existing"] >= 1

    state = session.execute(
        select(OpportunityMonitoringState).where(OpportunityMonitoringState.opportunity_id.like("planning_delivery:long_pending_application:%"))
    ).scalars().first()
    assert state is not None
    assert state.last_change_classification == BASELINE_EXISTING


def test_genuinely_new_candidate_after_the_kind_is_baselined_becomes_new(session):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    _make_pending_site(session, submitted_date=submitted, address="First Long Pending Site")
    first = sync_opportunity_monitoring_state(session)
    assert first["baseline_existing"] >= 1

    _make_pending_site(session, submitted_date=submitted, address="Second Long Pending Site")
    second = sync_opportunity_monitoring_state(session)
    assert second["new"] >= 1
    assert second["baseline_existing"] == 0  # the kind is already tracked now


def test_rerun_is_idempotent(session):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    _make_pending_site(session, submitted_date=submitted, address="Idempotent Site")
    sync_opportunity_monitoring_state(session)
    second = sync_opportunity_monitoring_state(session)
    third = sync_opportunity_monitoring_state(session)
    assert second == third


# --- Buyer matching --------------------------------------------------------

def test_long_pending_candidate_flows_into_existing_buyer_matching_unmodified(session):
    """LONG_PENDING_APPLICATION candidates simply flow into the EXISTING,
    unmodified assess_buyer_fit - no new matching rules added, and
    INSUFFICIENT_EVIDENCE is an acceptable, expected outcome for a
    pre-decision application with no SchemeIntelligence yet (Section 21)."""
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    site = _make_pending_site(session, submitted_date=submitted, address="Buyer Match Site")
    universe = build_current_opportunity_universe(session)
    record = next(r for r in universe if r.opportunity_id == planning_delivery_long_pending_application_opportunity_id(site.id))

    for key in BUYER_PROFILE_ORDER:
        assessment = assess_buyer_fit(BUYER_PROFILES[key], record.matching_facts)
        assert assessment.classification is not None  # a real, computable assessment - never a crash or None


# --- Feed integration --------------------------------------------------------

def test_long_pending_application_can_appear_in_generic_feed(session):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    _make_pending_site(session, submitted_date=submitted, address="Feed Site")
    feed = build_opportunity_feed(session, limit=6)
    assert "long_pending_application" in feed["counts"]
    assert feed["counts"]["long_pending_application"] >= 1


def test_generic_feed_remains_bounded_and_does_not_get_overwhelmed(session):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    for i in range(20):
        _make_pending_site(session, submitted_date=submitted, address=f"Bulk Feed Site {i}")
    feed = build_opportunity_feed(session, limit=6)
    assert len(feed["cards"]) <= 6
    assert feed["counts"]["long_pending_application"] >= 1
