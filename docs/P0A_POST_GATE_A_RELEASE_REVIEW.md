# P0-A post-Gate-A release review — 29 September 2026

## Decision status

Offline Gate A is CLOSED by independent Product Owner acceptance, with the exceptions below. Production release is NOT approved. This package changes only local documentation and proposed CI tooling. No push, PR, migration, deployment, activation, live scrape, paid call or production setting change occurred. Neither the Manchester OOM cause nor Supabase egress is resolved by these results. Stockport and all-council readiness remain open.

## Exact baseline and changes

- Tested application candidate: `ff0baa237f809265be50b72247633a7b7a193c1d`.
- Matched baseline: `301a56b3cde781f37e5f5bb0ffaded6537d5ca14`.
- Branch: `feature/p0a-bounded-discovery`; initial clean HEAD `c102551e987f6fa56d02a1ef7389b2476cf95e17`.
- Preserved documentation branch: `docs/astra-reliability-handover-20260928`.
- Approved specification 019 SHA-256 remains `c007e2b2912ae5d8817142c32fdf35e0000f72d4fa127d5c83e32e6ef10970f8`.

Every intervening commit before this preparation:

| Commit | Changes after the tested candidate |
|---|---|
| `47a61904ca847202ddb8ae01f62f5910e0d8f0fb` | WSL launcher `verification/p0a-wsl-run.sh`: candidate/blob constants updated for UTF8 candidate. This IS a launcher change; the uploaded second WSL run used the corresponding external wrapper. |
| `ef44657edb824f4dbede5ecca43d6c55ab6e1aac` | WSL review and JSON evidence report only. |
| `3a93ae055f003649729e775402f4b4373fd46bf1` | Access handover documentation only. |
| `c102551e987f6fa56d02a1ef7389b2476cf95e17` | Session-first/GitHub-fallback access documentation only. |

No application, migration, application-test or dependency changes after ff0baa2. The frozen integration runner `verification/p0a_gate_a.sh` is unchanged, blob `9102803d9b2db4b52e22b4b7c46aa4a5657a1723`. This preparation adds `.github/workflows/p0a-offline.yml`, `verification/p0a_ci.sh`, `verification/p0a_ci_assess.py`, its seven parser unit tests, this report and a status correction in operating instructions. The final preparation commit is provided in the accompanying response; it is not a newly integration-tested application candidate.

## Accepted evidence and remaining test boundaries

Uploaded `results-20260929T090946Z` establishes:

| Suite | Passed | Failed | Skipped | Deselected | Duration |
|---|---:|---:|---:|---:|---:|
| Candidate | 351 | 4 | 0 | 1 | 66.72s |
| Matched baseline | 282 | 4 | 0 | 1 | 27.75s |

All four failures are the identical missing-OPENAI_API_KEY failures in `test_pr2_final_amendment_migration_and_intelligence_processing.py`: outstanding selection, cross-council extraction limit, isolated failure, bounded workload. No credential is to be added to make these green. The renderer-RSS test `page_recycling_keeps_renderer_rss_flat_across_navigations` was explicitly deselected in both runs. This is not a fully passing suite.

Real PostgreSQL migration/idempotence/constraints/conditional ownership/rollback/interrupted continuation checks, all five real Chromium tests, and real inherited-lock/supervisor-death tests passed. Environment: WSL2 Ubuntu24.04, Python3.12.3, PostgreSQL16.15, Playwright1.63.0/Chromium1243, pinned dependency snapshot. Browser cleanup with blocked persistence and five persistence-stall positions passed. Observed stalls terminated in 2.442–2.456s against 2s + 3s scheduling margin; browser stop 8.439s and cleanup/successor 8.492s against 8s + 4s margin. Cooperative cancellation 0.204s. The supervisor-death lock-exclusion case deliberately uses test-side child termination before checking successor entry; it is not proof of automatic cleanup after every arbitrary supervisor death.

Local preparation checks: seven assessment-parser unit tests passed; assessment of the actual uploaded XML/logs reproduces 351/282 passes and the exact exceptions; shell syntax and YAML parsing passed. These do not substitute for integration execution of the new GitHub launcher. GitHub CI has NOT run. No application integration rerun is required solely for these documentation/CI edits; the new launcher must execute successfully in GitHub before calling CI operational. Any application/DB-bound change arising from release preflight creates a new candidate and requires affected offline and pooler integration checks.

## Read-only live findings

Authenticated Render and Supabase inspected on 29 September 2026. No secrets were revealed or copied.

| Check | Evidence / limit |
|---|---|
| Discovery service | `propertyaigent-daily-scrape`, `crn-d9sv93vavr4c73f98rb0`, Python cron, Standard, Blueprint-managed. |
| Deployed discovery commit | Render Settings: `6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a`, repository master. P0-A is not deployed. This is the cron's commit, not a newly verified web-service commit. |
| Actual configured entrypoint | `python -u -m scripts.run_daily_councils`; schedule `0 5 * * *` UTC. Suspend action available; service not suspended. No assertion that a process was active at inspection time. Last successful run shown: 11 August 2026 11:39 BST. |
| Environment | DATABASE_URL present but masked; no custom P0-A activation/disable variables displayed and no linked environment groups displayed. Old deployed code lacks the new switches, so absent activation does NOT disable the currently scheduled old code. |
| Runtime access | Shell stayed at Connecting; no command executed. Actual instance identifier, PID/start visibility, effective connection host/port/SSL/options, timeout behaviour and read-path success remain unverified. |
| Supabase | Property Tools / Property AIgent, project `zcikcfgpblzuzpanpdqd`; restriction banner and 9.13GB/5GB egress; DB size ~81MB/500MB. Database status healthy, PostgREST/auth unhealthy; project overview unhealthy. These dashboard statuses do not establish app connection success/failure or restriction causation. |
| Connection route | Supabase Connect offers direct/session/transaction routes. Render's masked URL prevents proving which is actually selected. A Connect-dialog default is NOT the application route. No connection string exported. |

Render's official documentation promises one active run per cron service; a next scheduled run waits for the active run, and manual triggering cancels the active run first. This supports the same-service successor contract, not cross-service exclusion. Default runtime docs list RENDER_SERVICE_ID, RENDER_SERVICE_TYPE (`cron`), RENDER_INSTANCE_ID and RENDER_GIT_COMMIT. They do not independently prove this job's actual values or how IDs change between cron executions. Admission must remain strict until a non-scraping runtime inspection confirms these values and observable process identity. Confirm scheduled-successor/container termination semantics and no alternate manual/local/legacy discovery entrypoint. Repository Blueprint has one daily discovery service; absence of another repository declaration cannot prove absence of external operators.

## Transaction-pooler compatibility: unresolved release blocker

Candidate `app/db/session.py` requests connect/pool waits 10s, statement timeout15s, lock timeout5s and idle-transaction timeout30s. The three server settings are supplied through connection-startup `options=-c ...`. Supabase documents that session settings are not reliable across transaction pooling and that transaction mode does not support prepared statements. The engine does not explicitly disable Psycopg automatic preparation. Thus the current direct-PostgreSQL evidence is insufficient to approve a transaction-pooler route; startup option acceptance, effective settings across transactions/reconnections and prepared execution require evidence. Do not infer that these options definitely fail, or silently remove them to connect.

Ownership uses inherited OS flock/process identity and conditional durable row updates, not session advisory locks. That design does not require database session affinity, but actual conditional-write/rollback/recovery behaviour through the selected pooler remains to be tested in a disposable non-production equivalent. No advisory-lock fallback is proposed.

Smallest remaining read-only runtime check: an operator-accessible shell for this existing cron container, without starting discovery, returning ONLY service/type/instance/commit identifiers, process-identity capability, parsed URL host/port/driver/SSL mode (no username/password/query secrets), and a bounded `SELECT 1` plus `SHOW` of the three timeout settings using the actual app path. Do not print DATABASE_URL or a full environment dump. The shell failed to connect in this inspection. A SQL Editor query is not a substitute. Deliberate cancellation/lock-conflict/write tests belong in a disposable pooler-equivalent environment, not production.

If transaction pooling is confirmed, choose after that evidence: (A) narrowly adapt discovery DB handling for transaction-local bounds and disabled prepared statements, then retest; or (B) separately approve a session-mode route after connection-budget/SSL assessment and verification. Neither is implemented or a billing recommendation. Existing watchdog containment remains valuable but does not waive DB-path compatibility.

## Proposed CI, local and unexecuted

Workflow runs on PR, feature-branch push and manual dispatch after separately approved publication. Disposable GitHub-hosted Ubuntu24.04; Python3.12.3; exact pip dependency snapshot; matching Playwright Chromium; local PostgreSQL16 only. Install dependencies before entering a loopback-only network/PID/mount namespace; tests and PG run non-root under tini, with private /proc/sysfs and inherited production inputs/.env rejected before application imports. No secret references, deployment permissions, production database, signed-in browser or paid calls. Baseline fetched from repository history, no test-time external access. Namespace or dependency failure fails closed; no skipped-integration fallback.

The existing integration runner is reused unchanged. New assessment tooling explicitly lists the four accepted failures and deselected RSS test; rejects changed/new failures, errors, skips, missing required integration cases, missing five blocked-persistence cases, missing baseline cases and reductions below accepted counts. It accounts for the deliberate replacement of the old missing-health-means-success test with honest partial/failure behaviour. A green assessment means no new regression under these exceptions, NOT pytest fully green or release approval. Future fixes to the baseline exceptions require an explicit expectation update; they are not silently swallowed.

Always-upload artifacts include both XML/logs, exact tested commit, runner/workflow blobs, dependency snapshot/actual packages, Python/PostgreSQL/kernel versions, clean-tree status, private-PG logs and raw runner exit. A fresh GitHub result is required to validate hosted-runner namespace permissions, dependencies and cleanup. Action major versions are review-draft references; review/pin their approved revisions before enabling. Future CI does not reauthorize production release.

## Migration-first release proposal — NOT executed or authorised

1. **Approve exact release artifact and prerequisites first.** Application candidate remains ff0baa2; if publishing a later documentation/CI-only descendant, verify the application/migration/test/dependency tree is identical and record that descendant's SHA. Resolve database-path compatibility and runtime ownership evidence before activation. No automatic master deployment as a side effect of publishing is approved.
2. **Suspend discovery externally and prove termination.** Suspend the cron, confirm no active run/descendants, block alternate old entrypoints and record previous settings. A new-code disable switch cannot stop old code. Preserve evidence; do not force-close legacy rows based on age. Keep other pipelines unchanged, subject to migration compatibility.
3. **Approve and apply only reviewed additive schema delta.** Expected missing objects are `parent_lookup_work` and nullable `scrape_runs.progress`; preflight actual schema and stop on any additional drift. `python -m scripts.migrate_schema` is the existing generic command, not a P0-A-only migration: it also runs historical idempotent backfills and uses multiple transactions. Confirm those backfills are no-ops before approval; do NOT describe the entire command as atomic. Retain a recovery snapshot via an approved method, verify expected constraints and legacy compatibility, run `python -m scripts.verify_schema`, and verify a repeat is a no-op. Migration connection route must be separately validated; no bulk evidence repair/recovery.
4. **Deploy exact artifact inactive.** Keep scheduler suspended, ACTIVATED=0 and MODE=disabled (DISABLED=1 is another valid stop input); verify SHA, schema, browser availability and runtime IDs without scraping. All switches validate first; either disable wins; MODE=bounded alone never activates. Invalid/empty values fail closed. Check that startup does not run discovery and no alternate entrypoint bypasses admission.
5. **Separately approved Manchester smoke only.** Same existing cron identity, current-month scope, command `python -u -m scripts.run_daily_councils --council manchester --timeout-seconds 3600 --triggered-by manual`; never `--include-ai-stages`. Proposed parent settings: PARENT_ITEMS=5, PARENT_ATTEMPTS=6, PARENT_SECONDS=60; INVOCATION_SECONDS=3720 (all prefixed PROPERTYAIGENT_DISCOVERY_). Activation/temporary command/scheduler handling requires separate approval; confirm whether suspended cron permits manual execution before selecting the exact operator sequence. Do not create another service or forge runtime identifiers to work around admission.
6. **Salford only after Manchester termination is proven and evidence accepted.** Separate approved invocation replacing only council with salford; same limits initially. No overlap, no automatic fallback to all councils, no recovery run. Return to suspended/inactive after each trial.

### Budgets and evidence

Council ceiling 3600s is the previously reviewed measurement ceiling, NOT a normal target. Historical 24 September low-arrival observations were Manchester8m57s and Salford3m48s; the OOM run's Manchester8m19s is censored. These are insufficient to select a sustained production timeout or capacity. A first limited smoke can end promptly on normal completion; it need not consume the ceiling. Further lowering requires measured stage progress rather than an arbitrary 12-minute cutoff. Stockport's 60-minute timeout and repeated ~53s HTTP429 exhaustion are excluded; no retry/circuit change here.

For parent-stage start at P, council deadline C and invocation deadline I: cooperative stop `min(P+60+60, C, I)`; hard stop `min(cooperative_stop+10, C+20, I)`. Thus the full parent envelope is **130s**, not125. Council's hard backstop is C+20, never beyond I. A 3720s invocation leaves startup/reconciliation allowance around a 3600s council, but time already spent reduces available time; no deadline resets or guaranteed130s reservation near invocation end. Earlier deadlines win and reduced coverage is honestly deferred/failed. A forced stop is not NOT_FOUND, completion or successful coverage. The locked specification's earlier cleanup numbers remain disclosed historical deviations, not silently edited.

Record actual start/end/deadlines; service/instance/owner; selected council; per-stage outcomes and progress; primary fetched/committed counts; distinct eligible parent references actually attempted, suppressed duplicates, retries/cooldowns/outcomes, deferred reasons, oldest-eligible ordering and fixed-cohort progress; cgroup/process peaks; final run-health and exit; committed evidence/downstream eligibility (do not trigger paid processing); descendant/lock absence. Choose a bounded existing evidence cohort beforehand; no request for 20 first attempts/day or inference of production capacity from synthetic throughput.

Stop and leave inactive on identity mismatch, unexpected council/AI execution, schema drift, DB timeout/preparation incompatibility, unhandled failure, missing final health, unexplained stale ownership, browser/lock leak, parent/council/invocation envelope overrun, memory stop or OOM. Soft70%, stop80%, restart below60% are containment settings, with normal completion target <=70%; memory stop proves containment only. At most +5s measurement/scheduling margin for observing production termination is proposed for review, not extra work budget. Normal partial parent deferral can exit0 but must not be labelled full coverage; failure/interruption/missing terminal health is nonzero. If the DB cannot persist terminal status, retain logs and reconcile only with positive termination evidence.

After smoke, separately approved seven-cycle Manchester/Salford observation can establish sustained scoped health: no OOM/crash/leaks, stage progress under justified limits, honest partial/failure reporting, bounded backlog advancement accounting for arrivals/cooldowns/outages, and measured normal usage. This does not block unrelated AH design/benchmark preparation and does not establish all-council readiness.

### Safe rollback

First suspend external scheduling, disable new admission and confirm active processes terminate; switches alone cannot stop an already-running invocation. Preserve committed evidence, continuation reservations/results and versioned run progress. Do not drop the additive table/column or rewrite unknown/running outcomes. Older code tolerates the additive schema but ignores new safety switches and continuation; therefore **keep old discovery suspended** if reverting code. Never resume the old all-council command automatically. A later compatible bounded release may resume from retained state after positive ownership reconciliation. Database restoration is not the routine rollback because it would erase committed evidence. No rollback or release action is approved now.

## Decisions and precise remaining gates

- Accept the local CI proposal for later publication/revision pinning; first actual GitHub execution remains pending.
- Provide read-only runtime shell capability or the sanitized operator evidence above; current authenticated dashboards alone cannot answer runtime/actual DB route questions.
- Decide the smallest DB compatibility remedy only if the actual route/equivalent tests establish it is needed; application changes require new candidate validation.
- Separately approve exact release artifact, migration delta/backfill no-op evidence, suspension/inactive deployment sequence, and Manchester smoke limits/operator method. Salford follows only after termination/evidence review. None is authorised by Gate A acceptance.

Official references checked 29 September 2026:
- https://render.com/docs/cronjobs — single-service scheduling guarantee.
- https://render.com/docs/environment-variables — documented runtime identity variables.
- https://supabase.com/docs/guides/database/postgres/timeouts — session timeout scope.
- https://supabase.com/docs/guides/database/connecting-to-postgres — transaction/session limitations and connection routes.
