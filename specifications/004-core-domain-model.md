# Core Domain Model

## Objective

PropertyAIgent is a Site-centred Residential Development Intelligence Platform.

Its purpose, as established in `001-platform-vision.md`, is to build the richest possible understanding of every residential development opportunity in the UK - not to collect planning applications, and not to accumulate disconnected datasets for their own sake.

Everything in the platform should relate back to one or more of a small number of core domain objects. This specification defines what those objects are, what belongs to each of them, and how they relate to one another. It exists so that every future feature has a clear, pre-agreed home before it is built, rather than each new capability inventing its own standalone concept.

The platform should be modelled around a small number of rich domain objects, not hundreds of disconnected datasets. Where a proposed feature does not obviously belong to one of the objects defined here, that is a signal to stop and extend an existing object rather than introduce a new one (see "Future Expansion" below).

This document is the definitive reference for PropertyAIgent's core domain model. Future specifications should reference it rather than redefining these entities.

---

# Core Domain Objects

## 1. Site

**Purpose**

A Site represents a parcel of land or a development opportunity - the physical place itself, independent of any single planning application, scheme, or point in time.

A Site is the primary object within PropertyAIgent. It is the anchor every other domain object ultimately connects back to, directly or indirectly.

**What belongs to a Site**

- **Identity** - the facts that make a Site a distinct physical place: address, canonical address, postcode, coordinates, council, ward, aliases.
- **Boundary** - the Site's physical extent, today a point (via geocoding) and in future a true polygon.
- **Planning Intelligence** - the record of planning activity on this land: linked Planning Applications, planning history, decisions, conditions, appeals.
- **Policy Intelligence** - the planning-policy position affecting this land: Local Plan allocations, adopted and emerging policy, constraints.
- **Market Intelligence** - what this Site, and this location, is worth: comparables, absorption, demand.
- **Commercial Intelligence** - who is or has been involved with this Site, via its relationships to Organisations and Persons.
- **Financial Intelligence** - the appraisal position for this Site, via its relationship to a Financial Model.
- **Investment Intelligence** - the synthesised view of whether this Site is worth pursuing, built from every other intelligence layer attached to it.

A Site does not own all of this data directly. Most of it is reached through the Site's relationships to the other domain objects defined below - a Site is enriched by what is connected to it, not by accumulating fields of its own indefinitely. This mirrors how the Site is implemented today: a deliberately thin identity/status record, with everything else derived at read time from its linked Planning Applications and their intelligence.

A Site may exist with no Planning Application at all - a Local Plan allocation with nothing yet submitted against it is still a genuine Site-level opportunity, and is one of the clearest cases where Policy Intelligence surfaces a Site before Planning Intelligence does.

---

## 2. Development

**Purpose**

A Development represents a residential scheme that has been, is being, or will be delivered - the product, not just the permission.

A Site describes the opportunity; a Development describes what is (or would be) actually built and sold or let on it. A single Site may have one Development, several (a phased scheme delivered as distinct Developments over time), or none yet (a Site still at the opportunity stage has no Development until delivery begins to take shape). A Development is not required to sit on a tracked Site at all - a nearby or competing scheme, delivered by someone else, on land PropertyAIgent has never scraped an application for, is still a legitimate standalone Development record, held for comparison against the Sites the platform is actually tracking.

This is the key distinction this specification introduces: **Developments are first-class objects, not simply nearby schemes.** A competing scheme two streets away deserves the same structured, evidenced richness as a Site's own opportunity - not a flat CSV row of "3-bed houses, £320k, sold out" bolted on as a comparable. Development Intelligence - understanding what has actually been delivered, to whom, at what price, with what specification, and how it performed in the market - should become one of PropertyAIgent's primary competitive advantages, because it is intelligence almost nobody else in this space holds in structured form.

**What belongs to a Development**

- **Identity** - name, address, the Site(s) and phase(s) it corresponds to.
- **Planning** - the permission(s) it was delivered under, via its relationship to Planning Applications.
- **Delivery** - build-out status, completions, delivery trajectory over time.
- **Product** - what is actually being or was built: unit types, tenure mix, typologies.
- **Market** - how this Development sits in its local market.
- **Comparable Intelligence** - how this Development compares to other Developments nearby or of a similar type, the structured version of what today would be called a "comparable scheme."
- **Market Position** - positioning within its segment (e.g. entry-level, premium, later-living, BTR).
- **Buyer Profile** - who this Development was or is being marketed to.
- **Sales Intelligence** - pricing, sales rates, absorption, achieved values.
- **Specification** - build quality, materials, internal specification.
- **Amenities** - on-site and nearby amenities relevant to marketing and value.

Today's `SchemeIntelligence` record (unit counts, tenure split, developer, reconciled from AI extraction and regex passes) is the seed of Planning and Product information for a Development, but it does not yet cover Comparable Intelligence, Market Position, Buyer Profile, Sales Intelligence, Specification, or Amenities - these are genuinely new ground for the platform, not a renaming of something that already exists.

---

## 3. Planning Application

**Purpose**

A Planning Application represents a planning proposal - a regulatory submission to a council.

- Applications are linked to Sites.
- Applications may contribute to Developments - a Development's Planning information is built from one or more Applications, but an Application existing does not by itself constitute a Development.
- **Applications are not Sites.** Many Applications can belong to one Site (an outline, its reserved matters, a discharge of conditions, an amendment); a Site can accumulate Applications across years without any one of them being definitive.

This matches the platform's existing implementation: `Application` is the raw per-filing record, consolidated onto a `Site` via tiered, confidence-scored linking (exact address match, cited parent reference, portal-native related-application search, or human-confirmed fuzzy match). Planning Applications remain the platform's primary evidence source and the most mature domain object in the system today.

---

## 4. Policy

**Purpose**

Policy represents planning policy - the documented intent of a planning authority, independent of any specific Application.

Policy includes:

- Local Plans
- Allocations
- Policies (development plan policy text itself, beyond site allocations)
- Design Codes
- Supplementary Planning Documents (SPDs)
- Neighbourhood Plans
- Future policy sources, as councils publish them in new forms

Policy relates to Sites the same way Applications do, but represents intent rather than a live regulatory process - an allocation can exist with no Application against it at all, and an Application can exist with no corresponding allocation. The platform's existing `LocalPlanSite` pilot (Stockport, Regulation 18 draft plan) is the first concrete instance of this object: a policy-level allocation record, independently matchable to a Site, that is fully in scope of this definition but currently covers only the "Allocations" sub-type of Policy for one council. Policies, Design Codes, SPDs, and Neighbourhood Plans remain future sources within the same object, not separate concepts.

---

## 5. Organisation

**Purpose**

Organisation represents any organisation connected to a Site or a Development, including:

- Developers
- Land Promoters
- Land Agents
- Architects
- Planning Consultants
- Registered Providers
- Housing Associations
- Institutional Investors
- Build-to-Rent operators
- Construction companies
- Landowners

Organisations may own, develop, promote, invest in, or advise on Sites and Developments. A single Organisation may hold several of these relationships at once, and its relationship to any given Site or Development may change over time (a land promoter progressing a Site to a housebuilder, a Registered Provider being confirmed after being "not yet named").

This corresponds to the platform's existing `Company` object (Companies House matching, officers, persons with significant control, verified domain, contacts) extended to explicitly cover the fuller set of organisation types the target-customer strategy in `001-platform-vision.md` now recognises - institutional investors, BTR operators, and Registered Providers/Housing Associations are customer types as well as organisations the platform already tracks as counterparties on a Site, and this object is what unifies those two views.

---

## 6. Person

**Purpose**

Person represents an individual contact, such as:

- Land Director
- Planning Manager
- Acquisition Manager
- Consultant
- Owner
- Relationship Manager

Persons belong to Organisations. A Person does not exist independently of the Organisation they are connected to - the platform's value is in knowing which person, at which organisation, to approach about which Site or Development, not in holding a person record as an end in itself.

This corresponds to the platform's existing `Contact` object (sourced from Companies House officers, Apollo, Hunter, or verified news evidence, with provenance and suppression/opt-out tracking already built in).

---

## 7. Financial Model

**Purpose**

A Financial Model represents a user-owned appraisal model for a Site or Development.

The agreed hybrid approach, first recorded in `002-site-profile.md`, applies without change:

- Users retain ownership of their own Excel appraisal models. PropertyAIgent does not become the appraisal tool itself.
- PropertyAIgent maps approved input cells within that model to trusted intelligence already gathered elsewhere in the platform.
- PropertyAIgent supplies trusted intelligence as inputs; it does not originate financial assumptions.
- Financial calculations remain deterministic and stay inside the user's own model - PropertyAIgent does not re-derive GDV, residual land value, or any other calculated output itself.

A Financial Model is not yet built in the platform, but is defined here so every future specification concerning appraisal has an agreed object to extend, rather than reopening the hybrid-approach decision.

---

## 8. Report

**Purpose**

A Report represents a generated output, such as:

- Investment Report
- Planning Summary
- Site Assessment
- Board Report
- Acquisition Report

**Reports never own data. Reports assemble intelligence from other domain objects.** A Report is a presentation of facts and synthesis that already exist, traceably, on a Site, a Development, an Organisation, or a Person - never a place where a new fact is first established. This is the same grounded-numbers-then-narrate principle already applied throughout the platform's AI extraction and summary generation, extended explicitly to cover Reports as a domain object.

The platform's existing PDF report generator and AI-generated scheme status summaries are the first working instances of this object.

---

# Relationships

- **Site ↔ Planning Application** - one-to-many. A Site accumulates Applications over time; an Application belongs to at most one Site.
- **Site ↔ Development** - one-to-many, optionally zero. A Site may have no Development yet (opportunity stage), one Development, or several (phased delivery, each phase its own Development).
- **Development ↔ Planning Application** - many-to-many. A Development may be delivered under several Applications (outline, reserved matters, amendments); a single large Application may in principle span more than one eventual Development where a masterplan is split.
- **Development ↔ Sales** - one-to-many (Sales Intelligence recorded per unit or per sales phase within a Development).
- **Development ↔ Organisation** - many-to-many. A Development may involve a developer, a sales agent, a contractor, and an eventual institutional or RP purchaser, each a distinct relationship, each potentially changing over the Development's lifecycle.
- **Site ↔ Policy** - many-to-many. A Site may overlap multiple Policy allocations; one allocation may relate to multiple Sites, or to none yet.
- **Site ↔ Financial Model** - one-to-many. A Site may have more than one Financial Model over time (a promoter's early appraisal, a housebuilder's later one), each independently owned.
- **Site ↔ Report** - one-to-many. A Site may have many Reports generated against it over time; a Report belongs to the Site(s)/Development(s) it was assembled from.
- **Organisation ↔ Person** - one-to-many. A Person belongs to one Organisation at a time, historically may have belonged to others.
- **Organisation ↔ Development** - many-to-many, role-qualified (developer, agent, contractor, investor, RP, etc. - the same role-qualified pattern the platform already uses for Site-level Organisation links).
- **Organisation ↔ Site** - many-to-many, role-qualified (applicant, developer, agent, landowner, architect, housing association, and the newer roles - promoter, institutional investor, BTR operator - the target-customer expansion in `001-platform-vision.md` introduces).

Relationships throughout the domain model must support:

- **One-to-one**, where a relationship is genuinely exclusive (e.g. a Financial Model belonging to exactly one Site at a time).
- **One-to-many** and **many-to-many**, as the default assumption for almost every relationship above - real development activity rarely reduces to a single, permanent pairing.
- **Historical relationships** - a relationship that was once true and no longer is (a Person who has left an Organisation, a landowner who has since sold) must remain visible as history, not be overwritten and lost.
- **Phased developments** - a single Site delivered as multiple Developments over time, each with its own Planning Applications, sales performance, and timeline.
- **Partial overlaps** - a Policy allocation only partly taken up by a linked Application, a Site that overlaps only part of an allocation's boundary - the relationship must be able to represent "some, not all" rather than forcing a binary matched/unmatched state.
- **Future expansion** - every relationship above should be extendable with new roles, new relationship types, or new qualifying detail without requiring the underlying domain objects themselves to change shape.

---

# Intelligence Layers

Intelligence layers enrich domain objects. They are not domain objects in their own right.

- Planning Intelligence
- Policy Intelligence
- Delivery Intelligence
- Market Intelligence
- Development Intelligence
- Commercial Intelligence
- Location Intelligence
- Financial Intelligence
- Investment Intelligence

Each layer is a lens applied to one or more of the eight domain objects above - most often Site and Development - rather than a place where new entities are created. Development Intelligence appearing both as a named intelligence layer and as the subject of its own domain object (Development) is intentional, not a contradiction: Development is a rich, first-class object precisely because so much intelligence enriches it, in the same way Site is both the core object and the target of every other intelligence layer in the platform.

A proposed feature that looks like a new intelligence layer should always be checked against this list first. If it fits an existing layer, it belongs there. If it appears to need a genuinely new layer, that new layer still enriches an existing domain object - it does not become a ninth core object.

---

# Design Principles

PropertyAIgent's domain model should:

- follow Site-first architecture - the Site remains the platform's central, anchoring object
- favour rich domain objects over disconnected datasets - depth on a small number of objects, not breadth across hundreds of unrelated tables
- build intelligence before reports - a Report only ever assembles what already exists elsewhere
- collect intelligence once, reuse it everywhere - the same fact, gathered once, should serve every domain object and every customer view that needs it
- preserve source provenance - every fact should remain traceable to where it came from
- put evidence before AI - AI narrates and synthesises verified facts, it does not originate them
- require human review for uncertain relationships - an ambiguous link between domain objects is surfaced for a decision, not silently guessed
- keep intelligence layers modular - a layer can be extended or added without reshaping the domain objects underneath it
- support national scalability - the model must remain coherent for every council, region, and organisation type in England and Wales, not just the ones currently configured
- let AI enhance decisions rather than replace evidence - the model exists to make a human's decision faster and better-informed, not to make the decision for them

---

# Future Expansion

New capabilities should extend one of the eight domain objects defined above wherever possible - a new field, a new relationship, a new intelligence layer attached to an existing object.

Avoid introducing new core domain objects unless absolutely necessary. Before adding a ninth object, confirm that none of Site, Development, Planning Application, Policy, Organisation, Person, Financial Model, or Report can reasonably be extended to cover it. If a genuinely new core object is ever required, it should be added to this specification first, with its relationships to the existing eight fully defined, rather than built ahead of an agreed place in the model.

---

# Acceptance Criteria

This specification is complete when:

- Every future feature has a logical home among the eight domain objects defined here.
- Domain objects are clearly separated from intelligence layers - no intelligence layer is modelled as if it were a standalone entity.
- Relationships between all eight domain objects are fully documented, including their cardinality and their support for historical, phased, and partial-overlap cases.
- The architecture supports national scale - nothing in the domain model depends on a specific council, region, or portal technology.
- The model supports housebuilders, land promoters, land agents, institutional investors, and affordable housing providers as named in `001-platform-vision.md`'s Target Customers section, each finding their relevant view through Organisation, Development, and the intelligence layers rather than a bespoke object of their own.
- Future specifications can reference this document instead of redefining Site, Development, Planning Application, Policy, Organisation, Person, Financial Model, or Report.
