# Stable-credential pipeline — release package (owner authority ceremony + restricted hosted job; prepared, not released)

Specification: `specifications/032-stage4-stable-credential-pipeline.md`. Nothing here is authorised until the Product Owner approves the grouped production proposal. Storage and the bounded credential qualification remain accepted; server reconciliation and operational acceptance remain outstanding; Stage 4 remains OPEN; the Salford global stop and `STORAGE_TEST_STOP` are preserved and not released by this package.

## Two cooperating controllers (kept apart)
1. **Owner controller** (`STABLE_PIPELINE_AUTHORITY`, owner-local, one hidden-input session, administrative credential). It never holds the restricted passwords and never changes a credential, membership, role setting or secret.
   * P0 fixed read-only readback → persisted → compared with the registration; any mismatch or uncertainty ends the run with nothing issued.
   * P1 one capture authority + Bolton exception (`source_calls=1`, ≤ 55 minutes).
   * P2 after the restricted job durably retained the capture: one source-free screening authority (`source_calls=0`) and a non-authoritative marker on the evidence branch.
   * P3 invalidation of both authorities (`expires_at=0`), repeated fixed readback, evidence publication. Runs on every outcome.
2. **Restricted job** (`stage4-stable-pipeline-once.yml`, protected environment, the two restricted secrets only, no administrative credential, kernel-enforced actual memory): bounded connection qualification → capture authority check → one source request and durable retention → wait for the marker (no database connection) → source-free queued screening → sealed result published. No connection retry after qualification.

## Numerical budgets
| Boundary | Bound |
|---|---|
| Readback (P0, and P3 repeat) | 1 connection, 9 statements used / ≤ 12 allowed, ≤ 20 s database-active, ≤ 30 s supervised-active, no retry |
| Owner administration overall | ≤ 8 connections / ≤ 48 commands normal, ≤ 9 / 60 through invalidation, ≤ 9 / 72 with failure diagnostics (pinned from the disposable measurement) |
| Owner session | hidden input 120 s; active ≤ 4,380 s; outer ≤ 4,500 s; process backstop 4,600 s; registration ≤ 110 minutes |
| Authorities | capture ≤ 55 minutes (`source_calls=1`); screening ≤ 30 minutes (`source_calls=0`); both invalidated at P3 |
| Source | one observation; ≤ 10 transport requests, ≤ 3,000,000 received-body bytes, ≤ 6 pages, ≤ 60 rows |
| Restricted runtime (capture + screening) | ≤ 1,040 driver statements, ≤ 40 connections, ≤ 300 s aggregate, per-slot ceilings as accepted |
| Connection qualification (before any ledger work) | the reviewed qualification: ≤ 3 attempts per login, ≤ 6 total, 20 s then 60 s, ≤ 330 s; read-only |
| Hosted job | 40-minute job limit; hard kill 2,100 s; **actual memory** 1.5 GiB aggregate / 256 MiB controller / 1 GiB source, no swap, OOM-group kill (cgroup v2) — an address-space limit is not used and is not described as this |
| GitHub requests | owner ≤ 140, hosted ≤ 140 |

## Failure disposition (execution authority vs standing credentials)
See specification section 7. Execution authority is always ended by P3 (or by its own ≤ 55-minute expiry if the owner session is lost). Standing credentials are never touched by this package; ending them is the separately registered `STABLE_CREDENTIAL_REVOCATION` (a fresh registration is rendered for the integrated revision when needed).

## Not authorised
Any production registration, dispatch, grant, exception, source call, application write, unit-fact work, stop release, password rotation, scheduling, deployment, purchase or Stage advancement.
