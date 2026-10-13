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
