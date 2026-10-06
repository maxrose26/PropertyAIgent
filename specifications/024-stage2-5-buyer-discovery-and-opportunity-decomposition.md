# Stage 2.5 — Buyer Discovery & Opportunity Decomposition

Status key used throughout:

- **IMPLEMENTED / ACCEPTED** — on branch `stage2.5/opportunity-decomposition`,
  accepted by REVIEW at `b0001c7e40e24a8a09e2e05b79643c8b0415db96` after hosted CI.
  Not merged to master and not deployed.
- **APPROVED DIRECTION / NOT IMPLEMENTED** — agreed product intent only. No code exists.

Acceptance evidence: `docs/STAGE2_5_ACCEPTANCE.md`. Evidence semantics inherited
from Stage 2: `023-stage2-commercial-evidence.md`.

## Objective

Turn trusted planning evidence into buyer-specific acquisition opportunities
without overstating what the evidence proves.

Product north star: PropertyAIgent continuously turns fragmented planning, ownership
and development evidence into ranked acquisition opportunities matched to a buyer's
strategy:

shared evidence → trusted planning subjects → acquisition subjects → buyer-specific
opportunity interpretations → ranked opportunities → selective deep verification →
continuous monitoring/re-evaluation.

Planning intelligence remains the evidence foundation; acquisition intelligence is
the primary product outcome.

## Business Value

A buyer who "normally wants 50–100 homes" should still see a commercially close
48- or 105-home opportunity, clearly labelled as close rather than preferred, and
large schemes that may contain a relevant parcel should stay investigable rather
than silently disappear.

## User Story

As a buyer (housebuilder, strategic land buyer, housing association), I want
opportunities ranked by how well their evidenced scale and attributes fit my
mandate, with close-but-not-preferred opportunities surfaced separately and every
material unknown visible, so that I can prioritise without being misled.

## Core concepts

**Planning subject** — a site, application, phase, plot or other subject represented
by planning evidence.

**Acquisition subject** — the commercially meaningful thing a buyer may acquire or
pursue. One planning scheme may eventually yield several simultaneous acquisition
subjects (see Stage 2.5B). *Decomposition is NOT YET IMPLEMENTED*: Stage 2.5A
evaluates the current planning/opportunity subject only.

### Evidence guardrails (IMPLEMENTED / ACCEPTED as principles)

- planning status ≠ acquisition status;
- planning capacity ≠ availability;
- Reserved Matters approval ≠ unavailable;
- developer/applicant identity ≠ ownership or control;
- residual planning capacity ≠ verified acquisition package;
- UNKNOWN ≠ zero; unknown physical status ≠ uncommenced;
- planning activity ≠ physical commencement; EPC evidence alone ≠ completion;
- commercial availability is never inferred from planning progression.

## Requirements — Stage 2.5 preflight (IMPLEMENTED / ACCEPTED)

### Gate 1 — Safe phase aggregation

- One shared rule, `summarize_phase_units`; no blind phase summation.
- A multi-phase aggregate requires explicit, sourced pairwise non-overlap evidence
  (`evidenced_pairs`); potentially overlapping phases/sub-phases are never summed.
- Partially known totals are withheld, never shown as complete.
- A single correctly scoped phase remains useful; parent, phase and sub-phase counts
  stay separate; plots/incompatible subjects never create unsupported totals.
- Status information remains available when a unit aggregate is withheld.

### Gate 2 / 2H — Residual planning capacity (foundation)

- `app/reporting/residual_capacity.py` returns RESOLVED, UNVERIFIED or MATERIAL_CONFLICT.
- RESOLVED requires: exact compatible metrics; operative/eligible positions;
  explicit trusted containment; pairwise non-overlap where several children exist;
  explicit child-set completeness (never inferred from "all supplied children were
  processed"); compatible site/scope identities; meaningful provenance. Otherwise
  `residual_planning_capacity` is None.
- Cross-site subtraction, negative residuals and duplicate child IDs are blocked;
  approximate evidence never becomes an exact residual.
- A resolved residual means only *supported residual planning capacity*. It does not
  establish availability, ownership, control, deliverability, one coherent parcel,
  an acquisition package, unexpired permission or non-commencement.
- **No production consumer** currently turns this primitive into an opportunity.

### Gate 3 — Supporting-source provenance

- One shared rule, `select_count_supporting_source`, used by buyer matching and the
  site profile: SUPPORT FIRST → OPERATIVE PREFERENCE SECOND → deterministic genuine
  supporter (reference/ID order). Only an application that is one of the count's
  sources AND whose own extracted total equals the exact count may be attributed.
  Operative, newer or alphabetically convenient non-supporters never receive
  attribution. Count resolution is unchanged; total/private/affordable metrics stay
  separate; AH identity is selected independently.
- **N2-B approximate-count corroboration** (`_corroborated_development_type`): for
  an assessment the CountAssessment rules have already accepted as APPROXIMATE /
  `immaterial_variance` (spec 023's single accepted same-scope set 100/101/102),
  development type is used only if every supporter carries the same non-blank
  stored value. Any null, blank, disagreement or missing supporter fails closed.
  Values are compared as stored (no domain normaliser exists). The operative
  application is preferred for provenance only when it is itself a supporter. The
  helper returns a value and a provenance reference only, never a record, so no
  other field (affordable, tenure, bedrooms, ownership, planning facts) is borrowed.
  This creates **no general unit-count tolerance**.

### Gate 4 — Fingerprint / monitoring ownership

- Buyer-matching policy version is hashed into the mandate fingerprint and the
  agent-evaluation input fingerprint; it is never part of the opportunity fingerprint.
- Opportunity fingerprints are global evidence snapshots. However, planning-delivery
  `fingerprint_fields` (unit count, affordable count, `development_type_raw`,
  `is_specialist_development`) come from `build_planning_delivery_matching_facts_
  from_operative`, so a **software derivation change** in that builder can move them.
- Known derivation-drift categories (software changes, not real-world events):
  - **Category A — Gate 3** exact-count supporting-source attribution;
  - **Category B — N2-B** approximate-count development-type corroboration.
  Both can change `development_type_raw` and/or `is_specialist_development`.

### Gate 5 / 5B — Physical status honesty

- Physical status remains UNKNOWN where evidence is insufficient
  (`classify_build_status` returns `unknown`); planning activity and EPCs remain
  unverified context.
- Explore's control reads "Hide sites with verified completion evidence" and hides
  only an explicit `complete` status; UNKNOWN always remains visible; the natural-
  language exclusion shows an evidence notice.
- Physical status is not a universal opportunity exclusion; richer physical-state
  matching depends on Stage 2.6 evidence and buyer-specific appetite
  (`development_state_appetite` remains soft).

## Requirements — Stage 2.5A buyer matching policy v6 (IMPLEMENTED / ACCEPTED)

`BUYER_MATCHING_POLICY_VERSION = 6`. `assess_buyer_fit` is the single authority.

### Preferred vs discovery range

- **Preferred range** — the buyer's normal target scale (mandate min/max).
- **Discovery range** — a wider acquisition-discovery envelope:
  `DEFAULT_DISCOVERY_TOLERANCE_PERCENT = 10`, applied independently to each boundary
  and rounded outward in integer arithmetic: lower = floor(min × 0.90),
  upper = ceil(max × 1.10). Preferred 50–100 → discovery 45–110; 51–99 → 45–109.
- `discovery_bounds` supports one-sided bounds (a missing bound stays missing), but
  **persisted mandates remain two-sided**; one-sided mandates are not implemented.
- The tolerance is policy, not a stored or buyer-configurable value.

### Classifications

- **STRONG_FIT** — the current subject satisfies the buyer's preferred-fit contract.
- **POSSIBLE_FIT** — scale is not verified within preferred but is wholly within the
  discovery envelope, with no higher-precedence blocker. Surfaced; never a verified
  preferred fit.
- **INSUFFICIENT_EVIDENCE / investigate** — evidence cannot establish discovery-
  envelope compliance; a required evidence gap or material conflict remains; OR the
  current known subject is outside the soft discovery scale but remains worth
  investigating for a relevant sub-scope. For an exact count (e.g. 500 against
  45–110) the count is not uncertain; the reason reads "outside this buyer's
  discovery range … investigate whether a relevant phase or acquisition sub-scope
  exists".
- **NOT_SUITABLE** — reserved for explicit hard buyer-rule failures.

### Precedence

1. explicit hard exclusion → NOT_SUITABLE;
2. blocking required-evidence gap / material conflict / discovery-boundary
   uncertainty → INSUFFICIENT_EVIDENCE;
3. known current subject outside soft discovery range → INSUFFICIENT_EVIDENCE as an
   investigative exception;
4. inside discovery but outside preferred → POSSIBLE_FIT;
5. preferred-fit contract satisfied → STRONG_FIT;

subject to explicit mandate-specific positive routes (below). Buyer matching stays
multi-dimensional: POSSIBLE scale never rescues a geography, acquisition-type,
development-type, wholly-affordable or other hard exclusion.

### Required examples (soft preferred 50–100, discovery 45–110)

| Evidence | Result |
|---|---|
| 75, 50, 100 | STRONG_FIT |
| 45, 49, 101, 105, 110 | POSSIBLE_FIT |
| 44, 111 | INSUFFICIENT_EVIDENCE / investigate (outside discovery) |
| 300, 500 (no explicit oversized route) | INSUFFICIENT_EVIDENCE / investigate sub-scope |
| range 100–102, 48–52, 105–110 | POSSIBLE_FIT |
| range 105–115, 40–60, 90–120 | INSUFFICIENT_EVIDENCE (evidence crosses a discovery boundary) |
| range 40–44, 111–120 | outside discovery / investigate |
| material conflict (e.g. 100 vs 180) | never POSSIBLE_FIT |
| unknown | never zero, never STRONG/POSSIBLE |

Rounded display scalars never override CountAssessment bounds.

### Hard constraints and explicit positive routes

- Discovery tolerance never weakens an explicit hard constraint:
  `below_minimum_scale_is_exclusion` applies at the stated minimum (Housing
  Association: 49 affordable homes against a hard minimum of 50 → NOT_SUITABLE).
- Discovery tolerance never erases an explicit positive route: Strategic Land Buyer's
  `large_allocation_is_self_qualifying` keeps a qualifying 3,500-home strategic
  allocation at STRONG_FIT (as an investigative exception). This is not a generic
  oversized-site rule for other buyers.

### Affordable evidence (N1-B)

- On planning delivery, an untrusted/missing affordable percentage stays untrusted
  and visible ("Affordable housing proportion has not been confirmed - not assumed
  to be 0%."), adds an investigation note, and **does not block** STRONG/POSSIBLE
  fit on its own. It never becomes 0%.
- Positive qualified wholly-affordable evidence still triggers an explicit buyer
  exclusion. Legacy AH percentages remain unqualified Buyer Fit inputs (AH/P0-A).
- Affordable/RP mandates still require trusted affordable QUANTUM where their scale
  metric or AFFORDABLE_HOUSING_PACKAGE acquisition type requires it.

### Fit versus due diligence

Buyer fit asks "is this sufficiently aligned with the buyer's strategy to surface and
prioritise?" — not "has every material due-diligence fact been verified?". Material
unknowns stay visible and block fit only where that evidence is required to
establish the opportunity for that buyer.

### Discovery, ranking and consumers

- Personalised feed order for otherwise comparable opportunities: STRONG_FIT >
  POSSIBLE_FIT > INSUFFICIENT_EVIDENCE (investigative) > INSUFFICIENT_EVIDENCE;
  NOT_SUITABLE stays excluded and counted.
- "Possible fit" badge; onboarding summaries count `possible_fit` separately; the
  agent prompt states POSSIBLE_FIT's deterministic meaning only when present, and the
  model's output carries no buyer-fit classification to upgrade.

## Non-Requirements

NOT YET IMPLEMENTED (none of these exist today):

- acquisition-subject decomposition, including the 500/125 canonical example;
  residual housebuilder acquisition opportunity generation; package creation;
  parcel inference; a persisted package/hierarchy model (Stage 2.5B);
- buyer-configurable or asymmetric discovery tolerance; one-sided persisted mandates;
- richer verified physical-status states, completed-stock appetite, SFH-investor profile;
- a qualified affordable-percentage pipeline, general count tolerance and other
  real-world evidence validation (Stage 2.6);
- the Deep Opportunity Verification Agent and the Autonomous Acquisition Agent.

## Data Model

No schema change. No new tables, columns or fingerprint versions.

## Production transition (REQUIRED, NOT YET PERFORMED)

Before the first ordinary opportunity-monitoring sync after an eventual Stage 2.5
deployment:

1. deploy only under separate production authority;
2. run `app/reporting/opportunity_monitoring_transition.py` as a DRY RUN;
3. identify the exact Category A + Category B opportunity IDs from the before/after
   fingerprint difference (never hard-coded or guessed);
4. review that ID set;
5. apply it through the existing `rebaseline_ids` mechanism (snapshot correction,
   not a change event);
6. re-onboard buyer mandates for policy v6;
7. run a dry ordinary monitoring sync;
8. confirm remaining changes are genuine evidence changes;
9. resume ordinary monitoring only after approval.

**None of these steps has happened.** Production buyer matching remains the
previously deployed policy until then.

## Benchmark

Accepted deterministic policy: v6. The frozen Agent Evaluation Benchmark keeps v4
provenance/expectations. Required sequence: v6 acceptance → this specification →
reviewed v4→v6 benchmark rebaseline → production recomputation only under separate
authority. Fixtures are unchanged.

## Acceptance Criteria

Met at `b0001c7e40e24a8a09e2e05b79643c8b0415db96` (hosted run `37430072540`); see
`docs/STAGE2_5_ACCEPTANCE.md`.

## Future Enhancements

### Stage 2.5B — Acquisition subject decomposition (APPROVED DIRECTION / NOT IMPLEMENTED)

Canonical example: a 500-home outline permission plus a 125-home Reserved Matters
parcel. Stage 2.5B must determine whether trusted evidence supports separate
acquisition subjects, e.g. an advanced ~125-home parcel (SFH/investor), a potential
affordable package (RP, subject to tenure/package/legal verification), residual
planning capacity up to ~375 homes (housebuilder, only where Gate 2/2H resolves it),
and the RM parcel as a developer opportunity. It must reuse Gate 1 scope safety,
Gate 2/2H residual safety, Gate 3 provenance, the existing acquisition-subject
anchor architecture and v6 matching. Until then a large parent stays an
investigative exception.

### Stage 2.6 — Real-world evidence validation

Owns: qualified affordable-percentage evidence; affordable quantum/percentage
validation; broader extraction validation; real-world source/provenance validation;
commencement/completion evidence; any general count-variance approach beyond the
accepted Stage 2 case.

Additional buyer archetypes (e.g. an SFH investor) are not Stage 2.6 work and need
separate product scope. Buyer-configurable/asymmetric discovery ranges also need
separate scope.
