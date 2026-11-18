import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLIENT_DIR = os.path.join(ROOT, "client")
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

import mixing_client


class MixingOfflineOutboxTests(unittest.TestCase):
    def test_server_ack_snapshot_is_not_replayed_into_mixing_state(self):
        client = mixing_client.MixingClientUI.__new__(mixing_client.MixingClientUI)
        with patch.object(
            mixing_client.production_client.ClientUI,
            "_apply_acknowledged_server_session",
        ) as base_apply:
            client._apply_acknowledged_server_session({"good_total": 999})
        base_apply.assert_not_called()

    def test_history_pull_is_blocked_while_outbox_has_mutations(self):
        client = mixing_client.MixingClientUI.__new__(mixing_client.MixingClientUI)
        client._mixing_server_pull_blocked_until = 0
        client._has_pending_server_mutations = MagicMock(return_value=True)
        client.state = SimpleNamespace(machine_code="M00001", job_code="123")
        client._mixing_history_synced_keys = set()
        client.client_config = {"server_url": "http://server.invalid"}
        with patch.object(mixing_client.production_client.requests, "get") as request_get:
            self.assertFalse(client._sync_mixing_material_history_from_server())
        request_get.assert_not_called()

    @staticmethod
    def _partial_client(response):
        client = mixing_client.MixingClientUI.__new__(mixing_client.MixingClientUI)
        client._mixing_partial_push_in_flight = False
        client._server_connection_ok = True
        client.client_config = {"server_url": "http://server"}
        client._request_with_ui_events = MagicMock(return_value=response)
        client._mixing_partial_outbox_timer = MagicMock()
        client._append_job_api_log = MagicMock()
        client._append_app_log = MagicMock()
        client.status = MagicMock()
        return client

    def test_partial_is_deleted_only_for_matching_explicit_ack(self):
        request_id = "mixing-1234567890abcdef"
        row = {
            "request_id": request_id,
            "attempt_count": 0,
            "next_attempt_epoch": 0,
            "request": {
                "endpoint": "/jobs/123/partials",
                "job_id": 123,
                "body": {"partial_qty": 5},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            outbox = Path(directory) / "partial_api_outbox.json"
            with patch.object(mixing_client, "MIXING_PARTIAL_API_OUTBOX_PATH", outbox):
                mixing_client.MixingClientUI._save_mixing_partial_api_outbox([row])
                wrong_ack = SimpleNamespace(
                    status_code=200,
                    json=lambda: {"ok": True, "request_id": "mixing-wrong-ack-id"},
                )
                client = self._partial_client(wrong_ack)
                client._http_error_snippet = MagicMock(return_value="wrong ACK")
                client._drain_mixing_partial_api_outbox()
                self.assertEqual(len(client._load_mixing_partial_api_outbox()), 1)

                mixing_client.MixingClientUI._save_mixing_partial_api_outbox([row])
                exact_ack = SimpleNamespace(
                    status_code=200,
                    json=lambda: {"ok": True, "request_id": request_id},
                )
                client = self._partial_client(exact_ack)
                client._drain_mixing_partial_api_outbox()
                self.assertEqual(client._load_mixing_partial_api_outbox(), [])


if __name__ == "__main__":
    unittest.main()
