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

---

*The five principles below were added at the Product Vision & Roadmap Refresh (post–Opportunity Experience V2), formalising discipline the platform's own agentic-reasoning direction now depends on — see [PRODUCT_VISION.md](PRODUCT_VISION.md), "Evidence-First, Agent-Assisted, Human-Decided," and [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7.*

## Preserve Uncertainty

An uncertain or unresolved fact must never be silently converted into a false positive or a false negative by a later layer — including a future reasoning agent sitting on top of it.

*In practice:* Opportunity Experience V2's own product language exists specifically to prevent this collapse — `UNCERTAIN` planning activity renders as "Activity uncertain — requires review," never as "no planning activity"; unknown ownership renders as "not yet assessed," never as "available." A future Opportunity Analyst inherits this obligation unchanged: where it cannot resolve a genuine evidence gap, the correct output names the gap, never fills it with a plausible-sounding assumption.

## Opportunities Before Raw Records

The product should present itself around things worth investigating, not as a searchable database of underlying records the user has to interrogate to find one.

*In practice:* Opportunity Experience V2's Dashboard replaced seven technical signal-category sections ("Approaching lapse date," "Allocations without planning applications") with a single unified feed of real opportunities, each carrying its own reason and evidence — the signals became supporting tags on an opportunity, not the primary thing being browsed.

## No Opaque Scoring

A conclusion is never expressed as a number or ranking unless the platform can also show the defensible methodology behind it — a plausible-looking score with no inspectable basis is worse than no score at all.

*In practice:* `build_opportunity_signal` classifies an allocation into one of four named states (INVESTIGATE/MONITOR/LOWER_PRIORITY/INSUFFICIENT_EVIDENCE) with a real, cited reason for each — never a 0–100 opportunity score. The same discipline is a hard constraint on the future Opportunity Analyst and Buyer Analyst: see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7.

## Buyer Suitability Is Contextual, Not Universal

An opportunity's value is relative to who's asking — it should never be reduced to one universal ranking that pretends otherwise.

*In practice:* built — Buyer Profiles V1 and `app.policy.buyer_matching.assess_buyer_fit` (Gate 1, closed — see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)): an opportunity may legitimately be `STRONG_FIT` for one buyer profile and `NOT_SUITABLE` for another, and the platform shows that difference per buyer, never averaging it into one universal number. The same discipline governs the future Acquisition Agent and Acquisition Prioritisation (see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7): any future score belongs to a buyer × opportunity pair, never to the opportunity universally.

**Extended (Product Owner decision, post Gate 2B-0B investigation):** this principle is not limited to *scoring* an opportunity per buyer — **opportunity membership itself is buyer-relative.** The existing global signal detectors (long pending, recent permission, approaching lapse, undeveloped permission, strategic land) are useful, real, buyer-independent signals, but they must never be treated as the complete definition of what can be an acquisition opportunity for every buyer: a development matching none of the five detectors can still be exactly what one buyer's mandate is looking for. See [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md), "Buyer-Specific Opportunity Universes," for the architecture this now drives (Shared Candidate Signal Universe vs. Buyer Opportunity Universe).

## Unknown Must Remain Unknown

The absence of evidence must never be converted into positive evidence — for anything, in either direction.

*In practice:* this is the concrete, general form of "Preserve Uncertainty" above, restated for acquisition reasoning specifically: no construction evidence does not mean a site is available; no `parent_group` does not mean an entity is independent (Applicant Intelligence's own structural completeness gap makes this a real, present-day case, not a hypothetical — see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §2); no identified owner does not mean a site is unowned or uncontrolled; no known developer does not mean a site is available; no transaction evidence does not mean a site isn't being marketed; no evidence of a constraint does not mean the constraint is absent. Every one of these must render as an explicit `UNKNOWN` / `INSUFFICIENT EVIDENCE` state, never silently collapsed into whichever answer happens to be more convenient. This governs the future Acquisition Position Intelligence (Gate 2C) directly — see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md).

## Source Authority Is Not Claim Support

A source being authoritative in general does not mean every specific claim attributed to it is strongly evidenced — the two are separate questions, and conflating them lets an unsupported claim inherit a confidence it hasn't earned.

*In practice:* Applicant Intelligence's deterministic confidence ceiling reasons about evidence-*source-type* tier (e.g. a Companies House record is authoritative), not about whether a specific cited fact's *content* actually supports the specific claim made from it — production validation found one isolated case where a company's own registered SIC classification did not support the commercial role asserted from it, yet its source-type tier alone let a HIGH confidence through (see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §2). This is a general reconciliation-safety principle, not a one-off bug, and matters even more for Trusted Opportunity Data (Gate 2B, closed), which reconciles a similar mix of authoritative-but-not-always-conclusive planning sources — a decision notice being an authoritative document type does not, by itself, mean every figure a professional might read off it is the operative one; see Gate 2B-2C's own trusted operative-anchor resolution for a real, closed instance of exactly this discipline.

## Build Only Where Validated

A capability — especially an agentic one — is built because real evidence from real use shows it's needed, not because it's the most exciting thing to build next.

*In practice:* the Product Owner paused further implementation after Opportunity Experience V2 specifically to run Phase 1 Opportunity Validation — reviewing 10–15 genuine opportunities as a land professional would — before choosing the next workstream, rather than defaulting to whichever capability looks most appealing in the abstract. See [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md), "Current Validation Milestone."

## Development State Is a Neutral Fact, Not a Universal Buyer Recommendation

*(Added post Gate 2B-2C.)* A development/delivery state (e.g. `UNDERWAY`, `PARTIALLY_COMPLETE`, `COMPLETE`) is factual evidence about a scheme's progress. It must never itself encode a universal acquisition recommendation — the same state means different things to different buyers, and the platform must preserve that difference rather than average it away.

*In practice:* Gate 2B-2C's own trusted lapse/progress facts (`compute_lapse_status`, `compute_phase_progress`) return a neutral status string; today's land-oriented opportunity detectors (`_approaching_lapse_cards`, `_undeveloped_phase_cards`, `_recent_permission_cards`) each apply their *own* eligibility filter on top of that fact (e.g. excluding `underway` sites), which is correct for *those* detectors' own "is this undeveloped land" question — but is a detector-specific choice, not a property baked into the fact itself. A traditional housebuilder/land buyer may read `UNDERWAY` as "too late, already committed"; an investment fund, BTR investor, forward-funding or forward-purchase buyer may read the identical fact as "now more interesting" (schemes under construction, nearing completion, or completed-but-unsold stock); a Housing Association may read it as an opportunity to acquire affordable/S106 units or completed homes. A future fund/BTR-oriented detector must consume the same trusted fact, not a re-interpreted or re-labelled one — this is the same discipline as [Buyer Suitability Is Contextual, Not Universal](#buyer-suitability-is-contextual-not-universal), applied to development/delivery state specifically. Do not invent a `NEARING_COMPLETION` state ahead of reliable supporting evidence (condition-discharge sequence, commencement notices, building-control evidence, developer updates, sales/marketing evidence, EPC/address creation, completion notices) — see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md), "Explicit Architectural Deferrals."
