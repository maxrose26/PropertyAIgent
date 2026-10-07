"""Stage 2.5B final slice: HONEST representation of a strategic allocation's stored capacity figures through the EXISTING residential-count semantics (CountAssessment).

A strategic allocation stores up to three plan-stated figures (LocalPlanSite.minimum_dwellings, indicative_capacity, maximum_capacity). Matching historically reduced them to one scalar
(maximum_capacity or minimum_dwellings) and ignored indicative_capacity. This module defines the deterministic, PURE conversion into CountAssessment semantics and the wording that
states, always, that the figure is PLAN-STATED and UNVERIFIED (it is not a qualified planning-delivery count). It performs no arithmetic beyond representing stored figures, never invents
a unit, and fails closed (UNKNOWN) for malformed or conflicting values.

Source semantics (app.reporting.allocation_discovery.format_capacity, kpi_capacity_contribution and the LocalPlanSite model comment): a stated minimum is a FLOOR ("at least"), an indicative
figure is the council's own estimate, a maximum is a ceiling, a genuine range needs a minimum and a maximum that differ.

  minimum == maximum (both stated)  -> EXACT  (the plan states one figure as both its floor and its ceiling); still plan-stated and unverified.
  minimum < maximum                 -> RANGE  lower=minimum, upper=maximum (an indicative figure inside it is recorded in the note, never averaged).
  minimum only                      -> RANGE  lower=minimum, upper=None (a floor: the ceiling is unknown, so it can never be evidence of fitting a ceiling).
  maximum only                      -> RANGE  lower=None, upper=maximum.
  indicative only                   -> APPROXIMATE value=indicative (unbounded estimate).
  nothing stated                    -> UNKNOWN.
  malformed / conflicting           -> UNKNOWN (non-positive or non-integer figures; minimum > maximum; an indicative figure outside the stated floor/ceiling or different from an equal min/max).

This module changes NO matching behaviour (see specification 025, final slice: matching integration needs a BUYER_MATCHING_POLICY_VERSION decision).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.reporting.residential_count import CountAssessment

SCALE_BASIS_PLAN_STATED_UNVERIFIED = "PLAN_STATED_UNVERIFIED"
QUALIFIER = "unverified"
SCOPE_TYPE = "allocation"
SCOPE_LABEL = "Plan-stated capacity"
BASIS = "plan_stated_unverified"



@dataclass(frozen=True)
class PlanStatedCapacity(CountAssessment):
    """A CountAssessment whose open-ended RANGE (a plan-stated floor or ceiling) has a safe label. (residential_count.py is whole-file pinned by the frozen v6 parity oracle, so the
    label for one-sided bounds lives here, not there.)"""

    def label(self):
        noun = "homes" if self.metric == "total_residential" else self.metric.replace("_", " ")
        if self.precision == "RANGE" and (self.lower is None) != (self.upper is None):
            return f"at least {self.lower:,} {noun}" if self.lower is not None else f"up to {self.upper:,} {noun}"
        return super().label()


KIND_UNKNOWN, KIND_MALFORMED, KIND_EXACT, KIND_RANGE, KIND_MINIMUM, KIND_MAXIMUM, KIND_INDICATIVE = (
    "unknown", "malformed", "exact", "range", "minimum", "maximum", "indicative")


def _valid(value) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool) and value > 0)


def classify_capacity_kind(minimum, indicative, maximum) -> str:
    """The deterministic kind of a stored (minimum, indicative, maximum) triple."""
    figures = (minimum, indicative, maximum)
    if all(f is None for f in figures):
        return KIND_UNKNOWN
    if not all(_valid(f) for f in figures):
        return KIND_MALFORMED
    if minimum is not None and maximum is not None:
        if minimum > maximum:
            return KIND_MALFORMED
        if indicative is not None and not (minimum <= indicative <= maximum):
            return KIND_MALFORMED
        return KIND_EXACT if minimum == maximum else KIND_RANGE
    if minimum is not None:
        return KIND_MALFORMED if indicative is not None and indicative < minimum else KIND_MINIMUM
    if maximum is not None:
        return KIND_MALFORMED if indicative is not None and indicative > maximum else KIND_MAXIMUM
    return KIND_INDICATIVE


def strategic_capacity_assessment(allocation) -> CountAssessment:
    """allocation: any object with minimum_dwellings / indicative_capacity / maximum_capacity (a LocalPlanSite). Pure; no database access."""
    minimum, indicative, maximum = allocation.minimum_dwellings, allocation.indicative_capacity, allocation.maximum_capacity
    kind = classify_capacity_kind(minimum, indicative, maximum)
    base = dict(scope_type=SCOPE_TYPE, scope_label=SCOPE_LABEL, basis=BASIS, confidence="plan_stated")
    if kind in (KIND_UNKNOWN, KIND_MALFORMED):
        return PlanStatedCapacity(**base, precision="UNKNOWN", resolution="capacity_not_identified" if kind == KIND_UNKNOWN else "conflicting_or_malformed_plan_figures")
    if kind == KIND_EXACT:
        return PlanStatedCapacity(**base, precision="EXACT", value=minimum, lower=minimum, upper=maximum, resolution="plan_stated_single_figure")
    if kind == KIND_RANGE:
        return PlanStatedCapacity(**base, precision="RANGE", lower=minimum, upper=maximum, resolution="plan_stated_range")
    if kind == KIND_MINIMUM:
        return PlanStatedCapacity(**base, precision="RANGE", lower=minimum, upper=None, resolution="plan_stated_minimum_only")
    if kind == KIND_MAXIMUM:
        return PlanStatedCapacity(**base, precision="RANGE", lower=None, upper=maximum, resolution="plan_stated_maximum_only")
    return PlanStatedCapacity(**base, precision="APPROXIMATE", value=indicative, resolution="plan_stated_indicative_only")


def strategic_scale_view(allocation) -> dict:
    """The presentation contract for a strategic allocation's scale: the figure(s) AND their basis, in wording that never presents a plan-stated figure as a verified count."""
    minimum, indicative, maximum = allocation.minimum_dwellings, allocation.indicative_capacity, allocation.maximum_capacity
    kind = classify_capacity_kind(minimum, indicative, maximum)
    assessment = strategic_capacity_assessment(allocation)
    suffix = f" — {QUALIFIER}"
    if kind == KIND_EXACT:
        display = f"Plan-stated capacity: {minimum:,} homes{suffix}"
    elif kind == KIND_RANGE:
        inside = f" (plan-indicative ~{indicative:,})" if indicative is not None else ""
        display = f"Plan-stated range: {minimum:,}–{maximum:,} homes{inside}{suffix}"
    elif kind == KIND_MINIMUM:
        display = f"Plan-stated minimum: {minimum:,} homes{suffix}"
    elif kind == KIND_MAXIMUM:
        display = f"Plan-stated maximum: {maximum:,} homes{suffix}"
    elif kind == KIND_INDICATIVE:
        display = f"Plan-stated indicative capacity: approximately {indicative:,} homes{suffix}"
    elif kind == KIND_MALFORMED:
        display = "Plan-stated capacity figures conflict — not used"
    else:
        display = "Plan capacity not identified"
    figure = {KIND_EXACT: lambda: f"{minimum:,} homes", KIND_RANGE: lambda: f"{minimum:,}–{maximum:,} homes", KIND_MINIMUM: lambda: f"at least {minimum:,} homes",
              KIND_MAXIMUM: lambda: f"up to {maximum:,} homes", KIND_INDICATIVE: lambda: f"approximately {indicative:,} homes"}.get(kind, lambda: "Not identified")()   # lazy: only a VALID triple is formatted
    return {"kind": kind, "display": display, "figure": figure, "precision": assessment.precision, "value": assessment.value, "lower": assessment.lower, "upper": assessment.upper,
            "basis": SCALE_BASIS_PLAN_STATED_UNVERIFIED, "verified": False, "resolution": assessment.resolution}
