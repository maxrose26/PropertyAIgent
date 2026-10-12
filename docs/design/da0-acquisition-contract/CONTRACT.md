# DA0 planning-data acquisition contract

Version: `da0-contract-v1`. Status: proposed offline contract; no execution, acceptance, merge or operational authority. Base: architecture merge `ab5dffea684706c953fdf759d5d7ac33f0da5c5d` (PR #47). The 211-reference bootstrap asset is retained, qualified evidence, not the permanent discovery universe. The 23 other factual candidates, ten allocation-review applications, unresolved attribution and strategic subjects remain separate.

## Purpose and implementation boundary

Continuously turn fragmented land, planning and development evidence into hidden, ranked acquisition opportunities matched to buyer strategy, then provide intelligence to assess and act. Acquisition supplies traceable facts to existing intelligence. DA0 neither ranks opportunities nor evaluates buyers. Owned acquisition remains the foundation; competitors are benchmarks, not foundational dependencies.

`verification/da0/contracts.py` contains small pure executable examples, not a production adapter framework. Tests use retained research and explicitly synthetic factual examples. No transport, parser integration, database table, launch policy, scheduler, new source or accepted-evidence store is implemented. Validation checks configuration and contract examples; it cannot certify actual source completeness, authority, DNS destination safety or rights.

## Registry and capability admission

The closed fixture record has these fields. Strings must not carry secret configuration or private evidence.

| Fields | Contract |
|---|---|
| manifest_version, source_id, research_source_id | Version and stable identity; link to the accepted research inventory |
| council, fact_domain | Exact admission scope; a research candidate domain is not a claim that the source actually covers it |
| source_name, source_type, platform_family, publisher | Source description and protocol family; no family-wide certification |
| authority_class | Claim-specific candidate authority, independently assessed at admission |
| priority | Preferred/fallback transport preference only after eligibility; null while unproved |
| adapter_type | Design identifier, not an installed runnable adapter |
| admission | Exact public URLs, zero followed redirects, required future DNS/IP validation; origin and route derived from the URL rather than arbitrary caller input |
| capabilities | All ten declarations, eight independent gate states and evidence IDs per capability |
| freshness | Expected cadence and uncertainty, not successful-verification proof |
| rights | Licence qualification including dataset/third-party exclusions |
| operational_state, execution_authority | Non-operational fixture state; authority always null in DA0 |
| versions | Schema, adapter and council configuration provenance |
| last_capability_review, limitations | Review date and unresolved constraints; review time is not source freshness |

Capabilities: KNOWN_REFERENCE_STATUS, KNOWN_REFERENCE_DECISION, KNOWN_REFERENCE_DECISION_DATE, NEW_APPLICATION_DISCOVERY, CHANGE_DISCOVERY, BULK_SNAPSHOT, RELATED_APPLICATION_DISCOVERY, DOCUMENT_METADATA, DOCUMENT_RETRIEVAL and ALLOCATION_DATA. Each is UNPROVED, UNSUPPORTED or SUPPORTED. UNSUPPORTED in a fixture denotes a deliberately unavailable configured operation, not proof that the underlying council never publishes that data. All current evidence gates remain UNKNOWN. No source is operationally supported.

Admission is **source + council + fact domain + capability**. Each requires IDENTITY, AUTHORITY, COMPLETENESS, FRESHNESS_LATENCY, RIGHTS, RESOURCE_BOUNDING, SCHEMA_STABILITY and PROVENANCE to PASS with reviewable evidence IDs. A pass for discovery cannot establish authoritative status. A pass is not activation: a pinned implementation, bounded live proof and separate operational authority are still required. `eligible` illustrates evidence qualification only; `invoke_offline_operation` always returns UNSUPPORTED and never executes.

Lifecycle states are retained because they distinguish proposed work, tested design, tested live capability, activation and three different impediments. PROPOSED → OFFLINE_PROVED → LIVE_CANARY_PROVED → ACTIVE requires new authority at the live and activation gates. DEGRADED retains accepted evidence after operating failure; UNSUPPORTED means no admitted implementation; DEFERRED means a deliberate work hold. Recovery requires requalification of the affected capability. Lifecycle is evaluated per admitted tuple; a source-level state is only a summary and must not activate other capabilities. DA0 fixtures can only be PROPOSED, DEFERRED or UNSUPPORTED.

## Raw evidence and field states

Canonical envelope: manifest version; run/source identity; provider/type/claim-specific authority; council; raw and canonical reference; source record ID if available; sanitised public provenance URL; retrieval outcome; complete-for-claim scope/controls; retrieved_at; separately qualified record_created_at, record_updated_at and dataset_updated_at; adapter/parser/config/source-schema/code versions; request count, received bytes, elapsed time and budget outcome.

Every factual/timestamp field carries state, value where permitted, provenance locator and SOURCE_LITERAL or DERIVED_QUALIFIED meaning. States are PRESENT_VALUE, PRESENT_BLANK, NOT_PRESENT, CONFLICTING and UNPARSEABLE. Only PRESENT_VALUE carries an accepted string in the examples. Blank is not omitted. A null alone certifies nothing. Conflicting or unparseable evidence blocks acceptance of that claim. Source timestamps retain their documented meaning and timezone; unknown meaning is not freshness proof. Retrieval time never substitutes for source observation/publication time. Production code revision must be pinned; example versions are explicitly synthetic.

Per-capability projections are closed. Status permits reference, source_status_raw, source_decision_raw and source_decision_date. Discovery may separately admit application_type_raw, proposal_raw, approved location IDs and relationship evidence only when necessary to its reviewed capability. Those extended projections require a separate schema/test gate before implementation; the executable DA0 envelope deliberately demonstrates status only. No free-form extras, documents or personal identities are admitted by default.

Status completion requires exact independently evidenced reference and explicit unambiguous literal status, successful complete-enough retrieval and all budgets passing. Decision/date may be NOT_PRESENT without preventing literal-status verification; that does not verify their absence or certify a decision/date claim. For a claimed issued decision or material transition requiring date, the supporting decision/date must independently pass their claim requirements. Dates are parsed using an admitted source-specific rule; parse failure is UNPARSEABLE, never an invented date.

The sequence is raw fact → qualification → separately accepted semantics → materiality → intelligence. Deposited may be a verified literal while semantic_state remains UNKNOWN_UNMAPPED. No canonical classifier fallback is authoritative evidence. Unknown-label change is a source fact change requiring review, not automatically material. Committee recommendation/resolution and issued permission are different claims.

## Minimal adapter interface and platform reuse

Future operations are `acquire_exact(admitted_claim, budget)`, `enumerate_window(admitted_scope, checkpoint, budget)` and `fetch_snapshot(admitted_scope, budget)`. An admitted claim includes exact source/council/domain/capability, identity and required factual fields. Scope pins filters/window and schema; checkpoints bind the same scope and accepted predecessor. Unsupported methods return UNSUPPORTED explicitly. No method may activate capabilities, broaden scope, follow documents or call models.

Keep transport, parsing, evidence qualification and semantic interpretation distinct. Share bounded retrieval, admission, pagination accounting, cleanup and outcomes only where protocols actually match. Idox and Arcus council configurations own origin/path, labels, reference rules, date semantics, document system, rate evidence and supported capabilities. Same family is not same behaviour. Existing generic scrapers and classifiers are untouched. Oldham remains deferred/unproved; existing Bolton literal tooling remains preserved and separately gated.

## Same-fact precedence and conflict

Compare only the same council, exact application identity, factual field and field meaning. Parent/child records are not the same claim. Reject identity mismatch before precedence. Require qualified source success and completeness for the particular field. Trace publisher and upstream lineage: copied datasets are not independent corroboration. Compare fact-specific authority and actual source observation/publication age where evidenced. Unknown age cannot establish newer truth. A transport preference or later retrieval alone never wins.

If eligible sources agree, retain both provenance paths without falsely counting copied lineage as corroboration. If values disagree, preserve SOURCE_CONFLICT_DETECTED and hold automatic acceptance of the disputed material fact. A later, demonstrably superseding primary decision can be proposed for acceptance only through a separately authorised claim-specific resolution with lineage and supporting evidence. DA0's `compare_fact` intentionally performs conservative equality/conflict classification, not automated winner selection. No automatic precedence engine is implemented. Tests prohibit newest/tier selection and parent/child certification.

## Snapshot, hashes and source events

A complete baseline must identify source, council/capability, scope and filters; schema/parser/config; stable unique keys; all pages/parts and terminal proof; expected versus observed counts where available; no overflow/truncation; deterministic minimal projection; provenance and retrieval completion. SOURCE_GUARANTEED consistency needs a documented version/snapshot guarantee. RECONCILED_COMPLETE needs recorded reconciliation evidence, window/change-cursor handling and count/key/terminal checks. Neither label can be self-certified by HTTP success. If consistency cannot be proved, the capture is partial/qualified, not an accepted removal baseline. Multi-request HTTP is never described as a database transaction.

The pure Snapshot example assumes these proof booleans/qualification were independently established; it validates keys/counts/projection, not a live pagination chain. A production adapter must supply page manifests (ordinal, boundary keys, counts, duplicate/overlap checks, terminal marker and source version). Partial captures cannot establish removals or complete discovery. Compared snapshots must share source/scope/schema/parser/config. Any drift requires a controlled rebaseline and review; no mass factual changes are inferred from a parser upgrade.

Separate transport/content digest (bounded original bytes, not retained in normal audit), qualified raw factual digest and accepted semantic/material digest. The latter requires accepted semantic rules and is not implemented by DA0. Raw digest excludes retrieval/processing time and ordering; significant reference formatting is preserved unless an independently approved council rule exists. Geometry is excluded from the status example; future geometry canonicalisation must be separately specified. Field state remains in the raw digest. Absence in a compatible complete snapshot creates a **source-record removal candidate**, never planning withdrawal or opportunity removal.

Events: APPLICATION_DISCOVERED, APPLICATION_SOURCE_CHANGED, STATUS_CHANGED, DECISION_CHANGED, DECISION_DATE_CHANGED, SOURCE_RECORD_REMOVED, RELATIONSHIP_DISCOVERED, SOURCE_CONFLICT_DETECTED. They are data events, not buyer-fit or opportunity events. Deterministic identity includes manifest/source/key/kind, old/new qualified hash and the accepted predecessor checkpoint/event. Replay from the same predecessor yields the same ID; A→B→A→B yields three IDs because predecessor advances. Checkpoints advance only after separately authorised acceptance of the entire bounded unit; incomplete units cannot advance them. No random run ID as sole deduplication key. DA0 computes identities without storage or event publication.

## Failure, documents, security and metrics

Failures preserve last accepted facts and last successful verification; record failed attempt separately. No clearing, missing→zero, fabricated unchanged or opportunity suppression. Reuse B2.1 qualification: show stored evidence and successful-verification date, with refresh unavailable/required where appropriate. DEGRADED/UNSUPPORTED/DEFERRED prevent capability scheduling, not commercial exclusion. Acceptance, timestamp advancement, lifecycle/invalidation and reprocessing remain separately gated B2 work.

Document metadata and retrieval are separate capabilities and authority. New application/decision/S106/report/condition or material change may propose later selective work, never trigger an automatic download. B3/AH, counts, control and document interpretation are separate contracts.

Future adapter safety must bind reviewed exact origins/routes/identities; reject userinfo, unsafe ports, private/local/metadata IPv4/IPv6 and DNS rebinding by validating the actual destination on every connection and redirect. Exact URL fixture checks are configuration tests, not an implemented network sandbox. Default redirects zero; any exception requires explicit route admission and accounting. Enforce actual streamed/decompressed bytes, per-response/run/request/retry/page/entity bounds, concurrency/per-host rate policy, independent deadlines, cancellation and cleanup. No arbitrary URLs, assets, document paths or external calls.

Bulk handling requires compressed **and expanded** byte/member limits, no path traversal/symlinks, bounded parsing and no executable content. XML forbids DTD/external entities; JSON rejects duplicate keys/non-finite values/unknown schema; CSV uses explicit encoding/columns/row bounds and never evaluates formula cells (escape spreadsheet-facing output). Malformed or schema-drifted captures fail closed. Untrusted HTML is data only. Provenance is assembled from admitted configuration and observed exact identity, not untrusted page claims. Diagnostics omit HTML, field values outside accepted projection, cookies/tokens/headers, private narrative and credentials. These are DA1 implementation gates; DA0 does not claim their transport enforcement is proved.

Future metrics: retrieval attempts/complete/failures; records received/discovered/changed; source conflicts; verified versus accepted changes; source age/latency with timestamp meaning; requests/bytes/runtime; parser/schema failures; downstream opportunity changes only from later accepted consumers. Label council/source/capability/version and bounded outcome; avoid personal data and high-cardinality raw text. No dashboard or monitoring activation.

## Forty research fixtures and DA1 decision

`verification/da0/registry_fixtures.json` maps every accepted SOURCE_MATRIX research ID into the non-operational contract. Rights/freshness qualifications are carried forward. Research is not live capability proof. All eight eligibility gates remain UNKNOWN. The ten councils cover 211 retained references (Bolton 16, Bury 5, Manchester 38, Oldham 20, Rochdale 20, Salford 32, Stockport 35, Tameside 7, Trafford 19, Wigan 19). No reference is certified by conversion to a fixture.

**DA1 BLOCKED.** No accepted structured/bulk/change source has all entry evidence. Ranked investigation candidates below use existing research only; no new source request was made.

| Rank/source | Why relevant | Exact missing evidence before DA1 |
|---|---|---|
| 1 Wigan official annual ArcGIS planning-application layers | Official machine-readable application inventory; most promising genuine discovery source | Complete supported export/keyset retrieval; stable exact-reference coverage; field dictionary/decision semantics; reliable refresh/publication timestamps; dataset-specific commercial rights including third-party qualification; demonstrated bounded completeness. Catalogue updates and six preview records do not prove these. Prior REST/export failures remain unresolved. |
| 2 Salford official application CSV | Application-level bulk history, potentially useful discovery | Current supported complete CSV retrieval; scope/current count/stable keys; actual cadence and timestamp meaning; current field schema; commercial rights qualification, especially OS/UPRN restrictions. Historical catalogue dates do not establish currentness. |
| 3 Manchester official SHLAA structured resource | Selected permitted housing context could support narrowly scoped discovery | Current complete supported extract; exact application identity; scope and omissions; cadence; dataset rights and semantics. SHLAA is not the complete planning application universe and cannot be represented as such. |

Bolton historic bulk and Bury 2014 CSV lack current complete-feed proof; weekly lists/committee publications require complete machine-readable retrieval, identities, cadence and rights proof. National Planning Data has no demonstrated populated application/status universe for this requirement. Existing direct summaries are freshness fallbacks, not a substitute for the required first discovery-capable DA1. Request a bounded evidence-qualification decision for Wigan first, or defer DA1; no ingestion is authorised by this contract.

## Gated roadmap

Each stage needs a new REVIEW authority. Ordering keeps source completeness ahead of diff and discovery; independent freshness assets are reusable without making 211 references the opportunity universe.

| Stage | Product outcome / technical scope | Dependencies | Tests and GO gate | Explicit deferrals |
|---|---|---|---|---|
| DA0 contracts | Evidence quality: registry, qualification, events and offline examples | Merged architecture and retained research | Contract/fixture tests; exact remote review; no operational authority | All live acquisition and persistence |
| DA1 first structured/bulk/change source | Hidden discovery foundation: one bounded admitted adapter | DA0 plus source access/rights/identity/cadence proof | Exact schema/keys/limits/privacy; supported complete capture; blocked until evidence resolved | Portals as substitution, other councils, scheduling |
| DA2 prove complete discovery source | Trustworthy discovery coverage: baseline and repeatable completeness | DA1 | Terminal/count/keys/scope/version/retrieval reconciliation; authorised tiny live proof | Discovery completeness claims beyond proved scope |
| DA3 snapshot/change engine | Monitoring: deterministic source diffs and replay | Accepted DA2 baselines | Partial removal rejection; rebaseline; A→B→A→B; idempotent checkpoints | Automatic factual persistence/opportunity decisions |
| DA4 known-reference freshness | Evidence quality for existing buyer facts | DA0 and separately admitted exact-source capability, 211 qualified asset | Literal/semantic/field states/materiality; separate B2 acceptance authority | Unsupported councils, 23 other domains, AI |
| DA5 new-application discovery | Hidden opportunities beyond existing references | DA2–3 and scoped identity reconciliation | Complete scope, duplicates and new-state qualification; no invented facts | Ranking/new matcher and speculative identity merging |
| DA6 relationship/site reconciliation | Explainable phased/site evidence for buyer matching | DA5 and accepted existing identities | Parent/child isolation, rejected edges, uncertainty; separate identity approval | Stand Golf/component decomposition without its own authority |
| DA7 selective documents | Deeper investment intelligence | Document capability, rights/budgets and qualified triggers | No default downloads; provenance, privacy and safe parsers | B3/AH/control remediation and model processing |
| DA8 opportunity-trigger integration | Buyer matching and proactive explanations | Accepted factual changes and existing evaluator/consumer contracts | Selective invalidation, unchanged-time control, buyer isolation | Second matcher and indiscriminate summary regeneration |
| DA9 repeatable council expansion | National discovery/monitoring | Proven per-capability recipe and rights/completeness tests | Council-specific gates, portability and unsupported semantics | Universal coverage as prerequisite and giant generic scraper |

The foundation enables existing differentiated reasoning, timing, buyer relevance and future investment analysis; it does not reproduce a generic planning-search product. Any expansion must demonstrate one of those outcomes before engineering approval.

## Review and authority boundary

Review the exact remotely published candidate, including tests and hosted offline result. DA0 GO is a recommendation for contract acceptance, not merge or activation. Separate DA1 BLOCKED remains valid even if DA0 passes. Next decision: accept/merge DA0 separately and choose a bounded Wigan source-evidence qualification exercise, or retain the DA1 hold. No source client, portal access, production write/schema, evaluator observation, model, document acquisition, scheduling, deployment or live canary follows automatically.
