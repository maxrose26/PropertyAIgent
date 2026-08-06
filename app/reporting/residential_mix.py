"""Residential Mix Intelligence (Sprint 4.4 Amendment, Phase 1).

A reusable module WITHIN Planning Intelligence (see docs/PRODUCT_VISION.md's
six-layer capability stack and docs/PLATFORM_ARCHITECTURE.md §1) - not a
seventh platform capability. It transforms the already-reconciled
SchemeIntelligence figures for a Site's current preferred scheme version
into structured, evidence-backed residential-composition intelligence.

Pure module, no Streamlit imports - mirrors app.reporting.site_profile's own
discipline (CLAUDE.md's "keep business logic out of the UI"). Adds NO new
extraction pipeline and NO new source of truth: every figure here is read
from app.extraction.reconcile's already-reconciled SchemeIntelligence
columns, the platform's one existing home for housing-mix/affordable-
housing data. Where a figure genuinely isn't extracted by this platform
today - a structured bedroom mix, and a structured house/flat/bungalow
count - this module says so honestly rather than inventing one; see
build_bedroom_mix/build_housing_type's own docstrings.

Phase 1 scope only: structured mix, affordable provision, tenure, evidence,
commentary. Explicitly NOT in scope: market comparison, Local Plan
affordable-policy compliance, viability, mix optimisation, or any planning-
permission-likelihood claim - those belong to future phases/future
capabilities (Market Intelligence, Development Economics), and nothing
below ever implies them.

Designed for reuse beyond Site Profile (Reports, Planning Statements,
Market Intelligence comparisons, Development Economics, AI Decision
Support): build_residential_mix's only inputs are a Site, its Applications,
and the already-selected representative Application (computed once by the
caller via app.ui.common.pick_representative_application - the platform's
one existing "current scheme version" selector, deliberately not
reimplemented here). No Session/DB access happens in this module at all;
every application passed in must already have its .scheme_intelligence
relationship available, exactly as every existing caller of
aggregate_scheme_fields/pick_representative_application already relies on.
"""
from __future__ import annotations

from app.db.models import Application, SchemeIntelligence, Site

# --- Evidence/review states (Part 16) ---------------------------------------
# The vocabulary every section below reports against - deliberately reused
# everywhere in this module rather than each section inventing its own
# words for the same ideas.
CONFIRMED = "confirmed"
AUTO_APPLIED = "auto_applied"
CALCULATED = "calculated"
NEEDS_REVIEW = "needs_review"
CONFLICTING = "conflicting"
NOT_IDENTIFIED = "not_identified"
STALE = "stale"
SUPERSEDED = "superseded"


# --- Affordable-percentage rules (Part 5) ------------------------------------


def _clamp_percentage(value: float | None) -> float | None:
    """A percentage outside 0-100 is a data-quality anomaly (e.g.
    inconsistent affordable/total evidence), not a real figure to display -
    treated as unknown here so the caller falls back to a review state
    rather than showing something like "142% affordable"."""
    if value is None:
        return None
    if value < 0 or value > 100:
        return None
    return value


def format_affordable_percentage(value: float) -> str:
    """Display rounding rule (Part 5): whole percentage by default. One
    decimal place only where a whole-number rounding would misrepresent the
    figure - specifically when it would round to a bare 0% or 100% while
    the true value is not actually 0 or 100, since "0% affordable" reads as
    a confident, evidenced zero (Part 4 Case F), which a genuinely small
    nonzero figure (e.g. 0.4%) is not. Every other value rounds to a whole
    number, which is sufficiently clear for a headline figure."""
    whole = round(value)
    if whole in (0, 100) and value not in (0, 100):
        return f"{value:.1f}%"
    return f"{whole:g}%"


def compute_affordable_headline(scheme: SchemeIntelligence | None) -> dict:
    """The Affordable Homes headline state (Part 4 A-F), computed entirely
    from ONE scheme_intelligence row - never mixes affordable units from
    one application with the total from another (Part 5's core
    requirement), since both are always read from this single `scheme`
    argument, which the caller must have already selected as the one
    current/preferred version (see build_current_version below).

    Returns a dict with:
        state: one of "verified" | "calculated" | "percentage_only" |
               "review" | "not_identified" | "zero"
        evidence_status: the Part 16 vocabulary word for this state
        affordable_units: int | None
        percentage_raw: float | None (full precision, for reuse by future
               consumers - Part 5's "retain audit precision internally")
        percentage_display: str | None (rounded, for headline display)
        percentage_is_calculated: bool - True only when this module derived
               the percentage itself (Case B); False when the figure came
               directly from evidence (Case A/C)
        headline_units: str - the Part 4 "42 affordable homes" / "Not
               identified" / "Requires manual review" / "0 affordable
               homes" line
        headline_percentage: str | None - the Part 4 "30% affordable" /
               "30% calculated" / "Unit count not identified" second line
    """
    empty = {
        "state": "not_identified", "evidence_status": NOT_IDENTIFIED,
        "affordable_units": None, "percentage_raw": None, "percentage_display": None,
        "percentage_is_calculated": False, "headline_units": "Not identified",
        "headline_percentage": None,
    }
    if scheme is None:
        return empty

    affordable = scheme.affordable_units_final
    total = scheme.total_units_final
    stated_pct = _clamp_percentage(scheme.affordable_percentage_final)

    # Case D: reuse reconcile.py's OWN ambiguity signals directly, never
    # re-derive a parallel consistency check - affordable_status_note is
    # set exactly when the evidence is self-contradictory (a stated
    # percentage with no confirmable unit count at a stage where none was
    # expected); unit_reconciliation_status != "OK" is set exactly when
    # affordable + private doesn't add up to total.
    if scheme.affordable_status_note or (scheme.unit_reconciliation_status and scheme.unit_reconciliation_status != "OK"):
        return {
            "state": "review", "evidence_status": NEEDS_REVIEW,
            "affordable_units": None, "percentage_raw": None, "percentage_display": None,
            "percentage_is_calculated": False, "headline_units": "Requires manual review",
            "headline_percentage": None,
        }

    # Case F: an explicit, trusted zero - reconcile.py only ever sets
    # affordable_units_final = 0 when the classifier confidently resolved
    # "no on-site affordable required" (or a genuinely 0% calculated/stated
    # figure) - never as a default for "missing". `is not None` throughout,
    # never truthiness, so a real 0 is never confused with "nothing found".
    if affordable is not None and affordable == 0:
        return {
            "state": "zero", "evidence_status": CONFIRMED,
            "affordable_units": 0, "percentage_raw": stated_pct if stated_pct is not None else 0.0,
            "percentage_display": format_affordable_percentage(stated_pct if stated_pct is not None else 0.0),
            "percentage_is_calculated": stated_pct is None, "headline_units": "0 affordable homes",
            "headline_percentage": format_affordable_percentage(stated_pct if stated_pct is not None else 0.0),
        }

    # Case A: both affordable units and a stated percentage are present.
    if affordable is not None and stated_pct is not None:
        return {
            "state": "verified", "evidence_status": CONFIRMED,
            "affordable_units": affordable, "percentage_raw": stated_pct,
            "percentage_display": format_affordable_percentage(stated_pct),
            "percentage_is_calculated": False, "headline_units": f"{affordable:,} affordable homes",
            "headline_percentage": f"{format_affordable_percentage(stated_pct)} affordable",
        }

    # Case B: affordable units and a trusted total are both known, but no
    # stated percentage exists in evidence - calculate one here (this
    # module's own presentation-time maths, not a new extraction pipeline;
    # reconcile.py never populates affordable_percentage_final this way).
    if affordable is not None and total:
        calculated_pct = _clamp_percentage(round((affordable / total) * 100, 2))
        if calculated_pct is None:
            return {
                "state": "review", "evidence_status": NEEDS_REVIEW,
                "affordable_units": affordable, "percentage_raw": None, "percentage_display": None,
                "percentage_is_calculated": False, "headline_units": f"{affordable:,} affordable homes",
                "headline_percentage": None,
            }
        return {
            "state": "calculated", "evidence_status": CALCULATED,
            "affordable_units": affordable, "percentage_raw": calculated_pct,
            "percentage_display": format_affordable_percentage(calculated_pct),
            "percentage_is_calculated": True, "headline_units": f"{affordable:,} affordable homes",
            "headline_percentage": f"{format_affordable_percentage(calculated_pct)} calculated",
        }

    # Case C: a stated percentage exists but no reliable affordable-unit
    # count does (no trusted total to derive one from, or evidence simply
    # never gave a raw count) - never infer a unit count here.
    if stated_pct is not None:
        return {
            "state": "percentage_only", "evidence_status": CONFIRMED,
            "affordable_units": None, "percentage_raw": stated_pct,
            "percentage_display": format_affordable_percentage(stated_pct),
            "percentage_is_calculated": False, "headline_units": "Unit count not identified",
            "headline_percentage": f"{format_affordable_percentage(stated_pct)} affordable",
        }

    # Case E: genuinely nothing found - never labelled "needs review",
    # since there is no evidence to review, only evidence that's absent.
    return empty


def format_affordable_tile(headline: dict) -> tuple[str, str | None]:
    """(value, caption) for the Affordable Homes headline tile (Part 4) -
    the one shared implementation of "which line is primary" for every
    state, used identically by the Site Profile headline metrics
    (app.reporting.site_profile.build_headline_metrics) and the dedicated
    Residential Mix Intelligence tab (app.ui.shell.affordable_headline_tile),
    so the two can never drift out of sync with each other. Case C
    ("percentage_only") is the one state where the percentage is primary
    and the unit-count gap is the caption - every other state is unit-count
    primary, percentage (or nothing) as caption."""
    if headline["state"] == "percentage_only":
        return headline["headline_percentage"], headline["headline_units"]
    if headline["state"] in ("verified", "calculated"):
        return headline["headline_units"], headline["headline_percentage"]
    return headline["headline_units"], None


# --- Affordable tenure (Part 11) ---------------------------------------------


# The exact keyword vocabulary app.extraction.housing_mix.TENURE_KEYWORDS
# searches for - kept as a display-label lookup here (not re-imported,
# since importing app.extraction.housing_mix would pull in its regex
# extraction machinery for what's really just a label lookup) so a raw
# match like "shared ownership" renders with consistent capitalisation.
_TENURE_LABELS = {
    "affordable rent": "Affordable rent",
    "social rent": "Social rent",
    "shared ownership": "Shared ownership",
    "shared equity": "Shared equity",
    "discount market rent": "Discount market rent",
    "discount market sale": "Discount market sale",
    "first homes": "First homes",
    "rent to buy": "Rent to buy",
}


def parse_tenure_categories(raw: str | None) -> list[str]:
    """affordable_tenure_split_final is a comma-joined list of whichever
    TENURE_KEYWORDS were found mentioned in the source documents (see
    app.extraction.housing_mix._tenure_split) - never a quantified
    breakdown (no per-tenure unit counts exist), so this only ever returns
    which categories are evidenced, not how many units each represents."""
    if not raw:
        return []
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return [_TENURE_LABELS.get(p, p.title()) for p in parts]


def build_affordable_tenure(scheme: SchemeIntelligence | None, affordable_headline: dict) -> dict:
    """Part 11 - only ever shows evidenced categories; never invents a
    distribution across them (there is no per-category unit count to
    show). If affordable homes are known but tenure isn't, says so
    explicitly rather than leaving a blank that could read as "market
    housing"."""
    categories = parse_tenure_categories(scheme.affordable_tenure_split_final if scheme else None)
    affordable_known = affordable_headline["state"] in ("verified", "calculated", "percentage_only", "zero")
    return {
        "categories": categories,
        "has_categories": bool(categories),
        "affordable_known_tenure_unknown": affordable_known and not categories,
    }


# --- Bedroom mix (Part 8) - honest Phase-1 gap -------------------------------


def build_bedroom_mix(scheme: SchemeIntelligence | None) -> dict:
    """Part 8. This platform does not extract a structured bedroom mix
    (studio/1-bed/2-bed/... counts) today - confirmed by inspection of
    app.extraction.housing_mix, app.extraction.reconcile and the
    SchemeIntelligence model, none of which capture per-bedroom-size unit
    counts. Per the brief's own "do not create a new extraction pipeline"
    and "do not invent missing categories with zero values", this always
    returns an honest "not available" state in Phase 1 rather than a table
    of zeroes - a future extraction phase would populate this the same
    shape without changing any caller."""
    return {"available": False, "categories": [], "reconciled_total": None, "unreconciled": False, "version_reference": None}


# --- Housing type (Part 9) - honest Phase-1 gap ------------------------------


def build_housing_type(scheme: SchemeIntelligence | None) -> dict:
    """Part 9. Like bedroom mix, this platform has no structured house/
    flat/bungalow COUNT - but the LLM site-intelligence pass does capture a
    free-text housing_typology/specialist_housing_type description (e.g.
    "terraced houses and apartments"), which is real evidence worth
    surfacing even though it isn't a quantified split. Shown as descriptive
    evidence, never converted into invented category counts, and never
    inferred from bedroom count (the brief explicitly forbids this, and no
    bedroom data exists to infer from regardless)."""
    if scheme is None:
        return {"available": False, "typology_description": None, "specialist_type": None, "development_type": None}
    description = scheme.housing_typology
    return {
        "available": bool(description or scheme.specialist_housing_type or scheme.development_type),
        "typology_description": description,
        "specialist_type": scheme.specialist_housing_type,
        "development_type": scheme.development_type,
    }


# --- Density (Part 7) --------------------------------------------------------


def build_density(scheme: SchemeIntelligence | None) -> dict:
    """Part 7 - only ever shows a density figure the AI site-intelligence
    pass already extracted and stored (density_dph); never computed here
    from a guessed Site.area, which the brief explicitly forbids."""
    if scheme is None or scheme.density_dph is None:
        return {"available": False, "density_dph": None, "site_area_ha": None}
    return {"available": True, "density_dph": scheme.density_dph, "site_area_ha": scheme.site_area_ha}


# --- Current/preferred scheme version (Part 12) ------------------------------


def build_current_version(site: Site, apps: list[Application], rep_app: Application | None) -> dict:
    """Identifies the one Application whose scheme_intelligence this whole
    module reads from, and why - reusing app.ui.common.
    pick_representative_application's own already-established selection
    (passed in as rep_app, computed once by the caller), not a parallel
    selector. This is the single mechanism that satisfies Part 5's "never
    mix affordable units from one scheme version with total homes from
    another": every figure in this module's totals/tenure/bedroom/housing-
    type sections comes from exactly this one Application's
    scheme_intelligence row, never blended across applications.

    Also surfaces every OTHER application on the Site that has its own
    scheme_intelligence, as alternative/superseded evidence (never merged
    into the current figures), and flags a "version conflict" when an
    alternative's own total/affordable figures materially differ from the
    current version's - a signal for manual review, never silently
    resolved."""
    if rep_app is None:
        return {
            "application_id": None, "reference": None, "why_preferred": None,
            "has_scheme_intelligence": False, "alternatives": [], "version_conflict": False,
        }

    why_preferred = (
        "This application has complete, reconciled residential intelligence and is the most recently "
        "received qualifying application linked to this site."
        if rep_app.scheme_intelligence and rep_app.scheme_intelligence.core_intelligence_complete
        else "This is the most recently received qualifying application linked to this site; its "
        "residential intelligence is not yet fully reconciled."
    )

    alternatives = []
    version_conflict = False
    current_scheme = rep_app.scheme_intelligence
    for app in apps:
        if app.id == rep_app.id or not app.scheme_intelligence:
            continue
        si = app.scheme_intelligence
        alternatives.append({
            "application_id": app.id, "reference": app.reference,
            "total_units_final": si.total_units_final, "affordable_units_final": si.affordable_units_final,
            "affordable_percentage_final": si.affordable_percentage_final,
            "received": app.application_received,
        })
        if current_scheme and si.total_units_final is not None and current_scheme.total_units_final is not None:
            if si.total_units_final != current_scheme.total_units_final:
                version_conflict = True

    return {
        "application_id": rep_app.id, "reference": rep_app.reference, "why_preferred": why_preferred,
        "has_scheme_intelligence": current_scheme is not None,
        "alternatives": alternatives, "version_conflict": version_conflict,
    }


# --- Residential Mix Overview totals (Part 7) --------------------------------


def build_overview_totals(scheme: SchemeIntelligence | None, affordable_headline: dict) -> dict:
    """Part 7 headline facts - only ever shows a figure that's actually
    supported; never a zero standing in for "unknown" (e.g. a missing
    total is None here, not 0)."""
    total = scheme.total_units_final if scheme else None
    return {
        "total_homes": total,
        "affordable_homes": affordable_headline["affordable_units"],
        "affordable_percentage_display": affordable_headline["headline_percentage"],
        # Bedroom-mix/house-flat/family-percentage/apartment-percentage are
        # deliberately absent here - Phase 1 has no structured evidence for
        # any of them (see build_bedroom_mix/build_housing_type above), and
        # Part 7 explicitly forbids showing an unsupported value as zero.
    }


# --- Residential Mix Commentary (Part 13/15) ---------------------------------


def build_structured_summary(
    affordable_headline: dict, tenure: dict, current_version: dict, unit_reconciliation_status: str | None,
) -> str | None:
    """Part 15's deterministic, clearly-NOT-AI "Structured summary" -
    direct observations only, built from Python string formatting of
    already-computed facts, no LLM call. Returns None when there's
    genuinely nothing supported to say (e.g. no affordable evidence and no
    reconciliation issue - an empty structured summary would just be noise
    on top of the headline tile that already says "Not identified")."""
    sentences: list[str] = []

    state = affordable_headline["state"]
    if state in ("verified", "calculated"):
        units = affordable_headline["affordable_units"]
        pct_bit = f", representing {affordable_headline['percentage_display']} of the reconciled scheme total" if affordable_headline["percentage_display"] else ""
        sentences.append(f"Affordable provision is recorded at {units:,} homes{pct_bit}.")
    elif state == "percentage_only":
        sentences.append(f"Affordable provision is recorded at {affordable_headline['percentage_display']}, with the unit count not yet identified.")
    elif state == "zero":
        sentences.append("No on-site affordable housing is recorded for this scheme.")
    elif state == "review":
        sentences.append("Affordable housing evidence for this scheme requires manual review.")

    if tenure["has_categories"]:
        sentences.append(f"Affordable tenure recorded: {', '.join(tenure['categories'])}.")
    elif tenure["affordable_known_tenure_unknown"]:
        sentences.append("Affordable tenure has not been identified.")

    if current_version.get("version_conflict"):
        sentences.append("Alternative application versions on this site record a different total unit count - see Evidence and Reconciliation.")
    if unit_reconciliation_status and unit_reconciliation_status != "OK":
        sentences.append("The recorded unit figures do not yet fully reconcile for this scheme.")

    return " ".join(sentences) if sentences else None


def build_ai_commentary_view(site: Site) -> dict:
    """Part 14 - first checks for an existing, suitable stored commentary;
    none exists (confirmed by inspection: Site.status_summary is a general
    site-status narrative covering phases/lapse/build status/developer,
    generated only by the weekly pipeline with no residential-mix-specific
    scope or evidence fingerprinting, and no per-row
    model/prompt_version columns the way LocalPlan's AI summary has - see
    this module's own top docstring and the sprint's final report). Rather
    than repurpose a differently-scoped summary or build a new AI pipeline
    in this amendment, this honestly reports "not yet generated" - the
    Structured summary above (Part 15) is the Phase 1 substitute."""
    return {"has_commentary": False, "text": None, "generated_at": None, "is_stale": False}


# --- Evidence gaps (Part 6, section 8) ---------------------------------------


def build_evidence_gaps(current_version: dict, affordable_headline: dict, tenure: dict, bedroom_mix: dict, housing_type: dict) -> list[str]:
    gaps: list[str] = []
    if not current_version.get("application_id"):
        gaps.append("No qualifying application is linked to this site yet.")
    elif not current_version.get("has_scheme_intelligence"):
        gaps.append("The current preferred application has no extracted residential intelligence yet.")
    if current_version.get("version_conflict"):
        gaps.append("Alternative application versions record a different total unit count - flagged for review.")
    if affordable_headline["state"] == "not_identified":
        gaps.append("No affordable-housing evidence has been located yet.")
    elif affordable_headline["state"] == "review":
        gaps.append("Affordable-housing evidence is ambiguous or unreconciled and needs manual review.")
    elif affordable_headline["state"] == "percentage_only":
        gaps.append("Affordable-housing unit count has not been identified, only a stated percentage.")
    if tenure["affordable_known_tenure_unknown"]:
        gaps.append("Affordable tenure has not been identified.")
    if not bedroom_mix["available"]:
        gaps.append("No structured bedroom mix has been extracted for this platform yet.")
    if not housing_type["available"]:
        gaps.append("No housing-type evidence has been extracted for this scheme yet.")
    return gaps


# --- Top-level assembly -------------------------------------------------------


def build_residential_mix(site: Site, apps: list[Application], *, rep_app: Application | None) -> dict:
    """The Residential Mix Intelligence view model (Part 1/18) - the one
    entry point every consumer (Site Profile today; Reports, Planning
    Statements, Market Intelligence comparisons, Development Economics, AI
    Decision Support in future - none of those are built in this
    amendment) should call. Adds zero new database queries: every
    Application passed in must already have its .scheme_intelligence
    relationship reachable, exactly as app.ui.common.aggregate_scheme_fields
    and pick_representative_application already rely on for the same
    `apps` list - this module iterates that same already-loaded data, not a
    fresh query per application."""
    current_version = build_current_version(site, apps, rep_app)
    scheme = rep_app.scheme_intelligence if rep_app else None

    affordable_headline = compute_affordable_headline(scheme)
    tenure = build_affordable_tenure(scheme, affordable_headline)
    bedroom_mix = build_bedroom_mix(scheme)
    housing_type = build_housing_type(scheme)
    density = build_density(scheme)
    overview_totals = build_overview_totals(scheme, affordable_headline)
    ai_commentary = build_ai_commentary_view(site)
    structured_summary = build_structured_summary(
        affordable_headline, tenure, current_version,
        scheme.unit_reconciliation_status if scheme else None,
    )
    evidence_gaps = build_evidence_gaps(current_version, affordable_headline, tenure, bedroom_mix, housing_type)

    return {
        "current_version": current_version,
        "affordable_headline": affordable_headline,
        "tenure": tenure,
        "bedroom_mix": bedroom_mix,
        "housing_type": housing_type,
        "density": density,
        "overview_totals": overview_totals,
        "ai_commentary": ai_commentary,
        "structured_summary": structured_summary,
        "evidence_gaps": evidence_gaps,
        "scheme": scheme,
    }
