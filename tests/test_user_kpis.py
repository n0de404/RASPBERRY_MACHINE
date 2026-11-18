from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import server as dashboard_server


class UserKpiPeopleCardTests(unittest.TestCase):
    def test_all_roles_include_department_and_role_aware_activity(self):
        profiles = [
            {"id_number": "OP-1", "name": "Operator One", "role": "Operator", "department": "Production"},
            {"id_number": "MT-1", "name": "Tech One", "role": "Maintenance", "department": "Engineering"},
            {"id_number": "PL-1", "name": "Planner One", "role": "Planner", "department": "Planning"},
        ]
        history = [
            {
                "machine_code": "M1", "job_code": "J1", "operator_id": "OP-1 - Operator One",
                "finished_at_utc": "2026-10-12T00:00:00+00:00", "raw_material_logs": [{}],
                "product_pack_history_logs": [{}], "pack_count": 1,
            },
            {
                "machine_code": "M2", "job_code": "J2", "maintenance_name": "MT-1 - Tech One",
                "finished_at_utc": "2026-10-12T01:00:00+00:00",
            },
        ]
        with patch.object(dashboard_server, "PROFILES", profiles), \
             patch.object(dashboard_server, "FINISHED_JOBS", history), \
             patch.object(dashboard_server, "ARCHIVED_JOBS", []), \
             patch.object(dashboard_server, "SESSIONS", {}):
            payload = dashboard_server.build_user_kpis("all")

        by_id = {row["id_number"]: row for row in payload["items"]}
        self.assertEqual(set(by_id), {"OP-1", "MT-1", "PL-1"})
        self.assertEqual(by_id["OP-1"]["department"], "Production")
        self.assertEqual(by_id["OP-1"]["activity_records"], 1)
        self.assertEqual(by_id["MT-1"]["activity_records"], 1)
        self.assertIsNone(by_id["MT-1"]["kpi_rating_percent"])
        self.assertEqual(by_id["MT-1"]["rating_band"], "BUILDING DATA")
        self.assertEqual(by_id["MT-1"]["rating_confidence"], "LOW")
        self.assertIsNone(by_id["PL-1"]["kpi_rating_percent"])

    def test_operator_rating_uses_five_equal_components(self):
        profiles = [{"id_number": "OP-1", "name": "Operator One", "role": "Operator"}]
        history = []
        for index in range(10):
            history.append({
                "machine_code": "M1",
                "job_code": f"J{index}",
                "operator_id": "OP-1 - Operator One",
                "finished_at_utc": f"2026-10-{index + 1:02d}T00:00:00+00:00",
                "raw_material_logs": [] if index < 9 else [{}],
                "product_pack_history_logs": [],
                "pack_count": 0,
            })
        with patch.object(dashboard_server, "PROFILES", profiles), \
             patch.object(dashboard_server, "FINISHED_JOBS", history), \
             patch.object(dashboard_server, "ARCHIVED_JOBS", []), \
             patch.object(dashboard_server, "SESSIONS", {}):
            row = dashboard_server.build_user_kpis("all")["items"][0]

        self.assertEqual(row["activity_records"], 10)
        self.assertEqual(row["follow_up_rate_percent"], 90.0)
        self.assertEqual(row["kpi_rating_percent"], 82.0)
        self.assertEqual(row["rating_band"], "STRONG")
        self.assertEqual(row["rating_confidence"], "MEDIUM")
        self.assertEqual(len(row["rating_components"]), 5)
        self.assertEqual([component["weight_percent"] for component in row["rating_components"]], [20.0] * 5)
        self.assertEqual(
            [component["key"] for component in row["rating_components"]],
            ["reject_scan", "scan_accuracy", "jobs_closed", "materials_parts", "pack_qr"],
        )

    def test_operator_rating_shows_below_ten_activities_with_low_confidence(self):
        profiles = [{"id_number": "OP-1", "name": "Operator One", "role": "Operator"}]
        history = [{
            "machine_code": "M1", "job_code": "J1", "operator_id": "OP-1 - Operator One",
            "finished_at_utc": "2026-10-12T00:00:00+00:00", "raw_material_logs": [{}],
            "product_pack_history_logs": [{}], "pack_count": 1,
        }]
        with patch.object(dashboard_server, "PROFILES", profiles), \
             patch.object(dashboard_server, "FINISHED_JOBS", history), \
             patch.object(dashboard_server, "ARCHIVED_JOBS", []), \
             patch.object(dashboard_server, "SESSIONS", {}), \
             patch.object(dashboard_server, "PLANNING_QUEUE_ALERTS", {}):
            row = dashboard_server.build_user_kpis("operator")["items"][0]

        self.assertEqual(row["activity_records"], 1)
        self.assertEqual(row["kpi_rating_percent"], 100.0)
        self.assertEqual(row["rating_confidence"], "LOW")
        self.assertEqual(row["minimum_activity_required"], 1)

    def test_maintenance_rating_uses_availability_response_and_repair_time(self):
        profiles = [{"id_number": "MT-1", "name": "Tech One", "role": "Maintenance"}]
        history = []
        for index in range(3):
            history.append({
                "machine_code": f"M{index}",
                "job_code": f"J{index}",
                "maintenance_name": "MT-1 - Tech One",
                "finished_at_utc": f"2026-10-{index + 1:02d}T00:00:00+00:00",
                "pdr_downtime_logs": [{
                    "maintenance": "MT-1 - Tech One",
                    "waiting_seconds": 120,
                    "duration_seconds": 600,
                }],
            })
        with patch.object(dashboard_server, "PROFILES", profiles), \
             patch.object(dashboard_server, "FINISHED_JOBS", history), \
             patch.object(dashboard_server, "ARCHIVED_JOBS", []), \
             patch.object(dashboard_server, "SESSIONS", {}), \
             patch.object(dashboard_server, "PLANNING_QUEUE_ALERTS", {}):
            row = dashboard_server.build_user_kpis("maintenance")["items"][0]

        self.assertEqual(row["kpi_rating_percent"], 100.0)
        self.assertEqual([component["weight_percent"] for component in row["rating_components"]], [10.0, 45.0, 45.0])

    def test_maintenance_rating_ignores_legacy_text_null_durations(self):
        profiles = [{"id_number": "MT-1", "name": "Tech One", "role": "Maintenance"}]
        history = [{
            "machine_code": "M1", "job_code": "J1", "maintenance_name": "MT-1 - Tech One",
            "finished_at_utc": "2026-10-12T01:00:00+00:00",
            "pdr_downtime_logs": [{
                "maintenance": "MT-1 - Tech One", "waiting_seconds": "null", "duration_seconds": "null",
            }],
        }]
        with patch.object(dashboard_server, "PROFILES", profiles), \
             patch.object(dashboard_server, "FINISHED_JOBS", history), \
             patch.object(dashboard_server, "ARCHIVED_JOBS", []), \
             patch.object(dashboard_server, "SESSIONS", {}), \
             patch.object(dashboard_server, "PLANNING_QUEUE_ALERTS", {}):
            row = dashboard_server.build_user_kpis("maintenance")["items"][0]

        self.assertIsNone(row["kpi_rating_percent"])
        self.assertEqual(row["rating_band"], "BUILDING DATA")

    def test_maintenance_role_filter_excludes_other_profiles(self):
        profiles = [
            {"id_number": "OP-1", "name": "Operator One", "role": "Operator"},
            {"id_number": "MT-1", "name": "Tech One", "role": "Maintenance"},
        ]
        with patch.object(dashboard_server, "PROFILES", profiles), \
             patch.object(dashboard_server, "FINISHED_JOBS", []), \
             patch.object(dashboard_server, "ARCHIVED_JOBS", []), \
             patch.object(dashboard_server, "SESSIONS", {}):
            payload = dashboard_server.build_user_kpis("maintenance")

        self.assertEqual([row["id_number"] for row in payload["items"]], ["MT-1"])

    def test_summary_payload_keeps_cards_but_defers_heavy_details(self):
        profiles = [{"id_number": "OP-1", "name": "Operator One", "role": "Operator"}]
        history = [{
            "machine_code": "M1", "job_code": "J1", "operator_id": "OP-1 - Operator One",
            "finished_at_utc": "2026-10-12T00:00:00+00:00", "raw_material_logs": [{}],
            "product_pack_history_logs": [{}], "pack_count": 1,
        }]
        with patch.object(dashboard_server, "PROFILES", profiles), \
             patch.object(dashboard_server, "FINISHED_JOBS", history), \
             patch.object(dashboard_server, "ARCHIVED_JOBS", []), \
             patch.object(dashboard_server, "SESSIONS", {}), \
             patch.object(dashboard_server, "PLANNING_QUEUE_ALERTS", {}):
            summary = dashboard_server.build_user_kpis("all", include_details=False)["items"][0]
            detail = dashboard_server.build_user_kpis("all", profile_id="OP-1", include_details=True)["items"][0]

        for key in ("id_number", "name", "role", "kpi_rating_percent", "missed_breakdown"):
            self.assertEqual(summary[key], detail[key])
        self.assertNotIn("handled_jobs", summary)
        self.assertNotIn("issues", summary)
        self.assertNotIn("rating_components", summary)
        self.assertIn("handled_jobs", detail)
        self.assertIn("issues", detail)
        self.assertIn("rating_components", detail)

    def test_kpi_cache_reuses_snapshot_and_force_refreshes(self):
        dashboard_server.USER_KPI_CACHE.clear()
        payloads = [
            {"items": [{"id_number": "A"}]},
            {"items": [{"id_number": "B"}]},
        ]
        with patch.object(dashboard_server, "build_user_kpis", side_effect=payloads) as builder:
            first = dashboard_server._cached_user_kpis("all")
            second = dashboard_server._cached_user_kpis("all")
            forced = dashboard_server._cached_user_kpis("all", force=True)

        self.assertIs(first, second)
        self.assertEqual(first["items"][0]["id_number"], "A")
        self.assertEqual(forced["items"][0]["id_number"], "B")
        self.assertEqual(builder.call_count, 2)
        dashboard_server.USER_KPI_CACHE.clear()

    def test_qc_loader_and_planner_use_their_own_role_components(self):
        profiles = [
            {"id_number": "QC-1", "name": "Quality One", "role": "QA/QC"},
            {"id_number": "ML-1", "name": "Loader One", "role": "Material Loader"},
            {"id_number": "PL-1", "name": "Planner One", "role": "Planner"},
        ]
        history = []
        for index in range(5):
            history.extend([
                {
                    "machine_code": f"Q{index}", "job_code": f"QJ{index}",
                    "started_at_utc": f"2026-10-{index + 1:02d}T00:00:00+00:00",
                    "finished_at_utc": f"2026-10-{index + 1:02d}T02:00:00+00:00",
                    "external_average_weight_received_at": f"2026-10-{index + 1:02d}T01:00:00+00:00",
                    "external_average_weight_sender": "QC-1 - Quality One",
                },
                {
                    "machine_code": f"L{index}", "job_code": f"LJ{index}",
                    "finished_at_utc": f"2026-10-{index + 1:02d}T03:00:00+00:00",
                    "material_loader": "ML-1 - Loader One",
                    "raw_material_logs": [{}],
                    "raw_consumption_pending": False,
                },
            ])
        board = {"lanes": {"M1": [
            {"id": f"P{index}", "planner_id": "PL-1", "mismatch": False}
            for index in range(5)
        ]}}
        with patch.object(dashboard_server, "PROFILES", profiles), \
             patch.object(dashboard_server, "FINISHED_JOBS", history), \
             patch.object(dashboard_server, "ARCHIVED_JOBS", []), \
             patch.object(dashboard_server, "SESSIONS", {}), \
             patch.object(dashboard_server, "PLANNING_BOARD", board), \
             patch.object(dashboard_server, "PLANNING_QUEUE_ALERTS", {}):
            rows = {row["id_number"]: row for row in dashboard_server.build_user_kpis("all")["items"]}

        self.assertEqual(rows["QC-1"]["kpi_rating_percent"], 100.0)
        self.assertEqual(rows["ML-1"]["kpi_rating_percent"], 100.0)
        self.assertEqual(rows["PL-1"]["kpi_rating_percent"], 100.0)
        self.assertEqual(len(rows["QC-1"]["rating_components"]), 5)
        self.assertEqual([c["weight_percent"] for c in rows["ML-1"]["rating_components"]], [50.0, 50.0])
        self.assertEqual([c["weight_percent"] for c in rows["PL-1"]["rating_components"]], [50.0, 50.0])

    def test_dashboard_defaults_to_all_people_and_never_infers_break_from_kpis(self):
        script = dashboard_server.DASHBOARD_JAVASCRIPT
        self.assertIn('let userKpiRoleState = "all";', script)
        self.assertIn('row?.department || "Department not set"', script)
        self.assertNotIn('label: "STATUS: ON BREAK"', script)
        self.assertIn('label: "BUILDING DATA"', script)
        self.assertNotIn('RATING: NEEDS REVIEW', script)
        self.assertIn('data-target="userKpiTab">Production Cards<span', dashboard_server.DASHBOARD_HTML)
        self.assertNotIn('>User KPIs<', dashboard_server.DASHBOARD_HTML)
        self.assertIn('.user-kpi-card-grid { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); justify-content:start;', dashboard_server.DASHBOARD_HTML)
        self.assertIn('id="userKpiThemeBtn"', dashboard_server.DASHBOARD_HTML)
        self.assertIn('id="userKpiDateBtn"', dashboard_server.DASHBOARD_HTML)
        self.assertIn('id="productionCardsNotifBadge"', dashboard_server.DASHBOARD_HTML)
        self.assertIn('availability-overbreak', script)
        self.assertIn('/api/user-kpis/${encodeURIComponent(row.id_number || "")}', script)
        self.assertIn('loadUserKpis(userKpiRoleState, true)', script)

    def test_breaktime_public_profile_exposes_only_allowed_fields(self):
        profile = {
            "id_number": "OP-9", "name": "Operator Nine", "role": "Operator",
            "department": "Production", "photo_data_url": "secret-photo", "print_count": 4,
        }
        self.assertEqual(
            dashboard_server._breaktime_public_profile(profile),
            {"name": "Operator Nine", "id_number": "OP-9", "role": "Operator", "department": "Production"},
        )

    def test_breaktime_status_overrides_local_availability_only_during_break(self):
        profile = {"id_number": "OP-9", "name": "Operator Nine", "role": "Operator"}
        active = SimpleNamespace(operator_id="OP-9 - Operator Nine", reliever_id="")
        with patch.object(dashboard_server, "SESSIONS", {"M1": active}), \
             patch.object(dashboard_server, "BREAKTIME_STATE", {"statuses": {}, "notifications": [], "revision": 0}):
            self.assertEqual(dashboard_server._breaktime_profile_status(profile)["availability_status"], "AVAILABLE")
            dashboard_server.BREAKTIME_STATE["statuses"]["OP-9"] = {
                "status": "ON_BREAK", "status_since_utc": "2026-10-12T00:00:00+00:00"
            }
            self.assertEqual(dashboard_server._breaktime_profile_status(profile)["availability_status"], "ON_BREAK")
            dashboard_server.BREAKTIME_STATE["statuses"]["OP-9"]["status"] = "OVERBREAK"
            self.assertEqual(dashboard_server._breaktime_profile_status(profile)["availability_status"], "OVERBREAK")

    def test_production_card_activity_identifies_role_and_machine(self):
        active_rows = [
            {
                "machine_code": "M00002", "machine_name": "IMM 302", "operator_id": "OP-1 - Operator",
                "last_seen_utc": "2026-10-13T01:00:00+00:00", "break_active": True,
                "reliever_id": "OP-2 - Reliever", "downtime_active": True,
                "maintenance_name": "MT-1 - Technician", "downtime_started_at": 1791853200,
                "downtime_reason_text": "Hydraulic leak",
                "external_average_weight_sender": "QC-1 - Quality", "external_average_weight_received_at": "2026-10-13T01:05:00+00:00",
                "material_loader_name": "ML-1 - Loader",
                "raw_material_logs": [{"material_sku": "Z-RM-001", "scanned_at": "2026-10-13T01:06:00+00:00"}],
                "supervisor_rotation_logs": [{
                    "supervisor_code": "SV-1", "supervisor_name": "Supervisor",
                    "checked_at_utc": "2026-10-13T01:07:00+00:00",
                }],
                "supervisor_review_logs": [],
            }
        ]
        availability = {"availability_status": "AVAILABLE"}

        reliever = dashboard_server._kpi_presence_status(
            {"id_number": "OP-2", "name": "Reliever", "role": "Operator"}, active_rows, [], availability
        )
        with patch.object(dashboard_server, "utc_now", return_value=datetime(2026, 10, 13, 2, 0, tzinfo=timezone.utc)):
            supervisor = dashboard_server._kpi_presence_status(
                {"id_number": "SV-1", "name": "Supervisor", "role": "Supervisor"}, active_rows, [], availability
            )
        with patch.object(dashboard_server, "utc_now", return_value=datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)):
            supervisor_next_shift = dashboard_server._kpi_presence_status(
                {"id_number": "SV-1", "name": "Supervisor", "role": "Supervisor"}, active_rows, [], availability
            )
        qc = dashboard_server._kpi_presence_status(
            {"id_number": "QC-1", "name": "Quality", "role": "QA/QC"}, active_rows, [], availability
        )
        loader = dashboard_server._kpi_presence_status(
            {"id_number": "ML-1", "name": "Loader", "role": "Material Loader"}, active_rows, [], availability
        )
        maintenance = dashboard_server._kpi_presence_status(
            {"id_number": "MT-1", "name": "Technician", "role": "Maintenance"}, active_rows, [], availability
        )

        self.assertEqual(reliever["activity_label"], "Reliever on IMM 302")
        self.assertEqual(supervisor["activity_status"], "ONLINE")
        self.assertEqual(supervisor["activity_label"], "Online on IMM 302")
        self.assertEqual(supervisor["activity_detail"], "Rotation check this shift on IMM 302")
        self.assertEqual(supervisor_next_shift["activity_status"], "OFFLINE")
        self.assertEqual(supervisor_next_shift["activity_detail"], "Last rotation check on IMM 302")
        self.assertEqual(qc["activity_detail"], "Last weight sent to IMM 302")
        self.assertEqual(loader["activity_detail"], "Last Z-RM scan on IMM 302")
        self.assertEqual(maintenance["activity_label"], "Fixing downtime on IMM 302")


if __name__ == "__main__":
    unittest.main()
