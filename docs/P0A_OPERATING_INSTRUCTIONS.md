# P0-A operating instructions — inactive review candidate

These instructions describe the local review candidate. They do not authorise a production migration, configuration change, run or deployment. Offline Gate A was independently accepted on 29 September 2026 with four matched-baseline failures and one explicit deselection. That acceptance applies only to ff0baa2. See `P0A_NARROW_CORRECTIONS_REVIEW.md` for the new, unverified candidate and current release gates; production remains unapproved.

## Admission switches and precedence

`app/pipeline/discovery_config.py` is the shared parser for supervisor and child admission. Values are case-sensitive and are not whitespace-normalised. Empty strings are invalid, not defaults.

| Input | Accepted values | Unset default | Meaning |
|---|---|---|---|
| `PROPERTYAIGENT_DISCOVERY_MODE` | `bounded`, `disabled` | `bounded` | Specification-compatible safety input. `bounded` is not production activation. |
| `PROPERTYAIGENT_DISCOVERY_ACTIVATED` | `0`, `1` | `0` | Additional release gate. Production admission requires `1` as well as the approved identity/ownership contract. |
| `PROPERTYAIGENT_DISCOVERY_DISABLED` | `0`, `1` | `0` | Compatible explicit disable alias retained from the first implementation. |

Order of evaluation:

1. Validate every switch. Any unknown, empty or malformed value produces an error/nonzero exit before DB bootstrap; an invalid value is not silently ignored even if another switch disables discovery.
2. `MODE=disabled` **or** `DISABLED=1` blocks admission regardless of `ACTIVATED`.
3. Otherwise, production requires `ACTIVATED=1`. `MODE=bounded` alone cannot activate production.
4. Runtime/service/instance identity, observable PID-start identity and the inherited exclusive ownership contract must also pass. Local synthetic test callers do not need production activation but still honour disable/invalid inputs.

Examples: `ACTIVATED=1, DISABLED=1` is disabled. `ACTIVATED=1, MODE=disabled` is disabled. All switches unset leaves production inactive. `DISABLED=false`, `ACTIVATED=true`, `MODE=off` and empty values are errors.

**Current desired state remains inactive:** leave activation unset/zero; do not enable any production schedule through this review. No production settings were changed. Turning a switch off prevents new admissions; it does not terminate an already-running process. Old code does not understand these switches.

The first implementation replaced the specification's MODE switch without documenting the replacement. This follow-up restores MODE compatibility. ACTIVATED remains an additional fail-closed release gate; DISABLED is a redundant alias, not a new execution mode. The original reviewed specification stays byte-identical; this deviation and compatibility treatment are recorded in the follow-up report.

## Limits and scope

The effective limits are validated before DB bootstrap, printed once as `[discovery-config]` and stored in each council's progress. Positive integer environment inputs: `PROPERTYAIGENT_DISCOVERY_PARENT_ITEMS` (25), `...PARENT_ATTEMPTS` (30), `...PARENT_SECONDS` (180), `...INVOCATION_SECONDS` (9000). Council limit remains the existing `--timeout-seconds` CLI input (3600), not a new environment alias. `--council` is repeatable and must constrain a limited smoke invocation explicitly. AI stages remain skipped by default; never add `--include-ai-stages` under this approval.

These are trial hypotheses, not production capacity. The selected scope and effective child timeout must be checked before activation. An unchanged all-council default command must not be activated as a substitute for a Manchester/Salford-only release candidate. Stockport is excluded pending separate primary-retry remediation and acceptance.

Elapsed time starts on entry to `main`, before ownership, bootstrap and reconciliation. An independent `discovery_watchdog` subprocess enforces the absolute invocation deadline without DB access. It registers each council process group before any persistence callback. The council hard backstop is its timeout plus a 20-second cleanup allowance, capped by the invocation deadline; the parent-stage backstop is its start budget plus 60 seconds plus a 10-second cleanup allowance, also capped. The ordinary supervisor still attempts graceful termination first. A stuck progress/final commit cannot prevent the independent backstop killing the registered group and supervisor. Hard termination aborts the invocation; later councils remain deferred, not successful. It emits a best-effort stderr diagnostic; no database final-status write is claimed. Existing running rows are reconciled only under the unchanged positive-termination ownership contract.

Discovery supervisor and admitted child PostgreSQL connections retain a 10-second connection/pool wait and TCP keepalives. An opt-in SQLAlchemy transaction-begin hook sets and verifies transaction-local statement timeout 15s, lock timeout 5s and idle-transaction timeout 30s, including after rollback or connection replacement. Startup options were observed ineffective on the live session pooler and are no longer relied upon. Failure to set/verify bounds invalidates the connection and raises; no persistent database defaults are modified. These are containment hypotheses, not production latency measurements. They do not configure unrelated application connections. Driver/network hangs remain covered by the watchdog. Verify compatibility with the actual pooler before activation; do not silently remove bounds to make connection startup succeed.

Parent cancellation is now cooperative: remaining-time native browser navigation/action waits and bounded retry sleeps, with checks between protocol operations. No SIGALRM is installed. Immediate browser protocol calls and requests body reads are not claimed to be individually preemptible: their hard containment is the independent stage/council envelope. Actual Chromium tests passed in the accepted WSL evidence; Render runtime compatibility remains a release requirement.

## Scheduler identity release block

Shell/non-scheduler admission is rejected. `SCHEDULED_INSTANCE_PATTERN` is deliberately None: no actual scheduled-job identity contract has yet been verified. ACTIVATED=1 is insufficient to bypass this. Offline tests substitute a synthetic reviewed identity pattern; this is not production evidence. Cross-instance recovery requires both owners to carry the reviewed scheduler contract and satisfy that contract. Old legacy rows without an owner remain visible. Do not set a permissive pattern or an environment self-attestation to release this block.

## Exact migration

Use the proposed `python -m scripts.migrate_p0a` for read-only preflight only after its own validation. `--apply` is a separate, unapproved production action. It verifies managed column definitions and exact P0-A constraints/index/defaults; aborts on unreviewed drift; creates only parent_lookup_work and nullable scrape_runs.progress in one transaction; performs no historical backfills. Do not use the generic migrate_schema command for P0-A release. Stricter checks may expose pre-existing legacy nullability/type drift; report it for review, never repair it automatically.

## Development integration prerequisites

Use a non-production, non-root Linux development runtime with:

- PostgreSQL server, libpq/psycopg, an empty disposable `p0a_test_*` database and loopback connections. The test refuses non-loopback hosts, connection-query overrides and a nonempty database.
- The Chromium binary matching the installed Playwright version, its shared libraries, child-process execution and signals.
- Reliable `/proc` PID/start identity and descendant visibility, process groups and file locking. The earlier remote runtime could not establish all lifecycle evidence; the accepted WSL run did.
- External network blocked during tests. Browser fixtures additionally reject external routes and use a local rejecting proxy; local synthetic HTTP and the disposable PostgreSQL endpoint are permitted. No signed-in cloud browser substitutes for local process/lock tests.

Set **only** `P0A_TEST_POSTGRES_URL` for the empty local test database. Do not provide or reuse a production `DATABASE_URL`; do not paste credentials into chat. Example shape: `postgresql+psycopg://local_test_role@127.0.0.1:5432/p0a_test_gate_a` (illustrative local role, not a supplied credential).

From the repository root, in that development runtime:

```sh
PYTHONPATH=tests:. python -m pytest -p p0a_offline_guard -q tests/test_p0a_bounded_discovery.py tests/test_p0a_chromium_integration.py tests/test_p0a_release_corrections.py
## SQL trace already accepted; no further optimisation/reproduction required here.
```

A skipped PostgreSQL or Chromium case leaves the gate open. The real-browser tests deliberately fail if cleanup leaves any recorded descendant, including a zombie. Passing mocked page/resource tests is insufficient. The PostgreSQL test covers migration idempotence, uniqueness/FKs, transactional DDL rollback, conditional owner/result writes, evidence rollback and successor recovery; it executed successfully in the accepted WSL run. Future candidate changes still require the relevant real integration checks.

## Future migration-first rollout and smoke

Only after offline acceptance and explicit release approval: suspend/verify all discovery entrypoints, confirm exact service/type/instance identifiers, run and verify the additive migration **before** starting new consumers, then verify the exact deployed SHA and restricted invocation scope while inactive. Approve trial budgets before activation.

Proposed restricted smoke remains Manchester first, then Salford after terminal ownership/cleanup verification. Current-month only; initially five parent references, six attempts, 60-second start budget (130-second hard stop envelope: 60 + 60 + 10), existing 3600-second council trial ceiling, no AI or historical recovery. Earlier council/invocation limits take precedence. Pre-read bounded candidate metadata to verify useful document→refresh work exists. A primary timeout, unexplained deferment, ownership contradiction or memory stop fails the relevant acceptance. This is a proposal, not permission to run it.

Manchester/Salford acceptance does not establish Stockport or platform-wide readiness. A subsequent seven-cycle observation window must meet the specification's scope/freshness/continuation criteria before sustained operational health can be claimed.

## Rollback

Suspend the scheduler and verify all active discovery processes terminal **before** reverting. Do not rely on a new switch to restrain an older revision. Prefer a forward revert that retains bounded admission/supervision; otherwise keep discovery suspended. Retain the additive table, progress column, committed evidence and run-health history. No destructive downgrade, blanket reservation clearing or historical replay. Reconcile only with positive termination evidence. Resume only a reviewed bounded version under separately approved smoke scope.

## Reproducible Gate A handoff

Use `verification/P0A_GATE_A_HANDOFF.md` and its exact-commit runner. Do not rerun failed installations in the current runtime. A clean matched baseline and all actual integration results must accompany the candidate review.

## Final-preflight enforcement details

The council launcher waits on a one-byte pipe before importing/executing discovery. The supervisor requires a watchdog registration acknowledgement before releasing it; supervisor death in the creation/registration gap closes the pipe and the launcher exits without doing discovery. Absolute launch/invocation deadlines are checked before release and again before exec. Budget control messages are acknowledged with a bounded wait and expiry wins over queued deadline extensions. The watchdog terminates the supervisor first to prevent subsequent launches, then registered groups, and only then attempts nonblocking diagnostic output.

A bounded reader tracks parent-stage deadlines independently of persistence/log callbacks, using the child's monotonic start stamp. Duplicate before-markers do not reset that start; retries never change it. An after-marker received after cooperative expiry cannot declare completion. If a callback cannot consume the bounded log queue, excess lines are dropped and the run fails explicitly rather than claiming full health; budget control still drains. All subordinate watchdog limits are capped by the invocation deadline.

Ordinary termination is SIGTERM, then at most 15 seconds for council timeout (5 for parent/memory stop), then SIGKILL and bounded leader wait. The independent watchdog caps this at the documented hard deadline even if callbacks, logging or persistence stall. It cannot guarantee prompt kernel scheduling, terminate an uninterruptible kernel task, or kill descendants which escape their process group. Unexpected watchdog death while the supervisor is blocked is a remaining single-watchdog limitation; acknowledgement checks prevent subsequent admitted starts when its loss is observed, not a guarantee during an already blocked operation. Actual browser descendant and lock-release tests remain release requirements. No result or negative finding is inferred from forced termination.
