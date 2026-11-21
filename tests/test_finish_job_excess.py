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
                "client_id": "RPI-CLIENT-008", "review_status": "APPROVED",
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

    def test_actual_excess_records_match_and_difference(self):
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
        self.assertEqual(row["status"], "MATCH")
        self.assertTrue(ui._pending_finish_excess_ready_to_print)

    def test_mismatch_requires_reason_before_print_is_ready(self):
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
        self.assertEqual(row["status"], "REASON REQUIRED")
        self.assertTrue(row["reason_required"])
        self.assertFalse(ui._pending_finish_excess_ready_to_print)

        self.assertTrue(ui._handle_finish_job_excess_scan("num_3"))
        self.assertEqual(row["variance_reason"], "MISSING PARTS")
        self.assertEqual(row["status"], "SHORT")
        self.assertFalse(row["reason_required"])
        self.assertTrue(ui._pending_finish_excess_ready_to_print)

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
        self.assertIn("Q000000012.5", first["payload"])
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
            "verified_at_utc": "2026-11-21T01:00:00+00:00",
            "part": {"part_product_id": "8335"},
        }]
        ui._pending_finish_excess_index = 0
        ui._pending_finish_excess_input = ""
        ui._pending_finish_excess_ready_to_print = True
        ui.finishStatus = Mock()
        ui.status = Mock()
        ui._submit_pack_qr_print = Mock(return_value=True)
        ui._show_final_job_review_overlay = Mock()

        self.assertTrue(ui._print_finish_job_excess_and_continue())
        final_payload = ui._show_final_job_review_overlay.call_args.args[0]
        self.assertEqual(final_payload["product_part_excess_logs"][0]["actual_excess_qty"], 12.5)
        self.assertIn("excess_verification_completed_at_utc", final_payload)
        ui._show_final_job_review_overlay.assert_called_once()


if __name__ == "__main__":
    unittest.main()
