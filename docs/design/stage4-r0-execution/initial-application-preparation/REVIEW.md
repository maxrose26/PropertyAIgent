# TO REVIEW — INITIAL-APPLICATION CONTRACT AND REMAINING DISCOVERY PREPARATION

Stage 4 remains OPEN. No merge, registration, dispatch, source/browser observation,
production access, admission, model or scheduling occurred. Consumed runs38758282951
and38758465439 remain closed. Admission cohort remains empty.

## Contract finding and precise decision

NO-GO for promoting Bolton initial-status eligibility under the current contract.
This is a concrete source-contract gap, not an architecture failure or a requirement
to populate every field. There is no supported Idox INITIAL_STATUS_ONLY route to wire
without extending an accepted restriction. No initial Idox promotion was implemented. The supported positive initial-status path remains the accepted Arcus path; its end-to-end disposable tests pass.

The accepted trace is:
1. Arcus worker independently qualifies record/reference and literal field states.
2. arcus_adapter._from_observed_row/_project initial_status accepts only Manchester
   Under Consideration or Salford Under Consultation, with uncertain decision/date
   states preserved. It builds explicit field_evidence and INITIAL_STATUS_ONLY.
3. rejection_audit exports actual eligibility/scope without deciding them.
4. Shared admit_identity creates only discovery_pending identity with duplicate/race,
   transaction and readback protection. Existing identities skip initial facts.
5. committee_exact._run_cohort obtains fresh source evidence then refresh._refresh_row
   delegates INITIAL_STATUS_ONLY to existing B2.
6. status_verification._verify_initial_status independently checks exact Arcus path,
   query/host/council/literal, fresh empty discovery_pending record, no site/units/prior
   facts and explicit field evidence. Only status receives verification provenance.
   Decision/date retain their literal uncertainty and verified_at=NULL. Combined
   status_verified_at remains NULL; no initial source-change event is manufactured.

Both projection and B2 explicitly restrict the accepted source/literal combinations:
Manchester/arcusbe.manchester.gov.uk/Under Consideration;
Salford/salfordcitycouncil.my.site.com/Under Consultation.
B2 additionally requires /pr/s/detail/<18-character record ID> and exact register query.
Bolton's Idox URL and Deposited literal fail those restrictions independently.

Idox _retrieve_row returns COUPLED and requires present decision/date for B2 eligibility;
material_qualification.project_idox accepts COUPLED only. Merely setting eligible or
relabelling cannot bypass the projector or B2. The pre-existing known-reference
Awaiting decision proof is an unchanged-existing-record scope, not a new-record path.
No inference Deposited=Awaiting decision or pending/granted was made.

The precise Product Owner decision is whether to authorise qualification of an
ADDITIVE Bolton-specific initial literal-status contract: exact approved Idox summary
route and displayed reference, literal Deposited retained as-is, independently present
status, no inferred semantic planning state, explicit decision/date uncertainty, only
an empty new discovery_pending application, and existing B2 as sole writer. This is
not already accepted merely because field incompleteness is legitimate. No generic
Idox/Bury/status allowlist expansion, new writer or schema redesign is proposed.

## Implemented correction: failure observability only

Successful Observation construction, B2, Arcus policy, source restrictions, existing
COUPLED and known-reference rules are unchanged. No consumed manifest/workflow changed.

_refresh_row's underlying retrieval accepts an OPTIONAL diagnostic sink used only by
the qualification worker. It records fixed execution stage and response bytes in worker
memory. On failure, source_diagnostics exports only schema-validated stage/code,
body byte count/SHA256, bounded counts of summary tables/labels/forms/sort selectors,
and shape availability. No raw bytes/HTML/literal values/URLs/exceptions are exported.
Resource counters and closure still come from existing transport/supervisor.

Idox window failures similarly capture the actual parsing stage and last relevant
response shape. Existing known sort-selector/duplicate-reference messages retain their
fixed spellings; other exception text is replaced by a fixed SOURCE_CONTRACT_REJECTED
label. Failures remain hard stops; no criteria/sort/identity evidence is weakened.

Parser findings from retained evidence ONLY:
- Bolton01842/26: PARSER_FAILURE after one request/36621bytes; no retained response
  body or precise failure stage. Exact parser subcause remains UNKNOWN. The new bounded
  stage/shape audit can distinguish summary/identity/decode/structure stages in a future
  separately authorised observation. No parser correction is established now.
- Oldham8–14October: ListingError:sort selector. Code requires exactly one orderBy
  selector after explicit-zero qualification failed. The retained artifact has two body
  fingerprints but no content/selector count. Missing versus multiple selector, changed
  page, unexpected response and unqualified zero remain unresolved. Earlier independent
  zero cannot establish the later response was empty. No parser correction is justified.

## Separate frozen remaining scopes (proposal only)

All JSON manifests explicitly registered=false, execution_authorised=false,
persistence=false. manifest-index.json records exact file digests. No executable new
workflow/caller registration or authority is supplied by these files.

| File | Exact scope | Proposed source ceilings |
|---|---|---|
|retained42-offline-assessment.json|42 qualified Bolton observations|zero calls; reassessment only; no eligibility promotion|
|failed-bolton-one.json|Bolton01842/26 only|1call/2requests/2MB/55s/64KiB audit; assessment only|
|qualification-unattempted37.json|11Bolton+26Bury, including all five UNKNOWN-window refs|37calls/74requests/74MB/2035s/5MB audit|
|primary-unattempted20.json|Rochdale/Salford/Stockport/Tameside/Wigan, four original windows each|20calls/760requests/203772160bytes/1220s/20MB audit|
|failed-oldham-one.json|Oldham8–14October RECEIVED|1call/10requests/3MB/55s/1MiB checkpoint; assessment only|
|capped-manchester-three.json|17–23Sep,24–30Sep,1–7Oct originals; six proposed non-overlapping subwindows|6calls/480requests/125829120bytes/450s/20MB audit|
|unresolved-bury-one.json|Bury8–14October RECEIVED|separate residual; existing1call/10requests/3MB/55s per-window cap|
|preserved-comparison-proposal.json|unchanged147target identities, Manchester128/Oldham19|no query authority; identity-only comparison proposal retained|

The42 retained observations are minimised actual evidence derived from artifact11985255295,
not reconstructed source HTML. Identity/status/state/fingerprint/scope can be reassessed
OFFLINE without another request. They cannot gain eligibility under the existing contract.
Any later admission still requires fresh independently qualified source evidence plus
current automatic duplicate/race protection; an earlier snapshot/retained response is
not replay authority. No new37 qualification is recommended until the contract issue
is decided; Bury's literal status remains unobserved, not assumed to equal Bolton's.

Budget derivation:37*2requests/2MB and37*55s reserves yield74requests/74MB/2035s.
Two checkpoint copies at37*65536bytes plus131072envelope reserve fit within5MB.
41minute job proposal leaves at least120s cleanup/upload after280s setup and2035s
execution. The20 windows comprise8Arcus+12Idox, giving760requests and203772160bytes.
20*55s=1100s plus120s parent/checkpoint headroom gives1220s;27minute job leaves140s
after260s setup. Preserve1.5GiB owned RSS, credential-free child environments, durable
checkpoint-before-next-call, truthful partials and hard stop/accounting/cleanup controls.
The existing fixed80 caller cannot be reused as a resume: it still iterates exactly80. A future fixed37 parent must bind only the listed original case identities and reuse the existing per-record workers; a future20-window parent must validate its exact manifest before the shared recovery core. These ceilings need binding/enforcement in separately reviewed future entrypoints;
no existing consumed workflow is repurposed and no automatic retry is possible.

The six Manchester partition proposals split each original week into3days+4days.
Per-call page/request/byte limits are unchanged. Completeness is UNPROVEN; another
cap remains INCOMPLETE. Old timestamps/results/seals are unchanged. No partitions ran.
Single failed-record manifests are assessment scope ceilings, not complete registered
job proposals. Bury remains UNKNOWN with all five retained references intact.

## Tests and review

All response bodies generated in tests are explicitly SYNTHETIC. The42-observation
fixture contains minimised real retained audit evidence, not page HTML. Tests exercise
actual Idox worker/streaming parser/projector/rejection audit, missing/conflicting/wrong
identity and unmapped literals, and rejection of forged scope/eligibility changes.
The accepted Arcus projector flows through shared admission/B2 in disposable SQLite,
retains CONFLICTING/NOT_PRESENT decisions unverified, reads back initial status, and
preserves already-known/changed facts on repeated admission. An adversarial Bolton
INITIAL_STATUS_ONLY handoff is rejected by B2 without factual writes. No Idox positive
initial acceptance or fresh-source qualification is claimed.

Existing disposable PostgreSQL admission/race/lost-ack/readback checks remain relevant
and are included in hosted discovery CI. New tests verify disjoint manifests, exact
remaining windows, unchanged147proposal scope and sanitised exception output. CI paths
include actual changed source/diagnostic/test files. Final exact-head results and
independent review are recorded in the handoff; this branch is not merged.

## Smallest next execution and gate consequences

Recommend the20 genuinely untouched windows as the next independent SOURCE-ONLY scope
AFTER review/integration/registration and exact execution confirmation. Fresh observation
is necessary because these windows have never been called; no primary output can be
recovered offline. This avoids replaying42 completed records or retrying failed windows.
It does not depend on promoting Bolton status. No execution is authorised here.

Keep the147current-identity comparison proposal separate and unchanged. Do not add
uncertain-date or independent-only references without their own reviewed comparison
scope. All283 independent-only candidates and original seals remain preserved; no
fresh independent observation or reconstructed lost set occurred.

To close catch-up: resolve the initial-status contract decision; complete untouched
source windows and separately approved gap handling; qualify eligible identities;
perform authorised current identity comparison and bounded shared admission/B2 with
fresh evidence/duplicate-race controls; reconcile committed readback and residuals.
Publication recall, unsupported latency, independent denominators, Bury/Manchester
caps/Oldhamfailure and15October onward bridge remain open. No prospective acceptance
or stage advancement is approved.
