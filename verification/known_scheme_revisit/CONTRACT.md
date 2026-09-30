# Offline known-scheme revisit contract

Approved review base: 826045d0633b8074e8264ddf12dffdeffd60dbc0.

## Boundary, before implementation

This increment is a pure offline reference model consuming supplied fixture responses. It has no portal, database, environment, AI, scheduler or production entry point. It is not a second operational queue. No existing P0-A code, ownership, admission or release contract changes. Future integration must execute under the existing admitted council child, inherited owner lock and watchdog; it may not acquire a separate owner, use a time lease, or bypass scheduled identity verification. That integration and additive persistence remain unimplemented and require review. If the existing child cannot host a bounded stage without changing admission/ownership, stop for review.

The reference model demonstrates the stage's checkpoint/outcome contract, not live adapter correctness, transactional database durability or P0-A release readiness. Its JSON-serialisable state is round-tripped in fixtures. Future persistence must atomically commit an observation, newly discovered work and cursor advancement in the admitted child's transaction. Existing owner reconciliation must precede recovery; time passing never authorises stealing in-flight work.

## Work and limits

Work identity is cycle + council + canonical application reference + stage + route. Canonicalisation reuses P0-A reference_key (strip/casefold); no address, proximity, site ID or guessed punctuation aliases. Stages: document-register/body observations and related-reference search. Each cycle is an explicitly supplied bounded set; no schedule or automatic recurring enqueue. Successful earlier-cycle observations survive later cycles.

Caller supplies the council order produced by the P0-A supervisor (least recently attempted), and an explicit stage allocation within its existing council/run deadlines. Offline selection models one reserved slice per council, oldest stage attempt first; a stalled application cannot consume another council's allocation. Limits: logical response steps per cycle call, per council, body bytes per response, total body bytes per call, and total work identities per cycle. No network/time guarantee is claimed by a fixture step: production requests must additionally consume the existing stage deadline/watchdog, HTTP timeout and memory budget. Oversized responses remain partial; no truncation recorded as success.

A cursor identifies the next adapter page/item, within a stable snapshot if the portal supports it. Otherwise a restart re-lists and content/edge deduplication absorbs replay; adapter cursors must never be assumed stable across changed registers. An applied cursor token is idempotent. Progress is committed only after the complete response is accepted; an interrupted uncommitted response is replayed. Backoff is 1 day after the first failure, exponential to a 7-day cap, with a longer server Retry-After respected. No same-call retry. Budget deferral does not increase failure backoff. Work that exceeds the frontier cap stays at its cursor for explicit resumption with a reviewed larger slice; report it, never silently discard children.

## Evidence and completion

Every revalidated document supplies full bytes. ETag/Last-Modified, URL or 304 alone cannot establish content equality in this model; unavailable body is partial and pending. Production adapter design must force a bounded unconditional fetch when validators cannot establish a verified body; it cannot reuse the old downloader cache. SHA256 compares bytes. A changed body creates an immutable version observation including application, URL, issue/publication/observation dates and stage; earlier versions remain. Identical bytes create no duplicate version; a later return to earlier bytes is a new chronological observation. No parsing accuracy is asserted: proposed fields supplied by fixtures are unreviewed evidence, never selected planning truth. Same bytes with changed scope/stage/date/proposed fields also preserve a new observation. No intelligence/current AH field is updated.

Related edges retain type, route, confidence and supporting citation. Only explicit, same-council verified references seed further checks. Address-only, cross-council or unsupported relation types stay review candidates. Even verified edges never copy AH claims. An empty complete citation-search page means route complete only, not universal related-case coverage. Unsupported routes remain explicitly unavailable/partial.

Per work: last attempt, last successful complete check, cursor, completed response tokens, new/revised document counters, failure count, next eligibility, outcome and reason. Partial/failed/deferred work preserves prior success. Per-application coverage is complete only for all requested stages/routes in that cycle; omitted routes are not asserted checked. Aggregation retains each council/application outcome, never substitutes council success for application coverage. Historical cycle results remain available.

## Measurement and approval gates

Fixture workload is measured from explicit work and response counts, not production throughput. Production monitored count, document volumes, relationship volume, cycle duration and deferred backlog are unmeasured: this increment has no authorised production metadata connection. Weekly/monthly cadence remains a hypothesis until inventory and bounded runtime measurements support it.

Future additive migration needs: stage work/checkpoints, document version/observation storage, typed related-edge provenance; exact schema and atomic ownership-conditioned writes need review. Do not overload ParentLookupWork, mutate Document in place, or auto-import AH claims. P0-A release/admission, persistence review, adapter capture tests and bounded live pilot approval all precede activation. Stored buyer refresh remains deferred; no fingerprint or new observation triggers a paid evaluation.
