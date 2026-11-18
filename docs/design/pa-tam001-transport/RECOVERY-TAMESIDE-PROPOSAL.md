# PA-TAM001 v1.2 — combined recovery, release and first Tameside proposal

17 November 2026. **REVIEWABLE / NOT APPROVED FOR EXECUTION.**
Master Stage 4 OPEN. Current gate: controller permission/concurrency acceptance
and one combined operational proposal. Next gate: independent REVIEW, then exact
owner operational approval. No production command accompanies this document.

## Recommendation and practical outcome

Continue with one Tameside RECEIVED batch, 15–21 September 2026 inclusive, using
the existing pipeline. It must prove committed retention, screening and a separate
database readback. The capped batch may be incomplete; qualification, saved facts
and usable backlog are separate evidenced outcomes, not promised counts.

The owner-assisted route has succeeded for the read-only inspection; recovery
and collection invocation remain unproven. Do not rerun consumed
PA-TAM001 v1.1. Do not add credentials, services, endpoints or another worker.
Native one-off jobs and autonomous browser transport are not prerequisites.

## Exact evidence and revisions

| Component | Pin / status |
|---|---|
| Production observation | Receipt `e5464f22-684e-4c6d-95d6-b6e993e5b006`, 2026-11-17 12:43:27–30 UTC; [#214/6948459425](https://github.com/maxrose26/PropertyAIgent/issues/214#issuecomment-6948459425), [full reconciliation](https://github.com/maxrose26/PropertyAIgent/pull/227#issuecomment-6948438839) |
| Original inspected artifact | `fe843add6cb57e5ccbd2441369e9f45f1d231dd5`; original receipt and acknowledgement remain unchanged |
| Preserved hourly-worker correction | `70d488d84c1362af8ec0e64154cfc2735dc8592d` |
| Reviewed offline code candidate | `5955c49c4e0ef1a6ea009fd00020e607a577d7ba`, tree `d69bc07d628e5214f827ae16973f2daa57450ed1` |
| Existing Render service/deployment | `srv-d9qbl7qjnfac73d8nieg` / `2fa0f07cfdfb56a27243ebff18110d441f9da04d`; not changed here |
| Pinned owner adapter and Bolton settlement | #213 `f027ba28af69ae70208eab5ed047e4a8a81c6337`; `owner_pilot.Database`, `bolton01_settlement.recover` and independent `inspect` |
| Stable campaign SQL (uninstalled) | Full SQL SHA256 `c037fbff6f32687fc9f6e4a39aea67b11bf868e31c53edd5c83ac3ff830e7e2f`; body SHA256 `64b972a1d558800e27d4c149300965df7e5f73c2cf4e283761122088b6638eeb` |
| Private writer transition | `private_evidence_writer_transition.sql` SHA256 `307994ca2fb2925e3d1501f4fe2686cdc926ba87428c02a70211157998bfa964` |
| Inactive shared-stop release | `inactive_shared_stop_release_v1.sql` SHA256 `e6ada86a9e55521f9812c2064d5a60c3ba53bc5e0f6e508ca4a64bdca39a034a` |
| Corrected receipt reporter | `inspection.py` SHA256 `b16a26ad6eef7af7b2006291936339ce75718c4bd316657ecb0978bdf06dd09c`; OFFLINE ONLY, no new inspection authority |

The production observation established postgres identity, READ ONLY, 10s statement
and 3s lock timeouts, generation 14 with both STOPs set, seventeen explicitly
closed grants, no unexpired grants and no matching sessions at that instant.
All three installed function hashes match pinned #213. One aggregate
CLAIMED/SOURCE_INTENT remains. The inspection did not identify that item's key,
return exact stop-reason strings, inspect column ACLs, prove historical process
closure or measure database population. Client closure was true; ROLLBACK execute
returned, but original acknowledgement remains UNVERIFIED due to reporter error.

## Controller-locking resolution

Original SQL, executed as actual `session_user=current_user=postgres`:

```sql
SELECT outcome FROM public.ingestion_work_items
WHERE key=repeat('0',64) FOR SHARE;
```

It reads `outcome` and filters `key`. PostgreSQL requires SELECT on referenced
columns and UPDATE on at least one column for this locking clause. Table UPDATE
false does not exclude a column grant. Disposable proof covers SELECT-only denial
and UPDATE(key)-only success while table-level UPDATE remains false.

**Do not grant UPDATE(outcome) or UPDATE(key) in production.** Both permit direct
table mutation. Advisory SELECT followed only by later issuer locking leaves a
STOP race before temporary role acquisition, even if later writes would refuse.

The candidate preserves the worker's advisory SELECT and uses the SAME stable
campaign function for an exact owner-only `campaign_owner_preflight` operation:

1. Verify actual session/database and installed function body, owner, SECURITY
   DEFINER and search_path before calling it.
2. In the existing transaction, advisory-read and validate the actual STOP/policy.
3. The owner-only function branch checks exact payload and session identity,
   executes `SELECT outcome::jsonb ... FOR UPDATE` as ingestion_storage_owner,
   and returns only the four STOP fields. It neither updates nor registers work.
4. Compare the locked result with the advisory snapshot. A raced STOP refuses
   before GRANT. The lock persists through the existing transaction.
5. Only then acquire the temporary barrier capability. Normal issuance retains
   its own locked expected-state check and all registration predicates.

This closes the two original installed-function/actual-STOP findings. It does not
claim that expiry, duplicate-period, unfinished-run or unresolved-work predicates
all run before temporary GRANT: those remain issuer checks before data writes;
failure aborts the transaction and uncommitted role grant. No grant is committed
as a way around a refusal.

Installation proposal must explicitly grant **EXECUTE on this one exact function
to postgres**, keep PUBLIC revoked, and verify no additional grantees. Before the
collection stage, add only the existing restricted worker EXECUTE required for
its checked operations. Owner read/lock operation rejects all other session users
even if EXECUTE is accidentally granted. Actual owner SQL identity is postgres;
the configured pooler username is not a substitute for observing that identity.

This removes dependency on uninspected column UPDATE grants. The remaining
installation privileges use the already-reviewed owner admin-only membership and
schema-grant lifecycle; verify its original grantor/options, revoke only the
self-issued temporary membership and independently compare the baseline.

## Ordered operation — every step conditional on separate exact approval

1. **Freeze and reconcile before any mutation.** One operator; no active overlapping
   owner/worker. Bind the reviewed runnable build, exact release manifest, source
   qualification hash, screening hash, runtime/workflow hashes, actual London
   execution endpoint and finite expiry. Verify present process containment and
   all seven historical effect dispositions. Refuse unknown current activity.
   The new SQL is still uninstalled; all mutating branches remain WITHHELD and
   both distributed live flags remain FALSE. This is NOT a release-enabled build.

2. **Establish the unresolved item identity, not by guessing from its count.**
   Before approving settlement, use the smallest missing-fact read described
   below (or existing attributable equivalent). Confirm exact Bolton key
   `d9d8d667eef5fb012c74cdd28f5c55c6b577f749e7dc69d9179a6c032853d252`, period
   `b-bolton-20261103-1105-01`, run `ee7cf0d9bc714f56951527b940937054`, original
   marker SHA256 `1cc12dd9115573308aaaed83676c04260750aab9a8c4d8ad0694a9731cae1f02`.
   A different or additional unresolved identity changes the recovery proposal;
   it must not be fed into the Bolton adapter.

3. **Recover once under STOP14 using pinned #213.** Verify exact retained artifacts,
   original marker/journal, runtime closure and role baseline using existing
   settlement entry point. Its locked transaction fences the exact old item,
   records FAILED_RECONCILED/coverage UNKNOWN and advances to generation15 still
   stopped. Preserve all original records and other-work digest. Separate fresh
   connection runs `inspect` to prove committed receipt, fence, STOP15 and cleanup.
   Lost COMMIT acknowledgement invokes read-only reconciliation, never replay.

4. **Install reviewed changes while stopped.** Check the installed OLD writer/read
   hashes and ACLs against this receipt and the transition preconditions. Apply
   the exact writer transition; verify resulting body/owner/search_path/ACL and
   unchanged evidence hashes. Install only the reviewed single stable campaign
   function with owner-only read/lock permission initially. No activation just
   because installation succeeds. The final release-enabled SQL/build and manifest
   must be separately pinned after historical disposition is accepted; approval
   must not cover an unspecified future edit or removal of WITHHELD.

5. **Release15→16 once, then register one finite period.** Only an accepted exact
   seven-effect manifest, matching controller digest and owner authority allow
   the reviewed one-shot release transaction. Its table/controller locks and
   evidence comparisons remain intact. Independently read STOP16, release receipt
   and temporary-membership cleanup before proceeding. Register the canonical
   Tameside period through the same verified owner connection/preflight/issuer;
   max_runs=1, fixed RECEIVED window, exact bindings. The current negative-only
   issuer cannot perform this step and must not be advertised as executable.

6. **Run the restricted collector once.** Apply the limits below. On changed STOP,
   budget exhaustion, access challenge, failed total/terminal proof or uncertain
   persistence, preserve evidence and stop. Do not substitute a wider window,
   change a date field, fetch another council, or automatically retry.

7. **Close, reconcile and read back independently.** Invalidate period/grants,
   disable runtime logins/access, restore temporary memberships/settings and
   verify resulting sessions and grant state. Suspension remains; no successor
   run is automatically authorised. A separate connection reconciles committed
   identity/evidence/screening records against the pre-run baseline. Uncertain
   COMMIT is read back by exact operation identity; rollback never deletes useful
   evidence or overwrites UNKNOWN history.

## Fixed first-batch and outer limits

Tameside RECEIVED 2026-09-15 through 2026-09-21, inclusive, one finite period/run.
Source: **10 requests, zero retries, at most6 pages ×5 listings (30),3,000,000
bytes,45s worker/60s supervised,1GiB source/1.5GiB aggregate memory**.
Overall existing envelope: **960s including180s closure reserve;90 aggregate
requests/23,971,520 bytes;120s source/150s supervised;2,080 statements/96
connections/8MiB DB result bytes;2MiB export/512KiB source export**.
Closure reserve:32 statements/4 connections/768KiB. Existing GitHub80/20 call
budget unchanged. Stricter scope limits always win; public publication is optional
only with private receipt reconciliation. The preceding PA-TAM001 inspection
limits are not authority or budgets for recovery/collection.

## Missing fact and external release decision

No need to inspect column ACLs just to justify the selected no-table-UPDATE path.
The material missing production fact is the exact identity of the outstanding
CLAIMED/SOURCE_INTENT and present containment. Proposed targeted check, **not run
or authorised here**: existing owner route, one read-only connection, at most10
statements including controls,20s overall,10s statement/3s lock,64KiB results.
At most three bounded SELECTs: (a) actual session/READ ONLY/timeouts and STOP reason
fields/digest; (b) up to8 unresolved key/state/phase/fence/lease-presence rows and
exact Bolton period/run membership booleans, no raw payload; (c) matching session
metadata. Return overflow as UNKNOWN; explicit rollback/close, no retries. This
is a new narrowly scoped decision ONLY if equivalent evidence cannot be reused,
not a repeat of the consumed 17-statement inspection. It decides whether pinned
Bolton recovery is applicable; absence of sessions cannot prove child-process
termination. Obtain existing supervisor/provider process receipts separately.

Manchester−09 `21330c06…` and Tameside−06 `dc8ae276…` remain WITHHELD and permanently
no-replay. The original physical requests and attributable process termination
remain unknown. Either provide trustworthy original termination evidence, or the
owner AND distinct reviewer must explicitly accept that residual historical risk
conditional on independently verified present containment. Five preservation-only
ACCEPTs are insufficient. No current uncontrolled process can be accepted away.

**External dependency:** the operator supplies missing exact-item/present-containment
evidence; independent REVIEW and the owner resolve the two historical dispositions.
Only then can an honest accepted release manifest and exact enabled build be
finalised. This document deliberately does not invent acceptance, a future commit,
an execution timestamp, expiry, or a qualification target.

## Product readback and decision

Report separately by council/window: newly retained unique identities, existing
records updated, screened outcomes, rejected/unresolved reasons, verified scheme
qualification, saved facts and discoverable backlog. Match committed references
and evidence digests, source totals/terminal proof, run/period identity and prior
state. Listings are not admitted Applications. Incomplete intervals remain missing
or PARTIAL; zero may be reported only where actually measured. No new operational
population has been produced by this offline work.

Keep PA-D004 v1.3 all-ten catch-up from15September through the actual bound London
execution endpoint, <=7-day windows, current day PARTIAL, unknown earlier complete
dates honest. Trafford/Bolton requirements remain; this first Tameside operation
does not approve every later batch or close Stage4.

**GO:** review the completed narrow offline permission/rollback fixes and this
ordered proposal, using the exact focused PostgreSQL result linked in the handoff.
**NO-GO:** production execution, installation, settlement, stop clearance or live
collection until missing evidence, historical disposition and exact enabled
artifacts are independently accepted and specifically authorised. No generic new
access permission or repeat-inspection request is justified by this handoff.
