from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import server as dashboard_server


class PlanningQueueMismatchTests(unittest.TestCase):
    @staticmethod
    def _session(session_id: str = "SESSION-1") -> dashboard_server.MachineSession:
        return dashboard_server.MachineSession(
            client_id="RPI-303",
            machine_code="M00103",
            machine_name="IMM 303",
            job_code="RUNNING-JOB",
            job_name="Running Job",
            product_sku="SKU-RUNNING",
            production_session_id=session_id,
        )

    def test_removing_alerted_head_clears_only_that_mismatch(self) -> None:
        session = self._session()
        future_card = {"id": "CARD-2", "job_ref": "Future 2", "product_sku": "SKU-FUTURE-2"}
        board = {"lanes": {"M00103": [
            {"id": "CARD-1", "job_ref": "Expected next", "product_sku": "SKU-EXPECTED"},
            future_card,
        ]}}
        alerts: dict[str, dict] = {}

        with patch.object(dashboard_server, "PLANNING_BOARD", board), \
             patch.object(dashboard_server, "PLANNING_QUEUE_ALERTS", alerts), \
             patch.object(dashboard_server, "SESSIONS", {"M00103": session}):
            self.assertEqual(dashboard_server._reconcile_planning_queue_for_session(session), "MISMATCH")
            self.assertEqual(alerts["M00103"]["queued_card_id"], "CARD-1")

            board["lanes"]["M00103"] = [future_card]
            dashboard_server._refresh_active_planning_queue_alerts()

            self.assertEqual(alerts, {})
            self.assertEqual(board["lanes"]["M00103"], [future_card])

    def test_existing_head_keeps_its_attached_mismatch(self) -> None:
        session = self._session()
        board = {"lanes": {"M00103": [
            {"id": "CARD-1", "job_ref": "Expected next", "product_sku": "SKU-EXPECTED"},
            {"id": "CARD-2", "job_ref": "Future 2", "product_sku": "SKU-FUTURE-2"},
        ]}}
        alerts: dict[str, dict] = {}

        with patch.object(dashboard_server, "PLANNING_BOARD", board), \
             patch.object(dashboard_server, "PLANNING_QUEUE_ALERTS", alerts), \
             patch.object(dashboard_server, "SESSIONS", {"M00103": session}):
            dashboard_server._reconcile_planning_queue_for_session(session)
            original_alert_id = alerts["M00103"]["id"]
            dashboard_server._refresh_active_planning_queue_alerts()

            self.assertEqual(alerts["M00103"]["id"], original_alert_id)
            self.assertEqual(alerts["M00103"]["queued_card_id"], "CARD-1")

    def test_new_production_session_can_check_the_remaining_head(self) -> None:
        old_session = self._session("SESSION-1")
        new_session = self._session("SESSION-2")
        board = {"lanes": {"M00103": [
            {"id": "CARD-1", "job_ref": "Expected next", "product_sku": "SKU-EXPECTED"},
            {"id": "CARD-2", "job_ref": "Future 2", "product_sku": "SKU-FUTURE-2"},
        ]}}
        alerts: dict[str, dict] = {}

        with patch.object(dashboard_server, "PLANNING_BOARD", board), \
             patch.object(dashboard_server, "PLANNING_QUEUE_ALERTS", alerts), \
             patch.object(dashboard_server, "SESSIONS", {"M00103": new_session}):
            dashboard_server._reconcile_planning_queue_for_session(old_session)
            board["lanes"]["M00103"] = board["lanes"]["M00103"][1:]
            dashboard_server._refresh_active_planning_queue_alerts()

            self.assertEqual(alerts["M00103"]["production_session_id"], "SESSION-2")
            self.assertEqual(alerts["M00103"]["queued_card_id"], "CARD-2")


if __name__ == "__main__":
    unittest.main()
