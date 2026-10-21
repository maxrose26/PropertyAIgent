# 034. Partial listing observations, Phase 2: ledger admission, history, queue screening, enablement and reporting

Status: **specification only; nothing here is implemented or authorised.** Builds on specification 033 (v2) and its merged Phase 1 (PR 162). No production execution, no new allowance policy, no council request is authorised by this document. Stage 4 remains OPEN.

## 1. Scope and principle
Make one thing possible, narrowly: a `LISTING_OBSERVATION_V1` (Bolton RECEIVED, one page, non-empty and strictly below the selected page size, no total) can be admitted to the existing ledger, durably retained, queued for the existing record-level screening, and reported honestly - **reusing the existing machinery** (capture root item, durable archive before checkpoint, batch plan, screening children, publication-before-closure, invalidation) with **no interface redesign** and no new table. Everything enabling it is *data in the owner-registered grant* plus **two predicates** in one database function.

## 2. What already works and what does not (evidence from the code)
* Root capture item: `Coordinator.idox_source` calls `contract.project`; for an observation it would call `contract.observe` instead (Python, section 4). Archive-before-checkpoint is `batching.archive_capture` and is kind-neutral.
* Broker checkpoint (`resolve_effect`) stores whatever closed payload it is given; **no kind check** on that path.
* **`ingestion_worker_step`, op `checkpoint`** (worker.sql ~line 222): for a `capture_only` grant and a DISCOVERY task the checkpoint must equal the broker-resolved one *and* have kind `LISTING_RECEIPT_V1`. An observation is refused there (`BROKER_CAPTURE_REQUIRED`).
* **`ingestion_worker_step`, op `batch_row`/`batch_reseal`** (~line 145): the capture parent must have kind `LISTING_RECEIPT_V1` or the call raises `CAPTURE_BINDING`. An observation cannot spawn screening children.
* Op `enqueue_child` (~line 179) also requires the receipt kind, but the capture-only pipeline does **not** use it (it uses `batch_row`); it stays unchanged and therefore still rejects observations by type.
* Finish (`else` branch) is generic: it only requires the outcome string to be in the grant's `completion_outcomes` for the task. The root item's finish in `Coordinator.idox_source` uses the **existing** outcome `ENUMERATED_METADATA_RETAINED` (already allowed), so no outcome list changes; the checkpoint kind carries the distinction.
* `Coordinator.screening` has **no parent-kind check**: it reads `records`, `council` and `source_sha256`, which an observation also has, so queue screening already runs over an observation's children. `Coordinator.metadata_from_scope` requires the receipt kind and therefore keeps rejecting observations.

## 3. The exact database-function change
One function is replaced: `public.ingestion_worker_step`. The replacement file is **derived mechanically from the installed reviewed definition** (`docs/design/ingestion-operational-20261016/worker.sql`) by exactly two textual substitutions (a test regenerates it and requires byte equality; every other byte is identical):
1. In `batch_row`/`batch_reseal` capture binding, `capture.checkpoint::jsonb->>'kind'<>'LISTING_RECEIPT_V1'` becomes
   `(capture.checkpoint::jsonb->>'kind' IS DISTINCT FROM 'LISTING_RECEIPT_V1' AND NOT (capture.checkpoint::jsonb->>'kind'='LISTING_OBSERVATION_V1' AND coalesce(g->'observation_councils','[]'::jsonb) ? (capture.subject::jsonb->>'council')))`.
2. In op `checkpoint`, `w.checkpoint::jsonb->>'kind' IS DISTINCT FROM 'LISTING_RECEIPT_V1'` becomes
   `(w.checkpoint::jsonb->>'kind' IS DISTINCT FROM 'LISTING_RECEIPT_V1' AND NOT (w.checkpoint::jsonb->>'kind'='LISTING_OBSERVATION_V1' AND coalesce(g->'observation_councils','[]'::jsonb) ? (w.subject::jsonb->>'council')))`.
Properties: **default OFF** (a grant without `observation_councils` behaves exactly as today); the enabling list is the grant's, written by the owner and covered by the existing exception's `grant_binding` equality (no change to the exception functions or to any allowance policy); a NULL kind is now *refused* in change 1 (`IS DISTINCT FROM` closes a NULL gap in the original `<>`); no ACL, owner, search_path or signature change; `CREATE OR REPLACE` keeps grants. The original function body stays available as the **rollback** (re-run the reviewed original definition).
**Inventory.** `verify_installed` gains one recognised state (`OBSERVATION_WORKER_APPLIED` = the current reviewed inventory with `ingestion_worker_step` replaced); the installation ceremony is the existing policy-ceremony shape (observe, verify the installed inventory, install, verify, capability read back absent, control record unchanged). That ceremony is **a production change and needs its own approval**; this document only specifies it.

## 4. Application changes (Python; no schema)
* `Coordinator.idox_source`: when the registered grant lists the council in `observation_councils` and the contract is observation-enabled, call `contract.observe(..., observed_at=<UTC now>)` after the strict `project` refusal (`TOTAL_UNKNOWN` is the *only* condition that diverts), archive-before-checkpoint as today, resolve the checkpoint, finish with the existing `ENUMERATED_METADATA_RETAINED` outcome.
* `batching.batch_plans`: accept the observation kind (interval taken from `requested_interval`); the plan records `source_kind`.
* `Coordinator.screening`: only when the parent checkpoint is an observation, the child's recorded result additionally carries `source_kind = LISTING_OBSERVATION_V1`, `window_claim = NONE` and the observation's `observed_at`. For a complete receipt the result is **byte-identical to today** (the fields are added conditionally, so no historical or comparison shape changes). The screening function itself is unchanged (v1, or v2 once Option B is adopted).
* All window-claim consumers keep rejecting the kind (Phase 1 behaviour is retained and re-tested).

## 5. Registration enablement
A new one-shot mode (modes are single-registration namespaces), constructed like the window mode, whose registration carries one extra bound field `observation = {councils: ["bolton"], kind: "LISTING_OBSERVATION_V1"}`. The owner validates it exactly (any other value, or the field in any other mode, is refused) and writes `observation_councils` into the CAPTURE and SCREEN grants. Limits, ceilings, resource bounds, publication reserve and invalidation are the window mode's, unchanged. Named allowances for such a run are a **separate policy decision** (not proposed here).

## 6. Durable observation history (no new table)
Observations are immutable ledger checkpoints plus the durable archive already on the evidence branch. The application history of specification 033 is a **read-side projection** over those immutable records (`observation_history.append` over the stored checkpoints in `observed_at` order); it can always be rebuilt, never edited. A materialised table is deferred until a product surface needs query performance, and would be a separate specification. **Nothing is pruned** (section 9).

## 7. Reporting
Owner and hosted results use `PARTIAL_OBSERVATION_RETAINED_SCREENED_AUTHORITY_INVALIDATED` (never `...COMPLETED...`), carry `window_claim: NONE`, `source_kind`, the observation digest and `observed_at`, and the display label from specification 033. A reconciliation note keeps *recorded* values and *local recomputation* in separate columns, as the 24-scheme review does.

## 8. Acceptance tests (before any production use)
1. **Mechanical derivation:** regenerate the replacement from `worker.sql`; byte equality; the diff is exactly the two substitutions.
2. **Default off (disposable PostgreSQL 17):** with the original function and with the replacement, an observation checkpoint and `batch_row` over an observation parent are refused when the grant has no `observation_councils`, and a `LISTING_RECEIPT_V1` flow behaves identically (full existing lifecycle suite unchanged).
3. **Enabled:** with `observation_councils=["bolton"]` an observation checkpoint is stored once, children are created with the capture as sole dependency, and screening completes; another council, a mislabelled kind, a NULL kind, a stale or foreign parent and a changed record are refused.
4. **Rollback:** reinstalling the original definition restores behaviour 2 exactly; the control record and every stop are untouched by install and rollback.
5. **Inventory:** the new state is recognised; mixed or modified inventories fail closed.
6. **Registration:** the enabling field is validated exactly; absent, extra, wrong council, wrong kind and wrong mode all refuse.
7. **Lifecycle with the real memory scope** (owner and hosted halves): publication inside the scope and reserve, then closure, then the sealed record; invalidation preserved; statuses as in section 7.
8. **Screening parity and provenance** end to end; the observation never appears to any window-claim consumer; no watermark or coverage write exists.
9. **Historical receipts:** stored identities and existing items are untouched (the PR 162 backward-compatibility tests stay green).
10. **No ceiling, retry, redirect, policy or allowance change.**

## 9. Retention: UNRESOLVED (recorded, not decided)
There is *behaviour* but no *written policy* for retained captures, observations and derived screening results (section 8 of specification 033). **Interim rule until the product owner decides: preserve everything; no pruning, expiry or deletion path is added by any phase.** Open questions for the decision: duration per evidence class; whether the raw archive or ledger rows may ever be pruned; treatment of derived screening results; personal-data considerations of addresses in listing text.

## 10. Out of scope
New allowance policy, generation-agnostic policy, any council request or live run, a materialised history table, product surfaces, other councils, zero-result handling, screening rule changes (Option B is separate), scheduling, Stage advancement.
