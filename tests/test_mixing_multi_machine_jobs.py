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


def snapshot(machine, job, *, active_at=1):
    return {
        "machine_code": machine,
        "machine_name": machine,
        "job_code": job,
        "job_name": job,
        "mixing_open": True,
        "mixing_last_active_at": active_at,
    }


class MixingMultiMachineJobTests(unittest.TestCase):
    @staticmethod
    def client(machine="MIX-A", job="JOB-1"):
        client = mixing_client.MixingClientUI.__new__(mixing_client.MixingClientUI)
        client.state = SimpleNamespace(
            machine_code=machine,
            machine_name=machine,
            job_code=job,
            job_name=job,
        )
        client._mixing_sessions = {}
        client._mixing_active_job_key = ""
        client._mixing_active_jobs_by_machine = {}
        return client

    def test_same_job_number_on_two_machines_has_separate_session_keys(self):
        client = self.client()
        self.assertEqual(client._mixing_session_key("mix-a", "123"), "MIX-A|123")
        self.assertEqual(client._mixing_session_key("mix-b", "123"), "MIX-B|123")

    def test_open_job_lookup_is_scoped_to_scanned_machine(self):
        client = self.client(machine="MIX-A", job="")
        client._mixing_sessions = {
            "MIX-A|123": snapshot("MIX-A", "123"),
            "MIX-B|123": snapshot("MIX-B", "123", active_at=2),
        }
        self.assertEqual(client._find_open_mixing_job(["123"]), "MIX-A|123")
        client.state.machine_code = "MIX-B"
        self.assertEqual(client._find_open_mixing_job(["123"]), "MIX-B|123")

    def test_machine_scan_restores_that_machines_latest_job_group(self):
        client = self.client(machine="MIX-A", job="111")
        client._mixing_sessions = {
            "MIX-A|111": snapshot("MIX-A", "111"),
            "MIX-B|222": snapshot("MIX-B", "222", active_at=1),
            "MIX-B|333": snapshot("MIX-B", "333", active_at=3),
        }
        client._mixing_active_jobs_by_machine = {"MIX-B": "MIX-B|333"}
        client._capture_current_mixing_session = MagicMock(return_value="MIX-A|111")
        client._switch_mixing_session = MagicMock(return_value=True)
        client.status = MagicMock()
        result = SimpleNamespace(meta={"machine_code": "MIX-B"})

        self.assertTrue(client._select_mixing_machine("MIX-B", result))
        client._switch_mixing_session.assert_called_once_with(
            "MIX-B|333", reason="machine group selected"
        )


if __name__ == "__main__":
    unittest.main()
