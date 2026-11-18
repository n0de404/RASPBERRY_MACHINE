from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import server as dashboard_server


class CompactVoidEventTests(unittest.TestCase):
    @staticmethod
    def _session() -> dashboard_server.MachineSession:
        return dashboard_server.MachineSession(
            client_id="RPI-TEST",
            machine_code="M00014",
            machine_name="IMM 314",
            job_code="JOB-VOID",
            operator_id="26-00025",
        )

    def test_pack_void_removes_row_and_uses_post_void_totals(self):
        session = self._session()
        session.pack_total = 2
        session.good_total = 40
        session.product_pack_history_logs = [
            {"pack_key": "PACK-A", "raw_scan": "A", "qty_q": 20},
            {"pack_key": "PACK-B", "raw_scan": "B", "qty_q": 20},
        ]

        dashboard_server._apply_pack_void_event(
            session,
            {
                "void_record": {"pack_key": "PACK-B", "raw_scan": "B", "qty_q": 20},
                "post_pack_total": 1,
                "post_good_total": 20,
            },
        )

        self.assertEqual(session.pack_total, 1)
        self.assertEqual(session.good_total, 20)
        self.assertEqual([row["pack_key"] for row in session.product_pack_history_logs], ["PACK-A"])

    def test_product_part_void_removes_only_matching_row(self):
        session = self._session()
        session.raw_sacks_count = 2
        session.raw_material_scans = ["Part A", "Part B"]
        session.raw_material_logs = [
            {"unique_key": "PART-A", "raw_scan": "A"},
            {"unique_key": "PART-B", "raw_scan": "B"},
        ]

        dashboard_server._apply_product_part_void_event(
            session,
            {
                "void_record": {"unique_key": "PART-B", "raw_scan": "B"},
                "post_raw_sacks_count": 1,
                "post_raw_material_scans": ["Part A"],
            },
        )

        self.assertEqual(session.raw_sacks_count, 1)
        self.assertEqual(session.raw_material_scans, ["Part A"])
        self.assertEqual([row["unique_key"] for row in session.raw_material_logs], ["PART-A"])

    def test_butal_void_marks_audit_row_and_uses_post_void_total(self):
        session = self._session()
        session.butal_total = 12
        session.butal_by_job = {"JOB-VOID": 12}
        session.butal_scan_logs = [
            {"raw_scan": "BUTAL~12", "qty": 12, "scanned_at": "2026-10-03T01:00:00+00:00", "voided": False}
        ]

        dashboard_server._apply_butal_void_event(
            session,
            {
                "void_record": {
                    "raw_scan": "BUTAL~12",
                    "qty": 12,
                    "scanned_at": "2026-10-03T01:00:00+00:00",
                    "voided_at": "2026-10-03T01:01:00+00:00",
                },
                "post_butal_total": 0,
                "post_butal_by_job": {},
            },
        )

        self.assertEqual(session.butal_total, 0)
        self.assertEqual(session.butal_by_job, {})
        self.assertTrue(session.butal_scan_logs[0]["voided"])

    def test_butal_multiplier_void_marks_every_row(self):
        session = self._session()
        session.butal_total = 5
        session.butal_scan_logs = [
            {"raw_scan": "BUTAL~1", "qty": 1, "scanned_at": f"2026-10-03T01:00:0{i}+00:00", "voided": False}
            for i in range(5)
        ]
        voided = [
            {**session.butal_scan_logs[i], "voided": True, "voided_at": "2026-10-03T01:01:00+00:00"}
            for i in range(2, 5)
        ]

        dashboard_server._apply_butal_void_event(
            session,
            {
                "void_records": voided,
                "void_count": 3,
                "post_butal_total": 2,
                "post_butal_by_job": {},
            },
        )

        self.assertEqual(session.butal_total, 2)
        self.assertEqual(sum(1 for row in session.butal_scan_logs if row.get("voided")), 3)

    def test_reject_multiplier_void_applies_all_rows_and_post_totals(self):
        session = self._session()
        session.reject_total = 5
        session.reject_breakdown = {"BR": 5}
        session.reject_review_logs = [
            {
                "reject_scan_id": f"RS-{i}",
                "entry_type": "REJECT_SCAN",
                "reason_code": "BR",
                "voided": False,
            }
            for i in range(5)
        ]
        voided = [
            {**session.reject_review_logs[i], "voided": True, "voided_at": "2026-10-03T01:01:00+00:00"}
            for i in range(2, 5)
        ]

        applied = dashboard_server._apply_reject_void_event(
            session,
            {
                "reason": "BR",
                "void_records": voided,
                "void_count": 3,
                "post_reject_total": 2,
                "post_startup_reject_total": 0,
                "post_no_shot_total": 0,
                "post_reject_breakdown": {"BR": 2},
            },
        )

        self.assertTrue(applied)
        self.assertEqual(session.reject_total, 2)
        self.assertEqual(session.reject_breakdown["BR"], 2)
        self.assertEqual(sum(1 for row in session.reject_review_logs if row.get("voided")), 3)

    def test_parked_color_mold_session_can_be_resumed_by_session_id(self):
        session = self._session()
        session.color_mold_sessions = {
            "JOB-RED": {
                "job_code": "JOB-RED",
                "production_session_id": "PS-RED",
            }
        }

        self.assertTrue(dashboard_server._is_parked_color_mold_session(session, "PS-RED"))
        self.assertFalse(dashboard_server._is_parked_color_mold_session(session, "PS-UNKNOWN"))

        session.production_session_id = "PS-BLUE"
        session.color_mold_group_id = "CMG-1"
        switch_snapshot = {
            "production_session_id": "PS-RED",
            "color_mold_group_id": "CMG-1",
            "color_mold_sessions": {
                "JOB-BLUE": {"production_session_id": "PS-BLUE"}
            },
        }
        self.assertTrue(
            dashboard_server._color_mold_snapshot_can_switch(session, switch_snapshot, "PS-RED")
        )

    def test_color_mold_snapshot_fields_survive_server_restore(self):
        restored = dashboard_server._session_from_active_snapshot({
            "client_id": "RPI-TEST",
            "machine_code": "M00014",
            "machine_name": "IMM 314",
            "job_code": "JOB-BLUE",
            "production_session_id": "PS-BLUE",
            "color_mold_group_id": "CMG-1",
            "color_mold_sessions": {
                "JOB-RED": {"job_code": "JOB-RED", "production_session_id": "PS-RED"}
            },
            "change_supervisor_code": "SUP-1",
            "change_supervisor_name": "Supervisor One",
            "change_supervisor_owners": [{"code": "SUP-1", "name": "Supervisor One"}],
        })

        self.assertIsNotNone(restored)
        snapshot = restored.to_dict()
        self.assertEqual(snapshot["color_mold_group_id"], "CMG-1")
        self.assertEqual(snapshot["color_mold_sessions"]["JOB-RED"]["production_session_id"], "PS-RED")
        self.assertEqual(snapshot["change_supervisor_owners"][0]["code"], "SUP-1")

    def test_job_linkage_removal_uses_exact_client_remainder(self):
        session = self._session()
        session.linkage_enabled = True
        session.linkage_job_code = "JOB-300"
        session.linkage_job_name = "Green Cover"
        session.linkage_job_payload = {"id": 300}
        session.linkage_jobs = [
            {"job_code": "JOB-200", "job_name": "Blue Cover", "job_payload": {"id": 200}},
            {"job_code": "JOB-300", "job_name": "Green Cover", "job_payload": {"id": 300}},
        ]

        dashboard_server._apply_job_linkage_removed_event(
            session,
            {
                "removed_job_code": "JOB-300",
                "post_linkage_enabled": True,
                "post_linkage_jobs": [
                    {"job_code": "JOB-200", "job_name": "Blue Cover", "job_payload": {"id": 200}}
                ],
                "post_linkage_job_code": "JOB-200",
                "post_linkage_job_name": "Blue Cover",
                "post_linkage_job_payload": {"id": 200},
            },
        )

        self.assertTrue(session.linkage_enabled)
        self.assertEqual([row["job_code"] for row in session.linkage_jobs], ["JOB-200"])
        self.assertEqual(session.linkage_job_code, "JOB-200")
        self.assertEqual(session.linkage_job_payload, {"id": 200})


if __name__ == "__main__":
    unittest.main()
