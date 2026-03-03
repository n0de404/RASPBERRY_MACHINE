from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import pymysql
    from pymysql.cursors import DictCursor
except Exception:
    pymysql = None
    DictCursor = None


BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "Database"
SQL_CONFIG_FILE = DATABASE_DIR / "sql_config.json"


def load_sql_config() -> Dict[str, Any]:
    cfg: Dict[str, Any] = {
        "enabled": True,
        "host": "localhost",
        "port": 3306,
        "database": "rpimachineapp_db",
        "user": "rpimachine_user",
        "password": "0t1docmtl$tm",
        "connect_timeout": 5,
    }
    try:
        if SQL_CONFIG_FILE.exists():
            raw = json.loads(SQL_CONFIG_FILE.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                cfg.update(raw)
    except Exception:
        pass
    try:
        cfg["port"] = int(cfg.get("port", 3306) or 3306)
    except Exception:
        cfg["port"] = 3306
    try:
        cfg["connect_timeout"] = int(cfg.get("connect_timeout", 5) or 5)
    except Exception:
        cfg["connect_timeout"] = 5
    cfg["enabled"] = bool(cfg.get("enabled", True))
    return cfg


def _connect():
    if pymysql is None:
        return None
    cfg = load_sql_config()
    if not cfg.get("enabled"):
        return None
    try:
        return pymysql.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            database=cfg["database"],
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
            connect_timeout=cfg["connect_timeout"],
        )
    except Exception:
        return None


def ensure_schema() -> bool:
    conn = _connect()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS `server_settings` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `theme` VARCHAR(100) NULL,
                  `qrgen_base_url` VARCHAR(255) NULL,
                  `raw_json` JSON NOT NULL,
                  PRIMARY KEY (`id`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS `user_qr_profiles` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `id_number` VARCHAR(100) NOT NULL,
                  `name` VARCHAR(255) NULL,
                  `role` VARCHAR(100) NULL,
                  `created_at_utc` VARCHAR(50) NULL,
                  `print_count` INT NOT NULL DEFAULT 0,
                  `last_printed_at_utc` VARCHAR(50) NULL,
                  `raw_json` JSON NOT NULL,
                  PRIMARY KEY (`id`),
                  UNIQUE KEY `uq_user_qr_profiles_id_number` (`id_number`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS `finished_jobs` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `finished_at_utc` VARCHAR(50) NULL,
                  `client_id` VARCHAR(100) NULL,
                  `machine_code` VARCHAR(50) NULL,
                  `machine_name` VARCHAR(255) NULL,
                  `job_code` VARCHAR(100) NULL,
                  `job_name` VARCHAR(255) NULL,
                  `operator_id` VARCHAR(255) NULL,
                  `pack_count` INT NOT NULL DEFAULT 0,
                  `good_total` INT NOT NULL DEFAULT 0,
                  `butal_total` INT NOT NULL DEFAULT 0,
                  `reject_total` INT NOT NULL DEFAULT 0,
                  `total_good` INT NOT NULL DEFAULT 0,
                  `startup_reject_total` INT NOT NULL DEFAULT 0,
                  `raw_sacks_count` INT NOT NULL DEFAULT 0,
                  `downtime_last_seconds` INT NULL,
                  `downtime_reason_code` VARCHAR(50) NULL,
                  `downtime_reason_text` TEXT NULL,
                  `cycle_time_current` VARCHAR(100) NULL,
                  `maintenance_name` VARCHAR(255) NULL,
                  `supervisor_name` VARCHAR(255) NULL,
                  `approved_by` VARCHAR(255) NULL,
                  `approved_by_code` VARCHAR(100) NULL,
                  `approved_by_role` VARCHAR(100) NULL,
                  `approved_remarks` TEXT NULL,
                  `approved_at_utc` VARCHAR(50) NULL,
                  `review_status` VARCHAR(100) NULL,
                  `linkage_enabled` TINYINT NOT NULL DEFAULT 0,
                  `linkage_job_code` VARCHAR(100) NULL,
                  `linkage_job_name` VARCHAR(255) NULL,
                  `linkage_role` VARCHAR(50) NULL,
                  `linkage_group_total_jobs` INT NULL,
                  `linkage_main_job_code` VARCHAR(100) NULL,
                  `linkage_main_job_name` VARCHAR(255) NULL,
                  `linkage_note` TEXT NULL,
                  `reject_breakdown` JSON NOT NULL,
                  `raw_material_scans` JSON NOT NULL,
                  `raw_material_logs` JSON NOT NULL,
                  `job_payload` JSON NOT NULL,
                  `reject_review_logs` JSON NOT NULL,
                  `linkage_job_payload` JSON NULL,
                  `linkage_jobs` JSON NULL,
                  `linkage_mirror` JSON NULL,
                  `review_history` JSON NULL,
                  `raw_json` JSON NOT NULL,
                  PRIMARY KEY (`id`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        conn.close()


def _decode_json(raw: Any, fallback: Any) -> Any:
    if raw is None:
        return fallback
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def load_user_qr_profiles() -> Optional[List[Dict[str, Any]]]:
    conn = _connect()
    if conn is None:
        return None
    try:
        items: List[Dict[str, Any]] = []
        with conn.cursor() as cur:
            cur.execute("SELECT `raw_json` FROM `user_qr_profiles` ORDER BY `id` ASC")
            for row in cur.fetchall() or []:
                item = _decode_json(row.get("raw_json"), {})
                if isinstance(item, dict):
                    items.append(item)
        return items
    except Exception:
        return None
    finally:
        conn.close()


def user_qr_profiles_storage_ready() -> bool:
    conn = _connect()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM `user_qr_profiles` LIMIT 1")
            cur.fetchone()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def save_user_qr_profiles(rows: List[Dict[str, Any]]) -> bool:
    conn = _connect()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM `user_qr_profiles`")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cur.execute(
                    """
                    INSERT INTO `user_qr_profiles`
                    (`id_number`, `name`, `role`, `created_at_utc`, `print_count`, `last_printed_at_utc`, `raw_json`)
                    VALUES (%s, %s, %s, %s, %s, %s, CAST(%s AS JSON))
                    """,
                    (
                        row.get("id_number"),
                        row.get("name"),
                        row.get("role"),
                        row.get("created_at_utc"),
                        int(row.get("print_count", 0) or 0),
                        row.get("last_printed_at_utc"),
                        json.dumps(row, ensure_ascii=False),
                    ),
                )
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        conn.close()


def load_server_settings() -> Optional[Dict[str, Any]]:
    conn = _connect()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT `raw_json` FROM `server_settings` ORDER BY `id` DESC LIMIT 1")
            row = cur.fetchone()
        if not row:
            return None
        raw = _decode_json(row.get("raw_json"), {})
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None
    finally:
        conn.close()


def save_server_settings(row: Dict[str, Any]) -> bool:
    conn = _connect()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM `server_settings`")
            cur.execute(
                """
                INSERT INTO `server_settings` (`theme`, `qrgen_base_url`, `raw_json`)
                VALUES (%s, %s, CAST(%s AS JSON))
                """,
                (
                    row.get("theme"),
                    row.get("qrgen_base_url"),
                    json.dumps(row, ensure_ascii=False),
                ),
            )
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        conn.close()


def load_finished_jobs() -> Optional[List[Dict[str, Any]]]:
    conn = _connect()
    if conn is None:
        return None
    try:
        items: List[Dict[str, Any]] = []
        with conn.cursor() as cur:
            cur.execute("SELECT `raw_json` FROM `finished_jobs` ORDER BY `id` ASC")
            for row in cur.fetchall() or []:
                item = _decode_json(row.get("raw_json"), {})
                if isinstance(item, dict):
                    items.append(item)
        return items
    except Exception:
        return None
    finally:
        conn.close()


def save_finished_jobs(rows: List[Dict[str, Any]]) -> bool:
    conn = _connect()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM `finished_jobs`")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cur.execute(
                    """
                    INSERT INTO `finished_jobs`
                    (`finished_at_utc`, `client_id`, `machine_code`, `machine_name`, `job_code`, `job_name`, `operator_id`,
                     `pack_count`, `good_total`, `butal_total`, `reject_total`, `total_good`, `startup_reject_total`, `raw_sacks_count`,
                     `downtime_last_seconds`, `downtime_reason_code`, `downtime_reason_text`, `cycle_time_current`, `maintenance_name`, `supervisor_name`,
                     `approved_by`, `approved_by_code`, `approved_by_role`, `approved_remarks`, `approved_at_utc`, `review_status`,
                     `linkage_enabled`, `linkage_job_code`, `linkage_job_name`, `linkage_role`, `linkage_group_total_jobs`,
                     `linkage_main_job_code`, `linkage_main_job_name`, `linkage_note`,
                     `reject_breakdown`, `raw_material_scans`, `raw_material_logs`, `job_payload`, `reject_review_logs`,
                     `linkage_job_payload`, `linkage_jobs`, `linkage_mirror`, `review_history`, `raw_json`)
                    VALUES
                    (%s, %s, %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s,
                     CAST(%s AS JSON), CAST(%s AS JSON), CAST(%s AS JSON), CAST(%s AS JSON), CAST(%s AS JSON),
                     CAST(%s AS JSON), CAST(%s AS JSON), CAST(%s AS JSON), CAST(%s AS JSON), CAST(%s AS JSON))
                    """,
                    (
                        row.get("finished_at_utc"),
                        row.get("client_id"),
                        row.get("machine_code"),
                        row.get("machine_name"),
                        row.get("job_code"),
                        row.get("job_name"),
                        row.get("operator_id"),
                        int(row.get("pack_count", 0) or 0),
                        int(row.get("good_total", 0) or 0),
                        int(row.get("butal_total", 0) or 0),
                        int(row.get("reject_total", 0) or 0),
                        int(row.get("total_good", 0) or 0),
                        int(row.get("startup_reject_total", 0) or 0),
                        int(row.get("raw_sacks_count", 0) or 0),
                        row.get("downtime_last_seconds"),
                        row.get("downtime_reason_code"),
                        row.get("downtime_reason_text"),
                        row.get("cycle_time_current"),
                        row.get("maintenance_name"),
                        row.get("supervisor_name"),
                        row.get("approved_by"),
                        row.get("approved_by_code"),
                        row.get("approved_by_role"),
                        row.get("approved_remarks"),
                        row.get("approved_at_utc"),
                        row.get("review_status"),
                        1 if row.get("linkage_enabled") else 0,
                        row.get("linkage_job_code"),
                        row.get("linkage_job_name"),
                        row.get("linkage_role"),
                        row.get("linkage_group_total_jobs"),
                        row.get("linkage_main_job_code"),
                        row.get("linkage_main_job_name"),
                        row.get("linkage_note"),
                        json.dumps(row.get("reject_breakdown", {}), ensure_ascii=False),
                        json.dumps(row.get("raw_material_scans", []), ensure_ascii=False),
                        json.dumps(row.get("raw_material_logs", []), ensure_ascii=False),
                        json.dumps(row.get("job_payload", {}), ensure_ascii=False),
                        json.dumps(row.get("reject_review_logs", []), ensure_ascii=False),
                        json.dumps(row.get("linkage_job_payload"), ensure_ascii=False),
                        json.dumps(row.get("linkage_jobs"), ensure_ascii=False),
                        json.dumps(row.get("linkage_mirror"), ensure_ascii=False),
                        json.dumps(row.get("review_history"), ensure_ascii=False),
                        json.dumps(row, ensure_ascii=False),
                    ),
                )
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        conn.close()


def insert_finished_job(row: Dict[str, Any]) -> bool:
    existing = load_finished_jobs()
    if existing is None:
        return False
    existing.append(row)
    return save_finished_jobs(existing)
