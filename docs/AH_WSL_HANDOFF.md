# AH consumer correction: isolated WSL verification

This handoff does not approve a release or modify P0-A. Use the existing Ubuntu WSL development environment and `~/p0a-work/venv`; Python 3.12.3 is acceptable for this SQLite/pandas consumer check, with the dependency snapshot recorded. No installation, PostgreSQL, browser, credentials or production data needed. A new `~/ah-work/PropertyAIgent` checkout avoids changing the P0-A checkout.

Download `ah-downstream-verification.bundle` and `ah-downstream-verification.sha256` into `~/p0a-handoff`. Check the checksum there before cloning. The accompanying instructions state the full candidate SHA; supply it explicitly to the runner. The bundle contains the full `review/ah-downstream-audit` branch and matched baseline `c8580831590e75936f787fcd2ae08b292fa7908e`.

One step at a time:
1. `cd ~/p0a-handoff && sha256sum -c ah-downstream-verification.sha256` — stop unless OK.
2. `mkdir -p ~/ah-work && git clone ~/p0a-handoff/ah-downstream-verification.bundle ~/ah-work/PropertyAIgent` — missing remote HEAD warning is harmless before explicit checkout.
3. In that new checkout, detach at the supplied full candidate SHA; verify `git rev-parse HEAD` and empty `git status --short`.
4. `bash verification/ah-wsl-run.sh FULL_CANDIDATE_SHA` — never paste a prompt prefix. Enter sudo password only at Ubuntu's password prompt. Existing sudo/unshare/mount/runuser/timeout are required; runner stops if absent.
5. Return the printed `~/p0a-work/ah-results-TIMESTAMP.tar.gz` archive intact. It contains logs, XML, actual failure/skip names, candidate/baseline identities, dependency snapshot and exit codes. We inspect actual results before accepting anything. A nonzero result does not mean no useful evidence was collected.

Safety: runner rejects inherited database/provider/P0-A variables and Python path overrides, and rejects `.env` files in the checkout or ancestors before application imports. It requires an exact clean commit. A temporary network+mount namespace exposes only down loopback; tests run as the normal user with empty environment except safe test inputs, fresh HOME, plugins disabled and `DATABASE_URL=sqlite:///:memory:`. Fixtures create fresh SQLite in-memory schemas. No production query or external model call can succeed. Namespace setup uses sudo only; tests do not. Baseline worktree is removed after results; committed application evidence is never touched. Outer envelope 950 seconds plus 10 seconds termination allowance; each pytest group 300 seconds plus 10 seconds. A host/runtime failure can still require operator cleanup; no claim of P0-A lifecycle verification.

Candidate and baseline run the same affected suites (`test_agent_ready_fact_foundation.py`, `test_affordable_housing_scope.py`). Candidate additionally runs eight new consumer cases separately; baseline does not contain them. The standalone pandas filter unittest is also recorded. Failed/skipped cases remain explicit; baseline equivalence is never converted to pass. This is targeted AH verification, not the P0-A suite or a benchmark.

Preparation checks in Astra: shell syntax, Python compilation, diff whitespace passed; actual standalone pandas filter unittest passed (one test). pytest/SQLAlchemy missing in Astra prevents local ORM execution. WSL namespace execution and ORM results remain unverified until the returned archive is inspected.

## Buyer-trust follow-up
The current handoff baseline is c5b17a0ddb5a088502288bc58935ecc07ba05535 (the earlier baseline above is historical). The current runner adds buyer-matching, B2-policy and evaluation-persistence suites, and expects20 new-test cases (prior8 plus12 buyer-trust regressions). Use the separately supplied current bundle and exact SHA. This is required because matching code changed, not a repeat of the old acceptance run.
