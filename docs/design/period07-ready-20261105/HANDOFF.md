# Period 07 ready for one official live B test

MASTER STAGE 4 — OPEN. Readiness gate passed; collection → retention → screening → backlog acceptance remains outstanding. STOPPED before `run-successor`.

## Exact execution route and revisions

Used the authenticated Render Web Shell of owner web service `srv-d9qbl7qjnfac73d8nieg`, workspace `tea-d9qbf8jm8hqs7385cu0g`, existing protected configuration and existing encrypted database journal. No owner credential transfer or new web deployment was needed. The running web remains `2fa0f07cfdfb56a27243ebff18110d441f9da04d`.

Owner checkout: `/tmp/propertyaigent-owner07-54700366`, final executable owner revision `e191729bd9f05224932fef9903341d99d63650de`, branch `prep/period07-owner-readiness-20261105`. This is distinct from the scraper release.

The scraper source branch `prep/b-timing-pg17-current-20261103` was fast-forwarded from `da8959d06bea35da5104fe6638aa566952004853` to `54700366bab5434a5cda30abc853e0dc6dcc5d33`. Comparison showed ahead 10 / behind 0, with the reviewed 16 changed paths. Independent branch readback returned exactly `54700366bab5434a5cda30abc853e0dc6dcc5d33`.

## Committed database results

Executed `settle` once, then `dispose` once. Each entry point committed and verified its result through a separate read-only connection. Final independent disposition readback also passed after preparation.

- Attempt06 original marker and failure receipt retained under period history; active OPEN marker retired.
- Tameside: `SAFETY_BLOCKED / RECOVERED`, fence 2; former fence-1 attempt finished as `RECOVERED`; no replay authorised.
- Historical Tameside actual count and polling cause remain UNKNOWN. Manchester remains NOT_ATTEMPTED.
- Recovery advanced generation 6 → 7. Disposition preserved generation 7 and `last_hard_stop=ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP`.
- Only the receipt-bound global/manual failure stops became null. Other control state was preserved by the reviewed transaction comparisons.
- Temporary recovery/owner authority and schema CREATE permission removed; stable password verifiers MATCH, logins disabled, runtime memberships 0, pipeline sessions 0.
- Attempt06 encrypted journal unchanged: `1a2ec3d7176c142ac356daa6eae1667f0dfe75c84b29a0e9c64494a64105878f`, ordinal 55, 17096 encrypted bytes.
- Recovery receipt: `25470c04237b8cc167b4ceb6a10dc612601683108f27aebffab9ad61dd778b6e`.
- Original result/event hashes remain `3386dfb045fe64cd149faea835a0b377b7d25e3733eb53e31fd6687644de1e11` / `8a23b2641ce84002f7c726aa9de6681570b7d12ce8f874fc639910cf03ee0294`.

## Artifact, startup and restoration

One reviewed preparation build: `dep-dbm702rbc2fs738gfuv0`, live 2026-11-05T12:02:58.442297Z.

One startup-only job: `job-dbm710tg1s2s73ca9v90`, succeeded, finished 2026-11-05T12:04:00Z. Independently retrieved Render receipt proves:

- Commit `54700366bab5434a5cda30abc853e0dc6dcc5d33`.
- Tree `95bfb2677cddfe539b8b69945d870f6c8b5eb62e`.
- Workflow SHA-256 `e5289d43dbd05f2ffa051529c4feeb6aa32fb719c621de00df3638e077bf78e4`.
- Manifest SHA-256 `482e137a9a62fdd1007ee351845a4fc2c0825693dfc3472217c2ac8d4c3b74fc`.
- Canonical execution-binding hash `56d001cfe9f60e24d4ed468d53727c879e7e0ea8f392fe15995dd2bcf9717c1c`.
- Clean checkout at `/opt/render/project/src`, zero runtime authentication attempts, zero council requests.
- Startup receipt hash `57e083c78c06baa17eb13a0b97378084d068d11d6c5c476dc9caf2b27bfcfe5c`.

The build canary launched and closed Chromium. Browser binary SHA-256 `ded93a9c9a53a1ae040f08124badcca95c938e9d5015ff340c3b5538c41bf39e`.

Independent owner readbacks verified exact baseline configuration/environment equality and suspension. Separate Render connector readback confirms cron service `crn-d9sv93vavr4c73f98rb0`: suspended, auto-deploy off, branch restored to master, start command `/bin/true`, baseline build command restored. GitHub publication remains NOT_REQUESTED; its installation was not modified or reopened in this work.

## Compatibility fixes and partial effects

The standalone PR207 CLI predated the deployed journal's compressed metadata format. Its first read-only inspection refused `A06_PREDECESSOR_CLOSURE` without a live write. Reused the deployed lossless reader; all predecessor/recovery guards stayed intact (`7e3c6f45ac08cdae960794e0d52b4ffe439d9f90`, fixture correction `dfb7f5ef1ee3d35d161704c11c7b8ac3adaa2121`).

Preparation built and submitted the single startup check successfully, but a later provider read timed out. It recorded `ReadTimeout / STARTUP_PREFLIGHT_JOB / RECONCILIATION_REQUIRED`. No build or job was repeated. The exact existing startup-reconciliation pattern was bound to the period07 job, deploy, receipt hash and refusal-journal hash; it verified provider state and retained the receipt through independent journal readback (`76ae2757447d6127799fb14721003f8b95d2903b`). The timeout remains recorded as preparation history.

Readiness then refused `OWNER_CLEANUP_RESERVE_BYTE_BOUND` with the old writer. Reused the deployed metadata encoding, root-referenced period checkpoint and full late-phase capacity projection (`e191729bd9f05224932fef9903341d99d63650de`). No storage ceiling or reserve was increased. Scraper source, worker guards, intake_finish and database recovery semantics remain unchanged.

Hosted focused regression set: 44 passed, 2 failures. The same two failures were independently reproduced on unmodified `54700366`: `test_connected_owner_prepare_run_and_independent_closure_mocked` lacks `startup_preflight`; `test_closed_predecessor_binding_preserves_bytes_and_fixed_window` uses the obsolete predecessor snapshot. These are older fixture failures, not introduced by this change. The 26 compatibility/reconciliation/successor-specific cases passed, including malformed metadata, changed identity/state, zero provider mutation and idempotent readback after a lost acknowledgement. Local new compatibility/reconciliation tests: 18 passed. These hosted checks used the existing Render runtime; they are not new GitHub CI results. Reused accepted PR207 PostgreSQL evidence for unchanged recovery transactions, additionally verified their actual committed live effects.

## Final connected readiness evidence

At 2026-11-05T12:13:55.086781Z, `verify-successor` returned `RELEASE_BINDING_VERIFIED_READ_ONLY`:

- Max runs 1; no release intent, no access opened, no intake job created, no provider mutations, no deadline frozen.
- Period07 remains unregistered and unused; only the startup-only job exists since preparation.
- Journal ordinal 23 / 13236 ciphertext bytes; unchanged by verification; hash `33f5b1609de158f025dc3e765b1ae82322676f2c17fd84d8f1d5311dca975a9f`.
- Full modeled normal-phase maximum 17672 ciphertext bytes under 22152; remaining margin 4480 bytes.
- Projected last normal ordinal 46 under 47; all 16 cleanup snapshots retained. Projected worst cleanup ciphertext 28296 under the unchanged 32768-byte storage bound.
- Runtime roles dormant, stable verifiers MATCH, pipeline sessions ABSENT, runtime memberships ABSENT, temporary owner ABSENT.

Capacity is a bounded projection, not proof of future collection success. Period07 qualification, actual council coverage, durable capture, screening and discoverable backlog remain for the official B test.

## Exact next start action — INACTIVE, NOT EXECUTED

Use the existing authenticated owner web service's Render Web Shell. The current checkout above is ready. Before starting, make a fresh actual Dashboard isolation observation for the scraper: no linked environment groups or inherited credential sources, no secret files, no other running/queued jobs or deploys, cron suspended and no concurrent owner operation. The reviewed guard requires this observation within 300 seconds. Record the time only after that observation; do not reuse a historical timestamp.

```bash
cd /tmp/propertyaigent-owner07-54700366
test "$(git rev-parse HEAD)" = e191729bd9f05224932fef9903341d99d63650de &&
P07_OWNER_CHECKED_AT="$(date +%s)" &&
PROPERTYAIGENT_OWNER_PILOT_AUTHORITY=b-dbpilot-20261027-1102-07 python -B -m scripts.owner_attempt06 --action run-successor --owner-checked-at "$P07_OWNER_CHECKED_AT"
```

If the ephemeral checkout is no longer present after a service restart, fetch the pinned owner revision into a detached checkout using the existing hosted configuration, then run read-only `verify-successor` before the fresh isolation observation. Do not recreate credentials or rerun settle/dispose/prepare/reconcile-startup.

Scope remains 27 October–2 November 2026 inclusive; Tameside RECEIVED and Manchester VALIDATED. Tameside: 10 requests, 3,000,000 bytes, 6 pages × 5 listings, 45 source seconds. Manchester: 80 requests, 20 MiB, 60 listings, 6 pages, 75 source seconds. Aggregate job envelope 960 seconds; existing resource/cost controls unchanged. No publication.

On any uncertain write or submission, use read-only `status` and exact provider readback before any further action; never repeat `run-successor` to discover whether it ran. Success must separately establish actual coverage, durable hash readback, screening, backlog, independent closure and restoration. This handoff authorises no additional submission beyond the owner's next instruction. Stage 4 remains OPEN for acceptance.
