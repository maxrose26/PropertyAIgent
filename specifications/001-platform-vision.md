# PropertyAIgent Platform Vision

> **Historical document.** This reflects the original platform vision as written during early development, before the platform's capability model was formalised. It is retained here for historical context only, and its content below is unchanged from that time.
>
> The current, authoritative product vision is maintained in:
> - [docs/PRODUCT_VISION.md](../docs/PRODUCT_VISION.md) — mission, target users, capability stack, core philosophy
> - [docs/PLATFORM_ARCHITECTURE.md](../docs/PLATFORM_ARCHITECTURE.md) — functional architecture per capability
> - [docs/PRODUCT_ROADMAP.md](../docs/PRODUCT_ROADMAP.md) — build sequencing
>
> Where this document's six-pillar framing (Planning / Delivery / Market / Commercial / Location / Investment Intelligence) differs from the current six-capability model (Planning / Policy / Market / Development Economics / AI Decision Support / Workflow & Collaboration), the current documents take precedence.

## Mission

PropertyAIgent is a Development Intelligence Platform.

Its purpose is to build the richest possible understanding of every residential development opportunity in the UK.

The platform should enable developers, land promoters, investors, housebuilders, planners and landowners to make faster and better informed decisions by bringing together every relevant source of intelligence into one place.

PropertyAIgent is not simply a planning application database.

Planning applications are only one intelligence layer.

The Site is the core object within the platform.

Everything else exists to enrich a Site.

Every new feature should ultimately answer one question:

"Does this help somebody make a better development or investment decision about this Site?"

## Business Value

A land/planning acquisition professional's real question is never "what applications exist" - it's "which of these physical opportunities is worth pursuing, and what do I need to know about it before I act." Every intelligence layer this platform adds is answering a piece of that question. The more layers a Site has, the more of that question is already answered before a human has to go and find it themselves.

## User Story

As a UK residential land/planning acquisition professional
I want every physical development opportunity I might pursue to already have as much verified context attached to it as possible - not just "an application exists", but who's behind it, what's actually being delivered, how far it's progressed, and what constraints or opportunities surround it
So that I can make a pursue/don't-pursue decision quickly, with evidence, instead of re-researching each site from scratch

---

# Target Customers

## Primary Customers

The platform is initially designed for:

- Regional housebuilders
- Land promoters
- Land agents

These users need to:

- identify opportunities
- evaluate opportunities
- progress opportunities
- present opportunities

## Secondary Customers

The platform should also be designed so it naturally expands into:

- Institutional investors
- Single Family Housing (SFH) investors
- Build-to-Rent (BTR) investors
- Affordable Housing Providers
- Registered Providers (RPs)
- Housing Associations
- Residential investment funds

These customers use the same underlying Site Intelligence but focus on different stages of the development lifecycle.

---

# Residential Development Lifecycle

PropertyAIgent follows the lifecycle of a residential development, rather than a single planning application.

Example lifecycle:

Land
↓
Policy & Allocation
↓
Planning
↓
Approval
↓
Construction
↓
Completion
↓
Sales / Disposal
↓
Institutional Investment
↓
Affordable Housing Acquisition
↓
Long-term Ownership & Portfolio Management

Different customers engage with the Site at different stages of this lifecycle, but the intelligence engine underneath them remains the same.

---

# One Intelligence Engine

PropertyAIgent should not evolve into separate products for different customer types.

Instead:

- There should be one Site Intelligence Engine.
- Different customer types should see different views, dashboards and reports built from the same underlying intelligence.
- Intelligence should be collected once and reused throughout the platform.

---

## The Core Object

The Site is the centre of PropertyAIgent.

Everything should either:

- describe a Site
- explain a Site
- enrich a Site
- predict a Site
- assess a Site
- connect information to a Site

No dataset should exist in isolation.

Every intelligence layer should ultimately relate back to a Site.

---

# Platform Pillars

PropertyAIgent is built around six intelligence pillars.

## 1. Planning Intelligence

Answers:

"Can this Site be developed?"

Examples:

- Planning Applications
- Planning History
- Appeals
- Local Plan Allocations
- Housing Need
- Housing Land Supply
- Development Plan Policies
- Affordable Housing Policy
- Planning Constraints
- Green Belt
- Conservation Areas
- Flood Risk
- Listed Buildings
- Biodiversity
- Heritage Constraints

---

## 2. Delivery Intelligence

Answers:

"Is this Site progressing?"

Examples:

- Build Status
- Construction Phases
- EPC Evidence
- Commencement
- Completions
- Delivery Trajectory
- Developer Activity

---

## 3. Market Intelligence

Answers:

"What is this Site worth?"

Examples:

- Sales Comparables
- House Price Growth
- Rental Values
- New Build Premiums
- Nearby Developments
- Competing Schemes
- Market Absorption
- Land Sales Comparables
- Demand Indicators

---

## 4. Commercial Intelligence

Answers:

"Who is involved?"

Examples:

- Developers
- Landowners
- Companies
- Directors
- Planning Consultants
- Architects
- Agents
- Contacts

---

## 5. Location Intelligence

Answers:

"What is this location like?"

Examples:

- Schools
- Transport
- Hospitals
- Employment
- Retail
- Parks
- Leisure
- Demographics
- Population Growth
- Household Formation
- Crime
- Connectivity
- Amenities

---

## 6. Investment Intelligence

Answers:

"Should somebody invest in this Site?"

Examples:

- Planning Risks
- Policy Risks
- Opportunities
- Site Score
- AI Investment Summary
- Comparable Sites
- Exit Value Indicators
- Development Potential
- Investment Report

---

# Intelligence Layers

Every feature added to PropertyAIgent should belong to one of these intelligence pillars.

Features should enrich the Site rather than exist independently.

If a proposed feature does not improve one of these pillars, its value should be questioned before implementation.

---

# Design Principles

PropertyAIgent should:

- build intelligence, not just collect data
- preserve source evidence
- use AI to enhance understanding rather than replace evidence
- avoid duplicate data
- favour modular intelligence layers
- remain scalable to every planning authority in England and Wales
- answer real investment questions
- keep the Site as the centre of the platform
- collect intelligence once, use it many times
- keep the Site as the single source of truth
- treat reports as outputs, not data stores
- let different customers consume the same intelligence in different ways

---

# Long-Term Vision

The long-term goal is for a user to open a Site and immediately understand everything relevant about that opportunity from one screen.

The Site, not the Application, is the primary unit of interaction with the platform. A user should see accumulated evidence synthesised into something they can act on quickly - not a list of raw filings they have to interpret themselves. Individual Applications, documents, and other raw evidence remain inspectable underneath, for anyone who wants to verify the synthesis, but they are not the primary view.

Rather than searching multiple planning portals, GIS systems, Land Registry records, market reports and policy documents, the platform should consolidate all relevant intelligence into one coherent view.

Ultimately, PropertyAIgent should become the operating system for evaluating residential development opportunities.
