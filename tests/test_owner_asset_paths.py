"""Owner readback assets must not depend on the caller's working directory."""
import hashlib,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from verification.ingestion_storage import operational_owner as old, intake_owner as owner
BASELINE={"ingestion_acceptance_control":"f25822db425df0c125df975d1cb46cfc710b76999744304d45d7037292d77d17","ingestion_bolton_allowed":"09d3e0e8e87bbf158bb89cb683063a21e5e8c23076d342961d49b50ac7e60569","ingestion_raise_stop":"5e41868876be6c533a31a8f7af25442ce308cb42681210296d516f361521e53a","ingestion_recover_abandoned":"9e7f98210c737d6f8f7fae2d98e328261ab9faf31481f041b6f63befa6686f58","ingestion_register_bolton_exception":"dba6b809c50b9bd937b2f509fc05c20de9d69499ca4394e9007ef3af196b481c","ingestion_worker_step":"abb46082f6d0891e131271a2567d45d8afdeccfd4561a6692baece7c3759c5bf"}
class Tests(unittest.TestCase):
 def test_function_bodies_identical_from_nonrepository_directory(self):
  before=Path.cwd()
  with tempfile.TemporaryDirectory() as d:
   try:
    os.chdir(d);actual=old.Owner.daily_intake_inventory()
   finally:os.chdir(before)
  self.assertEqual({k:hashlib.sha256(v.encode()).hexdigest() for k,v in actual.items()},BASELINE)
 def test_activation_gate_same_sql_outside_repository(self):
  before=Path.cwd();a=Mock();owner.activation_gate(a)
  with tempfile.TemporaryDirectory() as d:
   try:
    os.chdir(d);b=Mock();owner.activation_gate(b)
   finally:os.chdir(before)
  self.assertEqual(a.execute.call_args,b.execute.call_args)
 def test_retained_cleanup_reads_pinned_asset_outside_repository(self):
  c=Mock();c.execute.return_value.fetchone.return_value=('a'*64,)
  ctl={'grants':{owner.OLDHAM:{'expires_at':0}},'oldham_allowances':{owner.OLDHAM:{'revoked':True}}}
  before=Path.cwd()
  with tempfile.TemporaryDirectory() as d,patch.object(owner,'json_equal',return_value=False):
   try:
    os.chdir(d)
    with self.assertRaisesRegex(owner.Denied,'OLDHAM_HISTORICAL_BINDING_CHANGED'):owner.retained_cleanup(c,ctl)
   finally:os.chdir(before)
  self.assertTrue(c.execute.called)
if __name__=='__main__':unittest.main(verbosity=2)
