# Oldham read-only inspection — package (NOT AUTHORISED FOR EXECUTION)

Specification: `specifications/038-oldham-readonly-inspection.md`. Controller: `verification/ingestion_storage/oldham_inspection.py` (entrypoint `verification.ingestion_storage.oldham_inspection`).
Nothing here has run against production. No production connection, credential entry, installation, registration, stop change, council request or model call is authorised by this package.

## What it establishes (and does not)
Whether the existing environment supports the authentic Oldham capture and screening: installed function state (pre-Oldham / exact Oldham / missing / mixed; by body hash, owner, search_path, overloads and the helper's signature and SECURITY DEFINER flag only), EXECUTE on seven named functions and table privileges on four named tables for the three runtime logins, the four logins (flags, password-presence boolean, settings, memberships), sessions, and the stop fields the installed control function exposes.
It does **not** prove uncertainty barriers absent: `ingestion_acceptance_control()` returns only `global_stop`, `manual_stop`, `hard_stop_generation` and a count of `unexpired_grants`. It does not return `last_hard_stop`, the stop-state digest, WRITE_INTENT rows, Oldham allowances or per-grant detail, and the migration identity has no table privilege on the ledger. Those remain unobserved by design (no GRANT is permitted).

## Identity (stated honestly)
The existing administrative `postgres` migration account, URL entered at the hidden prompt only. At the last accepted readback (2026-10-22, from the owner-local audit file `~/.local/state/propertyaigent/operational-bolton-screening-v3-retained-successor-once-20261030/events.jsonl`, sha256 `e9c42e3d9aedef790cf7341558a6b9f1bd463add6c2ab4aeebe03c20941ce129`; that file is not in the repository) it was not a superuser but held CREATEROLE, CREATEDB and BYPASSRLS, was a member of `pg_read_all_stats` and `pg_signal_backend` (which can terminate other backends), and held neither `ingestion_storage_owner` nor `ingestion_barrier_releaser`. This is a broad administrative account; this inspection issues none of those powers. `BEGIN READ ONLY` is a guard on the transaction, **not** a restricted account. No restricted read credential exists and none is created or discovered.

## Fixed statements (one connection; the complete list)
1. `begin` — —
```sql
BEGIN READ ONLY
```
2. `identity` — —
```sql
SELECT current_user,session_user,r.rolsuper,r.rolcreaterole,r.rolcreatedb,r.rolbypassrls,pg_catalog.pg_has_role(current_user,(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='ingestion_storage_owner'),'USAGE'),pg_catalog.pg_has_role(current_user,(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='ingestion_storage_owner'),'SET'),pg_catalog.pg_has_role(current_user,(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='ingestion_barrier_releaser'),'USAGE'),pg_catalog.pg_has_role(current_user,(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='ingestion_barrier_releaser'),'SET'),pg_catalog.pg_has_role(current_user,'pg_read_all_stats','USAGE'),pg_catalog.pg_has_role(current_user,'pg_signal_backend','USAGE'),pg_catalog.has_column_privilege(current_user,'pg_catalog.pg_authid','rolpassword','SELECT') AND pg_catalog.has_column_privilege(current_user,'pg_catalog.pg_authid','rolname','SELECT'),pg_catalog.has_function_privilege(current_user,pg_catalog.to_regprocedure('public.ingestion_acceptance_control()'),'EXECUTE'),pg_catalog.to_regprocedure('public.ingestion_acceptance_control()') IS NOT NULL FROM pg_catalog.pg_roles r WHERE r.rolname=current_user
```
3. `control` — —
```sql
SELECT public.ingestion_acceptance_control()
```
4. `roles` — fixed list(s): 4 names
```sql
SELECT r.rolname,r.rolcanlogin,a.rolpassword IS NOT NULL,r.rolvaliduntil,r.rolconnlimit,r.rolsuper,r.rolcreaterole,r.rolcreatedb,r.rolbypassrls,r.rolreplication FROM pg_catalog.pg_roles r JOIN pg_catalog.pg_authid a ON a.rolname=r.rolname WHERE r.rolname=ANY(%s) ORDER BY r.rolname
```
5. `role_settings` — fixed list(s): 4 names
```sql
SELECT r.rolname,r.rolconfig,(SELECT count(*) FROM pg_catalog.pg_db_role_setting s WHERE s.setrole=r.oid AND s.setdatabase<>0) FROM pg_catalog.pg_roles r WHERE r.rolname=ANY(%s) ORDER BY r.rolname
```
6. `memberships` — fixed list(s): 4 names
```sql
SELECT mr.rolname,ro.rolname,m.admin_option,m.inherit_option,m.set_option FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles mr ON mr.oid=m.member JOIN pg_catalog.pg_roles ro ON ro.oid=m.roleid WHERE mr.rolname=ANY(%s) ORDER BY 1,2
```
7. `sessions` — fixed list(s): 4 names
```sql
SELECT usename,state,backend_type FROM pg_catalog.pg_stat_activity WHERE usename=ANY(%s) OR (usename IS NULL AND backend_type='client backend' AND pid<>pg_catalog.pg_backend_pid()) ORDER BY pid
```
8. `functions` — fixed list(s): 7 names
```sql
SELECT p.proname,encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),r.rolname,p.proconfig,p.prosecdef,pg_catalog.pg_get_function_identity_arguments(p.oid) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace JOIN pg_catalog.pg_roles r ON r.oid=p.proowner WHERE n.nspname='public' AND p.proname=ANY(%s) ORDER BY p.proname,p.oid
```
9. `function_privileges` — fixed list(s): 7 names; 3 names
```sql
SELECT p.proname,r.rolname,pg_catalog.has_function_privilege(r.oid,p.oid,'EXECUTE') FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace CROSS JOIN pg_catalog.pg_roles r WHERE n.nspname='public' AND p.proname=ANY(%s) AND r.rolname=ANY(%s) ORDER BY 1,2
```
10. `table_privileges` — fixed list(s): 4 names; 3 names
```sql
SELECT r.rolname,c.relname,pg_catalog.has_table_privilege(r.oid,c.oid,'SELECT'),pg_catalog.has_table_privilege(r.oid,c.oid,'INSERT'),pg_catalog.has_table_privilege(r.oid,c.oid,'UPDATE'),pg_catalog.has_table_privilege(r.oid,c.oid,'DELETE'),pg_catalog.has_any_column_privilege(r.oid,c.oid,'INSERT'),pg_catalog.has_any_column_privilege(r.oid,c.oid,'UPDATE'),pg_catalog.has_any_column_privilege(r.oid,c.oid,'SELECT') FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p') AND c.relname=ANY(%s) AND r.rolname=ANY(%s) ORDER BY 1,2
```
11. `rollback` — —
```sql
ROLLBACK
```

4b. `roles` (fallback form without `pg_authid`; sent instead of statement 4 when `rolname` and `rolpassword` of `pg_authid` are not both readable)
```sql
SELECT r.rolname,r.rolcanlogin,NULL::boolean,r.rolvaliduntil,r.rolconnlimit,r.rolsuper,r.rolcreaterole,r.rolcreatedb,r.rolbypassrls,r.rolreplication FROM pg_catalog.pg_roles r WHERE r.rolname=ANY(%s) ORDER BY r.rolname
```

Variants: `control` is skipped if the control function is absent or not executable by the identity (reported UNKNOWN); `roles` uses the `pg_authid` form only if the identity may read both `rolname` and `rolpassword` of `pg_authid`, else the fallback form 4b above (password presence reported UNKNOWN); `sessions` is skipped unless the identity holds `pg_read_all_stats` (reported UNKNOWN).

## Accounting and bounds
Driver statements are counted as sent, including `BEGIN READ ONLY`, every SELECT and the `ROLLBACK`: **11 planned maximum, 9 minimum, ceiling 12 (unchanged)**. A failure after BEGIN attempts one counted ROLLBACK (11 + 1 = 12 at most); a dead connection is simply closed. 1 connection attempt, 0 commits, returned data ≤ 32 KiB, database seconds ≤ 30, active window 45 s after the 120 s hidden-input window, controller memory 256 MiB, aggregate 1.5 GiB, persisted evidence ≤ 64 KiB, terminal JSON ≤ 32 KiB. Server-side `statement_timeout` 10 s and `lock_timeout` 3 s come from the existing startup options.

## Output
Fixed fields only (see `tests/test_oldham_inspection_pg.py::test_the_result_has_only_the_fixed_fields`): no password or verifier value, credential, query text, application record or exception text.

## Proposed owner command — NOT AUTHORISED FOR EXECUTION
```
# 1. at the reviewed commit, in a clean checkout at $HOME/stage4-owner/inspection-checkout:
python docs/design/oldham-readonly-inspection-20261028/render_registration.py --minutes 60 > $HOME/stage4-owner/oldham-readonly-inspection-registration.json
# 2. note the sha256 printed to stderr, then (visible WSL terminal):
bash docs/design/oldham-readonly-inspection-20261028/owner-run.sh <commit> <tree> <registration-sha256>
```
It validates the registration (exact commit/tree/hashes, expiry ≤ 2 h, single-use audit namespace) before the hidden prompt, and refuses to run without a secure TTY.

## Separate production approval wording (to be given by the Product Owner; not given)
"I confirm I am at my Ubuntu terminal and attending. I approve ONE read-only inspection of the production database as the existing administrative postgres migration account (credential entered at the hidden prompt), with registration sha256 <…> at commit <…> / tree <…>: one connection, `BEGIN READ ONLY`, the fixed statements in docs/design/oldham-readonly-inspection-20261028/PACKAGE.md (at most 12), `ROLLBACK`, no GRANT, SET ROLE, installation, credential change, stop change, registration, GitHub access, source or council request. I understand this identity is administrative, that READ ONLY does not make it restricted, that the control function does not prove uncertainty barriers absent, and that TLS is verified by the existing route mechanism only at that connection."
