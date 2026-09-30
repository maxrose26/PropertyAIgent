# 020 — Qualified AH discovery

Status: bounded local implementation authorised and in progress; no release authorised.
Base: AH branch review/ah-downstream-audit, a1f3a2e685fcc1fe296e426da90ff2e5d0a197d4 (documentation-only successor to tested executable 6d31f1ed7dfb442d006d75698811160d8fc0fb1b). P0-A and roadmap ordering unchanged.

## 1. Outcome and boundaries
Identify buyer-relevant affordable-home leads using source-linked counts first and tenure second. Percentage is supporting context. Preserve uncertainty without suppressing independently supported evidence. No availability assertion, new contact system, paid evaluation, production correction, extraction reprocessing or schema migration. Generic low/medium/high bands are deferred.

## 2. Shared claim model
Extend existing in-memory AffordablePosition with a shared immutable AH assessment, reused by single-application and operative paths. Each count, percentage and explicitly evidenced tenure quantity has: reported value; optional explicit lower/upper bounds; qualifier (exact, approximate, range, at_least, up_to); evidence state (verified, estimated, unknown, conflicting); application identity; scope type/key/label; planning stage; source/document identifiers and URLs where present; document date distinct from extraction date; supporting passage reference; conflicts and investigation reasons. Tenure names with no supported quantity remain named evidence with quantity unknown.

Verified means the value was checked against an identified source for the stated scope/stage, not merely that a database field is populated or extraction confidence says high. Proposed/approved/secured are independent stage labels. Estimated requires affirmative support for that count and scope, not arithmetic rescue of a conflicting record. Preserve alternative claims rather than averaging. Do not fill a missing date or document identity with unrelated application metadata.

Reuse SchemeIntelligence fields, existing scope reconciliation, document relations and evidence notes. The adapter may copy an unambiguous existing structured source linkage; it must not parse arbitrary prose into new quantitative claims as part of this release. Unsupported legacy values remain reported/unverified and investigation-only, not zero or verified. No new persistence is proposed. If required scope/provenance cannot be represented from current records, return unknown/conflicting and report the precise gap; do not add a schema or extraction change without review.

A percentage mismatch alone does not identify the incorrect operand. Retaining the count as credible requires independent support. A component's count can support a named-component lead; it is not the whole-site total. Never sum overlapping components. No private-home count or missing tenure is inferred by subtraction in this gate.

## 3. Inclusive threshold decision table
Return separate threshold outcome: meets, likely_meets, investigate, does_not_meet, unknown. Preserve evidence state separately. These are search/count assessments, not new commercial recommendation taxonomy values.

| Input | Minimum N | Maximum N |
|---|---|---|
| Verified exact x | meets if x >= N; otherwise does_not_meet | meets if x <= N; otherwise does_not_meet |
| Credible approximate x, no bound | investigate if 0.9N <= x <= 1.1N; likely_meets above1.1N; does_not_meet below0.9N | investigate if 0.9N <= x <= 1.1N; likely_meets below0.9N; does_not_meet above1.1N |
| Evidenced range [L,U] | likely_meets if L >= N; does_not_meet if U < N; otherwise investigate | likely_meets if U <= N; does_not_meet if L > N; otherwise investigate |
| Evidenced at_least L | likely_meets if L >= N; otherwise investigate | does_not_meet if L > N; otherwise investigate |
| Evidenced up_to U | does_not_meet if U < N; otherwise investigate | likely_meets if U <= N; otherwise investigate |
| Unknown | unknown | unknown |
| Material competing claims | investigate if any credible alternative could qualify; does_not_meet only if every credible alternative establishes nonqualification | same symmetric rule |

Product Owner amendment: use10% of the buyer threshold, never of the reported count. Both boundaries inclusive; do not round the band to whole units. This is discovery leeway, not a confidence interval, a claim correction or a new source range. Outside the band, does_not_meet means excluded from that numeric discovery route under this policy, not proof of a final legal count. Threshold0 yields a zero-width band. Apply only to qualified approximate point counts without explicit bounds. Exact, range, at_least, up_to, unknown and unsupported claims retain their separate rules. Impossible bounds, negative counts, uncertain scope or unsupported claims produce investigation/unknown, never a firm match.

Examples for min50: exact verified72 meets; approx72 likely; approx48 investigates; approx50 investigates; 60–80 likely based on entire range; 45–60 investigates; up_to72 investigates; exact verified0 does_not_meet. For max50: exact0 meets; unknown never meets; approx48 investigates; approx52 investigates; 20–40 likely; 45–60 investigates; at_least72 does_not_meet. Compound min/max must be tested jointly against the same claim/range; never select different conflicting alternatives for each bound.

Default targeted search includes meets and likely_meets with qualifiers. Investigation candidates are visibly accessible with an explicit separate result category/control. Unknown has an explicit unknown-evidence route and never counts as satisfying numeric criteria. No-filter browsing retains unknown. Explicit min0 differs from no filter: it must not silently coerce unknown to zero. Maximum searches over a component qualify that component only; they cannot establish a whole-scheme upper bound unless whole-scheme coverage is evidenced. Every matching component is named and deduplicated within the existing opportunity identity.

## 4. Buyer decisions and display
Retain strict operative source selection, percentage guards, explicit-zero requirements, raw conflicts and independent specialist/planning exclusions. Replace blanket affordable_review_reason gating: count review controls AH scale/package claims; tenure review controls tenure claims; percentage review controls ratio/wholly-affordable claims. Unrelated percentage uncertainty must not set a blanket blocking_unknown for a count-only criterion. Scope ambiguity affecting the count still blocks qualification.

Keep existing overall BuyerFitAssessment classification contract. Carry separate count threshold outcome and qualified evidence reasons; do not create a STRONG_FIT solely from an estimate. Estimated essential criteria retain overall INSUFFICIENT_EVIDENCE with an explicit likely count match, available through the investigation route. Independent hard exclusion remains NOT_SUITABLE. Ensure feed eligibility does not silently drop qualified investigation candidates; reuse existing investigation eligibility, narrowly extend if necessary and test both inclusion and hard-exclusion precedence. No new recommendation taxonomy or quantitative tenure mandate engine.

Focus School fixture: separately evidenced approximate72 retirement AH apartments in an82-home proposal, reported10 open-market houses; retain disputed whole-scheme100/all_units fields for review. Show likely50+ component lead with retirement/OPSO reported and legal position unverified; do not hardcode a real-record correction. A retirement-excluding buyer remains excluded independently. If the count-to-source link is missing, investigation-only until linked.

Across detail, Explore, feed, dashboard and CSV show quantity/range, evidence state, component scope, planning stage, source/date and conflict reason. Percentage may remain withheld while count is useful. CSV adds explicit qualifier/scope columns; raw reported and usable assessment values must not be conflated. Contact next action uses only already available developer/delivery-party/contact information; applicant does not prove ownership, availability or seller intent.

## 5. Proposed files and consumers
- app/reporting/affordable_housing_scope.py: shared claim adapter/assessment and existing scope selection.
- app/policy/buyer_matching.py: both build_planning_delivery_matching_facts and build_planning_delivery_matching_facts_from_operative; assess_buyer_fit AH scale, package and percentage paths.
- app/reporting/scheme_reconciliation.py: OperativeFilterFacts and percentage presentation.
- app/ui/housing_type.py and app/ui/pages/0_Explore.py: manual and parsed min/max filtering, investigation/unknown route, CSV generation. Remove numeric coercion as evidence logic.
- app/reporting/site_profile.py and app/ui/site_profile_view.py: source/scoped quantity and tenure presentation.
- app/reporting/opportunity_feed.py and app/reporting/dashboard.py: qualified results and eligibility propagation.
- app/reporting/opportunity_intelligence_packet.py: same claims/qualifiers for downstream inputs; never an alternate evidence selector.
- app/policy/agent_evaluation_persistence.py and buyer_profile_store.py: reviewed fingerprint/compatibility boundaries only; no running refresh.
- Focused tests in existing AH/buyer/filter/persistence suites, plus actual rendered/export assembly coverage. Inspect downstream prompt projection to ensure qualifiers survive; any required edit stays within AH claim projection.

## 6. Versioning decision proposed
Recommend retain global matching version5 for the first unreleased AH change, with qualified claim semantics included in agent input fingerprints. Do not revert to4. Version5 is not known to be deployed; verify deployed version before release. If any version5 results already exist under earlier semantics, require a fresh revision/component identity rather than reusing that identity. Prior offline evidence remains tied to its exact commit.

Global version is present both in mandate fingerprints and agent policy_versions. Agent payload also embeds the mandate fingerprint: making only the agent version conditional does NOT preserve strategic-land hashes. Global5 therefore invalidates every otherwise-identical recomputed v4 mandate/evaluation hash, including unrelated strategic-land inputs. Counts of production combinations remain unmeasured because the last browser query attempt returned no result. Do not estimate by sites times buyers.

A narrow AH component could preserve unaffected hashes, but requires context-specific mandate identity or separating baseline policy identity from evaluation mandate-input identity, plus conditional agent payload versioning. That expands caller and legacy compatibility work. Defer it unless measured invalidation cost justifies it. No silent historical hash rewriting or fake-current baseline migration.

Mandate bootstrap can detect stale baselines and deterministically recompute them only when explicitly invoked. Agent history and current pointers stay intact; a changed fingerprint is not a paid call. A future run_persisted_evaluation caller may claim changed inputs and then either terminate deterministically or reach an LLM. No refresh/call is authorised here.

At any existing reader of stored agent results, compare current input identity where safely available and label current/stale/unknown; no re-evaluation on read. If freshness cannot be established, never present historical output as freshly assessed. Current code tracing has not established a universal reader check or live persisted-evaluation caller. Inventory readers before implementation; do not build an otherwise absent historical-evaluation UI. Broad invalidation is a release impact, not permission for bulk work.

## 7. Verification and treatment of stored records
Keep ORM records, histories, fingerprints and source documents unchanged. New adapters interpret on read; no backfill. Previously verified executable 6d31f1e has188 affected+20 AH+1 filter passes against baseline188; those prove earlier behaviour only. No repeat before code changes.

After implementation: table-driven min/max, unbounded approx48, crossing bounds, up_to, compound filter, component max nonpromotion, conflicting alternatives, unknown/zero; independent percentage/count/tenure states; missing provenance; mixed-app isolation; no double counting; Focus School qualified lead plus specialist exclusion; feed investigation visibility; CSV/detail/packet consistent qualifier propagation; sound evidence unchanged. Fingerprint tests cover global legacy invalidation, qualified semantic inputs, no on-read writes/calls and stale/unknown history labels where readers exist. Run changed-focused tests then bounded affected suite once at an exact clean candidate; use existing isolated WSL if local dependencies unavailable. Preserve failures/skips and matched baseline evidence.

Real-source acceptance is separate: source-linked nonzero/estimate/unknown/confirmed-zero examples, operative scope/stage and actual selected CSV/feed/detail comparison. Synthetic fixture passes do not verify Focus School or any production figure. Legal documents need not all be final for discovery, but any claim of legal status needs its own evidence. No deployment until reviewed artifact, acceptance gaps, invalidation impact and rollback are agreed. Rollback restores prior executable only under separate approval; preserved records remain compatible, while affected old assessments must not become falsely current.

## 8. Approval gate
Product direction and threshold corrections already approved. Remaining proposed decisions: (1) default matches plus visible separate investigation category and explicit unknown route; (2) qualified count matches remain separate from unchanged overall recommendation taxonomy; (3) retain global5 for first release subject to deployed-version check, defer narrower component. Approve bounded local implementation separately. No thresholds for low/medium/high required because deferred. No production authorisation implied.

## 9. Approved ten-percent amendment and bounded implementation
For threshold50, approximate44/45/50/55/56 produce minimum outcomes does_not_meet/investigate/investigate/investigate/likely_meets; maximum outcomes likely_meets/investigate/investigate/investigate/does_not_meet. This supersedes prior approx48 likely max50 and approx52 likely min50 examples. The whole45–55 band is investigation-only in both directions. No estimate in this band is displayed as a likely numeric match. Range60–80 stays a qualified likely min50 match; up_to72 remains possible only. Independent scope/retirement exclusions remain active.

The threshold kernel and shared assessment are now being integrated under the subsequent local implementation approval. Consumer and ORM acceptance remains pending; see docs/AH_SPEC020_IMPLEMENTATION_REVIEW.md. Do not relabel raw legacy counts as approximate to activate leeway. This increment does not implement all specification020 or change production behaviour. Search, matching, detail, feed and CSV must consume the same qualified result and retain original estimate/scope/source when integration is implemented.
