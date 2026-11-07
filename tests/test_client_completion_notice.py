import sys
import unittest
from pathlib import Path
from unittest.mock import patch


CLIENT_DIR = Path(__file__).resolve().parents[1] / "client"
sys.path.insert(0, str(CLIENT_DIR))

import client as client_module
from client import ClientUI, _completion_pack_projection


class CompletionPackProjectionTests(unittest.TestCase):
    def test_three_exact_packs_remain_after_scan(self):
        result = _completion_pack_projection(4000, 3925, 25)

        self.assertEqual(result["remaining_qty"], 75)
        self.assertEqual(result["packs_remaining"], 3)
        self.assertEqual(result["projected_total"], 4000)
        self.assertEqual(result["projected_overrun"], 0)

    def test_whole_pack_projection_allows_final_overrun(self):
        before_scan = _completion_pack_projection(4000, 3900, 30)
        after_scan = _completion_pack_projection(4000, 3930, 30)

        self.assertEqual(before_scan["packs_remaining"], 4)
        self.assertEqual(after_scan["packs_remaining"], 3)
        self.assertEqual(after_scan["projected_total"], 4020)
        self.assertEqual(after_scan["projected_overrun"], 20)

    def test_fulfilled_job_has_no_remaining_packs(self):
        result = _completion_pack_projection(4000, 4020, 30)

        self.assertEqual(result["remaining_qty"], 0)
        self.assertEqual(result["packs_remaining"], 0)
        self.assertEqual(result["projected_overrun"], 20)


class StartupCompletionFenceTests(unittest.TestCase):
    def test_approved_partial_shift_does_not_close_production_session(self):
        partial = {
            "record_type": "SHIFT_PARTIAL",
            "review_status": "APPROVED",
            "production_session_id": "PS-ACTIVE",
        }
        with patch.object(client_module, "_load_finish_shift_json", return_value=[partial]), patch.object(
            client_module, "_load_finished_jobs_json", return_value=[]
        ):
            self.assertEqual(ClientUI._locally_completed_session_ids(object()), set())

    def test_approved_finished_job_closes_production_session(self):
        finished = {
            "record_type": "FINISHED_JOB",
            "review_status": "APPROVED",
            "production_session_id": "PS-CLOSED",
        }
        with patch.object(client_module, "_load_finish_shift_json", return_value=[]), patch.object(
            client_module, "_load_finished_jobs_json", return_value=[finished]
        ):
            self.assertEqual(ClientUI._locally_completed_session_ids(object()), {"PS-CLOSED"})

    def test_missing_pack_quantity_cannot_make_projection(self):
        result = _completion_pack_projection(4000, 3900, 0)

        self.assertEqual(result["remaining_qty"], 100)
        self.assertEqual(result["packs_remaining"], 0)


if __name__ == "__main__":
    unittest.main()
