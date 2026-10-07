"""Stage 2.5B V7C: run_persisted_evaluation refuses a STALE mandate before any anchor/claim/history write or model call (mixed-version guard)."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

import app.policy.buyer_profile_store as store
from app.db.models import AcquisitionSubjectAnchor, AgentEvaluationClaim, AgentEvaluationHistory, CurrentBuyerOpportunityState
from app.policy.agent_evaluation_persistence import StaleMandateBaseline, run_persisted_evaluation
from tests.test_agent_evaluation_persistence import _FakeClient, _build_case, _valid_raw


def run(session, case, client, **kw):
    site, opp, mandate_row, mandate, packet, assessment = case
    return run_persisted_evaluation(
        session, mandate=mandate, mandate_key=mandate_row.buyer.buyer_key, buyer_mandate_id=mandate_row.id, mandate_fingerprint="fp-mandate",
        acquisition_type="LAND_SITE_ACQUISITION", opportunity=opp, opportunity_fingerprint="fp-opp", packet=packet, buyer_fit_assessment=assessment, client=client, **kw)


def rows(session):
    return {model.__name__: session.execute(select(func.count()).select_from(model)).scalar()
            for model in (AcquisitionSubjectAnchor, AgentEvaluationClaim, AgentEvaluationHistory, CurrentBuyerOpportunityState)}


def test_a_never_onboarded_mandate_is_refused_with_no_model_call_and_no_writes(session):
    case = _build_case(session)
    case[2].matching_fingerprint = None
    case[2].onboarding_completed_at = None
    session.commit()
    client = _FakeClient([json.dumps(_valid_raw())])
    before = rows(session)
    with pytest.raises(StaleMandateBaseline):
        run(session, case, client)
    assert client.responses.calls == 0 and rows(session) == before            # zero model calls; zero anchor/claim/history/current-state writes
    assert case[2].matching_fingerprint is None                                # the guard never re-onboards


def test_a_policy_version_change_makes_a_previously_fresh_mandate_stale_and_refuses(session, monkeypatch):
    case = _build_case(session)                                                # onboarded under the current policy: fresh
    import app.policy.buyer_matching as bm
    monkeypatch.setattr(bm, "BUYER_MATCHING_POLICY_VERSION", bm.BUYER_MATCHING_POLICY_VERSION + 1)
    monkeypatch.setattr(store, "BUYER_MATCHING_POLICY_VERSION", bm.BUYER_MATCHING_POLICY_VERSION)
    assert store.is_buyer_mandate_baseline_stale(case[2]) is True              # the mixed-version situation the guard exists for
    client = _FakeClient([json.dumps(_valid_raw())])
    before = rows(session)
    fingerprint_before = case[2].matching_fingerprint
    with pytest.raises(StaleMandateBaseline):
        run(session, case, client)
    assert client.responses.calls == 0 and rows(session) == before and case[2].matching_fingerprint == fingerprint_before


def test_a_fresh_mandate_still_evaluates_and_persists_exactly_as_before(session):
    case = _build_case(session)
    assert store.is_buyer_mandate_baseline_stale(case[2]) is False
    client = _FakeClient([json.dumps(_valid_raw(recommendation="PURSUE"))])
    outcome = run(session, case, client)
    assert outcome.status == "evaluated" and outcome.history.recommendation == "PURSUE" and client.responses.calls == 1
    assert rows(session)["AgentEvaluationHistory"] == 1 and rows(session)["CurrentBuyerOpportunityState"] == 1


def test_the_guard_sits_after_the_operator_and_mandate_authority_checks_and_before_any_write():
    import ast
    import inspect
    import textwrap
    import app.policy.agent_evaluation_persistence as persistence
    tree = ast.parse(textwrap.dedent(inspect.getsource(persistence.run_persisted_evaluation)))
    first_call_line = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else None
            if name:
                first_call_line[name] = min(first_call_line.get(name, 10 ** 9), node.lineno)
    order = [first_call_line[name] for name in ("require_operator", "mandate_by_id", "is_buyer_mandate_baseline_stale", "resolve_acquisition_subject_key",
                                                "get_or_create_subject_anchor", "try_claim_evaluation", "evaluate")]
    assert order == sorted(order) and len(set(order)) == len(order)
