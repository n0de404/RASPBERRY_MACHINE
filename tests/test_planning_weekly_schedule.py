from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import server as dashboard_server


class PlanningWeeklyScheduleTests(unittest.TestCase):
    @staticmethod
    def _session() -> dashboard_server.MachineSession:
        return dashboard_server.MachineSession(
            client_id="RPI-303",
            machine_code="M00103",
            machine_name="IMM 303",
            job_code="RUNNING-JOB",
            job_name="Running Job",
            product_sku="SKU-TODAY",
            production_session_id="SESSION-TODAY",
        )

    def test_today_filter_keeps_legacy_and_today_but_excludes_other_dates(self) -> None:
        today = datetime.now().astimezone().date()
        cards = [
            {"id": "LEGACY"},
            {"id": "TODAY", "schedule_date": today.isoformat()},
            {"id": "TOMORROW", "schedule_date": (today + timedelta(days=1)).isoformat()},
        ]

        result = dashboard_server._planning_cards_for_today(cards)

        self.assertEqual([card["id"] for card in result], ["LEGACY", "TODAY"])

    def test_future_card_does_not_block_or_get_removed_when_today_job_starts(self) -> None:
        today = datetime.now().astimezone().date()
        future_card = {
            "id": "FUTURE",
            "job_ref": "Future job",
            "product_sku": "SKU-FUTURE",
            "schedule_date": (today + timedelta(days=1)).isoformat(),
            "manpower_count": 4,
        }
        today_card = {
            "id": "TODAY",
            "job_ref": "Today's job",
            "product_sku": "SKU-TODAY",
            "schedule_date": today.isoformat(),
            "manpower_count": 3,
        }
        board = {"lanes": {"M00103": [future_card, today_card]}}
        alerts: dict[str, dict] = {}

        def save_without_storage(payload):
            dashboard_server.PLANNING_BOARD = payload
            return payload

        with patch.object(dashboard_server, "PLANNING_BOARD", board), \
             patch.object(dashboard_server, "PLANNING_QUEUE_ALERTS", alerts), \
             patch.object(dashboard_server, "save_planning_board", side_effect=save_without_storage), \
             patch.object(dashboard_server, "append_planning_activity_log"):
            result = dashboard_server._reconcile_planning_queue_for_session(self._session())

            self.assertEqual(result, "MATCHED")
            self.assertEqual(dashboard_server.PLANNING_BOARD["lanes"]["M00103"], [future_card])
            self.assertEqual(alerts, {})

    def test_board_save_preserves_schedule_date_and_manual_manpower(self) -> None:
        card = {
            "id": "PLANNED",
            "product_sku": "SKU-PLANNED",
            "schedule_date": "2026-11-04",
            "manpower_count": 6,
        }

        with patch.object(dashboard_server, "_save_server_document_sql", return_value=True):
            saved = dashboard_server.save_planning_board({"lanes": {"M00103": [card]}})

        self.assertEqual(saved["lanes"]["M00103"][0]["schedule_date"], "2026-11-04")
        self.assertEqual(saved["lanes"]["M00103"][0]["manpower_count"], 6)


if __name__ == "__main__":
    unittest.main()
