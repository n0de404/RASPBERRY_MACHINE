from __future__ import annotations

import sys
import unittest
from unittest.mock import patch
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
                "session_snapshot": {
                    "job_code": "34589",
                    "job_name": "WO-34589",
                    "operator_id": "26-00025",
                    "production_session_id": "PS-REAL-FLOW-TEST",
                    "job_payload": {"data": {"job": {"ref_no": "WO-34589"}}},
                },
            }
        }

        session = dashboard_server._test_machine_session_payload(settings)

        self.assertIsNotNone(session)
        self.assertTrue(session["is_test_machine"])
        self.assertEqual(session["machine_code"], dashboard_server.TEST_MACHINE_CODE)
        self.assertEqual(session["production_session_id"], "PS-REAL-FLOW-TEST")
        self.assertEqual(session["job_code"], "34589")
        self.assertEqual(session["operator_id"], "26-00025")
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

    def test_real_client_pack_and_reject_events_stay_out_of_production_sessions(self):
        original_settings = dashboard_server.SERVER_SETTINGS
        original_session_keys = set(dashboard_server.SESSIONS)
        dashboard_server.SERVER_SETTINGS = {
            **original_settings,
            "test_machine": dashboard_server._normalize_test_machine_settings({
                "enabled": True,
                "target_packs": 5,
                "pack_qty": 8,
            }),
        }
        try:
            with patch.object(dashboard_server, "save_server_settings", return_value=None):
                dashboard_server._apply_test_machine_client_event({
                    "client_id": "RPI-TEST",
                    "machine_code": dashboard_server.TEST_MACHINE_CODE,
                    "job_code": "34589",
                    "job_name": "WO-34589",
                    "operator_id": "26-00025",
                    "production_session_id": "PS-REAL-FLOW-TEST",
                    "event": {
                        "type": "PACK",
                        "pack_qty": 1,
                        "qty": 8,
                        "pack_key": "CLIENT-TEST-PACK-1",
                        "pack_record": {"raw_scan": "testpack~8"},
                    },
                    "last_event": "TEST PACK +1 GOOD +8",
                })
                dashboard_server._apply_test_machine_client_event({
                    "machine_code": dashboard_server.TEST_MACHINE_CODE,
                    "event": {"type": "REJECT", "qty": 2, "reason": "BM01"},
                    "last_event": "TEST REJECT +2",
                })

            config = dashboard_server.SERVER_SETTINGS["test_machine"]
            self.assertEqual(config["pack_count"], 1)
            self.assertEqual(config["good_total"], 8)
            self.assertEqual(config["reject_total"], 2)
            self.assertEqual(config["session_snapshot"]["job_code"], "34589")
            self.assertEqual(config["session_snapshot"]["operator_id"], "26-00025")
            self.assertEqual(set(dashboard_server.SESSIONS), original_session_keys)
            self.assertNotIn(dashboard_server.TEST_MACHINE_CODE, dashboard_server.SESSIONS)
        finally:
            dashboard_server.SERVER_SETTINGS = original_settings


if __name__ == "__main__":
    unittest.main()
