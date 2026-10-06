"""Derived count evidence for discovery; no persistence or extraction.

Display precision is not confidence. Rounded values are never qualification
inputs. Sources are the existing fact-level application positions, not invented
document verification. The sole variance allowance is Product Owner approved.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.reporting.commercial_evidence import known_unit_count


@dataclass(frozen=True)
class CountAssessment:
    scope_type: str
    scope_label: str
    subject_id: str = ""
    metric: str = "total_residential"
    precision: str = "UNKNOWN"
    value: int | None = None
    lower: int | None = None
    upper: int | None = None
    resolution: str = "insufficient_evidence"
    confidence: str = "none"
    sources: tuple = ()
    basis: str | None = None
    superseded: tuple = ()

    @property
    def exact_value(self):
        return known_unit_count(self.value) if self.precision == "EXACT" else None

    def label(self):
        noun = "homes" if self.metric == "total_residential" else self.metric.replace("_", " ")
        if self.precision == "EXACT":
            return f"{self.value:,} {noun}"
        if self.precision == "APPROXIMATE":
            return f"~{self.value:,} {noun}"
        if self.precision == "RANGE":
            return f"{self.lower:,}–{self.upper:,} {noun}"
        return "Unit count unverified"

    def note(self):
        if self.resolution == "immaterial_variance":
            return f"Current evidence varies slightly: {self.lower:,}–{self.upper:,}."
        if self.resolution == "material_conflict":
            return "Conflicting unit evidence; verification required."
        if self.precision == "RANGE":
            return "Scale not yet resolved."
        if self.precision == "APPROXIMATE":
            return "Reported estimate; exact scale unverified."
        return ""

    def within_hard_bounds(self, *, minimum=None, maximum=None):
        """Three-state proof: True / False / None (not verified compliant).

        Bounds must be supported; a standalone estimate has no invented bounds.
        A material conflict's envelope is not a qualified range.
        """
        if self.precision == "UNKNOWN" or self.lower is None or self.upper is None:
            return None
        if (minimum is not None and self.upper < minimum) or (maximum is not None and self.lower > maximum):
            return False
        if (minimum is not None and self.lower < minimum) or (maximum is not None and self.upper > maximum):
            return None
        return True

    def fingerprint(self):
        return {"subject": self.subject_id, "scope": self.scope_label, "metric": self.metric,
                "precision": self.precision, "value": self.value, "lower": self.lower,
                "upper": self.upper, "resolution": self.resolution, "basis": self.basis}

    def report_columns(self):
        """Plain export values; never serialize live ORM objects into reports."""
        return {"Count Display": self.label(), "Count Evidence": self.note(),
                "Count Precision": self.precision, "Count Lower": self.lower, "Count Upper": self.upper,
                "Count Scope": self.scope_label, "Count Metric": self.metric,
                "Count Sources": "; ".join(str(getattr(s, "application_reference", "")) for s in self.sources)}


def assess_positions(positions, *, scope_type, scope_label, subject_id="", metric="total_residential",
                     basis=None, confidence="high", superseded=()):
    """Compare already eligible, current same-scope point evidence only."""
    positions = tuple(sorted(positions, key=lambda p: (getattr(p, "application_reference", ""), str(getattr(p, "application_id", "")))))
    base = dict(scope_type=scope_type, scope_label=scope_label, subject_id=subject_id,
                metric=metric, sources=positions, basis=basis, superseded=tuple(superseded))
    if not positions:
        return CountAssessment(**base)
    if any((p.scope_type, p.scope_label) != (scope_type, scope_label) for p in positions):
        return CountAssessment(**base, resolution="unresolved_scope")
    values = {known_unit_count(p.value) for p in positions}
    if None in values:
        return CountAssessment(**base, resolution="malformed_evidence")
    low, high = min(values), max(values)
    if len(values) == 1:
        return CountAssessment(**base, precision="EXACT", value=low, lower=low, upper=high,
                               resolution="agreement", confidence=confidence)
    dates = {getattr(p, "decision_date", None) for p in positions}
    roles = {getattr(p, "planning_role", None) for p in positions}
    compatible_current = len(dates) == 1 and None not in dates and len(roles) == 1 and None not in roles
    if values == {100, 101, 102} and metric == "total_residential" and compatible_current:
        return CountAssessment(**base, precision="APPROXIMATE", value=100, lower=low, upper=high,
                               resolution="immaterial_variance", confidence="medium")
    return CountAssessment(**base, lower=low, upper=high, resolution="material_conflict", confidence="low")


def supported_range(*, lower, upper, sources, scope_type, scope_label, subject_id="", metric="total_residential"):
    """Read-contract entry for explicitly range-qualified source evidence.

    No legacy scalar adapter calls this: min/max competing point claims do not
    establish a source-supported range. Callers must supply matching qualified
    bounds on every source, not just two numbers.
    """
    lo, hi = known_unit_count(lower), known_unit_count(upper)
    base = dict(scope_type=scope_type, scope_label=scope_label, subject_id=subject_id, metric=metric,
                sources=tuple(sources))
    valid = lo is not None and hi is not None and lo <= hi and bool(sources) and bool(subject_id)
    valid = valid and all(getattr(s, "qualified", False) and getattr(s, "qualifier", None) == "range"
                        and getattr(s, "scope_type", None) == scope_type
                        and getattr(s, "scope_label", None) == scope_label
                        and getattr(s, "subject_id", None) == subject_id and getattr(s, "metric", None) == metric
                        and bool(getattr(s, "evidence_date", None)) and bool(getattr(s, "version", None))
                        and bool(getattr(s, "source_reference", None))
                        and getattr(s, "lower", None) == lo and getattr(s, "upper", None) == hi
                        for s in sources)
    if not valid:
        return CountAssessment(**base)
    return CountAssessment(**base, precision="RANGE", lower=lo, upper=hi,
                           resolution="supported_range", confidence="medium")


def is_meaningful_provenance(value):
    """True only for a non-empty, non-whitespace string reference.

    Structurally meaningless provenance (True, 1, object(), "", "   ", None) is
    never evidence. Whether the text is factually authoritative is a later
    evidence-validation question, not decided here.
    """
    return isinstance(value, str) and bool(value.strip())


def evidenced_pairs(evidence):
    """Unordered identifier pairs that have explicit, sourced non-overlap evidence.

    The single rule shared by phase aggregation and residual planning-capacity
    arithmetic: a pair without meaningful provenance is not evidence, and
    nothing is inferred from labels, references, dates, chronology or arithmetic.
    """
    return {frozenset((left, right)) for left, right, source in evidence if is_meaningful_provenance(source)}


# Metrics whose count comes from an application's total_units_final. A private or
# affordable count must never be attributed to a source through that field.
COUNT_SOURCE_METRICS = frozenset({"total_residential", "all_use_units"})


def select_count_supporting_source(count_assessment, applications, *, operative_application_id=None):
    """The application a displayed exact residential count may be attributed to, or None.

    Support first, operative preference second. Only an application that actually
    supports the exact count qualifies: it is one of the count's own sources AND its
    extracted total equals that count. Among genuine supporters the trusted operative
    application is preferred when it is one of them; otherwise a deterministic
    reference/ID order picks one. That fallback is merely deterministic - it does not
    mean the chosen application has more commercial authority. An application that is
    operative, newer, older or alphabetically convenient but does NOT support the count
    never receives attribution. Never changes or recomputes the count itself.
    """
    if count_assessment is None or count_assessment.metric not in COUNT_SOURCE_METRICS:
        return None
    exact = count_assessment.exact_value
    if exact is None:
        return None
    source_ids = {source.application_id for source in count_assessment.sources
                  if known_unit_count(source.value) == exact}
    supporters = []
    for application in applications:
        scheme = getattr(application, "scheme_intelligence", None)
        if application.id in source_ids and scheme is not None and known_unit_count(scheme.total_units_final) == exact:
            supporters.append(application)
    if not supporters:
        return None
    if operative_application_id is not None:
        for application in supporters:
            if application.id == operative_application_id:
                return application
    return min(supporters, key=lambda application: (application.reference or "", str(application.id)))


def aligned_tenure_counts(total, private, affordable):
    """Return a coherent breakdown only with identical source/version identity.

    This never qualifies an AH claim or proves package availability.
    """
    values = (total, private, affordable)
    if any(v.exact_value is None or not v.sources for v in values):
        return None
    # Legacy application scalars have no count-level document revision. They
    # cannot manufacture this stronger alignment. Existing AH reported evidence
    # remains separate until a qualified same-version source is supplied.
    if any(not getattr(s, "version", None) or not getattr(s, "source_reference", None)
           or not getattr(s, "evidence_date", None) or not getattr(s, "qualified", False)
           or getattr(s, "metric", None) != v.metric or getattr(s, "subject_id", None) != v.subject_id
           for v in values for s in v.sources):
        return None
    identities = [{(s.source_reference, s.version, s.evidence_date) for s in v.sources} for v in values]
    if not (total.metric == "total_residential" and private.metric == "private_units"
            and affordable.metric == "affordable_units"):
        return None
    if len({(v.subject_id, v.scope_type, v.scope_label) for v in values}) != 1 or not identities[0] == identities[1] == identities[2]:
        return None
    if private.value + affordable.value != total.value:
        return None
    return {"total": total.value, "private": private.value, "affordable": affordable.value}
