# PropertyAIgent — UX Audit

**Prepared as:** a UX consultancy review, ahead of demonstrations to planning consultants, land promoters and developers. **Scope:** the product experience only — no intelligence-layer changes are proposed or implied.

**Methodology:** every page was reviewed against its live source (`app/ui/streamlit_app.py` and `app/ui/pages/*.py`) and against a running instance of the application (`streamlit run app/ui/streamlit_app.py`), including live screenshots of the home page, Scheme Detail, and Council Dashboard. Findings below describe what the product **actually does today**, not a guess at it — consistent with this platform's own evidence-first discipline (see [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md)).

See also: [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md) (the visual language proposed to fix the consistency issues below) and [PRODUCT_EXPERIENCE_ROADMAP.md](PRODUCT_EXPERIENCE_ROADMAP.md) (prioritised, sequenced fixes).

---

## Executive Summary

The underlying intelligence is genuinely strong — full traceability, deterministic matching, real monitoring, real evidence. **None of that currently reads on screen.** The product today looks and behaves like what it is: an internal engineering tool that grew page-by-page, sprint-by-sprint, with each feature bolted onto whichever existing page it was closest to. There is no home dashboard, no distinguishable navigation hierarchy, no visual system, and no moment in the current experience that says "this platform already knows more about this Site than you do" — the single most important thing it needs to communicate in the first ten seconds of a demo.

The good news: **every issue below is a presentation-layer problem.** The data, the evidence, the traceability — the actual hard part — is already built and working. This is a UX and product-polish gap, not a capability gap.

---

## Part 1 — Page-by-Page Audit

### Home page (`streamlit_app.py`) — the de facto "everything" page
Today's home page is simultaneously the dashboard, the search page, the filter panel, the map, the results table, and the export centre. On load, before any product value is visible, the user sees three stacked review-queue notices (suggested site links, unmatched Local Plan sites, watchlist opinions) — internal triage items, not a reason to trust the platform. The natural-language search box, the map, and a 20+-column raw data table all compete for attention on one continuously scrolling page with no section breaks beyond `st.divider()`.

### Scheme Detail (`pages/1_Scheme_Detail.py`, `render_scheme_detail`) — the flagship page, unstructured
This is genuinely the richest page in the product — policy position, visual evidence, phase tracking, AI summary, companies and contacts, all present. But it renders as one long, undifferentiated vertical scroll: a raw address as the only heading, then an unbroken sequence of colour-coded info/warning boxes, bold-markdown key/value pairs in two plain columns, and four-plus independently-triggered expanders (Application history, Phase & plot breakdown, Evidence, and the per-company contact tables). There is no way to jump to a section, no persistent summary of the Site's headline facts, and the single most commercially important content on the page (companies & contacts) is the very last thing on it, reached only after scrolling past everything else. **Visiting this page directly with no site selected produces a dead end** — one info box, nothing else — the credits sidebar doesn't even render, and there is no way to search or browse from there.

### Council Dashboard (`pages/4_Council_Dashboard.py`)
Explicitly labelled in its own page caption as "Not part of the public site-browsing experience" — yet it sits in the primary navigation with equal visual weight to every customer-facing page. Content is a wide 8-column summary table followed by one expander per council, each containing up to four further levels of nested expanders (monitored reports → document coverage → plan evidence → historic values). This is a genuinely useful operations view, wrongly exposed as if it were a product page.

### Local Plan Sites (`pages/3_Local_Plan_Sites.py`)
A single flat, 10-column table listing every allocation across every onboarded council at once, with council/unmatched-only filters in the sidebar. Allocation imagery — one of the platform's most visually compelling, hardest-won capabilities — is reachable only by picking one allocation at a time from a dropdown; there is no gallery, no way to browse "which allocations have a confirmed map" visually.

### Review Site Links (`pages/2_Review_Site_Links.py`)
A clean, single-purpose page — genuinely one of the better-designed pages in the product, because it does exactly one job (confirm/reject a suggested match) with a clear two-column comparison. Its only real issue is discoverability: it only surfaces via a conditional text link on the home page, easy to miss entirely.

### Navigation / Sidebar
Streamlit's default multipage sidebar is used unmodified: page names are derived directly from filenames ("Scheme Detail", "Review Site Links", "Local Plan Sites", "Council Dashboard"), flat, unordered by importance, with no icons, no grouping, and no visual distinction between customer-facing pages and an explicitly internal admin page. The sidebar's very first content block is **Credits** (a personal API-spend throttle), ranked above **Filters** — an internal engineering concern outranking the core product interaction in visual priority.

### Maps
Functional and genuinely useful (status-by-fill-colour, housing-type-by-ring-colour, click-to-open), but the legend is two lines of small caption text with manually coloured Unicode circle glyphs, not a real legend component; there's no layer control panel (the Local Plan overlay is a single checkbox); and the same map pattern is duplicated, not shared, between the home page and Local Plan Sites page.

### Typography, spacing, colour, icons — observed, not designed
There is no design system. Colour meaning is inherited entirely from Streamlit's four built-in alert types (info/warning/error/success) plus ad hoc emoji (🚫 ✅ ⚠️ 🕗 🎯 🏗️ ⏳ 📋 🔍) used inconsistently as informal status markers. There is no consistent badge, chip, or status-pill treatment anywhere in the product.

### Loading, empty and error states
AI-triggered actions (PDF generation, AI summary refresh, contact enrichment) correctly show a spinner with a descriptive label — that pattern is good and should be the template everywhere. Page reruns otherwise rely entirely on Streamlit's default top-of-page progress bar. Most empty states are a single plain `st.info` sentence; the Scheme Detail page's no-selection state (above) is the sharpest example of a true dead end.

---

## Part 2 — Structured UX Issues

Severity: **Critical** (actively undermines trust or blocks a task) · **High** (materially hurts the demo/commercial experience) · **Medium** (real, not blocking) · **Low** (polish).
Priority: **P0** (fix before any external demo) · **P1** (fix this sprint) · **P2** (next sprint) · **P3** (backlog).

### Navigation

| Problem | Why it matters | Severity | Suggested solution | Priority |
|---|---|---|---|---|
| Sidebar nav is a flat, filename-derived list with no grouping or hierarchy. | A first-time viewer can't tell what the product does from its own navigation. | High | Grouped nav (Dashboard / Explore / Planning / Policy / Reports / Administration) — see Part 4. | P1 |
| An explicitly internal admin page (Council Dashboard) sits at the same visual rank as customer-facing pages. | Undermines commercial credibility — a prospect can click straight into an "internal, not for you" page from the main menu. | High | Move under an "Administration" nav group, visually separated. | P1 |
| No persistent way back to a starting point except a text link at the top of each sub-page. | Easy to feel lost navigating a multi-page evidence trail. | Medium | Persistent top-level nav (not just a back-link) on every page. | P2 |

### Information Hierarchy

| Problem | Why it matters | Severity | Suggested solution | Priority |
|---|---|---|---|---|
| Home page stacks dashboard + search + filters + map + table with no visual priority between them. | The most important thing (what should I look at today?) is indistinguishable from everything else. | Critical | Split into a real Dashboard (Part 5) and a separate Explore/search page. | P0 |
| Scheme Detail has no section structure — one continuous scroll of boxes and bold text. | The richest page in the product is also the hardest to scan; a demo viewer can't quickly find "what I need." | Critical | Restructure into named sections/tabs — see Part 6. | P0 |
| Companies & contacts (arguably the most commercially valuable section) is the last thing on the page. | Buries the highest-value content behind everything else. | High | Promote to a top-level tab, not the final scroll position. | P1 |
| Council Dashboard nests up to 4 levels of expanders. | Real information becomes undiscoverable past 2 levels of nesting. | Medium | Flatten to at most 2 levels; use tabs for the 3rd grouping. | P2 |

### Consistency

| Problem | Why it matters | Severity | Suggested solution | Priority |
|---|---|---|---|---|
| The live product is titled "UK Planning Deal Finder" everywhere in the UI; every current document and the vision itself calls it "PropertyAIgent." | A prospect sees a different product name than the one in any pitch material. | Critical | Rename page title, browser tab title and app header to "PropertyAIgent" (see [PRODUCT_EXPERIENCE_ROADMAP.md](PRODUCT_EXPERIENCE_ROADMAP.md)). | P0 |
| "Scheme," "Site," and "Allocation" are used inconsistently as page/section titles for what the platform's own domain model calls a **Site**. | Undermines the "Site is the core object" story that is central to the vision. | High | Standardise on "Site" in all user-facing labels; reserve "Scheme"/"Application" for their precise technical meaning only. | P1 |
| Status/evidence signalling mixes Streamlit's 4 alert colours with ad hoc emoji, with no shared rule for when each is used. | Inconsistent visual language reads as unpolished, and trains users to ignore colour as a real signal. | High | Formal badge/status system — see [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md). | P1 |

### Readability

| Problem | Why it matters | Severity | Suggested solution | Priority |
|---|---|---|---|---|
| Key facts are presented as bold-label markdown sentences ("**Total / Affordable / Private units:** 45 / 12 / 33") rather than distinct, scannable fields. | Slower to scan than a real data display; hard to compare across sites. | Medium | Key stats as a small set of stat tiles/cards at the top of Scheme Detail. | P2 |
| Data tables routinely show 15–20+ raw columns at once (home page table, Local Plan Sites table, Council Dashboard summary). | Overwhelming on a laptop screen; forces horizontal scrolling, which most users won't discover. | High | Default to a curated column subset with a "show all columns" toggle. | P1 |

### Discoverability

| Problem | Why it matters | Severity | Suggested solution | Priority |
|---|---|---|---|---|
| Allocation imagery is only reachable one allocation at a time via a dropdown. | One of the platform's most visually persuasive capabilities is effectively hidden. | High | A visual gallery/grid view for allocation imagery. | P1 |
| Review Site Links only surfaces via a conditional text link on the home page. | Easy to never notice a growing review backlog. | Medium | Surface unresolved review counts as a Dashboard alert (Part 5). | P2 |
| The Evidence behind a scheme's figures sits inside a collapsed expander below the figures themselves. | The platform's central "evidence, not invention" promise is not visible until a user thinks to expand something. | High | Inline evidence indicators (an "i" or source badge next to each figure) rather than a separate expander. | P1 |

### Interaction

| Problem | Why it matters | Severity | Suggested solution | Priority |
|---|---|---|---|---|
| Navigating directly to Scheme Detail with no site selected is a dead end (one sentence, no search, no back-to-browse CTA). | A bookmarked/shared link that's lost its query param, or a stray click, strands the user. | High | A real empty state with a search box and/or "browse all sites" CTA. | P1 |
| Natural-language search requires a full form submit; there's no visible "is my query supported" affordance while typing. | Users may not realise the query needs submitting, or may not know what kinds of questions are answerable. | Low | Example-chip suggestions below the search box; live character-count/hint styling. | P3 |

### Accessibility

| Problem | Why it matters | Severity | Suggested solution | Priority |
|---|---|---|---|---|
| Map legends use `unsafe_allow_html` inline-coloured spans as the only way to associate colour with meaning — no text-only fallback, no colourblind-safe check performed. | Colour-only encoding is a known accessibility failure mode; also a maintenance risk (unstructured HTML in a caption string). | Medium | Legend as a structured component pairing colour with a text/shape label (see [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md)); verify the palette against a colourblind simulator. | P2 |
| Emoji used as the sole status signal in several places (e.g. "🎯", "🏗️") with no text equivalent for a screen reader. | Emoji-only meaning is not reliably conveyed by assistive tech. | Low | Pair every status emoji with a text label (already true in most places; audit and close the gaps). | P3 |

### Visual Design

| Problem | Why it matters | Severity | Suggested solution | Priority |
|---|---|---|---|---|
| No design system — every page independently reinvents spacing, emphasis and colour choices via ad hoc `st.markdown`/`st.caption`/`st.info` calls. | Product feels assembled rather than designed — the single biggest driver of "not commercial-grade" first impressions. | Critical | Adopt [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md) platform-wide. | P0 |
| No consistent iconography — emoji stand in for icons throughout. | Reads as informal/prototype-grade rather than professional SaaS. | Medium | A small, consistent icon set (see design system) replacing ad hoc emoji where they signal status/type rather than add warmth. | P2 |

### Performance Perception

| Problem | Why it matters | Severity | Suggested solution | Priority |
|---|---|---|---|---|
| No skeleton/placeholder states — a full-page rerun shows Streamlit's default top progress bar only. | On a slower connection or a large filtered result set, the page can feel frozen rather than working. | Medium | Skeleton placeholders for the table/map region during rerun; the AI-call spinner pattern already used elsewhere is good and should extend to data-loading reruns too. | P2 |

### Commercial Polish

| Problem | Why it matters | Severity | Suggested solution | Priority |
|---|---|---|---|---|
| Product is branded "UK Planning Deal Finder" in the live app, not "PropertyAIgent." | See Consistency above — this is the single highest-visibility fix available. | Critical | Rebrand pass across `st.set_page_config` titles and the app header. | P0 |
| No success confirmation pattern beyond Streamlit's default green toast for a handful of actions (e.g. saving contact edits) — most actions (excluding a site, confirming a link) just rerun silently. | A demo viewer can't always tell an action succeeded. | Medium | Consistent success-notification pattern for every state-changing action. | P2 |
| Terminology throughout is engineering-accurate but not always commercially polished (e.g. "needs_review", "not yet classified", raw internal status strings surfacing in a few table cells). | Reads as a database dump rather than a professional report in places. | Medium | A terminology pass turning internal enum values into commercial-grade labels everywhere they reach the UI. | P2 |

---

## Part 3 — Comparison Against Product Vision

Reviewed against [PRODUCT_VISION.md](PRODUCT_VISION.md), [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md), [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md), [USER_JOURNEYS.md](USER_JOURNEYS.md) and [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md).

**Current:** Planning applications and policy feel disconnected — a user has to notice, scroll to, and mentally connect an `st.info` policy box sitting above an unrelated phase-tracking block, sitting above a separate visual-evidence block, sitting above a separate AI summary, on one undifferentiated page.

**Desired** (per [USER_JOURNEYS.md](USER_JOURNEYS.md)):
```
Search
    ↓
Planning
    ↓
Policy
    ↓
Visual evidence
    ↓
AI summary
    ↓
Decision
```

Specific gaps against the vision documents:

- **The vision's capability stack is invisible in the product.** [PRODUCT_VISION.md](PRODUCT_VISION.md) describes Planning → Policy → Market → Development Economics → AI Decision Support → Workflow as the platform's defining structure, and [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) is explicit that Market Intelligence and Development Economics don't exist yet. The current UI has no equivalent structure at all — a user has no way to see "here's what this platform already tells you, and here's what's coming," which is both an honesty gap (nothing signals what's *not* built yet) and a missed sales opportunity (nothing signals the roadmap either).
- **"AI explains evidence, it does not invent conclusions"** ([PRODUCT_VISION.md](PRODUCT_VISION.md)) is true in the backend but not visible in the frontend. Evidence/provenance is real but under-surfaced (buried in expanders, plain captions) rather than presented as the platform's core differentiator it actually is.
- **The Site is meant to be the primary unit of interaction** ([PRODUCT_VISION.md](PRODUCT_VISION.md), and `specifications/001-platform-vision.md`'s "Long-Term Vision" section, still valid on this point). In the current product, the Site Profile page is reached almost accidentally (a map click or a table row selection) rather than being the clear, obvious destination of every journey.
- **User journeys assume a "Decision" step the product doesn't yet visually support** ([USER_JOURNEYS.md](USER_JOURNEYS.md)). There is no summary/decision view anywhere — a user has to synthesise the page's contents themselves, exactly the manual synthesis the platform's own mission ([PRODUCT_VISION.md](PRODUCT_VISION.md)) says it exists to remove.

---

## Part 4 — Navigation Review

The current navigation is Streamlit's unmodified filename-derived sidebar. It does not communicate what the product is, does not distinguish customer-facing from internal pages, and gives every page equal visual weight regardless of importance.

### Proposed structure

```
PropertyAIgent
├── 📊 Dashboard            (Part 5 — new)
├── 🔍 Explore               (search + filter + map — today's home page, narrowed)
├── 🏗️ Planning              (per-Site: applications, phases, build status)
├── 📋 Policy                 (Local Plan allocations, imagery, monitoring status)
├── 📄 Reports                (CSV/PDF export, saved views — today's export buttons, promoted)
├── ⚙️ Administration        (Council Dashboard, Review Site Links — clearly separated, distinct visual treatment)
```

Notes:
- **Dashboard** is new (Part 5) and becomes the default landing page — today there is no dashboard at all, only the search/map page.
- **Explore** is today's home page with the review-queue notices and credits widget removed from the primary flow (moved to Dashboard and Administration respectively).
- **Planning** and **Policy** are not new pages so much as the existing Scheme Detail and Local Plan Sites content, promoted to first-class nav items rather than reached only by drilling in from Explore.
- **Reports** elevates the already-built CSV/PDF export capability (currently buried mid-page on Explore) to its own destination — a natural, low-effort home for future output types (planning statements, etc., per [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)'s AI Decision Support layer) without overloading the nav now.
- **Administration** groups Council Dashboard and Review Site Links behind a visually distinct treatment (e.g. a divider and muted styling in the sidebar) so a prospect never mistakes an internal ops page for a product page.
- **Future capabilities are not exposed as empty/broken nav items.** Per the brief's own instruction, Market Intelligence, Development Economics and AI Decision Support are *not* added as clickable-but-empty nav entries. Instead, their eventual arrival is foreshadowed inside the Dashboard (Part 5) and Site Profile (Part 6) as clearly-labelled "Coming soon" placeholders scoped to where their content will actually live — visible ambition without a broken click.

---

## Part 5 — Dashboard Review & Proposal

**Current:** no dashboard exists. The home page is search, filter, map and table combined, with three review-queue notices stacked above all of it.

**Proposal** — a real home dashboard answering, in order, the three questions a returning user actually has:

1. **What has changed?**
   - Recently updated councils (last monitoring check, per [ARCHITECTURE_STATUS_v2.md](ARCHITECTURE_STATUS_v2.md)'s monitoring cadence data, already computed by `app.policy.monitor` — just not currently surfaced anywhere in the customer-facing UI).
   - Recent planning applications (newest scraped Sites, already computable from existing data).
   - Policy updates (recently approved `PolicyChangeEvent`s, recently refreshed AI Local Plan Summaries).

2. **What needs attention?**
   - Monitoring alerts (source-check failures/errors — already tracked as `monitoring_health` on the Council Dashboard, just not surfaced outside Administration).
   - Review items pending (today's three separate home-page notices — suggested site links, unmatched Local Plan sites, screening/scoping watchlist — consolidated into one "needs your attention" panel with real counts, not three independent banners).

3. **Where are the opportunities?**
   - A small set of platform KPIs (total sites tracked, sites with a planning position not yet decided, allocated sites with no application yet — the platform's own "genuinely new opportunity" signal, currently under-promoted on the home page as a single conditional link).
   - Recent activity (a short feed: new sites discovered, new allocation images extracted, new AI summaries generated).
   - **Watchlist** — explicitly a future capability per [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md)'s Workflow & Collaboration layer; shown here as a clearly labelled "Coming soon" card, not a working feature, so the roadmap is visible without anything looking broken.

### Suggested layout (markdown wireframe)

```
┌─────────────────────────────────────────────────────────────────┐
│  PropertyAIgent                                    [Search···]   │
├─────────────────────────────────────────────────────────────────┤
│  KPI strip:  [ 400 Sites ]  [ 69 Allocations, no app yet ]        │
│              [ 175 links to review ]  [ 3 councils updated today ]│
├───────────────────────────────┬───────────────────────────────────┤
│  Needs attention                │  Recent activity                  │
│  • 175 suggested site links     │  • Bury: 2 new applications        │
│  • 69 unreviewed allocations    │  • Stockport: AI summary refreshed │
│  • 2 monitoring sources stale   │  • Bury: 8 new allocation images   │
├───────────────────────────────┴───────────────────────────────────┤
│  Opportunities                                                     │
│  Local Plan allocations with no application yet, by council        │
│  [ small bar chart or ranked table — the platform's leading signal]│
├─────────────────────────────────────────────────────────────────┤
│  Watchlist (coming soon)                                           │
│  Save sites and get notified when their planning or policy         │
│  position changes.                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Part 6 — Site Profile Review & Proposal

Treated here as the flagship page, per the brief. Currently `render_scheme_detail` in `app/ui/common.py` — one function, one continuous render, no section boundaries a user can navigate by.

### Current structure (as built)
Address heading → policy info box(es) → commencement status line → visual evidence block → AI status summary + review-correction expander → phase breakdown (conditional) → consultation/affordable warnings (conditional) → Application history expander → Phase & plot breakdown expander → two-column key facts + Evidence expander → Companies & contacts (unlock buttons, PSC, officer tables, editable contact tables).

### Proposed structure

```
[ ← Back ]   Old Grove House, 13 Vine Street, Hazel Grove          [Status badge] [Build status badge]

Overview
  Key stat tiles: Total units · Affordable % · Development type · Data quality
  One-line AI headline (already computed by app.ui.site_headline — currently only used for map tooltips)

┌─── Tab: Planning Position ───┬─── Tab: Policy Position ───┬─── Tab: Visual Evidence ───┬─── Tab: Nearby Development ───┬─── Tab: Timeline ───┬─── Tab: AI Summary ───┐
│ Application history           │ Allocation match, capacity,  │ Site plans / allocation      │ (Coming soon —                │ Phase & plot         │ Narrative summary,   │
│ Phase & plot breakdown        │ progression signal, delivery │ maps, confirmed/unreviewed   │ Market Intelligence layer,    │ breakdown as a       │ key risks/           │
│ Commencement status           │ scope vs. allocation          │ status                        │ per PRODUCT_ROADMAP.md)       │ visual sequence, not │ opportunities,       │
│                                │                                │                                │                                │ just a table          │ evidence gaps         │
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┴────────────────────────────────┴────────────────────────┴────────────────────────┘

Companies & Contacts                                                                                     [promoted to its own top-level section, not the final scroll item]
  Per-company cards: CH match, verified domain, PSC/owner, contacts (unlock on demand)

Review this scheme  [collapsed by default, unchanged from today's correction workflow]
```

Rationale for the ordering: **Overview → Planning → Policy → Visual Evidence → Nearby Development → Timeline → AI Summary** mirrors the brief's suggested structure and the vision documents' own evidence chain (search → planning → policy → visual evidence → market → decision). "Nearby Development" is included as an explicit **future placeholder** (Market Intelligence doesn't exist yet, per [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)) so the page's own structure previews where that capability will land, without implying it works today. Companies & Contacts moves out of the tab strip into its own always-visible section below it, reflecting that it's a distinct concern (who to contact) from the Site's own evidence (what's true about it) — and because it's genuinely high commercial value, it should never require a tab click to discover.

---

## Part 7 — Council Dashboard Review

Assessed dimensions, as requested:

- **Plan summaries** — present (AI Local Plan Summary), well-gated (never regenerates without a click), but visually indistinguishable from the raw evidence fields around it.
- **Monitoring** — a real health indicator exists (OK/Error/Stale/Never checked/No sources) but only as a table cell, not a glanceable status.
- **Coverage** — the document-coverage table (Expected/Found/Current/Missing/Superseded/Visual/Policy/Monitoring — 8 columns) is one of the most information-dense tables in the product, nested inside an expander inside an expander.
- **Document status, housing supply, housing delivery, policy evidence** — all present and genuinely well-organised *within* their own expander, but reaching any of them requires opening council → evidence → section, three clicks deep.
- **AI summaries** — same content-quality strength, same discoverability weakness as the plan summary point above.
- **Visual hierarchy** — effectively none; every council, regardless of activity level or health status, gets the identical expander treatment.

**Recommendation:** keep this page's content and logic entirely as-is (it is operationally sound) but reduce nesting depth (2 levels maximum, per Part 2's Information Hierarchy findings), add a visible health-status colour indicator per council row (not just a table cell), and clearly mark the page throughout as an Administration surface (per Part 4) rather than a peer of the customer-facing pages.

---

## Part 8 — Local Plan Sites Review

- **Filtering** — council multiselect and "unmatched only" checkbox, both functional, sidebar-only (consistent with the rest of the product).
- **Allocation imagery** — the platform's strongest visual asset, reachable only one allocation at a time via a dropdown (`st.selectbox`) — no gallery, no thumbnail grid, no "show me the allocations with a confirmed map" visual browse.
- **Review workflow** — none exists on this page specifically; image confirm/reject happens elsewhere (implied by the review-status data shown), not visible here.
- **Policy references** — shown as a plain table column; no visual grouping by plan or by review/match status.
- **Search** — none; only council/matched-status filtering, no free-text search across allocation names or references.
- **Allocation discoverability** — weakest point of this page: a user has no way to know which allocations have imagery worth looking at without opening the selectbox and scanning labels one at a time (the `format_allocation_option` helper does encode image status in the label text, which is good, but a label string is a poor substitute for a visual grid).

**Recommendation:** add a thumbnail-grid "gallery" view above or instead of the single-selection dropdown, filterable by the same image-availability filter that already exists, and add free-text search across policy reference/site name.

---

## Part 9 — Maps

- **Layer controls** — a single checkbox toggles the Local Plan allocation layer; no broader layer panel exists or is needed yet, but the pattern won't scale cleanly once more layers (constraints, GIS, per [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)) are added.
- **Legend** — present but visually minimal (small caption text, inline-coloured Unicode glyphs via `unsafe_allow_html`), and duplicated as two separate caption lines rather than one coherent legend component.
- **Selection** — click-to-open works well (`on_select="rerun"`, `resolve_selected_site_id`) — a genuine strength, not a weakness.
- **Hover behaviour** — a well-composed plain-text tooltip (`format_site_tooltip`), deliberately not HTML for a real, sound security reason (documented in the source) — worth preserving as-is, just needs a matching visual polish pass (Part 10) rather than a behaviour change.
- **Filtering** — the map reflects whatever the sidebar filters/table selection already produced; no map-native filtering (e.g. draw-a-boundary, zoom-to-filter).
- **Search** — none map-native; search happens above the map, in the NL search box.
- **Future GIS placeholders** — none exist today. Per the brief, GIS itself is explicitly out of scope for this sprint; the recommendation here is only to reserve visual space (a collapsed "Constraint layers (coming soon)" toggle group in the eventual layer panel) so the map's own UI previews the roadmap the same way the Dashboard and Site Profile do, without implementing anything.

**Recommendation:** build a proper legend component (Part 10) and, as the map gains layers over time (Local Plan allocations today; constraints and comparables later, per [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)), introduce a real layer-control panel before the single-checkbox pattern becomes unworkable — not urgent this sprint, but worth planning for now rather than retrofitting later.
