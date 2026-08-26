# Allocation Discovery Gate 1A - Pre-Merge Performance Amendment

## Issue

Pre-merge review of Gate 1A (`specifications/012-allocation-discovery-gate-1a-table.md`) identified that the previous implementation report's claim - "one call on batch submit" - was wrong. Re-inspecting the actual execution order confirmed the suspected sequence exactly:

1. `st.form_submit_button` click triggers Streamlit's normal, automatic rerun.
2. `build_allocation_discovery(session)` executes unconditionally near the top of the script, before the tab loop - so it runs once for this rerun (build #1).
3. The script reaches the tab whose form was submitted; `submitted` is `True`.
4. The shortlist is mutated.
5. An explicit `st.rerun()` (previously present) immediately aborts the rest of this script run and starts a new one.
6. `build_allocation_discovery()` executes again from the top (build #2), purely so the shortlist badge (computed before the tab loop) and the flash message could reflect the new state.

One batch submission therefore paid the ~14-query/~2s discovery-build cost **twice**, not once as previously and incorrectly reported.

## Fix

Removed the explicit `st.rerun()` after the batch shortlist mutation. The two things it existed to refresh are instead updated inline, in the same script pass that already has the build's result available:

- **Badge**: the "N allocations shortlisted" link is now rendered into an `st.empty()` placeholder created once near the top of the script. The batch-submit handler (further down, inside the tab loop) calls the same `_render_shortlist_badge()` helper again after mutating state, overwriting the placeholder's content in place - a standard, well-established Streamlit pattern requiring no rerun.
- **Feedback message**: the previous approach stored a message in `st.session_state["_shortlist_add_feedback"]` and displayed it (via `session_state.pop`) only on the *next* script run - which depended on the (now-removed) rerun to ever appear promptly. It is now shown directly with `st.success(...)` at the point of mutation, in the same pass - arguably an improvement, since it now appears immediately next to the action that produced it rather than scrolled to the top of the page after a full reload.

## Execution flow (before / after)

**Before**: submit → rerun #1 (discovery build #1) → mutate → `st.rerun()` → rerun #2 (discovery build #2) → badge/message shown.
**After**: submit → rerun #1 (discovery build #1) → mutate → message shown inline → badge placeholder updated inline. One discovery build, not two.

## Detail-view toggle

Reconfirmed unchanged from Gate 1A: no explicit `st.rerun()` present (verified by a new AST-based regression test, not just re-reading the code).

## Performance verification

- **CODE-VERIFIED**: no `st.rerun()` call exists anywhere within the batch-submit `if submitted:` block or the detail-view toggle's `if _in_shortlist:` block (new AST-based tests, immune to false-positives from this file's own explanatory comments mentioning "st.rerun()" as text).
- **CODE-VERIFIED**: exactly 3 real `st.rerun()` call sites remain in the whole page (detail-view "back" button, "Clear filters", "Show more" pagination) - all pre-existing, all unrelated to the shortlist, all out of this amendment's scope.
- **INFERRED** (from the above, not independently re-measured against production): one batch submission now costs exactly one `build_allocation_discovery()` execution, matching the natural cost of any other Streamlit interaction on this page - down from two.
- **MANUAL-UX-VERIFIED** (brief, per explicit instruction not to spend significant time here): the page loads cleanly against production data with no server errors, and the badge placeholder correctly renders nothing when the shortlist is empty. Full interactive re-verification of the batch-submit flow was not repeated in this amendment, given the prior task's already-documented automation-environment constraints (canvas-rendered grid, no screenshot support) and this task's explicit instruction not to spend significant time on them.

## Tests

3 new tests (`tests/test_allocation_discovery.py`), all using `ast` to inspect `app/ui/pages/3_Local_Plan_Sites.py`'s real source rather than a plain substring search (which would false-positive against this file's own comments describing the fix): `test_batch_submit_handler_contains_no_explicit_rerun`, `test_page_contains_exactly_the_three_pre_existing_non_shortlist_rerun_calls`, `test_detail_view_shortlist_toggle_contains_no_explicit_rerun`. All prior Gate 1A tests (`build_table_row`, `resolve_selected_cards`, shortlist batch-add pattern) are unchanged and pass.

## Unchanged

`ReportCandidate`, `st.session_state["_shortlist"]`, every `app.ui.shortlist` helper function, table columns, pagination, sorting, party evidence, filters, and all Gate 2 architecture - none touched by this amendment.
