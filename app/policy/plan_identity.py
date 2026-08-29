"""Config-driven plan identity/alias resolution (LPDI V1 Gate 2A, "Multi-Plan
Attribution & Same-Plan Evidence Validation Hardening").

Two related, generic (never per-council-hardcoded) problems this solves:

1. REPORT ATTRIBUTION (see app.policy.plan_attribution): when a council has
   more than one LocalPlan - a genuine joint plan like Places for Everyone,
   or two entirely separate plans like Bury's own emerging plan and PfE -
   which specific plan does a discovered report/document belong to?
   Explicit report/source titles often name the plan by one of several
   conventional labels (a full formal title, a shortened title, an
   acronym) - this module lets that be matched deterministically against
   config, rather than guessed or hardcoded per authority.

2. SAME-PLAN FACT VALIDATION (see app.policy.evidence_validation): a fact's
   supporting excerpt can be entirely accurate about a value while
   describing a DIFFERENT, sibling planning document (specifications/018's
   Salford SLP:CSA/SLP:DMP finding). Recognising that requires knowing what
   a sibling plan's own name/aliases are - including for a sibling plan
   that has no LocalPlan row of its own yet (an "identity-only" entry,
   config/plan_aliases.yaml's plan_name=null case).

config/plan_aliases.yaml is the single source of truth for both. An
identity entry with plan_name/plan_version set is bound to a real LocalPlan
row (matched the same way config/joint_plans.yaml matches its own entries -
exact (council_code, plan_name, plan_version) triple); an entry with
plan_name=null is identity-only, existing purely so its aliases can be
recognised as "a different, real plan" even though nothing about it is
ingested in this platform yet.

Every plan - even one with zero config entry - gets a generic single-alias
fallback: its own plan_name. This is what makes the mechanism safe by
construction for every authority not explicitly configured here: with no
config at all, alias matching degrades to exact-plan_name matching, and
sibling-group detection returns no groups (nothing to conflict with)."""
from __future__ import annotations

from pathlib import Path

import yaml

from app.db.models import LocalPlan

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLAN_ALIASES_YAML = PROJECT_ROOT / "config" / "plan_aliases.yaml"


def load_plan_identities(path: Path = PLAN_ALIASES_YAML) -> list[dict]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("plan_identities", [])


def identities_for_council(council_code: str, config: list[dict] | None = None) -> list[dict]:
    config = config if config is not None else load_plan_identities()
    return [entry for entry in config if entry.get("council_code") == council_code]


def _find_identity_entry(plan: LocalPlan, config: list[dict] | None = None) -> dict | None:
    """Matches plan against config, preferring the exact
    (council_code, plan_name, plan_version) triple app.policy.joint_plans.
    find_joint_plan_entry itself uses, but falling back to a
    (council_code, plan_name) match (ignoring plan_version) when no exact
    triple matches - a known, real, already-documented risk in this
    codebase (specifications/017's own note on Salford's plan_version
    string not always matching the live database value one-for-one).
    Still fully deterministic string matching, never fuzzy/semantic - this
    fallback exists specifically so a plan_version drift can never cause
    sibling_alias_groups to mistake a plan's OWN identity entry for a
    sibling's (which would otherwise wrongly treat the plan's own name as
    "a different plan" and block its own genuine evidence). A plan with no
    matching entry at all simply has no configured aliases, not an
    error."""
    config = config if config is not None else load_plan_identities()
    for entry in config:
        if (
            entry.get("council_code") == plan.council_code
            and entry.get("plan_name") == plan.plan_name
            and entry.get("plan_version") == plan.plan_version
        ):
            return entry
    for entry in config:
        if entry.get("council_code") == plan.council_code and entry.get("plan_name") == plan.plan_name:
            return entry
    return None


def aliases_for_plan(plan: LocalPlan, config: list[dict] | None = None) -> list[str]:
    """Every string this specific plan is known to be called - its
    configured aliases if any exist, always including its own plan_name as
    a guaranteed generic fallback (so a plan with zero config still matches
    its own exact name)."""
    entry = _find_identity_entry(plan, config)
    aliases = list(entry.get("aliases", [])) if entry else []
    if plan.plan_name and plan.plan_name not in aliases:
        aliases.append(plan.plan_name)
    return aliases


def sibling_alias_groups(plan: LocalPlan, config: list[dict] | None = None) -> list[list[str]]:
    """Alias groups for every OTHER known plan identity for this plan's
    council - real LocalPlan-backed siblings (other rows sharing
    council_code, e.g. Bury Local Plan vs Places for Everyone) AND
    identity-only siblings that have no LocalPlan row at all yet (e.g.
    Salford's SLP:DMP) - used only to recognise "this excerpt names a
    different plan", never to create or imply a new LocalPlan."""
    config = config if config is not None else load_plan_identities()
    own_entry = _find_identity_entry(plan, config)
    own_key = own_entry.get("key") if own_entry else None

    groups: list[list[str]] = []
    seen_keys: set[str] = set()
    for entry in identities_for_council(plan.council_code, config):
        key = entry.get("key")
        if key == own_key or key in seen_keys:
            continue
        aliases = list(entry.get("aliases", []))
        if entry.get("plan_name") and entry["plan_name"] not in aliases:
            aliases.append(entry["plan_name"])
        if aliases:
            groups.append(aliases)
            seen_keys.add(key)
    return groups
