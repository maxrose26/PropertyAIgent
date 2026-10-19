# Corrected preflight and second settled generation — final review package (preparation only; nothing here is authorised or run)

Stage 4 remains OPEN. PR #145 (archive of the settled run that stopped in preflight) is preserved unchanged, as are PR #142, all consumed authorities and namespaces, IDs 1504–1508 and the existing stops. No credential research, storage acceptance or queue design is touched.

## 1. Candidate
| Item | Value |
|---|---|
| PR | #146 (draft), branch `stage4/preflight-policy-reuse-20261019`, based on `master` `2afee9cc7581e19f8cad7951eed6dc9b428af73b` |
| Tested code state | `30d3bc5e9cf3042eedde78b64f5e70c93de2063c`, tree `ce292ea0a032246ddafa4cec44dfd1acde273fa2` (later commits on the branch are documentation only) |
| Hosted results at exactly that head | all pass: offline (both), native, postgres-admission, restricted-provisioning (PG17, complete wrapper), web |

## 2. The correction
**Distinguishing the record from the reconciliation.** The consumed run's recorded result is preserved as written: phase `ADMIN_PREFLIGHT`, `ValueError`, reason `UNKNOWN`, cleanup `UNCERTAIN`, access `UNRECONCILED`. The attribution to a function-inventory mismatch (two bodies equal to `successor-policy.sql` instead of `worker.sql`) is a later reconciliation from the two audits and the repository, not part of that recorded result.

**What preflight now does** (`Owner.verify_installed`): it accepts exactly one of two coherent, explicitly identified installed states and nothing else:
- `ORIGINAL`: all six functions equal the reviewed `worker.sql` bodies.
- `SUCCESSOR_POLICY_APPLIED`: the original with exactly the two functions redefined by `successor-policy.sql`.
The permitted state is bound to the execution mode: a mode that applies the policy (the capture and settled modes) accepts either; a mode that does not (matrix, diagnostic) accepts only `ORIGINAL`. Functions are never judged independently, so a mixed inventory is refused even though each body is individually reviewed. Owner (`ingestion_storage_owner`) and `search_path=pg_catalog` are still required on every function; missing, extra or duplicated functions and any altered body are refused. A fixed reason code and the recognised policy state are exported (`POLICY_STATE_RECOGNISED`, `INSTALLED_POLICY_STATE_MIXED`, `INSTALLED_POLICY_STATE_NOT_PERMITTED_FOR_MODE`, `INSTALLED_FUNCTION_CONTENT_CHANGED`, `INSTALLED_FUNCTION_OWNER_OR_CONFIG_CHANGED`) in the audit event, the administration accounting and the failure result (`preflight`); exception text and credentials stay private.

**Disclosed, not changed:** the inventory query still matches by function name and compares body, owner and search path, as before; it does not compare `prosecdef`, volatility, language, argument types or ACLs. That gap pre-dates this change; enforcing attributes never observed on the production database could itself stop a run, so it is left for a separate review.

## 3. Lifecycle regression (disposable PG17, real installation path)
`policy_lifecycle`: original installed state → preflight (`ORIGINAL`) → the real reuse-mode installation applies the successor policy → credentials mapped, activated and torn down with verified cleanup → a **fresh** controller → (a) the predecessor's verification logic, run against that retained state, fails with `INSTALLED_FUNCTION_CONTENT_CHANGED` exactly as in the live run; (b) the corrected logic passes (`SUCCESSOR_POLICY_APPLIED`), repeatedly (the already-upgraded start); (c) a mode that does not apply the policy refuses it; (d) a mixed inventory is refused and then repaired through the real policy path; (e) an altered body and an altered search path are refused. Plus 11 unit tests of the decision logic (both states, both modes, mixed in both directions, every function altered, owner/config variants, missing/extra/duplicated rows, fixed-code-only export).

## 4. Full successor wrapper against the retained state
The three settled scenarios were rehearsed twice, from a fresh installation and from the retained upgraded installation (the state the consumed runs left): success (capture, queued screening of 60 rows, teardown), first restricted connection rejected, and owner STOP during the settling period. All passed.
| Scenario | Fresh install | Retained state |
|---|---|---|
| Success: admin commands / connections | 136 / 7 | 114 / 7 |
| First connection rejected: commands / connections | 106 / 6 | 84 / 6 |
| STOP during settling: commands / connections | 106 / 6 | 84 / 6 |
Each asserts (as applicable): worker once, effect never attempted on rejection; no restricted contact before the end of the interval; first-contact intervals recorded; role settings restored to NULL; session disposition clean; secrets removed (only `DATABASE_URL`); roles `NOLOGIN` with NULL password; administrative, runtime and process closure `CLOSED` reported separately. The settling period remains the single fixed 30 seconds (the rehearsal substitutes 0.6 s only to keep CI short; the constant is asserted separately).

## 5. Independent review
Two reviews cover this work: the first settled-generation review and its re-review (earlier), and a review of this correction. Dispositions: duplicated/missing-row `KeyError` (fixed, fixed reason code, test); renderer expiry margin (cap 110 minutes); evidence-file trap order (fixed); attribute-comparison gap (disclosed above); `preflight` field present only in the Runner failure result (documented; consumers must tolerate absence); `legacy_verify` in the test is a copy of the predecessor logic from master `336cd939` rather than the live code (so it cannot drift silently, but it is a copy).

## 6. Proposed successor binding (one grouped decision; not released)
| Field | Value |
|---|---|
| Integration order | PR #145 (documentation), then PR #146 — guarded `[skip render]` commits, combined-tree and executable-hash reconciliation, required checks on the combined tree and on `master` |
| Mode | `REQUIRED_CAPTURE_SCREENING_SETTLED_R2` |
| Authority | `AUTHORISE_BOLTON_CAPTURE_QUEUE_SETTLED_R2_ONCE_20261019` (unused; grant names derive `_CAPTURE` / `_SCREEN`) |
| Namespace | `operational-capture-queue-settled-r2-once-20261019` (absent) |
| Registration | one fresh file `~/stage4-owner/operational-settled-r2-registration-20261019.json`, rendered from the integrated revision, expiry ≤ 110 minutes, current evidence-branch head re-read at render and again by the owner script |
| Predecessors bound by hash | run 1: registration `1034c92e…`, events `2af82ca9…`, result `ffedfe33…`; run 2: registration `fa3a94c8…`, events `c4dc1277…`, result `8116e066…` |
| Behaviour | the existing corrected preflight; role-level timeouts (captured, applied, restored); one fixed 30-second settling period; worker qualified once then effect once, any failure stops and tears down; if both qualify, the single Bolton observation and source-free queued screening in the same lifecycle; teardown |
| Unchanged limits | hidden input 300 s; active window 480 s; job 450 s; `RuntimeMaxSec` 810 s; administration ≤ 240 commands / 13 connections; runtime ≤ 1,040 statements / 40 connections / 300 s; cancellations ≤ 8 runtime + 3 administrative, 2 s each; source one observation (≤ 10 transport requests, ≤ 3,000,000 received-body bytes, ≤ 6 pages, ≤ 60 rows), screening 0 source requests; memory, returned-data and evidence limits unchanged |
| Risk and exception | the previously reviewed temporary-credential (possible SCRAM verifier retention) acceptance and the single-use Bolton exception, re-bound to this run only, under the unchanged global and manual stops |
| Owner terminal | none until a release; then the same two-step shape, with the launch refused on any unreadable scope state |
If the worker's first connection is rejected again after the interval, the run stops and tears down; the earlier instruction to stop this line of experimentation and return the evidence for provider escalation applies.
