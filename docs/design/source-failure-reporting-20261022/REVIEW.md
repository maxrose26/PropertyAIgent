# Source failure reporting — offline correction

Aim: retain actionable, bounded evidence when the existing fixed source launcher
fails, without relaxing source, containment, publication or continuation gates.
Stage 4 remains OPEN. No live successor is registered or authorised by this PR.

## Baseline and historical reconciliation

Baseline master: `2cb3797f852fc690935d882ebf12f3ca48f17cd9`, tree
`74f55297f14fccd7574d5298ac221b6dba544672` (PR #182).

The consumed release `three-council-source-once-20261022` used registration
SHA256 `ac2fb86797b3350386324f6db81221f376261195fba6c8d073f1db13fdd229ea`.
Its claim/manifest are committed at `ff0f8942db10a4252a8fc79ed7074c43ff2833a6`,
parent `4b465be614dd3bc77cf2bc358ae0755a6152cade` (permit/preflight report).
Read-only GitHub inspection found no committed source slot or completed archive.

Owner-reported local receipts, preserved unchanged:

| File | Bytes | SHA256 |
| --- | ---: | --- |
| final-result.json | 1253 | 191c0d169aa33ead0d369924f3cca475b68c61a2647462a6acc0b8c9e8dcd066 |
| events.jsonl | 16299 | df2d5278154b808a09052bdbac97583b3a03aed1c160da170f7a13606510ca0b |
| publication-events.jsonl | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |

These are reported hashes and an available audit excerpt, not an independently
retrieved or fully archived copy of the owner-local files. The full original audit
still needs durable archival; this PR does not reconstruct or replace it.

### Established facts

The consumed claim readbacks passed; Rochdale slot 0 was reserved and entered.
Active control GETs 16–18 were acknowledged against the unchanged claim head.
The earliest established failure boundary is `Source.run`: it did not return an
accepted source audit. The historical generic `BOUNDARY_FAILURE` means a non-Stop
exception escaped, potentially including a later cleanup exception overwriting an
earlier failure. Its exact operation and exception were not retained.

No returned source file, accepted result, or usable source-accounting receipt is
available. Observed counters of zero are lower bounds, not proof of no requests.
The 80-request /20MiB reservation remains retained; Tameside and Oldham stayed unused.
Recorded controller costs: 18 GitHub calls, 10 publication calls, 5.517451594 active
seconds, 15.290896669 supervised seconds, 20,994 attempted exported bytes.

The final owned cleanup snapshot failed before assignment, leaving `{}`. Final
child/socket readbacks were zero, but group removal was not verified. The final
publication journal was created but stayed empty and the API count did not
advance. Final publication failed before its first journalled GitHub intent; the
specific precondition/reporting failure was not recorded. Subsequent systemd
readback was `LoadState=not-found`, empty InvocationID and unavailable counters.
It cannot establish closure or memory usage for the historical invocation.

### Unknowns and demonstrated defect

The root cause is UNKNOWN: memory-limit events, unavailable/changed cgroup files,
a control/call exception or another local failure cannot be selected from this
record. A persistent MemoryUnavailable is a **reproduction**, not a diagnosis.
No council timeout/parser defect, zero result, historical availability or latency
is established. Historical cleanup remains UNCERTAIN; coverage remains unresolved.

The code demonstrates diagnostic loss: non-Stop failures become generic; cleanup
exceptions can replace the first source failure; memory reporting failures are
not retained separately. Final publication uses the same enforcing deadline/gate,
so a persistent validation failure can prevent export; group close also rejects
such a condition. This correction retains those fail-closed decisions.

An additional deterministic reporting defect was reproduced offline: after a source
returned, failed validation could add its elapsed active interval a second time.
The interval is now charged once. Historical missing source usage is not reconstructed.

## Narrow correction

* Source.run captures a fixed stage and allowlisted reason/category for the first
  failure, separately retaining termination, group readback and child-reap errors.
  It still kills the entire owned source group and attempts no extra source call.
* OperationalMemory.observe reads only fixed kernel fields, with bounded sizes,
  fixed diagnostics and explicit PARTIAL/UNAVAILABLE results. It grants no execution
  permission. Existing snapshot and close checks, memory limits and defaults are
  unchanged. No arbitrary exception text, response bodies or credentials are added.
* The launcher reports source outcome, unknown source usage, retained reservations,
  accounting status (without double-counting a completed source interval after failed validation), child/socket closure, containment observation, owned-group
  closure and outer-scope observation separately. A missing outer scope is not proof
  of closure. Containment/source-closure uncertainty prevents overall CLOSED.
* The exact controller evidence packet and hashes are saved locally before final
  publication. Invalid source bodies stay local and unvalidated; only the already
  safe controller audit/receipts can be exported. A valid audit prefix is explicitly
  PARTIAL when a reporting event/close failed; valid hash chains do not prove audit
  completeness.
* Final publication retains the **original** memory.snapshot, authority/expiry,
  cancellation, expected-head/CAS, immutable-blob and committed-readback gates.
  The existing reserve_scope narrows remaining API/time allowances. There is no
  fallback publisher or weakened containment check. Persistent gate failure keeps
  the packet local. Uncertain publication is never retried or compensated.

All per-source/aggregate resource ceilings, source routes, parsers, timeouts,
continuation allowlist, default-off controls and cancellation protections remain.
No database, writer, schema, function, role, permission or dependency change.

## Validation and limits

Focused tests inject persistent containment validation failure at the source-run
boundary, a second cleanup failure, reporting/prefix failure, invalid source proof,
local packet/read errors, publication failures/lost acknowledgement and uncertain
process/group readbacks. They assert no subsequent scope, no unknown-as-zero claim,
no invalid-source export, no arbitrary-message export, locally preserved hashes,
no mutation after uncertain acknowledgement and no false CLOSED result.

The existing whole-launcher native rehearsal adds three fixed faults:
`memory-failure` (injected persistent MemoryUnavailable), `reporting-failure`
(final audit-event write failure), and `publication-failure` (uncertain final blob
acknowledgement). It uses real processes, cgroups and the existing publisher with
synthetic source/GitHub transports. Injected failure is not a measured real memory
breach. Missing group verification remains UNCERTAIN even with no live processes.

The PR report records final head/tree, independent review, CI identities, verified
artifact digests and measured rehearsal costs. Synthetic costs do not predict
council/network latency. No live qualification or historical gap is closed.

## Held actions

Draft PR only. Merge, registration, permit, source execution and all production
changes remain held. No terminal diagnosis or retry of the consumed release.
Bury remains parked; all original stops, IDs1504–1508, consumed authorities and
historical uncertainty remain unchanged. No automatic next observation.
