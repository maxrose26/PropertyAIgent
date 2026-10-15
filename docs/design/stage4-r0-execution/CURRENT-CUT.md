# R0 latest-completed-day scope — execution HOLD

Stage 4 remains OPEN. This supersedes only the prior date scope; no observation or admission is authorised by this correction. Both old and revised execution authorities remain on hold pending confirmation of the revised integrated identities.

## Current manifest

- Exclusive cut: **15 October 2026 00:00 Europe/London**, equivalent to **14 October 2026 23:00 UTC**.
- Suspension target: **29 September–14 October inclusive**.
- Trailing 28-day observation: **17 September–14 October inclusive**.
- 17–28 September is overlap context, not suspension recovery.
- Nine councils, four contiguous weekly windows each: 17–23 September; 24–30 September; 1–7 October; 8–14 October. Total 36 windows. Trafford excluded.
- Canonical manifest SHA256: `01d91aaea90f5ac03fbbc325fe85e66f7cc09539cd917457412c185bc38fa7cb`.
- Primary/independent budgets, source-date semantics, source rules, exact identity, independent-blinding/seal chronology, completeness/partial accounting, cleanup and single-use controls are unchanged.

The guard derives the UTC time boundary from the same CUT constant and Europe/London zone used by the manifest, avoiding a second independently maintained date literal. Tests prove refusal immediately before the cut, acceptance at the cut, exact manifest/file agreement and rejection of the superseded manifest digest. They also assert all four new weekly windows for every council.

## Previous manifest

`manifest-superseded-cut-2026-10-16.json` preserves the previous manifest unchanged. Canonical SHA256: `99a5bff2f627111f7c2addc3457caf4725312d1a4a8e935de205d5e6bd85d3f4`.

Disposition: **SUPERSEDED — NOT EXECUTED**. Existing master before this correction was `4ec81d2a46c425ae84c3f40f0d88392d2260a8b8`. Complete available manual-dispatch history was checked: 21 runs overall, zero R0 runs. Recheck again before any later execution. Original REVIEW.md/REGISTRATION.md remain historical records with explicit supersession banners. Their old dispatch inputs are not current authority.

## Bridge interval

**[15 October 2026 00:00 Europe/London, eventual prospective start)** is the explicit bridge interval. It is not covered by this R0 manifest. If prospective start is not yet fixed, the bridge end remains OPEN; subsequent bounded coverage requires review. Do not silently treat 15 October as recovered, lose this interval, or count later recovery as original prospective detection.

## Proposed inputs after separate execution confirmation

- ref: master
- reviewed_sha: the verified post-merge revision for this correction, not the preceding registered master or a draft head
- manifest_sha: 01d91aaea90f5ac03fbbc325fe85e66f7cc09539cd917457412c185bc38fa7cb
- authority: AUTHORISE_NINE_COUNCIL_R0_SOURCE_DATE_OBSERVATION_ONCE
- run 1 / attempt 1 only, subject to fresh exact-master/workflow/manifest/history checks

Workflow path remains `.github/workflows/stage4-r0-source-date-once.yml`; workflow bytes/SHA256 remain unchanged: `5766acc2a137d50c4072d3153b6a0c52e7966580a66298c602d4d68484e4d893`.

No dispatch of either version in this task. No live source calls, production database access/admission, schedules, models, deployment or prospective execution. Publication recall and unsupported latency remain UNKNOWN. R0 source observation is not database catch-up completion.
