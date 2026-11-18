import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


CLIENT_DIR = Path(__file__).resolve().parents[1] / "client"
sys.path.insert(0, str(CLIENT_DIR))

from client import ClientUI


class _Points:
    def __init__(self):
        self.total = 0

    def add_points(self, value):
        self.total += value


class ClientMultiplierVoidTests(unittest.TestCase):
    @staticmethod
    def _base_dummy(state):
        messages = []
        dummy = SimpleNamespace(
            state=state,
            status=SimpleNamespace(setText=messages.append),
            lblReject=_Points(),
            lblButal=_Points(),
            lblTotalGood=_Points(),
        )
        dummy._sync_machine_counter_current = lambda: None
        dummy._append_adjustment_log = lambda *args, **kwargs: None
        dummy.log_last = lambda *args, **kwargs: None
        dummy._format_reject_history_action_text = lambda *args, **kwargs: "reject"
        dummy._format_butal_history_action_text = lambda *args, **kwargs: "butal"
        dummy._operator_display_name = lambda value: str(value or "-")
        dummy._scan_owner_context = lambda: {}
        dummy._normalize_job_code = lambda value: str(value or "").strip().upper()
        dummy._reject_detail_bucket_code = lambda value: str(value or "").strip().upper()
        return dummy

    def test_reject_multiplier_void_keeps_all_rows_voided(self):
        state = SimpleNamespace(
            reject_review_logs=[
                {
                    "reject_scan_id": f"RS-{i}",
                    "entry_type": "REJECT_SCAN",
                    "reason_code": "BR",
                    "voided": False,
                }
                for i in range(4)
            ],
            reject_total=4,
            reject_breakdown={"BR": 4},
            startup_reject_total=0,
            no_shot_total=0,
            supervisor_review_actor_name="",
            supervisor_name="",
            operator_id="OP-1",
        )
        dummy = self._base_dummy(state)

        self.assertTrue(ClientUI._void_reject_scan(dummy, "BR", 3))
        self.assertEqual(state.reject_total, 1)
        self.assertEqual(state.reject_breakdown["BR"], 1)
        self.assertEqual(len(dummy._last_voided_reject_records), 3)
        self.assertEqual(sum(1 for row in state.reject_review_logs if row.get("voided")), 3)

    def test_counter_only_reject_recovery_honors_multiplier(self):
        state = SimpleNamespace(
            reject_review_logs=[],
            reject_total=5,
            reject_breakdown={"BR": 5},
            startup_reject_total=0,
            no_shot_total=0,
            supervisor_review_actor_name="",
            supervisor_name="",
            operator_id="OP-1",
        )
        dummy = self._base_dummy(state)

        self.assertTrue(ClientUI._void_reject_scan(dummy, "BR", 3))
        self.assertEqual(state.reject_total, 2)
        self.assertEqual(state.reject_breakdown["BR"], 2)
        self.assertEqual(len(dummy._last_voided_reject_records), 3)
        self.assertTrue(all(row.get("counter_only_recovery") for row in state.reject_review_logs))

    def test_butal_multiplier_void_keeps_all_rows_voided(self):
        state = SimpleNamespace(
            butal_scan_logs=[
                {
                    "raw_scan": "BUTAL~2",
                    "qty": 2,
                    "assigned_job_code": "JOB-1",
                    "scanned_at": f"2026-10-03T01:00:0{i}+00:00",
                    "voided": False,
                }
                for i in range(4)
            ],
            butal_total=8,
            butal_by_job={"JOB-1": 8},
        )
        dummy = self._base_dummy(state)

        self.assertTrue(ClientUI._void_butal_scan(dummy, "BUTAL~2", 2, 3))
        self.assertEqual(state.butal_total, 2)
        self.assertEqual(state.butal_by_job["JOB-1"], 2)
        self.assertEqual(len(dummy._last_voided_butal_records), 3)
        self.assertEqual(sum(1 for row in state.butal_scan_logs if row.get("voided")), 3)

    def test_product_part_void_requires_the_same_scanned_item(self):
        first_qr = "PACK~PART-A~LOT-1"
        second_qr = "PACK~PART-B~LOT-2"
        state = SimpleNamespace(
            raw_material_logs=[
                {
                    "raw_scan": first_qr,
                    "unique_key": "PART-A",
                    "material_name": "Part A",
                    "qty": 1,
                    "source": "OFFLINE_CONFIRMED_PRODUCT_PART",
                },
                {
                    "raw_scan": second_qr,
                    "unique_key": "PART-B",
                    "material_name": "Part B",
                    "qty": 1,
                    "source": "OFFLINE_CONFIRMED_PRODUCT_PART",
                },
            ],
            raw_material_unique_keys={"PART-A", "PART-B"},
            raw_material_scans=["Part A", "Part B"],
            raw_sacks_count=2,
        )
        dummy = self._base_dummy(state)
        dummy._recent_scan_seen = {first_qr: 1.0}

        self.assertFalse(ClientUI._void_product_part_scan(dummy, "PACK~OTHER~LOT-9"))
        self.assertEqual(state.raw_sacks_count, 2)
        self.assertEqual(len(state.raw_material_logs), 2)

        self.assertTrue(ClientUI._void_product_part_scan(dummy, first_qr))
        self.assertEqual(state.raw_sacks_count, 1)
        self.assertEqual([row["unique_key"] for row in state.raw_material_logs], ["PART-B"])
        self.assertEqual(state.raw_material_scans, ["Part B"])
        self.assertEqual(dummy._last_voided_product_part_record["unique_key"], "PART-A")
        self.assertNotIn(first_qr, dummy._recent_scan_seen)
        self.assertNotIn("PART-A", state.raw_material_unique_keys)


if __name__ == "__main__":
    unittest.main()
