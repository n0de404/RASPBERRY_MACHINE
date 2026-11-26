import os
import inspect
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


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

    def test_color_mold_choice_precedes_general_multiplier_input(self):
        source = inspect.getsource(production_client.ClientUI.on_scanned)

        choice_position = source.index("if self._handle_color_change_number_choice(raw_l):")
        reject_choice_position = source.index('state_choice = re.fullmatch(r"num_(\\d+)", raw_l)')
        multiplier_position = source.index("self._append_reject_multiplier_digit(input_digit)")

        self.assertLess(choice_position, reject_choice_position)
        self.assertLess(choice_position, multiplier_position)

    def test_color_mold_preview_checks_supervisor_before_numeric_choice(self):
        source = inspect.getsource(production_client.ClientUI.on_scanned)

        preview_position = source.index("if isinstance(self._pending_color_mold_change, dict):")
        choice_position = source.index("if self._handle_color_change_number_choice(raw_l):")

        self.assertLess(preview_position, choice_position)

    def test_num_1_selects_color_without_becoming_multiplier(self):
        ui = self._client()
        ui.state.waiting_color_change_job_scan = True
        ui.state.pending_color_change_reason = "CHOOSE_TYPE"
        ui.state.reject_multiplier_input = ""
        ui.status = Mock()
        ui._hide_invalid_overlay = Mock()
        ui._show_info_overlay = Mock()
        ui._save_active_session_snapshot = Mock()

        handled = ui._handle_color_change_number_choice("num_1")

        self.assertTrue(handled)
        self.assertEqual(ui.state.pending_color_change_reason, "COLOR_CHANGE")
        self.assertEqual(ui.state.reject_multiplier_input, "")
        ui._show_info_overlay.assert_called_once()

    def test_visible_color_mold_menu_repairs_cleared_transient_state(self):
        ui = self._client()
        ui.state.waiting_color_change_job_scan = False
        ui.state.pending_color_change_reason = ""
        ui.invalidOverlay = SimpleNamespace(isVisible=lambda: True)
        ui.choiceCardsWidget = SimpleNamespace(isVisible=lambda: True)
        ui.invalidTextLabel = SimpleNamespace(text=lambda: "CHANGE COLOR / MOLD")
        ui.status = Mock()
        ui._hide_invalid_overlay = Mock()
        ui._show_info_overlay = Mock()
        ui._save_active_session_snapshot = Mock()

        handled = ui._handle_color_change_number_choice("num_2")

        self.assertTrue(handled)
        self.assertTrue(ui.state.waiting_color_change_job_scan)
        self.assertEqual(ui.state.pending_color_change_reason, "MOLD_CHANGE")
        ui._show_info_overlay.assert_called_once()

    def test_signed_carryover_fences_job_started_before_cutover(self):
        ui = self._client()
        ui.state.machine_code = "M00008"
        ui.state.job_code = "122648"
        ui.state.job_started_at = "2026-11-20T06:00:00+00:00"
        ui._negative_carryover_policy = {
            "version": 1,
            "cutover_created_at_utc": "2026-11-21T00:00:00+00:00",
            "grandfathered_job_keys": [],
        }

        with patch.object(production_client, "_save_negative_carryover_policy", return_value=True):
            enabled = ui._signed_carryover_enabled_for_current_job()

        self.assertFalse(enabled)
        self.assertIn(
            "M00008|122648",
            ui._negative_carryover_policy["grandfathered_job_keys"],
        )

    def test_signed_carryover_enables_job_started_after_cutover(self):
        ui = self._client()
        ui.state.machine_code = "M00008"
        ui.state.job_code = "NEW-123"
        ui.state.job_started_at = "2026-11-21T01:00:00+00:00"
        ui._negative_carryover_policy = {
            "version": 1,
            "cutover_created_at_utc": "2026-11-21T00:00:00+00:00",
            "grandfathered_job_keys": [],
        }

        self.assertTrue(ui._signed_carryover_enabled_for_current_job())

    def test_finish_job_releases_signed_carryover_fence(self):
        ui = self._client()
        ui._negative_carryover_policy = {
            "version": 1,
            "grandfathered_job_keys": ["M00008|122648"],
        }

        with patch.object(production_client, "_save_negative_carryover_policy", return_value=True):
            ui._release_negative_carryover_job_fence("M00008", "122648")

        self.assertEqual(ui._negative_carryover_policy["grandfathered_job_keys"], [])

    def test_machine_release_retains_server_snapshot_and_clears_local_assignment(self):
        ui = self._client()
        ui.state.machine_code = "M00008"
        ui.state.machine_name = "IMM 308"
        ui.state.job_code = "JOB-100"
        ui._pending_final_review_payload = None
        ui._operator_shift_flash_active = False
        ui._finish_anim_running = False
        ui._supervisor_validation_pending = False
        ui._pending_server_recovery = {"machine_code": "M00008"}
        ui._skip_server_recovery_machine = "M00008"
        ui.status = Mock()
        ui._state_to_active_snapshot = Mock(return_value={
            "machine_code": "M00008",
            "job_code": "JOB-100",
            "pack_count": 7,
        })
        ui.push_event = Mock(return_value=True)
        ui._clear_full_session = Mock()
        ui._enqueue_active_session_file_persist = Mock()
        ui._hide_invalid_overlay = Mock()
        ui._append_app_log = Mock()

        released = ui._release_current_machine()

        self.assertTrue(released)
        event = ui.push_event.call_args.args[0]
        self.assertEqual(event["type"], "MACHINE_RELEASE")
        self.assertEqual(event["session_snapshot"]["pack_count"], 7)
        ui._clear_full_session.assert_called_once_with()
        ui._enqueue_active_session_file_persist.assert_called_once_with(
            {"op": "delete", "machine_code": "M00008"}
        )
        self.assertIsNone(ui._pending_server_recovery)
        self.assertEqual(ui._skip_server_recovery_machine, "")

    def test_operator_handoff_is_a_log_not_a_production_segment(self):
        ui = self._client()
        ui.state.machine_code = "M00008"
        ui.state.machine_name = "IMM 308"
        ui.state.job_code = "JOB-100"
        ui.state.job_name = "3-26-100-1"
        ui.state.production_session_id = "PS-CONTINUOUS"
        ui.state.operator_id = "OP-1 - First Operator"
        ui.state.operator_shift_started_at = "2026-11-24T01:00:00+00:00"
        ui._current_client_id = Mock(return_value="RPI-CLIENT-008")
        ui._operator_display_name = lambda value: str(value or "")

        row = ui._record_operator_handoff(
            reason="QR_SHIFT_HANDOFF",
            reviewer={"code": "SV-1", "name": "Supervisor One", "role": "SUPERVISOR"},
        )

        self.assertEqual(row["record_type"], "OPERATOR_HANDOFF")
        self.assertEqual(row["outgoing_operator_id"], "OP-1 - First Operator")
        self.assertNotIn("pack_count", row)
        self.assertNotIn("good_total", row)
        self.assertEqual(ui._operator_shift_segment_rows(), [])

    def test_continuous_handoff_preserves_job_totals_and_scan_history(self):
        ui = self._client()
        ui.state.machine_code = "M00008"
        ui.state.job_code = "JOB-100"
        ui.state.production_session_id = "PS-CONTINUOUS"
        ui.state.operator_id = "OP-1 - First Operator"
        ui.state.pack_count = 12
        ui.state.good_total = 48
        ui.state.reject_total = 2
        ui.state.product_pack_history_logs = [{"pack_key": "PACK-1", "scan_operator_id": "OP-1"}]
        ui.state.raw_material_logs = [{"unique_key": "PART-1", "scan_operator_id": "OP-1"}]
        ui.state.raw_material_unique_keys = {"PART-1"}
        ui._close_open_relief_for_operator_handoff = Mock()
        ui._refresh_ui = Mock()
        ui._save_active_session_snapshot = Mock()
        ui.push_event = Mock(return_value=True)
        ui.sync_session_snapshot_to_server = Mock()

        ui._prepare_continuous_operator_handoff({"handoff_id": "OH-1"})

        self.assertIsNone(ui.state.operator_id)
        self.assertEqual(ui.state.production_session_id, "PS-CONTINUOUS")
        self.assertEqual(ui.state.pack_count, 12)
        self.assertEqual(ui.state.good_total, 48)
        self.assertEqual(ui.state.reject_total, 2)
        self.assertEqual(len(ui.state.product_pack_history_logs), 1)
        self.assertEqual(len(ui.state.raw_material_logs), 1)
        self.assertEqual(ui.state.raw_material_unique_keys, {"PART-1"})
        self.assertEqual(ui.push_event.call_args.args[0]["type"], "OPERATOR_HANDOFF")

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


class ClientRawMaterialRecoveryTests(unittest.TestCase):
    @staticmethod
    def _client():
        ui = production_client.ClientUI.__new__(production_client.ClientUI)
        ui.state = production_client.ClientState()
        return ui

    def test_dedupe_uses_qr_identity_not_sku_or_lot(self):
        ui = self._client()
        rows = [
            {"unique_key": "PART:LOT-A:1", "material_sku": "RESIN-A", "qty": 25},
            {"unique_key": "PART:LOT-A:2", "material_sku": "RESIN-A", "qty": 25},
            {"unique_key": "PART:LOT-A:1", "material_sku": "RESIN-A", "qty": 25},
        ]

        deduped = ui._dedupe_raw_material_logs(rows)

        self.assertEqual(len(deduped), 2)
        self.assertEqual(
            [row["unique_key"] for row in deduped],
            ["PART:LOT-A:1", "PART:LOT-A:2"],
        )
        self.assertEqual(sum(row["qty"] for row in deduped), 50)

    def test_recovery_merge_unions_registry_and_deduplicates_replicas(self):
        ui = self._client()
        server = {
            "production_session_id": "PS-1",
            "raw_material_logs": [
                {"unique_key": "PART-1", "material_name": "Resin", "qty": 25},
            ],
            "raw_material_unique_keys": ["PART-1"],
        }
        local = {
            "production_session_id": "PS-1",
            "raw_material_logs": [
                {"unique_key": "PART-1", "material_name": "Resin", "qty": 25},
                {"unique_key": "PART-2", "material_name": "Resin", "qty": 25},
            ],
            "raw_material_unique_keys": ["PART-1", "PART-2", "VOIDED-HISTORY-BLOCK"],
        }

        merged = ui._merge_matching_recovery_snapshots(server, local)

        self.assertEqual(len(merged["raw_material_logs"]), 2)
        self.assertEqual(merged["raw_sacks_count"], 2)
        self.assertEqual(
            set(merged["raw_material_unique_keys"]),
            {"PART-1", "PART-2", "VOIDED-HISTORY-BLOCK"},
        )

    def test_sanitize_repairs_count_and_keeps_job_wide_identity_history(self):
        ui = self._client()
        ui.state.raw_material_logs = [
            {"unique_key": "PART-1", "material_name": "Resin", "qty": 25},
            {"unique_key": "PART-1", "material_name": "Resin", "qty": 25},
            {
                "unique_key": "SHIFT-CARRY:PART-1",
                "material_name": "Resin",
                "qty": 5,
                "source": "FINISH_SHIFT_PART_CARRYOVER",
            },
        ]
        ui.state.raw_material_unique_keys = {"PART-1", "PART-OLD"}

        ui._sanitize_active_raw_material_inventory(ui.state.raw_material_unique_keys)

        self.assertEqual(len(ui.state.raw_material_logs), 2)
        self.assertEqual(ui.state.raw_sacks_count, 1)
        self.assertIn("PART-OLD", ui.state.raw_material_unique_keys)
        self.assertIn("SHIFT-CARRY:PART-1", ui.state.raw_material_unique_keys)

    def test_recovery_drops_carryover_when_its_original_qr_is_present(self):
        ui = self._client()
        original_raw = "O000000000060000001246500000000000|LOT-A|1"
        rows = [
            {
                "unique_key": "PART:LOT-A:1",
                "raw_scan": original_raw,
                "material_name": "Resin",
                "qty": 25,
                "source": "RAW_MATERIAL_QR",
            },
            {
                "unique_key": "SHIFT-CARRY:JOB-1:RESIN:TIME",
                "carryover_origin_unique_key": "PART:LOT-A:1",
                "raw_scan": original_raw,
                "material_name": "Resin",
                "qty": 14.738,
                "source": "FINISH_SHIFT_PART_CARRYOVER",
            },
        ]

        deduped = ui._dedupe_raw_material_logs(rows)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["unique_key"], "PART:LOT-A:1")
        self.assertEqual(sum(row["qty"] for row in deduped), 25)


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
