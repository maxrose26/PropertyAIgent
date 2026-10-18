# Timing-safe revoke-only cleanup successor

The authorised successor is ready for **one owner-local execution**. It has not been executed in production during preparation. Storage is accepted; operational acceptance failed; the pipeline retry is held and Stage4 remains OPEN.

## Exact integration and authority

- Reviewed candidate: `158ac2df3329806408cd0d30bb55bafea80af1db`.
- Integrated PR127 revision: `acd3f5690b439d7d91b7a7efb9ace79c9098d303`; exact tree `3f07eeb8442ef6fe5bf93907a03c357faf602a72`.
- Guarded merge commit includes [skip render]; no deployment or source workflow was dispatched.
- Nine exact-candidate checks and seven post-merge checks passed. Independent exact-code and final owner-handoff review PASS, with no unresolved findings.
- Helper blob `a026c05faee4069be24c6ed2218644e8a8663847`; SHA256 `66467e6396fffe6ae4e8a8860f1b22b50a102dbad3814e5d8e4058ca2d72be7b`.
- Cleanup authority `AUTHORISE_OPERATIONAL_SAFETY_CLEANUP_TIMING_ONCE_20261018` is cleanup-only. It issues no replacement capture grant.
- Registration blob `f123d34b2f1557ebadf089b3c7be5a063803d388`; SHA256 `3a1f7e58506d507deb9bf5c1b60c08af8c7a4ea2202785d27344e53d404f696f`.
- Release 18 October2026 08:55UTC; expires **22:00UTC / 23:00BST on18October2026**. No automatic renewal or reuse.
- Owner script blob `27f03a7b5596d7e5912a3954343d1f97843051b5`; SHA256 `9d7dd7e6b75b334fceb046b2104b546d220fb970748655c08bca8d24510680ca`.
- The original failed capture remains bound to ad8d5211afcc635c5bc50f4963adde4f31b4ef62; this new helper revision does not change or renew that execution authority.

## Timing and failure handling

Setup has a10-second bound. Secure hidden input has up to300seconds and permits no database or secret API operations. Registration expiry is rechecked after input, before preparing the connector or any effect, and again before subsequent operations.

The active cleanup phase then has45seconds, comprising40seconds work and a5-second finalisation reserve. The independent systemd outer scope ceiling is355seconds, covering setup, input and active cleanup. Native cgroup memory is256MiB including gh and descendants; no virtual-address cap.

Input timeout and ordinary active failures save and display one bounded result; a late reporting error becomes an UNCERTAIN fallback, not a second traceback. An unresponsive output/finalisation path can hard-stop with exit124; persisted files alone must not be treated as proof of successful exit. The owner script prints the controller exit code and performs a bounded three-second local read-only unit-status inspection after exit. It invokes no further DB/secret operation.

The reporting receipt distinguishes persisted evidence bytes, terminal JSON bytes and their sum. Terminal JSON is capped64KiB, with additional fallback/local-receipt reserve under512KiB. Phase timings contain no input or input length. Credentials stay in memory and enter only through the existing echo-protected TTY mechanism.

## Exact effects and permissions

Existing migration principal, endpoint, CA and verify-full are preserved. Its exact non-superuser flags and reviewed capabilities must pass. No stronger principal, new credential creation, provisioning replay, source call, application write or new permission is introduced.

The existing helper's cleanup effects are unchanged:
1. Complete names-only secret metadata read, requiring the two target names and DATABASE_URL.
2. Connection1: record safe identity, roles/password-null booleans, exact memberships, associated session identifiers/state, control and unchanged ledger hashes. Atomically expire only the failed capture grant/exception, increment hard-stop generation, preserve the original Salford stop and STORAGE_TEST_STOP, disable ingestion_worker_login and ingestion_effect_login, remove passwords and revoke only their reviewed memberships. Remove transient migration-owner capability before COMMIT.
3. Connection2: actual disabled-access readback, exact committed control/unchanged-ledger verification, rollback of temporary readback capability and positive capability removal.
4. DELETE exactly INGESTION_WORKER_DATABASE_URL and INGESTION_EFFECT_DATABASE_URL, with certain acknowledgements; final complete names-only read must equal the initial set minus those targets. Preserve DATABASE_URL and every other secret.
5. Positive closed native connections, socket/child accounting and kernel memory evidence.

Ceilings:2connections,32driver commands,1MiB returned database data-value bytes,45active seconds,256MiB actual memory,512KiB exported evidence,2DELETEs and2complete names-only GETs. These are independent new cleanup limits, not a replenishment of any prior phase.

Unexpected sessions are recorded and stop execution; none are terminated. Unexpected state, ambiguous effects, expiry or exhausted limits stop without retry or compensation. All four non-control ledger rows, zero work attempts, installed functions, accepted applications1504–1508 and historical authorities remain preserved.

## Focused disposable proof

Hosted run39112814246, number196/attempt1, exact reviewed candidate: PASS. Twenty tests, zero failures/errors/skips. Tests include real hidden-TTY delayed input and timeout, input expiry, active timeout, bounded finalisation fallback, blocked-output hard stop, real PostgreSQL17 connection rejection, lost COMMIT acknowledgement, lost first secret-delete acknowledgement, changed grant and associated session.

All six PostgreSQL cases use the same phase controller as production, comparable non-superuser migration flags, actual restricted logins and real Linux gh against a bounded loopback TLS fixture. Short timing values accelerate timeout regressions through the same code; they do not claim a real five-minute wait. The fixed production timings cannot be changed through CLI inputs or broadened registration limits.

Success:20commands,2connections opened/closed,17,268returned database data-value bytes,2DELETEs and2names reads. Active time before finalisation was0.281036712seconds; the0.282720352-second fixture accounting sample also includes later test assertions, so it is not labelled the full production runtime. The fixture's cumulative kernel peak was106,135,552bytes, no max/OOM events. A separate excess-memory test started real gh, killed the full256MiB scope and verified empty ControlGroup.

Uncertain COMMIT stops before connection2 or secret deletes. A failed PostgreSQL handshake records one connection attempt, zero SQL commands and zero opened connections. Uncertain first DELETE stops before the second request. The chosen disposable handshake failure is not evidence of the historical production connection's cause.

Original artifact12130947187:68,988bytes, SHA256 `3ccba61bd65c7b0162cd806250e885c035edb83fd431995a233609778fe2b72f`. Full original ZIP, reversible base64 mirror, cleanup.xml and all member hashes are archived here; no dependency on hosted expiry.

## Preserved history and owner action

The consumed timeout remains at791557cf84b27c24ec3cf134bbf8af4ca3b5a658. Both its original files and the175-event operational audit are hash-checked before consuming the fresh successor state. They are never overwritten. Historical UNCERTAIN classifications and the original operational accounting gaps remain unchanged; original admin time/returned-byte values remain UNKNOWN.

Run the reviewed owner command once using existing WSL/keyring/venv setup. The registration and helper hashes, clean integrated checkout and fresh state are checked before prompting. No new token or password is requested. Enter only the existing migration URL at hidden local input.

Return the full terminal result/exit-status readback and the new credential-free events.jsonl and final-result.json from:
`~/.local/state/propertyaigent/operational-safety-cleanup-timing-successor-20261018/`.

Expected successful helper result: SAFETY_CLEANUP_ACCESS_DISABLED / CLOSED. Final production cleanup is accepted only after reconciling actual readbacks, hashes, accounting and exit evidence. On any stop, preserve files and do not rerun. Pipeline retry remains held.
