# PropertyAIgent — Interaction Design

How the screens in [WIREFRAMES.md](WIREFRAMES.md) actually behave — what happens on hover, click, load, filter, and back-navigation — following the navigation model in [NAVIGATION_ARCHITECTURE.md](NAVIGATION_ARCHITECTURE.md) and the visual language in [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md). Design-only, per this sprint's scope — every behaviour below describes intent, not an implementation.

---

## Navigation Behaviour

- **Top nav is always present and always reflects current location** — the active tab (Dashboard/Explore/Policy/Reports) is visually distinguished (primary colour underline/fill, per [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md)'s `primaryColor`), so a user never has to check the breadcrumb just to know which of the four top-level areas they're in.
- **The Policy dropdown expands on hover or click** (not click-only) to reveal Council Intelligence / Local Plan Sites — a two-item menu doesn't need a full click-to-open modal-style interaction; hover-reveal keeps browsing fast.
- **Administration (⚙) is a distinct navigation mode, not a page.** Clicking it doesn't just load a page — it visually re-skins the persistent chrome (the "You are viewing Administration" banner from [NAVIGATION_ARCHITECTURE.md](NAVIGATION_ARCHITECTURE.md)) so there is never a moment of ambiguity about which "half" of the product is on screen. Leaving Administration always requires an explicit "← Back to Dashboard" click, never an accidental one.
- **Breadcrumbs are always clickable up the chain**, including the leaf (current page) segment, which re-scrolls to the top of the current page rather than being inert — small, but it makes breadcrumbs double as a "scroll to top" affordance on long pages like Site Profile.

## Hover Behaviour

- **Map markers** — hovering a Site marker shows the existing plain-text tooltip (address, status, key figures) exactly as built today; this pattern is already sound (deliberately not HTML, for the documented security reason in `app/ui/common.py`) and is kept unchanged, just visually restyled to match the new Card aesthetic (rounded corners, drop shadow) rather than the browser's default tooltip box.
- **Result table rows** — hovering a row highlights it and reveals the `›` open-affordance (today it's present but static); this is the one new hover-triggered reveal introduced, so a user can tell a row is clickable before they click it.
- **Gallery thumbnails (Local Plan Sites)** — hovering a thumbnail card lifts it slightly (subtle shadow increase) and surfaces the policy reference/site name label if it was previously truncated — no click required to preview which allocation a thumbnail belongs to.
- **Badges** — hovering a Status or Evidence Badge (per [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md)) reveals a small tooltip with the full underlying detail (e.g. hovering an Evidence Badge reading "📄 p.106" reveals the full source document title and a "click to open" cue) — badges stay compact by default, full detail is always one hover away, never hidden behind a click-through expander as it is today.

## Loading

- **Every action with a real network/AI cost gets a labelled spinner**, extending today's already-good pattern (AI summary generation, PDF generation, contact enrichment already do this correctly) to cover data-heavy page loads too (e.g. Explore's initial site list, Council Intelligence's evidence load).
- **Skeleton placeholders for structural regions** — the map and results table on Explore, and the Overview stat tiles on Site Profile, show a grey placeholder shape in their final layout position during a rerun, rather than the page briefly going blank/reflowing — this is the single biggest perceived-performance improvement available without any backend change, per [UX_AUDIT.md](UX_AUDIT.md)'s Performance Perception findings.
- **AI-generated content always loads with an explicit label naming what's happening** ("Generating summary from verified evidence...", "Analysing schemes and writing the report...") — never a generic spinner — reinforcing, even in the loading state, that this is evidence-grounded synthesis rather than an opaque black box.

## Filtering

- **Filters apply live, without a submit button**, except the natural-language search box (which genuinely needs a submit, since it triggers a real AI call and shouldn't fire on every keystroke — the existing form-based pattern here is correct and unchanged).
- **Every active filter is visible as a removable chip** above the results, not just reflected in sidebar checkbox state — so a user scanning a narrowed result set can see *why* it's narrowed without opening the sidebar to check.
- **Filter state persists across navigation within Explore** (e.g. opening a Site Profile and returning via breadcrumb keeps the same filters/scroll position) — today's full-page rerun model already tends to preserve this via session state; the design intent is that this is guaranteed, not incidental.

## Selection

- **Single-select behaviours** (choosing a Site from the map or table, choosing an allocation in the Local Plan Sites gallery) always navigate to a detail view — never expand inline. This is a deliberate change from today's inline `render_scheme_detail` expansion pattern on the home page: full navigation gives the Site Profile a real, bookmarkable, breadcrumb-able location, and avoids the page-length problem of an inline expansion pushing everything else down.
- **Multi-select** (today's table row checkboxes, used for the "export selected" flow) is retained specifically for the Explore results table, since bulk export is a genuinely multi-item action — the one place inline multi-select behaviour stays, clearly visually distinguished (checkbox column) from the single-select "click a row to open" pattern used everywhere else.
- **Map selection and table selection stay synchronised** (already true today via `resolve_selected_site_id`) — clicking a marker highlights the corresponding table row and vice versa.

## Back Navigation

- **Breadcrumbs are the primary back mechanism**, not a browser-back-button dependency — every drill-down (Explore → Site, Policy → Council → Allocation, Administration → Review Centre → category) is expressed as a breadcrumb chain a user can step back up at any point.
- **A dead-end state never exists.** Directly fixing [UX_AUDIT.md](UX_AUDIT.md)'s Critical-severity finding: a Site Profile URL with an invalid or missing id shows a real empty state — a quick-search box and an "or browse all sites" link to Explore — never a bare sentence with no way forward.

## Search

- **Quick search** (top nav, everywhere) is autocomplete-as-you-type against Site addresses, council names, and allocation references — a small dropdown of direct matches appears after 2–3 characters; selecting one navigates straight to that Site/Council/Allocation page. No filtering, no AI call — a fast, deterministic jump-to.
- **Explore search** (natural language) keeps today's submit-on-Enter/button behaviour and its existing "Interpreted as: ..." confirmation line — the one addition is a row of clickable example-query chips shown when the box is empty, so a first-time user immediately understands what kinds of questions are answerable, rather than facing a blank placeholder.

## Maps

- **Click-to-open** (marker → Site Profile) is unchanged from today — already a genuine strength (per [UX_AUDIT.md](UX_AUDIT.md) Part 9).
- **The Layers panel** (new, replacing today's single checkbox) opens/closes on click, remembers its open/closed state across a session, and every layer row shows a small coloured swatch matching the legend — so toggling a layer and reading the legend use the same visual language rather than two disconnected UI pieces.
- **Zoom/pan state persists** when navigating away and back to Explore within the same session (e.g. Site Profile → breadcrumb back to Explore) — a user shouldn't lose their place on the map after a detail-view detour.

## Cards

- **A Card is always either fully static (informational) or fully interactive (clickable to a single destination)** — never a mix, avoiding the current pattern where a page has some clickable elements and some inert-looking ones with identical visual treatment.
- **Interactive Cards always carry a hover-lift** (per Hover Behaviour above) as the one consistent signal that a card is clickable, so a user learns the pattern once (Dashboard KPI tiles are static; Dashboard "Needs attention"/"Recent activity" rows and gallery thumbnails are interactive) and it holds everywhere.

## Evidence Expansion

- **Evidence is inline by default, not hidden behind a click.** Directly resolving [UX_AUDIT.md](UX_AUDIT.md)'s Discoverability finding: every fact that today requires opening a separate "Evidence" expander instead carries its Evidence Badge (per [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md)) directly next to the figure.
- **A click on an Evidence Badge opens the source** — either the linked source document (external URL, jumping to the correct page anchor where one exists, exactly as today's `#page=N` links already do) or, for a page-rendered image, a larger preview of that image in place. No navigation away from the current page is required just to check a source.
- **"Show full evidence trail"** remains available as an explicit, clearly-labelled expander *only* for genuinely long content (e.g. an allocation's full extraction history, a plan's historic value log) — the distinction from today is that this is reserved for content that's genuinely too long for inline display, not used as the default hiding mechanism for a single source reference.

## Review Workflows

- **Every review action (confirm/reject) stays a single, unambiguous click**, exactly as today's Review Site Links page already does well — this pattern is the template, not something being redesigned.
- **A review action always produces an immediate, visible confirmation** (`st.success`/toast) and the reviewed item visibly leaves its queue (count decrements in the Review Centre's tab badge) — closing [UX_AUDIT.md](UX_AUDIT.md)'s Commercial Polish finding that many state-changing actions today rerun silently with no confirmation.
- **A rejection is never destructive without context** — every reject action in the Review Centre requires the same side-by-side comparison view already used on today's Review Site Links page (never a bare "reject" button with no evidence shown), consistent with [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md)'s Human Review principle: a reviewer should never have to reconstruct context the platform already has.
- **Batch actions are available within the Review Centre's tabbed queues** (e.g. "confirm all exact-reference-match allocation images") but only ever for items that already meet a defined, visible confidence/match threshold — never a blanket "approve all," which would silently reintroduce the guessing behaviour the platform's matching logic deliberately avoids (per [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md)'s "Deterministic Before AI" and "Never Invent" principles). This is a design constraint worth stating explicitly: efficiency for the administrator must never come at the cost of the platform's own evidentiary discipline.
