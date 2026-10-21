import sys
import unittest
from pathlib import Path


CLIENT_DIR = Path(__file__).resolve().parents[1] / "client"
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

import mixing_client


class _RequestBuilder:
    @staticmethod
    def _parse_number(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0


class MixingPartialRequestTests(unittest.TestCase):
    def test_partial_qty_uses_produced_total_not_kg_counter_delta(self):
        payload = {
            "job_payload": {"data": {"job": {"id": 120625}}},
            "job_code": "120625",
            "job_name": "MX1-26-9999",
            "machine_code": "MT-302",
            "shift_index": 1,
            "partial_qty": 75,
            "total_good": 75,
            "good_total": 75,
            "mixing_kg_produced_shift": 999,
            "mixing_kg_counter_start": 10,
            "mixing_kg_counter_end": 1009,
            "mixing_cumulative_part_totals": [
                {"part_product_id": 9241, "part_qty_per_unit": 0.9785}
            ],
        }

        request = mixing_client.MixingClientUI._build_mixing_partial_api_request(
            _RequestBuilder(), payload, "Femelyn Valmas"
        )

        self.assertEqual(request["body"]["partial_qty"], 75.0)
        self.assertEqual(request["body"]["partial_by"], 11)
        self.assertEqual(request["body"]["partial_by_name"], "API INTEGRATION")
        self.assertEqual(request["body"]["partial_part_qty"], [73.3875])

    def test_old_payload_can_fall_back_to_mixing_shift_kg(self):
        payload = {
            "job_payload": {"data": {"job": {"id": 120625}}},
            "mixing_kg_produced_shift": 50,
        }

        request = mixing_client.MixingClientUI._build_mixing_partial_api_request(
            _RequestBuilder(), payload
        )

        self.assertEqual(request["body"]["partial_qty"], 50.0)
        self.assertEqual(request["body"]["partial_by"], 11)
        self.assertEqual(request["body"]["partial_by_name"], "API INTEGRATION")


if __name__ == "__main__":
    unittest.main()
