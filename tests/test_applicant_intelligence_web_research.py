"""Gate 2A amendment ("Evidence-Grounded Applicant Web Research") - tests
for the new eligibility rules, semantic evidence-sufficiency ceiling, the
person-shaped not_researched fast path, external evidence persistence, and
the strategic-land exclusion/exception regression.

OpenAI is ALWAYS mocked here (unchanged discipline from the original Gate
2A test file) - no real network call is ever made by this file.
"""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import select

from app.db.models import Application, ApplicantIntelligence, LocalPlan, LocalPlanSite, SchemeIntelligence, Site
from app.reporting.applicant_identity import is_likely_individual_name
from app.reporting.applicant_intelligence import (
    CONFIDENCE_HIGH, CONFIDENCE_LOW, CONFIDENCE_MEDIUM, ROLE_LAND_PROMOTER, ROLE_UNKNOWN, SPV_UNKNOWN,
    SOURCE_OFFICIAL_COMPANY_WEBSITE, SOURCE_REPUTABLE_NEWS_SOURCE,
    apply_evidence_sufficiency_ceiling, build_applicant_identity_contexts, estimate_bootstrap_scope,
    evidence_supported_confidence_ceiling, generate_applicant_intelligence, get_applicant_intelligence,
    is_person_shaped_identity, is_planning_opportunity_linked, process_applicant_intelligence_backlog,
    select_priority_identity_refs, validate_applicant_intelligence_output,
)
from app.reporting.opportunity_universe import LONG_PENDING_APPLICATION_WINDOW_MONTHS, add_calendar_months


def _make_site(session, *, address="Test Site", council="testcouncil") -> Site:
    site = Site(council_code=council, canonical_address=f"{address}-canon", display_address=address)
    session.add(site)
    session.flush()
    return site


def _make_long_pending_opportunity(session, *, address, applicant_company, ref, council="testcouncil"):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    site = _make_site(session, address=address, council=council)
    app = Application(
        council_code=council, reference=ref, site_id=site.id, status="Under consideration",
        application_category="primary_residential", application_received=submitted.strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(app)
    session.flush()
    if applicant_company:
        session.add(SchemeIntelligence(application_id=app.id, applicant_company=applicant_company))
    session.commit()
    return site, app


def _ordinary_application(session, site, *, ref, applicant_company):
    """An Application with NO opportunity-candidate signal at all (not
    pending long enough, not recently granted, no phase) - used to prove
    is_planning_opportunity_linked correctly excludes it."""
    app = Application(
        council_code=site.council_code, reference=ref, site_id=site.id, status="Under consideration",
        application_category="primary_residential", application_received=dt.date.today().strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(app)
    session.flush()
    session.add(SchemeIntelligence(application_id=app.id, applicant_company=applicant_company))
    session.commit()
    return app


class _Item:
    def __init__(self, type_):
        self.type = type_


class _FakeResponse:
    def __init__(self, output: dict, web_search_called: bool = False):
        self.output_text = json.dumps(output)
        self.output = [_Item("web_search_call")] if web_search_called else [_Item("message")]


class _FakeClient:
    def __init__(self, output, web_search_called: bool = False):
        self._output = output
        self._web_search_called = web_search_called
        self.calls = 0
        self.responses = self

    def create(self, **kwargs):
        self.calls += 1
        if isinstance(self._output, Exception):
            raise self._output
        return _FakeResponse(self._output, web_search_called=self._web_search_called)


class _NeverCalledClient:
    """A client that fails the test outright if the model is ever invoked -
    used for the person-shaped fast-path (Section 12: zero AI cost)."""
    class _Responses:
        def create(self, **kwargs):
            raise AssertionError("OpenAI must never be called for a person-shaped identity")

    def __init__(self):
        self.responses = self._Responses()


# --- Web research eligibility (Section 1/12/14/24) --------------------------

def test_planning_opportunity_linked_identity_is_eligible(session):
    _make_long_pending_opportunity(session, address="Eligible Site", applicant_company="Eligible Org Ltd", ref="REF-E1")
    contexts = build_applicant_identity_contexts(session)
    ctx = next(c for c in contexts.values() if c.display_name == "Eligible Org Ltd")
    assert is_planning_opportunity_linked(ctx) is True


def test_non_opportunity_application_is_not_eligible_for_processing(session):
    site = _make_site(session)
    _ordinary_application(session, site, ref="REF-ORD-1", applicant_company="Not A Candidate Ltd")
    contexts = build_applicant_identity_contexts(session)
    ctx = next(c for c in contexts.values() if c.display_name == "Not A Candidate Ltd")
    assert is_planning_opportunity_linked(ctx) is False
    assert select_priority_identity_refs(contexts, limit=10) == []  # excluded by default


def test_person_shaped_identity_never_calls_the_model_and_is_not_researched(session):
    site, _ = _make_long_pending_opportunity(session, address="Person Site", applicant_company="Annabel Baker", ref="REF-PERSON")
    contexts = build_applicant_identity_contexts(session)
    ctx = next(c for c in contexts.values() if c.display_name == "Annabel Baker")
    assert is_person_shaped_identity(ctx) is True

    result = generate_applicant_intelligence(session, _NeverCalledClient(), ctx)
    assert result.status == "not_researched"
    assert result.roles == [{"role": ROLE_UNKNOWN, "confidence": CONFIDENCE_LOW, "evidence_refs": []}]
    assert result.web_research_performed is False

    row = get_applicant_intelligence(session, ctx.identity_ref)
    assert row.status == "not_researched"


def test_junk_placeholder_never_becomes_an_identity_at_all(session):
    site, _ = _make_long_pending_opportunity(session, address="Junk Site", applicant_company="See company name", ref="REF-JUNK")
    contexts = build_applicant_identity_contexts(session)
    assert all(c.display_name != "See company name" for c in contexts.values())


def test_organisation_identity_with_org_keyword_is_not_person_shaped(session):
    assert is_likely_individual_name("Bloor Homes") is False
    assert is_likely_individual_name("Peel L&P") is False
    assert is_likely_individual_name("Annabel Baker") is True
    assert is_likely_individual_name("Mr Darran Morrison") is True


# --- Evidence sufficiency (Section 6/10/22) ---------------------------------

def test_raw_name_alone_cannot_support_high_or_medium(session):
    ceiling = evidence_supported_confidence_ceiling(["raw_name:Bloor Homes"], [])
    assert ceiling == CONFIDENCE_LOW


def test_application_count_fact_alone_cannot_support_high_or_medium(session):
    ceiling = evidence_supported_confidence_ceiling(["fact:application_count"], [])
    assert ceiling == CONFIDENCE_LOW


def test_two_weak_internal_refs_together_support_medium_not_high(session):
    ceiling = evidence_supported_confidence_ceiling(["occurrence:REF-1", "occurrence:REF-2"], [])
    assert ceiling == CONFIDENCE_MEDIUM


def test_strong_external_source_supports_high(session):
    evidence = [{"source_type": SOURCE_OFFICIAL_COMPANY_WEBSITE, "title": "x", "url": "https://example.com", "publisher": "x", "claim": "x", "accessed_date": ""}]
    ceiling = evidence_supported_confidence_ceiling(["evidence:0"], evidence)
    assert ceiling == CONFIDENCE_HIGH


def test_medium_external_source_supports_medium_not_high(session):
    evidence = [{"source_type": SOURCE_REPUTABLE_NEWS_SOURCE, "title": "x", "url": "https://example.com", "publisher": "x", "claim": "x", "accessed_date": ""}]
    ceiling = evidence_supported_confidence_ceiling(["evidence:0"], evidence)
    assert ceiling == CONFIDENCE_MEDIUM


def test_company_house_internal_ref_supports_medium_not_high(session):
    ceiling = evidence_supported_confidence_ceiling(["company:ch_status"], [])
    assert ceiling == CONFIDENCE_MEDIUM


def test_apply_evidence_sufficiency_ceiling_downgrades_overclaimed_confidence(session):
    """The Bloor Homes / Onward Homes worked example from the amendment
    brief itself: a role claiming HIGH but citing only a bare raw_name ref
    must be downgraded to LOW, never silently accepted."""
    structured = {
        "roles": [{"role": ROLE_LAND_PROMOTER, "confidence": CONFIDENCE_HIGH, "evidence_refs": ["raw_name:Bloor Homes"]}],
        "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "x", "unresolved_questions": [], "evidence": [],
    }
    adjusted, notes = apply_evidence_sufficiency_ceiling(structured)
    assert adjusted["roles"][0]["confidence"] == CONFIDENCE_LOW
    assert len(notes) == 1
    assert "LAND_PROMOTER" in notes[0]


def test_apply_evidence_sufficiency_ceiling_never_upgrades(session):
    evidence = [{"source_type": SOURCE_OFFICIAL_COMPANY_WEBSITE, "title": "x", "url": "https://example.com", "publisher": "x", "claim": "x", "accessed_date": ""}]
    structured = {
        "roles": [{"role": ROLE_LAND_PROMOTER, "confidence": CONFIDENCE_LOW, "evidence_refs": ["evidence:0"]}],
        "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "x", "unresolved_questions": [], "evidence": evidence,
    }
    adjusted, notes = apply_evidence_sufficiency_ceiling(structured)
    assert adjusted["roles"][0]["confidence"] == CONFIDENCE_LOW  # model's own LOW is never raised to the HIGH ceiling
    assert notes == []


def test_unknown_role_is_never_downgraded_or_flagged(session):
    structured = {
        "roles": [{"role": ROLE_UNKNOWN, "confidence": CONFIDENCE_HIGH, "evidence_refs": []}],
        "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "x", "unresolved_questions": [], "evidence": [],
    }
    adjusted, notes = apply_evidence_sufficiency_ceiling(structured)
    assert adjusted["roles"][0]["confidence"] == CONFIDENCE_HIGH  # UNKNOWN's own "confidence" is not a role-strength claim
    assert notes == []


# --- Web evidence validation (Section 17/29) --------------------------------

def _minimal_context(session, *, applicant="Sample Web Org Ltd"):
    _make_long_pending_opportunity(session, address="Web Evidence Site", applicant_company=applicant, ref="REF-WEB")
    contexts = build_applicant_identity_contexts(session)
    return next(c for c in contexts.values() if c.display_name == applicant)


def test_external_evidence_with_valid_url_is_accepted(session):
    ctx = _minimal_context(session)
    structured = {
        "roles": [{"role": ROLE_UNKNOWN, "confidence": CONFIDENCE_LOW, "evidence_refs": []}],
        "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "x", "unresolved_questions": [],
        "evidence": [{"source_type": SOURCE_OFFICIAL_COMPANY_WEBSITE, "title": "Official site", "url": "https://sampleweborg.co.uk", "publisher": "Sample Web Org", "claim": "Builds homes.", "accessed_date": ""}],
    }
    ok, problems = validate_applicant_intelligence_output(ctx, structured)
    assert ok, problems


def test_malformed_url_is_rejected(session):
    ctx = _minimal_context(session)
    structured = {
        "roles": [{"role": ROLE_UNKNOWN, "confidence": CONFIDENCE_LOW, "evidence_refs": []}],
        "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "x", "unresolved_questions": [],
        "evidence": [{"source_type": SOURCE_OFFICIAL_COMPANY_WEBSITE, "title": "x", "url": "not-a-real-url", "publisher": "x", "claim": "x", "accessed_date": ""}],
    }
    ok, problems = validate_applicant_intelligence_output(ctx, structured)
    assert not ok
    assert any("malformed URL" in p for p in problems)


def test_role_citing_out_of_range_evidence_index_is_rejected(session):
    ctx = _minimal_context(session)
    structured = {
        "roles": [{"role": ROLE_LAND_PROMOTER, "confidence": CONFIDENCE_HIGH, "evidence_refs": ["evidence:0"]}],
        "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "x", "unresolved_questions": [], "evidence": [],
    }
    ok, problems = validate_applicant_intelligence_output(ctx, structured)
    assert not ok
    assert any("unsupported evidence_ref" in p for p in problems)


def test_evidence_persists_with_intelligence(session):
    ctx = _minimal_context(session)
    evidence = [{"source_type": SOURCE_OFFICIAL_COMPANY_WEBSITE, "title": "Official site", "url": "https://sampleweborg.co.uk", "publisher": "Sample Web Org", "claim": "Builds homes.", "accessed_date": ""}]
    client = _FakeClient({
        "roles": [{"role": ROLE_LAND_PROMOTER, "confidence": CONFIDENCE_HIGH, "evidence_refs": ["evidence:0"]}],
        "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "x", "unresolved_questions": [], "evidence": evidence,
    }, web_search_called=True)
    result = generate_applicant_intelligence(session, client, ctx)
    assert result.regenerated
    assert result.web_research_performed is True
    assert len(result.evidence) == 1
    assert result.evidence[0]["accessed_date"] == dt.date.today().isoformat()  # server-set, not model-trusted

    row = get_applicant_intelligence(session, ctx.identity_ref)
    assert row.web_research_performed is True
    stored_evidence = json.loads(row.evidence)
    assert stored_evidence[0]["url"] == "https://sampleweborg.co.uk"


def test_unchanged_identity_does_not_call_the_model_twice(session):
    ctx = _minimal_context(session)
    client = _FakeClient({
        "roles": [{"role": ROLE_UNKNOWN, "confidence": CONFIDENCE_LOW, "evidence_refs": []}],
        "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "x", "unresolved_questions": [], "evidence": [],
    })
    generate_applicant_intelligence(session, client, ctx)
    generate_applicant_intelligence(session, client, ctx)
    assert client.calls == 1


# --- Deduplication (Section 13) ---------------------------------------------

def test_one_entity_across_multiple_opportunities_is_researched_once(session):
    _make_long_pending_opportunity(session, address="Dedup Site A", applicant_company="Dedup Org Ltd", ref="REF-DEDUP-A")
    _make_long_pending_opportunity(session, address="Dedup Site B", applicant_company="Dedup Org Ltd", ref="REF-DEDUP-B")

    call_count = {"n": 0}

    def factory():
        call_count["n"] += 1
        return _FakeClient({
            "roles": [{"role": ROLE_UNKNOWN, "confidence": CONFIDENCE_LOW, "evidence_refs": []}],
            "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "x", "unresolved_questions": [], "evidence": [],
        })

    result = process_applicant_intelligence_backlog(session, factory, limit=10)
    assert result["attempted"] == 1  # ONE identity, even though it touches two Sites/occurrences
    rows = session.execute(select(ApplicantIntelligence)).scalars().all()
    assert len(rows) == 1


# --- Strategic land regression (Section 24) ---------------------------------

def _make_plan(session) -> LocalPlan:
    plan = LocalPlan(council_code="testcouncil", plan_name="Test Local Plan", status="adopted", raw_status="adopted")
    session.add(plan)
    session.commit()
    return plan


def test_strategic_land_only_opportunity_produces_no_applicant_identity(session):
    plan = _make_plan(session)
    allocation = LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan.id, policy_reference="AN1", site_name="Strategic Only Allocation",
        plan_name="Test Local Plan", plan_status="adopted", minimum_dwellings=500, matched_site_id=None,
    )
    session.add(allocation)
    session.commit()

    contexts = build_applicant_identity_contexts(session)
    assert len(contexts) == 0  # no Application exists anywhere - strategic-land-only, correctly produces nothing


def test_strategic_land_site_with_genuine_linked_application_remains_eligible(session):
    """A strategic-land allocation whose matched Site ALSO carries a real,
    long-pending planning application must still produce Applicant
    Intelligence through that Application relationship (Gate 2A amendment
    Section 1's own 'linked exception')."""
    plan = _make_plan(session)
    site, _ = _make_long_pending_opportunity(session, address="Strategic Site With App", applicant_company="Strategic Linked Org Ltd", ref="REF-STRAT-LINK")
    allocation = LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan.id, policy_reference="AN2", site_name="Strategic Allocation With Application",
        plan_name="Test Local Plan", plan_status="adopted", minimum_dwellings=500, matched_site_id=site.id,
    )
    session.add(allocation)
    session.commit()

    contexts = build_applicant_identity_contexts(session)
    ctx = next((c for c in contexts.values() if c.display_name == "Strategic Linked Org Ltd"), None)
    assert ctx is not None
    assert is_planning_opportunity_linked(ctx) is True


def test_strategic_land_opportunity_universe_and_buyer_matching_unaffected(session):
    """Explicit end-to-end regression (Gate 2A amendment Section 24) -
    building the applicant identity index must never change the
    Opportunity Universe's own strategic_land count, and BuyerProfile/
    assess_buyer_fit stay completely untouched."""
    from app.policy.buyer_matching import assess_buyer_fit, build_planning_delivery_matching_facts
    from app.policy.buyer_profiles import BUYER_PROFILES
    from app.reporting.opportunity_universe import build_current_opportunity_universe

    plan = _make_plan(session)
    session.add(LocalPlanSite(
        council_code="testcouncil", local_plan_id=plan.id, policy_reference="AN3", site_name="Untouched Strategic Allocation",
        plan_name="Test Local Plan", plan_status="adopted", minimum_dwellings=200, matched_site_id=None,
    ))
    session.commit()

    universe_before = build_current_opportunity_universe(session)
    strategic_before = len([r for r in universe_before if r.opportunity_type == "strategic_land"])
    build_applicant_identity_contexts(session)  # exercise the new module
    universe_after = build_current_opportunity_universe(session)
    strategic_after = len([r for r in universe_after if r.opportunity_type == "strategic_land"])
    assert strategic_before == strategic_after == 1

    facts = build_planning_delivery_matching_facts(None)
    assessment = assess_buyer_fit(BUYER_PROFILES["nesten_homes"], facts)
    assert assessment.classification is not None


def test_weekly_opportunity_engine_contains_no_openai_calls():
    """Static regression check (Gate 2A amendment Section 26) - mirrors
    app/ui/site_profile_view.py's own established test_no_ai_calls
    pattern: the weekly Opportunity Engine's own source files must never
    reference OpenAI, keeping deterministic opportunity detection and AI
    intelligence processing architecturally separate."""
    from pathlib import Path
    markers = ("import openai", "from openai", "OpenAI(", ".responses.create(")
    for path in ("app/reporting/opportunity_universe.py", "scripts/sync_opportunity_monitoring.py", "app/reporting/opportunity_change.py"):
        source = Path(path).read_text(encoding="utf-8")
        for marker in markers:
            assert marker not in source, f"{path} unexpectedly references {marker!r}"


# --- Bootstrap scope estimate (Section 31) ----------------------------------

def test_estimate_bootstrap_scope_deduplicates_at_entity_level(session):
    _make_long_pending_opportunity(session, address="Estimate Site A", applicant_company="Shared Estimate Org Ltd", ref="REF-EST-A")
    _make_long_pending_opportunity(session, address="Estimate Site B", applicant_company="Shared Estimate Org Ltd", ref="REF-EST-B")
    _make_long_pending_opportunity(session, address="Estimate Site C", applicant_company="Annabel Baker", ref="REF-EST-C")

    result = estimate_bootstrap_scope(session)
    assert result["planning_application_opportunities"] == 3
    assert result["distinct_eligible_organisation_identities"] == 1  # the two Shared Estimate Org occurrences dedupe to one
    assert result["private_person_identities_excluded"] == 1
    assert result["estimated_openai_calls"] == 1
