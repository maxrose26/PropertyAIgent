# Fixed three-council source isolation — offline candidate

Aim: allow the three independent, unattempted council scopes to acquire evidence
without making one specifically contained early source failure block the others.
This is not authority to execute, merge, publish an enabled permit or clear a stop.
Stage 4 remains OPEN. Bury is excluded.

Baseline: `dae815dda2832005f92e6d7b8426acc6cded6a06`, tree
`2fbaf3acbc4e9a729a88021fe0b4d210f297e18b` (integrated PR #181).
The final reviewed head/tree and CI identities are reported in the draft PR.

## Fixed scope and reuse

| Order | Council | Basis | Inclusive interval |
| --- | --- | --- | --- |
| 1 | Rochdale | VALIDATED | 8–14 October 2026 |
| 2 | Tameside | RECEIVED | 1–7 October 2026 |
| 3 | Oldham | RECEIVED | 8–14 October 2026 |

The same `verification.discovery.four_council_release` controller, private source
child, readers, proof projection, kernel containment and committed-readback publisher
are reused. Original reader indices 1/2/3 remain explicit, so Rochdale uses its
Arcus route and bounds and Bury cannot enter this profile. No reader, parser,
timeout, transport retry, SQL, writer or source qualification is changed.

`THREE_COUNCIL_SOURCE_RELEASE_V1` has its own exact manifest and permit binding.
The render flag `--three-council-successor` selects this fixed profile only;
the renderer remains INACTIVE unless proposed enabled bytes are explicitly selected.
Rendering proposals grants no execution authority. The old four profile retains
its stop-all decisions and default selection. Existing consumed registrations,
evidence and local audit directories are not modified or replayed.

## Positive continuation allowlist

The following fixed codes identify policy eligibility, **not a proven council-only
root cause**. A transport failure could still reflect shared network conditions.
No generic FAILED, UNKNOWN, INCOMPLETE, cap or arbitrary exception may continue.

| Code | Exact admitted shape | Preserved outcome |
| --- | --- | --- |
| ROCHDALE_RESULT_MARKER_TIMEOUT | Existing `criteria_containment.eligible`, narrowed to typed Playwright `RESULT_MARKER_VISIBLE` timeout; complete rendered projection, no contradictory/ambiguous criteria, no rows/segments, applied interval unknown. Existing exact origins, blocked-action, safety, supervisor, accounting and closure checks all apply. | Source FAILED; existing wrapper may say UNKNOWN. Neither is rewritten. |
| IDOX_SEARCH_OR_SORT_TIMEOUT | Tameside/Oldham only; fixed `BoundaryFailure:SOURCE_CONTRACT_REJECTED`, SEARCH_REQUEST or SORT_REQUEST; matching TIMEOUT transport facts and unavailable-body proof; exact preceding operations/request count, no rows/pages/retry/budget exhaustion. Any retained SEARCH criteria mismatch/ambiguity refuses continuation. | FAILED |
| OLDHAM_SORT_SELECTOR_ABSENT | Oldham only; exact `ListingError:sort selector`/SORT_SELECTOR_COUNT at SORT_FORM_PARSE; two requests; retained HTTP200 SEARCH body hash matches diagnostic and response provenance; closed structural document, zero sort controls, no explicit-zero literal or contradictory/ambiguous date controls. | FAILED; no zero/completeness inference |

All require existing proof scope/hash validation, exact source identity, certain
finite request/byte/timing accounting, positive source-group closure, no surviving
child/new socket, intact kernel limits and verified durable slot publication.
Every next slot, after COMPLETE **or** an allowed failure, additionally requires
fresh authority/control/head/expiry checks, repeated process/socket closure and
enough reserved next-slot resource/publication/finalisation budget.

Malformed proof, wrong identity/criteria, unknown failures, source-security events,
accounting/export/publication uncertainty, cancellation, expiry, memory/containment
or cleanup failures stop all remaining scopes. No error flag is erased. Invalid
proof remains local and is not exported as valid source evidence. Source cleanup
uncertainty is preserved even if later controller groups can be removed.

Per-slot receipts preserve wrapper outcome and source outcome separately. An
eligible code in a receipt is not itself authority: a `source_local_continuation`
event is emitted only after publication and the next-slot checks pass. Finishing
all three with any unresolved outcome gives OBSERVATIONS_FINISHED_WITH_GAPS and
exit 1, never THREE_COMPLETE. No coverage, absence or watermark is advanced.

## Budgets and live holds

Per-observation ceilings are unchanged: 6 pages/segments, 60 rows, 45 worker
seconds, 60 active seconds and 480 elapsed seconds. Each Idox scope has 10 requests
and 3,000,000 received-body bytes; Rochdale has 80 requests and 20MiB under the
existing Arcus metric. Existing lower worker-audit bounds win over 512KiB export.

Aggregate reservations are reduced to 3 observations, 100 source requests,
26,971,520 mixed-accounting bytes, 135 worker seconds, 180 active seconds and
1,440 elapsed seconds. The existing 320 GitHub calls /80 publication calls /2MiB
export maxima are not increased. Kernel limits remain 256MiB controller, 1GiB
source and 1.5GiB aggregate, swap zero. The owner script derives its independent
systemd deadline from the exact validated profile (1,440s here, 1,920s for four).
No borrowing, retry, replacement or subdivision. These are ceilings, not targets;
none of these byte metrics is total network traffic.

The database-free permit still does not synchronise database stops. Original
Salford/global/manual stops remain unchanged. Remote detection remains at most
7 seconds **after API visibility**, with unknown GitHub propagation delay;
local cancellation and hard deadlines remain independent. No new exception is live.

The prior Bury release is consumed and CLOSED within its recorded scope:
evidence `a7125179a72830af8b2c75d877a2dd2947aa5ffc`; final receipt SHA256
`9b629b7f324ef065ff8ff6a1bfa51a3e4054c09405edd1e041ccf353292c2db8`;
publication journal SHA256
`a40251b06f7e41cf84e3af0adf5a8cfee46516bd1773462b8886b3307b238043`.
Its outer systemd removal and all earlier uncertainty remain as recorded. The
eight-second read-inactivity timeout does not establish why Bury timed out.
No Bury correction or observation is part of this change.

## Validation and evidence boundaries

Focused tests exercise actual source readers against reconstructed HTML/locator
fixtures, then the shared launcher and expected-head publisher algorithm against
a Git-shaped API fixture. No council, production database or source retry occurs.
Native CI uses real Popen/cgroups and the Arcus supervisor with synthetic browser
transport. It covers all success, each allowed failure position, all three allowed
failures together, active/startup cancellation and unavailable control. Existing
four-profile tests/native rehearsals remain in CI.

Focused negative cases include wrong bindings, rehashed contradictory criteria,
security fields, incomplete accounting, unknown outcomes, caps, malformed proof,
surviving processes/sockets, unavailable containment, exhausted next-slot budgets,
expiry/control changes and publication failure/lost acknowledgement. No consumed
release is resumed and every fixed scope is attempted at most once.

Source/control/slot evidence and prefix audit are archived through the existing
publisher. Final publication acknowledgements and final memory closure remain in
separate local sealed receipts; an archive cannot include its own upload receipt.
The final local receipts must be reconciled before accepting any future run.
No claim of outer scope removal before process exit or retrospective public
availability/latency is made. Tests are engineering evidence, not live coverage.

## Next decision

Review this draft and exact-head CI first. Dormant integration is separate from
any later source authority. A live decision must separately accept these exact
three continuation codes, fixed scopes/budgets and unchanged database-free stop
boundary; it would require a new unused identity, expected evidence head and
expiry within24h. No live registration is prepared here. Before later release,
revalidate the owner's pinned packages, matching Chromium shell, import/launch/
closure and kernel delegation using the accepted council-free preflight.

No merge, enabled permit, source observation, database access, application effect,
deployment, scheduling, admission expansion, candidate freeze or Stage advancement.
IDs1504–1508, existing evidence, historical authorities and all four gaps remain
unchanged. Completing observations does not automatically accept their coverage.
