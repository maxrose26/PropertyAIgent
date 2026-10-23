# Bounded post-failure finalisation — offline candidate

Aim: after a source memory-limit event, retain the existing stop of all source
work while allowing the controller's own evidence to be exported and its owned
cgroups removed, without relaxing any limit, gate or authority. Stage 4 remains
OPEN. No release, registration, permit or live execution is created or authorised.

Baseline: `e07c3ce5a1ba29d564eb4bec16645e2d0c0600e4`, tree
`a591a08a997c708123e104a1fc578b539bd32a4e`.

## Evidence (owner-local, not published)

`three-council-recovery-once-20261023` recorded `SOURCE_MEMORY_CHECK/MEMORY_LIMIT_HIT`
with source `memory.events max=26, oom=0, oom_kill=0`, peak at the 1GiB ceiling and
685MB still charged to the emptied source group. Final publication and owned-group
removal then failed with the same code. An offline investigation (empty network
namespace, identical scope properties) reproduced the mechanism, not Rochdale's
exact composition:

* A cold page cache charges about 680MB of reclaimable file cache (browser, Playwright
  `node`, fonts rebuilt by Chromium's bundled fontconfig, shared libraries) to the
  source group before any page content; anonymous memory was about 250MB.
* Exceeding the ceiling made the kernel reclaim file cache: `max` increments, no OOM,
  and the reader completes when the gate is not applied.
* The memory.events counters are cumulative. `snapshot()` raises on any `max>0`, and
  it gates every GitHub call (`deadline`) and `close()`, so the recorded failure
  could never be exported and the owned groups never removed by the launcher. The
  same removal sequence without that check succeeded.

Rochdale's real page footprint, its source outcome and usage remain unknown.

## Change

* **Latch.** On a `MEMORY_LIMIT_HIT` failure whose source closure is certain and whose
  failing slot's outcome is still UNVERIFIED, the launcher calls
  `OperationalMemory.latch()`. It closes execution first and permanently
  (`snapshot()` then always raises `FINALISATION_ONLY`; `Source.run` refuses before
  any process start), then verifies exact limits, swap, group OOM, an empty source
  and sole controller occupancy, and records all six counters per group plus group
  inode identity and the controller's own cgroup as the baseline. Only a
  source-group event can be finalised: any controller event, or any event local to
  the aggregate (`memory.events.local`), refuses the latch. A source OOM is latched
  and reported in the counters, never hidden. Failure to latch leaves no baseline:
  finalisation refuses and today's held behaviour remains.
* **Finalisation check.** Used only by `deadline()` once `finish()` enters
  finalisation, by the containment readback and by `close()`. It refuses on lost or
  changed enforcement, changed identity, a populated source, controller survivors,
  unreadable fields or **any counter differing from the baseline**.
* **Export preconditions.** Before finalisation export, no live child and no new
  socket. Expiry, cancellation, head/CAS, immutable blob, readback, request,
  time and byte reservations are unchanged. No retry, fallback publisher or
  "ignore memory errors" flag exists.
* **Reporting.** The original failure and reason are preserved; the result adds
  `finalisation` (state, latched failure and counters). Confirmed removal reports
  `owned_group_closure=CLOSED`. Source outcome, accounting (`PARTIAL_SOURCE_USAGE_UNKNOWN`),
  containment status and overall `cleanup` are not upgraded.
* **memory.stat.** `observe()` adds bounded allowlisted fields. `memory.current` is
  approximately `anon+file+kernel+sock`; `shmem/file_mapped/file_dirty` are subsets
  of `file` and `slab_*/kernel_stack/pagetables/percpu` subsets of `kernel`. The
  observation carries this partition so subsets are never summed with their parents.

The latched packet keeps `process_cleanup`/`cleanup` UNCERTAIN, including the
exported copy. Unreadable counters refuse with `MEMORY_FIELD_UNAVAILABLE`. The
baseline compares the six `memory.events` keys; swap events are not compared
because swap is fixed at 0 and verified. `memory.stat` requires `anon`, `file`
and `shmem`; `kernel` needs Linux 5.18 or later and is optional.

Without a latch, every OperationalMemory behaviour used by other operational tools is
unchanged. Limits remain 256MiB controller, 1GiB source, 1.5GiB aggregate, swap 0.

## Validation

* `tests/test_discovery_memory_finalisation.py` drives the real OperationalMemory and
  launcher code on a file-backed cgroup tree: max without OOM; each counter rising
  in each group; changed limits/swap/OOM policy; populated source and controller
  survivors; replaced groups and moved process; unreadable/malformed counters;
  live child at export; publication failure, lost ACK, cancellation and expiry
  without retry; no later council or source process after the latch.
* Native rehearsals (real cgroups) add `memory-reclaim` (real kernel `max` without
  OOM → exported and removed), `memory-enforcement-lost` and `memory-survivor`
  (held, groups not removed) to the CI loop, and an owner-local `real-chromium`
  council-free browser rehearsal (inline content, all requests aborted). CI has no
  browser installed, so `real-chromium` is not added to CI.

An independent review (separate agent, read-only) found no violation of the
stop-source-work or retained-gate invariants. Its findings were addressed: latch
scope narrowed to source events, the latched exported packet no longer reports
pending cleanup, fixed codes for unreadable counters, a detached survivor fixture
asserting the kernel group check, a relaxed `memory.stat` precondition, no
spurious latch failure for doubles, and self-removal of the reclaim fixture file.

A focused read-only re-review of the exact candidate `3d42404f` judged findings 1, 2, 4,
5, 6 and 7 fixed and 3 partially fixed, and found one new issue. Follow-ups:
* New: on the four-council path a memory event first seen after a slot receipt was
  accepted could be latched and exported with that COMPLETE receipt. The latch now
  requires the failing slot's outcome to be UNVERIFIED; otherwise the run stays held.
* `enforcement()`/`identity()` readback errors now refuse with `MEMORY_FIELD_UNAVAILABLE`.
* CI uploads the receipts of the new memory faults on failure.
* CI containment: the three-council native loop scope has `RuntimeMaxSec=80s` (below the
  90s timeout); the memory-survivor process lives 60s and is killed via its recorded
  source group. Because `systemd-run --scope` does not report a scope timeout in its exit
  code, each iteration checks the scope `Result`; anything but `success` is reset and
  fails the step, so a bounded-out iteration can never pass silently.

A further focused review (exact `39dd77f2` and the CI commit) found the slot, receipt and
no-execution properties holding, and raised: an unreported scope timeout (now checked),
`close()` survivor pre-reads without fixed codes when latched (latched `close()` now goes
straight to `finalisation_check()`), latching of non-limit MEMORY failures (now only
`MEMORY_LIMIT_HIT`; lost enforcement and unclassified memory failures stay held), and test
gaps (identity/usage readback, exact stages, slot-top failure) now covered.

## Held

No merge, push, registration, permit or live execution. The fontconfig cache
preparation and any change to treating `max` without OOM as non-fatal are separate
owner decisions and are not implemented. Consumed releases are never replayed.
