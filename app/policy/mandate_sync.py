"""Specification 027: explicit, audited SYNC of an EXISTING stored buyer mandate to an approved canonical mandate change.

Five things are kept apart and never conflated:
  1. CANONICAL BUYER TEMPLATE (app.policy.buyer_profiles)      - the product-approved intended strategy; a seed/default only.
  2. STORED BUYER MANDATE (BuyerMandate row)                   - what matching actually uses; never touched by reseeding or startup.
  3. MANDATE SYNC (this module)                                - an explicit, Product Owner-approved update of NAMED rule fields of ONE mandate.
  4. RE-ONBOARDING (app.policy.mandate_reonboarding)           - recomputes/stamps the baseline AFTER the mandate is correct; this module never does it.
  5. BUYER MATCHING POLICY VERSION (BUYER_MATCHING_POLICY_VERSION) - the deterministic matching semantics.

This is deliberately NOT "overwrite mandates from defaults". The only authorised correction is the one in APPROVED_CHANGES (Nesten Homes, commit f8e1c9b: preferred maximum 100 -> 200,
no wholly-affordable exclusion, the approved brief as notes). A plan is READY only when the stored mandate is EXACTLY the expected pre-correction state (whole-policy sha256 pin) and the
resulting state is EXACTLY the pinned approved post-correction state; any other state (drift, an extra difference, another buyer, already corrected) is refused / reported, never "fixed".

DRY RUN is the default (selects only). APPLY needs the Stage 1 operator command check, the confirm phrase, the digest of the REVIEWED plan and the exact expected old state; it updates only
the approved columns in ONE transaction (rolled back on any failure) and does NOT touch the onboarding baseline columns, so the stored baseline fingerprint stops matching and the mandate
becomes STALE by computation (is_buyer_mandate_baseline_stale). It never re-onboards, runs monitoring, reseeds, calls a model, scrapes or alerts.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field

from sqlalchemy import select

from app.db.models import BuyerMandate
from app.policy.buyer_matching import BUYER_MATCHING_POLICY_VERSION, discovery_bounds
from app.policy.buyer_profile_store import (
    DEFAULT_MANDATE_KEY, _resolve_default_mandate_for_buyer, _template_to_mandate_fields, compute_buyer_mandate_fingerprint, is_buyer_mandate_baseline_stale, mandate_to_policy,
)
from app.policy.buyer_profiles import BUYER_PROFILES
from app.security.commands import command

REPORT_VERSION = 1
DIGEST_VERSION = 1
CONFIRM_PHRASE = "SYNC NESTEN MANDATE TO APPROVED CANONICAL BRIEF"

# The ONLY BuyerMandate columns this mechanism may ever write (canonical-template rule/brief fields). Everything else is PRESERVED instance/operational state.
SYNCABLE_RULE_FIELDS = (
    "primary_requirement", "target_unit_min", "target_unit_max", "scale_metric", "accepted_planning_states", "treats_no_activity_as_positive", "large_allocation_is_self_qualifying",
    "specialist_development_is_exclusion", "wholly_affordable_is_exclusion", "below_minimum_scale_is_exclusion", "notes", "geography_scope", "geography_councils", "acquisition_types",
    "development_state_appetite", "control_appetite",
)
# Never written here: identity, workspace, status, provenance, display name, and the whole onboarding baseline (so the old baseline is left in place and is STALE by computation).
PRESERVED_FIELDS = ("id", "buyer_id", "mandate_key", "display_name", "status", "source_template_key", "matching_fingerprint", "onboarding_completed_at", "onboarding_summary", "created_at")
BASELINE_FIELDS = ("matching_fingerprint", "onboarding_completed_at", "onboarding_summary")


class MandateSyncRefused(RuntimeError):
    """Apply refused before any write. ``reasons`` are deterministic, non-secret strings."""

    def __init__(self, reasons):
        self.reasons = tuple(reasons)
        super().__init__("; ".join(self.reasons))


@dataclass(frozen=True)
class ApprovedMandateChange:
    buyer_key: str
    approved_fields: tuple
    expected_old_policy_sha256: str       # whole-policy sha256 of the stored mandate BEFORE the correction (the pre-f8e1c9b canonical template; Gate B digest prefix cc45186babbf1043)
    expected_new_policy_sha256: str       # whole-policy sha256 of the mandate AFTER the correction (the approved canonical template)
    reasons: dict = field(default_factory=dict)
    source_commit: str = ""


APPROVED_CHANGES = {
    "nesten_homes": ApprovedMandateChange(
        buyer_key="nesten_homes", approved_fields=("target_unit_max", "wholly_affordable_is_exclusion", "notes"),
        expected_old_policy_sha256="cc45186babbf1043a7d3319e1dc1d043ba31e56b4c40c2ccabf827442a31d607",
        expected_new_policy_sha256="ee54c5eae327b3eb2f0235ce0e7a00cc47402ba409ed925e2c9addb1835068f1",
        source_commit="f8e1c9b61f6d2624d60959dc62a41cc4ddd8d20e",
        reasons={
            "target_unit_max": "Real Nesten Land Requirements: preferred scale 50-200 homes (discovery 45-220 is derived); accepted in f8e1c9b",
            "wholly_affordable_is_exclusion": "The brief states no affordable-housing exclusion; wholly-affordable evidence is investigation context, not a hard exclusion; accepted in f8e1c9b",
            "notes": "The approved real brief recorded as mandate notes (no new matching rules); accepted in f8e1c9b",
        }),
}


def policy_sha256(policy) -> str:
    """Whole-policy digest (the full-length form of the digest recorded in the Gate B artifact)."""
    def default(value):
        return sorted(value) if isinstance(value, (set, frozenset)) else str(value)
    return hashlib.sha256(json.dumps(dataclasses.asdict(policy), sort_keys=True, default=default).encode()).hexdigest()


@dataclass
class MandateSyncPlan:
    buyer_key: str
    status: str                                   # READY | ALREADY_CORRECTED | DRIFT | TARGET_NOT_APPROVED | MANDATE_NOT_FOUND
    blocking_reasons: list
    mandate: object = None
    buyer_id: int | None = None
    mandate_id: int | None = None
    workspace_id: int | None = None
    stored_sha256: str | None = None
    proposed_sha256: str | None = None
    expected_old_sha256: str | None = None
    expected_new_sha256: str | None = None
    diff: list = field(default_factory=list)      # [{field, old, proposed, reason}]
    discovery_before: tuple | None = None
    discovery_after: tuple | None = None
    baseline_present: bool = False
    stale_before: bool | None = None
    stale_after_correction: bool | None = None

    @property
    def applicable(self) -> bool:
        return self.status == "READY" and not self.blocking_reasons

    def digest(self) -> str:
        material = {"digest_version": DIGEST_VERSION, "matching_policy_version": BUYER_MATCHING_POLICY_VERSION, "buyer_key": self.buyer_key, "buyer_id": self.buyer_id,
                    "mandate_id": self.mandate_id, "workspace_id": self.workspace_id, "expected_old_sha256": self.expected_old_sha256, "stored_sha256": self.stored_sha256,
                    "proposed_sha256": self.proposed_sha256, "diff": self.diff, "status": self.status}
        return hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()

    def report(self, mode: str) -> dict:
        return {"report_version": REPORT_VERSION, "mode": mode, "buyer_key": self.buyer_key, "status": self.status, "applicable": self.applicable, "blocking_reasons": list(self.blocking_reasons),
                "plan_digest": self.digest(), "matching_policy_version": BUYER_MATCHING_POLICY_VERSION, "target": {"buyer_id": self.buyer_id, "mandate_id": self.mandate_id, "workspace_id": self.workspace_id},
                "expected_old_policy_sha256": self.expected_old_sha256, "stored_policy_sha256": self.stored_sha256, "proposed_policy_sha256": self.proposed_sha256,
                "expected_new_policy_sha256": self.expected_new_sha256, "field_diff": list(self.diff),
                "derived": {"discovery_before": self.discovery_before, "discovery_after": self.discovery_after},
                "baseline": {"stored_baseline_present": self.baseline_present, "stale_before": self.stale_before, "stale_after_correction": self.stale_after_correction,
                             "note": "the onboarding baseline columns are never written by this command; the old baseline is left in place and is stale by computation"},
                "preserved_fields": list(PRESERVED_FIELDS), "syncable_rule_fields": list(SYNCABLE_RULE_FIELDS)}


def _column(row, name):
    return getattr(row, name)


def compute_mandate_sync_plan(session, buyer_key: str) -> MandateSyncPlan:
    """Pure read: the field-level plan for one buyer. Zero writes."""
    change = APPROVED_CHANGES.get(buyer_key)
    if change is None:
        return MandateSyncPlan(buyer_key=buyer_key, status="TARGET_NOT_APPROVED", blocking_reasons=[f"no approved mandate correction exists for buyer {buyer_key!r}; only {sorted(APPROVED_CHANGES)} is authorised"])
    from app.services.authorised_reads import buyer_by_key, mandate_by_id, persistent_id
    buyer = buyer_by_key(session, buyer_key)
    with session.no_autoflush:
        mandate = _resolve_default_mandate_for_buyer(session, buyer)
    if mandate is None:
        return MandateSyncPlan(buyer_key=buyer_key, status="MANDATE_NOT_FOUND", blocking_reasons=["no active default mandate for this buyer"], buyer_id=buyer.id)
    mandate = mandate_by_id(session, persistent_id(mandate))
    template = BUYER_PROFILES[buyer_key]
    stored_policy = mandate_to_policy(mandate)
    stored_sha = policy_sha256(stored_policy)
    proposed_policy = dataclasses.replace(stored_policy, **{name: getattr(template, name) for name in SYNCABLE_RULE_FIELDS})
    proposed_sha = policy_sha256(proposed_policy)
    template_columns = _template_to_mandate_fields(template, mandate.buyer_id)
    diff = [{"field": name, "old": _column(mandate, name), "proposed": template_columns[name], "reason": change.reasons.get(name, "UNAPPROVED FIELD DIFFERENCE")}
            for name in SYNCABLE_RULE_FIELDS if _column(mandate, name) != template_columns[name]]
    reasons: list = []
    if mandate.mandate_key != DEFAULT_MANDATE_KEY or mandate.status != "active":
        reasons.append("the target mandate is not the active default mandate")
    unexpected = [d["field"] for d in diff if d["field"] not in change.approved_fields]
    if unexpected:
        reasons.append(f"stored mandate differs from the canonical template in unapproved fields {unexpected}: refusing to sync")
    if proposed_sha != change.expected_new_policy_sha256:
        reasons.append("the canonical template or the resulting mandate state is not the pinned approved post-correction state")
    if stored_sha == change.expected_new_policy_sha256:
        status = "ALREADY_CORRECTED"
    elif stored_sha == change.expected_old_policy_sha256 and not reasons:
        status = "READY"
    else:
        status = "DRIFT"
        if stored_sha != change.expected_old_policy_sha256:
            reasons.append("stored mandate is not the expected pre-correction state (whole-policy digest differs): refusing; investigate drift")
    baseline_present = mandate.matching_fingerprint is not None and mandate.onboarding_completed_at is not None
    stale_after = (not baseline_present) or compute_buyer_mandate_fingerprint(proposed_policy) != mandate.matching_fingerprint
    return MandateSyncPlan(
        buyer_key=buyer_key, status=status, blocking_reasons=reasons, mandate=mandate, buyer_id=mandate.buyer_id, mandate_id=mandate.id, workspace_id=buyer.workspace_id, stored_sha256=stored_sha,
        proposed_sha256=proposed_sha, expected_old_sha256=change.expected_old_policy_sha256, expected_new_sha256=change.expected_new_policy_sha256, diff=diff,
        discovery_before=discovery_bounds(stored_policy.target_unit_min, stored_policy.target_unit_max), discovery_after=discovery_bounds(proposed_policy.target_unit_min, proposed_policy.target_unit_max),
        baseline_present=baseline_present, stale_before=is_buyer_mandate_baseline_stale(mandate), stale_after_correction=stale_after)


@command('buyer.write')
def plan_mandate_sync(session, *, buyer_key: str = "nesten_homes") -> dict:
    """Dry run (the default path): the reviewable field-level plan. Zero writes."""
    return compute_mandate_sync_plan(session, buyer_key).report(mode="dry_run")


@command('buyer.write')
def apply_mandate_sync(session, *, buyer_key: str, confirm: str, expected_plan_digest: str) -> dict:
    """Explicit apply. Refuses (MandateSyncRefused, no write) unless the confirm phrase matches, the buyer is the approved target, the freshly recomputed plan is READY (stored state is exactly the
    expected old state) and its digest equals the REVIEWED dry-run digest. Writes ONLY the approved columns, in ONE transaction; any failure rolls back. Does not touch the onboarding baseline."""
    from app.security.access import current_actor
    from app.services.authorised_reads import require_workspace_write
    if confirm != CONFIRM_PHRASE:
        raise MandateSyncRefused(["explicit confirm phrase required"])
    if buyer_key not in APPROVED_CHANGES:
        raise MandateSyncRefused([f"no approved mandate correction exists for buyer {buyer_key!r}"])
    require_workspace_write(session, current_actor().workspace_id)
    plan = compute_mandate_sync_plan(session, buyer_key)
    reasons = list(plan.blocking_reasons)
    if plan.status != "READY":
        reasons.append(f"plan status is {plan.status}: nothing to apply")
    if plan.digest() != expected_plan_digest:
        reasons.append("plan changed since the reviewed dry run (stored mandate drift): re-run the dry run")
    if reasons:
        raise MandateSyncRefused(reasons)
    approved = set(APPROVED_CHANGES[buyer_key].approved_fields)
    try:
        with session.no_autoflush:
            row = session.execute(select(BuyerMandate).where(BuyerMandate.id == plan.mandate_id).with_for_update().execution_options(populate_existing=True)).scalar_one()
        if policy_sha256(mandate_to_policy(row)) != plan.stored_sha256 or row.status != "active" or row.mandate_key != DEFAULT_MANDATE_KEY:   # re-verified under the row lock, same transaction
            raise MandateSyncRefused(["stored mandate changed between plan and write"])
        for entry in plan.diff:
            if entry["field"] not in approved:                                          # defence in depth: the plan already refuses unapproved fields
                raise MandateSyncRefused([f"field {entry['field']!r} is not approved"])
            setattr(row, entry["field"], entry["proposed"])
        session.commit()                                                                # ONE controlled commit
    except BaseException:
        session.rollback()
        raise
    report = plan.report(mode="applied")
    session.expire_all()
    after = session.get(BuyerMandate, plan.mandate_id)
    report["verified_after"] = {"stored_policy_sha256": policy_sha256(mandate_to_policy(after)), "baseline_stale": is_buyer_mandate_baseline_stale(after)}
    return report
