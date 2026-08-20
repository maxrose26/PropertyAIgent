"""AI Allocation Intelligence Summary - Pre-Merge Architecture Amendment
tests. Covers the two architecture decisions this amendment makes on top
of the approved V1 (feature/ai-allocation-intelligence-summary, 17b4e38):

  1. Persistence moved from LocalPlanSite.ai_summary_* columns to a
     dedicated AllocationIntelligenceSummary table (source/generated-
     interpretation separation).
  2. An automatic refresh mechanism (app.pipeline.run_weekly.
     stage_allocation_intelligence_refresh / count_pending_allocation_
     summary_refresh), wired into the ALREADY-LIVE scripts.
     run_intelligence_processing cron job behind an explicit, default-off
     opt-in (PROPERTYAIGENT_ENABLE_ALLOCATION_SUMMARY_REFRESH /
     --enable-allocation-summaries) so merging and deploying this amendment
     alone cannot start generating real summaries in production.

Everything already covered by tests/test_allocation_intelligence_summary.py
(role semantics, grounding validation, fingerprint sensitivity, the 4
representative-allocation regressions, etc.) is NOT duplicated here - that
file was updated in place to use the new persistence architecture and all
42 of its tests continue to pass unchanged in intent."""
from __future__ import annotations

import json

import pytest
from sqlalchemy.exc import IntegrityError

from app.config import CouncilConfig
from app.db.models import (
    AllocationIntelligenceSummary, Council, IntelligenceRun, LocalPlan, LocalPlanSite,
)
from app.pipeline.run_weekly import (
    count_pending_allocation_summary_refresh, stage_allocation_intelligence_refresh,
)
from app.reporting.allocation_intelligence_summary import (
    PROMPT_VERSION, build_allocation_context, compute_context_fingerprint,
    generate_allocation_intelligence_summary, get_allocation_summary,
)
from scripts.run_intelligence_processing import DEFAULT_MAX_ALLOCATION_SUMMARIES_PER_RUN, process_intelligence_backlog


def _make_council(session, code="testcouncil") -> None:
    if session.get(Council, code) is None:
        session.add(Council(code=code, name=code.title(), base_url="https://example.invalid",
                             date_field_mode="received", doc_system="idox"))
        session.commit()


def _council_config(code="testcouncil") -> CouncilConfig:
    return CouncilConfig(
        code=code, name=code, base_url="https://example.invalid",
        date_field_mode="received", doc_system="idox", anite_base_url=None,
        unit_threshold=10, region=None, country=None,
    )


def _make_plan(session, council_code="testcouncil", status="adopted") -> LocalPlan:
    plan = LocalPlan(council_code=council_code, plan_name="Test Local Plan", status=status, raw_status=status)
    session.add(plan)
    session.commit()
    return plan


def _make_allocation(session, plan, *, council_code="testcouncil", policy_reference="REF-1",
                      site_name="Test Allocation", minimum_dwellings=300) -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code=council_code, local_plan_id=plan.id, policy_reference=policy_reference, site_name=site_name,
        plan_name="Test Local Plan", plan_status="adopted", minimum_dwellings=minimum_dwellings, intended_use="residential",
    )
    session.add(allocation)
    session.commit()
    return allocation


class _FakeResponse:
    def __init__(self, output_text: str):
        self.output_text = output_text


def _good_output_for(context) -> dict:
    return {
        "headline": "Adopted allocation with partial development coverage",
        "overview": "This allocation is adopted and has identified planning activity.",
        "key_points": ["Identified planning activity exists."],
        "key_uncertainties": [], "investigation_priorities": [],
        "referenced_applications": [], "referenced_entities": [],
    }


def _fake_client(structured_output: dict):
    class _Responses:
        def create(self, model, input, text):
            return _FakeResponse(json.dumps(structured_output))
    client = type("FakeClient", (), {})()
    client.responses = _Responses()
    return client


class _CountingFakeClient:
    """Counts real .responses.create calls - used to prove the automatic
    refresh stage makes exactly the expected number of OpenAI-shaped calls,
    never more (e.g. never re-checks/re-calls for an already-fresh
    allocation)."""

    def __init__(self, structured_output: dict):
        self.call_count = 0
        self._output = structured_output
        self.responses = self

    def create(self, model, input, text):
        self.call_count += 1
        return _FakeResponse(json.dumps(self._output))


# ---------------------------------------------------------------------------
# 1/2. Selected persistence architecture - source vs generated interpretation
# ---------------------------------------------------------------------------


def test_local_plan_site_has_no_ai_summary_columns():
    """Source intelligence (LocalPlanSite) must carry zero AI-generated
    columns after this amendment - the separation the Product Owner asked
    for is a physical one, not just a naming convention."""
    column_names = {c.name for c in LocalPlanSite.__table__.columns}
    assert not any(name.startswith("ai_summary_") for name in column_names)


def test_dedicated_summary_table_exists_and_is_keyed_by_allocation_id():
    assert AllocationIntelligenceSummary.__tablename__ == "allocation_intelligence_summaries"
    column_names = {c.name for c in AllocationIntelligenceSummary.__table__.columns}
    assert {
        "id", "allocation_id", "headline", "overview", "key_points", "key_uncertainties",
        "investigation_priorities", "generated_at", "context_fingerprint", "model", "prompt_version",
        "status", "generation_error", "created_at", "updated_at",
    } == column_names


# ---------------------------------------------------------------------------
# 3. Summary uniqueness invariant (one current row per allocation)
# ---------------------------------------------------------------------------


def test_second_summary_row_for_same_allocation_violates_uniqueness(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan)
    session.commit()

    session.add(AllocationIntelligenceSummary(allocation_id=allocation.id, headline="First"))
    session.commit()

    session.add(AllocationIntelligenceSummary(allocation_id=allocation.id, headline="Second"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_generate_never_creates_a_second_row_for_the_same_allocation(session):
    """generate_allocation_intelligence_summary's get-or-create logic must
    reuse the existing row across repeated regenerations, never insert a
    second one."""
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan)
    session.commit()

    context = build_allocation_context(session, allocation)
    client = _fake_client(_good_output_for(context))
    generate_allocation_intelligence_summary(session, client, allocation)

    allocation.minimum_dwellings = 999
    session.commit()
    context2 = build_allocation_context(session, allocation)
    generate_allocation_intelligence_summary(session, _fake_client(_good_output_for(context2)), allocation)

    from sqlalchemy import select
    rows = session.execute(
        select(AllocationIntelligenceSummary).where(AllocationIntelligenceSummary.allocation_id == allocation.id)
    ).scalars().all()
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# 12/19/20. Automatic refresh stage - canonical generator, stale-only, no
# wasted OpenAI calls
# ---------------------------------------------------------------------------


def test_automatic_refresh_selects_allocation_made_stale_by_new_trusted_application(session):
    """Section 11/12's exact lifecycle: a new trusted Application changes
    the allocation's context fingerprint, and the automatic refresh stage
    (not the CLI) picks it up and regenerates."""
    from app.db.models import AllocationSiteRelationship, Application, SchemeIntelligence, Site

    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    site = Site(council_code="testcouncil", canonical_address="a site", display_address="A Site")
    session.add(site)
    session.commit()
    session.add(AllocationSiteRelationship(allocation_id=allocation.id, site_id=site.id, evidence_basis="document_confirmed_site"))
    session.commit()

    context = build_allocation_context(session, allocation)
    fingerprint = compute_context_fingerprint(context)
    session.add(AllocationIntelligenceSummary(
        allocation_id=allocation.id, headline="Old", context_fingerprint=fingerprint, prompt_version=PROMPT_VERSION,
    ))
    session.commit()

    # New trusted Application -> Site now has capacity -> fingerprint moves.
    app = Application(council_code="testcouncil", reference="APP/NEW", site_id=site.id)
    session.add(app)
    session.commit()
    session.add(SchemeIntelligence(application_id=app.id, total_units_final=120, core_intelligence_complete=True))
    session.commit()

    client = _fake_client(_good_output_for(build_allocation_context(session, allocation)))
    result = stage_allocation_intelligence_refresh(session, client, _council_config(), limit=10)
    assert result.attempted == 1
    assert result.succeeded == 1
    summary = get_allocation_summary(session, allocation.id)
    assert summary.headline != "Old"


def test_automatic_refresh_ignores_unrelated_application(session):
    from app.db.models import Application, SchemeIntelligence, Site

    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()
    # No AllocationSiteRelationship - allocation has insufficient context
    # (no capacity_value fallback here since minimum_dwellings IS set -
    # adjust: give it sufficient context via capacity alone, then attach an
    # unrelated Site/Application that must not matter).
    unrelated_site = Site(council_code="testcouncil", canonical_address="unrelated", display_address="Unrelated Site")
    session.add(unrelated_site)
    session.commit()
    app = Application(council_code="testcouncil", reference="APP/UNRELATED", site_id=unrelated_site.id)
    session.add(app)
    session.commit()
    session.add(SchemeIntelligence(application_id=app.id, total_units_final=999, core_intelligence_complete=True))
    session.commit()

    context = build_allocation_context(session, allocation)
    fingerprint = compute_context_fingerprint(context)
    session.add(AllocationIntelligenceSummary(
        allocation_id=allocation.id, headline="Fresh", context_fingerprint=fingerprint, prompt_version=PROMPT_VERSION,
    ))
    session.commit()

    client = _CountingFakeClient(_good_output_for(context))
    result = stage_allocation_intelligence_refresh(session, client, _council_config(), limit=10)
    assert result.attempted == 0
    assert client.call_count == 0


def test_automatic_refresh_makes_zero_openai_calls_when_nothing_stale(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()
    context = build_allocation_context(session, allocation)
    fingerprint = compute_context_fingerprint(context)
    session.add(AllocationIntelligenceSummary(
        allocation_id=allocation.id, headline="Fresh", context_fingerprint=fingerprint, prompt_version=PROMPT_VERSION,
    ))
    session.commit()

    client = _CountingFakeClient(_good_output_for(context))
    result = stage_allocation_intelligence_refresh(session, client, _council_config(), limit=10)
    assert result.candidates_inspected == 1
    assert result.attempted == 0
    assert client.call_count == 0


def test_automatic_refresh_uses_the_canonical_generator(session, monkeypatch):
    """Confirms Section 13's "one canonical path, never a second summary
    generator" - the stage function must call app.reporting.
    allocation_intelligence_summary.generate_allocation_intelligence_summary
    itself, not re-implement generation."""
    import app.pipeline.run_weekly as run_weekly_module

    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()

    calls = []
    import app.reporting.allocation_intelligence_summary as summary_module
    real_generate = summary_module.generate_allocation_intelligence_summary

    def _spy(session_arg, client_arg, allocation_arg, **kwargs):
        calls.append(allocation_arg.id)
        return real_generate(session_arg, client_arg, allocation_arg, **kwargs)

    monkeypatch.setattr(summary_module, "generate_allocation_intelligence_summary", _spy)

    client = _fake_client(_good_output_for(build_allocation_context(session, allocation)))
    stage_allocation_intelligence_refresh(session, client, _council_config(), limit=10)
    assert calls == [allocation.id]


# ---------------------------------------------------------------------------
# 23. Ingestion path contains no OpenAI generation for allocation summaries
# ---------------------------------------------------------------------------


def test_site_linking_never_calls_allocation_summary_generation():
    import inspect
    from app.pipeline import site_linking
    source = inspect.getsource(site_linking)
    assert "generate_allocation_intelligence_summary" not in source
    assert "allocation_intelligence_summary" not in source


# ---------------------------------------------------------------------------
# 27. Batch refresh idempotency
# ---------------------------------------------------------------------------


def test_automatic_refresh_idempotent_across_consecutive_runs(session):
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()

    context = build_allocation_context(session, allocation)
    client = _CountingFakeClient(_good_output_for(context))
    first = stage_allocation_intelligence_refresh(session, client, _council_config(), limit=10)
    assert first.attempted == 1
    assert first.succeeded == 1
    assert client.call_count == 1

    second = stage_allocation_intelligence_refresh(session, client, _council_config(), limit=10)
    assert second.attempted == 0
    assert client.call_count == 1  # no second OpenAI-shaped call


# ---------------------------------------------------------------------------
# 28. Generation failure isolation across candidates in one stage run
# ---------------------------------------------------------------------------


def test_one_allocation_failure_does_not_stop_the_rest_of_the_stage_run(session):
    _make_council(session)
    plan = _make_plan(session)
    a1 = _make_allocation(session, plan, policy_reference="A1", minimum_dwellings=300)
    a2 = _make_allocation(session, plan, policy_reference="A2", minimum_dwellings=400)
    session.commit()

    class _FirstFailsClient:
        def __init__(self):
            self.calls = 0
            self.responses = self

        def create(self, model, input, text):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("simulated transient OpenAI failure")
            return _FakeResponse(json.dumps(_good_output_for(None)))

    client = _FirstFailsClient()
    result = stage_allocation_intelligence_refresh(session, client, _council_config(), limit=10)
    assert result.attempted == 2
    assert result.failed == 1
    assert result.succeeded == 1
    # Both allocations were genuinely inspected/attempted despite the first raising.
    assert get_allocation_summary(session, a1.id).status == "error"
    assert get_allocation_summary(session, a2.id).headline is not None


# ---------------------------------------------------------------------------
# 34. No new N+1 regression introduced by this amendment's stage function
# ---------------------------------------------------------------------------


def test_count_pending_allocation_summary_refresh_scales_linearly(session):
    from sqlalchemy import event

    _make_council(session)
    plan = _make_plan(session)
    for i in range(5):
        _make_allocation(session, plan, policy_reference=f"REF-{i}", minimum_dwellings=100 + i)
    session.commit()

    engine = session.get_bind()
    statements = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        count_pending_allocation_summary_refresh(session, "testcouncil")
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    # 5 allocations, no related Sites/ownership - bounded, roughly constant
    # per-allocation cost (context build + summary lookup), not a much
    # larger multiplier.
    assert len(statements) <= 5 * 6


# ---------------------------------------------------------------------------
# 35. Production scheduling/config remains inactive
# ---------------------------------------------------------------------------


def test_render_yaml_does_not_declare_allocation_summary_env_var():
    from pathlib import Path
    render_yaml_text = (Path(__file__).resolve().parents[1] / "render.yaml").read_text(encoding="utf-8")
    assert "PROPERTYAIGENT_ENABLE_ALLOCATION_SUMMARY_REFRESH" not in render_yaml_text


def test_process_intelligence_backlog_defaults_to_allocation_summaries_disabled(session, monkeypatch):
    """Calling process_intelligence_backlog the same way the LIVE scheduled
    job's main() does (no enable_allocation_summaries kwarg) must never
    touch allocation summaries, even when a stale one genuinely exists, and
    must never even require OPENAI_API_KEY to be set on its account -
    the exact "inert until deployment/configuration" invariant."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()
    # No AllocationIntelligenceSummary row at all - maximally "stale" -
    # yet with allocation summaries disabled, this must still be a no-op.

    def _boom(api_key):
        raise AssertionError("must not create an OpenAI client when allocation summary refresh is disabled")

    run = process_intelligence_backlog(
        session, {"testcouncil": _council_config()}, ["testcouncil"],
        max_extractions=0, max_summaries=0, max_intelligence_refresh=0,
        client_factory=_boom,
    )
    assert run.allocation_summaries_attempted == 0
    assert run.status == "success"
    assert get_allocation_summary(session, allocation.id) is None


def test_process_intelligence_backlog_respects_explicit_opt_in(session, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _make_council(session)
    plan = _make_plan(session)
    allocation = _make_allocation(session, plan, minimum_dwellings=300)
    session.commit()

    context = build_allocation_context(session, allocation)
    client = _CountingFakeClient(_good_output_for(context))
    run = process_intelligence_backlog(
        session, {"testcouncil": _council_config()}, ["testcouncil"],
        max_extractions=0, max_summaries=0, max_intelligence_refresh=0,
        max_allocation_summaries=DEFAULT_MAX_ALLOCATION_SUMMARIES_PER_RUN,
        enable_allocation_summaries=True,
        client_factory=lambda api_key: client,
    )
    assert client.call_count == 1
    assert run.allocation_summaries_attempted == 1
    assert run.allocation_summaries_succeeded == 1
    assert get_allocation_summary(session, allocation.id) is not None


def test_default_max_allocation_summaries_per_run_is_small_and_bounded():
    assert 0 < DEFAULT_MAX_ALLOCATION_SUMMARIES_PER_RUN <= 20
