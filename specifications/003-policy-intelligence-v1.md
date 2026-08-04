# Policy Intelligence V1

## 1. Business Objective

Every intelligence layer PropertyAIgent has today is built around evidence that only exists once a planning **Application** has been submitted. By the time an application appears on a council's portal, the opportunity is already visible to every other agent, developer and investor watching the same portal - it is a lagging indicator.

A Local Plan allocation is different. It is a council's own advance signal of where it intends housing to go, published years before most applications on that land will ever be submitted. A platform that only sees a Site once an application exists is, by construction, always looking at opportunities after they've already become visible to everyone else. Policy Intelligence exists to close that gap.

Concretely, Policy Intelligence answers a question no other current intelligence layer can:

> "Which physical opportunities has a council already earmarked for housing, that nobody has applied for yet?"

That is a genuinely new kind of Site - and a genuinely new kind of evidence about an existing one. It improves the Site Profile (`002-site-profile.md`) in two distinct ways:

- It gives Sites that already have an Application a second, independent source of confidence: an allocation confirms that a scheme isn't just administratively live, but consistent with adopted or emerging policy, and it reveals whether the Application on record covers the whole allocation or only part of it (see §5).
- It surfaces genuinely new Sites - allocated land with no Application at all - which is precisely the earliest-stage, highest-value class of opportunity this platform exists to find, and which no other intelligence layer can produce.

This is the first implementation of the Policy Intelligence pillar described in `001-platform-vision.md` and `002-site-profile.md`. Almost everything under Policy Intelligence in the Site Profile is currently marked **Future**; this specification defines what moves to **Existing** in V1, and draws the line clearly around what does not.

---

## 2. Scope of Version 1

V1 is deliberately narrow: it captures a Local Plan's own stated facts about individual site allocations, structured and traceable, and nothing beyond that.

**Local Plan metadata** (captured once per plan, not once per allocation):

- Plan name
- Plan status (draft / emerging / examination / adopted)
- Plan period (the years the plan covers, e.g. 2024-2042)
- Housing requirement (the plan's own stated overall housing number for its area - distinct from a housing need study's output, and distinct from housing land supply)
- Housing land supply, where the council makes this available as a discrete, citable figure or dataset. This is explicitly "where available", not a promise of coverage - not every council publishes it in a usable form, and V1 does not depend on it existing.

**Housing allocations** (captured once per site, linked to its plan):

- Allocation reference (the plan's own policy code for the site, e.g. "HOM 2.30")
- Allocation name
- Intended use (as stated by the plan - most will be residential, some may be mixed use; V1 records what the plan says rather than assuming residential-only)
- Capacity (the plan's own stated dwelling count for that specific allocation)
- Source document (which document the allocation was read from)
- Source page (so a person can go and verify the figure against the original text)
- Source URL (a working link back to the source document)

V1 covers exactly this - a structured, traceable record of what a Local Plan states about individual site allocations. It does not include future functionality (see §3 and §7).

---

## 3. Out of Scope

The following are explicitly excluded from V1:

- **AI interpretation** of what a policy means, implies, or is likely to result in. V1 only structures facts that are already explicitly printed in the source document (a name, a reference, a number) into a consistent record - it does not draw conclusions from them. This mirrors the platform-wide principle that AI narrates and structures verified facts, it does not originate them (`002-site-profile.md`, Design Principles).
- **Automatic policy summaries** - no AI-generated prose summarising a plan or a policy's intent.
- **Polygon extraction from PDFs** - no attempt to derive a site's boundary shape from a Policies Map or any other document.
- **GIS editing** - no tooling for drawing, adjusting, or managing spatial boundaries.
- **Automatic policy scoring** - no numeric score representing how favourable an allocation's policy position is.
- **Automated planning recommendations** - no "this Site is a good/bad bet" output derived from policy data. That belongs to Investment Intelligence, and only once Policy Intelligence itself is mature enough to be relied on as an input (`002-site-profile.md`, Investment Intelligence).

---

## 4. Data Sources

Unlike planning Applications, there is no equivalent of a council-portal system (Idox, Arcus) for Local Plans - no consistent format, no shared platform, no search API. Every council publishes its own plan in its own way, at its own stage of adoption. V1 therefore expects source discovery to be manual or semi-manual, per council, rather than a generic crawler.

Expected sources, in rough order of how directly they map to V1's scope:

- **Council Local Plan webpages** - the starting point for finding the current, authoritative version of a council's plan (and confirming its status - draft, under examination, or adopted).
- **Local Plan PDFs** - the definitive published plan document, and the primary source for V1's data.
- **Site allocation schedules** - the specific section or appendix of the plan (or a companion document) that lists individual sites with their reference, name and capacity. This is the core source V1 is built to read.
- **Policies maps** - large-format documents showing every allocation's boundary together. Useful for context and future boundary work (§7), but not read for V1 - no data is extracted from them at this stage.
- **Supporting evidence documents** (e.g. a Strategic Housing Land Availability Assessment or housing trajectory annex) - useful for cross-checking a plan's housing requirement or land supply figures, and occasionally the more complete source for a figure the main plan document doesn't state as clearly, but not a required source for V1.

---

## 5. Site Relationships

Policy Intelligence introduces one additional concept - the **Local Plan Allocation** - alongside the two that already exist, **Site** and **Application**. The three must not be confused with one another:

- **Allocations are not Sites.** An Allocation represents a council's planning intent for a piece of land. A Site is the physical development opportunity that intent may or may not eventually correspond to. An Allocation can - and very often does, in V1 - exist with no Site or Application yet linked to it at all.
- **Applications are not Allocations.** An Application is a live regulatory submission. An Allocation is a policy statement. Neither implies the other: a Site can have an Application with no corresponding Allocation (most Sites today), and an Allocation can have no Application at all (the pre-application opportunities this feature exists to surface).
- **Sites may overlap multiple Allocations.** A single physical Site can span, or otherwise relate to, more than one Allocation - for example where a plan splits one larger opportunity into several referenced sub-areas.
- **Allocations may contain multiple Sites.** Equally, a single Allocation may end up being delivered as more than one physical Site over time, if that land is ultimately brought forward in separate pieces.
- **Relationships must support full-site, partial-site, and phased developments**, not just a simple one-to-one match. A confirmed real case already demonstrates why this matters: one Stockport allocation states a capacity of 300 dwellings, while the only Application actually linked to it is for 134 - a partial, likely phased, delivery of that allocation, not the whole of it. Any relationship model that only records "matched" or "not matched" would lose exactly this distinction, which is one of the most useful signals Policy Intelligence can surface: an allocation that's only been partly taken up still has a genuine remaining opportunity attached to it.

**Known V1 implementation limitation (added following the Policy Intelligence Foundation sprint's CTO review):** `LocalPlanSite.matched_site_id` is a single nullable foreign key, so the *implementation* today supports at most one confirmed Site per allocation - even though this section already establishes that an allocation may conceptually correspond to several Sites. The partial-delivery comparison (the 300-vs-134 example above) currently works around this at the unit-count level, comparing an allocation's stated capacity against whichever one Site is matched, not by representing multiple Site links directly. Future work should introduce an explicit relationship table (`allocation_id`, `site_id`, `relationship_type`: full | partial | phased, `confidence`) rather than widening `matched_site_id` itself - not implemented in this sprint or its amendment, recorded here so the gap between what this section describes and what V1 actually stores is explicit, not silently assumed.

---

## 6. User Experience

Policy Intelligence must not become a separate "Local Plan module" that a user has to know to go and look at. It is another section of the Site Profile - the same page a user already goes to for a Site's Planning, Delivery and Commercial Intelligence.

- When a Site corresponds to all or part of a Local Plan allocation, that should be immediately visible on the Site's own page: the allocation's reference, name, stated capacity, the plan it comes from and that plan's status, and a way to verify the figure against its original source. Where the linked Application only accounts for part of the allocation's stated capacity, that gap should be stated plainly (see §5) rather than left for the user to calculate themselves.
- Where an allocation has no Site or Application linked to it at all, it represents a pre-application opportunity - genuinely new information the platform hasn't surfaced any other way. It should still be discoverable, but it is fundamentally a fact *about* a potential Site, not a different category of record with its own separate browsing experience.
- A user should never need to understand "which system this data came from" to find it. Policy Intelligence should read as one more thing PropertyAIgent already knows about a Site, not as a bolt-on tool sitting next to the platform.

---

## 7. Future Roadmap

The following are recognised as genuine future directions for Policy Intelligence, and are explicitly **not** part of V1. Each would need its own specification before implementation:

- Allocation boundaries (true polygon geometry, not a point)
- GIS layers (boundary data rendered as a map layer, not point markers)
- Policy mapping (structured capture of policy text itself, beyond the site-allocation schedule)
- Constraint mapping (Green Belt, flood risk, conservation areas, heritage, biodiversity - each its own future intelligence layer per `002-site-profile.md`)
- AI summaries (a narrative synthesis of a Site's policy position, once there is enough verified Policy Intelligence to synthesise from)
- Planning probability (an estimate of how likely an allocation is to receive permission)
- Automated overlap calculations (systematically computing which Sites overlap which Allocations from real spatial data, rather than the name/address matching V1 relies on)

---

## 8. Acceptance Criteria

This specification is ready for implementation to begin against once:

- The V1 scope in §2 is agreed as complete and final for this version - no item from §3 or §7 has crept back in.
- The exclusions in §3 are agreed and understood as genuinely out of scope, not just "not yet mentioned."
- The relationship rules in §5 are unambiguous, in particular that Allocations are not Sites, Applications are not Allocations, and that partial-site and phased-delivery relationships (an Application covering only part of an Allocation's stated capacity) must be representable, not just a binary matched/unmatched flag.
- The data source expectation in §4 is understood: V1 depends on per-council manual or semi-manual source discovery, not a generic crawler, and does not assume uniform coverage across every council from day one.
- The user experience direction in §6 is agreed: Policy Intelligence appears as a section of the existing Site Profile, not a separate Local Plan module.
- This document itself contains no implementation detail, database schema, or code - it defines what V1 is and why, not how it is built.
