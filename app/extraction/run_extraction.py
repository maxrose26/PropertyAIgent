"""Per-application AI extraction orchestrator.

Runs the 3 LLM stages (entities, site intelligence, affordable classifier)
plus the 2 regex stages (housing mix, affordable snippets) for one
Application, then reconciles everything into scheme_intelligence fields.
"""
from __future__ import annotations

import json
import time

from openai import OpenAI

from app.db.models import Application, Document
from app.extraction import prompts
from app.extraction.affordable_snippets import build_snippets
from app.extraction.housing_mix import extract_housing_mix
from app.extraction.pdf_text import build_broad_sample_text, build_combined_priority_text
from app.extraction.reconcile import reconcile_scheme

# Deterministic extraction outcome taxonomy (AI Processing Reliability &
# Backlog Throughput) - the smallest set of buckets that distinguishes
# "nothing to extract from" (not a failure, never billed) from a genuine
# AI/API failure (retryable) from a malformed response (retryable) from an
# unexpected bug (retryable) - see stage_extraction in app.pipeline.
# run_weekly, the only caller that classifies against these.
OUTCOME_SUCCESS = "success"
OUTCOME_NO_USABLE_TEXT = "no_usable_text"
OUTCOME_AI_ERROR = "ai_error"
OUTCOME_INVALID_OUTPUT = "invalid_output"
OUTCOME_ERROR = "error"

_NULL_LIKE_STRINGS = {"null", "none", "n/a", "na"}


def has_usable_document_text(application: Application) -> bool:
    """True if run_extraction_for_application has anything to actually
    extract from - i.e. at least one Document with text_extracted=True and
    non-empty extracted_text. Factored out of run_extraction_for_application
    (which still starts with this exact check, unchanged) so stage_extraction
    can classify OUTCOME_NO_USABLE_TEXT BEFORE spending a bounded-workload
    "genuine attempt" slot on an application with nothing to send an LLM at
    all - no OpenAI call happens either way, this only changes what a
    candidate-scan counts as an attempt."""
    return any(d.text_extracted and d.extracted_text for d in application.documents)


def _sanitise_null_like_strings(data: dict) -> dict:
    """Every nullable string field in these schemas is typed ["string",
    "null"], so the model CAN return real JSON null - but sometimes writes
    the literal text "null" (or "None"/"N/A") as a string value instead,
    even though the schema permits an actual null. Confirmed a real case:
    four schemes ended up with registered_provider stored as the literal
    string "null" in the database, which then won an aggregate ranking
    ("most active registered provider") outright since it wasn't recognised
    as blank. Applied to every string field generically rather than just
    registered_provider, since the same LLM quirk can hit any of them.

    Deliberately NOT including "unknown"/"not specified"/"not applicable"
    here even though they sound null-ish - confirmed several schema fields
    (development_type, allocation_status, registered_provider_status) use
    "unknown"/"not_applicable" as genuine, required enum members with real
    meaning, not filler. A first pass at this wrongly nulled those out
    across 40 records before being caught and reverted."""
    return {
        key: (None if isinstance(value, str) and value.strip().lower() in _NULL_LIKE_STRINGS else value)
        for key, value in data.items()
    }


def _call_llm(client: OpenAI, prompt: str, schema: dict) -> dict:
    response = client.responses.create(
        model=prompts.MODEL,
        input=prompt,
        text={"format": {"type": "json_schema", "name": schema["name"], "schema": schema["schema"], "strict": True}},
    )
    return _sanitise_null_like_strings(json.loads(response.output_text))


def run_extraction_for_application(client: OpenAI, application: Application) -> dict | None:
    documents: list[Document] = [d for d in application.documents if d.text_extracted and d.extracted_text]
    if not documents:
        return None

    doc_tuples = [(d.doc_type, d.document_name or "", d.extracted_text or "") for d in documents]
    combined_text = build_combined_priority_text(doc_tuples)
    if not combined_text:
        return None

    # Broad-but-shallow sample across every document, for the two prompts that
    # go hunting for names rather than reading one document deeply.
    entity_sample_text = build_broad_sample_text(doc_tuples)

    reference = application.reference or ""
    address = application.address or ""
    proposal = application.proposal or ""
    application_type = application.application_type or ""
    applicant_name = application.applicant_name_raw or ""
    applicant_address = application.applicant_address_raw or ""

    # Regex pass
    housing_mix = extract_housing_mix(combined_text, application.estimated_unit_count)

    # Affordable evidence snippets across all documents
    snippet_rows: list[str] = []
    for doc in documents:
        for _, snippet in build_snippets(doc.extracted_text or ""):
            snippet_rows.append(snippet)
    snippets_text = "\n\n--- SNIPPET ---\n\n".join(snippet_rows)[:60000]

    # LLM: project entities
    entities = _call_llm(
        client,
        prompts.build_entities_prompt(
            reference, address, proposal, application_type, applicant_name, applicant_address, entity_sample_text
        ),
        prompts.ENTITIES_SCHEMA,
    )
    time.sleep(prompts.SLEEP_BETWEEN_CALLS)

    # LLM: site development intelligence - this one benefits from reading a
    # single document deeply (site area/density/allocation status tend to be
    # stated once, clearly, in the planning statement) so keep the
    # priority-ordered depth-first text here rather than the broad sample.
    site_intelligence = _call_llm(
        client,
        prompts.build_site_intelligence_prompt(reference, combined_text[:22000]),
        prompts.SITE_INTELLIGENCE_SCHEMA,
    )
    time.sleep(prompts.SLEEP_BETWEEN_CALLS)

    # LLM: affordable evidence classifier. Always call this even with no snippets -
    # it's the only stage that sees the portal Proposal text, so it can correct a
    # regex housing-mix total that latched onto an unrelated number (e.g. a nearby
    # strategic allocation mentioned for context rather than the scheme itself).
    affordable_classification = _call_llm(
        client,
        prompts.build_affordable_classifier_prompt(
            reference, proposal, application_type, application.status or "", application.decision or "",
            applicant_name, applicant_address,
            housing_mix.total_units, housing_mix.affordable_units, housing_mix.private_units,
            housing_mix.affordable_percentage, housing_mix.affordable_tenure_split or "",
            snippets_text or "(no affordable-housing evidence snippets found in extracted document text)",
        ),
        prompts.AFFORDABLE_SCHEMA,
    )
    time.sleep(prompts.SLEEP_BETWEEN_CALLS)

    return reconcile_scheme(
        housing_mix=housing_mix,
        affordable_classification=affordable_classification,
        entities=entities,
        site_intelligence=site_intelligence,
        portal_estimated_units=application.estimated_unit_count,
        application_category=application.application_category,
        proposal=proposal,
        applicant_name_raw=applicant_name or None,
    )
