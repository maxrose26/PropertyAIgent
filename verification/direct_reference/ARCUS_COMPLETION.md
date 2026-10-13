# Stage 4 known-reference completion with Trafford deferred

Authority: Product Owner instruction of 13 October 2026, “Complete Stage 4
known-reference refresh with Trafford deferred”. It supersedes the earlier
requirement for ten operational councils at this sub-gate. Master Stage 4 stays
open; discovery and model/intelligence work are not authorised here.

## Scope and truthful acceptance

The closed manifest contains 57 retained policy-due applications: Manchester 22,
Rochdale 18, Salford 17. Rochdale application 1100 remains a separate manual
candidate. No Trafford application is admitted. Validation uses already-qualified
688 / 142419/FO/2025, 295 / 25/01149/FUL, 252 / PA/2025/1084. Six disjoint groups
of nine cover the remaining 54; no historical expansion or automatic retry.

The existing guest HTTP exact-record reader supplies facts. The existing bounded
browser worker obtains the ordinary page's transient guest request context; it
does not substitute DOM/navigation text for independently displayed exact record
identity. Only the already-qualified read methods are replayed. Council
configuration and a closed reference-derived Salford navigation path share one
transport. Missing status/decision does not disqualify a supported decision date.
Unqualified status vocabulary is never promoted to a supported status.

B2 remains the only factual writer. The additive nullable TEXT column
`planning_field_verification` records per-field state, literal/normalized value,
source URL, response hash, observation scope and field verification timestamp.
The date-only scope changes decision date and its provenance atomically through
B2; status, decision, coupled status watermark and last-seen time are unchanged.
Unverified observed status/decision literals retain their states but receive no
verification timestamp. A value-bound accessor rejects stale metadata after a
later date change. Existing stale-response CAS protection includes the field
metadata. Existing lifecycle/date-correction/evidence-refresh consequences apply.
No backfill, parallel persistence system or manual factual SQL.

The one-off runner checks the exact clean integrated SHA, workflow/ref, first run
and first attempt. It adds only the nullable provenance column, reads its schema
back, then performs three representative B2 validations. Catch-up requires all
three validations to commit with bounded matching readback in that same run.
Source failures and withheld fields are explicit outcomes. Any uncertain commit,
audit/identity/control failure stops; there is no uncertain-commit retry.

Each batch retains the existing 300-second bound and starts no record without
its full allowance. Each source has 80 requests, 20 MiB observed payload, one
page, two navigations, 45 seconds and 1 GiB aggregate observed owned RSS. The
75-second database-worker envelope allows transaction/readback and cleanup; it
does not increase the source deadline. This Arcus invocation alone uses a
60-second idle database transaction timeout to span the 45-second source deadline
and cleanup; existing Idox defaults remain 40 seconds. Concurrency is one. Byte accounting has
the limitations documented in INSTRUMENTED_PROBE.md; no full wire-byte claim.
Source children receive no database/model/GitHub credentials. Audits contain
planning fields only, not raw HTML, contacts, cookies or tokens.

Separate outcomes: FULL_FACTUAL, STATUS_ONLY, FIELD_LEVEL_VERIFIED, WITHHELD,
SOURCE_FAILURE and UNSUPPORTED. Date-only verification does not count as status
freshness or full verification. Individual safe failures may remain at the pilot
sub-gate. Nine councils must have operational truthful routes; Trafford is the
explicit council-level exception.

## Retained Trafford evidence — no further execution

Ordinary interactive access worked, but tested bounded automated environments did
not establish an operational route. Existing Render job
`job-db7a8rivcj2c73cs0j70` on `crn-d9sv93vavr4c73f98rb0`, launcher revision
`1255ad651151d0c44116a4d05f4f28e472b2115a`, timed out on its initial entry-page
request: one request, zero responses/observed bytes, no verified reference or
facts. Supervisor elapsed 13.629 seconds; peak owned RSS 577728512 bytes;
eight processes observed, zero live survivors, cleanup CLOSED. This establishes
an environment-specific failure, not permanent source unavailability.

The owner confirmed temporary Render CLI revocation. No further Trafford calls,
jobs, credentials or infrastructure are authorised. The cron remains suspended,
normal command /bin/true and auto-deploy off. Retained launcher and earlier
browser/HTTP evidence remain for a genuinely new future route hypothesis.

## Candidate versus production evidence

Implementation and offline tests are preparation, not production qualification.
Exact-head hosted checks and independent review must precede guarded integration
with [skip render]. The manual production workflow then generates schema,
validation and catch-up audits. Until those audits exist, do not claim any new
production refresh or nine-council operational acceptance. No deployment occurs.

After acceptance, the next Stage 4 requirement is new/material application
discovery, including retained committee/publication evidence. Do not start it.

The archived owner launcher payload remains tied to revision 1255ad6. Do not
regenerate or execute the current historical Render packager: the newer worker
has Arcus manifest dependencies outside its old two-file payload. Any future
Trafford task must explicitly reconcile this dependency before execution.
