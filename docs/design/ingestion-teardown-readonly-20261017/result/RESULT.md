# Read-only teardown reconciliation — DB access disabled; two temporary secrets remain

Stage4 OPEN. Owner-authorised single reconciliation completed. This observation made zero persistent database/secret mutations and did not replay the storage controller.

## Exact current observed state

Both exact runtime roles ingestion_worker_login and ingestion_storage_login:
- can_login=false;
- password IS NULL=true (boolean-only source evidence; no password/verifier returned);
- NOSUPERUSER/NOCREATEROLE/NOCREATEDB/NOBYPASSRLS/NOREPLICATION;
- connection_limit1; original validity expiry2026-10-18T08:54:58.469465Z;
- zero direct memberships and zero associated sessions.

Migration current/session postgres matched accepted NOSUPERUSER/CREATEROLE/CREATEDB/BYPASSRLS profile. Existing privileges allowed the boolean-only password query; no permission expansion/fallback occurred.

Names-only successful protected-environment metadata read confirms BOTH temporary secrets PRESENT:
INGESTION_WORKER_DATABASE_URL
INGESTION_STORAGE_DATABASE_URL

No secret value was retrieved. Current access verdict DATABASE_ACCESS_DISABLED_SECRET_CLEANUP_PENDING. The earlier TEARDOWN_READBACK tuple was not logged; this later observation does not establish its original cause. Do not assume transient sessions, pooler caching or another explanation.

## Verification and closure

Received exact final-result.json2072bytes SHA2564f1da6a2e5a3078813a42015da38a92016ab1cf631947fe74a60c423701d1e9a, plus the complete new read-only events.jsonl8180bytes SHA256f72d6b58c7787313f680df4f29f51acf46cf1b544531a67ae66401592afc0772.

Independently verified all17event hashes/sequence/links, chain head1cdefdc4c931e7f16a8530fc10a1349ab57b8eebf640cc4c5dc67436754604ab, source-audit binding, recorded observation versus authoritative final result, and cumulative counters. Confirmed rollback acknowledgment and closed native connection in new audit. Final authoritative result reports READ_ONLY_OBSERVATION_COMPLETE and CLOSED for THIS observation. Intermediate observation-supervisor receipt is distinct from final archive-inclusive elapsed result.

Original three consumed attempts retain historical UNCERTAIN cleanup. Current effective database readback resolves present access state without rewriting those historical outcomes. No provisioning/storage retry or authority replenishment.

Reconciliation used1connection/6driver statements/.616468669999449supervised seconds,765returned database data-value bytes. Cumulative9connections/145commands/7.079792436999014supervised seconds. Aggregate remaining4connections/232.920207563001seconds; neither originalteardown10commands nor reconciliation6commands is replenished. Kernel outer peak73142272bytes; worker peak18604032bytes; no max/OOM/OOMkill events, no forced cleanup, worker group empty/removed. These are memory-accounting counters, not totalRSS or wire-byte claims.

## Full earlier audit archive remains pending transfer

The final result binds credential-free-audits.zip SHA25609edd0dd786799f62ec88b20ca5cc5be696b76ff3ae07e4e97979cecb602c529. That ZIP was NOT supplied in this turn. The newly supplied8180byteevents file is the read-only observation, not the original104114bytestorage audit or either earlier failedattempt.

Upload the EXISTING credential-free-audits.zip from:
\\\\wsl.localhost\\Ubuntu-24.04\\home\\maxrose26\\.local\\state\\propertyaigent\\storage-teardown-readonly-reconciliation-20261017
No rerun is needed to transfer it. Verify its bound hash, HASHES.json, original3audits and complete chains before claiming durable full-original archival. Earlier publication still contains only an excerpt.

## Exact finite completion proposal — not authorised/executed by read-only scope

Only two secret deletions remain as live cleanup. Propose one owner-local phase with:
-0database connections/commands and no provisioning/role/password/session/application changes;
-at most2DELETErequests, exactly the two dedicated temporarysecret names in stage4-production-canary for maxrose26/PropertyAIgent;
-at most1successful names-only boundedGET for post-deletion absence readback;3APIrequestsmaximum, no pagination/retries;
-10supervised seconds/256MiBfrom-exec kernel ceiling/swap0, boundedexport under existingcombined2MiB; carry current cumulative counters and originalexpiry18October09:54:58BST;
-durable intent/ack for each exact deletion; uncertainty stops subsequent mutations, with no blindrepeat/compensation; read-only absence reconciliation remains distinct;
-preserve existing DATABASE_URL, all ledger rows/evidence, Salfordstop and IDs1504–1508.

Reviewed operation shapes (proposal only):
DELETE /repos/maxrose26/PropertyAIgent/environments/stage4-production-canary/secrets/INGESTION_WORKER_DATABASE_URL
DELETE /repos/maxrose26/PropertyAIgent/environments/stage4-production-canary/secrets/INGESTION_STORAGE_DATABASE_URL
GET /repos/maxrose26/PropertyAIgent/environments/stage4-production-canary/secrets?per_page=100
GET exports only exact2allowlisted names and total_count; failed/capped/ambiguousresponses remainUNKNOWN.

Current instruction is READ-ONLY: explicit release of these exact2deletions is required before execution. No additionalDBquery, newinstallation or storage replay is proposed. Preserve 3blockeditems/control, zeroattempts/grants and acceptedstoragefunctionality evidence. Final storage acceptance remains conditional on secret cleanup/readback and evidence reconciliation; operationalactivation/source/scheduling/stageadvancement remain held.
