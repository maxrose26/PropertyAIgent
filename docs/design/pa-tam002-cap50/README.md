# PA-TAM002 — scoped 50 KiB STOP15 continuation amendment

Stage 4 OPEN. Owner authority: Issue214/comment6970516113. Installation and
continuation require independent acceptance of this exact package; this file
is not itself execution evidence. Scheduled engineering stays paused.

## Exact identities and scope

Owner executable: d79d29c138a8414ab40b52e02f9f8c749b6b695a.
Worker: dd36ba711932e9f831daf7e885e40447be43d41d (unchanged).
Frozen owner adapter/codec: f027ba28af69ae70208eab5ed047e4a8a81c6337.
Package commit and index SHA256 are in the linked PR handoff; index.json binds
all files and the exact owner source hashes. Old v1.5 package remains historical.

Only S4_FINITE_677f555670666bcf21f45860_owner admits encrypted bodies up to
51,200 bytes. Every other namespace retains its original ceiling, including
the existing historical 36 KiB exception. Original row18 hash
0e6d08aa0b6e04c669998a828924e30322bab4ac73a0cf157a9d63b5fac955af,
all history, 64 total rows, normal ordinal47, 16 cleanup snapshots, cleanup
growth6,937 and margin1,024 are unchanged. No worker change is caused by this
amendment. The previously accepted stopped replacement of9524503 withdd36
remains necessary for its already-reviewed private-finalisation correction.

## Why this closes the capacity gap

The original encrypted ceiling and cleanup reserve rejected the larger retained
STOP15 state. The scoped Vault reader/writer and SQL function now share50KiB,
while the frozen codec and metadata/integrity/CAS rules are retained. The used
namespace is upgraded rather than installed again. Inspection, replacement
recovery and cleanup all retain the compatible reader.

Two old metadata-only saves are coalesced: retained deployment binding joins
its existing STOPPED_BUILD_READY checkpoint; terminal job observation joins
its independently read outcome. No consequential operation loses its prior
intent. Failed terminal/outcome reads preserve evidence in cleanup snapshots.
This offsets the two upgrade rows without increasing any row allowance.

## Ordered procedure and independent readbacks

Use the existing authenticated Render owner route, workspace
tea-d9qbf8jm8hqs7385cu0g, owner service srv-d9qbl7qjnfac73d8nieg.
The collection target remains crn-d9sv93vavr4c73f98rb0. Verify exact current
instance, retained receipt files, no active operation, unused binding/submission
and clean pinned checkouts before effects. Do not infer current DB state from
these dated documents. Preserve original receipts and elapsed binding.

1. Run `inspect` with the new owner executable. It independently checks archive,
   exact row18 (or matching upgrade-intent/ACK rows19/20), STOP15, historical
   dispositions, installed functions, owner permissions, disabled logins and
   absence of active work/sessions, plus actual provider restoration/deployment.
2. Run `prepare` once through the existing receipt transport. It performs the
   guarded capacity upgrade before binding and replacement: persist/read back
   row19 intent under32KiB; lock/recheck exact STOP15, row18 and row19 hashes,
   old function, work and sessions; change only the selected SQL ceiling;
   restore temporary capability/schema permissions; independently verify exact
   function fingerprint/ACL and permission restoration; append/read row20 ACK
   with the capacity marker and reserve policy. Never write larger checkpoints
   before this independent readback. No downgrade below persisted sizes.
3. Still in `prepare`, bind exactly once at actual t and prove remaining state
   capacity before saving; perform the existing journalled stopped corrected
   deployment and exact environment/configuration restoration. No recovery,
   historical disposition, namespace initial-install or private writer repeat.
4. Independently read the prepared checkpoint and exact deployment. Complete
   current provider-boundary observations through the existing approved route,
   not caller assertions: actual env-group/secret-file/inherited credential and
   overlapping activity facts. No secrets in public receipts. Keep the existing
   private observation file. Verify current DNS includes18.169.28.97; preserve
   TLS hostname/full certificate verification and no alternative address.
5. `run` reopens the same binding/artifacts. Install campaign once and verify
   exact function body/owner/search path plus only non-grantable EXECUTE for
   postgres and ingestion_worker. Locked conditional release toSTOP16,
   independent manifest/controller readback, restricted registration/activation,
   filtered HTTP handoff and exactly one durable job intent/submission follow.
6. Read capture/private-final evidence independently. Report retained records,
   screening outcomes and discoverable backlog separately. Qualification and
   saved facts remain NOT_CONNECTED unless separate evidence demonstrates them.
   Run cleanup/restoration and independently verify expired/closed authorities,
   disabled logins, zero matching sessions, restored settings/memberships and
   exact original provider environment/configuration/suspension.

The existing command entry point, run from the pinned owner checkout, is:

```sh
python -m verification.ingestion_storage.tameside_stop15_run \
  --action ACTION \
  --runtime-root /tmp/pa-stop15-worker-dd36 \
  --frozen-root /tmp/pa-tam002-owner-f027ba28 \
  --approval-ref https://github.com/maxrose26/PropertyAIgent/issues/214#issuecomment-6970516113 \
  --review-ref EXACT_INDEPENDENT_PACKAGE_REVIEW_REF \
  --observation-file EXISTING_VERIFIED_PRIVATE_OBSERVATION_FILE
```

ACTION order: inspect → prepare → inspect → run. `cleanup` is independently
available after interruption. `upgrade` permits isolated reconciliation of the
same durable intent, never a second upgrade. The existing terminal transport
must record ACK/completion tied to command/build and independently read them;
uncertain submission requires reconciliation, not a new invocation.

## Interrupted upgrade / deployment

If SQL commits and row20 fails, row19 and the new function are retained. Reopen
with this compatible reader, independently check exact function/permissions,
then acknowledge without repeating SQL. Unexpected hash/state stops. After
latest binding time, inspection/containment remain available, but this upgrade
entry point refuses new ACK/continuation; preserve committed state for a precise
owner decision. Never erase history or downgrade to the old incompatible writer.
A replacement deployment interruption uses the original retained restoration
baseline. No blind repeat of resume, collection POST or uncertain SQL.

## Finite authority and unchanged limits

One Tameside RECEIVED15–21September2026 inclusive batch; max_runs1;10source
requests;zero retries;six pages of five;3,000,000source bytes;45source seconds;
60supervisor seconds. Existing aggregate/provider/access budgets remain exact.
Fresh binding must still be unused. Bind by18November2026 19:25London;
submit by t+600;runtime expiry t+1915;access/cleanup deadline t+2100 and no later
than20:00London. No automatic extension/rebinding/replacement submission.
Manchester, Bolton, Tameside, Trafford and the other six Greater Manchester
councils remain the all-ten follow-on scope; this amendment does not activate it.

## Evidence and limitations

Six focused codec/policy/deadline tests pass. Joined disposable PostgreSQL uses
the actual owner continuation from retained-shaped partialSTOP15, encrypted
archive,78deployment inventory, old allowance boundary and installed functions.
Explicit substitutions: synthetic secrets/ciphertext identities, local database
name/route and source-derived disposable issuer inventory, simulated provider
and source responses. Zero live source requests. Production credentials,
current provider/DB state, portal response/completeness and retention are not
established by these tests.

Success: one synthetic retained/screened/backlog record, CLOSED;6cleanup
snapshots;finalordinal52. All29normal projections (2upgrade+27remaining) and16
cleanup projections fit. Largest projected encrypted normal24,668bytes;
cleanup33,332bytes;cleanup headroom17,868bytes. Actual maximum saved23,196bytes;
serialized saved capacity report518bytes. Old-contract row19 plaintext12,605bytes.
Actual production values must pass the same measurement; these are not invented
live population counts. Exact per-row measures are in none.json.

SQL boundary tests accept51,200, refuse51,201; historical namespace refuses32,769;
wrong namespace refuses; test transactions roll back. Lost upgrade SQL ACK plus
failed ACK checkpoint reopens row19 and writes row20 without second SQL. The
failure receipts separately cover uncertain submission/restoration, reopened
cleanup and missing-job containment with no resubmission. Tests preserve history,
permission restoration and all cleanup reserves. Hosted validation and exact
independent acceptance must be linked before production continuation.
