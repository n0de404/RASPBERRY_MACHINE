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


if __name__ == "__main__":
    unittest.main()
