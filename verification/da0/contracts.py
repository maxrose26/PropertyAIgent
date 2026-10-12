"""DA0 executable contract examples. Pure, offline; never an ingestion service.

These helpers validate fixtures and illustrate semantics for later implementation.
They do not admit production execution or persist accepted planning facts.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import ipaddress
import json
import math
from urllib.parse import urlsplit


VERSION = "da0-contract-v1"


class Capability(str, Enum):
    STATUS = "KNOWN_REFERENCE_STATUS"
    DECISION = "KNOWN_REFERENCE_DECISION"
    DECISION_DATE = "KNOWN_REFERENCE_DECISION_DATE"
    NEW = "NEW_APPLICATION_DISCOVERY"
    CHANGE = "CHANGE_DISCOVERY"
    SNAPSHOT = "BULK_SNAPSHOT"
    RELATED = "RELATED_APPLICATION_DISCOVERY"
    DOCUMENT_METADATA = "DOCUMENT_METADATA"
    DOCUMENT = "DOCUMENT_RETRIEVAL"
    ALLOCATION = "ALLOCATION_DATA"


class OperationalState(str, Enum):
    PROPOSED = "PROPOSED"
    OFFLINE_PROVED = "OFFLINE_PROVED"
    LIVE_CANARY_PROVED = "LIVE_CANARY_PROVED"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    UNSUPPORTED = "UNSUPPORTED"
    DEFERRED = "DEFERRED"


class FieldState(str, Enum):
    VALUE = "PRESENT_VALUE"
    BLANK = "PRESENT_BLANK"
    MISSING = "NOT_PRESENT"
    CONFLICT = "CONFLICTING"
    UNPARSEABLE = "UNPARSEABLE"


GATES = frozenset({"IDENTITY", "AUTHORITY", "COMPLETENESS", "FRESHNESS_LATENCY",
                   "RIGHTS", "RESOURCE_BOUNDING", "SCHEMA_STABILITY", "PROVENANCE"})
EVENTS = frozenset({"APPLICATION_DISCOVERED", "APPLICATION_SOURCE_CHANGED", "STATUS_CHANGED",
                    "DECISION_CHANGED", "DECISION_DATE_CHANGED", "SOURCE_RECORD_REMOVED",
                    "RELATIONSHIP_DISCOVERED", "SOURCE_CONFLICT_DETECTED"})
STATUS_FIELDS = frozenset({"reference", "source_status_raw", "source_decision_raw", "source_decision_date"})


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def validate_url(url):
    p = urlsplit(url)
    require(p.scheme == "https" and bool(p.hostname), "HTTPS origin required")
    require(not p.username and not p.password and not p.fragment, "unsafe URL state")
    require(p.port in (None, 443), "unapproved port")
    host = p.hostname.lower().rstrip(".")
    require(host not in {"localhost", "metadata.google.internal"} and not host.endswith(".localhost"), "local host denied")
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        require(addr.is_global, "non-public destination denied")
    return url


def validate_registry(record):
    required = {"manifest_version", "source_id", "council", "fact_domain", "source_name", "source_type",
                "platform_family", "publisher", "authority_class", "priority", "adapter_type", "admission",
                "capabilities", "freshness", "rights", "operational_state", "versions", "last_capability_review",
                "limitations", "research_source_id", "execution_authority"}
    require(set(record) == required, "registry closed schema")
    require(record["manifest_version"] == VERSION, "registry version")
    require(all(isinstance(record[k], str) and record[k] for k in ("source_id", "council", "fact_domain")), "registry identity")
    require(record["operational_state"] in {x.value for x in OperationalState}, "operational state")
    require(set(record["capabilities"]) == {x.value for x in Capability}, "explicit capability declarations required")
    for cap in record["capabilities"].values():
        require(set(cap) == {"declaration", "gates", "evidence_ids"}, "capability schema")
        require(cap["declaration"] in {"UNPROVED", "UNSUPPORTED", "SUPPORTED"}, "capability declaration")
        require(set(cap["gates"]) == GATES, "all eligibility gates required")
        require(set(cap["gates"].values()) <= {"PASS", "FAIL", "UNKNOWN"}, "gate state")
        if cap["declaration"] == "SUPPORTED":
            require(all(v == "PASS" for v in cap["gates"].values()) and bool(cap["evidence_ids"]), "unsupported support claim")
    require(set(record["admission"]) == {"exact_urls", "redirects_followed", "dns_validation_required"}, "admission schema")
    require(bool(record["admission"]["exact_urls"]), "no admitted source")
    for url in record["admission"]["exact_urls"]:
        validate_url(url)
    require(record["admission"]["redirects_followed"] == 0, "research fixture redirect policy")
    require(record["admission"]["dns_validation_required"] is True, "resolved destination check required")
    require(record["execution_authority"] is None, "DA0 cannot grant execution authority")
    require(record["operational_state"] in {"PROPOSED", "DEFERRED", "UNSUPPORTED"}, "DA0 fixtures remain non-operational")
    return record


def eligible(record, council, domain, capability):
    validate_registry(record)
    c = record["capabilities"].get(capability)
    return bool(record["council"] == council and record["fact_domain"] == domain and c
                and c["declaration"] == "SUPPORTED" and all(v == "PASS" for v in c["gates"].values()))


def admit_fixture_url(record, url):
    validate_registry(record)
    validate_url(url)
    require(url in record["admission"]["exact_urls"], "exact URL admission")


@dataclass(frozen=True)
class FieldEvidence:
    state: FieldState
    value: str | None
    locator: str
    meaning: str = "SOURCE_LITERAL"

    def __post_init__(self):
        require(isinstance(self.state, FieldState), "field state")
        require(self.meaning in {"SOURCE_LITERAL", "DERIVED_QUALIFIED"}, "field meaning")
        require(isinstance(self.locator, str) and bool(self.locator), "field provenance")
        if self.state == FieldState.VALUE:
            require(isinstance(self.value, str) and bool(self.value.strip()), "value evidence")
        else:
            require(self.value is None, "non-value states cannot carry an accepted value")


@dataclass(frozen=True)
class RawEnvelope:
    manifest_version: str
    source_id: str
    council: str
    application_reference_raw: str
    application_reference_canonical: str
    source_record_id: str | None
    source_url: str
    retrieved_at: str
    fields: dict[str, FieldEvidence]
    versions: dict[str, str]
    source_timestamps: dict[str, FieldEvidence]
    complete_for_claim: bool
    requests: int
    received_bytes: int
    elapsed_seconds: float
    budget_outcome: str
    capability: str = Capability.STATUS.value
    provider: str = "council"
    source_type: str = "DIRECT_SUMMARY"
    authority_class: str = "PRIMARY_CLAIM_SPECIFIC"
    run_id: str = "offline-fixture"
    discovery_window: dict[str, str] | None = None

    def __post_init__(self):
        require(self.manifest_version == VERSION, "envelope version")
        require(bool(self.source_id and self.council and self.application_reference_raw), "envelope identity")
        require(self.application_reference_raw == self.application_reference_canonical, "no unapproved reference normalisation")
        validate_url(self.source_url)
        require(self.capability in {Capability.STATUS.value, Capability.NEW.value}, "unsupported offline projection")
        if self.capability == Capability.NEW.value:
            from datetime import date
            w = self.discovery_window
            require(isinstance(w, dict) and set(w) == {"basis", "start", "end"}, "discovery window provenance")
            require(w["basis"] in {"RECEIVED", "VALIDATED"}, "discovery date basis")
            require(date.fromisoformat(w["start"]) <= date.fromisoformat(w["end"]), "discovery window order")
            require(set(self.fields) == {"reference"}, "identity-only discovery projection")
            ref = self.fields["reference"]
            require(isinstance(ref, FieldEvidence) and ref.state == FieldState.VALUE
                    and ref.meaning == "SOURCE_LITERAL" and ref.value == self.application_reference_raw,
                    "displayed discovery reference required")
        else:
            require(self.discovery_window is None, "status cannot claim discovery window")
            require(set(self.fields) <= STATUS_FIELDS, "unauthorised status projection")
        require(all(isinstance(x, FieldEvidence) for x in self.fields.values()), "qualified fields required")
        require(set(self.versions) == {"adapter", "parser", "config", "source_schema", "code"}
                and all(self.versions.values()), "version provenance")
        require(set(self.source_timestamps) == {"record_created_at", "record_updated_at", "dataset_updated_at"}
                and all(isinstance(x, FieldEvidence) for x in self.source_timestamps.values()), "timestamp meaning/states required")
        require(type(self.requests) is int and type(self.received_bytes) is int
                and self.requests >= 0 and self.received_bytes >= 0
                and math.isfinite(self.elapsed_seconds) and self.elapsed_seconds >= 0, "resource accounting")


def status_claim_complete(envelope, authorised_reference):
    f = envelope.fields
    return bool(envelope.capability == Capability.STATUS.value and envelope.complete_for_claim and envelope.budget_outcome == "WITHIN_BOUND"
                and envelope.application_reference_canonical == authorised_reference
                and all(k in f and f[k].state == FieldState.VALUE and f[k].meaning == "SOURCE_LITERAL"
                        for k in ("reference", "source_status_raw"))
                and f["reference"].value == authorised_reference
                and all(x.state not in {FieldState.CONFLICT, FieldState.UNPARSEABLE} for x in f.values()))


def compare_fact(left_identity, left, right_identity, right):
    """Conservative comparison only; no automatic production acceptance."""
    if left_identity != right_identity:
        return "IDENTITY_MISMATCH"
    if left.meaning != right.meaning:
        return "REVIEW_REQUIRED"
    if any(f.state in {FieldState.MISSING, FieldState.CONFLICT, FieldState.UNPARSEABLE} for f in (left, right)):
        return "REVIEW_REQUIRED"
    return "AGREEMENT" if (left.state, left.value) == (right.state, right.value) else "SOURCE_CONFLICT_DETECTED"


@dataclass(frozen=True)
class Snapshot:
    source_id: str
    scope: str
    schema: str
    parser: str
    config: str
    records: tuple[tuple[str, dict], ...]
    complete: bool
    terminal: bool
    expected_count: int | None
    overflow: bool = False
    consistency: str = "UNPROVED"

    def accepted(self):
        require(self.complete and self.terminal and not self.overflow, "partial snapshot")
        require(bool(self.source_id and self.scope and self.schema and self.parser and self.config), "snapshot provenance")
        require(self.consistency in {"SOURCE_GUARANTEED", "RECONCILED_COMPLETE"}, "snapshot consistency unproved")
        keys = [k for k, _ in self.records]
        require(all(keys) and len(keys) == len(set(keys)), "duplicate/unstable snapshot key")
        require(self.expected_count is None or self.expected_count == len(keys), "count mismatch")
        require(all(set(v) <= STATUS_FIELDS for _, v in self.records), "minimal factual snapshot projection")
        for _, record in self.records:
            for field in record.values():
                require(isinstance(field, dict) and set(field) == {"state", "value"}, "snapshot qualified field")
                state = FieldState(field["state"])
                FieldEvidence(state, field["value"], "snapshot-field")
        return self

    def factual_hash(self):
        self.accepted()
        return digest({"source": self.source_id, "scope": self.scope, "schema": self.schema,
                       "parser": self.parser, "config": self.config, "records": sorted(self.records)})


def snapshot_diff(old, new):
    old.accepted(); new.accepted()
    require((old.source_id, old.scope, old.schema, old.parser, old.config)
            == (new.source_id, new.scope, new.schema, new.parser, new.config), "controlled rebaseline required")
    a, b = dict(old.records), dict(new.records)
    return {"new": sorted(b.keys() - a.keys()), "changed": sorted(k for k in a.keys() & b.keys() if digest(a[k]) != digest(b[k])),
            "removed_candidates_only": sorted(a.keys() - b.keys())}


def event_id(source, key, predecessor, old_hash, new_hash, kind):
    require(kind in EVENTS and bool(source and key and predecessor), "event identity")
    return digest([VERSION, source, key, predecessor, old_hash, new_hash, kind])


def failure_projection(accepted_fact, successful_at, failure_class):
    require(bool(failure_class), "failure classification")
    return {"accepted_fact": accepted_fact, "successful_verification_at": successful_at,
            "failed_attempt": failure_class, "acceptance_authorised": False}


def invoke_offline_operation(record, capability):
    validate_registry(record)
    # DA0 has no transports. Even a synthetic eligibility example cannot launch one.
    return {"outcome": "UNSUPPORTED", "capability": capability, "execution_performed": False}
