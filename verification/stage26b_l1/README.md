# L1 — offline selection and council verification design

Base: 183570e0c940d28b51b9f05a5dbf47f56dff37b2. Controlling specification: 031 (030 status contract). No application source or scheduling changes. No production command, persistence writer or live request runner is supplied.

## Evidence / selection

`selection.build` consumes the accepted L0 retained dependency artifact and minimum structural capture; it never runs the buyer evaluator or reads the DB. It rejects a changed 234/211 basis, duplicate IDs, exact reference/site/council mismatch, incomplete structural retrieval and future verification dates. Current commercial completeness remains QUALIFIED. Raw private inputs and generated manifests are not committed.

234 direct candidates reconcile. 211 have exact planning-status dependencies; their retained edges also support decision and decision date. The other 23: A (additional status source) 0; B (other direct fact, deferred) 23; C (unresolved field) 0. Known retained fields map to residential scale or OTHER_DIRECT_FACT (opportunity signal/development type/specialist context). No AH or commencement/deadline role is manufactured. Verifying status does not certify any other domain.

Generated status manifest: 211. Cohorts: C1 1, C2 134, C3 0, C4 67, C5 9. C5 records remain in the proposed dependency ledger, deferred from first execution. The queue reuses Specification 031 cohorts and missing-first/oldest-first deterministic ordering, not a commercial score. No universal age threshold; age is measured as of the structural capture, not falsely current at execution.

Council counts: Bolton 16; Bury 5; Manchester 38; Oldham 20; Rochdale 20; Salford 32; Stockport 35; Tameside 7; Trafford 19; Wigan 19.

11 application-edge subjects without exact status attribution remain in a separate non-polling queue. 226 strategic subjects without retained application edges remain qualified allocation-policy subjects, not manufactured planning dependencies.

Ten allocation-review applications: 23,63,96,123,142,294,328,961,962,1433. Each retains individual relationship ID/allocation ID/review status. confirmed is accepted relationship evidence, auto_applied is machine-proposed, needs_confirmation unresolved, rejected remains rejected. All ten are contextual-only without an established direct status source; no new request authority. Historical origin of additional captured links is unresolved.

## Adapter/source matrix (source inspection, not live capability certification)

| Council | Existing module | Mechanism / known limits |
|---|---|---|
| Bolton | idox_portal | Exact reference form; direct redirect or result keyVal; browser plus requests detail |
| Bury | idox_portal | Same status route; separate Anite document route is excluded |
| Manchester | arcus_portal | Quick-search exact reference filter, detail page; see Arcus limitations below |
| Oldham | idox_portal | Exact reference; Failsworth and Southlink proposed canary |
| Rochdale | arcus_portal | Quick search/detail; result and detail casing/date labels differ |
| Salford | arcus_portal | Quick search/detail; some result-list fields may be absent |
| Stockport | idox_portal | Further Information uses details tab; configured 2.5s delay; known 429 risk |
| Tameside | idox_portal | Exact reference form, result/redirect handling |
| Trafford | idox_portal | Known connection/navigation timeout risk |
| Wigan | idox_portal | Inline result tabs deduplicated by keyVal; summary tab forced |

Idox navigation retries: 3 attempts, 30s navigation timeout and 2s retry pause. HTTP detail retry budget: 4 attempts; default 30s timeout; connection pause 3s, 429 pause Retry-After or 5s multiplier. These defaults are NOT proof of compliance with the proposed canary global budget.

Arcus navigation defaults 45s plus explicit wait. Exact lookup does not walk the full related-app discovery pagination. It chooses the first matching row; Idox fallback similarly chooses the first distinct keyVal. Future status-only execution must reject ambiguous matches before detail selection, not accept first-match behaviour. Arcus normal residential detail attempts the Files/document-list branch; future status-only execution must deny that branch. No integration/parser replacement is implemented here.

Related application search, document-delta discovery, date-range searches and document downloads remain excluded. A result of None alone cannot distinguish definitive not-found from incomplete/unparsed retrieval; `contract.assess` defaults it to PARTIAL_RETRIEVAL, not a successful or definitive not-found check.

## Outcome / materiality / factual acceptance

Outcome vocabulary: VERIFIED_UNCHANGED, VERIFIED_MATERIAL_CHANGE, VERIFIED_NON_MATERIAL_CHANGE, SOURCE_UNAVAILABLE, REFERENCE_NOT_FOUND, AMBIGUOUS_SOURCE_RESULT, PARTIAL_RETRIEVAL, PARSER_FAILURE, RATE_LIMITED, TIMEOUT, UNSUPPORTED_COUNCIL.

Failures require explicit transport/parser evidence. Existing broad fetch_failed exception must remain qualified, not be relabelled as a specific failure by guessing exception prose. Mocked explicit signals test the outcome contract; they do not prove current adapters emit every differentiated signal.

Pure assessment delegates planning state/materiality/date parsing to existing production helpers. Missing fields cannot erase established decision/date. Unknown decision strings, incompatible committee/issued decision and older conflicting terminal evidence fail closed. Unsupported appeal/supersession semantics remain partial/unresolved pending exact evidence, not silently pending. Issued pending-to-grant/refusal/withdrawal and committee-to-issued transitions are material where source-qualified. Equivalent raw wording can be non-material. Timestamp-only change is unchanged; document metadata alone cannot establish material planning change.

Future acceptance must use existing B2.0 transaction architecture: clean owned session, optimistic watermark guard, single atomic status/decision/date/verification/provenance/lifecycle/material transaction, stale-response rejection, rollback, idempotent retry and lost-ack handling. No new attempt column, schema, lifecycle engine or production persistence is implemented. If source provenance cannot fit existing fields, return for review; no migration is assumed. A failure never writes accepted facts or advances successful verification.

Consequences are candidates only: B2.1 planning presentation, Scheme Intelligence eligibility, allocation narrative eligibility, deterministic reconciliation, buyer assessment, Spec028 explanation, family presentation, fingerprint values and future summaries where the exact status fact is a dependency. No fingerprint algorithm/matcher/family/AH change. No actual invalidation or regeneration. Unchanged verification triggers none solely due to elapsed time.

## Request and resource planning

121 Idox references and 90 Arcus references. An idealised status-only path would require roughly 4 logical operations per Idox reference (search navigation/submission and two detail GETs), 2 per Arcus reference: 664 logical operations. This excludes browser assets/XHR, redirects, retries and session overhead and is NOT an HTTP request count. No defensible measured likely/worst network count exists yet. A provisional one-retry-per-operation envelope doubles logical operations to 1,328, still excluding browser traffic; existing adapter defaults can exceed it.

Illustrative planning scenarios only: 5–30 seconds per reference means 17.6–105.5 minutes sequential; 0.1–1 MB per reference means 21.1–211 MB. No throughput/bandwidth measurement exists. Full queue execution must not be authorised on these assumptions. Concurrency 1; council-specific batches, traffic observation, limited retry/backoff and circuit stop required before larger authority.

## Two-reference canary proposal — NOT READY FOR LIVE EXECUTION

Allowlist only Oldham FUL/355686/26 (app42/site28) and FUL/355201/25 (app29/site25). No related discovery, documents, AI or DB persistence. Fixed order Failsworth then Southlink. Expected outcomes are retained expectations, never forced results: refusal confirmed -> material candidate; pending confirmed -> unchanged. Changed contemporary evidence must be reported honestly.

Proposed lower global ceilings: 20 total HTTP requests including browser assets/redirects/retries, 10,000,000 received bytes, 180 seconds wall time; concurrency1; at most one bounded retry of a transient request; never retry ambiguity/parser/not-found/overflow. Per-response ceiling2MB, at most10requests per reference. Abort whole run on host-domain violation, ambiguity, overflow or unsupported path. Explicit configured Oldham host plus separately reviewed necessary asset hosts only; no arbitrary URL redirects. Source hostname and exact returned reference required.

`CanaryBudget` tests accounting/allowlist/circuit arithmetic ONLY. It does not intercept live browser traffic or independently enforce a process deadline. A live run is HOLD until a bounded offline rehearsal proves all browser/HTTP requests, redirects, response bytes, duplicate results and deadline/cancellation are intercepted without altering accepted product semantics. Do not use normal run_weekly/verify_application_status as a read-only canary launcher: those routes can persist production changes.

Future audit: pinned SHA, input manifest hash, allowed refs/hosts, per-attempt timestamps/counts/bytes/outcome, source identity/hash, no bodies/private fields. Partial-run progress is an audit artifact, not successful verification. Resume only explicitly authorised incomplete refs; completed unchanged checks are not material changes. Abort/circuit state must prevent continuation. No new crawler/service/credential is proposed.

## Offline coverage and exclusions

Synthetic portal HTML/text fixtures exercise the REAL Idox exact lookup and parsing plus Arcus quick/detail parsing for an administrative fixture avoiding Files. They are not retained current portal bodies. Stored IDs/references and Failsworth/Southlink expectation are retained; mock source responses are MOCKED_EXPECTATION. Failures are explicit synthetic signals. No live council or DB access. No model calls.

Private per-row manifest, 23 dispositions, 10 review relationships and unresolved queue are derived outside Git. Hosted tests exercise synthetic fixtures only. No live command, no production policy, deployment, refresh, bootstrap, monitoring, B3–B5, Stage2.5C or decomposition.
