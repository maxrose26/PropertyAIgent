"""Stage 2.5B V7C-2: STANDALONE stale-mandate re-onboarding - the approved v7 transition path for mandate baselines.

It re-evaluates the CURRENT opportunity universe against every STALE active mandate (computed staleness: policy version / mandate fields changed, or never onboarded) and
restamps ``matching_fingerprint`` / ``onboarding_completed_at`` / ``onboarding_summary`` - and nothing else. Unlike ``bootstrap_acquisition_monitoring`` it runs NO ordinary global
monitoring sync, NO default-profile reseed, NO scraping/ingestion/agent evaluation/alert, and it never commits per mandate.

DRY-RUN IS THE DEFAULT: the plan path performs zero writes (selects only), builds the universe and every b2 context ONCE, evaluates each stale mandate against that SAME universe, and
reports non-secret audit information (identity, old/proposed fingerprint identifiers, timestamps, stored vs proposed summary with per-field deltas). The stored-summary comparison is SECONDARY
evidence (it can differ simply because the universe drifted since the last onboarding); the PRIMARY transition verification is same-universe v6/v7 parity of classification and the
investigative flag per opportunity (``parity_oracle``). The approved oracle is the TEMPORARY frozen v6 matcher (verification/transition: wired by scripts/reonboard_stale_mandates.py only;
the application never imports it). With no oracle supplied the plan reports parity NOT_AVAILABLE and APPLY REFUSES; any single mismatch makes the overall status FAILED and also refuses.
Nothing is faked by comparing counts.

APPLY (explicit): requires the confirm phrase, the digest of the REVIEWED dry-run plan (so exactly what was reviewed is what is applied; any drift refuses), a passing parity result, and
the existing Stage 1 workspace-write check. ALL mandates are computed first; then the row values are set and committed ONCE; any failure rolls back and leaves state unchanged.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy import select

from app.db.models import Buyer, BuyerMandate, utcnow
from app.policy.buyer_profile_store import (
    DEFAULT_STRATEGIC_LAND_PAGE_SIZE, compute_buyer_mandate_fingerprint, evaluate_policy_over_universe, is_buyer_mandate_baseline_stale, mandate_to_policy,
    summarise_onboarding_assessments,
)
from app.security.commands import command

REPORT_VERSION = 1
CONFIRM_PHRASE = "REONBOARD STALE MANDATES UNDER CURRENT POLICY"
PARITY_NOT_AVAILABLE, PARITY_PASSED, PARITY_FAILED = "NOT_AVAILABLE", "PASSED", "FAILED"
DIGEST_VERSION = 2
_MAX_LISTED_MISMATCHES = 20


class ReonboardingRefused(RuntimeError):
    """Apply refused before any write. ``reasons`` are deterministic, non-secret strings."""

    def __init__(self, reasons):
        self.reasons = tuple(reasons)
        super().__init__("; ".join(self.reasons))


@dataclass(frozen=True)
class ParityVerdict:
    classification_equal: bool
    investigative_equal: bool
    detail: str = ""
    # The compared values (v6 oracle vs v7), reported ONLY for mismatches; reason text is deliberately never part of parity.
    v6_classification: str | None = None
    v7_classification: str | None = None
    v6_investigative: bool | None = None
    v7_investigative: bool | None = None


# oracle(policy, opportunity_record, b2_context, v7_assessment) -> ParityVerdict, comparing the accepted v6 semantic result with the supplied v7 assessment on the SAME facts.
ParityOracle = Callable[..., ParityVerdict]


@dataclass
class _Entry:
    buyer_key: str
    mandate: BuyerMandate
    old_fingerprint: str | None
    proposed_fingerprint: str
    old_completed_at: dt.datetime | None
    old_summary: str | None
    proposed_summary: str
    reviewed: int
    parity_status: str
    parity_compared: int = 0
    classification_mismatches: int = 0
    investigative_mismatches: int = 0
    parity_mismatches: list = field(default_factory=list)
    outcomes_digest: str = ""


@dataclass
class ReonboardingPlan:
    universe_size: int
    entries: list
    fresh_mandates: int
    parity_status: str
    blocking_reasons: list
    universe_identity: str = ""

    @property
    def can_apply(self) -> bool:
        return bool(self.entries) and not self.blocking_reasons

    def digest(self) -> str:
        """Binds apply to the REVIEWED plan (it is NOT authentication - Stage 1 operator permission is the authority). Covers: the stale mandate set and identities, the FULL old and
        proposed mandate fingerprints, the proposed summaries, the universe identity (every opportunity id with its evidence fingerprint), the per-mandate assessed outcomes
        (opportunity id, classification, investigative flag), the parity result and aggregates, and the matching policy version. No secrets; no timestamps."""
        from app.policy.buyer_matching import BUYER_MATCHING_POLICY_VERSION
        material = {
            "digest_version": DIGEST_VERSION, "policy_version": BUYER_MATCHING_POLICY_VERSION, "universe_size": self.universe_size, "universe_identity": self.universe_identity,
            "parity": self.parity_status,
            "entries": [[e.buyer_key, e.mandate.id, e.old_fingerprint, e.proposed_fingerprint, e.proposed_summary, e.outcomes_digest, e.parity_status, e.parity_compared,
                         e.classification_mismatches, e.investigative_mismatches] for e in self.entries],
        }
        return hashlib.sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()

    def report(self, *, mode: str) -> dict:
        return {
            "report_version": REPORT_VERSION, "mode": mode, "read_only": mode == "dry_run", "universe_size": self.universe_size,
            "stale_mandates": [_entry_report(e) for e in self.entries], "fresh_mandates_untouched": self.fresh_mandates,
            "parity": {
                "status": self.parity_status, "boundary": "classification and investigative flag per opportunity, same universe (reason text excluded)",
                "opportunities_compared": sum(e.parity_compared for e in self.entries),
                "classification_mismatches": sum(e.classification_mismatches for e in self.entries),
                "investigative_mismatches": sum(e.investigative_mismatches for e in self.entries),
            },
            "can_apply": self.can_apply, "blocking_reasons": list(self.blocking_reasons), "plan_digest": self.digest(),
            "secondary_note": "stored-summary differences are SECONDARY evidence (possible universe drift); same-universe parity is the primary check",
        }


def _short(fingerprint) -> str | None:
    return None if not fingerprint else str(fingerprint)[:12]


_SUMMARY_FIELD = re.compile(r"([a-z_]+)=(\d+)")


def parse_summary(text: str | None) -> dict:
    return {key: int(value) for key, value in _SUMMARY_FIELD.findall(text or "")}


def _entry_report(entry: _Entry) -> dict:
    old, new = parse_summary(entry.old_summary), parse_summary(entry.proposed_summary)
    delta = {key: {"old": old.get(key), "new": new.get(key)} for key in sorted(set(old) | set(new)) if old.get(key) != new.get(key)}
    return {
        "buyer_key": entry.buyer_key, "mandate_id": entry.mandate.id,
        "old_fingerprint_id": _short(entry.old_fingerprint), "proposed_fingerprint_id": _short(entry.proposed_fingerprint),
        "old_onboarding_completed_at": entry.old_completed_at.isoformat() if entry.old_completed_at else None,
        "old_summary": entry.old_summary, "proposed_summary": entry.proposed_summary, "opportunities_reviewed": entry.reviewed,
        "stored_vs_proposed_summary_delta": delta,
        "drift_note": ("stored summary differs from the proposed summary: possible universe drift or a policy change since the previous onboarding (secondary evidence only)"
                       if delta else None),
        "parity": {"status": entry.parity_status, "opportunities_compared": entry.parity_compared, "classification_mismatches": entry.classification_mismatches,
                   "investigative_mismatches": entry.investigative_mismatches,
                   "mismatches_listed": list(entry.parity_mismatches)},   # at most _MAX_LISTED_MISMATCHES; a passing run lists none (no per-opportunity PASS lines)
    }


def _stale_active_mandates(session, buyer_keys=None):
    """Active mandates of active buyers this actor may see, stale by the computed fingerprint rule. Selects only; deterministic order."""
    from app.security.access import current_actor
    actor = current_actor()
    with session.no_autoflush:
        rows = session.execute(
            select(Buyer, BuyerMandate).join(BuyerMandate, BuyerMandate.buyer_id == Buyer.id)
            .where(Buyer.workspace_id == actor.workspace_id, Buyer.id.in_(sorted(actor.buyer_ids)), Buyer.status == "active", BuyerMandate.status == "active")
            .order_by(Buyer.buyer_key, BuyerMandate.id)
        ).all()
    wanted = None if buyer_keys is None else set(buyer_keys)
    candidates = [(b, m) for b, m in rows if wanted is None or b.buyer_key in wanted]
    return [(b, m) for b, m in candidates if is_buyer_mandate_baseline_stale(m)], len(candidates)


def compute_reonboarding_plan(session, *, page_size=DEFAULT_STRATEGIC_LAND_PAGE_SIZE, buyer_keys=None, parity_oracle: ParityOracle | None = None) -> ReonboardingPlan:
    """READ-ONLY. Builds the universe and every b2 context exactly ONCE, evaluates each stale mandate against that same universe and, when an oracle is supplied, checks
    same-universe parity per opportunity. Raises nothing for a parity mismatch (it is reported and blocks apply); any computation error propagates and nothing is written."""
    from app.policy.buyer_matching_b2_context import build_b2_context
    from app.reporting.opportunity_universe import build_current_opportunity_universe, compute_opportunity_fingerprint
    stale, candidates = _stale_active_mandates(session, buyer_keys)
    if not stale:
        return ReonboardingPlan(universe_size=0, entries=[], fresh_mandates=candidates, parity_status=PARITY_NOT_AVAILABLE if parity_oracle is None else PARITY_PASSED,
                                blocking_reasons=[])
    with session.no_autoflush:
        universe = build_current_opportunity_universe(session, page_size=page_size)
        contexts = {o.opportunity_id: build_b2_context(session, o.opportunity_id, o.opportunity_type) for o in universe}
    by_id = {o.opportunity_id: o for o in universe}
    universe_identity = hashlib.sha256(json.dumps(sorted([o.opportunity_id, compute_opportunity_fingerprint(o.fingerprint_fields)] for o in universe)).encode("utf-8")).hexdigest()
    entries, blocking = [], []
    for buyer, mandate in stale:
        policy = mandate_to_policy(mandate)
        with session.no_autoflush:
            assessments = evaluate_policy_over_universe(session, policy, universe, contexts)
        result = summarise_onboarding_assessments(assessments)
        entry = _Entry(buyer_key=buyer.buyer_key, mandate=mandate, old_fingerprint=mandate.matching_fingerprint,
                       proposed_fingerprint=compute_buyer_mandate_fingerprint(policy), old_completed_at=mandate.onboarding_completed_at,
                       old_summary=mandate.onboarding_summary, proposed_summary=result.summary_line, reviewed=result.opportunities_reviewed,
                       parity_status=PARITY_NOT_AVAILABLE,
                       outcomes_digest=hashlib.sha256(json.dumps(sorted([i, a.classification, bool(a.is_investigative_exception)] for i, a in assessments)).encode("utf-8")).hexdigest())
        if parity_oracle is not None:
            entry.parity_status = PARITY_PASSED
            for opportunity_id, assessment in assessments:
                verdict = parity_oracle(policy, by_id[opportunity_id], contexts.get(opportunity_id), assessment)
                entry.parity_compared += 1
                if not verdict.classification_equal:
                    entry.classification_mismatches += 1
                if not verdict.investigative_equal:
                    entry.investigative_mismatches += 1
                if not (verdict.classification_equal and verdict.investigative_equal):
                    entry.parity_status = PARITY_FAILED
                    if len(entry.parity_mismatches) < _MAX_LISTED_MISMATCHES:
                        entry.parity_mismatches.append({
                            "buyer_key": buyer.buyer_key, "mandate_id": mandate.id, "opportunity_id": opportunity_id,
                            "v6_classification": verdict.v6_classification, "v7_classification": verdict.v7_classification,
                            "v6_investigative": verdict.v6_investigative, "v7_investigative": verdict.v7_investigative, "detail": verdict.detail})
        entries.append(entry)
    statuses = {e.parity_status for e in entries}
    overall = PARITY_FAILED if PARITY_FAILED in statuses else PARITY_NOT_AVAILABLE if PARITY_NOT_AVAILABLE in statuses else PARITY_PASSED
    if overall == PARITY_NOT_AVAILABLE:
        blocking.append("same-universe v6/v7 parity oracle not configured: parity is NOT_AVAILABLE and apply is impossible")
    elif overall == PARITY_FAILED:
        blocking.append("same-universe v6/v7 parity FAILED (classification or investigative flag differs for at least one opportunity): fail closed, do not re-onboard")
    return ReonboardingPlan(universe_size=len(universe), entries=entries, fresh_mandates=candidates - len(stale), parity_status=overall, blocking_reasons=blocking,
                            universe_identity=universe_identity)


@command('buyer.write')
def plan_stale_mandate_reonboarding(session, *, page_size: int = DEFAULT_STRATEGIC_LAND_PAGE_SIZE, buyer_keys=None, parity_oracle: ParityOracle | None = None) -> dict:
    """Dry-run (the default path): the audit report for every stale mandate. Zero writes."""
    return compute_reonboarding_plan(session, page_size=page_size, buyer_keys=buyer_keys, parity_oracle=parity_oracle).report(mode="dry_run")


@command('buyer.write')
def apply_stale_mandate_reonboarding(session, *, confirm: str, expected_plan_digest: str, page_size: int = DEFAULT_STRATEGIC_LAND_PAGE_SIZE, buyer_keys=None,
                                     parity_oracle: ParityOracle | None = None) -> dict:
    """Explicit apply. Refuses (ReonboardingRefused, no write) unless the confirm phrase matches, the freshly recomputed plan's digest equals the REVIEWED dry-run digest and
    the plan is applicable (parity PASSED). Computes ALL mandates first, then sets the three baseline columns on each and commits ONCE; a failure rolls back."""
    from app.security.access import current_actor
    from app.services.authorised_reads import require_workspace_write
    if confirm != CONFIRM_PHRASE:
        raise ReonboardingRefused(["explicit confirm phrase required"])
    require_workspace_write(session, current_actor().workspace_id)
    plan = compute_reonboarding_plan(session, page_size=page_size, buyer_keys=buyer_keys, parity_oracle=parity_oracle)
    reasons = list(plan.blocking_reasons)
    if not plan.entries:
        reasons.append("no stale mandates: nothing to apply")
    if plan.digest() != expected_plan_digest:
        reasons.append("plan changed since the reviewed dry run (universe or mandate drift): re-run the dry run")
    if reasons:
        raise ReonboardingRefused(reasons)
    now = utcnow()
    try:
        for entry in plan.entries:
            entry.mandate.matching_fingerprint = entry.proposed_fingerprint
            entry.mandate.onboarding_completed_at = now
            entry.mandate.onboarding_summary = entry.proposed_summary
        session.commit()                                   # ONE controlled commit for every mandate
    except BaseException:
        session.rollback()
        raise
    return plan.report(mode="applied")
