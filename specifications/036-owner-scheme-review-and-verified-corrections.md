# 036. Owner Scheme Review and Verified Corrections

Status: **agreed product scope; documentation-only draft for review; not implemented.** Version `owner-scheme-review-v1`. Roadmap placement: **Stage 7 extension**. This document authorises no implementation, migration, release, source request or production execution. Stage 4 remains OPEN; this workspace is not an additional Stage 4 completion gate.

## 1. Purpose and dependencies

Provide a small owner-only Scheme Review workspace inside the existing application. Resolve materially uncertain planning applications into evidence-backed scheme assessments, select specific further investigation and preserve verified corrections. The product outcome is acquisition intelligence: identifying, qualifying and monitoring opportunities that can subsequently be matched to buyer strategies.

Scheme admission is shared and buyer-independent. A supported proposed total of **10 or more residential dwellings** meets the current size criterion for scheme ingestion and deeper assessment. It establishes neither commercial suitability nor availability nor an acquisition recommendation. Retain valid below-threshold identities and evidence for reassessment without automatic promotion.

Dependencies and controlling contracts:

| Dependency | Contract / intended reuse |
|---|---|
| Stage 4 discovery, evidence and screening | [032](032-stage4-stable-credential-pipeline.md), existing WorkItem/WorkAttempt coordinator and durable capture references; no second queue |
| Sparse observations | [033](033-verified-records-under-unknown-window-completeness.md); [034 proposal at PR #164](https://github.com/maxrose26/PropertyAIgent/pull/164): observed record evidence remains separate from window completeness |
| Residential count, admission and presentation | [Specification 035 / PR #166](https://github.com/maxrose26/PropertyAIgent/pull/166) owns admission, headline-count presentation and **Approved / Proposed / Either** search behaviour, alongside its versioned count rules and acceptance corpus. Consume that contract; do not implement parallel rules in this workspace |
| Count trust and qualifiers | [023 Stage 2](023-stage2-commercial-evidence.md), [024](024-stage2-5-buyer-discovery-and-opportunity-decomposition.md), [025](025-stage2-5b-acquisition-subject-decomposition.md); preserve exact/qualified/conflicting/unknown and scope distinctions |
| Application, Site and scheme identity | [004](004-core-domain-model.md), existing application-to-Site reconciliation; no new generic Scheme entity is prescribed |
| Stage 1 access | [020](020-stage1-access-command-boundary.md), existing server-owned identity, admission and revocable leases |
| Stage 6 interface conventions | [Product Experience Roadmap](../docs/PRODUCT_EXPERIENCE_ROADMAP.md), [UI design system](../docs/UI_DESIGN_SYSTEM.md); reuse existing application components |

At inspection on 21 October 2026, specifications 034 and 035 are on separate open PRs, not master. Links deliberately target those PRs until integration; do not copy their evolving rules or assume implementation. Their branch/date labels do not establish production state. Agreed decisions for this workspace are buyer-independent admission, the proposed-gross-total size criterion, separate proposed and approved positions, and delegation of admission, headline-count presentation and Approved / Proposed / Either search behaviour to 035. These are not open product questions in 036. The inspected PR #166 head `c0513f61fc90ea2e092ab0bdda966558986e2521` does not yet record the approved/proposed presentation and search alignment; synchronising that controlling specification is a documentation dependency, not permission to invent local fallback rules. This change does not edit Claude's separate branch or infer acceptance of unrelated proposals in 035.

## 2. Roadmap placement and domain boundaries

Stage 7 has two distinct deliverables:

- **Owner Scheme Review:** shared scheme evidence, verified corrections, scheme linking and bounded research-task requests.
- **Buyer decisions and saved opportunities:** a particular buyer's strategy, interest and investment decisions. Existing buyer isolation remains authoritative.

Review status, automated screening assessment, scheme admission and task execution are independent states. A completed review can leave an investigation blocked; an open review does not erase a previously supported fact. This version is neither a CRM nor an autonomous acquisition agent.

Use “Scheme Review” as the workspace label, with Site as the existing physical identity anchor. An Application is a council submission, not a Site; SchemeIntelligence is currently per application, not a canonical multi-application scheme. Resolve the exact scheme/phase identity mapping before implementation (section 12). Never infer shared site, phase or progress from a citation alone.

## 3. Owner-only access

Authorise **before loading any review data** and before every command. Protect navigation, direct URLs, endpoints, downloads, exports, caches and background read paths. General users must not receive the inbox, unresolved review records, internal notes or owner controls through ordinary surfaces. Published scheme facts continue to follow their separate approved publication/access rules.

Reuse Stage 1's verified identity and server-owned policy. The intended boundary is the authenticated human owner identified by the policy's issuer plus `owner_subject`, with an active admitted lease and appropriate command permission. An operator role alone is insufficient; machine principals and other operators are denied. Do not hard-code an email or an unverified account ID, accept client-supplied roles, or rely on a hidden button. Missing/expired/revoked policy fails closed. Additional reviewer roles are deferred.

## 4. Entry and prioritisation

Enter review when resolving uncertainty could materially change treatment:

- Residential development evident, proposed dwelling count unknown.
- Supported sources conflict on proposed totals for the same application/phase scope and revision.
- Approved and proposed positions cannot be reliably attributed to their scopes or revisions; a legitimate approved-scheme/proposed-revision difference alone is not a count conflict.
- Existing, demolished, retained and proposed dwellings are mixed.
- Quantities may refer to blocks, bedrooms, bedspaces or a wider development.
- Amendment/condition wording suggests a larger parent scheme.
- Potential duplicate or uncertain existing scheme membership.
- New evidence materially challenges a verified assessment.

Clear qualifying cases follow the automatic path. Clear minor works and known below-threshold cases remain retained without routinely filling the inbox. Prioritise potentially qualifying cases using explainable reasons; retain a small separately labelled QA sample of exclusions. Sample size/selection is an implementation acceptance decision, not an unrestricted review feed or retrieval allowance. Inbox membership is not commercial attractiveness.

## 5. Review experience and evidence contract

Provide a bounded, searchable list with stable pagination and an evidence panel. Opening, searching or paging performs no new source retrieval. Define finite page/payload limits before implementation acceptance; do not load the entire corpus into a session.

Show:

- Council, exact reference, address and validated source link.
- Literal proposal with truncation/ambiguity explicitly marked.
- Observation time and distinct relevant council dates.
- Retained document excerpts and citations, when available.
- Current screening result, rule version and actionable review reason.
- **Proposed and approved dwelling counts shown separately**, each with its application/reference, Site/phase scope, evidence and supporting citation, relevant source/decision dates, observation time, proposal/permission revision and qualifiers. Unknown approval remains UNKNOWN; never substitute the proposed figure.
- Existing and demolished counts, supported net change, calculation and evidence, attached to the relevant scoped position.
- Mixed-use components recorded separately: residential dwellings and commercial units are distinct measures.
- Related-application leads, prior observations and established scheme links with their verification state.
- Previous owner decisions and material changes since the reviewed snapshot.

Missing fields remain UNKNOWN. Distinguish listing evidence, document evidence, automated interpretation and owner verification. Preserve qualifiers and conflicts; do not convert a qualified maximum to an exact verified total. An application form can support a proposed quantity but **cannot establish approval**. Owner verification confirms an evidence-backed assessment; it cannot manufacture planning consent, grant an application or promote proposed quantities into approved facts. Approval requires applicable authoritative consent evidence under the controlling contract. Verification also does not establish delivery, availability or commercial relevance.

Distinguish conflicting proposed totals within the same scope/revision from a legitimate difference between an approved scheme and a proposed revision. Retain both positions with their evidence and chronology; do not label the latter a conflict merely because the numbers differ, average them or overwrite approval with a later proposal. Uncertain scope, revision or supersession remains explicitly unresolved. Admission, the user-facing headline count and Approved / Proposed / Either search behaviour are defined by **035**, not by review-list state or an owner-selected preferred number.

Citations retain complete literal references, supporting wording, offsets, source field and snapshot/hash provenance. An explicitly stated relation differs from an inferred one and remains an unverified lead until independently supported. Match retained evidence first using exact council/reference where supported; ambiguous/cross-council targets stay unresolved. No automatic parent crawling or new request occurs on review open or link selection.

## 6. Residential-count acceptance examples

Use the versioned rules and corpus in specification 035; the following are required review acceptance cases, not an alternative counting algorithm. Keep proposed total, existing, demolished and net change separate. Apply the current 10+ size criterion to the supported **proposed total**, not net increase. Do not equate bedrooms, occupants, blocks or commercial units with dwellings or sum ambiguous/overlapping counts.

| Proposal wording | Expected assessment |
|---|---|
| Erection of five houses and five flats | 10 proposed dwellings; meets size criterion |
| Ten dwellings comprising five houses and five flats | 10 proposed dwellings; do not double-count breakdown |
| Demolition of five houses and erection of twelve flats | 12 proposed; 5 demolished; net increase 7 |
| Four apartment blocks containing 49 apartments | 49 proposed dwellings |
| Conversion of offices into twelve flats | 12 proposed dwellings |
| Conversion of twelve flats into a hotel | Existing flats do not establish proposed residential supply |
| Erection of six flats | 6 proposed dwellings; below current threshold |
| Mixed-use development of nine flats and one commercial unit | 9 proposed residential dwellings; 1 commercial unit recorded separately, never 10 dwellings. Preserve potential commercial relevance without inventing an admission exception; admission follows 035 |
| Residential development with no supported count | Proposed count UNKNOWN; review or specific further investigation |

If evidence cannot safely establish a qualified quantity or scope, withhold the exact total and show the limitation. This workspace creates no exception to factual acceptance contracts. A human correction to a record cannot establish council-window completeness, absence, newly submitted status or coverage/watermark advancement.

## 7. Actions and independent outcomes

| Action | Consequence |
|---|---|
| **Qualify scheme** | Confirm supported admission criteria and create or link the correct scheme for deeper assessment, independently of current buyer profiles |
| **Investigate further** | Record a specific research task, missing evidence, purpose and finite proposed scope |
| **Below current threshold** | Retain supported count, evidence and reason; no promotion |
| **Outside current residential scope** | Retain with explicit evidence-backed exclusion reason |
| **Defer** | Keep unresolved with reason and optional eligibility/review date |
| **Link to existing scheme** | Associate with the verified existing development scope without duplicating it; available alongside an appropriate review outcome |

Do not offer overlapping “keep”, “add to database” and “add to queue” controls. A correction is not an execution permission. Investigation creates or references a task through the existing durable coordinator, with dependencies, priority, eligibility, evidence, attempt history, applicable limits and next permitted action. Unsupported, deferred and safety-blocked work remains visibly non-executable. Task creation never grants scraping, paid processing, barrier release or bypass of existing stops. A child application may preserve a useful lead without full child extraction.

## 8. Persistence, concurrency and history

Every saved decision must durably record application identity (council/reference and ledger identity even without an Application row), existing application/Site/scheme/phase identity where established, actor, timestamp, decision, reason, evidence snapshot/version/hash, original automated assessment and rule version, corrected fields and calculation, supporting citations, resulting link/task identity and supersession lineage. For each corrected count retain whether it is proposed or approved, the exact application/phase scope, source/decision dates, revision and qualifiers; recording a review never changes the planning status of its source.

Original sources, observations and automated outputs remain immutable. Supersede a decision with a recorded reason; never silently overwrite it. Later automation preserves verified corrections. Material new conflicting evidence flags reassessment and explains the change while retaining both assessments; no silent source preference erases conflict.

Use idempotent commands, durable decision identity and an expected evidence/decision version to reject stale edits explicitly. Repeated submissions must not duplicate schemes or tasks. Review save, scheme/link effect and task request need a reviewed transaction or recoverable reconciliation boundary; do not claim atomicity across separately committed effects. Uncertain persistence blocks repeating effects pending reconciliation. Decisions survive logout, browser restart and a new session.

Storage design remains an implementation prerequisite, not a schema approval. Reuse existing evidence references/hashes and work ledger where suitable; neither Site.excluded nor a browser session alone supplies the required decision history. Do not create pending Applications merely to display ledger-held identities.

## 9. Feedback and learning

Verified corrections may become candidate evaluation/regression examples, carrying provenance and rule versions. Scheme-specific corrections do not silently change general counting/admission policy. Evaluate proposed rule improvements against verified positive, negative and related-application examples before a separately approved release. Automatic training, rule changes and model promotion are outside v1; manual correction alone is not autonomous machine learning.

## 10. Acceptance criteria

Require inspectable evidence that:

1. Only the authenticated owner loads or acts on review data, including direct URLs/endpoints; non-owner operators, machines, readers and signed-out users are denied before data loading.
2. Clear cases follow automatic processing; materially uncertain cases enter review with actionable reasons; QA exclusions are separately labelled.
3. Proposed and approved counts remain separate with application/phase scope, evidence, dates, revisions, qualifiers and original automated assessment. Neither an application form nor owner verification establishes consent; missing approval remains UNKNOWN.
4. Every section 6 example produces its expected assessment under the versioned 035 contract, including nine flats plus one commercial unit remaining nine dwellings. Same-revision proposed-count conflicts are distinguished from legitimate approved/proposed revision differences; headline and Approved / Proposed / Either search behaviour follow 035 without local overrides.
5. Qualification creates or links the correct scheme once, with no buyer-profile prerequisite; below-threshold identities remain retained.
6. Research tasks preserve purpose, missing evidence and existing execution controls without authority issuance.
7. Decisions survive new sessions and support explicit supersession with audit history.
8. Material changed evidence prompts reassessment without erasing prior decisions or silently replacing accepted facts.
9. Duplicate submissions, concurrent saves and stale evidence versions have explicit safe outcomes; uncertain effects reconcile before replay.
10. Ordinary pages, APIs, exports, caches and downloads do not leak internal review data or controls to general users.
11. Partial observations never acquire completeness, absence or coverage claims through review or correction.
12. Feedback examples do not automatically alter production rules or models.

## 11. Version-one scope and retention

Include the owner inbox, evidence review, supported corrections, decisions, scheme linking, specific research-task creation and audit history within the existing application.

Defer separate admin app/frontend rebuild, reviewer teams/complex permissions, bulk editing, CRM/outreach, automatic learning/training and broader scheme-admission exceptions. No new source or model invocation is implied.

Retention remains an open policy decision. Preserve existing evidence under the interim rule in 033 and the 034 proposal. Introduce no pruning, automatic expiry or deletion mechanism here; expiring execution authority does not delete evidence or unresolved work.

## 12. Inspection findings and concrete unresolved architecture questions

Inspection baseline: master `82988cbecfc2b76537a329dddb4eeb1819fbbbfd`. Repository evidence is source inspection, not a current production readback.

| Finding / conflict | Minimum resolution before implementation |
|---|---|
| `app/security/access.py` has server-owned issuer/owner_subject and reader/operator grants; `require_operator` does not restrict human operators to the owner | Add a reviewed owner-only guard reusing the existing policy and lease validation; decide command names and prove pre-load denial. No new auth platform |
| `app/db/models.py`: Application.site_id links to Site; SchemeIntelligence is unique per application; specification 004 describes a Development concept but no Development model appears in the inspected schema | Decide which existing Site/phase identity the “qualify/link scheme” command commits against, and distinguish evidence grouping from a Development delivery entity. Do not invent a parallel scheme table implicitly |
| Site.excluded/reason/timestamp are a coarse mutable exclusion; they do not implement versioned corrections or protected review history | Specify the smallest durable decision/supersession representation, stale-version guard and read/publication overlay, with disposable migration rehearsal if needed |
| Ledger-held identities need not have an Application; count proposal 035 Phase B admission/promotion is not integrated | Review must reference council/reference plus immutable ledger evidence before Application creation. Confirm promotion transaction and shared-writer/recovery seam before implementing qualification |
| The buyer-independent proposed-gross-total criterion and proposed/approved separation are agreed. 035 remains a separate open PR; its inspected text has not yet incorporated the agreed headline/search alignment | Cross-reference the aligned 035 version for admission, headline count and Approved / Proposed / Either search. This is a documentation synchronisation dependency, not a request to decide these principles again. Older scalar paths require an explicit implementation mapping; no alternate extractor or fallback policy here |
| Proposed and approved scoped assessments must coexist, while current scalar fields do not by themselves supply complete revision/evidence history | Resolve the smallest durable representation and read overlay for both positions, including authoritative approval evidence, qualifiers and stale-version handling, before correction writes. No schema or consent inference is authorised |
| 033 distinguishes record truth from completeness; 034 ledger enablement is a separate proposal | Consume accepted receipt/observation contracts explicitly; no review-driven watermark or source completeness repair |
| Product Experience Roadmap proposes an Administration navigation treatment; visibility alone is not security | Owner-only server checks precede UI work. This extension is Stage 7 shared evidence, not buyer saved decisions or a new Stage 4 gate |
| Existing roadmaps mix historical production claims and later gated work | Keep historical records intact; this document states planned requirements only and makes no fresh production claim |

## 13. Later implementation sequence (requires separate approval)

1. Resolve section 12's identity, persistence/overlay and count-contract dependencies; agree bounded inbox/QA limits and command contracts.
2. Implement owner-only service/read/command guards and durable decision history with stale-edit/idempotency tests; rehearse any additive migration and rollback non-destructively.
3. Connect retained evidence and versioned count assessments; add scheme/link and research-task orchestration through existing writers/coordinator with recovery boundaries.
4. Build the bounded workspace using Stage 6 conventions; verify denied direct access, ordinary-user non-disclosure and no retrieval on open.
5. Run section 10 acceptance, independent security/data review and a separately approved release plan. No Stage 4 milestone, operational activation or autonomous learning follows automatically.
