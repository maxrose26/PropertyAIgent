# TO REVIEW — OBSERVED-CANDIDATE COMPARISON AND REMAINING-WINDOW RECOVERY PREPARATION

Master Stage 4: OPEN. Current gate: cron-suspension source-date catch-up. Outcome: OFFLINE PROPOSAL REVIEWED; PRODUCTION COMPARISON ACCESS BLOCKED — CHECKPOINT ONLY. No architecture NO-GO is inferred.

## Exact observed cohort and provenance

`comparison-80-manifest.json` freezes exactly the retained IN_TARGET identities: Bolton 54, Bury 26, 80 unique pairs, no substitutions. File SHA256 `cf31d3a5dd69da7c65348428473a0bb15cf38071caab41b5db76b6d5ea8845cd`.

Verified against original run 38731487848, revision 388532c640a22ca89f2409686db168c90db57ac9, artifact 11970371484, ZIP SHA256 `67d39048af9e2f0048d36173baf0424b881efc313c74247a11a814909c8d8eef`. The retained ledger's Git blob was independently recalculated and equals `758a19b83096b97f8bfc21eabffc114083e80ca4`, matching the published audit. Independent reviewer rechecked selection, artifact hash, retained ledger hash and exact ordered identities.

All five Bury 8–14 October references remain candidates: 73755, 73748, 73743, 73742, 73741. Their window remains UNKNOWN. The 83 overlap records remain unchanged context and are excluded from the proposed production comparison.

## Current database comparison — NOT EXECUTED

Existing Supabase browser access was attempted through the already-authorised GitHub sign-in route. Fresh visible Supabase evidence confirmed signed-in account maxrose26 and the Property Tools organization with one project. However, after selecting the organization, the browser's credential-protection layer prevented project-page observation. One documented explicit navigation also failed to permit observation. No workarounds, new credentials, broad exports or new access mechanism were attempted. Secure owner interaction is required to continue.

The correct retained production project identifier is zcikcfgpblzuzpanpdqd; it must be positively verified in the live dashboard before running the read-only query. A signed-in organization list alone does not qualify the project or comparison.

Current results:

| Comparison | Result |
|---|---|
| Requested exact identities | 80 |
| Production queries executed | 0 |
| Comparison timestamp | NONE — no query |
| Proven absent | UNKNOWN |
| Proven one-match | UNKNOWN |
| Proven duplicate | UNKNOWN |
| Unresolved comparisons | 80 |
| Database connections/reads/writes by this task | 0 / 0 / 0 |

The old 1,453-row snapshot has NOT been used to prove current absence. No absent count of zero is claimed. `qualification-80.json` explicitly preserves UNKNOWN_ACCESS_BLOCKED_NO_QUERY and UNPROVEN absence eligibility for each identity.

`comparison-80-read-only.sql` is prepared, not executed. It uses BEGIN READ ONLY, 15-second statement/2-second lock timeouts and exact council/reference predicates for the frozen 80. It returns only timestamp/database-name metadata, request/result counts and matched id/council_code/reference. Each identity is capped at two matches: 0 = absent, 1 = unique, 2 = duplicate detected (two or more, not an exact total). Maximum 160 matched identity rows. No planning-fact export, mutation, credentials or arbitrary identity input. Project identity must be verified separately in the dashboard. The query is acceptance comparison only; future admission must independently recheck exact duplicates/races automatically.

## Deterministic qualification and proposed admission scope

Retained literal metadata supports 80 in-target candidates under existing stage4-discovery-v1 conservative qualification. All remain POTENTIALLY_MATERIAL because scale/relationship uncertainty cannot safely exclude them; this is not proof of buyer relevance or 80 missed opportunities. No unsupported facts, new site or relationship inference was added. No fresh official-source calls were made. Existing literal field states and source fingerprints remain authoritative.

No genuinely absent eligible cohort can yet be frozen: database comparison is unresolved for all 80. Proposal after comparison: retain uniquely known identities without duplication; stop/escalate duplicate identities; take proven-absent candidates forward for deterministic qualification and fresh exact-source evidence before any reviewed shared admission/B2 authority. No admission is authorised now. Initial identity capture is not factual-verification success. B2 remains sole planning-fact writer.

## Exact remaining-window manifest

`remaining-28-manifest.json` equals the original artifact's 28 NOT_ATTEMPTED rows exactly, independently reviewed. Canonical SHA256:
`5e4170c781314ba76583682e39ef0072ec932926617f3be169316873485ee9ae`.
File SHA256:
`7202f16381d01db734ee7d31bfd2e469325e1b801d5e4a627028df57d413e63f`.

| Council | Semantics | Fixed windows |
|---|---|---|
| Manchester | VALIDATED | 17–23 Sep; 24–30 Sep; 1–7 Oct; 8–14 Oct 2026 |
| Oldham | RECEIVED | same four windows |
| Rochdale | VALIDATED | same four windows |
| Salford | VALIDATED | same four windows |
| Stockport | VALIDATED | same four windows |
| Tameside | RECEIVED | same four windows |
| Wigan | RECEIVED | same four windows |

No Bolton or Bury window is included; no retry of the seven completed windows or Bury's unresolved window. Original R0 run remains consumed. No date/cut movement. The explicit bridge remains 15 October onward.

## Offline continuation candidate and safeguards

New `verification/discovery/r0_recovery_proposal.py` reuses existing source contracts, configuration and `finite_acceptance.classify`; it adds a fixed-manifest execution API requiring explicit reader injection, with no CLI, workflow registration, authority or source call performed in this task. Existing R0 and finite-caller semantics are unchanged.

Safe local continuation is limited to missing total/terminal evidence or ordinary page-cap state, with exact source/window/date context, retained criteria evidence, qualified non-conflicting literal identities, certain bounded accounting and closed cleanup. Gaps remain UNKNOWN/INCOMPLETE. COMPLETE children also undergo independent identity/safety checks. Any source exception, unclassified failure, identity conflict, wrong destination/context, uncertain resources, security event, supervisor limit or failed cleanup stops remaining calls. Child accounting uncertainty propagates to parent. No discarded exception text is exported.

Parent coverage is always INCOMPLETE because the unresolved required Bury window remains outside this proposal. Even complete enumeration of the 28 cannot erase that gap or prove publication completeness. No persistence, watermark or admission path exists.

Limits: 28 finite calls, 1,120 requests, 299,658,240 observed bytes, 1,900 seconds and 20 MB output — no increase from R0 ceilings. Existing per-worker origin, request, byte, navigation, deadline and cleanup controls remain unchanged. Worst-case reservations occur before each call. No automatic retry/resume outside accepted internal source behaviour.

Execution is NOT registered or live-ready. Before any execution, a separately reviewed new master/revision/manifest/run-1/attempt-1 authority binding, credential-free worker wiring and enforceable outer supervisor/timeout must be installed and tested. The existing outer supervisor's hard-coded R0 worker must not accidentally launch the old manifest. No new workflow or alteration to historical execution identities was made here.

Proposed future authority string: AUTHORISE_SEVEN_COUNCIL_R0_UNTOUCHED_WINDOW_RECOVERY_ONCE. Requested scope would be exactly the 28 manifest rows, once, after separate registration/review and exact integrated identities are confirmed, with no database access/admission and no Bury retry. This string is a proposal, not current authority; no dispatch inputs are yet valid.

## Tests and independent review

62 affected network-denied tests passed across the new recovery suite, existing finite caller and original R0 suite. Independent reviewer separately ran all 25 new focused tests successfully. Coverage includes manifest mutation rejection, local-gap continuation, identity checks for COMPLETE and incomplete observations, criteria provenance, Arcus gap handling, security/cleanup/resource/accounting stops, source exceptions, budget reservation and no credential context. Original caller's stop-first-gap tests still pass.

Three review findings were corrected before publication: COMPLETE Idox children previously bypassed draft identity checks; draft local gaps could omit criteria fingerprints; explicit child accounting uncertainty was not propagated. Focused regressions now cover each. Final review: PASS for bounded OFFLINE PROPOSAL only. Live authority/outer wiring remains a registration requirement, not claimed proven.

The existing offline CI invocation adds the new focused suite; existing verification/discovery/** and tests/test_discovery_*.py path triggers cover new files. No source-execution workflow is registered. Hosted validation is not represented as completed unless separately evidenced on the published candidate.

## Bury and independent comparison residuals

Retained Bury audit and parser handling were inspected offline. The primary audit reports TOTAL_UNKNOWN with five records and null total/terminal; separate UI observation had no Next but no displayed count. No concrete parser or evidence-handling defect is established from retained evidence. No raw HTML exists in the audit to justify reconstructing one. Preserve UNKNOWN; no eligibility/terminal relaxation or live diagnostic loop.

Smallest Bury resolution proposal is to review whether existing retained evidence can ever meet the accepted terminal/count contract; it currently cannot. If REVIEW requires another live observation, it must separately approve one bounded resolution of this exact window, not replay R0 or invent a parser correction. No such call is requested implicitly by the 28-window manifest.

The independent Manchester UI limitation remains unmodified: first window was INCOMPLETE, later independent windows NOT_ATTEMPTED. No replacement denominator method has been silently introduced. Seven-council independent comparison is NOT complete. Before new source execution REVIEW must approve a feasible bounded independent method/session, or accept explicitly partial comparison; primary output cannot grade itself. Retain sealed evidence and independent chronology from the original run; do not copy new primary output into a denominator.

## Precise decisions / handoff

1. Owner securely completes the existing Supabase browser interaction so the correct production project and SQL editor can be verified; no credentials in chat. Then execute only the prepared frozen 80-identity read-only comparison under existing authority and reconcile results. If browser protection remains unusable, owner may run the exact query in the already-authorised production SQL editor and return only its bounded JSON output, not credentials.
2. REVIEW the offline continuation proposal and remaining denominator requirement before authorising its new registration/execution. No merge/registration is authorised in this task.
3. Keep Bury UNKNOWN separately; do not use it as a reason to restart source research or block safe observed-candidate comparison.

No new source calls, database query/mutation, admission, production workflow registration/dispatch, rerun/resume, models, schedules, deployment, Trafford work, Stockport reinvestigation or prospective acceptance occurred. Publication recall/unsupported latency remain UNKNOWN. MASTER STAGE 4 remains OPEN.
