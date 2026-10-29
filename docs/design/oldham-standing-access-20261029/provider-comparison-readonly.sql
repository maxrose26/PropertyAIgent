-- INACTIVE: proposed fixed comparison only. No execution is authorised.
-- Fixed provider profile of oldham_inspection; one READ ONLY connection,
-- <=5s connect timeout; 5s statement,1s lock,30s active,16 statements,
-- 64KiB export. No extension-view rows or statistics functions are read.
BEGIN READ ONLY;
SET LOCAL statement_timeout='5s';
SET LOCAL lock_timeout='1s';
SELECT current_user,session_user,current_setting('transaction_read_only')='on' AS read_only;
WITH wanted(name,expected) AS (VALUES
 ('pg_stat_statements','ad1495ce5b4c54e4501e907a1f6aae8c'),
 ('pg_stat_statements_info','1807985dc152d2828720e1272d549775')),
 runtime(name) AS (VALUES ('ingestion_worker_login'),('ingestion_effect_login'))
SELECT w.name AS object,runtime.name AS role,c.oid IS NOT NULL AS present,
 c.relkind='v' AS view_kind,c.reloptions IS NULL AS no_options,
 md5(pg_get_viewdef(c.oid,true)) AS view_hash,
 md5(pg_get_viewdef(c.oid,true))=w.expected AS reviewed_definition,
 c.relowner=e.extowner AS extension_owner,
 EXISTS(SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass
   AND d.objid=c.oid AND d.deptype='e' AND d.refclassid='pg_extension'::regclass
   AND d.refobjid=e.oid) AS extension_member,
 CASE WHEN r.oid IS NOT NULL AND c.oid IS NOT NULL THEN
  NOT has_table_privilege(r.oid,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN,SELECT WITH GRANT OPTION')
 END AS no_forbidden_table_privileges,
 CASE WHEN r.oid IS NOT NULL AND c.oid IS NOT NULL THEN
  NOT has_any_column_privilege(r.oid,c.oid,'INSERT,UPDATE,REFERENCES,SELECT WITH GRANT OPTION') END AS no_forbidden_column_privileges,
 CASE WHEN r.oid IS NOT NULL AND n.oid IS NOT NULL THEN
  NOT has_schema_privilege(r.oid,n.oid,'USAGE,CREATE') END AS schema_denied
FROM wanted w CROSS JOIN runtime
LEFT JOIN pg_namespace n ON n.nspname='extensions'
LEFT JOIN pg_class c ON c.relnamespace=n.oid AND c.relname=w.name
LEFT JOIN pg_roles r ON r.rolname=runtime.name
LEFT JOIN pg_extension e ON e.extname='pg_stat_statements'
ORDER BY w.name,runtime.name;
WITH wanted(name,symbol,args,result,setof) AS (VALUES
 ('pg_stat_statements','pg_stat_statements_1_11','16',2249,true),
 ('pg_stat_statements_info','pg_stat_statements_info','',2249,false),
 ('pg_stat_statements_reset','pg_stat_statements_reset_1_11','26 26 20 16',1184,false))
SELECT w.name AS object,p.oid IS NOT NULL AS present,
 p.proowner=e.extowner AS extension_owner,p.proconfig IS NULL AS no_configuration,
 p.prokind='f' AS reviewed_function_kind,l.lanname='c' AS reviewed_language,
 NOT p.prosecdef AS no_security_definer,
 p.probin='$libdir/pg_stat_statements' AS reviewed_library,
 p.prosrc=w.symbol AS reviewed_symbol,p.proargtypes::text=w.args AS reviewed_arguments,
 p.prorettype=w.result::oid AS reviewed_result,p.proretset=w.setof AS reviewed_setof,
 EXISTS(SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass
   AND d.objid=p.oid AND d.refclassid='pg_extension'::regclass
   AND d.refobjid=e.oid AND d.deptype='e') AS extension_member,
 e.extversion='1.11' AS reviewed_extension_version,en.nspname='extensions' AS reviewed_extension_schema,
 (SELECT count(*) FROM pg_proc x WHERE x.pronamespace=n.oid AND x.proname=w.name) AS overload_count
FROM wanted w LEFT JOIN pg_namespace n ON n.nspname='extensions'
LEFT JOIN pg_proc p ON p.pronamespace=n.oid AND p.proname=w.name
LEFT JOIN pg_language l ON l.oid=p.prolang
LEFT JOIN pg_extension e ON e.extname='pg_stat_statements'
LEFT JOIN pg_namespace en ON en.oid=e.extnamespace
ORDER BY w.name,p.oid;
ROLLBACK;
