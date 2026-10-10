# L1 final native process boundary — NO-GO

## Result

**NO-GO — SHARED RENDER PROCESS BOUNDARY UNSUITABLE** for the proposed standard
session/group-only ownership guarantee. This is a native Linux finding, not a
claim that Render was inspected or exercised. No Render command was executed.

The local standalone probe used real `fork`, `setsid`, `getpgid`, `killpg`, and
`waitid` kernel operations. It used process-namespace IDs directly and anonymous
pipes, avoiding the earlier namespace-vs-`/proc` identity mismatch entirely.
These POSIX group/session escape semantics are meaningful Linux evidence; an
unverified Render-specific restriction must not be presumed to prevent escape.

## Evidence

`native_ownership_result.json` records run
`4a7c28740ef54265ae3462eadd0774cd`:

- Ten synthetic cases: success, exception, parser failure, hung worker, child,
  grandchild, SIGTERM-ignoring child, output overflow, explicit cancellation,
  and hostile detach.
- Nine ordinary cases behaved as expected. All ten unrelated controls survived.
- Independent parent deadline was 0.75 seconds with 0.10 seconds graceful wait
  and bounded forced-termination confirmation. Long-sleeping workers did not
  cooperatively check the deadline. Fixture-only five-second alarms were not
  the successful cancellation mechanism.
- Ordinary child/grandchild groups terminated. The SIGTERM-ignoring child
  required forced group termination.
- The final detached child successfully called `setsid()`. It remained alive
  after both SIGTERM and SIGKILL to the original verifier group.
- The escaped child was separately killed and reaped solely to clean the
  synthetic fixture. That rescue is **not** group-containment success.
- Every recorded fixture was reaped, temporary artifact removed and pipe closed.
  Final remaining fixture count is zero. This does not erase the one live escape
  observed after primary cancellation.
- Completed-case elapsed times were 0.017–1.340 seconds. These are rehearsal
  observations, not measured Render/council/browser performance.

The native probe exited zero because it completed its diagnostic; its explicit
capability result is NO-GO. Exception/parser fixture exit codes are synthetic
10/11, not actual parser failures. Native browser execution was not attempted.

The evidence validator independently checks all controls, cleanup, expected
outcomes, elapsed bounds and the decisive escape. The probe's top-level verdict
alone is not evidence that every ordinary case passed.

## Safety and limits

Worker session/group identity differs from the supervisor/control group. The
worker root remains unreaped while group signals are issued, preventing its PID
from being recycled. Only fixture-created identities are signalled. No names,
service process groups, application imports, environment values, database,
council, model or network functionality are used.

A probe-local Linux child-subreaper setting exists **only** to reap synthetic
escaped children after the negative finding. It is not a proposed production
ownership solution and is not installed on Render. No daemon/cgroup/service or
new execution architecture is created.

Fixture CPU (2/3 seconds), open-file (64), and core-dump (zero) limits were applied
successfully. These do not prevent `setsid()` or provide aggregate process-tree
memory/CPU containment. No arbitrary browser memory cap or UID-wide process cap
is proposed; both require separate compatibility assessment.

Two intermediate harness observations were corrected before the recorded run:
asynchronous SIGKILL delivery required a bounded exit wait; overflow handling
needed to retain the bounded identity prefix before discarding excess output.
Those debug runs are not represented as accepted containment evidence.

## Decision boundary

The final authorised shared-runtime containment attempt stops here. No second
ownership design, adapter completion, shared Render probe or live authority is
proposed. PR #39 and its accepted ancestor remain unchanged.

Smallest alternatives for REVIEW, **not implemented**:

1. An existing disposable GitHub Actions Linux runner, pinned to reviewed code,
   with no production secrets/database access. Its independent job lifetime and
   cleanup guarantee must be qualified before council authority.
2. An existing standalone owner Linux/WSL runtime, subject to availability and
   isolation confirmation, outside the production web-service process boundary.

Neither option authorises live requests. First-canary scope remains Failsworth
and Southlink only; the Idox request boundary remains a separate unfinished gate.
