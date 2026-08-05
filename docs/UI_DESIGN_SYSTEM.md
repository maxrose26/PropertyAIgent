# PropertyAIgent — UI Design System

A lightweight design language for a Streamlit product, aimed at **consistency, not visual novelty** — every rule below exists to make the platform's underlying rigour (evidence, provenance, review status) visible and legible, not to redesign it. This document specifies what to build; it does not implement it — see [PRODUCT_EXPERIENCE_ROADMAP.md](PRODUCT_EXPERIENCE_ROADMAP.md) for sequencing. Findings that motivate these choices are in [UX_AUDIT.md](UX_AUDIT.md).

Everything specified here is realistic within Streamlit: a `.streamlit/config.toml` theme for the base palette/typography, plus a small set of reusable HTML/CSS snippets (rendered via `st.markdown(..., unsafe_allow_html=True)` from **static, developer-authored strings only** — never from AI-generated or user-supplied text, preserving the security discipline already documented in `app/ui/common.py`) for badges, cards and status pills that Streamlit doesn't provide natively.

---

## Typography

One typeface family (Streamlit's default system font stack is acceptable — no custom font loading required), one scale:

| Role | Streamlit primitive | Notes |
|---|---|---|
| Page title | `st.title` | One per page, always the Site address / plan name / page purpose — never the product name (that lives in the nav header). |
| Section heading | `st.header` | Used for the named sections introduced in [UX_AUDIT.md](UX_AUDIT.md) Part 6 (Overview, Planning Position, etc.) |
| Subsection heading | `st.subheader` | Used within a section (e.g. "Companies & contacts" within a Site Profile). |
| Body text | `st.markdown` (plain) | No bold-label-sentence pattern for structured facts — see Stat Tiles below. |
| Caption / metadata | `st.caption` | Source attribution, timestamps, confidence — always secondary, never used for a primary fact. |

**Rule:** a fact the user is meant to scan (a unit count, a status) is never delivered only as a bold word inside a sentence. It gets a Stat Tile or Badge (below). Bold-in-sentence is reserved for narrative content (AI summaries, evidence text).

## Spacing

Streamlit's own vertical rhythm (one block per `st.` call) is kept, with two explicit rules to fix today's inconsistency:

- **One `st.divider()` between named sections, never mid-section.** (Today's pages use dividers inconsistently — sometimes between unrelated content, sometimes not at all between genuinely distinct blocks.)
- **Related facts are grouped inside one container** (`st.container(border=True)`, available in current Streamlit) rather than as a loose sequence of independent `st.markdown` calls — this is what gives the Card treatment below its visual boundary without custom CSS.

## Cards

A **Card** is `st.container(border=True)` holding one coherent unit of information — a stat-tile row, a company entry, a KPI block. Cards are the default container for anything that today renders as an unbounded sequence of `st.markdown` lines (e.g. each company in "Companies & contacts", each KPI on the new Dashboard).

**Stat Tile** — a small Card variant for a single headline figure:
```
┌──────────────────┐
│ TOTAL UNITS        │
│ 45                  │
└──────────────────┘
```
Rendered as a `st.container(border=True)` with a small caption-styled label above a large value — used for the Site Profile Overview (Part 6 of the audit) and the Dashboard KPI strip (Part 5).

## Tables

- **Default to a curated column set**, not every available field. Every table in the product today (home page, Local Plan Sites, Council Dashboard summary) shows 8–20+ columns at once; the design system default is the 5–7 columns a user actually scans, with a "Show all columns" toggle (`st.checkbox`) revealing the rest via `st.dataframe`'s `column_order`.
- **`st.dataframe` over `st.table`** throughout (already the pattern in use) — sortable, selectable, and consistent with the platform's existing interaction model.
- **Row selection** (`on_select="rerun"`) is the standard way to drill into a table row — already used well on the home page; extend the same pattern anywhere a table currently has no way to act on a row.

## Buttons

- **Primary action per page, one only** — `st.button(..., type="primary")` for the single most important action in a section (e.g. "Unlock contacts", "Confirm same site"). Every other button stays default/secondary styling. Today's pages don't distinguish primary from secondary actions at all — every button looks identical regardless of importance.
- **Destructive or state-changing actions get a confirming label, not just a verb** — "Exclude from results," "Reject — different site" (already good practice on Review Site Links; extend it everywhere a button changes stored state).
- **Every state-changing button resolves to a visible confirmation** (`st.success`/`st.toast`) — see Alerts below.

## Icons

Emoji are kept (they render natively in Streamlit with no dependency, and several are already well-chosen — 🏗️ for construction, 📋 for policy), but their role is narrowed and made consistent:

| Use | Icon | Meaning, and only this meaning |
|---|---|---|
| ✅ | Confirmed / current / OK | A human-reviewed or system-healthy state |
| ⚠️ | Needs review / caution | An AI-derived, not-yet-reviewed fact, or a data caveat |
| 🕗 | Pending / awaiting change | A proposed change awaiting approval |
| 🆕 | New evidence available | A newer source exists, not yet extracted |
| 🚫 | Excluded / rejected | A human decision to exclude |
| 🤖 | AI-generated content | Marks AI Summary content specifically (see AI-Generated Content Styling below) — never used for any deterministic fact |
| 📋 | Policy | Local Plan / allocation content |
| 🏗️ | Build / construction | Site build-status content |

**Rule:** an icon is never introduced for decoration. If a new icon is proposed, it must map to exactly one entry in this table, and that table is the single source of truth — no page invents its own icon meaning.

## Colours

Base palette, set once in `.streamlit/config.toml` under `[theme]`, inherited everywhere rather than re-specified per page:

| Token | Hex (light) | Use |
|---|---|---|
| `primaryColor` | `#1F3A5F` (deep navy-blue) | Primary buttons, active nav item, page titles — professional, not a "startup" bright colour, in keeping with a planning/property-sector audience |
| `backgroundColor` | `#FFFFFF` | Page background |
| `secondaryBackgroundColor` | `#F4F6F8` | Sidebar, card backgrounds |
| `textColor` | `#1A1A1A` | Body text |

Status colours (used only via the Badge component below, never as raw inline styling per page):

| Status | Colour | Hex |
|---|---|---|
| Confirmed / current / healthy | Green | `#1E7E34` |
| Needs review / stale | Amber | `#B7791F` |
| Error / excluded / rejected | Red | `#B42318` |
| Informational / neutral | Blue-grey | `#3B5773` |
| AI-generated | Soft purple | `#6B4FA0` |

This is a deliberately small, sector-appropriate palette (not the "one colour per data dimension" approach the home-page map already correctly uses for its own specific two-channel encoding — that stays as-is, it's a different, already-justified use of colour).

## Status Badges

A single reusable component (one static HTML/CSS snippet, parameterised only by pre-defined label/colour pairs — never by raw user or AI text) replacing today's ad hoc emoji-in-caption pattern:

```html
<span class="pig-badge pig-badge--confirmed">✓ Confirmed</span>
<span class="pig-badge pig-badge--review">⚠ Needs review</span>
<span class="pig-badge pig-badge--pending">🕗 Pending review</span>
```
Rounded-pill shape, status colour from the table above at ~15% opacity background with full-opacity text/icon — legible, not shouty. Used for: application/allocation review status, monitoring health, build status, decision status — every place the product currently renders status as plain coloured `st.info`/`st.warning` text.

## Evidence Badges

A distinct, smaller badge specifically for **source attribution**, always adjacent to the fact it supports rather than hidden in a separate expander (directly addressing the Discoverability finding in [UX_AUDIT.md](UX_AUDIT.md) Part 2):

```html
<span class="pig-evidence-badge" title="Source: Bury Local Plan, page 106">📄 p.106</span>
```
Hovering/clicking reveals the full source document title and link — the same underlying data already captured by the platform's provenance fields (see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md)'s Evidence Platform section), just finally surfaced at the point of use instead of in a collapsed "Evidence" expander below it.

## Review Badges

A specific Status Badge variant, always paired with a confidence indicator when the underlying fact is AI-derived and unconfirmed:

```html
<span class="pig-badge pig-badge--review">⚠ Needs review · 82% confidence</span>
```
Never shown for a deterministically-derived fact (which needs no confidence figure at all) — only for AI classification/matching output, consistent with [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md)'s "Deterministic Before AI" principle: the badge itself is how a user can tell, at a glance, which kind of fact they're looking at.

## Alert Styling

Streamlit's four native alert types are kept (`st.info`/`st.warning`/`st.error`/`st.success`) — no custom alert component — but their use is narrowed to genuine page-level messages (a failed action, a missing prerequisite, a successful save), **not** as a substitute for inline status on a data field (that's what Status Badges are for). This is the single biggest change in practice: most of today's `st.info`/`st.warning` calls embedded mid-page (e.g. the policy-allocation box, the affordable-housing caveat) become Cards with an inline Status/Evidence Badge instead, reserving the full-width alert treatment for messages, not facts.

## AI-Generated Content Styling

Every AI-generated block (Local Plan Summary, Site AI status summary, future planning assessments per [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)'s AI Decision Support layer) gets one consistent treatment, extending the pattern already partially present on the Council Dashboard (`🤖 AI Local Plan Summary`, "AI-generated from verified PropertyAIgent evidence" caption):

```
┌─────────────────────────────────────────────┐
│ 🤖 AI Summary                                  │
│ (soft purple left border, #6B4FA0)             │
│                                                  │
│ [narrative text]                                │
│                                                  │
│ Generated 04 Aug 2026 · gpt-4o-mini             │
│ Built from evidence already verified by this    │
│ platform — see sources below.                   │
└─────────────────────────────────────────────┘
```
Rules:
- Always inside a bordered Card with the AI accent colour as a left border (never the full card background — this is a citation-style treatment, not a warning).
- Always carries the generation timestamp and model — already done well on the Council Dashboard; extend everywhere else AI content appears.
- Never rendered without at least one Evidence Badge nearby linking back to what it was generated from — the visual expression of [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md)'s "AI explains evidence, it does not invent conclusions."

---

## Summary Reference Table

| Element | Component | Governing rule |
|---|---|---|
| Headline figure | Stat Tile | Never bold-in-sentence for a scannable fact |
| Grouped facts | Card (`st.container(border=True)`) | One coherent unit per card |
| Status | Status Badge | One badge vocabulary, defined once, used everywhere |
| Source attribution | Evidence Badge | Always adjacent to the fact, never a separate expander |
| AI-derived + unconfirmed | Review Badge | Confidence shown only for AI-derived facts |
| Page/action message | Native `st.info/warning/error/success` | Messages only, never a substitute for field-level status |
| AI narrative | AI-Generated Content card | Purple accent, timestamp + model, adjacent evidence badge |
