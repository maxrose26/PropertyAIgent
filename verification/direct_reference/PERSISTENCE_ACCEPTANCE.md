# Stage 4 direct-reference → B2 persistence acceptance candidate

Master stage: 4 — bounded reliable pipeline. Current gate: durable factual acceptance. Next gate: REVIEW decision on a bounded production persistence canary. No production authority, merge, deployment or operational activation is implied.

## Provenance and integration

Base: `a0feeb7c1cd39c979e2a9018b82d764d1edcd76b`. The two runtime files `app/pipeline/run_weekly.py` and `app/pipeline/status_verification.py`, direct-reference regression file and retained-summary fixture are integrated byte-for-byte from accepted PR #61 head `dd88c922ad75ba0ae9c2e9f826086cf1fa9c838d`. Other PR #61 work is not imported. Shared `refresh.py` remains unchanged from registered master. No second writer is introduced.

Frozen audit: live run **38310507094**, run 1 attempt 1; source SHA equals base above. Artifact **11774039334**, ZIP 1,044 bytes SHA256 `627183fc6aa42e9ea946f5cace93bc7d44dfec1f0537a5aefa7a7c56200f665c`. Retained JSON **2,819 bytes**, SHA256 `8f717b99ef386ee793095bc9e8f3ea64377cf762535e3fba2ffdb18eba9b9cd4`. All three observations retain LIVE_SOURCE_OBSERVATION provenance. Database rows and replay context are disposable. The job's retained acquisition interval is 2026-10-12T21:25:24Z–21:25:34Z; exact per-reference wall-clock retrieval timestamps and source-body hashes were not retained and remain UNKNOWN. Frozen observations are **not current production verification evidence**; replay requires the disposable guard and denies DATABASE_URL.

| Application / council / reference | Literal source observation | Disposition required by existing B2 |
|---|---|---|
| 202 Bolton 00307/26 | Deposited; decision and date NOT_PRESENT; UNKNOWN_UNMAPPED | Withhold coupled acceptance and successful verification; preserve every stored fact. No invented pending mapping or NULL fact. |
| 42 Oldham FUL/355686/26 | Decided; Refuse Permission; Fri 25 Sep 2026 → 2026-09-25 | Material correction from disposable Awaiting decision / NULL / NULL, atomically with watermark, lifecycle event and refresh signal. |
| 78 Stockport DC/078942 | Decided; Granted; Wed 27 Dec 2023 → 2023-12-27 | Same substantive facts; legacy display-date canonicalisation is a non-material write. Replay is unchanged, without duplicate lifecycle or invalidation. |

## Translation and transaction contract

`refresh()` validates admitted application/reference/source URL and field states before calling B2's `verify_application_status(..., evidence_loader=...)`. B2 captures the prior successful-verification watermark **before** invoking the evidence loader. The loader supplies the exact qualified status/decision/date; B2 is the sole writer through its existing status-only upsert and transaction. NOT_PRESENT never becomes an authoritative NULL. Conflicting or partial evidence cannot enter acceptance. No new timestamp arbitration is added.

Successful complete acceptance advances `status_verified_at` according to accepted B2 semantics, including unchanged complete observations. Identical facts/events are idempotent; the verification timestamp intentionally advances for a newly accepted verification. Lost commit acknowledgement is initially PERSISTENCE_FAILED/uncertain, not proof of rollback; committed readback and retry establish the outcome. The retry creates no duplicate lifecycle event.

Bolton uses existing safe disposition **B: source-only literal success, factual acceptance withheld**. Its partial/unmapped observation cannot certify the coupled watermark, so neither facts nor watermark advance. This is an explicit limitation, not a request to weaken B2 or invent a separate watermark.

Oldham's accepted existing consequence is one `decision_refused` ApplicationLifecycleEvent (source `status_verification`), `evidence_refresh_required=True`, reason `decision_refused`, trigger `material_change`, and requested-at time. These commit in the same transaction as facts/watermark. Existing `stage_evidence_refresh` can later consume that bounded flag; it is not executed here. The flag means a targeted evidence check is needed, not that AI is stale or recomputation already happened. No buyer reassessment, ranking, summary/model call or automatic new downstream behaviour is added. B2.1 readers can subsequently display verification age from the accepted watermark.

## Acceptance evidence

Local offline selection: Stage 4 frozen/live translation, direct-reference and registration; B2.0/B2.1; planning verification; Stage 1 access/outbound preservation. Hosted exact-head workflow `stage4-persistence-offline.yml` repeats it and executes the accepted native PostgreSQL 17 machinery with 12 focused scenarios alongside existing native regressions. No production connection, migration or import; disposable Base metadata is created only in the throwaway database. Network source calls are denied in tests. PG uses READ COMMITTED, 10-second statement and 8-second lock timeouts, loopback-only public throwaway credentials; service stop and idle/pool checks retain cleanup evidence.

Native scenarios: Oldham material acceptance; Bolton withholding; Stockport non-material canonicalisation and unchanged retry; failure after flush before commit with independent-reader isolation; SQL exception; concurrent newer accepted observation causing outer stale-response rejection; commit succeeded/acknowledgement lost followed by idempotent retry; wrong reference; conflicting field; partial field; parser failure; older terminal-decision rejection. Every non-commit path preserves prior accepted facts, watermark, lifecycle and refresh signal. Hosted results and exact candidate identity belong in the REVIEW handoff; this document does not claim tests that have not run.

## Minimum future persistence audit

Closed, bounded record (16 KiB ceiling): application/reference; source observation run/SHA/artifact provenance or freshly acquired source URL/body digest; retrieval start/end (UNKNOWN if interrupted); accepted/rejected outcome; before, qualified incoming and after coupled planning facts; field evidence states and semantic qualification; before/after verification watermark; materiality; transaction outcome; before/after lifecycle and evidence-refresh signal; bounded error category. Preserve COMMIT_ACK_UNKNOWN until readback. No raw HTML, arbitrary errors/headers, cookies, credentials, proposal, applicant/contact details or documents. `validate_persistence_audit` is the disposable frozen-provenance schema test, not a registered production runner; a future runner must retain fresh provenance and the existing retrieval audit alongside this persistence record.

## One proposed production canary — design only

Exactly **Oldham application 42 / FUL/355686/26**, same frozen official summary destination in manifest. It is the smallest evidenced material correction; Bolton adds no complete acceptance and Stockport adds no material correction. Current production facts remain UNKNOWN. If production already agrees, report unchanged; do not manufacture a material change.

Future separately reviewed registration must: freeze one identity/destination/reviewed SHA and single-use authority; capture bounded before facts/watermark/event/signal state; retrieve fresh authoritative summary **inside B2's evidence-loader window**, independently match exact reference, qualify all coupled fields, then write solely through existing B2. Never use this frozen October 12 audit to advance a production watermark. Verify committed facts/watermark and exact existing lifecycle/refresh consequences with a separate bounded readback. Failure before commit rolls back; lost acknowledgement requires readback, no blind repeat or compensating direct UPDATE. Stop on stale/conflicting/partial evidence or uncertain commit. No downstream worker/model execution.

Proposed limits retain one worker, two attempts/one transient retry, no redirects, 1 MB/response and 2 MB/reference, 45 seconds worker, 512 MiB/30 CPU seconds, three-minute outer job; database connect 5 seconds, statement 10 seconds, lock 8 seconds, at most two DB connections and bounded one-application reads; combined persistence audit 16 KiB. Registration must prove minimum credentials, cleanup, exact SHA admission, immutable scope and run-once gate before REVIEW grants execution. No production credentials or executable persistence workflow are introduced by this candidate.

## Remaining Stage 4 scope and exclusions

Production persistence is unproved and unauthorised. Broader known-reference coverage, operational cadence/manual fallback, unsupported routes and major/material discovery remain separate Stage 4 decisions. This candidate does not close Stage 4 or authorise rollout to 116 references. No live requests, production queries/writes, migration, additional councils, Arcus, discovery, scheduling, models, new ranking, Stage 5 work, merge or deployment.
