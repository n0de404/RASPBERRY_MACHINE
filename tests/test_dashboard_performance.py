from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import server as dashboard_server


class DashboardPerformanceSafetyTests(unittest.TestCase):
    def test_dashboard_summary_does_not_copy_heavy_logs(self):
        session = dashboard_server.MachineSession(
            client_id="RPI-TEST",
            machine_code="M00010",
            machine_name="IMM 310",
            product_pack_history_logs=[{"pack_key": "PACK-1", "qty_q": 25}],
            client_app_logs=[{"timestamp_utc": "2026-10-02T00:00:00+00:00", "message": "test"}],
            supervisor_rotation_logs=[{"checked_at_utc": "2026-10-02T00:00:00+00:00"}],
        )

        summary = session.to_dashboard_dict()

        for field in dashboard_server.DASHBOARD_HEAVY_SESSION_FIELDS:
            self.assertNotIn(field, summary)
        self.assertEqual(len(session.product_pack_history_logs), 1)
        self.assertEqual(len(session.client_app_logs), 1)
        self.assertTrue(summary["summary_only"])

    def test_activity_ids_are_deterministic_and_merge_is_idempotent(self):
        session = dashboard_server.MachineSession(
            client_id="RPI-TEST",
            machine_code="M00010",
            machine_name="IMM 310",
        )
        row = {
            "timestamp_utc": "2026-10-02T00:00:00+00:00",
            "source": "STATUS",
            "actor": "Operator",
            "message": "Ready",
        }

        first_id = dashboard_server._machine_activity_id(row)
        second_id = dashboard_server._machine_activity_id(dict(row))
        self.assertEqual(first_id, second_id)
        self.assertEqual(dashboard_server._merge_client_app_logs(session, [row]), 1)
        self.assertEqual(dashboard_server._merge_client_app_logs(session, [row]), 0)
        self.assertEqual(len(session.client_app_logs), 1)
        self.assertEqual(session.client_app_logs[0]["activity_id"], first_id)

    def test_dashboard_assets_are_separated_and_versioned(self):
        self.assertIn('/assets/dashboard.css?v=', dashboard_server.DASHBOARD_PAGE_HTML)
        self.assertIn('/assets/dashboard.js?v=', dashboard_server.DASHBOARD_PAGE_HTML)
        self.assertNotIn('function render(state)', dashboard_server.DASHBOARD_PAGE_HTML)
        self.assertIn('function render(state)', dashboard_server.DASHBOARD_JAVASCRIPT)
        self.assertGreater(len(dashboard_server.DASHBOARD_CSS), 1000)
        self.assertGreater(len(dashboard_server.DASHBOARD_JAVASCRIPT), 1000)

    def test_dashboard_supports_incremental_state_patches(self):
        script = dashboard_server.DASHBOARD_JAVASCRIPT
        self.assertIn('STATE_PATCH', script)
        self.assertIn('renderDashboardSectionIfChanged', script)

    def test_sql_history_does_not_load_large_json_fallback(self):
        compact = {
            "_history_summary_only": True,
            "finished_at_utc": "2026-10-02T00:00:00+00:00",
            "machine_code": "M00010",
            "job_code": "JOB-1",
            "operator_id": "OP-1",
            "pack_count": 2,
            "good_total": 50,
            "butal_total": 0,
            "reject_total": 0,
        }
        with patch.object(dashboard_server, "_load_finished_jobs_sql", return_value=[compact]):
            with patch.object(
                dashboard_server,
                "_load_json_list",
                side_effect=AssertionError("fallback JSON must stay cold while SQL is available"),
            ):
                rows = dashboard_server.load_finished_jobs()
        self.assertEqual(rows, [compact])

    def test_kpi_summary_uses_compact_history_log_counts(self):
        row = {
            "_history_summary_only": True,
            "_raw_material_log_count": 7,
            "_pack_history_log_count": 4,
            "_reject_review_log_count": 2,
            "machine_code": "M00010",
            "job_code": "JOB-1",
        }
        summary = dashboard_server._kpi_job_summary(row, [])
        self.assertEqual(summary["raw_material_scans"], 7)
        self.assertEqual(summary["pack_qr_scans"], 4)
        self.assertEqual(summary["reject_scans"], 2)


if __name__ == "__main__":
    unittest.main()
