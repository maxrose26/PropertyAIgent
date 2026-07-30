"""Natural-language search -> structured filters.

One LLM call turns a free-text query like "find me projects with 50+
affordable units in Greater Manchester which haven't been completed" into
the same structured filters a filter UI would set - same
client.responses.create(..., json_schema, strict=True) pattern already used
throughout app/extraction/prompts.py, reused rather than reinvented.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import pandas as pd
from openai import OpenAI

from app.config import load_councils

MODEL = "gpt-4o-mini"

# Groupable entity columns for "who/which X is most active" style questions -
# these map 1:1 to columns already present on the site-level dataframe built
# in streamlit_app.py.
AGGREGATE_GROUP_BY_FIELDS = [
    "registered_provider", "developer", "applicant_company",
    "planning_agent", "landowner", "housing_association", "council",
]
AGGREGATE_METRICS = ["count_schemes", "total_units", "total_affordable_units"]

FILTERS_SCHEMA = {
    "name": "search_filters",
    "schema": {
        "type": "object",
        "properties": {
            "query_type": {"type": "string", "enum": ["filter", "aggregate"]},
            "region": {"type": ["string", "null"]},
            "council_codes": {"type": ["array", "null"], "items": {"type": "string"}},
            "min_total_units": {"type": ["integer", "null"]},
            "max_total_units": {"type": ["integer", "null"]},
            "min_affordable_units": {"type": ["integer", "null"]},
            "max_affordable_units": {"type": ["integer", "null"]},
            "development_types": {"type": ["array", "null"], "items": {"type": "string"}},
            "exclude_completed": {"type": "boolean"},
            "statuses": {
                "type": ["array", "null"],
                "items": {"type": "string", "enum": ["granted", "refused", "withdrawn", "not_yet_decided"]},
            },
            "needs_review": {"type": ["boolean", "null"]},
            # Only set when query_type == "aggregate" - a question like "who
            # is the most active registered provider" rather than a filter
            # request. The actual computation is done in pandas against real
            # data, never by the LLM, to avoid hallucinated numbers - this
            # just captures what to compute.
            "aggregate_group_by": {"type": ["string", "null"], "enum": AGGREGATE_GROUP_BY_FIELDS + [None]},
            "aggregate_metric": {"type": ["string", "null"], "enum": AGGREGATE_METRICS + [None]},
            "aggregate_top_n": {"type": ["integer", "null"]},
            "interpretation_notes": {"type": "string"},
        },
        "required": [
            "query_type", "region", "council_codes", "min_total_units", "max_total_units", "min_affordable_units",
            "max_affordable_units", "development_types", "exclude_completed", "statuses", "needs_review",
            "aggregate_group_by", "aggregate_metric", "aggregate_top_n", "interpretation_notes",
        ],
        "additionalProperties": False,
    },
}


@dataclass
class SearchFilters:
    query_type: str = "filter"  # "filter" | "aggregate"
    region: str | None = None
    council_codes: list[str] = field(default_factory=list)
    min_total_units: int | None = None
    max_total_units: int | None = None
    min_affordable_units: int | None = None
    max_affordable_units: int | None = None
    development_types: list[str] = field(default_factory=list)
    exclude_completed: bool = False
    statuses: list[str] = field(default_factory=list)
    needs_review: bool | None = None
    aggregate_group_by: str | None = None
    aggregate_metric: str | None = None
    aggregate_top_n: int | None = None
    interpretation_notes: str = ""


def build_prompt(nl_query: str) -> str:
    councils = load_councils()
    known_councils = "\n".join(f"- {c.code}: {c.name} (region: {c.region})" for c in councils.values())
    known_regions = sorted({c.region for c in councils.values() if c.region})

    return f"""
You are turning a UK property-sourcing search query into structured filters
for a database of planning applications.

Known councils (map region/place names in the query to these):
{known_councils}

Known regions: {", ".join(known_regions)}

Rules:
- Only set council_codes if the query names a specific council; otherwise use region.
- "haven't been completed" / "not yet built" / "still available" -> exclude_completed = true.
- "50+ affordable units" -> min_affordable_units = 50.
- "no affordable units" / "zero affordable" / "fully private" -> max_affordable_units = 0.
- "no more than N affordable units" -> max_affordable_units = N.
- If a filter isn't mentioned, leave it null/empty - do not guess values that weren't asked for.
- development_types should match values like: apartments, houses, mixed_apartments_and_houses,
  build_to_rent, retirement_living, extra_care, supported_living, student_accommodation,
  care_home, affordable_housing, mixed_affordable_and_market_housing, mixed_use_residential,
  conversion. Only set this when the query explicitly describes the TYPE/FORM of housing,
  using phrases like "houses only", "no flats"/"not flats", "flats only", "detached houses",
  "semi-detached", "terraced houses", "bungalows", "apartment scheme(s)", "flat scheme(s)".
  Do NOT set it just because "houses" or "homes" appears as a plain count noun next to a
  number (e.g. "50 houses", "100+ new homes", "over 30 houses") - in everyday UK property
  language that's a generic synonym for "units"/"dwellings", not a type filter. Confirmed a
  real case: "50+ houses" (meant as "50+ homes/units") wrongly matched only 3 of 40 genuinely-
  matching schemes when read as houses-only. But "houses only, no flats" and "detached houses"
  DO mean the type specifically - set development_types = ["houses"] for those. When genuinely
  ambiguous, prefer NOT setting it - a missed type filter shows a few extra results to skim
  past; a wrong one can silently hide most of the real matches, as it did here.
- statuses (planning decision outcome, not build/completion status - that's exclude_completed):
  "approved" / "granted" / "has planning permission" / "with consent" -> statuses = ["granted"].
  "refused" / "rejected" -> statuses = ["refused"]. "withdrawn" -> statuses = ["withdrawn"].
  "awaiting decision" / "not yet decided" / "pending" / "undecided" -> statuses = ["not_yet_decided"].
  Only set this if the query explicitly asks about decision outcome - most queries don't.

query_type:
- "filter" (default) - the query describes which schemes to LIST (e.g. "50+
  unit schemes in Bolton").
- "aggregate" - the query is a QUESTION asking for a ranking/total across
  schemes rather than a list of them, e.g. "who's the most active registered
  provider", "which developer has delivered the most homes", "how many
  affordable units has Vistry built", "top planning agents in Stockport".
  When aggregate:
  - aggregate_group_by: the entity being ranked - registered_provider (RP),
    developer, applicant_company, planning_agent, landowner,
    housing_association, or council.
  - aggregate_metric: count_schemes ("most active"/"most schemes"/"busiest"),
    total_units ("most homes"/"most units built"), or
    total_affordable_units ("most affordable homes delivered").
  - aggregate_top_n: 1 if the query asks for a single "the most X" answer,
    otherwise however many the query asks for ("top 5" -> 5), default 5.
  - Region/council/other filters mentioned alongside the question (e.g. "...
    across Greater Manchester") should still be extracted normally - they
    scope which schemes the aggregation runs over.
- Briefly explain your interpretation in interpretation_notes (one sentence).

Query:
{nl_query}
"""


def parse_query(client: OpenAI, nl_query: str) -> SearchFilters:
    response = client.responses.create(
        model=MODEL,
        input=build_prompt(nl_query),
        text={"format": {"type": "json_schema", "name": FILTERS_SCHEMA["name"], "schema": FILTERS_SCHEMA["schema"], "strict": True}},
    )
    result = json.loads(response.output_text)
    return SearchFilters(
        query_type=result.get("query_type") or "filter",
        region=result.get("region"),
        council_codes=result.get("council_codes") or [],
        min_total_units=result.get("min_total_units"),
        max_total_units=result.get("max_total_units"),
        min_affordable_units=result.get("min_affordable_units"),
        max_affordable_units=result.get("max_affordable_units"),
        development_types=result.get("development_types") or [],
        exclude_completed=bool(result.get("exclude_completed")),
        statuses=result.get("statuses") or [],
        needs_review=result.get("needs_review"),
        aggregate_group_by=result.get("aggregate_group_by"),
        aggregate_metric=result.get("aggregate_metric"),
        aggregate_top_n=result.get("aggregate_top_n"),
        interpretation_notes=result.get("interpretation_notes", ""),
    )


# Maps SearchFilters.aggregate_group_by -> the matching column on the
# site-level dataframe built in streamlit_app.py.
GROUP_BY_COLUMNS = {
    "registered_provider": "Registered Provider",
    "developer": "Developer",
    "applicant_company": "Applicant Company",
    "planning_agent": "Planning Agent",
    "landowner": "Landowner",
    "housing_association": "Housing Association",
    "council": "Council",
}

METRIC_LABELS = {
    "count_schemes": "qualifying scheme{s}",
    "total_units": "total unit{s}",
    "total_affordable_units": "total affordable unit{s}",
}

# Defense in depth against the same "wrote the word null as a string" LLM
# quirk fixed at the source in app.extraction.run_extraction - a stale
# record from before that fix, or any other blank-ish placeholder, shouldn't
# be able to win a ranking outright.
_BLANK_LIKE_VALUES = {"none", "null", "n/a", "na", "not specified", "not applicable", "unknown", ""}


@dataclass
class AggregateAnswer:
    headline: str
    ranked: pd.DataFrame  # columns: [group_label, metric_label]
    group_by_column: str
    metric_column: str | None


def compute_aggregate_answer(df: pd.DataFrame, filters: SearchFilters) -> AggregateAnswer | None:
    """Computes the actual ranking in pandas against real data - the LLM
    only decided WHAT to compute (see parse_query), never the numbers
    themselves, so this can't hallucinate a wrong answer the way asking an
    LLM to "read" a table of scheme data directly could."""
    group_col = GROUP_BY_COLUMNS.get(filters.aggregate_group_by or "")
    if not group_col or group_col not in df.columns:
        return None

    metric = filters.aggregate_metric or "count_schemes"
    top_n = filters.aggregate_top_n or 5

    # Blank/missing entity names can't be ranked - most commonly a
    # registered_provider that hasn't been named yet, which would otherwise
    # dominate every ranking as a meaningless "top" answer.
    normalised = df[group_col].astype(str).str.strip().str.lower()
    present = df[df[group_col].notna() & ~normalised.isin(_BLANK_LIKE_VALUES)]

    if metric == "total_units":
        grouped = present.groupby(group_col)["Total Units"].sum(min_count=1)
        metric_col = "Total Units"
    elif metric == "total_affordable_units":
        grouped = present.groupby(group_col)["Affordable Units"].sum(min_count=1)
        metric_col = "Affordable Units"
    else:
        grouped = present.groupby(group_col).size()
        metric_col = "Schemes"
        metric = "count_schemes"

    grouped = grouped.dropna().sort_values(ascending=False)
    if grouped.empty:
        return None

    ranked = grouped.head(top_n).reset_index()
    ranked.columns = [group_col, metric_col]

    top_name, top_value = ranked.iloc[0][group_col], ranked.iloc[0][metric_col]
    unit = "" if top_value == 1 else "s"
    metric_phrase = METRIC_LABELS[metric].format(s=unit)
    group_label = group_col if group_col != "Registered Provider" else "registered provider (RP)"
    headline = f"**{top_name}** is the most active {group_label}, with **{int(top_value)} {metric_phrase}**."

    return AggregateAnswer(headline=headline, ranked=ranked, group_by_column=group_col, metric_column=metric_col)
