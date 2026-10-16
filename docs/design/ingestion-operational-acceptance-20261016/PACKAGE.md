# Stage 4 — consolidated operational acceptance package

This package follows accepted candidate 37e5eb1d6424cb5e646315a92c0ccb3ebb837234 / tree fb13619f472dab5f2b2fd5a17814fc7840f3951c and evidence 0a6688c6619b0d95f81bfdf09e0cc7d737f092b3. PR119 and its credential stop remain preserved. Master a3a698beb0542579042bbcc48e8cf7a66f13514f is unchanged. All work here is offline/disposable. No production connection, source call, credential action, installation, population, stop release, scheduling or deployment occurred.

## Independent review and corrections

Independent reviewer inspected the exact accepted tree and subsequent corrections, separately from implementation. Findings and dispositions are in REVIEW.md. Closed code findings: detail authority now commits before callback; complete target/council/envelope binding precedes consumption; only trusted broker resolves DETAIL_RECEIPT_V1; writes consume that receipt; known races/unsupported facts preserve it without overwrite; Arcus SQL source resolution uses the broker; supervisor scans the owned group after root exit, including ordinary unsampled orphans. Future autonomous/untrusted workers are outside this trust model.

The accepted shared admission/B2/qualification code is unchanged. The worker API never issues authority or releases a barrier. Exact login/owner/task/contract/revision/subject, dependencies, eligibility, lease/fence and existing allowances remain mandatory. New source intent is permitted on an application only if its exact key appears in the pre-existing grant's detail_source_keys. Queue membership and nomination alone grant nothing.

## Concrete controller

`operational_controller.execute` runs one prebound listing scope, recomputes cheap screening in the trusted controller, then considers only the nominated exact reference/source URL/source record/listing revision/screening task/factual task. It performs an existing-identity read before detail retrieval. Missing, changed, insufficient/excluded or already-known nominees produce separate discovery/screening-only or HOLD results. There is no replacement candidate, retry, parent/document/model retrieval or full legacy ingestion command.

A complete current capture is the discovery proof for admission: WindowEvidence is rebuilt from its exact retained interval, semantics, resource metrics, page terminal and hashes, rather than borrowed from another caller window. Metadata stays in the ledger and its durable archive; no pending Application is needed to retain identity/task evidence.

`operational_source.read` launches the existing qualified `idox_window.live` or `material_qualification.idox_worker` in a credential-free owned child, only after SQL source intent. No DB, GitHub or model credentials enter that child. `operational_supervisor` uses existing Linux process-identity/group-signalling helpers, samples the tree/RSS/output, enforces a hard deadline, kills/reaps owned processes and checks remaining group members. It is containment for trusted fixed code, not a hostile-process sandbox: deliberate setsid/double-fork between samples is not certified. Hosted runner teardown is final containment, never proof of a write outcome.

The only CLI supplied here is the fixed-loopback disposable rehearsal, which rejects production endpoints and production identities. Production registration/secret loading is deliberately absent while the hold remains. Runtime functions have injected engines/readers; no stronger-role fallback exists. Production engine factory accepts only the reviewed endpoint/TLS CA and named runtime users. Its worker connection uses AUTOCOMMIT for single atomic definer calls/read statements; broker and application connections remain READ COMMITTED. Broker holds the control/task lock across the shared writer. Physical connections pin and verify 10s statement / 3s lock / 20s idle-transaction timeouts, connect timeout3s, prepare_threshold=None, pool_size1/max_overflow0. No weaker TLS is used; disposable loopback alone omits TLS.

## Exact permission and credential boundaries

| Login | Membership, ADMIN=false / INHERIT=true / SET=false | Allowed scope | Denied |
|---|---|---|---|
| ingestion_worker_login | ingestion_worker | Ledger reads; exact worker_step claim/checkpoint/complete/block/intent; raise_stop | Direct ledger DML; authority/barrier/recovery; application access; owner/admin |
| ingestion_storage_login | ingestion_storage_operator | Existing fixed three-item seed + readbacks only | Claims, application effects, arbitrary table mutation |
| ingestion_effect_login | ingestion_effect_broker | Exact bound worker_step broker operations | Direct ledger/application mutation; issuer, recovery, owner/admin |
| ingestion_application_login | ingestion_application_writer | SELECT applications; INSERT identity + unavoidable ORM defaults; UPDATE status/decision/date, verification/seen watermark and existing refresh flags; INSERT lifecycle events; SELECT lifecycle id; sequence USAGE | Units, site links, proposal/type/address writes, DELETE/TRUNCATE, ledger, owner/admin |
| ingestion_recovery_login | ingestion_recovery_operator | Fixed expired-fence recovery only, if separately activated | Runtime consumer; stop release; new authority; automatic source/write replay |

Worker/source code receives neither broker nor application credentials. Trusted controller owns the broker/writer and recomputes selection. SQL worker checkpoints are bounded assertions, not independently verified facts. The runtime is not suitable for arbitrary later agents without a separate capability review. Application writer has no row-specific SQL policy; it is a trusted writer with constrained columns, invoked only after exact fenced authority. This residual boundary is explicit.

Files: existing base install/activate/three-item SQL unchanged; worker.sql is the operational extension; application-writer.sql is the exact new column capability; runtime-mappings.sql creates three NOLOGIN mappings. activate.sql is a new operational gate, not a silent relaxation of the old base gate. It verifies memberships, role flags, ambient table/schema/definer access and application column exclusions, then enables only worker/effect/application. Recovery stays NOLOGIN. Issuer and barrier-releaser remain dormant.

The application grant sequence is rehearsed using a non-superuser migration principal with explicitly supplied fixture-only grant options. Production must establish the corresponding existing table-owner/grant-option access; CREATEROLE alone is insufficient. Do not grant unrelated application permissions or use stronger credentials if it fails. Inherited PUBLIC/default grants cannot be overridden with a DENY: unexpected effective rights stop activation. The migration principal's documented ADMIN-only residual remains an administrative trust boundary, never runtime owner membership.

No secure password method is accepted yet. The targeted Supabase dependency and blocked SCRAM helper are unchanged; no equivalent-method/logging research occurred. Runtime password/secret installation must wait for its answer and concrete method acceptance. Credentials/verifiers must never enter files, arguments, output or artifacts. No live credential mappings were invoked. New runtime mapping names are a proposed extension requiring review of the same accepted secure mechanism; there is no unreviewed helper fallback.

## Frozen source proposal and honest nomination

The proposed NEW discovery scope is Bolton RECEIVED 16 October 2026, start=end 2026-10-16, ordinary public Idox advanced-listing route, zero transport retries; earliest eligibility 17 October 2026 00:00 UTC. This is a proposal, not source authority or a claim that this interval is closed/current catch-up. Later publication remains a coverage limitation. Existing qualified Bolton RECEIVED components are reused; no equivalence to other councils is inferred. No completed historical observation is repeated.

Listing qualification binds the retained independently reviewed Bolton RECEIVED artifact docs/design/stage4-discovery/evidence/bolton-window3-38545477089.json, SHA2561833eb7349dda9b1dceb0924abd7380b2f24e591e13ad34ec37dd8e4763df3f2, with count/date/identity/resource/cleanup scope only. Its historical latency/prospective recall was not assessed; the new window must independently pass current strict source-shape checks. Zero retries is a restriction relative to its old retry1 profile. No actual candidate is invented. The production nomination is UNSET because this new observation has not happened. The executable disposable manifest uses synthetic 01780/26 with real existing parsers and explicitly synthetic source evidence; that identity is NOT nominated for production.

To avoid either invented bindings or automatic authority issuance, use two manual phases within ONE observation:

1. A reviewed fixed discovery-only manifest permits that one window, root key, contract/qualification hashes, worker/broker binding, one observation allowance and no application writes. `capture` retains metadata, creates idempotent screening work and recomputes screening. Return DISCOVERY_SCREENING_ONLY, never admission/B2 acceptance. No eligible supported nominee means STOP with no replacement.
2. From that durable capture, REVIEW/owner freezes at most one exact reference/URL/key/row digest, the screening and factual task keys, existing COUPLED contract target/content digest, and one detail-source allowance/two write slots. Only the authorised issuer/owner may register those finite task bindings. The controller has no issuer capability. `execute` takes the sealed full-checkpoint retained_capture_sha256, consumes the previous capture without a listing call, and completes the selective path. A changed/missing/known/unsupported nominee ends without substitution. Protected approval alone never creates authority.

This extra exact nomination is a concrete prerequisite, not renewed generic execution approval. If REVIEW instead requires a wholly prebound one-pass test, nominate a genuine retained reference absent from the DB and freeze its listing revision before dispatch; mismatch/absence remains a truthful non-admission outcome. Do not invent such a reference from historical absence snapshots or reuse consumed Bolton comparison authority.

## Resource bindings and accounting

| Phase/resource | Hard proposal |
|---|---|
| Listing | One observation;10requests;3,000,000 received-body bytes;500,000 per response;45worker seconds;6pages/60rows;zero retries |
| Exact selected detail | At most one candidate;2requests;2,000,000 received-body bytes;existing response cap;45worker seconds;zero retries |
| Aggregate source |12requests;5,000,000 received-body bytes;90worker seconds maximum;sequential, no borrowing |
| Source worker |1GiB address-space ceiling;45CPU/wall seconds;512KiB file/audit;credential-free |
| Owned controller |165active seconds + at most10cleanup seconds;1GiB sampled per process /1.5GiB aggregate;2MiB total output;128files;zero automatic restart |
| Database controller |16connection attempts and120driver commands total, including initialization, BEGIN/COMMIT/ROLLBACK;8command reserve for closure;3s connect;one pooled connection per principal;no bulk statements |
| Job allocation |480seconds maximum:120setup +165controller +15cleanup +90evidence,90reserve. Between manual phases no worker stays alive and no open transaction/credentialed process is left waiting for approval. Source totals/observation allowance carry forward; cannot reset budgets between phases. DatabaseBudget requires prior CLOSED connection/command/active-time accounting for retained-capture continuation; an uncertain prior receipt cannot resume. Paused approval time is not active execution time. |

Actual successful controller measurement must be recorded from its final hosted artifact, not inferred from tests passing. DatabaseBudget increments before connection/driver execution and also intercepts internal protocol commands. It logs operation kinds/counts only, no SQL values/credentials. Excess normal work stops with8remaining rollback/closure slots. A larger returned listing may exhaust the DB materialisation budget: preserve its checkpoint and report partial, do not borrow or retry the source. The one-row rehearsal is not proof that60rows fit120commands.

Received-body accounting measures streamed chunks delivered by the existing Requests boundary, not total wire bytes. Allowlisted GET/POST forms, exact URLs, zero retry, finite redirects/request count, per-response and aggregate body caps, 3s/8s connection/read timeouts, independent45s process kill, RSS/AS and output ceilings constrain request multiplicity, decompressed payload, duration and resident/output storage. They do NOT establish a numeric cap on response headers, compressed framing/padding, TLS handshakes or socket traffic. Headers/parser/runtime limits are not newly certified here. REVIEW must explicitly accept this metric/residual risk for the finite canary or require a separate bounded accounting correction; do not label it a5MB wire-byte ceiling or a Supabase egress forecast.

## Existing Stage2 unit acceptance: observed limitation

The disposable test calls the actual run_extraction_for_application (including its paid command boundary using a fixture-only synthetic operator and fake provider), existing housing_mix and reconcile_scheme, then actual stage_extraction persistence into SchemeIntelligence. Synthetic documents are retained locally; no document download or real model call occurs. A separate session reads committed fields. The legacy whole-run command is never activated.

| Synthetic source | Existing committed field / Stage2 result | Acceptance |
|---|---|---|
| Granted100; proposed S73=120 | Scalars100/120 remain separate; consented assessment100 with proposed120 | PASS in disposable evidence |
| “up to200” | Scalar200; Stage2 returns precisionEXACT/value200 | **NO-GO for verified unit delivery: qualifier lost** |
| Phase2=30 | Own scoped assessment30, not parent+phase sum | PASS; no site/phase relationship is created |
| “additional20 pursuant to BASE” | Scalar20 retained as raw extraction candidate; no verified parent/baseline/delta | WITHHELD as new total or additional capacity |
| Conflicting granted100/180 | Material conflict; no resolved value | PASS |
| Number to be confirmed | Persisted NULL, not0 | PASS |

The original document retains literal “up to”/“additional” wording, but scalar persistence and current interpretation do not prove qualifier-safe factual delivery. Do not call these successful verified totals. This test exposes the limitation; it does not ratify new policy or replace the extractor. Any correction must reuse existing Stage2 semantics with independent review, not add a new extractor/field merely to obtain a pass. No production unit evidence, real provider accuracy, full scheme extraction, phase non-overlap or baseline/additional-unit proof has been established. Unit extraction remains unsupported/blocked in the operational canary; status-only success leaves unitsUNKNOWN.

## Ordered production decision and non-destructive recovery

All below remain PROPOSED/NO-GO for execution now:

1. Accept reviewed candidate/evidence; separately accept source metric and unit withholding. Parked Supabase method answer and secure method acceptance are mandatory before ANY password operation. Verify exact master/checks/workflow/manifest and unused authorities. No generic secret acknowledgement substitutes for evidence.
2. One bounded access/prerequisite gate establishes intended verified TLS endpoint, migration owner-transfer/role ADMIN rights, exact table/sequence grant options, effective ambient rights and protected owner mapping. Reconcile any existing objects by hashes; reuse exact installed work, never reinstall blindly.
3. Install accepted base once if absent; keep existing consumed Salford control untouched. Perform exact fixed three-blocked-item test and duplicate/readback/denial checks, zero attempts/executable grants. Storage acceptance is separate from operational acceptance. If any uncertainty, STOP before operational permissions.
4. Only after separate exact operational permissions/controller approval: install operational extension once, application capability and NOLOGIN mappings; compare definitions/ACLs. No authority issuer or barrier release is implicit. A future combined approval may map worker/storage/effect/application once and defer worker's final teardown until the finite operational phase to avoid redundant password setup; this would explicitly amend the earlier storage-only teardown timing. Without that approval, execute the original full storage revocation and stop; never retain usable credentials through an indefinite hold. Recovery login remains dormant.
5. The consumed Salford GLOBAL stop still prevents source/claims. REVIEW must resolve its actual failure and explicitly accept any later release; this package does not clear, bypass, waive or replace it. A provider answer, storage pass or environment approval cannot release it.
6. Freeze/register discovery-only manifest and one unused source authority after prerequisites; perform the sole observation. Persist original artifact+hashes in durable evidence, retain all rows/unknowns, report screening separately. If none qualify, finish without replacement. Otherwise exact owner-reviewed nomination/remaining allowance, then retained-capture continuation with at most one detail/admission/B2/readback. No second window or repeated discovery.
7. Compare committed application status/decision/date and verification scope, exact identity/duplicates, immutable protected existing IDs, ledger task/attempt/fence/receipt, source/DB/resources and positive owned cleanup. Outcome GO only for the exact delivered scope. Any identity, accounting, TLS, security or cleanup failure is NO-GO. Uncertain application/ledger/secret commits stop subsequent mutations and require reconciliation; cleanupCLOSED alone never proves no write.
8. Apply exact non-destructive revoke.sql, remove only test protected mappings, read back NOLOGIN/memberships and reconcile exact owned backend PIDs. Close connections and verify no owned sockets/processes. Do not delete populated applications, ledger records, attempts, seals or consumed grants. No automatic rollback/deletion; preserve all audit. Failure to revoke/remove a mapping is an explicit incomplete teardown incident.

Manual stop is an owner-created STOP marker polled by the supervisor and checked before each expensive phase/driver call, plus runner cancellation. Child death during a durable intent is reconciliation-required; no next task or auto-resume. Expired claims require the separate recovery operator and exact fence/closure evidence. A completed qualified capture may be resumed solely as retained evidence; no source replay. Existing physical/serialized capacity warnings/pauses and retention policy remain unchanged: unresolved work/essential audit are never automatically deleted.

Pipeline implementation/disposable readiness, storage acceptance, backlog completeness and operational activation are separate positions. No backlog item or discovery interval is marked complete by this rehearsal. Stage4 remains OPEN. Stages5–8 maintenance remains only an agreed direction; Stage9's autonomous monitoring/agent gate is not being implemented here. No scheduling or later-stage agents are included.
