# Four-council proof retention and source-only recovery proposal

Stage 4 OPEN. Offline candidate only: no merge, installation, registration,
source execution, production access or stop change. All future execution limits
below are PROPOSED, not issued authority. No Bolton work is included.

Baseline master `e08a316cc6473f9d0b172b359577821cadf29883`, tree
`d8a78a1e055a87483a146ba70191a75bed58cb42`. Open PR/worktree inventory was
checked before edits; existing specification/proposal branches are unchanged.
The draft PR records the exact final candidate/tree and hosted check identities.

## Controlling contracts and minimum change

Specification 029, **Completeness and identity**, **Persistence**, **Acceptance**
and **Boundaries**, controls window claims, admission and the later campaign.
Specification 032 supplies bounded source/process/authority contracts.
Specifications 033 and PR179 do not make a partial observation complete and
are not extended here. PR178's complete-receipt admission seam is unchanged.

The current readers gain an explicit `retain_proof=False` selection. Enabled
selection requires exactly one of the following tuples, with zero Idox retries:

| Council | Date basis | Inclusive interval | Existing route |
| --- | --- | --- | --- |
| Bury | RECEIVED | 8–14 October 2026 | `https://planning.bury.gov.uk/online-applications/search.do?action=advanced&searchType=Application` |
| Rochdale | VALIDATED | 8–14 October 2026 | Existing `dated_config(ROCHDALE, '2026-10-08', '2026-10-14')` ordinary public `/pr/s/register-view` on `account.rochdale.gov.uk`; unchanged observed URL filter structure, not a constructed RPC |
| Tameside | RECEIVED | 1–7 October 2026 | `https://publicaccess.tameside.gov.uk/online-applications/search.do?action=advanced&searchType=Application` |
| Oldham | RECEIVED | 8–14 October 2026 | `https://planningpa.oldham.gov.uk/online-applications/search.do?action=advanced&searchType=Application` |

Implementation reuses `finite_acceptance.read`, `idox_window`/WindowBoundary,
`arcus_ui_window.enumerate_ui`, `instrumented_probe.supervised`, existing safe
transport facts, source counters, process cleanup and existing audit publication.
No parser acceptance condition, source limit, writer, schema, SQL function,
role, privilege, policy, grant or registration is changed.

## Question → retained evidence

| Council/question | Added proof | Claim boundary |
| --- | --- | --- |
| Bury: were dates applied; where is count/terminal proof missing? | Fixed date-control counts and equality with requested dates; heading/container/row counts; bounded pager count triples and Next counts; selected reference-sort/page-size values; existing source page/refine hashes. | No pager/count remains missing proof, never a short-page completion rule. |
| Oldham: what result/error/zero and sort structure was present? | Search response hash; fixed result-heading, message-box and exact known zero-literal counts; sort-control counts and selected allowlisted values; failure operation. | No selector is not zero. Unknown page wording remains unknown; arbitrary source/error text is never exported. |
| Rochdale: what did rendered locators expose when the operation timed out? | Existing Playwright piercing locators for result markers, cards, exact zero literal, Next and applied/blank/category controls; bounded control visibility; MATCH/MISMATCH/ABSENT/AMBIGUOUS/UNAVAILABLE/NOT_ATTEMPTED states; operation/time and sanitized hash. | Not `page.content()`: serialized light DOM can omit shadow content. No clicks, retries or navigation. No Manchester zero qualification. Locator state does not retroactively establish applied criteria. |
| Tameside: did the request fail, or did returned markup fail parsing? | Existing fixed HTTP/media/redirect/rejection fields at SORT_REQUEST; projected response structure if the existing boundary returns an accepted body; explicit unavailable response evidence otherwise. | The pinned request boundary discards rejected HTTP bodies. A 403/429/502 may have a body upstream but its body/hash is UNAVAILABLE to this projection. No invented empty-response hash or parser diagnosis. |

### Evidence format, safety and integrity

`FOUR_COUNCIL_STRUCTURAL_PROOF_V1` retains only integer counts, booleans, fixed
states and a small set of selected sort/page-size literals. No hidden control
values, token/cookie/header values, URLs, applicant/contact values, arbitrary
exception text or full response bodies enter the proof.

Each event records UTC observation time, operation and projection version.
Idox retains original response SHA256 separately from sanitized evidence SHA256.
Rochdale's locator snapshot is explicitly **not an HTTP response or raw DOM**:
original response and raw DOM hashes/byte counts remain unavailable, while the
sanitized projection has its own hash. No response hash is fabricated from
projected text. Enclosing council/date scope and existing Idox response
provenance are checked at export/read boundaries. These are integrity checks,
not a provider signature or independent confirmation of source truth.

Absent, empty, invalid-encoding, oversized and partial/unavailable locator proof
are explicit. The 500ms local locator-collection deadline is included inside the
unchanged worker/supervisor time; it does not replenish a source allowance.
Rochdale evidence failure sets a fixed failure and cannot qualify COMPLETE.
Proof-mode listing exceptions export fixed codes only; legacy default output
is preserved. Export is exclusive, bounded, flushed and read back; write or
readback failure removes the owned partial file or reports cleanup uncertainty.
A nonzero proof worker exit is not accepted as successful completion.

Internal proof ceiling: 24KiB / 12 events. Per HTML projection: at most 500,000
bytes and 20,000 markup openings; at most four pager/visibility controls. This
is proof-processing headroom, not a larger source response limit. It must not
silently truncate. The overall audit remains within the existing Idox 512,000
byte and non-metadata Arcus 65,536 byte worker bounds. Requested 512KiB per
observation / 2MiB combined are outer maxima: **the existing lower bounds win**.
If a normal audit no longer fits, stop and retain the gap; do not increase a cap.

## Existing evidence preserved

- Bury run38731487848: five references, applied dates, TOTAL_UNKNOWN; run38813486644:
  seven, adds73757/73750, still no count/terminal proof. No cause of growth inferred.
- Oldham run38758465439 and38813486644: sort-selector refusal. Historical second
  body hash `d6710ba4e39239e1e6cfc74bdd2ef8831b5c642430361e8ad260603af97b3def`.
  Bridge run38824329688 hash0a222... refers to15October, not this target window.
- Rochdale run38786550045: original CRITERIA TimeoutError without rendered state.
  Run38824069251 identifies RESULT_MARKER_VISIBLE, checkpoint
  `2aa39d9937cb8f0bd8383e419f941c1c08c75c103c7bfab0c6361a1642cfd7ea`, still FAILED.
- Tameside run38805348801: SORT_REQUEST boundary failure, not parsed-list failure.

Original audits, consumed authorities, classifications and stops remain unchanged.
No live gap is closed by the offline implementation. IDs1504–1508 are untouched.

## Complete source-only recovery proposal (not registered)

### Order and execution structure

Propose **Bury → Rochdale → Tameside → Oldham**, one observation per exact window.
Bury has verified rows/criteria and the clearest missing total. Rochdale then
addresses the only browser-source gap and exposes its previously missing state.
Tameside's request failure benefits from existing transport facts. Oldham's
unrecognized search response is last because no supported alternate shape exists.

Use four **sequential separate jobs**, preserving the existing disposable source
process contexts and per-worker ceilings. Each job reserves setup, worker,
cleanup and publication time independently; no parallel resource stacking.
A later grouped approval could permit one owner launch of a finite fixed-four
manifest calling existing readers, with explicit `retain_proof=True` and Idox
zero-retry selection. This is not a new generic execution framework or permanent
schedule. No launcher/workflow is built or registered by this candidate.

Default proposed stop policy: **no failure isolation**. A failed/UNKNOWN/
INCOMPLETE observation is sealed and stops later source jobs pending review.
A COMPLETE result must independently satisfy the unchanged source contract;
proof collection alone never produces it. Four observations are a maximum, not
permission to run four despite stops. A future source-local continuation policy
would need an explicit decision and containment evidence; it is not assumed.

### Proposed ceilings

| Limit | Each Bury/Oldham/Tameside job | Rochdale job | Four-job maximum |
| --- | ---: | ---: | ---: |
| Observations | 1 | 1 | 4 |
| Attempted requests | 10 | 80 | 110 |
| Source bytes | 3,000,000 received-body bytes | 20MiB `max(encoded,decoded)+outbound_payload` | 29,971,520 mixed-accounting bytes |
| Source worker seconds | 45 | 45 | 180 |
| Active outer allocation | 60 | 60 | 240 |
| Pages/segments; rows | 6;60 | 6;60 | No subdivision/borrowing |
| Worker/aggregate owned RSS | 1GiB /1.5GiB | 1GiB /1.5GiB | Sequential, unchanged controls |
| Audit | Existing512,000byte worker bound | Existing65,536byte worker bound | At most2MiB exported total |
| Job elapsed allocation | 480s | 480s | 1,920s including setup/cleanup/publication |

Each480s job reserves up to260s setup,60s active and160s cleanup/publication.
These phase maxima do not enlarge the45s worker limit. Preserve current
per-response, outbound payload, process, checkpoint and evidence-accounting caps.
Source byte metrics and exported audit bytes are distinct; neither claims total
network traffic. No source retry, replacement observation or automatic split.

### Authority, permissions and owner involvement

No database connection, database credential, application/admission/B2 effect,
ledger grant or stop-table mutation is needed for this source-only reader path.
Do not route it through the DB-backed operational runner merely to acquire proof.
Existing source workers use credential-free minimized environments. Repository
read access and the existing narrowly controlled evidence publisher are sufficient;
publisher access is separate from the source child and limited to the existing
evidence destination with expected-head reconciliation/hash verification.

A later release needs exact candidate/tree, dependencies, four scope bindings,
manifest/publisher hashes, explicit expiry and unused single-use execution history.
Existing consumed registrations cannot be reused. No such release occurs here.

**Unresolved prerequisite:** the Salford/global stop remains in force. Bolton's
exception covers none of these four scopes. Product Owner review must explicitly
permit these bounded source-only observations under a supported stop treatment;
this PR adds no exception, policy or administrative DB fallback. If stop controls
cannot permit the source-only path without a DB effect, return that conflict
before dispatch rather than adding DB access.

Propose one owner launch, **zero credential entries**, and at most one protected
approval per job if the existing environment requires it (maximum four). Do not
remove environment protection to reduce attendance. Owner availability is needed
for those approvals and reconciliation decisions, not for interactive SQL or
continuous terminal attendance. Uncertainty means no retry; retain the evidence
and unused later scopes for a new explicit decision.

### Outcomes and next step

Success: unchanged complete-enumeration proof, exact applied criteria and identity,
no cap, certain accounting, verified publication and CLOSED owned cleanup.
Unknown/sparse/unsupported/error: retain the actual evidence and explain the exact
missing proof; do not advance coverage, completed-through or watermarks. Security,
identity/criteria mismatch, unclassified failure, accounting/export/cleanup failure
or uncertainty stops the whole package. Publish existing evidence without another
source call; no blind resume or corrective writes.

A later observation establishes then-current source contents under the historical
source-date filter. It does not reconstruct the earlier public snapshot, explain
reference growth without evidence or establish historical publication latency.

After reviewable acquisition, implement only a supported source-specific correction
if one becomes justified. Resolve these four completeness tasks before claiming
historical coverage complete. Reuse closed storage, v3 screening, admission,
authority and cleanup engineering for the finite nine-council campaign; no further
Bolton demonstration, candidate freeze or acceptance-calendar claim is made here.

## Validation and remaining approvals

See VALIDATION.json and the draft PR for measurements and exact hosted results.
Reconstructed HTML and locator doubles test actual boundary/reader/proof/export
paths. They do not qualify council markup, installed browser behavior, production
RSS fit or a publisher installation. Existing publication/process evidence is reused.
No disposable PostgreSQL is necessary: no database path changed.

Needed next: review/integrate the exact candidate, then separately decide exact
source-only release/stop treatment and the proposed finite ceilings. No generic
architecture, credential, writer or broader campaign approval is requested.
