"""Render a pinned, INACTIVE one-shot owner writer installation transaction.

Preparation ONLY. No database connections, credentials, source calls, owner
decision or runtime activation are provided by this module. Its output is not
production installation authority. Separate exact-head review, live identity/
ACL observation, owner approval and rollback/readback controls remain required.

The writer source is the already-reviewed inactive candidate, not a second
copy of its 150-line SQL body. Reuse frozen #213 owner_pilot.Database for a
future separately authorised owner session; do not import it into #227.
"""
import hashlib

WRITER_SOURCE_GIT_BLOB = "e0ad8a32c8b466f265e551117e8bd795b5d82c6b"

PRELUDE = """BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '10s';
DO $owner_install_preflight$
DECLARE n integer; baseline_ok boolean;
BEGIN
 IF current_database() IS DISTINCT FROM 'postgres'
    OR session_user IS DISTINCT FROM 'postgres'
    OR current_user IS DISTINCT FROM 'postgres'
    OR (SELECT rolsuper OR NOT rolcreaterole OR NOT rolcreatedb OR NOT rolbypassrls
        FROM pg_catalog.pg_roles WHERE rolname=current_user)
 THEN RAISE EXCEPTION 'OWNER_WRITER_IDENTITY' USING ERRCODE='42501'; END IF;
 SELECT count(*),coalesce(bool_and(grantor<>'postgres'::regrole
       AND admin_option AND NOT inherit_option AND NOT set_option),false)
   INTO n,baseline_ok FROM pg_catalog.pg_auth_members
   WHERE member='postgres'::regrole AND roleid='ingestion_storage_owner'::regrole;
 IF n<>1 OR NOT baseline_ok
    OR pg_catalog.pg_has_role(current_user,'ingestion_storage_owner','USAGE')
    OR pg_catalog.pg_has_role(current_user,'ingestion_storage_owner','SET')
 THEN RAISE EXCEPTION 'OWNER_WRITER_ADMIN_ONLY_BASELINE' USING ERRCODE='42501'; END IF;
END $owner_install_preflight$;
DO $owner_schema_preflight$
BEGIN
 IF NOT pg_catalog.has_schema_privilege(current_user,'public','USAGE WITH GRANT OPTION')
    OR NOT pg_catalog.has_schema_privilege(current_user,'public','CREATE WITH GRANT OPTION')
 THEN RAISE EXCEPTION 'OWNER_WRITER_SCHEMA_CAPABILITY' USING ERRCODE='42501'; END IF;
END $owner_schema_preflight$;
GRANT ingestion_storage_owner TO postgres
 WITH ADMIN FALSE, INHERIT TRUE, SET TRUE GRANTED BY postgres;
"""

EPILOGUE = """
REVOKE ingestion_storage_owner FROM postgres GRANTED BY postgres RESTRICT;
DO $owner_install_restored$
DECLARE n integer; baseline_ok boolean;
BEGIN
 SELECT count(*),coalesce(bool_and(grantor<>'postgres'::regrole
       AND admin_option AND NOT inherit_option AND NOT set_option),false)
   INTO n,baseline_ok FROM pg_catalog.pg_auth_members
   WHERE member='postgres'::regrole AND roleid='ingestion_storage_owner'::regrole;
 IF n<>1 OR NOT baseline_ok
    OR current_user IS DISTINCT FROM 'postgres'
    OR session_user IS DISTINCT FROM 'postgres'
    OR pg_catalog.pg_has_role(current_user,'ingestion_storage_owner','USAGE')
    OR pg_catalog.pg_has_role(current_user,'ingestion_storage_owner','SET')
 THEN RAISE EXCEPTION 'OWNER_WRITER_CAPABILITY_REMAINS' USING ERRCODE='42501'; END IF;
END $owner_install_restored$;
COMMIT;
"""


def render_inactive_writer_install(source: str) -> str:
    """Pure renderer for exactly one pinned writer body and SQL transaction.

    Deliberately no file write, shell command, SQL executor or manifest switch.
    Refuse modified source; the returned SQL still requires a separate owner
    operational decision and may never be installed just because tests pass.
    """
    if not isinstance(source, str):
        raise ValueError("OWNER_WRITER_SOURCE_TYPE")
    raw = source.encode("utf-8")
    git_blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if git_blob != WRITER_SOURCE_GIT_BLOB:
        raise ValueError("OWNER_WRITER_SOURCE_DRIFT")
    if source.count("\nBEGIN;\n") != 1 or source.count("\nCOMMIT;\n") != 1:
        raise ValueError("OWNER_WRITER_TRANSACTION_BOUNDARY")
    body = source.replace("\nBEGIN;\n", "\n", 1).replace("\nCOMMIT;\n", "\n", 1)
    rendered = PRELUDE + body + EPILOGUE
    if rendered.count("\nCOMMIT;\n") != 1 or rendered.count("GRANT ingestion_storage_owner TO postgres") != 1:
        raise ValueError("OWNER_WRITER_RENDER_BOUNDARY")
    return rendered

# PA-D004 v1.3: reuse the EXACT existing inactive owner transaction lifecycle
# to prove one static historical issuer can be installed and rolled back by a
# non-superuser owner in a disposable database. This intentionally does not
# register a period, release a STOP, install into production, or enable runtime.
def render_inactive_stable_campaign_owner_install() -> str:
    """Pure one-shot, INACTIVE owner SQL artifact; not a deployment command.

    Reuses the existing source-pinned writer PRELUDE/EPILOGUE with its exact
    admin-only capability acquisition/restoration and owner identity checks.
    The SQL body is the single stable campaign issuer, which ALWAYS raises
    CAMPAIGN_STABLE_MANIFEST_WITHHELD even after successful installation.
    A separately approved owner release and production role/ACL observation
    are required before any real source execution.
    """
    from .inactive_tameside_first_issuer import (
        CAMPAIGN_FUNCTION, render_inactive_stable_campaign_issuer,
    )
    stable = render_inactive_stable_campaign_issuer()
    name = "public." + CAMPAIGN_FUNCTION + "(jsonb)"
    if (stable.count("CREATE OR REPLACE FUNCTION public." +
                     CAMPAIGN_FUNCTION + "(") != 1
            or stable.count("CAMPAIGN_STABLE_MANIFEST_WITHHELD") != 1
            or "REVOKE ALL ON FUNCTION " + name + " FROM PUBLIC;" not in stable
            or "GRANT EXECUTE" in stable
            or "ingestion_register_disposable_catchup" in stable):
        raise ValueError("OWNER_CAMPAIGN_STABLE_SOURCE_DRIFT")
    # Refuse replay/replacement of an existing installed function, even in a
    # disposable fixture. No time-dependent window-specific SQL is installed.
    one_shot = (
        "DO $campaign_owner_one_shot$ BEGIN\n"
        " IF to_regprocedure('" + name + "') IS NOT NULL THEN\n"
        "  RAISE EXCEPTION 'OWNER_CAMPAIGN_ALREADY_INSTALLED' USING ERRCODE='42501';\n"
        " END IF;\n"
        "END $campaign_owner_one_shot$;\n"
    )
    result = (PRELUDE + one_shot
              + "SET LOCAL ROLE ingestion_storage_owner;\n"
              + stable
              + "RESET ROLE;\n" + EPILOGUE)
    if (result.count("\nCOMMIT;\n") != 1
            or result.count("\nBEGIN;\n") != 0
            or result.count("GRANT ingestion_storage_owner TO postgres") != 1
            or result.count("REVOKE ingestion_storage_owner FROM postgres") != 1
            or result.count("SET LOCAL ROLE ingestion_storage_owner;") != 1
            or result.count("RESET ROLE;") != 1):
        raise ValueError("OWNER_CAMPAIGN_INSTALL_BOUNDARY_DRIFT")
    return result
