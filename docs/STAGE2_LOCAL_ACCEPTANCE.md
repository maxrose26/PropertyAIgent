# Stage 2 local acceptance

## Identity and authority

Base commit: `28c2c16e3e715c806dfb33f7edfff65e2aaa5451`.
Base tree: `d38b287f7663120d7a70a5ef7573007fe8d4c695`.
Branch: `stage2/commercial-evidence-trust`.
Remote master was refreshed before implementation and again before committing;
both observations matched the authorised base. Local engineering only.

## Reproduction

`verification/stage2_baseline_probe.py` runs synthetic shapes against the checkout
at cwd, uses in-memory SQLite and mocked EPC responses, and makes no provider call.
The baseline and corrected results are in `stage2-evidence/*-probes.json`.
All six failure mechanisms were reproduced against the exact accepted baseline:

- D01: ten pre-grant EPCs for ten expected units produced `complete`; corrected
  result is unknown with zero date-qualified certificates and retained raw evidence.
- D02: a later administrative filing promoted unknown AND legacy complete to
  underway; corrected physical status stays unknown and raw state stays intact.
- D03: grant+three-years was labelled a commencement deadline without a basis;
  now explicitly an assumed review date, not legal lapse, availability or urgency.
- W01: a qualifying review-date card had zero display-qualified applications;
  now the same subject opens a scoped limitation with its originating reference
  and source. This reproduces the Site 491 failure shape, not its current facts.
- D04: joint-plan membership supplied other councils as allocation cross-boundary
  geography; now membership and unknown allocation geography are separate.
- D05: an automatically selected, 90%-confidence needs-review image yielded a
  confirmed summary but needs-review status; both now require human confirmation.
  This is the Allocation 45 failure shape, not a production data correction.

## Contract and consumer coverage

Specification 023 is the governing contract. EPC postcode records cannot verify
scheme delivery; administrative filings cannot verify works. There is no accepted
reviewed dwelling/phase completion writer in the current schema, so stored EPC
classifications remain unverified, not promoted to physical facts. Returned EPC
rows and reasons are retained in memory; no raw-EPC persistence schema was added.
Availability has no evidenced producer and explicit availability searches return
no matches with an explanation. Reserved Matters makes no land-control claim.

Known finite whole counts are shared across Explore and buyer qualification.
Conflicted consent cannot fall back to a convenient proposal. Phase counts require
agreement, never first/max selection; phase feeds cannot inherit a whole-site
count. PDF totals describe known counts and disclose unknown coverage.
Dashboard, feed, profile, inline detail, allocation views, search, qualification,
report prompts and exports use the corrected semantics. Stored unversioned site
narratives are withheld rather than silently republished; data is not erased.

## Verification

Python 3.12 isolated environment, repository requirements and existing Stage 1
constraints, SQLite fixtures. Final results (all zero failed/errors/skipped/deselected):

| Suite | Passed |
| --- | ---: |
| Focused commercial evidence | 62 |
| AppTest dashboard/profile/source/return journeys | 2 |
| Broader relevant regression suite | 769 |
| Stage 1 access, buyer scope, call sites and commands | 199 |
| Existing UI session lifecycle | 8 |
| Total | 1040 |

Machine-readable final results are in `stage2-evidence/*.xml`. Tests did not call
paid APIs, Google or production. Non-UI tests use the existing syscall-denial
runner. AppTest uses `stage2_ui_offline_pytest.py`: network connect and datagram
send syscalls are denied, while asyncio's local socketpair is permitted. Synthetic
identity uses the existing Stage 1 test adapter; application auth is unchanged.
This is not browser OAuth, production HTTP delivery or deployment acceptance.

The 769-test regression selection comprises site profile/headline, dashboard/feed,
recent permissions, transaction signals, allocation discovery/visuals, Explore,
buyer matching/B2, reconciliation and Gate 2 alignment, opportunity universe/change/
time transitions, allocation reports, entity search, ownership, Arrow and AH-scope
preservation. Focused and UI suites are separate (no double counting).

Three historical tests failed unchanged at the accepted base: the old AH tooltip
label, a top-level-only source slice after the Stage 1 page wrapper, and a pool-size
test assuming an unqualified legacy AH percentage could produce Strong Fit. Their
fixtures/assertions were repaired to the existing accepted contracts: labelled raw
AH text; AST-extracted function body with current tenure label; explicit synthetic
qualified MatchingFacts at the producer boundary for the pool-size test. Buyer
classification and selection assertions remain real. Stage 2 tests that expected
admin activity to mean underway, or inferred deadlines to mean statutory urgency,
were deliberately migrated to specification 023 with raw-evidence checks retained.

## Product walkthrough and limitations

Both complete and limited-evidence routes render the SAME synthetic subject,
originating reference/source, requested scope limitation, selected buyer, and back
link. Returning to Dashboard preserves the selected buyer; the existing active
mandate resolution is reused. Wrong-subject source references are rejected by the
shared origin contract. No fabricated profile evidence is added.

A permission/admin lead claims permission/planning activity only: investigate
current progress and availability. An assumed-date lead warrants checking actual
conditions now, not treating the seller as distressed. A visual pending review is
presented as such, even at high machine confidence. Joint-plan membership is useful
policy context but does not establish the allocation's physical boundary.

CODE SEMANTICS VERIFIED is distinct from REAL-WORLD PLANNING FACT VERIFIED.
No current production planning facts were verified. Site 491, Allocation 45 and
other historical observations remain REAL-WORLD VERIFICATION PENDING.

No schema/migration changes. No new full-corpus retrieval. Profile selection adds
bounded existing buyer/mandate reads and an optional one-reference, one-site query;
the limited path reads only that site's existing applications. Production query
cost has not been benchmarked under the external infrastructure restriction.

Future monitoring fingerprints can differ (unit reconciliation, physical status
and newly retained permission leads). Stored summaries, derived build classifications,
monitoring snapshots and evaluations were not rewritten. Before production
recomputation, separately review/rebaseline this semantic transition so it is not
misrepresented as a real-world planning change. Exact affected production counts
are unknown; no production inventory or egress was authorised/performed.

No Google work, source-secret access, production DB mutation, backfill, scraping,
AI regeneration, paid calls, Render change, cron/job execution, deployment, master
merge, P0-A activation, AH migration/security change or Stage 3 work was performed.
Independent review must assess the exact local committed candidate; a local pass
does not authorise publication, integration or any production activity.
