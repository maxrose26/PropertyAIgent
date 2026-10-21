# Proposal: connecting screening rule v3 to the production ingestion pipeline

**Status: PROPOSAL ONLY. Documentation, no code, no SQL installed, nothing registered or run. Nothing here is deployed or production-enabled.** Production screening is still v1. Stage 4 remains OPEN.
Grounded in `master` at `92fa88d7356f4b7c51fa7257373b0fcd20055e75` (PR #172: disposable-ledger slice 1, merged). Every file reference below is to that commit. The ledger, SQL and controller were inspected by reading the repository only; no database, host or council was contacted.

**Aim.** Make explicitly selected v3 assessments of the already-captured Bolton window (24 records) storable, traceable and routable through the real SQL ledger, worker function and controller, without a council request and without touching the capture or its v1 screening items.

## 0. What is being asked

Decisions needed before any implementation are collected in section 9. In short, this proposal recommends:

1. One `ingestion_worker_step` replacement (installation is a separate, held step) that adds a v3 branch beside the unchanged v1 branch.
2. v3 identity extended with a **code binding** (digest of the modules that produce the saved result) so a code change can never silently share an identity.
3. History presentation removed from the assessment step and replaced by a bounded, paginated, read-only query.
4. A **screening-only** first production demonstration against the retained capture: `source_calls = 0`, `writes = 0`, no application-database effect, no identity write.
5. Sequencing with the separate sparse-observation work (specification 034), which also replaces `ingestion_worker_step`.

## 1. Current-state findings

### 1.1 How production screening works today

| # | Finding | Reference |
|---|---|---|
| F1 | The only SQL function a worker calls is `public.ingestion_worker_step(op, key, fence, owner, authority, binding, payload)`, `SECURITY DEFINER`, one definition. Every op re-reads the control row `FOR UPDATE`, requires an unexpired grant that lists the key, the **contract**, the login, the worker and an **exact** `{task, contract, revision, subject}` binding. | `docs/design/ingestion-operational-20261016/worker.sql:88-116` |
| F2 | Screening children are created by the broker only, through `batch_row` (or `enqueue_child`). Both hard-code `child.contract = 'listing-screen-v1'` and require `revision = sha256(record_json)`; the `INSERT` writes the literal `'listing-screen-v1'`. A duplicate must match subject, revision, dependencies and limits or raises `CONFLICTING_DUPLICATE`. | `worker.sql:160-175` (`batch_row`), `worker.sql:181-195` (`enqueue_child`) |
| F3 | `batch_row` needs a claimed batch item (`LISTING_METADATA`, contract `listing-batch-v1`, `revision = sha256(plan_json)`), a capture parent that is `COMPLETE`, task `DISCOVERY`, kind `LISTING_RECEIPT_V1`, a matching subject, and a payload `capture_json` equal to the capture checkpoint. The capture is read `FOR SHARE`; it is never written. | `worker.sql:131-149` |
| F4 | A worker `checkpoint` is stored as a bounded **worker receipt**, not validated for content (size only: `least(131072, limits.audit_bytes)`). `complete` accepts any outcome string that is in `grant.completion_outcomes[task]`. SQL therefore does **not** know what a screening result says. | `worker.sql:221-233` |
| F5 | The screening result itself is computed in Python by `Coordinator.screening` through `SQLLedger`. The **controller** recomputes every disposition in trusted memory and rejects a forged receipt (`FORGED_SCREENING_RECEIPT`). | `app/ingestion/coordinator.py:217-244`; `verification/ingestion_storage/operational_controller.py:317-333` |
| F6 | `SQLLedger.enqueue` and `SQLLedger.batch_row` hard-code `listing-screen-v1`; `enqueue` raises `QUALIFIED_CHILD_ONLY` for any other contract; `batch_row` cannot express v3 at all (it always builds a v1 identity and sends no contract parameter), so with a v3 coordinator the refusal comes later, as `SCREENING_CONTRACT_NOT_REGISTERED` (`coordinator.py:220`), after `batch_row` has returned or created **v1** children. v3 therefore cannot be created in production, and **fails closed**. | `app/ingestion/sql_ledger.py:48`, `:63` |
| F7 | Authority is registered by the owner: `register(items, authority, capture_key=..., source_calls=..., prepared=...)` builds the grant, with `contracts` taken from the registered items and a **fixed** `completion_outcomes` vocabulary (`SCREENING`: v1 dispositions only). | `verification/ingestion_storage/operational_owner.py:396-399` |
| F8 | The runner builds the screening batches from the retained capture (`batch_plans`), prepares 24 `listing-screen-v1` children and 5 batch items, registers them under `<authority>_SCREEN` with `source_calls=0`, and processes each batch with `process_batch`. Its coordinator is `Coordinator(ledger, {CONTRACT: IdoxListingContract(...)})`, so it takes the **default v1 rule**. | `operational_runner.py:428-456`, `:336-341`; `app/ingestion/batching.py:16-25`, `:44-82` |
| F9 | The controller's nomination path (`execute`) gates identity creation on the **v1** dispositions, pins the screening child's contract to `listing-screen-v1`, and compares the stored receipt with `screen_row(r)` (v1). `resume_capture` recomputes the 24 expected v1 child keys. | `operational_controller.py:327`, `:331`, `:390` |
| F10 | `ingestion_worker_step` is the **original** reviewed definition in every accepted installed inventory (`ORIGINAL`, `SUCCESSOR_POLICY_APPLIED`, `GENERATION2_*`, `GENERATION3_WINDOW_POLICY_APPLIED`); the policy files redefine only `ingestion_bolton_allowed` and `ingestion_register_bolton_exception`. The owner accepts exactly one coherent inventory per mode and refuses any mixture. | `operational_owner.py:219-256`; `docs/design/ingestion-window-demonstration-20261023/policy-window-allowance.sql` |
| F11 | The control row was **last recorded** (23 October reconciliation, not re-read for this proposal) in a **stopped** state: generation 3, manual stop `IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE`, global stop `CONSUMED_SALFORD_GLOBAL_STOP`. While a global stop is set, `ingestion_worker_step` proceeds only if `ingestion_bolton_allowed` admits the authority, and policy v5 names **exactly two** allowances (the 23 October window demonstration, both consumed and invalidated, one exact scope). A new demonstration needs a **new** named allowance, i.e. a policy successor, or an owner decision to change the stop. | `policy-window-allowance.sql:14-29` (allowed), `:30-` (registration; it also names three generation-2 allowances, unreachable at generation 3); `docs/design/ingestion-window-demonstration-reconciliation-20261023/RECONCILIATION.md` rows 41-42 |
| F12 | Ledger resource bounds are enforced in SQL: 4,096 items (`ITEM_BOUND`), 12,288 attempts, 32 MiB total, 131,072-byte payloads, `statement_timeout 10s`, `lock_timeout 3s`. The table has a primary key on `key` and **no secondary index**; `subject` is a `JSON` column. | `worker.sql:171` (items), `:125` (attempts), `:246` (storage), `:225` (checkpoint size); `app/ingestion/schema.py:9-29`; `sql_ledger.py:19-21` |

### 1.2 What slice 1 (PR #172) already provides, and what it does not

Provided (disposable ledger only): explicit selection through `Coordinator(screening_rules=...)` (`coordinator.py:76-83`), one contract per run, a frozen `ScreeningRule` (`listing_screening.py:173-209`), `assessment_identity` (revision = `digest({record_sha256, config_sha256})`, `:210-221`), version-aware `identity_admission_eligible` (`:223-`), and read-only projections (`screening_projection.py`).

Not provided, and the reason this proposal exists:

* **Nothing reaches SQL.** F2, F4, F6, F7, F9 are all unchanged and v1-only.
* **Code is not in the identity.** The configuration binds `rule_version`, `count_spec_version`, `assessor`, `unit_threshold`, `max_text_chars` (`listing_screening.py:194-196`). It does not bind the v1 qualifier whose output is embedded in every v3 result (`_screen_v1` → `app/scrapers/unit_filter.py`). This is not hypothetical: PR #170 changed `unit_filter.UNIT_COUNT_PATTERNS` after the v3 assessor was written, and a v3 assessment made before and after would have had the **same** identity and possibly different content.
* **History scan.** `screening_items()` reads every SCREENING row and checkpoint, and `Coordinator.screening` calls it per record (`coordinator.py:238-242`). Accepted for the disposable slice only.

## 2. Minimum production connection (scope item 1)

Principle: **add a v3 branch, leave the v1 branch's text and behaviour unchanged, and make SQL (not only Python) enforce what v3 means.** All of it is dormant unless a registration explicitly says otherwise (default OFF), exactly the discipline of specification 034.

### 2.1 `ingestion_worker_step` (one replacement function)

Derived **mechanically** from the installed `worker.sql` definition by a short, reviewed list of textual substitutions, with a derivation module and tests identical in shape to `observation_worker_sql.py` (undoing the substitutions reproduces the original byte for byte; a site that is absent or non-unique fails). Sites and behaviour:

| Site | Change | Why |
|---|---|---|
| S1 `batch_row`, child type check (`worker.sql:161`) and identity check (`:164`) | Accept `listing-screen-v1` **or** `listing-screen-v3`; v3 only when the batch plan carries a `screening` binding **and** the grant lists that binding's `config_sha256` in a new `screening_configs` array (absent array ⇒ v3 refused). | F2. SQL checks the plan's `config_sha256` is on the grant's list and that revision, checkpoint and outcome are consistent with it; **SQL does not recompute the configuration** (see 5.3). v3 is admitted only over a `LISTING_RECEIPT_V1` capture, never an observation (2.6). |
| S2 `batch_row`, revision check (`:166`) | For v1: unchanged `revision = sha256(record_json)`. For v3: `revision = sha256('{"config_sha256":"<C>","record_sha256":"<sha256(record_json)>"}')`, where `C` is the plan's bound `config_sha256`. (This is the canonical-JSON digest `assessment_identity` already uses, keys sorted, compact.) | Reuses the slice-1 revision rule exactly; SQL recomputes it. |
| S3 `batch_row`, `INSERT` (`:173`) | Insert the child's validated contract instead of the literal. | F2. |
| S4 `checkpoint` op | When `w.contract = 'listing-screen-v3'`: require `payload.rule_version`, `payload.assessment_revision = w.revision`, `payload.config_sha256` in the grant's `screening_configs`, and `sha256` of the canonical `{record_sha256, config_sha256}` equal to `w.revision`. Size bound unchanged. | F4. A stored v3 receipt is internally bound to its item by SQL. |
| S5 `complete` op (`:231`) | For a v3 child: `outcome` must equal `checkpoint.count_assessment.admission` **and** be in the v3 vocabulary the grant lists. | F4. The ledger outcome can never disagree with the stored routing. |

Not changed: `enqueue_child` (the v3 path uses `batch_row`, like production capture screening today), every other op, every authority/stop/fence/lease/barrier check, `ITEM_BOUND`, attempt and storage bounds.

Interaction with batch identity: a batch item's identity is `(subject, 'LISTING_METADATA', 'listing-batch-v1', digest(plan))`. A v3 plan differs from the recorded v1 plan because it carries the `screening` binding, so the five v3 batch items have **new keys** and cannot collide with, resume or overwrite the five existing batches.

### 2.2 `SQLLedger` and `batching`

* `SQLLedger.batch_row` takes the child contract/revision from the plan's screening binding instead of the literals (`sql_ledger.py:63`); `enqueue` keeps `QUALIFIED_CHILD_ONLY` for v1 and stays v1-only.
* `batch_plans(capture_key, capture, screening=None)` adds the optional binding to each plan. `screening=None` produces byte-identical v1 plans.
* `process_batch` is unchanged: it already calls `coordinator.screening(...)`, which uses the registered rule.

### 2.3 Grant vocabulary (owner)

`register(...)` gains an optional `screening` argument and, for v3, its own mode constants (stop state, expected generation, authority-name rule), because `register` requires the exact stop and refuses a name already in `grants` (`operational_owner.py:405-407`). Only when it is supplied does the grant add (a) `screening_configs: [config_sha256]`, (b) the v3 admission strings to `completion_outcomes['SCREENING']`. Without it the grant is byte-identical to today's (the v1 vocabulary is never widened). `contracts` already follows the registered items, so `listing-screen-v3` appears only when v3 items are registered. A v3 registration is its own execution **mode** (modes are single-registration namespaces) so it cannot be confused with a v1 one.

### 2.4 Controller

* New source-free function `assess_retained(coordinator, key, plan_keys, ...)`, modelled on `resume_capture` (`operational_controller.py:377-400`): verifies the retained capture digest and sealed prior accounting, recomputes the 24 expected v3 child keys, runs the registered rule, and **compares each stored receipt with a trusted-memory recomputation** (the F5 discipline, extended to the v3 binding fields and `assessment_sha256`).
* `execute` (nomination path): the gates and bindings at `:324`, `:327`, `:330` (`screen_task['revision'] != digest(r)`, which a v3 parent would fail closed on as `EXACT_COMPLETED_SCREENING_REQUIRED`), `:331` and `:333` become `identity_admission_eligible(expected, screening_item)` and a contract check against the **registered** rule's contract, so a v3 parent can reach the existing pending-identity path and a v1 parent behaves exactly as now. All later checks (known application, B2/verification scope, coupled gate, `FACTUAL_DEPENDENCY_BINDING`, `new_identity_source`) are untouched. **This wiring is required for the acceptance test of section 5 but is not exercised in production by the first demonstration** (section 8).
* `capture()` and `resume_capture()` remain v1.

### 2.5 Creating v3 assessments from the completed Bolton capture, without changing it

1. The capture item (`DISCOVERY`, `COMPLETE`, kind `LISTING_RECEIPT_V1`, key `d1ff23c0…0545`) and the 24 v1 children and five v1 batch items are **read only**: `batch_row` reads the capture `FOR SHARE` (F3) and inserts only **new** rows whose keys differ because contract and revision differ.
2. New rows: five batch items (new plans) and 24 children (`listing-screen-v3`, revision from S2, dependency `[capture_key]`). The batch items are inserted by the owner's registration (R3, `operational_owner.py:407-410` inserts the registered `items`), the 24 children by the broker's `batch_row` at R4: 5 rows at R3, 24 at R4. Claims are bounded by `max_attempts = 2` (up to 58 attempts if every item retried once), far inside F12.
3. The v3 children are screened source-free from the retained capture (`source_calls = 0`), reusing the same immutable-parent read as `process_batch` (`batching.py:68-79`).
4. Preserved: every v1 checkpoint, outcome and attempt; the capture checkpoint and its archive record; the application database (untouched; no identity is attempted).
5. No automatic link between old and new items is written. Linking is a read-time projection (section 4).

### 2.6 Interaction with the sparse-observation work (specification 034 / PR #164, draft)

Specification 034 also **replaces `ingestion_worker_step`**, deriving it from the same `worker.sql` by two substitutions at the `batch_row`/`batch_reseal` capture-kind test (`worker.sql:145`) and the `capture_only` checkpoint test (~`:222`). Findings:

* The site sets are **disjoint** (034: capture kind; v3: child contract/revision/insert and two ops' tails), but they sit in the same `batch_row` condition chain, and both define a **new installed inventory state** with a new owner mode and installation ceremony.
* Two independent replacements cannot both be "the" reviewed function: whichever installs second must be derived from the first, or both must be derived once.
* **Recommendation:** one derivation module with **both** substitution lists applied to the original, one new inventory state, one ceremony; each list individually default-off (034 by `observation_councils`, v3 by `screening_configs`), each individually removable, and a test that undoing either list alone reproduces the other's single-list function byte for byte. If 034 is not approved soon, v3 proceeds alone and 034 is later rebased onto the combined derivation.
* No other overlap: 034 changes capture-side Python (`idox_source`, `observe`) and a `source_kind` annotation inside `Coordinator.screening`; v3 changes the registry, the identity binding and the controller. The `Coordinator.screening` edits are in different branches but the same method; implementation order must be agreed to avoid a rebase conflict.
* **Correction to a tempting assumption:** 034's own site 1 makes an observation parent *admissible* for `batch_row` once the grant lists the council (034 section 3), so in a combined function an observation could spawn screening children. v3 must therefore **not** inherit that admission: S1 admits a v3 child only when `capture.checkpoint->>'kind' = 'LISTING_RECEIPT_V1'` (never for `LISTING_OBSERVATION_V1`), with a test over an observation parent. A v3 assessment of an observation is out of scope for both proposals.

## 3. Assessment identity and reproducibility (scope item 2)

Reuse, do not replace: `digest`, `revision`, `rule_version`, `assessment_identity` (slice 1). Extend the **configuration** only.

**Proposed binding (identity = what the result depends on):**

```
config = {
  rule_version, count_spec_version, assessor, unit_threshold, max_text_chars,   # as slice 1
  code_binding: sha256 over the canonical list of {path, sha256(LF-normalised bytes)} for
      app/ingestion/listing_screening.py, count_assessment.py, count_evidence.py,
      app/scrapers/unit_filter.py,
  qualifier_contract: 'listing-screen-v1-output-embedded'
}
revision = digest({record_sha256, config_sha256})            # unchanged rule
```

Not bound by the digest: the Python interpreter and `re` behaviour (partly covered by the repository revision in the owner's `execution_binding`). Editing `listing_screening.py` or the coordinator for the proposed `link_related` option re-pins the digest. Stored beside the identity (provenance, not identity): `qualifier_output_sha256` (digest of the embedded v1 result), `assessment_sha256` (digest of `count_assessment`), repository `revision` (already bound by the owner registration's `execution_binding`).

Why a byte digest of four modules rather than a hand-maintained version number: the failure to prevent is a silent change (PR #170 is the example), and a version number is exactly what gets forgotten. The cost is that a comment-only edit to those modules changes new identities; that is safe (new assessments, old ones preserved) and visible. A test pins the expected digest so a change must be a conscious one.

Properties kept: identical inputs and configuration ⇒ the same item (idempotent); a changed threshold or code ⇒ a different item; the source-record digest stays separately recoverable; the controller recomputes the identity in trusted memory and the grant's per-key binding includes the revision, so a worker running different code derives a different revision and is refused before it can write anything: by `EXACT_BATCH_PLAN` / `BATCH_ROW_IDENTITY` in SQL when it builds a child, by `EXACT_AUTHORITY_BINDING_REQUIRED` (F1) when it presents a binding the grant does not hold, or by `SCREENING_CONFIG_BINDING` (`coordinator.py:232`) in Python.

**No supersession.** No column, field or query marks an assessment current, latest, preferred or superseding. Older assessments, v1 results and factual evidence are never modified. A newer assessment does not retire an older one.

## 4. Bounded history access (scope item 3)

**Separate execution from presentation.**

* *Execution* no longer reads other assessments. In the production path `Coordinator.screening` does **not** compute `related_assessments`; the stored v3 checkpoint carries only the binding fields. (`rule.link_related` is a registry option, default `True` for the disposable ledger so PR #172 behaviour is unchanged; the production registration sets it `False`.) Work per record is therefore O(1) regardless of backlog.
* *Presentation* is a read-only query, run on request, never by a worker, never inside a claim:

```
SELECT key, contract, revision, state, outcome->>'outcome' AS outcome,
       checkpoint->>'config_sha256' AS config_sha256, checkpoint->>'rule_version' AS rule_version
FROM ingestion_work_items
WHERE task = 'SCREENING' AND subject::jsonb = :subject::jsonb
  AND key > :after
ORDER BY key
LIMIT :page_size
```

Only scalar columns are selected (never whole checkpoints), results are keyset-paginated, and the page size is capped by the function (**proposed** default 25, hard cap 50). The record digest is not stored in a column for v1 items, so v1 membership is derived from `revision` (v1 revision = record digest) and v3 membership from `checkpoint->>'record_sha256'`; the caller supplies the digest and a page is filtered to it. Queued or not-yet-screened v3 items have no checkpoint, so they never match a per-record filter until screened; the presentation query lists them by contract and revision instead.

**Bounds.** *Enforced today (code constants; nothing here is measured):* the table cannot exceed 4,096 items, 12,288 attempts or 32 MiB (F12); `statement_timeout 10s`, `lock_timeout 3s`. *Proposed:* ≤ 1 query per request, ≤ 50 rows per page, ≤ 10 pages per presentation call, no write, no lock beyond `ACCESS SHARE`, a scan of at most 4,096 rows (the table bound) because there is no secondary index. *To be measured in the disposable PostgreSQL job:* the query's latency at the 4,096-row bound with realistic checkpoints, and its returned bytes. **No new index is proposed**: it would be a schema change and a held decision; the 4,096-row table bound makes it unnecessary at present. If the ledger bound is ever raised, an expression index becomes a separate decision.

The query is executed by the controller/reader under the existing worker login's `SELECT` (the worker already reads rows, `sql_ledger.py:23-27`); it adds no function, grant or privilege.

## 5. Acceptance using retained evidence (scope item 4)

### 5.1 Evidence

* The 24-record projection fixture `tests/fixtures/bolton_window_24_listing.json` (sha256 `9f453625…a268`) and its `PROVENANCE.json`, equal record-for-record to the owner capture (file sha256 `5525be5a…013a`).
* **Open item:** the fixture is a *projection* (reference, proposal, address). The real v1 children were created from the full retained records, so their keys and `digest(record)` can only be reproduced from the full capture. The committed archive `docs/design/ingestion-operational-execution-bolton-window-demonstration-20261023/capture/source.json` is 20,733 bytes on branch `stage4/narrow-continuation-evidence-20261016`, not on `master`. Acceptance must either (a) use fixture-derived records with neutral URLs (self-contained, as in PR #172) or (b) additionally commit the verified capture file. Whether the committed file reproduces the checkpoint digest recorded as the capture sha in the owner retention marker must be **checked, not assumed**, before choosing (b). See decision D6.

### 5.2 Expected routing: a recomputation, not a production result

Recomputed offline on 2026-10-28 from the fixture with the merged rule and threshold 10 (`ls.screen_row(..., RULE_V3, unit_threshold=10)`). Only the **aggregate** of the v1 column is recorded (1 / 3 / 20, `tests/fixtures/bolton_window_24_listing.PROVENANCE.json`); the per-row v1 dispositions are likewise recomputed from the fixture projection (which has no application type or URLs) and agree with that aggregate. **No v3 assessment exists in production.** This table is an expectation, to be checked against the implementation, not evidence of production behaviour.

| # | Reference | v1 disposition (recorded) | v3 admission (recomputed) | v3 reason | Identity-eligible under v3 |
|---|---|---|---|---|---|
| 1 | 01797/26 | INSUFFICIENT_EVIDENCE | RETAIN_NOT_RESIDENTIAL_SUPPLY | NO_RESIDENTIAL_CREATED | no |
| 2 | 01790/26 | INSUFFICIENT_EVIDENCE | RETAIN_NOT_RESIDENTIAL_SUPPLY | NO_RESIDENTIAL_CREATED | no |
| 3 | 01789/26 | INSUFFICIENT_EVIDENCE | RETAIN_NOT_RESIDENTIAL_SUPPLY | NO_RESIDENTIAL_CREATED | no |
| 4 | 01787/26 | INSUFFICIENT_EVIDENCE | ROUTE_COUNT_UNCONFIRMED | RESIDENTIAL_WITHOUT_STATED_COUNT | no |
| 5 | 01786/26 | INSUFFICIENT_EVIDENCE | RETAIN_NOT_RESIDENTIAL_SUPPLY | NO_RESIDENTIAL_CREATED | no |
| 6 | 01785/26 | INSUFFICIENT_EVIDENCE | RETAIN_NOT_RESIDENTIAL_SUPPLY | NO_RESIDENTIAL_CREATED | no |
| 7 | 01784/26 | INSUFFICIENT_EVIDENCE | RETAIN_NOT_RESIDENTIAL_SUPPLY | NO_RESIDENTIAL_CREATED | no |
| 8 | 01783/26 | INSUFFICIENT_EVIDENCE | ROUTE_COUNT_UNCONFIRMED | RESIDENTIAL_WITHOUT_STATED_COUNT | no |
| 9 | 01782/26 | INSUFFICIENT_EVIDENCE | RETAIN_NOT_RESIDENTIAL_SUPPLY | NO_RESIDENTIAL_CREATED | no |
| 10 | 01780/26 | INSUFFICIENT_EVIDENCE | RETAIN_NOT_RESIDENTIAL_SUPPLY | NO_RESIDENTIAL_CREATED | no |
| 11 | 01778/26 | INSUFFICIENT_EVIDENCE | RETAIN_NOT_RESIDENTIAL_SUPPLY | NO_RESIDENTIAL_CREATED | no |
| 12 | 01777/26 | INSUFFICIENT_EVIDENCE | RETAIN_NOT_RESIDENTIAL_SUPPLY | NO_RESIDENTIAL_CREATED | no |
| 13 | 01776/26 | RELATED_APPLICATION_FOLLOW_THROUGH | RETAIN_NOT_RESIDENTIAL_SUPPLY | NO_RESIDENTIAL_CREATED | no |
| 14 | 01775/26 | INSUFFICIENT_EVIDENCE | RETAIN_NOT_RESIDENTIAL_SUPPLY | NO_RESIDENTIAL_CREATED | no |
| 15 | 01769/26 | RELATED_APPLICATION_FOLLOW_THROUGH | RETAIN_RELATED_TO_PARENT | AMENDMENT_OF_PARENT | no |
| 16 | 01768/26 | SUPPORTED_PROCESSING_PRIORITY | ADMIT_SCHEME | PROPOSED_TOTAL_AT_OR_ABOVE_THRESHOLD | yes |
| 17 | 01767/26 | INSUFFICIENT_EVIDENCE | RETAIN_NOT_RESIDENTIAL_SUPPLY | NO_RESIDENTIAL_CREATED | no |
| 18 | 01766/26 | INSUFFICIENT_EVIDENCE | RETAIN_NOT_RESIDENTIAL_SUPPLY | NO_RESIDENTIAL_CREATED | no |
| 19 | 01764/26 | INSUFFICIENT_EVIDENCE | ROUTE_COUNT_UNCONFIRMED | RESIDENTIAL_WITHOUT_STATED_COUNT | no |
| 20 | 01763/26 | RELATED_APPLICATION_FOLLOW_THROUGH | RETAIN_RELATED_TO_PARENT | DISCHARGE_OF_PARENT_CONDITIONS | no |
| 21 | 01762/26 | INSUFFICIENT_EVIDENCE | ROUTE_COUNT_UNCONFIRMED | RESIDENTIAL_WITHOUT_STATED_COUNT | no |
| 22 | 01759/26 | INSUFFICIENT_EVIDENCE | RETAIN_NOT_RESIDENTIAL_SUPPLY | NO_RESIDENTIAL_CREATED | no |
| 23 | 01758/26 | INSUFFICIENT_EVIDENCE | RETAIN_NOT_RESIDENTIAL_SUPPLY | NO_RESIDENTIAL_CREATED | no |
| 24 | 01757/26 | INSUFFICIENT_EVIDENCE | RETAIN_BELOW_THRESHOLD | PROPOSED_TOTAL_BELOW_THRESHOLD | no |

Summary of the recomputation: `RETAIN_NOT_RESIDENTIAL_SUPPLY` 16, `ROUTE_COUNT_UNCONFIRMED` 4, `RETAIN_RELATED_TO_PARENT` 2, `ADMIT_SCHEME` 1, `RETAIN_BELOW_THRESHOLD` 1. One record (01768/26) is identity-eligible under v3; it is also the single v1 `SUPPORTED_PROCESSING_PRIORITY`. The three v1 `RELATED_APPLICATION_FOLLOW_THROUGH` records are separated by v3: 01776/26 becomes `RETAIN_NOT_RESIDENTIAL_SUPPLY`, and 01769/26 and 01763/26 become `RETAIN_RELATED_TO_PARENT` (an amendment and a condition discharge); none is identity-eligible any more. Four records route to count confirmation because the assessor sees residential wording without a stated count (householder extensions and an HMO); that is existing assessor behaviour and outside this proposal.

### 5.3 Tests (disposable PostgreSQL, real proposed SQL and controller path)

Environment: the disposable PostgreSQL 17 service already used by the `restricted-provisioning` job (`stage4-discovery-offline.yml:195`), real roles and logins, the actual replacement function text installed into a disposable database only, `INGESTION_REQUIRE_LOCAL_PG`, loopback only. **No network egress, no council host.**

| Area | Test |
|---|---|
| v1 compatibility | With the replacement installed, the existing v1 tests (`test_discovery_ingestion_operational_pg.py`, storage-controller and statistics suites) pass unchanged; a v1 grant has no `screening_configs`; v1 plans, keys and revisions byte-identical; v1 registration vocabulary unchanged. |
| Default OFF | A grant without `screening_configs` refuses a v3 child (`BATCH_ROW_TYPES`); a v3 plan with a grant listing a different `config_sha256` is refused. |
| Configuration mismatch | Wrong `config_sha256` in plan vs grant vs checkpoint vs revision: refused by SQL (`batch_row`, `checkpoint`, `complete`). Wrong threshold or wrong `code_binding` is **not** detectable by SQL (it cannot recompute canonical JSON from `jsonb`); it is refused by the Python recomputation and the controller's trusted-memory comparison, and by the grant's per-key binding when the resulting revision differs. |
| Duplicate execution | Replaying `batch_row` for the same record/config returns the existing child (`old_child`), never a second row; a conflicting duplicate raises `CONFLICTING_DUPLICATE`; a completed batch is read-only (`BATCH_ALREADY_COMPLETE`). |
| Malformed / stripped version fields | v3 checkpoint with `rule_version`, `routing_authority` or `count_assessment` removed, mislabelled, or admission outside the vocabulary: refused by `checkpoint`/`complete` SQL and by the controller; a v3 item with its fields stripped is ineligible at the identity gate while a genuine historical v1 parent still passes (the PR #172 hardening, now enforced against real rows). |
| Authority expiry | Grant expiry mid-batch: further `claim`/`checkpoint`/`complete` raise `EXACT_AUTHORITY_BINDING_REQUIRED`; nothing half-written; no authority outlives its registration. |
| Failure cleanup | A worker killed after a child checkpoint: `ingestion_recover_abandoned`; resume re-checkpoints under the recovered fence and never duplicates; a failure inside `process_batch` raises the stop (`BATCH_SECURITY_IDENTITY_ACCOUNTING_OR_PERSISTENCE_FAILURE`) and launches no next slot; storage and item bounds hold. |
| Preservation | Before/after row comparison of every pre-existing row (capture, 5 batches, 24 v1 children, attempts): byte-identical, including checkpoints and outcomes. |
| Zero council requests | The v3 grant has `source_calls = 0`; the test asserts no `begin_source` is ever recorded, `begin_source`/`begin_write` on a SCREENING child is refused by `TASK_EFFECT` (`worker.sql:198`) and the allowance is `source_calls = 0`, the supervised worker has no source client, and the job runs with outbound network disabled. Evidence is the grant, the attempt/phase rows and the absence of any socket. |
| Identity gate | An eligible v3 receipt reaches the **existing** pending-identity path in the controller test, and every existing check still applies (unsupported source, known application, B2 withheld). Assertions: `estimated_unit_count IS NULL`, `unit_facts = NOT_WRITTEN`, `unit_confirmation_status` pending, no Site link, no dwelling count, no approval, no qualified scheme. Non-eligible outcomes never reach it. |
| History | The paginated query returns bounded pages in a stable order, never a checkpoint body, never a `current`/`latest`/`supersedes` field; a ledger at the 4,096-item bound still answers within `statement_timeout`. |
| Derivation | The replacement equals the original with exactly the listed substitutions; undoing them reproduces `worker.sql` byte for byte; (if combined with 034) each list is separately removable. |

Bounds: *proposed* (to be enforced by the tests above) — per-test wall-time ≤ the existing 90-180 s step timeouts; one extra CI step. *Measured later in CI and reported*, not claimed here.

## 6. Release and disable plan (scope item 5)

Four **separately approvable** stages. None is authorised by this proposal.

| Stage | What happens | Production effect |
|---|---|---|
| **R1 Code integration** | Merge the Python, derivation module, tests and documentation. | None. The SQL function text exists only as a file; no connection is made. The production path remains v1 (F6). |
| **R2 Function installation** | Owner ceremony installs the replacement `ingestion_worker_step` (and the policy successor of F11, if the stop is retained) into the production database, as a new, named, verified inventory state. | The function behaviour for v1 is unchanged; v3 is refused unless a grant lists `screening_configs`. No row is created. This is the first production database change and needs its own approval, ceremony readback and rollback text. |
| **R3 Authority registration** | Owner registers one named allowance (`screen`-only, `source_calls = 0`, `writes = 0`) binding the 29 prepared items (5 inserted at registration, 24 created by the broker), the single `config_sha256` and the repository revision. | A grant exists until expiry (bounded ≤ 24 h by F1). Grant data in the control row **plus the 5 registered batch items** (inserted by the owner's registration). A v3 mode needs its own stop/generation constants and the same "authority not already in grants" rule as the existing modes. |
| **R4 Execution** | The finite owner run screens the 24 records source-free and invalidates the authority with a committed readback. | 29 new ledger rows (5 batches, 24 v3 children) and their attempts. No application-database write, no council request. |

**Smallest separately approvable production demonstration (R2+R3+R4, one approval each):** re-assess the 24 retained Bolton records with one frozen configuration, screening-only. Exact effects: ≤ 29 new `ingestion_work_items` (5 + 24), ≤ 58 `ingestion_work_attempts` (`max_attempts = 2`), one grant added and then invalidated, **zero** source calls, **zero** application writes, **zero** identities, the capture and all 24 v1 children unchanged. The nomination/identity path (section 2.4) is built and tested but **not used** in this demonstration.

**Disabling v3 while preserving evidence.**

1. *Stop issuing*: do not register a v3 allowance; v3 is default-off in SQL (no `screening_configs`) and in Python (default registry is v1).
2. *Invalidate*: the existing invalidation with committed readback removes any registered allowance; the control state is read back unchanged.
3. *Roll back the function*: restore the previous reviewed `ingestion_worker_step` text (the derivation guarantees byte-identical restoration). Existing v3 rows are inert data: v1 code never claims them (contract not in any grant), and they are not deleted.
4. *Preserve*: no delete, no `supersedes`, no rewrite. v3 checkpoints, outcomes, attempts and the history query remain available read-only. The history query works with the v1-only function installed because it is a plain `SELECT`.

## 7. Residual risks

* **Two function replacements** (034 and v3): ordering and a single derivation are required (2.6).
* **Policy successor** for the stopped control state (F11) is a third database change in the chain; alternatives in D3.
* **Code-digest sensitivity**: any edit to the four bound modules changes new identities (safe; visible).
* **Bound modules are Windows/Linux byte-sensitive**: the digest normalises line endings; a test must prove it on both.
* **Fixture is a projection** (5.1): record-level reproducibility of the *real* v1 children needs the full capture.
* **Checkpoint size**: a v3 checkpoint embeds the proposal and the v1 result; the 24 Bolton rows are small, but the 131,072-byte payload bound applies and must be tested at the largest proposal (8,192 characters).
* **Assessor content is not a planning fact**: v3 outcomes are routing, not counts or approvals. `ROUTE_COUNT_UNCONFIRMED` records stay non-executable questions.
* **History query** cost is bounded by the table bound, not by an index (4).
* **Householder/HMO over-routing** to count confirmation is existing assessor behaviour.

## 8. Keep outside

Automatic document retrieval or parent resolution; the owner-review portal; general backlog processing, discovery checkpoints, overlap rules, scheduling; search or display; changes to counting rules, buyer matching or retention; a general allowance-policy redesign. Investigation requirements remain explicitly non-executable (`executable: false`, `executor: NONE`).

## 9. Decisions needed before implementation

* **D1 (sequencing with 034).** Combine into one derivation and one inventory state, or land v3 alone first? *Recommendation:* one module, two independent default-off lists, whichever approves first lands first.
* **D2 (identity).** Approve the `code_binding` byte-digest of the four modules in the v3 configuration (with a pinned-digest test)? *Alternative:* explicit version constants with a drift test.
* **D3 (stop state).** The control row is stopped (generation 3). Approve a mechanical **policy v6** successor (one new named screen-only allowance; larger than "same shape as v5": v6 must also change the exception-key cap exemption, the name lists in both policy functions, the stop-digest branch and the owner's inventory set), **or** ask the owner to resolve the stop through a separately approved owner action, **or** defer production until the stop is resolved. This proposal does not choose.
* **D4 (demonstration scope).** Approve the screening-only re-assessment of the 24 retained records as the smallest first demonstration, with the identity path built and tested but unused.
* **D5 (history).** Approve removing `related_assessments` from production checkpoints and the paginated read-only query (page 25 default, 50 cap, 10 pages per call, no new index).
* **D6 (evidence).** Fixture-derived records only, or commit the verified full capture file (after the digest check in 5.1)?
* **D7 (installation).** Who runs R2, and the rollback text it must carry, to be written with the implementation PR.

Nothing here authorises implementation, merge, SQL installation, grants, stop changes, registration, execution, council requests, live re-screening, application writes, deployment or Stage advancement.
