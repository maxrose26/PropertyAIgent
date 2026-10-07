"""Stage 2.5B v8 production transition - the narrow, dry-run-first, digest-bound monitoring rebaseline for the INTENTIONAL strategic capacity-semantics fingerprint change.

Why: v8 adds ONE fingerprint entry, ``capacity_semantics`` (precision / value / lower / upper), to the evidence fingerprint of a strategic allocation whose plan-stated capacity is NOT
exact (app.reporting.opportunity_universe.strategic_capacity_fingerprint_fields). Exact capacities and every planning-delivery fingerprint are unchanged. Left alone, the first ordinary sync after
the v8 code is active would report each such allocation MATERIALLY_CHANGED although nothing changed on the ground. This module reconciles exactly those rows - and nothing else - using the
EXISTING Category C ("rebaseline") engine (app.reporting.opportunity_monitoring_transition.apply_monitoring_transition), so no new write mechanism and no SQL rewrite is introduced.

Eligible (ALL must hold) - an opportunity is rebaselined only if it is:
  * a tracked ``strategic_land:allocation:{id}`` row (detector ``strategic_land``) that the read-only ordinary-sync preview predicts MATERIALLY_CHANGED; and
  * its ONLY changed fingerprint field is ``capacity_semantics``, whose OLD value is absent (the pre-v8 fingerprint had no such entry) and whose NEW value is a non-EXACT kind.
Anything else the preview reports is NOT touched and NOT hidden:
  * planning-delivery changes, strategic changes in any other field, NEW/untracked and retired ids are listed under ``not_included`` (ordinary monitoring will report them as it would anyway);
  * a strategic row that changed ``capacity_semantics`` AND another field is a MIXED change (a genuine evidence change coincides with v8): it is listed under ``blockers`` and apply is REFUSED,
    because rebaselining would hide the genuine change - REVIEW decides.
The plan carries a deterministic digest over the eligible entries (id, previous / new fingerprint, changed fields). Apply requires the confirm phrase and the digest of the REVIEWED dry run, recomputes the
plan against the live state, refuses on any difference or blocker, and then performs the one engine commit. No model call, no schema change, no ordinary sync, no reseed, no buyer/mandate write.
"""
from __future__ import annotations

import hashlib
import json

from app.reporting.opportunity_change import MATERIALLY_CHANGED, opportunity_detector_identity, preview_ordinary_sync
from app.reporting.opportunity_monitoring_transition import MonitoringTransitionManifest, apply_monitoring_transition

PLAN_VERSION = 1
CONFIRM_PHRASE = "REBASELINE V8 STRATEGIC CAPACITY SEMANTICS"
STRATEGIC_PREFIX = "strategic_land:allocation:"
SEMANTICS_FIELD = "capacity_semantics"
EXPECTED_REASON = ("v8 strategic capacity semantics: the evidence fingerprint now records the non-exact plan-stated capacity kind (software change, not new planning evidence)")


class RebaselineRefused(ValueError):
    """The reviewed plan cannot be applied (blockers, digest mismatch or a wrong confirmation phrase). Nothing was written."""


def _is_expected_semantic_change(change: dict) -> bool:
    fields = change.get("changed_fields") or {}
    if set(fields) != {SEMANTICS_FIELD}:
        return False
    old, new = fields[SEMANTICS_FIELD].get("old"), fields[SEMANTICS_FIELD].get("new")
    return old is None and isinstance(new, dict) and new.get("precision") not in (None, "EXACT")


def build_rebaseline_plan(session, *, preview: dict | None = None) -> dict:
    """READ-ONLY. ``preview`` (tests) defaults to ``preview_ordinary_sync(session)`` - the same planner the real sync uses."""
    preview = preview if preview is not None else preview_ordinary_sync(session)
    eligible, not_included, blockers = [], [], []
    for change in preview["changes"]:
        opportunity_id = change["opportunity_id"]
        base = {"opportunity_id": opportunity_id, "detector": opportunity_detector_identity(opportunity_id), "classification": change["classification"],
                "previous_fingerprint": change["previous_fingerprint"], "proposed_fingerprint": change["new_fingerprint"], "changed_fields": change["changed_fields"]}
        strategic = opportunity_id.startswith(STRATEGIC_PREFIX)
        if strategic and change["classification"] == MATERIALLY_CHANGED and _is_expected_semantic_change(change):
            eligible.append({**base, "reason": EXPECTED_REASON, "expected_v8_strategic_capacity_semantic_change": True})
        elif strategic and change["classification"] == MATERIALLY_CHANGED and SEMANTICS_FIELD in (change.get("changed_fields") or {}):
            blockers.append({**base, "blocker": "MIXED_CHANGE: capacity_semantics changed together with other evidence fields; a genuine change coincides with v8"})
        else:
            not_included.append({**base, "why_not_included": "not a v8 strategic capacity-semantics change; ordinary monitoring will report it as it would regardless of v8"})
    eligible.sort(key=lambda e: e["opportunity_id"])
    digest_payload = [{k: e[k] for k in ("opportunity_id", "previous_fingerprint", "proposed_fingerprint", "changed_fields")} for e in eligible]
    digest = hashlib.sha256(json.dumps({"v": PLAN_VERSION, "eligible": digest_payload}, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return {
        "plan_version": PLAN_VERSION, "read_only": True, "plan_digest": digest, "can_apply": not blockers and bool(eligible),
        "totals": {"eligible": len(eligible), "blockers": len(blockers), "not_included": len(not_included), **{f"preview_{k}": v for k, v in preview["totals"].items()}},
        "eligible": eligible, "blockers": sorted(blockers, key=lambda b: b["opportunity_id"]), "not_included": sorted(not_included, key=lambda n: n["opportunity_id"]),
        "planning_delivery_in_eligible": sum(1 for e in eligible if e["opportunity_id"].startswith("planning_delivery:")),
        "note": "Only strategic allocations whose sole fingerprint change is the added non-exact capacity_semantics entry are eligible. Nothing else is touched.",
    }


def apply_rebaseline(session, *, confirm: str, expected_plan_digest: str) -> dict:
    if confirm != CONFIRM_PHRASE:
        raise RebaselineRefused("confirmation phrase does not match")
    plan = build_rebaseline_plan(session)
    if plan["blockers"]:
        raise RebaselineRefused(f"{len(plan['blockers'])} blocker(s): a genuine evidence change coincides with the v8 change; REVIEW must decide")
    if not plan["eligible"]:
        raise RebaselineRefused("nothing to rebaseline")
    if plan["plan_digest"] != expected_plan_digest:
        raise RebaselineRefused("the live plan digest differs from the reviewed dry run; re-run the dry run and have it reviewed again")
    if plan["planning_delivery_in_eligible"]:
        raise RebaselineRefused("a planning-delivery opportunity is in the manifest; refusing")
    manifest = MonitoringTransitionManifest(rebaseline_ids=frozenset(e["opportunity_id"] for e in plan["eligible"]))
    report = apply_monitoring_transition(session, manifest, dry_run=False)        # the existing engine: fails closed as a whole, ONE commit
    if not report.ok:
        raise RebaselineRefused(f"the transition engine refused: {report.summary_line()}")
    after = preview_ordinary_sync(session)
    leftover = sorted(c["opportunity_id"] for c in after["changes"] if c["opportunity_id"] in manifest.rebaseline_ids)
    return {**{k: plan[k] for k in ("plan_version", "plan_digest", "totals")}, "mode": "applied", "rebaselined_ids": sorted(report.rebaseline_applied),
            "writes": len(report.writes), "still_reported_changed_after_apply": leftover}
