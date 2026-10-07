"""Stage 2.5B V8-B: every residual SURFACE follows the ladder - R1 may show a derived count with caveats (feed/presentation, covered in test_v8b_residual_feed), R2 shows investigation
context with NO trusted number, R3 shows no residual proposition. The internal Stage 3A subtraction stays internal (a trigger, never a quantity). AI grounding is evidence-safe.
Offline and deterministic: prompts are built and inspected, no model is called."""
from __future__ import annotations

import dataclasses
import inspect
import re
from types import SimpleNamespace

import pytest

import app.reporting.allocation_intelligence_summary as ais
import app.reporting.cross_site_intelligence as csi
import app.reporting.residual_opportunity as ro
from app.reporting import allocation_report as ar
from tests.test_cross_site_intelligence import _make_context, _make_entry, _make_web_context

PARTIAL = dict(development_coverage_classification="PARTIAL_COVERAGE", capacity_accounting_status="ok", linked_application_count=1, indicative_residual_capacity=4321)
NUMBER = re.compile(r"4,?321")


def entry(**kw):
    return dataclasses.replace(_make_entry(1, capacity_value=10000, linked_application_count=1), **{**PARTIAL, **kw})


def test_report_csv_and_rows_show_r2_context_never_the_subtraction():
    partial, none = entry(), entry(development_coverage_classification="FULLY_ACCOUNTED_FOR")
    context = _make_context([partial])
    row = ar.to_csv_rows(context)[0]
    assert row["Potential Residual Scope"] == ro.POTENTIAL_RESIDUAL_SHORT and "Indicative Residual Capacity" not in row and "Indicative Residual Capacity" not in ar.CSV_COLUMNS
    assert not NUMBER.search(" ".join(str(v) for v in row.values()))
    assert ar.to_csv_rows(_make_context([none]))[0]["Potential Residual Scope"] == ro.NO_POTENTIAL_RESIDUAL_SHORT
    assert not NUMBER.search(ar.to_csv_bytes(context).decode("utf-8"))


def test_pdf_renders_no_residual_quantity():
    from app.reporting import allocation_report_pdf as pdf
    source = inspect.getsource(pdf)
    assert "indicative_residual_capacity" not in source and "Indicative residual" not in source and "Residual Capacity" not in source
    assert "potential_residual_scope_text" in source


def test_shortlist_and_local_plan_pages_do_not_show_the_subtraction_as_a_quantity():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    shortlist = (root / "app/ui/pages/3b_Shortlist.py").read_text(encoding="utf-8")
    assert "Indicative residual" not in shortlist and "indicative_residual_capacity" not in shortlist and "potential_residual_scope_text" in shortlist
    plans = (root / "app/ui/pages/3_Local_Plan_Sites.py").read_text(encoding="utf-8")
    assert "homes of allocation capacity are not" not in plans and "residual_section.residual_capacity:" not in plans and "ALLOCATION_R2_TEXT" in plans


def test_cross_site_prompt_is_number_free_for_residuals_and_forbids_subtraction():
    partial = entry()
    prompt = csi.build_cross_site_prompt(_make_context([partial]), _make_web_context())
    assert "potential residual scope identified - investigate (not quantified)" in prompt
    assert not NUMBER.search(prompt) and "indicative residual capacity" not in prompt.lower()
    assert "NEVER subtract planning-application" in prompt and "no availability, ownership, title, geometry or further-phase inference" in prompt
    quiet = csi.build_cross_site_prompt(_make_context([entry(development_coverage_classification="FULLY_ACCOUNTED_FOR")]), _make_web_context())
    assert "potential residual scope identified" not in quiet
    assert csi.PROMPT_VERSION == "cross-site-intelligence-v2"


def test_cross_site_validator_no_longer_whitelists_the_residual_number():
    context = _make_context([entry()])
    web = _make_web_context()
    from tests.test_cross_site_intelligence import _good_output
    assert "4321" not in csi._allowed_numbers(context, web) and "4,321" not in csi._allowed_numbers(context, web)
    for text in ("About 4,321 homes of residual capacity may be available.", "4321 homes remain unaccounted for."):
        valid, problems = csi.validate_cross_site_output(context, web, _good_output(executive_summary=text))
        assert not valid and problems, problems                                                  # an ungrounded residual number is rejected


def _allocation_context(classification="PARTIAL_COVERAGE", status="ok", residual=4321, linked=1):
    return SimpleNamespace(development_coverage_classification=classification, capacity_accounting_status=status, indicative_residual_capacity=residual,
                           number_of_linked_applications=linked)


def test_allocation_summary_grounding_gives_r2_context_and_never_the_number():
    r2 = ais._potential_residual_prompt_line(_allocation_context())
    assert "investigation context only" in r2 and not NUMBER.search(r2) and "available" not in r2.replace("availability", "")
    assert ais._potential_residual_prompt_line(_allocation_context(classification="FULLY_ACCOUNTED_FOR")).startswith("none indicated")      # R3: no proposition
    assert ais._potential_residual_prompt_line(_allocation_context(status="review_required")).startswith("none indicated")
    assert ais._potential_residual_prompt_line(_allocation_context(residual=None)).startswith("none indicated")
    template = inspect.getsource(ais.build_summary_prompt)
    assert "indicative_residual_capacity" not in template and "Indicative residual" not in template and "NEVER subtract planning-application" in template
    assert ais.PROMPT_VERSION == "allocation-intelligence-summary-v9"
    validator_text = inspect.getsource(ais)
    assert "_add(context.indicative_residual_capacity)" not in validator_text                 # the residual number is not a grounded, citable figure any more


def test_internal_coverage_arithmetic_remains_internal_and_unmodified():
    from app.reporting.allocation_development_coverage import DevelopmentCoverageResult
    assert {"indicative_residual_capacity", "development_coverage_percentage"} <= {f.name for f in dataclasses.fields(DevelopmentCoverageResult)}
    assert not re.search(r"residual|remaining|available", ro.POTENTIAL_RESIDUAL_SHORT.replace("residual scope", ""), re.I)


def test_the_complete_v8_expectation_table_is_unapproved_complete_and_matches_the_live_evaluation():
    from benchmark.v8_expectation_table import build_v8_expectation_table, to_markdown
    table = build_v8_expectation_table()
    assert table["approved_by_product_owner"] is False and table["disagreements"] == [] and table["unexpected_regressions"] == []
    assert len(table["rows"]) == 24 and [r["case_no"] for r in table["rows"]] == list(range(1, 25))
    assert all(r["approved_by_product_owner"] is False and r["prohibited_inferences"] and r["rationale"] for r in table["rows"])
    routes = {r["route"] for r in table["rows"]}
    assert "STRATEGIC_ALLOCATION" in routes and "RESIDUAL_OPPORTUNITY" in routes
    assert "R15_qualified_500_300" in to_markdown(table)
