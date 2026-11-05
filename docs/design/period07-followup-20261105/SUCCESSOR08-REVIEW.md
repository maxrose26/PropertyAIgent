# One successor B test — preparation for REVIEW

Master Stage 4 OPEN. Current gate: prepare one fresh bounded test after the accepted Tameside fix. Next gate: REVIEW approves the receipt-bound successor path, then assesses connected B evidence. **NO-GO for immediate execution; GO for the narrow continuation proposal below.** No production deployment, configuration update, stop change, runtime opening, council request or submission was performed in this preparation.

## Proven identity and release

Accepted scraper code: `56a8a420ae21f60633dc2b8eea4c2f61ef5659a1`; accepted evidence handoff: `2a7d17aa3de6eddc6e24a04cfb65f9dfd7196336`; PR #211. These remain distinct from the future owner-extension revision.

The five proposed scraper release fields, computed from the exact Git tree (not the documentation head), are:

```json
{
  "execution_binding": {
    "revision": "56a8a420ae21f60633dc2b8eea4c2f61ef5659a1",
    "workflow_sha256": "1fa3e58f6ccfe47a4ff5b6b6d8d4aa08b458e08cfa3a3b66741b3b1a75d07aa4",
    "manifest_sha256": "b82b6c4c3a8390422d8f5a1a98a2e489ce2ef5104e2386560af945c7a3d998d9"
  },
  "tree": "a27d1f7970fe719a7d542f35da83d2f78455ffdb",
  "branch": "prep/b-timing-pg17-current-20261103"
}
```

Canonical execution-binding SHA-256: `9652d6a6eb0fed7709e026422e3bf362956bf5152287b8fa266fa377c5e75737`. Manifest calculation used the existing `daily_intake_runtime.BOUND_FILES` and canonical digest format. Local accepted-code tree equals the GitHub tree above. Source branch remains `54700366bab5434a5cda30abc853e0dc6dcc5d33`; GitHub comparison reports ahead 12, behind 0. Compared files concern owner readiness/settlement, parser diagnostic/fix, associated tests, workflow and sanitised evidence. No unrelated change identified. No branch update performed.

Proposed successor: `b-dbpilot-20261027-1102-08`, max_runs=1. Its deterministic owner-journal run key is `c87a2fb29f7043cbef53c8470cd30732`. This is NOT the intake run ID: the actual intake runtime creates a UUID at execution and must bind/read it back, not substitute this owner key.

## Fresh read-only evidence

5 November 2026 **14:45:54.841616 UTC**, using the existing owner checkout `e191729bd9f05224932fef9903341d99d63650de`, exact tracked-clean assertion and the reviewed period07 validator:

- Period08 absent from registered periods; zero matching work items; zero evidence or owner-journal rows; no active intake marker. This is an observation, not a reservation: recheck under lock before mutation.
- Period07 receipt `b461d84c45aadbea3bab1960273cedcf55f75a19b967b5d71a205d587ba8fb44` verified; original archived marker and all three original artifact hashes verified.
- Period07 Tameside SAFETY_BLOCKED / RECOVERED, fence2, attempt_count1, no owner, lease or checkpoint. Fence1 attempt RECOVERED and closed, no checkpoint. Three accounted requests, coverage NOT_ESTABLISHED, Manchester NOT_ATTEMPTED preserved. Historical navigation cause remains UNPROVEN; the separate diagnostic is not substituted into historical evidence.
- Attempt06 retained history/disposition still verified; historical request count and cause UNKNOWN, Manchester NOT_ATTEMPTED.
- Generation9; global_stop={reason: DAILY_INTAKE_SHARED_FAILURE}; manual_stop=last_hard_stop=ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP. Stable credentials dormant; runtime sessions0; temporary memberships0. Readback ROLLED_BACK.

At **14:48:01.640123 UTC**, another read-only inspection confirmed owner journal function exactly matches ATTEMPT07_OWNER_SQL, SHA-256 `e11e137a81c027f36d02541c44e5d511b60bbfef01794211f97b53e8b57d40b7`; owner ingestion_storage_owner, SECURITY DEFINER, search_path=pg_catalog. **It does not admit period08_owner.** Transaction ROLLED_BACK.

Provider GET checks confirmed scraper suspended, configuration and environment exactly equal the period07 saved baseline, complete terminal-only job/deployment inventories, latest job `job-dbm7dqh42hec73dsgahg`, latest deployment `dep-dbm702rbc2fs738gfuv0`. Auto-deploy remains off. Configured source release still binds 54700366 / tree95bfb2677cddfe539b8b69945d870f6c8b5eb62e, workflow e5289d43dbd05f2ffa051529c4feeb6aa32fb719c621de00df3638e077bf78e4, manifest482e137a9a62fdd1007ee351845a4fc2c0825693dfc3472217c2ac8d4c3b74fc. Secrets were compared in memory and not exported.

## Exact missing capability and smallest proposal

Clearing stops alone is insufficient. `scripts.owner_attempt06` fixes successor07; `attempt06_recovery` binds the Attempt06 receipt and generation7; `Pilot.prepare_continuation` selects the Attempt06 predecessor only for07 and otherwise falls back to a different historical predecessor. `intake_owner.accepted_stop` falls back to generation5 for08. `owner_pilot_continuation.migrate_owner_namespace` and the installed owner-state function have no08 namespace. Do not monkey-patch constants, reuse07's journal or call the old disposal against generation9.

Extend these EXISTING paths for exactly period07 -> period08, with fixed receipt, predecessor journal hash/ordinal, successor and release binding. No new recovery framework or repeat settlement. Reuse period07_settlement's history/evidence checks, existing transaction locks, full-ledger preservation checks, temporary SET permission cleanup, encrypted Journal, Pilot build/startup/run/cleanup. Keep intake_finish and worker guards intact. Owner-side exact inventory validation must recognise the one new journal definition; keep historical hashes intact. Preserve scraper revision56a8 independently; if implementation changes scraper-bound files in the deployed scraper checkout, recompute and review that new release instead of claiming this binding still applies.

The journal namespace migration is a separate guarded transaction through the existing migration path. Change ONLY the existing function's period allow-list by adding `'b-dbpilot-20261027-1102-08_owner'`. Offline comparison confirms this single addition would change its body SHA-256 to `551a7cf34367ea509fdff95dd51bb4e0da0b7347a20cab8c009a372f596c4948`. This is a proposed definition, not an installed or PostgreSQL-tested migration. Keep owner, ACL, search_path, SECURITY DEFINER, deterministic run check, ciphertext/history ceilings, advisory exclusion and compare-and-swap unchanged. Any temporary owner membership/schema CREATE privilege must be removed before COMMIT with original ACL equality checked. No permanent grant is proposed.

The proposed disposition transaction changes exactly one control row, `public.ingestion_work_items.key=repeat('0',64)`, and only its outcome JSON:

- global_stop: `{reason: DAILY_INTAKE_SHARED_FAILURE}` -> JSON null.
- manual_stop: `ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP` -> JSON null.
- Add `intake_periods[period07].failure_disposition`, recording the exact period07 receipt hash, successor08, accepted release binding and exact before/after stop tuples.
- Preserve hard_stop_generation=9, last_hard_stop=ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP, all other control fields/stops, both histories, original artifacts, work items and attempts. Do not recover the item again or advance generation.

Preconditions: exact archived period07 marker/run/job/evidence and receipt; predecessor encrypted journal ordinal56/hash31e7d340047e37df0d0e4382374dce5ccc939b1eb819d1213f11e238fa69fdf2; valid closure/restoration; exact recovered item/attempt; no checkpoint; exact generation9 tuple; no existing disposition, active marker, active authority, competing operation or successor rows; exact owner/function/ACL baseline; dormant stable logins and no sessions; exact successor release. Lock and revalidate before writing. Changed/unrelated state refuses without clearing anything.

Independent readback must validate the complete disposition and receipt, unchanged generation/last_hard_stop/history/evidence, no temporary permission and no unexpected ledger change. Lost acknowledgement stops progression: inspect on a fresh connection. Exact committed state -> continue; exact pre-state -> report not committed; mixed/changed state -> refuse. Never repeat a write or submission to discover whether it happened.

## Ordering and validation before live approval

The existing build calls Pilot.preflight, which requires the accepted stop tuple; the existing07 migration likewise checks successor_guard. Therefore the supported ordering cannot prepare the artifact while the reviewed failure stops remain active. With the narrow extension tested, sequence is: read-only prerequisites -> receipt-bound two-stop disposition -> independent readback -> exact08 namespace migration/readback -> prepare_continuation -> one build and zero-source startup verification -> independent artifact, suspension and baseline restoration readback. Registration/access opening happens only later in run-successor. Branch fast-forward and protected release-setting update require approval and must occur before build, preserving unrelated configuration and privately retaining the previous setting.

Before any live mutation, disposable PostgreSQL must prove the actual08 owner sequence: exact disposition; unchanged generation9 and historical evidence; wrong receipt/release/stop or used08 refusal; rollback of every pre-commit failure; permission cleanup; migration hash/ACL equality; predecessor journal preservation; fresh registration/activation with the exact accepted stop; finish guard retained; uncertain-ack readback. Existing accepted parser and period07 settlement tests need not be rerun unchanged. The owner extension is not yet implemented or validated and has no executable live command in this handoff. Do not treat the old Attempt06 CLI as that command.

Accepted validation reused: 170 focused local passes; hosted PostgreSQL run42045703206: 98 diagnostic/navigation/settlement,31 B-readback,72 Attempt06 owner-path,92 connected-ledger passes. These do not validate08. Overall CI retains documented baseline failures (11 timeout continuation cases, frozen inventory assertion, verification-import oracle and request-boundary digest); no historical hashes were changed to hide them.

## One proposed official B test and acceptance

27 October–2 November2026 inclusive; Tameside RECEIVED, Manchester VALIDATED. Existing limits unchanged: Tameside10 requests,3,000,000 bytes,6 pages of5/30 listings,45 source seconds; Manchester80 requests,20MiB,60 listings,6 pages,75 source seconds; aggregate90 requests,23,971,520 source bytes,120 source seconds,150 supervised seconds,960 wall seconds. Existing DB/resource budgets and cleanup reserves remain enforced. GitHub publication NOT_REQUESTED; scheduled collection suspended. Do not broaden the window or call capped partial coverage complete.

For EACH council separately require: qualified restricted roles before source; verified live navigation to terminal page with criteria/date semantics intact; displayed/parsed totals reconciled and no duplicates/gaps; truthful request accounting; durable capture linked to its checkpoint with independent bytes/hash readback; deterministic screening completed; discoverable backlog references and counts reconciled. An empty valid window can pass with verified zero results; a genuine bound or ambiguity remains a refusal. Tameside live page2+ is still UNVERIFIED. Manchester live completion is still UNVERIFIED. One council succeeding does not imply the other passed.

Before submission require fresh Dashboard observation of no inherited credentials/environment groups, secret files or competing operations, within the existing300-second bound. Record exact artifact commit/tree/execution binding, deployment and zero-source startup job with zero runtime authentication attempts. Then allow ONE run-successor submission, monitor/reconcile to terminal outcome, independently verify all evidence, authorities closed, login/membership/session closure, temporary-permission removal, exact scraper configuration/environment restoration and suspension. Expiry alone is insufficient. Capture partial/unknown outcomes without replay.

## REVIEW decision

Approve only the exact receipt-bound07->08 continuation and additive owner-journal namespace above, with disposable validation before live execution. Stop disposition must precede artifact preparation under the existing guard. No stop change is justified until the extension and all read-only preparation prerequisites are proven. Once that narrow path is validated, the next live approval can cover the two-stop transaction, migration, source branch/release preparation, zero-source verification and one bounded08 submission with cleanup. Do not approve blind execution of today's07-specific commands. Stage4 remains OPEN; this is preparation, not connected pilot acceptance.
