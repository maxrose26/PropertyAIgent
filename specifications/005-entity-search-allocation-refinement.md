# Entity Search + Allocation Card Refinement

## Objective

Improve PropertyAIgent's discovery/search architecture while simplifying Allocation Discovery cards, without merging the two domain models `004-core-domain-model.md` already keeps separate: Planning Application (a regulatory submission) and Policy/Allocation (planning intent, via `LocalPlanSite`).

The Allocation Discovery gallery card currently gives the "no linked planning application" signal an oversized, repetitive panel on every card that has no link - see `app.reporting.allocation_discovery.show_no_application_panel`/`NO_LINKED_APPLICATION_PANEL_MESSAGE`. That panel is replaced here by a compact positive tag shown only where a link genuinely exists, with the explanatory wording moved to the Allocation Detail state instead.

Separately, Explore's Site/Application search and Allocation Discovery's own search behave as two disconnected product experiences today - a user looking for "JPA 8" or "HOM 2.1" has to already know which page to search on. This spec introduces a reusable Entity Search layer that searches both, while keeping every result explicitly tagged with which domain object it came from.

## Business Value

- Removes a visually dominant, repeated negative-framed panel from every unmatched allocation card, letting the gallery read as evidence, not as a wall of "nothing found" notices.
- Gives a user one place to search "JPA 8", an address, an application reference or a policy reference, without needing to already know whether that's an Application or an Allocation.
- Preserves `004-core-domain-model.md`'s domain boundary: the UX may unify search, the database never unifies Site/Application and Policy/Allocation into one entity.

## User Story

As a land promoter or planning consultant using PropertyAIgent,
I want to search once across both planning applications and Local Plan allocations, and see Allocation Discovery cards that lead with genuine evidence rather than a repeated "not found" panel,
So that I can find what I'm looking for faster and trust that what the platform shows me is either confirmed or clearly marked as unconfirmed.

## Requirements

**Allocation cards (Part 1-2)**
- Remove the `render_alert("opportunity_signal", ...)` "No linked planning application currently identified" panel from the gallery card.
- Show a compact `🔗 Planning application linked` tag, alongside the existing plan-status/review-status badges, only when `linked_application_count > 0`.
- Never show a negative card-level panel when there is no link - the existing "No Linked Application" discovery category/filter is preserved as the way to find these allocations.

**Allocation detail (Part 3)**
- List every linked Application (never pick one and hide the rest): reference, site/address, planning status, decision, units where supported, the site-level build/commencement status, and a link to Site Profile.
- Where none are linked: `"No planning application is currently linked to this allocation in PropertyAIgent."` plus the optional note `"An application may exist but not yet have been matched."`.

**Entity Search (Part 4-13)**
- A new pure module, `app.reporting.entity_search`, with a typed `SearchResult` dataclass (matching the project's existing `SearchFilters`/`AggregateAnswer` dataclass convention in `app.search.query_parser`) and two independent search functions - one over `LocalPlanSite` (via the already-batched `app.reporting.allocation_discovery.build_allocation_discovery`), one over `Application` (a single bounded, `LIMIT`-ed query) - never a combined query or a combined table.
- Deterministic ranking only: exact reference match, then exact title match, then prefix match, then substring match, then id tie-break. No AI, no scoring, no `OPENAI_API_KEY` dependency anywhere in this module.
- Explore gets an explicit scope selector (All / Planning Sites / Allocations) and a deterministic search box, kept visibly separate from the existing optional AI-enhanced natural-language box.
- "All" scope returns grouped, never-merged results, each entity type in its own section, with a subtle cross-link indicator (`"Linked to allocation <ref>"` / `"Linked planning Site"`) wherever a real `matched_site_id` relationship already exists.

## Non-Requirements

- No new combined Site/Application/Allocation database table or model.
- No Land Registry integration, no landowner inference from coordinates or addresses.
- No opportunity/relevance scoring, no AI-ranked search results.
- No user profile or persona-specific matching.
- No changes to extraction pipelines, Development Economics, or a redesign of Dashboard/Council Intelligence/Site Profile.

## Data Model

No schema changes. `SearchResult` (see `app/reporting/entity_search.py`) is a read-only, request-scoped view model, not a persisted entity - it always carries `entity_type` so a caller can never treat an allocation result as if it were a Site result or vice versa. The existing `LocalPlanSite.matched_site_id` FK remains the only relationship this spec reads between the two domain objects; nothing new is added to either table.

## User Experience

Allocation Discovery gallery cards keep their existing content and layout, minus the removed panel and plus one small badge. Allocation Detail gains a genuinely richer "Matched Site and Applications" section when a link exists (one block per linked Application, not a single merged summary). Explore gains a compact scope selector and a second, clearly-labelled search box above its existing AI-enhanced one; typing a query there shows a grouped results panel with direct navigation into Allocation Discovery's detail state or Site Profile.

## Architecture Considerations

`app.reporting.entity_search` sits above both existing reporting modules (`allocation_discovery`, and Application queried directly, mirroring how `app.ui.common` already queries `Application`/`Site` elsewhere) rather than replacing either. It is presentation-agnostic (no Streamlit import) so `app/ui/pages/0_Explore.py` stays a thin caller, per CLAUDE.md's "keep business logic out of the UI". Both search paths are bounded, batched queries (see each function's own docstring for its exact query budget) - Explore's existing per-request cost does not grow with the number of allocations or applications in the database.

## Acceptance Criteria

- No allocation card shows the old panel; a linked-application tag appears only where `linked_application_count > 0`.
- Allocation Detail lists every linked Application when one or more exist, and shows the new concise wording otherwise.
- Entity Search returns correctly-scoped, correctly-typed, deterministically-ranked results for allocation name, policy reference, Application reference, Site/address and council queries, with `OPENAI_API_KEY` unset.
- Full test suite passes; query-count tests confirm no N+1 pattern in either search path.
- `master` and the domain model in `004-core-domain-model.md` are unchanged.

## Future Enhancements

### Ownership Intelligence (future Market Intelligence module)

Not implemented in this sprint. Product Owner amendment (continuation review): moved out of `specifications/001-platform-vision.md`, which the Product Owner identified as historical/superseded and not the right home for new architecture going forward. The canonical architecture record now lives in `docs/PLATFORM_ARCHITECTURE.md` §3 Market Intelligence instead. A short forward-looking mention was also added to `docs/PRODUCT_ROADMAP.md` §3 Market Intelligence's "Future functionality" list, without scheduling it into that section's implementation order, since it isn't ready to be sequenced yet.

### Future user-specific opportunity matching

`SearchResult`'s fields (entity type, capacity/units, status, council, matched-entity linkage) are the seam a future SME housebuilder / land promoter / housing association / investor matching feature would read from - deliberately not built now, and deliberately not a universal "best site" ranking (see `004-core-domain-model.md`'s Design Principles: "let AI enhance decisions rather than replace evidence").
