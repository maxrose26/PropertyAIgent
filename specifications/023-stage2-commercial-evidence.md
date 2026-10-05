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
