import hashlib
from tests.test_database_evidence_migration_pg import migration_world,installed,world,support
from verification.ingestion_storage import intake_owner as op
from verification.ingestion_storage.database_evidence import migration_sql,verify_inventory
from verification.ingestion_storage.owner_pilot_continuation import migrate_owner_namespace
import pytest

def test_attempt06_exact_namespace_history_and_cleanup(migration_world,record_property):
 b=migration_world['boot']
 with support.actor() as c:
  support.execute(c,migration_sql())
  for kw in ({'qualification':True},{'deadline':True},{'diagnostic_cap':True}):migrate_owner_namespace(c,**kw)
  old='b-dbpilot-20261027-1102-05_owner';rid=hashlib.sha256(old.encode()).hexdigest()[:32]
  prior=c.execute('SELECT * FROM ingestion_intake_owner_state(%s,%s,%s,%s)',(old,rid,'',b'preserved-synthetic-ciphertext')).fetchone()
 before=b.execute(op.MEMBERS).fetchall();ledger=op.ledger_sha(b)
 with support.actor() as c:
  r=migrate_owner_namespace(c,attempt06=True)
  assert r['permissions_restored'] and r['status']=='COMMIT_ACKNOWLEDGED_AND_READ_BACK'
  assert c.execute('SELECT * FROM ingestion_intake_owner_state(%s,%s,%s,NULL::bytea)',(old,rid,'')).fetchone()==prior
  exact=migrate_owner_namespace(c,attempt06=True);assert exact['mutation'] is False
  name='b-dbpilot-20261027-1102-06_owner';run=hashlib.sha256(name.encode()).hexdigest()[:32]
  assert c.execute('SELECT * FROM ingestion_intake_owner_state(%s,%s,%s,NULL::bytea)',(name,run,'')).fetchone() is None
  row=c.execute('SELECT * FROM ingestion_intake_owner_state(%s,%s,%s,%s)',(name,run,'',b'x'*32768)).fetchone()
  assert row[0]==0 and len(row[1])==32768
  assert c.execute('SELECT * FROM ingestion_intake_owner_state(%s,%s,%s,%s)',(name,run,'',b'x'*32768)).fetchone()==row
  for body,previous,reason in [(b'x'*32769,row[2],'VAULT_BOUND'),(b'y','0'*64,'CONCURRENT_OR_UNCERTAIN')]:
   with pytest.raises(Exception,match=reason):c.execute('SELECT * FROM ingestion_intake_owner_state(%s,%s,%s,%s)',(name,run,previous,body))
   c.execute('ROLLBACK')
  verify_inventory(c);op.owner_absent(c)
 assert b.execute(op.MEMBERS).fetchall()==before and op.ledger_sha(b)==ledger and support.actor_flags()==(False,False,False)
 record_property('postgres_version',migration_world['server_version']);record_property('permissions_restored',True);record_property('historical_row_unchanged',True)
