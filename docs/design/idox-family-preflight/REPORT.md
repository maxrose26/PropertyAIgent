# DA1 Idox platform-family preflight

Decision: **DA1 IDOX FAMILY — BLOCKED**. Shared received/validated-date-window enumeration is a credible engineering hypothesis, followed by selective separately admitted summary evidence. It is not yet an evidenced reusable bounded acquisition route. This is not a source-eligibility PASS, a live-canary readiness decision, or a claim that current search windows are complete. General change discovery remains unproved. Base: merged DA0 `da06dae001cbef9af6c0f38776e1fa4adfb022b3`. No adapter/runtime changes or live application requests.

## A. Cohort and evidence

Membership is reconciled against the accepted DA0 research registry and repository configuration, not portal appearance. Seven councils represent 121 retained direct status references; excluding deferred Oldham leaves 101 **candidate references**, not verified/addressable coverage. Operationally admitted sources: zero.

| Council | Base path / date mode | Evidenced difference |
|---|---|---|
| Bolton | paplanning.bolton.gov.uk/online-applications; received | Retained direct-summary and field-state work; no successful live factual verification |
| Bury | planning.bury.gov.uk/online-applications; received | Separate legacy Anite documents; not a different admitted discovery architecture |
| Oldham | planningpa.oldham.gov.uk/online-applications; received | Deferred/unproved under accepted contract; no new experiment |
| Stockport | planning.stockport.gov.uk/PlanningData-live; validated | `details` further-info tab; configured 2.5-second detail pause; historical 429 risk |
| Tameside | publicaccess.tameside.gov.uk/online-applications; received | Official weekly/monthly description; current bounded protocol unproved |
| Trafford | pa.trafford.gov.uk/online-applications; received | Historical direct-result redirect and navigation/connection failures |
| Wigan | planning.wigan.gov.uk/online-applications; received | Historical inline links share keyVal across tabs; official list description |

Primary repository evidence: `app/config.py`, `config/councils.yaml`, `app/scrapers/idox_portal.py`, accepted DA0 registry/SOURCE_MATRIX, `verification/stage26b_l1/bolton_literal.py`, retained Bolton field projections/tests, and request-boundary tests. Existing scraper-health/orchestration tests and mocked status tests do not prove discovery-window completeness.

Public documentation inspected only: [Wigan guidance](https://www.wigan.gov.uk/Resident/Planning-and-Building-Control/Planning/Search-planning-applications.aspx), its linked historical platform user guide/disclaimer, and [Tameside guidance](https://www.tameside.gov.uk/w/development-management-home-page). Council guidance describes weekly/monthly lists; historical platform documentation distinguishes validated/decided lists, result paging and account notifications. These feature descriptions do not certify current installed versions or machine access. No portal link/form was opened. Stockport/Trafford guidance returned research-tool 403; existing descriptions remain retained evidence. No structured Wigan/Salford retries, Manchester qualification or Oldham requests occurred.

The vendor manual carries copyright/commercial-use restrictions. Do not copy its procedures, screenshots or code into implementation; this recommendation derives from existing repository code and minimal public feature facts. Wigan's portal disclaimer qualifies indicative information and document/image/map rights. Public portal access is not a blanket commercial licence. Council-specific RIGHTS gates remain UNKNOWN, including for factual projections; do not assume a platform-wide licence.

## B–C. Shared primitives versus configuration and exceptions

**One family already exists.** `CouncilConfig` supplies host/base path and received versus validated field names to the same `collect_result_links` function. Routes, keyVal parsing and summary-table parsing are shared. This is concrete code commonality, not proof that every deployment behaves identically.

Reuse route/identity parsing and council configuration; extend evidence qualification using the accepted field-state approach. Configuration may express host/base path, reviewed date field names/meaning, labels/date format, observed page-size/sort controls and pacing. Result-page size is currently hardcoded to attempt 100, not a proven configuration property or actual page-size guarantee. Different protocols remain exceptions; unsupported councils must stop without relaxing shared admission.

Do not call these existing paths unchanged as the new acquisition adapter:

- `collect_result_links`: Next-click/wait exceptions silently break and return partial links; no counts/page manifest/loop/byte/deadline guard. Missing Next alone is treated as terminal, even for an unrecognised page.
- Link collection deduplicates full URLs; different tabs with one keyVal remain distinct and substring matches lack source/route admission.
- `fetch_application_by_reference`: fallback takes the first sorted keyVal; ambiguity/independent exact-reference proof is insufficient.
- `extract_table_fields`: duplicate labels overwrite; a qualifier must detect conflicts first.
- `fetch_application_detail` and `scrape_month`: couple discovery to proposal/unit qualification and further-information extraction. This is beyond cheap discovery and would exclude/overfetch prematurely.
- Local four-attempt HTTP/three-attempt navigation retries are not a whole-run request/byte/deadline boundary.

The frozen unmodified collector excerpt is inert `.txt` evidence. Offline tests execute only that trusted repository function against synthetic fake pages and the real HTML parser, demonstrating partial-return and identity failures without app imports/browser/network. These are current-code findings, not fixtures of actual council pages or desired production acceptance.

## D–F. Three separate capabilities

**New applications:** shared date-window enumeration is the narrow reuse hypothesis supported by existing code; bounded end-to-end acquisition is not proved. Received-date scope is not validated-date scope; Stockport's configured validated mode cannot certify all newly submitted applications. Weekly lists may likewise cover validated publications. Name the admitted scope explicitly, require all statuses/types within that scope, and never assume a default form is unfiltered. No current COMPLETE/PAGINATED/DETERMINISTIC/BOUNDED/REPLAYABLE operational claim passes yet.

**Changed applications:** platform documentation provides a **DECISION_ONLY_CHANGE_DISCOVERY lead**, not a general change cursor. Current repository configuration implements received/validated pairs, not a proved decision-window protocol. Per-council operational classification is UNKNOWN. Decision-date windows can miss withdrawal, appeals, corrections, committee progression, older/backdated decisions and other updates. General change detection still needs separately qualified targeted polling or stable snapshots; no complete modified-since feed/RSS is established. Documented login notifications are not an admitted public machine feed; do not create accounts or subscribe as a workaround.

**Known-reference facts:** shared exact identity, sanitised summary route, table/date helpers and field qualification are reusable design primitives. Exact search and known direct-summary are distinct capabilities; neither proves discovery. Independently confirm displayed reference, reject ambiguity/conflicts, retain omitted versus blank decision/date, keep Deposited UNKNOWN_UNMAPPED and do not advance verification on failure. Preserve consumed Oldham/Bolton canary outcomes and existing generic behaviour; no rerun is implied.

## G–J. Identity, completeness, checkpoints and selective detail

Minimum accepted application identity: admitted council/source + independently evidenced full reference, with keyVal and admitted public summary URL as source provenance. Preserve significant prefixes/suffixes/zeros; reference equality and source-key uniqueness are different checks. Conflicting reference↔key mappings are unresolved. A key-only link is an unresolved source-record candidate, not APPLICATION_DISCOVERED or an acquisition opportunity. No fuzzy addresses. If the list cannot supply reference, fetch only the separately admitted minimal summary needed to establish it.

A COMPLETE discovery window needs explicit source/capability/date kind/filter scope, proved inclusive boundary semantics, recognised first page, expected count where supplied, ordered page/boundary manifest, all subsequent pages, stable unique identities, terminal proof, no loop/missing page/cap/overflow, parser/config versions and qualified source consistency. A repeated page is failure, not successful deduplication. A failed page invalidates the unit; retain partial positives with qualification without advancing the accepted checkpoint. HTTP paging is not a transaction snapshot. Stable ordering/count alone cannot rule out concurrent mutation; source session/version semantics or sufficient reviewed reconciliation are required. Otherwise return QUALIFIED/PARTIAL, not complete discovery or removals.

Checkpoint key binds source/council/capability/date kind/filters and schema/parser/config, accepted predecessor and accepted window proof. Use overlapping local-calendar windows (Europe/London; explicit DST/date semantics) and deterministic authority/reference deduplication. Advance only after the entire bounded window is accepted. Overlap addresses boundaries, but no arbitrary overlap duration guarantees unknown late/backdated publication. Establish publication lateness or keep coverage qualified; periodic reconciliation needs separate authority. Old received dates first published later must not be silently missed. Schema/parser/config drift requires controlled rebaseline; event replay follows DA0 predecessor semantics.

Stage 1 obtains a cheap admitted window inventory: reference if actually present, keyVal/summary URL, date/window provenance, optional list facts and completeness controls. It does not parse proposal text for buyer ranking or residential exclusion. Stage 2 selects minimal summaries for new identities, qualified changed evidence, demonstrated dependencies or insufficient list identity/facts. Known unchanged entries do not justify blanket detail fetching. Commercial relevance uses existing accepted downstream logic, never a new matcher. No further-information, documents, related/history or applicant/control acquisition is implicitly authorised.

Emit the common DA0 capability-specific discovery projection, not an Idox-specific evidence model: qualified field states, source/identity/provenance, literal facts, source timestamp meanings, completeness and resource/version controls. DA0's executable RawEnvelope example is status-only; its documented discovery projection needs a separately reviewed common schema before runtime implementation. Do not bypass it with arbitrary fields or invented reference/status. A discovered record proceeds through reconciliation and intelligence before any opportunity/buyer assessment.

## K–L. Resource and security model

For a bounded HTTP window with P result pages, S page-size/sort operations and D selected summaries: one form GET + one submission + P−1 next-page operations + S + D, **plus every redirect/retry**. Submission may include a redirected result GET; account for it, not an assumed free operation. List-only cost is approximately P+1+S before redirects/retries. Actual URL/method sequence and bytes are unproved; this is a logical request model, not measured throughput. Whole-population detail retrieval adds at least one request per item and often more in the generic path.

Cost classification: **MEDIUM** for proved bounded HTTP list-only acquisition; **HIGH** for browser traffic or indiscriminate detail retrieval. Existing date searches use Playwright; that does not prove browsers are mandatory for every council. HTTP feasibility remains unproved, and Oldham's raw-HTTP failure must not be extrapolated to all seven. No new HTTP form implementation/browser path is built here. Browser navigation/XHR/assets/redirects must be counted; reliable response/download accounting remains an unresolved live gate. Preserve the prior Oldham browser NO-GO rather than assuming disposable runners fix byte accounting.

Future admission binds exact origins/routes/window/query fields and required server state, without arbitrary URLs, populated hidden search expansions or guessed exceptions. Resolve public destinations and validate every redirect. Deny all document/further-info/related/history routes, downloads and unrelated assets. Fail closed on layout drift, unrecognised result/empty pages, ambiguity, rate limit, unsafe redirect or any request/page/row/wire/expanded-byte/deadline bound. Use source-specific pacing and bounded permitted retries, never inherited retry multiplication. No OS egress sandbox claim and no runtime-containment implementation in this slice. Council rights, latency and complete consistent retrieval remain independent gates.

## M. Three-council future acceptance

Use **Bolton, Stockport and Wigan** in one coordinated offline matrix before a separately authorised family live evidence gate. This is a future test design, not another Bolton verifier or a Wigan structured-source retry.

| Council | Distinct behaviour to exercise | Must not be inferred |
|---|---|---|
| Bolton | Received-date mode, optional decision/date, Deposited literal | Summary transport success is not list completeness |
| Stockport | Validated-date mode, different base path/pacing, rate-limit failure | Validated coverage equals all received submissions |
| Wigan | Multiple tabs sharing one keyVal/inline identity handling | First URL/key is operative authority |

Common offline fixtures must cover >1 page, true terminal and zero results, missing/failed page, repeated page, counts/duplicates, shifting results, late/boundary publication, conflicting reference/key, malformed/empty/login/rate pages, exact host/route/query denial, budget failures and checkpoint replay. No actual current council HTML is fabricated as retained truth. Source-specific selectors/page size/default scope remain UNKNOWN until evidence proves them.

Live acceptance, if later proposed, is one fixed small window per council, list/identity only, under shared enforced limits; no arbitrary operator references/date expansion/details. It must demonstrate real pagination in at least one admitted case and effective query filters/terminal/count/identity/budget evidence in all three. If a window overflows or transport cannot account for traffic, fail without broadening. Three passes certify only those source/capability tuples, never the entire family or general change discovery. Rights and source-consistency proof cannot be waived by the canary.

## N–T. DA0 fit, product value, recommendation and boundaries

Owning a shared family capability can improve hidden-opportunity discovery by reducing duplicated collection and selectively supplying new evidence to existing intelligence. Generic search parity is not the product advantage. The advantage depends on economical complete-enough evidence, relationship reasoning and buyer-specific timing/relevance. Do not build a public search clone, universal council support, accounts, document crawler or another matcher. The existing 211 references remain a separate freshness asset, not the permanent discovery scope.

**DA1 IDOX FAMILY — BLOCKED.** The user-defined gate requires a reusable bounded acquisition route, not only shared code or synthetic traversal. Missing evidence: effective current form/query scope; a transport that accounts for every admitted request and actual response bytes; exact result identities; count/terminal/consistent paging; publication latency; and council-specific rights. General change discovery remains an additional unproved capability. Do not build the operational discovery adapter or call the generic scraper unchanged.

Recommend ONE coordinated platform-family evidence gate. First prepare, under separate authority, a small offline fixed-scope proof package using the common DA0 discovery projection and existing primitives, with three synthetic council configurations, explicit partial failures and enforceable request/byte/deadline controls. This is proof preparation, not an operational adapter, new crawler or runtime-containment workstream. If no existing transport can satisfy the safety contract, stop before requesting live authority.

After that package passes review, one separately authorised family canary could inspect a fixed closed date window for Bolton, Stockport and Wigan, list/identity only, with no reference substitution or detail/document requests. Provisional rejection ceilings for review: 20 total accounted HTTP requests, at most two result pages and 100 unique identities per council, 1 MB per response, 6 MB total actual received/expanded bytes, zero followed redirects/retries and an independent 120-second deadline. These are proposed small administrative bounds, not throughput claims or authority; reject operation if they cannot be enforced. Real pagination must be exercised in at least one case or coverage remains unproved. It could resolve current query/result identity/basic paging and resource evidence; it cannot alone clear council rights, long-term publication latency, arbitrary late changes or transaction-like snapshot consistency. No sequential council-dataset qualification is proposed.

Independent exact-remote review and hosted test identities are recorded in the PR/final report. No live search/reference/detail/document requests, scraper/adapter/runtime change, Wigan/Salford retry, Manchester qualification, Oldham experiment, Bolton dispatch, production access/schema, ingestion, scheduling, models, ranking, deployment or merge occurred. PRs #49/#50 remain preserved and unmerged.
