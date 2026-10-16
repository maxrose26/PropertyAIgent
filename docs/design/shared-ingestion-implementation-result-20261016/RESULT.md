# Shared ingestion coordinator — implementation result

Stage4 remains OPEN. DraftPR113 only; no integration, production migration, production queue population, source execution or scheduling. Master remains f5a5d92c42c6708c24c9f6c6cf10d6310b1bbedf.

## Identities and acceptance

- DraftPR113: https://github.com/maxrose26/PropertyAIgent/pull/113
- Exact candidate head:1d3bc6162aa8d58907f7a2d7de00496239a4e593.
- Candidate tree:b38dc743db09cc577b40bfd2c5d8387c8f46ef8e; local equivalent4339b18d3d31ac0a85149dfaaff8fd8cd6cbb8f3.
- Independent review PASS on exact source tree;101 focused checks pass (31 new ledger/coordinator checks plus70 existing boundary/screening regressions), zero failures/skips.
- Final candidate hosted checks:8PASS, zero failures/skips.
- Disposable PostgreSQL run38888860344, job116933184474:23PASS in9.76s, including7 new ledger/B2 tests and16 existing admission tests. Original artifact12041285042 archived here; ZIP SHA256213adae348762b0a63019a2d00bce6286c565fd9c601680ee5099d6f095047d1.
- Initial candidate35919cbad2b22de3dbeedcc8a8a84d135891800a had a CI architectural boundary failure (application imports of verification modules). Corrected by explicit qualified adapter injection; architectural check unchanged. First disposablePG23PASS also preserved as historical evidence, not final revision acceptance.

## What works end to end

The same coordinator processes synthetic historical/current windows and the exact accepted Manchester14 retained receipt. Exact council/window/criteria/card identity/provenance and source resource contracts are checked through existing qualified validators; shared screening/citation code is a single implementation with compatibility imports. Bounded listing evidence is committed before application task materialisation. Metadata can be matched against a retained scope without detail retrieval. Screening occurs before any explicitly requested factual task; unsupported/insufficient work never automatically escalates. A citation remains a literal unverified lead with full wording/offsets/provenance.

Disposable PostgreSQL demonstrates listing receipt → application screening → separately authorised selective factual refresh → real existing B2 writer → independent committed readback → distinct task completion. Shared admission is unchanged and its concurrent duplicate-delivery test creates exactly one disposable Application. The coordinator itself does not automatically admit new identities or create pending Applications; factual refresh currently operates on existing identities only. This avoids creating unsupported pending records to show throughput.

Task dependencies, versions, priority/eligibility, independent task outcomes, exact finite disposable permissions, source/write reservations, bounded attempts and claims are implemented. Different tasks against the same subject can be complete, deferred or blocked independently. Dependency completion/queue membership never grants authority.

## Recovery demonstrated

- Concurrent delivery wins one atomic claim; stale fence cannot checkpoint, finish, create children or enter a write.
- Crash after durable listing checkpoint resumes by materialising idempotent children, with no source call. Duplicate/overlap receipts reuse equivalent application screening work; original dependency remains conservatively preserved.
- Crash after real B2 commit/readback checkpoint but before task completion resumes by comparing committed facts; no repeated writer or changed verification timestamp.
- Lost acknowledgement after an actual disposable DB commit leaves WRITE_INTENT and a persistence-uncertain/global barrier. No blind retry/deletion/compensation.
- Expired SOURCE_INTENT is globally blocked because resource/outcome accounting is unknown. Expiry is claim recovery, never authority to repeat a call or write.
- Unknown/security/accounting/cleanup failures block globally and record the owned task as blocked. Existing consumedSalford stop is not reclassified or released.
- Known rate-limit/source-unavailable deferral requires explicitly reviewed isolated contract, certain accounting and CLOSED source/outer cleanup. Failure checkpoint, task deferral and durable council source cooldown are atomic. Independent councils may continue; same-council source work waits. Attempts and source allowances remain finite.

## Storage/migration/rollback

Exactly two additive operational tables, outside application Base: ingestion_work_items and ingestion_work_attempts. No application/site schema redesign or infrastructure service. No automatic startup migration. Each JSON payload <=128KiB; aggregate serialized UTF-8 column payload <=32MiB; max4096 work rows/12288 attempt rows, at most3 attempts per task. Physical table/index/TOAST overhead is additional. Checkpoints are embedded durable payloads with hashes and bounded provenance; recovery does not depend on hosted artifact expiry. Larger receipts are rejected, not truncated. An external evidence-reference reader is not implemented or claimed.

Explicit install is idempotent for the matching schema and rejects mismatched columns. PostgreSQL revokes PUBLIC/anon/authenticated/service_role access and enables FORCE RLS with no policies: default deny. Tests verify migration, constraints, RLS and empty rollback. Production-role operation is NOT proven by disposable superuser acceptance.

Proposed production procedure: review exact DDL/access contract and non-secret destination; backup; explicit approved migration; verify schema/constraints/ACL/RLS; accept a restricted worker role and controller/authority binding before any population or execution. This candidate admits only fixed disposable engines/test grants; production engine admission is intentionally absent and requires reviewed operational registration. No hidden activation flag is present.

Empty rollback drops only these two tables. Populated rollback refuses destructive removal: stop consumers, revoke access, preserve/export tasks/attempts, roll code back. Never compensate by deleting accepted application/factual records. Reconcile uncertain intents before restart.

## Backlog plan (not populated)

The source candidate includes BACKLOG-REPRESENTATION-PLAN.json:401 known application metadata tasks linked to13 exact remaining scope tasks; completedManchester14 remain preserved (5related,9insufficient). These are planned work records, not401 new Applications or a coverage claim. Manchester238 remain behind the global stop; Salford117 remain unqualified after failure; Rochdale46 remain unqualified/unexecuted. No refetch or source absence is inferred.

Four separate unresolved discovery gaps remain Bury8–14Oct, Oldham8–14Oct, Rochdale8–14Oct, Tameside1–7Oct. Seven unresolved15October bridge rows remain Bolton,Oldham,Salford,Rochdale,Stockport,Tameside,Wigan. Bury15October complete andManchester15October explicit-zero preserved. Independent-onlyRochdale8/Tameside16 identities retained. Ongoing interval from16October is not made complete by queueing.

AcceptedBolton1504–1506 preserved. Oldham1507–1508 remain committed pending identities withFACTS_WITHHELD and no uncertain commits; no automatic reprocessing. Parents remain parked; Stockport factual expansion/Trafford/later agents/buyer work remain out of scope. No production workload changed.

## Readiness, limitations and smallest next decision

Pipeline readiness: offline/disposable coordination PASS, including real PostgreSQL locking/B2/readback. Operational activation NO-GO. Backlog completion INCOMPLETE (14/415 usable metadata;401 remain). These positions are independent.

Remaining limitations: no live source qualifications gained; current concrete receipt adapter is Arcus, and Idox coordinator integration needs its own reviewed adapter (existing source/admission/B2 functions preserved). The library trusts supervisor receipts and controlled adapter composition; it is not an untrusted-agent API. Production engine/role/pooler admission, a manual bounded controller/kill switch and explicit execution authority remain unaccepted. SQLite cannot prove shared B2 writer behaviour and rejects that operation. A blocked/global-stop item has no automatic unblock mechanism. No exactly-once claim spans independent factual/ledger transactions.

Smallest bounded operational proposal: after restricted role/controller/engine and migration review, a storage-only smoke with at most3 preselected blocked work items (Salford failed discovery scope, an unresolved Rochdale application metadata task, OldhamNMA/356901/26 factual-refresh hold). Zero source calls, zero Application/factual writes, no executable grants, zero attempts, <=32KiB retained payload. Verify duplicate enqueue, persistence across reconnection, exact blocked dispositions and refusal to claim without authority. This requires explicit production migration/population acceptance; it does not releaseSalford or rerun completedManchester work. Any subsequent source or factual canary requires its own finite reviewed authority. No new execution workflow is built here.
