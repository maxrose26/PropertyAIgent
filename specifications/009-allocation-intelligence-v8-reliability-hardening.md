# Allocation Intelligence V8 Reliability Hardening

## Objective

A read-only audit of the first platform-wide V7 production run (287 allocations, 161 successful, 102 rejected) found the underlying evidence-grounding architecture sound, but three narrow representation/normalisation defects causing the large majority of false rejections. This spec fixes exactly those three, without weakening any material-fact grounding check.

## Production Problem

161/263 eligible allocations (61.2%) had a valid V7 summary. Of 102 rejections, the audit found:
- **72 (71%)**: an all-blank self-report entry (`application_reference: ""` or entity `name: ""`) read by the validator as a claimed-but-unsupported reference/entity, when it actually meant "nothing to report".
- **9 of 25 "unsupported numbers"**: a trusted plan-stage label ("Regulation 18") masked only in its exact original case; a model writing "regulation 18" mid-sentence was not masked.
- **≥1 confirmed**: `Application.decision` containing the real portal placeholder `"Not Available"`, treated as a genuine decision value, rejecting an otherwise-correct "no decision recorded" claim.

## Product Principle (unchanged, reinforced)

No linked planning Application is a valid, potentially commercially important intelligence state. Absence of identified evidence on this platform must never be upgraded into a real-world claim of non-existence, unavailability, or lack of interest - only ever an investigation signal. This task changes representation, never that principle.

## Fix A — Inert Empty Self-Report Entries

`_is_inert_application_entry`/`_is_inert_entity_entry` (`app/reporting/allocation_intelligence_summary.py`): an entry is inert **only** when it carries zero material claims - for `referenced_applications`, empty `reference` AND empty `claimed_status` AND empty `claimed_decision` AND `decision_claim_mode` not `"value"`/`"absent"`; for `referenced_entities`, empty `name` AND `role` AND `site_scope` AND `application_reference`. Inert entries are skipped before validation, semantically identical to omitting them. The moment any field carries a real claim, full grounding applies unchanged - an empty reference can never be paired with a real status/decision claim "for free" (still rejected, since there is no representative Application for `""` to ground against). Rule 17 added to the prompt, telling the model directly that `[]` is the correct self-report when nothing was named.

## Fix B — Case-Insensitive Trusted-Label Masking

`_mask_known_strings_case_insensitive` (new): masks trusted **label** substrings (`context.allocation_reference`, `context.plan_status_label` and their parenthetical sub-phrases) case-insensitively. Application references and entity names remain masked exact-case via the existing `_mask_known_strings` - a reference or company name's case is part of its identity; a natural-language label's is not. An invented label ("Regulation 25") was never a trusted substring in any case, so it remains rejected.

## Fix C — Placeholder Decision Normalisation

`_clean_portal_value` (generalised and renamed from `_clean_applicant_name`, now shared): `RepresentativeApplicationDetail.decision` is cleaned through the same portal-placeholder vocabulary applicant names already used. Verified against a full query of every distinct real production `Application.decision` value: `"Not Available"` is the only placeholder-shaped value among 60+ genuine outcomes (Approve, Granted, Refuse, Withdrawn, Split, etc. are all real). `status` was investigated for the same phenomenon and deliberately left unchanged - a genuine `"Unknown"` status value exists in production, but `claimed_status` grounding is a plain exact-match with no "absent" mode, and the audit found zero rejections attributable to it.

## Unchanged Grounding Guarantees

Numerical grounding, Application-reference grounding, status grounding, decision-value grounding, entity-name grounding, party-role grounding (Applicant/Developer/Owner/Promoter/Planning ownership declaration all remain non-promotable), Site-scope grounding, specific-Application attribution grounding, `needs_confirmation`/`rejected` trust boundaries, failure-preserves-last-valid-summary behaviour, and context fingerprinting/staleness are all confirmed unchanged and re-tested. No token-level prose scanning was introduced. No sentence template was introduced.

## Deliberately Deferred (unchanged from the audit's own recommendation)

AI-derived arithmetic (e.g. "83" from 100% − 17%), fabricated numeric breakdowns, genuine invented Application references, wrong specific-Application attribution, role promotion of any kind, compound applicant-name splitting, malformed/truncated OpenAI JSON handling, the Linked Planning Applications UI, general prose polishing, new data extraction, new party resolution, schema changes, migrations.

## Estimated Production Impact

Not a guarantee - a real regeneration could produce different output. Based on the persisted V7 rejection taxonomy: Fix A ≈ 72-73 allocations, Fix B ≈ 9 (some overlapping with Fix A's compound-error rows), Fix C ≈ 1 confirmed plus an unknown number of the 3 primary `absence_decision_claim` rejections not yet individually verified. Combined estimate: roughly 80-88 of 102 previously-rejected allocations, moving coverage from 61.2% (161/263) toward an estimated 90%+.

## Test Coverage

27 new tests covering: inert-entry equivalence to `[]` for both self-report arrays, the safety guard preventing an empty reference/name from smuggling a material claim, fabricated/wrong references still rejected, case-insensitive label masking (including a different label and an invented Regulation number), and placeholder-decision normalisation (including that Granted/Refused/Withdrawn still reject an absence claim, and that a genuine decision value is never erased). Full suite: 2493 passed (2466 prior baseline). All three fixes additionally verified directly against live production contexts for allocations 4, 6, 9, 13, 32, 51, 66, 196 (read-only, zero writes, zero OpenAI calls).

## Prompt Version

Bumped `allocation-intelligence-summary-v7` → `v8`. Both the prompt text (new Rule 17, updated array-field descriptions) and the validator's grounding semantics changed materially - a v7-generated summary's self-report shape is no longer evaluated identically under v8, so this is a genuine version bump, not cosmetic. This intentionally makes every existing v7 summary (success or failure) eligible for a controlled retry via the existing `--stale` targeting once a Product Owner authorises one - `is_allocation_summary_stale` already detects a prompt-version-only change (V7 Quality Hardening Amendment).
