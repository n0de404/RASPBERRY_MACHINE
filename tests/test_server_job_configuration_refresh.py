import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLIENT_DIR = os.path.join(ROOT, "client")
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

import client
import mappings


def payload(job_id, ref, marker):
    return {
        "data": {
            "job": {"id": job_id, "ref_no": ref, "request_qty": marker},
            "job_details": {
                "product_id": f"P-{marker}",
                "std_cycle_time": str(marker),
                "packing_qty": marker,
                "color": f"COLOR-{marker}",
            },
            "parts": [{"product_id": f"PART-{marker}", "qty": marker}],
        }
    }


class ServerJobConfigurationRefreshTests(unittest.TestCase):
    @staticmethod
    def make_client():
        ui = client.ClientUI.__new__(client.ClientUI)
        ui.state = SimpleNamespace(
            job_code="101",
            job_name="OLD-MAIN",
            job_payload=payload("101", "OLD-MAIN", 1),
            linkage_job_code="202",
            linkage_job_name="OLD-LINKED",
            linkage_job_payload=payload("202", "OLD-LINKED", 1),
            linkage_jobs=[{
                "job_code": "202",
                "job_name": "OLD-LINKED",
                "job_payload": payload("202", "OLD-LINKED", 1),
            }],
            good_total=77,
            reject_total=3,
            operator_id="OP-1",
        )
        ui._job_configuration_versions = {}
        ui._job_configuration_refresh_inflight = True
        ui._job_parts_table_refresh_key = "old"
        ui._cache_job_payload = MagicMock(return_value=True)
        ui._refresh_ui = MagicMock()
        ui._save_active_session_snapshot = MagicMock()
        ui.sync_session_snapshot_to_server = MagicMock()
        ui._hide_bms_loading = MagicMock()
        ui.status = MagicMock()
        return ui

    def test_refresh_qr_is_recognized(self):
        result = mappings.parse_scan("refreshjobapi~1")
        self.assertIsNotNone(result)
        self.assertEqual(result.kind, "JOB_API_REFRESH_TRIGGER")

    def test_complete_server_configs_replace_job_fields_only(self):
        ui = self.make_client()
        result = {
            "manual": False,
            "response": {
                "items": [
                    {
                        "job_identifier": "101",
                        "job_id": "101",
                        "job_name": "NEW-MAIN",
                        "version": "main-v2",
                        "payload": payload("101", "NEW-MAIN", 9),
                    },
                    {
                        "job_identifier": "202",
                        "job_id": "202",
                        "job_name": "NEW-LINKED",
                        "version": "linked-v2",
                        "payload": payload("202", "NEW-LINKED", 8),
                    },
                ],
                "errors": [],
            },
        }

        ui._apply_server_job_configurations(result)

        self.assertEqual(ui.state.job_name, "NEW-MAIN")
        self.assertEqual(ui.state.job_payload["data"]["job_details"]["color"], "COLOR-9")
        self.assertEqual(ui.state.linkage_jobs[0]["job_name"], "NEW-LINKED")
        self.assertEqual(ui.state.linkage_job_payload["data"]["parts"][0]["qty"], 8)
        self.assertEqual(ui.state.good_total, 77)
        self.assertEqual(ui.state.reject_total, 3)
        self.assertEqual(ui.state.operator_id, "OP-1")
        ui._refresh_ui.assert_called_once_with(force=True)
        ui.sync_session_snapshot_to_server.assert_called_once()

    def test_unchanged_automatic_version_does_not_reapply(self):
        ui = self.make_client()
        ui._job_configuration_versions = {"101": "same-version"}
        ui.state.linkage_jobs = []
        ui.state.linkage_job_code = None
        result = {
            "manual": False,
            "response": {
                "items": [{
                    "job_identifier": "101",
                    "job_id": "101",
                    "job_name": "IGNORED",
                    "version": "same-version",
                    "payload": payload("101", "IGNORED", 5),
                }],
                "errors": [],
            },
        }

        ui._apply_server_job_configurations(result)

        self.assertEqual(ui.state.job_name, "OLD-MAIN")
        ui._refresh_ui.assert_not_called()
        ui.sync_session_snapshot_to_server.assert_not_called()


if __name__ == "__main__":
    unittest.main()
