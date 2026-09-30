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


if __name__ == '__main__':
    unittest.main()
