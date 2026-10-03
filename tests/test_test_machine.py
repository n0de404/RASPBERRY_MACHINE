from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import server as dashboard_server


class TestMachineSandboxTests(unittest.TestCase):
    def test_disabled_sandbox_does_not_create_dashboard_session(self):
        settings = {
            "test_machine": {
                "enabled": False,
                "target_packs": 12,
                "pack_qty": 20,
            }
        }

        self.assertIsNone(dashboard_server._test_machine_session_payload(settings))

    def test_enabled_session_is_visibly_marked_and_uses_only_test_data(self):
        settings = {
            "test_machine": {
                "enabled": True,
                "target_packs": 12,
                "pack_qty": 20,
                "pack_count": 3,
                "good_total": 60,
                "reject_total": 2,
                "reject_breakdown": {"DENT": 2},
                "pack_logs": [{"pack_key": "TEST-PACK-1", "qty": 20}],
                "reject_logs": [{"reject_scan_id": "TEST-REJECT-1", "reason_code": "DENT"}],
            }
        }

        session = dashboard_server._test_machine_session_payload(settings)

        self.assertIsNotNone(session)
        self.assertTrue(session["is_test_machine"])
        self.assertEqual(session["machine_code"], dashboard_server.TEST_MACHINE_CODE)
        self.assertEqual(session["production_session_id"], "TEST-SANDBOX-SESSION")
        self.assertEqual(session["test_target_packs"], 12)
        self.assertEqual(session["pack_total"], 3)
        self.assertEqual(session["good_total"], 60)
        self.assertEqual(session["reject_total"], 2)

    def test_test_configuration_is_bounded_and_logs_are_capped(self):
        config = dashboard_server._normalize_test_machine_settings({
            "enabled": True,
            "target_packs": -50,
            "pack_qty": 0,
            "pack_count": -2,
            "pack_logs": [{"index": idx} for idx in range(600)],
            "reject_logs": [{"index": idx} for idx in range(600)],
        })

        self.assertEqual(config["target_packs"], 1)
        self.assertEqual(config["pack_qty"], 1)
        self.assertEqual(config["pack_count"], 0)
        self.assertEqual(len(config["pack_logs"]), 500)
        self.assertEqual(len(config["reject_logs"]), 500)

    def test_dashboard_exposes_test_controls_and_isolation_label(self):
        html = dashboard_server.DASHBOARD_HTML
        self.assertIn('id="settingsNavTestMachine"', html)
        self.assertIn('id="settingsTestAddPackBtn"', html)
        self.assertIn('id="settingsTestAddRejectBtn"', html)
        self.assertIn('id="settingsTestResetBtn"', html)
        self.assertIn("TEST ONLY", html)
        self.assertIn("/api/test-machine/action", html)


if __name__ == "__main__":
    unittest.main()
