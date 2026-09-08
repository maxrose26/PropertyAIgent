"""Gate 2A ("Applicant Intelligence") - tests for entity identity
resolution (app.reporting.applicant_identity), the deterministic context
builder, AI schema/grounding validation, fingerprinting, and bounded
processing (app.reporting.applicant_intelligence).

OpenAI is ALWAYS mocked here (Gate 2A Section 33: "Tests must mock OpenAI.
Do not make uncontrolled paid API calls in the test suite.") - no real
network call is ever made by this file.
"""
from __future__ import annotations

import json

from sqlalchemy import select

from app.db.models import (
    Application, ApplicantIntelligence, ApplicationCompany, Company, ControlRelationship, Site, SchemeIntelligence,
)
from app.reporting.applicant_identity import (
    IDENTITY_COMPANY, IDENTITY_NAME, clean_organisation_name, resolve_applicant_identity,
)
from app.reporting.applicant_intelligence import (
    ROLE_UNKNOWN, ROLE_LAND_PROMOTER, ROLE_HOUSEBUILDER, CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    SPV_UNKNOWN, SPV_TRUE, PROMPT_VERSION,
    allowed_evidence_refs, build_applicant_identity_contexts, compute_context_fingerprint,
    generate_applicant_intelligence, get_applicant_intelligence, process_applicant_intelligence_backlog,
    select_priority_identity_refs, should_regenerate, validate_applicant_intelligence_output,
    apply_evidence_sufficiency_ceiling, evidence_supported_confidence_ceiling, is_planning_opportunity_linked,
    is_person_shaped_identity, estimate_bootstrap_scope,
    SOURCE_OFFICIAL_COMPANY_WEBSITE, SOURCE_REPUTABLE_NEWS_SOURCE,
)


def _make_site(session, *, address="Test Site", council="testcouncil") -> Site:
    site = Site(council_code=council, canonical_address=f"{address}-canon", display_address=address)
    session.add(site)
    session.flush()
    return site


def _make_application(
    session, site, *, ref, applicant_company=None, developer=None, applicant_name_raw=None,
    decision=None, status="Under consideration", category="primary_residential",
) -> Application:
    import datetime as dt
    app = Application(
        council_code=site.council_code, reference=ref, site_id=site.id,
        decision=decision, status=status, application_category=category, applicant_name_raw=applicant_name_raw,
        first_seen_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(app)
    session.flush()
    if applicant_company or developer:
        session.add(SchemeIntelligence(application_id=app.id, applicant_company=applicant_company, developer=developer))
    session.commit()
    return app


# --- Identity ----------------------------------------------------------------

def test_individual_applicant_name_is_excluded(session):
    assert clean_organisation_name("Mr Darran Morrison") is None
    assert clean_organisation_name("Mrs. Jane Smith") is None
    assert clean_organisation_name("See company name") is None
    assert clean_organisation_name("-") is None


def test_organisation_name_is_kept(session):
    assert clean_organisation_name("Peel L&P") == "Peel L&P"
    assert clean_organisation_name("Bellway Homes Limited") == "Bellway Homes Limited"


def test_resolves_to_existing_company_when_present(session):
    company = Company(name_raw="XYZ Developments Ltd", name_normalized="xyz developments")
    session.add(company)
    session.commit()
    identity = resolve_applicant_identity(session, "XYZ Developments Ltd")
    assert identity.identity_type == IDENTITY_COMPANY
    assert identity.company_id == company.id


def test_resolves_to_name_based_identity_when_no_company_exists(session):
    identity = resolve_applicant_identity(session, "Unknown Promoter Ltd")
    assert identity.identity_type == IDENTITY_NAME
    assert identity.identity_key


def test_name_variants_do_not_silently_merge_across_different_normalised_forms(session):
    """'Peel L&P' and 'Peel Land and Property' must NOT be forced into the
    same identity by name-based resolution - only a real Company match or
    exact deterministic normalisation may unify identities."""
    a = resolve_applicant_identity(session, "Peel L&P")
    b = resolve_applicant_identity(session, "Peel Land and Property")
    assert a.ref != b.ref


def test_deterministic_normalisation_does_unify_trivial_variants(session):
    a = resolve_applicant_identity(session, "Kirkland Developments Ltd")
    b = resolve_applicant_identity(session, "Kirkland Developments Limited")
    assert a.ref == b.ref  # legal-suffix-only difference - same identity_key


# --- Context -------------------------------------------------------------

def test_context_includes_only_trusted_facts_and_deduplicates_across_sites(session):
    site1 = _make_site(session, address="Site One")
    site2 = _make_site(session, address="Site Two")
    _make_application(session, site1, ref="REF-1", applicant_company="ABC Land Ltd")
    _make_application(session, site2, ref="REF-2", applicant_company="ABC Land Ltd")

    contexts = build_applicant_identity_contexts(session)
    matches = [c for c in contexts.values() if c.display_name == "ABC Land Ltd"]
    assert len(matches) == 1
    ctx = matches[0]
    assert ctx.application_count == 2
    assert ctx.site_count == 2


def test_applicant_and_developer_produce_separate_identities_when_different(session):
    site = _make_site(session)
    _make_application(session, site, ref="REF-1", applicant_company="Agent Co Ltd", developer="Housebuilder Co Ltd")
    contexts = build_applicant_identity_contexts(session)
    names = {c.display_name for c in contexts.values()}
    assert "Agent Co Ltd" in names
    assert "Housebuilder Co Ltd" in names


def test_repeated_application_facts_are_deterministic(session):
    site1 = _make_site(session, address="A")
    site2 = _make_site(session, address="B", council="othercouncil")
    _make_application(session, site1, ref="REF-A", applicant_company="Multi Site Ltd", decision="Granted", status="Decided")
    _make_application(session, site2, ref="REF-B", applicant_company="Multi Site Ltd")
    contexts = build_applicant_identity_contexts(session)
    ctx = next(c for c in contexts.values() if c.display_name == "Multi Site Ltd")
    assert ctx.application_count == 2
    assert ctx.site_count == 2
    assert len(ctx.authorities) == 2
    assert ctx.granted_count == 1
    assert ctx.pending_count == 1


def test_control_evidence_is_kept_separate_from_role_facts(session):
    site = _make_site(session)
    app = _make_application(session, site, ref="REF-1", applicant_company="Owner Evidenced Ltd")
    session.add(ControlRelationship(
        application_id=app.id, site_id=site.id, entity_name_raw="Owner Evidenced Ltd", entity_type="company",
        role="OWNER", evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
        extraction_method="deterministic_regex", confidence="medium",
    ))
    session.commit()
    contexts = build_applicant_identity_contexts(session)
    ctx = next(c for c in contexts.values() if c.display_name == "Owner Evidenced Ltd")
    assert len(ctx.control_evidence) == 1
    assert ctx.control_evidence[0].role == "OWNER"
    # Separate from, never merged into, the AI's own primary_type
    # classification - ApplicantIdentityContext itself carries no
    # classification field at all (that only ever exists on the
    # persisted ApplicantIntelligence row), so control_evidence here can
    # never be confused with a role/type assertion.
    assert not hasattr(ctx, "primary_type")


def test_control_evidence_for_unrelated_organisation_is_not_attached(session):
    """Certificate A evidence for an organisation never otherwise seen as
    applicant/developer must not silently attach to the wrong identity
    (Gate 2A Section 15) - it is simply out of this run's scope."""
    site = _make_site(session)
    app = _make_application(session, site, ref="REF-1", applicant_company="Named Applicant Ltd")
    session.add(ControlRelationship(
        application_id=app.id, site_id=site.id, entity_name_raw="Completely Different Owner Ltd", entity_type="company",
        role="OWNER", evidence_basis="certificate_a_declaration", evidence_category="X",
        extraction_method="deterministic_regex",
    ))
    session.commit()
    contexts = build_applicant_identity_contexts(session)
    applicant_ctx = next(c for c in contexts.values() if c.display_name == "Named Applicant Ltd")
    assert len(applicant_ctx.control_evidence) == 0


# --- Priority --------------------------------------------------------------

def test_priority_puts_long_pending_application_linked_entities_first(session):
    import datetime as dt
    from app.reporting.opportunity_universe import add_calendar_months, LONG_PENDING_APPLICATION_WINDOW_MONTHS

    site_a = _make_site(session, address="Long Pending Site")
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    a = Application(
        council_code="testcouncil", reference="REF-LP", site_id=site_a.id, status="Under consideration",
        application_category="primary_residential", application_received=submitted.strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(a)
    session.flush()
    session.add(SchemeIntelligence(application_id=a.id, applicant_company="Priority Promoter Ltd"))

    site_b = _make_site(session, address="Unrelated Site")
    _make_application(session, site_b, ref="REF-OTHER", applicant_company="Not Prioritised Ltd")
    session.commit()

    contexts = build_applicant_identity_contexts(session)
    priority = select_priority_identity_refs(contexts, limit=1)
    assert contexts[priority[0]].display_name == "Priority Promoter Ltd"


# --- AI schema / grounding ---------------------------------------------------

def _minimal_context(session, *, applicant="Sample Org Ltd"):
    site = _make_site(session)
    _make_application(session, site, ref="REF-1", applicant_company=applicant)
    contexts = build_applicant_identity_contexts(session)
    return next(c for c in contexts.values() if c.display_name == applicant)


def test_valid_grounded_output_passes(session):
    ctx = _minimal_context(session)
    ref = next(iter(allowed_evidence_refs(ctx)))
    structured = {
        "primary_type": ROLE_LAND_PROMOTER, "primary_type_confidence": CONFIDENCE_MEDIUM, "primary_type_evidence_refs": [ref],
        "secondary_roles": [],
        "is_spv": SPV_UNKNOWN, "parent_group": None,
        "summary": "Named as applicant on one application, still pending.",
        "unresolved_questions": [], "evidence": [],
    }
    ok, problems = validate_applicant_intelligence_output(ctx, structured)
    assert ok, problems


def test_unknown_role_needs_no_evidence(session):
    ctx = _minimal_context(session)
    structured = {
        "primary_type": ROLE_UNKNOWN, "primary_type_confidence": CONFIDENCE_HIGH, "primary_type_evidence_refs": [],
        "secondary_roles": [],
        "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "Insufficient evidence to classify.",
        "unresolved_questions": [], "evidence": [],
    }
    ok, problems = validate_applicant_intelligence_output(ctx, structured)
    assert ok, problems


def test_hallucinated_evidence_ref_is_rejected(session):
    ctx = _minimal_context(session)
    structured = {
        "primary_type": ROLE_HOUSEBUILDER, "primary_type_confidence": CONFIDENCE_HIGH, "primary_type_evidence_refs": ["occurrence:DOES-NOT-EXIST"],
        "secondary_roles": [],
        "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "x", "unresolved_questions": [], "evidence": [],
    }
    ok, problems = validate_applicant_intelligence_output(ctx, structured)
    assert not ok
    assert any("unsupported evidence_ref" in p for p in problems)


def test_non_unknown_role_with_no_evidence_is_rejected(session):
    ctx = _minimal_context(session)
    structured = {
        "primary_type": ROLE_HOUSEBUILDER, "primary_type_confidence": CONFIDENCE_HIGH, "primary_type_evidence_refs": [],
        "secondary_roles": [],
        "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "x", "unresolved_questions": [], "evidence": [],
    }
    ok, problems = validate_applicant_intelligence_output(ctx, structured)
    assert not ok
    assert any("no primary_type_evidence_refs" in p for p in problems)


def test_banned_commercial_overreach_phrase_is_rejected(session):
    ctx = _minimal_context(session)
    ref = next(iter(allowed_evidence_refs(ctx)))
    structured = {
        "primary_type": ROLE_LAND_PROMOTER, "primary_type_confidence": CONFIDENCE_MEDIUM, "primary_type_evidence_refs": [ref],
        "secondary_roles": [],
        "is_spv": SPV_UNKNOWN, "parent_group": None,
        "summary": "This site is for sale and represents an acquisition opportunity.",
        "unresolved_questions": [], "evidence": [],
    }
    ok, problems = validate_applicant_intelligence_output(ctx, structured)
    assert not ok
    assert any("disallowed commercial-overreach phrase" in p for p in problems)


def test_parent_group_evidence_ref_must_also_be_grounded(session):
    ctx = _minimal_context(session)
    structured = {
        "primary_type": ROLE_UNKNOWN, "primary_type_confidence": CONFIDENCE_HIGH, "primary_type_evidence_refs": [],
        "secondary_roles": [],
        "is_spv": SPV_UNKNOWN,
        "parent_group": {"name": "Big Group PLC", "confidence": CONFIDENCE_MEDIUM, "evidence_refs": ["company:not_a_real_ref"]},
        "summary": "x", "unresolved_questions": [], "evidence": [],
    }
    ok, problems = validate_applicant_intelligence_output(ctx, structured)
    assert not ok


# --- Fingerprinting ----------------------------------------------------------

def test_unchanged_context_produces_same_fingerprint(session):
    ctx = _minimal_context(session)
    assert compute_context_fingerprint(ctx) == compute_context_fingerprint(ctx)


def test_new_application_changes_fingerprint(session):
    site = _make_site(session)
    _make_application(session, site, ref="REF-1", applicant_company="Change Org Ltd")
    contexts_before = build_applicant_identity_contexts(session)
    ctx_before = next(c for c in contexts_before.values() if c.display_name == "Change Org Ltd")
    fp_before = compute_context_fingerprint(ctx_before)

    _make_application(session, site, ref="REF-2", applicant_company="Change Org Ltd")
    contexts_after = build_applicant_identity_contexts(session)
    ctx_after = next(c for c in contexts_after.values() if c.display_name == "Change Org Ltd")
    fp_after = compute_context_fingerprint(ctx_after)
    assert fp_before != fp_after


def test_should_regenerate_triggers(session):
    assert should_regenerate(None, "abc") is True
    row = ApplicantIntelligence(identity_type="name", identity_key="x", display_name="X", primary_type="NOT_DETERMINED", context_fingerprint="abc", prompt_version=PROMPT_VERSION)
    assert should_regenerate(row, "abc") is False
    assert should_regenerate(row, "different") is True
    assert should_regenerate(row, "abc", force=True) is True
    row.prompt_version = "old-version"
    assert should_regenerate(row, "abc") is True


# --- Orchestration / persistence --------------------------------------------

class _FakeResponse:
    def __init__(self, output: dict, web_search_called: bool = False):
        self.output_text = json.dumps(output)
        # Mirrors the real Responses API's own `output` list of typed items
        # (see app.reporting.applicant_intelligence.generate_applicant_
        # intelligence's own web_research_performed detection) - a plain
        # object with a `.type` attribute stands in for a real
        # ResponseFunctionWebSearch item; no real SDK type needed for tests.
        class _Item:
            def __init__(self, type_):
                self.type = type_
        self.output = [_Item("web_search_call")] if web_search_called else [_Item("message")]


class _FakeClient:
    def __init__(self, output: dict | Exception):
        self._output = output
        self.calls = 0
        self.responses = self

    def create(self, **kwargs):
        self.calls += 1
        if isinstance(self._output, Exception):
            raise self._output
        return _FakeResponse(self._output)


def test_successful_generation_persists_and_reuses(session):
    ctx = _minimal_context(session)
    ref = next(iter(allowed_evidence_refs(ctx)))
    client = _FakeClient({
        "primary_type": ROLE_LAND_PROMOTER, "primary_type_confidence": CONFIDENCE_MEDIUM, "primary_type_evidence_refs": [ref],
        "secondary_roles": [],
        "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "Named as applicant, still pending.",
        "unresolved_questions": [], "evidence": [],
    })
    result = generate_applicant_intelligence(session, client, ctx)
    assert result.regenerated
    assert client.calls == 1

    row = get_applicant_intelligence(session, ctx.identity_ref)
    assert row is not None
    assert row.status == "ok"
    assert row.primary_type == ROLE_LAND_PROMOTER

    # Re-running with an unchanged context and no force must NOT call OpenAI again.
    result2 = generate_applicant_intelligence(session, client, ctx)
    assert result2.regenerated is False
    assert client.calls == 1


def test_rejected_output_does_not_destroy_last_good_result(session):
    ctx = _minimal_context(session)
    ref = next(iter(allowed_evidence_refs(ctx)))
    good_client = _FakeClient({
        "primary_type": ROLE_LAND_PROMOTER, "primary_type_confidence": CONFIDENCE_MEDIUM, "primary_type_evidence_refs": [ref],
        "secondary_roles": [],
        "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "Fine.", "unresolved_questions": [], "evidence": [],
    })
    generate_applicant_intelligence(session, good_client, ctx)
    row = get_applicant_intelligence(session, ctx.identity_ref)
    original_primary_type = row.primary_type

    bad_client = _FakeClient({
        "primary_type": ROLE_LAND_PROMOTER, "primary_type_confidence": CONFIDENCE_MEDIUM, "primary_type_evidence_refs": ["occurrence:FAKE"],
        "secondary_roles": [],
        "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "Fine.", "unresolved_questions": [], "evidence": [],
    })
    result = generate_applicant_intelligence(session, bad_client, ctx, force=True)
    assert result.rejected
    row2 = get_applicant_intelligence(session, ctx.identity_ref)
    assert row2.primary_type == original_primary_type  # unchanged
    assert row2.status == "error"


def test_client_exception_does_not_destroy_last_good_result(session):
    ctx = _minimal_context(session)
    ref = next(iter(allowed_evidence_refs(ctx)))
    good_client = _FakeClient({
        "primary_type": ROLE_LAND_PROMOTER, "primary_type_confidence": CONFIDENCE_MEDIUM, "primary_type_evidence_refs": [ref],
        "secondary_roles": [],
        "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "Fine.", "unresolved_questions": [], "evidence": [],
    })
    generate_applicant_intelligence(session, good_client, ctx)
    original = get_applicant_intelligence(session, ctx.identity_ref).primary_type

    failing_client = _FakeClient(RuntimeError("network error"))
    result = generate_applicant_intelligence(session, failing_client, ctx, force=True)
    assert not result.regenerated
    row = get_applicant_intelligence(session, ctx.identity_ref)
    assert row.primary_type == original
    assert row.status == "error"


# --- Bounded processing ------------------------------------------------------

def _make_long_pending_opportunity(session, *, address, applicant_company, ref):
    """A genuine LONG_PENDING_APPLICATION Opportunity Candidate (Gate 2A
    amendment Section 1/14 - process_applicant_intelligence_backlog now
    only ever selects planning-opportunity-linked identities, so bounded-
    processing tests need real candidates, not merely any Application)."""
    import datetime as dt
    from app.reporting.opportunity_universe import add_calendar_months, LONG_PENDING_APPLICATION_WINDOW_MONTHS

    site = _make_site(session, address=address)
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    app = Application(
        council_code=site.council_code, reference=ref, site_id=site.id, status="Under consideration",
        application_category="primary_residential", application_received=submitted.strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(app)
    session.flush()
    session.add(SchemeIntelligence(application_id=app.id, applicant_company=applicant_company))
    session.commit()
    return site, app


def test_bounded_processing_respects_limit_and_isolates_failures(session):
    for i in range(5):
        _make_long_pending_opportunity(session, address=f"Site {i}", applicant_company=f"Bounded Org {i} Ltd", ref=f"REF-{i}")

    call_count = {"n": 0}

    def factory():
        call_count["n"] += 1
        if call_count["n"] == 2:
            return _FakeClient(RuntimeError("simulated failure"))
        return _FakeClient({
            "primary_type": ROLE_UNKNOWN, "primary_type_confidence": CONFIDENCE_HIGH, "primary_type_evidence_refs": [],
        "secondary_roles": [],
            "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "x", "unresolved_questions": [], "evidence": [],
        })

    result = process_applicant_intelligence_backlog(session, factory, limit=3)
    assert result["attempted"] == 3
    assert result["identities_considered"] == 5


def test_processing_excludes_identities_with_no_opportunity_candidate_link(session):
    """A raw Application with no live Opportunity Candidate signal at all
    (Gate 2A amendment Section 1/14's own scope decision) must never be
    selected by the bounded processing stage, even though it still appears
    in the platform-wide identity index."""
    site = _make_site(session)
    _make_application(session, site, ref="REF-NOT-A-CANDIDATE", applicant_company="Never Processed Ltd")

    result = process_applicant_intelligence_backlog(session, lambda: _FakeClient(RuntimeError("should never be called")), limit=10)
    assert result["attempted"] == 0


def test_rerun_with_unchanged_backlog_is_idempotent(session):
    _make_long_pending_opportunity(session, address="Idempotent Site", applicant_company="Idempotent Org Ltd", ref="REF-1")

    def factory():
        return _FakeClient({
            "primary_type": ROLE_UNKNOWN, "primary_type_confidence": CONFIDENCE_HIGH, "primary_type_evidence_refs": [],
        "secondary_roles": [],
            "is_spv": SPV_UNKNOWN, "parent_group": None, "summary": "x", "unresolved_questions": [], "evidence": [],
        })

    first = process_applicant_intelligence_backlog(session, factory, limit=10)
    assert first["attempted"] >= 1
    second = process_applicant_intelligence_backlog(session, factory, limit=10)
    assert second["attempted"] == 0
    assert second["skipped_fresh"] >= 1

    total_rows = session.execute(select(ApplicantIntelligence)).scalars().all()
    assert len({r.id for r in total_rows}) == len(total_rows)  # no duplicates


# --- Regression --------------------------------------------------------------

def test_opportunity_universe_unaffected_by_applicant_intelligence_module(session):
    """Importing/using app.reporting.applicant_intelligence must never
    change app.reporting.opportunity_universe's own behaviour - Gate 2A
    adds a read-only consumer, never a mutation to Gate 1C's engine."""
    from app.reporting.opportunity_universe import build_current_opportunity_universe
    site = _make_site(session)
    _make_application(session, site, ref="REF-1", applicant_company="Regression Org Ltd")
    universe_before = build_current_opportunity_universe(session)
    build_applicant_identity_contexts(session)  # exercise the new module
    universe_after = build_current_opportunity_universe(session)
    assert len(universe_before) == len(universe_after)


def test_buyer_matching_unaffected(session):
    """assess_buyer_fit must remain callable and unmodified - Applicant
    Intelligence never becomes a deterministic exclusion rule (Gate 2A
    Section 28)."""
    from app.policy.buyer_matching import assess_buyer_fit
    from app.policy.buyer_profiles import BUYER_PROFILES
    from app.policy.buyer_matching import build_planning_delivery_matching_facts
    facts = build_planning_delivery_matching_facts(None)
    assessment = assess_buyer_fit(BUYER_PROFILES["nesten_homes"], facts)
    assert assessment.classification is not None
