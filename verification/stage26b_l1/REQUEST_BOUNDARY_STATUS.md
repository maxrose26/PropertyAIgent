# L1 request boundary: offline prototype — NO-GO

This checkpoint is **not live-ready**. It does not authorise a council request,
production access, factual persistence, deployment, or operational activation.
Accepted L1 selection remains at `371acef3e2a075d8fb7a8579540f87f5dc72c985`.
The accepted 211-reference selection is unchanged.

## Implemented prototype

`request_boundary.py` injects physical dispatch, constrains route classes,
accounts request/retry/redirect attempts and streaming response-body bytes,
closes responses, and makes failures sticky. Limits cannot exceed 20 requests,
10/reference, 10 MB total body bytes, 2 MB/response, and 165 worker seconds.
Byte accounting uses the greater of decoded bytes and exposed wire-body
position, including reconciliation when an iterator fails. It does not measure
HTTP headers or TLS overhead. The response limit is an abort bound: an offending
received chunk is counted and invalidates the entire run, never partial success.

`browser_boundary.py` is an **unrehearsed** verification-only CDP integration
prototype using existing `_PausedRoute` and `protected_browser`. Native browser
networking, CDP redirects/XHR/assets, and cleanup have not been demonstrated for
this new integration. Unknown routes are denied; Arcus Salesforce XHR routes
are not qualified. No live command is provided.

`process_boundary.py` supervises a short-lived child with bounded pipes and an
independent parent deadline. It rejects a host where `/proc` process identities
differ from process-namespace PIDs before spawning anything. The DEVELOPMENT
runtime exhibited that mismatch. This rejection is not native containment proof.

## STOP: ownership and cancellation are not proved

Independent review identified that periodic descendant enumeration can miss a
rapidly detached process that closes inherited pipes and exits between samples.
A JSON/EOF result therefore cannot establish that every descendant has stopped.
The current prototype has no proven complete ownership mechanism for that case.
Do not run it in Render. Do not claim the browser guardian's existing protections
prove the new parent/child integration. Native browser/hung-path cleanup must be
proved before any live-authority recommendation.

The user required STOP if cancellation/cleanup cannot be demonstrated without
unsafe shared-host process handling. No signals, browser execution, or probe were
sent to Render. No new process-containment subsystem was built.

## Scope preservation

Verification-specific adapter changes were investigated but **withdrawn before
publication**. The application scraper files remain byte-identical to the
accepted base. Independent review found an Idox default-path regression and an
Arcus detail-reference attribution gap in the local draft. Neither is published
as application behaviour. Adapter uniqueness/status-only integration remains
unfinished; the existing broader adapter paths must not be used for a canary.

Other unresolved requirements include exact two-reference entry-point admission,
real Idox form-field qualification, Arcus exact detail identity, explicit complete
not-found evidence, actual browser request accounting, native cancellation and
cleanup, and complete offline adapter/outcome rehearsal. Pure budget tests do not
substitute for any of these.

## Verification and next decision

`tests/test_stage26b_l1_boundary.py` is synthetic, network-free transport evidence.
`verification/stage26b_l1/test_native_boundary.py` defines native process tests;
it intentionally rejects an incompatible host rather than skipping containment.
It is not an accepted native rehearsal. Standard hosted CI and the L1 offline
suite are source/regression checks, not live-readiness acceptance.

Recommendation: **NO-GO — REQUEST BOUNDARY NOT SAFE**. Failsworth and Southlink
remain the only proposed future canary references, but no live authority is
requested. REVIEW should decide whether to authorise a narrowly scoped native
ownership/cancellation resolution and rehearsal, or retain the canary on HOLD.
No new infrastructure, credential, service or deployment is proposed as approved.
