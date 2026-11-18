import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


CLIENT_DIR = Path(__file__).resolve().parents[1] / "client"
sys.path.insert(0, str(CLIENT_DIR))

import client as client_module
from client import ClientUI, _completion_pack_projection


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

    def test_num_zero_is_input_digit_but_not_pdr_reason(self):
        dummy = object()

        self.assertEqual(ClientUI._numpad_digit_from_scan(dummy, "num_0"), "0")
        self.assertIsNone(ClientUI._extract_production_reason_code(dummy, "num_0"))

    def test_clear_is_a_numpad_command(self):
        dummy = object()

        self.assertEqual(ClientUI._numpad_command_from_scan(dummy, "clear"), "clear")

    def test_clear_erases_butal_input_without_leaving_workflow(self):
        state = SimpleNamespace(
            pending_offline_qr_raw="",
            pending_offline_qr_phase="",
            waiting_cycle_time_confirm_popup=False,
            waiting_machine_counter_overwrite_input=False,
            waiting_initial_machine_counter_input=False,
            waiting_initial_cycle_time_input=False,
            waiting_butal_completion_carry_input=True,
            waiting_cycle_time_input=False,
            butal_completion_input="125",
            reject_multiplier_input="",
        )
        status_messages = []
        dummy = SimpleNamespace(state=state, status=SimpleNamespace(setText=status_messages.append))
        dummy._refresh_ui = lambda: None
        dummy._save_active_session_snapshot = lambda: None

        cleared = ClientUI._clear_active_typed_input(dummy)

        self.assertTrue(cleared)
        self.assertEqual(state.butal_completion_input, "")
        self.assertTrue(state.waiting_butal_completion_carry_input)
        self.assertIn("same workflow", status_messages[-1])


class StartupCompletionFenceTests(unittest.TestCase):
    def test_approved_partial_shift_does_not_close_production_session(self):
        partial = {
            "record_type": "SHIFT_PARTIAL",
            "review_status": "APPROVED",
            "production_session_id": "PS-ACTIVE",
        }
        with patch.object(client_module, "_load_finish_shift_json", return_value=[partial]), patch.object(
            client_module, "_load_finished_jobs_json", return_value=[]
        ):
            self.assertEqual(ClientUI._locally_completed_session_ids(object()), set())

    def test_approved_finished_job_closes_production_session(self):
        finished = {
            "record_type": "FINISHED_JOB",
            "review_status": "APPROVED",
            "production_session_id": "PS-CLOSED",
        }
        with patch.object(client_module, "_load_finish_shift_json", return_value=[]), patch.object(
            client_module, "_load_finished_jobs_json", return_value=[finished]
        ):
            self.assertEqual(ClientUI._locally_completed_session_ids(object()), {"PS-CLOSED"})

    def test_missing_pack_quantity_cannot_make_projection(self):
        result = _completion_pack_projection(4000, 3900, 0)

        self.assertEqual(result["remaining_qty"], 100)
        self.assertEqual(result["packs_remaining"], 0)

    def test_parked_finish_event_uses_parked_production_session_id(self):
        captured = {}
        dummy = SimpleNamespace(
            state=SimpleNamespace(
                machine_code="M00014",
                machine_name="IMM 314",
                job_code="JOB-CURRENT",
                job_name="Current Job",
                job_started_at="2026-11-07T00:00:00+00:00",
                operator_id="OP-1",
                production_session_id="PS-CURRENT",
            )
        )
        dummy._current_client_id = lambda: "RPI-TEST"
        dummy._save_active_session_snapshot = lambda: None
        dummy._legacy_production_session_id = lambda *args: "PS-LEGACY"
        dummy._enqueue_server_event = lambda payload, silent=False: captured.update(payload) or True

        accepted = ClientUI.push_event(
            dummy,
            {
                "type": "FINISH_JOB",
                "finished_job": {
                    "job_code": "JOB-PARKED",
                    "production_session_id": "PS-PARKED",
                },
            },
            "FINISH PARKED JOB",
        )

        self.assertTrue(accepted)
        self.assertEqual(captured["production_session_id"], "PS-PARKED")
        self.assertEqual(captured["event"]["production_session_id"], "PS-PARKED")


if __name__ == "__main__":
    unittest.main()
