"""Real disposable PG17: add05 without changing existing stable credentials."""
import pytest
from tests.test_database_evidence_migration_pg import migration_world,installed,world,support
from verification.ingestion_storage import owner_pilot_continuation as step,intake_owner as op,stable_runtime_credentials as stable
from verification.ingestion_storage.database_evidence import migration_sql,OWNER_SQL,verify_inventory

@pytest.mark.parametrize('mode',['success','rollback'])
def test_namespace05_preserves_stable_verifiers_history_and_privileges(migration_world,monkeypatch,record_property,mode):
    boot=migration_world['boot']
    with support.actor() as c:
        support.execute(c,migration_sql());secrets=stable.prepare(c);stable.configure(c,secrets)
    old=OWNER_SQL.split('REVOKE ALL ON FUNCTION',1)[0].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1).replace(",'b-dbpilot-20261027-1102-05_owner'",'')
    boot.execute(old);ledger=op.ledger_sha(boot);members=boot.execute(op.MEMBERS).fetchall();schema=boot.execute("SELECT nspacl::text FROM pg_namespace WHERE nspname='public'").fetchone()
    source=boot.execute("SELECT prosrc FROM pg_proc WHERE proname='ingestion_intake_owner_state'").fetchone()[0]
    if mode=='rollback':monkeypatch.setattr(step,'verify_inventory',lambda c:(_ for _ in ()).throw(RuntimeError('SYNTHETIC_LATE_FAILURE')))
    with support.actor() as c:
        if mode=='success':step.migrate_owner_namespace(c,stable_verifiers=secrets['verifier_sha256']);step.migrate_owner_namespace(c,stable_verifiers=secrets['verifier_sha256'])
        else:
            with pytest.raises(RuntimeError):step.migrate_owner_namespace(c,stable_verifiers=secrets['verifier_sha256'])
            assert c.execute("SELECT prosrc FROM pg_proc WHERE proname='ingestion_intake_owner_state'").fetchone()[0]==source
        op.dormant(c,stable_verifiers=secrets['verifier_sha256']);op.owner_absent(c)
    assert stable.hashes(boot)==secrets['verifier_sha256'] and op.ledger_sha(boot)==ledger
    assert boot.execute(op.MEMBERS).fetchall()==members and boot.execute("SELECT nspacl::text FROM pg_namespace WHERE nspname='public'").fetchone()==schema
    assert support.actor_flags()==(False,False,False)
    record_property('server_version',migration_world['server_version']);record_property('actor_superuser',False)

@pytest.mark.parametrize('mode',['success','rollback'])
def test_qualification_namespace_preserves_closed_attempt_bytes(migration_world,monkeypatch,record_property,mode):
    import hashlib
    from verification.ingestion_storage.database_evidence import QUALIFICATION_OWNER_SQL
    boot=migration_world['boot']
    with support.actor() as c:
        support.execute(c,migration_sql());secrets=stable.prepare(c);stable.configure(c,secrets)
    period='b-dbpilot-20261027-1102-05_owner';raw=b'synthetic-closed-history'
    boot.execute('INSERT INTO ingestion_run_evidence(period,run_id,name,body,sha256) VALUES(%s,%s,%s,%s,%s)',(period,hashlib.sha256(period.encode()).hexdigest()[:32],'owner/state-000',raw,hashlib.sha256(raw).hexdigest()))
    before=boot.execute('SELECT period,run_id,name,body,sha256,created_at FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()
    ledger=op.ledger_sha(boot);members=boot.execute(op.MEMBERS).fetchall()
    source=boot.execute("SELECT prosrc FROM pg_proc WHERE proname='ingestion_intake_owner_state'").fetchone()[0]
    if mode=='rollback':monkeypatch.setattr(step,'verify_inventory',lambda c:(_ for _ in ()).throw(RuntimeError('SYNTHETIC_PRECOMMIT_FAILURE')))
    with support.actor() as c:
        if mode=='success':
            step.migrate_owner_namespace(c,stable_verifiers=secrets['verifier_sha256'],qualification=True)
            step.migrate_owner_namespace(c,stable_verifiers=secrets['verifier_sha256'],qualification=True)
            assert c.execute("SELECT prosrc FROM pg_proc WHERE proname='ingestion_intake_owner_state'").fetchone()[0]==QUALIFICATION_OWNER_SQL.split('$owner_state$',2)[1]
        else:
            with pytest.raises(RuntimeError):step.migrate_owner_namespace(c,stable_verifiers=secrets['verifier_sha256'],qualification=True)
            assert c.execute("SELECT prosrc FROM pg_proc WHERE proname='ingestion_intake_owner_state'").fetchone()[0]==source
        op.owner_absent(c);op.dormant(c,stable_verifiers=secrets['verifier_sha256'])
    assert boot.execute('SELECT period,run_id,name,body,sha256,created_at FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()==before
    assert op.ledger_sha(boot)==ledger and boot.execute(op.MEMBERS).fetchall()==members
    record_property('server_version',migration_world['server_version']);record_property('history_rows_preserved',len(before))
