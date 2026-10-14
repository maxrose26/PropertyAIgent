# TO REVIEW — ROUTE COMPATIBILITY CORRECTION AND CONNECTION-FREE PREFLIGHT PROPOSAL

Master Stage 4 remains OPEN. Current gate: committee-discovered application admission. Next: REVIEW of the corrected adapter and actual route qualification before any new production admission.

## Decision-ready result

GO — bounded offline correction and validation complete.

Actual-secret route qualification: NOT_PERFORMED.
Authentication/connectivity: NOT_TESTED.
Production re-execution: NOT_AUTHORISED.

Failed run38655110927 remains consumed. Its three candidates were not attempted and its transaction state remains NOT_STARTED — CERTAIN. Nothing in this work changes those historical results or proves which raw-URL requirement failed.

## Exact candidate and diff

Integrated base/current master: `e1e98704913b572e46822f1fbe2b5a273f47bbd9`.
Base tree: `59a29bc05b99b80105f8a6ca9580e7952aef4259`.
Failure-analysis baseline: `b757852276f7f303d392792b1887371a108f5e09`.

PR #88: https://github.com/maxrose26/PropertyAIgent/pull/88 — draft, unmerged.
Branch: stage4/route-compatibility-preflight-proposal.
Final head: `30ea36b5af266dc770609c58f183c037209f2e35`.
Final tree: `905b1e3e09d8372edec14da7cf4ca9ed986e0278`.
Diff: https://github.com/maxrose26/PropertyAIgent/pull/88/files . Nine changed paths, 328 additions / 8 deletions. Published file blobs matched the reviewed local files.

Changed paths:
- verification/discovery/route_validation.py — pure exact-route validator and safe audit.
- verification/discovery/committee_exact.py — checked_engine invokes the same validator before unchanged engine construction.
- verification/discovery/material_admission.py — truthful failure phases and suppressed exception/cleanup chains.
- verification/discovery/route_preflight.py — connection-free entry, without admission/source paths.
- verification/ah-offline-route-preflight.py — existing seccomp network-denial pattern, before application imports.
- verification/discovery/proposals/stage4-route-preflight-once.yml.txt — unregistered workflow template.
- verification/discovery/proposals/ROUTE-PREFLIGHT-REVIEW.md — proposal boundaries.
- tests/test_discovery_route_validation.py — focused synthetic regression coverage.
- .github/workflows/stage4-discovery-offline.yml — adds those tests to existing offline CI.

Master was re-fetched and remains unchanged. Historical workflow identities and consumed manifests were not modified. Frozen three-record manifest still hashes to `91be2de17f9e7fd0f4e62c7e95b611ef91bb1484673191f489f928b9879e5981`.

## Implementation and preserved policy

The validator reuses the existing pure `app.db.session._normalize_database_url` function. Plain postgresql:// and legacy postgres:// receive the established native-psycopg normalization. An omitted port receives the accepted effective port5432 interpretation.

The exact approved driver, host, project username, database, effective port and prohibition on query parameters remain intact. No alternative destination, SQLite fallback or different database user is admitted. The engine's TLS, connect/statement/lock/idle-transaction timeouts and pool limits are unchanged.

Both checked_engine and the proposed preflight invoke the same pure validator. The validator does not construct an engine or connect. It returns a private URL only to the engine caller; audit never serializes that URL.

Public rejection codes are limited to DRIVER_MISMATCH, HOST_MISMATCH, PORT_MISMATCH, DATABASE_MISMATCH, USERNAME_MISMATCH, QUERY_FORBIDDEN and fixed MALFORMED_INPUT. Parser exceptions and later secret-bearing exception chains are suppressed. No URL components, credentials, query contents or raw parser exceptions are emitted.

Audit phases distinguish REJECTED_BEFORE_ENGINE_CREATION from ENGINE_CONSTRUCTION_STARTED, ADMISSION_EXECUTION_STARTED and EXECUTION_COMPLETED. Preconnection rejection is explicitly NO_TRANSACTION; later failures do not receive false zero-write or transaction-certainty claims. Existing per-record transaction results remain authoritative. Cleanup errors use fixed messages and preserve the bounded audit.

Safe booleans driver_normalization_applied and default_port_applied can explain transformations required by a future compatible input. They do not establish that the historical secret was identical or that normalization caused run38655110927.

## Tests and independent review

41 focused offline tests passed, with networking denied. Coverage includes accepted equivalent forms, wrong driver/host/user/database/port/query, malformed inputs, privacy of exception output, zero factory/execution calls on rejection, later failure phases, safe output, single-use template controls and the actual synthetic subprocess/seccomp entrypoint.

Six exact-final-head hosted checks passed, zero failures/skips/pending. The existing disposable PostgreSQL job passed all four tests, including shared admission/B2, canonical date/readback, concurrency/duplicate protection and lost acknowledgement. These database connections were disposable CI only, not production.

Independent review approved the offline correction/unregistered proposal after the safe transformation flags and subprocess smoke test were added. No further concrete blocker was found. This review does not authorise registration, actual-secret execution or production admission.

## Concrete preflight proposal — NOT REGISTERED

Template path: `verification/discovery/proposals/stage4-route-preflight-once.yml.txt`.
Template blob: `3043a10f355990667d04b6d3a384e9fdfc9955e5`.
Template SHA256: `6dec41cf87be81c3f48127d854216b1f140eb0f4047db993aef511d6fac2ed65`.

Proposed future registration path: `.github/workflows/stage4-route-preflight-once.yml` — absent from the candidate tree.
Proposed authority: AUTHORISE_CONNECTION_FREE_ROUTE_PREFLIGHT_ONCE — no execution authorised now.

Controls: manual dispatch only; exact reviewed integrated SHA must equal checkout, workflow SHA and GITHUB_SHA; master-bound; hosted runner; run1/attempt1; no arbitrary URL/reference input; contents-read permission; existing production concurrency lock; five-minute outer deadline; fixed safe artifact.

The existing stage4-production-canary environment and DATABASE_URL secret remain in place. Only the validator step receives it through an explicit env-i environment. No secret transfer, replacement or new credential. Setup/artifact steps have no explicit production-secret binding. The entry removes the secret from its process environment when evaluated and never writes it to audit.

OS network syscalls are denied BEFORE application imports. The callable entry has no engine/source/admission/B2 path. No browser installation or source request. A compatible result states route compatibility only; authentication and connectivity remain NOT_TESTED. A rejected result yields only the fixed safe audit/code.

A future registration changes the workflow-state assertion and integrated SHA, so the registered candidate must be separately reconciled/tested. Current CI does not prove a future registration or actual-secret result.

## Residual uncertainty and precise REVIEW decision

The actual failed route requirement remains UNKNOWN. Current actual-secret compatibility, database authentication and connectivity are not qualified by synthetic tests or disposable PostgreSQL CI.

Requested decision: review this exact candidate and, if accepted, authorise its guarded integration and separately reviewed registration/execution of exactly one connection-free preflight. Do not approve another production admission yet. No copy into .github/workflows or dispatch will occur without that decision.

After any authorised preflight, reconcile compatibility/rejection and safe transformation flags without widening the route or replacing secrets. Any further production execution still requires new exact REVIEW authority. No rerun or resume of the consumed admission is permitted.

Zero production credentials accessed, production connections/reads/writes, source retrievals or admissions occurred in this work. No evidence/B2/persistence policy change, sites/opportunities, models, scheduling, Render deployment, prospective acceptance or Stage5+ work. Stockport/Trafford/withheld-source positions remain preserved. Master Stage4 remains OPEN.
