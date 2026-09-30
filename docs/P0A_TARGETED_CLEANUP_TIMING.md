# Targeted cleanup timing review — 29 September 2026

The premise of a 13.46-second browser-cleanup failure is not supported by the uploaded archives. XML identifies 13.463782665s as `statement_timeout_elapsed_seconds` in `test_pg_real_timeout_retry_and_subsequent_work`, failing its lower bound of 14s in c1c3da4. It is not a browser measurement and must not be compared with the browser test's 12s envelope. The later PostgreSQL result was 15.001804s and passed the unchanged bound; the earlier discrepancy remains unexplained.

Actual browser blocked-persistence cleanup:

| Archive UTC suffix | Supervisor termination | Termination, descendant absence and successor admission | Entire pytest case |
|---|---:|---:|---:|
| 110519Z (c1c3da4) | 8.463527s | 8.515689s | 8.869s |
| 111800Z (06b978c) | 8.510289s | 8.562712s | 8.952s |

Both cases passed the unchanged 12-second envelope. After supervisor termination the remaining measured interval was about 0.052s in each case. Pytest total duration additionally includes fixtures; it is not the application deadline measurement. No surviving recorded browser PID/start identity or retained owner lock was detected: those assertions precede the final elapsed property and passing assertion. This is not evidence of zero scheduling delay, nor a diagnosis of the unrelated PostgreSQL clock discrepancy. Earlier archives also show passing cleanup measurements of 8.412s and 8.492s, but do not substitute for repetitions of the exact current candidate.

## Bounded requested repeat

Prepared external WSL handoff `verification/handoffs/p0a-cleanup-repeat.sh`, to be downloaded to ~/p0a-handoff/p0a-cleanup-repeat.sh. It uses the existing reviewed WSL isolation wrapper, exact clean candidate 06b978c59ece44bb20efc6d5b26009d769a22b5d, same dependency snapshot and browser, loopback-only network, PID namespace, non-root test execution and credential/.env refusal. It does not modify the checkout or run a database migration. Only `test_real_browser_cleanup_when_persistence_blocks` runs, in five separate pytest invocations. It stops at the first nonzero result rather than retrying it away. The XML assessor rejects skips or missing/multiple cases.

Each attempt preserves XML, log, exit status, original browser PID/start records in the pytest temporary directory and the existing timing properties. A passing case specifically establishes descendant absence and successor lock admission before fixture teardown; summary labels these as assertions by the test, not independently sampled telemetry. Namespace cleanup contains a failed attempt but cannot change its recorded outcome to pass. The 8-second invocation deadline and 4-second startup/reaping allowance are unchanged. Five passes provide a small consistency sample, not sustained production health.

This remote runtime lacks the integration dependencies and cannot operate the user's laptop. No installation was attempted. Required operator action: download the script/checksum, verify it, then run `bash ~/p0a-handoff/p0a-cleanup-repeat.sh 06b978c59ece44bb20efc6d5b26009d769a22b5d` from the existing authorised WSL setup and return the generated cleanup-repeat archive. No new results archive exists until that execution occurs. Current local checks: shell syntax and embedded Python AST parse, diff whitespace check. Not an integration pass.

The prior affected-suite result remains 365 passed / 4 baseline-matched failures / 0 skipped / 1 deselected, against baseline 282 passed / 4 failed / 0 skipped / 1 deselected. The deselected test is page_recycling_keeps_renderer_rss_flat_across_navigations. Baseline failures remain the four missing-OPENAI_API_KEY tests; this browser-only repeat does not rerun or resolve them. No application defect has been found from this timing premise; no application code or threshold changed.

## Reviewable old-cron suspension decision — not executed

Last verified state: old discovery enabled at 05:00 UTC on 6fd4202; it ignores P0-A switches. No fresh live inspection was performed in this timing review. Cohort 24–29 September: 3 Bolton applications, 1 Bury application, 10 Bolton documents downloaded/text-extracted, plus 7 Manchester applications committed; timestamps alone are not exclusive writer attribution. Repeated Manchester OOMs left Oldham, Rochdale, Salford, Stockport, Tameside, Trafford and Wigan unattempted on five consecutive days. Suspension loses useful early-council updates while containing repeated incomplete execution.

Proposal: after explicit approval, suspend on 29 September, with completion no later than 30 September 04:45 UTC (05:45 BST), ahead of the 05:00 UTC slot. Before acting, recheck current service, deployed command, enabled state and active execution. Confirm the scheduler is suspended and any existing execution is terminal using Render run/termination evidence; a stale running database row is neither proof of activity nor proof of termination. If suspension leaves a run active, report that and obtain explicit cancellation approval if required; do not assume suspension killed it.

Review the pause at the next release review and no later than 1 October 04:30 UTC (05:30 BST), before the following daily slot. Continued pause or resumption is an explicit decision, not an automatic expiry. Resume only via a separately approved migration-first inactive release, positive real scheduled-job identity and database-path checks, then bounded Manchester smoke and Salford after confirmed termination. Rollback preserves evidence/continuation/additive schema and keeps uncontrolled old discovery suspended. No suspension, deployment, migration, scrape, push or production configuration change is authorised or performed here.

## Actual five-repeat evidence received 29 September, 12:53 BST

Archive cleanup-repeat-20260929T114934Z.tar.gz SHA-256 daab6b9b9a22abf93c7ae11fadc660323bf5273e648a0df6b7f3db67037113cf. Exact tested candidate 06b978c59ece44bb20efc6d5b26009d769a22b5d; clean manifest. Runner SHA-256 9baa70be07218b54fbce27305d3824c11fb598374f61985e0eb2aafe931802cb matches the handed-off script. Dependencies match the pinned snapshot byte for byte. Each individual XML contains one passing case, no failures/errors/skips; all five pytest exits and outer runner exit are zero. Seven browser/driver descendant PID/start identities are recorded per attempt. The test verifies their absence and successor lock admission before recording completion and before fixture teardown.

| Attempt | Supervisor termination | Cleanup including descendant absence and successor admission | Limit |
|---|---:|---:|---:|
| 1 | 8.453580s | 8.506020s | 12s |
| 2 | 8.439719s | 8.492197s | 12s |
| 3 | 8.453765s | 8.506854s | 12s |
| 4 | 8.425311s | 8.477927s | 12s |
| 5 | 8.457940s | 8.510563s | 12s |

The first entire pytest suite duration is 12.191s, which includes collection/setup/teardown; it is NOT the application cleanup measurement of 8.506s. No threshold was changed and no fixture/namespace cleanup was used to turn an application assertion failure into success. Pytest absolute `current` symlinks in the archive were excluded during safe extraction; regular logs, XML, manifests and original process records were inspected.

Conclusion: the requested browser-cleanup check is consistent across these five local repetitions. No browser-cleanup defect or environment-only overrun was demonstrated. The earlier 13.46-second measurement belongs to the database test and remains an unexplained prior anomaly, not explained by these browser repetitions. No more browser repetition is warranted by this evidence. This is a small synthetic sample, not production readiness or sustained reliability.

No application/test/limit change resulted. The actual tested commit remains 06b978c; subsequent commits only preserve documentation and the external targeted handoff. Full-suite exceptions remain four baseline-matched failures and one deselected memory test; the targeted run does not rerun the full suite. Suspension remains a proposal with the review/termination conditions above; no production action occurred.
