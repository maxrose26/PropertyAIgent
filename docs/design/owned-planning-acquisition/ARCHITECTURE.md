# PropertyAIgent owned planning-data acquisition — proposed architecture

Status: REVIEW candidate; documentation only. Research date: 12 October 2026.
Exact integration base: `6cce9244a4068002d7d8fd4e860b70159870f5d4`.
Authority: Product Owner owned-acquisition architecture decision, superseding immediate commercial supplier evaluation. No merge, implementation, source activation, production access, supplier/council contact or deployment authority.

## 1. Product objective and limits

Continuously turn fragmented land, planning and development evidence into hidden, ranked acquisition opportunities matched to buyer strategy, with the intelligence needed to assess and act on them. Own source selection, acquisition contracts, provenance and factual acceptance. Ownership does not require building every transport technology: standard HTTP/GIS libraries and existing adapters are reusable; a competitor's proprietary data is not the foundation proposed here.

Collection is a necessary foundation, not the differentiator. Budget collection by the buyer-relevant evidence it enables and independently assess discovery coverage. Do not build a national planning-search clone, universal crawler, data warehouse or generic evidence framework. Existing identities, matcher/family construction and Specification 028 semantics remain authoritative. Phase/component hypotheses do not authorise Stand Golf decomposition.

The historical 1,270 linked applications and accepted 211 direct status references are qualified bootstrap assets, not a current complete opportunity universe. Preserve 23 other factual candidates, 10 allocation review applications and unresolved subjects as separately gated queues. Never manufacture status dependencies to improve coverage.

## 2. Evidence and source map

`SOURCE_MATRIX.json` is the detailed, minimised research inventory. Every row records all requested capabilities; UNKNOWN is explicit. CONFIRMED means the particular documented observation is established, not that a collector is live-ready. Repository configurations are retained technical evidence, not new live portal tests. This bounded map is not an exhaustive census of all official resources.

| Council | Platform in accepted repository | Structured source evidence | Publication/change lead | Near-term disposition |
|---|---|---|---|---|
| Bolton (16 refs) | Idox | Historical 2015 CSV catalogue | Public portal/weekly lists; ModernGov committee | Direct summaries have demonstrated transport; corrected field contract still lacks successful live acceptance |
| Bury (5) | Idox + Anite documents | November 2014 CSV catalogue | Committee agenda includes delegated decisions; older weekly-list evidence | Publication supplement candidate; document adapter stays separate |
| Manchester (38) | Arcus/Salesforce | SHLAA selected housing sites, not full register | Published guidance describes weekly/monthly date searches; committee agendas | No supported structured status API established; older guidance must not prove current platform behaviour |
| Oldham (20) | Idox | No current full structured feed established | Official SCI describes weekly applications; committee index | Automated exact-reference status unsupported/unproved; access engineering deferred |
| Rochdale (20) | Arcus/Salesforce | No current full structured feed established | Historical publicity code describes weekly applications/decisions; committee index | Current feed endpoint/cadence unproved |
| Salford (32) | Arcus/Salesforce | Historical application CSV; current data/cadence unproved | Public-register date search described; planning-panel publication | No supported structured status API established |
| Stockport (35) | Idox, custom path | Constraints open data, not status register | Official weekly new-application list; planning/area committees | Prior 429 risk; no verified complete decision feed |
| Tameside (7) | Idox | No current application feed established | Official page describes weekly/monthly portal lists; ModernGov panels | Portal-generated lists are not independent API feeds |
| Trafford (19) | Idox | Official open-data repository; no application-status dataset identified | Official weekly/monthly register options; committee index access unproved | No demonstrated structured status feed |
| Wigan (19) | Idox + ArcGIS extract | Annual GIS/CSV layers; six partial preview records | Official weekly/monthly options; committee publication | Bulk access, semantics, completeness and latency blocked; no ingestion |

No published status API, authenticated/private Arcus API, RSS/Atom, webhook, updated-since cursor or comprehensive daily decision feed has been established for these ten councils in this research. UNKNOWN is not proof of absence. Weekly UI options do not establish anonymous machine access or complete updates. Committee lists cover selected cases; general council decision feeds are not necessarily planning decisions.

Evidence sources are linked in each matrix row. Key official sources:

- [National application catalogue](https://www.planning.data.gov.uk/dataset/planning-application), [status catalogue](https://www.planning.data.gov.uk/dataset/planning-application-status), [decision catalogue](https://www.planning.data.gov.uk/dataset/planning-decision): accepted zero production-record observations; schemas are not populated coverage.
- [Wigan 2026 catalogue](https://www.data.gov.uk/dataset/5d14984a-0d15-454a-932b-5b5a27db12c0/planning-applications-2026) and [Open Data policy](https://www.wigan.gov.uk/Council/DataProtection-FOI-Stats/Open-Data.aspx): official derived source, qualified commercial reuse with attribution; catalogue date is not record freshness.
- [Stockport weekly-list description](https://www.stockport.gov.uk/find-planning-applications), [Tameside list description](https://www.tameside.gov.uk/w/development-management-home-page), [Trafford list description](https://www.trafford.gov.uk/planning-and-building-control/step-by-step/search-and-comment-planning-applications/search-planning-application), [Wigan list description](https://www.wigan.gov.uk/Resident/Planning-and-Building-Control/Planning/Search-planning-applications.aspx).
- [Bury planning committee/delegated decisions example](https://councildecisions.bury.gov.uk/ieListDocuments.aspx?CId=134&MId=4221&Ver=4): evidence of a publication route, not a complete decision/change cursor.

## 3. Source registry and selection

Propose a configuration-backed registry first, beside existing `config/councils.yaml`, not a new database table now. Key: authority identity + fact domain + capability + source ID. Record publisher, source URLs/approved origins/routes, adapter version, platform/config version, exact lookup/list/delta/snapshot/document capabilities, identity/field mapping, authority/lineage, scope, licence/retention, cadence/latency qualification, paging contract, resource budgets, operational status and explicitly admitted fallback. Configuration `monitoring_enabled` is not proof production jobs are active.

Operational statuses: PROPOSED, OFFLINE_PROVED, LIVE_CANARY_PROVED, ACTIVE, DEGRADED, UNSUPPORTED, DEFERRED. ACTIVE requires separate launch authority; no source is made ACTIVE by this design. A raw-HTTP failure cannot automatically enable a browser or change authentication.

Preference order, after eligibility gates:

1. Official structured API with adequate exact identity, fact coverage and latency.
2. Official complete bulk extract/GIS with documented semantics and acceptable cadence.
3. Official application/decision publication feed for its evidenced claims.
4. Direct known application summary/detail source.
5. Bounded portal search only where necessary.

Gate selection on identity, fact-specific authority, completeness, successful retrieval, time qualification, licence and enforceable budgets BEFORE considering transport convenience. A newer issued-decision list may outrank an older GIS record; a committee resolution subject to S106 does not establish issued permission. No weighted freshness/commercial score. Select independently per fact and per loop; one council may use bulk for discovery and primary detail for acceptance.

## 4. Platform reuse

Reuse Idox identity/table parsing/navigation primitives and Arcus register/result/detail primitives where they satisfy the new contract. Current generic paths also discover/download documents and may select first matches; do not run unchanged for status-only verification. Arcus's existing encoded search URL is browser transport, not a published supported API. Do not reverse engineer private APIs.

Shared primitive owns URL admission, response/paging accounting, parsing, cleanup and outcome contracts. Council configuration owns exact origin/base path, supported modes, received-vs-validated date field, labels, document system, approved reference rules and observed limits. Stockport's custom base path/tab and rate delay, Bury's Anite documents and council-specific Arcus fields demonstrate why family membership is insufficient. Add a genuinely different adapter only when protocol/evidence requires it; no ten-council bespoke orchestrator.

## 5. Two loops with a common acquisition boundary

### A. Known-evidence freshness

Accepted direct dependency -> due factual claim -> admitted source/capability -> bounded acquisition -> field qualification -> exact identity -> semantic/material review -> separately authorised B2 atomic acceptance -> dependent consumer candidates. Begin with the qualified 211 references, not all 1,270. Unsupported sources remain explicit. Timestamp-only advancement is not a material change.

For every council, no verified complete change cursor currently exists: **REFERENCE POLLING REQUIRED for known status, unless a later proved decision/delta/snapshot source covers the exact claim**. This is a fallback requirement, not permission to poll or to call an unproved adapter.

### B. New-evidence/opportunity discovery

Admitted changed-since feed, weekly publication or complete snapshot -> new/changed source records -> deduplicated evidence candidates -> exact authority/reference identity -> accepted linking/reconciliation -> potential opportunity -> actual buyer matcher -> explanation/monitoring subject to later authority. Historical backfill is not current discovery. Related references are CONTEXT or DISCOVERY until operative-source attribution establishes DIRECT dependency.

Provisional discovery leads: Wigan complete bulk diff if blockers close; Stockport/Tameside/Trafford/Wigan published weekly-list paths if bounded completeness can be proved; Bolton list/committee path; Bury delegated/committee publication; Manchester/Salford current register date windows; Rochdale historical weekly-decision publication needs current endpoint confirmation; Oldham weekly publication only after separately approved capability, no new access engineering now. No lead is operationally certified.

Overlap date windows with deterministic deduplication to catch late publication/corrections. A received/validated date search does not discover later decisions on older applications. Decision feeds need separate completeness and correction coverage. Periodic known-reference checks may remain necessary even with discovery lists.

## 6. Minimum raw-evidence adapter contract

Design only; no new framework or runtime schema is implemented. Two narrow operations: `acquire_exact(admitted_claim, budget)` and `enumerate_window(admitted_scope, checkpoint, budget)` where capabilities permit. Separate `discover_document_metadata`/document retrieval; absence of a capability is UNSUPPORTED, never a silent substitute.

Envelope: manifest/adapter/config/code identity; run/source ID; source provider/type/authority; council identity; application reference as published and canonical comparison rule; source record ID; admitted/sanitised source URL; retrieved_at UTC; record_created_at, record_updated_at and dataset_updated_at with documented meaning/timezone and evidence states; retrieval outcome; scope/completeness controls; request/byte/time accounting; licence/lineage; source content/projection hash.

Facts: source_status_raw, source_decision_raw, source_decision_date, application_type_raw, proposal_raw, approved site/location IDs and relationship assertions **only when needed and authorised**. Status-only projection excludes proposal/parties/geometry/documents. Discovery may need proposal/type/location under its own minimisation contract. All fields optional in the envelope; required fields depend on the claim.

Each field carries PRESENT_VALUE, PRESENT_BLANK, NOT_PRESENT, CONFLICTING or UNPARSEABLE; original label/path and bounded provenance locator; transformation/parser identity; raw-vs-derived qualification. Date precision, timezone and parsing qualification are explicit. Null cannot alone prove authoritative absence. Errors carry safe category/field name, not raw HTML, tokens or arbitrary exception values.

Identity and explicit status are required for literal-status success. Decision/date can be independently evidenced; omitted values never become verified NULL. Bolton Deposited remains literal with UNKNOWN_UNMAPPED semantic state; global fallback cannot establish pending. Source raw facts -> field qualification -> accepted semantic mapping -> materiality -> intelligence. Unknown transitions remain review candidates, not automatic invalidation.

Retain accepted L1 failure outcomes and literal-status extensions. Failed attempts never advance successful verification. Successful acquisition for one field never certifies residential count, AH, control, parent/child or all documents.

## 7. Precedence and conflicts

Compare only evidence for the SAME exact subject/application/fact. Record primary application/register evidence, official extract, derived GIS, committee/decision publication, national aggregation and any future third party as distinct lineages. Apply fact-specific authority, publication/observation date, scope, completeness and successful identity controls; never choose solely by tier or newest retrieval.

Preserve contradictory observations and last accepted facts. SOURCE_CONFLICT_DETECTED blocks automatic acceptance of the disputed field. New retrieval of an old source is not newer evidence. A copied extract is not independent corroboration. Parent verification does not certify child or vice versa. Committee recommendation/resolution, delegated issued decision and appeal outcome retain distinct lifecycle meaning.

## 8. Snapshot and source events

Use source-scoped run manifests and minimise factual projections. Complete snapshot requires schema identity, scope/filters, unique stable keys, reconciled expected/result counts, all pages/export parts, no exceeded transfer limit, terminal paging and fixed deterministic ordering. Multi-request APIs may not provide one source snapshot: record consistency limitations and reconcile concurrent changes; never invent PostgreSQL-style consistency. Incomplete capture produces no accepted removal/change census and does not advance checkpoint.

Identity: council + full reference + source ID; source-native IDs retained as aliases, not sole global identity. Hash SHA-256 of canonical JSON with explicit field states, stable keys, schema/parser version and relevant factual values; exclude retrieval/processing/check timestamps from material hash. Separate transport/content hash, raw-fact hash and accepted semantic/material fingerprint. Preserve significant reference zeros/slashes/suffixes. Date/whitespace normalisation requires recorded deterministic rules.

Ignore ordering, geometry serialization noise and non-factual timestamps for status diffs. Parser/schema upgrades require controlled rebaseline/replay, not mass planning-change events. Compare against last complete compatible source snapshot. Disappearance emits SOURCE_RECORD_REMOVED qualification, not withdrawal, deletion of accepted evidence or proof no application exists. Confirm scope/access/deletion policy before consequences.

Source-event envelope: deterministic event ID from source/key/old-new hashes/event kind AND the accepted predecessor checkpoint/event identity (or independently stable source version). Replaying the same transition from the same predecessor keeps its ID; recurring A->B->A->B transitions must remain distinct. A random run ID alone is not the deduplication key. Include run/checkpoint, old/new field states and provenance, event/observation/source dates, qualification, schema/code identity. Kinds: APPLICATION_DISCOVERED, APPLICATION_SOURCE_CHANGED, STATUS_CHANGED, DECISION_CHANGED, DECISION_DATE_CHANGED, SOURCE_RECORD_REMOVED, RELATIONSHIP_DISCOVERED, SOURCE_CONFLICT_DETECTED. Coalesce overlapping field events without duplicate downstream acceptance; replay is idempotent. These are DATA events, not proof of acquisition availability or opportunity value.

## 9. Hidden-opportunity and document boundaries

New/changed evidence -> exact application identity -> existing site/family/subject reconciliation -> qualified scheme/phase facts -> opportunity hypothesis -> stored buyer mandate evaluation -> existing explainable ranking -> buyer explanation -> later monitoring. Do not implement new matching, component identities, availability claims or numerical ranking in this slice. Count-source provenance remains separate from status-source provenance.

Deterministic logic controls identity, fact states, source precedence, materiality, admission and accepted matching. Later AI may interpret authorised narrative evidence, hypothesise latent commercial patterns and explain qualified buyer relevance; it cannot invent facts, treat missing as zero, manufacture decisions or bypass identity. AI output stays a hypothesis/explanation with provenance and uncertainty. Acquisition decisions stay human.

Documents are separate: eligible new application, issued decision, committee report, S106 or material document signal -> selective metadata lookup -> exact document identity/hash -> bounded fetch -> separately authorised extraction/review. Status refresh never retrieves all documents. Committee resolution does not replace decision notice; AH/S106 tenure/count/control facts require their own future contracts. No B3 implementation or bulk narrative regeneration.

Other future evidence families (titles, companies, EPC, allocations, housing supply, brownfield, viability, progress and comparables) can share source IDs, timestamps/provenance and candidate events, but keep domain-specific authority/contracts. No research or implementation of those families here.

## 10. Storage, retention and cost

Prefer existing PostgreSQL/Supabase for canonical facts, acceptance events, minimised observations and run/checkpoint metadata after a separately approved schema gap review. No schema changes now. Use existing object storage only when a measured complete snapshot is too large/costly for repeated DB storage; store compressed minimised projections, digest and index, not permanent raw HTML by default. No new warehouse: no justified analytical workload yet.

Retain source/key/URL, field-qualified factual projection, hashes, observation/source dates, successful/failed attempt provenance, compatible snapshot manifests and decision/change events. Retention must follow source licence/privacy and allow audit/replay. Propose pilot caps only after measuring source sizes; do not invent storage forecasts. Failed/partial snapshots get short diagnostic retention and cannot become baselines. Document bodies retained only under their separate justified pipeline. Avoid repeated large Supabase egress for unchanged evidence.

| Mechanism | Network | Compute | Maintenance | Engineering | Failure risk |
|---|---|---|---|---|---|
| Supported narrow API/delta | LOW | LOW | LOW–MEDIUM | MEDIUM | MEDIUM |
| Small complete bulk snapshot/diff | LOW–MEDIUM | LOW | MEDIUM | MEDIUM | MEDIUM |
| Large full bulk exports | HIGH | MEDIUM | MEDIUM | MEDIUM | MEDIUM–HIGH |
| Weekly structured lists | LOW | LOW | MEDIUM | MEDIUM | MEDIUM |
| PDF/HTML weekly lists | LOW–MEDIUM | MEDIUM | HIGH | MEDIUM–HIGH | HIGH |
| Known direct summaries | MEDIUM proportional to due refs | LOW | MEDIUM | MEDIUM | MEDIUM–HIGH |
| Browser search/extraction | HIGH | HIGH | HIGH | HIGH | HIGH |
| Documents/OCR/model extraction | HIGH | HIGH–VERY HIGH | HIGH | HIGH | HIGH |

Qualitative design estimates, not measured throughput or monetary forecasts. HTTP-only is not automatically reliable; bulk is cheap only when size/cadence allow. Source budgets and selective documents are more important than universal daily schedules.

## 11. Security, execution and graceful degradation

Reuse Stage 1 admission/allowlisting and accepted request-budget concepts. Separate source read worker from factual acceptance; future worker no production credentials, no models, explicit council/source/scope admission, disposable process environment where needed. Do not return to shared Render process containment engineering.

Allowlisted HTTPS origins/routes; reject local/private/link-local/metadata-service destinations and DNS/redirect origin escapes; validate resolved destinations and every redirect. No arbitrary source URL or shell/network command supplied by scraped data. Bound requests, retries, pages, compressed/decompressed bytes, record counts, deadlines and output. Respect rate/access policies; no anti-bot bypass. Circuit breaker and checkpointed partial-run recovery remain small per-source controls, not a new platform. Cancellation/cleanup must be independently proved for actual runtime before live authority.

Treat HTML/XML/CSV/document data as untrusted: disable external XML entities, formula execution and executable attachments; reject malformed/oversized/decompression-bomb inputs; escape buyer UI; prevent prompt injection from controlling tools; sanitise URLs/output; verify publisher lineage and schema drift. Documents have separate sandbox/permissions. Machine action must be dedicated and exact; no inherited historical launch authority.

On failure preserve last accepted evidence and successful timestamp; record failed attempt separately; qualify affected claims. Source failure is not material planning change, zero, withdrawn or a reason alone to suppress an opportunity. Existing narrative eligibility may still withhold incompatible narratives independently. No source switches or verification-time advancement without their acceptance gates.

## 12. Observability and offline test design

Metrics: attempted/successful source reads, complete/partial captures, exact identity coverage, field coverage, new/changed/removed candidates, accepted factual changes, conflicts, source latency where actually measurable, successful source-observation age, requests/retries/bytes, parser/schema errors, downstream opportunity changes. Source-check count is not verified-application count. Zero new records may be healthy; a silent failed source is different. No vanity totals.

Test contracts using clearly labelled retained historical, synthetic/mock, verified and unresolved evidence. Include Failsworth retained contradiction (not current truth), Southlink unchanged expectation, Bolton Deposited unmapped, omitted-vs-blank decision/date, conflicting duplicates, exact wrong/missing reference, Hazelhurst separate parent/child verification, discovery relation not status authority, allocation without application, administrative/withdrawn/appeal cases.

Require no-network fixtures, malformed/schema drift, redirect/SSRF, time/row/byte/request overflow, hung worker cleanup, partial paging and concurrent mutation qualification, duplicate/overlap keys, snapshot deletion/scope mismatch, canonical hashing excluding verification time, deterministic replay/idempotency, conflict holds, no database/model dependency in acquisition and no new matcher. Preserve B1.1/B2.0/B2.1/Spec028/Stage1 regressions where later shared code is touched. This slice designs tests; no live adapter acceptance is claimed.

## 13. Roadmap and first implementation recommendation

Do not implement a snapshot engine before obtaining a complete, suitable source. Do not make national rollout block useful bounded freshness.

| Stage | Product outcome / scope | Dependencies and tests | GO / NO-GO | Explicit deferrals |
|---|---|---|---|---|
| DA0 architecture/source eligibility | Configuration registry contract, both loops, evidence/authority rules | This documentation; source-map completeness/privacy review | GO only after REVIEW accepts bounded scope; unresolved sources visible | No registry tables/orchestration/runtime |
| DA1 one source contract offline | Reuse corrected Bolton two-summary literal verifier; align observation envelope/fixtures only | Architecture approval; reviewed URLs/code; identity/field/semantic/budget/no-network tests | Offline GO does not imply live success; source/rights/resource ambiguity blocks live authority | Search/browser, other refs, persistence, discovery |
| DA1 live acceptance gate | Separately authorised two-summary audit proves first useful exact-status source | Exact pinned candidate, zero-persistence runner, independent review | Both identity/status acquisitions complete; Deposited stays unknown; failure stops | No automatic retries/redesign, no rollout |
| DA2 first complete discovery source | Validate/select one official bulk/weekly source; Wigan only if existing blockers close, otherwise return to REVIEW | Count/scope/latency/licence/identity proof; paging/partial/schema tests | NO-GO if completeness/rights/cadence unproved; do not fabricate removals | No generic full-council crawler |
| DA3 deterministic source diff | Complete compatible snapshots/checkpoints -> qualified candidate events | DA2; ordering/hash/time/deletion/replay tests | Only complete compatible captures advance checkpoint | No factual persistence or opportunity ranking |
| DA4 selective known freshness + factual acceptance | Due exact claims and event-driven rechecks through existing B2 boundary | Proven source; separately authorised persistence and unknown-literal storage contract; atomic/idempotent/failure tests | Failed attempts never advance success; conflicts/unknown materiality held | No all-1,270 bootstrap or automatic AI |
| DA5 bounded new application discovery | Dedupe/feed window overlap -> source candidates using current identities | DA2/3; coverage/backfill/date-vs-change tests | Cannot call discovery complete from partial/new-submission-only data | No family/component decomposition |
| DA6 relationship/site reconciliation | Exact supported parent/phase/related edges and unresolved queue | Existing accepted linking + proof; isolation/discovery tests | Context never becomes operative status without provenance | Stand Golf identities, B3–B5 |
| DA7 selective documents | Document signal -> minimal metadata/hash/bounded fetch | Separate source/document licence/security/extraction contract; no-status-download tests | Exact necessity/provenance/resources proved | Bulk OCR, autonomous AI, AH remediation |
| DA8 opportunity triggers | Material accepted fact -> existing consumer/matcher candidates | Accepted evidence, admission and controlled recompute; B1/B2/Spec028/isolation tests | No buyer ranking or AI from mere transport/timestamp change | New matcher/agent autonomy/economics |
| DA9 repeatable council expansion | Add eligible source/config using same contract | At least two differing councils demonstrate actual reuse; per-council canary/budgets | Coverage advertised per capability, not family-wide assumption | Universal portal parity, warehouse |

**One first implementation recommendation:** DA1, Bolton's existing corrected direct-summary verifier, offline contract alignment/rehearsal only after architecture acceptance. It is not a first structured/bulk adapter and does not establish discovery. Bolton is selected because exact retained URLs and one successful bounded summary transport already exist; no other council has a better demonstrated complete live status path under the accepted controls. Reuse rather than rebuild; future live retry needs NEW authority. This proposal does not resume Bolton engineering now.

Alternative comparison: Wigan is strongest bulk lead but blocked; Bury committee/delegated lists potentially offer inexpensive change context for 5 refs but are not a complete literal-status source; Stockport 35 refs has weekly evidence but prior429 risk; Manchester/Rochdale/Salford 90 refs need materially more browser/API work; Oldham20 deferred; Trafford19/Tameside7 have list paths but unproved bounds; Bolton16/Wigan19 direct Idox can be evaluated independently. No source is currently approved as a production refresh capability. If REVIEW insists DA1 must be structured/bulk, first-source selection is BLOCKED rather than silently treating Bolton as bulk.

## 14. Competitive benchmark and differentiation

Public benchmarks only, no supplier data/contact/accounts: [LandTech API/product](https://land.tech/ecosystem/landtech-api), [LandTech datasets](https://land.tech/landtech-datasets), [Searchland planning product](https://searchland.co.uk/our-apis/planning-applications). Coverage/update claims unverified. Do not pursue feature parity.

| Capability | Position |
|---|---|
| Exact planning lookup/history, identity, source provenance, qualified freshness, basic map/site navigation/filtering | TABLE STAKES |
| Ownership links, document metadata, evidence alerts | TABLE STAKES only where acquisition workflow needs them; later gated implementation |
| Broad contact marketing, generic planning analytics, every planning-document field, encyclopaedic national search UI | NOT REQUIRED for this vision/slice |
| Comparables/financial appraisal | USEFUL LATER; not collection prerequisites |
| Hidden opportunities, phase/component hypotheses, buyer-specific relevance, acquisition timing and explanation | DIFFERENTIATION; facts/identities still require deterministic support |
| Proactive buyer opportunity monitoring and later development/cost-return analysis | DIFFERENTIATION, separately gated; no automatic activation |

Own a trustworthy, selective foundation and explainable intelligence, not necessarily every raw national planning record immediately. Do not turn unknown coverage into a claim of comprehensive discovery. UK expansion must explicitly account for nation-specific planning terms/appeal systems, authority identifiers and different publication/rights regimes, not assume English Idox semantics apply everywhere.

## 15. Publication, review and decision

Two documentation paths only; no application/config/workflow change. Remote feature branch established from exact master before writing. Independent review and exact remote identities must be recorded in the completion report. Hosted doc-only acceptance is useful publication evidence, not source validation. No automatic or manual live workflow is changed/dispatched.

Requested REVIEW decision: accept/revise owned architecture and narrowed DA0/DA1 sequence; choose whether first source may be direct-summary (recommended) or must be structured/bulk (currently blocked). Authorise only a later bounded offline DA1 slice if accepted. Live source access, acceptance persistence and activation remain separate decisions.

No commercial supplier evaluation/contact, council contact, planning portal scraping, raw-HTTP experimentation, production access/write, new infrastructure, scheduler, model, summary, schema, ingestion, later-stage feature or deployment was performed.
