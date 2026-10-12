"""Bounded discovery state machine over an inert synthetic exchange tape.

The fixture decoder is deliberately NOT advertised as a real Idox HTML parser.
No HTTP client, browser, database or application import exists here. Protocol
binding (form submission, continuation and live terminal proof) remains BLOCKED.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
import math
import re
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit
from xml.etree import ElementTree as ET

from verification.da0.contracts import Capability, FieldEvidence, FieldState, RawEnvelope, VERSION as DA0_VERSION, digest

VERSION = "idox-offline-safety-v1"
CONFIG_VERSION = "retained-council-config-v1"
STATES = frozenset({"COMPLETE", "COMPLETE_ZERO_RESULTS", "PARTIAL_RETRIEVAL", "BUDGET_EXCEEDED",
                    "SOURCE_LAYOUT_UNRECOGNISED", "AMBIGUOUS_IDENTITY", "SOURCE_UNAVAILABLE", "TIMEOUT"})


class Failure(Exception):
    def __init__(self, state, reason):
        self.state, self.reason = state, reason
        super().__init__(reason)


def check(ok, state, reason):
    if not ok:
        raise Failure(state, reason)


@dataclass(frozen=True)
class Config:
    council: str
    base: str
    basis: str
    qualification: str
    operational: bool = False

    @property
    def search(self):
        return self.base + "/search.do?action=advanced&searchType=Application"

    @property
    def date_fields(self):
        kind = "Validated" if self.basis == "VALIDATED" else "Received"
        return (f"date(application{kind}Start)", f"date(application{kind}End)")


CONFIGS = {
    "bolton": Config("bolton", "https://paplanning.bolton.gov.uk/online-applications", "RECEIVED",
                     "HTTP date-form submission and live result proof UNPROVED"),
    "stockport": Config("stockport", "https://planning.stockport.gov.uk/PlanningData-live", "VALIDATED",
                        "Historical 429 risk; detail pacing is not a discovery throughput measurement"),
    "wigan": Config("wigan", "https://planning.wigan.gov.uk/online-applications", "RECEIVED",
                    "Shared key/tab URLs require identity reconciliation; live protocol UNPROVED"),
}


@dataclass(frozen=True)
class Limits:
    requests: int = 6
    pages: int = 2
    candidates: int = 100
    response_bytes: int = 1_000_000
    total_bytes: int = 2_000_000
    seconds: float = 30

    def __post_init__(self):
        for name, cap in (("requests", 6), ("pages", 2), ("candidates", 100),
                          ("response_bytes", 1_000_000), ("total_bytes", 2_000_000)):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= cap:
                raise ValueError("invalid offline limit")
        if type(self.seconds) not in (int, float) or not 0 < self.seconds <= 30:
            raise ValueError("invalid deadline")


def window(start, end, basis, config):
    check(config == CONFIGS.get(config.council) and not config.operational, "PARTIAL_RETRIEVAL", "configuration_not_admitted")
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
    except (ValueError, TypeError):
        raise Failure("PARTIAL_RETRIEVAL", "invalid_window") from None
    check(a.isoformat() == start and b.isoformat() == end and 0 <= (b-a).days < 2,
          "PARTIAL_RETRIEVAL", "window_exceeds_two_calendar_days")
    check(basis == config.basis, "PARTIAL_RETRIEVAL", "date_basis_mismatch")
    return {"basis": basis, "start": start, "end": end}


def admit(config, link, purpose):
    """Strict URI checks; no fetching. Metadata tab aliases are never navigated."""
    check(isinstance(link, str) and 0 < len(link) <= 512 and not re.search(r"[\s\\%]", link),
          "PARTIAL_RETRIEVAL", "malformed_url")
    u = urljoin(config.base + "/", link)
    try:
        p, origin = urlsplit(u), urlsplit(config.base)
        port = p.port
        pairs = parse_qsl(p.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise Failure("PARTIAL_RETRIEVAL", "malformed_url") from None
    check(p.scheme == "https" and p.netloc == origin.netloc and port is None
          and not p.username and not p.password and not p.fragment,
          "PARTIAL_RETRIEVAL", "origin_denied")
    check(len(pairs) == len(dict(pairs)), "PARTIAL_RETRIEVAL", "duplicate_query_key")
    q = dict(pairs)
    if purpose == "search":
        check(u == config.search, "PARTIAL_RETRIEVAL", "search_expansion_denied")
        return u, None
    check(purpose == "identity" and p.path == origin.path + "/applicationDetails.do",
          "PARTIAL_RETRIEVAL", "route_denied")
    check(set(q) == {"keyVal", "activeTab"} and q["activeTab"] in {"summary", "details"}
          and bool(re.fullmatch(r"[A-Za-z0-9]{1,40}", q["keyVal"])),
          "PARTIAL_RETRIEVAL", "detail_tab_or_query_denied")
    # 'details' is only a retained link alias (Stockport). Never a GET capability.
    canonical = config.base + "/applicationDetails.do?" + urlencode({"activeTab": "summary", "keyVal": q["keyVal"]})
    return canonical, q["keyVal"]


@dataclass(frozen=True)
class Exchange:
    operation: str
    body_chunks: tuple[bytes, ...]
    status: int = 200
    failure: str | None = None
    redirect: str | None = None
    attachment: bool = False
    content_encoding: str = "identity"


class FixtureTape:
    """Sealed offline transport. No injectable callback or live implementation."""
    def __init__(self, exchanges):
        self.exchanges = tuple(exchanges)
        if not all(type(e) is Exchange for e in self.exchanges):
            raise ValueError("fixture exchange required")
        self.index, self.closed = 0, False

    def take(self, operation):
        check(not self.closed and self.index < len(self.exchanges), "PARTIAL_RETRIEVAL", "missing_exchange")
        e = self.exchanges[self.index]
        self.index += 1
        check(e.operation == operation, "PARTIAL_RETRIEVAL", "unexpected_operation")
        return e

    def close(self):
        self.closed = True


class Boundary:
    def __init__(self, tape, limits):
        check(type(tape) is FixtureTape, "PARTIAL_RETRIEVAL", "offline_transport_only")
        self.tape, self.limits = tape, limits
        self.started = time.monotonic()
        self.requests = self.redirects = self.retries = self.received = 0

    def deadline(self):
        check(time.monotonic()-self.started <= self.limits.seconds, "TIMEOUT", "worker_deadline")

    def request(self, operation):
        self.deadline()
        check(self.requests < self.limits.requests, "BUDGET_EXCEEDED", "request_budget")
        self.requests += 1  # before transport access, including failed/partial attempts
        e = self.tape.take(operation)
        body, response_bytes = bytearray(), 0
        try:
            for chunk in e.body_chunks:
                self.deadline()
                check(type(chunk) is bytes, "PARTIAL_RETRIEVAL", "invalid_chunk")
                response_bytes += len(chunk)
                self.received += len(chunk)  # count even the chunk that crosses a ceiling
                check(response_bytes <= self.limits.response_bytes and self.received <= self.limits.total_bytes,
                      "BUDGET_EXCEEDED", "body_budget")
                body.extend(chunk)
            if e.redirect is not None or 300 <= e.status < 400:
                self.redirects += 1
                raise Failure("PARTIAL_RETRIEVAL", "redirect_denied")
            check(not e.attachment, "PARTIAL_RETRIEVAL", "attachment_denied")
            check(e.content_encoding == "identity", "PARTIAL_RETRIEVAL", "compressed_body_not_admitted")
            if e.failure:
                raise Failure("TIMEOUT" if e.failure == "timeout" else "PARTIAL_RETRIEVAL", "transport_failure")
            check(e.status == 200, "SOURCE_UNAVAILABLE", "http_failure")
            return bytes(body)
        finally:
            body.clear()


def decode_fixture(body):
    """Synthetic XML-shaped HTML protocol. NEVER claim actual Idox selectors."""
    try:
        check(b"<!" not in body, "SOURCE_LAYOUT_UNRECOGNISED", "declarations_denied")
        root = ET.fromstring(body)
        check(root.tag == "fixture-results" and set(root.attrib) == {"version", "page", "total", "terminal", "zero"}
              and root.attrib["version"] == VERSION, "SOURCE_LAYOUT_UNRECOGNISED", "result_marker_missing")
        check(root.attrib["terminal"] in {"true", "false"} and root.attrib["zero"] in {"true", "false"},
              "SOURCE_LAYOUT_UNRECOGNISED", "invalid_markers")
        page, total = int(root.attrib["page"]), int(root.attrib["total"])
        check(1 <= page <= 2 and 0 <= total <= 100, "BUDGET_EXCEEDED", "declared_count_budget")
        entries, continuations = [], []
        for child in root:
            if child.tag == "candidate" and set(child.attrib) == {"reference", "href"} and len(child) == 0:
                entries.append(dict(child.attrib))
            elif child.tag == "next" and set(child.attrib) == {"page"} and len(child) == 0:
                continuations.append(int(child.attrib["page"]))
            else:
                raise Failure("SOURCE_LAYOUT_UNRECOGNISED", "unknown_fixture_element")
        return page, total, root.attrib["terminal"] == "true", root.attrib["zero"] == "true", entries, continuations
    except (ET.ParseError, ValueError, TypeError):
        raise Failure("SOURCE_LAYOUT_UNRECOGNISED", "malformed_fixture_page") from None


def raw_candidate(config, candidate, w, boundary, observed_at, code_sha):
    missing = FieldEvidence(FieldState.MISSING, None, "not_requested")
    return RawEnvelope(DA0_VERSION, config.council + "-idox", config.council,
        candidate["reference"], candidate["reference"], candidate["source_key"], candidate["source_url"],
        observed_at, {"reference": FieldEvidence(FieldState.VALUE, candidate["reference"], "synthetic-result-list")},
        {"adapter": VERSION, "parser": "synthetic-protocol-v1", "config": CONFIG_VERSION,
         "source_schema": "UNPROVED_LIVE", "code": code_sha},
        {k: missing for k in ("record_created_at", "record_updated_at", "dataset_updated_at")},
        True, boundary.requests, boundary.received, time.monotonic()-boundary.started, "WITHIN_BOUND",
        capability=Capability.NEW.value, source_type="SYNTHETIC_RESULT_LIST", authority_class="FIXTURE_EXPECTATION",
        discovery_window=w)


def collect(council, start, end, basis, tape, *, limits=Limits(),
            observed_at="2026-10-01T00:00:00Z", code_sha="0"*40):
    """All outputs are offline fixture expectations; no checkpoint is committed."""
    config = CONFIGS[council]
    w = window(start, end, basis, config)
    check(bool(re.fullmatch(r"[0-9a-f]{40}", code_sha)), "PARTIAL_RETRIEVAL", "code_identity")
    try:
        stamp = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        check(stamp.utcoffset() is not None and len(observed_at) <= 32, "PARTIAL_RETRIEVAL", "observation_timestamp")
    except (ValueError, TypeError, AttributeError):
        raise Failure("PARTIAL_RETRIEVAL", "observation_timestamp") from None
    boundary = Boundary(tape, limits)
    candidates, key_refs, ref_keys, seen_pages = {}, {}, {}, set()
    pages_attempted = pages_accepted = 0
    terminal = False
    state, reason = "PARTIAL_RETRIEVAL", None
    try:
        admit(config, config.search, "search")
        # Logical fixture operations ONLY: HTTP method/action/server state unresolved.
        check(boundary.request("FORM") == b"OFFLINE_FORM_V1", "SOURCE_LAYOUT_UNRECOGNISED", "fixture_form_marker")
        expected_page, total_expected, operation = 1, None, "SUBMIT"
        while True:
            check(pages_attempted < limits.pages, "BUDGET_EXCEEDED", "page_budget")
            pages_attempted += 1
            body = boundary.request(operation)
            fingerprint = digest(body.hex())
            check(fingerprint not in seen_pages, "PARTIAL_RETRIEVAL", "repeated_page")
            seen_pages.add(fingerprint)
            page, total, terminal_flag, zero, entries, next_pages = decode_fixture(body)
            check(page == expected_page, "PARTIAL_RETRIEVAL", "page_progression")
            check(total_expected is None or total == total_expected, "PARTIAL_RETRIEVAL", "count_drift")
            total_expected = total
            check(total <= limits.candidates, "BUDGET_EXCEEDED", "candidate_budget")
            check((total == 0) == zero and (not zero or (not entries and page == 1 and terminal_flag)),
                  "SOURCE_LAYOUT_UNRECOGNISED", "zero_not_proved")
            page_keys = set()
            for entry in entries:
                url, key = admit(config, entry["href"], "identity")
                ref = entry["reference"]
                check(not ref or bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/_.-]{0,79}", ref)),
                      "AMBIGUOUS_IDENTITY", "reference_shape")
                check(key not in key_refs or key_refs[key] == ref, "AMBIGUOUS_IDENTITY", "key_reference_conflict")
                check(not ref or ref not in ref_keys or ref_keys[ref] == key, "AMBIGUOUS_IDENTITY", "reference_key_conflict")
                check(key not in candidates or key in page_keys, "PARTIAL_RETRIEVAL", "overlapping_page_membership")
                key_refs[key] = ref
                if ref:
                    ref_keys[ref] = key
                identity = council + ":" + ref if ref else None
                candidates[key] = {"identity": identity, "reference": ref or None, "source_key": key,
                                   "source_url": url, "qualification": "DISPLAYED_REFERENCE" if ref else "SELECTIVE_DETAIL_REQUIRED"}
                page_keys.add(key)
                check(len(candidates) <= limits.candidates, "BUDGET_EXCEEDED", "candidate_budget")
            check(bool(entries) or zero, "SOURCE_LAYOUT_UNRECOGNISED", "empty_nonzero_page")
            pages_accepted += 1
            if terminal_flag:
                check(not next_pages and len(candidates) == total, "PARTIAL_RETRIEVAL", "terminal_count_mismatch")
                terminal = True
                state = "COMPLETE_ZERO_RESULTS" if zero else "COMPLETE"
                break
            check(len(next_pages) == 1 and next_pages[0] == page+1 and len(candidates) < total,
                  "PARTIAL_RETRIEVAL", "continuation_not_proved")
            expected_page = next_pages[0]
            operation = "NEXT:" + str(expected_page)
        boundary.deadline()
        check(tape.index == len(tape.exchanges), "PARTIAL_RETRIEVAL", "unconsumed_fixture_exchange")
    except Failure as exc:
        state, reason = exc.state, exc.reason
        candidates.clear()
        terminal = False
    finally:
        tape.close()
    complete = state in {"COMPLETE", "COMPLETE_ZERO_RESULTS"}
    ordered = sorted(candidates.values(), key=lambda x: (x["reference"] or "", x["source_key"]))
    envelopes = [asdict(raw_candidate(config, c, w, boundary, observed_at, code_sha)) for c in ordered if c["identity"]] if complete else []
    result = dict(manifest_version=VERSION, council=council, date_basis=basis, window_start=start, window_end=end,
        config_version=CONFIG_VERSION, adapter_version=VERSION, source_mode="SYNTHETIC_OFFLINE",
        code_sha=code_sha, observed_at=observed_at, completion_state=state, failure_reason=reason,
        pages_attempted=pages_attempted, pages_accepted=pages_accepted, terminal_proof=terminal,
        requests=boundary.requests, redirects=boundary.redirects, retries=boundary.retries,
        received_bytes=boundary.received, elapsed_seconds=round(time.monotonic()-boundary.started, 6),
        candidate_count=len(ordered), unique_application_identities=sum(bool(c["identity"]) for c in ordered),
        candidates=ordered, raw_evidence=envelopes, cleanup_verified=tape.closed,
        checkpoint_eligible=False, consistency="SYNTHETIC_TAPE_ONLY", live_ready=False)
    validate_result(result)
    return result


RESULT_KEYS = frozenset("manifest_version council date_basis window_start window_end config_version adapter_version source_mode code_sha observed_at completion_state failure_reason pages_attempted pages_accepted terminal_proof requests redirects retries received_bytes elapsed_seconds candidate_count unique_application_identities candidates raw_evidence cleanup_verified checkpoint_eligible consistency live_ready".split())


def validate_result(r):
    check(type(r) is dict and set(r) == RESULT_KEYS and r["manifest_version"] == VERSION,
          "PARTIAL_RETRIEVAL", "audit_schema")
    check(r["source_mode"] == "SYNTHETIC_OFFLINE" and r["live_ready"] is False
          and r["checkpoint_eligible"] is False, "PARTIAL_RETRIEVAL", "operational_claim_denied")
    check(r["council"] in CONFIGS and r["adapter_version"] == VERSION and r["config_version"] == CONFIG_VERSION
          and r["consistency"] == "SYNTHETIC_TAPE_ONLY" and r["cleanup_verified"] is True,
          "PARTIAL_RETRIEVAL", "audit_provenance")
    window(r["window_start"], r["window_end"], r["date_basis"], CONFIGS[r["council"]])
    check(isinstance(r["code_sha"], str) and bool(re.fullmatch(r"[0-9a-f]{40}", r["code_sha"])),
          "PARTIAL_RETRIEVAL", "audit_code_identity")
    for name in ("pages_attempted", "pages_accepted", "requests", "redirects", "retries", "received_bytes",
                 "candidate_count", "unique_application_identities"):
        check(type(r[name]) is int and r[name] >= 0, "PARTIAL_RETRIEVAL", "audit_counter")
    check(r["pages_accepted"] <= r["pages_attempted"] <= 2 and r["requests"] <= 6
          and r["redirects"] <= r["requests"] and r["retries"] == 0
          and type(r["elapsed_seconds"]) in (int, float) and math.isfinite(r["elapsed_seconds"])
          and r["elapsed_seconds"] >= 0, "PARTIAL_RETRIEVAL", "audit_counter")
    check(r["completion_state"] in STATES, "PARTIAL_RETRIEVAL", "outcome_schema")
    complete = r["completion_state"] in {"COMPLETE", "COMPLETE_ZERO_RESULTS"}
    check(r["candidate_count"] == len(r["candidates"])
          and r["unique_application_identities"] == len(r["raw_evidence"]), "PARTIAL_RETRIEVAL", "audit_count")
    check((complete and r["terminal_proof"] and r["failure_reason"] is None)
          or (not complete and not r["candidates"] and not r["raw_evidence"] and not r["terminal_proof"]
              and isinstance(r["failure_reason"], str)), "PARTIAL_RETRIEVAL", "partial_output_denied")
    keys, identities = set(), set()
    for c in r["candidates"]:
        check(set(c) == {"identity", "reference", "source_key", "source_url", "qualification"},
              "PARTIAL_RETRIEVAL", "candidate_schema")
        url, key = admit(CONFIGS[r["council"]], c["source_url"], "identity")
        check(url == c["source_url"] and key == c["source_key"] and key not in keys,
              "PARTIAL_RETRIEVAL", "candidate_key")
        keys.add(key)
        ref = c["reference"]
        if ref is not None:
            check(isinstance(ref, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/_.-]{0,79}", ref))
                  and c["identity"] == r["council"] + ":" + ref and c["identity"] not in identities
                  and c["qualification"] == "DISPLAYED_REFERENCE", "PARTIAL_RETRIEVAL", "candidate_reference")
            identities.add(c["identity"])
        else:
            check(c["identity"] is None and c["qualification"] == "SELECTIVE_DETAIL_REQUIRED",
                  "PARTIAL_RETRIEVAL", "unknown_identity")
    check(len(identities) == r["unique_application_identities"], "PARTIAL_RETRIEVAL", "identity_count")
    envelope_refs = set()
    for e in r["raw_evidence"]:
        check(e["council"] == r["council"] and e["application_reference_raw"] not in envelope_refs
              and e["council"] + ":" + e["application_reference_raw"] in identities
              and e["capability"] == Capability.NEW.value and e["authority_class"] == "FIXTURE_EXPECTATION"
              and e["source_type"] == "SYNTHETIC_RESULT_LIST", "PARTIAL_RETRIEVAL", "envelope_identity")
        envelope_refs.add(e["application_reference_raw"])
        e = dict(e)
        e["fields"] = {k: FieldEvidence(FieldState(v["state"]), v["value"], v["locator"], v["meaning"]) for k, v in e["fields"].items()}
        e["source_timestamps"] = {k: FieldEvidence(FieldState(v["state"]), v["value"], v["locator"], v["meaning"]) for k, v in e["source_timestamps"].items()}
        RawEnvelope(**e)
    return r


def encode_result(result):
    validate_result(result)
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > 65_536:
        failure = dict(result, completion_state="BUDGET_EXCEEDED", failure_reason="artifact_budget",
                       terminal_proof=False, candidate_count=0, unique_application_identities=0,
                       candidates=[], raw_evidence=[])
        validate_result(failure)
        return json.dumps(failure, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return encoded
