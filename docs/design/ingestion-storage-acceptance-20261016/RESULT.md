# Integration complete; protected catalogue preflight awaiting owner approval

Stage4 OPEN. Storage acceptance NOT STARTED. Operational pipeline acceptance NOT COMPLETE. Backlog unchanged. No database migration/population, source execution, application/factual writes, scheduling or barrier release.

## Integration and reviewed content

PR113 candidate7682c33b874920d1114611cbbb04ba598689057a integrated via mergee2f199bc2ec86a14389554fe5bbc4864774a6d0f. Exact unchanged tree892cf6ff1704a857f19d383f49ab83da109483d6; parentsf5a5d92c42c6708c24c9f6c6cf10d6310b1bbedf and reviewedcandidate.8candidate checks and6postmerge checks PASS. Merge includes [skip render]. Accepted evidencefd3d51a5e66cb889dd7d7603da2e237d8be2d5d8 and previous checkpoints preserved.

Necessary catalogue-only access registration PR114 candidatebe67b245cb70f6434603ae8ed2109def53db8977 integrated as5485ab74a236232a6acf3409383364ad9a5517f6, unchanged registration treebe322adc5f274346dffbd938f90c65f52c4c5ea0.10candidate hosted checks and6postmerge checks PASS; independent final review PASS. No app/ingestion, pipeline, migration or manifest content changed by registration. Historical authorities were not repurposed. New workflow contains no migration/seed capability. Both merges use [skip render]; no deployment command issued. Render's documented skip phrase is the deployment suppression mechanism (https://render.com/docs/deploys). Live Render event/auto-deploy configuration was not independently read: connector requires a confirmed workspace; none was selected or modified in this task.

Fixed workflow.github/workflows/stage4-ingestion-storage-catalogue-once.yml SHA2560ad0e1931253639e883947b996147181c23b8a0fee1845d614fa99c7b632989c. MigrationSHA256f790550778172adbfe1db792d20b4c4fb58298e5829f4033f269c8670dc47033; three-item manifestSHA2567883c1a8f99ce3e498fb73911713c3b531d4c73d20fd2524e3c9901e822e7b04 unchanged.

Validation for new access code:10focused checks PASS (8newpure checks plus2existing exclusivity guards).25disposablePG checks PASS on exact registration candidate, run38893848251/job116949513140,10.36s. This includes actual psycopg cursor accounting of dialect initialization and rejecting a non-TLS disposable connection. Original artifact12042768172 archived as disposable-pg.zip, SHA256c6b516eeac9c810a9264306a61202b9bb118d51f1b09ef060b9e89c7d451deba. All earlier completed suites retained; no manual blanket rerun. CI runs normal required jobs. Two initial exclusivity guard failures are preserved in execution history; correction pins exact new workflow SHA, not a blanket protected-environment exemption.

## Existing execution and exact remaining access step

Exactly one catalogue-only run38894230179, number1/attempt1, revision/workflowSHA5485ab74a236232a6acf3409383364ad9a5517f6:
https://github.com/maxrose26/PropertyAIgent/actions/runs/38894230179

At this checkpoint statusWAITING, job116950746714 waiting, steps=[], no artifact. The environment requires maxrose26 to approve stage4-production-canary via Review deployments. No new dispatch/retry is permitted; resume by inspecting this exact run after owner approval. Complete pre-dispatch manual history was44/44, no target execution, no other active/waiting manual run. After dispatch45/45; target first run only. No actual source or database step started. Approval permits catalogue SELECTs only; conditional migration stays subject to compatibility evidence.

Existing protected environment metadata confirms exactly1 secretDATABASE_URL and no variables; no restricted worker/storage credential mapping in this environment. Values not read/exported. Required reviewermaxrose26, bypass disabled, master only. Existing route is the accepted session-pooler endpoint on5432; an old generic model comment about transaction pooling is not authoritative route evidence. TLS certificate/hostname verification, actual connection/read-only/reconnect behaviour, migration privileges, existing named objects/roles and restricted-role ownership/membership are NOT YET TESTED in production. Do not treat the missing credential mapping as proof that database roles are absent.

## Fixed storage items and accounting

This task created0production work items,0attempts,0authorities,0Applications or verified facts. The exact reviewed pending manifest remains:

| Subject | Task/state | Stable key |
|---|---|---|
| Salford VALIDATED8–14Oct2026 | LISTING_METADATA / SAFETY_BLOCKED, consumed stop | c1f526eed20e392382001cad4d28eb5bc16e5d1c0f92adb282fe7b1cc775f3f3 |
| Rochdale PL/2026/0882 | LISTING_METADATA / UNSUPPORTED_CONTRACT, unqualified source | 0eff5d22b28ee79039d151382ac0321e26350b9ccb10c58f46b82050dab82bf9 |
| Oldham NMA/356901/26, context1507 | FACTUAL_REFRESH / UNSUPPORTED_CONTRACT, COUPLED facts withheld | 16c9c4d1fb67d844ddb29b092217c3b5a7c42eb8ba63e296611ce2f617779f6d |

No production committed readback of these new items is claimed. Accepted IDs1504–1508 remain preserved and were not queried/refreshed. Oldham1507–1508 accepted COMMITTED_PENDING_IDENTITY/FACTS_WITHHELD remains historical evidence, not new factual delivery.

Actual preflight usage at WAITING:0database connections/SQL,0source calls,0writes, no worker process launched, no DB pool constructed; database cleanup not applicable. Do not label future accounting/cleanup CLOSED before execution evidence. Finite run bounds:2sequential connection attempts,40drivercursor executions including initialization,3sconnect/10sstatement/3slock/10sidle deadlines,30sactive/120sjob,256MiBhardaddressspace (stricter thanRSS),32KiBworker audit/2MiBoutput. ExplicitBEGIN READ ONLY/read-committed/clientTLSverify-full, rollback/reconnect/close/dispose. AtomicUNKNOWN intent before each connect; closure/disposal separately recorded. Any cap/uncertainty fails closed, no retry/fallback. Original consumed Salford stop remains intact; no authority/barrier release functions invoked.

Conditional first install/seed must not occur on catalogue success alone. The production restricted-login mapping and new-owner-transfer/membership requirements must actually satisfy the reviewed package. No administrative credential as worker, owner membership, stronger-role fallback, secret replacement or unreviewed grant. Uncertain DDL/seed commit requires read-only reconciliation before any further mutation. Non-destructive rollback keeps populated evidence, revokes dedicated access and leaves workers disabled; no DROP/delete/restore. Capacity warn70%/pause85% and hard bounds remain proposals; unresolved work/essential evidence never automatically deleted.

## Smallest remaining implementation, separate from storage acceptance

- Controlled claims/checkpoints/effects: narrow transactional database interfaces around existing ledger decisions/fences/checkpoints/intents, with worker authority separated from issuer and barrier release; no broad CONTROL UPDATE grants. Explicit production engine/role registration and pooler/timeout checks. No general agent platform.
- New-candidate admission: retain WorkItem identity through listing/screening/selective supported evidence; only after exact identity/factual contract qualifies call existing admit_identity, duplicate/race protection and committed identity readback, then separately authorised shared B2/readback. Pending identity is not verified facts; uncertain persistence blocks later writes. New-identity orchestration remains outstanding; do not create unsupported pending Applications for throughput.
- Idox: integrate existing qualified Idox discovery/listing evidence and supervisors into the coordinator contract, with source-specific tests and unchanged factual semantics. Not done/activated here.
- Operational canary: after those prerequisites and an explicit scoped safety decision, freeze one exact qualified source/date observation and at most1genuinely new supported candidate, screen before expensive retrieval, separately finite detail/admission/B2 allowances. No repeated completed window, broad rollout, scheduling or automatic stop release. Current approval is storage-only, not this canary.

Proposal capture remains14/415,401missing (Manchester238/Salford117/Rochdale46).13partitions,4historical gaps,7bridge gaps and subsequent interval coverage remain unresolved. Historical seals/consumed scopes and parked parents/Stockport/Trafford holds unchanged. Storage retention, operational pipeline readiness, backlog completion and Stage4 acceptance remain separate.
