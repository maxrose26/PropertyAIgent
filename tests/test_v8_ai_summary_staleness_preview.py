"""v8 production transition: the READ-ONLY AI-summary staleness census (no model call, no write)."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import event

from app.db.models import AllocationIntelligenceSummary, LocalPlan, LocalPlanSite
from app.reporting.allocation_intelligence_summary import PROMPT_VERSION
from scripts.preview_ai_summary_staleness import build_staleness_report

ROOT = Path(__file__).resolve().parents[1]


def _allocation(session, n):
    plan = session.query(LocalPlan).first()
    if plan is None:
        plan = LocalPlan(council_code="t", plan_name="P", status="adopted", raw_status="adopted")
        session.add(plan)
        session.commit()
    a = LocalPlanSite(council_code="t", local_plan_id=plan.id, policy_reference=f"R{n}", site_name=f"A{n}", plan_name="P", plan_status="adopted", minimum_dwellings=100)
    session.add(a)
    session.commit()
    return a


def _summary(session, allocation, version, headline="H", overview="O"):
    session.add(AllocationIntelligenceSummary(allocation_id=allocation.id, headline=headline, overview=overview, prompt_version=version, status="ok"))
    session.commit()


def test_report_counts_stale_summaries_and_residual_wording_without_writing(session):
    a1, a2, a3, a4 = (_allocation(session, i) for i in range(1, 5))
    _summary(session, a1, "allocation-intelligence-summary-v8", overview="About 400 homes of indicative residual capacity remain.")
    _summary(session, a2, "allocation-intelligence-summary-v8", overview="A plain summary.")
    _summary(session, a3, PROMPT_VERSION)
    session.add(AllocationIntelligenceSummary(allocation_id=a4.id, headline=None, prompt_version="allocation-intelligence-summary-v7", status="error"))
    session.commit()
    statements = []
    event.listen(session.get_bind(), "before_cursor_execute", lambda conn, cur, stmt, *a: statements.append(stmt))
    report = build_staleness_report(session)
    assert all(s.lstrip().upper().startswith(("SELECT", "PRAGMA", "WITH")) for s in statements)
    assert report["summary_rows"] == 4 and report["model_calls"] == 0 and report["read_only"] is True
    assert report["stale_by_prompt_version_with_displayed_narrative"] == 2 and report["stale_allocation_ids"] == sorted([a1.id, a2.id])
    assert report["stale_narratives_mentioning_residual_wording"] == 1 and report["stale_residual_wording_allocation_ids"] == [a1.id]
    assert report["current_version_with_displayed_narrative"] == 1
    assert report["rows_by_prompt_version"][PROMPT_VERSION] == 1 and json.dumps(report)
    assert "indicative residual" not in json.dumps(report)                                         # ids and counts only: no narrative text


def test_cli_registered_authorised_and_has_no_model_or_write_path():
    manifest = json.loads((ROOT / "verification/stage1_cli_manifest.json").read_text(encoding="utf-8"))
    assert manifest["scripts/preview_ai_summary_staleness.py"] == {"command": "preview_ai_summary_staleness", "required_scope": "launch:preview_ai_summary_staleness"}
    source = (ROOT / "scripts/preview_ai_summary_staleness.py").read_text(encoding="utf-8")
    assert "@authorised_cli('preview_ai_summary_staleness')" in source
    for forbidden in ("openai", "OpenAI(", "generate_allocation_intelligence_summary", "session.add", "session.commit", ".delete("):
        assert forbidden not in source.replace("no model call", ""), forbidden
