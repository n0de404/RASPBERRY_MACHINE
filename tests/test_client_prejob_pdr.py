import sys
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace


CLIENT_DIR = Path(__file__).resolve().parents[1] / "client"
sys.path.insert(0, str(CLIENT_DIR))

from client import ClientState, ClientUI


class PreJobPdrTransferTests(unittest.TestCase):
    def test_line_technician_profile_has_pdr_maintenance_rights_only(self):
        client = SimpleNamespace(
            _user_qr_profiles_cache=[
                {
                    "id_number": "60027",
                    "name": "Line Technician One",
                    "role": "LINE TECHNICIAN",
                }
            ],
            _daily_role_assignments_cache={},
        )
        client._clean_badge_scan_code = MethodType(ClientUI._clean_badge_scan_code, client)
        client._role_caps_from_text = MethodType(ClientUI._role_caps_from_text, client)
        client._trigger_identity_cache_sync = lambda force=False: None
        client._operator_from_local_cache = lambda code: None
        client._local_operator_from_history = lambda code: None

        person = ClientUI._authorized_person_from_scan(client, "60027")

        self.assertIsNotNone(person)
        self.assertEqual(person["role"], "LINE TECHNICIAN")
        self.assertEqual(person["can_pdr_maintenance"], "1")
        self.assertEqual(person["can_maintenance"], "0")
        self.assertEqual(person["can_supervisor"], "0")
        self.assertEqual(person["can_qc"], "0")
        self.assertTrue(ClientUI._can_handle_pdr_maintenance(client, person))

    def test_regular_maintenance_profile_keeps_pdr_rights(self):
        person = {"can_maintenance": "1", "can_pdr_maintenance": "1"}

        self.assertTrue(ClientUI._can_handle_pdr_maintenance(SimpleNamespace(), person))

    def test_machine_only_pdr_state_is_captured_and_attached(self):
        state = ClientState(
            machine_code="M00001",
            pdr_started_before_job=True,
            downtime_active=True,
            waiting_downtime_end_maintenance=True,
            downtime_started_at=123.5,
            pdr_reason_segments=[{"reason_code": "04", "duration_seconds": 12}],
            pdr_downtime_logs=[{"duration_seconds": 30}],
        )
        client = SimpleNamespace(state=state)

        saved = ClientUI._capture_prejob_pdr_state(client)

        state.downtime_active = False
        state.waiting_downtime_end_maintenance = False
        state.downtime_started_at = None
        state.pdr_reason_segments = []
        state.pdr_downtime_logs = []
        state.job_code = "JOB-100"
        attached = ClientUI._restore_prejob_pdr_state(client, saved)

        self.assertTrue(attached)
        self.assertTrue(state.downtime_active)
        self.assertTrue(state.waiting_downtime_end_maintenance)
        self.assertEqual(state.downtime_started_at, 123.5)
        self.assertEqual(state.pdr_reason_segments[0]["reason_code"], "04")
        self.assertEqual(state.pdr_downtime_logs[0]["duration_seconds"], 30)
        self.assertFalse(state.pdr_started_before_job)

    def test_regular_job_state_is_not_treated_as_prejob_pdr(self):
        state = ClientState(
            machine_code="M00001",
            job_code="JOB-100",
            pdr_started_before_job=True,
            downtime_active=True,
        )
        client = SimpleNamespace(state=state)

        self.assertEqual(ClientUI._capture_prejob_pdr_state(client), {})

    def test_pdr_workflow_detects_machine_only_waiting_state(self):
        state = ClientState(
            machine_code="M00001",
            pdr_started_before_job=True,
            waiting_downtime_start_maintenance=True,
        )
        client = SimpleNamespace(state=state)

        self.assertTrue(ClientUI._pdr_workflow_active(client))

    def test_pending_pdr_start_can_be_cancelled_without_erasing_job(self):
        state = ClientState(
            machine_code="M00001",
            job_code="JOB-100",
            operator_id="OP-1",
            waiting_downtime_start_maintenance=True,
            downtime_wait_started_at=123.5,
        )
        status_messages = []
        sync_reasons = []
        client = SimpleNamespace(
            state=state,
            status=SimpleNamespace(setText=status_messages.append),
            _hide_production_overlay=lambda: None,
            _refresh_ui=lambda: None,
            _save_active_session_snapshot=lambda: None,
            sync_session_snapshot_to_server=sync_reasons.append,
        )

        cancelled = ClientUI._cancel_pending_pdr_start(client)

        self.assertTrue(cancelled)
        self.assertFalse(state.waiting_downtime_start_maintenance)
        self.assertIsNone(state.downtime_wait_started_at)
        self.assertEqual(state.job_code, "JOB-100")
        self.assertEqual(sync_reasons, ["SESSION SNAPSHOT SYNC (PDR START CANCELLED)"])
        self.assertIn("PDR start cancelled", status_messages[-1])

    def test_started_pdr_downtime_cannot_be_cancelled(self):
        state = ClientState(
            machine_code="M00001",
            job_code="JOB-100",
            downtime_active=True,
            downtime_started_at=123.5,
            waiting_downtime_end_maintenance=True,
        )
        client = SimpleNamespace(state=state)

        self.assertFalse(ClientUI._cancel_pending_pdr_start(client))
        self.assertTrue(state.downtime_active)
        self.assertTrue(state.waiting_downtime_end_maintenance)

    def test_completed_machine_only_pdr_skips_cycle_time_and_waits_for_job(self):
        state = ClientState(
            machine_code="M00001",
            pdr_started_before_job=True,
            maintenance_name="Maintenance One",
            maintenance_downtime_seconds=45,
            downtime_last_seconds=45,
            waiting_pdr_maintenance_reason=True,
            pdr_reason_segments=[{"reason_code": "04", "duration_seconds": 45}],
            pdr_downtime_logs=[],
        )
        client = SimpleNamespace(state=state)
        client._record_completed_pdr_downtime = MethodType(
            ClientUI._record_completed_pdr_downtime, client
        )
        client._reset_downtime_resolution_state = MethodType(
            ClientUI._reset_downtime_resolution_state, client
        )

        record = ClientUI._complete_prejob_pdr_without_cycle_time(client)

        self.assertIsNotNone(record)
        self.assertEqual(record["duration_seconds"], 45)
        self.assertIsNone(record["cycle_time"])
        self.assertEqual(record["confirmed_by"], "Maintenance One")
        self.assertFalse(state.waiting_cycle_time_input)
        self.assertFalse(state.waiting_pdr_maintenance_reason)
        self.assertFalse(state.downtime_active)
        self.assertTrue(state.pdr_started_before_job)
        self.assertEqual(len(state.pdr_downtime_logs), 1)

    def test_prejob_cycle_skip_does_not_apply_after_job_is_selected(self):
        state = ClientState(
            machine_code="M00001",
            job_code="JOB-100",
            pdr_started_before_job=True,
            maintenance_downtime_seconds=45,
            pdr_downtime_logs=[],
        )
        client = SimpleNamespace(state=state)

        record = ClientUI._complete_prejob_pdr_without_cycle_time(client)

        self.assertIsNone(record)
        self.assertEqual(state.pdr_downtime_logs, [])

    def test_stopped_pdr_uses_server_restored_downtime_duration(self):
        state = ClientState(
            machine_code="M00001",
            pdr_started_before_job=True,
            downtime_active=False,
            downtime_started_at=None,
            downtime_last_seconds=4189,
            maintenance_downtime_seconds=None,
            waiting_pdr_maintenance_reason=True,
        )
        client = SimpleNamespace(state=state)

        duration = ClientUI._stopped_pdr_repair_duration(client)

        self.assertEqual(duration, 4189)


if __name__ == "__main__":
    unittest.main()
