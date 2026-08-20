# Allocation Intelligence V7 Quality Hardening

## Objective

The first real multi-allocation v6 production run (51/32/66/196) succeeded for three allocations and correctly rejected the fourth for a genuine hallucination - but the successful output revealed real product-quality issues (a wrong party/Application attribution risk, a prose claim not supported by its underlying evidence, over-claimed real-world absence), and a real CLI eligibility-reporting bug was found alongside it. This spec closes all four without weakening any grounding check.

## Business Value

Real production output is the only reliable signal for whether Allocation Intelligence is actually trustworthy commercial intelligence, not just technically ungrounded-free. This amendment converts four concrete, evidenced production findings into fixes, keeping the "evidence-grounded" promise credible as the product moves toward wider rollout.

## Requirements

- **Party-attribution prompt clarity**: `_render_applicant_line` now states explicitly, per entry, when an applicant's own evidenced reference is NOT the Site's representative Application. Rule 2a instructs the model to prefer the safe general form ("associated with planning activity on the Site") whenever it is not citing one specific, correctly-evidenced reference.
- **Prose-grounding clarity for non-applicant roles**: `_render_ownership_line`'s evidence-source wording no longer reads as "submitted this Application" - it now names the evidence *document*, with an explicit negative statement. Rule 2 gained a concrete counter-example matching the real Holmpatrick Ltd mistake. This is an explicit mitigation, not a structural guarantee - no general NLP claim-parser was built (out of scope by instruction); free prose is still never token-scanned.
- **Absence-of-evidence semantics**: new Rule 16 - absence of evidence on this platform is never described as absence in the real world; a genuine, material absence is framed as a concrete investigation signal, never as a speculative reason (e.g. "cautious commercial outlook") the evidence doesn't support.
- **Commercial synthesis quality**: reworked headline/overview guidance toward an "analyst, not summariser" framing and information density; key_uncertainties/investigation_priorities guidance now explicitly discourages generic, could-apply-to-any-allocation phrasing.
- **Dry-run/execute eligibility parity**: `scripts/generate_allocation_intelligence_summaries.py`'s `_classify` is now the single function both `_run_dry_run` and `_run_execute` call - no separately hand-written freshness check in `_run_execute` any more.
- **Staleness/prompt-version parity**: `is_allocation_summary_stale` now delegates to `should_regenerate_allocation_summary` (after its own distinct "missing is not stale" pre-check) instead of comparing only the fingerprint - a prompt-version bump alone now correctly marks a summary stale, matching what generation itself has always done.
- `PROMPT_VERSION` bumped to v7 (v6 was genuinely deployed and used for three real successful generations).

## Non-Requirements

- No general NLP/semantic prose fact-checker.
- No numeric allow-listing of "83" - confirmed AI-derived arithmetic (100% − 17% coverage), a genuine hallucination, still rejected.
- No weakening of any existing grounding check (numeric, reference, status/decision, entity/role/scope, trust boundary).
- No fuzzy entity resolution, no Local Plan Delivery Intelligence, no buyer scoring, no UI change, no capacity-arithmetic change, no allocation/Site-matching change.
- No database schema change, no migration.
- No production data changes, no OpenAI calls, no summaries regenerated, no automatic refresh enabled.

## Data Model

No schema/migration. No new dataclass fields. `SUMMARY_SCHEMA` unchanged from v6.

## Architecture Considerations

Root causes were confirmed against real, persisted production data and live production context (read-only), not assumed:
- Heald Green West's rejection was the validator *correctly* catching a wrong Application attribution - a prompt-clarity gap, not a validator bug.
- Britannia Mill's real successful output contained a prose claim ("Holmpatrick Ltd has submitted a planning application") that was never self-reported at all, so nothing checked it - a genuine, confirmed prose/self-report gap, explicitly not solved with a general parser per instruction.
- Beal Valley's real successful output over-claimed real-world absence in several places - a prompt-guidance gap.
- The CLI's dry-run/execute mismatch was a genuine, confirmed logic-duplication bug (two independently-hand-written eligibility checks that had drifted apart) compounded by `is_allocation_summary_stale` never checking `prompt_version` - both fixed centrally, with the fingerprint/prompt-version fix keeping `should_regenerate_allocation_summary` as the ONE place that decision is made.

## Acceptance Criteria

- All four real production contexts (51/32/66/196), re-inspected read-only, show the corrected prompt wording exactly as designed (confirmed directly, not just via fixtures).
- `_classify` used identically by both dry-run and execute; a prompt-version-only change is now correctly detected as stale.
- Full test suite passes with zero failures (2466/2466 at implementation time, up from a 2441 pre-this-spec baseline).

## Future Enhancements

- A structural (non-NLP) mechanism to guarantee prose claims are always self-reported remains an open question - flagged as a known limitation, not solved here.
