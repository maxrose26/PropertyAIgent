# Settled operational acceptance run — release package (one run, owner-local; prepared, not released)

Successor of the consumed 2026-10-19 run (audit archived in PR #142; its registration `1034c92e…`, `events.jsonl` `2af82ca9…`, `final-result.json` `ffedfe33…` are bound by hash and never reused). That run stopped at restricted-connection qualification: the worker's first connection was rejected (`AUTHENTICATION_REJECTED`, cause undetermined) with no grant, no source request, and a clean teardown.

Aim: test whether letting the credentials settle enables the existing operational run. The interval is an **experiment, not a provider guarantee**. This package authorises nothing until the Product Owner releases it.

## The only behavioural change
One fixed **30-second settling period** after BOTH passwords and the activation are committed and BEFORE either restricted account is first contacted (`Runner.settle`). It touches no database object, opens no connection and polls nothing; it is sliced into one-second steps, each checked against the stop file, the registration expiry and the job/administrative deadlines. Everything else is the existing controller: same lifecycle, same role-level timeouts (captured, applied, restored), same qualification gate (identity, flags, effective timeouts, client deadline), same stops.

## Sequence and stops
1. Preflight; reuse accepted installation; capture and apply the three role-level timeouts; fresh passwords with `VALID UNTIL`; protected secrets; activation (all committed).
2. **Settle 30 s** (audit events `settling_started` / `settling_completed`).
3. Worker qualification **once**; if it succeeds, effect qualification **once**. Any authentication failure stops and tears down: no polling, no retry, no fallback, no second attempt on either login.
4. Only if both qualify: the single Bolton capture authority and exception, one source observation, retention, queued screening (no further source requests).
5. Teardown: invalidate grants, disable both logins, session policy, delete the temporary secrets, restore role settings, closure checks.

## Recorded intervals (non-secret)
At each role's first connection attempt the audit records `since_password_commit_seconds`, `since_mapping_seconds` and `since_activation_seconds` (event `runtime_connection_intent` with `first_contact: true`) and the final accounting exports them as `first_connection_intervals`. A first connection that fails is still recorded.

## Credential discipline (verified offline)
The password is generated once, hashed into a SCRAM verifier for the database, rendered into the connection URL, mapped to the protected secret and held in memory for qualification: the mapped value equals the URL used to qualify (asserted against the real mapping call), and the password never appears in the audit or result. No administrative step contacts either role before the interval ends (the administrative connector uses the migration identity only; a connection recorder in the rehearsal asserts that no `ingestion_*_login` connection precedes the end of the settling period).

## Budgets and timing (unchanged ceilings)
Administration ≤ 240 commands / 13 connections; runtime ≤ 1,040 statements / 40 connections / 300 s; cancellations ≤ 8 runtime + 3 administrative, 2 s each; source one observation, ≤ 10 transport requests, ≤ 3,000,000 received-body bytes, ≤ 6 pages, ≤ 60 rows, screening 0 source requests. Hidden input 300 s; active window 480 s; job 450 s; failure window 25 s; `RuntimeMaxSec` 810 s (session outer ceiling 790 s). The interval is inside the administrative phase allowance (`admin_pre` 210 s) and the job limit: 30 s plus an allowance of 60 s for the whole lifecycle leaves ≥ 300 s of the job for capture and screening, and no timing amendment is needed.

## Namespace and authority
Mode `REQUIRED_CAPTURE_SCREENING_SETTLED`; authority `AUTHORISE_BOLTON_CAPTURE_QUEUE_SETTLED_ONCE_20261019`; state directory `operational-capture-queue-settled-once-20261019` (absent); registration file `~/stage4-owner/operational-settled-registration-20261019.json`. No consumed authority or namespace is reused or modified.

## Not authorised
Application/B2 writes, unit facts, scheduling, deployment, Stage 4 advancement, a matrix, any privilege or TLS change, any retry.
