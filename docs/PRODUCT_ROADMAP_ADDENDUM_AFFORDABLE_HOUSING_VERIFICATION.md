# PropertyAIgent — Product Roadmap Addendum: Affordable Housing Verification Agent

**Status:** Identified / specification pending — **not yet authorised for implementation**  
**Product Owner decision:** Add a dedicated Affordable Housing Verification capability to the roadmap as a specialist trust/verification agent beneath the acquisition-intelligence layer.

## 1. Why this capability exists

Affordable housing is one of the most commercially important and error-prone data domains in PropertyAIgent. A headline number can be numerically extracted correctly while still being commercially or legally misleading because the source may refer to a different application, phase, parcel, legal status, denominator, grant assumption or viability position.

Examples of the failure modes this capability is intended to prevent include:

- `0 affordable homes` where the true state is unknown, conflicted or present in another application;
- a technical/condition-discharge application overriding the substantive permission's affordable-housing position;
- a unit count from one source being paired with a percentage from another;
- `54 on-site affordable homes / 37%` plus a `3% financial contribution` being flattened to `54 homes = 40%`;
- a proposed affordable-housing position being presented as agreed or legally secured;
- grant-supported delivery being treated as a planning obligation;
- phase-specific affordable housing being presented as the whole-site obligation, or vice versa;
- S73 / variation evidence replacing affordable-housing facts it did not actually vary;
- specialist / extra-care / supported housing inflating general-needs affordable housing totals;
- `up to`, `minimum`, indicative or viability-dependent values losing their qualifiers;
- stale or superseded affordable-housing evidence remaining buyer-facing after stronger evidence exists.

The commercial objective is not simply to improve extraction accuracy. It is to establish a **trusted, auditable operative affordable-housing position** that can safely feed Housing Association / RP searches, private housebuilder exclusions/preferences, opportunity qualification, reporting and future Acquisition Agent reasoning.

## 2. Core objective

> **Continuously audit affordable-housing facts across the database, identify records that are missing, inconsistent, conflicted or low-confidence, investigate the supporting planning evidence more deeply where necessary, and produce a verified operative AH position with provenance — without silently overwriting history or manufacturing certainty.**

The agent is a verification and investigation layer, not the system of record by itself. Authoritative facts remain evidence-backed and auditable.

## 3. Target verification loop

```text
Existing affordable-housing facts
        ↓
Deterministic consistency checks
        ↓
Internal evidence verification
        ↓
Conflict / uncertainty detection
        ↓
Deeper authoritative-source investigation where needed
        ↓
Fact-level reconciliation
        ↓
Verified / conflicted / unresolved AH position
        ↓
Provenance + verification state retained
        ↓
Affected opportunity / buyer-fit reassessment
```

The preferred design principle is:

**deterministic validation first → bounded evidence investigation second → AI interpretation only where useful → trusted reconciliation → downstream propagation.**

An unconstrained LLM must never directly rewrite planning truth.

## 4. Facts the capability should verify

The verification model should cover, where evidence supports it:

- affordable units;
- affordable percentage;
- affordable tenure;
- tenure unit split / percentage split;
- on-site affordable units;
- on-site affordable percentage;
- off-site affordable provision;
- financial contribution / commuted sum;
- overall policy-equivalent contribution where explicitly evidenced;
- proposed / applicant-offer / officer-recommended / committee-approved / agreed / S106-secured / legally secured status;
- grant dependency / Homes England / council-funding dependency;
- viability reduction;
- review mechanisms / deferred contributions where evidenced;
- minimum / maximum / `up to` / indicative qualifiers;
- whole-site / phase / parcel scope;
- relevant application / permission / S106 source;
- general-needs vs specialist / extra-care / supported / later-living distinction;
- evidence date / verification freshness;
- superseded or historic positions.

No single application is assumed to control every AH fact.

## 5. Verification stages

### Level 1 — Database consistency audit

No external search required.

Flag suspicious records such as:

- AH = 0 while another linked substantive application contains AH > 0;
- units and percentage that do not reconcile arithmetically where they are expected to share a denominator;
- 100% AH with missing or contradictory tenure evidence;
- AH sourced from withdrawn, refused, screening, condition-discharge or other ineligible applications;
- proposed AH shown as legally secured;
- a later S73 becoming operative without explicit AH-change evidence;
- phase and whole-site figures being flattened together;
- `unknown` becoming zero;
- duplicated or contradictory AH positions;
- unit count / percentage / tenure assembled from different source applications without an explicit deterministic rule;
- grant-funded delivery being represented as planning-required provision;
- specialist housing counted as general-needs affordable housing without supporting evidence.

This stage should be cheap, deterministic and capable of prioritising which records genuinely need deeper investigation.

### Level 2 — Internal evidence verification

Use evidence already held by PropertyAIgent before searching externally.

Candidate evidence includes:

- planning statements;
- affordable-housing statements;
- committee / officer reports;
- decision notices;
- S106 / heads of terms;
- viability statements / summaries;
- reserved-matters and variation documents;
- already-ingested supporting documents and SchemeIntelligence provenance.

Core question:

> **Can the current AH position be proven or reconciled from evidence PropertyAIgent already holds?**

If yes, no deeper external search should be required.

### Level 3 — Deeper authoritative investigation

Where internal evidence is missing, stale or contradictory, investigate authoritative sources more deeply, subject to approved access methods and rate limits.

Preferred source order:

1. council planning portal / official application documents;
2. decision notice / committee report / officer report;
3. S106 / planning-obligation documents / heads of terms;
4. official council / public-sector publications;
5. developer or RP material as corroborating context only where authoritative planning evidence is unavailable.

Press articles, marketing pages and general web sources must not silently outrank authoritative planning evidence.

### Level 4 — Unresolved / human review

Where credible sources remain inconsistent, ambiguous or incomplete, return an explicit unresolved state rather than forcing a value.

Examples:

- conflicting same-scope legally credible AH positions;
- unclear denominator;
- ambiguous phase relationship;
- missing executed S106;
- grant-dependent uplift with no evidence that funding was secured;
- unclear specialist/general-needs split.

The correct outcome may be **REQUIRES_MANUAL_REVIEW**.

## 6. Verification-state model

A future implementation should consider a bounded, explicit state model such as:

- `VERIFIED_SECURED`
- `VERIFIED_AGREED`
- `VERIFIED_PROPOSED`
- `VERIFIED_GRANT_DEPENDENT`
- `VERIFIED_VIABILITY_REDUCED`
- `VERIFIED_ZERO`
- `CONFLICTED`
- `INSUFFICIENT_EVIDENCE`
- `REQUIRES_MANUAL_REVIEW`

Exact names are not approved by this roadmap entry; the principle is approved: **verification status must describe the legal/evidential position, not merely extraction confidence.**

A generic `HIGH CONFIDENCE` label must never be allowed to mean both:

- “we are confident this number was extracted from a document”; and
- “we are confident this is the current operative AH obligation.”

Those are different trust dimensions.

## 7. Provenance and auditability

Every verified operative AH fact should ultimately be capable of carrying:

- value;
- unit / percentage / tenure semantics;
- source application reference;
- application role;
- source document;
- page / excerpt where available;
- evidence date;
- scope (whole-site / phase / parcel);
- legal/status position;
- extraction confidence;
- verification status;
- verification date;
- reason this source outranks or does not outrank alternatives;
- prior / superseded position where commercially relevant.

Verification must be non-destructive. Existing extracted values and historic positions should not be silently overwritten or deleted.

## 8. Hard trust rules

The following principles are mandatory for any implementation:

1. **Unknown must never become zero.**
2. **Policy target must never automatically become the agreed obligation.**
3. **Proposed must never automatically become secured.**
4. **Grant-supported delivery must remain distinct from planning-required provision.**
5. **On-site unit count, on-site percentage and wider policy-equivalent contribution must remain semantically distinct.**
6. **Whole-site and phase obligations must not be flattened.**
7. **S73 / variation authority is fact-specific, never application-wide by recency.**
8. **Administrative / technical / screening / condition-discharge records cannot establish an operative AH position unless the relevant fact is explicitly eligible under trusted reconciliation rules.**
9. **Tenure must not be invented from absence or generic affordable-housing language.**
10. **Specialist / extra-care / supported housing must not inflate general-needs AH counts without explicit evidence.**
11. **Conflicting credible evidence must surface as conflict rather than be hidden by a convenient fallback.**
12. **The agent may investigate; trusted evidence determines the fact.**

## 9. Relationship to existing architecture

This capability must build on, not replace:

- Gate 2B-1 Scheme / Application / Phase Reconciliation;
- Trusted Operative Planning Facts;
- decided-state-aware affordable-housing reconciliation;
- application-role eligibility;
- phase/scope handling;
- evidence provenance;
- lifecycle/freshness infrastructure.

It is a **specialist evidence-verification capability beneath the Acquisition Agent**, not a new parallel opportunity engine.

Conceptually:

```text
Shared planning evidence
        ↓
Trusted planning reconciliation
        ↓
Affordable Housing Verification Agent
        ↓
Trusted operative AH position
        ↓
Opportunity facts / Buyer Fit / RP or housebuilder mandate interpretation
        ↓
Future Acquisition Agent
```

The capability should verify shared evidence once and allow many buyer mandates to interpret it differently.

## 10. Downstream propagation requirement

Verification is incomplete if the corrected AH position only appears in one detail view.

A material AH verification/change should eventually be capable of triggering bounded reassessment of:

- Trusted Operative Planning Facts;
- opportunity facts;
- Buyer Fit;
- Housing Association / RP opportunity relevance;
- private-housebuilder AH exclusions/preferences;
- buyer-facing Dashboard / Explore / Scheme Detail outputs;
- reports / exports;
- future Acquisition Agent state.

A corrected source value must not coexist indefinitely with stale opportunity logic using the old value.

## 11. Buyer-specific value

### Housing Association / RP buyers

The capability should eventually enable queries such as:

> “Show me schemes with 50–300 verified affordable homes, distinguish legally secured from proposed, identify tenure and grant dependence, and keep unresolved packages in a separate verification queue.”

100% affordable schemes may be highly relevant rather than excluded.

### Private housebuilders / land buyers

The same verified evidence supports rules such as:

> “Exclude 100% affordable schemes and prefer schemes below 50% AH, but do not reject a site because AH is merely unknown.”

The underlying evidence is shared; the commercial interpretation is buyer-specific.

## 12. Initial backlog / real-case acceptance set

Future design and validation should include known difficult cases already identified by live review, including where still present:

- Former Burnage Cricket Club — ancillary zero vs substantive AH position;
- Brixham Road — on-site units / on-site percentage / wider contribution semantics;
- Hazelhurst Farm — whole-site vs phase AH;
- World of Pets — conflicting quantum and AH evidence / upstream extraction quality;
- Stockport Rugby Club — withdrawn / specialist evidence leakage;
- Lacy Street — grant-dependent AH vs planning obligation;
- Jenny Lane / Woodford Road — minimum / high-AH uncertainty;
- East of Chew Moor Lane — `up to` AH wording;
- Tongfields — high-AH / tenure extraction;
- Pinfold / Edenfield — zero-AH certainty from weak/non-objection evidence;
- at least several genuine 100% affordable schemes;
- at least several true verified-zero schemes.

A pass should require both correct values **and** correct legal/status/scope meaning.

## 13. Monitoring / rerun strategy

Do not repeatedly run expensive web research over the entire database without cause.

Preferred long-term pattern:

- one initial full-corpus consistency audit;
- deeper investigation only for flagged / incomplete / materially important cases;
- re-verification triggered by relevant lifecycle/document changes;
- periodic lightweight re-check of stale high-value AH evidence;
- event/change-driven downstream reassessment rather than full-universe LLM reruns.

Exact cadence and cost controls require a separate architecture investigation before implementation.

## 14. Human-in-the-loop policy

Human review should be reserved for ambiguity that genuinely matters, not every clean evidence update.

Potential future paths:

- **Auto-verify:** one authoritative, internally consistent source; no competing evidence; semantics clear.
- **Auto-process + flag:** strong source but commercially material qualifier/change deserves review visibility.
- **Manual review:** conflicting authoritative sources, ambiguous scope/denominator/legal status, or low-confidence evidence.

The final rules for automatic writes are **not approved by this roadmap entry**.

## 15. Non-goals for V1

Do not use this capability as an excuse to add:

- valuation / GDV / residual appraisal;
- comparable evidence;
- generic AI opportunity scoring;
- new Buyer Profile ranking models;
- a new planning graph unless a proven acceptance case requires it;
- uncontrolled whole-web browsing;
- autonomous owner/developer outreach;
- destructive rewriting of historic SchemeIntelligence;
- speculative availability / seller-intent inference;
- a cosmetic AH dashboard redesign before evidence semantics are trustworthy.

## 16. Roadmap sequencing

**Roadmap status:** capability identified and promoted into the product roadmap; implementation sequencing remains subject to the current validation cycle.

Recommended pre-implementation sequence:

```text
Affordable Housing / RP live product audit
        ↓
Field-level extraction + reconciliation findings
        ↓
Repository / architecture investigation
        ↓
Define V1 verification contract + write policy
        ↓
Bounded full-corpus consistency audit
        ↓
Controlled deep-verification cohort
        ↓
Production rollout only after Product Owner acceptance
```

This capability should be considered ahead of more sophisticated RP / Housing Association recommendation logic if the live audit confirms that AH data quality is the binding constraint.

It does **not** automatically outrank all other roadmap work. The Product Owner will choose sequencing after the current Astra/product-validation cycle establishes whether AH verification, lifecycle freshness, policy monitoring, opportunity propagation, ownership/control or another gap is the highest-value blocker.

## 17. Relationship to Planning Policy Monitoring Agent

The two newly identified specialist monitoring/verification capabilities are complementary:

- **Planning Policy Monitoring Agent:** asks *“Has the authoritative policy/evidence environment changed, and which opportunities are affected?”*
- **Affordable Housing Verification Agent:** asks *“Is this scheme’s affordable-housing position actually correct, current, scoped and legally/evidentially understood?”*

Both must ultimately feed the same trusted evidence → opportunity reassessment pipeline rather than become isolated AI-summary generators.


## 18. Post-Astra Audit Amendment — Affordable Housing Truth Layer is a prerequisite

**Product Owner decision following the 17–18 September 2026 live Affordable Housing / RP audit:** the Affordable Housing Verification Agent remains a roadmap capability, but it must **not** be the first implementation step. The audit demonstrated that the immediate architectural gap is a trusted, evidence-resolved affordable-housing position that the agent can verify and update.

The live audit found that PropertyAIgent can extract useful AH counts and tenure labels, but it is not yet reliable at selecting the current commercially applicable AH position. Confirmed failure modes included:

- absence of AH evidence becoming a false zero;
- correct AH counts paired with the wrong scheme denominator;
- whole-site and phase evidence being mixed across screens;
- grant-dependent delivery losing its qualifier;
- proposal / policy / agreed / secured meanings being collapsed;
- non-tenure content appearing in tenure fields;
- buyer-fit language treating unresolved AH as trusted;
- corrected or conflicted intelligence failing to propagate consistently across Dashboard, Explore, Detail and AI summaries.

### New prerequisite capability — Affordable Housing Truth / Operative Position Layer

Before a verification agent is authorised to write or promote conclusions, PropertyAIgent should establish one reusable, evidence-resolved AH position **per development scope**.

Conceptually, that position should be capable of representing, separately and without semantic flattening:

- physical affordable units;
- the denominator those units relate to;
- affordable percentage;
- on-site percentage;
- off-site provision;
- financial contribution / commuted sum;
- overall policy-equivalent contribution where explicitly evidenced;
- tenure and tenure split;
- proposed / recommended / agreed / S106-secured / legally secured status;
- grant dependency;
- viability outcome and review mechanism where evidenced;
- minimum / maximum / `up to` / indicative qualifiers;
- whole-site / phase / parcel scope;
- general-needs vs specialist / extra-care / supported housing;
- source application, document, date and passage;
- extraction confidence;
- operative-fact confidence;
- verification freshness;
- conflict / unresolved state.

A value of zero requires affirmative evidence applicable to the selected scope. **No mention / not found / not extracted / unknown / not applicable / confirmed zero are distinct states and must never be collapsed.**

### Revised sequencing

```text
1. Correct confirmed P0 AH data defects
        ↓
2. Affordable Housing Truth / Operative Position Layer
        ↓
3. Affordable Housing Verification Agent
        ↓
4. Shared downstream propagation
   Dashboard / Explore / Scheme Detail / AI Summary / Buyer Fit / reports
        ↓
5. RP / Housing Association qualification improvements
        ↓
6. Re-run the same difficult Astra cohort as release acceptance
```

The Verification Agent therefore becomes an **exception-driven investigator** over unresolved or suspicious AH positions, not a roaming agent that re-researches every scheme indiscriminately.

### Verification queue principle

Long-term preferred flow:

```text
Raw planning evidence
        ↓
AH extraction
        ↓
AH scope / legal-status reconciliation
        ↓
Trusted Affordable Housing Position
        ↓
Resolved? ── yes ──> downstream consumers
   │
   no
   ↓
Affordable Housing Verification Agent
        ↓
existing internal evidence review
        ↓
authoritative external investigation where needed
        ↓
verified / conflicted / manual-review result
        ↓
Trusted Affordable Housing Position updated non-destructively
        ↓
bounded opportunity + buyer reassessment
```

### Acceptance principles promoted from the audit

A future release should not pass unless the difficult regression cohort demonstrates all of the following:

1. no unknown becomes zero;
2. no AH percentage uses an incompatible denominator;
3. no whole-site position is silently attached to a phase, or vice versa;
4. grant-dependent intended delivery is not presented as secured planning obligation;
5. tenure contains tenure concepts only;
6. proposed, recommended, agreed and legally secured positions remain distinct;
7. specialist housing is not silently treated as general-needs AH;
8. unresolved AH cannot produce language such as “trusted” or an unqualified Strong Fit;
9. the same development scope produces the same AH position across every buyer-facing surface;
10. a correction to the trusted AH position triggers bounded downstream reassessment rather than leaving stale opportunity logic in place.

### Initial confirmed P0 acceptance cases

The live audit promotes these cases into the initial implementation/acceptance cohort:

- **Cross Lane / former Ship, Salford** — false zero from “AH not mentioned”;
- **Woodford Garden Village Extension** — wrong operative scheme scale/status and AH quantum;
- **Viadux Phase 2** — wrong denominator;
- **Stretford Mall** — whole-scheme AH mixed with Reserved Matters phase;
- **Hazelhurst Farm** — multiple incompatible site/phase totals;
- **Lacy Street** — grant-dependent intended AH presented without sufficient qualification;
- **Brixham Road** — physical on-site homes vs financial contribution semantics;
- **World of Pets** — later scheme quantum vs historic scale;
- **Focus School / Brotherton House** — specialist / whole-scheme 100%-AH classification and tenure semantics.

This amendment does **not** authorise implementation. It changes the required architecture and sequencing for the already-identified Affordable Housing Verification capability.


## 19. Product-owner implementation boundary

This roadmap entry is **documentation only**.

It authorises:

- future architecture investigation;
- future specification work;
- use of the AH/RP audit to define acceptance criteria.

It does **not** authorise:

- schema changes;
- production writes;
- full-database reprocessing;
- new scheduled agents;
- external web-search automation;
- AI-driven overwrites;
- deployment.

Implementation requires a separate Product Owner-approved gate after the current validation cycle.
