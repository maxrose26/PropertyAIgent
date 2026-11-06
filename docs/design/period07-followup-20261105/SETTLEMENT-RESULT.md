# Period07 committed settlement and diagnostic route assessment

Stage 4 OPEN. Current gate: identify Tameside pagination fault; failed-run settlement is now complete. Another live B test remains unauthorised.

## Committed result

On 5 November 2026 the owner authorised exactly the reviewed settlement candidate at `8f289e0eb32dab4fc1628e933dd6ede6a752b40c`. Its unchanged module and CLI bytes were verified against GitHub and loaded into the existing clean owner checkout `e191729bd9f05224932fef9903341d99d63650de` without changing that checkout or deploying the web/scraper service.

The initial fresh inspection passed and rolled back. Exactly one `settle` invocation then completed; the CLI's fresh-connection verification returned COMMITTED_STATE_VERIFIED_READ_ONLY. A second independent process verified the same committed state at **2026-11-05 14:08:42 UTC**. Its read-only verification transactions ended in ROLLBACK; that does not undo the earlier committed settlement.

Period `b-dbpilot-20261027-1102-07`; run `a3a3def1b87d411aa9b5754b4b168b12`; original failed job `job-dbm7dqh42hec73dsgahg`.

- Original OPEN marker retained verbatim in the period's failed_runs history; active marker absent.
- Receipt SHA-256: `b461d84c45aadbea3bab1960273cedcf55f75a19b967b5d71a205d587ba8fb44`.
- Tameside item SAFETY_BLOCKED / RECOVERED, fence 2, attempt_count 1, no owner, lease or checkpoint.
- Fence-1 attempt RECOVERED and closed, checkpoint absent.
- Generation 9. Global stop DAILY_INTAKE_SHARED_FAILURE remains active. Manual stop and last_hard_stop are ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP.
- Temporary storage-owner/recovery memberships: zero. Runtime sessions: zero. Dormant access and original credential-verifier hashes matched.
- Original three artifacts independently rehashed and exact inventory matched. Three requests remain COMPLETE-accounted; coverage NOT_ESTABLISHED; Manchester NOT_ATTEMPTED.
- Attempt06 retained receipt and original evidence passed the unchanged history validator, preserving UNKNOWN cause/count and Manchester NOT_ATTEMPTED.
- No uncertain acknowledgement or retry occurred. No stop clearance, runtime access reopening, deployment or intake submission occurred.

The bounded nonsecret readback is `committed-readback.json`, SHA-256 `f3b14e872821fee8d6cf56157d2a593e06493a4f4f2d91d01d28e3aacd7fe004`. Original artifact names, sizes and hashes are included there. Raw evidence bodies and credentials are not included.

Render read-only service inspection also confirmed scheduled collection remains suspended, auto-deploy disabled and start command /bin/true.

## Source diagnostic: stopped before any request

**New diagnostic council requests: 0.** No source job or intake job was submitted. The historical period07 count remains 3, not zero.

The existing source-only route does not meet this authorisation unchanged:

1. `finite_acceptance._read`, its Idox worker and `daily_intake_runtime.source_worker` admit private response retention only for 24–30 October 2026. The approved 27 October–2 November window refuses with PRIVATE_RESPONSE_SCOPE before transport.
2. `WindowBoundary` supplies a ten-request budget. `_run_five_page` has no stop-after-first-sorted-page mode: it can continue to PAGE and then REFINE. The existing calibration mode also binds the older window. There is no supported three-request diagnostic option in the inspected entry points.
3. `PrivateResponseBodies.record` writes full response bytes. It does not remove hidden session/CSRF values or session-bearing link destinations. Private file permissions do not satisfy the instruction to exclude session tokens from retained evidence.

Two local checks ran the actual reader and source-worker validation against the approved window with transport forbidden: both returned PRIVATE_RESPONSE_SCOPE; transport calls were zero and no source output was created. No guard was bypassed and no new live route was improvised.

The previous handoff identified reusable components, but its proposed diagnostic was not an executable supported route. This assessment closes that preparation gap explicitly. The live navigation cause remains UNPROVEN; there is no new observed response to justify a pagination acceptance change.

## Smallest next decision

Approve one narrow diagnostic mode in the existing source worker/reader, with an offline-tested three-physical-request ceiling including redirects, zero retries, exact RECEIVED window, FORM → SEARCH → SORT only, and unconditional stop before PAGE/REFINE. Reuse the existing credential-free child/supervisor and existing parser. Keep database access and intake registration absent and all current stops active.

Retain only the parser-relevant pagination DOM: necessary labels, allow-listed page/sort/action fields and same-origin destinations; remove session-bearing values before disk or logs. Retain the original body hash plus sanitised fixture hash and fixed refusal subcode. Verify offline that sanitisation preserves the parser decision; otherwise report evidence insufficient rather than retaining tokens. Preserve 45-second, 3,000,000-byte aggregate and 500,000-byte response ceilings.

Focused tests must prove the fourth physical request is impossible, no Next/refine dispatch occurs even when page 1 is valid, token redaction, zero database credentials, failure accounting and child cleanup. This is a small extension of the existing route, not a new recovery or collection framework. No new implementation or source execution is claimed by this report.

Recommendation: settlement GO/completed; source diagnostic BLOCKED on the above route adaptation; another live B test NO-GO. No owner-only authentication action is needed.
