# Independent shared ingestion review

PASS for the exact offline/disposable implementation candidate; PostgreSQL execution acceptance remains pending. No remaining code blocker found in final inspection.

Verified local commit `4339b18d3d31ac0a85149dfaaff8fd8cd6cbb8f3`, tree `b38dc743db09cc577b40bfd2c5d8387c8f46ef8e`, with clean working tree. Reviewed app/ingestion coordinator, ledger, schema, listing screener, focused SQLite/retained-evidence tests, seven disposable PostgreSQL tests, implementation/operations document and backlog representation plan. No implementation changes, live source or DB calls, or repeated passing suites performed by reviewer.

## Verified boundaries

Source task/subject/council/window/contract preflight now occurs before intent reservation and reader invocation. Ledger operations enforce task compatibility: only factual tasks reserve writes; source reservations require listing/discovery scope tasks. Retained listing cannot clear SOURCE_INTENT. Source checkpoints require independently supplied outer cleanup/accounting proof. Typed finite nonnegative source/outer accounting, successful exit, per-task limits, exact row provenance and segment hashes are checked before reusable receipts.

Claims serialize under a control-row lock/reservation, bind owner/fence/expiry and immutable exact task identity, check dependencies and finite grants. Child insertion validates the live parent claim in the same serialized transaction; stale children cannot be published. Concurrent duplicate/overlap work reuses stable evidence-version keys and conservatively preserves original dependencies. Grant counters are reserved durably before effects and never refunded on interruption. Claim recovery is not source replay permission.

Abandoned source intent, unknown cleanup/accounting and uncertain factual persistence set a durable global stop. WRITE_INTENT blocks subsequent work even if later stop acknowledgement fails. Shared B2 remains the sole factual writer; SQLite explicitly cannot exercise the separate factual transaction path. Successful B2 committed readback checkpoints can resume acknowledgement without another write; changed readback stops for reconciliation. No exactly-once cross-transaction claim is made.

Evidence and attempts are durable, bounded and retained without requiring an expiring external artifact URL. The 32 MiB bound now counts UTF-8 column payload bytes using PostgreSQL octet_length / SQLite BLOB length, and documentation explicitly excludes physical storage/index/TOAST overhead. Task/attempt row caps and per-payload caps remain additional bounds. Oversize evidence is rejected, not silently truncated.

The screener/citation implementation is preserved without silently adopting the six advisory exclusions. Literal references, supporting wording, provenance and UNKNOWN target council/relationship remain intact. Source/metadata completion does not imply usable proposals, positive relevance, fact delivery or catch-up completion.

Schema remains additive and separate from ordinary application startup metadata; no production controller, source client, historical authority reuse, queue population or scheduling activation is supplied. Default-deny RLS/ACL is intentional. Test grant authority and trusted supervisor/operator inputs are not represented as an untrusted-agent security boundary.

## Backlog and operations assessment

Representation plan preserves 14 accepted Manchester captures, 401 deferred application metadata tasks and 13 blocked/unqualified scope partitions. The consumed Salford stop remains explicit; Rochdale is unqualified, not failed by a new execution. Four historical gaps, bridge limits, independent-only identities, accepted IDs, pending Oldham facts, parents, Stockport and Trafford exclusions remain separate. The plan has no source allowance or production-population authority and advances no watermarks.

The proposed first future production canary is limited to importing accepted Manchester14 evidence and offline screening under separate migration/population approval; no source calls, factual writes or new Applications. This is a recommendation, not execution authority. Operational restricted roles/policies, production capacity/retention, kill switch and concrete activation authority remain unaccepted.

## Test evidence and acceptance limit

Focused local JUnit evidence is inspected; parent reports 101 checks passed. Seven PostgreSQL tests are present for migration/RLS, concurrency/fencing, actual B2 readback/recovery, lost commit acknowledgement barriers, duplicate admission, shared listing/screening/B2 flow and unsupported facts. These were not executed by this reviewer. Their forthcoming disposable PostgreSQL CI results are a required acceptance dependency, especially for the actual writer and lock semantics. Superuser migration tests cannot establish future restricted operational-role access.

This PASS supports publishing the draft and running already-authorised offline/disposable checks. It is not approval for production migration, population, live council calls, deployment, activation, scheduling or Stage 4 closure. If PostgreSQL tests expose new defects, review the resulting implementation delta before final acceptance.

## Final successor delta reviewed

Compared committed successor against the prior reviewed implementation. Source validators and row projectors are now supplied explicitly through ListingContract; shared B2 handoff is supplied through FactualContract. Production application modules no longer import verification modules, and combined byte accounting is promoted to app/ingestion with compatibility import preserving old readers. This keeps the same validated implementation in tests without introducing a live adapter/registration or alternate writer. Callable injection remains within the documented trusted controller boundary; it does not qualify arbitrary adapters for production.

Global stop now also records the owned task as SAFETY_BLOCKED or PERSISTENCE_UNCERTAIN, revokes ownership and advances its fence while preserving durable intent/checkpoint evidence. Known isolated failure receipt, task deferral and council cooldown are committed atomically. Same-council source tasks cannot claim during cooldown; unrelated councils remain eligible under independent authority, except when global stop applies. The original wrong-task/source-intent bypass guards remain present.

Inspected focused tests and local JUnit: 101 tests, zero failures/errors/skips. Parent reports the first hosted disposable PostgreSQL run passed 23 tests (7 new plus 16 existing); reviewer has not independently inspected its artifact. Final candidate hosted PostgreSQL CI is still pending. No new code blocker found; acceptance remains conditional on final exact-revision CI evidence. No production authority or stage exit is implied.
