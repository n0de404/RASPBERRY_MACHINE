import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLIENT_DIR = os.path.join(ROOT, "client")
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

import client as production_client


class ClientCommandBannerTests(unittest.TestCase):
    @staticmethod
    def _client():
        ui = production_client.ClientUI.__new__(production_client.ClientUI)
        ui.state = production_client.ClientState()
        ui._change_work_order_phase = ""
        ui._change_work_order_target = None
        ui._remove_job_linkage_mode = False
        ui._crew_action_mode = ""
        ui._reliever_action_mode = False
        ui._mixing_pending_job_raw = ""
        ui._pending_final_review_payload = None
        ui._operator_shift_flash_active = False
        return ui

    def test_change_work_order_state_is_shown_in_banner(self):
        ui = self._client()
        ui.state.machine_code = "M00001"
        ui.state.job_code = "123"
        ui.state.operator_id = "OP-1"
        ui._change_work_order_phase = "SELECT"

        text = ui._active_command_banner_text()

        self.assertIn("CHANGE WORK ORDER", text)
        self.assertIn("scan running JOB", text)
        self.assertIn("cancel", text)

    def test_orphaned_change_command_is_cleared_after_reconnect(self):
        ui = self._client()
        ui.state.machine_code = "M00001"
        ui._change_work_order_phase = "SELECT"
        ui._change_work_order_target = {"job_code": "OLD"}

        changed = ui._sanitize_transient_command_modes()

        self.assertTrue(changed)
        self.assertEqual(ui._change_work_order_phase, "")
        self.assertIsNone(ui._change_work_order_target)

    def test_persisted_void_state_is_shown_after_reconnect(self):
        ui = self._client()
        ui.state.machine_code = "M00001"
        ui.state.job_code = "123"
        ui.state.operator_id = "OP-1"
        ui.state.waiting_void_scan = True

        self.assertEqual(
            ui._active_command_banner_text(),
            "VOID MODE: scan item QR to void",
        )


if __name__ == "__main__":
    unittest.main()
