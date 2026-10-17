# Complete finite storage controller — owner execution handoff

Stage4 OPEN. Production installation, mapping, activation, fixed storage test and teardown NOT RUN. This checkpoint is implementation/readiness, not storage or operational pipeline acceptance.

## Exact identities

- PR123: https://github.com/maxrose26/PropertyAIgent/pull/123
- Independently reviewed candidate: 5091b62ffe6f0b59606f809872de2a23f6646a7d
- Integrated master: dd6a94c171c7658b5c699c526d19e345fa6bef7b
- Exact candidate/integrated tree: e961cdd375f89e2d254581dbfb9864087f583336
- Prior accepted master: 1088bc35def340f4b8ce9b5ec904e55bfb0fd605
- Prior durable evidence: 33c195865cbc1ec35a3fc2bab11696e76e69eabc
- Nine exact-head candidate checks PASS. All seven exact integrated post-merge checks PASS (CHECKS.json).
- Expected-head [skip render] merge, unchanged reviewed tree. No deployment invocation.

## Completed capability

One owner-local CLI now covers bounded prerequisite checks, exact installation and fresh committed catalogue readback, existing 48-random-byte/SCRAM helper, exact restricted activation, fixed three blocked items and control, duplicate no-op, eight real-role permission denials, two fresh committed readbacks, exact non-destructive revocation, two secret deletions/metadata absence check and positive owned-process/socket closure.

One cumulative supervisor covers machine GitHub checks, DNS, database and secret-store operations. It holds two seconds inside the240s ceiling for process closure and30s against earlier phases for teardown. Shared13-attempt connection counter; only one open SQL connection. Existing source route, CA/verify-full, SQL, manifest, runtime restrictions and Salford stop preserved. No source, application/factual, scheduling or operational consumer API is invoked. Issuer/releaser remain dormant.

The parent fsyncs a bounded hash-chain journal before acknowledging the next effect; fixed directory creation is exclusive. Per-role credential transaction and secret PUT intent/ack are distinct. A missing acknowledgement/abandoned process is not permission to repeat. No automatic resume, destructive rollback or secret compensation. Fixed safe reason codes and SQLSTATE are recorded without raw SQL/exception/credential text. Only final supervisor acceptance following closure is authoritative. Password-null proof in production is the acknowledged exact revoke transaction; catalogue readback independently checks NOLOGIN/memberships/session absence. No pg_authid/password/verifier retrieval is required.

## Focused validation and actual measured scope

-26 local focused tests PASS (new pure fences + affected existing credential helper tests).
- Exact candidate PostgreSQL run39018877018, number161, attempt1, job117356505407 PASS.
-20 tests; zero failures/errors/skips; suite19.245s, including existing affected provisioning/permission contracts and new controller/supervisor tests.
- Actual native worker+supervisor complete path:0.522796186s, peak owned RSS196009984bytes, zero live survivors, CLOSED, exit0.
- Complete SQL sequence:7 connections (2 provisioning +4 restricted +1 teardown);134 driver commands in disposable path,40 storage and10 teardown; active DB0.064319703s (storage0.025993049s, teardown0.005990152s);9379 serialized returned database data-value bytes; zero open connections at completion.
- Production helper's additional exact migration-identity SELECT is counted at runtime; disposable134 is not falsely asserted as production usage. No driver/server internal function statements are hidden as claimed separate calls.
- Full-worker journal97435bytes; reported fileSHA2560811774f0c7f8b0a409e9cd0c3c85bc8d3e67f9f808b04a2ab1a7156e7b81341; chain head2176d4442ba5e0860f45863126d8a9884241ae0cfdb4395e136d53e3b46bc872. Separate direct-sequence journal95722bytes, SHA256779096673b0c6df3707be8d68d7f57935d49db4e70281e3a5ade4ef3922bf5fd. These checkpoint identities are JUnit-recorded fixture measurements; original individual journal files are not included in the hosted artifact. The original XML/ZIP are retained below; production journal remains on the owner's durable Linux filesystem and must be archived after execution.
- Real non-superuser CREATEROLE installation, real restricted logins, full3+control readbacks, duplicate no-op,8 SQLSTATE42501 denials,0 attempts/grants. Disposable bootstrap independently verifies NULL passwords after revocation and protects fixture IDs1504–1508.
- Interruption after installation/mapping/seed/before-revocation; lost installation and revocation COMMIT acknowledgement; ambiguous secret PUT/deletion; real process death after committed seed; exclusive no-replay latch; deadline/STOP/orphan cleanup cases PASS.
- Real worker uses the production supervision/limits/pipe code. Disposable DNS, transport, GitHub secret-store and migration-principal bindings are fixed fixture replacements. No real provider/GitHub secret mutations or production database connections occurred. Actual production TLS/custom-login/pooler session closure and API permissions remain live acceptance conditions.
- Received source-body bytes/source calls are zero. Returned data-value serialization is not wire traffic; no total network-byte claim.

## Archived original evidence

- Artifact12095922371: ingestion-provisioning-disposable-5091b62ffe6f0b59606f809872de2a23f6646a7d
- Original ZIP64571bytes, SHA2567198177cac15c4914d2edf3a98a010ca56e2da9b8be15eb9453dc93d52ca933f, downloaded bytes verified.
- Extracted provisioning XML51868bytes, SHA2562d3d953ad313d4f250f82cd525ccda9c59ebe8e7450ec31050db88688c9367d1, parsed20-test PASS.
- Files postgres-original.zip and postgres.xml preserve original artifact independently of hosted expiry. No raw logs are archived.
- Independent review PASS for final candidate 5091b62ffe6f0b59606f809872de2a23f6646a7d, including final closure delta; conditional on exact-head gates, which passed. No reviewer edits/production operations.

## Registration retirement and successor

The mapping-only registration SHA256e685c79086758f5b52bf5ceff5a8ad34fb2d9e2598e8670485b3ce3a07d7252d is explicitly RETIRED_UNUSED because its binding does not cover the complete controller. Original content/history/expiry preserved. No authority was consumed, reset, duplicated or expanded.

- Successor registration.json SHA256: 802a4eae09ec897c1cc9c27704abeb9f6913eaeb919252ed64e98a452a055279
- Bound integrated revision: dd6a94c171c7658b5c699c526d19e345fa6bef7b
- Expiry: 2026-10-18T08:54:58.469465+00:00 (18October2026,09:54:58BST).
- Authority: AUTHORISE_RESTRICTED_INGESTION_CREDENTIAL_MAPPING_ONCE_20261016, same existing finite allowance.
- State: UNUSED; NOT INVOKED. Owner command may run only while valid and with existing migration credential privately available. No new PAT/stronger account/credential replacement.
- Budget:240 supervised seconds/13 connections/256MiB owned worker+children RSS/2MiB total exported evidence; storage40commands/8connections/30active DB seconds; teardown10commands/10active DB seconds. Sequential, no reset/borrowing.

## Owner-local next step

Keep the already verified WSL/keyring session; update the existing clean checkout to dd6a94c171c7658b5c699c526d19e345fa6bef7b. Create the minimal external Python venv from verification/ingestion_storage/owner-requirements.txt (accepted lock versions). Download this credential-free registration from this durable evidence commit to an external file, verify its pinned hash and run the exact storage_controller CLI once with explicit authority/risk/revision/binding/hash. The existing migration URL is accepted only through the original hidden getpass prompt; never in chat, argv, files, environment or logs. If it is not available in the owner's trusted store, do not invoke the controller or reset credentials; report that concrete dependency.

Return final sanitised JSON and credential-free events.jsonl. Do not rerun on failure. Fixed latch/audit path: ~/.local/state/propertyaigent/storage-acceptance-once-20261016/. STOP file or Ctrl+C requests supervised stop; unknown persistence or incomplete teardown stays uncertain and requires bounded read-only reconciliation, no automatic mutation. The journal is necessary evidence, not independent proof of an unknown commit.

## Separate positions

- Provisioning/storage/teardown: not yet executed in production.
- Storage implementation: independently reviewed, integrated, disposable proof complete; all seven post-merge gates PASS (CHECKS.json).
- Operational pipeline activation: held. No source authority, Bolton exception activation, Salford release, new candidate/B2, unit facts or backlog completion claimed.
- Ticket SU-511198 remains open; no provider redaction confirmation claimed. Accepted finite two-login retention risk only.
- IDs1504–1508, all historical seals/consumed authorities and blocked scopes preserved. Stage4 remains OPEN.
