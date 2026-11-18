import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLIENT_DIR = os.path.join(ROOT, "client")
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

import client as production_client


class ClientOperatorWorkflowTests(unittest.TestCase):
    @staticmethod
    def _client():
        ui = production_client.ClientUI.__new__(production_client.ClientUI)
        ui.state = production_client.ClientState()
        return ui

    def test_active_reliever_is_displayed_without_main_operator(self):
        ui = self._client()
        ui.state.operator_id = "OP-1 - Main Operator"
        ui.state.reliever_id = "OP-2 - Relief Operator"
        ui.state.break_active = True

        text, highlighted = ui._operator_header_display()

        self.assertEqual(text, "RELIEVER: Relief Operator")
        self.assertNotIn("Main Operator", text)
        self.assertTrue(highlighted)

    def test_active_reliever_has_priority_over_helper_manpower_count(self):
        ui = self._client()
        ui.state.operator_id = "OP-1 - Main Operator"
        ui.state.crew_members = [{"operator_id": "OP-3 - Helper Operator"}]
        ui.state.reliever_id = "OP-2 - Relief Operator"
        ui.state.break_active = True

        text, highlighted = ui._operator_header_display()

        self.assertEqual(text, "RELIEVER: Relief Operator")
        self.assertTrue(highlighted)

    def test_change_operator_choices_list_main_then_helpers(self):
        ui = self._client()
        ui.state.operator_id = "OP-1 - Main Operator"
        ui.state.crew_members = [
            {"operator_id": "OP-2 - Helper One"},
            {"operator_id": "OP-3 - Helper Two"},
        ]

        rows = ui._change_operator_candidates()

        self.assertEqual([row["role"] for row in rows], ["MAIN", "HELPER", "HELPER"])
        self.assertEqual([row["operator_code"] for row in rows], ["OP-1", "OP-2", "OP-3"])

    def test_main_or_reliever_badge_can_end_active_relief(self):
        ui = self._client()
        ui.state.operator_id = "OP-1 - Main Operator"
        ui.state.reliever_id = "OP-2 - Relief Operator"
        ui.state.break_active = True

        self.assertTrue(ui._operator_scan_ends_relief("OP-1"))
        self.assertTrue(ui._operator_scan_ends_relief("OP-2"))
        self.assertFalse(ui._operator_scan_ends_relief("OP-3"))

    def test_offline_related_linked_pack_credits_both_jobs(self):
        ui = self._client()
        ui.state.job_code = "100"
        ui.state.linkage_enabled = True
        ui.state.linkage_jobs = [
            {
                "job_code": "200",
                "job_name": "Linked Output",
                "job_payload": {"data": {"job": {"ref_no": "Linked Output"}}},
            }
        ]

        allocation = ui._normal_linkage_pack_allocation(
            12,
            routed_job_code="200",
            related_to_main=True,
        )

        self.assertEqual(allocation["mode"], "MULTI_OUTPUT")
        self.assertEqual(allocation["main_qty"], 12)
        self.assertEqual(
            allocation["job_output_qty"],
            {"100": 12, "200": 12},
        )

    def test_offline_unrelated_linked_pack_credits_qr_job_only(self):
        ui = self._client()
        ui.state.job_code = "100"
        ui.state.linkage_enabled = True
        ui.state.linkage_jobs = [
            {
                "job_code": "200",
                "job_name": "Linked Output",
                "job_payload": {"data": {"job": {"ref_no": "Linked Output"}}},
            }
        ]

        allocation = ui._normal_linkage_pack_allocation(
            12,
            routed_job_code="200",
            related_to_main=False,
        )

        self.assertEqual(allocation["main_qty"], 0)
        self.assertEqual(
            allocation["job_output_qty"],
            {"100": 0, "200": 12},
        )

    def test_scanning_existing_linked_job_removes_it_and_syncs_exact_remainder(self):
        ui = self._client()
        ui.state.waiting_linkage_job_scan = True
        ui.state.linkage_enabled = True
        ui.state.linkage_job_code = "JOB-300"
        ui.state.linkage_job_name = "Green Cover"
        ui.state.linkage_job_payload = {"job": {"id": "JOB-300"}}
        ui.state.linkage_jobs = [
            {"job_code": "JOB-200", "job_name": "Blue Cover", "job_payload": {"id": 200}},
            {"job_code": "JOB-300", "job_name": "Green Cover", "job_payload": {"id": 300}},
        ]
        ui.state.prepack_active_job_code = "JOB-300"
        ui._remove_job_linkage_mode = False
        ui._offline_pack_main_qty_overrides = {"JOB-300": 12}
        ui.status = Mock()
        ui._clear_pending_linked_job_api_retry = Mock()
        ui._resolved_linked_job_api_retry = None
        ui._hide_invalid_overlay = Mock()
        ui._refresh_ui = Mock()
        ui._save_active_session_snapshot = Mock()
        ui.sync_session_snapshot_to_server = Mock()
        ui.push_event = Mock()
        res = SimpleNamespace(value="JOB-300", meta={"po_number": "JOB-300"})

        index = ui._linked_job_index_for_scan(res, "JOB-300")
        removed = ui._remove_linked_job_at_index(index, linkage_toggle=True)

        self.assertTrue(removed)
        self.assertEqual([row["job_code"] for row in ui.state.linkage_jobs], ["JOB-200"])
        self.assertEqual(ui.state.linkage_job_code, "JOB-200")
        self.assertEqual(ui.state.prepack_active_job_code, "JOB-200")
        self.assertFalse(ui.state.waiting_linkage_job_scan)
        event = ui.push_event.call_args.args[0]
        self.assertEqual(event["type"], "JOB_LINKAGE_REMOVED")
        self.assertEqual(event["removed_job_code"], "JOB-300")
        self.assertEqual([row["job_code"] for row in event["post_linkage_jobs"]], ["JOB-200"])
        self.assertTrue(event["post_linkage_enabled"])


class ClientShiftTurnoverWorkflowTests(unittest.TestCase):
    @staticmethod
    def _client():
        ui = production_client.ClientUI.__new__(production_client.ClientUI)
        ui.state = production_client.ClientState()
        ui.status = Mock()
        ui._refresh_ui = Mock()
        ui._save_active_session_snapshot = Mock()
        ui.sync_session_snapshot_to_server = Mock()
        ui._restore_same_job_part_carryover = Mock(return_value=2)
        ui._start_operator_shift_tracking = Mock()
        ui._begin_initial_cycle_time_setup = Mock()
        return ui

    def test_num_1_turnover_keeps_job_operator_and_helper_crew(self):
        ui = self._client()

        def clear_session():
            ui.state = production_client.ClientState()

        ui._clear_full_session = Mock(side_effect=clear_session)
        snapshot = {
            "machine_code": "M00001",
            "machine_name": "IMM 301",
            "job_code": "JOB-100",
            "job_name": "Blue Cover",
            "job_payload": {"data": {"parts": [{"sku": "PART-1"}]}},
            "operator_id": "OP-1 - Main Operator",
            "operator_qr_payload": "OP-1-QR",
            "operator_pending_server_validation": False,
            "crew_members": [{"operator_id": "OP-2 - Helper Operator"}],
            "reliever_id": "OP-3 - Temporary Reliever",
            "break_active": True,
            "pack_count": 9,
            "good_total": 108,
            "linkage_enabled": True,
            "linkage_job_code": "JOB-200",
            "linkage_job_name": "Linked Cover",
            "linkage_job_payload": {"data": {"job": {"id": "JOB-200"}}},
            "linkage_jobs": [{
                "job_code": "JOB-200",
                "linkage_pack_count": 5,
                "linkage_good_total": 60,
            }],
        }

        changed = ui._clear_shift_for_turnover_keep_job(snapshot)

        self.assertTrue(changed)
        self.assertEqual(ui.state.machine_code, "M00001")
        self.assertEqual(ui.state.job_code, "JOB-100")
        self.assertEqual(ui.state.job_payload, snapshot["job_payload"])
        self.assertEqual(ui.state.operator_id, "OP-1 - Main Operator")
        self.assertEqual(ui.state.operator_qr_payload, "OP-1-QR")
        self.assertEqual(
            [row["operator_id"] for row in ui.state.crew_members],
            ["OP-2 - Helper Operator"],
        )
        self.assertIsNone(ui.state.reliever_id)
        self.assertFalse(ui.state.break_active)
        self.assertEqual(ui.state.pack_count, 0)
        self.assertEqual(ui.state.good_total, 0)
        self.assertTrue(ui.state.production_session_id.startswith("PS-"))
        self.assertEqual(ui.state.linkage_jobs[0]["linkage_pack_count"], 0)
        self.assertEqual(ui.state.linkage_jobs[0]["linkage_good_total"], 0)
        ui._restore_same_job_part_carryover.assert_called_once_with()
        ui._start_operator_shift_tracking.assert_called_once_with()
        ui._begin_initial_cycle_time_setup.assert_called_once_with()
        ui.sync_session_snapshot_to_server.assert_called_once_with(
            "SESSION SNAPSHOT SYNC (SHIFT TURNOVER)"
        )

    def test_num_1_choice_uses_saved_turnover_snapshot(self):
        ui = self._client()
        snapshot = {"machine_code": "M00001", "job_code": "JOB-100"}
        ui._pending_finish_shift_clear_choice = True
        ui._pending_finish_shift_turnover_snapshot = snapshot
        ui._hide_invalid_overlay = Mock()
        ui._clear_shift_for_turnover_keep_job = Mock(return_value=True)
        ui._clear_shift_session_keep_machine = Mock()

        handled = ui._handle_finish_shift_clear_choice("num_1")

        self.assertTrue(handled)
        ui._clear_shift_for_turnover_keep_job.assert_called_once_with(snapshot)
        ui._clear_shift_session_keep_machine.assert_not_called()
        self.assertFalse(ui._pending_finish_shift_clear_choice)
        self.assertIsNone(ui._pending_finish_shift_turnover_snapshot)

    def test_num_2_choice_clears_job_and_operator(self):
        ui = self._client()
        ui._pending_finish_shift_clear_choice = True
        ui._pending_finish_shift_turnover_snapshot = {
            "machine_code": "M00001",
            "job_code": "JOB-100",
        }
        ui._hide_invalid_overlay = Mock()
        ui._clear_shift_for_turnover_keep_job = Mock(return_value=True)
        ui._clear_shift_session_keep_machine = Mock()

        handled = ui._handle_finish_shift_clear_choice("num_2")

        self.assertTrue(handled)
        ui._clear_shift_session_keep_machine.assert_called_once_with()
        ui._clear_shift_for_turnover_keep_job.assert_not_called()
        self.assertFalse(ui._pending_finish_shift_clear_choice)
        self.assertIsNone(ui._pending_finish_shift_turnover_snapshot)

    def test_linked_shift_totals_use_filtered_pack_ledger(self):
        ui = self._client()
        ui.state.machine_code = "M00001"
        ui.state.job_code = "MAIN-1"
        ui.state.job_name = "Main Job"
        ui.state.operator_id = "OP-1"
        ui.state.linkage_enabled = True
        ui.state.linkage_jobs = [{
            "job_code": "PACK-1",
            "job_name": "Packing Job",
            "job_payload": {},
            "linkage_output_role": "PACKING",
            "linkage_pack_count": 2,
            "linkage_good_total": 24,
        }]
        ui.state.product_pack_history_logs = [
            {
                "index": str(index),
                "completed_pack_qty": 12,
                "job_output_qty": {"PACK-1": 12},
                "voided": False,
            }
            for index in range(1, 57)
        ]
        ui.state.operator_shift_baseline_product_pack_history_logs_len = 0
        ui._shift_butal_qty_for_job = Mock(return_value=0)
        main_payload = {
            "job_code": "MAIN-1",
            "job_name": "Main Job",
            "pack_count": 0,
            "good_total": 0,
            "product_pack_history_logs": [],
        }

        linked = ui._build_linked_operator_shift_payloads(main_payload)[0]

        self.assertEqual(linked["pack_count"], 56)
        self.assertEqual(linked["good_total"], 672)
        self.assertEqual(linked["total_good"], 672)
        self.assertEqual(len(linked["product_pack_history_logs"]), 56)


if __name__ == "__main__":
    unittest.main()
