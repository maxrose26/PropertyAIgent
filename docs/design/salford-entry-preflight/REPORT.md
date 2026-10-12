# DA1 Salford structured CSV qualification

Decision: **DA1 SALFORD ENTRY GATE — BLOCKED**. Assessed 12 October 2026 against merged DA0 master `da06dae001cbef9af6c0f38776e1fa4adfb022b3`. Qualification only; no adapter or ingestion. PR #49 and the accepted Wigan assessment remain unchanged and unmerged. This report/ledger reuses DA0 concepts; it introduces no source architecture or runtime.

## A–C. Source identity, authority and scope

Exact existing source: `salford-historical-csv`, catalogue [Salford City Council – Planning applications](https://www.data.gov.uk/dataset/61f7eda9-b456-47ab-bba8-b27217dd15a7/scc-planning-applications). Publisher: Salford City Council. Its advertised resource is `https://map.salford.gov.uk/maps/opendata/SCC-planning-applications.csv`. The catalogue describes applications received since 1 April 2014 and declares compliance with the Local Government Open Data Incentive Scheme planning schema. The council's upstream software/database product is not identified by the evidence. No new/replacement source was discovered or admitted.

Scope classification: **UNKNOWN**. The declared starting date is known; actual first/last records, end date, submitted/received versus validated/decided membership, current/pending inclusion, mapped-only restrictions, application-type coverage and continuing additions/corrections are unproved. The old catalogue name/date does not establish HISTORICAL_ONLY. Equally, an open-ended description does not prove CURRENT_PLUS_HISTORICAL. The published schema expects ordinary public-register application types and supports nonterminal statuses; this is a schema intention, not actual Salford coverage evidence.

Catalogue updated/added: 18 July 2016. CSV resource link updated: 30 October 2014. These are publication metadata, not observed record dates or evidence that the CSV ceased updating.

## D–F. Retrieval, completeness and identity

One research-tool fetch of the exact advertised CSV reported a fetch timeout. No CSV header, data rows, count, file size, encoding or compression was obtained. One bounded native HEAD of the same HTTPS URL, timeout five seconds, zero followed redirects/retries and no body read, returned URLError after 5.012 seconds. Actual HTTP status and content length are unknown; do not call it a confirmed server timeout/outage. Harvested catalogue HTML metadata was inaccessible. No source retry/access engineering followed.

Complete retrieval therefore remains **UNPROVED**. There is one advertised CSV resource; no API, pagination, field/geometry projection or supported count/checksum mechanism was established. An advertised download is not complete acquisition proof. No preview, partial response or Content-Length hint is treated as a complete source.

The declared standard defines `CaseReference` as the application reference, unique within the planning authority, and `OrganisationURI/Label` as that authority. This is promising deterministic identity. Actual reference strings, duplicate frequency, authority labels, full suffix preservation and cross-publication key stability are untested. The actual-resource identity classification cannot be resolved to EXACT_REFERENCE_SUPPORTED, DETERMINISTIC_NORMALISATION_REQUIRED, IDENTITY_AMBIGUOUS or IDENTITY_UNAVAILABLE merely from unreadable content. No fuzzy addresses, suffix removal or inferred key normalisation is proposed.

## G. Field semantics: documentation versus actual source

The catalogue links the [official schema guidance](https://schemas.opendata.esd.org.uk/PlanningApplications/LocalOpenDataIncentiveSchemePlanningApplicationsSchemaGuidance.pdf), dated 23 July 2014. It provides actual definitions rather than guessed meanings from column names. Present Salford CSV conformity/version is unverified: documented candidate fields below are **PARTIALLY_CONFIRMED for this source**, and current field availability is **UNTESTED**.

| Candidate field | Documented meaning | Qualification |
|---|---|---|
| CaseReference | Unique application reference within planning authority | No actual values/uniqueness tested |
| Status | Optional literal state at source extraction date | Do not map schema labels to PropertyAIgent semantics here |
| Decision | Optional authority outcome; separate from DecisionType/appeal outcome | Blank is not pending or a verified absence without observed field state |
| DecisionDate | Date authority made decision | Do not equate with notice/issued date; DecisionNoticeDate has a separate definition |
| ServiceTypeURI/Label | Application service/type | Actual codes and mapping not tested |
| CaseText | Proposal text | Not needed in qualification output; not retrieved |
| CaseDate | Date valid application received, even if validity checked later | Not a separate validation date or extraction/update date |
| ExtractDate | Date extracted from source database | Not per-record modification or guaranteed publication time |
| OrganisationURI/Label | Planning authority | Publisher and authority may differ |
| UPRN / GeoAreaURI | Property reference / spatial area | Restricted UPRN excluded; area is not a proved stable site identifier |

Separate row-created, row-modified and validation-date fields remain **UNKNOWN**. The schema's date format is day/month/year and its optional empty fields represent null under that standard. No actual Salford blank or omitted field was observed: do not instantiate PRESENT_BLANK, NOT_PRESENT or factual NULL from missing retrieval. Preserve literal/semantic separation and distinguish reference, status, decision and date claims.

## H–I. Freshness/change and rights

Change mechanism: **UNKNOWN**. No reliable cadence, row-modified timestamp, cursor, repeatable complete refresh, corrections, removals or continuing new-application publication was proved. NEW_APPLICATION_DISCOVERY, CHANGE_DISCOVERY and KNOWN_REFERENCE_STATUS are independently UNPROVED. ExtractDate could qualify a future extraction batch if actually present/conformant, but cannot certify individual changes or council-current truth. Exclude changing extract/retrieval timestamps from the planning-factual hash to avoid fabricated changes.

Rights: **RIGHTS_CONFIRMED_WITH_ATTRIBUTION for the advertised reduced open dataset**. The dataset's catalogue explicitly states OGL and distinguishes the restricted UPRN-enriched version. That is stronger dataset-specific evidence than Wigan's general policy plus unset item licence. It does not authorise the enriched version, OS-derived coordinates or other third-party fields. No restricted resource was requested. Because the CSV header could not be inspected, the actual current restricted-field boundary remains unverified; operational RIGHTS admission is still UNKNOWN. No contact with Salford/Ordnance Survey was made and no unsupported legal entitlement is inferred.

## J. Resource envelope

**NOT QUALIFIED**: there is no observed size, row count, schema/header length, compression or complete download profile. Setting large numeric limits now would manufacture confidence.

The smallest conditional future design is one exact admitted CSV GET, no automatic retry or followed redirect, with full wire/expanded byte accounting and independent deadline. Before assigning operational ceilings, require actual supported metadata/header/size and count evidence, a minimal permitted field projection and measurable completion profile. Bind maximum rows and bytes to a separately reviewed measured source envelope; refuse when unknown, exceeded or inconsistent. Do not silently increase limits. No paging mechanism is assumed for a file. No archive handling is proposed.

Future complete CSV proof must include transfer completion and strict parser success through the final quoted record, matched row widths, no duplicate header/key, known encoding, reconciled publisher count/checksum/version where available, and a version/consistency qualification. Content-Length alone is insufficient. Raw proposal/agent/location data and restricted geometry/UPRN cannot be downloaded by default simply because a full schema describes them; a safe actual source projection/public reduced-resource boundary must be demonstrated first. No acquisition client is supplied by this report.

## K–M. L1 control, discovery and snapshot

The retained accepted L1 manifest contains exactly **32 Salford references**, each individually recorded with application/site IDs in EVIDENCE.json. Retained provenance: selection commit `371acef3e2a075d8fb7a8579540f87f5dc72c985`, observed 9 October 2026, QUALIFIED_RETAINED_BASIS; the full input hash is recorded without publishing private inputs.

Cross-check results: FOUND_EXACT 0; NOT_FOUND_WITHIN_PROVED_COMPLETE_SCOPE 0; AMBIGUOUS 0; FORMAT_DIFFERENCE 0; OUTSIDE_DATASET_SCOPE 0; **UNTESTED 32**. Their legitimate inclusion/period cannot be certified without actual source scope. Old metadata does not justify marking them outside scope. No individual portal request or factual comparison occurred.

Discovery value: **UNRESOLVED**. A conforming, continuing CSV with stable CaseReference could enable discovery/diffs through one/few structured downloads. Schema support for Status/Decision does not prove those facts exist or update. A static historical file may support later planning history/site intelligence but would not satisfy DA1's primary discovery objective. Current evidence establishes neither ongoing discovery nor historical-only unsuitability.

SALFORD SNAPSHOT COMPLETE must follow DA0: admitted exact source/capability; proved received-date/type scope; actual pinned schema/config/parser; approved minimal projection; complete final-file/terminal proof; source count reconciliation where supported; unique authority/reference keys; deterministic ordering/hash; no overflow or malformed records; source version/consistent-capture qualification and provenance. A documented atomic exported-file version or sufficient reconciled completeness is required, not merely a successful HTTP GET. Partial acquisition cannot establish removals. Do not equate a removed row with withdrawn application or suppressed opportunity. Schema/parser changes require rebaseline. No diff engine is implemented.

## N–O. Privacy/security and Wigan comparison

Only public metadata and schema documentation were obtained; no actual Salford application row, applicant/contact, geometry, UPRN, body/document or production data was retained. Native HEAD read no body. The audit omits raw exception content, headers/cookies/tokens and HTML. CI reads retained minimised evidence with socket paths denied; no live source client is present.

Future DA0 admission requires exact HTTPS URL/origin and actual resolved-public-IP checks, no caller URLs or response-provided URL following, bounded wire/decompressed bytes/records/fields/quoting, malformed CSV/JSON rejection, schema drift rejection and safe cleanup. Treat formula-leading cells as inert data and escape spreadsheet-facing output; never evaluate them. These are unproved future transport/parser requirements, not claimed runtime protection. No database, models, secrets or infrastructure changes.

| Dimension | Salford | Wigan accepted blocked assessment |
|---|---|---|
| Access/completeness | Advertised CSV timed out; no file/count | REST unavailable via research route; export target inaccessible; no complete capture |
| Identity | Declared standard defines unique authority/reference | Retained reference-shaped preview only |
| Semantics | Documented candidate definitions; actual CSV untested | Official current dictionary unproved |
| Freshness | Old catalogue; actual ongoing update unknown | Newer annual catalogue; record cadence/updates unknown |
| Rights | Dataset OGL for reduced projection; restricted enrichment excluded | General council OGL policy; dataset-specific licence unresolved |
| Bounds | No measured file size/count | No measured complete count/pagination |
| Discovery | Unresolved continuing feed | Unresolved annual boundary feed |
| Complexity | Potentially simple CSV if source proves fit | Layer/pagination/scope qualification also needed |

Neither source currently satisfies DA1. Salford has better documented candidate semantics/rights, but is not selected merely because Wigan is blocked. Research-surface failures do not demonstrate a broader failure of UK structured planning data.

## P–V. Review, decision and next step

**DA1 SALFORD ENTRY GATE — BLOCKED.** All eight capability-specific DA0 admission gates remain UNKNOWN for operational use. Independent review and exact hosted test identities are recorded in the PR/final report. Offline assertions validate source/ledger/provenance boundaries, not live CSV quality. No implementation proposal is justified.

Using existing evidence only, `manchester-shlaa` is a specialist selected-permitted-housing source, with historical 2019 metadata and unproved current latency/identity. It deserves at most a **small currentness/scope metadata check before any full qualification**, not automatic DA1 implementation or a full-register claim. Require a current official edition, update mechanism and suitable exact identities first. If those cannot be established, stop; do not continue access engineering or substitute Bolton. No Manchester request occurred here.

The product needs repeatable new/changed evidence, not a chain of downloaded historical catalogues. The next REVIEW decision should either authorise that narrowly scoped Manchester currentness/scope check or pause source qualification for targeted publisher clarification under separate authority. Keep historical/contextual value distinct from discovery eligibility. No adapter, ingestion, production database/schema, scheduling, portal scraping, Wigan retry/contact, Bolton/Oldham/Arcus work, documents, AI, ranking, AH, investment implementation, merge or deployment was performed.
