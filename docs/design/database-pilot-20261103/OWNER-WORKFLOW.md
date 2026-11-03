# Owner-only database evidence pilot

The approved pilot uses the existing Render web service for owner control and
the existing 2-GiB cron service for one restricted daily job. GitHub publication
is NOT_REQUESTED; installation 177784553 remains suspended. P0-A, AH, admission,
extraction, refresh and wider council activation are separate.

Fixed collection: 27 October–2 November 2026 inclusive, Tameside RECEIVED and
Manchester VALIDATED. Later execution never shifts this historical window.

The owner opens `/bounded-intake`, confirms the Dashboard-only inherited-group
and isolation facts once, and clicks **Run approved Manchester/Tameside pilot**.
No database password, Vault passphrase, signing key, token or copied approval
phrase is requested. Fresh service/work/file reads are separately bound to
HANDOFF and SUBMISSION. A stale confirmation refuses; its timestamp never rolls
forward automatically. Build preparation finishes before that confirmation.

## Existing protected configuration

- Web-only DATABASE_URL: verified server-side as the reviewed non-superuser
  postgres owner, session pooler port5432, verify-full pinned Supabase CA.
- Web-only PROPERTYAIGENT_INTAKE_RENDER_API_KEY: provider secret, never exported
  to the scraper, source child, command arguments or evidence.
- PROPERTYAIGENT_INTAKE_SOURCE_RELEASE: nonsecret expected source revision,
  workflow/manifest hashes and exact preparation branch.

The owner bridge uses this administrative identity only for migration and finite
control/recovery. Collection uses generated ingestion_worker_login and
ingestion_effect_login passwords, connection limit1, the existing restricted
capabilities and server-enforced VALID UNTIL D. Expiry is not closure.

## Durable recovery and one use

The existing Vault format encrypts recovery snapshots using domain-separated
material derived from the already configured owner database password. No new
credential store or owner-chosen run passphrase is introduced. Only ciphertext
touches temporary files. Ciphertexts are append-only in the same approved
private evidence table, under the separate owner period suffix. The owner-only
interface permits at most64 snapshots of32768 bytes:2MiB private control history.
Routine worker interfaces cannot read or write this namespace. This does not
increase the source/runtime2MiB aggregate export allowance.

Initial state and each effect intent commit before the effect. Activation's exact
password/settings/membership baseline commits before BEGIN, on the phase's owner
connection; activation rechecks it inside its transaction. Transaction callbacks
do not open a second connection or acquire the controller lock. Period/access
acknowledgements and each closure acknowledgement persist after COMMIT using
that same owner connection. Compare-and-swap plus a fixed transaction advisory
lock protects private journal append, independently of the controller row.

An existing release intent prevents re-entry, regardless of paths, process loss
or date changes. Unknown acknowledgements require readback, never another build,
POST, activation or environment write. The source SQL max_runs=1 and original
ledger source-intent guards remain in force.

## Preparation, run and closure

1. Explicit approved migration: exact predecessor, dormant roles/memberships/
   sessions and generation5 guards; one atomic transaction; temporary SET-only
   owner membership/schema CREATE removed before COMMIT; exact preservation,
   function/ACL and private table checks.
2. Prepare one source artifact: durable encrypted original configuration/env;
   complete fresh work inventories; remove only the two approved unsafe build
   variables; fixed branch/build command; one resume-triggered build and no
   explicit second deploy. Verify actual revision/file/browser receipt, resuspend
   and restore exact configuration/direct variables without another build.
   Provider-managed timestamps are observations, not restoration targets.
3. At the owner's run click, verify readiness and fix D=T+2100 once,
   P=D-185; D must fit before London midnight. Issue one period and verify
   temporary issuer cleanup, activate exact roles and qualify authentication.
4. Fresh HANDOFF reads, one restricted secret/environment handoff; separate
   SUBMISSION reads and durable one-job intent. Submit only while D-now>1500.
   No provider token or artificial ageing is involved.
5. Runtime startup independently requires D-now>1500. The existing960-second
   budget and P preserve execution/closure reserve during continuation. Queue
   delays cannot obtain a new deadline. No automatic retry or replacement job.
6. Independently read terminal job and database evidence. Success requires both
   complete captures, deterministic screening and batches, durable backlog,
   byte/hash readback, finite authorities closed and VERIFIED successful run.
   Retention before projection preserves refused audits without accepting them.
7. Independently disable both logins/passwords, revoke only exact self-granted
   memberships, invalidate only this period's authorities, restore captured role
   settings, resolve at most the existing two precise sessions, and verify
   temporary owner cleanup. Restore exact handoff environment after named
   terminal evidence; verify suspension/configuration/environment equality.

The same page's recovery button stops only its owned owner process and invokes
the existing independent closure. It works after a lost page/session, partial
activation or expiry. Unknown restoration acknowledgements are GET-reconciled;
another PUT is refused. Inaccessible settings remain unproven, and OPEN is never
forced to VERIFIED. Python cannot guarantee memory erasure.

Limits: Tameside10requests/3,000,000bytes/45source seconds/60supervised seconds,
six pages of five (effective30 listings); Manchester80requests/20MiB/75source
seconds/90supervised seconds/60rows/six pages. Aggregate90requests,
23,971,520source bytes,120source seconds,150supervised seconds,960wall seconds;
2080statements/96connections/8MiB returned;512KiB each source export and2MiB
aggregate export. Existing closure reserves and exact2147483648-byte cgroup
equality remain. No additional service or larger compute plan is created.

Evidence retrieval: the owner page displays independent summary/closure. Private
source audits and pre-finalisation report/events are retrievable through
ingestion_intake_evidence_read(period,run_id,name), with stored-byte/hash checking.
Actual finalisation comes from the committed controller record; the immutable
pre-finalisation report is never relabelled as a successful final receipt.
