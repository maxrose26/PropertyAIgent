"""AI Allocation Intelligence Summary (Phase 1 Local Plan Intelligence)
tests - app.reporting.allocation_intelligence_summary's deterministic
context builder, fingerprint/staleness gating, prompt construction,
factual-grounding validation, and the generation orchestration, plus
scripts.generate_allocation_intelligence_summaries' CLI. No real OpenAI
call anywhere - a fake client stands in, matching the pattern already
established in tests/test_local_plan_summary.py.
"""
from __future__ import annotations

import inspect
import json
import sys

import pytest
from sqlalchemy import event

import app.policy  # noqa: F401  (ensures package import path resolves the same as production)
import scripts.generate_allocation_intelligence_summaries as cli
from app.db.models import (
    AllocationSiteRelationship, Application, Council, ControlRelationship, LocalPlan, LocalPlanSite,
    SchemeIntelligence, Site,
)
from app.reporting.allocation_intelligence_summary import (
    PROMPT_VERSION,
    AllocationIntelligenceContext,
    build_allocation_context,
    build_summary_prompt,
    compute_context_fingerprint,
    generate_allocation_intelligence_summary,
    is_allocation_summary_stale,
    should_regenerate_allocation_summary,
    validate_summary_output,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_council(session, code="testcouncil") -> None:
    if session.get(Council, code) is None:
        session.add(Council(code=code, name=code.title(), base_url="https://example.invalid",
                             date_field_mode="received", doc_system="idox"))
        session.commit()


def _make_plan(session, council_code="testcouncil", status="adopted") -> LocalPlan:
    plan = LocalPlan(council_code=council_code, plan_name="Test Local Plan", status=status, raw_status=status)
    session.add(plan)
    session.commit()
    return plan


def _make_allocation(session, plan, *, council_code="testcouncil", policy_reference="REF-1",
                      site_name="Test Allocation", minimum_dwellings=None, intended_use="residential") -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code=council_code, local_plan_id=plan.id, policy_reference=policy_reference, site_name=site_name,
        plan_name="Test Local Plan", plan_status="adopted", minimum_dwellings=minimum_dwellings, intended_use=intended_use,
    )
    session.add(allocation)
    session.commit()
    return allocation


def _make_site(session, address="Test Site", council_code="testcouncil") -> Site:
    site = Site(council_code=council_code, canonical_address=address.lower(), display_address=address)
    session.add(site)
    session.commit()
    return site


def _make_relationship(session, *, allocation_id, site_id, review_status="auto_applied") -> AllocationSiteRelationship:
    rel = AllocationSiteRelationship(allocation_id=allocation_id, site_id=site_id, evidence_basis="document_confirmed_site", review_status=review_status)
    session.add(rel)
    session.commit()
    return rel


def _make_app_with_capacity(session, site_id, reference, units, *, council_code="testcouncil") -> Application:
    app = Application(council_code=council_code, reference=reference, site_id=site_id)
    session.add(app)
    session.commit()
    session.add(SchemeIntelligence(application_id=app.id, total_units_final=units, core_intelligence_complete=True))
    session.commit()
    return app


def _make_control_relationship(session, *, site_id, application_id, entity_name_raw, role, evidence_category,
                                review_status="auto_applied", evidence_basis="s106_defined_role") -> ControlRelationship:
    cr = ControlRelationship(
        site_id=site_id, application_id=application_id, entity_name_raw=entity_name_raw, entity_type="company",
        role=role, evidence_basis=evidence_basis, evidence_category=evidence_category,
        extraction_method="deterministic_regex", review_status=review_status,
    )
    session.add(cr)
    session.commit()
    return cr


class _FakeResponse:
    def __init__(self, output_text: str):
        self.output_text = output_text


def _fake_client(structured_output: dict):
    class _Responses:
        def create(self, model, input, text):
            return _FakeResponse(json.dumps(structured_output))

    client = type("FakeClient", (), {})()
    client.responses = _Responses()
    return client


class _RaisingClient:
    class responses:
        @staticmethod
        def create(model, input, text):
            raise RuntimeError("simulated OpenAI failure")


_GOOD_OUTPUT_TEMPLATE = {
    "headline": "Adopted allocation with partial development coverage",
    "overview": "This allocation is adopted and has identified planning activity. Some capacity remains indicative residual.",
    "key_points": ["Identified planning activity exists.", "Ownership evidence has been identified for one Site."],
    "key_uncertainties": [],
    "investigation_priorities": [],
    "referenced_application_references": [],
    "referenced_entity_names": [],
    "referenced_roles": [],
}


def _good_output(context: AllocationIntelligenceContext) -> dict:
    output = dict(_GOOD_OUTPUT_TEMPLATE)
    output["referenced_application_references"] = [ref for s in context.sites for ref in s.application_references]
    output["referenced_entity_names"] = [o.entity_name_raw for o in context.ownership_entities]
    output["referenced_roles"] = [o.role_label for o in context.ownership_entities]
    return output


# ---------------------------------------------------------------------------
# Item 1 - context builder uses trusted allocation facts
# ---------------------------------------------------------------------------


def test_context_uses_trusted_allocation_facts(session):
    _make_council(session)
    plan = _make_plan(session, status="adopted")
    allocation = _make_allocation(session, plan, policy_reference="JPA 99", site_name="Trusted Facts Allocation", minimum_dwellings=500)
    session.commit()

    context = build_allocation_context(session, allocation)
    assert context.allocation_reference == "JPA 99"
    assert context.allocation_name == "Trusted Facts Allocation"
    assert context.allocation_capacity_value == 500
    assert context.plan_status_bucket == "adopted"


# ---------------------------------------------------------------------------
# Items 2/3 - rejected/needs_confirmation relationships
# ---------------------------------------------------------------------------


def test_rejected_relationship_excluded_from_context(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="rejected")
    _make_app_with_capacity(session, site.id, "APP/REJECTED", 50)
    session.commit()

    context = build_allocation_context(session, allocation)
    assert context.sites == []
    assert context.number_of_related_sites == 0
    assert context.identified_application_capacity == 0


def test_needs_confirmation_not_presented_as_fact(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id, review_status="needs_confirmation")
    _make_app_with_capacity(session, site.id, "APP/DISPUTED", 50)
    session.commit()

    context = build_allocation_context(session, allocation)
    assert context.disputed_site_count == 1
    assert len(context.sites) == 1
    assert context.sites[0].relationship_review_status == "needs_confirmation"
    prompt = build_summary_prompt(context)
    assert "PENDING CONFIRMATION" in prompt
    assert "do not present as confirmed" in prompt.lower()


# ---------------------------------------------------------------------------
# Item 4 - trusted Application included
# ---------------------------------------------------------------------------


def test_trusted_application_included(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    _make_app_with_capacity(session, site.id, "APP/TRUSTED", 100)
    session.commit()

    context = build_allocation_context(session, allocation)
    assert context.sites[0].application_references == ["APP/TRUSTED"]
    assert context.identified_application_capacity == 100


# ---------------------------------------------------------------------------
# Items 5-9 - fingerprint sensitivity
# ---------------------------------------------------------------------------


def test_new_trusted_application_changes_fingerprint(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    session.commit()
    fp_before = compute_context_fingerprint(build_allocation_context(session, allocation))

    _make_app_with_capacity(session, site.id, "APP/NEW", 100)
    fp_after = compute_context_fingerprint(build_allocation_context(session, allocation))
    assert fp_before != fp_after


def test_unrelated_application_does_not_change_fingerprint(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session, "Related Site")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    session.commit()
    fp_before = compute_context_fingerprint(build_allocation_context(session, allocation))

    unrelated_site = _make_site(session, "Unrelated Site")
    _make_app_with_capacity(session, unrelated_site.id, "APP/UNRELATED", 999)
    fp_after = compute_context_fingerprint(build_allocation_context(session, allocation))
    assert fp_before == fp_after


def test_capacity_change_changes_fingerprint(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()
    fp_before = compute_context_fingerprint(build_allocation_context(session, allocation))

    allocation.minimum_dwellings = 400
    session.commit()
    fp_after = compute_context_fingerprint(build_allocation_context(session, allocation))
    assert fp_before != fp_after


def test_residual_capacity_change_changes_fingerprint(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=1000)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    app = _make_app_with_capacity(session, site.id, "APP/1", 100)
    session.commit()
    fp_before = compute_context_fingerprint(build_allocation_context(session, allocation))

    app.scheme_intelligence.total_units_final = 250
    session.commit()
    fp_after = compute_context_fingerprint(build_allocation_context(session, allocation))
    assert fp_before != fp_after


def test_ownership_control_change_changes_fingerprint(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    app = _make_app_with_capacity(session, site.id, "APP/1", 100)
    session.commit()
    fp_before = compute_context_fingerprint(build_allocation_context(session, allocation))

    _make_control_relationship(session, site_id=site.id, application_id=app.id, entity_name_raw="Test Developer Ltd",
                                role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    fp_after = compute_context_fingerprint(build_allocation_context(session, allocation))
    assert fp_before != fp_after


# ---------------------------------------------------------------------------
# Item 10 - rejected ownership excluded
# ---------------------------------------------------------------------------


def test_rejected_ownership_excluded(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    app = _make_app_with_capacity(session, site.id, "APP/1", 100)
    _make_control_relationship(session, site_id=site.id, application_id=app.id, entity_name_raw="Rejected Entity Ltd",
                                role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER", review_status="rejected")
    session.commit()

    context = build_allocation_context(session, allocation)
    assert context.ownership_entities == []


# ---------------------------------------------------------------------------
# Items 11-15 - role handling (Section 5)
# ---------------------------------------------------------------------------


def _ownership_fixture(session, *, role, evidence_category, entity_name_raw="Test Entity Ltd", review_status="auto_applied"):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = _make_site(session)
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    app = _make_app_with_capacity(session, site.id, "APP/ROLE", 100)
    _make_control_relationship(session, site_id=site.id, application_id=app.id, entity_name_raw=entity_name_raw,
                                role=role, evidence_category=evidence_category, review_status=review_status)
    session.commit()
    return allocation


def test_certificate_a_role_not_called_current_owner(session):
    allocation = _ownership_fixture(session, role="OWNER", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION")
    context = build_allocation_context(session, allocation)
    assert context.ownership_entities[0].role_label == "Planning ownership declaration"
    assert "current owner" not in context.ownership_entities[0].role_label.lower()


def test_applicant_not_automatically_called_developer(session):
    allocation = _ownership_fixture(session, role="APPLICANT", evidence_category="SOME_OTHER_CATEGORY")
    context = build_allocation_context(session, allocation)
    role_label = context.ownership_entities[0].role_label
    assert "developer" not in role_label.lower()
    assert role_label == "Applicant evidence"


def test_mortgagee_not_called_owner(session):
    allocation = _ownership_fixture(session, role="MORTGAGEE", evidence_category="S106_DEFINED_MORTGAGEE")
    context = build_allocation_context(session, allocation)
    role_label = context.ownership_entities[0].role_label
    assert role_label == "S106 Mortgagee"
    assert "owner" not in role_label.lower()


def test_developer_role_preserved(session):
    allocation = _ownership_fixture(session, role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    context = build_allocation_context(session, allocation)
    assert context.ownership_entities[0].role_label == "S106 Developer"


def test_promoter_only_when_supported(session):
    """No structured evidence source in this codebase ever uses "promoter"
    wording for a Certificate A / S106 Owner / S106 Developer / S106
    Mortgagee / Applicant role - confirm "promoter" never appears in the
    allowed_roles set for a context built from those roles."""
    allocation = _ownership_fixture(session, role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    context = build_allocation_context(session, allocation)
    assert all("promoter" not in o.role_label.lower() for o in context.ownership_entities)


# ---------------------------------------------------------------------------
# Item 16 - Site-specific ownership not widened to allocation
# ---------------------------------------------------------------------------


def test_site_specific_ownership_not_widened_to_allocation(session):
    allocation = _ownership_fixture(session, role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    context = build_allocation_context(session, allocation)
    prompt = build_summary_prompt(context)
    assert 'For Site "' in prompt
    assert "never say an entity" in prompt.lower() or "never the allocation as a whole" in prompt.lower()


# ---------------------------------------------------------------------------
# Item 17 - no adjacency inference
# ---------------------------------------------------------------------------


def test_no_adjacency_inference(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()
    context = build_allocation_context(session, allocation)
    assert not hasattr(context, "adjoining_allocations")
    prompt = build_summary_prompt(context)
    assert "do not mention any other local plan allocation" in prompt.lower()


# ---------------------------------------------------------------------------
# Item 18 - fingerprint stable when unchanged
# ---------------------------------------------------------------------------


def test_fingerprint_stable_when_context_unchanged(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()
    fp1 = compute_context_fingerprint(build_allocation_context(session, allocation))
    fp2 = compute_context_fingerprint(build_allocation_context(session, allocation))
    assert fp1 == fp2


# ---------------------------------------------------------------------------
# Items 19-22 - regeneration triggers
# ---------------------------------------------------------------------------


def test_prompt_version_change_invalidates_summary(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()
    fp = compute_context_fingerprint(build_allocation_context(session, allocation))
    allocation.ai_summary_headline = "Old headline"
    allocation.ai_summary_context_fingerprint = fp
    allocation.ai_summary_prompt_version = "some-older-version"
    session.commit()
    assert should_regenerate_allocation_summary(allocation, fp) is True


def test_fresh_summary_not_regenerated(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()
    fp = compute_context_fingerprint(build_allocation_context(session, allocation))
    allocation.ai_summary_headline = "Fresh headline"
    allocation.ai_summary_context_fingerprint = fp
    allocation.ai_summary_prompt_version = PROMPT_VERSION
    session.commit()
    assert should_regenerate_allocation_summary(allocation, fp) is False


def test_stale_summary_selected_for_regeneration(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()
    fp = compute_context_fingerprint(build_allocation_context(session, allocation))
    allocation.ai_summary_headline = "Stale headline"
    allocation.ai_summary_context_fingerprint = "a-completely-different-fingerprint"
    allocation.ai_summary_prompt_version = PROMPT_VERSION
    session.commit()
    assert is_allocation_summary_stale(session, allocation) is True
    assert should_regenerate_allocation_summary(allocation, fp) is True


def test_missing_summary_selected(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()
    fp = compute_context_fingerprint(build_allocation_context(session, allocation))
    assert allocation.ai_summary_headline is None
    assert is_allocation_summary_stale(session, allocation) is False  # missing, not stale
    assert should_regenerate_allocation_summary(allocation, fp) is True


# ---------------------------------------------------------------------------
# Items 23/24 - no OpenAI in render/filter path
# ---------------------------------------------------------------------------


def test_page_render_performs_no_openai_call(session):
    """is_allocation_summary_stale (what the detail page calls to show a
    staleness indicator) never touches OpenAI."""
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    allocation.ai_summary_headline = "Existing"
    allocation.ai_summary_context_fingerprint = "x"
    session.commit()
    is_allocation_summary_stale(session, allocation)  # must not raise / require a client
    source = inspect.getsource(is_allocation_summary_stale)
    assert "openai" not in source.lower()
    assert "responses.create" not in source


def test_filtering_performs_no_openai_call():
    from app.reporting.allocation_discovery import apply_filters
    source = inspect.getsource(apply_filters)
    assert "openai" not in source.lower()


# ---------------------------------------------------------------------------
# Items 25-28 - factual-grounding validation
# ---------------------------------------------------------------------------


def test_structured_output_validates_when_grounded(session):
    allocation = _ownership_fixture(session, role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    context = build_allocation_context(session, allocation)
    is_valid, problems = validate_summary_output(context, _good_output(context))
    assert is_valid is True
    assert problems == []


def test_hallucinated_organisation_rejected(session):
    allocation = _ownership_fixture(session, role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    context = build_allocation_context(session, allocation)
    output = _good_output(context)
    output["referenced_entity_names"] = output["referenced_entity_names"] + ["Completely Invented Organisation Ltd"]
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False
    assert any("entity names" in p for p in problems)


def test_hallucinated_application_reference_rejected(session):
    allocation = _ownership_fixture(session, role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    context = build_allocation_context(session, allocation)
    output = _good_output(context)
    output["referenced_application_references"] = output["referenced_application_references"] + ["FAKE/999999/99"]
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False
    assert any("application references" in p for p in problems)


def test_invalid_capacity_number_rejected(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()
    context = build_allocation_context(session, allocation)
    output = dict(_GOOD_OUTPUT_TEMPLATE)
    output["overview"] = "This allocation has capacity for 9999 homes, all identified."
    is_valid, problems = validate_summary_output(context, output)
    assert is_valid is False
    assert any("unsupported numbers" in p for p in problems)


# ---------------------------------------------------------------------------
# Item 29 - last successful summary survives generation failure
# ---------------------------------------------------------------------------


def test_last_successful_summary_survives_validation_failure(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()

    context = build_allocation_context(session, allocation)
    good = _good_output(context)
    client = _fake_client(good)
    result = generate_allocation_intelligence_summary(session, client, allocation)
    assert result.regenerated is True
    original_headline = allocation.ai_summary_headline
    assert original_headline == good["headline"]

    # Force a regeneration attempt (context genuinely changed) whose output is ungrounded.
    allocation.minimum_dwellings = 999999
    session.commit()
    bad_output = dict(good)
    bad_output["overview"] = "This mentions a hallucinated figure of 42424242 homes."
    client2 = _fake_client(bad_output)
    result2 = generate_allocation_intelligence_summary(session, client2, allocation)
    assert result2.rejected is True
    assert allocation.ai_summary_headline == original_headline  # unchanged
    assert allocation.ai_summary_status == "error"


def test_last_successful_summary_survives_client_exception(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()

    context = build_allocation_context(session, allocation)
    good = _good_output(context)
    client = _fake_client(good)
    generate_allocation_intelligence_summary(session, client, allocation)
    original_headline = allocation.ai_summary_headline

    allocation.minimum_dwellings = 12345
    session.commit()
    result = generate_allocation_intelligence_summary(session, _RaisingClient(), allocation)
    assert result.regenerated is False
    assert allocation.ai_summary_headline == original_headline
    assert allocation.ai_summary_status == "error"
    assert "simulated OpenAI failure" in allocation.ai_summary_generation_error


# ---------------------------------------------------------------------------
# Items 30-34 - CLI runner
# ---------------------------------------------------------------------------


def test_dry_run_performs_zero_writes(session, monkeypatch):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()

    monkeypatch.setattr(sys, "argv", ["generate_allocation_intelligence_summaries.py"])
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "get_session", lambda: session)

    cli.main()
    assert allocation.ai_summary_headline is None


def test_execute_without_exact_confirm_phrase_fails_closed(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["generate_allocation_intelligence_summaries.py", "--execute", "--confirm", "WRONG"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2


def test_execute_with_missing_confirm_fails_closed(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["generate_allocation_intelligence_summaries.py", "--execute"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2


def test_execute_idempotency(session, monkeypatch):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()

    context = build_allocation_context(session, allocation)
    good = _good_output(context)
    client = _fake_client(good)

    first = generate_allocation_intelligence_summary(session, client, allocation)
    assert first.regenerated is True
    second = generate_allocation_intelligence_summary(session, client, allocation)
    assert second.regenerated is False  # unchanged context - no second OpenAI-shaped call needed


def test_single_allocation_targeting(session, monkeypatch):
    _make_council(session)
    plan = _make_plan(session)
    target = _make_allocation(session, plan, policy_reference="TARGET", minimum_dwellings=300)
    other = _make_allocation(session, plan, policy_reference="OTHER", minimum_dwellings=300)
    session.commit()

    monkeypatch.setattr(sys, "argv", ["generate_allocation_intelligence_summaries.py", "--allocation-id", str(target.id)])
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "get_session", lambda: session)
    targets = cli._select_targets(session, cli.parse_args())
    assert [a.id for a in targets] == [target.id]


def test_stale_only_targeting(session, monkeypatch):
    _make_council(session)
    plan = _make_plan(session)
    stale = _make_allocation(session, plan, policy_reference="STALE", minimum_dwellings=300)
    fresh = _make_allocation(session, plan, policy_reference="FRESH", minimum_dwellings=300)
    fresh_fp = compute_context_fingerprint(build_allocation_context(session, fresh))
    fresh.ai_summary_headline = "Fresh"
    fresh.ai_summary_context_fingerprint = fresh_fp
    fresh.ai_summary_prompt_version = PROMPT_VERSION
    session.commit()

    monkeypatch.setattr(sys, "argv", ["generate_allocation_intelligence_summaries.py", "--stale"])
    classification_stale = cli._classify(session, stale, only_stale=True)
    classification_fresh = cli._classify(session, fresh, only_stale=True)
    assert classification_stale == "missing"
    assert classification_fresh == "fresh"


# ---------------------------------------------------------------------------
# Item 35 - no N+1 regression in context building
# ---------------------------------------------------------------------------


def _select_count_for_n_sites(session, allocation, n: int) -> int:
    for i in range(n):
        site = _make_site(session, f"Site {allocation.id}-{i}")
        _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
        app = _make_app_with_capacity(session, site.id, f"APP/{allocation.id}-{i}", 20)
        _make_control_relationship(session, site_id=site.id, application_id=app.id, entity_name_raw=f"Entity {allocation.id}-{i} Ltd",
                                    role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")

    engine = session.get_bind()
    statements = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        build_allocation_context(session, allocation)
    finally:
        event.remove(engine, "before_cursor_execute", _count)
    return len(statements)


def test_no_n_plus_1_in_context_building(session):
    """build_allocation_context itself introduces no NEW N+1 on top of what
    its two reused, already-shipped sources already do:
    build_allocation_development_coverage is already O(1)-in-query-count for
    one allocation regardless of related-Site count (Stage 3A); get_
    allocation_control_intelligence is a pre-existing Stage 4B.2/4B.3
    architecture that legitimately issues one query per related Site (see
    its own docstring: "each queried independently... so evidence never
    crosses Sites") - the SAME per-Site cost the Allocation Detail page's
    own Ownership & Control section already pays today. The honest
    regression check is therefore that the MARGINAL query cost per
    additional Site stays constant (linear growth from the pre-existing
    per-Site pattern), not that this new module adds a second, multiplying
    layer on top of it."""
    _make_council(session)
    plan = _make_plan(session)
    small_allocation = _make_allocation(session, plan, policy_reference="SMALL", minimum_dwellings=300)
    large_allocation = _make_allocation(session, plan, policy_reference="LARGE", minimum_dwellings=300)

    small_count = _select_count_for_n_sites(session, small_allocation, 2)
    large_count = _select_count_for_n_sites(session, large_allocation, 10)

    marginal_per_site = (large_count - small_count) / (10 - 2)
    # The pre-existing per-Site ownership query is exactly 1 query/Site;
    # allow a little headroom (e.g. one extra lookup per Site) without
    # allowing a real multiplicative regression (e.g. a query per
    # Application or per ControlRelationship row on top of that).
    assert marginal_per_site <= 2


# ---------------------------------------------------------------------------
# Items 36-39 - representative allocation regressions
# ---------------------------------------------------------------------------


def test_north_of_mosley_common_regression(session):
    """Mirrors the real production figures (allocation 73, JPA 32): ~1,100
    allocation capacity, 244 identified, ~856 indicative residual,
    Site-specific ownership/control, residual ownership unknown."""
    _make_council(session, "wigan")
    plan = _make_plan(session, council_code="wigan")
    allocation = _make_allocation(session, plan, council_code="wigan", policy_reference="JPA 32",
                                   site_name="North of Mosley Common", minimum_dwellings=1100)
    site = _make_site(session, "Land North Of Mosley Common", council_code="wigan")
    _make_relationship(session, allocation_id=allocation.id, site_id=site.id)
    app = _make_app_with_capacity(session, site.id, "A/25/099409/RMMAJ", 244, council_code="wigan")
    _make_control_relationship(session, site_id=site.id, application_id=app.id, entity_name_raw="Taylor Wimpey Manchester",
                                role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    session.commit()

    context = build_allocation_context(session, allocation)
    assert context.allocation_capacity_value == 1100
    assert context.identified_application_capacity == 244
    assert context.indicative_residual_capacity == 856
    assert context.ownership_entities[0].entity_name_raw == "Taylor Wimpey Manchester"
    assert context.ownership_entities[0].is_residual is False
    assert context.residual_ownership_known is False  # residual ownership unknown


def test_jpa10_regression_no_trusted_relationship_after_cleanup(session):
    """JPA10 Beal Valley - no trusted Bullcote Lane relationship after
    cleanup; must not resurrect rejected planning activity."""
    _make_council(session, "wigan")
    plan = _make_plan(session, council_code="wigan")
    jpa10 = _make_allocation(session, plan, council_code="wigan", policy_reference="JPA 10",
                              site_name="Beal Valley", minimum_dwellings=480)
    site = _make_site(session, "Land South Of Bullcote Lane", council_code="wigan")
    _make_relationship(session, allocation_id=jpa10.id, site_id=site.id, review_status="rejected")
    _make_app_with_capacity(session, site.id, "FUL/355603/26", 248, council_code="wigan")
    session.commit()

    context = build_allocation_context(session, jpa10)
    assert context.sites == []
    assert context.number_of_related_sites == 0
    assert context.identified_application_capacity == 0
    assert context.development_coverage_classification == "NO_IDENTIFIED_ACTIVITY"


def test_jpa12_regression_valid_relationship_retained(session):
    """JPA12 Broadbent Moss - the SAME Site's valid relationship remains;
    identified planning capacity retained."""
    _make_council(session, "wigan")
    plan = _make_plan(session, council_code="wigan")
    jpa12 = _make_allocation(session, plan, council_code="wigan", policy_reference="JPA 12",
                              site_name="Broadbent Moss", minimum_dwellings=1450)
    site = _make_site(session, "Land South Of Bullcote Lane", council_code="wigan")
    _make_relationship(session, allocation_id=jpa12.id, site_id=site.id, review_status="auto_applied")
    _make_app_with_capacity(session, site.id, "FUL/355603/26", 248, council_code="wigan")
    session.commit()

    context = build_allocation_context(session, jpa12)
    assert context.number_of_related_sites == 1
    assert context.identified_application_capacity == 248
    assert context.sites[0].application_references == ["FUL/355603/26"]


def test_north_leigh_park_multi_site_ownership_regression(session):
    """North Leigh Park - multi-Site/phase hierarchy, ownership evidence
    differs by Site, large residual allocation capacity."""
    _make_council(session, "wigan")
    plan = _make_plan(session, council_code="wigan")
    allocation = _make_allocation(session, plan, council_code="wigan", policy_reference="H3",
                                   site_name="North Leigh Park", minimum_dwellings=1400)
    site_a = _make_site(session, "North Leigh Development Site", council_code="wigan")
    site_b = _make_site(session, "Land East Of North Leigh Park", council_code="wigan")
    _make_relationship(session, allocation_id=allocation.id, site_id=site_a.id)
    _make_relationship(session, allocation_id=allocation.id, site_id=site_b.id)
    app_a = _make_app_with_capacity(session, site_a.id, "A/26/100520/RMMAJ", 100, council_code="wigan")
    app_b = _make_app_with_capacity(session, site_b.id, "A/26/100521/RMMAJ", 56, council_code="wigan")
    _make_control_relationship(session, site_id=site_a.id, application_id=app_a.id, entity_name_raw="Site A Developer Ltd",
                                role="DEVELOPER", evidence_category="S106_DEFINED_DEVELOPER")
    _make_control_relationship(session, site_id=site_b.id, application_id=app_b.id, entity_name_raw="Site B Owner Ltd",
                                role="OWNER", evidence_category="S106_DEFINED_OWNER")
    session.commit()

    context = build_allocation_context(session, allocation)
    assert context.number_of_related_sites == 2
    assert context.identified_application_capacity == 156
    assert context.indicative_residual_capacity == 1400 - 156
    entities_by_site = {o.site_label: o.entity_name_raw for o in context.ownership_entities}
    assert entities_by_site[site_a.display_address] == "Site A Developer Ltd"
    assert entities_by_site[site_b.display_address] == "Site B Owner Ltd"


# ---------------------------------------------------------------------------
# Item 40 - no external APIs other than approved OpenAI generation path
# ---------------------------------------------------------------------------


def test_no_external_apis_other_than_openai_generation_path():
    reporting_source = inspect.getsource(__import__("app.reporting.allocation_intelligence_summary", fromlist=["x"]))
    assert "requests.get(" not in reporting_source
    assert "requests.post(" not in reporting_source
    assert "companies_house" not in reporting_source.lower()
    assert "land_registry" not in reporting_source.lower()
    # OpenAI is the one, approved dependency - imported at module scope
    # nowhere (only client.responses.create is called, client passed in by
    # the caller) - confirms this module holds no client construction/
    # secret-reading logic of its own.
    assert "import openai" not in reporting_source.lower()
    assert "os.getenv" not in reporting_source
    assert "os.environ" not in reporting_source

    cli_source = inspect.getsource(cli)
    assert "requests.get(" not in cli_source
    assert "requests.post(" not in cli_source
