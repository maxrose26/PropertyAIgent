# TO REVIEW — R0 FIXED-80 QUALIFICATION / EXACT-27 OBSERVATION RESULT

Master Stage 4 OPEN. Current gate: cron-suspension source-date catch-up.
Result: TWO CONSUMED, SAFE PARTIAL EXECUTIONS. No retry or replacement dispatch.
Parent R0 coverage and database catch-up remain INCOMPLETE.

## Execution identities and artifacts

Both runs used master 77356e04ef855f7373b96b9210f593e9b96c897c,
tree 1f36311cbc66ef3b474110cb15723d81cb4ed8ca, run 1 / attempt 1.
Before each dispatch, master/registered tree/blobs/manifests, six successful applicable
CI checks and full manual history were checked. Qualification itself added a running
source check on that revision; it was distinguished from the six prerequisite CI checks.
Existing signed-in GitHub browser access performed each dispatch once. No CLI was
installed, credential transferred, permissions expanded or protection changed.

| Scope | Run | Artifact | Verified ZIP SHA256 |
|---|---|---|---|
| fixed80 |38758282951|11985255295|4efd1716953bca638e84ad65481fc4c21c890aac6d30425d2a75b36e224b8d8f|
| exact27 |38758465439|11984302666|19279ea9886b950f3b90b6f85a12d26d3a1c03477d621710736177181f212526|

Both workflows concluded FAILURE because their parent reported controlled hard stops.
Both audit gates and uploads succeeded. The worker exited 0; outer supervision did not
expire or hit a resource limit. A workflow failure is not a finding of lost evidence.
The Node.js deprecation warning was not the causal failure.

Manifest identities are unchanged:
- fixed80:1c4cb696cfd352532a0c19fe9e919e86059908cc3cf21ed37f8be2ec8ab23b12
- exact27:f99d86a5deb251f45c0787af295836aa948d8250d9f7b180062db229c6dc0e3d

## All 80 qualification outcomes

qualification-all80.json/CSV reconcile every authorised identity and its actual outcome.

| Disposition | Bolton | Bury | Total |
|---|---:|---:|---:|
| Exact identity, B2-ineligible/withheld |42|0|42|
| Parser failure, identity not qualified |1|0|1|
| Not attempted |11|26|37|
| Admission-ready under current path |0|0|0|
| Commercially excluded |0|0|0|

For the 42 observations: displayed reference matched exactly; reference/status were
PRESENT_VALUE; literal status was Deposited; decision and decision date were NOT_PRESENT.
Scope reported COUPLED, eligibility FALSE, rejection B2_EVIDENCE_SCOPE_INELIGIBLE.
Diagnostic conditions: DECISION_NOT_PRESENT, DECISION_DATE_NOT_PRESENT,
SOURCE_SEMANTIC_STATE_UNKNOWN_UNMAPPED. These are qualified source observations,
not accepted FULL_FACTUAL/STATUS_ONLY/FIELD_LEVEL factual persistence.

The existing Idox retrieval path requires decision/date for its COUPLED eligibility
(refresh.py _retrieve_row); project_idox accepts COUPLED only. It did not exercise
INITIAL_STATUS_ONLY. The accepted Arcus initial-status implementation is explicitly
limited to qualified council/literal combinations and does not already admit Bolton
Deposited. No status mapping, eligibility or evidence rule was changed in this task.
Missing decision/date must not be turned into an unsupported-council or non-material
classification. REVIEW should distinguish this concrete path limitation from the
accepted broader field-completeness product contract. No automatic relaxation is proposed.

Attempt 43 Bolton 01842/26 received 36,621 bytes in one request, then PARSER_FAILURE,
NOT_QUALIFIED and NO_QUALIFIED_OBSERVATION. Its precise parser subcause is not retained;
no wrong-reference, access-block or council-wide failure is inferred. All prior 43
observations/checkpoints remain intact. No live diagnosis/retrieval was repeated.

All materiality remains the retained POTENTIALLY_MATERIAL/qualification-pending state;
no scale/site/role inference or commercial exclusion was made. All relationships and
roles remain UNKNOWN. All five Bury UNKNOWN-window candidates remain visible and
NOT_ATTEMPTED. The earlier absence snapshot is not current admission authority.

## All 27 windows and 206 retained references

all27-window-reconciliation.json contains every window and the retained independent
comparison. New-primary-candidate-ledger.json records 206 unique council/reference
identities with source IDs/links, literal dates, timestamps, windows and provenance.

| Council/window | Primary enumeration | Retained refs | Independent comparison |
|---|---|---:|---|
|Manchester 24–30 Sep|INCOMPLETE/PAGE_CAP|60 of 69|denominator unavailable; retained 10 are a subset|
|Manchester 1–7 Oct|INCOMPLETE/PAGE_CAP|60 of 67|unavailable|
|Manchester 8–14 Oct|COMPLETE|43 of 43|unavailable|
|Oldham 17–23 Sep|COMPLETE|19 of 19|exact retained identity-set match|
|Oldham 24–30 Sep|COMPLETE|13 of 13|exact retained identity-set match|
|Oldham 1–7 Oct|COMPLETE|11 of 11|exact retained identity-set match|
|Oldham 8–14 Oct|FAILED|0 retained|primary qualification unavailable; not a proved zero-result window|
|Rochdale/Salford/Stockport/Tameside/Wigan, four windows each|NOT_ATTEMPTED|0new|20 untouched windows|

PAGE_CAP continuation is positively demonstrated: both ordinary caps retained 60
candidates and proceeded. Neither was promoted to COMPLETE. The Oldham hard stop
remained intact and prevented subsequent calls.

Oldham 8–14Oct failed ListingError:sort selector after two requests / 126,367 bytes.
Offline code inspection identifies sort_payload's requirement for exactly one
select[name="orderBy"] after explicit-zero qualification did not succeed. The audit
does not retain response content, so the underlying page shape/cause is UNKNOWN.
The older independent zero-reference observation cannot qualify this later failed
response as empty. No source exception was downgraded to a safe gap.

New references: Manchester 163 (128 in-target / 35 overlap), Oldham 43
(19 in-target / 24 overlap). Total 147 in-target / 59 overlap. All 206 have parseable source dates;
these are VALIDATED/RECEIVED dates, not public-availability timestamps. No unknown-date
reference was silently discarded. Listing identity is not exact-detail qualification,
material value, database absence or admission eligibility.

## Retained independent evidence

Original seals unchanged. No fresh browser denominator observation occurred.
Twelve usable retained denominators remain available, 15 unavailable. Only three usable
windows now have successful primary enumeration; all three Oldham identity sets match.
Eight usable denominators belong to windows not attempted. The remaining usable Oldham
zero window has a failed primary call. No unexplained material/parser miss is established.

Original ledger 715da66d96a643800c7a30df9ae88481e7fc2576d89fc55a4ec93484a2049f17;
append ledger 7a46aa77843e85b226f1f1a0982feff79a2d111a4a93596a37ad953a0c7ceb23.
Original seals 13:24:35.113641Z/13:51:40.727344Z preceded original reveal 13:52:00.570326Z.
These new primary observations occurred 15:14:50–15:15:42Z. Sources could have changed
between observations. Matching sets do not establish publication recall or timeliness.

All 283 original independent-only identities remain in retained-283-reconciliation.json:
53 were also observed in this new primary invocation;230 were not. The latter are not
labelled parser misses, absent database records or lost opportunities. Original
Manchester stopping-rule and browser-reset accounting/retention limitations persist.
No lost set was reconstructed and the original evidence was not relabelled.

## Resources, checkpoints, cleanup and production effects

| Audit measure | fixed80 | exact27 |
|---|---:|---:|
| Source calls/windows attempted |43|7|
| Requests |43|115|
| Budget-accounted bytes |1504324|34221862|
| Outer execution seconds |145.294|52.629|
| Peak owned RSS bytes |146853888|1050144768|
| Completed checkpoints |43|7|
| Checkpoint bytes |81740|121119|
| Expanded aggregate audit bytes |170541|247098|
| Accounting |CERTAIN|CERTAIN|
| Cleanup / survivors |CLOSED/0|CLOSED/0|

All checkpoint hashes/contents, aggregate byte totals and per-source request/byte sums
were independently recomputed offline. No deadline/RSS/output limit was hit. Exact27
byte accounting follows the accepted max(decoded,encoded)+outbound Arcus convention.
Each completed observation was durably retained before subsequent calls.

Both workflows have no protected environment, database secret or admission path.
Execution metadata reports 0 production connections/reads/writes; registered code and
workflow separation reconcile. No application/site/link/opportunity was created.
Transaction: NOT_STARTED—CERTAIN; no uncertain commit or retry. No watermark advanced.
No raw HTML, credentials/cookies or applicant/contact payload keys were found in audit.
No code implementation changed or new generic test programme ran; reconciliation
assertions verify the artifacts and ledgers. Earlier exact-head CI/review remain intact.

## Proposed next bounded decision

Eligible admission cohort under the current qualification path: EMPTY. No admission
should be dispatched from these results. Preserve 42 qualified literal observations
without interpreting withheld facts as commercial exclusions. The smallest engineering
question is offline compatibility of the existing Idox COUPLED path with the already
accepted field-level/initial-status contract; do not broaden semantics automatically.

proposed-additional-identity-comparison.json freezes 147 in-target identities:
Manchester 128 / Oldham 19. Proposal only: existing protected route/validator, BEGIN READ
ONLY, exact council/reference predicates, LIMIT 2 each (max 294 identity rows), identity-only
output, existing statement/lock/outer bounds, rollback/disposal. No arbitrary SQL,
source retrieval, B2 or admission. It does not expand/re-execute consumed fixed80.
Any execution requires a reviewed binding and separate authority.

Twenty primary windows remain genuinely untouched. Failed Oldham, both new Manchester
caps, prior capped Manchester and BuryUNKNOWN must remain separately identified—no
silent retry manifest. No replacement workflow or automatic resume was prepared.

Bury, Manchester caps, unavailable denominators, publication recall, unsupported
latency and 15 October onward bridge remain unresolved. Database catch-up incomplete.
No prospective acceptance, recurring schedule, AI/model, deployment, Trafford or
Stockport committee investigation occurred. Stage 4 is not closed or advanced.
