import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_DIR = os.path.join(ROOT, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import server as dashboard_server


class ClientStatusRegistryTests(unittest.TestCase):
    def setUp(self):
        self.original_rows = dashboard_server.CLIENT_STATUSES
        self.original_dirty = dashboard_server.CLIENT_STATUSES_DIRTY
        self.original_last_flush = dashboard_server.CLIENT_STATUSES_LAST_FLUSH
        dashboard_server.CLIENT_STATUSES = {}
        dashboard_server.CLIENT_STATUSES_DIRTY = False
        dashboard_server.CLIENT_STATUSES_LAST_FLUSH = 0.0

    def tearDown(self):
        dashboard_server.CLIENT_STATUSES = self.original_rows
        dashboard_server.CLIENT_STATUSES_DIRTY = self.original_dirty
        dashboard_server.CLIENT_STATUSES_LAST_FLUSH = self.original_last_flush

    def test_poll_does_not_erase_heartbeat_ip(self):
        dashboard_server._update_client_status(
            "RPI-CLIENT-06",
            "192.168.13.13",
            machine_code="M00010",
            machine_name="IMM 310",
            event_type="HEARTBEAT",
            machine_scanned=True,
        )
        row = dashboard_server._update_client_status(
            "RPI-CLIENT-06",
            "",
            machine_code="M00010",
            machine_name="IMM 310",
            event_type="CLIENT_POLL",
            machine_scanned=True,
        )

        self.assertEqual(row["remote_host"], "192.168.13.13")

    def test_offline_client_registry_survives_reload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "client_statuses.json"
            with patch.object(dashboard_server, "CLIENT_STATUS_FILE", registry_path):
                dashboard_server._update_client_status(
                    "RPI-CLIENT-105",
                    "192.168.10.239",
                    machine_code="M00013",
                    machine_name="IMM 313",
                    event_type="HEARTBEAT",
                    machine_scanned=True,
                )
                self.assertTrue(
                    dashboard_server._flush_client_status_registry_if_due(force=True)
                )
                dashboard_server.CLIENT_STATUSES = {}
                restored = dashboard_server._load_client_status_registry()

        self.assertEqual(
            restored["RPI-CLIENT-105"]["remote_host"], "192.168.10.239"
        )
        self.assertEqual(restored["RPI-CLIENT-105"]["machine_code"], "M00013")


if __name__ == "__main__":
    unittest.main()
