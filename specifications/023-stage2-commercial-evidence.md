# Stage 2 commercial evidence contract

Authorised baseline: `28c2c16e3e715c806dfb33f7edfff65e2aaa5451`.
This contract supersedes historical commencement/completion/availability
assumptions in the delivery section of specification 002. It changes evidence
semantics, not acquisition strategy, access control, AH policy or schema.

## Claims and qualification

- Administrative filings establish planning activity only. Their absence does
  not establish non-commencement. Phase labels and qualification must retain
  potentially useful permission leads while recording commencement as unknown.
- Postcode EPCs are investigation evidence, not scheme completion evidence.
  Pre-grant, undated, invalid-date and duplicate records never establish delivery.
  Preserve returned evidence and exclusion reasons in the lookup result. The
  existing database has no reviewed dwelling/phase linkage for these records;
  do not invent one or trust legacy derived build-status strings as verification.
  Existing stored values remain unchanged and may be exposed as unverified context.
- A stronger, independently scoped completion source must not be overridden by
  administrative activity. Stage 2 does not create a new completion-data writer.
- Availability is unknown unless independently evidenced. An explicit availability
  filter returns only evidenced matches; with the current contract there are none.
  Show the limitation and allow users to investigate without that filter. Merely
  excluding evidenced completion is a separate operation.
- The existing grant-plus-three-years calculation is an assumed review date,
  not an evidenced statutory deadline. Preserve its anchor and date, expose its
  assumption, and never assert legal lapse, seller pressure or verified urgency.
  The implementation-deadline transaction signal is UNKNOWN for assumed dates.
  Potential permission-review leads may still surface with this limitation.
- Reserved Matters establishes a planning submission/stage, not ownership,
  land control, disposal, availability or whole-permission legal protection.
- Numeric bounds require a finite non-negative integer, from the resolved
  operative fact. Missing, malformed and conflicting totals do not match an
  explicit bound. Unfiltered browsing preserves those leads as unknown.
  A conflicting consent cannot fall back to a convenient active proposal. Phase
  totals require agreement across eligible scoped counts; no first/max winner.
  Named phase buyer qualification never inherits a whole-site total. Report sums
  describe known counts and disclose the number of unknown totals.
- A dashboard destination preserves site/opportunity and selected buyer context.
  A site with no display-qualified applications shows its identity and a scoped
  evidence limitation, including existing authoritative anchor/source links when
  available. Do not fabricate evidence or substitute a different subject.
- Joint-plan membership describes the plan. Allocation cross-boundary geography
  remains unknown without allocation-specific boundary evidence; membership alone
  cannot satisfy a cross-boundary filter.
- Visual selection, machine confidence and human confirmation are separate.
  Only review_status=confirmed supports a confirmed visual claim. Primary-image
  selection does not confer confirmation; rejected evidence is excluded.

## Validation and data boundary

## Bounded unit/phasing amendment (Product Owner approved 2026-10-05)

Continuation base: `090fd06b4573fe82dd09d5460a17a109b07306d3`; preserve it.
This amendment supersedes the count-agreement paragraph above where stated:

- Resolve counts per subject/scope and metric. Whole-site selection never uses
  a named child or a multi-phase application as a whole-site total. Scope names
  do not prove containment, disjointness or saleability.
- An approved variation can supersede only same-scope approved evidence with
  an explicit reference link and supported chronology. Pending/refused counts
  do not change approved counts. Recency alone does not prove supersession.
- Use a derived EXACT/APPROXIMATE/RANGE/UNKNOWN assessment carrying provenance,
  bounds, scope, metric, precision and separate confidence. Only the explicitly
  accepted same-current-scope set {100,101,102} gets the ~100 discovery treatment;
  no general tolerance is invented. Other differing point counts remain conflict.
  Source-supported ranges can be represented without inventing a range from conflict.
- Strict point inputs remain absent for approximate/range/conflict assessments.
  Explicit hard-bound checks use evidence bounds, never the rounded label.
  Existing buyer soft preferences can retain uncertain discovery leads; buyer
  total/affordable metric choice remains unchanged. No mandate schema change.
- Profile, Explore, reviewed cards/matching/universe and exports share this
  assessment. Unresolved approved evidence cannot fall back to a live proposal.
- Retain every eligible phase subject before normal feed limits. Never sum
  multiple phases without explicit non-overlap evidence; keep individual rows.
- Tenure figures must share subject/version before forming a combined breakdown.
  Existing AH qualification/security remains authoritative and unchanged.
- No schema migration, persisted hierarchy/package model or Level 2 agent.
  Unknown relationships stay unknown. Any need for those changes returns to REVIEW.

Test deterministic consumers with synthetic adversarial fixtures and offline
SQLite. Historical site 491/allocation 45 are reported observations, not invented
production fixtures. Local reproduction of their failure modes verifies code
semantics only; real-world factual verification remains pending without sources.
No production rewrite, migration, paid API call, ingestion or deployment.
Unversioned stored site narratives are withheld from buyer presentation until
reviewed against this contract; their database content and timestamps remain.
Future opportunity fingerprints can differ because physical and unit evidence
semantics changed. Historical monitoring/evaluations need a separately authorised
transition review before any production recomputation; do not emit this as a new
real-world planning event.
Inventory any persisted derived-data carry-forward separately; exact affected
production row counts cannot be supplied without an authorised future query.

## Final pre-merge reconciliation (2026-10-05)

Uncertain residential scale remains discoverable, but cannot yield unqualified
STRONG_FIT when its supported bounds do not establish the buyer's target range.
Use the existing INSUFFICIENT_EVIDENCE classification and investigative reasons;
soft targets do not become hard exclusions. Fully contained bounds can support
fit with uncertainty disclosed. Rounded/stale scalars cannot override assessment
bounds; unknown stays unknown. Buyer total/affordable metric selection is unchanged.

For an exact count, prefer the established operative application among genuine
supporting extractions. Otherwise use deterministic supporting-reference/ID order.
Never attribute a count to a source without that count, or change the resolved
count to obtain a preferred source. AH identity remains independently selected.
