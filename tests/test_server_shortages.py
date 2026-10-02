from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import server as dashboard_server


class DashboardPartShortageTests(unittest.TestCase):
    def setUp(self) -> None:
        dashboard_server._DASHBOARD_PART_SHORTAGE_CACHE.clear()

    @staticmethod
    def _machine_308_row() -> dict:
        return {
            "machine_code": "M00008",
            "production_session_id": "TEST-M308-REPLACEMENT",
            "job_code": "118174",
            "job_started_at": "2026-09-24T23:15:57+00:00",
            "job_payload": {
                "data": {
                    "job": {
                        "sku": "W-823-BODY",
                        "approve_qty": "3000.0000",
                        "request_qty": "3000.0000",
                    },
                    "job_details": {
                        "parts": [
                            {
                                "part_product_id": 13505,
                                "sku": "Z-RM-PP-R-MF28-KINGFA-KF-RP340R",
                                "name": "PP Random Copolymer China (25 KGS)",
                                "request_part_qty": "579.0000",
                                "approve_part_qty": "0.0000",
                            },
                            {
                                "part_product_id": 5516,
                                "sku": "Z-RM-PP-R-MF30SCN-TITAN-SM598",
                                "name": "Approved replacement resin (25 KGS)",
                                "request_part_qty": "0.0000",
                                "approve_part_qty": "579.0000",
                            },
                        ]
                    },
                }
            },
            "raw_material_logs": [],
            "product_pack_history_logs": [],
        }

    def test_approved_replacement_is_required_and_zero_approved_part_is_ignored(self) -> None:
        row = self._machine_308_row()
        row["product_pack_history_logs"] = [
            {
                "scanned_at": "2026-09-25T02:00:00+00:00",
                "raw_part_consumption": [
                    {
                        "product_id": 13505,
                        "sku": "Z-RM-PP-R-MF28-KINGFA-KF-RP340R",
                        "produced_units": 128,
                        "used_qty": 24.704,
                    },
                    {
                        "product_id": 5516,
                        "sku": "Z-RM-PP-R-MF30SCN-TITAN-SM598",
                        "produced_units": 128,
                        "used_qty": 24.704,
                    },
                ],
            }
        ]

        result = dashboard_server._dashboard_product_part_shortages(row)

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["names"], ["Z-RM-PP-R-MF30SCN-TITAN-SM598"])

    def test_standard_product_weight_uses_active_api_raw_material_allocation(self) -> None:
        row = self._machine_308_row()

        result = dashboard_server._dashboard_standard_product_weight(row)

        self.assertAlmostEqual(result["weight_kg"], 0.193)
        self.assertEqual(result["source"], "JOB_API")
        self.assertEqual(len(result["components"]), 1)
        self.assertEqual(
            result["components"][0]["sku"],
            "Z-RM-PP-R-MF30SCN-TITAN-SM598",
        )

    def test_assigned_part_without_consumption_is_not_short(self) -> None:
        row = self._machine_308_row()
        row["production_session_id"] = "TEST-M308-NO-DEMAND"

        result = dashboard_server._dashboard_product_part_shortages(row)

        self.assertEqual(result["count"], 0)
        self.assertEqual(result["names"], [])

    def test_same_job_partials_are_included_without_double_counting_carryover(self) -> None:
        row = self._machine_308_row()
        row["production_session_id"] = "TEST-M310-PARTIALS"
        replacement = "Z-RM-PP-R-MF30SCN-TITAN-SM598"
        row["prior_partial_raw_material_totals"] = {
            "partial_count": 4,
            "consumed_units": 0,
            "rows": [
                {
                    "material_product_id": 5516,
                    "material_sku": replacement,
                    "qty": 200,
                    "used_qty": 234.2630268,
                }
            ],
        }
        row["raw_material_logs"] = [
            {
                "product_id": 5516,
                "material_sku": replacement,
                "qty": 15.7369732,
                "source": "FINISH_SHIFT_PART_CARRYOVER",
            },
            {
                "product_id": 5516,
                "material_sku": replacement,
                "qty": 25,
                "source": "RAW_MATERIAL_QR",
            },
        ]
        row["product_pack_history_logs"] = [
            {
                "scanned_at": "2026-09-25T02:00:00+00:00",
                "raw_part_consumption": [
                    {
                        "product_id": 5516,
                        "sku": replacement,
                        "used_qty": 21.5556,
                    }
                ],
            }
        ]

        result = dashboard_server._dashboard_product_part_shortages(row)

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["names"], [replacement])
        self.assertAlmostEqual(result["details"][0]["scanned_qty"], 225.0)
        self.assertAlmostEqual(result["details"][0]["used_qty"], 255.818627)

    def test_replacement_with_enough_scanned_weight_is_not_short(self) -> None:
        row = self._machine_308_row()
        row["production_session_id"] = "TEST-M308-SUFFICIENT"
        row["raw_material_logs"] = [
            {
                "product_id": 5516,
                "sku": "Z-RM-PP-R-MF30SCN-TITAN-SM598",
                "qty": 50,
                "scanned_at": "2026-09-25T01:00:00+00:00",
            }
        ]
        row["product_pack_history_logs"] = [
            {
                "scanned_at": "2026-09-25T02:00:00+00:00",
                "raw_part_consumption": [
                    {
                        "product_id": 5516,
                        "sku": "Z-RM-PP-R-MF30SCN-TITAN-SM598",
                        "produced_units": 128,
                        "used_qty": 0,
                    }
                ],
            }
        ]

        result = dashboard_server._dashboard_product_part_shortages(row)

        self.assertEqual(result["count"], 0)
        self.assertEqual(result["names"], [])


class DashboardRecentPartialsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_finished_jobs = dashboard_server.FINISHED_JOBS
        dashboard_server._DASHBOARD_RECENT_PARTIALS_CACHE = (0.0, (), {})
        dashboard_server.FINISHED_JOBS = [
            {
                "record_type": "SHIFT_PARTIAL",
                "machine_code": "M00010",
                "job_code": "118623",
                "job_name": "3-26-1406-1",
                "operator_id": "26-00001",
                "finished_at_utc": "2026-09-24T08:00:00+00:00",
                "review_status": "APPROVED",
                "total_good": 100,
            },
            {
                "record_type": "FINISHED_JOB",
                "machine_code": "M00010",
                "job_code": "IGNORE-ME",
                "finished_at_utc": "2026-09-24T09:00:00+00:00",
            },
            {
                "record_type": "SHIFT_PARTIAL",
                "machine_code": "M00008",
                "job_code": "118174",
                "finished_at_utc": "2026-09-24T10:00:00+00:00",
                "review_status": "PENDING",
                "total_good": 128,
            },
            {
                "record_type": "SHIFT_PARTIAL",
                "machine_code": "M00010",
                "job_code": "118623",
                "job_name": "3-26-1406-1",
                "finished_at_utc": "2026-09-24T11:00:00+00:00",
                "review_status": "PENDING",
                "machine_counter_difference": 3,
                "total_good": 120,
            },
            {
                "record_type": "SHIFT_PARTIAL",
                "machine_code": "M00010",
                "job_code": "DIFFERENT-JOB",
                "job_name": "DIFFERENT-JOB",
                "finished_at_utc": "2026-09-24T12:00:00+00:00",
                "review_status": "PENDING",
                "total_good": 999,
            },
        ]

    def tearDown(self) -> None:
        dashboard_server.FINISHED_JOBS = self.original_finished_jobs
        dashboard_server._DASHBOARD_RECENT_PARTIALS_CACHE = (0.0, (), {})

    def test_recent_partials_match_current_job_and_are_newest_first(self) -> None:
        sessions = [
            {"machine_code": "M00010", "job_code": "118623", "job_name": "3-26-1406-1"},
            {"machine_code": "M00008", "job_code": "118174", "job_name": "3-26-1370"},
        ]
        grouped = dashboard_server._dashboard_recent_partials_by_machine(sessions, limit=2)

        self.assertEqual(set(grouped), {"M00008", "M00010"})
        self.assertEqual([row["total_good"] for row in grouped["M00010"]], [120, 100])
        self.assertNotIn(999, [row["total_good"] for row in grouped["M00010"]])
        self.assertEqual(grouped["M00010"][0]["machine_counter_difference"], 3)
        self.assertTrue(grouped["M00010"][0]["job_key"])

if __name__ == "__main__":
    unittest.main()
