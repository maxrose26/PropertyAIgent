# DA1 Wigan entry-gate qualification

Decision: **DA1 WIGAN ENTRY GATE — BLOCKED**. Evidence gathered 12 October 2026. This is source qualification only; no adapter, ingestion, activation or factual acceptance is implemented. DA0 is binding at master `da06dae001cbef9af6c0f38776e1fa4adfb022b3`. Its contracts and registry remain unchanged. `EVIDENCE.json` is a non-operational assessment ledger, not a replacement source contract.

## A–D: exact source, publisher, retrieval and completeness

The assessed DA0 records are `wigan-2021-2030`, `wigan-2025` and `wigan-2026`. All catalogue records identify Wigan Metropolitan Borough Council and the same ArcGIS item `1a3ea7fae81b46b68aa36ed2401f1161`. The annual catalogues identify sublayers 6 (2025) and 9 (2026). No replacement source was admitted.

Official references inspected:

- [Service catalogue](https://www.data.gov.uk/dataset/2fcf1013-970c-4329-8231-fe32b25c4890/planning-applications-2021-to-20303)
- [2025 catalogue](https://www.data.gov.uk/dataset/3221d41e-1877-4f87-8f58-36d2e6d85d0c/planning-applications-20252)
- [2026 catalogue](https://www.data.gov.uk/dataset/5d14984a-0d15-454a-932b-5b5a27db12c0/planning-applications-2026)
- [Council open-data policy](https://www.wigan.gov.uk/Council/DataProtection-FOI-Stats/Open-Data.aspx)

The advertised MapServer is `https://maps.wigan.gov.uk/arcgis/rest/services/Planning_BuildingControl/Planning_Applications_2021_to_2030/MapServer`. The catalogues advertise ArcGIS REST and Hub exports, including annual CSV/GeoJSON/KML/Shapefile. Advertised formats are not successful retrieval evidence.

The research tool reported 403 when fetching the service and layers 6/9; no schema was obtained. The annual CSV link redirected to an ArcGIS Hub download target inaccessible through that tool. One additional ordinary GET of the exact published service with `f=pjson`, five-second timeout, 256 KiB read ceiling, no followed redirects and no retry returned URLError after 5.01 seconds; no response/schema was accepted. The actual HTTP status/body bytes of that failed native attempt are unknown. It is not classified as a confirmed source timeout or outage. The item JSON, harvested HTML metadata and Hub pages yielded no usable additional evidence. An additional Hub about-page probe is recorded as unproductive research, not a replacement source or proposed runtime route.

**Stop at the completeness gate:** no total count, object-ID field, maxRecordCount, ordering support, pagination capability, selected-field support, geometry suppression or terminal-page proof was obtained. No full dataset or six-row preview is treated as complete. Research-tool access failures do not establish universal source unavailability and therefore support BLOCKED, not NO-GO.

## E–F: exact identity and field semantics

| Field | Classification | Evidence and unresolved meaning |
|---|---|---|
| REFVAL | PARTIALLY_CONFIRMED | Accepted retained previews contained reference-shaped values; official field definition, uniqueness and stability across refreshes are unproved |
| KEYVAL | UNKNOWN | No readable official schema/dictionary; cannot assume a stable portal/application key |
| OBJECTID or equivalent | UNKNOWN | Actual identity field/type and refresh stability unavailable; an ArcGIS protocol convention is not this dataset's metadata |
| DECSN, DATEDECISN | UNKNOWN | Retained preview columns were present and blank; official outcome/date meanings and absent-value conventions unproved |
| APPLDECTYP, DATEAPPDEC | UNKNOWN | Names do not establish application type, decision type or operative date semantics |
| Status, application/validation dates, created/modified timestamps | UNKNOWN | No current official schema/definitions or qualifying records retrieved |

A future source key must bind council/source plus exact canonical application reference, with official reference-format rules and an independently documented source key. Preserve leading zeros and significant punctuation. OBJECTID cannot be a cross-refresh key until stability is proved. Multiple geometries/records per application require explicitly documented deduplication, never first-row selection. No fuzzy address matching is proposed.

Blank decision never implies pending. Missing schema/records are unknown, not NOT_PRESENT source facts. Historical preview observations remain historical and do not prove the current schema. No literal facts or semantic states were verified in this exercise.

## G–H: freshness and rights

Change capability: **UNKNOWN**. No updated-since cursor, edit timestamps, source snapshot/version token, annual replacement rule, retention/removal semantics or refresh SLA was established. Catalogue modification dates are publication metadata: service 21 October 2025, 2025 catalogue 18 December 2025, 2026 catalogue 11 October 2026. The annual resource link dates differ (2025: 21 October 2025; 2026: 21 January 2026). None certifies individual application freshness. Application year, decision year and layer membership rules remain unproved.

Rights classification: **RIGHTS_UNRESOLVED**. Wigan's official policy expressly permits commercial/research reuse of its OGL-published data/maps. This is useful council-level evidence. The exact catalogues still show Licence: Not set, and item-level rights/exclusions were not readable. Dataset-specific linkage, required attribution and third-party restrictions must be resolved for the retained factual projection and derived intelligence. Public accessibility and the catalogue site's general OGL footer are not dataset rights clearance. No council contact was made.

## I: proposed future resource envelope

This is a conditional fail-closed design, not measured throughput or approved execution. Start only with one proved annual layer (2026/9) after entry evidence closes; do not silently claim 2021–2030 coverage. The 19-reference control spans several application years and therefore needs separately proved appropriate layers.

| Limit | Proposed initial design |
|---|---|
| Records | Exact independently obtained count C; refuse if unknown or C > 2,000 |
| Data partitions | 100 records maximum each; ceil(C/100), at most 20 plus one terminal check |
| Requests | At most 25 including admitted metadata/count/terminal controls; concurrency 1, at least one second between requests |
| Schema | 65,536 received bytes, at most 64 declared fields; reviewed explicit factual projection only |
| Data response | 512,000 actual received and expanded bytes maximum |
| Run bytes | 5,000,000 actual received and expanded bytes maximum, including failures |
| Time | Connection 3 seconds, read 8 seconds; independent run deadline 120 seconds |
| Redirects/retries | Zero followed redirects; zero automatic retries during first completeness proof |
| Compression/geometry | Request uncompressed JSON where supported; otherwise both wire/expanded bounds. No archive ingestion. returnGeometry=false must be demonstrated |

These small ceilings are administrative rejection bounds, not estimates of Wigan's actual size. They are not sufficient evidence for RESOURCE_BOUNDING PASS: exact count/schema and supported bounded retrieval must be established first. If the source exceeds the envelope, return for review rather than raising it. No bulk ZIP is proposed. No executable client is supplied.

## J–K: 19-reference control and discovery value

The accepted L1 artifact (`371acef3e2a075d8fb7a8579540f87f5dc72c985`, stage26b-l1-selection-v1) contains exactly 19 Wigan references. The retained observation date is 9 October 2026. Its qualified provenance and SHA-256 are recorded without exporting private inputs. All 19 appear individually in EVIDENCE.json:

FOUND_EXACT 0; NOT_FOUND 0; AMBIGUOUS 0; FORMAT_DIFFERENCE 0; **UNTESTED 19**.

No 19 portal requests or individual structured queries were made. Current field availability remains UNTESTED. There is no observed structured mismatch. A reference dated 2020 is not automatically absent from a 2021–2030 layer: the layer's inclusion/date rule is unknown. A later full quality sample would use explicit minimal fields and one bounded exact-reference batch per required proved layer, accounting for duplicates and coverage. No fuzzy matching or status repair follows.

The boundary source remains promising for discovery because it is advertised as annual machine-readable planning-application data. Whether it covers newly submitted applications, only mapped boundaries, decisions, historical subsets or subsequent edits is unproved. Two complete stable snapshots could support additions/changes only after identity, scope, freshness and consistency are qualified. A static historical subset would fail DA1's intended discovery outcome; current evidence does not establish that it is static or unsuitable.

## L: DA0 snapshot-completeness proposal

For WIGAN SNAPSHOT COMPLETE require the exact admitted source/layer, reviewed schema fingerprint and version, explicit scope/year/filter semantics and minimal selected fields. Actual ID field and exact reference are mandatory discovery inputs; decision/date/type/timestamps are optional only under independently established field meanings. Geometry/free text/applicants/documents are excluded.

Require a supported deterministic keyset or ID-manifest method; stable ordered partitions with first/last keys, count, duplicate/overlap checks, terminal proof and no exceededTransferLimit/truncation. Counts must reconcile with the source's independently obtained total where supplied. Capture source schema/version before and after; a matching count alone does not prove consistent content. SOURCE_GUARANTEED requires a documented pinned version; otherwise RECONCILED_COMPLETE requires a genuinely sufficient documented reconciliation method. Neither was proved here. Without consistent-capture proof, retain QUALIFIED/PARTIAL and prohibit removals/complete discovery claims.

Use DA0's minimal field-state projection and deterministic qualified factual hash, retaining field states and significant reference formatting while excluding retrieval timestamps, ordering and irrelevant geometry. Schema/parser/config changes require rebaseline. Record URL, retrieval times, budgets, page controls and source timestamp meanings. Missing pages, duplicate keys, count mismatch, malformed payload, schema drift or overflow invalidate the capture. No snapshot/diff engine is implemented or new Wigan-specific contract introduced.

## M–N: security and independent review

Future admission must use DA0 exact-origin/route and resolved-public-address controls. Pagination/filter parameters must be constructed from the reviewed scope, not caller URLs. Reject redirects, private/metadata destinations, geometry, unknown schema, duplicate JSON keys and non-finite data; enforce wire/expanded bytes and independent deadlines, rate limits and cleanup. Treat provenance as admitted configuration plus observed identity, not arbitrary source assertions. Exact portal/documents/discovery routes are excluded. No credentials, production database, model or persistence are required.

No live route containment, DNS-rebinding protection or complete snapshot is claimed proved by this assessment. Offline tests verify the ledger against DA0's registry/gates, retained sample provenance/identity, UNKNOWN/UNTESTED distinctions and partial-removal prohibition. The independently reviewed exact remote candidate and hosted test identities are recorded in the review PR/report, rather than guessed in this document.

## O–T: decision, fallback, product value and boundaries

**DA1 WIGAN ENTRY GATE — BLOCKED.** All eight capability-specific DA0 eligibility gates remain UNKNOWN. Confirmed publisher metadata alone cannot establish claim-specific authority or complete discovery. No PASS recommendation or DA1 implementation proposal is justified.

Salford's existing `salford-historical-csv` record should receive the next **bounded qualification slice**, not ingestion. Existing evidence describes an official CSV since April 2014, an old catalogue and a previous retrieval timeout. The reduced open projection has stronger stated OGL qualification than UPRN-enriched data, but current retrieval, schema, identity, completeness and cadence remain unproved. Exclude restricted UPRN enrichment. No new Salford request or full qualification was performed. First stop rule: cannot retrieve a supported current schema/count/scope → BLOCKED; do not engineer access workarounds.

The commercial priority is current, repeatable discovery, not making a council pass. Keep Wigan as an unresolved candidate and avoid spending implementation effort on an unproved feed. This preserves the owned-data strategy and the separate known-freshness/discovery loops; Bolton direct-summary is not substituted. Further Wigan work needs a new evidence/rights clarification decision. No council contact, portal scraping, ingestion, adapter, database/schema change, source activation, scheduling, documents, AI, opportunity ranking change, Bolton/Oldham/Arcus work or deployment occurred.
