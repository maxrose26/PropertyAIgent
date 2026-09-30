# First WSL verification — Gate A OPEN

Operator evidence: results-20260929T084954Z, 29 September 2026.
Candidate e1b53eb4b942eb7b27fa14b49a60731eb2179293, clean checkout;
runner blob a82af5ab4f49675a92cba4ad10f9f6fae11f5969.
Baseline 301a56b3cde781f37e5f5bb0ffaded6537d5ca14. Python 3.12.3,
unchanged pinned dependencies, local PostgreSQL 16.15, matching Chromium.

Candidate: 350 passed, 5 failed, 0 skipped, 1 deselected (66.88s).
Baseline: 282 passed, 4 failed, 0 skipped, 1 deselected (27.13s).
Four shared failures require an absent OPENAI_API_KEY in intelligence-processing tests.
No credentials should be added to resolve those baseline failures. The earlier SOCKS
failure did not recur in this clean runtime. Baseline-equivalent failures are not passes.

All five real Chromium tests passed: cooperative deadline cancellation (0.210s),
page recycling then evidence refresh, supervised callback failure cleanup,
supervisor death with inherited child lock, and blocked-persistence watchdog cleanup.
The supervisor-death test deliberately kills the surviving child process group before
asserting release; it does not prove automatic cleanup upon arbitrary supervisor death.
The callback-failure and blocked-persistence tests assert application cleanup before
fixture teardown. Blocked persistence with browser: supervisor termination 8.411s,
descendants absent and successor admission at 8.412s, against 8s + 4s scheduling margin.
Five non-browser persistence stalls terminated in 2.415–2.503s against 2s + 3s margin.
The previously failing real inherited-lock test passed; confirmed termination to
successor admission was 0.0208s. Strict ownership admission remains unchanged.

The PostgreSQL test failed on initial SQLAlchemy connection, before migration or
transaction assertions. initdb.log explicitly reports locale C and SQL_ASCII encoding;
the driver returned PostgreSQL version as bytes, rejected by SQLAlchemy's string regex.
This is a verification setup defect, not evidence that migration passed or failed.

Narrow correction: initialise the disposable cluster explicitly with UTF8 and locale C,
assert server encoding before database creation, and record encoding. No dependency,
application, migration, ownership, timeout, or approved specification changes.
Shell syntax/diff checks are local only; corrected PostgreSQL checks require a WSL rerun.
Keep the exact specification hash c007e2b2912ae5d8817142c32fdf35e0000f72d4fa127d5c83e32e6ef10970f8.

No release approval. Outstanding: real PostgreSQL migration/ownership/rollback/recovery
assertions; review corrected evidence; Render identifiers, sole entrypoint and scheduler
guarantees; actual database path timeouts and transaction-pooler compatibility;
migration-first release approval, trial limits and Manchester/Salford smoke scope.
Stockport remains outside this release candidate. No OOM-root-cause or egress claim.
