# Manchester isolated initial navigation — completed

Stage 4 OPEN. GO for accepting this bounded diagnostic; NO-GO for claiming Manchester collection/coverage or a completed live B test.

## Change and validation

PR #211 code revision 32410a68d06412a2c74c0aff818b4a19471e8ab0; tree 1d82bbb6c342a9f8cffe2eabc7681182e96901de. Applied the approved diagnostic-only RLIMIT_FSIZE increase from 512 KiB to 20 MiB. The exact fixed Manchester diagnostic plan is checked before the increased limit is installed. Normal collection and other modes retain 512 KiB. No production collector deployment occurred.

The actual patched worker, without a limit override on the success path, passed hosted Chromium/supervisor proof. The retained negative fixture deliberately reinstates 512 KiB and reproduces ERR_ABORTED. Focused tests verify exact plan/limit selection, scope refusal before transport, single request dispatch, blocked redirects/subresources, zero retries, failure cleanup and no owned survivors.

- Navigation CI run 42104495295, job 127515616614: 47 passed in 5.76 seconds.
- PostgreSQL settlement CI run 42104495458, job 127515617262: 26 passed in 49.54 seconds.
- Local focused selection: 18 passed, three native-browser skips, three supervisor deselections. Hosted results supply native validation. Not a whole-repository green claim.

## Single live execution

Job job-dbmehqrbc2fs7381np50, created 2026-11-05T20:36:59.673664Z, terminal succeeded at 2026-11-05T20:37:51Z. Exactly one submission; no retries. An exclusive local intent was fsynced before POST, and acknowledgement retained. Intent/ack and approved command remain in /tmp/pai-mnav-owner; this temporary filesystem is not the durable archive. Provider job history and this committed sanitized evidence preserve the outcome.

Approved command SHA-256 f3f9592728a9c3826a71a6c571e43e6e29eb60392765904e7c08597897f2fb11.

The isolated one-off job reused scraper artifact dep-dbma8cg8v5cc73e1enqg at 3adb65d06d0492d3b8f9b798e49e3be20699b082. Bootstrap verified its Git HEAD and actual Chromium executable hash ded93a9c9a53a1ae040f08124badcca95c938e9d5015ff340c3b5538c41bf39e before running diagnostic revision 32410a68d06412a2c74c0aff818b4a19471e8ab0. The source subprocess environment excluded database credentials and provider credentials. Source setup used the existing artifact; no service deployment/configuration change.

Bounded observation at 2026-11-05T20:37:45.38858976Z:

| Field | Result |
|---|---|
| Scope | Manchester VALIDATED, 27 October–2 November 2026 inclusive |
| Status / stage | FIRST_RESPONSE_OBSERVED / INITIAL_NAVIGATION |
| Physical council requests | 1 |
| Responses / status | 1 / HTTP 200 |
| Further request attempts blocked before transport | 3 |
| Retries | 0 |
| Exception class | null |
| Network error | UNKNOWN (no error observed; not a diagnosed failure) |
| Browser elapsed | 2.118 seconds |
| Supervised elapsed | 4.379216089844704 seconds |
| Peak owned RSS | 659283968 bytes, below 1 GiB |
| Exit / limits | 0; no limit hit; not expired |
| Browser cleanup | CONTEXT_BROWSER_CLOSED |
| Supervisor cleanup | CLOSED; accounting_complete true; live_owned_survivors 0 |
| Coverage | NOT_ESTABLISHED |

The observation stops at response headers. Its byte-event counter is 0; this is not a claim that the network transferred zero bytes. No body, DOM, cookies, session tokens or raw request URLs were retained. The three blocked request attempts were not classified in retained output, so no unsupported claim is made about which were redirects versus subresources.

Sanitized provider evidence: MANCHESTER-INITIAL-NAVIGATION-LIVE.json, SHA-256 a2714385066bd6741f0bcfecd83832cc728d9b79a2b20c522cb1270ec5ec2f34. Provider log ID 006507e3-0ca4-493a-b751-020a45fa692a. This task consumed the one approved diagnostic opportunity; do not resubmit it.

## Independent settlement and cleanup readback

Fresh database connections before and after execution returned COMMITTED_STATE_VERIFIED_READ_ONLY for period08/run768e1bd059474281ae9dc5113db42a99 with receipt 838d00b6b6a87dba856027bf5a4e60852d0f3ae3688db3e5baae4f35d0b1f24f. The validator checks original evidence, prior history, Tameside fingerprint, recovered Manchester claim, closed attempt, absent checkpoints and removed temporary permissions. Generation remains 11, global DAILY_INTAKE_SHARED_FAILURE active, manual_stop and last_hard_stop ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP.

Independent final provider/database readback at 2026-11-05T20:38:09.440287+00:00:

- Job succeeded; terminal jobs 20→21, deployments remain 74. No competing active jobs/deployments in complete inventory.
- Scraper suspended; exact baseline configuration and environment equal; artifact unchanged.
- Both restricted logins disabled; runtime memberships 0; pipeline sessions 0; temporary owner absent; stable credential verifiers MATCH.
- Encrypted owner journal unchanged: 6cd68c0f6fc43bfda8b884eb08ae9dc873e24e95ca10d4626d53da22af8d6d4f.
- Read-only verification transactions ended ROLLBACK. No recovery or stop write occurred in this task.
- Private bounded readback /tmp/pai-mnav-owner/mnav-final-readback.json SHA-256 26ee4bf8b1cdd24547d6033a535860183163bf350d4f85cd71cb782f87f7e527.

Tameside's accepted period08 capture, 24 screenings, five metadata batches and 24 backlog records remain preserved. Period08 remains consumed. Prior period07 and Attempt06 histories remain unchanged. Scheduled collection remains suspended; GitHub publication NOT_REQUESTED.

## Interpretation and next decision

The revised isolated worker can reach Manchester and obtain HTTP 200 on the retained Render browser/artifact. Offline testing demonstrates that the inherited per-file ceiling can abort this browser path. Historical period08's exact exception was discarded, so its cause remains UNKNOWN; do not rewrite the historical outcome or its one-request accounting.

HTTP 200 does not establish a usable search form, query submission, pagination, terminal-page coverage, retention, screening or backlog. No additional live request was made to inspect these. No further code correction is justified by this successful header-only observation.

Smallest next approval: prepare and validate offline a Manchester-only successor through the existing owner path, including an evidence-backed browser-compatible file limit for that collector path and explicit completion rules linking the accepted Tameside period08 evidence without rerunning it. Preserve separate council/run provenance and completeness guards. Normal collection still retains 512 KiB today, so this diagnostic fix alone does not make the production collector ready.

Return an exact release/receipt-bound stop-disposition and single-use submission proposal for REVIEW before any new live request, deployment, stop clearance or access reopening. Do not authorize a two-council rerun merely to satisfy an existing fixed owner route. Stage 4 remains OPEN.
