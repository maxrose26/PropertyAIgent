"""Stage 2.5B G3a - pure opportunity-family grouping (specifications/025, "Opportunity-family decisions").

Answers ONE question: which EXISTING opportunity subjects belong to the same commercial planning context, and which of
them is the representative (headline) subject for this buyer? It does NOT answer whether one subject is contained in
another (that is G2) and it never creates, infers or removes a subject.

PURE: no database, session, network, Streamlit or feed import. Input is a narrow immutable protocol
(``FamilySubject``) plus two small pure adapters (from an existing opportunity id, from a feed-card mapping); the
caller supplies the COMPLETE relevant subject set (a bounded pool can pick the wrong representative - a hard G3b
requirement, not solved here).

Decisions implemented (Product Owner):
  * a FAMILY is a grouping, NOT an acquisition subject: a phase-only site is a valid family and no whole-site subject
    is ever synthesised;
  * planning family = (planning_delivery, site_id); strategic family = (strategic_land, allocation_id), one per
    allocation id, never duplicated by repeated/linked input; the two are never merged;
  * representative order: buyer fit > count evidence quality > (commercial specificity: only with an evidence-qualified
    G2 relationship - none exists in G3a, so NO parent/child or kind preference is applied) > stable key;
  * nothing is hidden: every other subject is retained as a related subject with an explicit role (also STRONG / also
    POSSIBLE / investigative / insufficient / not suitable);
  * a family is terminally NOT_SUITABLE only if every member is;
  * unit counts are NEVER summed or subtracted - the model carries no unit field at all, so no total or residual can
    exist, and the overlap state states that same-site subjects may overlap;
  * conflicting lifecycle representations (which the universe/feed precedence never produces) FAIL CLOSED;
  * one grouping call must use ONE canonical subject-id representation (opportunity-universe ids OR feed-card ids): a mixture
    FAILS CLOSED (it would double-list one subject under two keys);
  * the final stable-key tie-break is LEXICAL/STRING order (so '...A10' sorts before '...A9'): deterministic only, with no
    commercial meaning.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from app.reporting.acquisition_subjects import (
    KIND_PHASE, LIFECYCLE_KINDS, MAX_ANCHOR_ID, PLANNING_DELIVERY, STRATEGIC_LAND, parse_opportunity_id,
)

# Same literals as app.policy.buyer_matching's classification constants (asserted equal by a test); kept literal so
# this module stays import-light and cycle-free.
STRONG_FIT = "STRONG_FIT"
POSSIBLE_FIT = "POSSIBLE_FIT"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
NOT_SUITABLE = "NOT_SUITABLE"
FITS = (STRONG_FIT, POSSIBLE_FIT, INSUFFICIENT_EVIDENCE, NOT_SUITABLE)

SLOT_LIFECYCLE = "LIFECYCLE"    # the one whole-site lifecycle slot per site (site / recent_permission / long_pending)
SLOT_PHASE = "PHASE"            # a named phase / scope card
SLOT_ALLOCATION = "ALLOCATION"  # a strategic allocation
SLOT_RESIDUAL = "RESIDUAL"      # V8-B: an R1 DERIVED residual subject (never persisted); R2 is context only and is never a subject

ROLE_ALSO_STRONG_FIT = "ALSO_STRONG_FIT"
ROLE_ALSO_POSSIBLE_FIT = "ALSO_POSSIBLE_FIT"
ROLE_INSUFFICIENT_INVESTIGATIVE = "INSUFFICIENT_INVESTIGATIVE"
ROLE_INSUFFICIENT = "INSUFFICIENT"
ROLE_NOT_SUITABLE = "NOT_SUITABLE"

ID_SYSTEM_OPPORTUNITY = "opportunity"   # opportunity-universe ids (planning_delivery:site:61 ...)
ID_SYSTEM_FEED = "feed"                 # feed-card ids (opp-lapse-61 ...)

OVERLAP_SINGLE_SUBJECT = "SINGLE_SUBJECT"
OVERLAP_MAY_OVERLAP = "MAY_OVERLAP_NO_EVIDENCE"
OVERLAP_WARNING = "Related subjects may overlap — do not add unit counts."

_COUNT_PRECISIONS = frozenset({"EXACT", "APPROXIMATE", "RANGE", "UNKNOWN"})


class FamilyInputError(ValueError):
    """The supplied subjects cannot be grouped safely. Callers must treat this as 'no family', never as a default."""


class ConflictingLifecycleRepresentations(FamilyInputError):
    pass


class ConflictingSubjectInput(FamilyInputError):
    pass


class UnsupportedSubject(FamilyInputError):
    pass


class MixedIdentitySystems(FamilyInputError):
    pass


# --- model -----------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class FamilySubject:
    """One EXISTING subject supplied for grouping. Deliberately carries NO unit field (a total/residual cannot exist) and no
    UI field. ``source`` is an opaque pass-through of the caller's own object (feed card, universe record...)."""
    domain: str                      # PLANNING_DELIVERY | STRATEGIC_LAND
    anchor_id: int                   # Site.id | LocalPlanSite.id
    subject_key: str                 # the subject's canonical identity string, unique and stable (the tie-break key)
    slot: str                        # SLOT_LIFECYCLE | SLOT_PHASE | SLOT_ALLOCATION
    fit: str                         # one of FITS
    investigative: bool = False      # BuyerFitAssessment.is_investigative_exception
    count_precision: str | None = None  # CountAssessment.precision, if known
    source: object = field(default=None, compare=False, repr=False)
    id_system: str = ID_SYSTEM_OPPORTUNITY  # which id representation subject_key uses; one per grouping call

    def __post_init__(self):
        if self.domain not in (PLANNING_DELIVERY, STRATEGIC_LAND):
            raise UnsupportedSubject(f"unknown domain {self.domain!r}")
        if isinstance(self.anchor_id, bool) or not isinstance(self.anchor_id, int) or not (1 <= self.anchor_id <= MAX_ANCHOR_ID):
            raise UnsupportedSubject(f"anchor id {self.anchor_id!r} is not a valid id")
        if not isinstance(self.subject_key, str) or not self.subject_key or self.subject_key != self.subject_key.strip():
            raise UnsupportedSubject("subject_key must be a non-empty, trimmed string")
        allowed = {SLOT_ALLOCATION} if self.domain == STRATEGIC_LAND else {SLOT_LIFECYCLE, SLOT_PHASE, SLOT_RESIDUAL}
        if self.slot not in allowed:
            raise UnsupportedSubject(f"slot {self.slot!r} is not valid for domain {self.domain!r}")
        if self.fit not in FITS:
            raise UnsupportedSubject(f"unknown buyer-fit classification {self.fit!r}")
        if not isinstance(self.investigative, bool):
            raise UnsupportedSubject("investigative must be a bool")
        if self.count_precision is not None and self.count_precision not in _COUNT_PRECISIONS:
            raise UnsupportedSubject(f"unknown count precision {self.count_precision!r}")
        if self.id_system not in (ID_SYSTEM_OPPORTUNITY, ID_SYSTEM_FEED):
            raise UnsupportedSubject(f"unknown id system {self.id_system!r}")

    @property
    def family_key(self) -> tuple[str, int]:
        return (self.domain, self.anchor_id)


@dataclass(frozen=True)
class RelatedSubject:
    subject: FamilySubject
    role: str


@dataclass(frozen=True)
class OpportunityFamily:
    """A grouping of existing subjects. NOT an acquisition subject and never a whole-site claim."""
    family_key: tuple[str, int]
    representative: FamilySubject
    related: tuple[RelatedSubject, ...]

    @property
    def members(self) -> tuple[FamilySubject, ...]:
        return (self.representative, *(r.subject for r in self.related))

    @property
    def fit(self) -> str:
        """The family's fit: the representative's fit under the same deterministic order."""
        return self.representative.fit

    @property
    def investigative(self) -> bool:
        return self.representative.investigative

    @property
    def fit_rank(self) -> int:
        return fit_rank(self.representative.fit, self.representative.investigative)

    @property
    def is_terminally_excluded(self) -> bool:
        """True only if EVERY member is NOT_SUITABLE (the representative is the best member, so it is NOT_SUITABLE iff all are)."""
        return self.representative.fit == NOT_SUITABLE

    @property
    def overlap_state(self) -> str:
        """Same-site subjects may overlap and no non-overlap evidence exists in G3a: never summed (see OVERLAP_WARNING)."""
        return OVERLAP_SINGLE_SUBJECT if len(self.members) == 1 else OVERLAP_MAY_OVERLAP


# --- ordering ----------------------------------------------------------------------------------------------------------------

def fit_rank(fit: str, investigative: bool) -> int:
    """STRONG 0 < POSSIBLE 1 < INSUFFICIENT+investigative 2 < INSUFFICIENT 3 < NOT_SUITABLE 4 (lower is better)."""
    if fit == STRONG_FIT:
        return 0
    if fit == POSSIBLE_FIT:
        return 1
    if fit == INSUFFICIENT_EVIDENCE:
        return 2 if investigative else 3
    if fit == NOT_SUITABLE:
        return 4
    raise UnsupportedSubject(f"unknown buyer-fit classification {fit!r}")


def evidence_rank(count_precision: str | None) -> int:
    """EXACT 0 < APPROXIMATE (including a bounded RANGE) 1 < UNKNOWN / not stated 2."""
    if count_precision == "EXACT":
        return 0
    if count_precision in ("APPROXIMATE", "RANGE"):
        return 1
    return 2


def subject_order_key(subject: FamilySubject) -> tuple:
    """Total order within a family: fit, evidence quality, then the stable key. There is NO commercial-specificity or subject-kind
    term: specificity applies only to an evidence-qualified relationship (G2), which G3a does not have. The key has no commercial
    meaning - it only makes the result reproducible irrespective of input order. The key is compared as a plain STRING
    (lexical, not natural number order: '...A10' sorts before '...A9')."""
    return (fit_rank(subject.fit, subject.investigative), evidence_rank(subject.count_precision), subject.subject_key)


def _role(subject: FamilySubject) -> str:
    if subject.fit == STRONG_FIT:
        return ROLE_ALSO_STRONG_FIT
    if subject.fit == POSSIBLE_FIT:
        return ROLE_ALSO_POSSIBLE_FIT
    if subject.fit == INSUFFICIENT_EVIDENCE:
        return ROLE_INSUFFICIENT_INVESTIGATIVE if subject.investigative else ROLE_INSUFFICIENT
    return ROLE_NOT_SUITABLE


# --- grouping ----------------------------------------------------------------------------------------------------------------

def group_into_families(subjects: Iterable[FamilySubject]) -> list[OpportunityFamily]:
    """Group EXISTING subjects into families and choose each family's representative for this buyer.

    Input order never matters. Exact duplicates (same fields) collapse to one subject (so repeated link/relationship input cannot
    duplicate a family); a same-key subject with different fields, a second distinct lifecycle representation for one site, or two
    distinct subjects for one allocation raise. Families are ordered by fit bucket, then family key - no new scoring."""
    unique: dict[str, FamilySubject] = {}
    systems: set[str] = set()
    for subject in subjects:
        if not isinstance(subject, FamilySubject):
            raise UnsupportedSubject(f"expected FamilySubject, got {type(subject).__name__}")
        systems.add(subject.id_system)
        if len(systems) > 1:
            raise MixedIdentitySystems(
                "one grouping call must use one canonical subject-id representation "
                "(opportunity-universe ids or feed-card ids, not both)")
        existing = unique.get(subject.subject_key)
        if existing is None:
            unique[subject.subject_key] = subject
        elif existing != subject:
            raise ConflictingSubjectInput(f"subject {subject.subject_key!r} supplied twice with different values")

    by_family: dict[tuple[str, int], list[FamilySubject]] = {}
    for subject in unique.values():
        by_family.setdefault(subject.family_key, []).append(subject)

    families = []
    for family_key, members in by_family.items():
        lifecycle = sorted(m.subject_key for m in members if m.slot == SLOT_LIFECYCLE)
        if len(lifecycle) > 1:
            raise ConflictingLifecycleRepresentations(
                f"site {family_key[1]} has several lifecycle representations {lifecycle}; the detector precedence never produces this")
        if family_key[0] == STRATEGIC_LAND and len(members) > 1:
            raise ConflictingSubjectInput(f"allocation {family_key[1]} has several distinct subjects "
                                          f"{sorted(m.subject_key for m in members)}")
        ordered = sorted(members, key=subject_order_key)
        families.append(OpportunityFamily(
            family_key=family_key, representative=ordered[0],
            related=tuple(RelatedSubject(subject=m, role=_role(m)) for m in ordered[1:])))
    families.sort(key=lambda f: (f.fit_rank, f.family_key))
    return families


# --- adapters (pure; no feed/universe import) --------------------------------------------------------------------------------

def subject_from_opportunity_id(opportunity_id: str, *, fit: str, investigative: bool = False,
                                count_precision: str | None = None, source: object = None) -> FamilySubject:
    """A subject from an EXISTING opportunity id (the strict G1 parser). New kinds are not supported; the id is the stable key."""
    parsed = parse_opportunity_id(opportunity_id)
    if not parsed.is_legacy:
        raise UnsupportedSubject(f"{parsed.kind!r} subjects are not supported by G3a (no new kinds)")
    if parsed.domain == STRATEGIC_LAND:
        slot = SLOT_ALLOCATION
    elif parsed.kind in LIFECYCLE_KINDS:
        slot = SLOT_LIFECYCLE
    elif parsed.kind == KIND_PHASE:
        slot = SLOT_PHASE
    else:  # pragma: no cover - parse_opportunity_id already rejects anything else
        raise UnsupportedSubject(f"unsupported kind {parsed.kind!r}")
    return FamilySubject(domain=parsed.domain, anchor_id=parsed.anchor_id, subject_key=opportunity_id, slot=slot, fit=fit,
                         investigative=investigative, count_precision=count_precision, source=source,
                         id_system=ID_SYSTEM_OPPORTUNITY)


# Existing feed-card id shapes (app.reporting.dashboard / opportunity_feed). The card id is the explicit stable subject key.
# Numeric ids must be CANONICAL positive integers ('opp-lapse-3', never 'opp-lapse-03').
_CANON = r"([1-9][0-9]*)"
_FEED_LIFECYCLE_RE = re.compile(rf"^opp-(?:lapse|recent-permission|long-pending)-{_CANON}$")
_FEED_PHASE_RE = re.compile(rf"^opp-phase-{_CANON}-(.+)$")
_FEED_ALLOCATION_RE = re.compile(rf"^opp-feed-alloc-{_CANON}$")
_FEED_RESIDUAL_RE = re.compile(rf"^opp-residual-{_CANON}-([0-9a-f]{{20}})$")
_CANON_FULL_RE = re.compile(r"^[1-9][0-9]*$")


def subject_from_feed_card(card: Mapping) -> FamilySubject:
    """A subject from an existing feed-card mapping (``id``, ``opportunity_type``, ``params``, ``buyer_fit``, optional
    ``phase_code`` / ``count_assessment``). Unrecognised ids, an id/params mismatch or a missing buyer fit raise."""
    card_id = card.get("id")
    if not isinstance(card_id, str):
        raise UnsupportedSubject("feed card has no string id")
    params = card.get("params") or {}
    fit_object = card.get("buyer_fit")
    if fit_object is None:
        raise UnsupportedSubject(f"feed card {card_id!r} has no buyer fit")
    precision = getattr(card.get("count_assessment"), "precision", None)

    def _as_id(value):
        if isinstance(value, bool) or not (isinstance(value, int) or (isinstance(value, str) and _CANON_FULL_RE.match(value))):
            raise UnsupportedSubject(f"feed card {card_id!r} has a non-canonical id {value!r}")
        return int(value)

    match = _FEED_ALLOCATION_RE.match(card_id)
    if match:
        domain, slot, anchor = STRATEGIC_LAND, SLOT_ALLOCATION, int(match.group(1))
        if _as_id(params.get("allocation_id")) != anchor:
            raise UnsupportedSubject(f"feed card {card_id!r} id does not match its allocation_id")
    else:
        match = _FEED_LIFECYCLE_RE.match(card_id)
        slot = SLOT_LIFECYCLE
        if not match:
            match = _FEED_RESIDUAL_RE.match(card_id)
            slot = SLOT_RESIDUAL
            if match and (card.get("residual_subject_id") or "").rsplit(":", 1)[-1] != match.group(2):
                raise UnsupportedSubject(f"feed residual card {card_id!r} does not carry its derived residual identity")
        if not match:
            match = _FEED_PHASE_RE.match(card_id)
            slot = SLOT_PHASE
            if match:
                phase_code = card.get("phase_code")
                if not phase_code:
                    raise UnsupportedSubject(f"feed phase card {card_id!r} has no phase_code")
                if phase_code != match.group(2):  # the id-encoded scope and phase_code must agree exactly; never pick one
                    raise UnsupportedSubject(
                        f"feed phase card {card_id!r} id scope {match.group(2)!r} disagrees with phase_code {phase_code!r}")
        if not match:
            raise UnsupportedSubject(f"unrecognised feed card id {card_id!r}")
        domain, anchor = PLANNING_DELIVERY, int(match.group(1))
        if _as_id(params.get("site_id")) != anchor:
            raise UnsupportedSubject(f"feed card {card_id!r} id does not match its site_id")
    if card.get("opportunity_type") != domain:
        raise UnsupportedSubject(f"feed card {card_id!r} opportunity_type does not match its id")
    return FamilySubject(domain=domain, anchor_id=anchor, subject_key=card_id, slot=slot, fit=fit_object.classification,
                         investigative=bool(fit_object.is_investigative_exception), count_precision=precision, source=card,
                         id_system=ID_SYSTEM_FEED)
