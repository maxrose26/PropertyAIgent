# Inactive diagnostic staging proposal — 29 September 2026

No production change authorised or performed in this preparation. Gate A OPEN. Suspension review remains30September05:30BST, no automatic restart.

## Exact artifact and schema decision

Proposed executable commit92fdb0dcf653fda0a6be821da8fd54a417a5c9bd. Starting HEAD61c6fdbafc230742dbfb07d8c90d2a0e345d5a26, clean. Changes after executable:7bf32c4 operator/decision docs;61c6fdb suspension evidence/docs only. Application/migration/tests/dependencies unchanged after92fdb0d. Eight focused tests rerun passed, zero failures/skips; alarm0.223476s. No broad suite or new integration acceptance claimed.

Identity-only staging DOES NOT require migration, conditional on the entrypoint isolation below. Reviewed import chain: scripts is a namespace package; app/__init__.py and app/pipeline/__init__.py are empty; probe imports only stdlib and pure discovery_config. No models/session imports or startup hook. /bin/true imports nothing. Build installs dependencies and browser, then verify_browser_runtime imports Playwright and launches/closes a blank browser without application DB imports. Blueprint has no preDeploy migration hook. Review current effective build/predeploy fields again at deployment approval; unexpected hook stops staging. Dependencies in requirements.txt are not fully pinned: exact Git SHA does not prove identical built dependencies. Preserve build dependency/browser versions; this artifact is identity-only, not accepted full discovery release.

Other entrypoints are NOT made safe merely by deployment: daily supervisor imports ORM definitions but its disabled main branch precedes init_db; run_weekly verify_child precedes init_db. Do not execute either as an admission test. Intelligence, weekly opportunity sync, historical rebuild, web and manual scripts remain outside this deployment scope. They must not receive this candidate automatically. No global master merge/push is proposed. No claim every arbitrary script is safe on an unmigrated schema. This is controlled entrypoint isolation, not universal schema compatibility.

Migration delta for this diagnostic: ZERO. Existing proposed P0-A migration unchanged; remains separately required before discovery runs. No production preflight/migration needed for this identity-only decision. Do not use generic migrate_schema.

## Live configuration inspected read-only

Discovery service crn-d9sv93vavr4c73f98rb0 remains Suspended, deployed6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a, command python -u -m scripts.run_daily_councils, schedule0 5 * * *, master. Service Auto-Deploy visually verified On Commit. Blueprint propertyaigent-automation / exs-d9sv76h42hec73bp9q90 uses master/render.yaml; Auto Sync visually verified Yes. No secret exposed. Switch values not reread; proposed explicit values below must be established, not assumed.

| Control | Current | Proposed before staging |
|---|---|---|
| Blueprint Auto Sync | Yes | No (first approval only) |
| Discovery Auto-Deploy | On Commit | Off (later approval) |
| Discovery suspension | Suspended | Remains suspended |
| Command | python -u -m scripts.run_daily_councils | /bin/true |
| Schedule | 0 5 * * * | Unchanged while parked |
| PROPERTYAIGENT_DISCOVERY_ACTIVATED | Not reread | 0 |
| PROPERTYAIGENT_DISCOVERY_DISABLED | Not reread | 1 |
| PROPERTYAIGENT_DISCOVERY_MODE | Not reread | disabled |
| Service branch | master | Dedicated diagnostic staging ref at exact92fdb0d, later approval |
| Blueprint branch/path | master/render.yaml | Unchanged; do not sync |
| Build/plan/secrets/other services | Existing | Unchanged |

Repository delta now: this proposal only. No actual render.yaml edit. Later propose publishing ONLY a dedicated diagnostic branch/ref pointing at92fdb0d (for example release/p0a-identity-only), after checking remote ref absent or exact and auditing workflows for push triggers. No master push/merge. Prior to approving publication inspect whether any GitHub workflow would contact paid/production services; do not publish first and discover later. Render source-branch selection/manual exact-commit deployment mechanics must be verified before its own approval. Do not silently deploy documentation HEAD instead. These are future preflight checks, not publication approval.

Blueprint protection: Auto SyncNo blocks automatic Blueprint reconciliation but not service auto-deploy, manual sync or sync hook. Therefore no manual/hook sync during staging; separate service Auto-DeployOff before publication. No shared Blueprint sync of candidate, as it includes other jobs. Before eventually re-enabling Auto Sync, review master/render.yaml to preserve intended parked/disabled discovery state, review sync plan and other resources, then obtain separate approval. Rollback code only while externally suspended/parked; re-read state afterwards. Old code ignores P0-A flags. Never roll back by restoring discovery command or enabling sync.

## Finite approval sequence

A. Approve only Blueprint Auto Sync Yes→No, save, refresh and verify No plus discovery remains suspended. This is Blueprint-wide: existing other jobs keep their schedules/code, but future automatic YAML configuration updates for all managed resources stop. No service Auto-Deploy change yet. If save fails report/no progress; if an unexpected sync starts do not assume safe or cancel without authority. Reversion to Yes requires a reviewed Blueprint diff and explicit approval, since it removes protection.
B. Separately approve discovery Auto-DeployOff; verify. Then separately approve parking/three disabled settings while suspended, accounting for any platform-triggered build before proceeding.
C. Review remote/workflow/deployment preflight; separately approve publishing exact staging ref, then separately approve inactive deployment from it. Verify SHA/source hash/build manifest, command /bin/true, suspended status, disabled flags and no active discovery. Do not invoke discovery main to prove guards. Existing pure helper test plus external parked/suspended state provides admission evidence. SCHEDULED_INSTANCE_PATTERN remains None.
D. Separately approve actual date/window, temporary diagnostic command/schedule, one scheduled invocation and restoration; follow P0A_FIRST_SCHEDULED_DIAGNOSTIC_PROCEDURE.md. No date committed. A present operator must match TRIGGER Scheduled/run-linked logs/unique marker/SHA/instance and restore suspension and /bin/true. Exit3 means evidence captured, identity unverified in-process; never hide with ||true. Recurring cron expression and date guard do not replace restoration. Ambiguous correlation stops progression.
E. Review identity contract, separate read-only DB-path diagnostic and clock finding; only later exact migration, tested admission and bounded Manchester smoke approvals. No automatic progression to Salford/all councils.

## Preserved limitations

WSL additional monotonic lower-bound failure remains a failure, not baseline-equivalent. Four baseline failures and one deselected memory test remain visible. Identity staging is not Gate A closure, OOM root-cause resolution or egress remediation. No new schema or orchestration framework. This document is self-review, not independent production approval.

## Approved discovery Auto-Deploy change completed29September

Explicit approval limited to discovery service Auto-DeployOn Commit→Off. Saved and refreshed Render confirms Off, Suspended, command python -u -m scripts.run_daily_councils, schedule0 5 * * *, deployed6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a unchanged. No deployment triggered by the operator; no command/schedule/branch/other-service setting changed. Blueprint Auto Sync remains off under prior approval; not modified in this action. Screenshot docs/reports/p0a-auto-deploy-off-20260929.jpg. Review30September05:30BST retained; no automatic restoration. Parking command and inactive switches remain separately unapproved.

## Approved command parking completed 29 September

Explicit approval limited to changing the discovery command to /bin/true while suspended. The edit showed Save Changes with no indication of deployment, resumption, execution or additional changes. Saved and refreshed Settings confirms command /bin/true, Suspended, schedule 0 5 * * *, deployed SHA 6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a and Auto-Deploy Off. No other setting was edited. Screenshot: docs/reports/p0a-command-parked-20260929.jpg. Blueprint Auto Sync was not changed. The 30 September 05:30 UK review checkpoint remains; no automatic restart. Inactive environment switches and all later deployment/diagnostic/migration actions remain separately unapproved. Gate A remains open.
