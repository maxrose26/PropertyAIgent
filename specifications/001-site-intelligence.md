# Site Intelligence Platform

## Objective

To define what PropertyAIgent fundamentally is, so that every future feature can be judged against a single, consistent long-term vision rather than against whatever seemed useful at the time it was built.

PropertyAIgent is not simply a planning application database. It is a **Site Intelligence Platform**.

A planning application database would collect and display planning applications. PropertyAIgent does something different: it uses planning applications - along with every other source of evidence it can reach - to build the richest possible understanding of a physical development opportunity. The application is a source of evidence, not the product.

## Business Value

A land/planning acquisition professional's real question is never "what applications exist" - it's "which of these physical opportunities is worth pursuing, and what do I need to know about it before I act." Every intelligence layer this platform adds is answering a piece of that question. The more layers a Site has, the more of that question is already answered before a human has to go and find it themselves.

## User Story

As a UK residential land/planning acquisition professional
I want every physical development opportunity I might pursue to already have as much verified context attached to it as possible - not just "an application exists", but who's behind it, what's actually being delivered, how far it's progressed, and what constraints or opportunities surround it
So that I can make a pursue/don't-pursue decision quickly, with evidence, instead of re-researching each site from scratch

## Requirements

- The **Site** is the central object in the platform. It represents one physical development opportunity.
- Every piece of information in the platform should either describe a Site, explain a Site, enrich a Site, predict something about a Site, or connect to a Site. Nothing should exist in isolation from the Site it relates to.
- The platform is organised as a collection of independent **intelligence layers**, each contributing a different kind of evidence about a Site.

Current intelligence layers:

- Planning Applications
- Planning Documents
- Housing Mix
- Affordable Housing
- Companies
- Contacts
- Build Status
- EPC Evidence
- AI Summaries

Future intelligence layers (see [Future Enhancements](#future-enhancements)):

- Local Plan Allocations
- Housing Need
- Housing Land Supply
- Planning Policies
- Green Belt
- Flood Risk
- Conservation Areas
- Listed Buildings
- Biodiversity
- Ownership
- Land Registry
- Section 106
- Infrastructure Levy
- Images
- GIS Layers
- Comparable Schemes
- Viability Signals
- Future Opportunities

Every future feature should do one of exactly two things:

1. **Improve an existing intelligence layer** - make it more accurate, more complete, more timely, or more useful to act on.
2. **Introduce a new intelligence layer** - add a genuinely new kind of evidence about a Site that isn't captured by an existing layer.

A feature that does neither of these should be questioned before it is implemented. That doesn't automatically mean it's wrong - but it means the reason it belongs in PropertyAIgent needs to be made explicit before building it, not assumed.

## Non-Requirements

- PropertyAIgent is explicitly **not** a general-purpose planning application tracker or council-portal mirror. Collecting applications is a means, not the goal.
- This specification does not define the implementation of any individual intelligence layer (existing or future) - each of those, when built or substantially changed, should have its own specification.
- This document does not prescribe a rollout order for future layers. Sequencing is a product decision made separately, informed by this vision, not fixed by it.

## Data Model

At the centre: **Site**. A Site is a physical development opportunity - a place, not a filing.

Everything else in the data model exists to relate to a Site, directly or indirectly:

- An **Application** is a regulatory planning submission. Many Applications can belong to one Site. An Application is evidence *about* a Site, not itself the thing being tracked.
- A **Local Plan Allocation** represents planning intent (a council has earmarked land for development) rather than a live regulatory process. It is a distinct concept from an Application: it can exist with no Application yet, one Allocation may relate to multiple Sites, and one Site may overlap multiple Allocations. It is itself an intelligence layer on a Site, never treated as a second kind of Site.
- A **Company** is an organisation connected to a Site (as applicant, developer, landowner, agent, etc.).
- A **Contact** is a person connected to a Company.

Every other current or future intelligence layer (Housing Mix, Build Status, EPC Evidence, Green Belt, Flood Risk, Ownership, and so on) is data that attaches to, or is computed from data attached to, a Site - not a parallel hierarchy.

## User Experience

A user's primary unit of interaction with the platform is the Site, not the Application. When a user opens a Site, they should see the accumulated evidence from every intelligence layer that has anything to say about it, synthesised into something they can act on quickly - not a list of raw filings they have to interpret themselves. Individual Applications, documents, and other raw evidence remain inspectable underneath, for anyone who wants to verify the synthesis, but they are not the primary view.

## Architecture Considerations

- Intelligence layers should be **independent and additive**. A new layer should be able to be introduced without requiring changes to unrelated existing layers.
- The platform should be built for national rollout, not just the councils currently supported - a design that only makes sense for one council or one region should be treated as a warning sign.
- Reuse existing architecture where a new layer's needs resemble an existing layer's, rather than building a parallel system.
- Evidence is more valuable than inference: prefer capturing and preserving real source evidence over letting an AI-generated summary become the only record of a fact.

## Acceptance Criteria

This specification's ongoing acceptance criteria (it defines a standard to hold every future feature to, rather than something that is "done" once):

- Every significant feature proposed for PropertyAIgent can be described as clearly improving one of the current intelligence layers, or introducing one of the future intelligence layers (or a genuinely new one not yet listed here).
- When a proposed feature cannot be described that way, that gap has been explicitly raised and discussed before implementation, not silently built anyway.
- The list of current and future intelligence layers in this document stays up to date as the platform evolves - it's the reference point everything else is checked against.

## Future Enhancements

The following are recognised as future intelligence layers - real, intended directions for the platform - but are **not** to be implemented until each has its own specification:

- Local Plan Allocations
- Housing Need
- Housing Land Supply
- Planning Policies
- Green Belt
- Flood Risk
- Conservation Areas
- Listed Buildings
- Biodiversity
- Ownership
- Land Registry
- Section 106
- Infrastructure Levy
- Images
- GIS Layers
- Comparable Schemes
- Viability Signals
- Future Opportunities
