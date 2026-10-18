# Administrative connection probe — specification and release package

Status: PREPARED FOR REVIEW. No registration is released, nothing is executed. Stage 4 remains OPEN. Storage remains accepted. Pipeline retry remains HELD.
Intelligence layer: operational evidence for the ingestion pipeline (it exists so a Site's planning evidence can later be ingested; it touches no Site, Application or council data).

## The one question this probe answers
With corrected, stage-attributed preparation, **does the approved ADMINISTRATIVE identity (`postgres.<project>` through the reviewed pooler route, verify-full TLS, pinned IPv4) complete preparation and one authenticated connection, and if it does not, at which fixed stage or classified reason does it stop?**

It does NOT answer, and its result must never be read as answering:
- whether the restricted worker or effect-broker logins authenticate (the earlier worker-handshake failure is a separate historical fact and is untouched);
- whether the startup `options` are the cause of that handshake failure (they are left exactly as reviewed; one probe cannot isolate them);
- whether the pipeline, a council source, queue state or policy is healthy.

A classified failed connection is **diagnostic progress, not qualification**. A qualified administrative connection qualifies only the administrative role's connection.

## Why a new controller and not `CONNECTION_DIAGNOSTIC_ONLY`
`CONNECTION_DIAGNOSTIC_ONLY` is a flag on the operational `Runner`. Its `execute()` runs `setup()`: GitHub identity call, `Owner.preflight()` (which executes `GRANT ingestion_storage_owner TO CURRENT_USER` inside a rolled-back transaction), `install()`, `map_and_activate()` (credential generation, role password change, protected-secret mapping), restricted-login qualification, then `teardown()`. Its failure path (`failed()`) invalidates authorities and tears down mappings. Reusing it would run credential lifecycle mutations. This package therefore introduces `verification/ingestion_storage/admin_connection_probe.py`, which **has no such code path to reach**.

## Mechanical boundary (what is proven, and how)
| Forbidden effect | Why it cannot happen | Test evidence |
|---|---|---|
| Credential generation, mapping, role/membership change, function install, grant/exception, queue or ledger mutation | `ProbeRunner` is constructed from a connect closure, journal, progress record and memory object only. No GitHub client, Owner, credential mapper, ledger, source reader or Runner exists in the module's imports or names. | AST allow-list of imports and forbidden-name test; import footprint in a clean interpreter excludes `operational_owner`, `credential_mapping`, `operational_runner`, `operational_source`, `operational_controller`, `storage_controller` and every `app.*` module. |
| Any SQL beyond the reviewed constant | The only statement sent is the module constant `SELECT current_user`; any other text raises before it reaches the driver; a second statement is denied. | Direct tests; **server-side log** of a disposable PostgreSQL (`log_statement=all`) shows exactly one statement, one connection, one disconnection, and no BEGIN/ROLLBACK/COMMIT/SET/startup query. A mutation test (adding a hidden `SELECT 1`) fails two tests. |
| Rollback, commit, driver startup query | Autocommit connection, `prepare_threshold=None`, no explicit transaction control; accounted as measured zero and confirmed by the server log. | as above |
| Council or other network calls | No source module is importable from the probe; spies on `Popen`, `socket.connect` and `getaddrinfo` show only the credential-free DNS child and the single loopback connection. | `test_no_external_effect_*` |
| GitHub access | `gh` is never invoked; the entrypoint refuses `GH_TOKEN`/`GITHUB_TOKEN`; no GitHub client is constructed. | spy test, entrypoint test |
| Reuse / replay | State directory is created exclusively (`FileExistsError` on any second use) and the registration is single-purpose (mode, authority, exact key set, bound limits and absent-capability list). | registration and one-use tests |
| A registration for another mode being accepted | Exact key set; mode/authority/status must equal the probe constants; the old `CONNECTION_DIAGNOSTIC_ONLY` registration and authority are rejected. | parametrised rejection tests |

A test-only seam (`connect_factory`) lets tests substitute a disposable-server connection. `main()` never passes it; the entrypoint tests assert the production path.

## Numerical limits (bound into the registration; enforced in code or by the kernel)
| Quantity | Limit |
|---|---|
| Database connection attempts | 1 |
| Driver statements (including any startup query or rollback) | 1 (rollbacks 0, commits 0) |
| Returned data value bytes | 128 |
| Database wait | ≤ 13 s (connect_timeout 3 s + statement_timeout 10 s, from the unchanged startup options) |
| DNS | 1 credential-free subprocess, 3 s |
| Hidden credential input | ≤ 120 s, no database/GitHub/network operation in this phase |
| Active window after input | ≤ 45 s, work-closure reserve at 35 s, diagnostic 5 s, final report 5 s; outer ceiling 180 s; systemd `RuntimeMaxSec=200s` |
| Memory | controller cgroup 256 MiB, aggregate 1.5 GiB, swap 0, OOM-group kill (existing `OperationalMemory`, verified before any credential is read) |
| Persisted evidence | ≤ 64 KiB; terminal JSON ≤ 32 KiB (existing finaliser also bounds 256 KiB / 2 MiB) |

## Outcomes (stated separately; none implies another)
- `preparation`: `COMPLETED` | `FAILED` (with fixed stage and reason) | `UNKNOWN`
- `administrative_connection`: `QUALIFIED` | `FAILED_CLASSIFIED` | `FAILED_UNCLASSIFIED` | `NOT_ATTEMPTED`
- `failure`: `NONE` | `CLASSIFIED` | `UNCLASSIFIED`
- `closure`: `VERIFIED` | `UNCERTAIN`, derived only from positive evidence (native connection object closed or no surviving socket, zero owned children, kernel group removal with zero survivors). Post-exit systemd scope removal is **not** verifiable from inside the controller and is reported as `NOT_VERIFIABLE_BEFORE_CONTROLLER_EXIT`.
- Always: `worker_authentication_qualified=false`, `route_qualified_for_restricted_roles=false`, `application_writes=0`, `pipeline_retry=HELD`, `stage4=OPEN`.

A `QUALIFIED` connection with `closure=UNCERTAIN` is reported as exactly that.

## Pass / fail criteria for the observation itself
The observation is **informative** (regardless of the connection result) when: `final-result.json` exists with a stage- or reason-attributed outcome, all counters are within the limits, no forbidden-capability counter is non-absent, no secret appears in any output, and `closure` is `VERIFIED`.
It is **inconclusive** when: the final result is missing, any counter exceeds a limit, `failure=UNCLASSIFIED` (the answer is then "an unclassified failure at stage X", which is still recorded and still not retried), or `closure=UNCERTAIN`.
Any `UNCERTAIN` closure or limit breach stops everything and requires a separate reconciliation decision; there is no automatic retry and the same authority cannot be reused.

## Cleanup
Nothing is created that needs teardown: no credential, mapping, role, grant, exception or queue row. Cleanup is closing the one connection, reaping the DNS child, removing the owner-local memory groups, and leaving the audit directory in place. No executable authority remains.

## Release procedure (owner-local; not authorised by this package)
1. Merge decision and release approval are separate Product Owner acts and are not part of this PR.
2. At release, `render_registration.py` (offline, no network) produces the registration from the then-current clean checkout, hashes every path in `MANIFEST.json`, and prints the registration SHA-256. Expiry is capped at two hours by the validator.
3. `owner-run.sh` re-checks the exact commit/tree, absence of the state directory and registration SHA, performs read-only validation, prompts for the credential at a hidden prompt, and runs the probe under `systemd-run --scope`.
4. Evidence to return: `events.jsonl` and `final-result.json` hashes, controller exit status and the scope readback (10 s allowance; timeout is reported as UNKNOWN, never as success).

## Historical record preserved
- The earlier operational failure (pre-connection, 19 ms, redacted to `ROUTE_VALIDATION`/`UNKNOWN`) and the earlier restricted worker handshake `OperationalError` remain separate, unchanged and unresolved. This probe cannot reclassify either.
- Startup `options` stay unchanged. No evidence yet supports removing them; if a later observation shows a handshake failure that only the options plausibly explain, that is a new decision with its own evidence.
