# P0-A — WSL integration evidence for independent Gate A assessment

Gate A is submitted for assessment, not declared approved. No release authorised.
This report supersedes runtime-unavailable conclusions in previous dated reports;
historical failures and skipped evidence remain preserved.

## Exact state

Tested candidate: ff0baa237f809265be50b72247633a7b7a193c1d.
Candidate working tree clean at test start. Baseline:
301a56b3cde781f37e5f5bb0ffaded6537d5ca14.
Runner blob: 9102803d9b2db4b52e22b4b7c46aa4a5657a1723.
WSL wrapper distribution commit: 47a61904ca847202ddb8ae01f62f5910e0d8f0fb.
Development branch: feature/p0a-bounded-discovery. Subsequent report commit changes
only evidence documents, not the tested application or runner.
Spec 019 remains byte-identical:
c007e2b2912ae5d8817142c32fdf35e0000f72d4fa127d5c83e32e6ef10970f8.

User-operated Ubuntu 24.04 WSL2, Python 3.12.3, PostgreSQL 16.15,
Playwright 1.63.0 / Chromium build 1243. Pinned dependency snapshot matched exactly.
Python patch-version difference from earlier 3.12.14 evidence was explicitly accepted
for verification; both candidate and baseline executed with the same environment.
Loopback-only network namespace, isolated PID namespace with tini reaping, non-root
tests, production-input and .env rejection, disposable UTF8 database.

## Actual results

Candidate: 351 passed, 4 failed, 0 skipped, 1 deselected, 66.72s.
Baseline: 282 passed, 4 failed, 0 skipped, 1 deselected, 27.75s.
All four failures match names and missing OPENAI_API_KEY errors in existing intelligence
processing tests (selection, extraction limit, one-failure isolation, bounded workload).
These are failures, not passes. No API key was added and no paid calls were made.
The same legacy renderer-RSS test was deselected in both runs; its claim remains untested.
No candidate-specific failures remain in this affected-suite run.

PostgreSQL test actually passed: additive migration, second-call idempotence, schema
verification, unique reference and foreign-key constraints, transaction rollback,
conditional ownership completion, committed reservation survival, interrupted-owner
recovery, stale-owner rejection and safe continuation. Statement timeout abort and
subsequent connection work also passed. Initial run failed before those assertions
because the runner selected SQL_ASCII; correction explicitly selects UTF8 and records
it. PostgreSQL log confirms final shutdown. Direct local PostgreSQL does not establish
Supabase or transaction-pooler behaviour.

All five real Chromium tests passed: slow navigation cancellation and subsequent work;
document-page recycling followed by evidence refresh; application cleanup following
supervised failure; supervisor death with surviving child lock; and watchdog cleanup
when persistence blocks. Exact process identities including zombies were checked.
Application cleanup assertions occur before fixture teardown. The explicit supervisor-
death test deliberately kills the surviving child after proving lock exclusion; this
establishes ownership lifetime, not autonomous cleanup following every supervisor death.
The strict PID/start-time ownership admission test now passes without weakening admission.

Measured cancellation: 0.204s. Blocked-persistence browser termination: 8.439s;
termination plus descendant removal and successor admission: 8.492s (8s + 4s scheduling
margin). Five non-browser persistence blocks: 2.442–2.456s (2s + 3s margin).
SIGTERM-resistant child: 5.224s (0.1s synthetic stop + 10s cleanup + 1s margin).
Confirmed termination to successor admission: 0.021s. Full stderr pipe: 0.568s.
These are synthetic correctness measurements, not production capacity or memory proof.

## Material refinements and limits

MODE remains bounded|disabled; ACTIVATED and DISABLED are additional 0|1 inputs,
default 0. All values validated before precedence; invalid values reject admission.
Either disable input wins. Production requires ACTIVATED=1 plus strict runtime identity;
MODE=bounded alone never activates production. No production configuration changed.
Separate emergency watchdog process supplements cooperative bounded browser operations;
SIGALRM is not used. Parent envelope is start budget + 60s + 10s: 130s for a 60s
start budget, capped by earlier council/invocation deadlines. Approved spec is unchanged;
this refinement and extra activation gate remain disclosed deviations. Bounded log queue
overflow fails honestly. Watchdog loss while supervisor is blocked, OS uninterruptible
states and descendants escaping their groups remain limitations; no universal guarantee.
One additive ParentLookupWork table and nullable run progress remain the only schema work.
No advisory-lock fallback, general queue or stage continuation was introduced.

## Remaining release gates and controlled proposal

Independent Gate A review and disposition of the four baseline failures/deselected test.
Verify Render runtime service/instance identifiers, sole discovery entrypoint, scheduler
successor termination guarantees and actual database-path timeout behaviour. Verify
transaction-pooler compatibility separately. Approve exact release state and additive
migration before any production step. Agree representative configurable limits and
Manchester/Salford-only smoke scope; no Stockport trial or platform-wide readiness claim.

Proposed rollout remains migration-first under suspended discovery, schema verification,
then approved inactive release, followed only on approval by one supervised, capped
Manchester/Salford smoke using agreed reference and time budgets, measured memory,
per-stage coverage, deferred work and downstream progress. No bulk recovery. Smoke
success precedes a separate seven-daily-cycle observation window; neither blocks
unrelated approved AH design or benchmark preparation. No numerical production budget
is inferred from these synthetic tests.

Rollback: suspend discovery, positively verify all relevant processes terminated, then
use an approved bounded version or keep discovery suspended. Reverting to old code must
not resume uncontrolled discovery: it may ignore the new flags. Preserve additive
schema, committed evidence, continuation and run-health records. No destructive downgrade,
age-only owner recovery or bulk replay. Production remains inactive for P0-A.

No push, merge, production migration, deployment, live scrape, paid call or production
configuration change. No Stockport retry change, AH remediation, egress attribution or
SQL expansion. Reliability improvements do not prove the Manchester OOM root cause.
