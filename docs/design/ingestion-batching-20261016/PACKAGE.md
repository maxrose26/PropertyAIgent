# Stage 4: bounded listing acceptance successor

OFFLINE/DISPOSABLE ONLY. Supersedes the unbounded materialisation proposal, not
the accepted historical evidence or credentials hold. Stage 4 remains OPEN.
No production installation, exception, grant, secret operation or source call
is authorised by this package. PR119 and the targeted Supabase question remain
parked; no equivalent-method research or credential experiment was performed.

## Executable implementation and trust boundaries

Use `batching.capture_once` with existing `Coordinator.idox_source`, the qualified
`IdoxListingContract` and the existing source supervisor. Capture-only completes
with zero child materialisation. A trusted archive callback must publish the
complete canonical source audit to the existing durable Git evidence mechanism
and independently verify its bytes, SHA256, commit and path **before** returning
its receipt. The source worker cannot supply this callback or archive identity.
The offline callback writes/fsyncs/readbacks a disposable file and labels its
commit as a fixture: it is not proof of production Git publication. Production
controller registration must bind the protected publisher and verify its actual
commit, rather than accept the fixture receipt or an expiring CI download URL.

`batch_plans` freezes at most twelve non-overlapping five-row LISTING_METADATA
tasks, each bound to the full immutable capture hash and exact half-open row
indices. Dependencies include the completed capture and previous batch. Empty
capture creates no batches. Owner registration of exact bindings remains
separate; workers cannot issue authority, enqueue arbitrary tasks or release
barriers. Historical/current workload dates are configuration of these same
components, not a new backlog pipeline.

`process_batch` reads the full capture once per batch, not once per row. Existing
screening reads receive that verified immutable cached parent; all task state,
claims and fences remain live. Each broker `batch_row` call validates the exact
record/identity hashes and atomically creates/reuses one screening child AND
advances one progress ordinal. There is no SQL loop hiding sixty effects behind
one driver call. Batch completion requires all its children COMPLETE. Concurrent
claims, stale fences, unresolved write intents and uncertain persistence retain
the existing SQL denials and global barriers.

An interruption after committed progress resumes from the next row, reuses
completed child tasks and never invokes a source client. A fully materialised
interrupted batch re-seals its unchanged broker progress under its new fence.
Recovery requires positive prior cleanup, exact slot/capture binding and the
owner/controller-sealed previous accounting hash. Recovery permission is not
permission to repeat a source operation or writer effect. Missing/unreconciled
accounting or cleanup blocks the next execution. Completed duplicate delivery
only reads its outcome, without another claim, attempt, child or source call.

The database retains bounded receipts (128KiB call/checkpoint bounds; existing
32MiB ledger ceiling), not arbitrary source bodies. Original source audit remains
subject to the existing 512KiB source bound. A valid audit whose projected receipt
cannot fit is durably archived in full, then recorded CAPTURED_PROCESSING_BLOCKED /
UNSUPPORTED_CONTRACT. It is not truncated, screened, marked complete coverage or
automatically refetched. An oversized broker payload also stops before its
effect; preserve the original archive and reconcile the blocked task. No external
large-payload reader is claimed as implemented.

## Scoped recovery policy: implemented, not activated

`ingestion_register_bolton_exception` is callable only by the separately reviewed
owner/barrier capability. Workers/effect brokers have no registration permission.
It preserves the exact original Salford stop:
`CONSUMED_SALFORD_GLOBAL_STOP`, run38884069913, checkpoint
`a2345cf136fc92abf13bb55772f5c14a7a299b7f2b9cb0b89fe6037ccdb8a10e`.
No cause is invented for TargetClosedError; Salford and its failed Arcus scope
remain blocked and consumed. The accepted containment evidence establishes
closed owned processes/zero survivors, not an explanation of the source failure.

An exception binds REQUESTS_IDOX, exact Bolton RECEIVED16October2026 capture,
exact revision/workflow/manifest and the entire immutable authority grant snapshot
(only consumed source/write counters are excluded). Maximum three separately
registered exceptions allow capture, queue processing and later optional factual
work; an existing authority exception cannot be extended or replaced. Grant expiry
is enforced at every operation, at most24hours; registration never extends it.
JSON-null/type omissions fail closed. Every subsequent `ingestion_raise_stop`
atomically increments the hard-stop generation under the same control-row lock
used by claims/effects, invalidating **all** exceptions. Recovery of unknown source
or write intent also raises that stop. Original historical stop data is preserved.

Wrong council, interval, transport, execution binding, grant snapshot, expiry,
security, identity, accounting, cleanup or uncertain persistence is not isolated
as an ordinary council failure. It prevents continuation. The reviewed exception
is transport/process containment, not permission to ignore systemic failure.
Dormant owner policy registration itself requires later explicit approval; this
package does not activate its capability or create a production exception.

## Measured basis and proposed finite allocation

First hosted PG17 rehearsal (candidate796ae7fe88a7e2ee54c2349a978bd1dc95283c03,
run38940784987 / run145 / attempt1) delivered60 rows through12 batches, one
interruption/recovery and one completed duplicate:845 driver commands,
30 connections,1,646,386 returned data-value bytes,3.497 database-controller
seconds. Ordinary five-row slot65 commands/2 connections; interrupted slot96/5;
capture26/2; duplicate raised its logical first slot from65 to73 commands.
All owned executions and DB handles CLOSED. Final-head measured receipts are
published separately; this first result is not substituted for final validation.

| Resource | Proposed aggregate; requires production decision |
|---|---|
| Listing | One observation, existing10requests/3,000,000 received-body bytes;500,000 per response;6pages/60rows;45source-worker seconds;zero retries |
| Processing | At most12 five-row tasks; zero source/detail/document/model/application calls |
| Driver commands |1,040 inclusive of capture, processing, closure, duplicate and any explicitly permitted recovery; about23% above the measured845 |
| Connections |40 total; about33% above the measured30; no automatic retries |
| DB returned data values |4MiB aggregate; measured separately from protocol, column metadata, TLS and wire traffic |
| Active supervision |300seconds aggregate across capture and processing; each controller remains<=165seconds; each source<=45seconds; no concurrent workers |
| Per logical slot |Existing<=120commands,16connections,165DB-active seconds, including carried recovery counters; at most two claims where the frozen task permits it |
| Memory/output |Existing1GiB sampled per process/1.5GiB aggregate;512KiB worker audit;2MiB combined exported evidence;128 files per execution |
| Job |Existing480seconds per job; no open connection/process while awaiting owner nomination; each dispatch has a frozen finite setup/execution/cleanup/evidence allocation |

Proposed combined allocation: at most five480second job slots (2,400seconds
allocated wall time): provisioning/storage, capture, sequential queue processing,
one explicitly approved recovery if needed, and optional nominated detail/B2.
Queue processing may supervise multiple sequential five-row processes inside its
one job; it is not twelve new bespoke workflows. Each job reserves120seconds
setup, at most300supervision (subject to the smaller phase/aggregate allowance),
15cleanup and45evidence. Capture plus queue plus recovery share the same300active
seconds/1,040commands/40connections, not three independent copies. Provisioning
retains its separate240seconds/13connections; optional candidate retains165/16.
Maximum combined supervised reservation705seconds and69connections across all
three distinct envelopes, not permission to borrow between them. Any inability
to finish/archive/close within an envelope ends BLOCKED without a replacement.
Interactive approval time is outside execution with zero owned live processes.

`batch_allocation` validates at most13 exact logical slots and a sealed durable
receipt collection. It calculates remaining cumulative allowances before each
execution, counts the latest cumulative slot receipt once, requires CLOSED,
and fails on aggregate exhaustion. The controller passes the smaller remaining
connection/command/returned-value allowance into DatabaseBudget. A new artifact
or process does not reset a logical slot. Production handoffs must archive and
verify receipt versions/hash chain before authorising the next slot; caller
assertions or queue dependency completion alone grant no authority.

The larger active allowance is a proposal for bounded remote DB latency, not a
production measurement or increase to any existing per-job/source ceiling.
No budget borrowing from the optional admission test or provisioning is allowed.
Global received-body counters are **not total wire bytes**. Existing request,
response, timeout/process and memory caps bound received bodies and multiplicity;
unmeasured headers, TLS and transfer framing remain an explicit acceptance risk.

The original108-command one-row path included fixed connection/driver setup,
capture, metadata, screening and candidate admission/B2/readback. It was not a
per-row screening cost. New measured65-command five-row slots include broker
per-row transactions plus screening; driver initialization/BEGIN/COMMIT/ROLLBACK
are included, not hidden by batching. Fixture installation, owner registration,
synthetic-plan preparation and test assertions are reported separately from
operational counters. Hosted process import/startup is in supervisor active time,
not falsely labelled database time.

## Ordered acceptance and pass/fail gates

1. Obtain the parked targeted Supabase response and accept the concrete secure
   method. No SCRAM-in-SQL helper, password/verifier in files/logs/artifacts, new
   route, stronger-role fallback or unsupported acknowledgement. Freeze reviewed
   candidate/checks/SQL/CA/manifest and unused finite authorities before install.
2. Establish exact migration grant options/ownership transfer and ambient rights.
   Reuse the PR118 reviewed install/credential mapping/activation/revocation
   sequence, TLS and endpoint; do not blindly reinstall existing objects. Fixed
   base test remains exactly three blocked rows plus original-stop control,
   duplicate seed no-op, zero attempts/executable grants, exact reconnection
   readbacks and real restricted denials. Original240seconds/13connections/
   256MiB/2MiB storage-package ceilings remain a separate envelope. No source call.
3. Only with explicit operational permissions acceptance install reviewed
   worker.sql and existing application-writer.sql/runtime-mappings.sql once.
   Runtime logins retain no owner/issuer/barrier membership. Issuer/releaser and
   recovery stay dormant except separately approved finite owner/recovery action.
   Reconcile definitions/ACLs before activating the minimal runtime mappings.
4. Explicitly approve the exact scoped recovery disposition (not Salford release),
   frozen single capture grant and exception. Bolton civil day is
   [16Oct00:00BST,17Oct00:00BST) = [15Oct23:00Z,16Oct23:00Z).
   Conservative eligibility17Oct00:00Z =01:00BST. It is not prospective authority,
   late-publication completeness or permission to replay a historical window.
5. Capture once, archive complete source/evidence with positive readback, commit
   its bounded receipt, end source execution CLOSED. Freeze actual captured row
   hashes and <=12 batch bindings from that capture. Empty result is explicit
   zero with no batches. A payload cap means BLOCKED, not silent truncation.
6. Register only the reviewed exact source-free queue authority/exception. Run
   sequential batches under sealed cumulative allocation and stop controls;
   no source client or application writer is needed in batch execution. Recovery
   is a separate exact-fence decision with certain closed prior accounting;
   interrupted source/write intent cannot automatically resume. Read back all
   rows/progress/dispositions/citations and attempts, plus protected record/stop
   preservation. Screening is not commercial or factual qualification.
7. SEPARATE at-most-one candidate allowance: from that immutable capture REVIEW
   freezes one genuinely new supported exact council/reference/URL/key/row hash,
   screening/factual keys and existing accepted COUPLED contract. Optional bound:
   one detail observation,<=2requests/2,000,000 received-body bytes/45worker seconds,
   <=120commands/16connections/165controller seconds, existing memory/output/job
   limits and at most two reviewed write slots through shared admission/B2 and
   committed readback. No listing refetch, automatic replacement or parent/model/
   document work. Known/changed/unsupported/no candidate means no pending identity
   and no admission/B2 success. Application writer remains status-only; unit facts
   UNKNOWN. Qualifier-safe withholding is not successful verified unit extraction.
8. Stop on any uncertainty; reconcile before subsequent writes or secret actions.
   Revoke all test runtime access and remove protected mappings with exact
   non-destructive scripts, preserving rows/attempts/artifacts/consumed authority.
   Read back NOLOGIN/membership/owned backend closure. Partial teardown is an
   explicit incident, never CLOSED by inference. No automatic deletion/rollback.

Storage acceptance, operational-path acceptance, factual/unit acceptance,
backlog completion and activation are distinct. All production positions remain
NOT RUN. Existing discovery gaps,415 retained identities, parked parents and
unsupported contracts are not completed by these synthetic60 rows. IDs1504–1508,
all accepted seals and consumed authorities remain protected. No scheduling,
deployment, integration/master movement or stage advancement is included.
