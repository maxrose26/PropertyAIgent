"""Offline standard-library tests of the real threshold module."""
import unittest
from app.policy.ah_count_threshold import assess_count_threshold as assess


class CountThresholdTests(unittest.TestCase):
    def check(self, expected, **kwargs):
        self.assertEqual(assess(threshold=50, qualified=True, **kwargs), expected)

    def test_minimum_boundaries(self):
        for count, expected in [(44,'does_not_meet'),(45,'investigate'),(50,'investigate'),(55,'investigate'),(56,'likely_meets')]:
            with self.subTest(count=count):
                self.check(expected, direction='minimum', qualifier='approximate', value=count)

    def test_maximum_boundaries(self):
        for count, expected in [(44,'likely_meets'),(45,'investigate'),(50,'investigate'),(55,'investigate'),(56,'does_not_meet')]:
            with self.subTest(count=count):
                self.check(expected, direction='maximum', qualifier='approximate', value=count)

    def test_exact_has_no_leeway(self):
        for count in (44,45,48,50,52,55,56):
            for direction in ('minimum','maximum'):
                meets = count >= 50 if direction == 'minimum' else count <= 50
                self.check('meets' if meets else 'does_not_meet', direction=direction,qualifier='exact',value=count)

    def test_explicit_ranges(self):
        self.check('likely_meets',direction='minimum',qualifier='range',lower=60,upper=80)
        self.check('does_not_meet',direction='minimum',qualifier='range',lower=45,upper=49)
        self.check('investigate',direction='minimum',qualifier='range',lower=45,upper=60)
        self.check('likely_meets',direction='maximum',qualifier='range',lower=45,upper=50)

    def test_one_sided_bounds(self):
        self.check('investigate',direction='minimum',qualifier='up_to',upper=72)
        self.check('likely_meets',direction='maximum',qualifier='up_to',upper=50)
        self.check('likely_meets',direction='minimum',qualifier='at_least',lower=50)
        self.check('investigate',direction='maximum',qualifier='at_least',lower=45)

    def test_unknown_and_unsupported(self):
        for value in (None,-1,float('nan'),float('inf')):
            self.check('unknown',direction='minimum',qualifier='approximate',value=value)
        self.assertEqual(assess(threshold=50,direction='minimum',qualifier='approximate',value=72),'unknown')

    def test_zero_and_fractional_thresholds(self):
        self.assertEqual(assess(threshold=0,direction='maximum',qualifier='approximate',qualified=True,value=0),'investigate')
        self.assertEqual(assess(threshold=0,direction='maximum',qualifier='exact',qualified=True,value=0),'meets')
        self.assertEqual(assess(threshold=55,direction='minimum',qualifier='approximate',qualified=True,value='49.5'),'investigate')
        self.assertEqual(assess(threshold=55,direction='minimum',qualifier='approximate',qualified=True,value='60.5'),'investigate')

    def test_no_silent_bound_discard(self):
        with self.assertRaises(ValueError):
            assess(threshold=50,direction='minimum',qualifier='approximate',qualified=True,value=72,lower=40)

    def test_invalid_request(self):
        for threshold,direction in [(-1,'minimum'),(float('nan'),'minimum'),(50,'other')]:
            with self.assertRaises(ValueError):
                assess(threshold=threshold,direction=direction,qualifier='exact',qualified=True,value=72)


class ScopedCountContractTests(unittest.TestCase):
    """Count-first discovery preserves source bounds; no inferred consensus."""

    def claim(self, **changes):
        from app.policy.ah_assessment import AHClaim
        fields = dict(qualifier='at_least', lower=70, state='estimated',
                      application_reference='APP/1', scope_type='whole_site',
                      scope_label='Whole scheme', document_id='source-1',
                      document_date='2024-10-23', passage='At least 70 affordable homes')
        fields.update(changes)
        return AHClaim(**fields)

    def test_supported_lower_bound_is_useful_without_invented_ceiling(self):
        from app.policy.ah_assessment import AHAssessment
        a = AHAssessment(count=self.claim())
        self.assertEqual(a.search(minimum=70), 'likely_meets')
        self.assertEqual(a.search(minimum=71), 'investigate')
        self.assertEqual(a.search(maximum=100), 'investigate')
        self.assertEqual(a.search(maximum=69), 'does_not_meet')
        self.assertIn('at least 70 affordable homes', a.label())
        self.assertEqual(a.columns()['AH Lower Bound'], 70)
        self.assertIsNone(a.columns()['AH Reported Count'])
        self.assertIsNone(a.columns()['AH Upper Bound'])

    def test_explicit_range_preserves_both_source_boundaries(self):
        from app.policy.ah_assessment import AHAssessment
        a = AHAssessment(count=self.claim(qualifier='range', lower=71, upper=74,
                                          passage='Between 71 and 74 affordable homes'))
        self.assertEqual(a.search(minimum=70, maximum=74), 'likely_meets')
        self.assertEqual(a.search(minimum=72), 'investigate')
        self.assertEqual(a.search(maximum=73), 'investigate')
        self.assertIn('71–74 affordable homes', a.label())

    def test_conflicting_claims_are_not_rounded_into_a_new_source_bound(self):
        from app.policy.ah_assessment import AHAssessment
        claims = tuple(self.claim(qualifier='exact', value=n, lower=None,
                                  state='verified', passage=f'{n} affordable homes',
                                  document_id=f'doc-{n}') for n in (71, 73, 74))
        a = AHAssessment(alternatives=claims)
        before = a.payload()
        self.assertEqual(a.search(minimum=70), 'investigate')
        self.assertEqual(a.search(maximum=74), 'investigate')
        self.assertIsNone(a.columns()['AH Lower Bound'])
        self.assertEqual(a.payload(), before)
        for n in (71, 73, 74):
            self.assertIn(str(n), a.label())

    def test_scope_separation_and_component_minimum_not_whole_scheme_maximum(self):
        from app.policy.ah_assessment import AHAssessment
        c = self.claim(qualifier='exact', value=72, lower=None, state='verified',
                       scope_type='component', scope_label='Retirement apartments')
        self.assertEqual(AHAssessment(count=c).search(minimum=70), 'meets')
        self.assertEqual(AHAssessment(count=c).search(maximum=75), 'investigate')
        other = self.claim(application_reference='OTHER/2', lower=147)
        self.assertEqual(AHAssessment(alternatives=(c, other)).search(minimum=70), 'investigate')

    def test_unverified_bound_is_visible_but_never_qualified(self):
        from app.policy.ah_assessment import AHAssessment
        a = AHAssessment(count=self.claim(document_id=None, passage=None))
        self.assertIn('at least 70', a.label())
        self.assertIn('reported; source and scope unverified', a.label())
        self.assertEqual(a.search(minimum=70), 'unknown')
        self.assertEqual(a.search(maximum=100), 'unknown')
        self.assertIn('source link unavailable', ' '.join(a.evidence_notes()))

    def test_source_document_identity_is_not_a_source_link_or_legal_verification(self):
        from app.policy.ah_assessment import AHAssessment
        a = AHAssessment(count=self.claim(stage='legally_secured'))
        self.assertIn('document source-1; source link unavailable', ' '.join(a.evidence_notes()))
        self.assertIn('Reported AH status: legally secured; operative terms unverified', a.label())
        b = AHAssessment(count=self.claim(source_url='https://example.test/source.pdf', stage='legally_secured'))
        self.assertIn('https://example.test/source.pdf', ' '.join(b.evidence_notes()))
        self.assertIn('operative terms unverified', b.label())


if __name__ == '__main__':
    unittest.main()
