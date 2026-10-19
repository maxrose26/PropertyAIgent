# Operational acceptance run 2026-10-19 — complete audit (stopped at qualification; no grant, no source observation)

Run: master `336cd939afed1e3ae55b2f451a7f7b2232d19c8b` (tree `0eb145d19d3616ea2fce4086ae9c1cfab3cb5162`), registration sha256 `1034c92ee3e654bc4ccf1f37b6c5e20d0b15d1cce3f3982a3dfbdae2a402455c`, namespace `operational-capture-queue-successor-once-20261018`. Files here are the owner's local audit, byte for byte (hashes in HASHES.sha256). Hash chain verified: 171 events, head `ca329c80b5baef49a1f6b416764fd1b6625f11c2da7777f5fa8a1cb9760f38a4`.

## Result
`STOP_RECONCILE_NO_RETRY`, cleanup `CLOSED`, access `DISABLED_VERIFIED`, phase `RESTRICTED_CONNECTION_QUALIFICATION`.
The first runtime connection (worker, verify-full, pinned pooler address, startup options passed, role-level timeouts already applied) was rejected: `AUTHENTICATION_REJECTED`, SQLSTATE absent (connect-time server errors carry none in this driver), underlying cause UNDETERMINED. Qualification therefore never reached the identity/flags/timeouts comparison: **whether the role-level timeouts are reflected through the pooler remains unobserved.** The effect login was never attempted.

## Reconciliation against the approved run
| Obligation | Evidence |
|---|---|
| Qualification before any grant | Failed on attempt 1 of the worker; no registration, no grant (`owner_registration_committed` absent; control `unexpired_grants: 0`; authority invalidation `NOT_REQUIRED_NO_AUTHORITY`) |
| Source | 0 requests, 0 bytes, status `NOT_STARTED`, no capture retained; screening not exercised; application writes 0 |
| Role settings | Captured (both roles empty), applied (`10s`/`3s`/`20s`, verified), restored `RESTORED_VERIFIED`; final `rolconfig` NULL for both |
| Credentials | Both logins `NOLOGIN`, NULL password, no memberships, no sessions (session disposition `NONE`, 0 terminations); both temporary secrets absent, `DATABASE_URL` present; independently re-read after the run: environment secrets = `["DATABASE_URL"]` |
| Administration | 84 commands / 6 connections (ceilings 240 / 13), all 6 closed, no administrative deadline events |
| Runtime | 1 connection attempt, 0 statements, 0.71 s (ceilings 1 040 / 40 / 300 s), closed; cancellations 0 of 8 runtime, 0 of 3 administrative |
| Process | closure `CLOSED`, 0 children, 0 new sockets, memory groups removed, no OOM events (peak 76.9 MB); active 7.66 s, hidden input 8.87 s; GitHub CLI invocations 8 |
| Evidence branch | head unchanged `7368d77b4908d1676023904ed0af6f0345ce0053`; the failure path publishes nothing there, so this archive is the evidence of record |
| Single use | Namespace consumed; no retry |

## What is and is not established
- Established: the lifecycle, role-level configuration, restoration, teardown and closure all behave as designed under a real failure.
- Not established: the cause of the rejection. This is the second live rejection of the worker's first connection (the 18 October matrix entry 1 without options, now with options and role settings). In both cases it was the first connection after a fresh password; in the matrix a later entry connected. That pattern is consistent with provider-side propagation delay of new credentials but does not prove it (elapsed times are not compared here).
