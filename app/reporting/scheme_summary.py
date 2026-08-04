"""AI-narrated synthesis of everything known about one site - every linked
application, phase/plot breakdown, and build-status signal - into a single
coherent status summary.

Same grounded-numbers-then-narrate principle already used by
app.reporting.pdf_report and app.search.query_parser: every fact fed to the
model (phase count, phase statuses, application counts, developer,
lapse/build status) is computed in Python first from already-verified data -
the model only ever writes the connective prose synthesising facts it's
given, it never counts, classifies, or invents a phase/status itself.
"""
from __future__ import annotations

import json

from openai import OpenAI

from app.db.models import Application, Site
from app.pipeline.lapse_tracking import BUILD_STATUS_LABELS, LAPSE_STATUS_LABELS, get_expected_decision, parse_portal_date
from app.pipeline.phase_tracking import PHASE_STATUS_LABELS, summarize_phase_units

MODEL = "gpt-4o-mini"

# Every site gets a summary now, including single-application ones still
# awaiting a decision - confirmed real user request: "we can create a status
# for all schemes even if building work hasn't started", specifically what
# planning stage it's at and when a decision might come, which is genuinely
# useful even with just one linked application.
MIN_APPLICATIONS_FOR_SUMMARY = 1


def _fmt_application(app: Application) -> str:
    expected = get_expected_decision(app)
    expected_bit = ""
    if expected["date"]:
        tag = "confirmed by the council" if expected["source"] == "scraped" else "statutory 13-week estimate, not confirmed"
        expected_bit = f", expected decision ~{expected['date'].strftime('%d %b %Y')} ({tag})"
    return (
        f"{app.reference} ({app.application_category or 'unknown'}, "
        f"{app.status or '?'}/{app.decision or '?'}, received {app.application_received or '?'}{expected_bit}): "
        f"{(app.proposal or '')[:150]}"
    )


def build_summary_prompt(
    site: Site, applications: list[Application], merged: dict, lapse: dict, phase_breakdown: list[dict],
) -> str:
    lapse_label = LAPSE_STATUS_LABELS.get(lapse["status"], lapse["status"])
    build_label = BUILD_STATUS_LABELS.get(lapse["build_status"], lapse["build_status"])

    if phase_breakdown:
        phase_lines = [
            f"- {p['label']}: {PHASE_STATUS_LABELS.get(p['status'], p['status'])} "
            f"({len(p['applications'])} application(s) filed against it)"
            + (f", {p['unit_count']} units" if p.get("unit_count") else "")
            for p in phase_breakdown
        ]
        phase_text = "\n".join(phase_lines)

        # Rolled-up totals by build status, computed the same way the
        # Streamlit "Under construction / Approved, not yet started / Awaiting
        # decision" banner is - a phase with no confirmed unit count still
        # counts toward its bucket's phase count, it just can't add to that
        # bucket's unit total, so the model is never handed a fabricated sum.
        unit_summary = summarize_phase_units(phase_breakdown)

        def _bucket_line(name: str, bucket: dict) -> str | None:
            if bucket["phase_count"] == 0:
                return None
            units_bit = f"{bucket['units']} units" if bucket["units"] else "unit count not confirmed"
            if bucket["units"] and bucket["phases_with_known_units"] < bucket["phase_count"]:
                units_bit += f" (known for {bucket['phases_with_known_units']} of {bucket['phase_count']} phases)"
            return f"- {name}: {bucket['phase_count']} phase(s), {units_bit}"

        rollup_lines = [
            line for line in (
                _bucket_line("Underway", unit_summary["underway"]),
                _bucket_line("Approved, not yet started", unit_summary["approved_not_started"]),
                _bucket_line("Awaiting decision", unit_summary["not_yet_approved"]),
            ) if line
        ]
        phase_unit_rollup = "\n".join(rollup_lines) if rollup_lines else None
    else:
        phase_text = "No distinct phases or plots are named in any application's own text - treat this as a single, unphased scheme, not one with undetermined phases."
        phase_unit_rollup = None

    app_lines = "\n".join(
        f"- {_fmt_application(a)}"
        # parse_portal_date, not a raw string sort - confirmed real bug:
        # portal dates are "Wed 29 Feb 2012", so a plain string comparison
        # sorts on the day-of-week/day-of-month prefix, not the year, and
        # was putting a 2012 outline permission BEFORE a 2026 filing on the
        # same site despite the list being labelled "most recent first".
        for a in sorted(applications, key=lambda a: parse_portal_date(a.application_received), reverse=True)
    )

    return f"""
You are writing an internal status note for a UK residential land/planning
acquisition professional, synthesising everything currently known about ONE
site from its full history of linked planning applications. Every fact
below is already verified - restate and synthesise it, never invent a
figure, phase, or status that isn't listed here.

SITE: {site.display_address} ({site.council_code})
SCHEME SCOPE: {merged.get('total_units_final')} total units, developer {merged.get('developer') or 'not identified'}
OVERALL COMMENCEMENT STATUS: {lapse_label}
OVERALL BUILD STATUS: {build_label}

PHASE / PLOT BREAKDOWN ({len(phase_breakdown)} distinct phase(s)/plot(s) named across this site's applications):
{phase_text}
{"" if not phase_unit_rollup else f'''
UNIT TOTALS BY STATUS (named phases only, not individual plots - use these
exact figures if you state any unit count by status, never derive your own):
{phase_unit_rollup}
'''}
ALL {len(applications)} LINKED APPLICATIONS ON THIS SITE (most recent first):
{app_lines}

Write a short status note (3-5 sentences, plain text, no markdown headers)
covering:
1. Where this scheme currently stands overall - if nothing is granted yet,
   say so plainly and state the actual portal status of its live
   application(s) (e.g. "Under Consultation", "Registered", "Awaiting
   decision" - use the exact status shown against each application above,
   never invent a generic "pending"). If something is granted, say roughly
   how much of it has confirmed activity versus how much doesn't yet.
2. If any application above is still undecided and shows an "expected
   decision" figure, state it - and say plainly whether it's confirmed by
   the council or a statutory estimate (the wording in brackets tells you
   which). If no application shows an expected decision figure, don't
   mention one.
3. If phases or plots were named above: which specific ones show confirmed
   activity (a discharge-of-conditions or amendment filed against them, i.e.
   status "Underway") versus which have full permission but NO such filing
   yet (status "Approved, not yet started") - name the actual phase/plot
   labels, don't speak generically.
4. The acquisition opportunity is ONLY the phase(s)/plot(s) whose status is
   literally "Approved, not yet started" (🟢 in the breakdown above) - full
   permission, nothing built, no legal deadline forcing the developer to
   act once something else on the site has already started. Do NOT call an
   "Underway" phase/plot an opportunity or "undeveloped" under any
   circumstance, even if its own unit count is unconfirmed - underway means
   it already has confirmed activity, full stop. If NO phase/plot has
   "Approved, not yet started" status, say plainly that there is currently
   no undeveloped phase-level opportunity on this site - do not invent one.
5. If a UNIT TOTALS BY STATUS section is present, state the underway and
   approved-not-yet-started unit figures using those exact numbers. If a
   bucket's unit count wasn't confirmed, say so rather than guessing - name
   the phase and describe the count as unconfirmed, don't omit it or invent
   a figure.
6. If no phases were named at all (including single-application sites),
   describe the site as a whole rather than inventing a phase structure
   that isn't there.
"""


SUMMARY_SCHEMA = {
    "name": "scheme_status_summary",
    "schema": {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    },
}


def generate_scheme_summary(
    client: OpenAI, site: Site, applications: list[Application], merged: dict, lapse: dict, phase_breakdown: list[dict],
) -> str:
    prompt = build_summary_prompt(site, applications, merged, lapse, phase_breakdown)
    response = client.responses.create(
        model=MODEL, input=prompt,
        text={"format": {"type": "json_schema", "name": SUMMARY_SCHEMA["name"], "schema": SUMMARY_SCHEMA["schema"], "strict": True}},
    )
    return json.loads(response.output_text)["summary"]
