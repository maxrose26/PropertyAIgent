import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from .final_guard import validate_environment,BRANCH
from .final_rehearsal import integrity,MIG,EXP,P,R

class FinalTests(unittest.TestCase):
    def env(self):return {'GITHUB_ACTIONS':'true','GITHUB_REF':BRANCH,'AH_REHEARSAL_NONPRODUCTION':'YES_DISPOSABLE_ONLY','AH_SERVICE_ID':'a'*64}
    def test_integrity(self):integrity()
    def test_exact_migration(self):self.assertEqual(hashlib.sha256((P/'004_production_proposal.sql').read_bytes()).hexdigest(),MIG)
    def test_exact_schema(self):self.assertEqual(hashlib.sha256((R/'expected_schema.json').read_bytes()).hexdigest(),EXP)
    def test_guard_accepts_only_fixture(self):
        with tempfile.TemporaryDirectory() as d:validate_environment(self.env(),Path(d))
    def test_guard_denies_sensitive_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            for key in ('DATABASE_URL','PGHOST','SUPABASE_URL','OPENAI_API_KEY','RENDER_API_KEY','DB_PASSWORD'):
                e=self.env();e[key]='redacted'
                with self.subTest(key=key),self.assertRaises(ValueError):validate_environment(e,Path(d))
    def test_guard_denies_wrong_branch_and_identity(self):
        with tempfile.TemporaryDirectory() as d:
            for key,val in [('GITHUB_REF','refs/heads/master'),('AH_SERVICE_ID','localhost'),('AH_REHEARSAL_NONPRODUCTION',''),('GITHUB_ACTIONS','false')]:
                e=self.env();e[key]=val
                with self.subTest(key=key),self.assertRaises(ValueError):validate_environment(e,Path(d))
    def test_env_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'.env').write_text('not-a-secret')
            with self.assertRaises(ValueError):validate_environment(self.env(),Path(d))
    def test_workflow_manual_and_service(self):
        s=(R.parents[1]/'.github/workflows/ah-native-postgres.yml').read_text()
        self.assertIn('on:\n  workflow_dispatch:\n',s)
        for bad in ('  push:','  pull_request:','  schedule:','  workflow_run:','secrets.','postgres:16','supabase.com'):
            self.assertNotIn(bad,s)
        self.assertIn('image: postgres:17.6',s)
        self.assertEqual(s.count('AH_SERVICE_ID: ${{ job.services.postgres.id }}'),3)
    def test_null_sequence_acl_type(self):
        s=(R/'native_exporter.py').read_text()
        self.assertNotIn("WHEN r.relkind='S' THEN 'S'::",s)
        self.assertEqual(s.count("WHEN r.relkind='S' THEN 's'::"),2)
    def test_rls_probe_is_not_missing_select(self):
        s=(P/'final_rehearsal.py').read_text()
        self.assertIn('GRANT SELECT,INSERT ON ah_source_claims TO ah_evidence_importer',s)
        self.assertIn("'row-level security' not in str(e).lower()",s)
    def test_fail_closed_results(self):
        s=(P/'final_rehearsal.py').read_text()
        self.assertIn("raise AssertionError('Incomplete native acceptance areas')",s)
        self.assertIn("ok('bounded-reader-positive')",s)
        w=(R.parents[1]/'.github/workflows/ah-native-postgres.yml').read_text()
        self.assertIn('Offline guard and artifact tests\n        shell: bash',w)
    def test_no_approved_sql_rewrite(self):
        s=(P/'final_rehearsal.py').read_text()
        self.assertNotIn('004_production_proposal.sql\').write',s)
        self.assertIn("raise\n            installed=True",s)

if __name__=='__main__':unittest.main(verbosity=2)
