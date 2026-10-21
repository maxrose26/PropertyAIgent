# Connecting screening rule v3: bounded offline integration proposal

Status: **proposal for review. Nothing here is implemented or authorised** (no implementation, merge, production activation, database change, historical re-screening, council request, workflow dispatch, deployment or Stage advancement). Inspected at master `d0e172d882fa411d6d4ea5356cd518badbc1746b` (source inspection, not a production readback). Builds on specifications [032](../../../specifications/032-stage4-stable-credential-pipeline.md), [033](../../../specifications/033-verified-records-under-unknown-window-completeness.md), [035](../../../specifications/035-residential-count-and-categorisation.md) (Phase A merged) and [036](../../../specifications/036-owner-scheme-review-and-verified-corrections.md). 034 (ledger admission for observations) remains an unmerged proposal (PR 164). It creates no competing architecture: the existing WorkItem/WorkAttempt ledger, screening checkpoints, observation history and the legacy investigation stages are reused.

## 1. The current path (what exists)

| Step | Where | Fact |
|---|---|---|
| Capture a window | `Coordinator.idox_source` -> `LISTING_RECEIPT_V1` (`COUNT_RECONCILED` only) | A partial `LISTING_OBSERVATION_V1` is separate and never a capture (`capture_once` refuses it) |
| Plan screening | `batching.batch_plans` -> `listing-batch-v1` items, 5 rows each | Child identity is `digest(subject, task='SCREENING', contract='listing-screen-v1', revision=digest(record))` |
| Create children | production: `SQLLedger.batch_row` -> SQL worker op `batch_row`; offline/generic: `Ledger.enqueue` / `Coordinator._materialize` | |
| Screen | `Coordinator.screening` (coordinator.py:207) calls `screen_row(record)` = **v1 only**, writes the result as the item checkpoint and finishes with the **v1 disposition** as outcome | Retention is already "never lost": every result is `retained=True`, immutable once COMPLETE |
| Gate to identity | three v1 disposition gates: `Coordinator.new_identity` (coordinator.py:308-310), `new_identity.execute` (new_identity.py:38), `operational_controller.execute` (recomputes `screen_row(r)` and tests the disposition, ~line 319-321) | Only `SUPPORTED_PROCESSING_PRIORITY` / `RELATED_APPLICATION_FOLLOW_THROUGH` proceed |
| Identity, not scheme | `new_identity.execute` -> `discovery_admission.admit_identity`: identity-only `Application`, `unit_confirmation_status='discovery_pending'`, `unit_facts NOT_WRITTEN`; `stage_link_sites` skips pending rows | A screening outcome never writes a count, a Site link or a scheme |
| Per-window completeness | `discovery_contract.completed_through(previous, windows, council, date_semantics)` (pure; tested; **not persisted or fed from the ledger anywhere**) | Contiguous COMPLETE windows only; never leaps a gap; mixed council/semantics raises |
| Record history | `observation_history.append` (pure projection: UNCHANGED / NORMAL_UPDATE / CONFLICT, identity = council + reference) | |
| Investigation (legacy, `Application` rows only) | `run_weekly.stage_fetch_missing_parents` (parent permission of reserved matters), `stage_confirm_units` (form then statement for "residential, no count"), `stage_documents` / `stage_evidence_refresh` / `stage_extraction` | Not reachable from a ledger-held identity without an `Application` row |
| Ledger task vocabulary | `ledger.TASKS = {DISCOVERY, LISTING_METADATA, SCREENING, FACTUAL_REFRESH}` | `FACTUAL_REFRESH` = detail page for status/decision facts only (`INITIAL_STATUS_ONLY` scope) |

## 2. Precise gaps

1. **Rule selection is hard-coded to v1.** The screening contract string `listing-screen-v1` is pinned in `coordinator.py` (lines 111, 209), `sql_ledger.py` (48, 63) **and inside the installed SQL worker function** (`docs/design/ingestion-operational-20261016/worker.sql`: the `batch_row` checks at lines 160-164 and 189-195 and `enqueue_child` at 181-195). The generic `Ledger` accepts any contract string (1-100 chars); the production restricted path does not.
2. **Owner grants pin the outcome vocabulary.** `operational_owner.py:399` registers `completion_outcomes['SCREENING']` = the v1 dispositions (+ `SCREENED`, `ALREADY_KNOWN`, `INSUFFICIENT_EVIDENCE`). v3 outcomes (the eight admission values) are not in any grant.
3. **One assessment per identity.** Because contract and revision are in the item key and a COMPLETE item is immutable, a retained record already screened under v1 cannot also hold a v3 assessment in the same item.
4. **No re-screen operation for a completed capture.** SQL `enqueue_child` needs the parent in an active claim holding `LISTING_RECEIPT_V1`; `batch_row` needs an in-progress batch plan. Neither can create children for an already-COMPLETE capture.
5. **A recorded investigation requirement is not an executable task.** v3 already records *why* (`RESERVED_MATTERS_WITHOUT_STATED_COUNT`, `MIXED_USE_WITHOUT_STATED_RESIDENTIAL_COUNT`, `RESIDENTIAL_WITHOUT_STATED_COUNT`, `AMBIGUOUS_PER_GROUP_COUNT`, `COUNT_WORDING_NOT_PARSED`, `MULTIPLE_PROPOSED_DWELLING_COUNTS`, `STUDENT_ACCOMMODATION_IN_MIXED_SCHEME`, parent context on `RETAIN_RELATED_TO_PARENT`). **There is no ledger task type for parent-reference resolution or targeted document extraction**, and the SQL worker only accepts the four tasks (and Bolton only, line 70).
6. **No persisted per-(council, date basis) discovery checkpoint.** `completed_through` exists but nothing derives windows from ledger captures or lists outstanding gaps.
7. **Consumers still read the v1 `disposition`.** `routing_of()` exists and fails closed, but no consumer uses it.

## 3. Selection, storage and routing

**Selection.** A run selects v3 only by *registering it*: `Coordinator(..., screening_rules={...})` with a default registry containing v1 only. v3 is registered explicitly, per run, as `{'listing-screen-v3': (RULE_V3, threshold)}` where the threshold is passed in (never read ambiently) and recorded. The *contract string is the selector*: children enqueued under `listing-screen-v3` are screened by v3; children under `listing-screen-v1` by v1. Nothing else selects v3; an unregistered contract raises `SCREENING_CONTRACT_NOT_REGISTERED`. Contract-per-rule (not a flag in the payload) is recommended because the contract is already part of the item key, the owner grant's `contracts` list and every existing check, so selection, identity and authority move together.

**Storage (all in existing fields).**
- Item identity: `subject` (council + reference), `task=SCREENING`, `contract=listing-screen-v3`, `revision=digest(record)` (unchanged definition), dependency = the immutable capture key.
- Checkpoint = the screening result (existing): `rule_version`, `routing_authority`, `count_assessment` (counts, category, role, parent context, admission, reason, records, headline), `count_assessment_threshold`, `source_url`, `source_record_id`, `source_sha256`, `proposal`, `application_type`. **Add** to the checkpoint: `assessment_sha256 = digest(count_assessment)`, `record_sha256 = revision`, `capture_key`, `capture_sha256`, `supersedes_assessments` (see section 5). These bind the assessment to its exact evidence; no new column.
- Outcome (existing field): `routing_of(result)[1]`, i.e. the v3 admission string. v1 items keep the disposition outcome.

**Consumers.** One helper in `listing_screening`: `identity_admission_eligible(result)` built on `routing_of()`, returning false on any `ValueError`. Gates call it, never `result['disposition']`:

| `routing_of` authority / outcome | Progression |
|---|---|
| `disposition` (v1) | unchanged: `SUPPORTED_PROCESSING_PRIORITY`, `RELATED_APPLICATION_FOLLOW_THROUGH` -> identity gate |
| `count_assessment` / `ADMIT_SCHEME` | eligible for the existing identity gate (pending identity only) |
| `ADMIT_FOR_ASSESSMENT` (qualified maximum, conflict) | eligible for a pending identity so the evidence is held for investigation (**decision D2**) |
| `ROUTE_COUNT_UNCONFIRMED` | retained + recorded investigation requirement; **no identity yet** |
| `RETAIN_RELATED_TO_PARENT` | retained with parent context; never admits alone; progress only through its parent |
| `RETAIN_BELOW_THRESHOLD`, `RETAIN_NOT_RESIDENTIAL_SUPPLY`, `RETAIN_WATCHLIST`, `RETAIN_UNUSABLE_PROPOSAL` | retained, no effect; below-threshold reassessed only by a new recorded assessment (035 section 7) |
A screening outcome **alone never bypasses database-admission requirements**: the eligible outcomes still pass the unchanged `new_identity.execute` / `admit_identity` path (B2 hand-off, pending status, `unit_facts NOT_WRITTEN`). Promotion to `confirmed_qualifying` and `estimated_unit_count` remain 035 Phase B and are untouched.

## 4. Uncertain applications and investigation

- **Preserved, never dropped.** `ROUTE_COUNT_UNCONFIRMED` and reserved matters without a count are retained like every result (immutable checkpoint) with `parent_context` (reference, relation `PURSUANT_TO`, parent figure only as context).
- **Parent count never becomes a phase count.** The assessor already refuses it (reserved-matters examples E28 and the new tests). The proposal adds a projection test: no field of a derived requirement or any report copies `parent_context.context_count` into a proposed or approved total.
- **Recorded requirement (read-side, no storage).** `screening_projection.investigation_requirements(results)` maps reason codes to requirement kinds and states what can execute today:

| Requirement | Raised by | Executable today? |
|---|---|---|
| `PARENT_REFERENCE_RESOLUTION` | reserved matters, `PURSUANT_TO` reference | **Only for an `Application` row** via legacy `stage_fetch_missing_parents`; **no ledger task** |
| `DETAIL_PAGE_TEXT` (fuller proposal / application type) | unusable or truncated proposal; ambiguous wording | Partly: `FACTUAL_REFRESH` retrieves the detail page, but only status/decision facts are verified; text is not captured as a count record |
| `COUNT_CONFIRMATION_FORM_OR_STATEMENT` | residential, no stated count | **Only for an `Application` row** via legacy `stage_confirm_units`; no ledger task |
| `TARGETED_DOCUMENT_EXTRACTION` (decision notice, approved-plans schedule, form total) | conflicts, qualified maximums, approvals | Legacy `stage_documents` / `stage_extraction` only after admission; no per-record decision-notice extraction exists (035 Phase B2) |
| `PHASE_SCOPE_EVIDENCE` / `NON_OVERLAP_OR_MEMBERSHIP` | per-phase counts with unresolved overlap | none: evidence only, or an owner assessment (035 D10) |
**Missing capability, stated plainly:** a ledger-resident, executable investigation task (parent resolution, document extraction) does not exist. It needs a new task kind, SQL worker support, grants/privileges and source authority: **Phase B and live authority**, not this slice.
- **Specification 036 boundary preserved.** The owner review workspace consumes these immutable v3 assessments and requirements and records its own decisions (036 section 8) as separate records; nothing here writes a correction, creates a pending Application for display, or implements the portal.

## 5. New applications and backlog

- **Discovery progress is separate from screening progress.** Discovery progress = the state of `DISCOVERY_SCOPE` items; screening progress = `SCREENING` children. Neither advances the other, and a screening result never changes a window.
- **Checkpoint per (council, date basis), derived not stored.** `screening_projection.discovery_checkpoints(items)` projects COMPLETE `LISTING_RECEIPT_V1` captures (a `COUNT_RECONCILED`, non-observation kind only) into `WindowEvidence` and reuses `completed_through(...)` per `(council, semantics in {RECEIVED, VALIDATED})`; mixed bases raise as today. Because it is a read-side projection over immutable items, it can be rebuilt and cannot be edited (the same pattern as 034's history).
- **Gaps stay outstanding.** Any window whose item is failed, blocked, `UNSUPPORTED_CONTRACT`, `INCOMPLETE` or `UNKNOWN` is listed as an outstanding gap and **blocks `completed_through` at its start**; a newer COMPLETE window never hides it. A `LISTING_OBSERVATION_V1` never contributes (asserted by test: `window_claim = NONE`).
- **Ongoing discovery from verified coverage, with overlap (decision D3).** The next window starts at `completed_through - overlap` and ends at the day before the run. Recommend **7 days** ongoing (029's 28 days applies to the initial acceptance only). Duplicates are handled by identity, not by trimming: an unchanged record in the overlap yields the identical child key (same subject, contract, `digest(record)`), so `enqueue` returns the existing item; a changed record yields a new revision and so a new assessment, and `observation_history` classifies UNCHANGED / NORMAL_UPDATE / CONFLICT.
- **Re-screening retained records is not retrieving undiscovered history.** (a) *Re-screen*: no source request; new v3 items on retained captures. (b) *Undiscovered history*: new `DISCOVERY_SCOPE` windows before the earliest checkpoint; needs council authority, source requests and discovery grants; out of scope here.
- **Versioned, linked, never overwritten.** A v3 assessment of an already-screened record is a **new item** (different contract so different key) with the same subject and revision. It carries `supersedes_assessments=[prior item key + rule_version]` in its checkpoint; the v1 item is untouched. The projection `assessment_versions(subject, revision)` lists every assessment oldest-first with its rule version and routing authority.

## 6. Recommended first slice (offline, existing storage only)

**Slice 1: "contract-selected v3 on the generic ledger, routing consumers and read-side projections."** Everything below runs against the disposable SQLite ledger and the existing fixtures; **no SQL function, grant, schema, privilege or live authority changes**.

1. `Coordinator`: optional `screening_rules` registry (default v1 only); `screening()` selects the rule from the item's contract, adds the binding fields of section 3, finishes with `routing_of(result)[1]`. v1 behaviour byte-identical.
2. `listing_screening`: `identity_admission_eligible(result)` and the reason-code -> investigation-requirement table (data only).
3. New `app/ingestion/screening_projection.py` (pure, read-only): `assessment_versions`, `investigation_requirements`, `discovery_checkpoints` (+ gaps), `rescreen_report` (local recomputation of retained captures under v3, labelled as such, writing nothing).
4. Migrate the two **application-level** gates (`Coordinator.new_identity`, `new_identity.execute`) to `identity_admission_eligible`. `operational_controller.py` (reviewed production-path file) is left unchanged in this slice and migrated with the Phase B slice. Several consumed packages' MANIFESTs pin these files' bytes; the slice's CI must show those package tests unaffected (Phase A changed `listing_screening.py` without breaking them), otherwise reconcile pins by the archive precedent used for `unit_filter.py`.

**Acceptance tests (offline).**
- *Compatibility:* default registry gives v1 results byte-identical to master (extend the V1 golden digest through the Coordinator); existing screening/batching/new-identity suites pass; 62 examples unchanged.
- *Selection:* v3 contract unregistered -> denied; registered -> v3 result with `routing_authority='count_assessment'`, binding fields present, outcome == admission, `assessment_sha256` correct; v1 and v3 children of the same record have different keys and both persist.
- *Routing:* each of the eight admissions maps as in the section 3 table; a v3 result is never routed by its informational `disposition` (E17-style case: disposition `SUPPORTED...`, v3 `RETAIN_NOT_RESIDENTIAL_SUPPLY` -> no identity); tampered/unknown outcomes fail closed.
- *No bypass:* eligible outcomes reach only the unchanged `admit_identity` (pending, no counts, no Site link); `ROUTE`/`RETAIN_*` never create an identity.
- *Uncertain:* reserved matters without a count retain `parent_context` and raise `PARENT_REFERENCE_RESOLUTION`; the requirement and every report never copy the parent figure into a phase total.
- *Backlog:* re-screening a retained capture creates new items linked to the originals and leaves the originals byte-identical; a second pass is idempotent.
- *Discovery:* contiguous COMPLETE windows advance `completed_through`; a failed window blocks it and appears as a gap; an observation never advances it; two councils/bases keep separate checkpoints; the overlap re-presents a record without a duplicate child and a changed record yields one new assessment.
- *Disable/rollback:* removing the registration (or running with the default) makes v3 unusable and leaves every v3 item immutable and readable; consumers keep working for both versions through `routing_of`; nothing needs a database rollback because nothing is written outside existing fields.

**Demonstration data.** The 62 agreed examples; disposable captures built with the repository's own page generator; and the 24-record Bolton window fixture, which currently exists only on the unmerged PR 163 branch (decision D4) while the original archive stays with the owner.

## 7. What needs Phase B, schema, privileges or live authority (not in the slice)

| Item | Why |
|---|---|
| Production restricted path for v3 children | the `listing-screen-v1` pin inside `ingestion_worker_step` (batch_row, enqueue_child) must accept the v3 contract: an exact function replacement with disposable PostgreSQL tests (same shape as 034's) |
| Grants | `contracts` and `completion_outcomes['SCREENING']` must list `listing-screen-v3` and the v3 admission values: a new owner registration mode, with live authority |
| Persisted re-screen of a completed capture | a new SQL op (or exact-task path) because `enqueue_child`/`batch_row` cannot create children for a COMPLETE capture |
| Executable investigation tasks | new task kinds, worker support, source authority, privileges |
| A persisted (rather than derived) discovery checkpoint | only if the projection proves insufficient; new storage |
| Application promotion, count storage, search/display | 035 Phase B/C |
| `operational_controller.py` gate migration | reviewed production-path file |
Search UI, buyer matching, scheduling and a replacement queue are not touched.

## 8. Decisions genuinely required

- **D1** Contract-per-rule (`listing-screen-v3`) as the selector (recommended) versus an in-payload flag.
- **D2** Do `ADMIT_FOR_ASSESSMENT` results create a *pending identity* (recommended: yes, to hold their evidence) or only a retained requirement?
- **D3** Ongoing discovery overlap (recommended 7 days) and whether `VALIDATED` and `RECEIVED` are checkpointed independently (recommended: yes, never merged).
- **D4** How the 24-record Bolton fixture lands as test data (cherry-pick the fixture file from PR 163 only, or keep the examples and synthetic captures).
- **D5** Whether the Phase B slice that follows is the SQL contract acceptance (production path) or the executable investigation task kinds first (recommended: SQL contract acceptance, since nothing else can persist v3 results).
