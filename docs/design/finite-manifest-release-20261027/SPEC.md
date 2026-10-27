# Finite manifest source release (offline, default off)

Baseline: e8b249e5c0064f38205ae5c9f43c49379ecf22d5 / 475666b9c61181fb0f9b59c2540d9b6c0c0498f6. No merge or live authority is part of this slice.

## Data and admission

Add FINITE_MANIFEST_SOURCE_RELEASE_V1 to the existing launcher. A campaign input has exactly `finite_manifest`, `finite_manifest_sha256`, `selected_ordinals`. The full plan is the unchanged `finite_acceptance.manifest(start,end,purpose)` output (at most 28 days, its three existing purposes). Regenerate the full canonical plan, verify its hash, then select strictly increasing unique zero-based row ordinals. Canonical generator order is retained: council order, then contiguous windows of at most seven days. No supplied row, command, URL, limit, continuation or unknown field is accepted.

The initial reusable source-proof scope is the four existing proof-retention councils: Bury RECEIVED, Oldham RECEIVED, Rochdale VALIDATED, Tameside RECEIVED. Other generator councils are refused before a claim, not presented as newly qualified. Dates vary only through the generator. Extending proof/owner-local source support to other councils is a separate qualification dependency. Manifest membership establishes neither completeness, admission, a detail contract nor database authority.

Registration binds the complete regenerated plan, selection, derived rows/routes, immutable fixed limits and manifest hash; the existing revision/tree/dependency/package/expiry/permit checks remain. A child receives the same bounded registration and hash and derives its row by ordinal. Historical versions and command defaults do not select this path.

## Existing controls and limits

Reuse the reviewed V2 package envelope unchanged: at most three observations, 100 attempted requests, 26,971,520 mixed-accounting bytes, 225 worker seconds, 270 active seconds, 1,440 package seconds, 480 per job, 320 GitHub/80 publication calls, 2MiB exported, 512KiB per slot. Existing V2 memory limits remain 1.5GiB source/2GiB aggregate/256MiB controller. Arcus uses the explicitly selected reviewed BROWSER_SOURCE_V2; Idox keeps its historical reader ceilings (45 seconds/10 requests/3,000,000 bytes/60 rows/six pages/no retry).

Before claim/source work reserve each selected row's worst-case requests, bytes, worker/active/job allocations, publication calls, control calls and export space. Refuse any excess; unused allowance cannot expand another slot. The generator's much larger round limits are data only, never executable allowances. Demonstrate at most three rows (including one Arcus plus two Idox); do not claim a full nine-council week fits.

Retain existing control polling, fail-closed checks, publication CAS/readback and owned-process cleanup. This source-only permit remains unsynchronised with database stops; there is no enabled permit in this workstream. Continuation reuses the existing predicates only: Rochdale marker timeout; Tameside/Oldham search/sort timeout; Oldham missing sort selector. Bury receives no continuation exception. Any other failure/unknown, cancellation, authority, accounting, export, publication or cleanup uncertainty stops later rows.

## Proof retention and compatibility

Reuse the structural proof schema, sanitiser and reader code. An explicit per-process manifest proof context permits only the exact selected four-council row; the historical TARGETS/default scope check stays unchanged outside it. Propagate that context to existing child entrypoints, never via ambient environment. The parent revalidates returned proof against the selected row; evidence remains an observation at execution time, not a historical snapshot.

No new parser, writer, orchestrator, database function/policy/role or operational registration is introduced. Prepared font-cache selection remains off.

## Acceptance

Two different selections/weeks execute through the same launcher/Source/worker/publisher with synthetic sources. Test exact canonical binding, tampering, unknown fields, purpose/council/date/ordering/duplicates/overlap, capacity before claim/source, council-correct worker selection, receipts/usage/publication, exact continuation isolation, cancellation, uncertainty and historical V1/V2 regressions. Reuse hosted real-cgroup infrastructure; temporary-file simulations are not kernel proof. Report measured fixture costs separately from reserved ceilings and real council qualification.
