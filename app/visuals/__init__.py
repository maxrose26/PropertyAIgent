"""Visual-document intelligence layer (Sprint 3C, "Allocation and
Site-Plan Image Extraction") - identifies, renders, classifies, stores
and displays source-backed page images (site location plans, red-line
boundaries, allocation maps, masterplans...) from planning and Local Plan
documents.

Images are evidence, not geometry: this package never produces a
boundary, an acreage, or GIS geometry - only a rendered page image with
full provenance back to the real document and page it came from. See
app.db.models.VisualEvidence for the persisted shape.

Not a GIS-polygon-extraction package - explicitly out of scope this sprint.
"""
from __future__ import annotations

# Normalised image-type vocabulary (Part 3). Preserve the raw source/
# document label separately (VisualEvidence.raw_classification_label) -
# this list is what the AI classifier and the UI both constrain to, never
# free text. "unknown" is a valid, storable value for a page that's a
# genuine candidate but whose specific type couldn't be determined with
# confidence - never guessed into a more specific bucket.
IMAGE_TYPES = (
    "allocation_map",
    "site_location_plan",
    "red_line_boundary",
    "blue_line_boundary",
    "proposed_site_layout",
    "masterplan",
    "phasing_plan",
    "parameter_plan",
    "access_plan",
    "policies_map_extract",
    "development_framework",
    "other_site_visual",
    "unknown",
)

# Human-readable labels for the UI (Part 11/Part 12) - kept alongside
# IMAGE_TYPES rather than derived by naive title-casing, since a couple
# (e.g. "policies_map_extract") read awkwardly that way.
IMAGE_TYPE_LABELS = {
    "allocation_map": "Allocation map",
    "site_location_plan": "Site location plan",
    "red_line_boundary": "Red line boundary",
    "blue_line_boundary": "Blue line boundary",
    "proposed_site_layout": "Proposed site layout",
    "masterplan": "Masterplan",
    "phasing_plan": "Phasing plan",
    "parameter_plan": "Parameter plan",
    "access_plan": "Access plan",
    "policies_map_extract": "Policies map extract",
    "development_framework": "Development framework",
    "other_site_visual": "Other site visual",
    "unknown": "Unclassified image",
}
