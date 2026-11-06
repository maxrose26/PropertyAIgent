# Period08 implementation and release-binding blocker

MASTER STAGE4 OPEN. **NO-GO for live pilot acceptance: no period08 submission was made.** The exact authorised scraper pin cannot accept the authorised period08 argument. The owner extension and a minimal scraper admission correction are prepared on PR #211; the material decision is the replacement scraper binding, not another approval for routine phases.

## Revisions and demonstrated blocker

Preparation handoff: `58dcf2cc106285318943c6499a133c289833391a`.
Initial implementation: `ac6f503d33e9ad2a884e6cc56b4dc02bb2ad6ee1`.
Final code: **`3adb65d06d0492d3b8f9b798e49e3be20699b082`**, tree **`62b685ac7a2e826ad1f14bc4bb8ba98e42fe15eb`**.

The accepted scraper `56a8a420ae21f60633dc2b8eea4c2f61ef5659a1` has an explicit argparse period allow-list ending at07 in `scripts/owner_pilot_job.py`. Running that exact file offline with `--period b-dbpilot-20261027-1102-08 --hostaddr 127.0.0.1 --startup-check-only` reproduced exit2 / invalid choice. Parsing refuses before any runtime authentication or source request. Its qualification and startup mode lists also end at07. This was missed in the earlier preparation assessment; an owner-only journal change cannot correct the packaged scraper entry point.

The final candidate adds08 to those existing lists, without changing the qualification boundary, environment filtering, startup guard or worker behaviour. The manifest binds this file, so changing it invalidates the old release binding. It is not safe to deploy changed files and continue claiming revision56a8/treea27d. No such substitution occurred.

## Implemented narrow owner extension

- `scripts.owner_period08`: explicit inspect, dispose, prepare-successor, verify-successor, run-successor, close-successor and status actions, using the existing Pilot and encrypted Journal. No automatic retry after uncertain acknowledgement; bounded refusal output.
- `period08_successor`: fixed07->08 identity, period07 receipt hash, exact retained history/evidence, exact accepted release, generation9 stop tuple, unused successor and predecessor journal checks. No arbitrary period/recovery framework.
- Disposition updates only the control outcome's matched global/manual stops and adds period07.failure_disposition. Generation9, last_hard_stop and all other state remain unchanged. It does not recover period07 again.
- Existing owner-state migration adds only08_owner. Original function body SHA e11e137a81c027f36d02541c44e5d511b60bbfef01794211f97b53e8b57d40b7; proposed body SHA551a7cf34367ea509fdff95dd51bb4e0da0b7347a20cab8c009a372f596c4948. Existing ACL, owner, search_path, SECURITY DEFINER, bounds, exclusion and compare-and-swap retained. Temporary schema CREATE and owner SET membership are removed before commit.
- Existing registration and activation now require the exact08 namespace as well as the exact receipt/disposition. Changed definitions, stops, receipt, release, consumed successor and historical outcomes refuse. intake_finish, SQL worker functions and completeness guards are unchanged.
- Period07 historical item/receipt checks were extracted without changing the original settlement guard or transaction. Attempt06 history remains independently checked.

The owner module deliberately still pins the user-authorised56a8 release. The candidate scraper correction is proposed, not silently adopted as an approved release. The binding update below must be accepted before updating that fixed owner pin and executing live. Do not run the existing candidate disposal now merely because its PostgreSQL tests pass.

## Validation

Local focused owner/startup regressions: **20 passed**. Includes actual Runtime startup path with transport/database access forbidden, dirty/unverified checkout refusal, zero-source/zero-authentication startup, qualification boundary, all five release-field mismatches and CLI lost-ack stop behaviour.

Initial hosted PostgreSQL17 run42052063692, job127330468470: **33 new period08 tests passed**,98 period07/navigation,31 targeted B readback,72 Attempt06 owner path and92 connected-ledger tests passed. The final candidate additionally requires the migrated08 namespace before admission and puts migration into the same connected disposable sequence. Final hosted PostgreSQL17 validation on **3adb65d**, run **42053266822**, job **127334722871**:

- **34 period08 tests passed**, including migration in the connected disposition/admission/runtime/closure sequence and refusal of a changed journal definition.
- **98 period07/navigation**, **31 targeted readback**, **72 Attempt06 owner**, and **92 connected-ledger tests passed**.
- The historical fixed B-readonly suite remains16 passed/1 failed: the same frozen `ingestion_register_bolton_exception` inventory assertion, actual SHA1d05b3f4476a8ad2a14aa083eb15396c9d157265dc19254df738777673cd995d. No relevant PostgreSQL path failed.

Overall CI is not green. The final discovery offline job127334723369 has the same11 legacy timeout-continuation failures (1508 pass); these were reproduced on the accepted baseline and are unchanged by this extension. AH offline job127334724167 has the same verification-import oracle failure (1867 pass); batch offline job127334724227 has the same frozen direct-registration digest assertion (826 pass). The application/import path, request-boundary bytes and historical oracle files are unchanged. Accepted baseline reproductions are retained in PAGINATION-FIX-RESULT.md and its linked run42045703206. Historical hashes/guards were not altered to suppress these reds. Web and native checks passed. These baseline failures remain disclosed; focused synthetic acceptance is not whole-release or live acceptance.

CI: https://github.com/maxrose26/PropertyAIgent/actions/runs/42053266822

Disposable evidence uses synthetic bodies and credential fixtures. Only expected private evidence hashes and release identity are substituted; production owner/SQL/history validators are exercised. The non-superuser actor has read-only catalogue/evidence visibility, temporary authority only for the tested transaction, and no persistent write ACL on evidence. This is not proof of live collection.

The new sequence proves exact disposition/readback -> namespace migration/readback -> period issuance -> restricted activation -> synthetic Tameside and Manchester capture -> hash-verified retention -> screening -> independent finalisation -> access closure. Tests cover failure before commit and after mutation, lost commit acknowledgement resolved on another connection without repeating the write, unchanged evidence/history, removal of temporary permissions, preserved original schema/function ACLs, and readable encrypted predecessor history after the new journal is created.

## Live read-only result; no mutation

**5 November2026 15:12:13.381016 UTC:** the original reviewed validator rechecked period07 settlement and original artifact hashes using the unchanged clean owner checkout `e191729bd9f05224932fef9903341d99d63650de`.

- Receipt b461d84c45aadbea3bab1960273cedcf55f75a19b967b5d71a205d587ba8fb44; archived marker and three artifacts unchanged.
- Period07 Tameside SAFETY_BLOCKED/RECOVERED fence2, attempt_count1, no owner/lease/checkpoint; original fence1 attempt closed/RECOVERED, no checkpoint.
- Generation9; global DAILY_INTAKE_SHARED_FAILURE and manual/last_hard_stop ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP remain in force.
- Period08 absent from registrations; zero matching work items, evidence and owner-journal rows; no active intake marker. It remains unused, not reserved.
- Runtime sessions0, temporary memberships0, stable restricted access dormant. Attempt06 history remains valid. Transactions ROLLED_BACK.

**15:13:42.292247 UTC:** provider GET checks independently confirmed scraper suspended, configuration_equal=true, environment_equal=true against the saved baseline, and complete terminal-only job/deployment inventories. Latest deployment remains `dep-dbm702rbc2fs738gfuv0`; latest job remains period07 `job-dbm7dqh42hec73dsgahg`. Installed journal function still exactly07, with no08 namespace. Configured scraper release remains54700366. No credentials or environment values were exported.

No live deployment, source branch change, configuration change, schema migration, stop disposition, runtime opening, fresh council request or intake submission occurred. No cleanup was necessary for a new run; existing closure/restoration was independently reverified. No period08 job ID exists.

## Proposed replacement release — REVIEW decision

```json
{
  "execution_binding": {
    "revision": "3adb65d06d0492d3b8f9b798e49e3be20699b082",
    "workflow_sha256": "a111c858189389df02d3fa2360c5d5d31520c472e85402ed2eab12993d90f2c2",
    "manifest_sha256": "4cc667f3727fc1f27fc0b305a4186174fcc2590185d1b7bd9384932dd96ee5ad"
  },
  "tree": "62b685ac7a2e826ad1f14bc4bb8ba98e42fe15eb",
  "branch": "prep/b-timing-pg17-current-20261103"
}
```

Canonical binding SHA256: `f9436e02690dfe2cbdf265ca773da6039ac40d73a302a6ae3399848b5e7fd732`. This was computed from the exact candidate tree using the existing execution-binding function. The documentation revision is not the scraper revision.

Smallest decision: **approve replacing the scraper pin56a8 with the final tested candidate above, and the corresponding fixed owner-pin update.** All other execution limits and the existing one-submission authorisation remain unchanged. No wider collection, new credentials, scheduled restart or replacement run is requested. After approval, update the owner-only literal pin in a distinct owner revision, validate exact values, recheck live preconditions, perform receipt-bound disposition and independent readback, migrate/read back the namespace, fast-forward only the reviewed source branch, prepare/verify the artifact and zero-source startup, verify cleanup capacity and fresh Dashboard isolation, then submit once and verify terminal outcome/cleanup. An uncertain acknowledgement stops progression until readback reconciles it.

## Council acceptance and current limitations

Window remains27 October–2 November2026 inclusive, Tameside RECEIVED and Manchester VALIDATED. Existing Tameside10-request/30-listing/6-page/45-second and Manchester80-request/60-listing/6-page/75-second limits, byte/memory ceilings and960-second aggregate runtime remain unchanged. GitHub publication NOT_REQUESTED; scheduled collection stays suspended.

For period08 both councils are **NOT_ATTEMPTED**. Live terminal-page traversal, coverage reconciliation, durable capture, completed screening and discoverable backlog are **NOT_VERIFIED**, separately for each council. Existing synthetic tests do not establish these live outcomes. Period07 retains its three accounted requests, failed coverage and Manchester NOT_ATTEMPTED; Attempt06 retains UNKNOWN cause/count. No historical outcome was rewritten.

Recommendation: NO-GO for pilot acceptance now; GO for REVIEW of the replacement release binding with the final focused hosted results above. Stage4 remains OPEN.
