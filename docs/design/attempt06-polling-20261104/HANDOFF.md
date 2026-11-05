# Attempt06 owner recovery and bounded successor — 5 November 2026

MASTER STAGE 4: OPEN. CURRENT GATE: collection → durable retention → deterministic screening → discoverable backlog. NEXT GATE: REVIEW accepts connected evidence; stage advancement remains the owner's decision.

## Recommendation and boundary

GO for review of the implemented narrow owner path and its disposable PostgreSQL proof. Live recovery, stop disposition, deployment and intake remain ON HOLD. No live SQL, provider mutation, collection, new credential or intake submission was performed in this task. Synthetic collection proves orchestration and durable database results, not council availability, Render connectivity or Greater Manchester coverage.

Draft PR: https://github.com/maxrose26/PropertyAIgent/pull/207 ; branch `review/attempt06-recovery-20261104`.
Reviewed baseline `b4b74e588baae75b44a697f6b2c6cd05cb489f74`, documented at `adfedc8d24cf9f019ce51ed26ffc7c9505a1f744`.
Final code revision `54700366bab5434a5cda30abc853e0dc6dcc5d33`, tree `95bfb2677cddfe539b8b69945d870f6c8b5eb62e`, identical to local code commit `24acb03b551517d70fb071e75551b41a95b2bbe4`. GitHub connector commits have different metadata from local commits; tree equality is verified.
Earlier implementation revisions in this task: `aec3ad92342fe0302a179e13b971e7ba9eff14ab`, `1d55c6ef31a2e751046093b4c2ab4074e280bbcb`, `7d0609374b58523557e0206b920d6e3fb7b9abff`, `1726f81788d06c14373e8622c5feb967c683592b`.

Outgoing diff and branch additions were inspected for credentials, raw production evidence and unrelated material. Test passwords and bodies are synthetic. Existing dirty simplification work was preserved. Publication used the existing authorised GitHub integration; no automatic approval rejection occurred. Historical SQL definitions and hashes, worker guards and intake_finish remain unchanged. The prior disposable-only prototype and its fixture stop-clearance tests were replaced by the actual owner operation tests; their history remains in Git.

## Retained historical facts

Attempt06 period `b-dbpilot-20261027-1102-06`; run `f0afadd31d56467580ce61b51bbf19a3`; job `job-dblr422jnfac73d8eaeg`.
Tameside key `dc8ae276a9c3f697b9905adf0ec8835398009769b69e788e4fd70e13216ee6fc`; authority `INGESTION_CHAIN_TAMESIDE_CAPTURE_6111B8A8125C`.
Saved readbacks: `2026-11-04T23:21:33.131286Z` and narrowed identity readback `2026-11-04T23:43:38.062498Z`. They were reused, not rerun.

Tameside is historically CLAIMED/SOURCE_INTENT, fence1, expired lease, one unfinished attempt, no checkpoint or capture archive. Actual requests and the discarded polling exception remain UNKNOWN. Manchester remains NOT_ATTEMPTED. Archived usage.requests=0 does not establish an actual count. Final evidence records STOP_RECONCILE_NO_RETRY / SOURCE_STOP_OR_ACCESS_CHANGED.

Original execution binding:

- revision `da8959d06bea35da5104fe6638aa566952004853`
- workflow SHA-256 `5b87c6cbef2944fa05468314fc6daefc19b785644b04e04d1ff382b0596cadea`
- manifest SHA-256 `6e223d11ad74799688a9c18d3b245d3d2908abc4f806dc5507eb5c5ccab2c77a`
- final/result-before-publication.json SHA-256 `3386dfb045fe64cd149faea835a0b377b7d25e3733eb53e31fd6687644de1e11`
- final/events-before-publication.json SHA-256 `8a23b2641ce84002f7c726aa9de6681570b7d12ce8f874fc639910cf03ee0294`

The narrowed readback established exact intake_run.id, period, day, publication path, policy/grant execution binding and Tameside-only day map. Access closure and scraper restoration were previously independently verified. These are dated facts, not fresh live qualification. Inaccessible prior role settings remain restoration-unproven. GitHub installation suspension has not been freshly checked here.

The inherited polling/accounting fixes (original commits `91b5ee25ce00ef60f6d6c22519f47ecaa3ececbb` and `b802db026f9219278c142eb65ed2869f717d598b`) keep SQL polling on the main thread, distinguish allowlisted polling errors from genuine stops, and retain incomplete accounting as null/UNKNOWN. The reproduced main-thread deadline defect does not establish Attempt06's original exception.

## Exact operation and mutation scope

Entry point: `python -m scripts.owner_attempt06 --action ACTION`, using the existing configured owner connection, verify-full TLS, encrypted journal, saved stable credentials and bounded envelopes. No new credential store or manual receipt-hash copying: the command derives and checks the receipt binding in memory from the existing journal and read-only control state.

Recovery A (`settle`) is one transaction. It verifies the exact original marker and publication path; original policy, window, day map and execution binding; invalidated exact authority; two exact evidence names/body hashes; exact Tameside task/contract/scope/revision/claim/fence/expired lease; one unfinished attempt; absent Manchester and other uncertain work; unused successor; dormant credentials/sessions; expected function inventory and retained historical cleanup. Ledger/evidence locks prevent concurrent drift. Missing capability or any changed state refuses, without provisioning new permanent authority.

| Row or permission | Committed effect of A |
|---|---|
| Exact Tameside work item | Unchanged `ingestion_recover_abandoned(key,1,false)` sets SAFETY_BLOCKED/RECOVERED, fence2, owner/lease null, reason ABANDONED_SOURCE_INTENT, next_action RECONCILE, no-replay outcome. Checkpoint remains null. |
| Exact fence1 attempt | RECOVERED, finished_at set, no-replay abandonment outcome. |
| Zero-key control outcome | Generation6→7; manual_stop and last_hard_stop become ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP; global `{reason: DAILY_INTAKE_SHARED_FAILURE}` remains. |
| Same control, original period | Add `intake_periods[Attempt06].failed_runs[run_id]` containing the full original OPEN marker, identity, evidence hashes, FAILED_RECONCILED, requests null/UNKNOWN, historical cause UNKNOWN, Manchester NOT_ATTEMPTED, successor07 and no replay authority; remove only active intake_run. Original policy, grants and day map remain. |
| Temporary permissions | Existing ADMIN-only capability must already permit exact temporary membership. Recovery INHERIT-only/no-SET/no-ADMIN and owner SET-only grants are removed before COMMIT; complete membership inventory must equal its starting state. |

Item settlement is atomic with archival, not deferred. The existing no_hazards guard would reject the abandoned SOURCE_INTENT; generation6→7 is the unchanged recovery contract, not optional bookkeeping. Historical evidence bytes are never rewritten. No Manchester item is manufactured.

Disposition B (`dispose`) is a separate transaction after committed readback of A. It requires the exact retained receipt SHA, recovered item/attempt, exact complete generation7 tuple, dormant access, no hazards, absent active marker, unused successor07 and no previous disposition. It changes only global_stop and manual_stop to null and appends `intake_periods[Attempt06].failure_disposition` with receipt SHA, before/after tuple and successor. Generation7 and last_hard_stop=ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP remain. Full ledger projection and memberships are checked. A new/unrelated global/manual stop or altered receipt refuses; there is no generic clear-all action.

Successor admission is restricted to unused `b-dbpilot-20261027-1102-07`, database evidence, the exact receipt/disposition and accepted generation7 tuple. Existing period issuer, prepare_activation, activate, restricted runtime, finalisation and close perform their normal checks. Other periods retain the original owner stop contract. The owner journal function gains only the exact07 namespace through the existing migration path; original06 encrypted rows survive byte-for-byte and remain decryptable. Temporary schema permission is revoked. No worker function or intake_finish is relaxed.

Affected paths: `attempt06_recovery.py`; narrow branches in `intake_owner.py`, `intake_owner_operations.py`, `owner_pilot.py`, `owner_pilot_continuation.py`, `database_evidence.py`, `scripts/owner_pilot_job.py`; thin `scripts/owner_attempt06.py`; focused tests and existing PostgreSQL workflow.

## Validation

Final code run https://github.com/maxrose26/PropertyAIgent/actions/runs/41943067508 , daily-intake job126968418759:

- 31 targeted B checks PASS (3.69s).
- 72 owner-path/owner-operation checks PASS (13.39s), including the full actual sequence and independent finalisation.
- 92 connected intake checks PASS (104.00s); three older fixture-only recovery tests were replaced by the dedicated owner suite, explaining 95→92.
- Archived B inspection:16 PASS,1 inherited failure below. Overall job/workflow is red, not an acceptance-suite failure.
- Artifact https://github.com/maxrose26/PropertyAIgent/actions/runs/41943067508/artifacts/13377346599 ; SHA-256 `a58ab99aa543d493dc7dca83ab4e32c7673aa29a72150028fe7f9c52cd97b1b3`.
- Locally:51 owner/unit checks PASS; diff whitespace check PASS. Secret-pattern review found only explicitly disposable fixture database URLs. No SQL archive files changed.

Earlier revision1726f817 run41942515154 also passed31+72+92, before the final encrypted-journal and independent-finalisation assertions. On final54700366, PostgreSQL admission, v3 admission, Render fixture, reusable-batch native and AH web jobs pass. The longer e2e-connection, screening-v3 and restricted-provisioning jobs were still running at report publication; no result is claimed for those final-head jobs. Their prior1726 equivalents passed except the known restricted legacy three-council continuation failure.

The actual non-superuser owner sequence is recover → new-connection readback → dispose → new-connection readback → issue_period → prepare_activation/activate → restricted runtime → independent finalisation → close. It uses real disposable PostgreSQL17, production SQL/guards and existing owner functions. No fixture UPDATE clears the stops. Tests assert original history survives registration and runtime completion, both council captures and independent source/report hash readback, completed screening, authority invalidation, disabled runtime logins, absent sessions and restored memberships.

Fault cases exercise failure immediately before COMMIT (entire recovery/disposition and permissions roll back) and lost acknowledgement after COMMIT (separate read-only reconciliation, no second write). Changed id, stop, generation, fence, lease, attempt, evidence, successor, grant, Manchester state and receipt all refuse. The encrypted prior journal survives namespace extension and decrypts unchanged. Unit coverage checks exact07 startup/qualification routing and that CLI uncertainty does not invoke a follow-up write or expose an exception.

Sources and evidence bodies are synthetic. The Tameside fixture uses the existing qualified five-request reader and supervisor; Manchester uses the existing Arcus supervisor fixture. Transport/resource context adapters do not prove Render capacity. The runtime still executes real restricted ledger admission, retention, screening, backlog read and finalisation. No claim of live collection, live cleanup, provider restoration, deployment or GM-wide readiness follows from this proof.

### Red checks against the same baseline

Baseline run https://github.com/maxrose26/PropertyAIgent/actions/runs/41938546990 at b4b74e already contains these failures:

- Fixed B read-only inspection: 16 pass, exact candidate inventory fails because archived SQL lacks current ingestion_register_bolton_exception hash `1d05b3f4476a8ad2a14aa083eb15396c9d157265dc19254df738777673cd995d`. Baseline reproduction also confirms this mismatch. Do not rewrite historical SQL or hashes to turn this green.
- Offline continuation: the same eleven failed test node IDs in baseline job126953125442 and new job126966584174, covering legacy finite-manifest/source-profile/three-council contained timeout continuation. One Tameside timeout case was additionally reproduced locally at exact b4 tree. No change to those continuation guards was made.
- Restricted provisioning: baseline job126953125466 reaches the fixed three-council fixture and fails expected three results after the legacy contained-failure continuation stops at two. The preceding provisioning checks pass. This is the same legacy continuation family, separate from the fixed two-council daily-intake path.

Two additional workflow reds are accounted for separately:

- AH run41943067503 job126968418733:1 failed/1867 passed, frozen-v6-oracle import-boundary test. Exact baseline run41938546925 job126953125429 has the same failing node and1867 passes. This is an unrelated historical oracle-import inventory, not owner recovery/intake execution.
- Reusable batch run41943067514 job126968418604:1 failed/826 passed, `test_stage4_direct_registration.py::test_exact_cohort_and_shared_bytes`. Independently reproduced locally on exact b4 tree: current request_boundary.py digest `decc2b92bd4cfd51763dc0dba5a98b36981e6547c55a26e824f174152d47ab7c` differs from the test's frozen expected `188198827c2192dec97f75a373fa3f3bbd066cd5f245ebad43e576a7b6e90057`. Those direct-reference files and hashes are unchanged here and outside this owner path.

These are not a green-repository claim. They do not invalidate the explicit two-council owner acceptance evidence, which runs independently and passes, but remain release-review limitations. One owner operation test double incorrectly rejected the existing stable_verifiers keyword on b4; its signature was corrected, and all43 owner operation unit tests pass. Initial new fixture failures (outer supervisor fields, then wrong Tameside pagination profile) were fixed by reusing the actual qualified supervisor/five-request fixture, without weakening production guards.

## Executable live procedure for REVIEW — inactive

Run only after separate live authorisation, from the existing configured owner checkout/environment at the reviewed code revision. Do not execute in a generic SQL Editor: its previously observed permissions were insufficient. Existing owner ADMIN-only role relationships, stable encrypted Attempt06 journal and configured database/Render/source-release integration are preconditions. If any are missing, stop and report that exact capability; do not create credentials or broader grants.

The configured source release must identify the reviewed successor code/artifact and its workflow/manifest hashes. Existing preflight verifies this against the artifact; do not reuse the historical da8959d execution binding for new code. Keep cron and GitHub publication suspended. Fixed window 2026-10-27 through 2026-11-02 inclusive; Tameside RECEIVED; Manchester VALIDATED; one new run only. Existing aggregate limits remain 90 requests, 23,971,520 source bytes,120 source seconds,150 supervised seconds,960 wall seconds,2080 driver statements,96 connection attempts,8MiB returned bytes,80 GitHub calls,2MiB export and existing closure reserves. No spending or instance-size expansion is implied.

Commands below use the configured owner's Python environment. Each command is a separate deliberate action, not a blindly rerunnable batch:

```bash
export PROPERTYAIGENT_OWNER_PILOT_AUTHORITY=b-dbpilot-20261027-1102-07
python -m scripts.owner_attempt06 --action inspect-binding
python -m scripts.owner_attempt06 --action settle
python -m scripts.owner_attempt06 --action read-recovery
python -m scripts.owner_attempt06 --action dispose
python -m scripts.owner_attempt06 --action read-disposition
```

STOP after any nonzero exit or unexpected result. `settle` and `dispose` each commit once and then open a separate connection for read-only verification ending ROLLBACK. Expected status is COMMITTED_STATE_VERIFIED_READ_ONLY with the correct phase and retry=false. Independent commands repeat only the readback. After A expect exact retained receipt, no active marker, blocked recovered item/fence2, finished attempt, unchanged evidence, generation7/blocking stops, baseline memberships/no sessions. After B expect only reviewed two stops null, generation7/laststop unchanged, exact disposition, no marker or successor registration and dormant access.

If acknowledgement is lost, run only the corresponding `read-recovery` or `read-disposition`. A verified committed result settles uncertainty without repeating the mutation. A refusal is not proof of rollback; retain the private journal and inspect the exact state before deciding anything further. CLI emits bounded STOP_RECONCILE_NO_RETRY and does not chain a retry. Recovery and disposition deliberately refuse already-consumed state.

Only with separate deployment/submission authority, continue through the existing pilot path:

```bash
python -m scripts.owner_attempt06 --action prepare-successor
python -m scripts.owner_attempt06 --action verify-successor
```

Preparation includes a separate exact journal-namespace transaction, existing build/deployment and zero-source startup qualification job; it is NOT read-only. It must preserve the original encrypted journal, return the service to suspension and pass RELEASE_BINDING_VERIFIED_READ_ONLY before run. No preparation/deployment was executed for this task. An uncertain preparation must be reconciled through `status` and the saved existing intents/provider readback; do not repeat it.

The existing owner path requires a fresh Dashboard observation of inherited environment groups/secret boundaries that its API cannot independently establish. Preserve that guard. After the owner has actually verified the existing required boundary, the existing UI may supply its observation timestamp; the shell equivalent, on that same configured owner host, is:

```bash
python -m scripts.owner_attempt06 --action run-successor --owner-checked-at "$(date +%s)"
python -m scripts.owner_attempt06 --action status
```

Do not supply a current timestamp without making the observation. Run registers the single unused period, activates the existing restricted roles, submits once through the journalled provider operation, then performs finalisation and access/service restoration. Each existing operation retains its own transaction/intent boundary; this is not one cross-provider transaction. Success requires CLOSED / VERIFIED_RETAINED_AND_SCREENED, independent database source/report hashes, both councils' truthful coverage/screening/backlog, provider job terminal evidence, access closed and scraper configuration restored. Any uncertainty stops submission: inspect `status` and the existing provider/job journal, never rerun `run-successor` to discover whether it ran. Supported cleanup after reconciliation is `python -m scripts.owner_attempt06 --action close-successor`; it is a write/cleanup operation and also needs live authorisation. Expiry alone is not closure.

REVIEW decision: accept or reject the narrowly matched two-stop disposition and exact07 owner extension for a later live window. This task does not approve that window. Historical cause/count remain UNKNOWN, Manchester historical status remains NOT_ATTEMPTED, and source-polling/provider behaviour still needs one separately authorised live acceptance run after the recovery gate is accepted. No further recovery architecture is proposed.
