#!/usr/bin/env python3
"""Safely compact a Raspberry Machine client's legacy JSON outbox."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


DEFAULT_OUTBOX = Path.home() / ".local/share/raspberry-machine-client/server_event_queue.json"


def _event_type(row: Dict[str, Any]) -> str:
    payload = row.get("payload") if isinstance(row, dict) else {}
    event = payload.get("event") if isinstance(payload, dict) else {}
    return str(event.get("type") or "").strip().upper() if isinstance(event, dict) else ""


def _finished_record(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = row.get("payload") if isinstance(row, dict) else {}
    event = payload.get("event") if isinstance(payload, dict) else {}
    finished = event.get("finished_job") if isinstance(event, dict) else {}
    return finished if isinstance(finished, dict) else {}


def _finish_shift_key(row: Dict[str, Any]) -> Optional[Tuple[str, ...]]:
    finished = _finished_record(row)
    if not finished:
        return None
    values = (
        str(finished.get("record_type") or "").strip().upper(),
        str(finished.get("client_id") or "").strip(),
        str(finished.get("machine_code") or "").strip(),
        str(finished.get("job_code") or "").strip(),
        str(finished.get("operator_id") or "").strip(),
        str(finished.get("shift_index") or "").strip(),
        str(finished.get("finished_at_utc") or finished.get("ended_at_utc") or "").strip(),
    )
    return values if any(values[1:]) and values[-1] else None


def _finish_job_key(row: Dict[str, Any]) -> Optional[Tuple[str, ...]]:
    finished = _finished_record(row)
    if not finished:
        return None
    values = (
        str(finished.get("finished_at_utc") or finished.get("ended_at_utc") or "").strip(),
        str(finished.get("machine_code") or "").strip(),
        str(finished.get("job_code") or "").strip(),
        str(finished.get("operator_id") or "").strip(),
        str(finished.get("pack_count") or "").strip(),
        str(finished.get("good_total") or "").strip(),
    )
    return values if values[0] and values[1] and values[2] else None


def compact_rows(rows: Iterable[Any], *, app_log_limit: int = 80) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Return compact rows while retaining the oldest ID for equivalent retries."""
    clean: List[Dict[str, Any]] = []
    seen_shifts: Set[Tuple[str, ...]] = set()
    seen_jobs: Set[Tuple[str, ...]] = set()
    stats = {
        "input_rows": 0,
        "output_rows": 0,
        "invalid_rows": 0,
        "duplicate_finish_shifts": 0,
        "duplicate_finish_jobs": 0,
        "embedded_snapshots_removed": 0,
        "app_logs_removed": 0,
    }

    for raw in rows:
        stats["input_rows"] += 1
        if not isinstance(raw, dict) or not isinstance(raw.get("payload"), dict):
            stats["invalid_rows"] += 1
            continue
        row = dict(raw)
        payload = dict(row["payload"])
        event = payload.get("event")
        if not isinstance(event, dict):
            stats["invalid_rows"] += 1
            continue
        event = dict(event)
        event_type = str(event.get("type") or "").strip().upper()
        if not event_type:
            stats["invalid_rows"] += 1
            continue

        if event_type != "SESSION_SYNC" and "session_snapshot" in event:
            event.pop("session_snapshot", None)
            stats["embedded_snapshots_removed"] += 1

        if event_type in {"FINISH_SHIFT", "FINISH_JOB"} and isinstance(event.get("finished_job"), dict):
            finished = dict(event["finished_job"])
            logs = finished.get("client_app_logs")
            if isinstance(logs, list) and len(logs) > app_log_limit:
                stats["app_logs_removed"] += len(logs) - app_log_limit
                finished["client_app_logs"] = logs[-app_log_limit:]
            event["finished_job"] = finished

        payload["event"] = event
        row["payload"] = payload

        if event_type == "FINISH_SHIFT":
            key = _finish_shift_key(row)
            if key and key in seen_shifts:
                stats["duplicate_finish_shifts"] += 1
                continue
            if key:
                seen_shifts.add(key)
        elif event_type == "FINISH_JOB":
            key = _finish_job_key(row)
            if key and key in seen_jobs:
                stats["duplicate_finish_jobs"] += 1
                continue
            if key:
                seen_jobs.add(key)

        clean.append(row)

    stats["output_rows"] = len(clean)
    return clean, stats


def compact_file(path: Path, *, dry_run: bool = False, app_log_limit: int = 80) -> Dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    original_size = path.stat().st_size
    with path.open("r", encoding="utf-8-sig") as handle:
        rows = json.load(handle)
    if not isinstance(rows, list):
        raise ValueError(f"Outbox root must be a JSON list: {path}")
    compacted, stats = compact_rows(rows, app_log_limit=max(0, int(app_log_limit)))
    encoded = json.dumps(compacted, ensure_ascii=False, indent=2).encode("utf-8")
    result: Dict[str, Any] = {
        **stats,
        "path": str(path),
        "original_bytes": original_size,
        "compacted_bytes": len(encoded),
        "backup": "",
        "dry_run": bool(dry_run),
    }
    if dry_run or encoded == path.read_bytes():
        return result

    tmp = path.with_name(f".{path.name}.compact.tmp")
    backup = path.with_name(f"{path.name}.pre-compact.bak")
    with tmp.open("wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(path, backup)
    try:
        os.replace(tmp, path)
    except Exception:
        os.replace(backup, path)
        raise
    result["backup"] = str(backup)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_OUTBOX)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--app-log-limit", type=int, default=80)
    args = parser.parse_args()
    result = compact_file(args.path, dry_run=args.dry_run, app_log_limit=args.app_log_limit)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
