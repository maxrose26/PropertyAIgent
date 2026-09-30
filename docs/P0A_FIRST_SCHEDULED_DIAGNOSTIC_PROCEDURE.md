# P0-A identity-only diagnostic: local review package

29 September 2026. NOT production approval. Gate A OPEN. Supersedes the earlier proposed identity attestation checkpoint: no transport or guessed instance pattern has been introduced. Specification 019 and roadmap unchanged.

## Decision and executable scope

`scripts/p0a_scheduled_diagnostic.py` is now executable, standard-library only except the existing pure discovery admission helper. It accepts only phase `identity`. It cannot open a database, network connection, launch a child, load .env, invoke discovery, reconcile, run a council or migrate. There is deliberately no database phase or identity override. This implements the expressly permitted identity-only fallback, not the complete proposed database diagnostic.

Render documents RENDER_INSTANCE_ID as a unique service-instance identifier, not a scheduled-run ID or trustworthy trigger-origin assertion. Unlisted environment variables are not a stable public contract. No safe in-process scheduled-run correlation was established. A temporary shell is rejected; any other syntactically valid instance remains UNVERIFIED. No API credentials are added. The previous 30-second external attestation idea is removed: a fabricated attestation would merely move the trust problem.

Positive evidence procedure: named operator opens the actual scheduled entry in Render Runs, records its run ID, scheduled trigger evidence, start/end/status and deployed SHA, then matches the probe's unique marker, exact SHA, instance and timestamp in THAT run's logs. Preserve the run-log association, not merely service-wide logs at a similar time. No manual Trigger Run or shell counts. If the UI does not positively establish origin or associate logs with the run, stop and request provider clarification. Missing triggeredBy alone is not positive proof. One observed instance is not a general instance-pattern contract or proof of successor uniqueness. The probe has already exited before this external assessment; no database work resumes automatically.

## Checks, output and containment

Require exact 40-character expected SHA equals RENDER_GIT_COMMIT, exact service crn-d9sv93vavr4c73f98rb0/type cron/RENDER true, explicit ACTIVATED=0, DISABLED=1, MODE=disabled under PROPERTYAIGENT_DISCOVERY_. Pure require_discovery_enabled must reject; discovery main/owner entry are never called. Window must be UTC, positive, at most120 seconds and current at both preflight and emission. SHA environment comparison is not cryptographic deployment attestation: operator must check deployed SHA and emitted source hash against the reviewed artifact.

Emit a single <=4096-byte nonblocking JSON record: version, identity_unverified, database_access=false, discovery_admission=disabled, service, sanitized instance, SHA, random marker, PID, wall and monotonic sample, source SHA256, scheduled_origin_verified=false. No DSN, exception text, arbitrary args or full environment. Exit3 means identity evidence collected but unverified, not a passed diagnostic. Exit2 preflight rejection; exit4 failed log write; exit124 emergency termination. Missing output is failure. No zero exit path or retry.

Five-second ITIMER_REAL emergency termination calls os._exit without logging/persistence. It is NOT the application watchdog, cooperative browser cancellation or proof of Render clock safety. There are no resource-owning children/DB sessions to clean up. GNU timeout outer15s +2s kill escalation covers interpreter startup; confirm its availability before deployment approval. No physically guaranteed wall duration under host stall/uninterruptible kernel waits is claimed. Clock samples are identity timestamps, NOT a 15-second timeout measurement. Existing monotonic failure remains unresolved.

## Current and proposed production settings

Read-only Render Settings inspected29September in this preparation: Blueprint managed, Python3/Standard, master, deployed6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a, schedule0 5 * * *, command python -u -m scripts.run_daily_councils, Suspend Cron Job control (enabled). Build command matches render.yaml: pip install -r requirements.txt && playwright install chromium && python -m scripts.verify_browser_runtime. No settings changed. Active-run terminal state and Blueprint Auto Sync/service Auto-Deploy values must be refreshed before action; unavailable values are not assumed off. Current switch values were not reread. Old code ignores P0-A switches regardless.

| Setting | Current verified / limitation | Proposed during preparation / final safe state |
|---|---|---|
| Scheduler | Enabled | Suspended |
| Command | python -u -m scripts.run_daily_councils | /bin/true |
| Schedule | 0 5 * * * | Retain while parked; temporary reviewed slot only for diagnostic |
| Branch | master | No change without deployment approval |
| Deployed SHA | 6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a | Exact reviewed diagnostic commit |
| Blueprint Auto Sync | Not freshly verified | No |
| Service Auto-Deploy | Not reliably read | Off |
| ACTIVATED / DISABLED / MODE | Not freshly verified | 0 / 1 / disabled |
| Standard/build command/secrets | As above; secrets not retrieved | Unchanged |

## Ordered actions — separate approvals, none executed

1. S: suspend only this old cron. Re-read Runs first; record scheduler suspension and terminal end/status of any active run. Suspension/build alone is not termination proof. If active, wait; cancellation needs separate approval. No command/deployment changes until no pending/active execution remains. Database running rows and age alone are insufficient.
2. D configuration controls: Blueprint Auto Sync=No and service Auto-Deploy=Off BEFORE an approved push. Set /bin/true while suspended; set three explicit disabled values. Verify effective state. No manual Blueprint sync: current render.yaml declares discovery command/schedule and can restore them; explicit sync can overwrite dashboard changes even with Auto Sync off. Branch, build, plan, schedule and declared env values are also overwrite risks. Keep other services unchanged. A reviewed inactive Blueprint delta must precede any future sync. No render.yaml edits in this artifact.
3. M remains separately required for a P0-A application release: only python -m scripts.migrate_p0a --apply from the reviewed commit following read-only preflight. Delta remains parent_lookup_work plus nullable TEXT scrape_runs.progress, no historical backfill/UPDATE. Identity-only probe technically needs no schema, so recommendation is to defer migration until its independent approval; this is a disclosed diagnostic-only staging choice, NOT permission to activate unmigrated code. Migration-first remains mandatory before discovery release.
4. D: separately approved push/deployment of the exact artifact while externally suspended/parked. Verify deployment SHA, source hash, disabled values, command, no active discovery and no unexpected Blueprint sync. The reviewed application ownership pattern remains None. Do not enable it based solely on this probe.
5. X: operator Max (account owner), assisted in this Astra chat only while present, selects a future UTC slot and explicitly approves execution/restoration scope. No30September slot is committed. For example ONLY, a30September09:00UTC slot would use schedule `0 9 30 9 *` and window09:00:00Z–09:02:00Z. Before resume, replace D with exact reviewed commit in:

   `timeout --signal=TERM --kill-after=2s 15s python -u -m scripts.p0a_scheduled_diagnostic --phase identity --expected-sha D --not-before 2026-09-30T09:00:00Z --expires 2026-09-30T09:02:00Z`

   This is an unapproved example, not a command to execute now. Verify effective config and deployment after changes; resume only for the diagnostic command, never Trigger Run. Cron repeats annually: the window guard rejects later years but external suspension is the primary safeguard. Do not schedule unless Max or an explicitly approved present operator accepts responsibility for restoration. Astra is not an unattended monitoring service.
6. Immediately after the terminal run, that operator suspends again, checks no queued/active job, restores /bin/true and0 5 * * * while remaining suspended, confirms disabled flags and sync/autodeploy off, captures logs and matching run record. Expected exit3 will show unsuccessful: do not mask with `|| true`. Missing output, identity ambiguity, unexpected SHA, timeout or any failed guard ends the procedure. No automatic retry, DB phase, watchdog phase, smoke or1October resume.

Rollback: remain suspended and parked BEFORE rollback; retain sync/autodeploy locks. Old code ignores switches, so software guards alone are never rollback safety. Verify command/suspension after rollback, no old Blueprint sync, no schema down-migration, no evidence deletion. If safe state cannot be confirmed stop; do not resume discovery.

## Focused evidence and self-review

`python -m unittest verification.test_scheduled_diagnostic -v`: eight tests passed, zero failures/skips, Python3.12.14. Actual module subprocesses cover uncertain identity, wrong SHA/context/config, early/expired window, unavailable DB phase and sanitized bad arguments. Fake invalid DATABASE_URL cannot be accessed because there is no database implementation. Real alarm termination test0.225344s against2s test ceiling with0.2s configured timer. Nonblocking output failure unit check passed. Full DB timeout/recovery failure-path tests are NOT implemented/executed for this identity-only artifact; they must accompany a later positively identified DB probe. No new PostgreSQL/Chromium evidence claimed. No broad suite rerun: application, migration, dependencies, original integration tests and watchdog unchanged.

Self-review found and fixed argparse echoing unexpected arguments. Reviewed no execution path to discovery/DB, no secret logging, no retry, no durable state. Residual limits: OS/runtime scheduling, operator correlation and restoration, env SHA not independent attestation. Do not call local self-review independent Gate A approval.

Preserved evidence: full06b978c run365 passed/four baseline-matched failures/zero skips/one memory test deselected. Additional targeted DB repeat one pass/one failure: monotonic13.873s vs wall15.002s/server15.006s; original14<=elapsed<19 unchanged. Recovery/settings/SQLSTATE57014 verified but lower bound failed; NOT baseline-equivalent, root cause unknown. Historical13.4638s remains unresolved. Browser five cleanup repeats passed; no further broad cycle requested.

Finite route: suspend old failing cron if approved; inactive identity-only observation; resolve documented identity contract; then separately implement/test/approve bounded read-only DB diagnostic, assess clocks and connection recovery. Only after those findings, tested admission contract, additive migration and trial-limit approval may Manchester smoke be proposed. Salford later; all-council readiness remains open. No OOM root-cause or egress resolution claim.

Provider references reviewed29September: https://render.com/docs/environment-variables ; https://render.com/docs/cronjobs ; https://render.com/docs/infrastructure-as-code . Provider documentation is not account-state evidence.

## Final operator checklist (29 September decision preparation)

Executable is exactly92fdb0dcf653fda0a6be821da8fd54a417a5c9bd. Documentation-only later commits do not replace this executable identifier. Probe source SHA256:1ec1ea9e88f83a57cc35cc33e23260767ee48654a94638b3244373ef4a8c1059. No execution approval requested here.

Starting state, separately approved beforehand: suspended, command `/bin/true`, exact executable deployed, ACTIVATED=0/DISABLED=1/MODE=disabled, Blueprint Auto SyncNo/service Auto-DeployOff, no active/pending run. Max is accountable for restoration and must be present; Astra may assist only under the later explicit execution/restoration approval.

Command transition, while suspended:

`/bin/true`

becomes the following EXACT example for an UNCOMMITTED slot (30September09:00UTC /10:00BST):

```sh
timeout --signal=TERM --kill-after=2s 15s python -u -m scripts.p0a_scheduled_diagnostic --phase identity --expected-sha 92fdb0dcf653fda0a6be821da8fd54a417a5c9bd --not-before 2026-09-30T09:00:00Z --expires 2026-09-30T09:02:00Z
```

Schedule for that example: `0 9 30 9 *`. A later approval must name the actual date/time; change both UTC arguments and cron expression together if a different slot is chosen. Verify GNU timeout availability, actual deployed SHA/source hash, effective command/window/schedule and disabled state before resuming. No build, shell or manual Trigger Run substitutes for the scheduled invocation. Resume only after these checks and with the operator present.

Run correlation checklist: open Runs; capture the entry explicitly labelled `TRIGGER Scheduled` (this label is visible on current historical entries), start/end/status, and its log link. Follow THAT entry's log link; capture the emitted marker/SHA/instance/PID/time/source hash. Current UI links are time-filtered service logs rather than visibly immutable run-ID URLs, so retain the association and check there is only one matching diagnostic marker and no overlapping shell/manual execution. Capture provider run ID if actually exposed; do not invent it. If uniqueness or positive association remains uncertain, classify identity unresolved and stop; a matching approximate timestamp alone is insufficient. Evidence about one execution does not establish a general successor identity contract.

Exit3 is deliberately nonzero: collected sanitized evidence, but scheduled origin NOT established in-process and DB NOT accessed. Render may mark this run failed; preserve that status. It is not Gate A acceptance, a database timeout pass or a discovery failure. No `|| true`, retry or automatic next phase.

After terminal execution: suspend first, refresh and verify suspended status; confirm no active/pending execution. Restore command `/bin/true`; restore schedule `0 5 * * *` WHILE SUSPENDED. Refresh again: parked command, suspended status, correct SHA, three disabled values, Auto SyncNo and Auto-DeployOff. Preserve run/log evidence. The annual recurrence of the example expression must not be left enabled; the absolute date guard is supplementary only. If any setting fails to persist, stop and report, never restore discovery as a fallback. Active execution beyond the17-second outer envelope needs separate cancellation authority; suspension alone is not termination. No automatic restart or1October resumption.

Blueprint impact prerequisite: see P0A_BLUEPRINT_AUTO_SYNC_IMPACT.md. Four managed cron resources were inspected read-only; no current YAML delta found. After restoring suspended /bin/true, do NOT re-enable Auto Sync automatically: YAML still declares the old discovery command. At30September05:30BST review all-resource YAML delta, then seek separate approval for any sync-control change. The other three jobs continue while Auto Sync is paused; their service auto-deploy remains independent.
