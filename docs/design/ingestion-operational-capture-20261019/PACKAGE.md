# Operational acceptance run — release package (one run, owner-local)

Approved by the Product Owner on PR #139 (package commit `0425e7af23255ae1aa757f4313cf7484349ea4b7`, tested code state `50c9f7063a61aac341cee47e57455b0537fea987`, tree `52b9f4a2e0c095e2c1e38aa6aaa40f319667e52d`). Integrated into `master` as guarded `[skip render]` commits; the non-documentation file set of the integrated tree is identical to the tested code state. This package adds only the registration renderer, owner script and manifest. It contains no executable change to the pipeline, storage controller or runner.

Aim: one Bolton listing capture (RECEIVED, 16 October 2026), durable retention, and queued screening through the restricted production pipeline. Storage remains accepted. Stage 4 remains OPEN pending the result.

## What the run does (single credential lifecycle)
1. Preflight (read-only): migration identity flags, ownership/grant options, exact stops (consumed Salford global stop, manual `STORAGE_TEST_STOP`, hard-stop generation 1, control digest `0d829597…`), both logins `NOLOGIN` with NULL password, no memberships, no sessions, accepted function inventory.
2. Reuse the accepted installation (successor policy + the two reviewed capability memberships). No new account, no privilege grant.
3. Capture the existing role configuration of the two restricted logins; set only `statement_timeout='10s'`, `lock_timeout='3s'`, `idle_in_transaction_session_timeout='20s'` on those two roles (one transaction, read back).
4. Fresh temporary passwords with `VALID UNTIL`, protected environment secrets, activation.
5. **Qualification before any grant**: both identities connect through the actual runtime factory with exact identity, flags and the effective timeouts `('10s','3s','20s')`, under the client deadline. Failure ends the run and tears down.
6. Register one single-use Bolton capture authority and its exception (one source observation) under the unchanged global and manual stops.
7. Capture (one observation), durable retention, batched queued screening (zero further source requests).
8. Teardown: invalidate grants, disable both logins, session policy, delete the temporary secrets, restore the captured role configuration, closure checks. Evidence is published to the evidence branch.

## Ceilings (unchanged from the approved package)
| Resource | Ceiling |
|---|---|
| Source | one observation; ≤ 10 transport requests, ≤ 3,000,000 received-body bytes, ≤ 6 pages, ≤ 60 rows; screening uses 0 source requests |
| Runtime | ≤ 1,040 statements, ≤ 40 connections, ≤ 300 s |
| Administration | ≤ 240 commands, ≤ 13 connections |
| Cancellation | ≤ 8 runtime + ≤ 3 administrative cancellation connections, each bounded to 2 s |
| Timing | hidden input 300 s; active window 480 s; job 450 s; failure window 25 s; process backstop (`RuntimeMaxSec`) 810 s, which is the session's own outer ceiling of 790 s plus margin |
| Memory | cgroup scope `propertyaigent-operational-once.scope`, 1.5 GiB, no swap |

## Outcomes
Compounded failures can leave cleanup incomplete; any such outcome is `UNCERTAIN`, blocks continuation and needs reconciliation. There is no retry, no second observation and no matrix replay. The owner script refuses to start unless the evidence branch head still equals the registration's `evidence_head` (a moved head would otherwise be found only after the single source observation).

## Not authorised
Application/B2 writes, unit facts, scheduling, deployment, Stage 4 advancement, any further credential lifecycle or source observation.
