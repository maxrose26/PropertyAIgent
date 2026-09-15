"""Agent Evaluation Policy V1 - deterministic post-validator (narrow
implementation slice).

Rejects an LLM result whose SHAPE or EVIDENCE DISCIPLINE is unsafe, without
ever re-judging whether the commercial recommendation itself was the
"right" call (Section O of the design report: "checks shape and evidence
discipline, never re-derives whether PURSUE was the right answer").

Every check here is a pure function over already-parsed JSON + the exact
PromptContext that was actually sent to the model - nothing here queries
the database or calls an LLM."""
from __future__ import annotations

from dataclasses import dataclass

from app.policy.agent_evaluation_prompt import PromptContext
from app.policy.agent_evaluation_result import (
    ACQUISITION_SUBJECT_LEVELS,
    CONFIDENCE_VALUES,
    IDENTIFY_PHASE_OR_PARCEL,
    MONITOR,
    MONITORING_TRIGGER_VALUES,
    NEXT_ACTION_VALUES,
    NOT_RELEVANT,
    PARCEL_TBD,
    PHASE,
    RECOMMENDATION_VALUES,
    VERIFY,
    AcquisitionSubject,
    AgentEvaluationResult,
    AgentEvaluationResultKey,
    MaterialSignal,
    MaterialUnknown,
)

# --- Unsupported-language guard ---------------------------------------------
#
# Negation-aware, per-sentence (mirrors app.reporting.opportunity_
# transaction_signals' own test-time pattern, promoted here to production
# validation code): a sentence stating a forbidden phrase WITHOUT a
# negation cue in the same sentence is rejected; a sentence explicitly
# negating it ("no evidence establishes that the site is available") is
# exactly the required safety language and must be accepted.
FORBIDDEN_PHRASES = (
    "is available", "for sale", "motivated seller", "likely to sell", "willing to sell",
    "wants out", "wants to sell", "unwilling to sell",
    "site is dormant", "site dormant", "land banked", "land-banked",
    "construction has started", "construction commenced", "construction has commenced",
    "development has commenced", "development is underway", "development underway",
    "physical works have started", "physical works started", "site is inactive",
    "confirmed uncommenced", "owner is not progressing", "owner not progressing",
    "self-delivering", "self delivering",
)

_NEGATION_CUES = (
    "does not", "do not", "never", "not itself", "not that", "not proof", "no evidence",
    "not confirmed", "not established", "not mean", "cannot", "can not", "no direct evidence",
)


def find_unsupported_language(text: str | None) -> str | None:
    """Returns the first unqualified forbidden phrase found, or None."""
    if not text:
        return None
    lowered = text.lower()
    for sentence in lowered.split("."):
        for phrase in FORBIDDEN_PHRASES:
            if phrase in sentence and not any(cue in sentence for cue in _NEGATION_CUES):
                return phrase
    return None


@dataclass(frozen=True)
class ValidationOutcome:
    ok: bool
    result: AgentEvaluationResult | None
    errors: tuple[str, ...]


def _get(d: dict, key: str, expected_type, errors: list[str]):
    if key not in d:
        errors.append(f"missing required field {key!r}")
        return None
    value = d[key]
    if expected_type is not None and not isinstance(value, expected_type):
        errors.append(f"field {key!r} has wrong type: expected {expected_type}, got {type(value)}")
        return None
    return value


def validate_and_build_result(
    raw: dict, *, context: PromptContext, key: AgentEvaluationResultKey,
    mandate_fingerprint: str, opportunity_fingerprint: str, evaluation_policy_version: str,
) -> ValidationOutcome:
    """The one entry point app.policy.acquisition_evaluate calls after
    parsing the model's own JSON output. Returns ok=False with a non-empty
    errors tuple on ANY violation - the caller (acquisition_evaluate) owns
    the bounded repair/retry policy, this function never retries itself."""
    errors: list[str] = []
    valid_refs = set(context.reference_tokens.keys())

    if not isinstance(raw, dict):
        return ValidationOutcome(False, None, (f"top-level output is not a JSON object: {type(raw)}",))

    recommendation = _get(raw, "recommendation", str, errors)
    confidence = _get(raw, "confidence", str, errors)
    confidence_basis = _get(raw, "confidence_basis", list, errors)
    acquisition_subject_raw = _get(raw, "acquisition_subject", dict, errors)
    supporting_reasons = _get(raw, "supporting_reasons", list, errors)
    countervailing_reasons = _get(raw, "countervailing_reasons", list, errors)
    material_unknowns_raw = _get(raw, "material_unknowns", list, errors)
    reasoning_summary = _get(raw, "reasoning_summary", str, errors)
    next_action = _get(raw, "next_action", str, errors)
    next_action_detail = _get(raw, "next_action_detail", str, errors)
    monitoring_trigger = raw.get("monitoring_trigger")
    evidence_references = _get(raw, "evidence_references", list, errors)

    if errors:
        return ValidationOutcome(False, None, tuple(errors))

    if recommendation not in RECOMMENDATION_VALUES:
        errors.append(f"recommendation {recommendation!r} not in {sorted(RECOMMENDATION_VALUES)}")
    if confidence not in CONFIDENCE_VALUES:
        errors.append(f"confidence {confidence!r} not in {sorted(CONFIDENCE_VALUES)}")
    if next_action not in NEXT_ACTION_VALUES:
        errors.append(f"next_action {next_action!r} not in {sorted(NEXT_ACTION_VALUES)}")
    if monitoring_trigger is not None and monitoring_trigger not in MONITORING_TRIGGER_VALUES:
        errors.append(f"monitoring_trigger {monitoring_trigger!r} not in {sorted(MONITORING_TRIGGER_VALUES)}")
    if recommendation == MONITOR and not monitoring_trigger:
        errors.append("MONITOR requires a non-null monitoring_trigger")

    # Acquisition subject shape.
    acquisition_subject = None
    if acquisition_subject_raw is not None:
        level = acquisition_subject_raw.get("level")
        reference = acquisition_subject_raw.get("reference")
        note = acquisition_subject_raw.get("note")
        if level not in ACQUISITION_SUBJECT_LEVELS:
            errors.append(f"acquisition_subject.level {level!r} not in {sorted(ACQUISITION_SUBJECT_LEVELS)}")
        else:
            acquisition_subject = AcquisitionSubject(level=level, reference=reference, note=note)

            # PARCEL_TBD means "a smaller subject MAY exist but has not
            # been identified" (Pre-Release Commercial Semantic Fix,
            # Section 2/I) - a populated `reference` asserts a SPECIFIC
            # parcel/phase has been identified, which contradicts that
            # meaning outright. This is a pure structural check (no NLP):
            # if the model actually has a specific reference, PHASE is the
            # correct level, never PARCEL_TBD.
            if level == PARCEL_TBD and reference:
                errors.append(
                    f"acquisition_subject.level=PARCEL_TBD must not carry a specific reference "
                    f"(got {reference!r}) - a populated reference asserts a parcel has been identified, "
                    "which contradicts PARCEL_TBD's own meaning; use PHASE instead if a specific "
                    "phase/parcel has actually been established by evidence"
                )

            # Structural acquisition-subject/next-action consistency
            # (Pre-Release Commercial Semantic Fix, Section 3): choosing
            # next_action=IDENTIFY_PHASE_OR_PARCEL is itself a statement
            # that the true acquisition subject is not yet established -
            # it is therefore inconsistent with an acquisition_subject that
            # already claims to BE the whole evidence object
            # (WHOLE_ALLOCATION/DEVELOPMENT_SITE) or the whole affordable
            # package/pipeline. Checked via the bounded next_action field,
            # never via free-text pattern-matching over reasoning_summary.
            if next_action == IDENTIFY_PHASE_OR_PARCEL and level not in (PARCEL_TBD, PHASE):
                errors.append(
                    f"next_action=IDENTIFY_PHASE_OR_PARCEL is inconsistent with acquisition_subject.level="
                    f"{level!r} - choosing to identify a phase/parcel implies the acquisition subject is not "
                    "yet established; use acquisition_subject.level=PARCEL_TBD (or PHASE if a specific "
                    "phase/parcel is already evidenced), never WHOLE_ALLOCATION or DEVELOPMENT_SITE"
                )

    # Evidence-reference discipline: every cited reference must be one of
    # the exact tokens actually supplied in this evaluation's own context -
    # never a fact the model was not given (Section 16 of the narrow-
    # implementation authorisation).
    def _check_refs(label: str, refs) -> None:
        for r in refs:
            if r not in valid_refs:
                errors.append(f"{label} cites unknown reference token {r!r} (not present in this evaluation's own context)")

    _check_refs("confidence_basis", confidence_basis or [])
    _check_refs("evidence_references", evidence_references or [])

    positive_signals: list[MaterialSignal] = []
    for item in supporting_reasons or []:
        ref = item.get("evidence_reference")
        if ref not in valid_refs:
            errors.append(f"supporting_reasons cites unknown reference token {ref!r}")
        else:
            positive_signals.append(MaterialSignal(label=item.get("label", ""), source_reference=ref))

    negative_signals: list[MaterialSignal] = []
    countervailing_refs_valid: list[str] = []
    for item in countervailing_reasons or []:
        ref = item.get("evidence_reference")
        if ref not in valid_refs:
            errors.append(f"countervailing_reasons cites unknown reference token {ref!r}")
        else:
            negative_signals.append(MaterialSignal(label=item.get("label", ""), source_reference=ref))
            countervailing_refs_valid.append(ref)

    unknowns: list[MaterialUnknown] = []
    for item in material_unknowns_raw or []:
        try:
            unknowns.append(MaterialUnknown(
                fact_or_question=item["fact_or_question"], blocking=bool(item["blocking"]),
                resolvable=bool(item["resolvable"]), material=bool(item.get("material", True)),
                why_it_matters=item.get("why_it_matters", ""),
            ))
        except (KeyError, TypeError) as exc:
            errors.append(f"material_unknowns entry malformed: {exc}")

    # VERIFY requires >=1 material+resolvable+blocking unknown (Section 11
    # of the narrow-implementation authorisation - "VERIFY requires at
    # least one: blocking=True, resolvable=True material unknown").
    if recommendation == VERIFY:
        if not any(u.material and u.resolvable and u.blocking for u in unknowns):
            errors.append("VERIFY requires at least one material_unknowns entry with material=True, resolvable=True, blocking=True")

    # MONITOR must never be "investigate now" in disguise (Pre-Release
    # Commercial Semantic Fix, Section 6/10): the governing policy's own
    # formula is MATERIAL + RESOLVABLE + BLOCKING == VERIFY. If the model's
    # own material_unknowns already contain such an entry, MONITOR is
    # structurally inconsistent with it - a question that could be
    # resolved NOW is investigation work to do now (PURSUE or VERIFY),
    # never a reason to defer to some future external trigger. Confirmed
    # live: a model that correctly marks an unknown material+resolvable+
    # blocking nonetheless sometimes still chose MONITOR instead of VERIFY.
    if recommendation == MONITOR and any(u.material and u.resolvable and u.blocking for u in unknowns):
        errors.append(
            "MONITOR is inconsistent with a material_unknowns entry that is material=True, resolvable=True, "
            "blocking=True - by this policy's own rule (MATERIAL + RESOLVABLE + BLOCKING = VERIFY), a "
            "question resolvable right now is investigation work to act on (VERIFY, or PURSUE if the "
            "opportunity already has a credible angle), never a reason to wait for a future external trigger"
        )

    # A countervailing reason is only real grounding for DEFERRING/
    # REJECTING an opportunity if it cites a CONFIRMED fact -
    # "buyer_fit.unknown[i]" and "buyer_fit.investigate[i]" are Buyer Fit's
    # own "could not establish this" buckets (see agent_evaluation_prompt.
    # build_prompt_context), not confirmed negative facts. Citing only
    # those to justify NOT pursuing now is the same "unknown reframed as a
    # confirmed negative" pattern whether the recommendation is NOT_RELEVANT
    # (Section 3/9 - confirmed live via BENCHMARK 3) or MONITOR (confirmed
    # live via the Pre-Release Commercial Semantic Fix calibration - a
    # model citing only "scale exceeds target" via buyer_fit.unknown[i] to
    # justify MONITOR instead of investigating now).
    #
    # Final Pre-Release Ownership & Stability Patch, Section 3: "missing
    # ownership/control evidence must NOT cause an otherwise interesting
    # opportunity to be systematically discounted." packet.actors_control.
    # has_ownership_evidence is a genuinely CONFIRMED fact even when its
    # value is False (absence really was confirmed) - but citing the
    # ABSENCE of ownership evidence as countervailing/negative grounding is
    # exactly the forbidden "ordinary incompleteness treated as a negative
    # signal" pattern, confirmed live (a model citing "no ownership/control
    # evidence established" as its countervailing basis for MONITOR). Only
    # the ABSENCE value is excluded here - a confirmed PRESENCE of
    # ownership evidence (has_ownership_evidence=True) is legitimate
    # negative grounding where relevant (e.g. combined with the ownership/
    # control posture), so this is a narrow, value-specific exclusion, not
    # a blanket ban on the token.
    def _is_absence_of_ownership_evidence(ref: str) -> bool:
        return ref == "packet.actors_control.has_ownership_evidence" and context.reference_tokens.get(ref) == "False"

    _NOT_A_CONFIRMED_FACT_PREFIXES = ("buyer_fit.unknown[", "buyer_fit.investigate[")
    confirmed_countervailing_refs = [
        r for r in countervailing_refs_valid
        if not r.startswith(_NOT_A_CONFIRMED_FACT_PREFIXES) and not _is_absence_of_ownership_evidence(r)
    ]
    confirmed_negative_signals = [
        s for s in negative_signals
        if not s.source_reference.startswith(_NOT_A_CONFIRMED_FACT_PREFIXES) and not _is_absence_of_ownership_evidence(s.source_reference)
    ]

    # Recommendation-vs-evidence consistency: MONITOR (and NOT_RELEVANT)
    # both mean "the current commercial case does not justify effort now" -
    # if the model itself supplied at least one supporting_reasons entry,
    # zero CONFIRMED countervailing_reasons, and every material_unknowns
    # entry is blocking=False, there is no honest basis left for anything
    # other than PURSUE. This is not re-judging commercial attractiveness
    # (Section O's own limit) - it is catching the model contradicting its
    # OWN structured fields with its OWN recommendation, a real,
    # reproducible failure mode confirmed during live calibration (a model
    # that correctly marks both unknowns non-blocking yet still returns
    # MONITOR, in one case grounded only in a buyer_fit.unknown[i] token).
    if recommendation in (MONITOR, NOT_RELEVANT) and positive_signals and not confirmed_negative_signals:
        if unknowns and all(not u.blocking for u in unknowns):
            errors.append(
                f"{recommendation} is inconsistent with the model's own structured output: at least one "
                "supporting reason was cited, no CONFIRMED countervailing reason was cited (a "
                "buyer_fit.unknown[i]/buyer_fit.investigate[i] citation alone does not count), and every "
                "material_unknowns entry is blocking=false - there is no basis left for anything other than "
                "PURSUE (with any non-blocking unknowns investigated in parallel)"
            )

    # NOT_RELEVANT must never rely solely on an unknown/soft-miss/absence-
    # of-disposal-evidence basis (Section 3 - "never solely because of
    # UNKNOWN / soft target miss / absence of disposal evidence"), and - per
    # the Final Pre-Release Ownership & Stability Patch, Section 13 -
    # "KNOWN DEVELOPER, even a KNOWN NATIONAL HOUSEBUILDER, alone must not
    # create NOT_RELEVANT". packet.actors_control.* tokens are transaction/
    # ownership CONTEXT (who has been identified, what posture applies) -
    # they are never themselves a mandate-INCOMPATIBILITY fact, so citing
    # only those does not satisfy NOT_RELEVANT's own evidentiary bar either
    # (they remain legitimate grounding for MONITOR, which only means
    # "insufficient case right now" - see confirmed_negative_signals above,
    # deliberately NOT filtered the same way).
    _NOT_A_MANDATE_INCOMPATIBILITY_PREFIXES = _NOT_A_CONFIRMED_FACT_PREFIXES + ("packet.actors_control.",)
    confirmed_countervailing_refs = [
        r for r in confirmed_countervailing_refs if not r.startswith(_NOT_A_MANDATE_INCOMPATIBILITY_PREFIXES)
    ]
    if recommendation == NOT_RELEVANT and not confirmed_countervailing_refs:
        errors.append(
            "NOT_RELEVANT requires at least one countervailing_reasons entry citing a CONFIRMED MANDATE-"
            "INCOMPATIBILITY fact (packet.* excluding actors_control.*, signals.*, or "
            "buyer_fit.non_terminal_does_not_match[i]) - never solely material_unknowns, never solely "
            "buyer_fit.unknown[i]/buyer_fit.investigate[i] (Buyer Fit's own unresolved buckets), and never "
            "solely packet.actors_control.* (developer/ownership identity is transaction context, never "
            "itself a mandate-incompatibility fact)"
        )

    # Unsupported-language guard across every free-text field.
    free_text_fields = [("reasoning_summary", reasoning_summary), ("next_action_detail", next_action_detail)]
    for item in (supporting_reasons or []):
        free_text_fields.append(("supporting_reasons.label", item.get("label")))
    for item in (countervailing_reasons or []):
        free_text_fields.append(("countervailing_reasons.label", item.get("label")))
    for item in (material_unknowns_raw or []):
        free_text_fields.append(("material_unknowns.why_it_matters", item.get("why_it_matters")))
    if acquisition_subject_raw is not None:
        free_text_fields.append(("acquisition_subject.note", acquisition_subject_raw.get("note")))

    for field_name, text in free_text_fields:
        phrase = find_unsupported_language(text)
        if phrase is not None:
            errors.append(f"{field_name} contains unsupported language ({phrase!r}): {text!r}")

    if errors:
        return ValidationOutcome(False, None, tuple(errors))

    try:
        result = AgentEvaluationResult(
            key=key,
            recommendation=recommendation,
            confidence=confidence,
            confidence_basis=tuple(confidence_basis),
            acquisition_subject=acquisition_subject,
            material_positive_signals=tuple(positive_signals),
            material_negative_signals=tuple(negative_signals),
            material_unknowns=tuple(unknowns),
            reasoning_summary=reasoning_summary,
            next_action=next_action,
            next_action_detail=next_action_detail,
            monitoring_trigger=monitoring_trigger,
            evidence_references=tuple(evidence_references),
            mandate_fingerprint=mandate_fingerprint,
            opportunity_fingerprint=opportunity_fingerprint,
            evaluation_policy_version=evaluation_policy_version,
        )
    except ValueError as exc:
        return ValidationOutcome(False, None, (f"AgentEvaluationResult construction failed: {exc}",))

    return ValidationOutcome(True, result, ())
