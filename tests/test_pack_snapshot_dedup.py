from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import server as dashboard_server


class PackSnapshotDedupTests(unittest.TestCase):
    @staticmethod
    def _pack_row(series: int) -> dict:
        return {
            "product_p": "00000013075",
            "index": str(series),
            "po_number": "00000120489",
            "good_qty": 36,
            "completed_pack_qty": 36,
            "voided": False,
            "production_session_id": "PS-IMM313",
        }

    def test_unkeyed_snapshot_row_matches_keyed_pack_event(self) -> None:
        row = self._pack_row(315)
        event = {
            "type": "PACK",
            "pack_key": "00000013075|315|120489",
            "pack_record": dict(row),
        }
        session = dashboard_server.MachineSession(
            client_id="RPI-CLIENT-105",
            machine_code="M00013",
            machine_name="IMM 313",
            production_session_id="PS-IMM313",
            product_pack_history_logs=[row],
        )

        event_key = dashboard_server._pack_counter_event_key(event)

        self.assertEqual(event_key, "13075|315|120489")
        self.assertTrue(dashboard_server._session_has_pack_counter_event(session, event_key))

    def test_duplicate_snapshot_rows_are_collapsed_and_stamped(self) -> None:
        rows = [self._pack_row(series) for series in range(314, 322)]
        rows.insert(2, self._pack_row(315))
        rows.insert(4, self._pack_row(316))

        clean, repair = dashboard_server._dedupe_pack_history_rows(rows, "PS-IMM313")

        self.assertEqual(len(clean), 8)
        self.assertEqual(repair["duplicate_active"], 2)
        self.assertEqual(repair["duplicate_good"], 72)
        self.assertEqual(repair["active_good_before"], 360)
        self.assertEqual(repair["active_good_after"], 288)
        self.assertTrue(all(row.get("pack_key") for row in clean))

    def test_active_snapshot_repairs_good_without_reducing_correct_pack_count(self) -> None:
        rows = [self._pack_row(series) for series in range(314, 322)]
        rows.extend([self._pack_row(315), self._pack_row(316)])
        raw = {
            "client_id": "RPI-CLIENT-105",
            "machine_code": "M00013",
            "machine_name": "IMM 313",
            "job_code": "120488",
            "job_name": "3-26-1530",
            "production_session_id": "PS-IMM313",
            "pack_total": 8,
            "good_total": 360,
            "product_pack_history_logs": rows,
        }

        session = dashboard_server._session_from_active_snapshot(raw)

        self.assertIsNotNone(session)
        self.assertEqual(session.pack_total, 8)
        self.assertEqual(session.good_total, 288)
        self.assertEqual(len(session.product_pack_history_logs), 8)


if __name__ == "__main__":
    unittest.main()
