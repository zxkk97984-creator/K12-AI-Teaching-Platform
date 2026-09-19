from __future__ import annotations

import unittest

from validate_plan import derive_stage, resolve_stage


class StageBoundaryTests(unittest.TestCase):
    def test_boundaries(self):
        expected = {1: "PRIMARY_LOWER", 3: "PRIMARY_LOWER", 4: "PRIMARY_UPPER", 6: "PRIMARY_UPPER", 7: "JUNIOR", 9: "JUNIOR", 10: "SENIOR", 12: "SENIOR"}
        for grade, stage in expected.items():
            with self.subTest(grade=grade):
                self.assertEqual(derive_stage(grade), stage)

    def test_invalid(self):
        for bad in (0, 13, "6", True, None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                derive_stage(bad)  # type: ignore[arg-type]

    def test_stage_only_keeps_grade_unknown(self):
        self.assertEqual(resolve_stage(None, "JUNIOR"), ("JUNIOR", None))

    def test_conflict(self):
        with self.assertRaises(ValueError):
            resolve_stage(7, "SENIOR")


if __name__ == "__main__":
    unittest.main()
