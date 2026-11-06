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

        # Mixing jobs retain only a compact per-job summary for the live cards;
        # every full audit ledger must stay out of the dashboard payload.
        for field in dashboard_server.DASHBOARD_HEAVY_SESSION_FIELDS - {"mixing_open_jobs"}:
            self.assertNotIn(field, summary)
        self.assertEqual(summary["mixing_open_jobs"], [])
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

    def test_dashboard_defers_hidden_heavy_panels_until_after_machine_cards(self):
        script = dashboard_server.DASHBOARD_JAVASCRIPT
        self.assertIn('scheduleDeferredDashboardSections(state);', script)
        self.assertIn('window.requestIdleCallback(run, {timeout:250});', script)
        render_start = script.index('function render(state)')
        render_end = script.index('function setPlanningQueueOpen', render_start)
        render_source = script[render_start:render_end]
        self.assertLess(
            render_source.index('renderMachineTodo(state || {});'),
            render_source.index('scheduleDeferredDashboardSections(state);'),
        )

    def test_dashboard_reload_uses_product_cache_without_forced_refresh(self):
        script = dashboard_server.DASHBOARD_JAVASCRIPT
        self.assertIn('loadProducts(false).catch(() => {});', script)
        self.assertNotIn('loadProducts(true).catch(() => {});', script)

    def test_shift_history_always_includes_durable_scan_ledgers(self):
        script = dashboard_server.DASHBOARD_JAVASCRIPT
        self.assertNotIn('if(!clientRows.length){', script)
        self.assertIn('(item.product_pack_history_logs || [])', script)

    def test_single_shift_detail_hydrates_its_activity_time_window(self):
        detail = {
            "record_type": "SHIFT_PARTIAL",
            "machine_code": "M00005",
            "started_at_utc": "2026-11-03T10:44:45+00:00",
            "ended_at_utc": "2026-11-03T22:39:54+00:00",
            "client_app_logs": [
                {"timestamp_utc": "2026-11-03T10:45:00+00:00", "message": "embedded"}
            ],
        }
        stored = {
            "items": [
                {"timestamp_utc": "2026-11-03T12:00:00+00:00", "message": "stored"}
            ],
            "total": 1,
        }
        with patch.object(dashboard_server, "_load_history_detail_sql", return_value=detail):
            with patch.object(
                dashboard_server,
                "_same_job_partial_raw_material_totals",
                return_value={"rows": []},
            ):
                with patch.object(
                    dashboard_server,
                    "_load_machine_activity_logs_sql",
                    return_value=stored,
                ) as load_activity:
                    result = dashboard_server._finished_detail_with_prior_partials(
                        {}, include_activity=True
                    )
        self.assertEqual([row["message"] for row in result["client_app_logs"]], ["embedded", "stored"])
        self.assertEqual(result["client_app_logs_total"], 1)
        args = load_activity.call_args.args
        self.assertEqual(args[0], "M00005")
        self.assertEqual(args[2], "2026-11-03T10:44:45+00:00")
        self.assertEqual(args[3], "2026-11-03T22:40:54+00:00")

    def test_active_session_recovery_snapshot_uses_compact_lossless_json(self):
        source = (SERVER_DIR / "server.py").read_text(encoding="utf-8-sig")
        self.assertIn(
            'json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))',
            source,
        )

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
