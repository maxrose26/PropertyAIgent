"""Web-search-grounded search for news coverage of a SPECIFIC development
that names a real contact person at the developer - a genuinely different
discovery channel from Apollo/Hunter (directory/email-pattern data) or
Companies House (statutory filings). Local/regional property press, trade
publications, and developer press releases routinely name a development
director, land director, or spokesperson for a named scheme even when that
person has no public Apollo/Hunter footprint at all - confirmed useful in
practice for the exact kind of company (a young SPV with no independent web
presence) that Apollo/Hunter struggle with most. Contact.source="news_article"
(see app/db/models.py) was already reserved for this, just never wired up to
a live search until now.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from openai import OpenAI

MODEL = "gpt-4o-mini"

_SCHEMA = {
    "type": "object",
    "properties": {
        "contacts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "full_name": {"type": "string"},
                    "job_title": {"type": ["string", "null"]},
                    "source_url": {"type": "string"},
                    "context": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["full_name", "job_title", "source_url", "context", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["contacts"],
    "additionalProperties": False,
}


@dataclass
class NewsContact:
    full_name: str
    job_title: str | None
    source_url: str
    context: str
    confidence: str  # high | medium | low


def find_scheme_news_contacts(
    client: OpenAI, developer_name: str, site_address: str, proposal_summary: str | None = None,
) -> list[NewsContact]:
    """Two calls, not one - confirmed a real reliability issue combining
    web_search_preview with strict structured output in a single call: the
    model would perform a real web_search_call, find genuinely good results
    (verified separately with the exact same query in free-text mode - it
    found 3 real, well-cited Berkeley Group contacts for Kidbrooke Village),
    but then return an empty contacts array anyway once forced to also
    conform to the strict JSON schema in that same turn. Splitting into a
    free-text search call (which reliably surfaces what it actually found)
    followed by a separate plain structured-extraction call (no tools, just
    reformatting the first call's own text) keeps the good recall from
    search while still producing clean structured data to store."""
    proposal_line = f"\nProposal: {proposal_summary}" if proposal_summary else ""
    search_prompt = f"""
Search news coverage (local/regional property press, trade publications such as Place North West, Insider Media,
React News, local newspapers, or the developer's own press releases) for THIS specific development, and identify
any named individual quoted or credited as working AT the developer company in connection with it.

Developer: {developer_name}
Site address: {site_address}{proposal_line}

Rules:
- Only include a person explicitly identified as employed by or representing "{developer_name}" itself (a
  development director, land director, managing director, spokesperson etc) - NOT journalists, council
  officers/planning committee members, or the planning agent/consultant (unless that same person is ALSO
  explicitly identified as in-house staff at the developer).
- Only include a person if you found a real, specific article or press-release URL naming them IN CONNECTION WITH
  THIS development - do not include someone only associated with the developer in general with no scheme-specific
  mention.
- For each person found, give their full name, job title, the article/press-release URL, and the relevant
  quote/context.
- If you find nothing meeting this bar, say so plainly rather than guessing or including a loose match.
"""
    search_response = client.responses.create(
        model=MODEL, input=search_prompt, tools=[{"type": "web_search_preview"}],
    )
    search_text = search_response.output_text
    if not search_text or not search_text.strip():
        return []

    extract_response = client.responses.create(
        model=MODEL,
        input=(
            "Extract any named contact person(s) at the developer from the following research notes into "
            "structured form. If the notes say nothing meeting the bar was found, return an empty contacts array.\n\n"
            f"{search_text}"
        ),
        text={"format": {"type": "json_schema", "name": "scheme_news_contacts", "schema": _SCHEMA, "strict": True}},
    )
    data = json.loads(extract_response.output_text)
    return [NewsContact(**c) for c in data.get("contacts", [])]
