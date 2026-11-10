"""Tests for the prospective policy assessment; NO SQL / deletion."""
import copy
import unittest
from app.ingestion.retention_dry_run import assess_retention, assess_unverified_storage_snapshot

T0='2026-01-01T00:00:00+00:00'
AS_OF='2026-11-09T19:00:00+00:00'

def row(**kwargs):
    result=dict(period='new-period',run_id='a'*32,name='capture-1/source.json',
                sha256='b'*64,bytes=120,captured_at=T0,
                retention_tag='PA_D002_PROSPECTIVE_V1',readback_verified=True,
                resolution='RECONCILED',resolved_at=T0,explicit_hold=False,
                hold_history_verified=True,hold_released_at=None,
                historical=False)
    result.update(kwargs)
    # Optimistic policy fixtures represent a separately resolved old run.
    # VERIFIED runs instead need both private final receipts, tested below.
    if result['resolution'] == 'RECONCILED' and 'resolved_at' not in kwargs:
        result['resolved_at'] = result['captured_at']
    elif result['resolution'] in ('VERIFIED', 'UNRESOLVED') and 'resolved_at' not in kwargs:
        result['resolved_at'] = None
    return result

def verified_index(*records):
    # Synthetic *trusted* manifest for prospective policy unit tests only;
    # not proof of an authenticated database inventory.
    return {(records[0]['period'], records[0]['run_id']):
            frozenset((r['name'], r['sha256']) for r in records)}

class RetentionSafety(unittest.TestCase):
    def find(self,record,as_of=AS_OF):
        outcome=assess_retention([record],as_of=as_of,
                                 verified_run_index=verified_index(record))
        self.assertTrue(outcome['dry_run_only'])
        self.assertEqual(outcome['sql_or_delete_operations'],0)
        self.assertFalse(outcome['items'][0]['may_delete_now'])
        return outcome['items'][0]['disposition']

    def test_verified_old_prospective_only_candidate(self):
        self.assertEqual(self.find(row()),'FUTURE_OWNER_REVIEW_CANDIDATE')
        self.assertEqual(self.find(row(historical=True)),'PRESERVE_HISTORICAL_OR_UNTAGGED')
        # Fresh historical evidence must keep its real provenance refusal.
        self.assertEqual(self.find(row(historical=True,
                                     captured_at='2026-11-01T00:00:00Z')),
                         'PRESERVE_HISTORICAL_OR_UNTAGGED')
        self.assertEqual(self.find(row(retention_tag='UNKNOWN')),'PRESERVE_HISTORICAL_OR_UNTAGGED')

    def test_unresolved_and_hold_are_never_candidates(self):
        self.assertEqual(self.find(row(resolution='UNRESOLVED')),'PRESERVE_UNRESOLVED')
        self.assertEqual(self.find(row(explicit_hold=True)),'PRESERVE_EXPLICIT_HOLD')
        self.assertEqual(self.find(row(readback_verified=False)),'PRESERVE_UNVERIFIED')

    def test_missing_trusted_hold_history_cannot_offer_owner_review(self):
        self.assertEqual(self.find(row(hold_history_verified=False)),
                         'PRESERVE_UNVERIFIED_HOLD_HISTORY')

    def test_hold_release_restarts_raw_and_metadata_index_clocks(self):
        # A hold lifted yesterday must not make old evidence a review candidate.
        held = row(hold_released_at='2026-10-15T00:00:00Z')
        result = assess_retention([held], as_of=AS_OF,
                                  verified_run_index=verified_index(held))['items'][0]
        self.assertEqual(result['disposition'], 'PRESERVE_WITHIN_RETENTION')
        self.assertEqual(result['raw_not_before'], '2027-01-13T00:00:00+00:00')
        self.assertEqual(result['index_keep_through_at_least'],
                         '2027-10-15T00:00:00+00:00')
        old = row(hold_released_at='2026-02-01T00:00:00Z')
        self.assertEqual(self.find(old), 'FUTURE_OWNER_REVIEW_CANDIDATE')
        # An unresolved current hold always preserves, even after a year.
        self.assertEqual(self.find(row(explicit_hold=True)), 'PRESERVE_EXPLICIT_HOLD')

    def test_resolution_restarts_full_90_day_clock(self):
        self.assertEqual(self.find(row(resolution='RECONCILED',resolved_at='2026-10-01T00:00:00Z')),
                         'PRESERVE_WITHIN_RETENTION')
        self.assertEqual(self.find(row(resolution='RECONCILED',resolved_at='2026-05-01T00:00:00Z')),
                         'FUTURE_OWNER_REVIEW_CANDIDATE')

    def test_boundary_and_never_delete(self):
        recent='2026-08-11T19:00:00Z'
        self.assertEqual(self.find(row(captured_at=recent)), 'FUTURE_OWNER_REVIEW_CANDIDATE')
        self.assertEqual(self.find(row(captured_at='2026-08-12T00:00:00Z')),'PRESERVE_WITHIN_RETENTION')

    def test_malformed_uncertain_inventory_refused(self):
        invalid=[row(bytes=True),row(bytes=524289),row(name='capture-3/source.json'),
                 row(resolution='RECONCILED',resolved_at=None),row(resolution='VERIFIED',resolved_at='2026-08-01T00:00:00Z'),
                 row(captured_at='9999-01-01T00:00:00Z'),row(captured_at='2026-01-01'),
                 row(explicit_hold='false'),row(sha256='not-a-hash'),row(retention_tag=None),
                 row(hold_history_verified='yes'),
                 row(hold_history_verified=False,hold_released_at='2026-08-01T00:00:00Z'),
                 row(explicit_hold=True,hold_released_at='2026-08-01T00:00:00Z'),
                 row(hold_released_at='2025-12-31T00:00:00Z'),
                 row(hold_released_at='2026-12-01T00:00:00Z'),
                 row(hold_released_at='not-a-date')]
        for case in invalid:
            with self.subTest(case=case),self.assertRaises(ValueError):
                assess_retention([case],as_of=AS_OF)
        with self.assertRaises(ValueError):
            assess_retention([row(),row()],as_of=AS_OF)
        with self.assertRaises(ValueError):
            assess_retention([dict(row(),raw_source='SECRET')],as_of=AS_OF)

    def test_verified_run_needs_both_private_finals_and_source(self):
        # A structural manifest of a lone VERIFIED capture must preserve it,
        # even when old, fully hashed and otherwise apparently eligible.
        source = row(resolution='VERIFIED')
        alone = assess_retention([source], as_of=AS_OF,
                                 verified_run_index=verified_index(source))
        self.assertEqual(alone['items'][0]['disposition'],
                         'PRESERVE_RUN_FINAL_EVIDENCE_UNVERIFIED')
        final_result = row(name='final/result-before-publication.json',
                           sha256='c'*64, resolution='VERIFIED')
        final_events = row(name='final/events-before-publication.json',
                           sha256='d'*64, resolution='VERIFIED')
        for truncated in ([source, final_result], [final_result, final_events]):
            outcome = assess_retention(truncated, as_of=AS_OF,
                                       verified_run_index=verified_index(*truncated))
            self.assertEqual({i['disposition'] for i in outcome['items']},
                             {'PRESERVE_RUN_FINAL_EVIDENCE_UNVERIFIED'})
        complete = [source, final_result, final_events]
        positive = assess_retention(complete, as_of=AS_OF,
                                    verified_run_index=verified_index(*complete))
        self.assertEqual({i['disposition'] for i in positive['items']},
                         {'FUTURE_OWNER_REVIEW_CANDIDATE'})
        self.assertTrue(all(i['may_delete_now'] is False for i in positive['items']))

    def test_impossible_run_wide_storage_size_preserves(self):
        # Per-item bounds alone cannot prove the existing aggregate 2 MiB cap.
        source = row(resolution='VERIFIED', bytes=524288)
        final_result = row(name='final/result-before-publication.json',
                           sha256='c'*64, bytes=1400000, resolution='VERIFIED')
        final_events = row(name='final/events-before-publication.json',
                           sha256='d'*64, bytes=300000, resolution='VERIFIED')
        items = [source, final_result, final_events]
        observed = assess_retention(items, as_of=AS_OF,
                                    verified_run_index=verified_index(*items))
        self.assertEqual({i['disposition'] for i in observed['items']},
                         {'PRESERVE_RUN_STORAGE_BOUND_UNVERIFIED'})
        self.assertTrue(all(not i['may_delete_now'] for i in observed['items']))

    def test_unverified_storage_snapshot_is_preservation_only(self):
        # Storage hash, byte size and capture timestamp do NOT authenticate
        # prospective retention, hold releases or a resolved failure.
        stored=dict(period='new-period',run_id='a'*32,
                    name='capture-1/source.json',stored_sha256='b'*64,
                    actual_sha256='b'*64,bytes=120,created_at=T0)
        result=assess_unverified_storage_snapshot([stored],as_of=AS_OF)
        self.assertTrue(result['dry_run_only'])
        self.assertEqual(result['sql_or_delete_operations'],0)
        self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['disposition'],
                         'PRESERVE_HISTORICAL_OR_UNTAGGED')
        self.assertFalse(result['items'][0]['may_delete_now'])
        self.assertNotIn('stored_sha256',result['items'][0])
        self.assertNotIn('created_at',result['items'][0])
        # Caller cannot smuggle trusted flags, raw bytes or a mismatched digest.
        invalid=[dict(stored,body=b'private'),dict(stored,historical=False),
                 dict(stored,actual_sha256='c'*64),dict(stored,bytes=0),
                 dict(stored,created_at='2100-01-01T00:00:00Z')]
        for case in invalid:
            with self.subTest(case=case),self.assertRaises(ValueError):
                assess_unverified_storage_snapshot([case],as_of=AS_OF)
        with self.assertRaises(ValueError):
            assess_unverified_storage_snapshot([stored,stored],as_of=AS_OF)

    def test_run_wide_uncertainty_and_owner_hold_cannot_release_sibling(self):
        a = row(name='capture-1/source.json')
        b = row(name='capture-2/source.json', resolution='UNRESOLVED')
        outcome = assess_retention([a, b], as_of=AS_OF,
                                   verified_run_index=verified_index(a, b))
        self.assertEqual({item['disposition'] for item in outcome['items']},
                         {'PRESERVE_RUN_UNRESOLVED'})
        for override, expected in (
            ({'explicit_hold': True}, 'PRESERVE_RUN_EXPLICIT_HOLD'),
            ({'hold_history_verified': False}, 'PRESERVE_RUN_HOLD_HISTORY_UNVERIFIED'),
            ({'readback_verified': False}, 'PRESERVE_RUN_READBACK_UNVERIFIED'),
            ({'historical': True}, 'PRESERVE_RUN_PROVENANCE_UNVERIFIED'),
            ({'resolution': 'RECONCILED',
              'resolved_at': '2026-05-01T00:00:00Z'},
             'PRESERVE_RUN_RESOLUTION_CONFLICT'),
        ):
            second = row(name='capture-2/source.json', **override)
            candidate = assess_retention([a, second], as_of=AS_OF,
                                         verified_run_index=verified_index(a, second))
            self.assertEqual({item['disposition'] for item in candidate['items']},
                             {expected})
            self.assertTrue(all(not item['may_delete_now']
                                for item in candidate['items']))

    def test_latest_capture_or_hold_release_starts_run_wide_clock(self):
        # VERIFIED-run fixtures include both required private final receipts.
        older = row(name='capture-1/source.json', resolution='VERIFIED')
        recent = row(name='capture-2/source.json',
                     captured_at='2026-10-15T00:00:00Z', resolution='VERIFIED')
        final_result = row(name='final/result-before-publication.json',
                           sha256='c'*64, resolution='VERIFIED')
        final_events = row(name='final/events-before-publication.json',
                           sha256='d'*64, resolution='VERIFIED')
        records = [older, recent, final_result, final_events]
        outcome = assess_retention(records, as_of=AS_OF,
                                   verified_run_index=verified_index(*records))
        self.assertEqual({i['disposition'] for i in outcome['items']},
                         {'PRESERVE_WITHIN_RETENTION'})
        self.assertEqual({i['raw_not_before'] for i in outcome['items']},
                         {'2027-01-13T00:00:00+00:00'})
        self.assertEqual({i['index_keep_through_at_least']
                          for i in outcome['items']}, {'2027-10-15T00:00:00+00:00'})
        release = row(name='capture-2/source.json', resolution='VERIFIED',
                      hold_released_at='2026-10-15T00:00:00Z')
        records = [older, release, final_result, final_events]
        outcome = assess_retention(records, as_of=AS_OF,
                                   verified_run_index=verified_index(*records))
        self.assertEqual({i['disposition'] for i in outcome['items']},
                         {'PRESERVE_WITHIN_RETENTION'})
        self.assertEqual({i['raw_not_before'] for i in outcome['items']},
                         {'2027-01-13T00:00:00+00:00'})

    def test_missing_or_truncated_run_inventory_never_recommends_review(self):
        original = row()
        sibling = row(name='capture-2/source.json', sha256='c'*64)
        no_index = assess_retention([original], as_of=AS_OF)
        self.assertEqual(no_index['items'][0]['disposition'],
                         'PRESERVE_RUN_INVENTORY_UNVERIFIED')
        incomplete = assess_retention([original], as_of=AS_OF,
                    verified_run_index=verified_index(original, sibling))
        self.assertEqual(incomplete['items'][0]['disposition'],
                         'PRESERVE_RUN_INVENTORY_UNVERIFIED')
        mismatched = assess_retention([original], as_of=AS_OF,
                    verified_run_index=verified_index(row(sha256='c'*64)))
        self.assertEqual(mismatched['items'][0]['disposition'],
                         'PRESERVE_RUN_INVENTORY_UNVERIFIED')
        trusted = assess_retention([original, sibling], as_of=AS_OF,
                    verified_run_index=verified_index(original, sibling))
        self.assertEqual({i['disposition'] for i in trusted['items']},
                         {'FUTURE_OWNER_REVIEW_CANDIDATE'})
        self.assertTrue(all(not i['may_delete_now'] for i in trusted['items']))
        with self.assertRaisesRegex(ValueError, 'RETENTION_RUN_INDEX_SHAPE'):
            assess_retention([original], as_of=AS_OF, verified_run_index=[])

    def test_sorted_minimal_output_no_raw_fields(self):
        a=row(name='capture-2/source.json')
        b=row()
        result=assess_retention([a,b],as_of=AS_OF,
                                verified_run_index=verified_index(a,b))
        self.assertEqual([e['name'] for e in result['items']],
                         ['capture-1/source.json','capture-2/source.json'])
        self.assertEqual(result['total'],2)
        self.assertFalse(any('body' in x or 'address' in x for x in result['items'][0]))

if __name__=='__main__': unittest.main()
