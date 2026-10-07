"""Stage 2.5B V7C-1: the READ-ONLY ordinary monitoring sync preview (app.reporting.opportunity_change.preview_ordinary_sync).

The preview must reuse the one pure planner the real sync executes, perform zero writes, never call a model/network, be deterministic, and carry enough identity/fingerprint
information for a hand-reviewed Category A/B/C manifest - without ever building or applying one.
"""
from __future__ import annotations

import inspect
import json
import socket

import pytest
from sqlalchemy import event, select

import app.reporting.opportunity_change as oc
from app.db.models import Application, OpportunityMonitoringState
from tests.test_buyer_family_feed import LAPSE_AGE, World


@pytest.fixture
def world(session, monkeypatch):
    return World(session, monkeypatch)


def seed(world):
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE)                      # lapse + phases
    world.site(rm_age=300, rm_phase="Phase 1")                                # phase-only
    world.allocation(capacity=8400)                                          # strategic


def table(session):
    return {r.opportunity_id: (r.fingerprint, r.fingerprint_fields, r.last_change_classification, r.last_change_reasons, r.last_change_at)
            for r in session.execute(select(OpportunityMonitoringState)).scalars()}


class WriteGuard:
    """Fails the test on ANY insert/update/delete statement, flush with pending changes, or commit."""

    def __init__(self, session):
        self.session = session
        self.statements = []
        self.engine = session.get_bind()

    def __enter__(self):
        def execute(conn, cursor, statement, *args):
            self.statements.append(statement)
            assert statement.lstrip().upper().startswith(("SELECT", "PRAGMA", "WITH")), f"non-read statement issued: {statement[:80]}"
        def flush(session, context, instances):
            assert not (session.new or session.dirty or session.deleted), "preview staged ORM changes"
        def commit(session):
            raise AssertionError("preview committed")
        self.handlers = (execute, flush, commit)
        event.listen(self.engine, "before_cursor_execute", execute)
        event.listen(self.session, "before_flush", flush)
        event.listen(self.session, "before_commit", commit)
        return self

    def __exit__(self, *exc):
        execute, flush, commit = self.handlers
        event.remove(self.engine, "before_cursor_execute", execute)
        event.remove(self.session, "before_flush", flush)
        event.remove(self.session, "before_commit", commit)


def test_preview_is_read_only_deterministic_and_json_serialisable(session, world, monkeypatch):
    seed(world)
    oc.sync_opportunity_monitoring_state(session)
    before = table(session)
    world.site(rm_age=200, rm_phase="Phase 3")                                # real-world change since the last sync
    session.commit()
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("preview attempted a network connection")))
    with WriteGuard(session) as guard:
        first = oc.preview_ordinary_sync(session)
        second = oc.preview_ordinary_sync(session)
    assert guard.statements and all(s.lstrip().upper().startswith(("SELECT", "PRAGMA", "WITH")) for s in guard.statements)
    assert first == second and first["read_only"] is True
    assert json.loads(json.dumps(first, sort_keys=True)) == first                # machine-readable, no non-serialisable values
    assert table(session) == before                                              # not one monitoring row inserted/updated/deleted
    assert not (session.new or session.dirty or session.deleted)


def test_preview_and_sync_share_the_same_plan_and_agree_on_every_prediction(session, world, monkeypatch):
    seed(world)
    calls = {"plan": 0, "build": 0}
    real_plan, real_build = oc.plan_opportunity_changes, oc._build_sync_plan
    monkeypatch.setattr(oc, "plan_opportunity_changes", lambda *a, **k: calls.__setitem__("plan", calls["plan"] + 1) or real_plan(*a, **k))
    monkeypatch.setattr(oc, "_build_sync_plan", lambda *a, **k: calls.__setitem__("build", calls["build"] + 1) or real_build(*a, **k))
    # 1. empty table: the first-ever sync baselines every detector
    preview = oc.preview_ordinary_sync(session)
    sync = oc.sync_opportunity_monitoring_state(session)
    assert calls == {"plan": 2, "build": 2}                                      # the SAME planner and plan builder served both
    assert (preview["predicted"]["BASELINE_EXISTING"], preview["predicted"]["NEW"], preview["predicted"]["MATERIALLY_CHANGED"], preview["predicted"]["UNCHANGED"]) == \
        (sync["baseline_existing"], sync["new"], sync["materially_changed"], sync["unchanged"])
    assert preview["predicted"]["BASELINE_EXISTING"] == preview["totals"]["current_opportunity_ids"] and preview["baseline_detectors"]
    # 2. steady state, then a new site (NEW inside an already-tracked detector) and a changed application (MATERIALLY_CHANGED)
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE)
    session.query(Application).filter(Application.reference.like("OUT/%")).first().decision = "Refused"
    session.commit()
    preview = oc.preview_ordinary_sync(session)
    sync = oc.sync_opportunity_monitoring_state(session)
    assert (preview["predicted"]["NEW"], preview["predicted"]["MATERIALLY_CHANGED"], preview["predicted"]["UNCHANGED"]) == (sync["new"], sync["materially_changed"], sync["unchanged"])
    assert preview["predicted"]["NEW"] >= 1 and preview["predicted"]["BASELINE_EXISTING"] == 0
    assert oc.preview_ordinary_sync(session)["predicted"]["MATERIALLY_CHANGED"] == 0   # after the real sync a second preview predicts nothing to do


def test_report_carries_category_a_b_c_candidate_information(session, world):
    seed(world)
    oc.sync_opportunity_monitoring_state(session)
    site = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE)                    # new ids inside tracked detectors (Category B shape)
    changed = session.query(Application).filter(Application.reference.like("RM/%")).first()
    changed.decision = "Refused"                                                  # Category C shape: same ids, new fingerprint
    session.add(OpportunityMonitoringState(opportunity_id="planning_delivery:site:99999", opportunity_type="planning_delivery", fingerprint="x",
                                           fingerprint_fields="{}", last_change_classification="BASELINE_EXISTING"))   # tracked, absent from the universe (Category A shape)
    session.commit()
    report = oc.preview_ordinary_sync(session)
    assert "planning_delivery:site:99999" in report["retired_ids"] and report["predicted"]["RETIRED"] == 0 and "never retires" in report["retired_note"]
    assert any(i.endswith(f":{site.id}") or f":{site.id}-" in i for i in report["untracked_ids"])
    assert report["partial_detector_untracked"]                                   # a TRACKED detector with untracked ids: they classify NEW
    assert report["tracked_detector_identities"] == sorted(report["tracked_detector_identities"]) and "planning_delivery:phase" in report["tracked_detector_identities"]
    changes = {c["opportunity_id"]: c for c in report["changes"]}
    assert changes and all(c["classification"] in ("NEW", "MATERIALLY_CHANGED") for c in changes.values())
    modified = [c for c in changes.values() if c["classification"] == "MATERIALLY_CHANGED"]
    assert modified and all(c["previous_fingerprint"] and c["new_fingerprint"] != c["previous_fingerprint"] and c["changed_fields"] for c in modified)
    assert report["by_detector"]["planning_delivery:phase"]["tracked_detector"] is True
    assert report["reasons"] and set(report["reasons"]) <= {r for c in modified for r in c["reasons"]}
    assert {c["opportunity_id"] for c in changes.values()} == {i for i in changes}   # ids unique


def test_detector_semantics_match_the_sync_for_the_phase_identity_and_malformed_history(session, world):
    seed(world)
    session.add(OpportunityMonitoringState(opportunity_id="not-a-parseable-id", opportunity_type="planning_delivery", fingerprint="x", fingerprint_fields="{}",
                                           last_change_classification="BASELINE_EXISTING"))   # historical malformed row: tolerated by the fallback in BOTH paths
    session.commit()
    preview = oc.preview_ordinary_sync(session)
    assert "not-a-parseable-id" in preview["retired_ids"]
    assert all(detector.count(":") == 1 for detector in preview["by_detector"])         # canonical domain:kind, the phase detector is NOT per site
    sync = oc.sync_opportunity_monitoring_state(session)
    assert sync["baseline_existing"] == preview["predicted"]["BASELINE_EXISTING"] and sync["new"] == preview["predicted"]["NEW"]


def test_a_malformed_current_id_raises_in_the_preview_exactly_as_in_the_sync_before_any_write(session, world, monkeypatch):
    seed(world)
    real = oc.build_current_opportunity_universe

    def broken(session_, **kw):
        universe = real(session_, **kw)
        return [*universe, type(universe[0])(**{**universe[0].__dict__, "opportunity_id": "planning_delivery:bogus:abc"})]
    monkeypatch.setattr(oc, "build_current_opportunity_universe", broken)
    with pytest.raises(oc.UnparseableOpportunityId):
        oc.preview_ordinary_sync(session)
    with pytest.raises(oc.UnparseableOpportunityId):
        oc.sync_opportunity_monitoring_state(session)
    assert session.execute(select(OpportunityMonitoringState)).first() is None


def test_the_preview_has_no_write_path_no_apply_mode_and_no_model_or_network():
    import ast
    import textwrap
    import scripts.preview_opportunity_monitoring_sync as script

    def identifiers(obj):
        tree = ast.parse(textwrap.dedent(inspect.getsource(obj)))
        return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} |                {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    reading = identifiers(oc.preview_ordinary_sync) | identifiers(oc._build_sync_plan) | identifiers(oc._changed_fields)
    assert not reading & {"commit", "add", "delete", "flush", "merge", "rollback", "utcnow", "openai", "requests", "httpx", "socket"}, reading
    module = identifiers(script)
    assert not module & {"commit", "add", "delete", "flush", "openai", "requests", "httpx", "argparse", "execute", "apply"}, module
    assert not hasattr(script, "apply")
