"""Control observation against a REAL disposable PostgreSQL 17 with the real installed ledger: normal rollback and failure/disconnect leave no membership, option, password, setting or control-row change
behind, and a failed readback is reported as unverified. The one operation that is not strictly read-only - the transaction-local `GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE` - is
named, exercised and observed from OUTSIDE the observer (as the bootstrap superuser). Disposable loopback server only."""
import json
import os
import secrets
from datetime import datetime,timezone,timedelta

import psycopg
import pytest
from psycopg import sql

from app.ingestion.ledger import digest
from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_owner import Owner
from verification.ingestion_storage.operational_publication import GitHub
from tests.test_discovery_ingestion_provisioning_pg import ROLES as BASE_ROLES, PACKAGE
from tests.test_ingestion_control_observation import registration

EXTRA=['ingestion_effect_login','ingestion_effect_broker','ingestion_recovery_operator']
ROLE='observation_migrator'


class Tap:
    """A real connection with a hook that can fail or terminate it at a chosen statement. Everything else is delegated untouched."""
    def __init__(self,conn,hook):self.conn=conn;self.hook=hook
    def execute(self,statement,params=None):
        self.hook(' '.join(str(statement).split()),self)
        return self.conn.execute(statement,params)
    @property
    def closed(self):return self.conn.closed
    def close(self):self.conn.close()
    def __getattr__(self,name):return getattr(self.conn,name)


@pytest.fixture
def disposable():
    raw=os.environ.get('INGESTION_PROVISIONING_TEST_URL')
    if not raw:pytest.skip('fixed disposable PG17 required')
    info=psycopg.conninfo.conninfo_to_dict(raw)
    assert (info['host'],info['port'],info['dbname'],info['user'])==('127.0.0.1','5432','ingestion_provisioning_test','provisioning_bootstrap')
    password=secrets.token_urlsafe(48)
    def connector():return psycopg.connect(**{**info,'user':ROLE,'password':password},autocommit=True,prepare_threshold=None,connect_timeout=3)
    with psycopg.connect(raw,autocommit=True) as boot:
        boot.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER CREATEROLE CREATEDB BYPASSRLS NOINHERIT PASSWORD {}').format(sql.Identifier(ROLE),sql.Literal(password)))
        boot.execute(sql.SQL('GRANT USAGE,CREATE ON SCHEMA public TO {} WITH GRANT OPTION').format(sql.Identifier(ROLE)))
        boot.execute(sql.SQL('GRANT CONNECT ON DATABASE ingestion_provisioning_test TO {} WITH GRANT OPTION').format(sql.Identifier(ROLE)))
        boot.execute(sql.SQL('GRANT SELECT(rolname,rolpassword) ON pg_catalog.pg_authid TO {}').format(sql.Identifier(ROLE)))
        boot.execute(sql.SQL('GRANT pg_read_all_stats TO {} WITH INHERIT TRUE').format(sql.Identifier(ROLE)))
        boot.execute('CREATE SCHEMA extensions')
        boot.execute("CREATE EXTENSION pg_stat_statements WITH SCHEMA extensions VERSION '1.11'")
        boot.execute(sql.SQL('GRANT USAGE ON SCHEMA extensions TO {}').format(sql.Identifier(ROLE)))
        try:
            with connector() as c:      # the same installation sequence as the pipeline lifecycle test: the provisioning package, then the operational installer
                c.execute((PACKAGE/'install.sql').read_text())
                c.execute('REVOKE ingestion_worker FROM ingestion_worker_login')
                c.execute('REVOKE ingestion_storage_operator FROM ingestion_storage_login')
            boot.execute("SELECT public.ingestion_raise_stop('STORAGE_TEST_STOP')")
            installer=Owner(connector,lambda *_:None,lambda:None,identity=ROLE,expiry=datetime.now(timezone.utc)+timedelta(minutes=30),bindings={})
            installer.install()      # the real ledger, the real roles, the real ADMIN-only membership of the migration identity
            boot.execute("SELECT public.ingestion_raise_stop('IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE')")
            yield boot,connector
        finally:
            boot.execute('DROP TABLE IF EXISTS public.ingestion_work_attempts,public.ingestion_work_items CASCADE')
            boot.execute('DROP EXTENSION IF EXISTS pg_stat_statements')
            boot.execute('DROP SCHEMA IF EXISTS extensions')
            for r in [*EXTRA,*BASE_ROLES,ROLE]:
                if boot.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(r,)).fetchone():boot.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(r)))
            for r in [*EXTRA,*BASE_ROLES,ROLE]:boot.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(r)))


def catalog(boot):
    """Everything the transaction-local GRANT could leave behind, read as the bootstrap superuser: every membership row with its options and grantor, every role's login/password hash/validity/settings,
    and the control record."""
    return dict(
        memberships=[tuple(map(str,r)) for r in boot.execute("SELECT member::regrole::text,roleid::regrole::text,admin_option,inherit_option,set_option,grantor::regrole::text FROM pg_auth_members ORDER BY 1,2,6").fetchall()],
        roles=[tuple(map(str,r)) for r in boot.execute("SELECT a.rolname,a.rolcanlogin,coalesce(a.rolpassword,''),coalesce(a.rolvaliduntil::text,''),coalesce(r.rolconfig::text,'') FROM pg_authid a JOIN pg_roles r ON r.oid=a.oid ORDER BY 1").fetchall()],
        control=digest(boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]),
        sessions=boot.execute('SELECT count(*) FROM pg_stat_activity WHERE usename=%s',(ROLE,)).fetchone()[0])


def run_observer(tmp_path,connector,hook):
    holder={}
    journal=Journal(tmp_path/'j')
    github=GitHub(journal.emit,lambda:holder['r'].check(),bound=0)
    def tapped():return Tap(connector(),hook)
    r=orr.Runner(registration(),journal,tapped,source_reader=lambda row:(_ for _ in ()).throw(AssertionError('no source request')),github=github,url_factory=None,identity=ROLE)
    holder['r']=r
    return r.execute(),r


def no_hook(text,tap):pass


def test_a_normal_observation_leaves_the_catalog_exactly_as_it_was(disposable,tmp_path):
    boot,connector=disposable
    before=catalog(boot)
    assert any(m[0]==ROLE and m[1]=='ingestion_storage_owner' for m in before['memberships'])      # the installed ADMIN-only membership of the migration identity exists before
    result,runner=run_observer(tmp_path,connector,no_hook)
    after=catalog(boot)
    assert result['status']=='CONTROL_OBSERVED_NO_COMMITTED_MUTATION' and result['cleanup']=='CLOSED' and result['committed_writes']==0
    observation=result['observation']
    assert observation['statements']==6 and observation['transient_owner_capability']=='ROLLED_BACK_AND_READ_BACK_ABSENT'
    assert after==before      # no membership row, option, grantor, password hash, validity, setting or control-record change; no session left
    projection=observation['projection']
    assert projection['manual_stop']=='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE' and projection['hard_stop_generation']>=1 and projection['global_stop']['reason']=='CONSUMED_SALFORD_GLOBAL_STOP'
    assert projection['counts']==dict(grants=0,grants_unexpired=0,exceptions=0,exceptions_unexpired=0)
    # What the observer saw is what an independent read of the real record says
    real=boot.execute("SELECT outcome::jsonb->>'manual_stop',(outcome::jsonb->>'hard_stop_generation')::int FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()
    assert (projection['manual_stop'],projection['hard_stop_generation'])==tuple(real)
    assert runner.github.requests==0 and runner.owner.connections==1 and runner.owner.commands==6


@pytest.mark.parametrize('scenario',['failure_after_grant','disconnect_after_grant','failed_readback','failure_before_grant'])
def test_a_failure_or_disconnect_leaves_no_membership_behind_and_is_reported_as_unverified(disposable,tmp_path,scenario):
    boot,connector=disposable
    before=catalog(boot)
    def hook(text,tap):
        if scenario=='failure_after_grant' and text.startswith('SELECT outcome::jsonb'):raise RuntimeError('injected failure after the grant')
        if scenario=='disconnect_after_grant' and text.startswith('SELECT outcome::jsonb'):
            boot.execute('SELECT pg_terminate_backend(%s)',(tap.conn.info.backend_pid,))      # the server kills the session while the transaction is open
        if scenario=='failed_readback' and text.startswith('SELECT pg_has_role'):raise RuntimeError('injected failure of the capability readback')
        if scenario=='failure_before_grant' and text.startswith('BEGIN'):raise RuntimeError('injected failure before the grant')
    result,runner=run_observer(tmp_path,connector,hook)
    after=catalog(boot)
    assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['committed_writes']==0 and result['source_observations_attempted']==0 and result['execution_grants_created']==0
    assert after==before,(scenario,before['memberships'],after['memberships'])      # observed from outside the observer: nothing is left behind, whatever the failure
    assert 'UNVERIFIED' in result['transient_owner_capability'] and 'NOT_READ_BACK' in result['transient_owner_capability']      # the observer itself cannot, and does not claim to, have verified absence
    events=[json.loads(l)['event'] for l in (tmp_path/'j'/'events.jsonl').read_text().splitlines()] if (tmp_path/'j'/'events.jsonl').exists() else []
    assert 'control_observation' not in events      # no observation record is claimed after a failure
    assert runner.github.requests==0 and runner.owner.connections==1


def test_a_second_run_after_the_failures_is_still_clean(disposable,tmp_path):
    boot,connector=disposable
    before=catalog(boot)
    for scenario in ('a','b'):
        def hook(text,tap):
            if scenario=='a' and text.startswith('SELECT outcome::jsonb'):raise RuntimeError('injected')
        run_observer(tmp_path/scenario,connector,hook)
    assert catalog(boot)==before
