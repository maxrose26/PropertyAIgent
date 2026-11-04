# Attempt06: polling correction and recovery boundary

MASTER STAGE 4 remains OPEN. CURRENT GATE: prove collection → durable retention → deterministic screening → discoverable backlog. NEXT GATE: REVIEW accepts connected evidence. Decision: NO-GO for live intake; the authorised fresh submission remains unused.

## Preserved baseline

- Repository: maxrose26/PropertyAIgent; baseline da8959d06bea35da5104fe6638aa566952004853.
- Period: b-dbpilot-20261027-1102-06; run: f0afadd31d56467580ce61b51bbf19a3; Render job: job-dblr422jnfac73d8eaeg.
- Tameside work key: dc8ae276a9c3f697b9905adf0ec8835398009769b69e788e4fd70e13216ee6fc; authority: INGESTION_CHAIN_TAMESIDE_CAPTURE_6111B8A8125C.
- Window remains 2026-10-27 through 2026-11-02 inclusive, Tameside RECEIVED and Manchester VALIDATED. Existing request/runtime/cost limits are unchanged.

## Changes actually made

Isolated branch `fix/attempt06-poll-diagnostics-20261104`, local commits:

- 91b5ee25ce00ef60f6d6c22519f47ecaa3ececbb: polling correction, safe diagnostics, interrupted accounting, focused regressions.
- b802db026f9219278c142eb65ed2869f717d598b: reject unexpected denial payloads from diagnostics.

Only `daily_intake_runtime.py`, `intake_budget.py` and `test_daily_intake_runtime.py` changed for implementation. The existing dirty simplification worktree was preserved. No deployment, live database write, role change, stop change, new collection job, credential creation or GitHub publication occurred.

The baseline polls SQL from a background thread. `DatabaseBudget.guarded()` uses `hard_deadline()`, which refuses that thread with HARD_DEADLINE_MAIN_THREAD_ONLY. A local reproduction establishes this defect. It does not recover the historical exception: Attempt06's exact original cause remains UNKNOWN.

The candidate keeps SQL and its signal deadline on the main thread, and runs the existing owned-process supervisor independently. A slow database poll therefore does not block the supervisor's memory/time/process checks. Poll failures emit only fixed categories/codes and validated SQLSTATE, never raw messages, SQL, parameters or credentials. An observed shared-stop change is distinguished from a polling error, expiry or binding change.

After source launch intent, request totals remain null/UNKNOWN until complete source accounting is accepted. The numeric `requests_accounted` field is explicitly partial when status is UNKNOWN. Unknown accounting blocks another council. Historical evidence is not rewritten.

## Validation and limits

- Seven focused local polling/accounting cases passed on the final code candidate.
- Sixteen existing daily-intake and budget tests passed.
- `git diff --check` passed.
- Real restricted PostgreSQL delayed-source regression added for both councils; the existing attended-stop test now checks the genuine-stop diagnostic and unknown request total.
- PostgreSQL 17 and native owned-process integration tests have NOT passed on this candidate. GPT Work's process namespace does not expose child PIDs at matching `/proc/<pid>` paths; the native supervisor correctly refused the local smoke attempt and killed its child. No guard was weakened. The passing polling unit tests use a synthetic supervisor and the real deadline guard.
- Hosted CI was not started. Automatic approval review rejected pushing this branch to the existing GitHub remote, citing lack of explicit authorisation to publish potentially private code. A subsequent read-only remote branch check returned no branch. No alternate upload or push was attempted.

## Connected evidence actually inspected

The existing Render job logs were read, with no new job. At 2026-11-04T22:32:12.410936583Z both restricted roles reported qualification MATCH and closed qualification connections. At 22:32:41.497838418Z the job reported STOP_RECONCILE_NO_RETRY, CLOSED, INVALIDATED, NOT_REQUESTED. Only three log entries exist in the bounded job query; none retains the original poll exception.

Reused the completed 2026-11-04T23:21:33.131286Z database readback without rerunning it. It records Tameside CLAIMED / SOURCE_INTENT, fence 1, one unfinished attempt, expired lease, no checkpoint/capture archive, and no Manchester item under the exact revision. Actual Tameside requests remain UNKNOWN. The archived usage.requests=0 is not a recovered actual count.

The two final evidence hashes were independently verified in that readback:

- result-before-publication.json: 3386dfb045fe64cd149faea835a0b377b7d25e3733eb53e31fd6687644de1e11
- events-before-publication.json: 8a23b2641ce84002f7c726aa9de6681570b7d12ce8f874fc639910cf03ee0294

A separate narrowed SELECT-only query ran once at 2026-11-04T23:43:38.062498Z in the signed-in project zcikcfgpblzuzpanpdqd. It used BEGIN READ ONLY, 15-second statement/2-second lock/30-second idle timeouts and ended ROLLBACK. It returned booleans and bounded shared-state observations, not whole JSON or secrets:

- Exact `intake_run.id`, period, day and publication path match; marker remains OPEN.
- Exact period capture mapping contains only Tameside's expected key: Manchester was not registered in this run.
- Policy and retained grant execution bindings match revision da8959d..., workflow hash 5b87c6cbef2944fa05468314fc6daefc19b785644b04e04d1ff382b0596cadea and manifest hash 6e223d11ad74799688a9c18d3b245d3d2908abc4f806dc5507eb5c5ccab2c77a. Grant run matches and expiry is zero.
- Full shared stop tuple matches generation 6, global_stop={reason: DAILY_INTAKE_SHARED_FAILURE}, manual_stop=DAILY_INTAKE_SHARED_FAILURE, last_hard_stop=DAILY_INTAKE_SHARED_FAILURE.
- Worker/effect logins disabled; zero worker/effect/application/recovery sessions.
- Current SQL Editor session has neither owner USAGE nor SET; neither recovery USAGE nor recovery-function EXECUTE. No temporary permission was acquired by this work.

Render service crn-d9sv93vavr4c73f98rb0 was independently read: suspended, start command /bin/true, branch master, auto-deploy off. GitHub publication settings were not changed; installation suspension was not freshly reverified. Previously inaccessible historical role settings remain restoration-unproven; this read does not reconstruct them.

## Why existing operations cannot reach the finish line

`ingestion_recover_abandoned(key,1,false)` can settle the abandoned item, subject to existing capability checks. It sets SAFETY_BLOCKED / RECOVERED, fence 2, clears owner/lease, records ABANDONED_SOURCE_INTENT and replay=false, next_action RECONCILE; it finishes attempt fence 1 as RECOVERED. It raises generation 6 → 7 and manual/last stop ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP, preserving the existing global stop. It leaves the OPEN intake marker. Current SQL Editor access cannot execute it.

`intake_finish` cannot truthfully settle this run: it requires both councils and verified COMPLETE/DEFERRED receipts, matching retained final evidence, and a live eligible worker context. The final status here is STOP_RECONCILE_NO_RETRY. Its success/INCOMPLETE rules must not change.

Owner `no_hazards`, period registration and runtime startup reject an unresolved marker. Existing `stop_disposition` is hard-bound to the old generation-5 tuple. An OPEN→FAILED label still blocks continuation. Neither replay, fabricated VERIFIED status nor merely clearing stops is an acceptable solution.

## Smallest proposed decision — not implemented or authorised yet

Approve a narrow extension of the existing owner reconciliation/disposition path, not another collection route:

1. Within one bounded transaction, lock/recheck exact run, period, execution binding, both evidence hashes, Tameside key/authority/claim/fence/expired lease/unfinished attempt, absent checkpoints/captures, absent Manchester mapping/item, generation-6 stop tuple, dormant roles, absent sessions and invalidated grants. Verify installed function identity and capabilities. Refuse any drift.
2. Reuse the existing abandoned-item recovery unchanged. Because current session lacks its capability, any temporary recovery membership is an explicit additional permission decision: exact existing recovery role, no ADMIN option, no worker access, revoke before COMMIT, and restore the original membership set. If existing owner authority cannot grant it, stop rather than acquire wider rights.
3. Preserve the complete original marker plus bounded terminal failure/reconciliation receipt under `outcome.intake_periods[period].failed_runs[run_id]` on the zero-key control row, then retire only the active `outcome.intake_run` pointer. Receipt records item recovery, expected pre/post stop tuples, hashes, UNKNOWN actual requests and original cause, Manchester NOT_ATTEMPTED, no coverage and no replay authority. This is a new privileged lifecycle operation requiring REVIEW; it is not an existing supported command. Original final evidence, policies, consumed-day mapping and grants remain intact.
4. Keep generation 7 and all stops active after settlement. Only after candidate PostgreSQL/native validation and committed reconciliation/closure readback, extend the existing owner stop-disposition path for the exact resulting generation-7 failure tuple. Record its disposition in the receipt, clear only the acknowledged global/manual failure stops, and retain generation 7 and last_hard_stop. This is an explicit stop-disposition decision, not automatic stop clearance to pass a test. Other/new stops refuse.

This avoids changing any worker guard or `intake_finish`. A fresh uniquely bound period/run would use the existing registration, fixed window, limits and still-unused live-run authorisation only after the active marker is legitimately retired and the exact stop is disposed. Tameside recovery is a prerequisite to retiring the active marker, and can be atomic with it. Settlement alone does not prove collection or screening.

Affected proposed paths: `intake_owner.py`, `intake_owner_client.py`, and focused owner-operation PostgreSQL tests. Preserve normal worker SQL, intake_finish, database evidence format and collection routing. Required tests: exact successful retirement/recovery, every identity/hash/fence/stop/capability mismatch refusing atomically, no Manchester fabrication, untouched evidence/unknown counts, permission cleanup, stop drift refusal, failed-run history surviving successor registration, and lost acknowledgement without a second write.

On uncertain COMMIT acknowledgement, perform only readback: compare the exact receipt, original marker archive, work fence/state, finished attempt, stop tuple and original privileges. Exact expected state establishes commit; exact original state plus absence of the original transaction establishes non-commit; mixed/inaccessible state remains unresolved. Never blindly repeat the mutation.

## Outcome and single approval request

Qualification: historical connected PASS. Collection: Tameside interrupted/UNKNOWN, Manchester NOT_ATTEMPTED. Capture retention: no Attempt06 capture; final failure evidence hash-verified. Screening: no Attempt06 completed screening evidence. Backlog: no new Attempt06 discoverable-backlog proof. Access closure: independently verified dormant roles/zero sessions; scraper restoration: independently verified suspended /bin/true/master/auto-deploy off. No new deployment/job ID exists.

Approve the bounded reconciliation and exact stop-disposition extension above, including publishing the local polling candidate and subsequent scoped changes to maxrose26/PropertyAIgent for the existing PostgreSQL CI. This is the smallest decision that addresses the lifecycle boundary and permits connected validation; no owner machine or secret transfer is currently required. Stage 4 remains OPEN and end-to-end acceptance remains NOT ESTABLISHED.

Automatic approval review rejected `git push` to maxrose26/PropertyAIgent because it considered code publication insufficiently explicit. That rejection was respected; no workaround publication occurred.
