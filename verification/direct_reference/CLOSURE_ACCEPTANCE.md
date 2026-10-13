# Stage 4 known-reference closure admission

Authority: Product Owner autonomous known-reference gate closure, 2026-10-13.
No discovery, deployment, models, semantic relaxation or Trafford Batch B.

The private read-only census at 2026-10-13 12:24:33.082790+00:00 returned
1,453 applications (read_only=on, statement_timeout=10s). Application identities,
site links, current-buyer counts, monitoring counts, intelligence-presence and
refresh-required indicators match the retained census. Raw census is not in Git.

Recovery correction: the previous statement that all recorded dependency counts
matched was incorrect. The earlier export records 28 allocation-link incidences
across 22 applications; the 12:24 export records 114 across 107 applications.
85 application rows differ. These are per-application counts repeated for shared
sites, not counts of distinct allocation relationships. The current SQL counts
all allocation_site_relationships rows for each application's site. The earlier
SQL definition is not retained here, so a query-definition difference versus a
real intervening relationship change is not established.

Allocation counts are not used by the retained policy classifier, route admission
or cohort generator. All inputs used for dependency prioritisation above match.
The policy-due denominator remains 118, the extension remains 512, and the frozen
17/19 manifests and hashes are unchanged. No pending-cohort member has a changed
allocation count; expanded members 298, 708 and 710 do, but their selection and
factual persistence do not use that count. Five policy-due rows differ overall.
This corrects documentation and does not certify allocation relationships or
reconstruct the product's parent/phase dependency graph. Both raw exports remain
private and unchanged; no production query or factual repair was used to resolve
the candidate-selection impact.
Policy A/B/C due count is 118: 33 original admitted, 1 manual, 84 unsupported.
The retained pre-live due universe was 124; six due records were refreshed.

## Offline admission

The original 202-reference manifest and its historical dependency evidence are
unchanged. A separate SHA-pinned closed registry admits 512 additional routes:
Bolton 74, Bury 35, Oldham 72, Stockport 162, Tameside 50, Wigan 119.
Each meets the existing exact HTTPS origin/path/summary/keyVal contract and
has an exact stored application ID, council, reference and source identifier.
Closed count/schema/digest, original-ID exclusion, no Trafford and council-scoped
reference/key/destination collision checks fail closed. It reuses the unchanged
Idox parser and bounded transport. This is **offline route admission**, not 512
successful live retrievals or new factual verification. The remaining 107 of
619 compatible candidates are Trafford availability residuals and not admitted.

## Fixed refresh cohorts

- Pending17: previously completeness-withheld policy-due records with retained
  literal Awaiting decision and actual NULL decision/date. Only the accepted
  unchanged pending status verification path is enabled; omissions do not prove
  authoritative NULL, and future changed/terminal evidence follows ordinary B2.
- Expanded19: 18 newly admitted currently policy-due records plus original
  Stockport78 (previous retrieval-only, no persistence). Exact current source
  evidence determines outcomes. Prior facts in manifests are reconciliation
  context, never production observations or overrides.

Both manifests are deterministic, council/ID ordered and SHA-pinned. The exact
master workflow identity selects a fixed context; there is no arbitrary manifest,
application/reference/URL input. Each manual workflow requires exact checked-out
workflow SHA, exact manifest SHA256, explicit unique authority, clean checkout,
GitHub-hosted runner, run number1/attempt1. Only live job binds the existing
stage4-production-canary environment; DATABASE_URL appears only in the isolated
live execution step. Original consumed registrations remain unchanged.

## Preserved contracts

Fresh official retrieval and independent literal exact-reference match are
mandatory. B2 remains the sole writer, with one independent application
transaction and bounded readback; no SQL repair, DDL or alternate watermark.
No automatic resume; unknown commit/safety failure stops. Ordinary local failure
continues only with unchanged prior facts, known transaction, valid audit and
closed cleanup. Preceding cohort must reconcile without safety/unknown persistence
before another cohort executes. Existing status-only consumer limitations and
coupled evidence semantics are preserved; no semantic mapping changes.

Caps remain: <=20 sequential records, <=40GET attempts, one eligible retry,
zero followed redirects, 1MB response, 20MB aggregate, 150s cumulative source,
45s worker, 512MiB/30CPU seconds per record, 300s batch/10minute job, one concurrent
DB connection and existing DB timeouts, 16KiB record/384KiB batch audit.
Audit excludes HTML, credential/cookie/header/narrative/contact data. No models or
AI regeneration; material changes preserve lifecycle/evidence_refresh consequences.

Accepted security limitations remain postgres-role credential, uninspected
privileges/no established DB least privilege, environment approval not an exact
workflow allowlist, prior private tool-record exposure accepted/unremediated,
and incomplete independent TLS verification. No credential is inspected or changed.

Registration is not a new general rollout. Production activation is bounded to
these owner-authorised current-gate cohorts after exact-head CI/review and guarded
integration with [skip render]. Trafford and other unsupported routes remain
explicit limitations to reconcile, not a scraper acquisition programme.
