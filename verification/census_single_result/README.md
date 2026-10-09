# Single-result dependency census — OFFLINE DESIGN, not execution authority

Base: 183570e0c940d28b51b9f05a5dbf47f56dff37b2. No application code changes. L1/current census remain HOLD.

## Purpose and limits

One evidence SELECT returns one result set through the existing SQL Editor's last-non-empty-result contract. The full wrapper is BEGIN; SET TRANSACTION REPEATABLE READ, READ ONLY; two SET LOCAL timeouts; SELECT; ROLLBACK. Six SQL statements, one evidence SELECT. There is no database client, credential handling, production executor, model call or council request in this package.

The query captures a structured relational boundary, not exact buyer replay. `retrieval_state=COMPLETE` does **not** mean `dependency_census_state=COMPLETE`: dependency state is always QUALIFIED. Complex reconstruction/consumer attribution must use existing accepted application logic later and explicitly carry omissions; this package never chooses an operative application or classifies relationships by proximity/recency.

## Format and SQL

Four fixed columns: record_type TEXT; row_kind DATA/CONTROL; record_id TEXT (NULL for controls); payload JSONB. Each DATA payload is one explicitly projected entity row, not EAV. Sixteen section controls exist even when a section has zero rows; one __capture control carries version/mode, statement timestamp, snapshot, backend PID, read-only/isolation/timeouts, counts and conservative byte budget. `capture.py --output generated` produces exact full/canary SQL and exact-column manifests. No operator edits SQL.

Sixteen bounded MATERIALIZED retrieval CTEs use simple IN/semi-joins and explicit predicates. UNION ALL emits individual records and section counts; only count/sum and small row/control JSON objects are built. No nested evidence aggregation, document hashing, regex parsing, full text, fuzzy resolver, AI prose or evaluator recreation. One safety/budget cross join joins two guaranteed one-row aggregates; no evidence cross-products/recursion/OFFSET.

Scope is GM, workspace 1 active buyers/mandates, non-excluded sites plus exact scoped allocation-linked sites. Related tables are fetched independently. Company IDs are limited to selected structured ControlRelationship.company_id values; entity-level ApplicantIntelligence is limited to those company IDs. Name-only/fuzzy identity association is omitted and explicitly qualified, never interpreted as absence. Titles are presence booleans only. Documents are metadata only. Application proposals and public planning locations are retained as already-approved factual scope inputs; applicant/contact addresses are excluded. Allocation summary headline/overview are only presence booleans, never bodies.

## Bounds and completeness

Full entity bounds remain the approved V1 bounds. Canary bounds: documents 300; applications/intelligence 100 each; control/allocation relationships 50 each; others at most 20 (lower original ceilings retained). Each retrieval LIMIT is ceiling+1; ordering is the stable primary key. This is a bounded full-scope retrieval, **not pagination**. If the cap is exceeded, no terminal/full-scope claim is made.

Server budget: 6 * sum(UTF8 row_to_json row bytes + 2) + 4096 <= 10,000,000. The factor reserves JSON ASCII escaping and CSV quote expansion; 4096 reserves bounded capture/error metadata and framing. On any row/byte overflow, DATA and section rows are suppressed; only bounded capture-error metadata returns. The assembler rejects it. Actual received file bytes must also be <=10 MB. No automatic guard relaxation is permitted.

Assembler rejects missing/duplicate controls, count mismatches, duplicate entity keys, unknown schema/mode/sections, unexpected projected columns, unsafe transaction metadata, timeout/runtime/byte overflow, UI truncation and unresolved buyer/workspace relationships. Cross-scope context FKs are recorded UNRESOLVED_OUTSIDE_CAPTURE_SCOPE, never erased. DATA uniqueness is entity+PK; natural duplicate references are not assumed unique. All 16 sections must reconcile. Partial input never creates a qualified-capture output file. Dependency direct/context/discovery values can be preserved with the existing vocabulary; the assembler does not invent attribution.

The SQL Editor row limit must allow the **whole** result. A truncated export fails count checks. No assumption that the default 100-row UI limit is adequate. UI row-limit availability, one-result export, native wrapper/rollback behavior and schema/performance are canary acceptance gates, not tested facts.

## Canary

Six retained site IDs: 25 Southlink; 28 Failsworth; 254 Trafford missing-verification; 58 Stockport missing-verification; 96 phase isolation; 281 retained related/discovery example (VAR/349651/22). These are lookup/cohort aids, not source-authority assignments. Canary allocations include exact cohort links plus the smallest GM summary-bearing allocation to exercise summary metadata. Any linked site outside the cohort remains explicitly unresolved; no whole-universe expansion.

Oct8 sizing: 18 applications, 8 intelligence records, 191 document metadata records, 6 control rows for the six sites. Current counts are unknown. Zero-row sections still have completeness controls; the canary cannot prove join behavior on a section that happens to be empty. Its success requires all controls, exact safety settings, no overflow, <=5-second evidence SELECT, <=60-second request, <=10-MB received file, complete export and successful assembler. It does not approve full census or L1.

## Full sizing / feasibility

Retained Oct8 known input sections total approximately 6,052 entity rows and 2,987,014 compact UTF8 bytes before current summary/company metadata, controls and extra projection flags. These are sizing observations, not certified current counts. The conservative encoding guard exceeds 17.9 MB for that retained projection. Therefore **full capture is NO-GO under the current conservative guard**. A canary may establish transport/performance; it cannot justify silently lowering the safety factor. A narrower full projection or evidenced encoding bound needs separate review.

Primary keys are declared in retained ORM models. Application.reference has an ORM index declaration. Deployed indexes and FK access paths are UNVERIFIED. Simple bounded table/semi-join scans may dominate SQL time; no EXPLAIN/native timings exist. Duration cannot be predicted credibly from row counts alone. A canary must measure it; no timeout increase is proposed.

## Omitted inputs and bootstrap risk

Document-derived phasing/certificate/control, AH-note semantics, original developer/applicant-name equality, fuzzy company resolution, canonical narrative context hashes and source excerpt markers are absent. These may affect opportunity membership/qualification or exact narrative eligibility. Structural application relationships and successful status timestamps remain retrievable, but an exact buyer-facing dependency reduction cannot yet be claimed. Summary prompt versions/status/context fingerprints/presence can establish version metadata; token-free canonical hash recomputation is not promised. Every omission stays qualified. No summary regeneration nominations follow.

## Offline verification

pglast==8.5 (PostgreSQL grammar parser) parses full/canary SELECT and six-statement wrappers. AST checks enforce one SelectStmt, approved tables/functions and no unrestricted star/DML. Retained ORM manifest columns reconcile. Tests use synthetic records and retained sizing; not source truth, native PostgreSQL, transport or production evidence. No PostgreSQL binaries/container were available. Transaction cancellation/rollback/session closure are pending live preflight; not simulated as proven database semantics.

Run from this directory with Python 3.12 and pglast 8.5:
`python -m unittest discover -s . -v`
Generate: `python capture.py --output generated`
After separately authorised capture: `python capture.py --assemble downloaded.csv --elapsed-seconds MEASURED_SECONDS --output evidence`
The measured duration is supplied from the bounded operator audit, not inferred from file timestamps. Accepted output is atomically written locally only after validation.

## Authority / next decision

Qualified GO FOR SINGLE-RESULT CANARY only, after review. No production execution in this task. Full census and L1 remain HOLD. A canary failure returns failure metadata; no speculative retry, alternate transport, credentials, schema/index change, timeout increase or external calls follow. No production changes, models, operations, ranking or decomposition.
