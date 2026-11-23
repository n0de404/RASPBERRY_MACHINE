import os
import sys
import unittest
from unittest.mock import Mock, patch


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLIENT_DIR = os.path.join(ROOT, "client")
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

import client as production_client


class FinishJobExcessWorkflowTests(unittest.TestCase):
    @staticmethod
    def _client():
        ui = production_client.ClientUI.__new__(production_client.ClientUI)
        ui.state = production_client.ClientState()
        ui.client_config = {"client_id": "RPI-CLIENT-008"}
        return ui

    def test_combined_totals_include_only_approved_shifts_after_last_finish_job(self):
        ui = self._client()
        current = {
            "machine_code": "M00008",
            "job_code": "122648",
            "client_id": "RPI-CLIENT-008",
            "pack_count": 2,
            "good_total": 150,
            "butal_total": 5,
            "reject_total": 3,
        }
        shifts = [
            {
                "machine_code": "M00008", "job_code": "122648",
                "client_id": "RPI-CLIENT-008", "review_status": "APPROVED",
                "finished_at_utc": "2026-11-20T09:00:00+00:00",
                "pack_count": 1, "good_total": 75, "butal_total": 2, "reject_total": 1,
            },
            {
                "machine_code": "M00008", "job_code": "122648",
                "client_id": "RPI-CLIENT-019", "review_status": "APPROVED",
                "finished_at_utc": "2026-11-21T09:00:00+00:00",
                "pack_count": 3, "good_total": 225, "butal_total": 4, "reject_total": 2,
            },
            {
                "machine_code": "M00008", "job_code": "122648",
                "client_id": "RPI-CLIENT-008", "review_status": "PENDING_SUPERVISOR",
                "finished_at_utc": "2026-11-21T10:00:00+00:00",
                "pack_count": 99, "good_total": 999,
            },
        ]
        finals = [{
            "machine_code": "M00008", "job_code": "122648",
            "finished_at_utc": "2026-11-20T12:00:00+00:00",
        }]

        with patch.object(production_client, "_load_finish_shift_json", return_value=shifts), patch.object(
            production_client, "_load_finished_jobs_json", return_value=finals
        ):
            totals = ui._finish_job_combined_totals(current)

        self.assertEqual(totals["shift_count"], 2)
        self.assertEqual(totals["pack_count"], 5)
        self.assertEqual(totals["good_total"], 375)
        self.assertEqual(totals["butal_total"], 9)
        self.assertEqual(totals["reject_total"], 5)
        self.assertEqual(totals["total_good"], 384)

    def test_actual_excess_is_saved_as_optional_print_override(self):
        ui = self._client()
        ui._pending_finish_excess_rows = [{
            "sku": "PART-A", "expected_qty": 12.5, "actual_qty": None,
            "difference_qty": None, "status": "PENDING", "input": "12.5",
        }]
        ui._pending_finish_excess_index = 0
        ui._pending_finish_excess_input = ""
        ui._pending_finish_excess_ready_to_print = False
        ui._render_finish_job_excess_review = Mock()
        ui._hide_invalid_overlay = Mock()

        self.assertTrue(ui._commit_finish_job_excess_input())
        row = ui._pending_finish_excess_rows[0]
        self.assertEqual(row["actual_qty"], 12.5)
        self.assertEqual(row["difference_qty"], 0)
        self.assertEqual(row["status"], "ACTUAL SAVED")
        self.assertEqual(row["print_qty"], 12.5)
        self.assertTrue(ui._pending_finish_excess_ready_to_print)

    def test_mismatch_is_saved_without_requiring_a_reason(self):
        ui = self._client()
        ui._pending_finish_excess_payload = {"job_code": "122648"}
        ui._pending_finish_excess_rows = [{
            "sku": "PART-A", "expected_qty": 12.5, "actual_qty": None,
            "difference_qty": None, "status": "PENDING", "input": "10",
        }]
        ui._pending_finish_excess_index = 0
        ui._pending_finish_excess_input = ""
        ui._pending_finish_excess_ready_to_print = False
        ui._finish_review_page_index = 1
        ui._render_finish_job_excess_review = Mock()
        ui._hide_invalid_overlay = Mock()

        self.assertTrue(ui._commit_finish_job_excess_input())
        row = ui._pending_finish_excess_rows[0]
        self.assertEqual(row["status"], "ACTUAL SAVED")
        self.assertEqual(row["difference_qty"], -2.5)
        self.assertEqual(row["print_qty"], 10)
        self.assertTrue(ui._pending_finish_excess_ready_to_print)

    def test_actual_excess_rounds_half_up_to_two_decimals(self):
        ui = self._client()
        row = {
            "sku": "PART-A", "expected_qty": 10, "actual_qty": None,
            "difference_qty": None, "status": "PENDING", "input": "12.345",
        }

        self.assertTrue(ui._apply_finish_inventory_actual_input(row))

        self.assertEqual(row["actual_qty"], 12.35)
        self.assertEqual(row["difference_qty"], 2.35)
        self.assertEqual(row["print_qty"], 12.35)

    def test_custom_01_adds_decimal_to_optional_actual_count(self):
        ui = self._client()
        ui._pending_finish_excess_payload = {"job_code": "122648"}
        ui._pending_finish_excess_rows = [{
            "sku": "PART-A", "expected_qty": 12.5, "actual_qty": None,
            "difference_qty": None, "print_qty": 12.5,
            "status": "USES EXPECTED", "input": "",
        }]
        ui._pending_finish_excess_index = 0
        ui._pending_finish_excess_input = ""
        ui._pending_finish_excess_ready_to_print = True
        ui._render_finish_job_excess_review = Mock()

        self.assertTrue(ui._handle_finish_job_excess_scan("num_1"))
        self.assertTrue(ui._handle_finish_job_excess_scan("Custom 01"))
        self.assertTrue(ui._handle_finish_job_excess_scan("num_2"))

        row = ui._pending_finish_excess_rows[0]
        self.assertEqual(row["input"], "1.2")
        self.assertEqual(row["actual_qty"], 1.2)
        self.assertEqual(row["print_qty"], 1.2)
        self.assertEqual(row["difference_qty"], -11.3)

    def test_butal_is_first_row_in_unified_return_inventory(self):
        ui = self._client()
        ui._pending_finish_excess_payload = {
            "job_combined_totals": {"butal_total": 18},
            "product_id": "3480",
            "product_sku": "MUG-ORD-GRN-9532",
            "product_name": "Mug - Ordinary Green",
        }
        ui._job_part_rows = Mock(return_value=[])
        ui._current_part_availability_statuses = Mock(return_value=[])

        rows = ui._finish_job_excess_rows()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["return_type"], "BUTAL PACK")
        self.assertEqual(rows[0]["sku"], "MUG-ORD-GRN-9532")
        self.assertEqual(rows[0]["expected_qty"], 18)
        self.assertEqual(rows[0]["print_qty"], 18)
        self.assertIsNone(rows[0]["actual_qty"])

    def test_blank_actual_prints_and_saves_expected_balance(self):
        ui = self._client()
        ui.state.machine_code = "M00008"
        ui.state.job_code = "122648"
        ui.state.production_session_id = "PS-TEST-EXPECTED"
        ui.state.reprint_qr_logs = []
        ui._pending_finish_excess_payload = {"job_code": "122648", "butal_total": 0}
        ui._pending_finish_excess_linked_payloads = []
        ui._pending_finish_excess_hidden_payloads = []
        ui._pending_finish_excess_rows = [{
            "identity": "8335", "return_type": "PRODUCT PART",
            "product_id": "8335", "sku": "Z-RM-TEST", "name": "Test Resin",
            "unit": "kg", "expected_qty": 8.555, "actual_qty": None,
            "difference_qty": None, "print_qty": 8.555,
            "status": "USES EXPECTED", "input": "", "part": {"part_product_id": "8335"},
        }]
        ui.finishInventoryInstruction = Mock()
        ui.status = Mock()
        ui._submit_pack_qr_print = Mock(return_value=True)
        ui._show_final_job_review_overlay = Mock()

        self.assertTrue(ui._print_finish_job_excess_and_continue())
        printable = ui._submit_pack_qr_print.call_args.args[0]
        self.assertEqual(printable["quantity"], 8.56)
        self.assertIn("Q00000008.56", printable["payload"])
        final_payload = ui._show_final_job_review_overlay.call_args.args[0]
        saved = final_payload["return_inventory_logs"][0]
        self.assertEqual(saved["expected_balance_qty"], 8.56)
        self.assertIsNone(saved["actual_count_qty"])
        self.assertEqual(saved["printed_quantity"], 8.56)
        self.assertEqual(saved["quantity_source"], "EXPECTED_BALANCE")

    def test_incomplete_custom_decimal_blocks_print(self):
        ui = self._client()
        ui._pending_finish_excess_payload = {"job_code": "122648"}
        ui._pending_finish_excess_rows = [{
            "identity": "8335", "return_type": "PRODUCT PART",
            "product_id": "8335", "sku": "Z-RM-TEST", "unit": "kg",
            "expected_qty": 8.5, "actual_qty": 1, "difference_qty": -7.5,
            "print_qty": 1, "status": "ACTUAL SAVED", "input": "1.",
            "part": {"part_product_id": "8335"},
        }]
        ui._pending_finish_excess_index = 0
        ui._render_finish_job_excess_review = Mock()
        ui._show_invalid_overlay = Mock()

        self.assertFalse(ui._print_finish_job_excess_and_continue())
        ui._show_invalid_overlay.assert_called_once()

    def test_excess_label_uses_verified_quantity_and_stable_print_key(self):
        ui = self._client()
        ui.state.machine_code = "M00008"
        ui.state.job_code = "122648"
        ui.state.production_session_id = "PS-TEST-123"
        row = {
            "identity": "8335",
            "product_id": "8335",
            "sku": "Z-RM-TEST",
            "name": "Test Resin",
            "actual_qty": 12.5,
            "part": {"part_product_id": "8335"},
        }

        first = ui._build_product_part_excess_print(row)
        second = ui._build_product_part_excess_print(row)

        self.assertIsNotNone(first)
        self.assertIn("Q00000012.50", first["payload"])
        self.assertEqual(first["quantity"], 12.5)
        self.assertEqual(first["idempotency_key"], second["idempotency_key"])

    def test_successful_excess_print_opens_existing_supervisor_review(self):
        ui = self._client()
        ui.state.machine_code = "M00008"
        ui.state.job_code = "122648"
        ui.state.production_session_id = "PS-TEST-123"
        ui.state.reprint_qr_logs = []
        ui._pending_finish_excess_payload = {"job_code": "122648", "butal_total": 0}
        ui._pending_finish_excess_linked_payloads = []
        ui._pending_finish_excess_hidden_payloads = []
        ui._pending_finish_excess_rows = [{
            "identity": "8335", "product_id": "8335", "sku": "Z-RM-TEST",
            "name": "Test Resin", "unit": "kg", "expected_qty": 10,
            "actual_qty": 12.5, "difference_qty": 2.5, "status": "OVER",
            "print_qty": 12.5, "input": "12.5",
            "verified_at_utc": "2026-11-21T01:00:00+00:00",
            "part": {"part_product_id": "8335"},
        }]
        ui._pending_finish_excess_index = 0
        ui._pending_finish_excess_input = ""
        ui._pending_finish_excess_ready_to_print = True
        ui.finishInventoryInstruction = Mock()
        ui.finishStatus = Mock()
        ui.status = Mock()
        ui._submit_pack_qr_print = Mock(return_value=True)
        ui._show_final_job_review_overlay = Mock()

        self.assertTrue(ui._print_finish_job_excess_and_continue())
        final_payload = ui._show_final_job_review_overlay.call_args.args[0]
        self.assertEqual(final_payload["product_part_excess_logs"][0]["actual_excess_qty"], 12.5)
        self.assertEqual(final_payload["return_inventory_logs"][0]["printed_quantity"], 12.5)
        self.assertIn("excess_verification_completed_at_utc", final_payload)
        ui._show_final_job_review_overlay.assert_called_once()


if __name__ == "__main__":
    unittest.main()
