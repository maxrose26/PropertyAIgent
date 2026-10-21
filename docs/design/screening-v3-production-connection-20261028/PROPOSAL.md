# Proposal: connecting screening rule v3 to the production ingestion pipeline

**Status: PROPOSAL ONLY. Documentation, no code, no SQL installed, nothing registered or run. Nothing here is deployed or production-enabled.** Production screening is still v1. Stage 4 remains OPEN.
Grounded in `master` at `92fa88d7356f4b7c51fa7257373b0fcd20055e75` (PR #172: disposable-ledger slice 1, merged). Every file reference below is to that commit. The ledger, SQL and controller were inspected by reading the repository only; no database, host or council was contacted.

**Aim.** Make explicitly selected v3 assessments of the already-captured Bolton window (24 records) storable, traceable and routable through the real SQL ledger, worker function and controller, without a council request and without touching the capture or its v1 screening items.

## 0. What is being asked

This is the **finalised** proposal. Design directions from the Product Owner are recorded in section 9.1 (v3 first and compatible with 034 but not bundled; code binding; stops preserved; the 24 retained records only; no history scan in execution; the verified full retained capture; the owner-terminal ceremony). Decisions that remain are in section 9.3. In short, this proposal recommends:

1. One `ingestion_worker_step` replacement (installation is a separate, held step) that adds a v3 branch beside the unchanged v1 branch.
2. v3 identity extended with a **code binding** (digest of the modules that produce the saved result) so a code change can never silently share an identity.
3. History presentation removed from the assessment step and replaced by a bounded, paginated, read-only query.
4. A **screening-only** first production demonstration against the retained capture: `source_calls = 0`, `writes = 0`, no application-database effect, no identity write.
5. v3 first, compatible with (but not bundled with) the separate sparse-observation work (specification 034), which also replaces `ingestion_worker_step` at disjoint sites; v3 explicitly refuses observation parents.

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
| F11 | The control row was **last recorded** (owner audit timestamps of **2026-10-20**; the `20261023` in the file and authority names is a namespace identifier; not re-read for this proposal and not assumed current) in a **stopped** state: generation 3, manual stop `IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE`, global stop `CONSUMED_SALFORD_GLOBAL_STOP`. While a global stop is set, `ingestion_worker_step` proceeds only if `ingestion_bolton_allowed` admits the authority, and policy v5 names **exactly two** allowances (the window demonstration named `…20261023`, executed 2026-10-20, both consumed and invalidated, one exact scope). A new demonstration needs a **new** named allowance, i.e. a policy successor, or an owner decision to change the stop. | `policy-window-allowance.sql:14-29` (allowed), `:30-` (registration; it also names three generation-2 allowances, unreachable at generation 3); `docs/design/ingestion-window-demonstration-reconciliation-20261023/RECONCILIATION.md` rows 41-42 (reconciliation namespace identifier; the audit times in it are 2026-10-20) |
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
* Two independent replacements cannot both be "the" reviewed function. **Direction recorded: v3 first, not bundled with sparse-observation implementation.** Whichever of v3 and 034 installs second must be derived from the first as a further substitution list over the installed text (with its own inventory state and ceremony); the two lists are independent, each default-off, each individually removable.
* **Compatibility, not bundling:** the v3 derivation module contains only the v3 list; a test applies the v3 and the 034 lists in both orders to `worker.sql` and requires identical output, and a test over an observation parent requires that v3 children are still refused. If 034 is approved first, v3 rebases onto its inventory state; if v3 lands first, 034 is rebased onto it.
* No other overlap: 034 changes capture-side Python (`idox_source`, `observe`) and a `source_kind` annotation inside `Coordinator.screening`; v3 changes the registry, the identity binding and the controller. The `Coordinator.screening` edits are in different branches but the same method; implementation order must be agreed to avoid a rebase conflict.
* **Correction to a tempting assumption:** 034's own site 1 makes an observation parent *admissible* for `batch_row` once the grant lists the council (034 section 3), so in a combined function an observation could spawn screening children. v3 must therefore **not** inherit that admission: S1 admits a v3 child only when `capture.checkpoint->>'kind' = 'LISTING_RECEIPT_V1'` (never for `LISTING_OBSERVATION_V1`), with a test over an observation parent. A v3 assessment of an observation is out of scope for both proposals.


## 3. Assessment identity and reproducibility (scope item 2)

Reuse, do not replace: `digest`, `revision`, `rule_version`, `assessment_identity` (slice 1). Extend the **configuration** only.

**Proposed binding (identity = what the saved result depends on):**

```
config = {
  rule_version, count_spec_version, assessor, unit_threshold, max_text_chars,   # as slice 1
  code_binding: sha256 over the canonical list of {path, sha256(LF-normalised bytes)} for the bound modules,
  digest_probe:  digest(<fixed test vector>)        # detects a change in the canonical-JSON digest function
}
revision = digest({record_sha256, config_sha256})   # unchanged rule
```

**Bound modules** (the assessment's runtime closure inside `app/`, measured on `master` by importing and running `ScreeningRule(RULE_V3).screen()` plus `assessment_identity()` on a retained record): `app/ingestion/listing_screening.py` (contains `_screen_v1`, the embedded v1 result), `app/ingestion/count_assessment.py`, `app/ingestion/count_evidence.py`, `app/scrapers/unit_filter.py` (the v1 qualifier). `app/ingestion/ledger.py` is also loaded (for `digest`), but binding its whole file would re-key every identity on any unrelated ledger edit; instead its `digest` behaviour is bound by `digest_probe`. `app/config` is imported lazily only when a rule is built from a council name and does not enter the result. The embedded v1 result is therefore covered twice: by the code that computes it, and by `qualifier_output_sha256` stored beside the identity.

Stored beside the identity (provenance, not identity): `qualifier_output_sha256` (digest of the embedded v1 result), `assessment_sha256` (digest of `count_assessment`), the repository revision (already bound by the owner registration's `execution_binding`). Not bound by the digest: the Python interpreter and `re` behaviour (recorded as provenance, and covered by the execution revision and the pinned CI environment).

**Why a byte digest and not a version number.** The failure to prevent is a silent change; PR #170 changed `unit_filter.UNIT_COUNT_PATTERNS` after the v3 assessor existed and a version number is exactly what gets forgotten. The cost is that a comment-only edit changes new identities; that is safe (new assessments, old ones preserved) and visible. Editing `listing_screening.py` for the proposed `link_related` option also changes the digest, so the option and the digest land together and the pinned value is set once, in the implementation PR.

**How dependency coverage and Windows/Linux consistency are tested (all offline, runnable in the existing CI job):**

1. *Closure test.* In a fresh interpreter, import the modules, run the v3 screen on a probe record, and collect every loaded module whose file is under the repository. The set must be a subset of `{bound modules} ∪ {declared exclusions: ledger.py, schema.py, package __init__ files}`. A new import in the assessment path fails the test until it is bound or consciously excluded.
2. *Pinned digest.* The expected `code_binding` is a constant in the test. Changing any bound byte fails it, forcing a conscious update (the failure message names the file).
3. *Line-ending independence.* The digest function reads bytes (never text mode) and replaces `\r\n` with `\n` before hashing. Test: for each bound module, hash the bytes, a CRLF-transformed copy and an LF copy; all three give the same file digest; a lone `\r` or a UTF-8 BOM in a bound file fails the test.
4. *Cross-platform.* The same test runs on the Linux CI job; its pinned value was also produced from the git blob (`git show <rev>:<path>`), not the working tree, so a Windows `autocrlf` checkout and a Linux checkout agree. Run on both before the pin is accepted; this proposal only specifies it.
5. *Content-addressing end to end.* The v3 identity of the 24 retained records is computed twice (the worker's rule and the controller's trusted recomputation) and must agree; the grant's per-key binding includes the revision, so a worker running different bytes derives a different revision and is refused before it can write: by `EXACT_BATCH_PLAN` / `BATCH_ROW_IDENTITY` in SQL when it builds a child, by `EXACT_AUTHORITY_BINDING_REQUIRED` when it presents a binding the grant does not hold, or by `SCREENING_CONFIG_BINDING` (`coordinator.py:232`) in Python.

Properties kept: identical inputs and configuration give the same item (idempotent); a changed threshold or code gives a different item; the source-record digest stays separately recoverable.

**No supersession.** No column, field or query marks an assessment current, latest, preferred or superseding. Older assessments, v1 results and factual evidence are never modified.

## 4. Bounded history access (scope item 3)

**Separate execution from presentation.**

* *Execution* never reads other assessments. In the production path `Coordinator.screening` does not compute `related_assessments`; the stored v3 checkpoint carries only the binding fields. (`rule.link_related` stays `True` for the disposable ledger so PR #172 behaviour is unchanged; the production registration sets it `False`.) Work per record is O(1) regardless of backlog.
* *Presentation* is a read-only query run on request, never by a worker and never inside a claim.

**The query (one per request, one page per request):**

```
SELECT key, contract, revision, state,
       outcome::jsonb->>'outcome'        AS outcome,
       checkpoint::jsonb->>'rule_version'    AS rule_version,
       checkpoint::jsonb->>'config_sha256'   AS config_sha256,
       checkpoint::jsonb->>'record_sha256'   AS record_sha256
FROM ingestion_work_items
WHERE task = 'SCREENING'
  AND subject::jsonb = :subject::jsonb
  AND (revision = :record_sha256 OR checkpoint::jsonb->>'record_sha256' = :record_sha256)
  AND key > :cursor
ORDER BY key
LIMIT :page_plus_one
```

* **Record-digest filter.** A v1 item's `revision` *is* the record digest (`digest(record)`, `coordinator.py` v1 branch), so v1 membership is `revision = :record_sha256`. A v3 item's `revision` is `digest({record_sha256, config_sha256})` and cannot be inverted, so v3 membership is the stored scalar `checkpoint->>'record_sha256'`. The filter is in SQL, on scalar fields; no checkpoint body is returned or parsed in Python.
* **Unscreened v3 items** (queued, no checkpoint) have no result and therefore no assessment to present; they do not match, by definition. Their existence is visible by contract and revision to the owner's registration readback.
* **Pagination.** Keyset on the unique primary key `key`. `page_size` default **25**, maximum **50** (enforced; larger values are clamped, not rejected). The function fetches `page_size + 1` rows: if an extra row exists the response carries `next_cursor = key of the last returned row`, otherwise `next_cursor = null`. **One page and one query per request.** There is no automatic traversal and no multi-page call; a caller who wants the next page makes a new request with the cursor. No write, no lock beyond `ACCESS SHARE`.
* **Bounds.** *Enforced today (code constants; nothing here is measured):* 4,096 items, 12,288 attempts, 32 MiB (F12), `statement_timeout 10s`, `lock_timeout 3s`. *Proposed:* ≤ 1 query per request, ≤ 50 rows per page, a scan of at most 4,096 rows (the table bound; no secondary index exists), returned bytes ≤ 50 rows × the scalar fields (a few kilobytes). *To be measured in the disposable PostgreSQL job:* latency at the 4,096-row bound and returned bytes. **No new index is proposed**: that would be a schema change and a held decision.
* **Tests (disposable PostgreSQL, no skipped or duplicated matches).** Seed one record with mixed v1 and v3 assessments (several configurations), plus non-matching records, with more than 50 matches in one scenario and exactly `page_size` matches in another (the boundary case: `next_cursor` must be null). Assert: the concatenation of all pages equals the complete match set; no key appears twice; no match is missing; the order is ascending by key on every page; page size never exceeds 50 and defaults to 25; a request with a valid cursor beyond the last key returns an empty page and a null cursor; rows inserted between two requests with keys above the cursor appear later, rows with keys below it are never inserted into an already-passed range (so a traversal never repeats); no row contains `supersedes`, `current` or `latest`; and the plan touches no more than the table bound.

The query runs under the existing worker login's `SELECT` (the worker already reads rows, `sql_ledger.py:23-27`); it adds no function, grant or privilege.

## 5. Acceptance using retained evidence (scope item 4)

### 5.1 Retained-capture reconciliation, resolved offline

The demonstration must use the **verified full retained capture**. This was reconciled offline on 2026-10-21 using only committed evidence and the repository's own generating code; no database, host or council was contacted. Full values are in [`retained-capture-reconciliation.json`](retained-capture-reconciliation.json). Four different objects carry four different hashes, and they are **not expected to match each other**:

| Object | Representation | Generating code | Value (prefix) | Reproduced |
|---|---|---|---|---|
| **Archive file** `capture/source.json` (20,733 bytes) | Compact canonical JSON of the adapter's `source` object (`sort_keys`, separators `(',',':')`), exactly what the runner wrote | `batching.archive_capture` (`raw = json.dumps(source, sort_keys=True, separators=(',',':'))`), receipt `sha256 == digest(source)` | `5525be5a…013a` | **Yes.** The file's SHA-256 equals `digest(source)` and equals the archive hash recorded in `retained.json`. |
| **Capture checkpoint** (`LISTING_RECEIPT_V1`) | The *derived* receipt stored in the ledger: projected records, segments, `outer_supervisor`, resources, `durable_archive` | `IdoxListingContract.project(source, outer, limits)` then `idox_source` adds `durable_archive` (`coordinator.py`, `batching.py`) | `d5fa9e29…45ee` | **Yes, exactly**, from the archive file, the supervisor receipt in `events.jsonl` (sequence 19) and the archive receipt (`commit 3587e277…`, path `…/capture/source.json`, size, hash). |
| **Capture key** | `digest({subject: scope, task: DISCOVERY, contract, revision: manifest_sha256})` | `operational_owner.item` | `d1ff23c0…0545` | **Yes.** |
| **Individual record digests** (24) | `digest(record)` of each *projected* record inside the checkpoint | `ledger.digest`; a v1 child's revision is exactly this | see JSON | **Yes.** All 24 equal the v1 children's revisions. |
| **Screening bindings** (30 = root + 5 batches + 24 children) | `digest({key: {subject, task, contract, revision}})` | `operational_owner.register` | `ad4e5982…445f` (`registered.json`) | **Yes, exactly.** |

Why the hashes differ legitimately: the archive hash covers the raw `source`; the checkpoint hash covers a *different object derived from it* plus runtime facts (supervisor receipt, archive commit); a record digest covers one projected record; the capture key covers an identity, not content; the bindings hash covers task identities. None is a hash of another. The chain is: file bytes → `source` → (project + supervisor + archive receipt) → checkpoint → projected records → child identities → registered bindings. Every link was recomputed, and every recomputed value matches the retained value.

The reproduction was run with the code at `master` **and** with an export of the generating revision `b851b358…` (`idox_adapter.py` and `batching.py` differ between them only by the additive observation support from PR #162); both give `d5fa9e29…`. The reproduction script is in Appendix A; it needs only the five committed evidence files.

**What this does and does not establish.** Offline evidence proves the committed archive file is exactly the capture that the retained checkpoint digest, the capture key and the registered child identities were derived from, and that the 24 v1 children's identities are reproducible. It does **not** prove, offline, that those rows are currently `COMPLETE` in the production database, nor that the control row is in any particular state; those are facts about production that were last recorded in the owner's archive (events 88 and 163 in the reconciliation) and can only be re-checked by a read-only readback during the approved run.

**Remaining gaps (exact, with consequence).**

1. The owner's `events.jsonl` (191 events, the reconciliation's authority) is in the owner's write-protected archive; the committed copy is the earlier 106-event "published before closure" version. *Consequence:* nothing in this reconciliation depends on the missing events (the outer supervisor and archive receipt are in the committed copy), but the cross-check "event 88 / event 163" in the reconciliation is quoted, not re-derived.
2. The evidence directory is on a **branch**, not on `master`, and branches move. *Consequence:* the demonstration must cite immutable blobs (below), and the implementation PR must copy the five files into `master` at those exact hashes rather than referencing the branch.
3. `registered.json` was last committed in `50bf769` (not in the branch's later head); its hash is pinned below. No alteration of any historical evidence is proposed.

**Immutable evidence revision and hashes the demonstration would require** (all to be re-verified by the implementation PR and by the run):

| Item | Value |
|---|---|
| Evidence directory | `docs/design/ingestion-operational-execution-bolton-window-demonstration-20261023/` on branch `stage4/narrow-continuation-evidence-20261016` (head at inspection `3a0b52f018e25b6430f259bd25d47416e24d88b5`) |
| `capture/source.json` | sha256 `5525be5a6b5fc3fdfac43849bc502cd05c0c9023da1440627b975672fe55013a`, 20,733 bytes, committed in `3587e2778720f56a9510b33c7bbce7584f6be59d` |
| `capture-retained/retained.json` | sha256 `a47122d0bf386a83f423d0f41d0fb2984a4f3eb8d2cf7cf0aeff74016d7ec2ee`, commit `b56d26b4dbc04def8777145fde8b1e3f3bbf7f8f` |
| `screening-authority/registered.json` | sha256 `458c50efd3c55e2ef10193f4449e85ddcb84e2b7eda397eb9bb872fdeedb7c5d`, commit `50bf769` |
| `completed/final-result.json`, `completed/events.jsonl` | sha256 `d38db9b6…ab9e`, `26d6392b…de2dd0`, commit `3a0b52f0…` |
| Generating code revision | `b851b358b9a8665f5c661d252013149301aa8524` |
| Capture checkpoint digest (pinned in the registration and checked against the ledger row at run time) | `d5fa9e29bdd51afbf36772e9b08880af6811a8cec771a3335bad0095801445ee` |
| Capture key | `d1ff23c04af746a5219e7c109255db0310d2a006c732bcac4f66f126b0240545` |

At run time the controller reads the capture row's checkpoint from the ledger and requires `digest(checkpoint) == d5fa9e29…` (the plan already binds `capture_sha256`, `batching.py:16-25`), so a production row that differed from the retained evidence would stop the run before any child is created. Synthetic or projected records may supplement tests but cannot substitute for this evidence.

### 5.2 Expected routing: a local recomputation, not a production result

Every v1 and v3 outcome below is a **local recomputation on 2026-10-21** from the retained records, with the merged rule and threshold 10. The only recorded production result is the archived v1 **aggregate** (1 `SUPPORTED_PROCESSING_PRIORITY`, 3 `RELATED_APPLICATION_FOLLOW_THROUGH`, 20 `INSUFFICIENT_EVIDENCE`, `final-result.json`). **No v3 assessment exists in production.** Routing was computed from the 24 *full retained records* and from the committed projection fixture (`tests/fixtures/bolton_window_24_listing.json`); the two agree for every record. The v1 recomputation agrees with the recorded aggregate. This table is an expectation to check the implementation against, not evidence of production behaviour.

| # | Reference | v1 disposition (local recomputation) | v3 admission (local recomputation) | v3 reason | Identity-eligible under v3 |
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

Summary of the recomputation: `RETAIN_NOT_RESIDENTIAL_SUPPLY` 16, `ROUTE_COUNT_UNCONFIRMED` 4, `RETAIN_RELATED_TO_PARENT` 2, `ADMIT_SCHEME` 1, `RETAIN_BELOW_THRESHOLD` 1. One record (01768/26) is identity-eligible under v3; it is also the single v1 `SUPPORTED_PROCESSING_PRIORITY`. The three v1 `RELATED_APPLICATION_FOLLOW_THROUGH` records are separated by v3: 01776/26 becomes `RETAIN_NOT_RESIDENTIAL_SUPPLY`, and 01769/26 and 01763/26 become `RETAIN_RELATED_TO_PARENT`; none is identity-eligible any more. Four records route to count confirmation because the assessor sees residential wording without a stated count (householder extensions and an HMO); that is existing assessor behaviour and outside this proposal. Each v3 checkpoint for these records measures 2,319–3,043 bytes locally (bound 131,072); computing and binding all 24 took about 0.02 s locally.

### 5.3 Tests (disposable PostgreSQL, real proposed SQL and controller path)

Environment: the disposable PostgreSQL 17 service already used by the `restricted-provisioning` job (`stage4-discovery-offline.yml:195`), real roles and logins, the actual replacement function text installed into a disposable database only, loopback only. **No network egress, no council host.**

| Area | Test |
|---|---|
| v1 compatibility | With the replacement installed, the existing v1 tests (`test_discovery_ingestion_operational_pg.py`, storage-controller and statistics suites) pass unchanged; a v1 grant has no `screening_configs`; v1 plans, keys and revisions byte-identical; the v1 registration vocabulary unchanged. |
| Default OFF | A grant without `screening_configs` refuses a v3 child (`BATCH_ROW_TYPES`); a v3 plan with a grant listing a different `config_sha256` is refused. |
| Observation parent | A `LISTING_OBSERVATION_V1` capture can never be the parent of a v3 child, with and without the 034 substitutions applied (S1 admits v3 only over `LISTING_RECEIPT_V1`). |
| Configuration mismatch | Wrong `config_sha256` in plan vs grant vs checkpoint vs revision: refused by SQL (`batch_row`, `checkpoint`, `complete`). Wrong threshold or wrong `code_binding` is **not** detectable by SQL (it cannot recompute canonical JSON from `jsonb`); it is refused by the Python recomputation, the controller's trusted-memory comparison, and the grant's per-key binding when the resulting revision differs. |
| Duplicate execution | Replaying `batch_row` for the same record/config returns the existing child, never a second row; a conflicting duplicate raises `CONFLICTING_DUPLICATE`; a completed batch is read-only (`BATCH_ALREADY_COMPLETE`). |
| Malformed / stripped version fields | v3 checkpoint with `rule_version`, `routing_authority` or `count_assessment` removed, mislabelled, or admission outside the vocabulary: refused by `checkpoint`/`complete` SQL and by the controller; a v3 item with its fields stripped is ineligible at the identity gate, while a genuine historical v1 parent (contract exactly `listing-screen-v1`) still passes. |
| Authority expiry | Grant expiry mid-batch: further `claim`/`checkpoint`/`complete` raise `EXACT_AUTHORITY_BINDING_REQUIRED`; nothing half-written; no authority outlives its registration. |
| Failure cleanup | A worker killed after a child checkpoint: `ingestion_recover_abandoned`; resume re-checkpoints under the recovered fence and never duplicates; a failure inside `process_batch` raises the stop (`BATCH_SECURITY_IDENTITY_ACCOUNTING_OR_PERSISTENCE_FAILURE`) and launches no next slot; storage and item bounds hold. |
| Preservation | Before/after row comparison of every pre-existing row (capture, 5 batches, 24 v1 children, attempts): byte-identical, including checkpoints and outcomes; the control row changes only by the intended grant addition/invalidation. |
| Zero council requests | The v3 grant has `source_calls = 0`; the test asserts no `begin_source` is ever recorded; `begin_source`/`begin_write` on a SCREENING child is refused by `TASK_EFFECT` (`worker.sql:198`) and the allowance is `source_calls = 0`; the supervised worker has no source client; the job runs with outbound network disabled. Evidence is the grant, the attempt/phase rows and the absence of any socket. |
| Identity gate | An eligible v3 receipt reaches the **existing** pending-identity path in the controller test, and every existing check still applies. Assertions: `estimated_unit_count IS NULL`, `unit_facts = NOT_WRITTEN`, `unit_confirmation_status` pending, no Site link, no dwelling count, no approval, no qualified scheme. Non-eligible outcomes never reach it. (Test only; the demonstration does not use this path.) |
| History | The pagination test of section 4. |
| Derivation | The replacement equals the original with exactly the listed substitutions; undoing them reproduces `worker.sql` byte for byte; combined with the 034 list, each list is separately removable. |
| Retained evidence | The five committed evidence files reproduce `d5fa9e29…`, `d1ff23c0…`, `ad4e5982…` and the 24 child identities (Appendix A as a test), on Linux CI. |

Bounds: *proposed* (enforced by the tests above) — one extra CI step within the existing 90-180 s step timeouts. *Measured later in CI and reported*, not claimed here.

## 6. Release and disable plan (scope item 5)

Four **separately approvable** stages. None is authorised by this proposal. Namespace dates in file and authority names (`…20261023`) are identifiers; execution dates in this document come from audit timestamps (the window demonstration ran on **2026-10-20**).

| Stage | What happens | Production effect |
|---|---|---|
| **R1 Code integration** | Merge the Python, derivation module, tests, evidence copy and documentation. | None. The SQL function text exists only as a file; no connection is made. Production stays v1 (F6). |
| **R2 Function installation** | Owner-terminal ceremony installs the replacement `ingestion_worker_step` (and the policy successor of F11) as a new, named, verified inventory state, using the existing ceremony shape: exact inventory check before and after, rollback text, and **capability-absence readbacks** (no runtime login gains the owner, issuer, barrier or recovery memberships; the worker and broker still lack `INSERT/UPDATE/DELETE` on the tables; `EXECUTE` unchanged). | First production database change. The behaviour for v1 is unchanged; v3 is refused unless a grant lists `screening_configs`. No ledger row is created. **Separately held.** |
| **R3 Authority registration** | Owner registers **one** narrowly named, screening-only allowance (section 6.1). | **Ledger and control-row mutations, by design:** one grant added to the control row, and **5 batch items inserted** by the registration transaction (`operational_owner.py:407-410`). Nothing else. |
| **R4 Execution** | The finite owner run screens the 24 records source-free and then invalidates the authority with a committed readback. | **24 v3 children created** by the broker's `batch_row`; checkpoints/outcomes and attempts on the 5 batch items and 24 children; grant invalidated. |

**Smallest separately approvable production demonstration (R2 + R3 + R4, one approval each):** re-assess the 24 retained Bolton records with one frozen configuration, screening-only, from the verified full retained capture.

*Effects, kept apart:*

| | Registration (R3) | Execution (R4) |
|---|---|---|
| New `ingestion_work_items` | 5 (batch items) | 24 (v3 children) |
| `ingestion_work_attempts` | 0 | at most **58** (batch items `max_attempts = 2` ⇒ ≤ 10; children `max_attempts = 2` ⇒ ≤ 48); expected 29 (one claim each) |
| Control-row change | grant added | grant invalidated; no stop/generation change |
| Source calls / council requests | 0 | **0** |
| **Application-database writes** | **0** | **0** |
| Identities created | 0 | **0** (the nomination path is built and tested but not used) |
| Capture, 5 v1 batches, 24 v1 children | untouched | untouched (capture read `FOR SHARE` only) |

"Zero application writes" refers to the application database (`applications`, sites, intelligence tables). The intentional mutations are the ledger rows and control-row grant entries listed above; they are the audit trail of the demonstration, not a side effect.

### 6.1 The proposed allowance (for later review; nothing is registered or installed)

* **Name (proposed):** `AUTHORISE_INGESTION_BOLTON_SCREENING_V3_RETAINED_WINDOW_ONCE_<id>_SCREEN` — one name, screening-only, never reusable (a name already in `grants` can never be registered again).
* **Scope:** exactly Bolton `RECEIVED` 2026-09-28 to 2026-10-04 (the retained window); `source_calls = 0`, `writes = 0`; contracts `listing-batch-v1` and `listing-screen-v3`; `screening_configs = [one config_sha256]`; bindings for the 5 batch items, the 24 v3 children and the root capture binding (30 bindings, as in the reconciliation); `capture_sha256 = d5fa9e29…`.
* **Stops are preserved.** The allowance does not clear, reset or advance any stop or generation. The policy successor admits it only when the control row is in the stop state **read and digested at ceremony time**; this proposal does not assume the last recorded state (generation 3, last read on 2026-10-20) is current. If the state differs, the ceremony stops and a new proposal is needed.
* **Lifetime and deadline (proposed; the SQL ceiling of 24 h is not used).**
  * *Measured (retained final result, 2026-10-20):* each of the five batch slots took 9.2–10.7 s of database time (sum ≈ 51.4 s), 56–65 driver statements, 2 connections, 70–82 KB returned. v3 computation for 24 records is ~0.02 s locally.
  * *Enforced ceilings today:* a slot claim lease of 165 s and a per-slot supervised ceiling of 165 s (`batching.py`, `operational_runner.py`); batch claim leases 1-480 s (`worker.sql` claim).
  * *Proposed:* **execution deadline 600 s** for the whole screening run (≈ 11× the measured 51.4 s total, and below the 5 × 165 s = 825 s slot ceilings, so the tighter bound binds first); **cleanup and invalidation reserve 300 s**; **authority lifetime 900 s (15 minutes) from registration** (= deadline + reserve). A run that has not finished by the deadline stops with the barrier set; it is not extended. These are proposals to be confirmed by a rehearsal in the disposable PostgreSQL job, not measured production figures.

**Disabling v3 while preserving evidence.**

1. *Stop issuing:* do not register a v3 allowance; v3 is default-off in SQL (no `screening_configs`) and in Python (default registry is v1).
2. *Invalidate:* the existing invalidation with committed readback removes any registered allowance; the control state is read back unchanged.
3. *Roll back the function:* restore the previous reviewed `ingestion_worker_step` text (the derivation guarantees byte-identical restoration), with the same capability-absence readbacks. Existing v3 rows are inert data: v1 code never claims them (their contract is in no grant) and they are not deleted.
4. *Preserve:* no delete, no `supersedes`, no rewrite. v3 checkpoints, outcomes, attempts and the history query remain available read-only; the history query works with the v1-only function installed because it is a plain `SELECT`.

## 7. Residual risks

* **Two function replacements** (034 and v3): ordering and a single derivation are required (2.6).
* **Policy successor** for the stopped control state (F11) is a third database change in the chain; alternatives in D3.
* **Code-digest sensitivity**: any edit to the four bound modules changes new identities (safe; visible).
* **Bound modules are Windows/Linux byte-sensitive**: the digest normalises line endings; a test must prove it on both.
* **Retained evidence lives on a branch and in the owner's archive**: the five evidence files must be copied into `master` at the pinned hashes; the owner's 191-event archive is not in the repository; production row state is checked read-only at run time, not proved offline (5.1).
* **Checkpoint size**: a v3 checkpoint embeds the proposal and the v1 result; the 24 Bolton rows are small, but the 131,072-byte payload bound applies and must be tested at the largest proposal (8,192 characters).
* **Assessor content is not a planning fact**: v3 outcomes are routing, not counts or approvals. `ROUTE_COUNT_UNCONFIRMED` records stay non-executable questions.
* **History query** cost is bounded by the table bound, not by an index (4).
* **Householder/HMO over-routing** to count confirmation is existing assessor behaviour.

## 8. Keep outside

Automatic document retrieval or parent resolution; the owner-review portal; general backlog processing, discovery checkpoints, overlap rules, scheduling; search or display; changes to counting rules, buyer matching or retention; a general allowance-policy redesign. Investigation requirements remain explicitly non-executable (`executable: false`, `executor: NONE`).

## 9. Decisions, directions recorded, and the smallest implementation scope

### 9.1 Design directions recorded (Product Owner, for finalising this proposal; not approval to implement)

1. **v3 first.** Compatible with specification 034 but not bundled with sparse-observation implementation. The v3 slice explicitly **refuses observation parents** (S1 admits v3 only over `LISTING_RECEIPT_V1`). If both change `ingestion_worker_step`, the later one is derived from the earlier with its own substitution list; the sites are disjoint (2.6).
2. **Code binding.** A digest of the code that produces the saved assessment, including its embedded v1 result, with the dependency-coverage and Windows/Linux tests of section 3.
3. **Stops preserved.** One narrowly named, screening-only allowance for later review (6.1). No stop is cleared or reset, no policy is installed, and the last recorded state is not assumed current.
4. **Demonstration scope.** The 24 retained Bolton records only; zero council requests, zero application writes, zero identities; the capture and all earlier assessments preserved.
5. **History.** No history scan in assessment execution; bounded read-only pagination (section 4).
6. **Evidence.** The demonstration uses the verified full retained capture (5.1); projected or synthetic records only supplement tests.
7. **Installation.** The existing owner-terminal ceremony with exact inventory checks, rollback and capability-absence readbacks (R2). Separately held.

### 9.2 Evidence reconciliation: result

Every link reproduced offline (5.1): archive file hash, capture checkpoint digest, capture key, the 24 record digests (equal to the v1 children's revisions) and the registered bindings digest. **No blocker to binding the demonstration to the retained capture.** Remaining, non-blocking gaps: the owner's 191-event archive is not in the repository; the evidence lives on a branch and must be copied into `master` at the pinned hashes; production row state is not provable offline and is checked read-only at run time against `d5fa9e29…`.

### 9.3 Decisions that remain before implementation

* **D3 (stop-state route).** Approve a mechanical **policy v6** successor that admits exactly the allowance of 6.1 only when the stop state read at ceremony time matches the reviewed digest (v6 must also change the exception-key cap exemption, the name lists in both policy functions, the stop-digest branch and the owner's inventory set), **or** defer. This proposal does not clear or change any stop.
* **D7 (installation).** Who runs R2, and the exact rollback text; to be written with the implementation PR.
* **D8 (lifetime and deadline).** Confirm the proposed 600 s execution deadline, 300 s cleanup reserve and 900 s authority lifetime after a rehearsal in the disposable job.
* **D9 (evidence copy).** Approve copying the five retained evidence files into `master` at the pinned hashes in the implementation PR (public planning data, no secrets).

### 9.4 Smallest concrete implementation scope ready for approval

One implementation PR (R1 only; nothing installed, registered or run), containing exactly:

1. `ScreeningRule` code binding, `digest_probe`, and the closure / pinned-digest / line-ending tests (section 3).
2. The `link_related=False` production option and the paginated read-only history function with its PostgreSQL tests (section 4).
3. The mechanical derivation module for the replacement `ingestion_worker_step` (sites S1-S5, default OFF, observation parents refused) with its byte-reversibility tests; the SQL text is **not installed**.
4. The `SQLLedger.batch_row`, `batch_plans(..., screening=)` and owner `register(..., screening=)` v3 options (default v1, byte-identical v1 output).
5. The controller `assess_retained` function and the version-aware nomination gates (tested, unused in the demonstration).
6. The five retained evidence files copied at the pinned hashes, `retained-capture-reconciliation.json`, and the Appendix A reproduction as a test.
7. The disposable-PostgreSQL acceptance suite of 5.3 as one additional CI step.

Out of that PR: the policy v6 text beyond a reviewable draft, any installation, any registration, any run. Each of R2, R3 and R4 is a separate later approval.

Nothing here authorises implementation, merge, SQL installation, grants, stop changes, registration, execution, council requests, live re-screening, application writes, deployment or Stage advancement.

## Appendix A. Offline reproduction of the retained-capture binding

Needs only the committed evidence files and the repository checkout; it touches no database or network. `item` is copied verbatim from `operational_owner.item` because that module imports the Linux-only `resource` module. Run from a checkout in which the evidence directory exists at the path in `E`.

```python
import json, hashlib
from datetime import date
from app.ingestion.ledger import digest, DEFAULT_LIMITS
from app.ingestion.batching import batch_plans
from app.ingestion.idox_adapter import IdoxListingContract
from verification.discovery.idox_window import WindowConfig

E = 'docs/design/ingestion-operational-execution-bolton-window-demonstration-20261023/'
raw = open(E + 'capture/source.json', 'rb').read(); source = json.loads(raw)
assert hashlib.sha256(raw).hexdigest() == digest(source) == '5525be5a6b5fc3fdfac43849bc502cd05c0c9023da1440627b975672fe55013a'
events = [json.loads(l) for l in open(E + 'completed/events.jsonl', encoding='utf-8') if l.strip()]
outer = next(e for e in events if e['event'] == 'source_supervisor_observed')['payload']['actual']
CON = 'bolton-received-idox-coordinator-v1'
contract = IdoxListingContract(CON, WindowConfig('bolton', 'RECEIVED', date(2026, 9, 28), date(2026, 10, 4), 0),
                               '1833eb7349dda9b1dceb0924abd7380b2f24e591e13ad34ec37dd8e4763df3f2')
receipt = contract.project(source, outer, dict(DEFAULT_LIMITS, requests=10, bytes=3000000, rows=60, pages=6), source_bytes_limit=512 * 1024)
receipt.pop('window')
receipt['durable_archive'] = dict(commit='3587e2778720f56a9510b33c7bbce7584f6be59d', path=E + 'capture/source.json',
                                  sha256=digest(source), bytes=len(raw), readback_verified=True)
assert digest(receipt) == 'd5fa9e29bdd51afbf36772e9b08880af6811a8cec771a3335bad0095801445ee'      # capture checkpoint

def item(identity, *, dependencies=(), checkpoint=None, limits=None, max_attempts=2):      # == operational_owner.item
    return dict(identity, key=digest(identity), dependencies=list(dependencies), priority=50, eligible_at=0, state='QUEUED', reason=None,
                next_action='CLAIM_WHEN_AUTHORISED', limits=limits or DEFAULT_LIMITS, authority=None, attempt_count=0, max_attempts=max_attempts,
                fence=0, owner=None, lease_until=None, phase='IDLE', checkpoint=checkpoint, outcome=None)

scope = dict(kind='DISCOVERY_SCOPE', council='bolton', start='2026-09-28', end='2026-10-04', semantics='RECEIVED')
manifest = '8fb79d78db499a4f5f622ae20debba6397451f242ae0028514246d3234358e0c'
root = item(dict(subject=scope, task='DISCOVERY', contract=CON, revision=manifest), max_attempts=1, limits=dict(DEFAULT_LIMITS, requests=10, bytes=3000000, rows=60, pages=6))
assert root['key'] == 'd1ff23c04af746a5219e7c109255db0310d2a006c732bcac4f66f126b0240545'      # capture key
children = [item(dict(subject=dict(kind='APPLICATION', council='bolton', reference=r['reference']), task='SCREENING',
                      contract='listing-screen-v1', revision=digest(r)), dependencies=[root['key']]) for r in receipt['records']]
batches = [item({k: p[k] for k in ('subject', 'task', 'contract', 'revision')}, dependencies=p['dependencies'], checkpoint=p['checkpoint'])
           for p in batch_plans(root['key'], receipt)]
bindings = {x['key']: {k: x[k] for k in ('subject', 'task', 'contract', 'revision')}
            for x in [*batches, item(dict(subject=scope, task='DISCOVERY', contract=CON, revision=manifest)), *children]}
assert len(bindings) == 30 and digest(bindings) == 'ad4e598267d2104a6d2e0d2321087d84ac6313270f58a2411b3100e66762445f'
print('reconciled: archive, checkpoint, capture key, 24 record digests, 5 batches, 30 registered bindings')
```
