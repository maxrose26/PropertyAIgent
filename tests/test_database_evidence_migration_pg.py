"""Exact migration on existing non-superuser production-shaped PG17 fixture."""
import pytest
from tests.test_intake_owner_finite import installed,world,support,accepted
from verification.ingestion_storage import intake_owner as op
from verification.ingestion_storage.database_evidence import migration_sql

@pytest.fixture
def migration_world(installed):
 accepted(installed)
 yield installed
 b=installed['boot']
 b.execute('DROP FUNCTION IF EXISTS ingestion_intake_evidence_write(text,text,text,bytea)')
 b.execute('DROP FUNCTION IF EXISTS ingestion_intake_evidence_read(text,text,text)')
 b.execute('DROP TABLE IF EXISTS ingestion_run_evidence')

@pytest.mark.parametrize('mode',['success','late_failure','wrong_predecessor'])
def test_exact_atomic_migration_cleanup_and_predecessor(migration_world,mode,record_property):
 w=migration_world;b=w['boot'];before=op.ledger_sha(b);members=b.execute(op.MEMBERS).fetchall()
 sql=migration_sql()
 if mode=='late_failure':sql=sql.replace('DO $post$', 'SELECT 1/0;\nDO $post$',1)
 if mode=='wrong_predecessor':sql=sql.replace('dba6b809c50b9bd937b2f509fc05c20de9d69499ca4394e9007ef3af196b481c','0'*64,1)
 with support.actor() as c:
  assert c.execute('SELECT rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()==(False,)
  if mode=='success':support.execute(c,sql)
  else:
   with pytest.raises(Exception) as failure:support.execute(c,sql)
   assert getattr(failure.value,'sqlstate',None)==('22012' if mode=='late_failure' else 'P0001')
   c.execute('ROLLBACK')
 assert op.ledger_sha(b)==before and b.execute(op.MEMBERS).fetchall()==members
 assert support.actor_flags()==(False,False,False)
 assert (b.execute("SELECT to_regclass('public.ingestion_run_evidence')").fetchone()[0] is not None)==(mode=='success')
 if mode=='success':
  with support.actor() as c:op.inventory(c)
  assert b.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='public.ingestion_run_evidence'::regclass").fetchone()==(True,True)
 record_property('server_version',w['server_version']);record_property('actor_superuser',False)
