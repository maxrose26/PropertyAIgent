"""Gate 1 (Acquisition Monitoring Substrate) - explicit bootstrap command.

THE canonical, safe first-deployment sequence (Gate 1 amendment, Product
Owner review - this command now performs all of it, in the correct order,
as one call):

    existing DB
    -> global opportunity monitoring baseline established (every current
       opportunity is recorded as BASELINE_EXISTING - historical, never a
       "newly discovered" opportunity for any buyer)
    -> default Workspace resolved, four pilot Buyer Profiles seeded into
       it (idempotent - never overwrites an already-persisted, edited
       row)
    -> each profile's own onboarding baseline established (the existing,
       unmodified assess_buyer_fit reviews the CURRENT, now-baselined
       opportunity universe once - no AI, no score; every opportunity
       reviewed here is this buyer's historical baseline too, never later
       reported as newly discovered merely because monitoring has just
       started)

    python -m scripts.bootstrap_acquisition_monitoring

Idempotent - safe to run any number of times, including against a database
that's already fully bootstrapped and current (an already-established
global baseline is ordinary, idempotent ongoing sync; a profile whose own
baseline is already current is a cheap no-op fingerprint comparison, never
a wasted opportunity-universe re-scan).

Deliberately its own explicit command, never invoked from app.ui.common.
bootstrap() or any other ordinary request/page-load path - mirrors
scripts.migrate_schema's own "schema evolution/seeding is not a page-load
side effect" discipline exactly. Requires scripts.migrate_schema to have
already been run first (it creates the workspaces/buyer_profiles/
opportunity_monitoring_states tables this command writes to) - the
complete, canonical first-deployment procedure is exactly these two
commands, in this order, and nothing else:

    1. python -m scripts.migrate_schema
    2. python -m scripts.bootstrap_acquisition_monitoring

After that, scripts.sync_opportunity_monitoring is the SEPARATE, ONGOING
step - run on its own recurring schedule from then on, never as part of
first deployment - that detects genuinely NEW/MATERIALLY_CHANGED
opportunities from that point forward. This command performs NO OpenAI
call and writes NO planning-intelligence data - it only ever creates/
updates rows in workspaces, buyer_profiles and opportunity_monitoring_
states.
"""
from __future__ import annotations

from app.db.session import get_session
from app.policy.buyer_profile_store import bootstrap_acquisition_monitoring


def main() -> None:
    session = get_session()
    try:
        result = bootstrap_acquisition_monitoring(session)
    finally:
        session.close()

    baseline = result["global_opportunity_baseline"]
    print(
        f"[bootstrap-acquisition-monitoring] global opportunity baseline: "
        f"considered={baseline['opportunities_considered']} baseline_existing={baseline['baseline_existing']} "
        f"new={baseline['new']} materially_changed={baseline['materially_changed']} unchanged={baseline['unchanged']}"
    )
    print(f"[bootstrap-acquisition-monitoring] workspace_id={result['workspace_id']} profiles_total={result['profiles_total']}")
    if not result["profiles_onboarded_this_run"]:
        print("[bootstrap-acquisition-monitoring] every profile's baseline was already current - no further changes made.")
        return
    for profile_key in result["profiles_onboarded_this_run"]:
        summary = result["results"][profile_key].summary_line
        print(f"[bootstrap-acquisition-monitoring] onboarded {profile_key}: {summary}")


if __name__ == "__main__":
    main()
