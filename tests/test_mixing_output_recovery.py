import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLIENT_DIR = os.path.join(ROOT, "client")
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

import mixing_client


class MixingOutputRecoveryTests(unittest.TestCase):
    @staticmethod
    def _client():
        client = mixing_client.MixingClientUI.__new__(mixing_client.MixingClientUI)
        client._parse_number = mixing_client.MixingClientUI._parse_number.__get__(client)
        return client

    def test_zero_legacy_totals_are_rebuilt_from_unique_sack_history(self):
        client = self._client()
        snapshot = {
            "pack_count": 0,
            "good_total": 0,
            "product_pack_history_logs": [
                {"pack_key": "SACK-1", "good_qty": 25.5},
                {"pack_key": "SACK-2", "qty_q": 25.5},
                {"pack_key": "SACK-2", "qty_q": 25.5},
            ],
        }

        recovered = client._repair_mixing_output_totals(snapshot)

        self.assertEqual(recovered["pack_count"], 2)
        self.assertEqual(recovered["mixing_sack_count"], 2)
        self.assertEqual(recovered["good_total"], 51.0)
        self.assertEqual(recovered["mixing_total_kg"], 51.0)

    def test_existing_nonzero_totals_remain_authoritative(self):
        client = self._client()
        snapshot = {
            "pack_count": 7,
            "good_total": 175,
            "product_pack_history_logs": [
                {"pack_key": "SACK-1", "good_qty": 25},
            ],
        }

        recovered = client._repair_mixing_output_totals(snapshot)

        self.assertEqual(recovered["pack_count"], 7)
        self.assertEqual(recovered["good_total"], 175)

    def test_nested_open_job_totals_are_imported_from_server(self):
        client = self._client()
        client._mixing_sessions = {}
        client._mixing_active_job_key = ""
        client._mixing_active_jobs_by_machine = {}
        client._persist_mixing_sessions = MagicMock()
        snapshot = {
            "machine_code": "MT-302",
            "job_code": "120741",
            "job_name": "MX3-26-1547-1",
            "pack_total": 0,
            "good_total": 0,
            "mixing_open_jobs": [
                {
                    "job_code": "120741",
                    "job_name": "MX3-26-1547-1",
                    "pack_count": 0,
                    "good_total": 0,
                },
                {
                    "job_code": "121332",
                    "job_name": "MX3-26-1562-3",
                    "pack_count": 14,
                    "mixing_sack_count": 14,
                    "good_total": 657.0,
                    "mixing_total_kg": 657.0,
                },
            ],
        }

        client._ingest_server_mixing_open_jobs(snapshot)

        recovered = client._mixing_sessions["MT-302|121332"]
        self.assertEqual(recovered["pack_count"], 14)
        self.assertEqual(recovered["mixing_sack_count"], 14)
        self.assertEqual(recovered["good_total"], 657.0)
        self.assertEqual(recovered["mixing_total_kg"], 657.0)

    def test_cards_add_prior_shift_output_without_mutating_live_state(self):
        client = self._client()
        client.state = SimpleNamespace(
            machine_code="MT-302",
            job_code="120741",
            job_name="MX3-26-1547-1",
            pack_count=0,
            good_total=0.0,
            butal_total=0.0,
        )
        client._mixing_prior_output_totals = MagicMock(
            return_value={"sacks": 5, "good_kg": 125.0, "total_kg": 125.0}
        )
        client.lblPack = MagicMock()
        client.lblGood = MagicMock()
        client.lblTotalGood = MagicMock()

        client._refresh_mixing_output_cards()

        client.lblPack.set_value.assert_called_once_with(5)
        client.lblGood.set_value.assert_called_once_with(125.0)
        client.lblTotalGood.set_value.assert_called_once_with(125.0)
        self.assertEqual(client.state.pack_count, 0)
        self.assertEqual(client.state.good_total, 0.0)


if __name__ == "__main__":
    unittest.main()
