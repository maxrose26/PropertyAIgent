# Bounded end-to-end connection: implementation scope and test mapping

Baseline `f4c34379019181b73d0564ee2eaefd56b4c77f8f` (tree `36952e15a1a1d464743ce083498f04280bcf848e`). Offline implementation, disposable PostgreSQL, local fixtures, isolated test publisher.
Stage 4 remains OPEN. No merge, no live activation, no production stop change, no production-database access, no council contact, no controller-venv installation, no registration.
Prepared-cache mode stays off; local memory-pressure and eviction tests stay paused. Latency stays UNKNOWN where evidence is insufficient. Original misses are never erased; no received-date bound, no final-day read policy.

## Chain demonstrated, for both Idox and Arcus
non-empty local listing -> validated retained audit -> durable archive with verified readback -> batching and frozen v3 screening -> deterministic exact nominee -> fresh local detail verification -> existing shared identity admission and B2 -> committed database readback.

## Findings that fix the design (checked in the baseline)
* `Coordinator.idox_source` is the only entry to archive/batching and it spends a `source_calls` unit; Arcus never archives. SQL `checkpoint` + `complete` need no source intent unless the grant is `capture_only` (`worker-step-v3.sql`, `checkpoint` branch); `completion_outcomes['DISCOVERY']` must list the outcome.
* `operational_controller._execute` is Idox-specific in four places: contract type, `cfg.start.isoformat()`, `receipt['resources']`/`segments`, `r['provenance']['body_sha256']`.
* `v3_admission.factual_binding` and `execute_retained_v3` refuse Arcus by construction.
* `batching.batch_plans` hard-codes `'semantics':'RECEIVED'`; the Idox receipt drops the window, so no date basis survives. SQL `batch_row` requires batch subject == root subject, so a VALIDATED council (Stockport) could not batch at all.
* `ListingContract.validate` calls the Arcus audit validator without the execution budget and bounds `supervisor_seconds` at 45 s.
* The Arcus detail projector `_qualify_row` already returns the `{observation, audit, failure}` packet `NewIdentityContract.projector` needs.
* The shared B2 handoff requires the council row's hostname to equal the target `source_url` hostname.
* The existing admission test inserts the root capture as COMPLETE with a synthetic archive; that substitution is exactly what this slice must not repeat.

## Implementation (only the missing connections)
| ID | Change | Files |
|---|---|---|
| S1 | Receipt `date_semantics`; batch identity takes semantics from the receipt (historical receipts without the key keep `RECEIVED`) | `app/ingestion/idox_adapter.py`, `app/ingestion/batching.py` |
| S2 | `Coordinator.retained_capture`: verify archive readback, project, checkpoint, finish; no listing request, no `source_calls` spend, no replay, optional evidence label | `app/ingestion/coordinator.py` |
| S3 | `ArcusListingContract`: validated audit -> `LISTING_RECEIPT_V1` with `WindowEvidence`, per-record provenance, execution-budget pass-through, annotation-key handling; `ListingContract` gains an optional `execution_budget` | `app/ingestion/arcus_adapter.py`, `app/ingestion/coordinator.py` |
| S4 | Deterministic exact nominee derivation (pure; frozen v3 table; conflicting observations withheld) | `app/ingestion/nomination.py` |
| S5 | `_execute`/`execute_retained_v3`/`factual_binding` accept the two known families | `verification/ingestion_storage/operational_controller.py`, `v3_admission.py` |
| S6 | Narrow Arcus projector wrapper and factory over the existing `_qualify_row`/`_from_observed_row`/`_refresh_row` | `verification/ingestion_storage/new_identity_contract.py` |
| S7 | Minimal finite-manifest row selection (regenerate, hash-match, subset) | `verification/discovery/finite_acceptance.py` |
| S8 | Port-flexible disposable PostgreSQL world, isolated test publisher, supervised runner, CI job | `tests/e2e_*`, `.github/workflows/stage4-discovery-offline.yml` |
Not built: new writer, workflow framework, scheduler, exception-policy generalisation, recovery derivations, acceptance reporting, latency rules, live Arcus detail reader for unregistered references.

## Test mapping
| Requirement | Test | Layer |
|---|---|---|
| Date basis for all nine councils; Stockport regression | `test_e2e_connection_units.py::test_date_basis_nine_councils` | unit |
| Manifest selection | `...::test_manifest_selection_*` | unit |
| Retained capture: no listing request, no source spend, no replay | `...::test_retained_capture_*` | unit (in-memory ledger) |
| Archive / readback failure, tampered provenance | `...::test_archive_*`, `...::test_tampered_*` | unit |
| Arcus contract, budget pass-through, WindowEvidence | `...::test_arcus_contract_*` | unit |
| Deterministic nominee, frozen v3 table, conflicts withheld | `...::test_nominees_*` | unit |
| Arcus projector/factory, binding refusals | `...::test_arcus_factual_*` | unit |
| Eligible scheme and `ADMIT_FOR_ASSESSMENT`, both families, through restricted roles | `test_e2e_connection_pg.py::test_chain_eligible[idox|arcus]` | PostgreSQL |
| Unusable metadata (frozen outcomes), no detail call, no write | `...::test_unusable_metadata_*` | PostgreSQL |
| Known identity, competing delivery, conflicting observations | `...::test_known_*`, `test_race_*`, `test_conflicting_*` | PostgreSQL |
| Tampered provenance after capture, archive failure | `...::test_tampered_after_capture_*`, `test_archive_failure_*` | PostgreSQL |
| Uncertain commits (identity, B2, readback, lost ack, interrupt) | `...::test_uncertain_*` | PostgreSQL |
| Grant expiry, insufficient authority, set global stop | `...::test_authority_*` | PostgreSQL |
| Cancellation, accounting, connection and process closure | `...::test_cancellation_*`, `test_closure_*`, supervised runner | PostgreSQL + supervisor |
| No Site, document, opportunity or inferred-fact writes | write-set check after every PostgreSQL case | PostgreSQL |
Source-only fixture success is never reported as admission proof; synthetic contract tests qualify no council markup.

## Local-development note
Hosted CI (PostgreSQL 17) is the authority. Locally only PostgreSQL 16 is available, on a separate loopback port; the system cluster on 5432 is not touched.
