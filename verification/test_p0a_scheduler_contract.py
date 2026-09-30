"""Standard-library admission checks; not a substitute for real lifecycle tests."""
import os
import unittest
from unittest.mock import patch
from app.pipeline import discovery_owner as owner

class SchedulerContractTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ, {'RENDER_SERVICE_TYPE':'cron',
            'RENDER_SERVICE_ID':owner.SERVICE_ID,'RENDER_INSTANCE_ID':'run-first'}, clear=True)
        self.env.start(); self.addCleanup(self.env.stop)
    def test_unverified_contract_blocks_production(self):
        with self.assertRaisesRegex(RuntimeError,'unverified'): owner.require_scheduled_identity()
    def test_known_shell_rejected_even_by_permissive_test_pattern(self):
        with patch.object(owner,'SCHEDULED_INSTANCE_PATTERN','.*'), patch.dict(os.environ,{'RENDER_INSTANCE_ID':'shl-'+owner.SERVICE_ID}):
            with self.assertRaisesRegex(RuntimeError,'rejected'): owner.require_scheduled_identity()
    def test_offline_attested_shape(self):
        with patch.object(owner,'SCHEDULED_INSTANCE_PATTERN',r'run-[a-z]+'):
            self.assertEqual(owner.require_scheduled_identity(),'run-first')
    def test_wrong_service_is_not_scheduled_identity(self):
        with patch.object(owner,'SCHEDULED_INSTANCE_PATTERN',r'run-[a-z]+'),patch.dict(os.environ,{'RENDER_SERVICE_ID':'foreign'}):
            with self.assertRaisesRegex(RuntimeError,'invalid'): owner.require_scheduled_identity()
    def test_successor_requires_both_contracts(self):
        old=dict(version=1,invocation='first',service=owner.SERVICE_ID,instance='run-first',scheduler_contract=owner.SCHEDULER_CONTRACT)
        new={**old,'invocation':'second','instance':'run-second'}
        with patch.object(owner,'SCHEDULED_INSTANCE_PATTERN',r'run-[a-z]+'):
            self.assertEqual(owner.terminal_evidence(old,new),'same_service_successor_admitted')
            for key,value in [('instance','shl-'+owner.SERVICE_ID),('scheduler_contract',None)]:
                with self.assertRaisesRegex(RuntimeError,'unresolved'): owner.terminal_evidence({**old,key:value},new)
    def test_legacy_row_not_an_owner(self):
        self.assertIsNone(owner.terminal_evidence(None,{}))
    def test_same_host_active_child_still_blocks(self):
        old=dict(version=1,invocation='first',service='local',instance='local',boot='b',pid=12,pid_start=1,child_pid=13,child_start=2)
        with patch.object(owner,'process_identity',side_effect=lambda pid:None if pid==12 else 2):
            with self.assertRaisesRegex(RuntimeError,'unresolved'): owner.terminal_evidence(old,{**old,'invocation':'next'})

if __name__=='__main__': unittest.main()
