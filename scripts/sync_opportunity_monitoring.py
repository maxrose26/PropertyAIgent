"""Gate 1 (Acquisition Monitoring Substrate) - explicit opportunity
change-detection sync command.

Rebuilds the current opportunity universe (app.reporting.opportunity_
universe.build_current_opportunity_universe - the platform's own existing,
unmodified opportunity-detection functions) and reconciles app.db.models.
OpportunityMonitoringState against it: every opportunity identity is
classified NEW / MATERIALLY_CHANGED / UNCHANGED (app.reporting.
opportunity_change.classify_opportunity_change) and the monitoring table
is updated accordingly.

    python -m scripts.sync_opportunity_monitoring

Idempotent, deterministic, bounded (see app.reporting.opportunity_universe.
DEFAULT_UNIVERSE_POOL_LIMIT), no OpenAI call, no opportunity scoring.
Requires scripts.migrate_schema to have already created the
opportunity_monitoring_states table.

NOT wired into scripts.run_intelligence_processing.py or any production
cron in this gate (Gate 1 brief, Section 22: "do NOT activate new
production scheduling in this gate unless required and clearly safe") -
this is the standalone building block Gate 2's own selective Acquisition
Agent trigger will call as a new bounded stage of that existing cron; see
the Gate 1 implementation report for exactly how that wiring would work
once approved.
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
        f"new={counts['new']} materially_changed={counts['materially_changed']} unchanged={counts['unchanged']}"
    )


if __name__ == "__main__":
    main()
