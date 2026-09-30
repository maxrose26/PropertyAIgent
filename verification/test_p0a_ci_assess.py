"""Offline assessment-parser tests; these are not integration evidence."""
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
from p0a_ci_assess import assess, EXPECTED, MESSAGE, REQUIRED

class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        base = {f'tests.fixture.test_{i}' for i in range(282)}
        candidate = base | {f'tests.integration.{n}' for n in REQUIRED}
        candidate |= {f'tests.integration.test_independent_watchdog_bounds_blocked_persistence[{i}]' for i in range(5)}
        candidate.add('tests.test_daily_discovery_portal_resilience.test_no_run_health_line_is_partial_with_process_failure')
        candidate |= {f'tests.candidate.test_{i}' for i in range(60)}
        for name, passed in [('candidate', candidate), ('baseline', base)]:
            root = ET.Element('testsuite')
            for key in sorted(passed | EXPECTED):
                module, test = key.rsplit('.', 1)
                case = ET.SubElement(root, 'testcase', classname=module, name=test)
                if key in EXPECTED: ET.SubElement(case, 'failure', message=MESSAGE)
            ET.ElementTree(root).write(self.folder / f'{name}.xml')
            (self.folder / f'{name}.log').write_text('1 deselected')

    def mutate(self, action):
        p = self.folder / 'candidate.xml'
        tree = ET.parse(p)
        action(tree.getroot())
        tree.write(p)

    def test_accepted_exceptions_remain_explicit(self):
        self.assertEqual(assess(self.folder)['failed_each'], 4)

    def test_missing_xml_rejected(self):
        (self.folder / 'baseline.xml').unlink()
        with self.assertRaises(OSError): assess(self.folder)

    def test_new_failure_rejected(self):
        self.mutate(lambda r: ET.SubElement(r[0], 'failure', message='new defect'))
        with self.assertRaises(ValueError): assess(self.folder)

    def test_integration_skip_rejected(self):
        self.mutate(lambda r: ET.SubElement(next(c for c in r if c.get('name') in REQUIRED), 'skipped'))
        with self.assertRaises(ValueError): assess(self.folder)

    def test_changed_known_failure_rejected(self):
        self.mutate(lambda r: next(r.iter('failure')).set('message', 'different defect'))
        with self.assertRaises(ValueError): assess(self.folder)

    def test_missing_integration_rejected(self):
        self.mutate(lambda r: r.remove(next(c for c in r if c.get('name') in REQUIRED)))
        with self.assertRaises(ValueError): assess(self.folder)

    def test_deselection_must_be_reported(self):
        (self.folder / 'candidate.log').write_text('')
        with self.assertRaises(ValueError): assess(self.folder)

if __name__ == '__main__': unittest.main()
