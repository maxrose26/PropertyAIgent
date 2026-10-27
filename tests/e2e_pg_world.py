"""Disposable PostgreSQL world for the end-to-end connection: the same reviewed installation sequence as `test_ingestion_v3_admission_pg.py` (identical SQL packages, roles and
restricted logins) and the same fixed-URL and version enforcement: only 127.0.0.1:5432, the fixed database and the fixed bootstrap role, and a PostgreSQL 17 or newer server.

Hosted CI is the authority (the postgres:17 service). The server version is recorded in the world so a result on another version is never presented as the PostgreSQL 17 proof.
A developer machine that already runs its own PostgreSQL on 5432 must not be touched: run these tests in a private network namespace (see the runner note in the PR), where
loopback and port 5432 are the namespace's own.
"""
import copy
import os
import secrets
import time
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.db.models import Base, Council
from tests.test_discovery_ingestion_provisioning_pg import PACKAGE, ROLES
from verification.ingestion_storage import screening_v3_worker_sql

NAMES = ['provisioning_migrator', 'ingestion_worker_login', 'ingestion_storage_login', 'ingestion_effect_login', 'ingestion_recovery_login', 'ingestion_application_login']
RESTRICTED = ['ingestion_worker_login', 'ingestion_effect_login', 'ingestion_application_login']
COUNCILS = {
    'bury': dict(name='Bury',base_url='https://planning.bury.gov.uk/online-applications',date_field_mode='received',doc_system='idox_anite'),
    'oldham': dict(name='Oldham',base_url='https://planningpa.oldham.gov.uk/online-applications',date_field_mode='received',doc_system='idox'),
    'tameside': dict(name='Tameside Metropolitan Borough Council', base_url='https://publicaccess.tameside.gov.uk/online-applications', date_field_mode='received', doc_system='idox'),
    'stockport': dict(name='Stockport Metropolitan Borough Council', base_url='https://planning.stockport.gov.uk/PlanningData-live', date_field_mode='validated', doc_system='idox'),
    'manchester': dict(name='Manchester City Council', base_url='https://arcusbe.manchester.gov.uk/pr', date_field_mode='validated', doc_system='arcus'),
}


def settings():
    raw = os.environ.get('INGESTION_PROVISIONING_TEST_URL')
    if not raw:
        pytest.skip('fixed disposable PostgreSQL service required')
    info = psycopg.conninfo.conninfo_to_dict(raw)
    assert (info['host'], info['port'], info['dbname'], info['user']) == ('127.0.0.1', '5432', 'ingestion_provisioning_test', 'provisioning_bootstrap'), 'FIXED_DISPOSABLE_ONLY'
    return raw, info, 5432, 170000


def disposable_world():
    raw, info, port, minimum = settings()
    passwords = {name: secrets.token_urlsafe(48) for name in NAMES}
    started = time.monotonic()
    costs = dict(connection_attempts=1, cursor_calls=0)

    class CountingCursor(psycopg.Cursor):
        def execute(self, *args, **kwargs):
            costs['cursor_calls'] += 1
            return super().execute(*args, **kwargs)

    with psycopg.connect(raw, autocommit=True, prepare_threshold=None, cursor_factory=CountingCursor) as boot:
        assert boot.info.server_version >= minimum, 'DISPOSABLE_POSTGRES_VERSION'
        app = create_engine(URL.create('postgresql+psycopg', username=info['user'], password=info['password'], host='127.0.0.1', port=port, database=info['dbname']),
                            poolclass=NullPool, connect_args=dict(cursor_factory=CountingCursor))

        def connect(role):
            costs['connection_attempts'] += 1
            return psycopg.connect(**{**info, 'user': role, 'password': passwords[role]}, autocommit=True, prepare_threshold=None, cursor_factory=CountingCursor)

        try:
            boot.execute(sql.SQL('CREATE ROLE provisioning_migrator LOGIN NOSUPERUSER NOCREATEDB CREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}').format(sql.Literal(passwords['provisioning_migrator'])))
            boot.execute('GRANT USAGE,CREATE ON SCHEMA public TO provisioning_migrator WITH GRANT OPTION')
            boot.execute('GRANT CONNECT ON DATABASE ingestion_provisioning_test TO provisioning_migrator WITH GRANT OPTION')
            with connect('provisioning_migrator') as c:
                c.execute((PACKAGE / 'install.sql').read_text())
                c.execute(Path('docs/design/ingestion-operational-20261016/worker.sql').read_text())
            Base.metadata.create_all(app)
            writer = Path('docs/design/ingestion-operational-acceptance-20261016/application-writer.sql').read_text()
            grants = '\n'.join(line for line in writer.splitlines() if not line.startswith('CREATE ROLE ')).replace(' TO ingestion_application_writer', ' TO provisioning_migrator WITH GRANT OPTION')
            boot.execute(grants)
            with connect('provisioning_migrator') as c:
                c.execute(writer)
                c.execute(Path('docs/design/ingestion-operational-acceptance-20261016/runtime-mappings.sql').read_text())
                c.execute(screening_v3_worker_sql.installation_script())      # the existing reviewed derived v3 worker function, unchanged, installed as fixture only
            for role in NAMES[1:]:
                boot.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(role), sql.Literal(passwords[role])))
            with connect('provisioning_migrator') as c:
                c.execute(Path('docs/design/ingestion-operational-acceptance-20261016/activate.sql').read_text())
            with Session(app) as session:
                session.add_all([Council(code=code, **values) for code, values in COUNCILS.items()])
                session.commit()
            control = boot.execute("SELECT outcome FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
            initial_control = copy.deepcopy(control)
            # Disposable authority fixture only: no production stop is read or changed, and no stop is bypassed. The disposable control record starts with no stop and no grants.
            control['global_stop'] = None
            control['manual_stop'] = None
            control['grants'] = {}
            urls = {role: URL.create('postgresql+psycopg', username=role, password=passwords[role], host='127.0.0.1', port=port, database=info['dbname']).render_as_string(hide_password=False) for role in NAMES[1:]}
            yield dict(boot=boot, app=app, control=control, initial_control=initial_control, urls=urls, connect=connect, port=port, server_version=boot.info.server_version,
                       setup_seconds=time.monotonic() - started, setup_costs=dict(costs))
        finally:
            app.dispose()
            boot.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public')
            extra = ['ingestion_application_writer', 'ingestion_effect_broker', 'ingestion_recovery_operator', 'ingestion_effect_login', 'ingestion_recovery_login', 'ingestion_application_login']
            for name in ['provisioning_migrator', *ROLES, *extra]:
                boot.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(name)))
            for name in ['provisioning_migrator', *ROLES, *extra]:
                boot.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(name)))
