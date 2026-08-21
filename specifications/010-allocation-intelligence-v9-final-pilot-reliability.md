# Allocation Intelligence V9 Final Pilot Reliability Hardening

## Objective

The completed platform-wide V8 production run left 208/263 (79.1%) eligible allocations with a valid summary (100 under v8, 108 retained from v7) and 55 in error. This spec fixes the two mechanical causes behind the large majority of those 55, investigates the remainder individually per instruction, and is intended to close the Allocation Intelligence summary reliability-hardening cycle for the pilot.

## Production Baseline

287 total allocations, 263 eligible, 24 insufficient context. 208 successful (100 v8 / 108 v7), 55 errors. Primary error taxonomy: `empty_application_reference` 35, `unsupported_numbers` 17, `entity_role_scope_claim` 2, `entity_wrong_application_reference` 1.

## Fix A — Untargeted Absence Claims Now Inert

Root cause, reproduced exactly against real allocation 193's trusted context: V8's `_is_inert_application_entry` treated any non-`"none"` `decision_claim_mode` as automatically material. A model narrating the no-linked-Application principle ("no linked planning application has been identified, so no decision has been recorded") naturally wants to add the second clause as a companion fact, and with no real Application to attach it to, sets `decision_claim_mode="absent"` on an entry whose `reference`/`claimed_status`/`claimed_decision` are all still blank - this fell through to `"unsupported application reference: "`, reproduced byte-for-byte against the real row.

Widened boundary: an entry with blank `reference`/`claimed_status`/`claimed_decision` is now inert for `decision_claim_mode` in `{"none", "absent"}` - an untargeted "absent" claim names no Application, so it is not checkable against anything, structurally equivalent to no claim at all. `decision_claim_mode="value"` is **never** inert, even with blank text fields - "value" itself asserts a concrete decision was stated. A blank reference still cannot smuggle a real `claimed_status`, non-empty `claimed_decision`, or `"value"`-mode claim past grounding.

## Fix B — Trusted Compound-Label Substring Masking

`_trusted_label_substrings` previously only masked the WHOLE literal label string (plus a parenthetical's own bracketed content). Real production proved this too brittle for multi-part labels:
- **Address-shaped `allocation_name`** (e.g. "499 Chester Road, Old Trafford") - a model narrating only the street portion, without repeating the suburb, was unmasked. Fixed via comma-segment splitting (each segment, and cumulative prefixes, independently maskable).
- **`local_plan_name` with its own trailing parenthetical** (e.g. "Wigan Borough Local Plan: Planning for the Future to 2040 (Initial Draft)") - a model narrating "...to 2040" without repeating "(Initial Draft)" was unmasked; the paren-stripped prefix was never actually implemented despite the function's own docstring claiming it was. Now genuinely masked.
- **`local_plan_name` itself** was never in the masked-label set at all (only `allocation_reference`/`plan_status_label`) - added, alongside `allocation_name`.
- **`allocation_capacity_display`'s own range lower bound** (e.g. "8,400-15,000 homes" - `allocation_capacity_value` only ever reports the upper bound) - added to `_allowed_numbers` directly (a numeric-allowlist addition, not string masking, since this is a genuine quantity already rendered verbatim, not a name).

All 17 of the V8 audit's `unsupported_numbers` rejections were individually investigated against real production context and traced to one of these three sources - none were genuine hallucinations.

## Numerical Safety Guarantees (unchanged)

An invented number sharing no relationship to any trusted string or figure remains rejected - verified directly (`test_g`, and re-confirmed against a real address-named allocation). AI-derived arithmetic (e.g. "83" from `100% − 17%`) remains rejected - re-verified after V9. No numeric allow-list was introduced; every fix is either string-masking of a genuinely-present trusted label, or addition of a genuinely-present trusted figure already rendered verbatim.

## Party-Evidence Investigation (not fixed - per instruction)

- **Allocation 26 (Jenny Lane / Richborough)**: real evidence exists (`Richborough`, Applicant, `DC/099650`) - rejected because the model's self-reported `site_scope` used single quotes (`Site 'Land At Jenny Lane Woodford'`) against the trusted double-quoted form (`Site "Land At Jenny Lane Woodford"`) - an exact-string scope-formatting mismatch, not a hallucination. Not fixed (narrow, cosmetic, out of this task's scope).
- **Allocation 65 (Hazelhurst Farm)**: confirmed compound raw portal value (`Application.applicant_name_raw = "Story Homes Ltd and Taylor Wimpey"`, one string) - the model split it into two separate entities, neither matching exactly. Confirmed as the already-known compound-applicant-name limitation. Not fixed, per explicit instruction against introducing fuzzy/company-name-splitting resolution.
- **Allocation 66 (East of Boothstown / Annabel Baker)**: confirmed the model conflated two real, distinct, exact-string entities ("Annabel Baker" evidenced via `23/81742/HYBEIA`, "Ms Annabel Baker" evidenced via `PA/2024/0749`), attributing the wrong entity's reference. The already-known title-variant duplicate-name limitation. Not fixed, per instruction that exact-string dedup remains acceptable for the pilot.

## Unchanged Grounding Guarantees

Party-role semantics (Applicant≠Developer/Owner/Promoter), Site-scope validation, specific-Application attribution, `needs_confirmation`/`rejected` trust boundaries, and failure-preserves-last-valid-summary behaviour are all unchanged and re-tested (tests `h` through `o`).

## Tests

15 new tests added, covering the exact reproduced V8 production failure shape (Fix A), four distinct real address formats plus a `local_plan_name`-with-year and a range-capacity fixture (Fix B), and explicit re-assertions of every unchanged safety guarantee. Full suite: 2508 passed (2493 prior baseline).

## Estimated Production Impact

Not a guarantee. Fix A mechanically addresses the `empty_application_reference` family where the untargeted-absent shape applies (up to 35 primary + related occurrences, pending how many of the real remaining rows share this exact shape rather than a genuine material claim). Fix B mechanically addresses all 17 `unsupported_numbers` rejections investigated. The 3 party-evidence and 2 `entity_role_scope_claim`/`entity_wrong_application_reference` rejections are NOT expected to be resolved by this amendment (deliberately left as known, accepted pilot limitations). Conservative expected post-retry coverage: roughly 245-252 of 263 (93-96%), leaving a small, understood, deliberately-unaddressed remainder.

## Prompt Version

**Remains `allocation-intelligence-summary-v8`.** Every V9 change is confined to post-generation validation logic (`_is_inert_application_entry`, `_trusted_label_substrings`, `_allowed_numbers`) - `build_summary_prompt`'s text and `SUMMARY_SCHEMA` are byte-for-byte unchanged, so the model receives an identical prompt and would produce identical output; only what the validator now correctly recognises as grounded has changed. Not bumping avoids marking the 208 already-successful summaries stale.

## Recommended Controlled Retry

Because `PROMPT_VERSION` is unchanged, `--stale` targeting would (correctly, but unnecessarily) also re-flag the 108 v7-successful rows as stale (their own `prompt_version` already differs from the current `"v8"`, independent of this amendment). To retry only the current failed population without touching those, target the exact 55 current error-row allocation ids explicitly via the existing `--allocation-ids` flag - the same safe, already-proven mechanism used throughout this project's prior controlled retries:

```
python -m scripts.generate_allocation_intelligence_summaries --allocation-ids <55 ids> --execute --confirm YES-GENERATE-ALLOCATION-INTELLIGENCE-SUMMARIES
```

## Remaining Known Limitations (deferred, not fixed)

- Compound/joint applicant names remain unresolved (one raw portal string naming two companies splits incorrectly).
- Title-variant duplicate applicant names (e.g. "Annabel Baker" / "Ms Annabel Baker") remain two separate exact-string entities.
- Self-reported `site_scope` quote-style variance (single vs double quotes) can cause a cosmetic mismatch against an otherwise-correct claim.
- The generation-attempt-history limitation (a failed attempt's own prompt_version is never persisted) remains, as previously documented and deliberately deferred.

## Closure Statement

This is intended as the final Allocation Intelligence summary reliability-hardening cycle for the pilot. The remaining known limitations above are accepted, understood, and explicitly not pursued further absent a genuine new architecture defect.
