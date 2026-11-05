# Period07 follow-up — REVIEW handoff

Stage 4 OPEN. Current gate: resolve Tameside pagination and supported period07 settlement. Next gate: REVIEW decides whether a further bounded live B test can be authorised. No live settlement, stop change, deployment, access reopening, council request or intake submission occurred in this follow-up.

## Baselines and retained evidence

- Scraper: `54700366bab5434a5cda30abc853e0dc6dcc5d33`, tree `95bfb2677cddfe539b8b69945d870f6c8b5eb62e`.
- Owner: `e191729bd9f05224932fef9903341d99d63650de`, tree `b4be80ce098635fc309cf7a904cd624f90e3e35f`.
- Candidate code: `8f289e0eb32dab4fc1628e933dd6ede6a752b40c`, draft PR #211, stacked on the existing owner branch. No changes to PR #207's historical commits or the deployed scraper branch.
- Period: `b-dbpilot-20261027-1102-07`; run `a3a3def1b87d411aa9b5754b4b168b12`; failed job `job-dbm7dqh42hec73dsgahg`.
- Capture audit: 7,802 bytes, SHA-256 `08171942f8a8ddc5f125d3468f7df800eef7189d0a80cc92ebf0094bd8b3bdf8`.
- Final events: 2,691 bytes, SHA-256 `4abd400c87f26ea09743ee355ec40c98ae3d157fb652012c796dcc94d8ae9e21`.
- Final result: 4,255 bytes, SHA-256 `f1c1d65333ffee46af4c8c48c964ffcf5d3429cd10a5be653f63deac1565ac8b`.
- Encrypted owner journal: ordinal 56, SHA-256 `31e7d340047e37df0d0e4382374dce5ccc939b1eb819d1213f11e238fa69fdf2`.

All three artifact hashes and their exact inventory were independently rechecked read-only. Raw production response data and credentials are not included in this PR.

## Demonstrated failure and exact evidence gap

The third request was the five-result Reference/Descending sort POST to `/online-applications/pagedSearchResults.do`. Its 42,307-byte response was HTTP 200, hash `1c04041162e7fac548d328e921cd0f555cf296bf409b46394cd9171f2e4a91d2`. Structural proof records five result rows, two pagers each showing 1–5 of 22 and each containing one Next control; page-size and sort controls match. Failure occurred at `PAGE_PARSE` on this first sorted result page, before any page-2 request or refine-search criteria readback.

`directions()` can emit the same ambiguity code for a later numbered page, an unclassified forward-page link, ambiguous selected controls, distinct requests for the same direction, or numbered navigation without explicit Next. The audit retains body hashes and structural counts, not the response HTML, individual hrefs or form controls. `original_response_availability=PRESENT` means present to the collector then; it does not mean the body is durably available now. The exact branch/control therefore remains UNPROVEN. The 22-count page makes later numbered links a plausible explanation, not a demonstrated cause.

No pagination acceptance rule was relaxed. The smallest evidenced fix is diagnostic: five fixed refusal subcodes, stage, page ordinal and response hash, with no URLs, DOM text, submitted values or credentials. The original refusal code and capture rejection remain intact.

Actual counted navigation and capture-validator tests cover a synthetic five-page/22-record result, a valid terminal page, and four distinct ambiguities. Existing equivalence, malformed destination, contradictory count, repeated page, criteria and validator tests remain passing. These fixtures do not prove the live council's layout or coverage.

## Settlement candidate

Entry point: `scripts.owner_period07_settlement`; default action `inspect`. Fixed period/run/job, execution binding, full original-marker hash, journal hash, evidence hashes and Attempt06 receipt are pinned. There is no successor, disposition, activation or source action.

Live read-only checks passed using the existing configured owner connection, ending in ROLLBACK. Exact marker hash: `ba74765f7d35eb420a12f59e3ac8207d17778892108d3529ca8808324d6167fc`. Expected retained settlement receipt hash: `b461d84c45aadbea3bab1960273cedcf55f75a19b967b5d71a205d587ba8fb44`.

Checks include owner identity and function inventory, unchanged restricted credential verifiers, dormant roles and absent sessions, storage-owner and recovery admin-only memberships, absence of storage-owner schema CREATE, exact claim/fence/expired lease/unfinished attempt/no checkpoint, generation-8 stop tuple, absence of competing work, original Attempt06 recovery/disposition and history, and three accounted requests in the retained audit/events/final result. Recovery membership was granted by `supabase_admin`, ADMIN true, INHERIT false, SET false. No grant was made during inspection. Actual future grant execution remains unproven on live; disposable PostgreSQL exercises it under a non-superuser owner.

The proposed single transaction reuses Attempt06's owner locking and cleanup and calls the unchanged `ingestion_recover_abandoned(key,1,false)`:

1. Exact Tameside item `ef5afe887f3e5162212fc33f2cf4429d5cbb19cf11bede34e2d1156b09741bc5`: CLAIMED/SOURCE_INTENT/fence1 → SAFETY_BLOCKED/RECOVERED/fence2; owner and lease NULL; reason ABANDONED_SOURCE_INTENT; next_action RECONCILE; outcome forbids replay. Checkpoint remains NULL and attempt_count remains 1.
2. Its fence-1 attempt: finished_at set, phase RECOVERED, outcome copied from recovery; checkpoint remains NULL.
3. Shared control row `repeat('0',64)`: generation 8 → 9; global_stop remains DAILY_INTAKE_SHARED_FAILURE; manual_stop and last_hard_stop become ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP. This is the existing recovery function's mandatory fencing/stop behaviour for SOURCE_INTENT, not a new guard exception.
4. The original OPEN marker is retained verbatim in `intake_periods[period07].failed_runs[run_id].original_marker`, together with FAILED_RECONCILED, three COMPLETE-accounted requests, NOT_ESTABLISHED coverage, known source/validator failures, exact navigation cause UNPROVEN, and Manchester NOT_ATTEMPTED. The active intake_run marker is removed in that same transaction.
5. Temporary recovery and storage-owner membership removed before COMMIT. Full control comparison permits only the listed changes. Evidence bodies, Attempt06 history and unrelated control state remain unchanged. No runtime access opens; neither failure stop clears.

A fresh connection independently reads committed state and permissions. Lost COMMIT acknowledgement requires `inspect`, never another `settle`. A second settlement refuses. If inspect still shows the original state, report rollback/no commit and return for a decision; do not infer permission to repeat a write.

Inactive procedure, only after separate live approval, from a verified checkout of the candidate in the configured owner environment:

```bash
python -B -m scripts.owner_period07_settlement --action inspect
# Stop unless exact binding and READY_FOR_REVIEW_NOT_AUTHORISED are returned.
PROPERTYAIGENT_OWNER_SETTLEMENT_AUTHORITY=b-dbpilot-20261027-1102-07 \
  python -B -m scripts.owner_period07_settlement --action settle
# After any uncertain response, run only the following readback:
python -B -m scripts.owner_period07_settlement --action inspect
```

Expected final status: COMMITTED_STATE_VERIFIED_READ_ONLY, the receipt hash above, generation 9 with blocking stops, no active intake marker, recovered item/attempt, unchanged archives/history and no temporary permission. This does not prepare or authorise another intake run.

## Validation

Final code tree: `e01b8b8142632c54e0fda836b56fafd4c8bde0eb`.

Hosted PostgreSQL 17.11 run [42034214419](https://github.com/maxrose26/PropertyAIgent/actions/runs/42034214419), daily-intake job `127268014014`:

- Period07 settlement/navigation: **74 passed**. Actual owner path, non-superuser PostgreSQL, rollback after recovery and before commit, exact permission restoration, evidence/history preservation, changed-state refusal and lost-acknowledgement readback.
- Targeted B readback: **31 passed**.
- Existing Attempt06 recovery/successor owner path: **72 passed**.
- Connected restricted-ledger intake with synthetic sources: **92 passed**.
- Historical fixed B inspection: **16 passed, 1 failed**, the pre-existing frozen inventory mismatch described below.

Local navigation/equivalence/B-connection regressions: **85 passed**. Hosted offline job `127268013319`: connection units **414 passed**; broad discovery **1,508 passed, 11 failed**, the same baseline timeout cases described below. E2E connection, v3 admission, PostgreSQL admission, Render fixture and screening-v3 PostgreSQL jobs passed. Broader restricted-provisioning CI was still running when this handoff was prepared; it is not required evidence for the new focused sequence.

The final candidate's live inspect returned `READY_FOR_REVIEW_NOT_AUTHORISED`, exact receipt hash above, unchanged generation-8 stops and `ROLLED_BACK`. It executed no settlement. Source module SHA-256 `81e02e12fd9a6b3ad4fe17ae422036ff31a0742cb2e54d0b5fb6c99efc7378cb` matches the inspected candidate. Scheduled collection remains suspended.

Initial disposable CI caught and corrected a candidate defect: the admin check used current_user after SET ROLE. It now checks session_user. A synthetic corrupt-evidence fixture was also corrected to preserve the table's own body/hash constraint so the candidate hash guard could be tested. Neither failure caused a live write.

The existing broader CI is not all green. Eleven timeout/continuation failures reproduce identically on the accepted owner tree and candidate (279 passed, 11 failed, one PostgreSQL-dependent test skipped in each local comparison). They concern legacy four/three-council continuation classification, not the period07 settlement or new navigation diagnostics. The historical `b-readonly.sql` inventory test also compares an old frozen proposal against the newer registrar definition; the same registrar mismatch is present on both trees. Historical SQL/hashes were preserved. Do not present this as a clean overall release.

## Smallest next decision

NO-GO for another live B test: the actual navigation control is still unknown. REVIEW can separately approve the tested settlement, without stop disposition or any successor.

For the source gap, propose one separately bound source-only diagnostic using the existing supervised Tameside reader and private-response retention hook: same 27 October–2 November 2026 RECEIVED window, maximum three requests (FORM, SEARCH, SORT), zero retries, 45 source seconds, existing 3,000,000-byte response ceiling and 500,000-byte per-response bound. Stop immediately after parsing the first sorted five-result page; never follow Next or request refine-search. Retain the private third response and bounded navigation subcode/hash so the exact link/form can be reproduced offline. No database authentication, registration, recovery, publication or intake. It must use a separate diagnostic identity, never reuse consumed period07. This proposal is not implemented as a live execution route or authorised by this handoff.

The fact it must establish is which specific returned control triggered the existing ambiguity guard, and whether multiple controls represent the same adjacent-page request or conflicting/unsupported destinations. No full intake test is needed to answer that question. A diagnostic on a later response cannot retroactively prove the discarded original DOM; any changed response remains explicitly new evidence.
