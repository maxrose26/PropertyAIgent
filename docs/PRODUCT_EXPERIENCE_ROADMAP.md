# PropertyAIgent — Product Experience Roadmap

A prioritised, sequenced set of UX improvements arising from [UX_AUDIT.md](UX_AUDIT.md), styled per [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md). This document proposes **what to build and in what order** — it does not implement anything (see both linked documents' own scope notes; this remains a documentation-only sprint).

Priority follows the audit's own scale: **P0** (before any external demo) · **P1** (this sprint) · **P2** (next sprint) · **P3** (backlog).

---

## Commercial Polish — Specific Improvements

Per the brief's Part 11, the concrete, demo-facing improvements that make the platform feel commercially ready, independent of which page they touch:

| Improvement | Current state | Target state | Priority |
|---|---|---|---|
| Product rebrand | Live app titled "UK Planning Deal Finder" throughout | "PropertyAIgent" everywhere — browser tab, app header, page titles | P0 |
| Loading indicators | Spinner only on AI-triggered actions; default progress bar otherwise | Spinner (with descriptive label) extended to every action that takes >~1s, including data-heavy reruns | P1 |
| Skeleton states | None | Skeleton placeholders for the map/table region during a filter-triggered rerun | P2 |
| Empty states | Single plain sentence (or, on Scheme Detail with no selection, a true dead end) | Every empty state includes a clear next action (search box, CTA button, or explanatory context) | P0 (Scheme Detail dead end) / P1 (others) |
| Success notifications | Only present for a handful of actions (e.g. saving contact edits) | Consistent `st.success`/`st.toast` confirmation for every state-changing action | P2 |
| Spacing / clutter | Continuous scroll, no section boundaries beyond ad hoc dividers | Card-grouped content, one divider per named section (per [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md)) | P1 |
| Badges | Ad hoc emoji + Streamlit alert colours, no shared vocabulary | Status/Evidence/Review badge system, one definition used everywhere | P1 |
| Terminology | Mixed "Scheme"/"Site"/"Allocation," some raw internal enum values surfacing directly | Standardised on "Site" per the domain model; a full label pass replacing raw enum strings with commercial-grade text | P1 |

---

## Phased Rollout

Phases are sequenced by **impact on the first ten seconds of a demo**, then by dependency (a design system needs to exist before pages are restyled against it; navigation needs to exist before a Dashboard has somewhere to live).

### Phase 1 — Demo-Ready Baseline (P0)
The minimum needed before this platform is shown to a planning consultant, land promoter or developer.

1. **Rebrand** — "UK Planning Deal Finder" → "PropertyAIgent" across every page title and the app header.
2. **Fix the Scheme Detail dead end** — a real empty state (search box or CTA) when no site is selected.
3. **Adopt the design system's base theme** — `.streamlit/config.toml` palette/typography (Part 10), applied globally, zero page-level layout changes required to get an immediate visual-consistency lift.
4. **Reduce the home page's opening clutter** — move the three review-queue notices out of the primary above-the-fold flow (they relocate to the Dashboard in Phase 2, but even a temporary collapse behind one "Needs attention" summary line is a same-day win).

### Phase 2 — Navigation & Dashboard (P1)
Establishes the structural fix everything else builds on.

1. **Navigation restructure** — Dashboard / Explore / Planning / Policy / Reports / Administration, per [UX_AUDIT.md](UX_AUDIT.md) Part 4.
2. **Build the Dashboard** — per [UX_AUDIT.md](UX_AUDIT.md) Part 5: what's changed, what needs attention, where the opportunities are. This is what finally gives the home page a genuine "front door" separate from the search/filter/map experience.
3. **Separate Administration visually** — Council Dashboard and Review Site Links moved behind a clearly distinct nav treatment, so an internal ops page is never mistaken for a product page.

### Phase 3 — Site Profile Restructure (P1)
The flagship page, per the brief — highest content value, currently the least structured.

1. Introduce the tabbed section structure (Overview / Planning Position / Policy Position / Visual Evidence / Nearby Development / Timeline / AI Summary) per [UX_AUDIT.md](UX_AUDIT.md) Part 6.
2. Promote Companies & Contacts to its own always-visible section, out of the bottom of the scroll.
3. Add the Overview stat-tile row (Total units / Affordable % / Development type / Data quality) as the page's new headline, replacing the raw address-only heading.
4. Add the "Nearby Development" placeholder tab (clearly labelled coming soon), previewing the Market Intelligence layer per [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) without implementing it.

### Phase 4 — Design System Rollout (P1/P2)
Apply the full component set (Part 10) beyond the Phase 1 base theme.

1. Status Badges — replace ad hoc emoji/alert-colour status signalling everywhere it currently appears (home table, Site Profile, Council Dashboard, Local Plan Sites).
2. Evidence Badges — move source attribution from collapsed "Evidence" expanders to inline badges next to the facts they support.
3. AI-Generated Content styling — apply the purple-accent card treatment to every AI summary (Local Plan Summary, Site AI status summary), not just the Council Dashboard's current implementation.
4. Table column curation — default to a curated column set with a "show all" toggle, on the home page table, Local Plan Sites table, and Council Dashboard summary table.

### Phase 5 — Remaining Page Polish (P2)
1. **Local Plan Sites** — allocation-imagery gallery/grid view, free-text search across policy reference/site name (per [UX_AUDIT.md](UX_AUDIT.md) Part 8).
2. **Council Dashboard** — flatten nesting to 2 levels max, add a glanceable per-council health indicator (per Part 7).
3. **Maps** — build a proper legend component (part of the badge/legend pattern in [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md)), reserve visual space for a future layer-control panel without building it yet (per Part 9).

### Phase 6 — Interaction & Accessibility Polish (P2/P3)
1. NL search example-chip suggestions; live query affordance.
2. Colourblind-safe check on the map's status/housing-type palettes; text-paired status everywhere colour currently carries meaning alone.
3. Emoji-as-status audit — confirm every status emoji has a text equivalent nearby (most already do; close the remaining gaps).

---

## What This Roadmap Deliberately Does Not Include

Consistent with the brief and with [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)'s own capability sequencing:

- No Market Intelligence, Development Economics, or AI Decision Support functionality — only clearly-labelled placeholders where their eventual UI will live (Dashboard's Watchlist card, Site Profile's Nearby Development tab).
- No GIS layers — the Maps section (Phase 5) only reserves visual space for a future layer panel, per [UX_AUDIT.md](UX_AUDIT.md) Part 9's explicit instruction not to implement GIS.
- No new intelligence engines of any kind — every item above is presentation-layer only, matching every existing capability's current, real data.

---

## Sequencing Rationale

Phase 1 exists because a rebrand and a dead-end fix are same-day, zero-dependency wins with outsized impact on a first impression — they should not wait behind a full navigation rebuild. Phase 2 (navigation + dashboard) is sequenced next because every later phase assumes navigation exists to reach it from. Phase 3 (Site Profile) is prioritised immediately after navigation because it is explicitly the flagship page and the audit's single highest-value structural fix. Phases 4–6 are lower-dependency, higher-volume polish work, sequenced by how much of the product each phase's fix touches (design system components first, since they're reused everywhere; page-specific fixes last).
