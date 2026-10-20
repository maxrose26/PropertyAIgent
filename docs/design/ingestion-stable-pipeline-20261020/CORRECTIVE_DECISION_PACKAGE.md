# Corrective candidate and decision package — run 39388007668 (offline; nothing here is authorised or run)

Stage 4 remains OPEN. No merge, replacement registration, dispatch, council request, credential change or production connection is authorised or has been made by this candidate. All earlier stops, IDs 1504–1508, consumed authorities, the first run's evidence and historical uncertainty are preserved.

## 1. Combined diagnosis
| Question | Established | Not established |
|---|---|---|
| Why did the Bolton `FORM_REQUEST` fail? | The job made exactly one request (the first form `GET`): 183 bytes received in 0.385 s, 0 redirects, 0 retries, so the connection and TLS worked and the council side answered. It ended `BoundaryFailure:SOURCE_CONTRACT_REJECTED` at stage `FORM_REQUEST`. The retained diagnostic holds an empty body because the first retrieval did not return one. | **The cause.** The record names no HTTP status, media type or specific rejection, because `idox_window.run` collapses every `BoundaryFailure`/`Failure` into one code. The reachable rejections (HTTP failure, rate limit, unexpected response shape, transient upstream response, transport failure) are indistinguishable. **It is UNDETERMINED and is not an IP block.** |
| Why was the final result not published? | Offline reproduction: `closure()` removed the memory scope and set `memory_closure`; every later GitHub call runs `check()`, which raised `Denied('RESOURCE_ENVELOPE_CLOSED_NO_MORE_OPERATIONS')`. The artifact recorded `publication = UNCERTAIN_Denied`. | The artifact does not export the message; the reason is established by code reading plus the reproduction, not by a logged string. The same ordering would deny the final publication on a *successful* run. |
| Why did the owner wait the full timeout? | It waits for the retained marker or an early `completed/final-result.json`; neither existed, so it ran its bounded wait (about 45 minutes) to `HOSTED_PUBLICATION_WAIT_EXPIRED`. | — |
| Why was this not seen in rehearsal? | The rehearsals ran with no memory scope (`memory=None`), so the guard never engaged. | — |

## 2. Owner reconciliation of the first run (read-only)
`HOSTED_PUBLICATION_WAIT_EXPIRED` at `PIPELINE_AWAIT_DURABLE_RETENTION` → failure handling → the capture authority revoked, post-commit readback `CONFIRMED` (it tests that both the grant's and the Bolton exception's `expires_at` are 0; the raw expiry numbers are not exported), diagnostic `unexpired_grants: 0`, no sessions, standing credentials unchanged. Controller result `STOP_RECONCILE_NO_RETRY`, `authority_invalidation = ACKNOWLEDGED_READBACK`, `cleanup = CLOSED`; process and scope gone. The Salford global stop is unchanged. The accepted fail-safe raised a newer manual stop `IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE` (hard-stop generation 2), which replaced `STORAGE_TEST_STOP` as the active manual stop; it was neither cleared nor altered and needs your reconciliation. Audit: `events.jsonl` sha256 `35dedf6a87c3b10d4e23af54590c49bb5af4393358dd79ee9f95675be5035449`, `final-result.json` sha256 `8c26067b366efc208fec0bbb7affdaed80ab355b0e50c867a6d538dad7a26381`, chain head `471027a8b9508fb1a25a5c993ce222d208244214f0a30060bd6c88afb89ccbdc`, 281 events, 38 commands / 4 connections, 109 GitHub requests.

## 3. The smallest corrective proposal (this candidate)
| # | Change | Where |
|---|---|---|
| 1 | The final result is published **inside** the enforced memory scope and a bounded reserve (≤ 14 requests including the two-file publication of 10, ≤ 90 s, existing 2 MiB bound, inside the hosted bound of 140), **then** the scope is closed and the complete closure is sealed locally. No GitHub call is admitted after the scope is closed. The closed-envelope guard is **unchanged** and is tested to still deny. The published record is labelled `closure_stage = PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE`, `cleanup = PENDING_MEMORY_SCOPE_CLOSURE`; the sealed local record (artifact) carries `FINAL_AFTER_PUBLICATION` and `CLOSED`/`UNCERTAIN`. | `stable_pipeline.py` (`finalise`), `operational_runner.py` (`closure(memory_close=…)`, `hosted_finished`), `operational_publication.py` (`reserve_scope`) |
| 2 | The owner accepts the published pending-closure record as a completed hosted run **only** with the exact stage and a non-stop status. | `operational_runner.py` |
| 3 | Safe bounded source diagnostics: `failure_diagnostic.transport` = HTTP status (100–599), media type from a fixed allow-list, redirect disposition (never the location), and the rejection's own fixed literals when allow-listed (else `OTHER`). Never credentials, cookies, headers, URLs, bodies or exception text. Version-1 keys and the original classifications are unchanged. The accepted shared bytes of `request_boundary.py` (pinned by a guard) are untouched; the shape is recorded in the discovery window. | `source_diagnostics.py`, `idox_window.py` |
| 4 | Renderer command-line defect fixed (a comment swallowed `--evidence-head`). | `render_registration.py` |
| 5 | Specification 032 §9 written first and updated after review. | `specifications/` |

Residual by design: the **published and sealed records can differ** — if the final closure fails after publication, the sealed record and workflow artifact report `UNCERTAIN` and a non-zero exit, while the owner (which sees only the published record) cannot observe that. The workflow artifact is the authority for the complete closure and the run is reconciled against it.

## 4. Candidate and evidence
| Item | Value |
|---|---|
| PR | #154 (draft) → `master` `038e9b13c552094682a5bae0016769d0c88b5917` |
| Tested head | `ee4c1b0e7b22c131cae3620c8fd55ded62ff26aa`, tree `fb3bdaf363c222c70d3c93bfab6d5b1d03c960b4` (this package is a later documentation-only commit) |
| CI at the tested head | all pass: discovery contract (203 passed / 1 skipped wrapper; **lifecycle 12 passed**, restricted PG17 + real gh), reusable-batch guard, hosted memory proof (**incl. the publication-inside-the-real-cgroup-v2-scope step**), web |
| Local offline tests | 106 passed (publication/diagnostics 14, pipeline, invalidation, failure path, idox window) |

**Complete lifecycle rehearsals** (disposable PG17, real gh, hosted half as a separate process over a stateful memory scope that drives the real controller guard and the real publication path; new assertions: published record is `PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE`, no GitHub request after the scope closed, sealed record `FINAL_AFTER_PUBLICATION`/`CLOSED`, owner accepted the pending record):
| Scenario | Owner result | Invalidation | Fixed reason | Owner commands / conn | GH |
|---|---|---|---|---|---|
| success | `STABLE_PIPELINE_AUTHORITY_COMPLETED_AUTHORITY_INVALIDATED` | ACKNOWLEDGED_READBACK | — | 73 / 7 | 55 |
| idle pooled session | same | ACKNOWLEDGED_READBACK | — | 73 / 7 | 55 |
| active session | `STOP_RECONCILE_NO_RETRY` | none needed | `PIPELINE_READBACK_ROLE_SESSION_NOT_IDLE` | 15 / 2 | 2 |
| unexpired grant | same | none needed | `PIPELINE_READBACK_UNEXPIRED_GRANT_PRESENT` | 15 / 2 | 2 |
| expiry mismatch | same | none needed | `PIPELINE_READBACK_VALID_UNTIL_MISMATCH` | 15 / 2 | 2 |
| **source failure** | `STOP_RECONCILE_NO_RETRY`, one source call, no replay | ACKNOWLEDGED_READBACK | **`HOSTED_ENDED_BEFORE_RETENTION` — observed on the next poll, not at the end of the wait** | 38 / 4 | 16 |
| screening stops | `…ENDED_INCOMPLETE_AUTHORITY_INVALIDATED` | ACKNOWLEDGED_READBACK | — | 73 / 7 | 52 |
| owner wait expires | `STOP_RECONCILE_NO_RETRY` | ACKNOWLEDGED_READBACK | `HOSTED_PUBLICATION_WAIT_EXPIRED` | 38 / 4 | 17 |
| wrong revision | zero source calls | ACKNOWLEDGED_READBACK | `HOSTED_ENDED_BEFORE_RETENTION` | 38 / 4 | 16 |
| wrong executable | zero source calls | ACKNOWLEDGED_READBACK | `HOSTED_ENDED_BEFORE_RETENTION` | 38 / 4 | 16 |
Limit: the rehearsal scope is a stateful stand-in with the production contract; the **real** cgroup-v2 scope is proved separately in the hosted memory-proof workflow (publication occurs while the scope enforces, the scope is then closed, and the next call is denied), but no single run combines the real scope, the real database and the full lifecycle.

**CI failures on the way (disclosed).** Run on `9c96da81`: (1) the reusable-batch guard failed because I had changed the byte-pinned `request_boundary.py` — a real defect in my change, fixed by restoring the file and moving the capture into the discovery window; (2) the step "Cleanup actual-memory excess kills entire owned scope" failed. **Classification from its logs:** the deliberate over-allocation was killed as designed (`Killed`, about 0.2 s after the scope started); the step then failed one of its two post-kill systemd state checks (`Result = oom-kill` or an empty control group), evaluated within milliseconds of the kill; which one is not recorded because the step prints neither. This candidate touches neither that step's workflow lines nor its test module, and the step passed unchanged on `ee4c1b0e` (a new commit, not a re-run of the same one). Classification: an **intermittent timing race in a pre-existing post-kill check, unrelated to the candidate** — an inference from those facts, not an observed root cause. A first fix commit also had a rehearsal-quoting defect found by an earlier CI run (test code only).

**Independent reviews.** Review 1 (of `7f0d2eab`): HIGH owner would have classified every successful run as incomplete — fixed (`hosted_finished`) and tested; MEDIUM stale transport facts — fixed and tested; MEDIUM published/sealed difference — documented in §9. Review 2 (of the fix delta): no HIGH or MEDIUM; two LOW test gaps accepted (no dedicated test that a 3xx *response shape survives a rejected redirect target* in isolation — covered indirectly by the 302 run test; no test of a 5xx followed by a raising retry — the worker's retry count is 0).

## 5. Remaining limitations
* The Bolton failure cause remains undetermined until a future request records the new transport facts; this candidate does not make one.
* The rehearsal is not a single real-scope end-to-end run (above). The local environment has no PostgreSQL; the lifecycle runs only in CI.
* Low review notes: the time reserve can overshoot by the per-call 5 s runner timeout; near the job deadline `check()` can still deny the publication (recorded as `UNCERTAIN_Denied`); `put_secret` bypasses the reserve (not on the hosted path).
* The current manual stop (generation 2) and the consumed first run still need your reconciliation; nothing here releases a stop.

## 6. Decision and recommendation
**Recommendation: approve this candidate (`ee4c1b0e`) as the corrective for the two defects, but do not authorise a new council request until you decide how to handle the undetermined Bolton failure.** The candidate cannot, by itself, tell us why the council did not return the form; a further request would be needed to record the new transport facts, and that is a separate decision (a new registration and dispatch, a new Bolton exception, and your reconciliation of the generation-2 stop).
Decisions requested: (a) approve the candidate for integration (guarded `[skip render]` merge) — separately authorised; (b) decide whether to authorise one further bounded request with the new diagnostics, and if so how the generation-2 stop is to be reconciled first; (c) accept the residuals above.
**Not authorised by this package:** merge, registration, dispatch, council request, credential change, stop release, Stage advancement.
