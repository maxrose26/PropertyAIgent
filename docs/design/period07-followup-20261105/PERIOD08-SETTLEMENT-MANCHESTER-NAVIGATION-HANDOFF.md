# Period 08 settlement and Manchester navigation handoff

MASTER STAGE 4 OPEN. Settlement GO; live navigation diagnostic NO-GO under the unchanged per-file ceiling. No new council request, Render job, production deployment, stop clearance, runtime reopening or intake submission occurred. The one approved live diagnostic remains unused.

## Exact baseline and committed settlement

Period b-dbpilot-20261027-1102-08; run 768e1bd059474281ae9dc5113db42a99; original job job-dbmacl5g1s2s73civi60. Reviewed settlement implementation 98eaff0636a0efbdec8e9ca73f4a40c6a720a9c0 is code-identical to validated checkout 46b7907970f84d39d582990300281b3e93a4cfbe. The existing owner shell executed scripts.owner_period08_settlement --action settle exactly once after its read-only preflight passed. No retry occurred.

Fresh-connection inspection returned COMMITTED_STATE_VERIFIED_READ_ONLY. Final independent readback at 2026-11-05T18:03:30.800107+00:00 confirmed:

- Exact original marker archived; active marker retired; receipt SHA-256 838d00b6b6a87dba856027bf5a4e60852d0f3ae3688db3e5baae4f35d0b1f24f.
- Manchester item SAFETY_BLOCKED / RECOVERED at fence 2; original fence-1 attempt RECOVERED and finished; both checkpoints absent.
- Generation 11. global_stop remains {reason: DAILY_INTAKE_SHARED_FAILURE}. manual_stop and last_hard_stop are ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP.
- Recovery SET and USAGE false; temporary owner absent. Restricted logins disabled, runtime memberships 0, pipeline sessions 0, stable credential binding MATCH.
- Tameside completed-work fingerprint unchanged: 959cc7c96a9fcd90446472da56e2209cacedbbef4fa3ea441d82d215fcf62f09. Completed capture, 24 screenings, five metadata batches and 24 discoverable backlog records preserved. The actual backlog_page product read independently returned 24 current-rule COMPLETE Tameside records in a transaction ending ROLLBACK.
- Prior period history/evidence preserved, including Attempt06 UNKNOWN cause/count and period07 failed coverage/three requests/Manchester NOT_ATTEMPTED.
- Owner journal unchanged at ordinal 56, SHA-256 6cd68c0f6fc43bfda8b884eb08ae9dc873e24e95ca10d4626d53da22af8d6d4f.

Private bounded readback: /tmp/pai-mnav-owner/final-settlement-readback.json; SHA-256 61a5f703855adb414bd36b98c1c08c76e0e43fa68ccc84898333f43422809fa6. Its inspection transactions ended ROLLBACK; this does not undo the separately committed settlement.

Original artifact hashes verified unchanged:

| Artifact | SHA-256 |
|---|---|
| capture-1/source.json | 4691339a26f8bd4e86ea6df92e6730bcd964304753fe2ce4760e69685a993fd3 |
| capture-2/source.json | d21c771f96138af731d05445b45e1a155c26d1306a7419a488c21feb559d3698 |
| final/events-before-publication.json | 8fa7b51bbeb9a7f113b8b641908397e0c3e5509c699125e95826ffe4b271f2d3 |
| final/result-before-publication.json | 03db3bcdfc8c3a4e2fdbc901bb1525c55d7932f9d878da3501af45826e6c7051 |

## Diagnostic implementation and offline evidence

PR #211 validation revision: fb7836ca951a448caa599ac2094c3853a43e1e8c. Diagnostic implementation includes 85f4807e2644de9677555537b1f9d89dc90fd362; later commits refine disposable fixtures and prove the file-limit boundary.

The fixed source-worker mode is Manchester VALIDATED, 27 October–2 November 2026 inclusive. CDP interception reserves the single request slot before dispatch, blocks subsequent/redirect/subresource requests, uses zero retries, a 25-second navigation timeout and the existing supervisor's 45-second process limit. Credential-free environment, browser cleanup, bounded error class/stage/allowlisted network code, 20 MiB source-byte ceiling and 1 GiB source-process-group RSS are retained. No raw pages, cookies, tokens, credentials or request URLs are retained. Normal collection and SOURCE_SAFETY remain unchanged.

GitHub Actions run 42079685633, job 127429162444: **44 passed in 7.70 seconds**. Artifact 13438364497, ZIP SHA-256 6702d9b28aeca1b228bd40dd044998e0b2ab89ddb1ede73cc7ef6d7a3bc020a9. Real Chromium loopback transport tests prove one server request for normal, redirect and disconnect cases; subresource/redirect attempts never become additional physical requests. Actual supervised worker tests verify accounting and zero surviving owned processes. Same-revision PostgreSQL settlement workflow 42079685710, job 127429162567: 26 passed in 45.49 seconds. This is focused validation, not a claim that every repository workflow is green.

The decisive actual-worker comparison changes only inherited RLIMIT_FSIZE in a disposable child:

| Per-file ceiling | Physical loopback requests | Result | Cleanup |
|---|---:|---|---|
| 512 KiB (existing) | 1 | 0 responses, ERR_ABORTED | CLOSED; no survivors |
| 20 MiB (prototype) | 1 | 1 response, HTTP 200 | CLOSED; no survivors |

The passing suite deliberately asserts the existing-limit failure and the prototype success. It does NOT prove the unmodified worker ready for live diagnosis. A small response-observation fallback also has a regression: retain the response returned by page.goto when its separate CDP event has not yet been observed. This is an offline diagnostic reliability fix, not a demonstrated historical cause.

Earlier native owner-web tests hit the 45-second deadline on its 512 MiB host; cleanup reported no survivors. No OOM or restart cause was established. Work Mode native process-accounting tests were not usable in its namespace. Final native proof used disposable hosted CI. Earlier CI attempts exposed the response failure above; optional browser-font installation also timed out before tests and was removed in favour of runner-provided dependencies. No production limit was raised.

## What remains UNKNOWN

The original Manchester period08 first-request exception detail was discarded. Its historical cause remains UNKNOWN; the new offline ERR_ABORTED reproduction is not proof of the original cause. Original Manchester accounting remains one request, zero responses and no coverage/checkpoint/screening/backlog. Tameside remains eight requests and accepted completed coverage; total period08 accounting remains nine requests. No live Manchester observation was obtained in this task.

CI Chromium was downloaded from the official Playwright distribution. A matching hash to the retained Render browser was not established by CI. Any eventual isolated job must verify the retained artifact/browser binding before its one request.

## Provider and access closure

Independent provider readback retained scraper artifact dep-dbma8cg8v5cc73e1enqg at 3adb65d06d0492d3b8f9b798e49e3be20699b082, tree 62b685ac7a2e826ad1f14bc4bb8ba98e42fe15eb. Scraper suspended; exact baseline configuration and environment equal. Provider inventory remained 74 terminal deploys and 20 terminal jobs. Owner web remains 2fa0f07cfdfb56a27243ebff18110d441f9da04d. No source branch movement, deployment, live diagnostic job or intake submission occurred. GitHub publication NOT_REQUESTED; scheduled collection suspended.

## Smallest REVIEW decision

Approve only the fixed Manchester diagnostic subprocess per-file RLIMIT_FSIZE increase from 512 KiB to 20 MiB. Preserve the 512 KiB retained-output/supervisor-output bounds, 20 MiB network-byte ceiling, 1 GiB source-group RSS, one outbound request, zero retries/redirect/subresource traversal, 25-second navigation and 45-second process limits. Normal collection stays at its existing file ceiling. Runtime DB access stays dormant and all intake stops stay active.

MANCHESTER-DIAGNOSTIC-FILE-CEILING-INACTIVE.patch is a review-only proposal, not applied or deployed. It admits the higher ceiling only for the exact diagnostic plan; normal paths retain 512 KiB. The hosted test used a disposable child-only setrlimit override, not this patch. After approval, apply the narrow patch, test that exact path and unchanged normal-path limit, recheck settlement/access/provider state and artifact/browser identity, then consume the still-unused one-shot diagnostic. Reconcile any uncertain job submission from journal/provider history before repetition. Do not reuse the previously prepared inactive command unchanged: it pins the old 512 KiB implementation and is blocked pending this decision.

No Manchester-only intake is approved here. That requires a later REVIEW decision and a supported owner-path completion policy that reconciles Manchester evidence with accepted Tameside period08 evidence. Do not rerun Tameside merely to satisfy a hard-coded two-council route. Stage 4 remains OPEN.
