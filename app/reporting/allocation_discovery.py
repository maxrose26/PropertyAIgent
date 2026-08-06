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
    stated AND they actually differ."""
    minimum = allocation.minimum_dwellings
    indicative = allocation.indicative_capacity
    maximum = allocation.maximum_capacity

    if minimum is None and indicative is None and maximum is None:
        return {"kind": "unknown", "display": "Capacity not stated", "value": None}
    if minimum is not None and maximum is not None and minimum != maximum:
        return {"kind": "range", "display": f"{minimum:,}–{maximum:,} homes", "value": maximum}
    if minimum is not None:
        return {"kind": "minimum", "display": f"{minimum:,} homes (minimum)", "value": minimum}
    if maximum is not None:
        return {"kind": "maximum", "display": f"Up to {maximum:,} homes", "value": maximum}
    return {"kind": "indicative", "display": f"~{indicative:,} homes (indicative)", "value": indicative}


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
    reasons: list[str] = []
    capacity_value = card["capacity"]["value"]

    if card["plan_status_bucket"] == "adopted" and card["major_housing"]:
        reasons.append(
            f"Adopted {card['intended_use_label'].lower()} allocation with capacity for approximately "
            f"{capacity_value:,} homes."
        )
    elif card["plan_status_bucket"] == "adopted":
        reasons.append(f"Adopted allocation within {card['plan_name']}.")
    elif card["plan_status_bucket"] == "emerging" and card["linked_application_count"] == 0:
        reasons.append("Emerging allocation with no linked planning application currently held by the platform.")
    elif card["plan_status_bucket"] == "emerging":
        reasons.append(f"Emerging allocation within {card['plan_name']}.")

    if card["linked_application_count"] == 0 and card["plan_status_bucket"] != "emerging":
        reasons.append("No linked planning application currently held by the platform for this allocation.")

    if card["matched"] and card["lapse_status"] in _NOT_COMMENCED_LAPSE_STATUSES:
        reasons.append("Linked permission has not yet commenced, based on available filing evidence.")

    if card["council_five_year_supply"] is not None and card["council_five_year_supply"] < FIVE_YEAR_SUPPLY_WARNING_THRESHOLD:
        reasons.append(
            f"{card['council_name']} has a verified housing land supply below five years "
            f"({card['council_five_year_supply']:.2f} years)."
        )

    if card["visual_status"] == "confirmed":
        reasons.append("Confirmed allocation map is available, but development progress has not yet been established.")
    elif card["visual_status"] == "needs_review" or card["visual_fallback"] is not None:
        reasons.append("Evidence remains unreviewed - a suggested visual is awaiting confirmation.")

    if card["is_multi_authority"] and card["major_housing"]:
        reasons.append("Cross-boundary strategic allocation shared across multiple authorities.")

    if not reasons:
        reasons.append("No standout signals identified from currently held evidence for this allocation.")
    return reasons


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
    intended_use_label = INTENDED_USE_LABELS.get(allocation.intended_use, allocation.intended_use or "Not stated")
    major_housing = is_major_housing_allocation(allocation.intended_use, capacity["value"])

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
        "capacity": capacity,
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
    return card


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
    just not in these aggregate totals."""
    countable = [c for c in cards if _counts_toward_summary(c)]
    total = len(countable)
    return {
        "total_allocations": total,
        "adopted_allocations": sum(1 for c in countable if c["plan_status_bucket"] == "adopted"),
        "emerging_allocations": sum(1 for c in countable if c["plan_status_bucket"] == "emerging"),
        "with_visual_evidence": sum(1 for c in countable if c["visual_status"] != "none" or c["visual_fallback"] is not None),
        "matched_to_sites": sum(1 for c in countable if c["matched"]),
        "no_linked_application": sum(1 for c in countable if c["linked_application_count"] == 0),
        "needs_review": sum(1 for c in countable if _needs_review(c)),
    }


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

    application_filter = filters.get("application_linkage")
    if application_filter == "linked":
        result = [c for c in result if c["linked_application_count"] > 0]
    elif application_filter == "not_linked":
        result = [c for c in result if c["linked_application_count"] == 0]

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


CATEGORY_DEFINITIONS: tuple[tuple[str, str, object], ...] = (
    ("all", "All Allocations", lambda c: True),
    ("adopted", "Adopted", lambda c: c["plan_status_bucket"] == "adopted"),
    ("emerging", "Emerging", lambda c: c["plan_status_bucket"] == "emerging"),
    ("with_maps", "With Maps", _has_map),
    ("no_linked_application", "No Linked Application", lambda c: c["linked_application_count"] == 0),
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
