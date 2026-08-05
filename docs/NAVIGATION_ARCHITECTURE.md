# PropertyAIgent — Navigation Architecture

The complete navigation design for PropertyAIgent, aimed at making a genuinely deep intelligence platform feel like a modern commercial SaaS product from the first click. This document defines the vocabulary — page names, nav groups, URL structure — that [WIREFRAMES.md](WIREFRAMES.md) and [INTERACTION_DESIGN.md](INTERACTION_DESIGN.md) both build on.

Grounded in [UX_AUDIT.md](UX_AUDIT.md) Part 4's navigation review and [PRODUCT_EXPERIENCE_ROADMAP.md](PRODUCT_EXPERIENCE_ROADMAP.md) Phase 2, and styled per [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md). This is a design document only — see those documents' own scope notes; nothing here is implemented.

---

## Design Principle

**Customer-facing intelligence and internal administration are two different applications sharing one platform**, never two flavours of the same page. A planning consultant should never be one accidental click from a page that says "not part of the public experience" (as the current Council Dashboard does, per [UX_AUDIT.md](UX_AUDIT.md)) — and an administrator should never have to leave the operational workflow to find review/monitoring tools. This single principle drives almost every decision below.

---

## Top-Level Structure

```
PropertyAIgent
│
├── CUSTOMER EXPERIENCE
│   ├── Dashboard              (home / landing)
│   ├── Explore                 (search, map, filters, results)
│   ├── Site Profile            (reached via Explore/search, not a standalone nav item)
│   ├── Policy
│   │     ├── Council Intelligence   (per-council customer-facing view)
│   │     └── Local Plan Sites       (allocation browser)
│   └── Reports                 (export + generated documents)
│
└── ADMINISTRATION                                    (visually and structurally separate)
      ├── Review Centre         (all pending-review queues, consolidated)
      └── Council Operations    (monitoring health, document coverage, source registration)
```

---

## Top Navigation

A persistent horizontal bar, present on every customer-facing page (Streamlit's `st.navigation(position="top")` makes this a realistic, buildable pattern — noted for feasibility, not as an implementation instruction):

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  🏠 PropertyAIgent    Dashboard   Explore   Policy ▾   Reports        [🔍 Quick search] ⚙ │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

- **Product name** ("PropertyAIgent," fixing the current live-app/documentation naming mismatch flagged in [UX_AUDIT.md](UX_AUDIT.md)) is the permanent top-left anchor and doubles as "return to Dashboard."
- **Primary tabs**: Dashboard, Explore, Policy (a dropdown revealing Council Intelligence / Local Plan Sites), Reports. Four items, matching the brief's own worked example structure and avoiding the current sidebar's flat, undifferentiated list.
- **Quick search** sits on the right of the bar, always available regardless of which page is open (distinct from Explore's own natural-language search box — see Search, below).
- **⚙ (Administration entry point)** sits furthest right, visually separated by a divider and a muted/greyed treatment distinct from the primary tabs' active colour — a deliberate, permanent visual signal that this is a different kind of page, not just another tab.

## Sidebar

Not a global page-list (that job now belongs to the top nav). The sidebar becomes **contextual to the page it appears on** — exactly the content that's genuinely page-specific:

| Page | Sidebar content |
|---|---|
| Explore | Filters (council, housing type, unit thresholds, etc.) |
| Site Profile | Section jump-links (Overview, Planning, Policy, Visual Evidence, …) — replacing today's continuous-scroll-with-no-wayfinding |
| Council Intelligence | Council switcher (jump between councils without returning to a list) |
| Local Plan Sites | Filters (council, image availability) |
| Review Centre | Review-queue category switcher (Site Matching / Visual Evidence / Policy Evidence / Monitoring) |

This directly resolves the audit's finding that the Credits widget (an internal spend-throttle) currently outranks Filters in visual priority — Credits moves to Administration, and each page's sidebar carries only what that page actually needs.

## Breadcrumbs

Used wherever a page is reached by drilling into something, never on the four top-level destinations themselves:

```
Dashboard  ›  Explore  ›  Old Grove House, 13 Vine Street, Hazel Grove
Dashboard  ›  Policy  ›  Stockport  ›  HOM 2.12 Compstall Mills
Administration  ›  Review Centre  ›  Visual Evidence
```

Every breadcrumb segment is a real link back up the chain — critical for a platform where "how did I get to this specific piece of evidence" is itself a meaningful question a user may want to retrace (consistent with [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md)'s transparency principle).

## Search

Two distinct, intentionally different search surfaces — conflating them was a real source of confusion in the current single natural-language box doing double duty:

1. **Quick search** (top nav, everywhere) — a fast, autocomplete jump-to-a-specific-thing search: type a Site address, council name, or policy reference, get a short dropdown of direct matches, press Enter or click to go straight there. This is a **navigation tool**, not an intelligence query.
2. **Explore search** (Explore page only) — today's natural-language structured query ("projects with 50+ affordable units…"), which filters and ranks a result set. This is an **intelligence tool**, staying exactly as capable as it is today, just no longer also expected to double as the site's primary navigation.

## Quick Actions

A small set of always-available actions, surfaced as icon buttons in the top nav (not buried in page content):

- **New search** — clears Explore's current filters/query and refocuses the search box.
- **Export current view** — available wherever a result set or Site is on screen (routes to Reports' existing export capability).
- **Notifications** (🔔) — a lightweight badge-count icon reflecting the Dashboard's "needs attention" total (Part 3 of [WIREFRAMES.md](WIREFRAMES.md)), giving administrators and power users a persistent, page-independent signal without requiring a Dashboard visit.

## Future Expansion

Per the brief's explicit instruction, **future capabilities are never exposed as clickable-but-empty nav items.** Market Intelligence, Development Economics, AI Decision Support (beyond today's narrow summary generation) and Workflow & Collaboration have no entry in the top nav or Policy dropdown today. Instead:

- Their eventual home is **foreshadowed contextually**, inside the pages where their content will actually live (Site Profile's "Nearby Development" and future "Development Economics" tabs, Dashboard's "Watchlist" card, Reports' listed-but-disabled future report types) — see [WIREFRAMES.md](WIREFRAMES.md) Part 11.
- When a capability is genuinely ready to ship, it becomes a **new top-level tab or Policy-style dropdown group**, following the same pattern established here — the navigation architecture is designed to extend by addition, not by restructuring what already exists. A plausible future top nav, once Market Intelligence and Development Economics both exist, is `Dashboard · Explore · Policy ▾ · Market ▾ · Reports` — noted here only to confirm the current structure has somewhere natural to grow, not as a commitment to that exact shape.

## Administration

Structurally and visually separate from the four customer-facing destinations, reached only via the muted ⚙ entry point in the top nav — never appearing in the primary tab set, never discoverable by a customer-facing user unless they deliberately seek it out:

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  ⚙ Administration                                              [← Back to Dashboard]   │
├──────────────────────────────────────────────────────────────────────────────────────┤
│   Review Centre        Council Operations        Credits & Usage                        │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

- **Review Centre** — see [WIREFRAMES.md](WIREFRAMES.md) Part 8; consolidates every pending-review queue that today is scattered across the home page, Council Dashboard, and individual Site pages.
- **Council Operations** — the operational half of today's Council Dashboard (monitoring health, document coverage internals, source registration status) split out from its customer-facing half (Council Intelligence, now living under Policy — see [WIREFRAMES.md](WIREFRAMES.md) Part 6).
- **Credits & Usage** — today's Credits sidebar widget, relocated here in full (add credits, view remaining balance, usage history) — an internal spend-throttle, never a customer-facing concern.

A persistent, distinctly-styled banner ("You are viewing Administration") appears on every page under this section, so it is never ambiguous which "mode" of the product is currently on screen — directly resolving the audit's Critical-severity finding that an explicitly internal page currently carries the same visual weight as the product itself.

---

## URL / Route Structure (conceptual)

Not an implementation instruction — a naming convention the wireframes and interaction design both assume, so a future implementation has a coherent structure to follow rather than inventing one page-by-page (consistent with [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md)'s "modular architecture" principle):

```
/                          → Dashboard
/explore                   → Explore
/site/{id}                 → Site Profile
/policy/councils/{code}    → Council Intelligence
/policy/allocations        → Local Plan Sites
/policy/allocations/{id}   → Allocation detail
/reports                   → Reports
/admin                     → Administration home
/admin/review              → Review Centre
/admin/review/{category}   → Review Centre, filtered to one category
/admin/councils            → Council Operations
/admin/credits             → Credits & Usage
```
