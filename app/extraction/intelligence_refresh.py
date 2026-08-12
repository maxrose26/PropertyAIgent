"""PR B3: Evidence-Driven AI Intelligence Refresh.

B1 (app.pipeline.material_change) detects a material planning-state change.
B2 (app.pipeline.evidence_refresh) turns that into a targeted portal check
and, on genuinely new relevant evidence, advances Application.material_
evidence_changed_at - the B3 handoff signal. Neither of those two PRs ever
touches SchemeIntelligence or calls OpenAI.

This module is what CONSUMES that handoff: for one Application whose live
SchemeIntelligence is now stale relative to material_evidence_changed_at, it
works out how deep a refresh the triggering B1 reason warrants (ROUTING
below), assembles a bounded, evidence-authority-ordered set of document text
from the already-linked application family, asks ONE structured LLM call to
produce an updated planning-outcome + affordable-housing position, and - only
if that succeeds AND the regenerated Site Summary also succeeds - commits
the whole replacement atomically and advances the intelligence_evidence_
processed_at watermark. Any failure anywhere in that sequence leaves the
previous live SchemeIntelligence, Site Summary, and watermark completely
untouched (see refresh_intelligence_for_application's own docstring).

Deliberately reuses rather than duplicates:
  - app.extraction.run_extraction's OUTCOME_* taxonomy (no second AI failure
    system - PR B3 spec, Part 28);
  - app.pipeline.evidence_refresh.resolve_application_family (the same
    bounded, already-persisted-relationships-only family B2 itself checks -
    never "every Application on the Site");
  - app.extraction.pdf_text.build_combined_priority_text/clean_document_text
    (the same text-assembly/truncation machinery the original extraction
    pipeline already uses).

AFFORDABLE HOUSING AS FIRST-CLASS INTELLIGENCE (explicit Product Owner
requirement, this PR's own Part 10-14): the existing SchemeIntelligence.
affordable_data_status field only ever answers "did we find affordable
DATA" (affordable_percentage_found, insufficient_evidence, ...) - a
different question from this module's own affordable_housing_status,
which answers "what is the SECURITY/AUTHORITY of that data" (proposed
through legally_secured - see AFFORDABLE_HOUSING_STATUSES below). The one
hard commercial rule the prompt/schema exist to enforce: Property AIgent
must never describe a merely-proposed affordable position as legally
secured - only executed S106/operative Deed of Variation evidence may
justify that value.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field

from openai import OpenAI, OpenAIError

from app.db.models import Application, Document, Site
from app.extraction.pdf_text import build_combined_priority_text, clean_document_text
from app.extraction.run_extraction import (
    OUTCOME_AI_ERROR,
    OUTCOME_ERROR,
    OUTCOME_INVALID_OUTPUT,
    OUTCOME_NO_USABLE_TEXT,
    OUTCOME_SUCCESS,
)
from app.pipeline.evidence_refresh import resolve_application_family
from app.pipeline.material_change import (
    REASON_DECISION_GRANTED,
    REASON_DECISION_OUTCOME_UNKNOWN,
    REASON_DECISION_REFUSED,
    REASON_DECISION_WITHDRAWN,
    REASON_RECOMMENDATION_MADE,
    REASON_RECOMMENDED_FOR_APPROVAL,
    REASON_RECOMMENDED_FOR_REFUSAL,
    REASON_UNIT_COUNT_CHANGED,
)

MODEL = "gpt-4o-mini"

# --- Event-aware refresh depth (PR B3 spec, Parts 8, 16-21) -------------------

DEPTH_BROAD = "broad"
DEPTH_FOCUSED_REFUSAL = "focused_refusal"
DEPTH_FOCUSED_WITHDRAWAL = "focused_withdrawal"
DEPTH_RECOMMENDATION = "recommendation"
DEPTH_DECISION_RESOLUTION = "decision_resolution"
DEPTH_UNIT_CHANGE = "unit_change"

# One reason -> one depth (Part 7: "evidence is authoritative" - the B1
# reason only ever picks a STARTING depth/prompt focus, never gates which
# evidence categories the refresh is allowed to look at; the document set
# itself already comes from whatever B2 most recently acquired for this
# Application, regardless of which reason triggered that acquisition).
_DEPTH_BY_REASON = {
    REASON_DECISION_GRANTED: DEPTH_BROAD,
    REASON_DECISION_REFUSED: DEPTH_FOCUSED_REFUSAL,
    REASON_DECISION_WITHDRAWN: DEPTH_FOCUSED_WITHDRAWAL,
    REASON_RECOMMENDATION_MADE: DEPTH_RECOMMENDATION,
    REASON_RECOMMENDED_FOR_APPROVAL: DEPTH_RECOMMENDATION,
    REASON_RECOMMENDED_FOR_REFUSAL: DEPTH_RECOMMENDATION,
    REASON_DECISION_OUTCOME_UNKNOWN: DEPTH_DECISION_RESOLUTION,
    REASON_UNIT_COUNT_CHANGED: DEPTH_UNIT_CHANGE,
}


def refresh_depth_for_reasons(reasons: list[str] | tuple[str, ...]) -> str:
    """Multiple simultaneous B1 reasons (comma-joined in Application.
    evidence_refresh_reason - see that field's own comment) always widen to
    the broadest depth any one of them alone would warrant - a focused
    refresh must never silently drop a reason a broader one would have
    covered. An unrecognised/empty reason set also defaults to BROAD
    (Part 9: a later S106/DoV can advance material_evidence_changed_at with
    NO fresh B1 reason at all - the safest default when the trigger is
    ambiguous is the widest refresh, not the narrowest)."""
    if not reasons:
        return DEPTH_BROAD
    depths = {_DEPTH_BY_REASON.get(r, DEPTH_BROAD) for r in reasons}
    if DEPTH_BROAD in depths:
        return DEPTH_BROAD
    if len(depths) > 1:
        return DEPTH_BROAD
    return depths.pop()


# Which document categories are worth including at each depth - deliberately
# reuses app.pipeline.evidence_refresh.ROUTING's own category vocabulary
# rather than inventing a parallel one, but is its own mapping: B2's ROUTING
# answers "what should be portal-checked for this reason", B3's answers
# "what evidence should the LLM actually read for this refresh depth" -
# related but not identical questions (e.g. a focused refusal refresh reads
# s106 too, since a refusal can still turn on an unresolved S106 position).
_DOC_TYPES_BY_DEPTH = {
    # B3 live-validation amendment (Defect C) - a dedicated Affordable
    # Housing / Viability Statement (doc_type=viability_affordable_housing)
    # is exactly the kind of evidence a BROAD refresh should read; confirmed
    # by the first live Oldham sample, whose real "AFFORDABLE HOUSING
    # STATEMENT" document was silently skipped because this set didn't
    # include its category. Deliberately NOT added to any focused depth
    # below - Part 11 of the amendment: only BROAD is mandated.
    DEPTH_BROAD: frozenset({
        "decision_notice", "officer_report", "s106", "planning_statement", "design_access",
        "viability_affordable_housing",
    }),
    DEPTH_FOCUSED_REFUSAL: frozenset({"decision_notice", "officer_report", "s106"}),
    DEPTH_FOCUSED_WITHDRAWAL: frozenset({"decision_notice", "officer_report"}),
    DEPTH_RECOMMENDATION: frozenset({"officer_report", "s106"}),
    DEPTH_DECISION_RESOLUTION: frozenset({"decision_notice", "officer_report", "s106"}),
    DEPTH_UNIT_CHANGE: frozenset({"planning_statement", "design_access", "officer_report"}),
}


# --- Evidence authority + input selection (PR B3 spec, Parts 14, 26) --------

# Simple, explicit ranking, not a document-relationship graph (Part 14:
# "do not hard-code a simplistic hierarchy if document relationships are
# more nuanced" - kept honest by NOT claiming more precision than a flat
# rank can offer: this only orders which evidence the model reads FIRST/
# most prominently, the prompt itself - see build_refresh_prompt - still
# explicitly instructs the model to note a genuine conflict rather than
# silently prefer rank). s106 ranks equal to decision_notice (both are
# operative legal/formal evidence); officer_report below both (informs but
# does not itself decide); planning/design statements lowest (applicant's
# own proposal, not the council's or a legal instrument's position).
_EVIDENCE_AUTHORITY_RANK = {
    "s106": 3,
    "decision_notice": 3,
    "officer_report": 2,
    "planning_statement": 1,
    "design_access": 1,
    # Same tier as planning_statement/design_access - applicant/consultant-
    # authored, not a legal instrument or the council's own determination,
    # so it must never outrank officer_report/s106/decision_notice; but it
    # still needs a real (non-zero) rank so it isn't starved to always-last
    # at the MAX_REFRESH_CONTEXT_CHARS truncation boundary.
    "viability_affordable_housing": 1,
}

# Matches app.extraction.pdf_text.MAX_TOTAL_CHARS - the same bound the
# original extraction pipeline already applies, reused rather than
# reinvented (Part 26: "control context size").
MAX_REFRESH_CONTEXT_CHARS = 120000


def select_refresh_evidence_documents(family: list[Application], depth: str) -> list[Document]:
    """Bounded, authority-ordered evidence selection across an already-
    resolved Application family (Part 26: "do not blindly send every
    historical document... Original S106 + later Deed of Variation may
    both be required" - so this includes every stored Document of a
    relevant category across the WHOLE family, not just the triggering
    Application, and ranks by authority+recency rather than truncating to
    one). Deduplicated by id (a shared Document row is impossible today,
    but this stays correct even if that ever changes)."""
    target_types = _DOC_TYPES_BY_DEPTH.get(depth, _DOC_TYPES_BY_DEPTH[DEPTH_BROAD])
    seen: set[int] = set()
    docs: list[Document] = []
    for application in family:
        for document in application.documents:
            if document.doc_type not in target_types:
                continue
            if not (document.text_extracted and document.extracted_text):
                continue
            if document.id in seen:
                continue
            seen.add(document.id)
            docs.append(document)

    docs.sort(
        key=lambda d: (
            _EVIDENCE_AUTHORITY_RANK.get(d.doc_type, 0),
            d.downloaded_at or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
        ),
        reverse=True,
    )
    return docs


# --- Affordable housing status vocabulary (PR B3 spec, Part 12) --------------

AFFORDABLE_HOUSING_STATUSES = frozenset({
    "proposed", "policy_required", "officer_recommended", "committee_position",
    "agreed", "conditioned", "legally_secured", "subject_to_viability_review", "unknown",
})

# The one hard commercial rule (Part 12's own words: "Property AIgent must
# not describe a proposal as legally secured") - only these statuses are
# permitted to originate from S106/decision-notice-level evidence; the
# schema enum itself doesn't encode this (JSON schema can't express
# cross-field evidence constraints), so it's enforced by prompt instruction
# plus this constant documenting the rule for any future validation logic.
LEGALLY_SECURED_STATUS = "legally_secured"

# PR B3 FINAL pre-merge amendment ("Schema Reconciliation + Affordable
# Housing Change Narrative") - the document types capable of legally
# authorising an affordable housing position (Part 10/20: "a numerical
# difference alone is not proof the newer value supersedes the older one").
# Deliberately the same operative-legal-instrument set the prompt's own
# LEGALLY_SECURED_STATUS rule already names.
_LEGALLY_AUTHORITATIVE_DOC_TYPES = frozenset({"s106", "decision_notice"})


def _evidence_includes_legally_authoritative_document(documents: list[Document]) -> bool:
    return any(d.doc_type in _LEGALLY_AUTHORITATIVE_DOC_TYPES for d in documents)


def guard_legally_secured_position(existing_intelligence, new_fields_raw: dict, documents: list[Document]) -> dict:
    """Deterministic, code-level safety net for the evidence-authority rule
    build_refresh_prompt's own instructions already ask the model to follow -
    not a replacement for those instructions, a backstop against the model
    getting it wrong. If the CURRENTLY LIVE position is already legally_
    secured and THIS PASS's own evidence set contains no legally-
    authoritative document (s106/decision_notice - see _LEGALLY_
    AUTHORITATIVE_DOC_TYPES), a lower-authority document (an applicant
    statement, a later marketing document, an officer report...) can never
    downgrade or contradict it - Part 10's own example: "Executed S106: 20%
    ... later marketing/planning statement: 35% -> do NOT automatically
    replace the legally secured 20%." Returns new_fields_raw unchanged if
    the guard does not apply; otherwise returns a copy with the affordable
    fields forced back to the existing secured values and affordable_
    housing_notes left untouched (never describes a downgrade that didn't
    genuinely happen)."""
    if existing_intelligence is None or existing_intelligence.affordable_housing_status != LEGALLY_SECURED_STATUS:
        return new_fields_raw
    if _evidence_includes_legally_authoritative_document(documents):
        return new_fields_raw
    if new_fields_raw.get("affordable_housing_status") == LEGALLY_SECURED_STATUS:
        return new_fields_raw  # model already correctly preserved it - nothing to guard

    guarded = dict(new_fields_raw)
    guarded["affordable_housing_status"] = LEGALLY_SECURED_STATUS
    guarded["affordable_percentage"] = existing_intelligence.affordable_percentage_final
    guarded["affordable_units"] = existing_intelligence.affordable_units_final
    guarded["affordable_tenure_split"] = existing_intelligence.affordable_tenure_split_final
    guarded["affordable_housing_notes"] = existing_intelligence.affordable_housing_notes
    # This guard only ever fires when the position was already fully
    # legally_secured AND this pass's evidence contains no legally-
    # authoritative document at all (nothing new about security this pass)
    # - so the reasserted position is by definition still fully secured.
    # Without this, guard_mixed_legal_security_position below (which reads
    # this same flag) would immediately undo this guard's own protection.
    guarded["affordable_provision_fully_legally_secured"] = True
    return guarded


# PR B3 pre-historical-rebuild amendment (Defect A: legal-security scope) -
# guard_legally_secured_position above only protects a DOWNGRADE of an
# already-secured position by lower-authority evidence. Phase 3's live
# Trafford 114786/FUL/24 sample exposed the OPPOSITE failure mode: a
# genuine executed S106 present anywhere in the evidence incorrectly
# promoted the ENTIRE current affordable total (50% / 73 units) to
# legally_secured, even though the same evidence explicitly distinguished
# a legally-secured base (10%, via the S106) from a separately-delivered
# additional non-S106 component (a further 40%). The mere presence of an
# authoritative legal document must never, by itself, promote the whole
# current total - only the portion that document actually secures.
MIXED_SECURITY_FALLBACK_STATUS = "conditioned"

# Deliberately a small, bounded keyword/phrase scan - not a general legal-
# reasoning engine - and only a second, independent signal alongside the
# model's own affordable_provision_fully_legally_secured flag (see
# REFRESH_SCHEMA/build_refresh_prompt below). Matches the real evidenced
# phrasing from the Trafford sample ("an additional 40% non-s106
# affordable homes").
_MIXED_SECURITY_SIGNAL_PATTERNS = [
    re.compile(r"non[\s-]?s106", re.IGNORECASE),
    re.compile(r"outside\s+(?:the|of\s+the)\s+(?:s106|section\s*106)", re.IGNORECASE),
    re.compile(r"in\s+addition\s+to\s+the\s+(?:s106|section\s*106)", re.IGNORECASE),
    re.compile(r"additional\s+to\s+the\s+(?:s106|section\s*106)", re.IGNORECASE),
]


def _evidence_indicates_mixed_affordable_security(evidence_text: str) -> bool:
    text = evidence_text or ""
    return any(pattern.search(text) for pattern in _MIXED_SECURITY_SIGNAL_PATTERNS)


def guard_mixed_legal_security_position(new_fields_raw: dict, evidence_text: str) -> dict:
    """Deterministic backstop for the mixed-security overclaim (Defect A) -
    the UPWARD failure mode guard_legally_secured_position's own DOWNWARD
    guard does not cover. Blocks affordable_housing_status="legally_secured"
    for the CURRENT TOTAL position unless BOTH: (1) the model itself
    explicitly asserts affordable_provision_fully_legally_secured=true, AND
    (2) the evidence text contains no explicit mixed-security signal phrase
    - a legally-authoritative document merely existing somewhere in the
    evidence is never, by itself, sufficient (this module's own docstring).
    Falls back to "conditioned" - the closest fit in the existing
    AFFORDABLE_HOUSING_STATUSES vocabulary to "partially governed by a
    legal instrument, not fully" without inventing a new status (the
    amendment explicitly requires exhausting the existing vocabulary
    first). Leaves affordable_percentage/affordable_units/affordable_
    tenure_split/affordable_housing_notes untouched - the current TOTAL
    position (e.g. 50% / 73 units) may still legitimately stand; only its
    security LABEL is corrected."""
    if new_fields_raw.get("affordable_housing_status") != LEGALLY_SECURED_STATUS:
        return new_fields_raw

    model_says_fully_secured = new_fields_raw.get("affordable_provision_fully_legally_secured") is True
    evidence_suggests_mixed = _evidence_indicates_mixed_affordable_security(evidence_text)

    if model_says_fully_secured and not evidence_suggests_mixed:
        return new_fields_raw  # legitimate full-security case - Part 9 requirement

    guarded = dict(new_fields_raw)
    guarded["affordable_housing_status"] = MIXED_SECURITY_FALLBACK_STATUS
    return guarded


# PR B3 pre-historical-rebuild amendment (Defect B: refusal-reason
# reliability) - Phase 3's live Stockport DC/060928 sample showed an
# explicit, correctly-labelled refusal reason near the START of an 8,035-
# char decision_notice document was missed, despite being well within
# MAX_REFRESH_CONTEXT_CHARS. Root cause: build_combined_priority_text (the
# shared, unmodified extraction-pipeline text assembler - not reopened
# here) orders sections by ITS OWN PRIORITY_ORDER, which places
# decision_notice AFTER a much larger Planning Statement - the refusal
# wording isn't lost to truncation, but it is buried behind ~60,000 chars
# of lower-authority applicant-authored text before the model ever reaches
# it. Rather than reordering shared machinery other pipelines also depend
# on, this surfaces a small, clearly-labelled excerpt of the decision
# notice's own refusal-reason section directly in the refresh prompt, so
# it reaches the model prominently regardless of where it falls in the
# combined text.
_REFUSAL_REASON_PATTERNS = [
    re.compile(r"reasons?\s+for\s+refusal", re.IGNORECASE),
    re.compile(r"refused\s+for\s+the\s+following\s+reasons?", re.IGNORECASE),
    re.compile(r"following\s+reasons?\s*:", re.IGNORECASE),
]


def extract_refusal_reason_excerpt(documents: list[Document], max_chars: int = 2000) -> str | None:
    """Deterministic surfacing, not parsing, of a formal decision_notice's
    own refusal-reason section (Part 15 of the amendment: "reliable
    evidence surfacing, not replacing AI interpretation" - the LLM still
    produces the final normalized refusal_reasons output, this only makes
    sure it clearly sees the relevant excerpt). A small, fixed pattern
    list, not a portal-specific parser; returns None (no behaviour change)
    if no marker is found in any decision_notice document."""
    for document in documents:
        if document.doc_type != "decision_notice":
            continue
        text = document.extracted_text or ""
        for pattern in _REFUSAL_REASON_PATTERNS:
            match = pattern.search(text)
            if match:
                start = match.start()
                return text[start:start + max_chars].strip()
    return None


# --- Refresh outcome + change detection --------------------------------------


@dataclass
class RefreshOutcome:
    outcome: str
    affordable_housing_changes: list[str] = field(default_factory=list)
    depth: str = DEPTH_BROAD


def detect_affordable_housing_changes(old, new_fields: dict) -> list[str]:
    """Pure comparison (Part 13) between the CURRENTLY LIVE SchemeIntelligence
    (`old`, possibly None for a first-ever B3 pass) and the newly-generated
    replacement fields - never inspects raw document text itself, only the
    two structured positions, so it's exactly as trustworthy as its inputs
    and trivially unit-testable. Returns short machine-stable change
    descriptors (for [affordable-housing] observability logging and for
    Site Summary grounding), never free text - see this module's own
    _AFFORDABLE_CHANGE_LABELS below for the human-readable form."""
    changes: list[str] = []
    old_pct = getattr(old, "affordable_percentage_final", None) if old else None
    old_units = getattr(old, "affordable_units_final", None) if old else None
    old_tenure = getattr(old, "affordable_tenure_split_final", None) if old else None
    old_status = getattr(old, "affordable_housing_status", None) if old else None

    new_pct = new_fields.get("affordable_percentage_final")
    new_units = new_fields.get("affordable_units_final")
    new_tenure = new_fields.get("affordable_tenure_split_final")
    new_status = new_fields.get("affordable_housing_status")

    if new_pct is not None and old_pct is not None and new_pct != old_pct:
        changes.append("affordable_percentage_changed")
    if new_units is not None and old_units is not None and new_units != old_units:
        changes.append("affordable_unit_count_changed")
    if new_tenure and old_tenure and new_tenure != old_tenure:
        changes.append("tenure_split_changed")
    if new_tenure and not old_tenure:
        changes.append("tenure_split_newly_agreed")
    if new_status and old_status and new_status != old_status:
        if new_status == LEGALLY_SECURED_STATUS and old_status != LEGALLY_SECURED_STATUS:
            changes.append("tenure_split_legally_secured")
        else:
            changes.append("affordable_status_changed")
    return changes


# --- Prompt + schema ----------------------------------------------------------

REFRESH_SCHEMA = {
    "name": "planning_intelligence_refresh",
    "schema": {
        "type": "object",
        "properties": {
            "recommendation_direction": {"type": ["string", "null"], "enum": ["approval", "refusal", "unclear", None]},
            "formal_decision_outstanding": {"type": ["boolean", "null"]},
            "refusal_reasons": {"type": ["string", "null"]},
            "withdrawal_reason": {"type": ["string", "null"]},
            "affordable_percentage": {"type": ["number", "null"]},
            "affordable_units": {"type": ["integer", "null"]},
            "affordable_tenure_split": {"type": ["string", "null"]},
            "affordable_housing_status": {"type": "string", "enum": sorted(AFFORDABLE_HOUSING_STATUSES)},
            "affordable_housing_notes": {"type": ["string", "null"]},
            # PR B3 pre-historical-rebuild amendment (Defect A) - ephemeral
            # signal only, consumed by guard_mixed_legal_security_position
            # below and never persisted as its own SchemeIntelligence
            # column (Part 4 of the amendment: no new persisted fields).
            "affordable_provision_fully_legally_secured": {"type": ["boolean", "null"]},
            "planning_position_summary": {"type": "string"},
        },
        "required": [
            "recommendation_direction", "formal_decision_outstanding", "refusal_reasons", "withdrawal_reason",
            "affordable_percentage", "affordable_units", "affordable_tenure_split",
            "affordable_housing_status", "affordable_housing_notes",
            "affordable_provision_fully_legally_secured", "planning_position_summary",
        ],
        "additionalProperties": False,
    },
}


def _fmt_existing_position(intel) -> str:
    if intel is None:
        return "(no prior AI intelligence exists for this application yet)"
    return (
        f"total_units={intel.total_units_final} affordable_units={intel.affordable_units_final} "
        f"affordable_percentage={intel.affordable_percentage_final} "
        f"affordable_tenure_split={intel.affordable_tenure_split_final!r} "
        f"affordable_housing_status={intel.affordable_housing_status!r} "
        f"affordable_housing_notes={intel.affordable_housing_notes!r} "
        f"recommendation_direction={intel.recommendation_direction!r} "
        f"refusal_reasons={intel.refusal_reasons!r} withdrawal_reason={intel.withdrawal_reason!r}"
    )


def build_refresh_prompt(
    application: Application, depth: str, existing_intelligence, evidence_text: str,
    refusal_reason_excerpt: str | None = None,
) -> str:
    return f"""
You are updating UK residential planning intelligence for ONE application
after genuinely NEW evidence was acquired from the council portal. You are
NOT starting from scratch - you are told the CURRENTLY RECORDED position
below, and must produce an UPDATED position using only the NEW evidence
text also given below, changing only what the new evidence actually
supports changing.

APPLICATION: {application.reference} - {application.address or 'address not recorded'}
PORTAL STATUS: {application.status or 'unknown'} / DECISION: {application.decision or 'unknown'}
REFRESH FOCUS: {depth}

CURRENTLY RECORDED POSITION (do not discard this - only update fields the
new evidence below actually speaks to; leave anything else exactly as
recorded):
{_fmt_existing_position(existing_intelligence)}
{"" if not refusal_reason_excerpt else f'''
HIGHLIGHTED EXCERPT FROM THE FORMAL DECISION NOTICE (verbatim - this is the
part of the Decision Notice most likely to state the formal refusal
reason(s); treat it as strong, authoritative evidence for refusal_reasons,
but still corroborate it against the full evidence text below rather than
relying on it alone):
{refusal_reason_excerpt}
'''}
NEW EVIDENCE TEXT (this is the entire basis for any change you make):
{evidence_text or '(no readable evidence text was available this pass)'}

STRICT EVIDENCE-GROUNDING RULES - violating any of these makes your output
useless and actively harmful to a commercial user:
- Never guess a recommendation direction. Only set recommendation_direction
  to "approval" or "refusal" if the evidence text itself states a
  recommendation. If a recommendation exists but its direction is not
  stated, use "unclear". If no recommendation evidence exists at all,
  leave it as the currently recorded value (null if none).
- formal_decision_outstanding means ONLY whether a formal planning decision
  itself has yet to be issued/evidenced. It does NOT mean, and must never be
  set true or false based on, whether S106 has been executed, whether
  conditions remain outstanding, or whether the scheme is ready to
  implement - those are separate facts, represented elsewhere (affordable_
  housing_status/notes), never folded into this field.
  - If the evidence text itself contains a formal Decision Notice, Notice of
    Approval of Planning Permission, Notice of Refusal, or an equivalent
    formal determination document, set formal_decision_outstanding=false -
    even if the portal headline status above still says "Awaiting decision",
    even if the decision wording says "Granted, subject to legal agreement",
    and even if S106 execution is not evidenced anywhere. A formal decision
    having been issued and a legal agreement having been executed are two
    different facts; do not conflate them or let one imply the other.
  - If the only evidence is a recommendation (an officer/committee report
    recommending approval or refusal, with no formal Decision Notice/Notice
    of Approval/Notice of Refusal present), set formal_decision_outstanding=
    true - a recommendation is never itself a formal decision, however
    confident or final it reads.
  - If no evidence text contains a formal decision document and none
    contains a recommendation either, do not guess - leave formal_decision_
    outstanding as the currently recorded value above (null if none was
    ever recorded).
- Never invent refusal_reasons or withdrawal_reason. If the evidence does
  not state a reason, leave the field null - do not guess a plausible one.
- For a formally refused application, refusal_reasons is one of the
  HIGHEST-VALUE outputs of this whole refresh - never treat it as
  incidental. Actively look for explicit refusal wording ("Reason for
  Refusal", "Reasons for Refusal", numbered refusal reasons, or equivalent
  formal wording) within any Decision Notice text in the evidence below
  (see also the HIGHLIGHTED EXCERPT above, if present), and populate
  refusal_reasons with a concise, evidence-grounded summary of the stated
  reason(s) whenever such wording exists. A short, authoritative Decision
  Notice must never be overlooked just because a longer Officer Report or
  Planning Statement also appears in the evidence. Only leave refusal_
  reasons null if no formal reason wording exists anywhere in the
  evidence - never infer a reason merely from objections, consultation
  responses, or general policy commentary.
- Affordable housing: never describe a proposed or officer-recommended
  position as "legally_secured". Only use affordable_housing_status=
  "legally_secured" if the evidence text is an EXECUTED S106 agreement, a
  Deed of Variation, a Unilateral Undertaking, or another document that is
  itself the operative legal instrument - not a proposal, planning
  statement, committee report, or officer report describing what a future
  S106 will contain.
- MIXED LEGAL SECURITY: affordable_housing_status="legally_secured"
  describes the CURRENT TOTAL affordable position (affordable_percentage/
  affordable_units above), not just a portion of it. An executed S106,
  Deed of Variation, Unilateral Undertaking, or Decision Notice existing
  SOMEWHERE in the evidence does NOT by itself justify legally_secured for
  the whole total - only use it if that legal instrument secures the
  ENTIRE current total position. If the evidence distinguishes a legally-
  secured base amount from an ADDITIONAL amount delivered outside that
  legal mechanism (e.g. "non-S106", "outside the S106 agreement", "in
  addition to the S106 requirement"), the total position is MIXED and must
  NOT be labelled legally_secured - use "conditioned" instead, and set
  affordable_provision_fully_legally_secured=false. In that case, explain
  the split factually in affordable_housing_notes (e.g. "The executed S106
  secures the base 10% affordable housing requirement. The Affordable
  Housing Statement identifies a further 40% as non-S106 affordable
  housing, bringing the overall proposal to 50% / 73 homes."). Do NOT
  invent exact secured unit counts from arithmetic alone - e.g. do not
  state "15 homes are legally secured" merely because 10% of 147 is
  approximately 15, unless the legal instrument itself states that figure;
  it is sufficient and more accurate to describe the S106 as securing "the
  10% requirement" while separately stating the overall current total. Set
  affordable_provision_fully_legally_secured=true ONLY when the evidence
  shows the ENTIRE current total is secured by the same executed legal
  instrument with no separate additional non-secured component; never
  leave it null when affordable_housing_status is legally_secured.
- TENURE CONSISTENCY: affordable_tenure_split and affordable_housing_notes
  must describe ONE coherent current tenure position. If this pass's
  evidence clearly establishes a fuller or updated tenure picture (specific
  tenure categories/counts), update affordable_tenure_split to match what
  affordable_housing_notes says - never leave affordable_tenure_split as a
  stale prior value while affordable_housing_notes describes a different or
  more detailed tenure breakdown. If evidence is genuinely conflicting or
  too incomplete to update confidently, say so explicitly in affordable_
  housing_notes and leave affordable_tenure_split as currently recorded -
  never present a narrative tenure detail that contradicts the structured
  field.
- If the new evidence conflicts with an earlier proposal (e.g. the executed
  S106 secures a different % or tenure split than the applicant originally
  proposed), state that difference explicitly in affordable_housing_notes -
  do not silently overwrite it without saying so.
- If the new evidence does not mention affordable housing at all, leave
  affordable_percentage/affordable_units/affordable_tenure_split/
  affordable_housing_status/affordable_housing_notes as the currently
  recorded values (do not blank them out just because this pass's evidence
  happens not to mention them).
- affordable_housing_notes represents the CURRENT position, not a running
  transcript: state the current evidenced position plus, only where
  genuinely material, the single most relevant change from the CURRENTLY
  RECORDED POSITION above (e.g. "Affordable housing reduced from 35% to
  20%.", "The tenure split is now agreed at 60/40, previously unknown.",
  "The previously proposed 35% affordable provision is now legally secured
  through the executed S106."). Keep it to 1-3 sentences. Never append your
  new note onto the old one, never build a chronological log of every past
  observation, and never invent a "previous position" that the CURRENTLY
  RECORDED POSITION above does not actually show - if that position has no
  evidenced prior percentage/units/tenure/status, do not claim one existed.
- AFFORDABLE UNIT RECONCILIATION: if the affordable unit total is known
  (either from this pass's new evidence or the CURRENTLY RECORDED POSITION
  above) and affordable_housing_notes gives a specific unit/tenure
  breakdown, that breakdown must either (a) sum to the full known total, or
  (b) explicitly say the breakdown is partial and does not account for the
  full total - e.g. "60 affordable homes are proposed. The evidence
  identifies 21 social/affordable-rent houses and 21 shared-ownership
  houses; the available evidence in this refresh does not clearly allocate
  the remaining 18 affordable homes by tenure." Never state a partial
  breakdown in a way a reader would take as the complete picture, and never
  invent the missing units/tenures just to make the arithmetic reconcile.
- EVIDENCE AUTHORITY: the NEW EVIDENCE TEXT below is ordered from highest to
  lowest legal/evidential authority - an executed S106, Deed of Variation,
  Unilateral Undertaking, or Decision Notice outranks an officer/committee
  report, which outranks an applicant's own planning/affordable housing
  statement. If the CURRENTLY RECORDED POSITION above already shows
  affordable_housing_status="legally_secured" and the new evidence you were
  given contains NO executed S106/Deed of Variation/Unilateral Undertaking/
  Decision Notice text, you MUST leave affordable_percentage/
  affordable_units/affordable_tenure_split/affordable_housing_status
  exactly as currently recorded - a lower-authority document (a later
  marketing statement, an earlier-stage planning statement, etc.) can never
  downgrade or contradict an already-secured legal position, and must not
  be described as doing so in affordable_housing_notes either.
- planning_position_summary: one or two factual sentences stating the
  current planning position given everything above - this feeds directly
  into a commercial Site Summary, so state facts plainly and never imply a
  legal position that isn't evidenced.
"""


# --- Atomic replacement orchestration ---------------------------------------


def _call_refresh_llm(client: OpenAI, prompt: str) -> dict:
    response = client.responses.create(
        model=MODEL, input=prompt,
        text={"format": {"type": "json_schema", "name": REFRESH_SCHEMA["name"], "schema": REFRESH_SCHEMA["schema"], "strict": True}},
    )
    return json.loads(response.output_text)


def refresh_intelligence_for_application(
    session, client: OpenAI, application: Application, *,
    generate_summary=None, extra_fields: dict | None = None,
) -> RefreshOutcome:
    """The B3 atomic-replacement entry point (PR B3 spec, Part 27) - ONE
    Application whose Application.material_evidence_changed_at is newer
    than its own intelligence_evidence_processed_at watermark (see app.
    pipeline.run_weekly.INTELLIGENCE_REFRESH_ELIGIBLE, the only caller
    that should ever select candidates for this).

    Sequence: resolve the same bounded family B2 itself uses -> select
    evidence documents for the reason-derived depth -> call the LLM once ->
    on SUCCESS, mutate the existing SchemeIntelligence ORM object in place
    (never delete+recreate) and regenerate the linked Site's status summary
    via `generate_summary` (injected so tests never need a live OpenAI
    Site-Summary call too) -> only if BOTH succeed, commit everything in one
    transaction and advance the watermark to the exact material_evidence_
    changed_at value just incorporated.

    ATOMICITY: no assignment to the live SchemeIntelligence/Site/Application
    ORM objects happens until the LLM call AND (if a Site is linked) the
    Site Summary regeneration have BOTH already succeeded - see the ordering
    below. If either raises, this function returns before touching the
    session at all, so a subsequent session.commit() anywhere else in the
    caller cannot accidentally persist a partial change - `intelligence.
    field = x` lines only ever execute after every fallible step has already
    returned successfully.

    generate_summary(site, applications) -> str | None - injected callable
    for Site Summary regeneration (defaults to app.reporting.scheme_summary.
    generate_scheme_summary via the real OpenAI client if not given);
    returning/raising lets a test simulate summary failure independently of
    the intelligence-refresh LLM call.

    extra_fields: dict | None - opt-in mechanism (B3 pre-historical-rebuild
    final amendment, Issue A) for a CALLER-SPECIFIC completion marker to be
    persisted in the exact SAME commit as the SchemeIntelligence/Site
    Summary/watermark replacement, with no second transaction and no
    crash window between "intelligence rebuilt" and "marker recorded".
    This function applies the given key/value pairs to the SAME
    `existing_intelligence` ORM object as a plain setattr, at the same
    point in the sequence as its own new_fields assignment (i.e. only
    after BOTH fallible steps - the LLM call and, if a Site is linked, the
    Site Summary regeneration - have already succeeded) - never earlier,
    so a failure anywhere before that point leaves extra_fields completely
    unapplied, exactly like every other field this function sets. B3
    itself never passes this (normal scheduled processing always omits
    it, so it defaults to None and this whole mechanism is a no-op for
    every existing caller) - it exists solely so a caller like
    app.extraction.historical_rebuild can atomically record its own
    intelligence_rebuild_version/intelligence_rebuilt_at without this
    function needing to know what those fields mean or why they exist.
    Deliberately generic (not named/typed around "historical rebuild") so
    this stays a small, caller-agnostic seam rather than a second,
    rebuild-specific code path inside B3 itself.

    Reuses app.extraction.run_extraction's own OUTCOME_* taxonomy - no
    second AI failure system (Part 28). NO_USABLE_TEXT here means no
    evidence document text was available for the depth-relevant categories
    this pass - it does NOT destroy the existing intelligence (Part 28's own
    explicit warning), it simply leaves everything untouched and remains
    retryable on the next pass (e.g. once B2 actually acquires readable
    text for a category that currently has none)."""
    if generate_summary is None:
        from app.reporting.scheme_summary import generate_scheme_summary as _default_generate_summary

        def generate_summary(site, applications):  # noqa: F811
            from app.pipeline.lapse_tracking import compute_lapse_status
            from app.pipeline.phase_tracking import build_phase_breakdown
            from app.ui.common import aggregate_scheme_fields

            # `new_fields` is a free variable resolved from the enclosing
            # refresh_intelligence_for_application scope at CALL time, not
            # definition time - by the time this closure actually runs (see
            # the `generate_summary(site, site.applications)` call below),
            # new_fields already holds this pass's prospective replacement
            # values, so the Site Summary can see them WITHOUT the real
            # `application.scheme_intelligence` ORM object being mutated
            # yet (Defect A / live-validation amendment Part 2-4) - atomicity
            # is preserved because this is a transient dict passed alongside
            # the still-untouched real applications, never a write to them.
            merged = aggregate_scheme_fields(applications, prospective_overrides={application.id: new_fields})
            lapse = compute_lapse_status(applications, site)
            phase_breakdown = build_phase_breakdown(applications)
            return _default_generate_summary(client, site, applications, merged, lapse, phase_breakdown)

    family = resolve_application_family(session, application)
    reasons = tuple(
        part for part in (application.evidence_refresh_reason or "").split(",") if part
    )
    depth = refresh_depth_for_reasons(reasons)

    documents = select_refresh_evidence_documents(family, depth)
    if not documents:
        return RefreshOutcome(outcome=OUTCOME_NO_USABLE_TEXT, depth=depth)

    doc_tuples = [(d.doc_type, d.document_name or "", d.extracted_text or "") for d in documents]
    evidence_text = build_combined_priority_text(doc_tuples, max_total_chars=MAX_REFRESH_CONTEXT_CHARS)
    if not evidence_text:
        return RefreshOutcome(outcome=OUTCOME_NO_USABLE_TEXT, depth=depth)

    existing_intelligence = application.scheme_intelligence
    refusal_reason_excerpt = extract_refusal_reason_excerpt(documents)
    prompt = build_refresh_prompt(
        application, depth, existing_intelligence, evidence_text,
        refusal_reason_excerpt=refusal_reason_excerpt,
    )

    try:
        new_fields_raw = _call_refresh_llm(client, prompt)
    except OpenAIError:
        return RefreshOutcome(outcome=OUTCOME_AI_ERROR, depth=depth)
    except (json.JSONDecodeError, KeyError, ValueError):
        return RefreshOutcome(outcome=OUTCOME_INVALID_OUTPUT, depth=depth)
    except Exception:
        return RefreshOutcome(outcome=OUTCOME_ERROR, depth=depth)

    if not isinstance(new_fields_raw, dict) or "affordable_housing_status" not in new_fields_raw:
        return RefreshOutcome(outcome=OUTCOME_INVALID_OUTPUT, depth=depth)
    if new_fields_raw["affordable_housing_status"] not in AFFORDABLE_HOUSING_STATUSES:
        return RefreshOutcome(outcome=OUTCOME_INVALID_OUTPUT, depth=depth)

    # Deterministic evidence-authority backstop (PR B3 FINAL amendment,
    # Part 10) - build_refresh_prompt's own instructions already ask the
    # model to preserve an already-secured position against lower-authority
    # evidence; this is the code-level guarantee that holds even if the
    # model doesn't comply.
    new_fields_raw = guard_legally_secured_position(existing_intelligence, new_fields_raw, documents)

    # Deterministic mixed-security backstop (pre-historical-rebuild
    # amendment, Defect A) - the UPWARD counterpart to the guard above: an
    # authoritative legal document existing somewhere in the evidence must
    # never, by itself, promote the entire current affordable total to
    # legally_secured when the evidence itself describes a mixed position.
    new_fields_raw = guard_mixed_legal_security_position(new_fields_raw, evidence_text)

    # Map the LLM's own field names onto SchemeIntelligence's existing
    # reconciled-field names (affordable_percentage -> affordable_
    # percentage_final etc.) - reusing those columns rather than adding
    # parallel ones (Part 22: "prefer existing fields where fit-for-
    # purpose"). A null in the LLM response means "no new evidence spoke to
    # this", so the CURRENT value is preserved, not blanked.
    new_fields = {
        "recommendation_direction": new_fields_raw.get("recommendation_direction")
        or (existing_intelligence.recommendation_direction if existing_intelligence else None),
        "formal_decision_outstanding": (
            new_fields_raw["formal_decision_outstanding"]
            if new_fields_raw.get("formal_decision_outstanding") is not None
            else (existing_intelligence.formal_decision_outstanding if existing_intelligence else None)
        ),
        "refusal_reasons": new_fields_raw.get("refusal_reasons")
        or (existing_intelligence.refusal_reasons if existing_intelligence else None),
        "withdrawal_reason": new_fields_raw.get("withdrawal_reason")
        or (existing_intelligence.withdrawal_reason if existing_intelligence else None),
        "affordable_percentage_final": (
            new_fields_raw["affordable_percentage"]
            if new_fields_raw.get("affordable_percentage") is not None
            else (existing_intelligence.affordable_percentage_final if existing_intelligence else None)
        ),
        "affordable_units_final": (
            new_fields_raw["affordable_units"]
            if new_fields_raw.get("affordable_units") is not None
            else (existing_intelligence.affordable_units_final if existing_intelligence else None)
        ),
        "affordable_tenure_split_final": new_fields_raw.get("affordable_tenure_split")
        or (existing_intelligence.affordable_tenure_split_final if existing_intelligence else None),
        "affordable_housing_status": new_fields_raw["affordable_housing_status"],
        "affordable_housing_notes": new_fields_raw.get("affordable_housing_notes")
        or (existing_intelligence.affordable_housing_notes if existing_intelligence else None),
        "latest_material_event": application.evidence_refresh_reason,
    }

    changes = detect_affordable_housing_changes(existing_intelligence, new_fields)

    # Site Summary regeneration - the second required-to-succeed step
    # (Part 27, steps 6-7) BEFORE anything is committed. Deliberately
    # AFTER the intelligence LLM call succeeds but BEFORE any ORM
    # mutation, so a summary failure here still leaves the live
    # SchemeIntelligence row completely unmutated in memory, not merely
    # uncommitted (belt-and-braces against a stray earlier commit
    # elsewhere in a long-lived session).
    site: Site | None = application.site
    generated_summary: str | None = None
    if site is not None:
        try:
            generated_summary = generate_summary(site, site.applications)
        except Exception:
            return RefreshOutcome(outcome=OUTCOME_ERROR, depth=depth, affordable_housing_changes=changes)
        if not generated_summary or not generated_summary.strip():
            return RefreshOutcome(outcome=OUTCOME_INVALID_OUTPUT, depth=depth, affordable_housing_changes=changes)

    # Both fallible steps succeeded - commit the atomic replacement.
    if existing_intelligence is None:
        from app.db.models import SchemeIntelligence

        existing_intelligence = SchemeIntelligence(application_id=application.id)
        # Sets the ORM relationship itself (back_populates="scheme_
        # intelligence"), not just the raw application_id FK - required so
        # application.scheme_intelligence reflects the new row immediately
        # for THIS SAME in-memory application object, without relying on a
        # later expire/refetch. A plain session.add(...) with only
        # application_id set would leave application.scheme_intelligence
        # stale (still None) for the rest of this process/test if that
        # relationship was already lazily read earlier in this same call.
        application.scheme_intelligence = existing_intelligence
        session.add(existing_intelligence)
    for key, value in new_fields.items():
        setattr(existing_intelligence, key, value)

    if extra_fields:
        for key, value in extra_fields.items():
            setattr(existing_intelligence, key, value)

    if site is not None and generated_summary is not None:
        site.status_summary = generated_summary
        site.status_summary_updated_at = dt.datetime.now(dt.timezone.utc)

    application.intelligence_evidence_processed_at = application.material_evidence_changed_at
    session.commit()

    for change in changes:
        print(f"[affordable-housing] application={application.reference} change={change}")
    print(
        f"[intelligence-refresh] application={application.reference} depth={depth} "
        f"reason={application.evidence_refresh_reason or 'none'} outcome=success"
    )
    return RefreshOutcome(outcome=OUTCOME_SUCCESS, depth=depth, affordable_housing_changes=changes)
