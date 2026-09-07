"""Gate 1 (Acquisition Monitoring Substrate) - explicit bootstrap command.

Resolves/creates the single default Workspace, seeds the four existing
pilot Buyer Profiles into it (idempotent - never overwrites an
already-persisted, possibly edited row), and runs the deterministic
onboarding baseline (app.policy.buyer_profile_store.run_buyer_onboarding_
baseline - the existing, unmodified assess_buyer_fit, no AI, no score)
for every profile that has never been onboarded, or whose own mandate has
genuinely changed since its last baseline.

    python -m scripts.bootstrap_acquisition_monitoring

Idempotent - safe to run any number of times, including against a database
that's already fully bootstrapped and current (every profile's baseline
already current is a cheap no-op fingerprint comparison, never a wasted
opportunity-universe re-scan).

Deliberately its own explicit command, never invoked from app.ui.common.
bootstrap() or any other ordinary request/page-load path - mirrors
scripts.migrate_schema's own "schema evolution/seeding is not a page-load
side effect" discipline exactly. Requires scripts.migrate_schema to have
already been run first (it creates the workspaces/buyer_profiles/
opportunity_monitoring_states tables this command writes to) - run in that
order:

    1. python -m scripts.migrate_schema
    2. python -m scripts.bootstrap_acquisition_monitoring

This command performs NO OpenAI call and writes NO planning-intelligence
data - it only ever creates/updates rows in workspaces and buyer_profiles.
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

    print(f"[bootstrap-acquisition-monitoring] workspace_id={result['workspace_id']} profiles_total={result['profiles_total']}")
    if not result["profiles_onboarded_this_run"]:
        print("[bootstrap-acquisition-monitoring] every profile's baseline was already current - no changes made.")
        return
    for profile_key in result["profiles_onboarded_this_run"]:
        summary = result["results"][profile_key].summary_line
        print(f"[bootstrap-acquisition-monitoring] onboarded {profile_key}: {summary}")


if __name__ == "__main__":
    main()
