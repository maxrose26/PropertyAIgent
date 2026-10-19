# Stable-credential pipeline — release package (owner authority ceremony + restricted hosted job; prepared, not released)

Specification: `specifications/032-stage4-stable-credential-pipeline.md`. Nothing here is authorised until the Product Owner approves the grouped production proposal. Storage and the bounded credential qualification remain accepted; server reconciliation and operational acceptance remain outstanding; Stage 4 remains OPEN; the Salford global stop and `STORAGE_TEST_STOP` are preserved and not released by this package.

## Two cooperating controllers (kept apart)
1. **Owner controller** (`STABLE_PIPELINE_AUTHORITY`, owner-local, one hidden-input session, administrative credential). It never holds the restricted passwords and never changes a credential, membership, role setting or secret.
   * P0 fixed read-only readback → persisted → compared with the registration; any mismatch or uncertainty ends the run with nothing issued.
   * P1 one capture authority + Bolton exception (`source_calls=1`, ≤ 55 minutes).
   * P2 after the restricted job durably retained the capture: one source-free screening authority (`source_calls=0`) and a non-authoritative marker on the evidence branch.
   * P3 **revocation-only** invalidation: under the control-row lock, only the authorities this execution registered, with their exact execution and exception bindings verified, have only their grant and exception expiry set to zero (stops, generation, unrelated grants and every other field are preserved exactly, verified inside the transaction before COMMIT and again by a readback after it); an uncertain commit is never retried. Then the repeated fixed readback and evidence publication. Runs on every outcome and does not depend on any stop-state.
2. **Restricted job** (`stage4-stable-pipeline-once.yml`, protected environment, the two restricted secrets only, no administrative credential, kernel-enforced actual memory): bounded connection qualification → capture authority check → one source request and durable retention → wait for the marker (no database connection) → source-free queued screening → sealed result published. No connection retry after qualification.

## Numerical budgets
| Boundary | Bound |
|---|---|
| Readback (P0, and P3 repeat) | 1 connection, 9 statements used / ≤ 12 allowed, ≤ 20 s database-active, ≤ 30 s supervised-active, no retry |
| Owner administration overall | **measured** (real Owner methods against a scripted connection, repeated on the disposable PG17): normal path 52 commands / 5 connections (readback 9, capture authority 11, ledger read 5, screening authority 22 for the maximum 12 batches, ledger read 5); through the revocation-only invalidation (12) and the final readback (9) 73 / 7; worst failure at the end of the normal path plus the reserved invalidation and diagnostics 71. Allowances: **56 / 80 / 96 commands** (normal / through the end-of-run / failure incl. diagnostics), **8 / 10 connections** (the rehearsal measured 7 on the normal path and 9 on a failure after it). The earlier placeholder of 48 / 60 / 72 was exhausted by the normal path |
| Owner session | hidden input 120 s; active ≤ 4,380 s; outer ≤ 4,500 s; process backstop 4,600 s; registration ≤ 110 minutes |
| Authorities | capture ≤ 55 minutes (`source_calls=1`); screening ≤ 30 minutes (`source_calls=0`); both invalidated at P3 |
| Source | one observation; ≤ 10 transport requests, ≤ 3,000,000 received-body bytes, ≤ 6 pages, ≤ 60 rows |
| Restricted runtime (capture + screening) | ≤ 1,040 driver statements, ≤ 40 connections, ≤ 300 s aggregate, per-slot ceilings as accepted |
| Connection qualification (before any ledger work) | the reviewed qualification: ≤ 3 attempts per login, ≤ 6 total, 20 s then 60 s, ≤ 330 s; read-only |
| Hosted job | 40-minute job limit; hard kill 2,100 s; **actual memory** 1.5 GiB aggregate / 256 MiB controller / 1 GiB source, no swap, OOM-group kill (cgroup v2) — an address-space limit is not used and is not described as this |
| GitHub requests | owner ≤ 160 (at most 110 polls at 30 s plus about 16 publication requests), hosted ≤ 140 |

## Failure disposition (execution authority vs standing credentials)
See specification section 7. Execution authority is always ended by P3 (or by its own ≤ 55-minute expiry if the owner session is lost). Standing credentials are never touched by this package; ending them is the separately registered `STABLE_CREDENTIAL_REVOCATION` (a fresh registration is rendered for the integrated revision when needed).

## Not authorised
Any production registration, dispatch, grant, exception, source call, application write, unit-fact work, stop release, password rotation, scheduling, deployment, purchase or Stage advancement.
