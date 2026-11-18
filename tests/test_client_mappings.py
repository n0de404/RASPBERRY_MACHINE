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


class ChangeOperatorMappingTests(unittest.TestCase):
    def test_change_operator_qr_is_recognized(self):
        result = parse_scan("changeoperator~1")

        self.assertIsNotNone(result)
        self.assertEqual(result.kind, "CHANGE_OPERATOR_TRIGGER")

    def test_change_operator_alias_is_case_insensitive(self):
        result = parse_scan("OPERATOR_CHANGE~1")

        self.assertIsNotNone(result)
        self.assertEqual(result.kind, "CHANGE_OPERATOR_TRIGGER")


class ColorMoldAndNumericStateMappingTests(unittest.TestCase):
    def test_combined_color_mold_qr_is_recognized(self):
        for raw in ("changecolormold", "changecolormold~1", "CHANGE_COLOR_MOLD~1"):
            with self.subTest(raw=raw):
                result = parse_scan(raw)
                self.assertIsNotNone(result)
                self.assertEqual(result.kind, "COLOR_CHANGE_TRIGGER")

    def test_plain_reject_void_and_butal_controls_follow_mapping_sheet(self):
        expected = {
            "finishshift": "OPERATOR_SHIFT_TRIGGER",
            "changeoperator": "CHANGE_OPERATOR_TRIGGER",
            "refreshjob": "JOB_API_REFRESH_TRIGGER",
            "changeworkorder": "CHANGE_WORK_ORDER_TRIGGER",
            "joblinkage": "JOB_LINKAGE_TRIGGER",
            "virtualpackqr": "VIRTUAL_PACK_QR_TRIGGER",
            "printqr": "PRINT_NEXT_PACK_QR_TRIGGER",
            "reject": "REJECT_TRIGGER",
            "void": "VOID_TRIGGER",
            "butal": "BUTAL",
            "startupreject": "STARTUP_REJECT",
            "pdrstart": "PRODUCTION_DAILY_REPORT_TRIGGER",
            "svisorreview": "SUPERVISOR_REVIEW_TRIGGER",
            "machinecounteroverwrite": "MACHINE_COUNTER_OVERWRITE_TRIGGER",
        }
        for raw, kind in expected.items():
            with self.subTest(raw=raw):
                result = parse_scan(raw)
                self.assertIsNotNone(result)
                self.assertEqual(result.kind, kind)

    def test_num_qr_is_not_globally_misclassified(self):
        # num_N is interpreted by the active client state, not globally by
        # parse_scan (reject, PDR, choice, and numeric-input states differ).
        self.assertIsNone(parse_scan("num_0"))
        self.assertIsNone(parse_scan("num_22"))

if __name__ == "__main__":
    unittest.main()
