# Database TLS correction — REVIEW package, 16 October 2026

Status: OFFLINE VALIDATED; successor live connection NOT authorised or registered. Stage 4 OPEN. No production calls, migration, seeding, application writes or scheduling in this preparation. Master and consumed workflow remain unchanged. Production storage acceptance remains incomplete.

## Preserved failure

Run 38894230179, number 1/attempt 1, revision 5485ab74a236232a6acf3409383364ad9a5517f6; evidence d1bd2dd03deae268e49b3d4274c725f3b25fdf05. Original artifact 12043313332, 866 bytes, ZIP SHA256 23f8e0808f63bf74621556537d60112970535de33d363ca4ce274673b5ff56b5. Result JSON SHA256 7b761613d39412ef77d692a8be3fae06892dce446718ae8d3e1e98a4315acb76. Original archive remains on that evidence commit under docs/design/ingestion-storage-preflight-result-20261016; no replacement or rerun.

Original CONNECT_VERIFY_FULL failed: OperationalError / TLS_CERTIFICATE_VERIFICATION_FAILED, SQLSTATE null, no sessions. 1 logical connect attempt, 0 returned connections, 0 explicit/driver statements, 0 production writes; 0.871 active seconds, 67,915,776 peak RSS bytes; pool disposed; cleanup UNCERTAIN. One logical connect does not prove one native handshake: libpq/psycopg can iterate DNS addresses. The old artifact did not count these.

## Cause: established facts and limits

The reviewed native psycopg3/NullPool configuration used sslmode=verify-full and sslrootcert=/etc/ssl/certs/ca-certificates.crt, connect_timeout=3, autocommit, no prepared statements. Exact approved session-pooler route is aws-0-eu-west-2.pooler.supabase.com:5432/postgres, login postgres.zcikcfgpblzuzpanpdqd. No alternate endpoint is proposed.

The configuration omitted an explicit provider CA. The published Supabase Root 2021 CA is absent from this scratch runtime's system bundle (125 certificates, 187940 bytes, bundle SHA256 a491bd3f853f9e03376786d1ef525d7421aa42aa378ef189b40f468b8619123c). This is NOT evidence of the original hosted runner's exact bundle. Its CA bytes, presented certificate chain and original detailed exception were not retained. Consequently the precise original cause remains UNDETERMINED.

| Possibility | Retained evidence and disposition |
|---|---|
| Chain trust / missing issuer CA | Consistent with generic verification failure and omitted provider CA; exact missing issuer not proved. Proposed provider-root correction addresses this configuration gap. |
| Hostname mismatch | No original SAN/hostname diagnostic retained; cannot assert ruled out. Original host is exact approved route; full hostname checks retained and negative-tested. |
| Missing/unreadable CA file | Prior configuration checked system file existence, not its issuer content. No detailed read diagnostic retained. Successor verifies fixed CA bytes before connection. |
| Endpoint/configuration error | Retained route matches approved configuration. Live certificate binding and project access still need the bounded accepted preflight; no new route investigation. |
| Provider intermediate/chain defect | Original chain absent; cannot diagnose or fix through guessing. If correction still fails, stop with sanitised category; no automatic download/retry. |

Supabase official guidance prescribes its database CA and verify-full, including session-pooler examples:
https://supabase.com/docs/guides/platform/ssl-enforcement
https://supabase.com/docs/guides/database/psql

## Exact trust change and provenance

Replace only sslrootcert with the absolute resolved checkout path verification/ingestion_storage/trust/supabase-prod-ca-2021.crt. Retain sslmode=verify-full, original hostname, port, database, credential, NullPool and deadlines. No system trust-store mutation, weaker TLS, leaf pinning or credential fallback. The CA file is public certificate material; no private key is included.

Official verified-HTTPS download:
https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt

Provider publication independently traced at Supabase commit bc27d2661edd09a5d0b8d76ce33da6d4071a756e: apps/studio/components/interfaces/Settings/Database/SSLConfiguration.tsx selects prod and uses ssl:certificate_url from apps/studio/hooks/custom-content/custom-content.json (blob da81853cfd3010af703ce268c44208416fe2975a). Template: https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/${env}/ssl/${env}-ca-2021.crt.

PEM: 1367 bytes; SHA256 700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7.
DER fingerprint SHA256: 807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa.
Self-signed Supabase Root 2021 CA, CA:true, keyCertSign; valid 2021-04-28T10:56:53Z to 2031-04-26T10:56:53Z. Self-signature is an integrity check, not independent provenance authentication. Provenance is the verified provider publication. Runtime checks fixed hash/fingerprint, no symlink, size, signing purpose, self-signature and validity; pause for reviewed renewal at least 90 days before expiry. Any provider root rotation requires a reviewed new file/hash, never silent runtime fetching. Leaf renewal beneath the trusted root does not require pin updates. Normal certificate chain, leaf validity and hostname checks remain libpq's responsibility.

## Cleanup uncertainty and correction

Pool disposal only closes resources handed to SQLAlchemy; failed native connections can be outside that pool. Original failed-handle finish receipt, FD census and resolved-address count were not recorded. Thus UNCERTAIN is preserved for the original in-flight cleanup; no retrospective CLOSED assertion.

Pinned psycopg 3.3.6 C generator source (psycopg/psycopg tag 3.3.6, psycopg_c/psycopg_c/_psycopg/generators.pyx, blob 5a36f2b9169f1a7e26a10cfcc756c8ea6c6e2965) passes polling failures through finish_pgconn. That calls PQfinish and returns FinishedPGconn, an unusable snapshot. Other failure branches need not provide this receipt. Never dump that snapshot or raw exception because connection metadata can contain secrets.

The original worker exited with code 1 and the hosted job terminated. A dead process cannot retain its process-owned socket descriptors; no child worker is spawned by this DB phase. This resolves present local process-lifetime risk, not a contemporaneous FD census or remote peer observation. A failed TLS handshake returned no authenticated DB session; remote peer teardown was not directly observed. No production probe is justified to rewrite that historical limitation.

Successor records allowlisted failure category and FinishedPGconn receipt; combines it with pool disposal plus /proc/self socket-inode/descriptor census and child census. CLOSED requires positive evidence for native finish on failed connect and zero new owned sockets/children; missing census, missing receipt, leaked descriptor or disposal failure stays UNCERTAIN and stops. Linux /proc/self avoids PID namespace ambiguity. Outer timeout/kill may prevent final receipt: retain UNKNOWN/UNCERTAIN, reconcile worker/job termination and never infer CLOSED from job status.

## Focused offline validation

17 tests passed in 0.84 seconds; retained focused-tests.xml. Three pytest record_property/xunit2 compatibility warnings, no failing tests; recorded properties remain in XML. Command: python -m pytest tests/test_discovery_ingestion_tls_trust.py tests/test_discovery_ingestion_storage_access.py -q --junitxml=... . No production URL/secret used.

Disposable loopback PostgreSQL TLS emulator, hostaddr fixed 127.0.0.1 and ephemeral port: trusted CA + matching SAN reaches synthetic FATAL after TLS/startup; untrusted CA is rejected; wrong hostname is rejected. It is not a database and accepts no SQL. All three native failures yielded FinishedPGconn, closed socket property, joined server thread, no new owned socket descriptors or children. Local client psycopg/binary 3.3.6, libpq 180006; Python OpenSSL 3.5.8 is not proof of libpq's linked OpenSSL version. Hosted runtime remains to be separately recorded.

Additional tests cover CA tampering and expiry review; one DNS resolution/one selected address with original hostname retained; consumed authority and attempts/run numbers >1 rejected; missing finish receipt redacted; finished receipt plus simulated leaked FD remains UNCERTAIN; disposal/close failures remain UNCERTAIN; original access bounds and sanitisation. The existing offline CI job gains only this disposable loopback test step, no production credentials.

## Bounded successor proposal — requires concrete REVIEW and live authority

Executable entry: verification.ingestion_storage.tls_successor. Proposed workflow is successor-workflow.yml.proposed, deliberately outside .github/workflows. No workflow registered, dispatch or rerun. New proposed authority AUTHORISE_STORAGE_TLS_CATALOGUE_ONCE_20261016 is unused and not granted by this package. Old authority/run remain consumed.

After review, register the exact proposed workflow at .github/workflows/stage4-ingestion-storage-catalogue-tls-once.yml and bind reviewed clean revision, workflow hash, unchanged migration/manifest hashes and complete execution history; exact run1/attempt1 only. Recheck no prior successor execution and no active publication/execution. Use the existing protected environment and DATABASE_URL only; protected approval is specific access, never a stronger-role fallback.

Same scope: catalogue-only SELECTs in explicit READ ONLY transactions, rollback and two reconnect observations; no migration, seed, SET ROLE, application table access or writes. Maximum 2 logical/native connection attempts, 40 total driver statements (including SQLAlchemy setup), 30 active seconds, 120-second job, 256MiB worker RSS/address-space ceiling, 32KiB result and 2MiB file ceiling; setup75s maximum and pre-connect85s elapsed gate. Keep connect3s, statement10s, lock3s, idle-transaction10s deadlines. Outer TERM30s/KILL+2s supervises DNS and connection work. One bounded resolution of the same host (IPv4, <=32 records), one deterministic selected address reused for both connects, original host retained for SNI/verification: no address failover, retry or alternative route. IPv4 absence stops rather than falling back.

Successor records provider CA digests, psycopg/PQ implementation and libpq version, Python OpenSSL label, before-connect checkpoint, SQL/connection counters, rollback/reconnect readbacks and cleanup census. Each TLS/connect/catalogue/accounting/cleanup failure stops immediately. Preserve output and hashes durably before hosted expiry. Even catalogue success is READ_ONLY_CATALOGUE_COMPLETE_BLOCKED until restricted-login mapping, ownership/membership and all reviewed access conditions are proven; it does not release migration or the Salford stop. Reconcile any uncertain outcome before another mutation or connection.

Decision needed: accept this fixed provider-root configuration and cleanup treatment; approve guarded integration/registration and ONE new catalogue-only run with the above unchanged ceilings. No generic migration reapproval is requested; conditional migration remains contingent on successful accepted access evidence, not mere TLS success. No production action was taken in preparing this package.
