"""Offline supplied-response acceptance; no portal/database fixtures."""
import json
import socket
from copy import deepcopy

import pytest

from verification.known_scheme_revisit.model import Revisit, work_key


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("offline test attempted network")
    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


def key(ref="DC/085997", stage="documents", cycle="first", council="stockport", route=None):
    return work_key(cycle, council, ref, stage, route or ("register" if stage == "documents" else "citation_search"))


def doc(body=b"72 affordable retirement apartments; 10 private houses", ref="DC/085997", **overrides):
    return dict(council="stockport", reference=ref, url="fixture://statement", body=body,
                stage="submitted_statement", issued="2024-10-23", published="2024-10-24",
                proposed={"ah_count": 72, "total": 82, "tenure": "proposed social rent"}, **overrides)


def response(documents=(), edges=(), cursor="start", next_cursor=None):
    return dict(cursor=cursor, next=next_cursor, documents=list(documents), edges=list(edges))


def seed_docs(model, cycle="first", ref="DC/085997", council="stockport"):
    model.seed(cycle, council, ref, (("documents", "register"),))


def apply_doc(model, body, now, cycle="first", **kwargs):
    seed_docs(model, cycle)
    return model.run_slice(cycle, {(key(cycle=cycle), "start"): response([doc(body)])}, ["stockport"], now, **kwargs)


def test_unchanged_summary_completed_check_does_not_prevent_new_statement():
    m = Revisit()
    seed_docs(m)
    m.run_slice("first", {(key(), "start"): response()}, ["stockport"], 10)
    assert m.state["work"][key()]["last_success"] == 10
    seed_docs(m, "later")  # no status or unit-change input required
    m.run_slice("later", {(key(cycle="later"), "start"): response([doc()])}, ["stockport"], 20)
    assert m.state["work"][key(cycle="later")]["new"] == 1
    assert m.state["observations"][0]["proposed"]["ah_count"] == 72
    assert m.state["work"][key()]["last_success"] == 10


@pytest.mark.parametrize("validators", [{}, {"etag": "unchanged", "last_modified": "unchanged"}])
def test_same_url_revision_preserves_body_despite_missing_or_lying_validators(validators):
    m = Revisit()
    for cycle, body in [("first", b"original"), ("later", b"revised")]:
        seed_docs(m, cycle)
        d = doc(body)
        d.update(validators)
        m.run_slice(cycle, {(key(cycle=cycle), "start"): response([d])}, ["stockport"], 10)
    versions = next(iter(m.state["versions"].values()))
    assert [bytes.fromhex(v["body_hex"]) for v in versions] == [b"original", b"revised"]
    assert m.state["work"][key(cycle="later")]["revised"] == 1


def test_unchanged_body_no_duplicate_but_reversion_preserved():
    m = Revisit()
    for cycle, body in [("first", b"a"), ("second", b"a"), ("third", b"b"), ("fourth", b"a")]:
        apply_doc(m, body, 10, cycle)
    assert len(next(iter(m.state["versions"].values()))) == 3
    assert m.state["work"][key(cycle="second")]["new"] == 0
    assert m.state["work"][key(cycle="second")]["revised"] == 0


def edge(ref, kind="variation", council="stockport", confidence="verified_reference"):
    return dict(council=council, reference=ref, type=kind, confidence=confidence,
                citation="fixture: explicit application reference")


def test_focus_chain_traverses_verified_variation_then_discharge_across_checkpoints():
    m = Revisit()
    m.seed("first", "stockport", "DC/085997")
    root = key(stage="relationships")
    m.run_slice("first", {(key(), "start"): response(), (root, "start"): response(edges=[edge("DC/093884")])}, ["stockport"], 10)
    m = Revisit(json.loads(json.dumps(m.state)))
    variation = key("DC/093884", "relationships")
    m.run_slice("first", {(key("DC/093884"), "start"): response([doc(ref="DC/093884")]),
                          (variation, "start"): response(edges=[edge("DC/094889", "discharge")])}, ["stockport"], 20)
    assert key("DC/094889") in m.state["work"]
    assert [(e["type"], e["route"], e["confidence"]) for e in m.state["edges"]] == [
        ("variation", "citation_search", "verified_reference"), ("discharge", "citation_search", "verified_reference")]
    observation = m.state["observations"][0]
    assert observation["application"] == ["stockport", "dc/093884"]
    assert observation["stage"] == "submitted_statement"
    assert observation["review"] == "unreviewed"
    assert observation["issued"] != observation["published"]
    assert observation["observed"] == 20


@pytest.mark.parametrize("candidate", [edge("DC/095922", confidence="address_only"),
                                       edge("SITE/313", council="tameside"),
                                       edge("DC/095922", kind="same_address")])
def test_hyde_ambiguous_or_cross_council_never_copies_evidence(candidate):
    m = Revisit()
    m.seed("first", "stockport", "DC/098428")
    before = len(m.state["work"])
    m.run_slice("first", {(key("DC/098428"), "start"): response(),
        (key("DC/098428", "relationships"), "start"): response(edges=[candidate])}, ["stockport"], 10)
    assert len(m.state["work"]) == before
    assert m.state["edges"][0]["confidence"] == "review_candidate"
    assert not m.state["observations"]


def test_even_verified_same_council_edge_never_transfers_ah():
    m = Revisit()
    seed_docs(m, ref="DC/095922")
    d = doc(ref="DC/095922")
    d["proposed"] = {"ah_count": 0}
    m.run_slice("first", {(key("DC/095922"), "start"): response([d])}, ["stockport"], 1)
    m.seed("first", "stockport", "DC/098428")
    m.run_slice("first", {(key("DC/098428"), "start"): response(),
        (key("DC/098428", "relationships"), "start"): response(edges=[edge("DC/095922")])}, ["stockport"], 2)
    assert all(o["application"][1] == "dc/095922" for o in m.state["observations"])


def test_wrong_application_document_is_rejected_atomically():
    m = Revisit()
    seed_docs(m, ref="DC/098428")
    m.run_slice("first", {(key("DC/098428"), "start"): response([doc(ref="DC/095922")])}, ["stockport"], 1)
    assert not m.state["versions"]
    assert m.state["work"][key("DC/098428")]["outcome"] == "partial"


@pytest.mark.parametrize("failure", [{"error": "PDF inaccessible"}, response([doc(None)])])
def test_failure_or_304_keeps_prior_success_and_backoff(failure):
    m = Revisit()
    apply_doc(m, b"old", 10)
    seed_docs(m, "later")
    k = key(cycle="later")
    m.run_slice("later", {(k, "start"): failure}, ["stockport"], 20)
    w = m.state["work"][k]
    assert (w["last_success"], w["last_attempt"], w["outcome"], w["cursor"]) == (10, 20, "partial", "start")
    assert w["next_due"] == 86420
    assert m.run_slice("later", {}, ["stockport"], 21)["attempts"] == 0


def test_checkpoint_replay_interruption_and_resume_preserve_earlier_progress():
    m = Revisit()
    seed_docs(m)
    first = {(key(), "start"): response([doc(b"first")], next_cursor="page2")}
    before = json.dumps(m.state)
    m.run_slice("first", first, ["stockport"], 1)
    committed = json.dumps(m.state)
    replay = Revisit(json.loads(before))  # crash before transaction publication
    replay.run_slice("first", first, ["stockport"], 1)
    assert replay.state == json.loads(committed)
    resumed = Revisit(json.loads(committed))
    resumed.run_slice("first", {(key(), "page2"): {"error": "interrupted"}}, ["stockport"], 2)
    assert len(resumed.state["observations"]) == 1
    assert resumed.state["work"][key()]["cursor"] == "page2"
    resumed.run_slice("first", {(key(), "page2"): response([doc(b"second")], cursor="page2")}, ["stockport"], 86402)
    assert resumed.state["work"][key()]["outcome"] == "complete"
    assert len(resumed.state["observations"]) == 2
    assert resumed.run_slice("first", first, ["stockport"], 86403)["attempts"] == 0


def test_complete_early_council_survives_late_failure_and_budget_deferral():
    m = Revisit()
    for council in ["bury", "stockport", "tameside"]:
        seed_docs(m, council=council)
    report = m.run_slice("first", {(key(council="bury"), "start"): response(),
        (key(), "start"): {"error": "timeout"}}, ["bury", "stockport", "tameside"], 1, steps=2)
    assert m.state["work"][key(council="bury")]["outcome"] == "complete"
    assert m.state["work"][key()]["outcome"] == "partial"
    assert m.state["work"][key(council="tameside")]["outcome"] == "deferred"
    assert report["deferred"] == 1
    assert len(m.coverage("first")) == 3


def test_one_council_backlog_cannot_consume_later_council_slice():
    m = Revisit()
    for ref in ["A", "B", "C"]:
        seed_docs(m, ref=ref)
    seed_docs(m, council="tameside")
    report = m.run_slice("first", {(key(council="tameside"), "start"): response()}, ["stockport", "tameside"], 1, per_council=1)
    assert report["attempts"] == 2
    assert m.state["work"][key(council="tameside")]["outcome"] == "complete"
    assert report["deferred"] == 2


@pytest.mark.parametrize("limit", [{"body_limit": 2}, {"total_bytes": 2}])
def test_bytes_bounded_no_false_completion(limit):
    m = Revisit()
    apply_doc(m, b"oversized", 1, **limit)
    assert not m.state["versions"]
    assert m.state["work"][key()]["reason"] == "body budget"


def test_frontier_limit_rolls_back_cursor_and_children():
    m = Revisit()
    m.seed("first", "stockport", "DC/085997", (("relationships", "citation_search"),))
    k = key(stage="relationships")
    m.run_slice("first", {(k, "start"): response(edges=[edge("DC/093884")])}, ["stockport"], 1, max_work=1)
    assert len(m.state["work"]) == 1
    assert not m.state["edges"]
    assert m.state["work"][k]["cursor"] == "start"


def test_missing_route_is_partial_not_universal_completion():
    m = Revisit()
    m.seed("first", "stockport", "DC/085997", (("relationships", "citation_search"), ("relationships", "related_tab")))
    m.run_slice("first", {(key(stage="relationships"), "start"): response()}, ["stockport"], 1)
    states = next(iter(m.coverage("first").values()))
    assert states["relationships:citation_search"]["outcome"] == "complete"
    assert states["relationships:related_tab"]["outcome"] == "partial"


def test_new_statement_conflict_preserves_proposals_no_selected_truth():
    m = Revisit()
    apply_doc(m, b"original", 1)
    prior = deepcopy(m.state["observations"][0])
    seed_docs(m, "later")
    d = doc(b"changed")
    d["proposed"] = {"ah_count": 70, "tenure": "different proposal"}
    m.run_slice("later", {(key(cycle="later"), "start"): response([d])}, ["stockport"], 2)
    assert m.state["observations"][0] == prior
    assert [o["proposed"]["ah_count"] for o in m.state["observations"]] == [72, 70]
    assert all(o["review"] == "unreviewed" for o in m.state["observations"])
    assert "current_ah" not in m.state


def test_fixture_workload_is_explicit_not_production_extrapolation():
    m = Revisit()
    for council, ref in [("stockport", "DC/085997"), ("stockport", "DC/093884"),
                         ("stockport", "DC/094889"), ("stockport", "DC/098428"),
                         ("stockport", "DC/095922"), ("tameside", "SITE/313")]:
        m.seed("first", council, ref)
    assert m.workload("first") == dict(applications=6, document_checks=6, relationship_lookups=6, deferred=0, incomplete=12)


def test_frontier_budget_can_resume_without_failure_backoff():
    m = Revisit()
    m.seed("first", "stockport", "DC/085997", (("relationships", "citation_search"),))
    k = key(stage="relationships")
    responses = {(k, "start"): response(edges=[edge("DC/093884")])}
    m.run_slice("first", responses, ["stockport"], 1, max_work=1)
    assert m.state["work"][k]["failures"] == 0
    m.run_slice("first", responses, ["stockport"], 2, max_work=3)
    assert m.state["work"][k]["outcome"] == "complete"
    assert len(m.state["work"]) == 3


def test_backoff_cap_and_server_retry_after_are_respected():
    m = Revisit()
    seed_docs(m)
    now = 1
    for expected_delay in [86400, 172800, 345600, 604800, 604800]:
        m.run_slice("first", {(key(), "start"): {"error": "unavailable"}}, ["stockport"], now)
        assert m.state["work"][key()]["next_due"] == now + expected_delay
        now += expected_delay
    m.run_slice("first", {(key(), "start"): {"error": "rate limited", "retry_after": 900000}}, ["stockport"], now)
    assert m.state["work"][key()]["next_due"] == now + 900000


def test_invalid_limits_and_duplicate_council_allocation_rejected():
    m = Revisit()
    with pytest.raises(ValueError, match="positive"):
        m.run_slice("first", {}, [], 1, steps=0)
    with pytest.raises(ValueError, match="duplicate"):
        m.run_slice("first", {}, ["stockport", "STOCKPORT"], 1)


def test_cursor_loop_is_partial_and_response_not_applied():
    m = Revisit()
    seed_docs(m)
    m.run_slice("first", {(key(), "start"): response([doc()], next_cursor="start")}, ["stockport"], 1)
    assert not m.state["observations"]
    assert m.state["work"][key()]["reason"] == "cursor loop"


def test_oldest_attempt_allows_deferred_application_next_turn():
    m = Revisit()
    for ref in ["A", "B"]:
        seed_docs(m, ref=ref)
    m.run_slice("first", {(key("A"), "start"): response(next_cursor="next")}, ["stockport"], 1, per_council=1)
    m.run_slice("first", {(key("B"), "start"): response()}, ["stockport"], 2, per_council=1)
    assert m.state["work"][key("B")]["outcome"] == "complete"
    assert m.state["work"][key("A")]["cursor"] == "next"


def test_measured_fixture_cycle_finishes_without_recreating_identical_versions():
    from verification.known_scheme_revisit.workload import measure
    report = measure()
    assert report["document_body_revalidations"] == 6
    assert report["relationship_pages"] == 6
    assert report["slices"][0]["deferred"] == 8
    assert report["slices"][-1]["incomplete"] == 0
    assert sum(s["attempts"] for s in report["slices"]) == 12
    assert report["new_version_observations_during_revisit"] == 0
