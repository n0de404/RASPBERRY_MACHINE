from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import server as dashboard_server


class SupervisorRotationTests(unittest.TestCase):
    @staticmethod
    def _session() -> dashboard_server.MachineSession:
        return dashboard_server.MachineSession(
            client_id="RPI-TEST",
            machine_code="M00010",
            machine_name="IMM 310",
            job_code="JOB-310",
            operator_id="26-00025",
        )

    def test_rotation_check_updates_count_log_and_last_check(self):
        session = self._session()
        event = {
            "checked_at_utc": "2026-10-02T02:00:00+00:00",
            "supervisor_code": "SUP-01",
            "supervisor_name": "Supervisor One",
            "supervisor_role": "SUPERVISOR",
        }

        dashboard_server._apply_supervisor_rotation_check(session, event)
        dashboard_server._apply_supervisor_rotation_check(
            session,
            {**event, "checked_at_utc": "2026-10-02T03:00:00+00:00"},
        )

        self.assertEqual(session.supervisor_rotation_count, 2)
        self.assertEqual(len(session.supervisor_rotation_logs), 2)
        self.assertEqual(session.last_supervisor_check_name, "Supervisor One")
        self.assertEqual(session.last_supervisor_check_at_utc, "2026-10-02T03:00:00+00:00")
        self.assertEqual(session.supervisor_rotation_logs[-1]["job_code"], "JOB-310")

    def test_rotation_state_survives_snapshot_and_resets_for_new_job(self):
        session = self._session()
        dashboard_server._apply_supervisor_rotation_check(
            session,
            {
                "checked_at_utc": "2026-10-02T02:00:00+00:00",
                "supervisor_code": "SUP-01",
                "supervisor_name": "Supervisor One",
            },
        )

        restored = dashboard_server._session_from_active_snapshot(session.to_dict())
        self.assertIsNotNone(restored)
        self.assertEqual(restored.supervisor_rotation_count, 1)
        self.assertEqual(len(restored.supervisor_rotation_logs), 1)

        dashboard_server._reset_active_session_for_new_job_segment(restored)
        self.assertEqual(restored.supervisor_rotation_count, 0)
        self.assertEqual(restored.supervisor_rotation_logs, [])
        self.assertIsNone(restored.last_supervisor_check_at_utc)

    def test_dashboard_contains_rotation_indicator(self):
        self.assertIn("machine-supervisor-rotation-dot", dashboard_server.DASHBOARD_HTML)
        self.assertIn("supervisor_rotation_count", dashboard_server.DASHBOARD_HTML)
        self.assertIn('id="machineDetailSupervisorBtn"', dashboard_server.DASHBOARD_HTML)
        self.assertIn('id="machineDetailSupervisorMenu"', dashboard_server.DASHBOARD_HTML)
        self.assertIn("machineSupervisorActivityRows", dashboard_server.DASHBOARD_HTML)
        self.assertIn("Rotation checks", dashboard_server.DASHBOARD_HTML)
        self.assertNotIn("┬╖", dashboard_server.DASHBOARD_HTML)
        self.assertNotIn("ΓÇó", dashboard_server.DASHBOARD_HTML)

    def test_dashboard_summary_includes_compact_rotation_identity_and_time(self):
        session = self._session()
        dashboard_server._apply_supervisor_rotation_check(
            session,
            {
                "checked_at_utc": "2026-10-02T02:00:00+00:00",
                "supervisor_code": "SUP-01",
                "supervisor_name": "Supervisor One",
            },
        )

        summary = session.to_dashboard_dict()

        self.assertNotIn("supervisor_rotation_logs", summary)
        self.assertEqual(
            summary["supervisor_rotation_summary_logs"],
            [{
                "checked_at_utc": "2026-10-02T02:00:00+00:00",
                "supervisor_code": "SUP-01",
                "supervisor_name": "Supervisor One",
                "supervisor_role": "SUPERVISOR",
            }],
        )
        self.assertIn("Last supervisor", dashboard_server.DASHBOARD_HTML)
        self.assertIn("Last check time", dashboard_server.DASHBOARD_HTML)


if __name__ == "__main__":
    unittest.main()
