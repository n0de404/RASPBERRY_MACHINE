import json
import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "client" / "compact_outbox.py"
SPEC = importlib.util.spec_from_file_location("compact_outbox", MODULE_PATH)
compact_outbox = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(compact_outbox)
compact_file = compact_outbox.compact_file
compact_rows = compact_outbox.compact_rows


def event(event_id, event_type, *, finished=None, snapshot=None):
    body = {"type": event_type}
    if finished is not None:
        body["finished_job"] = finished
    if snapshot is not None:
        body["session_snapshot"] = snapshot
    return {
        "id": event_id,
        "payload": {
            "client_id": "RPI-CLIENT-13",
            "machine_code": "IMM 413",
            "sync_protocol_requested": 2,
            "event": body,
        },
    }


class CompactOutboxTests(unittest.TestCase):
    def test_deduplicates_protocol_two_finish_shift_and_compacts_payload(self):
        finished = {
            "record_type": "SHIFT_PARTIAL",
            "client_id": "RPI-CLIENT-13",
            "machine_code": "IMM 413",
            "job_code": "118639",
            "operator_id": "26-00814",
            "shift_index": 1,
            "finished_at_utc": "2026-10-02T22:18:48+00:00",
            "client_app_logs": [{"activity_id": str(i)} for i in range(100)],
        }
        rows = [
            event("oldest-id", "FINISH_SHIFT", finished=finished, snapshot={"large": True}),
            event("duplicate-id", "FINISH_SHIFT", finished=finished, snapshot={"large": True}),
            event("pack-id", "PACK", snapshot={"large": True}),
        ]
        clean, stats = compact_rows(rows, app_log_limit=10)
        self.assertEqual([row["id"] for row in clean], ["oldest-id", "pack-id"])
        self.assertEqual(stats["duplicate_finish_shifts"], 1)
        self.assertEqual(len(clean[0]["payload"]["event"]["finished_job"]["client_app_logs"]), 10)
        self.assertNotIn("session_snapshot", clean[0]["payload"]["event"])
        self.assertNotIn("session_snapshot", clean[1]["payload"]["event"])

    def test_file_replacement_keeps_recoverable_backup(self):
        finished = {
            "machine_code": "IMM 413",
            "job_code": "118639",
            "operator_id": "26-00814",
            "finished_at_utc": "2026-10-02T22:18:48+00:00",
        }
        rows = [event("one", "FINISH_SHIFT", finished=finished), event("two", "FINISH_SHIFT", finished=finished)]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "server_event_queue.json"
            path.write_text(json.dumps(rows), encoding="utf-8")
            result = compact_file(path)
            self.assertEqual(len(json.loads(path.read_text(encoding="utf-8"))), 1)
            backup = Path(result["backup"])
            self.assertTrue(backup.exists())
            self.assertEqual(len(json.loads(backup.read_text(encoding="utf-8"))), 2)


if __name__ == "__main__":
    unittest.main()
