"""Evidence for the teardown session policy: a session that survives the disable keeps NO capability privileges.

The matrix left one idle `ingestion_worker_login` backend after its teardown (NOLOGIN, NULL password, capability membership revoked). This disposable test shows the mechanics the policy
relies on: privileges obtained through a role membership are evaluated at statement time, so revoking the membership removes them from an ALREADY OPEN session immediately, while the
session itself persists. It does NOT show that a surviving session is harmless in every respect (it can still run statements the login is entitled to without any membership, and it holds a
connection slot) - which is why the policy still requires bounded waiting and exact termination, and reports any residual session as UNCERTAIN, never CLOSED."""
import psycopg,pytest
from tests.test_ingestion_admin_connection_probe import cluster      # noqa: F401


def admin(cluster):return psycopg.connect(host='127.0.0.1',port=cluster.port,dbname='postgres',user='postgres',autocommit=True)


def test_an_open_session_loses_membership_granted_privileges_when_the_membership_is_revoked(cluster):
    with admin(cluster) as a:
        for stmt in ('DROP TABLE IF EXISTS ssp_ledger','DROP ROLE IF EXISTS ssp_login','DROP ROLE IF EXISTS ssp_capability'):a.execute(stmt)
        a.execute('CREATE ROLE ssp_capability NOLOGIN');a.execute('CREATE ROLE ssp_login LOGIN CONNECTION LIMIT 1')
        a.execute('CREATE TABLE ssp_ledger(i int)');a.execute('INSERT INTO ssp_ledger VALUES (1)');a.execute('GRANT SELECT ON ssp_ledger TO ssp_capability')
        a.execute('GRANT ssp_capability TO ssp_login WITH ADMIN FALSE, INHERIT TRUE, SET FALSE')
        held=psycopg.connect(host='127.0.0.1',port=cluster.port,dbname='postgres',user='ssp_login',autocommit=True)
        try:
            assert held.execute('SELECT count(*) FROM ssp_ledger').fetchone()==(1,)                     # privilege through the membership works
            a.execute('ALTER ROLE ssp_login NOLOGIN PASSWORD NULL');a.execute('REVOKE ssp_capability FROM ssp_login')
            assert a.execute("SELECT count(*) FROM pg_stat_activity WHERE usename='ssp_login'").fetchone()==(1,)      # the session survives the disable
            with pytest.raises(psycopg.errors.InsufficientPrivilege):held.execute('SELECT count(*) FROM ssp_ledger')     # ... but no longer has the privilege
            with pytest.raises(psycopg.OperationalError):                                              # and no NEW login is possible
                psycopg.connect(host='127.0.0.1',port=cluster.port,dbname='postgres',user='ssp_login',connect_timeout=3)
        finally:
            held.close()
            for stmt in ('DROP TABLE IF EXISTS ssp_ledger','DROP ROLE IF EXISTS ssp_login','DROP ROLE IF EXISTS ssp_capability'):a.execute(stmt)
