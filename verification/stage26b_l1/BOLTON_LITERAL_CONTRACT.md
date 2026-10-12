# Bolton direct-summary literal-source contract

Scope: application 202 / 00307/26 and application 74 / 21233/25 only.
Retained baseline/source identities are fixed in `bolton_literal.CASES`.
Source URLs are public summary routes already present in accepted capture and
8 October retained audit metadata. Synthetic HTML is labelled MOCKED_EXPECTATION.
No fixture is presented as current council truth.

## Two independent layers

Source verification requires independently displayed exact reference, a complete
summary document/table, mandatory reference/status labels, unambiguous values
and successful safety checks. It returns literal
status, literal decision and separately parsed decision date.

Deposited is UNKNOWN_UNMAPPED. Neither date absence nor the global classifier's
fallback is evidence that it is pending or non-terminal. Unknown current labels
never reach that fallback. No global classifier or Idox source was changed.

Two additive outcomes qualify source-only observations:
SOURCE_FACT_VERIFIED_UNCHANGED and SOURCE_FACT_VERIFIED_CHANGED.
Existing L1 failures are preserved. When both prior/current semantic states are
established, the existing L1 assessment/material contract is reused unchanged.
When an unmapped prior state becomes a known grant/refusal/withdrawal, the new
state can be established but transition materiality is UNKNOWN_REQUIRES_REVIEW.
Unknown-to-unknown changes also require review; no invalidation is implied.

This is audit-only. Source verification success does not authorise a successful
verification timestamp write for unmapped semantics. Future literal-fact storage,
semantic-state storage and timestamp interpretation require separate acceptance.

## Transport and runtime

Requests: 4 total / 2 per reference; concurrency 1. One transient retry at most;
no rate-limit, ambiguity, parser or deterministic HTTP failure retry.
Zero followed redirects; observed denied redirects are counted.
Only the two exact HTTPS summary URLs may reach the real HTTP adapter.
No search, browser, documents, further-information, conditions or discovery.
Session trust_env is false; no environment proxy/netrc credentials are inherited.
Connection timeout 3s, read timeout 8s; accounting window and independent worker
deadline 45s. Ordinary termination escalation is bounded by existing supervisor;
disposable GitHub runner remains final cleanup boundary.

Response ceiling: 1,000,000 bytes; run ceiling: 2,000,000 bytes, charged across
retries. Existing streaming boundary charges the greater of decoded and exposed
wire-body position, not Content-Length. An overflow chunk is charged and fails
closed; enforcement is chunk-granular (up to 65,536 bytes), not an OS packet cap.
No artifact claims an overflow run succeeded. Artifact maximum 16,384 bytes.

The originally accepted offline command-line rehearsal uses a clean exact SHA,
mock transport, import/network denial, a short-lived worker and temporary-file
cleanup. The added CI workflow is OFFLINE-only, contents:read, hosted Ubuntu,
no production secrets/environment and no manual/live dispatch route.
Existing application/security CI remains required. The separate registration
launcher below adds a manual workflow without dispatching it.

## Review gate

Live source access and persistence remain HOLD. A future live authority must
cover only the two fixed tuples and separately approve the launcher/registration.
No Oldham, Arcus, broader manifest or production service is involved.

## V2 field-granular evidence correction — offline, not registered

Retained 8 October browser-table text for app202 contains Reference/Status but
omits Decision/date labels; app74 contains all four. The privacy-minimised
fixture is a historical table-text projection rendered into synthetic HTML,
not original HTML or current council truth. Its table-text hashes differ from
case-index snapshot hashes; that cryptographic linkage is unresolved.
This justifies historical field optionality, not the latest run's missing label.

Reference and status remain mandatory nonblank exact evidence. Decision/date
use PRESENT_VALUE, PRESENT_BLANK, NOT_PRESENT, CONFLICTING or UNPARSEABLE.
NOT_PRESENT means the recognised label was not found, never verified absence.
Successful artifacts carry field_evidence and source_fact_change_scope so None
cannot imply authoritative absence without PRESENT_BLANK qualification.
Optional omission gives COMPLETE_FOR_STATUS_ONLY, not complete decision facts.
Unchanged applies only to the explicitly listed evidenced fields.

Missing decision prevents semantic interpretation; missing either optional field
prevents semantic materiality assessment. Explicit blanking of an earlier
decision/date still fails; conflicting fields and malformed dates still fail.
Deposited remains UNKNOWN_UNMAPPED. No persistence or freshness write follows.

V2 diagnostics contain only parser version, fixed summary-table identifier,
bounded ordinal, four approved field identifiers, states and occurrence counts.
No values, arbitrary labels, HTML or personal information are included.
The registered workflow/verifier on master remains V1 until separate review
and integration; the consumed canary remains FAIL and is not rerun.

## Registration-only launcher

`bolton-literal-canary.yml` registers workflow_dispatch ONLY. No merge, push,
PR or schedule can start that workflow. Its inputs are SHA, offline/live mode
and a dedicated acknowledgement; none can substitute council/reference/URL.
Live access still requires a separately approved Product Owner decision.

`bolton_runner` admits an exact clean SHA matching the executing workflow,
GitHub-hosted runner, manual event and AUTHORISE_BOLTON_TWO_SUMMARIES_ONLY.
Worker environment is rebuilt without service credentials, model keys, proxies
or GitHub token. ImportFence is installed before importing the verifier.

Outer job: 2 minutes, including dependency setup. Worker: at most 45 seconds;
15 seconds are reserved for normal cancellation/upload. Slow setup shortens
the worker allowance or rejects execution before any council request. Runner
disposal remains the final process boundary; no shared Render execution.

Complete and valid failure audits are validated against the accepted closed
schema before export. Interrupted/missing/invalid output fails the job without
inventing zero-request accounting or manufacturing a complete artifact.

Registration CI invokes the launcher OFFLINE with mock transport/network denial.
Its automatic triggers never supply live mode or live authority. The manual
workflow is not dispatched during registration, including in offline mode.
