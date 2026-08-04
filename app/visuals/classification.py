"""AI visual classification (Sprint 3C, "Allocation and Site-Plan Image
Extraction", Part 7) - runs a vision model ONLY on pages that have already
passed Stage 1 deterministic candidate detection
(app.visuals.page_detection) and been rendered (app.visuals.rendering).
Cost/hallucination control for WHICH pages reach this module lives in the
orchestration pipeline (app.visuals.pipeline, Part 16), not here.

Same "grounded facts, AI narrates/structures, never invents" discipline as
app.extraction.plan_evidence, adapted for an image instead of text: the
model classifies what it can actually SEE on the page, and is explicitly
forbidden from estimating measurements, inferring GIS geometry, guessing
which named Site/Allocation an image belongs to (that matching happens
separately, from text evidence - app.visuals.matching), or interpreting
colours/legends it can't actually see explained on the page.

Every classification this module produces is untrusted until a human
reviews it - review_status is forced to "needs_review" by the pipeline
regardless of what the model reports, never auto-applied the way a
high-confidence text fact can be (Part 9/Part 10: showing the WRONG image
is a worse failure than a wrong number).
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from openai import OpenAI

from app.visuals import IMAGE_TYPES

MODEL = "gpt-4o-mini"
# Bumped whenever the prompt or schema changes in a way that could change
# classification output - stored on every VisualEvidence row this pipeline
# creates, so a re-run under a NEW version is never treated as "already
# classified" against a classification made under an old one (Part 14).
PROMPT_VERSION = "visual-classification-v1"

_LIKELY_OBJECTS = ("site", "allocation", "unclear")

CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "is_useful": {"type": "boolean"},
        "image_type": {"type": "string", "enum": list(IMAGE_TYPES)},
        "likely_object": {"type": "string", "enum": list(_LIKELY_OBJECTS)},
        "reason": {"type": "string"},
        "confidence": {"type": "number"},
        "review_required": {"type": "boolean"},
    },
    "required": ["is_useful", "image_type", "likely_object", "reason", "confidence", "review_required"],
    "additionalProperties": False,
}

PROMPT = f"""You are looking at ONE rendered page from a UK planning application or Local Plan document. Decide whether this page is a genuinely useful SITE-PLAN-STYLE VISUAL - a drawing or map showing a site's location, boundary, or a proposed layout - and if so, classify it.

Valid image_type values: {", ".join(IMAGE_TYPES)}

Rules - follow these exactly:
- Only classify as "red_line_boundary" or "blue_line_boundary" if you can actually SEE a red or blue boundary line drawn on the page. A page titled "Site Plan" with no visible coloured boundary line is NOT a red_line_boundary or blue_line_boundary - use "site_location_plan" or "proposed_site_layout" instead, whichever the image actually shows.
- Never estimate an area, acreage, or any measurement from the image.
- Never describe or infer GIS geometry, coordinates, or a polygon.
- Never guess which specific named Site or Allocation this image belongs to - only report whether the image itself looks like it relates to a single development plot/application ("site"), a Local Plan policy map extract ("allocation"), or you genuinely cannot tell ("unclear"). Matching to a specific named object is done separately, from text evidence, not from you.
- Never infer a development phase from the image unless a phase label is genuinely legible on the page itself.
- Never interpret colours, hatching, or a legend's meaning unless that legend is visible on the same page.
- If the page is NOT a useful site-plan-style visual (a floor plan, an elevation, a photograph, a table, a block of text, a blank/administrative page), set is_useful to false and image_type to "unknown".
- confidence is your own genuine confidence in this classification, from 0.0 to 1.0.
- review_required must be true whenever is_useful is true - a human always reviews before an AI classification is trusted - and may also be true when you are unsure even if is_useful is false.
- reason must be a short, concrete description of what you actually see on the page - not a restatement of these rules.
"""


def _encode_image(image_path: str) -> str:
    return base64.b64encode(Path(image_path).read_bytes()).decode("ascii")


def normalise_classification(raw: dict) -> dict:
    """Deterministic, non-LLM clamp over the model's own structured output
    - defence in depth against a value technically valid per the JSON
    schema but outside what the rest of the pipeline should ever trust
    (e.g. a confidence outside [0, 1]), mirroring
    app.policy.evidence_validation's role for text facts."""
    image_type = raw.get("image_type")
    if image_type not in IMAGE_TYPES:
        image_type = "unknown"

    likely_object = raw.get("likely_object")
    if likely_object not in _LIKELY_OBJECTS:
        likely_object = "unclear"

    try:
        confidence = float(raw.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    is_useful = bool(raw.get("is_useful"))
    # A useful classification always needs review, regardless of what the
    # model itself reported - the pipeline layer additionally forces this
    # again at the VisualEvidence.review_status level, but normalising it
    # here too keeps this function's own output internally consistent.
    review_required = bool(raw.get("review_required")) or is_useful

    reason = raw.get("reason")
    reason = reason.strip() if isinstance(reason, str) else None

    return {
        "is_useful": is_useful,
        "image_type": image_type,
        "likely_object": likely_object,
        "reason": reason,
        "confidence": confidence,
        "review_required": review_required,
    }


def classify_page(client: OpenAI, image_path: str, usage_sink: list | None = None) -> dict:
    """Sends ONE rendered page image to the vision model, returns a
    normalised dict: {"is_useful", "image_type", "likely_object", "reason",
    "confidence", "review_required", "model", "prompt_version"}.

    usage_sink, if given, has the raw OpenAI response.usage object
    appended to it when the API reports one, for a caller that wants to
    total up token/image cost (Part 15/19: pipeline must report estimated
    AI cost) without changing this function's return type."""
    encoded = _encode_image(image_path)
    response = client.responses.create(
        model=MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": PROMPT},
                    {"type": "input_image", "image_url": f"data:image/png;base64,{encoded}"},
                ],
            }
        ],
        text={"format": {"type": "json_schema", "name": "visual_classification", "schema": CLASSIFICATION_SCHEMA, "strict": True}},
    )
    if usage_sink is not None and getattr(response, "usage", None) is not None:
        usage_sink.append(response.usage)

    result = normalise_classification(json.loads(response.output_text))
    result["model"] = MODEL
    result["prompt_version"] = PROMPT_VERSION
    return result
