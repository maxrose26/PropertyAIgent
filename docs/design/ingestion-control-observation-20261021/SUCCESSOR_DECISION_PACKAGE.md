# Observation successor with hidden-input pre-check — candidate and decision package (offline; nothing here is authorised or run)

Stage 4 remains OPEN. No merge, registration, live observation, policy installation, stop change, council request, dispatch or credential change has been made. Generation 2 and `IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE`, IDs 1504–1508, standing credentials and consumed authorities are untouched. The historical Bolton cause remains UNDETERMINED (an IP block is neither established nor excluded). The precise cause of the first observation's input rejection is **unobserved** and is not attributed to anyone or anything.

## 1. Candidate
| Item | Value |
|---|---|
| PR | #156 (draft) → `master` `64fa32b67b4aa095d50d2cea01c37339ba0e58d7` |
| Tested code | commit `68380bd6784c2c12ca5b3e62984e2122087e1e47`, tree `cd0c37a5b41429848c9ed25d886942f3df5dc4e7` (this package is a later documentation-only commit) |
| CI at the tested code | all pass: discovery contract (including the 18-test PostgreSQL step), reusable-batch guard, hosted memory proof, web |
| Local | 38 pre-check/observation tests pass; the whole ingestion suite is 697 passed with only the 10 known environment-only failures (no local PostgreSQL) |
| Review | independent read-only review of the changed boundary: no HIGH or MEDIUM; the LOW points were addressed with tests and specification notes (below) |

## 2. What changed (and what did not)
**Changed — only two things.**
1. **Fresh successor names, consumed attempt preserved.** Authority `AUTHORISE_INGESTION_CONTROL_OBSERVATION_SUCCESSOR_2_ONCE_20261021`, namespace `operational-control-observation-successor-2-once-20261021`, owner script and registration file names. The consumed first attempt (authority, namespace, registration `da5dce7f…99f`, `events.jsonl` `84213920…1a4`, `final-result.json` `7505156e…fb27`) is bound by hash in the successor's registration and re-checked by the owner script; it is never reused or modified.
2. **A hidden-input pre-check before the registration is consumed.** The one bounded visible hidden prompt (120 s) is validated with the **existing route validator** (complete route: driver, host, port, database, username, no query) and for password presence **before** the journal or namespace exists. An invalid or unreadable value exits with a fixed, secret-free code (`INPUT_REJECTED_NOT_CONSUMED:ROUTE_<code>`, `…:PASSWORD_ABSENT`, `INPUT_NOT_READ_NOT_CONSUMED`), creates no state, and leaves the registration usable for a second start (until it expires). A valid value stays in memory only, is handed **once** (a one-shot reader) to the unchanged session, and is never asked for again. The core-dump limit is set to zero, and the memory scope exists, before the prompt. The pre-check is observer-only; every other mode consumes first and prompts inside the session exactly as before (tested).

**Unchanged:** the observation's SQL (6 statements), the transaction-local `GRANT … WITH INHERIT TRUE, SET TRUE` inside a rolled-back transaction with no `COMMIT`, both capability-absence readbacks, privileges, and every number: 1 connection, 12 statements, 20 database-active seconds, 30 supervised-active seconds after the hidden input, registration ≤ 30 minutes, zero GitHub and source requests. No registration handling was redesigned and no authentication setup was added.

## 3. Validation (offline and disposable)
* **Malformed-input refusal:** empty, non-URL, oversize, wrong host, port, database or username, query parameters, password-less, unreadable prompt, and a prompt that outlasts its bound — each exits with its fixed code, never echoes the value, and disarms the timer.
* **Non-consumption:** `main()` with a refused value creates no namespace and no journal; the registration remains usable and the second start (with a valid value) consumes it, and only then.
* **Valid-input handoff:** the value reaches the session exactly once and is then forgotten; the prompt is called exactly once; the real `session()` accepts the one-shot reader.
* **Secret-safe output:** the value is in no argument, environment variable, file, audit event or output (asserted across every file under the test home and all captured output); the audit records only booleans and the prompt duration.
* **Ordering:** memory scope → zero core limit → single prompt (asserted).
* **Other modes unchanged:** the pipeline mode still consumes before prompting and has no pre-check event (tested).
Disclosed limits: the prompt is exercised through injected readers, not a real terminal; an owner-script run is verified by string and syntax checks, not executed; the PostgreSQL evidence for the observation itself (catalog unchanged after normal, failure, disconnect and failed-readback runs) is unchanged and was recorded on the previous candidate (still part of this CI).

## 4. Accounting notes
The prompt duration is recorded in `hidden_input_prechecked.seconds`; the session, given an immediate reader, records about zero input time, so read the input duration from that event. The worst case from scope start is about 155 s (120 s prompt + 30 s active + 2 s reporting + margin), inside the 240-second scope limit. A refusal exits with code 1 and the fixed code on standard error; a run that started and failed also exits 1, so the two are told apart by the code text and by the absent namespace.

## 5. Grouped proposal (nothing starts without your decision)
**One decision:** approve (a) guarded, head-locked `[skip render]` integration of PR #156 at its final head (a documentation-only delta over `68380bd6`); (b) one fresh successor registration (≤ 30 minutes, bound to the integrated revision and tree, new namespace); (c) one owner command in your visible terminal — you are asked **once**, and if the value is refused nothing is consumed and the same command can be run again until the registration expires. The previously approved exception (the transaction-local `GRANT`, rolled back, no `COMMIT`) and limits carry over unchanged.
**After the ceremony** I reconcile the audit (including the rollback and both capability-absence readbacks, or UNVERIFIED where unavailable — no inference about pooler-side closure, no automatic retry), then continue the already-authorised offline preparation of one combined policy-and-diagnostic proposal from the observed stop state.
**Not authorised by this package:** policy installation, stop change, council request, probe dispatch, credential change or Stage advancement.
