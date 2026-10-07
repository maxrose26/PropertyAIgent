"""V7C-1 - READ-ONLY preview of the ordinary opportunity monitoring sync.

    python -m scripts.preview_opportunity_monitoring_sync

Answers "if the ordinary sync ran against exactly this universe and monitoring state, what would it do?" and prints a deterministic JSON report (counts by predicted
classification and detector, untracked/retired ids, per-opportunity changes with fingerprints) for REVIEW and for building a hand-reviewed Category A/B/C transition
manifest. It performs ZERO writes (selects only), calls no model, sends no alert, and has NO apply mode: the existing scripts.sync_opportunity_monitoring remains the one
write path, and both go through the same planner (app.reporting.opportunity_change._build_sync_plan -> plan_opportunity_changes).

Operator-authorised launch only (explicit command identity and scope `launch:preview_opportunity_monitoring_sync`). Production execution needs separate REVIEW authority.
"""
from __future__ import annotations

import json

from app.db.session import get_session
from app.reporting.opportunity_change import preview_ordinary_sync
from app.security.cli import authorised_cli


@authorised_cli('preview_opportunity_monitoring_sync')
def main() -> None:
    session = get_session()
    try:
        report = preview_ordinary_sync(session)
    finally:
        session.close()
    print(json.dumps(report, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
