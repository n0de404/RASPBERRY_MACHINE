from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


MACHINE_CODE = "M00413"
SESSION_ID = "PS-85C7A11B57CD4F43A1CFDC196E953A3C"
TARGET_TOTAL = 33


def is_active_startup_reject(row: object) -> bool:
    if not isinstance(row, dict) or bool(row.get("voided")):
        return False
    entry_type = str(row.get("entry_type") or "").strip().upper()
    reason = str(row.get("reason_code") or row.get("reason") or "").strip().upper()
    return entry_type == "STARTUP_REJECT_SCAN" or reason == "SUR"


def repair_snapshot(snapshot: dict) -> tuple[int, int]:
    if str(snapshot.get("machine_code") or "").strip() != MACHINE_CODE:
        raise RuntimeError(f"unexpected machine: {snapshot.get('machine_code')!r}")
    if str(snapshot.get("production_session_id") or "").strip() != SESSION_ID:
        raise RuntimeError(
            f"unexpected production session: {snapshot.get('production_session_id')!r}"
        )
    before = int(snapshot.get("startup_reject_total") or 0)
    logs = snapshot.get("reject_review_logs")
    if not isinstance(logs, list):
        logs = []
    kept_active = 0
    repaired_logs = []
    for row in logs:
        if is_active_startup_reject(row):
            if kept_active >= TARGET_TOTAL:
                continue
            kept_active += 1
        repaired_logs.append(row)
    if kept_active < TARGET_TOTAL:
        raise RuntimeError(
            f"only {kept_active} active startup-reject records exist; expected at least {TARGET_TOTAL}"
        )
    snapshot["startup_reject_total"] = TARGET_TOTAL
    snapshot["reject_review_logs"] = repaired_logs
    return before, len(logs) - len(repaired_logs)


def backup(path: Path, suffix: str) -> Path:
    target = path.with_name(f"{path.name}.startup-reject-repair-{suffix}.bak")
    shutil.copy2(path, target)
    return target


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: repair_413_startup_reject.py DATA_DIRECTORY")
    data_dir = Path(sys.argv[1]).expanduser().resolve()
    confirmed_path = data_dir / "server_confirmed_sessions.json"
    runtime_path = data_dir / "client_runtime.sqlite3"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    confirmed = json.loads(confirmed_path.read_text(encoding="utf-8"))
    if not isinstance(confirmed, dict):
        raise RuntimeError("server_confirmed_sessions.json must contain an object")
    matching = [
        row
        for row in confirmed.values()
        if isinstance(row, dict)
        and str(row.get("machine_code") or "").strip() == MACHINE_CODE
        and str(row.get("production_session_id") or "").strip() == SESSION_ID
    ]
    if len(matching) != 1:
        raise RuntimeError(f"expected one confirmed session, found {len(matching)}")

    connection = sqlite3.connect(runtime_path)
    try:
        db_row = connection.execute(
            "SELECT payload_json FROM active_sessions "
            "WHERE machine_code = ? AND production_session_id = ?",
            (MACHINE_CODE, SESSION_ID),
        ).fetchone()
        if db_row is None:
            raise RuntimeError("active runtime session was not found")
        runtime_snapshot = json.loads(db_row[0])

        confirmed_before, confirmed_removed = repair_snapshot(matching[0])
        runtime_before, runtime_removed = repair_snapshot(runtime_snapshot)
        if confirmed_before != runtime_before:
            raise RuntimeError(
                f"confirmed/runtime counters disagree: {confirmed_before} vs {runtime_before}"
            )

        confirmed_backup = backup(confirmed_path, stamp)
        runtime_backup = backup(runtime_path, stamp)
        confirmed_path.write_text(
            json.dumps(confirmed, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        connection.execute(
            "UPDATE active_sessions SET payload_json = ?, updated_at_utc = ? "
            "WHERE machine_code = ? AND production_session_id = ?",
            (
                json.dumps(runtime_snapshot, ensure_ascii=False, separators=(",", ":")),
                datetime.now(timezone.utc).isoformat(),
                MACHINE_CODE,
                SESSION_ID,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    print(
        json.dumps(
            {
                "ok": True,
                "machine_code": MACHINE_CODE,
                "production_session_id": SESSION_ID,
                "before": runtime_before,
                "after": TARGET_TOTAL,
                "confirmed_duplicates_removed": confirmed_removed,
                "runtime_duplicates_removed": runtime_removed,
                "backups": [str(confirmed_backup), str(runtime_backup)],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
