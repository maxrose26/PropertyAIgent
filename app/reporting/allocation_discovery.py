"""Allocation Discovery (Sprint 4.5) - the customer-facing view model behind
the redesigned "Local Plan Sites" page (app/ui/pages/3_Local_Plan_Sites.py).

Mirrors app.reporting.site_profile's role for the Site Profile: all query
assembly, filtering, sorting, category membership and deterministic
narrative ("why it matters" / "investigate next") logic lives here as pure,
independently-testable functions, so app/ui/pages/3_Local_Plan_Sites.py stays
presentation-only (CLAUDE.md: "keep business logic out of the UI").

Reuses existing architecture throughout rather than re-deriving anything:
- app.ui.common.load_applications_for_sites for batched Application loading
  (never one query per allocation);
- app.visuals.site_view.build_allocation_visual_summaries /
  build_plan_wide_policies_map for batched VisualEvidence lookups;
- app.pipeline.lapse_tracking.compute_lapse_status for the same
  granted-but-not-commenced signal Site Profile's Opportunity Position
  already uses - no parallel "has this started" logic invented here;
- app.policy.status.PLAN_STATUSES / ALLOCATION_STATUSES as the closed
  vocabularies status wording is checked against, never re-derived from
  keyword matching a second time.

build_allocation_discovery(session) is the ONE DB-touching entrypoint - a
bounded, small, fixed number of batched queries regardless of how many
allocations exist (see its own docstring for the exact query budget).
Everything else in this module (capacity formatting, search, filters, sort,
categories, why-it-matters/investigate-next) is pure Python operating on
already-built card dicts, no session required.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import LocalPlan, LocalPlanSite, Site
from app.extraction.local_plan import assess_delivery_scope
from app.pipeline.lapse_tracking import BUILD_STATUS_LABELS, compute_lapse_status
from app.ui.common import load_applications_for_sites
from app.visuals import IMAGE_TYPE_LABELS
from app.visuals.site_view import build_allocation_visual_summaries, build_plan_wide_policies_map

# A council-agnostic, platform-defined threshold, deliberately reusing the
# exact figure app.reporting.site_profile.MAJOR_UNIT_THRESHOLD already
# established for "major scheme" wording on the Site Profile - one
# documented bar for the word "major" across the product, not a second,
# different number invented here.
MAJOR_HOUSING_CAPACITY_THRESHOLD = 100

FIVE_YEAR_SUPPLY_WARNING_THRESHOLD = 5.0

# The "undeveloped/not commenced" evidence signal never treats absence of
# data as proof - only a genuinely granted allocation whose lapse status
# says "no confirmed start of works yet" (the same signal Site Profile's
# Opportunity Position already surfaces as "an undeveloped phase") counts.
_NOT_COMMENCED_LAPSE_STATUSES = {"safe", "approaching", "lapsed"}

INTENDED_USE_LABELS = {
    "residential": "Residential",
    "employment": "Employment",
    "mixed use": "Mixed use",
    None: "Not stated",
}

# app.policy.status.PLAN_STATUSES, bucketed into the three customer-facing
# groups Part 5's filter asks for, plus a friendly label and the Part 8
# status-chip colour/icon kind (added to app.ui.shell._BADGE_KIND_STYLE) -
# derived entirely from the plan's own NORMALISED status (never re-reads
# raw_status keyword text a second time), so this can never disagree with
# what app.policy.status.normalise_plan_status already decided.
PLAN_STATUS_META: dict[str | None, dict] = {
    "preparation": {"label": "Preparation", "bucket": "emerging", "chip_kind": "plan_consultation"},
    "early_consultation": {"label": "Early consultation (Regulation 18)", "bucket": "emerging", "chip_kind": "plan_consultation"},
    "issues_and_options": {"label": "Issues and options", "bucket": "emerging", "chip_kind": "plan_consultation"},
    "draft_consultation": {"label": "Draft consultation (Regulation 18)", "bucket": "emerging", "chip_kind": "plan_consultation"},
    "preferred_options": {"label": "Preferred options", "bucket": "emerging", "chip_kind": "plan_consultation"},
    "proposed_submission": {"label": "Proposed submission (Regulation 19)", "bucket": "emerging", "chip_kind": "plan_emerging"},
    "submitted": {"label": "Submitted", "bucket": "emerging", "chip_kind": "plan_emerging"},
    "examination": {"label": "Examination", "bucket": "emerging", "chip_kind": "plan_examination"},
    "main_modifications": {"label": "Main modifications", "bucket": "emerging", "chip_kind": "plan_examination"},
    "inspector_report": {"label": "Inspector's report", "bucket": "emerging", "chip_kind": "plan_examination"},
    "adopted": {"label": "Adopted", "bucket": "adopted", "chip_kind": "plan_adopted"},
    "paused": {"label": "Paused", "bucket": "other", "chip_kind": "plan_unknown"},
    "withdrawn": {"label": "Withdrawn", "bucket": "other", "chip_kind": "plan_withdrawn"},
    "superseded": {"label": "Superseded", "bucket": "other", "chip_kind": "plan_withdrawn"},
    "unknown": {"label": "Status uncertain", "bucket": "other", "chip_kind": "plan_unknown"},
    None: {"label": "Status uncertain", "bucket": "other", "chip_kind": "plan_unknown"},
}

ALLOCATION_REVIEW_STATUS_META = {
    "auto_applied": {"label": "Auto-applied match", "badge_kind": "pending"},
    "needs_confirmation": {"label": "Needs confirmation", "badge_kind": "review"},
    "confirmed": {"label": "Confirmed", "badge_kind": "confirmed"},
    "rejected": {"label": "Rejected", "badge_kind": "rejected"},
    None: {"label": "Not yet reviewed", "badge_kind": "pending"},
}

# app.policy.status.PLAN_STATUSES' own natural progression order (earliest
# stage first) - reused as-is for the "Plan stage" sort option rather than
# inventing a second ranking of the same 15 values.
_PLAN_STAGE_ORDER = (
    "preparation", "early_consultation", "issues_and_options", "draft_consultation", "preferred_options",
    "proposed_submission", "submitted", "examination", "main_modifications", "inspector_report",
    "adopted", "paused", "withdrawn", "superseded", "unknown",
)
_PLAN_STAGE_RANK = {status: i for i, status in enumerate(_PLAN_STAGE_ORDER)}

_BUCKET_RELEVANCE_RANK = {"adopted": 0, "emerging": 1, "other": 2}


# --- Capacity ----------------------------------------------------------------


def format_capacity(allocation: LocalPlanSite) -> dict:
    """Never combines incompatible figures into one invented number (Part
    14) - minimum/indicative/maximum are shown for exactly what they are,
    labelled, and a genuine range only when both a minimum and a maximum are
    stated AND they actually differ.

    Sprint 4.5a ("Commercial Polish", Part 3) - reads as a natural
    commercial sentence fragment ("Approximately 250 homes") rather than a
    database field-and-value pair ("Capacity: 250") - "Approximately" is
    used for both the minimum-only and indicative-only cases since both are
    genuinely non-exact estimates (a stated minimum is a floor, not a
    promise of the final count; an indicative figure is explicitly a
    council's own estimate) - never claims more precision than the source
    evidence actually supports."""
    minimum = allocation.minimum_dwellings
    indicative = allocation.indicative_capacity
    maximum = allocation.maximum_capacity

    if minimum is None and indicative is None and maximum is None:
        return {"kind": "unknown", "display": "Capacity not identified", "value": None}
    if minimum is not None and maximum is not None and minimum != maximum:
        return {"kind": "range", "display": f"{minimum:,}–{maximum:,} homes", "value": maximum}
    if minimum is not None:
        return {"kind": "minimum", "display": f"Approximately {minimum:,} homes", "value": minimum}
    if maximum is not None:
        return {"kind": "maximum", "display": f"Up to {maximum:,} homes", "value": maximum}
    return {"kind": "indicative", "display": f"Approximately {indicative:,} homes", "value": indicative}


def kpi_capacity_contribution(allocation: LocalPlanSite) -> dict:
    """Evidence Terminology Amendment (following Sprint 4.5a) - the Total
    Homes Identified KPI's own documented, deterministic rule. Distinct
    from format_capacity's DISPLAY value above: that value picks a range's
    MAXIMUM (a reasonable single ordering key for sorting/filtering cards),
    which is exactly the figure Part 2/4 of this amendment says must never
    be silently summed into one "homes identified" total, since a maximum
    is an upper bound, not a count of homes this platform has actually
    identified.

    Only counts genuine FLOOR evidence, one documented rule, never a mix
    of incompatible measures added as if equivalent:
      - a stated minimum_dwellings (including the minimum half of a
        range - minimum_dwellings is set whenever a range exists, so this
        branch already covers ranges too) -> counted at face value, not
        flagged as an estimate: a plan's own stated minimum IS a genuine
        floor ("at least this many homes here").
      - maximum_capacity alone, with no minimum stated -> EXCLUDED
        entirely. An upper bound alone is not evidence of how many homes
        are identified as a floor; including it would overstate exactly
        what Part 4 warns against.
      - indicative_capacity alone, with no minimum stated -> counted, but
        flagged is_estimate=True (a council's own indicative figure is an
        estimate, not a stated floor) - the caller uses this flag to
        relabel the KPI "Indicative homes identified" rather than
        presenting the aggregate as a firm total (Part 2).
      - nothing stated -> excluded (never treated as zero)."""
    minimum = allocation.minimum_dwellings
    indicative = allocation.indicative_capacity

    if minimum is not None:
        return {"value": minimum, "is_estimate": False}
    if indicative is not None:
        return {"value": indicative, "is_estimate": True}
    return {"value": None, "is_estimate": False}


# A separate, higher bar than MAJOR_HOUSING_CAPACITY_THRESHOLD, used ONLY
# to choose between "Residential allocation" and "Large residential
# allocation" wording - Evidence Terminology Amendment (following Sprint
# 4.5a): capacity alone is explicitly NOT evidence of development TYPE
# (see development_type_label's own docstring) - "Strategic urban
# extension" is reserved for allocations with an explicit textual signal
# (title/category wording), never inferred from scale. Using capacity to
# choose WORDING is not the same as using it to change a card's visual
# weight (Sprint 4.5a's product principle) - every card renders with
# identical size/border/prominence regardless of this label; only the
# descriptive text differs, grounded in the allocation's own stated
# figures/evidence.
LARGE_RESIDENTIAL_CAPACITY_THRESHOLD = 1000

# Explicit textual evidence required before "Strategic urban extension" is
# ever used - deliberately NOT triggered by capacity (Evidence Terminology
# Amendment, Part 1: "Capacity alone is not evidence of development
# type"). Matched against site_name and category - the only free-text
# fields this row carries that could genuinely state a planning typology.
_STRATEGIC_EXTENSION_KEYWORDS = ("urban extension", "strategic extension", "strategic urban")


def development_type_label(*, site_name: str | None, category: str | None, intended_use: str | None, capacity_value: int | None) -> str | None:
    """Sprint 4.5a ("Commercial Polish", Part 2; tightened by the Evidence
    Terminology Amendment) - a concise, deterministic commercial
    description beneath the allocation title, built ONLY from evidence
    already stored on the row (site_name, category, intended_use,
    capacity) - never a fresh classification invented for this purpose.

    "Strategic urban extension", "Garden village allocation" and "Urban
    regeneration allocation" are planning TYPOLOGY claims - they are used
    ONLY when the row's own title or category text explicitly says so.
    Capacity is used exclusively to choose between two capacity-neutral
    housing descriptions ("Residential allocation" vs "Large residential
    allocation") - it is never allowed to promote an allocation into a
    specific typology label on its own (Part 1: "Do not infer garden
    village, urban extension, regeneration area or other planning
    typologies from scale alone").

    Returns None when nothing in the existing evidence supports a
    description more specific than the bare word "allocation" - an honest
    omission, not a guess."""
    name = (site_name or "").lower()
    cat = (category or "").lower()

    if "garden village" in name:
        return "Garden village allocation"
    if "regeneration" in name or "regeneration" in cat:
        return "Urban regeneration allocation"
    if any(keyword in name or keyword in cat for keyword in _STRATEGIC_EXTENSION_KEYWORDS):
        return "Strategic urban extension"
    if intended_use == "employment":
        return "Employment allocation"
    if intended_use == "mixed use":
        return "Mixed-use allocation"
    if intended_use == "residential":
        if capacity_value is not None and capacity_value >= LARGE_RESIDENTIAL_CAPACITY_THRESHOLD:
            return "Large residential allocation"
        return "Residential allocation"
    return None


def is_major_housing_allocation(intended_use: str | None, capacity_value: int | None) -> bool:
    """Major Housing Allocation (Part 6): a housing or mixed-use allocation
    at or above MAJOR_HOUSING_CAPACITY_THRESHOLD - no invented ranking score,
    just a documented, fixed capacity bar against the one already-stated
    figure."""
    if intended_use not in ("residential", "mixed use"):
        return False
    return capacity_value is not None and capacity_value >= MAJOR_HOUSING_CAPACITY_THRESHOLD


# --- Matched / unmatched / linked-application wording (Part 13) -------------


def matched_status_text(matched: bool) -> str:
    return "Matched to a Site" if matched else "Not matched to a Site"


def matched_status_help() -> str:
    return (
        "\"Matched\" means PropertyAIgent has linked this allocation to a scraped Site. \"Not matched\" means no "
        "link has been made in this platform - it does not mean the allocation has no development, no planning "
        "application, or is undeveloped in reality."
    )


def linked_application_text(count: int) -> str:
    if count == 0:
        return "No linked Application"
    return f"{count} linked Application{'s' if count != 1 else ''}"


def linked_application_help() -> str:
    return "Reflects Applications currently linked in PropertyAIgent only - not confirmation that no application exists in reality."


# --- Why it matters / investigate next (Part 9 / Part 10) -------------------
#
# Deterministic, evidence-grounded, no AI, no permission-likelihood or
# investment-advice language - the same discipline as
# app.reporting.site_profile.build_opportunity_position. Every reason is
# traceable to a fact already present on the card dict this module builds;
# nothing here re-derives or estimates anything fresh.


def _why_it_matters_reasons(card: dict) -> list[str]:
    """Sprint 4.5a ("Commercial Polish", Part 5) rewrote every string below
    for a more commercially natural tone (e.g. "One of the council's
    planned residential growth locations" rather than the bare category
    label "Major housing allocation") - the underlying SIGNALS and their
    priority order are unchanged from Sprint 4.5, only the wording. Still
    entirely deterministic, still grounded in facts already present on the
    card dict, still free of permission-likelihood or investment-advice
    language (Part 6's explicit bans: "good buying opportunity",
    "acquisition opportunity", "strong investment", "likely to gain
    planning permission")."""
    reasons: list[str] = []
    capacity_value = card["capacity"]["value"]

    if card["plan_status_bucket"] == "adopted" and card["major_housing"]:
        reasons.append(
            f"One of {card['council_name']}'s planned {card['intended_use_label'].lower()} growth locations, "
            f"adopted with capacity for approximately {capacity_value:,} homes."
        )
    elif card["plan_status_bucket"] == "adopted":
        reasons.append(f"Confirmed as part of {card['plan_name']}, the council's adopted development plan.")
    elif card["plan_status_bucket"] == "emerging" and card["linked_application_count"] == 0:
        reasons.append(
            "Identified for future development through the emerging Local Plan, with no linked planning "
            "application currently held by the platform."
        )
    elif card["plan_status_bucket"] == "emerging":
        reasons.append(f"Identified for future development through the emerging Local Plan ({card['plan_name']}).")

    if card["linked_application_count"] == 0 and card["plan_status_bucket"] != "emerging":
        reasons.append("No linked planning application currently held by the platform for this allocation.")

    if card["matched"] and card["lapse_status"] in _NOT_COMMENCED_LAPSE_STATUSES:
        reasons.append("A linked planning permission exists but has not yet commenced, based on available filing evidence.")

    if card["council_five_year_supply"] is not None and card["council_five_year_supply"] < FIVE_YEAR_SUPPLY_WARNING_THRESHOLD:
        reasons.append(
            f"{card['council_name']} currently reports a housing land supply below the five-year requirement "
            f"({card['council_five_year_supply']:.2f} years)."
        )

    if card["visual_status"] == "confirmed":
        reasons.append("Confirmed allocation mapping is available, though development progress has not yet been established.")
    elif card["visual_status"] == "needs_review" or card["visual_fallback"] is not None:
        reasons.append("Suggested allocation mapping is available but has not yet been confirmed.")

    if card["is_multi_authority"] and card["major_housing"]:
        reasons.append("A cross-boundary strategic allocation shared across multiple authorities.")

    if not reasons:
        reasons.append("No additional planning signals identified from evidence currently held by the platform.")
    return reasons


# --- "No linked planning application" commercial signal --------------------
#
# Sprint 4.5b ("Entity Search + Allocation Card Refinement", Part 1/2)
# removed this signal from the gallery card - the original Sprint 4.5a
# "highlighted panel on every card" framing made every unmatched allocation
# (the majority of the gallery) show the same repeated block, which read as
# visual noise rather than a strong signal. The card now shows nothing
# negative at all when there is no link (the existing "No Linked
# Application" discovery category is the way to find these allocations);
# a positive, compact tag appears instead ONLY where a link genuinely
# exists (see LINKED_APPLICATION_TAG_LABEL / allocation_card's badge row).
# This constant pair is now Detail-state-only wording (Part 3: "Keep this
# detail-level wording rather than putting it on every gallery card").

NO_LINKED_APPLICATION_PANEL_TITLE = "No linked planning application currently identified"
NO_LINKED_APPLICATION_PANEL_MESSAGE = (
    "PropertyAIgent has not matched this allocation to a planning application. This may warrant further "
    "investigation to determine whether an application exists or whether the allocation remains at a "
    "pre-application stage."
)

# Part 3's own, more concise detail-state wording - deliberately distinct
# from the panel text above (still used as the "no development identified"
# evidence-gap signal below Part 3's linked-application section) rather
# than reusing it, per that Part's explicit wording.
ALLOCATION_DETAIL_NO_APPLICATION_MESSAGE = (
    "No planning application is currently linked to this allocation in PropertyAIgent."
)
ALLOCATION_DETAIL_NO_APPLICATION_NOTE = "An application may exist but not yet have been matched."

# Part 2 - the compact positive tag, shown in the card's badge row only
# when linked_application_count > 0 (never inferred - a linked Application
# only exists here once a Site is genuinely matched, see
# build_allocation_discovery's own batched Application lookup, which never
# guesses a link).
LINKED_APPLICATION_TAG_LABEL = "Planning application linked"


def has_trusted_linked_application(card: dict) -> bool:
    """THE ONE canonical definition of "a sufficiently trusted linked
    Planning Application exists" (Sprint 4.5b Product Owner amendment,
    Part 5: "There must be one canonical definition of trusted linked
    planning application... used wherever the product means a confirmed/
    trusted Application relationship"). Every one of the following reads
    this single function rather than re-deriving the same boolean:
    show_linked_application_tag (the gallery badge), apply_filters's
    application_linkage filter, CATEGORY_DEFINITIONS's "No Linked
    Application" category, build_matching_attributes's
    has_linked_application field, and build_summary_metrics's
    no_linked_application KPI. app.reporting.entity_search's cross-link
    labels also call this (not duplicated there either).

    linked_application_count alone isn't enough - if the allocation's OWN
    match to that Site is itself still needs_confirmation (an unreviewed,
    possibly-wrong suggestion - see ALLOCATION_REVIEW_STATUS_META), a
    confident "linked" claim would overstate what's actually been
    confirmed, even though the underlying Application row is perfectly
    real. "auto_applied" is trusted - that review state already means the
    platform's own deterministic matching pipeline applied it without
    flagging ambiguity, the same trust level card["matched"] and every
    other confident card element already extends to an auto_applied match.

    Before this fix, apply_filters/CATEGORY_DEFINITIONS/build_matching_
    attributes/build_summary_metrics each independently checked only
    `linked_application_count > 0`, disagreeing with the badge's own
    (correct) needs_confirmation exclusion - an allocation could pass a
    "Linked" filter while showing no badge at all. This function is the
    fix: one definition, one place, every caller reads it."""
    return card["linked_application_count"] > 0 and card["review_status"] != "needs_confirmation"


def has_trusted_site_match(card: dict) -> bool:
    """A DELIBERATELY SEPARATE canonical definition from
    has_trusted_linked_application above (Sprint 4.5b Product Owner
    amendment, Part 8: "Audit the distinction between Matched Site and
    Planning Application linked. These are not necessarily equivalent.").
    This one answers "is this allocation's own match to a Site itself
    trustworthy" - true whenever a Site is matched at all AND that match
    isn't still needs_confirmation, regardless of whether any Application
    has been filed on that Site yet (a freshly-matched Site with zero
    Applications is still a genuine, trustworthy Site match). Used only
    for the "Linked planning Site" / "Linked to allocation X" cross-link
    labels in app.reporting.entity_search (Part 13: "Do not present
    needs_confirmation/fuzzy relationships as confirmed") - never for the
    Application-linkage badge/filter/KPI above, which read
    has_trusted_linked_application instead. card["matched"] itself (Site
    genuinely matched, regardless of review confidence) remains its own,
    unchanged, third concept - see build_summary_metrics's
    matched_to_sites KPI, deliberately left reading card["matched"]."""
    return card["matched"] and card["review_status"] != "needs_confirmation"


def build_linked_application_summaries(linked_applications: list, matched_site: Site | None) -> list[dict]:
    """Part 3 - one dict per linked Application, never picking one and
    hiding the rest. `units` prefers the AI-reconciled SchemeIntelligence
    figure (the same total_units_final every other Application-facing view
    in this codebase trusts - see app.ui.common.aggregate_scheme_fields's
    own docstring for why) and falls back to the portal listing's own
    estimated_unit_count only when no reconciled figure exists yet -
    never a fresh estimate invented here. Build/commencement status is
    deliberately NOT duplicated per-application: it's a Site-level signal
    (app.pipeline.lapse_tracking.compute_lapse_status already reasons
    across every linked Application together, see build_allocation_card's
    own call site) - inventing a second, per-Application version of that
    same judgement here would risk disagreeing with it."""
    site_address = matched_site.display_address if matched_site else None
    summaries = []
    for app in linked_applications:
        si = getattr(app, "scheme_intelligence", None)
        units = None
        if si is not None and si.total_units_final:
            units = si.total_units_final
        elif app.estimated_unit_count:
            units = app.estimated_unit_count
        summaries.append({
            "id": app.id,
            "reference": app.reference,
            "site_address": site_address or app.address,
            "status": app.status,
            "decision": app.decision,
            "units": units,
            "summary_url": app.summary_url,
        })
    return summaries


def _no_development_identified(card: dict) -> bool:
    """True only when the platform genuinely holds no evidence of
    development activity for this allocation - never inferred from an
    unmatched Site alone (Part 13: unmatched is not the same claim as "no
    development"). A matched Site with a real build-status signal (even a
    weak one, e.g. "no completions yet") is still evidence of SOME
    activity being tracked, so it does not qualify."""
    if card["linked_application_count"] > 0:
        return False
    if not card["matched"]:
        return True
    return card["build_status"] in (None, "unknown")


def show_no_application_panel(card: dict) -> bool:
    """Part 6's four-part conjunction: the allocation exists (trivially
    true for any card), is adopted or emerging (not withdrawn/paused/
    superseded/uncertain - a signal worth surfacing only for a plan
    genuinely still in force or being progressed), has no linked
    Application, and no development has been identified at all."""
    return (
        card["plan_status_bucket"] in ("adopted", "emerging")
        and card["linked_application_count"] == 0
        and _no_development_identified(card)
    )


def _investigate_next(card: dict) -> str:
    if card["visual_status"] == "confirmed":
        return "Review the confirmed allocation map."
    if card["visual_status"] == "needs_review":
        return "Review suggested imagery awaiting confirmation."
    if not card["matched"] and card["linked_application_count"] == 0:
        return "Investigate whether an Application exists but has not been matched to this allocation."
    if card["matched"] and card["lapse_status"] in _NOT_COMMENCED_LAPSE_STATUSES:
        return "Verify whether development has commenced."
    if card["plan_status_bucket"] == "emerging":
        return "Review the emerging plan evidence."
    if card["capacity"]["kind"] == "unknown":
        return "Confirm the allocation's current capacity."
    if card["review_status"] == "needs_confirmation":
        return "This allocation's match/status is awaiting confirmation in Administration."
    return "Review the allocation's full detail for further evidence."


# --- Card assembly (pure - no DB access) -------------------------------------


def build_allocation_card(
    allocation: LocalPlanSite, *, plan: LocalPlan | None, council_name: str, council_codes_on_plan: list[str],
    matched_site: Site | None, linked_applications: list, visual_summary: dict, visual_fallback,
    council_five_year_supply: float | None,
) -> dict:
    """Pure assembly of one allocation's full card - every input is already
    loaded by build_allocation_discovery's batched queries; this function
    issues no queries of its own."""
    plan_status = plan.status if plan else (allocation.plan_status or None)
    plan_meta = PLAN_STATUS_META.get(plan_status, PLAN_STATUS_META[None])
    capacity = format_capacity(allocation)
    kpi_capacity = kpi_capacity_contribution(allocation)
    intended_use_label = INTENDED_USE_LABELS.get(allocation.intended_use, allocation.intended_use or "Not stated")
    major_housing = is_major_housing_allocation(allocation.intended_use, capacity["value"])
    development_type = development_type_label(
        site_name=allocation.site_name, category=allocation.category,
        intended_use=allocation.intended_use, capacity_value=capacity["value"],
    )

    matched = matched_site is not None
    linked_application_count = len(linked_applications)

    lapse_status = None
    build_status = None
    build_status_label = None
    delivery_note = None
    if matched:
        lapse = compute_lapse_status(linked_applications, matched_site)
        lapse_status = lapse["status"]
        build_status = lapse["build_status"]
        build_status_label = BUILD_STATUS_LABELS.get(build_status) if build_status not in (None, "unknown") else None
        matched_total_units = None
        for app in linked_applications:
            si = getattr(app, "scheme_intelligence", None)
            if si and si.total_units_final:
                matched_total_units = si.total_units_final
                break
        scope = assess_delivery_scope(allocation.minimum_dwellings, matched_total_units)
        delivery_note = scope["note"] if scope["status"] != "unknown" else None

    def _visual_card(img) -> dict | None:
        if img is None:
            return None
        return {
            "id": img.id,
            "image_path": img.thumbnail_path or img.image_path,
            "label": IMAGE_TYPE_LABELS.get(img.image_type, img.image_type),
            "source_title": img.source_document_title,
            "source_page": img.source_page,
            "source_url": img.source_document_url,
            "confidence": img.extraction_confidence,
            "review_status": img.review_status,
        }

    visual_status = visual_summary.get("status", "none")
    visual_primary = _visual_card(visual_summary.get("primary"))
    visual_fallback_card = None
    if visual_status == "none" and visual_fallback is not None:
        visual_fallback_card = _visual_card(visual_fallback)

    review_meta = ALLOCATION_REVIEW_STATUS_META.get(allocation.review_status, ALLOCATION_REVIEW_STATUS_META[None])

    plan_page_url = (
        f"{allocation.source_document_url}#page={allocation.source_page}"
        if allocation.source_document_url and allocation.source_page else allocation.source_document_url
    )

    card = {
        "id": allocation.id,
        "site_name": allocation.site_name,
        "policy_reference": allocation.policy_reference,
        "council_code": allocation.council_code,
        "council_name": council_name,
        "local_plan_id": allocation.local_plan_id,
        "plan_name": plan.plan_name if plan else allocation.plan_name,
        "plan_status": plan_status,
        "plan_status_label": plan_meta["label"],
        "plan_status_bucket": plan_meta["bucket"],
        "plan_status_chip_kind": plan_meta["chip_kind"],
        "is_multi_authority": len(council_codes_on_plan) > 1,
        "cross_boundary_councils": [c for c in council_codes_on_plan if c != allocation.council_code],
        "intended_use": allocation.intended_use,
        "intended_use_label": intended_use_label,
        "development_type": development_type,
        "capacity": capacity,
        "kpi_capacity_contribution": kpi_capacity,
        "major_housing": major_housing,
        "category": allocation.category,
        "allocation_status": allocation.allocation_status,
        "raw_allocation_status": allocation.raw_allocation_status,
        "progression_signal": allocation.progression_signal,
        "review_status": allocation.review_status,
        "review_status_label": review_meta["label"],
        "review_status_badge_kind": review_meta["badge_kind"],
        "duplicate_classification": allocation.duplicate_classification,
        "matched": matched,
        "matched_site_id": allocation.matched_site_id,
        "matched_site_address": matched_site.display_address if matched_site else None,
        "match_confidence": allocation.match_confidence,
        "linked_application_count": linked_application_count,
        "matched_summary": f"{matched_status_text(matched)} · {linked_application_text(linked_application_count)}",
        "matched_summary_help": f"{matched_status_help()} {linked_application_help()}",
        "lapse_status": lapse_status,
        "build_status": build_status,
        "build_status_label": build_status_label,
        "delivery_note": delivery_note,
        "visual_status": visual_status,
        "visual_primary": visual_primary,
        "visual_others": [c for c in (_visual_card(i) for i in visual_summary.get("others", [])) if c],
        "visual_fallback": visual_fallback_card,
        "council_five_year_supply": council_five_year_supply,
        "source_document_url": allocation.source_document_url,
        "source_page": allocation.source_page,
        "plan_page_url": plan_page_url,
        "last_checked": plan.last_checked if plan else None,
        "updated_at": allocation.updated_at,
        "latitude": allocation.latitude,
        "longitude": allocation.longitude,
    }
    card["why_it_matters_reasons"] = _why_it_matters_reasons(card)
    card["why_it_matters"] = card["why_it_matters_reasons"][0]
    card["investigate_next"] = _investigate_next(card)
    # Sprint 4.5b, Part 1/2 - show_no_application_panel/its title+message
    # are kept for the "no development identified" evidence-gap panel a
    # future caller may still want, but allocation_card() itself no longer
    # renders them (see LINKED_APPLICATION_TAG_LABEL / show_linked_
    # application_tag below for the card-level replacement, and
    # ALLOCATION_DETAIL_NO_APPLICATION_MESSAGE for the detail-state one).
    card["show_no_application_panel"] = show_no_application_panel(card)
    card["no_application_panel_title"] = NO_LINKED_APPLICATION_PANEL_TITLE
    card["no_application_panel_message"] = NO_LINKED_APPLICATION_PANEL_MESSAGE
    card["show_linked_application_tag"] = has_trusted_linked_application(card)
    card["linked_application_tag_label"] = LINKED_APPLICATION_TAG_LABEL
    card["linked_applications"] = build_linked_application_summaries(linked_applications, matched_site)
    card["detail_no_application_message"] = ALLOCATION_DETAIL_NO_APPLICATION_MESSAGE
    card["detail_no_application_note"] = ALLOCATION_DETAIL_NO_APPLICATION_NOTE
    card["matching_attributes"] = build_matching_attributes(card)
    return card


# --- Structured attributes for future matching (Part 9) ---------------------
#
# NOT a ranking, score, or recommendation - PropertyAIgent never decides
# what the "best" allocation is (Sprint 4.5a's product principle: different
# users value different opportunities, and only future user-defined
# personalisation should determine relevance). This is a stable, narrowly-
# named subset of the full card dict - the exact attribute list Part 9
# names (capacity, intended use, planning status, build status, linked
# application, matched site, visual evidence, review status, council,
# Local Plan, housing supply context) - with every display-only/formatting
# field left out, so a future matching feature has one clean, documented
# seam to read from rather than reaching into the full display-oriented
# card dict. Also rendered today (Part 9: "do not expose these purely for
# debugging") as the Allocation Detail view's compact "Key attributes"
# reference list - genuinely useful now for a user manually comparing
# allocations, not just inert plumbing for later.


def build_matching_attributes(card: dict) -> dict:
    return {
        "capacity_value": card["capacity"]["value"],
        "capacity_kind": card["capacity"]["kind"],
        "intended_use": card["intended_use"],
        "planning_status_bucket": card["plan_status_bucket"],
        "planning_status": card["plan_status"],
        "build_status": card["build_status"],
        # Canonical trusted definition (Sprint 4.5b Product Owner
        # amendment, Part 5) - the same has_trusted_linked_application a
        # future matching feature would need "linked/no linked Planning
        # Application" to mean the same thing everywhere else it appears.
        "has_linked_application": has_trusted_linked_application(card),
        "linked_application_count": card["linked_application_count"],
        "matched_site_id": card["matched_site_id"],
        "visual_evidence_status": card["visual_status"],
        "review_status": card["review_status"],
        "council_code": card["council_code"],
        "local_plan_id": card["local_plan_id"],
        "council_five_year_supply": card["council_five_year_supply"],
    }


# --- Batched, bounded top-level builder --------------------------------------


def build_allocation_discovery(session, *, council_codes: list[str] | None = None) -> dict:
    """The one DB-touching entrypoint. Fixed query budget regardless of
    allocation count:
      1. LocalPlanSite (+ selectinload LocalPlan + LocalPlan.council_links -
         2 further batched SELECTs, never one per allocation/plan);
      2. matched Sites, batched by id;
      3-4. linked Applications, batched via load_applications_for_sites
         (2 queries total);
      5. allocation-scoped VisualEvidence, batched;
      6. plan-wide Policies Map fallback, batched.
    council_five_year_supply is read directly off the already-loaded
    LocalPlan row (LocalPlan.five_year_supply_years) - no extra query.
    Council display names come from app.config.load_councils(), a config
    file read, never a database query."""
    from app.config import load_councils

    query = select(LocalPlanSite).options(
        selectinload(LocalPlanSite.local_plan).selectinload(LocalPlan.council_links)
    )
    if council_codes:
        query = query.where(LocalPlanSite.council_code.in_(council_codes))
    allocations = list(session.execute(query).scalars())

    council_config = load_councils()

    matched_site_ids = [a.matched_site_id for a in allocations if a.matched_site_id]
    sites_by_id: dict[int, Site] = {}
    if matched_site_ids:
        sites_by_id = {
            s.id: s for s in session.execute(select(Site).where(Site.id.in_(matched_site_ids))).scalars()
        }

    apps_by_site = load_applications_for_sites(session, matched_site_ids)

    allocation_ids = [a.id for a in allocations]
    visual_summaries = build_allocation_visual_summaries(session, allocation_ids)

    local_plan_ids = sorted({a.local_plan_id for a in allocations if a.local_plan_id})
    plan_wide_fallbacks = build_plan_wide_policies_map(session, local_plan_ids)

    cards = []
    for allocation in allocations:
        plan = allocation.local_plan
        council_codes_on_plan = (
            sorted({link.council_code for link in plan.council_links}) if plan and plan.council_links
            else [allocation.council_code]
        )
        council_name = council_config[allocation.council_code].name if allocation.council_code in council_config else allocation.council_code
        matched_site = sites_by_id.get(allocation.matched_site_id) if allocation.matched_site_id else None
        linked_applications = apps_by_site.get(allocation.matched_site_id, []) if allocation.matched_site_id else []
        card = build_allocation_card(
            allocation,
            plan=plan,
            council_name=council_name,
            council_codes_on_plan=council_codes_on_plan,
            matched_site=matched_site,
            linked_applications=linked_applications,
            visual_summary=visual_summaries.get(allocation.id, {"status": "none", "primary": None, "others": []}),
            visual_fallback=plan_wide_fallbacks.get(allocation.local_plan_id) if allocation.local_plan_id else None,
            council_five_year_supply=plan.five_year_supply_years if plan else None,
        )
        cards.append(card)

    return {
        "cards": cards,
        "all_council_codes": sorted({a.council_code for a in allocations}),
        "council_names": {code: cfg.name for code, cfg in council_config.items()},
        "all_local_plans": sorted({(a.local_plan_id, (a.local_plan.plan_name if a.local_plan else a.plan_name)) for a in allocations if a.local_plan_id}, key=lambda t: t[1]),
    }


# --- Summary metrics (Part 3) ------------------------------------------------


# duplicate_of_other_plan / contextual_reference are the two APPROVED
# (human-confirmed, see LocalPlanSite.duplicate_classification's own
# docstring) classifications meaning "this row is the same physical
# allocation as another one already counted elsewhere" - excluded from
# summary COUNTS only, per Part 14 ("do not double-count them in summary
# totals if the approved relationship explicitly identifies the same
# physical Site"). uncertain_needs_review and None (not yet classified)
# are NOT excluded - an unapproved/absent classification must never
# silently deduplicate a row that might turn out to be genuinely distinct.
_EXCLUDED_FROM_SUMMARY_CLASSIFICATIONS = {"duplicate_of_other_plan", "contextual_reference"}


def _counts_toward_summary(card: dict) -> bool:
    return card["duplicate_classification"] not in _EXCLUDED_FROM_SUMMARY_CLASSIFICATIONS


def build_summary_metrics(cards: list[dict]) -> dict:
    """Real counts only - a metric this platform genuinely cannot support
    yet is simply omitted by the caller, never shown as an unsupported
    zero (Part 3). Every count is scoped to _counts_toward_summary, so an
    allocation an approved AllocationRelationship review has already
    identified as the same physical site as another counted row is never
    counted twice (Part 14) - it still appears in the gallery itself,
    just not in these aggregate totals.

    Sprint 4.5a ("Commercial Polish", Part 7) added total_homes_identified,
    strategic_housing_allocations and confirmed_allocation_maps - metrics
    that communicate development SCALE (how much housing this platform has
    identified, how much of it is confirmed-mapped) rather than database
    size (row counts alone). Every added figure is a straightforward sum/
    count over facts each card already carries - never a new estimate."""
    countable = [c for c in cards if _counts_toward_summary(c)]
    total = len(countable)
    # Total Homes Identified (Evidence Terminology Amendment, Part 2): each
    # card's own kpi_capacity_contribution (see kpi_capacity_contribution's
    # docstring for the full documented rule) - never capacity["value"],
    # which picks a range's MAXIMUM for display/sort purposes and would
    # silently overstate the total if summed directly (Part 4). A maximum-
    # only capacity contributes nothing (excluded, not zero); an
    # indicative-only capacity contributes its figure but is flagged as an
    # estimate so the caller can rename the metric accordingly.
    contributions = [c["kpi_capacity_contribution"] for c in countable if c["kpi_capacity_contribution"]["value"] is not None]
    total_homes = sum(c["value"] for c in contributions) if contributions else None
    total_homes_is_estimate = any(c["is_estimate"] for c in contributions)
    return {
        "total_allocations": total,
        "adopted_allocations": sum(1 for c in countable if c["plan_status_bucket"] == "adopted"),
        "emerging_allocations": sum(1 for c in countable if c["plan_status_bucket"] == "emerging"),
        "with_visual_evidence": sum(1 for c in countable if c["visual_status"] != "none" or c["visual_fallback"] is not None),
        # "Allocation matched to a PropertyAIgent Site" - a genuinely
        # different claim from "has a trusted linked Planning Application"
        # (Sprint 4.5b Product Owner amendment, Part 8) - intentionally
        # NOT changed to has_trusted_linked_application; card["matched"]
        # already means exactly what this KPI's name says.
        "matched_to_sites": sum(1 for c in countable if c["matched"]),
        # Canonical trusted definition (Part 5/22) - "Without Linked
        # Applications" is a customer-facing claim about trusted Planning
        # Application relationships, so it must agree with the badge/filter/
        # category above, not the raw linked_application_count this used
        # to read before the fix.
        "no_linked_application": sum(1 for c in countable if not has_trusted_linked_application(c)),
        "needs_review": sum(1 for c in countable if _needs_review(c)),
        # Only a real total when at least one allocation has a known
        # capacity - an empty list summed to 0 would misrepresent "we
        # haven't identified any homes" as "no homes exist here", so this
        # is None (never shown) rather than a false 0 when nothing is known.
        "total_homes_identified": total_homes,
        # True whenever the total includes at least one indicative
        # (estimated, not stated-minimum) figure - the caller must then
        # present the metric as "Indicative homes identified", never as a
        # firm deliverable total (Part 2).
        "total_homes_identified_is_estimate": total_homes_is_estimate,
        "strategic_housing_allocations": sum(1 for c in countable if c["major_housing"]),
        "confirmed_allocation_maps": sum(1 for c in countable if c["visual_status"] == "confirmed"),
    }


TOTAL_HOMES_KPI_LABEL = "Total Homes Identified"
TOTAL_HOMES_KPI_LABEL_ESTIMATE = "Indicative homes identified"

TOTAL_HOMES_KPI_CAPTION = (
    "Sum of each allocation's stated minimum capacity (a range uses its minimum, never its maximum) - "
    "never a firm delivery figure. Allocations with only an upper-bound capacity, or no stated capacity, "
    "are excluded rather than counted as zero. Approved duplicate/contextual allocations are excluded once."
)
TOTAL_HOMES_KPI_CAPTION_ESTIMATE = (
    "Includes one or more council-stated indicative (estimated, not a confirmed minimum) capacity figures - "
    "shown as an indicative total, not a firm delivery figure. A range uses its minimum, never its maximum; "
    "allocations with only an upper-bound or no stated capacity are excluded rather than counted as zero."
)


def total_homes_kpi_label(summary: dict) -> str:
    return TOTAL_HOMES_KPI_LABEL_ESTIMATE if summary["total_homes_identified_is_estimate"] else TOTAL_HOMES_KPI_LABEL


def total_homes_kpi_caption(summary: dict) -> str:
    return TOTAL_HOMES_KPI_CAPTION_ESTIMATE if summary["total_homes_identified_is_estimate"] else TOTAL_HOMES_KPI_CAPTION


# --- Search (Part 4) ---------------------------------------------------------


def search_allocations(cards: list[dict], query: str) -> list[dict]:
    """Case-insensitive, deterministic substring search across allocation
    name, policy reference, council, Local Plan, intended use, and matched
    Site address - no AI, no fuzzy ranking."""
    q = (query or "").strip().lower()
    if not q:
        return list(cards)

    def _matches(card: dict) -> bool:
        haystacks = (
            card["site_name"], card["policy_reference"], card["council_name"], card["council_code"],
            card["plan_name"], card["intended_use_label"], card["matched_site_address"],
        )
        return any(h and q in h.lower() for h in haystacks)

    return [c for c in cards if _matches(c)]


# --- Filters (Part 5) --------------------------------------------------------


def apply_filters(cards: list[dict], filters: dict) -> list[dict]:
    """filters: a dict of optional keys, each None/empty meaning "no
    constraint". Every key is independent (AND'd together) and safe to omit
    entirely - callers only ever set the filters a user has actually
    touched."""
    result = list(cards)

    councils = filters.get("councils")
    if councils:
        result = [c for c in result if c["council_code"] in councils]

    local_plan_ids = filters.get("local_plan_ids")
    if local_plan_ids:
        result = [c for c in result if c["local_plan_id"] in local_plan_ids]

    plan_status_buckets = filters.get("plan_status_buckets")
    if plan_status_buckets:
        result = [c for c in result if c["plan_status_bucket"] in plan_status_buckets]

    intended_uses = filters.get("intended_uses")
    if intended_uses:
        result = [c for c in result if c["intended_use"] in intended_uses]

    capacity_min = filters.get("capacity_min")
    if capacity_min is not None:
        result = [c for c in result if c["capacity"]["value"] is not None and c["capacity"]["value"] >= capacity_min]
    capacity_max = filters.get("capacity_max")
    if capacity_max is not None:
        result = [c for c in result if c["capacity"]["value"] is not None and c["capacity"]["value"] <= capacity_max]

    matched_filter = filters.get("matched")
    if matched_filter == "matched":
        result = [c for c in result if c["matched"]]
    elif matched_filter == "unmatched":
        result = [c for c in result if not c["matched"]]

    # Sprint 4.5b Product Owner amendment (Part 5/7) - the correctness fix:
    # this used to check raw linked_application_count, which disagreed with
    # the badge's own needs_confirmation exclusion (see
    # has_trusted_linked_application's own docstring for the full story).
    # Both branches now read the one canonical definition, so this filter
    # can never disagree with what the badge shows.
    application_filter = filters.get("application_linkage")
    if application_filter == "linked":
        result = [c for c in result if has_trusted_linked_application(c)]
    elif application_filter == "not_linked":
        result = [c for c in result if not has_trusted_linked_application(c)]

    visual_filter = filters.get("visual_evidence")
    if visual_filter == "confirmed":
        result = [c for c in result if c["visual_status"] == "confirmed"]
    elif visual_filter == "suggested":
        result = [c for c in result if c["visual_status"] == "needs_review" or c["visual_fallback"] is not None]
    elif visual_filter == "none":
        result = [c for c in result if c["visual_status"] == "none" and c["visual_fallback"] is None]

    review_filter = filters.get("review_states")
    if review_filter:
        result = [c for c in result if c["review_status"] in review_filter]

    if filters.get("joint_plan_only"):
        result = [c for c in result if c["is_multi_authority"]]

    if filters.get("cross_boundary_only"):
        result = [c for c in result if c["is_multi_authority"] and c["cross_boundary_councils"]]

    return result


# --- Discovery categories (Part 6) -------------------------------------------


def _needs_review(card: dict) -> bool:
    return (
        card["review_status"] == "needs_confirmation"
        or card["visual_status"] == "needs_review"
        or card["duplicate_classification"] == "uncertain_needs_review"
    )


def _not_commenced(card: dict) -> bool:
    return card["matched"] and card["lapse_status"] in _NOT_COMMENCED_LAPSE_STATUSES


def _has_map(card: dict) -> bool:
    return card["visual_status"] != "none" or card["visual_fallback"] is not None


# "No Linked Application" reads has_trusted_linked_application (Sprint
# 4.5b Product Owner amendment, Part 5/6) - so this category always
# contains exactly the allocations NOT showing the badge, including a
# needs_confirmation match with a real Application row. That is Part 6's
# own definition of the negative state: "No sufficiently trusted planning
# application relationship is currently recorded" - never "no Application
# exists in reality" (see linked_application_help's wording).
CATEGORY_DEFINITIONS: tuple[tuple[str, str, object], ...] = (
    ("all", "All Allocations", lambda c: True),
    ("adopted", "Adopted", lambda c: c["plan_status_bucket"] == "adopted"),
    ("emerging", "Emerging", lambda c: c["plan_status_bucket"] == "emerging"),
    ("with_maps", "With Maps", _has_map),
    ("no_linked_application", "No Linked Application", lambda c: not has_trusted_linked_application(c)),
    ("not_commenced", "Undeveloped / Not Commenced", _not_commenced),
    ("major_housing", "Major Housing Allocations", lambda c: c["major_housing"]),
    ("needs_review", "Needs Review", _needs_review),
)


def compute_categories(cards: list[dict]) -> list[dict]:
    """One entry per CATEGORY_DEFINITIONS whose predicate matches at least
    one card (Part 6: "hide unsupported categories rather than showing
    misleading empty tabs") - "All Allocations" is always included whenever
    there is at least one card at all."""
    categories = []
    for key, label, predicate in CATEGORY_DEFINITIONS:
        matched = [c for c in cards if predicate(c)]
        if matched:
            categories.append({"key": key, "label": label, "cards": matched, "count": len(matched)})
    return categories


# --- Sorting (Part 16) -------------------------------------------------------


SORT_OPTIONS: tuple[tuple[str, str], ...] = (
    ("default", "Best match (recently updated, adopted/emerging first)"),
    ("recent_updated", "Recently updated"),
    ("capacity_desc", "Capacity: high to low"),
    ("council", "Council"),
    ("policy_reference", "Policy reference"),
    ("plan_stage", "Plan stage"),
    ("visual_evidence", "Visual evidence available"),
    ("unmatched_first", "Unmatched first"),
)
SORT_LABELS = dict(SORT_OPTIONS)


def _updated_ts(card: dict) -> float:
    value = card.get("updated_at")
    if value is None:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.timestamp()


def sort_cards(cards: list[dict], sort_key: str = "default") -> list[dict]:
    """Every option is fully deterministic - id is always the final
    tie-breaker so the same input always produces the same order, never an
    invented "opportunity score" (Part 16)."""
    if sort_key == "recent_updated":
        return sorted(cards, key=lambda c: (-_updated_ts(c), c["id"]))
    if sort_key == "capacity_desc":
        return sorted(cards, key=lambda c: (c["capacity"]["value"] is None, -(c["capacity"]["value"] or 0), c["id"]))
    if sort_key == "council":
        return sorted(cards, key=lambda c: (c["council_name"].lower(), c["id"]))
    if sort_key == "policy_reference":
        return sorted(cards, key=lambda c: (c["policy_reference"] is None, (c["policy_reference"] or "").lower(), c["id"]))
    if sort_key == "plan_stage":
        return sorted(cards, key=lambda c: (_PLAN_STAGE_RANK.get(c["plan_status"], len(_PLAN_STAGE_ORDER)), c["id"]))
    if sort_key == "visual_evidence":
        visual_rank = {"confirmed": 0, "needs_review": 1, "none": 2}
        return sorted(cards, key=lambda c: (visual_rank.get(c["visual_status"], 2) if c["visual_status"] != "none" or c["visual_fallback"] is None else 1, c["id"]))
    if sort_key == "unmatched_first":
        return sorted(cards, key=lambda c: (c["matched"], c["id"]))
    # "default" - documented rule (Part 16): recent meaningful update, then
    # adopted/emerging relevance, then stable id as the final tie-breaker.
    return sorted(
        cards,
        key=lambda c: (-_updated_ts(c), _BUCKET_RELEVANCE_RANK.get(c["plan_status_bucket"], 2), c["id"]),
    )
