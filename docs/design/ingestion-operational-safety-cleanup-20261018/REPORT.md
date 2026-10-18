# Finite revoke-only safety cleanup: executable owner handoff

The helper is ready for the one authorised owner-local cleanup. Production cleanup has **not** been executed by this preparation. Production storage remains accepted; operational acceptance failed; the pipeline retry is held and Stage 4 remains OPEN.

## Exact identities

- Candidate `2c092cc7758452b85f9a7467b3c9ee76643ae84d`; tree `847c7f17d8bd3885e198a64d611bb23fff4a39d0`; draft PR #127.
- External helper blob `2a100d7d9307f75cc58df9429e376d769cb608e1`, SHA256 `a8f6e78399fe89585f45f9815ca96e15d8f4e9a7e118103bbe41de66fc8a212c`.
- Existing checkout/master remains `ad8d5211afcc635c5bc50f4963adde4f31b4ef62`, tree `8482c3d62c79bcbdb6ce91b1b8075751bcaf9893`. No merge, runtime change, deployment or pipeline dispatch is needed.
- Cleanup authority: `AUTHORISE_OPERATIONAL_SAFETY_CLEANUP_ONCE_20261018`.
- Registration blob `37a969bbab0c9e51850a506a26379e40ab7e834d`; SHA256 `3c10291a1b2e7f3d81f463a619fca177a224259f1ed708f01d8d0a5e935cc377`; expiry **18 October 2026 22:00 UTC / 23:00 BST**. This is a separate cleanup registration; it does not renew the consumed capture authority.
- Original reconciliation: `047f8ef88bbcf115b8783f75019e4f42b07883c8`. The original full 44,272-byte/175-event audit remains archived unchanged there, SHA256 `dd7c5814b686c8dd4c23451238d88fa76e095040ac30871e4139936b9d02677f`.

## Enforced effects and order

1. One complete names-only GitHub GET; require both exact temporary names and preserved DATABASE_URL.
2. Connection 1: record migration flags; lock and verify original control, exact consumed grant and exception, both restricted roles/memberships and associated sessions; verify all four non-control ledger rows and zero attempts. In one transaction expire the consumed grant/exception, increment hard-stop generation to 1, retain Salford and STORAGE_TEST_STOP, disable both runtime logins, set their passwords NULL and revoke only their reviewed memberships. Temporary migration-owner capability is removed before COMMIT.
3. Connection 2: record actual role/password-null/membership/session values; read back exact committed control and unchanged ledger; roll back the temporary readback capability and verify it is absent.
4. Exactly two acknowledged DELETEs: INGESTION_WORKER_DATABASE_URL, then INGESTION_EFFECT_DATABASE_URL. Final complete names-only GET must equal the initial set minus those two names. DATABASE_URL and all other names remain.
5. Verify owned sockets/children, closed connections, actual kernel memory and final evidence. No automatic compensation, retry or pipeline call.

Unknown acknowledgements, unexpected state, any associated runtime session, exhausted allowances or expired registration stop the helper. Session state may be NULL when PostgreSQL hides it; actual values are recorded, never inferred. No session-termination API is used.

## Separate safety-cleanup allowance

Two connections; 32 commands; 45 supervised seconds including hidden input and final evidence; 1 MiB returned database data-value bytes; 256 MiB actual memory across Python and gh descendants; 512 KiB combined exported evidence; two DELETEs and two complete names-only GETs. Work stops at 42 seconds to reserve closure, with an outer kernel/systemd 45-second deadline. No virtual-address limit.

The original incomplete accounting remains incomplete: 87 reconstructed admin commands, five admin connections and one runtime connection, zero runtime SQL. Original admin active seconds and returned-value bytes are UNKNOWN. This separate cleanup allowance neither resets nor validates those counters.

## Focused disposable evidence

Independent exact-candidate and final command/registration review: PASS. Existing hosted workflow run **39108893557**, number **191**, attempt **1**, exact candidate: PASS.

Eleven focused tests passed (six pure and five PostgreSQL 17/non-superuser/real-gh cases). Success used **20 commands, 2 connections, 17,268 returned data-value bytes, 0.233558444 helper-phase seconds**; both connections closed; two exact deletes and two names reads. The combined fixture cgroup peak at that point was **83,099,648 bytes**, zero max/OOM events. These disposable measurements exclude fixture setup, assertions, owner input and final production wrapper overhead.

Changed grant and an associated restricted session stop before committed cleanup. Lost COMMIT acknowledgement prevents the second connection and all secret mutations. Lost first DELETE acknowledgement prevents the second delete and final GET; no automatic retry. Expiry after startup prevents the next SQL/DELETE. A separate real-gh + excessive allocation probe killed the complete 256 MiB scope; systemd reported oom-kill and empty ControlGroup. The CI fixture's 90-second setup/test wrapper is not the production cleanup budget.

Original hosted ZIP artifact **12129796921**, 68,447 bytes; SHA256 `f12676a1f7333c2c7176706cd4540881299ee22e4006616e340d1a4b8b4faddd`. Full original ZIP, reversible base64 mirror, all member hashes, cleanup.xml and the focused native log excerpt are retained alongside this report. The ZIP digest and all members were verified before publication.

## Owner step and result

Have the existing migration URL ready privately before running owner-command.sh; the hidden prompt is inside the 45-second envelope. Existing WSL/keyring authentication and venv are reused. No credential may enter chat, a file, an environment override or a command argument.

On success expect SAFETY_CLEANUP_ACCESS_DISABLED and CLOSED for this **new** cleanup only. Return the printed JSON and the new credential-free events.jsonl/final-result.json for reconciliation and durable archival. If stopped, preserve both files, do not rerun, and return the result. Historical UNCERTAIN classifications remain unchanged even after successful cleanup.

After actual cleanup, the grouped offline correction remains: invalidate authority on early runtime failure; retain safe phase/class/SQLSTATE/native-closure diagnostics without raw connection exceptions; always export full cumulative accounting and final audit receipt. The original underlying connection cause remains UNDETERMINED. No pipeline retry is approved.
