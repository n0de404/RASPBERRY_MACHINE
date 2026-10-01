"""Transactional local runtime storage for the Raspberry Machine client.

The UI historically persisted mutable runtime state in JSON files.  This
module keeps the public payload shapes unchanged while storing the hot paths
(active sessions, outbox, scan identities, and learned QR rules) in SQLite.
Every method opens a short-lived connection so worker and Qt threads never
share a sqlite connection object.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _json_value(value: Any, fallback: Any) -> Any:
    try:
        parsed = json.loads(str(value or ""))
        return parsed
    except Exception:
        return fallback


class ClientRuntimeStore:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "client_runtime.sqlite3"
        self._init_lock = threading.Lock()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=10.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def transaction(self):
        self.initialize()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            conn = self._connect()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS runtime_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS active_sessions (
                        machine_code TEXT PRIMARY KEY,
                        client_id TEXT NOT NULL DEFAULT '',
                        production_session_id TEXT NOT NULL DEFAULT '',
                        updated_at_utc TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS event_outbox (
                        event_id TEXT PRIMARY KEY,
                        client_id TEXT NOT NULL DEFAULT '',
                        machine_code TEXT NOT NULL DEFAULT '',
                        production_session_id TEXT NOT NULL DEFAULT '',
                        session_sequence INTEGER NOT NULL DEFAULT 0,
                        event_type TEXT NOT NULL DEFAULT '',
                        created_at_utc TEXT NOT NULL,
                        silent INTEGER NOT NULL DEFAULT 0,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        last_error TEXT NOT NULL DEFAULT '',
                        last_attempt_utc TEXT NOT NULL DEFAULT '',
                        payload_json TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_outbox_order
                        ON event_outbox(machine_code, production_session_id, session_sequence, created_at_utc);
                    CREATE INDEX IF NOT EXISTS idx_outbox_type
                        ON event_outbox(event_type, created_at_utc);
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_outbox_session_sequence
                        ON event_outbox(client_id,machine_code,production_session_id,session_sequence)
                        WHERE session_sequence > 0;
                    CREATE TABLE IF NOT EXISTS scan_identities (
                        scan_key TEXT PRIMARY KEY,
                        production_session_id TEXT NOT NULL DEFAULT '',
                        machine_code TEXT NOT NULL DEFAULT '',
                        job_code TEXT NOT NULL DEFAULT '',
                        product_id TEXT NOT NULL DEFAULT '',
                        series_identity TEXT NOT NULL DEFAULT '',
                        scan_kind TEXT NOT NULL DEFAULT 'PACK',
                        first_scanned_at_utc TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_scan_session_product
                        ON scan_identities(production_session_id, product_id, scan_kind);
                    CREATE TABLE IF NOT EXISTS qr_classifications (
                        production_session_id TEXT NOT NULL,
                        active_job_code TEXT NOT NULL,
                        product_id TEXT NOT NULL,
                        qr_type TEXT NOT NULL,
                        confirmed_at_utc TEXT NOT NULL,
                        PRIMARY KEY(production_session_id, active_job_code, product_id)
                    );
                    CREATE TABLE IF NOT EXISTS session_sequences (
                        client_id TEXT NOT NULL,
                        machine_code TEXT NOT NULL,
                        production_session_id TEXT NOT NULL,
                        last_sequence INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY(client_id, machine_code, production_session_id)
                    );
                    CREATE TABLE IF NOT EXISTS sync_state (
                        client_id TEXT NOT NULL,
                        machine_code TEXT NOT NULL,
                        production_session_id TEXT NOT NULL,
                        last_ack_sequence INTEGER NOT NULL DEFAULT 0,
                        last_sync_at_utc TEXT NOT NULL DEFAULT '',
                        last_error TEXT NOT NULL DEFAULT '',
                        PRIMARY KEY(client_id, machine_code, production_session_id)
                    );
                    CREATE TABLE IF NOT EXISTS finished_records (
                        record_key TEXT PRIMARY KEY,
                        record_kind TEXT NOT NULL,
                        production_session_id TEXT NOT NULL DEFAULT '',
                        machine_code TEXT NOT NULL DEFAULT '',
                        job_code TEXT NOT NULL DEFAULT '',
                        finished_at_utc TEXT NOT NULL DEFAULT '',
                        sync_status TEXT NOT NULL DEFAULT 'PENDING',
                        payload_json TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_finished_pending
                        ON finished_records(record_kind,sync_status,finished_at_utc);
                    """
                )
                conn.execute(
                    "INSERT INTO runtime_meta(key,value) VALUES('schema_version',?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(SCHEMA_VERSION),),
                )
                conn.commit()
            finally:
                conn.close()
            self._initialized = True

    def meta_get(self, key: str, default: str = "") -> str:
        self.initialize()
        conn = self._connect()
        try:
            row = conn.execute("SELECT value FROM runtime_meta WHERE key=?", (str(key),)).fetchone()
            return str(row["value"]) if row is not None else default
        finally:
            conn.close()

    def meta_set(self, key: str, value: Any) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO runtime_meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(key), str(value)),
            )

    def _backup_legacy_file(self, path: Path) -> None:
        if not path.exists():
            return
        backup = Path(f"{path}.pre-sqlite-v{SCHEMA_VERSION}.bak")
        if backup.exists():
            return
        try:
            shutil.copy2(path, backup)
        except Exception:
            pass

    def migrate_legacy_json(
        self,
        *,
        active_sessions_file: str,
        outbox_file: str,
        scanned_keys_file: str,
        finished_jobs_file: str = "",
        finish_shifts_file: str = "",
    ) -> None:
        """Import existing JSON once and leave timestamped-compatible backups."""
        if self.meta_get("legacy_json_migrated_v1") == "1":
            return
        active_path = Path(active_sessions_file)
        outbox_path = Path(outbox_file)
        scans_path = Path(scanned_keys_file)
        finished_jobs_path = Path(finished_jobs_file) if finished_jobs_file else None
        finish_shifts_path = Path(finish_shifts_file) if finish_shifts_file else None
        for path in (active_path, outbox_path, scans_path, finished_jobs_path, finish_shifts_path):
            if path is None:
                continue
            self._backup_legacy_file(path)

        def read(path: Path, fallback: Any) -> Any:
            for candidate in (path, Path(f"{path}.bak")):
                try:
                    return json.loads(candidate.read_text(encoding="utf-8-sig"))
                except Exception:
                    continue
            return fallback

        active = read(active_path, {})
        outbox = read(outbox_path, [])
        scans = read(scans_path, {})
        finished_jobs = read(finished_jobs_path, []) if finished_jobs_path else []
        finish_shifts = read(finish_shifts_path, []) if finish_shifts_path else []
        with self.transaction() as conn:
            if isinstance(active, dict):
                for code, payload in active.items():
                    if not str(code).strip() or not isinstance(payload, dict):
                        continue
                    self._upsert_active_conn(conn, str(code).strip(), payload)
            if isinstance(outbox, list):
                for index, item in enumerate(outbox):
                    if isinstance(item, dict):
                        if not str(item.get("id") or "").strip():
                            digest = hashlib.sha256(
                                f"{index}|{_json_text(item)}".encode("utf-8", errors="replace")
                            ).hexdigest()
                            item = dict(item)
                            item["id"] = f"LEGACY-{digest}"
                            item.setdefault("created_at_utc", _utc_now())
                        self._upsert_outbox_conn(conn, item)
            if isinstance(scans, dict):
                for key, payload in scans.items():
                    if str(key).strip() and isinstance(payload, dict):
                        self._upsert_scan_conn(conn, str(key).strip(), payload)
            for kind, records in (("FINISH_JOB", finished_jobs), ("FINISH_SHIFT", finish_shifts)):
                if not isinstance(records, list):
                    continue
                for record in records:
                    if isinstance(record, dict):
                        self._upsert_finished_conn(conn, kind, record)
            conn.execute(
                "INSERT INTO runtime_meta(key,value) VALUES('legacy_json_migrated_v1','1') "
                "ON CONFLICT(key) DO UPDATE SET value='1'"
            )
            check = conn.execute("PRAGMA quick_check").fetchone()
            if check is None or str(check[0]).lower() != "ok":
                raise sqlite3.DatabaseError("SQLite quick_check failed after legacy import")

    def _upsert_active_conn(self, conn: sqlite3.Connection, machine_code: str, payload: Dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO active_sessions(machine_code,client_id,production_session_id,updated_at_utc,payload_json)
            VALUES(?,?,?,?,?)
            ON CONFLICT(machine_code) DO UPDATE SET
              client_id=excluded.client_id,
              production_session_id=excluded.production_session_id,
              updated_at_utc=excluded.updated_at_utc,
              payload_json=excluded.payload_json
            """,
            (
                machine_code,
                str(payload.get("client_id") or ""),
                str(payload.get("production_session_id") or ""),
                str(payload.get("saved_at_utc") or _utc_now()),
                _json_text(payload),
            ),
        )
        rules = payload.get("offline_qr_type_rules") if isinstance(payload.get("offline_qr_type_rules"), dict) else {}
        session_id = str(payload.get("production_session_id") or "")
        active_job = str(payload.get("job_code") or "")
        for signature, qr_type in rules.items():
            parts = str(signature or "").split("|PRODUCT:", 1)
            product_id = parts[1].strip() if len(parts) == 2 else ""
            if not session_id or not active_job or not product_id:
                continue
            conn.execute(
                """
                INSERT INTO qr_classifications(
                  production_session_id,active_job_code,product_id,qr_type,confirmed_at_utc
                ) VALUES(?,?,?,?,?)
                ON CONFLICT(production_session_id,active_job_code,product_id)
                DO UPDATE SET qr_type=excluded.qr_type,confirmed_at_utc=excluded.confirmed_at_utc
                """,
                (session_id, active_job, product_id, str(qr_type or "").upper(), _utc_now()),
            )

    def load_active_sessions(self) -> Dict[str, Dict[str, Any]]:
        self.initialize()
        conn = self._connect()
        try:
            rows = conn.execute("SELECT machine_code,payload_json FROM active_sessions").fetchall()
            return {
                str(row["machine_code"]): value
                for row in rows
                if isinstance((value := _json_value(row["payload_json"], {})), dict)
            }
        finally:
            conn.close()

    def replace_active_sessions(self, rows: Dict[str, Dict[str, Any]]) -> bool:
        try:
            with self.transaction() as conn:
                wanted = {str(code).strip() for code in (rows or {}) if str(code).strip()}
                for code, payload in (rows or {}).items():
                    if str(code).strip() and isinstance(payload, dict):
                        self._upsert_active_conn(conn, str(code).strip(), payload)
                if wanted:
                    placeholders = ",".join("?" for _ in wanted)
                    conn.execute(f"DELETE FROM active_sessions WHERE machine_code NOT IN ({placeholders})", tuple(wanted))
                else:
                    conn.execute("DELETE FROM active_sessions")
            return True
        except Exception:
            return False

    def upsert_active_session(self, payload: Dict[str, Any]) -> bool:
        code = str((payload or {}).get("machine_code") or "").strip()
        if not code:
            return False
        try:
            with self.transaction() as conn:
                self._upsert_active_conn(conn, code, payload)
            return True
        except Exception:
            return False

    def delete_active_session(self, machine_code: Any) -> bool:
        code = str(machine_code or "").strip()
        if not code:
            return False
        try:
            with self.transaction() as conn:
                conn.execute("DELETE FROM active_sessions WHERE machine_code=?", (code,))
            return True
        except Exception:
            return False

    @staticmethod
    def _outbox_fields(item: Dict[str, Any]) -> tuple:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
        return (
            str(item.get("id") or ""),
            str(payload.get("client_id") or ""),
            str(payload.get("machine_code") or ""),
            str(payload.get("production_session_id") or event.get("production_session_id") or ""),
            int(payload.get("session_sequence") or item.get("session_sequence") or 0),
            str(event.get("type") or "").strip().upper(),
            str(item.get("created_at_utc") or _utc_now()),
            1 if bool(item.get("silent")) else 0,
            int(item.get("attempts") or 0),
            str(item.get("last_error") or "")[:1000],
            str(item.get("last_attempt_utc") or ""),
            _json_text(item),
        )

    def _upsert_outbox_conn(self, conn: sqlite3.Connection, item: Dict[str, Any]) -> bool:
        fields = self._outbox_fields(item)
        if not fields[0]:
            return False
        conn.execute(
            """
            INSERT INTO event_outbox(
              event_id,client_id,machine_code,production_session_id,session_sequence,event_type,
              created_at_utc,silent,attempts,last_error,last_attempt_utc,payload_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(event_id) DO UPDATE SET
              attempts=excluded.attempts,
              last_error=excluded.last_error,
              last_attempt_utc=excluded.last_attempt_utc,
              payload_json=excluded.payload_json
            """,
            fields,
        )
        return True

    def upsert_outbox(self, item: Dict[str, Any]) -> bool:
        try:
            with self.transaction() as conn:
                return self._upsert_outbox_conn(conn, item)
        except Exception:
            return False

    def enqueue_outbox(self, item: Dict[str, Any]) -> bool:
        """Reserve sequence, persist dedupe identity, and enqueue atomically."""
        try:
            with self.transaction() as conn:
                payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
                event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
                event_type = str(event.get("type") or "").strip().upper()
                client_id = str(payload.get("client_id") or "")
                machine_code = str(payload.get("machine_code") or "")
                session_id = str(payload.get("production_session_id") or event.get("production_session_id") or "") or "NO_SESSION"
                if event_type not in ("", "HEARTBEAT") and not int(payload.get("session_sequence") or 0):
                    identity = (client_id, machine_code, session_id)
                    seq_row = conn.execute(
                        "SELECT last_sequence FROM session_sequences WHERE client_id=? AND machine_code=? AND production_session_id=?",
                        identity,
                    ).fetchone()
                    sequence = int(seq_row["last_sequence"] if seq_row is not None else 0) + 1
                    conn.execute(
                        """
                        INSERT INTO session_sequences(client_id,machine_code,production_session_id,last_sequence)
                        VALUES(?,?,?,?)
                        ON CONFLICT(client_id,machine_code,production_session_id)
                        DO UPDATE SET last_sequence=excluded.last_sequence
                        """,
                        (*identity, sequence),
                    )
                    payload["session_sequence"] = sequence
                    item["session_sequence"] = sequence
                item["payload"] = payload

                scan_key = ""
                scan_payload: Dict[str, Any] = {}
                if event_type in {"PACK", "LAST_SHIFT_BUTAL_PACK", "BUTAL_COMPLETION_PACK"}:
                    pack_record = event.get("pack_record") if isinstance(event.get("pack_record"), dict) else {}
                    scan_key = str(event.get("pack_key") or pack_record.get("pack_key") or "").strip()
                    scan_payload = dict(pack_record)
                    scan_payload["scan_kind"] = "PACK"
                elif event_type == "RAW_MATERIAL":
                    raw_record = event.get("raw_material_log") if isinstance(event.get("raw_material_log"), dict) else {}
                    scan_key = str(event.get("unique_key") or raw_record.get("unique_key") or "").strip()
                    scan_payload = dict(raw_record)
                    scan_payload["scan_kind"] = (
                        "RAW_MATERIAL"
                        if str(raw_record.get("material_type") or "").upper() == "RAW_MATERIAL"
                        else "PRODUCT_PART"
                    )
                if scan_key:
                    scan_payload.setdefault("production_session_id", session_id)
                    scan_payload.setdefault("machine_code", machine_code)
                    scan_payload.setdefault("job_code", payload.get("job_code"))
                    self._upsert_scan_conn(conn, scan_key, scan_payload)

                return self._upsert_outbox_conn(conn, item)
        except Exception:
            return False

    def load_outbox(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        self.initialize()
        conn = self._connect()
        try:
            sql = (
                "SELECT payload_json FROM event_outbox "
                "ORDER BY created_at_utc,event_id"
            )
            args: tuple = ()
            if limit is not None:
                sql += " LIMIT ?"
                args = (max(1, int(limit)),)
            rows = conn.execute(sql, args).fetchall()
            return [
                value for row in rows
                if isinstance((value := _json_value(row["payload_json"], {})), dict)
            ]
        finally:
            conn.close()

    def replace_outbox(self, rows: Iterable[Dict[str, Any]]) -> bool:
        clean = [row for row in rows or [] if isinstance(row, dict) and str(row.get("id") or "").strip()]
        try:
            with self.transaction() as conn:
                wanted = [str(row.get("id") or "") for row in clean]
                for row in clean:
                    self._upsert_outbox_conn(conn, row)
                if wanted:
                    placeholders = ",".join("?" for _ in wanted)
                    conn.execute(f"DELETE FROM event_outbox WHERE event_id NOT IN ({placeholders})", tuple(wanted))
                else:
                    conn.execute("DELETE FROM event_outbox")
            return True
        except Exception:
            return False

    def delete_outbox(self, event_id: Any) -> bool:
        event_key = str(event_id or "").strip()
        if not event_key:
            return False
        try:
            with self.transaction() as conn:
                conn.execute("DELETE FROM event_outbox WHERE event_id=?", (event_key,))
            return True
        except Exception:
            return False

    def mark_outbox_failed(self, event_id: Any, error: Any) -> bool:
        event_key = str(event_id or "").strip()
        if not event_key:
            return False
        try:
            with self.transaction() as conn:
                row = conn.execute("SELECT payload_json FROM event_outbox WHERE event_id=?", (event_key,)).fetchone()
                if row is None:
                    return False
                item = _json_value(row["payload_json"], {})
                item["attempts"] = int(item.get("attempts") or 0) + 1
                item["last_error"] = str(error or "")[:240]
                item["last_attempt_utc"] = _utc_now()
                self._upsert_outbox_conn(conn, item)
            return True
        except Exception:
            return False

    def next_session_sequence(self, client_id: Any, machine_code: Any, session_id: Any) -> int:
        identity = (str(client_id or ""), str(machine_code or ""), str(session_id or "") or "NO_SESSION")
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT last_sequence FROM session_sequences WHERE client_id=? AND machine_code=? AND production_session_id=?",
                identity,
            ).fetchone()
            value = int(row["last_sequence"] if row is not None else 0) + 1
            conn.execute(
                """
                INSERT INTO session_sequences(client_id,machine_code,production_session_id,last_sequence)
                VALUES(?,?,?,?)
                ON CONFLICT(client_id,machine_code,production_session_id)
                DO UPDATE SET last_sequence=excluded.last_sequence
                """,
                (*identity, value),
            )
            return value

    def acknowledge_sequence(self, client_id: Any, machine_code: Any, session_id: Any, sequence: Any) -> None:
        value = max(0, int(sequence or 0))
        identity = (str(client_id or ""), str(machine_code or ""), str(session_id or "") or "NO_SESSION")
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO sync_state(client_id,machine_code,production_session_id,last_ack_sequence,last_sync_at_utc,last_error)
                VALUES(?,?,?,?,?,'')
                ON CONFLICT(client_id,machine_code,production_session_id) DO UPDATE SET
                  last_ack_sequence=MAX(sync_state.last_ack_sequence,excluded.last_ack_sequence),
                  last_sync_at_utc=excluded.last_sync_at_utc,
                  last_error=''
                """,
                (*identity, value, _utc_now()),
            )

    def _upsert_scan_conn(self, conn: sqlite3.Connection, scan_key: str, payload: Dict[str, Any]) -> None:
        product_id = str(payload.get("product_p") or payload.get("product_id") or "")
        series = "|".join(
            str(payload.get(name) or "")
            for name in ("index", "lot_number", "po_number")
        )
        conn.execute(
            """
            INSERT INTO scan_identities(
              scan_key,production_session_id,machine_code,job_code,product_id,series_identity,
              scan_kind,first_scanned_at_utc,payload_json
            ) VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(scan_key) DO UPDATE SET payload_json=excluded.payload_json
            """,
            (
                scan_key,
                str(payload.get("production_session_id") or ""),
                str(payload.get("machine_code") or ""),
                str(payload.get("job_code") or payload.get("po_number") or ""),
                product_id,
                series,
                str(payload.get("scan_kind") or "PACK").upper(),
                str(payload.get("first_scanned_at") or payload.get("scanned_at") or _utc_now()),
                _json_text(payload),
            ),
        )

    def load_scan_identities(self) -> Dict[str, Dict[str, Any]]:
        self.initialize()
        conn = self._connect()
        try:
            rows = conn.execute("SELECT scan_key,payload_json FROM scan_identities").fetchall()
            return {
                str(row["scan_key"]): value
                for row in rows
                if isinstance((value := _json_value(row["payload_json"], {})), dict)
            }
        finally:
            conn.close()

    def scan_identity_exists(self, scan_key: Any) -> bool:
        key = str(scan_key or "").strip()
        if not key:
            return False
        self.initialize()
        conn = self._connect()
        try:
            return conn.execute(
                "SELECT 1 FROM scan_identities WHERE scan_key=? LIMIT 1",
                (key,),
            ).fetchone() is not None
        finally:
            conn.close()

    def upsert_scan_identity(self, scan_key: Any, payload: Dict[str, Any]) -> bool:
        key = str(scan_key or "").strip()
        if not key:
            return False
        try:
            with self.transaction() as conn:
                self._upsert_scan_conn(conn, key, payload)
            return True
        except Exception:
            return False

    def delete_scan_identity(self, scan_key: Any) -> bool:
        key = str(scan_key or "").strip()
        if not key:
            return False
        try:
            with self.transaction() as conn:
                conn.execute("DELETE FROM scan_identities WHERE scan_key=?", (key,))
            return True
        except Exception:
            return False

    def remember_qr_classification(
        self,
        production_session_id: Any,
        active_job_code: Any,
        product_id: Any,
        qr_type: Any,
    ) -> bool:
        values = (
            str(production_session_id or "").strip(),
            str(active_job_code or "").strip(),
            str(product_id or "").strip().upper(),
            str(qr_type or "").strip().upper(),
        )
        if not all(values) or values[3] not in {"PACK", "PRODUCT_PART"}:
            return False
        try:
            with self.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO qr_classifications(
                      production_session_id,active_job_code,product_id,qr_type,confirmed_at_utc
                    ) VALUES(?,?,?,?,?)
                    ON CONFLICT(production_session_id,active_job_code,product_id)
                    DO UPDATE SET qr_type=excluded.qr_type,confirmed_at_utc=excluded.confirmed_at_utc
                    """,
                    (*values, _utc_now()),
                )
            return True
        except Exception:
            return False

    def load_qr_classifications(self, production_session_id: Any, active_job_code: Any) -> Dict[str, str]:
        self.initialize()
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT product_id,qr_type FROM qr_classifications WHERE production_session_id=? AND active_job_code=?",
                (str(production_session_id or "").strip(), str(active_job_code or "").strip()),
            ).fetchall()
            return {str(row["product_id"]): str(row["qr_type"]) for row in rows}
        finally:
            conn.close()

    def diagnostics(self) -> Dict[str, Any]:
        self.initialize()
        conn = self._connect()
        try:
            return {
                "database": str(self.db_path),
                "schema_version": int(self.meta_get("schema_version", "0") or 0),
                "active_sessions": int(conn.execute("SELECT COUNT(*) FROM active_sessions").fetchone()[0]),
                "outbox_events": int(conn.execute("SELECT COUNT(*) FROM event_outbox").fetchone()[0]),
                "scan_identities": int(conn.execute("SELECT COUNT(*) FROM scan_identities").fetchone()[0]),
                "qr_classifications": int(conn.execute("SELECT COUNT(*) FROM qr_classifications").fetchone()[0]),
                "finished_records": int(conn.execute("SELECT COUNT(*) FROM finished_records").fetchone()[0]),
            }
        finally:
            conn.close()

    @staticmethod
    def _finished_record_key(kind: str, payload: Dict[str, Any]) -> str:
        explicit = str(payload.get("local_record_id") or payload.get("record_id") or "").strip()
        if explicit:
            return explicit
        stable = "|".join(
            (
                str(kind or "").upper(),
                str(payload.get("production_session_id") or ""),
                str(payload.get("machine_code") or ""),
                str(payload.get("job_code") or ""),
                str(payload.get("shift_index") if payload.get("shift_index") is not None else ""),
                str(payload.get("finished_at_utc") or payload.get("ended_at_utc") or ""),
            )
        )
        return f"LEGACY-{hashlib.sha256(stable.encode('utf-8')).hexdigest()}"

    def _upsert_finished_conn(
        self,
        conn: sqlite3.Connection,
        kind: str,
        payload: Dict[str, Any],
    ) -> str:
        record_kind = str(kind or payload.get("record_type") or "FINISH_JOB").upper()
        key = self._finished_record_key(record_kind, payload)
        conn.execute(
            """
            INSERT INTO finished_records(
              record_key,record_kind,production_session_id,machine_code,job_code,
              finished_at_utc,sync_status,payload_json
            ) VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(record_key) DO UPDATE SET
              sync_status=excluded.sync_status,
              payload_json=excluded.payload_json
            """,
            (
                key,
                record_kind,
                str(payload.get("production_session_id") or ""),
                str(payload.get("machine_code") or ""),
                str(payload.get("job_code") or ""),
                str(payload.get("finished_at_utc") or payload.get("ended_at_utc") or ""),
                str(payload.get("sync_status") or "PENDING").upper(),
                _json_text(payload),
            ),
        )
        return key

    def load_finished_records(self, kind: str) -> List[Dict[str, Any]]:
        self.initialize()
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT payload_json FROM finished_records WHERE record_kind=? ORDER BY finished_at_utc,record_key",
                (str(kind or "").upper(),),
            ).fetchall()
            return [
                value for row in rows
                if isinstance((value := _json_value(row["payload_json"], {})), dict)
            ]
        finally:
            conn.close()

    def replace_finished_records(self, kind: str, rows: Iterable[Dict[str, Any]]) -> bool:
        record_kind = str(kind or "").upper()
        clean = [row for row in rows or [] if isinstance(row, dict)]
        try:
            with self.transaction() as conn:
                wanted: List[str] = []
                for row in clean:
                    wanted.append(self._upsert_finished_conn(conn, record_kind, row))
                if wanted:
                    placeholders = ",".join("?" for _ in wanted)
                    conn.execute(
                        f"DELETE FROM finished_records WHERE record_kind=? AND record_key NOT IN ({placeholders})",
                        (record_kind, *wanted),
                    )
                else:
                    conn.execute("DELETE FROM finished_records WHERE record_kind=?", (record_kind,))
            return True
        except Exception:
            return False

    def append_finished_record(self, kind: str, payload: Dict[str, Any]) -> bool:
        try:
            with self.transaction() as conn:
                self._upsert_finished_conn(conn, str(kind or "").upper(), payload)
            return True
        except Exception:
            return False
