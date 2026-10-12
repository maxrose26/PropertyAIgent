# Stage 4 three-summary canary registration candidate

Stage4 remains OPEN. Registration is not live execution authority. No live
workflow dispatch, source request, B2 persistence or production query is authorised.

## Integration identity and scope

Remote base master: d253773a09690f27b150adb701c95f9aa3ee210f.
Accepted offline mechanism: PR61 dd88c922ad75ba0ae9c2e9f826086cf1fa9c838d.
This separate registration PR imports only four byte-identical accepted files:
refresh.py, manifest.json, fixtures.py and __init__.py. All transitive repository
parser/qualification dependencies already exist on the base and are byte-identical
to PR61; accepted-dependencies.json pins their SHA256 digests.

No application runtime, B2 writer, database schema, Render configuration or normal
production dependency file changes. PR61's status-only writer changes, native
PostgreSQL additions and unrelated acceptance history are not integrated. The
copied module's dormant refresh() helper is not called; its B2 import is denied
by AuditFence in every worker. Only retrieve() and source qualification are used.
This is an explicitly scoped integration of accepted artifacts, preserving original
provenance, not a replacement claim for PR61's accepted history.

The exact candidate/head/tree, hosted results and merge/registration state belong
in the PR handoff; this file cannot embed its own SHA.

## Frozen cohort (execution order)

| Council | Application/site | Reference | Source identifier | Retained context |
|---|---|---|---|---|
| Bolton | 202/129 | 00307/26 | TAPAO1DEGJP00 | Deposited; optional decision/date; UNKNOWN semantics allowed |
| Oldham | 42/28 | FUL/355686/26 | TA7382MCIP700 | Retained awaiting-decision/refusal contradiction control |
| Stockport | 78/58 | DC/078942 | QKM8H1PJGJA00 | Retained Decided / Granted / Wed27Dec2023; dated manual-summary observation |

Exact destinations:

- https://paplanning.bolton.gov.uk/online-applications/applicationDetails.do?activeTab=summary&keyVal=TAPAO1DEGJP00
- https://planningpa.oldham.gov.uk/online-applications/applicationDetails.do?activeTab=summary&keyVal=TA7382MCIP700
- https://planning.stockport.gov.uk/PlanningData-live/applicationDetails.do?keyVal=QKM8H1PJGJA00&activeTab=summary

Stockport is selected entirely from retained evidence. It has complete identity,
a straightforward terminal decision/date and historical manual-source provenance.
Its /PlanningData-live path is already configured in the accepted shared Idox
mechanism, making it a useful generalisation control without new transport logic.
No current status was looked up or assumed. The retained census is dated9October;
its facts are expectations to compare, never instructions to force current truth.

The unchanged 202-manifest hash is
ce143eafd498e89129965d098b2f820295fa1d1e1b4d9458f5d9209543071dde.
Only the three hard-coded tuples above can enter the registration runner. There
are no URL, council, reference or cohort-substitution workflow inputs.

## Admission and single use

Live workflow: .github/workflows/stage4-direct-live-once.yml.
Manual workflow_dispatch ONLY; no push, pull_request, schedule or workflow_call.
Ubuntu24.04 GitHub-hosted runner; contents:read; checkout credentials not persisted.
No secrets expressions, production environment or database service.

Require reviewed_sha equal to github.workflow_sha and checked-out HEAD, clean
tracked/untracked worktree, exact workflow repository/path, immutable run ID,
github.run_number==1, github.run_attempt==1 and exact acknowledgement:
AUTHORISE_STAGE4_THREE_SUMMARIES_ONCE_NO_PERSISTENCE.

First dispatch consumes the one-use slot even if admission/setup/source access
fails. Rerunning jobs or dispatching again is denied. No workflow deletion/rename,
run-number reset or alternate workflow is authorised to renew that slot. Such a
change requires new REVIEW authority. Concurrency serialises admission attempts.
The acknowledgement is deliberately NOT_AUTHORISED by default.

## Bounds and cleanup

At most2 GET attempts/reference, one transient retry, zero followed redirects,
1,000,000 body bytes/response,2,000,000/reference,6,000,000 total, concurrency1.
The shared body reader can observe the rejecting chunk (maximum16,384 bytes) when
it detects overflow; this is reported as exhausted and never successful. It does
not claim a wire/TLS/header-byte cap or known unread buffered bytes.

Each disposable worker has an independent45s wall ceiling,512MiB address-space
limit and30CPU seconds. Shared retrieval retains40s cooperative reference timeout,
3s connect/8s read maxima and20,000tag/256row parser ceilings. Sessions and responses
close in finally blocks. No browser/JS/assets/search/further-information/documents.

Whole acquisition ceiling is140s, reduced to180s minus measured setup time minus
20s cleanup/upload reserve. Never launch another worker with less than45s remaining.
The job has an independent three-minute platform maximum. Slow dependency setup
can therefore prevent any source work, or prevent a later reference; this is an
explicit stopped run, not permission to increase limits. No setup-time or source-
time live measurement is claimed.

Reuse the accepted ordinary process-group supervisor. Hosted runner disposal is
the final process boundary; no hostile-descendant or OS network-isolation claim.
Workers get fresh temporary HOME/TMPDIR and env-i allowlisted metadata only. No
GitHub token, proxies, service credentials or source cookies are inherited.

## Audit and success/failure

At most16KiB per reference and48KiB combined JSON. Closed schema admits only frozen
identity, literal status/decision/date, normalized counterparts, field states,
semantic qualification, fixed outcome enums and numeric/UNKNOWN accounting.
No raw HTML, unrelated fields, proposal text, arbitrary headers, exception strings,
cookies, applicant/contact information or documents enter the artifact. Worker
stdout/stderr are discarded; output is validated before publication.

Per-reference literal success requires complete exact displayed reference/status,
correct optional-field states, no conflicts, successful parsing, reconciled counters
and closed responses/session. NOT_PRESENT never establishes NULL. Deposited may
remain UNKNOWN_UNMAPPED. No B2-eligibility claim is an acceptance stamp, and this
runner emits no database update or verification watermark.

Counters include attempts, observed redirects (none followed), retries, consumed
body bytes, elapsed time, budget and cleanup states. Interrupted/missing/invalid
worker results become UNKNOWN accounting, not manufactured zeroes. Never-launched
references are explicitly NOT_ATTEMPTED with known zero requests. Parent interruption
or platform cancellation can prevent an artifact entirely; missing artifact is
failed acceptance, never zero activity or success.

Stop at the first failure; later references remain NOT_ATTEMPTED. Access failures
are recorded per source and do not prove shared architecture invalid. Identity,
scope, redirect, privacy, accounting, artifact or cleanup failure stops and fails
the entire canary. No patch/retry/new council/search fallback follows any live run.
The allowed internal transient retry is the only retry budget.

Overall COMPLETE requires all three literal successes, without requiring matching
field shapes or mapped semantics. Other results are STOPPED_REVIEW_REQUIRED.
No persistence occurs for either outcome.

## Offline verification and independent review

Registration tests cover exact copied dependencies/cohort, shared successful
parsing, Deposited/optional states, wrong identity/conflicts/partial bodies,
HTTP429/403/404/503 and redirects, transport exceptions, response overflow, privacy,
cleanup failure, interrupted unknowns, stop-on-first-failure, exact SHA/workflow/
first-attempt admission, environment stripping and the persistence import fence.

Separate PR-only offline workflow runs these plus accepted Bolton, B2/B2.1, L1,
status and Stage1 access/outbound regressions under network denial. It also installs
the minimum pinned dependency closure and executes the actual supervisor against
three explicitly synthetic fixtures. No live workflow dispatch is used for testing.

Independent review identified a response/parser/deadline-bound accounting ambiguity;
registration now marks rejected individual ceilings EXHAUSTED rather than using
only aggregate bytes to report WITHIN_LIMITS. The shared accepted retrieval file is
unchanged. Hosted/local exact results must be read from the final handoff.

## Registration versus execution state

A branch publication alone is not an active manual workflow registration. After
hosted CI and review, minimal default-branch integration is the requested operational
registration change. Confirm workflow active and its run collection empty before
asking for one live execution. Do not dispatch to prove registration.

At preparation, current Render deployment-impact verification was unavailable:
Render connector returned no selected workspace and requires explicit user workspace
selection. It lists My Workspace (tea-d9qbf8jm8hqs7385cu0g). Historical repository
records say auto-deploy OFF; they do not establish current service settings. No
workspace was selected, Render settings changed or deployment performed. If this
preflight remains unresolved, do not merge and do not claim GO—CANARY REGISTERED.
Finish and publish the tested candidate, then return the exact outstanding access
confirmation. No broader infrastructure review or production-data access is needed.

Stage4 stays OPEN. This canary does not establish116 live-compatible references,
seven-council Idox coverage, full ten-council GM refresh, cadence or new discovery.
Arcus and discovery are unchanged, separate outstanding work.
