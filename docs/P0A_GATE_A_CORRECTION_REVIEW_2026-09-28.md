# P0-A correction and verification handoff — Gate A OPEN

## Exact reviewed/tested state

- Branch: `feature/p0a-bounded-discovery`.
- Exact candidate tested: `c88c7248094ac8334bc4f5a5bcb02224abc56593`.
- Working tree was clean when the matched verification started. The subsequent report commit changes documentation/evidence only, including correcting the handoff interpreter version to the actual Python 3.12.14. No application/test/runner code differs from the candidate.
- Baseline: `301a56b3cde781f37e5f5bb0ffaded6537d5ca14` (preserved documentation branch); application baseline `6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a`.
- Reviewed specification 019 is byte-identical: SHA-256 `c007e2b2912ae5d8817142c32fdf35e0000f72d4fa127d5c83e32e6ef10970f8`.
- Local commits only. No push, merge, production migration, deployment, live scrape, paid call or production configuration change.

## Focused corrections

`app/pipeline/discovery_watchdog.py` adds a small independent subprocess, not a new ownership/queue framework. `scripts/run_daily_councils.py` starts elapsed accounting before bootstrap/reconciliation and starts the watchdog before ownership/DB work. It registers each council process group before callbacks. The absolute invocation deadline caps every council and parent-stage backstop. Normal council supervision retains graceful cleanup; if persistence stalls, the watchdog can kill the registered group and supervisor without waiting for DB or stdout callbacks. A council backstop allows 20 seconds for cleanup; parent-envelope backstop allows 10 seconds, both capped by the invocation deadline.

The watchdog does not own or inherit the discovery lock. The recorded supervisor and inherited child lock contract remain unchanged. On hard deadline the process fails, remaining councils are unattempted/deferred, and stderr reports that final database status is unverified. It does not fabricate persisted failure status or reclaim running rows by age. Already committed evidence/continuation survives; positive termination reconciliation remains required. Losing the supervisor pipe also triggers cleanup of registered groups. Real Chromium descendant/no-zombie evidence remains pending; passing the synthetic lock test is not sufficient to assert it.

`app/db/session.py` and the admitted child bootstrap request discovery-only PostgreSQL bounds: connect/pool wait 10 seconds, statement 15 seconds, lock wait 5 seconds, idle transaction 30 seconds, TCP keepalive settings. The independent watchdog handles stalls outside driver guarantees. No unrelated application engine is reconfigured. Actual PostgreSQL/pooler compatibility remains unverified.

`app/pipeline/lookup_outcome.py`, `app/scrapers/arcus_portal.py` and `app/scrapers/idox_portal.py` remove SIGALRM cancellation. A context-local budget bounds native navigation/action waits and retry delays, checks before/after operations, and preserves strict identity/outcome semantics. Budget exhaustion remains transient, with Retry-After information retained. Primary Stockport retry/circuit behaviour is unchanged: parent deadline context is absent on primary scraping. No SQL optimisation was added.

Tests add real subprocess blocking-persistence containment and lock release, cooperative timeout propagation, DB bound configuration, PostgreSQL statement timeout/recovery and actual Chromium blocked-persistence/descendant cleanup. Existing page-lifetime, continuation, migration and identity regressions remain intact. The handoff adds a dependency snapshot and isolated exact-commit runner, without running an installation here.

## Specification deviations and limits

- The new independent watchdog is the focused implementation of the requested whole-invocation correction. If its hard backstop fires during stalled persistence, the entire invocation fails instead of attempting later councils against the same unresponsive DB. This containment trade-off is explicit; no later council is counted as covered.
- Cooperative cancellation replaces the earlier signal deviation. Immediate browser protocol operations (for example page content/evaluation) and requests body reads do not have a claimed hard per-call total deadline. The independent stage/council envelope contains a hung driver/read. Actual Chromium safety is still unverified.
- Specification-compatible `DISCOVERY_MODE` is retained; the additional `ACTIVATED` release gate and `DISABLED` alias remain. Validate all values first; either disable wins; production requires activation plus strict identity. Invalid/empty values fail before DB. Operating instructions define exact accepted values. Production remains inactive by default.
- Council timeout remains the existing configurable CLI ceiling, not a new environment alias. Trial limits remain hypotheses pending approval and representative evidence.
- No advisory-lock fallback, weakened PID admission, broad stage continuation, new schema beyond approved ParentLookupWork/progress, or wider roadmap change.

## Actual offline evidence

Both aggregate runs used Python 3.12.14, the same installed package snapshot and the offline guard; `pip check` reported no broken requirements. Baseline and candidate share the same explicitly deselected legacy renderer-RSS test.

| Run | Passed | Failed | Skipped | Deselected | Duration |
|---|---:|---:|---:|---:|---:|
| Candidate c88c724 | 338 | 6 | 6 | 1 | 44.28 s |
| Matched baseline 301a56b | 281 | 5 | 0 | 1 | 23.68 s |

The five matching failures are the existing intelligence-processing tests (four missing-key paths and one SDK SOCKS dependency path). They remain failures; this is not a fully passing affected suite. The sixth candidate failure is `test_actual_supervisor_death_surviving_child_holds_lock`: the spawned supervisor cannot observe its own process start identity, fails strict admission, and never writes the child-ready marker. It is **not baseline-equivalent** and has not been resolved by relaxing admission.

All five deterministic blocked-persistence subprocess variants passed (bootstrap, reconciliation, on-start callback, streamed persistence callback and final-status stall). They use a two-second watchdog deadline, require completion under five seconds, verify SIGKILL failure and honest unavailable-status reporting, and verify child-held file-lock release for child scenarios. Bootstrap/reconciliation cases inject a stall inside the watchdog scope; callback cases exercise the real council subprocess helper. This is actual subprocess containment evidence, not a real PostgreSQL stall result or Chromium evidence.

PostgreSQL: **one test skipped**, no server available. Its prepared checks cover migration idempotence, constraints, conditional owner transitions, transaction rollback, interrupted reservation recovery, statement deadline and subsequent connection use. SQLite/offline equivalents passed but are not substituted for PostgreSQL.

Chromium: **five tests skipped**, matching binary unavailable. These cover navigation deadline and subsequent work, recycled document-page/evidence refresh, supervised browser-descendant cleanup, supervisor-death lock behaviour and blocked persistence with browser descendants. No actual Chromium pass is claimed. Installation blockers were not retried.

`git diff --check` and handoff shell syntax validation passed. Machine-readable results: `docs/reports/p0a-gate-a-correction-results.json`. Earlier evidence is retained historically, not presented as fresh execution.

## Runtime handoff and access needed

Only the current restricted execution tool is available; no authorised alternate Linux executor is connected. There is no postgres/initdb/pg_ctl, container runtime or usable Chromium binary here, and PID visibility is unreliable.

**One action needed:** provide an authorised non-production Linux executor with PostgreSQL, matching Playwright Chromium, loopback-only test networking, process groups, flock and reliable `/proc`/zombie reaping, or run `verification/p0a_gate_a.sh` there and return its logs/XML. The full handoff supplies dependencies, commands, exact-commit checks and database isolation safeguards. No production credentials or secrets are needed in chat. Do not retry the blocked current-runtime installation methods.

## Remaining release gates and bounded rollout

Gate A stays open until the PostgreSQL/Chromium checks actually execute and pass, the additional ownership failure passes on reliable PID visibility, and any remaining candidate-specific failures are resolved. Then verify actual runtime identifiers, sole discovery entrypoint and scheduler successor guarantees; verify DB timeout options on the real connection path without activating work; obtain approval for the additive migration, exact release state, trial budgets and smoke scope.

Migration-first proposal remains: suspend and verify discovery terminal; apply/verify the approved additive migration before new consumers; verify deployed SHA and restricted command while inactive; then separately approve Manchester followed by Salford, current-month only, no AI or historical recovery. Proposed initial parent bounds remain five references, six attempts and a 60-second start budget, with the configurable 3600-second council trial ceiling requiring approval. The implementation’s parent hard envelope is start budget + 60 seconds plus up to 10 seconds watchdog cleanup, capped by the invocation deadline; this supersedes earlier draft wording of a 125-second envelope. Duration, memory, stage coverage, distinct attempts, deferral reasons, throughput and fixed-cohort progress must be observed; synthetic throughput is not production capacity. Seven subsequent daily cycles assess sustained health separately from smoke acceptance and do not block unrelated AH design/benchmark preparation.

Manchester/Salford remain a **limited candidate**, not release-ready today and not proof of all-council readiness. Stockport remains excluded. Separate proposal only: typed exhausted primary 429 handling, respect Retry-After, avoid a final pointless sleep, stop further primary requests after exhaustion and report primary failure honestly; verify exact request counts, waits, no next-record request and replay implications before any Stockport trial. No retry/circuit change is implemented here.

Safe rollback: suspend the scheduler and positively verify all discovery processes terminal before reverting. Older code may ignore new switches, so never restore it under an active schedule. Prefer a forward rollback retaining bounds/admission; otherwise keep discovery suspended. Preserve the additive table/progress column, committed evidence and health records; no destructive downgrade, bulk replay or age-only reservation reset. Resume only an approved bounded state.

These changes reduce duplicate work and contain exposure; they do not establish the Manchester OOM root cause, resolve Supabase egress, or correct AH data.
