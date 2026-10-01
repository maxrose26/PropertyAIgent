"""Read-only psycopg 3 catalogue exporter; caller supplies a guarded connection.

No connection creation or transaction commits. Call inside one caller-owned
REPEATABLE READ, READ ONLY transaction. Object identities use names/definitions,
never database-specific OIDs. Extra public ah_* objects remain in the inventory
and therefore cannot disappear from comparison with the independent reference.
"""
import json
import re
from verification.production_readiness.catalog_verifier import SECTIONS

# This prefix deliberately includes every relation kind and function kind.
# Parameterisation applies even to role names supplied by a rehearsal runner.
PREFIX = r"""
WITH RECURSIVE base_rel AS (
 SELECT c.* FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND starts_with(c.relname,'ah_')
), rel AS (
 SELECT c.* FROM pg_catalog.pg_class c WHERE c.oid IN (
 SELECT oid FROM base_rel
 UNION SELECT indexrelid FROM pg_catalog.pg_index WHERE indrelid IN (SELECT oid FROM base_rel)
 UNION SELECT d.objid FROM pg_catalog.pg_depend d JOIN pg_catalog.pg_class s ON s.oid=d.objid AND s.relkind='S'
 WHERE d.classid='pg_class'::regclass AND d.refclassid='pg_class'::regclass AND d.refobjid IN (SELECT oid FROM base_rel)
 UNION SELECT d.refobjid FROM pg_catalog.pg_depend d JOIN pg_catalog.pg_attrdef a ON d.classid='pg_attrdef'::regclass AND d.objid=a.oid
 JOIN pg_catalog.pg_class s ON s.oid=d.refobjid AND s.relkind='S' WHERE d.refclassid='pg_class'::regclass AND a.adrelid IN (SELECT oid FROM base_rel)
 )
), fun AS (
 SELECT p.* FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
 WHERE (n.nspname='public' AND starts_with(p.proname,'ah_')) OR p.oid IN (SELECT tgfoid FROM pg_catalog.pg_trigger WHERE tgrelid IN (SELECT oid FROM rel))
), seed_roles(oid) AS (
 SELECT oid FROM pg_catalog.pg_roles WHERE rolname=ANY(%s::text[])
 UNION SELECT relowner FROM rel UNION SELECT proowner FROM fun
 UNION SELECT a.grantee FROM rel r CROSS JOIN LATERAL aclexplode(coalesce(r.relacl,acldefault(CASE WHEN r.relkind='S' THEN 'S'::"char" ELSE 'r'::"char" END,r.relowner))) a WHERE a.grantee<>0
 UNION SELECT a.grantee FROM fun f CROSS JOIN LATERAL aclexplode(coalesce(f.proacl,acldefault('f',f.proowner))) a WHERE a.grantee<>0
 UNION SELECT x.grantee FROM rel r JOIN pg_catalog.pg_attribute c ON c.attrelid=r.oid CROSS JOIN LATERAL aclexplode(c.attacl) x WHERE x.grantee<>0
 UNION SELECT x.grantor FROM rel r CROSS JOIN LATERAL aclexplode(r.relacl) x
 UNION SELECT x.grantor FROM fun f CROSS JOIN LATERAL aclexplode(f.proacl) x
 UNION SELECT x.grantor FROM rel r JOIN pg_catalog.pg_attribute c ON c.attrelid=r.oid CROSS JOIN LATERAL aclexplode(c.attacl) x
 UNION SELECT nspowner FROM pg_catalog.pg_namespace WHERE nspname='public'
 UNION SELECT x.grantee FROM pg_catalog.pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) x WHERE n.nspname='public' AND x.grantee<>0
 UNION SELECT x FROM pg_catalog.pg_policy p CROSS JOIN LATERAL unnest(p.polroles) x WHERE p.polrelid IN (SELECT oid FROM rel) AND x<>0
), relevant_roles(oid) AS (
 SELECT oid FROM seed_roles
 UNION
 SELECT CASE WHEN m.member=r.oid THEN m.roleid ELSE m.member END
 FROM relevant_roles r JOIN pg_catalog.pg_auth_members m ON r.oid IN (m.member,m.roleid)
)
"""

QUERIES = {
'relations': """SELECT (SELECT quote_ident(nspname) FROM pg_catalog.pg_namespace WHERE oid=r.relnamespace)||'.'||quote_ident(r.relname) AS identity, r.relkind, pg_get_userbyid(r.relowner) AS owner,
 r.relpersistence,r.relrowsecurity,r.relforcerowsecurity,r.relreplident,r.relispartition,
 r.reloptions, am.amname AS access_method, t.spcname AS tablespace,
 CASE WHEN r.relkind IN ('v','m') THEN pg_get_viewdef(r.oid,false) END AS view_definition,
 CASE WHEN r.relispartition THEN pg_get_expr(r.relpartbound,r.oid,false) END AS partition_bound,
 CASE WHEN r.relkind='p' THEN pg_get_partkeydef(r.oid) END AS partition_key
 FROM rel r LEFT JOIN pg_catalog.pg_am am ON am.oid=r.relam LEFT JOIN pg_catalog.pg_tablespace t ON t.oid=r.reltablespace""",
'columns': """SELECT (SELECT quote_ident(nspname) FROM pg_catalog.pg_namespace WHERE oid=r.relnamespace)||'.'||quote_ident(r.relname) AS relation,a.attnum,a.attname,a.attisdropped,
 format_type(a.atttypid,a.atttypmod) AS type,a.attnotnull,a.attidentity,a.attgenerated,
 a.attstorage,a.attcompression,a.attstattarget,a.attoptions,
 CASE WHEN co.oid IS NOT NULL THEN quote_ident(n.nspname)||'.'||quote_ident(co.collname) END AS collation,
 pg_get_expr(d.adbin,d.adrelid,false) AS default_expression
 FROM rel r JOIN pg_catalog.pg_attribute a ON a.attrelid=r.oid AND a.attnum>0
 LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=r.oid AND d.adnum=a.attnum
 LEFT JOIN pg_catalog.pg_collation co ON co.oid=a.attcollation LEFT JOIN pg_catalog.pg_namespace n ON n.oid=co.collnamespace""",
'constraints': """SELECT (SELECT quote_ident(nspname) FROM pg_catalog.pg_namespace WHERE oid=r.relnamespace)||'.'||quote_ident(r.relname) AS relation,c.conname,c.contype,c.condeferrable,c.condeferred,c.convalidated,
 c.conislocal,c.coninhcount,c.connoinherit,pg_get_constraintdef(c.oid,false) AS definition,
 CASE WHEN p.oid IS NOT NULL THEN p.conname END AS parent_constraint
 FROM rel r JOIN pg_catalog.pg_constraint c ON c.conrelid=r.oid LEFT JOIN pg_catalog.pg_constraint p ON p.oid=c.conparentid""",
'indexes': """SELECT quote_ident(n.nspname)||'.'||quote_ident(i.relname) AS identity,
 quote_ident(tn.nspname)||'.'||quote_ident(t.relname) AS relation,
 pg_get_indexdef(x.indexrelid,0,false) AS definition,x.indisunique,x.indisprimary,x.indisexclusion,
 x.indimmediate,x.indisclustered,x.indisvalid,x.indcheckxmin,x.indisready,x.indislive,x.indisreplident,
 pg_get_expr(x.indexprs,x.indrelid,false) AS expressions,pg_get_expr(x.indpred,x.indrelid,false) AS predicate
 FROM pg_catalog.pg_index x JOIN pg_catalog.pg_class i ON i.oid=x.indexrelid
 JOIN pg_catalog.pg_namespace n ON n.oid=i.relnamespace JOIN pg_catalog.pg_class t ON t.oid=x.indrelid
 JOIN pg_catalog.pg_namespace tn ON tn.oid=t.relnamespace
 WHERE x.indexrelid IN (SELECT oid FROM rel) OR x.indrelid IN (SELECT oid FROM rel)""",
'sequences': """SELECT (SELECT quote_ident(nspname) FROM pg_catalog.pg_namespace WHERE oid=r.relnamespace)||'.'||quote_ident(r.relname) AS identity,format_type(s.seqtypid,NULL) AS type,
 s.seqstart,s.seqincrement,s.seqmax,s.seqmin,s.seqcache,s.seqcycle,pg_get_userbyid(r.relowner) AS owner
 FROM rel r JOIN pg_catalog.pg_sequence s ON s.seqrelid=r.oid""",
'sequence_dependencies': """SELECT (SELECT quote_ident(nspname) FROM pg_catalog.pg_namespace WHERE oid=r.relnamespace)||'.'||quote_ident(r.relname) AS sequence,d.deptype,
 pg_describe_object(d.refclassid,d.refobjid,d.refobjsubid) AS depends_on,
 pg_describe_object(d.classid,d.objid,d.objsubid) AS dependent_object
 FROM pg_catalog.pg_depend d JOIN rel r ON (d.classid='pg_class'::regclass AND d.objid=r.oid)
 WHERE r.relkind='S'
 UNION ALL
 SELECT (SELECT quote_ident(nspname) FROM pg_catalog.pg_namespace WHERE oid=r.relnamespace)||'.'||quote_ident(r.relname),d.deptype,pg_describe_object(d.refclassid,d.refobjid,d.refobjsubid),
 pg_describe_object(d.classid,d.objid,d.objsubid)
 FROM pg_catalog.pg_depend d JOIN rel r ON d.refclassid='pg_class'::regclass AND d.refobjid=r.oid WHERE r.relkind='S'""",
 'triggers': """SELECT (SELECT quote_ident(nspname) FROM pg_catalog.pg_namespace WHERE oid=r.relnamespace)||'.'||quote_ident(r.relname) AS relation,t.tgname,t.tgenabled,t.tgisinternal,
 pg_get_triggerdef(t.oid,false) AS definition,pg_describe_object('pg_proc'::regclass,t.tgfoid,0) AS function,
 CASE WHEN c.oid IS NOT NULL THEN c.conname END AS constraint_name,
 c.contype AS constraint_type,
 CASE WHEN c.oid IS NOT NULL THEN pg_describe_object('pg_class'::regclass,c.conrelid,0) END AS constraint_relation,
 t.tgtype,t.tgdeferrable,t.tginitdeferred,encode(t.tgargs,'hex') AS arguments
 FROM rel r JOIN pg_catalog.pg_trigger t ON t.tgrelid=r.oid LEFT JOIN pg_catalog.pg_constraint c ON c.oid=t.tgconstraint""",
'functions': """SELECT (SELECT quote_ident(nspname) FROM pg_catalog.pg_namespace WHERE oid=f.pronamespace)||'.'||quote_ident(f.proname)||'('||pg_get_function_identity_arguments(f.oid)||')' AS identity,
 f.prokind,pg_get_userbyid(f.proowner) AS owner,l.lanname AS language,
 f.prosecdef,f.proleakproof,f.proisstrict,f.proretset,f.provolatile,f.proparallel,f.proconfig,
 f.procost,f.prorows,pg_get_function_arguments(f.oid) AS arguments,pg_get_function_result(f.oid) AS result,
 CASE WHEN f.prokind<>'a' THEN pg_get_functiondef(f.oid) ELSE f.prosrc END AS definition
 FROM fun f JOIN pg_catalog.pg_language l ON l.oid=f.prolang""",
'policies': """SELECT (SELECT quote_ident(nspname) FROM pg_catalog.pg_namespace WHERE oid=r.relnamespace)||'.'||quote_ident(r.relname) AS relation,p.polname,p.polcmd,p.polpermissive,
 ARRAY(SELECT CASE WHEN x=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x) END FROM unnest(p.polroles) x ORDER BY 1) AS roles,
 pg_get_expr(p.polqual,p.polrelid,false) AS using_expression,pg_get_expr(p.polwithcheck,p.polrelid,false) AS check_expression
 FROM rel r JOIN pg_catalog.pg_policy p ON p.polrelid=r.oid""",
'acl': """SELECT 'relation' AS kind,(SELECT quote_ident(nspname) FROM pg_catalog.pg_namespace WHERE oid=r.relnamespace)||'.'||quote_ident(r.relname) AS identity,NULL::text AS column_name,
 pg_get_userbyid(a.grantor) AS grantor,CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS grantee,a.privilege_type,a.is_grantable
 FROM rel r CROSS JOIN LATERAL aclexplode(coalesce(r.relacl,acldefault(CASE WHEN r.relkind='S' THEN 'S'::"char" ELSE 'r'::"char" END,r.relowner))) a
 UNION ALL SELECT 'column',(SELECT quote_ident(nspname) FROM pg_catalog.pg_namespace WHERE oid=r.relnamespace)||'.'||quote_ident(r.relname),c.attname,pg_get_userbyid(a.grantor),CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,a.privilege_type,a.is_grantable
 FROM rel r JOIN pg_catalog.pg_attribute c ON c.attrelid=r.oid CROSS JOIN LATERAL aclexplode(c.attacl) a
 UNION ALL SELECT 'function',(SELECT quote_ident(nspname) FROM pg_catalog.pg_namespace WHERE oid=f.pronamespace)||'.'||quote_ident(f.proname)||'('||pg_get_function_identity_arguments(f.oid)||')',NULL,
 pg_get_userbyid(a.grantor),CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,a.privilege_type,a.is_grantable
 FROM fun f CROSS JOIN LATERAL aclexplode(coalesce(f.proacl,acldefault('f',f.proowner))) a
 UNION ALL SELECT 'schema','public',NULL,pg_get_userbyid(a.grantor),CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,a.privilege_type,a.is_grantable
 FROM pg_catalog.pg_namespace n CROSS JOIN LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a WHERE n.nspname='public'""",
'default_acl': """SELECT pg_get_userbyid(d.defaclrole) AS owner,coalesce(n.nspname,'GLOBAL') AS schema,d.defaclobjtype,
 pg_get_userbyid(a.grantor) AS grantor,CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS grantee,a.privilege_type,a.is_grantable
 FROM pg_catalog.pg_default_acl d LEFT JOIN pg_catalog.pg_namespace n ON n.oid=d.defaclnamespace
 LEFT JOIN LATERAL aclexplode(d.defaclacl) a ON true
 WHERE d.defaclrole IN (SELECT oid FROM relevant_roles) AND (d.defaclnamespace=0 OR n.nspname='public')""",
'roles': """SELECT r.rolname,r.rolsuper,r.rolinherit,r.rolcreaterole,r.rolcreatedb,r.rolcanlogin,
 r.rolreplication,r.rolconnlimit,r.rolbypassrls,r.rolvaliduntil::text,r.rolconfig
 FROM pg_catalog.pg_roles r WHERE r.oid IN (SELECT oid FROM relevant_roles)""",
'memberships': """SELECT pg_get_userbyid(m.roleid) AS role,pg_get_userbyid(m.member) AS member,
 pg_get_userbyid(m.grantor) AS grantor,m.admin_option,
 to_jsonb(m)->>'inherit_option' AS inherit_option,to_jsonb(m)->>'set_option' AS set_option
 FROM pg_catalog.pg_auth_members m WHERE m.roleid IN (SELECT oid FROM relevant_roles) OR m.member IN (SELECT oid FROM relevant_roles)""",
}


def _rows(conn, sql, params=()):
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        names=[c.name if hasattr(c,'name') else c[0] for c in cursor.description]
        return [dict(zip(names,row)) if not isinstance(row,dict) else row for row in cursor.fetchall()]



def _stable_trigger(row):
    """Remove only PostgreSQL's generated FK-trigger name's database OID.

    Keep user trigger names and all execution semantics. Constraint identity,
    function identity and trigger type distinguish the paired FK triggers.
    Unexpected internal trigger forms remain verbatim (fail-closed drift).
    """
    name = row.get('tgname', '')
    if not (row.get('tgisinternal') and row.get('constraint_type') == 'f'
            and re.fullmatch(r'RI_ConstraintTrigger_[ac]_[0-9]+', name)):
        return row
    if not all(row.get(key) is not None for key in
               ('constraint_name', 'constraint_relation', 'function', 'tgtype')):
        raise ValueError('Internal FK trigger lacks stable constraint identity')
    definition = row.get('definition', '')
    prefix = 'CREATE CONSTRAINT TRIGGER "' + name + '" '
    if not definition.startswith(prefix):
        raise ValueError('Unexpected internal FK trigger definition')
    stable = 'internal_fk:' + json.dumps(
        [row['constraint_relation'], row['constraint_name'], row['function'], row['tgtype']],
        separators=(',', ':'))
    result = dict(row, tgname=stable)
    result['definition'] = 'CREATE CONSTRAINT TRIGGER <internal_fk> ' + definition[len(prefix):]
    return result


def export_catalog(conn, role_names, migration_sha256, expected_ddl_sha256, *, allow_writable_snapshot=False):
    """Export a guarded connection without commits, writes or connection creation.

    Snapshot rows are stable sorted JSON objects. Does not certify native tests,
    approve a migration, or learn an expected schema from the candidate.
    """
    if not isinstance(role_names,(list,tuple)) or not role_names or any(not isinstance(r,str) or not r for r in role_names) or len(set(role_names))!=len(role_names):
        raise ValueError('Explicit unique role names required')
    if any(not isinstance(h,str) or not re.fullmatch(r'[0-9a-f]{64}',h) for h in (migration_sha256,expected_ddl_sha256)):
        raise ValueError('Expected SHA256 hashes required')
    state=_rows(conn,"SELECT current_setting('server_version_num')::int AS version, current_setting('transaction_read_only') AS read_only, current_setting('transaction_isolation') AS isolation")
    if len(state)!=1 or (state[0]['read_only']!='on' and not allow_writable_snapshot) or state[0]['isolation'] not in ('repeatable read','serializable'):
        raise ValueError('Caller must establish one repeatable-read read-only transaction')
    if set(QUERIES)!=set(SECTIONS):
        raise RuntimeError('Catalogue section mismatch')
    catalog={}
    for section in SECTIONS:
        rows=_rows(conn,PREFIX+QUERIES[section],(list(role_names),))
        if section == 'triggers':
            rows = [_stable_trigger(row) for row in rows]
        catalog[section]=sorted(rows,key=lambda r:json.dumps(r,sort_keys=True,separators=(',',':')))
    present={r['rolname'] for r in catalog['roles']}
    if not set(role_names)<=present:
        raise ValueError('Requested roles missing from catalogue')
    return dict(server_version_num=int(state[0]['version']),role_names=list(role_names),
                migration_sha256=migration_sha256,expected_ddl_sha256=expected_ddl_sha256,catalog=catalog)
