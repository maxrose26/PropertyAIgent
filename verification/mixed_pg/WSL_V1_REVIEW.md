# Mixed WSL archive review — 30 September 2026

Candidate: 50cc8eedb91042a6598331fa035993a2d3b76b0b.
Returned archive SHA256:
92415bf0c9f2a9057fa9e67c40ffe68b97d5e3c9e0cf2a28881374fc3c46db93.
Outer checksum and all internal SHA256SUMS verified. Native XML: one test,
one failure, zero errors or skips. PostgreSQL shutdown recorded. No acceptance.

The controller successfully SIGKILLed child 147 at its readiness marker. The
supervisor recorded return_code=-9, then echoed the marker in its error summary.
The controller matched that echo and signalled the now absent PID again, raising
ProcessLookupError. Successor slice 7 and later-council slice 8 were not reached.
This identifies a controller defect, not a demonstrated storage/recovery defect.

Observed bounded progress before the failure:

| Slice | New discovery completed/deferred | Revisit result |
|---|---|---|
| 0 | 2/1 | Original documents and relationships complete; variation discovered |
| 1 | 2/1 | Hyde document HTTP403 partial; relationships complete |
| 2 | 2/1 | Variation statement and relationships complete; discharge discovered |
| 3 | 2/1 | Discharge document HTTP403 partial; relationships complete |
| 4 | 2/1 | Unchanged body: one version, two observations |
| 5 | 2/1 | Changed same-URL body: two versions, three observations |
| 6 | 2/1 in child progress log | Child killed before document persistence; controller then failed |

Slices 0–5 snapshots retained. Post-kill storage assertions were not reached.
Variation summary remained unchanged. Each discovery slice used two requests,
234 bytes. Revisit slices 0–5 used respectively 2/2/3/2/2/2 requests and
184/27/389/27/220/220 bytes. These are synthetic fixture measurements, not live
throughput. Cgroup memory availability was false; memory-cap enforcement is not
established by these results. Production workload and cadence remain unmeasured.

Narrow repair: exact council-prefixed readiness parsing and a one-shot signal.
Log echoes, malformed markers and repeats cannot trigger another kill. A failed
first signal still propagates. No application, schema, admission, ownership or
migration changes. Eight focused offline controller tests passed, no failures or
skips; the one native composite test collects. Native rerun is needed only to
finish the interrupted walkthrough. Accepted prior suites were not rerun.
