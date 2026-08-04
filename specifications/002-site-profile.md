# Site Profile

## Objective

Define the full set of intelligence that may eventually exist against a Site.

The Site Profile is the blueprint for every future capability and specification in PropertyAIgent. It exists so that when a new dataset or feature is proposed, there is already a place for it to belong - a specific part of the Site's intelligence profile it improves - rather than becoming an isolated tool that sits outside the platform's actual purpose (see `001-platform-vision.md`).

Every future feature specification should be able to point at a section of this document and say which part of the Site Profile it is building.

---

## Site Identity

The base facts that identify a Site as a distinct physical place, independent of any single Application or data source.

- Site name - **Existing** (`Site.display_address`, the most descriptive address string across an application's linked filings)
- Canonical address - **Existing** (`Site.canonical_address`, normalised for matching)
- Postcode - **Existing** (`Site.postcode`)
- Coordinates - **Existing** (`Site.latitude` / `Site.longitude`, geocoded from postcode or free-text address)
- Site boundary (polygon/shape, not just a point) - **Future**
- Council - **Existing** (`Site.council_code`)
- Ward - **Improving** (captured per Application today, not yet consolidated onto the Site itself)
- Site aliases (other names/addresses the same physical site is known by) - **Future**
- Source references (which Applications, documents and external datasets a Site's facts were derived from) - **Existing** (every linked Application retains its own portal URL, reference and `site_link_method`)
- Unique internal identifier - **Existing** (`Site.id`)

---

## Planning Intelligence

*Answers: "Can this Site be developed?"*

- Planning applications - **Existing**
- Planning history (multi-year record of everything filed against a Site) - **Existing**
- Application relationships (which Applications belong to the same Site, and how that link was established - exact address match, cited parent reference, portal search, or manual review) - **Existing**
- Planning documents (downloaded, text-extracted, retained) - **Existing**
- Decisions - **Existing**
- Appeals - **Future**
- Unit counts - **Existing**
- Housing mix (houses/apartments/mixed, development type) - **Existing**
- Affordable housing (unit counts, percentage, evidence classification) - **Existing**
- Tenure (affordable tenure split - social rent, affordable rent, intermediate, etc.) - **Existing**
- Site metrics (site area, density) - **Existing**
- Planning conditions (itemised, condition-by-condition tracking) - **Planned** (condition-discharge filings are already captured as a whole-application progress signal; breaking them down to individual condition level is not yet built)
- Section 106 (structured extraction of obligations, not just keyword detection) - **Future**
- Planning obligations - **Future**
- Planning risks (e.g. commencement-deadline lapse risk) - **Existing** for lapse risk specifically; a broader planning risk view is **Future**

---

## Policy Intelligence

*Answers: "Is this Site consistent with planning policy, and what does policy say should happen here?"*

- Adopted Local Plan - **Future** (current pilot covers a draft/emerging plan only)
- Emerging Local Plan - **Existing** (pilot: Stockport's Regulation 18 draft, AI-extracted site allocations)
- Site allocations - **Existing** (pilot, one council)
- Proposed allocations - **Existing**, captured as part of the same pilot, distinguished by plan status
- Sites under consideration / reasonable alternatives (candidate sites not yet allocated) - **Future**
- Housing need - **Future**
- Housing requirement - **Future**
- Housing land supply - **Future** (a relevant open dataset has been identified for at least one council, not yet ingested)
- Affordable housing policy (the policy target itself, distinct from what a scheme delivers) - **Future**
- Development plan policies (the wider policy document, beyond site allocations) - **Future**
- Green Belt - **Future**
- Conservation - **Future**
- Heritage - **Future**
- Flood risk - **Future**
- Biodiversity - **Future**
- Other planning constraints - **Future**

---

## Delivery Intelligence

*Answers: "Is this Site progressing?"*

- Build status - **Existing** (derived from EPC evidence)
- Commencement evidence (condition-discharge and similar portal-native filings as proof of activity) - **Existing**
- EPC evidence - **Existing**
- Construction phases (a Site broken into its named phases/plots, each tracked separately) - **Existing**
- Completions - **Existing** (via EPC evidence)
- Delivery trajectory (forward-looking projection of build-out over time) - **Future**
- Remaining units (units still undelivered per phase, and which phases are approved but not yet started) - **Existing**
- Developer activity (a developer's track record and pattern of activity across multiple Sites) - **Future**

---

## Market Intelligence

*Answers: "What is this Site worth?"*

- Nearby schemes - **Future**
- Competing schemes - **Future**
- New-build sales comparables - **Future**
- Second-hand sales comparables - **Future**
- Rental comparables - **Future**
- House price growth - **Future**
- New-build premium - **Future**
- Market absorption - **Future**
- Land sales comparables - **Future**
- Demand indicators - **Future**

No part of Market Intelligence has been built yet. This is a whole intelligence pillar still to be started.

---

## Commercial Intelligence

*Answers: "Who is involved?"*

- Developer - **Existing**
- Landowner - **Improving** (field exists, frequently unconfirmed - a genuine landowner is often only established once ownership evidence is added)
- Applicant - **Existing**
- Agent - **Existing**
- Planning consultant - **Existing**
- Architect - **Existing**
- Companies (Companies House matching) - **Existing**
- Directors - **Existing** (officer and person-with-significant-control lookups)
- Contacts (individual people, sourced and enriched) - **Existing**
- Ownership evidence (verified proof of who owns the land, beyond an applicant's stated name) - **Future**
- Land Registry information - **Future**

---

## Location Intelligence

*Answers: "What is this location like?"*

- Schools - **Future**
- Transport - **Future**
- Employment centres - **Future**
- Retail - **Future**
- Parks - **Future**
- Leisure - **Future**
- Healthcare - **Future**
- Demographics - **Future**
- Population growth - **Future**
- Household formation - **Future**
- Income - **Future**
- Deprivation - **Future**
- Crime - **Future**
- Connectivity - **Future**
- Nearby activities and amenities - **Future**

No part of Location Intelligence has been built yet. This is a whole intelligence pillar still to be started.

---

## Financial Intelligence

Financial Intelligence will be added later. It is documented here so the intended shape of it is on record before any of it is built - not because implementation is starting now.

- Development appraisals - **Future**
- User-uploaded Excel financial models - **Future**
- Mapping model inputs once and saving them as templates - **Future**
- Populating templates from trusted Site intelligence - **Future**
- Manual review and adjustment of assumptions - **Future**
- GDV - **Future**
- Build costs - **Future**
- Professional fees - **Future**
- Finance costs - **Future**
- Section 106 and infrastructure costs - **Future**
- Contingency - **Future**
- Profit - **Future**
- Residual land value - **Future**
- Cash flow - **Future**
- Sensitivity analysis - **Future**

**PropertyAIgent should use a hybrid approach to financial appraisal, not attempt to replace the user's own model:**

- Users retain their own Excel model. PropertyAIgent does not become the appraisal tool itself.
- PropertyAIgent maps and populates approved input cells within that model, from Site intelligence already gathered elsewhere in the platform.
- Users remain responsible for reviewing and approving every assumption before it's relied on.
- Deterministic calculations remain in the financial model, not in PropertyAIgent - the platform supplies inputs, it does not re-derive GDV, residual land value, or any other calculated output itself.
- PropertyAIgent should not invent or silently overwrite financial assumptions. Where a Site's evidence is uncertain or absent, the correct behaviour is to leave the input for manual entry, not to guess a plausible-looking number.

---

## Investment Intelligence

*Answers: "Should somebody invest in this Site?"*

- Risks - **Improving** (commencement-deadline lapse risk is tracked; a holistic risk view spanning policy, market and delivery risk is not)
- Opportunities - **Existing** (phases/plots with full permission and no start of works are already surfaced as acquisition opportunities; Local Plan allocations with no application yet are surfaced the same way)
- Site scoring (a single comparable score across Sites) - **Future**
- AI summary - **Existing** (a grounded, weekly-refreshed narrative synthesis of everything known about a Site)
- Comparable opportunities - **Future** (depends on Market Intelligence existing first)
- Development potential - **Improving** (comparing an allocation's or permission's stated capacity against what's actually been applied for/delivered exists at the phase level; a general development-potential assessment does not)
- Investment recommendation - **Future**
- Investment reports - **Existing** for a grounded PDF summary report of current data; a true investment recommendation report is **Future**

**Investment Intelligence, and any investment report built from it, should only be built out once the intelligence layers it depends on are sufficiently mature.** A recommendation is only as trustworthy as the evidence underneath it - Planning, Policy, Delivery, Market, Commercial and Financial Intelligence all feed Investment Intelligence, not the other way round. Building the recommendation layer ahead of the evidence it should be grounded in would produce exactly the kind of confident-sounding but unverifiable output this platform exists to avoid.

---

## Status Framework

Every capability above is marked with one of:

- **Existing** - built and in use today.
- **Improving** - a real, working version exists, but it is known to be partial or is actively being extended.
- **Planned** - not yet built, but a concrete mechanism or near-term direction already exists to build from.
- **Future** - a genuine long-term intention, with no work started yet.

These statuses describe the platform as it stands at the time this document was written. They will drift out of date as work continues - a section that says "Future" today may become "Existing" without this document being updated in lockstep. Treat the status markings as a snapshot, not a live dashboard; when in doubt, check the actual implementation rather than trusting this document's status label as current fact.

---

## Relationship Rules

- Applications are not Sites. An Application is a regulatory submission; a Site is the physical opportunity it relates to.
- Local Plan Allocations are not Sites. An Allocation represents planning intent and may exist with no Application at all.
- Financial Models are not Sites. A model is a tool applied to a Site's intelligence, not a new kind of Site.
- Reports do not own intelligence. A report is a presentation of intelligence that already exists elsewhere.
- Reports assemble intelligence from the Site Profile. They should never contain a fact that doesn't already exist, traceably, somewhere in the Site's own intelligence.
- All intelligence layers should remain independently traceable to their source - a fact on a Site should always be answerable with "where did this come from," not just presented as given.
- A Site may link to multiple Applications, multiple Local Plan Allocations, multiple Companies, multiple Contacts, multiple Comparables, and multiple Appraisals. None of these relationships are one-to-one.

---

## Design Principles

- Site-centred design - every capability exists to describe, explain, enrich, predict, assess, or connect information to a Site.
- Evidence before AI - AI narrates and synthesises verified facts; it does not originate them.
- No isolated datasets - a new dataset with no path back to the Site doesn't belong in PropertyAIgent.
- Preserve source provenance - never lose the ability to say where a fact came from.
- Avoid duplicate data - reuse and extend an existing intelligence layer before adding a new, overlapping one.
- Support national rollout - a capability that only makes sense for one council or one region should be treated as a warning sign, not a template.
- Build intelligence before reports - a report is only as good as the intelligence layers underneath it; don't build the presentation layer ahead of the evidence it depends on.
- Keep financial calculations deterministic - PropertyAIgent supplies inputs to a financial model, it does not perform or replace the calculation itself.
- Human review for uncertain relationships and assumptions - where a match, a link, or a financial input is anything less than certain, surface it for a human decision rather than silently committing to a guess.

---

## Acceptance Criteria

This specification is complete when:

- Every current and future intelligence layer identified across `001-platform-vision.md` and this document has a place within the Site Profile.
- Each major capability has a maturity status (Existing, Improving, Planned, or Future).
- The relationships between Site, Application, Allocation, Appraisal and Report are clearly and unambiguously stated.
- The hybrid Excel appraisal direction for Financial Intelligence is recorded.
- Future feature specifications can reference this document as the place a proposed capability belongs.
- No implementation details, database table definitions, APIs, or application code are introduced by this document.
