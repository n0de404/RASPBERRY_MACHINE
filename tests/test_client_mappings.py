import sys
import unittest
from pathlib import Path


CLIENT_DIR = Path(__file__).resolve().parents[1] / "client"
sys.path.insert(0, str(CLIENT_DIR))

from mappings import parse_scan


class SupervisorReviewMappingTests(unittest.TestCase):
    def test_supervisor_review_qr_is_recognized(self):
        result = parse_scan("svisorreview~1")

        self.assertIsNotNone(result)
        self.assertEqual(result.kind, "SUPERVISOR_REVIEW_TRIGGER")
        self.assertEqual(result.value, "Open Supervisor Review")

    def test_supervisor_review_qr_is_case_insensitive(self):
        result = parse_scan("SVISORREVIEW~1")

        self.assertIsNotNone(result)
        self.assertEqual(result.kind, "SUPERVISOR_REVIEW_TRIGGER")


if __name__ == "__main__":
    unittest.main()
