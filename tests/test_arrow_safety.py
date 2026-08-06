"""Regression tests for the Planning Position Arrow-serialization hotfix.

Root cause: app.ui.site_profile_view's phase/plot Units table column mixed
raw int unit counts with str placeholders ("-"/"") across different rows of
the same pandas column - a dtype pyarrow.Table.from_pandas cannot reliably
infer one Arrow type for. Confirmed live against real multi-phase Sites
(site_id 62, 67, 179, 389, 391, 515, 528 all reproduced the exact error:
pyarrow.lib.ArrowInvalid: ("Could not convert '-' with type str: tried to
convert to int64", 'Conversion failed for column Units with type object')).

app.ui.shell.arrow_safe_count is the narrow presentation-boundary fix: it
always returns a str, so the Units column is never a mix of int and str
regardless of which phases have a known count.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pyarrow as pa
import pytest
from streamlit import dataframe_util

from app.db.models import Application, Site
from app.pipeline.phase_tracking import PHASE_STATUS_LABELS, build_phase_breakdown
from app.ui.shell import arrow_safe_count


# --- arrow_safe_count -----------------------------------------------------

def test_arrow_safe_count_known_value_becomes_a_plain_string():
    assert arrow_safe_count(245) == "245"
    assert isinstance(arrow_safe_count(245), str)


def test_arrow_safe_count_none_falls_back_to_placeholder():
    assert arrow_safe_count(None) == "—"
    assert arrow_safe_count(None, "") == ""


def test_arrow_safe_count_zero_falls_back_to_placeholder():
    """Matches the truthy `or` check the call site used before this helper
    existed - a phase recorded as delivering exactly 0 units is treated the
    same as "unknown", not silently changed by this hotfix."""
    assert arrow_safe_count(0) == "—"


def test_arrow_safe_count_custom_placeholder():
    assert arrow_safe_count(None, "") == ""
    assert arrow_safe_count(None, "n/a") == "n/a"


def test_arrow_safe_count_deterministic():
    assert arrow_safe_count(18) == arrow_safe_count(18)
    assert arrow_safe_count(None) == arrow_safe_count(None)


# --- integration: real mixed-type phase breakdown -------------------------

def _make_site(session, **kwargs) -> Site:
    site = Site(council_code="testcouncil", canonical_address="1 test street", display_address="1 Test Street", **kwargs)
    session.add(site)
    session.commit()
    return site


def _make_app(session, site_id: int, reference: str, **kwargs) -> Application:
    app = Application(council_code="testcouncil", reference=reference, site_id=site_id, **kwargs)
    session.add(app)
    session.commit()
    return app


def _mixed_unit_count_site(session) -> Site:
    """One phase with a known int unit count (from portal-text extraction)
    and one phase with none - the exact shape that broke pyarrow
    conversion before this fix, reproduced with a real Application/Site
    fixture rather than a hand-built dict."""
    site = _make_site(session)
    _make_app(
        session, site.id, "REF/1A",
        proposal="Reserved matters application for Phase 1A for the erection of 245 dwellings",
        decision="Granted", status="Decided", decision_issued_date="2024-01-10",
        application_category="reserved_matters",
    )
    _make_app(
        session, site.id, "REF/2",
        proposal="Outline application for Phase 2 residential development",
        decision=None, status="Pending", application_category="outline",
    )
    session.refresh(site)
    return site


def _phase_rows(site: Site) -> list[dict]:
    phase_breakdown = build_phase_breakdown(site.applications)
    assert len(phase_breakdown) > 1, "fixture must produce a real multi-group breakdown"
    return [{
        "Phase / plot": p["label"],
        "Units": arrow_safe_count(p.get("unit_count"), "—" if p["kind"] == "phase" else ""),
        "Status": PHASE_STATUS_LABELS[p["status"]],
        "Applications": len(p["applications"]),
    } for p in phase_breakdown]


def test_mixed_unit_count_breakdown_reproduces_a_real_int_and_placeholder_mix(session):
    site = _mixed_unit_count_site(session)
    phase_breakdown = build_phase_breakdown(site.applications)
    counts = {p["label"]: p.get("unit_count") for p in phase_breakdown}
    assert 245 in counts.values()
    assert None in counts.values()


def test_fixed_phase_rows_units_column_is_a_single_arrow_safe_dtype(session):
    site = _mixed_unit_count_site(session)
    rows = _phase_rows(site)
    df = pd.DataFrame(rows)
    assert all(isinstance(v, str) for v in df["Units"])
    # pandas: every value is `str`, so this collapses to a single dtype -
    # never "object" mixing int and str, which is what pyarrow couldn't
    # infer a type for.
    assert df["Units"].map(type).nunique() == 1


def test_fixed_phase_rows_survive_pyarrow_table_from_pandas(session):
    site = _mixed_unit_count_site(session)
    df = pd.DataFrame(_phase_rows(site))
    table = pa.Table.from_pandas(df)  # raises pyarrow.lib.ArrowInvalid before the fix
    assert table.num_rows == len(df)


def test_fixed_phase_rows_survive_streamlits_own_conversion_path(session):
    """The exact function st.dataframe calls internally
    (streamlit.dataframe_util.convert_pandas_df_to_arrow_bytes) - proves the
    fix works through Streamlit's real code path, not just a raw pyarrow
    call."""
    site = _mixed_unit_count_site(session)
    df = pd.DataFrame(_phase_rows(site))
    result = dataframe_util.convert_pandas_df_to_arrow_bytes(df)
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_fixed_phase_rows_do_not_hit_streamlits_internal_fallback(session, caplog):
    """Before the fix, Streamlit's own conversion silently caught
    ArrowInvalid and logged "Applying automatic fixes..." - i.e. it was
    masking a real internal exception on every render. After the fix, no
    exception is raised internally and no such log line appears."""
    import logging

    site = _mixed_unit_count_site(session)
    df = pd.DataFrame(_phase_rows(site))
    with caplog.at_level(logging.INFO, logger="streamlit.dataframe_util"):
        dataframe_util.convert_pandas_df_to_arrow_bytes(df)
    assert "Applying automatic fixes" not in caplog.text


def test_fixed_phase_rows_preserve_the_visible_values(session):
    """The known unit count still reads "245" and the unknown phase still
    shows the same placeholder distinction (em dash for a phase, blank for
    a plot) that existed before this hotfix - no field silently dropped or
    hidden."""
    rows = _phase_rows(_mixed_unit_count_site(session))
    units_by_label = {r["Phase / plot"]: r["Units"] for r in rows}
    assert units_by_label["Phase 1A"] == "245"
    assert units_by_label["Phase 2"] == "—"
    for r in rows:
        assert r["Status"] in PHASE_STATUS_LABELS.values()
        assert isinstance(r["Applications"], int)


def test_source_phase_breakdown_is_never_mutated_by_building_display_rows(session):
    """The presentation-only fix must never write back into the domain
    objects build_phase_breakdown returns - p["unit_count"] must stay a
    real int/None, never get coerced to a string in place."""
    site = _mixed_unit_count_site(session)
    phase_breakdown = build_phase_breakdown(site.applications)
    before = [(p["label"], p.get("unit_count"), type(p.get("unit_count"))) for p in phase_breakdown]

    _ = [{
        "Units": arrow_safe_count(p.get("unit_count"), "—" if p["kind"] == "phase" else ""),
    } for p in phase_breakdown]

    after = [(p["label"], p.get("unit_count"), type(p.get("unit_count"))) for p in phase_breakdown]
    assert before == after


def test_plot_rows_still_use_blank_placeholder_not_em_dash(session):
    """Plots never carry a unit_count of their own (see
    phase_tracking.build_phase_breakdown's own docstring) - this hotfix
    must not change that existing phase-vs-plot placeholder distinction."""
    site = _make_site(session)
    _make_app(
        session, site.id, "REF/P1",
        proposal="Reserved matters for Plot 1, erection of 245 dwellings",
        decision="Granted", status="Decided", decision_issued_date="2024-01-10",
        application_category="reserved_matters",
    )
    _make_app(
        session, site.id, "REF/P2",
        proposal="Reserved matters for Plot 2",
        decision=None, status="Pending", application_category="reserved_matters",
    )
    session.refresh(site)
    rows = _phase_rows(site)
    units_by_label = {r["Phase / plot"]: r["Units"] for r in rows}
    assert units_by_label["Plot 1"] == ""
    assert units_by_label["Plot 2"] == ""
