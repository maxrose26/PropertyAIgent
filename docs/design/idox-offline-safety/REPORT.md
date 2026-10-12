# DA1 Idox family offline safety acceptance

Decision: **NO-GO — OFFLINE SAFETY PACKAGE INCOMPLETE for a live canary**.

This is a bounded offline safety proof, not the production DA1 adapter. Its state
machine and independent fixture deadline are implemented and tested. It has no
live transport, form-submission binding, or evidenced live result-page decoder.
A fabricated HTML contract must not be represented as working Idox acquisition.
No additional source research or transport workaround is proposed or started.

## Provenance and scope

Base: `da06dae001cbef9af6c0f38776e1fa4adfb022b3`.
Accepted preflight evidence: PR #51, `882dbe5f788598aa4e9f1dad4464b6291ebcff48`.
PRs #49, #50 and #51 remain separate unmerged evidence. This branch starts at
master and does not merge or copy their prototype history.

Sources inspected offline: `app/config.py`, `config/councils.yaml`,
`app/scrapers/idox_portal.py`, DA0 contracts and accepted preflight. No council
page was requested. Synthetic bodies are constructed in `rehearsal.page`; they
are not retained council HTML. October 1, 2026 is an arbitrary synthetic test
date, not a selected live window or a claim about applications on that date.

## Shared collector and configuration

One common state machine consumes a sealed `FixtureTape`. Every logical FORM,
SUBMIT and NEXT operation passes through `Boundary.request`. Only the exact
fixture transport class is admitted; there is no requests/httpx/browser client,
callback injection, live mode, dispatcher or registered live workflow. Logical
SUBMIT/NEXT operations deliberately do not assert HTTP methods, form action,
server-state fields or pagination routes that the retained evidence cannot prove.

| Council | Retained base | Date basis | Retained qualifications |
|---|---|---|---|
| Bolton | `https://paplanning.bolton.gov.uk/online-applications` | RECEIVED | Date form HTTP submission and result proof unproved |
| Stockport | `https://planning.stockport.gov.uk/PlanningData-live` | VALIDATED | Historical 429/navigation risk; detail pacing does not establish discovery throughput |
| Wigan | `https://planning.wigan.gov.uk/online-applications` | RECEIVED | Multiple tab URLs can share a keyVal; they are not separate applications |

All configurations are non-operational. Search path is the retained
`search.do?action=advanced&searchType=Application`. Date fields are the actual
`date(applicationReceivedStart/End)` or `date(applicationValidatedStart/End)`
configuration. No default broadening criteria or hidden server fields are guessed.
The existing generic browser scraper remains byte-for-byte unchanged.

## Window, pagination and zero semantics

Window dates must be ISO dates, start <= end, at most two inclusive calendar
days, and exactly the configured RECEIVED/VALIDATED basis. No caller search-field
map is accepted. Live dates must be separately fixed and reviewed. Conversion to
portal form date syntax, timezone/cutoff semantics and live form submission are
unimplemented because not established for a bounded HTTP route.

The synthetic page contract explicitly records page ordinal, total unique
applications, terminal flag, recognised-zero flag, candidate links and a next
ordinal. It fails on unrecognised layout, malformed/declaration-bearing markup,
repeated body, ordinal drift, count drift, overlapping pages, missing continuation,
terminal count mismatch, pages/candidates beyond limits and unknown elements.

A genuine synthetic zero requires the recognised results marker, total zero,
no candidates, first page, terminal proof and no continuation. Text such as
"No results" on an otherwise unrecognised HTML page never establishes zero.
Absence of a next link alone is not terminal proof.

All failures discard candidate/raw-evidence output. Counters and safe failure
codes survive. Partial traversal never produces COMPLETE. COMPLETE here means
complete retrieval of the synthetic tape, not a coherent live database snapshot,
source eligibility, factual freshness, or commercial opportunity coverage.
`checkpoint_eligible` is always false. No checkpoint persistence exists.

## Identity, URL and evidence

Canonical identity is `(council, exact displayed full reference)` with no new
reference normalisation. `(council, keyVal)` is only a source locator. Identical
same-page duplicates/tab aliases collapse. One key with different references,
one reference with different keys, or duplicate membership across pages fails.
Missing reference retains a qualified source candidate, emits no DA0 identity
envelope, and requires future selective detail evidence; no detail is fetched.

URI admission validates HTTPS, exact netloc, no explicit port, no userinfo,
fragment, percent-encoded ambiguity, whitespace/backslash, duplicate query key or
unexpected query/path. Relative links resolve against the retained council base.
Summary/Stockport `details` tab links may be inspected as identity metadata;
`details` is canonicalised to the summary URL and never navigated. Document,
furtherInformation, related/history/download routes are rejected. Identity URLs
cannot be used as search requests. All redirects fail; none are followed.
DNS destination validation is NOT implemented or claimed: there is no live client.

DA0 `RawEnvelope` gains one narrow common `NEW_APPLICATION_DISCOVERY` projection:
reference evidence only plus `{basis,start,end}` window provenance. Existing
status projection still requires its own factual evidence. `status_claim_complete`
explicitly rejects discovery envelopes. No new evidence model or event/persistence
engine exists. Unknown source timestamps use existing NOT_PRESENT field states.
Synthetic envelopes identify FIXTURE_EXPECTATION and UNPROVED_LIVE schema.
The DA0 import-security test adds only Python stdlib `datetime` to support real
date validation; it continues to reject transport/database/model dependencies.

## Accounting and cleanup

Every fixture operation increments requests before attempting the exchange.
There are zero retries. Redirect responses increment redirects and fail closed.
Streaming chunks count actual bytes before limit comparison, including partial
failure and the chunk that exceeds a ceiling. Content-Length is not used.
Compressed bodies and attachments are denied; no claim of compressed live wire
accounting is made. A future transport must separately prove its raw/decompressed
byte semantics and bounded read buffers. The tape is closed in finally on all
handled collector outcomes.

The fixed offline subprocess worker has an independent parent wall clock, bounded
nonblocking stdout, no stderr retention, TERM then bounded KILL escalation, wait
and pipe/selector closure. There are no temporary files or worker descendants.
The parent emits bounded failure metadata without partial artifacts. Tests cover
normal completion, exception, hung worker and output overflow. This is not hostile
process containment or a general process manager. No shared Render process is used.
No live client/session cleanup or cancellation is claimed as tested.

Closed artifact: version/config/code/time/window provenance, explicit offline
mode, completion state/reason, page controls, request/redirect/retry/body counters,
elapsed time, candidate and exact-identity counts, qualified candidates and DA0
raw envelopes, cleanup state, consistency and false checkpoint/live flags.
Encoding is sorted compact JSON with 65,536-byte ceiling. Overflow emits only
bounded failure/control metadata; no partial candidate list. Ordering is stable;
timestamp/runtime/accounting values naturally vary by execution. Normal output
contains no HTML, documents, tokens, cookies, headers, narrative or other facts.

## Offline evidence

The suite covers all 22 requested fixture categories, plus count drift,
page overlap, malformed audits, foreign transport rejection, common DA0
status/discovery separation, and child-process failure cleanup. Network connect,
connect_ex, DNS and create_connection are denied during tests; subprocess workers
install the same denial. Application/database/model/client modules are absent.
Dependency installation by Actions may contact the package registry; test code
has no council network route. No workflow_dispatch trigger is introduced.

Local combined result after audit review: **146 tests passed** (57 DA0 plus89 safety cases).
Native fixture measurement (not council throughput): Bolton/Stockport/Wigan each
2 logical operations, 1 page, 1 candidate, 231 fixture body bytes; artifacts about
2.4KB; process wall time 0.072/0.079/0.087 seconds. Hung fixture: TIMEOUT at0.502s
for a0.5s deadline, returncode-15, wait/pipe cleanup verified. Exception and output
overflow also terminate with no accepted artifact. Hosted evidence and exact
remote review are recorded in the PR/final return, never inferred from local tests.

## Proposed future coordinated canary — NOT READY / NOT AUTHORISED

Same pinned revision; exactly Bolton, Stockport, Wigan; separately reviewed tiny
fixed windows, no detail requests, no related/document capability, no retries or
followed redirects. At least one case must exercise real pagination; an all-zero
or all-single-page result cannot certify pagination. A council retrieval/layout
failure may allow the next isolated council only if global safety remains intact.
Any origin escape, accounting bypass, output/privacy violation, uncontrolled
network/process or global budget violation stops the whole run. No adaptive
window expansion or retry is permitted.

Provisional **rejection ceilings**, not measured live requirements:

| Resource | Per council | Coordinated run |
|---|---:|---:|
| Attempted HTTP operations | 6 | 18 |
| Accepted result pages | 2 | 6 |
| Unique source candidates | 100 | 300 |
| Body bytes per response | 1,000,000 | same |
| Body bytes including failures | 2,000,000 | 6,000,000 |
| Redirects followed / retries | 0 / 0 | 0 / 0 |
| Connection / read timeout | 3s / 8s | same |
| Independently supervised worker | 30s | 100s total with cleanup |
| Audit bytes | 65,536 | 196,608 max |
| Outer hosted job | — | 3 minutes |

These are small rejection boundaries informed by the intended 1form +1submit +
1next shape, not promises that real Idox traffic fits. No page-size/sort/detail
calls are assumed; any future required request must be counted inside the same
ceiling. Current package enforces the per-council fixture ceilings; no live
coordinated budget implementation or launcher is claimed.

Preferred future execution remains a disposable GitHub-hosted ubuntu-24.04 job,
pinned code, contents:read, no credentials/database/models, final runner disposal.
Only the existing offline PR/push verification is extended here. No live workflow
is registered. Rights, freshness latency and long-term change completeness remain
separate unproved gates even if a future tiny transport canary succeeds.

## Exact blockers and recommendation

1. The existing accepted Idox browser interaction does not establish the HTTP
   request method/action/server-state contract for bounded date-window submission.
2. Current retained bodies do not establish a real parser for recognised result,
   total/page/continuation and terminal-zero proof across the three configurations.
3. No live transport binds these operations to streamed request/body accounting,
   DNS admission and independently cancellable sessions. Synthetic counters are
   not evidence that all real outbound operations are intercepted.

Therefore **NO-GO**. Review can accept this offline proof as durable evidence, but
must not authorise a live canary on it. No speculative protocol implementation,
second browser scraper, source experiment or further architecture research began.
Any next decision must explicitly address these narrow protocol/evidence gaps;
this package does not expand authority to obtain that evidence.

## Independent review correction

The first remote checkpoint was independently fetched and reproduced at136 passes.
Adversarial review found insufficient audit reconciliation: a zero-result label
could carry a candidate, successful counters could be zero, and envelope source
URLs/keys could differ from their candidate. A genuine follow-up commit adds
completion/counter invariants, envelope source/key/URL/window/code/accounting
linkage, fixed failure reasons and timestamp/field-locator validation with ten
new rejection tests. These changes do not bind or enable live transport.
