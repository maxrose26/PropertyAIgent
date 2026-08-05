# PropertyAIgent — User Journeys

This document describes the intended end-to-end experience for each of the platform's four primary user types, as the capability stack described in [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) is built out. For what each capability actually is, see that document; for why the layers are sequenced this way, see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md).

Every journey below follows the same underlying shape, because there is one Site Intelligence Engine underneath all four user types (see [PRODUCT_VISION.md](PRODUCT_VISION.md)):

```
Search site
    ↓
Planning history
    ↓
Policy review
    ↓
Visual evidence
    ↓
Market intelligence
    ↓
Development economics
    ↓
Planning assessment
    ↓
Generate professional report
```

Today, the platform delivers the first three steps of this chain in full (Planning Intelligence and Policy Intelligence, including visual evidence) and stops there. Every journey below is written as **Current workflow** (what exists today), **Future workflow** (the next capabilities that extend it), and **Ultimate experience** (the full chain once every layer is built).

---

## Developer

**Role in the lifecycle:** Assessing whether a specific opportunity is worth taking forward — usually already aware of a site, needing to quickly establish whether it stacks up.

**Current workflow:**
Search or browse Sites in the platform → review planning history (every related application consolidated onto one Site, phase-tracked) → review the Site's policy position (which Local Plan allocation it sits in or near, its status and progression) → review any visual evidence (site plans, allocation maps, masterplans) already extracted for that Site or allocation → make a manual pursue/don't-pursue call using everything above, taking the remaining research (values, costs, viability) outside the platform.

**Future workflow:**
The same first four steps, now followed inside the platform by real market context (comparable schemes, land values, build costs) and a first-pass residual appraisal, so the commercial "does this stack up" question is answered with real figures rather than the developer's own estimate.

**Ultimate experience:**
Search a Site, and within minutes have planning history, policy position, visual evidence, market context, a residual appraisal with sensitivity analysis, and an AI-generated planning assessment explaining the planning balance — each claim traceable to its source — culminating in a professional report the developer can act on or hand to a colleague without re-doing the research.

---

## Planning Consultant

**Role in the lifecycle:** Building the evidenced planning case for a Site — the professional whose output *is* the planning judgement, produced for a client or for submission.

**Current workflow:**
Search or open a Site → review consolidated planning history and every prior application's outcome → review the Site's Local Plan/allocation status, progression signal, and the underlying policy evidence (housing requirement, delivery position, five-year supply) with full source provenance → review extracted visual evidence (allocation boundaries, site-specific policy pages) → take all of this outside the platform to draft a planning statement or supporting statement by hand.

**Future workflow:**
The same steps, but with an AI-generated first-draft planning assessment — a planning balance narrative built strictly from the evidence already gathered by Planning and Policy Intelligence — available as a starting point rather than a blank page, with every claim in it traceable to the source document and page it came from.

**Ultimate experience:**
Full evidence gathering (planning, policy, visual, market, viability) followed by an AI-assisted planning statement or supporting statement draft that already cites the platform's own evidence base — turning what is currently days of manual research and drafting into a review-and-refine task.

---

## Land Promoter

**Role in the lifecycle:** Building and sustaining the case for allocation or permission over a long promotion timeline, where policy and market context change continuously and need to be tracked, not just checked once.

**Current workflow:**
Track a Site's allocation status and progression through the platform's ongoing policy monitoring (change-protected, so nothing shifts silently) → review policy document coverage to know what evidence still needs chasing → review visual evidence already extracted for the allocation → manually track market conditions and prepare promotion materials outside the platform.

**Future workflow:**
The same ongoing monitoring, now paired with market intelligence that also updates over time (so a promoter can see when market conditions start supporting a stronger case) and an early Development Economics view of likely viability, informing when and how hard to push a promotion.

**Ultimate experience:**
Continuous, monitored visibility of a Site's policy position, market context and viability throughout a multi-year promotion, with AI Decision Support generating and refreshing Call for Sites submissions and site promotion documents as the underlying evidence changes — rather than a promoter manually re-assembling the case from scratch at each plan stage.

---

## Investor

**Role in the lifecycle:** Assessing risk and return across a pipeline of opportunities, typically at a later stage of the development lifecycle than a developer or promoter, and typically across many Sites at once rather than one at a time.

**Current workflow:**
Search and filter Sites (including natural-language search) → review planning history and build-status (has this actually progressed) → review policy position → review visual evidence → assess risk/return manually outside the platform using the developer/promoter's own figures.

**Future workflow:**
The same filtering and review, now including real market intelligence (values, comparables) so an investor can compare Sites on consistent, evidenced figures rather than developer-supplied ones, and an early Development Economics view giving an independent viability check.

**Ultimate experience:**
A filterable, evidenced pipeline of Sites, each with planning history, policy position, market context, an independent viability appraisal with sensitivity analysis, and an AI-generated investment recommendation explaining its reasoning against the underlying evidence — allowing an investor to triage a large pipeline down to the Sites that genuinely warrant deeper diligence, with a professional report ready to support that diligence.
