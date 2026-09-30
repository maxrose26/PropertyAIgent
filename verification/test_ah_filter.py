"""Run independently: python -m unittest verification.test_ah_filter -v.

No pytest/conftest/database or external services. Tests actual pandas masks.
"""
import unittest
import pandas as pd
from app.ui.housing_type import explicit_affordable_maximum_mask


class AHMaximumFilterTests(unittest.TestCase):
    def test_unknown_is_not_zero(self):
        for dtype in ('float64', 'Float64'):
            with self.subTest(dtype=dtype):
                counts = pd.Series([None, 0, 1, 10], dtype=dtype)
                self.assertEqual(explicit_affordable_maximum_mask(counts, 0).tolist(),
                                 [False, True, False, False])
                self.assertEqual(explicit_affordable_maximum_mask(counts, 5).tolist(),
                                 [False, True, True, False])


if __name__ == '__main__':
    unittest.main()
