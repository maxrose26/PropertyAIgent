"""Stage 2.5B V7A: the pure derivation of planning-delivery ACQUISITION phasing evidence (app.reporting.acquisition_phasing).

Offline. Real Application / Site ORM objects (transient, or in the in-memory test schema where a query count is the point). The derivation must make no database call,
exclude the unphased bucket, require a substantive GRANTED anchor, treat only assumed-lapsed phases as historical, and never claim more than 'phased delivery is evidenced'.
"""
from __future__ import annotations

import ast
import datetime as dt
import inspect
import random

import pytest
from sqlalchemy import event

import app.reporting.acquisition_phasing as ap
from app.db.models import Application, SchemeIntelligence, Site
from app.policy.buyer_matching import (
    PHASING_CURRENT_EVIDENCED_PHASE, PHASING_DOCUMENTED, PHASING_HISTORICAL_ONLY, PHASING_NONE_IDENTIFIED, AcquisitionPhasingEvidence,
)

TODAY = dt.date.today()
RM, OUTLINE = "Approval of Reserved Matters", "Outline"
LAPSED_AGE = 365 * 3 + 200


def portal(days_ago: int) -> str:
    return (TODAY - dt.timedelta(days=days_ago)).strftime("%a %d %b %Y")


def app(i, proposal, *, decision="Granted", age=300, application_type=RM, status="Decided", site_id=1):
    return Application(id=i, council_code="testcouncil", reference=f"R/{i}", site_id=site_id, proposal=proposal, application_type=application_type, status=status,
                       decision=decision, decision_issued_date=portal(age) if decision else None, application_received=portal((age or 0) + 90))


SITE = Site(id=1, council_code="testcouncil", canonical_address="x", display_address="X")


def state(applications, site=SITE):
    return ap.derive_acquisition_phasing_evidence(applications, site).state


def test_a_a_current_granted_named_phase_is_current():
    assert state([app(1, "Reserved matters for Phase 2 of 30 dwellings")]) == PHASING_CURRENT_EVIDENCED_PHASE


@pytest.mark.parametrize("decision,status", [("Refused", "Decided"), (None, "Withdrawn"), (None, "Pending consideration")])
def test_b_c_d_refused_withdrawn_and_undecided_phases_are_not_current_and_not_historical(decision, status):
    result = state([app(1, "Reserved matters for Phase 2 of 30 dwellings", decision=decision, status=status)])
    assert result == PHASING_NONE_IDENTIFIED                       # never even HISTORICAL: there is no granted anchor


@pytest.mark.parametrize("proposal,application_type", [
    ("Non-material amendment to Phase 2 layout", "Non-Material Amendment"),
    ("Discharge of condition 5 for Phase 2", "Discharge of Conditions"),
])
def test_e_conditions_or_nma_only_named_phase_is_not_current(proposal, application_type):
    assert state([app(1, proposal, application_type=application_type)]) == PHASING_NONE_IDENTIFIED


def test_f_an_assumed_lapsed_granted_phase_is_historical_not_current():
    assert state([app(1, "Reserved matters for Phase 2 of 30 dwellings", age=LAPSED_AGE)]) == PHASING_HISTORICAL_ONLY


def test_g_current_wins_over_historical():
    apps = [app(1, "Reserved matters for Phase 1", age=LAPSED_AGE + 100), app(2, "Reserved matters for Phase 2", age=100)]
    assert state(apps) == PHASING_CURRENT_EVIDENCED_PHASE


def test_the_unphased_bucket_never_qualifies_as_a_child_phase():
    from app.pipeline.phase_tracking import UNPHASED_LABEL, group_applications_by_phase
    outline_only = [app(1, "Outline erection of 400 dwellings", application_type=OUTLINE, age=800)]
    assert (UNPHASED_LABEL, "phase") in group_applications_by_phase(outline_only) and state(outline_only) == PHASING_NONE_IDENTIFIED
    mixed = outline_only + [app(2, "Variation of condition 3", application_type="Discharge of Conditions", age=100)]
    assert state(mixed) == PHASING_NONE_IDENTIFIED


def test_a_parent_plus_a_current_phase_is_current_and_the_result_is_order_independent():
    apps = [app(1, "Outline erection of 400 dwellings", application_type=OUTLINE, age=800), app(2, "Reserved matters for Phase 1 of 125", age=200),
            app(3, "Reserved matters for Phase 2", decision="Refused"), app(4, "Reserved matters for Phase 3", age=LAPSED_AGE)]
    baseline = state(apps)
    assert baseline == PHASING_CURRENT_EVIDENCED_PHASE
    for seed in range(5):
        shuffled = apps[:]
        random.Random(seed).shuffle(shuffled)
        assert state(shuffled) == baseline


def test_without_the_site_row_currency_cannot_be_verified_so_nothing_is_claimed():
    assert state([app(1, "Reserved matters for Phase 2 of 30 dwellings")], site=None) == PHASING_NONE_IDENTIFIED


def test_documented_phasing_is_reserved_and_is_never_produced_here():
    produced = {state(apps) for apps in (
        [app(1, "Reserved matters for Phase 2")], [app(1, "Reserved matters for Phase 2", age=LAPSED_AGE)], [app(1, "Outline erection of 400", application_type=OUTLINE)],
    )}
    assert PHASING_DOCUMENTED not in produced
    assert AcquisitionPhasingEvidence(PHASING_DOCUMENTED).state == PHASING_DOCUMENTED          # the state exists (dormant) for Stage 2.6
    with pytest.raises(ValueError):
        AcquisitionPhasingEvidence("PROBABLY_PHASED")


def test_the_derivation_makes_no_database_call_and_never_lazy_loads_scheme_intelligence(session):
    site = Site(council_code="testcouncil", canonical_address="s", display_address="S")
    session.add(site)
    session.flush()
    rows = [Application(council_code="testcouncil", reference=f"R/{i}", site_id=site.id, proposal=f"Reserved matters for Phase {i} of 30 dwellings",
                        application_type=RM, status="Decided", decision="Granted", decision_issued_date=portal(100 + i), application_received=portal(200))
            for i in (1, 2, 3)]
    session.add_all(rows)
    session.flush()
    for row in rows:
        session.add(SchemeIntelligence(application_id=row.id, total_units_final=30))
    session.commit()
    applications = session.query(Application).filter(Application.site_id == site.id).all()
    site = session.get(Site, site.id)
    statements = []
    engine = session.get_bind()
    listener = lambda conn, cursor, statement, *a: statements.append(statement)   # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        session.execute(__import__("sqlalchemy").text("select 1"))
        assert statements, "positive control: the listener must see a query"          # so an empty list below is not vacuous
        statements.clear()
        assert ap.derive_acquisition_phasing_evidence(applications, site).state == PHASING_CURRENT_EVIDENCED_PHASE
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert statements == []


def test_the_module_is_pure_and_does_not_reuse_the_strategic_phasing_flag():
    tree = ast.parse(inspect.getsource(ap))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m and any(token in m for token in ("sqlalchemy", "openai", "requests", "session")) for m in imported)
    identifiers = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "has_phasing_evidence" not in identifiers


@pytest.mark.parametrize("card,expected", [
    ({"id": "opp-phase-5-2", "phase_code": "2"}, ("2", False)),
    ({"id": "opp-phase-5-Whole site / unphased", "phase_code": "Whole site / unphased"}, (None, False)),
    ({"id": "opp-lapse-5"}, (None, False)),
    ({"id": "opp-recent-permission-5"}, (None, True)),
    ({"id": "opp-long-pending-5"}, (None, True)),
])
def test_self_scope_guard_inputs_for_feed_cards(card, expected):
    assert ap.subject_scope_for_feed_card(card) == expected


@pytest.mark.parametrize("opportunity_id,expected", [
    ("planning_delivery:phase:5:2", ("2", False)),
    ("planning_delivery:phase:5:Whole site / unphased", (None, False)),
    ("planning_delivery:phase:5:3B:odd", ("3B:odd", False)),
    ("planning_delivery:site:5", (None, False)),
    ("planning_delivery:recent_permission:5", (None, True)),
    ("planning_delivery:long_pending_application:5", (None, True)),
])
def test_self_scope_guard_inputs_for_opportunity_ids(opportunity_id, expected):
    assert ap.subject_scope_for_opportunity_id(opportunity_id) == expected
