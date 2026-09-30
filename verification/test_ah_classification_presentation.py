"""Execute the changed UI function offline; no DB, imports or paid calls.

The qualified record is a local acceptance input, not a production claim
import. Renderer dependencies are recording presentation doubles only.
"""
import ast
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import unittest

from app.policy.ah_assessment import AHAssessment, AHClaim, legacy_assessment


class ClassificationPresentationTests(unittest.TestCase):
    def render(self, assessment, reconciles=False, reported=None):
        path = Path(__file__).resolve().parents[1] / 'app/ui/site_profile_view.py'
        fn = next(n for n in ast.parse(path.read_text()).body
                  if isinstance(n, ast.FunctionDef) and n.name == '_affordable_housing_section')
        captions, writes, tiles = [], [], []
        scheme = SimpleNamespace(affordable_classification_confidence='high',
            affordable_data_status='all_units_affordable',
            affordable_classification_evidence='72 retirement apartments plus ten private houses.',
            affordable_status_note=None)
        ui = SimpleNamespace(caption=captions.append, write=writes.append,
                             expander=lambda *a: nullcontext())
        ns = dict(st=ui, section_header=lambda *a, **k: None,
                  affordable_headline_tile=lambda *a: tiles.append(a),
                  status_badge=lambda *a: None)
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), 'exec'), ns)
        ns[fn.name](dict(scheme=scheme, affordable_assessment=assessment, reported_affordable_assessment=reported,
            affordable_headline={'percentage_is_calculated': False, 'affordable_units': 72},
            percentage_reconciliation={'percentage_reconciles': reconciles}))
        self.assertNotIn('all_units_affordable', ' '.join(captions))
        self.assertNotIn('confidence: high', ' '.join(captions))
        self.assertEqual(tiles[0][0]['affordable_units'], 72)
        self.assertEqual(scheme.affordable_data_status, 'all_units_affordable')
        self.assertFalse(any(isinstance(w, dict) for w in writes), 'Internal assessment must not reach buyer UI')
        return captions, writes

    def test_focus_exact_component_retains_minimum_and_source_scope(self):
        a = AHAssessment(count=AHClaim(value=72, qualifier='exact', state='verified',
            application_reference='DC/093884', scope_type='component',
            scope_label='Retirement apartments within the DC/085997 82-home scheme',
            stage='proposed', document_id='2378349', document_date='2024-10-23',
            passage='The retirement apartments are to be 100% affordable'),
            reported_percentage=100, percentage_review_reason='Component percentage is not whole-scheme percentage')
        before = a.payload()
        captions, writes = self.render(a)
        self.assertEqual(a.search(minimum=50), 'meets')
        self.assertEqual(a.count.threshold(73, 'minimum', whole_scheme=False), 'does_not_meet')
        self.assertIn('exact, verified', ' '.join(captions))
        self.assertIn('DC/093884', ' '.join(captions))
        self.assertIn('proposed', ' '.join(captions))
        self.assertIn('classification requires source and scope review', ' '.join(captions))
        # Same public projection consumed by Explore and selected CSV.
        self.assertEqual(a.columns()['AH Scope Type'], 'component')
        self.assertTrue(a.columns()['AH Qualified'])
        self.assertEqual(a.payload(), before)

    def test_unlinked_legacy_count_is_not_silently_qualified(self):
        a = legacy_assessment(fields={'affordable_units_final':72, 'affordable_percentage_final':100})
        captions, _ = self.render(a)
        self.assertIn('reported; source and scope unverified', ' '.join(captions))
        self.assertEqual(a.search(minimum=50), 'unknown')

    def test_bare_application_report_is_visible_without_replacing_selected_unknown(self):
        selected = AHAssessment()
        reported = legacy_assessment(fields={'affordable_units_final':30}, application_reference='APP/2')
        captions, writes = self.render(selected, reported=reported)
        self.assertTrue(any('30' in c and 'APP/2' in c and 'reported; source and scope unverified' in c for c in captions))
        self.assertTrue(any('not an operative numeric match' in c for c in captions))
        self.assertIsNone(selected.columns()['AH Reported Count'])
        self.assertFalse(selected.columns()['AH Qualified'])

    def test_actual_focus_legacy_legal_stage_is_reported_not_verified(self):
        a = legacy_assessment(fields={'affordable_units_final': 72,
            'affordable_percentage_final': 100, 'affordable_housing_status': 'legally_secured'},
            application_reference='DC/085997')
        before = a.payload()
        captions, writes = self.render(a)
        self.assertIn('Reported stage: legally secured; operative terms unverified', a.label())
        self.assertIn('operative terms unverified', a.columns()['AH Stage'])
        self.assertIn('Final approved conditions and tenure terms require checking', ' '.join(captions))
        self.assertNotIn('legally_secured', ' '.join(captions))
        self.assertEqual(a.count.stage, 'legally_secured')
        self.assertEqual(a.payload(), before)
        self.assertEqual(a.columns()['AH Reported Count'], 72)
        self.assertFalse(a.count.qualified)
        self.assertEqual(a.search(minimum=50), 'unknown')
        self.assertEqual(a.search(maximum=100), 'unknown')

    def test_qualified_count_does_not_independently_verify_legal_stage(self):
        a = AHAssessment(count=AHClaim(value=72, qualifier='exact', state='verified',
            application_reference='DC/093884', scope_type='component', scope_label='Retirement',
            stage='legally_secured', document_id='statement', passage='72 affordable apartments'))
        self.assertTrue(a.count.qualified)
        self.assertIn('operative terms unverified', a.label())
        self.assertEqual(a.search(minimum=50), 'meets')

    def test_absent_assessment_fails_closed(self):
        captions, _ = self.render(None)
        self.assertEqual(captions, ['Whole-scheme affordable classification requires source and scope review.'])

    def test_component_is_not_whole_scheme_even_if_percentage_reconciles(self):
        a = AHAssessment(count=AHClaim(value=72, qualifier='exact', state='verified',
            application_reference='LOCAL/1', scope_type='component', scope_label='Retirement',
            stage='proposed', document_id='local', passage='72 affordable apartments'))
        captions, _ = self.render(a, reconciles=True)
        self.assertIn('classification requires source and scope review', ' '.join(captions))


if __name__ == '__main__':
    unittest.main()
