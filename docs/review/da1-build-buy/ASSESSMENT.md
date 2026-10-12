# TO REVIEW — UK PLANNING-DATA BUILD-VS-BUY DECISION

Research date: 12 October 2026. Documentation only; no procurement or implementation.
Base: `d253773a09690f27b150adb701c95f9aa3ee210f`.
Preserved, unmerged: PR #54, `8653a2be7741cd7a391e461172fa20ab9f7b860e`.

## A / R. Executive recommendation

**D. INSUFFICIENT MARKET EVIDENCE — COMMERCIAL ENQUIRIES REQUIRED BEFORE DECISION.**

The market clearly contains real API/feed products; the unresolved question is whether their coverage, licence and economics permit PropertyAIgent's intended multi-buyer intelligence product. There is sufficient evidence to keep council-specific acquisition engineering paused. There is insufficient evidence to select a supplier or commit to A, B or C as an executable acquisition strategy.

The preferred architecture to qualify is a **licensed planning baseline with narrowly selective owned enrichment and official verification**. That is a conditional hypothesis, not a second formal decision. It must not become an obligation to rebuild every portal behind the supplier. A commercial feed can support discovery and labelled supplier observations even where official automation is unavailable; material factual acceptance remains separately qualified.

Single next action proposed: a short supplier commercial-enquiry round to **Idox Geospatial/Emapsite, LandTech and Plota**, using the questions in S. Nothing has been sent. No trial, key, account or contract was created.

## Evidence discipline and platform context

PUBLICLY CONFIRMED below means a product, interface, price or term is visible in primary supplier documentation. It does not mean the data works as advertised. All coverage, accuracy, refresh and operational performance statements remain **PROVIDER CLAIM — UNVERIFIED** until tested. UNKNOWN means commercial/technical clarification required, not a negative finding.

Research covered nine supplier/product groups using public product pages, documentation, terms and coverage descriptions. It is a decision shortlist, not an exhaustive market census or legal opinion. No supplier API or application lookup was executed. Zero of the retained 211 references was tested against a supplier. No council was contacted or queried. Prices are public page observations on the research date, not quotes; VAT and contractual scope must be confirmed unless explicitly stated.

The supplied platform report is dated 30 July 2026. Its product intent is useful, but its operational claims and counts are historical. In particular, its suggestion that adding councils is merely configuration is not supported as a reliable current cost assumption after the accepted DA1 investigations. This assessment uses the later accepted failures/holds and PR #54 conclusions as the current boundary. It does not reactivate the report's old retry/rollout roadmap.

## B. Minimum viable planning-data contract

| Tier | Required capability / fields | Qualification |
|---|---|---|
| 1 — discovery-critical | Council identifier + exact reference; stable supplier ID and provenance URL; proposal; application type; address or usable location; received/validated dates with explicit meaning; literal status, decision and decision date where published; field evidence state; geometry/coordinates with provenance/precision; supplier observation/update metadata | A schema must support these fields and expose coverage; every individual row need not populate all of them. Missing decision on an undecided record is not ingestion failure. Missing location must remain unresolved rather than guessed. Polygon boundaries are desirable, not mandatory for every record. |
| 1 — operational contract | Complete bounded pagination or bulk snapshot; restartable changes; corrections/removals; stable identity; per-council coverage/lag; lawful commercial storage/display/derived use; cost and limits | A proximity search returning the nearest 200 applications cannot prove council-wide discovery. Daily ingestion of newly received applications is not sufficient to monitor old pending records. |
| 2 — opportunity enrichment | Residential scale, AH, applicant/developer, document metadata and separately licensed documents, explicit related applications, parent/phase evidence, conditions, S106/obligations | Supplier extraction and inferred relationships must remain distinct from source facts. Do not require all these to buy a strong core feed. Parent/child or same-site association does not transfer verification. |
| 3 — later investment intelligence | Ownership/control, comparables, values, build costs, EPC and local market evidence | Independently licensed datasets; not prerequisites to selecting the planning baseline. Basic constraint screening and site location may be commercially necessary earlier, but detailed constraints/appraisal do not need to come from the planning supplier. |

Require field-level distinctions equivalent to PRESENT_VALUE, PRESENT_BLANK, NOT_PRESENT, CONFLICTING and UNPARSEABLE. Supplier nulls require interpretation evidence. Preserve literal/semantic separation: Bolton Deposited remains UNKNOWN_UNMAPPED under PropertyAIgent's accepted rules regardless of a supplier's normalisation. Do not import an upstream unknown-to-pending fallback as fact.

## C–D. Supplier market and capability comparison

Source keys link to primary evidence in the source register. API existence is confirmed by published material; population and quality are not independently tested.

| Supplier/product | Published capability and geographic/history claim | Update/delivery evidence | Principal fit or gap |
|---|---|---|---|
| **Idox Geospatial / Emapsite; LandHawk** | Emapsite offers dataset/API, claims GB, 437 authorities, 19.6m+ records, 20+ years and 96% of published applications; 45 fields, source URLs, geolocation/UPRN [I1]. LandHawk separately claims UK/99% and hourly refresh [I2]. | CSV, WFS/WMS, ESRI and REST query delivery [I1]; daily collection/overnight publication versus LandHawk hourly wording needs product-level reconciliation. Delta/tombstone contract UNKNOWN. | Strong data-supply candidate. Do not count brands as independent redundancy or infer privileged access because Idox supplies portal software. GB versus UK/NI scope and denominator differences need explanation. |
| **LandTech API** | Standalone paid API, no LandInsight licence needed; customer-facing integration advertised [L1]. Schema includes council/ref, raw status/decision/date, received date, location/boundary, source URL, applicant/agent, derived status and processing timestamp [L2]. | Search and detail endpoints confirmed. `updated` means last processed by LandTech, not council verification. National history, GM field coverage, delta/bulk/webhook contract and latency SLA UNKNOWN from reviewed API material. | Strong technical contract fit; competitor-as-supplier commercial permissions and exit rights must be explicit. |
| **Searchland Planning API** | API advertised separately; claims all UK councils, history since 1990, 23.9m applications, appeals, key dates and documents [S1]. Search/detail/document interfaces published [S2]. | Product says real-time; platform page says 24-hour updates [S3]. No measured latency. Public docs contain differing credit descriptions; obtain definitive schedule. Bulk/delta/webhook guarantees UNKNOWN. | Genuine supplier possibility, not only competitor. Platform terms restrict third-party services; API-specific agreement is essential [S4]. Reserve shortlist. |
| **Plota API** | Claims 389 UK portal sources, 10m+ applications since 2016 [P1]. Public schemas distinguish verbatim fields from derived stage, expose exact council/reference lookup, source links and cursor retrieval [P2]. | Daily checks claimed; Pro+ `changed_since` uses content-change time; `updated_at` moves on recheck. CSV, saved feeds, webhooks, Enterprise whole-dataset delivery [P2/P3]. | Strong public specification and price transparency; substitute-database restriction creates a material licence question for an owned national planning layer [P4]. Historical field/filter limitations also matter. Its documented derived stage groups blank/awaiting values as pending and several different outcomes as approved; retain raw fields and do not adopt that mapping as PropertyAIgent authority. |
| **UK Planning API** | Public docs claim 329 complete-history councils from January 2023; partial councils separately flagged; core raw/normalised fields, references, detail source and related/document paths documented [U1]. | Daily changes/webhooks and coverage flags documented. Public pricing page and API docs disagree on some webhook entitlements [U1/U2]. Terms explicitly give no uptime guarantee [U3]. | Plausible smaller supplier; deeper pre-2023 history, legal continuity, field coverage and support need qualification. No individual-record test. |
| **PropertyData** | UK nearby-planning endpoint, source link/reference/status/decision example; filters and max 200 results, 3-mile radius [D1]. | Metered API, not a complete council stream. Published terms exclude bulk extracts/update feeds [D3]. Planning-specific latency/history completeness UNKNOWN. | Potential selective property enrichment; poor primary national discovery fit under the published delivery contract. |
| **Glenigan Construction Leads API** | API for construction intelligence [G1]; claims daily checking of every UK LPA plus research; Planning Portal partnership provides early submissions [G2/G3]. | Underlying application-to-project mapping, complete API application population, correction/delta mechanics and history range UNKNOWN. | Credible enterprise supply enquiry alternative, but sales/project intelligence is not automatically an exact application-level feed. Submission is not validation or permission. |
| **Barbour ABI Locations / Projects APIs** | Locations versus researched Projects products documented; older field matrix places exact planning reference in Projects API, not Locations [B1]. | Publication timestamps and ongoing updates described. Current field entitlement, all-application granularity, decisions/date and delta contract require confirmation. | A cheaper location API may fail minimum identity. Developer licence and product scope require clarification; do not equate project status with council application status. |
| **Planning Signal API** | Applications and decision-notice conditions, paged API, council/reference/proposal/status and decision fields advertised [PS1]. | API/conditions documentation and trial published; history depth, complete GM coverage, delta/webhooks and SLA UNKNOWN. | Restrictive competing-dataset/model provisions and deletion terms [PS2] need negotiated carve-outs. Not an assumed fit for proprietary national intelligence. |

Field qualification crosswalk: `D` = publicly documented schema/field; `C` = broad product claim; `U` = unestablished. Documentation does not establish actual fill rate. `Partial` denotes published subset/qualification, not tested quality.

| Supplier | Council/ref | Literal status/decision/date | Proposal/type/location | Docs / linked cases | Applicant/developer | Constraints | History/pending |
|---|---|---|---|---|---|---|---|
| Idox/Emapsite | C | Status/key dates C; precise decision/date semantics U | C | U | U | Separate product | History C; pending completeness U |
| LandTech | D | D | D | Appeals D; document/parent feed U | Applicant D; developer identity U | API product C | Pending enum D; historical coverage U |
| Searchland | D/C | Key dates/decisions C; literal contract needs check | C | Document interface D; link semantics U | Applicants C; developer U | Separate API C | Since 1990 and ongoing C |
| Plota | D | D, missing/derived distinctions need testing | D | Related/enrichment D; rights separate | Plan-dependent C | Plan-dependent D | 2016+ C; older filters/depth differ |
| UK Planning API | D | D | D; geometry completeness U | D; explicit vs address associations qualified | Agent D; developer U | Documented separate endpoint | 2023+ C; pending D |
| PropertyData | D | Example D; decision-date completeness U | D | U for planning documents/links | U | Other endpoints | Pending/type defaults must be tested |
| Glenigan | Exact feed schema U | U at required granularity | C | Documents/research C | Companies/research C | U | Broad lifecycle C; full history U |
| Barbour ABI | Projects D; Locations insufficient in matrix | Project status D; literal application fields U | D | U | Research/company fields C | U | Scope/history U |
| Planning Signal | D/C | Status/decision C; date fill U | C | Conditions C; relationships U | Agent plan-dependent; developer U | U | Depth/pending completeness U |

None establishes full AH/S106/commencement evidence as a guaranteed core feed. Unknown future fields do not disqualify an otherwise strong Tier 1 supplier.

### Greater Manchester coverage

No supplier coverage was independently tested. Broad UK/GB marketing cannot certify the ten councils or all fields. Plota's public coverage page explicitly lists all ten; the following are provider-reported latest public application dates, observed 12 October, not measured ingestion lag [P5]:

| Bolton | Bury | Manchester | Oldham | Rochdale | Salford | Stockport | Tameside | Trafford | Wigan |
|---|---|---|---|---|---|---|---|---|---|
| 8 Oct | 9 Oct | 8 Oct | 6 Oct | 8 Oct | 9 Oct | 9 Oct | 9 Oct | 9 Oct | 8 Oct |

Each was labelled checked Today/up to date. These labels do not prove completeness or decision freshness. UK Planning API also publishes council-level coverage metadata [U4]; the review saw named Bolton, Manchester, Oldham and Wigan entries, without treating counts as independent verification. For every supplier, request ten explicit LPA rows with history range, field fill rates, pending revisit frequency and outage backlog. England, Great Britain and UK are not interchangeable; clarify Scotland, Wales, NI, historic authorities and successor identifiers.

## E. Public commercial evidence

All figures below are API/data products, not substituted end-user seat prices.

| Provider | Public price / limit observed | Trial, contract and support |
|---|---|---|
| Idox/Emapsite | PRICING UNKNOWN — SALES ENQUIRY REQUIRED | Field dictionary and free trial offered [I1]; API contract, limits, SLA unknown. LandHawk desktop seat pricing is not an API quote. |
| LandTech | PRICING UNKNOWN — SALES ENQUIRY REQUIRED | API demo offered [L1]; minimum term, sandbox quotas and SLA unknown. |
| Searchland | PRICING UNKNOWN — SALES ENQUIRY REQUIRED | API credits documented but money/definitive schedule needs quotation [S2]; platform term is not assumed API term. |
| Plota | Starter £49/month: 10,000 records/20,000 requests, 120/min; Pro £149: 100,000/200,000, 300/min; Business £399: 250,000/500,000, 600/min; Enterprise custom [P3] | Demo 500 one-off records/requests. Multi-tenant and change feed Pro+. SLA Enterprise. Do not infer standard plan licences national replication. VAT/minimum term confirm. |
| UK Planning API | Free 500 requests/month; Starter £19/2,500; Growth £99/15,000; Enterprise custom [U1/U2] | Monthly/cancellable; no guaranteed uptime [U3]. Webhook entitlement contradiction needs resolution; VAT confirm. |
| PropertyData | £30/2k, £50/5k, £100/15k, £150/30k, £200/50k, £300/100k, £400/150k, £800/300k monthly credits [D2] | 500-credit trial; published rate limits 12–60 calls/30 seconds across plans. Planning returns ten records per credit [D1]. No national feed quote implied. |
| Glenigan / Barbour ABI | PRICING UNKNOWN — SALES ENQUIRY REQUIRED | API/developer access confirmed; exact minimum, quotas, trial and contractual SLA unknown [G1/B1]. |
| Planning Signal | £49/month+VAT/2,500 records; £149+VAT/10,000; national/bulk from £399+VAT; 60 requests/min [PS1] | 100-record demo, cancellation offered; support/SLA and bulk licence scope require clarification. |

No total monthly GM/UK cost can be calculated safely from these headlines. Cost depends on initial backfill, unique records versus calls, corrections, repeated monthly charging, deleted records, documents, multi-tenant permissions and national database rights. Obtain pilot and national annual quotes with fixed assumptions. No developer-day or pound build estimate is invented.

## F. Rights and proprietary intelligence

Four distinct rights must be explicit: **display raw facts, store/cache, create/retain derived intelligence, redistribute raw data**. A right in one column does not confer the others. Also distinguish LLM inference/RAG/embeddings from model training/fine-tuning and evaluation. An MCP endpoint is not blanket AI licensing.

| Provider | Display / storage | Derived data / AI | Redistribution / exit |
|---|---|---|---|
| Idox/Emapsite | API/dataset sale confirmed; applicable licence UNKNOWN | UNKNOWN — COMMERCIAL CLARIFICATION REQUIRED | UNKNOWN: ask OEM/end-user, provenance retention and termination rights |
| LandTech | Customer-facing integration advertised; binding API licence UNKNOWN | UNKNOWN, including competing intelligence service and model processing | UNKNOWN; legal landing page did not expose a reviewed API agreement |
| Searchland | Published platform agreement restricts third-party services; cannot assume it governs or authorises API product [S4] | UNKNOWN under a suitable API agreement | Require negotiated API/OEM schedule, not platform subscription assumptions |
| Plota | Paid own-product use; multi-tenant Pro+; storage while subscribed [P4] | Derived analysis belongs to customer, but competing/substitute database prohibition must be resolved; external-model processing/training scope UNKNOWN | Raw resale/feed and general-purpose substitute restricted; ordinary incorporated records/outputs may survive cancellation, continued general-purpose searchable service does not. Linked-document rights excluded. |
| UK Planning API | Commercial retention/display scope not fully specified [U3] | Derived ownership, inference and training UNKNOWN | Competing bulk redistribution prohibited; enterprise data-sharing arrangement advertised; exit rights UNKNOWN |
| PropertyData | Customer-facing SaaS permitted; current cache 60 days, refresh/delete; dated historical observations and derived scores may be retained [D3] | Derived material permitted within terms; third-party model processing/training clarification still needed | No raw bulk/update feed; no substitute searchable dataset. Historical retention is not continuing current service after cancellation. |
| Glenigan / Barbour ABI | API for own systems established; external product licence UNKNOWN | UNKNOWN | UNKNOWN; enterprise contract required |
| Planning Signal | Individual records to users permitted; stored-data deletion within 30 days after plan ends [PS1/PS2] | Competing dataset/service and related ML training/evaluation restrictions are a material risk | No bulk resale; independent document rights/derived survival not established |

No supplier is licence-approved for PropertyAIgent. The questions concern actual intended use, not finding a label to evade a restriction. Do not assume underlying public facts invalidate the supplier's contractual compilation rights. Separate personal data, third-party documents and mapping licences from the core reference/status feed. Attribution requirements explicitly include Plota council links and Planning Signal credit/record attributions; others need the precise API schedule. Public PropertyData terms generally do not require API attribution, but have separate extract/report conditions.

## G / O. Competitors and the moat

LandTech publicly demonstrates map/site sourcing, planning history, ownership, constraints, comparables and alerts [L3]. Searchland demonstrates comparable breadth plus application/document alerts and AI-assisted searches [S3/S5]. These are feature claims, not a comparative product test. Both have genuine API offerings, so treating them only as closed competitors would be inaccurate; treating their end-user licences as supply contracts would be equally wrong.

Competitive foundation: broad searchable planning identity, map location, history, dependable changes and traceable evidence. PropertyAIgent should own the reconciliation and intelligence above this: separate scheme/opportunity identities, residual/component hypotheses, buyer-specific relevance, explanations, longitudinal outcomes and disciplined investment analysis. A generic AI chat/search layer is not by itself a moat when competitors advertise it too.

Raw collection is defensible only if it yields unique coverage, latency, rights, cost advantage or proprietary feedback others cannot readily buy. Current evidence has not demonstrated that advantage. Sunk cost in adapters is not a reason to continue. Conversely, a licence that prevents retaining explanatory evidence or proprietary longitudinal results could undermine the intended moat despite a low monthly price.

## H–I. Build and buy burden

Own platform-family collection: HIGH initial effort for GM; VERY HIGH for national coverage; HIGH/VERY HIGH ongoing maintenance. Reusable Idox/Arcus code reduces duplication but does not eliminate council exceptions, pagination/completeness, field drift, rate limits, backfills, corrections, source health, provenance and licensing. Accepted Oldham/Bolton observations demonstrate distinct failure layers; do not attribute every failure to anti-bot systems. Arcus remains unqualified for the desired coverage. Structured sources and publications have their own completeness/rights gaps. These are qualitative inferences from accepted work, not measured staffing costs.

Licensed feed: LOW/MEDIUM transport integration, MEDIUM qualification and ongoing operation. Still needs schema/identity tests, coverage monitoring, budgets, idempotency, source qualification, licence compliance, corrections/deletions and incident handling. Supplier claims do not remove these. A trial success is not an SLA; HTTP success is not completeness. Outsourcing collection buys focus, not unquestionable truth.

## J–L. Conditional hybrid, provenance and freshness

Keep the initial hybrid narrow: one qualified primary feed; reuse already accepted public evidence; enrich/verify selected material cases only. Do not build two complete acquisition estates for theoretical redundancy.

Conceptual flow: licensed observations -> canonical council/reference identity -> new/changed candidate -> PropertyAIgent reconciliation -> relevance qualification -> selected evidence enrichment -> opportunity hypothesis -> buyer assessment. This is not implementation authority.

Four explicit evidence classes:

1. SUPPLIER_REPORTED_FACT: supplier's observation with source link and timestamps; not silently council-verified.
2. OFFICIAL_SOURCE_FACT: evidence actually obtained and qualified from the competent authority (including appeal authority where relevant).
3. PROPERTYAIGENT_DERIVED_FACT: deterministic transformation with input provenance/rule version.
4. AI_INFERENCE: hypothesis/explanation with cited inputs and uncertainty, never promoted solely by generation.

Keep decision date, source publication time, supplier observation/ingestion time, supplier content-change time and PropertyAIgent retrieval time separate. Some will be unknown. LandTech processing time and Plota recheck time are not decision dates. Daily/hourly service claims do not prove maximum council-to-customer delay.

Autonomous monitoring eventually requires complete restartable deltas, ordering/tie handling, overlap/replay, correction/tombstone semantics, retention window and outage catch-up. A webhook is a signal, not sufficient recovery on its own. Do not checkpoint past an incomplete page/window. Supplier normalisation changes must not masquerade as official material changes.

Reuse DA0 gates and the 211-reference manifest for future evaluation. Preserve literal/semantic separation, field evidence states, exact status-source attribution and B2 material-change/factual-acceptance rules. Supplier retrieval must not automatically advance the existing successful official-verification timestamp. Material downstream invalidation remains after accepted evidence, not after an unqualified upstream delta. Unsupported verification should remain explicit; do not suppress an opportunity solely because council automation is unavailable.

## M–N / P. Strategy decision matrix

Ratings describe expected burden or potential, not measured vendor performance. Every positive licensed rating is conditional on contract and data qualification.

| Dimension | Licensed feed | Public structured + targeted own | Own platform collection | Licensed + selective own |
|---|---|---|---|---|
| Coverage | HIGH potential; supplier exclusions untested | Limited source evidence; operational GM discovery coverage unproved | HIGH potential, LOW currently qualified | HIGH potential; gaps explicitly qualified |
| Freshness | MEDIUM/HIGH potential; SLA/deltas needed | Uneven publication/council cadence | Controllable schedule, upstream delays remain | Feed signals plus selective verification; no universal currentness claim |
| Reliability | Contract/observability dependent | Heterogeneous weak guarantees | Owned incidents across many hosts | Two evidence layers, but more failure states |
| Time to market | Shorter if licensing fits | Uncertain per-source qualification | Longest under current evidence | Shorter only if supplementation stays selective |
| Initial effort | LOW/MEDIUM integration; MEDIUM qualification | HIGH qualification/integration | HIGH GM / VERY HIGH national | MEDIUM, rises sharply if every portal rebuilt |
| Ongoing effort | MEDIUM supplier and data-quality operations | HIGH fragmented upkeep | HIGH/VERY HIGH break-fix and coverage | MEDIUM/HIGH depending supplement count |
| Rights clarity | Potentially high with negotiated schedule; unresolved now | Dataset-specific; unresolved gaps | Public access does not supply reuse rights | Must reconcile multiple licences |
| Provenance | Potential source URLs; fact-level chain needs proof | Strong for official records, incomplete fields | Direct origin, parser errors still possible | Best potential for explicit precedence/traceability |
| UK scalability | Strong potential; GB/UK/history exclusions matter | Weak without many local agreements | Very high expansion burden | Strong if one baseline and bounded exceptions |
| Vendor dependence | HIGH | LOW vendor, HIGH public-source dependence | LOW aggregator, HIGH council-platform dependence | MEDIUM/HIGH; selective fallback not complete replacement |
| Differentiation | Frees effort for proprietary intelligence | Can expose niche official evidence | Only defensible if uniquely better acquisition | Strongest conditional fit with evidence/derived rights |
| Operational complexity | MEDIUM | HIGH | VERY HIGH | MEDIUM if narrow, VERY HIGH if uncontrolled |

Vendor risks include correlated upstream sources, pricing/term changes, API discontinuation, licence termination, data errors and inaccessible historic evidence. Mitigations to negotiate: canonical council/reference keys, versioned export, retained provenance/derived rights, deprecation notice, capped price escalation, measurable SLA, correction process and exit window. Do not buy two brands as resilience without checking upstream independence. Selective council fallback is not yet proven; it cannot be sold as guaranteed failover.

## Q. Independent review

Separate independent review: GO for documentation-only publication. Reviewer supported decision D, the bounded three-supplier shortlist, explicit rights/AI distinctions, qualitative cost reasoning, competitor treatment, freshness and national-coverage qualifications, vendor risk and moat analysis. One wording correction was adopted: public structured coverage is now described as unproved operational GM coverage rather than a demonstrated LOW/MEDIUM rating. Review assessed the artifact against the instruction; it did not independently retest supplier claims, fetch supplier data or contact suppliers. No supplier selection, purchase, implementation or merge authority follows.

## S. One next action: tightly scoped commercial-enquiry round

Shortlist **Idox Geospatial/Emapsite, LandTech, Plota**. This samples a dedicated data-supply route, a mature land-intelligence API and a transparent API-first offering. These are enquiry priorities, not approved suppliers. Searchland is the first reserve if an initial supplier cannot license the use; do not open an unbounded sales process. Glenigan/Barbour may be useful later if project enrichment becomes the priority; PropertyData's feed constraint and Planning Signal's restrictions make them weaker baseline candidates. UK Planning API remains a technical reserve pending licence/service qualification.

Exact questions for the Product Owner to ask (not sent):

1. Will you license a paid multi-tenant product that stores UK planning records, reconciles sites/schemes, applies deterministic and hosted-LLM analysis, and presents proprietary buyer-specific acquisition rankings/explanations? Identify the governing API/OEM terms and any competition restriction.
2. Separately confirm raw display, current caching, permanent dated evidence/provenance, derived-data ownership, exports to individual customers, raw redistribution, and post-termination retention/use. Can we retain our scheme graph, annotations, scores and explanations after exit? Which outputs remain restricted?
3. Distinguish inference/RAG, embeddings, evaluation and training/fine-tuning rights. Can data be sent to a contracted model processor with no training? State personal-data/document/mapping exclusions and attribution.
4. Supply a ten-LPA GM matrix: active source, full history range, gaps, pending revisits, field fill rates, raw versus inferred values, correction process, source URLs and last successful collection. Explain GB versus UK/NI and historical council identifiers.
5. Supply exact schema/date/null semantics, especially literal status versus normalisation, absent versus blank, decision/date, parent/phase links and guessed locations. Can we ignore your semantic mapping and retain literal evidence?
6. Describe initial bulk load and complete deltas: cursor/pagination, inclusive boundaries, change timestamp meaning, replay retention, deletions, late corrections, versioning and outage recovery. Is a whole-council/national replica for this product permitted?
7. Quote GM pilot and UK expansion separately: onboarding/backfill, updates, records/calls, retries/rechecks, documents, multi-tenant rights, minimum term, VAT, overages, renewal uplift, support/SLA and termination/export charges. Do not quote an end-user seat instead.
8. What measurable service and freshness commitments apply? How are council outages, missing pending decisions and incorrect joins reported? Is the supplier legally entitled to license every supplied layer for this use?
9. Can a separately authorised evaluation compare the fixed 211 references plus a bounded genuinely new/date-window cohort and correction/replay cases, without purchase or broad contractual commitment? Provide evaluation terms first. The 211 alone cannot test new discovery recall or current truth.

Supplier-specific gates: Idox reconcile 96%/99%, GB/UK and daily/hourly product statements; LandTech provide external competing-product and delta/exit terms; Plota give written approval for the intended persistent planning baseline and AI use rather than relying on standard-plan marketing. If no supplier can meet rights/coverage at an acceptable quote, return to REVIEW; do not automatically restart owned acquisition.

## T–U. Limitations and actions not taken

No measured supplier accuracy, throughput, latency, actual 211 coverage or complete GM discovery recall. Public schemas/examples are not tested production data. Price/coverage pages may change; public claims use incompatible denominators. Corporate/service continuity and upstream licensing chain were not independently audited. Public terms do not replace a negotiated product-specific agreement. Rights UNKNOWN remains a blocking commercial question.

No supplier contact, paid account, trial signup, contractual acceptance, API key, supplier data API call, council request, portal scraping, Idox/Arcus engineering, Trafford/SHLAA qualification, Wigan/Salford retry, ingestion, production DB/schema access, scheduling, model call, deployment or merge. PR #54 and historical evidence remain unchanged. No runtime/registry/workflow change in this branch. Documentation checks and review only; no claim of hosted runtime CI.

## Primary-source register (accessed 12 October 2026)

- I1: https://www.emapsite.com/digital-maps-and-data/address-data/planning-applications/
- I2: https://www.landhawk.uk/api/planning-application-data/
- L1: https://land.tech/ecosystem/landtech-api
- L2: https://developers.land.tech/openapi/planning-applications
- L3: https://land.tech/find-sites ; https://pages.land.tech/planning-data
- L4: https://land.tech/legal (embedded legal content did not establish API licence)
- S1: https://searchland.co.uk/our-apis/planning-applications
- S2: https://docs.searchland.co.uk/
- S3: https://searchland.co.uk/features/planning-applications
- S4: https://searchland.co.uk/terms-and-conditions
- S5: https://searchland.co.uk/features/ai-assistant
- P1: https://plota.co.uk/api-access (official search-index result inspected; direct read unavailable; core coverage claims also on P3)
- P2: https://plota.co.uk/api-docs
- P3: https://plota.co.uk/api-pricing
- P4: https://plota.co.uk/api-terms
- P5: https://plota.co.uk/coverage
- U1: https://www.ukplanningapi.co.uk/api-docs
- U2: https://www.ukplanningapi.co.uk/
- U3: https://www.ukplanningapi.co.uk/terms
- U4: https://www.ukplanningapi.co.uk/councils
- D1: https://propertydata.co.uk/api/documentation/planning-applications
- D2: https://propertydata.co.uk/api/pricing
- D3: https://propertydata.co.uk/terms
- G1: https://www.glenigan.com/our-products/construction-leads-api/
- G2: https://www.glenigan.com/data-practices/
- G3: https://www.glenigan.com/glenigan-partners-with-planning-portal-for-early-access-to-planning-applications/
- B1: https://barbour-abi.com/locations-api/ (field matrix says last reviewed 3 August 2023; present applicability requires confirmation)
- PS1: https://www.planningsignal.co.uk/developers
- PS2: https://www.planningsignal.co.uk/api-terms
