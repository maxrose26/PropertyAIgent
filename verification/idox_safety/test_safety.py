"""Synthetic offline safety proofs, never assertions of live Idox compatibility."""
from dataclasses import replace
import copy
import json
from pathlib import Path
import socket
import pytest
from verification.da0.contracts import Capability, FieldEvidence, FieldState, RawEnvelope, status_claim_complete
from verification.idox_safety.collector import *
from verification.idox_safety.rehearsal import page, tape, supervise


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*a, **kw):
        raise AssertionError("ZERO COUNCIL REQUESTS: network prohibited")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


def run(body=None, exchanges=None, council="bolton", **kw):
    t = FixtureTape(exchanges) if exchanges is not None else tape(body)
    result = collect(council, "2026-10-01", "2026-10-01", CONFIGS[council].basis, t, **kw)
    assert t.closed
    if result["completion_state"] not in {"COMPLETE", "COMPLETE_ZERO_RESULTS"}:
        assert not result["candidates"] and not result["raw_evidence"] and not result["terminal_proof"]
    return result


def sequence(first, second):
    return [Exchange("FORM", (b"OFFLINE_FORM_V1",)), Exchange("SUBMIT", (first,)), second]


@pytest.mark.parametrize("council,basis", [("bolton", "RECEIVED"), ("stockport", "VALIDATED"), ("wigan", "RECEIVED")])
def test_three_configs(council, basis):
    r = run(council=council)
    assert r["completion_state"] == "COMPLETE" and r["requests"] == 2
    assert r["date_basis"] == basis and not r["live_ready"]
    assert r["raw_evidence"][0]["fields"].keys() == {"reference"}
    assert not CONFIGS[council].operational


def test_retained_configuration_consistency():
    import yaml
    retained = yaml.safe_load(Path("config/councils.yaml").read_text())["councils"]
    for name, c in CONFIGS.items():
        assert c.base == retained[name]["base_url"]
        assert c.basis.lower() == retained[name]["date_field_mode"]
        assert c.date_fields[0] == f'date(application{c.basis.title()}Start)'


@pytest.mark.parametrize("start,end,basis", [("2026-10-02", "2026-10-01", "RECEIVED"), ("2026-10-01", "2026-10-03", "RECEIVED"),
                                            ("bad", "2026-10-01", "RECEIVED"), ("2026-10-01", "2026-10-01", "VALIDATED")])
def test_window_rejection(start, end, basis):
    with pytest.raises(Failure):
        collect("bolton", start, end, basis, tape())


def test_multi_page_complete():
    first = page(total=2, terminal=False, next_page=2)
    second = page(2, 2, [("SYNTH/002", "applicationDetails.do?activeTab=summary&keyVal=SYNTH2")])
    r = run(exchanges=sequence(first, Exchange("NEXT:2", (second,))))
    assert r["completion_state"] == "COMPLETE" and r["candidate_count"] == 2
    assert r["pages_attempted"] == r["pages_accepted"] == 2 and r["requests"] == 3


def test_failed_next_includes_partial_bytes():
    first = page(total=2, terminal=False, next_page=2)
    r = run(exchanges=sequence(first, Exchange("NEXT:2", (b"abc", b"def"), failure="broken")))
    assert r["completion_state"] == "PARTIAL_RETRIEVAL" and r["requests"] == 3
    assert r["received_bytes"] == len(b"OFFLINE_FORM_V1") + len(first) + 6


def test_loop():
    first = page(total=2, terminal=False, next_page=2)
    r = run(exchanges=sequence(first, Exchange("NEXT:2", (first,))))
    assert r["failure_reason"] == "repeated_page"


@pytest.mark.parametrize("body", [page(total=2, terminal=False), page(total=2), page(terminal=True, next_page=2)])
def test_missing_terminal_or_continuation(body):
    assert run(body)["completion_state"] == "PARTIAL_RETRIEVAL"


def test_zero_positive_proof():
    assert run(page(total=0, entries=[], zero=True))["completion_state"] == "COMPLETE_ZERO_RESULTS"


@pytest.mark.parametrize("body", [b"<html>No results</html>", b"<html><", page(total=0, entries=[], zero=False), page(total=1, entries=[]), b"<!DOCTYPE x><x/>"])
def test_unrecognised_zero_and_malformed(body):
    assert run(body)["completion_state"] == "SOURCE_LAYOUT_UNRECOGNISED"


def test_shared_key_tabs_and_identical_duplicate():
    links = [("SYNTH/001", "applicationDetails.do?activeTab=summary&keyVal=SYNTH1"),
             ("SYNTH/001", "applicationDetails.do?activeTab=details&keyVal=SYNTH1")]
    r = run(page(entries=links+links), council="wigan")
    assert r["candidate_count"] == 1 and r["completion_state"] == "COMPLETE"


@pytest.mark.parametrize("entries", [
    [("REF1", "applicationDetails.do?activeTab=summary&keyVal=KEY1"), ("REF2", "applicationDetails.do?activeTab=details&keyVal=KEY1")],
    [("REF1", "applicationDetails.do?activeTab=summary&keyVal=KEY1"), ("REF1", "applicationDetails.do?activeTab=summary&keyVal=KEY2")]])
def test_identity_conflict(entries):
    assert run(page(entries=entries))["completion_state"] == "AMBIGUOUS_IDENTITY"


def test_missing_reference_is_qualified_not_manufactured():
    r = run(page(entries=[("", "applicationDetails.do?activeTab=summary&keyVal=KEY1")]))
    assert r["completion_state"] == "COMPLETE" and r["candidate_count"] == 1
    assert r["unique_application_identities"] == 0 and not r["raw_evidence"]
    assert r["candidates"][0]["qualification"] == "SELECTIVE_DETAIL_REQUIRED"
    assert not r["checkpoint_eligible"]


@pytest.mark.parametrize("link", [
    "https://evil.invalid/applicationDetails.do?activeTab=summary&keyVal=K", 
    "https://paplanning.bolton.gov.uk.evil.invalid/online-applications/applicationDetails.do?activeTab=summary&keyVal=K",
    "https://evilpaplanning.bolton.gov.uk/online-applications/applicationDetails.do?activeTab=summary&keyVal=K",
    "https://u@paplanning.bolton.gov.uk/online-applications/applicationDetails.do?activeTab=summary&keyVal=K",
    "https://paplanning.bolton.gov.uk:443/online-applications/applicationDetails.do?activeTab=summary&keyVal=K",
    "http://paplanning.bolton.gov.uk/online-applications/applicationDetails.do?activeTab=summary&keyVal=K",
    "//evil.invalid/x", "javascript:alert(1)", "file:///tmp/x", "data:text/html,x", "\\evil.invalid/x",
    "applicationDetails.do?activeTab=documents&keyVal=K", "applicationDetails.do?activeTab=furtherInformation&keyVal=K",
    "applicationDetails.do?activeTab=relatedCases&keyVal=K", "applicationDetails.do?activeTab=history&keyVal=K",
    "download.do?keyVal=K", "applicationDetails.do?activeTab=summary&keyVal=K&keyVal=Z",
    "applicationDetails.do?activeTab=summary&keyVal=K&address=x", "applicationDetails.do?activeTab=summary&keyVal=%4b",
    "applicationDetails.do?activeTab=summary&keyVal=K#docs"])
def test_url_denial(link):
    r = run(page(entries=[("REF1", link)]))
    assert r["completion_state"] == "PARTIAL_RETRIEVAL"


def test_search_fields_cannot_expand():
    c = CONFIGS["bolton"]
    with pytest.raises(Failure):
        admit(c, c.search + "&applicant=x", "search")
    with pytest.raises(Failure):
        admit(c, c.base + "/applicationDetails.do?activeTab=summary&keyVal=K", "search")


@pytest.mark.parametrize("redirect", ["https://evil.invalid/x", CONFIGS["bolton"].search])
def test_redirect_counted_never_followed(redirect):
    r = run(exchanges=[Exchange("FORM", (b"redirect-body",), status=302, redirect=redirect)])
    assert r["requests"] == r["redirects"] == 1 and r["retries"] == 0
    assert r["received_bytes"] == 13 and r["failure_reason"] == "redirect_denied"


@pytest.mark.parametrize("status", [403, 404, 429, 500])
def test_source_error_no_retry(status):
    r = run(exchanges=[Exchange("FORM", (b"err",), status=status)])
    assert r["completion_state"] == "SOURCE_UNAVAILABLE" and r["requests"] == 1
    assert r["received_bytes"] == 3 and r["retries"] == 0


def test_response_overflow_actual_body():
    r = run(exchanges=[Exchange("FORM", (b"0123456789", b"abc"))], limits=Limits(response_bytes=12))
    assert r["completion_state"] == "BUDGET_EXCEEDED" and r["received_bytes"] == 13


def test_total_bytes_overflow():
    r = run(limits=Limits(total_bytes=len(page())+13))
    assert r["failure_reason"] == "body_budget"
    assert r["received_bytes"] == len(page()) + len(b"OFFLINE_FORM_V1")


def test_request_overflow_no_transport_operation():
    r = run(limits=Limits(requests=1))
    assert r["completion_state"] == "BUDGET_EXCEEDED" and r["requests"] == 1


def test_page_overflow():
    r = run(page(total=2, terminal=False, next_page=2), limits=Limits(pages=1))
    assert r["failure_reason"] == "page_budget" and r["requests"] == 2


def test_timeout_partial_body():
    r = run(exchanges=[Exchange("FORM", (b"partial",), failure="timeout")])
    assert r["completion_state"] == "TIMEOUT" and r["received_bytes"] == 7


@pytest.mark.parametrize("exchange", [Exchange("FORM", (b"body",), attachment=True), Exchange("FORM", (b"body",), content_encoding="gzip")])
def test_attachment_compression_denial(exchange):
    assert run(exchanges=[exchange])["completion_state"] == "PARTIAL_RETRIEVAL"


def test_no_underaccounted_extra_operation():
    r = run(exchanges=[Exchange("FORM", (b"OFFLINE_FORM_V1",)), Exchange("SUBMIT", (page(),)), Exchange("DETAIL", (b"x",))])
    assert r["failure_reason"] == "unconsumed_fixture_exchange" and r["requests"] == 2


def test_da0_discovery_does_not_certify_status():
    d = run()["raw_evidence"][0]
    d["fields"] = {k: FieldEvidence(**v) for k, v in d["fields"].items()}
    d["source_timestamps"] = {k: FieldEvidence(**v) for k, v in d["source_timestamps"].items()}
    e = RawEnvelope(**d)
    assert e.capability == Capability.NEW.value and not status_claim_complete(e, "SYNTH/001")
    with pytest.raises(ValueError):
        replace(e, fields={})
    with pytest.raises(ValueError):
        replace(e, discovery_window=None)


def test_closed_artifact_and_deterministic_order():
    r = run()
    assert encode_result(r) == encode_result(copy.deepcopy(r))
    r["private_text"] = "must fail"
    with pytest.raises(Failure):
        encode_result(r)


def test_no_network_database_model_imports():
    import ast
    for name in ("collector.py", "rehearsal.py"):
        tree = ast.parse(Path("verification/idox_safety", name).read_text())
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): modules += [a.name for a in node.names]
            if isinstance(node, ast.ImportFrom): modules += [node.module or ""]
        assert not any(m.startswith(("app", "requests", "httpx", "urllib.request", "playwright", "openai", "sqlalchemy")) for m in modules)
    with pytest.raises(AssertionError):
        socket.create_connection(("example.invalid", 443))


@pytest.mark.parametrize("scenario,expected", [("bolton", "COMPLETE"), ("stockport", "COMPLETE"), ("wigan", "COMPLETE"),
                                             ("hung", "TIMEOUT"), ("exception", "PARTIAL_RETRIEVAL"), ("overflow", "BUDGET_EXCEEDED")])
def test_independent_process_deadline_cleanup(scenario, expected):
    r = supervise(scenario, deadline=0.5 if scenario == "hung" else 5)
    assert r["outcome"] == expected and r["cleanup_verified"]
    assert r["elapsed_seconds"] < (2 if scenario == "hung" else 6.5)
    if expected != "COMPLETE": assert r["artifact"] is None


def test_artifact_overflow_emits_only_failure_metadata():
    entries = [(f"SYNTH/{i:03d}", f"applicationDetails.do?activeTab=summary&keyVal=KEY{i}") for i in range(100)]
    r = run(page(total=100, entries=entries))
    encoded = encode_result(r)
    result = json.loads(encoded)
    assert len(encoded) <= 65_536 and result["completion_state"] == "BUDGET_EXCEEDED"
    assert not result["candidates"] and not result["raw_evidence"]


@pytest.mark.parametrize("field,value", [("requests", -1), ("requests", 7), ("retries", 1), ("elapsed_seconds", float("nan")),
                                         ("live_ready", True), ("candidate_count", 2), ("terminal_proof", False)])
def test_malformed_audit_rejected(field, value):
    r = run()
    r[field] = value
    with pytest.raises(Failure):
        encode_result(r)


def test_page_overlap_rejected():
    first = page(total=2, terminal=False, next_page=2)
    second = page(2, 2)
    assert run(exchanges=sequence(first, Exchange("NEXT:2", (second,))))["failure_reason"] == "overlapping_page_membership"


def test_count_drift_rejected():
    first = page(total=2, terminal=False, next_page=2)
    second = page(2, 1, [("SYNTH/002", "applicationDetails.do?activeTab=summary&keyVal=SYNTH2")])
    assert run(exchanges=sequence(first, Exchange("NEXT:2", (second,))))["failure_reason"] == "count_drift"


def test_foreign_transport_rejected():
    class Sneaky:
        def take(self, op): raise AssertionError("must not execute")
    with pytest.raises(Failure):
        collect("bolton", "2026-10-01", "2026-10-01", "RECEIVED", Sneaky())
