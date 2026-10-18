# Restricted-connection matrix — numerical release package

Status: PREPARED FOR REVIEW. No registration is released; no credential is generated, mapped or activated; nothing connects. Storage remains accepted. Operational acceptance and Stage 4 remain OPEN. The historical failures and consumed authorities are preserved and unchanged.

## DIAGNOSTIC ALLOWANCE versus EXECUTION AUTHORITY (kept separate)
| | This package |
|---|---|
| **DIAGNOSTIC ALLOWANCE** | Four restricted-account connection entries, one connection and one fixed identity statement each, inside the accepted credential lifecycle (fresh temporary passwords, temporary protected secrets, activation, teardown). The existing residual-risk acceptance (possible provider SCRAM-verifier retention, worker/effect, once) is applied to **this finite test only** (`risk_application`). |
| **EXECUTION AUTHORITY** | **NONE.** The mode registers no authority, issues no grant or exception, processes no queue item, makes no council or GitHub-evidence call and writes no application row. A result is never a qualification for execution; a later execution registration would have to bind this result's hash and carry its own approval. |

## What the test is, and is not
Each entry observes one configuration at one point in time after credential installation:

| # | Account | Startup options |
|---|---|---|
| 1 | `ingestion_worker_login` | none |
| 2 | `ingestion_worker_login` | reviewed (`statement_timeout=10000`, `lock_timeout=3000`, `idle_in_transaction_session_timeout=20000`) |
| 3 | `ingestion_effect_login` | none |
| 4 | `ingestion_effect_login` | reviewed |

The ordered matrix **does not establish** a cause. Options, elapsed time since installation, any credential caching or propagation, and any provider behaviour vary together along the order, so a result is a configuration-specific observation only. It cannot prove or rule out caching, propagation or a provider defect. Non-secret elapsed intervals (since password installation, since protected-secret mapping, since activation, since the previous entry closed) are recorded for every entry so the owner can see the timing, not so that this test can claim a timing conclusion.

`CONNECTION LIMIT 1`: both logins admit a single session. Each entry's connection is closed and positively verified closed (connection object closed and no new owned socket) before the next entry starts; an unclosed connection is a global stop. A held session on a login would produce a classified capacity failure for that login's entries only (tested).

## Per-entry rules
- Exactly one connection attempt (3 s connect timeout). If it connects, exactly one fixed identity statement; autocommit, no rollback, no commit, no retry.
- Outcome stored per entry: `CONNECTED_IDENTITY_VERIFIED`, `FAILED_CLASSIFIED` (allow-listed reason, SQLSTATE if any — connect-time server errors carry **none** in this driver, so absence of a SQLSTATE says nothing), `FAILED_UNCLASSIFIED`, `IDENTITY_UNEXPECTED`, `CLOSURE_UNCERTAIN`, `STOPPED_DURING_ENTRY`, `SKIPPED_GLOBAL_STOP`.
- **Continue only after** a classified failure in {authentication rejected, authorization rejected, permission denied, routing identity rejected, connection capacity, connection timeout, connection refused, connection failure, server not ready} **with** the entry's connection/process closure verified and accounting certain.
- **Global stops** (remaining entries recorded as skipped; teardown is still attempted in its reserved allowance): unclassified failure; TLS integrity failure (hostname, chain, CA); unexpected identity or an options variant whose session does not carry the requested settings; closure uncertain; any budget exhausted; non-continuable classified failure; uncertain persistence or cleanup (reported UNCERTAIN, never CLOSED); a lifecycle stop before the matrix finishes.

## Numerical allowance
| Quantity | Limit | Where enforced |
|---|---|---|
| Entries | 4, fixed order | registration binds the list; validator rejects any other |
| Restricted connection attempts | 4 total, 1 per entry | `Matrix`, global stop `CONNECTION_BUDGET_EXHAUSTED` |
| Restricted driver statements | 4 total (1 identity statement per connected entry); rollbacks 0; commits 0 | `Matrix`; server-log test shows exactly these |
| Returned data value bytes | 1 024 | `Matrix` |
| Connect timeout / per-entry | 3 s / 13 s | libpq / registration-bound |
| Matrix wall time | 60 s | `Matrix` |
| Administrative connections (TOTAL: preflight, install, mapping/activation, teardown, failure diagnostics) | 4 before diagnostics, **5 total** | `Owner.limits` |
| Administrative commands (TOTAL) | 44 before teardown, 58 through teardown, **64 total** | `Owner.limits` |
| Hidden input / active window / work alarm / outer / systemd backstop | 120 s / 270 s / 215 s / 420 s / 450 s | session timing, `RuntimeMaxSec` |
| Runner deadlines | job 170 s; failure window 40 s and diagnostic total 255 s; administrative time before teardown 60 s, through teardown 100 s, including failure diagnostics 130 s; restricted phase 60 s | `Runner.deadlines` (ordering invariants tested, including a stop arriving with the pre-teardown allowance fully spent) |
| Memory | 256 MiB controller, 1.5 GiB aggregate, no swap | existing `OperationalMemory` + systemd scope |
| Evidence | 64 KiB persisted per file group; terminal JSON ≤ 256 KiB (existing finaliser also bounds total 2 MiB) | existing journal/finaliser |
| Credential generation / protected-secret mappings | 2 / 2 (both deleted at teardown) | accepted lifecycle |
| GitHub API (owner preparation) | 1 read-only identity call in `owner-run.sh`; lifecycle calls as accepted | script / `GitHub` budget |

## Administrative allowance is sufficient for the complete lifecycle and failure handling (measured, not inferred)
Measured in the hosted restricted PG17 fixture with the real `Runner`, real `Owner`, real `GitHub` client against the real Linux `gh` fixture, real teardown SQL and the real matrix (hosted job `restricted-provisioning`, test ids `...[matrix_*-operational]`, lines `MATRIX_MEASURE` in the job log):

| Scenario (injected, real wrapper) | Admin connections | Admin commands | Result |
|---|---|---|---|
| All four entries connect (`matrix_success`) | 4 | 46 | completed, access disabled, cleanup CLOSED |
| Classified failures at entries 1 and 3, matrix continues (`matrix_classified_continue`) | 4 | 46 | completed, access disabled, CLOSED |
| Unclassified failure at entry 2 (`matrix_unclassified_stop`) | 5 | 52 | stop, entries 3-4 skipped, teardown ran, CLOSED |
| TLS-integrity failure at entry 1 (`matrix_tls_stop`) | 5 | 52 | stop, teardown ran, CLOSED |
| Unexpected identity at entry 1 (`matrix_identity_stop`) | 5 | 52 | stop, teardown ran, CLOSED |
| Connection budget exhausted before entry 3 (`matrix_budget_stop`) | 5 | 52 | stop, teardown ran, CLOSED |
| Connection left open at entry 1 (`matrix_close_uncertain`) | 5 | 52 | stop, cleanup **UNCERTAIN**, access `UNRECONCILED` (not reported closed) |
| Normal command allowance exhausted right after mapping (`matrix_admin_bound_reserve`; counter forced to 44, then real teardown + diagnostics) | 5 | 59 | stop, teardown completed inside the reserved allowance, CLOSED |

Derived components (from the rows above): preflight + install + mapping/activation = **37** commands over 3 connections; teardown = **9** commands over 1 connection; failure diagnostics = **6** commands over 1 connection. Therefore the worst real path (stop after mapping: 37 + 9 + 6) is **52 commands / 5 connections**; the success path is 46 / 4. Ceilings: 44 before teardown (margin 7 over 37), 58 through teardown (margin 12 over 46, and 14 reserved against 9 needed), 64 total (margin 12 over 52); connections 4 before diagnostics, 5 total. The sufficiency of these ceilings is shown by the measured failure-handling paths above, not inferred from the successful path. A failure earlier than mapping (preflight or install) uses fewer commands because it skips mapping and, with no temporary credentials, teardown (covered by the local wrapper test with recording fakes).

Every row also asserts, after the run: no authority, no grant, no exception, no source call, no queue row, no application write; the control row unchanged; both logins `NOLOGIN` with NULL password, no capability membership, no session; both temporary secrets deleted; administrative connections opened = closed.

## What this package changes in code (nothing else)
- `restricted_matrix.py` (new): the four-entry matrix.
- `operational_runner.py`: new mode `RESTRICTED_CONNECTION_MATRIX_ONLY` (registration binding, `setup_matrix`, matrix result in success and failure results, mode-specific deadlines). Capture and existing diagnostic modes keep their previous deadlines and limits (tested).
- `operational_owner.py`: configurable administrative limits (defaults unchanged) and non-secret monotonic lifecycle stamps.
- `connection_diagnostics.py`: one allow-listed pattern, `too many connections for role|database` → `CONNECTION_CAPACITY` (previously `UNKNOWN`).

## Correction of an earlier statement
`ANALYSIS.md` in the restricted-gap evidence (PR #133) says an absent SQLSTATE means the driver did not receive a server error response. That is wrong for connect-time failures: this psycopg exposes **no** SQLSTATE for server FATALs raised while connecting (reproduced against a disposable server: role missing, too many connections). The absent SQLSTATE of the 18 Oct failure therefore does not distinguish a server rejection from any other connect failure.

## SU-511198
The follow-up remains **unsent** until an authorised existing-thread channel is available; no duplicate ticket is created and the provider's response is not a prerequisite for this package.

## Release procedure (not authorised by this package)
1. Product Owner decision on this exact candidate (merge is separate) and on applying the residual-risk acceptance to this finite test.
2. `render_registration.py` (offline) from a clean checkout of the approved commit; expiry ≤ 2 h.
3. Owner runs `owner-run.sh <commit> <tree> <registration-sha256>` in a visible WSL terminal; hidden credential entry only.
4. Return: audit hashes, per-entry outcomes and intervals, administrative and restricted accounting, closure components, scope readback.
