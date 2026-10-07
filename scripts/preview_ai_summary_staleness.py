"""v8 production transition - READ-ONLY census of persisted allocation AI summaries against the current prompt version.

    python -m scripts.preview_ai_summary_staleness

Counts (selects only; no model call, no regeneration, no write, no context rebuild) how many ``AllocationIntelligenceSummary`` rows were generated under an OLDER prompt version (so the
v8 allocation-summary prompt change makes them stale), how many have a displayed narrative, and how many of those narratives mention residual / unaccounted capacity wording that the v8
prompt contract no longer allows a model to state. Prints a deterministic JSON report (allocation ids only; no narrative text). The cross-site report summary is generated on demand and is
not persisted, so there is nothing to count for it. Operator-authorised launch only (`launch:preview_ai_summary_staleness`). Production execution needs separate REVIEW authority.
"""
from __future__ import annotations

import json
import re

from sqlalchemy import select

from app.db.models import AllocationIntelligenceSummary
from app.reporting.allocation_intelligence_summary import PROMPT_VERSION
from app.security.cli import authorised_cli

RESIDUAL_WORDING = re.compile(r"residual|unaccounted|not (yet )?(currently )?accounted for|remaining (homes|capacity|units|land)", re.I)
NARRATIVE_FIELDS = ("headline", "overview", "key_points", "key_uncertainties", "investigation_priorities")


def build_staleness_report(session) -> dict:
    rows = session.execute(select(AllocationIntelligenceSummary).order_by(AllocationIntelligenceSummary.allocation_id)).scalars().all()
    by_version: dict[str, int] = {}
    stale_with_narrative, stale_residual_wording, current_with_narrative = [], [], []
    for row in rows:
        version = row.prompt_version or "(none)"
        by_version[version] = by_version.get(version, 0) + 1
        displayed = bool(row.headline)
        stale_by_prompt = (row.prompt_version != PROMPT_VERSION)
        if displayed and stale_by_prompt:
            stale_with_narrative.append(row.allocation_id)
            text = " ".join(str(getattr(row, field) or "") for field in NARRATIVE_FIELDS)
            if RESIDUAL_WORDING.search(text):
                stale_residual_wording.append(row.allocation_id)
        elif displayed:
            current_with_narrative.append(row.allocation_id)
    return {
        "read_only": True, "current_prompt_version": PROMPT_VERSION, "model_calls": 0,
        "summary_rows": len(rows), "rows_by_prompt_version": {k: by_version[k] for k in sorted(by_version)},
        "stale_by_prompt_version_with_displayed_narrative": len(stale_with_narrative), "stale_allocation_ids": sorted(stale_with_narrative),
        "stale_narratives_mentioning_residual_wording": len(stale_residual_wording), "stale_residual_wording_allocation_ids": sorted(stale_residual_wording),
        "current_version_with_displayed_narrative": len(current_with_narrative),
        "cross_site_summary": "generated on demand, not persisted: nothing to count",
        "regeneration": "paid model call; NOT performed by this command",
    }


@authorised_cli('preview_ai_summary_staleness')
def main() -> None:
    from app.db.session import get_session
    session = get_session()
    try:
        report = build_staleness_report(session)
    finally:
        session.close()
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
