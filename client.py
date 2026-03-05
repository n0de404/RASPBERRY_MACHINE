# client.py
from __future__ import annotations
import json
import os
import re
import socket
import sys
import threading
import time
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Set

import requests

try:
    import pymysql
    from pymysql.cursors import DictCursor
except Exception:
    pymysql = None
    DictCursor = None

from PyQt6.QtCore import (
    Qt, QObject, QEvent, pyqtSignal, QTimer, QSize, QRectF,
    QPropertyAnimation, QEasingCurve, pyqtProperty,
)
from PyQt6.QtGui import QMovie, QPixmap, QColor, QPainter, QPen, QFont
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame, QGridLayout, QSizePolicy,
    QGraphicsDropShadowEffect, QGraphicsBlurEffect, QProgressBar, QPushButton, QComboBox, QScrollArea,
    QLineEdit, QInputDialog, QTableWidget, QTableWidgetItem, QHeaderView
)

from mappings import parse_scan, ScanResult, MACHINE_MAP, JOB_MAP, REJECT_REASON_MAP
from ui_theme import APP_STYLESHEET

try:
    import serial  # pyserial
except Exception:
    serial = None


SERVER_URL = os.environ.get("MACHINE_SERVER_URL", "http://192.168.1.178:8000")
CLIENT_ID = os.environ.get("MACHINE_CLIENT_ID", socket.gethostname())
SCANNER_MODE = os.environ.get("MACHINE_SCANNER_MODE", "auto").strip().lower()
SCANNER_COM_PORT = os.environ.get("MACHINE_SCANNER_COM_PORT", "/dev/ttyACM0").strip()
SCANNER_BAUDRATE = int(os.environ.get("MACHINE_SCANNER_BAUDRATE", "9600"))
SCANNER_TIMEOUT = float(os.environ.get("MACHINE_SCANNER_TIMEOUT", "1.0"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ANIMATIONS_DIR = os.path.join(BASE_DIR, "Animations")
IMAGES_DIR = os.path.join(BASE_DIR, "Images")
DATABASE_DIR = os.path.join(BASE_DIR, "Database")
JOB_API_CONFIG_FILE = os.path.join(DATABASE_DIR, "job_api_config.json")
INVALID_SCAN_GIF = os.environ.get(
    "MACHINE_INVALID_SCAN_GIF",
    os.path.join(ANIMATIONS_DIR, "slap-virtual-slap.gif"),
).strip()
REPAIR_GIF = os.environ.get(
    "MACHINE_REPAIR_GIF",
    os.path.join(ANIMATIONS_DIR, "repair.gif"),
).strip()
SUPERVISOR_BADGES = {"3000001": "Charlie Brown"}
QC_BADGES = {"4000001": "Lucy Van Pelt"}
REJECT_REVIEW_REQUIRED_ROTATIONS = 4
USER_QR_PROFILES_FILE = os.path.join(DATABASE_DIR, "user_qr_profiles.json")
PRODUCT_CATALOG_CACHE_FILE = os.path.join(DATABASE_DIR, "product_catalog_cache.json")
FINISHED_JOBS_FILE = os.path.join(DATABASE_DIR, "finished_jobs.json")
SQL_CONFIG_FILE = os.path.join(DATABASE_DIR, "sql_config.json")


def _load_sql_config() -> Dict[str, Any]:
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
        if os.path.exists(SQL_CONFIG_FILE):
            with open(SQL_CONFIG_FILE, "r", encoding="utf-8-sig") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                cfg.update(raw)
    except Exception:
        pass
    try:
        cfg["port"] = int(cfg.get("port", 3306) or 3306)
    except Exception:
        cfg["port"] = 3306
    return cfg


def _sql_conn():
    if pymysql is None:
        return None
    cfg = _load_sql_config()
    if not cfg.get("enabled"):
        return None
    try:
        return pymysql.connect(
            host=str(cfg.get("host", "localhost")),
            port=int(cfg.get("port", 3306)),
            user=str(cfg.get("user", "")),
            password=str(cfg.get("password", "")),
            database=str(cfg.get("database", "")),
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
            connect_timeout=int(cfg.get("connect_timeout", 5) or 5),
        )
    except Exception:
        return None


def _ensure_sql_schema() -> bool:
    conn = _sql_conn()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
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
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS `daily_role_assignments` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `assignment_date` VARCHAR(20) NOT NULL,
                  `badge_id` VARCHAR(100) NOT NULL,
                  `name` VARCHAR(255) NULL,
                  `rights` VARCHAR(50) NULL,
                  `company_role` VARCHAR(100) NULL,
                  `extra_privilege` VARCHAR(50) NULL,
                  `updated_at_utc` VARCHAR(50) NULL,
                  `raw_json` JSON NOT NULL,
                  PRIMARY KEY (`id`),
                  UNIQUE KEY `uq_daily_role_assignments_date_badge` (`assignment_date`, `badge_id`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS `active_machine_sessions` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `machine_code` VARCHAR(50) NOT NULL,
                  `saved_at_utc` VARCHAR(50) NULL,
                  `machine_name` VARCHAR(255) NULL,
                  `job_code` VARCHAR(100) NULL,
                  `job_name` VARCHAR(255) NULL,
                  `operator_id` VARCHAR(255) NULL,
                  `raw_json` JSON NOT NULL,
                  PRIMARY KEY (`id`),
                  UNIQUE KEY `uq_active_machine_sessions_machine_code` (`machine_code`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS `client_settings` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `server_url` VARCHAR(500) NULL,
                  `client_id` VARCHAR(100) NULL,
                  `scanner_mode` VARCHAR(50) NULL,
                  `scanner_com_port` VARCHAR(100) NULL,
                  `scanner_baudrate` INT NOT NULL DEFAULT 9600,
                  `scanner_timeout` DOUBLE NOT NULL DEFAULT 1.0,
                  `raw_json` JSON NOT NULL,
                  PRIMARY KEY (`id`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def _load_profiles_sql() -> List[Dict[str, Any]]:
    conn = _sql_conn()
    if conn is None:
        return []
    try:
        items: List[Dict[str, Any]] = []
        with conn.cursor() as cur:
            cur.execute("SELECT `raw_json` FROM `user_qr_profiles` ORDER BY `id` ASC")
            for row in cur.fetchall() or []:
                raw = row.get("raw_json")
                if isinstance(raw, dict):
                    items.append(raw)
                elif isinstance(raw, str):
                    try:
                        parsed = json.loads(raw)
                    except Exception:
                        parsed = None
                    if isinstance(parsed, dict):
                        items.append(parsed)
        return items
    except Exception:
        return []
    finally:
        conn.close()


def _save_profiles_sql(rows: List[Dict[str, Any]]) -> bool:
    conn = _sql_conn()
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
                    (`id_number`,`name`,`role`,`created_at_utc`,`print_count`,`last_printed_at_utc`,`raw_json`)
                    VALUES (%s,%s,%s,%s,%s,%s,CAST(%s AS JSON))
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
        return False
    finally:
        conn.close()


def _load_daily_role_assignments_sql() -> Dict[str, Any]:
    conn = _sql_conn()
    if conn is None:
        return {}
    try:
        out: Dict[str, Any] = {}
        with conn.cursor() as cur:
            cur.execute(
                "SELECT `assignment_date`, `badge_id`, `raw_json` FROM `daily_role_assignments` ORDER BY `assignment_date` ASC, `badge_id` ASC"
            )
            for row in cur.fetchall() or []:
                assignment_date = str(row.get("assignment_date") or "").strip()
                badge_id = str(row.get("badge_id") or "").strip()
                raw = row.get("raw_json")
                item = raw if isinstance(raw, dict) else None
                if item is None and isinstance(raw, str):
                    try:
                        parsed = json.loads(raw)
                    except Exception:
                        parsed = None
                    if isinstance(parsed, dict):
                        item = parsed
                if not assignment_date or not badge_id or not isinstance(item, dict):
                    continue
                date_rows = out.get(assignment_date)
                if not isinstance(date_rows, dict):
                    date_rows = {}
                    out[assignment_date] = date_rows
                date_rows[badge_id] = item
        return out
    except Exception:
        return {}
    finally:
        conn.close()


def _save_daily_role_assignments_sql(rows: Dict[str, Any]) -> bool:
    conn = _sql_conn()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM `daily_role_assignments`")
            for assignment_date, items in (rows or {}).items():
                date_key = str(assignment_date or "").strip()
                if not date_key or not isinstance(items, dict):
                    continue
                for badge_id, raw_row in items.items():
                    badge_key = str(badge_id or "").strip()
                    if not badge_key or not isinstance(raw_row, dict):
                        continue
                    cur.execute(
                        """
                        INSERT INTO `daily_role_assignments`
                        (`assignment_date`,`badge_id`,`name`,`rights`,`company_role`,`extra_privilege`,`updated_at_utc`,`raw_json`)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,CAST(%s AS JSON))
                        """,
                        (
                            date_key,
                            badge_key,
                            raw_row.get("name"),
                            raw_row.get("rights"),
                            raw_row.get("company_role"),
                            raw_row.get("extra_privilege"),
                            raw_row.get("updated_at_utc"),
                            json.dumps(raw_row, ensure_ascii=False),
                        ),
                    )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def _load_active_sessions_sql() -> Dict[str, Any]:
    conn = _sql_conn()
    if conn is None:
        return {}
    try:
        out: Dict[str, Any] = {}
        with conn.cursor() as cur:
            cur.execute("SELECT `machine_code`, `raw_json` FROM `active_machine_sessions` ORDER BY `machine_code` ASC")
            for row in cur.fetchall() or []:
                machine_code = str(row.get("machine_code") or "").strip()
                raw = row.get("raw_json")
                item = raw if isinstance(raw, dict) else None
                if item is None and isinstance(raw, str):
                    try:
                        parsed = json.loads(raw)
                    except Exception:
                        parsed = None
                    if isinstance(parsed, dict):
                        item = parsed
                if machine_code and isinstance(item, dict):
                    out[machine_code] = item
        return out
    except Exception:
        return {}
    finally:
        conn.close()


def _upsert_active_session_sql(row: Dict[str, Any]) -> bool:
    machine_code = str((row or {}).get("machine_code") or "").strip()
    if not machine_code:
        return False
    conn = _sql_conn()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO `active_machine_sessions`
                (`machine_code`,`saved_at_utc`,`machine_name`,`job_code`,`job_name`,`operator_id`,`raw_json`)
                VALUES (%s,%s,%s,%s,%s,%s,CAST(%s AS JSON))
                ON DUPLICATE KEY UPDATE
                  `saved_at_utc`=VALUES(`saved_at_utc`),
                  `machine_name`=VALUES(`machine_name`),
                  `job_code`=VALUES(`job_code`),
                  `job_name`=VALUES(`job_name`),
                  `operator_id`=VALUES(`operator_id`),
                  `raw_json`=VALUES(`raw_json`)
                """,
                (
                    machine_code,
                    row.get("saved_at_utc"),
                    row.get("machine_name"),
                    row.get("job_code"),
                    row.get("job_name"),
                    row.get("operator_id"),
                    json.dumps(row, ensure_ascii=False),
                ),
            )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def _delete_active_session_sql(machine_code: Optional[str]) -> bool:
    code = str(machine_code or "").strip()
    if not code:
        return False
    conn = _sql_conn()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM `active_machine_sessions` WHERE `machine_code`=%s", (code,))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def _load_client_settings_sql() -> Dict[str, Any]:
    conn = _sql_conn()
    if conn is None:
        return {}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT `raw_json` FROM `client_settings` ORDER BY `id` DESC LIMIT 1")
            row = cur.fetchone() or {}
        raw = row.get("raw_json")
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                return parsed
        return {}
    except Exception:
        return {}
    finally:
        conn.close()


def _save_client_settings_sql(row: Dict[str, Any]) -> bool:
    conn = _sql_conn()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM `client_settings`")
            cur.execute(
                """
                INSERT INTO `client_settings`
                (`server_url`,`client_id`,`scanner_mode`,`scanner_com_port`,`scanner_baudrate`,`scanner_timeout`,`raw_json`)
                VALUES (%s,%s,%s,%s,%s,%s,CAST(%s AS JSON))
                """,
                (
                    row.get("server_url"),
                    row.get("client_id"),
                    row.get("scanner_mode"),
                    row.get("scanner_com_port"),
                    int(row.get("scanner_baudrate", SCANNER_BAUDRATE) or SCANNER_BAUDRATE),
                    float(row.get("scanner_timeout", SCANNER_TIMEOUT) or SCANNER_TIMEOUT),
                    json.dumps(row, ensure_ascii=False),
                ),
            )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def _migrate_active_sessions_json_to_sql() -> bool:
    legacy_path = os.path.join(DATABASE_DIR, "active_machine_sessions.json")
    if not os.path.exists(legacy_path):
        return True
    sql_rows = _load_active_sessions_sql()
    if sql_rows:
        return True
    try:
        with open(legacy_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except Exception:
        return False
    if not isinstance(loaded, dict):
        return False
    ok = True
    for machine_code, row in loaded.items():
        if not isinstance(row, dict):
            continue
        payload = dict(row)
        payload["machine_code"] = str(payload.get("machine_code") or machine_code or "").strip()
        if not payload["machine_code"]:
            ok = False
            continue
        ok = _upsert_active_session_sql(payload) and ok
    return ok


def _insert_finished_job_sql(row: Dict[str, Any]) -> bool:
    conn = _sql_conn()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO `finished_jobs`
                (`finished_at_utc`,`client_id`,`machine_code`,`machine_name`,`job_code`,`job_name`,`operator_id`,
                 `pack_count`,`good_total`,`butal_total`,`reject_total`,`total_good`,`startup_reject_total`,`raw_sacks_count`,
                 `downtime_last_seconds`,`downtime_reason_code`,`downtime_reason_text`,`cycle_time_current`,`maintenance_name`,`supervisor_name`,
                 `approved_by`,`approved_by_code`,`approved_by_role`,`approved_remarks`,`approved_at_utc`,`review_status`,
                 `linkage_enabled`,`linkage_job_code`,`linkage_job_name`,`linkage_role`,`linkage_group_total_jobs`,
                 `linkage_main_job_code`,`linkage_main_job_name`,`linkage_note`,
                 `reject_breakdown`,`raw_material_scans`,`raw_material_logs`,`job_payload`,`reject_review_logs`,
                 `linkage_job_payload`,`linkage_jobs`,`linkage_mirror`,`review_history`,`raw_json`)
                VALUES
                (%s,%s,%s,%s,%s,%s,%s,
                 %s,%s,%s,%s,%s,%s,%s,
                 %s,%s,%s,%s,%s,%s,
                 %s,%s,%s,%s,%s,%s,
                 %s,%s,%s,%s,%s,
                 %s,%s,%s,
                 CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),
                 CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON))
                """,
                (
                    row.get("finished_at_utc"), row.get("client_id"), row.get("machine_code"), row.get("machine_name"), row.get("job_code"), row.get("job_name"), row.get("operator_id"),
                    int(row.get("pack_count", 0) or 0), int(row.get("good_total", 0) or 0), int(row.get("butal_total", 0) or 0), int(row.get("reject_total", 0) or 0), int(row.get("total_good", 0) or 0), int(row.get("startup_reject_total", 0) or 0), int(row.get("raw_sacks_count", 0) or 0),
                    row.get("downtime_last_seconds"), row.get("downtime_reason_code"), row.get("downtime_reason_text"), row.get("cycle_time_current"), row.get("maintenance_name"), row.get("supervisor_name"),
                    row.get("approved_by"), row.get("approved_by_code"), row.get("approved_by_role"), row.get("approved_remarks"), row.get("approved_at_utc"), row.get("review_status"),
                    1 if row.get("linkage_enabled") else 0, row.get("linkage_job_code"), row.get("linkage_job_name"), row.get("linkage_role"), row.get("linkage_group_total_jobs"),
                    row.get("linkage_main_job_code"), row.get("linkage_main_job_name"), row.get("linkage_note"),
                    json.dumps(row.get("reject_breakdown", {}), ensure_ascii=False), json.dumps(row.get("raw_material_scans", []), ensure_ascii=False), json.dumps(row.get("raw_material_logs", []), ensure_ascii=False), json.dumps(row.get("job_payload", {}), ensure_ascii=False), json.dumps(row.get("reject_review_logs", []), ensure_ascii=False),
                    json.dumps(row.get("linkage_job_payload"), ensure_ascii=False), json.dumps(row.get("linkage_jobs"), ensure_ascii=False), json.dumps(row.get("linkage_mirror"), ensure_ascii=False), json.dumps(row.get("review_history"), ensure_ascii=False), json.dumps(row, ensure_ascii=False),
                ),
            )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


_ensure_sql_schema()
_migrate_active_sessions_json_to_sql()


def _load_client_config() -> Dict[str, Any]:
    defaults = {
        "server_url": SERVER_URL,
        "client_id": CLIENT_ID,
        "scanner_mode": SCANNER_MODE,
        "scanner_com_port": SCANNER_COM_PORT,
        "scanner_baudrate": SCANNER_BAUDRATE,
        "scanner_timeout": SCANNER_TIMEOUT,
    }
    raw = _load_client_settings_sql()
    if isinstance(raw, dict):
        defaults.update(raw)

    defaults["server_url"] = str(defaults.get("server_url", SERVER_URL)).strip().rstrip("/")
    defaults["client_id"] = str(defaults.get("client_id", CLIENT_ID)).strip() or CLIENT_ID
    defaults["scanner_mode"] = str(defaults.get("scanner_mode", SCANNER_MODE)).strip().lower()
    defaults["scanner_com_port"] = str(defaults.get("scanner_com_port", SCANNER_COM_PORT)).strip() or SCANNER_COM_PORT
    try:
        defaults["scanner_baudrate"] = int(defaults.get("scanner_baudrate", SCANNER_BAUDRATE))
    except Exception:
        defaults["scanner_baudrate"] = SCANNER_BAUDRATE
    try:
        defaults["scanner_timeout"] = float(defaults.get("scanner_timeout", SCANNER_TIMEOUT))
    except Exception:
        defaults["scanner_timeout"] = SCANNER_TIMEOUT
    return defaults


def _load_job_api_config() -> Dict[str, Any]:
    cfg = {
        "base_url": "",
        "user": "svcapiroleprod",
        "password": "0t1docmtl$tm",
        "bearer_token": "",
        "token_expires_at_epoch": 0,
        "ttl_seconds": 604800,
        "force_new_token": True,
    }
    try:
        if os.path.exists(JOB_API_CONFIG_FILE):
            # Accept files saved with UTF-8 BOM (common from some Windows editors).
            with open(JOB_API_CONFIG_FILE, "r", encoding="utf-8-sig") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                # Load top-level values first, then fill missing values from a Product_ID.json-like shape:
                # { "bms": { "base_url": ".../IMS/v1", "username": "...", "password": "...", ... } }
                cfg.update(raw)
                if not str(cfg.get("user", "")).strip():
                    cfg["user"] = raw.get("username") or raw.get("user") or cfg["user"]
                if isinstance(raw.get("bms"), dict):
                    bms = raw.get("bms") or {}
                    if not str(cfg.get("base_url", "")).strip():
                        cfg["base_url"] = bms.get("base_url", cfg["base_url"])
                    if not str(cfg.get("user", "")).strip():
                        cfg["user"] = bms.get("username") or bms.get("user") or cfg["user"]
                    if not str(cfg.get("password", "")):
                        cfg["password"] = bms.get("password", cfg["password"])
                    if "ttl_seconds" not in raw and "ttl_seconds" in bms:
                        cfg["ttl_seconds"] = bms.get("ttl_seconds", cfg["ttl_seconds"])
                    if "force_new_token" not in raw and "force_new_token" in bms:
                        cfg["force_new_token"] = bms.get("force_new_token", cfg["force_new_token"])
    except Exception:
        pass
    cfg["base_url"] = str(cfg.get("base_url", "")).strip().rstrip("/")
    if cfg["base_url"].endswith("/jobs"):
        cfg["base_url"] = cfg["base_url"][:-5].rstrip("/")
    cfg["user"] = str(cfg.get("user", "")).strip()
    cfg["password"] = str(cfg.get("password", ""))
    cfg["bearer_token"] = str(cfg.get("bearer_token", ""))
    try:
        cfg["token_expires_at_epoch"] = int(float(cfg.get("token_expires_at_epoch", 0) or 0))
    except Exception:
        cfg["token_expires_at_epoch"] = 0
    try:
        cfg["ttl_seconds"] = int(cfg.get("ttl_seconds", 604800) or 604800)
    except Exception:
        cfg["ttl_seconds"] = 604800
    cfg["force_new_token"] = bool(cfg.get("force_new_token", True))
    return cfg


def _save_job_api_config(cfg: Dict[str, Any]):
    try:
        os.makedirs(DATABASE_DIR, exist_ok=True)
        with open(JOB_API_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _save_client_config(cfg: Dict[str, Any]):
    _save_client_settings_sql(cfg)


def _machine_display_name(machine_code: Optional[str], machine_name: Optional[str] = None) -> str:
    code = str(machine_code or "").strip()
    if code and code in MACHINE_MAP:
        return MACHINE_MAP[code]
    name = str(machine_name or "").strip()
    return name or (code if code else "-")

REJECT_DETAIL_ITEMS = [
    ("BM", "BURN MARK"),
    ("CS", "COLOR STREAK"),
    ("CO", "CONTAMINATION"),
    ("CR", "CRACK/BRITTLE"),
    ("DI", "DISCOLORATION"),
    ("EM", "EJECTOR MARK"),
    ("FL", "FLASHES"),
    ("FM", "FLOW MARK/ WRINKLE"),
    ("NO", "NO SHOT"),
    ("OC", "OVER-CUT"),
    ("SC", "SCRATCH"),
    ("SS", "SHORT SHOT"),
    ("SI", "SILICONE MARK"),
    ("SK", "SILVER STREAK"),
    ("SM", "SINK MARK"),
    ("ST", "STUCK"),
    ("VO", "VOID"),
    ("WA", "WARP"),
    ("WM", "WATER MARK"),
    ("WL", "WELD LINE"),
]

PRODUCTION_DAILY_REPORT_ITEMS = [
    ("01", "Machine Issue/Breakdown/Repair"),
    ("02", "Machine Adjustment - Parameters"),
    ("03", "Material Issue/Delay/Drying"),
    ("04", "Mold Issue/Repair/Cleaning"),
    ("05", "No Manpower/Operator"),
    ("06", "Material Color Change"),
    ("07", "Mold Change"),
    ("08", "Preventive Maintenance"),
    ("09", "No production schedule"),
    ("10", "Start-up/Shutdown (1st&Last Day)"),
    ("11", "Shift Meeting/Shift Turn-over"),
    ("12", "Mold / Color Testing"),
    ("13", "Power interruption"),
    ("14", "Robot Set-up/Adjustment"),
    ("15", "Others"),
]


@dataclass
class ClientState:
    machine_code: Optional[str] = None
    machine_name: Optional[str] = None
    job_code: Optional[str] = None
    job_name: Optional[str] = None
    operator_id: Optional[str] = None

    pack_count: int = 0
    good_total: int = 0
    butal_total: int = 0
    reject_total: int = 0
    reject_breakdown: Dict[str, int] = None

    waiting_reject_reason: bool = False
    waiting_production_report_reason: bool = False
    waiting_cycle_time_input: bool = False
    waiting_initial_cycle_time_input: bool = False
    waiting_initial_cycle_qc_confirm: bool = False
    waiting_cycle_time_confirm_popup: bool = False
    cycle_time_confirm_phase: int = 0
    waiting_maintenance_qr: bool = False
    waiting_supervisor_qr: bool = False
    waiting_operator_downtime_confirm: bool = False
    showing_reject_summary: bool = False
    reject_summary_last_scanned_at: Optional[str] = None
    job_payload: Dict[str, Any] = None
    downtime_reason_code: Optional[str] = None
    downtime_reason_text: Optional[str] = None
    downtime_started_at: Optional[float] = None
    downtime_last_seconds: Optional[int] = None
    downtime_active: bool = False
    cycle_time_current: Optional[str] = None
    cycle_time_new_input: str = ""
    cycle_time_confirmed_by: Optional[str] = None
    cycle_time_confirm_actor_code: Optional[str] = None
    cycle_time_confirm_actor_name: Optional[str] = None
    cycle_time_confirm_actor_role: Optional[str] = None
    maintenance_name: Optional[str] = None
    supervisor_name: Optional[str] = None
    raw_sacks_count: int = 0
    raw_material_scans: List[str] = None
    raw_material_logs: List[Dict[str, Any]] = None
    raw_material_unique_keys: Set[str] = None
    product_pack_history_logs: List[Dict[str, Any]] = None
    startup_reject_total: int = 0
    reject_review_open: bool = False
    reject_review_phase: int = 0
    reject_review_actor_code: Optional[str] = None
    reject_review_actor_name: Optional[str] = None
    reject_review_actor_role: Optional[str] = None
    reject_review_logs: List[Dict[str, Any]] = None
    waiting_linkage_job_scan: bool = False
    linkage_enabled: bool = False
    linkage_job_code: Optional[str] = None
    linkage_job_name: Optional[str] = None
    linkage_job_payload: Dict[str, Any] = None
    linkage_jobs: List[Dict[str, Any]] = None
    operator_shift_logs: List[Dict[str, Any]] = None
    operator_shift_index: int = 0
    operator_shift_started_at: Optional[str] = None
    operator_shift_baseline_pack_count: int = 0
    operator_shift_baseline_good_total: int = 0
    operator_shift_baseline_butal_total: int = 0
    operator_shift_baseline_reject_total: int = 0
    operator_shift_baseline_startup_reject_total: int = 0
    operator_shift_baseline_raw_sacks_count: int = 0
    operator_shift_baseline_reject_breakdown: Dict[str, int] = None
    operator_shift_baseline_raw_material_logs_len: int = 0
    operator_shift_baseline_product_pack_history_logs_len: int = 0
    operator_shift_baseline_reject_review_logs_len: int = 0

    def __post_init__(self):
        if self.reject_breakdown is None:
            self.reject_breakdown = {}
        if self.job_payload is None:
            self.job_payload = {}
        if self.raw_material_scans is None:
            self.raw_material_scans = []
        if self.raw_material_logs is None:
            self.raw_material_logs = []
        if self.raw_material_unique_keys is None:
            self.raw_material_unique_keys = set()
        if self.product_pack_history_logs is None:
            self.product_pack_history_logs = []
        if self.reject_review_logs is None:
            self.reject_review_logs = []
        if self.linkage_job_payload is None:
            self.linkage_job_payload = {}
        if self.linkage_jobs is None:
            self.linkage_jobs = []
        if self.operator_shift_logs is None:
            self.operator_shift_logs = []
        if self.operator_shift_baseline_reject_breakdown is None:
            self.operator_shift_baseline_reject_breakdown = {}


@dataclass
class StatusPulse:
    age: float


class ScannerFilter(QObject):
    scanned = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._buf = []

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()

            # scanners usually end with Enter/Return
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                text = "".join(self._buf).strip()
                self._buf.clear()
                if text:
                    self.scanned.emit(text)
                return True

            # ignore modifier keys
            if key in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
                return False

            ch = event.text()
            if ch:
                self._buf.append(ch)
                return True

        return False


class HeartbeatBorderPulseOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.pulses: List[StatusPulse] = []
        self.t = 0.0
        self.beat_pattern = [0.00]
        self.beat_cycle = 1.00
        self._next_cycle_time = 0.0
        self._pattern_index = 0
        self._active_mode = False
        self._target_rect = QRectF()
        self._duration = 1.2
        self._start_out = 2.0
        self._end_out = 14.0
        self._glow_scale = 1.0
        self._core_scale = 1.0
        self._alpha_scale = 1.0

    def set_target_rect(self, rect: QRectF):
        self._target_rect = QRectF(rect)
        self.update()

    def set_pulse_profile(
        self,
        *,
        duration: float = 1.2,
        start_out: float = 2.0,
        end_out: float = 14.0,
        glow_scale: float = 1.0,
        core_scale: float = 1.0,
        alpha_scale: float = 1.0,
    ):
        self._duration = max(0.2, float(duration))
        self._start_out = max(0.0, float(start_out))
        self._end_out = max(self._start_out, float(end_out))
        self._glow_scale = max(0.0, float(glow_scale))
        self._core_scale = max(0.0, float(core_scale))
        self._alpha_scale = max(0.0, float(alpha_scale))
        self.update()

    def set_mode(self, active: bool):
        self._active_mode = bool(active)

    def trigger_now(self):
        self.pulses.append(StatusPulse(age=0.0))
        self.update()

    def advance(self, enabled: bool, dt: float = 0.06):
        if not enabled:
            if self.pulses:
                self.pulses = []
                self.update()
            return

        self.t += dt
        if self.t >= self._next_cycle_time:
            self._next_cycle_time = self.t + self.beat_cycle
            self._pattern_index = 0

        cycle_start = self._next_cycle_time - self.beat_cycle
        while self._pattern_index < len(self.beat_pattern) and self.t >= cycle_start + self.beat_pattern[self._pattern_index]:
            self.pulses.append(StatusPulse(age=0.0))
            self._pattern_index += 1

        max_age = self._duration
        keep: List[StatusPulse] = []
        for pl in self.pulses:
            pl.age += dt
            if pl.age <= max_age:
                keep.append(pl)
        self.pulses = keep
        self.update()

    def paintEvent(self, _):
        if not self.pulses or self._target_rect.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for pl in self.pulses:
            self._draw_pulse_ring(p, self._target_rect, 14.0, pl.age)
        p.end()

    def _draw_pulse_ring(self, p: QPainter, card: QRectF, base_radius: float, age: float):
        duration = self._duration
        u = max(0.0, min(1.0, age / duration))
        start_out = self._start_out
        end_out = self._end_out
        out = start_out + (end_out - start_out) * (u ** 0.85)
        alpha = int(255 * self._alpha_scale * (1.0 - u) ** 1.6)
        glow_w = self._glow_scale * (7.0 * (1.0 - u) + 1.4)
        core_w = self._core_scale * (2.0 * (1.0 - u) + 1.0)
        base = QColor("#22c55e" if self._active_mode else "#f97316")

        ring = QRectF(
            card.left() - out,
            card.top() - out,
            card.width() + out * 2,
            card.height() + out * 2,
        )
        rr = base_radius + out

        glow = QColor(base)
        glow.setAlpha(max(0, min(120, int(alpha * 0.42))))
        p.setPen(QPen(glow, glow_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(ring, rr, rr)

        core = QColor(base)
        core.setAlpha(max(0, min(255, int(alpha * 0.88))))
        p.setPen(QPen(core, core_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawRoundedRect(ring, rr, rr)


class SuccessCheck(QWidget):
    def __init__(self, size=140, parent=None):
        super().__init__(parent)

        self._progress = 0.0
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")

        self.animation = QPropertyAnimation(self, b"progress")
        self.animation.setDuration(650)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def start(self):
        self.animation.stop()
        self.setProgress(0.0)
        self.animation.start()

    def getProgress(self):
        return self._progress

    def setProgress(self, value):
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    progress = pyqtProperty(float, fget=getProgress, fset=setProgress)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        padding = int(min(w, h) * 0.12)
        rect = QRectF(padding, padding, w - padding * 2, h - padding * 2)

        pen = QPen(QColor(22, 163, 74))
        pen.setWidth(int(min(w, h) * 0.07))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        circle_phase = min(self._progress / 0.65, 1.0)
        check_phase = 0.0 if self._progress < 0.65 else min((self._progress - 0.65) / 0.35, 1.0)

        start_angle = int(270 * 16)
        span_angle = int(-360 * 16 * circle_phase)
        painter.drawArc(rect, start_angle, span_angle)

        if check_phase > 0:
            x0 = rect.left()
            y0 = rect.top()
            rw = rect.width()
            rh = rect.height()

            a = (x0 + 0.28 * rw, y0 + 0.55 * rh)
            b = (x0 + 0.44 * rw, y0 + 0.70 * rh)
            c = (x0 + 0.74 * rw, y0 + 0.38 * rh)

            if check_phase <= 0.5:
                t = check_phase / 0.5
                bx = a[0] + (b[0] - a[0]) * t
                by = a[1] + (b[1] - a[1]) * t
                painter.drawLine(int(a[0]), int(a[1]), int(bx), int(by))
            else:
                painter.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))
                t = (check_phase - 0.5) / 0.5
                cx = b[0] + (c[0] - b[0]) * t
                cy = b[1] + (c[1] - b[1]) * t
                painter.drawLine(int(b[0]), int(b[1]), int(cx), int(cy))


class ClientUI(QWidget):
    UI_BASE_WIDTH = 1920
    UI_BASE_HEIGHT = 1080
    UI_MIN_SCALE = 0.50
    UI_MAX_SCALE = 1.35

    scan_received = pyqtSignal(str)
    scanner_status = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.state = ClientState()
        self.client_config = _load_client_config()
        self.job_api_config = _load_job_api_config()
        self._identity_sync_lock = threading.Lock()
        self._identity_sync_inflight = False
        self._identity_sync_last_attempt = 0.0
        self._identity_sync_last_ok = 0.0
        self._serial_stop = threading.Event()
        self._serial_thread: Optional[threading.Thread] = None
        self._motion_index = 0
        self._label_icon_candidates = {
            "machine": ["machine.png", "machine.jpg", "machine.jpeg", "machine_icon.png", "icon_machine.png"],
            "job": ["job-seeker.png", "job.png", "job.jpg", "job.jpeg", "job_icon.png", "icon_job.png"],
            "operator": ["worker.png", "operator.png", "operator.jpg", "operator.jpeg", "operator_icon.png", "icon_operator.png"],
            "raw-material": ["raw-material.png"],
            "cycle": ["cycle.png"],
            "downtime": ["downtime (1).png"],
        }
        self._ui_scale = 1.0
        self._ui_scale_applied = False
        self._ui_scale_bases: Dict[int, Dict[str, Any]] = {}
        self._ui_layout_scale_bases: Dict[int, Dict[str, Any]] = {}
        self._product_history_page = 0
        self._product_history_page_size = 15
        self._product_catalog_name_by_id: Optional[Dict[str, str]] = None

        self.setWindowTitle("Machine Client Dashboard")
        self.setMinimumSize(0, 0)
        self.setObjectName("ClientUIRoot")
        bg_image = os.path.join(IMAGES_DIR, "background.png").replace("\\", "/")
        self.setStyleSheet(
            APP_STYLESHEET
            + f"""
QWidget#ClientUIRoot {{
    background-image: url("{bg_image}");
    background-position: center;
    background-repeat: no-repeat;
}}
"""
        )
        self.enable_check_animation = True
        self.enable_flashing_lights = True
        self.enable_pulse_effects = True

        root = QVBoxLayout()
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        leftWrap = QWidget()
        self.leftWrap = leftWrap
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(6)
        leftWrap.setLayout(left)

        self.pageTitle = QLabel("Machine Dashboard")
        self.pageTitle.setObjectName("PageTitle")
        self.headerDateTime = QLabel("")
        self.headerDateTime.setObjectName("MetaValue")
        self.headerDateTime.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.btnSettings = QPushButton("\u2699")
        self.btnSettings.setObjectName("SettingsButton")
        self.btnSettings.setFixedSize(40, 40)
        self.btnSettings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btnSettings.clicked.connect(self._show_settings_overlay)

        headerRow = QHBoxLayout()
        headerRow.setContentsMargins(0, 0, 0, 0)
        headerRow.setSpacing(8)
        headerRow.addWidget(self.btnSettings, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        headerRow.addWidget(self.pageTitle, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        headerRow.addWidget(self.headerDateTime, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.headerDivider = QFrame()
        self.headerDivider.setFrameShape(QFrame.Shape.HLine)
        self.headerDivider.setFrameShadow(QFrame.Shadow.Plain)
        self.headerDivider.setStyleSheet("background: rgba(148, 163, 184, 0.45); min-height: 1px; max-height: 1px; border: none;")

        self._banner_base_text = "Scan MACHINE QR to start"
        self.banner = QLabel(self._banner_base_text)
        self.banner.setObjectName("Banner")
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setWordWrap(True)
        self.banner.setMinimumHeight(68)
        self.banner.setMaximumHeight(92)
        self.banner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.status = QLabel("Waiting...")
        self.status.setObjectName("StatusBar")
        self.status.setWordWrap(True)
        self.status.setFixedHeight(44)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.machineAnim = QLabel("[M] ----")
        self.machineAnim.setObjectName("MachineAnim")
        self.machineAnim.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.machineAnim.setProperty("mode", "idle")
        self.machineAnim.setProperty("pulse", "0")
        self.scanSectionDivider = QFrame()
        self.scanSectionDivider.setFrameShape(QFrame.Shape.HLine)
        self.scanSectionDivider.setFrameShadow(QFrame.Shadow.Plain)
        self.scanSectionDivider.setStyleSheet("background: rgba(148, 163, 184, 0.35); min-height: 1px; max-height: 1px; border: none;")

        left.addWidget(self.banner, 0)
        left.addWidget(self.scanSectionDivider)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        # Production panel
        self.cardProductionOuter, self.cardProduction = self._make_double_layer_card("Production")
        # Keep only the stat cards visible for this strip.
        self.cardProductionOuter.setStyleSheet("QFrame#LeftCardOuter { background: transparent; border: none; }")
        self.cardProduction.setStyleSheet("QFrame#LeftCardInner { background: transparent; border: none; }")
        self.cardProduction.layout().setContentsMargins(0, 0, 0, 0)
        self.cardProduction.layout().setSpacing(0)
        _production_title = self.cardProduction.findChild(QLabel, "SectionTitle")
        if _production_title is not None:
            _production_title.hide()
        statRow = QHBoxLayout()
        statRow.setSpacing(6)
        self.lblPack = QLabel("0")
        self.lblGood = QLabel("0")
        self.lblButal = QLabel("0")
        self.lblReject = QLabel("0")
        self.lblTotalGood = QLabel("0")
        self.cardStatPack = self._make_stat_card("Pack", self.lblPack, "StatPack")
        self.cardStatGood = self._make_stat_card("Good", self.lblGood, "StatGood")
        self.cardStatButal = self._make_stat_card("Butal", self.lblButal, "StatButal")
        self.cardStatReject = self._make_stat_card("Reject", self.lblReject, "StatReject")
        self.cardStatTotalGood = self._make_stat_card("Total Good", self.lblTotalGood, "StatTotalGood")
        for card in (
            self.cardStatPack,
            self.cardStatGood,
            self.cardStatButal,
            self.cardStatReject,
            self.cardStatTotalGood,
        ):
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            card.setMinimumHeight(60)
            statRow.addWidget(card, 1)
        self.cardProduction.layout().addLayout(statRow)
        self.cardProductionOuter.setMinimumHeight(100)
        self.cardProductionOuter.setMaximumHeight(120)
        self.cardProductionOuter.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        grid.addWidget(self.cardProductionOuter, 0, 0, 1, 2)

        # Session panel
        self.cardSessionOuter, self.cardSession = self._make_double_layer_card("Session")
        _session_title = self.cardSession.findChild(QLabel, "SectionTitle")
        if _session_title is not None:
            _session_title.hide()
        sessionGrid = QGridLayout()
        sessionGrid.setHorizontalSpacing(12)
        sessionGrid.setVerticalSpacing(8)
        sessionGrid.setContentsMargins(0, 0, 0, 0)
        sessionGrid.setColumnStretch(0, 0)
        sessionGrid.setColumnStretch(1, 1)

        self.lblMachine = QLabel("-")
        self.lblJob = QLabel("-")
        self.lblOperator = QLabel("-")
        self.machineAnim.setText("Machine Status: IDLE")
        self.machineAnim.setFixedHeight(40)
        self.machineAnim.setMinimumWidth(0)
        self.machineAnim.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.machineAnim.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _machine_status_spacer = QWidget()
        _machine_status_spacer.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sessionGrid.addWidget(_machine_status_spacer, 0, 0)
        sessionGrid.addWidget(self.machineAnim, 0, 1)

        session_rows = [
            ("Machine", self.lblMachine),
            ("Job", self.lblJob),
            ("Operator", self.lblOperator),
        ]
        for i, (name, value_lbl) in enumerate(session_rows, start=1):
            value_lbl.setObjectName("MetaValue")
            value_lbl.setMinimumWidth(260)
            value_lbl.setFixedHeight(40)
            value_lbl.setWordWrap(True)
            value_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            value_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            session_value_widget = value_lbl
            sessionGrid.addWidget(session_value_widget, i, 0, 1, 2)
        self.cardSession.layout().addLayout(sessionGrid)
        self.machinePulseOverlay = HeartbeatBorderPulseOverlay(self.cardSession)
        self.machinePulseOverlay.setGeometry(self.cardSession.rect())
        self.machinePulseOverlay.set_pulse_profile(
            duration=1.0,
            start_out=1.0,
            end_out=8.0,
            glow_scale=0.65,
            core_scale=0.75,
            alpha_scale=0.72,
        )
        self.machinePulseOverlay.raise_()
        self.cardSessionOuter.setMinimumHeight(186)
        self.cardSessionOuter.setMaximumHeight(228)
        self.cardSessionOuter.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        # Reject detail panel
        self.cardRejectOuter, self.cardReject = self._make_double_layer_card("Reject Details")
        self.rejectDetailTable = QTableWidget(1, len(REJECT_DETAIL_ITEMS))
        self.rejectDetailTable.setHorizontalHeaderLabels([code for code, _ in REJECT_DETAIL_ITEMS])
        self.rejectDetailTable.setAlternatingRowColors(False)
        self.rejectDetailTable.setWordWrap(False)
        self.rejectDetailTable.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rejectDetailTable.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.rejectDetailTable.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rejectDetailTable.verticalHeader().setVisible(False)
        self.rejectDetailTable.verticalHeader().setDefaultSectionSize(32)
        self.rejectDetailTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.rejectDetailTable.setShowGrid(False)
        self.rejectDetailTable.setMinimumHeight(72)
        self.rejectDetailTable.setStyleSheet(
            "QTableWidget { background: transparent; border: none; gridline-color: transparent; }"
            "QHeaderView::section { background: rgba(226,232,240,0.9); color: #0f172a; font-weight: 900;"
            " border: none; border-right: 1px solid rgba(148,163,184,0.45);"
            " border-bottom: 1px solid rgba(148,163,184,0.5); padding: 6px; }"
            "QTableWidget::item { padding: 2px; color: #0f172a; font-weight: 900;"
            " border-right: 1px solid rgba(148,163,184,0.35); background: transparent; }"
        )
        self.reject_detail_labels: Dict[str, QTableWidgetItem] = {}
        for col, (code, label) in enumerate(REJECT_DETAIL_ITEMS):
            qty_item = QTableWidgetItem("0")
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.rejectDetailTable.setItem(0, col, qty_item)
            self.reject_detail_labels[code] = qty_item

        self.cardReject.layout().addWidget(self.rejectDetailTable)
        self.cardRejectOuter.setMinimumHeight(104)
        self.cardRejectOuter.setMaximumHeight(122)
        self.cardRejectOuter.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        grid.addWidget(self.cardRejectOuter, 2, 0, 1, 2)

        # Product parts panel
        self.cardJobDetailsOuter, self.cardJobDetails = self._make_double_layer_card("PRODUCT PARTS")
        self.jobPartsTable = QTableWidget(0, 6)
        self.jobPartsTable.setHorizontalHeaderLabels(
            ["Part Product ID", "SKU", "Name", "Part Qty/Unit", "Request Part Qty", "Approve/Complete"]
        )
        self.jobPartsTable.setAlternatingRowColors(True)
        self.jobPartsTable.setWordWrap(True)
        self.jobPartsTable.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.jobPartsTable.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.jobPartsTable.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.jobPartsTable.verticalHeader().setVisible(False)
        self.jobPartsTable.verticalHeader().setDefaultSectionSize(30)
        self.jobPartsTable.horizontalHeader().setStretchLastSection(False)
        self.jobPartsTable.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.jobPartsTable.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.jobPartsTable.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.jobPartsTable.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.jobPartsTable.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.jobPartsTable.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        # Size table to show up to 10 visible rows without clipping.
        parts_row_h = self.jobPartsTable.verticalHeader().defaultSectionSize()
        parts_header_h = self.jobPartsTable.horizontalHeader().height()
        parts_frame_h = self.jobPartsTable.frameWidth() * 2
        parts_target_h = parts_header_h + (parts_row_h * 10) + parts_frame_h
        self.jobPartsTable.setMinimumHeight(parts_target_h)
        self.jobPartsTable.setMaximumHeight(parts_target_h)
        self.cardJobDetails.layout().addWidget(self.jobPartsTable)
        self.cardJobDetails.layout().addStretch(1)
        self.cardJobDetailsOuter.setMinimumHeight(280)
        self.cardJobDetailsOuter.setMaximumHeight(360)
        self.cardJobDetailsOuter.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        # Job details panel beside Session.
        self.cardActivityOuter, self.cardActivity = self._make_double_layer_card("Job Details")
        _job_details_title = self.cardActivity.findChild(QLabel, "SectionTitle")
        if _job_details_title is not None:
            _job_details_title.hide()
        self.cardActivity.layout().setContentsMargins(0, 0, 0, 0)
        self.cardActivity.layout().setSpacing(4)
        activityGrid = QGridLayout()
        activityGrid.setHorizontalSpacing(12)
        activityGrid.setVerticalSpacing(8)
        activityGrid.setContentsMargins(0, 0, 0, 0)
        activityGrid.setColumnStretch(0, 0)
        activityGrid.setColumnStretch(1, 1)
        self.lblActivityMold = QLabel("-")
        self.lblActivityColor = QLabel("-")
        self.lblActivityCavities = QLabel("-")
        self.lblActivitySticker = QLabel("-")
        activity_rows = [
            ("Mold", self.lblActivityMold),
            ("Color", self.lblActivityColor),
            ("Cavities", self.lblActivityCavities),
            ("Sticker Label", self.lblActivitySticker),
        ]
        for i, (name, value_lbl) in enumerate(activity_rows):
            value_lbl.setObjectName("MetaValue")
            value_lbl.setWordWrap(True)
            value_lbl.setMinimumWidth(260)
            value_lbl.setFixedHeight(40)
            value_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            value_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            activityGrid.addWidget(value_lbl, i, 0, 1, 2, Qt.AlignmentFlag.AlignVCenter)
        self.cardActivity.layout().addLayout(activityGrid)
        self.cardActivityOuter.setMinimumHeight(196)
        self.cardActivityOuter.setMaximumHeight(238)
        self.cardActivityOuter.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        # Unified frame: Session + Job Details in one shared outer frame.
        self.cardSessionActivityOuter, self.cardSessionActivity = self._make_double_layer_card("")
        _session_activity_title = self.cardSessionActivity.findChild(QLabel, "SectionTitle")
        if _session_activity_title is not None:
            # Remove the default placeholder title entirely so it doesn't reserve top space.
            self.cardSessionActivity.layout().removeWidget(_session_activity_title)
            _session_activity_title.deleteLater()
        self.cardSessionActivity.layout().setContentsMargins(0, 0, 0, 0)
        self.cardSessionActivity.layout().setSpacing(6)
        self.jobDetailsUnifiedTitle = QLabel("Job Details")
        self.jobDetailsUnifiedTitle.setObjectName("SectionTitle")
        self.jobDetailsUnifiedTitle.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.cardSessionActivity.layout().setContentsMargins(10, 6, 10, 12)
        self.cardSessionActivity.layout().addWidget(self.jobDetailsUnifiedTitle, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        # Remove individual outer borders so only one frame is visible.
        self.cardSessionOuter.setStyleSheet("QFrame#LeftCardOuter { background: transparent; border: none; }")
        self.cardActivityOuter.setStyleSheet("QFrame#LeftCardOuter { background: transparent; border: none; }")
        # Remove individual inner frames as well.
        self.cardSession.setStyleSheet("QFrame#LeftCardInner { background: transparent; border: none; }")
        self.cardActivity.setStyleSheet("QFrame#LeftCardInner { background: transparent; border: none; }")

        # Top-grid cycle fields (separate widgets from right panel cycle widgets).
        self.topCycleCount = QLabel("Confirmed by: -")
        self.topCycleCount.setObjectName("MetaValue")
        self.topCycleCount.setFixedHeight(40)
        self.topCycleCurrent = QLabel("Cycle Time: ")
        self.topCycleCurrent.setObjectName("MetaValue")
        self.topCycleCurrent.setFixedHeight(40)
        self.topCycleStd = QLabel("Std Cycle Time: -")
        self.topCycleStd.setObjectName("MetaValue")
        self.topCycleStd.setFixedHeight(40)
        self.topCycleQtyShift = QLabel("Qty / Shift: -")
        self.topCycleQtyShift.setObjectName("MetaValue")
        self.topCycleQtyShift.setFixedHeight(40)

        unified_fields_grid = QGridLayout()
        unified_fields_grid.setContentsMargins(0, 0, 0, 0)
        unified_fields_grid.setHorizontalSpacing(12)
        unified_fields_grid.setVerticalSpacing(8)
        unified_fields_grid.setColumnStretch(0, 1)
        unified_fields_grid.setColumnStretch(1, 1)
        unified_fields_grid.setColumnStretch(2, 1)

        unified_fields_grid.addWidget(self.machineAnim, 0, 0)
        unified_fields_grid.addWidget(self.lblActivityMold, 0, 1)
        unified_fields_grid.addWidget(self.topCycleQtyShift, 0, 2)
        unified_fields_grid.addWidget(self.lblMachine, 1, 0)
        unified_fields_grid.addWidget(self.lblActivityColor, 1, 1)
        unified_fields_grid.addWidget(self.topCycleCurrent, 1, 2)
        unified_fields_grid.addWidget(self.lblJob, 2, 0)
        unified_fields_grid.addWidget(self.lblActivityCavities, 2, 1)
        unified_fields_grid.addWidget(self.topCycleStd, 2, 2)
        unified_fields_grid.addWidget(self.lblOperator, 3, 0)
        unified_fields_grid.addWidget(self.lblActivitySticker, 3, 1)
        unified_fields_grid.addWidget(self.topCycleCount, 3, 2)
        self.cardSessionActivity.layout().addLayout(unified_fields_grid)

        self.cardSessionActivityOuter.setMinimumHeight(190)
        self.cardSessionActivityOuter.setMaximumHeight(230)
        self.cardSessionActivityOuter.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        grid.addWidget(self.cardSessionActivityOuter, 1, 0, 1, 2)
        # Machine status now lives in the unified frame, so pulse overlay must follow that parent.
        self.machinePulseOverlay.setParent(self.cardSessionActivity)
        self.machinePulseOverlay.setGeometry(self.cardSessionActivity.rect())
        self.machinePulseOverlay.raise_()

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        # Distribute extra height across left-side rows proportionally to their base panel heights.
        # This avoids the top Production row looking over-stretched on taller displays.
        grid.setRowStretch(0, 2)  # Production
        grid.setRowStretch(1, 2)  # Session + Activity
        grid.setRowStretch(2, 1)
        grid.setRowStretch(3, 2)  # Raw Materials + Cycle row
        left.addLayout(grid, 7)

        # Keep in-memory logging, but remove the temporary visible Job API logs panel.
        self.cardJobApiLogsOuter = None
        self.cardJobApiLogs = None
        self.jobApiLogLabel = None

        # Let the main grid consume remaining height so the bottom cards can expand on taller screens.

        # Right side panel (downtime reason + timer).
        self.rightPanel = QFrame()
        self.rightPanel.setObjectName("RightPanel")
        rightLayout = QVBoxLayout()
        rightLayout.setContentsMargins(16, 0, 16, 14)
        rightLayout.setSpacing(0)
        self.rightPanel.setLayout(rightLayout)
        self.rightTopSpacer = QWidget()
        self.rightTopSpacer.setFixedHeight(0)
        self.rightTopSpacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        rightLayout.addWidget(self.rightTopSpacer)

        self.rightRawTitle = QLabel("Raw Materials Consumption")
        self.rightRawTitle.setObjectName("RightTitle")
        self.rightRawHint = QLabel("Track sacks count and scanned raw materials.")
        self.rightRawHint.setObjectName("RightHint")
        self.rightRawSacks = QLabel("Sacks Count: 0")
        self.rightRawSacks.setObjectName("RightMonitorValue")
        self.rightRawScanned = QLabel("Raw Mats Scanned: -")
        self.rightRawScanned.setObjectName("RightMonitorValue")
        self.rightRawScanned.setWordWrap(True)

        self.rightTitle = QLabel("Downtime Monitor")
        self.rightTitle.setObjectName("RightTitle")
        self.rightHint = QLabel("Scan ProductionDailyReport~1, then scan reason QR (01-15).")
        self.rightHint.setObjectName("RightHint")
        self.rightDowntimeTimer = QLabel("Downtime: 00:00:00")
        self.rightDowntimeTimer.setObjectName("RightMonitorValueAccent")
        self.rightDowntimeReason = QLabel("Reason: -")
        self.rightDowntimeReason.setObjectName("RightMonitorValue")
        self.rightDowntimeReason.setWordWrap(True)
        self.rightStartupReject = QLabel("Start Up Reject: 0")
        self.rightStartupReject.setObjectName("RightMonitorValue")
        self.rightCycleTitle = QLabel("Cycle Monitor")
        self.rightCycleTitle.setObjectName("RightTitle")
        self.rightCycleHint = QLabel("Cycle count and cycle time status.")
        self.rightCycleHint.setObjectName("RightHint")
        self.rightCycleCount = QLabel("Confirmed by: -")
        self.rightCycleCount.setObjectName("RightMonitorValue")
        self.rightCycleCurrent = QLabel("Cycle Time: ")
        self.rightCycleCurrent.setObjectName("RightMonitorValue")
        self.rightCycleStd = QLabel("Std Cycle Time: -")
        self.rightCycleStd.setObjectName("RightMonitorValue")
        self.rightCycleQtyShift = QLabel("Qty / Shift: -")
        self.rightCycleQtyShift.setObjectName("RightMonitorValue")
        self.rightMaintenance = QLabel("Maintenance: ")
        self.rightMaintenance.setObjectName("RightMonitorValue")
        self.rightSupervisor = QLabel("Supervisor: ")
        self.rightSupervisor.setObjectName("RightMonitorValue")
        self.rightSupervisorLeft = QLabel("Supervisor: -")
        self.rightSupervisorLeft.setObjectName("RightMonitorValue")

        rawDowntimeCol = QVBoxLayout()
        rawDowntimeCol.setContentsMargins(0, 0, 0, 0)
        rawDowntimeCol.setSpacing(10)

        rawOuter = QFrame()
        rawOuter.setObjectName("RightCardOuter")
        rawOuterLay = QVBoxLayout()
        rawOuterLay.setContentsMargins(8, 8, 8, 8)
        rawOuterLay.setSpacing(0)
        rawOuter.setLayout(rawOuterLay)

        rawFrame = QFrame()
        rawFrame.setObjectName("RightCardInner")
        rawFrame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        rawCol = QVBoxLayout()
        rawCol.setContentsMargins(12, 10, 12, 10)
        rawCol.setSpacing(6)
        rawFrame.setLayout(rawCol)
        rawCol.addWidget(self._make_right_title_with_icon("Raw Materials Consumption", "raw-material"))
        rawCol.addWidget(self.rightRawHint)
        rawCol.addWidget(self.rightRawSacks)
        rawCol.addWidget(self.rightRawScanned)
        rawOuterLay.addWidget(rawFrame)

        rawOuter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        rawFrame.setMinimumHeight(154)
        rawDowntimeCol.addWidget(rawOuter)

        downtimeOuter = QFrame()
        downtimeOuter.setObjectName("RightCardOuter")
        downtimeOuterLay = QVBoxLayout()
        downtimeOuterLay.setContentsMargins(8, 8, 8, 8)
        downtimeOuterLay.setSpacing(0)
        downtimeOuter.setLayout(downtimeOuterLay)

        downtimeFrame = QFrame()
        downtimeFrame.setObjectName("RightCardInner")
        downtimeCol = QVBoxLayout()
        downtimeCol.setContentsMargins(12, 10, 12, 10)
        downtimeCol.setSpacing(8)
        downtimeFrame.setLayout(downtimeCol)
        downtimeCol.addWidget(self._make_right_title_with_icon("Downtime Monitor", "downtime"))
        downtimeCol.addWidget(self.rightHint)

        downtimeGrid = QGridLayout()
        downtimeGrid.setContentsMargins(0, 0, 0, 0)
        downtimeGrid.setHorizontalSpacing(8)
        downtimeGrid.setVerticalSpacing(8)
        downtimeGrid.addWidget(self.rightDowntimeTimer, 0, 0)
        downtimeGrid.addWidget(self.rightDowntimeReason, 0, 1)
        downtimeGrid.addWidget(self.rightStartupReject, 1, 0)
        downtimeGrid.addWidget(self.rightMaintenance, 1, 1)
        downtimeGrid.addWidget(self.rightSupervisorLeft, 2, 0)
        downtimeGrid.addWidget(self.rightSupervisor, 2, 1)
        downtimeCol.addLayout(downtimeGrid)
        downtimeOuterLay.addWidget(downtimeFrame)

        rawDowntimeCol.addWidget(downtimeOuter)

        linkageOuter = QFrame()
        linkageOuter.setObjectName("RightCardOuter")
        linkageOuterLay = QVBoxLayout()
        linkageOuterLay.setContentsMargins(8, 8, 8, 8)
        linkageOuterLay.setSpacing(0)
        linkageOuter.setLayout(linkageOuterLay)

        linkageFrame = QFrame()
        linkageFrame.setObjectName("RightCardInner")
        linkageFrame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        linkageCol = QVBoxLayout()
        linkageCol.setContentsMargins(12, 10, 12, 10)
        linkageCol.setSpacing(6)
        linkageFrame.setLayout(linkageCol)
        linkageCol.addWidget(self._make_right_title_with_icon("Linkage Mirror", "job"))
        self.linkageMirrorHint = QLabel('Scan "joblinkage~1" then scan another JOB QR.')
        self.linkageMirrorHint.setObjectName("RightHint")
        self.linkageMirrorJob = QLabel("Linked Job: -")
        self.linkageMirrorJob.setObjectName("RightMonitorValue")
        self.linkageMirrorCounts = QLabel("Pack: 0 | Good: 0 | Butal: 0 | Reject: 0 | Total Good: 0")
        self.linkageMirrorCounts.setObjectName("RightMonitorValue")
        self.linkageMirrorCounts.setWordWrap(True)
        self.linkageMirrorRejects = QLabel("Reject Details: -")
        self.linkageMirrorRejects.setObjectName("RightMonitorValue")
        self.linkageMirrorRejects.setWordWrap(True)
        linkageCol.addWidget(self.linkageMirrorHint)
        linkageCol.addWidget(self.linkageMirrorJob)
        linkageCol.addWidget(self.linkageMirrorCounts)
        linkageCol.addWidget(self.linkageMirrorRejects)
        linkageOuterLay.addWidget(linkageFrame)
        self.linkageMirrorOuter = linkageOuter

        # Show Linkage above Product Parts in the right panel.
        rightLayout.addWidget(linkageOuter)
        rightLayout.addSpacing(10)
        rightLayout.addWidget(self.cardJobDetailsOuter)
        rightLayout.addStretch()

        # Swap positions: place Raw Materials + Cycle Monitor where Job Details used to be.
        rawCycleSwapWrap = QWidget()
        rawCycleSwapWrap.setLayout(rawDowntimeCol)
        rawCycleSwapWrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        rawCycleSwapWrap.setMinimumHeight(360)
        self.rawCycleSwapWrap = rawCycleSwapWrap
        grid.addWidget(rawCycleSwapWrap, 3, 0, 1, 2)

        contentRow = QHBoxLayout()
        contentRow.setContentsMargins(0, 0, 0, 0)
        contentRow.setSpacing(10)
        contentRow.addWidget(leftWrap, 1)
        contentRow.addWidget(self.rightPanel, 1)

        root.addLayout(headerRow)
        root.addWidget(self.headerDivider)
        root.addLayout(contentRow, 1)

        self.setLayout(root)

        # Center overlay for invalid scans (GIF)
        self.invalidOverlay = QFrame(self)
        self.invalidOverlay.setObjectName("InvalidOverlay")
        self.invalidOverlay.setStyleSheet(
            "background: rgba(220,38,38,0.60); border: 2px solid rgba(0,0,0,0.72); border-radius: 0px;"
        )
        self.invalidOverlay.setLayout(QVBoxLayout())
        self.invalidOverlay.layout().setContentsMargins(10, 10, 10, 10)
        self.invalidOverlay.layout().setSpacing(8)
        self.invalidOverlay.layout().setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.invalidGifLabel = QLabel()
        self.invalidGifLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.invalidGifLabel.setStyleSheet("background: rgba(255,255,255,0.04); border: 2px solid rgba(0,0,0,0.78);")
        self.invalidTextLabel = QLabel("INVALID SCAN")
        self.invalidTextLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.invalidTextLabel.setStyleSheet(
            "background: transparent; border: none; color: #ffffff; font-size: 28px; font-weight: 900;"
        )
        self.invalidReasonLabel = QLabel("")
        self.invalidReasonLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.invalidReasonLabel.setWordWrap(True)
        self.invalidReasonLabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.invalidReasonLabel.setStyleSheet(
            "background: transparent; border: none; color: #fde68a; font-size: 15px; font-weight: 700;"
        )
        self.invalidTextBand = QFrame()
        self.invalidTextBand.setObjectName("InvalidTextBand")
        self.invalidTextBand.setStyleSheet(
            "QFrame#InvalidTextBand {"
            "background: rgba(127, 29, 29, 0.94);"
            "border: none;"
            "border-radius: 2px;"
            "}"
        )
        self.invalidTextBand.setLayout(QVBoxLayout())
        self.invalidTextBand.layout().setContentsMargins(8, 6, 8, 6)
        self.invalidTextBand.layout().setSpacing(4)
        gif_shadow = QGraphicsDropShadowEffect(self)
        gif_shadow.setBlurRadius(10)
        gif_shadow.setOffset(0, 0)
        gif_shadow.setColor(Qt.GlobalColor.black)
        self.invalidGifLabel.setGraphicsEffect(gif_shadow)
        self.invalidTextLabel.setGraphicsEffect(None)
        self.invalidReasonLabel.setGraphicsEffect(None)
        self.invalidOverlay.layout().addWidget(self.invalidGifLabel, 0, Qt.AlignmentFlag.AlignCenter)
        self.invalidTextBand.layout().addWidget(self.invalidTextLabel, 0, Qt.AlignmentFlag.AlignCenter)
        self.invalidTextBand.layout().addWidget(self.invalidReasonLabel, 0, Qt.AlignmentFlag.AlignCenter)
        self.invalidOverlay.layout().addWidget(self.invalidTextBand)
        self.invalidOverlay.hide()
        self.invalidOverlay.raise_()
        self._invalid_movie: Optional[QMovie] = None
        self._invalid_hide_timer = QTimer(self)
        self._invalid_hide_timer.setSingleShot(True)
        self._invalid_hide_timer.timeout.connect(self._hide_invalid_overlay)
        self._setup_invalid_overlay_media()

        # Center overlay for Production Daily Report reason options.
        self.productionOverlay = QFrame(self)
        self.productionOverlay.setObjectName("ProductionOverlay")
        self.productionOverlay.setStyleSheet("")
        self.productionOverlay.setLayout(QVBoxLayout())
        self.productionOverlay.layout().setContentsMargins(14, 12, 14, 12)
        self.productionOverlay.layout().setSpacing(6)
        self.productionOverlay.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.productionTitle = QLabel("PRODUCTION DAILY REPORT")
        self.productionTitle.setStyleSheet("color: #0f172a; font-size: 22px; font-weight: 900;")
        self.productionOverlay.layout().addWidget(self.productionTitle)
        self.productionHint = QLabel("Scan reason QR code (01-15)")
        self.productionHint.setStyleSheet("color: #334155; font-size: 14px; font-weight: 700;")
        self.productionOverlay.layout().addWidget(self.productionHint)
        self.productionReasonList = QLabel("\n".join(f"{code} - {label}" for code, label in PRODUCTION_DAILY_REPORT_ITEMS))
        self.productionReasonList.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: 700;")
        self.productionReasonList.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.productionReasonList.setWordWrap(True)
        self.productionOverlay.layout().addWidget(self.productionReasonList)

        self.productionLiveReason = QLabel("Reason: -")
        self.productionLiveReason.setObjectName("ProductionLiveReason")
        self.productionLiveReason.setWordWrap(True)
        self.productionOverlay.layout().addWidget(self.productionLiveReason)

        self.productionCounter = QLabel("00:00:00")
        self.productionCounter.setObjectName("ProductionCounter7")
        self.productionCounter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.productionOverlay.layout().addWidget(self.productionCounter)
        self.pdrPulseOverlay = HeartbeatBorderPulseOverlay(self.productionOverlay)
        self.pdrPulseOverlay.setGeometry(self.productionOverlay.rect())
        self.pdrPulseOverlay.raise_()

        self.productionFixAnim = QLabel("Repair in progress...")
        self.productionFixAnim.setObjectName("ProductionFixAnim")
        self.productionFixAnim.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.productionOverlay.layout().addWidget(self.productionFixAnim)

        self.productionMarqueeWrap = QWidget()
        self.productionMarqueeWrap.setObjectName("ProductionMarqueeWrap")
        self.productionMarqueeWrap.setFixedHeight(28)
        self.productionMarqueeWrap.setStyleSheet("background: transparent;")
        self.productionMarqueeText = QLabel(
            "MACHINE IS UNDER REPAIR/ADJUSTMENT...   MACHINE IS UNDER REPAIR/ADJUSTMENT..."
        )
        self.productionMarqueeText.setObjectName("ProductionMarqueeText")
        self.productionMarqueeText.setParent(self.productionMarqueeWrap)
        self.productionMarqueeText.adjustSize()
        self._marquee_x = 0
        self._marquee_speed = 5
        self.productionOverlay.layout().addWidget(self.productionMarqueeWrap)

        self.resolveOverlay = QFrame(self)
        self.resolveOverlay.setObjectName("ProductionOverlay")
        self.resolveOverlay.setStyleSheet(
            "QFrame#ProductionOverlay {"
            "background: qradialgradient(cx:0.42, cy:0.26, radius:1.0, fx:0.42, fy:0.26,"
            "stop:0 rgba(255,255,255,0.99), stop:0.58 rgba(239,246,255,0.98), stop:1 rgba(219,234,254,0.97));"
            "border: 2px solid #f97316; border-radius: 16px; }"
            "QFrame#ResolveInfoCard {"
            "background: rgba(255,255,255,0.88); border: 1px solid rgba(148,163,184,0.45); border-radius: 12px; }"
            "QLabel#ResolveInfoTitle { color: #64748b; font-size: 11px; font-weight: 800; }"
            "QLabel#ResolveInfoValue { color: #0f172a; font-size: 19px; font-weight: 900; }"
        )
        self.resolveOverlay.setLayout(QVBoxLayout())
        self.resolveOverlay.layout().setContentsMargins(16, 14, 16, 14)
        self.resolveOverlay.layout().setSpacing(10)
        self.resolveOverlay.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.resolveTitle = QLabel("DOWNTIME RESOLUTION")
        self.resolveTitle.setStyleSheet("color: #0f172a; font-size: 22px; font-weight: 900;")
        self.resolveHint = QLabel("Scan cycle time digits (num_0..num_9), backspace, then confirm")
        self.resolveHint.setStyleSheet("color: #334155; font-size: 14px; font-weight: 700;")
        self.resolveHint.setWordWrap(True)
        self.resolveOldCycle = QLabel("Old Cycle Time: -")
        self.resolveOldCycle.setObjectName("ResolveInfoValue")
        self.resolveNewCycle = QLabel("Cycle Time: ")
        self.resolveNewCycle.setObjectName("ResolveInfoValue")
        self.resolveOldCycleTitle = QLabel("REFERENCE")
        self.resolveOldCycleTitle.setObjectName("ResolveInfoTitle")
        self.resolveNewCycleTitle = QLabel("CURRENT INPUT")
        self.resolveNewCycleTitle.setObjectName("ResolveInfoTitle")
        self.resolveOldCard = QFrame()
        self.resolveOldCard.setObjectName("ResolveInfoCard")
        self.resolveOldCard.setLayout(QVBoxLayout())
        self.resolveOldCard.layout().setContentsMargins(12, 10, 12, 10)
        self.resolveOldCard.layout().setSpacing(4)
        self.resolveOldCard.layout().addWidget(self.resolveOldCycleTitle)
        self.resolveOldCard.layout().addWidget(self.resolveOldCycle)
        self.resolveNewCard = QFrame()
        self.resolveNewCard.setObjectName("ResolveInfoCard")
        self.resolveNewCard.setLayout(QVBoxLayout())
        self.resolveNewCard.layout().setContentsMargins(12, 10, 12, 10)
        self.resolveNewCard.layout().setSpacing(4)
        self.resolveNewCard.layout().addWidget(self.resolveNewCycleTitle)
        self.resolveNewCard.layout().addWidget(self.resolveNewCycle)
        self.resolveOverlay.layout().addWidget(self.resolveTitle)
        self.resolveOverlay.layout().addWidget(self.resolveHint)
        self.resolveOverlay.layout().addWidget(self.resolveOldCard)
        self.resolveOverlay.layout().addWidget(self.resolveNewCard)
        self.resolveOverlay.hide()
        self.resolveOverlay.raise_()

        # Center overlay for raw materials history (toggle with "showrawmats").
        self.rawMatsOverlay = QFrame(self)
        self.rawMatsOverlay.setObjectName("ProductionOverlay")
        self.rawMatsOverlay.setLayout(QVBoxLayout())
        self.rawMatsOverlay.layout().setContentsMargins(14, 12, 14, 12)
        self.rawMatsOverlay.layout().setSpacing(8)
        self.rawMatsOverlay.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.rawMatsTitle = QLabel("RAW MATERIALS SCANNED")
        self.rawMatsTitle.setStyleSheet("color: #0f172a; font-size: 22px; font-weight: 900;")
        self.rawMatsHint = QLabel('Scan "rawmatsummary~1" (or "showrawmats") again to close')
        self.rawMatsHint.setStyleSheet("color: #334155; font-size: 14px; font-weight: 700;")
        self.rawMatsList = QTableWidget(0, 8)
        self.rawMatsList.setHorizontalHeaderLabels(["#", "Raw Material", "Qty", "Index", "Total Labels", "Lot", "PO No.", "Timestamp"])
        self.rawMatsList.setAlternatingRowColors(True)
        self.rawMatsList.setWordWrap(False)
        self.rawMatsList.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rawMatsList.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.rawMatsList.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rawMatsList.verticalHeader().setVisible(False)
        self.rawMatsList.verticalHeader().setDefaultSectionSize(28)
        self.rawMatsList.horizontalHeader().setStretchLastSection(False)
        self.rawMatsList.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.rawMatsList.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.rawMatsList.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.rawMatsList.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.rawMatsList.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.rawMatsList.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.rawMatsList.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.rawMatsList.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.rawMatsList.setMinimumHeight(240)
        self.rawMatsList.setStyleSheet(
            "QTableWidget { background: rgba(255,255,255,0.78); border: 1px solid rgba(148,163,184,0.45);"
            " border-radius: 10px; gridline-color: rgba(148,163,184,0.28); }"
            "QHeaderView::section { background: rgba(226,232,240,0.9); color: #0f172a; font-weight: 800;"
            " border: none; border-bottom: 1px solid rgba(148,163,184,0.5); padding: 6px; }"
        )
        self.rawMatsOverlay.layout().addWidget(self.rawMatsTitle)
        self.rawMatsOverlay.layout().addWidget(self.rawMatsHint)
        self.rawMatsOverlay.layout().addWidget(self.rawMatsList)
        self.rawMatsOverlay.hide()
        self.rawMatsOverlay.raise_()

        # Center overlay for reject summary snapshot (triggered by "rejectsummary").
        self.rejectSummaryOverlay = QFrame(self)
        self.rejectSummaryOverlay.setObjectName("ProductionOverlay")
        self.rejectSummaryOverlay.setLayout(QVBoxLayout())
        self.rejectSummaryOverlay.layout().setContentsMargins(14, 12, 14, 12)
        self.rejectSummaryOverlay.layout().setSpacing(8)
        self.rejectSummaryOverlay.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.rejectSummaryTitle = QLabel("REJECT SUMMARY")
        self.rejectSummaryTitle.setStyleSheet("color: #0f172a; font-size: 22px; font-weight: 900;")
        self.rejectSummaryHint = QLabel('Scan "rejectsummary" again to refresh')
        self.rejectSummaryHint.setStyleSheet("color: #334155; font-size: 14px; font-weight: 700;")
        self.rejectSummaryStamp = QLabel("Scanned at: -")
        self.rejectSummaryStamp.setObjectName("MetaValue")
        self.rejectSummaryConfirmedBy = QLabel("Confirmed by: -")
        self.rejectSummaryConfirmedBy.setObjectName("MetaValue")
        self.rejectSummaryTotals = QLabel("Reject Total: 0 | Start Up Reject: 0")
        self.rejectSummaryTotals.setObjectName("MetaValue")
        self.rejectSummaryDetails = QTableWidget(1, len(REJECT_DETAIL_ITEMS))
        self.rejectSummaryDetails.setHorizontalHeaderLabels([code for code, _ in REJECT_DETAIL_ITEMS])
        self.rejectSummaryDetails.setVerticalHeaderLabels(["Qty"])
        self.rejectSummaryDetails.setAlternatingRowColors(False)
        self.rejectSummaryDetails.setWordWrap(False)
        self.rejectSummaryDetails.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rejectSummaryDetails.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.rejectSummaryDetails.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rejectSummaryDetails.verticalHeader().setVisible(True)
        self.rejectSummaryDetails.verticalHeader().setDefaultSectionSize(34)
        self.rejectSummaryDetails.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.rejectSummaryDetails.setMinimumHeight(120)
        self.rejectSummaryDetails.setStyleSheet(
            "QTableWidget { background: rgba(255,255,255,0.84); border: 1px solid rgba(148,163,184,0.45);"
            " border-radius: 10px; gridline-color: rgba(148,163,184,0.28); }"
            "QHeaderView::section { background: rgba(226,232,240,0.92); color: #0f172a; font-weight: 900;"
            " border: none; border-bottom: 1px solid rgba(148,163,184,0.5); padding: 6px; }"
            "QTableWidget::item { padding: 6px; color: #0f172a; font-weight: 800; }"
        )
        self.rejectSummaryOverlay.layout().addWidget(self.rejectSummaryTitle)
        self.rejectSummaryOverlay.layout().addWidget(self.rejectSummaryHint)
        self.rejectSummaryOverlay.layout().addWidget(self.rejectSummaryStamp)
        self.rejectSummaryOverlay.layout().addWidget(self.rejectSummaryConfirmedBy)
        self.rejectSummaryOverlay.layout().addWidget(self.rejectSummaryTotals)
        self.rejectSummaryOverlay.layout().addWidget(self.rejectSummaryDetails, 1)
        self.rejectSummaryOverlay.hide()
        self.rejectSummaryOverlay.raise_()

        # Center overlay for scanned PACK QR history (toggle with "prodhistory~1").
        self.productHistoryOverlay = QFrame(self)
        self.productHistoryOverlay.setObjectName("PackHistoryOverlay")
        self.productHistoryOverlay.setLayout(QVBoxLayout())
        self.productHistoryOverlay.layout().setContentsMargins(12, 10, 12, 10)
        self.productHistoryOverlay.layout().setSpacing(8)
        self.productHistoryOverlay.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.productHistoryOverlay.setStyleSheet(
            "QFrame#PackHistoryOverlay {"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "   stop:0 rgba(247,248,250,0.985), stop:1 rgba(236,239,243,0.985));"
            " border: 1px solid rgba(203,213,225,0.80);"
            " border-radius: 18px;"
            "}"
            "QFrame#PackHistoryHeaderBand {"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "   stop:0 #111827, stop:0.55 #1e293b, stop:1 #334155);"
            " border: 1px solid rgba(148,163,184,0.25);"
            " border-radius: 16px;"
            "}"
            "QFrame#PackHistoryStatsBand {"
            " background: rgba(255,255,255,0.86);"
            " border: 1px solid rgba(226,232,240,1.0);"
            " border-radius: 14px;"
            "}"
            "QLabel#PackHistoryHeaderTitle { color:#f8fafc; font-size:20px; font-weight:900; }"
            "QLabel#PackHistoryHeaderSub { color:#cbd5e1; font-size:12px; font-weight:800; }"
            "QLabel#PackHistoryChip {"
            " color:#e2e8f0; background: transparent;"
            " border: none; border-radius: 12px;"
            " padding: 4px 10px; font-size:12px; font-weight:800;"
            "}"
            "QWidget#PackHistoryTitleRow, QWidget#PackHistoryTopChips { background: transparent; border: none; }"
            "QLabel#PackHistoryStatCardTitle { color:#64748b; font-size:11px; font-weight:800; }"
            "QLabel#PackHistoryStatCardValue { color:#0f172a; font-size:15px; font-weight:900; }"
            "QFrame#PackHistoryStatCard {"
            " background: rgba(248,250,252,0.95);"
            " border: 1px solid rgba(226,232,240,0.95);"
            " border-radius: 12px;"
            "}"
            "QFrame#PackHistoryStatCardMissing {"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "   stop:0 rgba(254,226,226,0.97), stop:1 rgba(252,165,165,0.93));"
            " border: 1px solid rgba(239,68,68,0.30);"
            " border-radius: 12px;"
            "}"
            "QLabel#PackHistoryHint { color:#64748b; font-size:11px; font-weight:700; }"
            "QLabel#PackHistoryPageInfo { color:#475569; font-size:12px; font-weight:800; }"
            "QTableWidget#PackHistoryTable {"
            " background: rgba(255,255,255,0.96);"
            " alternate-background-color: rgba(248,250,252,0.95);"
            " border: 1px solid rgba(226,232,240,0.95);"
            " border-radius: 14px;"
            " color: #0f172a;"
            " padding: 4px;"
            "}"
            "QTableWidget#PackHistoryTable::item {"
            " border-bottom: 1px solid rgba(226,232,240,0.9);"
            " padding: 8px 12px;"
            " font-size: 14px;"
            "}"
            "QHeaderView::section {"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #eef2ff, stop:1 #dbeafe);"
            " color: #334155;"
            " font-weight: 900;"
            " border: none;"
            " border-bottom: 1px solid rgba(191,219,254,0.95);"
            " padding: 8px 10px;"
            "}"
        )

        self.productHistoryHeaderBand = QFrame()
        self.productHistoryHeaderBand.setObjectName("PackHistoryHeaderBand")
        self.productHistoryHeaderBand.setLayout(QVBoxLayout())
        self.productHistoryHeaderBand.layout().setContentsMargins(14, 12, 14, 10)
        self.productHistoryHeaderBand.layout().setSpacing(8)

        titleRow = QWidget()
        titleRow.setObjectName("PackHistoryTitleRow")
        titleRow.setLayout(QHBoxLayout())
        titleRow.layout().setContentsMargins(0, 0, 0, 0)
        titleRow.layout().setSpacing(8)
        self.productHistoryIcon = QLabel("\u2630")
        self.productHistoryIcon.setFixedSize(28, 28)
        self.productHistoryIcon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.productHistoryIcon.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #60a5fa, stop:1 #2563eb);"
            "color:#ffffff; border-radius:10px; font-size:16px; font-weight:900;"
        )
        self.productHistoryTitle = QLabel("Pack Scan History")
        self.productHistoryTitle.setObjectName("PackHistoryHeaderTitle")
        self.productHistoryIcon.hide()
        titleRow.layout().addWidget(self.productHistoryTitle, 0, Qt.AlignmentFlag.AlignVCenter)
        titleRow.layout().addStretch(1)

        self.productHistoryTopChips = QWidget()
        self.productHistoryTopChips.setObjectName("PackHistoryTopChips")
        self.productHistoryTopChips.setLayout(QHBoxLayout())
        self.productHistoryTopChips.layout().setContentsMargins(0, 0, 0, 0)
        self.productHistoryTopChips.layout().setSpacing(8)
        self.productHistoryTopProduct = QLabel("Product ID: -")
        self.productHistoryTopProduct.setObjectName("PackHistoryChip")
        self.productHistoryTopScans = QLabel("Total Scans: 0")
        self.productHistoryTopScans.setObjectName("PackHistoryChip")
        self.productHistoryTopQty = QLabel("Total Quantity: 0")
        self.productHistoryTopQty.setObjectName("PackHistoryChip")
        self.productHistoryTopChips.layout().addWidget(self.productHistoryTopProduct)
        self.productHistoryTopChips.layout().addWidget(self.productHistoryTopScans)
        self.productHistoryTopChips.layout().addWidget(self.productHistoryTopQty)
        self.productHistoryTopChips.layout().addStretch(1)
        self.productHistoryTopChips.hide()

        self.productHistoryHeaderBand.layout().addWidget(titleRow)
        self.productHistoryHeaderBand.layout().addWidget(self.productHistoryTopChips)

        self.productHistorySummary = QLabel("No scans yet")
        self.productHistorySummary.setObjectName("PackHistoryHeaderSub")
        self.productHistoryHeaderBand.layout().addWidget(self.productHistorySummary)
        self.productHistorySummary.hide()
        self.productHistoryHint = QLabel('Scan "next" / "prev" to change page. Scan "prodhistory~1" again to close.')
        self.productHistoryHint.setObjectName("PackHistoryHint")
        self.productHistoryList = QTableWidget(0, 5)
        self.productHistoryList.setObjectName("PackHistoryTable")
        self.productHistoryList.setHorizontalHeaderLabels(["Label #", "Product Name", "Pack Qty", "Operator", "Scan Time"])
        self.productHistoryList.setAlternatingRowColors(True)
        self.productHistoryList.setWordWrap(False)
        self.productHistoryList.setShowGrid(False)
        self.productHistoryList.setCornerButtonEnabled(False)
        self.productHistoryList.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.productHistoryList.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.productHistoryList.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.productHistoryList.verticalHeader().setVisible(False)
        self.productHistoryList.verticalHeader().setDefaultSectionSize(30)
        self.productHistoryList.setSortingEnabled(False)
        self.productHistoryList.horizontalHeader().setStretchLastSection(False)
        self.productHistoryList.horizontalHeader().setMinimumSectionSize(70)
        self.productHistoryList.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.productHistoryList.horizontalHeader().setFixedHeight(34)
        self.productHistoryList.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.productHistoryList.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.productHistoryList.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.productHistoryList.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.productHistoryList.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.productHistoryList.setMinimumHeight(470)

        self.productHistoryStatsBand = QFrame()
        self.productHistoryStatsBand.setObjectName("PackHistoryStatsBand")
        self.productHistoryStatsBand.setLayout(QHBoxLayout())
        self.productHistoryStatsBand.layout().setContentsMargins(10, 8, 10, 8)
        self.productHistoryStatsBand.layout().setSpacing(8)
        def _make_ph_stat(title: str, value: str):
            card = QFrame()
            card.setObjectName("PackHistoryStatCard")
            card.setLayout(QVBoxLayout())
            card.layout().setContentsMargins(10, 6, 10, 6)
            card.layout().setSpacing(2)
            t = QLabel(title); t.setObjectName("PackHistoryStatCardTitle")
            v = QLabel(value); v.setObjectName("PackHistoryStatCardValue")
            card.layout().addWidget(t)
            card.layout().addWidget(v)
            return card, v
        self.productHistoryMetricProductCard, self.productHistoryMetricProductValue = _make_ph_stat("Product ID", "-")
        self.productHistoryMetricLabelsCard, self.productHistoryMetricLabelsValue = _make_ph_stat("Total Labels", "0")
        self.productHistoryMetricQtyCard, self.productHistoryMetricQtyValue = _make_ph_stat("Total Quantity", "0")
        self.productHistoryMetricMissingCard, self.productHistoryMetricMissingValue = _make_ph_stat("Missing Labels", "-")
        self.productHistoryMetricMissingCard.setObjectName("PackHistoryStatCardMissing")
        self.productHistoryPageInfo = QLabel("Page 1 of 1")
        self.productHistoryPageInfo.setObjectName("PackHistoryPageInfo")
        self.productHistoryMetricProductCard.hide()
        self.productHistoryStatsBand.layout().addWidget(self.productHistoryMetricLabelsCard)
        self.productHistoryStatsBand.layout().addWidget(self.productHistoryMetricQtyCard)
        self.productHistoryStatsBand.layout().addWidget(self.productHistoryMetricMissingCard)
        self.productHistoryStatsBand.layout().addStretch(1)
        self.productHistoryStatsBand.layout().addWidget(self.productHistoryPageInfo, 0, Qt.AlignmentFlag.AlignVCenter)

        self.productHistoryOverlay.layout().addWidget(self.productHistoryHeaderBand)
        self.productHistoryOverlay.layout().addWidget(self.productHistoryList)
        self.productHistoryOverlay.layout().addWidget(self.productHistoryStatsBand)
        self.productHistoryOverlay.layout().addWidget(self.productHistoryHint)
        self._product_history_shadow = QGraphicsDropShadowEffect(self.productHistoryOverlay)
        self._product_history_shadow.setBlurRadius(26)
        self._product_history_shadow.setOffset(0, 10)
        self._product_history_shadow.setColor(QColor(15, 23, 42, 95))
        self.productHistoryOverlay.setGraphicsEffect(self._product_history_shadow)
        self.productHistoryOrderNote = QFrame(self)
        self.productHistoryOrderNote.setObjectName("PackHistoryOrderNote")
        self.productHistoryOrderNote.setStyleSheet(
            "QFrame#PackHistoryOrderNote {"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "   stop:0 rgba(254,242,242,0.98), stop:1 rgba(254,202,202,0.95));"
            " border: 1px solid rgba(239,68,68,0.30);"
            " border-radius: 12px;"
            "}"
            "QLabel#PackHistoryOrderNoteText { color:#991b1b; font-size:12px; font-weight:900; }"
        )
        self.productHistoryOrderNote.setLayout(QVBoxLayout())
        self.productHistoryOrderNote.layout().setContentsMargins(10, 8, 10, 8)
        self.productHistoryOrderNote.layout().setSpacing(2)
        self.productHistoryOrderNoteText = QLabel("Why the order of label # is not in order?")
        self.productHistoryOrderNoteText.setObjectName("PackHistoryOrderNoteText")
        self.productHistoryOrderNoteText.setWordWrap(True)
        self.productHistoryOrderNote.layout().addWidget(self.productHistoryOrderNoteText)
        self._product_history_order_note_shadow = QGraphicsDropShadowEffect(self.productHistoryOrderNote)
        self._product_history_order_note_shadow.setBlurRadius(18)
        self._product_history_order_note_shadow.setOffset(0, 6)
        self._product_history_order_note_shadow.setColor(QColor(127, 29, 29, 65))
        self.productHistoryOrderNote.setGraphicsEffect(self._product_history_order_note_shadow)
        self.productHistoryOrderNote.hide()
        self.productHistoryOrderNote.raise_()
        self.productHistoryOverlay.hide()
        self.productHistoryOverlay.raise_()

        # Center overlay for reject confirmation by Supervisor/QC.
        self.rejectReviewOverlay = QFrame(self)
        self.rejectReviewOverlay.setObjectName("ProductionOverlay")
        self.rejectReviewOverlay.setLayout(QVBoxLayout())
        self.rejectReviewOverlay.layout().setContentsMargins(14, 12, 14, 12)
        self.rejectReviewOverlay.layout().setSpacing(8)
        self.rejectReviewOverlay.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.rejectReviewTitle = QLabel("REJECT CHECK")
        self.rejectReviewTitle.setStyleSheet("color: #0f172a; font-size: 20px; font-weight: 900;")
        self.rejectReviewActor = QLabel("Authorized Review")
        self.rejectReviewActor.setObjectName("MetaValue")
        self.rejectReviewList = QLabel("No rejects to confirm.")
        self.rejectReviewList.setObjectName("ProductionLiveReason")
        self.rejectReviewList.setWordWrap(True)
        self.rejectReviewList.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.rejectReviewCycle = QLabel("Cycle Count: - | Cycle Time: -")
        self.rejectReviewCycle.setObjectName("MetaValue")
        self.rejectReviewCycle.hide()
        self.rejectReviewHint = QLabel("Scan the same authorized badge to continue.")
        self.rejectReviewHint.setStyleSheet("color: #334155; font-size: 14px; font-weight: 700;")
        self.rejectReviewOverlay.layout().addWidget(self.rejectReviewTitle)
        self.rejectReviewOverlay.layout().addWidget(self.rejectReviewActor)
        self.rejectReviewOverlay.layout().addWidget(self.rejectReviewList)
        self.rejectReviewOverlay.layout().addWidget(self.rejectReviewCycle)
        self.rejectReviewOverlay.layout().addWidget(self.rejectReviewHint)
        self.rejectReviewLoadingLayer = QFrame(self.rejectReviewOverlay)
        self.rejectReviewLoadingLayer.setStyleSheet("background: rgba(255,255,255,0.46); border: none;")
        self.rejectReviewLoadingLayer.setLayout(QVBoxLayout())
        self.rejectReviewLoadingLayer.layout().setContentsMargins(18, 18, 18, 18)
        self.rejectReviewLoadingLayer.layout().setSpacing(8)
        self.rejectReviewLoadingLayer.layout().setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rejectReviewLoadingText = QLabel("Confirming...")
        self.rejectReviewLoadingText.setObjectName("MetaValue")
        self.rejectReviewLoadingText.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rejectReviewLoadingBar = QProgressBar()
        self.rejectReviewLoadingBar.setRange(0, 100)
        self.rejectReviewLoadingBar.setValue(0)
        self.rejectReviewLoadingBar.setTextVisible(False)
        self.rejectReviewLoadingBar.setFixedWidth(260)
        self.rejectReviewLoadingLayer.layout().addWidget(self.rejectReviewLoadingText)
        self.rejectReviewLoadingLayer.layout().addWidget(self.rejectReviewLoadingBar, 0, Qt.AlignmentFlag.AlignCenter)
        self.rejectReviewLoadingLayer.hide()
        self.rejectReviewLoadingLayer.raise_()
        self.rejectReviewOverlay.setStyleSheet(
            "QFrame#ProductionOverlay {"
            "background: qradialgradient(cx:0.45, cy:0.35, radius:1.0, fx:0.45, fy:0.35,"
            "stop:0 rgba(255,255,255,0.99), stop:0.58 rgba(236,253,245,0.98), stop:1 rgba(209,250,229,0.97));"
            "border: 3px solid #0f766e; border-radius: 14px; }"
            "QProgressBar {"
            "border: 1px solid #0f766e; border-radius: 8px; background: rgba(255,255,255,0.88); min-height: 14px; }"
            "QProgressBar::chunk {"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0f766e, stop:1 #f59e0b);"
            "border-radius: 7px; }"
        )
        self.rejectReviewOverlay.hide()
        self.rejectReviewOverlay.raise_()
        self._reject_review_anim_timer = QTimer(self)
        self._reject_review_anim_timer.setInterval(80)
        self._reject_review_anim_timer.timeout.connect(self._tick_reject_review_anim)
        self._reject_review_anim_value = 0
        self._reject_review_blur_effects: List[QGraphicsBlurEffect] = []
        self._reject_review_blur_targets = [
            self.rejectReviewTitle,
            self.rejectReviewActor,
            self.rejectReviewList,
            self.rejectReviewCycle,
            self.rejectReviewHint,
        ]

        # Center overlay for finish-job processing.
        self.finishOverlay = QFrame(self)
        self.finishOverlay.setObjectName("ProductionOverlay")
        self.finishOverlay.setLayout(QVBoxLayout())
        self.finishOverlay.layout().setContentsMargins(16, 14, 16, 14)
        self.finishOverlay.layout().setSpacing(10)
        self.finishOverlay.layout().setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.finishTitle = QLabel("FINISHING JOB")
        self.finishTitle.setStyleSheet("color: #0f172a; font-size: 22px; font-weight: 900;")
        self.finishTitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.finishStatus = QLabel("Processing...")
        self.finishStatus.setStyleSheet("color: #334155; font-size: 14px; font-weight: 700;")
        self.finishStatus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.finishProgressBar = QProgressBar()
        self.finishProgressBar.setRange(0, 100)
        self.finishProgressBar.setValue(0)
        self.finishProgressBar.setTextVisible(False)
        self.finishProgressBar.setFixedWidth(300)
        self.finishSuccessRow = QWidget()
        self.finishSuccessRow.setObjectName("FinishSuccessRow")
        self.finishSuccessRow.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.finishSuccessRow.setStyleSheet("background: transparent;")
        self.finishSuccessRow.setLayout(QHBoxLayout())
        self.finishSuccessRow.layout().setContentsMargins(0, 0, 0, 0)
        self.finishSuccessRow.layout().setSpacing(10)
        self.finishSuccessRow.layout().setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.finishCheck = SuccessCheck(size=64, parent=self.finishSuccessRow)
        self.finishDoneText = QLabel("Success")
        self.finishDoneText.setObjectName("FinishDoneText")
        self.finishDoneText.setStyleSheet("background: transparent; color: #166534; font-size: 20px; font-weight: 900;")
        self.finishSuccessRow.layout().addWidget(self.finishCheck, 0, Qt.AlignmentFlag.AlignVCenter)
        self.finishSuccessRow.layout().addWidget(self.finishDoneText, 0, Qt.AlignmentFlag.AlignVCenter)
        self.finishSuccessRow.hide()
        self.finishOverlay.layout().addWidget(self.finishTitle)
        self.finishOverlay.layout().addWidget(self.finishStatus)
        self.finishOverlay.layout().addWidget(self.finishProgressBar, 0, Qt.AlignmentFlag.AlignCenter)
        self.finishOverlay.layout().addWidget(self.finishSuccessRow, 0, Qt.AlignmentFlag.AlignCenter)
        self.finishOverlay.setStyleSheet(
            "QFrame#ProductionOverlay {"
            "background: qradialgradient(cx:0.5, cy:0.45, radius:0.9, fx:0.5, fy:0.45,"
            "stop:0 rgba(255,255,255,0.99), stop:0.58 rgba(240,253,244,0.98), stop:1 rgba(220,252,231,0.98));"
            "border: 3px solid #16a34a; border-radius: 14px; }"
            "QWidget#FinishSuccessRow { background: transparent; border: none; }"
            "QLabel#FinishDoneText { background: transparent; border: none; }"
            "QProgressBar {"
            "border: 1px solid #16a34a; border-radius: 8px; background: rgba(255,255,255,0.88); min-height: 14px; }"
            "QProgressBar::chunk {"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #16a34a, stop:1 #22c55e);"
            "border-radius: 7px; }"
        )
        self.finishOverlay.hide()
        self.finishOverlay.raise_()
        self._finish_anim_timer = QTimer(self)
        self._finish_anim_timer.setInterval(75)
        self._finish_anim_timer.timeout.connect(self._tick_finish_anim)
        self._finish_anim_value = 0
        self._finish_anim_running = False
        self._finish_pending_clear = False
        self._operator_shift_flash_active = False
        self._operator_shift_flash_timer = QTimer(self)
        self._operator_shift_flash_timer.setSingleShot(True)
        self._operator_shift_flash_timer.timeout.connect(self._hide_operator_shift_overlay)

        # Settings overlay with category navigation (Graphics / Display).
        self.settingsOverlay = QFrame(self)
        self.settingsOverlay.setObjectName("SettingsOverlay")
        self.settingsOverlay.setLayout(QVBoxLayout())
        self.settingsOverlay.layout().setContentsMargins(0, 0, 0, 0)
        self.settingsOverlay.layout().setSpacing(0)

        self.settingsShell = QFrame()
        self.settingsShell.setObjectName("SettingsShell")
        self.settingsShell.setLayout(QHBoxLayout())
        self.settingsShell.layout().setContentsMargins(0, 0, 0, 0)
        self.settingsShell.layout().setSpacing(0)

        self.settingsNav = QFrame()
        self.settingsNav.setObjectName("SettingsNav")
        self.settingsNav.setLayout(QVBoxLayout())
        self.settingsNav.layout().setContentsMargins(14, 14, 14, 14)
        self.settingsNav.layout().setSpacing(8)
        self.settingsTitle = QLabel("APP SETTINGS")
        self.settingsTitle.setObjectName("SettingsNavTitle")
        self.settingsBtnGraphics = QPushButton("Graphics")
        self.settingsBtnGraphics.setObjectName("SettingsNavButton")
        self.settingsBtnGraphics.setCheckable(True)
        self.settingsBtnDisplay = QPushButton("Display")
        self.settingsBtnDisplay.setObjectName("SettingsNavButton")
        self.settingsBtnDisplay.setCheckable(True)
        self.settingsBtnApi = QPushButton("API Config")
        self.settingsBtnApi.setObjectName("SettingsNavButton")
        self.settingsBtnApi.setCheckable(True)
        self.settingsNav.layout().addWidget(self.settingsTitle)
        self.settingsNav.layout().addSpacing(8)
        self.settingsNav.layout().addWidget(self.settingsBtnGraphics)
        self.settingsNav.layout().addWidget(self.settingsBtnDisplay)
        self.settingsNav.layout().addWidget(self.settingsBtnApi)
        self.settingsNav.layout().addStretch(1)

        self.settingsContent = QFrame()
        self.settingsContent.setObjectName("SettingsContent")
        self.settingsContent.setLayout(QVBoxLayout())
        self.settingsContent.layout().setContentsMargins(14, 12, 14, 12)
        self.settingsContent.layout().setSpacing(8)
        self.settingsContentTop = QHBoxLayout()
        self.settingsContentTop.setContentsMargins(0, 0, 0, 0)
        self.settingsContentTop.setSpacing(8)
        self.settingsContentTitle = QLabel("Graphics")
        self.settingsContentTitle.setObjectName("SettingsContentTitle")
        self.settingsCloseBtn = QPushButton("X")
        self.settingsCloseBtn.setObjectName("SettingsCloseX")
        self.settingsCloseBtn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settingsContentTop.addWidget(self.settingsContentTitle, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.settingsContentTop.addWidget(self.settingsCloseBtn, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.settingsContentDivider = QFrame()
        self.settingsContentDivider.setFrameShape(QFrame.Shape.HLine)
        self.settingsContentDivider.setFrameShadow(QFrame.Shadow.Plain)
        self.settingsContentDivider.setObjectName("SettingsContentDivider")

        self.settingsScroll = QScrollArea()
        self.settingsScroll.setObjectName("SettingsScroll")
        self.settingsScroll.setWidgetResizable(True)
        self.settingsScroll.setFrameShape(QFrame.Shape.NoFrame)
        self.settingsScroll.setStyleSheet(
            """
            QScrollArea#SettingsScroll {
                background: transparent;
                border: none;
            }
            QScrollArea#SettingsScroll > QWidget > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                background: rgba(15, 23, 42, 0.22);
                width: 12px;
                margin: 4px 2px 4px 2px;
                border-radius: 6px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(148, 163, 184, 0.92),
                    stop:1 rgba(100, 116, 139, 0.95)
                );
                min-height: 34px;
                border-radius: 6px;
                border: 1px solid rgba(255, 255, 255, 0.20);
            }
            QScrollBar::handle:vertical:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(203, 213, 225, 0.96),
                    stop:1 rgba(148, 163, 184, 0.98)
                );
            }
            QScrollBar::handle:vertical:pressed {
                background: rgba(226, 232, 240, 0.95);
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
                background: transparent;
                border: none;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QScrollBar:horizontal {
                background: rgba(15, 23, 42, 0.18);
                height: 12px;
                margin: 2px 4px 2px 4px;
                border-radius: 6px;
                border: none;
            }
            QScrollBar::handle:horizontal {
                background: rgba(148, 163, 184, 0.9);
                min-width: 34px;
                border-radius: 6px;
                border: 1px solid rgba(255, 255, 255, 0.20);
            }
            QScrollBar::handle:horizontal:hover {
                background: rgba(203, 213, 225, 0.95);
            }
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0px;
                background: transparent;
                border: none;
            }
            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {
                background: transparent;
            }
            """
        )
        self.settingsScrollContent = QWidget()
        self.settingsScrollContent.setObjectName("SettingsScrollContent")
        self.settingsScrollContent.setLayout(QVBoxLayout())
        self.settingsScrollContent.layout().setContentsMargins(0, 0, 4, 0)
        self.settingsScrollContent.layout().setSpacing(0)

        self.settingsGraphicsSection = QWidget()
        self.settingsGraphicsSection.setObjectName("SettingsPage")
        self.settingsGraphicsSection.setLayout(QVBoxLayout())
        self.settingsGraphicsSection.layout().setContentsMargins(0, 0, 0, 0)
        self.settingsGraphicsSection.layout().setSpacing(8)
        self.chkCheckAnimation = QPushButton()
        self.chkCheckAnimation.setObjectName("SettingToggle")
        self.chkCheckAnimation.setCheckable(True)
        self.chkCheckAnimation.setChecked(True)
        self.chkFlashingLights = QPushButton()
        self.chkFlashingLights.setObjectName("SettingToggle")
        self.chkFlashingLights.setCheckable(True)
        self.chkFlashingLights.setChecked(True)
        self.chkPulseEffects = QPushButton()
        self.chkPulseEffects.setObjectName("SettingToggle")
        self.chkPulseEffects.setCheckable(True)
        self.chkPulseEffects.setChecked(True)
        self._set_toggle_button_text(self.chkCheckAnimation, "Check animation", True)
        self._set_toggle_button_text(self.chkFlashingLights, "Flashing lights", True)
        self._set_toggle_button_text(self.chkPulseEffects, "Pulse / moving effects", True)
        for btn in (self.chkCheckAnimation, self.chkFlashingLights, self.chkPulseEffects):
            btn.setFixedWidth(300)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.graphicsSectionTitle = QLabel("Graphics")
        self.graphicsSectionTitle.setObjectName("MetaLabel")
        self.settingsGraphicsSection.layout().addWidget(self.graphicsSectionTitle)
        self.settingsGraphicsSection.layout().addWidget(self.chkCheckAnimation, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsGraphicsSection.layout().addWidget(self.chkFlashingLights, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsGraphicsSection.layout().addWidget(self.chkPulseEffects, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsGraphicsSection.layout().addStretch(1)

        self.settingsDisplaySection = QWidget()
        self.settingsDisplaySection.setObjectName("SettingsPage")
        self.settingsDisplaySection.setLayout(QVBoxLayout())
        self.settingsDisplaySection.layout().setContentsMargins(0, 0, 0, 0)
        self.settingsDisplaySection.layout().setSpacing(8)
        self.displayOsLabel = QLabel("OS Profile")
        self.displayOsLabel.setObjectName("MetaLabel")
        self.displayOsCombo = QComboBox()
        self.displayOsCombo.addItems(["Raspberry Pi OS", "Linux", "Windows"])
        self.displaySizeLabel = QLabel("Monitor / Window Size")
        self.displaySizeLabel.setObjectName("MetaLabel")
        self.displaySizeCombo = QComboBox()
        self.displaySizeCombo.addItems([
            "Fullscreen",
            "1024x600",
            "1280x720",
            "1366x768",
            "1600x900",
            "1920x1080",
        ])
        self.displayApplyBtn = QPushButton("Apply")
        self.displayApplyBtn.setObjectName("SettingToggle")
        self.displayOsCombo.setFixedWidth(190)
        self.displaySizeCombo.setFixedWidth(190)
        self.displayApplyBtn.setFixedWidth(190)
        self.displayApplyBtn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.settingsDisplaySection.layout().addWidget(self.displayOsLabel)
        self.settingsDisplaySection.layout().addWidget(self.displayOsCombo, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsDisplaySection.layout().addWidget(self.displaySizeLabel)
        self.settingsDisplaySection.layout().addWidget(self.displaySizeCombo, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsDisplaySection.layout().addWidget(self.displayApplyBtn, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsDisplaySection.layout().addStretch(1)

        self.settingsApiSection = QWidget()
        self.settingsApiSection.setObjectName("SettingsPage")
        self.settingsApiSection.setLayout(QVBoxLayout())
        self.settingsApiSection.layout().setContentsMargins(0, 0, 0, 0)
        self.settingsApiSection.layout().setSpacing(8)

        self.apiServerUrlLabel = QLabel("Server URL")
        self.apiServerUrlLabel.setObjectName("MetaLabel")
        self.apiServerUrlInput = QLineEdit()
        self.apiServerUrlInput.setPlaceholderText("http://192.168.1.178:8000")

        self.apiClientIdLabel = QLabel("Client ID")
        self.apiClientIdLabel.setObjectName("MetaLabel")
        self.apiClientIdInput = QLineEdit()
        self.apiClientIdInput.setPlaceholderText(socket.gethostname())

        self.apiScannerModeLabel = QLabel("Scanner Mode")
        self.apiScannerModeLabel.setObjectName("MetaLabel")
        self.apiScannerModeCombo = QComboBox()
        self.apiScannerModeCombo.addItems(["auto", "keyboard", "serial"])

        self.apiScannerPortLabel = QLabel("Scanner COM Port")
        self.apiScannerPortLabel.setObjectName("MetaLabel")
        self.apiScannerPortInput = QLineEdit()
        self.apiScannerPortInput.setPlaceholderText("/dev/ttyACM0 or COM3")

        self.apiScannerBaudLabel = QLabel("Scanner Baudrate")
        self.apiScannerBaudLabel.setObjectName("MetaLabel")
        self.apiScannerBaudInput = QLineEdit()
        self.apiScannerBaudInput.setPlaceholderText("9600")

        self.apiScannerTimeoutLabel = QLabel("Scanner Timeout (sec)")
        self.apiScannerTimeoutLabel.setObjectName("MetaLabel")
        self.apiScannerTimeoutInput = QLineEdit()
        self.apiScannerTimeoutInput.setPlaceholderText("1.0")

        self.apiJobApiBaseUrlLabel = QLabel("Job API Base URL")
        self.apiJobApiBaseUrlLabel.setObjectName("MetaLabel")
        self.apiJobApiBaseUrlInput = QLineEdit()
        self.apiJobApiBaseUrlInput.setPlaceholderText("http://<host>")

        self.apiJobApiUserLabel = QLabel("Job API Username")
        self.apiJobApiUserLabel.setObjectName("MetaLabel")
        self.apiJobApiUserInput = QLineEdit()
        self.apiJobApiUserInput.setPlaceholderText("svcapiroleprod")

        self.apiJobApiTokenLabel = QLabel("Job API Bearer Token")
        self.apiJobApiTokenLabel.setObjectName("MetaLabel")
        self.apiJobApiTokenInput = QLineEdit()
        self.apiJobApiTokenInput.setEchoMode(QLineEdit.EchoMode.Password)
        self.apiJobApiTokenInput.setPlaceholderText("<API_TOKEN>")

        self.apiJobApiPasswordLabel = QLabel("Job API Password")
        self.apiJobApiPasswordLabel.setObjectName("MetaLabel")
        self.apiJobApiPasswordInput = QLineEdit()
        self.apiJobApiPasswordInput.setEchoMode(QLineEdit.EchoMode.Password)
        self.apiJobApiPasswordInput.setPlaceholderText("Password")

        self.apiJobApiTestBtn = QPushButton("Test Job API (GET)")
        self.apiJobApiTestBtn.setObjectName("SettingToggle")
        self.apiApplyBtn = QPushButton("Apply API Config")
        self.apiApplyBtn.setObjectName("SettingToggle")
        for w in (
            self.apiServerUrlInput,
            self.apiClientIdInput,
            self.apiScannerModeCombo,
            self.apiScannerPortInput,
            self.apiScannerBaudInput,
            self.apiScannerTimeoutInput,
            self.apiJobApiBaseUrlInput,
            self.apiJobApiUserInput,
            self.apiJobApiTokenInput,
            self.apiJobApiPasswordInput,
            self.apiJobApiTestBtn,
            self.apiApplyBtn,
        ):
            w.setFixedWidth(320)

        self.settingsApiSection.layout().addWidget(self.apiServerUrlLabel)
        self.settingsApiSection.layout().addWidget(self.apiServerUrlInput, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsApiSection.layout().addWidget(self.apiClientIdLabel)
        self.settingsApiSection.layout().addWidget(self.apiClientIdInput, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsApiSection.layout().addWidget(self.apiScannerModeLabel)
        self.settingsApiSection.layout().addWidget(self.apiScannerModeCombo, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsApiSection.layout().addWidget(self.apiScannerPortLabel)
        self.settingsApiSection.layout().addWidget(self.apiScannerPortInput, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsApiSection.layout().addWidget(self.apiScannerBaudLabel)
        self.settingsApiSection.layout().addWidget(self.apiScannerBaudInput, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsApiSection.layout().addWidget(self.apiScannerTimeoutLabel)
        self.settingsApiSection.layout().addWidget(self.apiScannerTimeoutInput, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsApiSection.layout().addWidget(self.apiJobApiBaseUrlLabel)
        self.settingsApiSection.layout().addWidget(self.apiJobApiBaseUrlInput, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsApiSection.layout().addWidget(self.apiJobApiUserLabel)
        self.settingsApiSection.layout().addWidget(self.apiJobApiUserInput, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsApiSection.layout().addWidget(self.apiJobApiTokenLabel)
        self.settingsApiSection.layout().addWidget(self.apiJobApiTokenInput, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsApiSection.layout().addWidget(self.apiJobApiPasswordLabel)
        self.settingsApiSection.layout().addWidget(self.apiJobApiPasswordInput, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsApiSection.layout().addWidget(self.apiJobApiTestBtn, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsApiSection.layout().addWidget(self.apiApplyBtn, 0, Qt.AlignmentFlag.AlignLeft)
        self.settingsApiSection.layout().addStretch(1)

        # Job API settings are available in the client Settings > API Config section.

        self.settingsCloseBtn.clicked.connect(self._hide_settings_overlay)
        self.chkCheckAnimation.toggled.connect(self._on_setting_check_animation_toggled)
        self.chkFlashingLights.toggled.connect(self._on_setting_flashing_lights_toggled)
        self.chkPulseEffects.toggled.connect(self._on_setting_pulse_effects_toggled)
        self.settingsBtnGraphics.clicked.connect(lambda: self._show_settings_section("graphics"))
        self.settingsBtnDisplay.clicked.connect(lambda: self._show_settings_section("display"))
        self.settingsBtnApi.clicked.connect(lambda: self._show_settings_section("api"))
        self.displayApplyBtn.clicked.connect(self._apply_display_settings)
        self.apiJobApiTestBtn.clicked.connect(self._test_job_api_settings)
        self.apiApplyBtn.clicked.connect(self._apply_api_settings)
        self.settingsContent.layout().addLayout(self.settingsContentTop)
        self.settingsContent.layout().addWidget(self.settingsContentDivider)
        self.settingsScrollContent.layout().addWidget(self.settingsGraphicsSection)
        self.settingsScrollContent.layout().addWidget(self.settingsDisplaySection)
        self.settingsScrollContent.layout().addWidget(self.settingsApiSection)
        self.settingsScrollContent.layout().addStretch(1)
        self.settingsScroll.setWidget(self.settingsScrollContent)
        self.settingsContent.layout().addWidget(self.settingsScroll, 1)
        self.settingsShell.layout().addWidget(self.settingsNav, 0)
        self.settingsShell.layout().addWidget(self.settingsContent, 1)
        self.settingsOverlay.layout().addWidget(self.settingsShell)
        self._load_api_settings_form()
        self._show_settings_section("graphics")
        self.settingsOverlay.hide()
        self.settingsOverlay.raise_()

        self._repair_movie: Optional[QMovie] = None
        if REPAIR_GIF and os.path.exists(REPAIR_GIF):
            repair_movie = QMovie(REPAIR_GIF)
            if repair_movie.isValid():
                self.productionFixAnim.setMovie(repair_movie)
                self._repair_movie = repair_movie
        self._overlay_mode = "select"
        self._overlay_pulse_on = False
        self._pulse_phase = 0.0
        self._machine_idle_flash_phase = 0.0
        self._overlay_shadow = QGraphicsDropShadowEffect(self)
        self._overlay_shadow.setBlurRadius(18)
        self._overlay_shadow.setOffset(0, 0)
        self._overlay_shadow.setColor(Qt.GlobalColor.transparent)
        self.productionOverlay.setGraphicsEffect(self._overlay_shadow)
        self._blur_left = None
        self._blur_right = None
        self.leftWrap.setGraphicsEffect(None)
        self.rightPanel.setGraphicsEffect(None)
        self._set_production_overlay_mode("select")
        self.productionOverlay.hide()
        self.productionOverlay.raise_()

        self.scan_received.connect(self.on_scanned)
        self.scanner_status.connect(self._set_status_text)
        self._setup_scanner_input()

        # heartbeat timer
        self.hb = QTimer(self)
        self.hb.timeout.connect(self.send_heartbeat)
        self.hb.start(1500)

        # Keep profile/role cache synced from server so remote profile creation is recognized by scans.
        self.identitySyncTimer = QTimer(self)
        self.identitySyncTimer.timeout.connect(lambda: self._trigger_identity_cache_sync(force=False))
        self.identitySyncTimer.start(3000)
        QTimer.singleShot(250, lambda: self._trigger_identity_cache_sync(force=True))

        self.motionTimer = QTimer(self)
        self.motionTimer.timeout.connect(self._tick_motion)
        self.motionTimer.start(60)

        self.downtimeTimer = QTimer(self)
        self.downtimeTimer.timeout.connect(self._refresh_downtime_panel)
        self.downtimeTimer.start(1000)

        self.overlayPulseTimer = QTimer(self)
        self.overlayPulseTimer.timeout.connect(self._tick_overlay_pulse)
        self.overlayPulseTimer.start(70)

        self.rejectDetailFlashTimer = QTimer(self)
        self.rejectDetailFlashTimer.timeout.connect(self._tick_reject_detail_flash)
        self.rejectDetailFlashTimer.start(450)
        self._reject_detail_flash_on = False
        self.clockTimer = QTimer(self)
        self.clockTimer.timeout.connect(self._update_header_datetime)
        self.clockTimer.start(1000)
        self._update_header_datetime()
        QTimer.singleShot(0, self._sync_machine_status_pulse_overlay)

        self._refresh_ui()
        QTimer.singleShot(0, self._apply_adaptive_ui_scale)
        QTimer.singleShot(0, self._sync_right_panel_top_alignment)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_right_panel_top_alignment()
        self._position_invalid_overlay()
        self._position_production_overlay()
        self._position_resolve_overlay()
        self._position_raw_mats_overlay()
        self._position_reject_summary_overlay()
        self._position_product_history_overlay()
        self._position_reject_review_overlay()
        self._position_finish_overlay()
        self._sync_machine_status_pulse_overlay()

    def _screen_ui_scale(self) -> float:
        screen = None
        try:
            win = self.windowHandle()
            if win is not None:
                screen = win.screen()
        except Exception:
            screen = None
        if screen is None:
            try:
                screen = self.screen()
            except Exception:
                screen = None
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return 1.0
        try:
            geom = screen.geometry()
            width = max(1, int(geom.width()))
            height = max(1, int(geom.height()))
        except Exception:
            return 1.0
        raw_scale = min(width / float(self.UI_BASE_WIDTH), height / float(self.UI_BASE_HEIGHT))
        return max(self.UI_MIN_SCALE, min(self.UI_MAX_SCALE, raw_scale))

    def _scale_px_value(self, value: float, scale: float) -> int:
        scaled = int(round(float(value) * float(scale)))
        if value <= 0:
            return max(0, scaled)
        return max(1, scaled)

    def _scale_stylesheet_px(self, css: str, scale: float) -> str:
        if not css or abs(scale - 1.0) < 0.01:
            return css

        def _repl(match):
            try:
                num = float(match.group(1))
            except Exception:
                return match.group(0)
            return f"{self._scale_px_value(num, scale)}px"

        return re.sub(r"(\d+(?:\.\d+)?)px", _repl, css)

    def _capture_ui_scale_bases(self):
        if self._ui_scale_bases:
            return

        widgets = [self] + self.findChildren(QWidget)
        for w in widgets:
            rec: Dict[str, Any] = {
                "style": w.styleSheet() or "",
                "min_w": int(w.minimumWidth()),
                "min_h": int(w.minimumHeight()),
                "max_w": int(w.maximumWidth()),
                "max_h": int(w.maximumHeight()),
                "font_pt": -1.0,
                "font_px": -1,
            }
            f = w.font()
            try:
                rec["font_pt"] = float(f.pointSizeF())
            except Exception:
                rec["font_pt"] = -1.0
            try:
                rec["font_px"] = int(f.pixelSize())
            except Exception:
                rec["font_px"] = -1
            self._ui_scale_bases[id(w)] = rec

        layouts = []
        if self.layout() is not None:
            layouts.append(self.layout())
        layouts.extend(self.findChildren(QVBoxLayout))
        layouts.extend(self.findChildren(QHBoxLayout))
        layouts.extend(self.findChildren(QGridLayout))
        seen_layouts: Set[int] = set()
        for layout in layouts:
            if layout is None or id(layout) in seen_layouts:
                continue
            seen_layouts.add(id(layout))
            margins = layout.contentsMargins()
            rec = {
                "margins": (
                    int(margins.left()),
                    int(margins.top()),
                    int(margins.right()),
                    int(margins.bottom()),
                ),
                "spacing": int(layout.spacing()),
            }
            if isinstance(layout, QGridLayout):
                rec["h_spacing"] = int(layout.horizontalSpacing())
                rec["v_spacing"] = int(layout.verticalSpacing())
            self._ui_layout_scale_bases[id(layout)] = rec

    def _apply_adaptive_ui_scale(self):
        if self._ui_scale_applied:
            return
        scale = self._screen_ui_scale()
        self._capture_ui_scale_bases()

        widgets = [self] + self.findChildren(QWidget)
        for w in widgets:
            rec = self._ui_scale_bases.get(id(w))
            if not rec:
                continue

            base_css = rec.get("style", "") or ""
            if base_css:
                w.setStyleSheet(self._scale_stylesheet_px(base_css, scale))

            font = w.font()
            base_font_px = int(rec.get("font_px", -1) or -1)
            base_font_pt = float(rec.get("font_pt", -1.0) or -1.0)
            if base_font_px > 0:
                font.setPixelSize(max(8, self._scale_px_value(base_font_px, scale)))
                w.setFont(font)
            elif base_font_pt > 0:
                font.setPointSizeF(max(6.0, base_font_pt * scale))
                w.setFont(font)

            max_default = 16777215
            min_w = int(rec.get("min_w", 0) or 0)
            min_h = int(rec.get("min_h", 0) or 0)
            max_w = int(rec.get("max_w", max_default) or max_default)
            max_h = int(rec.get("max_h", max_default) or max_default)

            scaled_min_w = self._scale_px_value(min_w, scale) if min_w > 0 else 0
            scaled_min_h = self._scale_px_value(min_h, scale) if min_h > 0 else 0
            scaled_max_w = self._scale_px_value(max_w, scale) if 0 < max_w < max_default else max_w
            scaled_max_h = self._scale_px_value(max_h, scale) if 0 < max_h < max_default else max_h

            if 0 < scaled_max_w < scaled_min_w:
                scaled_max_w = scaled_min_w
            if 0 < scaled_max_h < scaled_min_h:
                scaled_max_h = scaled_min_h

            w.setMinimumSize(scaled_min_w, scaled_min_h)
            w.setMaximumSize(scaled_max_w, scaled_max_h)

        layouts = []
        if self.layout() is not None:
            layouts.append(self.layout())
        layouts.extend(self.findChildren(QVBoxLayout))
        layouts.extend(self.findChildren(QHBoxLayout))
        layouts.extend(self.findChildren(QGridLayout))
        seen_layouts: Set[int] = set()
        for layout in layouts:
            if layout is None or id(layout) in seen_layouts:
                continue
            seen_layouts.add(id(layout))
            rec = self._ui_layout_scale_bases.get(id(layout))
            if not rec:
                continue
            l, t, r, b = rec.get("margins", (0, 0, 0, 0))
            layout.setContentsMargins(
                self._scale_px_value(l, scale) if l > 0 else 0,
                self._scale_px_value(t, scale) if t > 0 else 0,
                self._scale_px_value(r, scale) if r > 0 else 0,
                self._scale_px_value(b, scale) if b > 0 else 0,
            )
            spacing = int(rec.get("spacing", -1))
            if spacing >= 0:
                layout.setSpacing(self._scale_px_value(spacing, scale) if spacing > 0 else 0)
            if isinstance(layout, QGridLayout):
                h_spacing = int(rec.get("h_spacing", -1))
                v_spacing = int(rec.get("v_spacing", -1))
                if h_spacing >= 0:
                    layout.setHorizontalSpacing(self._scale_px_value(h_spacing, scale) if h_spacing > 0 else 0)
                if v_spacing >= 0:
                    layout.setVerticalSpacing(self._scale_px_value(v_spacing, scale) if v_spacing > 0 else 0)

        self._ui_scale = scale
        self._ui_scale_applied = True
        self.updateGeometry()
        self._sync_right_panel_top_alignment()
        self._sync_machine_status_pulse_overlay()

    def _sync_machine_status_pulse_overlay(self):
        if not hasattr(self, "machinePulseOverlay"):
            return
        host = self.machinePulseOverlay.parentWidget()
        if host is None:
            return
        self.machinePulseOverlay.setGeometry(host.rect())
        top_left = self.machineAnim.mapTo(host, self.machineAnim.rect().topLeft())
        target = QRectF(
            float(top_left.x()),
            float(top_left.y()),
            float(self.machineAnim.width()),
            float(self.machineAnim.height()),
        )
        self.machinePulseOverlay.set_target_rect(target)
        self.machinePulseOverlay.raise_()

    def _sync_right_panel_top_alignment(self):
        if not hasattr(self, "rightTopSpacer"):
            return
        try:
            # Align top right frame (Linkage Mirror) with the scan banner frame.
            target_ref = self.banner
            target_top = target_ref.mapTo(self, target_ref.rect().topLeft()).y()
            right_top = self.rightPanel.mapTo(self, self.rightPanel.rect().topLeft()).y()
            # Keep first right frame top aligned with the selected reference frame.
            offset = max(0, int(target_top - right_top))
            self.rightTopSpacer.setFixedHeight(offset)
        except Exception:
            self.rightTopSpacer.setFixedHeight(0)

    def _setup_invalid_overlay_media(self):
        gif_path = INVALID_SCAN_GIF
        if gif_path and os.path.exists(gif_path):
            movie = QMovie(gif_path)
            if movie.isValid():
                movie.jumpToFrame(0)
                movie.setScaledSize(self._fit_movie_size(self.invalidOverlay.size(), movie))
                movie.setSpeed(180)
                self.invalidGifLabel.setMovie(movie)
                self._invalid_movie = movie
                return
        # fallback is text-only overlay when gif is missing/invalid
        self._invalid_movie = None

    def _fit_movie_size(self, container: QSize, movie: Optional[QMovie] = None) -> QSize:
        m = movie or self._invalid_movie
        if m is None:
            return container
        frame = m.currentPixmap().size()
        if not frame.isValid() or frame.width() <= 0 or frame.height() <= 0:
            return container
        max_w = max(1, int(container.width() * 0.82))
        max_h = max(1, int(container.height() * 0.82))
        # Keep aspect ratio and do not upscale the GIF (prevents stretched-looking frames).
        ratio = min(1.0, max_w / frame.width(), max_h / frame.height())
        return QSize(max(1, int(frame.width() * ratio)), max(1, int(frame.height() * ratio)))

    def _position_invalid_overlay(self):
        fm = self.invalidTextLabel.fontMetrics()
        text_w = fm.horizontalAdvance("INVALID SCAN") + 24
        text_h = fm.height() + 12
        reason_text = str(self.invalidReasonLabel.text() or "").strip()

        max_overlay_w = max(360, int(self.width() * 0.94))
        max_overlay_h = max(220, int(self.height() * 0.90))
        max_reason_w = max(280, min(int(self.width() * 0.86), 980))
        reason_w = 0
        reason_h = 0
        if reason_text:
            rfm = self.invalidReasonLabel.fontMetrics()
            reason_rect = rfm.boundingRect(
                0, 0, max_reason_w, max(120, int(self.height() * 0.42)),
                int(Qt.TextFlag.TextWordWrap),
                reason_text,
            )
            reason_w = max(260, min(max_reason_w, reason_rect.width() + 20))
            reason_h = max(26, reason_rect.height() + 10)

        gif_size = QSize(220, 140)
        if self._invalid_movie is not None:
            f = self._invalid_movie.currentPixmap().size()
            if f.isValid():
                gif_size = QSize(max(180, min(320, f.width())), max(100, min(240, f.height())))

        band_w = max(text_w, reason_w, 260) + 20
        w = min(max_overlay_w, max(gif_size.width(), band_w) + 34)
        h = min(max_overlay_h, gif_size.height() + text_h + reason_h + 62)
        x = max(0, (self.width() - w) // 2)
        y = max(0, (self.height() - h) // 2)
        self.invalidOverlay.setGeometry(x, y, w, h)
        band_inner_w = max(240, w - 28)
        self.invalidTextBand.setMinimumWidth(band_inner_w)
        self.invalidReasonLabel.setMinimumWidth(max(220, band_inner_w - 16))
        self.invalidReasonLabel.setMaximumWidth(max(220, band_inner_w - 16))

    def _show_invalid_overlay(self, reason: str = ""):
        msg = str(reason or "").strip()
        self.invalidReasonLabel.setText(msg)
        self._position_invalid_overlay()
        if self._invalid_movie is not None:
            self._invalid_movie.stop()
            self._invalid_movie.setScaledSize(self._fit_movie_size(self.invalidOverlay.size()))
            self._invalid_movie.start()
            self.invalidGifLabel.show()
        else:
            self.invalidGifLabel.hide()
        self.invalidTextLabel.setText("INVALID SCAN")
        self.invalidOverlay.show()
        self.invalidOverlay.raise_()
        self.invalidOverlay.layout().activate()
        # Longer messages need more time to read.
        hide_ms = 3000 + min(5000, max(0, len(msg) - 40) * 35)
        self._invalid_hide_timer.start(hide_ms)

    def _hide_invalid_overlay(self):
        if self._invalid_movie is not None:
            self._invalid_movie.stop()
        self.invalidOverlay.hide()

    def _position_production_overlay(self):
        w = min(760, max(500, int(self.width() * 0.58)))
        h = min(620, max(420, int(self.height() * 0.72)))
        x = max(0, (self.width() - w) // 2)
        y = max(0, (self.height() - h) // 2)
        self.productionOverlay.setGeometry(x, y, w, h)
        self._sync_pdr_pulse_overlay()
        self._position_marquee()
        self._update_repair_movie_size()

    def _sync_pdr_pulse_overlay(self):
        if not hasattr(self, "pdrPulseOverlay"):
            return
        self.pdrPulseOverlay.setGeometry(self.productionOverlay.rect())
        top_left = self.productionCounter.mapTo(self.productionOverlay, self.productionCounter.rect().topLeft())
        target = QRectF(
            float(top_left.x()),
            float(top_left.y()),
            float(self.productionCounter.width()),
            float(self.productionCounter.height()),
        )
        self.pdrPulseOverlay.set_target_rect(target)
        self.pdrPulseOverlay.raise_()

    def _position_resolve_overlay(self):
        self.resolveOverlay.adjustSize()
        hint_h = self.resolveOverlay.sizeHint().height()
        hint_w = self.resolveOverlay.sizeHint().width()
        w = min(max(560, int(self.width() * 0.95)), max(520, hint_w + 24, int(self.width() * 0.58)))
        h = min(max(320, int(self.height() * 0.90)), max(260, hint_h + 16))
        x = max(0, (self.width() - w) // 2)
        y = max(0, (self.height() - h) // 2)
        self.resolveOverlay.setGeometry(x, y, w, h)

    def _position_raw_mats_overlay(self):
        w = min(1100, max(700, int(self.width() * 0.82)))
        h = min(640, max(360, int(self.height() * 0.65)))
        x = max(0, (self.width() - w) // 2)
        y = max(0, (self.height() - h) // 2)
        self.rawMatsOverlay.setGeometry(x, y, w, h)

    def _position_reject_summary_overlay(self):
        w = min(720, max(460, int(self.width() * 0.52)))
        h = min(520, max(260, int(self.height() * 0.42)))
        x = max(0, (self.width() - w) // 2)
        y = max(0, (self.height() - h) // 2)
        self.rejectSummaryOverlay.setGeometry(x, y, w, h)

    def _position_product_history_overlay(self):
        w = min(920, max(680, int(self.width() * 0.68)))
        h = min(700, max(520, int(self.height() * 0.70)))
        x = max(0, (self.width() - w) // 2)
        y = max(0, (self.height() - h) // 2)
        self.productHistoryOverlay.setGeometry(x, y, w, h)
        if hasattr(self, "productHistoryOrderNote") and self.productHistoryOrderNote is not None:
            note_w = min(300, max(220, int(self.width() * 0.22)))
            note_h = 66
            note_x = max(8, x - note_w - 10)
            note_y = max(8, y + 24)
            self.productHistoryOrderNote.setGeometry(note_x, note_y, note_w, note_h)
            if self.productHistoryOrderNote.isVisible():
                self.productHistoryOrderNote.raise_()

    def _position_reject_review_overlay(self):
        self.rejectReviewOverlay.adjustSize()
        hint_h = self.rejectReviewOverlay.sizeHint().height()
        hint_w = self.rejectReviewOverlay.sizeHint().width()
        w = min(620, max(420, hint_w + 28))
        h = min(460, max(220, hint_h + 20))
        x = max(0, (self.width() - w) // 2)
        y = max(0, (self.height() - h) // 2)
        self.rejectReviewOverlay.setGeometry(x, y, w, h)
        self.rejectReviewLoadingLayer.setGeometry(0, 0, w, h)

    def _position_finish_overlay(self):
        w = min(560, max(380, int(self.width() * 0.45)))
        h = min(280, max(210, int(self.height() * 0.30)))
        x = max(0, (self.width() - w) // 2)
        y = max(0, (self.height() - h) // 2)
        self.finishOverlay.setGeometry(x, y, w, h)

    def _position_settings_overlay(self):
        w = min(660, max(500, int(self.width() * 0.50)))
        h = min(620, max(360, int(self.height() * 0.64)))
        x = max(0, (self.width() - w) // 2)
        y = max(0, (self.height() - h) // 2)
        self.settingsOverlay.setGeometry(x, y, w, h)

    def _show_settings_overlay(self):
        self._position_settings_overlay()
        self._set_background_blur(True)
        self.settingsOverlay.show()
        self.settingsOverlay.raise_()

    def _hide_settings_overlay(self):
        self.settingsOverlay.hide()
        if not self._should_keep_background_blur():
            self._set_background_blur(False)

    def _refresh_raw_mats_overlay(self):
        logs = self.state.raw_material_logs or []
        table = self.rawMatsList
        table.setRowCount(0)
        valid_rows: List[Dict[str, Any]] = [x for x in logs if isinstance(x, dict)]
        if not valid_rows:
            table.setRowCount(1)
            empty_item = QTableWidgetItem("No raw materials scanned yet.")
            table.setItem(0, 0, empty_item)
            table.setSpan(0, 0, 1, 8)
            for c in range(1, 8):
                table.setItem(0, c, QTableWidgetItem(""))
            table.resizeRowsToContents()
            return

        table.setRowCount(len(valid_rows))
        for row_idx, item in enumerate(valid_rows):
            name = str(item.get("material_name") or item.get("material") or "-").strip() or "-"
            qty = int(item.get("qty") or 1)
            ts_raw = str(item.get("scanned_at") or "").strip()
            ts_text = ts_raw
            try:
                ts_dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                ts_text = ts_dt.astimezone().strftime("%Y-%m-%d %I:%M:%S %p")
            except Exception:
                pass

            values = [
                str(row_idx + 1),
                name,
                str(qty),
                str(item.get("index") or "-"),
                str(item.get("total_labels") or "-"),
                str(item.get("lot_number") or "-"),
                str(item.get("po_number") or item.get("raw_job_code") or "-"),
                ts_text,
            ]
            for col_idx, val in enumerate(values):
                cell = QTableWidgetItem(val)
                if col_idx in (0, 2, 3, 4):
                    cell.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
                else:
                    cell.setTextAlignment(int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft))
                table.setItem(row_idx, col_idx, cell)

        table.clearSpans()
        table.resizeRowsToContents()
        for col in range(0, 7):
            table.resizeColumnToContents(col)

    def _show_raw_mats_overlay(self):
        self._refresh_raw_mats_overlay()
        self._position_raw_mats_overlay()
        self._set_background_blur(True)
        self.rawMatsOverlay.show()
        self.rawMatsOverlay.raise_()

    def _hide_raw_mats_overlay(self):
        self.rawMatsOverlay.hide()
        if not self._should_keep_background_blur():
            self._set_background_blur(False)

    def _normalized_reject_counts(self, breakdown: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
        counts_by_name: Dict[str, int] = {}
        source = breakdown if isinstance(breakdown, dict) else (self.state.reject_breakdown or {})
        for k, v in source.items():
            key = str(k).strip().upper()
            try:
                qty = int(v or 0)
            except Exception:
                qty = 0
            counts_by_name[key] = counts_by_name.get(key, 0) + qty
        out: Dict[str, int] = {}
        for code, label in REJECT_DETAIL_ITEMS:
            by_name = counts_by_name.get(label.upper(), 0)
            by_code = counts_by_name.get(code.upper(), 0)
            out[code] = by_name if by_name else by_code
        return out

    def _refresh_reject_summary_overlay(self):
        s = self.state
        stamp_raw = str(s.reject_summary_last_scanned_at or "").strip()
        stamp_text = stamp_raw
        if stamp_raw:
            try:
                dt = datetime.fromisoformat(stamp_raw.replace("Z", "+00:00"))
                stamp_text = dt.astimezone().strftime("%Y-%m-%d %I:%M:%S %p")
            except Exception:
                pass
        self.rejectSummaryStamp.setText(f"Scanned at: {stamp_text or '-'}")
        pending_name = ""
        if s.waiting_cycle_time_confirm_popup and int(s.cycle_time_confirm_phase or 0) == 2:
            pending_name = str(s.cycle_time_confirm_actor_name or "").strip()
        confirmed_name = pending_name or str(s.cycle_time_confirmed_by or "").strip() or "-"
        self.rejectSummaryConfirmedBy.setText(f"Confirmed by: {confirmed_name}")
        self.rejectSummaryTotals.setText(
            f"Reject Total: {int(s.reject_total or 0)} | Start Up Reject: {int(s.startup_reject_total or 0)}"
        )
        counts = self._normalized_reject_counts()
        self.rejectSummaryDetails.setRowCount(1)
        for col, (code, _label) in enumerate(REJECT_DETAIL_ITEMS):
            item = QTableWidgetItem(str(int(counts.get(code, 0))))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.rejectSummaryDetails.setItem(0, col, item)

    def _show_reject_summary_overlay(self):
        self._refresh_reject_summary_overlay()
        self._position_reject_summary_overlay()
        self._set_background_blur(True)
        self.rejectSummaryOverlay.show()
        self.rejectSummaryOverlay.raise_()

    def _hide_reject_summary_overlay(self):
        self.rejectSummaryOverlay.hide()
        if not self._should_keep_background_blur():
            self._set_background_blur(False)

    def _refresh_product_history_overlay(self):
        logs = self.state.product_pack_history_logs or []
        table = self.productHistoryList
        table.setRowCount(0)
        valid_rows: List[Dict[str, Any]] = [x for x in logs if isinstance(x, dict)]
        page_size = max(1, int(getattr(self, "_product_history_page_size", 15) or 15))
        total_rows = len(valid_rows)
        total_pages = max(1, (total_rows + page_size - 1) // page_size)
        self._product_history_page = max(0, min(int(getattr(self, "_product_history_page", 0) or 0), total_pages - 1))

        def _fmt_product_id(raw_val: Any) -> str:
            s = str(raw_val or "").strip()
            if s.isdigit():
                return s.lstrip("0") or "0"
            return s

        def _fmt_scan_time(ts_raw: str) -> str:
            text = ts_raw
            try:
                ts_dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                text = ts_dt.astimezone().strftime("%b %d, %Y, %I:%M:%S %p")
            except Exception:
                pass
            return text or "-"

        def _compact_product_text(product_id_text: str, product_name_text: str) -> str:
            base = product_id_text or "-"
            if not product_name_text or product_name_text == "-":
                return base
            name = str(product_name_text).strip()
            max_name = 28
            if len(name) > max_name:
                name = name[: max_name - 3].rstrip() + "..."
            return f"{base} | {name}"

        def _compact_text(value: str, max_len: int) -> str:
            s = str(value or "").strip()
            if len(s) <= max_len:
                return s or "-"
            return s[: max_len - 3].rstrip() + "..."

        if not valid_rows:
            table.setRowCount(1)
            empty_item = QTableWidgetItem("No PACK QR scans recorded yet.")
            table.setItem(0, 0, empty_item)
            table.setSpan(0, 0, 1, 5)
            for c in range(1, 5):
                table.setItem(0, c, QTableWidgetItem(""))
            table.resizeRowsToContents()
            self.productHistorySummary.setText("No scans yet")
            self.productHistoryHint.setText('Scan "next" / "prev" to change page. Scan "prodhistory~1" again to close.')
            if hasattr(self, "productHistoryTopProduct"):
                self.productHistoryTopProduct.setText("Product ID: -")
                self.productHistoryTopScans.setText("Total Scans: 0")
                self.productHistoryTopQty.setText("Total Quantity: 0")
                self.productHistoryMetricProductValue.setText("-")
                self.productHistoryMetricLabelsValue.setText("0")
                self.productHistoryMetricQtyValue.setText("0")
                self.productHistoryMetricMissingValue.setText("-")
                self.productHistoryMetricMissingValue.setStyleSheet("color: #0f172a;")
                self.productHistoryPageInfo.setText("Page 1 of 1")
            if hasattr(self, "productHistoryOrderNote"):
                self.productHistoryOrderNote.hide()
            return

        label_numbers_by_row: List[Optional[int]] = []
        out_of_order_rows: Set[int] = set()
        last_label_num: Optional[int] = None
        scanned_label_set: Set[int] = set()
        expected_total_labels = 0
        for idx, row in enumerate(valid_rows):
            label_num: Optional[int] = None
            try:
                label_num = int(str((row or {}).get("index") or "").strip())
            except Exception:
                label_num = None
            label_numbers_by_row.append(label_num)
            if label_num is not None and label_num > 0:
                scanned_label_set.add(label_num)
                if last_label_num is not None and label_num < last_label_num:
                    out_of_order_rows.add(idx)
                last_label_num = label_num
            try:
                tl = int(str((row or {}).get("total_labels") or "").strip())
                if tl > expected_total_labels:
                    expected_total_labels = tl
            except Exception:
                pass
        if expected_total_labels <= 0 and scanned_label_set:
            expected_total_labels = max(scanned_label_set)
        missing_labels: List[int] = []
        if expected_total_labels > 0:
            missing_labels = [n for n in range(1, expected_total_labels + 1) if n not in scanned_label_set]

        start = self._product_history_page * page_size
        end = min(total_rows, start + page_size)
        page_rows = valid_rows[start:end]

        total_qty = 0
        for row in valid_rows:
            try:
                total_qty += int(float(row.get("qty_q") or row.get("qty") or 0))
            except Exception:
                pass
        self.productHistorySummary.setText(
            f"Total Scans: {total_rows}   |   Total Qty: {total_qty}   |   Page {self._product_history_page + 1} of {total_pages}"
        )
        self.productHistoryHint.setText(
            'Scan "next" / "prev" to change page. Scan "prodhistory~1" again to close.'
        )

        first_product_id = "-"
        for row in valid_rows:
            pid = _fmt_product_id((row or {}).get("product_p") or (row or {}).get("product_id"))
            if pid:
                first_product_id = pid
                break
        if hasattr(self, "productHistoryTopProduct"):
            self.productHistoryTopProduct.setText(f"Product ID: {first_product_id}")
            self.productHistoryTopScans.setText(f"Total Scans: {total_rows}")
            self.productHistoryTopQty.setText(f"Total Quantity: {total_qty}")
            self.productHistoryMetricProductValue.setText(first_product_id)
            self.productHistoryMetricLabelsValue.setText(str(total_rows))
            self.productHistoryMetricQtyValue.setText(str(total_qty))
            if missing_labels:
                if len(missing_labels) <= 6:
                    missing_text = ", ".join(str(x) for x in missing_labels)
                else:
                    missing_text = ", ".join(str(x) for x in missing_labels[:6]) + f" (+{len(missing_labels) - 6})"
            else:
                missing_text = "None"
            self.productHistoryMetricMissingValue.setText(missing_text)
            self.productHistoryMetricMissingValue.setStyleSheet(
                "color: #991b1b;" if missing_labels else "color: #14532d;"
            )
            self.productHistoryPageInfo.setText(f"Page {self._product_history_page + 1} of {total_pages}")
            if hasattr(self, "productHistoryOrderNote"):
                if out_of_order_rows:
                    self.productHistoryOrderNote.show()
                    self.productHistoryOrderNote.raise_()
                else:
                    self.productHistoryOrderNote.hide()

        table.setRowCount(len(page_rows))
        for row_idx, item in enumerate(page_rows):
            product_id = _fmt_product_id(item.get("product_p") or item.get("product_id"))
            if not product_id:
                product_id = "-"
            product_name = self._lookup_product_name(product_id) or str(item.get("product_name") or "-").strip() or "-"
            label_number = str(item.get("index") or "-").strip() or "-"
            qty_text = str(item.get("qty_q") or item.get("qty") or "-").strip() or "-"
            operator_text = _compact_text(str(item.get("operator_name") or item.get("operator") or "-"), 18)
            ts_text = _fmt_scan_time(str(item.get("scanned_at") or "").strip())
            product_name_text = product_name if product_name and product_name != "-" else (product_id or "-")
            product_name_text = _compact_text(product_name_text, 22)

            values = [f"#{label_number}", product_name_text, qty_text, operator_text, ts_text]
            for col_idx, val in enumerate(values):
                cell = QTableWidgetItem(val)
                if col_idx in (0, 2):
                    cell.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
                else:
                    cell.setTextAlignment(int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft))
                if col_idx == 0 and (start + row_idx) in out_of_order_rows:
                    cell.setForeground(QColor("#7f1d1d"))
                    cell.setBackground(QColor(254, 202, 202))
                    f = cell.font()
                    f.setBold(True)
                    cell.setFont(f)
                    cell.setToolTip("Out of order scan sequence")
                table.setItem(row_idx, col_idx, cell)

        table.clearSpans()
        for col in range(0, 5):
            table.resizeColumnToContents(col)

    def _show_product_history_overlay(self):
        self._refresh_product_history_overlay()
        self._position_product_history_overlay()
        self._set_background_blur(True)
        self.productHistoryOverlay.show()
        self.productHistoryOverlay.raise_()

    def _hide_product_history_overlay(self):
        self.productHistoryOverlay.hide()
        if hasattr(self, "productHistoryOrderNote") and self.productHistoryOrderNote is not None:
            self.productHistoryOrderNote.hide()
        if not self._should_keep_background_blur():
            self._set_background_blur(False)

    def _ensure_product_catalog_index(self):
        if isinstance(self._product_catalog_name_by_id, dict):
            return
        self._product_catalog_name_by_id = {}
        raw = self._load_json_file(PRODUCT_CATALOG_CACHE_FILE, {})
        items = []
        if isinstance(raw, dict):
            maybe_items = raw.get("items")
            if isinstance(maybe_items, list):
                items = maybe_items
        elif isinstance(raw, list):
            items = raw
        for row in items:
            if not isinstance(row, dict):
                continue
            pid = str(row.get("id") or "").strip()
            name = str(row.get("name") or "").strip()
            if not pid or not name:
                continue
            key = pid.lstrip("0") or "0"
            self._product_catalog_name_by_id[key] = name

    def _lookup_product_name(self, product_id: str) -> str:
        pid = str(product_id or "").strip()
        if not pid:
            return ""
        self._ensure_product_catalog_index()
        key = pid.lstrip("0") if pid.isdigit() else pid
        key = key or "0"
        return str((self._product_catalog_name_by_id or {}).get(key) or "")

    def _load_json_file(self, path: str, fallback: Any) -> Any:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8-sig") as f:
                    return json.load(f)
        except Exception:
            pass
        return fallback

    def _save_json_file(self, path: str, payload: Any):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _trigger_identity_cache_sync(self, force: bool = False):
        server_url = str(self.client_config.get("server_url", SERVER_URL)).strip().rstrip("/")
        if not server_url:
            return
        now_ts = time.time()
        if not force and (now_ts - float(self._identity_sync_last_attempt or 0.0)) < 1.0:
            return
        with self._identity_sync_lock:
            if self._identity_sync_inflight:
                return
            self._identity_sync_inflight = True
            self._identity_sync_last_attempt = now_ts

        def _worker():
            ok = False
            try:
                headers = {"Accept": "application/json"}
                # Profiles cache (list)
                resp_profiles = requests.get(f"{server_url}/api/profiles", headers=headers, timeout=2.5)
                if resp_profiles.status_code == 200:
                    out_profiles = resp_profiles.json()
                    items = out_profiles.get("items") if isinstance(out_profiles, dict) else None
                    if isinstance(items, list):
                        ok = _save_profiles_sql(items) or ok

                # Daily roles cache is SQL-backed as {date: items}.
                resp_roles = requests.get(f"{server_url}/api/daily-roles", headers=headers, timeout=2.5)
                if resp_roles.status_code == 200:
                    out_roles = resp_roles.json()
                    if isinstance(out_roles, dict):
                        date_key = str(out_roles.get("date") or "").strip()
                        items = out_roles.get("items")
                        if date_key and isinstance(items, dict):
                            local_daily = _load_daily_role_assignments_sql()
                            local_daily[date_key] = items
                            ok = _save_daily_role_assignments_sql(local_daily) or ok
                        elif isinstance(items, dict):
                            local_daily = _load_daily_role_assignments_sql()
                            local_daily[datetime.now().date().isoformat()] = items
                            ok = _save_daily_role_assignments_sql(local_daily) or ok

            except Exception:
                ok = False
            finally:
                with self._identity_sync_lock:
                    if ok:
                        self._identity_sync_last_ok = time.time()
                    self._identity_sync_inflight = False

        threading.Thread(target=_worker, daemon=True).start()

    def _role_caps_from_text(self, text: Any) -> Set[str]:
        s = str(text or "").strip().lower()
        caps: Set[str] = set()
        if not s:
            return caps
        if "supervisor" in s:
            caps.add("supervisor")
        if "maintenance" in s:
            caps.add("maintenance")
        if "operator" in s:
            caps.add("operator")
        if "qa/qc" in s or "qaqc" in s or ("qa" in s and "qc" in s) or s in ("qc", "qa"):
            caps.add("qc")
        return caps

    def _authorized_person_from_scan(self, raw: str) -> Optional[Dict[str, str]]:
        code = str(raw).strip()
        if not code:
            return None
        self._trigger_identity_cache_sync(force=False)

        caps: Set[str] = set()
        display_name = ""

        # Fallback/static local badges.
        if code in SUPERVISOR_BADGES:
            caps.add("supervisor")
            display_name = SUPERVISOR_BADGES[code]
        if code in QC_BADGES:
            caps.add("qc")
            display_name = display_name or QC_BADGES[code]

        # Profile-based role from SQL-backed profile cache.
        profiles = _load_profiles_sql()
        for row in profiles:
            if not isinstance(row, dict):
                continue
            if str(row.get("id_number") or "").strip() != code:
                continue
            display_name = display_name or str(row.get("name") or "").strip()
            caps.update(self._role_caps_from_text(row.get("role")))
            break

        # Daily assignments can grant temporary rights (including both).
        daily_map = _load_daily_role_assignments_sql()
        if isinstance(daily_map, dict):
            today_key = datetime.now().date().isoformat()
            today_rows = daily_map.get(today_key)
            if isinstance(today_rows, dict):
                today_info = today_rows.get(code)
                if isinstance(today_info, dict):
                    display_name = display_name or str(today_info.get("name") or "").strip()
                    rights = str(today_info.get("rights") or "").strip().lower()
                    if rights == "both":
                        caps.update({"supervisor", "qc"})
                    else:
                        caps.update(self._role_caps_from_text(rights))
                    caps.update(self._role_caps_from_text(today_info.get("company_role")))
                    extra_priv = str(today_info.get("extra_privilege") or "").strip().lower()
                    if extra_priv in ("qc", "qa/qc", "qaqc"):
                        caps.add("qc")
                    if extra_priv == "supervisor":
                        caps.add("supervisor")

        if not caps:
            return None
        if {"supervisor", "qc"}.issubset(caps):
            role_text = "SUPERVISOR/QC"
        elif "supervisor" in caps:
            role_text = "SUPERVISOR"
        elif "qc" in caps:
            role_text = "QC"
        elif "maintenance" in caps:
            role_text = "MAINTENANCE"
        else:
            role_text = "AUTHORIZED"
        return {
            "code": code,
            "name": display_name or code,
            "role": role_text,
            "can_supervisor": "1" if "supervisor" in caps else "0",
            "can_qc": "1" if "qc" in caps else "0",
            "can_maintenance": "1" if "maintenance" in caps else "0",
            "can_operator": "1" if "operator" in caps else "0",
        }

    def _reviewer_from_scan(self, raw: str) -> Optional[Dict[str, str]]:
        person = self._authorized_person_from_scan(raw)
        if not person:
            return None
        if str(person.get("can_supervisor", "0")) == "1" or str(person.get("can_qc", "0")) == "1":
            return person
        return None

    def _operator_from_scan(self, raw: str) -> Optional[Dict[str, str]]:
        person = self._authorized_person_from_scan(raw)
        if not person:
            return None
        if str(person.get("can_operator", "0")) != "1":
            return None
        return person

    def _get_non_zero_rejects(self) -> List[tuple]:
        rows = []
        for key, count in (self.state.reject_breakdown or {}).items():
            qty = int(count or 0)
            if qty > 0:
                rows.append((str(key), qty))
        rows.sort(key=lambda x: x[0])
        return rows

    def _show_reject_review_overlay(self, reviewer: Dict[str, str]):
        s = self.state
        s.reject_review_open = True
        s.reject_review_phase = 1
        s.reject_review_actor_code = reviewer["code"]
        s.reject_review_actor_name = reviewer["name"]
        s.reject_review_actor_role = reviewer["role"]
        rows = self._get_non_zero_rejects()
        self.rejectReviewActor.setText(f"Authorized: {reviewer['name']}")
        self.rejectReviewList.setText("\n".join(f"{k}: {v}" for k, v in rows))
        self.rejectReviewCycle.hide()
        self.rejectReviewLoadingLayer.hide()
        self.rejectReviewLoadingBar.setValue(0)
        self.rejectReviewHint.setText("Scan the same authorized badge to show cycle count/time.")
        self._position_reject_review_overlay()
        self._set_background_blur(True)
        self.rejectReviewOverlay.show()
        self.rejectReviewOverlay.raise_()

    def _hide_reject_review_overlay(self):
        s = self.state
        s.reject_review_open = False
        s.reject_review_phase = 0
        s.reject_review_actor_code = None
        s.reject_review_actor_name = None
        s.reject_review_actor_role = None
        self.rejectReviewOverlay.hide()
        self._reject_review_anim_timer.stop()
        self.rejectReviewLoadingLayer.hide()
        self.rejectReviewLoadingBar.setValue(0)
        self._set_reject_review_blur(False)
        if not self._should_keep_background_blur():
            self._set_background_blur(False)

    def _show_finish_overlay(self):
        self._position_finish_overlay()
        self._set_background_blur(True)
        self.finishStatus.setText("Processing...")
        self.finishProgressBar.setValue(0)
        self.finishSuccessRow.hide()
        self.finishCheck.setProgress(0.0)
        self._finish_anim_value = 0
        self._finish_anim_running = True
        self.finishOverlay.show()
        self.finishOverlay.raise_()
        self._finish_anim_timer.start()

    def _hide_finish_overlay(self):
        self._finish_anim_timer.stop()
        self._finish_anim_running = False
        self.finishOverlay.hide()
        if not self._should_keep_background_blur():
            self._set_background_blur(False)

    def _tick_finish_anim(self):
        self._finish_anim_value = min(100, self._finish_anim_value + 7)
        self.finishProgressBar.setValue(self._finish_anim_value)
        if self._finish_anim_value < 100:
            return
        self._finish_anim_timer.stop()
        self.finishStatus.setText("Completed")
        self.finishSuccessRow.show()
        if self.enable_check_animation:
            self.finishCheck.start()
            QTimer.singleShot(900, self._complete_finish_sequence)
        else:
            self.finishCheck.setProgress(1.0)
            QTimer.singleShot(280, self._complete_finish_sequence)

    def _complete_finish_sequence(self):
        self._hide_finish_overlay()
        if self._finish_pending_clear:
            self._finish_pending_clear = False
            self._clear_full_session()

    def _show_operator_shift_overlay(self, shift_payload: Dict[str, Any]):
        name = self._safe_text(shift_payload.get("operator_name"), "-")
        code = self._safe_text(shift_payload.get("operator_id"), "-")
        summary = (
            f"Operator: {name} ({code})\n"
            f"Pack: {int(shift_payload.get('pack_count') or 0)} | "
            f"Good: {int(shift_payload.get('good_total') or 0)} | "
            f"Butal: {int(shift_payload.get('butal_total') or 0)} | "
            f"Reject: {int(shift_payload.get('reject_total') or 0)} | "
            f"Total Good: {int(shift_payload.get('total_good') or 0)}"
        )
        self._operator_shift_flash_active = True
        self._position_finish_overlay()
        self._set_background_blur(True)
        self.finishTitle.setText("OPERATOR SHIFT SAVED")
        self.finishStatus.setText(summary)
        self.finishProgressBar.hide()
        self.finishSuccessRow.hide()
        self.finishOverlay.show()
        self.finishOverlay.raise_()
        self._operator_shift_flash_timer.start(5000)

    def _hide_operator_shift_overlay(self):
        if not self._operator_shift_flash_active:
            return
        self._operator_shift_flash_active = False
        self.finishTitle.setText("FINISHING JOB")
        self.finishStatus.setText("Processing...")
        self.finishProgressBar.show()
        self.finishOverlay.hide()
        if not self._should_keep_background_blur():
            self._set_background_blur(False)

    def _set_reject_review_blur(self, enabled: bool):
        if enabled:
            if self._reject_review_blur_effects:
                return
            for target in self._reject_review_blur_targets:
                fx = QGraphicsBlurEffect(target)
                fx.setBlurRadius(2.8)
                target.setGraphicsEffect(fx)
                self._reject_review_blur_effects.append(fx)
            return
        for target in self._reject_review_blur_targets:
            target.setGraphicsEffect(None)
        self._reject_review_blur_effects = []

    def _tick_reject_review_anim(self):
        self._reject_review_anim_value = min(100, self._reject_review_anim_value + 8)
        self.rejectReviewLoadingBar.setValue(self._reject_review_anim_value)
        if self._reject_review_anim_value >= 100:
            self._reject_review_anim_timer.stop()
            self._set_reject_review_blur(False)

    def _update_repair_movie_size(self):
        if self._repair_movie is None:
            return
        base = self._repair_movie.currentPixmap().size()
        if not base.isValid() or base.width() <= 0 or base.height() <= 0:
            base = self._repair_movie.frameRect().size()
        if not base.isValid() or base.width() <= 0 or base.height() <= 0:
            return
        max_w = max(120, int(self.productionOverlay.width() * 0.46))
        max_h = 120
        ratio = min(max_w / base.width(), max_h / base.height())
        self._repair_movie.setScaledSize(QSize(max(1, int(base.width() * ratio)), max(1, int(base.height() * ratio))))

    def _position_marquee(self):
        if self.productionMarqueeText.parent() is not self.productionMarqueeWrap:
            self.productionMarqueeText.setParent(self.productionMarqueeWrap)
        y = max(0, (self.productionMarqueeWrap.height() - self.productionMarqueeText.sizeHint().height()) // 2)
        self.productionMarqueeText.move(self._marquee_x, y)

    def _show_production_overlay(self):
        self._position_production_overlay()
        self._set_background_blur(True)
        self.productionOverlay.setProperty("pulse", "0")
        self._overlay_shadow.setBlurRadius(18)
        self._overlay_shadow.setColor(Qt.GlobalColor.transparent)
        self.productionOverlay.show()
        self.productionOverlay.raise_()
        self._position_marquee()
        self._update_repair_movie_size()
        if self._repair_movie is not None and self._overlay_mode == "active":
            self._repair_movie.start()
        if self._overlay_mode == "active" and hasattr(self, "pdrPulseOverlay"):
            self._sync_pdr_pulse_overlay()
            self.pdrPulseOverlay.set_mode(True)
            self.pdrPulseOverlay.trigger_now()

    def _hide_production_overlay(self):
        if self._repair_movie is not None:
            self._repair_movie.stop()
        self.productionOverlay.hide()
        self.productionOverlay.setProperty("pulse", "0")
        self._overlay_shadow.setColor(Qt.GlobalColor.transparent)
        if not self._should_keep_background_blur():
            self._set_background_blur(False)
        self._apply_overlay_base_style()

    def _show_resolve_overlay(self):
        self._position_resolve_overlay()
        self._set_background_blur(True)
        self.resolveOverlay.show()
        self.resolveOverlay.raise_()

    def _hide_resolve_overlay(self):
        self.resolveOverlay.hide()
        if not self._should_keep_background_blur():
            self._set_background_blur(False)

    def _set_background_blur(self, enabled: bool):
        if enabled:
            self._blur_left = QGraphicsBlurEffect(self.leftWrap)
            self._blur_left.setBlurRadius(3.2)
            self._blur_right = QGraphicsBlurEffect(self.rightPanel)
            self._blur_right.setBlurRadius(3.2)
            self.leftWrap.setGraphicsEffect(self._blur_left)
            self.rightPanel.setGraphicsEffect(self._blur_right)
        else:
            self.leftWrap.setGraphicsEffect(None)
            self.rightPanel.setGraphicsEffect(None)
            self._blur_left = None
            self._blur_right = None

    def _set_production_overlay_mode(self, mode: str):
        self._overlay_mode = mode
        if mode == "select":
            self.productionTitle.setText("PRODUCTION DAILY REPORT")
            self.productionHint.setText("Scan reason QR code (01-15)")
            self.productionReasonList.show()
            self.productionLiveReason.hide()
            self.productionCounter.hide()
            self.productionFixAnim.hide()
            self.productionMarqueeWrap.hide()
            self.pdrPulseOverlay.advance(False)
            return
        self.productionTitle.setText("DOWNTIME ACTIVE")
        self.productionHint.setText("Machine under repair / adjustment")
        self.productionReasonList.hide()
        self.productionLiveReason.show()
        self.productionCounter.show()
        self.productionFixAnim.show()
        self.productionMarqueeWrap.show()
        self._sync_pdr_pulse_overlay()
        self.pdrPulseOverlay.set_mode(True)
        self.pdrPulseOverlay.trigger_now()
        self._marquee_x = self.productionMarqueeWrap.width()
        self._position_marquee()
        if self._repair_movie is not None and self.productionOverlay.isVisible():
            self._repair_movie.start()

    def _apply_overlay_base_style(self):
        self.productionOverlay.setStyleSheet(
            "QFrame#ProductionOverlay {"
            "background: qradialgradient(cx:0.5, cy:0.45, radius:0.9, fx:0.5, fy:0.45,"
            "stop:0 rgba(255,255,255,0.99), stop:0.58 rgba(248,250,252,0.98), stop:1 rgba(226,232,240,0.98));"
            "border: 3px solid #fb923c; border-radius: 14px; }"
        )

    def _tick_overlay_pulse(self):
        if not self.enable_pulse_effects:
            if self.productionOverlay.isVisible():
                self._overlay_shadow.setColor(Qt.GlobalColor.transparent)
                self._apply_overlay_base_style()
        if not self.productionOverlay.isVisible() or self._overlay_mode != "active":
            if hasattr(self, "pdrPulseOverlay"):
                self.pdrPulseOverlay.advance(False)
            return
        if self.enable_pulse_effects:
            self._pulse_phase += 0.16
            level = (math.sin(self._pulse_phase) + 1.0) * 0.5
            border_alpha = int(130 + 110 * level)
            glow_alpha = int(45 + 155 * level)
            blur = 18 + 16 * level
            self.productionOverlay.setStyleSheet(
                "QFrame#ProductionOverlay {"
                "background: qradialgradient(cx:0.5, cy:0.45, radius:0.9, fx:0.5, fy:0.45,"
                "stop:0 rgba(255,255,255,0.99), stop:0.58 rgba(248,250,252,0.98), stop:1 rgba(226,232,240,0.98));"
                f"border: 3px solid rgba(249,115,22,{border_alpha}); border-radius: 14px; }}"
            )
            self._overlay_shadow.setBlurRadius(blur)
            self._overlay_shadow.setColor(QColor(249, 115, 22, glow_alpha))
        else:
            self._overlay_shadow.setColor(Qt.GlobalColor.transparent)
            self._apply_overlay_base_style()
        self._sync_pdr_pulse_overlay()
        self.pdrPulseOverlay.set_mode(True)
        self.pdrPulseOverlay.advance(True, dt=0.07)
        self._tick_marquee()

    def _tick_marquee(self):
        if self._overlay_mode != "active" or not self.productionMarqueeWrap.isVisible():
            return
        text_w = self.productionMarqueeText.sizeHint().width()
        if text_w <= 0:
            self.productionMarqueeText.adjustSize()
            text_w = self.productionMarqueeText.sizeHint().width()
        self._marquee_x -= self._marquee_speed
        if self._marquee_x + text_w < 0:
            self._marquee_x = self.productionMarqueeWrap.width()
        self._position_marquee()

    def _make_card(self, title: str) -> QFrame:
        f = QFrame()
        f.setObjectName("Panel")
        f.setLayout(QVBoxLayout())
        f.layout().setContentsMargins(10, 8, 10, 8)
        f.layout().setSpacing(6)
        t = QLabel(title)
        t.setObjectName("SectionTitle")
        f.layout().addWidget(t)
        return f

    def _make_double_layer_card(self, title: str) -> tuple[QFrame, QFrame]:
        outer = QFrame()
        outer.setObjectName("LeftCardOuter")
        outer.setLayout(QVBoxLayout())
        outer.layout().setContentsMargins(8, 8, 8, 8)
        outer.layout().setSpacing(0)

        inner = self._make_card(title)
        inner.setObjectName("LeftCardInner")
        outer.layout().addWidget(inner)
        return outer, inner

    def _find_icon_path(self, key: str) -> Optional[str]:
        for candidate in self._label_icon_candidates.get(key.lower(), []):
            p1 = os.path.join(IMAGES_DIR, candidate)
            if os.path.exists(p1):
                return p1
            # Fallback: script directory and current working directory.
            p2 = os.path.join(BASE_DIR, candidate)
            if os.path.exists(p2):
                return p2
            if os.path.exists(candidate):
                return os.path.abspath(candidate)
        return None

    def _make_meta_label_with_icon(self, text: str) -> QWidget:
        key = text.strip().lower()
        icon_path = self._find_icon_path(key)
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        wrap.setFixedWidth(150)
        wrap.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        lay = QHBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        wrap.setLayout(lay)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(18, 18)
        if icon_path:
            pm = QPixmap(icon_path)
            if not pm.isNull():
                pm = pm.scaled(18, 18, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                icon_lbl.setPixmap(pm)
        lay.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        txt = QLabel(text)
        txt.setObjectName("MetaLabel")
        txt.setStyleSheet("font-size: 14px; font-weight: 800; background: transparent;")
        txt.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(txt, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        lay.addStretch(1)
        return wrap

    def _make_right_title_with_icon(self, text: str, icon_key: str) -> QWidget:
        icon_path = self._find_icon_path(icon_key)
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        lay = QHBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        wrap.setLayout(lay)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(26, 26)
        if icon_path:
            pm = QPixmap(icon_path)
            if not pm.isNull():
                pm = pm.scaled(26, 26, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                icon_lbl.setPixmap(pm)
        lay.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        txt = QLabel(text)
        txt.setObjectName("RightTitle")
        lay.addWidget(txt, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        lay.addStretch(1)
        return wrap

    def _make_stat_card(self, title: str, value_label: QLabel, stat_object_name: str) -> QFrame:
        f = QFrame()
        f.setProperty("role", "stat")
        f.setObjectName(stat_object_name)
        f.setLayout(QVBoxLayout())
        f.layout().setContentsMargins(8, 6, 8, 6)
        f.layout().setSpacing(2)
        t = QLabel(title)
        t.setObjectName("StatTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_label.setObjectName("StatValue")
        if isinstance(value_label, QLabel):
            value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            try:
                value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            except Exception:
                pass
        f.layout().addWidget(t)
        f.layout().addWidget(value_label)
        return f

    def _pulse_card(self, card: QFrame):
        if card is None:
            return
        if not self.enable_pulse_effects:
            return
        card.setProperty("flash", "1")
        card.style().unpolish(card)
        card.style().polish(card)
        QTimer.singleShot(220, lambda c=card: self._clear_pulse(c))

    def _clear_pulse(self, card: QFrame):
        if card is None:
            return
        card.setProperty("flash", "0")
        card.style().unpolish(card)
        card.style().polish(card)

    def _refresh_ui(self):
        s = self.state
        self.lblMachine.setText(f"Machine: {_machine_display_name(s.machine_code, s.machine_name)}")
        self.lblJob.setText(f"Job: {s.job_name or '-'}")
        self.lblOperator.setText(f"Operator: {self._operator_display_name(s.operator_id)}")
        payload = s.job_payload or {}
        data_obj = payload.get("data") if isinstance(payload, dict) else {}
        job = data_obj.get("job") if isinstance(data_obj, dict) else {}
        job_details = data_obj.get("job_details") if isinstance(data_obj, dict) else {}
        if not isinstance(job, dict):
            job = {}
        if not isinstance(job_details, dict):
            job_details = {}
        self.lblActivityMold.setText(f"Mold: {self._safe_text(job_details.get('mold') or job.get('custom_05'), '-')}")
        self.lblActivityColor.setText(f"Color: {self._safe_text(job_details.get('color') or job.get('custom_06'), '-')}")
        self.lblActivityCavities.setText(f"Cavities: {self._safe_text(job_details.get('no_of_cavity') or job.get('custom_11'), '-')}")
        self.lblActivitySticker.setText(f"Sticker Label: {self._safe_text(job_details.get('sticker_label'), '-')}")

        self.lblPack.setText(str(s.pack_count))
        self.lblGood.setText(str(s.good_total))
        self.lblButal.setText(str(s.butal_total))
        self.lblReject.setText(str(s.reject_total))
        self.lblTotalGood.setText(str(s.good_total + s.butal_total))
        self.rightCycleCount.setText(f"Confirmed by: {s.cycle_time_confirmed_by or '-'}")
        self.rightCycleCurrent.setText(f"Cycle Time: {s.cycle_time_current or ''}")
        if hasattr(self, "topCycleCount") and self.topCycleCount is not None:
            self.topCycleCount.setText(f"Confirmed by: {s.cycle_time_confirmed_by or '-'}")
        if hasattr(self, "topCycleCurrent") and self.topCycleCurrent is not None:
            self.topCycleCurrent.setText(f"Cycle Time: {s.cycle_time_current or ''}")

        self._refresh_reject_detail_grid()

        # banner message depending on workflow
        if not s.machine_code:
            self._set_banner_text("Scan MACHINE QR to start")
        elif not s.job_code:
            self._set_banner_text("Scan JOB QR")
        elif not s.operator_id:
            self._set_banner_text("Scan OPERATOR badge")
        elif s.showing_reject_summary:
            self._set_banner_text("Reject summary loaded")
        elif s.waiting_reject_reason:
            self._set_banner_text("Reject mode: Scan reason (BM01/CS02/CO03/CR04/DI05) or SUR")
        elif s.waiting_production_report_reason:
            self._set_banner_text("Production Daily Report mode: Scan reason QR (01-15)")
        elif s.waiting_initial_cycle_time_input:
            self._set_banner_text("Initial setup: Scan cycle time digits, then confirm")
        elif s.waiting_cycle_time_confirm_popup:
            self._set_banner_text("Cycle time confirmation: Scan same Supervisor badge again")
        elif s.waiting_initial_cycle_qc_confirm:
            self._set_banner_text("Initial setup: Scan QC badge to confirm cycle time")
        elif s.waiting_cycle_time_input:
            self._set_banner_text("Downtime resolve: Scan cycle time digits, then confirm")
        elif s.waiting_maintenance_qr:
            self._set_banner_text("Downtime resolve: Scan Maintenance QR")
        elif s.waiting_supervisor_qr:
            self._set_banner_text("Downtime resolve: Scan Supervisor QR")
        elif s.waiting_operator_downtime_confirm:
            self._set_banner_text("Downtime resolve: Scan Operator QR to confirm")
        elif s.downtime_active:
            self._set_banner_text('Downtime active: scan "productiondailyreport~2" or SUR')
        else:
            self._set_banner_text("Ready: Scan PACK / BUTAL / Reject~1")
        self._refresh_job_details()
        self._refresh_downtime_panel()
        self._refresh_linkage_panel()

    def _session_is_running(self) -> bool:
        s = self.state
        return bool(
            s.machine_code
            and s.job_code
            and s.operator_id
            and not s.waiting_reject_reason
            and not s.downtime_active
        )

    def _tick_motion(self):
        is_active = self._session_is_running() or bool(self.state.machine_code)
        status_text = "ACTIVE" if is_active else "IDLE"
        self.machineAnim.setText(f"Machine Status: {status_text}")
        mode = "active" if is_active else "idle"
        if self.machineAnim.property("mode") != mode:
            self.machineAnim.setProperty("mode", mode)
            self.machineAnim.setProperty("pulse", "0")
            self.machineAnim.setStyleSheet("")
            self.machineAnim.style().unpolish(self.machineAnim)
            self.machineAnim.style().polish(self.machineAnim)
        self._sync_machine_status_pulse_overlay()
        self.machinePulseOverlay.set_mode(is_active)
        self.machinePulseOverlay.advance(self.enable_pulse_effects, dt=0.06)

    def _refresh_downtime_panel(self):
        s = self.state
        self.rightRawSacks.setText(f"Sacks Count: {s.raw_sacks_count}")
        raw_logs = [x for x in (s.raw_material_logs or []) if isinstance(x, dict)]
        if raw_logs:
            recent_names = [str(x.get("material_name") or x.get("material") or "-").strip() or "-" for x in raw_logs[-4:]]
            self.rightRawScanned.setText(f"Raw Mats Scanned: {', '.join(recent_names)}")
        else:
            self.rightRawScanned.setText("Raw Mats Scanned: -")

        if s.downtime_reason_code and s.downtime_reason_text:
            self.rightDowntimeReason.setText(f"Reason {s.downtime_reason_code}: {s.downtime_reason_text}")
        else:
            self.rightDowntimeReason.setText("Reason: -")
        self.rightStartupReject.setText(f"Start Up Reject: {s.startup_reject_total}")
        self.rightMaintenance.setText(f"Maintenance: {s.maintenance_name or '-'}")
        self.rightSupervisor.setText(f"Supervisor: {s.supervisor_name or '-'}")
        self.rightSupervisorLeft.setText(f"Supervisor: {s.supervisor_name or '-'}")

        if s.downtime_started_at:
            elapsed = max(0, int(time.time() - s.downtime_started_at))
            hh = elapsed // 3600
            mm = (elapsed % 3600) // 60
            ss = elapsed % 60
            self.rightDowntimeTimer.setText(f"Downtime: {hh:02d}:{mm:02d}:{ss:02d}")
            if self._overlay_mode == "active":
                self.productionLiveReason.setText(self.rightDowntimeReason.text())
                self.productionCounter.setText(f"{hh:02d}:{mm:02d}:{ss:02d}")
        else:
            if s.downtime_last_seconds is not None:
                hh = s.downtime_last_seconds // 3600
                mm = (s.downtime_last_seconds % 3600) // 60
                ss = s.downtime_last_seconds % 60
                self.rightDowntimeTimer.setText(f"Downtime: {hh:02d}:{mm:02d}:{ss:02d}")
            else:
                self.rightDowntimeTimer.setText("Downtime: 00:00:00")
            if self._overlay_mode == "active":
                self.productionCounter.setText("00:00:00")
                if self._repair_movie is None:
                    self.productionFixAnim.setText("Repair in progress...")

    def _refresh_linkage_panel(self):
        s = self.state
        if getattr(self, "linkageMirrorOuter", None) is None:
            return
        if s.waiting_linkage_job_scan:
            self.linkageMirrorHint.setText("Linkage mode active: scan another JOB QR to mirror current session.")
        elif s.linkage_enabled:
            self.linkageMirrorHint.setText("Mirroring current session counters/reject details to linked job.")
        else:
            self.linkageMirrorHint.setText('Scan "joblinkage~1" then scan another JOB QR.')

        linked_rows = list(s.linkage_jobs or [])
        if linked_rows:
            linked_name = ", ".join(
                [str(r.get("job_name") or r.get("job_code") or "-") for r in linked_rows[:2]]
            )
            if len(linked_rows) > 2:
                linked_name += f" (+{len(linked_rows) - 2})"
        else:
            linked_name = s.linkage_job_name or s.linkage_job_code or "-"
        self.linkageMirrorJob.setText(f"Linked Job(s): {linked_name}")
        self.linkageMirrorCounts.setText(
            f"Pack: {s.pack_count} | Good: {s.good_total} | Total Good (Pack Only): {s.good_total}"
        )
        self.linkageMirrorRejects.setText("Reject/Butal: main job only (linked job mirrors Pack/Good only)")
        self.linkageMirrorOuter.setVisible(bool(s.machine_code))

    def _save_finished_job_local(self, payload: Dict[str, Any]):
        return _insert_finished_job_sql(payload)

    def _start_operator_shift_tracking(self):
        s = self.state
        if not (s.machine_code and s.job_code and s.operator_id):
            return
        s.operator_shift_index = int(s.operator_shift_index or 0) + 1
        s.operator_shift_started_at = datetime.now(timezone.utc).isoformat()
        s.operator_shift_baseline_pack_count = int(s.pack_count or 0)
        s.operator_shift_baseline_good_total = int(s.good_total or 0)
        s.operator_shift_baseline_butal_total = int(s.butal_total or 0)
        s.operator_shift_baseline_reject_total = int(s.reject_total or 0)
        s.operator_shift_baseline_startup_reject_total = int(s.startup_reject_total or 0)
        s.operator_shift_baseline_raw_sacks_count = int(s.raw_sacks_count or 0)
        s.operator_shift_baseline_reject_breakdown = dict(s.reject_breakdown or {})
        s.operator_shift_baseline_raw_material_logs_len = len(s.raw_material_logs or [])
        s.operator_shift_baseline_product_pack_history_logs_len = len(s.product_pack_history_logs or [])
        s.operator_shift_baseline_reject_review_logs_len = len(s.reject_review_logs or [])

    def _build_operator_shift_payload(self, reason: str) -> Optional[Dict[str, Any]]:
        s = self.state
        if not (s.machine_code and s.job_code and s.operator_id):
            return None
        ended_at_utc = datetime.now(timezone.utc).isoformat()
        started_at_utc = s.operator_shift_started_at or ended_at_utc
        base_rejects = dict(s.operator_shift_baseline_reject_breakdown or {})
        now_rejects = dict(s.reject_breakdown or {})
        reject_delta: Dict[str, int] = {}
        for key in sorted(set(base_rejects.keys()) | set(now_rejects.keys())):
            try:
                delta = int(now_rejects.get(key, 0) or 0) - int(base_rejects.get(key, 0) or 0)
            except Exception:
                delta = 0
            if delta > 0:
                reject_delta[str(key)] = delta
        raw_from = max(0, int(s.operator_shift_baseline_raw_material_logs_len or 0))
        pack_from = max(0, int(s.operator_shift_baseline_product_pack_history_logs_len or 0))
        review_from = max(0, int(s.operator_shift_baseline_reject_review_logs_len or 0))
        pack_count = max(0, int(s.pack_count or 0) - int(s.operator_shift_baseline_pack_count or 0))
        good_total = max(0, int(s.good_total or 0) - int(s.operator_shift_baseline_good_total or 0))
        butal_total = max(0, int(s.butal_total or 0) - int(s.operator_shift_baseline_butal_total or 0))
        reject_total = max(0, int(s.reject_total or 0) - int(s.operator_shift_baseline_reject_total or 0))
        startup_reject_total = max(0, int(s.startup_reject_total or 0) - int(s.operator_shift_baseline_startup_reject_total or 0))
        raw_sacks_count = max(0, int(s.raw_sacks_count or 0) - int(s.operator_shift_baseline_raw_sacks_count or 0))
        return {
            "shift_index": int(s.operator_shift_index or (len(s.operator_shift_logs or []) + 1)),
            "reason": str(reason or "SHIFT_CHANGE"),
            "started_at_utc": started_at_utc,
            "ended_at_utc": ended_at_utc,
            "machine_code": s.machine_code,
            "machine_name": _machine_display_name(s.machine_code, s.machine_name),
            "job_code": s.job_code,
            "job_name": s.job_name,
            "operator_id": s.operator_id,
            "operator_name": self._operator_display_name(s.operator_id),
            "pack_count": pack_count,
            "good_total": good_total,
            "butal_total": butal_total,
            "reject_total": reject_total,
            "total_good": int(good_total + butal_total),
            "reject_breakdown": reject_delta,
            "startup_reject_total": startup_reject_total,
            "raw_sacks_count": raw_sacks_count,
            "raw_material_logs": list((s.raw_material_logs or [])[raw_from:]),
            "product_pack_history_logs": list((s.product_pack_history_logs or [])[pack_from:]),
            "reject_review_logs": list((s.reject_review_logs or [])[review_from:]),
            "downtime_active": bool(s.downtime_active),
            "downtime_reason_code": s.downtime_reason_code,
            "downtime_reason_text": s.downtime_reason_text,
            "downtime_last_seconds": s.downtime_last_seconds,
            "cycle_time_current": s.cycle_time_current,
            "maintenance_name": s.maintenance_name,
            "supervisor_name": s.supervisor_name,
        }

    def _finalize_current_operator_shift(self, reason: str, emit_event: bool = True) -> Optional[Dict[str, Any]]:
        payload = self._build_operator_shift_payload(reason=reason)
        if payload is None:
            return None
        s = self.state
        rows = list(s.operator_shift_logs or [])
        rows.append(payload)
        s.operator_shift_logs = rows
        if emit_event:
            self.push_event(
                {"type": "OPERATOR_SHIFT_SAVE", "operator_shift": payload},
                f"OPERATOR SHIFT SAVE {payload.get('operator_name') or payload.get('operator_id') or ''}".strip(),
            )
        return payload

    def _state_to_active_snapshot(self) -> Dict[str, Any]:
        s = self.state
        return {
            "saved_at_utc": datetime.now(timezone.utc).isoformat(),
            "machine_code": s.machine_code,
            "machine_name": s.machine_name,
            "job_code": s.job_code,
            "job_name": s.job_name,
            "operator_id": s.operator_id,
            "pack_count": int(s.pack_count or 0),
            "good_total": int(s.good_total or 0),
            "butal_total": int(s.butal_total or 0),
            "reject_total": int(s.reject_total or 0),
            "reject_breakdown": dict(s.reject_breakdown or {}),
            "waiting_reject_reason": bool(s.waiting_reject_reason),
            "waiting_production_report_reason": bool(s.waiting_production_report_reason),
            "showing_reject_summary": bool(s.showing_reject_summary),
            "reject_summary_last_scanned_at": s.reject_summary_last_scanned_at,
            "job_payload": s.job_payload or {},
            "downtime_reason_code": s.downtime_reason_code,
            "downtime_reason_text": s.downtime_reason_text,
            "downtime_started_at": s.downtime_started_at,
            "downtime_last_seconds": s.downtime_last_seconds,
            "downtime_active": bool(s.downtime_active),
            "cycle_time_current": s.cycle_time_current,
            "cycle_time_new_input": s.cycle_time_new_input,
            "waiting_cycle_time_input": bool(s.waiting_cycle_time_input),
            "waiting_initial_cycle_time_input": bool(s.waiting_initial_cycle_time_input),
            "waiting_initial_cycle_qc_confirm": bool(s.waiting_initial_cycle_qc_confirm),
            "waiting_cycle_time_confirm_popup": bool(s.waiting_cycle_time_confirm_popup),
            "cycle_time_confirm_phase": int(s.cycle_time_confirm_phase or 0),
            "cycle_time_confirmed_by": s.cycle_time_confirmed_by,
            "cycle_time_confirm_actor_code": s.cycle_time_confirm_actor_code,
            "cycle_time_confirm_actor_name": s.cycle_time_confirm_actor_name,
            "cycle_time_confirm_actor_role": s.cycle_time_confirm_actor_role,
            "waiting_maintenance_qr": bool(s.waiting_maintenance_qr),
            "waiting_supervisor_qr": bool(s.waiting_supervisor_qr),
            "waiting_operator_downtime_confirm": bool(s.waiting_operator_downtime_confirm),
            "maintenance_name": s.maintenance_name,
            "supervisor_name": s.supervisor_name,
            "raw_sacks_count": int(s.raw_sacks_count or 0),
            "raw_material_scans": list(s.raw_material_scans or []),
            "raw_material_logs": list(s.raw_material_logs or []),
            "raw_material_unique_keys": sorted(list(s.raw_material_unique_keys or set())),
            "product_pack_history_logs": list(s.product_pack_history_logs or []),
            "startup_reject_total": int(s.startup_reject_total or 0),
            "reject_review_open": bool(s.reject_review_open),
            "reject_review_phase": int(s.reject_review_phase or 0),
            "reject_review_actor_code": s.reject_review_actor_code,
            "reject_review_actor_name": s.reject_review_actor_name,
            "reject_review_actor_role": s.reject_review_actor_role,
            "reject_review_logs": list(s.reject_review_logs or []),
            "waiting_linkage_job_scan": bool(s.waiting_linkage_job_scan),
            "linkage_enabled": bool(s.linkage_enabled),
            "linkage_job_code": s.linkage_job_code,
            "linkage_job_name": s.linkage_job_name,
            "linkage_job_payload": dict(s.linkage_job_payload or {}),
            "linkage_jobs": list(s.linkage_jobs or []),
            "operator_shift_logs": list(s.operator_shift_logs or []),
            "operator_shift_index": int(s.operator_shift_index or 0),
            "operator_shift_started_at": s.operator_shift_started_at,
            "operator_shift_baseline_pack_count": int(s.operator_shift_baseline_pack_count or 0),
            "operator_shift_baseline_good_total": int(s.operator_shift_baseline_good_total or 0),
            "operator_shift_baseline_butal_total": int(s.operator_shift_baseline_butal_total or 0),
            "operator_shift_baseline_reject_total": int(s.operator_shift_baseline_reject_total or 0),
            "operator_shift_baseline_startup_reject_total": int(s.operator_shift_baseline_startup_reject_total or 0),
            "operator_shift_baseline_raw_sacks_count": int(s.operator_shift_baseline_raw_sacks_count or 0),
            "operator_shift_baseline_reject_breakdown": dict(s.operator_shift_baseline_reject_breakdown or {}),
            "operator_shift_baseline_raw_material_logs_len": int(s.operator_shift_baseline_raw_material_logs_len or 0),
            "operator_shift_baseline_product_pack_history_logs_len": int(s.operator_shift_baseline_product_pack_history_logs_len or 0),
            "operator_shift_baseline_reject_review_logs_len": int(s.operator_shift_baseline_reject_review_logs_len or 0),
        }

    def _save_active_session_snapshot(self):
        s = self.state
        machine_code = str(s.machine_code or "").strip()
        if not machine_code:
            return
        _upsert_active_session_sql(self._state_to_active_snapshot())

    def _load_active_session_snapshot(self, machine_code: str) -> Optional[Dict[str, Any]]:
        rows = _load_active_sessions_sql()
        snap = rows.get(str(machine_code or "").strip())
        if isinstance(snap, dict):
            return snap
        return None

    def _clear_active_session_snapshot(self, machine_code: Optional[str]):
        code = str(machine_code or "").strip()
        if not code:
            return
        _delete_active_session_sql(code)

    def _restore_state_from_snapshot(self, snap: Dict[str, Any]):
        s = self.state
        s.machine_code = snap.get("machine_code")
        s.machine_name = _machine_display_name(snap.get("machine_code"), snap.get("machine_name"))
        s.job_code = snap.get("job_code")
        s.job_name = snap.get("job_name")
        s.operator_id = snap.get("operator_id")
        s.pack_count = int(snap.get("pack_count") or 0)
        s.good_total = int(snap.get("good_total") or 0)
        s.butal_total = int(snap.get("butal_total") or 0)
        s.reject_total = int(snap.get("reject_total") or 0)
        s.reject_breakdown = dict(snap.get("reject_breakdown") or {})
        s.waiting_reject_reason = bool(snap.get("waiting_reject_reason"))
        s.waiting_production_report_reason = bool(snap.get("waiting_production_report_reason"))
        s.showing_reject_summary = bool(snap.get("showing_reject_summary"))
        s.reject_summary_last_scanned_at = snap.get("reject_summary_last_scanned_at")
        s.job_payload = snap.get("job_payload") or {}
        s.downtime_reason_code = snap.get("downtime_reason_code")
        s.downtime_reason_text = snap.get("downtime_reason_text")
        s.downtime_started_at = snap.get("downtime_started_at")
        s.downtime_last_seconds = snap.get("downtime_last_seconds")
        s.downtime_active = bool(snap.get("downtime_active"))
        s.cycle_time_current = snap.get("cycle_time_current")
        s.cycle_time_new_input = str(snap.get("cycle_time_new_input") or "")
        s.waiting_cycle_time_input = bool(snap.get("waiting_cycle_time_input"))
        s.waiting_initial_cycle_time_input = bool(snap.get("waiting_initial_cycle_time_input"))
        s.waiting_initial_cycle_qc_confirm = bool(snap.get("waiting_initial_cycle_qc_confirm"))
        s.waiting_cycle_time_confirm_popup = bool(snap.get("waiting_cycle_time_confirm_popup"))
        s.cycle_time_confirm_phase = int(snap.get("cycle_time_confirm_phase") or 0)
        s.cycle_time_confirmed_by = snap.get("cycle_time_confirmed_by")
        s.cycle_time_confirm_actor_code = snap.get("cycle_time_confirm_actor_code")
        s.cycle_time_confirm_actor_name = snap.get("cycle_time_confirm_actor_name")
        s.cycle_time_confirm_actor_role = snap.get("cycle_time_confirm_actor_role")
        s.waiting_maintenance_qr = bool(snap.get("waiting_maintenance_qr"))
        s.waiting_supervisor_qr = bool(snap.get("waiting_supervisor_qr"))
        s.waiting_operator_downtime_confirm = bool(snap.get("waiting_operator_downtime_confirm"))
        s.maintenance_name = snap.get("maintenance_name")
        s.supervisor_name = snap.get("supervisor_name")
        s.raw_sacks_count = int(snap.get("raw_sacks_count") or 0)
        s.raw_material_scans = list(snap.get("raw_material_scans") or [])
        s.raw_material_logs = list(snap.get("raw_material_logs") or [])
        s.raw_material_unique_keys = set(snap.get("raw_material_unique_keys") or [])
        s.product_pack_history_logs = list(snap.get("product_pack_history_logs") or [])
        s.startup_reject_total = int(snap.get("startup_reject_total") or 0)
        s.reject_review_open = bool(snap.get("reject_review_open"))
        s.reject_review_phase = int(snap.get("reject_review_phase") or 0)
        s.reject_review_actor_code = snap.get("reject_review_actor_code")
        s.reject_review_actor_name = snap.get("reject_review_actor_name")
        s.reject_review_actor_role = snap.get("reject_review_actor_role")
        s.reject_review_logs = list(snap.get("reject_review_logs") or [])
        s.waiting_linkage_job_scan = bool(snap.get("waiting_linkage_job_scan"))
        s.linkage_enabled = bool(snap.get("linkage_enabled"))
        s.linkage_job_code = snap.get("linkage_job_code")
        s.linkage_job_name = snap.get("linkage_job_name")
        s.linkage_job_payload = dict(snap.get("linkage_job_payload") or {})
        s.linkage_jobs = list(snap.get("linkage_jobs") or [])
        s.operator_shift_logs = list(snap.get("operator_shift_logs") or [])
        s.operator_shift_index = int(snap.get("operator_shift_index") or 0)
        s.operator_shift_started_at = snap.get("operator_shift_started_at")
        s.operator_shift_baseline_pack_count = int(snap.get("operator_shift_baseline_pack_count") or 0)
        s.operator_shift_baseline_good_total = int(snap.get("operator_shift_baseline_good_total") or 0)
        s.operator_shift_baseline_butal_total = int(snap.get("operator_shift_baseline_butal_total") or 0)
        s.operator_shift_baseline_reject_total = int(snap.get("operator_shift_baseline_reject_total") or 0)
        s.operator_shift_baseline_startup_reject_total = int(snap.get("operator_shift_baseline_startup_reject_total") or 0)
        s.operator_shift_baseline_raw_sacks_count = int(snap.get("operator_shift_baseline_raw_sacks_count") or 0)
        s.operator_shift_baseline_reject_breakdown = dict(snap.get("operator_shift_baseline_reject_breakdown") or {})
        s.operator_shift_baseline_raw_material_logs_len = int(snap.get("operator_shift_baseline_raw_material_logs_len") or 0)
        s.operator_shift_baseline_product_pack_history_logs_len = int(snap.get("operator_shift_baseline_product_pack_history_logs_len") or 0)
        s.operator_shift_baseline_reject_review_logs_len = int(snap.get("operator_shift_baseline_reject_review_logs_len") or 0)
        if s.operator_id and not s.operator_shift_started_at:
            self._start_operator_shift_tracking()
        self._refresh_ui()
        # Re-open pending overlays after reconnect/resume so the user can continue the interrupted step.
        if s.waiting_initial_cycle_time_input:
            std_cycle = "-"
            try:
                payload = s.job_payload or {}
                data = payload.get("data") if isinstance(payload, dict) else {}
                job_details = data.get("job_details") if isinstance(data, dict) else {}
                if isinstance(job_details, dict):
                    std_cycle = self._safe_text(job_details.get("std_cycle_time"), "-")
            except Exception:
                pass
            self.resolveTitle.setText("INITIAL CYCLE TIME SETUP")
            self.resolveHint.setText("Scan cycle time digits (num_0..num_9), backspace, then confirm")
            self.resolveOldCycleTitle.setText("JOB STD CYCLE TIME")
            self.resolveNewCycleTitle.setText("CYCLE TIME INPUT")
            self.resolveOldCycle.setText(f"Job Std Cycle Time: {std_cycle}")
            self.resolveNewCycle.setText(f"Cycle Time: {s.cycle_time_new_input}")
            self._show_resolve_overlay()
        elif s.waiting_cycle_time_confirm_popup:
            self.resolveTitle.setText("SUPERVISOR CYCLE TIME REVIEW")
            if int(s.cycle_time_confirm_phase or 0) == 2:
                self.resolveHint.setText("Cycle time updated. Reject summary is open. Scan the same Supervisor badge again to confirm all.")
                self.resolveOldCycleTitle.setText("STD CYCLE TIME")
                self.resolveNewCycleTitle.setText("CURRENT CYCLE TIME")
                self.resolveNewCycle.setText(f"Cycle Time: {s.cycle_time_current or '-'}")
            else:
                self.resolveHint.setText(
                    f"Current Cycle Time: {s.cycle_time_current or '-'}\n"
                    "Scan num_0..num_9, backspace, then confirm to update."
                )
                self.resolveOldCycleTitle.setText("STD CYCLE TIME")
                self.resolveNewCycleTitle.setText("NEW CYCLE TIME INPUT")
                self.resolveNewCycle.setText(f"Cycle Time: {s.cycle_time_new_input}")
            self.resolveOldCycleTitle.setText("STD CYCLE TIME")
            self._show_resolve_overlay()

    def _build_finished_job_payload(self) -> Dict[str, Any]:
        s = self.state
        return {
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "client_id": CLIENT_ID,
            "machine_code": s.machine_code,
            "machine_name": _machine_display_name(s.machine_code, s.machine_name),
            "job_code": s.job_code,
            "job_name": s.job_name,
            "operator_id": s.operator_id,
            "pack_count": int(s.pack_count or 0),
            "good_total": int(s.good_total or 0),
            "butal_total": int(s.butal_total or 0),
            "reject_total": int(s.reject_total or 0),
            "total_good": int((s.good_total or 0) + (s.butal_total or 0)),
            "reject_breakdown": dict(s.reject_breakdown or {}),
            "startup_reject_total": int(s.startup_reject_total or 0),
            "raw_sacks_count": int(s.raw_sacks_count or 0),
            "raw_material_scans": list(s.raw_material_scans or []),
            "raw_material_logs": list(s.raw_material_logs or []),
            "product_pack_history_logs": list(s.product_pack_history_logs or []),
            "job_payload": s.job_payload or {},
            "reject_review_logs": list(s.reject_review_logs or []),
            "downtime_last_seconds": s.downtime_last_seconds,
            "downtime_reason_code": s.downtime_reason_code,
            "downtime_reason_text": s.downtime_reason_text,
            "cycle_time_current": s.cycle_time_current,
            "maintenance_name": s.maintenance_name,
            "supervisor_name": s.supervisor_name,
            "operator_shift_logs": list(s.operator_shift_logs or []),
            "linkage_enabled": bool(s.linkage_enabled),
            "linkage_job_code": s.linkage_job_code,
            "linkage_job_name": s.linkage_job_name,
            "linkage_job_payload": s.linkage_job_payload or {},
            "linkage_jobs": list(s.linkage_jobs or []),
            "linkage_mirror": {
                "pack_count": int(s.pack_count or 0),
                "good_total": int(s.good_total or 0),
                "butal_total": int(s.butal_total or 0),
                "total_good": int((s.good_total or 0) + (s.butal_total or 0)),
            } if s.linkage_enabled else None,
        }

    def _build_linked_finished_job_payloads(self, main_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        s = self.state
        linked_rows = list(s.linkage_jobs or [])
        if not linked_rows:
            return []
        total_jobs_in_group = 1 + len(linked_rows)
        out: List[Dict[str, Any]] = []
        for idx, row in enumerate(linked_rows, start=2):
            linked_payload = dict(main_payload)
            linked_payload["job_code"] = row.get("job_code") or linked_payload.get("job_code")
            linked_payload["job_name"] = row.get("job_name") or linked_payload.get("job_name")
            linked_payload["job_payload"] = dict(row.get("job_payload") or {})
            # Linked jobs mirror only finish-goods counters, not rejects.
            linked_payload["pack_count"] = int(s.pack_count or 0)
            linked_payload["good_total"] = int(s.good_total or 0)
            linked_payload["butal_total"] = 0
            linked_payload["reject_total"] = 0
            linked_payload["reject_breakdown"] = {}
            linked_payload["total_good"] = int(s.good_total or 0)
            linked_payload["startup_reject_total"] = 0
            linked_payload["linkage_enabled"] = True
            linked_payload["linkage_role"] = "LINKED"
            linked_payload["linkage_group_total_jobs"] = total_jobs_in_group
            linked_payload["linkage_main_job_code"] = main_payload.get("job_code")
            linked_payload["linkage_main_job_name"] = main_payload.get("job_name")
            linked_payload["linkage_note"] = (
                f"Linked job {idx} of {total_jobs_in_group}. "
                f"Main job is {main_payload.get('job_name') or main_payload.get('job_code') or '-'} (1 of {total_jobs_in_group})."
            )
            out.append(linked_payload)
        return out

    def _clear_full_session(self):
        s = self.state
        active_machine_code = s.machine_code
        s.machine_code = None
        s.machine_name = None
        s.job_code = None
        s.job_name = None
        s.operator_id = None
        s.pack_count = 0
        s.good_total = 0
        s.butal_total = 0
        s.reject_total = 0
        s.reject_breakdown = {}
        s.waiting_reject_reason = False
        s.waiting_production_report_reason = False
        s.showing_reject_summary = False
        s.reject_summary_last_scanned_at = None
        s.job_payload = {}
        s.downtime_reason_code = None
        s.downtime_reason_text = None
        s.downtime_started_at = None
        s.downtime_last_seconds = None
        s.downtime_active = False
        s.cycle_time_current = None
        s.cycle_time_confirmed_by = None
        s.waiting_initial_cycle_time_input = False
        s.waiting_initial_cycle_qc_confirm = False
        s.waiting_cycle_time_confirm_popup = False
        s.cycle_time_confirm_phase = 0
        s.cycle_time_confirm_actor_code = None
        s.cycle_time_confirm_actor_name = None
        s.cycle_time_confirm_actor_role = None
        s.maintenance_name = None
        s.supervisor_name = None
        s.raw_sacks_count = 0
        s.raw_material_scans = []
        s.raw_material_logs = []
        s.raw_material_unique_keys = set()
        s.product_pack_history_logs = []
        s.startup_reject_total = 0
        s.reject_review_logs = []
        s.waiting_linkage_job_scan = False
        s.linkage_enabled = False
        s.linkage_job_code = None
        s.linkage_job_name = None
        s.linkage_job_payload = {}
        s.linkage_jobs = []
        s.operator_shift_logs = []
        s.operator_shift_index = 0
        s.operator_shift_started_at = None
        s.operator_shift_baseline_pack_count = 0
        s.operator_shift_baseline_good_total = 0
        s.operator_shift_baseline_butal_total = 0
        s.operator_shift_baseline_reject_total = 0
        s.operator_shift_baseline_startup_reject_total = 0
        s.operator_shift_baseline_raw_sacks_count = 0
        s.operator_shift_baseline_reject_breakdown = {}
        s.operator_shift_baseline_raw_material_logs_len = 0
        s.operator_shift_baseline_product_pack_history_logs_len = 0
        s.operator_shift_baseline_reject_review_logs_len = 0
        self._reset_downtime_resolution_state()
        self._hide_resolve_overlay()
        self._hide_production_overlay()
        self._hide_raw_mats_overlay()
        self._hide_reject_summary_overlay()
        self._hide_product_history_overlay()
        self._hide_reject_review_overlay()
        self._clear_active_session_snapshot(active_machine_code)
        self._refresh_ui()
        self.rightCycleCount.setText(f"Confirmed by: {s.cycle_time_confirmed_by or '-'}")
        self.rightCycleCurrent.setText(f"Cycle Time: {s.cycle_time_current or ''}")
        if hasattr(self, "topCycleCount") and self.topCycleCount is not None:
            self.topCycleCount.setText(f"Confirmed by: {s.cycle_time_confirmed_by or '-'}")
        if hasattr(self, "topCycleCurrent") and self.topCycleCurrent is not None:
            self.topCycleCurrent.setText(f"Cycle Time: {s.cycle_time_current or ''}")
        self.rightMaintenance.setText(f"Maintenance: {s.maintenance_name or ''}")
        self.rightSupervisor.setText(f"Supervisor: {s.supervisor_name or ''}")

    def _extract_production_reason_code(self, raw: str) -> Optional[str]:
        m = re.search(r"(\d+)", str(raw).strip())
        if not m:
            return None
        try:
            idx = int(m.group(1))
        except Exception:
            return None
        if idx < 1 or idx > len(PRODUCTION_DAILY_REPORT_ITEMS):
            return None
        return f"{idx:02d}"

    def _operator_code_only(self, operator_text: Optional[str]) -> str:
        if not operator_text:
            return ""
        return str(operator_text).split(" - ", 1)[0].strip()

    def _reset_downtime_resolution_state(self):
        s = self.state
        s.waiting_cycle_time_input = False
        s.waiting_maintenance_qr = False
        s.waiting_supervisor_qr = False
        s.waiting_operator_downtime_confirm = False
        s.cycle_time_new_input = ""

    def _begin_initial_cycle_time_setup(self):
        s = self.state
        s.waiting_initial_cycle_time_input = True
        s.waiting_initial_cycle_qc_confirm = False
        s.cycle_time_new_input = ""
        s.cycle_time_confirmed_by = None
        self._hide_production_overlay()
        self.resolveTitle.setText("INITIAL CYCLE TIME SETUP")
        self.resolveHint.setText("Scan cycle time digits (num_0..num_9), backspace, then confirm")
        self.resolveOldCycleTitle.setText("JOB STD CYCLE TIME")
        self.resolveNewCycleTitle.setText("CYCLE TIME INPUT")
        std_cycle = "-"
        try:
            payload = s.job_payload or {}
            data = payload.get("data") if isinstance(payload, dict) else {}
            job_details = data.get("job_details") if isinstance(data, dict) else {}
            if isinstance(job_details, dict):
                std_cycle = self._safe_text(job_details.get("std_cycle_time"), "-")
        except Exception:
            std_cycle = "-"
        self.resolveOldCycle.setText(f"Job Std Cycle Time: {std_cycle}")
        self.resolveNewCycle.setText("Cycle Time: ")
        self._show_resolve_overlay()

    def _show_cycle_time_confirm_popup(self, reviewer: Dict[str, str]):
        s = self.state
        s.waiting_cycle_time_confirm_popup = True
        s.cycle_time_confirm_phase = 1
        s.cycle_time_confirm_actor_code = reviewer.get("code")
        s.cycle_time_confirm_actor_name = reviewer.get("name")
        s.cycle_time_confirm_actor_role = reviewer.get("role")
        s.cycle_time_new_input = str(s.cycle_time_current or "")
        std_cycle = "-"
        try:
            payload = s.job_payload or {}
            data = payload.get("data") if isinstance(payload, dict) else {}
            job_details = data.get("job_details") if isinstance(data, dict) else {}
            if isinstance(job_details, dict):
                std_cycle = self._safe_text(job_details.get("std_cycle_time"), "-")
        except Exception:
            pass
        self.resolveTitle.setText("SUPERVISOR CYCLE TIME REVIEW")
        self.resolveHint.setText(
            f"Current Cycle Time: {s.cycle_time_current or '-'}\n"
            "Scan num_0..num_9, backspace, then confirm to update."
        )
        self.resolveOldCycleTitle.setText("STD CYCLE TIME")
        self.resolveNewCycleTitle.setText("NEW CYCLE TIME INPUT")
        self.resolveOldCycle.setText(f"Std Cycle Time: {std_cycle}")
        self.resolveNewCycle.setText(f"Cycle Time: {s.cycle_time_new_input or ''}")
        self._show_resolve_overlay()

    def _hide_cycle_time_confirm_popup(self):
        s = self.state
        s.waiting_cycle_time_confirm_popup = False
        s.cycle_time_confirm_phase = 0
        s.cycle_time_confirm_actor_code = None
        s.cycle_time_confirm_actor_name = None
        s.cycle_time_confirm_actor_role = None
        self._hide_resolve_overlay()

    def _begin_downtime_resolution(self):
        s = self.state
        self._reset_downtime_resolution_state()
        s.waiting_cycle_time_input = True
        s.cycle_time_new_input = ""
        self._hide_production_overlay()
        self.resolveTitle.setText("DOWNTIME RESOLUTION")
        self.resolveHint.setText("Scan cycle time digits (num_0..num_9), backspace, then confirm")
        self.resolveOldCycleTitle.setText("OLD CYCLE TIME")
        self.resolveNewCycleTitle.setText("CYCLE TIME INPUT")
        self.resolveOldCycle.setText(f"Old Cycle Time: {s.cycle_time_current or '-'}")
        self.resolveNewCycle.setText("Cycle Time: ")
        self._show_resolve_overlay()

    def _update_cycle_input_display(self):
        self.resolveNewCycle.setText(f"Cycle Time: {self.state.cycle_time_new_input}")

    def _refresh_reject_detail_grid(self):
        counts = self._normalized_reject_counts()
        for code, label in REJECT_DETAIL_ITEMS:
            total = int(counts.get(code, 0))
            item = self.reject_detail_labels[code]
            item.setText(str(total))
            is_active = total > 0
            item.setData(Qt.ItemDataRole.UserRole, 1 if is_active else 0)
            item.setData(Qt.ItemDataRole.UserRole + 1, 0)
            if is_active:
                item.setBackground(QColor(254, 226, 226, 90))
                item.setForeground(QColor("#991b1b"))
            else:
                item.setBackground(QColor(0, 0, 0, 0))
                item.setForeground(QColor("#0f172a"))
        self.rejectDetailTable.viewport().update()

    def _tick_reject_detail_flash(self):
        if not self.enable_flashing_lights:
            return
        self._reject_detail_flash_on = not self._reject_detail_flash_on
        for item in self.reject_detail_labels.values():
            if int(item.data(Qt.ItemDataRole.UserRole) or 0) == 1:
                if self._reject_detail_flash_on:
                    item.setBackground(QColor(252, 165, 165, 130))
                else:
                    item.setBackground(QColor(254, 226, 226, 90))
        self.rejectDetailTable.viewport().update()

    def _on_setting_check_animation_toggled(self, checked: bool):
        self.enable_check_animation = bool(checked)
        self._set_toggle_button_text(self.chkCheckAnimation, "Check animation", self.enable_check_animation)

    def _on_setting_flashing_lights_toggled(self, checked: bool):
        self.enable_flashing_lights = bool(checked)
        self._set_toggle_button_text(self.chkFlashingLights, "Flashing lights", self.enable_flashing_lights)
        if not self.enable_flashing_lights:
            for item in self.reject_detail_labels.values():
                if int(item.data(Qt.ItemDataRole.UserRole) or 0) == 1:
                    item.setBackground(QColor(254, 226, 226, 90))
                else:
                    item.setBackground(QColor(0, 0, 0, 0))
            self.rejectDetailTable.viewport().update()

    def _on_setting_pulse_effects_toggled(self, checked: bool):
        self.enable_pulse_effects = bool(checked)
        self._set_toggle_button_text(self.chkPulseEffects, "Pulse / moving effects", self.enable_pulse_effects)
        if not self.enable_pulse_effects:
            self._overlay_shadow.setColor(Qt.GlobalColor.transparent)
            self._apply_overlay_base_style()
            self.machineAnim.setStyleSheet("")
            self.machineAnim.style().unpolish(self.machineAnim)
            self.machineAnim.style().polish(self.machineAnim)

    def _show_settings_section(self, section: str):
        is_graphics = section == "graphics"
        is_display = section == "display"
        is_api = section == "api"
        self.settingsBtnGraphics.setChecked(is_graphics)
        self.settingsBtnDisplay.setChecked(is_display)
        self.settingsBtnApi.setChecked(is_api)
        self.settingsGraphicsSection.setVisible(is_graphics)
        self.settingsDisplaySection.setVisible(is_display)
        self.settingsApiSection.setVisible(is_api)
        if is_graphics:
            self.settingsContentTitle.setText("Graphics")
        elif is_display:
            self.settingsContentTitle.setText("Display")
        else:
            self.settingsContentTitle.setText("API Config")

    def _load_api_settings_form(self):
        cfg = self.client_config
        self.apiServerUrlInput.setText(str(cfg.get("server_url", SERVER_URL)))
        self.apiClientIdInput.setText(str(cfg.get("client_id", CLIENT_ID)))
        mode = str(cfg.get("scanner_mode", SCANNER_MODE)).strip().lower()
        idx = self.apiScannerModeCombo.findText(mode, Qt.MatchFlag.MatchFixedString)
        self.apiScannerModeCombo.setCurrentIndex(idx if idx >= 0 else 0)
        self.apiScannerPortInput.setText(str(cfg.get("scanner_com_port", SCANNER_COM_PORT)))
        self.apiScannerBaudInput.setText(str(cfg.get("scanner_baudrate", SCANNER_BAUDRATE)))
        self.apiScannerTimeoutInput.setText(str(cfg.get("scanner_timeout", SCANNER_TIMEOUT)))
        jcfg = getattr(self, "job_api_config", {}) or {}
        self.apiJobApiBaseUrlInput.setText(str(jcfg.get("base_url", "")))
        self.apiJobApiUserInput.setText(str(jcfg.get("user") or jcfg.get("username") or ""))
        self.apiJobApiTokenInput.setText(str(jcfg.get("bearer_token", "")))
        self.apiJobApiPasswordInput.setText(str(jcfg.get("password", "")))

    def _apply_api_settings(self):
        server_url = self.apiServerUrlInput.text().strip().rstrip("/")
        client_id = self.apiClientIdInput.text().strip() or socket.gethostname()
        scanner_mode = self.apiScannerModeCombo.currentText().strip().lower()
        scanner_port = self.apiScannerPortInput.text().strip()
        job_api_base_url = self.apiJobApiBaseUrlInput.text().strip().rstrip("/")
        job_api_user = self.apiJobApiUserInput.text().strip()
        job_api_token = self.apiJobApiTokenInput.text()
        job_api_password = self.apiJobApiPasswordInput.text()
        if not server_url:
            self.status.setText("API config failed: Server URL is required.")
            return
        if scanner_mode not in ("auto", "keyboard", "serial"):
            self.status.setText("API config failed: invalid scanner mode.")
            return
        try:
            scanner_baudrate = int(self.apiScannerBaudInput.text().strip())
            if scanner_baudrate <= 0:
                raise ValueError()
        except Exception:
            self.status.setText("API config failed: Scanner baudrate must be a positive integer.")
            return
        try:
            scanner_timeout = float(self.apiScannerTimeoutInput.text().strip())
            if scanner_timeout < 0:
                raise ValueError()
        except Exception:
            self.status.setText("API config failed: Scanner timeout must be 0 or greater.")
            return

        self.client_config.update({
            "server_url": server_url,
            "client_id": client_id,
            "scanner_mode": scanner_mode,
            "scanner_com_port": scanner_port or SCANNER_COM_PORT,
            "scanner_baudrate": scanner_baudrate,
            "scanner_timeout": scanner_timeout,
        })
        self.job_api_config.update({
            "base_url": job_api_base_url,
            "user": job_api_user,
            "username": job_api_user,
            "password": job_api_password,
            "bearer_token": job_api_token,
        })
        _save_client_config(self.client_config)
        _save_job_api_config(self.job_api_config)
        self._restart_scanner_input()
        self._trigger_identity_cache_sync(force=True)
        self.status.setText("API/Scanner configuration applied.")

    def _test_job_api_settings(self):
        base = self.apiJobApiBaseUrlInput.text().strip().rstrip("/")
        user = self.apiJobApiUserInput.text().strip()
        token = self.apiJobApiTokenInput.text().strip()
        password = self.apiJobApiPasswordInput.text()
        if not base:
            self.status.setText("Job API test failed: Job API Base URL is required.")
            return
        if not token and not user:
            self.status.setText("Job API test failed: Bearer token or username is required.")
            return
        job_id, ok = QInputDialog.getText(self, "Test Job API", "Enter Job ID to test (GET /v1/jobs/{id}):")
        if not ok:
            self.status.setText("Job API test cancelled.")
            return
        job_id = str(job_id).strip()
        if not job_id:
            self.status.setText("Job API test failed: Job ID is required.")
            return
        try:
            if not token and user and password:
                token = self._get_job_api_bearer_token(base=base, user=user, password=password) or ""
                if not token:
                    self.status.setText("Job API test failed: login did not return a bearer token.")
                    self._append_job_api_log("TEST FAIL: login did not return bearer token")
                    return
            elif token:
                self.job_api_config.update({
                    "base_url": base,
                    "user": user,
                    "username": user,
                    "password": password,
                    "bearer_token": token,
                })
                _save_job_api_config(self.job_api_config)
            headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
            resp = requests.get(
                self._job_api_url(base, f"/jobs/{job_id}"),
                headers=headers,
                timeout=5,
            )
            self._append_job_api_log(f"TEST GET {self._job_api_url(base, f'/jobs/{job_id}')} -> HTTP {resp.status_code}")
            print(f"[JobAPI] TEST GET {self._job_api_url(base, f'/jobs/{job_id}')} -> HTTP {resp.status_code}")
            if resp.status_code != 200:
                self.status.setText(
                    f"Job API test failed HTTP {resp.status_code}: {self._http_error_snippet(resp) or 'No response body'}"
                )
                self._append_job_api_log(f"TEST FAIL: {self._http_error_snippet(resp) or 'No response body'}")
                print(f"[JobAPI] TEST FAIL HTTP {resp.status_code}: {self._http_error_snippet(resp) or 'No response body'}")
                return
            data = resp.json()
            job = {}
            if isinstance(data, dict) and isinstance(data.get("data"), dict):
                job = data["data"].get("job") or {}
            ref = str((job or {}).get("ref_no", "")).strip()
            jid = str((job or {}).get("id", "")).strip() or job_id
            self.status.setText(f"Job API test OK (GET): {jid}{' / ' + ref if ref else ''}")
            self._append_job_api_log(f"TEST OK: {jid}{' / ' + ref if ref else ''}")
            print(f"[JobAPI] TEST OK: {jid}{' / ' + ref if ref else ''}")
        except Exception as e:
            self.status.setText(f"Job API test failed: {e}")
            self._append_job_api_log(f"TEST ERROR: {e}")
            print(f"[JobAPI] TEST ERROR: {e}")

    def _restart_scanner_input(self):
        self._serial_stop.set()
        if self._serial_thread and self._serial_thread.is_alive():
            self._serial_thread.join(timeout=1.0)
        self._serial_thread = None
        if hasattr(self, "filter"):
            try:
                self.removeEventFilter(self.filter)
            except Exception:
                pass
            self.filter = None
        self._serial_stop = threading.Event()
        self._setup_scanner_input()

    def _apply_display_settings(self):
        os_name = self.displayOsCombo.currentText().strip()
        size_name = self.displaySizeCombo.currentText().strip()
        self.setWindowState(Qt.WindowState.WindowNoState)
        if size_name.lower() == "fullscreen":
            self.showFullScreen()
            self.status.setText(f"Display applied: {os_name} / Fullscreen")
            return

        m = re.match(r"^\s*(\d+)\s*x\s*(\d+)\s*$", size_name)
        if m:
            w = max(800, int(m.group(1)))
            h = max(480, int(m.group(2)))
            self.showNormal()
            self.resize(w, h)
            self.status.setText(f"Display applied: {os_name} / {w}x{h}")
            return
        self.status.setText("Display apply failed: invalid size preset.")

    def _set_toggle_button_text(self, btn: QPushButton, label: str, enabled: bool):
        btn.setText(f"{label}: {'ON' if enabled else 'OFF'}")

    def _should_keep_background_blur(self) -> bool:
        return (
            self.productionOverlay.isVisible()
            or self.resolveOverlay.isVisible()
            or self.rawMatsOverlay.isVisible()
            or self.rejectSummaryOverlay.isVisible()
            or self.productHistoryOverlay.isVisible()
            or self.rejectReviewOverlay.isVisible()
            or self.finishOverlay.isVisible()
            or self.settingsOverlay.isVisible()
        )

    def _safe_text(self, v: Any, fallback: str = "-") -> str:
        if v is None:
            return fallback
        s = str(v).strip()
        return s if s else fallback

    def _http_error_snippet(self, resp: Any, max_len: int = 180) -> str:
        try:
            txt = str(getattr(resp, "text", "") or "").strip()
        except Exception:
            txt = ""
        if not txt:
            return ""
        txt = re.sub(r"\s+", " ", txt)
        return txt[:max_len] + ("..." if len(txt) > max_len else "")

    def _append_job_api_log(self, msg: str):
        line = f"[{time.strftime('%H:%M:%S')}] {str(msg or '').strip()}"
        rows = list(getattr(self, "_job_api_logs", []) or [])
        rows.append(line)
        rows = rows[-8:]
        self._job_api_logs = rows
        if hasattr(self, "jobApiLogLabel") and self.jobApiLogLabel is not None:
            self.jobApiLogLabel.setText("\n".join(rows) if rows else "No Job API logs yet.")

    def _extract_job_record(self) -> Dict[str, Any]:
        payload = self.state.job_payload or {}
        if isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("job"), dict):
            return payload["data"]["job"]
        if isinstance(payload.get("job"), dict):
            return payload["job"]
        return payload if isinstance(payload, dict) else {}

    def _get_job_api_bearer_token(self, *, base: str, user: str, password: str) -> Optional[str]:
        base_url = str(base or "").strip().rstrip("/")
        username = str(user or "").strip()
        pwd = str(password or "")
        if not (base_url and username and pwd):
            self._append_job_api_log(
                f"LOGIN skipped: missing config (base={'set' if base_url else 'empty'}, user={'set' if username else 'empty'}, pass={'set' if pwd else 'empty'})"
            )
            print(
                f"[JobAPI] LOGIN skipped: missing config (base={'set' if base_url else 'empty'}, user={'set' if username else 'empty'}, pass={'set' if pwd else 'empty'})"
            )
            return None
        cfg = getattr(self, "job_api_config", {}) or {}
        cached_base = str(cfg.get("base_url", "")).strip().rstrip("/")
        cached_user = str(cfg.get("user", "")).strip()
        cached_token = str(cfg.get("bearer_token", "")).strip()
        try:
            cached_exp = int(float(cfg.get("token_expires_at_epoch", 0) or 0))
        except Exception:
            cached_exp = 0
        now_epoch = int(time.time())
        if cached_token and cached_base == base_url and cached_user == username and cached_exp > (now_epoch + 30):
            self._append_job_api_log("LOGIN skipped (cached bearer token reused)")
            return cached_token
        login_url = f"{base_url}/auth/login"
        self._append_job_api_log(f"LOGIN preparing {login_url} (user={username}, ttl={cfg.get('ttl_seconds', 604800) if isinstance(cfg, dict) else 604800})")
        print(f"[JobAPI] LOGIN preparing {login_url} (user={username})")
        try:
            ttl_seconds = int(cfg.get("ttl_seconds", 604800) or 604800) if isinstance(cfg, dict) else 604800
            force_new_token = bool(cfg.get("force_new_token", True)) if isinstance(cfg, dict) else True
            resp = requests.post(
                login_url,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json={
                    "identity": username,
                    "password": pwd,
                    "ttlSeconds": ttl_seconds,
                    "forceNewToken": force_new_token,
                },
                timeout=5,
            )
            self._append_job_api_log(f"LOGIN POST {login_url} -> HTTP {resp.status_code}")
            print(f"[JobAPI] LOGIN POST {login_url} -> HTTP {resp.status_code}")
            if resp.status_code != 200:
                self.status.setText(
                    f"Job API login failed HTTP {resp.status_code}: {self._http_error_snippet(resp) or 'No response body'}"
                )
                self._append_job_api_log(f"LOGIN FAIL: {self._http_error_snippet(resp) or 'No response body'}")
                print(f"[JobAPI] LOGIN FAIL HTTP {resp.status_code}: {self._http_error_snippet(resp) or 'No response body'}")
                return None
            data = resp.json()
            if isinstance(data, dict) and isinstance(data.get("data"), dict):
                token = str(data["data"].get("token", "") or "").strip()
                if token and isinstance(cfg, dict):
                    cfg["base_url"] = base_url
                    cfg["user"] = username
                    cfg["password"] = pwd
                    cfg["bearer_token"] = token
                    cfg["token_expires_at_epoch"] = int(time.time()) + max(60, ttl_seconds)
                    self.job_api_config = cfg
                    _save_job_api_config(cfg)
                self._append_job_api_log("LOGIN OK (bearer token received)")
                print("[JobAPI] LOGIN OK (bearer token received)")
                return token or None
            self._append_job_api_log("LOGIN FAIL: response JSON has no data.token")
            print(f"[JobAPI] LOGIN FAIL: response JSON has no data.token payload={self._http_error_snippet(resp)}")
        except Exception as e:
            self._append_job_api_log(f"LOGIN ERROR: {e}")
            print(f"[JobAPI] LOGIN ERROR: {e}")
            pass
        return None

    def _job_api_url(self, base: str, path: str) -> str:
        base_url = str(base or "").strip().rstrip("/")
        p = "/" + str(path or "").lstrip("/")
        if base_url.endswith("/jobs"):
            base_url = base_url[:-5].rstrip("/")
        if base_url.endswith("/v1"):
            if p.startswith("/v1/"):
                return f"{base_url}{p[3:]}"
            return f"{base_url}{p}"
        if p.startswith("/v1/"):
            return f"{base_url}{p}"
        return f"{base_url}/v1{p}"

    def _fetch_job_payload_from_api(self, job_identifier: str) -> Optional[Dict[str, Any]]:
        # Reload from disk so config edits apply without restarting the client.
        try:
            self.job_api_config = _load_job_api_config()
            try:
                _dbg_cfg = self.job_api_config if isinstance(self.job_api_config, dict) else {}
                print(
                    "[JobAPI] FETCH reload cfg "
                    f"keys={list(_dbg_cfg.keys())} "
                    f"base={str(_dbg_cfg.get('base_url', ''))!r} "
                    f"bms_base={str((_dbg_cfg.get('bms') or {}).get('base_url', '')) if isinstance(_dbg_cfg.get('bms'), dict) else ''!r}"
                )
            except Exception:
                pass
        except Exception as e:
            print(f"[JobAPI] FETCH reload config error: {e}")
        raw_job_id = str(job_identifier or "").strip()
        print(f"[JobAPI] FETCH requested job_identifier={raw_job_id!r}")
        m_job_url = re.search(r"/v1/jobs/(\d+)\s*$", raw_job_id, flags=re.IGNORECASE)
        job_id = (m_job_url.group(1) if m_job_url else raw_job_id).strip()
        if not job_id:
            print("[JobAPI] FETCH skipped: empty job_id after parsing")
            return None
        jcfg = getattr(self, "job_api_config", {}) or {}
        bms = jcfg.get("bms") if isinstance(jcfg.get("bms"), dict) else {}
        base = str(jcfg.get("base_url") or bms.get("base_url") or "").strip().rstrip("/")
        token = str(jcfg.get("bearer_token", "")).strip()
        user = str(jcfg.get("user") or bms.get("username") or bms.get("user") or "").strip()
        password = str(jcfg.get("password") or bms.get("password") or "")
        print(f"[JobAPI] FETCH config base={base!r} user={'set' if user else 'empty'} token={'set' if token else 'empty'}")
        if not base or (not token and not user):
            print("[JobAPI] FETCH skipped: missing base_url or auth config")
            return None
        url = self._job_api_url(base, f"/jobs/{job_id}")

        def _payload_has_useful_job_details(payload_obj: Any) -> bool:
            if not isinstance(payload_obj, dict):
                return False
            jd = payload_obj.get("job_details") if isinstance(payload_obj.get("job_details"), dict) else {}
            if not isinstance(jd, dict):
                jd = {}
            keys = ("product_id", "mold", "color", "no_of_cavity", "std_cycle_time", "qty_per_shift")
            if any(str(jd.get(k, "") or "").strip() for k in keys):
                return True
            part_ids = jd.get("part_ids")
            parts = jd.get("parts")
            if isinstance(part_ids, list) and len(part_ids) > 0:
                return True
            if isinstance(part_ids, dict) and len(part_ids.keys()) > 0:
                return True
            if isinstance(parts, list) and len(parts) > 0:
                return True
            data_parts = payload_obj.get("parts")
            data_part_ids = payload_obj.get("parts_ids")
            if isinstance(data_parts, list) and len(data_parts) > 0:
                return True
            if isinstance(data_part_ids, list) and len(data_part_ids) > 0:
                return True
            return False

        best_partial_wrapped: Optional[Dict[str, Any]] = None
        max_attempts = 3
        try:
            if not token and user and password:
                print("[JobAPI] FETCH no cached token; requesting new token via login")
                token = self._get_job_api_bearer_token(base=base, user=user, password=password) or ""
                if not token:
                    self.status.setText("Job API login failed; using local job mapping/stub.")
                    return None
            for attempt in range(1, max_attempts + 1):
                if attempt > 1:
                    time.sleep(0.18)
                headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
                resp = requests.get(
                    url,
                    headers=headers,
                    timeout=5,
                )
                self._append_job_api_log(f"GET {url} -> HTTP {resp.status_code} (try {attempt}/{max_attempts})")
                print(f"[JobAPI] GET {url} -> HTTP {resp.status_code} (try {attempt}/{max_attempts})")
                if resp.status_code == 401 and user and password:
                    self._append_job_api_log("GET unauthorized; refreshing bearer token")
                    token = self._get_job_api_bearer_token(base=base, user=user, password=password) or token
                    continue
                if resp.status_code != 200:
                    if attempt < max_attempts:
                        continue
                    self.status.setText(
                        f"Job API GET failed HTTP {resp.status_code}: {self._http_error_snippet(resp) or 'No response body'}"
                    )
                    self._append_job_api_log(f"GET FAIL: {self._http_error_snippet(resp) or 'No response body'}")
                    print(f"[JobAPI] GET FAIL HTTP {resp.status_code}: {self._http_error_snippet(resp) or 'No response body'}")
                    return best_partial_wrapped
                data = resp.json()
                if not isinstance(data, dict):
                    if attempt < max_attempts:
                        continue
                    self.status.setText("Job API fetch returned invalid response; using local job mapping/stub.")
                    return best_partial_wrapped
                payload = data.get("data")
                if not isinstance(payload, dict):
                    if attempt < max_attempts:
                        continue
                    self.status.setText("Job API fetch has no job payload; using local job mapping/stub.")
                    return best_partial_wrapped

                wrapped = {"code": data.get("code"), "message": data.get("message"), "data": payload}
                if _payload_has_useful_job_details(payload):
                    self._append_job_api_log(f"GET OK: job {job_id}")
                    print(f"[JobAPI] GET OK: job {job_id}")
                    return wrapped
                best_partial_wrapped = wrapped
                self._append_job_api_log(f"GET partial/blank job_details; retrying ({attempt}/{max_attempts})")
                print(f"[JobAPI] GET partial/blank job_details; retrying ({attempt}/{max_attempts})")

            if best_partial_wrapped is not None:
                self.status.setText("Job API returned partial job details after retries.")
                return best_partial_wrapped
            self.status.setText("Job API fetch failed after retries; using local job mapping/stub.")
            return None
        except Exception as e:
            self.status.setText(f"Job API fetch error: {e}; using local job mapping/stub.")
            self._append_job_api_log(f"GET ERROR: {e}")
            print(f"[JobAPI] GET ERROR: {e}")
            return None

    def _refresh_job_details(self):
        job = self._extract_job_record()
        payload = self.state.job_payload or {}
        job_details = {}
        if isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("job_details"), dict):
            job_details = payload["data"]["job_details"]
        elif isinstance(payload.get("job_details"), dict):
            job_details = payload.get("job_details") or {}

        data_obj = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        part_rows: List[Dict[str, Any]] = []
        # Preferred source from Job API sample: data.parts (or job_details.parts)
        if isinstance(data_obj.get("parts"), list):
            part_rows = [r for r in data_obj.get("parts") or [] if isinstance(r, dict)]
        elif isinstance(job_details.get("parts"), list):
            part_rows = [r for r in job_details.get("parts") or [] if isinstance(r, dict)]
        # Fallback legacy sources
        elif isinstance(job_details.get("part_ids"), list):
            part_rows = [r for r in job_details.get("part_ids") or [] if isinstance(r, dict)]
        elif isinstance(job_details.get("part_ids"), dict):
            part_rows = [job_details.get("part_ids") or {}]
        elif isinstance(data_obj.get("part_ids"), list):
            part_rows = [r for r in data_obj.get("part_ids") or [] if isinstance(r, dict)]
        elif isinstance(payload.get("part_ids"), list):
            part_rows = [r for r in payload.get("part_ids") or [] if isinstance(r, dict)]

        # Keep these in payload/state for downstream use, but do not display them in Job Details cards.
        _stored_machine_num = self._safe_text(job_details.get("machine_num"), "")
        _stored_special_instructions = self._safe_text(job_details.get("special_instructions"), "")
        _stored_machine_tons = self._safe_text(job_details.get("machine_tons"), "")
        _ = (_stored_machine_num, _stored_special_instructions, _stored_machine_tons)

        fields = {
            "job_ref": self._safe_text(job.get("ref_no") or self.state.job_name),
            "product_id": self._safe_text(job_details.get("product_id") or job.get("product_id")),
            "mold": self._safe_text(job_details.get("mold") or job.get("custom_05")),
            "color": self._safe_text(job_details.get("color") or job.get("custom_06"), "N/A"),
            "cavities": self._safe_text(job_details.get("no_of_cavity") or job.get("custom_11")),
            "sticker_label": self._safe_text(job_details.get("sticker_label"), "N/A"),
            "std_cycle_time": self._safe_text(job_details.get("std_cycle_time"), "N/A"),
            "qty_per_shift": self._safe_text(job_details.get("qty_per_shift"), "N/A"),
        }

        if hasattr(self, "jobPartsTable") and self.jobPartsTable is not None:
            self.jobPartsTable.setRowCount(0)
            for part in part_rows:
                r = self.jobPartsTable.rowCount()
                self.jobPartsTable.insertRow(r)
                values = [
                    self._safe_text(part.get("part_product_id"), "-"),
                    self._safe_text(part.get("sku"), "-"),
                    self._safe_text(part.get("name"), "-"),
                    self._safe_text(part.get("part_qty_per_unit"), "-"),
                    self._safe_text(part.get("request_part_qty"), "-"),
                    f"{self._safe_text(part.get('approve_part_qty'), '-')} / {self._safe_text(part.get('complete_part_qty'), '-')}",
                ]
                for c, val in enumerate(values):
                    item = QTableWidgetItem(val)
                    item.setTextAlignment(int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
                    self.jobPartsTable.setItem(r, c, item)
            if self.jobPartsTable.rowCount() == 0:
                self.jobPartsTable.insertRow(0)
                for c in range(6):
                    self.jobPartsTable.setItem(0, c, QTableWidgetItem("-"))

        if hasattr(self, "rightCycleStd") and self.rightCycleStd is not None:
            self.rightCycleStd.setText(f"Std Cycle Time: {fields.get('std_cycle_time', 'N/A')}")
        if hasattr(self, "topCycleStd") and self.topCycleStd is not None:
            self.topCycleStd.setText(f"Std Cycle Time: {fields.get('std_cycle_time', 'N/A')}")
        if hasattr(self, "rightCycleQtyShift") and self.rightCycleQtyShift is not None:
            self.rightCycleQtyShift.setText(f"Qty / Shift: {fields.get('qty_per_shift', 'N/A')}")
        if hasattr(self, "topCycleQtyShift") and self.topCycleQtyShift is not None:
            self.topCycleQtyShift.setText(f"Qty / Shift: {fields.get('qty_per_shift', 'N/A')}")

    def _build_reject_summary_text(self) -> str:
        s = self.state
        payload = s.job_payload or {}
        job = self._extract_job_record()

        summary = {}
        if isinstance(payload.get("summary"), dict):
            summary = payload["summary"]
        elif isinstance(payload.get("reject_summary"), dict):
            summary = payload["reject_summary"]

        pack_total = summary.get("pack_total", s.pack_count)
        good_total = summary.get("good_total", s.good_total)
        butal_total = summary.get("butal_total", s.butal_total)
        reject_total = summary.get("reject_total", s.reject_total)

        if isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("partials"), list):
            p_list = payload["data"]["partials"]
            if p_list:
                pack_total = sum(int(float(p.get("partial_qty", 0) or 0)) for p in p_list)
                reject_total = sum(int(float(p.get("reject_qty", 0) or 0)) for p in p_list)
                good_total = pack_total

        breakdown = {}
        if isinstance(summary.get("reject_breakdown"), dict):
            breakdown = summary.get("reject_breakdown")
        elif isinstance(payload.get("rejects"), dict):
            breakdown = payload.get("rejects")
        elif s.reject_breakdown:
            breakdown = s.reject_breakdown

        lines = [
            f"Job: {self._safe_text(job.get('ref_no') or s.job_name)} ({s.job_code or '-'})",
            f"Pack: {pack_total} | Good: {good_total} | Butal: {butal_total} | Reject: {reject_total} | Total Good: {good_total + butal_total}",
        ]

        if breakdown:
            details = ", ".join(f"{k}={v}" for k, v in breakdown.items())
            lines.append(f"Reasons: {details}")
        else:
            lines.append("Reasons: -")

        extra_ref = job.get("id") or payload.get("reference") or payload.get("process_id") or payload.get("id")
        if extra_ref:
            lines.append(f"Ref: {extra_ref}")

        return "\n".join(lines)

    def _set_banner_text(self, text: str):
        self._banner_base_text = text
        self.banner.setText((self._banner_base_text or "").strip())

    def _update_header_datetime(self):
        now_local = datetime.now()
        self.headerDateTime.setText(now_local.strftime("%A | %b %d, %Y | %I:%M:%S %p"))

    def _operator_display_name(self, text: Optional[str]) -> str:
        if not text:
            return "-"
        parts = [p.strip() for p in str(text).split(" - ", 1)]
        if len(parts) == 2:
            return parts[1] or "-"
        return str(text)

    def _normalize_job_code(self, value: Optional[str]) -> str:
        if not value:
            return ""
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        if not digits:
            return str(value).strip().upper()
        return digits.lstrip("0") or "0"

    def _extract_job_code_from_pack_qr(self, raw: str) -> Optional[str]:
        # Expected tail format like "...-000000102378" where 102378 is the job code.
        m = re.search(r"-0*(\d+)\s*$", str(raw).strip())
        if not m:
            return None
        return m.group(1).lstrip("0") or "0"

    def _extract_pack_history_fields(self, raw: str) -> Optional[Dict[str, str]]:
        s = str(raw).strip()
        if "V2" not in s or "QB" in s:
            return None
        m = re.search(r"P(\d{11})Q(\d{11})I(\d{11})T(\d{11})L(\d{14})-(\d+)\s*$", s)
        if not m:
            return None
        p_digits, q_digits, i_digits, t_digits, lot_digits, po_digits = m.groups()
        product_code = p_digits.lstrip("0") or "0"
        return {
            "product_name": f"Product {product_code}",
            "product_p": p_digits,
            "qty_q": str(int(q_digits)),
            "index": str(int(i_digits)),
            "total_labels": str(int(t_digits)),
            "lot_number": lot_digits,  # preserve QR formatting
            "po_number": po_digits,    # preserve QR formatting
        }

    def _scan_display_text(self, res, raw: str) -> str:
        if res is None:
            return "Unknown scan"
        if res.kind == "MACHINE":
            return f"Machine: {res.value}"
        if res.kind == "JOB":
            return f"Job: {res.value}"
        if res.kind == "OPERATOR":
            return f"Operator: {self._operator_display_name(res.value)}"
        if res.kind == "RAW_MATERIAL":
            if isinstance(res.meta, dict) and res.meta.get("unique_key"):
                return f"Raw Material: {res.value} (+{int(res.qty or 1)}) [{res.meta.get('unique_key')}]"
            return f"Raw Material: {res.value} (+{int(res.qty or 1)})"
        if res.kind == "PACK":
            return f"Pack +{int(res.qty or 0)}"
        if res.kind == "BUTAL":
            return f"Butal +{int(res.qty or 0)}"
        if res.kind == "REJECT_TRIGGER":
            return "Reject mode enabled"
        if res.kind == "REJECT_REASON":
            return f"Reject reason: {res.value}"
        if res.kind == "STARTUP_REJECT":
            return "Start Up Reject +1"
        if res.kind == "REJECT_SUMMARY":
            return "Reject summary requested"
        if res.kind == "OPERATOR_SHIFT_TRIGGER":
            return "Operator shift handoff requested"
        if res.kind == "PRODUCTION_DAILY_REPORT_TRIGGER":
            return "Production daily report mode enabled"
        if res.kind == "PRODUCTION_DAILY_REPORT_RESOLVE":
            return "Production daily report resolve"
        if res.kind == "JOB_STUB":
            return res.value
        return "Scan received"

    def log_last(self, text: str):
        return

    def _set_status_text(self, text: str):
        t = str(text).replace("\n", " ").strip()
        # Hide scanner transport diagnostics from UI for now.
        if (
            t.startswith("Scanner serial ")
            or t.startswith("Scanner input:")
            or "could not open port" in t.lower()
        ):
            return
        if len(t) > 120:
            short = t[:117] + "..."
            self.status.setText(short)
            self.status.setToolTip(t)
        else:
            self.status.setText(t)
            self.status.setToolTip("")

    def _setup_scanner_input(self):
        mode = str(self.client_config.get("scanner_mode", SCANNER_MODE)).strip().lower()
        scanner_port = str(self.client_config.get("scanner_com_port", SCANNER_COM_PORT)).strip() or SCANNER_COM_PORT
        scanner_baudrate = int(self.client_config.get("scanner_baudrate", SCANNER_BAUDRATE))
        scanner_timeout = float(self.client_config.get("scanner_timeout", SCANNER_TIMEOUT))
        if mode not in ("auto", "keyboard", "serial"):
            mode = "auto"

        if mode in ("auto", "keyboard"):
            self.filter = ScannerFilter()
            self.installEventFilter(self.filter)
            self.filter.scanned.connect(self.scan_received.emit)
            if mode == "keyboard":
                self._set_status_text("Scanner input: Keyboard mode")
                return

        # auto or serial path
        if serial is None:
            if mode == "serial":
                self._set_status_text("Scanner input: Serial requested but pyserial is not installed.")
            else:
                self._set_status_text("Scanner input: Keyboard mode (pyserial not installed)")
            return

        self._serial_thread = threading.Thread(target=self._serial_reader_loop, daemon=True)
        self._serial_thread.start()
        if mode == "auto":
            self._set_status_text(f"Scanner input: Auto mode (keyboard + serial {scanner_port})")
        else:
            self._set_status_text(f"Scanner input: Serial mode ({scanner_port})")

    def _serial_reader_loop(self):
        while not self._serial_stop.is_set():
            scanner_port = str(self.client_config.get("scanner_com_port", SCANNER_COM_PORT)).strip() or SCANNER_COM_PORT
            scanner_baudrate = int(self.client_config.get("scanner_baudrate", SCANNER_BAUDRATE))
            scanner_timeout = float(self.client_config.get("scanner_timeout", SCANNER_TIMEOUT))
            try:
                with serial.Serial(
                    port=scanner_port,
                    baudrate=scanner_baudrate,
                    timeout=scanner_timeout,
                ) as ser:
                    self.scanner_status.emit(
                        f"Scanner serial connected: {scanner_port} @ {scanner_baudrate}"
                    )
                    while not self._serial_stop.is_set():
                        raw = ser.readline()
                        if not raw:
                            continue
                        text = raw.decode("utf-8", errors="ignore").strip()
                        if text:
                            self.scan_received.emit(text)
            except Exception as e:
                self.scanner_status.emit(f"Scanner serial retry ({scanner_port}): {e}")
                self._serial_stop.wait(2.0)

    def can_accept_production_scans(self) -> bool:
        s = self.state
        return bool(
            s.machine_code and s.job_code and s.operator_id
            and not s.waiting_initial_cycle_time_input
        )

    def _missing_session_prereq_message(self) -> Optional[str]:
        s = self.state
        if not s.machine_code:
            return "Scan machine QR first."
        if not s.job_code:
            return "Scan job QR first."
        if not s.operator_id:
            return "Scan operator QR first."
        return None

    def on_scanned(self, raw: str):
        if self._operator_shift_flash_active:
            self.status.setText("Operator shift handoff in progress. Please wait.")
            return
        if self._finish_anim_running:
            self.status.setText("Finish job in progress. Please wait.")
            return
        raw_s = str(raw).strip()
        raw_l = raw_s.lower()
        s = self.state

        if s.waiting_cycle_time_confirm_popup:
            phase = int(s.cycle_time_confirm_phase or 1)
            if phase == 1:
                if raw_l.startswith("num_") and raw_l[-1:].isdigit():
                    s.cycle_time_new_input += raw_l[-1]
                    self.resolveNewCycle.setText(f"Cycle Time: {s.cycle_time_new_input}")
                    return
                if raw_l == "backspace":
                    s.cycle_time_new_input = s.cycle_time_new_input[:-1]
                    self.resolveNewCycle.setText(f"Cycle Time: {s.cycle_time_new_input}")
                    return
                if raw_l == "confirm":
                    if not s.cycle_time_new_input:
                        self.status.setText("Cycle Time is empty. Scan digits first.")
                        return
                    s.cycle_time_current = s.cycle_time_new_input
                    s.cycle_time_confirm_phase = 2
                    s.reject_summary_last_scanned_at = datetime.now(timezone.utc).isoformat()
                    self._hide_resolve_overlay()
                    s.showing_reject_summary = True
                    self._show_reject_summary_overlay()
                    self.status.setText("Cycle time updated. Scan the same Supervisor badge again to confirm all.")
                    self._refresh_ui()
                    self._save_active_session_snapshot()
                    return
                self.status.setText("Supervisor cycle review: scan num_0..num_9, backspace, confirm.")
                return

            if raw_s != (s.cycle_time_confirm_actor_code or ""):
                self.status.setText("Confirmation active: scan the same Supervisor badge again.")
                return
            actor_name = s.cycle_time_confirm_actor_name or raw_s
            actor_role = s.cycle_time_confirm_actor_role or "SUPERVISOR"
            s.cycle_time_confirmed_by = actor_name
            stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            s.reject_review_logs.append(
                {
                    "timestamp": stamp,
                    "status": "CONFIRMED",
                    "actor_role": actor_role,
                    "actor_name": actor_name,
                    "actor_code": raw_s,
                }
            )
            self._hide_cycle_time_confirm_popup()
            self._hide_reject_summary_overlay()
            self.status.setText(f"Cycle time and reject summary confirmed by {actor_name}")
            self._refresh_ui()
            self._save_active_session_snapshot()
            self.push_event(
                {
                    "type": "CYCLE_TIME_CONFIRMED",
                    "cycle_time": s.cycle_time_current,
                    "confirmed_by_role": actor_role,
                    "confirmed_by_name": actor_name,
                    "confirmed_by_code": raw_s,
                },
                f"CYCLE TIME CONFIRMED {actor_name}",
            )
            self.push_event(
                {
                    "type": "REJECT_REVIEW_CONFIRM",
                    "timestamp": stamp,
                    "status": "CONFIRMED",
                    "actor_role": actor_role,
                    "actor_name": actor_name,
                    "rotation_count": len(s.reject_review_logs),
                },
                f"REJECT REVIEW CONFIRMED {actor_name} ({actor_role})",
                silent=True,
            )
            return

        reviewer = self._reviewer_from_scan(raw_s)
        if reviewer is not None:
            reviewer_can_supervisor = str(reviewer.get("can_supervisor", "0")) == "1"
            reviewer_can_qc = str(reviewer.get("can_qc", "0")) == "1"
            in_downtime_flow = (
                s.waiting_production_report_reason
                or s.waiting_cycle_time_input
                or s.waiting_maintenance_qr
                or s.waiting_supervisor_qr
                or s.waiting_operator_downtime_confirm
                or s.downtime_active
            )
            if not in_downtime_flow:
                if not self.can_accept_production_scans():
                    self.status.setText("Complete session first: MACHINE -> JOB -> OPERATOR.")
                    return
                # Supervisor can review/update cycle time any time, then confirm with a second scan.
                if reviewer_can_supervisor and s.cycle_time_current:
                    self._show_cycle_time_confirm_popup(reviewer)
                    self.status.setText("Supervisor cycle review opened. Enter new cycle time, then confirm.")
                    return
                if not reviewer_can_supervisor:
                    self.status.setText("Authorized badge scanned. No supervisor action pending.")
                    return
                if not s.reject_review_open:
                    rows = self._get_non_zero_rejects()
                    if not rows:
                        self.status.setText("No recorded rejects to review.")
                        return
                    self._show_reject_review_overlay(reviewer)
                    self.status.setText("Reject check started. Scan same badge to continue.")
                    return
                if raw_s != (s.reject_review_actor_code or ""):
                    self.status.setText("Reject review active: scan the same badge to continue.")
                    return
                if s.reject_review_phase == 1:
                    s.reject_review_phase = 2
                    self.rejectReviewCycle.setText(f"Cycle Count: {s.pack_count} | Cycle Time: {s.cycle_time_current or '-'}")
                    self.rejectReviewCycle.show()
                    self.rejectReviewHint.setText("Scan the same authorized badge again to confirm.")
                    self.status.setText("Cycle details shown. Scan same badge again to confirm.")
                    return
                if s.reject_review_phase == 2:
                    s.reject_review_phase = 3
                    self.rejectReviewLoadingLayer.show()
                    self.rejectReviewLoadingLayer.raise_()
                    self._reject_review_anim_value = 0
                    self.rejectReviewLoadingBar.setValue(0)
                    self._set_reject_review_blur(True)
                    self._set_background_blur(True)
                    self._reject_review_anim_timer.start()
                    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                    log = {
                        "timestamp": stamp,
                        "status": "CONFIRMED",
                        "actor_role": s.reject_review_actor_role,
                        "actor_name": s.reject_review_actor_name,
                        "actor_code": s.reject_review_actor_code,
                    }
                    s.reject_review_logs.append(log)
                    self.push_event(
                        {
                            "type": "REJECT_REVIEW_CONFIRM",
                            "timestamp": stamp,
                            "status": "CONFIRMED",
                            "actor_role": log["actor_role"],
                            "actor_name": log["actor_name"],
                            "rotation_count": len(s.reject_review_logs),
                        },
                        f"REJECT REVIEW CONFIRMED {log['actor_name']} ({log['actor_role']})",
                    )
                    self._refresh_ui()
                    QTimer.singleShot(1200, self._hide_reject_review_overlay)
                    self.status.setText("Reject review confirmed.")
                    return

        if raw_l in ("showrawmats", "rawmatsummary~1"):
            if self.rawMatsOverlay.isVisible():
                self._hide_raw_mats_overlay()
                self.status.setText("Raw materials summary closed.")
            else:
                if self.productHistoryOverlay.isVisible():
                    self._hide_product_history_overlay()
                self._show_raw_mats_overlay()
                self.status.setText("Raw materials summary opened.")
            return

        if self.productHistoryOverlay.isVisible() and raw_l in ("next", "prev", "previous", "preview"):
            logs_count = len([x for x in (self.state.product_pack_history_logs or []) if isinstance(x, dict)])
            page_size = max(1, int(getattr(self, "_product_history_page_size", 15) or 15))
            total_pages = max(1, (logs_count + page_size - 1) // page_size)
            if raw_l == "next":
                if self._product_history_page < (total_pages - 1):
                    self._product_history_page += 1
                    self._refresh_product_history_overlay()
                    self.status.setText(f"Pack history page {self._product_history_page + 1} of {total_pages}.")
                else:
                    self.status.setText("Pack history: already on last page.")
            else:
                if self._product_history_page > 0:
                    self._product_history_page -= 1
                    self._refresh_product_history_overlay()
                    self.status.setText(f"Pack history page {self._product_history_page + 1} of {total_pages}.")
                else:
                    self.status.setText("Pack history: already on first page.")
            return

        if raw_l == "prodhistory~1":
            if self.productHistoryOverlay.isVisible():
                self._hide_product_history_overlay()
                self.status.setText("Product PACK history closed.")
            else:
                if self.rawMatsOverlay.isVisible():
                    self._hide_raw_mats_overlay()
                self._product_history_page = 0
                self._show_product_history_overlay()
                self.status.setText("Product PACK history opened.")
            return

        if self.rawMatsOverlay.isVisible():
            self._hide_raw_mats_overlay()
        if self.rejectSummaryOverlay.isVisible() and raw_l != "rejectsummary":
            self._hide_reject_summary_overlay()
        if self.productHistoryOverlay.isVisible():
            self._hide_product_history_overlay()

        res_pre = parse_scan(raw_s)

        if s.waiting_initial_cycle_time_input:
            if raw_l.startswith("num_") and raw_l[-1:].isdigit():
                s.cycle_time_new_input += raw_l[-1]
                self._update_cycle_input_display()
                return
            if raw_l == "backspace":
                s.cycle_time_new_input = s.cycle_time_new_input[:-1]
                self._update_cycle_input_display()
                return
            if raw_l == "confirm":
                if not s.cycle_time_new_input:
                    self.status.setText("Cycle Time is empty. Scan digits first.")
                    return
                s.cycle_time_current = s.cycle_time_new_input
                s.waiting_initial_cycle_time_input = False
                s.waiting_initial_cycle_qc_confirm = False
                self._hide_resolve_overlay()
                self.status.setText("Cycle time saved. Production can continue; Supervisor may confirm later.")
                self._refresh_ui()
                self._save_active_session_snapshot()
                return
            self.status.setText("Cycle Time setup: scan num_0..num_9, backspace, confirm.")
            return

        # Raw material scanning: no mode/state required, only needs active session.
        if res_pre and res_pre.kind == "RAW_MATERIAL":
            if not self.can_accept_production_scans():
                msg = self._missing_session_prereq_message() or "Complete session first: MACHINE -> JOB -> OPERATOR."
                self.status.setText(msg[:1].upper() + msg[1:])
                self._show_invalid_overlay(msg)
                return
            meta = res_pre.meta if isinstance(res_pre.meta, dict) else {}
            raw_job_code = self._normalize_job_code(meta.get("job_code")) if meta.get("job_code") else ""
            current_job_code = self._normalize_job_code(s.job_code)
            if raw_job_code and current_job_code and raw_job_code != current_job_code:
                self.status.setText(
                    f"Invalid RAW MATERIAL QR: job code {raw_job_code} does not match current job {s.job_code}."
                )
                self._show_invalid_overlay("This QR is not for this job.")
                return

            unique_key = str(meta.get("unique_key") or "").strip()
            if unique_key and unique_key in s.raw_material_unique_keys:
                self.status.setText("Invalid RAW MATERIAL QR: duplicate serial already scanned.")
                self._show_invalid_overlay("QR code already scanned.")
                return

            qty = int(res_pre.qty or 1)
            s.raw_sacks_count += qty
            material_name = str((meta.get("material_name") if isinstance(meta, dict) else None) or res_pre.value or "Raw Material").strip()
            s.raw_material_scans.append(material_name)
            s.raw_material_logs.append(
                {
                    "material": material_name,
                    "material_name": material_name,
                    "qty": qty,
                    "index": str(meta.get("index") or "") if isinstance(meta, dict) else None,
                    "total_labels": str(meta.get("total_labels") or "") if isinstance(meta, dict) else None,
                    "lot_number": str(meta.get("lot_number") or "") if isinstance(meta, dict) else None,
                    "po_number": str(meta.get("po_number") or "") if isinstance(meta, dict) else None,
                    "unique_key": unique_key or None,
                    "raw_job_code": raw_job_code or None,
                    "scanned_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            if unique_key:
                s.raw_material_unique_keys.add(unique_key)
            self.log_last(self._scan_display_text(res_pre, raw_s))
            self.status.setText(f"Raw material scanned: {material_name} (+{qty})")
            self._refresh_ui()
            self.push_event(
                {
                    "type": "RAW_MATERIAL",
                    "material": material_name,
                    "qty": qty,
                    "unique_key": unique_key or None,
                    "raw_job_code": raw_job_code or None,
                },
                f"RAW MATERIAL {material_name} +{qty}",
            )
            return

        # Resolution step 1: Cycle time input via num_0..num_9, backspace, confirm
        if s.waiting_cycle_time_input:
            if raw_l.startswith("num_") and raw_l[-1:].isdigit():
                s.cycle_time_new_input += raw_l[-1]
                self._update_cycle_input_display()
                return
            if raw_l == "backspace":
                s.cycle_time_new_input = s.cycle_time_new_input[:-1]
                self._update_cycle_input_display()
                return
            if raw_l == "confirm":
                if not s.cycle_time_new_input:
                    self.status.setText("Cycle Time is empty. Scan digits first.")
                    return
                s.cycle_time_current = s.cycle_time_new_input
                s.waiting_cycle_time_input = False
                s.waiting_maintenance_qr = True
                self.resolveOldCycleTitle.setText("RESOLVED CYCLE TIME")
                self.resolveNewCycleTitle.setText("NEXT STEP")
                self.resolveHint.setText("Scan Maintenance QR")
                self.resolveNewCycle.setText(f"Cycle Time: {s.cycle_time_current}")
                return
            self.status.setText("Cycle Time input mode: scan num_0..num_9, backspace, confirm.")
            return

        # Resolution step 2: Maintenance
        if s.waiting_maintenance_qr:
            auth = self._authorized_person_from_scan(raw_s)
            if auth and str(auth.get("can_maintenance", "0")) == "1":
                s.maintenance_name = str(auth.get("name") or raw_s)
                s.waiting_maintenance_qr = False
                s.waiting_supervisor_qr = True
                self.resolveOldCycleTitle.setText("MAINTENANCE")
                self.resolveNewCycleTitle.setText("NEXT STEP")
                self.resolveHint.setText("Scan Supervisor QR")
                self._refresh_downtime_panel()
                return
            self.status.setText("Scan valid Maintenance QR.")
            return

        # Resolution step 3: Supervisor
        if s.waiting_supervisor_qr:
            auth = self._authorized_person_from_scan(raw_s)
            if auth and str(auth.get("can_supervisor", "0")) == "1":
                s.supervisor_name = str(auth.get("name") or raw_s)
                s.waiting_supervisor_qr = False
                s.waiting_operator_downtime_confirm = True
                self.resolveOldCycleTitle.setText("SUPERVISOR")
                self.resolveNewCycleTitle.setText("NEXT STEP")
                self.resolveHint.setText("Scan Operator QR to confirm.")
                self._refresh_downtime_panel()
                return
            self.status.setText("Scan valid Supervisor QR.")
            return

        # Resolution step 4: Operator confirmation
        if s.waiting_operator_downtime_confirm:
            op_auth = self._operator_from_scan(raw_s)
            if op_auth:
                op_value = f"{op_auth.get('code', raw_s)} - {op_auth.get('name', raw_s)}"
                scanned_operator_code = self._operator_code_only(op_value)
                current_operator_code = self._operator_code_only(s.operator_id)
                if scanned_operator_code != current_operator_code:
                    self.status.setText("Operator confirmation failed: must be current operator.")
                    return
                if s.downtime_started_at:
                    s.downtime_last_seconds = max(0, int(time.time() - s.downtime_started_at))
                s.downtime_started_at = None
                s.downtime_active = False
                self._reset_downtime_resolution_state()
                self._hide_resolve_overlay()
                self._hide_production_overlay()
                self.status.setText("Downtime resolved and confirmed.")
                self.push_event(
                    {
                        "type": "PRODUCTION_DAILY_REPORT_RESOLVED",
                        "reason_code": s.downtime_reason_code,
                        "reason": s.downtime_reason_text,
                        "cycle_time": s.cycle_time_current,
                        "maintenance": s.maintenance_name,
                        "supervisor": s.supervisor_name,
                    },
                    "PRODUCTION DAILY REPORT RESOLVED",
                )
                self._refresh_ui()
                return
            known_auth = self._authorized_person_from_scan(raw_s)
            if known_auth is not None:
                self.status.setText("Operator confirmation failed: scanned badge is not an Operator.")
                self._show_invalid_overlay("Only Operator role can confirm this step.")
                return
            self.status.setText("Scan operator QR to confirm.")
            return

        # Downtime lock: allow resolve trigger and SUR while active
        if s.downtime_active and raw_l not in ("productiondailyreport~2", "sur"):
            self.status.setText('Downtime active: only "productiondailyreport~2" or "SUR" is allowed.')
            return

        res = parse_scan(raw_s)
        op_auth = self._operator_from_scan(raw_s)
        if op_auth is not None:
            res = ScanResult(kind="OPERATOR", raw=raw_s, value=f"{op_auth.get('code', raw_s)} - {op_auth.get('name', raw_s)}")
        elif res is not None and res.kind == "OPERATOR":
            # Reject legacy/static operator QR unless it exists in the server profile data with Operator role.
            self.status.setText("Invalid operator QR: badge is not registered as Operator.")
            self._show_invalid_overlay("Operator badge is not registered on server.")
            return
        elif res is None and s.machine_code and s.job_code and not s.operator_id:
            known_auth = self._authorized_person_from_scan(raw_s)
            if known_auth is not None:
                self.status.setText("Invalid operator QR: scanned badge is not an Operator role.")
                self._show_invalid_overlay("Only Operator role can be used as operator on client.")
                return
        self.log_last(self._scan_display_text(res, raw_s))

        if s.waiting_production_report_reason:
            code = self._extract_production_reason_code(raw_s)
            if not code:
                self.status.setText("Production Daily Report: scan valid reason QR (01-15).")
                return
            reason_map = {k: v for k, v in PRODUCTION_DAILY_REPORT_ITEMS}
            reason = reason_map.get(code)
            if not reason:
                self.status.setText("Production Daily Report: unknown reason code.")
                return
            s.waiting_production_report_reason = False
            s.downtime_reason_code = code
            s.downtime_reason_text = reason
            s.downtime_started_at = time.time()
            s.downtime_active = True
            s.maintenance_name = None
            s.supervisor_name = None
            self._set_production_overlay_mode("active")
            self._show_production_overlay()
            self.status.setText(f"Production Daily Report reason set: {code} - {reason}")
            self._refresh_ui()
            self.push_event(
                {"type": "PRODUCTION_DAILY_REPORT", "reason_code": code, "reason": reason},
                f"PRODUCTION DAILY REPORT {code} {reason}",
            )
            return

        if res is None:
            self.status.setText("Invalid scan: QR code is not recognized.")
            self._show_invalid_overlay("QR code is not recognized.")
            return

        if res.kind == "OPERATOR_SHIFT_TRIGGER":
            if not self.can_accept_production_scans():
                msg = self._missing_session_prereq_message() or "Complete session first: MACHINE -> JOB -> OPERATOR."
                self.status.setText(msg[:1].upper() + msg[1:])
                self._show_invalid_overlay(msg)
                return
            if (
                s.waiting_reject_reason
                or s.waiting_production_report_reason
                or s.waiting_cycle_time_input
                or s.waiting_maintenance_qr
                or s.waiting_supervisor_qr
                or s.waiting_operator_downtime_confirm
                or s.waiting_initial_cycle_time_input
                or s.waiting_cycle_time_confirm_popup
                or s.downtime_active
            ):
                self.status.setText("Cannot shift operator while reject/downtime flow is active.")
                self._show_invalid_overlay("Finish the active reject/downtime flow first.")
                return
            shift_payload = self._finalize_current_operator_shift("QR_SHIFT_HANDOFF", emit_event=True)
            if shift_payload is None:
                self.status.setText("Operator shift handoff failed: no active operator data.")
                self._show_invalid_overlay("No active operator shift to save.")
                return
            old_operator = self._safe_text(shift_payload.get("operator_name"), "-")
            s.operator_id = None
            s.operator_shift_started_at = None
            self._show_operator_shift_overlay(shift_payload)
            self._save_active_session_snapshot()
            self.status.setText(f"Shift data saved for {old_operator}. Scan next OPERATOR badge.")
            return

        if res.kind == "FINISH_JOB":
            if not self.can_accept_production_scans():
                self.status.setText("Cannot finish yet: complete MACHINE -> JOB -> OPERATOR first.")
                return
            if (
                s.waiting_reject_reason
                or s.waiting_production_report_reason
                or s.waiting_cycle_time_input
                or s.waiting_maintenance_qr
                or s.waiting_supervisor_qr
                or s.waiting_operator_downtime_confirm
                or s.downtime_active
            ):
                self.status.setText("Cannot finish while downtime/reject flow is active.")
                return
            self._finalize_current_operator_shift("JOB_FINISH", emit_event=True)
            finished_payload = self._build_finished_job_payload()
            if self.state.linkage_enabled and (self.state.linkage_jobs or []):
                total_jobs_in_group = 1 + len(self.state.linkage_jobs or [])
                finished_payload["linkage_role"] = "MAIN"
                finished_payload["linkage_group_total_jobs"] = total_jobs_in_group
                finished_payload["linkage_note"] = (
                    f"Main job (1 of {total_jobs_in_group}) with {len(self.state.linkage_jobs or [])} linked job(s)."
                )
            linked_finished_payloads = self._build_linked_finished_job_payloads(finished_payload)
            try:
                saved_ok = self._save_finished_job_local(finished_payload)
                for lp in linked_finished_payloads:
                    saved_ok = self._save_finished_job_local(lp) and saved_ok
            except Exception as e:
                saved_ok = False
                self.status.setText(f"Finish save failed: {e}")
            if not saved_ok:
                self.status.setText("Finish save failed: active session kept for recovery.")
                return
            self.push_event(
                {"type": "FINISH_JOB", "finished_job": finished_payload},
                f"FINISH JOB {s.job_name or s.job_code or ''}".strip(),
            )
            for lp in linked_finished_payloads:
                self.push_event(
                    {"type": "FINISH_JOB", "finished_job": lp},
                    f"FINISH LINKED JOB {lp.get('job_name') or lp.get('job_code') or ''}".strip(),
                    silent=True,
                )
            self.status.setText("Finishing job...")
            self._finish_pending_clear = True
            self._show_finish_overlay()
            return

        if res.kind == "JOB_LINKAGE_TRIGGER":
            if not self.can_accept_production_scans():
                msg = self._missing_session_prereq_message() or "Complete session first: MACHINE -> JOB -> OPERATOR."
                self.status.setText(msg[:1].upper() + msg[1:])
                self._show_invalid_overlay(msg)
                return
            if s.waiting_reject_reason or s.waiting_production_report_reason or s.downtime_active:
                self.status.setText("Cannot start linkage while reject/downtime flow is active.")
                return
            s.waiting_linkage_job_scan = True
            s.linkage_enabled = False
            s.linkage_job_code = None
            s.linkage_job_name = None
            s.linkage_job_payload = {}
            s.linkage_jobs = []
            self.status.setText("Linkage mode enabled. Scan another JOB QR to mirror current session.")
            self._refresh_ui()
            return

        if res.kind == "PRODUCTION_DAILY_REPORT_RESOLVE":
            if not s.downtime_active:
                self.status.setText("No active downtime to resolve.")
                return
            self._begin_downtime_resolution()
            self.status.setText("Downtime resolve mode: enter cycle time.")
            return

        if s.waiting_reject_reason:
            if res.kind == "REJECT_REASON":
                reason = res.value
                s.reject_total += 1
                s.reject_breakdown[reason] = s.reject_breakdown.get(reason, 0) + 1
                s.waiting_reject_reason = False
                self.status.setText(f"Reject recorded: {reason}")
                self._refresh_ui()
                self._pulse_card(self.cardStatReject)
                self.push_event({"type": "REJECT", "qty": 1, "reason": reason}, f"REJECT {reason} +1")
                return
            if res.kind == "STARTUP_REJECT":
                s.startup_reject_total += 1
                s.waiting_reject_reason = False
                self.status.setText("Start Up Reject recorded.")
                self._refresh_ui()
                self.push_event({"type": "STARTUP_REJECT", "qty": 1}, "STARTUP REJECT +1")
                return
            self.status.setText("Reject mode: scan BM01/CS02/CO03/CR04/DI05 or SUR.")
            return

        if res.kind == "STARTUP_REJECT":
            if not self.can_accept_production_scans():
                msg = self._missing_session_prereq_message() or "Complete session first: MACHINE -> JOB -> OPERATOR."
                self.status.setText(msg[:1].upper() + msg[1:])
                self._show_invalid_overlay(msg)
                return
            s.startup_reject_total += 1
            self.status.setText("Start Up Reject recorded.")
            self._refresh_ui()
            self.push_event({"type": "STARTUP_REJECT", "qty": 1}, "STARTUP REJECT +1")
            return

        if res.kind == "MACHINE":
            if s.machine_code:
                self.status.setText("Finish your current job first before changing machine.")
                self._show_invalid_overlay("Cannot change machine while current job is active.")
                return
            snap = self._load_active_session_snapshot(raw_s)
            if snap is not None and str(snap.get("job_code") or "").strip():
                self._restore_state_from_snapshot(snap)
                if not self.state.machine_name:
                    self.state.machine_name = _machine_display_name(self.state.machine_code, res.value)
                self.status.setText(
                    f"Recovered ongoing session for {self.state.machine_name} / {self.state.job_name or self.state.job_code}."
                )
                self.push_event({"type": "SESSION_RESUME"}, "SESSION RESUMED")
                self.sync_session_snapshot_to_server("SESSION SNAPSHOT SYNC (RESUME)")
                return
            s.machine_code = raw_s
            s.machine_name = _machine_display_name(s.machine_code, res.value)
            s.job_code = None
            s.job_name = None
            s.operator_id = None
            s.waiting_reject_reason = False
            s.waiting_production_report_reason = False
            s.showing_reject_summary = False
            s.reject_summary_last_scanned_at = None
            s.job_payload = {}
            s.downtime_reason_code = None
            s.downtime_reason_text = None
            s.downtime_started_at = None
            s.downtime_last_seconds = None
            s.downtime_active = False
            s.cycle_time_current = None
            s.cycle_time_confirmed_by = None
            s.waiting_initial_cycle_time_input = False
            s.waiting_initial_cycle_qc_confirm = False
            s.waiting_cycle_time_confirm_popup = False
            s.cycle_time_confirm_phase = 0
            s.cycle_time_confirm_actor_code = None
            s.cycle_time_confirm_actor_name = None
            s.cycle_time_confirm_actor_role = None
            s.maintenance_name = None
            s.supervisor_name = None
            s.raw_sacks_count = 0
            s.raw_material_scans = []
            s.raw_material_logs = []
            s.raw_material_unique_keys = set()
            s.product_pack_history_logs = []
            s.startup_reject_total = 0
            s.reject_review_logs = []
            s.waiting_linkage_job_scan = False
            s.linkage_enabled = False
            s.linkage_job_code = None
            s.linkage_job_name = None
            s.linkage_job_payload = {}
            s.linkage_jobs = []
            s.operator_shift_logs = []
            s.operator_shift_index = 0
            s.operator_shift_started_at = None
            s.operator_shift_baseline_pack_count = 0
            s.operator_shift_baseline_good_total = 0
            s.operator_shift_baseline_butal_total = 0
            s.operator_shift_baseline_reject_total = 0
            s.operator_shift_baseline_startup_reject_total = 0
            s.operator_shift_baseline_raw_sacks_count = 0
            s.operator_shift_baseline_reject_breakdown = {}
            s.operator_shift_baseline_raw_material_logs_len = 0
            s.operator_shift_baseline_product_pack_history_logs_len = 0
            s.operator_shift_baseline_reject_review_logs_len = 0
            self._reset_downtime_resolution_state()
            self._hide_resolve_overlay()
            self._hide_production_overlay()
            self._hide_raw_mats_overlay()
            self._hide_reject_summary_overlay()
            self._hide_product_history_overlay()
            self._hide_reject_review_overlay()
            self.status.setText(f"Machine set: {s.machine_name}")
            self._refresh_ui()
            self._save_active_session_snapshot()
            self.push_event({"type": "MACHINE_SET"}, f"MACHINE {s.machine_name}")
            self.sync_session_snapshot_to_server("SESSION SNAPSHOT SYNC (FIRST SCAN)")
            return

        if res.kind in ("JOB", "JOB_STUB"):
            print(f"[SCAN] Job-like scan detected kind={res.kind} raw={raw_s!r} value={res.value!r}")
            if s.waiting_linkage_job_scan:
                if not (s.machine_code and s.job_code and s.operator_id):
                    s.waiting_linkage_job_scan = False
                    self.status.setText("Linkage cancelled: complete current session first.")
                    self._refresh_ui()
                    return
                linked_job_code = ""
                linked_job_name = ""
                linked_job_payload: Dict[str, Any] = {}
                if res.kind == "JOB":
                    po_from_meta = ""
                    if isinstance(res.meta, dict):
                        po_from_meta = self._safe_text(res.meta.get("po_number"), "")
                    requested_job_id = po_from_meta or raw_s
                    fetched_linked_payload = self._fetch_job_payload_from_api(requested_job_id)
                    if isinstance(fetched_linked_payload, dict):
                        linked_job_payload = fetched_linked_payload
                        api_job = {}
                        if isinstance(fetched_linked_payload.get("data"), dict) and isinstance(fetched_linked_payload["data"].get("job"), dict):
                            api_job = fetched_linked_payload["data"]["job"]
                        elif isinstance(fetched_linked_payload.get("job"), dict):
                            api_job = fetched_linked_payload["job"]
                        linked_job_code = (
                            self._safe_text(api_job.get("id"), "")
                            or self._safe_text(api_job.get("ref_no"), "")
                            or requested_job_id
                        )
                        linked_job_name = (
                            self._safe_text(api_job.get("ref_no"), "")
                            or self._safe_text(res.value, "")
                            or requested_job_id
                        )
                    else:
                        linked_job_code = requested_job_id
                        linked_job_name = res.value
                else:
                    payload = res.meta or {}
                    linked_job_payload = payload if isinstance(payload, dict) else {}
                    job = {}
                    if isinstance(linked_job_payload.get("data"), dict) and isinstance(linked_job_payload["data"].get("job"), dict):
                        job = linked_job_payload["data"]["job"]
                    elif isinstance(linked_job_payload.get("job"), dict):
                        job = linked_job_payload["job"]
                    linked_job_code = (
                        self._safe_text(job.get("id"), "")
                        or self._safe_text(job.get("ref_no"), "")
                        or self._safe_text(linked_job_payload.get("job_code"), "")
                        or "QR-STUB"
                    )
                    linked_job_name = (
                        self._safe_text(job.get("ref_no"), "")
                        or self._safe_text(linked_job_payload.get("job_name"), "")
                        or "Job Stub"
                    )
                if self._normalize_job_code(linked_job_code) == self._normalize_job_code(s.job_code):
                    s.waiting_linkage_job_scan = False
                    self.status.setText("Linkage cancelled: linked job must be different from current job.")
                    self._show_invalid_overlay("This QR is for the current job. Scan a different linked job.")
                    self._refresh_ui()
                    return
                normalized_new = self._normalize_job_code(linked_job_code)
                if any(self._normalize_job_code(x.get("job_code")) == normalized_new for x in (s.linkage_jobs or [])):
                    self.status.setText("Linked job already added. Scan another JOB or scan PACK/BUTAL to continue.")
                    self._show_invalid_overlay("Linked job QR already scanned.")
                    self._refresh_ui()
                    return
                s.linkage_enabled = True
                s.linkage_job_code = linked_job_code
                s.linkage_job_name = linked_job_name
                s.linkage_job_payload = linked_job_payload
                s.linkage_jobs.append({
                    "job_code": linked_job_code,
                    "job_name": linked_job_name,
                    "job_payload": linked_job_payload,
                })
                self.status.setText(f"Linked job added: {linked_job_name or linked_job_code}. Scan more jobs or scan PACK/BUTAL to continue.")
                self._refresh_ui()
                self._save_active_session_snapshot()
                return
            if s.machine_code and s.job_code and s.operator_id:
                self.status.setText("Finish your current job first before changing machine or job.")
                return
            if s.machine_code and s.job_code and not s.operator_id:
                self.status.setText("Invalid scan: scan OPERATOR badge for the current job first.")
                self._show_invalid_overlay("Scan OPERATOR badge first. Job is already set.")
                return
            if not s.machine_code:
                self.status.setText("Scan MACHINE QR first.")
                self._show_invalid_overlay("Scan machine QR first.")
                return
            if res.kind == "JOB":
                po_from_meta = ""
                if isinstance(res.meta, dict):
                    po_from_meta = self._safe_text(res.meta.get("po_number"), "")
                requested_job_id = po_from_meta or raw_s
                print(f"[SCAN] JOB fetch path requested_job_id={requested_job_id!r}")
                fetched_payload = self._fetch_job_payload_from_api(requested_job_id)
                if isinstance(fetched_payload, dict):
                    s.job_payload = fetched_payload
                    api_job = self._extract_job_record()
                    s.job_code = (
                        self._safe_text(api_job.get("id"), "")
                        or self._safe_text(api_job.get("ref_no"), "")
                        or requested_job_id
                    )
                    s.job_name = (
                        self._safe_text(api_job.get("ref_no"), "")
                        or res.value
                    )
                    self.status.setText(f"Job set (API): {s.job_name}")
                else:
                    s.job_code = requested_job_id
                    s.job_name = res.value
                    s.job_payload = {}
            else:
                payload = res.meta or {}
                s.job_payload = payload
                job = self._extract_job_record()
                s.job_code = (
                    self._safe_text(job.get("id"), "")
                    or self._safe_text(job.get("ref_no"), "")
                    or self._safe_text(payload.get("job_code"), "")
                    or s.job_code
                    or "QR-STUB"
                )
                s.job_name = (
                    self._safe_text(job.get("ref_no"), "")
                    or self._safe_text(payload.get("job_name"), "")
                    or s.job_name
                    or "Job Stub"
                )
            s.operator_id = None
            s.showing_reject_summary = False
            s.waiting_production_report_reason = False
            s.reject_summary_last_scanned_at = None
            s.downtime_reason_code = None
            s.downtime_reason_text = None
            s.downtime_started_at = None
            s.downtime_last_seconds = None
            s.downtime_active = False
            s.cycle_time_current = None
            s.cycle_time_confirmed_by = None
            s.waiting_initial_cycle_time_input = False
            s.waiting_initial_cycle_qc_confirm = False
            s.waiting_cycle_time_confirm_popup = False
            s.cycle_time_confirm_phase = 0
            s.cycle_time_confirm_actor_code = None
            s.cycle_time_confirm_actor_name = None
            s.cycle_time_confirm_actor_role = None
            s.maintenance_name = None
            s.supervisor_name = None
            s.raw_sacks_count = 0
            s.raw_material_scans = []
            s.raw_material_logs = []
            s.raw_material_unique_keys = set()
            s.product_pack_history_logs = []
            s.startup_reject_total = 0
            s.reject_review_logs = []
            s.waiting_linkage_job_scan = False
            s.linkage_enabled = False
            s.linkage_job_code = None
            s.linkage_job_name = None
            s.linkage_job_payload = {}
            s.linkage_jobs = []
            s.operator_shift_logs = []
            s.operator_shift_index = 0
            s.operator_shift_started_at = None
            s.operator_shift_baseline_pack_count = 0
            s.operator_shift_baseline_good_total = 0
            s.operator_shift_baseline_butal_total = 0
            s.operator_shift_baseline_reject_total = 0
            s.operator_shift_baseline_startup_reject_total = 0
            s.operator_shift_baseline_raw_sacks_count = 0
            s.operator_shift_baseline_reject_breakdown = {}
            s.operator_shift_baseline_raw_material_logs_len = 0
            s.operator_shift_baseline_product_pack_history_logs_len = 0
            s.operator_shift_baseline_reject_review_logs_len = 0
            self._reset_downtime_resolution_state()
            self._hide_resolve_overlay()
            self._hide_production_overlay()
            self._hide_raw_mats_overlay()
            self._hide_reject_summary_overlay()
            self._hide_product_history_overlay()
            self._hide_reject_review_overlay()
            if not str(self.status.text() or "").startswith("Job set (API):"):
                self.status.setText(f"Job set: {s.job_name}")
            self._refresh_ui()
            self._save_active_session_snapshot()
            if res.kind == "JOB":
                ev = {"type": "JOB_SET"}
                if s.job_payload:
                    ev["job_payload"] = s.job_payload
                self.push_event(ev, f"JOB {s.job_name}")
            else:
                self.push_event({"type": "JOB_STUB_SET", "stub": s.job_payload}, f"JOB STUB {s.job_name}")
            return

        if res.kind == "REJECT_SUMMARY":
            if not s.machine_code or not s.job_code:
                if not s.machine_code:
                    self.status.setText("Scan MACHINE QR first.")
                    self._show_invalid_overlay("Scan machine QR first.")
                else:
                    self.status.setText("Scan JOB QR first.")
                    self._show_invalid_overlay("Scan job QR first.")
                return
            if self.rejectSummaryOverlay.isVisible():
                self._hide_reject_summary_overlay()
                s.showing_reject_summary = False
                self.status.setText("Reject summary closed.")
                self._refresh_ui()
                self._save_active_session_snapshot()
                return
            s.showing_reject_summary = True
            s.reject_summary_last_scanned_at = datetime.now(timezone.utc).isoformat()
            s.waiting_reject_reason = False
            s.waiting_production_report_reason = False
            self._hide_production_overlay()
            self._show_reject_summary_overlay()
            self.status.setText("Reject summary loaded.")
            self._refresh_ui()
            self._save_active_session_snapshot()
            self.push_event({"type": "REJECT_SUMMARY_VIEW"}, "REJECT SUMMARY")
            return

        if res.kind == "OPERATOR":
            if not s.machine_code or not s.job_code:
                if not s.machine_code:
                    self.status.setText("Scan MACHINE QR first.")
                    self._show_invalid_overlay("Scan machine QR first.")
                else:
                    self.status.setText("Scan JOB QR first.")
                    self._show_invalid_overlay("Scan job QR first.")
                return
            new_operator_code = self._operator_code_only(res.value)
            current_operator_code = self._operator_code_only(s.operator_id)
            if current_operator_code and new_operator_code != current_operator_code:
                self.status.setText('Operator change blocked. Scan "operatorshift~1" first.')
                self._show_invalid_overlay('Scan "operatorshift~1" first to save current operator shift data.')
                return
            if current_operator_code and new_operator_code == current_operator_code:
                self.status.setText(f"Operator already active: {self._operator_display_name(s.operator_id)}")
                return
            s.operator_id = res.value
            self._start_operator_shift_tracking()
            if not str(s.cycle_time_current or "").strip():
                self._begin_initial_cycle_time_setup()
                self.status.setText(f"Operator set: {s.operator_id}. Enter cycle time now.")
            else:
                self.status.setText(f"Operator set: {s.operator_id}. Job resumed.")
            self._refresh_ui()
            self._save_active_session_snapshot()
            self.push_event(
                {"type": "OPERATOR_SET", "shift_index": int(s.operator_shift_index or 0)},
                f"OPERATOR {s.operator_id}",
            )
            return

        if res.kind in ("PACK", "BUTAL", "REJECT_TRIGGER", "PRODUCTION_DAILY_REPORT_TRIGGER"):
            if not self.can_accept_production_scans():
                msg = self._missing_session_prereq_message() or "Complete session first: MACHINE -> JOB -> OPERATOR."
                self.status.setText(msg[:1].upper() + msg[1:])
                self._show_invalid_overlay(msg)
                return
            if s.waiting_linkage_job_scan:
                if s.linkage_jobs:
                    s.waiting_linkage_job_scan = False
                    s.linkage_enabled = True
                    self.status.setText(f"Linkage finalized with {len(s.linkage_jobs)} linked job(s).")
                    self._refresh_ui()
                else:
                    self.status.setText("Linkage mode active: scan at least one JOB QR first.")
                    return

            if res.kind == "PRODUCTION_DAILY_REPORT_TRIGGER":
                s.waiting_production_report_reason = True
                s.waiting_reject_reason = False
                self._set_production_overlay_mode("select")
                self._show_production_overlay()
                self.status.setText("Production Daily Report mode enabled. Scan reason QR now (01-15).")
                self._refresh_ui()
                self.push_event({"type": "PRODUCTION_DAILY_REPORT_MODE"}, "PRODUCTION DAILY REPORT MODE")
                return

            if res.kind == "REJECT_TRIGGER":
                s.waiting_reject_reason = True
                s.waiting_production_report_reason = False
                self._hide_production_overlay()
                self.status.setText("Reject mode enabled. Scan reason code now.")
                self._refresh_ui()
                self.push_event({"type": "REJECT_MODE"}, "REJECT MODE")
                return

            if res.kind == "PACK":
                scanned_job_code = self._extract_job_code_from_pack_qr(raw_s)
                current_job_code = self._normalize_job_code(s.job_code)
                if scanned_job_code is None:
                    self.status.setText("Invalid PACK QR format: missing job code segment.")
                    self._show_invalid_overlay("PACK QR format is invalid.")
                    return
                allowed_pack_job_codes = set()
                if current_job_code:
                    allowed_pack_job_codes.add(current_job_code)
                if s.linkage_enabled:
                    for row in (s.linkage_jobs or []):
                        linked_code_norm = self._normalize_job_code((row or {}).get("job_code"))
                        if linked_code_norm:
                            allowed_pack_job_codes.add(linked_code_norm)
                if allowed_pack_job_codes and scanned_job_code not in allowed_pack_job_codes:
                    self.status.setText(
                        f"Invalid PACK QR: job code {scanned_job_code} does not match main/linked job."
                    )
                    self._show_invalid_overlay("This QR is not for this job.")
                    return

                qty = int(res.qty or 0)
                pack_hist = self._extract_pack_history_fields(raw_s)
                if pack_hist is not None:
                    pack_hist["operator"] = str(s.operator_id or "").strip() or "-"
                    pack_hist["operator_name"] = self._operator_display_name(s.operator_id)
                    scan_idx = str(pack_hist.get("index") or "").strip()
                    scan_lot = str(pack_hist.get("lot_number") or "").strip()
                    if scan_idx and scan_lot:
                        for prev in (s.product_pack_history_logs or []):
                            if not isinstance(prev, dict):
                                continue
                            prev_idx = str(prev.get("index") or "").strip()
                            prev_lot = str(prev.get("lot_number") or "").strip()
                            if prev_idx == scan_idx and prev_lot == scan_lot:
                                self.status.setText(
                                    f"Invalid PACK QR: duplicate index {scan_idx} and lot {scan_lot}."
                                )
                                self._show_invalid_overlay("PACK QR index and lot number already scanned.")
                                return
                    pack_hist["scanned_at"] = datetime.now(timezone.utc).isoformat()
                    s.product_pack_history_logs.append(pack_hist)
                s.pack_count += 1
                s.good_total += qty
                self.status.setText(f"Pack +1 (Good +{qty})")
                self._refresh_ui()
                self._pulse_card(self.cardStatPack)
                self._pulse_card(self.cardStatGood)
                self._pulse_card(self.cardStatTotalGood)
                self.push_event({"type": "PACK", "qty": qty}, f"PACK +{qty}")
                return

            if res.kind == "BUTAL":
                qty = int(res.qty or 0)
                s.butal_total += qty
                self.status.setText(f"Butal +{qty}")
                self._refresh_ui()
                self._pulse_card(self.cardStatButal)
                self._pulse_card(self.cardStatTotalGood)
                self.push_event({"type": "BUTAL", "qty": qty}, f"BUTAL +{qty}")
                return

        self.status.setText(f"Scan handled: {res.kind}")
        self._refresh_ui()
    def send_heartbeat(self):
        # heartbeat carries a full session snapshot so server can recover after restart
        if self.state.machine_code:
            snapshot = self._state_to_active_snapshot()
            self.push_event(
                {"type": "HEARTBEAT", "session_snapshot": snapshot},
                "HEARTBEAT",
                silent=True,
            )

    def sync_session_snapshot_to_server(self, note: str = "SESSION SYNC"):
        if not self.state.machine_code:
            return
        snapshot = self._state_to_active_snapshot()
        self.push_event({"type": "SESSION_SYNC", "session_snapshot": snapshot}, note)

    def push_event(self, event: Dict[str, Any], last_event: str, silent: bool = False):
        s = self.state
        if not s.machine_code:
            return
        self._save_active_session_snapshot()

        payload = {
            "client_id": str(self.client_config.get("client_id", CLIENT_ID)).strip() or CLIENT_ID,
            "machine_code": s.machine_code,
            "machine_name": s.machine_name or s.machine_code,
            "job_code": s.job_code,
            "job_name": s.job_name,
            "operator_id": s.operator_id,
            "event": event,
            "last_event": last_event,
        }

        def _send():
            try:
                server_url = str(self.client_config.get("server_url", SERVER_URL)).strip().rstrip("/")
                requests.post(f"{server_url}/api/event", json=payload, timeout=3)
                if not silent:
                    pass
            except Exception as e:
                if not silent:
                    self.status.setText(f"Server send failed: {e}")

        threading.Thread(target=_send, daemon=True).start()

    def closeEvent(self, event):
        self._serial_stop.set()
        self._save_active_session_snapshot()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    w = ClientUI()
    w.setWindowState(Qt.WindowState.WindowFullScreen)
    w.showFullScreen()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()


