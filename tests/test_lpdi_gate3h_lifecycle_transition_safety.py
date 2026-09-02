"""LPDI V1 Gate 3H ("Lifecycle Transition Safety + Wigan Regulation 19
Progression") - Phase A: focused regression tests proving the EXISTING
review/history pathway (PolicyChangeEvent -> approve_change ->
snapshot_plan_status -> LocalPlanStatusHistory -> current LocalPlan update)
safely supports a Local Plan progressing through statutory stages (e.g.
Regulation 18 -> Regulation 19 -> Submission) IN PLACE, without creating a
second LocalPlan row and without losing the previous stage's evidence.

Gate 3G ("Local Plan Lifecycle & Version Progression Assessment") found this
mechanism already exists (built in Sprint 1 for status/raw_status/
plan_version, extended in Sprint 3B for every other evidence field) but had
never actually been exercised in production for a stage/version change
(LocalPlanStatusHistory had 0 rows platform-wide at that point). This file
is the missing regression coverage Gate 3G recommended before Wigan LocalPlan
id 14 is progressed for real - see app.policy.review.approve_change and
app.policy.history.snapshot_plan_status, both UNCHANGED by this gate.

No network, no AI call, no production database access anywhere in this file
- every fixture is a hand-built row against the isolated in-memory `session`
fixture (tests/conftest.py), exactly like every other Policy Intelligence
test in this suite."""
from __future__ import annotations

import json

from sqlalchemy import select

from app.db.models import LocalPlan, LocalPlanCouncil, LocalPlanStatusHistory, MonitoredReport, MonitoredSource, PolicyChangeEvent
from app.policy.joint_plans import plans_for_council
from app.policy.review import approve_change, reject_change

REG_18 = {
    "status": "draft_consultation",
    "raw_status": "Regulation 18 Initial Draft",
    "plan_version": "Regulation 18 Initial Draft",
}
REG_19 = {
    "status": "proposed_submission",
    "raw_status": "Regulation 19 Publication",
    "plan_version": "Regulation 19 Publication",
}
SUBMISSION = {
    "status": "submitted",
    "raw_status": "Submitted for Examination",
    "plan_version": "Submission",
}


def _make_wigan_like_plan(session, **overrides):
    fields = {**REG_18, **overrides}
    plan = LocalPlan(
        council_code="testcouncil",
        plan_name="Test Borough Local Plan: Planning for the Future to 2040 (Initial Draft)",
        **fields,
    )
    session.add(plan)
    session.commit()
    return plan


def _make_pfe_like_plan(session, council_code="testcouncil"):
    """A second LocalPlan a council is linked to via LocalPlanCouncil (not
    council_code) - mirrors Wigan's real production shape, where Wigan is a
    Places for Everyone participating authority (LocalPlanCouncil,
    role="participating_authority") in addition to owning its own emerging
    plan. Deliberately owned by "othercouncil" (its real council_code, same
    pattern as PfE's own council_code="bury" in production) so
    plans_for_council's legacy-column fallback does not also pick it up for
    testcouncil independently of the join row."""
    pfe = LocalPlan(
        council_code="othercouncil", plan_name="Test Joint Development Plan", plan_version="2022-2039", status="adopted",
        raw_status="Adopted (test fixture)",
    )
    session.add(pfe)
    session.commit()
    link = LocalPlanCouncil(local_plan_id=pfe.id, council_code=council_code, role="participating_authority")
    session.add(link)
    session.commit()
    return pfe


def _queue_stage_change(session, plan, new_values: dict, event_type="new_plan_version",
                         source_document_url="https://example.invalid/reg19-consultation.aspx",
                         source_page=None, source_excerpt=None):
    """Mirrors the shape app.policy.change_detection.diff_plan itself already
    produces for a plan_version/status change (see EVENT_TYPES) - a
    PolicyChangeEvent with proposed_data carrying the new plan_version/
    status/raw_status triple, queued needs_review, never auto_applied. This
    is the exact shape Gate 3H Step 10 asks the real Wigan transition to use."""
    event = PolicyChangeEvent(
        local_plan_id=plan.id, event_type=event_type,
        old_value=plan.plan_version, new_value=new_values["plan_version"],
        detail=f"Plan progressed from {plan.plan_version!r} to {new_values['plan_version']!r}.",
        proposed_data=json.dumps(new_values),
        source_document_url=source_document_url, source_page=source_page, source_excerpt=source_excerpt,
        auto_applied=False, review_status="needs_review",
    )
    session.add(event)
    session.commit()
    return event


def _history_rows(session, plan_id):
    return session.execute(
        select(LocalPlanStatusHistory).where(LocalPlanStatusHistory.local_plan_id == plan_id).order_by(LocalPlanStatusHistory.id)
    ).scalars().all()


# --- Test 1: stage transition snapshots the previous state ---

def test_1_stage_transition_snapshots_previous_state_before_mutation(session):
    plan = _make_wigan_like_plan(session)
    event = _queue_stage_change(session, plan, REG_19)

    approve_change(session, event, note="Reg 19 verified against the official consultation page.")

    rows = _history_rows(session, plan.id)
    assert len(rows) == 1
    snapshot = rows[0]
    assert snapshot.local_plan_id == plan.id
    assert snapshot.status == REG_18["status"]
    assert snapshot.raw_status == REG_18["raw_status"]
    assert snapshot.plan_version == REG_18["plan_version"]
    assert snapshot.captured_at is not None


# --- Test 2: current LocalPlan updates after snapshot ---

def test_2_current_localplan_updates_to_new_values_after_approval(session):
    plan = _make_wigan_like_plan(session)
    plan_id = plan.id
    event = _queue_stage_change(session, plan, REG_19)

    approve_change(session, event)

    session.refresh(plan)
    assert plan.id == plan_id
    assert plan.status == REG_19["status"]
    assert plan.raw_status == REG_19["raw_status"]
    assert plan.plan_version == REG_19["plan_version"]


# --- Test 3: no new LocalPlan is created ---

def test_3_no_new_localplan_row_is_created_by_the_transition(session):
    plan = _make_wigan_like_plan(session)
    before = session.execute(select(LocalPlan).where(LocalPlan.council_code == "testcouncil")).scalars().all()
    assert len(before) == 1

    event = _queue_stage_change(session, plan, REG_19)
    approve_change(session, event)

    after = session.execute(select(LocalPlan).where(LocalPlan.council_code == "testcouncil")).scalars().all()
    assert len(after) == 1
    assert after[0].id == plan.id


# --- Test 4: PolicyChangeEvent remains preserved ---

def test_4_policy_change_event_remains_fully_auditable_after_approval(session):
    plan = _make_wigan_like_plan(session)
    event = _queue_stage_change(
        session, plan, REG_19, event_type="new_plan_version",
        source_document_url="https://www.wigan.gov.uk/reg19-publication",
        source_page=1, source_excerpt="Consultation on the Publication version of the Local Plan",
    )
    event_id = event.id

    approve_change(session, event, note="Independently verified.")

    reloaded = session.get(PolicyChangeEvent, event_id)
    assert reloaded is not None
    assert reloaded.event_type == "new_plan_version"
    assert reloaded.old_value == REG_18["plan_version"]
    assert reloaded.new_value == REG_19["plan_version"]
    assert reloaded.proposed_data is not None and json.loads(reloaded.proposed_data) == REG_19
    assert reloaded.source_document_url == "https://www.wigan.gov.uk/reg19-publication"
    assert reloaded.source_page == 1
    assert reloaded.source_excerpt == "Consultation on the Publication version of the Local Plan"
    assert reloaded.review_status == "confirmed"
    assert reloaded.reviewed_at is not None
    assert reloaded.reviewed_note == "Independently verified."


# --- Test 5: approval is required ---

def test_5_a_pending_proposal_alone_never_mutates_trusted_state(session):
    plan = _make_wigan_like_plan(session)
    _queue_stage_change(session, plan, REG_19)

    session.refresh(plan)
    assert plan.status == REG_18["status"]
    assert plan.raw_status == REG_18["raw_status"]
    assert plan.plan_version == REG_18["plan_version"]
    assert _history_rows(session, plan.id) == []


# --- Test 6: override_data lifecycle transition (the exact mechanism Gate
# 3G proposed for a plan_version/status/raw_status change that has no
# machine-proposed proposed_data of its own) ---

def test_6_override_data_transition_updates_all_three_fields_and_snapshots_first(session):
    plan = _make_wigan_like_plan(session)
    # An event created with no concrete proposed_data at all - e.g. a
    # human-initiated stage_change event recording only that a transition
    # is needed, with the reviewer supplying the exact values at approval
    # time via override_data (approve_change's documented mechanism).
    event = PolicyChangeEvent(
        local_plan_id=plan.id, event_type="stage_change",
        old_value=plan.plan_version, new_value=None, detail="Plan progressed to Regulation 19 Publication.",
        proposed_data=None,
        source_document_url="https://www.wigan.gov.uk/reg19-publication",
        auto_applied=False, review_status="needs_review",
    )
    session.add(event)
    session.commit()

    approve_change(session, event, note="Reg 19 confirmed.", override_data=REG_19)

    session.refresh(plan)
    assert plan.status == REG_19["status"]
    assert plan.raw_status == REG_19["raw_status"]
    assert plan.plan_version == REG_19["plan_version"]

    rows = _history_rows(session, plan.id)
    assert len(rows) == 1
    assert rows[0].plan_version == REG_18["plan_version"]
    assert rows[0].status == REG_18["status"]
    assert rows[0].raw_status == REG_18["raw_status"]


# --- Test 7: existing evidence fields unaffected ---

def test_7_unrelated_evidence_fields_are_unchanged_by_a_stage_only_transition(session):
    plan = _make_wigan_like_plan(session)
    plan.plan_period_start = 2022
    plan.plan_period_end = 2040
    plan.annual_housing_requirement = 1234
    plan.publication_date = None
    session.commit()

    event = _queue_stage_change(session, plan, REG_19)  # proposed_data has only status/raw_status/plan_version
    approve_change(session, event)

    session.refresh(plan)
    assert plan.plan_period_start == 2022
    assert plan.plan_period_end == 2040
    assert plan.annual_housing_requirement == 1234
    assert plan.publication_date is None  # never touched - not part of this event's proposed_data


# --- Test 8: PfE relationships unaffected ---

def test_8_pfe_style_localplancouncil_relationship_is_untouched_by_the_transition(session):
    plan = _make_wigan_like_plan(session)
    pfe = _make_pfe_like_plan(session)
    links_before = session.execute(select(LocalPlanCouncil).where(LocalPlanCouncil.council_code == "testcouncil")).scalars().all()
    assert len(links_before) == 1
    link_id, pfe_id = links_before[0].id, pfe.id

    event = _queue_stage_change(session, plan, REG_19)
    approve_change(session, event)

    links_after = session.execute(select(LocalPlanCouncil).where(LocalPlanCouncil.council_code == "testcouncil")).scalars().all()
    assert len(links_after) == 1  # no duplicate, no new join row
    assert links_after[0].id == link_id
    assert links_after[0].local_plan_id == pfe_id
    assert links_after[0].role == "participating_authority"

    reloaded_pfe = session.get(LocalPlan, pfe_id)
    assert reloaded_pfe.plan_version == "2022-2039"  # PfE's own row completely untouched
    assert reloaded_pfe.status == "adopted"


# --- Test 9: candidate-plan behaviour unaffected ---

def test_9_plans_for_council_still_returns_exactly_own_plan_plus_pfe_after_progression(session):
    plan = _make_wigan_like_plan(session)
    pfe = _make_pfe_like_plan(session)

    event = _queue_stage_change(session, plan, REG_19)
    approve_change(session, event)

    candidates = plans_for_council(session, "testcouncil")
    assert {p.id for p in candidates} == {plan.id, pfe.id}  # exactly 2 - never 3, never a duplicate Reg18+Reg19 row
    reloaded = next(p for p in candidates if p.id == plan.id)
    assert reloaded.plan_version == REG_19["plan_version"]


# --- Test 10: attribution remains stable ---

def test_10_existing_source_and_report_linkage_still_resolves_after_plan_version_changes(session):
    plan = _make_wigan_like_plan(session)
    source = MonitoredSource(
        council_code="testcouncil", local_plan_id=plan.id, source_type="monitoring_page",
        url="https://example.invalid/wigan-style-monitoring-page",
    )
    session.add(source)
    session.commit()
    report = MonitoredReport(
        council_code="testcouncil", local_plan_id=plan.id, monitored_source_id=source.id,
        source_type="local_plan", url="https://example.invalid/reg18-doc.pdf",
    )
    session.add(report)
    session.commit()
    source_id, report_id, plan_id = source.id, report.id, plan.id

    event = _queue_stage_change(session, plan, REG_19)
    approve_change(session, event)

    # Foreign-key identity (local_plan_id) is completely independent of the
    # plan's own mutable columns - a source/report registered against plan
    # id 14 keeps resolving to plan id 14 after its plan_version changes.
    reloaded_source = session.get(MonitoredSource, source_id)
    reloaded_report = session.get(MonitoredReport, report_id)
    assert reloaded_source.local_plan_id == plan_id
    assert reloaded_report.local_plan_id == plan_id
    assert session.get(LocalPlan, reloaded_source.local_plan_id).plan_version == REG_19["plan_version"]

    # Documented caveat (Gate 3G/3F): config-driven source registration
    # (app.policy.sources._resolve_local_plan_id) matches NEW sources by an
    # EXACT (plan_name, plan_version) triple at registration time only. It
    # is never re-run automatically when an existing plan's plan_version
    # changes - a config entry still stating the OLD "Regulation 18..."
    # plan_version would no longer resolve to this plan if registered
    # AFTER this transition. This is a real, known convention (any new
    # Reg 19 source's config entry must state the NEW plan_version), not a
    # defect in the transition mechanism itself, which this test documents
    # rather than silently assumes away.
    from app.policy.sources import _resolve_local_plan_id
    stale_config_entry = {"plan_name": plan.plan_name, "plan_version": REG_18["plan_version"]}
    assert _resolve_local_plan_id(session, "testcouncil", stale_config_entry) is None
    current_config_entry = {"plan_name": plan.plan_name, "plan_version": REG_19["plan_version"]}
    assert _resolve_local_plan_id(session, "testcouncil", current_config_entry) == plan_id


# --- Test 11: multiple successive transitions ---

def test_11_two_successive_transitions_preserve_chronological_history(session):
    plan = _make_wigan_like_plan(session)

    event_1 = _queue_stage_change(session, plan, REG_19, event_type="new_plan_version")
    approve_change(session, event_1, note="Reg 18 -> Reg 19.")

    event_2 = _queue_stage_change(session, plan, SUBMISSION, event_type="stage_change")
    approve_change(session, event_2, note="Reg 19 -> Submission.")

    session.refresh(plan)
    assert plan.plan_version == SUBMISSION["plan_version"]
    assert plan.status == SUBMISSION["status"]

    rows = _history_rows(session, plan.id)
    assert len(rows) == 2
    assert rows[0].plan_version == REG_18["plan_version"]  # first snapshot: pre-Reg19 state
    assert rows[1].plan_version == REG_19["plan_version"]  # second snapshot: pre-Submission state
    assert rows[0].captured_at <= rows[1].captured_at


# --- Test 12: rejection does not mutate state ---

def test_12_rejecting_a_stage_change_event_leaves_current_state_and_history_untouched(session):
    plan = _make_wigan_like_plan(session)
    event = _queue_stage_change(session, plan, REG_19)

    reject_change(session, event, note="Not yet corroborated by a second official source.")

    session.refresh(plan)
    assert plan.status == REG_18["status"]
    assert plan.raw_status == REG_18["raw_status"]
    assert plan.plan_version == REG_18["plan_version"]
    assert _history_rows(session, plan.id) == []  # no false "approved transition" snapshot

    reloaded = session.get(PolicyChangeEvent, event.id)
    assert reloaded.review_status == "rejected"
    assert reloaded.reviewed_at is not None


# --- Test 13: existing history is append-only ---

def test_13_an_earlier_history_row_is_never_modified_by_a_later_transition(session):
    plan = _make_wigan_like_plan(session)
    event_1 = _queue_stage_change(session, plan, REG_19)
    approve_change(session, event_1)
    [reg18_snapshot] = _history_rows(session, plan.id)
    reg18_snapshot_id = reg18_snapshot.id
    original_values = (reg18_snapshot.status, reg18_snapshot.raw_status, reg18_snapshot.plan_version, reg18_snapshot.captured_at)

    event_2 = _queue_stage_change(session, plan, SUBMISSION)
    approve_change(session, event_2)

    reloaded_reg18_snapshot = session.get(LocalPlanStatusHistory, reg18_snapshot_id)
    assert (reloaded_reg18_snapshot.status, reloaded_reg18_snapshot.raw_status,
            reloaded_reg18_snapshot.plan_version, reloaded_reg18_snapshot.captured_at) == original_values
    assert len(_history_rows(session, plan.id)) == 2  # appended, not replaced


# --- Test 14: raw/direct update bypasses the intended pathway ---
# Not a global ORM prohibition (none is built in this gate) - this documents,
# as an explicit regression test, exactly WHY the trust principle in Gate 3H
# forbids a raw setattr/ad-hoc script for the real Wigan transition: nothing
# stops it at the ORM level, and it silently produces zero history.

def test_14_a_direct_setattr_outside_approve_change_produces_no_history_at_all(session):
    plan = _make_wigan_like_plan(session)

    # Deliberately the ANTI-pattern this gate's trust principle prohibits -
    # exercised here only to prove why it must never be used for the real
    # Wigan transition, not as an endorsed code path.
    plan.plan_version = REG_19["plan_version"]
    plan.status = REG_19["status"]
    plan.raw_status = REG_19["raw_status"]
    session.commit()

    session.refresh(plan)
    assert plan.plan_version == REG_19["plan_version"]  # the mutation "worked"...
    assert _history_rows(session, plan.id) == []  # ...but Reg 18's state is now genuinely, silently lost
