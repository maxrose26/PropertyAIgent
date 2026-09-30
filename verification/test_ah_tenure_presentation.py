"""Offline presentation regression: execute the actual renderer with a recording UI.

Only the function AST is loaded to avoid application/database startup imports.
This tests displayed wording, not ORM assembly or browser rendering.
"""
import ast
from pathlib import Path
import unittest

class TenurePresentationTests(unittest.TestCase):
    def render(self, categories, known=False):
        source = Path(__file__).resolve().parents[1] / "app/ui/site_profile_view.py"
        tree = ast.parse(source.read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_affordable_tenure_section")
        messages = []
        class UI:
            caption = staticmethod(messages.append)
            info = staticmethod(messages.append)
            markdown = staticmethod(messages.append)
        namespace = {"st": UI, "section_header": lambda *a, **k: None}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), "exec"), namespace)
        namespace[fn.name]({"categories": categories, "has_categories": bool(categories), "affordable_known_tenure_unknown": known})
        return messages

    def test_current_application_does_not_borrow_older_tenure(self):
        from types import SimpleNamespace
        from app.policy.ah_assessment import AHAssessment, AHClaim
        from app.reporting.residential_mix import build_affordable_tenure
        older = SimpleNamespace(affordable_tenure_split_final="Social rent")
        current = AHAssessment(count=AHClaim(application_reference="DC/098428"))
        result = build_affordable_tenure(older, {"state": "unverified"}, current)
        self.assertEqual(result["categories"], [])

    def test_unknown_provision_is_unresolved_not_not_applicable(self):
        self.assertEqual(self.render([]), ["Affordable tenure not identified; affordable housing provision remains unresolved."])

    def test_known_provision_missing_tenure_stays_unknown(self):
        self.assertEqual(self.render([], True), ["Affordable tenure not identified"])

    def test_evidenced_categories_are_preserved(self):
        self.assertEqual(self.render(["Older Persons Shared Ownership"]), ["Reported tenure evidence; current approved terms and application scope require verification.", "- Older Persons Shared Ownership"])

if __name__ == "__main__":
    unittest.main()
