# Stage 4 instrumented source probe

Authority: Product Owner instruction 13 October 2026, instrumented transport
validation and minimum ten-council completion. Extends specification 030's
source qualification; does not change B2 or admit production routes.

Start with four frozen public references: Manchester 142419/FO/2025 (688),
Salford PA/2025/1084 (252), Rochdale 25/01149/FUL (295), Trafford
117039/FUL/25 (290). Manchester's recommendation-only 138696/FO/2023 (1299)
is a separately selectable field-semantics control. No arbitrary URL input.

Use existing Playwright, an isolated subprocess/process group and ephemeral
context. No database credentials, persistent browser profiles, document visits,
model calls or raw HTML/cookie/token retention. Initially allow only GET/HEAD on
the exact council origin; unknown POSTs are stopped before dispatch and reduced
to safe action descriptors for review. No direct API replay without an evidenced
ordinary public read-only contract. Off-origin requests fail closed.

Bounds per invocation: one case, one context/page, two main-frame navigations,
at most two direct-child about:blank/about:srcdoc frame navigations,
80 requests, 20 MiB observed encoded and decoded response bytes, 45-second worker
deadline, 1 GiB aggregate owned-process RSS. No retries. Observed network byte
events have reporting latency; this is an observed-byte threshold, not a claim
that wire transfer can never overshoot by an in-flight chunk. No response bodies
are retained. DOM evidence limited to exact reference and planning field labels.

Parent records owned process identities, terminates the process group on every
exit and checks observed descendants have exited. No hostile OS detachment claim.
Missing worker output, surviving processes or unqualified fields cannot pass.
Execution is restricted to a GitHub-hosted disposable runner with coherent
runtime/procfs process identities. The current local execution environment has
different runtime and procfs PID views, so its process accounting is not accepted.
CDP accounts the main page; popup/worker creation stops the diagnostic but is not
claimed as hostile all-target network containment. Observed payload byte totals
exclude headers and can omit cached transfers. No full wire-byte claim.
Hosted ephemeral runner is the final process boundary. A local launch failure
does not establish a council source failure.

Initial probe is diagnostic only. Even a successful result cannot directly
advance verification. Actual source admission requires reviewed transport
semantics, focused tests, live bounds/cleanup evidence and existing B2 integration.

## Observed guest HTTP diagnostic

The reviewed browser metadata identified the Arcus PublicRegisterViewService
getRecordHeaderDetails read action with a literal null guest token. One fresh
cookieless HTTP session may replay that exact observed single-action envelope
for the frozen record and register. No guessed context, credentials, redirects
or retries. The response is capped at 1 MiB; socket timeout is two seconds,
cooperative elapsed cutoff five seconds, and the existing supervisor provides
the hard worker deadline. Browser POSTs remain blocked, including telemetry.
Selected planning labels and structural keys only are retained, never raw JSON.
This diagnostic is not B2-eligible and does not establish a complete source
contract. Its HTTP attempt and decoded body bytes join aggregate counts; CDP
encoded-byte counts exclude this separate HTTP request. Trafford is not retried.

Guest framework context may contain up to 20 primitive public globals from the
fresh credential-free page. Values remain transient and unchanged; nested,
oversized or credential-named entries are rejected. This tolerance does not
change the exact action/record/register/null-token boundary.
