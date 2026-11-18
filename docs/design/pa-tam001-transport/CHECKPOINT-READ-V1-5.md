# PA-TAM001 v1.5 — inactive checkpoint-read package

Stage 4 OPEN. Preparation only. Exact command/revision are in the accompanying PR #227 handoff; no execution authority is implied. v1.4 is consumed, v1.3 fenced.

## Fixed scope

Read only `ingestion_intake_owner_state('b-bolton-20261103-1105-01_owner','65ea9cfb9eb260a54b728d1de44eb4d7','',NULL::bytea)`. Require one row, ordinal 55, stored and computed ciphertext SHA-256 `a5ba6be74c47eea89bd5068111bf3bc65198c8b4fd54c5036394a2c512f55c52`. No Journal.load/save, second connection, retry or substitute invocation.

Reserved, unused invocation: `pa-tam001-v1-5-owner-checkpoint-01`. Workspace `tea-d9qbf8jm8hqs7385cu0g`; existing owner service `srv-d9qbl7qjnfac73d8nieg`; deployment `2fa0f07cfdfb56a27243ebff18110d441f9da04d`; instance `srv-d9qbl7qjnfac73d8nieg-8684bcc77c-xgxgz`; working directory `/opt/render/project/src`. Drift refuses; do not switch targets automatically.

Six statements maximum: BEGIN REPEATABLE READ READ ONLY; SET LOCAL statement_timeout 10s; SET LOCAL lock_timeout 3s; actual identity/settings SELECT; bounded checkpoint SELECT; ROLLBACK. Identity must be exactly postgres/postgres/postgres/on/10s/3s before the checkpoint query. One existing owner Database connection; full bootstrap/work/cleanup envelope under 20 seconds. Work deadline 15s, rollback 18s, close 18.5s; independent timeout terminates/kills by 19.5s. No production query was executed during preparation.

## Result bound and privacy

The server materializes at most two checkpoint rows once. Two rows refuse as duplicate without base64 encoding or returning either body (two means at least two, not an exact full count). Wrong ordinal, null/oversized body, stored/computed hash mismatch refuse server-side. The server returns a single text JSON envelope only if its entire UTF-8 size fits the remaining cumulative budget. Metadata, JSON escaping and base64 expansion are included. Identity payload is server-capped at 1 KiB. A conservative 4096-byte reserve covers result column metadata/framing and the six command responses; payload plus reserve must stay <=65536 before transfer. This is a SQL-result cap, not a claim about all TLS/network traffic. Client independently verifies cumulative size, shape, ordinal, length and SHA before decrypting.

The decoder embeds unchanged AST routines from #213 `f027ba28af69ae70208eab5ed047e4a8a81c6337`: Vault, hydrated_state, Journal._vault and canonical. Tests compare their exact source and exercise original encrypted and compressed fixtures. The deployed source files differ from #213: retain the proven v1.4 deployed file/CA checks and identical Database AST hash, rather than pretending the whole deployment equals #213. Embedded decoder avoids reliance on an unverified installed decoder. It uses the existing adapter key; it creates no credentials and runs no SQL.

Allowlisted historical projection only: bounded profile/binding values, historical execution identity and closure fields, missing-field markers and verifier-presence/equality booleans. No ciphertext, credentials, full state, credential verifier values or exception text in receipts/logs. Existing decoder uses its original private temporary ciphertext file, removed in its finally path; it is not a receipt/log. Instance replacement or missing completion remains UNKNOWN, with no retry.

ACK precedes the sole worker start. Exclusive invocation directory and worker claim prevent duplicate start/worker. Completion binds ACK hash, invocation, launcher/core hashes and instance. Independent `read` validates both files, elapsed time and successful-result limits. Rollback acknowledgement requires psycopg cursor ROLLBACK plus ConnectionInfo.transaction_status IDLE. Connection closed is independently reported. Neither proves the other.

## Validation

Final focused run: **32 passed, 0 skipped, 3.94 seconds**, disposable PostgreSQL 17.11 and actual frozen decoder fixtures. Command: `python -m pytest docs/design/pa-tam001-transport/test_checkpoint_read.py docs/design/pa-tam001-transport/test_checkpoint_receipts.py -q --tb=short`, with the test-only localhost PostgreSQL URL and frozen #213 checkout required by the tests. Tests cover identity-before-query refusal; duplicate million-byte bodies without transfer; oversize/hash/metadata-cap refusal before decode; maximum accepted body; output/receipt redaction; separate rollback and closure failures; work and external timeout; duplicate invocation; missing/tampered receipt; wrong instance; detached receipt readback. Same-instance browser disconnect/reconnect proof is reused from PR #227 comment 6951899418; this run did not repeat browser or production access. Original candidate tests and verified Bolton receipt remain unchanged.

During development, a fixture incorrectly applied deployed-file preflight to the different #213 checkout and refused SOURCE_OR_CA_DRIFT. This exposed the decoder deployment distinction above. A later source-equality-test string quoting error was corrected. Neither failed test queried production; the final focused run is clean.

## Before sealing Tameside

A matching read recovers historical values, not present runtime acceptance. Require complete profile and matching bound profile; validate historical service, build, route, browser path/hash, resource ceilings and configuration digest against the accepted historical binding. Then compare with the actual intended current restricted runtime (`crn-d9sv93vavr4c73f98rb0`), enabled candidate artifact and provider configuration using existing verification paths under applicable authority. Derive the new configuration digest and build pins from actual values; do not substitute fixtures or blindly reuse old host addresses/deadlines. Any missing/changed value stays explicit and prevents sealing. The owner service used for this read is not the restricted collection service.

The recovered closure belongs to the historical run, not a new proof of current STOPs, permissions or surviving processes. Retain verified Bolton v1.4 receipt and accepted no-replay dispositions. Preserve locked live rechecks and independent recovery/release/retention/screening/backlog/cleanup readbacks in the later operational sequence. The fixed first batch remains Tameside RECEIVED 15–21 September 2026; all-ten follow-on includes Manchester, Bolton and Trafford. Existing expiry ceiling 18 November 2026 20:00 UTC is not silently extended. Distinct REVIEW and separate owner approval remain necessary before any recovery, installation, deployment, stop clearance or collection.
