# One operational acceptance — consolidated preparation checkpoint

## Decision and readiness

Storage milestone CLOSED/ACCEPTED at 14446a64073bd190aff40b337b3111d515408282; do not rerun installation, seed test or owner authentication. Stage 4 OPEN. Operational execution is NO-GO at this checkpoint: below are actual integration gaps, not a renewed architecture investigation or an execution-authority request. No live activation/source call/credential change/production query/integration occurred.

GitHub master independently read back at 7cf8d32547b63d485de872afc2f717c3dce55322, tree 68bf766cda023b1f15a19a63978903995391ec46. Fourteen relevant integrated files matched Git object hashes and have SHA256 bindings in manifest.json. The attached older platform report is product context, not evidence of present coverage or a release of current holds.

## Exact proposed observation

Bolton RECEIVED 16 October 2026 only, using existing qualified Requests/Idox advanced listing route:
https://paplanning.bolton.gov.uk/online-applications/search.do?action=advanced&searchType=Application
Inclusive form start=end=2026-10-16. Civil interval [16Oct00:00BST,17Oct00:00BST), UTC [15Oct23:00Z,16Oct23:00Z). This is a fixed historical acceptance day, not current catch-up or proof against late publication. No forced expected reference/count; no replacement date if empty/unsupported/capped.

Capture once with zero retries, <=10 requests, 3,000,000 received-body bytes, 500,000 per response, 6 pages/60 rows, 45 source-worker seconds, 512KiB worker audit. Existing source process ceilings: 1GiB each/1.5GiB aggregate sampled RSS, fixed owned-process supervision and job<=480seconds. Received-body bytes exclude request/response headers, TLS/framing and are not total network traffic.

## Exact restricted roles and new approvals

| Principal | Proposed finite rights | Forbidden |
|---|---|---|
| Existing migration principal postgres | Only reviewed operational installation, fixed owner registration/reconciliation/revocation; temporary installer membership removed; non-superuser profile already accepted | Stronger credential fallback, unrelated schema/application changes |
| ingestion_worker_login | Restore only ingestion_worker membership, ADMIN=false INHERIT=true SET=false; ledger SELECT and exact worker_step / raise_stop | Issuing authority, releasing barriers, direct DML, application writes, owner/admin membership |
| New ingestion_effect_login | ingestion_effect_broker only, same membership flags; exact broker operations in worker_step | Direct ledger/application DML, owner/issuer/releaser/recovery |
| Optional new ingestion_application_login | Existing reviewed ingestion_application_writer only; shared status-only admission/B2 | Units, proposals, addresses, schemes/sites/opportunities/documents, delete/truncate, owner/admin |
| ingestion_storage_login | Remains NOLOGIN/password NULL/no memberships | Reactivation or another storage test |
| Recovery/issuer/barrier capabilities | Dormant for runtime; any finite owner action separately exact-bound | Runtime issuance or open-ended recovery login |

Application writer's reviewed ACL is SELECT applications; INSERT identity and ORM default columns; UPDATE status/decision/decision-date, verification/seen and evidence-refresh columns; lifecycle INSERT plus id SELECT; USAGE on the two reviewed sequences. The full exact SQL remains docs/design/ingestion-operational-acceptance-20261016/application-writer.sql at bound baseline. These are substantive new operational permissions, not already installed/accepted storage permissions. Its trusted controller boundary is essential; this is not an arbitrary-agent sandbox.

Finite credential method: same hidden existing migration input, verified endpoint/CA and verify-full, independent passwords from 48 random bytes, client-generated SCRAM in memory, direct existing protected-secret mechanism, NOLOGIN during mapping, <=24-hour expiry and immediate teardown. Never write/export secrets, URLs or verifiers. Runtime route usernames must be role.zcikcfgpblzuzpanpdqd; session/current SQL identity must be the unsuffixed role with NOSUPERUSER/NOCREATEROLE/NOCREATEDB/NOBYPASSRLS/NOREPLICATION.

Genuinely new approval: previous accepted verifier-retention risk and mapping authority were consumed and limited to worker/storage. They do NOT authorise another worker password or the new effect/application accounts. A grouped operational approval must name worker+effect once and application only if optional writer is included, exact protected secret names INGESTION_WORKER_DATABASE_URL / INGESTION_EFFECT_DATABASE_URL / optional INGESTION_APPLICATION_DATABASE_URL, expiry, new authority, helper/revision hashes, budgets and teardown. DATABASE_URL remains untouched. No Supabase-method research is reopened.

## Scoped stop disposition

Preserve original CONSUMED_SALFORD_GLOBAL_STOP run38884069913, checkpoint a2345cf136fc92abf13bb55772f5c14a7a299b7f2b9cb0b89fe6037ccdb8a10e and historical TargetClosedError without invented cause. No Arcus execution or Salford replay/release. Preserve existing STORAGE_TEST_STOP from accepted storage.

Proposed owner-only Bolton exception binds exact transport REQUESTS_IDOX, fixed civil day, integrated revision/controller/workflow digest/manifest, exact immutable grant snapshot, expiry<=24h and initial stop generation. At most capture, processing and optional writer exceptions; worker cannot create/extend them. Every subsequent hard stop increments generation under control-row lock and invalidates all exceptions. Security/identity/unknown persistence/accounting/cleanup remain global stops.

The existing SQL does not explicitly validate manual_stop against the accepted STORAGE_TEST_STOP while registering an exception. The final registration gate must compare exact current control state and record an explicit owner disposition of this known storage-only stop, while rejecting any other/new manual stop. Do not silently clear it or make exceptions applicable to all stops.

## Ordered execution and acceptance checks

1. Read-only exact content/ACL/flags/grant-option/ownership and stop-state preflight under a new finite operational authority. Existing production storage stays installed. Unexpected objects/privileges stop, never repair broad PUBLIC ACLs or substitute access.
2. Apply only reviewed operational worker.sql + minimal ACL/mapping changes after exact absent-or-definition-matched checks. Do not run old whole runtime-mappings/activate/revoke blindly: they create/activate extra dormant roles and predate accepted effective statistics boundaries.
3. Verify restricted denies and effective ambient permissions, including the two exact pg_stat_statements 1.11 view definitions/extension dependency/functions; no extensions USAGE/CREATE, pg_monitor/read_all_stats or reset privilege. Only accepted latent SELECT to extensions.pg_stat_statements and extensions.pg_stat_statements_info; no query text retrieved. Reject any additional object/privilege. New-role effective denial tests must be rehearsed before production credential operations.
4. Map approved exact operational accounts, activate only needed principals, and register one immutable capture task/authority/exception. Queue membership and dependencies grant no execution authority. New once-only journal, unused-history check and original expiry required; consumed storage registrations remain untouched.
5. Commit source intent before one credential-free source child. Archive complete canonical source audit to existing Git evidence branch using expected-head check, verify committed bytes/SHA256/path/commit independently, then seal receipt in ledger. Fixture commit receipts and expiring CI artifacts cannot satisfy this step. Incomplete/oversized receipt is durably retained and explicitly blocked; no truncation/refetch.
6. Freeze actual capture hash/row identities and <=12 disjoint five-row tasks/dependencies. Complete capture CLOSED before source-free processing. Each row's child creation/progress is atomic under exact fence. Read parent once per batch; retain full fields/UNKNOWNs, provenance and literal citations/offsets/supporting wording. Use existing reversible screen dispositions; citation target council/relationship/progress remain unverified. No models/details/documents/parents/application writer during capture/screening.
7. Per logical slot persist and verify cumulative counters before the next process. Completed duplicate returns completed outcome without new claim/effect. A permitted recovery requires exact checkpoint/fence, prior CLOSED cleanup, sealed cumulative spend and no unresolved source/write/secret intent. Any hard-stop or uncertain intent prevents automatic recovery and invalidates exceptions. Do not deliberately exhaust a live budget to demonstrate recovery already proved offline.
8. Optional at-most-one candidate: immutable capture+completed exact batch/screen child+row hash must bind nominee and existing accepted COUPLED Idox contract. Absent/changed/known/unsupported/no eligible candidate means no admission, no replacement retrieval and no writer-success claim. One detail observation only; confirm supported source evidence BEFORE creating Application; reuse shared admission/uniqueness/race protections, B2 and committed readback. Distinguish ALREADY_KNOWN, COMMITTED_PENDING_IDENTITY, supported status facts, FACTS_WITHHELD, ROLLBACK and UNCERTAIN_COMMIT_OR_READBACK. Units UNKNOWN/outside this proof.
9. Revoke exact operational memberships, NOLOGIN PASSWORD NULL; close handles; read actual safe role flags/password-null booleans/membership/session IDs and states before verdict. Delete only mapped temporary operational secret names with acknowledgements and names-only absence check, preserving DATABASE_URL. No drop/delete of ledger or application evidence. Any uncertain mutation stops subsequent mutations; preserve intent and require reconciliation rather than automatic compensation.

## Budgets and retained proof

Capture + all processing + permitted source-free recovery share accepted 1,040 driver commands, 40 connection attempts, 4MiB DB returned data-value bytes, 300 aggregate supervised seconds; max12 five-row batches. Each logical slot<=120commands/16connections/165seconds including closure reserve and carried recovery usage. No resource stacking, borrowing or reset by process/artifact. Combined exported evidence<=2MiB. Source and DB value-byte metrics are not total traffic.

Optional writer is separate <=120commands/16connections/165supervised seconds, <=2requests/2,000,000 received-body bytes/45source-worker seconds; at most one candidate and existing two shared admission/B2 write slots. No eligible nominee consumes no detail allowance and produces no admission success.

Previous storage 240s/13connection authority is consumed/closed, not replenished. Operational installation/mapping/owner registration/teardown must have its own measured, approved finite allocation; the old design's 240s/13connection setup envelope is a proposal, not a fresh grant. Final controller must include all installation and failure readbacks, secret operations, archival and teardown in its exact allocated counters/reserves before registration. There is currently no measured production-wrapper total for that new work.

Reuse accepted final batching proof ba4248f35b90d3d81c6895830495ee1e7147de5d:60 rows/12 batches, interrupted recovery and completed duplicate,845 commands/30connections,1,646,404 returned data-value bytes,12.376864279 supervisor seconds,133,853 exported bytes,87,044,096 peak sampled RSS; setup/assertion costs separately recorded. Three mixed dispositions20each,20 citation leads, no live source. No rerun performed.

Reuse accepted writer proof 7d626d6e9cf463147c52b3c917d0de29cd8fbfbf: success74commands/3connections; duplicate continuation cumulative96/5; race73/3, one preserved application; uncertain59/3 with subsequent claim denied despite CLOSED process cleanup. Unit facts NOT_WRITTEN. These are disposable proofs, not production wrapper acceptance.

## Preparation correction and remaining genuine gaps

One minimal candidate correction is supplied, NOT integrated: operational_controller.py now distinguishes exact project-suffixed pooler routing identity from unsuffixed SQL role, retains exact endpoint/CA/verify-full/no query overrides and checks safe current/session role flags alongside server timeouts before use. Prior integrated code rejected the exact routing username before any connection; this was reproduced offline with0connections/0commands.17 focused offline tests pass; no unaffected suite repeated. Candidate source SHA2568cc3c42cfa40cea9f4ec64d88b51bffd6a0dbe5b35273521b995f8890dcefea3, tests and JUnit archived. No independent final-controller review or complete disposable production-wrapper rehearsal is claimed.

Still necessary within this preparation scope:
- Wire the real finite production entrypoint, owner registration, memory-contained credential mapping and protected Git archive publisher to existing component functions. Current only CLI is explicitly DISPOSABLE_PRIVATE_ONLY and uses a fixture archive; it must never be pointed at production.
- Carry the already accepted exact statistics boundary into operational activation for worker/effect/optional application, validate those real restricted logins in disposable PG, and make actual diagnostic readbacks precede every verdict.
- Rehearse complete operational setup/capture-publication/source-free batches/teardown with new role restrictions and real gh against isolated fixtures, including archive/secret uncertainty. Measure new administrative allocation; reuse accepted core batching/writer evidence.
- Freeze independently reviewed final controller/SQL/CA/manifest/revision/checks and new authority/expiry only after those corrections. No run/registration exists here.

These are execution integration and narrowly scoped credential/permission decisions. No new schema, pipeline, queue service, architecture programme, scheduler or scraper is proposed. This package intentionally withholds an executable production command rather than disguise a fixture command as ready.

## Outcome reporting

Report separate SOURCE_CAPTURE, METADATA_RETAINED, QUEUED_SCREENING, OPTIONAL_ADMISSION_B2 and ACCESS_DISABLED/CLEANUP statuses. Zero rows with qualified explicit-zero enumeration is a legitimate source result, not screening-row or writer proof. Partial/capped/unknown provenance cannot be complete. Preserve all identities/evidence and all original classifications. Operational proof does not close historical discovery gaps,415 metadata backlog,unit extraction or database catch-up. IDs1504–1508 and all held scopes remain protected.
