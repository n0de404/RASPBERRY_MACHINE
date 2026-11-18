import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock


CLIENT_DIR = Path(__file__).resolve().parents[1] / "client"
sys.path.insert(0, str(CLIENT_DIR))

from mappings import (
    DEFAULT_QR_MAPPING_CONFIG,
    apply_qr_mapping_config,
    numeric_context_mapping,
    parse_scan,
    qr_mapping_config_from_text,
    qr_mapping_config_to_text,
    resolve_mapped_scan,
    validate_qr_mapping_config,
)
from client import ClientUI


class QrMappingConfigurationTests(unittest.TestCase):
    def tearDown(self):
        apply_qr_mapping_config(deepcopy(DEFAULT_QR_MAPPING_CONFIG))

    def test_defaults_are_valid(self):
        ok, errors = validate_qr_mapping_config(deepcopy(DEFAULT_QR_MAPPING_CONFIG))
        self.assertTrue(ok, errors)

    def test_custom_command_alias_uses_existing_workflow(self):
        config = deepcopy(DEFAULT_QR_MAPPING_CONFIG)
        linkage = next(row for row in config["commands"] if row["id"] == "job_linkage")
        linkage["aliases"] = ["my-new-linkage-qr"]

        ok, errors = apply_qr_mapping_config(config)
        self.assertTrue(ok, errors)
        self.assertEqual(resolve_mapped_scan("my-new-linkage-qr"), "joblinkage")
        self.assertEqual(parse_scan("my-new-linkage-qr").kind, "JOB_LINKAGE_TRIGGER")
        self.assertIsNone(resolve_mapped_scan("joblinkage~1"))

    def test_duplicate_command_alias_is_rejected(self):
        config = deepcopy(DEFAULT_QR_MAPPING_CONFIG)
        config["commands"][1]["aliases"] = [config["commands"][0]["aliases"][0]]

        ok, errors = validate_qr_mapping_config(config)
        self.assertFalse(ok)
        self.assertTrue(any("Duplicate command alias" in error for error in errors))

    def test_numeric_context_can_be_reassigned(self):
        config = deepcopy(DEFAULT_QR_MAPPING_CONFIG)
        config["reject_reasons"][0]["number"] = 0
        ok, errors = apply_qr_mapping_config(config)

        self.assertTrue(ok, errors)
        mapping = numeric_context_mapping("reject")
        self.assertEqual(mapping[0]["code"], "BM")
        self.assertNotIn(1, mapping)

    def test_retired_commands_are_not_scannable(self):
        for raw in (
            "joblinkageremove~1",
            "prepacklinkage~1",
            "pdrdone",
            "pdrcancel",
            "butalpack~1",
        ):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_scan(raw))

    def test_pdrstart_is_the_single_pdr_start_mapping(self):
        row = next(row for row in DEFAULT_QR_MAPPING_CONFIG["commands"] if row["id"] == "pdrstart")
        self.assertEqual(row["aliases"], ["pdrstart"])
        self.assertEqual(parse_scan("pdrstart").kind, "PRODUCTION_DAILY_REPORT_TRIGGER")

    def test_finish_shift_uses_finishshift_as_its_canonical_payload(self):
        row = next(row for row in DEFAULT_QR_MAPPING_CONFIG["commands"] if row["id"] == "operator_shift")

        self.assertEqual(row["handler_token"], "finishshift")
        self.assertEqual(row["aliases"][0], "finishshift")
        self.assertEqual(resolve_mapped_scan("finishshift"), "finishshift")
        self.assertEqual(parse_scan("finishshift").kind, "OPERATOR_SHIFT_TRIGGER")

    def test_custom_finish_shift_mapping_uses_existing_workflow(self):
        config = deepcopy(DEFAULT_QR_MAPPING_CONFIG)
        row = next(row for row in config["commands"] if row["id"] == "operator_shift")
        row["aliases"] = ["end-my-shift"]

        ok, errors = apply_qr_mapping_config(config)

        self.assertTrue(ok, errors)
        self.assertEqual(resolve_mapped_scan("end-my-shift"), "finishshift")
        self.assertEqual(parse_scan("end-my-shift").kind, "OPERATOR_SHIFT_TRIGGER")
        self.assertIsNone(resolve_mapped_scan("operatorshift~1"))

    def test_no_shot_has_direct_and_numeric_mappings(self):
        row = next(row for row in DEFAULT_QR_MAPPING_CONFIG["commands"] if row["id"] == "no_shot")
        self.assertEqual(row["aliases"], ["NO"])
        self.assertEqual(parse_scan("NO").kind, "REJECT_REASON")
        self.assertEqual(parse_scan("NO").value, "NO")
        self.assertEqual(numeric_context_mapping("reject")[9]["code"], "NO")

    def test_reject_modal_lists_configured_numbered_choices(self):
        client = ClientUI.__new__(ClientUI)
        client._show_choice_cards_overlay = Mock()

        ClientUI._show_reject_reason_choices_overlay(client)

        args, kwargs = client._show_choice_cards_overlay.call_args
        self.assertEqual(args[0], "SELECT REJECT DETAIL")
        self.assertEqual(args[1][0]["number"], 1)
        self.assertEqual(args[1][0]["name"], "BURN MARK")
        self.assertEqual(args[1][1]["number"], 2)
        self.assertEqual(args[1][1]["name"], "COLOR STREAK")
        self.assertTrue(kwargs["compact"])

    def test_text_editor_uses_one_name_payload_pair_per_row(self):
        text = qr_mapping_config_to_text(DEFAULT_QR_MAPPING_CONFIG)

        self.assertIn("[COMMANDS]", text)
        self.assertIn("Finish Job = finishjob", text)
        self.assertIn("num_1 | BURN MARK = BM", text)
        self.assertIn("num_1 | Machine Issue/Breakdown/Repair = 01", text)
        self.assertNotIn('"commands"', text)

    def test_text_editor_updates_command_reject_and_pdr_payloads(self):
        text = qr_mapping_config_to_text(DEFAULT_QR_MAPPING_CONFIG)
        text = text.replace("Finish Job = finishjob", "Finish Job = finish-now")
        text = text.replace("num_1 | BURN MARK = BM", "num_1 | BURN MARK = reject-burn")
        text = text.replace(
            "num_1 | Machine Issue/Breakdown/Repair = 01",
            "num_1 | Machine Issue/Breakdown/Repair = pdr-machine",
        )

        config, errors = qr_mapping_config_from_text(text, DEFAULT_QR_MAPPING_CONFIG)

        self.assertFalse(errors)
        self.assertIsNotNone(config)
        finish = next(row for row in config["commands"] if row["id"] == "finish_job")
        self.assertEqual(finish["aliases"], ["finish-now"])
        self.assertEqual(config["reject_reasons"][0]["aliases"], ["reject-burn"])
        self.assertEqual(config["reject_reasons"][0]["code"], "BM")
        self.assertEqual(config["pdr_reasons"][0]["aliases"], ["pdr-machine"])

        ok, apply_errors = apply_qr_mapping_config(config)
        self.assertTrue(ok, apply_errors)
        self.assertEqual(resolve_mapped_scan("finish-now"), "finishjob")
        self.assertEqual(parse_scan("reject-burn").value, "BM")


if __name__ == "__main__":
    unittest.main()
