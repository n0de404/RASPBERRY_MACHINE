import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
sys.path.insert(0, str(SERVER_DIR))

import server as server_module


class ServerRoleAssignmentTests(unittest.TestCase):
    def test_permanent_privilege_is_published_in_existing_daily_payload(self):
        profiles = [
            {
                "id_number": "26-00123",
                "name": "Dual Role Supervisor",
                "role": "Supervisor",
                "extra_privilege": "qc",
                "privilege_updated_at_utc": "2026-11-07T00:00:00+00:00",
            }
        ]
        with patch.object(server_module, "PROFILES", profiles), patch.object(
            server_module, "DAILY_ROLE_ASSIGNMENTS", {}
        ):
            rows = server_module.get_today_role_assignments()

        self.assertEqual(rows["26-00123"]["rights"], "both")
        self.assertEqual(rows["26-00123"]["assignment_scope"], "permanent")

    def test_temporary_assignment_overrides_permanent_for_current_day(self):
        badge = "26-00123"
        day = "2026-11-07"
        profiles = [{"id_number": badge, "name": "Person", "role": "Supervisor", "extra_privilege": "qc"}]
        daily = {
            day: {
                badge: {
                    "name": "Person",
                    "rights": "maintenance",
                    "company_role": "Supervisor",
                    "extra_privilege": "maintenance",
                }
            }
        }
        with patch.object(server_module, "PROFILES", profiles), patch.object(
            server_module, "DAILY_ROLE_ASSIGNMENTS", daily
        ), patch.object(server_module, "_today_key_local", return_value=day):
            rows = server_module.get_today_role_assignments()

        self.assertEqual(rows[badge]["rights"], "maintenance")
        self.assertEqual(rows[badge]["assignment_scope"], "temporary")

    def test_saving_permanent_role_removes_same_day_override(self):
        badge = "26-00123"
        day = "2026-11-07"
        profiles = [{"id_number": badge, "name": "Person", "role": "Supervisor"}]
        daily = {day: {badge: {"rights": "maintenance"}}}
        with patch.object(server_module, "PROFILES", profiles), patch.object(
            server_module, "DAILY_ROLE_ASSIGNMENTS", daily
        ), patch.object(server_module, "_today_key_local", return_value=day), patch.object(
            server_module, "save_profiles"
        ) as save_profiles, patch.object(
            server_module, "save_daily_role_assignments"
        ) as save_daily:
            saved = server_module.set_permanent_role_assignment(badge, "qc")

        self.assertTrue(saved)
        self.assertEqual(profiles[0]["extra_privilege"], "qc")
        self.assertNotIn(badge, daily[day])
        save_profiles.assert_called_once()
        save_daily.assert_called_once()


if __name__ == "__main__":
    unittest.main()
