# Stage 4 direct-reference refresh MVP — offline candidate

Master Stage 4 remains OPEN. Current gate: known-reference planning refresh.
Next gate: REVIEW decision on bounded live acceptance. No live requests or live
workflow dispatch are implemented or performed by this candidate.

## Candidate scope and retained manifest

Base: d253773a09690f27b150adb701c95f9aa3ee210f. Exact published head/tree and hosted
results are reported in the PR handoff; this file cannot contain its own commit hash.

`manifest.json` SHA256:
`ce143eafd498e89129965d098b2f820295fa1d1e1b4d9458f5d9209543071dde`.

Frozen selection is the accepted retained L1 status manifest excluding cohort 5:
202 exact application/council/reference identities, joined to the 9 October census.
The manifest includes source URL/identifier, site identity, retained status,
decision/date, successful-verification provenance, cohort/reasons and consumer/
dependency roles. It is an initial establishment cohort, not a polling schedule.
No contact, applicant, address, document body or private database export is included.

| Council | ADMITTED_DIRECT_ROUTE | MANUAL_FALLBACK_CANDIDATE | UNSUPPORTED_ROUTE | Total |
|---|---:|---:|---:|---:|
| Bolton | 13 | 0 | 0 | 13 |
| Bury | 5 | 0 | 0 | 5 |
| Manchester | 0 | 0 | 37 | 37 |
| Oldham | 20 | 0 | 0 | 20 |
| Rochdale | 0 | 2 | 16 | 18 |
| Salford | 0 | 2 | 29 | 31 |
| Stockport | 34 | 0 | 0 | 34 |
| Tameside | 7 | 0 | 0 | 7 |
| Trafford | 19 | 0 | 0 | 19 |
| Wigan | 18 | 0 | 0 | 18 |
| **Total** | **116** | **4** | **82** | **202** |

INSUFFICIENT_RETAINED_EVIDENCE=0 and DEFERRED_BY_ACCEPTED_FAILURE=0.
The latter does not erase historical failures: search-form failures do not apply
to this direct-destination route. Unsupported Arcus transport remains explicit.
Idox=116 offline admissions. Arcus=86, of which four have historical manual-summary
observations; none has an admitted automated direct route. Manual provenance is
retained in the accepted Stage26A source index hashed by the manifest.

ADMITTED means only that the implementation enforces the offline exact-destination
transport/parser contract. It does NOT mean the council page works live. Each row
has its disposition/reason. No live automated coverage count is claimed.

## Shared semantics and family reuse

One Idox implementation reuses Bolton's accepted summary-table parser and semantic
guard, without Bolton's two-case allowlist. Each admitted URL must exactly match
its council origin/path and retained key; only GET of that URL is possible. No
search, redirect following, further-information, document, related-case, asset or
browser requests are supported. A source body must independently contain exactly
one literal matching reference. Wrong, absent, duplicate or ambiguous identity
fails closed. Retained URL identity alone is insufficient.

Arcus's existing detail flow relies on search-supplied identity and dynamic browser
behaviour, and can enter Files. No direct contract is inherited from it. That branch
stops at UNSUPPORTED_ROUTE/manual candidate; no new Arcus engineering is started.

Literal status/decision/date are retained independently of normalized evidence.
PRESENT_VALUE, PRESENT_BLANK, NOT_PRESENT, CONFLICTING and UNPARSEABLE are preserved
in observations or rejection diagnostics. Optional missing labels permit literal
source observation, but do not establish NULL or semantic completeness. Deposited
stays UNKNOWN_UNMAPPED. No new status mapping or date parser is introduced.

The existing date parser accepts only its known formats; other literal dates are
UNPARSEABLE, not silently normalized. Only minimized factual fields and a body hash
leave parsing; unrelated labels/HTML, cookies and raw error text are excluded.

## B2 integration and important limitation

The existing `verify_application_status` owns the snapshot, guarded reservation,
shared upsert, lifecycle/material signal and commit. An additive evidence-loader
seam runs AFTER that prior-state snapshot. Existing callers keep their old path.
The existing shared upsert gains a default-off status-only mode for this seam;
it updates only status/decision/date and never copies or overwrites unit counts,
confirmation, classification, URLs, batch identity or other ancillary metadata.
No second writer, schema or persistence mechanism exists.

Direct-route material-change comparison uses the same post-refresh unit count on
both sides: an unrelated concurrent count update is not attributed to status evidence.
The old guarded status/decision snapshot is preserved for comparison.

B2 still has a coupled successful-verification watermark, not field-level verified
watermarks. Consequently omitted optional fields, unmapped semantics, or blank
fields that would contradict retained nonblank facts are SOURCE-ONLY observations:
`literal_verified=true`, `accepted=false`, handoff PARTIAL_RETRIEVAL, and no stamp.
This is a deliberate safe rejection, not a claim that literal retrieval failed.
The retained Oldham24 summary directly exercises this limitation. Extending B2 to
persist partial literal observations is not silently implemented.

Mapped complete evidence demonstrates unchanged/material/non-material outcomes;
rollback, stale response, lost acknowledgement and retry remain B2 responsibilities.
PERSISTENCE_FAILED after a lost acknowledgement means uncertain commit state, not
an assertion that the server could not commit. Retrying is idempotent.

## Bounds and cleanup

| Bound | Contract |
|---|---|
| Requests | At most 2 attempts/reference; 40/invocation; default HTTPS adapter retries disabled |
| Redirects | Zero; even same-origin redirects fail closed |
| Retries | One transient retry; zero retries for 429/403/404/redirect/parser failures |
| Response body | 1,000,000 bytes, streamed in at most 16,384-byte chunks |
| Reference body | 2,000,000 bytes across attempts |
| Whole invocation body | 20,000,000 bytes; at most 20 references; sequential use |
| Socket timeouts | Up to 3s connect and 8s read, reduced to remaining budget |
| Cooperative deadlines | 40s/reference, 150s/invocation; check before/after parsing and between chunks |
| Parser | At most 20,000 tag openings and 256 rows; no scripts or remote assets |
| Disposable worker | Independent 45s wall deadline, 512MiB address-space ceiling, 30 CPU seconds |
| Audit | At most 16KiB for the worker's one-reference result |

Response budgets are yielded HTTP BODY bytes, not total TLS/socket/header traffic.
A rejected HTTP response is closed without consuming its body. Byte counters cannot
certify unread/buffered bytes after interruption. No OS-level network isolation is
claimed for future live execution. Offline tests use the existing syscall-level
network-denial launcher; the standalone synthetic worker uses the accepted offline
network guard. Production credentials are not supplied.

The 1MB page ceiling exceeds retained summary sizes (~35–63KB) substantially. A
single GET avoids search/browser assets. Zero redirect policy is deliberate because
this slice admits exact destinations only. A live redirect becomes an explicit
limitation rather than permission to broaden the route. No live measurement is
claimed. The generic ceilings are not a 202-row batch authorisation.

Responses and sessions close in finally blocks, including interruption. The offline
worker reuses the accepted disposable Actions process-group supervisor, temporary
artifacts and minimal environment. Expired/failed workers produce no accepted success;
interrupted accounting is UNKNOWN. No shared-Render hostile-descendant work is added.
The worker proves one-reference containment; the 150s/20-reference budget object is
not a tested full batch orchestrator or whole-GM/process-tree acceptance proof.

## Offline evidence and regressions

Focused tests enumerate all 202 dispositions and exercise every Idox tuple with
explicitly synthetic summary responses. They cover identity, literal/semantic and
optional fields, conflicts, parsing, request/byte/time limits, rate limits, transient
retry, privacy, cleanup, direct B2 unchanged/change/retry, failure preservation,
concurrent metadata preservation and stale status rejection.

`retained-summary-24.json` is a field-minimized retained source projection with the
original body hash; it is not a full transport fixture. Synthetic coverage is never
reported as source compatibility.

Hosted workflow `stage4-direct-reference.yml` runs network-denied focused plus
B2/B2.1/L1/Bolton/status and Stage1 outbound/access selections, then the ordinary
supervisor rehearsal. A separate disposable PostgreSQL17 job runs existing B2 native
recovery/concurrency tests and the new direct retrieval-to-B2 transaction rehearsal.
It exposes no live dispatch. No model calls, production databases or council access
are required. Exact results belong to the remote candidate's handoff.

Independent review required the concurrent-count attribution correction and explicit
resource/partial-field qualifications above. No accepted assertion is weakened.

## One proposed subsequent live canary — NOT EXECUTED

Disposable GitHub-hosted runner only, exact REVIEW-approved candidate SHA. A separately
reviewed live registration is needed; this candidate intentionally has no live CLI
or live workflow. No database connection, B2 persistence, search or documents.

1. **Oldham FUL/355686/26**, application42/site28:
   `https://planningpa.oldham.gov.uk/online-applications/applicationDetails.do?activeTab=summary&keyVal=TA7382MCIP700`
   Retained contradiction makes a direct status read valuable. Historical refusal is
   a dated expectation, never forced onto current contrary evidence.
2. **Bolton 00307/26**, application202/site129:
   `https://paplanning.bolton.gov.uk/online-applications/applicationDetails.do?activeTab=summary&keyVal=TAPAO1DEGJP00`
   Retained Deposited/optional-label case tests successful literal evidence with
   UNKNOWN semantics and withheld B2 acceptance.

Both use the sole admitted Idox family but exercise distinct acceptance outcomes.
Arcus is not probed. Two cases do not prove all seven Idox councils or ten-council GM.

Proposed aggregate limits: 4 GET attempts, 0 redirects, at most one transient retry
per reference, 1MB/response, 2MB/reference, 4MB total body, concurrency1, independent
45s/reference and 100s acquisition supervisor ceiling, 3-minute job ceiling including
setup with refusal if setup leaves insufficient budget; 512MiB/30CPU worker limits.
At most 32KiB combined factual audit. No auth cookies, credentials or model budget.

Success: both identities independently agree; fields/states and accounting are
complete within bounds; ordinary cleanup succeeds; literal-only vs B2-eligible is
honest. A changed current decision is reported, not fitted to historical fixtures.
A literal-only success does NOT certify the integrated writer works on that page.

Stop on first identity conflict, access/rate failure, redirect, partial body, parser
failure, resource ceiling, interruption or invalid audit. Do not try another source,
search form or council. Preserve failure accounting/UNKNOWN without successful stamps.
The live run is read-only; B2 acceptance stays disposable/offline at this next gate.

## Remaining scope and authority

Stage4 stays OPEN: 86 initial references lack an admitted automated path; all116
admissions still lack live compatibility evidence; partial source observations may
remain ineligible for B2. Full GM coverage, the wider538 admission review, approved
cadence and new-major/material discovery remain separate outstanding requirements.
Known-reference refresh precedes discovery; no frozen inventory is called final.
Stage3 acceptance and AH/security boundaries remain unchanged.

Request only REVIEW assessment of the exact offline candidate and its bounded live
canary design. Live registration/execution, merge, deployment and production writes
require their separate authority. No supplier work, scheduling, new source research,
Stage5+ work or live activation was performed.
