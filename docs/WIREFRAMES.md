# PropertyAIgent — Wireframes

Markdown/ASCII wireframes for every screen in the redesigned product experience, following [NAVIGATION_ARCHITECTURE.md](NAVIGATION_ARCHITECTURE.md)'s structure and [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md)'s components (Cards, Stat Tiles, Status/Evidence/Review Badges, AI-Generated Content styling). Behavioural detail for these screens (hover, loading, selection) is in [INTERACTION_DESIGN.md](INTERACTION_DESIGN.md). Design-only — no implementation, per this sprint's scope.

---

## Part 1 — Overall Product Flow

The end-to-end journey a user actually takes, and the destination each step lives at:

```
Dashboard                    /
    │  "what needs my attention today?"
    ▼
Explore                      /explore
    │  search, filter, browse the map/results
    ▼
Site Profile                 /site/{id}
    │  the flagship page — everything known about one opportunity
    ├──▶ Planning Position    (what's been applied for / built)
    ├──▶ Policy Position      (what the council has allocated / intends)
    ├──▶ Visual Evidence      (maps, masterplans, allocation boundaries)
    ├──▶ Nearby Development   (future — Market Intelligence)
    ├──▶ Timeline             (phases, plots, milestones)
    └──▶ AI Summary           (narrative synthesis of everything above)
    ▼
Reports                      /reports
    │  turn the evidence above into something to send/print/act on
    ▼
Future: Development Economics, AI Planning Assessment
    (the eventual "should I pursue this" answer, once those layers exist)
```

This mirrors [USER_JOURNEYS.md](USER_JOURNEYS.md)'s own worked example (search → planning → policy → visual evidence → market → decision) and directly answers [UX_AUDIT.md](UX_AUDIT.md) Part 3's finding that "planning and policy currently feel disconnected" — every step above is a tab within one Site Profile, not a separate, disconnected page.

The journey is deliberately **re-entrant, not linear** — Dashboard and Explore are both always one click away (top nav, per [NAVIGATION_ARCHITECTURE.md](NAVIGATION_ARCHITECTURE.md)), so a user can jump straight back to browsing after reading one Site's evidence, rather than being funnelled through a fixed wizard.

---

## Part 3 — Dashboard

**Answers, in order:** what's changed? what needs attention? where are the opportunities? what should I look at next?

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  🏠 PropertyAIgent    Dashboard   Explore   Policy ▾   Reports         [🔍 Search] 🔔 ⚙ │
├──────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  Good morning — here's what's changed since you last looked.                            │
│                                                                                          │
│  ┌─ Platform KPIs ──────────────────────────────────────────────────────────────────┐  │
│  │  [ 400 ]          [ 69 ]                [ 175 ]              [ 3 ]                │  │
│  │  Sites tracked    Allocations, no        Items awaiting       Councils updated     │  │
│  │                   application yet         review               this week            │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                          │
│  ┌─ Needs attention ─────────────────────┐  ┌─ Recent activity ────────────────────┐  │
│  │  ⚠ 175 suggested site links            │  │  🏗️ Bury — 2 new applications          │  │
│  │  ⚠ 69 unreviewed allocation images     │  │  📋 Stockport — AI summary refreshed   │  │
│  │  ⚠ 2 monitoring sources stale          │  │  🖼️ Bury — 8 new allocation images     │  │
│  │  [ Open Review Centre → ]              │  │  📄 Trafford — new monitored report    │  │
│  └────────────────────────────────────────┘  └────────────────────────────────────────┘  │
│                                                                                          │
│  ┌─ Planning alerts ─────────────────────┐  ┌─ Policy alerts ───────────────────────┐  │
│  │  ⏳ 4 sites: commencement deadline      │  │  🆕 Rochdale: newer AMR discovered,    │  │
│  │     approaching                          │  │      not yet extracted                 │  │
│  │  🚩 2 sites: permission may have        │  │  🕗 1 policy change awaiting approval  │  │
│  │     lapsed                               │  │      (Bury Local Plan)                 │  │
│  └────────────────────────────────────────┘  └────────────────────────────────────────┘  │
│                                                                                          │
│  ┌─ Opportunities: Local Plan allocations with no application yet ──────────────────┐  │
│  │  Ranked by council:                                                                │  │
│  │  Stockport ████████████████████████████████████ 36     Bolton ████ 2               │  │
│  │  Rochdale  ██████████████ 12                            Oldham ███ 3                │  │
│  │  [ View all in Local Plan Sites → ]                                                 │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                          │
│  ┌─ Latest AI summaries ────────────────┐  ┌─ Recent searches ─────────────────────┐  │
│  │  🤖 Stockport Local Plan               │  │  "50+ affordable units in Greater      │  │
│  │      "...emerging draft, 37            │  │   Manchester, not yet completed"       │  │
│  │       allocations, 1.77yr supply..."   │  │  "Bury schemes with no developer       │  │
│  │  [ View → ]                            │  │   confirmed"                            │  │
│  │  🤖 Bury Local Plan                    │  │  [ Re-run in Explore → ]                │  │
│  │  [ View → ]                            │  │                                          │  │
│  └────────────────────────────────────────┘  └────────────────────────────────────────┘  │
│                                                                                          │
│  ┌─ Watchlist  ·  Coming soon ───────────────────────────────────────────────────────┐  │
│  │  Save a Site and get notified when its planning or policy position changes.        │  │
│  │  Part of the platform's future Workflow & Collaboration layer.                      │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Design notes:**
- Every figure above is real, currently-computable data — the platform already tracks monitoring health, review-queue counts, and allocation coverage; this Dashboard is a presentation layer over facts that exist today, not new intelligence.
- The KPI strip and "Opportunities" panel are the emotional core of the page — they're what make a returning user feel the platform has been working *for* them since their last visit, directly per [PRODUCT_VISION.md](PRODUCT_VISION.md)'s mission.
- "Needs attention" consolidates today's three separate, stacked home-page banners (suggested links / unmatched allocations / watchlist opinions) into one panel with a single door into the [Review Centre](#part-8--review-centre).
- Recent Searches previews the "Saved searches (future)" capability named in the brief's Explore section — shown here as a lightweight history list (genuinely buildable today, since queries are already parsed and stored in session state) rather than the heavier "save + notify" Watchlist capability, which is explicitly future.

---

## Part 4 — Explore

**The primary search/browse surface** — today's home page, narrowed to exactly this job (Dashboard now owns the "what's new" job).

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  🏠 PropertyAIgent    Dashboard   Explore   Policy ▾   Reports         [🔍 Search] 🔔 ⚙ │
├───────────────┬──────────────────────────────────────────────────────────────────────┤
│  FILTERS        │  Describe what you're looking for                                     │
│                  │  ┌────────────────────────────────────────────────────┐ [ Search ]   │
│  Council         │  │ e.g. "50+ affordable units in Greater Manchester,   │              │
│  ☑ Bury          │  │  not yet completed"                                  │              │
│  ☑ Stockport      │  └────────────────────────────────────────────────────┘              │
│  ☐ Trafford       │  Interpreted as: region=Greater Manchester, min_affordable=50, ...    │
│  ...              │                                                                        │
│                  │  ┌─ Map ──────────────────────────────┐  ┌─ Layers ──────────────┐   │
│  Housing type     │  │                                       │  │ Style: ● Road ○ Dark  │   │
│  ☑ Houses         │  │        [ pydeck map, cluster-aware ]  │  │ ☐ Local Plan          │   │
│  ☑ Apartments     │  │                                       │  │   allocations          │   │
│  ☑ Mixed          │  │                                       │  │ ☐ Constraint layers    │   │
│                  │  │                                       │  │   (coming soon)        │   │
│  Min units        │  └──────────────────────────────────────┘  └────────────────────────┘   │
│  [   0   ]        │  Legend:  ● Not yet granted  ● OK  ● Deadline approaching  ● Lapsed      │
│                  │           ◯ Houses  ◯ Apartments  ◯ Mixed  ◯ Other                        │
│  ☐ Hide completed │                                                                        │
│  ☐ Needs review   │  247 sites                              [ Export CSV ] [ Generate PDF ] │
│    only            │  ┌──────────────────────────────────────────────────────────────────┐ │
│                  │  │  Address              Council   Units  Affordable%  Status    ›    │ │
│  Saved searches   │  │  Old Grove House       Stockport  11    —           Granted   ›    │ │
│  (coming soon)    │  │  Land east of...       Bury       350   30%         Pending   ›    │ │
│                  │  │  ...                                                                │ │
│                  │  └──────────────────────────────────────────────────────────────────┘ │
└───────────────┴──────────────────────────────────────────────────────────────────────┘
```

**Design notes:**
- Filters stay in a contextual sidebar (per [NAVIGATION_ARCHITECTURE.md](NAVIGATION_ARCHITECTURE.md)) — but with a curated default column set on the results table (5–7 columns, "show all" toggle), addressing [UX_AUDIT.md](UX_AUDIT.md)'s Readability finding.
- A visible **Layers** panel (rather than today's single checkbox) is introduced now, with a disabled/greyed "Constraint layers (coming soon)" row — reserving space for the roadmap without exposing anything unbuilt, per Part 11 below.
- **Saved searches (future)** sits directly under the filter panel as a clearly-labelled, not-yet-active section — the natural next step after today's real, working "recent searches" history (shown on the Dashboard).
- Row selection opens the Site Profile — a `›` affordance on every row makes this discoverable without relying on a user guessing that a table row is clickable (today's implicit checkbox-select-then-scroll-down pattern is not self-evident).

---

## Part 5 — Site Profile (Flagship Page)

The single most important page in the product, per the brief. Redesigned from today's unstructured continuous scroll into a card-based, tabbed layout.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  🏠 PropertyAIgent    Dashboard   Explore   Policy ▾   Reports         [🔍 Search] 🔔 ⚙ │
├──────────────────────────────────────────────────────────────────────────────────────┤
│  Dashboard › Explore › Old Grove House, 13 Vine Street, Hazel Grove                    │
│                                                                                          │
│  Old Grove House, 13 Vine Street, Hazel Grove                     [Granted] [Underway]  │
│  Stockport · 1 linked application                                                       │
│                                                                                          │
│  ┌─ Overview ───────────────────────────────────────────────────────────────────────┐  │
│  │  [ 11 ]         [ — ]              [ Discharge of  ]     [ ✓ Verified ]           │  │
│  │  Total units    Affordable %       conditions          Data quality               │  │
│  │  📋 Allocated in the Stockport Local Plan as HOM 2.1 (109 min. dwellings)          │  │
│  │  🔍 This application covers only 10% of the allocation — ~98 units may remain      │  │
│  │      available.                                                                     │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                          │
│  ┌ Planning ┬ Policy ┬ Visual Evidence ┬ Nearby Development ┬ Timeline ┬ AI Summary ┐  │
│  ├──────────┴────────┴──────────────────┴──────────────────────┴───────────┴──────────┤  │
│  │                                                                                       │  │
│  │  [ active tab content — see below ]                                                  │  │
│  │                                                                                       │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                          │
│  ┌─ Companies & Contacts ──────────────────────────────────────────────────────────┐  │
│  │  M Moss Technical Ltd  —  developer          [CH: 04521xxx ✓]  [Website ✓]        │  │
│  │  Owner (PSC): Jane Smith — 75-100% shares                                          │  │
│  │  [ 2 contacts ]  Name · Title · Email · Outreach status                            │  │
│  │                                                                                       │  │
│  │  (no landowner extracted yet)                        [ Unlock contacts (1 credit) ]  │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                          │
│  [ ▸ Review this scheme ]                                             [ Generate report ]│
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Tab contents:**

- **Planning Position** — application history (table), phase & plot breakdown, commencement status, build status — today's content, now scoped to its own tab instead of interleaved with policy/evidence content.
- **Policy Position** — full allocation match detail (reference, capacity, category, progression signal, delivery-scope note), sourced straight from today's `build_site_policy_intelligence` — unchanged logic, contained layout.
- **Visual Evidence** — primary confirmed image (large), other candidate images (thumbnail grid) — same content as today's `render_visual_evidence`, given its own dedicated tab instead of a mid-page block.
- **Nearby Development** *(future placeholder — Market Intelligence)*:
  ```
  ┌──────────────────────────────────────────────────────────────┐
  │  🔒 Nearby Development — coming soon                            │
  │  Comparable schemes, sales values and land value evidence near  │
  │  this Site will appear here once Market Intelligence is built.  │
  │  See PRODUCT_ROADMAP.md.                                        │
  └──────────────────────────────────────────────────────────────┘
  ```
- **Timeline** — phase/plot breakdown re-rendered as a horizontal sequence (not just a table), each phase a small card showing status, unit count, and latest filing date.
- **AI Summary** — the existing weekly-generated narrative, styled per [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md)'s AI-Generated Content card (purple accent, generation timestamp, adjacent evidence badges).

A future **Development Economics** tab is *not* added to the tab strip yet (per Part 11's "do not expose unfinished functionality") — its natural future home is between Nearby Development and Timeline, noted here for continuity with [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md)'s capability ordering, not built or previewed as a tab today.

**Companies & Contacts** is deliberately *not* a tab — it's promoted to its own always-visible section beneath the tab strip, directly addressing [UX_AUDIT.md](UX_AUDIT.md)'s finding that this is arguably the highest commercial-value content on the page and was previously the very last thing on it.

**Reports** is represented here as a single "Generate report" action in the page footer, routing to the [Reports](#part-9--reports) area pre-scoped to this one Site — not a full tab of its own, since report generation is an action, not content to browse.

---

## Part 6 — Council Intelligence (customer-facing)

Splits today's single Council Dashboard into a customer-facing intelligence view (below) and an internal Council Operations view (moved to [Administration](#part-8--review-centre), not detailed further here — its content is unchanged from today's monitoring-health/coverage tables, just relocated and re-labelled for an operator audience).

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  Dashboard › Policy › Stockport Metropolitan Borough Council                            │
│                                                                                          │
│  Stockport Local Plan                                    [Emerging draft] [Last checked │
│                                                             04 Aug 2026]                  │
│                                                                                          │
│  ┌─ 🤖 AI Local Plan Summary ────────────────────────────────────────────────────────┐  │
│  │  The Stockport Local Plan is currently at the emerging stage... 37 allocations,     │  │
│  │  1.77 years of five-year housing land supply...                                     │  │
│  │  Key risks: [...]   Key opportunities: [...]   Evidence gaps: [...]                 │  │
│  │  Generated 04 Aug 2026 · gpt-4o-mini                              [ 🔄 Refresh ]      │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                          │
│  ┌─ Housing requirement ────┐ ┌─ Housing delivery ────────┐ ┌─ 5-year land supply ───┐ │
│  │ [ 31,790 ] total          │ │ Latest period: Mar 2026     │ │ [ 1.77 yrs ]            │ │
│  │ [ 13,455 ] need (studies) │ │ Homes delivered: not stated │ │ Deliverable: 3,847      │ │
│  │ 📄 p.12, Housing Topic     │ │ 📄 p.44, AMR 2025            │ │ dwellings                │ │
│  │    Paper                   │ │                              │ │ Required: 10,890         │ │
│  └────────────────────────────┘ └──────────────────────────────┘ └──────────────────────┘ │
│                                                                                          │
│  ┌─ Evidence completeness ────────────────────────────────────────────────────────────┐  │
│  │  ✓ Local Plan       ✓ Policies Map       ✓ AMR       ⚠ Housing Land Supply (stale)  │  │
│  │  [ 37 of 37 allocations sourced ]   [ 1 of 37 allocations have a confirmed image ]   │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                          │
│  [ View all Stockport allocations → ]                            [ Switch council: ▾ ]  │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Design notes:**
- This view keeps every genuinely customer-relevant fact from today's page (plan status, housing requirement/delivery/supply evidence, AI summary) but drops the operational language entirely — no "monitoring health," no "classification_status," no raw enum values. "Last checked" replaces "monitoring health: OK" as the only freshness signal a customer needs.
- **Evidence completeness** is a deliberately softened, customer-facing reframing of today's internal "policy document coverage" table — same underlying data, expressed as "what we have" rather than an 8-column internal audit grid.
- Every figure carries an inline Evidence Badge (📄 page reference) per [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md), rather than requiring a click into a separate expander to see where it came from.
- The full operational detail this page's current version shows (monitored-report classification queues, per-document-type coverage internals, source-registration status) is not lost — it moves to **Council Operations** under Administration, framed for an operator, not removed.

---

## Part 7 — Local Plan Sites (Allocation Experience)

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  Dashboard › Policy › Local Plan Sites                                                 │
│                                                                                          │
│  Local Plan allocated sites               37 sites (36 no application, 1 have one)      │
│  🔍 [ Search by reference or name...             ]   Council: [ All ▾ ]  Image: [ All ▾ ]│
│                                                                                          │
│  ┌─ Gallery ────────────────────────────────────────────────────────────────────────┐  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │  │
│  │  │[thumbnail]│  │[thumbnail]│  │ no image  │  │[thumbnail]│  │ no image  │            │  │
│  │  │HOM 2.12   │  │JPA1.1     │  │HOM 2.1    │  │JPA3.1     │  │HOM 2.3    │            │  │
│  │  │Compstall  │  │Northern   │  │John St.   │  │Medipark   │  │Station Rd │            │  │
│  │  │Mills      │  │Gateway    │  │[Needs img]│  │[✓Confirmed]│  │[Needs img]│            │  │
│  │  │[⚠ Review] │  │[✓Confirmed]│  │           │  │           │  │           │            │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │  │
│  │  ... (grid continues, filterable by "has image" / "confirmed only")               │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                          │
│  Selected: HOM 2.12 — Compstall Mills                                                  │
│  ┌─ Detail ─────────────────────────────────┐  ┌─ Map ─────────────────────────────┐  │
│  │  [ large confirmed image ]                  │  │  🟡 Allocated, no application yet   │  │
│  │  Stockport Local Plan, p.106                │  │  [ pydeck point, this allocation ]  │  │
│  │  Min. dwellings: 130   Category: List 2      │  │                                      │  │
│  │  Status: draft_allocation  Progression: →    │  │                                      │  │
│  │  [⚠ Needs review · 90% confidence]           │  │                                      │  │
│  └──────────────────────────────────────────────┘  └──────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Design notes:**
- The single biggest change from today: a **thumbnail gallery replaces the one-at-a-time dropdown**, directly resolving [UX_AUDIT.md](UX_AUDIT.md) Part 8's "weakest discoverability point" finding — a user can now see at a glance which allocations have imagery worth opening, without reading label text in a `st.selectbox`.
- Free-text search across policy reference and site name is added (none exists today).
- Every gallery card carries a Review Badge (✓ Confirmed / ⚠ Needs review) directly on the thumbnail, so review status is visible during browsing, not only after opening a detail view.
- Selecting a card populates the Detail + Map panel below, mirroring the click-to-detail pattern already established well elsewhere in the product (e.g. today's map-to-Site-Profile flow).

---

## Part 8 — Review Centre

A dedicated administrator surface consolidating every review queue that today is scattered across the home page, Council Dashboard, and individual Site pages.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  ⚙ Administration                                              [← Back to Dashboard]   │
│  Administration › Review Centre                                                        │
├──────────────────────────────────────────────────────────────────────────────────────┤
│  Review Centre                                            175 items awaiting review     │
│                                                                                          │
│  ┌ Site Matching (175) ┬ Visual Evidence (69) ┬ Policy Evidence (12) ┬ Monitoring (2) ┬ Recent Changes ┐
│  ├──────────────────────┴───────────────────────┴────────────────────┴─────────────────┴─────────────────┤
│  │                                                                                                          │
│  │  [ Site Matching tab active — today's "Review Site Links" page, unchanged content/logic ]                │
│  │                                                                                                          │
│  │  Suggested reason: same postcode district (BL9) and 82% address text similarity.                         │
│  │  ┌─ New application: 24/01234/FUL ──────┐  ┌─ Existing site ─────────────────────┐                     │
│  │  │  Land east of Walmersley Road, Bury    │  │  73108, 73354 — Walmersley Road       │                     │
│  │  │  Total units: 350                      │  │  Total units: 350                     │                     │
│  │  └──────────────────────────────────────┘  └──────────────────────────────────────┘                     │
│  │  [ ✓ Confirm same site ]   [ ✗ Reject — different site ]                                                  │
│  │  ─────────────────────────────────────────────────────────────────────────────────                       │
│  │  ... (175 items, paginated)                                                                               │
│  │                                                                                                          │
│  └──────────────────────────────────────────────────────────────────────────────────────────────────────┘
│                                                                                          │
│  Other tabs (same page, same consolidated pattern):                                     │
│   • Visual Evidence — confirm/reject AI-classified images (today: scattered per-Site)   │
│   • Policy Evidence — approve/reject PolicyChangeEvent proposals (today: buried in       │
│     Council Dashboard's nested expanders)                                                │
│   • Monitoring — sources/reports needing type classification or showing an error state   │
│   • Recent Changes — an audit trail of every review decision made, who/when (new —       │
│     no equivalent exists today; a natural by-product of consolidating the queues)         │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Design notes:**
- Every underlying review action (confirm/reject a site link, confirm/reject an image, approve/reject a policy change) is **unchanged in logic** — this is a consolidation of where reviews happen, not a redesign of what reviewing means, consistent with [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md)'s Human Review principle.
- The tab-count badges (175 / 69 / 12 / 2) give an administrator instant triage priority without opening anything — directly resolving [UX_AUDIT.md](UX_AUDIT.md)'s Discoverability finding that today's review backlog is easy to never notice.
- **Recent Changes** is a genuinely new page (not just a relocation) — a natural, low-cost addition once every review action funnels through one place, and a meaningful trust-building feature in its own right (an administrator, or eventually a customer, can see the platform's own review history, not just its current state).

---

## Part 9 — Reports

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  Dashboard › Reports                                                                    │
│                                                                                          │
│  Reports                                                                                 │
│                                                                                          │
│  ┌─ Available now ──────────────────────────────────────────────────────────────────┐  │
│  │  📊 CSV Export                    Export any filtered Explore result set            │  │
│  │      [ Generate → ]                                                                 │  │
│  │  📄 PDF Summary Report            AI-narrated summary of a filtered result set       │  │
│  │      [ Generate → ]                                                                 │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                          │
│  ┌─ Coming soon — AI Decision Support layer ───────────────────────────────────────┐  │
│  │  🔒 Planning Statement            🔒 Planning Assessment      🔒 Executive Report  │  │
│  │  🔒 Call for Sites Submission     🔒 Site Promotion Report     🔒 Development       │  │
│  │                                                                    Appraisal          │  │
│  │  These will be generated the same way today's PDF Summary is — from verified         │  │
│  │  evidence already gathered by this platform, never invented. See PRODUCT_ROADMAP.md. │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Design notes:** the "Coming soon" cards are locked (🔒), not disabled-but-clickable, and each is a plain label with no interaction at all — the brief's "do not expose unfinished functionality" applied literally. Their value here is entirely narrative: it tells a demo viewer, truthfully, what this platform is going to be able to generate, without pretending it can today.

---

## Part 11 — Future Hooks (Consolidated)

Every future-capability placeholder that appears across the wireframes above, gathered in one place for review — **none of these are functional; each is a clearly-labelled, non-interactive preview of where the eventual capability will live**, per [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) and [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md):

| Future capability | Where it's previewed | Treatment |
|---|---|---|
| Market Intelligence | Site Profile's "Nearby Development" tab | Locked placeholder tab with explanatory text |
| Market Intelligence | Explore's Layers panel | Greyed "Constraint layers (coming soon)" row |
| Development Economics | Noted in Site Profile design notes as a future tab position | Not shown in the tab strip at all yet |
| AI Planning Assessment | Reports' "Coming soon" section | Locked card, no interaction |
| Workflow & Collaboration | Dashboard's "Watchlist" card | Explained in text, no working save/notify action |
| CRM | Not previewed anywhere yet | Deliberately omitted — per [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md), CRM is sequenced after Watchlists within Workflow & Collaboration, and previewing it before its own dependency exists would be premature |
| Watchlists | Dashboard | See Workflow & Collaboration, above — the same placeholder |

This table exists so a reviewer can audit, in one place, that every "coming soon" element across the whole product is accounted for and none of them silently imply working functionality.
