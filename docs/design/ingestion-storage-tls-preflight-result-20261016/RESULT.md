# Successor TLS catalogue preflight — reconciled result

Stage4 OPEN. TLS/catalogue preflight completed; production storage acceptance BLOCKED. No migration, seeding, source calls, application reads/writes or factual writes.

## Exact identities

Accepted correction PR115 candidate256863357c78eb56b2ddbff99a620d5b95480670, tree67740ba24b1a09e02baaaa0f545073b114d1f28c. PR115 integration e2cfb101959ff3d0178a395fbbf7579878bbdb1a. Registration PR116 integration0a0fb5b30c41822e3a0fcba9cc08a9690ee64994; exact-hash guard correction PR117 final runtime eaed72d7d9e377d7e397b28db4e4936435ed85ec, tree697fd47af7c7fd5ced97e055f7aaed00e4fe7896. All ten correction-candidate and six final post-merge checks passed; [skip render] integration preserved.

Existing run38907801607, number1/attempt1, job116995709201, exact approved revision. Complete46-entry workflow-dispatch history contains exactly one successor, with no duplicates. Owner manual handoff followed retired browser uncertainty; no automated second dispatch or rerun occurred. Existing run was inspected after owner approval. Job13:31:44–13:32:29UTC (45 seconds), completed success. Workflow success is not storage acceptance.

Workflow .github/workflows/stage4-ingestion-storage-catalogue-tls-once.yml; blob4a4eb608e6a69eef2e1e2096859568d4647b6a78; SHA256618b2f2723b7381772a27e3af75a7ff098166b22f0d7dbaafc2a1f98e3f08684. Authority AUTHORISE_STORAGE_TLS_CATALOGUE_ONCE_20261016 now CONSUMED.

CA PEM SHA256700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7; DER SHA256807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa. Migration SHA256f790550778172adbfe1db792d20b4c4fb58298e5829f4033f269c8670dc47033 and manifest SHA2567883c1a8f99ce3e498fb73911713c3b531d4c73d20fd2524e3c9901e822e7b04 unchanged and bound in result.

Artifact12048972871,1793bytes. Original ZIP independently downloaded and verified SHA2563fb077f81a0cca9aa8bcb39d8d925ad7677ac1535df7059637e4e2eb5eb42b97, matching GitHub digest. Its sole entry result.json SHA25660144dd903e108d38008eae1f3b9e52c08be5faa31579e353976112571fc48b6. Both original bytes and extracted result retained here before hosted expiry30October2026. Final result is the retained checkpoint; earlier intent files were atomically replaced by the reviewed worker and are not claimed as separate retained checkpoints.

## Verified live result

Same approved session-pooler endpoint aws-0-eu-west-2.pooler.supabase.com:5432/postgres and existing protected credential. Native psycopg3.3.6/binary libpq180006, NullPool, no prepared statements, verify-full and pinned official provider root. Both connections report negotiated TLS. Original host is preserved for hostname verification; reviewed engine selects one DNS address once and reuses it without failover. The selected numeric address is not exported; do not claim a separately observed IP receipt. No alternative route, certificate download or credential fallback.

Two connections/attempts;23 total driver statements,19 explicit statements including both ROLLBACKs. Both readbacks show transaction_read_only=on and read committed. Snapshots2026-10-16 13:32:24.248452+00 and13:32:25.765248+00. Server version170006 (PostgreSQL17.6), current_user=session_user=postgres, databasepostgres. Same backendPID2942427 across reconnect is compatible with pooler backend reuse and is not proof of a persistent client connection or independently inferred pooler mode. Registered session route remains the accepted route contract.

Final successful worker control flow plus explicit statement accounting establishes both transaction rollbacks and connection-context exits. Pool disposed. Positive /proc/self cleanup census: accounting certain,0 new owned socket descriptors,0 live owned child processes. Final cleanup CLOSED. TLS success under the reviewed provider-root configuration is now established; this does not retroactively establish the exact cause of the original failure.

Active3.454seconds; peak RSS77,979,648bytes (74.3671875MiB); job45seconds. ZIP1793bytes/result size in SHA256SUMS verification; below reviewed30s active/120s job/256MiB worker/32KiB result/2MiB file bounds. No source worker or automatic consumer was started.

## Access blockers — no conditional migration

Required ingestion_worker_login and ingestion_storage_login roles are absent from the bounded role readback; no dedicated restricted credential mapping is established. Named ledger tables and reviewed functions are absent, capability roles absent, and bounded membership readback is empty. Current postgres has CREATEROLE, CREATEDB, BYPASSRLS, database CREATE and public-schema CREATE, but is not superuser. Those privileges alone do not prove new-owner transfer, required membership or restricted-role authentication/denial behaviour.

Current default table privileges include literal Dxtm grants for anon/authenticated/service_role (including TRUNCATE); unchanged, not authority for ingestion workers and not weakened. Reviewed migration hardening remains necessary. No permissions or credentials were changed.

Exact blockers from result:
- EXISTING_RESTRICTED_LOGIN_NOT_AVAILABLE:ingestion_worker_login
- EXISTING_RESTRICTED_LOGIN_NOT_AVAILABLE:ingestion_storage_login
- DEDICATED_RESTRICTED_LOGIN_SECRET_MAPPING_NOT_ESTABLISHED
- NEW_OWNER_TRANSFER_AND_RESTRICTED_MEMBERSHIP_REQUIRE_REVIEW

No migration or three-item test was attempted; no ledger population, executable grants or work attempts were created by this execution. Restricted-role production denials remain UNTESTED. No uncertain production commit: this execution performed no production writes. Storage acceptance and operational pipeline acceptance remain INCOMPLETE, independently of successful TLS/catalogue observation.

Smallest next REVIEW: a concrete least-privilege provisioning and protected-credential mapping decision for the two reviewed restricted login roles, including how the existing provider route can establish required ownership/membership without stronger-role fallback or worker owner membership. Do not infer that current postgres CREATEROLE makes the reviewed migration executable. Existing conditional migration authority cannot proceed until these missing conditions are established. No new live preflight/retry is authorised by this result.

Original run38894230179 remains consumed with historical cleanup UNCERTAIN and certificate cause UNDETERMINED; archived original evidence atd1bd2dd03deae268e49b3d4274c725f3b25fdf05 remains unchanged. Prior uncertain dispatch checkpoint6f42d399bc68be9e79c1328786148b2b8df55b45 is preserved; subsequent owner handoff and unique actual run now resolve the operational continuation without rewriting history. IDs1504–1508, consumed Salford stop and all held scopes preserved. No scheduling, deployment or stage advancement.
