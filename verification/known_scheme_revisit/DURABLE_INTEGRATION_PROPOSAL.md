# Durable revisit integration — boundary review

30 September 2026. Inspected exact offline checkpoint
33af977f669f60b2d2e046b6f6a0804f53f81d21; initially clean tree.
Status: STOPPED BEFORE RUNTIME/SCHEMA IMPLEMENTATION under the user's explicit
migration/release-contract review condition. This document is a proposal.

## Concrete boundary found

scripts/migrate_p0a.py declares TABLE='parent_lookup_work' and
COLUMN=('scrape_runs', 'progress'). verify_definitions iterates all shared
Base.metadata tables and allows only those missing objects. Adding revisit
models to Base would make the existing P0-A preflight reject the unmigrated
schema. Enlarging that allow-list would broaden the exact approved migration.
Putting production models in hidden separate metadata merely to avoid this
verification would not resolve the release-contract decision.

app/pipeline/discovery_owner.py::reconcile_owners and
release_interrupted_work enumerate ParentLookupWork only. New durable in-flight
work cannot claim to participate in successor/reaped-child recovery by reusing
its run ID alone. No time-based lease replacement or new scheduler is proposed.
The inherited descriptor/owner verification, terminal_evidence requirements,
sole owner, fail-closed scheduled identity and activation switches must remain
unchanged. A narrowly reviewed recovery participant or explicit stage recovery
protocol is needed before concurrency/recovery can be asserted.

The existing AH disposable PostgreSQL authority verifies AH-specific names and
catalogues. It is not evidence of approval or verification for new revisit DDL.
Reuse its isolation principles, but review a separately scoped revisit test
manifest and schema allow-list; do not silently expand AH schema authority.
No PostgreSQL server installation or execution was attempted for this review.

## Minimum proposed additive schema

No alteration/backfill of existing Document, AH claims, SchemeIntelligence,
buyer profiles or stored evaluations. Five conceptual tables, names provisional:

| Table | Identity and purpose |
|---|---|
| revisit_work | Unique council + canonical reference + stage + route. Optional resolved application FK must agree with council/reference. Current cycle/generation, cursor/snapshot, last attempt, last complete success, next due, failure count, outcome, deferred reason, owner ScrapeRun and reservation generation. Due index on council/due/last attempt. |
| revisit_attempts | Unique work + cycle + reservation generation. Retains requested coverage, initial/final cursor, owner invocation/run, start/end, outcome, request/byte/new/version counters, errors and deferrals. Finalised outcomes immutable; earlier successful cycles remain visible. |
| revisit_content_versions | Immutable application-scoped logical document identity + SHA256 bytes, unique within that scope. Bounded byte body stored transactionally for this first local implementation; no mutable local_path as sole evidence. Digest checked against bytes. Storage cap required before any production sizing. |
| revisit_document_observations | Immutable attempt + response token + item identity, linked to content version when a complete body was obtained. URL/title, issue/publication/observed times, stage, validators, full-body verification time, unavailable/deferred reason and unreviewed evidence metadata. Unchanged successful fetch adds an observation but no new content bytes; reverting to an older body references that version in a new observation. |
| revisit_relationship_observations | Immutable source council/reference, target council/reference, relation type, route, supporting source/citation, observed time, confidence and initial review state. Idempotent per attempt/response/edge. Candidate review is initially read-only; any later review appends an event under a separately reviewed workflow. No automatic selected AH or legal status updates. |

Important refinement of the offline model: an observation is not a content
version. Repeated bytes share immutable content storage but retain successful
check evidence; metadata/stage changes create observations, not fake byte
versions. Stages with unseen bodies cannot claim a new full-content check.
Application/site membership never confers shared operative terms.

## Transactions and crash behaviour

1. After real child admission, reserve bounded due work in a short transaction:
   validate the running council ScrapeRun and owner invocation, conditionally
   advance reservation generation, create attempt, record last attempted time.
   One active reservation per work. No database transaction spans portal I/O.
2. Fetch one bounded response/body outside the transaction. Count bytes while
   streaming, including decompressed bytes; reject oversize/incomplete content.
   Do not use the existing path-based downloader cache as fresh body evidence.
3. In one short commit transaction, lock the work row, verify reservation
   generation and still-current run/owner, insert versions/observations/edges
   and any verified child work, then advance cursor and finalise coverage.
   Completion and evidence cannot become durable separately. Use the existing
   transaction-local timeouts, reapplying after rollback. Explicit foreign keys,
   uniqueness, scope checks and append-only protections form the release schema.
4. A failed request records partial coverage/backoff in a separate bounded
   outcome transaction. A database failure leaves no completion; the active
   reservation requires approved terminal recovery. Never claim the failed
   response was checked because the failure log itself committed.

| Failure | Required behaviour |
|---|---|
| Crash after body fetch, before persistence | Discard uncommitted buffer. Same cursor remains pending; successor may refetch under its next allocation. Attempt shows interrupted/unknown, not unchanged. |
| Crash during commit | All observation/frontier/cursor changes roll back together, or all are committed. Query the idempotency token before refetching after ambiguous commit acknowledgement. |
| Crash after commit, before acknowledgement | Successor sees committed response token/cursor; duplicate persistence is a no-op. |
| Competing local worker / stale child | Reservation CAS and owner-conditioned locked commit reject stale generation; no unrelated process gets portal admission. PostgreSQL race tests supplement, never substitute for, real P0-A admission. |
| Successor | Reuse only verified existing terminal-owner/reaped-process evidence. Atomically finalise interrupted attempt and release reservation; no elapsed-time stealing. Implement only after the recovery hook decision below. |
| Unchanged content | Reuse bytes row; record successful observation and full-body check timestamp. Preserve prior versions and proposal/decision stages. |
| Inaccessible final notice | Register observation may succeed; required body/legal coverage remains partial. Do not promote proposed social rent to operative terms. |

## Proposed adapter and bounded allocation

Use Idox's existing document-register parser and reference-search parsing,
with recorded HTML and streamed body responses at the transport boundary.
Existing search_related_applications currently performs broader search/detail
work; the integration needs a page-sized adapter result with explicit next
cursor or restart-and-dedup semantics. Do not wrap its full traversal and call
it one bounded step. Search routes remain citation search unless an actual
Related Cases parser is implemented and tested separately.

Required recordings: unchanged summary/new statement; same URL/new bytes with
misleading validators; variation-only citation leading to discharge; final
notice failure; Stockport Hyde references and cross-council negative control.
No new live capture is authorised. Constructed HTML must be labelled synthetic,
not described as a captured portal response. Check whether adequate historical
captures exist before making adapter compatibility claims.

Preserve accepted fixture limits as test parameters: eight logical responses,
two per council, 4096 bytes per response, 16384 total body bytes, 32 work
identities. These tiny bytes are test limits, not useful PDF production limits.
Require a request cap as well as logical response cap: redirects and retries
consume it; no same-slice transient retries. Retry next cycle after 1/2/4/7 days
with longer Retry-After respected. Oversize/budget deferral is not a portal
failure and does not erase earlier progress.

Within the admitted child, allocation must end before the effective existing
council/invocation deadline, reserving cleanup margin. New-application discovery
gets its existing finite allocation before a capped revisit slice; neither a
revisit backlog nor new-discovery backlog can claim the entire remaining budget.
This requires a reviewed stage allocation point: simply appending revisits after
an unbounded stage does not prove fairness. Keep supervisor council order and
hard deadlines unchanged. If enforcing the split requires watchdog/admission
changes, stop again rather than silently extend P0-A.

Count every full-body revalidation against byte/request budgets even when the
content is unchanged. A 304 can record validator observation, not refreshed
full-content verification. Scheduled body verification remains due until bytes
are read successfully; oversize files show deferred/unverified, with no false
complete badge. No live PDF size allowance or cadence is approved here.

## Tests required after design approval

Use the proposed release models/DDL and real disposable PostgreSQL, not substitute
DDL or SQLite concurrency. Runner creates isolated cluster/database/restricted
role, rejects inherited production inputs and repository environment files,
verifies cluster identity before schema writes, records dependency versions,
and shuts down its cluster. Do not reuse prior AH PostgreSQL passes as evidence.

Focused tests: atomic checkpoint rollback at each insertion boundary; immutable
versions; same-content and ambiguous-commit replay; connection recovery;
concurrent reservation/stale-generation commit rejection; proven terminal
successor and unresolved-owner rejection; final notice partial coverage;
recorded/synthetic-labelled Idox pages through actual parsing; stream-byte cap,
lying validators, no cache shortcut; mixed new/revisit work and multiple councils
under finite deadlines. Assert earlier successes survive later failures and
remaining work is reported. A supplied-response loop alone does not prove these.

No new tests run for this documentation-only boundary review. The accepted
27-test result belongs to 33af977; no durable integration pass is claimed.
Production workload/cadence remain unmeasured. No read-only production access
was attempted because the migration/recovery decision is the blocking boundary.

## Concrete decision requested

Approve a separate LOCAL revisit schema/migration artifact for exactly the five
conceptual tables above and a narrowly scoped recovery participant, while keeping
the original P0-A migration allow-list and owner/admission semantics fixed. Review
how the P0-A schema verifier composes with the new artifact (including pinned
metadata/version expectations) before changing shared models. Permit disposable
PostgreSQL application of that exact artifact solely for tests. Approve an
explicit capped child-stage allocation and page-sized Idox adapter interface;
no activation or general crawler. If that cannot be achieved without altering
P0-A admission or hard-deadline contracts, return the precise difference for review.

This is the smallest useful next decision: storage and recovery together.
Implementing tables alone would leave stranded in-flight work; wiring the stage
alone would falsely imply crash durability. Production migration, P0-A release,
live portal trial, workload measurement, cadence and stored buyer refresh remain
separate gates.
