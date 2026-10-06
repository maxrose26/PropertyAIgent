# Stage 2.5B — Acquisition Subject Decomposition

Status key used throughout:

- **SPECIFICATION — NOT IMPLEMENTED.** This document is a design contract only. No code, schema,
  fingerprint, monitoring or production change exists for anything described here.
- **CURRENT BEHAVIOUR** — what master `ca2f323826ddaefdb2d1c9a0da34d148d8d64084` does today, verified
  by repository inspection.

Related: `024-stage2-5-buyer-discovery-and-opportunity-decomposition.md` (Stage 2.5A, accepted and
merged; contains the earlier "approved direction" note for this stage, which this specification
supersedes for design detail), `023-stage2-commercial-evidence.md` (evidence semantics).

> Numbering note: `023-` is used by two existing specifications. This is `025-`, the next unused number.

## Objective

Answer one product question from evidence PropertyAIgent already holds:

> Within the planning/development evidence we already know about, what economically distinct
> acquisition subjects could a buyer actually pursue?

A planning scheme must no longer automatically equal one acquisition opportunity. Where trusted
evidence supports it, a family of related acquisition subjects is shown and matched per buyer;
where it does not, the system says so and fails closed.

## Core concepts

**Planning subject** — the planning/evidence object: a site, application, phase, plot or allocation,
identified by existing ids. It exists whether or not anyone could buy anything.

**Acquisition subject** — an evidenced, economically meaningful scope that a buyer could potentially
pursue. One planning site may yield **zero, one or several**. An acquisition subject is **not** proof
of availability, ownership or control, transaction structure, willingness to sell, or parcel
geometry. It is a **read model** recomputed from evidence (like opportunities today), not a
persisted hierarchy.

**Family** — either a **planning family** (the acquisition subjects of one planning site) or a
**strategic family** (one strategic allocation, canonical and never duplicated). The two may cross-link
through existing evidenced links but are independently identified and monitored. Ranking and display
operate at family level.

**Evidence guardrails (inherited, unchanged):** planning status ≠ acquisition status; planning
capacity ≠ availability; Reserved Matters approval ≠ unavailable; developer/applicant identity ≠
ownership or control; residual planning capacity ≠ verified acquisition package; UNKNOWN ≠ zero;
commercial availability is never inferred from planning progression.

## Minimum evidence to create an acquisition subject

All required (otherwise no subject, never a guessed one):

1. a named planning scope resolved by the existing `_resolve_scopes` rules;
2. an exact (or explicitly approximate, and labelled as such) total-residential `CountAssessment` for
   **that scope** with a Gate 3 supporting source;
3. an operative planning position for that scope;
4. for any **child** subject, sourced containment in its parent (see Parent/child contract).

## Taxonomy (APPROVED)

| Kind | Status | Meaning | Identity source | Notes |
|---|---|---|---|---|
| `WHOLE_SITE` | exists today | the scheme as one pursuit | `planning_delivery:site\|long_pending_application\|recent_permission:{site_id}` (one lifecycle slot per site) | unchanged |
| `PHASE` | exists today | an evidenced named phase | `planning_delivery:phase:{site_id}:{phase_code}` | unchanged; an RM scope **is** a PHASE where it carries a named scope. **No separate RM_PARCEL kind** |
| `STRATEGIC_PARENT` | exists today | an allocation as a whole | `strategic_land:allocation:{allocation_id}` | unchanged |
| `MIXED_COMPONENT` | new, conditional | an independently evidenced component (e.g. the conventional or the retirement element) of a mixed parent | new id shape (see Identity) | created **only** where an independent component scope is evidenced; never inferred from a development-type string |
| `AFFORDABLE_PACKAGE` | **identity contract only** | the affordable component as a package | new id shape | **production creation disabled** until Stage 2.6 produces qualified affordable evidence |

**`RESIDUAL_CAPACITY` is NOT an acquisition-subject kind.** Arithmetic residual planning capacity
does not prove that an economically or spatially identifiable acquisition parcel exists. It is an
**evidence/intelligence proposition** attached to the relevant parent/family (see Residual
capacity). A future residual acquisition subject may be created only where additional evidence
establishes an identifiable acquisition scope; that is outside this specification. There is no
"available units" subject or terminology anywhere.

Rejected kinds: parcel-by-geometry (no geometry evidence), sub-phase (no stable identity),
RM_PARCEL (duplicates PHASE), any "available"/"unbuilt" kind.

## Identity (CURRENT BEHAVIOUR → REQUIRED GRAMMAR)

### Current opportunity-id shapes (unchanged by this specification)

| Shape | Example |
|---|---|
| `strategic_land:allocation:{allocation_id}` | `strategic_land:allocation:213` |
| `planning_delivery:site:{site_id}` | `planning_delivery:site:526` |
| `planning_delivery:long_pending_application:{site_id}` | `planning_delivery:long_pending_application:61` |
| `planning_delivery:recent_permission:{site_id}` | `planning_delivery:recent_permission:460` |
| `planning_delivery:phase:{site_id}:{phase_code}` | `planning_delivery:phase:281:1` |

`phase_code` is free text from phase tracking (the unphased bucket is `Whole site / unphased`,
containing spaces and `/`). It is **not** guaranteed delimiter-safe.

**Existing opportunity ids MUST remain byte-for-byte unchanged.**

### Required grammar for new subject kinds

- Every new kind uses an **explicit kind segment**: `planning_delivery:{kind}:{site_id}:{scope_key}`
  with `kind ∈ {component, affordable_package}` (kind names ≤ 50 characters; whole id ≤ 200).
  **Mapping:** kind segment `component` ↔ `MIXED_COMPONENT`; `affordable_package` ↔ `AFFORDABLE_PACKAGE`.
  The kind segment is also what existing columns persist (`AgentEvaluationHistory.opportunity_kind`,
  `CurrentBuyerOpportunityState.current_opportunity_kind`), so the persisted kind vocabulary gains these two
  values; consumers of those columns must tolerate them (see inventory #10 and the evaluation contract).
- `scope_key` MUST be delimiter-safe: characters `[A-Za-z0-9._~%-]`, **never** `:`, whitespace or `/`.
  Any free-text source (phase code, component label) is encoded by RFC 3986 percent-encoding of its UTF-8
  bytes, which is deterministic and reversible. Percent-encoding can inflate text up to 3×, so the
  **length is capped, and the cap is part of the contract**: the *anchor* scope key (reserved prefix
  included) MUST be ≤ **100** characters (the `AcquisitionSubjectAnchor.scope_key` column is
  `String(100)`), and the whole opportunity id ≤ 200. **If the encoded key would exceed the cap, no
  subject is created (fail closed); the specification does not authorise a schema change to widen it.**
- Identity is derivable from evidence ids alone, with no hidden state.
- **Anchor keys** (`AcquisitionSubjectAnchor`: `(subject_type, anchor_id, scope_key)`, `scope_key`
  `String(100)`): existing keys are unchanged (`WHOLE_SITE`, `WHOLE_ALLOCATION`, the verbatim phase code).
  New kinds use a reserved, namespaced scope key (`component~{encoded}` / `affordable~{encoded}`; the
  prefix counts toward the 100-character cap). G1 MUST add a fail-closed collision guard: a legacy phase code that begins
  with a reserved prefix is rejected, never merged. (Production data is not read in this
  specification; G1 proves the guard against repository fixtures and captured evidence.)
- **Strict parser.** A single parser, `parse_opportunity_id(id) → (kind, anchor_id, scope_key|None)`:
  known kinds only, digit-only ids, and **per-kind segment rules**: the three site-lifecycle kinds and
  `strategic_land:allocation` have exactly three segments; **a legacy `phase` id is parsed as
  `id.split(":", 3)` — everything after the third `:` is the phase code verbatim**, so legacy phase codes
  containing `:`, spaces or `/` (e.g. `Whole site / unphased`) parse correctly and are never rejected or
  truncated *by the parser*; only the new kinds (`component`, `affordable_package`) require exactly four
  segments and a delimiter-safe key. **Legacy anchor compatibility:** today's resolver takes `parts[3]`
  (the text up to the next `:`), so a phase id whose code contains `:` already anchors to a *truncated*
  key. Because existing history and current-state rows are keyed by those anchors, **G1 MUST preserve the
  existing resolver's anchor result byte-for-byte for every existing id** (the parser exposes the full
  remainder; a separate legacy-anchor function reproduces today's truncating result). Whether any phase
  code containing `:` (or longer than 100 characters, which the cap below does not retroactively cover)
  actually exists is **unknown to this specification** (no production read is authorised); if any does, the
  possible anchor collision/truncation is a pre-existing latent defect whose correction needs its own
  migration decision, not a silent change inside G1.) **An unknown kind, malformed id or
  ambiguous scope key raises; it MUST NEVER default to `WHOLE_SITE`** (current
  `resolve_acquisition_subject_key` does exactly that for any non-phase, non-strategic kind — see the
  inventory below).

### Fail-closed delivery schedule and emission gate

"Unknown kinds fail closed" is delivered **consumer by consumer**, not by one change. G1 delivers it for
the persistence resolver (#1, #2). Other consumers also accept any `parts[1]` today — notably
`build_b2_context` (#3), which treats any non-`site`, non-`phase` kind as a `recent_permission`-style
branch with `development_state_scope_verified=False`, and the packet builder (#4) and applicant
intelligence (#6). **Hard rule (emission gate): no new subject kind may be emitted into the opportunity
universe, a feed, monitoring or evaluation until every consumer in the inventory that parses ids has been
migrated to the strict parser or explicitly proven compatible, and G1A has landed.** Each consumer's
migration is owned by the gate named in its inventory row.

### Inventory of current opportunity-id consumers (repository inspection)

| # | Consumer | Current assumption | Compatibility requirement before any new kind ships |
|---|---|---|---|
| 1 | `app/policy/agent_evaluation_persistence.py` `resolve_acquisition_subject_key` (L117–144) | `parts[1]` is kind, `int(parts[2])` is anchor; phase → `parts[3]`; **anything else → WHOLE_SITE** | **Fail-open today.** Must use the strict parser; unknown kinds raise. A mis-anchored child would share the parent's evaluation history. |
| 2 | same file, `_opportunity_kind` (L191) | `split(":")[1]` | Use the parser's kind. |
| 3 | `app/policy/buyer_matching_b2_context.py` `build_b2_context` (L176–196) | kind, `int(parts[2])`, phase code `parts[3]`; branches on `kind == "site"` / phase; **any other kind falls into the scope-unverified branch (L193–195)** | Explicit handling for each new kind; unknown kind → no context (fail closed). Owned by G4. Also called per universe record from `buyer_profile_store.py` (L592, L718). |
| 4 | `app/reporting/opportunity_intelligence_packet.py` (L218–221) | `parts[1]`, `int(parts[2])`, `parts[3]` only as phase code | Parser-based; new kinds must supply subject-scoped packet facts. |
| 5 | `app/pipeline/status_verification.py` `build_opportunity_kinds_by_site` (L341+; parse L359–363) | kind `parts[1]` by site for verification prioritisation | New kinds excluded or mapped explicitly; must not change which sites are verified. `app/pipeline/run_weekly.py` (L102, L626, L705, L2635+) uses the per-site kinds map **as a truthiness check** (L725), so any new-kind id would change that set. **A test proving the verified-site set is unchanged is a G6/G7 acceptance condition.** |
| 6 | `app/reporting/applicant_intelligence.py` (L421–429) | `candidate_kind_by_site` from `parts[1]`, `parts[2]` digit | Parser-based; new kinds must not displace site-level candidate kinds. |
| 7 | `app/reporting/opportunity_change.py` `_opportunity_kind_prefix` (L177–188) | `opportunity_id.rsplit(":", 1)[0]` | **See G1A.** Not an acceptable foundation for new kinds. |
| 8 | `app/reporting/opportunity_universe.py` (constructors L202–222; phase code from card id L478) | five constructors; phase code from `card["id"].rsplit("-", 1)[-1]` | New constructors only for new kinds; legacy constructors untouched. |
| 8a | `app/reporting/dashboard.py` (L1206) — the **producer** of the card id `opp-phase-{site.id}-{scope_key}` that #8 re-parses | the phase code is the text after the last `-` | A phase code containing `-` is already ambiguous/truncated here. Because existing ids must stay byte-for-byte unchanged, **this legacy limitation is recorded and accepted unless G1A decides otherwise**; it is not fixed by G1. |
| 9 | `app/reporting/opportunity_monitoring_transition.py` and `scripts/gate2b2b2_monitoring_transition.py` | ids treated as opaque strings; the script hard-codes phase ids including `Whole site / unphased` | Compatible (opaque); new-kind manifests built by a reviewed tool (see Monitoring). |
| 10 | `app/db/models.py`: `OpportunityMonitoringState.opportunity_id` `String(200)` unique; `AgentEvaluationHistory.opportunity_id` `String(200)` and `opportunity_kind` `String(50)`; `CurrentBuyerOpportunityState.current_opportunity_kind` `String(50)` | length limits | New ids ≤ 200, kind names ≤ 50. No schema change. |
| 11 | `app/policy/acquisition_evaluate.py`, `agent_evaluation_prompt.py`, `agent_evaluation_result.py` | id is an opaque key/label; anchor derived through #1 | Compatible once #1 is strict. |
| 12 | `app/reporting/opportunity_transaction_signals.py` (L248–301) | looks up `OpportunityMonitoringState` by id for "ownership/control evidence changed" | A new subject has no monitoring row yet: signal must be UNKNOWN/ABSENT, never "changed". |
| 13 | `app/reporting/opportunity_feed.py` | builds/attaches facts per card | Becomes family-aware only in G3b (G3a is a pure model with no feed integration). |
| 14 | `benchmark/extraction.py`, `benchmark/benchmark_case.py`, `scripts/run_agent_evaluation_benchmark.py` | id is a provenance label; extraction looks the id up in the live universe | Compatible; new kinds only resolvable if they exist in the universe. |
| 15 | `app/reporting/residual_capacity.py` `_parse_subject` (L148–155) | a **different grammar**: the `CountAssessment.subject_id` `site:{site_id}:{scope_type}:{scope_label}`, parsed with `split(":", 3)`; the label may contain `:` | Not an opportunity id. It matters because **parent identity in this specification is defined as the specific parent `CountAssessment` (its `subject_id`)**. The mapping from an opportunity/subject id to the parent `CountAssessment.subject_id` is a **G2 deliverable** and must be unambiguous before any child relationship is created. |

(No `app/ui` module parses opportunity ids; confirmed by repository search. Any further consumer found
during implementation MUST be added here before the change ships.)

## Parent / child contract

Every child subject MUST carry: **planning site; subject kind; scope key; parent subject identity
(the specific evidenced parent `CountAssessment`/planning scope, not merely "the site"); supporting
source application reference(s); evidence basis.**

- A child requires **sourced containment evidence** (an explicit, provenance-carrying statement that
  the child scope is contained in the named parent scope). It is **never** inferred from a smaller
  unit count, a newer date, Reserved Matters status alone, address similarity or phase-like wording
  alone.
- Where several outlines or phases exist, the parent is the specific evidenced parent scope. **If
  parent identity cannot be established, no child relationship is created** (the scope is displayed,
  if it qualifies at all, as an unrelated subject).
- The parent link is recomputed on every build; it is not persisted. Existing `AcquisitionSubjectAnchor`
  carries identity only (no schema change planned).

## Overlap contract

- All sibling subjects are **potentially overlapping by default**. Unit counts are **never summed**
  across subjects unless explicit, sourced non-overlap evidence exists for every pair
  (existing `evidenced_pairs` rule shared with phase aggregation and residual arithmetic).
- Missing or ambiguous evidence → no sibling aggregation; subjects display as related, not additive.
- The family presentation MUST be able to say: **"Related subjects may overlap — do not add unit
  counts."**
- Overlap discovered later changes the related-subject fingerprint field of both subjects (see
  Monitoring); it never silently rewrites counts.

## Residual planning capacity (evidence proposition, not a subject)

`assess_residual_planning_capacity` remains the evidence primitive. Its outcomes map to:

| Outcome | Meaning | Presentation |
|---|---|---|
| `RESOLVED` | exact compatible counts, operative parent, explicit containment, pairwise non-overlap, evidenced-complete child set | "**Supported residual planning capacity: N homes**" |
| APPROXIMATE / INVESTIGATE | parent or a contained child is approximate | no integer; "residual capacity may exist — verify", only if containment is evidenced |
| UNKNOWN / `MATERIAL_CONFLICT` | any gate unmet, or conflicting evidence | nothing, or a stated conflict |

`RESOLVED` is **not** automatically converted into an acquisition subject. "Supported residual
planning capacity" means **arithmetic capacity only** and explicitly does **not** imply availability,
parcel identity, ownership, control, saleability or spatial location. Production residual reasoning
remains fail-closed wherever containment, non-overlap or child-set-completeness evidence is absent
(which is every production site today). Stage 2.5B does **not** require an evidence producer merely
to make residual results appear; Stage 2.6 may later improve the qualified evidence needed.

## Mixed specialist parents

- Matching policy **v7 is NOT authorised by this specification** and `BUYER_MATCHING_POLICY_VERSION`
  stays 6. Subject-level decomposition comes first.
- Where **independently evidenced** child/component scopes exist, each subject is matched
  independently using its own subject-specific development type (retirement child → assessed as
  retirement; conventional child → assessed as conventional housing). Specialist exclusions are not
  weakened globally.
- For a mixed parent with **no** evidenced child/component scope, the semantic question is recorded,
  not decided here. A possible future outcome is `INSUFFICIENT_EVIDENCE` / investigate instead of
  `NOT_SUITABLE`. **The decision is made at the post-G4 product-policy gate** (see Implementation
  gates), after subject-level matching exists; only then is it determined whether v7 is required.
- Until then the temporary Nesten limitation stays pinned by
  `test_mixed_specialist_parent_remains_excluded_pending_stage_2_5b_decomposition`, which must be
  updated (not deleted) when behaviour changes.
- **Rejected premature approaches (recorded):** buyer-name hard-coding; a Nesten-only special case;
  unnecessary schema added solely to work around decomposition.
- Fact verified for the record: `is_specialist_development` is computed per opportunity from
  `SPECIALIST_DEVELOPMENT_TYPES` (which contains both mixed types), so the fact is buyer-independent
  and only `specialist_development_is_exclusion` differs per buyer; any change at fact level is a
  global matching-semantics change.

## Affordable package

Identity and relationship contract only. A package is a child of its parent scope and overlaps the
parent's other subjects by default. **Production creation remains disabled until Stage 2.6 produces
qualified affordable-housing evidence**; Stage 2.5B adds no AH extraction, percentage derivation,
tenure inference or S106 interpretation. Acceptance uses injected qualified evidence only, mirroring
how `derive_whole_site_affordable_state` is tested.

## Subject-level matching

- Buyer matching evaluates **the subject's own evidence**. A **dedicated subject facts builder** is
  required; current parent/site `MatchingFacts` builders must not be assumed reusable (they hard-code
  fields such as `has_phasing_evidence` and `matched_to_site` and read unit counts from
  representative scheme intelligence).
- Subject-specific facts, where evidenced: count assessment, development type, planning position,
  specialist state, affordable scope, phase/scope identity.
- **Parent evidence may be inherited only as explicitly labelled CONTEXT**; it must not silently
  become subject-specific evidence.
- Examples: Nesten vs a 125-home conventional phase → assess 125; a strategic land buyer vs the
  strategic parent regardless of children; Housing Association vs a qualified package (when enabled)
  → assess the affordable quantum.

## Family feed contract (APPROVED)

**One opportunity-family row per planning site/family**, buyer-specific:

- **Best subject** for the buyer is selected deterministically; related subjects are listed beneath
  (whole site, other evidenced phases, components, affordable package when enabled).
- **Residual planning capacity** is shown as intelligence in the family, never as a subject.
- **Ranking operates at family level.** A parent and child never count as two independent top-level
  opportunities. Strategic and planning families coexist and may cross-link (see the decided
  strategic-family rule below); a strategic allocation is never a subject duplicated into each linked
  site's family.
- **Deterministic representative-subject order (Product Owner Decision 4)** — each step breaks ties of the previous:
  1. **buyer fit**, highest first: `STRONG_FIT` > `POSSIBLE_FIT` > `INSUFFICIENT_EVIDENCE` **with** the investigative
     exception (`BuyerFitAssessment.is_investigative_exception`) > `INSUFFICIENT_EVIDENCE` **without** it > `NOT_SUITABLE`;
  2. **count evidence quality**: `EXACT` > `APPROXIMATE` (including a bounded `RANGE`) > `UNKNOWN`;
  3. **commercial specificity**: ONLY where an **evidence-qualified relationship** exists (G2) may a more-specific child outrank its
     parent when the preceding dimensions tie. G3a has no G2 relationships, so G3a MUST NOT invent parent/child specificity and
     this step has no effect there; **no fixed subject-kind rank is used**;
  4. a **stable deterministic key**, final tie-break only, with no commercial meaning (G3a: the subject's own canonical
     identity string — the opportunity id, or the feed card id for feed subjects).
  (Cross-family ordering, where fit buckets tie, is simply the family key; no new commercial scoring model.)
- **Representative is not the only opportunity (Decision 5).** The representative is the headline subject for this buyer; every
  other non-`NOT_SUITABLE` subject of the family stays available as a related subject, and subjects sharing `STRONG_FIT` /
  `POSSIBLE_FIT` with the representative are surfaced as "also STRONG_FIT" / "also POSSIBLE_FIT". A parent is never hidden because a
  child won a tie, nor a child because a parent did.
- Display per subject: kind, units with precision, relationship to parent ("contained in …"),
  evidence confidence, buyer fit, investigation requirements, and the overlap notice above.
- **DECIDED (Product Owner): strategic families are canonical and distinct from planning families.**
  A strategic allocation has **ONE canonical strategic family**. It is **not** duplicated as a related
  acquisition subject inside every linked planning-site family.

  ```
  STRATEGIC FAMILY               PLANNING FAMILY
  Allocation A                   Site X
    relationships:                 subjects:
      → matched planning Site X      → whole site
      → matched planning Site Y      → evidenced phases / components
  ```

  The two kinds of family **may cross-link** through the existing evidenced allocation–site links, but
  they remain **independently identifiable and independently monitored**. The same strategic allocation
  must never become multiple top-level opportunities merely because it links to several planning sites.
  The strategic family's canonical identity is the existing `strategic_land:allocation:{allocation_id}`
  (unchanged; no per-site copies); a planning family shows the link as a labelled cross-reference, not as
  one of its own subjects. An allocation with no linked site is simply a one-subject strategic family.

No UI is implemented by this specification.

### Opportunity-family decisions (Product Owner; G3a/G3b)

1. **A family is a grouping/read-model concept, not an acquisition subject.** It does not imply a whole-site opportunity exists; a
   phase-only site is a valid family (e.g. Site X with Phase 1 and Phase 2) with **no** whole-site subject, and none is synthesised.
2. **Planning family identity = (`planning_delivery`, `site_id`).** Grouping does **not** establish containment or non-overlap.
   Lifecycle representations stay subject to the existing detector precedence (at most one of lapse/recent-permission/long-pending
   per site); phase subjects may coexist with a lifecycle subject where one genuinely exists. If conflicting lifecycle
   representations are ever supplied, G3a fails closed rather than choosing one.
3. **Strategic family identity = (`strategic_land`, `allocation_id`).** One allocation id is one strategic family; multiple
   relationship rows or linked planning sites never duplicate it. Planning and strategic families stay separate identities and may later
   cross-link; they are not merged in G3a.
4. **Representative order** as above (fit, evidence quality, relationship-qualified specificity, stable key).
5. **Representative ≠ only opportunity** (also-STRONG / also-POSSIBLE; nothing hidden).
6. **Family `NOT_SUITABLE` only if every buyer-relevant subject is `NOT_SUITABLE`**; any STRONG/POSSIBLE/INSUFFICIENT subject means the
   family is not terminally excluded. G3a may compute this pure state; live dashboard/feed count semantics are **not** altered until G3b.
7. **No unit summation.** G3a never calculates or displays a family unit total; same-site subjects may overlap, and without G2 non-overlap
   evidence they are never summed. The model exposes an overlap-safety state sufficient for the wording
   "Related subjects may overlap — do not add unit counts."
8. **Complete-family requirement.** Final buyer-facing families must be built from the **complete** relevant subject set; a bounded
   candidate pool can omit a better subject and so choose the wrong representative. G3a is pure and operates on whatever complete iterable
   it is given. **G3b hard acceptance requirement:** build families from an unbounded/complete relevant subject source, or *prove* the bounded
   optimisation cannot omit a member capable of changing the best subject, family fit, the also-STRONG/POSSIBLE list or the family
   exclusion state. An "incomplete family" warning is not an acceptable final substitute.
9. **Phase-only sites** remain valid families; the family header may use site-level contextual metadata, which does not create a whole-site
   subject.
10. **Identity-system and ordering notes (G3a).** One grouping invocation must use **one canonical subject-id representation** — all
    opportunity-universe ids **or** all feed-card ids, never a mixture; a mixture **fails closed** (it would otherwise double-list one
    subject under two keys). The final **stable-key tie-break is lexical/string order** (so `…A10` sorts before `…A9`): deterministic only,
    with no commercial meaning. A feed phase card's id-encoded scope must **agree** with its `phase_code`, and feed-card numeric ids must be
    canonical (`opp-lapse-3`, not `opp-lapse-03`); disagreement or non-canonical ids fail closed. The canonical opportunity-universe id grammar is unchanged.
11. **G2 is deferred.** G3a implements no containment, no "pursuant to outline application" phrase support, no RM → VAR → OUT chains and
    makes no `CONTAINED_IN` claim.

## Monitoring identity

- Existing ids and the monitoring rows keyed by them are unchanged. New subjects use the grammar above.
- **Stable ids**: derived from evidence ids only (no counters, no timestamps).
- **New software-created subject kinds at deployment must baseline as existing** through the
  controlled transition (`replacement_ids`, reviewed manifest, dry run first) and must **not**
  generate false NEW events. This depends on G1A and the carried-forward pre-production transition
  tooling (before/after fingerprint diff builder, field-level guard, standalone mandate
  re-onboarding, dry-run ordinary monitoring sync).
- A subject appearing through **genuinely new evidence** after baselining is a real NEW. **This holds only
  once G1A has landed:** under the current `rsplit` rule a new-shape id such as
  `planning_delivery:component:{site}:{key}` has the per-site prefix `planning_delivery:component:{site}`,
  so the first component at any site would be classified `BASELINE_EXISTING`, not `NEW` — the same latent
  gap as phases today. **Therefore G6, G7 and G8 (and any emission of a new kind) depend on G1A.**
- **Fingerprint ownership:** a subject's fingerprint covers its own facts plus parent scope key,
  evidence tier and related-subject set; a parent change changes a child fingerprint only through
  those explicit fields.
- **Overlap discovered later:** both subjects' related-subject field changes with a stated reason.
- **Retirement/replacement:** a subject that stops being evidenced is retired using the existing
  retired/replacement manifest categories; its history is not rewritten.

### G1A — Opportunity Kind / Monitoring Identity Normalisation (dedicated gate)

**IMPLEMENTATION OUTCOME (G1A, Option B — canonical domain+kind detector identity):**
`opportunity_detector_identity(id)` returns `{domain}:{kind}` (the four three-segment shapes are identical to the
old prefix; phase ids now map to `planning_delivery:phase` instead of `planning_delivery:phase:{site}`). It is shared
by the tracked-detector set and by the classification of universe records, and the classification decision is a pure
seam, `plan_opportunity_changes`, reusable by the future G1B dry-run. An existing persisted row that cannot be parsed
falls back, explicitly, to the legacy prefix (and a non-string row is skipped); a CURRENT universe id that cannot be
parsed raises before any monitoring state is written. The old `_opportunity_kind_prefix` helper has been removed (the
text below describes the behaviour that existed when this specification was written). No schema, fingerprint, id,
anchor or version change.

**CURRENT BEHAVIOUR WHEN THIS SPECIFICATION WAS WRITTEN (verified):** `_opportunity_kind_prefix(id) = id.rsplit(":", 1)[0]` and
`sync_opportunity_monitoring_state` treats an opportunity as part of a **detector baseline run** when
its prefix is not among the prefixes already tracked.

| Shape | Prefix produced | Granularity |
|---|---|---|
| `strategic_land:allocation:{id}` | `strategic_land:allocation` | per kind |
| `planning_delivery:site:{id}` | `planning_delivery:site` | per kind |
| `planning_delivery:long_pending_application:{id}` | `planning_delivery:long_pending_application` | per kind |
| `planning_delivery:recent_permission:{id}` | `planning_delivery:recent_permission` | per kind |
| `planning_delivery:phase:{site}:{code}` | `planning_delivery:phase:{site}` | **per site**, not per kind (and a phase code containing `:` shifts it further) |

The code's own documentation describes the intent as per-kind ("`planning_delivery:phase`…").
Consequently, for phases, a phase appearing at a site with no previously tracked phase is currently
treated as part of a baseline run (classified `BASELINE_EXISTING`, not `NEW`). This is a latent
discovery gap; it is documented here, **not** fixed in G0.

G1A MUST: (1) define the canonical opportunity-kind/detector identity (a parser-derived kind, not a
string prefix); (2) specify backwards compatibility for every shape above, **including phase ids whose
code contains `:`, spaces or `/` (if any exist; the specification does not assume they do), and the card-id
`-` ambiguity (inventory #8a)**; (3) state explicitly that
correcting phase granularity **changes baselining semantics**; (4) define the transition (existing
tracked ids must keep their rows; untracked-but-live phase ids must be baselined by reviewed manifest
**before** the corrected rule runs, otherwise a first sync after the change would report them NEW);
(5) prove by test that no existing opportunity can become falsely NEW. **G1A is not hidden inside G1
and needs separate approval.**

## Agent-evaluation contract

- Each acquisition subject gets its **own anchor/evaluation identity** (`subject_type`, `anchor_id`,
  new namespaced `scope_key`); history and current-state rows already key on `subject_anchor_id`, so a
  correct anchor prevents leakage by construction. **A parent evaluation is never copied to a child.**
- Parent planning history and site-level evidence may be provided as **labelled context**.
  **Subject-specific (must be recomputed):** count, fit, development type, affordable scope, next
  action.
- **Verified current facts:** `compute_agent_evaluation_input_fingerprint`
  (`agent_evaluation_persistence.py`, `AGENT_EVALUATION_INPUT_FINGERPRINT_VERSION` currently 2)
  hashes the mandate fingerprint, acquisition type, the deterministic buyer-fit assessment, the
  packet's commercially material facts, linked strategic allocation id, transaction-signal states and
  designated policy versions. The subject anchor is part of the history key, not of this payload.
- **UNRESOLVED until implementation verifies it:** whether subject-level packets/fit change the
  semantic payload. If the payload's meaning changes, the appropriate fingerprint-version decision is
  required (and is a REVIEW decision, not assumed).
- The persisted `opportunity_kind` columns gain the kind segments `component` and `affordable_package`
  (see the identity mapping); consumers of those columns must tolerate them. No model calls are made by
  any gate in this specification.

## Implementation gates (each separately approved; none is authorised by this document)

Dependency order: **G1 → G1A → G3a → G2 → G3b → G4 → post-G4 decision → G5 → G6 → G7 → G8** (G3a is implemented before G2; G3b does not depend on G2, which only enriches the relationship line), with **G1B** (below) a
deferred monitoring-tooling gate and the **Option C decision** a hard gate before first real emission. Any boundary change
needs a specification amendment first. Every gate lists objective, boundary, likely files, tests,
acceptance and stop conditions.

### G1 — Strict acquisition-subject identity grammar/parser (pure identity work only)
- **Objective:** the delimiter-safe grammar, `parse_opportunity_id`, anchor-key grammar with the 100-character cap, and the collision guard.
- **Boundary:** identity only. `resolve_acquisition_subject_key` becomes strict **for unknown/malformed
  ids while returning exactly today's anchor key for every existing id** (including today's truncation of a
  phase code containing `:`). No subject emitted, no consumer behaviour change for existing ids, no feed
  change, no schema.
- **Likely files:** `app/policy/agent_evaluation_persistence.py`, new `app/reporting/acquisition_subjects.py` (identity only), tests.
- **Tests:** round-trip for every grammar shape; the five legacy shapes unchanged byte-for-byte, **and the legacy anchor key for existing ids identical to the current resolver's output** (including `Whole site / unphased` and a code containing `:`, pinning today's truncation); unknown kind / malformed id / delimiter in a new-kind `scope_key` / reserved-prefix collision / over-length key all raise; encoding reversible; id and kind lengths within column limits.
- **Acceptance:** no schema; existing ids and anchors unchanged; nothing falls through to `WHOLE_SITE`.
- **Stop:** any change to an existing id, anchor or consumer result.

### G1A — Opportunity Kind / Monitoring Identity Normalisation (separate approval)
- **Objective:** a canonical, parser-derived opportunity-kind/detector identity replacing `rsplit(":", 1)[0]`, with the transition required if phase granularity changes.
- **Boundary:** `_opportunity_kind_prefix` and baselining only. No new subject kinds. No change to ids.
- **Likely files:** `app/reporting/opportunity_change.py`, `app/reporting/opportunity_monitoring_transition.py` (manifest use only), tests.
- **Tests:** current prefix behaviour pinned for all five shapes (including phase ids with `:`); the corrected rule; **no existing tracked or live opportunity can become falsely NEW**; untracked-but-live phase ids baselined by reviewed manifest before the corrected rule runs.
- **Acceptance:** documented before/after semantics; dry-run transition report; fingerprint unchanged.
- **Stop:** any path by which an existing opportunity could become NEW, or an unreviewed baselining-semantics change.

### G1B — Monitoring Baseline Impact / Dry-Run Tooling (FUTURE; not authorised)
- **Objective:** a read-only preview of what the ordinary monitoring sync would do, so a release can be reviewed before it runs.
- **Boundary:** MUST reuse `plan_opportunity_changes` (the same pure classifier as the real sync, so preview and execution cannot drift);
  **performs no writes in dry-run mode**; reports live untracked ids **by canonical detector**; previews `BASELINE_EXISTING` vs `NEW`;
  **previews the one-off phase `NEW` wave caused by G1A** (phases at sites with no phase rows, formerly baselined per site); supports construction
  of a reviewed transition manifest; enforces the rule that **a detector manifest covers ALL untracked live ids for that detector, or NONE**
  (any partial pre-created row activates the whole detector and turns the rest `NEW`).
- **Production reads:** any production read for G1B requires separate Product Owner authority.
- **Likely files:** a new read-only reporting module/script reusing `app/reporting/opportunity_change.py`, tests.
- **Stop:** any write in dry-run mode, a re-implementation of the classifier, or a production read without authority.
- **Status:** monitoring infrastructure is **paused**; G1B is deliberately not started.

### Option C — pre-emission decision gate (HARD GATE; not a gate to implement now)
Before the **first real emission** of `MIXED_COMPONENT` or `AFFORDABLE_PACKAGE`, REVIEW must explicitly decide whether
(a) the bounded **zero-subject false-baseline edge** is acceptable (a detector baselined with zero subjects makes its first genuinely later
subject read `BASELINE_EXISTING`; bounded to one subject per kind) or (b) **persisted detector activation/version state** is commercially
necessary. No schema is introduced now.

### Failure mode 7 — monitoring id vs acquisition-subject anchor (UNRESOLVED; separate future decision)
Monitoring is keyed by **opportunity id** while agent evaluation is keyed by the **acquisition-subject anchor**. A lifecycle change
(`site` ↔ `recent_permission` ↔ `long_pending_application`) therefore creates a new monitoring id while retaining the same underlying anchor.
This is **not** solved by G1A and must be recorded and decided separately; no gate in this specification resolves it.

### G2 — Evidence relationship contract (v1: evidence-qualified `CONTAINED_IN` only)

**Principle (Product Owner):** derive only **evidence-qualified** relationships between already-known subjects. G2 prefers **NO RELATIONSHIP**
over a **plausible but unproven** one. No schema, no persistence, no production read.

**`CONTAINED_IN`** means: the available evidence establishes that the child planning scope is pursued **pursuant to** the identified parent
permission/count scope. It does **not** establish ownership, availability, transaction structure, **non-overlap with sibling subjects**,
completeness of child phases, residual capacity, or parcel geometry.

**Qualified direct-parent rule (all must hold, otherwise no relationship):**
1. the child is a `phase` `CountAssessment` scope;
2. a supporting source application of the child is **reserved matters** (the existing `resolve_planning_role`);
3. that application's proposal contains **exactly one distinct qualifying parent citation** (all qualifying citations are scanned; see below);
4. the citation is a **full formatted planning reference** that **exactly equals** the reference of an existing application on the **same council
   and site** (no fuzzy matching; no inferred prefixes or year components);
5. that cited application is a **supporting source of the selected parent `CountAssessment`**;
6. the parent `CountAssessment` is **EXACT**, **operative/consented**, **`whole_site`** scope and a compatible residential metric
   (`total_residential`, for child and parent);
7. exactly one parent `CountAssessment` qualifies (several qualifying parents → no relationship).

**Phrase scanner (dedicated, reviewed; NOT `extract_parent_reference`'s first-match behaviour):** it inspects ALL matches in the text. A citation
qualifies only through one of these semantic phrases followed by a formatted reference: "pursuant to … permission <ref>", "pursuant to … approval
<ref>", "following … approval <ref>", and (explicitly authorised, because captured evidence shows this wording exists) "pursuant to outline
application <ref>" (and the hybrid equivalent). The phrase alone is **never** sufficient: every gate above still applies. Normalisation is minimal
and documented: trim whitespace and trailing punctuation only; the comparison with an existing reference is **exact and case-sensitive**.

**Rejected / deferred (not qualified containment):** bare numeric citations; "relating to"; "in association with"; variation, non-material
amendment and discharge-of-condition children (they are not reserved matters); a smaller unit count; a later date; reserved-matters status by
itself; a similar address; the same site; phase wording; counts that happen to add up. **No multi-hop chains** (RM → VAR → OUT or any other): the
child must directly cite the qualifying parent, and a variation may be that direct parent only if it **independently** satisfies the parent
`CountAssessment` requirements; G2 never traverses from it to another permission.

**Ambiguity:** if more than one **distinct** qualifying parent reference is present, there is no relationship (reason `AMBIGUOUS_CITATIONS`); G2
never chooses the first textual or regex match, the newest, the oldest, the operative-looking or the highest-count candidate. A citation repeated
identically counts once.

**Parent identity:** the relationship names the specific parent `CountAssessment.subject_id` (`site:{site_id}:{scope_type}:{scope_label}`), not merely
a `site_id`, and retains the parent supporting application reference. The existing read-model fields carry this; no schema.

**Pure relationship record** (derived each build, never persisted, no id, no confidence score because only qualified relationships are emitted):
`relationship` (`CONTAINED_IN` only), `child_subject_id`, `parent_subject_id`, `child_application_reference`, `parent_application_reference`, `basis`
(`RM_DIRECT_PARENT_CITATION`), `provenance` (the matched phrase).

**Reason codes** (diagnostic, deterministic, not user-facing): `NO_CITATION`, `BARE_DIGIT_CITATION`, `UNSPECIFIED_RELATION`, `NOT_RESERVED_MATTERS`,
`AMBIGUOUS_CITATIONS`, `CITED_APPLICATION_NOT_FOUND`, `CITED_NOT_PARENT_COUNT_SOURCE`, `PARENT_SCOPE_NOT_WHOLE_SITE`, `PARENT_NOT_EXACT_OPERATIVE`,
`MULTIPLE_PARENT_ASSESSMENTS`, plus `CHILD_NOT_PHASE_SCOPE`, `NO_CHILD_SOURCE`, `METRIC_NOT_COMPATIBLE`, `PARENT_SITE_MISMATCH`.

**Non-overlap boundary:** G2 v1 does **not** infer non-overlap. Siblings remain potentially overlapping; `evidenced_pairs` stays an explicit evidence
input with no production producer; no sum, no residual, no child-set completeness.

**No consumers in G2:** it is not wired into G3a family grouping, the feed, the dashboard, buyer matching, monitoring or residual calculation.

- **Objective:** a pure module deriving evidence-qualified `CONTAINED_IN` records (and diagnostic reason codes) from supplied applications and count assessments.
- **Boundary:** no database/session/network; no `site_linking` change; no schema; no persistence; no consumer.
- **Likely files:** `app/reporting/subject_relationships.py` (new), `tests/test_subject_relationships.py`, `verification/stage2/check.sh`.
- **Tests:** the full matrix in the G2 request — qualified RM + direct exact parent → `CONTAINED_IN`; the authorised "pursuant to outline application" phrase
  qualifies only when every gate passes; bare digit, "relating to", "in association with", variation/NMA/discharge children, the false "(12345)",
  absent/other-site/other-council citations, a citation not supporting the parent count, approximate / unclear-scope / non-operative parents, two
  distinct citations, a repeated citation, no chain traversal, exact `CountAssessment.subject_id`, no non-overlap or residual output, no schema; the
  captured (truncated) site 281 wording yields no relationship.
- **Acceptance:** no relationship without every gate; every record carries provenance; hosted CI green.
- **Stop:** any inference from wording, size, date, address or RM status alone; any chain traversal; any non-overlap inference; any schema.

### G3a — Opportunity family grouping: pure model
- **Objective:** group **existing** subjects into planning/strategic families and select the buyer-specific representative; no new subjects.
- **Boundary:** a pure module with no database/session/network, no feed/dashboard/UI integration, no new opportunity kinds, no
  synthetic whole-site subject, no containment, no unit arithmetic, no change to the universe, monitoring, matching, schema or fingerprints.
  Input is a narrow protocol (not Streamlit/feed internals), with small pure adapters from an existing opportunity id or feed-card dict.
- **Likely files:** `app/reporting/opportunity_families.py` (new), `tests/test_opportunity_families.py`, `verification/stage2/check.sh`.
- **Tests:** deterministic family identity; site grouping; phase-only family; lifecycle + phases; different sites; strategic canonicalisation
  and duplicate-link input; fit and investigative precedence; evidence-tier and stable-key tie-breaks; input-order independence; related
  subjects retained and also-STRONG/POSSIBLE roles; mixed and all-`NOT_SUITABLE` family fit; no unit total; no residual arithmetic; no
  containment claim; existing ids unchanged; no new kinds; conflicting lifecycle fails closed.
- **Acceptance:** all of the above, hosted CI green, no schema.
- **Stop:** any G2 containment logic, phrase-parser change, new kind, universe/feed/dashboard/monitoring change, or production read.

### G3b — Opportunity family grouping: feed integration
- **Objective:** make the buyer-facing feed show **one top-level row per family** with the representative plus related subjects.
- **Hard acceptance requirements:** families built from the **complete** relevant subject set (or a proof that the bounded pool cannot change
  the best subject, family fit, also-STRONG/POSSIBLE list or exclusion state); buyer-mode integration; family-level counts including migration of
  `excluded_not_suitable` from card to family semantics; strategic-family canonicalisation; deterministic cross-family ordering (fit bucket, then
  family key); no unit summation; the UI overlap warning "Related subjects may overlap — do not add unit counts."
- **Stop:** a bounded pool that can change a family result, any summed overlapping units, or an "incomplete family" warning used as the final substitute.

#### G3b Slice 1 — complete buyer-family feed DATA MODEL (Product Owner decisions; additive, not user-facing)
Authorised scope: an **additive** buyer-family result built alongside the existing buyer card feed. **Not authorised in Slice 1:** any dashboard/UI
change, any G2 consumption, any change to the generic/non-buyer feed, the legacy card counts or `build_opportunity_feed`'s meaning.
Direction: **Option A — complete/unbounded family construction** (approved for the current pilot scale; correctness over the old bounded optimisation).

1. **Completeness over the old pool.** The legacy `max(8 x limit, 40)` pool is NOT authoritative for family mode (it can omit members or phase-only
   families, change the representative, family fit, terminal exclusion and the top-N). Family mode builds from the **complete eligible subject population**
   before buyer-fit grouping, ranking and limit.
2. **Complete detector populations.** Lapse: complete. Phase: complete. Recent-permission: complete after the canonical precedence exclusions. Long-pending:
   complete after the canonical precedence exclusions. Strategic: complete across the eligible strategic population. No pool limit before family
   construction; the requested limit is applied ONLY after fit evaluation, grouping, representative selection and family ordering (limit 6 = six
   **families**).
3. **Canonical lifecycle precedence (approved visible correction).** A site covered by a (complete) lapse or phase detector never reappears as
   recent-permission or long-pending merely because its earlier card fell outside a bounded slice. Pinned by tests. Generic/non-buyer behaviour is unchanged.
4. **Strategic eligibility preserved.** The existing strategic eligibility (`_FEED_ELIGIBLE_SIGNALS`, the matched-site and minimum-dwellings filter) and card
   shaping are unchanged: completeness means evaluating the complete population that satisfies that contract, **not** turning every allocation into an
   opportunity. The capacity-ordered SQL `LIMIT`/pre-filter truncation is replaced by a completeness-preserving keyset-paged read (as the universe does),
   with feed eligibility applied across all pages. Universe records are not reused (they bypass feed eligibility). One allocation id = one strategic
   subject = one strategic family; several site relationships cannot duplicate it.
5. **Family order.** Family fit bucket, then the deterministic family key. No commercial score, no strategic-first special case, no pool-order tie-break.
6. **Integrity errors fail closed.** A G3a integrity violation (conflicting lifecycle representations, conflicting strategic subjects, mixed id systems,
   malformed adapter identity) or an unresolvable buyer profile raises a typed/explicit error. There is **no** silent fallback to the legacy card feed.
7. **G2 not consumed.** No `CONTAINED_IN` label, no specificity tie-break, no phrase scanning; family membership is independent of G2 and family
   construction succeeds without the G2 module.
8. **Request-scoped memoisation.** The B2 context may be memoised for one family-feed request only, by (buyer, site_id) for planning-delivery and
   (buyer, allocation_id) for strategic, because the context function's inputs are otherwise identical. `MatchingFacts` are never memoised across subjects;
   no global/process cache; nothing persisted.
9. **Counts (additive; legacy card counts untouched).** `families_considered`, `families_shown`, `families_excluded_not_suitable` (a family for which **every**
   buyer-relevant subject is NOT_SUITABLE), `subjects_considered`, plus the per-detector subject counts. An eligible subject with **no matching facts** makes family mode **fail closed**
   with the typed `MissingFamilySubjectMatchingFacts` (non-sensitive identity only): omitting it could change the representative, family fit, related
   subjects, terminal exclusion and top-N, so it is never skipped, never yields a partial family and never falls back to the legacy cards (the legacy
   card feed keeps its own skip behaviour, unchanged). The family order stays G3a's: fit bucket, then the lexical `(domain, anchor_id)` key - deterministic
   only, no commercial meaning (no strategic-first, planning-first, numeric-id or pool-order rule).
10. **Verification.** An independent unbounded reference oracle in tests (family membership, representative, family fit, related roles, exclusion, top-N);
    adversarial fixtures where the legacy bounded feed differs from the oracle and the new path equals it; precedence regression cases; fail-closed tests;
    generic-feed preservation; memoisation on/off equivalence; no model/paid calls.
- **Boundary:** no schema, no fingerprint/monitoring change, no policy-version change, no new opportunity kinds, no residual, no unit summation, no production read.
- **Likely files:** `app/reporting/buyer_family_feed.py` (new, additive), `app/reporting/opportunity_feed.py` (behaviour-preserving extraction of the shared
  card-building steps only), tests, `verification/stage2/check.sh`.
- **Stop:** any dashboard change; any change to generic feed behaviour; any bounded pool before grouping; any G2 coupling.

#### G3b Slice 2 — buyer dashboard family rendering (PRESENTATION ONLY)
Authorised after Slice 1 merged. Replaces the **buyer** dashboard's flat acquisition cards with one item per `OpportunityFamily`. Generic/non-buyer feed and
the legacy `build_opportunity_feed` are unchanged. No G2 consumption, no buyer-fit/policy change, no `BUYER_MATCHING_POLICY_VERSION` change, no new
extraction, no schema, no fingerprint/monitoring change.

**Primary user question:** "Why is PropertyAIgent showing me this development, and what exactly within it might I pursue?"

**Product principle — evidenced phasing is acquisition-investigation evidence (not availability).** An evidenced phase shows the wider development is being
delivered through at least one distinct smaller scope, which can make it more relevant to investigate than an otherwise identical scheme with no phasing
evidence. It does **not** prove that the phase is for sale, that the developer intends to dispose of it, that other buyer-sized parcels exist, that the rest
will be subdivided, ownership/control, transaction availability, residual capacity, non-overlap or parcel geometry.

**Phasing evidence ladder (product distinction; policy consequences are a SEPARATE later gate):**
- **Level 1 - evidenced child phase.** An actual phase subject is already evidenced (e.g. parent 500 homes, Phase 1 125 homes). The phase is assessed independently
  against the mandate; the wider development may be worth investigating because phased delivery is evidenced. No other parcel, residual or availability is inferred.
- **Level 2 - documented phasing, no established child subject.** Planning/portal/document evidence explicitly states phased delivery but no sufficiently evidenced
  individual subject exists (planning statement, Design & Access Statement, committee report, decision notice/condition requiring a phasing plan, a phasing plan,
  portal proposal text). May warrant investigation; **no synthetic phase, count, parcel size or availability**. **Not displayed in Slice 2**: no accepted,
  provenance-backed structured site-level phasing signal exists today (inventory below). PENDING STAGE 2.6 EVIDENCE QUALIFICATION.
- **Level 3 - no phasing/decomposition evidence.** A scheme merely larger than the mandate. Large scheme != divisible opportunity; no investigative decomposition route
  is manufactured from scale alone.

**Slice 2 policy boundary.** Slice 2 only PRESENTS Level 1 phasing context already present in the family. It does not change STRONG_FIT/POSSIBLE_FIT/
INSUFFICIENT_EVIDENCE/NOT_SUITABLE, investigative classification, reasons or ranking, and does not bump the policy version. A separate post-Slice-2 gate,
**STAGE 2.5B - PHASING INVESTIGATION POLICY**, will decide deterministically how Levels 1-3 affect investigative classification, reasons, ranking and
parent-vs-child interpretation.

**Level 1 display rule (conservative, no new inference):** the family contains **more than one subject** and at least one is an **actual phase** subject
(`slot == PHASE`, its scope key is not the unphased bucket, and its count assessment scope type is `phase`). Wording: "Phased delivery evidenced." A family with a
single subject (including a sole phase) shows no phasing label; strategic families are never labelled phased (linked planning sites do not make an allocation
phased). Forbidden wording: "suitable for subdivision", "remaining", "other phases available", "sold in phases", any family total.

**Existing structured phasing signals (inventory; none accepted for Level 2):** (a) the strategic-allocation Local Plan phasing classification
(`allocation_discovery` `phasing`, surfaced as `MatchingFacts.has_phasing_evidence` for allocations only) - plan-period trajectory evidence about an allocation, not
development phased delivery, and used by v6 for strategic subjects only; (b) the AI image type `phasing_plan` on `VisualEvidence` - AI classification, unqualified;
(c) planning/delivery `MatchingFacts.has_phasing_evidence` is hard-coded False. Level 2 is therefore not implemented; no weak heuristic, no arbitrary document-text
scan, no model call.

**Stage 2.6 carry-forward.** Stage 2.6 should assess qualified extraction of phasing evidence from planning statements, Design & Access Statements, committee
reports, decision notices, phasing plans, reserved-matters documents and relevant portal proposal text, distinguishing **FACT** ("the document states that
development is phased" - may become qualified evidence) from **INFERENCE** ("there may be a buyer-sized acquisition opportunity" - acquisition reasoning).

**Family UX contract.** One top-level item per family: (1) DEVELOPMENT/FAMILY CONTEXT - existing safe site fields only (title, location, council); not a synthetic
whole-site subject, and a phase-only family shows no fabricated "Whole site" subject; (2) BEST ACQUISITION SUBJECT FOR THIS BUYER - the G3a representative, never
re-ranked: label/type, unit count with honest precision (existing count wording: exact / approximate / range / unverified; never a family total), existing fit
language (Strong fit / Possible fit / Investigate / Insufficient evidence; Not suitable only in related lists), key deterministic reasons and the existing
policy caveat; (3) PHASING CONTEXT - only where Level 1 qualifies; (4) RELATED ACQUISITION SUBJECTS - compact/collapsed by default (also strong, also possible,
investigative/insufficient, not suitable where it helps explain the development); label/type, units/precision, fit, investigation state only; no internal subject
keys, detector ids, reason codes or fingerprints; (5) OVERLAP - for more than one subject: "Related subjects may overlap — do not add unit counts." A single-subject
family stays compact (no expander, no overlap note, no phasing label). A strategic family stays one canonical strategic item keeping its existing strategic
information, with no planning-delivery terminology forced on it.

**Relationships.** G2 is not consumed. Family membership means only "these subjects share the same planning-site family"; permitted wording is neutral ("Related
opportunity subjects within this development"). No "contained in / pursuant to" claim.

**Counts.** The buyer dashboard moves from card semantics to family semantics: families considered / shown / excluded as not suitable, subjects considered, and the
per-detector figures explicitly labelled as SUBJECT counts. A family is terminally not suitable only when every buyer-relevant subject is NOT_SUITABLE.

**Error state.** If family construction fails (integrity error, missing facts, unresolvable buyer) the buyer dashboard shows a concise operator-safe message that
acquisition-family results are temporarily unavailable. It never falls back to the legacy buyer cards and exposes no traceback, database detail or internal ids;
access refusals (Stage 1) are not swallowed. Generic views are unaffected.

**Architecture.** Business logic stays out of the UI: a pure presenter (`app/reporting/family_presentation.py`) turns the family result into plain view models;
`app/ui/shell.py` renders them; the buyer branch of `app/ui/pages/00_Dashboard.py` calls them. **Stop:** any change to fit/ranking/policy, any relationship claim,
any family total or "remaining" claim, any Level 2 display without an accepted structured signal, any legacy fallback.

### G4 — Subject-level MatchingFacts/context adapter
- **Objective:** a dedicated subject facts builder and context handling; match existing phase/whole subjects independently, with parent evidence as labelled context.
- **Boundary:** no policy change (still v6); no new kinds emitted; migrates inventory #3 and #4 to the strict parser.
- **Likely files:** `app/policy/buyer_matching.py` (builder only), `app/policy/buyer_matching_b2_context.py`, `app/reporting/opportunity_intelligence_packet.py`, tests.
- **Tests:** a 125-home phase evaluated against a buyer's range; parent not blindly matched when a child is evidenced; unknown kinds yield no facts; no inherited parent count.
- **Acceptance:** subject facts carry their own count, development type, planning position and scope; fingerprint inputs unchanged.
- **Stop:** subject facts silently reusing parent facts.

### POST-G4 PRODUCT-POLICY DECISION — mixed-specialist-parent semantics
Decide the no-evidenced-child outcome and **whether `BUYER_MATCHING_POLICY_VERSION` must move to v7**,
including the monitoring transition consequence. Not decided here; requires its own approval.

### G5 — Residual-capacity intelligence
- **Objective:** expose the evidence proposition at family level with the approved wording.
- **Boundary:** no residual acquisition subjects; no new ids; no availability language.
- **Likely files:** family module, `app/reporting/residual_capacity.py` (consumer only), tests.
- **Tests:** RESOLVED / APPROXIMATE / UNKNOWN / `MATERIAL_CONFLICT` presentation with injected evidence; fail-closed with none.
- **Acceptance:** "Supported residual planning capacity: N homes" appears only for RESOLVED and carries the not-availability disclaimer.
- **Stop:** any wording or logic implying availability, parcel identity, ownership or control.

### G6 — Additional evidenced component subjects
- **Objective:** `MIXED_COMPONENT` subjects where independent component-scope evidence exists.
- **Boundary:** depends on G1A and the emission gate; no inference from a development-type string; v6 unchanged unless the post-G4 decision says otherwise.
- **Likely files:** the subject builder, universe constructors for the new kind, tests.
- **Tests:** component created only with evidence; verified-site set (inventory #5) unchanged; baselining via manifest produces no NEW.
- **Acceptance:** each component matched with its own development type.
- **Stop:** any component without independent scope evidence.

### G7 — Affordable-package identity / disabled adapter
- **Objective:** identity and a disabled adapter only.
- **Boundary:** production creation disabled until Stage 2.6; depends on G1A and the emission gate; no AH extraction or inference.
- **Likely files:** the subject builder, tests with injected qualified evidence.
- **Tests:** disabled by default; enabled path works only with injected qualified evidence; verified-site set unchanged.
- **Acceptance:** no package in production output.
- **Stop:** any package created without qualified evidence.

### G8 — Monitoring / evaluation / transition integration
- **Objective:** new-kind baselining through the controlled transition, evaluation anchoring, and the fingerprint-version decision.
- **Boundary:** requires G1A and the carried-forward pre-production transition tooling before any production use; no deployment.
- **Likely files:** transition manifest tooling, `app/policy/agent_evaluation_persistence.py`, tests.
- **Tests:** new subjects baseline as existing; no false NEW; each subject has its own anchor; no parent evaluation reuse; fingerprint-version decision recorded.
- **Acceptance:** a dry-run transition report reviewed by REVIEW.
- **Stop:** any false NEW or parent-to-child evaluation reuse.

## Non-Requirements (explicitly out of scope)

Promotable-land intelligence; NPPF/planning-policy scoring; Stage 2.5C; new scraping; qualified AH
extraction; Stage 2.6 evidence production; financial appraisal; comparables; ownership inference;
transaction-availability inference; parcel-geometry invention; a generic rules engine; any production
deployment; any change to existing opportunity ids.

## Data model

No schema change is planned for G1–G4. `AcquisitionSubjectAnchor` carries identity via new namespaced
scope keys; the parent/family relationship is a recomputed read model. Any schema need discovered
later requires a specification amendment before implementation.

## Roadmap boundaries

- **Stage 2.5C — Promotion Opportunity Intelligence** (separate): defines evidence-backed "promotable"
  land — emerging/draft allocations, other plan-making evidence, housing-delivery/supply pressure, site
  constraints and suitability, land not currently represented as a consented acquisition opportunity.
  Stage 2.5B neither designs nor implements it, and does not depend on it. It may later reuse the
  identity grammar.
- **Stage 2.6 — Qualified Evidence Expansion** (separate): qualified affordable-housing evidence
  production and potentially improved containment/non-overlap evidence. Stage 2.5B does **not**
  depend on speculative Stage 2.6 evidence and fails closed when evidence is unavailable.
- **Pre-production transition gate (carried forward):** Category A/B diff builder; field-level
  rebaseline guard; standalone per-mandate re-onboarding (not the full bootstrap); dry-run ordinary
  monitoring sync.

## Production transition

Nothing in this specification is deployed. Any future production transition for new subject kinds
follows the monitoring contract and requires separate production authority.

## Benchmark carry-forward

Fixtures 281 and 526 are invalid for their original purpose and are to be retired/replaced; this
specification adds the future replacement requirement for an acquisition-subject decomposition case.
Product Owner expectations: 460, 57, 213/National Housebuilder, 104/Nesten, 491, 140, 67:3B →
INVESTIGATE; 61 → MONITOR. No fixture is edited by this specification.

## Acceptance Criteria (for this specification)

Planning vs acquisition subject explicit; residual capacity not a subject by default; existing ids
unchanged; unknown kinds fail closed; all known id consumers inventoried; monitoring-prefix
normalisation isolated as G1A; parent identity deterministic and containment sourced; overlapping
subjects never summed without evidence; family ranking without double counting yet buyer-specific;
strategic parents coexist; mixed children independently matchable where evidenced; v7 deferred until
after G4; affordable-package production disabled pending Stage 2.6; parent evaluations never leak;
evaluation-fingerprint impact unresolved until verified; 2.5C and 2.6 cleanly separated; gates
bounded to execute independently.

## Open decisions for REVIEW

1. ~~Family boundary between strategic allocations and linked planning sites~~ — **DECIDED** by the
   Product Owner (see Family feed contract): one canonical strategic family per allocation, cross-linked to
   planning families, never duplicated per linked site.
2. Delimiter-safe encoding details (percent-encoding vs a slug) and reserved anchor prefixes (G1).
3. Whether G1A corrects phase granularity or keeps it with an explicit per-site rule (G1A).
4. The post-G4 mixed-specialist decision and any v7 transition.
5. Evaluation-fingerprint version impact (verified at implementation).
6. Whether a second RM application sharing a phase code is a scope collision requiring its own
   evidence rule (G2).
