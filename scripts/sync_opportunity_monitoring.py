"""Gate 1 (Acquisition Monitoring Substrate) - explicit, ONGOING
opportunity change-detection sync command.

Rebuilds the COMPLETE current opportunity universe (app.reporting.
opportunity_universe.build_current_opportunity_universe - the platform's
own existing, unmodified opportunity-detection functions; this never
silently truncates, however large the universe grows - see that module's
own "COMPLETENESS" docstring section) and reconciles app.db.models.
OpportunityMonitoringState against it: every opportunity identity is
classified NEW / MATERIALLY_CHANGED / UNCHANGED (app.reporting.
opportunity_change.classify_opportunity_change) and the monitoring table
is updated accordingly.

    python -m scripts.sync_opportunity_monitoring

Idempotent, deterministic, no OpenAI call, no opportunity scoring. Requires
scripts.migrate_schema to have already created the opportunity_monitoring_
states table.

NOT part of first deployment - scripts.bootstrap_acquisition_monitoring
already establishes the global opportunity baseline (BASELINE_EXISTING)
as its own first step, so every opportunity already present in the
database at first deployment is correctly recorded as historical, not
"newly discovered", before this command ever needs to run. This command
is the SEPARATE, ONGOING step: run it on its own recurring schedule from
then on (e.g. as a new bounded stage of scripts.run_intelligence_
processing.py's existing daily cron - not wired in during this gate, see
the Gate 1 implementation report) to detect genuinely new or materially
changed opportunities as the underlying planning intelligence changes.
Safe to run even if scripts.bootstrap_acquisition_monitoring has not been
run yet - sync_opportunity_monitoring_state self-detects an empty
monitoring table and establishes the baseline correctly (BASELINE_
EXISTING, not NEW) either way; it never relies on being called in a
particular order relative to bootstrap.

NOT wired into scripts.run_intelligence_processing.py or any production
cron in this gate (Gate 1 brief, Section 22: "do NOT activate new
production scheduling in this gate unless required and clearly safe").
"""
from __future__ import annotations

from app.db.session import get_session
from app.reporting.opportunity_change import sync_opportunity_monitoring_state


def main() -> None:
    session = get_session()
    try:
        counts = sync_opportunity_monitoring_state(session)
    finally:
        session.close()

    print(
        f"[sync-opportunity-monitoring] considered={counts['opportunities_considered']} "
        f"baseline_existing={counts['baseline_existing']} new={counts['new']} "
        f"materially_changed={counts['materially_changed']} unchanged={counts['unchanged']}"
    )


if __name__ == "__main__":
    main()
