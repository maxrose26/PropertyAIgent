# PropertyAIgent — Design Principles

These are the rules every future feature follows, regardless of which capability in [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) it belongs to. They are not aspirational — each one is already load-bearing in the current codebase, and each entry below grounds the principle in a real, existing example so it stays a working discipline rather than a slogan. When a new feature's easiest implementation would violate one of these, the principle wins; see `CLAUDE.md`'s own instruction that specifications and principles take precedence over implementation convenience.

---

## Evidence First

Every fact the platform states should be traceable to a real source — a specific document, page, and (where AI was involved) model and prompt version — not asserted on its own authority.

*In practice:* every `VisualEvidence` row retains its source document, page number, file hash and render hash; every AI-extracted policy fact in `app/extraction/plan_evidence.py` carries a verbatim source excerpt alongside the extracted value.

## Never Invent

If a fact isn't genuinely present in a source, the platform records its absence rather than guessing or filling a gap with a plausible-sounding value.

*In practice:* `policy_reference` is nullable end-to-end in the Local Plan allocation model, and the extraction prompt explicitly forbids inventing a code where the source document doesn't print one. A page mentioning several allocation codes is never assigned to just one of them because that happens to be the only one already in the database — see [Deterministic Before AI](#deterministic-before-ai) below.

## Explainability

Every important decision the platform makes — a match, a status change, an AI summary — should be explainable after the fact: what evidence led to it, and by what method.

*In practice:* every `VisualEvidence` row stores `match_method` and `match_confidence` even when the match failed to resolve to an allocation, specifically so a reviewer can see *why* a page was left ambiguous rather than just that it was. AI Local Plan Summaries are generated only from a plan's own already-verified evidence, never from unattributed general knowledge.

## Human Review

Anything the platform is genuinely uncertain about is surfaced for a human decision, never silently resolved by best guess.

*In practice:* every AI-derived `VisualEvidence` row starts `review_status="needs_review"`; every ambiguous or status-changing policy fact is written as a `PolicyChangeEvent` proposal rather than mutating trusted state directly, resolved only by the two explicit functions `approve_change`/`reject_change`.

## Deterministic Before AI

Wherever a fact can be established by a deterministic method — regex, exact/normalised string comparison, rule-based classification — that method is used, and AI is reserved for genuinely judgement-requiring steps.

*In practice:* `app/visuals/matching.py`'s allocation-matching priority chain runs exact policy reference → normalised policy reference → exact allocation title → weaker substring suggestion → needs review, entirely without AI, *before* AI vision classification is even consulted for what an image shows. A page printing more than one distinct allocation code is never guessed at, even when only one of those codes happens to already exist in the database.

## AI Only Where Judgement Is Required

AI is used specifically for the narrow set of tasks that genuinely need interpretation or synthesis — never as a shortcut around building the deterministic method that should exist instead.

*In practice:* AI classifies what a rendered page *shows* (a fixed `IMAGE_TYPES` vocabulary), but never decides *which* Site or allocation that image belongs to — that step is always the deterministic matching chain above. This separation is deliberate and permanent, not a temporary limitation.

## Single Source of Truth

A fact is stored once, in the object it actually belongs to, and referenced everywhere else — never duplicated into a second place that can drift out of sync.

*In practice:* Places for Everyone, a single adopted plan spanning 9 councils, is represented as exactly one `LocalPlan` row linked to every participating council via an additive join table (`LocalPlanCouncil`) — never duplicated per authority. Two allocations that describe the same physical site are connected via an explicit `AllocationRelationship`, never merged or copied into one record.

## Monitoring Over Manual Updates

Evidence that can change over time is kept current through ongoing, automated monitoring, not one-off manual re-checks that quietly go stale.

*In practice:* `app.policy.monitor` re-checks every registered policy source and report on a cadence, gated so a scheduled run does near-zero work when nothing is actually due — and any detected change is queued for review, never applied silently.

## Commercial Usability

Every capability should ultimately serve a real business decision a target user is trying to make — not exist because it was interesting to build.

*In practice:* every intelligence layer in [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) is scoped against the question "does this help someone decide whether to pursue, promote, or invest in this Site" (see [PRODUCT_VISION.md](PRODUCT_VISION.md)) — a feature that doesn't answer a version of that question doesn't belong in the platform.

## Modular Architecture

Each capability is built as an independently reasoned-about layer with clear inputs, so it can be extended, re-onboarded to a new council, or rebuilt without destabilising the layers around it.

*In practice:* council-specific behaviour lives in config (`config/councils.yaml`, `config/policy_sources.yaml`), not in hardcoded per-council branches in application code — onboarding a new council or plan is a config change, not a code change, the same discipline `CLAUDE.md` states directly ("Do not hardcode council-specific behaviour unless absolutely necessary").

## Transparency

A user should always be able to ask "why does the platform believe this?" and get a real answer, down to the original evidence — not a black-box output presented as fact.

*In practice:* review status, source provenance, match method and confidence are first-class, always-populated fields throughout the schema, not optional metadata — this is what makes it possible for a human reviewer to audit any AI-assisted or automated conclusion the platform has produced.
