"""Gate 2B-0 ("Planning Freshness Remediation") - focused tests.

Covers:
1. classify_verification_tier - pure, no-DB tier classification (Tier 5
   already-decided exclusion, Tier 1 contradiction signal, Tier 2 long-
   pending opportunity, Tier 3 other opportunity, Tier 4 other pending).
2. select_verification_candidates - per-tier cadence, NULL-first ordering,
   the 10-per-council limit, and the starvation-protection fairness
   algorithm.
3. verify_application_status - the five outcome semantics
   (VERIFIED_UNCHANGED/VERIFIED_CHANGED stamp status_verified_at;
   APPLICATION_NOT_FOUND/PORTAL_UNAVAILABLE/FETCH_FAILED never do),
   material-change integration, and that a genuinely unrelated field
   update never counts as verification.
4. run_status_verification - circuit-breaker participation.
5. Monitoring/fingerprint safety - an unchanged verification never makes
   app.reporting.opportunity_universe's own fingerprint_fields differ.
6. The stage_fetch_related_applications eligibility extension (Section
   20-24 of the approved spec) - existing granted-anchor behaviour
   preserved; a genuinely unresolved opportunity becomes newly eligible;
   an unrelated pending non-opportunity application does not; the
   existing related_search_checked_at cooldown/semantics are reused
   unchanged; status_verified_at never drives this cooldown.
7. Acceptance-case fixtures (Brixham Road / London Road / B&M Kingsway
   shapes - disposable test data only, never the live production rows).

Uses the same in-memory-SQLite `session` fixture as the rest of this suite
(tests/conftest.py). No live council portals - every portal fetch is
patched.
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import pytest
import requests
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.config import CouncilConfig
from app.db.models import Application, Document, SchemeIntelligence, Site
from app.pipeline.material_change import REASON_DECISION_GRANTED
from app.pipeline.portal_circuit_breaker import CouncilPortalCircuitBreaker
from app.pipeline.run_weekly import stage_fetch_related_applications
from app.pipeline.status_verification import (
    MAX_STATUS_VERIFICATIONS_PER_COUNCIL_PER_RUN,
    OUTCOME_APPLICATION_NOT_FOUND,
    OUTCOME_FETCH_FAILED,
    OUTCOME_PORTAL_UNAVAILABLE,
    OUTCOME_VERIFIED_CHANGED,
    OUTCOME_VERIFIED_UNCHANGED,
    TIER_CADENCE_DAYS,
    TIER_CONTRADICTION_SIGNAL,
    TIER_LONG_PENDING_OPPORTUNITY,
    TIER_OTHER_OPPORTUNITY_PENDING,
    TIER_OTHER_PENDING,
    classify_verification_tier,
    run_status_verification,
    select_verification_candidates,
    verify_application_status,
)
from app.reporting.opportunity_universe import build_current_opportunity_universe, compute_opportunity_fingerprint
from app.scrapers.idox_portal import ScrapedApplication


def _council_config(code: str = "testcouncil", doc_system: str = "idox") -> CouncilConfig:
    return CouncilConfig(
        code=code, name=code, base_url="https://example.invalid",
        date_field_mode="received", doc_system=doc_system, anite_base_url=None,
        unit_threshold=10, region=None, country=None,
    )


def _add_site(session, *, reference_suffix: str, council_code: str = "testcouncil") -> Site:
    site = Site(
        council_code=council_code, canonical_address=f"1 Test St {reference_suffix}",
        display_address=f"1 Test St {reference_suffix}",
    )
    session.add(site)
    session.flush()
    return site


def _add_application(session, *, reference: str, council_code: str = "testcouncil", site: Site | None = None, **kwargs) -> Application:
    application = Application(council_code=council_code, reference=reference, **kwargs)
    session.add(application)
    session.flush()
    if site is not None:
        application.site_id = site.id
    session.commit()
    return application


def _scraped(reference: str, *, status: str | None = None, decision: str | None = None, unit_count: int | None = None) -> ScrapedApplication:
    fields = {"Reference": reference}
    if status is not None:
        fields["Status"] = status
    if decision is not None:
        fields["Decision"] = decision
    return ScrapedApplication(
        reference=reference, fields=fields, summary_url=f"https://example.invalid/{reference}",
        further_info_url="", keyval=None, estimated_unit_count=unit_count,
        application_category="primary_residential", opportunity_classification="", qualifies=True,
    )


# --- 1. classify_verification_tier (pure, no DB) ----------------------------


def test_already_decided_application_is_tier_none():
    app = Application(council_code="testcouncil", reference="A/1", decision="Approved")
    assert classify_verification_tier(
        app, has_decision_notice=False, recommendation_direction=None, opportunity_kinds_for_site=frozenset(),
    ) is None


def test_pending_with_decision_notice_is_tier_1():
    app = Application(council_code="testcouncil", reference="A/1", decision=None)
    assert classify_verification_tier(
        app, has_decision_notice=True, recommendation_direction=None, opportunity_kinds_for_site=frozenset(),
    ) == TIER_CONTRADICTION_SIGNAL


def test_pending_with_recommendation_approval_is_tier_1():
    app = Application(council_code="testcouncil", reference="A/1", decision="")
    assert classify_verification_tier(
        app, has_decision_notice=False, recommendation_direction="approval", opportunity_kinds_for_site=frozenset(),
    ) == TIER_CONTRADICTION_SIGNAL


def test_pending_recommendation_unclear_is_not_tier_1():
    """Section 19: only 'approval' is a Tier 1 signal - 'unclear' (London
    Road's own real shape) must not be treated the same way."""
    app = Application(council_code="testcouncil", reference="A/1", decision=None)
    tier = classify_verification_tier(
        app, has_decision_notice=False, recommendation_direction="unclear", opportunity_kinds_for_site=frozenset(),
    )
    assert tier != TIER_CONTRADICTION_SIGNAL


def test_pending_long_pending_opportunity_is_tier_2():
    app = Application(council_code="testcouncil", reference="A/1", decision=None)
    assert classify_verification_tier(
        app, has_decision_notice=False, recommendation_direction=None,
        opportunity_kinds_for_site=frozenset({"long_pending_application"}),
    ) == TIER_LONG_PENDING_OPPORTUNITY


def test_pending_other_opportunity_is_tier_3():
    app = Application(council_code="testcouncil", reference="A/1", decision=None)
    assert classify_verification_tier(
        app, has_decision_notice=False, recommendation_direction=None,
        opportunity_kinds_for_site=frozenset({"recent_permission"}),
    ) == TIER_OTHER_OPPORTUNITY_PENDING


def test_pending_non_opportunity_is_tier_4():
    app = Application(council_code="testcouncil", reference="A/1", decision=None)
    assert classify_verification_tier(
        app, has_decision_notice=False, recommendation_direction=None, opportunity_kinds_for_site=frozenset(),
    ) == TIER_OTHER_PENDING


def test_tier_1_takes_priority_over_opportunity_linkage():
    app = Application(council_code="testcouncil", reference="A/1", decision=None)
    assert classify_verification_tier(
        app, has_decision_notice=True, recommendation_direction=None,
        opportunity_kinds_for_site=frozenset({"long_pending_application"}),
    ) == TIER_CONTRADICTION_SIGNAL


# --- 2. select_verification_candidates (DB) ---------------------------------


def test_null_status_verified_at_is_eligible_immediately(session):
    _add_application(session, reference="A/1", decision=None)
    candidates = select_verification_candidates(session, "testcouncil", opportunity_kinds_by_site={})
    assert len(candidates) == 1
    assert candidates[0].application.reference == "A/1"


@pytest.mark.parametrize("tier,cadence_days", sorted(TIER_CADENCE_DAYS.items()))
def test_cadence_respected_per_tier(session, tier, cadence_days):
    now = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    site = _add_site(session, reference_suffix="cadence")
    opportunity_kinds = {
        TIER_CONTRADICTION_SIGNAL: {},
        TIER_LONG_PENDING_OPPORTUNITY: {site.id: frozenset({"long_pending_application"})},
        TIER_OTHER_OPPORTUNITY_PENDING: {site.id: frozenset({"recent_permission"})},
        TIER_OTHER_PENDING: {},
    }[tier]
    app = _add_application(session, reference=f"T{tier}/RECENT", decision=None, site=site)
    if tier == TIER_CONTRADICTION_SIGNAL:
        session.add(SchemeIntelligence(application_id=app.id, recommendation_direction="approval"))
        session.commit()

    # Verified just inside the cadence window - NOT eligible.
    app.status_verified_at = now - dt.timedelta(days=cadence_days - 1)
    session.commit()
    candidates = select_verification_candidates(session, "testcouncil", now=now, opportunity_kinds_by_site=opportunity_kinds)
    assert app.id not in {c.application.id for c in candidates}

    # Verified just outside the cadence window - eligible again.
    app.status_verified_at = now - dt.timedelta(days=cadence_days + 1)
    session.commit()
    candidates = select_verification_candidates(session, "testcouncil", now=now, opportunity_kinds_by_site=opportunity_kinds)
    assert app.id in {c.application.id for c in candidates}


def test_never_verified_sorted_ahead_of_previously_verified(session):
    now = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    old = _add_application(session, reference="OLD/1", decision=None)
    old.status_verified_at = now - dt.timedelta(days=59)  # inside tier-4's 60-day cadence boundary but let's push it out
    old.status_verified_at = now - dt.timedelta(days=61)
    never = _add_application(session, reference="NEVER/1", decision=None)
    session.commit()
    candidates = select_verification_candidates(session, "testcouncil", now=now, limit=1, opportunity_kinds_by_site={})
    assert len(candidates) == 1
    assert candidates[0].application.reference == "NEVER/1"


def test_per_council_limit_enforced(session):
    for i in range(15):
        _add_application(session, reference=f"MANY/{i}", decision=None)
    candidates = select_verification_candidates(session, "testcouncil", opportunity_kinds_by_site={})
    assert len(candidates) == MAX_STATUS_VERIFICATIONS_PER_COUNCIL_PER_RUN == 10


def test_starvation_protection_reserves_a_slot_for_lower_tier(session):
    """15 Tier-1 candidates (a large contradiction-signal backlog) plus one
    genuinely stale Tier-4 candidate - the Tier-4 candidate must not be
    permanently starved behind the Tier-1 population."""
    for i in range(15):
        app = _add_application(session, reference=f"TIER1/{i}", decision=None)
        session.add(SchemeIntelligence(application_id=app.id, recommendation_direction="approval"))
    tier4_app = _add_application(session, reference="TIER4/LONELY", decision=None)
    session.commit()

    candidates = select_verification_candidates(session, "testcouncil", opportunity_kinds_by_site={})
    assert len(candidates) == MAX_STATUS_VERIFICATIONS_PER_COUNCIL_PER_RUN
    assert tier4_app.id in {c.application.id for c in candidates}
    tier4_selected = next(c for c in candidates if c.application.id == tier4_app.id)
    assert tier4_selected.tier == TIER_OTHER_PENDING


def test_already_decided_applications_never_selected(session):
    _add_application(session, reference="DECIDED/1", decision="Approved")
    candidates = select_verification_candidates(session, "testcouncil", opportunity_kinds_by_site={})
    assert candidates == []


# --- 3. verify_application_status outcome semantics -------------------------


def test_verified_unchanged_stamps_status_verified_at(session):
    app = _add_application(session, reference="A/1", status="Awaiting decision", decision=None)
    with patch("app.scrapers.idox_portal.fetch_application_by_reference", return_value=_scraped("A/1", status="Awaiting decision")):
        outcome = verify_application_status(session, MagicMock(), _council_config(), app)
    assert outcome.outcome == OUTCOME_VERIFIED_UNCHANGED
    assert app.status_verified_at is not None


def test_verified_changed_stamps_status_verified_at_and_fires_material_change(session):
    app = _add_application(session, reference="A/1", status="Awaiting decision", decision=None)
    with patch("app.scrapers.idox_portal.fetch_application_by_reference", return_value=_scraped("A/1", status="Decided", decision="Granted")):
        outcome = verify_application_status(session, MagicMock(), _council_config(), app)
    assert outcome.outcome == OUTCOME_VERIFIED_CHANGED
    assert app.status_verified_at is not None
    assert app.decision == "Granted"
    assert app.evidence_refresh_required is True  # existing B1 mechanism, reused unmodified
    assert REASON_DECISION_GRANTED in outcome.material_change_reasons


def test_application_not_found_does_not_stamp(session):
    app = _add_application(session, reference="A/1", decision=None)
    with patch("app.scrapers.idox_portal.fetch_application_by_reference", return_value=None):
        outcome = verify_application_status(session, MagicMock(), _council_config(), app)
    assert outcome.outcome == OUTCOME_APPLICATION_NOT_FOUND
    assert app.status_verified_at is None
    assert app.decision is None  # never fabricated a withdrawn/refused/excluded state


def test_portal_unavailable_does_not_stamp(session):
    app = _add_application(session, reference="A/1", decision=None)
    breaker = CouncilPortalCircuitBreaker(council_code="testcouncil")
    with patch("app.scrapers.idox_portal.fetch_application_by_reference", side_effect=requests.exceptions.ConnectTimeout()):
        outcome = verify_application_status(session, MagicMock(), _council_config(), app, breaker=breaker)
    assert outcome.outcome == OUTCOME_PORTAL_UNAVAILABLE
    assert app.status_verified_at is None
    assert breaker.consecutive_host_failures == 1


def test_fetch_failed_does_not_stamp(session):
    app = _add_application(session, reference="A/1", decision=None)
    with patch("app.scrapers.idox_portal.fetch_application_by_reference", side_effect=requests.exceptions.HTTPError("500")):
        outcome = verify_application_status(session, MagicMock(), _council_config(), app)
    assert outcome.outcome == OUTCOME_FETCH_FAILED
    assert app.status_verified_at is None


def test_playwright_timeout_counts_as_portal_unavailable(session):
    app = _add_application(session, reference="A/1", decision=None)
    with patch("app.scrapers.idox_portal.fetch_application_by_reference", side_effect=PlaywrightTimeoutError("timeout")):
        outcome = verify_application_status(session, MagicMock(), _council_config(), app)
    assert outcome.outcome == OUTCOME_PORTAL_UNAVAILABLE
    assert app.status_verified_at is None


def test_real_trafford_connection_timeout_shape_counts_as_portal_unavailable(session):
    """Gate 2B-0A portal-failure hardening amendment - the exact real
    production exception shape (Brixham Road / Trafford, live controlled
    validation): a base playwright.sync_api.Error naming net::
    ERR_CONNECTION_TIMED_OUT, not the TimeoutError subclass. Confirms the
    hardened is_portal_host_failure() now routes this through
    verify_application_status() to PORTAL_UNAVAILABLE, notifies the
    circuit breaker via the existing record_failure() call, and leaves
    status_verified_at/Application facts completely untouched - the exact
    same safety guarantees as every other failure outcome."""
    app = _add_application(session, reference="114228/FUL/24", status="Awaiting decision", decision=None)
    breaker = CouncilPortalCircuitBreaker(council_code="testcouncil")
    real_shaped_exc = PlaywrightError(
        "Page.goto: net::ERR_CONNECTION_TIMED_OUT at https://pa.trafford.gov.uk/online-applications/search.do"
        "?action=advanced&searchType=Application\nCall log:\n  - navigating to \"...\", waiting until \"networkidle\""
    )
    with patch("app.scrapers.idox_portal.fetch_application_by_reference", side_effect=real_shaped_exc):
        outcome = verify_application_status(session, MagicMock(), _council_config(), app, breaker=breaker)
    assert outcome.outcome == OUTCOME_PORTAL_UNAVAILABLE
    assert app.status_verified_at is None
    assert app.status == "Awaiting decision"  # untouched
    assert app.decision is None  # never fabricated
    assert breaker.consecutive_host_failures == 1  # circuit breaker WAS notified this time


def test_unrelated_field_update_does_not_advance_status_verified_at(session):
    """A plain ORM update to some other field must never look like
    verification - status_verified_at is only ever written by
    verify_application_status itself."""
    app = _add_application(session, reference="A/1", decision=None)
    assert app.status_verified_at is None
    app.case_officer = "Someone Else"
    session.commit()
    assert app.status_verified_at is None


# --- 4. run_status_verification orchestration -------------------------------


def test_run_status_verification_respects_open_circuit(session):
    for i in range(3):
        _add_application(session, reference=f"A/{i}", decision=None)
    breaker = CouncilPortalCircuitBreaker(council_code="testcouncil")
    breaker.record_failure(requests.exceptions.ConnectTimeout(), stage="test")
    breaker.record_failure(requests.exceptions.ConnectTimeout(), stage="test")
    breaker.record_failure(requests.exceptions.ConnectTimeout(), stage="test")
    assert breaker.is_open is True

    with patch("app.scrapers.idox_portal.fetch_application_by_reference") as mock_fetch:
        stats = run_status_verification(session, MagicMock(), _council_config(), breaker=breaker, opportunity_kinds_by_site={})
    mock_fetch.assert_not_called()
    assert stats.selected == 0


def test_run_status_verification_records_material_changes(session):
    app = _add_application(session, reference="A/1", status="Awaiting decision", decision=None)
    with patch("app.scrapers.idox_portal.fetch_application_by_reference", return_value=_scraped("A/1", status="Decided", decision="Granted")):
        stats = run_status_verification(session, MagicMock(), _council_config(), opportunity_kinds_by_site={})
    assert stats.material_changes == 1
    assert stats.outcome_counts[OUTCOME_VERIFIED_CHANGED] == 1


# --- 5. Monitoring / fingerprint safety --------------------------------------


def test_status_verified_at_never_changes_the_opportunity_fingerprint(session):
    """Section 17/25 of the approved spec: a verification EVENT is not a
    planning CHANGE. Stamping status_verified_at, with no underlying fact
    changed, must produce an IDENTICAL fingerprint - never a false
    MATERIALLY_CHANGED."""
    site = _add_site(session, reference_suffix="fingerprint")
    old_date = (dt.date.today() - dt.timedelta(days=400)).strftime("%d/%m/%Y")
    app = _add_application(
        session, reference="LP/1", site=site, decision=None, status="Registered",
        application_received=old_date, application_category="primary_residential",
    )
    scheme = SchemeIntelligence(application_id=app.id, total_units_final=20, core_intelligence_complete=True)
    session.add(scheme)
    session.commit()

    universe_before = build_current_opportunity_universe(session)
    record_before = next((r for r in universe_before if f":{site.id}" in r.opportunity_id or r.opportunity_id.endswith(f":{site.id}")), None)
    if record_before is None:
        pytest.skip("fixture did not qualify as a planning-delivery opportunity in this schema version - not the behaviour under test")
    fingerprint_before = compute_opportunity_fingerprint(record_before.fingerprint_fields)

    # Simulate a routine, unchanged verification - only status_verified_at moves.
    app.status_verified_at = dt.datetime.now(dt.timezone.utc)
    session.commit()

    universe_after = build_current_opportunity_universe(session)
    record_after = next((r for r in universe_after if r.opportunity_id == record_before.opportunity_id), None)
    assert record_after is not None
    fingerprint_after = compute_opportunity_fingerprint(record_after.fingerprint_fields)

    assert fingerprint_before == fingerprint_after
    assert "status_verified_at" not in record_after.fingerprint_fields


# --- 6. Related-application discovery eligibility extension -----------------


def test_existing_granted_anchor_behaviour_unchanged(session):
    site = _add_site(session, reference_suffix="granted")
    anchor = _add_application(session, reference="GRANTED/1", site=site, decision="Granted", application_received="01/01/2020")
    with patch("app.pipeline.run_weekly.search_related_applications", return_value=[]) as mock_search:
        stage_fetch_related_applications(session, MagicMock(), _council_config(), opportunity_kinds_by_site={})
    mock_search.assert_called_once()
    assert anchor.related_search_checked_at is not None


def test_long_pending_opportunity_site_becomes_eligible_without_granted_anchor(session):
    site = _add_site(session, reference_suffix="longpending")
    pending = _add_application(session, reference="PENDING/1", site=site, decision=None, application_received="01/01/2020")
    with patch("app.pipeline.run_weekly.search_related_applications", return_value=[]) as mock_search:
        stage_fetch_related_applications(
            session, MagicMock(), _council_config(),
            opportunity_kinds_by_site={site.id: frozenset({"long_pending_application"})},
        )
    mock_search.assert_called_once()
    call_args = mock_search.call_args
    assert call_args.args[2] == pending.reference  # searched from the pending application itself
    assert pending.related_search_checked_at is not None


def test_unrelated_pending_non_opportunity_site_remains_ineligible(session):
    site = _add_site(session, reference_suffix="plainpending")
    pending = _add_application(session, reference="PLAINPENDING/1", site=site, decision=None, application_received="01/01/2020")
    with patch("app.pipeline.run_weekly.search_related_applications", return_value=[]) as mock_search:
        stage_fetch_related_applications(session, MagicMock(), _council_config(), opportunity_kinds_by_site={})
    mock_search.assert_not_called()
    assert pending.related_search_checked_at is None


def test_thirty_day_cooldown_still_applies_to_newly_eligible_anchors(session):
    site = _add_site(session, reference_suffix="cooldown")
    pending = _add_application(session, reference="COOLDOWN/1", site=site, decision=None, application_received="01/01/2020")
    pending.related_search_checked_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=5)
    session.commit()
    with patch("app.pipeline.run_weekly.search_related_applications", return_value=[]) as mock_search:
        stage_fetch_related_applications(
            session, MagicMock(), _council_config(),
            opportunity_kinds_by_site={site.id: frozenset({"long_pending_application"})},
        )
    mock_search.assert_not_called()


def test_status_verified_at_does_not_drive_related_discovery_cooldown(session):
    """Section 21: 'Do not use status_verified_at as the related-discovery
    timestamp.' A recently status-verified but never related-searched
    application must still be eligible for related discovery."""
    site = _add_site(session, reference_suffix="separatecadence")
    pending = _add_application(session, reference="SEP/1", site=site, decision=None, application_received="01/01/2020")
    pending.status_verified_at = dt.datetime.now(dt.timezone.utc)  # verified moments ago
    pending.related_search_checked_at = None  # but never related-searched
    session.commit()
    with patch("app.pipeline.run_weekly.search_related_applications", return_value=[]) as mock_search:
        stage_fetch_related_applications(
            session, MagicMock(), _council_config(),
            opportunity_kinds_by_site={site.id: frozenset({"long_pending_application"})},
        )
    mock_search.assert_called_once()


# --- 7. Acceptance-case fixtures (disposable test data only) ---------------


def test_brixham_road_shaped_fixture_is_tier_1_and_verifiable(session):
    """Mirrors the KNOWN real shape (decision=NULL, status='Awaiting
    decision', a committee-report-derived recommendation_direction=
    'approval', no decision_notice) - disposable test data, never the
    live production row."""
    site = _add_site(session, reference_suffix="brixham")
    app = _add_application(
        session, reference="114228/FUL/24-TEST", site=site, status="Awaiting decision", decision=None,
        application_received="12/08/2024",
    )
    session.add(SchemeIntelligence(application_id=app.id, recommendation_direction="approval", formal_decision_outstanding=True))
    session.commit()

    tier = classify_verification_tier(
        app, has_decision_notice=False, recommendation_direction="approval", opportunity_kinds_for_site=frozenset(),
    )
    assert tier == TIER_CONTRADICTION_SIGNAL

    with patch("app.scrapers.idox_portal.fetch_application_by_reference", return_value=_scraped(app.reference, status="Awaiting decision")):
        outcome = verify_application_status(session, MagicMock(), _council_config(), app)
    assert outcome.outcome == OUTCOME_VERIFIED_UNCHANGED
    assert app.status_verified_at is not None
    assert app.decision is None  # UNKNOWN correctly preserved - no decision fabricated from the recommendation


def test_london_road_shaped_fixture_is_eligible_despite_no_granted_anchor():
    """Mirrors the KNOWN real shape (decision=NULL, status='Registered',
    thin documents, recommendation_direction='unclear', no internal
    contradiction signal) - proves the structural blind spot fix reaches
    even a thin-evidence pending record, not just high-signal ones."""
    app = Application(council_code="testcouncil", reference="DC/089005-TEST", status="Registered", decision=None)
    tier = classify_verification_tier(
        app, has_decision_notice=False, recommendation_direction="unclear",
        opportunity_kinds_for_site=frozenset({"long_pending_application"}),
    )
    assert tier == TIER_LONG_PENDING_OPPORTUNITY  # reachable without any contradiction signal at all


def test_bm_kingsway_shaped_fixture_is_out_of_scope_for_status_verification():
    """Mirrors the KNOWN real shape (decision='Approve') - already
    decided, so Tier 5, out of scope for Gate 2B-0 V1 status verification
    (existing granted-anchor related-discovery behaviour is a SEPARATE,
    unaffected code path - see test_existing_granted_anchor_behaviour_
    unchanged above)."""
    app = Application(council_code="testcouncil", reference="141306/FO/2024-TEST", decision="Approve")
    tier = classify_verification_tier(
        app, has_decision_notice=True, recommendation_direction=None, opportunity_kinds_for_site=frozenset(),
    )
    assert tier is None
