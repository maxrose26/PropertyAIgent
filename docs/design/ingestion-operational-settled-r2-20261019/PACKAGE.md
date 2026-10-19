# Settled operational acceptance run, second generation — release package (one run, owner-local; prepared, not released)

Successor of the two consumed 2026-10-19 runs, both preserved and bound by hash:
- run 1 (`operational-capture-queue-successor-once-20261018`, audit PR #142): stopped at restricted-connection qualification, worker `AUTHENTICATION_REJECTED`, cause undetermined.
- run 2 (`operational-capture-queue-settled-once-20261019`, audit PR #145): stopped in `ADMIN_PREFLIGHT` before any settling or restricted contact: reuse-mode preflight accepted only the pre-policy function inventory, which run 1's own reviewed policy application had changed. Not an authentication failure.

This package authorises nothing until the Product Owner releases it.

## Changes since the first settled generation
1. **Preflight recognises two coherent, explicitly identified installed states** (`Owner.verify_installed`): `ORIGINAL` (the reviewed `worker.sql` inventory) and `SUCCESSOR_POLICY_APPLIED` (the original with exactly the two functions redefined by `successor-policy.sql`). The permitted state is bound to the execution mode: a mode that applies the policy accepts either; a mode that does not accepts only `ORIGINAL`. Each function is never judged independently: a mixed inventory, an altered body, a missing or extra function, a wrong owner or a wrong search path is refused. Fixed reason codes and the recognised policy state are exported (`POLICY_STATE_RECOGNISED`, `INSTALLED_POLICY_STATE_MIXED`, `INSTALLED_POLICY_STATE_NOT_PERMITTED_FOR_MODE`, `INSTALLED_FUNCTION_CONTENT_CHANGED`, `INSTALLED_FUNCTION_OWNER_OR_CONFIG_CHANGED`); exception text stays private.
2. New mode `REQUIRED_CAPTURE_SCREENING_SETTLED_R2`, authority `AUTHORISE_BOLTON_CAPTURE_QUEUE_SETTLED_R2_ONCE_20261019`, namespace `operational-capture-queue-settled-r2-once-20261019` (absent), registration file `~/stage4-owner/operational-settled-r2-registration-20261019.json`. The registration binds both predecessors' registration and audit hashes.
3. The owner script now treats an unreadable or timed-out scope answer as UNKNOWN and refuses to launch (it is no longer fail-open), re-checks both predecessors' audits and registrations, and cleans its temporary file by trap.

Unchanged: the one fixed 30-second settling period (an experiment, not a provider guarantee), first-contact interval recording, worker-once-then-effect-once with no polling or retry, role-level timeouts (captured, applied, restored), the qualification gate, stops, the single-use Bolton exception, teardown, TLS, privileges and every ceiling (hidden input 300 s, active 480 s, `RuntimeMaxSec` 810 s; administration 240 commands / 13 connections; runtime 1,040 statements / 40 connections / 300 s; cancellations 8 runtime + 3 administrative, 2 s each; source one observation ≤ 10 transport requests / 3,000,000 received-body bytes / 6 pages / 60 rows, screening 0 source requests).

## Not authorised
Application/B2 writes, unit facts, scheduling, deployment, Stage 4 advancement, a matrix, any privilege or TLS change, any retry.
