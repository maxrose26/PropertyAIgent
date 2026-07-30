"""AI-narrated PDF summary report over a filtered set of schemes.

Every number in the report (totals, counts, splits, top-N rankings) is
computed in pandas before the LLM ever sees the data - the same principle
already used by app.search.query_parser.compute_aggregate_answer: the model
writes the prose, it never computes a total or a ranking itself, so it can't
hallucinate a wrong number. The per-scheme detail table is built entirely in
Python too, for the same reason and so the report scales to any number of
schemes without an unbounded LLM call.
"""
from __future__ import annotations

import datetime as dt
import io
import json
from dataclasses import dataclass, field

import pandas as pd
from openai import OpenAI
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

MODEL = "gpt-4o-mini"

# Mirrors app.pipeline.lapse_tracking's own framing - a scheme approaching or
# past its commencement deadline is a genuine acquisition signal (the
# landowner may need to re-apply, sell, or risk losing the consent), and a
# not-yet-decided scheme is the earliest possible point to get involved
# before anyone else has committed capital.
BUYING_OPPORTUNITY_LAPSE_STATUSES = {"approaching", "lapsed"}
BUYING_OPPORTUNITY_DECISION_STATUSES = {"not_yet_decided"}


@dataclass
class AggregateStats:
    site_count: int
    total_units: int
    total_affordable_units: int
    total_private_units: int
    overall_affordable_pct: float | None
    decision_counts: dict[str, int]
    lapse_counts: dict[str, int]
    lapsing_count: int
    early_stage_count: int
    top_councils: list[tuple[str, int]]
    top_developers: list[tuple[str, int]]
    largest_schemes: list[dict] = field(default_factory=list)
    opportunity_schemes: list[dict] = field(default_factory=list)


def compute_aggregate_stats(df: pd.DataFrame, top_n: int = 5, highlight_n: int = 10) -> AggregateStats:
    """Pure pandas - no LLM call, no hallucination risk. df is the same
    site-level dataframe streamlit_app.py already builds (has Total Units/
    Affordable Units/Private Units/decision_status/lapse_status/Council/
    Developer columns)."""
    total_units = int(df["Total Units"].fillna(0).sum())
    total_affordable = int(df["Affordable Units"].fillna(0).sum())
    total_private = int(df["Private Units"].fillna(0).sum())
    overall_pct = round(100 * total_affordable / total_units, 1) if total_units else None

    decision_counts = df["decision_status"].value_counts().to_dict()
    lapse_counts = df["lapse_status"].value_counts().to_dict()
    lapsing_count = int(df["lapse_status"].isin(BUYING_OPPORTUNITY_LAPSE_STATUSES).sum())
    early_stage_count = int(df["decision_status"].isin(BUYING_OPPORTUNITY_DECISION_STATUSES).sum())

    def _top(col: str) -> list[tuple[str, int]]:
        normalised = df[col].astype(str).str.strip().str.lower()
        present = df[df[col].notna() & ~normalised.isin({"", "none", "nan", "n/a"})]
        counts = present.groupby(col).size().sort_values(ascending=False)
        return [(name, int(n)) for name, n in counts.head(top_n).items()]

    largest = (
        df.dropna(subset=["Total Units"])
        .sort_values("Total Units", ascending=False)
        .head(highlight_n)
        .to_dict("records")
    )
    opportunities = (
        df[df["lapse_status"].isin(BUYING_OPPORTUNITY_LAPSE_STATUSES) | df["decision_status"].isin(BUYING_OPPORTUNITY_DECISION_STATUSES)]
        .sort_values("Total Units", ascending=False, na_position="last")
        .head(highlight_n)
        .to_dict("records")
    )

    return AggregateStats(
        site_count=len(df),
        total_units=total_units,
        total_affordable_units=total_affordable,
        total_private_units=total_private,
        overall_affordable_pct=overall_pct,
        decision_counts=decision_counts,
        lapse_counts=lapse_counts,
        lapsing_count=lapsing_count,
        early_stage_count=early_stage_count,
        top_councils=_top("Council"),
        top_developers=_top("Developer"),
        largest_schemes=largest,
        opportunity_schemes=opportunities,
    )


def _or_unknown(value, fallback: str = "not identified") -> str:
    """`value or fallback` breaks when value is float('nan') - nan is
    truthy in Python, so the fallback never kicks in. pandas silently turns
    None into nan on any df.to_dict("records") round-trip (confirmed: the
    largest_schemes/opportunity_schemes lists built in
    compute_aggregate_stats always go through one), so this bit for real
    schemes with a missing developer/landowner - the LLM narrative prompt
    would embed the literal string "nan" as if it were a real value."""
    return str(value) if pd.notna(value) and value not in ("", None) else fallback


def _fmt_scheme(row: dict) -> str:
    units = row.get("Total Units")
    units_str = f"{int(units)} units" if pd.notna(units) else "unit count unknown"
    return (
        f"{row.get('Address', 'Unknown address')} ({row.get('Council', '?')}) - {units_str}, "
        f"developer: {_or_unknown(row.get('Developer'))}, "
        f"decision: {row.get('Decision Status', row.get('decision_status', '?'))}, "
        f"lapse risk: {row.get('Lapse Risk', row.get('lapse_status', '?'))}"
    )


def build_narrative_prompt(stats: AggregateStats, search_description: str | None) -> str:
    top_councils_str = ", ".join(f"{name} ({n})" for name, n in stats.top_councils) or "none"
    top_developers_str = ", ".join(f"{name} ({n})" for name, n in stats.top_developers) or "none"
    largest_str = "\n".join(f"- {_fmt_scheme(r)}" for r in stats.largest_schemes) or "none"
    opportunities_str = "\n".join(f"- {_fmt_scheme(r)}" for r in stats.opportunity_schemes) or "none"

    scope_line = f'The user searched for: "{search_description}"' if search_description else "No specific search query - this covers the currently filtered result set."

    return f"""
You are writing a property-sourcing summary report for a UK residential
land/planning acquisition professional. Every number below is already
correct and final - restate them accurately, never recalculate, round, or
invent a different figure.

{scope_line}

VERIFIED AGGREGATE FIGURES (do not alter these numbers):
- Schemes in this report: {stats.site_count}
- Total units across all schemes: {stats.total_units}
- Total affordable units: {stats.total_affordable_units} ({stats.overall_affordable_pct}% of total, where known)
- Total private units: {stats.total_private_units}
- Decision status breakdown: {stats.decision_counts}
- Lapse/commencement risk breakdown: {stats.lapse_counts}
- Schemes approaching or past their commencement deadline (landowner may need to sell or re-apply): {stats.lapsing_count}
- Schemes not yet decided (earliest-stage opportunity, nothing committed yet): {stats.early_stage_count}
- Most active councils by scheme count: {top_councils_str}
- Most active developers by scheme count: {top_developers_str}

LARGEST SCHEMES IN THIS SET (by unit count):
{largest_str}

FLAGGED BUYING OPPORTUNITIES (lapsing/approaching deadline, or not yet decided):
{opportunities_str}

Write two fields, each 2-4 sentences of genuine analytical prose, not a
restatement of the list:

executive_summary: Synthesise the overall picture - scale of opportunity
(units/affordable split), where activity is concentrated, and the general
mix of decision stages.

buying_opportunities_and_risks: Explain what the lapsing/approaching-deadline
schemes mean as an acquisition signal (the landowner may need to sell or
re-apply rather than lose the consent), and what the not-yet-decided schemes
represent as an earlier-stage opportunity. Name a small number of the most
notable specific schemes from the flagged list above, not all of them.
"""


NARRATIVE_SCHEMA = {
    "name": "report_narrative",
    "schema": {
        "type": "object",
        "properties": {
            "executive_summary": {"type": "string"},
            "buying_opportunities_and_risks": {"type": "string"},
        },
        "required": ["executive_summary", "buying_opportunities_and_risks"],
        "additionalProperties": False,
    },
}


def generate_narrative(client: OpenAI, stats: AggregateStats, search_description: str | None = None) -> dict[str, str]:
    """One structured-output LLM call - returns {"EXECUTIVE SUMMARY": "...", "BUYING OPPORTUNITIES AND RISKS": "..."}.

    Uses the same client.responses.create(..., json_schema, strict=True)
    pattern as app.search.query_parser.parse_query, rather than the
    plain-text "SECTION NAME:"-line format tried first - confirmed against
    real calls that gpt-4o-mini puts the header and body text on the same
    line about as often as it puts them on separate lines, so an exact
    line-match parser silently dropped whole sections (returned {}) on a
    real live report rather than raising an error."""
    prompt = build_narrative_prompt(stats, search_description)
    response = client.responses.create(
        model=MODEL, input=prompt,
        text={"format": {"type": "json_schema", "name": NARRATIVE_SCHEMA["name"], "schema": NARRATIVE_SCHEMA["schema"], "strict": True}},
    )
    result = json.loads(response.output_text)
    return {
        "EXECUTIVE SUMMARY": result["executive_summary"],
        "BUYING OPPORTUNITIES AND RISKS": result["buying_opportunities_and_risks"],
    }


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=20, spaceAfter=4))
    styles.add(ParagraphStyle("ReportSubtitle", parent=styles["Normal"], fontSize=10, textColor=colors.grey, spaceAfter=16))
    styles.add(ParagraphStyle("SectionHeading", parent=styles["Heading2"], spaceBefore=18, spaceAfter=8))
    styles.add(ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, leading=14, alignment=TA_JUSTIFY, spaceAfter=8))
    styles.add(ParagraphStyle("SchemeHeading", parent=styles["Heading4"], spaceBefore=10, spaceAfter=2))
    styles.add(ParagraphStyle("SchemeBody", parent=styles["Normal"], fontSize=9, leading=12))
    return styles


# Plain-text (no emoji - reportlab's default Helvetica font has no emoji
# glyphs) labels for the stats table specifically, kept separate from
# LAPSE_STATUS_LABELS (which is used in the Streamlit UI, where emoji render
# fine) rather than deriving one from the other by string-stripping.
_LAPSE_STATUS_TEXT_LABELS = {
    "lapsed": "Permission may have lapsed",
    "approaching": "Commencement deadline approaching",
    "underway": "Build underway",
    "safe": "OK",
    "not_granted": "Not yet granted",
    "unknown": "Unknown",
}

# Same plain-text-for-PDF reasoning as _LAPSE_STATUS_TEXT_LABELS above,
# mirroring app.pipeline.lapse_tracking.BUILD_STATUS_LABELS without its
# emoji.
_BUILD_STATUS_TEXT_LABELS = {
    "underway": "Underway (filing detected)",
    "complete": "Complete (EPC)",
    "partially_complete": "Partially complete (EPC)",
    "no_completions_yet": "No completions yet (0 EPCs - may still be under construction)",
    "unknown": "Unknown",
}


def _stats_table(stats: AggregateStats, styles) -> Table:
    def _labelled(counts: dict[str, int], labels: dict[str, str]) -> str:
        return ", ".join(f"{labels.get(k, k)}: {v}" for k, v in counts.items()) or "-"

    from app.pipeline.lapse_tracking import DECISION_STATUS_LABELS

    label_style = ParagraphStyle("StatLabel", parent=styles["Normal"], fontSize=9, fontName="Helvetica-Bold", textColor=colors.HexColor("#555555"), leading=12)
    value_style = ParagraphStyle("StatValue", parent=styles["Normal"], fontSize=9, leading=12)

    rows = [
        ("Schemes", str(stats.site_count)),
        ("Total units", f"{stats.total_units:,}"),
        ("Affordable units", f"{stats.total_affordable_units:,}" + (f" ({stats.overall_affordable_pct}%)" if stats.overall_affordable_pct is not None else "")),
        ("Private units", f"{stats.total_private_units:,}"),
        ("Decision status", _labelled(stats.decision_counts, DECISION_STATUS_LABELS)),
        ("Lapse/commencement risk", _labelled(stats.lapse_counts, _LAPSE_STATUS_TEXT_LABELS)),
        ("Buying opportunities flagged", f"{stats.lapsing_count} lapsing/approaching + {stats.early_stage_count} not yet decided"),
    ]
    data = [[Paragraph(label, label_style), Paragraph(value, value_style)] for label, value in rows]
    table = Table(data, colWidths=[55 * mm, 115 * mm])
    table.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def render_pdf(report_rows: list[dict], stats: AggregateStats, narrative: dict[str, str], search_description: str | None = None) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
    )
    styles = _styles()
    story = []

    story.append(Paragraph("UK Planning Deal Finder — Scheme Summary Report", styles["ReportTitle"]))
    subtitle = f"Generated {dt.datetime.now():%d %b %Y %H:%M} · {stats.site_count} schemes"
    if search_description:
        subtitle += f' · Search: "{search_description}"'
    story.append(Paragraph(subtitle, styles["ReportSubtitle"]))

    story.append(Paragraph("Executive Summary", styles["SectionHeading"]))
    story.append(Paragraph(narrative.get("EXECUTIVE SUMMARY", ""), styles["Body"]))

    story.append(Paragraph("Aggregate Statistics", styles["SectionHeading"]))
    story.append(_stats_table(stats, styles))

    story.append(Paragraph("Buying Opportunities and Risks", styles["SectionHeading"]))
    story.append(Paragraph(narrative.get("BUYING OPPORTUNITIES AND RISKS", ""), styles["Body"]))

    story.append(PageBreak())
    story.append(Paragraph(f"Scheme Detail ({len(report_rows)})", styles["SectionHeading"]))

    for row in report_rows:
        is_opportunity = row.get("decision_status") in BUYING_OPPORTUNITY_DECISION_STATUSES or row.get("lapse_status") in BUYING_OPPORTUNITY_LAPSE_STATUSES
        heading_text = row.get("Address") or "Unknown address"
        if is_opportunity:
            heading_text += "  ⚑ Buying opportunity"
        units = row.get("Total Units")
        units_str = f"{int(units)}" if pd.notna(units) else "unknown"
        affordable = row.get("Affordable Units")
        affordable_str = f"{int(affordable)}" if pd.notna(affordable) else "unknown"
        affordable_pct = row.get("Affordable %")
        if pd.notna(affordable_pct):
            affordable_str += f" ({affordable_pct}%)"
        build_status_text = _BUILD_STATUS_TEXT_LABELS.get(row.get("build_status"), row.get("Build Status", "Unknown"))

        body_lines = [
            f"<b>Council:</b> {row.get('Council', '')} &nbsp;&nbsp; <b>Reference(s):</b> {row.get('References', '')}",
            f"<b>Total units:</b> {units_str} &nbsp;&nbsp; <b>Affordable:</b> {affordable_str} &nbsp;&nbsp; <b>Housing type:</b> {row.get('Housing Type', '')}",
            f"<b>Developer:</b> {_or_unknown(row.get('Developer'))} &nbsp;&nbsp; <b>Landowner:</b> {_or_unknown(row.get('Landowner'))}",
            f"<b>Planning agent:</b> {_or_unknown(row.get('Planning Agent'))}",
            f"<b>Decision status:</b> {row.get('Decision Status', '')} &nbsp;&nbsp; <b>Decision date:</b> {_or_unknown(row.get('Decision Date'), 'not yet decided')}",
            f"<b>Lapse risk:</b> {row.get('Lapse Risk', '')} &nbsp;&nbsp; <b>Build status:</b> {build_status_text}",
        ]
        block = [Paragraph(heading_text, styles["SchemeHeading"])]
        block.extend(Paragraph(line, styles["SchemeBody"]) for line in body_lines)

        app_details = row.get("Applications Detail") or []
        if app_details:
            app_style = ParagraphStyle("AppDetail", parent=styles["SchemeBody"], leftIndent=10, spaceBefore=2)
            block.append(Paragraph("<b>Applications:</b>", app_style))
            for detail in app_details:
                proposal = detail.get("Proposal") or "no proposal text extracted"
                block.append(Paragraph(
                    f"- <b>{detail.get('Reference', '?')}</b> "
                    f"({_or_unknown(detail.get('Received'), 'date unknown')}, {_or_unknown(detail.get('Decision'), 'undecided')}): "
                    f"{proposal}",
                    app_style,
                ))

        story.append(KeepTogether(block))
        story.append(Spacer(1, 4))

    doc.build(story)
    return buffer.getvalue()
