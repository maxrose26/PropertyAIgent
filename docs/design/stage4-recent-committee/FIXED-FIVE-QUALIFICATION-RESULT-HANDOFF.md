# TO REVIEW — FIXED-FIVE QUALIFICATION RESULT AND REGISTERED THREE-APPLICATION ADMISSION

Master Stage 4: OPEN. Current gate: committee-discovered application admission. Next gate: review bounded production admissions, then a separate prospective primary-discovery acceptance slice.

## Verified consumed execution

Run https://github.com/maxrose26/PropertyAIgent/actions/runs/38652271830 completed successfully, run 1 / attempt 1, SHA a5ba90bde99a86810e10e3710925d89598b9e7b9. The qualification authority is CONSUMED. No rerun or attempt 2 occurred.

Artifact 11935541127 was downloaded and validated. ZIP SHA-256:
`e82ca7f14010a7c4fdb1dc7a5c3f0bdc5f218d8860a2a33cf4144ba8ad8d66af`

One bounded result.json; JSON SHA-256:
`08d646d0ccae55aa5d35a66848b893b7ae82cdf0ce3b6a2c64ae620f21ee4e59`

Exact run, code, manifest and five identities reconcile. The workflow has only the credential-free transport job, no production environment, database secret or admission capability. Artifact counters confirm zero database connections, reads, writes, applications created and model calls. No production transaction or uncertain commit occurred.

## Five-candidate reconciliation

| Candidate | Identity and supported facts | Scope and outcome |
|---|---|---|
| Bolton 21080/25 | Identity NOT_QUALIFIED; no qualified factual fields | SOURCE_UNAVAILABLE; WITHHELD_FROM_FREEZE |
| Manchester 143413/FO/2025 | Exact displayed reference; Status Final; Decision Approve; decision date 2026-09-28; all four fields PRESENT_VALUE | COUPLED, B2 eligible; frozen for admission |
| Manchester 145583/FO/2026 | Exact displayed reference; Status Under Consideration; decision and decision-date UNKNOWN | INITIAL_STATUS_ONLY, B2 eligible; frozen; no decision/date verification |
| Salford PA/2025/1664 | Exact displayed reference; status and decision NOT_PRESENT; decision-date UNKNOWN | COUPLED observation B2-ineligible; B2_EVIDENCE_SCOPE_INELIGIBLE; WITHHELD_FROM_FREEZE |
| Tameside 26/00396/FUL | Exact displayed reference; Status Decided; Decision Approve; literal date Tue 28 Jul 2026; all four fields PRESENT_VALUE | COUPLED, B2 eligible; frozen; canonical stored date 2026-07-28 |

Salford's available evidence supports neither coupled verification nor the existing narrow status/date scopes. Its rejection is correct without changing the evidence contract. It is not evidence of a Salford-wide integration defect. Bolton's artifact does not isolate DNS, TLS or HTTP failure; no broader cause is inferred. Both remain withheld, with no further source probe in this slice.

Official URLs, retrieval timestamps, field states and per-source fingerprints are preserved in run-38652271830-qualification.json and the frozen manifest. Four qualified observations have SHA-256 fingerprints; Bolton has none. No raw HTML, applicant/contact data, credentials or session payload is retained.

## Resource reconciliation

| Candidate | Requests | Received bytes | Supervisor seconds | Peak owned RSS bytes | Cleanup |
|---|---:|---:|---:|---:|---|
| Bolton | 2 | 0 | 9.715 | 71831552 | CLOSED |
| Manchester 143413 | 27 | 9415958 | 5.421 | 816664576 | CLOSED |
| Manchester 145583 | 27 | 9416396 | 4.297 | 828432384 | CLOSED |
| Salford 1664 | 33 | 11038935 | 3.974 | 833261568 | CLOSED |
| Tameside | 1 | 46007 | 2.994 | 73015296 | CLOSED |

All five are WITHIN_LIMITS; zero surviving owned processes. Aggregate 90 requests / 29917296 received bytes across independently bounded sequential workers. Arcus measured encoded bytes total 5937665; Idox encoded totals are unavailable. Bounds were not increased. Arcus used one page per worker, navigation counts 1/1/2 and redirect counts 0/0/1; zero Arcus retries. Bolton's two requests remain within its existing bounded retry behavior, not a workflow rerun.

## Frozen cohort and admission architecture

Exactly three candidates are frozen: Manchester 143413/FO/2025, Manchester 145583/FO/2026 and Tameside 26/00396/FUL. One confirmed material / two potentially material. Tameside remains a battery-storage variation with UNKNOWN residential/buyer relevance, not a new residential opportunity.

The owner absence check at 2026-10-14 22:46:16.98426+00 is retained as acceptance-only evidence. No further owner SQL or production query was performed. The operational caller automatically reads exact council/reference identity with LIMIT 2 before each record. The shared transaction independently rechecks identity, uses ON CONFLICT, and performs bounded committed readback. Existing identities and races reconcile without duplicate creation or factual overwrites.

The caller reuses the shared PR #84 identity transaction and B2 path, with fresh source evidence obtained after B2 captures the old state. It does not replay qualification observations as current evidence. Source workers receive no production credential; actual application-ID projection changes only that ID. No new writer, schema, business rule or evidence scope was introduced.

New applications remain discovery_pending with site relationship and application role UNKNOWN. No automatic site/link/opportunity creation. Committee proposal, scale and relationship evidence remains retained for qualification; this caller does not claim production proposal/unit/type population. Deeper evidence acquisition and AI_EXTRACTION_PENDING remain explicit.

Tameside's retained officer-report SHA-256 is independently verified:
`66fb4b05f108ff7ffac17e824a29afddabcfae55feeae5d58c74b05c75f0698e`

Its header explicitly says 26/00396/FUL. The manifest and transaction audit distinguish report bytes from the official meeting-container URL (CId 161 / MId 11814). Direct report URL remains UNKNOWN. The inconsistent minutes reference is not used. Two bounded metadata lookups failed; no wider committee research was restarted.

Ordinary safe factual rejection may leave a previously qualified identity as discovery_pending with no rejected facts certified, only after certain readback, closed cleanup and bounded resources. Such identity creation is not factual-verification success. Uncertain transaction, security, resource or cleanup failures stop the cohort. No blind retry or automatic resume.

## Integration and validation

PR #87: https://github.com/maxrose26/PropertyAIgent/pull/87 — MERGED with [skip render].

Final head: `cfd6376dba01d98444aa469cebef0b3d44f7e577`
Tree: `59a29bc05b99b80105f8a6ca9580e7952aef4259`
Merge/current master: `e1e98704913b572e46822f1fbe2b5a273f47bbd9`
Merge tree matches the reviewed tree. All 11 published changed paths matched local blob identities.

87 focused offline tests passed. Ten exact-head hosted checks passed, zero failures or skips. The native PostgreSQL job passed all four tests, including the new three-record caller, canonical Tameside date/readback, concurrency/duplicate protection and lost-acknowledgement preservation. Independent review verified the artifact eligibility, report header/hash, corrected provenance, ID projection, relationship uncertainty and reused persistence controls.

Changed paths: workflow registration; frozen manifest/caller; focused caller/PG tests; two existing workflow allowlists; discovery CI invocation; minimized qualification audit; 37-reference ledger; review report. No B2 or application business-rule implementation was changed.

## Registered production execution — not yet dispatched

Workflow: `.github/workflows/stage4-material-cohort-admission-once.yml`
Workflow blob: `26d978bd4fb28c2b733a961ee7b7e6d49a64bb58`
Manifest SHA-256: `91be2de17f9e7fd0f4e62c7e95b611ef91bb1484673191f489f928b9879e5981`

One protected admission job, existing stage4-production-canary environment and DATABASE_URL secret name; no new credential. Exact master/workflow revision, manifest, run 1 / attempt 1 and fixed three identities are enforced. Eight-minute outer job limit; existing per-record bounds remain unchanged.

After merge, workflow history predating registration showed zero executions of the new admission workflow. The qualification workflow has only consumed run 38652271830, run 1 / attempt 1. No production admission was dispatched and no production application was created.

The connector cannot dispatch and the existing browser session is unavailable. Before owner dispatch, confirm DATABASE_URL is present in stage4-production-canary by NAME ONLY; its current presence/value cannot be inspected through this connector. Do not reveal, replace or transfer its value. Existing accepted route/compatibility checks are reused and an empty secret fails before database access.

Owner action under existing authority:
1. Confirm that existing secret name is present.
2. Open https://github.com/maxrose26/PropertyAIgent/actions/workflows/stage4-material-cohort-admission-once.yml . Select Run workflow, branch master.
3. reviewed_sha: `e1e98704913b572e46822f1fbe2b5a273f47bbd9`
4. manifest_sha256: `91be2de17f9e7fd0f4e62c7e95b611ef91bb1484673191f489f928b9879e5981`
5. authority: `AUTHORISE_THREE_QUALIFIED_MATERIAL_COHORT_ADMISSIONS_ONCE`
6. Dispatch ONCE and complete the normal protected-environment approval if presented. Provide the run URL/ID. No rerun/attempt 2.

This is production admission for the three eligible identities, not another qualification diagnostic. No renewed generic Product Owner permission is requested. If the existing secret is absent, stop and report its NAME/PRESENCE only; do not create credentials or dispatch.

## Remaining limitations and decision

GO — consumed qualification reconciled; eligible three-record admission registered and verified. Production admission acceptance remains PENDING execution/audit. Master Stage 4 remains OPEN.

43 observed recent references still reconcile as six known / 37 initially absent; the updated absent ledger is one confirmed, five potential, 31 insufficient, zero confident non-material exclusions. Three are frozen for admission; Bolton 21080/25 and Salford 1664 are withheld, Salford 1506 remains withheld, and 31 insufficient references remain explicit. This is not complete nine-council committee coverage or proof of 37 material missed opportunities.

All three eligible applications' retained official validated dates are outside the unchanged 28 September–4 October primary VALIDATED comparison window. No systemic primary-discovery defect is demonstrated; public-availability latency remains UNKNOWN. Final prospective acceptance has not started.

Stockport's accepted supplementary committee limitation, Trafford deferral and Salford 1506 withholding remain unchanged. Both earlier consumed workflows were not retried. No models, AI regeneration, schedules, Render deployment, new infrastructure, sites, opportunities, broad archive/document acquisition or Stage 5+ work.

Precise next action: owner execution access for the registered cohort, followed by DEVELOPMENT reconciliation of CREATED / ALREADY_EXISTS_AT_EXECUTION / factual withholding / failure / uncertain commit, B2 readback and lifecycle effects. No new product/evidence-contract change is required by the inspected result. A further Product Owner decision is needed only if a genuine execution stop condition arises. Prospective acceptance remains a later bounded slice.
