# Current update — final inactive operational review package

See [PA-TAM002 v1.0](TAMESIDE-OPERATIONAL-PACKAGE.md) and [exact artifact pins](artifact-pins.json).
Source build **bd292e8110e9098f344d0ef2176d632988706c7a**. REVIEW supplied the matching provider configuration digest; v1.5 remains consumed. New owner/campaign adaptation and existing-journal namespace extension passed 26 focused offline tests. Hosted exact-head CI is pending, not inherited from the earlier build. Independent aggregate REVIEW and one owner operational decision remain; Stage 4 OPEN and production actions held. The older dependency descriptions below are preserved history.

# Current update — v1.5 checkpoint recovered

The checkpoint read succeeded; see [verified outcome and remaining current-runtime comparison](CHECKPOINT-V1-5-OUTCOME.md). Historical runtime inputs are recovered, not current-runtime acceptance. The older access dependency below is preserved as history. Stage 4 OPEN; operational release remains WITHHELD.

# Conditional release candidate — offline integration checkpoint

17 November 2026. MASTER STAGE 4 OPEN. Current gate: exact executable candidate;
next gate: distinct REVIEW, then one owner operational decision. No production
recovery, installation, deployment, STOP clearance or collection occurred.
v1.4 remains consumed; v1.3 remains fenced. Reuse receipt #227/6952744510.

## Implemented

- `bolton_recovery_guard.recover` wraps unchanged #213 at
  `f027ba28af69ae70208eab5ed047e4a8a81c6337`; source SHA256
  `5bd306a86bc8b273d3bd0d778e7fc7803e737d7a589828f9f0405bc844a18d4a`.
  The original locked OTHER_WORK check now includes every unrelated CLAIMED
  item. Original recovery checks, receipt, evidence and cleanup are retained.
- `release_candidate.render_dispositions` binds six historical dispositions
  to their original compound work/attempt hashes; the seventh is exact Bolton
  recovery. Original rows/attempts are preserved, attempts are not rewritten,
  UNKNOWN stays UNKNOWN, and all seven remain permanently barred from replay.
  The two older Bolton fixture rows have OPERATOR_REVIEW, not RECONCILE, and no
  original no-replay flag. The exact preimage hash remains mandatory; the new
  no-replay prohibition does not fabricate an old flag or old cleanup outcome.
- Disposition DML uses the existing temporary owner-role lifecycle but does not
  unnecessarily require schema CREATE grant options. Actual installation still
  requires and checks the schema grant capability. Campaign installation grants
  storage-owner CREATE temporarily and verifies its removal before commit.
- The campaign compiler binds the complete policy and canonical source-plan hash
  in SQL, plus the release-manifest hash. Only Tameside RECEIVED 15–21 September
  2026, max_runs=1, is accepted. Owner and runtime calculate that same installed
  function. Owner registration checks the actual postgres session, installed
  body/owner/search_path and the real controller before temporary capability.
- `manifest_from_readback` seals the seven actual post-recovery/disposition row
  and attempt hashes and controller hash through a separate read-only connection.
  Release independently rechecks them under locks. Future hashes are not guessed
  from old hashes. A review URL/content hash is a binding, not proof of approval.
- `tameside_candidate` is an explicit executable entry point; imports leave both
  live flags FALSE. Its enabled context accepts only the exact single batch,
  current build binding, release hash and expiry no later than **18 November
  2026 20:00 UTC**. It restores both flags on success or exception. The registered
  SQL policy, STOP checks, expiry and max_runs remain independent enforcement.

## Connected validation and its boundaries

Local PostgreSQL 17.11, loopback-only disposable database, no production secrets
or council requests. Eight focused candidate tests plus 43 existing issuer
checks pass (51 total). The joined test uses the actual pinned #213 failed-run
fixture and guarded recovery; deliberately lost COMMIT acknowledgement is
resolved by a fresh STOP15 read without repeating recovery.

In that SAME database the current candidate then executes six dispositions,
writer installation, campaign installation while STOP15 remains set, separate
manifest readback, conditional STOP16 release, actual
`Owner.register_historical_campaign_period`, and the runtime under
`tameside_candidate.enabled`. The actual non-superuser postgres owner executes
those administrative paths. Temporary owner/barrier/schema privileges are
restored. Independent evidence readback verifies all three stored artifact
hashes and absence of worker/effect database sessions after closure.

The result is ONE synthetic retained listing, COMPLETE metadata screening and
one discoverable backlog record, with CLOSED cleanup and INVALIDATED authority.
Application admission is disconnected: no verified qualification or saved
scheme facts are claimed. No production population is evidenced.

Explicit fixture projections: database name, historical fixture hashes,
synthetic source evidence, local transport and bootstrap-provided owner schema
and barrier ADMIN privileges. Existing fixture credentials are activated only
for this disposable run and disabled afterward. These are NOT observations of
present production grants, deployed runtime resources or credential restoration.
The dedicated install test also proves transactional rollback/absence, duplicate
installation refusal and original membership/schema baseline restoration.
Negative tests retain expiry, changed fingerprints/state, wrong canonical source
plan (including valid-looking wrong SHA), council/window/build drift, unrelated
CLAIMED work, duplicate refusal and explicit enabled-context restoration.

## Ordered operational sequence for review — NOT authorised commands

1. Existing owner route reconciles overlap, consumed/fenced invocations and
   unchanged accepted provider containment. Verify pinned checkout, owner
   identity, exact existing private runtime configuration and all necessary
   capabilities before any mutation; mismatch stops the sequence.
2. Load unchanged #213 module and binding through existing owner adapter; invoke
   `bolton_recovery_guard.recover(connection,binding,pinned_module=module)` once
   under STOP14. On uncertain acknowledgement: fresh `module.inspect`, never
   blind retry. Require exact COMMITTED_STATE_VERIFIED_READ_ONLY and STOP15,
   original marker/journal/attempt/evidence preserved and no replay authority.
3. Execute `render_dispositions(release-proposal.json)` once while stopped.
   Install pinned writer and `render_campaign_install` while STOP15 remains.
   Read back function bodies/owners/ACLs, role memberships and schema privileges.
   Failure rolls back the current transaction, leaves STOP in place, and stops.
4. A fresh READ ONLY transaction invokes `manifest_from_readback` with the final
   distinct operational REVIEW reference, retaining its exact output. Compile
   `render_release` from that output. Execute once; fresh readback must show
   STOP16, both stops clear, same manifest hash and restored temporary privileges.
   Unknown commit means independent reconciliation before any further phase.
5. Under `tameside_candidate.enabled(policy)`, use the existing owner registration
   entry point once. It rechecks the actual session, installed function and STOP
   before temporary capability, then independently reads back restored grants.
6. Existing restricted runtime only (no owner credential in worker environment):
   `timeout --signal=INT --kill-after=5s 960s python -m
   verification.ingestion_storage.tameside_candidate --policy <sealed-policy>
   --period <canonical-period> --output <fresh-directory> --hostaddr <bound-address>`.
   These named files/values MUST be sealed from the existing owner checkpoint;
   this displayed command is not yet a dispatchable pinned operational command.
7. Separately read committed capture, screening and backlog records, distinguish
   new unique listings/updates/rejections/unresolved outcomes, and verify artifact
   hashes. Qualification, admitted Applications and saved facts are separate,
   only reported if evidenced. Verify authority invalidation, sessions, original
   restricted-role settings and provider/process cleanup. A failed/uncertain
   run stops; expiry and an empty session list alone do not prove process closure.

Limits remain: one batch/run; source 10 requests, zero retries, six pages/five
rows per page, 3 MB, 45s source worker/60s supervisor; existing aggregate runtime
960s including closure reserve, database, memory, byte and publication limits.
Do not widen the window, manufacture a qualification target or infer completion
from a successful job. Preserve partial coverage and failed captures.

## Remaining binding dependency / recommendation

**GO for distinct review of this offline integration; NO-GO for an operational
approval or dispatch.** The available v1.4 receipt pins database identity and
Bolton STOP14 state, not the existing owner-side restricted runtime configuration.
The final policy needs the real retained route/address, browser/resource profile,
restricted credential lifecycle and intended runtime target/build binding. The
joined test supplies those as explicit fixtures; it does not resolve them live.
The frozen #213 owner launcher also names its original period/job command, so it
must not be dispatched unchanged for this new period.

Single next dependency: recover the existing private owner checkpoint's non-secret
runtime binding through the existing owner route, then finish its narrow command
adaptation and seal the policy/manifest recipe and dispatch command against this
candidate. Do not invent a new credential/store, repeat the consumed inspection,
or request generic offline approval. If the checkpoint is unavailable, report
that exact access limitation and retain NO-GO. No owner operational decision is
requested on this incomplete binding.

The final owner decision must cover the complete pinned sequence above, including
mechanical post-recovery manifest sealing, existing restricted access activation
and restoration, one Tameside batch and independent readbacks; it must not be
misrepresented as already granted by the historical risk acceptances.

Follow-on scope remains all ten: Manchester, Bolton, Tameside, Bury, Oldham,
Rochdale, Salford, Stockport, Trafford and Wigan. Initial fallback 15 September
2026 through the bound London execution date, <=7-day windows, current day partial.
Trafford remains required but unqualified for live execution; no dummy contract.

### Exact checkpoint-access boundary found

The signed-in Render owner shell is still available on instance `xgxgz`; no
terminal command was submitted. This is not a login/access-framework failure.
Pinned #213 `owner_pilot.Journal.load()` retrieves the retained checkpoint from
`ingestion_intake_owner_state`, then decrypts it locally using the existing
protected owner configuration. It is not a repository file or ordinary provider
log. Therefore obtaining its omitted runtime fields requires a production read,
which this offline instruction does not authorise. The consumed v1.4 receipt
cannot substitute for that checkpoint or authorise another read.

The smallest prospective retrieval is the existing NULL-body read branch:

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '3s';
SELECT ordinal, body, sha256
FROM public.ingestion_intake_owner_state(
 'b-bolton-20261103-1105-01_owner',
 '65ea9cfb9eb260a54b728d1de44eb4d7', '', NULL::bytea);
ROLLBACK;
```

One existing owner connection, five statements, 20 seconds including rollback
and close, maximum 64 KiB returned, no retry. Before decryption require journal
SHA256 `a5ba6be74c47eea89bd5068111bf3bc65198c8b4fd54c5036394a2c512f55c52`.
Use the pinned decoder; output only allowlisted non-secret profile/route,
deployment/configuration identities and closure-verification fields. Never print
or publish the ciphertext, passwords, tokens, private environment or full state.
A differing/missing hash is a STOP, not permission to follow another journal.
Record rollback acknowledgement separately from connection closure. Any future
execution needs a pinned bounded launcher and separate explicit read authority;
this SQL is preparation only, not a submitted command or ready live approval.

This would decide whether the existing runtime binding and restoration path can
be reused in the exact first-Tameside package. It would not prove a new deployment,
current provider process containment, fresh source qualification or population.
Alternatively REVIEW may accept a fully specified checkpoint-read/bind step as
part of the eventual single operational sequence; that choice must not be
silently substituted for the requested pre-pinned configuration.
