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
| GitHub requests | owner ≤ 160 (worst case 147: see the itemised table below), hosted ≤ 140 (worst case about 100) |

## Failure disposition (execution authority vs standing credentials)
See specification section 7. Execution authority is always ended by P3 (or by its own ≤ 55-minute expiry if the owner session is lost). Standing credentials are never touched by this package; ending them is the separately registered `STABLE_CREDENTIAL_REVOCATION` (a fresh registration is rendered for the integrated revision when needed).

## Not authorised
Any production registration, dispatch, grant, exception, source call, application write, unit-fact work, stop release, password rotation, scheduling, deployment, purchase or Stage advancement.

## Arithmetic behind the proposed limits (rehearsal allocations and proposed production limits; none of this is released production authority)
**Owner administrative commands** (measured with the real `Owner` methods against a scripted connection and repeated on the disposable PG17; the rehearsal reproduced 52 / 73 / 90 exactly where the model predicted 52 / 73 / 71+17):
| Phase | Commands | Connections |
|---|---|---|
| fixed read-only readback (before any grant) | 9 | 1 |
| capture authority registration | 11 | 1 |
| ledger read (capture checkpoint) | 5 | 1 |
| screening authority registration (maximum 12 batches = 60 rows / 5) | 22 | 1 |
| ledger read (batch states) | 5 | 1 |
| **normal path** | **52** | **5** |
| revocation-only invalidation with post-commit readback | 12 | 1 |
| final fixed readback | 9 | 1 |
| **through the end of the run** | **73** | **7** |
| failure after the normal path: reserved invalidation 12 + diagnostics 7 (measured 90 commands / 9 connections including the connections the failed run had already used) | 71 modelled, 90 measured | up to 9 |
Allowances: **56 / 80 / 96 commands** (normal 52 + 4, end-of-run 73 + 7, failure 90 + 6) and **8 / 10 connections** (7 and 9 measured, each with a reserve). The earlier placeholder of 48 / 60 / 72 was exhausted by the normal path (52 > 48).

**Owner GitHub requests** (allowance 160; the worst case below is computed by `tests/test_ingestion_stable_pipeline.py::owner_worst_case_github_requests` from the constants and the publisher's own request structure, and the test asserts at least ten requests of reserve):
| Item | Requests |
|---|---|
| account check | 1 |
| freshness check before anything is issued (one ref read, three absent-file probes) | 4 |
| wait for the retained marker or an early result: 2,700 s at the production 30 s interval = 90 polls + 1 boundary poll = 91 ref reads, plus up to 2 probes for each of 3 distinct heads observed | 97 |
| source archive probe and re-read of the retained marker at the observed head | 2 |
| screening marker publication (publisher: ref, commit, 1 blob, tree, commit, patch, ref, 1 file readback = 6 + 2×1) | 8 |
| wait for the restricted job's result: 600 s = 20 polls + 1 = 21 ref reads, plus 1 probe for each of 3 heads | 24 |
| owner evidence publication (2 files = 6 + 2×2) | 10 |
| failure-path secret-name read | 1 |
| **worst case** | **147 of 160 (reserve 13)** |
The disposable rehearsal polls at 1 s through a test-only override of the binding (the production constant stays 30 s and is asserted by a unit test); at 0.1 s it exhausted the bound, which is how the first lifecycle runs ended after the invalidation had already committed.

**Hosted job**: GitHub requests ≤ 140 (polling for the owner marker at 15 s over 480 s = 32, three publications of about 8 = 24, plus reads); 40-minute job limit; hard kill 2,100 s; actual memory 1.5 GiB aggregate / 256 MiB controller / 1 GiB source with no swap (cgroup v2, proved on a hosted runner).

## Evidence-branch waits are presence-based (not change-based)
The restricted job publishes the archive and, seconds later, the retained marker; the owner publishes the screening marker; the restricted job publishes its result. A poll at the production interval may observe only the latest head. A wait that remembers the head it last saw and waits for a *newer* head would take the marker's own commit as its baseline and never see another (the next publication is the owner's): it expires. The rehearsal found this (first as a fixture artefact at a 1 s poll, then reproduced on the committed code `58bfa966` against a scripted branch). Both sides now wait until the awaited file **exists at the current head** (each distinct head probed once; the first probe is of the head as it stands); trees are cumulative, so a later head still contains every earlier file. An HTTP 404 is "not there yet"; every other failure, and any file whose content does not match its git blob identity, is Uncertain. The owner also requires the evidence directory to contain none of the three files before it issues anything.

## Markers belong to this execution (existence is never acceptance)
Every file the two controllers exchange on the evidence branch names the execution it belongs to - the reviewed revision, the manifest, the capture root key, the evidence head the run was registered against and the authority - and the capture it concerns. The owner accepts the retained marker only if that identity matches, its capture digest and kind equal the checkpoint the DATABASE holds, and its archive digest equals both the checkpoint's recorded archive digest and the bytes of the archived source on the branch. The restricted job accepts the owner's marker only if the identity matches and the screening bindings and capture digest equal those it recomputes locally. The owner accepts the restricted job's result only for this execution and (once a capture exists) this capture. A restricted job that ends without retaining a capture publishes an execution-bound result, which the owner reads at once and ends the ceremony on (instead of holding it open for the retention window). Only a confirmed HTTP 404 means "not published yet"; every other failure, and any file whose content does not match its git blob identity, is Uncertain.
