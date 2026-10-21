# Intelligence rules: prioritised gaps and next decisions

21 October 2026. Source baseline `9e906b0f0edc8e79b5c245c678f7f69cbe840bdf`; see the [Rules Index](INTELLIGENCE_RULES_INDEX.md) for definitions, code, consumers, meaningful test assertions and open-PR identities. This is documentation-only. No production inspection, new intelligence policy, implementation, model run, source request or deployment is authorised.

## Decision summary

The platform has useful, often conservative rule foundations. The highest-value next improvement is **consistent evidence meaning from screening through persistence and buyer presentation**, not more scraping or a new agent framework. Preserve existing scope/qualifier/unknown safeguards. Finish already-scoped count work, use the existing AH trust programme, and close selected provenance/consumer seams only where acceptance examples show a material difference.

“Test-covered” below means inspected test assertions, not a new passing-suite or deployment claim. Historical audits and named sites remain dated evidence. Uncertain coverage is never converted to a supported negative result.

## Prioritised gap register

Priority reflects risk of an incorrect acquisition conclusion, then missed opportunity, avoidable operating cost and delivery dependency. It is a proposed work order, not permission to expand Stage 4.

| ID / priority | Finding and strength of evidence | Practical consequence | Existing owner / minimum response |
|---|---|---|---|
| G1 — High, missed opportunities and wasted extraction | **Reproduced legacy qualifier defect:** master `qualify` returns 5/non-qualifying for 5 houses + 5 flats; returns 12/qualifying for conversion of twelve flats into a hotel. Exact pure probe output is archived. Later reconciliation may withhold; no production incidence claimed | Genuine 10-home proposals can be screened out; existing-stock counts can buy detail/document processing without new residential supply | Claude's existing 035 work / PR #166; no competing counter or re-screening run |
| G2 — High, user trust | **Specified target, incomplete integration:** 035 v2's per-count proposed/approved basis, permission evidence, revision and headline/search rules are not the inspected master implementation. Master already has active/consented derived positions, so this is not a complete absence of separation | A later proposed 52-home revision can be mistaken for an approved 49-home scheme; mixed scope and legacy scalar display can change search eligibility silently | Complete the existing staged 035 contract-to-consumer mapping; keep unresolved approval UNKNOWN and show match basis. Do not implement policy here |
| G3 — High, AH commercial interpretation | **Verified representation/coverage limitation:** AHAssessment explicitly leaves operative terms unverified; scoped AH positions and legacy classifier/reconciliation do not establish the full proposed/required/secured/delivered, tenure/funding truth promised by the AH addendum | An RP may pursue an unsecured or wrong-scope package; a private buyer may reject a scheme on a sibling phase's or unqualified 100% figure | Existing AH Truth / Operative Position prerequisite, not an autonomous verification agent. Reuse AHClaim/alternatives and require legal-stage evidence independently |
| G4 — High if a bypass reaches users; incidence unproven | **Verified legacy write-path limitation:** `reconcile_scheme` derives an on-site zero from legacy status buckets without structured claim provenance at that assignment. AH read adapters deliberately downgrade legacy numbers and scope logic prevents several historical false-zero cases | A permissive caller could treat a derived zero as verified; unnecessary repair could also overwrite valid historical evidence | Map writer-to-consumer reachability first. Confirm a specific failing consumer or keep this a contained risk; do not declare every zero invalid or blanket-clear data |
| G5 — High impact, hypothesis not established defect | **Cross-layer risk:** legacy Site grouping accepts weaker exact-address/parent matching than strict G2 containment. No specific inspected consumer bypassing G2 is established | A shared address/citation could be mistaken for common development scope, disjoint phases or available residual capacity | Preserve strict G2 and current residual guards. Only a concrete failing path warrants correction; no general scheme graph rewrite |
| G6 — Medium/high freshness, known capability boundary | **Verified code/design limitation:** new Document rows can have a normalised text content_hash, but URL/name dedup is not a known-document revision revisit. Source comments/model and 031 explicitly retain this limitation | An amended notice or condition may not enter later assessment just because a hash column exists; stale facts can appear settled | Existing 030/031 risk-based freshness and document-delta decision; prioritise material sources, no full-corpus redownload |
| G7 — Medium/high title interpretation, no current coverage measurement | **Specified/implemented distinction is sound:** Certificate A declaration, S106-defined roles and corporate PSC records do not prove present land title, beneficial land ownership or disposal authority. Broader current title/control verification is not established | Wrong counterparty or false “available” inference if wording is inflated | No new extractor now. Preserve evidence labels and source/scope warnings; targeted title/option investigation remains separately gated |
| G8 — Medium, delivery dependency | **Verified future capability:** owner-only correction history/commands are specified in 036; existing Site.excluded or generic operator access is not that workspace | A “manual correction” could disappear, be overwritten or be visible to other operators if built carelessly | Stage 7 implementation prerequisites already explicit: owner guard, identity mapping, durable supersession/stale-save handling. Not a Stage 4 gate |
| G9 — Medium, auditability | **Verified heterogeneous contracts:** dates, locators, revision hashes and rule versions exist in different carriers and are optional in legacy records. No universal required document-date/revision/assessment-method field applies to every claim | A downloaded timestamp can be read as a decision date; an unqualified legacy scalar can gain false authority when copied | Align adapters to existing carrier contracts; retain unknowns and document the loss. No universal evidence-store redesign |
| G10 — Low/medium, maintenance | **Verified documentation drift / deliberate duplication:** `pipeline/evidence.py` says Document has no hash although the model has content_hash. AH status ranks are repeated for layer isolation; G2's role literal has parity coverage | A contributor might add redundant hashing or change one vocabulary without its consumer | Correct stale wording in a future focused docs change; add parity acceptance where a changed vocabulary needs it. Duplication alone is not a user defect |

## Explicit no-change-needed findings

**Related documentation alignment:** integrated 036's introductory size-criterion wording still names a supported proposed total; the separately open 035 v2 now explicitly includes an applicable proposed **or approved** count. 036 delegates admission/headline/search rules to 035, so it must track that adopted version when integrated rather than becoming a competing admission definition. This is a concrete cross-specification wording dependency, not permission for this assessment to alter either specification or settle unrelated open 035 decisions.

- **Count qualifiers and scope arithmetic:** keep CountAssessment bounds/precision, same-scope supersession and explicit non-overlap/completeness requirements. A parent 180 and nested 72 must not become 252; this already has meaningful regression coverage.
- **AH read containment:** keep coherent per-application positions, current-versus-historical separation, alternatives, “operative terms unverified” wording and unknown-not-zero consumers. Do not replace them with a generic confidence score.
- **Party roles:** keep distinct planning declaration/S106/mortgagee labels and company-versus-land scope. Applicant frequency, director status and corporate PSC data do not confer stronger land rights.
- **Planning/progress:** keep committee-unissued permission, conditions activity, physical commencement/completion, verification time and source fact date separate. No general “last seen” freshness shortcut or new status taxonomy is justified.
- **Relationships:** keep exact direct-parent G2 derivation and no automatic multi-hop traversal; no non-overlap from same-Site membership. No new relationship service is justified.
- **Buyer fit/recommendations:** keep deterministic fit separate from admission, commercial recommendation and next action. Preserve evidence-reference validation, independent buyer context and failed-evaluation-keeps-prior-success behaviour. Do not change recommendation labels or begin model benchmarking through this task.

These findings mean the existing semantics are adequate for their bounded purpose, not that every production record or consumer has been reverified.

## At most three next work packages

### 1. Finish the existing 035 count evidence and admission programme

**Outcome:** avoid false residential exclusions and prevent proposed/approved count ambiguity from contaminating scheme admission, headlines and search. This is the existing Claude-owned programme, not a new implementation branch commissioned by this assessment.

**Scope:** use 035 v2 and its versioned examples/read-model design. Agree its outstanding decisions in one review; record decisions already settled rather than asking again. Keep proposal-text assessment, durable evidence/promotion and user-facing search migration as independently accepted phases. Preserve the immutable v1 screening record; no live re-screening is implied.

**Acceptance:**

- Existing 035 examples reproduce supported component counts and do not count removed/existing dwellings, beds, blocks or commercial units as new homes.
- Nine flats + one commercial unit remains nine dwellings; possible commercial interest is retained without inventing a residential admission exception.
- Approved and proposed counts retain their own scope/source/date/revision/qualifiers. Forms cannot establish consent; a legitimate revised proposal is not automatically an approved-count conflict.
- Admission and buyer fit are independent; no pending Application is created merely to represent a retained identity or unsupported factual claim.
- Headline and Approved/Proposed/Either results follow the adopted 035 contract and disclose match basis, including the approved-49/proposed-52 case. Reference-model tests are distinguished from production consumer tests.
- Replay/idempotence and source-to-committed-readback proof are demonstrated only within separately approved disposable/production scopes. No current record repair or source execution follows this assessment.

**Dependencies:** PR #166, explicit decision record, existing shared admission/B2 and 036 dependency alignment. PR #163's disposition is decided by its owner, not this branch.

### 2. A narrow AH truth-to-consumer conformance slice

**Outcome:** ensure the same evidenced AH position reaches screening/qualification, profile, exports and buyer reasoning without implying legally secured or delivered provision.

**Scope:** begin with retained/synthetic cases from the existing AH addendum and 029 remediation. Trace the legacy status-to-zero write, AHAssessment qualification and actual consumers. Reuse AHClaim, scoped positions, alternatives and existing evidence storage. Resolve the smallest legal-stage/denominator/tenure representation gap in the existing AH contract before proposing any additive storage change. No new verification agent, models, external documents or broad production repair.

**Acceptance:**

- A 20%/97-home substantive position survives an unknown-zero condition filing; a phase's 100% does not become a whole-site claim.
- Distinguish proposed, policy-required, agreed/secured and delivered evidence; a count source alone establishes none of the other stages.
- Preserve on-site units, off-site/financial contributions, denominator, tenure, specialist scope and grant/viability qualifiers independently; missing evidence remains unknown.
- The legacy bucket-to-zero path is either contained by every relevant consumer with an explicit warning, or a specific defect is reproduced and corrected with a focused regression. Do not use this assessment as evidence of widespread live corruption.
- Same-scope current evidence produces consistent qualified output across the selected consumers; conflicting/historical evidence is retained and cannot silently become current buyer fit.

**Dependencies:** existing AH addendum/029; any unresolved legal-stage decision and write contract returned together for review. This is proposed follow-on trust work, not a new Stage 4 completion condition.

### 3. Targeted evidence-version and consumer-boundary acceptance

**Outcome:** prevent stale or wrongly scoped evidence being promoted when facts flow into acquisition decisions, with bounded ongoing operating cost.

**Scope:** one retained fixture chain spanning a revised document, planning check, scoped relationship and buyer packet. Reuse 030/031, G2 and current FactPosition/CountAssessment/AHClaim/ControlRelationship fields. Inventory exact adapter losses and revision-detection limits. Start with disposable/retained evidence; do not activate a document revisit, schedule or general title investigation.

**Acceptance:**

- A document hash is labelled normalised-text identity, never claimed as original PDF bytes; a known URL/name is not proof that its latest revision was checked.
- Source date, issued decision date, successful verification, observation and assessment timestamps are distinct; unknown historical dates are not backfilled by guesses.
- Same-site/citation/PSC evidence cannot become phase non-overlap, current land title or saleability in the selected packet/report consumer.
- A revised proposal cannot overwrite permission; failed verification preserves earlier accepted evidence with truthful freshness; material changes affect only dependent outputs.
- Method/rule version and evidence references survive the adapters, or missing fields produce an explicit limitation. No universal model migration is required unless a concrete missing field defeats the accepted contract.
- Any proposed later retrieval has finite subject/request/time/byte bounds, a material relevance reason, and separate operational approval under 031.

**Dependencies:** affected domain contract owners, PR #164 for any eventual partial-observation enablement, and separate Stage 7 authority for owner commands. This package is a conformance boundary, not a general agent platform.

## Proposed roadmap adjustment — sequencing clarification only

Keep existing stages and accepted gates. Add this index as the cross-domain entry point, then:

1. Continue the already-active 035 work before another count policy or general screening rewrite.
2. Preserve the AH Truth / Operative Position Layer before the AH Verification Agent, as already required by the addendum; validate a narrow consumer slice before authorising wider work.
3. Link 030/031 freshness and evidence-version limitations to later operational acceptance. Keep 036 owner correction persistence in Stage 7, independent of buyer saved decisions.

No additional global dependency is introduced. Stage 4 may be reviewed against its existing bounded pipeline/source/evidence criteria with explicit gaps and held scopes; it is not required to finish AH, ownership, search UI, manual review or all historical applications first. Conversely queued gaps are not complete coverage and source success is not factual acceptance. Stages 5–8 evidence maintenance remains subject to its explicit operational approval; this index activates nothing.

No existing roadmap status is rewritten here: concurrent roadmap edits are avoided by placing the proposed adjustment in this document and linking the index from the specification directory. No merge, release or production repair follows this draft PR.

## Evidence and limitations

The manifest records inspected master blobs and separate PR #166 v2 references. Pure reproduction uses four synthetic proposal strings against the inspected legacy qualifier, with no database, browser, network source or model. No existing application test suite was repeated, no new test pass total is claimed, and no retained council observation was repeated. Historical deployment/production figures in specifications are not current measurements. Full-corpus prevalence, all UI surfaces, paid/model factual entailment and external source truth remain unverified.
