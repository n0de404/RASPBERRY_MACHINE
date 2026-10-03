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


class TestMachineMappingTests(unittest.TestCase):
    def test_test_machine_qr_uses_isolated_machine_identity(self):
        result = parse_scan("testmachine~1")

        self.assertIsNotNone(result)
        self.assertEqual(result.kind, "MACHINE")
        self.assertEqual(result.value, "TEST MACHINE")
        self.assertEqual(result.meta.get("machine_code"), "TEST-MACHINE")
        self.assertTrue(result.meta.get("test_machine"))

    def test_test_pack_qr_supports_configurable_quantity(self):
        result = parse_scan("testpack~24")

        self.assertIsNotNone(result)
        self.assertEqual(result.kind, "PACK")
        self.assertEqual(result.qty, 24.0)


if __name__ == "__main__":
    unittest.main()
