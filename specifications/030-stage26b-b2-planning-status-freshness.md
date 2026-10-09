# Stage 2.6B B2 Planning-Status Freshness

Status: PREPARED FOR REVIEW — SPECIFICATION ONLY. Implementation, migration, production repair, source-refresh execution and operational activation require separate approval.
Date: 9 October 2026 (Europe/London).

## Objective, business value and user story

Give the buyer an honest, subject-specific planning position even when refresh operations are imperfect. The buyer must distinguish the accepted fact, its authoritative source/event date, successful verification, subsequent failed attempts and uncertainty. Improve evidence trust before prose or ranking. A successful check is not a new permission, acquisition availability or ownership evidence.

As a buyer, I want to see what planning position is supported and when it was verified, so I can choose proportionate investigation without mistaking dated intelligence for a current council finding.

## Authority and demonstrated problem

Application baseline: `c709bd7643161daab16db86b86509aabf289048d` (B1.1 accepted/closed; Render deployment `dep-db3va4g473hc73c38ia0`). Specification 029 is the parent remediation contract. B1.1, v8, Specification 028, Stage 1 and AH/P0-A boundaries remain accepted. All four crons/monitoring remain suspended. No historical gate is reopened.

**Failsworth’s post-refusal successful-verification gap is verified; the exact historical invocation, selection, retrieval or parsing cause is unresolved.**

Failsworth site28/application42, `FUL/355686/26`: stored Awaiting decision; decision/date NULL; last successful status verification 18 September 2026 05:20:51 UTC. Stage 2.6A authoritative observation records refusal issued 25 September 2026. No corresponding recorded status/decision lifecycle event or material-refresh request was established. Do not benchmark an invented parser failure.

Read-only production inspection at 2026-10-08T23:17:24.221564Z confirmed these fields and Southlink site25/application29 `FUL/355201/25`, Awaiting decision, verification 10 September 2026 10:51:19 UTC. Oldham council-run metadata returned seven runs18–24September (six success/one failure); none25–29September. Council run success is not exact-reference verification. Render's seven-day log retention cannot recover the historical per-application cause. No more expired-log investigation is required.

Audit pack SHA-256: `25c765339320d71e1892c88d67aaa93f98ada92f4080174c291f6685b73f724d`. Stage 2.6A23 comparable accessible current records had22 agreements/one disagreement;22/82 applications had successful-verification timestamps. Purposive sample and correlated records do not establish population accuracy. No pipeline-wide parser defect is demonstrated.

## Existing architecture and investigation findings

Reuse `app/pipeline/status_verification.py` exact-reference Idox/Arcus retrieval, `run_weekly._upsert_scraped_application`, `material_change`, `lifecycle_events`, `evidence_refresh`, `scheme_reconciliation` fact positions and `site_profile` reporting adapters. Do not add a second status engine, scheduler or freshness framework.

The verifier has explicit invocation controls, tier eligibility7/14/30/60days, per-council10-record limit and starvation protection. Decided applications are outside its existing pending-only selector. These are existing operational policies, not proof of currentness or causes proven for Failsworth. Retain dormant-by-default scheduling and skip precedence.

Current verifier commits upsert before committing `status_verified_at`; logically coupled facts can persist before the successful-verification watermark. This is a prospective atomicity risk requiring failure injection, not the demonstrated Failsworth cause. The shared upsert skips empty portal values; prospective transition tests must ensure incompatible stale decision fields cannot survive a changed accepted status. Returned reference/council identity must match the intended record before upsert; non-empty reference alone is insufficient.

## Planning-status semantic contract

Keep existing raw status/decision strings and normalisation wherever sufficient; define source-qualified presentation rather than a gratuitous taxonomy migration.

| Position | Required meaning and restraint |
|---|---|
| Awaiting determination/pending | Exact application unresolved according to accepted evidence; never a promise of approval |
| Committee resolution | Recommendation/resolution and date, with direction where supported; formal decision not yet established |
| Granted/approved | Issued permission established by authoritative exact-reference evidence; committee approval alone insufficient |
| Refused | Issued refusal established; retains decision date and source; not a finding that acquisition is impossible |
| Withdrawn | Explicit authoritative withdrawal; absence/404 cannot establish it |
| Appeal pending | Exact appeal/application relationship and authoritative appeal evidence required; original decision retained |
| Appeal allowed/dismissed | Issued appeal outcome and date where supported; original planning decision retained as history |
| Superseded/replaced/varied | Evidence-backed relationship between applications, not a fabricated terminal decision or permission cancellation |
| Unknown/unverified | No sufficient accepted fact or verification evidence; not refused, withdrawn, granted or not commenced |

Unsupported appeal/relationship outcomes remain qualified unknown. Do not infer legal permission validity, commencement, lapse, availability or control from a planning label.

## Fact-specific source authority

1. Issued decision notice establishes the formal decision/date/conditions for its exact reference/version. Issued appeal decision establishes its linked appeal outcome.
2. Current exact-reference council register supports current administrative status and issued decision metadata. A successful retrieval must expose enough identity and status evidence to verify the particular fact; an HTTP200 alone is insufficient.
3. Committee report/minutes establish recommendation/resolution only, not an issued decision. Other planning documents support their own propositions and scopes.
4. Retained portal/document evidence supports a dated finding, not a claim of current verification. Preserve source URL, reference, document identifier/version/hash/date where available.
5. Lifecycle rows are records of established transitions and detection provenance, not independent authority overriding original sources. Previously extracted intelligence is subordinate; AI prose never determines the authoritative status.

No universal last-write-wins rule. Distinguish event dates, document versions and application/appeal relationships. A newer register update does not erase an issued historical decision. A credible contradiction is displayed as conflict and routed for review; neither successful accepted-fact verification nor a new material fact is claimed merely because a conflicting page was retrieved. Wrong reference/council or malformed/ambiguous response fails closed before persistence.

## Timestamp and freshness contract

| Concept | Reuse and semantics |
|---|---|
| Source fact date | Existing `decision_issued_date` and source/document dates where applicable; parse safely, preserve provenance; unavailable/unparseable is unknown |
| Last successful verification | `status_verified_at`: complete identity-valid authoritative retrieval and adequate interpretation of accepted fact; not download time or generic update |
| Last attempted verification | Exact application attempt start/outcome, distinct from accepted fact; see persistence decision below |
| Material change detected | Existing lifecycle `detected_at`/refresh-request timestamp for established status changes; not source-event date or verification-only activity |
| Document checks | `documents_last_checked_at`/`evidence_refresh_last_checked_at`: successful document checks, never status verification |
| Material document change | `material_evidence_changed_at`: existing document-evidence watermark, not repurposed as every status change |
| Intelligence processed | `intelligence_evidence_processed_at`: incorporated evidence watermark, not freshness of every source |
| Generic activity | `last_seen_at` is row activity and cannot backfill verification |

Freshness is a separate request-local assessment: verified within applicable policy, verified but ageing, overdue/requires refresh, currently unverifiable after later failed attempt, conflict, or verification unavailable. Labels must distinguish policy freshness from guaranteed real-world currentness. Currentness is always as-of a dated source check. Operational pause is visible qualification, not source failure. No arbitrary new SLA: reuse existing pending tiers provisionally; approve/measure settled-decision and appeal cadence at the operational gate. A failed attempt does not by itself prove the accepted fact is false. An older failure is not displayed as the latest state after a newer success.

Example presentation, illustrative not observed future production: “Refused — Decision issued25September2026 — Verified8October2026.” Existing dated evidence may display “Awaiting determination — Last successfully verified18September2026 — Current status requires refresh.” Do not claim the illustrative8October verification occurred for Failsworth.

Shared dashboard, profile, related-subject and export adapters must use the same exact-application fact/freshness assessment; retain representative/related/phase boundaries. Do not inherit a parent's timestamp as verification of a child. Display source links or source-link-unavailable, verification-unavailable and conflict explicitly. Accessible text must convey meaning without colour, tooltips or icons alone; responsive layout must retain dates/qualification.

## Failure and atomicity contract

| Outcome | Accepted fact and successful watermark | Attempt reporting and consequences |
|---|---|---|
| Unavailable/timeout/rate limit/unexpected response | Preserve both | Bounded failure category, retryable policy/circuit breaker; no new lifecycle/material fact |
| Parse failure/reference not found/wrong identity | Preserve both | Distinct bounded cause where safely knowable; never infer withdrawal |
| Ambiguous/conflicting authoritative evidence | Preserve accepted fact with explicit conflict | Do not mark accepted fact freshly verified or silently choose a favourable outcome |
| Successful unchanged | Preserve fact; advance successful verification | Clear older failure as latest outcome; no fabricated lifecycle/material event |
| Successful changed | Atomically update accepted fact/date/provenance, successful watermark and appropriate lifecycle/refresh signal | Exactly one coherent change; idempotent retry |

Use one database transaction for the coupled successful update, lifecycle and refresh signal. No intervening commit in reused helpers. Failed persistence rolls back the coupled change and reports failure through a separate bounded attempt outcome after rollback where permitted. If attempt-outcome persistence itself fails, report observability failure; never report successful verification. No external retrieval inside a long-held database lock; recheck identity/expected prior version immediately before atomic update. Concurrent/stale responses cannot overwrite a newer accepted fact; conflict or retry instead.

Inject failure before update, after fact assignment, after lifecycle assignment, before verification assignment, before commit and during commit. Durable state must be coherent old-state or coherent new-state, never new fact with old success watermark represented as completed verification. Lost commit acknowledgement requires reread/idempotent reconciliation, not blind duplicate events or success assertion. Cancellation closes/rolls back sessions. Failure-path attempt records must not become material planning events.

## Persistence/schema assessment

Existing fields suffice for accepted decision/date, successful verification and status-change detection provenance. They do not provide a durable exact-application last-attempt timestamp/outcome: council runs and ephemeral logs cannot truthfully supply buyer-facing later-failure evidence. Document outcomes cannot be relabelled status attempts; lifecycle change history cannot be fabricated for failed checks.

**Recommended minimal prospective persistence delta, separately gated:** nullable `status_verification_attempted_at` plus bounded `status_verification_last_outcome` on Application, if implementation inventory confirms no equivalent existing persistent surface. Store attempt start and completed outcome consistently; distinguish in-progress/interrupted/unknown from completed success. Older attempt completions must not overwrite a newer attempt outcome; use guarded attempt ordering. Interrupted/in-progress outcomes must remain explicit until resolved, never converted into success by age. Keep diagnostic details in redacted operational logs, not arbitrary portal/error bodies. No new history table, framework or failure-event taxonomy. This proposal is justified by the required durable later-failure presentation and seven-day operational retention; it is not authority to run a migration. REVIEW must approve exact schema/migration before implementation of this delta. A no-migration alternative can show latest attempt unavailable, but cannot claim full durable-failure acceptance.

For provenance, use existing exact-reference URLs/document IDs and lifecycle source where sufficient. If durable accepted-fact source attribution cannot be faithfully retained for a proposed notice/appeal consumer, return a minimal evidenced persistence proposal; do not invent new provenance JSON or implement unsupported appeal extraction. Baseline register refresh can remain bounded to its existing authoritative source mechanism.

## Material changes and downstream consequences

Pending→granted/refused/withdrawn, supported appeal outcome and material corrected decision/date require explicit review of affected exact-subject facts. Supersession/variation affects relationship-qualified operative facts, not automatic legal cancellation. Keep existing `material_change`/lifecycle mechanisms; date-only correction coverage must be added deliberately because existing ApplicationState compares status/decision/count, not all dates.

- Scheme Summary: mark existing output stale when an accepted material status/date/source-scope fact changes; do not generate replacement prose.
- Buyer Summary: invalidate only affected buyer+subject evidence interpretation; recompute deterministic mandate assessment through existing v8, never through AI. No second matcher.
- Specification028: reasons remain derived from authoritative assessments; contextual freshness warnings remain separate from classification causes. Same qualified inputs preserve six-field behaviour.
- Opportunity/family presentation: existing subject/family algorithms remain unchanged; legitimate input consequences are enumerated separately, with no identity remap.
- Fingerprints: no algorithm change; verification/attempt-only timestamps must not manufacture material fingerprint changes. Actual fact corrections may change existing values; enumerate impact, including family/order/subject effects where relevant, before release.
- Monitoring/ranking: future consumers may use qualified changes only after separate operational/product gates. No monitoring invocation/rebaseline or commercial ranking follows from invalidation.

## Future refresh strategy and cost

Correctness works with mocked/manual bounded input and does not depend on active crons. Prefer existing targeted direct-reference verification, status/age priority, per-council cap, starvation protection, backoff and circuit breakers. Settled decisions need a lower-frequency or explicit correction/appeal-trigger policy; existing pending-only selector must not be represented as covering every status. Propose measured policy at activation rather than silently expanding daily work.

Keep deterministic status checks independent from AI processing. Unchanged checks do not enqueue model work. Changed fact→qualified invalidation/refresh request is not authority to execute intelligence generation. Rate-limit retry budgets, source terms, per-run requests/bytes/time, Supabase egress and scheduler health must be measured before activation. No full-corpus catch-up or wholesale reprocessing. No paid model calls required for structured pending→refused. Document interpretation for unsupported councils is a separate evidence-backed later decision, not a default AI fallback. This specification incurs zero model calls; future network/hosting cost is unmeasured and must not be described as fitting Free capacity.

## Qualified evaluation set

Retain Stage2.6A dated/source-hashed observations; do not edit frozen policy benchmarks. Use an additive B2 fixture manifest identifying REAL_SOURCE_OBSERVATION, SYNTHETIC_FAILURE or UNRESOLVED, exact reference/scope, source date, observed UTC, source URL/hash/version where retained, expected qualified fact and limitations.

| Case | Evidence and required expectation |
|---|---|
| Failsworth42/28 | Refused25Sep, observed8Oct; source snapshot SHA `8a8cb01baf5f4a032f5d89005597a07f2b63e0dd359451bef179f4c4871312a1`; prospective pending→refused, historical cause UNRESOLVED |
| Southlink29/25 | Pending observation8Oct; SHA `45d3ddd86ba031ca730540a6d554ae01b0e05e5e17b4ded4e243163fc8a32985`; committee position not issued permission |
| Other retained Stage2.6A records | Select exact-reference grants/refusals and dated positive controls only where original retained evidence supports expected status; no new claim from a label alone |
| Withdrawal/appeal/variation | Use retained authoritative evidence where actually available; otherwise synthetic contract tests, clearly labelled, not real-world validation |
| Unchanged/changed refresh | Deterministic fixtures with distinct fact/verification dates and source identity |
| Failed/unavailable/timeout/429/parse/not-found/wrong-reference | Synthetic fault injection; prior fact/watermark preserved |
| Conflicting sources and committee→issued decision | Scoped synthetic contract fixtures plus retained Southlink qualification |
| Atomicity/concurrency/cancellation | Synthetic persistence failures at every coupled update boundary and retry |

A real-world category without retained evidence remains COVERAGE NOT ESTABLISHED; it cannot be counted as a verified benchmark. Do not access full document bodies or production to manufacture fixture coverage. Before accepting a slice, publish exact selected fixtures and source-inspection manifest; preserve originals and source terms, redact unnecessary personal data.

## Acceptance criteria

AC01. Exact-reference Failsworth authoritative fixture can produce Refused and25September2026 without model inference or production repair.
AC02. Failsworth historical invocation/selection/retrieval/parser cause stays UNRESOLVED in all fixtures/reports.
AC03. Southlink retained pending control remains pending; no issued permission fabricated.
AC04. Committee recommendation/resolution alone never qualifies issued grant; source/version conflicts remain explicit.
AC05. Every failed/unavailable/wrong-identity/ambiguous check preserves successful-verification timestamp.
AC06. Those outcomes preserve previously accepted status/decision/date and source attribution.
AC07. Those outcomes create no material planning change/lifecycle event; later-failure qualification is truthful.
AC08. Successful unchanged check advances successful verification with exact identity and adequate parse.
AC09. Unchanged check produces no fabricated material event, invalidation or fingerprint change.
AC10. Successful changed check atomically persists accepted fact/date/provenance, successful watermark and corresponding lifecycle/refresh signal.
AC11. Failure injection, lost acknowledgement, concurrent response and cancellation leave coherent durable state and idempotent recovery; no misleading partial success.
AC12. Source event date, attempt time, verification time and detection time remain distinct, including missing/unparseable dates.
AC13. Credible authoritative conflict remains qualified; retained snapshot never masquerades as a current check.
AC14. B1.1 Renold56, Woodford landscaping/bridge containment, Cedar/Walthew/Strawberry negatives and positive residential controls remain unchanged for equivalent evidence.
AC15. v8 matcher six-field behaviour, mandates, subject/family algorithms and frozen historical/successor contracts remain unchanged for identical qualified inputs.
AC16. AH/P0-A tenure/count/legal/scope semantics remain unchanged; refusal does not establish secured AH or availability.
AC17. Stage1 admission/access/command boundaries and buyer isolation remain unchanged; wrong buyer/subject explanation rejected.
AC18. Deterministic status verification has zero model calls, including failure/retry paths; no page-load generation.
AC19. Offline acceptance uses no production credentials/network/cron; selected test counts include failures/errors/skips/deselections honestly.
AC20. Scheduling, intelligence processing, monitoring and all four cron activations remain separately gated and OFF.
AC21. Shared dashboard/profile/related/export output renders status, source/event date, freshness/failure/conflict consistently for exact scope; responsive/accessibility checks pass.
AC22. Minimal durable attempt contract is either demonstrated on an existing surface or approved/tested as a bounded migration; no invented historical backfill. Unavailable attempt evidence is labelled unavailable.
AC23. Actual fact-change differential enumerates classification, explanation, family/representative/order/key/fingerprint consequences separately from timestamp-only invariance; no production transition.
AC24. Bounded rate-limit/circuit/retry and source-identity tests fail closed; redacted outcomes contain no credentials, document bodies or unnecessary personal data.

## Implementation staging and verification commands

1. **B2 correctness contract and fixtures:** qualified source fixtures, timestamp inventory, atomicity/identity/failure design and minimal schema decision. REVIEW approves exact persistence delta before migration-capable work; no production migration authority.
2. **B2 deterministic correctness:** transactional fact/watermark/lifecycle safety, minimal attempt representation and shared truthful freshness presentation. Offline acceptance, independent review, durable PR/hosted CI; separate merge/release gate.
3. **B2 downstream invalidation:** status/date/source-scope dependency tracing, summary staleness and existing fingerprint differential. No summary generation or monitoring activation. May accompany correctness only if coupling is proven necessary and REVIEW accepts exact scope.
4. **Operational activation:** separate Stage4 scheduler/egress/rate-limit/security acceptance, measured bounded pilot and explicit production activation authority. Not bundled into correctness release.

Future implementation must extend existing tests rather than rewrite benchmarks. Baseline commands, to be run only after implementation authorisation (not claimed run for this documentation):

```sh
"$B2_OFFLINE_PYTHON" verification/stage1_spawn_offline_pytest.py -q -p no:cacheprovider tests/test_planning_status_verification.py tests/test_material_planning_change_detection.py tests/test_evidence_driven_intelligence_refresh.py
bash verification/stage2/check.sh "$B2_OFFLINE_PYTHON" "$B2_EVIDENCE_DIR/stage2"
```

Use an absolute pinned offline interpreter in `B2_OFFLINE_PYTHON` and an approved scratch output directory in `B2_EVIDENCE_DIR`; execute with the existing isolated SQLite environment, no production credentials or model/network access. The Stage2 command also runs its existing Stage1 security and rendered-journey selections. Check these paths on the eventual implementation baseline; add focused B2 transaction/provenance/rendered/attempt tests to offline CI, and run existing B0/B1/B1.1 successor integrity, v8, Spec028, AH, rendered dashboard/profile/related/CSV and mock-refresh suites appropriate to touched paths. No missing/selected suite is called all repository tests. Record exact pass/fail/error/skip/deselect counts, source identities and remote hosted head.

## Security, release, migration and rollback

Keep Stage1 least-privilege command permissions, exact buyer/subject access, allowlisted council navigation, TLS, redirect/SSRF protections, network/body/time bounds and redacted logs. Retained planning evidence is untrusted data, not executable instructions. No administrative runtime fallback or reusable privileged exporter. The exceptional investigation SQL route is not permission to activate an automated refresh. Validator stays NOLOGIN/password-null; no credentials/grants changed.

No historical timestamp backfill from last_seen/download/AI time. Any approved nullable attempt-field migration starts historical records unknown; no data repair/catch-up is bundled. Prospective facts must remain readable by rollback code; prove additive compatibility before release. Schema removal requires separate approval and preservation of audit evidence, not automated DROP on rollback.

Rollback disables future refresh invocation while preserving accepted dated facts and lifecycle evidence. A code rollback must not restore pending over an accepted refusal or mislabel stale data current. No data rollback, saved-subject migration or monitoring rebaseline follows automatically. Existing web auto-deploy/Blueprint pause and cron suspension remain unchanged.

## Monitoring and future acquisition subjects

Historical monitoring hashes disagree with current replay fingerprints; mismatch predates B1.1 and is unresolved. B2 does not depend on diagnosing/rebaselining that state for offline correctness. Activation depends on a separate bounded diagnosis/continuity review. No silent repair.

One planning scheme may contain multiple commercially distinct acquisition opportunities. Stand Golf103whole/60retirement/potential43residual illustrates the requirement;43 is not independently validated. Future work must reconcile component subjects against existing Stage2.5B phase/parcel/family architecture before proposing new machinery. B2 does not decompose opportunities.

## Explicit exclusions and decision requested

No application implementation, production repair/write/export expansion, schema migration/backfill execution, source-refresh run, cron/intelligence/monitoring/historical rebuild activation, model calls, generated summaries, ranking/Stage2.5C, AH remediation, ownership enrichment, fingerprint algorithm change, subject migration, StandGolf decomposition, merge or deployment.

Request REVIEW acceptance of this specification and authority for the first bounded offline correctness/fixture slice, with an explicit decision on the proposed minimal durable attempt persistence before any schema-capable implementation. Operational activation and downstream release/transition remain separate gates.
