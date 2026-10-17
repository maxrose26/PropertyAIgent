# Required operational acceptance and separate optional writer decision

Status: PREPARED, NOT AUTHORISED, NOT EXECUTED. Stage 4 OPEN. Base storage acceptance at `14446a64073bd190aff40b337b3111d515408282` is reused, not repeated. Integration, final checks, measurements and file hashes are recorded in the companion evidence manifest.

## Decision A — required capture and queued screening

Approve one owner-supervised invocation of `verification.ingestion_storage.operational_runner`, bound to the final integrated revision/tree, controller and dependent-file SHA256s, CA, manifest, exact original control state, evidence-branch head and a newly specified expiry no more than 24 hours away. The held registration is deliberately rejected by the runner. No existing consumed registration is reused.

Scope: Bolton ordinary Idox/Requests listing, RECEIVED **16 October 2026**. Europe/London civil interval `[2026-10-16T00:00:00+01:00, 2026-10-17T00:00:00+01:00)` equals UTC `[2026-10-15T23:00:00Z, 2026-10-16T23:00:00Z)`. One observation, no replacement or retry. This fixed historical day is not current catch-up. Qualification SHA256: `1833eb7349dda9b1dceb0924abd7380b2f24e591e13ad34ec37dd8e4763df3f2`. Exact listing contract: `bolton-received-idox-coordinator-v1`.

Order: exact checkout/registration/kernel checks → hidden existing migration URL input → bounded endpoint/TLS/identity/privilege/control preflight → install operational functions only → map two finite restricted credentials → exact activation gate → owner-register one capture grant and exception → credential-free source worker → immutable Git capture/readback → ledger capture receipt → at most twelve five-row materialisation/screening tasks → revoke own grants and credentials → actual database/session/secret readbacks → durable pending-closure report → native closure verification and final local receipt. Base storage installation and three-item test are not rerun.

### Permissions and credentials

| Principal | Permitted capability | Explicit boundary |
|---|---|---|
| Existing migration `postgres` | Exact checked non-superuser migration contract; install reviewed functions, create effect login, finite owner registration and teardown | Existing CREATEROLE/CREATEDB/BYPASSRLS flags do not transfer to runtime. No stronger fallback. Temporary owner/releaser self-memberships are transaction-scoped and positively checked removed. |
| `ingestion_worker_login` → `ingestion_worker` | Reviewed claims/fences/checkpoints/completion; qualified ledger reads | NOBYPASSRLS, no owner/admin/issuer/releaser membership, no arbitrary table mutation or application access |
| `ingestion_effect_login` → `ingestion_effect_broker` | Fixed trusted broker operations for retained capture and exact child materialisation | NOBYPASSRLS, no direct ledger SELECT/mutation, no application access or authority issuance |
| `ingestion_storage_login` | None | Remains NOLOGIN/password NULL; no storage seed execution |

Production routing usernames are exactly `ingestion_worker_login.zcikcfgpblzuzpanpdqd` and `ingestion_effect_login.zcikcfgpblzuzpanpdqd`; native identity checks require their unsuffixed SQL roles. Endpoint remains `aws-0-eu-west-2.pooler.supabase.com:5432/postgres`, same selected IPv4, reviewed CA, `sslmode=verify-full`, no environment/config override. Runtime role connection limit 1. Worker transaction mode and trusted broker transactions retain reviewed semantics, bounded single-connection pools, no overflow, statement/lock/idle deadlines.

The grouped decision must explicitly accept possible provider-side SCRAM-verifier retention for **worker + effect only**, this finite execution. Historical worker/storage acceptance is not silently extended to effect. Generate independent passwords from 48 random bytes, initially NOLOGIN, client SCRAM and in-memory direct mapping through existing keyring-authenticated `gh`. Protected environment secrets are exactly `INGESTION_WORKER_DATABASE_URL` and `INGESTION_EFFECT_DATABASE_URL`; preserve `DATABASE_URL`. No password/verifier/URL in files, argv, repository, chat or logs. Maximum 24-hour expiry, earlier explicit teardown. Provider confirmation is not asserted; SU-511198 remains open.

Activation admits only the reviewed latent PUBLIC SELECT on `extensions.pg_stat_statements` and `extensions.pg_stat_statements_info`, exact extension version/dependencies/definitions. No extensions schema USAGE, query-text retrieval, monitoring/reset/admin capability or wider exemption. Unexpected effective privileges stop activation. Real restricted-login denial checks are part of the disposable proof.

### Resource contract

| Phase | Hard ceiling |
|---|---|
| Capture plus all queued processing/recovery | 1,040 driver commands; 40 connection attempts; 4 MiB returned DB data-value bytes; 300 aggregate supervised seconds |
| Queue slots | One capture slot, at most twelve five-row batches; existing per-slot 120 commands/16 attempts/165 seconds, subject to remaining aggregate and closure reserves |
| Listing source | One observation, 10 attempted requests, 3,000,000 received-body bytes, 500,000-byte per-response cap, 6 pages/60 rows, 45 worker seconds; no details/documents/models/parents |
| Proposed separate administrative lifecycle | 240 supervised seconds, 13 connection attempts, 240 driver commands, 1 MiB returned DB values; normal caps reserve teardown/diagnostics |
| Processes/output | 256 MiB controller including gh descendants; 1 GiB source; 1.5 GiB aggregate kernel-enforced, swap zero; 512 KiB worker audit, 2 MiB combined output; 480-second outer scope, 450-second work and 475-second diagnostic/closure deadlines |
| GitHub | At most 40 CLI invocations, each bounded; not a claim of 40 HTTP requests (`gh secret set` uses its supported internal public-key/encrypted-write sequence) |

The global 480-second ceiling still applies: the phase maxima are not additive entitlements, and the controller may stop earlier to preserve closure reserves. The new administrative phase requires approval; it does not replenish consumed storage authority. No borrowing or resetting limits across slots, artifacts or reconstructed controllers. Setup/test assertions are separate from measured operational counters. Received source-body and returned DB data-value accounting are **not total network traffic**. Request/response-size/time/process caps bound remaining unmeasured traffic.

### Stop policy, durability and recovery

Initial owner preflight requires the retained `STORAGE_TEST_STOP`, original Salford stop/run `38884069913`, exact checkpoint hash and generation zero, with no active grants or prior exceptions; subsequent screening registration retains this execution’s capture grant/exception. Registration creates only the exact expiring Bolton contract/task exception; workers cannot create or extend one. Salford remains blocked; its historical cause is not inferred. Every subsequent hard stop invalidates the exception atomically. Persistence, security, identity, accounting or cleanup uncertainty remains a global stop.

Source capture is published to the existing evidence branch with expected-head/fast-forward checks and committed-path raw-byte/hash readback **before** the ledger receipt. Immutable row membership drives five-row tasks. Oversized/ambiguous/truncated/partial evidence is preserved or explicitly blocked; never silently truncated or reported complete. Literal citations, wording and provenance remain unverified leads; no target council/site/phase/progress is inferred.

Sealed progress and cumulative receipts survive a bounded pause between completed batches; the wrapper rehearsal constructs a fresh Runner from that checkpoint. This is not proof of autonomous recovery from an intrabatch source/write crash, which remains fenced and reconciliation-controlled. Reconstructed queue processing uses the same retained checkpoint and cannot call the source. Completed tasks and duplicate delivery preserve prior effects. The proven recovery keeps the trusted owner supervisor and credential material in RAM; loss of that supervisor, unknown persistence or uncertain secret acknowledgement requires reconciliation, not automatic re-provisioning or source replay. Queue membership/dependency completion grants no authority.

Owner pause/stop: create `~/.local/state/propertyaigent/operational-capture-queue-once-20261018/STOP`. Do not delete it or rerun. On failure the controller collects bounded actual non-secret role flags/password-null booleans/memberships/session IDs/control summary and exact secret-name presence, before verdict. Uncertain effects stop subsequent mutations; no blind retry or compensating cleanup.

### Teardown and evidence

Expire only this execution's grants; preserve records, capture and outcomes. Set worker/effect NOLOGIN and PASSWORD NULL; remove exact capabilities; verify login/password-null/membership/session state. Delete exactly the two temporary mappings with acknowledged 204 responses and complete names-only absence readback; preserve `DATABASE_URL`. No automatic deletion of unresolved work or evidence. Partial teardown is reported with exact remaining actions.

The durable runtime report is explicitly `CLOSURE_PENDING` until native process/socket/cgroup checks finish. The final owner-local receipt supplies positive CLOSED evidence and the complete journal hash/chain head; its publisher-acknowledgement/final-closure suffix must then be reconciled and archived, not inferred from a pending Git report. No recovery depends on expiring hosted artifacts. Historical UNCERTAIN classifications remain unchanged.

Pass: qualified enumeration, full saved capture and row-bound proposal coverage, completed truthful screening, certain cumulative accounting, access disabled and CLOSED closure. Explicit zero is discovery-only and does not exercise screening. Missing/ambiguous proposal coverage is PARTIAL; caps/unsupported shapes are blocked. No application or factual writes occur under Decision A.

## Decision B — optional, independent admission/B2 allowance

At most **one** supported, genuinely new candidate from this exact retained capture, only after completed deterministic screening and exact capture/row/batch hashes are available. No eligible nominee means no admission and no replacement retrieval. Decision A runs and tears down independently; it does not create or activate any application-writer principal.

Reuse the accepted `operational_controller.execute` retained-capture seam, shared discovery admission/uniqueness and B2/committed readback, existing COUPLED status contract. Unit facts remain UNKNOWN/outside scope. No pending identity before qualified detail evidence. Existing identities remain preserved. Uncertain application persistence blocks subsequent writes and needs separate reconciliation across application/ledger transactions.

Separate ceiling: 120 commands/16 connection attempts/165 supervised seconds, at most two detail requests/2,000,000 received-body bytes/45 worker seconds, existing response/process/output/job ceilings. Do not spend capture allowances again. Accepted PostgreSQL proof is reused: success 74 commands/3 connections, duplicate continuation cumulative 96/5, race 73/3, uncertain 59/3 followed by denied subsequent claim; none proves production unit extraction.

The separately reviewed `docs/design/ingestion-operational-acceptance-20261016/application-writer.sql` specifies exact application insert columns, status-verification update columns, lifecycle inserts and sequence use; no unit columns, ownership or RLS bypass. A new finite application login/credential and its accepted residual-risk scope, actual application-owner grant options, exact nominee authority, fenced factual task, exception binding and teardown must be released separately. **No optional writer CLI or credential is enabled by the required runner.** Candidate identity cannot truthfully be frozen before Decision A; the optional production invocation remains held until that data binding and separate permission decision. This does not block required readiness.

## Owner-local invocation after grouped release

Reuse the completed WSL/keyring/checkout preparation. Do not authenticate again. The external registration is released only after approval with exact integrated revision/tree, file hashes, evidence head, original expiry, and SHA256; a held template is not executable. No migration credential is entered during preparation.

```bash
cd "$HOME/stage4-owner/pr122-storage-acceptance"
test -z "$(git status --porcelain)"
# Fetch/switch only to the exact integrated revision in execution-identities.json.
"$HOME/stage4-owner/storage-controller-venv/bin/python" -m pip install \
  -r verification/ingestion_storage/operational-requirements.txt
# Download the separately released registration blob and verify its SHA256.
exec systemd-run --user --scope \
  --unit=propertyaigent-operational-once \
  -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 \
  -p OOMPolicy=kill -p RuntimeMaxSec=480s \
  "$HOME/stage4-owner/storage-controller-venv/bin/python" -I -B \
  -c 'import os,runpy,sys;sys.path.insert(0,os.getcwd());runpy.run_module("verification.ingestion_storage.operational_runner",run_name="__main__")' \
  --registration "$HOME/stage4-owner/operational-required-registration.json" \
  --registration-sha256 RELEASED_REGISTRATION_SHA256
```

The placeholder intentionally prevents accidental execution; release adds exact non-secret fetch/checkout/hash commands within this frozen package. The controller alone requests the existing approved migration URL through hidden local input after positive kernel and registration checks. Return final non-secret JSON and the full credential-free audit for hash verification/archival. Never return credentials.
