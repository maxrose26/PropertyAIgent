# Settled R2 operational run 2026-10-19 — complete audit (worker rejected after the 30-second settling period)

Run: master `9e0764205e9b553c24c509a7f1ce34897e8c9807` (tree `a208034e59bb56f29f9314d63671405f197ced99`), registration sha256 `4186c88fb6ce36c73b3eac03e6ad54d4c0f6aa6c9ca81d286789777e98261e8c`, mode `REQUIRED_CAPTURE_SCREENING_SETTLED_R2`, namespace `operational-capture-queue-settled-r2-once-20261019` (now consumed). Files are the owner's local audit byte for byte (HASHES.sha256). Chain verified: 173 events, head `cba0cdd093d0a48b499bf830c2da30915cf6b28bd50e8300b0cac4cd3a27f58f`.

## Result
`STOP_RECONCILE_NO_RETRY`, phase `RESTRICTED_CONNECTION_QUALIFICATION`, cleanup `CLOSED`, access `DISABLED_VERIFIED`.
- Preflight recognised the retained upgraded installation: policy state `SUCCESSOR_POLICY_APPLIED`, reason `POLICY_STATE_RECOGNISED` (the corrected check worked).
- Role-level timeouts were captured (both roles empty), applied (`10s`/`3s`/`20s`) and restored (`RESTORED_VERIFIED`).
- The 30-second settling period ran in full (`settling_started` → `settling_completed`, 30.007 s) with zero restricted contacts before it.
- The worker's first connection (attempt 1, verify-full, pinned pooler address, startup options passed, role-level timeouts in place) was **rejected: `AUTHENTICATION_REJECTED`**, SQLSTATE absent (connect-time server errors carry none in this driver), underlying cause undetermined. First-contact intervals: **30.104 s since activation, 31.372 s since mapping, 32.159 s since password commit.** The effect login was never attempted. No retry, no polling.

## Reconciliation
| Obligation | Evidence |
|---|---|
| Grant, authority, source | none issued (`unexpired_grants: 0`); source `NOT_STARTED`, 0 requests, 0 bytes; no capture, no publication, no screening; application writes 0 |
| Roles and sessions | both logins `NOLOGIN`, NULL password, no memberships, no sessions (0 terminations, disposition `NONE`); role configuration NULL for both |
| Secrets | environment secrets re-read after the run: `["DATABASE_URL"]` only |
| Administration | 84 commands / 6 connections (ceilings 240 / 13); all 6 opened and closed; no deadline events; teardown residuals none |
| Runtime | 1 slot, 1 connection attempt, 0 statements, 0.89 s (ceilings 1 040 / 40 / 300 s); cleanup `CLOSED`; no new owned sockets; cancellations 0 of 8 runtime and 0 of 3 administrative |
| Process | closure `CLOSED`: 0 children, 0 new sockets, 0 owned survivors, no OOM events, peak 137.2 MB; scope `not-found`/`inactive` afterwards |
| Timing | hidden input 85.9 s of 300; active 39.95 s of 480; GitHub CLI invocations 8 |
| Evidence branch | head unchanged `7368d77b4908d1676023904ed0af6f0345ce0053` (failure path publishes nothing there; this archive is the record) |
| Consumed records | runs 1 and 2 untouched; this namespace and registration consumed; no replacement run |

## What the three live runs establish about the rejection
| Run | Role options | First worker connection after fresh password | Outcome |
|---|---|---|---|
| 18 Oct matrix, entry 1 | none | interval recorded in that audit (not re-derived here) | rejected |
| 18 Oct matrix, entry 2 (later in the same run) | startup options | later than entry 1 | connected (identity statement ran; merged check recorded non-reflection) |
| 19 Oct run 1 | startup options + role-level timeouts | no delay; interval not recorded (recording was added afterwards) | rejected |
| 19 Oct R2 | startup options + role-level timeouts | **30.1 s after activation** | **rejected** |
A 30-second delay and role-level timeouts did not change the outcome for the worker's first connection. The data does not identify the cause (credential propagation beyond 30 s, per-user pooler state, or something else) and does not contradict a provider-side cause.

## Recommended alternative
Stop live experimentation and **escalate to the provider** (Supabase, existing ticket SU-511198, whose follow-up was never sent because no channel was available) with this sanitised evidence: the pooler tenant and routing form, the exact sequence (role created NOLOGIN, fresh SCRAM verifier set, LOGIN activated, first connection through the session-mode pooler rejected with no SQLSTATE), the three rejections including the 30-second one, and the one earlier success. The question for the provider is whether new-role credentials need a longer or different activation path on the pooler (for example an authentication-cache or tenant-sync interval), and what the supported way is to provision a pooler-reachable login. No further delay-based attempt is prepared.
