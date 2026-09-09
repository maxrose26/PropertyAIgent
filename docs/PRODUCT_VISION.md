# PropertyAIgent — Product Vision

This is the platform's North Star. Every other document in `docs/` and every specification in `specifications/` should be readable as a more detailed expression of what's written here. Where a future decision is unclear, this document — not a sprint brief, not a UI mockup — is the tie-breaker.

See also: [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) (how the vision is built), [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) (in what order), [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md) (the rules every feature follows), [USER_JOURNEYS.md](USER_JOURNEYS.md) (what it feels like to use).

---

## Mission

Property AIgent is an AI-native residential land and development opportunity intelligence platform. It continuously identifies development opportunities from fragmented UK planning and policy evidence, builds the richest possible evidence-backed understanding of each one — centred on the **Site** or Local Plan allocation it belongs to — and helps the people who evaluate, promote, permission and invest in development opportunities determine why an opportunity matters, who it may suit, and what to investigate next.

*(Product Vision & Roadmap Refresh, post–Opportunity Experience V2: this restates, rather than replaces, the platform's founding mission below. The original wording described building understanding of an opportunity; the platform has since shipped the first real instance of *identifying* one — deterministic opportunity signals, a Dashboard discovery feed, and an Opportunity Profile — so the mission now says what the product actually does, not only what it will eventually understand. Every substantive commitment in the original mission is preserved: evidence-backed, Site-centred, serving the same four user groups, judged by the same "faster, better-evidenced decisions" standard.)*

## The Acquisition-First Commercial Outcome

*(Product Owner decision, Acquisition-First Roadmap Alignment: the platform's product direction has been sharpened, not replaced. Planning intelligence — everything above — remains the trusted evidence layer the rest of this section depends on; it is no longer treated as the end product.)*

> **PropertyAIgent continuously turns fragmented planning, ownership and development evidence into ranked acquisition opportunities matched to a buyer's strategy.**

The platform's evolution reads as one continuous chain, each stage depending on the trustworthiness of the one before it:

```
trusted evidence → opportunity detection → opportunity qualification →
buyer-specific acquisition intelligence → prioritisation →
monitoring/workflow → human acquisition decision
```

**The primary unit of product value is the QUALIFIED BUYER-SPECIFIC ACQUISITION OPPORTUNITY** — not the planning application, not the planning record, and not a search result. A planning application matters because of what it establishes about an opportunity; an opportunity matters because of what it means for a specific buyer's mandate. See [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) for the gate sequence this now drives, and [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) for the revised conceptual architecture.

## Vision

Today, understanding a single development opportunity means separately searching a council planning portal, a GIS constraints viewer, Companies House, a policy document library, and a market-data provider — then manually holding all of it in your head at once. PropertyAIgent's vision is that this synthesis happens once, automatically, and continuously, and is presented back as a single coherent picture of the Site — not a pile of documents the user still has to read and reconcile themselves.

The long-term ambition is for a user to open a Site and immediately understand everything relevant about that opportunity: what's happening on it, what planning policy says about it, what it's worth, whether it's commercially viable, and what a professional planning judgement on it would be — each claim traceable back to the evidence it came from.

## Site, Allocation, and Opportunity

The **Site** remains the platform's core data object, per `CLAUDE.md`: the physical development opportunity, everything else exists to describe, explain, enrich, predict or connect to it. A **Local Plan Allocation** is a distinct object — planning intent, not a physical Site — that may relate to zero, one or several Sites, and is frequently the *only* evidence a genuinely early opportunity has (a strategic allocation with no matched Site yet is real policy intent, not an empty record waiting for one).

**Opportunity** is the product-experience term for whichever of the two a user is actually looking at: a Site with a real planning signal (approaching lapse, undeveloped permission), or an allocation with a real strategic-land signal (no or partial identified planning activity against its stated capacity). This is a presentation-layer generalisation, not a third data model — Opportunity Experience V2 (2026) is the first capability built at this level, and it deliberately keeps the two types distinct (a planning/delivery Site is never given an invented strategic-land classification, and vice versa) rather than merging them into one synthetic entity. See [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §2 "Opportunity Intelligence" for what is built today versus what remains future direction.

## AI-Intelligence-First, Evidence-Grounded

PropertyAIgent is an **AI-intelligence-first, evidence-grounded platform**. This is a deliberate, explicit product principle, not an implementation detail.

The deterministic/structured layer — extraction, matching, relationship-building, capacity/coverage calculation, review workflows, source preservation — is essential infrastructure. It is not, on its own, the intended customer experience. Its job is to build a reliable factual foundation the AI can reason across; the customer should not normally need to scan a page of deterministic fields and assemble the conclusion themselves. The AI layer's job is to turn that foundation into concise, commercially useful intelligence.

The intended presentation hierarchy, wherever an AI-narrated summary exists for an object, is:

```
AI INTELLIGENCE                  (what this means, at a glance)
        ↓
KEY DETERMINISTIC METRICS        (the numbers the AI's narrative is grounded in)
        ↓
SUPPORTING DETAIL                (everything else the platform holds)
        ↓
SOURCE EVIDENCE / AUDIT TRAIL    (the original document, page and method)
```

This does not relax the evidence-grounding safety principle above — a synthesised summary is only trustworthy because the deterministic layer beneath it is trustworthy. It does mean the AI is expected to *reason*, not merely *relay*: synthesising multiple facts, identifying material patterns, distinguishing settled fact from open uncertainty, and pointing at what's worth investigating next — see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) for how this is implemented today in the Policy Intelligence layer.

## Target Users

- **Developers** — assessing whether a specific opportunity is worth pursuing and what it would take to bring it forward.
- **Planning consultants** — building the evidenced case for a site: planning history, policy position, constraints, and the professional judgement that ties them together.
- **Land promoters** — building the strongest possible case for allocation or planning permission, and needing to track policy and market context over the long promotion timeline.
- **Investors** (institutional, SFH, BTR, affordable housing providers, registered providers) — assessing risk and return across a pipeline of opportunities, often at a different stage of the development lifecycle than a developer or promoter.

All four groups are asking variations of the same question — *"is this Site worth acting on, and what do I need to know before I do?"* — from different vantage points and at different stages of the same lifecycle. PropertyAIgent is one Site Intelligence Engine underneath all of them, not four separate products.

## Problems PropertyAIgent Solves

- **Fragmentation.** The evidence needed to judge a Site is scattered across a dozen unconnected systems (planning portal, policy PDFs, GIS, Companies House, market-data providers), each with its own interface and its own gaps.
- **Manual synthesis.** Even when a professional finds all the relevant evidence, turning it into a judgement — is this deliverable, is it viable, is it worth pursuing — is manual, repeated from scratch for every site, and rarely written down anywhere reusable.
- **Evidence decay.** Planning policy, market conditions and site status all change continuously. A one-off manual search goes stale immediately; nothing re-checks it.
- **Lost provenance.** Manually-assembled site files rarely preserve *why* a conclusion was reached — which document, which page, which figure it came from — making the work hard to trust, hard to audit, and hard to hand over.

## What Makes This Different from Planning Portals or GIS Systems

A planning portal shows applications. A GIS system shows spatial layers. Neither shows a *Site* — the physical opportunity a professional actually cares about, which regularly spans multiple applications, sits inside a policy allocation the portal doesn't know about, and only becomes understandable once its evidence is connected together.

PropertyAIgent is not a bigger, better version of either. It is the connective layer above them: it consolidates fragmented source records into one Site-centred record, keeps that record current through ongoing monitoring rather than one-off scraping, and uses AI strictly to *explain and interpret evidence that has already been gathered deterministically* — never to invent facts a source document doesn't actually contain.

## Long-Term Ambition

PropertyAIgent should become the operating system for evaluating UK residential development opportunities: the first place a professional opens when a Site enters their pipeline, and the place that already has more evidence attached to it, at higher confidence, than they could have assembled by hand in the same time.

Opportunity Experience V2 marks a real shift in what "opening the platform" means: the product is organising itself around **Opportunities** — things worth investigating — rather than presenting itself as a database of planning records a user has to search and filter to find one. The long-term direction this points toward, not yet built, is a platform that continuously processes evidence and surfaces something conceptually like *"12 opportunities identified for you this week"* — each already carrying its own reasons, evidence, planning status, planning activity, strategic-land context, monitoring changes, buyer fit and recommended next investigations. Search and the underlying database of Sites, Applications and allocations remain essential infrastructure; they simply stop being the entire product experience, the same way a search index is essential to a search engine without being the product a user thinks they're using.

### The Commercial Product Journey

The long-term acquisition journey this platform serves, independent of which specific capability is built at any given time:

```
DISCOVER → UNDERSTAND → INVESTIGATE → MATCH → MONITOR → CONTACT → ASSESS → DECIDE
```

| Stage | Question | Current Property AIgent capability |
|---|---|---|
| Discover | Where are opportunities worth looking at? | **Built** — Dashboard Opportunities feed (Opportunity Experience V2), Allocation Discovery, Explore |
| Understand | What is this opportunity, in plain terms? | **Built** — Opportunity Profile / Site Profile, deterministic why-it-matters and key metrics |
| Investigate | Why does it matter, and what's uncertain? | **Partially built** — deterministic reasons, evidence gaps and entity-level Applicant Intelligence (Gate 2A, closed) exist; the decision-defensible *operative* planning position (Gate 2B, next) and agentic synthesis (Opportunity Analyst) do not yet |
| Match | Who is this opportunity valuable to? | **Built (deterministic)** — persistent Buyer Profiles and deterministic `assess_buyer_fit` (Gate 1: Acquisition Monitoring Substrate, closed); the agentic Buyer Analyst / Acquisition Agent interpretation layer above it does not yet exist |
| Monitor | Has anything material changed? | **Built (deterministic, opportunity-level)** — stable opportunity identity, fingerprinting and NEW/MATERIALLY_CHANGED/UNCHANGED/BASELINE_EXISTING change detection exist platform-wide (Gate 1 + Gate 1C, closed); agentic "does this change matter for this buyer" interpretation does not yet |
| Contact | Who do I need to reach, and how? | **Foundation strengthened** — Companies House/contact enrichment per-company, on demand, now paired with entity-level Applicant Intelligence organisation classification (Gate 2A, closed); ownership/control resolution beyond Site/Application scope and recommended-route reasoning do not yet exist |
| Assess | Does this stack up commercially? | **Not built** — Market Intelligence and Development Economics (Phase 2); acquisition qualification (Gate 2B/2C) comes first, see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) |
| Decide | Should I pursue this? | **Always human** — see "Evidence-First, Agent-Assisted, Human-Decided" below; the platform is not designed to ever answer this on a professional's behalf |

This table is a map of gaps, not a committed build order — see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) for how the next stage to invest in is actually chosen.

### Acquisition-First UX Direction (not a redesign — direction for future work)

A future primary scheme overview should be answerable against five acquisition questions, in this order: *does it fit the buyer; how close is it to planning/delivery; can it realistically be acquired; what known risks/evidence gaps could affect the opportunity; what is the next useful acquisition action?* The corresponding information hierarchy — **Fit** (operative homes, affordable housing, product mix, Buyer Fit) → **Planning** (operative planning position, milestone/decision, next milestone, blockers, planning readiness) → **Control/Acquisition** (owner, developer/controller, delivery status, transaction/availability evidence, acquisition readiness) → **Risks/Evidence Gaps** (conflicting metrics, missing documents, control uncertainty, commencement uncertainty) → **Next Action** (specific evidence to obtain, party to investigate, milestone to monitor) — depends on capability not yet built (Operative Scheme Intelligence, Acquisition Position Intelligence — see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)), so it is recorded here as direction, not implemented now.

The same reorientation applies to the Dashboard: its long-term job is increasingly to answer *what new opportunities match my buyer mandate; what changed; which opportunities need verification; which should I pursue; which planning decisions changed; which existing leads now look committed/closed; what needs action today* — not to lead with aggregate database/coverage metrics, which remain useful operationally but should not dominate the eventual acquisition experience.

## The Capability Stack

The platform is built as six layers, each depending on the one below it. A layer is only built once the evidence it depends on already exists and is trustworthy — this is a deliberate constraint, not a limitation to work around.

```
Planning Intelligence
        │  (what is happening on this Site)
        ▼
Policy Intelligence
        │  (what planning policy says about it)
        ▼
Market Intelligence
        │  (what it could be worth)
        ▼
Development Economics
        │  (whether it is commercially viable)
        ▼
AI Decision Support
        │  (what a professional judgement on it would be)
        ▼
Workflow & Collaboration
           (how a team acts on that judgement)
```

Full detail on each layer's current and future capabilities lives in [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md); the build sequencing lives in [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md).

**Each layer builds on verified evidence produced by the layer below it — never on assumption, and never by skipping ahead.** Development Economics cannot honestly assess viability without real Market Intelligence to appraise against, just as Market Intelligence is meaningless without knowing, from Planning Intelligence and Policy Intelligence, what can actually be built. AI Decision Support only interprets what the first four layers have already established as fact. This ordering is why the platform was built Planning-Intelligence-first and Policy-Intelligence-second, and why the two layers most requested next by users — Market Intelligence and Development Economics — are sequenced *after* the evidence they depend on, not before it.

## The Evidence Platform: One Foundation Underneath All Six Layers

The six capabilities above are not six separate systems that happen to share a database — they are six views onto **one common Evidence Platform**, the technical foundation that discovers, extracts, verifies, stores and monitors evidence on behalf of every layer above it. This is not a seventh product capability a user would ever interact with directly; it is the infrastructure that makes the "evidence first, AI explains rather than invents" philosophy actually enforceable, rather than just an aspiration, in every layer built on top of it.

```
        Planning Intelligence   Policy Intelligence   Market Intelligence
        Development Economics   AI Decision Support   Workflow & Collaboration
                │                    │                    │
                └────────────────────┼────────────────────┘
                                     ▼
                         ┌───────────────────────┐
                         │   THE EVIDENCE PLATFORM │
                         │  (common foundation)    │
                         ├───────────────────────┤
                         │ Document discovery      │
                         │ Source monitoring        │
                         │ AI extraction            │
                         │ Provenance               │
                         │ Review workflows         │
                         │ Version history           │
                         │ Visual evidence           │
                         └───────────────────────┘
```

Every capability layer, present or future, is built by *consuming* the Evidence Platform's services, not by re-implementing them. Full detail on what the Evidence Platform currently does and how each capability depends on it is in [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md#0-the-evidence-platform-common-foundation).

## Core Philosophy: AI Explains Evidence, It Does Not Invent Conclusions

This is the single most important constraint on how PropertyAIgent is built, and it is non-negotiable for every future feature.

Every fact in the platform is produced deterministically wherever a deterministic method exists — extraction, matching, classification, status derivation. AI is reserved for the narrow set of tasks that genuinely require judgement or synthesis: summarising already-verified evidence into prose, classifying an already-rendered image, or (in the future) explaining what a body of already-gathered evidence means for a planning or investment decision. AI is never the source of a *fact* — a policy reference, a unit count, a housing requirement figure — only of an *interpretation* built on top of facts a human can trace back to their source.

This is why review status, source provenance, and confidence are first-class citizens throughout the platform rather than an afterthought: a user should always be able to ask "why does the platform believe this?" and get a real, evidenced answer, all the way from the AI Decision Support layer back down to the original document and page it came from.

### What "grounded" means, and what it does not mean

This principle governs *where facts come from*, not *how much freedom the AI has to reason once it has them*. A future implementation should not read "AI explains evidence, it does not invent conclusions" as license to reduce the AI to a sentence-template engine. Concretely:

**Grounded means:**
- deterministic systems establish every material factual input — a capacity figure, a planning status, a decision, a relationship, a role — before the AI ever sees it;
- the AI receives that trusted evidence as its bounded context, never raw source documents or unverified general knowledge;
- the AI's output is validated after generation so a material factual claim (a number, an organisation, a reference, a role) that doesn't trace back to the evidence it was given is rejected, not published;
- source evidence and the reasoning that produced it stay auditable back to the original document, page and extraction method.

**Grounded does not mean:**
- that every sentence the AI writes must be assembled from a fixed template or a pre-written allow-list of phrases;
- that the AI may only restate conclusions a deterministic system has already reached in words, rather than synthesising and interpreting them;
- that pattern recognition, explanation of commercial significance, and "what to investigate next" are out of bounds — these are exactly the judgement-requiring tasks AI exists for in this platform;
- that the deterministic layer *is* the product. It is the trustworthy foundation the product is built on — the customer-facing intelligence PropertyAIgent exists to deliver is the AI's synthesis of that foundation, not a requirement to scan the foundation manually. See [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) for how this plays out in the Policy Intelligence layer's Allocation Intelligence and Local Plan Delivery Intelligence capabilities.

An implementation that satisfies "grounded" by allow-listing individual tokens or forcing the AI into fixed sentence shapes has satisfied the letter of this principle while defeating its purpose. The bar is: every *material factual claim* is traceable to evidence — not that every *word* was chosen deterministically.

### The same discipline applies to interpreting what a user is asking for

"Grounded" governs the platform's outputs today; the same distinction is intended to govern its future inputs. Opportunity discovery itself — a deterministic feed of Opportunities, each with a real signal and a real reason it was surfaced — is now built (Opportunity Experience V2; see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §2 "Opportunity Intelligence" for exactly what exists today). What remains future is **AI-assisted Opportunity Discovery** specifically: letting a user describe the kind of opportunity they're looking for in ordinary acquisition language (*"emerging residential sites with capacity for 50–100 homes in areas with low housing delivery"*) rather than using the platform's own filters. Where a term in that language is genuinely subjective or requires interpretation — *emerging*, *low housing delivery*, *significant residual capacity* — the platform must make that interpretation transparent and evidence-grounded, the same way it already grounds a summary: never silently decide what a subjective term means and present the result as if it were objective fact. AI may translate a commercial brief into structured search criteria and reason about which opportunities match it; it may not quietly become the source of what the criteria themselves mean.

## Evidence-First, Agent-Assisted, Human-Decided

Opportunity Experience V2 and the LPDI programme together establish the platform's next governing architectural principle — a direct, more precise restatement of "AI explains evidence, it does not invent conclusions" for an era where the platform's AI increasingly takes the shape of specialist reasoning agents, not just narrative-generation calls:

```
Data
  ↓
Evidence
  ↓
Structured / verified intelligence
  ↓
Deterministic intelligence (facts, calculations, classifications)
  ↓
Specialist agentic investigation and interpretation
  ↓
Evidence-backed recommendation
  ↓
Human acquisition decision
```

**Deterministic systems establish facts and calculations. Agents investigate, interpret and reason over those facts. Humans make the acquisition decision.** An agent is a consumer of the platform's structured intelligence, never an alternative source of truth for it — it must not silently overwrite planning status, capacity, Local Plan evidence, planning activity, ownership, development coverage, or any other structured fact the deterministic layers below it already established.

The concrete discipline this requires is **preserving uncertainty, not resolving it into a false positive or negative**. If Property AIgent's own evidence says `Planning activity: UNCERTAIN`, an agent must never restate that as "no planning activity exists" — the platform's own Opportunity Experience V2 language ("Activity uncertain — requires review") already exists specifically to prevent that collapse, and any agent reasoning on top of it inherits the same obligation. Likewise, `Ownership: unknown` must never become "the site is available" — the two are not the same claim, and only one of them is actually evidenced. Where an agent cannot resolve a genuine gap, the correct output is to say so, name what's missing, and suggest what would resolve it — never to quietly fill the gap with a plausible-sounding assumption. This is the same "Never Invent" discipline in [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md) applied to agentic reasoning specifically, not a new rule invented for it.

This principle also disciplines *which* future capabilities become agents at all. A capability that primarily builds or maintains structured evidence — Strategic Land Intelligence, Ownership & Control Intelligence, Opportunity Monitoring — remains **platform intelligence**: deterministic, evidence-producing, and the thing an agent reasons *over*, not a personality wrapped around an LLM call. A capability that genuinely requires judgement over already-established facts — is this worth investigating, who does it suit, what does the market evidence imply — is where **agentic reasoning** belongs. Full detail on this distinction, the three agentic capabilities it currently justifies, and the ones it deliberately does not, is in [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7 ("Agentic Reasoning").

## Commercial Defensibility

Property AIgent's long-term moat is not "we use AI agents" — agent technology will keep commoditising, and a competitor can call the same model APIs Property AIgent does. The durable advantage is the **accumulated, proprietary evidence and intelligence graph** underneath those agents: the source documents and citations already gathered; the extraction and validation outcomes already proven correct against real councils' real documents; Local Plan and allocation histories; Site and Application relationships; development and build status; planning-activity coverage; opportunity history; ownership and control relationships once built; monitoring and change history; buyer profiles and fit once built; market and comparable evidence once built; and, over time, the record of which opportunities users actually investigated, pursued or passed on. None of this is reproducible by pointing a general-purpose agent at public planning portals — it is built once, correctly, with provenance, and it compounds every time the platform is used. Agents reason over this graph; they do not replace the work of building it, and a future architecture must never let agent development outpace the evidence base it depends on.

Full elaboration of this and every other governing principle is in [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md).
