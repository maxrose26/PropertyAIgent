# PA-TAM002 v1.2 — one inactive recovery/release/Tameside package

17 November 2026. **Stage 4 OPEN. Prepared for independent REVIEW; not authority
for execution.** Current gate: independent acceptance of this DNS-only delta. Next gate:
owner acceptance of the exact pin amendment to the already-approved operation. Source revision: 8b5f4e2e843ec42de37fce5a3827e0de475ba24a;
source tree: aa9fee6b9d7fbe09dea42c5bb033d25d03d8a0a9. The documentation commit is not the enabled build.

## DNS-only pin amendment — v1.2, preparation only

Owner approval #214/6958893399 and independent REVIEW #227/6958965414 accept the prior v1.1 sequence. The operational preflight #227/6959099227 stopped before any database connection because the frozen first-answer selector chose another valid pooler address. This v1.2 amendment changes only that selection dependency and its code/workflow pins. Production awaits acceptance of the changed pin; the original one collection submission is unused.

Construct the owner route from the corrected source checkout (never moving HEAD):

```python
from verification.ingestion_storage.tameside_owner_database import database_type
from verification.ingestion_storage.tameside_package import HOSTADDR
Database = database_type('/path/to/verified-f027ba28-checkout')
db = Database()  # existing DATABASE_URL remains private; no connection yet
assert db.address == HOSTADDR == '18.169.28.97'
```

The path above is the operator's existing verified pinned checkout, not a new credential/route. The adapter verifies the whole frozen owner_pilot.py SHA256 f33439807df02e14fec167e7f3782a36af5e12e52949404c2388b610d1e61981 and Database class SHA256 4959d79558bd5c4a5aabb8ec6c5dd6f05c02720c23bcefa9bf6985507673b36f. It replaces exactly one source anchor in that class; the original source is not edited. Current TLS trust source must match frozen SHA256 5b6e3dac999ad4b23efe148bb07ab43f64d4776e0c521d7303cecb9a2d47060d. The unchanged connection method retains the original hostname, certificate verification, CA, port 5432, timeouts and single hostaddr. No global socket override, address failover or retry is introduced.

Resolution runs in an isolated Python child, once per new owner Database construction, with a 3s parent timeout, maximum 32 answers/4096 result bytes and no credential environment. Require approved-address membership; never loop for a preferred DNS ordering. Use this same adapted db for owner preflight/recovery/readback/journal/access. A separate readback connection may reuse this db and its selected address; any newly constructed db must repeat the bounded presence check. Do not call the old unadapted Database for later phases.

Set owner binding hostaddr AND owner_hostaddr to db.address; require equality with the sealed policy hostaddr and compiled job --hostaddr. compile_package preserves the same fixed HOSTADDR. Existing owner validate_binding, restricted validate_job and runtime equality checks remain unchanged. If any binding differs, stop before effects rather than rebind it. The connection failure path makes one driver attempt and propagates failure; it never chooses another answer.

Focused offline results: **37 passed / 0 skipped in 0.90s**, including 15 DNS adapter cases plus existing provider/package/runtime checks. Actual hash-verified frozen class is exercised with mocked DNS and driver: reordered/additional/absent answers, timeout/error, source/route drift, unchanged TLS arguments, one failed connection/no fallback, owner-to-policy-to-runtime equality and different runtime address refusal. No live DNS/database/source calls occurred during this correction. Existing d9a2242 Stage4 8/8, 279 local and journal/recovery connected evidence is reused only for unchanged paths; it is not represented as validation of the new source. Final hosted delta status and distinct review are recorded in the publication handoff.

## Earlier corrections preserved

This supersedes v1.0's failed build. It reuses the corrective worker's five
commits through d66fed0601c4b0dee12d06f1c6224f5a7880de6b. That worker released its
claim at PR227/6958238955 and completed at 19:15:20.380290Z before this session
edited. Its build passed eight Stage4 jobs in run 44155820947. The v1.1 results below are retained unchanged-path evidence; v1.2 delta evidence is identified separately above.

The sealer calls `daily_intake_runtime.runtime_screening_config_sha256()` without
importing/selecting V3. The reviewed consumer list/scanner remain unchanged. The
sealed digest is tested against the runtime's exact rule.

The Tameside-only handoff succeeds without browser profile/path; a bound stale
profile refuses before a provider write. Old browser environment keys are removed
for the finite HTTP job and restored exactly afterwards. Only four harmless
names and two restricted DSNs enter the mapping. Wrong period or missing finite
timing refuses before any provider call. Pinned #213's Manchester path is
unchanged. Provider tests use mocks; they are not production connectivity proof.

## Outcome and scope

The first operation is one Tameside **RECEIVED 15–21 September 2026 inclusive**
batch, period `S4_FINITE_677f555670666bcf21f45860`, max_runs=1. Its useful acceptance
is separately read-back committed capture, metadata screening and discoverable
investigation backlog. This path does not admit Applications or extract verified
scheme facts. Qualification, saved facts and buyer opportunities must be reported
separately only if evidenced. A successful job cannot substitute for that readback.

All-ten follow-on remains Manchester, Bolton, Tameside, Bury, Oldham, Rochdale,
Salford, Stockport, Trafford and Wigan. Initial fallback is 15 September 2026,
including earlier evidenced gaps, in <=7-day windows through a separately bound
London execution date. Unknown coverage stays unknown; this first week proves
neither the shutdown-gap campaign nor Stage 4 completion.

## Evidence reused, not repeated

- Matching Bolton v1.4 receipt: PR227/6952744510; consumed. v1.3 remains fenced.
- v1.5: PR227/6955594746; consumed; ordinal55, exact checkpoint hash, six
  statements, 2967ms, separate confirmed rollback and connection closure.
- REVIEW's direct service comparison, supplied in the associated owner
  conversation: workspace `tea-d9qbf8jm8hqs7385cu0g`, restricted service
  `crn-d9sv93vavr4c73f98rb0`, unchanged #213 service_guard digest
  `78b5f3a8f5b2730f5d675d214192b53e339edb07ceeb14e188ed1d2c3ab14257`.
  cron_job, suspension, autoDeploy=no and /bin/true passed. This is REVIEW's
  observation of non-secret configuration, not this implementation's fresh read
  of addresses, credentials, grants, processes or deployment.
- Owner Manchester-09 and Tameside-06 risk acceptance #214/6950521818 and distinct
  containment assessment #214/6951000467, with provider evidence #227/6950238956.
  Original request counts and supervisor cleanup remain UNKNOWN. All seven
  original work/attempt identities, fingerprints and permanent no-replay remain
  in unchanged `release-proposal.json`; no old attempt becomes replayable.

## Exact pins and finite values

The build is 8b5f4e2e843ec42de37fce5a3827e0de475ba24a. `artifact-pins.json` lists the source hashes and
execution binding; #213 owner adapter remains
`f027ba28af69ae70208eab5ed047e4a8a81c6337`. Guarded Bolton recovery source is
`5bd306a86bc8b273d3bd0d778e7fc7803e737d7a589828f9f0405bc844a18d4a`.
Installed writer transition source is
`307994ca2fb2925e3d1501f4fe2686cdc926ba87428c02a70211157998bfa964`;
conditional release template is
`e6ada86a9e55521f9812c2064d5a60c3ba53bc5e0f6e508ca4a64bdca39a034a`.
Source-plan SHA is
`d90fe1a7effd84d05593a8cbdc782d97c9b42fa904c45b29312c5fc03d6dae06`.

Actual owner SQL identity must be `session_user=current_user=postgres`, database
`postgres`, using the explicit hash-verified adaptation of the existing #213 `owner_pilot.Database` session route described below. The pooler
account name is not proof of SQL identity. Select **18.169.28.97** only when a fresh bounded DNS answer for the exact configured hostname includes it; answer order/additional addresses do not change selection. Absence, timeout or malformed answers refuse before connection. No alternative address or credential
is invented. Retained stable restricted passwords/verifiers remain private and
must match current state. Worker receives only worker/effect credentials, no
owner/database administration, provider, GitHub or model tokens.

Absolute expiry ceiling: **18 November 2026 20:00 Europe/London (UTC)**,
1795032000. Record `bound_at` once, without retry/extension. Access expires at
bound_at+2100 seconds; policy runtime deadline is bound_at+1915, reserving 185s
for closure. Enforce existing opening/submission reserves and a 960s maximum
runtime. If too little time remains, do not release or submit; cleanup remains
available. Ceiling expiry requires a revised decision, not a silent extension.

Source limits unchanged: 10 requests, zero transport retries, six pages of five
rows, 3,000,000 source bytes, 45s source worker/60s supervisor. Existing DB,
aggregate archive (2MiB; original source <=512KiB), runtime, memory and provider
bounds continue. Recovered resource profile: 2GiB aggregate, 1GiB source,
256MiB controller, 512MiB reserve. Preserve historical browser settings for
Manchester; a new browser canary is not a Tameside HTTP prerequisite.

## What is sealed now and what is derived once

Sealed now: code, adapters, source templates, seven preimage identities, policy
recipe, batch, source qualification and screening config, provider digest,
address, resource limits and expiry ceiling. Default live flags stay FALSE.
Only the explicit candidate context enables the single policy and restores flags.

Post-recovery row/attempt/controller hashes cannot truthfully be known before
recovery. A *separate read-only connection* calls `manifest_from_readback` with
unchanged proposal and the genuine operational REVIEW reference. Its exact output
is retained. `compile_package(manifest, bound_at=..., owner_journal_source=...)`
then deterministically emits policy, manifest, stopped-install SQL, conditional
release SQL, self-contained job command and an index of every byte/hash. No
placeholders may be sent to production. These mechanical bindings are part of
this proposed one approval; an unexpected observation is a stop, not permission
to choose a new manifest. The enabled build is never taken from moving HEAD.

The job command carries only bounded non-secret policy as base64 plus its SHA256,
so it does not rely on a /tmp file surviving a new runtime instance. It invokes
`verification.ingestion_storage.tameside_candidate` under timeout 960s and checks
actual Render service/build, restricted environment, address, period, complete
policy and remaining time before entering the runtime. Exact command bytes are
in the compiled package index before submission.

## Necessary journal adaptation included in this proposed installation

The old checkpoint is ordinal55. #213 reserves the last16 of64 snapshots for
cleanup and permits normal writes only through ordinal47. Reusing or resetting
that old journal would defeat those protections. Do not call old `Pilot.run` or
its old-period job unchanged.

`tameside_owner_journal.render_install` extends only the existing owner-state
function's exact allowlist by `S4_FINITE_677f555670666bcf21f45860_owner`.
The deterministic run ID is in the pins file. Existing table, Vault encryption,
key derivation from protected configuration, 32KiB ciphertext bound, 64 snapshots,
advisory lock and previous-hash CAS are unchanged. No new service, table, role,
credential or storage system. The original ordinal55 and all earlier evidence
remain untouched. Installation requires exact old body hash, actual owner,
STOP15, unused namespace and temporary schema/owner restoration; duplicate
installation refuses. Existing journal loading reads the old state only under
the future combined operational authority; it does not rerun the v1.5 launcher.

Use `fresh(pinned_owner_module, db)` for the new namespace and the same encrypted
Journal callback. Retain original checkpoint reference, private original Render
environment and stable credential data needed for restoration; do not copy all
old phase history or any old pending intents. Validate actual encrypted capacity
before effects, with the existing cleanup-reserve policy and sixteen reserved
snapshots. Persist a prepared activation state before activation. Unknown journal
acknowledgement requires `tameside_owner_journal.reconcile(pinned_owner_module, db)`
and exact comparison with the retained intent. It opens a separate READ ONLY
transaction, decrypts with the existing codec, rolls back and closes; no write
is repeated. Missing state is UNKNOWN; fresh() refuses a used namespace.

## Ordered execution contract — only after separate REVIEW and owner approval

1. **Preflight while STOP14 remains.** Reconcile writer/active jobs, reserved
   operation and source/build hashes. Reuse accepted historical containment;
   inspect current overlapping jobs/processes before dispatch. Load retained
   private state through existing owner route; verify current owner identity,
   address, credential verifiers, database/interface permissions and encrypted
   capacity. Check original service/environment and no inherited secret sources.
   Do not mutate if schema/barrier/role capability or cleanup prerequisites fail.
   Build the exact candidate on the existing suspended restricted service only,
   keeping autoDeploy=no and harmless default command; independently verify its
   deployed revision and restore/check the bound service digest. No source job.
2. **Exact Bolton recovery.** Existing `bolton_recovery_guard.recover(c,binding,
   pinned_module=bolton01_settlement)` retains #213's locks and strengthens the
   unrelated CLAIMED predicate. Preserve key
   `d9d8d667eef5fb012c74cdd28f5c55c6b577f749e7dc69d9179a6c032853d252`, run
   `ee7cf0d9bc714f56951527b940937054`, original marker
   `1cc12dd9115573308aaaed83676c04260750aab9a8c4d8ad0694a9731cae1f02`.
   Separate `inspect` must prove committed recovery and STOP15. Unknown COMMIT
   acknowledgement: inspect, never repeat recovery. Mismatch stops here.
3. **Stopped installation and exact manifest.** Apply the six exact dispositions
   using `render_dispositions`; install the pinned private writer transaction.
   Separately read/seal the seven actual post-recovery/disposition hashes and
   controller snapshot. Freeze bound_at; compile the package once. Under STOP15
   install the new journal namespace and policy-bound campaign function using
   their owner transactions. Read back bodies/owners/search_path/ACLs and original
   owner/barrier/schema privileges. Create and independently load the new encrypted
   operation checkpoint. Any failed transaction rolls back; unknown commit is
   reconciled through installed state before considering any further action.
4. **Conditional release.** Execute the package's exact release SQL once. It
   locks/rechecks all observed hashes, unresolved work, expiry and STOP15. Separate
   readback must establish STOP16, matching manifest, both stops cleared and
   restored temporary permissions. No competing CLAIMED work may be overlooked.
5. **Register and activate.** Within `tameside_candidate.enabled(policy)`, call
   the existing `Owner.register_historical_campaign_period` once. Its installed
   function check and actual locked STOP check precede the temporary issuer grant.
   Use `tameside_owner_access.lifecycle` with source-derived inventory, prepared
   existing stable credentials and encrypted save callback. `activate` retains
   table/controller locks, current state/fingerprint rechecks, finite validity,
   exact memberships, verifier preservation and ledger no-change check. A STOP
   change after preparation refuses without enabling either login.
6. **One restricted handoff/job.** Use `provider_io` around pinned #213 handoff,
   submission check and restore functions; its validator is the new exact binding,
   not the old period validator. Fresh HANDOFF/SUBMISSION observations bind actual
   revision/deployment, service, no overlap or inherited secrets. Keep a durable
   one-submission intent before POST. Submit only the indexed `job-command.txt`
   once to the existing restricted service. No retry/alternative invocation.
   On uncertain submission, reconcile existing provider records and receipts;
   a command echo is not acknowledgement. Missing/lost receipts mean UNKNOWN.
7. **Independent outcomes and cleanup.** Independently read private final evidence
   and recompute its bytes/hash, then committed capture work and capture-bound
   screening rows/backlog against the exact council/window/run/build. Report new
   unique identities, updates, screened, rejected, unresolved and backlog counts
   separately. Deduplicate against prior retained identities; raw listings are
   not Applications. Do not infer qualifying schemes or saved facts.
   Always invoke access `close` independently of a changed STOP; verify NOLOGIN,
   exact grant removal, prior settings, preserved stable verifiers, no matching
   sessions and expired run authorities. Preserve original/failed evidence.
   Require attributable terminal job/process evidence as well as database closure;
   empty sessions or expiry alone are insufficient. Restore exact original
   environment, suspended service, harmless command and configuration digest via
   pinned restore path and separate provider readback. Unknown cleanup remains
   contained/reconciliation-required and bars any subsequent run.

The commands above name the exact existing entry points and compiled artifacts;
they are not a claim that old `owner_pilot.run` can be dispatched unchanged or
that a new end-to-end production supervisor has been exercised. Existing owner
transport and encrypted callback must execute these ordered phases. A failure
never permits proceeding to the next phase merely because its timeout expired.

## Validation and acceptance limits

Focused result: **279 passed / 0 skipped in 29.21s**. After the final READ ONLY
reconciliation refinement, the affected integrated test passed again in 25.09s;
unchanged passing evidence is reused. PostgreSQL 17.11 on loopback, no live sources.
The joined actual-entrypoint test covers guarded recovery/lost-COMMIT readback,
STOP15 dispositions, actual restricted-owner stopped installations, new journal
namespace/CAS/duplicate refusal, independent manifest, STOP16 release, actual
registration, stable access activation, synthetic capture/screening/backlog,
private hash readback and actual access closure. STOP changed between prepare and
activation refuses. Fixture-only catch-up permission was removed instead of
weakening the production activation guard. Unit checks cover exact policy,
address/build/service/expiry/credential refusal, source-derived inventory and
provider handoff, duplicate submission, restoration and lost-ack reconciliation.

Fixture projections remain explicit: local database/route, synthetic historical
rows/source and credential values, bootstrap-provided installation capabilities,
and mocked provider I/O. The actual pinned encrypted journal callback now records activation and closure
in the integrated sequence, with independently decrypted readback at each call.
A committed journal write with deliberately lost acknowledgement is recovered
without repeating it. Missing state, duplicate operation and stale CAS refuse.
Original evidence rows' stored and calculated hashes are compared before/after.
Installation is tested with transaction rollback and a lost post-COMMIT
acknowledgement resolved by separate installed-body/privilege readback. Normal
writes stop at ordinal 47; all sixteen cleanup snapshots succeed through ordinal 63, then further
writes refuse. The byte reserve is preserved. After the capacity stress proof,
ONLY its synthetic namespace is reset in disposable PostgreSQL before testing
actual activation/closure callbacks. No original namespace changes; this is not
a proposed production deletion/reset. Newly enabled production code, actual schema
rights, deployment, authentication, process closure and population remain unproven
until the separately authorised operation and its readbacks. Earlier passing
recovery/readback/issuer evidence is reused where unchanged. Prior v1.1 source d9a2242 passed **8/8 required Stage4 jobs** in [run 44158175273](https://github.com/maxrose26/PropertyAIgent/actions/runs/44158175273). The expanded actual-entrypoint/package step passed **30 tests in 31.11s**. The repaired V3 boundary passed within the **1078-test safety matrix**. AH and reusable workflows also succeeded. These counts describe their named checks; unrelated workflow steps retain their documented skips. Final aggregate
review must assess these new adapters and journal delta, not inherit an earlier
component acceptance automatically.

## One proposed pin amendment, after independent delta REVIEW

**PA-TAM002 v1.2 — recommend approval only after exact-head REVIEW accepts this
package and required checks.** The owner has already approved the finite sequence below at v1.1. The requested v1.2 amendment replaces only the executable/package pins and DNS selection binding, retaining that same authority:
existing-service candidate deployment while stopped; exact Bolton recovery and
historical dispositions; stopped writer/campaign/journal installation; mechanical
manifest/policy binding and conditional STOP release; temporary existing restricted
access; one Tameside week; independent outcome/cleanup readbacks and restoration.

Main trade-off: this starts delivering verified retained/screened data now but
still may yield incomplete coverage or no qualifying scheme. The alternative is
to remain stopped; optional browser, deletion, WhatsApp or publication work would
not resolve this gate. Excludes wider collection, retries/replay, extra spend,
new credentials/services, Application admission, Stage5 activation and Stage4
closure. No approval is requested before independent REVIEW is complete.

## Expiry check

Checked **17 November 2026 19:32 London**: 24h28m remains to the fixed expiry, and 23h53m to the latest binding time. This is practical for review and approval now, but must be checked again at execution. Latest permitted bound_at is **18 November 2026 19:25 London**
(20:00 minus 2100s). Preflight/build preparation must also fit. This is not a
scheduled dispatch. An expired/insufficient window refuses; a later expiry
requires a revised owner decision, never an automatic extension.

**Recommendation now: GO for independent REVIEW of this inactive package;
NO-GO for production execution until explicit acceptance/operational approval.**
No new production records or opportunities were produced in this preparation.
