# Attempt06 polling and recovery validation — 5 November 2026

MASTER STAGE 4: OPEN. CURRENT GATE: reliable collection → durable retention → deterministic screening → discoverable backlog. NEXT GATE: REVIEW accepts connected evidence; owner alone advances the stage.

This report supersedes the earlier investigation-only handoff. Review branch: `review/attempt06-recovery-20261104`; draft PR https://github.com/maxrose26/PropertyAIgent/pull/207. No live recovery, stop clearance, deployment, access reopening or intake submission was performed for this validation task.

## Recommendation and boundary

GO for review of the polling/accounting correction and disposable recovery mechanics. NO-GO for executing the prototype live or claiming complete owner-to-fresh-run admission. The smallest remaining design decision is an exact, receipt-bound generation-7 extension of the existing owner reconciliation/disposition and activation path, including one unused period. Keep the existing failure stops active until that disposition is explicitly approved; do not lower the generation or bypass a guard.

The prototype intentionally refuses every destination except the disposable PostgreSQL database. It is not a production recovery command. Existing SQL Editor access was previously verified to lack owner/recovery capability; disposable ADMIN permission does not establish live authority.

## Revisions and publication

Baseline: `da8959d06bea35da5104fe6638aa566952004853`.
Original polling commits: `91b5ee25ce00ef60f6d6c22519f47ecaa3ececbb`, `b802db026f9219278c142eb65ed2869f717d598b`.
Published combined polling/prototype revision: `c237e74fa5a24d3fa7aee643bd881ba2ed6d5b24`; fixture lock-permission correction: `38ecfc9bb9bb1f2870c4434aa0a1d2fc2cc9691f`; stronger evidence/generation assertions: `5a06fba5b34bc5aad7fcb3d0b98115f7232b5d32`.
Final code/test revision: `b4b74e588baae75b44a697f6b2c6cd05cb489f74`, tree `51f86e010d2ff642a327a99b0c46d4aba547130b`, identical to local commit `0476904` tree. GitHub connector publication uses different commit metadata from local commits; original SHAs are not claimed as remote ancestors.

Outgoing changes and history were inspected: only the two runtime/accounting modules, one disposable prototype, the focused test file and this sanitised handoff. No credentials or raw production rows/logs were published. Secret-looking strings in tests are synthetic leak-detection fixtures. Existing dirty simplification work was preserved. Direct git transport lacked credentials; the already authorised GitHub integration published the branch. No automatic approval rejection occurred for this authorised publication.

## Preserved Attempt06 evidence

Period `b-dbpilot-20261027-1102-06`; run `f0afadd31d56467580ce61b51bbf19a3`; Render job `job-dblr422jnfac73d8eaeg`.
Tameside key `dc8ae276a9c3f697b9905adf0ec8835398009769b69e788e4fd70e13216ee6fc`; authority `INGESTION_CHAIN_TAMESIDE_CAPTURE_6111B8A8125C`.
Window remains 27 October–2 November 2026 inclusive: Tameside RECEIVED, Manchester VALIDATED. Existing request/runtime/cost limits are unchanged.

Saved readback at `2026-11-04T23:21:33.131286Z` records CLAIMED / SOURCE_INTENT, fence 1, one unfinished attempt, expired lease, no checkpoint or linked capture archive. Tameside actual request count and historical polling cause remain UNKNOWN. Manchester remains NOT_ATTEMPTED. Archived usage.requests=0 does not establish actual requests.

Hash-verified final evidence records STOP_RECONCILE_NO_RETRY / SOURCE_STOP_OR_ACCESS_CHANGED:

- `final/result-before-publication.json`: `3386dfb045fe64cd149faea835a0b377b7d25e3733eb53e31fd6687644de1e11`.
- `final/events-before-publication.json`: `8a23b2641ce84002f7c726aa9de6681570b7d12ce8f874fc639910cf03ee0294`.

Saved narrowed readback at `2026-11-04T23:43:38.062498Z` established exact `intake_run.id`, period, day/publication path, Tameside-only mapping, policy/grant execution binding and invalidated grant. Execution revision is the baseline above, workflow hash `5b87c6cbef2944fa05468314fc6daefc19b785644b04e04d1ff382b0596cadea`, manifest hash `6e223d11ad74799688a9c18d3b245d3d2908abc4f806dc5507eb5c5ccab2c77a`. Shared tuple: generation 6; global `{reason: DAILY_INTAKE_SHARED_FAILURE}`; manual and last hard stop `DAILY_INTAKE_SHARED_FAILURE`.

That readback also established both runtime logins disabled and zero pipeline sessions, and no owner USAGE/SET or recovery USAGE/EXECUTE for the SQL Editor identity. Previously verified Render restoration: suspended, `/bin/true`, master, auto-deploy off. No live SQL was rerun for this task. These are dated evidence, not a fresh pre-write qualification. Inaccessible historical role settings remain restoration-unproven; installation suspension was not freshly checked.

## Polling/accounting change

The original background SQL polling thread calls a main-thread-only signal deadline. A focused test reproduces HARD_DEADLINE_MAIN_THREAD_ONLY. This demonstrates a defect, not Attempt06's discarded exception.

`daily_intake_runtime.py` keeps bounded SQL polling on the main thread while the existing source supervisor runs independently, retaining process/memory/time enforcement during a slow SQL poll. Diagnostics use allowlisted categories/codes and validated SQLSTATE; raw exceptions, SQL, parameters and credentials are excluded. Genuine shared-stop change is distinguishable from polling error.

`intake_budget.py` marks source accounting incomplete before launch. Until accepted complete metrics arrive, actual requests are null/UNKNOWN; requests_accounted is explicitly partial. Unknown accounting blocks continuation to another council. Existing worker guards and intake_finish were not changed.

## Recovery mechanics and exact mutation set

Entry point: `verification.ingestion_storage.failed_run_prototype.retire`; disposable only. It locks/rechecks the supplied complete control/item snapshots, exact OPEN marker id/period, generation-6 stop tuple, CLAIMED/SOURCE_INTENT/fence1/no-checkpoint item, single unfinished fence1 attempt, and exactly two evidence names/hashes/body hashes. Existing recovery itself rejects an unexpired lease. It takes temporary recovery-role membership without ADMIN or SET, invokes unchanged abandoned-item recovery with `(key,1,false)`, then revokes the membership before COMMIT and compares the complete membership inventory with its baseline.

One transaction changes:

| Row | Changes |
|---|---|
| Tameside work item | state SAFETY_BLOCKED; phase RECOVERED; fence 2; owner/lease NULL; reason ABANDONED_SOURCE_INTENT; next_action RECONCILE; outcome records no source/write replay authority. Existing identity/checkpoint/attempt_count are retained. |
| Its fence-1 attempt | phase RECOVERED; finished_at recorded; matching no-replay abandonment outcome. |
| Zero-key control outcome | generation 6→7; manual_stop and last_hard_stop become ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP; global DAILY_INTAKE_SHARED_FAILURE preserved. Add `intake_periods[period].failed_runs[run_id]`, then remove active `intake_run`. |
| Temporary membership | Grant and revoke within the transaction; final membership inventory must equal initial inventory. |

The retained receipt contains the complete original marker (still OPEN as historical evidence), FAILED_RECONCILED disposition, actual_requests null, request_count_status UNKNOWN, historical_cause UNKNOWN, Manchester NOT_ATTEMPTED, original evidence hashes, recovered key/fence and replay=false. FAILED_RECONCILED describes disposition, never verified collection. Final evidence bodies, period policy, day map and retained grants are not rewritten. No Manchester row is created by recovery.

Tameside settlement is necessary before retiring the pointer: `no_hazards` separately rejects SOURCE_INTENT. It can and should be in the same transaction. The generation increment is required by unchanged recovery semantics for abandoned SOURCE_INTENT, even when access closure is independently known; suppressing it would change the safety contract.

Prototype limitations: synthetic identities and evidence exercise transactional mechanics, not complete production attestation. The future owner wrapper must also enforce the exact real authority/revision/day mapping, full execution binding, dormant roles, no pipeline sessions, invalidated grants, absent Manchester/checkpoints/capture archives, installed-function inventory and permissible owner authority. It needs the existing bounded owner connection/idle timeout and secure credential handling. No live wrapper or new privilege installation was implemented.

## Generation-7 admission finding

After recovery, SQL runtime admission requires disposition of BOTH `global_stop` and `manual_stop` to null. Keep generation=7 and last_hard_stop=ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP. Match the complete expected tuple and retained receipt; any new/unrelated stop must refuse. Do not use a generic clear-all operation.

Existing `intake_owner.stop_disposition` accepts only its old generation-5 CONSUMED_SALFORD_GLOBAL_STOP tuple. Existing `validate_binding`, `activate` and `intake_owner_operations.validate_policy` bind ACCEPTED_STOP to generation 5; database pilot periods are restricted to 01–06. A test holds all accepted stop fields constant except generation=7 and confirms OWNER_STOP_BINDING. Therefore even correct disposition of the two generation-7 stops does not make existing owner activation usable. Rewriting generation to 5, reusing Attempt06, or bypassing equality would be unsafe and was not done.

Disposable tests separately exercise SQL registration and the existing worker command after fixture-only exact stop disposition, using a new period and unique run. This is not proof of owner activation. The proposed production extension belongs in the existing `intake_owner.py`, `intake_owner_operations.py` and owner client wiring: exact reconciled receipt, exact generation-7 tuple, and one unused period. Keep no_hazards, worker guards and intake_finish intact.

## Hosted validation

All sources are synthetic; PostgreSQL 17 is real and hosted in the repository's existing CI. No council traffic, Render job or live database was used.

- Seven focused local polling/accounting cases and sixteen existing intake/budget cases passed; diff whitespace validation passed.
- Run `41937560583`, job `126949776605`, revision `38ecfc9...`: 31 targeted B checks passed; all 95 connected intake tests passed. Includes delayed Tameside and Manchester, genuine stop, unknown accounting, recovery rollback, permission restoration, lost acknowledgement and retained history. Archived artifact `13374059258`, SHA-256 `a85d23e1506886252e42af0476ad91fb1ac15550c0741cfedc58362aac62afaf`.
- Run `41937853727`, job `126950777668`, revision `5a06fba...`: 31 targeted checks passed; 94 intake tests passed including stronger recovery/evidence/generation assertions. One existing rolling-window fixture crossed midnight: its registration failed at `2026-11-05T00:00:00.039Z` with INTAKE_ROLLING_SCOPE_OR_CONSUMED. SQL compares scope dates against clock_timestamp; no guard was changed to suppress this refusal. Artifact `13373789147`, SHA-256 `942891c88e24adca16b9d58db614541e06102f695934125a197a65422c449258`.
- Final code revision `b4b74e588baae75b44a697f6b2c6cd05cb489f74`: run `41938546990`, job `126953125398`, 31 targeted B checks PASS; all 95 connected intake tests PASS in 133.90 seconds at `2026-11-05T00:07:37.8139935Z`. This includes successor runtime execution through RETAINED_AND_SCREENED and VERIFIED, new run identity, surviving original history, generation7 retained, CLOSED/INVALIDATED cleanup and unchanged memberships, in both ordinary-commit and lost-ack cases. Fixed B inspection: 16 PASS, one inherited inventory-hash failure. Artifact `13375785439`, SHA-256 `0e0f4889f88ce5ab5ac7a85d9fbcac0862de5a53a21131789bc3772ce0662fbc`: https://github.com/maxrose26/PropertyAIgent/actions/runs/41938546990/artifacts/13375785439 . The final handoff-only commit does not alter tested code.

The overall workflow is not green: an archived B-readback expectation lacks the current registrar hash (reproduced on untouched baseline), and eleven offline continuation cases fail in unchanged code. One exact Tameside timeout case was independently reproduced on baseline da8959d. Do not claim all eleven were individually baseline-reproduced. Archived evidence/hash expectations and continuation semantics were not modified merely to produce green CI.

## Proposed live sequence — inactive, no execution authorised

There is no supported complete live command yet. Do NOT run the disposable module against production or invoke item recovery alone as a substitute for atomic retirement.

Transaction A, after the narrow owner wrapper is reviewed: exact owner readback and locks; original marker/evidence/identity/stop verification; temporary existing recovery capability if legitimately grantable; unchanged SQL call below; append history and retire active pointer; revoke temporary permission; exact postconditions; COMMIT. The only existing mutation call within that proposed transaction is:

```sql
-- INACTIVE FRAGMENT ONLY: requires the reviewed atomic owner wrapper.
SELECT public.ingestion_recover_abandoned(
 'dc8ae276a9c3f697b9905adf0ec8835398009769b69e788e4fd70e13216ee6fc',
 1, false);
```

Before A: requalify the exact saved identity/binding/hash/fence/lease/attempt/stop/capability and dormant-session evidence above. After A: independently read retained original marker/receipt, active-marker absence, SAFETY_BLOCKED/RECOVERED fence2, finished fence1 attempt, unchanged evidence, exact generation7 tuple and baseline privileges. Stops remain blocking.

Transaction B is a separate, presently unsupported owner disposition: require A's committed receipt, exact two failure stops, unchanged generation7/laststop, dormant access and no hazards; record disposition and null only those global/manual stops, retain generation7 and history, remove temporary owner capability. No executable command is supplied because the existing command refuses this state. A general SQL UPDATE would bypass the missing guard and is not recommended.

Before a later activation: review exact generation7 accepted binding, one unused period and the candidate execution revision; verify the preserved fixed window/limits and closed access. After registration: independent new period/run binding and surviving Attempt06 history. This task authorises none of those live transactions or submissions.

Lost acknowledgement: do not repeat a mutation. Use a new read-only connection to compare exact original versus expected committed marker/history/item/attempt/stop/evidence/privilege state. Confirm the original transaction is no longer active before concluding non-commit. Exact final state establishes commit; exact initial state and absent original transaction establishes non-commit. Mixed, inaccessible or changed state remains unresolved. Disposable lost-ack testing suppresses the COMMIT response and proves independent readback, without a second retirement call.

## REVIEW decision and outcomes

Accept or reject the smallest receipt-bound generation7 owner extension and one unused period; do not approve generic stop clearance. The prototype provides evidence for that decision but is not a deployable recovery mechanism. No owner credential relay or Ubuntu action is needed for this handoff.

Historical qualification and closure are verified by saved evidence. Attempt06 collection is interrupted/UNKNOWN for Tameside and NOT_ATTEMPTED for Manchester; no capture-retention, screening or new backlog success is established. Failure evidence is retained and hash-verified. Disposable success does not establish council connectivity, live collection, live restoration or Greater Manchester readiness. Stage4 remains OPEN for REVIEW.
