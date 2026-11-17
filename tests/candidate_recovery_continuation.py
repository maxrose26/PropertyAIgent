"""Continue actual guarded #213 recovery in the SAME disposable database."""
import json
import sys
from pathlib import Path
import psycopg
import pytest
from psycopg import sql
from tests.e2e_pg_world import settings
from tests.test_release_candidate_pg import exercise_conditional_runtime


def main():
    state=json.load(sys.stdin)
    raw,info,_,_=settings()
    assert state['owner']['host']=='127.0.0.1'
    assert state['owner']['dbname']=='ingestion_provisioning_test'
    def connect(role):
        assert role=='provisioning_migrator'
        return psycopg.connect(**state['migrator'],autocommit=True,prepare_threshold=None)
    def actor():
        return psycopg.connect(**state['owner'],autocommit=True,prepare_threshold=None)
    with psycopg.connect(raw,autocommit=True) as boot:
        assert boot.execute('SELECT oid FROM pg_database WHERE datname=current_database()').fetchone()[0]==state['database_oid']
        assert boot.execute("SELECT (outcome->>'hard_stop_generation')::int FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()==(15,)
        # Existing disposable worker credentials become usable only in this
        # synthetic fixture. This is not a production activation implementation.
        def activate():
            assert boot.execute("SELECT (outcome->>'hard_stop_generation')::int FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()==(16,)
            for role,cap in [('ingestion_worker_login','ingestion_worker'),('ingestion_effect_login','ingestion_effect_broker')]:
                boot.execute(sql.SQL('ALTER ROLE {} LOGIN').format(sql.Identifier(role)))
                boot.execute(sql.SQL('GRANT {} TO {} WITH INHERIT TRUE,SET TRUE').format(sql.Identifier(cap),sql.Identifier(role)))
        w=dict(boot=boot,connect=connect,actor=actor,urls=state['urls'],activate_restricted_fixture=activate)
        target=Path(sys.argv[1]);target.mkdir()
        try:
            with pytest.MonkeyPatch.context() as monkeypatch:
                result=exercise_conditional_runtime(w,target,monkeypatch,recovered=True)
        finally:
            for role,cap in [('ingestion_worker_login','ingestion_worker'),('ingestion_effect_login','ingestion_effect_broker')]:
                boot.execute(sql.SQL('ALTER ROLE {} NOLOGIN').format(sql.Identifier(role)))
                boot.execute(sql.SQL('REVOKE {} FROM {}').format(sql.Identifier(cap),sql.Identifier(role)))
        print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
