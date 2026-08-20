# Allocation Intelligence Grounding Hardening (Trusted Sub-Phrases + Null Decision Claims)

## Objective

The first real controlled production run of AI Allocation Intelligence Summary v5 (allocations 51/32/66/196) succeeded for one allocation and correctly rejected the other three's genuinely ungrounded output - but two of those three rejections turned out to be validator representation gaps, not real hallucinations. This spec closes those two specific gaps without weakening the validator's protection against genuine invention.

## Business Value

Two real, commercially-useful, fully-grounded AI narrations (Heald Green West's plan stage, East of Boothstown's pending decision) were being discarded by the validator, silently reducing Allocation Intelligence's usefulness exactly where it should have been strongest. Fixing the representation, not the protection, restores that value without opening any new hallucination surface.

## Requirements

- **Trusted-label sub-phrase masking**: `context.allocation_reference`/`context.plan_status_label` are masked as whole strings (existing behaviour) AND, for any parenthetical qualifier they contain (e.g. `"Draft consultation (Regulation 18)"`), the bracketed content on its own (`"Regulation 18"`) is also masked - via a new, generic `_trusted_label_substrings` helper, not a hardcoded exception for `"18"`/`"2.33"`. Generalises to any future label of the same `"<phase> (<qualifier>)"` shape.
- **Explicit null/absence decision claims**: `referenced_applications` items gain `decision_claim_mode: "none" | "value" | "absent"`. `"absent"` is accepted only when the trusted `RepresentativeApplicationDetail.decision` is genuinely falsy; a decided Application (`Granted`/`Refused`/`Withdrawn`/etc.) can never be described as undecided. The model's own prose wording for the absence claim is never checked against a fixed phrase list.
- Backward compatibility: an omitted `decision_claim_mode` (every real v4/v5 generation, every pre-v6 test) is inferred exactly as the pre-v6 validator behaved - `"value"` when `claimed_decision` is non-empty, `"none"` otherwise. No existing behaviour changes for legacy self-reports.
- `PROMPT_VERSION` bumped to v6 (v5 was genuinely deployed and used for a real successful generation - allocation 51 - so this is not a no-op bump).

## Non-Requirements

- No hardcoded numeric exceptions for `18`, `17`, or `32`.
- No weakening of numeric grounding generally - a companion test proves an unrelated invented number is still rejected after the masking change.
- No change to `claimed_status`'s semantics - only `claimed_decision`/`decision_claim_mode` were touched, since no null-status representation gap was found in real production data.
- No database schema change, no migration.
- Allocation 196's rejection (`"unsupported numbers: 17, 32"`) is diagnosed as a genuine, correctly-rejected hallucination (17+32 sums exactly to `identified_application_capacity`=49, and this allocation has only one linked Application - no basis for any two-way split) - **not** something this amendment fixes. A companion test proves the fabricated split is still rejected.

## Data Model

No schema/migration. `SUMMARY_SCHEMA`'s `referenced_applications` items gain one new required string-enum field, `decision_claim_mode`. No new dataclass fields.

## Architecture Considerations

Root causes were confirmed against real production `AllocationIntelligenceContext` objects (read-only), not assumed:
- Allocation 32: the whole-string mask added by the prior Party Evidence amendment covers `context.plan_status_label`'s FULL literal value; a real generation narrated only its parenthetical qualifier ("Regulation 18"), which never matches the whole-string mask.
- Allocation 66: `claimed_decision=""` was ambiguous between "no claim" and "explicit absence claim"; the model's genuine absence prose ("no decision recorded yet") had no structured field to land in other than the free-text-checked `claimed_decision`.
- Allocation 196: verified, not assumed, to be a genuine hallucination (a fabricated split of the single identified-capacity figure into two invented parts) - confirmed unchanged/still-rejected after this amendment via direct validation against the real production context.

## Acceptance Criteria

- Real production contexts for allocations 32 and 66, re-validated with a self-report matching the real rejection's shape, now pass (confirmed directly against live production, read-only, zero writes).
- The same real production context for allocation 196, given a fabricated capacity split, is still rejected.
- Full test suite passes with zero failures (2441/2441 at implementation time, up from a 2427 pre-this-spec baseline).

## Future Enhancements

None identified - this is a narrow, closed hardening fix.
