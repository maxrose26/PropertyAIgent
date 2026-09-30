# P0-A offline Gate A verification handoff

No release, production connection, migration, scrape or paid call is authorised. Use the exact candidate commit in the latest `docs/P0A_FINAL_PREFLIGHT_REVIEW.md` (available at the report HEAD in the supplied bundle); checkout that candidate for testing. Reviewed specification SHA-256 remains `c007e2b2912ae5d8817142c32fdf35e0000f72d4fa127d5c83e32e6ef10970f8`.

## Required runtime and one access action

Provide an authorised non-production Linux executor accessible to this workflow, or run the following handoff there and return its logs/XML. It must have a non-root account, reliable `/proc` PID/start/descendant visibility and zombie reaping, process groups/signals/flock, working loopback, a PostgreSQL server (`initdb`, `pg_ctl` on PATH), Python 3.12, and matching Playwright Chromium with shared libraries. Prior evidence used 3.12.14; the explicit 29 September WSL decision in `P0A-WSL-SETUP.md` permits 3.12.3 for integration verification subject to unchanged package pins and a fresh matched baseline. The frozen runner never enforced an exact Python patch version. No directly controllable external executor is currently available; the user's WSL machine is an operator-run option, not a connected remote shell. Cloud browser sessions do not supply these capabilities.

Provision dependencies before disabling external network. Use `p0a-python-environment.txt` as the exact package snapshot, not the floating application requirements. Install the Chromium revision selected by that installed Playwright (`python -m playwright install chromium`) in the target runtime only, with required OS libraries provisioned by its administrator. Do not repeat installation attempts in the current blocked runtime. If snapshot packages cannot be obtained, record the specific mismatch and re-baseline explicitly; do not silently substitute versions.

For execution, use a container/network namespace with **only loopback**, an init/reaper, no production mounts or environment, and no externally reachable database. Docker `--network none --init` is one possible runtime arrangement; the image must already contain the dependencies and PostgreSQL and run as a non-root UID. This is not permission to change production infrastructure. A route rule inside Playwright alone is not the full network isolation safeguard.

## Exact commands

Transfer the local branch/commit through a local Git bundle or filesystem copy; nothing is pushed. In the clean checkout of the exact candidate:

```sh
git checkout --detach <candidate-from-final-preflight-review>
sha256sum specifications/019-p0a-bounded-discovery-reliability.md
python --version
python -m pip check
export P0A_EXPECTED_COMMIT=<candidate-from-final-preflight-review>
export P0A_OUTPUT_DIR=/absolute/non-production/output/p0a-gate-a
bash verification/p0a_gate_a.sh
```

The runner refuses dirty/wrong commits, root, external interfaces, `.env` and inherited production connection/model inputs. It checks own/child PID identity, descendant visibility and the matching browser binary before tests. It initialises its own PostgreSQL cluster under a unique `/tmp/p0a-verification.*` directory, bound only to loopback on a temporary port; local trust authentication is confined to this isolated synthetic cluster. It creates `p0a_test_gate_a`, supplies only `P0A_TEST_POSTGRES_URL`, and stops the cluster on exit. The test independently refuses non-loopback/query-overridden URLs and any nonempty target database before mutation. No production URL is needed.

The runner executes candidate tests and a detached baseline at `301a56b3cde781f37e5f5bb0ffaded6537d5ca14` with the same interpreter, dependencies and offline guard. It retains logs, JUnit XML and cluster evidence; remove only its printed unique temporary directory after review. Do not run application pipeline entrypoints outside these synthetic tests.

## Expected evidence, not assumed results

- PostgreSQL: additive migration twice, schema verification, uniqueness/FK rejection, conditional reservation/completion ownership, DDL/data transaction rollback, interrupted-result recovery, statement timeout and subsequent connection work.
- Chromium: actual over-budget navigation, cooperative return, page cleanup and successful subsequent work; document-page recycling followed by evidence refresh; callback-failure process-group cleanup; supervisor death with a surviving lock-holding browser child; watchdog deadline while persistence blocks, with actual browser descendants. All recorded descendants including zombies must disappear, and the owner lock must be reacquirable.
- Deterministic watchdog regression: blocked bootstrap/reconciliation/persistence/final-status scenarios terminate under a two-second configured deadline with a five-second test tolerance; child lock release is checked. This validates containment, not production timing or OOM causation.
- Existing ownership admission remains strict. The additional supervisor-death failure is not baseline-equivalent and must pass in this reliable runtime; never patch out PID/start validation to pass it.
- Compare each affected-suite failure against the same baseline. Baseline-equivalent failures are still failures. Missing PostgreSQL/Chromium skips keep Gate A open. One legacy renderer-RSS test is explicitly deselected in both aggregate commands; it is not counted as passed, and the new browser tests do not assert production memory capacity.

If any lifecycle check fails, preserve stderr, PID/start records, `ps`/`/proc` evidence and lock results before cleanup. Do not claim readiness from matching aggregate exit codes. No SQL optimisation, Stockport retry implementation, AH correction or egress claim belongs in this handoff.

The runner rejects all inherited DATABASE_URL, RENDER*, OPENAI*, ANTHROPIC*, SUPABASE*, PG*, PROPERTYAIGENT_* and P0A_TEST_POSTGRES_URL inputs (including empty exported values) and repository/ancestor `.env` files before any Python/application import or DB initialisation. It clears inherited Python path overrides. It records candidate commit, runner Git blob, dependency snapshot SHA-256, actual package list and clean-tree evidence, and refuses a changed package snapshot.

Measured termination/cleanup times are JUnit properties. Watchdog invocation deadline is a hard stop (no extra grace): the synthetic two-second test adds three seconds for interpreter startup/shared-host scheduling; actual browser eight-second tests add four seconds including reaping. These margins are test tolerances, not additional production work budgets. A parent start budget of 60 seconds yields a 130-second hard envelope, not 125, and earlier invocation/council limits still cap it.

Application cleanup is asserted before fixture teardown. The explicit supervisor-death lock test deliberately performs a test-side SIGKILL after proving the surviving child blocks admission; this proves lock lifetime, not automatic watchdog cleanup. Separate callback-failure/watchdog Chromium cases establish application-driven process-group cleanup. No fixture rescue counts as a pass. A direct local PostgreSQL pass does not validate the production transaction pooler.
