# PropertyAIgent — Product Roadmap Addendum: Planning Policy Monitoring Agent

**Product Owner decision — 17 September 2026**

**Status:** Identified roadmap capability / specification pending. **Not authorised for implementation.**

This addendum forms part of the current PropertyAIgent product roadmap and should be read alongside `PRODUCT_ROADMAP.md`, `PRODUCT_VISION.md` and `PLATFORM_ARCHITECTURE.md`.

## Why this capability has been added

Live product review showed that PropertyAIgent can regenerate a current AI Local Plan / planning-intelligence summary while some of the underlying council policy sources have not been rechecked for several weeks, and some authorities remain disabled or never checked in the monitoring view.

This creates an important distinction that the product must make explicit:

- **AI intelligence last generated** is not the same as
- **underlying authoritative evidence last checked**, which is not the same as
- **underlying evidence last changed**.

A newly generated AI summary must never imply that the source planning-policy position has itself just been reverified.

The current platform therefore has a functioning intelligence-processing layer, but does not yet have a complete always-on policy-monitoring → change-detection → downstream-opportunity propagation loop.

## Capability objective

> **PropertyAIgent continuously monitors authoritative local-planning-policy evidence, detects material change, maintains a current trusted evidence base, updates planning intelligence, and triggers reassessment of affected acquisition opportunities.**

This is complementary to Application Lifecycle Intelligence:

- **Application Lifecycle Intelligence:** Has this individual planning application changed?
- **Planning Policy Monitoring Agent:** Has the wider planning-policy / evidence environment changed, and which allocations, sites and buyer-specific opportunities are affected?

Both ultimately feed the shared trusted evidence layer and the buyer-specific acquisition opportunity universe.

## Target monitoring loop

```text
Authoritative council / policy sources
        ↓
Source change detection
        ↓
Document discovery + version capture
        ↓
Document classification
        ↓
Structured evidence extraction
        ↓
Deterministic comparison with current trusted evidence
        ↓
Material-change classification
        ↓
AI interpretation of commercial / planning significance
        ↓
Human review only where required
        ↓
Trusted planning intelligence update
        ↓
Affected allocations / Sites identified
        ↓
Opportunity classification + Buyer Profile reassessment
        ↓
Commercially meaningful change surfaced to the user
```

The critical product requirement is the final propagation step. Updating a Local Plan summary without changing affected opportunities is not sufficient.

## Monitoring model

The preferred architecture is:

**deterministic monitoring and change detection first; AI interpretation second.**

The agent must not independently browse, infer and overwrite trusted policy facts without evidence controls.

The policy-monitoring capability should build on the existing evidence-first architecture rather than becoming a separate ungoverned AI process.

## Expected source coverage

The source register should ultimately cover, where relevant for each authority:

- adopted Local Plan / development-plan documents;
- emerging Local Plan documents;
- Regulation 18 / Regulation 19 material;
- policies maps / interactive policy-map evidence;
- Authority Monitoring Reports;
- Five Year Housing Land Supply statements;
- Housing Delivery Test results / Action Plans;
- housing trajectories;
- Local Development Schemes;
- allocation / site-selection updates;
- examination material and Inspector correspondence;
- relevant housing-need and delivery evidence-base documents;
- other authority publications that materially alter allocation, housing-supply or delivery intelligence.

The exact source register remains an implementation/design question and should reuse the monitored-report/document infrastructure already present in the platform where possible.

## Proposed cadence hypothesis

Cadence is not yet authorised as implementation detail, but the current product hypothesis is:

- **Daily lightweight monitoring:** check registered authoritative source pages / known documents for new versions or material change.
- **Weekly deeper discovery:** look for new or previously unregistered policy/evidence documents.
- **Event-driven downstream processing:** only re-extract/reconcile/reassess where a genuine source change is detected.

There is no requirement for minute-by-minute monitoring; policy evidence does not justify that cost or complexity.

## Freshness model

The product should distinguish and expose at least three separate timestamps/states:

1. **Source last checked** — when PropertyAIgent last checked the authoritative source.
2. **Evidence last changed** — when the underlying evidence most recently changed / a new version was detected.
3. **Intelligence last generated** — when the AI interpretation was last regenerated from the stored evidence.

Example of a trustworthy state:

```text
Source checked: 17 Sep 2026
Evidence changed: 16 Sep 2026
Intelligence updated: 17 Sep 2026
```

Example requiring an explicit warning:

```text
Source checked: 04 Aug 2026
Intelligence updated: 17 Sep 2026
⚠ Source verification overdue
```

A recent AI timestamp alone must never be presented as evidence freshness.

## Human-review model

The current product hypothesis is three handling paths:

### 1. Auto-process

For a clearly identified replacement/update to an already trusted authoritative source where classification is unambiguous and the extraction/change comparison passes deterministic checks.

### 2. Auto-process + flag material change

Where the source is authoritative and understood, but the change is commercially/planning-significant — for example housing requirement, five-year supply, allocation status, plan stage or delivery trajectory.

The evidence can be processed automatically, while the resulting material change is surfaced for review/audit where appropriate.

### 3. Manual review

For:

- unknown document type;
- ambiguous planning status;
- conflicting authoritative evidence;
- low-confidence extraction;
- unclear replacement/supersession relationship;
- material change that cannot be deterministically interpreted.

The objective is to avoid making every routine authoritative update dependent on manual approval while preserving human control at true ambiguity boundaries.

## Downstream propagation requirement

This capability is not complete if it only refreshes the Council Dashboard or AI Local Plan summary.

A material policy change must be able to propagate through the product where relevant:

```text
Policy evidence change
    → allocation / policy intelligence changes
    → affected Sites / opportunities identified
    → trusted opportunity facts / strategic-land evidence updated
    → Buyer Profile fit reassessed
    → buyer-specific opportunity universe updated
    → user sees the commercially meaningful change
```

Examples include:

- an allocation advancing, being removed or materially changing capacity;
- an emerging Local Plan moving stage;
- a changed housing-supply position;
- a revised housing requirement;
- a changed delivery trajectory;
- new examination evidence affecting allocation certainty or timing.

The platform should surface the consequence, not merely produce fresher prose.

## Relationship to the acquisition-first architecture

This capability strengthens the shared trusted market-evidence layer that the Acquisition Agent will eventually consume.

Target relationship:

```text
Application Lifecycle Intelligence ─┐
                                    ├─→ Trusted evidence layer
Planning Policy Monitoring Agent ───┘           ↓
                                      Opportunity universe
                                                ↓
                                       Buyer-specific fit
                                                ↓
                                       Acquisition Agent
```

Planning Policy Monitoring is therefore infrastructure for acquisition intelligence, not a separate policy-research product.

## V1 non-goals

The roadmap does **not** currently authorise:

- autonomous rewriting of trusted planning facts without provenance/evidence controls;
- predictive policy or consent scoring;
- minute-by-minute polling;
- a new unrestricted web-research agent operating outside the trusted evidence model;
- valuation, comparables, residual appraisal or financial modelling;
- regenerating every AI summary on a schedule when underlying evidence has not changed;
- treating a freshly generated AI summary as a freshly verified source position.

## Product sequencing decision

This capability is now formally on the roadmap, but **it is not automatically the next implementation gate**.

The Product Owner is currently using the development pause to run live product validation — including affordable-housing extraction, RP opportunity discovery, opportunity propagation and UX/workflow assessment.

The next implementation priority should still be selected from observed commercial blockers after that validation.

Planning Policy Monitoring should be promoted ahead of competing workstreams if validation confirms that stale policy evidence / incomplete source monitoring repeatedly causes incorrect or missed acquisition conclusions.

## Future architecture investigation questions

Before implementation, the specification should establish:

1. Which existing monitored-report / policy-document infrastructure can be reused unchanged?
2. Why monitoring is disabled or stale for particular authorities today.
3. Which source types can be safely auto-classified and auto-accepted.
4. How source versioning and supersession are represented.
5. What constitutes a **material policy change** versus a document/text change.
6. Which changes require re-running allocation intelligence versus only updating metadata.
7. How affected Sites / opportunities are identified efficiently.
8. How policy changes trigger Buyer Profile / opportunity reassessment without unnecessarily recomputing the entire universe.
9. How monitoring health is surfaced separately from AI-processing health.
10. How failures, inaccessible council sources and overdue checks are handled without implying evidence is current.
11. Whether the appropriate scheduler remains Render, moves to Trigger.dev, or uses another orchestration layer — to be decided from operational requirements, not preference.
12. How this capability interacts with Gate 2B-0B Application Lifecycle Intelligence without duplicating monitoring infrastructure.

## Acceptance outcome for a future V1

A future Planning Policy Monitoring Agent should not be considered successful because it generated a new Local Plan summary.

It should be able to demonstrate an auditable chain such as:

> authoritative policy source changed → PropertyAIgent detected the change → captured/versioned the evidence → extracted the changed fact → explained the material significance → identified affected allocations/Sites → reassessed relevant opportunities/buyers → surfaced the meaningful change with provenance.

Until that chain exists, policy monitoring remains incomplete.
