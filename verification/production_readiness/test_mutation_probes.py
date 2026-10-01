"""Offline probe-contract regression; native execution remains authoritative."""
import unittest
from unittest.mock import patch

from verification.production_readiness.native_rehearsal import probe_append_only


class MutationProbeTests(unittest.TestCase):
    def run_probe(self, after=None):
        before = {'claims': {'count': 3, 'hash': 'original'}, 'events': {'count': 5}}
        calls = []
        def forbidden(conn, name, statement, *, states):
            calls.append((name, statement, states))
        with patch('verification.production_readiness.native_rehearsal.evidence_hash',
                   side_effect=[before, before if after is None else after]):
            result = probe_append_only(object(), forbidden)
        return calls, result

    def test_fk_rejection_is_separate_and_exact(self):
        calls, _ = self.run_probe()
        self.assertEqual([c for c in calls if c[0].startswith('fk-')],
                         [('fk-TRUNCATE ah_source_claims', 'TRUNCATE ah_source_claims', ('0A000',))])

    def test_triggers_never_accept_fk_error(self):
        calls, _ = self.run_probe()
        triggers = [c for c in calls if c[0].startswith('trigger-')]
        self.assertEqual(len(triggers), 6)
        self.assertTrue(all(c[2] == ('P0001',) for c in triggers))
        self.assertIn('TRUNCATE ah_source_claims,ah_claim_events', [c[1] for c in triggers])
        self.assertIn('TRUNCATE ah_claim_events', [c[1] for c in triggers])
        self.assertFalse(any('CASCADE' in c[1] for c in calls))

    def test_both_tables_retain_update_delete_probes(self):
        calls, _ = self.run_probe()
        for table in ('ah_source_claims', 'ah_claim_events'):
            for statement in ('UPDATE '+table+' SET id=id', 'DELETE FROM '+table):
                self.assertIn(('trigger-'+statement, statement, ('P0001',)), calls)

    def test_unchanged_evidence_is_recorded(self):
        _, result = self.run_probe()
        self.assertEqual(result['before'], result['after'])

    def test_evidence_mutation_fails(self):
        with self.assertRaisesRegex(AssertionError, 'changed evidence'):
            self.run_probe(after={'claims': {'count': 0}})

    def test_probe_failure_is_not_swallowed(self):
        def failure(*args, **kwargs):
            raise AssertionError('operation unexpectedly succeeded')
        with patch('verification.production_readiness.native_rehearsal.evidence_hash', return_value={}):
            with self.assertRaisesRegex(AssertionError, 'unexpectedly succeeded'):
                probe_append_only(object(), failure)


if __name__ == '__main__':
    unittest.main()
