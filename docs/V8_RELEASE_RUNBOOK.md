# V8 release runbook — live `28c2c16` (policy v4) → v8 master

Status: PREPARED, NOT EXECUTED. Every production step below needs separate Product Owner/REVIEW authority. Nothing here deploys, writes, resumes a cron or calls a model by itself.

## 0. Facts (read from the Render dashboard and git on 2026-10-07)

| Item | Value |
|---|---|
| Web service `PropertyAIgent` (`srv-d9qbl7qjnfac73d8nieg`) | branch `release/stage1-access-boundary`, live deploy `28c2c16`, `BUYER_MATCHING_POLICY_VERSION = 4`, Auto-Deploy OFF (header: "deployed with a specific commit"), PR previews off |
| Crons (Blueprint `exs-d9sv76h42hec73bp9q90`, branch master, last built `6fd4202`) | `daily-scrape` (command `/bin/true`), `intelligence-processing`, `weekly-opportunity-sync`, `historical-rebuild-overnight`: all **Suspended**, all Auto-Deploy OFF; Blueprint Auto Sync = No |
| `28c2c16` is an ancestor of master | yes (the live AH web-only/Stage 1 work is inside master) |
| Master | the release SHA recorded in `v8_pin.txt` / the report that accompanies this runbook |

## 1. Release delta matrix: live `28c2c16` → master (bounded; not a re-review of features)

Classes: **HANDLED** (already covered by code or an existing guard), **TRANSITION** (must be done before the web is reopened), **DEFER** (safe while crons stay suspended; becomes a requirement at cron reactivation), **BLOCKER** (none found).

| # | Delta (evidence) | Class | Why / action |
|---|---|---|---|
| 1 | Schema / migrations: `git diff 28c2c16..master -- app/db scripts/migrate_schema.py` is empty | HANDLED | No migration, no `verify_schema` change. Deploying code cannot leave the schema mixed. |
| 2 | Environment / config: no added `os.environ`/`getenv` reads; `render.yaml`, `requirements.txt`, `config/` unchanged | HANDLED | No new variable to set; no dependency to install. |
| 3 | Access policy: `app/security/` unchanged since `28c2c16` | HANDLED | The live web policy file keeps working. New CLIs are launch-scoped (Stage 1 CLI manifest) and need the local transition policy only for the operator launchers. |
| 4 | Buyer matching policy 4 → 8 (`BUYER_MATCHING_POLICY_VERSION`) | HANDLED + TRANSITION | Live feeds/pages use the v8 matcher on deploy (deterministic, no persisted effect). Mandate baselines become stale → see #6. |
| 5 | Persisted mandate rule data (Nesten correction) | HANDLED | Already applied to production by the audited, digest-bound sync (Product Owner run). |
| 6 | Mandate onboarding baselines (`matching_fingerprint`, `onboarding_*`) computed under policy 4 are stale under v8 | TRANSITION | Standalone re-onboarding (dry run → digest → apply, with the frozen-v7 differential). Until applied, the stale-mandate guard refuses paid agent evaluations (`StaleMandateBaseline`), so a code-only deploy cannot produce a mixed-version evaluation. |
| 7 | Strategic opportunity evidence fingerprints: v8 adds `capacity_semantics` for non-exact capacities only | TRANSITION (monitoring) | Digest-bound rebaseline (Category C engine). Matters only to ordinary monitoring; with crons suspended it cannot fire, but it must be done before the first sync and is done before reopen per the order below. |
| 8 | Planning-delivery opportunity identities/fingerprints: earlier commits since `28c2c16` changed material-plot subjects, scoped unit counts, whole-site affordable reset on phase facts, canonical detector identity (G1A) | DEFER | Not v8-specific. The read-only dry run lists every such difference under `not_included` (never rebaselined here). It becomes a Category A/B/C manifest decision before cron reactivation. While the weekly sync, the daily lifecycle reassessment and bootstrap stay suspended nothing reads or rewrites these rows. |
| 9 | `AGENT_EVALUATION_INPUT_FINGERPRINT_VERSION` 2 → 3 | HANDLED | Only affects when a *paid* evaluation is persisted; paid actions are disabled and the stale-mandate guard also blocks. Stored history is preserved. |
| 10 | Agent-evaluation prompt text gained a POSSIBLE_FIT instruction without a policy-prompt version bump | DEFER | Only matters to paid evaluation (disabled). Record for the evaluation-refresh decision. |
| 11 | Allocation AI summary prompt v8 → v9; cross-site v1 → v2 | TRANSITION (presentation) | Persisted v8 narratives are now suppressed everywhere (`AI summary requires refresh.`), rows preserved. Cross-site summaries are on-demand and not persisted. Regeneration is a later, paid, separate decision. |
| 12 | New/changed UI pages (family dashboard, routes, residual context, shortlist/report columns) | HANDLED | Read-only presentation over existing tables; R1 is dormant (no producer), R2 is context text. |
| 13 | Residual figures in reports/CSV/PDF/AI grounding replaced by R2 context | HANDLED | Report CSV column renamed (`Potential Residual Scope`): downstream consumers of the old column name must be told (informational). |
| 14 | `app/pipeline/lapse_tracking.py`, `phase_tracking.py`, `epc_lookup.py`, `query_parser.py` changed | DEFER | Pipeline/enrichment/search-parse code used by crons or paid search; nothing runs while suspended. |
| 15 | New required production jobs / changed cron assumptions | HANDLED | None: cron commands, schedules and `render.yaml` unchanged; the daily-scrape `/bin/true` dashboard override differs from `render.yaml` (a Blueprint Sync would undo it — never sync). |
| 16 | Stage 1 CLI/service manifests gained entries | HANDLED | Registration only. |

**Blockers: none.** Items 6, 7, 11 are the transition requirements before reopen; 8, 10, 14 are explicit deferrals tied to cron reactivation.

## 2. Frozen-v7 oracle boundary

`verification/transition/frozen_v7_matcher.py` is a pinned, verbatim copy of the accepted **v7** matcher. It proves only the approved **v7 → v8 matcher semantic differences** on the same evidence (EQUAL or one of four narrow strategic transitions; any other difference fails the re-onboarding). It does **not** prove the broader live-v4 → v8 release delta, which is covered by section 1. It is not repurposed and its allow-list is not widened.

## 3. Rollback tooling (built; not executed)

| Forward write | Owned columns | Rollback command | Source of previous values |
|---|---|---|---|
| Strategic monitoring rebaseline | `OpportunityMonitoringState.fingerprint`, `fingerprint_fields` (+ `last_seen_at`, an ORM onupdate side effect) of the reviewed ids | `python -m scripts.v8_monitoring_rollback` (dry run default; `--apply --confirm "RESTORE PRE-V8 MONITORING FINGERPRINTS" --expect-digest <restore digest>`) | the forward **plan** + **result** artifacts (exact stored strings) |
| Stale-mandate re-onboarding | `BuyerMandate.matching_fingerprint`, `onboarding_completed_at`, `onboarding_summary` (+ `updated_at`) of the re-onboarded mandates | `python -m scripts.v8_reonboarding_rollback` (dry run default; `--apply --confirm "RESTORE PRE-V8 MANDATE BASELINES" --expect-digest <restore digest>`) | the forward **APPLIED report** (`restore_snapshot` per mandate) |

Both: re-read current state; refuse unless every row is exactly in the expected post-transition state; one transaction, full rollback on failure; audit file written before the write; no ordinary sync, no reseed, no model call. **Keep the forward artifacts** (`v8_rebaseline_artifacts`, `v8_artifacts`) — they are the rollback input. Offline test: forward → rollback → every column of every row equals the original.

## 4. Render deployment plan (web only)

Recommended mechanism — **deploy the exact SHA as a manual "specific commit" deploy, without changing the service's branch or any setting**:

1. Release SHA: the master SHA recorded in the release report (call it `R`). Confirm `git rev-parse origin/master == R`, CI green on `R`, and that no unmerged work exists.
2. (PO) Put the web service in **Maintenance Mode** (Settings → Maintenance Mode). Cron services are not touched.
3. (PO) Web service → Manual Deploy → **Deploy a specific commit** → paste `R` (the pinned 40-hex SHA). Auto-Deploy stays OFF; branch stays `release/stage1-access-boundary`; plan, env, start/pre-deploy commands are not edited. (Reasoning: editing the branch/plan/settings can itself deploy the linked branch head — observed on 2026-10-06 — so no setting is changed. Confirm before deploying that **Pre-Deploy Command** is empty.)
4. Wait for "Deploy live for `R`". Verify in the dashboard: header shows commit `R[:7]`, status Live; build/startup logs show Streamlit started with no migration or job execution.
5. Health, still closed: Render's own health check / "Live" status and the startup log. The in-app footer (APP_COMMIT, from `RENDER_GIT_COMMIT`) and `/_stcore/health` are checked at reopen (step 11 below) because Maintenance Mode intentionally serves a static page to every request.
6. Rollback of the deploy: Web service → Events/Deploys → **Rollback** to the `28c2c16` deploy (it is retained; the branch was never changed) or Manual Deploy → specific commit `28c2c16e3e715c806dfb33f7edfff65e2aaa5451`. Maintenance Mode stays on until the rollback is live. A deploy rollback does not undo database transitions — use the section 3 tools if (and only if) those were applied.

Proof that no scheduled processing starts because the web deploys: (a) the four crons are separate services, each shown **Suspended**, Auto-Deploy OFF; (b) Blueprint Auto Sync = No and `render.yaml` is unchanged; (c) the web start command is the Streamlit server (`streamlit run app/ui/server.py`, spec 020; `app/ui/server.py` and `streamlit_app.py` are unchanged since `28c2c16`) and it neither imports nor schedules the sync/scrape/processing entry points (they are `launch:`-scoped CLIs); confirm the Start Command field on the dashboard before deploying; (d) the daily-scrape service command is `/bin/true`. Re-verify (a)–(d) on the dashboard immediately before and after the deploy. **Never press "Sync Blueprint", resume a cron, or change a cron branch/command.**

## 5. Transition order

0. Verify all scheduled paths remain suspended (dashboard: 4 crons Suspended + Auto-Deploy OFF; Blueprint Auto Sync No).
1. Maintenance Mode ON; deploy `R` (section 4).
2. Verify the deploy (dashboard commit, Live, startup log); do not open normal processing.
3. `run_v8_01_ai_staleness_preview.ps1` (read-only census; informational once stale narratives are suppressed).
4. `run_v8_02_rebaseline_dry_run.ps1` (read-only plan + digest; coinciding genuine changes block and are returned to REVIEW).
5. `run_v8_04_reonboard_dry_run.ps1` (read-only; frozen-v7 differential by category + digest).
6. Return the dry-run artifacts to REVIEW. **STOP — separate authority.**
7. After authority: `run_v8_03_rebaseline_apply.ps1 -PlanDigest <digest>`.
8. After authority: `run_v8_05_reonboard_apply.ps1 -PlanDigest <digest>`.
9. `run_v8_06_gate_b_v8.ps1` (read-only; `gate-b1-local`, `--skip-legacy`).
10. REVIEW GO / NO-GO.
11. On GO: Maintenance Mode OFF; check the footer SHA = `R[:7]` and `/_stcore/health`; REVIEW accepts the web release.
12. Cron activation is a later, separate decision (it also requires the item-8 planning-delivery monitoring decision).

Order challenged: steps 7 and 8 are independent (monitoring vs mandate tables) and may run in either order; the written order is kept. Step 5 (re-onboarding dry run) is unaffected by step 7 because the plan reads the universe and mandates, not the monitoring table. No additional dependency was found.

## 6. Rollback procedure summary

| Situation | Action |
|---|---|
| Deploy looks wrong, no DB transition applied | Rollback deploy to `28c2c16` (section 4.6). |
| Rebaseline applied, must undo | `run_v8_rb1_monitoring_rollback_dry_run.ps1` → review digest → `…_apply.ps1`. |
| Re-onboarding applied, must undo | `run_v8_rb2_reonboard_rollback_dry_run.ps1` → review digest → `…_apply.ps1`. |
| Both applied and code rolled back | Roll back the DB tools first (either order), then the deploy, so the live v4 code never reads half-restored state; keep Maintenance Mode on throughout. |
| A rollback tool refuses | The refusal names the drifted rows; do not force. Return to REVIEW. |
