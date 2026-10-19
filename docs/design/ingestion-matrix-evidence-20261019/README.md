# Restricted-connection matrix and matrix-cleanup evidence

Complete, byte-identical copies of the two consumed audits, with verified hashes. Documentation only; nothing here is code and none of it is reinterpreted by later code.

| Audit | Directory | `events.jsonl` sha256 | `final-result.json` sha256 | Hash chain |
|---|---|---|---|---|
| Restricted-connection matrix (registration `7f06873e…7381`, commit `d44ebf93…`, tree `1e433220…`) | `restricted-connection-matrix/` | `e94e41309a1709afb19cfe0c4fd8df45841db76bae8542306f8003dd3a25f610` | `ff387721f53260bcd9a72f8e26ee7ddcfbbfbb004d03812eaea82e5ad9b4d954` | valid, head `067846c6…ea975` |
| Matrix cleanup (registration `5378c849…80de`, commit `375601af…`, tree `a4396e88…`) | `matrix-cleanup/` | `118be05e379c64df69f70d9ccfe4ccd8442652bd1e49ec48ef0a92fde1ace347` | `0d7939114cf5f61bf90509354e2b49ab8f9d5d1620421ae44f2e8687f76563a3` | valid, head `4fb56694…3dda` |

`HASHES.sha256` in this directory verifies all four files (`sha256sum --check`).

## Recorded results (as written, not reinterpreted)
- **Matrix**: stopped after two entries (`UNEXPECTED_IDENTITY` as classified by the code that ran), teardown unreconciled (one idle `ingestion_worker_login` session, pid 3175259, prevented the strict zero-session readback), both temporary secrets left in place, `DATABASE_URL` preserved. Entry 1 (worker, no options) `AUTHENTICATION_REJECTED`; entry 2 (worker, reviewed options) connected and ran the identity statement, and the merged check reported an unexpected identity [original wording: "session did not carry the reviewed server timeouts" - an inference, see the correction]; entries 3–4 skipped.

**Correction (2026-10-19):** the retained entry-2 outcome is a single merged result (`UNEXPECTED_IDENTITY` as classified by the code that ran). That merged check did not independently establish that the reviewed server timeouts were not reflected, nor that identity and flags passed; the earlier wording below is kept as originally written and should be read as an inference, not a finding. Administrative use 5 connections / 52 commands.
- **Cleanup**: `RESTRICTED_MATRIX_CLEANUP_VERIFIED`, cleanup `CLOSED`, access `DISABLED_VERIFIED`; the named session was already absent (`TARGET_ALREADY_ABSENT`, no termination); both temporary secrets deleted (204 each); `DATABASE_URL` preserved; 2 connections / 4 commands / 3 GitHub requests.
- No query text, credential or connection URL appears in either audit.
