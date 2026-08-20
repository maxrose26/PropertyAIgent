# PropertyAIgent — Product Vision

This is the platform's North Star. Every other document in `docs/` and every specification in `specifications/` should be readable as a more detailed expression of what's written here. Where a future decision is unclear, this document — not a sprint brief, not a UI mockup — is the tie-breaker.

See also: [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) (how the vision is built), [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) (in what order), [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md) (the rules every feature follows), [USER_JOURNEYS.md](USER_JOURNEYS.md) (what it feels like to use).

---

## Mission

Build the richest possible understanding of every residential development opportunity in the UK, centred on a single object — the **Site** — so that the people who evaluate, promote, permission and invest in development opportunities can make faster, better-evidenced decisions.

## Vision

Today, understanding a single development opportunity means separately searching a council planning portal, a GIS constraints viewer, Companies House, a policy document library, and a market-data provider — then manually holding all of it in your head at once. PropertyAIgent's vision is that this synthesis happens once, automatically, and continuously, and is presented back as a single coherent picture of the Site — not a pile of documents the user still has to read and reconcile themselves.

The long-term ambition is for a user to open a Site and immediately understand everything relevant about that opportunity: what's happening on it, what planning policy says about it, what it's worth, whether it's commercially viable, and what a professional planning judgement on it would be — each claim traceable back to the evidence it came from.

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

Full elaboration of this and every other governing principle is in [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md).
