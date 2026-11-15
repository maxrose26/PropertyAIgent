"""Second interpreter of the disposable-only two-checkout recovery test."""
import json
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from app.ingestion.sql_ledger import SQLLedger
from app.ingestion.daily_intake import backlog_page
from tests.test_daily_intake_runtime import RULE
from tests.e2e_pg_world import settings
from tests.test_daily_intake_runtime import _continue_s4_04_recovery, _recovery_control


def main():
    raw, info, _, _ = settings()  # fixed loopback / disposable database only
    state = json.load(sys.stdin)  # synthetic credentials; never output or save
    assert state['migrator']['host'] == '127.0.0.1'
    assert state['migrator']['dbname'] == 'ingestion_provisioning_test'
    def connect(role):
        assert role == 'provisioning_migrator'
        return psycopg.connect(**state['migrator'],autocommit=True,prepare_threshold=None)
    with psycopg.connect(raw,autocommit=True,prepare_threshold=None) as boot:
        assert boot.info.server_version >= 170000
        oid = boot.execute('SELECT oid FROM pg_database WHERE datname=current_database()').fetchone()[0]
        assert oid == state['database_oid']
        w = dict(boot=boot,connect=connect,urls=state['urls'],pinned_settlement=True)
        before = _recovery_control(w)
        assert before['hard_stop_generation'] == 15
        # Existing fixture credentials are reused solely in this disposable DB.
        # The real owner fixture closed both roles before settlement; activate
        # their existing test-only memberships for the restricted synthetic CLI.
        for role,cap in [('ingestion_worker_login','ingestion_worker'),('ingestion_effect_login','ingestion_effect_broker')]:
            boot.execute(sql.SQL('ALTER ROLE {} LOGIN VALID UNTIL \'infinity\'').format(sql.Identifier(role)))
            boot.execute(sql.SQL('GRANT {} TO {} WITH INHERIT TRUE, SET TRUE').format(sql.Identifier(cap),sql.Identifier(role)))
        target=Path(sys.argv[1]);target.mkdir()
        try:
            _continue_s4_04_recovery(w,target)
            with psycopg.connect(raw,autocommit=True) as independent:
                independent.execute('BEGIN READ ONLY')
                rows=independent.execute("SELECT name,sha256=encode(sha256(body),'hex') FROM ingestion_run_evidence WHERE period='test-connected-poststop-tameside' ORDER BY name").fetchall()
                assert len(rows)==3 and all(r[1] for r in rows)
                independent.execute('ROLLBACK')
            engine=create_engine(raw.replace('postgresql://','postgresql+psycopg://',1),poolclass=NullPool)
            try:
                with engine.connect() as reader:
                    reader.exec_driver_sql('BEGIN READ ONLY')
                    page=backlog_page(SQLLedger(engine,owner='test',authority='',bindings={}),
                                      ['tameside'],['daily-intake-tameside'],RULE,connection=reader)
                    assert len(page['records'])==1
                    assert page['records'][0]['screening_state']=='COMPLETE'
                    assert page['records'][0]['archive']['readback_verified'] is True
                    reader.rollback()
            finally:
                engine.dispose()
        finally:
            for role,cap in [('ingestion_worker_login','ingestion_worker'),('ingestion_effect_login','ingestion_effect_broker')]:
                boot.execute(sql.SQL('ALTER ROLE {} NOLOGIN').format(sql.Identifier(role)))
                boot.execute(sql.SQL('REVOKE {} FROM {}').format(sql.Identifier(cap),sql.Identifier(role)))
        assert boot.execute("SELECT count(*) FROM pg_stat_activity WHERE usename IN ('ingestion_worker_login','ingestion_effect_login')").fetchone()==(0,)
        print(json.dumps(dict(status='CONNECTED_RECOVERY_PROVEN',same_database=True,
              postgres_version=boot.info.server_version,settlement_revision='f027ba28af69ae70208eab5ed047e4a8a81c6337',
              generations=[14,15,16],settlement_readback=state['settlement'],
              evidence_independent_readback=rows,synthetic_listing_records=1,
              backlog_independent_readback=True,
              screening='COMPLETE',coverage_advance=False,qualification=False,
              six_dispositions='CONDITIONAL_NOT_REVIEW_ACCEPTANCE',
              rollback_verified=True,lost_ack_reconciled=True,no_replay_verified=True,
              restricted_sessions=0),sort_keys=True))


if __name__=='__main__':
    main()
