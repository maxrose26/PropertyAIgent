# Browser source execution budget V2 — controlling design

Status: approved offline workstream (path B plus the readiness budget). No registration, permit,
authority, live observation, merge or deployment is created or implied. Stage 4 remains OPEN;
live execution remains NO-GO.

Baseline: master `b49cd5c8a7ea53cbd2235cd94634b42bb1283b07`.

## Why
* A cold page cache charges about 680MB of reclaimable file cache to the browser source group
  before any page. The measured cold baseline is 930–951MB against the 1GiB source limit.
* The local 8–14 October attempt hit the memory gate. The hosted attempts at the same window timed
  out on readiness (the criteria check, and the 10s `RESULT_MARKER_VISIBLE` wait), while four other
  Rochdale windows completed in about 4–6s.
* Inner waits (25s + 10s + criteria + 6 × 8s) were not bounded by the 45s worker ceiling as one
  budget.

## Selection (existing versioning)
A new successor release version, `THREE_COUNCIL_SOURCE_RELEASE_V2`, has its own manifest file
(`docs/design/execution-budget-20261026/manifest.json`), its own permit
`OWNER_APPROVED_FIXED_THREE_SOURCE_ONLY_STOP_TREATMENT_V2`, and the same rows, routes, allowlist
and stop policy as V1. It is the only selector of the V2 envelope.

`FOUR_COUNCIL_SOURCE_RELEASE_V1` and `THREE_COUNCIL_SOURCE_RELEASE_V1` keep their manifests,
limits and behaviour byte-identical, so historical registrations stay bound to their revisions.
Every other caller (operational tools, direct-reference, discovery, metadata, screening and
completion readers, the Render disposable job) keeps the historical envelope by default.

## Resource envelope (V2)
| Group | V1 / default | V2 |
|---|---|---|
| Source/browser (`memory.max`) | 1GiB | **1.5GiB** |
| Aggregate scope (`memory.max`) | 1.5GiB | **2GiB** |
| Controller | 256MiB | 256MiB (unchanged) |
| Swap | 0 | 0 |
| Supervised RSS-sum ceiling | 1GiB | 1.5GiB (aligned with the source limit) |

These are **ceilings**: maxima the kernel enforces. They are not reserved RAM and not a guarantee
that any workload fits. The memory-event stop (any `max`/`oom`/`oom_kill` is fatal to execution),
`memory.oom.group=1`, exact-limit verification and refusal on mismatch, and finalisation-only
reporting are unchanged.

## Time envelope (V2)
**Page-ready condition:** the result marker (`p.pr-pagination__results`) or the exact zero literal
is visible; the criteria disclosure must then show the applied filters. There is no `networkidle`
wait, because background traffic would consume the 80-request cap.

| Step | V1 / default | V2 cap |
|---|---|---|
| Navigation (`domcontentloaded`) | 25s | 25s |
| Result readiness (`RESULT_MARKER_VISIBLE`) | 10s | 20s |
| Criteria checks (disclosure and controls) | 3s + 1.5s each | 10s total (each control ≤ its own cap) |
| Pagination advance / next click | 5s / 3s | 8s / 3s |
| Worker (supervisor) | 45s | 75s |
| Source outer deadline | 49s | 80s |
| Slot active allowance | 60s | 90s |
| Successor worker / active totals | 135s / 180s | 225s / 270s |
| Per-job, setup, package | 480s, 260s, 1440s | unchanged |

**One observation deadline:** it starts when the probe worker starts and lasts 70s (75s worker
minus a 5s finalisation reserve for closing and export). Every V2 wait uses
`min(step cap, remaining)`.

**Budget expiry:**
* With no observation time left (or no criteria-total time left), the reader stops with
  `listing_failure: ObservationDeadline` before the next wait.
* A wait shortened by the deadline or the criteria total that then times out is also
  `ObservationDeadline`. The typed control timeout is removed and only its operation name is kept
  (`deadline_truncated_operation`).
* At the transport boundary, budget expiry is the fixed failure `OBSERVATION_DEADLINE`. It is never
  the typed `SOURCE_LOCAL_CRITERIA_CONTROL_TIMEOUT` and never the allowlisted
  `ROCHDALE_RESULT_MARKER_TIMEOUT`, which stays limited to a full, untruncated 20s result wait.
* Navigation keeps `page.goto` semantics, capped at min(25s, remaining).

Request (80), byte (20MiB), row (60) and segment (6) caps are unchanged.

## Evidence
* V2 audits carry `execution_budget: "BROWSER_SOURCE_V2"` and `stage_timings`, with fixed names
  only: `NAVIGATION`, `READY`, `CRITERIA` (integer milliseconds), `SEGMENT` (at most 6 integers),
  plus `deadline_ms` and `remaining_ms`.
* V1 and default audits are unchanged.
* Validators check the budget explicitly supplied by the caller (`supervisor_seconds` ≤ the
  selected worker cap) and require the audit's declared budget to equal it, so a V1 audit cannot
  claim V2 limits. The historical bound refuses any audit that declares a budget or timings.
* The supervisor records `EXECUTION_BUDGET_MISMATCH` when a budgeted worker audit does not declare
  the selected budget.

## Affected callers
| Component | Change |
|---|---|
| `four_council_release` | V2 version, manifest, permit and limits; outer deadline, slot active and worker accounting from the selected limits; `OperationalMemory` and `owner_source_context` limits from the manifest; worker `--execution-budget` |
| `finite_acceptance.read` / `classify` | optional `execution_budget` passed through; default None |
| `instrumented_probe.supervised` / `probe` | optional `execution_budget`; supervisor cap, RSS ceiling, navigation cap and timings; default None (45s / 1GiB) |
| `arcus_ui_window.enumerate_ui` | optional budget with deadline-capped waits and timings; default literals unchanged |
| `arcus_ui_audit.validate`, `criteria_containment.eligible` | optional budget for the worker bound (default 45s) |
| `operational_memory.OperationalMemory` | keyword limits, defaults unchanged |
| `docs/design/execution-budget-20261026/owner-launch.sh` (new) | V2 registrations only; scope `MemoryMax` taken from the validated manifest (2147483648). The V1 launcher is unchanged |
| `operational_ci_scope.sh` | optional exact `--aggregate-bytes 2147483648`; default still requires 1610612736 |
| Fixture CLI and offline CI | `--execution-budget-v2` profile (successor only) under a 2GiB scope on hosted CI; reclaim writes bounded at the group's own `memory.max` + 512MiB (V1 unchanged at 192 × 8MiB) and 40s elapsed |

Callers that keep the historical envelope with no change in behaviour (no budget argument):
`finite_acceptance.execute` and its readers (`completion_source`, `metadata_rollout`,
`screening_assessment`, `r0_fixed80_qualification`, `narrow_oldham_*`, `bolton53_admission`,
`material_qualification`, `r0_bolton53_qualification`), `render_disposable_job`, the four-council
V1 and three-council V1 releases, the operational tools (`operational_runner`, `stable_pipeline`,
`form_probe`, `admin_connection_probe`) and every existing owner-run script.

## Not included
Prepared-font-cache enablement, its environment guard and cold comparison, cache eviction,
reboots, any live observation, registration, release or council/database request.

Consumed authorities are immutable and are never replayed. A fresh observation of the unresolved
8–14 October window may be considered later only under new approval; another week is not selected
merely because an earlier authority was consumed.
