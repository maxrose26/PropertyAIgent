# Bolton direct-summary literal-source contract

Scope: application 202 / 00307/26 and application 74 / 21233/25 only.
Retained baseline/source identities are fixed in `bolton_literal.CASES`.
Source URLs are public summary routes already present in accepted capture and
8 October retained audit metadata. Synthetic HTML is labelled MOCKED_EXPECTATION.
No fixture is presented as current council truth.

## Two independent layers

Source verification requires independently displayed exact reference, a complete
summary document/table, all four source labels (explicit blanks establish
absence), unambiguous values and successful safety checks. It returns literal
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

Only an offline command-line rehearsal is supplied. It uses a clean exact SHA,
mock transport, import/network denial, a short-lived worker and temporary-file
cleanup. The added CI workflow is OFFLINE-only, contents:read, hosted Ubuntu,
no production secrets/environment and no manual/live dispatch route.
Existing application/security CI remains required. No live workflow registered.

## Review gate

Live source access and persistence remain HOLD. A future live authority must
cover only the two fixed tuples and separately approve the launcher/registration.
No Oldham, Arcus, broader manifest or production service is involved.
