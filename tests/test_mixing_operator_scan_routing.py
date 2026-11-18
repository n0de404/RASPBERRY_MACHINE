import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLIENT_DIR = os.path.join(ROOT, "client")
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

import mixing_client


class _RoutingVerified(Exception):
    pass


class MixingOperatorScanRoutingTests(unittest.TestCase):
    @staticmethod
    def _client(*, pending_job=""):
        client = mixing_client.MixingClientUI.__new__(mixing_client.MixingClientUI)
        client.state = SimpleNamespace(
            machine_code="MT-301",
            job_code="1542",
            job_name="3-26-1542",
            operator_id=None,
        )
        client._mixing_pending_job_raw = pending_job
        client._mixing_pending_job_source_machine = "MT-301" if pending_job else ""
        client._normalize_mixing_machine_scan = MagicMock(side_effect=lambda raw: raw)
        client._handle_mixing_finish_confirmation = MagicMock(return_value=False)
        client._sync_mixing_material_history_from_server = MagicMock(
            side_effect=_RoutingVerified
        )
        client._capture_current_mixing_session = MagicMock(return_value="1542")
        client._refresh_ui = MagicMock()
        client._refresh_mixing_jobs_panel = MagicMock()
        client._route_product_part_to_open_job = MagicMock(return_value="")
        return client

    def test_job_shaped_operator_scan_reaches_operator_resolver(self):
        client = self._client()
        job_shaped_badge = "O000000000240000001234500000000000"
        parsed_as_job = mixing_client.production_client.ScanResult(
            kind="JOB",
            raw=job_shaped_badge,
            value="12345",
            meta={"po_number": "12345"},
        )

        with patch.object(
            mixing_client.production_client,
            "parse_scan",
            return_value=parsed_as_job,
        ), patch.object(
            mixing_client.production_client.ClientUI,
            "on_scanned",
        ) as production_scan:
            with self.assertRaises(_RoutingVerified):
                client.on_scanned(job_shaped_badge)

        production_scan.assert_called_once_with(job_shaped_badge)
        self.assertEqual(client._mixing_pending_job_raw, "")

    def test_stale_machine_picker_is_cleared_while_operator_is_expected(self):
        client = self._client(pending_job="WRONGLY_QUEUED_OPERATOR")
        operator_badge = "OPERATOR-BADGE"
        parsed_operator = mixing_client.production_client.ScanResult(
            kind="OPERATOR",
            raw=operator_badge,
            value="1001 - Mixer",
        )

        with patch.object(
            mixing_client.production_client,
            "parse_scan",
            return_value=parsed_operator,
        ), patch.object(
            mixing_client.production_client.ClientUI,
            "on_scanned",
        ) as production_scan:
            with self.assertRaises(_RoutingVerified):
                client.on_scanned(operator_badge)

        production_scan.assert_called_once_with(operator_badge)
        self.assertEqual(client._mixing_pending_job_raw, "")
        self.assertEqual(client._mixing_pending_job_source_machine, "")


if __name__ == "__main__":
    unittest.main()
