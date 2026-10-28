# Specifications

This folder is the specification workflow for PropertyAIgent.

## Purpose

Every major feature begins as a Specification, not as code.

A specification is a short document that explains **what** we are building and **why**, before any implementation work starts. It intentionally describes the product and the architecture first - the data model, the user experience, the acceptance criteria - so that implementation is a translation of an already-agreed design, not the place where the design actually happens.

## How this works

- Before writing code for a significant feature, Claude should read the relevant specification in this folder.
- If no specification exists for the feature being requested, Claude should stop and ask for one to be written before implementing.
- Implementation should follow the specification, not reinterpret it. If the specification turns out to be wrong or incomplete once work starts, the specification should be updated first, and the implementation should follow from that update - not silently diverge from it.
- Specifications are the long-term source of truth for PropertyAIgent. Code changes; the specification is where the reasoning behind it is preserved.

## Numbering and naming

- `000-template.md` is the reusable template every new specification is copied from.
- Specifications are numbered sequentially (`001-`, `002-`, ...) in the order they were written, e.g. `001-platform-vision.md`.
- File names are short, lowercase, and hyphenated after the number.

## Owner Scheme Review extension

- [036 — Owner Scheme Review and Verified Corrections](036-owner-scheme-review-and-verified-corrections.md): agreed product scope, documentation-only draft; Stage 7 shared-evidence extension, not an additional Stage 4 gate. Depends on the versioned residential-count proposal [035 / PR #166](https://github.com/maxrose26/PropertyAIgent/pull/166) and sparse-observation contracts [033](033-verified-records-under-unknown-window-completeness.md) / [034 proposal, PR #164](https://github.com/maxrose26/PropertyAIgent/pull/164). Separate proposal links do not imply integration or implementation.

- [037 — Owner-accepted single-page window](037-owner-accepted-single-page-window.md): one named Oldham RECEIVED window accepted by explicit owner review; closed, default-off, labelled, never a rule for other windows; coverage never advances.
- [038 — Fixed Oldham read-only inspection](038-oldham-readonly-inspection.md): dormant, not authorised for execution; reports the installed Oldham function/privilege/control state read-only.

## What belongs here

Specifications for anything that changes what PropertyAIgent does or how it's structured - a new intelligence layer, a new data source, a change to the core data model, a new user-facing capability. Not every code change needs one (a bug fix or a small refactor doesn't), but anything that a future contributor would need context to understand the "why" of should have one.

## Intelligence rules reference

[The Intelligence Rules Index](../docs/INTELLIGENCE_RULES_INDEX.md) maps current domain contracts, implementation, consumers and meaningful tests. [The gap assessment](../docs/INTELLIGENCE_RULES_GAPS.md) prioritises at most three follow-on packages. This is an assessment, not a new policy or implementation authority; open specifications and production-verification limits are explicit.
