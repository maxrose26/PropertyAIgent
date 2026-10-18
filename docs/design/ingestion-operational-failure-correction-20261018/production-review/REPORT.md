# Operational successor review package — no live release

**Recommendation: accept PR128's offline correction; release only the connection-only diagnostic next. Keep capture/screening held until its actual restricted-route result is reconciled.**

## Exact checkpoint
- Candidate: `07f4dc05d8fbd16d537d3ba2b1e9767407a4ae8d`.
- Tree: `a9d28fcf3994d2105c79b15e8f717f752d591e3c`.
- PR: https://github.com/maxrose26/PropertyAIgent/pull/128 (draft, not merged).
- Accepted integrated base: `acd3f5690b439d7d91b7a7efb9ace79c9098d303`; master is not moved by this work.
- Accepted cleanup: `8dc4a36bc5565318e138d192bf2f7e96906f048f`. Controller CLOSED; post-exit systemd scope removal unverified. Historical UNCERTAIN outcomes and original accounting gaps remain unchanged.

## What the evidence establishes
The original worker connection failed before runtime cursor SQL and before any source request. Its exception was redacted; the underlying cause remains **UNDETERMINED**. The factory already selected the approved pooler endpoint, project-suffixed custom username, verified provider CA/verify-full and the fixed selected address. No connection mode, credential route or TLS weakening is introduced here.

The new diagnostics emit only exact role, attempt, connection phase, allowlisted exception kind and validated SQLSTATE. No arbitrary message, URL, password, verifier or query text is exported. Server/client failures without SQLSTATE remain unclassified. Supabase's published routing convention is context, not proof of this project's runtime authentication.

References: https://supabase.com/docs/guides/troubleshooting/supavisor-faq-YyP5tI ; https://www.psycopg.org/psycopg3/docs/api/connections.html ; https://www.psycopg.org/psycopg3/docs/api/errors.html .

## Corrections and guarantees
1. Qualify both restricted connections before issuing any new execution grant/exception. Count that work in the capture slot's cumulative receipt; no allowance reset.
2. If a later connection fails before ledger construction, the trusted owner connector can invalidate the exact registered grants/exceptions independently, advance the hard-stop generation and read back the result. A known invalidation permits fixed teardown. If commit/invalidation is uncertain, report UNCERTAIN_RECONCILE and stop mutations; remote invalidation cannot be guaranteed during a database outage.
3. Track pending authority before possible registration commit ambiguity. Track uncertain SQL and GitHub mutations independently; no subsequent mutation after either uncertainty, including lost second secret-mapping or deletion acknowledgements.
4. Save failure final-result.json with administrative/runtime counters, opened/closed connections, cumulative prior-slot use, safe diagnostics, source invocation versus retained capture, explicit resource unknowns and actual failure readbacks. Preserve an already-written complete result if terminal output fails. OOM, hard kill or filesystem failure can still prevent finalisation; existing audits then remain reconciliation evidence rather than fabricated completion.
5. Bound hidden input separately to300 seconds with no DB/secret API operation. Active operation480 seconds:450 work,25 diagnostic reserve,5 hard-bounded reporting. Proposed outer790 seconds includes input/setup. Reporting is protected by both signal and shortened hard watchdog; blocked fallback output cannot consume the remaining full job allowance.
6. Check projected persisted replacement, temporary concurrent file and terminal output before writing, within2MiB combined output. Export source supervisor/resource observations even when the returned source capture is rejected; unknown received-body accounting is never represented as zero.
7. Reuse accepted installed roles/functions. Verify exact retained function bodies/owners/search path, dormant role/password/member state and the exact accepted activation gate before mapping. No storage reinstall/seed. The capture mode additionally needs a two-function owner policy patch binding an exception to accepted hard-stop generation1 without resetting it. Diagnostic-only does not install that patch or issue an exception.

## Exact focused validation
All9 exact-head hosted check runs passed. Independent review PASS for this candidate/tree, after substantive findings were corrected.

Native workflow: `39115906670`, number200, attempt1; restricted-provisioning job `117641520668` SUCCESS. Focused operational wrapper XML:45 tests,0 failures,0 errors,0 skips. Additional required native checks passed; their existing suites were reused through the required workflow, not rerun as additional manual validation.

Real Linux gh used loopback TLS fixture transport, not a mocked executable. PostgreSQL17 used real restricted logins and a comparable non-superuser migration principal. Production-shaped hostname/project username/CA/verify-full/pinned-address kwargs were checked before a disposable transport translation. **This does not emulate managed Supavisor authentication.**

Rehearsed: full60-row capture, durable publication/readback,12 retained five-row batches, pause/resume without source replay, duplicate completion reuse, effective denials, dormant-access reuse, generation1 exception binding, unrelated-council denial, generation2 invalidation, first-worker connection denial, post-grant/pre-ledger connection denial, uncertain invalidation commit, uncertain second mapping, source callback failure, teardown/deletion failures, input delay/timeout/expiry and blocked reporting.

### Recorded measurements
| Path | Runtime | Administration | Other evidence |
|---|---|---|---|
| Reused installation,60 rows,interruption/recovery |830 commands;29 connection attempts;1,662,959 returned data-value bytes;3.456470s recorded phase time |95 commands;6 opened/closed connections;119,820 returned bytes;0.986831s recorded phase time |118,268-byte audit;25 gh invocations;16 effective denials |
| Connection-only diagnostic |16 commands;2 opened/closed connections;392 returned data-value bytes;0.025657s recorded phase time |46 commands;4 opened/closed connections;26,926 returned bytes;0.764669s recorded phase time |7 gh invocations;zero execution grants,source calls,work attempts or ledger changes |

Fixture installation alone cost46 commands/1 connection, recorded separately. Negative preflight probes and policy assertion commands are fixture assertions, not operational commands. Recorded elapsed phase timings include fixture coordination and must not be sold as production latency measurements. Synthetic listing calls are not council traffic. Kernel-enforced controller256MiB/source1GiB/aggregate1.5GiB limits and native excess-memory cleanup checks passed; the wrapper's exact memory peak is not exported by its measurement property, so no peak figure is invented.

## Unchanged ceiling and stop contract
Runtime1040 commands/40 connections/4MiB returned DB values/300 supervised seconds; administration240 commands/13 connections/1MiB/240 seconds. Source10 attempted requests/3,000,000 received-body bytes/500,000 per response/45 worker seconds/6 pages/60 rows. Up to12 five-row batches. Active480-second overall ceiling; phase maxima are not additive. Controller256MiB,source1GiB,aggregate1.5GiB,swap0;2MiB combined output,512KiB source-worker audit. DB data-value bytes and received source-body bytes are not wire traffic.

No retry, replacement observation, stronger-role fallback, detail/document/parent retrieval, application/B2/unit writes, scheduling or deployment. Original Salford stop and STORAGE_TEST_STOP remain. Every new hard stop invalidates the scoped exception; no global barrier release.

## Grouped next decision
The original two logins now have no passwords, so an actual custom-role handshake necessarily requires a newly approved finite credential lifecycle. A migration-only catalogue query cannot prove their authentication. Do not replay full installation merely to obtain an error message.

**Recommended single diagnostic release:** existing two roles and the same accepted mapping/TLS mechanism only; read-only prerequisite/function inventory, restore only their same reviewed memberships, run the exact pre-mapping permission gate, generate independent48-byte passwords in RAM, map only the two exact protected secrets, activate under the reviewed gate, attempt each restricted connection once with identity/read-only driver initialisation, close both, then disable/password-null/revoke memberships/delete both temporary secrets and read back. No generation-policy patch, execution grant, exception, discovery work insertion, council call or pipeline activation. Abort after the first failed restricted handshake. Use existing ceilings above as hard caps; the actual measured path is much smaller. Do not borrow original incomplete accounting or retry after ambiguity. Expiry at release<=24h, with immediate teardown.

Pass requires both exact identities/NOBYPASSRLS profiles and transaction modes, certain accounting, no executable authority, unchanged ledger/control, disabled access, absent temporary secrets with DATABASE_URL preserved, and positive connection/process closure. An uncertain mutation or teardown stops and returns its actual readbacks. A connection failure returns safe phase diagnostics; its underlying cause may remain unknown without provider evidence.

**Capture release remains separate and HELD.** If later approved, it uses the same candidate, fixed Bolton RECEIVED16October2026, generation1 policy patch and at most one capture, followed by retained-only screening. Europe/London interval16Oct00:00–17Oct00:00BST corresponds to15Oct23:00–16Oct23:00UTC (end exclusive). No eligible rows/explicit zero proves discovery only. It does not authorise B2/admission. No consumed scope is silently renewed.

Both included registration files are explicitly HELD, with no release/expiry/evidence head; production validation rejects them. Their manifest hashes freeze proposed contents for review. A new owner-approved release must bind the post-integration revision/tree,dependencies,manifest,exact accepted control hash,evidence head and expiry. No credential should be entered before that release and the guided command are supplied.

## Native artifact preservation
Artifact12132182744:73,021 original ZIP bytes; SHA256 `e87fe64a7404a9b4cc9c1a1cbc7c737670da6c07ddd246b2c79c75d9f77a49e0`. Downloaded digest independently verified; original ZIP and base64 mirror/member hashes retained. Operational XML SHA256 `4abe5bc52e524426613842090e580d6a087a71cb011a2f9ca6f7abf97fe19b48`.

Storage remains accepted. Operational acceptance and backlog completion remain outstanding. IDs1504–1508, all retained evidence and blocked scopes remain protected. Stage4 remains OPEN.
