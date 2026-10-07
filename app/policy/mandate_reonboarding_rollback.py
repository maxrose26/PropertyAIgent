"""v8 production transition - deterministic ROLLBACK of the stale-mandate re-onboarding (app.policy.mandate_reonboarding).

The forward transition owns exactly three columns of exactly the re-onboarded ``BuyerMandate`` rows: ``matching_fingerprint``, ``onboarding_completed_at`` and ``onboarding_summary``. This module restores
those three columns, for those mandates, to the EXACT values the forward APPLIED report recorded in each ``restore_snapshot`` (including the exact applied timestamp), and touches nothing else (no rule
field, no Buyer, no monitoring row).

Read-only by default. Apply requires the confirm phrase, the digest of the REVIEWED restore plan, Stage 1 buyer.write authority, re-reads the live mandates and REFUSES unless every one is still exactly in
the expected post-transition state. One transaction; any failure rolls back completely. No monitoring sync, no reseed, no model call.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

from sqlalchemy import select

from app.db.models import Buyer, BuyerMandate
from app.security.commands import command

RESTORE_PLAN_VERSION = 1
CONFIRM_PHRASE = "RESTORE PRE-V8 MANDATE BASELINES"
AT_POST_STATE, ALREADY_RESTORED, DRIFTED, MISSING = "AT_EXPECTED_POST_STATE", "ALREADY_AT_RESTORE_TARGET", "DRIFTED_FROM_EXPECTED_POST_STATE", "MANDATE_MISSING"


class RollbackRefused(ValueError):
    """Nothing was written."""


def _norm(value) -> str | None:
    """Timestamps compare as UTC wall-clock text (SQLite drops tzinfo; PostgreSQL keeps it)."""
    if value is None:
        return None
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value)
    if value.tzinfo is not None:
        value = value.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return value.isoformat()


def _parse(value):
    return None if value is None else dt.datetime.fromisoformat(value)


def load_forward_report(report: dict) -> dict:
    """Validate the forward APPLIED report (parsed JSON) and return the entries needed for restore."""
    if report.get("mode") != "applied" or not report.get("applied_onboarding_completed_at"):
        raise RollbackRefused("the forward report is not an APPLIED re-onboarding report with its applied timestamp")
    entries = []
    for item in report.get("stale_mandates") or []:
        snap = item.get("restore_snapshot")
        if not snap or "old_matching_fingerprint" not in snap or "proposed_matching_fingerprint" not in snap or "old_updated_at" not in snap:
            raise RollbackRefused(f"mandate {item.get('mandate_id')}: no exact restore snapshot recorded; refusing a lossy restore")
        entries.append({"mandate_id": item["mandate_id"], "buyer_key": item["buyer_key"], **snap})
    if not entries:
        raise RollbackRefused("the forward report re-onboarded no mandates")
    return {"forward_plan_digest": report["plan_digest"], "applied_at": report["applied_onboarding_completed_at"], "entries": sorted(entries, key=lambda e: e["mandate_id"])}


def _mandates(session, ids):
    from app.security.access import current_actor
    actor = current_actor()
    with session.no_autoflush:
        rows = session.execute(
            select(Buyer, BuyerMandate).join(BuyerMandate, BuyerMandate.buyer_id == Buyer.id)
            .where(Buyer.workspace_id == actor.workspace_id, Buyer.id.in_(sorted(actor.buyer_ids)), BuyerMandate.id.in_(ids))).all()
    return {m.id: (b, m) for b, m in rows}


def _compute(session, forward: dict) -> dict:
    found = _mandates(session, [e["mandate_id"] for e in forward["entries"]])
    out, blockers = [], []
    for entry in forward["entries"]:
        pair = found.get(entry["mandate_id"])
        if pair is None:
            state = MISSING
        else:
            m = pair[1]
            current = (m.matching_fingerprint, _norm(m.onboarding_completed_at), m.onboarding_summary)
            post = (entry["proposed_matching_fingerprint"], _norm(forward["applied_at"]), entry["proposed_onboarding_summary"])
            old = (entry["old_matching_fingerprint"], _norm(entry["old_onboarding_completed_at"]), entry["old_onboarding_summary"])
            state = AT_POST_STATE if current == post else ALREADY_RESTORED if current == old else DRIFTED
        item = {"mandate_id": entry["mandate_id"], "buyer_key": entry["buyer_key"], "current_state": state,
                "restore": {"matching_fingerprint": entry["old_matching_fingerprint"], "onboarding_completed_at": entry["old_onboarding_completed_at"],
                            "onboarding_summary": entry["old_onboarding_summary"], "updated_at": entry["old_updated_at"]},
                "expected_current_fingerprint": entry["proposed_matching_fingerprint"]}
        out.append(item)
        if state != AT_POST_STATE:
            blockers.append({"mandate_id": entry["mandate_id"], "current_state": state})
    digest = hashlib.sha256(json.dumps({"v": RESTORE_PLAN_VERSION, "forward_plan_digest": forward["forward_plan_digest"], "applied_at": _norm(forward["applied_at"]),
                                        "restore": [[e["mandate_id"], e["restore"], e["expected_current_fingerprint"]] for e in out]}, sort_keys=True).encode("utf-8")).hexdigest()
    return {"restore_plan_version": RESTORE_PLAN_VERSION, "read_only": True, "forward_plan_digest": forward["forward_plan_digest"], "restore_plan_digest": digest,
            "can_apply": not blockers and bool(out), "blockers": blockers, "entries": out,
            "owned_columns": ["matching_fingerprint", "onboarding_completed_at", "onboarding_summary", "updated_at"],
            "note": "Only these columns of only these mandates are restored (updated_at is advanced by the forward write as an ORM onupdate side effect and is restored to its recorded value); no rule field, buyer, monitoring row or other table is touched."}


@command('buyer.write')
def plan_mandate_reonboarding_rollback(session, forward: dict) -> dict:
    """Dry run (the default path): the restore plan against the live mandates. Zero writes."""
    return _compute(session, forward)


@command('buyer.write')
def apply_mandate_reonboarding_rollback(session, forward: dict, *, confirm: str, expected_restore_digest: str) -> dict:
    from app.security.access import current_actor
    from app.services.authorised_reads import require_workspace_write
    if confirm != CONFIRM_PHRASE:
        raise RollbackRefused("confirmation phrase does not match")
    require_workspace_write(session, current_actor().workspace_id)
    plan = _compute(session, forward)                                                  # RE-READ the live state
    if plan["blockers"]:
        raise RollbackRefused(f"{len(plan['blockers'])} mandate(s) are not in the expected post-transition state: {plan['blockers']}")
    if plan["restore_plan_digest"] != expected_restore_digest:
        raise RollbackRefused("the live restore plan digest differs from the reviewed dry run")
    found = _mandates(session, [e["mandate_id"] for e in forward["entries"]])
    try:
        for entry in forward["entries"]:
            mandate = found[entry["mandate_id"]][1]
            mandate.matching_fingerprint = entry["old_matching_fingerprint"]
            mandate.onboarding_completed_at = _parse(entry["old_onboarding_completed_at"])
            mandate.onboarding_summary = entry["old_onboarding_summary"]
            if entry["old_updated_at"]:
                mandate.updated_at = _parse(entry["old_updated_at"])               # explicit value: suppresses the ORM onupdate so the original timestamp is restored exactly
        session.commit()                                                                # ONE commit
    except BaseException:
        session.rollback()
        raise
    after = _compute(session, forward)
    restored = sorted(e["mandate_id"] for e in after["entries"] if e["current_state"] == ALREADY_RESTORED)
    return {"mode": "restored", "forward_plan_digest": forward["forward_plan_digest"], "restore_plan_digest": plan["restore_plan_digest"], "restored_mandate_ids": restored,
            "all_restored": restored == sorted(e["mandate_id"] for e in forward["entries"]), "owned_columns": plan["owned_columns"]}
