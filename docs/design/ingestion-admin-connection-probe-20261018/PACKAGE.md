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
| Any SQL beyond the reviewed constant | The only statement sent is the module constant `SELECT current_user`; any other text raises before it reaches the driver; a second statement is denied. | Direct tests; **server-side log** of a disposable PostgreSQL (`log_statement=all`), reached both through a test connection and through the production `connect` closure with only host/TLS redirected, shows exactly one statement, one connection, one disconnection, and no BEGIN/ROLLBACK/COMMIT/SET/startup query. A mutation test (adding a hidden `SELECT 1`) fails two tests. |
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

## Limits of the evidence (stated plainly)
- Server-side observation of the single statement exists **only in tests**, against a disposable PostgreSQL over loopback without TLS or the pooler. The production result reports the statement count as `CLIENT_COUNTED`, not as server-observed. TLS verify-full and the managed pooler path are not reproduced; pooler-side behaviour is exactly what the live probe would add.
- `operational_publication` (which defines the unused `GitHub` class) is imported transitively for `canonical`/`Uncertain`; no instance is ever created and `gh` is never invoked. Absence is by non-reachability of any caller, not by absence of the module.
- Native memory closure is exercised in the hosted systemd scope by a separate test file with a stub connection, because the operational scope must contain exactly one process (a database server inside it makes `OperationalMemory` refuse). The queue/ledger/role-change counters are `CAPABILITY_ABSENT`, not measured zeros.
- `accounting_schema=VALUE_BASIS_V2` is carried only by results from the preparation-stage session path and this probe. Operational Runner results keep their historical flat shape; `legacy_counts` projects either to flat integers. In-repo readers of `final-result.json` (cleanup tooling, tests) use their own flat shape and are unaffected.
- The validator pins the registration's hash set to the manifest and the checkout to the clean registered revision/tree; the approved commit/tree values are pinned by the owner script placeholders at release.

## Successor attempt (namespace configuration, narrowly bound)
- Attempt 1 (authority `AUTHORISE_INGESTION_ADMIN_CONNECTION_PROBE_ONCE_20261018`, state directory `operational-admin-connection-probe-once-20261018`) is **consumed**: the 120 s hidden-input window elapsed because the prompt was shown in an automation terminal the owner could not reach. It stopped at `SESSION_INPUT` with `NOT_ATTEMPTED`, closure `CLOSED`. Its audit directory is preserved and is never reused.
- The registration now carries `attempt`, `state_directory` and `predecessor`. The validator holds a two-entry table (`ATTEMPTS`): attempt 1 and the single successor, attempt 2 (`..._SUCCESSOR_2`, `...-successor-2`). Any other attempt number is rejected; there is no open counter.
- A successor is valid only with `predecessor` evidence: the controller re-hashes the predecessor `events.jsonl` and `final-result.json` and requires the recorded outcome `SESSION_INPUT` / `NOT_ATTEMPTED` / closure `CLOSED` before it creates anything.
- Everything else is unchanged: limits, statement, boundary, startup options, code bindings. The owner script takes the commit, tree, registration hash and attempt as arguments (nothing is substituted into it), refuses before consuming anything unless stdin and stderr are a real terminal, checks out nothing itself, and prints the verified predecessor and the absence of the successor namespace before the input timer starts.
- Hidden input is verified on a pseudo-terminal (not echoed) and inside a `systemd-run --user --scope` (terminal preserved).
