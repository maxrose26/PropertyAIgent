"""Agent Evaluation Policy V1 - Terminal Hard Exclusion Policy V1 (narrow
implementation slice; Product Owner-approved refinement of the Design &
Production Calibration report's original "BuyerFit==NOT_SUITABLE ->
automatically NOT_RELEVANT" proposal).

CORE ARCHITECTURE DECISION (Product Owner correction): NOT_SUITABLE does NOT
automatically become NOT_RELEVANT. Only a specific, explicit, versioned
ALLOWLIST of BuyerFit `does_not_match` reasons may deterministically short-
circuit the LLM call - every other does_not_match reason (a "non-terminal"
NOT_SUITABLE) is passed to the LLM as strong screening context instead,
never silently treated as a new deterministic rejection. This is what
prevents a FUTURE change to app.policy.buyer_matching.assess_buyer_fit
(a new does_not_match reason nobody has added to this allowlist yet) from
silently creating new deterministic rejection behaviour - an un-recognised
does_not_match reason is always routed to the LLM, never blindly trusted
or blindly ignored.

HOW THE ALLOWLIST WAS BUILT: app.policy.buyer_matching.assess_buyer_fit has
exactly five call sites that ever append to `does_not_match` (confirmed by
direct inspection of that module's own source, not guessed) - each produces
one of a small, fixed set of f-string TEMPLATES whose LITERAL (non-
interpolated) text is stable and already exercised by that module's own
test suite. Every marker below is copied verbatim from that source, not
approximated.

STRATEGIC_LAND_CONTROL "confirmed underway" SAFETY (Product Owner Section 5
of the narrow-implementation authorisation): the one reason genuinely
involving development-activity-vs-scope ("...fundamentally incompatible
with this buyer's strategic-land-control acquisition strategy") is INCLUDED
in the terminal allowlist, but only because assess_buyer_fit's own code
ALREADY gates it on `context.development_state_scope_verified` being True
before ever appending it (see that function's own "Phase B2 narrow
remediation (Issue B)" comment, and the exact `if confirmed_underway_or_
further and context.development_state_scope_verified:` guard) - by the time
this specific reason text exists at all, the deterministic layer has
already proven the acquisition subject and the underway evidence share the
same scope. Development activity that is NOT scope-verified never reaches
`does_not_match` in the first place (it is routed to `investigate`/`unknown`
instead) - there is no unsafe path into this marker.

Confirmed exhaustive against the CURRENT codebase: every does_not_match
reason assess_buyer_fit can produce today matches one of these six markers.
This is expected to remain true, not by construction but because no other
does_not_match.append() call site currently exists - re-verified by this
module's own test suite, which will fail loudly if assess_buyer_fit grows a
new one that isn't listed here (a genuine, deliberate signal to update this
allowlist, never a silent gap)."""
from __future__ import annotations

from dataclasses import dataclass

TERMINAL_HARD_EXCLUSION_POLICY_VERSION = 1

CONFIRMED_SPECIALIST_USE_EXCLUSION = "CONFIRMED_SPECIALIST_USE_EXCLUSION"
CONFIRMED_WHOLLY_AFFORDABLE_EXCLUSION = "CONFIRMED_WHOLLY_AFFORDABLE_EXCLUSION"
CONFIRMED_GEOGRAPHY_EXCLUSION = "CONFIRMED_GEOGRAPHY_EXCLUSION"
CONFIRMED_BELOW_MINIMUM_SCALE_EXCLUSION = "CONFIRMED_BELOW_MINIMUM_SCALE_EXCLUSION"
CONFIRMED_STRATEGIC_LAND_CONTROL_UNDERWAY_AT_VERIFIED_SCOPE = "CONFIRMED_STRATEGIC_LAND_CONTROL_UNDERWAY_AT_VERIFIED_SCOPE"
CONFIRMED_ZERO_AFFORDABLE_PACKAGE = "CONFIRMED_ZERO_AFFORDABLE_PACKAGE"

TERMINAL_EXCLUSION_REASONS = frozenset({
    CONFIRMED_SPECIALIST_USE_EXCLUSION,
    CONFIRMED_WHOLLY_AFFORDABLE_EXCLUSION,
    CONFIRMED_GEOGRAPHY_EXCLUSION,
    CONFIRMED_BELOW_MINIMUM_SCALE_EXCLUSION,
    CONFIRMED_STRATEGIC_LAND_CONTROL_UNDERWAY_AT_VERIFIED_SCOPE,
    CONFIRMED_ZERO_AFFORDABLE_PACKAGE,
})

# (literal substring copied verbatim from app.policy.buyer_matching's own
# does_not_match.append() call sites, terminal reason code). Order matters
# only in that CONFIRMED_ZERO_AFFORDABLE_PACKAGE's marker must be checked
# before a hypothetical broader affordable-related marker, if one is ever
# added - not currently ambiguous, since the two existing affordable-shaped
# markers ("wholly affordable" vs "zero affordable package") use disjoint
# literal text.
_TERMINAL_MARKERS: tuple[tuple[str, str], ...] = (
    ("not the general-needs residential development this buyer requires.", CONFIRMED_SPECIALIST_USE_EXCLUSION),
    ("not open-market residential development.", CONFIRMED_WHOLLY_AFFORDABLE_EXCLUSION),
    ("is outside this buyer's explicit geographic boundary (", CONFIRMED_GEOGRAPHY_EXCLUSION),
    ("below this buyer's minimum requirement of", CONFIRMED_BELOW_MINIMUM_SCALE_EXCLUSION),
    (
        "which is fundamentally incompatible with this buyer's strategic-land-control acquisition strategy.",
        CONFIRMED_STRATEGIC_LAND_CONTROL_UNDERWAY_AT_VERIFIED_SCOPE,
    ),
    ("incompatible with this buyer's affordable-housing-package acquisition strategy.", CONFIRMED_ZERO_AFFORDABLE_PACKAGE),
)


@dataclass(frozen=True)
class TerminalExclusionResult:
    """is_terminal=True means at least one does_not_match reason matched a
    terminal marker - EVALUATE() must short-circuit to a deterministic
    NOT_RELEVANT without ever calling the LLM (Section 4/21 of the narrow-
    implementation authorisation). terminal_reasons/terminal_texts are the
    matched reason code(s) and their exact original text, for citation in
    the deterministic result. non_terminal_texts are does_not_match entries
    (if any) that did NOT match a known marker - these must still be passed
    to the LLM as strong screening context (never silently dropped, never
    silently trusted as terminal)."""

    is_terminal: bool
    terminal_reasons: tuple[str, ...]
    terminal_texts: tuple[str, ...]
    non_terminal_texts: tuple[str, ...]


def classify_terminal_exclusion(does_not_match: list[str] | tuple[str, ...]) -> TerminalExclusionResult:
    """Pure function over BuyerFitAssessment.does_not_match - never calls
    assess_buyer_fit itself, never reads context/facts directly. An empty
    does_not_match list (BuyerFit is not NOT_SUITABLE at all) correctly
    returns is_terminal=False with everything empty."""
    terminal_reasons: list[str] = []
    terminal_texts: list[str] = []
    non_terminal_texts: list[str] = []

    for reason_text in does_not_match:
        matched_code = None
        for marker, code in _TERMINAL_MARKERS:
            if marker in reason_text:
                matched_code = code
                break
        if matched_code is not None:
            terminal_reasons.append(matched_code)
            terminal_texts.append(reason_text)
        else:
            non_terminal_texts.append(reason_text)

    return TerminalExclusionResult(
        is_terminal=bool(terminal_reasons),
        terminal_reasons=tuple(terminal_reasons),
        terminal_texts=tuple(terminal_texts),
        non_terminal_texts=tuple(non_terminal_texts),
    )
