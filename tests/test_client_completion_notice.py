import sys
import unittest
from pathlib import Path


CLIENT_DIR = Path(__file__).resolve().parents[1] / "client"
sys.path.insert(0, str(CLIENT_DIR))

from client import _completion_pack_projection


class CompletionPackProjectionTests(unittest.TestCase):
    def test_three_exact_packs_remain_after_scan(self):
        result = _completion_pack_projection(4000, 3925, 25)

        self.assertEqual(result["remaining_qty"], 75)
        self.assertEqual(result["packs_remaining"], 3)
        self.assertEqual(result["projected_total"], 4000)
        self.assertEqual(result["projected_overrun"], 0)

    def test_whole_pack_projection_allows_final_overrun(self):
        before_scan = _completion_pack_projection(4000, 3900, 30)
        after_scan = _completion_pack_projection(4000, 3930, 30)

        self.assertEqual(before_scan["packs_remaining"], 4)
        self.assertEqual(after_scan["packs_remaining"], 3)
        self.assertEqual(after_scan["projected_total"], 4020)
        self.assertEqual(after_scan["projected_overrun"], 20)

    def test_fulfilled_job_has_no_remaining_packs(self):
        result = _completion_pack_projection(4000, 4020, 30)

        self.assertEqual(result["remaining_qty"], 0)
        self.assertEqual(result["packs_remaining"], 0)
        self.assertEqual(result["projected_overrun"], 20)

    def test_missing_pack_quantity_cannot_make_projection(self):
        result = _completion_pack_projection(4000, 3900, 0)

        self.assertEqual(result["remaining_qty"], 100)
        self.assertEqual(result["packs_remaining"], 0)


if __name__ == "__main__":
    unittest.main()
