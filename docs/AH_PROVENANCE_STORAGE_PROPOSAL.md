# AH source-linked claim design — proposed decision

30 September 2026. Design only; replaces the earlier snapshot-first recommendation because this review explicitly requires corrections, supersession and retained disagreements. Accepted executable and offline evidence remain exactly 739895df1c613e912560943a443d7a182311e26f: candidate 188, baseline 188, AH regressions 20, spec020 38 and filter 1, all passed with no skips. No new tests or application changes are needed to write this design.

## Recommendation and alternatives

Recommend two small AH-specific tables: immutable source claims and append-only review/relationship events. Reuse existing Site, Application and Document identities and the in-memory AHAssessment adapter. This is ordinary relational storage plus a small history reader, not a general event-processing platform, new agent or new opportunity model.

| Choice | Smallest initial change | Multiple claims | Corrections/review history | Main cost/risk |
|---|---|---|---|---|
| Nullable versioned JSON payload on SchemeIntelligence | One optional column containing a claims array | Yes, if all alternatives retained | Needs immutable snapshot history or internal revision/event arrays and optimistic concurrency | Whole-payload replacement can lose disagreements; growing history rewrites the row; source/relationship integrity relies on application code; extraction owns the row |
| Separate claims + events (recommended) | Two additive tables, one validated writer and one reader adapter | One row per source assertion, no winner overwritten | Append events and replacement claim rows; retain all originals | Slightly more initial schema work; explicit checks for scope, concurrency and relationship validity |

Both can be correct. A payload is smaller only for a frozen snapshot. Once immutable history and review edits are required, a payload plus a separate history mechanism is not materially simpler. The repository has domain-specific append-only precedents (LocalPlanFieldHistory, AllocationVersion, AgentEvaluationHistory); those are not reusable generic AH audit tables. Keep this design AH-specific.

## Proposed storage contract

Names below are proposed, not existing database objects.

### ah_source_claims — one immutable atomic assertion

| Field group | Minimum contents / invariants |
|---|---|
| Identity | claim_id; schema_version; application_id FK; site_id FK when resolved; stable scheme_key; scope_kind (whole_scheme/component/phase/unclear), scope_key and display label; recorded scope basis |
| Metric | affordable_count, tenure_count or affordable_percentage; tenure_name required only for tenure_count. Retirement/specialist housing is a product type, not itself a tenure. Preserve reported tenure text without inventing quantities. |
| Quantity | qualifier exact/approximate/range/at_least/up_to/unknown; either value, lower+upper, lower only, upper only, or no quantity. Nonnegative finite quantities; percentage bounds 0–100; lower <= upper. Do not invent bounds or round counts to a buyer threshold. |
| Percentage context | Explicit numerator/denominator scope and source basis; optional links to supporting count/total evidence. Uncertain denominator means no definitive whole-scheme percentage. No automatic percentage/private-unit derivation in this increment. |
| Source | document_id FK when present, source URL/title snapshot, document content hash/version if already available, verbatim passage plus page/section locator; document_date nullable with explicit missing-date reason. No substitution of download/extraction/review time. One source assertion per row; corroborating documents get distinct claims. |
| Stage/time | reported planning stage proposed/approved/secured/unresolved; stage-support reference where different; document/effective date if evidenced; recorded_at. Reported stage is not accepted merely because a source or extraction labels it secured. |
| Origin | manual evidence capture or extraction; extraction run/model/parser version when known; origin record reference; raw wording; idempotency key for exact replay. Distinct versions or different passages must not deduplicate into one claim. |

`scheme_key` identifies the development interpretation, not just the physical site: different applications on one site are not automatically the same scheme. Prefer an established reviewed scheme/root-application relationship. If absent, keep application-scoped identity and scope unclear; a reviewer must explicitly link it before cross-application use. Component keys remain stable within that scheme. Do not create a separate scheme master-data subsystem for this increment.

Missing source identity/passage/scope may be stored as pending reported evidence, but cannot qualify a quantity. For external evidence without an existing Document row, require an identified URL, captured passage/locator and reviewed link to the application. Reuse Document.content_hash where present; a hash proves captured bytes, not authority or current legal effect. Legacy documents may legitimately lack hashes/dates. Do not imply their original bytes were historically verified.

### ah_claim_events — append-only review and relationship history

Fields: event_id, claim_id FK, optional related_claim_id FK, event_type, reviewer/actor identity, recorded_at, reason, supporting reference and expected prior event/version. Types: accept, needs_review, reject, withdraw, corrects, supersedes, conflicts_with, and resolve_relationship (references the earlier relationship event being resolved). No delete/update of prior claims/events in the application workflow.

Acceptance records the checked claim interpretation: exact versus approximate remains unchanged, evidence basis, scope and accepted stage. A correction creates a new claim and a reviewed `corrects` link to the original. A later operative document may create a new claim with `supersedes`; it does not mutate the old proposal. A new disagreement creates a separate claim and optional explicit conflict link; selection also detects incompatible comparable quantities even without a manually entered link. Resolving a mistaken relationship appends an event referring to that event, never silently removes it.

Correction/supersession links are only effective after explicit review, must relate compatible metrics and scopes, cannot self-link or form cycles, and cannot let a component replace a whole-scheme claim. Cross-application supersession requires an evidenced scheme relationship and reason. If a proposed replacement is rejected or withdrawn, the prior claim is not silently restored as current; selection returns review-required until the relationship is explicitly resolved. Proposal and operative consent can coexist at different stages.

Use a transaction and expected prior event/version check for reviews. Concurrent stale approvals must fail visibly and require reloading, not last-writer-wins. Unique idempotency keys prevent double imports. Existing application permissions must restrict review; if there is no suitable identity/permission mechanism, first increment remains a controlled operator workflow rather than exposing an unauthenticated review form.

## Evidence versus review versus legal stage

These are separate dimensions:

- Pending/unreviewed, accepted, needs-review, rejected and withdrawn describe the review workflow.
- Verified exact means a reviewer checked the exact quantity, identified source, passage, application and scope for its stated stage. It does not mean current legally secured units or availability to acquire.
- Estimated means an accepted source explicitly supports approximation or bounds. A reviewer can verify that a source says “approximately 72”; the quantity remains estimated. Never relabel it an exact verified 72.
- Unknown means no supported useful quantity. An explicit unknown statement has no value or bounds. No stored claim at all also produces unknown, but these origins remain distinguishable.
- Conflicting is an assessment of incompatible, relevant claims, not a reason to delete either source. Review status can be accepted for two faithfully captured claims that conflict with each other.
- Legally secured requires evidence of the operative obligation and scope, separately from checking a proposed quantity. Availability, ownership and buyer suitability are separate questions.

Source-supported zero is an explicit exact numeric zero, backed by a passage covering the relevant scope/stage and accepted by review. An empty field, missing AH mention, missing agreement, technical application or component-only zero is not whole-scheme zero.

## Selection and consumers

Required finding from code review: `_resolve_group_position` in affordable_housing_scope.py currently primarily reconciles candidate percentages and returns one whole-record position. New claim storage must not be placed downstream of that single winner: otherwise independently evidenced counts can still disappear behind a percentage conflict.

Proposed bounded reader:

1. Select eligible application/scheme/phase context using existing operative planning rules. Fetch all claims/events for those linked applications; never all claims on a site indiscriminately.
2. Fold review events to effective claim status and explicitly reviewed correction/supersession relations. Exclude rejected/withdrawn/historical claims from numeric eligibility while retaining a visible audit trail. Pending competitors must be visible; where materially relevant, prevent a definitive current answer until reviewed.
3. Assess count, each named tenure component and percentage independently. Compare only like scopes and stages. Newest timestamp or a higher number never wins by itself. An operative source can supersede a proposal only on documented authority/scope basis; newer proposals do not silently replace consented obligations.
4. Preserve qualified alternatives in the shared assessment. Same-scope material disagreements produce investigation, not cherry-picking. Different components/stages coexist without being falsely labelled conflicting. Do not sum overlapping or incomplete components.
5. A named component can support a minimum lead; it cannot establish a whole-scheme maximum or disprove a whole-scheme minimum from its small count. Component-only zero cannot establish whole-scheme zero. Retain component identity throughout.
6. Both operative and single-application builders use this reader and the existing threshold kernel. When no eligible claims exist, preserve the legacy assessment as reported/unverified; no automatic qualification.

Reuse exact/approximate/range/one-sided rules in spec020. At threshold 50, qualified approximate 45–55 inclusive remains investigate for minimum and maximum. Exact values receive no leeway. Evidenced 60–80 is likely minimum-50, exact quantity unverified; “up to 72” is possible only. Unknown has its explicit unknown-evidence route and never passes a numeric filter, including maximum-only searches. Conflicting alternatives are investigation-only unless every relevant supported alternative establishes failure under the existing joint rule; unsupported relevant alternatives prevent a definitive exclusion.

Search, matching, Explore, detail, feed, packet, dashboard and selected CSV must use the same selected claim projection. Show quantity/bounds, estimate/review label, application, named component, stage and date/source; expose alternatives/history without replacing headline values with unqualified raw numbers. CSV should preserve selected claim IDs, source/scope/qualifiers and alternatives, not a single invented number. This is not a new tenure search engine; explicit tenure evidence informs existing explanations until separately scoped.

Keep retirement/specialist and other independent buyer exclusions. A useful count is not automatically STRONG_FIT and does not establish a package for sale. Existing developer/delivery/contact evidence can support a next action, but no contact-enrichment build is included.

## Three end-to-end traces

30 September 2026 evidence update: the Focus School row below is a historical design trace, not the current source finding. See `AH_SAME_RECORD_REVIEW_20260929.md`, “Superseding Focus School evidence”, for the inspected 23 October 2024 statement and council-confirmed variation/discharge dates. That statement expresses an exact 72-apartment component within 82 homes; all-social-rent is proposed wording until final approved details are inspected. Count qualification does not require pretending the final tenure has been verified. No production import is authorised by this documentation update.

These are design traces. No new authoritative documents were retrieved in this turn. Focus School's operative legal position remains unresolved; the zero example is a synthetic acceptance control, not a claimed verified production site.

| Example | Storage | Selection | Minimum 50 / maximum 50 | Buyer explanation |
|---|---|---|---|---|
| Focus School, DC/085997: reported approx.72 AH retirement apartments in 82 homes, reported10 market houses; disputed whole-scheme100/all_units | Preserve existing raw fields. Create a proposed count claim only when its actual source passage is captured, with named retirement component. Preserve separate whole-scheme percentage/classification evidence and disputes. Total82 remains independently sourced total evidence; 10 market houses stays reported source evidence, never 82−72 arithmetic. OPSO only if independently supported; retirement alone is not tenure. | Today: raw/unlinked remains unverified. After source/scope review: accepted estimated component count72 can survive unresolved whole-scheme100%; final legal stage not upgraded. Claims for condition40/DC/094889 remain pending until inspected. | Today unknown numeric route/investigation relevance. After qualification: likely minimum50; 72-component minimum itself exceeds whole-scheme maximum50 if that component belongs to the same scheme, so maximum50 does_not_meet. A component below50 would not prove a whole-scheme maximum. | “Approximately72 affordable retirement apartments reported within an82-home scheme; whole-scheme percentage disputed; current legal position unverified.” Suitable buyers can investigate. A retirement-excluding buyer remains excluded. No generic “high” label or availability claim. |
| Unknown AH scheme | No qualifying claim, or an explicit reviewed “count not established” claim with no value/bounds; retain any legacy narrative separately | Unknown; absence of AH mention is not zero. A newer unknown record does not supersede a supported older obligation automatically | Unknown for both, accessible by explicit unknown-evidence route; never a numeric match | “Affordable-home count unknown. No source-linked quantity available; investigate the relevant planning evidence.” |
| Source-supported whole-scheme zero (synthetic control) | Exact0 count claim with actual authoritative passage/document identity, whole-scheme scope and evidenced stage; review accepted. No automatic0% or all-private derivation | Select only if current/relevant and not contradicted by an unresolved amendment. Partial/phase zero remains component-only | Minimum50 fails; maximum50 meets the AH quantity criterion. An affordable-package buyer is excluded for supported whole-scheme zero; other buyer criteria remain independent | “0 affordable homes recorded for the whole scheme at [evidenced stage], source [document/date].” No private-count or availability claim. A contradictory current positive source changes this to investigation. |

## Entry and human review

First increment: a bounded operator import of explicitly captured claims from existing documents, with dry-run report and review events. The importer must validate IDs, source link, passage, scope, quantity shape, uniqueness and existing expected revision. Existing raw extraction fields remain untouched. Import is separately authorised work after design approval; no production import is authorised here.

A reviewer sees source passage/link alongside application/proposal, component, quantity form, stage, existing conflicting claims and legacy fields. Accept, reject or request further evidence with a reason; a quantity/scope correction creates a new claim. Preview the resulting buyer/search treatment before acceptance. First increment may use an operator command/report rather than build a general review dashboard. Persist authenticated/reliably attributable reviewer identity; no inferred identity from a model.

Future extraction can emit the same claim envelope, actual document/page evidence and extraction provenance as pending claims. Deterministic validation checks shape and linkage, not truth. The model must never stamp itself verified, infer source dates or silently resolve conflicts. Repeat identical input is idempotent; changed documents create new assertions. Automated promotion to source-qualified estimated status is a later, separately tested policy choice; initial entry is reviewed so this increment does not secretly enable a reprocessing/backfill job. Manual review of the first cohort is not a commitment to manual review of every future extraction.

Legacy figures stay in SchemeIntelligence and remain visible as reported/unverified, including raw zero. They may be investigation candidates in the buyer feed but never qualified approximate counts just because they look plausible. No automatic SQL/prose backfill and no replacement of missing source links with a general application URL. The first source cohort must be established before release, otherwise code alone can suppress existing numeric discovery without delivering qualified leads.

## Minimum viable first increment and gates

Required, after separate implementation approval: two additive tables; validated append-only import/review helper; claim/event reader; independent count/tenure/percentage selection before legacy whole-record winner; common consumer projection; a small reviewed offline source cohort; focused tests below. No generic review platform, scheduling, new AI calls, financial appraisal or broad contact features.

Migration proposal only: create new tables, indexes and foreign keys, no changes/backfill to existing rows. Reuse explicit migration conventions but do not run the broad migrate_schema command blindly: it applies every missing model change. A later reviewed narrowly scoped migration must list exactly these tables/constraints and the target database. Test on disposable SQLite and PostgreSQL; no page-load DDL. New-reader enablement requires schema preflight and explicit rollout; unexpected missing schema when enabled must report an operational error, not silently hide all claims.

Rollback proposal: disable the new reader/writer and restore prior executable through a separately approved release action; retain new tables/history read-only. Do not drop claims or delete event history. Existing raw fields remain unchanged, so legacy reporting remains possible, with its unverified labels. Existing evaluation histories remain intact; do not rewrite fingerprints to look current. Audit access/export must remain possible even when the old executable ignores the new tables.

Focused acceptance: append/correct/supersede/reject/withdraw with history preserved; concurrent review rejection; duplicate import; cross-application/component mismatch; cycle prevention; alternative claims retained; pending conflicting source; proposal versus consent coexistence; unchanged-source import and changed content hash; missing date/hash; exact/approx/range/one-sided validation; verified-source approximate remains estimated; unknown versus raw0 versus supported0; component minimum/maximum; retirement exclusion; independent percentage/count; source stage not legal status; same-record search/detail/feed/packet/CSV; legacy unchanged; fingerprint changes only for effective decision-relevant claim projection, not audit-only comments; no writes/model calls on read; additive migration and non-destructive rollback. Use real documents for source acceptance separately from synthetic code tests.

## Follow-up decision and measurement, 30 September 2026

The Product Owner approved the separate-claims/history direction and controlled validated import boundary, not implementation. [Specification021](../specifications/021-ah-source-claims-first-increment.md) is the controlling proposed first-increment contract: count/explicit tenure only, existing-Document-only imports, exact event/concurrency semantics and shared conservative selection. It supersedes broader first-increment percentage storage or URL-only source options in this proposal.

After explicit confirmation of My Workspace, read-only Render inspection verified all five identified services and their live deployment artifacts at 6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a. Exact-commit source declares matching version4, not5. This is current artifact evidence, not proof about every historical/manual execution. Specification021 section9 records service/deployment IDs. Database attachment again timed out before any query; actual stored combinations remain unknown. Local version5 and production records remain unchanged.

## Earlier production version and stored-impact findings (historical)

Measured live result: none; no SQL query ran and no production count was obtained. Unknown is not zero.

| Question | Result this turn |
|---|---|
| Current deployed matching version | Unconfirmed. Render list_services returned “no workspace selected.” list_workspaces returned My Workspace (tea-d9qbf8jm8hqs7385cu0g), but the connector explicitly requires user confirmation before selecting it. No deploy metadata was read. |
| Supabase access | Existing Property AIgent SQL-editor tab was visible in browser inventory; selecting it failed with Emulation.setFocusEmulationEnabled timeout. A follow-up inventory worked, but did not expose editor/results. No query was entered or executed. |
| Stored mandates / current evaluation tuples / historical tuples | Unmeasured; no result set. No Render-database substitution, no site×buyer estimate, no secret retrieval. |
| Local candidate policy | Source constant remains5 at accepted executable739895d. This is not evidence of production deployment. |

Further code finding: acquisition_evaluate._evaluation_policy_version() records mandate interpretation, acquisition type, transaction signal, terminal exclusion and agent-evaluation versions, but NOT buyer-matching version. AgentEvaluationHistory.evaluation_policy_version cannot establish matching5 by a string search. Matching version is hashed into mandate and agent fingerprints; hashes are not decodable version labels.

Bounded measurement plan when access is available: read live deployment commit for the web service and relevant evaluation workers, then read buyer_matching.py at those exact SHAs (repository HEAD is not deployment proof). Inspect historical deployed commits if asking whether5 was ever used, separately from whether it is live now. In a read-only, time-limited database transaction, inspect table existence first; count mandates by active/archived and baseline-present; count actual distinct (buyer_mandate_id, subject_anchor_id, acquisition_type) current-state and history tuples separately; group by anchor subject_type and current-history presence. Distinguish successful evaluations from failed-only tuples and active from inactive candidates.

For baseline impact, reproduce current mandate inputs under the exact old/new canonical fingerprint rules offline from a bounded read-only export; classify matching-old/matching-new/neither/missing. Neither means other field/version differences, not automatically a v4→v5 count. If mandate history lacks prior inputs, do not claim historical version attribution. For current evaluation impact, compare stored identity to pure recomputation for actual stored tuples only, without calling bootstrap, run_persisted_evaluation, claim acquisition or any model-capable entrypoint. If full historical input snapshots are unavailable, report measured tuple inventory as an exposure ceiling and separately report confirmed changed hashes/unknowns. Never count every historical attempt as a different buyer/opportunity combination.

Retain global5 locally. A v4→v5 change alters otherwise-identical mandate identities broadly; agent fingerprints also embed that mandate identity and policy version. New AH interpretations additionally change effective planning-delivery inputs. A narrower AH component needs coordinated mandate and agent handling, not simply a conditional agent field. If5 already ran with different semantics, agree a new semantic revision before release; do not silently reuse5 or revert4. Audit-only events should not invalidate assessments; source/scope/value/status changes affecting selection should. Reader freshness must label stale/unknown when current identity cannot be established, without evaluating on read. No universal reader freshness guarantee is established by this review.

Changed fingerprints are not model calls. Deterministic baseline refresh, stale-reader indication and future paid evaluation exposure must be counted separately. No automatic refresh or paid call is authorised. P0-A Gate A stays open and discovery stays parked.
