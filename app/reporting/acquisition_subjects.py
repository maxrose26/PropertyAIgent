"""Stage 2.5B G1 - strict acquisition-subject identity (specifications/025).

IDENTITY INFRASTRUCTURE ONLY. Pure and deterministic: no database, no network, no model. It does not emit
any acquisition subject, group families, change buyer matching, change monitoring, or alter any existing
opportunity id. Its jobs are:

  1. parse_opportunity_id: ONE strict parser for the five existing opportunity-id shapes and the grammar
     reserved for future kinds. Unknown kinds, malformed ids, missing/extra segments and non-canonical ids
     RAISE. Nothing ever defaults to WHOLE_SITE.
  2. legacy anchor compatibility: reproduce, byte-for-byte, the (subject_type, anchor_id, scope_key) the
     previous resolver returned for every existing id - including its truncation of a phase code that
     contains an extra ":". Existing history/current-state rows are keyed by those anchors, so G1 must not
     silently "repair" them (any repair needs its own migration decision).
  3. the delimiter-safe grammar, anchor keys and length caps for NEW kinds (spec 025 "Identity"), which are
     recognised here but NOT emit-capable: EMIT_CAPABLE_NEW_KINDS is empty (the spec's emission gate), so the
     resolver rejects them until every id consumer has been migrated and G1A has landed.

Strategic allocations keep their single canonical identity ``strategic_land:allocation:{id}``; nothing here
duplicates an allocation per linked planning site (spec 025: one canonical strategic family per allocation).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, unquote

# Same literals as app.policy.buyer_matching.PLANNING_DELIVERY / STRATEGIC_LAND (asserted equal by a test);
# kept literal so this module stays import-light and cycle-free.
PLANNING_DELIVERY = "planning_delivery"
STRATEGIC_LAND = "strategic_land"

WHOLE_SITE = "WHOLE_SITE"
WHOLE_ALLOCATION = "WHOLE_ALLOCATION"

KIND_PHASE = "phase"
KIND_ALLOCATION = "allocation"
# One planning lifecycle slot per site (opportunity_universe's own design): these share one WHOLE_SITE subject.
LIFECYCLE_KINDS = frozenset({"site", "recent_permission", "long_pending_application"})
# New kind segment -> acquisition-subject taxonomy name (spec 025). Recognised, NOT emit-capable.
NEW_KINDS = {"component": "MIXED_COMPONENT", "affordable_package": "AFFORDABLE_PACKAGE", "residual": "RESIDUAL_OPPORTUNITY"}   # residual: V8-B derived, NEVER persisted/emitted
NEW_KIND_ANCHOR_PREFIX = {"component": "component~", "affordable_package": "affordable~", "residual": "residual~"}
# The spec 025 emission gate: no new kind may be emitted until every id consumer is migrated and G1A has
# landed. Deliberately empty in G1.
EMIT_CAPABLE_NEW_KINDS: frozenset = frozenset()

MAX_OPPORTUNITY_ID_LENGTH = 200       # OpportunityMonitoringState.opportunity_id / AgentEvaluationHistory.opportunity_id
MAX_KIND_LENGTH = 50                  # opportunity_kind columns
MAX_ANCHOR_SCOPE_KEY_LENGTH = 100     # AcquisitionSubjectAnchor.scope_key String(100), reserved prefix included
MAX_ANCHOR_ID = 2**31 - 1             # AcquisitionSubjectAnchor.anchor_id Integer

_CANONICAL_ID_RE = re.compile(r"^[1-9][0-9]*$", re.ASCII)
_SAFE_SCOPE_KEY_RE = re.compile(r"^[A-Za-z0-9._~%-]+$", re.ASCII)
_UNRESERVED = "-._~"


class SubjectIdentityError(ValueError):
    """Base class: an identity could not be established. Callers must treat this as 'no subject' - never as a default."""


class UnknownOpportunityKind(SubjectIdentityError):
    pass


class MalformedOpportunityId(SubjectIdentityError):
    pass


class IdentityTooLong(SubjectIdentityError):
    pass


class NewKindNotEmitCapable(SubjectIdentityError):
    """A recognised future kind that the spec 025 emission gate has not opened."""


@dataclass(frozen=True)
class ParsedOpportunityId:
    domain: str                 # PLANNING_DELIVERY | STRATEGIC_LAND
    kind: str                   # the kind segment, verbatim
    anchor_id: int              # Site.id (planning_delivery) or LocalPlanSite.id (strategic_land)
    scope_key: str | None       # phase: the FULL code verbatim; new kinds: the delimiter-safe key; else None
    legacy_scope_key: str | None  # phase only: today's truncated anchor text (up to the next ':')
    is_legacy: bool             # one of the five existing shapes


def _canonical_anchor_id(text: str, opportunity_id: str) -> int:
    if not _CANONICAL_ID_RE.match(text):
        raise MalformedOpportunityId(f"anchor id {text!r} is not a canonical positive integer in {opportunity_id!r}")
    value = int(text)
    if value > MAX_ANCHOR_ID:
        raise MalformedOpportunityId(f"anchor id {text!r} exceeds the anchor_id column range")
    return value


def encode_scope_key(raw: str) -> str:
    """Deterministic, reversible, delimiter-safe encoding of free text (RFC 3986 percent-encoding, UTF-8,
    uppercase hex). Never contains ':', whitespace or '/'."""
    if not isinstance(raw, str) or not raw:
        raise MalformedOpportunityId("scope text must be a non-empty string")
    return quote(raw.encode("utf-8"), safe=_UNRESERVED)


def decode_scope_key(key: str) -> str:
    """Inverse of encode_scope_key; raises unless ``key`` is the CANONICAL encoding of some text."""
    if not isinstance(key, str) or not _SAFE_SCOPE_KEY_RE.match(key):
        raise MalformedOpportunityId(f"scope key {key!r} is not delimiter-safe")
    try:
        raw = unquote(key, errors="strict")
    except UnicodeDecodeError as exc:
        raise MalformedOpportunityId(f"scope key {key!r} is not valid percent-encoded UTF-8") from exc
    if not raw or encode_scope_key(raw) != key:
        raise MalformedOpportunityId(f"scope key {key!r} is not in canonical encoded form")
    return raw


def new_kind_anchor_scope_key(kind: str, scope_key: str) -> str:
    """The namespaced AcquisitionSubjectAnchor.scope_key for a new kind; the reserved prefix counts toward the cap."""
    if kind not in NEW_KINDS:
        raise UnknownOpportunityKind(f"{kind!r} is not a recognised new subject kind")
    decode_scope_key(scope_key)  # validates delimiter-safety and canonical form
    anchor_key = NEW_KIND_ANCHOR_PREFIX[kind] + scope_key
    if len(anchor_key) > MAX_ANCHOR_SCOPE_KEY_LENGTH:
        raise IdentityTooLong(f"anchor scope key would be {len(anchor_key)} characters (cap {MAX_ANCHOR_SCOPE_KEY_LENGTH})")
    return anchor_key


def build_new_kind_opportunity_id(kind: str, site_id: int, raw_scope: str) -> str:
    """Identity construction for a FUTURE kind (grammar + caps only). Emitting it is a later gate."""
    if kind not in NEW_KINDS:
        raise UnknownOpportunityKind(f"{kind!r} is not a recognised new subject kind")
    if isinstance(site_id, bool) or not isinstance(site_id, int) or not (1 <= site_id <= MAX_ANCHOR_ID):
        raise MalformedOpportunityId(f"site id {site_id!r} is not a valid anchor id")
    key = encode_scope_key(raw_scope)
    new_kind_anchor_scope_key(kind, key)  # enforces the 100-character anchor cap
    opportunity_id = f"{PLANNING_DELIVERY}:{kind}:{site_id}:{key}"
    if len(opportunity_id) > MAX_OPPORTUNITY_ID_LENGTH or len(kind) > MAX_KIND_LENGTH:
        raise IdentityTooLong(f"opportunity id would be {len(opportunity_id)} characters (cap {MAX_OPPORTUNITY_ID_LENGTH})")
    return opportunity_id


def parse_opportunity_id(opportunity_id: str) -> ParsedOpportunityId:
    """Strictly parse an opportunity id. Raises SubjectIdentityError for anything not recognised."""
    if not isinstance(opportunity_id, str) or not opportunity_id:
        raise MalformedOpportunityId("opportunity id must be a non-empty string")
    parts = opportunity_id.split(":")
    if len(parts) < 3:
        raise MalformedOpportunityId(f"opportunity id {opportunity_id!r} has too few segments")
    domain, kind = parts[0], parts[1]

    if domain == STRATEGIC_LAND:
        if kind != KIND_ALLOCATION:
            raise UnknownOpportunityKind(f"unknown strategic_land kind {kind!r}")
        if len(parts) != 3:
            raise MalformedOpportunityId(f"strategic allocation id {opportunity_id!r} must have exactly 3 segments")
        return ParsedOpportunityId(STRATEGIC_LAND, KIND_ALLOCATION, _canonical_anchor_id(parts[2], opportunity_id), None, None, True)

    if domain != PLANNING_DELIVERY:
        raise UnknownOpportunityKind(f"unknown opportunity domain {domain!r}")

    if kind in LIFECYCLE_KINDS:
        if len(parts) != 3:
            raise MalformedOpportunityId(f"{kind} id {opportunity_id!r} must have exactly 3 segments")
        return ParsedOpportunityId(PLANNING_DELIVERY, kind, _canonical_anchor_id(parts[2], opportunity_id), None, None, True)

    if kind == KIND_PHASE:
        # Legacy phase ids carry FREE TEXT after the third ':' (it may itself contain ':', spaces or '/').
        head = opportunity_id.split(":", 3)
        if len(head) != 4 or not head[3]:
            raise MalformedOpportunityId(f"phase id {opportunity_id!r} has no phase code")
        # head[3] is the full code verbatim; today's resolver used parts[3], i.e. the text up to the next ':'.
        return ParsedOpportunityId(PLANNING_DELIVERY, KIND_PHASE, _canonical_anchor_id(head[2], opportunity_id),
                                   head[3], parts[3], True)

    if kind in NEW_KINDS:
        if len(parts) != 4:
            raise MalformedOpportunityId(f"{kind} id {opportunity_id!r} must have exactly 4 segments")
        anchor_id = _canonical_anchor_id(parts[2], opportunity_id)
        key = parts[3]
        decode_scope_key(key)
        new_kind_anchor_scope_key(kind, key)  # raises IdentityTooLong
        if len(opportunity_id) > MAX_OPPORTUNITY_ID_LENGTH or len(kind) > MAX_KIND_LENGTH:
            raise IdentityTooLong(f"opportunity id is {len(opportunity_id)} characters (cap {MAX_OPPORTUNITY_ID_LENGTH})")
        return ParsedOpportunityId(PLANNING_DELIVERY, kind, anchor_id, key, None, False)

    raise UnknownOpportunityKind(f"unknown planning_delivery kind {kind!r}")


def resolve_anchor_key(parsed: ParsedOpportunityId, opportunity_type: str) -> tuple[str, int, str]:
    """(subject_type, anchor_id, scope_key) - identical to the previous resolver for every existing id.

    The opportunity_type must agree with the id's own domain (a mismatch raises: it used to silently anchor a
    strategic id onto a planning Site.id). A recognised new kind raises NewKindNotEmitCapable until the spec 025
    emission gate opens; it can never resolve to its parent's WHOLE_SITE anchor."""
    if parsed.domain != opportunity_type:
        raise MalformedOpportunityId(f"opportunity type {opportunity_type!r} does not match id domain {parsed.domain!r}")
    if parsed.domain == STRATEGIC_LAND:
        return (STRATEGIC_LAND, parsed.anchor_id, WHOLE_ALLOCATION)
    if parsed.kind == KIND_PHASE:
        return (PLANNING_DELIVERY, parsed.anchor_id, parsed.legacy_scope_key)  # today's behaviour, pinned
    if parsed.kind in LIFECYCLE_KINDS:
        return (PLANNING_DELIVERY, parsed.anchor_id, WHOLE_SITE)
    if parsed.kind in NEW_KINDS:
        if parsed.kind not in EMIT_CAPABLE_NEW_KINDS:
            raise NewKindNotEmitCapable(f"{parsed.kind!r} subjects are not emit-capable (spec 025 emission gate)")
        return (PLANNING_DELIVERY, parsed.anchor_id, new_kind_anchor_scope_key(parsed.kind, parsed.scope_key))
    raise UnknownOpportunityKind(f"unknown kind {parsed.kind!r}")  # unreachable; never defaults to WHOLE_SITE


def family_identity(parsed: ParsedOpportunityId) -> tuple[str, int]:
    """The identity of the FAMILY an id belongs to (spec 025): a planning family is one Site.id; a strategic
    family is one allocation, canonical and never duplicated per linked site. Identity only - no grouping."""
    return (parsed.domain, parsed.anchor_id)
