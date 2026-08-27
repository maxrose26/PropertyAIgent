"""Site Selection & Reporting V1 Gate 3 - deterministic PDF rendering over
AllocationReportContext (Gate 2).

PURE RENDERER (Section 3): render_allocation_report_pdf(context) -> bytes
takes an already-built AllocationReportContext and produces PDF bytes. Zero
database session, zero ORM object, zero OpenAI client, zero query - every
fact this module renders is already sitting on the context it was handed.
AllocationReportContext remains the single source of truth for this report;
this module never re-derives or independently looks up anything Gate 2's
context builder is responsible for.

Deliberately a NEW module, not an extension of app.reporting.pdf_report:
mirrors Gate 2's own reasoning for keeping CSV serialization out of that
module (the Allocation and Planning Site report domains have materially
different content contracts). Reuses pdf_report's generic ReportLab
style-sheet builder (_styles - Title/Subtitle/SectionHeading/Body, already
domain-neutral) rather than duplicating it; adds only the small number of
allocation-specific paragraph styles this report's layout needs on top of
that shared base. Also reuses the "deterministic figures first, model never
computes/writes narrative here" spirit of pdf_report's own architecture,
even though this gate has no narrative-writing step at all - this is a
persisted-evidence report, not an AI-narrated one (that is Gate 4's job).

No AllocationReportContext extension was required for this gate - every
field this report needed (identity, capacity, coverage, linked Applications,
party evidence with its trust partition, AI Allocation Intelligence
snapshot, source/evidence, and the aggregate totals) was already present
from Gate 2. See specifications/015-allocation-reporting-v1-gate-3-pdf.md
for the full audit trail of that decision.
"""
from __future__ import annotations

import datetime as dt
import io
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.reporting.allocation_discovery import DEVELOPMENT_COVERAGE_LABELS
from app.reporting.allocation_report import (
    AllocationReportContext,
    AllocationReportEntry,
    LinkedApplicationEntry,
    _planning_activity_label,
)
from app.reporting.pdf_report import _styles

REPORT_TITLE = "Allocation Opportunity Report"
REPORT_SUBTITLE = "Local Plan allocation and development activity intelligence"

# Section 6C - exact wording, reproduced verbatim. Neutral: not an error,
# not a warning, not negative planning evidence (that judgement belongs to
# a future Opportunity Potential capability, never asserted here).
NO_LINKED_APPLICATION_TEXT = "No linked planning application has been identified."

# Section 6E - exact wording for a missing/errored persisted summary
# (identical safe state either way, per AllocationIntelligenceSnapshot's
# own available=False guarantee - generation_error is never on this
# dataclass at all, so there is nothing here that could leak it).
AI_INTELLIGENCE_UNAVAILABLE_TEXT = "AI Allocation Intelligence not currently available."

_PROPOSAL_MAX_CHARS = 220


def _e(value) -> str:
    """Escape dynamic text before embedding it in a ReportLab Paragraph's
    XML-ish markup - a company/entity/proposal string containing "&" (a
    very ordinary character in UK company names, e.g. "Smith & Sons Ltd")
    or "<"/">" would otherwise corrupt or crash rendering. Never skipped
    for any value that ultimately came from scraped/extracted data."""
    if value is None:
        return ""
    return _xml_escape(str(value))


def _allocation_pdf_styles():
    """pdf_report._styles()'s existing Title/Subtitle/SectionHeading/Body
    styles, plus the small number of allocation-specific styles this
    report's layout needs - mirrors that module's own SchemeHeading/
    SchemeBody pair, renamed for this domain rather than reused directly,
    since "Scheme" is Planning Site vocabulary, not Allocation vocabulary."""
    styles = _styles()
    styles.add(ParagraphStyle("AllocationHeading", parent=styles["Heading3"], spaceBefore=14, spaceAfter=2))
    styles.add(ParagraphStyle("AllocationBody", parent=styles["Normal"], fontSize=9.5, leading=13, spaceAfter=4))
    styles.add(ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, leading=11, textColor=colors.grey))
    styles.add(ParagraphStyle("Pending", parent=styles["Normal"], fontSize=9.5, leading=13, textColor=colors.HexColor("#8a6d00"), spaceAfter=4))
    styles.add(ParagraphStyle("TableCell", parent=styles["Normal"], fontSize=8.5, leading=11))
    return styles


# --- Cover / header (Section 6) ----------------------------------------------


def _cover(styles, context: AllocationReportContext) -> list:
    authorities = sorted({e.council_name for e in context.entries})
    story = [
        Paragraph("PropertyAIgent", styles["ReportTitle"]),
        Paragraph(REPORT_TITLE, styles["Heading2"]),
        Paragraph(REPORT_SUBTITLE, styles["ReportSubtitle"]),
        Paragraph(f"Generated: {context.generated_at:%d %B %Y %H:%M} UTC", styles["Small"]),
        Paragraph(f"Shortlisted allocations: {len(context.entries)}", styles["Small"]),
        Paragraph(f"Authorities represented: {len(authorities)}", styles["Small"]),
        Spacer(1, 8 * mm),
    ]
    return story


# --- 1. Shortlist overview (Section 6) - aggregates only, evidence-faithful -


def _shortlist_overview(styles, context: AllocationReportContext) -> list:
    agg = context.aggregates
    story = [Paragraph("1. Shortlist Overview", styles["SectionHeading"])]

    # Capacity - deliberately three separate sentences (Section 6's own
    # GOOD/BAD example), never one blended "total capacity" figure that
    # would silently fold a range's upper bound in as if exact.
    if agg.exact_capacity_count:
        story.append(Paragraph(
            f"Exact stated capacity across {agg.exact_capacity_count} allocation"
            f"{'s' if agg.exact_capacity_count != 1 else ''}: {agg.exact_capacity_total:,} homes.",
            styles["Body"],
        ))
    if agg.ranged_capacity_count:
        story.append(Paragraph(
            f"{agg.ranged_capacity_count} allocation{'s have' if agg.ranged_capacity_count != 1 else ' has'} "
            "a ranged capacity - see individual allocation entries for each range.",
            styles["Body"],
        ))
    if agg.unknown_capacity_count:
        story.append(Paragraph(
            f"{agg.unknown_capacity_count} allocation{'s have' if agg.unknown_capacity_count != 1 else ' has'} "
            "unknown capacity.",
            styles["Body"],
        ))

    # Plan status.
    story.append(Paragraph(
        f"Plan status: {agg.adopted_count} adopted, {agg.emerging_count} emerging, "
        f"{agg.other_plan_status_count} other.",
        styles["Body"],
    ))

    # Planning activity.
    story.append(Paragraph(
        f"{agg.allocations_with_linked_activity} allocation"
        f"{'s have' if agg.allocations_with_linked_activity != 1 else ' has'} identified planning activity; "
        f"{agg.allocations_with_no_identified_activity} "
        f"{'have' if agg.allocations_with_no_identified_activity != 1 else 'has'} none identified.",
        styles["Body"],
    ))

    # Identified/residual capacity - known_total + unknown_count, never a
    # total presented as complete when some allocations are unknown/
    # review-required (Gate 2's own semantic-hardening discipline, carried
    # through unchanged into this report).
    identified_known_allocations = agg.allocation_count - agg.identified_application_capacity_unknown_count
    if identified_known_allocations:
        story.append(Paragraph(
            f"Identified application capacity across {identified_known_allocations} allocation"
            f"{'s' if identified_known_allocations != 1 else ''} with a known figure: "
            f"{agg.identified_application_capacity_known_total:,} homes "
            f"({agg.identified_application_capacity_unknown_count} unknown or review-required).",
            styles["Body"],
        ))
    residual_known_allocations = agg.allocation_count - agg.indicative_residual_capacity_unknown_count
    if residual_known_allocations:
        story.append(Paragraph(
            f"Indicative residual capacity across {residual_known_allocations} allocation"
            f"{'s' if residual_known_allocations != 1 else ''} with a known figure: "
            f"{agg.indicative_residual_capacity_known_total:,} homes "
            f"({agg.indicative_residual_capacity_unknown_count} unknown or review-required).",
            styles["Body"],
        ))

    return story


# --- 2. Shortlist summary table (Section 6) -----------------------------------


def _development_coverage_cell_text(entry: AllocationReportEntry) -> str:
    if entry.development_coverage_percentage is not None:
        return f"{entry.development_coverage_percentage:.0%}"
    return DEVELOPMENT_COVERAGE_LABELS.get(entry.development_coverage_classification, "Not determined")


def _summary_table(styles, context: AllocationReportContext) -> list:
    story = [Paragraph("2. Shortlist Summary", styles["SectionHeading"])]

    header = ["Allocation", "Authority", "Plan Status", "Capacity", "Planning Activity", "Dev. Coverage", "Residual Capacity"]
    rows = [[Paragraph(f"<b>{h}</b>", styles["TableCell"]) for h in header]]
    for entry in context.entries:
        residual_text = f"{entry.indicative_residual_capacity:,}" if entry.indicative_residual_capacity is not None else "Not determined"
        rows.append([
            Paragraph(_e(entry.allocation_name), styles["TableCell"]),
            Paragraph(_e(entry.council_name), styles["TableCell"]),
            Paragraph(_e(entry.plan_status_label), styles["TableCell"]),
            Paragraph(_e(entry.capacity_display), styles["TableCell"]),
            Paragraph(_e(_planning_activity_label(entry)), styles["TableCell"]),
            Paragraph(_e(_development_coverage_cell_text(entry)), styles["TableCell"]),
            Paragraph(_e(residual_text), styles["TableCell"]),
        ])

    # Column widths sum to the A4 printable width (210mm - 2*18mm margins =
    # 174mm) - Allocation/Authority get the most room since they carry the
    # longest text; every cell is Paragraph-wrapped (never a bare string)
    # so a long allocation name wraps instead of overflowing or crashing.
    col_widths = [40 * mm, 28 * mm, 22 * mm, 24 * mm, 22 * mm, 20 * mm, 18 * mm]
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.HexColor("#999999")),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#dddddd")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    return story


# --- 3. Allocation details (Section 6) ----------------------------------------


def _linked_application_block(styles, application: LinkedApplicationEntry) -> list:
    # Product presentation rule (Section 6C): the proposal is the
    # headline line; the reference is secondary/provenance, placed on its
    # own smaller, muted line below - never the other way round.
    proposal = application.proposal or "No proposal text extracted"
    if len(proposal) > _PROPOSAL_MAX_CHARS:
        proposal = proposal[:_PROPOSAL_MAX_CHARS].rstrip() + "…"
    heading = _e(proposal)
    if application.is_representative:
        heading += " <i>(representative)</i>"
    block = [Paragraph(heading, styles["AllocationBody"])]

    detail_bits = [b for b in (application.status, application.decision) if b]
    if application.unit_count is not None:
        unit_text = f"{application.unit_count:,} unit{'s' if application.unit_count != 1 else ''}"
        if application.unit_count_is_estimate:
            unit_text += " (estimated)"
        detail_bits.append(unit_text)
    if application.applicant:
        detail_bits.append(f"Applicant: {application.applicant}")
    detail_line = f"Ref: {_e(application.reference)}" + (" · " + " · ".join(_e(b) for b in detail_bits) if detail_bits else "")
    block.append(Paragraph(detail_line, styles["Small"]))
    return block


def _planning_activity_section(styles, entry: AllocationReportEntry) -> list:
    story = [Paragraph("Planning activity", styles["AllocationHeading"])]
    if not entry.linked_applications:
        story.append(Paragraph(NO_LINKED_APPLICATION_TEXT, styles["AllocationBody"]))
        return story
    # Deterministic rendering order (presentation-only, not a context
    # change) - by reference, independent of whatever internal query/dict
    # order the context happened to assemble them in.
    for application in sorted(entry.linked_applications, key=lambda a: a.reference):
        story.extend(_linked_application_block(styles, application))
    return story


def _party_evidence_section(styles, entry: AllocationReportEntry) -> list | None:
    applicant_names = sorted({e.entity_name for e in entry.applicant_evidence})
    trusted_developer = sorted({e.entity_name_raw for e in entry.trusted_ownership_evidence if e.role == "DEVELOPER"})
    trusted_other = sorted(
        {(e.entity_name_raw, e.role_label) for e in entry.trusted_ownership_evidence if e.role != "DEVELOPER"}
    )
    pending_developer = sorted({e.entity_name_raw for e in entry.review_pending_ownership_evidence if e.role == "DEVELOPER"})
    pending_other = sorted(
        {(e.entity_name_raw, e.role_label) for e in entry.review_pending_ownership_evidence if e.role != "DEVELOPER"}
    )

    if not any((applicant_names, trusted_developer, trusted_other, pending_developer, pending_other)):
        return None  # nothing to show - omitted entirely, matching the existing Shortlist page's own behaviour

    story = [Paragraph("Party evidence", styles["AllocationHeading"])]
    if applicant_names:
        story.append(Paragraph(f"<b>Applicant:</b> {_e(', '.join(applicant_names))}", styles["AllocationBody"]))
    if trusted_developer:
        story.append(Paragraph(f"<b>Developer:</b> {_e(', '.join(trusted_developer))}", styles["AllocationBody"]))
    for name, role_label in trusted_other:
        story.append(Paragraph(f"<b>{_e(role_label)}:</b> {_e(name)}", styles["AllocationBody"]))
    # Review-pending evidence is NEVER on the same line/style as trusted
    # evidence above - a visibly distinct style (Pending) and an explicit
    # qualification, matching Gate 2's own trust-partition discipline.
    if pending_developer:
        story.append(Paragraph(f"Developer (evidence pending confirmation): {_e(', '.join(pending_developer))}", styles["Pending"]))
    for name, role_label in pending_other:
        story.append(Paragraph(f"{_e(role_label)} (evidence pending confirmation): {_e(name)}", styles["Pending"]))
    return story


def _ai_intelligence_section(styles, entry: AllocationReportEntry) -> list:
    story = [Paragraph("AI Allocation Intelligence", styles["AllocationHeading"])]
    ai = entry.ai_intelligence
    if not ai.available:
        story.append(Paragraph(AI_INTELLIGENCE_UNAVAILABLE_TEXT, styles["AllocationBody"]))
        return story

    story.append(Paragraph(f"<b>{_e(ai.headline)}</b>", styles["AllocationBody"]))
    if ai.overview:
        story.append(Paragraph(_e(ai.overview), styles["AllocationBody"]))
    if ai.key_points:
        story.append(Paragraph("<b>Key intelligence</b>", styles["AllocationBody"]))
        for point in ai.key_points:
            story.append(Paragraph(f"• {_e(point)}", styles["AllocationBody"]))
    if ai.key_uncertainties:
        story.append(Paragraph("<b>Key uncertainties</b>", styles["AllocationBody"]))
        for item in ai.key_uncertainties:
            story.append(Paragraph(f"• {_e(item)}", styles["AllocationBody"]))
    if ai.investigation_priorities:
        story.append(Paragraph("<b>Investigation priorities</b>", styles["AllocationBody"]))
        for item in ai.investigation_priorities:
            story.append(Paragraph(f"• {_e(item)}", styles["AllocationBody"]))
    if ai.generated_at:
        story.append(Paragraph(
            f"Generated {ai.generated_at:%d %b %Y} · AI-generated interpretation of evidence PropertyAIgent already "
            "holds - not a substitute for the detail above.",
            styles["Small"],
        ))
    return story


def _source_evidence_section(styles, entry: AllocationReportEntry) -> list | None:
    bits = []
    if entry.source_document_url:
        bits.append(f"Source: {_e(entry.source_document_url)}")
    if entry.last_checked:
        bits.append(f"Local Plan evidence last checked: {entry.last_checked:%d %b %Y}")
    if entry.review_status_label:
        bits.append(f"Review status: {_e(entry.review_status_label)}")
    if not bits:
        return None
    return [Paragraph(" · ".join(bits), styles["Small"])]


def _allocation_section(styles, entry: AllocationReportEntry) -> list:
    header_bits = [b for b in (entry.council_name, entry.local_plan_name, entry.allocation_reference) if b]
    block = [
        Paragraph(_e(entry.allocation_name), styles["Heading2"]),
        Paragraph(" · ".join(_e(b) for b in header_bits), styles["Small"]),
        Paragraph(
            f"<b>Plan status:</b> {_e(entry.plan_status_label)} &nbsp;&nbsp; "
            f"<b>Intended use:</b> {_e(entry.intended_use_label)}",
            styles["AllocationBody"],
        ),
    ]

    # B. Development position - None is never rendered as zero; a range's
    # upper bound is never presented as if exact (capacity_display already
    # carries the honest range/exact/unknown wording, unchanged from
    # format_capacity - never reinterpreted here).
    identified_text = f"{entry.identified_application_capacity:,}" if entry.identified_application_capacity is not None else "Not determined"
    residual_text = f"{entry.indicative_residual_capacity:,}" if entry.indicative_residual_capacity is not None else "Not determined"
    block.append(Paragraph(
        f"<b>Capacity:</b> {_e(entry.capacity_display)} &nbsp;&nbsp; "
        f"<b>Identified application capacity:</b> {identified_text} &nbsp;&nbsp; "
        f"<b>Development coverage:</b> {_e(_development_coverage_cell_text(entry))} &nbsp;&nbsp; "
        f"<b>Indicative residual:</b> {residual_text}",
        styles["AllocationBody"],
    ))

    block.extend(_planning_activity_section(styles, entry))

    party_section = _party_evidence_section(styles, entry)
    if party_section:
        block.extend(party_section)

    block.extend(_ai_intelligence_section(styles, entry))

    source_section = _source_evidence_section(styles, entry)
    if source_section:
        block.append(Spacer(1, 2 * mm))
        block.extend(source_section)

    # Mirrors app.reporting.pdf_report's own established per-item
    # KeepTogether pattern (Sections 8's "avoid splitting small tables/
    # sections awkwardly across pages") - the same accepted tradeoff that
    # module already makes for scheme blocks, applied consistently here.
    return [KeepTogether(block), Spacer(1, 4 * mm)]


def _allocation_details(styles, context: AllocationReportContext) -> list:
    story = [Paragraph("3. Allocation Details", styles["SectionHeading"])]
    for entry in context.entries:  # already deterministic id order (Gate 2's own guarantee)
        story.extend(_allocation_section(styles, entry))
    return story


# --- Excluded shortlist items (Section 7) -------------------------------------


def _excluded_section(styles, context: AllocationReportContext) -> list:
    if not context.excluded:
        return []
    story = [Paragraph("Excluded Shortlist Items", styles["SectionHeading"])]
    story.append(Paragraph(
        "The following shortlisted allocations could not be included in this report:", styles["Body"],
    ))
    # Only allocation_id + reason are ever available for an excluded
    # candidate (Gate 2's ExcludedCandidate shape) - an id that never
    # resolved to a real allocation has no name to show; never fabricated
    # here (Section 16 - this is not a "genuinely required" context
    # extension, since there is no real display name to source it from).
    for excluded in sorted(context.excluded, key=lambda e: e.allocation_id):
        story.append(Paragraph(f"Allocation ID {excluded.allocation_id}: {_e(excluded.reason)}", styles["AllocationBody"]))
    return story


# --- Footer (page numbers) ----------------------------------------------------


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(18 * mm, 12 * mm, f"PropertyAIgent — {REPORT_TITLE}")
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


# --- Top-level renderer contract (Section 10) ---------------------------------


def render_allocation_report_pdf(context: AllocationReportContext) -> bytes:
    """AllocationReportContext -> PDF bytes. Pure renderer: no Session, no
    ORM object, no OpenAI client, zero database queries - every fact
    rendered is already present on `context`. Deterministic for the same
    context (byte-identical PDF metadata aside, which ReportLab itself may
    stamp with a creation timestamp - not something application code
    controls)."""
    styles = _allocation_pdf_styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
        title=f"PropertyAIgent — {REPORT_TITLE}",
    )

    story: list = []
    story.extend(_cover(styles, context))
    story.extend(_shortlist_overview(styles, context))
    story.append(Spacer(1, 4 * mm))
    story.extend(_summary_table(styles, context))
    story.append(Spacer(1, 4 * mm))
    story.extend(_allocation_details(styles, context))
    story.extend(_excluded_section(styles, context))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def allocation_report_pdf_filename(context: AllocationReportContext) -> str:
    """Deterministic, safe filename - built entirely from context.generated_at
    (an internally-produced UTC timestamp, never arbitrary site/user input),
    so no sanitisation of external text is needed."""
    return f"property-aigent-allocation-report-{context.generated_at:%Y-%m-%d}.pdf"
