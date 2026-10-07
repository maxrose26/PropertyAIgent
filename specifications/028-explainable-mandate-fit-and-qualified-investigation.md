# Explainable Mandate Fit and Qualified Investigation Presentation

Status: **PREPARED FOR REVIEW — NOT IMPLEMENTATION AUTHORISATION.**
Date: 7 October 2026. Bounded Stage 2.5B presentation follow-up, aligned with existing Stage 6 buyer UI/UX objectives.

Baseline: accepted deployed release `22636ddab7e0af9b6220c6466d400bc1ec98aafc`, matching policy v8. Stage 2.5B and its completed transition, rebaseline, re-onboarding and Gate B validation are not reopened. All production crons remain suspended.

Related: [roadmap decision](../docs/PRODUCT_ROADMAP.md#product-owner-decision-record--7-october-2026), [commercial evidence](023-stage2-commercial-evidence.md), [discovery](024-stage2-5-buyer-discovery-and-opportunity-decomposition.md), [subjects and v8 amendments](025-stage2-5b-acquisition-subject-decomposition.md), [Gate B](026-gate-b-production-discovery-validation.md), [release safeguards](../docs/V8_RELEASE_RUNBOOK.md).

## Objective

Explain why the selected acquisition subject is compatible with the active buyer's mandate, what actually affects its classification, and what remains unverified for acquisition investigation. Make no claim that mandate fit verifies acquisition quality or availability.

## Business Value

The accepted investigation found 43 Strong / 8 Possible Nesten families, 20 complete / 31 partial retained explanations, and 14 meaningful recorded investigation signals / 37 contextual-only families. Those numbers describe the accepted historical artifact, not guaranteed future populations. Improve interpretation of existing discovery before ranking or enrichment. No production rerun is needed to implement or test this contract.

## User Story

As a buyer, I want to understand mandate compatibility for the subject shown, see evidence-qualified investigation signals separately, and recognise unresolved facts so that I can decide what to inspect without confusing a good mandate fit with a verified acquisition opportunity.

## Requirements

### 1. Vocabulary and separation

- User-facing `STRONG_FIT` becomes **Strong Mandate Fit**; `POSSIBLE_FIT` becomes **Possible Mandate Fit** wherever buyer-fit labels are rendered in the affected dashboard, related-subject, existing opportunity-card and detail/profile paths.
- Internal classification constants, policy version, investigative flag, fingerprints, identifiers and persisted benchmark expectations remain unchanged. Other recommendation taxonomies and AH qualification labels are not renamed.
- Show the active buyer/mandate context. Add a concise qualification: "Mandate fit describes compatibility with this buyer's requirements; acquisition availability and control are not verified by this result."
- Separate **Why it fits**, **What affects this classification**, **Other evidence limitations**, and **Investigation evidence / checks**. Empty sections may be omitted except required missing-explanation and unverified-evidence notices.
- Do not call current deterministic family order commercial ranking. Do not invent a score or relabel a contextual signal as acquisition readiness.

### 2. One assessment, one subject, faithful reasons

Consume the `BuyerFitAssessment` already attached to the same subject's `source['buyer_fit']` and its authoritative facts/context. For an authorised fresh detail request use the existing `evaluate_buyer_fit` boundary with that subject's validated facts and scope; never bare `assess_buyer_fit` without B2 context. Do not recompute a second policy in a presenter or evaluate separately for each text section.

Positive reasons come from that assessment's `matches`. Preserve exact meaning, buyer metric, scope, quantities and uncertainty. Do not infer unrepresented positives from the classification, a route, lifecycle label, mandate notes, headline, count or absence of a negative. Existing positive strings may also contain a non-preferred-scale qualification; do not strip it. Preserve existing strings rather than changing matcher prose in this gate.

The compact card may show two positives, but must disclose truncation (for example "2 of 4 recorded reasons") and offer the remaining reasons in an accessible expansion/detail. Full detail shows every available reason. Truncation is not incomplete assessment coverage.

### 3. Classification causes versus context: technical boundary

At the baseline, `BuyerFitAssessment` exposes `classification`, `is_investigative_exception`, `matches`, `does_not_match`, `unknown`, `investigate`. It does **not** expose rule identifiers, reason coverage or per-reason causal roles. Inside `assess_buyer_fit`, `blocking_unknown`, `scale_possible` and `scale_outside_discovery` drive precedence; the `unknown` and `investigate` lists also contain neutral/contextual limitations. Bucket membership alone therefore cannot establish a cause.

Implement, only after approval of this specification, the smallest **additive in-memory explanation trace** at the existing reason-emission / classification-decision sites. It must record the existing rule's reason, stable provenance identifier, semantic role (positive, classification-affecting, contextual or investigation), and whether that role actually contributed to the returned classification under existing precedence. No new predicates or thresholds are allowed. Use existing branch results; do not duplicate comparisons, parse reason text, infer causes from classification labels, or retrospectively evaluate rule conditions in the UI.

This instrumentation is permitted solely as presentation provenance: existing six assessment fields and behaviour remain identical, metadata is non-persistent and is excluded from matching/evidence/agent fingerprints, baseline summaries, monitoring transitions and benchmark identities. Default metadata absence must remain compatible with existing constructors and historical/partial inputs. Audit serialization consumers explicitly; accidental new fingerprint input is a NO-GO. The trace must not feed back into any matcher decision. Rule identifiers are internal diagnostic provenance, not planning-document citations or evidence verification; do not present them as documentary sources or build a general explanation engine.

For Possible Mandate Fit, freshly evaluated cases must display the recorded existing scale/preference or uncertainty qualification that actually produced `scale_possible`, including applicable preferred/discovery bounds and total-versus-affordable metric. A missing control/physical-status fact is not a cause merely because it appears in `unknown` or `investigate`. For Strong Mandate Fit with contextual unknowns, keep those visible without suggesting they downgraded the classification.

An entry can legitimately supply a positive and a classification-affecting qualification; display both with their relationship clear. A branch taken but overridden by a higher-precedence result must not be called the decisive cause. For excluded or insufficient-evidence subjects, do not misdescribe soft preferences as hard failures.

### 4. Partial/missing explanation coverage

Do not retroactively mark the accepted 20/31 artifact groups complete by assuming current reason lists are exhaustive. Completeness is established only when the current evaluation's instrumented applicable paths cover its returned classification, and the presentation retains all those outputs. Do not claim completeness merely because `matches` is non-empty.

Presentation states: **complete recorded assessment**, **partial recorded explanation**, or **matching explanation unavailable**. These are explanation coverage states, not new fit classifications. Retained inputs without sufficient trace/coverage must default to partial or unavailable. Show available positives verbatim and state that other reasons/classification causes are not fully available.

If a Possible result has no authoritative causal trace, show "Possible Mandate Fit — classification explanation not fully available". Do not generate a guessed boundary explanation. If no reasons exist, show "Matching explanation unavailable" rather than "No limitations" or an invented positive. The historical population is never replayed through fabricated assessments.

### 5. Qualified evidence, missing facts and AH independence

Reuse existing deterministic evidence presenters/structures: routes, count assessments, acquisition phasing, residual qualification, planning reconciliation and ownership/control reporting. Existing headlines are evidence context, not causal fit explanations. Do not expand raw AI narratives into trusted evidence.

Show available source reference/link, subject scope, evidence date/version and qualified status. Where unavailable say "Source provenance incomplete" / "Evidence date unavailable"; never fabricate a citation/date. Treat absent facts as unverified, not negative or zero. Distinguish record age from proven evidence staleness.

Explicitly identify absent or unresolved **ownership/control**, **acquisition availability**, **physical commencement/completion**, and **provenance**. Do not downgrade the fit for these notices unless the existing assessment's trace establishes an actual classification-affecting rule. A buyer accepting unresolved control does not turn it into verified control.

Permission, pending applications, portal filings, EPCs, assumed review/lapse dates, applicant names and marketing context retain their existing qualification. No "available", "not commenced", "completed", "legally lapsed", owner/controller, sale intention or package claim follows from these alone. An assumed date remains labelled assumed; UNKNOWN stays UNKNOWN. Phasing and residual R2 context are not proof of an available parcel. R1 evidence requirements and dormant production state remain unchanged.

AH identity, source/scope trust, affordability quantum/percentage, legal/tenure qualifications, hard minima and qualification labels remain independent. A total-unit reason cannot explain an affordable-unit mandate. Existing-policy AH caveats remain; mandate-fit terminology must not imply AH count/package verification. No AH schema/security/policy or P0-A integration is permitted.

### 6. Representative, related subjects and profile scope

Keep the representative chosen by `opportunity_families` and all related subjects, fit keys, counts and order unchanged. Each displayed explanation/evidence panel belongs to its own subject. A parent positive, phase count, grant or control assertion must not be inherited by another subject merely through family membership. Wider family context must be explicitly labelled wider context, not representative evidence.

The site destination is currently a wider evidence profile, not automatically a subject-specific buyer assessment. Preserve that distinction. An additive navigation context may carry an existing subject key for presentation resolution only; it must not create identity, change family selection or bypass buyer/site guards. Resolve it server-side against the admitted buyer's authorised existing subject set; never trust query-supplied fit/reasons or another buyer's session assessment. No new full-universe query may be added just to render each card or recover a profile explanation.

On valid dashboard-to-profile navigation, show the originating subject/scale and its own explanation separately from wider-site evidence. If exact authorised subject resolution cannot be established, show "Subject-specific mandate explanation unavailable" and retain a qualified evidence-only profile: never silently substitute a different phase, whole-site assessment or representative. Direct generic profiles need not invent a fit. Related-subject expansion must expose each subject's own explanation/limitations; it must not present the representative's explanation as theirs.

## Non-Requirements

No matcher policy/rule/version or mandate changes; no family/subject identity, membership, representative, ordering or count changes; no ranking/score; no enrichment, production data access, model calls, new schema/migration, deployment, cron activation, re-onboarding, rebaseline or Gate B rerun; no Stage 2.5C/2.6 implementation. No wider UI redesign, CRM, ownership integration, benchmark rebaseline or paid evaluation. If schema, changed semantics or unbounded data work proves necessary, STOP and return an evidenced proposal to REVIEW.

## Data Model

No database entity, migration or persistence change. An optional request-local trace and shared presentation view model may carry authoritative reasons, causal roles, coverage and existing source references. No stored narrative repair/backfill. No buyer-specific trace shared across buyer sessions; no cache of private assessments added in this gate.

## User Experience

Compact dashboard example (only when the actual assessment supports it):

> Possible Mandate Fit · selected buyer
>
> Why it fits: [recorded positive reason]
>
> What affects this classification: [recorded non-preferred scale reason and bounds]
>
> Other evidence limitations: Control unverified; availability unverified.
>
> Investigation evidence: [qualified planning signal, source and scope].

These placeholders are illustrative, not output text inferred from labels. Preserve honest approximate/range scale. Expand details without a new page hierarchy. Use text alongside badges; no colour-only meaning. Do not add urgency/readiness language or numerical ranking.

## Architecture Considerations

Baseline inspected read-only:

| Component | Relevant existing boundary / intended follow-up |
|---|---|
| `app/policy/buyer_matching.py::BuyerFitAssessment`, `assess_buyer_fit` | Existing reason lists and decision precedence; additive trace only, no semantic alteration |
| `app/policy/buyer_matching_b2_context.py::evaluate_buyer_fit` | Authoritative context-aware production evaluator; do not bypass |
| `app/reporting/buyer_family_feed.py::evaluate_buyer_families` | One assessment per existing subject; scope guards and no mutation of shared inputs |
| `app/reporting/opportunity_families.py` | Identity/grouping/representative/order remain untouched |
| `app/reporting/family_presentation.py::_subject_view`, `fit_label`, `SubjectView` | Currently truncates positives to two; shared explanation presenter and terminology belong here or a small reporting helper |
| `app/ui/shell.py::opportunity_family_card`, existing opportunity cards and badge defaults | Render shared view model; no reasoning in UI |
| `app/ui/pages/00_Dashboard.py` | Preserve family feed and buyer context; no extra per-card queries |
| `app/reporting/profile_destination.py`, `app/ui/pages/1_Scheme_Detail.py`, `app/ui/site_profile_view.py` | Qualified wider-site destination; validate subject context or withhold subject fit |
| `app/ui/pages/3_Local_Plan_Sites.py` | Existing allocation assessment reason lists: adopt shared presentation without changing evidence or policy |
| `app/reporting/opportunity_route.py`, `acquisition_phasing.py`, `residual_opportunity.py`, `ownership_control.py` | Reuse qualified evidence; do not convert labels/context into causal fit or availability |

Audit affected runtime label paths (including badges using `.replace('_', ' ').title()`) rather than blindly replacing historical docs, fixtures or agent recommendation terminology. Reuse guarded read paths; no new writes, credentials, network/API/model dependencies. Keep unversioned stored AI narratives withheld and physical-status inference fail-safe.

## Acceptance Criteria

All criteria must pass on synthetic/offline evidence before any implementation candidate is presented for integration. Production counts are context only, not an acceptance oracle.

| ID | Measurable requirement / verification |
|---|---|
| AC1 | Every affected rendered buyer-fit surface uses Strong Mandate Fit / Possible Mandate Fit; no legacy generic Strong/Possible fit label remains there. Internal keys and independent AH/agent labels are unchanged. |
| AC2 | For complete traces, 100% of displayed positive/causal statements map to a recorded reason from the same buyer assessment and subject. No inferred reasons or duplicated policy predicates. Full detail retains all reasons; compact truncation shows count and accessible expansion. |
| AC3 | Cover complete, partial, empty and trace-absent fixtures. Partial/missing inputs always disclose coverage; no false completeness, guessed cause or "no limitations" claim. A legacy Possible result with positives but no causal trace uses the explicit incomplete-classification explanation. |
| AC4 | Fresh exact out-of-preferred/in-discovery and approximate boundary cases display the existing scale_possible cause. Strong plus contextual development/control unknown, Possible plus those unknowns, and higher-precedence exclusion cases prove contextual/overridden reasons are not called decisive causes. |
| AC5 | Pending-only, granted-plus-pending, UNKNOWN physical status, assumed lapse, applicant-only, provenance-missing, R2 residual and unverified strategic-capacity fixtures produce no unsupported ownership/control/availability/commencement/completion/legal-lapse/package claim. |
| AC6 | Parent 500 / phase 125, multiple phases, phase-only, plot, related subject with different fit, and invalid/missing destination context preserve each assessment's scope. No cross-subject evidence inheritance or silent profile substitution. |
| AC7 | Synthetic two-buyer journeys, buyer switching, tampered context, non-admitted and wrong-buyer direct links preserve Stage 1 refusal/isolation. Query parameters cannot inject classifications/reasons or authorise data. No private trace leakage in caching/session output. |
| AC8 | Housing Association affordable-unit metric/hard minimum and qualified/unqualified AH evidence cases preserve existing classifications and independent caveats. Total/private/affordable measures and AH identity are not conflated. |
| AC9 | Differentially compare against exact baseline: all existing six BuyerFitAssessment fields (including ordered strings/flags), v8 fingerprints/baseline inputs, subject/family keys, membership, representatives, exclusions, counts and ordering are identical across the full regression fixtures and all four canonical buyer strategies. Policy version remains 8. Any drift is NO-GO; do not rewrite frozen benchmark expectations. |
| AC10 | Actual rendered dashboard, related expansion and valid/invalid profile journeys show buyer context, reason sections, coverage and evidence qualifications. Include real page-link/navigation checks as well as view-model unit tests; string-only source checks are insufficient. |
| AC11 | Verify at 390, 768, 1366 and 1920 CSS-pixel widths and 200% zoom: no clipped/overlapping critical text or unintended horizontal scrolling. Keyboard-accessible links/expanders, visible focus, meaningful headings/labels, screen-reader-readable caveats and text equivalents for badge colour. Retain rendered screenshots and accessibility observations; AppTest alone is not proof of browser layout/accessibility. |
| AC12 | Presentation mapping over already-assessed inputs causes zero extra database queries, model calls, writes or network requests. Detail resolution is bounded and reuses existing guarded subject reads; synthetic query-count tests must detect per-card/full-universe re-evaluation regressions. No production measurement authorised. |
| AC13 | Focused explanation tests, full relevant business/UI/family/journey regressions, Stage 1 security and AH compatibility/walkthrough pass with exact commands/counts reported. Tests for legacy labels may be updated narrowly while preserving their underlying safety assertions; no assertion deletion to hide regressions. |
| AC14 | All new tests are automatically selected by the existing offline Stage 2/security job or its offline journey invocation. Both required hosted jobs pass on the exact future candidate. CI adds no production credentials, paid calls or deployment behaviour; runtime remains within existing 15-minute job limits. |

### Required implementation verification and evidence

1. Focused causal-trace, coverage, rendering, scope and isolation tests; run complete touched test files.
2. Relevant suites include `test_buyer_matching.py`, `test_buyer_mandate_v2_phase_b2.py`, `test_opportunity_families.py`, `test_buyer_family_feed.py`, `test_family_dashboard.py`, `test_family_dashboard_render.py`, `test_stage2_commercial_evidence.py`, `test_stage2_unit_phasing.py`, `test_stage2_profile_journey.py`, allocation/profile and relevant v8/fingerprint/frozen-oracle regressions. New explanation tests must be explicitly added to hosted selection if not in already-selected files.
3. Exact hosted commands locally: `bash verification/stage2/check.sh <test-python> <evidence-dir>` and `bash verification/web_ah/check.sh <test-python> <evidence-dir>` using their existing synthetic/offline isolation. Stage 1 security/journey commands remain selected by the Stage 2 script.
4. Offline rendered/browser accessibility evidence per AC10/11, no production/browser network dependencies added to CI. If existing CI cannot cover layout checks safely, record the offline manual evidence separately rather than weaken the criterion.
5. Record base/candidate SHA/tree, changed paths, selected test commands/counts, differential output, screenshots, CI run IDs/head SHA and independent review. No claim that a selected suite covers every repository test.
6. Independent review must verify causal fidelity, partial coverage, unchanged policy/fingerprints/order, buyer isolation, AH independence and scope-correct profile behaviour. Any unsupported explanation, semantic/security drift or relevant failed check is NO-GO and returns to REVIEW.

## Future Enhancements

Targeted Stage 2.6 source verification precedes paused Stage 2.5C by approved roadmap decision, but its scope/acceptance and implementation need separate approval. Acquisition ranking, deep verification, external ownership intelligence, paid benchmarking and autonomous monitoring remain deferred. This specification does not authorise implementation, publication, merge or release; each requires the applicable separate REVIEW gate.
