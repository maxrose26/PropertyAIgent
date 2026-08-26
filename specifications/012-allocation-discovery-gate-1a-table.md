# Allocation Discovery Gate 1A - Compact Table + Deferred Multi-Select

## Production UX problem

Live Gate 1 validation surfaced a noticeable delay after clicking "Add to shortlist" on an allocation card, before the user could continue selecting further allocations - making rapid multi-allocation screening feel cumbersome.

## Measured root cause

`build_allocation_discovery(session)` costs ~14 sequential SELECTs / ~2.0s against production (measured, read-only, via a SQLAlchemy `before_cursor_execute` listener). Gate 1's per-card shortlist button called `st.rerun()` **after** that build had already completed for the current script run - discarding it and forcing the whole page (including the discovery build) to execute a second time, per click. Doubling ~2s of backend work on every single shortlist click is a full explanation of the reported latency.

## Final table architecture

The card gallery grid is replaced, per tab/category, with a compact `st.dataframe` results table built from the same already-batched `build_allocation_discovery` cards (no new query path). The rich card/detail rendering itself (`app.ui.shell.allocation_card`, the allocation detail view) is unchanged - the card component is simply no longer called from the gallery loop.

## Form-deferred selection

The table is wrapped in `st.form(...)`, with `st.dataframe(selection_mode="multi-row", on_select="rerun", ...)` and a single `st.form_submit_button("Add selected to shortlist")`. Verified against the installed Streamlit 1.59.0 source (`elements/arrow.py`): `st.dataframe`'s selection state is bound to `current_form_id`, the same form-membership mechanism every standard widget uses - selecting/deselecting any number of rows is therefore a purely client-side interaction while inside the form and triggers **zero** backend reruns; only submitting the form does, once per batch.

## Shortlist batch behaviour

On submit, `resolve_selected_cards(page, selected_row_indices)` (new pure function, `app/reporting/allocation_discovery.py`) maps the selection event's row positions back to the exact card dicts they refer to (defensive against an out-of-range index). The page then loops `add_candidate` once per selected card - duplicate prevention remains structural (unchanged `ReportCandidate`/`_shortlist` dict-key design from Gate 1), so a batch containing an already-shortlisted allocation is a no-op for that entry. A one-shot flash message ("N allocation(s) added to shortlist") is shown via `st.session_state.pop("_shortlist_add_feedback", ...)`.

## Rerun decisions

- **Detail-view toggle**: the previously-explicit `st.rerun()` is removed. This is a single-allocation page outside the rapid-screening flow the redundant rerun was costing latency on - the only visible cost is the toggle button's own label lagging by one interaction (self-corrects on the next click or navigation), traded against not paying another full `build_allocation_discovery()` rebuild to refresh one label.
- **Batch-submit**: one `st.rerun()` is retained, deliberately, after the batch mutation - needed so the shortlist badge (computed near the top of the script, before the form) reflects the new count immediately. This cost is paid once per batch confirm, never once per row selected - a fundamentally different, accepted cost from the pattern being replaced.

## Optional cache decision

**Not implemented.** The form-deferred selection mechanism alone fully satisfies the stated acceptance bar (selecting 5-10 rows causes zero additional `build_allocation_discovery()` calls) with no freshness trade-off. A short-TTL `st.cache_data` wrapper (feasible via an underscore-prefixed session argument, per Streamlit's documented unhashed-argument convention - verified in `runtime/caching/cache_utils.py`) remains a legitimate future refinement for the once-per-batch-submit cost, not required to meet Gate 1A's acceptance bar.

## Detail drill-down

Implemented as a selector (`st.selectbox` populated with `"{site_name} ({council_name})"` labels) + `st.switch_page(THIS_PAGE, query_params={"allocation_id": ...})` button, mirroring the pre-existing pattern at the bottom of `0_Explore.py` ("Or get a shareable link to a specific scheme"), rather than an `st.column_config.LinkColumn` on the allocation-name column. `LinkColumn` renders a real `<a href>` anchor needing a literal, resolvable URL string; this app's internal multipage routing resolves each page to a URL slug that does not straightforwardly match either its title or its filename (confirmed live: neither `/Allocation_Discovery` nor `/3b_Shortlist` resolve - the actual slugs are `/Local_Plan_Sites` and, for the hidden Shortlist page, not reliably guessable at all, which is itself the reason hidden pages are meant to be reached via `st.page_link`/`st.switch_page`, never a constructed URL). Using the already-proven internal-navigation mechanism sidesteps that uncertainty entirely.

## Performance verification

**MEASURED** (production, read-only, unchanged from the design-amendment audit): 14 SELECTs, ~2.0s, for one `build_allocation_discovery()` call. **CODE-VERIFIED** (Streamlit 1.59.0 source): dataframe selection inside `st.form` cannot trigger a backend rerun before submission. **MANUAL-UX-VERIFIED** (live local run against production data, read-only): the table renders correctly per tab (native "Show/hide columns" / "Download as CSV" / "Search" / "Fullscreen" toolbar confirms a real interactive `st.dataframe`, one per tab, each with its own form and submit button); the detail-drill-down selector was populated with correctly-formatted real allocation names and, in one clean end-to-end run, successfully navigated to the correct allocation's detail page with zero server errors; the detail-view shortlist toggle correctly avoided crashing without its former `st.rerun()`. **NOT reproducibly verified**: actual row-selection inside the table itself - Streamlit's dataframe grid is canvas-rendered (glide-data-grid) with no accessible DOM structure for individual rows/cells, and this environment's Browser pane could not render screenshots to allow coordinate-based clicking, so no row could be selected and no selection-triggers-zero-backend-work claim could be directly observed in a live session; a second attempt at the detail-selector flow also did not reproduce cleanly, for reasons not conclusively identified (possibly widget-ref instability across reruns in this specific automation harness). The form-deferred-selection mechanism's correctness rests on the source-level verification above, not on a repeated live observation.

## Tests

17 new tests: `build_table_row` (9, `tests/test_allocation_discovery.py`) covering identity/status field mapping, the canonical `planning_activity_status` reuse (including the neutral no-linked-Application wording), coverage percentage/residual capacity formatting and None-safety (including the `0`-is-not-missing case), and the shortlisted-flag column; `resolve_selected_cards` (5) covering single/multiple index mapping, empty selection, out-of-range-index tolerance, and cross-page index isolation; batch-add pattern (3, `tests/test_shortlist.py`) covering batch idempotency and duplicate-freedom for the exact loop the page runs on submit. All existing Gate 1 shortlist and Allocation Discovery filter/sort/category tests are unchanged and pass.

## Deferred (Gate 2+)

CSV, PDF, the deterministic report-context builder, batched ownership/control evidence, party/developer result columns, the "AI summary available" indicator column (should-have, not implemented - would need a new batched query this gate deliberately did not introduce), natural-language search, NPPF, Planning Potential, Opportunity Potential, Buyer Profiles, any scoring/ranking, database-backed shortlist persistence.
