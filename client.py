# client.py
from __future__ import annotations
import json
import os
import re
import random
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
import threading
import time
import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Set
from PyQt6.QtWidgets import QLabel  # (already at top of file)
from PyQt6.QtCore import Qt

import requests

try:
    import pymysql
    from pymysql.cursors import DictCursor
except Exception:
    pymysql = None
    DictCursor = None

from PyQt6.QtCore import (
    Qt, QObject, QEvent, pyqtSignal, QTimer, QSize, QRectF, QPointF,
    QPropertyAnimation, QVariantAnimation, QEasingCurve, pyqtProperty, QRect,
    QParallelAnimationGroup,
    QSequentialAnimationGroup,
)
from PyQt6.QtGui import (
    QMovie, QPixmap, QColor, QPainter, QPen, QFont, QFontDatabase, QFontMetrics, QConicalGradient, QBrush,
    QLinearGradient, QRadialGradient, QPainterPath,
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame, QGridLayout, QSizePolicy,
    QGraphicsDropShadowEffect, QGraphicsBlurEffect, QGraphicsOpacityEffect, QProgressBar, QPushButton, QComboBox, QScrollArea,
    QLineEdit, QInputDialog, QTableWidget, QTableWidgetItem, QHeaderView, QStyleOptionHeader
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
PDR_ICON_DIR = os.path.join(BASE_DIR, "PDR_Icon")
DATABASE_DIR = os.path.join(BASE_DIR, "Database")
JOB_API_CONFIG_FILE = os.path.join(DATABASE_DIR, "job_api_config.json")
ACTIVE_MACHINE_SESSIONS_FILE = os.path.join(DATABASE_DIR, "active_machine_sessions.json")
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
RECORD_TYPE_SHIFT_PARTIAL = "SHIFT_PARTIAL"
RECORD_TYPE_FINAL_JOB = "FINAL_JOB"
REVIEW_STATUS_PENDING = "PENDING_SUPERVISOR"
REVIEW_STATUS_APPROVED = "APPROVED"
REVIEW_STATUS_CLOSED = "CLOSED_JOB"
TEMP_PART_QTY_PER_UNIT = 0.0848
MACHINE_BACKGROUND_IMAGE = os.path.join(IMAGES_DIR, "bgsteel.jpg")
AVERAGE_WEIGHT_API_HOST = os.environ.get("MACHINE_AVG_WEIGHT_HOST", "0.0.0.0").strip() or "0.0.0.0"
AVERAGE_WEIGHT_API_PORT = int(os.environ.get("MACHINE_AVG_WEIGHT_PORT", "5000"))
AVERAGE_WEIGHT_API_ENDPOINT = "/average-weight"


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
        print("[SQL] PyMySQL is not installed. MySQL features are unavailable.")
        return None
    cfg = _load_sql_config()
    if not cfg.get("enabled"):
        print("[SQL] SQL is disabled in configuration.")
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
    except Exception as e:
        print(f"[SQL] Connection failed: {e}")
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


def _load_active_sessions_json() -> Dict[str, Any]:
    try:
        if not os.path.exists(ACTIVE_MACHINE_SESSIONS_FILE):
            return {}
        with open(ACTIVE_MACHINE_SESSIONS_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            return {}
        out: Dict[str, Any] = {}
        for machine_code, row in loaded.items():
            code = str(machine_code or "").strip()
            if code and isinstance(row, dict):
                item = dict(row)
                item["machine_code"] = str(item.get("machine_code") or code).strip()
                out[code] = item
        return out
    except Exception:
        return {}


def _save_active_sessions_json(rows: Dict[str, Any]) -> bool:
    try:
        os.makedirs(DATABASE_DIR, exist_ok=True)
        payload: Dict[str, Any] = {}
        for machine_code, row in (rows or {}).items():
            code = str(machine_code or "").strip()
            if code and isinstance(row, dict):
                item = dict(row)
                item["machine_code"] = str(item.get("machine_code") or code).strip()
                payload[code] = item
        with open(ACTIVE_MACHINE_SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[JSON] Active session save failed: {e}")
        return False


def _upsert_active_session_json(row: Dict[str, Any]) -> bool:
    machine_code = str((row or {}).get("machine_code") or "").strip()
    if not machine_code:
        return False
    rows = _load_active_sessions_json()
    payload = dict(row or {})
    payload["machine_code"] = machine_code
    rows[machine_code] = payload
    return _save_active_sessions_json(rows)


def _delete_active_session_json(machine_code: Optional[str]) -> bool:
    code = str(machine_code or "").strip()
    if not code:
        return False
    rows = _load_active_sessions_json()
    if code in rows:
        rows.pop(code, None)
        return _save_active_sessions_json(rows)
    return True


def _sync_active_sessions_json_to_sql() -> bool:
    rows = _load_active_sessions_json()
    ok = True
    for machine_code, row in rows.items():
        if not isinstance(row, dict):
            continue
        payload = dict(row)
        payload["machine_code"] = str(payload.get("machine_code") or machine_code or "").strip()
        if not payload["machine_code"]:
            ok = False
            continue
        ok = _upsert_active_session_sql(payload) and ok
    return ok


def _upsert_active_session_sql(row: Dict[str, Any]) -> bool:
    machine_code = str((row or {}).get("machine_code") or "").strip()
    if not machine_code:
        print("[SQL] Active session save skipped: empty machine_code.")
        return False
    conn = _sql_conn()
    if conn is None:
        print(f"[SQL] Active session save failed for {machine_code}: no SQL connection.")
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO `active_machine_sessions`
                (`machine_code`,`saved_at_utc`,`machine_name`,`job_code`,`job_name`,`operator_id`,
                 `pack_count`,`good_total`,`butal_total`,`reject_total`,`reject_breakdown`,
                 `waiting_reject_reason`,`waiting_production_report_reason`,`showing_reject_summary`,`reject_summary_last_scanned_at`,
                 `job_payload`,`downtime_reason_code`,`downtime_reason_text`,`downtime_started_at`,`downtime_last_seconds`,`downtime_active`,
                 `cycle_time_current`,`cycle_time_new_input`,`waiting_cycle_time_input`,`waiting_initial_cycle_time_input`,
                 `waiting_initial_cycle_qc_confirm`,`waiting_cycle_time_confirm_popup`,`cycle_time_confirm_phase`,
                 `cycle_time_confirmed_by`,`cycle_time_confirm_actor_code`,`cycle_time_confirm_actor_name`,`cycle_time_confirm_actor_role`,
                 `waiting_maintenance_qr`,`waiting_supervisor_qr`,`waiting_operator_downtime_confirm`,`maintenance_name`,`supervisor_name`,
                 `raw_sacks_count`,`raw_material_scans`,`raw_material_logs`,`raw_material_unique_keys`,`product_pack_history_logs`,
                 `startup_reject_total`,`reject_review_open`,`reject_review_phase`,`reject_review_actor_code`,`reject_review_actor_name`,
                 `reject_review_actor_role`,`reject_review_logs`,`waiting_linkage_job_scan`,`linkage_enabled`,`linkage_job_code`,
                 `linkage_job_name`,`linkage_job_payload`,`linkage_jobs`,`operator_shift_logs`,`operator_shift_index`,
                 `operator_shift_started_at`,`operator_shift_baseline_pack_count`,`operator_shift_baseline_good_total`,
                 `operator_shift_baseline_butal_total`,`operator_shift_baseline_reject_total`,`operator_shift_baseline_startup_reject_total`,
                 `operator_shift_baseline_raw_sacks_count`,`operator_shift_baseline_reject_breakdown`,
                 `operator_shift_baseline_raw_material_logs_len`,`operator_shift_baseline_product_pack_history_logs_len`,
                 `operator_shift_baseline_reject_review_logs_len`,`raw_json`)
                VALUES (%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,CAST(%s AS JSON),
                        %s,%s,%s,%s,
                        CAST(%s AS JSON),%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,
                        %s,%s,%s,
                        %s,%s,%s,%s,
                        %s,%s,%s,%s,%s,
                        %s,CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),
                        %s,%s,%s,%s,%s,
                        %s,CAST(%s AS JSON),%s,%s,%s,
                        %s,CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),%s,
                        %s,%s,%s,
                        %s,%s,%s,
                        %s,CAST(%s AS JSON),
                        %s,%s,
                        %s,CAST(%s AS JSON))
                ON DUPLICATE KEY UPDATE
                  `saved_at_utc`=VALUES(`saved_at_utc`),
                  `machine_name`=VALUES(`machine_name`),
                  `job_code`=VALUES(`job_code`),
                  `job_name`=VALUES(`job_name`),
                  `operator_id`=VALUES(`operator_id`),
                  `pack_count`=VALUES(`pack_count`),
                  `good_total`=VALUES(`good_total`),
                  `butal_total`=VALUES(`butal_total`),
                  `reject_total`=VALUES(`reject_total`),
                  `reject_breakdown`=VALUES(`reject_breakdown`),
                  `waiting_reject_reason`=VALUES(`waiting_reject_reason`),
                  `waiting_production_report_reason`=VALUES(`waiting_production_report_reason`),
                  `showing_reject_summary`=VALUES(`showing_reject_summary`),
                  `reject_summary_last_scanned_at`=VALUES(`reject_summary_last_scanned_at`),
                  `job_payload`=VALUES(`job_payload`),
                  `downtime_reason_code`=VALUES(`downtime_reason_code`),
                  `downtime_reason_text`=VALUES(`downtime_reason_text`),
                  `downtime_started_at`=VALUES(`downtime_started_at`),
                  `downtime_last_seconds`=VALUES(`downtime_last_seconds`),
                  `downtime_active`=VALUES(`downtime_active`),
                  `cycle_time_current`=VALUES(`cycle_time_current`),
                  `cycle_time_new_input`=VALUES(`cycle_time_new_input`),
                  `waiting_cycle_time_input`=VALUES(`waiting_cycle_time_input`),
                  `waiting_initial_cycle_time_input`=VALUES(`waiting_initial_cycle_time_input`),
                  `waiting_initial_cycle_qc_confirm`=VALUES(`waiting_initial_cycle_qc_confirm`),
                  `waiting_cycle_time_confirm_popup`=VALUES(`waiting_cycle_time_confirm_popup`),
                  `cycle_time_confirm_phase`=VALUES(`cycle_time_confirm_phase`),
                  `cycle_time_confirmed_by`=VALUES(`cycle_time_confirmed_by`),
                  `cycle_time_confirm_actor_code`=VALUES(`cycle_time_confirm_actor_code`),
                  `cycle_time_confirm_actor_name`=VALUES(`cycle_time_confirm_actor_name`),
                  `cycle_time_confirm_actor_role`=VALUES(`cycle_time_confirm_actor_role`),
                  `waiting_maintenance_qr`=VALUES(`waiting_maintenance_qr`),
                  `waiting_supervisor_qr`=VALUES(`waiting_supervisor_qr`),
                  `waiting_operator_downtime_confirm`=VALUES(`waiting_operator_downtime_confirm`),
                  `maintenance_name`=VALUES(`maintenance_name`),
                  `supervisor_name`=VALUES(`supervisor_name`),
                  `raw_sacks_count`=VALUES(`raw_sacks_count`),
                  `raw_material_scans`=VALUES(`raw_material_scans`),
                  `raw_material_logs`=VALUES(`raw_material_logs`),
                  `raw_material_unique_keys`=VALUES(`raw_material_unique_keys`),
                  `product_pack_history_logs`=VALUES(`product_pack_history_logs`),
                  `startup_reject_total`=VALUES(`startup_reject_total`),
                  `reject_review_open`=VALUES(`reject_review_open`),
                  `reject_review_phase`=VALUES(`reject_review_phase`),
                  `reject_review_actor_code`=VALUES(`reject_review_actor_code`),
                  `reject_review_actor_name`=VALUES(`reject_review_actor_name`),
                  `reject_review_actor_role`=VALUES(`reject_review_actor_role`),
                  `reject_review_logs`=VALUES(`reject_review_logs`),
                  `waiting_linkage_job_scan`=VALUES(`waiting_linkage_job_scan`),
                  `linkage_enabled`=VALUES(`linkage_enabled`),
                  `linkage_job_code`=VALUES(`linkage_job_code`),
                  `linkage_job_name`=VALUES(`linkage_job_name`),
                  `linkage_job_payload`=VALUES(`linkage_job_payload`),
                  `linkage_jobs`=VALUES(`linkage_jobs`),
                  `operator_shift_logs`=VALUES(`operator_shift_logs`),
                  `operator_shift_index`=VALUES(`operator_shift_index`),
                  `operator_shift_started_at`=VALUES(`operator_shift_started_at`),
                  `operator_shift_baseline_pack_count`=VALUES(`operator_shift_baseline_pack_count`),
                  `operator_shift_baseline_good_total`=VALUES(`operator_shift_baseline_good_total`),
                  `operator_shift_baseline_butal_total`=VALUES(`operator_shift_baseline_butal_total`),
                  `operator_shift_baseline_reject_total`=VALUES(`operator_shift_baseline_reject_total`),
                  `operator_shift_baseline_startup_reject_total`=VALUES(`operator_shift_baseline_startup_reject_total`),
                  `operator_shift_baseline_raw_sacks_count`=VALUES(`operator_shift_baseline_raw_sacks_count`),
                  `operator_shift_baseline_reject_breakdown`=VALUES(`operator_shift_baseline_reject_breakdown`),
                  `operator_shift_baseline_raw_material_logs_len`=VALUES(`operator_shift_baseline_raw_material_logs_len`),
                  `operator_shift_baseline_product_pack_history_logs_len`=VALUES(`operator_shift_baseline_product_pack_history_logs_len`),
                  `operator_shift_baseline_reject_review_logs_len`=VALUES(`operator_shift_baseline_reject_review_logs_len`),
                  `raw_json`=VALUES(`raw_json`)
                """,
                (
                    machine_code,
                    row.get("saved_at_utc"),
                    row.get("machine_name"),
                    row.get("job_code"),
                    row.get("job_name"),
                    row.get("operator_id"),
                    int(row.get("pack_count", 0) or 0),
                    int(row.get("good_total", 0) or 0),
                    int(row.get("butal_total", 0) or 0),
                    int(row.get("reject_total", 0) or 0),
                    json.dumps(row.get("reject_breakdown", {}), ensure_ascii=False),
                    1 if row.get("waiting_reject_reason") else 0,
                    1 if row.get("waiting_production_report_reason") else 0,
                    1 if row.get("showing_reject_summary") else 0,
                    row.get("reject_summary_last_scanned_at"),
                    json.dumps(row.get("job_payload", {}), ensure_ascii=False),
                    row.get("downtime_reason_code"),
                    row.get("downtime_reason_text"),
                    row.get("downtime_started_at"),
                    row.get("downtime_last_seconds"),
                    1 if row.get("downtime_active") else 0,
                    row.get("cycle_time_current"),
                    row.get("cycle_time_new_input"),
                    1 if row.get("waiting_cycle_time_input") else 0,
                    1 if row.get("waiting_initial_cycle_time_input") else 0,
                    1 if row.get("waiting_initial_cycle_qc_confirm") else 0,
                    1 if row.get("waiting_cycle_time_confirm_popup") else 0,
                    int(row.get("cycle_time_confirm_phase", 0) or 0),
                    row.get("cycle_time_confirmed_by"),
                    row.get("cycle_time_confirm_actor_code"),
                    row.get("cycle_time_confirm_actor_name"),
                    row.get("cycle_time_confirm_actor_role"),
                    1 if row.get("waiting_maintenance_qr") else 0,
                    1 if row.get("waiting_supervisor_qr") else 0,
                    1 if row.get("waiting_operator_downtime_confirm") else 0,
                    row.get("maintenance_name"),
                    row.get("supervisor_name"),
                    int(row.get("raw_sacks_count", 0) or 0),
                    json.dumps(row.get("raw_material_scans", []), ensure_ascii=False),
                    json.dumps(row.get("raw_material_logs", []), ensure_ascii=False),
                    json.dumps(row.get("raw_material_unique_keys", []), ensure_ascii=False),
                    json.dumps(row.get("product_pack_history_logs", []), ensure_ascii=False),
                    int(row.get("startup_reject_total", 0) or 0),
                    1 if row.get("reject_review_open") else 0,
                    int(row.get("reject_review_phase", 0) or 0),
                    row.get("reject_review_actor_code"),
                    row.get("reject_review_actor_name"),
                    row.get("reject_review_actor_role"),
                    json.dumps(row.get("reject_review_logs", []), ensure_ascii=False),
                    1 if row.get("waiting_linkage_job_scan") else 0,
                    1 if row.get("linkage_enabled") else 0,
                    row.get("linkage_job_code"),
                    row.get("linkage_job_name"),
                    json.dumps(row.get("linkage_job_payload", {}), ensure_ascii=False),
                    json.dumps(row.get("linkage_jobs", []), ensure_ascii=False),
                    json.dumps(row.get("operator_shift_logs", []), ensure_ascii=False),
                    int(row.get("operator_shift_index", 0) or 0),
                    row.get("operator_shift_started_at"),
                    int(row.get("operator_shift_baseline_pack_count", 0) or 0),
                    int(row.get("operator_shift_baseline_good_total", 0) or 0),
                    int(row.get("operator_shift_baseline_butal_total", 0) or 0),
                    int(row.get("operator_shift_baseline_reject_total", 0) or 0),
                    int(row.get("operator_shift_baseline_startup_reject_total", 0) or 0),
                    int(row.get("operator_shift_baseline_raw_sacks_count", 0) or 0),
                    json.dumps(row.get("operator_shift_baseline_reject_breakdown", {}), ensure_ascii=False),
                    int(row.get("operator_shift_baseline_raw_material_logs_len", 0) or 0),
                    int(row.get("operator_shift_baseline_product_pack_history_logs_len", 0) or 0),
                    int(row.get("operator_shift_baseline_reject_review_logs_len", 0) or 0),
                    json.dumps(row, ensure_ascii=False),
                ),
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"[SQL] Active session save failed for {machine_code}: {e}")
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
    legacy_path = ACTIVE_MACHINE_SESSIONS_FILE
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


def _load_finished_jobs_sql() -> List[Dict[str, Any]]:
    conn = _sql_conn()
    if conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT `raw_json` FROM `finished_jobs` ORDER BY `id` ASC")
            rows = cur.fetchall() or []
        out: List[Dict[str, Any]] = []
        for row in rows:
            raw = row.get("raw_json") if isinstance(row, dict) else None
            try:
                item = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                item = None
            if isinstance(item, dict):
                out.append(item)
        return out
    except Exception:
        return []
    finally:
        conn.close()


def _replace_finished_jobs_sql(rows: List[Dict[str, Any]]) -> bool:
    conn = _sql_conn()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM `finished_jobs`")
        conn.commit()
        ok = True
        for row in rows:
            if not isinstance(row, dict):
                continue
            ok = _insert_finished_job_sql(row) and ok
        return ok
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
        "graphics_mode": "quality",
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
    mode = str(defaults.get("graphics_mode", "quality")).strip().lower().replace(" ", "_")
    if mode in ("fast",):
        mode = "faster"
    if mode in ("faster+quality", "faster_quality", "balanced"):
        mode = "faster_quality"
    if mode not in ("faster", "faster_quality", "quality"):
        mode = "quality"
    defaults["graphics_mode"] = mode
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

PDR_REASON_ICON_FILES = {
    "01": "breakdown.png",
    "02": "machineadjustment.png",
    "03": "Materialissue.png",
    "04": "moldissue.png",
    "05": "nomanpower.png",
    "06": "materialcolorchange.png",
    "07": "item.png",
    "08": "preventivemaintenance.png",
    "09": "noschedule.png",
    "10": "startup.png",
    "11": "turnover.png",
    "12": "colortesting.png",
    "13": "powerinterruption.png",
    "14": "robotsetup.png",
    "15": "others.png",
}


@dataclass
class ClientState:
    machine_code: Optional[str] = None
    machine_name: Optional[str] = None
    job_code: Optional[str] = None
    job_name: Optional[str] = None
    job_started_at: Optional[str] = None
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
    downtime_wait_started_at: Optional[float] = None
    downtime_wait_last_seconds: Optional[int] = None
    waiting_downtime_start_maintenance: bool = False
    waiting_downtime_end_maintenance: bool = False
    downtime_resolution_started_at: Optional[float] = None
    maintenance_downtime_seconds: Optional[int] = None
    supervisor_downtime_confirmation_started_at: Optional[float] = None
    supervisor_downtime_confirmation_seconds: Optional[int] = None
    operator_downtime_confirmation_started_at: Optional[float] = None
    operator_downtime_confirmation_seconds: Optional[int] = None
    cycle_time_current: Optional[str] = None
    cycle_time_change_logs: List[Dict[str, Any]] = None
    cycle_time_new_input: str = ""
    cycle_time_confirmed_by: Optional[str] = None
    cycle_time_confirm_actor_code: Optional[str] = None
    cycle_time_confirm_actor_name: Optional[str] = None
    cycle_time_confirm_actor_role: Optional[str] = None
    live_cycle_last_scan_at: Optional[float] = None
    live_cycle_total_seconds: float = 0.0
    live_cycle_intervals: int = 0
    live_cycle_total_units: int = 0
    live_cycle_avg_seconds: Optional[float] = None
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
    operator_shift_baseline_cycle_time: Optional[str] = None
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
    external_average_weight_grams: Optional[float] = None
    external_average_weight_unit: Optional[str] = None
    external_average_weight_received_at: Optional[str] = None

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
        if self.cycle_time_change_logs is None:
            self.cycle_time_change_logs = []
        if self.operator_shift_baseline_reject_breakdown is None:
            self.operator_shift_baseline_reject_breakdown = {}


@dataclass
class StatusPulse:
    age: float


@dataclass
class FloatingText:
    text: str
    x: float
    y: float
    start_y: float
    age: float = 0.0
    duration: float = 1.4


class CounterCard(QWidget):
    def __init__(self, title: str, theme: str = "green"):
        super().__init__()
        self.title = title
        self.theme = str(theme or "green").lower()
        self._value = 0
        self._display_value = 0.0
        self._glow = 0.0
        self._scale = 0.0
        self._flash = 0.0
        self._floating: List[FloatingText] = []
        self._animations_enabled = True

        self.setMinimumSize(128, 78)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

        self.num_anim = QVariantAnimation(self)
        self.num_anim.setDuration(500)
        self.num_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.num_anim.valueChanged.connect(self._num_update)

        self.glow_anim = QPropertyAnimation(self, b"glow", self)
        self.glow_anim.setDuration(1300)
        self.glow_anim.setStartValue(0.0)
        self.glow_anim.setKeyValueAt(0.5, 1.0)
        self.glow_anim.setEndValue(0.0)
        self.glow_anim.setEasingCurve(QEasingCurve.Type.InOutSine)

        self.scale_anim = QPropertyAnimation(self, b"scale", self)
        self.scale_anim.setDuration(1100)
        self.scale_anim.setStartValue(0.0)
        self.scale_anim.setKeyValueAt(0.4, 1.0)
        self.scale_anim.setEndValue(0.0)
        self.scale_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.flash_anim = QPropertyAnimation(self, b"flash", self)
        self.flash_anim.setDuration(900)
        self.flash_anim.setStartValue(0.0)
        self.flash_anim.setKeyValueAt(0.3, 1.0)
        self.flash_anim.setEndValue(0.0)
        self.flash_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def getGlow(self):
        return self._glow

    def setGlow(self, value):
        self._glow = float(value)
        self.update()

    glow = pyqtProperty(float, fget=getGlow, fset=setGlow)

    def getScale(self):
        return self._scale

    def setScale(self, value):
        self._scale = float(value)
        self.update()

    scale = pyqtProperty(float, fget=getScale, fset=setScale)

    def getFlash(self):
        return self._flash

    def setFlash(self, value):
        self._flash = float(value)
        self.update()

    flash = pyqtProperty(float, fget=getFlash, fset=setFlash)

    def add_points(self, val: int):
        delta = int(val or 0)
        if delta <= 0:
            return
        old_value = self._value
        self._value += delta

        if not self._animations_enabled:
            self._display_value = float(self._value)
            self.update()
            return

        self.num_anim.stop()
        self.num_anim.setStartValue(float(old_value))
        self.num_anim.setEndValue(float(self._value))
        self.num_anim.start()

        self.glow_anim.stop()
        self.glow_anim.start()
        self.scale_anim.stop()
        self.scale_anim.start()
        self.flash_anim.stop()
        self.flash_anim.start()

        self._floating.append(
            FloatingText(
                text=f"+{delta}",
                x=self.width() * 0.72,
                y=self.height() * 0.42,
                start_y=self.height() * 0.42,
            )
        )

    def set_value(self, value: int):
        self._value = max(0, int(value))
        self._display_value = float(self._value)
        self.update()

    def _num_update(self, value):
        self._display_value = float(value)
        self.update()

    def _tick(self):
        if not self._animations_enabled:
            if self._floating:
                self._floating = []
                self.update()
            return
        kept = []
        dt = 0.016
        for f in self._floating:
            f.age += dt
            t = min(1.0, f.age / f.duration)
            eased = 1.0 - (1.0 - t) * (1.0 - t)
            f.y = f.start_y - 40 * eased
            if t < 1.0:
                kept.append(f)
        self._floating = kept
        if kept:
            self.update()

    def colors(self):
        if self.theme == "red":
            return {
                "base": QColor(190, 20, 20),
                "dark": QColor(140, 10, 10),
                "glow": QColor(255, 120, 120),
                "border": QColor(255, 140, 140),
                "title": QColor(255, 245, 245),
                "value": QColor(255, 235, 235),
                "flash": QColor(255, 255, 255),
                "float": QColor(255, 240, 240),
            }
        return {
            "base": QColor(26, 132, 62),
            "dark": QColor(12, 95, 42),
            "glow": QColor(120, 255, 180),
            "border": QColor(72, 255, 170),
            "title": QColor(245, 245, 245),
            "value": QColor(180, 255, 210),
            "flash": QColor(255, 255, 255),
            "float": QColor(230, 255, 238),
        }

    def paintEvent(self, event):
        c = self.colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        rect = QRectF(5, 5, self.width() - 10, self.height() - 10)
        radius = 20.0

        scale_factor = 1.0 + self._scale * 0.06
        painter.translate(rect.center())
        painter.scale(scale_factor, scale_factor)
        painter.translate(-rect.center())

        self._draw_glow(painter, rect, radius, c)
        self._draw_shadow(painter, rect, radius)
        self._draw_body(painter, rect, radius, c)
        self._draw_flash(painter, rect, radius, c)
        self._draw_title(painter, rect, c)
        self._draw_value(painter, rect, c)
        self._draw_floating_text(painter, c)
        painter.end()

    def _draw_glow(self, painter: QPainter, rect: QRectF, radius: float, c: dict):
        if self._glow <= 0.001:
            return
        for i in range(12):
            alpha = max(0, int(125 * self._glow) - i * 10)
            if alpha <= 0:
                continue
            expand = i * 2.0
            painter.setPen(QPen(QColor(c["glow"].red(), c["glow"].green(), c["glow"].blue(), alpha), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(-expand, -expand, expand, expand), radius + expand, radius + expand)

    def _draw_shadow(self, painter: QPainter, rect: QRectF, radius: float):
        shadow_color = QColor(0, 0, 0, 90)
        for i in range(4):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(shadow_color.red(), shadow_color.green(), shadow_color.blue(), 30 - i * 6))
            painter.drawRoundedRect(rect.adjusted(i + 1, i + 3, i + 1, i + 3), radius, radius)

    def _draw_body(self, painter: QPainter, rect: QRectF, radius: float, c: dict):
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, c["base"])
        grad.setColorAt(1.0, c["dark"])
        painter.setPen(QPen(c["border"], 1.5))
        painter.setBrush(grad)
        painter.drawRoundedRect(rect, radius, radius)

        highlight = QRectF(rect.left() + 2, rect.top() + 2, rect.width() - 4, rect.height() * 0.42)
        highlight_grad = QLinearGradient(highlight.topLeft(), highlight.bottomLeft())
        highlight_grad.setColorAt(0.0, QColor(255, 255, 255, 42))
        highlight_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(highlight_grad)
        painter.drawRoundedRect(highlight, radius - 2, radius - 2)

    def _draw_flash(self, painter: QPainter, rect: QRectF, radius: float, c: dict):
        if self._flash <= 0.001:
            return
        rg = QRadialGradient(rect.center(), rect.width() / 1.5)
        rg.setColorAt(0.0, QColor(c["flash"].red(), c["flash"].green(), c["flash"].blue(), int(165 * self._flash)))
        rg.setColorAt(0.45, QColor(c["flash"].red(), c["flash"].green(), c["flash"].blue(), int(70 * self._flash)))
        rg.setColorAt(1.0, QColor(c["flash"].red(), c["flash"].green(), c["flash"].blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(rg)
        painter.drawRoundedRect(rect, radius, radius)

    def _draw_title(self, painter: QPainter, rect: QRectF, c: dict):
        title_px = max(10, min(16, int(rect.height() * 0.17)))
        font = QFont("Segoe UI", title_px, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        painter.setFont(font)
        painter.setPen(c["title"])
        title_rect = QRectF(rect.left(), rect.top() + max(4, int(rect.height() * 0.06)), rect.width(), max(18, int(rect.height() * 0.22)))
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, self.title)

    def _draw_value(self, painter: QPainter, rect: QRectF, c: dict):
        text = str(int(round(self._display_value)))
        value_rect = QRectF(rect.left(), rect.top() + max(18, int(rect.height() * 0.24)), rect.width(), rect.height() - max(20, int(rect.height() * 0.22)))
        glow_alpha = int(170 + 85 * self._glow)
        value_px = max(22, min(40, int(rect.height() * 0.36)))
        painter.setFont(QFont("Consolas", value_px, QFont.Weight.Bold))
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (0, 0)]:
            painter.setPen(QColor(c["glow"].red(), c["glow"].green(), c["glow"].blue(), min(255, glow_alpha)))
            painter.drawText(value_rect.translated(dx, dy), Qt.AlignmentFlag.AlignCenter, text)
        painter.setPen(c["value"])
        painter.drawText(value_rect, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_floating_text(self, painter: QPainter, c: dict):
        if not self._floating:
            return
        painter.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        for f in self._floating:
            t = min(1.0, f.age / f.duration)
            alpha = int(255 * (1.0 - t))
            painter.setPen(QColor(c["float"].red(), c["float"].green(), c["float"].blue(), alpha))
            painter.drawText(QPointF(f.x, f.y), f.text)

    def set_animations_enabled(self, enabled: bool):
        self._animations_enabled = bool(enabled)
        if not self._animations_enabled:
            self.num_anim.stop()
            self.glow_anim.stop()
            self.scale_anim.stop()
            self.flash_anim.stop()
            self._floating = []
            self._glow = 0.0
            self._scale = 0.0
            self._flash = 0.0
            self._display_value = float(self._value)
        self.update()


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


class FailureCross(QWidget):
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

        pen = QPen(QColor(220, 38, 38))
        pen.setWidth(int(min(w, h) * 0.07))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        circle_phase = min(self._progress / 0.65, 1.0)
        cross_phase = 0.0 if self._progress < 0.65 else min((self._progress - 0.65) / 0.35, 1.0)

        start_angle = int(270 * 16)
        span_angle = int(-360 * 16 * circle_phase)
        painter.drawArc(rect, start_angle, span_angle)

        if cross_phase > 0:
            x0 = rect.left()
            y0 = rect.top()
            rw = rect.width()
            rh = rect.height()

            a = (x0 + 0.34 * rw, y0 + 0.34 * rh)
            b = (x0 + 0.66 * rw, y0 + 0.66 * rh)
            c = (x0 + 0.66 * rw, y0 + 0.34 * rh)
            d = (x0 + 0.34 * rw, y0 + 0.66 * rh)

            if cross_phase <= 0.5:
                t = cross_phase / 0.5
                bx = a[0] + (b[0] - a[0]) * t
                by = a[1] + (b[1] - a[1]) * t
                painter.drawLine(int(a[0]), int(a[1]), int(bx), int(by))
            else:
                painter.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))
                t = (cross_phase - 0.5) / 0.5
                dx = c[0] + (d[0] - c[0]) * t
                dy = c[1] + (d[1] - c[1]) * t
                painter.drawLine(int(c[0]), int(c[1]), int(dx), int(dy))


class GraphicsModeToggle(QFrame):
    modeChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._modes = ["faster", "faster_quality", "quality"]
        self._labels = {
            "faster": "Fastest",
            "faster_quality": "Balanced",
            "quality": "Best Looking",
        }
        self._mode = "quality"
        self.setObjectName("GraphicsModeToggle")
        self.setFixedSize(420, 52)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("QFrame#GraphicsModeToggle { background: transparent; border: none; }")
        self._dot = QFrame(self)
        self._dot.setObjectName("GraphicsModeDot")
        self._dot.setStyleSheet(
            "QFrame#GraphicsModeDot {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                              stop:0 rgba(240,232,212,255),"
            "                              stop:1 rgba(190,180,160,255));"
            " border: 1px solid rgba(60,60,55,230);"
            " border-radius: 3px;"
            "}"
        )
        self._dot.resize(14, 18)
        self._dot_anim = QPropertyAnimation(self._dot, b"geometry", self)
        self._dot_anim.setDuration(180)
        self._dot_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.set_mode(self._mode, emit_signal=False, animate=False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._move_dot(self._mode, animate=False)

    def _track_rect(self) -> QRectF:
        return QRectF(4.0, 8.0, float(self.width() - 8), 12.0)

    def _dot_rect_for_mode(self, mode: str) -> QRect:
        track = self._track_rect()
        idx = self._modes.index(mode) if mode in self._modes else 2
        centers = [
            int(track.left() + 8),
            int(track.left() + (track.width() / 2.0)),
            int(track.right() - 8),
        ]
        size = self._dot.size()
        return QRect(centers[idx] - (size.width() // 2), int(track.top() - 3), size.width(), size.height())

    def _move_dot(self, mode: str, animate: bool):
        target = self._dot_rect_for_mode(mode)
        if animate:
            self._dot_anim.stop()
            self._dot_anim.setStartValue(self._dot.geometry())
            self._dot_anim.setEndValue(target)
            self._dot_anim.start()
        else:
            self._dot.setGeometry(target)
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        x = float(event.position().x())
        w = float(self.width())
        if x < w / 3.0:
            mode = "faster"
        elif x < (w * 2.0 / 3.0):
            mode = "faster_quality"
        else:
            mode = "quality"
        self.set_mode(mode, emit_signal=True)
        event.accept()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        track = self._track_rect()
        p.setPen(QPen(QColor(203, 213, 200, 220), 1.4))
        p.setBrush(QColor(40, 46, 44, 70))
        p.drawRoundedRect(track, 2.0, 2.0)

        tick_y1 = track.bottom() + 1.0
        tick_y2 = tick_y1 + 7.0
        tick_xs = [track.left(), track.left() + (track.width() / 3.0), track.left() + ((track.width() * 2.0) / 3.0), track.right()]
        for x in tick_xs:
            p.drawLine(QPointF(x, tick_y1), QPointF(x, tick_y2))

        font = QFont("Consolas", 9, QFont.Weight.Bold)
        p.setFont(font)
        for idx, mode in enumerate(self._modes):
            left = tick_xs[idx]
            right = tick_xs[idx + 1]
            rect = QRectF(left - 2.0, tick_y2 + 3.0, (right - left) + 4.0, 16.0)
            active = mode == self._mode
            p.setPen(QColor("#f8fafc") if active else QColor(189, 194, 184))
            if idx == 0:
                flags = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            elif idx == 2:
                flags = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            else:
                flags = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
            p.drawText(rect, flags, self._labels[mode])
        p.end()

    def set_mode(self, mode: str, *, emit_signal: bool = False, animate: bool = True):
        key = str(mode or "quality").strip().lower()
        if key not in self._modes:
            key = "quality"
        self._mode = key
        self._move_dot(key, animate=animate)
        if emit_signal:
            self.modeChanged.emit(key)

    def mode(self) -> str:
        return self._mode


class CircleProgressBadge(QWidget):
    def __init__(self, accent: QColor, parent=None):
        super().__init__(parent)
        self._accent = QColor(accent)
        self._progress = 0.0
        self._value_text = "0"
        self._phase = 0.0
        self._comet_pos = 0.0
        self._demo_mode = False
        self._demo_value = 90
        self._maximum = 100
        self._segment_count = 35
        self._start_angle = -90.0
        self._animations_enabled = True
        self.setMinimumSize(98, 98)
        self.setMaximumSize(118, 118)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self._anim = QTimer(self)
        self._anim.setInterval(15)
        self._anim.timeout.connect(self._tick)
        self._anim.start()

    def set_progress(self, value: float):
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    def set_value_text(self, text: str):
        self._value_text = str(text or "0")
        self.update()

    def _tick(self):
        if not self._animations_enabled:
            return
        self._phase = (self._phase + 0.08) % (math.pi * 2.0)
        active = max(0, min(self._segment_count, round((self._demo_value / self._maximum) * self._segment_count)))
        if active > 0:
            self._comet_pos = (self._comet_pos + 0.18) % float(self._segment_count)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        radius = min(w, h) * 0.32
        value_pct = float(self._demo_value) if self._demo_mode else max(0.0, min(100.0, self._progress * 100.0))
        active = max(0, min(self._segment_count, round((value_pct / self._maximum) * self._segment_count)))
        if (not self._demo_mode) and self._progress > 0 and active == 0:
            active = 1
        angle_step = 360.0 / self._segment_count

        # Background aura removed; keep only ring/tick animation.

        for i in range(self._segment_count):
            ang_deg = self._start_angle + i * angle_step
            ang = math.radians(ang_deg)
            inner_r = radius
            outer_r = radius + 8
            x1 = cx + math.cos(ang) * inner_r
            y1 = cy + math.sin(ang) * inner_r
            x2 = cx + math.cos(ang) * outer_r
            y2 = cy + math.sin(ang) * outer_r

            if i < active:
                d = abs(i - self._comet_pos)
                d = min(d, float(self._segment_count) - d)
                trail = max(0.0, 1.0 - d / 8.0)
                base_brightness = 195
                extra = int(60 * trail)
                g = min(255, base_brightness + extra)
                glow_w1 = 7.0 + 3.0 * trail
                glow_w2 = 4.8 + 2.0 * trail
                core_w = 2.2 + 0.9 * trail
                alpha1 = int(16 + 36 * trail)
                alpha2 = int(28 + 62 * trail)

                p.setPen(QPen(QColor(0, 255, 70, alpha1), glow_w1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
                p.setPen(QPen(QColor(0, 255, 70, alpha2), glow_w2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
                if d < 0.8:
                    p.setPen(QPen(QColor(180, 255, 190, 125), 6.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
                p.setPen(QPen(QColor(20, g, 60), core_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            else:
                p.setPen(QPen(QColor(238, 241, 245, 95), 1.9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        number_font = QFont("DS-Digital", max(12, int(min(w, h) * 0.10)), QFont.Weight.Bold)
        if "DS-Digital" not in number_font.family():
            number_font = QFont("Consolas", max(12, int(min(w, h) * 0.10)), QFont.Weight.Bold)
        draw_rect = self.rect()
        p.setFont(number_font)
        text_rect = draw_rect.adjusted(0, -6, 0, 0)
        if self._demo_mode:
            val_text = f"{int(round(value_pct))}%"
        else:
            val_text = f"{value_pct:.1f}%" if (0.0 < value_pct < 1.0) else f"{int(round(value_pct))}%"
        p.setPen(QColor("#f3f4f6"))
        p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, val_text)
        p.end()

    def set_animations_enabled(self, enabled: bool):
        self._animations_enabled = bool(enabled)
        if self._animations_enabled:
            if not self._anim.isActive():
                self._anim.start()
        else:
            self._anim.stop()
            self._phase = 0.0
            self._comet_pos = 0.0
        self.update()


@dataclass
class Spark:
    x: float
    y: float
    dx: float
    dy: float
    life: float


@dataclass
class Dust:
    x: float
    y: float
    dx: float
    dy: float
    r: float
    alpha: int


class MachineFixingAnimation(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(200, 150)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent; border: none;")

        self._gears = [
            {"x": 10.0, "y": 12.0, "size": 60.0, "bars": 3, "speed": 4.0, "clockwise": False, "angle": 0.0},
            {"x": 60.0, "y": 61.0, "size": 60.0, "bars": 3, "speed": 4.0, "clockwise": True, "angle": 0.0},
            {"x": 10.0, "y": 110.0, "size": 60.0, "bars": 3, "speed": 4.0, "clockwise": False, "angle": 0.0},
            {"x": 128.0, "y": 13.0, "size": 120.0, "bars": 6, "speed": 2.0, "clockwise": False, "angle": 0.0},
        ]
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

    def ensure_running(self):
        if not self.timer.isActive():
            self.timer.start(33)
        self.update()

    def _tick(self):
        for gear in self._gears:
            delta = gear["speed"]
            gear["angle"] = gear["angle"] + delta if gear["clockwise"] else gear["angle"] - delta
        self.update()

    def _draw_background(self, p: QPainter, rect: QRectF):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#111111"))
        p.drawRoundedRect(rect, 6, 6)

        p.setPen(QPen(QColor(255, 255, 255, 25), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)

    def _draw_overlay(self, p: QPainter, rect: QRectF):
        p.setPen(Qt.PenStyle.NoPen)

        grad_top = QLinearGradient(0, rect.top(), 0, rect.top() + 28)
        grad_top.setColorAt(0.0, QColor(0, 0, 0, 120))
        grad_top.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(grad_top)
        p.drawRoundedRect(rect, 6, 6)

        grad_bottom = QLinearGradient(0, rect.bottom(), 0, rect.bottom() - 28)
        grad_bottom.setColorAt(0.0, QColor(0, 0, 0, 120))
        grad_bottom.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(grad_bottom)
        p.drawRoundedRect(rect, 6, 6)

        grad_left = QLinearGradient(rect.left(), 0, rect.left() + 28, 0)
        grad_left.setColorAt(0.0, QColor(0, 0, 0, 90))
        grad_left.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(grad_left)
        p.drawRoundedRect(rect, 6, 6)

        grad_right = QLinearGradient(rect.right(), 0, rect.right() - 28, 0)
        grad_right.setColorAt(0.0, QColor(0, 0, 0, 90))
        grad_right.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(grad_right)
        p.drawRoundedRect(rect, 6, 6)

    def _draw_gear(self, p: QPainter, gear: Dict[str, float | int | bool]):
        x = float(gear["x"])
        y = float(gear["y"])
        size = float(gear["size"])
        radius = size / 2.0
        cx = x + radius
        cy = y + radius

        p.save()

        outer_rect = QRectF(x, y, size, size)
        shell_grad = QRadialGradient(QPointF(cx, cy), radius)
        shell_grad.setColorAt(0.0, QColor("#6a6a6a"))
        shell_grad.setColorAt(0.65, QColor("#5b5b5b"))
        shell_grad.setColorAt(1.0, QColor("#444444"))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(shell_grad)
        p.drawEllipse(outer_rect)

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#888888"), 1))
        p.drawArc(outer_rect.adjusted(0.5, 0.5, -0.5, -0.5), 45 * 16, 180 * 16)

        p.setPen(QPen(QColor(0, 0, 0, 170), 1))
        p.drawArc(outer_rect.adjusted(0.5, 0.5, -0.5, -0.5), 225 * 16, 180 * 16)

        p.translate(cx, cy)
        p.rotate(float(gear["angle"]))

        inner_radius = radius - 1
        inner_rect = QRectF(-inner_radius, -inner_radius, inner_radius * 2, inner_radius * 2)
        p.setPen(QPen(QColor(255, 255, 255, 25), 1))
        p.setBrush(QColor("#555555"))
        p.drawEllipse(inner_rect)

        angles = [0, 60, 120] if int(gear["bars"]) == 3 else [0, 60, 120, 90, 30, 150]
        bar_h = 16
        bar_w = 76 if int(size) == 60 else 136
        bar_rect = QRectF(-bar_w / 2, -bar_h / 2, bar_w, bar_h)
        for angle in angles:
            p.save()
            p.rotate(angle)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#555555"))
            p.drawRoundedRect(bar_rect, 2, 2)
            p.setPen(QPen(QColor(255, 255, 255, 25), 1))
            p.drawLine(
                QPointF(bar_rect.left() + 0.5, bar_rect.top() + 1),
                QPointF(bar_rect.left() + 0.5, bar_rect.bottom() - 1),
            )
            p.drawLine(
                QPointF(bar_rect.right() - 0.5, bar_rect.top() + 1),
                QPointF(bar_rect.right() - 0.5, bar_rect.bottom() - 1),
            )
            p.restore()

        hole_size = 36 if int(size) == 60 else 96
        hole_r = hole_size / 2
        hole_rect = QRectF(-hole_r, -hole_r, hole_size, hole_size)
        hole_grad = QRadialGradient(QPointF(0, 0), hole_r)
        hole_grad.setColorAt(0.0, QColor("#1b1b1b"))
        hole_grad.setColorAt(0.6, QColor("#131313"))
        hole_grad.setColorAt(1.0, QColor("#0d0d0d"))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(hole_grad)
        p.drawEllipse(hole_rect)

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        p.drawArc(hole_rect.adjusted(1, 1, -1, -1), 35 * 16, 180 * 16)
        p.setPen(QPen(QColor(0, 0, 0, 180), 1))
        p.drawArc(hole_rect.adjusted(1, 1, -1, -1), 215 * 16, 180 * 16)
        p.restore()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        panel_rect = QRectF(0, 0, 200, 150)
        panel_x = (self.width() - panel_rect.width()) / 2.0
        panel_y = (self.height() - panel_rect.height()) / 2.0
        p.save()
        p.translate(panel_x, panel_y)
        self._draw_background(p, panel_rect)
        for gear in self._gears:
            self._draw_gear(p, gear)
        self._draw_overlay(p, panel_rect)
        p.restore()
        p.end()


class HazardStripeWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(16)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(self.rect(), QColor("#facc15"))
        stripe_w = 18
        stripe_span = stripe_w * 2
        rect_h = self.height()
        for x in range(-stripe_span * 2, self.width() + stripe_span * 2, stripe_span):
            path = QPainterPath()
            path.moveTo(x, rect_h)
            path.lineTo(x + stripe_w, rect_h)
            path.lineTo(x + stripe_span, 0)
            path.lineTo(x + stripe_w, 0)
            path.closeSubpath()
            p.fillPath(path, QColor("#111111"))
        p.end()


class RejectDetailHeaderView(QHeaderView):
    def __init__(self, orientation: Qt.Orientation, parent=None):
        super().__init__(orientation, parent)
        self._flash_cols: set[int] = set()
        self._flash_on: bool = False

    def set_flash_columns(self, cols):
        self._flash_cols = {int(col) for col in (cols or []) if col is not None}
        self.viewport().update()

    def set_flash_on(self, on: bool):
        self._flash_on = bool(on)
        self.viewport().update()

    def paintSection(self, painter: QPainter, rect: QRect, logicalIndex: int):
        if (
            self.orientation() == Qt.Orientation.Horizontal
            and logicalIndex in self._flash_cols
            and rect.isValid()
        ):
            painter.save()
            bg = QColor(220, 38, 38) if self._flash_on else QColor(254, 202, 202)
            fg = QColor(255, 255, 255) if self._flash_on else QColor("#7f1d1d")
            painter.fillRect(rect, bg)
            painter.setPen(fg)
            text = ""
            try:
                m = self.model()
                if m is not None:
                    text = str(m.headerData(logicalIndex, self.orientation(), Qt.ItemDataRole.DisplayRole) or "")
            except Exception:
                text = ""
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)
            painter.restore()
            return
        super().paintSection(painter, rect, logicalIndex)


class HistoryAnimatedColumn(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("HistoryCol")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._title_text = str(title or "History")
        self._latest_base_rect = QRect()
        self._recent_items: deque[QFrame] = deque(maxlen=10)
        self._anim_groups: List[Any] = []
        self._latest_anim_groups: List[Any] = []
        self._recent_insert_queue: deque[str] = deque()
        self._recent_anim_running = False
        self._initialized = False
        self._current_latest_text = ""
        self.enable_heavy_animations = True
        self._build_ui()

    def _build_ui(self):
        self.colTitle = QLabel(self._title_text, self)
        self.colTitle.setObjectName("SectionTitle")
        self.colTitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.latestCard = QFrame(self)
        self.latestCard.setObjectName("HistoryLatestCard")
        self.latestCard.setGraphicsEffect(QGraphicsOpacityEffect(self.latestCard))
        self.latestCard.graphicsEffect().setOpacity(1.0)
        self.latestCardLabel = QLabel("No scan yet", self.latestCard)
        self.latestCardLabel.setObjectName("MetaValue")
        self.latestCardLabel.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: 800;")
        self.latestCardLabel.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.latestCardLabel.setWordWrap(False)

        self.recentPanel = QFrame(self)
        self.recentPanel.setObjectName("HistoryRecentPanel")
        self.recentContainer = QWidget(self.recentPanel)
        self.recentContainer.setStyleSheet("background: transparent; border: none;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        pad = 4
        y = 8
        w = max(0, self.width() - (pad * 2))
        if self.colTitle.isVisible():
            self.colTitle.setGeometry(pad, y, w, 24)
            y += 28
        else:
            self.colTitle.setGeometry(0, 0, 0, 0)
        self.latestCard.setGeometry(pad, y, w, 44)
        self.latestCardLabel.setGeometry(8, 0, max(0, w - 16), 44)
        self._latest_base_rect = self.latestCard.geometry()
        y += 50
        recent_h = max(60, self.height() - y - 8)
        self.recentPanel.setGeometry(pad, y, w, recent_h)
        self.recentContainer.setGeometry(4, 6, max(0, w - 8), max(0, recent_h - 12))
        self._reposition_recent_items()

    def set_snapshot(self, entries: List[str]):
        items = [str(x).strip() for x in (entries or []) if str(x).strip()]
        self._current_latest_text = items[0] if items else ""
        self.latestCardLabel.setText(self._current_latest_text or "No scan yet")
        for w in list(self._recent_items):
            w.deleteLater()
        self._recent_items.clear()
        for txt in items[1:11]:
            row = self._make_recent_row(txt)
            self._recent_items.append(row)
        self._reposition_recent_items()
        self._initialized = True

    def push_scan(self, text: str):
        new_text = str(text or "").strip()
        if not new_text:
            return
        if not self._initialized:
            self.set_snapshot([new_text])
            return
        old_latest = self._current_latest_text.strip()
        if old_latest and old_latest != "No scan yet":
            self._recent_insert_queue.append(old_latest)
            self._process_recent_queue()
        self._current_latest_text = new_text
        self.latestCardLabel.setText(new_text)
        self._animate_latest_pulse()

    def _make_recent_row(self, text: str) -> QFrame:
        row = QFrame(self.recentContainer)
        row.setObjectName("HistoryRecentRow")
        row.setGraphicsEffect(QGraphicsOpacityEffect(row))
        row.graphicsEffect().setOpacity(1.0)
        lbl = QLabel(str(text or ""), row)
        lbl.setObjectName("HistoryRecentValue")
        lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 700;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        lbl.setWordWrap(False)
        row._inner_label = lbl  # type: ignore[attr-defined]
        row.show()
        return row

    def _process_recent_queue(self):
        if self._recent_anim_running or not self._recent_insert_queue:
            return
        self._insert_recent_with_animation(self._recent_insert_queue.popleft())

    def _insert_recent_with_animation(self, text: str):
        if not getattr(self, "enable_heavy_animations", True):
            row_h = 26
            gap = 2
            max_rows = 10
            incoming = self._make_recent_row(text)
            self._recent_items.appendleft(incoming)
            while len(self._recent_items) > max_rows:
                w = self._recent_items.pop()
                w.deleteLater()
            self._reposition_recent_items()
            self._recent_anim_running = False
            self._process_recent_queue()
            return
        self._recent_anim_running = True
        row_h = 26
        gap = 2
        max_rows = 10
        incoming = self._make_recent_row(text)
        incoming.resize(self.recentContainer.width(), row_h)
        incoming._inner_label.setGeometry(8, 0, max(0, incoming.width() - 16), row_h)  # type: ignore[attr-defined]
        start_y = -row_h - 6
        incoming.setGeometry(0, start_y, self.recentContainer.width(), row_h)
        incoming.raise_()

        current_widgets = list(self._recent_items)
        group = QParallelAnimationGroup(self)
        anim_in = QPropertyAnimation(incoming, b"geometry")
        anim_in.setDuration(300)
        anim_in.setStartValue(QRect(0, start_y, self.recentContainer.width(), row_h))
        anim_in.setEndValue(QRect(0, 0, self.recentContainer.width(), row_h))
        anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(anim_in)

        removed_widget = None
        for i, widget in enumerate(current_widgets):
            anim = QPropertyAnimation(widget, b"geometry")
            anim.setDuration(300)
            anim.setStartValue(widget.geometry())
            anim.setEndValue(QRect(0, (i + 1) * (row_h + gap), self.recentContainer.width(), row_h))
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            group.addAnimation(anim)
        if len(current_widgets) >= max_rows:
            removed_widget = current_widgets[-1]
            fade = QPropertyAnimation(removed_widget.graphicsEffect(), b"opacity")
            fade.setDuration(200)
            fade.setStartValue(1.0)
            fade.setEndValue(0.0)
            group.addAnimation(fade)

        def cleanup():
            self._recent_items.appendleft(incoming)
            while len(self._recent_items) > max_rows:
                w = self._recent_items.pop()
                w.deleteLater()
            if removed_widget is not None and removed_widget not in self._recent_items:
                removed_widget.deleteLater()
            self._reposition_recent_items()
            self._recent_anim_running = False
            self._process_recent_queue()
            if group in self._anim_groups:
                self._anim_groups.remove(group)

        group.finished.connect(cleanup)
        self._anim_groups.append(group)
        group.start()

    def _reposition_recent_items(self):
        row_h = 26
        gap = 2
        w = self.recentContainer.width()
        for i, widget in enumerate(self._recent_items):
            widget.resize(w, row_h)
            widget._inner_label.setGeometry(8, 0, max(0, w - 16), row_h)  # type: ignore[attr-defined]
            widget.graphicsEffect().setOpacity(1.0)
            widget.setGeometry(0, i * (row_h + gap), w, row_h)

    def _animate_latest_pulse(self):
        if not getattr(self, "enable_heavy_animations", True):
            self.latestCard.setGeometry(self._latest_base_rect)
            self.latestCard.graphicsEffect().setOpacity(1.0)
            return
        for grp in list(self._latest_anim_groups):
            try:
                grp.stop()
            except Exception:
                pass
            if grp in self._latest_anim_groups:
                self._latest_anim_groups.remove(grp)
        base = QRect(self._latest_base_rect)
        drop_start = QRect(base.x(), base.y() - 10, base.width(), base.height())
        grow = QRect(base.x() - 2, base.y() - 1, base.width() + 4, base.height() + 2)
        self.latestCard.setGeometry(drop_start)
        self.latestCard.graphicsEffect().setOpacity(1.0)

        geom_seq = QSequentialAnimationGroup(self)
        for dur, start, end in (
            (120, drop_start, base),
            (90, base, grow),
            (120, grow, base),
        ):
            a = QPropertyAnimation(self.latestCard, b"geometry")
            a.setDuration(dur)
            a.setStartValue(start)
            a.setEndValue(end)
            a.setEasingCurve(QEasingCurve.Type.OutCubic)
            geom_seq.addAnimation(a)

        opacity_seq = QSequentialAnimationGroup(self)
        a1 = QPropertyAnimation(self.latestCard.graphicsEffect(), b"opacity")
        a1.setDuration(120)
        a1.setEndValue(0.9)
        a2 = QPropertyAnimation(self.latestCard.graphicsEffect(), b"opacity")
        a2.setDuration(210)
        a2.setStartValue(0.9)
        a2.setEndValue(1.0)
        opacity_seq.addAnimation(a1)
        opacity_seq.addAnimation(a2)

        group = QParallelAnimationGroup(self)
        group.addAnimation(geom_seq)
        group.addAnimation(opacity_seq)

        def cleanup():
            if group in self._latest_anim_groups:
                self._latest_anim_groups.remove(group)
            self.latestCard.setGeometry(self._latest_base_rect)
            self.latestCard.graphicsEffect().setOpacity(1.0)

        self._latest_anim_groups.append(group)
        group.finished.connect(cleanup)
        group.start()

    def set_animations_enabled(self, enabled: bool):
        self.enable_heavy_animations = bool(enabled)
        if self.enable_heavy_animations:
            return
        self._recent_anim_running = False
        for grp in list(self._anim_groups):
            try:
                grp.stop()
            except Exception:
                pass
        self._anim_groups.clear()
        for grp in list(self._latest_anim_groups):
            try:
                grp.stop()
            except Exception:
                pass
        self._latest_anim_groups.clear()
        self.latestCard.setGeometry(self._latest_base_rect)
        self.latestCard.graphicsEffect().setOpacity(1.0)
        self._reposition_recent_items()


class ClientUI(QWidget):
    UI_BASE_WIDTH = 1920
    UI_BASE_HEIGHT = 1080
    UI_MIN_SCALE = 0.50
    UI_MAX_SCALE = 1.35

    scan_received = pyqtSignal(str)
    scanner_status = pyqtSignal(str)
    average_weight_received = pyqtSignal(float, str)

    @staticmethod
    def _load_digital_font_family() -> str:
        font_path = os.path.join(BASE_DIR, "digital-7.ttf")
        fallback_family = "DS-Digital"
        if not os.path.exists(font_path):
            return fallback_family
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id < 0:
            return fallback_family
        families = QFontDatabase.applicationFontFamilies(font_id)
        return str(families[0]).strip() if families else fallback_family

    def __init__(self):
        super().__init__()
        self.state = ClientState()
        self.client_config = _load_client_config()
        self.job_api_config = _load_job_api_config()
        self._digital_font_family = self._load_digital_font_family()
        self._identity_sync_lock = threading.Lock()
        self._identity_sync_inflight = False
        self._identity_sync_last_attempt = 0.0
        self._identity_sync_last_ok = 0.0
        self._active_session_sql_sync_lock = threading.Lock()
        self._active_session_sql_sync_inflight = False
        self._active_session_sql_sync_last_attempt = 0.0
        self._active_session_sql_sync_last_ok = 0.0
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
        self._product_catalog_sku_by_id: Optional[Dict[str, str]] = None
        self._product_catalog_last_refresh_attempt = 0.0
        self._action_logs: List[str] = []
        self._background_pixmap = QPixmap(MACHINE_BACKGROUND_IMAGE)
        self._avg_weight_server: Optional[ThreadingHTTPServer] = None
        self._avg_weight_server_thread: Optional[threading.Thread] = None
        self._avg_weight_server_error: Optional[str] = None

        self.setWindowTitle("Machine Client Dashboard")
        self.setMinimumSize(0, 0)
        self.setObjectName("ClientUIRoot")
        self.setStyleSheet(
            APP_STYLESHEET
            + f"""
QWidget#ClientUIRoot {{
    background: transparent;
}}
"""
        )
        self.graphics_mode = "quality"
        self.enable_check_animation = True
        self.enable_flashing_lights = True
        self.enable_pulse_effects = True
        self.enable_heavy_animations = True
        self.enable_background_blur = True
        self.enable_gif_animations = True

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 8)
        root.setSpacing(0)

        leftWrap = QWidget()
        self.leftWrap = leftWrap
        self.leftWrap.setStyleSheet("background: transparent;")
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(6)
        leftWrap.setLayout(left)

        self.pageTitle = QLabel("Machine Dashboard")
        self.pageTitle.setObjectName("PageTitle")
        self.pageTitle.setWordWrap(False)
        self.pageTitle.setMinimumHeight(34)
        self.pageTitle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.headerJobStart = QLabel("")
        self.headerJobStart.setObjectName("HeaderMetaValue")
        self.headerJobStart.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.headerJobStart.setMinimumWidth(0)
        self.headerJobStart.hide()
        self.headerJobDuration = QLabel("")
        self.headerJobDuration.setObjectName("HeaderMetaValue")
        self.headerJobDuration.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.headerJobDuration.setMinimumWidth(0)
        self.headerJobDuration.hide()
        self.headerDateTime = QLabel("")
        self.headerDateTime.setObjectName("HeaderMetaValue")
        self.headerDateTime.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.btnSettings = QPushButton("\u2699")
        self.btnSettings.setObjectName("HeaderSettingsButton")
        self.btnSettings.setFixedSize(40, 40)
        self.btnSettings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btnSettings.clicked.connect(self._show_settings_overlay)

        headerRow = QHBoxLayout()
        headerRow.setContentsMargins(14, 5, 14, 5)
        headerRow.setSpacing(8)
        headerRow.addWidget(self.btnSettings, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        headerRow.addWidget(self.pageTitle, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        headerRow.addWidget(self.headerJobStart, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        headerRow.addWidget(self.headerJobDuration, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        headerRow.addWidget(self.headerDateTime, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.headerCard = QFrame()
        self.headerCard.setObjectName("HeaderCard")
        self.headerCard.setLayout(headerRow)

        self.headerDivider = QFrame()
        self.headerDivider.setFrameShape(QFrame.Shape.HLine)
        self.headerDivider.setFrameShadow(QFrame.Shadow.Plain)
        self.headerDivider.setStyleSheet("background: transparent; min-height: 0px; max-height: 0px; border: none;")

        self._banner_base_text = "Scan MACHINE QR to start"
        self.banner = QLabel(self._banner_base_text)
        self.banner.setObjectName("Banner")
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setWordWrap(True)
        self.banner.setMinimumHeight(56)
        self.banner.setMaximumHeight(76)
        self.banner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.banner.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f6aea, stop:1 #2454c6);"
            "color: #ffffff; border: 1px solid #1d4ed8; border-radius: 16px;"
            "padding: 10px 14px; font-size: 20px; font-weight: 800; letter-spacing: 0.2px;"
        )
        self.status = QLabel("Waiting...")
        self.status.setObjectName("StatusBar")
        self.status.setWordWrap(True)
        self.status.setFixedHeight(44)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.machineAnim = QLabel("[M] ----")
        self.machineAnim.setObjectName("MachineAnim")
        self.machineAnim.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.machineAnim.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.machineAnim.setProperty("mode", "idle")
        self.machineAnim.setProperty("pulse", "0")
        self._apply_machine_anim_style("idle")
        self.scanSectionDivider = QFrame()
        self.scanSectionDivider.setFrameShape(QFrame.Shape.HLine)
        self.scanSectionDivider.setFrameShadow(QFrame.Shadow.Plain)
        self.scanSectionDivider.setStyleSheet("background: rgba(148, 163, 184, 0.35); min-height: 1px; max-height: 1px; border: none;")

        left.addWidget(self.banner, 0)
        left.addWidget(self.scanSectionDivider)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)

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
        self.lblPack = CounterCard("PACK")
        self.lblGood = CounterCard("GOOD")
        self.lblButal = CounterCard("BUTAL")
        self.lblReject = CounterCard("REJECT", "red")
        self.lblTotalGood = CounterCard("TOTAL GOOD")
        self.lblPack.setObjectName("StatPack")
        self.lblGood.setObjectName("StatGood")
        self.lblButal.setObjectName("StatButal")
        self.lblReject.setObjectName("StatReject")
        self.lblTotalGood.setObjectName("StatTotalGood")
        self.cardStatPack = self.lblPack
        self.cardStatGood = self.lblGood
        self.cardStatButal = self.lblButal
        self.cardStatReject = self.lblReject
        self.cardStatTotalGood = self.lblTotalGood
        for card in (
            self.cardStatPack,
            self.cardStatGood,
            self.cardStatButal,
            self.cardStatReject,
            self.cardStatTotalGood,
        ):
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            card.setMinimumHeight(92)
            card.setMaximumHeight(104)
            statRow.addWidget(card, 1)
        self.cardProduction.layout().addLayout(statRow)
        self.cardProductionOuter.setMinimumHeight(106)
        self.cardProductionOuter.setMaximumHeight(126)
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
        self.machineAnim.setFixedHeight(36)
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
            value_lbl.setMinimumWidth(0)
            value_lbl.setFixedHeight(36)
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
        self._reject_detail_col_by_code = {code: i for i, (code, _label) in enumerate(REJECT_DETAIL_ITEMS)}
        self._reject_detail_active_codes: set[str] = set()
        _rej_hdr = RejectDetailHeaderView(Qt.Orientation.Horizontal, self.rejectDetailTable)
        self.rejectDetailTable.setHorizontalHeader(_rej_hdr)
        self.rejectDetailTable.setAlternatingRowColors(False)
        self.rejectDetailTable.setWordWrap(False)
        self.rejectDetailTable.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rejectDetailTable.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.rejectDetailTable.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rejectDetailTable.verticalHeader().setVisible(False)
        self.rejectDetailTable.verticalHeader().setDefaultSectionSize(30)
        self.rejectDetailTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.rejectDetailTable.setShowGrid(False)
        self.rejectDetailTable.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rejectDetailTable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rejectDetailTable.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.rejectDetailTable.horizontalHeader().setFixedHeight(34)
        self.rejectDetailTable.setMinimumHeight(68)
        self.rejectDetailTable.setMaximumHeight(68)
        self.rejectDetailTable.setStyleSheet(
            "QTableWidget { background: transparent; border: none; gridline-color: transparent; }"
            "QHeaderView::section { background: rgba(226,232,240,0.9); color: #0f172a; font-weight: 900;"
            " border: none; border-right: 1px solid rgba(148,163,184,0.45);"
            " border-bottom: 1px solid rgba(148,163,184,0.5); padding: 6px; }"
            "QHeaderView::section:last { border-right: none; }"
            "QTableWidget::item { padding: 2px; color: #f3f4f6; font-weight: 900;"
            " border-right: 1px solid rgba(148,163,184,0.35); background: transparent; }"
            "QTableWidget::item:last { border-right: none; }"
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

        # Product parts panel
        self.cardJobDetailsOuter, self.cardJobDetails = self._make_double_layer_card("PRODUCT PARTS")
        self.jobPartsTable = QTableWidget(0, 6)
        self.jobPartsTable.setObjectName("ProductPartsTable")
        self.jobPartsTable.setHorizontalHeaderLabels(
            ["SKU", "Name", "Part Qty/Unit", "Available", "Rqst Part Qty", "Remaining"]
        )
        self.jobPartsTable.setAlternatingRowColors(False)
        self.jobPartsTable.setWordWrap(True)
        self.jobPartsTable.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.jobPartsTable.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.jobPartsTable.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.jobPartsTable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.jobPartsTable.verticalHeader().setVisible(False)
        self.jobPartsTable.verticalHeader().setDefaultSectionSize(30)
        self.jobPartsTable.horizontalHeader().setStretchLastSection(False)
        self.jobPartsTable.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.jobPartsTable.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.jobPartsTable.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.jobPartsTable.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.jobPartsTable.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.jobPartsTable.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.jobPartsTable.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.jobPartsTable.horizontalHeader().setFixedHeight(32)
        self.jobPartsTable.setColumnWidth(0, 220)
        # Size table to show up to 12 visible rows without clipping.
        parts_row_h = self.jobPartsTable.verticalHeader().defaultSectionSize()
        parts_header_h = self.jobPartsTable.horizontalHeader().height()
        parts_frame_h = self.jobPartsTable.frameWidth() * 2
        parts_target_h = parts_header_h + (parts_row_h * 12) + parts_frame_h
        self.jobPartsTable.setMinimumHeight(parts_target_h)
        self.jobPartsTable.setMaximumHeight(parts_target_h)
        self.jobPartsTableShell = QFrame()
        self.jobPartsTableShell.setObjectName("ProductPartsTableShell")
        self.jobPartsTableShell.setLayout(QVBoxLayout())
        self.jobPartsTableShell.layout().setContentsMargins(0, 0, 0, 0)
        self.jobPartsTableShell.layout().setSpacing(0)
        self.jobPartsTableShell.layout().addWidget(self.jobPartsTable)
        self.cardJobDetails.layout().addWidget(self.jobPartsTableShell)
        self.cardJobDetails.layout().addStretch(1)
        _product_parts_title = self.cardJobDetails.findChild(QLabel, "SectionTitle")
        if _product_parts_title is not None:
            _product_parts_title.setMinimumHeight(38)
            _product_parts_title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.cardJobDetailsOuter.setStyleSheet(
            "QFrame#LeftCardOuter {"
            " background: transparent;"
            " border: none;"
            "}"
            "QFrame#ProductPartsTableShell {"
            " background: transparent;"
            " border: none;"
            " border-radius: 0px;"
            "}"
        )
        self.cardJobDetails.setStyleSheet(
            "QFrame#LeftCardInner {"
            " background: qradialgradient(cx:0.5, cy:0.36, radius:1.25, fx:0.5, fy:0.18,"
            "                           stop:0 rgba(120,124,134,232),"
            "                           stop:0.36 rgba(70,74,82,238),"
            "                           stop:1 rgba(24,26,31,248));"
            " border: 1px solid rgba(88,92,101,240);"
            " border-radius: 34px;"
            "}"
            "QLabel#SectionTitle {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(108,112,121,228),"
            "                             stop:1 rgba(58,61,68,220));"
            " color: rgba(237,240,244,230);"
            " border: none;"
            " border-top-left-radius: 22px;"
            " border-top-right-radius: 22px;"
            " border-bottom: 1px solid rgba(146,151,162,95);"
            " padding: 8px 12px;"
            " font-weight: 900;"
            "}"
        )
        self.cardJobDetails.layout().setContentsMargins(0, 0, 0, 0)
        self.cardJobDetails.layout().setSpacing(0)
        self.jobPartsTable.setStyleSheet(
            "QTableWidget#ProductPartsTable {"
            " background: transparent;"
            " color: rgba(234,236,239,225);"
            " border: none;"
            " border-radius: 0px;"
            " gridline-color: rgba(112,116,126,150);"
            " outline: none;"
            "}"
            "QTableWidget#ProductPartsTable::item {"
            " background: transparent;"
            " color: rgba(239,240,242,226);"
            " font-size: 9px;"
            " border-top: 1px solid rgba(126,130,140,132);"
            " border-right: 1px solid rgba(126,130,140,145);"
            " border-bottom: 1px solid rgba(126,130,140,132);"
            " padding: 2px 8px;"
            " selection-background-color: transparent;"
            " selection-color: rgba(239,240,242,226);"
            "}"
            "QHeaderView::section {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(112,116,126,232),"
            "                             stop:1 rgba(58,61,69,225));"
            " color: rgba(240,242,245,232);"
            " font-weight: 900;"
            " border: none;"
            " border-bottom: 1px solid rgba(136,140,149,150);"
            " border-right: 1px solid rgba(122,126,135,140);"
            " padding: 4px 8px;"
            "}"
            "QHeaderView::section:last { border-right: none; }"
            "QScrollBar:vertical {"
            " background: rgba(27,29,34,150);"
            " width: 12px;"
            " margin: 22px 2px 22px 2px;"
            " border-radius: 6px;"
            "}"
            "QScrollBar::handle:vertical {"
            " background: rgba(140,145,154,180);"
            " min-height: 24px;"
            " border-radius: 6px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            " height: 0px;"
            "}"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
            " background: transparent;"
            "}"
        )
        self.cardJobDetailsOuter.setMinimumHeight(400)
        self.cardJobDetailsOuter.setMaximumHeight(500)
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
            value_lbl.setMinimumWidth(0)
            value_lbl.setFixedHeight(36)
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
        self.cardSessionActivityOuter.setStyleSheet("QFrame#LeftCardOuter { background: transparent; border: none; }")
        self.cardSessionActivity.setStyleSheet(
            "QFrame#LeftCardInner {"
            " background: qradialgradient(cx:0.5, cy:0.34, radius:1.16, fx:0.5, fy:0.14,"
            "                           stop:0 rgba(121,125,135,232),"
            "                           stop:0.40 rgba(73,77,85,238),"
            "                           stop:1 rgba(24,26,31,246));"
            " border: 1px solid rgba(90,94,103,240);"
            " border-radius: 24px;"
            "}"
            "QLabel#SectionTitle {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(108,112,121,228),"
            "                             stop:1 rgba(58,61,68,220));"
            " color: rgba(237,240,244,230);"
            " border: none;"
            " border-top-left-radius: 22px;"
            " border-top-right-radius: 22px;"
            " border-bottom: 1px solid rgba(146,151,162,95);"
            " padding: 8px 12px;"
            " font-weight: 900;"
            "}"
        )
        self.jobDetailsUnifiedTitle = QLabel("Job Details")
        self.jobDetailsUnifiedTitle.setObjectName("SectionTitle")
        self.jobDetailsUnifiedTitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.jobDetailsUnifiedTitle.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 rgba(108,112,121,228), stop:1 rgba(58,61,68,220)); "
            "color: rgba(237,240,244,230); border: none; "
            "border-top-left-radius: 16px; border-top-right-radius: 16px; "
            "border-bottom-left-radius: 0px; border-bottom-right-radius: 0px; "
            "border-bottom: 1px solid rgba(146,151,162,95); "
            "padding: 8px 12px; font-weight: 900;"
        )
        self.jobDetailsUnifiedTitle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.jobDetailsUnifiedTitle.setMinimumHeight(38)
        self.cardSessionActivity.layout().addWidget(self.jobDetailsUnifiedTitle)

        # Remove individual outer borders so only one frame is visible.
        self.cardSessionOuter.setStyleSheet("QFrame#LeftCardOuter { background: transparent; border: none; }")
        self.cardActivityOuter.setStyleSheet("QFrame#LeftCardOuter { background: transparent; border: none; }")
        # Remove individual inner frames as well.
        self.cardSession.setStyleSheet("QFrame#LeftCardInner { background: transparent; border: none; }")
        self.cardActivity.setStyleSheet("QFrame#LeftCardInner { background: transparent; border: none; }")

        # Top-grid cycle fields (separate widgets from right panel cycle widgets).
        self.topCycleCount = QLabel("Confirmed by: -")
        self.topCycleCount.setObjectName("MetaValue")
        self.topCycleCount.setFixedHeight(36)
        self.topCycleCurrent = QLabel("Act Cycle Time: ")
        self.topCycleCurrent.setObjectName("MetaValue")
        self.topCycleCurrent.setFixedHeight(36)
        self.topCycleStd = QLabel("Std Cycle Time: -")
        self.topCycleStd.setObjectName("MetaValue")
        self.topCycleStd.setFixedHeight(36)
        self.topCycleQtyShift = QLabel("Pack Cycle Time: -")
        self.topCycleQtyShift.setObjectName("MetaValue")
        self.topCycleQtyShift.setFixedHeight(36)

        unified_fields_grid = QGridLayout()
        unified_fields_grid.setContentsMargins(18, 0, 18, 0)
        unified_fields_grid.setHorizontalSpacing(10)
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
        self.cardSessionActivity.layout().addSpacing(12)
        self.rejectLabel = QLabel("Reject Details")
        self.rejectLabel.setObjectName("SectionLabel")
        self.rejectLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rejectLabel.setStyleSheet(
            "background: transparent; color: white; font-size: 17px; "
            "font-weight: 900; letter-spacing: 0.5px;"
        )
        self.cardSessionActivity.layout().addWidget(self.rejectLabel)
        self.cardSessionActivity.layout().addSpacing(6)
        self.cardSessionActivity.layout().addWidget(self.rejectDetailTable)

        self.cardSessionActivityOuter.setMinimumHeight(326)
        self.cardSessionActivityOuter.setMaximumHeight(402)
        self.cardSessionActivityOuter.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
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
        grid.setRowStretch(2, 0)
        grid.setRowStretch(3, 0)  # Raw Materials + Cycle row
        left.addLayout(grid, 1)

        # Keep in-memory logging, but remove the temporary visible Job API logs panel.
        self.cardJobApiLogsOuter = None
        self.cardJobApiLogs = None
        self.jobApiLogLabel = None

        # Let the main grid consume remaining height so the bottom cards can expand on taller screens.

        # Right side panel (downtime reason + timer).
        self.rightPanel = QFrame()
        self.rightPanel.setObjectName("RightPanel")
        rightLayout = QVBoxLayout()
        rightLayout.setContentsMargins(16, 0, 16, 0)
        rightLayout.setSpacing(0)
        self.rightPanel.setLayout(rightLayout)
        self.rightTopSpacer = QWidget()
        self.rightTopSpacer.setFixedHeight(0)
        self.rightTopSpacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        rightLayout.addWidget(self.rightTopSpacer)

        self.rightRawSacks = QLabel("Raw Mat 1: -    Sacks: 0")
        self.rightRawSacks.setObjectName("RightMonitorValue")
        self.rightRawField = QLabel("Raw Mat 2: -    Sacks: 0")
        self.rightRawField.setObjectName("RightMonitorValue")
        self.rightRawTotalScans = QLabel("Raw Mat 3: -    Sacks: 0")
        self.rightRawTotalScans.setObjectName("RightMonitorValue")
        self.rawPreviewWrap = QFrame()
        self.rawPreviewWrap.setObjectName("RawPreviewWrap")
        self.rawPreviewWrap.setLayout(QHBoxLayout())
        self.rawPreviewWrap.layout().setContentsMargins(0, 0, 0, 0)
        self.rawPreviewWrap.layout().setSpacing(8)
        self.rawPreviewCols: List[QFrame] = []
        self.rawPreviewNames: List[QLabel] = []
        self.rawPreviewRings: List[CircleProgressBadge] = []
        accents = [QColor("#22c55e"), QColor("#0ea5e9"), QColor("#f59e0b")]
        for i in range(3):
            col = QFrame()
            col.setObjectName("RawPreviewCol")
            col.setLayout(QVBoxLayout())
            col.layout().setContentsMargins(8, 8, 8, 8)
            col.layout().setSpacing(6)
            name = QLabel("-")
            name.setObjectName("RawPreviewName")
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name.setWordWrap(True)
            name.setFixedHeight(34)
            ring = CircleProgressBadge(accents[i])
            col.layout().addWidget(name)
            col.layout().addWidget(ring, 1, Qt.AlignmentFlag.AlignCenter)
            self.rawPreviewWrap.layout().addWidget(col, 1)
            self.rawPreviewCols.append(col)
            self.rawPreviewNames.append(name)
            self.rawPreviewRings.append(ring)
        self.rawPreviewWrap.setStyleSheet(
            "QFrame#RawPreviewCol {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(101,105,113,222),"
            "                             stop:1 rgba(53,56,62,230));"
            " border: 1px solid #787d86;"
            " border-radius: 12px;"
            "}"
            "QLabel#RawPreviewName { color: #edf0f4; font-size: 11px; font-weight: 900; }"
        )
        self.rightRawSacks.setMinimumHeight(38)
        self.rightRawField.setMinimumHeight(38)
        self.rightRawTotalScans.setMinimumHeight(38)
        self.rawPreviewWrap.setMinimumHeight(128)

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
        self.rightCycleCurrent = QLabel("Act Cycle Time: ")
        self.rightCycleCurrent.setObjectName("RightMonitorValue")
        self.rightCycleStd = QLabel("Std Cycle Time: -")
        self.rightCycleStd.setObjectName("RightMonitorValue")
        self.rightCycleQtyShift = QLabel("Pack Cycle Time: -")
        self.rightCycleQtyShift.setObjectName("RightMonitorValue")
        self.rightMaintenance = QLabel("Maintenance: ")
        self.rightMaintenance.setObjectName("RightMonitorValue")
        self.rightSupervisor = QLabel("Supervisor: ")
        self.rightSupervisor.setObjectName("RightMonitorValue")
        self.rightSupervisorLeft = QLabel("Supervisor: -")
        self.rightSupervisorLeft.setObjectName("RightMonitorValue")
        for downtime_field in (
            self.rightDowntimeTimer,
            self.rightDowntimeReason,
            self.rightStartupReject,
            self.rightMaintenance,
            self.rightSupervisorLeft,
            self.rightSupervisor,
        ):
            downtime_field.setMinimumHeight(38)
            downtime_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        rawDowntimeCol = QVBoxLayout()
        rawDowntimeCol.setContentsMargins(0, 0, 0, 0)
        rawDowntimeCol.setSpacing(5)

        rawOuter = QFrame()
        rawOuter.setObjectName("RightCardOuter")
        rawOuterLay = QVBoxLayout()
        rawOuterLay.setContentsMargins(8, 8, 8, 8)
        rawOuterLay.setSpacing(0)
        rawOuter.setLayout(rawOuterLay)

        rawFrame = QFrame()
        rawFrame.setObjectName("RawMirrorHost")
        rawFrame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        rawCol = QVBoxLayout()
        rawCol.setContentsMargins(0, 0, 0, 0)
        rawCol.setSpacing(6)
        rawFrame.setLayout(rawCol)

        rawBody = QFrame()
        rawBody.setObjectName("RawMirrorBody")
        rawBody.setLayout(QVBoxLayout())
        rawBody.layout().setContentsMargins(0, 0, 0, 0)
        rawBody.layout().setSpacing(10)

        rawHeader = QFrame()
        rawHeader.setObjectName("RawMirrorHeader")
        rawHeader.setLayout(QVBoxLayout())
        rawHeader.layout().setContentsMargins(12, 10, 12, 10)
        rawHeader.layout().setSpacing(0)
        rawTitle = QLabel("Raw Materials Consumption")
        rawTitle.setObjectName("RightTitle")
        rawTitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rawHeader.layout().addWidget(rawTitle)
        rawBody.layout().addWidget(rawHeader)

        rawContent = QHBoxLayout()
        rawContent.setContentsMargins(10, 0, 10, 10)
        rawContent.setSpacing(8)

        rawLeftCol = QVBoxLayout()
        rawLeftCol.setContentsMargins(0, 0, 0, 0)
        rawLeftCol.setSpacing(8)
        rawLeftCol.addWidget(self.rightRawSacks)
        rawLeftCol.addWidget(self.rightRawField)
        rawLeftCol.addWidget(self.rightRawTotalScans)

        rawRightCol = QVBoxLayout()
        rawRightCol.setContentsMargins(0, 0, 0, 0)
        rawRightCol.setSpacing(8)
        rawRightCol.addWidget(self.rawPreviewWrap)

        rawContent.addLayout(rawLeftCol, 1)
        rawContent.addLayout(rawRightCol, 1)
        rawBody.layout().addLayout(rawContent)
        rawCol.addWidget(rawBody)
        rawFrame.setStyleSheet(
            "QFrame#RawMirrorHost { background: transparent; border: none; }"
            "QFrame#RawMirrorBody {"
            " background: qradialgradient(cx:0.5, cy:0.34, radius:1.16, fx:0.5, fy:0.14,"
            "                           stop:0 rgba(121,125,135,232),"
            "                           stop:0.40 rgba(73,77,85,238),"
            "                           stop:1 rgba(24,26,31,246));"
            " border: 1px solid rgba(90,94,103,240);"
            " border-radius: 24px;"
            "}"
            "QFrame#RawMirrorHeader {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(108,112,121,228),"
            "                             stop:1 rgba(58,61,68,220));"
            " border: none;"
            " border-top-left-radius: 24px;"
            " border-top-right-radius: 24px;"
            " border-bottom: 1px solid rgba(146,151,162,95);"
            "}"
            "QFrame#RawMirrorHeader QLabel#RightTitle { color: #edf0f4; }"
            "QFrame#RawMirrorHeader QLabel { color: #edf0f4; }"
        )
        rawOuterLay.addWidget(rawFrame)

        rawOuter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        rawFrame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        rawFrame.setMinimumHeight(150)
        rawDowntimeCol.addWidget(rawOuter, 1)

        downtimeOuter = QFrame()
        downtimeOuter.setObjectName("RightCardOuter")
        downtimeOuterLay = QVBoxLayout()
        downtimeOuterLay.setContentsMargins(8, 8, 8, 8)
        downtimeOuterLay.setSpacing(0)
        downtimeOuter.setLayout(downtimeOuterLay)

        downtimeFrame = QFrame()
        downtimeFrame.setObjectName("DowntimeMirrorHost")
        downtimeFrame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        downtimeCol = QVBoxLayout()
        downtimeCol.setContentsMargins(0, 0, 0, 0)
        downtimeCol.setSpacing(6)
        downtimeFrame.setLayout(downtimeCol)

        downtimeBody = QFrame()
        downtimeBody.setObjectName("DowntimeMirrorBody")
        downtimeBody.setLayout(QVBoxLayout())
        downtimeBody.layout().setContentsMargins(0, 0, 0, 0)
        downtimeBody.layout().setSpacing(10)

        downtimeHeader = QFrame()
        downtimeHeader.setObjectName("DowntimeMirrorHeader")
        downtimeHeader.setLayout(QVBoxLayout())
        downtimeHeader.layout().setContentsMargins(12, 8, 12, 8)
        downtimeHeader.layout().setSpacing(0)
        downtimeTitle = QLabel("Downtime Monitor")
        downtimeTitle.setObjectName("RightTitle")
        downtimeTitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        downtimeHeader.layout().addWidget(downtimeTitle)
        shared_header_h = max(rawHeader.sizeHint().height(), downtimeHeader.sizeHint().height()) + 4
        rawHeader.setMinimumHeight(shared_header_h)
        downtimeBody.layout().addWidget(downtimeHeader)

        downtimeGrid = QGridLayout()
        downtimeGrid.setContentsMargins(10, 6, 10, 12)
        downtimeGrid.setHorizontalSpacing(8)
        downtimeGrid.setVerticalSpacing(8)
        downtimeGrid.addWidget(self.rightDowntimeTimer, 0, 0)
        downtimeGrid.addWidget(self.rightDowntimeReason, 0, 1)
        downtimeGrid.addWidget(self.rightStartupReject, 1, 0)
        downtimeGrid.addWidget(self.rightMaintenance, 1, 1)
        downtimeGrid.addWidget(self.rightSupervisorLeft, 2, 0)
        downtimeGrid.addWidget(self.rightSupervisor, 2, 1)
        downtimeGrid.setRowStretch(0, 1)
        downtimeGrid.setRowStretch(1, 1)
        downtimeGrid.setRowStretch(2, 1)
        downtimeBody.layout().addLayout(downtimeGrid)
        downtimeCol.addWidget(downtimeBody)
        downtimeFrame.setStyleSheet(
            "QFrame#DowntimeMirrorHost { background: transparent; border: none; }"
            "QFrame#DowntimeMirrorBody {"
            " background: qradialgradient(cx:0.5, cy:0.34, radius:1.16, fx:0.5, fy:0.14,"
            "                           stop:0 rgba(121,125,135,232),"
            "                           stop:0.40 rgba(73,77,85,238),"
            "                           stop:1 rgba(24,26,31,246));"
            " border: 1px solid rgba(90,94,103,240);"
            " border-radius: 24px;"
            "}"
            "QFrame#DowntimeMirrorHeader {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(108,112,121,228),"
            "                             stop:1 rgba(58,61,68,220));"
            " border: none;"
            " border-top-left-radius: 24px;"
            " border-top-right-radius: 24px;"
            " border-bottom: 1px solid rgba(146,151,162,95);"
            "}"
            "QFrame#DowntimeMirrorHeader QLabel#RightTitle { color: #edf0f4; }"
            "QFrame#DowntimeMirrorHeader QLabel { color: #edf0f4; }"
        )
        downtimeOuterLay.addWidget(downtimeFrame)
        downtimeOuter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        downtimeFrame.setMinimumHeight(150)

        rawDowntimeCol.addWidget(downtimeOuter, 1)

        linkageOuter = QFrame()
        linkageOuter.setObjectName("RightCardOuter")
        linkageOuterLay = QVBoxLayout()
        linkageOuterLay.setContentsMargins(8, 0, 8, 8)
        linkageOuterLay.setSpacing(0)
        linkageOuter.setLayout(linkageOuterLay)

        linkageFrame = QFrame()
        linkageFrame.setObjectName("LinkageMirrorHost")
        linkageFrame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        linkageCol = QVBoxLayout()
        linkageCol.setContentsMargins(0, 0, 0, 0)
        linkageCol.setSpacing(6)
        linkageFrame.setLayout(linkageCol)
        linkageBody = QFrame()
        linkageBody.setObjectName("LinkageMirrorBody")
        linkageBody.setLayout(QVBoxLayout())
        linkageBody.layout().setContentsMargins(0, 0, 0, 10)
        linkageBody.layout().setSpacing(0)

        linkageHeader = QFrame()
        linkageHeader.setObjectName("LinkageMirrorHeader")
        linkageHeader.setLayout(QVBoxLayout())
        linkageHeader.layout().setContentsMargins(12, 10, 12, 10)
        linkageHeader.layout().setSpacing(0)
        linkageMirrorTitle = QLabel("Linkage Mirror")
        linkageMirrorTitle.setObjectName("RightTitle")
        linkageMirrorTitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        linkageHeader.layout().addWidget(linkageMirrorTitle)
        linkageHeader.setMinimumHeight(shared_header_h)
        linkageBody.layout().addWidget(linkageHeader)

        linkageContent = QWidget()
        linkageContent.setObjectName("LinkageMirrorContent")
        linkageContent.setLayout(QHBoxLayout())
        linkageContent.layout().setContentsMargins(10, 8, 10, 8)
        linkageContent.layout().setSpacing(14)
        linkageContent.layout().setStretch(0, 1)
        linkageContent.layout().setStretch(1, 1)

        linkageLeft = QFrame()
        linkageLeft.setObjectName("LinkageMirrorLeft")
        linkageLeft.setLayout(QVBoxLayout())
        linkageLeft.layout().setContentsMargins(0, 0, 0, 0)
        linkageLeft.layout().setSpacing(6)
        linkageLeft.setMinimumWidth(0)

        def _make_linked_job_row(title: str):
            row = QFrame()
            row.setObjectName("LinkageMirrorJobRow")
            row.setLayout(QHBoxLayout())
            row.layout().setContentsMargins(18, 7, 18, 7)
            row.layout().setSpacing(10)
            row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            row.setMinimumHeight(30)
            key = QLabel(title)
            key.setObjectName("LinkageMirrorJobKey")
            key.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            value = QLabel("-")
            value.setObjectName("LinkageMirrorJobVal")
            value.setWordWrap(False)
            value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            row.layout().addWidget(key, 1)
            row.layout().addWidget(value, 2)
            return row, value

        row1, self.linkageMirrorJob1 = _make_linked_job_row("Linked Job 1:")
        row2, self.linkageMirrorJob2 = _make_linked_job_row("Linked Job 2:")
        row3, self.linkageMirrorJob3 = _make_linked_job_row("Linked Job 3:")
        linkageLeft.layout().addWidget(row1)
        linkageLeft.layout().addWidget(row2)
        linkageLeft.layout().addWidget(row3)

        linkageRight = QFrame()
        linkageRight.setObjectName("LinkageMirrorRight")
        linkageRight.setLayout(QGridLayout())
        linkageRight.layout().setContentsMargins(0, 0, 0, 0)
        linkageRight.layout().setHorizontalSpacing(5)
        linkageRight.layout().setVerticalSpacing(10)

        def _make_counter_card(title: str):
            card = QFrame()
            card.setObjectName("LinkageMirrorCounterCard")
            card.setLayout(QHBoxLayout())
            card.layout().setContentsMargins(12, 8, 12, 8)
            card.layout().setSpacing(10)
            t = QLabel(title)
            t.setObjectName("LinkageMirrorCounterTitle")
            t.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            v = QLabel("0")
            v.setObjectName("LinkageMirrorCounterValue")
            v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            card.layout().addWidget(t, 1)
            card.layout().addWidget(v, 0)
            return card, v

        card_pack, self.linkageMirrorPack = _make_counter_card("Pack")
        card_good, self.linkageMirrorGood = _make_counter_card("Good")
        card_butal, self.linkageMirrorButal = _make_counter_card("Butal")
        card_total, self.linkageMirrorTotalGood = _make_counter_card("Total Good")
        linkageRight.layout().setColumnStretch(0, 1)
        linkageRight.layout().setColumnStretch(1, 1)
        linkageRight.layout().addWidget(card_pack, 0, 0)
        linkageRight.layout().addWidget(card_good, 0, 1)
        linkageRight.layout().addWidget(card_butal, 1, 0)
        linkageRight.layout().addWidget(card_total, 1, 1)

        linkageContent.layout().addWidget(linkageLeft, 1)
        linkageContent.layout().addWidget(linkageRight, 1)
        linkageBody.layout().addWidget(linkageContent)
        linkageCol.addWidget(linkageBody)
        linkageFrame.setMinimumHeight(170)
        linkageFrame.setStyleSheet(
            "QFrame#LinkageMirrorHost { background: transparent; border: none; }"
            "QFrame#LinkageMirrorBody {"
            " background: qradialgradient(cx:0.5, cy:0.34, radius:1.16, fx:0.5, fy:0.14,"
            "                           stop:0 rgba(121,125,135,232),"
            "                           stop:0.40 rgba(73,77,85,238),"
            "                           stop:1 rgba(24,26,31,246));"
            " border: 1px solid rgba(90,94,103,240);"
            " border-radius: 24px;"
            "}"
            "QFrame#LinkageMirrorLeft { background: transparent; border: none; }"
            "QFrame#LinkageMirrorHeader {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(108,112,121,228),"
            "                             stop:1 rgba(58,61,68,220));"
            " border: none;"
            " border-top-left-radius: 24px;"
            " border-top-right-radius: 24px;"
            " border-bottom: 1px solid rgba(146,151,162,95);"
            "}"
            "QFrame#LinkageMirrorHeader QLabel#RightTitle { color: #edf0f4; }"
            "QFrame#LinkageMirrorHeader QLabel { color: #edf0f4; }"
            "QWidget#LinkageMirrorContent { background: transparent; border: none; }"
            "QFrame#LinkageMirrorJobRow {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(103,107,115,220),"
            "                             stop:1 rgba(56,59,66,230));"
            " border: 1px solid #7a8089;"
            " border-radius: 16px;"
            "}"
            "QLabel#LinkageMirrorJobKey { color: #edf0f4; font-size: 13px; font-weight: 900; }"
            "QLabel#LinkageMirrorJobVal { color: #edf0f4; font-size: 16px; font-weight: 900; }"
            "QFrame#LinkageMirrorRight { background: transparent; border: none; }"
            "QFrame#LinkageMirrorCounterCard {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(103,107,115,220),"
            "                             stop:1 rgba(56,59,66,230));"
            " border: 1px solid #7a8089;"
            " border-radius: 10px;"
            " min-height: 40px;"
            " max-height: 40px;"
            "}"
            "QLabel#LinkageMirrorCounterTitle { color: #edf0f4; font-size: 13px; font-weight: 900; }"
            "QLabel#LinkageMirrorCounterValue { color: #f3f4f6; font-size: 18px; font-weight: 900; }"
        )
        linkageOuterLay.addWidget(linkageFrame)
        self.linkageMirrorOuter = linkageOuter
        self.linkageMirrorFrame = linkageFrame

        qtyOuter = QFrame()
        qtyOuter.setObjectName("RightCardOuter")
        qtyOuterLay = QVBoxLayout()
        qtyOuterLay.setContentsMargins(8, 0, 8, 8)
        qtyOuterLay.setSpacing(0)
        qtyOuter.setLayout(qtyOuterLay)

        qtyFrame = QFrame()
        qtyFrame.setObjectName("LinkageMirrorHost")
        qtyFrame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        qtyCol = QVBoxLayout()
        qtyCol.setContentsMargins(0, 0, 0, 0)
        qtyCol.setSpacing(6)
        qtyFrame.setLayout(qtyCol)
        qtyBody = QFrame()
        qtyBody.setObjectName("LinkageMirrorBody")
        qtyBody.setLayout(QVBoxLayout())
        qtyBody.layout().setContentsMargins(0, 0, 0, 10)
        qtyBody.layout().setSpacing(0)
        qtyHeader = QFrame()
        qtyHeader.setObjectName("LinkageMirrorHeader")
        qtyHeader.setLayout(QVBoxLayout())
        qtyHeader.layout().setContentsMargins(12, 10, 12, 10)
        qtyHeader.layout().setSpacing(0)
        qtyTitle = QLabel("Job Quantity Request")
        qtyTitle.setObjectName("RightTitle")
        qtyTitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qtyHeader.layout().addWidget(qtyTitle)
        qtyHeader.setMinimumHeight(shared_header_h)
        qtyBody.layout().addWidget(qtyHeader)

        qtyContent = QWidget()
        qtyContent.setObjectName("LinkageMirrorContent")
        qtyContent.setLayout(QVBoxLayout())
        qtyContent.layout().setContentsMargins(10, 10, 10, 12)
        qtyContent.layout().setSpacing(10)

        progress_card, self.linkageMirrorProduced = _make_counter_card("Produced")
        remaining_card, self.linkageMirrorRemaining = _make_counter_card("Remaining")
        overrun_card, self.linkageMirrorOverrun = _make_counter_card("Overrun")
        qtyContent.layout().addWidget(progress_card)
        qtyContent.layout().addWidget(remaining_card)
        qtyContent.layout().addWidget(overrun_card)
        qtyContent.layout().addStretch(1)
        qtyBody.layout().addWidget(qtyContent)
        qtyCol.addWidget(qtyBody)
        qtyFrame.setMinimumHeight(170)
        qtyFrame.setStyleSheet(linkageFrame.styleSheet())
        qtyOuterLay.addWidget(qtyFrame)
        self.jobQtyRequestOuter = qtyOuter
        self.jobQtyRequestFrame = qtyFrame

        def _make_history_card(header_text: str, column_title: str):
            outer = QFrame()
            outer.setObjectName("RightCardOuter")
            outer_lay = QVBoxLayout()
            outer_lay.setContentsMargins(8, 8, 8, 8)
            outer_lay.setSpacing(0)
            outer.setLayout(outer_lay)
            outer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            frame = QFrame()
            frame.setObjectName("HistoryMirrorHost")
            frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            frame_lay = QVBoxLayout()
            frame_lay.setContentsMargins(0, 0, 0, 0)
            frame_lay.setSpacing(6)
            frame.setLayout(frame_lay)

            body = QFrame()
            body.setObjectName("HistoryMirrorBody")
            body.setLayout(QVBoxLayout())
            body.layout().setContentsMargins(0, 0, 0, 10)
            body.layout().setSpacing(10)

            header = QFrame()
            header.setObjectName("HistoryMirrorHeader")
            header.setLayout(QVBoxLayout())
            header.layout().setContentsMargins(12, 10, 12, 10)
            header.layout().setSpacing(0)
            title = QLabel(header_text)
            title.setObjectName("RightTitle")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header.layout().addWidget(title)
            body.layout().addWidget(header)

            content = QWidget()
            content.setObjectName("HistoryMirrorContent")
            content.setLayout(QVBoxLayout())
            content.layout().setContentsMargins(10, 0, 10, 10)
            content.layout().setSpacing(0)

            col = HistoryAnimatedColumn(column_title, content)
            col.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            if hasattr(col, "colTitle") and col.colTitle is not None:
                col.colTitle.hide()
            content.layout().addWidget(col, 1)
            body.layout().addWidget(content, 1)

            frame_lay.addWidget(body, 1)
            frame.setStyleSheet(
                "QFrame#HistoryMirrorHost { background: transparent; border: none; }"
                "QFrame#HistoryMirrorBody {"
                " background: qradialgradient(cx:0.5, cy:0.34, radius:1.16, fx:0.5, fy:0.14,"
                "                           stop:0 rgba(121,125,135,232),"
                "                           stop:0.40 rgba(73,77,85,238),"
                "                           stop:1 rgba(24,26,31,246));"
                " border: 1px solid rgba(90,94,103,240);"
                " border-radius: 24px;"
                "}"
                "QFrame#HistoryMirrorHeader {"
                " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
                "                             stop:0 rgba(108,112,121,228),"
                "                             stop:1 rgba(58,61,68,220));"
                " border: none;"
                " border-top-left-radius: 24px;"
                " border-top-right-radius: 24px;"
                " border-bottom: 1px solid rgba(146,151,162,95);"
                "}"
                "QFrame#HistoryMirrorHeader QLabel#RightTitle { color: #edf0f4; }"
                "QFrame#HistoryMirrorHeader QLabel { color: #edf0f4; }"
                "QWidget#HistoryMirrorContent { background: transparent; border: none; }"
                "QFrame#HistoryCol { background: rgba(77,81,89,165); border: 1px solid rgba(132,137,148,110); border-radius: 12px; }"
                "QFrame#HistoryLatestCard { background: rgba(102,106,114,200); border: 1px solid rgba(132,137,148,110); border-radius: 10px; }"
                "QFrame#HistoryRecentPanel { background: transparent; border: none; }"
                "QFrame#HistoryRecentRow { background: rgba(102,106,114,188); border: 1px solid rgba(132,137,148,90); border-radius: 10px; }"
            )
            outer_lay.addWidget(frame, 1)
            return outer, col

        self.historyRowOuter = QFrame()
        self.historyRowOuter.setObjectName("HistoryRowOuter")
        self.historyRowOuter.setStyleSheet("QFrame#HistoryRowOuter { background: transparent; border: none; }")
        self.historyRowOuter.setLayout(QHBoxLayout())
        self.historyRowOuter.layout().setContentsMargins(0, 0, 0, 0)
        self.historyRowOuter.layout().setSpacing(6)
        self.historyRowOuter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.productionHistoryOuter, self.historyPackCol = _make_history_card("Production", "Pack/Good/Butal/Reject")
        self.partsHistoryOuter, self.historyRawCol = _make_history_card("Parts History", "Raw Materials (Recent)")
        self.actionsHistoryOuter, self.historyActionCol = _make_history_card("Last Action", "Last Actions")
        self.historyRowOuter.layout().addWidget(self.productionHistoryOuter, 1)
        self.historyRowOuter.layout().addWidget(self.partsHistoryOuter, 1)
        self.historyRowOuter.layout().addWidget(self.actionsHistoryOuter, 1)

        self.rightTopRow = QWidget()
        self.rightTopRow.setStyleSheet("background: transparent;")
        self.rightTopRow.setLayout(QHBoxLayout())
        self.rightTopRow.layout().setContentsMargins(0, 0, 0, 0)
        self.rightTopRow.layout().setSpacing(6)
        self.rightTopRow.layout().addWidget(linkageOuter, 2)
        self.rightTopRow.layout().addWidget(qtyOuter, 1)

        # Show Linkage above Product Parts in the right panel.
        rightLayout.addWidget(self.rightTopRow)
        rightLayout.addSpacing(6)
        rightLayout.addWidget(self.cardJobDetailsOuter)
        rightLayout.addSpacing(6)
        rightLayout.addWidget(self.historyRowOuter, 1)

        # Swap positions: place Raw Materials + Cycle Monitor where Job Details used to be.
        rawCycleSwapWrap = QWidget()
        rawCycleSwapWrap.setLayout(rawDowntimeCol)
        rawCycleSwapWrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        rawCycleSwapWrap.setMinimumHeight(440)
        rawCycleSwapWrap.setStyleSheet("background: transparent;")
        self.rawCycleSwapWrap = rawCycleSwapWrap
        grid.addWidget(rawCycleSwapWrap, 3, 0, 1, 2)

        contentRow = QHBoxLayout()
        contentRow.setContentsMargins(0, 0, 0, 0)
        contentRow.setSpacing(8)
        contentRow.addWidget(leftWrap, 1)
        contentRow.addWidget(self.rightPanel, 1)

        self.topSafeSpacer = QWidget()
        self.topSafeSpacer.setFixedHeight(0)
        self.topSafeSpacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.topSafeSpacer.setStyleSheet("background: transparent;")
        root.addWidget(self.topSafeSpacer)
        root.addWidget(self.headerCard)
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
        self.productionOverlay.layout().setContentsMargins(0, 16, 0, 16)
        self.productionOverlay.layout().setSpacing(12)
        self.productionOverlay.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.productionTitle = QLabel("PRODUCTION DAILY REPORT")
        self.productionTitle.setStyleSheet("color: #f8fafc; font-size: 24px; font-weight: 900;")
        self.productionTitle.setFixedWidth(552)
        self.productionTitle.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.productionOverlay.layout().addWidget(self.productionTitle, 0, Qt.AlignmentFlag.AlignHCenter)
        self.productionHint = QLabel("Scan reason QR code (01-15)")
        self.productionHint.setStyleSheet("color: #cbd5e1; font-size: 14px; font-weight: 700;")
        self.productionOverlay.layout().addWidget(self.productionHint)
        self.productionReasonList = QWidget()
        self.productionReasonList.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.productionReasonList.setLayout(QGridLayout())
        self.productionReasonList.layout().setContentsMargins(14, 2, 14, 2)
        self.productionReasonList.layout().setSpacing(8)
        self.productionReasonCards: List[QFrame] = []
        self.productionReasonCodes: List[str] = []
        self.productionReasonCodeLabels: List[QLabel] = []
        self.productionReasonIconLabels: List[QLabel] = []
        self.productionReasonTextLabels: List[QLabel] = []
        for idx, (code, label) in enumerate(PRODUCTION_DAILY_REPORT_ITEMS):
            card = QFrame()
            card.setObjectName("ProductionReasonCard")
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            card.setStyleSheet(
                "QFrame#ProductionReasonCard {"
                "background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
                "                        stop:0 rgba(103,107,115,220),"
                "                        stop:1 rgba(56,59,66,230));"
                "border: 1px solid rgba(148,163,184,0.55);"
                "border-radius: 12px;"
                "}"
            )
            card_shadow = QGraphicsDropShadowEffect(card)
            card_shadow.setBlurRadius(16)
            card_shadow.setOffset(0, 3)
            card_shadow.setColor(QColor(15, 23, 42, 45))
            card.setGraphicsEffect(card_shadow)
            card.setLayout(QVBoxLayout())
            card.layout().setContentsMargins(6, 6, 6, 5)
            card.layout().setSpacing(7)
            iconLabel = QLabel()
            iconLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
            iconLabel.setFixedHeight(60)
            icon_path = self._find_pdr_reason_icon_path(code)
            if icon_path:
                pm = QPixmap(icon_path)
                if not pm.isNull():
                    pm = pm.scaled(
                        55,
                        55,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    iconLabel.setPixmap(pm)
            codeLabel = QLabel(code, card)
            codeLabel.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            codeLabel.setContentsMargins(0, 0, 0, 0)
            codeLabel.setStyleSheet("color: #f59e0b; font-size: 32px; font-weight: 900;")
            codeLabel.adjustSize()
            codeLabel.raise_()
            textLabel = QLabel(label)
            textLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
            textLabel.setWordWrap(True)
            textLabel.setContentsMargins(0, 8, 0, 0)
            textLabel.setStyleSheet("color: #f8fafc; font-size: 15px; font-weight: 800;")
            card.layout().addWidget(iconLabel, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            card.layout().addWidget(textLabel, 1)
            self.productionReasonList.layout().addWidget(card, idx // 5, idx % 5)
            self.productionReasonCards.append(card)
            self.productionReasonCodes.append(code)
            self.productionReasonCodeLabels.append(codeLabel)
            self.productionReasonIconLabels.append(iconLabel)
            self.productionReasonTextLabels.append(textLabel)
        for col in range(5):
            self.productionReasonList.layout().setColumnStretch(col, 1)
        self.productionOverlay.layout().addWidget(self.productionReasonList)

        self.productionLiveReason = QLabel("Reason: -")
        self.productionLiveReason.setObjectName("ProductionLiveReason")
        self.productionLiveReason.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.productionLiveReason.setWordWrap(True)
        self.productionLiveReason.setFixedSize(538, 42)
        self.productionOverlay.layout().addWidget(self.productionLiveReason)

        self.productionMaintenanceLine = QLabel("Maintenance: -")
        self.productionMaintenanceLine.setObjectName("ProductionLiveReason")
        self.productionMaintenanceLine.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.productionMaintenanceLine.setWordWrap(True)
        self.productionMaintenanceLine.setFixedSize(538, 42)
        self.productionOverlay.layout().addWidget(self.productionMaintenanceLine)

        self.productionTimerPanelWrap = QWidget()
        self.productionTimerPanelWrap.setStyleSheet("background: transparent;")
        self.productionTimerPanelWrap.setLayout(QHBoxLayout())
        self.productionTimerPanelWrap.layout().setContentsMargins(8, 4, 8, 4)
        self.productionTimerPanelWrap.layout().setSpacing(22)

        self.productionWaitingPanel = QFrame()
        self.productionWaitingPanel.setStyleSheet(
            "background: #2f343f; border: none; border-radius: 16px; padding: 6px 10px;"
        )
        self.productionWaitingPanel.setFixedSize(257, 120)
        self.productionWaitingPanel.setLayout(QVBoxLayout())
        self.productionWaitingPanel.layout().setContentsMargins(10, 8, 10, 8)
        self.productionWaitingPanel.layout().setSpacing(0)
        self.productionWaitingIndicatorRow = QWidget()
        self.productionWaitingIndicatorRow.setStyleSheet("background: transparent;")
        self.productionWaitingIndicatorRow.setLayout(QHBoxLayout())
        self.productionWaitingIndicatorRow.layout().setContentsMargins(0, 0, 0, 0)
        self.productionWaitingIndicatorRow.layout().setSpacing(0)
        self.productionWaitingLabel = QLabel("WAITING TIME")
        self.productionWaitingLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.productionWaitingValue = QLabel("00:00:00")
        self.productionWaitingValue.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.productionWaitingPanel.layout().addWidget(self.productionWaitingLabel)
        self.productionWaitingPanel.layout().addWidget(self.productionWaitingValue)

        self.productionDowntimePanel = QFrame()
        self.productionDowntimePanel.setStyleSheet(
            "background: #2f343f; border: none; border-radius: 16px; padding: 6px 10px;"
        )
        self.productionDowntimePanel.setFixedSize(257, 120)
        self.productionDowntimePanel.setLayout(QVBoxLayout())
        self.productionDowntimePanel.layout().setContentsMargins(10, 8, 10, 8)
        self.productionDowntimePanel.layout().setSpacing(0)
        self.productionDowntimeIndicatorRow = QWidget()
        self.productionDowntimeIndicatorRow.setStyleSheet("background: transparent;")
        self.productionDowntimeIndicatorRow.setLayout(QHBoxLayout())
        self.productionDowntimeIndicatorRow.layout().setContentsMargins(0, 0, 0, 0)
        self.productionDowntimeIndicatorRow.layout().setSpacing(0)
        self.productionDowntimeLabel = QLabel("DOWNTIME")
        self.productionDowntimeLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.productionDowntimeValue = QLabel("00:00:00")
        self.productionDowntimeValue.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.productionDowntimePanel.layout().addWidget(self.productionDowntimeLabel)
        self.productionDowntimePanel.layout().addWidget(self.productionDowntimeValue)

        self.productionTimerPanelWrap.layout().addWidget(self.productionWaitingPanel, 1)
        self.productionTimerPanelWrap.layout().addWidget(self.productionDowntimePanel, 1)
        self.productionOverlay.layout().addWidget(self.productionTimerPanelWrap)
        self._apply_production_timer_fonts()

        self.productionOverlay.layout().removeWidget(self.productionLiveReason)
        self.productionOverlay.layout().removeWidget(self.productionMaintenanceLine)
        self.productionOverlay.layout().addWidget(self.productionLiveReason, 0, Qt.AlignmentFlag.AlignHCenter)
        self.productionOverlay.layout().addWidget(self.productionMaintenanceLine, 0, Qt.AlignmentFlag.AlignHCenter)

        self.productionActionBanner = QLabel('SCAN PDR DONE QR WHEN\nREPAIR IS DONE')
        self.productionActionBanner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.productionActionBanner.setWordWrap(True)
        self.productionActionBanner.setFixedSize(292, 66)
        self.productionOverlay.layout().addWidget(self.productionActionBanner, 0, Qt.AlignmentFlag.AlignHCenter)
        self.productionOverlay.layout().addSpacing(14)

        self.productionRepairZone = QFrame()
        self.productionRepairZone.setObjectName("ProductionRepairZone")
        self.productionRepairZone.setFixedHeight(206)
        self.productionRepairZone.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.productionRepairZone.setLayout(QVBoxLayout())
        self.productionRepairZone.layout().setContentsMargins(0, 0, 0, 0)
        self.productionRepairZone.layout().setSpacing(0)
        self.productionRepairZoneTopStripe = HazardStripeWidget(self.productionRepairZone)
        self.productionRepairZoneBody = QFrame(self.productionRepairZone)
        self.productionRepairZoneBody.setObjectName("ProductionRepairZoneBody")
        self.productionRepairZoneBody.setLayout(QVBoxLayout())
        self.productionRepairZoneBody.layout().setContentsMargins(0, 12, 0, 12)
        self.productionRepairZoneBody.layout().setSpacing(0)
        self.productionRepairZoneBottomStripe = HazardStripeWidget(self.productionRepairZone)
        self.productionRepairZone.layout().addWidget(self.productionRepairZoneTopStripe)
        self.productionRepairZone.layout().addWidget(self.productionRepairZoneBody)
        self.productionRepairZone.layout().addWidget(self.productionRepairZoneBottomStripe)
        self.productionOverlay.layout().addWidget(self.productionRepairZone)

        self.productionFixAnim = MachineFixingAnimation(self.productionRepairZoneBody)
        self.productionFixAnim.setObjectName("ProductionFixAnim")
        self.productionRepairZoneBody.layout().addWidget(self.productionFixAnim, 0, Qt.AlignmentFlag.AlignCenter)

        self.productionMarqueeWrap = QWidget()
        self.productionMarqueeWrap.setObjectName("ProductionMarqueeWrap")
        self.productionMarqueeWrap.setFixedWidth(420)
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
        self.productionOverlay.layout().addWidget(self.productionMarqueeWrap, 0, Qt.AlignmentFlag.AlignHCenter)
        self.productionMarqueeWrap.hide()

        self.resolveOverlay = QFrame(self)
        self.resolveOverlay.setObjectName("ProductionOverlay")
        self.resolveOverlay.setStyleSheet(
            "QFrame#ProductionOverlay {"
            "background: qradialgradient(cx:0.5, cy:0.12, radius:1.2, fx:0.5, fy:0.02,"
            "stop:0 rgba(112,116,124,242), stop:0.38 rgba(70,74,82,244), stop:1 rgba(24,26,31,248));"
            "border: 1px solid rgba(124,130,140,235); border-radius: 28px; }"
            "QFrame#ResolveInfoCard {"
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(103,107,115,220), stop:1 rgba(56,59,66,230));"
            "border: 1px solid rgba(148,163,184,0.45); border-radius: 20px; }"
            "QLabel#ResolveInfoTitle { color: transparent; font-size: 1px; }"
            "QLabel#ResolveInfoValue { color: #f8fafc; font-size: 24px; font-weight: 500; border: none; background: transparent; }"
        )
        self.resolveOverlay.setLayout(QVBoxLayout())
        self.resolveOverlay.layout().setContentsMargins(22, 18, 22, 20)
        self.resolveOverlay.layout().setSpacing(14)
        self.resolveOverlay.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.resolveTitle = QLabel("DOWNTIME RESOLUTION")
        self.resolveTitle.setStyleSheet("color: #f8fafc; font-size: 24px; font-weight: 700; background: transparent; border: none;")
        self.resolveTitle.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.resolveHint = QLabel("Scan cycle time digits (num_0..num_9), backspace, then confirm")
        self.resolveHint.setStyleSheet(
            "color: #ffffff; font-size: 21px; font-weight: 900;"
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(85,167,245,230), stop:1 rgba(48,118,193,238));"
            "border: 1px solid rgba(191,219,254,120); border-radius: 22px; padding: 14px 22px;"
        )
        self.resolveHint.setWordWrap(True)
        self.resolveHint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.resolveHint.setFixedSize(364, 78)
        self.resolveOldCycle = QLabel("Old Cycle Time: -")
        self.resolveOldCycle.setObjectName("ResolveInfoValue")
        self.resolveOldCycle.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.resolveNewCycle = QLabel("Cycle Time: ")
        self.resolveNewCycle.setObjectName("ResolveInfoValue")
        self.resolveNewCycle.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.resolveOldCycleTitle = QLabel("REFERENCE")
        self.resolveOldCycleTitle.setObjectName("ResolveInfoTitle")
        self.resolveNewCycleTitle = QLabel("CURRENT INPUT")
        self.resolveNewCycleTitle.setObjectName("ResolveInfoTitle")
        self.resolveOldCard = QFrame()
        self.resolveOldCard.setObjectName("ResolveInfoCard")
        self.resolveOldCard.setLayout(QVBoxLayout())
        self.resolveOldCard.setFixedHeight(52)
        self.resolveOldCard.layout().setContentsMargins(20, 10, 20, 10)
        self.resolveOldCard.layout().setSpacing(0)
        self.resolveOldCard.layout().addWidget(self.resolveOldCycleTitle)
        self.resolveOldCard.layout().addWidget(self.resolveOldCycle)
        self.resolveNewCard = QFrame()
        self.resolveNewCard.setObjectName("ResolveInfoCard")
        self.resolveNewCard.setLayout(QVBoxLayout())
        self.resolveNewCard.setFixedHeight(52)
        self.resolveNewCard.layout().setContentsMargins(20, 10, 20, 10)
        self.resolveNewCard.layout().setSpacing(0)
        self.resolveNewCard.layout().addWidget(self.resolveNewCycleTitle)
        self.resolveNewCard.layout().addWidget(self.resolveNewCycle)
        self.resolveOverlay.layout().addWidget(self.resolveTitle)
        self.resolveOverlay.layout().addWidget(self.resolveOldCard)
        self.resolveOverlay.layout().addWidget(self.resolveNewCard)
        self.resolveOverlay.layout().addSpacing(4)
        self.resolveOverlay.layout().addWidget(self.resolveHint, 0, Qt.AlignmentFlag.AlignHCenter)
        self._apply_widget_shadow(self.resolveOldCard, 26, 8, QColor(15, 23, 42, 55))
        self._apply_widget_shadow(self.resolveNewCard, 26, 8, QColor(15, 23, 42, 55))
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
        self.rawMatsHint.setStyleSheet("color: #cbd5e1; font-size: 14px; font-weight: 700;")
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
            "QTableWidget { background: rgba(32,35,41,0.88); border: 1px solid rgba(148,163,184,0.45);"
            " border-radius: 10px; gridline-color: rgba(148,163,184,0.28); color: #f8fafc; }"
            "QHeaderView::section { background: rgba(88,92,101,0.92); color: #f8fafc; font-weight: 800;"
            " border: none; border-bottom: 1px solid rgba(148,163,184,0.5); padding: 6px; }"
        )
        self.rawMatsOverlay.setStyleSheet(
            "QFrame#ProductionOverlay {"
            "background: qradialgradient(cx:0.5, cy:0.12, radius:1.2, fx:0.5, fy:0.02,"
            "stop:0 rgba(112,116,124,242), stop:0.38 rgba(70,74,82,244), stop:1 rgba(24,26,31,248));"
            "border: 1px solid rgba(124,130,140,235); border-radius: 22px; }"
            "QLabel { color: #f8fafc; }"
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
        self.rejectSummaryTitle.setStyleSheet("color: #f8fafc; font-size: 22px; font-weight: 900;")
        self.rejectSummaryHint = QLabel('Scan "rejectsummary" again to refresh')
        self.rejectSummaryHint.setStyleSheet("color: #cbd5e1; font-size: 14px; font-weight: 700;")
        self.rejectSummaryStamp = QLabel("Scanned at: -")
        self.rejectSummaryStamp.setObjectName("MetaValue")
        self.rejectSummaryConfirmedBy = QLabel("Confirmed by: -")
        self.rejectSummaryConfirmedBy.setObjectName("MetaValue")
        self.rejectSummaryTotals = QLabel("Reject Total: 0 | Start Up Reject: 0")
        self.rejectSummaryTotals.setObjectName("MetaValue")
        self.rejectSummaryDetails = QTableWidget(0, 3)
        self.rejectSummaryDetails.setHorizontalHeaderLabels(["Reason", "Operator", "Timestamp"])
        self.rejectSummaryDetails.setAlternatingRowColors(False)
        self.rejectSummaryDetails.setWordWrap(False)
        self.rejectSummaryDetails.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rejectSummaryDetails.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.rejectSummaryDetails.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rejectSummaryDetails.verticalHeader().setVisible(False)
        self.rejectSummaryDetails.verticalHeader().setDefaultSectionSize(32)
        self.rejectSummaryDetails.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.rejectSummaryDetails.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.rejectSummaryDetails.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.rejectSummaryDetails.setMinimumHeight(260)
        self.rejectSummaryDetails.setStyleSheet(
            "QTableWidget { background: rgba(32,35,41,0.88); border: 1px solid rgba(148,163,184,0.45);"
            " border-radius: 10px; gridline-color: rgba(148,163,184,0.28); }"
            "QHeaderView::section { background: rgba(88,92,101,0.92); color: #f8fafc; font-weight: 900;"
            " border: none; border-bottom: 1px solid rgba(148,163,184,0.5); padding: 6px; }"
            "QTableWidget::item { padding: 6px; color: #f8fafc; font-weight: 800; }"
        )
        self.rejectSummaryOverlay.setStyleSheet(
            "QFrame#ProductionOverlay {"
            "background: qradialgradient(cx:0.5, cy:0.12, radius:1.2, fx:0.5, fy:0.02,"
            "stop:0 rgba(112,116,124,242), stop:0.38 rgba(70,74,82,244), stop:1 rgba(24,26,31,248));"
            "border: 1px solid rgba(124,130,140,235); border-radius: 22px; }"
            "QLabel { color: #f8fafc; }"
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
        self.finishTitle.setStyleSheet("color: #f8fafc; font-size: 26px; font-weight: 900; background: transparent; border: none;")
        self.finishTitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.finishStatus = QLabel("Processing...")
        self.finishStatus.setStyleSheet("color: #dbeafe; font-size: 16px; font-weight: 800; background: transparent; border: none;")
        self.finishStatus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.finishReviewHint = QLabel(
            'Scan "next" / "prev" QR to move the review, then scan Supervisor QR to approve this finished shift.'
        )
        self.finishReviewHint.setStyleSheet(
            "color: #ffffff; font-size: 17px; font-weight: 900;"
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(85,167,245,230), stop:1 rgba(48,118,193,238));"
            "border: 1px solid rgba(191,219,254,120); border-radius: 22px; padding: 12px 20px;"
        )
        self.finishReviewHint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.finishReviewHint.setWordWrap(True)
        self.finishReviewHint.hide()
        self.finishProgressBar = QProgressBar()
        self.finishProgressBar.setRange(0, 100)
        self.finishProgressBar.setValue(0)
        self.finishProgressBar.setTextVisible(False)
        self.finishProgressBar.setFixedWidth(300)
        self.finishSummaryScroll = QScrollArea()
        self.finishSummaryScroll.setWidgetResizable(True)
        self.finishSummaryScroll.setFrameShape(QFrame.Shape.NoFrame)
        self.finishSummaryScroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:vertical { width: 0px; background: transparent; }"
            "QScrollBar::handle:vertical { background: transparent; min-height: 0px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )
        self.finishSummaryScroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.finishSummaryScroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.finishSummaryBody = QWidget()
        self.finishSummaryBody.setLayout(QVBoxLayout())
        self.finishSummaryBody.layout().setContentsMargins(4, 4, 4, 4)
        self.finishSummaryBody.layout().setSpacing(10)
        self.finishSummaryScroll.setWidget(self.finishSummaryBody)
        self.finishSummaryScroll.hide()

        self.finishSummaryCards: Dict[str, QLabel] = {}
        finish_card_grid = QGridLayout()
        finish_card_grid.setContentsMargins(0, 0, 0, 0)
        finish_card_grid.setHorizontalSpacing(8)
        finish_card_grid.setVerticalSpacing(8)
        for idx, title in enumerate((
            "Machine", "Job", "Operator", "Shift Window",
            "Pack Count", "Good", "Butal", "Reject",
            "Total Good", "Raw Sacks", "Cycle Time", "Downtime",
        )):
            card = QFrame()
            card.setStyleSheet(
                "QFrame {"
                "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(103,107,115,220), stop:1 rgba(56,59,66,230));"
                "border: 1px solid rgba(148,163,184,0.45); border-radius: 14px; }"
                "QLabel[role='title'] { color: #cbd5e1; font-size: 11px; font-weight: 900; background: transparent; border: none; }"
                "QLabel[role='value'] { color: #f8fafc; font-size: 15px; font-weight: 900; background: transparent; border: none; }"
            )
            card.setLayout(QVBoxLayout())
            card.layout().setContentsMargins(10, 8, 10, 8)
            card.layout().setSpacing(2)
            title_lbl = QLabel(title)
            title_lbl.setProperty("role", "title")
            value_lbl = QLabel("-")
            value_lbl.setProperty("role", "value")
            value_lbl.setWordWrap(True)
            card.layout().addWidget(title_lbl)
            card.layout().addWidget(value_lbl)
            finish_card_grid.addWidget(card, idx // 4, idx % 4)
            self.finishSummaryCards[title] = value_lbl
        self.finishSummaryBody.layout().addLayout(finish_card_grid)

        self.finishReviewJobDetails = self._make_finish_summary_table(
            "Job Details",
            ["Field", "Value"],
        )
        self.finishReviewCounters = self._make_finish_summary_table(
            "Production Counters",
            ["Counter", "Value"],
        )
        self.finishReviewRejects = self._make_finish_summary_table(
            "Reject Details",
            ["Reject", "Qty"],
        )
        self.finishReviewDowntime = self._make_finish_summary_table(
            "Downtime / Approval",
            ["Field", "Value"],
        )
        self.finishReviewParts = self._make_finish_summary_table(
            "Product Parts Used",
            ["SKU", "Name", "Qty/Unit", "Scanned", "Requested", "Remaining"],
        )
        self.finishReviewRaw = self._make_finish_summary_table(
            "Raw Materials",
            ["Material", "Qty", "Index", "Total", "Lot", "PO", "Scanned At"],
        )
        self.finishReviewPack = self._make_finish_summary_table(
            "Pack Scan History",
            ["Index", "Product", "Qty", "Lot", "Operator", "Scanned At"],
        )
        self.finishSuccessRow = QWidget()
        self.finishSuccessRow.setObjectName("FinishSuccessRow")
        self.finishSuccessRow.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.finishSuccessRow.setStyleSheet("background: transparent;")
        self.finishSuccessRow.setLayout(QHBoxLayout())
        self.finishSuccessRow.layout().setContentsMargins(0, 0, 0, 0)
        self.finishSuccessRow.layout().setSpacing(10)
        self.finishSuccessRow.layout().setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.finishCheck = SuccessCheck(size=64, parent=self.finishSuccessRow)
        self.finishCross = FailureCross(size=64, parent=self.finishSuccessRow)
        self.finishCross.hide()
        self.finishDoneText = QLabel("Success")
        self.finishDoneText.setObjectName("FinishDoneText")
        self.finishDoneText.setStyleSheet("background: transparent; color: #166534; font-size: 20px; font-weight: 900;")
        self.finishSuccessRow.layout().addWidget(self.finishCheck, 0, Qt.AlignmentFlag.AlignVCenter)
        self.finishSuccessRow.layout().addWidget(self.finishCross, 0, Qt.AlignmentFlag.AlignVCenter)
        self.finishSuccessRow.layout().addWidget(self.finishDoneText, 0, Qt.AlignmentFlag.AlignVCenter)
        self.finishSuccessRow.hide()
        self.finishOverlay.layout().addWidget(self.finishTitle)
        self.finishOverlay.layout().addWidget(self.finishStatus)
        self.finishOverlay.layout().addWidget(self.finishReviewHint)
        self.finishOverlay.layout().addWidget(self.finishProgressBar, 0, Qt.AlignmentFlag.AlignCenter)
        self.finishOverlay.layout().addWidget(self.finishSummaryScroll)
        self.finishOverlay.layout().addWidget(self.finishSuccessRow, 0, Qt.AlignmentFlag.AlignCenter)
        self.finishOverlay.setStyleSheet(
            "QFrame#ProductionOverlay {"
            "background: qradialgradient(cx:0.5, cy:0.12, radius:1.2, fx:0.5, fy:0.02,"
            "stop:0 rgba(112,116,124,242), stop:0.38 rgba(70,74,82,244), stop:1 rgba(24,26,31,248));"
            "border: 1px solid rgba(124,130,140,235); border-radius: 28px; }"
            "QWidget#FinishSuccessRow { background: transparent; border: none; }"
            "QLabel#FinishDoneText { background: transparent; border: none; }"
            "QProgressBar {"
            "border: 1px solid rgba(34,197,94,0.85); border-radius: 10px; background: rgba(15,23,42,0.65); min-height: 16px; }"
            "QProgressBar::chunk {"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #16a34a, stop:1 #22c55e);"
            "border-radius: 8px; }"
        )
        self.finishOverlay.hide()
        self.finishOverlay.raise_()
        self._finish_anim_timer = QTimer(self)
        self._finish_anim_timer.setInterval(75)
        self._finish_anim_timer.timeout.connect(self._tick_finish_anim)
        self._finish_anim_value = 0
        self._finish_anim_running = False
        self._finish_pending_clear = False
        self._finish_post_action = ""
        self._supervisor_validation_pending = False
        self._supervisor_validation_failed_value = ""
        self._fulfilled_notice_job_code = ""
        self._fulfilled_notice_active = False
        self._fulfilled_notice_timer = QTimer(self)
        self._fulfilled_notice_timer.setSingleShot(True)
        self._fulfilled_notice_timer.timeout.connect(self._clear_fulfilled_notice)
        self._operator_shift_flash_active = False
        self._operator_shift_flash_timer = QTimer(self)
        self._operator_shift_flash_timer.setSingleShot(True)
        self._operator_shift_flash_timer.timeout.connect(self._hide_operator_shift_overlay)
        self._pending_shift_review_payload: Optional[Dict[str, Any]] = None

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
        self.graphicsModeLabel = QLabel("Graphics Mode")
        self.graphicsModeLabel.setObjectName("MetaLabel")
        self.graphicsModeToggle = GraphicsModeToggle()
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
        self.settingsGraphicsSection.layout().addWidget(self.graphicsModeLabel)
        self.settingsGraphicsSection.layout().addWidget(self.graphicsModeToggle, 0, Qt.AlignmentFlag.AlignLeft)
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
        self.graphicsModeToggle.modeChanged.connect(self._apply_graphics_settings)
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
        self.settingsOverlay.setStyleSheet(
            "QFrame#SettingsOverlay {"
            " background: rgba(7,10,16,110);"
            " border: none;"
            "}"
            "QFrame#SettingsShell {"
            " background: qradialgradient(cx:0.50, cy:0.10, radius:1.25, fx:0.50, fy:0.05,"
            "                           stop:0 rgba(112,116,124,242),"
            "                           stop:0.38 rgba(70,74,82,244),"
            "                           stop:1 rgba(24,26,31,248));"
            " border: 1px solid rgba(124,130,140,235);"
            " border-radius: 24px;"
            "}"
            "QFrame#SettingsNav {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(80,84,92,232),"
            "                             stop:1 rgba(42,45,51,236));"
            " border: none;"
            " border-top-left-radius: 24px;"
            " border-bottom-left-radius: 24px;"
            " border-right: 1px solid rgba(156,163,175,85);"
            "}"
            "QLabel#SettingsNavTitle {"
            " color: #f8fafc;"
            " font-size: 18px;"
            " font-weight: 900;"
            " letter-spacing: 0.8px;"
            " padding: 4px 6px 10px 6px;"
            "}"
            "QPushButton#SettingsNavButton {"
            " min-height: 42px;"
            " padding: 0 16px;"
            " text-align: left;"
            " color: #e5e7eb;"
            " font-size: 16px;"
            " font-weight: 900;"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(87,91,99,208),"
            "                             stop:1 rgba(54,57,64,220));"
            " border: 1px solid rgba(154,160,170,110);"
            " border-radius: 14px;"
            "}"
            "QPushButton#SettingsNavButton:hover {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(103,107,115,220),"
            "                             stop:1 rgba(62,65,72,228));"
            "}"
            "QPushButton#SettingsNavButton:checked {"
            " color: #ffffff;"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(117,121,129,230),"
            "                             stop:1 rgba(70,74,82,236));"
            " border: 1px solid rgba(229,231,235,165);"
            "}"
            "QFrame#SettingsContent {"
            " background: transparent;"
            " border: none;"
            "}"
            "QLabel#SettingsContentTitle {"
            " color: #f8fafc;"
            " font-size: 28px;"
            " font-weight: 900;"
            " letter-spacing: 0.3px;"
            "}"
            "QPushButton#SettingsCloseX {"
            " min-width: 44px;"
            " max-width: 44px;"
            " min-height: 44px;"
            " max-height: 44px;"
            " color: #f8fafc;"
            " font-size: 22px;"
            " font-weight: 900;"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(97,101,110,220),"
            "                             stop:1 rgba(58,61,69,232));"
            " border: 1px solid rgba(203,213,225,130);"
            " border-radius: 14px;"
            "}"
            "QPushButton#SettingsCloseX:hover {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(113,117,126,228),"
            "                             stop:1 rgba(70,74,82,236));"
            "}"
            "QFrame#SettingsContentDivider {"
            " color: rgba(226,232,240,70);"
            " background: rgba(226,232,240,70);"
            " min-height: 1px;"
            " max-height: 1px;"
            " border: none;"
            "}"
            "QWidget#SettingsPage {"
            " background: transparent;"
            " border: none;"
            "}"
            "QLabel#MetaLabel {"
            " color: #cbd5e1;"
            " font-size: 14px;"
            " font-weight: 900;"
            " letter-spacing: 1.1px;"
            " text-transform: uppercase;"
            "}"
            "QPushButton#SettingToggle {"
            " min-height: 42px;"
            " padding: 0 16px;"
            " text-align: left;"
            " color: #f8fafc;"
            " font-size: 15px;"
            " font-weight: 900;"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(92,96,105,214),"
            "                             stop:1 rgba(55,58,66,224));"
            " border: 1px solid rgba(148,163,184,130);"
            " border-radius: 14px;"
            "}"
            "QPushButton#SettingToggle:disabled {"
            " color: #f8fafc;"
            "}"
            "QPushButton#SettingToggle:hover {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(108,112,121,224),"
            "                             stop:1 rgba(63,66,74,232));"
            "}"
            "QLineEdit, QComboBox {"
            " min-height: 40px;"
            " padding: 0 12px;"
            " color: #f8fafc;"
            " font-size: 14px;"
            " font-weight: 800;"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "                             stop:0 rgba(86,90,98,214),"
            "                             stop:1 rgba(48,51,58,224));"
            " border: 1px solid rgba(148,163,184,120);"
            " border-radius: 12px;"
            " selection-background-color: rgba(59,130,246,180);"
            "}"
            "QComboBox::drop-down {"
            " subcontrol-origin: padding;"
            " subcontrol-position: top right;"
            " width: 28px;"
            " border: none;"
            " background: transparent;"
            "}"
            "QComboBox QAbstractItemView {"
            " color: #f8fafc;"
            " background: rgba(31,41,55,245);"
            " border: 1px solid rgba(148,163,184,130);"
            " selection-background-color: rgba(71,85,105,220);"
            "}"
        )
        self._load_api_settings_form()
        self._load_graphics_settings_form()
        self._show_settings_section("graphics")
        self.settingsOverlay.hide()
        self.settingsOverlay.raise_()
        self._apply_graphics_mode(self.client_config.get("graphics_mode", "quality"), persist=False)

        self._overlay_mode = "select"
        self._overlay_pulse_on = False
        self._indicator_pulse_strength = 0.0
        self._production_timer_label_px: Optional[int] = None
        self._production_timer_value_px: Optional[int] = None
        self._pulse_phase = 0.0
        self._machine_idle_flash_phase = 0.0
        self._overlay_shadow = QGraphicsDropShadowEffect(self)
        self._overlay_shadow.setBlurRadius(18)
        self._overlay_shadow.setOffset(0, 0)
        self._overlay_shadow.setColor(Qt.GlobalColor.transparent)
        self.productionOverlay.setGraphicsEffect(self._overlay_shadow)
        self._apply_downtime_active_widget_styles()
        self._blur_left = None
        self._blur_right = None
        self.leftWrap.setGraphicsEffect(None)
        self.rightPanel.setGraphicsEffect(None)
        self._set_production_overlay_mode("select")
        self.productionOverlay.hide()
        self.productionOverlay.raise_()

        self.scan_received.connect(self.on_scanned)
        self.scanner_status.connect(self._set_status_text)
        self.average_weight_received.connect(self._apply_external_average_weight)
        self._setup_scanner_input()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._save_active_session_snapshot)
            app.aboutToQuit.connect(self._shutdown_average_weight_server)

        # heartbeat timer
        self.hb = QTimer(self)
        self.hb.timeout.connect(self.send_heartbeat)
        self.hb.start(1500)

        self.activeSessionSqlSyncTimer = QTimer(self)
        self.activeSessionSqlSyncTimer.timeout.connect(self._sync_active_session_snapshots_to_sql)
        self.activeSessionSqlSyncTimer.start(180000)
        QTimer.singleShot(2000, self._sync_active_session_snapshots_to_sql)

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
        self._start_average_weight_server()

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

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._background_pixmap.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        scaled = self._background_pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        offset_x = (self.width() - scaled.width()) // 2
        offset_y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(offset_x, offset_y, scaled)

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
        self._apply_production_timer_fonts()
        self._refresh_linkage_panel()

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
            # Lock the Linkage Mirror top to the scan banner top and its bottom
            # to the production strip bottom so the right panel mirrors the left.
            target_top = self.banner.mapTo(self, self.banner.rect().topLeft()).y()
            target_bottom = self.cardProductionOuter.mapTo(
                self, self.cardProductionOuter.rect().bottomLeft()
            ).y()
            right_top = self.rightPanel.mapTo(self, self.rightPanel.rect().topLeft()).y()
            desired_outer_height = max(150, int(target_bottom - target_top + 1))

            offset = max(0, int(target_top - right_top))
            self.rightTopSpacer.setFixedHeight(offset)

            if hasattr(self, "linkageMirrorOuter") and self.linkageMirrorOuter is not None:
                self.linkageMirrorOuter.setMinimumHeight(desired_outer_height)
                self.linkageMirrorOuter.setMaximumHeight(desired_outer_height)

            if hasattr(self, "linkageMirrorFrame") and self.linkageMirrorFrame is not None:
                linkage_margins = self.linkageMirrorOuter.layout().contentsMargins() if hasattr(self, "linkageMirrorOuter") and self.linkageMirrorOuter.layout() is not None else None
                outer_vertical_margins = (
                    int(linkage_margins.top() + linkage_margins.bottom()) if linkage_margins is not None else 0
                )
                linkage_height = max(150, desired_outer_height - outer_vertical_margins)
                self.linkageMirrorFrame.setMinimumHeight(linkage_height)
                self.linkageMirrorFrame.setMaximumHeight(linkage_height)

                if hasattr(self, "jobQtyRequestOuter") and self.jobQtyRequestOuter is not None:
                    self.jobQtyRequestOuter.setMinimumHeight(desired_outer_height)
                    self.jobQtyRequestOuter.setMaximumHeight(desired_outer_height)
                if hasattr(self, "jobQtyRequestFrame") and self.jobQtyRequestFrame is not None:
                    qty_margins = self.jobQtyRequestOuter.layout().contentsMargins() if self.jobQtyRequestOuter.layout() is not None else None
                    qty_outer_vertical_margins = (
                        int(qty_margins.top() + qty_margins.bottom()) if qty_margins is not None else 0
                    )
                    qty_height = max(150, desired_outer_height - qty_outer_vertical_margins)
                    self.jobQtyRequestFrame.setMinimumHeight(qty_height)
                    self.jobQtyRequestFrame.setMaximumHeight(qty_height)
        except Exception:
            self.rightTopSpacer.setFixedHeight(0)

    def _setup_invalid_overlay_media(self):
        if not getattr(self, "enable_gif_animations", True):
            self.invalidGifLabel.clear()
            self.invalidGifLabel.hide()
            self._invalid_movie = None
            return
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
        if self.enable_gif_animations and self._invalid_movie is not None:
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
        if getattr(self, "_overlay_mode", "select") == "select":
            w = min(1140, max(820, int(self.width() * 0.8)))
            h = min(610, max(380, int(self.height() * 0.5)))
        else:
            w = min(620, max(620, int(self.width() * 0.50)))
            h = min(640, max(640, int(self.height() * 0.80)))
        x = max(0, (self.width() - w) // 2)
        if getattr(self, "_overlay_mode", "select") == "select":
            y = max(0, (self.height() - h) // 2)
        else:
            y = max(12, (self.height() - h) // 2 - 8)
        self.productionOverlay.setGeometry(x, y, w, h)
        self._sync_production_reason_card_sizes()
        self._position_marquee()

    def _sync_production_reason_card_sizes(self):
        if not hasattr(self, "productionReasonCards") or not self.productionReasonCards:
            return
        grid = self.productionReasonList.layout()
        if grid is None:
            return
        available_w = max(0, int(self.productionReasonList.width()))
        if available_w <= 0:
            return
        columns = 5
        spacing = max(0, int(grid.spacing()))
        margins = grid.contentsMargins()
        inner_w = max(1, available_w - margins.left() - margins.right())
        cell_w = max(96, int((inner_w - ((columns - 1) * spacing)) / columns))
        reference_height = 0
        for code, card, codeLabel, iconLabel, textLabel in zip(
            self.productionReasonCodes,
            self.productionReasonCards,
            self.productionReasonCodeLabels,
            self.productionReasonIconLabels,
            self.productionReasonTextLabels,
        ):
            layout = card.layout()
            if layout is None:
                continue
            card_margins = layout.contentsMargins()
            text_w = max(72, cell_w - card_margins.left() - card_margins.right() - 4)
            text_rect = textLabel.fontMetrics().boundingRect(
                0,
                0,
                text_w,
                200,
                int(Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextExpandTabs),
                str(textLabel.text() or ""),
            )
            icon_h = max(0, int(iconLabel.maximumHeight() if iconLabel.maximumHeight() < 16777215 else iconLabel.height()))
            card_h = (
                card_margins.top()
                + card_margins.bottom()
                + icon_h
                + int(layout.spacing())
                + max(24, int(text_rect.height()))
            )
            reference_height = max(reference_height, card_h, 64)
        if reference_height <= 0:
            reference_height = 64
        for card, codeLabel in zip(self.productionReasonCards, self.productionReasonCodeLabels):
            target_h = reference_height
            card.setMinimumHeight(target_h)
            card.setMaximumHeight(target_h)
            codeLabel.adjustSize()
            codeLabel.move(12, 6)
            codeLabel.raise_()

    def _position_resolve_overlay(self):
        self.resolveOverlay.adjustSize()
        hint_h = self.resolveOverlay.sizeHint().height()
        hint_w = self.resolveOverlay.sizeHint().width()
        w = min(max(420, int(self.width() * 0.40)), max(400, hint_w + 20))
        h = min(max(250, int(self.height() * 0.34)), max(238, hint_h + 18))
        x = max(0, (self.width() - w) // 2)
        y = max(0, (self.height() - h) // 2)
        if hasattr(self, "productionMaintenanceLine") and self.productionMaintenanceLine is not None and self.productionMaintenanceLine.isVisible():
            maintenance_top_left = self.productionMaintenanceLine.mapTo(self, self.productionMaintenanceLine.rect().topLeft())
            maintenance_bottom = maintenance_top_left.y() + self.productionMaintenanceLine.height()
            x = max(0, int((self.width() - w) / 2))
            y = max(12, int(maintenance_bottom + 10))
        self.resolveOverlay.setGeometry(x, y, w, h)

    def _position_raw_mats_overlay(self):
        w = min(1100, max(700, int(self.width() * 0.82)))
        h = min(640, max(360, int(self.height() * 0.65)))
        x = max(0, (self.width() - w) // 2)
        y = max(0, (self.height() - h) // 2)
        self.rawMatsOverlay.setGeometry(x, y, w, h)

    def _position_reject_summary_overlay(self):
        w = min(980, max(720, int(self.width() * 0.72)))
        h = min(720, max(420, int(self.height() * 0.62)))
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
        w = min(1360, max(1040, int(self.width() * 0.88)))
        h = min(940, max(700, int(self.height() * 0.88)))
        x = max(0, (self.width() - w) // 2)
        y = max(0, (self.height() - h) // 2)
        self.finishOverlay.setGeometry(x, y, w, h)

    def _scroll_finish_shift_review(self, direction: int):
        if not self.finishOverlay.isVisible() or not self.finishSummaryScroll.isVisible():
            return
        bar = self.finishSummaryScroll.verticalScrollBar()
        if bar is None:
            return
        step = max(180, self.finishSummaryScroll.viewport().height() - 70)
        target = bar.value() + (step * (1 if direction > 0 else -1))
        target = max(bar.minimum(), min(bar.maximum(), target))
        if target == bar.value():
            edge = "last" if direction > 0 else "first"
            self.status.setText(f"Finish review: already on {edge} page.")
            return
        bar.setValue(target)
        page_size = max(1, step)
        page_num = max(1, (bar.value() // page_size) + 1)
        total_pages = max(1, (bar.maximum() // page_size) + 1)
        self.status.setText(f"Finish review page {page_num} of {total_pages}.")

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
        logs = []
        for row in (s.reject_review_logs or []):
            if not isinstance(row, dict):
                continue
            entry_type = str(row.get("entry_type") or "").strip().upper()
            if entry_type not in ("REJECT_SCAN", "STARTUP_REJECT_SCAN"):
                continue
            logs.append(row)
        self.rejectSummaryDetails.setRowCount(0)
        for row_idx, row in enumerate(logs):
            self.rejectSummaryDetails.insertRow(row_idx)
            reason_code = str(row.get("reason_code") or row.get("reason") or "").strip() or "-"
            operator_name = str(row.get("operator_name") or row.get("operator") or "-").strip() or "-"
            ts_raw = str(row.get("scanned_at") or row.get("timestamp") or "").strip()
            ts_text = ts_raw or "-"
            if ts_raw:
                try:
                    ts_dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                    ts_text = ts_dt.astimezone().strftime("%Y-%m-%d %I:%M:%S %p")
                except Exception:
                    pass
            values = [reason_code, operator_name, ts_text]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter if col in (0, 1) else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                self.rejectSummaryDetails.setItem(row_idx, col, item)
        if self.rejectSummaryDetails.rowCount() == 0:
            self.rejectSummaryDetails.insertRow(0)
            for col, value in enumerate(("-", "-", "No reject scans yet")):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if col in (0, 1) else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
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
        if isinstance(self._product_catalog_name_by_id, dict) and isinstance(self._product_catalog_sku_by_id, dict):
            return
        self._product_catalog_name_by_id = {}
        self._product_catalog_sku_by_id = {}
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
            self._product_catalog_sku_by_id[key] = str(row.get("sku") or "").strip()

    def _lookup_product_name(self, product_id: str) -> str:
        pid = str(product_id or "").strip()
        if not pid:
            return ""
        self._ensure_product_catalog_index()
        key = pid.lstrip("0") if pid.isdigit() else pid
        key = key or "0"
        return str((self._product_catalog_name_by_id or {}).get(key) or "")

    def _lookup_product_sku(self, product_id: str) -> str:
        pid = str(product_id or "").strip()
        if not pid:
            return ""
        self._ensure_product_catalog_index()
        key = pid.lstrip("0") if pid.isdigit() else pid
        key = key or "0"
        return str((self._product_catalog_sku_by_id or {}).get(key) or "")

    def _refresh_product_catalog_cache_from_api(self) -> bool:
        now_ts = time.time()
        if (now_ts - float(getattr(self, "_product_catalog_last_refresh_attempt", 0.0) or 0.0)) < 30.0:
            return False
        self._product_catalog_last_refresh_attempt = now_ts
        try:
            jcfg = getattr(self, "job_api_config", {}) or _load_job_api_config()
            self.job_api_config = jcfg
            bms = jcfg.get("bms") if isinstance(jcfg.get("bms"), dict) else {}
            base = str(jcfg.get("base_url") or bms.get("base_url") or "").strip().rstrip("/")
            token = str(jcfg.get("bearer_token", "") or "").strip()
            user = str(jcfg.get("user") or bms.get("username") or bms.get("user") or "").strip()
            password = str(jcfg.get("password") or bms.get("password") or "").strip()
            if not base:
                return False
            if not token and user and password:
                token = self._get_job_api_bearer_token(base=base, user=user, password=password) or ""
            if not token:
                return False
            url = self._job_api_url(base, "/products")
            resp = requests.get(
                url,
                headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
                timeout=5,
            )
            if resp.status_code != 200:
                return False
            payload = resp.json()
            items = []
            if isinstance(payload, dict):
                data = payload.get("data")
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    if isinstance(data.get("items"), list):
                        items = data.get("items") or []
                    elif isinstance(data.get("products"), list):
                        items = data.get("products") or []
            if not isinstance(items, list) or not items:
                return False
            out = []
            idx: Dict[str, str] = {}
            sku_idx: Dict[str, str] = {}
            for row in items:
                if not isinstance(row, dict):
                    continue
                pid = str(row.get("id") or row.get("product_id") or "").strip()
                name = str(row.get("name") or row.get("product_name") or "").strip()
                sku = str(row.get("sku") or "").strip()
                category_id = str(
                    row.get("categoryId")
                    or row.get("category_id")
                    or row.get("category")
                    or ""
                ).strip()
                category_name = str(
                    row.get("categoryName")
                    or row.get("category_name")
                    or row.get("category_text")
                    or ""
                ).strip()
                if not pid or not name:
                    continue
                out.append(
                    {
                        "id": pid,
                        "name": name,
                        "sku": sku,
                        "categoryId": category_id,
                        "categoryName": category_name,
                    }
                )
                key = pid.lstrip("0") if pid.isdigit() else pid
                idx[key or "0"] = name
                sku_idx[key or "0"] = sku
            if not out:
                return False
            self._save_json_file(PRODUCT_CATALOG_CACHE_FILE, {"items": out})
            self._product_catalog_name_by_id = idx
            self._product_catalog_sku_by_id = sku_idx
            return True
        except Exception:
            return False

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
        self.finishCheck.show()
        self.finishCross.hide()
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

    def _scroll_finish_summary_page(self, direction: int):
        if not getattr(self, "finishSummaryScroll", None) or not self.finishSummaryScroll.isVisible():
            return False
        bar = self.finishSummaryScroll.verticalScrollBar()
        if bar is None:
            return False
        page_step = max(1, int(bar.pageStep() or self.finishSummaryScroll.viewport().height() or 1))
        current = int(bar.value() or 0)
        maximum = int(bar.maximum() or 0)
        if direction > 0:
            if current >= maximum:
                self.status.setText("Finish review: already on last page.")
                return True
            bar.setValue(min(maximum, current + page_step))
        else:
            if current <= 0:
                self.status.setText("Finish review: already on first page.")
                return True
            bar.setValue(max(0, current - page_step))
        current_after = int(bar.value() or 0)
        total_pages = max(1, int(math.ceil((maximum + page_step) / max(1, page_step))))
        current_page = min(total_pages, max(1, int(current_after // max(1, page_step)) + 1))
        self.status.setText(f"Finish review page {current_page} of {total_pages}.")
        return True

    def _tick_finish_anim(self):
        if not getattr(self, "enable_heavy_animations", True):
            self._finish_anim_value = 100
            self.finishProgressBar.setValue(100)
        else:
            self._finish_anim_value = min(100, self._finish_anim_value + 7)
            self.finishProgressBar.setValue(self._finish_anim_value)
        if self._finish_anim_value < 100:
            return
        self._finish_anim_timer.stop()
        if self._finish_post_action and self._finish_post_action != "downtime_supervisor_saved":
            self.finishOverlay.setStyleSheet(
                "QFrame#ProductionOverlay {"
                "background: qradialgradient(cx:0.5, cy:0.12, radius:1.2, fx:0.5, fy:0.02,"
                "stop:0 rgba(102,45,45,242), stop:0.38 rgba(73,31,31,244), stop:1 rgba(28,10,10,248));"
                "border: 1px solid rgba(248,113,113,220); border-radius: 28px; }"
                "QWidget#FinishSuccessRow { background: transparent; border: none; }"
                "QLabel#FinishDoneText { background: transparent; border: none; }"
                "QProgressBar {"
                "border: 1px solid rgba(248,113,113,0.90); border-radius: 10px; background: rgba(15,23,42,0.65); min-height: 16px; }"
                "QProgressBar::chunk {"
                "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ef4444, stop:1 #dc2626);"
                "border-radius: 8px; }"
            )
            self.finishStatus.setText(self._finish_post_action)
        else:
            self.finishStatus.setText("Completed")
        self.finishSuccessRow.show()
        if self._finish_post_action and self._finish_post_action != "downtime_supervisor_saved":
            self.finishCheck.hide()
            self.finishCross.show()
            self.finishCross.start()
            QTimer.singleShot(2000, self._complete_finish_sequence)
        elif self.enable_check_animation:
            self.finishCross.hide()
            self.finishCheck.start()
            QTimer.singleShot(900, self._complete_finish_sequence)
        else:
            self.finishCross.hide()
            self.finishCheck.setProgress(1.0)
            QTimer.singleShot(280, self._complete_finish_sequence)

    def _complete_finish_sequence(self):
        self._hide_finish_overlay()
        if self._finish_pending_clear:
            self._finish_pending_clear = False
            self._clear_shift_session_keep_machine()
            return
        if self._finish_post_action == "downtime_supervisor_saved":
            self._finish_post_action = ""
            self._supervisor_validation_pending = False
            self._hide_resolve_overlay()
            self._refresh_ui()
            return
        if self._finish_post_action and self._finish_post_action != "downtime_supervisor_saved":
            self._finish_post_action = ""
            self._supervisor_validation_pending = False
            self.resolveNewCycle.setText("Confirmed by: ")
            self.resolveHint.setText("SCAN SUPERVISOR QR")
            self._refresh_ui()
            self._show_resolve_overlay()

    def _show_downtime_supervisor_saved_overlay(self, supervisor_name: str):
        self.finishOverlay.setStyleSheet(
            "QFrame#ProductionOverlay {"
            "background: qradialgradient(cx:0.5, cy:0.12, radius:1.2, fx:0.5, fy:0.02,"
            "stop:0 rgba(63,94,71,242), stop:0.38 rgba(38,61,44,244), stop:1 rgba(13,24,16,248));"
            "border: 1px solid rgba(74,222,128,220); border-radius: 28px; }"
            "QWidget#FinishSuccessRow { background: transparent; border: none; }"
            "QLabel#FinishDoneText { background: transparent; border: none; }"
            "QProgressBar {"
            "border: 1px solid rgba(74,222,128,0.90); border-radius: 10px; background: rgba(15,23,42,0.65); min-height: 16px; }"
            "QProgressBar::chunk {"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #16a34a, stop:1 #22c55e);"
            "border-radius: 8px; }"
        )
        self._position_finish_overlay()
        self._set_background_blur(True)
        self.finishTitle.setText("SUPERVISOR CONFIRMED")
        self.finishStatus.setText(str(supervisor_name or "Saving..."))
        self.finishDoneText.setText("Success")
        self.finishDoneText.setStyleSheet("background: transparent; color: #166534; font-size: 20px; font-weight: 900;")
        self.finishCheck.show()
        self.finishCross.hide()
        self.finishProgressBar.show()
        self.finishProgressBar.setValue(0)
        self.finishSuccessRow.hide()
        self.finishCheck.setProgress(0.0)
        self._finish_anim_value = 0
        self._finish_anim_running = True
        self._finish_pending_clear = False
        self._finish_post_action = "downtime_supervisor_saved"
        self.finishOverlay.show()
        self.finishOverlay.raise_()
        self._finish_anim_timer.start()

    def _show_downtime_supervisor_failed_overlay(self, message: str):
        self.finishOverlay.setStyleSheet(
            "QFrame#ProductionOverlay {"
            "background: qradialgradient(cx:0.5, cy:0.12, radius:1.2, fx:0.5, fy:0.02,"
            "stop:0 rgba(102,45,45,242), stop:0.38 rgba(73,31,31,244), stop:1 rgba(28,10,10,248));"
            "border: 1px solid rgba(248,113,113,220); border-radius: 28px; }"
            "QWidget#FinishSuccessRow { background: transparent; border: none; }"
            "QLabel#FinishDoneText { background: transparent; border: none; }"
            "QProgressBar {"
            "border: 1px solid rgba(248,113,113,0.90); border-radius: 10px; background: rgba(15,23,42,0.65); min-height: 16px; }"
            "QProgressBar::chunk {"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ef4444, stop:1 #dc2626);"
            "border-radius: 8px; }"
        )
        self._position_finish_overlay()
        self._set_background_blur(True)
        self.finishTitle.setText("SUPERVISOR VALIDATION")
        self.finishStatus.setText("Validating...")
        self.finishDoneText.setText("Failed")
        self.finishDoneText.setStyleSheet("background: transparent; color: #b91c1c; font-size: 20px; font-weight: 900;")
        self.finishCheck.hide()
        self.finishCross.show()
        self.finishCross.setProgress(0.0)
        self.finishProgressBar.show()
        self.finishProgressBar.setValue(0)
        self.finishSuccessRow.hide()
        self._finish_anim_value = 0
        self._finish_anim_running = True
        self._finish_pending_clear = False
        self._finish_post_action = str(message or "This is not supervisor QR")
        self.finishOverlay.show()
        self.finishOverlay.raise_()
        self._finish_anim_timer.start()

    def _show_operator_shift_overlay(self, shift_payload: Dict[str, Any]):
        self._pending_shift_review_payload = dict(shift_payload or {})
        self._operator_shift_flash_active = True
        self._position_finish_overlay()
        self._set_background_blur(True)
        self.finishTitle.setText("FINISH SHIFT REVIEW")
        self.finishStatus.setText("Supervisor review required before the next operator starts.")
        self.finishReviewHint.show()
        self.finishProgressBar.hide()
        self.finishSummaryScroll.show()
        self._populate_finish_shift_summary(self._pending_shift_review_payload)
        finish_bar = self.finishSummaryScroll.verticalScrollBar()
        if finish_bar is not None:
            finish_bar.setValue(finish_bar.minimum())
        self.finishSuccessRow.hide()
        self.finishOverlay.show()
        self.finishOverlay.raise_()

    def _hide_operator_shift_overlay(self):
        if not self._operator_shift_flash_active:
            return
        self._operator_shift_flash_active = False
        self._pending_shift_review_payload = None
        self.finishTitle.setText("FINISHING JOB")
        self.finishStatus.setText("Processing...")
        self.finishReviewHint.hide()
        self.finishProgressBar.show()
        self.finishSummaryScroll.hide()
        self.finishOverlay.hide()
        if not self._should_keep_background_blur():
            self._set_background_blur(False)

    def _approve_pending_shift_review(self, reviewer: Dict[str, Any], reviewer_badge: str):
        shift_payload = dict(self._pending_shift_review_payload or {})
        if not shift_payload:
            return
        remarks = f"Approved on client finish-shift review by {self._safe_text(reviewer.get('name'))}"
        local_ok = self._approve_local_finished_shift(shift_payload, reviewer, remarks)
        server_ok = self._approve_server_finished_shift(shift_payload, reviewer_badge, remarks)
        self._pending_shift_review_payload = shift_payload
        self._populate_finish_shift_summary(shift_payload)
        self.finishTitle.setText("FINISH SHIFT APPROVED")
        self.finishReviewHint.setText(
            "Approved. Shift saved in Finished Shifts."
            if server_ok else
            "Approved locally. Server sync will refresh on next connection."
        )
        self.finishStatus.setText(
            f"{self._safe_text(reviewer.get('name'))} approved this shift."
            if local_ok else
            "Approval could not be written locally."
        )
        if not local_ok:
            self._show_invalid_overlay("Unable to update local finished shift approval.")
            return
        self.status.setText(f"Shift approved by {self._safe_text(reviewer.get('name'))}. Scan JOB QR.")
        self._clear_shift_session_keep_machine()
        QTimer.singleShot(2200, self._hide_operator_shift_overlay)

    def _set_reject_review_blur(self, enabled: bool):
        if not getattr(self, "enable_background_blur", True):
            enabled = False
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
        if not getattr(self, "enable_heavy_animations", True):
            self._reject_review_anim_value = 100
            self.rejectReviewLoadingBar.setValue(100)
            self._reject_review_anim_timer.stop()
            self._set_reject_review_blur(False)
            return
        self._reject_review_anim_value = min(100, self._reject_review_anim_value + 8)
        self.rejectReviewLoadingBar.setValue(self._reject_review_anim_value)
        if self._reject_review_anim_value >= 100:
            self._reject_review_anim_timer.stop()
            self._set_reject_review_blur(False)

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
        if hasattr(self, "productionFixAnim") and self.productionFixAnim is not None:
            if self.enable_heavy_animations:
                self.productionFixAnim.show()
                self.productionFixAnim.ensure_running()
            else:
                self.productionFixAnim.timer.stop()
                self.productionFixAnim.hide()
        self.productionOverlay.show()
        self.productionOverlay.raise_()
        self._position_marquee()

    def _hide_production_overlay(self):
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
        if not getattr(self, "enable_background_blur", True):
            enabled = False
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
            self.productionTitle.setStyleSheet("color: #f8fafc; font-size: 24px; font-weight: 900;")
            self.productionHint.setStyleSheet("color: #cbd5e1; font-size: 14px; font-weight: 700;")
            self.productionHint.show()
            self.productionReasonList.show()
            self.productionLiveReason.hide()
            self.productionMaintenanceLine.hide()
            self.productionActionBanner.hide()
            self.productionTimerPanelWrap.hide()
            self.productionRepairZone.hide()
            self.productionMarqueeWrap.hide()
            self._apply_timer_indicator_state(False, False)
            return
        self.productionTitle.setText("DOWNTIME ACTIVE")
        self.productionHint.hide()
        self.productionReasonList.hide()
        self.productionLiveReason.show()
        self.productionMaintenanceLine.show()
        self.productionActionBanner.show()
        self.productionTimerPanelWrap.show()
        self.productionRepairZone.show()
        if self.enable_heavy_animations:
            self.productionFixAnim.show()
            self.productionFixAnim.ensure_running()
        else:
            self.productionFixAnim.timer.stop()
            self.productionFixAnim.hide()
        self.productionMarqueeWrap.hide()
        self._marquee_x = self.productionMarqueeWrap.width()
        self._position_marquee()
        self._apply_production_timer_fonts()

    def _apply_overlay_base_style(self):
        self.productionOverlay.setStyleSheet(
            "QFrame#ProductionOverlay {"
            "background: qradialgradient(cx:0.5, cy:0.12, radius:1.2, fx:0.5, fy:0.02,"
            "stop:0 rgba(112,116,124,242), stop:0.38 rgba(70,74,82,244), stop:1 rgba(24,26,31,248));"
            "border: 1px solid rgba(124,130,140,235); border-radius: 20px; }"
        )

    def _apply_downtime_active_widget_styles(self):
        self.productionTitle.setStyleSheet(
            "color: #f8fafc; font-size: 26px; font-weight: 900; letter-spacing: 0.2px; background: transparent; border: none;"
        )
        self.productionLiveReason.setStyleSheet(
            "color: #f8fafc; font-size: 15px; font-weight: 900;"
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(103,107,115,220), stop:1 rgba(56,59,66,230));"
            "border: 1px solid rgba(96,165,250,0.7); border-radius: 11px;"
            "padding: 8px 12px;"
        )
        self.productionMaintenanceLine.setStyleSheet(
            "color: #f8fafc; font-size: 15px; font-weight: 900;"
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(103,107,115,220), stop:1 rgba(56,59,66,230));"
            "border: 1px solid rgba(148,163,184,0.45); border-radius: 11px;"
            "padding: 8px 12px;"
        )
        self.productionActionBanner.setStyleSheet(
            "color: #ffffff; font-size: 17px; font-weight: 900;"
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5aa4ee, stop:0.52 #4795e3, stop:1 #3b84d2);"
            "border-top: 1px solid rgba(255,255,255,0.20);"
            "border-left: 1px solid rgba(255,255,255,0.12);"
            "border-right: 1px solid rgba(31,88,156,0.55);"
            "border-bottom: 1px solid rgba(22,67,122,0.72);"
            "border-radius: 12px; padding: 8px 18px;"
        )
        self.productionRepairZone.setStyleSheet("background: transparent; border: none;")
        self.productionRepairZoneBody.setStyleSheet(
            "QFrame#ProductionRepairZoneBody {"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            "stop:0 #9b9b9b, stop:0.22 #c9c9c9, stop:0.50 #808080, stop:0.80 #565656, stop:1 #383838);"
            "border: none; }"
        )
        timer_css = (
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "stop:0 #39404c, stop:0.55 #343b46, stop:1 #303742);"
            "border: 6px solid #b1b1b1; border-radius: 16px; padding: 6px 10px;"
        )
        self.productionWaitingPanel.setStyleSheet(timer_css)
        self.productionDowntimePanel.setStyleSheet(timer_css)
        self._apply_widget_shadow(self.productionWaitingPanel, 12, 2, QColor(0, 0, 0, 62))
        self._apply_widget_shadow(self.productionDowntimePanel, 12, 2, QColor(0, 0, 0, 62))
        self._apply_widget_shadow(self.productionLiveReason, 16, 2, QColor(0, 0, 0, 45))
        self._apply_widget_shadow(self.productionMaintenanceLine, 16, 2, QColor(0, 0, 0, 42))
        self.productionActionBanner.setGraphicsEffect(None)

    @staticmethod
    def _apply_widget_shadow(widget: Optional[QWidget], blur: int, offset_y: int, color: QColor):
        if widget is None:
            return
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(float(blur))
        shadow.setOffset(0, float(offset_y))
        shadow.setColor(color)
        widget.setGraphicsEffect(shadow)

    def _tick_overlay_pulse(self):
        if self.productionOverlay.isVisible():
            self._overlay_shadow.setColor(Qt.GlobalColor.transparent)
            self._apply_overlay_base_style()
            phase = time.time() % 1.0
            if phase < 0.18:
                strength = 1.0
            elif phase < 0.48:
                strength = max(0.30, 1.0 - ((phase - 0.18) / 0.30) * 0.70)
            else:
                strength = 0.30
            self._indicator_pulse_strength = strength
            self._overlay_pulse_on = strength >= 0.75
            self._apply_timer_indicator_state(
                getattr(self, "_waiting_indicator_active", False),
                getattr(self, "_downtime_indicator_active", False),
            )
        if not self.productionOverlay.isVisible() or self._overlay_mode != "active":
            return
        if self.enable_heavy_animations:
            self._tick_marquee()

    def _tick_marquee(self):
        if not getattr(self, "enable_heavy_animations", True):
            return
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

    def _make_timer_status_indicator(self, role: str = "red") -> QLabel:
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot._indicator_role = str(role or "red").strip().lower()  # type: ignore[attr-defined]
        glow = QGraphicsDropShadowEffect(dot)
        glow.setBlurRadius(34)
        glow.setOffset(0, 0)
        if getattr(dot, "_indicator_role", "red") == "green":
            glow.setColor(QColor(34, 255, 102, 170))
        else:
            glow.setColor(QColor(239, 68, 68, 220))
        dot.setGraphicsEffect(glow)
        dot._glow_effect = glow  # type: ignore[attr-defined]
        self._set_timer_indicator_style(dot)
        return dot

    def _apply_timer_indicator_state(self, waiting_active: bool, downtime_active: bool):
        self._waiting_indicator_active = bool(waiting_active)
        self._downtime_indicator_active = bool(downtime_active)
        self._set_timer_indicator_style(getattr(self, "productionWaitingIndicator", None))
        self._set_timer_indicator_style(getattr(self, "productionDowntimeIndicator", None))

    def _set_timer_indicator_style(self, dot: Optional[QLabel]):
        if dot is None:
            return
        role = str(getattr(dot, "_indicator_role", "red") or "red").strip().lower()
        glow = getattr(dot, "_glow_effect", None)
        is_active = bool(
            getattr(self, "_waiting_indicator_active", False)
            if role == "green"
            else getattr(self, "_downtime_indicator_active", False)
        )
        if role == "green":
            strength = float(self._indicator_pulse_strength) if is_active else 0.35
            fill_alpha = max(70, min(255, int(120 + (135 * strength))))
            glow_alpha = max(40, min(220, int(80 + (140 * strength))))
            glow_blur = 12 + (12 * strength)
            style = (
                "background: qradialgradient(cx:0.34, cy:0.32, radius:1.0,"
                f"stop:0 rgba(255,255,255,{min(255, fill_alpha + 35)}),"
                f"stop:0.22 rgba(187,247,208,{min(255, fill_alpha + 18)}),"
                f"stop:0.62 rgba(34,197,94,{fill_alpha}),"
                f"stop:1 rgba(22,101,52,{max(110, fill_alpha - 42)}));"
                "border: none; border-radius: 5px;"
            )
            if glow is not None:
                glow.setBlurRadius(glow_blur)
                glow.setColor(QColor(34, 255, 102, glow_alpha))
        else:
            fill_alpha = 255 if is_active else 150
            glow_alpha = 165 if is_active else 70
            style = (
                "background: qradialgradient(cx:0.34, cy:0.32, radius:1.0,"
                f"stop:0 rgba(255,255,255,{min(255, fill_alpha)}),"
                f"stop:0.18 rgba(254,202,202,{min(255, fill_alpha)}),"
                f"stop:0.62 rgba(239,68,68,{fill_alpha}),"
                f"stop:1 rgba(127,29,29,{max(90, fill_alpha - 30)}));"
                "border: none; border-radius: 5px;"
            )
            if glow is not None:
                glow.setBlurRadius(14 if is_active else 8)
                glow.setColor(QColor(239, 68, 68, glow_alpha))
        dot.setStyleSheet(style)

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

    def _find_pdr_reason_icon_path(self, code: str) -> Optional[str]:
        filename = PDR_REASON_ICON_FILES.get(str(code or "").strip())
        if not filename:
            return None
        path = os.path.join(PDR_ICON_DIR, filename)
        if os.path.exists(path):
            return path
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
        glow_map = {
            "StatPack": QColor(34, 197, 94),
            "StatGood": QColor(34, 197, 94),
            "StatButal": QColor(14, 165, 233),
            "StatReject": QColor(239, 68, 68),
            "StatTotalGood": QColor(34, 211, 238),
        }
        base = glow_map.get(str(card.objectName() or ""), QColor(59, 130, 246))
        fx = getattr(card, "_pulse_glow_fx", None)
        if fx is None:
            fx = QGraphicsDropShadowEffect(card)
            fx.setOffset(0, 0)
            fx.setBlurRadius(0)
            fx.setColor(QColor(base.red(), base.green(), base.blue(), 0))
            card.setGraphicsEffect(fx)
            card._pulse_glow_fx = fx

        blur_anim = getattr(card, "_pulse_blur_anim", None)
        if blur_anim is not None:
            blur_anim.stop()
        blur_anim = QPropertyAnimation(fx, b"blurRadius", card)
        blur_anim.setDuration(420)
        blur_anim.setStartValue(28.0)
        blur_anim.setEndValue(2.0)
        blur_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        card._pulse_blur_anim = blur_anim

        alpha_anim = getattr(card, "_pulse_alpha_anim", None)
        if alpha_anim is not None:
            alpha_anim.stop()
        alpha_anim = QVariantAnimation(card)
        alpha_anim.setDuration(420)
        alpha_anim.setStartValue(190)
        alpha_anim.setEndValue(0)
        alpha_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        alpha_anim.valueChanged.connect(
            lambda v, e=fx, c=base: e.setColor(QColor(c.red(), c.green(), c.blue(), int(v)))
        )
        card._pulse_alpha_anim = alpha_anim

        card.setProperty("flash", "1")
        card.style().unpolish(card)
        card.style().polish(card)
        blur_anim.start()
        alpha_anim.start()
        QTimer.singleShot(220, lambda c=card: self._clear_pulse(c))

    def _clear_pulse(self, card: QFrame):
        if card is None:
            return
        card.setProperty("flash", "0")
        card.style().unpolish(card)
        card.style().polish(card)

    def _refresh_ui(self):
        s = self.state
        self._restore_job_payload_from_active_snapshot()
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
        cavity_count = job_details.get("no_of_cavity") or job.get("custom_11") or 1
        self.lblActivityCavities.setText(f"Cavities: {self._safe_text(cavity_count, '-')}")
        self.lblActivitySticker.setText(f"Sticker Label: {self._safe_text(job_details.get('sticker_label'), '-')}")

        self.lblPack.set_value(s.pack_count)
        self.lblGood.set_value(s.good_total)
        self.lblButal.set_value(s.butal_total)
        self.lblReject.set_value(s.reject_total)
        self.lblTotalGood.set_value(s.good_total + s.butal_total)
        self.rightCycleCount.setText(f"Confirmed by: {s.cycle_time_confirmed_by or '-'}")
        act_cycle_current = self._parse_cycle_seconds(s.cycle_time_current)
        act_cycle_shift_avg = self._compute_current_shift_avg_cycle_seconds()
        act_cycle_for_qty = act_cycle_shift_avg if act_cycle_shift_avg is not None else act_cycle_current
        if act_cycle_shift_avg is not None and act_cycle_current is not None and abs(act_cycle_shift_avg - act_cycle_current) > 0.01:
            act_cycle_text = f"{act_cycle_shift_avg:.2f} sec avg"
        elif act_cycle_for_qty is not None:
            act_cycle_text = f"{act_cycle_for_qty:g} sec"
        else:
            act_cycle_text = "-"
        act_qty_shift = self._qty_per_shift_from_cycle(act_cycle_for_qty, cavity_count)
        act_qty_shift_text = str(act_qty_shift) if act_qty_shift is not None else "-"
        std_cycle_raw = self._safe_text(job_details.get("std_cycle_time"), "-")
        api_qty_raw = self._safe_text(job_details.get("qty_per_shift"), "")
        api_qty_num = self._parse_cycle_seconds(api_qty_raw)
        qty_shift_std_text = str(int(api_qty_num)) if api_qty_num is not None else act_qty_shift_text
        live_avg = s.live_cycle_avg_seconds if s.live_cycle_avg_seconds and s.live_cycle_avg_seconds > 0 else None
        live_cycle_text = f"{live_avg:.2f} sec" if live_avg is not None else "-"
        live_qty_shift = self._qty_per_shift_from_cycle(live_avg)
        live_qty_shift_text = str(live_qty_shift) if live_qty_shift is not None else "-"
        self.rightCycleCurrent.setText(f"Act Cycle Time: {act_cycle_text}    Qty / Shift: {act_qty_shift_text}")
        self.rightCycleStd.setText(f"Std Cycle Time: {std_cycle_raw}    Qty / Shift: {qty_shift_std_text}")
        self.rightCycleQtyShift.setText(f"Pack Cycle Time: {live_cycle_text}    Qty / Shift: {live_qty_shift_text}")
        if hasattr(self, "topCycleCount") and self.topCycleCount is not None:
            self.topCycleCount.setText(f"Confirmed by: {s.cycle_time_confirmed_by or '-'}")
        if hasattr(self, "topCycleCurrent") and self.topCycleCurrent is not None:
            self.topCycleCurrent.setText(f"Act Cycle Time: {act_cycle_text}    Qty / Shift: {act_qty_shift_text}")
        if hasattr(self, "topCycleStd") and self.topCycleStd is not None:
            self.topCycleStd.setText(f"Std Cycle Time: {std_cycle_raw}    Qty / Shift: {qty_shift_std_text}")
        if hasattr(self, "topCycleQtyShift") and self.topCycleQtyShift is not None:
            self.topCycleQtyShift.setText(f"Pack Cycle Time: {live_cycle_text}    Qty / Shift: {live_qty_shift_text}")

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
            self._set_banner_text("Production Daily Report mode: scan reason QR (01-15)")
        elif s.waiting_initial_cycle_time_input:
            self._set_banner_text("Initial setup: Scan cycle time digits, then confirm")
        elif s.waiting_cycle_time_confirm_popup:
            self._set_banner_text("Cycle time confirmation: Scan same Supervisor badge again")
        elif s.waiting_initial_cycle_qc_confirm:
            self._set_banner_text("Initial setup: Scan QC badge to confirm cycle time")
        elif s.waiting_cycle_time_input:
            if str(s.cycle_time_new_input or "").strip():
                self._set_banner_text("Downtime resolve: Scan QR to confirm")
            else:
                self._set_banner_text("Downtime resolve: Scan numkeys to input new cycle time")
        elif s.waiting_downtime_start_maintenance:
            self._set_banner_text("PDR waiting: scan Maintenance QR to start downtime")
        elif s.waiting_downtime_end_maintenance:
            self._set_banner_text('Downtime active: scan "pdr_done" when repair is done')
        elif s.waiting_maintenance_qr:
            self._set_banner_text("Downtime resolve: Scan Maintenance QR to stop downtime")
        elif s.waiting_supervisor_qr:
            self._set_banner_text("Downtime resolve: Scan Supervisor QR")
        elif s.waiting_operator_downtime_confirm:
            self._set_banner_text("Downtime resolve: Scan Operator QR to proceed")
        elif s.downtime_active:
            self._set_banner_text('Downtime active: scan "productiondailyreport~2" or SUR')
        else:
            self._set_banner_text("Ready: Scan PACK / BUTAL / Reject~1")

        show_pdr_select = bool(s.waiting_production_report_reason)
        show_pdr_active = bool(
            s.waiting_downtime_start_maintenance
            or s.waiting_downtime_end_maintenance
            or s.downtime_active
            or s.downtime_started_at
        )
        if show_pdr_select:
            self._set_production_overlay_mode("select")
            self._show_production_overlay()
        elif show_pdr_active:
            self._set_production_overlay_mode("active")
            self._show_production_overlay()
        else:
            self._hide_production_overlay()

        self._refresh_job_details()
        self._refresh_downtime_panel()
        self._refresh_linkage_panel()
        self._maybe_show_fulfilled_notice()

    def _session_is_running(self) -> bool:
        s = self.state
        return bool(
            s.machine_code
            and s.job_code
            and s.operator_id
            and not s.waiting_reject_reason
            and not s.downtime_active
        )

    def _apply_machine_anim_style(self, mode: str):
        mode = "active" if str(mode or "").strip().lower() == "active" else "idle"
        if mode == "active":
            css = (
                "QLabel#MachineAnim {"
                " color: #14532d;"
                " font-size: 14px;"
                " font-weight: 800;"
                " background: #b9fbcf;"
                " border: 1px solid #4ade80;"
                " border-radius: 12px;"
                " padding: 8px 12px;"
                "}"
            )
        else:
            css = (
                "QLabel#MachineAnim {"
                " color: #fff7ed;"
                " font-size: 14px;"
                " font-weight: 800;"
                " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
                "                             stop:0 rgba(251,146,60,245),"
                "                             stop:1 rgba(234,88,12,248));"
                " border: 1px solid #fb923c;"
                " border-radius: 12px;"
                " padding: 8px 12px;"
                "}"
            )
        self.machineAnim.setStyleSheet(css)

    def _tick_motion(self):
        has_machine = bool(self.state.machine_code)
        is_running = self._session_is_running()
        if is_running:
            status_text = "ACTIVE"
            mode = "active"
        elif has_machine:
            status_text = "NO JOB RUNNING"
            mode = "idle"
        else:
            status_text = "IDLE"
            mode = "idle"
        self.machineAnim.setText(f"Machine Status: {status_text}")
        if self.machineAnim.property("mode") != mode:
            self.machineAnim.setProperty("mode", mode)
            self.machineAnim.setProperty("pulse", "0")
        self._apply_machine_anim_style(mode)
        self._sync_machine_status_pulse_overlay()
        self.machinePulseOverlay.set_mode(is_running)
        self.machinePulseOverlay.advance(self.enable_pulse_effects, dt=0.06)
        self._update_product_parts_weight_indicator()

    def _refresh_downtime_panel(self):
        s = self.state
        raw_logs = [x for x in (s.raw_material_logs or []) if isinstance(x, dict)]
        qty_by_name: Dict[str, float] = {}
        scans_by_name: Dict[str, int] = {}
        recent_unique: List[str] = []
        seen_names: Set[str] = set()
        for row in raw_logs:
            name = str(row.get("material_name") or row.get("material") or "-").strip() or "-"
            scans_by_name[name] = int(scans_by_name.get(name, 0) or 0) + 1
            try:
                qty = float(row.get("qty") or 0)
            except Exception:
                qty = 0.0
            qty_by_name[name] = float(qty_by_name.get(name, 0.0) or 0.0) + max(0.0, qty)
        for row in reversed(raw_logs):
            name = str(row.get("material_name") or row.get("material") or "-").strip() or "-"
            if name in seen_names:
                continue
            seen_names.add(name)
            recent_unique.append(name)
            if len(recent_unique) >= 3:
                break
        while len(recent_unique) < 3:
            recent_unique.append("-")

        def _to_float(value: Any) -> Optional[float]:
            raw = str(value or "").strip()
            if not raw:
                return None
            try:
                return float(raw.replace(",", ""))
            except Exception:
                m = re.search(r"(\d+(?:\.\d+)?)", raw.replace(",", ""))
                if not m:
                    return None
                try:
                    return float(m.group(1))
                except Exception:
                    return None

        requested_part_qty = 0.0
        part_rows = self._job_part_rows()
        for part in part_rows:
            v = _to_float((part or {}).get("request_part_qty"))
            if v is not None and v > 0:
                requested_part_qty = v
                break
        part_qty_info = self._resolve_part_qty_per_unit(part_rows[0] if part_rows else None)
        part_qty_per_unit = float(part_qty_info.get("value") or TEMP_PART_QTY_PER_UNIT)

        n1, n2, n3 = recent_unique[0], recent_unique[1], recent_unique[2]
        self.rightRawSacks.setText(f"Raw Mat 1: {n1}    Sacks: {int(scans_by_name.get(n1, 0) or 0)}")
        self.rightRawField.setText(f"Raw Mat 2: {n2}    Sacks: {int(scans_by_name.get(n2, 0) or 0)}")
        self.rightRawTotalScans.setText(f"Raw Mat 3: {n3}    Sacks: {int(scans_by_name.get(n3, 0) or 0)}")
        preview_names = [n1, n2, n3]
        for idx, mat_name in enumerate(preview_names):
            display_name = str(mat_name or "-")
            if len(display_name) > 14:
                display_name = f"{display_name[:14]}\n{display_name[14:28]}"
            else:
                display_name = f"{display_name}\n "
            qty_val = float(qty_by_name.get(mat_name, 0.0) or 0.0)
            if requested_part_qty > 0:
                progress = (qty_val / requested_part_qty)
            else:
                progress = 0.0
            if idx < len(self.rawPreviewNames):
                self.rawPreviewNames[idx].setText(display_name)
            if idx < len(self.rawPreviewRings):
                self.rawPreviewRings[idx].set_value_text(str(int(round(qty_val))))
                self.rawPreviewRings[idx].set_progress(progress)
        self._update_product_parts_weight_indicator()

        if s.downtime_reason_code and s.downtime_reason_text:
            self.rightDowntimeReason.setText(f"Reason {s.downtime_reason_code}: {s.downtime_reason_text}")
            self.productionLiveReason.setText(
                f"REASON: {s.downtime_reason_code} {s.downtime_reason_text}"
            )
        else:
            self.rightDowntimeReason.setText("Reason: -")
            self.productionLiveReason.setText("REASON: -")
        if s.waiting_downtime_start_maintenance:
            action_text = "SCAN MAINTENANCE QR\nTO START DOWNTIME"
        elif s.waiting_downtime_end_maintenance:
            action_text = "SCAN PDR DONE QR WHEN\nREPAIR IS DONE"
        elif s.waiting_cycle_time_input:
            if str(s.cycle_time_new_input or "").strip():
                action_text = "SCAN QR\nTO CONFIRM"
            else:
                action_text = "SCAN NUMKEYS\nTO INPUT"
        elif s.waiting_maintenance_qr:
            action_text = "SCAN MAINTENANCE QR\nTO STOP DOWNTIME"
        elif s.waiting_supervisor_qr:
            action_text = "MACHINE UNDER REPAIR /\nADJUSTMENT"
        elif s.waiting_operator_downtime_confirm:
            action_text = "SCAN OPERATOR QR\nTO PROCEED"
        else:
            action_text = "MACHINE UNDER REPAIR /\nADJUSTMENT"
        self.productionActionBanner.setText(action_text)
        self.rightStartupReject.setText(f"Start Up Reject: {s.startup_reject_total}")
        self.rightMaintenance.setText(f"Maintenance: {s.maintenance_name or '-'}")
        self.productionMaintenanceLine.setText(f"MAINTENANCE: {s.maintenance_name or '-'}")
        self.productionMaintenanceLine.setVisible(bool(self._overlay_mode == "active"))
        self.rightSupervisor.setText(f"Supervisor: {s.supervisor_name or '-'}")
        self.rightSupervisorLeft.setText(f"Supervisor: {s.supervisor_name or '-'}")

        overlay_wait_seconds = None
        if s.waiting_downtime_start_maintenance and s.downtime_wait_started_at:
            overlay_wait_seconds = max(0, int(time.time() - s.downtime_wait_started_at))
        elif s.downtime_wait_last_seconds is not None:
            overlay_wait_seconds = int(s.downtime_wait_last_seconds)

        overlay_downtime_seconds = None
        if s.maintenance_downtime_seconds is not None:
            overlay_downtime_seconds = int(s.maintenance_downtime_seconds)
        elif s.downtime_started_at:
            overlay_downtime_seconds = max(0, int(time.time() - s.downtime_started_at))
        elif s.downtime_last_seconds is not None:
            overlay_downtime_seconds = int(s.downtime_last_seconds)

        waiting_indicator_active = bool(s.waiting_downtime_start_maintenance and s.downtime_wait_started_at)
        downtime_indicator_active = bool(
            s.maintenance_downtime_seconds is not None or s.downtime_started_at
        )
        self._apply_timer_indicator_state(waiting_indicator_active, downtime_indicator_active)

        self._set_overlay_timer_value(
            getattr(self, "productionWaitingValue", None),
            self._format_timer_seconds(overlay_wait_seconds),
        )
        self._set_overlay_timer_value(
            getattr(self, "productionDowntimeValue", None),
            self._format_timer_seconds(overlay_downtime_seconds),
        )

        if s.waiting_downtime_start_maintenance and s.downtime_wait_started_at:
            elapsed_wait = max(0, int(time.time() - s.downtime_wait_started_at))
            hh = elapsed_wait // 3600
            mm = (elapsed_wait % 3600) // 60
            ss = elapsed_wait % 60
            self.rightDowntimeTimer.setText(f"Waiting: {hh:02d}:{mm:02d}:{ss:02d}")
        elif s.maintenance_downtime_seconds is not None:
            hh = s.maintenance_downtime_seconds // 3600
            mm = (s.maintenance_downtime_seconds % 3600) // 60
            ss = s.maintenance_downtime_seconds % 60
            self.rightDowntimeTimer.setText(f"Downtime: {hh:02d}:{mm:02d}:{ss:02d}")
        elif s.downtime_started_at:
            elapsed = max(0, int(time.time() - s.downtime_started_at))
            hh = elapsed // 3600
            mm = (elapsed % 3600) // 60
            ss = elapsed % 60
            self.rightDowntimeTimer.setText(f"Downtime: {hh:02d}:{mm:02d}:{ss:02d}")
        else:
            if s.downtime_last_seconds is not None:
                hh = s.downtime_last_seconds // 3600
                mm = (s.downtime_last_seconds % 3600) // 60
                ss = s.downtime_last_seconds % 60
                self.rightDowntimeTimer.setText(f"Downtime: {hh:02d}:{mm:02d}:{ss:02d}")
            else:
                self.rightDowntimeTimer.setText("Downtime: 00:00:00")

    def _apply_production_timer_fonts(self):
        family = str(getattr(self, "_digital_font_family", "") or "").strip() or "DS-Digital"
        label_pairs = (
            (getattr(self, "productionWaitingPanel", None), getattr(self, "productionWaitingLabel", None)),
            (getattr(self, "productionDowntimePanel", None), getattr(self, "productionDowntimeLabel", None)),
        )
        value_pairs = (
            (getattr(self, "productionWaitingPanel", None), getattr(self, "productionWaitingValue", None)),
            (getattr(self, "productionDowntimePanel", None), getattr(self, "productionDowntimeValue", None)),
        )
        base_css = f"color: #38bdf8; background: transparent; border: none; font-family: '{family}';"
        label_px = self._resolve_production_timer_font_px(
            cached_attr="_production_timer_label_px",
            panel=getattr(self, "productionWaitingPanel", None),
            text="WAITING TIME",
            min_px=26,
            max_px=54,
            width_ratio=0.80,
            height_ratio=0.20,
            family=family,
        )
        value_px = self._resolve_production_timer_font_px(
            cached_attr="_production_timer_value_px",
            panel=getattr(self, "productionWaitingPanel", None),
            text="00:00:00",
            min_px=42,
            max_px=82,
            width_ratio=0.86,
            height_ratio=0.34,
            family=family,
        )
        for panel, widget in label_pairs:
            if panel is None or widget is None:
                continue
            widget.setStyleSheet(base_css + f"font-size: {label_px}px; line-height: 1.0;")
            label_font = QFont(family)
            label_font.setPixelSize(label_px)
            label_metrics = QFontMetrics(label_font)
            widget.setFixedHeight(max(26, label_metrics.height() + 2))
        for panel, widget in value_pairs:
            if panel is None or widget is None:
                continue
            widget.setStyleSheet(base_css + f"font-size: {value_px}px; line-height: 1.0;")
            value_font = QFont(family)
            value_font.setPixelSize(value_px)
            value_metrics = QFontMetrics(value_font)
            widget.setFixedHeight(max(44, value_metrics.height() + 2))

    def _resolve_production_timer_font_px(
        self,
        cached_attr: str,
        panel: Optional[QWidget],
        text: str,
        min_px: int,
        max_px: int,
        width_ratio: float,
        height_ratio: float,
        family: str,
    ) -> int:
        cached_px = getattr(self, cached_attr, None)
        if isinstance(cached_px, int) and cached_px > 0:
            return cached_px
        fitted_px = self._fit_overlay_timer_font(
            panel,
            text,
            min_px=min_px,
            max_px=max_px,
            width_ratio=width_ratio,
            height_ratio=height_ratio,
            family=family,
        )
        setattr(self, cached_attr, fitted_px)
        return fitted_px

    def _fit_overlay_timer_font(
        self,
        panel: Optional[QWidget],
        text: str,
        min_px: int,
        max_px: int,
        width_ratio: float,
        height_ratio: float,
        family: str,
    ) -> int:
        if panel is None:
            return min_px
        panel_w = max(1, int(panel.width()))
        panel_h = max(1, int(panel.height()))
        avail_w = max(1, int(panel_w * width_ratio))
        avail_h = max(1, int(panel_h * height_ratio))
        sample = str(text or "00:00:00")
        best = min_px
        for px in range(max_px, min_px - 1, -1):
            font = QFont(family)
            font.setPixelSize(px)
            metrics = QFontMetrics(font)
            text_w = max(1, metrics.horizontalAdvance(sample))
            text_h = max(1, metrics.height())
            if text_w <= avail_w and text_h <= avail_h:
                best = px
                break
        return best

    @staticmethod
    def _format_timer_seconds(total_seconds: Optional[int]) -> str:
        if total_seconds is None:
            return "00:00:00"
        safe_seconds = max(0, int(total_seconds))
        hh = safe_seconds // 3600
        mm = (safe_seconds % 3600) // 60
        ss = safe_seconds % 60
        return f"{hh:02d}:{mm:02d}:{ss:02d}"

    @staticmethod
    def _set_overlay_timer_value(widget: Optional[QLabel], value: str):
        if widget is not None:
            widget.setText(str(value or "00:00:00"))

    def _set_linkage_job_label_text(self, widget: Optional[QLabel], value: str):
        if widget is None:
            return
        text = str(value or "-")
        widget.setText(text)
        base_font = widget.font()
        family = base_font.family()
        weight = base_font.weight()
        avail_w = max(1, widget.contentsRect().width() or widget.width() or 1)
        best_px = 10
        for px in range(16, 9, -1):
            font = QFont(family)
            font.setPixelSize(px)
            font.setWeight(weight)
            metrics = QFontMetrics(font)
            if metrics.horizontalAdvance(text) <= avail_w:
                best_px = px
                break
        fitted = QFont(base_font)
        fitted.setPixelSize(best_px)
        widget.setFont(fitted)

    def _refresh_linkage_panel(self):
        s = self.state
        if getattr(self, "linkageMirrorOuter", None) is None:
            return
        linked_rows = list(s.linkage_jobs or [])
        linked_names = [
            str(r.get("job_name") or r.get("job_code") or "-")
            for r in linked_rows[:3]
        ]
        while len(linked_names) < 3:
            linked_names.append("-")
        self._set_linkage_job_label_text(self.linkageMirrorJob1, linked_names[0])
        self._set_linkage_job_label_text(self.linkageMirrorJob2, linked_names[1])
        self._set_linkage_job_label_text(self.linkageMirrorJob3, linked_names[2])
        has_linked_jobs = bool(linked_rows)
        self.linkageMirrorPack.setText(str(s.pack_count) if has_linked_jobs else "0")
        self.linkageMirrorGood.setText(str(s.good_total) if has_linked_jobs else "0")
        self.linkageMirrorButal.setText(str(s.butal_total) if has_linked_jobs else "0")
        self.linkageMirrorTotalGood.setText(str(s.good_total + s.butal_total) if has_linked_jobs else "0")
        progress = self._compute_job_progress_metrics()
        self.linkageMirrorProduced.setText(f"{progress['produced_now']} / {progress['target_qty']}")
        self.linkageMirrorRemaining.setText(str(progress["remaining_qty"]))
        self.linkageMirrorOverrun.setText(str(progress["overrun_qty"]))
        self.linkageMirrorOuter.setVisible(True)
        self._refresh_history_panel()

    def _refresh_history_panel(self):
        if not all(
            hasattr(self, name)
            for name in ("historyPackCol", "historyRawCol", "historyActionCol")
        ):
            return
        s = self.state

        def _fmt_ts(raw_val: Any) -> str:
            txt = str(raw_val or "").strip()
            if not txt:
                return "-"
            try:
                dt = datetime.fromisoformat(txt.replace("Z", "+00:00"))
                return dt.astimezone().strftime("%H:%M:%S")
            except Exception:
                return txt[-8:] if len(txt) >= 8 else txt

        pack_rows = []
        for row in reversed(list(s.product_pack_history_logs or [])[-20:]):
            if not isinstance(row, dict):
                continue
            idx = str(row.get("index") or "-")
            qty = str(row.get("qty_q") or row.get("qty") or "-")
            pid_raw = str(row.get("product_p") or row.get("product_id") or "").strip()
            pid = pid_raw.lstrip("0") if pid_raw.isdigit() else pid_raw
            pid = pid or ""
            pname = self._lookup_product_name(pid) if pid else ""
            if pid and not pname:
                if self._refresh_product_catalog_cache_from_api():
                    pname = self._lookup_product_name(pid)
            product_name = pname or (f"Product {pid}" if pid else "-")
            ts = _fmt_ts(row.get("scanned_at"))
            pack_rows.append(f"{idx} | {product_name} | {qty} | {ts}")

        raw_rows = []
        for row in reversed(list(s.raw_material_logs or [])[-20:]):
            if not isinstance(row, dict):
                continue
            name = str(row.get("material_name") or row.get("material") or "-").strip() or "-"
            qty = int(row.get("qty") or 1)
            raw_rows.append(f"{_fmt_ts(row.get('scanned_at'))}  {name}  +{qty}")

        action_rows = []
        raw_actions = list(reversed(list(getattr(self, "_action_logs", []) or [])[-20:]))
        for idx, row in enumerate(raw_actions, start=1):
            txt = str(row or "").strip()
            if not txt:
                continue
            ts = "-"
            action_text = txt
            m = re.match(r"^(\d{2}:\d{2}:\d{2})\s+(.*)$", txt)
            if m:
                ts = m.group(1)
                action_text = m.group(2).strip()
            has_pack_fields = ("Q:" in action_text) and ("I:" in action_text)
            if has_pack_fields:
                m_idx = re.search(r"\bI\s*:\s*([0-9]+)\b", action_text)
                m_qty = re.search(r"\bQ\s*:\s*([0-9]+)\b", action_text)
                item_idx = m_idx.group(1) if m_idx else str(idx)
                qty_val = m_qty.group(1) if m_qty else "-"
                name_text = re.sub(r"\bQ\s*:\s*[0-9]+\b", "", action_text)
                name_text = re.sub(r"\bI\s*:\s*[0-9]+\b", "", name_text)
                name_text = re.sub(r"\s{2,}", " ", name_text).strip(" |")
                action_rows.append(f"{item_idx} | {name_text} | {qty_val} | {ts}")
            else:
                action_rows.append(action_text)

        self._sync_history_column(self.historyPackCol, "pack", pack_rows)
        self._sync_history_column(self.historyRawCol, "raw", raw_rows)
        self._sync_history_column(self.historyActionCol, "action", action_rows)

    def _sync_history_column(self, col_widget: Any, key: str, entries: List[str]):
        vals = [str(x).strip() for x in (entries or []) if str(x).strip()]
        last_attr = f"_history_last_{key}"
        inited_attr = f"_history_init_{key}"
        if not bool(getattr(self, inited_attr, False)):
            col_widget.set_snapshot(vals)
            setattr(self, last_attr, vals[0] if vals else "")
            setattr(self, inited_attr, True)
            return
        latest = vals[0] if vals else ""
        prev = str(getattr(self, last_attr, "") or "")
        if latest and latest != prev:
            col_widget.push_scan(latest)
            setattr(self, last_attr, latest)
        elif not latest and prev:
            col_widget.set_snapshot([])
            setattr(self, last_attr, "")

    def _save_finished_job_local(self, payload: Dict[str, Any]):
        return _insert_finished_job_sql(payload)

    def _load_local_job_records(self, job_code: str) -> List[Dict[str, Any]]:
        code = str(job_code or "").strip()
        if not code:
            return []
        rows: List[Dict[str, Any]] = []
        for row in _load_finished_jobs_sql():
            if not isinstance(row, dict):
                continue
            if str(row.get("job_code") or "").strip() != code:
                continue
            rows.append(row)
        return rows

    def _local_shift_partial_rows(self, job_code: str, *, approved_only: bool = False) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for row in self._load_local_job_records(job_code):
            if str(row.get("record_type") or "").strip().upper() != RECORD_TYPE_SHIFT_PARTIAL:
                continue
            status = str(row.get("review_status") or "").strip().upper()
            if approved_only and status != REVIEW_STATUS_APPROVED:
                continue
            rows.append(row)
        return rows

    def _local_shift_partial_total(self, job_code: str, *, approved_only: bool = False) -> int:
        total = 0
        for row in self._local_shift_partial_rows(job_code, approved_only=approved_only):
            total += int(round(self._parse_number(row.get("partial_qty", row.get("total_good", 0)))))
        return max(0, total)

    def _current_shift_good_total(self) -> int:
        s = self.state
        if not s.operator_shift_started_at:
            return 0
        good_delta = max(0, int(s.good_total or 0) - int(s.operator_shift_baseline_good_total or 0))
        butal_delta = max(0, int(s.butal_total or 0) - int(s.operator_shift_baseline_butal_total or 0))
        return max(0, good_delta + butal_delta)

    def _start_operator_shift_tracking(self):
        s = self.state
        if not (s.machine_code and s.job_code and s.operator_id):
            return
        s.operator_shift_index = int(s.operator_shift_index or 0) + 1
        s.operator_shift_started_at = datetime.now(timezone.utc).isoformat()
        s.operator_shift_baseline_cycle_time = s.cycle_time_current
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
        shift_avg_cycle_seconds = self._compute_current_shift_avg_cycle_seconds()
        payload = s.job_payload or {}
        data_obj = payload.get("data") if isinstance(payload, dict) else {}
        job = data_obj.get("job") if isinstance(data_obj, dict) else {}
        job_details = data_obj.get("job_details") if isinstance(data_obj, dict) else {}
        cavity_count = 1
        if isinstance(job_details, dict) or isinstance(job, dict):
            cavity_count = (
                (job_details.get("no_of_cavity") if isinstance(job_details, dict) else None)
                or (job.get("custom_11") if isinstance(job, dict) else None)
                or 1
            )
        shift_qty_per_shift = self._qty_per_shift_from_cycle(shift_avg_cycle_seconds, cavity_count)
        return {
            "record_type": RECORD_TYPE_SHIFT_PARTIAL,
            "shift_index": int(s.operator_shift_index or (len(s.operator_shift_logs or []) + 1)),
            "reason": str(reason or "SHIFT_CHANGE"),
            "started_at_utc": started_at_utc,
            "ended_at_utc": ended_at_utc,
            "finished_at_utc": ended_at_utc,
            "machine_code": s.machine_code,
            "machine_name": _machine_display_name(s.machine_code, s.machine_name),
            "client_id": CLIENT_ID,
            "job_code": s.job_code,
            "job_name": s.job_name,
            "operator_id": s.operator_id,
            "operator_name": self._operator_display_name(s.operator_id),
            "pack_count": pack_count,
            "good_total": good_total,
            "butal_total": butal_total,
            "reject_total": reject_total,
            "total_good": int(good_total + butal_total),
            "partial_qty": int(good_total + butal_total),
            "reject_breakdown": reject_delta,
            "startup_reject_total": startup_reject_total,
            "raw_sacks_count": raw_sacks_count,
            "raw_material_logs": list((s.raw_material_logs or [])[raw_from:]),
            "raw_material_scans": list(s.raw_material_scans or []),
            "product_pack_history_logs": list((s.product_pack_history_logs or [])[pack_from:]),
            "reject_review_logs": list((s.reject_review_logs or [])[review_from:]),
            "downtime_active": bool(s.downtime_active),
            "downtime_reason_code": s.downtime_reason_code,
            "downtime_reason_text": s.downtime_reason_text,
            "downtime_last_seconds": s.downtime_last_seconds,
            "cycle_time_current": s.cycle_time_current,
            "cycle_time_shift_avg_seconds": shift_avg_cycle_seconds,
            "qty_per_shift_avg_cycle": shift_qty_per_shift,
            "maintenance_name": s.maintenance_name,
            "supervisor_name": s.supervisor_name,
            "job_payload": payload if isinstance(payload, dict) else {},
            "review_status": REVIEW_STATUS_PENDING,
            "review_history": [],
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
            "job_started_at": s.job_started_at,
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
            "downtime_wait_started_at": s.downtime_wait_started_at,
            "downtime_wait_last_seconds": s.downtime_wait_last_seconds,
            "waiting_downtime_start_maintenance": bool(s.waiting_downtime_start_maintenance),
            "waiting_downtime_end_maintenance": bool(s.waiting_downtime_end_maintenance),
            "downtime_resolution_started_at": s.downtime_resolution_started_at,
            "maintenance_downtime_seconds": s.maintenance_downtime_seconds,
            "supervisor_downtime_confirmation_started_at": s.supervisor_downtime_confirmation_started_at,
            "supervisor_downtime_confirmation_seconds": s.supervisor_downtime_confirmation_seconds,
            "operator_downtime_confirmation_started_at": s.operator_downtime_confirmation_started_at,
            "operator_downtime_confirmation_seconds": s.operator_downtime_confirmation_seconds,
            "cycle_time_current": s.cycle_time_current,
            "cycle_time_change_logs": list(s.cycle_time_change_logs or []),
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
            "live_cycle_last_scan_at": s.live_cycle_last_scan_at,
            "live_cycle_total_seconds": float(s.live_cycle_total_seconds or 0.0),
            "live_cycle_intervals": int(s.live_cycle_intervals or 0),
            "live_cycle_total_units": int(s.live_cycle_total_units or 0),
            "live_cycle_avg_seconds": s.live_cycle_avg_seconds,
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
            "action_logs": list(getattr(self, "_action_logs", []) or []),
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
            "operator_shift_baseline_cycle_time": s.operator_shift_baseline_cycle_time,
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
            "external_average_weight_grams": s.external_average_weight_grams,
            "external_average_weight_unit": s.external_average_weight_unit,
            "external_average_weight_received_at": s.external_average_weight_received_at,
        }

    def _save_active_session_snapshot(self):
        s = self.state
        machine_code = str(s.machine_code or "").strip()
        if not machine_code:
            return
        snapshot = self._state_to_active_snapshot()
        _upsert_active_session_json(snapshot)
        self._trigger_active_session_sql_sync(force=False)

    def _load_active_session_snapshot(self, machine_code: str) -> Optional[Dict[str, Any]]:
        code = str(machine_code or "").strip()
        if not code:
            return None
        rows = _load_active_sessions_json()
        snap = rows.get(code)
        if isinstance(snap, dict):
            return snap
        rows = _load_active_sessions_sql()
        snap = rows.get(code)
        if isinstance(snap, dict):
            return snap
        return None

    def _clear_active_session_snapshot(self, machine_code: Optional[str]):
        code = str(machine_code or "").strip()
        if not code:
            return
        _delete_active_session_json(code)
        _delete_active_session_sql(code)

    def _sync_active_session_snapshots_to_sql(self):
        self._trigger_active_session_sql_sync(force=True)

    def _trigger_active_session_sql_sync(self, force: bool = False):
        now_ts = time.time()
        if not force and (now_ts - float(self._active_session_sql_sync_last_attempt or 0.0)) < 10.0:
            return
        with self._active_session_sql_sync_lock:
            if self._active_session_sql_sync_inflight:
                return
            self._active_session_sql_sync_inflight = True
            self._active_session_sql_sync_last_attempt = now_ts

        def _run():
            ok = False
            try:
                ok = _sync_active_sessions_json_to_sql()
            except Exception as e:
                print(f"[SQL] Active session sync error: {e}")
            finally:
                with self._active_session_sql_sync_lock:
                    self._active_session_sql_sync_inflight = False
                    if ok:
                        self._active_session_sql_sync_last_ok = time.time()
            if ok:
                print("[SQL] Active session snapshot sync: SQL OK")
            else:
                print("[SQL] Active session snapshot sync: SQL pending, local JSON retained")

        threading.Thread(target=_run, daemon=True).start()

    def _restore_state_from_snapshot(self, snap: Dict[str, Any]):
        s = self.state
        s.machine_code = snap.get("machine_code")
        s.machine_name = _machine_display_name(snap.get("machine_code"), snap.get("machine_name"))
        s.job_code = snap.get("job_code")
        s.job_name = snap.get("job_name")
        s.job_started_at = snap.get("job_started_at")
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
        s.downtime_wait_started_at = snap.get("downtime_wait_started_at")
        s.downtime_wait_last_seconds = snap.get("downtime_wait_last_seconds")
        s.waiting_downtime_start_maintenance = bool(snap.get("waiting_downtime_start_maintenance"))
        s.waiting_downtime_end_maintenance = bool(snap.get("waiting_downtime_end_maintenance"))
        s.downtime_resolution_started_at = snap.get("downtime_resolution_started_at")
        s.maintenance_downtime_seconds = snap.get("maintenance_downtime_seconds")
        s.supervisor_downtime_confirmation_started_at = snap.get("supervisor_downtime_confirmation_started_at")
        s.supervisor_downtime_confirmation_seconds = snap.get("supervisor_downtime_confirmation_seconds")
        s.operator_downtime_confirmation_started_at = snap.get("operator_downtime_confirmation_started_at")
        s.operator_downtime_confirmation_seconds = snap.get("operator_downtime_confirmation_seconds")
        s.cycle_time_current = snap.get("cycle_time_current")
        s.cycle_time_change_logs = list(snap.get("cycle_time_change_logs") or [])
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
        s.live_cycle_last_scan_at = snap.get("live_cycle_last_scan_at")
        s.live_cycle_total_seconds = float(snap.get("live_cycle_total_seconds") or 0.0)
        s.live_cycle_intervals = int(snap.get("live_cycle_intervals") or 0)
        s.live_cycle_total_units = int(snap.get("live_cycle_total_units") or 0)
        live_avg = snap.get("live_cycle_avg_seconds")
        s.live_cycle_avg_seconds = float(live_avg) if live_avg is not None else None
        if s.live_cycle_last_scan_at is None and s.machine_code:
            s.live_cycle_last_scan_at = time.time()
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
        self._action_logs = list(snap.get("action_logs") or [])
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
        s.operator_shift_baseline_cycle_time = snap.get("operator_shift_baseline_cycle_time")
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
        avg_weight = snap.get("external_average_weight_grams")
        s.external_average_weight_grams = float(avg_weight) if avg_weight is not None else None
        s.external_average_weight_unit = snap.get("external_average_weight_unit")
        s.external_average_weight_received_at = snap.get("external_average_weight_received_at")
        for key in ("pack", "raw", "action"):
            setattr(self, f"_history_init_{key}", False)
            setattr(self, f"_history_last_{key}", "")
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
        elif s.waiting_cycle_time_input or s.waiting_supervisor_qr:
            self.resolveTitle.setText("DOWNTIME NEW CYCLE TIME")
            self.resolveOldCycleTitle.setText("NEW CYCLE TIME INPUT")
            self.resolveNewCycleTitle.setText("CONFIRMED BY")
            self.resolveOldCycle.setText(f"New Cycle Time Input: {s.cycle_time_new_input}")
            self.resolveNewCycle.setText(f"Confirmed by: {s.cycle_time_confirmed_by or ''}")
            if s.waiting_cycle_time_input:
                if str(s.cycle_time_new_input or "").strip():
                    self.resolveHint.setText("SCAN QR TO CONFIRM")
                else:
                    self.resolveHint.setText("SCAN NUMKEYS TO INPUT")
            else:
                self.resolveHint.setText("SCAN SUPERVISOR QR")
            self._show_resolve_overlay()

    def _build_finished_job_payload(self) -> Dict[str, Any]:
        s = self.state
        return {
            "record_type": RECORD_TYPE_FINAL_JOB,
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
            "downtime_wait_last_seconds": s.downtime_wait_last_seconds,
            "downtime_reason_code": s.downtime_reason_code,
            "downtime_reason_text": s.downtime_reason_text,
            "cycle_time_current": s.cycle_time_current,
            "maintenance_name": s.maintenance_name,
            "supervisor_name": s.supervisor_name,
            "operator_shift_logs": list(s.operator_shift_logs or []),
            "partial_qty": int((s.good_total or 0) + (s.butal_total or 0)),
            "review_status": REVIEW_STATUS_CLOSED,
            "linkage_enabled": bool(s.linkage_enabled),
            "linkage_job_code": s.linkage_job_code,
            "linkage_job_name": s.linkage_job_name,
            "linkage_job_payload": s.linkage_job_payload or {},
            "linkage_jobs": list(s.linkage_jobs or []),
            "external_average_weight_grams": s.external_average_weight_grams,
            "external_average_weight_unit": s.external_average_weight_unit,
            "external_average_weight_received_at": s.external_average_weight_received_at,
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
        s.job_started_at = None
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
        s.downtime_wait_started_at = None
        s.downtime_wait_last_seconds = None
        s.waiting_downtime_start_maintenance = False
        s.waiting_downtime_end_maintenance = False
        s.downtime_resolution_started_at = None
        s.maintenance_downtime_seconds = None
        s.supervisor_downtime_confirmation_started_at = None
        s.supervisor_downtime_confirmation_seconds = None
        s.operator_downtime_confirmation_started_at = None
        s.operator_downtime_confirmation_seconds = None
        s.cycle_time_current = None
        s.cycle_time_change_logs = []
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
        s.operator_shift_baseline_cycle_time = None
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
        self._clear_external_average_weight()
        self._reset_live_cycle_tracking()
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
        self.rightCycleCurrent.setText(f"Act Cycle Time: {s.cycle_time_current or ''}")
        if hasattr(self, "topCycleCount") and self.topCycleCount is not None:
            self.topCycleCount.setText(f"Confirmed by: {s.cycle_time_confirmed_by or '-'}")
        if hasattr(self, "topCycleCurrent") and self.topCycleCurrent is not None:
            self.topCycleCurrent.setText(f"Act Cycle Time: {s.cycle_time_current or ''}")
        self.rightMaintenance.setText(f"Maintenance: {s.maintenance_name or ''}")
        self.rightSupervisor.setText(f"Supervisor: {s.supervisor_name or ''}")

    def _clear_shift_session_keep_machine(self):
        s = self.state
        active_machine_code = s.machine_code
        active_machine_name = s.machine_name
        self._clear_full_session()
        s.machine_code = active_machine_code
        s.machine_name = active_machine_name
        self._save_active_session_snapshot()
        self._broadcast_machine_no_job_running()
        self.status.setText("Finish shift saved. Scan JOB QR.")

    def _broadcast_machine_no_job_running(self):
        s = self.state
        if not s.machine_code:
            return
        snapshot = self._state_to_active_snapshot()
        self.push_event(
            {
                "type": "MACHINE_STATUS",
                "status": "NO_JOB_RUNNING",
                "session_snapshot": snapshot,
            },
            "MACHINE STATUS NO JOB RUNNING",
            silent=True,
        )

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
        s.downtime_resolution_started_at = None
        s.supervisor_downtime_confirmation_started_at = None
        s.operator_downtime_confirmation_started_at = None
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
        s.cycle_time_confirmed_by = None
        s.waiting_cycle_time_input = True
        s.downtime_resolution_started_at = time.time()
        s.cycle_time_new_input = ""
        self._set_production_overlay_mode("active")
        self._show_production_overlay()
        self._hide_resolve_overlay()
        self.resolveTitle.setText("DOWNTIME NEW CYCLE TIME")
        self.resolveHint.setText("SCAN NUMKEYS TO INPUT")
        self.resolveOldCycleTitle.setText("NEW CYCLE TIME INPUT")
        self.resolveNewCycleTitle.setText("CONFIRMED BY")
        self.resolveOldCycle.setText(f"New Cycle Time Input: {s.cycle_time_new_input}")
        self.resolveNewCycle.setText("Confirmed by: ")
        self._show_resolve_overlay()

    def _update_cycle_input_display(self):
        self.resolveOldCycle.setText(f"New Cycle Time Input: {self.state.cycle_time_new_input}")
        if str(self.state.cycle_time_new_input or "").strip():
            self.resolveHint.setText("SCAN QR TO CONFIRM")
        else:
            self.resolveHint.setText("SCAN NUMKEYS TO INPUT")

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
        self._reject_detail_active_codes = {
            code for code, _label in REJECT_DETAIL_ITEMS if int(counts.get(code, 0)) > 0
        }
        self._sync_reject_detail_header_flash()
        self.rejectDetailTable.viewport().update()

    def _sync_reject_detail_header_flash(self):
        hdr = self.rejectDetailTable.horizontalHeader()
        if isinstance(hdr, RejectDetailHeaderView):
            hdr.set_flash_columns(
                [self._reject_detail_col_by_code.get(code) for code in self._reject_detail_active_codes]
            )
            hdr.set_flash_on(bool(self.enable_flashing_lights and getattr(self, "_reject_detail_flash_on", False)))

    def _tick_reject_detail_flash(self):
        self._reject_detail_flash_on = not self._reject_detail_flash_on
        if self.enable_flashing_lights:
            for item in self.reject_detail_labels.values():
                if int(item.data(Qt.ItemDataRole.UserRole) or 0) == 1:
                    if self._reject_detail_flash_on:
                        item.setBackground(QColor(252, 165, 165, 130))
                    else:
                        item.setBackground(QColor(254, 226, 226, 90))
        self._sync_reject_detail_header_flash()
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
        self._apply_machine_anim_style(str(self.machineAnim.property("mode") or "idle"))

    @staticmethod
    def _normalize_graphics_mode(mode: Any) -> str:
        key = str(mode or "quality").strip().lower().replace(" ", "_")
        if key in ("fast",):
            key = "faster"
        if key in ("faster+quality", "faster_quality", "balanced"):
            key = "faster_quality"
        if key not in ("faster", "faster_quality", "quality"):
            key = "quality"
        return key

    @staticmethod
    def _graphics_mode_label(mode: str) -> str:
        return {
            "faster": "Faster",
            "faster_quality": "Faster + Quality",
            "quality": "Quality",
        }.get(str(mode or "quality"), "Quality")

    def _load_graphics_settings_form(self):
        mode = self._normalize_graphics_mode(self.client_config.get("graphics_mode", "quality"))
        self.graphicsModeToggle.set_mode(mode, emit_signal=False, animate=False)

    def _apply_graphics_mode(self, mode: Any, persist: bool = True):
        mode_key = self._normalize_graphics_mode(mode)
        self.graphics_mode = mode_key
        self.enable_check_animation = mode_key == "quality"
        self.enable_flashing_lights = mode_key in ("faster_quality", "quality")
        self.enable_pulse_effects = mode_key in ("faster_quality", "quality")
        self.enable_heavy_animations = mode_key == "quality"
        self.enable_background_blur = mode_key == "quality"
        self.enable_gif_animations = mode_key == "quality"

        self.chkCheckAnimation.blockSignals(True)
        self.chkFlashingLights.blockSignals(True)
        self.chkPulseEffects.blockSignals(True)
        self.chkCheckAnimation.setChecked(self.enable_check_animation)
        self.chkFlashingLights.setChecked(self.enable_flashing_lights)
        self.chkPulseEffects.setChecked(self.enable_pulse_effects)
        self.chkCheckAnimation.blockSignals(False)
        self.chkFlashingLights.blockSignals(False)
        self.chkPulseEffects.blockSignals(False)
        self._set_toggle_button_text(self.chkCheckAnimation, "Check animation", self.enable_check_animation)
        self._set_toggle_button_text(self.chkFlashingLights, "Flashing lights", self.enable_flashing_lights)
        self._set_toggle_button_text(self.chkPulseEffects, "Pulse / moving effects", self.enable_pulse_effects)
        self.chkCheckAnimation.setEnabled(False)
        self.chkFlashingLights.setEnabled(False)
        self.chkPulseEffects.setEnabled(False)

        self.graphicsModeToggle.set_mode(mode_key, emit_signal=False, animate=False)

        if not self.enable_background_blur:
            self._set_background_blur(False)
            self._set_reject_review_blur(False)
        if hasattr(self, "productionFixAnim") and self.productionFixAnim is not None:
            if self.enable_heavy_animations:
                self.productionFixAnim.show()
                self.productionFixAnim.ensure_running()
            else:
                self.productionFixAnim.timer.stop()
                self.productionFixAnim.hide()
        if self.enable_gif_animations and self._invalid_movie is None:
            self._setup_invalid_overlay_media()
        if self._invalid_movie is not None and not self.enable_gif_animations:
            self._invalid_movie.stop()
        self.invalidGifLabel.setVisible(bool(self.enable_gif_animations and self.invalidOverlay.isVisible() and self._invalid_movie is not None))
        for widget in self.findChildren(CounterCard):
            widget.set_animations_enabled(self.enable_heavy_animations)
        for widget in self.findChildren(CircleProgressBadge):
            widget.set_animations_enabled(self.enable_heavy_animations)
        for widget in self.findChildren(HistoryAnimatedColumn):
            widget.set_animations_enabled(self.enable_heavy_animations)
        self._apply_machine_anim_style(str(self.machineAnim.property("mode") or "idle"))
        self._sync_reject_detail_header_flash()

        if persist:
            self.client_config["graphics_mode"] = mode_key
            _save_client_config(self.client_config)

    def _apply_graphics_settings(self, mode: Optional[str] = None):
        selected = mode if mode is not None else self.graphicsModeToggle.mode()
        self._apply_graphics_mode(selected, persist=True)
        self.status.setText(f"Graphics mode applied: {self._graphics_mode_label(self.graphics_mode)}")

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
            if self._job_api_body_is_unauthorized(data):
                self.status.setText("Job API test failed: bearer token unauthorized. Clear the token or save settings to force a fresh login.")
                self._append_job_api_log("TEST FAIL: response body reported unauthorized bearer token")
                print("[JobAPI] TEST FAIL: response body reported unauthorized bearer token")
                return
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

    def _parse_number(self, value: Any) -> float:
        if value is None:
            return 0.0
        raw = str(value).strip().replace(",", "")
        if not raw:
            return 0.0
        try:
            return float(raw)
        except Exception:
            m = re.search(r"-?\d+(?:\.\d+)?", raw)
            if not m:
                return 0.0
            try:
                return float(m.group(0))
            except Exception:
                return 0.0

    def _clear_external_average_weight(self):
        s = self.state
        s.external_average_weight_grams = None
        s.external_average_weight_unit = None
        s.external_average_weight_received_at = None

    def _job_part_rows(self, payload: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        base_payload = payload if isinstance(payload, dict) else (self.state.job_payload or {})
        job = self._extract_job_record()
        data_obj = base_payload.get("data") if isinstance(base_payload.get("data"), dict) else {}
        job_details = {}
        if isinstance(job.get("job_details"), dict):
            job_details = job.get("job_details") or {}
        elif isinstance(base_payload.get("job_details"), dict):
            job_details = base_payload.get("job_details") or {}
        elif isinstance(data_obj.get("job_details"), dict):
            job_details = data_obj.get("job_details") or {}
        if isinstance(data_obj.get("parts"), list):
            return [r for r in data_obj.get("parts") or [] if isinstance(r, dict)]
        if isinstance(job_details.get("parts"), list):
            return [r for r in job_details.get("parts") or [] if isinstance(r, dict)]
        if isinstance(job_details.get("part_ids"), list):
            return [r for r in job_details.get("part_ids") or [] if isinstance(r, dict)]
        if isinstance(job_details.get("part_ids"), dict):
            return [job_details.get("part_ids") or {}]
        if isinstance(data_obj.get("part_ids"), list):
            return [r for r in data_obj.get("part_ids") or [] if isinstance(r, dict)]
        if isinstance(base_payload.get("part_ids"), list):
            return [r for r in base_payload.get("part_ids") or [] if isinstance(r, dict)]
        return []

    def _resolve_part_qty_per_unit(self, part: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        s = self.state
        ext_weight = s.external_average_weight_grams
        ext_unit = str(s.external_average_weight_unit or "g").strip() or "g"
        if ext_weight is not None and ext_weight > 0:
            return {
                "value": float(ext_weight),
                "source": "app",
                "unit": ext_unit,
                "label": f"App ({float(ext_weight):.4f} {ext_unit})",
            }
        if isinstance(part, dict):
            part_qty = self._parse_number(part.get("part_qty_per_unit"))
            if part_qty > 0:
                return {
                    "value": part_qty,
                    "source": "job_api",
                    "unit": "g",
                    "label": f"Job API ({part_qty:.4f} g)",
                }
        for row in self._job_part_rows():
            part_qty = self._parse_number((row or {}).get("part_qty_per_unit"))
            if part_qty > 0:
                return {
                    "value": part_qty,
                    "source": "job_api",
                    "unit": "g",
                    "label": f"Job API ({part_qty:.4f} g)",
                }
        return {
            "value": TEMP_PART_QTY_PER_UNIT,
            "source": "standard",
            "unit": "g",
            "label": f"Standard ({TEMP_PART_QTY_PER_UNIT:.4f} g)",
        }

    def _update_product_parts_weight_indicator(self):
        if not hasattr(self, "jobPartsTable") or self.jobPartsTable is None:
            return
        info = self._resolve_part_qty_per_unit()
        row_count = int(self.jobPartsTable.rowCount() or 0)
        has_job = bool(str(self.state.job_code or "").strip())
        if row_count <= 0:
            return
        phase = (math.sin(time.time() * 5.2) + 1.0) * 0.5
        for row in range(row_count):
            item = self.jobPartsTable.item(row, 2)
            if item is None:
                continue
            txt = str(item.text() or "").strip()
            if not has_job or txt in ("", "-"):
                item.setBackground(QBrush(Qt.GlobalColor.transparent))
                item.setForeground(QBrush(QColor(239, 240, 242, 226)))
                continue
            if info.get("source") == "app":
                item.setBackground(QBrush(QColor(34, 197, 94, 185)))
                item.setForeground(QBrush(QColor("#ecfdf5")))
            else:
                flash_alpha = int(90 + (95 * phase))
                item.setBackground(QBrush(QColor(248, 113, 113, flash_alpha)))
                item.setForeground(QBrush(QColor("#fff7ed")))

    def _apply_external_average_weight(self, average_grams: float, unit: str):
        grams = float(average_grams or 0.0)
        normalized_unit = str(unit or "g").strip() or "g"
        if grams <= 0:
            return
        s = self.state
        s.external_average_weight_grams = grams
        s.external_average_weight_unit = normalized_unit
        s.external_average_weight_received_at = datetime.now(timezone.utc).isoformat()
        self.status.setText(f"Average weight received from app: {grams:.4f} {normalized_unit}")
        self._refresh_ui()
        if s.machine_code:
            self._save_active_session_snapshot()
        self.push_event(
            {"type": "AVERAGE_WEIGHT_RECEIVED", "average_grams": grams, "unit": normalized_unit},
            f"AVERAGE WEIGHT {grams:.4f} {normalized_unit}",
        )

    def _start_average_weight_server(self):
        if self._avg_weight_server is not None:
            return

        ui = self

        class AverageWeightHandler(BaseHTTPRequestHandler):
            def _send_json(self, status: int, payload: Dict[str, Any]):
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, format: str, *args):
                return

            def do_POST(self):
                if self.path.rstrip("/") != AVERAGE_WEIGHT_API_ENDPOINT:
                    self._send_json(404, {"success": False, "message": "Not found"})
                    return
                try:
                    content_length = int(self.headers.get("Content-Length", "0") or 0)
                except Exception:
                    content_length = 0
                body = self.rfile.read(max(0, content_length))
                try:
                    payload = json.loads(body.decode("utf-8") if body else "{}")
                except Exception:
                    self._send_json(400, {"success": False, "message": "Invalid JSON"})
                    return
                if not isinstance(payload, dict):
                    self._send_json(400, {"success": False, "message": "JSON body must be an object"})
                    return
                try:
                    average_grams = float(payload.get("average_grams"))
                except Exception:
                    self._send_json(400, {"success": False, "message": "average_grams must be numeric"})
                    return
                unit = str(payload.get("unit") or "").strip() or "g"
                if average_grams <= 0:
                    self._send_json(400, {"success": False, "message": "average_grams must be greater than zero"})
                    return
                ui.average_weight_received.emit(average_grams, unit)
                self._send_json(200, {"success": True, "message": "Average weight received"})

        try:
            server = ThreadingHTTPServer((AVERAGE_WEIGHT_API_HOST, AVERAGE_WEIGHT_API_PORT), AverageWeightHandler)
            server.daemon_threads = True
            self._avg_weight_server = server
            self._avg_weight_server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            self._avg_weight_server_thread.start()
            self._avg_weight_server_error = None
            print(f"[AverageWeightAPI] Listening on http://{AVERAGE_WEIGHT_API_HOST}:{AVERAGE_WEIGHT_API_PORT}{AVERAGE_WEIGHT_API_ENDPOINT}")
        except Exception as e:
            self._avg_weight_server = None
            self._avg_weight_server_thread = None
            self._avg_weight_server_error = str(e)
            print(f"[AverageWeightAPI] Failed to start: {e}")

    def _shutdown_average_weight_server(self):
        server = self._avg_weight_server
        self._avg_weight_server = None
        if server is None:
            return
        try:
            server.shutdown()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass

    def _make_finish_summary_table(self, title: str, headers: List[str]) -> QTableWidget:
        section = QFrame()
        section.setStyleSheet(
            "QFrame {"
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(103,107,115,220), stop:1 rgba(56,59,66,230));"
            "border: 1px solid rgba(148,163,184,0.45); border-radius: 18px; }"
            "QLabel { color: #f8fafc; font-size: 16px; font-weight: 900; background: transparent; border: none; }"
            "QTableWidget { background: rgba(15,23,42,0.32); border: none; gridline-color: rgba(148,163,184,0.18); color: #f8fafc; }"
            "QHeaderView::section { background: rgba(71,85,105,0.96); color: #f8fafc; font-weight: 900; border: none; border-bottom: 1px solid rgba(148,163,184,0.35); padding: 7px; }"
            "QTableWidget::item { padding: 5px; border-bottom: 1px solid rgba(148,163,184,0.20); }"
        )
        section.setLayout(QVBoxLayout())
        section.layout().setContentsMargins(10, 10, 10, 10)
        section.layout().setSpacing(6)
        title_lbl = QLabel(title)
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setAlternatingRowColors(False)
        table.setWordWrap(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setFixedHeight(30)
        table.verticalHeader().setDefaultSectionSize(28)
        table.setMinimumHeight(132)
        table.setMaximumHeight(340)
        section.layout().addWidget(title_lbl)
        section.layout().addWidget(table)
        self.finishSummaryBody.layout().addWidget(section)
        return table

    def _set_finish_summary_table_rows(self, table: Optional[QTableWidget], rows: List[List[str]]):
        if table is None:
            return
        clean_rows = rows or [["-"] * max(1, table.columnCount())]
        table.setRowCount(0)
        for row_vals in clean_rows:
            r = table.rowCount()
            table.insertRow(r)
            values = list(row_vals or [])
            while len(values) < table.columnCount():
                values.append("-")
            for c in range(table.columnCount()):
                item = QTableWidgetItem(str(values[c]))
                if c == 0:
                    item.setTextAlignment(int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
                else:
                    item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
                table.setItem(r, c, item)
        header_h = table.horizontalHeader().height()
        row_h = table.verticalHeader().defaultSectionSize()
        frame_h = table.frameWidth() * 2
        target_h = min(340, header_h + (table.rowCount() * row_h) + frame_h + 2)
        table.setMinimumHeight(max(96, target_h))
        table.setMaximumHeight(max(96, target_h))

    def _extract_job_payload_context(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data_obj = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        job = data_obj.get("job") if isinstance(data_obj.get("job"), dict) else {}
        job_details = data_obj.get("job_details") if isinstance(data_obj.get("job_details"), dict) else {}
        if not job and isinstance(payload.get("job"), dict):
            job = payload.get("job") or {}
        if not job_details and isinstance(payload.get("job_details"), dict):
            job_details = payload.get("job_details") or {}
        parts = []
        if isinstance(data_obj.get("parts"), list):
            parts = [r for r in data_obj.get("parts") or [] if isinstance(r, dict)]
        elif isinstance(job_details.get("parts"), list):
            parts = [r for r in job_details.get("parts") or [] if isinstance(r, dict)]
        elif isinstance(job_details.get("part_ids"), list):
            parts = [r for r in job_details.get("part_ids") or [] if isinstance(r, dict)]
        elif isinstance(data_obj.get("part_ids"), list):
            parts = [r for r in data_obj.get("part_ids") or [] if isinstance(r, dict)]
        elif isinstance(payload.get("part_ids"), list):
            parts = [r for r in payload.get("part_ids") or [] if isinstance(r, dict)]
        return {"job": job, "job_details": job_details, "parts": parts}

    def _finish_shift_row_key(self, row: Dict[str, Any]) -> str:
        return "|".join([
            str(row.get("record_type") or "").strip().upper(),
            str(row.get("client_id") or "").strip(),
            str(row.get("machine_code") or "").strip(),
            str(row.get("job_code") or "").strip(),
            str(row.get("operator_id") or "").strip(),
            str(row.get("shift_index") or "").strip(),
            str(row.get("finished_at_utc") or row.get("ended_at_utc") or "").strip(),
        ])

    def _server_finished_job_key(self, row: Dict[str, Any]) -> str:
        return "|".join([
            str(row.get("finished_at_utc", "")),
            str(row.get("machine_code", "")),
            str(row.get("job_code", "")),
            str(row.get("operator_id", "")),
            str(row.get("pack_count", "")),
            str(row.get("good_total", "")),
            str(row.get("butal_total", "")),
            str(row.get("reject_total", "")),
        ])

    def _approve_local_finished_shift(self, shift_payload: Dict[str, Any], reviewer: Dict[str, Any], remarks: str) -> bool:
        key = self._finish_shift_row_key(shift_payload)
        rows = _load_finished_jobs_sql()
        updated = False
        now_utc = datetime.now(timezone.utc).isoformat()
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            if self._finish_shift_row_key(row) != key:
                continue
            row = dict(row)
            row["approved_by"] = reviewer.get("name")
            row["approved_by_code"] = reviewer.get("code")
            row["approved_by_role"] = reviewer.get("role")
            row["approved_remarks"] = remarks
            row["approved_at_utc"] = now_utc
            row["review_status"] = REVIEW_STATUS_APPROVED
            history = list(row.get("review_history") or [])
            history.append({
                "action": "APPROVE",
                "remarks": remarks,
                "actor_name": reviewer.get("name"),
                "actor_code": reviewer.get("code"),
                "actor_role": reviewer.get("role"),
                "timestamp_utc": now_utc,
            })
            row["review_history"] = history
            rows[idx] = row
            shift_payload.update(row)
            updated = True
            break
        if not updated:
            return False
        return _replace_finished_jobs_sql(rows)

    def _approve_server_finished_shift(self, shift_payload: Dict[str, Any], reviewer_badge: str, remarks: str):
        try:
            resp = requests.post(
                f"{str(self.client_config.get('server_url', SERVER_URL)).rstrip('/')}/api/finished-jobs/review",
                json={
                    "job_key": self._server_finished_job_key(shift_payload),
                    "action": "approve",
                    "remarks": remarks,
                    "reviewer_badge": reviewer_badge,
                },
                timeout=4.5,
            )
            return resp.ok
        except Exception:
            return False

    def _populate_finish_shift_summary(self, shift_payload: Dict[str, Any]):
        payload = shift_payload.get("job_payload") if isinstance(shift_payload.get("job_payload"), dict) else {}
        ctx = self._extract_job_payload_context(payload if isinstance(payload, dict) else {})
        job = ctx["job"]
        job_details = ctx["job_details"]
        part_rows = ctx["parts"]
        raw_logs = [x for x in (shift_payload.get("raw_material_logs") or []) if isinstance(x, dict)]
        pack_logs = [x for x in (shift_payload.get("product_pack_history_logs") or []) if isinstance(x, dict)]
        reject_breakdown = shift_payload.get("reject_breakdown") if isinstance(shift_payload.get("reject_breakdown"), dict) else {}

        start_label = self._safe_text(shift_payload.get("started_at_utc"), "-")
        end_label = self._safe_text(shift_payload.get("finished_at_utc") or shift_payload.get("ended_at_utc"), "-")
        self.finishSummaryCards["Machine"].setText(self._safe_text(shift_payload.get("machine_name") or shift_payload.get("machine_code")))
        self.finishSummaryCards["Job"].setText(self._safe_text(shift_payload.get("job_name") or shift_payload.get("job_code")))
        self.finishSummaryCards["Operator"].setText(
            f"{self._safe_text(shift_payload.get('operator_name'))} ({self._safe_text(shift_payload.get('operator_id'))})"
        )
        self.finishSummaryCards["Shift Window"].setText(f"{start_label}\n{end_label}")
        self.finishSummaryCards["Pack Count"].setText(str(int(shift_payload.get("pack_count") or 0)))
        self.finishSummaryCards["Good"].setText(str(int(shift_payload.get("good_total") or 0)))
        self.finishSummaryCards["Butal"].setText(str(int(shift_payload.get("butal_total") or 0)))
        self.finishSummaryCards["Reject"].setText(str(int(shift_payload.get("reject_total") or 0)))
        self.finishSummaryCards["Total Good"].setText(str(int(shift_payload.get("total_good") or 0)))
        self.finishSummaryCards["Raw Sacks"].setText(str(int(shift_payload.get("raw_sacks_count") or 0)))
        self.finishSummaryCards["Cycle Time"].setText(self._safe_text(shift_payload.get("cycle_time_current"), "-"))
        self.finishSummaryCards["Downtime"].setText(self._format_timer_seconds(int(shift_payload.get("downtime_last_seconds") or 0)))

        job_rows = [
            ["Job Code", self._safe_text(shift_payload.get("job_code"))],
            ["Job Name", self._safe_text(shift_payload.get("job_name"))],
            ["Reference", self._safe_text(job.get("ref_no"))],
            ["Product ID", self._safe_text(job_details.get("product_id") or job.get("product_id"))],
            ["Mold", self._safe_text(job_details.get("mold") or job.get("custom_05"))],
            ["Color", self._safe_text(job_details.get("color") or job.get("custom_06"), "N/A")],
            ["Cavities", self._safe_text(job_details.get("no_of_cavity") or job.get("custom_11"))],
            ["Sticker Label", self._safe_text(job_details.get("sticker_label"), "N/A")],
            ["Std Cycle Time", self._safe_text(job_details.get("std_cycle_time"), "N/A")],
            ["Qty/Shift", self._safe_text(job_details.get("qty_per_shift"), "N/A")],
            ["Requested Qty", self._safe_text(job.get("approve_qty") or job.get("request_qty"))],
        ]
        self._set_finish_summary_table_rows(self.finishReviewJobDetails, job_rows)

        counter_rows = [
            ["Pack Count", str(int(shift_payload.get("pack_count") or 0))],
            ["Good", str(int(shift_payload.get("good_total") or 0))],
            ["Butal", str(int(shift_payload.get("butal_total") or 0))],
            ["Reject", str(int(shift_payload.get("reject_total") or 0))],
            ["Total Good", str(int(shift_payload.get("total_good") or 0))],
            ["Startup Reject", str(int(shift_payload.get("startup_reject_total") or 0))],
            ["Partial Qty", str(int(shift_payload.get("partial_qty") or shift_payload.get("total_good") or 0))],
            ["Qty/Shift Avg Cycle", self._safe_text(shift_payload.get("qty_per_shift_avg_cycle"))],
        ]
        self._set_finish_summary_table_rows(self.finishReviewCounters, counter_rows)

        reject_rows = [[str(k), str(int(v or 0))] for k, v in reject_breakdown.items() if int(v or 0) > 0]
        self._set_finish_summary_table_rows(self.finishReviewRejects, reject_rows)

        downtime_rows = [
            ["Review Status", self._safe_text(shift_payload.get("review_status"), REVIEW_STATUS_PENDING)],
            ["Reason Code", self._safe_text(shift_payload.get("downtime_reason_code"))],
            ["Reason", self._safe_text(shift_payload.get("downtime_reason_text"))],
            ["Downtime Last", self._format_timer_seconds(int(shift_payload.get("downtime_last_seconds") or 0))],
            ["Cycle Time", self._safe_text(shift_payload.get("cycle_time_current"))],
            ["Maintenance", self._safe_text(shift_payload.get("maintenance_name"))],
            ["Supervisor", self._safe_text(shift_payload.get("supervisor_name"))],
        ]
        self._set_finish_summary_table_rows(self.finishReviewDowntime, downtime_rows)

        scanned_raw_qty = sum(self._parse_number(x.get("qty")) for x in raw_logs)
        part_table_rows: List[List[str]] = []
        shift_external_avg_weight = shift_payload.get("external_average_weight_grams")
        for part in part_rows:
            request_part_qty = self._parse_number(part.get("request_part_qty"))
            if shift_external_avg_weight is not None and self._parse_number(shift_external_avg_weight) > 0:
                part_qty_per_unit = self._parse_number(shift_external_avg_weight)
            else:
                part_qty_per_unit = self._parse_number(part.get("part_qty_per_unit"))
                if part_qty_per_unit <= 0:
                    part_qty_per_unit = TEMP_PART_QTY_PER_UNIT
            produced_units = max(0.0, self._parse_number(shift_payload.get("good_total")) + self._parse_number(shift_payload.get("butal_total")))
            used_raw_qty = min(scanned_raw_qty, produced_units * part_qty_per_unit) if scanned_raw_qty > 0 else 0.0
            remaining_part_qty = max(request_part_qty - used_raw_qty, 0.0)
            part_table_rows.append([
                self._safe_text(part.get("sku")),
                self._safe_text(part.get("name")),
                f"{part_qty_per_unit:.4f}",
                f"{used_raw_qty:.2f}".rstrip("0").rstrip("."),
                self._safe_text(part.get("request_part_qty")),
                f"{remaining_part_qty:.2f}".rstrip("0").rstrip("."),
            ])
        self._set_finish_summary_table_rows(self.finishReviewParts, part_table_rows)

        raw_rows = []
        for row in raw_logs:
            raw_rows.append([
                self._safe_text(row.get("material_name") or row.get("material")),
                self._safe_text(row.get("qty"), "0"),
                self._safe_text(row.get("index")),
                self._safe_text(row.get("total_labels")),
                self._safe_text(row.get("lot_number")),
                self._safe_text(row.get("po_number")),
                self._safe_text(row.get("scanned_at")),
            ])
        self._set_finish_summary_table_rows(self.finishReviewRaw, raw_rows)

        pack_rows = []
        for row in pack_logs[-20:]:
            product_name = self._safe_text(row.get("product_name") or row.get("product_desc") or row.get("product_id"))
            pack_rows.append([
                self._safe_text(row.get("index")),
                product_name,
                self._safe_text(row.get("qty"), "0"),
                self._safe_text(row.get("lot_number")),
                self._safe_text(row.get("operator_name") or row.get("operator")),
                self._safe_text(row.get("scanned_at")),
            ])
        self._set_finish_summary_table_rows(self.finishReviewPack, pack_rows)

    def _compute_job_progress_metrics(self) -> Dict[str, int]:
        payload = self.state.job_payload or {}
        data_obj = payload.get("data") if isinstance(payload, dict) else {}
        job = data_obj.get("job") if isinstance(data_obj, dict) and isinstance(data_obj.get("job"), dict) else {}
        partials = data_obj.get("partials") if isinstance(data_obj, dict) and isinstance(data_obj.get("partials"), list) else []
        job_code = str(self.state.job_code or "").strip()
        target_qty_raw = job.get("approve_qty")
        if self._parse_number(target_qty_raw) <= 0:
            target_qty_raw = job.get("request_qty")
        target_qty = max(0, int(round(self._parse_number(target_qty_raw))))
        api_partial_total = 0
        for row in partials:
            if not isinstance(row, dict):
                continue
            api_partial_total += int(round(self._parse_number(row.get("partial_qty"))))
        local_partial_total = self._local_shift_partial_total(job_code, approved_only=False)
        live_shift_good = self._current_shift_good_total()
        produced_now = max(0, api_partial_total + local_partial_total + live_shift_good)
        remaining_qty = max(target_qty - produced_now, 0)
        overrun_qty = max(produced_now - target_qty, 0)
        return {
            "target_qty": target_qty,
            "api_partial_total": api_partial_total,
            "local_partial_total": local_partial_total,
            "live_shift_good": live_shift_good,
            "produced_now": produced_now,
            "remaining_qty": remaining_qty,
            "overrun_qty": overrun_qty,
        }

    def _maybe_show_fulfilled_notice(self):
        metrics = self._compute_job_progress_metrics()
        job_code = str(self.state.job_code or "").strip()
        target_qty = int(metrics.get("target_qty", 0) or 0)
        produced_now = int(metrics.get("produced_now", 0) or 0)
        if not job_code or target_qty <= 0 or produced_now < target_qty:
            if self._fulfilled_notice_job_code == job_code:
                self._fulfilled_notice_job_code = ""
            return
        if self._fulfilled_notice_active and self._fulfilled_notice_job_code == job_code:
            return
        self._fulfilled_notice_active = True
        self._fulfilled_notice_job_code = job_code
        self.status.setText("Job quantity request fulfilled.")
        self._fulfilled_notice_timer.start(5000)

    def _clear_fulfilled_notice(self):
        self._fulfilled_notice_active = False
        if str(self.state.job_code or "").strip() != self._fulfilled_notice_job_code:
            return
        self._fulfilled_notice_job_code = ""
        self.status.setText("Ready: request fulfilled. You can still scan or finish the job.")

    def _parse_cycle_seconds(self, v: Any) -> Optional[float]:
        if v is None:
            return None
        raw = str(v).strip()
        if not raw:
            return None
        m = re.search(r"(\d+(?:\.\d+)?)", raw)
        if not m:
            return None
        try:
            out = float(m.group(1))
            return out if out > 0 else None
        except Exception:
            return None

    def _record_cycle_time_change(self, value: Any, source: str = "manual"):
        cycle_seconds = self._parse_cycle_seconds(value)
        if cycle_seconds is None:
            return
        s = self.state
        rows = list(s.cycle_time_change_logs or [])
        prev = rows[-1] if rows else {}
        prev_seconds = self._parse_cycle_seconds(prev.get("cycle_seconds") if isinstance(prev, dict) else None)
        if prev_seconds is not None and abs(prev_seconds - cycle_seconds) < 1e-9:
            return
        rows.append(
            {
                "set_at_utc": datetime.now(timezone.utc).isoformat(),
                "cycle_time": str(value).strip(),
                "cycle_seconds": cycle_seconds,
                "source": str(source or "manual").strip() or "manual",
            }
        )
        s.cycle_time_change_logs = rows[-200:]

    def _set_cycle_time_current(self, value: Any, source: str = "manual"):
        txt = str(value).strip() if value is not None else ""
        self.state.cycle_time_current = txt or None
        if txt:
            self._record_cycle_time_change(txt, source=source)

    def _parse_utc_iso_datetime(self, raw: Any) -> Optional[datetime]:
        txt = str(raw or "").strip()
        if not txt:
            return None
        try:
            return datetime.fromisoformat(txt.replace("Z", "+00:00"))
        except Exception:
            return None

    def _compute_current_shift_avg_cycle_seconds(self) -> Optional[float]:
        s = self.state
        shift_start_dt = self._parse_utc_iso_datetime(s.operator_shift_started_at)
        if shift_start_dt is None:
            return self._parse_cycle_seconds(s.cycle_time_current)

        cycle_values: List[float] = []
        baseline_cycle = self._parse_cycle_seconds(s.operator_shift_baseline_cycle_time)
        if baseline_cycle is not None:
            cycle_values.append(baseline_cycle)
        rows = [row for row in (s.cycle_time_change_logs or []) if isinstance(row, dict)]
        rows.sort(key=lambda row: str(row.get("set_at_utc") or ""))

        for row in rows:
            changed_at = self._parse_utc_iso_datetime(row.get("set_at_utc"))
            if changed_at is None or changed_at < shift_start_dt:
                continue
            row_cycle = self._parse_cycle_seconds(row.get("cycle_seconds"))
            if row_cycle is None:
                row_cycle = self._parse_cycle_seconds(row.get("cycle_time"))
            if row_cycle is not None:
                cycle_values.append(row_cycle)

        if cycle_values:
            return sum(cycle_values) / len(cycle_values)
        return self._parse_cycle_seconds(s.cycle_time_current)

    def _qty_per_shift_from_cycle(self, cycle_seconds: Optional[float], cavities: Any = 1) -> Optional[int]:
        if cycle_seconds is None or cycle_seconds <= 0:
            return None
        try:
            cavity_count = int(float(cavities or 1))
        except Exception:
            cavity_count = 1
        cavity_count = max(1, cavity_count)
        return int(((12 * 60 * 60) / cycle_seconds) * cavity_count)

    def _reset_live_cycle_tracking(self, *, start_now: bool = False):
        s = self.state
        s.live_cycle_last_scan_at = time.time() if start_now else None
        s.live_cycle_total_seconds = 0.0
        s.live_cycle_intervals = 0
        s.live_cycle_total_units = 0
        s.live_cycle_avg_seconds = None

    def _mark_live_cycle_scan_event(self, units: int = 1):
        s = self.state
        now_ts = time.time()
        prev_ts = s.live_cycle_last_scan_at
        qty_units = max(1, int(units or 1))
        if prev_ts is not None and now_ts > prev_ts:
            delta = now_ts - prev_ts
            s.live_cycle_total_seconds = float(s.live_cycle_total_seconds or 0.0) + float(delta)
            s.live_cycle_intervals = int(s.live_cycle_intervals or 0) + 1
            s.live_cycle_total_units = int(s.live_cycle_total_units or 0) + qty_units
            if s.live_cycle_total_units > 0:
                # Live cycle time is per unit (sec/unit), weighted by scanned quantity.
                s.live_cycle_avg_seconds = s.live_cycle_total_seconds / s.live_cycle_total_units
        s.live_cycle_last_scan_at = now_ts

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
        self.log_last(f"JobAPI: {str(msg or '').strip()}")

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

    def _job_api_body_is_unauthorized(self, data: Any) -> bool:
        if not isinstance(data, dict):
            return False
        code = str(data.get("code", "") or "").strip()
        message = str(data.get("message", "") or "").strip().lower()
        return code == "401" or message == "unauthorized"

    def _restore_job_payload_from_active_snapshot(self):
        s = self.state
        if not (s.machine_code and s.job_code):
            return
        payload = s.job_payload if isinstance(s.job_payload, dict) else {}
        data_obj = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        if isinstance(data_obj.get("job"), dict) or isinstance(payload.get("job"), dict):
            return
        snap = self._load_active_session_snapshot(str(s.machine_code))
        if not isinstance(snap, dict):
            return
        snap_job_code = self._normalize_job_code(snap.get("job_code"))
        if snap_job_code != self._normalize_job_code(s.job_code):
            return
        snap_payload = snap.get("job_payload")
        if not isinstance(snap_payload, dict):
            return
        snap_data = snap_payload.get("data") if isinstance(snap_payload.get("data"), dict) else {}
        if isinstance(snap_data.get("job"), dict) or isinstance(snap_payload.get("job"), dict):
            s.job_payload = snap_payload

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
                if self._job_api_body_is_unauthorized(data):
                    if user and password:
                        self._append_job_api_log("GET body unauthorized; refreshing bearer token")
                        print("[JobAPI] GET body unauthorized; refreshing bearer token")
                        token = self._get_job_api_bearer_token(base=base, user=user, password=password) or token
                        if attempt < max_attempts:
                            continue
                    self.status.setText("Job API bearer token unauthorized; using local job mapping/stub.")
                    self._append_job_api_log("GET FAIL: response body reported unauthorized bearer token")
                    return best_partial_wrapped
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
        s = self.state
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

        scanned_raw_qty = 0.0
        for row in (s.raw_material_logs or []):
            if not isinstance(row, dict):
                continue
            try:
                scanned_raw_qty += float(row.get("qty") or 0)
            except Exception:
                pass

        def _fmt_number(v: float) -> str:
            if abs(v - int(v)) < 1e-9:
                return str(int(v))
            return f"{v:.2f}".rstrip("0").rstrip(".")

        if hasattr(self, "jobPartsTable") and self.jobPartsTable is not None:
            self.jobPartsTable.setRowCount(0)
            for part in part_rows:
                r = self.jobPartsTable.rowCount()
                self.jobPartsTable.insertRow(r)
                request_part_qty = self._parse_number(part.get("request_part_qty"))
                part_qty_info = self._resolve_part_qty_per_unit(part)
                part_qty_per_unit = float(part_qty_info.get("value") or TEMP_PART_QTY_PER_UNIT)
                produced_units = max(0.0, float(s.good_total or 0) + float(s.butal_total or 0))
                projected_used_qty = max(0.0, produced_units * max(part_qty_per_unit, 0.0))
                used_raw_qty = min(scanned_raw_qty, projected_used_qty) if scanned_raw_qty > 0 else 0.0
                available_raw_qty = max(scanned_raw_qty - used_raw_qty, 0.0)
                remaining_part_qty = max(request_part_qty - used_raw_qty, 0.0)
                request_part_display = self._safe_text(part.get("request_part_qty"), "-")
                if request_part_qty > 0:
                    request_part_display = f"{_fmt_number(used_raw_qty)} / {request_part_display}"
                else:
                    request_part_display = _fmt_number(used_raw_qty)
                values = [
                    self._safe_text(part.get("sku"), "-"),
                    self._safe_text(part.get("name"), "-"),
                    f"{part_qty_per_unit:.4f}",
                    _fmt_number(available_raw_qty),
                    request_part_display,
                    _fmt_number(remaining_part_qty),
                ]
                for c, val in enumerate(values):
                    item = QTableWidgetItem(val)
                    if c in (2, 3, 4, 5):
                        item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
                    else:
                        item.setTextAlignment(int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
                    self.jobPartsTable.setItem(r, c, item)
            if self.jobPartsTable.rowCount() == 0:
                self.jobPartsTable.insertRow(0)
                for c in range(6):
                    item = QTableWidgetItem("-")
                    item.setTextAlignment(
                        int(Qt.AlignmentFlag.AlignCenter)
                        if c in (2, 3, 4, 5)
                        else int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    )
                    self.jobPartsTable.setItem(0, c, item)
            self._update_product_parts_weight_indicator()

        # Cycle monitor values are computed live in _refresh_ui from:
        # - Act cycle time entered/confirmed by operator
        # - Live cycle average based on production scan cadence

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

    def _compute_total_job_duration_seconds(self) -> int:
        s = self.state
        total_seconds = 0.0
        for row in (s.operator_shift_logs or []):
            if not isinstance(row, dict):
                continue
            started_raw = str(row.get("started_at_utc") or "").strip()
            ended_raw = str(row.get("ended_at_utc") or "").strip()
            if not started_raw or not ended_raw:
                continue
            try:
                started_dt = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
                ended_dt = datetime.fromisoformat(ended_raw.replace("Z", "+00:00"))
                total_seconds += max(0.0, (ended_dt - started_dt).total_seconds())
            except Exception:
                continue
        current_started_raw = str(s.operator_shift_started_at or "").strip()
        if current_started_raw:
            try:
                current_started_dt = datetime.fromisoformat(current_started_raw.replace("Z", "+00:00"))
                total_seconds += max(0.0, (datetime.now(timezone.utc) - current_started_dt).total_seconds())
            except Exception:
                pass
        return max(0, int(total_seconds))

    def _update_header_datetime(self):
        now_local = datetime.now()
        job_started_text = ""
        job_started_raw = str(self.state.job_started_at or "").strip()
        if job_started_raw:
            try:
                started_dt = datetime.fromisoformat(job_started_raw.replace("Z", "+00:00"))
                if started_dt.tzinfo is not None:
                    started_dt = started_dt.astimezone()
                job_started_text = f"Job Start: {started_dt.strftime('%b %d, %Y | %I:%M:%S %p')}"
            except Exception:
                job_started_text = f"Job Start: {job_started_raw}"
        self.headerJobStart.setText(job_started_text)
        self.headerJobStart.setVisible(bool(job_started_text))

        total_job_seconds = self._compute_total_job_duration_seconds()
        duration_text = ""
        if total_job_seconds > 0:
            hh = total_job_seconds // 3600
            mm = (total_job_seconds % 3600) // 60
            ss = total_job_seconds % 60
            duration_text = f"Job Duration: {hh:02d}:{mm:02d}:{ss:02d}"
        self.headerJobDuration.setText(duration_text)
        self.headerJobDuration.setVisible(bool(duration_text))
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
        s = str(raw).strip()
        pack_hist = self._extract_pack_history_fields(s)
        if isinstance(pack_hist, dict):
            po_digits = str(pack_hist.get("po_number") or "").strip()
            if po_digits:
                return po_digits.lstrip("0") or "0"

        # Fallback for labels that still carry the standard tail but include
        # extra text before or after the structured payload.
        m = re.search(r"I\d{11}T\d{11}L\d{14}-0*(\d+)", s)
        if m:
            return m.group(1).lstrip("0") or "0"

        # Last fallback for older labels ending directly with "-<job_code>".
        m = re.search(r"-0*(\d+)\s*$", s)
        if not m:
            return None
        return m.group(1).lstrip("0") or "0"

    def _extract_pack_history_fields(self, raw: str) -> Optional[Dict[str, str]]:
        s = str(raw).strip()
        if "V2" not in s or "QB" in s:
            return None
        m = re.search(r"P(\d{11})Q(\d{11})I(\d{11})T(\d{11})L(\d{14})-(\d+)", s)
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
            pack_meta = self._extract_pack_history_fields(raw)
            qty_text = str(int(res.qty or 0))
            idx_text = "-"
            product_id = ""
            if isinstance(pack_meta, dict):
                qty_text = str(pack_meta.get("qty_q") or qty_text)
                idx_text = str(pack_meta.get("index") or "-")
                product_id = str(pack_meta.get("product_p") or "").strip()
            norm_pid = product_id.lstrip("0") if product_id.isdigit() else product_id
            norm_pid = norm_pid or ""
            product_name = self._lookup_product_name(norm_pid) if norm_pid else ""
            if norm_pid and not product_name:
                if self._refresh_product_catalog_cache_from_api():
                    product_name = self._lookup_product_name(norm_pid)
            display_name = product_name or (f"Product {norm_pid}" if norm_pid else "Pack")
            return f"{display_name}  Q:{qty_text}  I:{idx_text}"
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
        t = str(text or "").strip()
        if not t:
            return
        stamp = time.strftime("%H:%M:%S")
        rows = list(getattr(self, "_action_logs", []) or [])
        rows.append(f"{stamp}  {t}")
        self._action_logs = rows[-20:]
        self._refresh_history_panel()

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
            self.log_last(short)
        else:
            self.status.setText(t)
            self.status.setToolTip("")
            self.log_last(t)

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
            and not s.waiting_production_report_reason
            and not s.waiting_downtime_start_maintenance
            and not s.waiting_downtime_end_maintenance
            and not s.waiting_cycle_time_input
            and not s.waiting_maintenance_qr
            and not s.waiting_supervisor_qr
            and not s.waiting_operator_downtime_confirm
            and not s.downtime_active
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
            pending_shift = dict(self._pending_shift_review_payload or {})
            if pending_shift:
                raw_s = str(raw).strip()
                reviewer = self._reviewer_from_scan(raw_s)
                if reviewer is not None and str(reviewer.get("can_supervisor", "0")) == "1":
                    self.status.setText("Supervisor QR accepted. Approving finished shift...")
                    self._approve_pending_shift_review(reviewer, raw_s)
                    return
                self.status.setText("Finished shift review is open. Scan Supervisor QR to approve.")
                self._show_invalid_overlay("Supervisor QR is required to approve this finished shift.")
                return
            self.status.setText("Operator shift handoff in progress. Please wait.")
            return
        if self._finish_anim_running:
            self.status.setText("Finish job in progress. Please wait.")
            return
        if self._supervisor_validation_pending:
            self.status.setText("Supervisor validation in progress. Please wait.")
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
                    self._set_cycle_time_current(s.cycle_time_new_input, source="supervisor_review")
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
                or s.waiting_downtime_start_maintenance
                or s.waiting_downtime_end_maintenance
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

        if self.finishOverlay.isVisible() and self.finishSummaryScroll.isVisible() and raw_l in ("next", "prev", "previous", "preview"):
            self._scroll_finish_shift_review(1 if raw_l == "next" else -1)
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
                self._set_cycle_time_current(s.cycle_time_new_input, source="initial_setup")
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
            s.raw_sacks_count += 1
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

        # PDR waiting step: scan maintenance to actually start downtime timer.
        if s.waiting_downtime_start_maintenance:
            auth = self._authorized_person_from_scan(raw_s)
            if auth and str(auth.get("can_maintenance", "0")) == "1":
                s.maintenance_name = str(auth.get("name") or raw_s)
                if s.downtime_wait_started_at:
                    s.downtime_wait_last_seconds = max(0, int(time.time() - s.downtime_wait_started_at))
                s.downtime_wait_started_at = None
                s.waiting_downtime_start_maintenance = False
                s.downtime_started_at = time.time()
                s.downtime_active = True
                s.waiting_downtime_end_maintenance = True
                self.status.setText('Maintenance acknowledged. Downtime timer started. Scan "pdr_done" when downtime is done.')
                self._refresh_ui()
                self._save_active_session_snapshot()
                return
            self.status.setText("Waiting mode: scan valid Maintenance QR to start downtime.")
            return

        # Downtime running step: wait for pdr_done to begin resolution flow.
        if s.waiting_downtime_end_maintenance and s.downtime_active and raw_l not in ("productiondailyreport~2", "pdr_done", "pdrdone"):
            self.status.setText('Downtime active: scan "pdr_done" when repair is completed.')
            return

        # Resolution step 1: Cycle time input via num_0..num_9, backspace, confirm
        if s.waiting_cycle_time_input:
            if raw_l.startswith("num_") and raw_l[-1:].isdigit():
                s.cycle_time_new_input += raw_l[-1]
                self._update_cycle_input_display()
                self._refresh_downtime_panel()
                return
            if raw_l == "backspace":
                s.cycle_time_new_input = s.cycle_time_new_input[:-1]
                self._update_cycle_input_display()
                self._refresh_downtime_panel()
                return
            if raw_l == "confirm":
                if not s.cycle_time_new_input:
                    self.status.setText("Cycle Time is empty. Scan digits first.")
                    return
                s.waiting_cycle_time_input = False
                s.supervisor_downtime_confirmation_started_at = time.time()
                s.waiting_supervisor_qr = True
                self._refresh_ui()
                self.resolveHint.setText("SCAN SUPERVISOR QR")
                self._show_resolve_overlay()
                return
            self.status.setText("Cycle Time input mode: scan num_0..num_9, backspace, confirm.")
            return

        # Resolution step 2: Supervisor
        if s.waiting_supervisor_qr:
            auth = self._authorized_person_from_scan(raw_s)
            if auth and str(auth.get("can_supervisor", "0")) == "1":
                s.supervisor_name = str(auth.get("name") or raw_s)
                s.cycle_time_confirmed_by = s.supervisor_name
                self._set_cycle_time_current(s.cycle_time_new_input, source="downtime_resolution")
                if s.supervisor_downtime_confirmation_started_at:
                    s.supervisor_downtime_confirmation_seconds = max(
                        0, int(time.time() - s.supervisor_downtime_confirmation_started_at)
                    )
                s.waiting_supervisor_qr = False
                s.waiting_maintenance_qr = True
                self.resolveNewCycle.setText(f"Confirmed by: {s.cycle_time_confirmed_by or ''}")
                self._supervisor_validation_pending = True
                self.status.setText("Supervisor QR logged. Validating...")
                QTimer.singleShot(1000, lambda name=s.supervisor_name: self._show_downtime_supervisor_saved_overlay(name))
                return
            scanned_name = str((auth or {}).get("name") or raw_s or "").strip()
            self.resolveNewCycle.setText(f"Confirmed by: {scanned_name}")
            self._supervisor_validation_failed_value = ""
            self._supervisor_validation_pending = True
            self.status.setText("Supervisor QR validation failed.")
            QTimer.singleShot(1000, lambda: self._show_downtime_supervisor_failed_overlay("This is not supervisor QR"))
            return

        # Resolution step 3: Maintenance stops downtime, then operator can proceed
        if s.waiting_maintenance_qr:
            auth = self._authorized_person_from_scan(raw_s)
            if auth and str(auth.get("can_maintenance", "0")) == "1":
                s.maintenance_name = str(auth.get("name") or raw_s)
                if s.downtime_started_at:
                    s.maintenance_downtime_seconds = max(0, int(time.time() - s.downtime_started_at))
                    s.downtime_last_seconds = s.maintenance_downtime_seconds
                s.downtime_started_at = None
                s.waiting_maintenance_qr = False
                s.operator_downtime_confirmation_started_at = time.time()
                s.waiting_operator_downtime_confirm = True
                self._refresh_ui()
                return
            self.status.setText("Scan valid Maintenance QR.")
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
                if s.operator_downtime_confirmation_started_at:
                    s.operator_downtime_confirmation_seconds = max(
                        0, int(time.time() - s.operator_downtime_confirmation_started_at)
                    )
                if s.maintenance_downtime_seconds is not None:
                    s.downtime_last_seconds = int(s.maintenance_downtime_seconds)
                s.downtime_started_at = None
                s.downtime_active = False
                s.waiting_downtime_end_maintenance = False
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
                        "waiting_seconds": int(s.downtime_wait_last_seconds or 0),
                        "downtime_seconds": int(s.downtime_last_seconds or 0),
                        "maintenance_downtime_seconds": int(s.maintenance_downtime_seconds or 0),
                        "supervisor_downtime_confirmation_seconds": int(s.supervisor_downtime_confirmation_seconds or 0),
                        "operator_downtime_confirmation_seconds": int(s.operator_downtime_confirmation_seconds or 0),
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

        # Downtime lock: keep scans constrained while downtime flow is active.
        if s.downtime_active and raw_l not in ("productiondailyreport~2", "pdr_done", "pdrdone", "sur"):
            self.status.setText("Downtime flow active: complete maintenance/cycle/supervisor/operator steps.")
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
            s.downtime_wait_started_at = time.time()
            s.downtime_wait_last_seconds = None
            s.waiting_downtime_start_maintenance = True
            s.waiting_downtime_end_maintenance = False
            s.downtime_started_at = None
            s.downtime_resolution_started_at = None
            s.downtime_active = False
            s.maintenance_downtime_seconds = None
            s.supervisor_downtime_confirmation_started_at = None
            s.supervisor_downtime_confirmation_seconds = None
            s.operator_downtime_confirmation_started_at = None
            s.operator_downtime_confirmation_seconds = None
            s.maintenance_name = None
            s.supervisor_name = None
            self._set_production_overlay_mode("active")
            self._show_production_overlay()
            self.status.setText(f"Production Daily Report reason set: {code} - {reason}. Waiting for maintenance scan.")
            self._refresh_ui()
            self.push_event(
                {"type": "PRODUCTION_DAILY_REPORT", "reason_code": code, "reason": reason, "mode": "WAITING_FOR_MAINTENANCE"},
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
                or s.waiting_downtime_start_maintenance
                or s.waiting_downtime_end_maintenance
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
            saved_shift_ok = self._save_finished_job_local(shift_payload)
            if not saved_shift_ok:
                self.status.setText("Finish shift save failed: active session kept for recovery.")
                self._show_invalid_overlay("Unable to save shift partial locally.")
                return
            self.push_event(
                {"type": "FINISH_SHIFT", "finished_job": shift_payload},
                f"FINISH SHIFT {shift_payload.get('job_name') or shift_payload.get('job_code') or ''}".strip(),
                silent=True,
            )
            self._show_operator_shift_overlay(shift_payload)
            self.status.setText("Finish shift saved. Waiting for Supervisor QR approval.")
            return

        if res.kind == "FINISH_JOB":
            if not self.can_accept_production_scans():
                self.status.setText("Cannot finish yet: complete MACHINE -> JOB -> OPERATOR first.")
                return
            if (
                s.waiting_reject_reason
                or s.waiting_production_report_reason
                or s.waiting_downtime_start_maintenance
                or s.waiting_downtime_end_maintenance
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
            if (
                s.waiting_reject_reason
                or s.waiting_production_report_reason
                or s.waiting_downtime_start_maintenance
                or s.waiting_downtime_end_maintenance
                or s.downtime_active
            ):
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
            if not s.waiting_downtime_end_maintenance:
                self.status.setText("Downtime resolution is already in progress.")
                return
            s.waiting_downtime_end_maintenance = False
            self._begin_downtime_resolution()
            self.status.setText("Downtime done. Scan Maintenance QR, then input cycle time, confirm, Supervisor QR, and Operator QR.")
            return

        if s.waiting_reject_reason:
            if res.kind == "REJECT_REASON":
                reason = res.value
                s.reject_total += 1
                s.reject_breakdown[reason] = s.reject_breakdown.get(reason, 0) + 1
                s.reject_review_logs.append(
                    {
                        "entry_type": "REJECT_SCAN",
                        "reason_code": reason,
                        "reason_text": REJECT_REASON_MAP.get(reason, reason),
                        "operator": str(s.operator_id or "").strip() or "-",
                        "operator_name": self._operator_display_name(s.operator_id),
                        "scanned_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                s.waiting_reject_reason = False
                self.status.setText(f"Reject recorded: {reason}")
                self.lblReject.add_points(1)
                self._refresh_ui()
                self._pulse_card(self.cardStatReject)
                self.push_event({"type": "REJECT", "qty": 1, "reason": reason}, f"REJECT {reason} +1")
                return
            if res.kind == "STARTUP_REJECT":
                s.startup_reject_total += 1
                s.reject_review_logs.append(
                    {
                        "entry_type": "STARTUP_REJECT_SCAN",
                        "reason_code": "SUR",
                        "reason_text": "Start Up Reject",
                        "operator": str(s.operator_id or "").strip() or "-",
                        "operator_name": self._operator_display_name(s.operator_id),
                        "scanned_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
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
            s.job_started_at = None
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
            s.downtime_wait_started_at = None
            s.downtime_wait_last_seconds = None
            s.waiting_downtime_start_maintenance = False
            s.waiting_downtime_end_maintenance = False
            s.downtime_resolution_started_at = None
            s.maintenance_downtime_seconds = None
            s.supervisor_downtime_confirmation_started_at = None
            s.supervisor_downtime_confirmation_seconds = None
            s.operator_downtime_confirmation_started_at = None
            s.operator_downtime_confirmation_seconds = None
            s.cycle_time_current = None
            s.cycle_time_change_logs = []
            s.cycle_time_confirmed_by = None
            s.waiting_initial_cycle_time_input = False
            s.waiting_initial_cycle_qc_confirm = False
            s.waiting_cycle_time_confirm_popup = False
            s.cycle_time_confirm_phase = 0
            s.cycle_time_confirm_actor_code = None
            s.cycle_time_confirm_actor_name = None
            s.cycle_time_confirm_actor_role = None
            self._reset_live_cycle_tracking(start_now=True)
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
            s.operator_shift_baseline_cycle_time = None
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
            self._clear_external_average_weight()
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
                api_job: Dict[str, Any] = {}
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
                else:
                    s.job_payload = {}
                    s.job_code = requested_job_id
                s.job_name = (
                    self._safe_text(api_job.get("ref_no"), "")
                    or res.value
                )
                self.status.setText(f"Job set (API): {s.job_name}")
            else:
                payload = res.meta or {}
                s.job_payload = payload if isinstance(payload, dict) else {}
                job = self._extract_job_record()
                s.job_code = (
                    self._safe_text(job.get("id"), "")
                    or self._safe_text(job.get("ref_no"), "")
                    or self._safe_text(s.job_payload.get("job_code"), "")
                    or res.value
                    or "QR-STUB"
                )
                s.job_name = (
                    self._safe_text(job.get("ref_no"), "")
                    or self._safe_text(s.job_payload.get("job_name"), "")
                    or res.value
                    or "Job Stub"
                )
            s.job_started_at = datetime.now(timezone.utc).isoformat()
            s.operator_id = None
            s.showing_reject_summary = False
            s.waiting_production_report_reason = False
            s.reject_summary_last_scanned_at = None
            s.downtime_reason_code = None
            s.downtime_reason_text = None
            s.downtime_started_at = None
            s.downtime_last_seconds = None
            s.downtime_active = False
            s.downtime_wait_started_at = None
            s.downtime_wait_last_seconds = None
            s.waiting_downtime_start_maintenance = False
            s.waiting_downtime_end_maintenance = False
            s.downtime_resolution_started_at = None
            s.maintenance_downtime_seconds = None
            s.supervisor_downtime_confirmation_started_at = None
            s.supervisor_downtime_confirmation_seconds = None
            s.operator_downtime_confirmation_started_at = None
            s.operator_downtime_confirmation_seconds = None
            s.cycle_time_current = None
            s.cycle_time_change_logs = []
            s.cycle_time_confirmed_by = None
            s.waiting_initial_cycle_time_input = False
            s.waiting_initial_cycle_qc_confirm = False
            s.waiting_cycle_time_confirm_popup = False
            s.cycle_time_confirm_phase = 0
            s.cycle_time_confirm_actor_code = None
            s.cycle_time_confirm_actor_name = None
            s.cycle_time_confirm_actor_role = None
            self._reset_live_cycle_tracking(start_now=True)
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
            s.operator_shift_baseline_cycle_time = None
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
            self._clear_external_average_weight()
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
            if res.kind == "JOB" and s.job_payload:
                self.sync_session_snapshot_to_server("SESSION SNAPSHOT SYNC (JOB API)")
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
                product_name_for_pack = ""
                product_sku_for_pack = ""
                if isinstance(pack_hist, dict):
                    pid_raw = str(pack_hist.get("product_p") or pack_hist.get("product_id") or "").strip()
                    pid = pid_raw.lstrip("0") if pid_raw.isdigit() else pid_raw
                    pid = pid or ""
                    if pid:
                        product_name_for_pack = self._lookup_product_name(pid)
                        product_sku_for_pack = self._lookup_product_sku(pid)
                        if (not product_name_for_pack or not product_sku_for_pack) and self._refresh_product_catalog_cache_from_api():
                            product_name_for_pack = self._lookup_product_name(pid)
                            product_sku_for_pack = self._lookup_product_sku(pid)
                is_rm_from_pack = bool(str(product_sku_for_pack).strip().upper().startswith("Z-RM"))
                if is_rm_from_pack:
                    material_name = str(product_name_for_pack or "Raw Material").strip() or "Raw Material"
                    unique_key = ""
                    if isinstance(pack_hist, dict):
                        scan_idx = str(pack_hist.get("index") or "").strip()
                        scan_lot = str(pack_hist.get("lot_number") or "").strip()
                        pid_raw = str(pack_hist.get("product_p") or "").strip()
                        if scan_idx and scan_lot:
                            unique_key = f"PACKRM:{pid_raw}:{scan_idx}:{scan_lot}"
                    if unique_key and unique_key in (s.raw_material_unique_keys or set()):
                        self.status.setText("Invalid RAW MATERIAL QR: duplicate serial already scanned.")
                        self._show_invalid_overlay("RAW MATERIAL QR serial already scanned.")
                        return
                    s.raw_sacks_count += 1
                    s.raw_material_scans.append(material_name)
                    log_row = {
                        "material_name": material_name,
                        "qty": qty,
                        "scanned_at": datetime.now(timezone.utc).isoformat(),
                        "source": "PACK_QR_ZRM",
                    }
                    if isinstance(pack_hist, dict):
                        log_row.update(
                            {
                                "index": str(pack_hist.get("index") or "-"),
                                "total_labels": str(pack_hist.get("total_labels") or "-"),
                                "lot_number": str(pack_hist.get("lot_number") or "-"),
                                "po_number": str(pack_hist.get("po_number") or "-"),
                            }
                        )
                    s.raw_material_logs.append(log_row)
                    if unique_key:
                        s.raw_material_unique_keys.add(unique_key)
                    self.status.setText(f"Raw material scanned: {material_name} (+{qty})")
                    self._refresh_ui()
                    self.push_event(
                        {"type": "RAW_MATERIAL", "qty": qty, "material": material_name, "source": "PACK_QR_ZRM"},
                        f"RAW MATERIAL {material_name} +{qty}",
                    )
                    return

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
                self._mark_live_cycle_scan_event(units=qty if qty > 0 else 1)
                self.status.setText(f"Pack +1 (Good +{qty})")
                self.lblPack.add_points(1)
                self.lblGood.add_points(qty)
                self.lblTotalGood.add_points(qty)
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
                self.lblButal.add_points(qty)
                self.lblTotalGood.add_points(qty)
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
