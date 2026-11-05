# Period08 partial settlement and Manchester boundary — 5 November 2026

MASTER STAGE 4 OPEN. Current gate: preserve accepted Tameside results, reconcile Manchester's abandoned claim and identify its first-request failure. Next gate: REVIEW of a bounded Manchester live verification proposal.

**Recommendation:** GO for REVIEW of the exact inactive settlement below; NO-GO for claiming Manchester coverage or launching another intake through the unchanged owner path. No live settlement, stop change, deployment, access reopening, council request or intake submission was performed in this work. Period08 remains consumed. No owner action is required to maintain containment.

## Baseline and revisions

- Prior handoff: `d66c3cc5bd43afbab822521e4d6fca7146255b1c`; existing PR211 branch `stage4/period07-followup-20261105`.
- Final implementation and tests: `98eaff0636a0efbdec8e9ca73f4a40c6a720a9c0`.
- Period: `b-dbpilot-20261027-1102-08`; run `768e1bd059474281ae9dc5113db42a99`; consumed job `job-dbmacl5g1s2s73civi60`.
- Executed scraper remains `3adb65d06d0492d3b8f9b798e49e3be20699b082`, tree `62b685ac7a2e826ad1f14bc4bb8ba98e42fe15eb`; Render artifact `dep-dbma8cg8v5cc73e1enqg`. No source-branch movement or web deployment.
- New owner entry point: `scripts.owner_period08_settlement`, default action `inspect`. It reuses Attempt06 locks, privilege cleanup and existing `ingestion_recover_abandoned`, with fixed08 guards; no new SQL recovery function, table, role, journal namespace or recovery framework.
- Diagnostic improvement: `verification/direct_reference/instrumented_probe.py`. Tests: `tests/test_manchester_browser_boundary.py`, `tests/test_period08_settlement_pg.py`. Existing disposable PostgreSQL CI runs the focused checks first.

## Demonstrated boundary; historical cause remains UNKNOWN

The hash-verified Manchester audit records one accounted request, zero responses, zero redirects, zero navigations, one browser page, no listing stage, no segments and no UI posts. Browser/process cleanup completed with no survivors or supervisor limit hit. The worker reported `BROWSER_Error`; the capture validator correctly refused `SOURCE_SAFETY`.

The audited code path places this at initial browser navigation, before listing enumeration. This is a boundary diagnosis, not proof of DNS failure, TLS failure, server outage, bot blocking or a pagination defect. The exception message was discarded by the original outer catch; retained provider logs contain no additional cause. The historical cause cannot be reconstructed from these artifacts and remains UNKNOWN. Manchester's one accounted request is preserved, not reset to zero; Tameside's eight requests and aggregate nine remain COMPLETE accounting.

The smallest evidence-backed change retains `BROWSER_BOUNDARY_V1`: a fixed operation stage, allowlisted exception class and allowlisted Chromium `net::ERR_*` code. Unrecognised or conflicting codes return UNKNOWN. No exception message, URL, request ID, cookies, headers or tokens are added. The original failure code, safety flags, SOURCE_SAFETY refusal, request charging, limits and retry behaviour are unchanged. The first failing boundary survives cleanup exceptions.

Offline tests call the real probe through its request handler and V2 navigation budget with a synthetic Playwright transport. DNS/reset/timeout failures still produce one accounted request, no response, closed context/browser and SOURCE_SAFETY. They now expose bounded diagnostic fields. Sentinel URLs/tokens are absent from output. This proves the diagnostic, not the historical network cause or present council connectivity.

## Live read-only reconciliation

Final candidate `98eaff…` returned `READY_FOR_REVIEW_NOT_AUTHORISED`, `retry=false`, `ROLLED_BACK`. Its expected recovery receipt SHA256 is:

`838d00b6b6a87dba856027bf5a4e60852d0f3ae3688db3e5baae4f35d0b1f24f`

The exact active marker matched `intake_run.id`, period, OPEN state, day and publication path. Marker SHA256:

`0e3885f35230d37750cab20685b75962a614714bdec89717f0718fe8ce869347`

Manchester key `a22bac9985d0141d82a4adceaba2354eb3808280413bf7c3aad44d34de8515ad` matches the fixed authority, revision, VALIDATED scope and contract; CLAIMED/SOURCE_INTENT, fence1, attempt_count1, expired lease, checkpoint absent. Its sole fence1 attempt is unfinished with no checkpoint.

Tameside key `cfdd58f7cd0358819f4af28db7e09a74bf02ae34a1497d4f092102f9b23bfbc2` remains COMPLETE/FINISHED with its linked capture, 24 completed screenings and five completed metadata batches. The candidate pins the exact completed Tameside rows and attempts, not merely their counts:

`959cc7c96a9fcd90446472da56e2209cacedbbef4fa3ea441d82d215fcf62f09`

The accepted 24-record discoverable backlog evidence is retained. Disposable validation below exercises the actual backlog reader before and after settlement and checks equality, including current-rule and provenance validation.

The candidate verified current owner identity, fixed function inventory, admin-only baseline memberships, dormant stable runtime credentials, absent sessions, original cleanup state, exact Attempt06 and period07 history/disposition, closed authorities, fixed execution binding and the closed encrypted journal. Journal remains ordinal56, SHA256 `6cd68c0f6fc43bfda8b884eb08ae9dc873e24e95ca10d4626d53da22af8d6d4f`. No journal write occurred.

Fresh independent database/provider readback at **2026-11-05 16:38:04 UTC** confirmed both runtime logins disabled, memberships0, sessions0, stable verifiers MATCH and temporary owner/schema CREATE absent. Scraper suspended; configuration/environment exactly match the retained baseline; 74 deployments and20 jobs all terminal, still only the original startup and intake jobs since preparation. Provider mutations0. The intake marker remains OPEN; owner workflow CLOSED denotes access closure, not successful intake.

All four exact period/run evidence rows were independently reread; raw bytes remained private and each recomputed hash matched:

| Name | Bytes | SHA256 |
|---|---:|---|
| capture-1/source.json |71413|4691339a26f8bd4e86ea6df92e6730bcd964304753fe2ce4760e69685a993fd3|
| capture-2/source.json |5514|d21c771f96138af731d05445b45e1a155c26d1306a7419a488c21feb559d3698|
| final/events-before-publication.json |3504|8fa7b51bbeb9a7f113b8b641908397e0c3e5509c699125e95826ffe4b271f2d3|
| final/result-before-publication.json |4336|03db3bcdfc8c3a4e2fdbc901bb1525c55d7932f9d878da3501af45826e6c7051|

## Proposed settlement: exact single transaction, NOT executed

Prerequisites are the identities and hashes above, exact generation10 stop tuple, expired fence1 Manchester claim/unfinished attempt/no checkpoint, dormant runtime access and sessions, unchanged inventories/permissions, accepted Tameside fingerprint and prior histories. Any drift refuses. Table locks serialize the operation; identity/state/evidence are rechecked under the existing locks before mutation.

Only these persistent rows/fields change:

1. Manchester work item: state SAFETY_BLOCKED, phase RECOVERED, fence2; owner/lease cleared; reason ABANDONED_SOURCE_INTENT, next_action RECONCILE; outcome records that source/write replay is not authorised. Checkpoint remains NULL, attempt_count remains1.
2. Its fence1 attempt: phase RECOVERED, finished_at set and recovery outcome recorded; checkpoint remains NULL. No second attempt or source work is created.
3. Shared control outcome: archive the original OPEN marker and exact failed-run receipt at `intake_periods[period08].failed_runs[run08]`, then retire the active `intake_run` marker. The receipt explicitly records partial Tameside success, eight Tameside/one Manchester requests, Manchester coverage NOT_ESTABLISHED and cause UNKNOWN, original evidence and protected-work hash. It does not call intake_finish or label this run VERIFIED.
4. Existing abandoned recovery changes hard_stop_generation **10→11**, manual_stop and last_hard_stop to **ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP**. Global stop remains exactly `{"reason":"DAILY_INTAKE_SHARED_FAILURE"}`. This generation advance is the existing SOURCE_INTENT recovery guard, not a discretionary stop clearance; bypassing it would change the supported recovery semantics.

Temporary recovery membership and owner SET permission are removed before COMMIT; the original memberships must match. No schema CREATE is introduced. Every other work item/attempt must hash identically across the transaction. Original artifacts and prior periods are untouched. The receipt's persistent Tameside fingerprint does not freeze future unrelated registrations.

Inactive command, only after explicit live settlement approval, in the existing authenticated owner Web Shell:

```bash
cd /tmp/propertyaigent-settlement08-cb69c174 &&
test "$(git rev-parse HEAD)" = 98eaff0636a0efbdec8e9ca73f4a40c6a720a9c0 &&
PROPERTYAIGENT_OWNER_SETTLEMENT_AUTHORITY=b-dbpilot-20261027-1102-08 \
python -B -m scripts.owner_period08_settlement --action settle
```

The directory name reflects its first checkout; its verified HEAD is98eaff. The command uses the existing protected database/journal and performs a fresh independent readback after acknowledged commit. Expected result: `COMMITTED_STATE_VERIFIED_READ_ONLY`, the exact receipt hash above, generation11 and active global/manual recovery stops, Manchester fence2/closed attempt/no checkpoint, unchanged Tameside fingerprint and no temporary permissions.

For any lost/uncertain acknowledgement, **do not repeat settle**. On a fresh connection run only:

```bash
python -B -m scripts.owner_period08_settlement --action inspect
```

A matching committed receipt/state settles the acknowledgement question. An unexpected or mixed state refuses and requires reconciliation; no blind write retry. A failure before commit rolls back the complete recovery and archive operation.

## Focused validation

Local focused checks:46 passed (new browser boundary, existing instrumented probe and unchanged period08 owner units). No local PostgreSQL server was used or claimed.

Hosted PostgreSQL17 run42066338817/job127381325207 on a0d08b164edc636e4ad59cbe0e3689d15dfdac28 passed25 partial-settlement/browser cases,34 existing period08 continuation checks,98 period07/navigation checks,31 targeted readbacks,72 Attempt06 owner-path checks and92 connected-intake checks. The new fixture uses the actual owner sequence and runtime to retain24 synthetic Tameside listings, complete24 screenings/five metadata batches and then refuse Manchester SOURCE_SAFETY. Actual paginated backlog results, all other work rows/attempts, historical controls and raw evidence remain unchanged through settlement. Failure-before-commit/after-recovery/before-cleanup roll back; a lost commit acknowledgement is resolved by independent readback; repeat recovery refuses. An unrelated later row does not invalidate the retained receipt.

Final fingerprint precondition98eaff passed live read-only inspection; its additional completed-content-drift PostgreSQL case is pending validation. GitHub run42068074570 failed at startup with no jobs; the failed-job rerun API returned403 “This workflow run cannot be retried.” This is not a test result. The final candidate must not be called fully validated until the replacement CI observation below is completed.

FINAL_CI_RESULT_PENDING

Overall CI is not green: the earlier complete run reproduced the already documented frozen B-readonly inventory mismatch (16 pass/1 fail; actual registration hash1d05b3f4476a8ad2a14aa083eb15396c9d157265dc19254df738777673cd995d). Historical hashes were preserved. Other baseline red suites are not represented as newly passing.

Earlier candidate CI attempts exposed only fixture construction issues: missing source profile, attempting to create a synthetic zero-result success shape, omitting failure-audit prearchive/events, and trying to corrupt an evidence body without its database-enforced checksum. These were fixed in test setup; production completeness, evidence checks and SOURCE_SAFETY were not weakened. Negative recovery cases start from a successful preflight and require a Denied result, not an arbitrary exception.

## Manchester-only successor assessment and smallest next approval

The existing source worker and cross-run backlog reader can address Manchester alone, but the current supported PostgreSQL pilot owner path cannot admit/independently finish a Manchester-only period unchanged:

- `intake_policy.py`, intake_period POSTGRES_PILOT_V1 branch requires exactly two councils (`INTAKE_DATABASE_PILOT_BINDING`).
- `intake_owner_operations.validate_policy` requires the exact two-council COUNCILS map; owner preparation builds that map.
- `intake_owner.finalisation` requires exactly Tameside and Manchester roots (`INDEPENDENT_COUNCILS`).
- Owner/scraper entrypoint and journal namespaces admit reviewed periods only through08. Consumed08 cannot be reused.

The generic intake_finish checks and database evidence finish guard already verify all registered councils and their same-run archives; they need not be weakened. A future narrow one-council successor would need an explicitly reviewed fixed identity/release/receipt, a specific single-council registration policy and matching owner finalisation, namespace/admission updates and disposable proof. Do not silently bypass those guards or attach the old Tameside root to a new run: same-run archive identity correctly prevents that.

Recommend preserving accepted Tameside08 and reconciling a future independently verified Manchester-only result in the REVIEW handoff and existing cross-run backlog reader. Preserve separate run IDs, dates, source/record hashes, rule identities and outcome provenance. Do not retroactively mark08 VERIFIED or recollect Tameside merely to satisfy a hardcoded owner assumption. This remains a narrow two-council pilot, not GM-wide acceptance.

**Smallest next live scope:** approve the exact settlement above and, separately, one isolated Manchester initial-navigation diagnostic after its narrow mode/transport limits are tested offline. Use the existing Render source-worker route, fixed27 October–2 November2026 VALIDATED context, at most **one physically dispatched HTTP request**, zero retries, no redirect following, no subresource/form/pagination dispatch, stop after the first main-document response or browser failure; navigation≤25s, total process≤45s, existing≤20MiB and memory ceilings. Keep runtime database access dormant, all intake stops active, cron suspended and no intake job. Retain only fixed stage/network error, HTTP status if received, physical request accounting and verified process/provider cleanup. No raw page, session data or token retention.

This would distinguish currently reproducible DNS/TLS/connect/reset/timeout failures from an actual HTTP response. A successful response would establish current first-request connectivity, not the historical cause, listing traversal, applied criteria or Manchester coverage. Any unrecognised browser code remains UNKNOWN. Additional requests or a full Manchester verification still require their own reviewed scope. The single-request mode and its isolated live execution are proposed, not claimed implemented or run here.

No stop clearance, new grants, production deployment, runtime access reopening, source-branch change, council request, replay or submission occurred. Period08 remains consumed. Stage4 remains OPEN for REVIEW.
