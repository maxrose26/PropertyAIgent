# Settled first-connection successor — candidate and production decision package (preparation only; nothing here is authorised or run)

Stage 4 remains OPEN. PR #142 (archive of the consumed 2026-10-19 run) is accepted as reconciled; its registration, namespace, authority and complete audits are preserved and are bound by hash into the successor.

## 1. Candidate
| Item | Value |
|---|---|
| PR | #143 (draft), branch `stage4/settled-first-connection-20261019`, based on `master` `336cd939afed1e3ae55b2f451a7f7b2232d19c8b` |
| Tested code state | `3a1c787035161e887f70674bfcb9ccd80e72d11c`, tree `53c2da6c720b66cf8c579f513a900ac2439fc7b0` (later commits on the branch are documentation only) |
| Hosted checks at the code state | all pass: offline, native, postgres-admission, restricted-provisioning (PG17 rehearsals of the complete wrapper), web |
| Mode / authority / namespace | `REQUIRED_CAPTURE_SCREENING_SETTLED` / `AUTHORISE_BOLTON_CAPTURE_QUEUE_SETTLED_ONCE_20261019` / `operational-capture-queue-settled-once-20261019` (absent) |
| Predecessor (bound by hash, never reused) | registration `1034c92e…`, `events.jsonl` `2af82ca9…`, `final-result.json` `ffedfe33…` |

## 2. What changed (and what did not)
Executable change, confined to the existing controller:
1. `Runner.settle()`: one fixed **30-second** period after BOTH passwords and the activation are committed and before either restricted login is first contacted. It opens no connection, touches no database object and polls nothing. It is sliced into one-second steps, each checked against the registration expiry, the job and administrative deadlines and the owner STOP file. The interval is an experiment, not a provider guarantee.
2. Non-secret first-contact intervals: at each role's first connection attempt, the audit records seconds since password commit, since mapping and since activation (`runtime_connection_intent`, `first_contact: true`); the final accounting exports `first_connection_intervals`. A failed first connection is still recorded.
3. A new mode, authority and namespace (the consumed ones are neither reused nor modified), and a `validate_registration` binding for the settled mode (`settling_seconds` = 30, the predecessor hashes, the namespace, a two-hour expiry ceiling).

Not changed: qualification gate (identity, flags, effective timeouts `('10s','3s','20s')`, client deadline), role-level settings, stops, Bolton exception, teardown, ceilings, TLS, privileges. No matrix, no waiting for support.

Qualification stays strictly sequential and singular: the worker is attempted once; only if it succeeds is the effect login attempted once. The pool has one slot, no overflow, no pre-ping and no retry; any authentication failure stops the run, tears down and reports. If both qualify, the single Bolton capture and queued screening proceed in the same lifecycle.

## 3. Offline verification
- **No contact before the interval ends.** The only code path that connects as a restricted login is the runtime connection factory, first reached by the qualification slot. Hosted rehearsal (`settled_success`) records every connection made in the process and asserts that no `ingestion_*_login` connection precedes the end of the interval; an AST test asserts the order `map_and_activate` < `settle` < first `slot` < `register` in `setup()`.
- **One password, never exposed.** The mapped secret value, captured at the real mapping call, equals the URL used for qualification, and the password appears neither in the audit nor in the result.
- **Failure rehearsals** (hosted PG17): first connection rejected (`settled_first_connection_rejected`: exactly one restricted contact, the effect login never attempted, access disabled, role settings restored); owner STOP during the interval (`settled_stop_during_interval`: no restricted contact at all, no grant, secrets removed, closure CLOSED).
- **Interval recording**: first-contact intervals present for both roles on success, for the worker on rejection; worker ≥ 0.6 s in rehearsal (production constant asserted separately as 30).
- **Administrative load unchanged**: complete success 136 commands / 7 connections (as before; the settling period adds none).

## 4. Independent review
One focused review of the diff. Findings and dispositions:
- **STOP file not observed during the interval** (the review assumed the runner's check covered it; it does not). Fixed: the interval checks the STOP file at every step; unit test and hosted rehearsal added.
- **Hard-coded earlier authority in the consumed cleanup tool**: that tool names one earlier grant and would not cover the settled grants. It is single-use consumed code and is deliberately not modified. For the settled run, invalidation of grants on failure is `invalidate_failure` plus teardown (rehearsed); a failure that leaves a grant unexpired would need its own revoke-only tool, prepared only if that occurs. Disclosed here and pinned by a test.
- Test gaps (call order, stop path, predecessor registration hash, scope presence, temporary file cleanup): addressed.

## 5. Timing and budgets (no amendment needed)
The 30 s is inside the administrative phase (`admin_pre` 210 s) and the job limit. With a generous 60 s for the whole pre-capture lifecycle (observed: 8 s to the stop in the consumed run) the job retains ≥ 300 s for capture and screening (450 − 30 − 60 = 360; the source observation itself is capped at 45 s). The interval counts against the administrative phase seconds, so teardown has 30 s less administrative slack than before; the failure-window arithmetic (24.0 s of 25 s), job 450 s, diagnostic total 475 s and the 480 s backstop are unchanged. Hidden input 300 s and active execution 480 s remain the session caps; `RuntimeMaxSec` stays 810 s (session outer ceiling 790 s). All other ceilings unchanged: administration 240 commands / 13 connections; runtime 1,040 statements / 40 connections / 300 s; cancellations 8 runtime + 3 administrative, 2 s each; source one observation (≤ 10 transport requests, ≤ 3,000,000 received-body bytes, ≤ 6 pages, ≤ 60 rows), screening 0 source requests.

## 6. Production decision requested (one grouped decision; none of it is released by this document)
1. Integrate in this order, with guarded `[skip render]` commits and the same reconciliation as before (combined tree, executable file hashes, required checks): PR #142 (documentation), then PR #143.
2. Release ONE fresh registration for the settled mode, rendered from the integrated revision with the current evidence-branch head (read and re-verified at render and again by the owner script), expiring within two hours.
3. Accept the possible-SCRAM-verifier-retention risk for this run only, and the exact single-use Bolton exception as already specified, under the unchanged global and manual stops (Salford's original stop and all other holds preserved).
4. The owner runs it with the same two-step command shape (private-keyring session, then `owner-run.sh`), hidden input only in the owner's visible terminal.

If the worker's first connection is rejected again after the interval, the run stops and tears down; there is no automatic follow-up, and any further step needs a new decision.
