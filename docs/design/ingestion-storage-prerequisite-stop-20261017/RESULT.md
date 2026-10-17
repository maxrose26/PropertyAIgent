# Finite credential-risk acceptance — prerequisite stop

Stage4 OPEN. The owner explicitly accepted possible provider-side SCRAM-verifier retention for ingestion_worker_login and ingestion_storage_login only. Ticket SU-511198 stays open; no provider-confirmed redaction is asserted. That risk acceptance is preserved and is not the remaining blocker.

## Identity and ownership
Read-only GitHub verification: master remains44135bb406ea4cab1b053cef90ee34020ac1d35f/tree20a48f9e864f1eaab34686bc23957fa7db85f4ab.
Evidence parent7d626d6e9cf463147c52b3c917d0de29cd8fbfbf/tree496c43f890332e98c9fc1a9e8eebb6998fa85822. No previous active publisher identified; append only using expected-head lease. No runtime/master change.
Reviewed integrated activation file fetched at that exact master: blob629d0649012a25584a8ad4d549290c9810101c82; SHA25654ed6ee545ddb4ae71d19a1b9f36acada39a5cf85627d113e06fc8639d23eed5.

## Actual read-only prerequisite observation
At2026-10-16T23:59:20.595619+00:00 (17October00:59:20 BST), existing authorised Supabase dashboard SQL Editor/projectzcikcfgpblzuzpanpdqd returned:
```json
{"at":"2026-10-16T23:59:20.595619+00:00","principal":"postgres","read_only":"on","privileges":{"create_role":true,"connect_grant":true,"schema_usage_grant":true,"schema_create_grant":true},"public_definers":null,"public_relations":["extensions.pg_stat_statements","extensions.pg_stat_statements_info"]}
```
One script submission, BEGIN READ ONLY; SET LOCAL statement_timeout='5s'; one bounded catalogue SELECT; ROLLBACK. Catalogue queries only; no stored query text, credentials, application records or password catalogue retrieved. PUBLIC relation ACL scan used aclexplode(coalesce(relacl,acldefault('r',relowner))), grantee0, r/p/v/m/f, excluding system schemas and bounded to30 names. PUBLIC callable SECURITY DEFINER scan returned none. This does not prove every activation gate passes, or exercise ownership transfer.

SQL editor URL at observed result: https://supabase.com/dashboard/project/zcikcfgpblzuzpanpdqd/sql/bb45a641-cd8e-4955-950d-ceab3115e528 . Credential-free editor content may be retained by the provider; no credential SQL was entered. No independent production worker started. Counts are4 submitted script statements, not provider-internal driver/connection totals. Provider-managed backend socket closure, actual memory, wire bytes and internal driver accounting are not measured and are not labelled CLOSED. This observation supports a NO-GO; it is not a supervised storage acceptance execution or repeat of the consumed TLS preflight.

## Exact blocker
activate.sql rejects any non-system non-ledger table/view access through has_table_privilege or has_any_column_privilege. Both extensions views lie outside its two-object allowlist. NOINHERIT does not remove PUBLIC privileges. Therefore the proposed logins would fail AMBIENT_NON_LEDGER_ACCESS before LOGIN activation.
PACKAGE.md explicitly requires stopping on ambient access and forbids unrelated PUBLIC/application revocation to force a pass. The new credential-risk decision does not change that separate gate. Neither silently exempting these views nor revoking their shared grants is authorised.

Independent read-only review by storage_prerequisite_review confirmed this conclusion against exact local reviewed SQL/package, with no findings against the stop. No tests repeated; no implementation change made. Helper correction, focused tests, integration and registration were not completed because the necessary separate permission decision failed first; no executable corrected candidate is claimed.

## Dispositions
- Credential risk: explicitly ACCEPTED for exact two roles/finite sequence; not provider assurance.
- Provisioning/installation: NOT RUN.
- Credential generation/mapping/activation: NOT RUN.
- Three-item seed, duplicate seed, restricted-login denials and committed storage readbacks: NOT RUN; no storage PASS.
- Teardown: NOT NEEDED for this attempt; no roles/passwords/protected secrets created or changed by this attempt. No blind revocation against nonexistent/unverified resources.
- Storage-controller run/attempt/artifact: NONE. Existing authorities were not dispatched or rerun.
- Operational ingestion/source/council/application/factual effects/scheduling/deployment: NONE.
- Original blocked helper/history, accepted implementation evidence, IDs1504–1508 and Salford stop preserved.

## Smallest genuine REVIEW
Permit a narrow assessment of whether exactly extensions.pg_stat_statements and extensions.pg_stat_statements_info may be an explicit read-only baseline exception. Establish their actual ACLs, view/function definitions and restricted-role visibility, schema access, extension version and absence of pg_read_all_stats/equivalent runtime membership without reading stored query text. Only if accepted, correct the exact activation allowlist while retaining all other ambient gates, complete the already-authorised helper correction and focused independent validation, then resume the unused finite package with exact bindings. No blanket monitoring/schema exemption, grant revocation, stronger role or architecture change. All existing budgets/expiry/teardown and uncertain-outcome stops remain unchanged.
