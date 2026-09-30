"""Offline claim contract tests; no ORM, browser, network or production inputs."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from app.policy.ah_assessment import AHAssessment, AHClaim, TenureClaim, legacy_assessment


def claim(**changes):
    c = AHClaim(value=72, qualifier='approximate', state='estimated',
                application_reference='SYNTHETIC/1', scope_type='whole_site',
                scope_label='Whole scheme', stage='proposed', document_id='synthetic-1',
                source_url='https://example.invalid/evidence', document_date='2026-09-01',
                passage='Approximately 72 affordable homes proposed.')
    return replace(c, **changes)


class AssessmentTests(unittest.TestCase):
    def test_inclusive_band_in_both_directions(self):
        for x, minimum, maximum in ((44,'does_not_meet','likely_meets'),
                (45,'investigate','investigate'), (50,'investigate','investigate'),
                (55,'investigate','investigate'), (56,'likely_meets','does_not_meet')):
            with self.subTest(x=x):
                a = AHAssessment(count=claim(value=x))
                self.assertEqual(a.search(minimum=50), minimum)
                self.assertEqual(a.search(maximum=50), maximum)

    def test_exact_zero(self):
        a = AHAssessment(count=claim(value=0, qualifier='exact', state='verified'))
        self.assertEqual(a.search(maximum=0), 'meets')
        self.assertEqual(a.search(minimum=1), 'does_not_meet')

    def test_exact_does_not_get_leeway(self):
        for x in (44,45,50,55,56):
            a=AHAssessment(count=claim(value=x, qualifier='exact',state='verified'))
            self.assertEqual(a.search(minimum=50), 'meets' if x>=50 else 'does_not_meet')
            self.assertEqual(a.search(maximum=50), 'meets' if x<=50 else 'does_not_meet')

    def test_range_and_one_sided(self):
        a=AHAssessment(count=claim(value=None, qualifier='range', lower=60, upper=80))
        self.assertEqual(a.search(minimum=50), 'likely_meets')
        self.assertEqual(a.search(maximum=70), 'investigate')
        self.assertEqual(AHAssessment(count=claim(value=None,qualifier='up_to',upper=72)).search(minimum=50),'investigate')
        self.assertEqual(AHAssessment(count=claim(value=None,qualifier='at_least',lower=72)).search(maximum=50),'does_not_meet')

    def test_component_cannot_prove_whole_maximum(self):
        a=AHAssessment(count=claim(scope_type='component',scope_label='Retirement apartments'))
        self.assertEqual(a.search(minimum=50),'likely_meets')
        self.assertEqual(a.search(maximum=100),'investigate')
        self.assertEqual(a.search(maximum=100,whole_scheme=False),'likely_meets')

    def test_component_below_minimum_does_not_exclude_whole(self):
        a=AHAssessment(count=claim(value=10,scope_type='component',scope_label='Parcel A'))
        self.assertEqual(a.search(minimum=50),'investigate')

    def test_missing_source_is_unknown(self):
        for changes in ({'document_id':None,'source_url':None},{'passage':None},
                        {'application_reference':None},{'scope_label':None},{'scope_type':'unclear'}):
            with self.subTest(changes=changes):
                self.assertEqual(AHAssessment(count=claim(**changes)).search(minimum=50),'unknown')

    def test_legacy_value_never_becomes_estimate(self):
        a=legacy_assessment(SimpleNamespace(affordable_units_final=72,
            affordable_percentage_final=100, affordable_classification_evidence='72 retirement plus 10 market',
            affordable_tenure_split_final='OPSO', housing_confidence='high'),application_reference='SYNTHETIC/1')
        self.assertEqual(a.count.value,72)
        self.assertEqual(a.reported_percentage,100)
        self.assertEqual(a.reported_tenure,'OPSO')
        self.assertEqual(a.search(minimum=50),'unknown')
        self.assertIsNone(a.count.document_date)
        self.assertEqual(a.tenures,())

    def test_percentage_conflict_does_not_erase_supported_count(self):
        a=AHAssessment(count=claim(),reported_percentage=100,percentage_review_reason='72/82 conflicts')
        self.assertEqual(a.search(minimum=50),'likely_meets')
        self.assertEqual(a.payload()['reported_percentage'],100)

    def test_conflicting_alternatives_not_cherry_picked(self):
        a=AHAssessment(count=claim(state='conflicting'), alternatives=(claim(value=20),claim(value=80)))
        self.assertEqual(a.search(minimum=40, maximum=60),'does_not_meet')
        self.assertEqual(a.search(minimum=50),'investigate')
        b=replace(a,alternatives=(claim(value=20),claim(value=80,source_url=None,document_id=None)))
        self.assertEqual(b.search(minimum=40, maximum=60),'investigate')

    def test_unknown_not_zero_and_no_filter_retains_it(self):
        a=AHAssessment()
        self.assertEqual(a.search(minimum=0),'unknown')
        self.assertEqual(a.search(),'unfiltered')

    def test_invalid_bounds_fail_closed(self):
        for c in (claim(value=-1),claim(value=float('nan')),claim(lower=20),
                  claim(value=None,qualifier='range',lower=80,upper=60),
                  claim(qualifier='exact',state='estimated')):
            self.assertEqual(AHAssessment(count=c).search(minimum=50),'unknown')

    def test_projection_preserves_same_claim_without_derivation(self):
        a=AHAssessment(count=claim(),tenures=(TenureClaim('Social rent',claim(value=40)),),
                       reported_percentage=100,percentage_review_reason='Unresolved denominator')
        payload=a.payload(); cols=a.columns()
        self.assertEqual(payload['count']['value'],cols['AH Reported Count'])
        self.assertEqual(payload['count']['document_date'],cols['AH Document Date'])
        self.assertEqual(payload['count']['scope_label'],cols['AH Scope'])
        self.assertEqual(payload['tenures'][0]['claim']['value'],40)
        self.assertIn('estimated',a.label())
        self.assertNotIn('private_units',payload)

    def test_invalid_search(self):
        with self.assertRaises(ValueError):
            AHAssessment(count=claim()).search(60,50)

if __name__ == '__main__':
    unittest.main()
