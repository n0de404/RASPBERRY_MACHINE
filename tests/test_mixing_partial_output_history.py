import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import server as dashboard_server


class MixingPartialOutputHistoryTests(unittest.TestCase):
    def test_prior_partial_returns_sacks_and_kg(self):
        partial = {
            "record_type": "SHIFT_PARTIAL",
            "machine_code": "MT-302",
            "job_code": "120741",
            "finished_at_utc": "2026-10-17T19:07:44+00:00",
            "pack_count": 5,
            "good_total": 125,
            "butal_total": 0,
        }
        with patch.object(dashboard_server, "FINISHED_JOBS", [partial]), patch.object(
            dashboard_server, "_load_history_detail_sql", side_effect=lambda row: dict(row)
        ):
            totals = dashboard_server._same_job_partial_raw_material_totals(
                {"machine_code": "MT-302", "job_code": "120741"}
            )

        self.assertEqual(totals["output_sacks"], 5)
        self.assertEqual(totals["output_good_kg"], 125.0)
        self.assertEqual(totals["output_total_kg"], 125.0)


if __name__ == "__main__":
    unittest.main()
