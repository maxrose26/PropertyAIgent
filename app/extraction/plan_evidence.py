"""Plan-level AI evidence extraction (Sprint 3B, "AI Local Plan Evidence
Extraction") - reads a Local Plan or a supporting policy document (an
Annual Monitoring Report, a five-year supply statement, a Local
Development Scheme...) and extracts structured, source-linked facts about
the PLAN as a whole (housing requirement, delivery, five-year supply,
examination status...).

This is deliberately a SEPARATE module from app.extraction.local_plan,
which extracts individual site ALLOCATIONS - a different kind of fact,
already working, not touched by this sprint. The same "grounded facts,
AI narrates/structures, never invents" discipline applies here, just with
an explicit per-fact evidence bundle (page, excerpt, confidence) that
local_plan.py's allocation extraction doesn't need in the same way, since
every allocation is naturally its own row already.

Four targeted extraction passes (Part 4: "use targeted extraction passes
to control cost and reduce hallucination risk", never one broad prompt
across every field):

    plan_identity        - name/version/status/period/dates/milestones
    housing_requirement  - the plan's own requirement AND housing need (kept separate - Part 3)
    housing_delivery     - Annual Monitoring Report / trajectory facts
    five_year_supply     - five-year housing land supply position

Each pass returns one "fact" object per field in that category's list,
every time - never silently omitted - so a missing value is an explicit
null, not an absent key (Part 2: "missing evidence must return null or an
explicit 'not found'").
"""
from __future__ import annotations

import json

import pdfplumber
from openai import OpenAI

MODEL = "gpt-4o-mini"
# Bumped whenever the prompt or schema changes in a way that could change
# extracted output - stored on every PolicyChangeEvent this pipeline
# creates (app.policy.extract_plan_evidence) so a re-run under a NEW
# version is never silently treated as "unchanged" against facts extracted
# under an old one, and so a human reviewing a proposal knows exactly which
# prompt produced it.
PROMPT_VERSION = "plan-evidence-v1"

PLAN_IDENTITY_FIELDS = {
    "plan_name": "The plan's own title, exactly as printed on its cover/title page.",
    "plan_version": "The plan's stage label as the council itself calls it, e.g. 'Regulation 18', 'Regulation 19', 'Adopted 2024'.",
    "raw_plan_status": "The council's own current-status wording for this plan, verbatim (e.g. 'Publication', 'Submitted for Examination').",
    "plan_period_start": "The first year of the plan period, as a bare year number (e.g. 2024).",
    "plan_period_end": "The last year of the plan period, as a bare year number (e.g. 2042).",
    "publication_date": "The date this specific document/plan version was published.",
    "submission_date": "The date the plan was submitted to the Secretary of State for independent examination.",
    "examination_status": "The current state of the examination in the council's own words (e.g. 'Hearings concluded', 'Awaiting main modifications consultation').",
    "inspector_report_date": "The date the independent Inspector's final report was issued.",
    "adoption_date": "The date the plan was formally adopted by the council - only fill this if adoption has genuinely already happened.",
    "expected_adoption_date": "A stated FUTURE target/expected date for adoption - never the same as adoption_date, and never filled if the plan is already adopted.",
    "next_milestone": "The next stage in the plan's own timetable, in the council's own wording.",
    "next_milestone_date": "The date attached to next_milestone.",
    "planning_system": "'legacy' if this is a 2004-Act-style Local Plan, or 'new' if the document itself describes the new Levelling-up and Regeneration Act 2023 system - null if not stated either way.",
    "status_notes": "Any other short, materially useful nuance about the plan's current status that the fields above can't capture.",
}

HOUSING_REQUIREMENT_FIELDS = {
    "annual_housing_requirement": "The PLAN'S OWN adopted or proposed annual housing requirement, in dwellings per year - NOT a separate housing need study's output.",
    "total_plan_housing_requirement": "The plan's own total housing requirement across the whole plan period, in dwellings.",
    "housing_need_annual": "The annual output of a HOUSING NEED study or standard method calculation (e.g. from a Strategic Housing Market Assessment) - distinct from the plan's own adopted requirement above, even if the two numbers happen to match.",
    "housing_need_total": "The total housing need study output across the relevant period, in dwellings.",
    "requirement_basis": "How the requirement/need figure was derived, in the source's own words (e.g. 'standard method', 'standard method uplifted for affordability', 'locally-derived assessment').",
    "unmet_need": "A dwelling figure the plan itself explicitly states it CANNOT accommodate within its own area (unmet need), if stated.",
    "neighbouring_authority_contribution": "A short description, in the source's own words, of how any unmet need is being met elsewhere (e.g. redistributed to another authority via a joint plan).",
    "requirement_notes": "Any other short, materially useful nuance about the requirement/need position that the fields above can't capture.",
}

HOUSING_DELIVERY_FIELDS = {
    "latest_reporting_period": "The most recent monitoring/reporting year or period covered by this document (e.g. '2023/24').",
    "homes_delivered_latest_period": "The number of homes actually delivered/completed in latest_reporting_period.",
    "cumulative_homes_delivered": "The cumulative number of homes delivered across the plan period so far, if stated.",
    "delivery_requirement_for_period": "The number of homes that were required/expected to be delivered in latest_reporting_period.",
    "delivery_surplus_or_shortfall": "The stated surplus (positive) or shortfall (negative) against the requirement for that period, as a signed number of dwellings.",
    "housing_delivery_test_result": "The council's published Housing Delivery Test result/percentage for the latest year, exactly as stated (e.g. '87%').",
    "trajectory_remaining_requirement": "The remaining number of homes the plan's own trajectory still expects to deliver over the rest of the plan period - a forward PROJECTION, not an adopted requirement.",
    "delivery_notes": "Any other short, materially useful nuance about delivery performance that the fields above can't capture.",
}

FIVE_YEAR_SUPPLY_FIELDS = {
    "five_year_supply_years": "The number of years of deliverable housing land supply the source EXPLICITLY states as a headline figure (e.g. 4.8) - never a number you calculate or infer yourself from other dwelling figures in the text.",
    "five_year_supply_base_date": "The date this five-year supply position is calculated FROM (its base date).",
    "five_year_supply_publication_date": "The date this supply statement/position was published.",
    "deliverable_supply_dwellings": "The total number of dwellings in the stated deliverable supply.",
    "five_year_requirement_dwellings": "The total dwelling requirement the five-year supply is being measured against (including any buffer).",
    "five_year_shortfall_or_surplus_dwellings": "The stated shortfall (negative) or surplus (positive) in dwellings, if given directly.",
    "buffer_percentage": "The NPPF buffer percentage applied (e.g. 5, 20), as a bare number, if stated.",
    "calculation_method": "The named method used for the supply calculation, verbatim (e.g. 'Sedgefield', 'Liverpool').",
    "supply_position_notes": "Any other short, materially useful nuance about the supply position that the fields above can't capture.",
}

CATEGORIES: dict[str, dict[str, str]] = {
    "plan_identity": PLAN_IDENTITY_FIELDS,
    "housing_requirement": HOUSING_REQUIREMENT_FIELDS,
    "housing_delivery": HOUSING_DELIVERY_FIELDS,
    "five_year_supply": FIVE_YEAR_SUPPLY_FIELDS,
}


def extract_pdf_pages(pdf_path: str, first_page: int, last_page: int) -> list[tuple[int, str]]:
    """1-indexed, inclusive. Returns [(page_number, page_text), ...] -
    unlike app.extraction.local_plan.extract_pdf_page_range (which
    concatenates a whole range into one string and loses page boundaries
    entirely), this keeps every page's text separately addressable, which
    is the minimum mechanism needed for a fact to cite a real page number
    (Part 5: "the pipeline must retain page-level provenance")."""
    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages[first_page - 1:last_page]
        return [(first_page + i, (page.extract_text() or "")) for i, page in enumerate(pages)]


def format_pages_for_prompt(pages: list[tuple[int, str]]) -> str:
    """Explicit [PAGE N] markers so the model can cite a real page number
    per fact instead of guessing or defaulting to the range's first page."""
    return "\n\n".join(f"[PAGE {page_number}]\n{text}" for page_number, text in pages)


def _build_schema(category: str) -> dict:
    fields = CATEGORIES[category]
    return {
        "name": f"plan_evidence_{category}",
        "schema": {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string", "enum": list(fields.keys())},
                            "value": {
                                "type": ["string", "null"],
                                "description": "The value exactly as printed/stated in the source, as a string "
                                               "(digits for numbers, the date as printed) - null if this field is "
                                               "not explicitly supported anywhere in the source text.",
                            },
                            "source_page": {"type": ["integer", "null"], "description": "The [PAGE N] the excerpt came from. Null only when value is null."},
                            "source_excerpt": {
                                "type": ["string", "null"],
                                "description": "A short verbatim quote (under ~250 characters) from the source "
                                               "text that supports this value - never a paraphrase. Null only "
                                               "when value is null.",
                            },
                            "confidence": {
                                "type": ["string", "null"],
                                "description": "One of \"high\", \"medium\", \"low\" - null only when value is null.",
                            },
                        },
                        "required": ["field", "value", "source_page", "source_excerpt", "confidence"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["facts"],
            "additionalProperties": False,
        },
    }


def build_evidence_prompt(category: str, source_text: str) -> str:
    fields = CATEGORIES[category]
    field_list = "\n".join(f"- {name}: {description}" for name, description in fields.items())
    return f"""
The text below is extracted from a UK council's Local Plan or a supporting
policy document (an Annual Monitoring Report, a five-year housing land
supply statement, a Local Development Scheme, an Inspector's report, an
adoption statement...), with [PAGE N] markers showing where each source
page begins.

Extract ONLY the following fields. Return exactly one fact object per
field below, even when you cannot find it - use null for value,
source_page, source_excerpt and confidence in that case, never omit the
field or guess a plausible-sounding value:

{field_list}

Rules:
- Never invent, estimate, or calculate a figure yourself. If the source
  does not explicitly state it, the value is null. The one narrow
  exception: if the source itself states a calculation (shows its own
  inputs and its own result), you may transcribe the RESULT as printed -
  you must never perform the arithmetic yourself.
- source_excerpt must be a short, verbatim quote copied from the text
  above - never your own summary or paraphrase.
- source_page must be the number from the [PAGE N] marker immediately
  before the excerpt you quoted.
- Keep "housing need" and "housing requirement" strictly separate fields -
  never use a housing need figure to fill a requirement field, or a
  requirement figure to fill a need field, even if only one of the two is
  actually stated in this text.
- five_year_supply_years must only be filled when the source explicitly
  states a number of years of supply as its own headline figure - never
  infer or derive it yourself from a raw dwelling count.
- expected_adoption_date is a stated future target; adoption_date is only
  for a plan that has genuinely already been adopted. Never fill both from
  the same sentence.

SOURCE TEXT:
{source_text}
"""


def extract_plan_evidence(client: OpenAI, category: str, source_text: str, usage_sink: list | None = None) -> list[dict]:
    """Runs one targeted extraction pass. Returns a list of fact dicts:
    {"field", "value", "source_page", "source_excerpt", "confidence"} - one
    per field in CATEGORIES[category], in the schema's own field order.

    usage_sink, if given, has the raw OpenAI response.usage object appended
    to it when the API reports one - an opt-in side channel for a caller
    that wants to total up token usage/cost (app.policy.extract_plan_evidence,
    Part 9) without changing this function's own return type for every
    other caller that just wants the facts."""
    if category not in CATEGORIES:
        raise ValueError(f"Unknown evidence category {category!r} - expected one of {sorted(CATEGORIES)}")
    schema = _build_schema(category)
    prompt = build_evidence_prompt(category, source_text)
    response = client.responses.create(
        model=MODEL, input=prompt,
        text={"format": {"type": "json_schema", "name": schema["name"], "schema": schema["schema"], "strict": True}},
    )
    if usage_sink is not None and getattr(response, "usage", None) is not None:
        usage_sink.append(response.usage)
    return json.loads(response.output_text)["facts"]
