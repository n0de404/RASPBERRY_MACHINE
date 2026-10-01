from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "client"
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from runtime_store import ClientRuntimeStore, SCHEMA_VERSION


class ClientRuntimeStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._temp_dir.name)
        self.store = ClientRuntimeStore(str(self.data_dir))

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def _write_json(self, name: str, value: object) -> Path:
        path = self.data_dir / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _event(
        event_id: str,
        *,
        created_at: str,
        session_id: str = "PS-A",
        event_type: str = "PACK",
        pack_key: str = "",
        product_id: str = "00000001234",
        series: int = 1,
    ) -> dict:
        event = {
            "type": event_type,
            "production_session_id": session_id,
        }
        if event_type == "PACK":
            event.update(
                {
                    "pack_key": pack_key or f"{product_id}|{series}|118090",
                    "pack_qty": 1,
                    "qty": 6,
                    "pack_record": {
                        "production_session_id": session_id,
                        "product_p": product_id,
                        "index": str(series),
                        "lot_number": "20260922000001",
                        "po_number": "118090",
                        "scanned_at": created_at,
                    },
                }
            )
        return {
            "id": event_id,
            "created_at_utc": created_at,
            "silent": False,
            "attempts": 0,
            "last_error": "",
            "payload": {
                "client_id": "RPI-TEST-01",
                "machine_code": "M00004",
                "machine_name": "IMM 304",
                "job_code": "118090",
                "production_session_id": session_id,
                "event": event,
                "last_event": event_type,
            },
        }

    def test_legacy_json_migration_creates_backups_and_is_idempotent(self) -> None:
        active_payload = {
            "M00004": {
                "client_id": "RPI-TEST-01",
                "machine_code": "M00004",
                "job_code": "118090",
                "production_session_id": "PS-MIGRATE",
                "pack_count": 2,
                "saved_at_utc": "2026-09-22T00:00:05+00:00",
            }
        }
        legacy_event = self._event(
            "legacy-event-1",
            created_at="2026-09-22T00:00:01+00:00",
            session_id="PS-MIGRATE",
        )
        event_without_id = self._event(
            "temporary-id",
            created_at="2026-09-22T00:00:02+00:00",
            session_id="PS-MIGRATE",
            series=2,
        )
        event_without_id.pop("id")
        scan_payload = {
            "PACK-EXACT-1": {
                "production_session_id": "PS-MIGRATE",
                "machine_code": "M00004",
                "job_code": "118090",
                "product_p": "00000001234",
                "index": "1",
                "lot_number": "20260922000001",
                "po_number": "118090",
                "scan_kind": "PACK",
            }
        }
        finished_job = {
            "production_session_id": "PS-MIGRATE",
            "machine_code": "M00004",
            "job_code": "118090",
            "finished_at_utc": "2026-09-22T01:00:00+00:00",
            "record_type": "FINAL_JOB",
            "pack_count": 2,
        }
        finished_shift = {
            "production_session_id": "PS-MIGRATE",
            "machine_code": "M00004",
            "job_code": "118090",
            "shift_index": 1,
            "finished_at_utc": "2026-09-22T00:30:00+00:00",
            "record_type": "SHIFT_PARTIAL",
        }

        files = {
            "active_sessions_file": self._write_json("client_active_machine_sessions.json", active_payload),
            "outbox_file": self._write_json("server_event_queue.json", [legacy_event, event_without_id]),
            "scanned_keys_file": self._write_json("scanned_pack_qr_keys.json", scan_payload),
            "finished_jobs_file": self._write_json("finished_jobs.json", [finished_job]),
            "finish_shifts_file": self._write_json("finish_shift.json", [finished_shift]),
        }
        original_bytes = {name: path.read_bytes() for name, path in files.items()}

        self.store.migrate_legacy_json(**{name: str(path) for name, path in files.items()})

        for name, path in files.items():
            backup = Path(f"{path}.pre-sqlite-v{SCHEMA_VERSION}.bak")
            self.assertTrue(backup.exists(), f"missing migration backup for {name}")
            self.assertEqual(backup.read_bytes(), original_bytes[name])

        self.assertEqual(self.store.meta_get("legacy_json_migrated_v1"), "1")
        self.assertEqual(self.store.load_active_sessions()["M00004"]["pack_count"], 2)
        migrated_outbox = self.store.load_outbox()
        self.assertEqual(len(migrated_outbox), 2)
        self.assertEqual(migrated_outbox[0]["id"], "legacy-event-1")
        self.assertTrue(migrated_outbox[1]["id"].startswith("LEGACY-"))
        self.assertEqual(set(self.store.load_scan_identities()), {"PACK-EXACT-1"})
        self.assertEqual(self.store.load_finished_records("FINISH_JOB"), [finished_job])
        self.assertEqual(self.store.load_finished_records("FINISH_SHIFT"), [finished_shift])

        # A completed migration must not import later edits to legacy files.
        self._write_json("server_event_queue.json", [legacy_event, self._event(
            "late-legacy-event",
            created_at="2026-09-22T00:00:03+00:00",
            session_id="PS-MIGRATE",
            series=3,
        )])
        restarted_store = ClientRuntimeStore(str(self.data_dir))
        restarted_store.migrate_legacy_json(
            **{name: str(path) for name, path in files.items()}
        )
        self.assertEqual(len(restarted_store.load_outbox()), 2)

    def test_migration_uses_json_backup_when_primary_is_invalid(self) -> None:
        active_path = self.data_dir / "client_active_machine_sessions.json"
        active_path.write_text("{not valid json", encoding="utf-8")
        expected = {
            "M00010": {
                "machine_code": "M00010",
                "job_code": "118178",
                "production_session_id": "PS-FROM-BACKUP",
            }
        }
        Path(f"{active_path}.bak").write_text(json.dumps(expected), encoding="utf-8")
        outbox_path = self._write_json("server_event_queue.json", [])
        scans_path = self._write_json("scanned_pack_qr_keys.json", {})

        self.store.migrate_legacy_json(
            active_sessions_file=str(active_path),
            outbox_file=str(outbox_path),
            scanned_keys_file=str(scans_path),
        )

        self.assertEqual(self.store.load_active_sessions(), expected)
        primary_backup = Path(f"{active_path}.pre-sqlite-v{SCHEMA_VERSION}.bak")
        self.assertEqual(primary_backup.read_text(encoding="utf-8"), "{not valid json")

    def test_outbox_order_and_sequence_allocation_are_durable(self) -> None:
        first = self._event("event-1", created_at="2026-09-22T00:00:01+00:00")
        second = self._event(
            "event-2",
            created_at="2026-09-22T00:00:02+00:00",
            series=2,
        )
        other_session = self._event(
            "event-b1",
            created_at="2026-09-22T00:00:03+00:00",
            session_id="PS-B",
            series=3,
        )

        self.assertTrue(self.store.enqueue_outbox(first))
        self.assertTrue(self.store.enqueue_outbox(second))
        self.assertTrue(self.store.enqueue_outbox(other_session))

        self.assertEqual(first["payload"]["session_sequence"], 1)
        self.assertEqual(second["payload"]["session_sequence"], 2)
        self.assertEqual(other_session["payload"]["session_sequence"], 1)
        self.assertEqual(
            [row["id"] for row in self.store.load_outbox()],
            ["event-1", "event-2", "event-b1"],
        )

        restarted_store = ClientRuntimeStore(str(self.data_dir))
        self.assertEqual(
            [row["id"] for row in restarted_store.load_outbox()],
            ["event-1", "event-2", "event-b1"],
        )
        self.assertEqual(
            restarted_store.next_session_sequence("RPI-TEST-01", "M00004", "PS-A"),
            3,
        )
        self.assertEqual(
            restarted_store.next_session_sequence("RPI-TEST-01", "M00004", "PS-B"),
            2,
        )

    def test_exact_scan_identity_survives_restart(self) -> None:
        event = self._event(
            "scan-event-1",
            created_at="2026-09-22T00:00:01+00:00",
            pack_key="00000001234|1|118090",
        )
        self.assertTrue(self.store.enqueue_outbox(event))
        self.assertTrue(self.store.scan_identity_exists("00000001234|1|118090"))
        self.assertFalse(self.store.scan_identity_exists("00000001234|10|118090"))

        restarted_store = ClientRuntimeStore(str(self.data_dir))
        scans = restarted_store.load_scan_identities()
        self.assertEqual(set(scans), {"00000001234|1|118090"})
        self.assertEqual(scans["00000001234|1|118090"]["index"], "1")
        self.assertEqual(scans["00000001234|1|118090"]["scan_kind"], "PACK")

    def test_same_product_different_series_are_distinct_but_retry_is_not(self) -> None:
        product_id = "00000008306"
        first_key = f"PARTQR:{product_id}:1:20260922000001"
        second_key = f"PARTQR:{product_id}:2:20260922000001"
        common = {
            "production_session_id": "PS-PARTS",
            "machine_code": "M00010",
            "job_code": "118178",
            "product_p": product_id,
            "lot_number": "20260922000001",
            "po_number": "999999",
            "scan_kind": "PRODUCT_PART",
        }

        self.assertTrue(self.store.upsert_scan_identity(first_key, {**common, "index": "1"}))
        self.assertTrue(self.store.upsert_scan_identity(second_key, {**common, "index": "2"}))
        self.assertTrue(
            self.store.upsert_scan_identity(
                first_key,
                {**common, "index": "1", "retry_note": "same exact label"},
            )
        )

        scans = self.store.load_scan_identities()
        self.assertEqual(set(scans), {first_key, second_key})
        self.assertEqual(scans[first_key]["retry_note"], "same exact label")
        self.assertEqual(scans[second_key]["index"], "2")
        conn = sqlite3.connect(self.store.db_path)
        try:
            series_rows = conn.execute(
                "SELECT series_identity FROM scan_identities ORDER BY scan_key"
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual(len(series_rows), 2)
        self.assertEqual(len({row[0] for row in series_rows}), 2)

    def test_qr_classification_is_scoped_to_production_session_and_job(self) -> None:
        self.assertTrue(
            self.store.remember_qr_classification(
                "PS-ONE", "118090", "00000008306", "PRODUCT_PART"
            )
        )
        self.assertEqual(
            self.store.load_qr_classifications("PS-ONE", "118090"),
            {"00000008306": "PRODUCT_PART"},
        )
        self.assertEqual(self.store.load_qr_classifications("PS-TWO", "118090"), {})
        self.assertEqual(self.store.load_qr_classifications("PS-ONE", "118091"), {})

        self.assertTrue(
            self.store.remember_qr_classification(
                "PS-TWO", "118090", "00000008306", "PACK"
            )
        )
        self.assertEqual(
            self.store.load_qr_classifications("PS-ONE", "118090")["00000008306"],
            "PRODUCT_PART",
        )
        self.assertEqual(
            self.store.load_qr_classifications("PS-TWO", "118090")["00000008306"],
            "PACK",
        )

    def test_retrying_same_outbox_event_is_idempotent(self) -> None:
        event = self._event("retry-event", created_at="2026-09-22T00:00:01+00:00")
        self.assertTrue(self.store.enqueue_outbox(event))
        assigned_sequence = event["payload"]["session_sequence"]

        self.assertTrue(self.store.enqueue_outbox(event))
        self.assertEqual(event["payload"]["session_sequence"], assigned_sequence)
        self.assertEqual(len(self.store.load_outbox()), 1)
        self.assertEqual(self.store.diagnostics()["scan_identities"], 1)

        self.assertTrue(self.store.mark_outbox_failed("retry-event", "timeout one"))
        self.assertTrue(self.store.mark_outbox_failed("retry-event", "timeout two"))
        retried = self.store.load_outbox()[0]
        self.assertEqual(retried["id"], "retry-event")
        self.assertEqual(retried["attempts"], 2)
        self.assertEqual(retried["last_error"], "timeout two")
        self.assertEqual(retried["payload"]["session_sequence"], assigned_sequence)

        restarted_store = ClientRuntimeStore(str(self.data_dir))
        self.assertEqual(len(restarted_store.load_outbox()), 1)
        self.assertTrue(restarted_store.delete_outbox("retry-event"))
        self.assertEqual(restarted_store.load_outbox(), [])

    def test_finished_job_and_shift_records_persist_and_deduplicate(self) -> None:
        job = {
            "production_session_id": "PS-FINISH",
            "machine_code": "M00004",
            "job_code": "118090",
            "finished_at_utc": "2026-09-22T01:00:00+00:00",
            "record_type": "FINAL_JOB",
            "pack_count": 20,
            "good_total": 120,
        }
        shift = {
            "production_session_id": "PS-FINISH",
            "machine_code": "M00004",
            "job_code": "118090",
            "shift_index": 1,
            "finished_at_utc": "2026-09-22T00:30:00+00:00",
            "record_type": "SHIFT_PARTIAL",
            "pack_count": 10,
        }

        self.assertTrue(self.store.append_finished_record("FINISH_JOB", job))
        self.assertTrue(self.store.append_finished_record("FINISH_SHIFT", shift))
        updated_job = {**job, "good_total": 126, "sync_status": "PENDING"}
        self.assertTrue(self.store.append_finished_record("FINISH_JOB", updated_job))

        restarted_store = ClientRuntimeStore(str(self.data_dir))
        self.assertEqual(restarted_store.load_finished_records("FINISH_JOB"), [updated_job])
        self.assertEqual(restarted_store.load_finished_records("FINISH_SHIFT"), [shift])
        self.assertEqual(restarted_store.diagnostics()["finished_records"], 2)

        second_job = {
            **job,
            "production_session_id": "PS-FINISH-2",
            "finished_at_utc": "2026-09-22T02:00:00+00:00",
        }
        self.assertTrue(
            restarted_store.replace_finished_records("FINISH_JOB", [second_job])
        )
        self.assertEqual(
            restarted_store.load_finished_records("FINISH_JOB"),
            [second_job],
        )
        self.assertEqual(restarted_store.load_finished_records("FINISH_SHIFT"), [shift])


if __name__ == "__main__":
    unittest.main()
