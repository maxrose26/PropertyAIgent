"""Request-local presentation of one authoritative assessment; never evaluates policy."""
from dataclasses import dataclass
from urllib.parse import urlsplit


FIT_LABELS = {"STRONG_FIT": "Strong Mandate Fit", "POSSIBLE_FIT": "Possible Mandate Fit"}
MANDATE_QUALIFICATION = ("Mandate fit describes compatibility with this buyer's requirements; "
                         "acquisition availability and control are not verified by this result.")


def mandate_fit_label(classification, investigative=False):
    if classification == "INSUFFICIENT_EVIDENCE":
        return "Investigate" if investigative else "Insufficient evidence"
    return FIT_LABELS.get(classification, classification.replace("_", " ").capitalize())


@dataclass(frozen=True)
class MandateExplanation:
    positives: tuple[str, ...]
    classification_causes: tuple[str, ...]
    contextual_limitations: tuple[str, ...]
    investigation: tuple[str, ...]
    coverage: str
    coverage_notice: str
    evidence_context: tuple[str, ...] = ()
    source_link: str | None = None


def _unique(values):
    return tuple(dict.fromkeys(values))


def present_mandate_explanation(assessment, source=None):
    """Preserve reason text and causal provenance, defaulting legacy inputs to partial."""
    source = source or {}
    trace = getattr(assessment, "explanation_trace", None) or ()
    causes = _unique(e.reason for e in trace if e.role == "classification_affecting" and e.contributed)
    positives = tuple(getattr(assessment, "matches", ()) or ())
    contextual = _unique([e.reason for e in trace if e.role == "contextual" and e.reason not in causes] +
                         [r for r in (getattr(assessment, "unknown", ()) or ()) if r not in causes] +
                         [r for r in (getattr(assessment, "does_not_match", ()) or ()) if r not in causes])
    contextual = _unique((*contextual, "Ownership/control is not verified by this mandate assessment",
                          "Acquisition availability is not verified by this mandate assessment",
                          "Physical commencement/completion is not verified by this mandate assessment"))
    investigation = tuple(reason for reason in (getattr(assessment, "investigate", ()) or ()) if reason not in causes)
    complete = bool(trace) and getattr(assessment, "explanation_coverage", None) == "complete"
    coverage = "complete recorded assessment" if complete else (
        "partial recorded explanation" if positives or contextual or investigation or causes else "matching explanation unavailable")
    # The mandatory evidence notices are not themselves matching explanations.
    if not trace and not any((positives, getattr(assessment, "unknown", ()), getattr(assessment, "does_not_match", ()), investigation)):
        coverage = "matching explanation unavailable"
    notice = "Complete recorded assessment" if complete else "Other reasons and classification causes are not fully available."
    if coverage == "matching explanation unavailable":
        notice = "Matching explanation unavailable"
    elif assessment.classification == "POSSIBLE_FIT" and not causes:
        notice = "Possible Mandate Fit — classification explanation not fully available"
    evidence = []
    count = source.get("count_assessment")
    if count is not None:
        evidence.append(f"Count scope: {count.scope_label} ({count.scope_type}); metric: {count.metric}")
        evidence.append(f"Count resolution: {count.resolution.replace('_', ' ')}; confidence: {count.confidence}")
        if count.note():
            evidence.append(count.note())
        references = _unique(getattr(item, "application_reference", "") for item in count.sources)
        if any(references):
            evidence.append("Count supporting applications: " + "; ".join(r for r in references if r))
    reference = source.get("application_reference") or source.get("reference")
    evidence.append(f"Supporting application: {reference}" if reference else "Source provenance incomplete")
    date = source.get("decision_date") or source.get("evidence_date") or source.get("source_date")
    evidence.append(f"Evidence date: {date}" if date else "Evidence date unavailable")
    version = source.get("evidence_version") or source.get("source_version")
    evidence.append(f"Evidence version: {version}" if version else "Evidence version unavailable")
    url = source.get("source_url") or source.get("summary_url") or source.get("source_document_url") or source.get("plan_page_url")
    try:
        parsed = urlsplit(url or "")
        link = url if parsed.scheme in ("https", "http") and parsed.hostname and not parsed.username and not parsed.password else None
    except ValueError:
        link = None
    if not link:
        evidence.append("Source link unavailable")
    return MandateExplanation(positives, causes, contextual, investigation, coverage, notice, tuple(evidence), link)
