"""v8 production transition - deterministic ROLLBACK of the strategic monitoring rebaseline (app.reporting.v8_monitoring_rebaseline).

The forward transition owns exactly two columns of exactly the reviewed ``OpportunityMonitoringState`` rows: ``fingerprint`` and ``fingerprint_fields``. This module restores those two columns, for those
rows, to the EXACT stored values the forward plan recorded (``previous_fingerprint`` and the verbatim ``previous_fingerprint_fields`` string) and touches nothing else.

Source of truth: the forward ``plan`` artifact (written before the forward apply) and the forward ``result`` artifact (proof the apply happened and for which ids). The restore plan is READ-ONLY by
default. Apply requires the confirm phrase and the digest of the REVIEWED restore plan, RE-READS the live rows and REFUSES unless every row is still exactly in the expected post-transition state
(fingerprint equals the proposed one and the stored fields equal the proposed fields) - so an intervening ordinary sync, a manual edit or a partial earlier restore refuses rather than being overwritten.
One transaction; any failure rolls back completely. No ordinary monitoring sync, no reseed, no schema change, no model call.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

from sqlalchemy import select

from app.db.models import OpportunityMonitoringState

RESTORE_PLAN_VERSION = 1
CONFIRM_PHRASE = "RESTORE PRE-V8 MONITORING FINGERPRINTS"
AT_POST_STATE, ALREADY_RESTORED, DRIFTED, MISSING = "AT_EXPECTED_POST_STATE", "ALREADY_AT_RESTORE_TARGET", "DRIFTED_FROM_EXPECTED_POST_STATE", "ROW_MISSING"


class RollbackRefused(ValueError):
    """The restore cannot be applied (blockers, digest mismatch, wrong phrase, bad forward artifacts). Nothing was written."""


def forward_digest_of(entries: list) -> str:
    from app.reporting.v8_monitoring_rebaseline import PLAN_VERSION
    payload = [{k: e[k] for k in ("opportunity_id", "previous_fingerprint", "proposed_fingerprint", "changed_fields", "previous_fingerprint_fields", "proposed_fingerprint_fields",
                                                                                            "previous_last_seen_at")} for e in entries]
    return hashlib.sha256(json.dumps({"v": PLAN_VERSION, "eligible": payload}, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def load_forward_artifacts(plan: dict, result: dict) -> dict:
    """Validate the two forward artifacts (already parsed JSON). Integrity: the plan digest must recompute from its own entries, the result must be an applied result of the SAME digest and the SAME ids."""
    entries = plan.get("eligible")
    if not isinstance(entries, list) or not entries:
        raise RollbackRefused("the forward plan artifact has no eligible entries")
    if plan.get("plan_digest") != forward_digest_of(entries):
        raise RollbackRefused("the forward plan artifact fails its own digest (modified or from an incompatible version)")
    if result.get("mode") != "applied" or result.get("plan_digest") != plan["plan_digest"]:
        raise RollbackRefused("the forward result artifact is not an applied result of this plan")
    if sorted(result.get("rebaselined_ids") or []) != sorted(e["opportunity_id"] for e in entries):
        raise RollbackRefused("the forward result's rebaselined ids differ from the plan's eligible ids")
    for entry in entries:
        if not entry.get("previous_fingerprint_fields") or not entry.get("proposed_fingerprint_fields") or "previous_last_seen_at" not in entry:
            raise RollbackRefused(f"{entry['opportunity_id']}: the exact previous/proposed fingerprint_fields were not recorded; refusing a lossy restore")
    return {"plan_digest": plan["plan_digest"], "entries": sorted(entries, key=lambda e: e["opportunity_id"])}


def _same_fields(stored, expected) -> bool:
    try:
        return json.loads(stored) == json.loads(expected)
    except (TypeError, ValueError):
        return False


def build_restore_plan(session, forward: dict) -> dict:
    """READ-ONLY (selects only)."""
    ids = [e["opportunity_id"] for e in forward["entries"]]
    rows = {r.opportunity_id: r for r in session.execute(select(OpportunityMonitoringState).where(OpportunityMonitoringState.opportunity_id.in_(ids))).scalars()}
    out, blockers = [], []
    for entry in forward["entries"]:
        row = rows.get(entry["opportunity_id"])
        if row is None:
            state = MISSING
        elif row.fingerprint == entry["proposed_fingerprint"] and _same_fields(row.fingerprint_fields, entry["proposed_fingerprint_fields"]):
            state = AT_POST_STATE
        elif row.fingerprint == entry["previous_fingerprint"] and row.fingerprint_fields == entry["previous_fingerprint_fields"]:
            state = ALREADY_RESTORED
        else:
            state = DRIFTED
        item = {"opportunity_id": entry["opportunity_id"], "current_state": state, "restore_fingerprint": entry["previous_fingerprint"],
                "restore_fingerprint_fields": entry["previous_fingerprint_fields"], "restore_last_seen_at": entry["previous_last_seen_at"],
                "expected_current_fingerprint": entry["proposed_fingerprint"]}
        out.append(item)
        if state != AT_POST_STATE:
            blockers.append({"opportunity_id": entry["opportunity_id"], "current_state": state})
    digest = hashlib.sha256(json.dumps({"v": RESTORE_PLAN_VERSION, "forward_plan_digest": forward["plan_digest"],
                                        "restore": [[e["opportunity_id"], e["restore_fingerprint"], e["restore_fingerprint_fields"], e["restore_last_seen_at"], e["expected_current_fingerprint"]] for e in out]},
                                       sort_keys=True).encode("utf-8")).hexdigest()
    return {"restore_plan_version": RESTORE_PLAN_VERSION, "read_only": True, "forward_plan_digest": forward["plan_digest"], "restore_plan_digest": digest,
            "can_apply": not blockers and bool(out), "blockers": blockers, "entries": out,
            "owned_fields": ["fingerprint", "fingerprint_fields", "last_seen_at"],
            "note": "Only these columns of only these rows are restored (last_seen_at is advanced by the forward engine as an ORM onupdate side effect and is restored to its recorded value); every other column and row is untouched."}


def apply_restore(session, forward: dict, *, confirm: str, expected_restore_digest: str) -> dict:
    if confirm != CONFIRM_PHRASE:
        raise RollbackRefused("confirmation phrase does not match")
    plan = build_restore_plan(session, forward)                                      # RE-READ the live state
    if plan["blockers"]:
        raise RollbackRefused(f"{len(plan['blockers'])} row(s) are not in the expected post-transition state: {plan['blockers']}")
    if plan["restore_plan_digest"] != expected_restore_digest:
        raise RollbackRefused("the live restore plan digest differs from the reviewed dry run")
    by_id = {e["opportunity_id"]: e for e in forward["entries"]}
    rows = {r.opportunity_id: r for r in session.execute(select(OpportunityMonitoringState).where(OpportunityMonitoringState.opportunity_id.in_(list(by_id)))).scalars()}
    try:
        for opportunity_id, entry in by_id.items():
            rows[opportunity_id].fingerprint = entry["previous_fingerprint"]
            rows[opportunity_id].fingerprint_fields = entry["previous_fingerprint_fields"]
            rows[opportunity_id].last_seen_at = dt.datetime.fromisoformat(entry["previous_last_seen_at"]) if entry["previous_last_seen_at"] else rows[opportunity_id].last_seen_at
        session.commit()                                                              # ONE commit
    except BaseException:
        session.rollback()
        raise
    after = build_restore_plan(session, forward)
    restored = sorted(e["opportunity_id"] for e in after["entries"] if e["current_state"] == ALREADY_RESTORED)
    return {"mode": "restored", "forward_plan_digest": forward["plan_digest"], "restore_plan_digest": plan["restore_plan_digest"], "restored_ids": restored,
            "all_restored": restored == sorted(by_id), "owned_fields": plan["owned_fields"]}
