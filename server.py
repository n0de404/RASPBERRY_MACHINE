# server.py
from __future__ import annotations
import asyncio
import base64
import io
import json
import math
import os
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib import request as urllib_request
from urllib import error as urllib_error
from urllib.parse import quote, urlencode
import qrcode
from PIL import Image, ImageDraw, ImageFont

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

try:
    import pymysql
    from pymysql.cursors import DictCursor
except Exception:
    pymysql = None
    DictCursor = None

@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    global STATE_TICK_TASK
    if STATE_TICK_TASK is None or STATE_TICK_TASK.done():
        STATE_TICK_TASK = asyncio.create_task(_state_tick_loop())
    try:
        yield
    finally:
        if STATE_TICK_TASK is not None:
            STATE_TICK_TASK.cancel()
            try:
                await STATE_TICK_TASK
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            STATE_TICK_TASK = None


APP = FastAPI(title="Machine Dashboard Server", lifespan=_app_lifespan)
APP.mount("/Images", StaticFiles(directory=str(Path(__file__).resolve().parent / "Images")), name="images")

ACTIVE_TTL_SECONDS = 15  # allow several 5s client heartbeat intervals before marking disconnected
STATE_TICK_SECONDS = 0.25
PRODUCT_SOURCE_FILE = Path(__file__).resolve().parent / "Product_ID.json"  # legacy fallback
PRODUCT_API_CONFIG_FILE = Path(__file__).resolve().parent / "Database" / "product_api_config.json"
PRODUCT_CACHE_FILE = Path(__file__).resolve().parent / "Database" / "product_catalog_cache.json"
LOW_STOCK_CACHE_FILE = Path(__file__).resolve().parent / "Database" / "low_stock_recommendations.json"
ACTIVE_MACHINE_SESSIONS_FILE = Path(__file__).resolve().parent / "Database" / "active_machine_sessions.json"
PLANNING_BOARD_FILE = Path(__file__).resolve().parent / "Database" / "planning_board.json"
PROFILE_REPRINT_ADMIN_PASSWORD = "0t1docmtl$tm"
QRGEN_BASE_URL = os.environ.get("QRGEN_BASE_URL", "http://192.168.11.173:5000").strip().rstrip("/")
RAW_QR_O_SEGMENT = "O000000000240000010237800000000000"
RAW_QR_REMARK = "V2"
WIDTH_P = 11
WIDTH_Q = 11
WIDTH_I = 11
WIDTH_T = 11
WIDTH_L = 27
TOTAL_W_IN = 4.00
TOTAL_H_IN = 1.25
COLS = 3
TOP_BAR_IN = 0.22
MID_IN = 0.68
BOTTOM_IN = 0.35
MACHINE_NAME_MAP: Dict[str, str] = {
    "M00001": "IMM 301",
    "M00002": "IMM 302",
    "M00003": "IMM 303",
    "M00004": "IMM 304",
    "M00005": "IMM 305",
    "M00006": "IMM 306",
    "M00007": "IMM 307",
    "M00008": "IMM 308",
    "M00009": "IMM 309",
    "M00010": "IMM 310",
    "M00011": "IMM 311",
    "M00012": "IMM 312",
    "M00013": "IMM 313",
    "M00014": "IMM 314",
    "M00015": "IMM 315",
    "M00016": "IMM 316",
    "M00017": "IMM 317",
    "M00018": "IMM 318",
    "M00019": "IMM 319",
    "M00020": "IMM 320",
    "M00021": "IMM 321",
}
SUPERVISOR_BADGES: Dict[str, str] = {"3000001": "Charlie Brown"}
QC_BADGES: Dict[str, str] = {"4000001": "Lucy Van Pelt"}
APP_BASE_DIR = Path(__file__).resolve().parent
SQL_CONFIG_FILE = APP_BASE_DIR / "Database" / "sql_config.json"
FINISHED_JOBS_FALLBACK_FILE = APP_BASE_DIR / "Database" / "finished_jobs_server.json"
ARCHIVED_JOBS_FALLBACK_FILE = APP_BASE_DIR / "Database" / "archived_jobs_server.json"


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


def _sql_decode_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _load_json_object(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return {}


def _load_json_list(path: Path) -> List[Dict[str, Any]]:
    try:
        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
    except Exception as e:
        print(f"[JSON] Failed to load {path.name}: {e}")
    return []


def _save_json_list(path: Path, rows: List[Dict[str, Any]]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return True
    except Exception as e:
        print(f"[JSON] Failed to save {path.name}: {e}")
        return False


def _ensure_sql_schema() -> bool:
    conn = _sql_conn()
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
                CREATE TABLE IF NOT EXISTS `archived_jobs_server` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `record_type` VARCHAR(50) NULL,
                  `reason` VARCHAR(100) NULL,
                  `shift_index` INT NULL,
                  `started_at_utc` VARCHAR(50) NULL,
                  `ended_at_utc` VARCHAR(50) NULL,
                  `finished_at_utc` VARCHAR(50) NULL,
                  `client_id` VARCHAR(100) NULL,
                  `machine_code` VARCHAR(50) NULL,
                  `machine_name` VARCHAR(255) NULL,
                  `job_code` VARCHAR(100) NULL,
                  `job_name` VARCHAR(255) NULL,
                  `operator_id` VARCHAR(255) NULL,
                  `operator_name` VARCHAR(255) NULL,
                  `pack_count` INT NOT NULL DEFAULT 0,
                  `good_total` INT NOT NULL DEFAULT 0,
                  `butal_total` INT NOT NULL DEFAULT 0,
                  `reject_total` INT NOT NULL DEFAULT 0,
                  `total_good` INT NOT NULL DEFAULT 0,
                  `partial_qty` INT NOT NULL DEFAULT 0,
                  `startup_reject_total` INT NOT NULL DEFAULT 0,
                  `no_shot_total` INT NOT NULL DEFAULT 0,
                  `raw_sacks_count` INT NOT NULL DEFAULT 0,
                  `downtime_last_seconds` INT NULL,
                  `downtime_reason_code` VARCHAR(50) NULL,
                  `downtime_reason_text` TEXT NULL,
                  `cycle_time_current` VARCHAR(100) NULL,
                  `machine_counter_start` INT NULL,
                  `machine_counter_end` INT NULL,
                  `machine_counter_app_delta` INT NULL,
                  `machine_counter_app_end` INT NULL,
                  `machine_counter_difference` INT NULL,
                  `cycle_time_shift_avg_seconds` DOUBLE NULL,
                  `qty_per_shift_avg_cycle` INT NULL,
                  `maintenance_name` VARCHAR(255) NULL,
                  `supervisor_name` VARCHAR(255) NULL,
                  `approved_by` VARCHAR(255) NULL,
                  `approved_by_code` VARCHAR(100) NULL,
                  `approved_by_role` VARCHAR(100) NULL,
                  `changed_by` VARCHAR(255) NULL,
                  `changed_by_code` VARCHAR(100) NULL,
                  `changed_by_role` VARCHAR(100) NULL,
                  `approved_remarks` TEXT NULL,
                  `change_remarks` TEXT NULL,
                  `approved_at_utc` VARCHAR(50) NULL,
                  `changed_at_utc` VARCHAR(50) NULL,
                  `review_status` VARCHAR(100) NULL,
                  `linkage_enabled` TINYINT NOT NULL DEFAULT 0,
                  `linkage_job_code` VARCHAR(100) NULL,
                  `linkage_job_name` VARCHAR(255) NULL,
                  `linkage_role` VARCHAR(50) NULL,
                  `linkage_group_total_jobs` INT NULL,
                  `linkage_main_job_code` VARCHAR(100) NULL,
                  `linkage_main_job_name` VARCHAR(255) NULL,
                  `linkage_note` TEXT NULL,
                  `printed_at_utc` VARCHAR(50) NULL,
                  `archived_at_utc` VARCHAR(50) NULL,
                  `printed_qr_payload` LONGTEXT NULL,
                  `archive_status` VARCHAR(100) NULL,
                  `reject_breakdown` JSON NOT NULL,
                  `raw_material_scans` JSON NOT NULL,
                  `raw_material_logs` JSON NOT NULL,
                  `job_payload` JSON NOT NULL,
                  `reject_review_logs` JSON NOT NULL,
                  `review_history` JSON NULL,
                  `linkage_job_payload` JSON NULL,
                  `linkage_jobs` JSON NULL,
                  `linkage_mirror` JSON NULL,
                  `print_request_payload` JSON NULL,
                  `raw_json` JSON NOT NULL,
                  PRIMARY KEY (`id`),
                  KEY `idx_archived_jobs_server_machine_job` (`machine_code`, `job_code`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS `daily_role_assignments` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `assignment_date` DATE NOT NULL,
                  `badge_id` VARCHAR(100) NOT NULL,
                  `name` VARCHAR(255) NULL,
                  `rights` VARCHAR(50) NULL,
                  `company_role` VARCHAR(100) NULL,
                  `extra_privilege` VARCHAR(100) NULL,
                  `updated_at_utc` VARCHAR(50) NULL,
                  `raw_json` JSON NOT NULL,
                  PRIMARY KEY (`id`),
                  UNIQUE KEY `uq_daily_role_assignment` (`assignment_date`, `badge_id`),
                  KEY `idx_daily_role_assignment_date` (`assignment_date`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS `machine_status_overrides` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `machine_code` VARCHAR(50) NOT NULL,
                  `status` VARCHAR(100) NOT NULL,
                  `reason` TEXT NULL,
                  `updated_at_utc` VARCHAR(50) NULL,
                  `started_at_utc` VARCHAR(50) NULL,
                  `set_by_badge` VARCHAR(100) NULL,
                  `set_by_name` VARCHAR(255) NULL,
                  `set_by_role` VARCHAR(100) NULL,
                  `raw_json` JSON NOT NULL,
                  PRIMARY KEY (`id`),
                  UNIQUE KEY `uq_machine_status_overrides_machine_code` (`machine_code`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS `machine_status_archive` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `machine_code` VARCHAR(50) NOT NULL,
                  `machine_name` VARCHAR(255) NULL,
                  `status` VARCHAR(100) NOT NULL,
                  `reason` TEXT NULL,
                  `set_by_badge` VARCHAR(100) NULL,
                  `set_by_name` VARCHAR(255) NULL,
                  `set_by_role` VARCHAR(100) NULL,
                  `started_at_utc` VARCHAR(50) NULL,
                  `ended_at_utc` VARCHAR(50) NULL,
                  `duration_seconds` INT NULL,
                  `closed_by_badge` VARCHAR(100) NULL,
                  `closed_by_name` VARCHAR(255) NULL,
                  `closed_by_role` VARCHAR(100) NULL,
                  `closed_reason` TEXT NULL,
                  `closed_action` VARCHAR(100) NULL,
                  `raw_json` JSON NOT NULL,
                  PRIMARY KEY (`id`),
                  KEY `idx_machine_status_archive_machine_code` (`machine_code`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS `finished_jobs` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `record_type` VARCHAR(50) NULL,
                  `reason` VARCHAR(100) NULL,
                  `shift_index` INT NULL,
                  `started_at_utc` VARCHAR(50) NULL,
                  `ended_at_utc` VARCHAR(50) NULL,
                  `finished_at_utc` VARCHAR(50) NULL,
                  `client_id` VARCHAR(100) NULL,
                  `machine_code` VARCHAR(50) NULL,
                  `machine_name` VARCHAR(255) NULL,
                  `job_code` VARCHAR(100) NULL,
                  `job_name` VARCHAR(255) NULL,
                  `operator_id` VARCHAR(255) NULL,
                  `operator_name` VARCHAR(255) NULL,
                  `pack_count` INT NOT NULL DEFAULT 0,
                  `good_total` INT NOT NULL DEFAULT 0,
                  `butal_total` INT NOT NULL DEFAULT 0,
                  `reject_total` INT NOT NULL DEFAULT 0,
                  `total_good` INT NOT NULL DEFAULT 0,
                  `partial_qty` INT NOT NULL DEFAULT 0,
                  `startup_reject_total` INT NOT NULL DEFAULT 0,
                  `no_shot_total` INT NOT NULL DEFAULT 0,
                  `raw_sacks_count` INT NOT NULL DEFAULT 0,
                  `downtime_last_seconds` INT NULL,
                  `downtime_reason_code` VARCHAR(50) NULL,
                  `downtime_reason_text` TEXT NULL,
                  `cycle_time_current` VARCHAR(100) NULL,
                  `machine_counter_start` INT NULL,
                  `machine_counter_end` INT NULL,
                  `machine_counter_app_delta` INT NULL,
                  `machine_counter_app_end` INT NULL,
                  `machine_counter_difference` INT NULL,
                  `cycle_time_shift_avg_seconds` DOUBLE NULL,
                  `qty_per_shift_avg_cycle` INT NULL,
                  `maintenance_name` VARCHAR(255) NULL,
                  `supervisor_name` VARCHAR(255) NULL,
                  `approved_by` VARCHAR(255) NULL,
                  `approved_by_code` VARCHAR(100) NULL,
                  `approved_by_role` VARCHAR(100) NULL,
                  `changed_by` VARCHAR(255) NULL,
                  `changed_by_code` VARCHAR(100) NULL,
                  `changed_by_role` VARCHAR(100) NULL,
                  `approved_remarks` TEXT NULL,
                  `change_remarks` TEXT NULL,
                  `approved_at_utc` VARCHAR(50) NULL,
                  `changed_at_utc` VARCHAR(50) NULL,
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
                CREATE TABLE IF NOT EXISTS `pdr_reports` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT,
                  `client_id` VARCHAR(100) NULL,
                  `machine_code` VARCHAR(50) NULL,
                  `machine_name` VARCHAR(255) NULL,
                  `job_code` VARCHAR(100) NULL,
                  `job_name` VARCHAR(255) NULL,
                  `operator_id` VARCHAR(255) NULL,
                  `operator_reason_code` VARCHAR(50) NULL,
                  `operator_reason` TEXT NULL,
                  `reason_code` VARCHAR(50) NULL,
                  `reason` TEXT NULL,
                  `waiting_seconds` INT NULL,
                  `downtime_seconds` INT NULL,
                  `maintenance_downtime_seconds` INT NULL,
                  `cycle_time` VARCHAR(100) NULL,
                  `maintenance` VARCHAR(255) NULL,
                  `supervisor` VARCHAR(255) NULL,
                  `created_at_utc` VARCHAR(50) NULL,
                  `reason_segments` JSON NULL,
                  `raw_json` JSON NOT NULL,
                  PRIMARY KEY (`id`),
                  KEY `idx_pdr_reports_machine_code` (`machine_code`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            try:
                cur.execute("CREATE TABLE IF NOT EXISTS `finish_shift` LIKE `finished_jobs`")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE `archived_jobs_server` ADD COLUMN `no_shot_total` INT NOT NULL DEFAULT 0 AFTER `startup_reject_total`")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE `finished_jobs` ADD COLUMN `no_shot_total` INT NOT NULL DEFAULT 0 AFTER `startup_reject_total`")
            except Exception:
                pass
            for stmt in (
                "ALTER TABLE `archived_jobs_server` ADD COLUMN `machine_counter_start` INT NULL AFTER `cycle_time_current`",
                "ALTER TABLE `archived_jobs_server` ADD COLUMN `machine_counter_end` INT NULL AFTER `machine_counter_start`",
                "ALTER TABLE `archived_jobs_server` ADD COLUMN `machine_counter_app_delta` INT NULL AFTER `machine_counter_end`",
                "ALTER TABLE `archived_jobs_server` ADD COLUMN `machine_counter_app_end` INT NULL AFTER `machine_counter_app_delta`",
                "ALTER TABLE `archived_jobs_server` ADD COLUMN `machine_counter_difference` INT NULL AFTER `machine_counter_app_end`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `machine_counter_start` INT NULL AFTER `cycle_time_current`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `machine_counter_end` INT NULL AFTER `machine_counter_start`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `machine_counter_app_delta` INT NULL AFTER `machine_counter_end`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `machine_counter_app_end` INT NULL AFTER `machine_counter_app_delta`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `machine_counter_difference` INT NULL AFTER `machine_counter_app_end`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `record_type` VARCHAR(50) NULL AFTER `id`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `reason` VARCHAR(100) NULL AFTER `record_type`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `shift_index` INT NULL AFTER `reason`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `started_at_utc` VARCHAR(50) NULL AFTER `shift_index`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `ended_at_utc` VARCHAR(50) NULL AFTER `started_at_utc`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `partial_qty` INT NOT NULL DEFAULT 0 AFTER `total_good`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `cycle_time_shift_avg_seconds` DOUBLE NULL AFTER `machine_counter_difference`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `qty_per_shift_avg_cycle` INT NULL AFTER `cycle_time_shift_avg_seconds`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `approved_by` VARCHAR(255) NULL AFTER `supervisor_name`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `approved_by_code` VARCHAR(100) NULL AFTER `approved_by`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `approved_by_role` VARCHAR(100) NULL AFTER `approved_by_code`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `changed_by` VARCHAR(255) NULL AFTER `approved_by_role`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `changed_by_code` VARCHAR(100) NULL AFTER `changed_by`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `changed_by_role` VARCHAR(100) NULL AFTER `changed_by_code`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `approved_remarks` TEXT NULL AFTER `changed_by_role`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `change_remarks` TEXT NULL AFTER `approved_remarks`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `approved_at_utc` VARCHAR(50) NULL AFTER `change_remarks`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `changed_at_utc` VARCHAR(50) NULL AFTER `approved_at_utc`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `review_status` VARCHAR(100) NULL AFTER `changed_at_utc`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `linkage_enabled` TINYINT NOT NULL DEFAULT 0 AFTER `review_status`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `linkage_job_code` VARCHAR(100) NULL AFTER `linkage_enabled`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `linkage_job_name` VARCHAR(255) NULL AFTER `linkage_job_code`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `linkage_role` VARCHAR(50) NULL AFTER `linkage_job_name`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `linkage_group_total_jobs` INT NULL AFTER `linkage_role`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `linkage_main_job_code` VARCHAR(100) NULL AFTER `linkage_group_total_jobs`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `linkage_main_job_name` VARCHAR(255) NULL AFTER `linkage_main_job_code`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `linkage_note` TEXT NULL AFTER `linkage_main_job_name`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `linkage_job_payload` JSON NULL AFTER `reject_review_logs`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `linkage_jobs` JSON NULL AFTER `linkage_job_payload`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `linkage_mirror` JSON NULL AFTER `linkage_jobs`",
                "ALTER TABLE `finished_jobs` ADD COLUMN `review_history` JSON NULL AFTER `linkage_mirror`",
            ):
                try:
                    cur.execute(stmt)
                except Exception:
                    pass
                if "`finished_jobs`" in stmt:
                    try:
                        cur.execute(stmt.replace("`finished_jobs`", "`finish_shift`"))
                    except Exception:
                        pass
        conn.commit()
        return True
    except Exception as e:
        print(f"[SQL] Failed to ensure schema: {e}")
        return False
    finally:
        conn.close()


def _load_profiles_sql() -> Optional[List[Dict[str, Any]]]:
    conn = _sql_conn()
    if conn is None:
        return None
    try:
        items: List[Dict[str, Any]] = []
        with conn.cursor() as cur:
            cur.execute("SELECT `raw_json` FROM `user_qr_profiles` ORDER BY `id` ASC")
            for row in cur.fetchall() or []:
                item = _sql_decode_json((row or {}).get("raw_json"), {})
                if isinstance(item, dict):
                    items.append(item)
        return items
    except Exception:
        return None
    finally:
        conn.close()


def _load_machine_status_overrides_sql() -> Optional[Dict[str, Dict[str, Any]]]:
    conn = _sql_conn()
    if conn is None:
        return None
    try:
        out: Dict[str, Dict[str, Any]] = {}
        with conn.cursor() as cur:
            cur.execute("SELECT `machine_code`, `raw_json` FROM `machine_status_overrides` ORDER BY `machine_code` ASC")
            for row in cur.fetchall() or []:
                item = _sql_decode_json((row or {}).get("raw_json"), {})
                machine_code = str((row or {}).get("machine_code") or (item or {}).get("machine_code") or "").strip()
                if not machine_code or not isinstance(item, dict):
                    continue
                item = dict(item)
                item.pop("machine_code", None)
                out[machine_code] = item
        return out
    except Exception:
        return None
    finally:
        conn.close()


def _load_daily_role_assignments_sql() -> Optional[Dict[str, Any]]:
    conn = _sql_conn()
    if conn is None:
        return None
    try:
        out: Dict[str, Any] = {}
        with conn.cursor() as cur:
            cur.execute("SELECT `assignment_date`, `badge_id`, `raw_json` FROM `daily_role_assignments` ORDER BY `assignment_date` ASC, `badge_id` ASC")
            for row in cur.fetchall() or []:
                raw = _sql_decode_json((row or {}).get("raw_json"), {})
                if not isinstance(raw, dict):
                    raw = {}
                day = str((row or {}).get("assignment_date") or raw.get("assignment_date") or "").strip()
                badge = str((row or {}).get("badge_id") or raw.get("badge_id") or "").strip()
                if not day or not badge:
                    continue
                raw = dict(raw)
                raw.pop("assignment_date", None)
                raw.pop("badge_id", None)
                out.setdefault(day, {})
                out[day][badge] = raw
        return out
    except Exception:
        return None
    finally:
        conn.close()


def _load_archived_jobs_sql() -> Optional[List[Dict[str, Any]]]:
    conn = _sql_conn()
    if conn is None:
        return None
    try:
        items: List[Dict[str, Any]] = []
        with conn.cursor() as cur:
            cur.execute("SELECT `raw_json` FROM `archived_jobs_server` ORDER BY `id` ASC")
            for row in cur.fetchall() or []:
                item = _sql_decode_json((row or {}).get("raw_json"), {})
                if isinstance(item, dict):
                    items.append(item)
        return items
    except Exception:
        return None
    finally:
        conn.close()


def _save_archived_jobs_sql(rows: List[Dict[str, Any]]) -> bool:
    conn = _sql_conn()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM `archived_jobs_server`")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cur.execute(
                    """
                    INSERT INTO `archived_jobs_server`
                    (`finished_at_utc`,`client_id`,`machine_code`,`machine_name`,`job_code`,`job_name`,`operator_id`,
                     `pack_count`,`good_total`,`butal_total`,`reject_total`,`total_good`,`startup_reject_total`,`no_shot_total`,`raw_sacks_count`,
                     `downtime_last_seconds`,`downtime_reason_code`,`downtime_reason_text`,`cycle_time_current`,
                     `machine_counter_start`,`machine_counter_end`,`machine_counter_app_delta`,`machine_counter_app_end`,`machine_counter_difference`,
                     `maintenance_name`,`supervisor_name`,
                     `approved_by`,`approved_by_code`,`approved_by_role`,`approved_remarks`,`approved_at_utc`,`review_status`,
                     `printed_at_utc`,`archived_at_utc`,`printed_qr_payload`,`archive_status`,
                     `reject_breakdown`,`raw_material_scans`,`raw_material_logs`,`job_payload`,`reject_review_logs`,
                     `review_history`,`print_request_payload`,`raw_json`)
                    VALUES
                    (%s,%s,%s,%s,%s,%s,%s,
                     %s,%s,%s,%s,%s,%s,%s,%s,
                     %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                     %s,%s,%s,%s,%s,%s,
                     %s,%s,%s,%s,
                     CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),
                     CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON))
                    """,
                    (
                        row.get("finished_at_utc"), row.get("client_id"), row.get("machine_code"), row.get("machine_name"), row.get("job_code"), row.get("job_name"), row.get("operator_id"),
                        int(row.get("pack_count", 0) or 0), int(row.get("good_total", 0) or 0), int(row.get("butal_total", 0) or 0), int(row.get("reject_total", 0) or 0), int(row.get("total_good", 0) or 0), int(row.get("startup_reject_total", 0) or 0), int(row.get("no_shot_total", 0) or 0), int(row.get("raw_sacks_count", 0) or 0),
                        row.get("downtime_last_seconds"), row.get("downtime_reason_code"), row.get("downtime_reason_text"), row.get("cycle_time_current"),
                        row.get("machine_counter_start"), row.get("machine_counter_end"), row.get("machine_counter_app_delta"), row.get("machine_counter_app_end"), row.get("machine_counter_difference"),
                        row.get("maintenance_name"), row.get("supervisor_name"),
                        row.get("approved_by"), row.get("approved_by_code"), row.get("approved_by_role"), row.get("approved_remarks"), row.get("approved_at_utc"), row.get("review_status"),
                        row.get("printed_at_utc"), row.get("archived_at_utc"), row.get("printed_qr_payload"), row.get("archive_status"),
                        json.dumps(row.get("reject_breakdown", {}), ensure_ascii=False), json.dumps(row.get("raw_material_scans", []), ensure_ascii=False), json.dumps(row.get("raw_material_logs", []), ensure_ascii=False), json.dumps(row.get("job_payload", {}), ensure_ascii=False), json.dumps(row.get("reject_review_logs", []), ensure_ascii=False),
                        json.dumps(row.get("review_history"), ensure_ascii=False), json.dumps(row.get("print_request_payload"), ensure_ascii=False), json.dumps(row, ensure_ascii=False),
                    ),
                )
        conn.commit()
        return True
    except Exception as e:
        print(f"[SQL] Failed to save archived_jobs_server: {e}")
        return False
    finally:
        conn.close()


def _save_daily_role_assignments_sql(rows: Dict[str, Any]) -> bool:
    conn = _sql_conn()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM `daily_role_assignments`")
            for day, bucket in (rows or {}).items():
                if not isinstance(bucket, dict):
                    continue
                for badge, row in bucket.items():
                    if not isinstance(row, dict):
                        continue
                    raw_row = {"assignment_date": day, "badge_id": badge, **row}
                    cur.execute(
                        """
                        INSERT INTO `daily_role_assignments`
                        (`assignment_date`,`badge_id`,`name`,`rights`,`company_role`,`extra_privilege`,`updated_at_utc`,`raw_json`)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,CAST(%s AS JSON))
                        """,
                        (
                            day,
                            badge,
                            row.get("name"),
                            row.get("rights"),
                            row.get("company_role"),
                            row.get("extra_privilege"),
                            row.get("updated_at_utc"),
                            json.dumps(raw_row, ensure_ascii=False),
                        ),
                    )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def _save_machine_status_overrides_sql(rows: Dict[str, Dict[str, Any]]) -> bool:
    conn = _sql_conn()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM `machine_status_overrides`")
            for machine_code, row in (rows or {}).items():
                if not isinstance(row, dict):
                    continue
                raw_row = {"machine_code": machine_code, **row}
                cur.execute(
                    """
                    INSERT INTO `machine_status_overrides`
                    (`machine_code`,`status`,`reason`,`updated_at_utc`,`started_at_utc`,`set_by_badge`,`set_by_name`,`set_by_role`,`raw_json`)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,CAST(%s AS JSON))
                    """,
                    (
                        machine_code,
                        row.get("status"),
                        row.get("reason"),
                        row.get("updated_at_utc"),
                        row.get("started_at_utc"),
                        row.get("set_by_badge"),
                        row.get("set_by_name"),
                        row.get("set_by_role"),
                        json.dumps(raw_row, ensure_ascii=False),
                    ),
                )
        conn.commit()
        return True
    except Exception:
        return False
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
        return False
    finally:
        conn.close()


def _load_server_settings_sql() -> Optional[Dict[str, Any]]:
    conn = _sql_conn()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT `raw_json` FROM `server_settings` ORDER BY `id` DESC LIMIT 1")
            row = cur.fetchone()
        raw = _sql_decode_json((row or {}).get("raw_json"), {})
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None
    finally:
        conn.close()


def _save_server_settings_sql(row: Dict[str, Any]) -> bool:
    conn = _sql_conn()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM `server_settings`")
            cur.execute(
                "INSERT INTO `server_settings` (`theme`, `qrgen_base_url`, `raw_json`) VALUES (%s, %s, CAST(%s AS JSON))",
                (row.get("theme"), row.get("qrgen_base_url"), json.dumps(row, ensure_ascii=False)),
            )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def _load_finished_jobs_sql() -> Optional[List[Dict[str, Any]]]:
    conn = _sql_conn()
    if conn is None:
        return None
    try:
        items: List[Dict[str, Any]] = []
        with conn.cursor() as cur:
            for table_name in ("finished_jobs", "finish_shift"):
                try:
                    cur.execute(f"SELECT `raw_json` FROM `{table_name}` ORDER BY `id` ASC")
                except Exception:
                    continue
                for row in cur.fetchall() or []:
                    item = _sql_decode_json((row or {}).get("raw_json"), {})
                    if isinstance(item, dict):
                        items.append(item)
        return items
    except Exception:
        return None
    finally:
        conn.close()


def _load_machine_status_archive_sql() -> Optional[List[Dict[str, Any]]]:
    conn = _sql_conn()
    if conn is None:
        return None
    try:
        items: List[Dict[str, Any]] = []
        with conn.cursor() as cur:
            cur.execute("SELECT `raw_json` FROM `machine_status_archive` ORDER BY `id` ASC")
            for row in cur.fetchall() or []:
                item = _sql_decode_json((row or {}).get("raw_json"), {})
                if isinstance(item, dict):
                    items.append(item)
        return items
    except Exception:
        return None
    finally:
        conn.close()


def _save_machine_status_archive_sql(rows: List[Dict[str, Any]]) -> bool:
    conn = _sql_conn()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM `machine_status_archive`")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cur.execute(
                    """
                    INSERT INTO `machine_status_archive`
                    (`machine_code`,`machine_name`,`status`,`reason`,`set_by_badge`,`set_by_name`,`set_by_role`,
                     `started_at_utc`,`ended_at_utc`,`duration_seconds`,`closed_by_badge`,`closed_by_name`,
                     `closed_by_role`,`closed_reason`,`closed_action`,`raw_json`)
                    VALUES
                    (%s,%s,%s,%s,%s,%s,%s,
                     %s,%s,%s,%s,%s,
                     %s,%s,%s,CAST(%s AS JSON))
                    """,
                    (
                        row.get("machine_code"),
                        row.get("machine_name"),
                        row.get("status"),
                        row.get("reason"),
                        row.get("set_by_badge"),
                        row.get("set_by_name"),
                        row.get("set_by_role"),
                        row.get("started_at_utc"),
                        row.get("ended_at_utc"),
                        row.get("duration_seconds"),
                        row.get("closed_by_badge"),
                        row.get("closed_by_name"),
                        row.get("closed_by_role"),
                        row.get("closed_reason"),
                        row.get("closed_action"),
                        json.dumps(row, ensure_ascii=False),
                    ),
                )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def _save_finished_jobs_sql(rows: List[Dict[str, Any]]) -> bool:
    conn = _sql_conn()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM `finished_jobs`")
            try:
                cur.execute("DELETE FROM `finish_shift`")
            except Exception:
                pass
            for row in rows:
                if not isinstance(row, dict):
                    continue
                table_name = "finish_shift" if str(row.get("record_type") or "").strip().upper() == "SHIFT_PARTIAL" else "finished_jobs"
                cur.execute(
                    f"""
                    INSERT INTO `{table_name}`
                    (`record_type`,`reason`,`shift_index`,`started_at_utc`,`ended_at_utc`,`finished_at_utc`,
                     `client_id`,`machine_code`,`machine_name`,`job_code`,`job_name`,`operator_id`,
                     `pack_count`,`good_total`,`butal_total`,`reject_total`,`total_good`,`partial_qty`,`startup_reject_total`,`no_shot_total`,`raw_sacks_count`,
                     `downtime_last_seconds`,`downtime_reason_code`,`downtime_reason_text`,`cycle_time_current`,
                     `machine_counter_start`,`machine_counter_end`,`machine_counter_app_delta`,`machine_counter_app_end`,`machine_counter_difference`,
                     `cycle_time_shift_avg_seconds`,`qty_per_shift_avg_cycle`,`maintenance_name`,`supervisor_name`,
                     `approved_by`,`approved_by_code`,`approved_by_role`,`changed_by`,`changed_by_code`,`changed_by_role`,
                     `approved_remarks`,`change_remarks`,`approved_at_utc`,`changed_at_utc`,`review_status`,
                     `linkage_enabled`,`linkage_job_code`,`linkage_job_name`,`linkage_role`,`linkage_group_total_jobs`,
                     `linkage_main_job_code`,`linkage_main_job_name`,`linkage_note`,
                     `reject_breakdown`,`raw_material_scans`,`raw_material_logs`,`job_payload`,`reject_review_logs`,
                     `linkage_job_payload`,`linkage_jobs`,`linkage_mirror`,`review_history`,`raw_json`)
                    VALUES
                    (%s,%s,%s,%s,%s,%s,
                     %s,%s,%s,%s,%s,%s,
                     %s,%s,%s,%s,%s,%s,%s,%s,%s,
                     %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                     %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                     %s,%s,%s,%s,%s,
                     %s,%s,%s,
                     CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),
                     CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON))
                    """,
                    (
                        row.get("record_type"), row.get("reason"), row.get("shift_index"), row.get("started_at_utc"), row.get("ended_at_utc"), row.get("finished_at_utc"),
                        row.get("client_id"), row.get("machine_code"), row.get("machine_name"), row.get("job_code"), row.get("job_name"), row.get("operator_id"),
                        int(row.get("pack_count", 0) or 0), int(row.get("good_total", 0) or 0), int(row.get("butal_total", 0) or 0), int(row.get("reject_total", 0) or 0), int(row.get("total_good", 0) or 0), int(row.get("partial_qty", 0) or 0), int(row.get("startup_reject_total", 0) or 0), int(row.get("no_shot_total", 0) or 0), int(row.get("raw_sacks_count", 0) or 0),
                        row.get("downtime_last_seconds"), row.get("downtime_reason_code"), row.get("downtime_reason_text"), row.get("cycle_time_current"),
                        row.get("machine_counter_start"), row.get("machine_counter_end"), row.get("machine_counter_app_delta"), row.get("machine_counter_app_end"), row.get("machine_counter_difference"),
                        row.get("cycle_time_shift_avg_seconds"), row.get("qty_per_shift_avg_cycle"), row.get("maintenance_name"), row.get("supervisor_name"),
                        row.get("approved_by"), row.get("approved_by_code"), row.get("approved_by_role"), row.get("changed_by"), row.get("changed_by_code"), row.get("changed_by_role"),
                        row.get("approved_remarks"), row.get("change_remarks"), row.get("approved_at_utc"), row.get("changed_at_utc"), row.get("review_status"),
                        1 if row.get("linkage_enabled") else 0, row.get("linkage_job_code"), row.get("linkage_job_name"), row.get("linkage_role"), row.get("linkage_group_total_jobs"),
                        row.get("linkage_main_job_code"), row.get("linkage_main_job_name"), row.get("linkage_note"),
                        json.dumps(row.get("reject_breakdown", {}), ensure_ascii=False), json.dumps(row.get("raw_material_scans", []), ensure_ascii=False), json.dumps(row.get("raw_material_logs", []), ensure_ascii=False), json.dumps(row.get("job_payload", {}), ensure_ascii=False), json.dumps(row.get("reject_review_logs", []), ensure_ascii=False),
                        json.dumps(row.get("linkage_job_payload"), ensure_ascii=False), json.dumps(row.get("linkage_jobs"), ensure_ascii=False), json.dumps(row.get("linkage_mirror"), ensure_ascii=False), json.dumps(row.get("review_history"), ensure_ascii=False), json.dumps(row, ensure_ascii=False),
                    ),
                )
        conn.commit()
        return True
    except Exception as e:
        print(f"[SQL] Failed to save finished_jobs: {e}")
        return False
    finally:
        conn.close()


def _insert_pdr_report_sql(row: Dict[str, Any]) -> bool:
    conn = _sql_conn()
    if conn is None:
        return False
    try:
        raw = dict(row or {})
        raw.setdefault("created_at_utc", utc_now().isoformat())
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO `pdr_reports`
                (`client_id`,`machine_code`,`machine_name`,`job_code`,`job_name`,`operator_id`,
                 `operator_reason_code`,`operator_reason`,`reason_code`,`reason`,
                 `waiting_seconds`,`downtime_seconds`,`maintenance_downtime_seconds`,`cycle_time`,
                 `maintenance`,`supervisor`,`created_at_utc`,`reason_segments`,`raw_json`)
                VALUES
                (%s,%s,%s,%s,%s,%s,
                 %s,%s,%s,%s,
                 %s,%s,%s,%s,
                 %s,%s,%s,CAST(%s AS JSON),CAST(%s AS JSON))
                """,
                (
                    raw.get("client_id"), raw.get("machine_code"), raw.get("machine_name"), raw.get("job_code"), raw.get("job_name"), raw.get("operator_id"),
                    raw.get("operator_reason_code"), raw.get("operator_reason"), raw.get("reason_code"), raw.get("reason"),
                    raw.get("waiting_seconds"), raw.get("downtime_seconds"), raw.get("maintenance_downtime_seconds"), raw.get("cycle_time"),
                    raw.get("maintenance"), raw.get("supervisor"), raw.get("created_at_utc"),
                    json.dumps(raw.get("reason_segments", []), ensure_ascii=False), json.dumps(raw, ensure_ascii=False),
                ),
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"[SQL] Failed to save pdr_reports: {e}")
        return False
    finally:
        conn.close()


def _app_relative_path_str(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(APP_BASE_DIR)).replace("\\", "/")
    except Exception:
        return path.name


def _machine_display_name(machine_code: str, machine_name: Any = "") -> str:
    code = str(machine_code or "").strip()
    if code in MACHINE_NAME_MAP:
        return MACHINE_NAME_MAP[code]
    name = str(machine_name or "").strip()
    return name or code


@dataclass
class MachineSession:
    client_id: str
    machine_code: str
    machine_name: str
    job_code: Optional[str] = None
    job_name: Optional[str] = None
    job_started_at: Optional[str] = None
    operator_id: Optional[str] = None
    pack_total: int = 0
    good_total: int = 0
    butal_total: int = 0
    reject_total: int = 0
    reject_breakdown: Dict[str, int] = None
    no_shot_total: int = 0
    raw_sacks_count: int = 0
    raw_material_scans: List[str] = None
    raw_material_logs: List[Dict[str, Any]] = None
    startup_reject_total: int = 0
    downtime_reason_code: Optional[str] = None
    downtime_reason_text: Optional[str] = None
    downtime_started_at: Optional[float] = None
    downtime_last_seconds: Optional[int] = None
    downtime_active: bool = False
    pdr_operator_reason_code: Optional[str] = None
    pdr_operator_reason_text: Optional[str] = None
    downtime_wait_started_at: Optional[float] = None
    downtime_wait_last_seconds: Optional[int] = None
    waiting_downtime_start_maintenance: bool = False
    waiting_pdr_maintenance_reason: bool = False
    waiting_downtime_end_maintenance: bool = False
    waiting_maintenance_qr: bool = False
    waiting_supervisor_qr: bool = False
    supervisor_downtime_confirmation_started_at: Optional[Any] = None
    cycle_time_new_input: Optional[str] = None
    cycle_time_current: Optional[str] = None
    live_cycle_avg_seconds: Optional[float] = None
    maintenance_name: Optional[str] = None
    supervisor_name: Optional[str] = None
    job_payload: Dict[str, Any] = None
    linkage_enabled: bool = False
    linkage_jobs: List[Dict[str, Any]] = None
    operator_shift_logs: List[Dict[str, Any]] = None
    butal_by_job: Dict[str, int] = None
    last_shift_butal_qty: int = 0
    last_shift_butal_raw: str = ""
    last_shift_butal_saved_at: Optional[str] = None
    last_shift_butal_job_code: Optional[str] = None
    last_shift_butal_job_name: Optional[str] = None
    last_shift_butal_by_job: Dict[str, Dict[str, Any]] = None
    last_event: str = ""
    last_seen_utc: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["reject_breakdown"] = d["reject_breakdown"] or {}
        d["raw_material_scans"] = d["raw_material_scans"] or []
        d["raw_material_logs"] = d["raw_material_logs"] or []
        d["job_payload"] = d["job_payload"] or {}
        d["linkage_jobs"] = d["linkage_jobs"] or []
        d["operator_shift_logs"] = d["operator_shift_logs"] or []
        d["butal_by_job"] = d["butal_by_job"] or {}
        d["last_shift_butal_by_job"] = d["last_shift_butal_by_job"] or {}
        return d


def _session_from_active_snapshot(raw: Dict[str, Any]) -> Optional[MachineSession]:
    if not isinstance(raw, dict):
        return None
    machine_code = str(raw.get("machine_code") or "").strip()
    if not machine_code:
        return None
    last_seen_utc = str(raw.get("last_seen_utc") or raw.get("saved_at_utc") or "").strip()
    return MachineSession(
        client_id=str(raw.get("client_id") or "SNAPSHOT").strip() or "SNAPSHOT",
        machine_code=machine_code,
        machine_name=_machine_display_name(machine_code, raw.get("machine_name", machine_code)),
        job_code=str(raw.get("job_code") or "").strip() or None,
        job_name=str(raw.get("job_name") or "").strip() or None,
        job_started_at=str(raw.get("job_started_at") or "").strip() or None,
        operator_id=str(raw.get("operator_id") or "").strip() or None,
        pack_total=int(raw.get("pack_total", raw.get("pack_count", 0)) or 0),
        good_total=int(raw.get("good_total", 0) or 0),
        butal_total=int(raw.get("butal_total", 0) or 0),
        reject_total=int(raw.get("reject_total", 0) or 0),
        reject_breakdown=dict(raw.get("reject_breakdown") or {}),
        no_shot_total=int(raw.get("no_shot_total", 0) or 0),
        raw_sacks_count=int(raw.get("raw_sacks_count", 0) or 0),
        raw_material_scans=list(raw.get("raw_material_scans") or []),
        raw_material_logs=list(raw.get("raw_material_logs") or []),
        startup_reject_total=int(raw.get("startup_reject_total", 0) or 0),
        downtime_reason_code=raw.get("downtime_reason_code"),
        downtime_reason_text=raw.get("downtime_reason_text"),
        downtime_started_at=raw.get("downtime_started_at"),
        downtime_last_seconds=raw.get("downtime_last_seconds"),
        downtime_active=bool(raw.get("downtime_active", False)),
        pdr_operator_reason_code=raw.get("pdr_operator_reason_code"),
        pdr_operator_reason_text=raw.get("pdr_operator_reason_text"),
        downtime_wait_started_at=raw.get("downtime_wait_started_at"),
        downtime_wait_last_seconds=raw.get("downtime_wait_last_seconds"),
        waiting_downtime_start_maintenance=bool(raw.get("waiting_downtime_start_maintenance", False)),
        waiting_pdr_maintenance_reason=bool(raw.get("waiting_pdr_maintenance_reason", False)),
        waiting_downtime_end_maintenance=bool(raw.get("waiting_downtime_end_maintenance", False)),
        waiting_maintenance_qr=bool(raw.get("waiting_maintenance_qr", False)),
        waiting_supervisor_qr=bool(raw.get("waiting_supervisor_qr", False)),
        supervisor_downtime_confirmation_started_at=raw.get("supervisor_downtime_confirmation_started_at"),
        cycle_time_new_input=raw.get("cycle_time_new_input"),
        cycle_time_current=raw.get("cycle_time_current"),
        live_cycle_avg_seconds=raw.get("live_cycle_avg_seconds"),
        maintenance_name=raw.get("maintenance_name"),
        supervisor_name=raw.get("supervisor_name"),
        job_payload=dict(raw.get("job_payload") or {}),
        linkage_enabled=bool(raw.get("linkage_enabled", False)),
        linkage_jobs=list(raw.get("linkage_jobs") or []),
        operator_shift_logs=list(raw.get("operator_shift_logs") or []),
        butal_by_job={str(k): int(v or 0) for k, v in dict(raw.get("butal_by_job") or {}).items()},
        last_shift_butal_qty=int(raw.get("last_shift_butal_qty", 0) or 0),
        last_shift_butal_raw=str(raw.get("last_shift_butal_raw") or ""),
        last_shift_butal_saved_at=raw.get("last_shift_butal_saved_at"),
        last_shift_butal_job_code=raw.get("last_shift_butal_job_code"),
        last_shift_butal_job_name=raw.get("last_shift_butal_job_name"),
        last_shift_butal_by_job=dict(raw.get("last_shift_butal_by_job") or {}),
        last_event=str(raw.get("last_event") or "Recovered from active session snapshot").strip(),
        last_seen_utc=last_seen_utc,
    )


def load_active_sessions_seed() -> Dict[str, MachineSession]:
    try:
        if not ACTIVE_MACHINE_SESSIONS_FILE.exists():
            return {}
        raw = json.loads(ACTIVE_MACHINE_SESSIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, MachineSession] = {}
    for machine_code, row in raw.items():
        item = dict(row or {}) if isinstance(row, dict) else {}
        if "machine_code" not in item:
            item["machine_code"] = machine_code
        sess = _session_from_active_snapshot(item)
        if sess is not None:
            out[sess.machine_code] = sess
    return out


def _save_active_sessions_json(rows: Dict[str, MachineSession]) -> bool:
    try:
        payload: Dict[str, Any] = {}
        for machine_code, sess in (rows or {}).items():
            if isinstance(sess, MachineSession):
                payload[str(machine_code or sess.machine_code).strip()] = sess.to_dict()
        ACTIVE_MACHINE_SESSIONS_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except Exception:
        return False


def _upsert_active_session_sql(row: Dict[str, Any]) -> bool:
    conn = _sql_conn()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO `active_machine_sessions` (`machine_code`, `saved_at_utc`, `raw_json`)
                VALUES (%s, %s, CAST(%s AS JSON))
                ON DUPLICATE KEY UPDATE
                  `saved_at_utc`=VALUES(`saved_at_utc`),
                  `raw_json`=VALUES(`raw_json`)
                """,
                (
                    str(row.get("machine_code") or "").strip(),
                    row.get("saved_at_utc") or utc_now().isoformat(),
                    json.dumps(row, ensure_ascii=False),
                ),
            )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def _delete_active_session_sql(machine_code: str) -> bool:
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


def _persist_active_sessions_state() -> None:
    _save_active_sessions_json(SESSIONS)
    for sess in SESSIONS.values():
        _upsert_active_session_sql(sess.to_dict())


def _remove_persisted_active_session(machine_code: str) -> None:
    _delete_active_session_sql(machine_code)
    _save_active_sessions_json(SESSIONS)


SESSIONS: Dict[str, MachineSession] = load_active_sessions_seed()  # key = machine_code
WS_CLIENTS: List[WebSocket] = []
STATE_TICK_TASK: Optional[asyncio.Task] = None
MACHINE_STATUS_OVERRIDES: Dict[str, Dict[str, Any]] = {}
MACHINE_STATUS_ARCHIVE: List[Dict[str, Any]] = []
ACTIVE_SESSIONS_FILE_MTIME: Optional[float] = None


def refresh_active_sessions_from_file() -> None:
    global ACTIVE_SESSIONS_FILE_MTIME
    try:
        stat = ACTIVE_MACHINE_SESSIONS_FILE.stat()
    except Exception:
        return
    mtime = float(stat.st_mtime or 0)
    if ACTIVE_SESSIONS_FILE_MTIME == mtime:
        return
    ACTIVE_SESSIONS_FILE_MTIME = mtime
    for code, sess in load_active_sessions_seed().items():
        if not code:
            continue
        SESSIONS[code] = sess


def load_machine_status_overrides() -> Dict[str, Dict[str, Any]]:
    rows = _load_machine_status_overrides_sql()
    if isinstance(rows, dict):
        out: Dict[str, Dict[str, Any]] = {}
        for k, v in rows.items():
            code = str(k or "").strip()
            if not code or not isinstance(v, dict):
                continue
            status = str(v.get("status") or "").strip()
            if not status:
                continue
            out[code] = {
                "status": status,
                "reason": str(v.get("reason") or "").strip(),
                "updated_at_utc": str(v.get("updated_at_utc") or ""),
                "started_at_utc": str(v.get("started_at_utc") or v.get("updated_at_utc") or ""),
                "set_by_badge": str(v.get("set_by_badge") or "").strip(),
                "set_by_name": str(v.get("set_by_name") or "").strip(),
                "set_by_role": str(v.get("set_by_role") or "").strip(),
            }
        return out
    raise RuntimeError("machine_status_overrides SQL storage is unavailable")


def save_machine_status_overrides(rows: Dict[str, Dict[str, Any]]):
    if not _save_machine_status_overrides_sql(rows):
        raise RuntimeError("machine_status_overrides SQL storage is unavailable")


def load_machine_status_archive() -> List[Dict[str, Any]]:
    rows = _load_machine_status_archive_sql()
    if rows is None:
        raise RuntimeError("machine_status_archive SQL storage is unavailable")
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        machine_code = str(row.get("machine_code") or "").strip()
        status = str(row.get("status") or "").strip()
        if not machine_code or not status:
            continue
        out.append(
            {
                "machine_code": machine_code,
                "machine_name": str(row.get("machine_name") or "").strip(),
                "status": status,
                "reason": str(row.get("reason") or "").strip(),
                "set_by_badge": str(row.get("set_by_badge") or "").strip(),
                "set_by_name": str(row.get("set_by_name") or "").strip(),
                "set_by_role": str(row.get("set_by_role") or "").strip(),
                "started_at_utc": str(row.get("started_at_utc") or row.get("updated_at_utc") or "").strip(),
                "ended_at_utc": str(row.get("ended_at_utc") or "").strip(),
                "duration_seconds": row.get("duration_seconds"),
                "closed_by_badge": str(row.get("closed_by_badge") or "").strip(),
                "closed_by_name": str(row.get("closed_by_name") or "").strip(),
                "closed_by_role": str(row.get("closed_by_role") or "").strip(),
                "closed_reason": str(row.get("closed_reason") or "").strip(),
                "closed_action": str(row.get("closed_action") or "").strip(),
            }
        )
    return out


def save_machine_status_archive(rows: List[Dict[str, Any]]):
    if not _save_machine_status_archive_sql(rows):
        raise RuntimeError("machine_status_archive SQL storage is unavailable")


def _parse_iso_utc(iso: Any) -> Optional[datetime]:
    s = str(iso or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _parse_number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return 0.0
    raw = str(value).strip()
    if not raw:
        return 0.0
    m = re.search(r"-?\d+(?:\.\d+)?", raw)
    if not m:
        return 0.0
    try:
        return float(m.group(0))
    except Exception:
        return 0.0


def _parse_cycle_seconds(value: Any) -> Optional[float]:
    seconds = _parse_number(value)
    return seconds if seconds > 0 else None


def _extract_job_record_from_payload(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data_obj = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if isinstance(data_obj.get("job"), dict):
        return data_obj["job"]
    if isinstance(payload.get("job"), dict):
        return payload["job"]
    return payload


def _extract_job_details_from_payload(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data_obj = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if isinstance(data_obj.get("job_details"), dict):
        return data_obj["job_details"]
    if isinstance(payload.get("job_details"), dict):
        return payload["job_details"]
    return {}


def _extract_job_partials_from_payload(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data_obj = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    partials = data_obj.get("partials") if isinstance(data_obj.get("partials"), list) else []
    return [row for row in partials if isinstance(row, dict)]


def _qty_per_shift_from_cycle(cycle_seconds: Optional[float], cavities: Any = 1) -> Optional[int]:
    if cycle_seconds is None or cycle_seconds <= 0:
        return None
    try:
        cavity_count = int(float(cavities or 1))
    except Exception:
        cavity_count = 1
    cavity_count = max(1, cavity_count)
    try:
        return int(((12 * 60 * 60) / cycle_seconds) * cavity_count)
    except Exception:
        return None


def _build_job_queue_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    now_utc = utc_now()
    for sess in SESSIONS.values():
        if not isinstance(sess, MachineSession):
            continue
        if not str(sess.machine_code or "").strip():
            continue
        if not str(sess.job_code or "").strip():
            continue

        payload = sess.job_payload if isinstance(sess.job_payload, dict) else {}
        job = _extract_job_record_from_payload(payload)
        job_details = _extract_job_details_from_payload(payload)
        partials = _extract_job_partials_from_payload(payload)

        target_qty_raw = job.get("approve_qty")
        if _parse_number(target_qty_raw) <= 0:
            target_qty_raw = job.get("request_qty")
        target_qty = max(0, int(round(_parse_number(target_qty_raw))))

        api_partial_total = 0
        for part in partials:
            api_partial_total += int(round(_parse_number(part.get("partial_qty"))))

        live_good_total = max(0, int(sess.good_total or 0) + int(sess.butal_total or 0))
        produced_now = max(0, api_partial_total + live_good_total)
        remaining_qty = max(target_qty - produced_now, 0)
        overrun_qty = max(produced_now - target_qty, 0)
        last_seen_dt = _parse_iso_utc(sess.last_seen_utc)
        is_connected = False
        if last_seen_dt is not None:
            try:
                is_connected = (now_utc - last_seen_dt).total_seconds() <= float(ACTIVE_TTL_SECONDS or 0)
            except Exception:
                is_connected = False
        eta_anchor_utc = now_utc if is_connected else (last_seen_dt or now_utc)

        cavities_raw = (
            job_details.get("no_of_cavity")
            or job.get("custom_11")
            or job.get("no_of_cavity")
            or 1
        )
        try:
            cavity_count = max(1, int(round(_parse_number(cavities_raw) or 1)))
        except Exception:
            cavity_count = 1

        act_cycle_seconds = _parse_cycle_seconds(sess.cycle_time_current)
        live_cycle_seconds = _parse_cycle_seconds(sess.live_cycle_avg_seconds)
        act_qty_per_shift = _qty_per_shift_from_cycle(act_cycle_seconds, cavity_count)
        live_qty_per_shift = _qty_per_shift_from_cycle(live_cycle_seconds, 1)

        act_remaining_seconds: Optional[int] = None
        live_remaining_seconds: Optional[int] = None
        expected_finish_act_utc = ""
        expected_finish_pack_utc = ""
        if remaining_qty > 0 and act_cycle_seconds is not None:
            act_remaining_seconds = max(0, int(math.ceil((remaining_qty / max(1, cavity_count)) * act_cycle_seconds)))
            expected_finish_act_utc = (eta_anchor_utc + timedelta(seconds=act_remaining_seconds)).isoformat()
        if remaining_qty > 0 and live_cycle_seconds is not None:
            live_remaining_seconds = max(0, int(math.ceil(remaining_qty * live_cycle_seconds)))
            expected_finish_pack_utc = (eta_anchor_utc + timedelta(seconds=live_remaining_seconds)).isoformat()

        status = "RUNNING"
        if not is_connected:
            status = "DISCONNECTED"
        elif target_qty <= 0:
            status = "NO TARGET"
        elif remaining_qty <= 0:
            status = "DONE"
        elif act_cycle_seconds is None and live_cycle_seconds is None:
            status = "NO CYCLE"

        rows.append(
            {
                "machine_code": str(sess.machine_code or "").strip(),
                "machine_name": str(sess.machine_name or sess.machine_code or "").strip(),
                "job_code": str(sess.job_code or "").strip(),
                "job_name": str(sess.job_name or "").strip(),
                "operator_id": str(sess.operator_id or "").strip(),
                "job_started_at": str(sess.job_started_at or "").strip(),
                "last_seen_utc": str(sess.last_seen_utc or "").strip(),
                "is_connected": is_connected,
                "status": status,
                "target_qty": target_qty,
                "api_partial_total": api_partial_total,
                "live_good_total": live_good_total,
                "produced_now": produced_now,
                "remaining_qty": remaining_qty,
                "overrun_qty": overrun_qty,
                "pack_count": int(sess.pack_total or 0),
                "good_total": int(sess.good_total or 0),
                "butal_total": int(sess.butal_total or 0),
                "cavity_count": cavity_count,
                "act_cycle_seconds": act_cycle_seconds,
                "live_cycle_seconds": live_cycle_seconds,
                "act_qty_per_shift": act_qty_per_shift,
                "live_qty_per_shift": live_qty_per_shift,
                "remaining_seconds_act": act_remaining_seconds,
                "remaining_seconds_pack": live_remaining_seconds,
                "expected_finish_act_utc": expected_finish_act_utc,
                "expected_finish_pack_utc": expected_finish_pack_utc,
            }
        )

    rows.sort(
        key=lambda row: (
            1 if str(row.get("status") or "") == "DONE" else 0,
            str(row.get("machine_name") or ""),
            str(row.get("job_name") or row.get("job_code") or ""),
        )
    )
    return rows


def _close_machine_status_archive_entries(
    machine_code: str,
    *,
    closed_by_badge: str = "",
    closed_by_name: str = "",
    closed_by_role: str = "",
    closed_reason: str = "",
    closed_action: str = "",
    ended_at: Optional[datetime] = None,
) -> bool:
    code = str(machine_code or "").strip()
    if not code:
        return False
    ended_dt = ended_at or utc_now()
    changed = False
    for row in MACHINE_STATUS_ARCHIVE:
        if not isinstance(row, dict):
            continue
        if str(row.get("machine_code") or "").strip() != code:
            continue
        if str(row.get("ended_at_utc") or "").strip():
            continue
        started_dt = _parse_iso_utc(row.get("started_at_utc"))
        duration_seconds: Optional[int] = None
        if started_dt is not None:
            try:
                duration_seconds = max(0, int((ended_dt - started_dt).total_seconds()))
            except Exception:
                duration_seconds = None
        row["ended_at_utc"] = ended_dt.isoformat()
        row["duration_seconds"] = duration_seconds
        row["closed_by_badge"] = str(closed_by_badge or "").strip()
        row["closed_by_name"] = str(closed_by_name or "").strip()
        row["closed_by_role"] = str(closed_by_role or "").strip()
        row["closed_reason"] = str(closed_reason or "").strip()
        row["closed_action"] = str(closed_action or "").strip()
        changed = True
    if changed:
        save_machine_status_archive(MACHINE_STATUS_ARCHIVE)
    return changed


def _finished_job_key(row: Dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("finished_at_utc", "")),
            str(row.get("machine_code", "")),
            str(row.get("job_code", "")),
            str(row.get("operator_id", "")),
            str(row.get("pack_count", "")),
            str(row.get("good_total", "")),
            str(row.get("butal_total", "")),
            str(row.get("reject_total", "")),
        ]
    )


def _find_finished_job_index(rows: List[Dict[str, Any]], key: str) -> int:
    for i, row in enumerate(rows):
        if isinstance(row, dict) and _finished_job_key(row) == key:
            return i
    return -1


def _finished_job_review_rank(row: Dict[str, Any]) -> int:
    status = str((row or {}).get("review_status") or "").strip().upper()
    if status == "APPROVED":
        return 3
    if status == "DISAPPROVED_CHANGED":
        return 2
    if status:
        return 1
    return 0


def _prefer_finished_job_row(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    if _finished_job_review_rank(incoming) > _finished_job_review_rank(existing):
        return incoming
    existing_stamp = str((existing or {}).get("approved_at_utc") or (existing or {}).get("changed_at_utc") or (existing or {}).get("finished_at_utc") or "")
    incoming_stamp = str((incoming or {}).get("approved_at_utc") or (incoming or {}).get("changed_at_utc") or (incoming or {}).get("finished_at_utc") or "")
    if incoming_stamp and incoming_stamp >= existing_stamp:
        return incoming
    return existing


def _reviewer_from_badge(code: str) -> Optional[Dict[str, str]]:
    badge = str(code or "").strip()
    today = get_today_role_assignments()
    assigned = today.get(badge) if isinstance(today, dict) else None
    if isinstance(assigned, dict):
        rights = str(assigned.get("rights", "")).strip().lower()
        name = str(assigned.get("name", "")).strip() or SUPERVISOR_BADGES.get(badge) or QC_BADGES.get(badge) or badge
        if rights in ("supervisor", "qc", "both"):
            role = "Supervisor/QC" if rights == "both" else ("Supervisor" if rights == "supervisor" else "QC")
            return {"code": badge, "name": name, "role": role, "rights": rights}
    if badge in SUPERVISOR_BADGES:
        return {"code": badge, "name": SUPERVISOR_BADGES[badge], "role": "Supervisor", "rights": "supervisor"}
    if badge in QC_BADGES:
        return {"code": badge, "name": QC_BADGES[badge], "role": "QC", "rights": "qc"}
    profile = _find_profile_by_id_number(badge)
    if isinstance(profile, dict):
        company_role = _normalize_company_role(profile.get("company_role") or profile.get("role") or "")
        extra = str(profile.get("extra_privilege", "") or "").strip().lower()
        rights = _combine_privileges(_base_privilege_from_company_role(company_role), extra)
        if rights in ("supervisor", "qc", "both"):
            role = "Supervisor/QC" if rights == "both" else ("Supervisor" if rights == "supervisor" else "QC")
            name = str(profile.get("name", "") or "").strip() or badge
            return {"code": badge, "name": name, "role": role, "rights": rights}
    return None


def _person_from_badge_any(code: str) -> Optional[Dict[str, str]]:
    badge = str(code or "").strip()
    if not badge:
        return None
    today = get_today_role_assignments()
    assigned = today.get(badge) if isinstance(today, dict) else None
    if isinstance(assigned, dict):
        rights = str(assigned.get("rights", "")).strip().lower()
        company_role = _normalize_company_role(assigned.get("company_role", ""))
        role = company_role or (rights.upper() if rights else "")
        name = (
            str(assigned.get("name", "")).strip()
            or (str(_find_profile_by_id_number(badge).get("name", "")).strip() if _find_profile_by_id_number(badge) else "")
            or badge
        )
        return {"code": badge, "name": name, "role": role or "User", "rights": rights or "viewer"}
    profile = _find_profile_by_id_number(badge)
    if isinstance(profile, dict):
        company_role = _normalize_company_role(profile.get("company_role") or profile.get("role") or "")
        extra = str(profile.get("extra_privilege", "") or "").strip().lower()
        rights = _combine_privileges(_base_privilege_from_company_role(company_role), extra)
        name = str(profile.get("name", "") or "").strip() or badge
        return {"code": badge, "name": name, "role": company_role or "User", "rights": rights}
    return None


def _find_profile_by_id_number(id_number: str) -> Optional[Dict[str, Any]]:
    code = str(id_number or "").strip()
    if not code:
        return None
    for row in PROFILES:
        if not isinstance(row, dict):
            continue
        if str(row.get("id_number", "")).strip() == code:
            return row
    return None


def _normalize_company_role(value: Any) -> str:
    role = str(value or "").strip()
    low = role.lower()
    if low in {"qa/qc", "qa", "qc"}:
        return "QA/QC"
    if low == "supervisor":
        return "Supervisor"
    if low == "operator":
        return "Operator"
    if low == "maintenance":
        return "Maintenance"
    if low == "planner":
        return "Planner"
    if low == "production manager":
        return "Production Manager"
    return role


def _base_privilege_from_company_role(company_role: str) -> str:
    low = str(company_role or "").strip().lower()
    if low == "supervisor":
        return "supervisor"
    if low in {"qa/qc", "qa", "qc"}:
        return "qc"
    if low == "operator":
        return "operator"
    if low == "maintenance":
        return "maintenance"
    if low in {"planner", "production manager"}:
        return "viewer"
    return "viewer"


def _combine_privileges(base_privilege: str, extra_privilege: str) -> str:
    base = str(base_privilege or "").strip().lower() or "viewer"
    extra = str(extra_privilege or "").strip().lower()
    if extra not in {"", "none", "supervisor", "qc", "operator", "maintenance"}:
        extra = ""
    pair = {base}
    if extra and extra != "none":
        pair.add(extra)
    if "supervisor" in pair and "qc" in pair:
        return "both"
    if "supervisor" in pair:
        return "supervisor"
    if "qc" in pair:
        return "qc"
    if "maintenance" in pair:
        return "maintenance"
    if "operator" in pair:
        return "operator"
    return "viewer"


def load_finished_jobs() -> List[Dict[str, Any]]:
    current_rows = _load_finished_jobs_sql()
    fallback_rows = _load_json_list(FINISHED_JOBS_FALLBACK_FILE)
    if current_rows is None:
        if fallback_rows:
            current_rows = fallback_rows
        else:
            raise RuntimeError("finished_jobs SQL storage is unavailable")
    elif fallback_rows:
        current_rows = list(current_rows) + fallback_rows
    merged: List[Dict[str, Any]] = []
    index_by_key: Dict[str, int] = {}
    for row in current_rows:
        if not isinstance(row, dict):
            continue
        key = _finished_job_key(row)
        if key in index_by_key:
            existing_idx = index_by_key[key]
            merged[existing_idx] = _prefer_finished_job_row(merged[existing_idx], row)
            continue
        index_by_key[key] = len(merged)
        merged.append(row)
    return merged


def save_finished_jobs(rows: List[Dict[str, Any]]):
    json_ok = _save_json_list(FINISHED_JOBS_FALLBACK_FILE, rows)
    sql_ok = _save_finished_jobs_sql(rows)
    if not sql_ok and not json_ok:
        raise RuntimeError("finished_jobs SQL storage is unavailable")


def load_archived_jobs() -> List[Dict[str, Any]]:
    rows = _load_archived_jobs_sql()
    fallback_rows = _load_json_list(ARCHIVED_JOBS_FALLBACK_FILE)
    if not isinstance(rows, list):
        rows = []
    if fallback_rows:
        merged: List[Dict[str, Any]] = []
        index_by_key: Dict[str, int] = {}
        for row in list(rows) + fallback_rows:
            if not isinstance(row, dict):
                continue
            key = _finished_job_key(row)
            if key in index_by_key:
                merged[index_by_key[key]] = _prefer_finished_job_row(merged[index_by_key[key]], row)
                continue
            index_by_key[key] = len(merged)
            merged.append(row)
        return merged
    return rows


def save_archived_jobs(rows: List[Dict[str, Any]]):
    json_ok = _save_json_list(ARCHIVED_JOBS_FALLBACK_FILE, rows)
    sql_ok = _save_archived_jobs_sql(rows)
    if not sql_ok and not json_ok:
        raise RuntimeError("archived_jobs_server SQL storage is unavailable")


def load_profiles() -> List[Dict[str, Any]]:
    rows = _load_profiles_sql()
    if isinstance(rows, list):
        return [r for r in rows if isinstance(r, dict)]
    raise RuntimeError("user_qr_profiles SQL storage is unavailable")


def save_profiles(rows: List[Dict[str, Any]]):
    if not _save_profiles_sql(rows):
        raise RuntimeError("user_qr_profiles SQL storage is unavailable")


def _operator_record_matches_profile(operator_value: Any, profile: Dict[str, Any]) -> bool:
    raw = str(operator_value or "").strip()
    if not raw or not isinstance(profile, dict):
        return False
    profile_id = str(profile.get("id_number") or "").strip()
    profile_name = str(profile.get("name") or "").strip().casefold()
    code_part = raw.split(" - ", 1)[0].strip()
    name_part = raw.split(" - ", 1)[1].strip().casefold() if " - " in raw else ""
    if profile_id and (raw == profile_id or code_part == profile_id):
        return True
    if profile_name and (raw.casefold() == profile_name or name_part == profile_name):
        return True
    return False


def _activity_timestamp(row: Dict[str, Any]) -> Optional[datetime]:
    if not isinstance(row, dict):
        return None
    for key in ("finished_at_utc", "last_seen_utc", "saved_at_utc", "created_at_utc", "updated_at_utc"):
        dt = _parse_iso_utc(row.get(key))
        if dt is not None:
            return dt
    return None


def _operator_activity_summary(profile: Dict[str, Any]) -> Dict[str, Any]:
    active_rows = [s.to_dict() for s in SESSIONS.values() if _operator_record_matches_profile(getattr(s, "operator_id", ""), profile)]
    active_rows.sort(key=lambda x: _activity_timestamp(x) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    history_rows = [r for r in [*FINISHED_JOBS, *ARCHIVED_JOBS] if _operator_record_matches_profile((r or {}).get("operator_id", ""), profile)]
    history_rows.sort(key=lambda x: _activity_timestamp(x) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    latest_active = active_rows[0] if active_rows else None
    latest_history = history_rows[0] if history_rows else None
    recent_activity: List[Dict[str, Any]] = []

    if latest_active:
        recent_activity.append(
            {
                "kind": "active_session",
                "label": "Currently active",
                "machine_code": latest_active.get("machine_code", ""),
                "machine_name": latest_active.get("machine_name", ""),
                "job_code": latest_active.get("job_code", ""),
                "job_name": latest_active.get("job_name", ""),
                "at_utc": latest_active.get("last_seen_utc", ""),
                "detail": f"Monitoring {latest_active.get('machine_name') or latest_active.get('machine_code') or '-'}",
            }
        )

    for row in history_rows[:3]:
        machine_name = row.get("machine_name") or row.get("machine_code") or "-"
        job_name = row.get("job_name") or row.get("job_code") or "-"
        recent_activity.append(
            {
                "kind": "finished_job",
                "label": "Finished job",
                "machine_code": row.get("machine_code", ""),
                "machine_name": row.get("machine_name", ""),
                "job_code": row.get("job_code", ""),
                "job_name": row.get("job_name", ""),
                "at_utc": row.get("finished_at_utc", ""),
                "detail": f"{machine_name} | {job_name}",
            }
        )

    deduped_activity: List[Dict[str, Any]] = []
    seen_keys = set()
    for item in recent_activity:
        key = (
            str(item.get("kind") or ""),
            str(item.get("machine_code") or ""),
            str(item.get("job_code") or ""),
            str(item.get("at_utc") or ""),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped_activity.append(item)

    last_row = latest_active or latest_history or {}
    last_ts = _activity_timestamp(last_row)
    return {
        "name": str(profile.get("name") or "").strip(),
        "id_number": str(profile.get("id_number") or "").strip(),
        "role": str(profile.get("role") or "").strip(),
        "is_active": bool(latest_active),
        "current_machine_code": str((latest_active or {}).get("machine_code") or "").strip(),
        "current_machine_name": str((latest_active or {}).get("machine_name") or "").strip(),
        "current_job_code": str((latest_active or {}).get("job_code") or "").strip(),
        "current_job_name": str((latest_active or {}).get("job_name") or "").strip(),
        "last_machine_code": str(last_row.get("machine_code") or "").strip(),
        "last_machine_name": str(last_row.get("machine_name") or "").strip(),
        "last_job_code": str(last_row.get("job_code") or "").strip(),
        "last_job_name": str(last_row.get("job_name") or "").strip(),
        "last_activity_at_utc": last_ts.isoformat() if last_ts else "",
        "recent_activity": deduped_activity[:3],
        "all_activity": deduped_activity[:20],
    }


def build_operator_activity_directory() -> List[Dict[str, Any]]:
    operators = [p for p in PROFILES if isinstance(p, dict) and str(p.get("role") or "").strip().casefold() == "operator"]
    items = [_operator_activity_summary(p) for p in operators]
    items.sort(key=lambda row: str(row.get("name") or "").casefold())
    items.sort(key=lambda row: _parse_iso_utc(row.get("last_activity_at_utc")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    items.sort(key=lambda row: 0 if row.get("is_active") else 1)
    return items


def _today_key_local() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def load_daily_role_assignments() -> Dict[str, Any]:
    rows = _load_daily_role_assignments_sql()
    if isinstance(rows, dict):
        return rows
    raise RuntimeError("daily_role_assignments SQL storage is unavailable")


def save_daily_role_assignments(rows: Dict[str, Any]):
    if not _save_daily_role_assignments_sql(rows):
        raise RuntimeError("daily_role_assignments SQL storage is unavailable")


def get_today_role_assignments() -> Dict[str, Any]:
    day = _today_key_local()
    bucket = DAILY_ROLE_ASSIGNMENTS.get(day)
    return dict(bucket) if isinstance(bucket, dict) else {}


def set_today_role_assignment(
    badge_code: str,
    person_name: str,
    rights: str,
    *,
    company_role: str = "",
    extra_privilege: str = "",
):
    day = _today_key_local()
    DAILY_ROLE_ASSIGNMENTS.setdefault(day, {})
    DAILY_ROLE_ASSIGNMENTS[day][str(badge_code)] = {
        "name": str(person_name or "").strip(),
        "rights": str(rights or "").strip().lower(),
        "company_role": _normalize_company_role(company_role),
        "extra_privilege": str(extra_privilege or "").strip().lower(),
        "updated_at_utc": utc_now().isoformat() if "utc_now" in globals() else datetime.now(timezone.utc).isoformat(),
    }
    save_daily_role_assignments(DAILY_ROLE_ASSIGNMENTS)


def _zpad_digits(value: Any, width: int) -> str:
    d = re.sub(r"\D+", "", str(value or ""))
    if len(d) > width:
        d = d[-width:]
    return d.zfill(width)


def _build_raw_material_qr_value(
    product_id: str,
    po_number: str = "",
    *,
    qty: Any = 1,
    index_value: Any = 1,
    total: Any = 1,
    lot_number: str = "",
) -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    p = "P" + _zpad_digits(product_id, WIDTH_P)
    q = "Q" + _zpad_digits(qty, WIDTH_Q)
    i = "I" + _zpad_digits(index_value, WIDTH_I)
    t = "T" + _zpad_digits(total, WIDTH_T)
    po_digits = _zpad_digits(po_number, 12)
    lot_digits = re.sub(r"[^0-9A-Za-z\-]+", "", str(lot_number or "").strip())
    l = "L" + (lot_digits or f"{stamp}-{po_digits}")
    return f"{RAW_QR_O_SEGMENT}{RAW_QR_REMARK}{p}{q}{i}{t}{l}"


def _raw_qr_format_template() -> str:
    return (
        "O000000000240000010237800000000000"
        "V2"
        "P###########"
        "Q00000000001"
        "I00000000001"
        "T00000000001"
        "LYYYYMMDDHHMMSS-000000000000"
    )


def _parse_number_like(value: Any) -> float:
    raw = str(value or "").strip().replace(",", "")
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


def _extract_primary_part_row(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data_obj = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    job_details = data_obj.get("job_details") if isinstance(data_obj.get("job_details"), dict) else {}
    part_rows: List[Dict[str, Any]] = []
    if isinstance(data_obj.get("parts"), list):
        part_rows = [r for r in data_obj.get("parts") or [] if isinstance(r, dict)]
    elif isinstance(job_details.get("parts"), list):
        part_rows = [r for r in job_details.get("parts") or [] if isinstance(r, dict)]
    elif isinstance(job_details.get("part_ids"), list):
        part_rows = [r for r in job_details.get("part_ids") or [] if isinstance(r, dict)]
    elif isinstance(job_details.get("part_ids"), dict):
        part_rows = [job_details.get("part_ids") or {}]
    elif isinstance(data_obj.get("part_ids"), list):
        part_rows = [r for r in data_obj.get("part_ids") or [] if isinstance(r, dict)]
    return part_rows[0] if part_rows else {}


def _build_finished_job_qr_plan(finished_job: Dict[str, Any], product_id: str, po_number: str) -> List[Dict[str, Any]]:
    row = finished_job if isinstance(finished_job, dict) else {}
    payload = row.get("job_payload") if isinstance(row.get("job_payload"), dict) else {}
    data_obj = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    job = data_obj.get("job") if isinstance(data_obj.get("job"), dict) else {}
    part_row = _extract_primary_part_row(payload)
    part_qty_per_unit = _parse_number_like(part_row.get("part_qty_per_unit"))
    if part_qty_per_unit <= 0:
        part_qty_per_unit = 0.0
    total_good = max(0.0, _parse_number_like(row.get("total_good", 0)))
    raw_logs = row.get("raw_material_logs") if isinstance(row.get("raw_material_logs"), list) else []
    pack_logs = row.get("product_pack_history_logs") if isinstance(row.get("product_pack_history_logs"), list) else []
    butal_logs = row.get("butal_scan_logs") if isinstance(row.get("butal_scan_logs"), list) else []
    scanned_raw_qty = 0.0
    for item in raw_logs:
        if not isinstance(item, dict):
            continue
        scanned_raw_qty += max(0.0, _parse_number_like(item.get("qty", 0)))
    used_raw_qty = min(scanned_raw_qty, total_good * part_qty_per_unit)
    available_raw_qty = max(0.0, scanned_raw_qty - used_raw_qty)
    butal_total = max(0, int(round(_parse_number_like(row.get("butal_total", 0)))))
    plan: List[Dict[str, Any]] = []
    base_lot = _zpad_digits(po_number, 12)
    excess_qty = max(0, int(math.floor(available_raw_qty)))
    if excess_qty > 0:
        raw_name = ""
        raw_meta = {"id": str(product_id or "").strip(), "name": "", "sku": ""}
        if raw_logs:
            latest_raw = raw_logs[-1] if isinstance(raw_logs[-1], dict) else {}
            raw_name = str(latest_raw.get("material_name") or latest_raw.get("material") or "").strip()
            raw_meta = _lookup_product_meta_by_text(raw_name)
        plan.append(
            {
                "stage_kind": "RAW_EXCESS",
                "stage_title": "Raw Material Excess",
                "product_id": raw_meta.get("id", "") or str(product_id or "").strip(),
                "product_name": raw_meta.get("name", "") or raw_name,
                "product_sku": raw_meta.get("sku", ""),
                "qty": str(excess_qty),
                "index": "1",
                "total": "1",
                "po_required": False,
                "po_number": "",
                "lot_number": f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{base_lot}",
            }
        )
    if butal_total > 0:
        latest_pack = pack_logs[-1] if pack_logs and isinstance(pack_logs[-1], dict) else {}
        if not latest_pack and butal_logs:
            for item in reversed(butal_logs):
                if isinstance(item, dict) and str(item.get("raw_scan") or "").strip():
                    parsed_butal = _parse_qr_segments(str(item.get("raw_scan") or ""))
                    if parsed_butal:
                        latest_pack = {
                            "raw_scan": str(item.get("raw_scan") or ""),
                            "product_p": parsed_butal.get("product_id", ""),
                            "qty_q": parsed_butal.get("qty", butal_total),
                            "index": parsed_butal.get("index", "1"),
                            "total_labels": parsed_butal.get("total", "1"),
                            "lot_number": parsed_butal.get("lot_number", ""),
                            "po_number": parsed_butal.get("po_number", ""),
                        }
                        break
        pack_product_id = str(
            latest_pack.get("product_p")
            or latest_pack.get("product_id")
            or row.get("product_id")
            or job.get("product_id")
            or part_row.get("product_id")
            or product_id
            or ""
        ).strip()
        pack_meta = _lookup_product_meta(pack_product_id.lstrip("0") if pack_product_id.isdigit() else pack_product_id)
        plan.append(
            {
                "stage_kind": "BUTAL",
                "stage_title": "Butal Return",
                "product_id": pack_meta.get("id", "") or (pack_product_id.lstrip("0") if pack_product_id.isdigit() else pack_product_id),
                "product_name": pack_meta.get("name", ""),
                "product_sku": pack_meta.get("sku", ""),
                "pack_hist": latest_pack,
                "qty": str(butal_total),
                "index": "1",
                "total": "1",
                "po_required": True,
                "po_number": str(po_number or "").strip(),
                "lot_number": f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{base_lot}",
            }
        )
    if not plan:
        plan.append(
            {
                "stage_kind": "DEFAULT",
                "stage_title": "Raw Material QR",
                "product_id": str(product_id or "").strip(),
                "product_name": "",
                "product_sku": "",
                "qty": "1",
                "index": "1",
                "total": "1",
                "po_required": False,
                "po_number": "",
                "lot_number": f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{base_lot}",
            }
        )
    enriched: List[Dict[str, Any]] = []
    total_stages = len(plan)
    for idx, entry in enumerate(plan, start=1):
        entry_product_id = str(entry.get("product_id", "")).strip() or str(product_id or "").strip()
        if str(entry.get("stage_kind") or "").upper() == "BUTAL" and isinstance(entry.get("pack_hist"), dict):
            stage_po = str(entry.get("po_number", "")).strip()
            payload_text = ""
            if stage_po:
                pack_hist = dict(entry.get("pack_hist") or {})
                pack_hist["po_number"] = stage_po
                payload_text = _build_butal_qr_from_pack_history(pack_hist, entry.get("qty", "1"), index_value=entry.get("index", "1"))
        else:
            payload_text = _build_raw_material_qr_value(
                entry_product_id,
                po_number=str(entry.get("po_number", "")).strip(),
                qty=entry.get("qty", "1"),
                index_value=entry.get("index", "1"),
                total=entry.get("total", "1"),
                lot_number=str(entry.get("lot_number", "")).strip(),
            )
        parsed = _parse_qr_segments(payload_text)
        enriched.append(
            {
                **entry,
                "stage_index": idx,
                "stage_total": total_stages,
                "stage_label": f"{idx} / {total_stages} - {entry.get('stage_title', 'QR')}",
                "qr_payload": payload_text,
                "parsed": parsed,
            }
        )
    return enriched


def _qr_png_data_url(payload: str) -> str:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=3,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _lookup_product_meta(product_id: str) -> Dict[str, str]:
    items = get_products(force_refresh=False).get("items") or []
    for it in items:
        if str(it.get("id", "")).strip() == str(product_id).strip():
            return {
                "id": str(it.get("id", "")).strip(),
                "name": str(it.get("name", "")).strip(),
                "sku": str(it.get("sku", "")).strip(),
            }
    return {"id": str(product_id or "").strip(), "name": "", "sku": ""}


def _lookup_product_meta_by_text(text: str) -> Dict[str, str]:
    q = str(text or "").strip().casefold()
    if not q:
        return {"id": "", "name": "", "sku": ""}
    items = get_products(force_refresh=False).get("items") or []
    for it in items:
        name = str(it.get("name", "")).strip()
        sku = str(it.get("sku", "")).strip()
        if q == name.casefold() or q == sku.casefold() or q == f"{sku} - {name}".strip().casefold():
            return {"id": str(it.get("id", "")).strip(), "name": name, "sku": sku}
    for it in items:
        name = str(it.get("name", "")).strip()
        sku = str(it.get("sku", "")).strip()
        hay = f"{sku} {name}".casefold()
        if q and q in hay:
            return {"id": str(it.get("id", "")).strip(), "name": name, "sku": sku}
    return {"id": "", "name": str(text or "").strip(), "sku": ""}


def _build_butal_qr_from_pack_history(pack_hist: Dict[str, Any], qty: Any, index_value: Any = 1) -> str:
    p_digits = _zpad_digits(pack_hist.get("product_p") or pack_hist.get("product_id"), WIDTH_P)
    q_digits = _zpad_digits(qty, WIDTH_Q)
    i_digits = _zpad_digits(index_value, WIDTH_I)
    t_digits = _zpad_digits(1, WIDTH_T)
    lot_number = str(pack_hist.get("lot_number") or "").strip()
    po_number = str(pack_hist.get("po_number") or "").strip()
    if len(re.sub(r"\D+", "", lot_number)) != 14:
        lot_number = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{RAW_QR_O_SEGMENT}{RAW_QR_REMARK}P{p_digits}QB{q_digits}I{i_digits}T{t_digits}L{lot_number}-{_zpad_digits(po_number, 12)}"


def _extract_seg(qr_value: str, tag: str, width: int) -> str:
    pos = qr_value.find(tag)
    if pos < 0:
        return ""
    return qr_value[pos + 1: pos + 1 + width]


def _strip_leading_zeros(digits: str) -> str:
    s = (digits or "").lstrip("0")
    return s if s else "0"


def _parse_qr_segments(qr_value: str) -> Dict[str, str]:
    p_digits = _extract_seg(qr_value, "P", WIDTH_P)
    q_digits = _extract_seg(qr_value, "Q", WIDTH_Q)
    i_digits = _extract_seg(qr_value, "I", WIDTH_I)
    t_digits = _extract_seg(qr_value, "T", WIDTH_T)
    l_seg = _extract_seg(qr_value, "L", WIDTH_L)
    yy = ""
    mm = ""
    l_trim = l_seg.lstrip("0")
    lot_number = l_trim or l_seg
    po_number = ""
    if "-" in l_seg:
        po_number = _strip_leading_zeros(l_seg.split("-", 1)[1])
    if len(l_trim) >= 8 and l_trim[:8].isdigit():
        yyyy = l_trim[0:4]
        mm = l_trim[4:6]
        yy = yyyy[2:4]
    return {
        "product": _strip_leading_zeros(p_digits),
        "qty": _strip_leading_zeros(q_digits),
        "index": _strip_leading_zeros(i_digits),
        "total": _strip_leading_zeros(t_digits),
        "lot_number": lot_number,
        "po_number": po_number,
        "yy": yy,
        "mm": mm,
    }


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_w: int, max_h: int, start: int, min_px: int = 10) -> ImageFont.ImageFont:
    font_candidates = [
        "arial.ttf",
        "segoeui.ttf",
        "calibri.ttf",
        "DejaVuSans.ttf",
        "cour.ttf",
    ]
    for px in range(start, min_px - 1, -1):
        f = None
        for name in font_candidates:
            try:
                f = ImageFont.truetype(name, px)
                break
            except Exception:
                continue
        if f is None:
            f = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=f)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        if tw <= max_w and th <= max_h:
            return f
    return ImageFont.load_default()


def _draw_centered(draw: ImageDraw.ImageDraw, rect: tuple, text: str, start_px: int, fill=(0, 0, 0)):
    x0, y0, x1, y1 = rect
    w = max(1, x1 - x0)
    h = max(1, y1 - y0)
    font = _fit_font(draw, text, w, h, start=start_px, min_px=8)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = x0 + (w - tw) // 2
    ty = y0 + (h - th) // 2
    draw.text((tx, ty), text, fill=fill, font=font)


def _label_png_data_url(payload: str, product_id: str, product_name: str, product_sku: str = "", qty: int = 1, index_value: int = 1, total: int = 1) -> str:
    # Ported layout proportions from Automatic QR Generator.py
    dpi = 120
    label_w_in = TOTAL_W_IN / COLS
    w = max(10, int(round(label_w_in * dpi)))
    h = max(10, int(round(TOTAL_H_IN * dpi)))
    top_bar_h = int(round(TOP_BAR_IN * dpi))
    mid_h = int(round(MID_IN * dpi))
    bottom_h = h - top_bar_h - mid_h

    seg = _parse_qr_segments(payload)
    resolved_product_id = seg.get("product", str(product_id))
    meta = _lookup_product_meta(resolved_product_id)
    resolved_product_name = (product_name or meta.get("name") or resolved_product_id)
    resolved_product_sku = (product_sku or meta.get("sku") or "")

    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    black = (0, 0, 0)
    white = (255, 255, 255)

    line_thick = max(2, int(dpi * 0.01))
    draw.rectangle((0, top_bar_h - line_thick, w, top_bar_h), fill=black)
    draw.rectangle((0, top_bar_h + mid_h - line_thick, w, top_bar_h + mid_h), fill=black)

    idx_box_w = int(w * 0.34)
    draw.rectangle((w - idx_box_w, 0, w, top_bar_h), fill=black)
    _draw_centered(draw, (w - idx_box_w, 0, w, top_bar_h), seg.get("index", str(index_value)), start_px=24, fill=white)

    mid_y = top_bar_h
    left_col_w = int(w * 0.26)
    right_col_w = int(w * 0.26)
    center_w = w - left_col_w - right_col_w
    pad = max(4, int(w * 0.03))
    qr_target = max(10, min(center_w - 2 * pad, mid_h - 2 * pad))
    qr_x = left_col_w + (center_w - qr_target) // 2
    qr_y = mid_y + (mid_h - qr_target) // 2

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=1,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((qr_target, qr_target))
    img.paste(qr_img, (qr_x, qr_y))

    _draw_centered(draw, (0, mid_y + int(mid_h * 0.30), left_col_w, mid_y + int(mid_h * 0.52)), seg.get("qty", str(qty)), start_px=20)
    _draw_centered(draw, (0, mid_y + int(mid_h * 0.52), left_col_w, mid_y + int(mid_h * 0.74)), "PC", start_px=16)

    rx = left_col_w + center_w
    _draw_centered(draw, (rx, mid_y + int(mid_h * 0.30), rx + right_col_w, mid_y + int(mid_h * 0.52)), seg.get("yy", ""), start_px=20)
    _draw_centered(draw, (rx, mid_y + int(mid_h * 0.52), rx + right_col_w, mid_y + int(mid_h * 0.74)), seg.get("mm", ""), start_px=20)

    bottom_y = top_bar_h + mid_h
    top_h = int(bottom_h * 0.58)
    _draw_centered(draw, (0, bottom_y, w, bottom_y + top_h), resolved_product_sku or "-", start_px=22)
    _draw_centered(draw, (0, bottom_y + top_h, w, h), resolved_product_name, start_px=14)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _profile_qr_payload(name: str, id_number: str, role: str) -> str:
    # User requested QR content to be only the ID number.
    return str(id_number).strip()


def _profile_qr_png_data_url(payload: str, role: str, layout: str = "barcode_4x1.25") -> str:
    # Render at higher DPI so printed QR edges stay crisp on label printers.
    dpi = 300
    role_text = str(role or "").strip()
    resample_nearest = getattr(Image, "Resampling", Image).NEAREST
    if layout == "normal_2x2":
        w = int(round(2.0 * dpi))
        h = int(round(2.0 * dpi))
        pad_top = int(round(0.06 * dpi))
        side_pad = int(round(0.06 * dpi))
        footer_h = int(round(0.30 * dpi))
        qr_size = min(w - (side_pad * 2), h - pad_top - footer_h - side_pad)
        qr_size = max(int(round(0.9 * dpi)), qr_size)
        img = Image.new("RGB", (w, h), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=12, border=2)
        qr.add_data(payload)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((qr_size, qr_size), resample_nearest)
        x = (w - qr_size) // 2
        img.paste(qr_img, (x, pad_top))
        _draw_centered(draw, (side_pad, pad_top + qr_size + 6, w - side_pad, h - side_pad), role_text or "-", start_px=62)
    else:
        # Barcode-printer label: 4x1.25 overall, 3 columns. Fill only one column.
        total_w = int(round(4.0 * dpi))
        total_h = int(round(1.25 * dpi))
        col_w = int(round(total_w / 3.0))
        img = Image.new("RGB", (col_w, total_h), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        # Reserve a compact footer for role text; maximize QR within one column.
        footer_h = int(round(0.22 * dpi))
        inner_pad_x = int(round(0.03 * dpi))
        inner_pad_top = int(round(0.03 * dpi))
        qr_size = min(col_w - (inner_pad_x * 2), total_h - footer_h - inner_pad_top - int(round(0.02 * dpi)))
        qr_size = max(int(round(0.55 * dpi)), qr_size)
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=12, border=1)
        qr.add_data(payload)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((qr_size, qr_size), resample_nearest)
        x = (col_w - qr_size) // 2
        y = inner_pad_top
        img.paste(qr_img, (x, y))
        _draw_centered(draw, (4, total_h - footer_h, col_w - 4, total_h - 4), role_text or "-", start_px=34)
        draw.rectangle((0, 0, col_w - 1, total_h - 1), outline=(0, 0, 0), width=1)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def load_server_settings() -> Dict[str, Any]:
    raw = _load_server_settings_sql()
    if not isinstance(raw, dict):
        raise RuntimeError("server_settings SQL storage is unavailable")
    return {
        "theme": str(raw.get("theme", "Default")).strip() or "Default",
        "qrgen_base_url": str(raw.get("qrgen_base_url", QRGEN_BASE_URL)).strip().rstrip("/"),
    }


def save_server_settings(rows: Dict[str, Any]):
    if not _save_server_settings_sql(rows):
        raise RuntimeError("server_settings SQL storage is unavailable")
SERVER_SETTINGS: Dict[str, Any] = load_server_settings()


def current_qrgen_base_url() -> str:
    return str(SERVER_SETTINGS.get("qrgen_base_url", QRGEN_BASE_URL)).strip().rstrip("/")


DAILY_ROLE_ASSIGNMENTS: Dict[str, Any] = load_daily_role_assignments()


def _requested_at_ph_str() -> str:
    ph_tz = timezone(timedelta(hours=8))
    return datetime.now(ph_tz).strftime("%Y%m%d%H%M%S")


def _post_qrgen_pending_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{current_qrgen_base_url()}/api/pending-request"
    req = urllib_request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    with urllib_request.urlopen(req, timeout=12) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
        code = int(getattr(resp, "status", 200) or 200)
    parsed: Any = raw
    try:
        parsed = json.loads(raw) if raw else {}
    except Exception:
        pass
    return {"status_code": code, "body": parsed}


def _extract_products_from_payload(payload: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    rows = []
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for key in ("products", "data", "items", "result"):
            v = payload.get(key)
            if isinstance(v, list):
                rows = v
                break
        if not rows:
            data_obj = payload.get("data")
            if isinstance(data_obj, dict):
                nested_items = data_obj.get("items")
                if isinstance(nested_items, list):
                    rows = nested_items
    for it in rows:
        if not isinstance(it, dict):
            continue
        pid = str(it.get("id", "") or it.get("product_id", "") or it.get("productId", "")).strip()
        name = str(it.get("name", "") or it.get("product_name", "") or it.get("productName", "")).strip()
        sku = str(it.get("sku", "") or it.get("product_sku", "")).strip()
        tonnage = str(
            it.get("tonnage", "")
            or it.get("tons", "")
            or it.get("machine_tons", "")
            or it.get("machineTons", "")
            or it.get("clamping_force", "")
            or it.get("clampingForce", "")
            or ""
        ).strip()
        if pid and name:
            out.append({"id": pid, "name": name, "sku": sku, "tonnage": tonnage})
    return out


def _extract_pagination(payload: Any) -> Dict[str, Optional[int | bool]]:
    if not isinstance(payload, dict):
        return {"page": None, "total_pages": None, "has_next": None}

    page = None
    total_pages = None
    has_next = None

    def _to_int(v: Any) -> Optional[int]:
        try:
            if v is None:
                return None
            return int(v)
        except Exception:
            return None

    direct_page = _to_int(payload.get("page"))
    direct_total_pages = _to_int(payload.get("totalPages") or payload.get("total_pages"))
    direct_has_next = payload.get("hasNext") if isinstance(payload.get("hasNext"), bool) else payload.get("has_next")
    if isinstance(direct_has_next, bool):
        has_next = direct_has_next
    if direct_page is not None:
        page = direct_page
    if direct_total_pages is not None:
        total_pages = direct_total_pages

    data_obj = payload.get("data")
    if isinstance(data_obj, dict):
        if page is None:
            page = _to_int(data_obj.get("page"))
        if total_pages is None:
            total_pages = _to_int(data_obj.get("totalPages") or data_obj.get("total_pages"))
        if has_next is None:
            d_has_next = data_obj.get("hasNext") if isinstance(data_obj.get("hasNext"), bool) else data_obj.get("has_next")
            if isinstance(d_has_next, bool):
                has_next = d_has_next

    pag_obj = payload.get("pagination")
    if isinstance(pag_obj, dict):
        if page is None:
            page = _to_int(pag_obj.get("page") or pag_obj.get("currentPage") or pag_obj.get("current_page"))
        if total_pages is None:
            total_pages = _to_int(pag_obj.get("totalPages") or pag_obj.get("total_pages") or pag_obj.get("lastPage") or pag_obj.get("last_page"))
        if has_next is None:
            p_has_next = pag_obj.get("hasNext") if isinstance(pag_obj.get("hasNext"), bool) else pag_obj.get("has_next")
            if isinstance(p_has_next, bool):
                has_next = p_has_next

    return {"page": page, "total_pages": total_pages, "has_next": has_next}


def _load_product_cache() -> Dict[str, Any]:
    cache = _load_json_object(PRODUCT_CACHE_FILE)
    if not isinstance(cache.get("items"), list):
        cache["items"] = []
    return cache


def _load_product_source_config() -> Dict[str, Any]:
    cfg = _load_json_object(PRODUCT_API_CONFIG_FILE)
    if isinstance(cfg, dict) and cfg:
        return cfg
    # Backward-compatible fallback to the older file.
    legacy = _load_json_object(PRODUCT_SOURCE_FILE)
    if isinstance(legacy, dict) and legacy:
        try:
            PRODUCT_API_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            PRODUCT_API_CONFIG_FILE.write_text(json.dumps(legacy, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return legacy
    return {}


def _save_product_cache(items: List[Dict[str, str]], source_meta: Optional[Dict[str, Any]] = None):
    PRODUCT_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "items": items,
        "source_meta": source_meta or {},
    }
    PRODUCT_CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_planning_board() -> Dict[str, Any]:
    raw = _load_json_object(PLANNING_BOARD_FILE)
    lanes = raw.get("lanes") if isinstance(raw.get("lanes"), dict) else {}
    clean_lanes: Dict[str, List[Dict[str, Any]]] = {}
    for lane, cards in lanes.items():
        lane_key = str(lane or "").strip() or "BACKLOG"
        if not isinstance(cards, list):
            continue
        clean_lanes[lane_key] = [dict(c) for c in cards if isinstance(c, dict)]
    clean_lanes.setdefault("BACKLOG", [])
    return {
        "lanes": clean_lanes,
        "updated_at_utc": str(raw.get("updated_at_utc") or ""),
    }


def save_planning_board(board: Dict[str, Any]) -> Dict[str, Any]:
    lanes = board.get("lanes") if isinstance(board.get("lanes"), dict) else {}
    clean: Dict[str, List[Dict[str, Any]]] = {}
    for lane, cards in lanes.items():
        lane_key = str(lane or "").strip() or "BACKLOG"
        if not isinstance(cards, list):
            continue
        clean[lane_key] = [dict(c) for c in cards if isinstance(c, dict)]
    clean.setdefault("BACKLOG", [])
    payload = {
        "lanes": clean,
        "updated_at_utc": utc_now().isoformat(),
    }
    PLANNING_BOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    PLANNING_BOARD_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _planning_extract_job_record(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if isinstance(data.get("job"), dict):
        return data.get("job") or {}
    if isinstance(payload.get("job"), dict):
        return payload.get("job") or {}
    return data if isinstance(data, dict) else {}


def _planning_job_card_from_payload(identifier: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    job = _planning_extract_job_record(payload)
    details = data.get("job_details") if isinstance(data, dict) and isinstance(data.get("job_details"), dict) else {}
    parts = data.get("parts") if isinstance(data, dict) and isinstance(data.get("parts"), list) else []
    ref_no = str(job.get("ref_no") or job.get("reference_no") or job.get("job_no") or "").strip()
    job_id = str(job.get("id") or job.get("job_id") or identifier or "").strip()
    product_id = str(details.get("product_id") or job.get("product_id") or "").strip()
    product_meta = _lookup_product_meta(product_id) if product_id else {"id": "", "name": "", "sku": ""}
    return {
        "id": f"plan-{re.sub(r'[^A-Za-z0-9_-]+', '-', job_id or str(identifier or 'job')).strip('-') or int(time.time())}",
        "job_id": job_id,
        "job_ref": ref_no or job_id,
        "job_name": ref_no or job_id,
        "product_id": product_id,
        "product_name": str(product_meta.get("name") or details.get("product_name") or job.get("product_name") or "").strip(),
        "product_sku": str(product_meta.get("sku") or details.get("product_sku") or job.get("product_sku") or "").strip(),
        "mold": str(details.get("mold") or details.get("mold_no") or "").strip(),
        "color": str(details.get("color") or "").strip(),
        "std_cycle_time": str(details.get("std_cycle_time") or details.get("cycle_time") or "").strip(),
        "qty_per_shift": str(details.get("qty_per_shift") or "").strip(),
        "request_qty": str(job.get("request_qty") or job.get("qty") or "").strip(),
        "parts_count": len(parts),
        "source": "BMS",
        "raw_payload": payload,
        "created_at_utc": utc_now().isoformat(),
    }


def fetch_planning_job_from_bms(identifier: str) -> Dict[str, Any]:
    raw_id = str(identifier or "").strip()
    m_job_url = re.search(r"/v1/jobs/(\d+)\s*$", raw_id, flags=re.IGNORECASE)
    job_id = (m_job_url.group(1) if m_job_url else raw_id).strip()
    if not job_id:
        raise ValueError("job_id is required")
    cfg = _load_product_source_config()
    bms = cfg.get("bms") if isinstance(cfg.get("bms"), dict) else {}
    base_url = str(bms.get("base_url", "")).strip().rstrip("/")
    username = str(bms.get("username") or bms.get("user") or "").strip()
    password = str(bms.get("password") or "").strip()
    ttl_seconds = int(bms.get("ttl_seconds", 604800) or 604800)
    force_new_token = bool(bms.get("force_new_token", True))
    if not (base_url and username and password):
        raise RuntimeError("BMS config is missing base_url, username, or password")

    req_auth = urllib_request.Request(
        url=f"{base_url}/auth/login",
        data=json.dumps({
            "identity": username,
            "password": password,
            "ttlSeconds": ttl_seconds,
            "forceNewToken": force_new_token,
        }).encode("utf-8"),
        method="POST",
    )
    req_auth.add_header("Content-Type", "application/json")
    req_auth.add_header("Accept", "application/json")
    with urllib_request.urlopen(req_auth, timeout=12) as resp:
        auth_parsed = json.loads(resp.read().decode("utf-8", errors="ignore"))
    token = str(((auth_parsed or {}).get("data") or {}).get("token") or "").strip()
    if not token:
        raise RuntimeError("BMS login did not return a token")

    req_job = urllib_request.Request(url=f"{base_url}/jobs/{job_id}", method="GET")
    req_job.add_header("Authorization", f"Bearer {token}")
    req_job.add_header("Accept", "application/json")
    with urllib_request.urlopen(req_job, timeout=12) as resp:
        parsed = json.loads(resp.read().decode("utf-8", errors="ignore"))
    if not isinstance(parsed, dict):
        raise RuntimeError("BMS job response is invalid")
    return _planning_job_card_from_payload(job_id, parsed)


def _fetch_products_from_source() -> List[Dict[str, str]]:
    cfg = _load_product_source_config()
    if not cfg:
        return []

    # Simple BMS config shape:
    # {
    #   "bms": {
    #     "base_url": ".../IMS/v1",
    #     "username": "...",
    #     "password": "...",
    #     "ttl_seconds": 604800,
    #     "force_new_token": true
    #   }
    # }
    if isinstance(cfg.get("bms"), dict):
        bms = cfg["bms"]
        base_url = str(bms.get("base_url", "")).strip().rstrip("/")
        username = str(bms.get("username", "")).strip()
        password = str(bms.get("password", "")).strip()
        ttl_seconds = int(bms.get("ttl_seconds", 604800) or 604800)
        force_new_token = bool(bms.get("force_new_token", True))
        if not (base_url and username and password):
            return []

        auth_url = f"{base_url}/auth/login"
        auth_body = {
            "identity": username,
            "password": password,
            "ttlSeconds": ttl_seconds,
            "forceNewToken": force_new_token,
        }
        req_auth = urllib_request.Request(
            url=auth_url,
            data=json.dumps(auth_body).encode("utf-8"),
            method="POST",
        )
        req_auth.add_header("Content-Type", "application/json")
        with urllib_request.urlopen(req_auth, timeout=12) as resp:
            auth_raw = resp.read().decode("utf-8", errors="ignore")
        try:
            auth_parsed = json.loads(auth_raw)
        except Exception:
            return []
        token = str(((auth_parsed or {}).get("data") or {}).get("token") or "").strip()
        if not token:
            return []

        all_items: List[Dict[str, str]] = []
        seen_ids = set()
        per_page = int(bms.get("per_page", 1000) or 1000)
        max_pages = int(bms.get("max_pages", 500) or 500)
        page = 1

        while page <= max_pages:
            products_url = f"{base_url}/products?{urlencode({'page': page, 'perPage': per_page, 'includeInactive': 0})}"
            req_prod = urllib_request.Request(url=products_url, method="GET")
            req_prod.add_header("Authorization", f"Bearer {token}")
            with urllib_request.urlopen(req_prod, timeout=12) as resp:
                prod_raw = resp.read().decode("utf-8", errors="ignore")
            try:
                prod_parsed = json.loads(prod_raw)
            except Exception:
                break

            page_items = _extract_products_from_payload(prod_parsed)
            if page_items:
                for it in page_items:
                    pid = str(it.get("id", "")).strip()
                    if not pid:
                        continue
                    if pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    all_items.append(it)

            page_info = _extract_pagination(prod_parsed)
            total_pages = page_info.get("total_pages")
            has_next = page_info.get("has_next")

            if isinstance(total_pages, int) and total_pages > 0 and page >= total_pages:
                break
            if has_next is False:
                break
            if not page_items:
                break
            page += 1

        return all_items

    # Preferred two-step auth + products flow.
    # {
    #   "auth": {... "token_path": "data.token" ...},
    #   "products": {... "headers": {"Authorization":"Bearer {token}"} ...}
    # }
    if isinstance(cfg.get("auth"), dict) and isinstance(cfg.get("products"), dict):
        auth = cfg["auth"]
        prod = cfg["products"]

        auth_url = str(auth.get("url", "")).strip()
        auth_method = str(auth.get("method", "POST")).strip().upper()
        auth_headers = auth.get("headers") if isinstance(auth.get("headers"), dict) else {}
        auth_body = auth.get("body")
        token_path = str(auth.get("token_path", "data.token")).strip() or "data.token"
        if not auth_url:
            return []

        auth_data = None
        if isinstance(auth_body, (dict, list)):
            auth_data = json.dumps(auth_body).encode("utf-8")
            if "Content-Type" not in auth_headers:
                auth_headers["Content-Type"] = "application/json"
        elif auth_body is not None:
            auth_data = str(auth_body).encode("utf-8")

        req_auth = urllib_request.Request(url=auth_url, data=auth_data, method=auth_method)
        for k, v in auth_headers.items():
            req_auth.add_header(str(k), str(v))
        with urllib_request.urlopen(req_auth, timeout=12) as resp:
            auth_raw = resp.read().decode("utf-8", errors="ignore")
        try:
            auth_parsed = json.loads(auth_raw)
        except Exception:
            return []

        token_obj: Any = auth_parsed
        for seg in token_path.split("."):
            if isinstance(token_obj, dict):
                token_obj = token_obj.get(seg)
            else:
                token_obj = None
                break
        token = str(token_obj or "").strip()
        if not token:
            return []

        prod_url = str(prod.get("url", "")).strip()
        prod_method = str(prod.get("method", "GET")).strip().upper()
        prod_headers = prod.get("headers") if isinstance(prod.get("headers"), dict) else {}
        prod_body = prod.get("body")
        prod_params = prod.get("params") if isinstance(prod.get("params"), dict) else {}
        if not prod_url:
            return []

        if prod_params:
            sep = "&" if "?" in prod_url else "?"
            prod_url = f"{prod_url}{sep}{urlencode(prod_params)}"

        # Replace token placeholders in headers/body.
        replaced_headers = {}
        for k, v in prod_headers.items():
            replaced_headers[str(k)] = str(v).replace("{token}", token)

        prod_data = None
        if isinstance(prod_body, (dict, list)):
            body_text = json.dumps(prod_body).replace("{token}", token)
            prod_data = body_text.encode("utf-8")
            if "Content-Type" not in replaced_headers:
                replaced_headers["Content-Type"] = "application/json"
        elif prod_body is not None:
            prod_data = str(prod_body).replace("{token}", token).encode("utf-8")

        req_prod = urllib_request.Request(url=prod_url, data=prod_data, method=prod_method)
        for k, v in replaced_headers.items():
            req_prod.add_header(str(k), str(v))
        with urllib_request.urlopen(req_prod, timeout=12) as resp:
            prod_raw = resp.read().decode("utf-8", errors="ignore")
        try:
            prod_parsed = json.loads(prod_raw)
        except Exception:
            return []
        return _extract_products_from_payload(prod_parsed)

    url = str(cfg.get("url", "")).strip()
    method = str(cfg.get("method", "POST")).strip().upper()
    headers = cfg.get("headers") if isinstance(cfg.get("headers"), dict) else {}
    body = cfg.get("body")

    if not url and isinstance(cfg.get("curl"), str):
        curl = cfg["curl"]
        m_url = re.search(r"curl\s+['\"]([^'\"]+)['\"]", curl)
        if m_url:
            url = m_url.group(1).strip()
        m_data = re.search(r"--data(?:-raw)?\s+['\"](.+?)['\"]", curl)
        if m_data and body is None:
            body = m_data.group(1)
        if "-X GET" in curl.upper():
            method = "GET"
        for hm in re.finditer(r"-H\s+['\"]([^:'\"]+):\s*([^'\"]+)['\"]", curl):
            headers[hm.group(1).strip()] = hm.group(2).strip()

    if not url:
        return []

    payload_bytes = None
    if body is not None:
        if isinstance(body, (dict, list)):
            payload_bytes = json.dumps(body).encode("utf-8")
            if "Content-Type" not in headers:
                headers["Content-Type"] = "application/json"
        else:
            payload_bytes = str(body).encode("utf-8")

    req = urllib_request.Request(url=url, data=payload_bytes, method=method)
    for k, v in headers.items():
        req.add_header(str(k), str(v))
    with urllib_request.urlopen(req, timeout=12) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    return _extract_products_from_payload(parsed)


def _bms_login_token(bms: Dict[str, Any]) -> str:
    base_url = str(bms.get("base_url", "")).strip().rstrip("/")
    username = str(bms.get("username") or bms.get("user") or "").strip()
    password = str(bms.get("password") or "").strip()
    ttl_seconds = int(bms.get("ttl_seconds", 604800) or 604800)
    force_new_token = bool(bms.get("force_new_token", True))
    if not (base_url and username and password):
        raise RuntimeError("BMS config is missing base_url, username, or password")
    auth_url = f"{base_url}/auth/login"
    auth_variants = [
        {"identity": username, "password": password, "ttlSeconds": ttl_seconds, "forceNewToken": force_new_token},
        {"username": username, "password": password},
    ]
    last_error: Optional[Exception] = None
    auth_parsed: Dict[str, Any] = {}
    for auth_body in auth_variants:
        req_auth = urllib_request.Request(
            url=auth_url,
            data=json.dumps(auth_body).encode("utf-8"),
            method="POST",
        )
        req_auth.add_header("Content-Type", "application/json")
        req_auth.add_header("Accept", "application/json")
        try:
            with urllib_request.urlopen(req_auth, timeout=12) as resp:
                auth_parsed = json.loads(resp.read().decode("utf-8", errors="ignore"))
            break
        except Exception as e:
            last_error = e
            auth_parsed = {}
    if not auth_parsed and last_error is not None:
        raise last_error
    token = str(
        auth_parsed.get("access_token")
        or auth_parsed.get("token")
        or ((auth_parsed.get("data") or {}).get("access_token") if isinstance(auth_parsed.get("data"), dict) else "")
        or ((auth_parsed.get("data") or {}).get("token") if isinstance(auth_parsed.get("data"), dict) else "")
        or ""
    ).strip()
    if not token:
        raise RuntimeError("BMS login did not return a bearer token")
    return token


def _extract_rows_from_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("inventory", "products", "data", "items", "result", "rows"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            nested = _extract_rows_from_payload(value)
            if nested:
                return nested
    return []


def _parse_stock_qty(row: Dict[str, Any]) -> float:
    for key in (
        "qty", "quantity", "stock", "stocks", "available", "available_qty",
        "available_quantity", "on_hand", "onhand", "balance", "total_stock",
        "warehouse_stock", "current_stock",
    ):
        if key in row:
            try:
                return float(row.get(key) or 0)
            except Exception:
                return 0.0
    return 0.0


def _stock_qty_source(row: Dict[str, Any]) -> str:
    for key in (
        "qty", "quantity", "stock", "stocks", "available", "available_qty",
        "available_quantity", "on_hand", "onhand", "balance", "total_stock",
        "warehouse_stock", "current_stock",
    ):
        if key in row:
            return key
    return ""


def _product_key_candidates(row: Dict[str, Any]) -> List[str]:
    keys = []
    for key in ("product_id", "productId", "id", "product", "item_id", "itemId", "sku", "product_sku", "code"):
        value = str(row.get(key) or "").strip()
        if value:
            keys.append(value)
    return keys


def _fetch_low_stock_recommendations(threshold: float = 100.0, force_refresh: bool = False) -> Dict[str, Any]:
    cache = _load_json_object(LOW_STOCK_CACHE_FILE)
    saved_at = str(cache.get("saved_at_utc") or "")
    try:
        cache_age = (utc_now() - datetime.fromisoformat(saved_at)).total_seconds() if saved_at else 999999
    except Exception:
        cache_age = 999999
    if not force_refresh and isinstance(cache.get("items"), list) and cache_age < 300 and float(cache.get("threshold", threshold) or threshold) == float(threshold):
        return {"items": cache.get("items") or [], "from_cache": True, "saved_at_utc": saved_at, "error": ""}

    cfg = _load_product_source_config()
    bms = cfg.get("bms") if isinstance(cfg.get("bms"), dict) else {}
    base_url = str(bms.get("base_url", "")).strip().rstrip("/")
    if not base_url:
        return {"items": cache.get("items") or [], "from_cache": True, "saved_at_utc": saved_at, "error": "BMS base_url is not configured."}

    token = _bms_login_token(bms)
    warehouse_ids = bms.get("inventory_warehouse_ids")
    if not isinstance(warehouse_ids, list) or not warehouse_ids:
        warehouse_ids = [3, 5, 14, 18, 2]
    warehouse_names = {
        "3": "Dock 1",
        "5": "Dock 2",
        "14": "Dock 3",
        "18": "C5",
        "2": "6116",
    }
    products = get_products(force_refresh=False).get("items") or []
    by_id: Dict[str, Dict[str, Any]] = {}
    by_sku: Dict[str, Dict[str, Any]] = {}
    for product in products:
        if not isinstance(product, dict):
            continue
        pid = str(product.get("id") or product.get("product_id") or "").strip()
        sku = str(product.get("sku") or product.get("product_sku") or "").strip()
        if pid:
            by_id[pid] = product
        if sku:
            by_sku[sku] = product

    stock_by_key: Dict[str, Dict[str, Any]] = {}
    for product in products:
        if not isinstance(product, dict):
            continue
        pid = str(product.get("id") or product.get("product_id") or "").strip()
        sku = str(product.get("sku") or product.get("product_sku") or "").strip()
        if not (pid or sku):
            continue
        key = pid or sku
        stock_by_key[key] = {
            "product_id": pid,
            "sku": sku,
            "name": str(product.get("name") or product.get("product_name") or "").strip(),
            "tonnage": str(product.get("tonnage") or product.get("machine_tons") or product.get("tons") or "").strip(),
            "unit": "",
            "qty_source": "stock",
            "total_stock": 0.0,
            "warehouses": {},
        }
    for wh in warehouse_ids:
        wh_id = str(wh).strip()
        if not wh_id:
            continue
        req_inv = urllib_request.Request(url=f"{base_url}/inventory/{quote(wh_id)}", method="GET")
        req_inv.add_header("Authorization", f"Bearer {token}")
        req_inv.add_header("Accept", "application/json")
        with urllib_request.urlopen(req_inv, timeout=20) as resp:
            parsed = json.loads(resp.read().decode("utf-8", errors="ignore"))
        rows = _extract_rows_from_payload(parsed)
        for inv in rows:
            qty = _parse_stock_qty(inv)
            qty_source = _stock_qty_source(inv)
            unit = str(inv.get("unit") or inv.get("uom") or inv.get("unit_name") or "").strip()
            candidates = _product_key_candidates(inv)
            product = None
            key = ""
            for cand in candidates:
                if cand in by_id:
                    product = by_id[cand]
                    key = str(product.get("id") or cand)
                    break
                if cand in by_sku:
                    product = by_sku[cand]
                    key = str(product.get("id") or cand)
                    break
            if product is None:
                pid = str(inv.get("product_id") or inv.get("productId") or inv.get("id") or "").strip()
                sku = str(inv.get("sku") or inv.get("product_sku") or inv.get("code") or "").strip()
                name = str(inv.get("name") or inv.get("product_name") or inv.get("productName") or "").strip()
                if not (pid or sku):
                    continue
                tonnage = str(inv.get("tonnage") or inv.get("machine_tons") or inv.get("tons") or inv.get("clamping_force") or "").strip()
                product = {"id": pid, "sku": sku, "name": name, "tonnage": tonnage}
                key = pid or sku
            entry = stock_by_key.setdefault(key, {
                "product_id": str(product.get("id") or ""),
                "sku": str(product.get("sku") or ""),
                "name": str(product.get("name") or product.get("product_name") or ""),
                "tonnage": str(product.get("tonnage") or product.get("machine_tons") or product.get("tons") or ""),
                "unit": unit,
                "qty_source": qty_source,
                "total_stock": 0.0,
                "warehouses": {},
            })
            if unit and not entry.get("unit"):
                entry["unit"] = unit
            if qty_source and not entry.get("qty_source"):
                entry["qty_source"] = qty_source
            entry["total_stock"] = float(entry.get("total_stock") or 0) + qty
            entry["warehouses"][wh_id] = float(entry["warehouses"].get(wh_id) or 0) + qty

    items = []
    for entry in stock_by_key.values():
        total = float(entry.get("total_stock") or 0)
        if total > float(threshold):
            continue
        wh_parts = []
        for wh_id in [str(x) for x in warehouse_ids]:
            wh_parts.append({
                "warehouse_id": wh_id,
                "warehouse_name": warehouse_names.get(wh_id, wh_id),
                "qty": entry.get("warehouses", {}).get(wh_id, 0),
                "unit": entry.get("unit") or "",
            })
        items.append({
            "product_id": entry.get("product_id") or "",
            "sku": entry.get("sku") or "",
            "name": entry.get("name") or "",
            "tonnage": entry.get("tonnage") or "",
            "total_stock": int(total) if total.is_integer() else round(total, 2),
            "unit": entry.get("unit") or "",
            "qty_source": entry.get("qty_source") or "",
            "threshold": threshold,
            "warehouses": wh_parts,
        })
    items.sort(key=lambda x: (float(x.get("total_stock") or 0), str(x.get("sku") or x.get("product_id") or "")))
    payload = {
        "saved_at_utc": utc_now().isoformat(),
        "threshold": threshold,
        "items": items,
    }
    _save_json_list(LOW_STOCK_CACHE_FILE, payload["items"])
    try:
        LOW_STOCK_CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[JSON] Failed to save low stock recommendations: {e}")
    return {"items": payload["items"], "from_cache": False, "saved_at_utc": payload["saved_at_utc"], "error": ""}


def get_products(force_refresh: bool = False) -> Dict[str, Any]:
    cache = _load_product_cache()
    cached_items = cache.get("items") if isinstance(cache.get("items"), list) else []
    if cached_items and not force_refresh:
        has_any_sku = any(str((it or {}).get("sku", "")).strip() for it in cached_items if isinstance(it, dict))
        if has_any_sku:
            return {"items": cached_items, "from_cache": True, "updated": False, "error": ""}
        try:
            fetched_upgrade = _fetch_products_from_source()
            if fetched_upgrade:
                _save_product_cache(
                    fetched_upgrade,
                    {"source_file": str(PRODUCT_API_CONFIG_FILE), "cache_upgrade": True},
                )
                return {"items": fetched_upgrade, "from_cache": False, "updated": True, "error": ""}
        except Exception:
            pass
        return {"items": cached_items, "from_cache": True, "updated": False, "error": ""}

    fetch_error = ""
    try:
        fetched = _fetch_products_from_source()
    except Exception as e:
        fetched = []
        fetch_error = str(e)
    if fetched:
        old_set = {(str(x.get("id", "")), str(x.get("name", ""))) for x in cached_items if isinstance(x, dict)}
        new_set = {(str(x.get("id", "")), str(x.get("name", ""))) for x in fetched}
        updated = old_set != new_set
        _save_product_cache(fetched, {"source_file": str(PRODUCT_API_CONFIG_FILE)})
        return {"items": fetched, "from_cache": False, "updated": updated, "error": ""}

    return {"items": cached_items, "from_cache": True, "updated": False, "error": fetch_error}

_ensure_sql_schema()
FINISHED_JOBS: List[Dict[str, Any]] = load_finished_jobs()
ARCHIVED_JOBS: List[Dict[str, Any]] = load_archived_jobs()
PROFILES: List[Dict[str, Any]] = load_profiles()
PLANNING_BOARD: Dict[str, Any] = load_planning_board()
MACHINE_STATUS_OVERRIDES = load_machine_status_overrides()
MACHINE_STATUS_ARCHIVE = load_machine_status_archive()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def prune_dead_sessions():
    """
    Keep sessions so dashboard can show stale machines as DISCONNECTED.
    (No hard delete on heartbeat timeout.)
    """
    return


async def broadcast_state():
    refresh_active_sessions_from_file()
    payload = {
        "type": "STATE",
        "active_ttl_seconds": ACTIVE_TTL_SECONDS,
        "sessions": [s.to_dict() for s in SESSIONS.values()],
        "daily_roles": get_today_role_assignments(),
        "maintenance_profiles": [
            dict(p) for p in PROFILES
            if isinstance(p, dict) and _normalize_company_role(p.get("company_role") or p.get("role") or "") == "Maintenance"
        ],
        "job_queue": _build_job_queue_rows(),
        "machine_status_overrides": MACHINE_STATUS_OVERRIDES,
        "machine_status_archive": MACHINE_STATUS_ARCHIVE,
        "planning_board": PLANNING_BOARD,
        "finished_jobs": FINISHED_JOBS,
        "archived_jobs": ARCHIVED_JOBS,
        "server_time_utc": utc_now().isoformat(),
    }
    living = []
    for ws in WS_CLIENTS:
        try:
            await ws.send_json(payload)
            living.append(ws)
        except Exception:
            pass
    WS_CLIENTS[:] = living


async def _state_tick_loop():
    while True:
        try:
            await broadcast_state()
        except Exception:
            pass
        await asyncio.sleep(STATE_TICK_SECONDS)


DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Machine Status & Analytics</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; }
    html, body { min-height: 100%; margin: 0; }
    body { font-family: "Poppins", sans-serif; background: #f8f8f8; color: #333; display: flex; flex-direction: column; overflow-x: hidden; }
    .diagnostics { padding: 8px clamp(8px, 1.2vw, 14px); background: #e9ecef; border-bottom: 1px solid #d9d9d9; display: grid; grid-template-columns: repeat(4, 48px) repeat(4, minmax(140px, 1fr)); gap: 8px; align-items: stretch; }
    .server-menu-btn { width: 48px; min-width: 48px; border: 1px solid #d4dae4; border-radius: 11px; background: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: transform .12s ease, box-shadow .16s ease, background-color .16s ease; }
    .server-menu-btn:hover { transform: translateY(-1px); box-shadow: 0 8px 18px rgba(15,23,42,0.08); background: #fbfcfe; }
    .server-menu-btn:active { transform: translateY(0) scale(0.985); }
    .server-menu-icon { width: 20px; height: 14px; position: relative; }
    .server-menu-icon span { display: block; position: absolute; left: 0; right: 0; height: 2px; background: #334155; border-radius: 999px; }
    .server-menu-icon span:nth-child(1){ top: 0; }
    .server-menu-icon span:nth-child(2){ top: 6px; }
    .server-menu-icon span:nth-child(3){ top: 12px; }
    .menu-ico-img { width: 20px; height: 20px; display: block; object-fit: contain; }
    .person-menu-icon { width: 20px; height: 20px; position: relative; }
    .person-menu-icon::before { content: ""; position: absolute; top: 1px; left: 5px; width: 10px; height: 10px; border: 2px solid #334155; border-radius: 50%; box-sizing: border-box; }
    .person-menu-icon::after { content: ""; position: absolute; bottom: 1px; left: 2px; width: 16px; height: 8px; border: 2px solid #334155; border-top-left-radius: 10px; border-top-right-radius: 10px; border-bottom: none; box-sizing: border-box; }
    .person-menu-icon.with-plus::marker { content: ""; }
    .person-plus-badge { position: absolute; right: -2px; bottom: -2px; width: 10px; height: 10px; border-radius: 50%; background: #2563eb; color: #fff; font-size: 9px; line-height: 1; display:flex; align-items:center; justify-content:center; font-weight: 700; }
    .diag-item { min-width:0; background: #fff; border-radius: 10px; padding: 6px 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); font-size: 12px; line-height: 1.15; }
    .diag-item .value { font-weight: 700; margin-top: 4px; line-height: 1.12; }
    .diag-item, .diag-item .value { overflow-wrap:anywhere; }
    .status-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
    .connected { background: #4CAF50; }
    .disconnected { background: #f44336; }
    .main-tabs { display: flex; gap: 10px; padding: 14px clamp(10px, 1.6vw, 20px) 10px; flex-wrap: wrap; }
    .main-tab-button { background: #e1e5ef; border: none; border-radius: 20px; padding: 8px 18px; font-weight: 600; cursor: pointer; transition: transform .12s ease, box-shadow .16s ease, background-color .16s ease; }
    .main-tab-button:hover { transform: translateY(-1px); box-shadow: 0 6px 14px rgba(15,23,42,0.10); }
    .main-tab-button:active { transform: translateY(0) scale(0.985); }
    .main-tab-button.active { background: #1f8ef1; color: #fff; }
    .main-tab-content { display: none; padding: 0 clamp(10px, 1.6vw, 20px) clamp(12px, 1.6vw, 20px); min-width:0; }
    .main-tab-content.active { display: block; }
    .sub-tabs { display:flex; gap:8px; margin-top:12px; margin-bottom:12px; flex-wrap:wrap; }
    .sub-tab-button { background:#fff; border:1px solid #cbd5e1; border-radius:999px; padding:8px 14px; font-weight:700; color:#334155; cursor:pointer; transition: transform .12s ease, box-shadow .16s ease, background-color .16s ease; }
    .sub-tab-button:hover { transform: translateY(-1px); box-shadow: 0 6px 14px rgba(15,23,42,0.08); }
    .sub-tab-button.active { background:#1f8ef1; color:#fff; border-color:#1f8ef1; }
    .sub-tab-content { display:none; }
    .sub-tab-content.active { display:block; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(clamp(150px, 11vw, 190px), 1fr)); gap: clamp(10px, 1.2vw, 18px); }
    #machineGrid { grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); align-items:stretch; perspective:1200px; }
    .card { min-width:0; background: #fff; border-radius: 12px; padding: clamp(10px, 1vw, 16px); border: 2px solid transparent; box-shadow: 0 2px 8px rgba(0,0,0,0.08); cursor: pointer; transition: transform .12s ease, box-shadow .12s ease; }
    .card:hover { transform: translateY(-2px); box-shadow: 0 8px 18px rgba(0,0,0,0.12); }
    .card.active { border-color: #4CAF50; animation: cardPulseGreen 1.5s ease-in-out infinite; }
    .card.disconnected { border-color: #f44336; }
    .card.maintenance { border-color: #FF9800; animation: cardPulseOrange 1.5s ease-in-out infinite; }
    .card h3 { margin: 0 0 10px; font-size: clamp(.9rem, .9vw, 1.05rem); border-bottom: 1px solid #eee; padding-bottom: 8px; overflow-wrap:anywhere; }
    .card p { margin: 6px 0; font-size: 0.9rem; overflow-wrap:break-word; word-break:normal; }
    #machineGrid .card { position:relative; display:grid; grid-template-columns:minmax(0,1fr); gap:10px; min-height:0; padding:12px; border:1px solid #d8e2ef; border-top:4px solid #94a3b8; border-radius:10px; background:#fff; box-shadow:0 8px 20px rgba(15,23,42,.06); overflow:hidden; transform-style:preserve-3d; backface-visibility:hidden; will-change:transform, box-shadow; }
    #machineGrid .card:hover { transform:translateY(-1px); box-shadow:0 14px 28px rgba(15,23,42,.10); }
    #machineGrid .card.active { border-color:#bbf7d0; border-top-color:#16a34a; animation:none; background:#fbfffd; }
    #machineGrid .card.disconnected { border-color:#fecaca; border-top-color:#ef4444; animation:none; background:#fffafa; }
    #machineGrid .card.maintenance { border-color:#fed7aa; border-top-color:#f59e0b; animation:none; background:#fffdf8; }
    .machine-card-head { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:10px; align-items:center; }
    .machine-card-title { min-width:0; display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; }
    #machineGrid .card .machine-card-title h3 { margin:0; padding:0; border:0; color:#0f172a; font-size:1.16rem; line-height:1.15; }
    .machine-card-code { display:none; }
    .machine-status-badge { flex:0 0 auto; display:inline-flex; align-items:center; gap:7px; border-radius:6px; padding:6px 9px; font-size:.74rem; line-height:1; font-weight:900; letter-spacing:.04em; text-transform:uppercase; background:#f1f5f9; color:#475569; border:1px solid #e2e8f0; }
    .machine-status-badge::before { content:""; flex:0 0 auto; width:9px; height:9px; border-radius:999px; background:#94a3b8; box-shadow:0 0 0 3px rgba(148,163,184,.16); }
    .machine-status-badge.active { background:#dcfce7; color:#047857; border-color:#86efac; }
    .machine-status-badge.disconnected { background:#fef2f2; color:#b91c1c; border-color:#fecaca; }
    .machine-status-badge.maintenance { background:#ffedd5; color:#b45309; border-color:#fed7aa; }
    .machine-status-badge.active::before { background:#22c55e; animation:statusBeatGreen 1.25s ease-in-out infinite; }
    .machine-status-badge.disconnected::before { background:#ef4444; animation:statusBeatRed 1.25s ease-in-out infinite; }
    .machine-status-badge.maintenance::before { background:#f59e0b; animation:statusBeatOrange 1.25s ease-in-out infinite; }
    .machine-job-block { padding:0 0 9px; border-bottom:1px solid #edf2f7; }
    .machine-job-name { color:#0f172a; font-size:1rem; line-height:1.3; font-weight:900; overflow-wrap:anywhere; }
    .machine-job-meta { margin-top:5px; display:grid; grid-template-columns:1fr 1fr; gap:4px 10px; color:#64748b; font-size:.86rem; line-height:1.3; }
    .machine-job-meta span { min-width:0; overflow-wrap:anywhere; }
    #machineGrid .card.linkage-flip-out { animation:linkageCardFlipOut .24s cubic-bezier(.45,0,.7,.2) forwards; transform-origin:center center; pointer-events:none; }
    #machineGrid .card.linkage-flip-in { animation:linkageCardFlipIn .34s cubic-bezier(.18,.82,.28,1) forwards; transform-origin:center center; pointer-events:none; }
    .machine-linkage-panel { display:grid; gap:7px; padding:9px 10px; border:1px solid #bfdbfe; border-radius:8px; background:#eff6ff; }
    .machine-linkage-top { display:flex; align-items:center; justify-content:space-between; gap:8px; }
    .machine-linkage-label { color:#1d4ed8; font-size:.68rem; line-height:1; font-weight:900; letter-spacing:.04em; text-transform:uppercase; }
    .machine-linkage-job { color:#0f172a; font-size:.92rem; line-height:1.2; font-weight:900; overflow-wrap:anywhere; }
    .machine-linkage-switch { flex:0 0 auto; border:1px solid #93c5fd; border-radius:7px; background:#fff; color:#1d4ed8; padding:5px 8px; font-size:.68rem; line-height:1; font-weight:900; letter-spacing:0; cursor:pointer; transition:transform .12s ease, box-shadow .14s ease, background-color .14s ease; }
    .machine-linkage-switch:hover { transform:translateY(-1px); box-shadow:0 6px 14px rgba(37,99,235,.14); background:#f8fbff; }
    .machine-linkage-switch:active { transform:translateY(0) scale(.98); }
    .machine-metrics { display:flex; flex-wrap:wrap; gap:6px; }
    .machine-metric { min-width:64px; flex:1 1 64px; border:1px solid #e2e8f0; border-radius:8px; background:#f8fafc; padding:6px 8px; }
    .machine-metric .k { color:#64748b; font-size:.72rem; font-weight:900; text-transform:uppercase; letter-spacing:.04em; }
    .machine-metric .v { margin-top:3px; color:#0f172a; font-size:1.08rem; line-height:1; font-weight:900; overflow-wrap:anywhere; }
    .machine-metric.good .v { color:#047857; }
    .machine-metric.bad .v { color:#b91c1c; }
    .machine-card-foot { margin-top:0; padding-top:8px; border-top:1px solid #edf2f7; color:#64748b; font-size:.8rem; line-height:1.4; display:grid; gap:2px; }
    #machineGrid .machine-linkage-flag { display:inline-flex; align-items:center; gap:8px; border:1px solid #bfdbfe; background:#eff6ff; color:#1d4ed8; border-radius:6px; padding:5px 6px 5px 8px; font-size:.64rem; font-weight:900; letter-spacing:.04em; width:max-content; max-width:100%; }
    .machine-notif-wrap { position:absolute; right:12px; bottom:12px; z-index:4; }
    .machine-notif-badge { width:30px; height:30px; border-radius:999px; border:1px solid #fdba74; background:#f59e0b; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:900; font-size:.78rem; box-shadow:0 0 0 3px rgba(245,158,11,.14), 0 8px 18px rgba(146,64,14,.20); cursor:help; }
    .panel { margin-top: 14px; background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
    .panel h3 { margin: 0 0 6px; }
    .muted { color: #666; font-size: 0.9rem; }
    .placeholder { border: 1px dashed #d9d9d9; border-radius: 10px; padding: 14px; color: #777; background: #fafafa; margin-top: 12px; }
    .table-wrap { margin-top: 12px; border: 1px solid #dbe4f0; border-radius: 12px; overflow: auto; background: #fff; }
    .data-table { width: 100%; border-collapse: collapse; min-width: 920px; }
    .data-table th, .data-table td { padding: 10px 12px; border-bottom: 1px solid #edf2f7; text-align: left; font-size: 0.86rem; vertical-align: top; }
    .data-table th { background: #f8fafc; color: #334155; font-weight: 700; position: sticky; top: 0; z-index: 1; }
    .data-table tr:hover td { background: #f8fbff; }
    .maintenance-shell { position:relative; overflow:hidden; background:linear-gradient(180deg, rgba(255,255,255,.98), rgba(246,248,252,.98)); border:1px solid #d8e2ef; border-radius:18px; padding:12px 12px 8px; }
    .maintenance-shell::before { content:""; position:absolute; inset:0; pointer-events:none; opacity:.22; background:linear-gradient(135deg, transparent 0 83%, rgba(148,163,184,.18) 83% 84%, transparent 84% 100%), radial-gradient(circle at 90% 16%, rgba(148,163,184,.28) 0 2px, transparent 2.5px), radial-gradient(circle at 84% 28%, rgba(148,163,184,.22) 0 3px, transparent 3.5px), radial-gradient(circle at 93% 36%, rgba(148,163,184,.18) 0 2px, transparent 2.5px); }
    .maintenance-topbar { position:relative; z-index:1; display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
    .maintenance-topbar h3 { margin:0; font-size:1.02rem; line-height:1.1; }
    .maintenance-date { font-size:.83rem; color:#334155; white-space:nowrap; text-align:right; }
    .maintenance-summary { position:relative; z-index:1; display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:12px; margin-top:12px; }
    .maintenance-metric { display:flex; align-items:center; gap:12px; min-height:86px; border:1px solid #cdd8e7; border-radius:12px; padding:14px 16px; box-shadow: inset 0 1px 0 rgba(255,255,255,.7); }
    .maintenance-metric.blue { background:linear-gradient(180deg, #e7f1fb, #dbeafe); }
    .maintenance-metric.green { background:linear-gradient(180deg, #e8f8eb, #dcfce7); }
    .maintenance-metric.amber { background:linear-gradient(180deg, #fff4e5, #ffedd5); }
    .maintenance-metric.red { background:linear-gradient(180deg, #feeaea, #fee2e2); }
    .maintenance-metric .icon { width:34px; height:34px; border-radius:10px; display:flex; align-items:center; justify-content:center; font-size:18px; font-weight:700; background:rgba(255,255,255,.5); color:#1e293b; flex:0 0 auto; }
    .maintenance-metric .k { font-size:.9rem; color:#0f172a; font-weight:700; }
    .maintenance-metric .v { font-size:1.95rem; line-height:1; font-weight:800; color:#0f172a; margin-top:2px; }
    .maintenance-metric .s { font-size:.83rem; color:#334155; margin-top:2px; }
    .maintenance-live-grid { position:relative; z-index:1; display:grid; grid-template-columns: 1fr; gap:10px; margin-top:12px; }
    .maintenance-section-title { margin:0; font-size:1rem; line-height:1.1; }
    .maintenance-list { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:12px; }
    .maintenance-person { display:grid; grid-template-columns: 96px minmax(0, 1.2fr) minmax(160px, .9fr); border:1px solid #d5deea; border-radius:12px; background:rgba(255,255,255,.94); overflow:hidden; box-shadow:0 8px 18px rgba(15,23,42,.06); }
    .maintenance-person.busy { border-color:#ecc896; }
    .maintenance-avatar-wrap { padding:10px; display:flex; align-items:center; justify-content:center; border-right:1px solid #e5ecf4; background:linear-gradient(180deg, #f8fafc, #eef2f7); }
    .maintenance-avatar { width:78px; height:78px; border-radius:10px; background:radial-gradient(circle at 50% 34%, #cbd5e1 0 11px, transparent 12px), radial-gradient(circle at 50% 74%, #cbd5e1 0 24px, transparent 25px), linear-gradient(180deg, #f8fafc, #e2e8f0); border:1px solid #cbd5e1; box-shadow: inset 0 1px 0 rgba(255,255,255,.7); }
    .maintenance-person-main { padding:10px 12px; min-width:0; }
    .maintenance-person-head { display:flex; align-items:flex-start; justify-content:space-between; gap:10px; }
    .maintenance-person .title { font-weight:800; color:#0f172a; font-size:1rem; }
    .maintenance-person .meta { color:#111827; font-size:.85rem; line-height:1.3; }
    .maintenance-person .submeta { color:#334155; font-size:.83rem; margin-top:6px; line-height:1.35; }
    .maintenance-badge { display:inline-flex; align-items:center; justify-content:center; min-width:86px; padding:4px 10px; border-radius:999px; font-size:.67rem; font-weight:800; letter-spacing:.03em; text-transform:uppercase; }
    .maintenance-badge.available { background:#dcfce7; color:#166534; }
    .maintenance-badge.busy { background:#ffedd5; color:#9a3412; }
    .maintenance-badge.waiting { background:#fee2e2; color:#b91c1c; }
    .maintenance-machine-grid { display:grid; grid-template-columns: 1fr; gap:6px; margin-top:8px; }
    .maintenance-machine { display:grid; grid-template-columns:minmax(0, 1fr) auto; align-items:center; gap:8px; padding:6px 10px; border:1px solid #d7dee8; border-radius:9px; background:#f8fafc; }
    .maintenance-machine.busy { background:#fff7ed; border-color:#fed7aa; }
    .maintenance-machine.waiting { background:#f8fafc; }
    .maintenance-machine-title { font-size:.84rem; color:#111827; }
    .maintenance-machine-time { font-size:.82rem; color:#111827; white-space:nowrap; }
    .maintenance-stats { padding:10px 12px; border-left:1px solid #e5ecf4; }
    .maintenance-stats-title { font-size:.9rem; font-weight:700; color:#0f172a; margin-bottom:8px; }
    .maintenance-stat-line { display:flex; align-items:center; gap:8px; font-size:.84rem; color:#111827; margin-bottom:7px; }
    .maintenance-stat-icon { width:18px; text-align:center; color:#0f172a; font-size:.92rem; }
    .maintenance-performance-panel { margin-top:10px; border-top:1px solid #dbe4f0; padding-top:10px; position:relative; z-index:1; }
    .maintenance-performance-title { margin:0; font-size:1rem; line-height:1.1; }
    .maintenance-performance-wrap { margin-top:10px; border:1px solid #dbe4f0; border-radius:0 0 12px 12px; overflow:auto; background:rgba(255,255,255,.92); }
    .maintenance-performance-wrap .data-table { min-width:760px; }
    #maintenanceTab { background:#eef3f8; border-radius:18px; padding:14px; }
    #maintenanceTab .maintenance-shell { position:relative; background:linear-gradient(180deg, #f8fbff 0%, #eef4fb 100%); border:1px solid #d4e0ec; border-radius:18px; padding:18px; box-shadow:0 18px 44px rgba(15,23,42,.10); }
    #maintenanceTab .maintenance-shell::before { content:""; position:absolute; inset:0 0 auto 0; height:120px; pointer-events:none; opacity:1; background:linear-gradient(135deg, rgba(14,165,233,.14), rgba(16,185,129,.10) 48%, rgba(245,158,11,.10)); }
    #maintenanceTab .maintenance-topbar { align-items:center; padding:2px 2px 10px; border-bottom:1px solid rgba(148,163,184,.22); }
    #maintenanceTab .maintenance-topbar h3 { font-size:1.28rem; font-weight:800; letter-spacing:0; color:#0f172a; }
    #maintenanceTab .maintenance-date { padding:8px 12px; border:1px solid #d2deea; border-radius:999px; background:rgba(255,255,255,.78); color:#475569; box-shadow:0 6px 18px rgba(15,23,42,.06); }
    #maintenanceTab .maintenance-summary { gap:14px; margin-top:16px; }
    #maintenanceTab .maintenance-metric { position:relative; display:grid; grid-template-columns:minmax(0,1fr) 44px; align-items:center; min-height:116px; border:1px solid rgba(203,213,225,.92); border-radius:14px; padding:16px; background:rgba(255,255,255,.86); box-shadow:0 12px 28px rgba(15,23,42,.08), inset 0 1px 0 rgba(255,255,255,.78); overflow:hidden; }
    #maintenanceTab .maintenance-metric::before { content:""; position:absolute; inset:0 auto 0 0; width:4px; background:#3b82f6; }
    #maintenanceTab .maintenance-metric.green::before { background:#10b981; }
    #maintenanceTab .maintenance-metric.amber::before { background:#f59e0b; }
    #maintenanceTab .maintenance-metric.red::before { background:#ef4444; }
    #maintenanceTab .maintenance-metric.blue { background:linear-gradient(180deg, rgba(255,255,255,.92), rgba(239,246,255,.88)); }
    #maintenanceTab .maintenance-metric.green { background:linear-gradient(180deg, rgba(255,255,255,.92), rgba(236,253,245,.88)); }
    #maintenanceTab .maintenance-metric.amber { background:linear-gradient(180deg, rgba(255,255,255,.92), rgba(255,251,235,.88)); }
    #maintenanceTab .maintenance-metric.red { background:linear-gradient(180deg, rgba(255,255,255,.92), rgba(254,242,242,.88)); }
    #maintenanceTab .maintenance-metric .icon { width:42px; height:42px; border-radius:12px; background:#eff6ff; color:#2563eb; font-size:0; }
    #maintenanceTab .maintenance-metric .icon::before { content:""; width:18px; height:18px; border-radius:6px; border:2px solid currentColor; display:block; }
    #maintenanceTab .maintenance-metric.green .icon { background:#ecfdf5; color:#059669; }
    #maintenanceTab .maintenance-metric.amber .icon { background:#fffbeb; color:#d97706; }
    #maintenanceTab .maintenance-metric.red .icon { background:#fef2f2; color:#dc2626; }
    #maintenanceTab .maintenance-metric .k { color:#475569; font-size:.8rem; font-weight:800; text-transform:uppercase; letter-spacing:.05em; }
    #maintenanceTab .maintenance-metric .v { color:#0f172a; font-size:2.15rem; line-height:1; font-weight:800; margin-top:8px; }
    #maintenanceTab .maintenance-metric .s { color:#64748b; font-size:.82rem; margin-top:8px; }
    #maintenanceTab .maintenance-live-grid { grid-template-columns:1fr; gap:14px; margin-top:16px; }
    #maintenanceTab .maintenance-section-title, #maintenanceTab .maintenance-performance-title { color:#0f172a; font-size:1.05rem; font-weight:800; }
    #maintenanceTab .maintenance-call-board { margin-top:12px; border:1px solid #d5e1ed; border-radius:10px; background:rgba(255,255,255,.92); box-shadow:0 8px 18px rgba(15,23,42,.06); padding:10px; }
    #maintenanceTab .maintenance-call-head { display:flex; align-items:flex-start; justify-content:space-between; gap:10px; margin-bottom:8px; }
    #maintenanceTab .maintenance-call-count { border:1px solid #fecaca; background:#fef2f2; color:#b91c1c; border-radius:999px; padding:4px 8px; font-size:.7rem; font-weight:900; white-space:nowrap; }
    #maintenanceTab .maintenance-call-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 220px), max-content)); gap:8px; align-items:start; }
    #maintenanceTab .maintenance-call-card { width:min(100%, 260px); border:1px solid #fed7aa; border-left:4px solid #f59e0b; border-radius:9px; background:#fffbeb; padding:8px 9px; display:grid; gap:5px; box-shadow:0 6px 14px rgba(146,64,14,.07); }
    #maintenanceTab .maintenance-call-card.active { border-color:#fdba74; background:#fff7ed; }
    #maintenanceTab .maintenance-call-top { display:flex; align-items:flex-start; justify-content:space-between; gap:6px; }
    #maintenanceTab .maintenance-call-machine { color:#0f172a; font-size:.9rem; font-weight:900; line-height:1.15; overflow-wrap:anywhere; }
    #maintenanceTab .maintenance-call-status { border-radius:999px; padding:3px 7px; font-size:.6rem; font-weight:900; background:#fee2e2; color:#b91c1c; white-space:nowrap; }
    #maintenanceTab .maintenance-call-status.active { background:#ffedd5; color:#b45309; }
    #maintenanceTab .maintenance-call-meta { color:#64748b; font-size:.7rem; line-height:1.25; overflow-wrap:anywhere; }
    #maintenanceTab .maintenance-call-reason { color:#7c2d12; font-size:.76rem; font-weight:900; line-height:1.2; overflow-wrap:anywhere; }
    #maintenanceTab .maintenance-call-timer { font-family:"Consolas","Courier New",monospace; color:#9a3412; font-size:.95rem; font-weight:900; }
    #maintenanceTab .maintenance-list { grid-template-columns:repeat(auto-fit, minmax(min(100%, 320px), 1fr)); gap:14px; margin-top:12px; }
    #maintenanceTab .maintenance-person { grid-template-columns:74px minmax(0,1fr) minmax(170px,.72fr); border:1px solid #d5e1ed; border-radius:14px; background:rgba(255,255,255,.92); box-shadow:0 12px 26px rgba(15,23,42,.07); }
    #maintenanceTab .maintenance-person.busy { border-color:#f6c37a; box-shadow:0 12px 28px rgba(217,119,6,.12); }
    #maintenanceTab .maintenance-avatar-wrap { padding:12px; background:linear-gradient(180deg, #f8fafc, #edf4fb); }
    #maintenanceTab .maintenance-avatar { width:50px; height:50px; border-radius:50%; background:radial-gradient(circle at 50% 33%, #f3c9ad 0 13px, transparent 14px), radial-gradient(circle at 50% 92%, #64748b 0 24px, transparent 25px), linear-gradient(135deg, #e0f2fe, #f8fafc); border:1px solid #cbd5e1; }
    #maintenanceTab .maintenance-person .title { color:#0f172a; font-size:1rem; font-weight:800; }
    #maintenanceTab .maintenance-person .meta, #maintenanceTab .maintenance-person .submeta { color:#64748b; }
    #maintenanceTab .maintenance-badge { min-width:0; border-radius:999px; padding:5px 9px; font-size:.68rem; letter-spacing:.02em; }
    #maintenanceTab .maintenance-badge.available { background:#dcfce7; color:#047857; }
    #maintenanceTab .maintenance-badge.busy { background:#ffedd5; color:#b45309; }
    #maintenanceTab .maintenance-badge.waiting { background:#fee2e2; color:#b91c1c; }
    #maintenanceTab .maintenance-machine { border-color:#dce6f1; border-radius:10px; background:#f8fafc; }
    #maintenanceTab .maintenance-machine.busy { background:#fff7ed; border-color:#fed7aa; }
    #maintenanceTab .maintenance-stats { background:#f8fafc; }
    #maintenanceTab .maintenance-stat-icon { width:18px; height:18px; border-radius:6px; background:#e0f2fe; color:#0284c7; font-size:0; display:inline-flex; align-items:center; justify-content:center; flex:0 0 auto; }
    #maintenanceTab .maintenance-stat-icon::before { content:""; width:7px; height:7px; border-radius:50%; background:currentColor; }
    #maintenanceTab .maintenance-performance-panel { margin-top:16px; border-top:0; padding-top:0; }
    #maintenanceTab .maintenance-performance-wrap { border:1px solid #d5e1ed; border-radius:14px; background:rgba(255,255,255,.92); box-shadow:0 12px 26px rgba(15,23,42,.07); }
    #maintenanceTab .maintenance-performance-wrap .data-table th { background:#f8fafc; color:#475569; }
    .planning-shell { background:linear-gradient(180deg, #f8fbff, #eef4fb); border:1px solid #d5e1ed; border-radius:18px; padding:16px; box-shadow:0 18px 44px rgba(15,23,42,.10); }
    .planning-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; flex-wrap:wrap; }
    .planning-title h3 { margin:0; color:#0f172a; font-size:1.22rem; }
    .planning-controls { display:grid; grid-template-columns:minmax(0, 360px) auto auto; gap:8px; align-items:center; }
    .planning-controls input { border:1px solid #cbd5e1; border-radius:10px; padding:10px 12px; font:inherit; background:#fff; color:#0f172a; }
    .planning-controls button { border:0; border-radius:10px; padding:10px 14px; font-weight:800; cursor:pointer; background:#2563eb; color:#fff; box-shadow:0 8px 18px rgba(37,99,235,.22); }
    .planning-controls button.secondary { background:#fff; color:#334155; border:1px solid #cbd5e1; box-shadow:none; }
    .planning-status { margin-top:10px; min-height:20px; color:#64748b; font-size:.85rem; }
    .planning-ops-summary { display:grid; grid-template-columns:repeat(5, minmax(140px,1fr)); gap:12px; margin-top:14px; }
    .planning-ops-metric { min-width:0; border-radius:14px; background:#111827; color:#fff; padding:13px 16px; box-shadow:0 12px 26px rgba(15,23,42,.14); }
    .planning-ops-metric.warn { background:#92400e; }
    .planning-ops-metric.good { background:#065f46; }
    .planning-ops-metric .k { color:#aeb8c8; font-size:.68rem; font-weight:900; letter-spacing:.06em; text-transform:uppercase; }
    .planning-ops-metric .v { margin-top:5px; color:#fff; font-size:1.55rem; line-height:1; font-weight:900; }
    .planning-ops-metric .s { margin-top:6px; color:#cbd5e1; font-size:.74rem; line-height:1.25; overflow-wrap:break-word; }
    .planning-board { display:grid; grid-template-columns:minmax(520px, 620px) minmax(0,1fr); gap:14px; margin-top:14px; }
    .planning-lane, .planning-running { border:1px solid #d5e1ed; border-radius:14px; background:rgba(255,255,255,.88); box-shadow:0 10px 24px rgba(15,23,42,.06); min-width:0; }
    .planning-lane.backlog { display:flex; flex-direction:column; height:620px; min-height:0; overflow:hidden; }
    .planning-left-grid { display:grid; grid-template-columns:1fr; gap:14px; min-width:0; align-items:stretch; height:100%; }
    .planning-lane-head { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:12px 12px 8px; border-bottom:1px solid #e2e8f0; }
    .planning-lane-title { font-weight:800; color:#0f172a; }
    .planning-lane-count { color:#64748b; font-size:.78rem; }
    .planning-lane-time { grid-column:1/-1; display:grid; gap:4px; margin-top:8px; color:#475569; font-size:.72rem; line-height:1.35; }
    .planning-lane-time span { display:block; overflow-wrap:break-word; }
    .planning-dropzone { min-height:140px; padding:10px; display:grid; gap:10px; align-content:start; }
    .planning-dropzone.drag-over { outline:2px dashed #2563eb; outline-offset:-8px; background:#eff6ff; }
    .planning-machine-grid { display:grid; grid-template-columns:1fr; gap:10px; align-content:start; max-height:620px; overflow-y:auto; padding-right:4px; }
    .planning-machine-grid .planning-lane { width:100%; }
    .planning-machine-grid .planning-lane-head { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:start; padding:10px 12px; }
    .planning-machine-grid .planning-lane-time { display:flex; flex-wrap:wrap; column-gap:12px; row-gap:3px; margin-top:5px; }
    .planning-machine-grid .planning-dropzone { min-height:112px; max-height:128px; overflow-x:auto; overflow-y:hidden; padding:8px 10px; gap:8px; grid-auto-flow:column; grid-template-rows:1fr; grid-auto-columns:260px; align-content:start; justify-content:start; }
    .planning-machine-grid .planning-dropzone > * { width:260px; min-width:260px; box-sizing:border-box; }
    .planning-machine-grid .planning-empty { border:0; background:transparent; padding:2px 0; }
    .planning-machine-grid .planning-card { padding:8px 10px; box-shadow:none; max-height:104px; overflow:hidden; }
    .planning-machine-grid .planning-job { font-size:.9rem; }
    .planning-machine-grid .planning-meta { margin-top:4px; font-size:.72rem; line-height:1.28; }
    .planning-machine-grid .planning-card-actions { margin-top:5px; }
    .planning-card { border:1px solid #dbe5ef; border-radius:12px; background:#fff; padding:11px; box-shadow:0 8px 18px rgba(15,23,42,.07); cursor:default; }
    .planning-card[draggable="true"] { cursor:default; }
    .planning-card:active { cursor:default; }
    .planning-card.live { cursor:default; border-color:#bbf7d0; background:#f0fdf4; }
    .planning-card.next-job { border-color:#bfdbfe; background:#eff6ff; }
    .planning-card.queue-job { border-color:#dbe5ef; background:#fff; }
    .planning-card-top { display:flex; align-items:flex-start; justify-content:space-between; gap:8px; min-width:0; }
    .planning-job { min-width:0; font-weight:900; color:#0f172a; overflow-wrap:break-word; word-break:normal; }
    .planning-chip { border-radius:999px; padding:3px 7px; font-size:.68rem; font-weight:800; background:#dbeafe; color:#1d4ed8; white-space:nowrap; }
    .planning-chip.ongoing { background:#dcfce7; color:#047857; }
    .planning-chip.next { background:#dbeafe; color:#1d4ed8; }
    .planning-chip.queue { background:#f1f5f9; color:#475569; }
    .planning-meta { margin-top:7px; color:#475569; font-size:.78rem; line-height:1.4; overflow-wrap:break-word; word-break:normal; }
    .planning-card-actions { display:flex; justify-content:flex-end; margin-top:8px; }
    .planning-remove { border:0; background:#fee2e2; color:#b91c1c; border-radius:8px; padding:4px 8px; cursor:pointer; font-size:.72rem; font-weight:800; }
    .planning-empty { color:#94a3b8; border:1px dashed #cbd5e1; border-radius:10px; padding:12px; font-size:.84rem; }
    .planning-recommend { border-top:1px solid #e2e8f0; background:#f8fbff; overflow:hidden; display:flex; flex-direction:column; height:100%; min-height:0; }
    .planning-recommend-head { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:10px; border-bottom:1px solid #e2e8f0; flex-wrap:wrap; }
    .planning-recommend-title { font-weight:900; color:#0f172a; }
    .planning-recommend-actions { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
    .planning-recommend-actions input, .planning-recommend-actions select { width:70px; border:1px solid #cbd5e1; border-radius:10px; padding:7px 8px; font:inherit; background:#fff; }
    .planning-recommend-actions button { border:0; border-radius:10px; padding:8px 10px; font-weight:800; cursor:pointer; background:#0f766e; color:#fff; }
    .planning-recommend-list { padding:10px; display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:8px; overflow:auto; min-height:0; flex:1; align-content:start; }
    .planning-stock-search-row { padding:0 10px 10px; display:grid; gap:7px; }
    .planning-stock-search-row input { width:100%; box-sizing:border-box; border:1px solid #cbd5e1; border-radius:10px; padding:9px 10px; font:inherit; background:#fff; }
    .planning-stock-range { display:grid; grid-template-columns:1fr 1fr; gap:7px; }
    .stock-rec-card { border:1px solid #dbe5ef; border-radius:12px; background:#fff; padding:10px 11px; box-shadow:0 8px 18px rgba(15,23,42,.06); }
    .stock-rec-card[draggable="true"] { cursor:default; }
    .stock-rec-top { display:flex; justify-content:space-between; gap:8px; align-items:flex-start; }
    .stock-rec-sku { min-width:0; font-weight:900; color:#0f172a; overflow-wrap:break-word; word-break:normal; }
    .stock-rec-badge { border-radius:999px; padding:4px 8px; font-size:.68rem; font-weight:900; background:#fee2e2; color:#991b1b; white-space:nowrap; }
    .stock-rec-name { margin-top:5px; font-size:.78rem; color:#475569; line-height:1.35; overflow-wrap:break-word; word-break:normal; }
    .stock-rec-meta { margin-top:8px; display:flex; flex-wrap:wrap; gap:6px; font-size:.72rem; font-weight:800; color:#334155; }
    .stock-rec-meta span { background:#f1f5f9; border:1px solid #e2e8f0; border-radius:999px; padding:3px 7px; }
    .planning-dropzone, .planning-recommend-list, .stock-rec-card { cursor:default; }
    .planning-controls input, .planning-stock-search-row input, .planning-recommend-actions input, .planning-recommend-actions select { cursor:text; }
    .planning-recommend-actions select { cursor:pointer; }
    .planning-live-queue { margin-top:14px; border:1px solid #d5e1ed; border-radius:14px; background:rgba(255,255,255,.9); box-shadow:0 10px 24px rgba(15,23,42,.06); overflow:hidden; }
    .planning-live-queue-head { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:12px 14px; border-bottom:1px solid #e2e8f0; }
    .planning-live-queue-title { color:#0f172a; font-weight:900; }
    .planning-live-queue .table-wrap { margin:0; box-shadow:none; border:0; border-radius:0; }
    .table-actions { display: flex; gap: 8px; }
    .mini-btn { border: 1px solid #cbd5e1; background: #fff; color: #1f2937; border-radius: 8px; padding: 6px 10px; font-size: 0.82rem; cursor: pointer; transition: transform .12s ease, box-shadow .16s ease, background-color .16s ease; }
    .mini-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 12px rgba(15,23,42,0.08); }
    .mini-btn:active { transform: translateY(0) scale(0.985); }
    .mini-btn.primary { background: #eff6ff; border-color: #bfdbfe; color: #1d4ed8; }
    .finished-wrap { margin-top: 12px; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr)); gap: 14px; }
    .finished-item {
      border: 1px solid #d7e3f4;
      border-radius: 14px;
      padding: 14px;
      background: linear-gradient(160deg, #ffffff 0%, #f6f9ff 62%, #eef4ff 100%);
      box-shadow: 0 5px 14px rgba(22, 45, 90, 0.10);
    }
    .finished-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; margin-bottom: 10px; }
    .finished-item h4 { margin: 0; font-size: 1rem; color: #12233f; overflow-wrap: anywhere; word-break: break-word; }
    .finished-badge { font-size: 0.72rem; font-weight: 700; color: #1e40af; background: #dbeafe; border: 1px solid #93c5fd; border-radius: 999px; padding: 4px 9px; white-space: nowrap; }
    .finished-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .finished-grid div { font-size: 0.82rem; background: rgba(255,255,255,0.92); border: 1px solid #e6edf8; border-radius: 8px; padding: 7px 9px; min-width: 0; overflow-wrap: anywhere; word-break: break-word; }
    .raw-list { margin-top: 10px; font-size: 0.81rem; background: #fff; border: 1px solid #e6edf8; border-radius: 8px; padding: 8px; max-height: 130px; overflow: auto; white-space: pre-wrap; }
    .finished-actions { margin-top: 10px; display: flex; justify-content: flex-end; }
    .job-queue-summary { margin-top: 12px; display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; }
    .job-queue-metric { border: 1px solid #dbe4f0; border-radius: 12px; padding: 12px; background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%); }
    .job-queue-metric .k { font-size: 0.76rem; font-weight: 800; letter-spacing: .04em; text-transform: uppercase; color: #64748b; }
    .job-queue-metric .v { margin-top: 6px; font-size: 1.2rem; font-weight: 800; color: #0f172a; }
    .queue-status-badge { display: inline-flex; align-items: center; border-radius: 999px; padding: 4px 9px; font-size: 0.74rem; font-weight: 800; letter-spacing: .02em; white-space: nowrap; }
    .queue-status-badge.running { background: #dcfce7; color: #166534; border: 1px solid #86efac; }
    .queue-status-badge.done { background: #dbeafe; color: #1d4ed8; border: 1px solid #93c5fd; }
    .queue-status-badge.disconnected { background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; }
    .queue-status-badge.no-target, .queue-status-badge.no-cycle { background: #fef3c7; color: #92400e; border: 1px solid #fcd34d; }
    .approve-print-btn {
      border: none;
      border-radius: 10px;
      background: linear-gradient(135deg, #1f8ef1 0%, #1d4ed8 100%);
      color: #fff;
      font-weight: 600;
      font-size: 0.82rem;
      padding: 8px 12px;
      cursor: pointer;
      opacity: 0.95;
      transition: transform .12s ease, box-shadow .16s ease, opacity .16s ease;
    }
    .approve-print-btn:hover { opacity: 1; transform: translateY(-1px); box-shadow: 0 8px 18px rgba(29,78,216,0.24); }
    .approve-print-btn:active { transform: translateY(0) scale(0.985); }
    .overlay-backdrop { position: fixed; inset: 0; background: rgba(104, 120, 143, 0.52); backdrop-filter: blur(8px); display: none; align-items: center; justify-content: center; padding: 14px; z-index: 999; }
    .overlay-backdrop.active { display: flex; }
    .overlay-card { width: min(1120px, calc(100vw - 160px)); max-height: calc(100vh - 36px); background: #f4f5f7; border: 1px solid #cfd4dc; border-radius: 20px; box-shadow: 0 22px 56px rgba(15, 23, 42, 0.20); position: relative; overflow: hidden; display: flex; flex-direction: column; }
    .overlay-head { padding: 18px 24px 14px; border-bottom: 1px solid #d7dbe1; display: flex; align-items: center; justify-content: space-between; }
    .overlay-title { font-weight: 800; font-size: 1.08rem; color: #1d273c; letter-spacing: .01em; }
    .overlay-close { border: 1px solid #cfd4dc; background: #dde1e7; color: #2d3342; border-radius: 14px; width: 44px; height: 44px; padding: 0; cursor: pointer; font-size: 0; position: relative; }
    .overlay-close::before { content: "×"; font-size: 22px; line-height: 1; position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; }
    .overlay-body { padding: 10px 18px 8px; display: grid; gap: 6px; min-height: 0; overflow: hidden; flex: 1 1 auto; }
    .overlay-row { display: grid; grid-template-columns: 180px 1fr; gap: 12px; align-items: center; }
    .overlay-row > * { min-width: 0; }
    .overlay-row label { font-weight: 600; color: #40485a; font-size: 0.95rem; }
    .overlay-row select, .overlay-row input, .overlay-row textarea { width: 100%; max-width: 100%; box-sizing: border-box; border: 1px solid #c9d0db; border-radius: 14px; padding: 11px 14px; font-family: inherit; font-size: 0.98rem; background: #f7f8fa; color: #1f2937; }
    .overlay-row textarea { min-height: 64px; resize: none; line-height: 1.34; overflow: hidden; }
    .overlay-input-wrap { position: relative; width: 100%; }
    .overlay-suggest {
      position: absolute;
      top: calc(100% + 4px);
      left: 0;
      right: 0;
      z-index: 25;
      background: #fff;
      border: 1px solid #cbd5e1;
      border-radius: 10px;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.16);
      max-height: 220px;
      overflow-y: auto;
      display: none;
    }
    .overlay-suggest.active { display: block; }
    .overlay-suggest-item {
      width: 100%;
      border: none;
      border-bottom: 1px solid #eef2f7;
      background: #fff;
      text-align: left;
      padding: 8px 10px;
      cursor: pointer;
      font: inherit;
      font-size: 0.88rem;
    }
    .overlay-suggest-item:last-child { border-bottom: none; }
    .overlay-suggest-item:hover, .overlay-suggest-item.active { background: #eff6ff; }
    #overlayQrPayload { font-family: "Consolas", "Courier New", monospace; font-size: 0.78rem; line-height: 1.35; overflow-wrap: anywhere; word-break: break-all; }
    .overlay-preview { display: flex; align-items: center; justify-content: center; background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 10px; padding: 10px; min-height: 170px; }
    .overlay-preview img { width: 320px; max-width: 100%; height: auto; object-fit: contain; background: #fff; border: 1px solid #dbe4f0; border-radius: 8px; }
    .overlay-actions { padding: 10px 18px 14px; border-top: 1px solid #d7dbe1; display: flex; justify-content: flex-end; gap: 10px; flex: 0 0 auto; }
    .btn-secondary { border: 1px solid #c7cdd8; background: #f3f4f6; color: #202737; border-radius: 14px; padding: 9px 20px; cursor: pointer; font-size: 0.94rem; transition: transform .12s ease, box-shadow .16s ease, background-color .16s ease; }
    .btn-secondary:hover { background: #f8f9fb; transform: translateY(-1px); box-shadow: 0 8px 18px rgba(15,23,42,0.08); }
    .btn-secondary:active { transform: translateY(0) scale(0.985); }
    .btn-primary { border: none; background: linear-gradient(180deg, #3961dc 0%, #2d52cb 100%); color: #fff; border-radius: 14px; padding: 9px 20px; cursor: pointer; font-size: 0.94rem; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.10); transition: transform .12s ease, box-shadow .16s ease, filter .16s ease; }
    .btn-primary:hover { transform: translateY(-1px); box-shadow: 0 10px 22px rgba(45,82,203,0.28), inset 0 0 0 1px rgba(255,255,255,0.10); filter: brightness(1.03); }
    .btn-primary:active { transform: translateY(0) scale(0.985); }
    .review-slide-toolbar { display:flex; align-items:center; justify-content:center; gap:10px; margin: 0 0 10px; min-height: 42px; }
    .review-slide-status { font-size: 0.92rem; color: #4b5567; font-weight: 700; margin: 0; flex:1; text-align:center; }
    .review-slide-arrow { border: 1px solid rgba(199, 207, 219, 0.95); background: rgba(242,245,249,0.96); border-radius: 999px; width: 42px; height: 42px; cursor: pointer; font-size: 18px; box-shadow: 0 8px 22px rgba(15,23,42,0.11); color: #2f3a4d; transition: box-shadow .16s ease, background-color .16s ease, opacity .16s ease; }
    .review-slide-arrow:hover:not(:disabled) { box-shadow: 0 10px 22px rgba(15,23,42,0.13); background: rgba(248,250,252,0.98); }
    .review-slide-arrow:active:not(:disabled) { box-shadow: 0 7px 16px rgba(15,23,42,0.12); }
    .review-slide-arrow:disabled { opacity: 0.45; cursor: not-allowed; }
    .review-edge-arrow { position: absolute; top: 50%; transform: translateY(-50%); z-index: 5; }
    .review-edge-arrow.left { left: 14px; }
    .review-edge-arrow.right { right: 14px; }
    .review-subslide { display: none; animation: reviewSlideIn .16s ease; }
    .review-subslide.active { display: grid; grid-template-columns: 1fr; gap: 10px; align-items: start; }
    #overlayReviewStep { padding: 0 58px; width: 100%; box-sizing: border-box; margin: 0 auto; min-height: 0; overflow-y: auto; max-height: calc(100vh - 190px); }
    #overlayReviewStep .overlay-row { grid-template-columns: 190px 1fr; }
    #overlayReviewStep .overlay-row input[readonly] { background: #fff; }
    #overlayReviewStep .overlay-row textarea[readonly] { background: #fff; }
    .review-panel {
      background: #f7f8fb;
      border: 1px solid #d0d5de;
      border-radius: 16px;
      overflow: hidden;
      margin-bottom: 0;
      min-width: 0;
    }
    .review-panel-title {
      background: #dfe3e8;
      color: #222a3a;
      font-weight: 700;
      padding: 9px 14px;
      font-size: 0.92rem;
      border-bottom: 1px solid #d0d5de;
    }
    .review-panel-body {
      background: #f7f8fb;
      padding: 9px 12px;
      color: #1f2937;
      font-size: 0.88rem;
      line-height: 1.24;
      max-height: none;
      overflow: hidden;
    }
    .review-line-list { margin: 0; padding-left: 24px; display: grid; gap: 6px; }
    .review-line-list li { font-size: 0.92rem; color: #1f2937; }
    .review-inline-metrics { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
    .review-inline-metrics .dot { color: #8b93a1; }
    .review-inline-metrics .reject-emph { color: #d63b45; font-weight: 700; }
    .review-form-card { background: #f7f8fb; border: 1px solid #d0d5de; border-radius: 16px; padding: 10px; width: min(760px, 100%); margin: 0 auto; }
    .scan-capture-backdrop { position: fixed; inset: 0; background: rgba(15,23,42,0.35); display: none; align-items: center; justify-content: center; z-index: 1200; }
    .scan-capture-backdrop.active { display: flex; }
    .scan-capture-card { width: min(460px, calc(100vw - 32px)); background: #f8fafc; border: 1px solid #cfd8e3; border-radius: 16px; box-shadow: 0 20px 40px rgba(15,23,42,0.20); padding: 16px; }
    .scan-capture-title { font-weight: 700; color: #1f2937; font-size: 1rem; margin-bottom: 6px; }
    .scan-capture-sub { color: #64748b; font-size: 0.88rem; margin-bottom: 12px; }
    .scan-capture-input { width: 100%; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 12px; padding: 11px 12px; font-size: 0.95rem; }
    .scan-capture-actions { margin-top: 12px; display: flex; justify-content: flex-end; gap: 8px; }
    .settings-overlay { position: fixed; inset: 0; background: rgba(15,23,42,0.30); backdrop-filter: blur(6px); display: none; align-items: center; justify-content: center; z-index: 1100; padding: 14px; }
    .settings-overlay.active { display: flex; }
    .settings-card { width: min(840px, calc(100vw - 36px)); background: #f5f7fb; border: 1px solid #d8e0ea; border-radius: 18px; box-shadow: 0 24px 48px rgba(15,23,42,0.20); overflow: hidden; }
    .settings-head { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; border-bottom: 1px solid #dde5ef; }
    .settings-head-title { font-weight: 800; color: #1f2937; }
    .settings-body { display: grid; grid-template-columns: 210px 1fr; min-height: 400px; }
    .settings-nav { background: #eef2f7; border-right: 1px solid #dde5ef; padding: 12px; display: grid; gap: 8px; align-content: start; }
    .settings-nav-btn { border: 1px solid #d5dde8; background: #fff; color: #334155; border-radius: 12px; padding: 10px 12px; text-align: left; cursor: pointer; font-weight: 600; transition: background-color .14s ease, transform .1s ease; }
    .settings-nav-btn.active { background: #dbeafe; border-color: #bfdbfe; color: #1d4ed8; }
    .settings-nav-btn:hover { transform: translateY(-1px); }
    .settings-content { padding: 14px; }
    .settings-page { display: none; }
    .settings-page.active { display: block; }
    .settings-form { display: grid; gap: 10px; }
    .settings-row { display: grid; gap: 6px; }
    .settings-row label { font-size: 0.86rem; font-weight: 700; color: #475569; }
    .settings-row input, .settings-row select { width: 100%; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 10px; padding: 9px 10px; font: inherit; background: #fff; }
    .settings-actions { margin-top: 12px; display: flex; justify-content: flex-end; gap: 8px; }
    .settings-note { font-size: 0.85rem; color: #64748b; line-height: 1.35; }
    .people-role-list { margin-top: 10px; border: 1px solid #dbe4f0; border-radius: 12px; background: #fff; overflow: hidden; }
    .people-role-row { display: grid; grid-template-columns: 1.15fr .75fr .9fr .9fr .9fr; gap: 8px; padding: 8px 10px; border-bottom: 1px solid #eef2f7; font-size: 0.84rem; align-items: center; }
    .people-role-row:last-child { border-bottom: none; }
    .people-role-row.head { background: #f8fafc; font-weight: 700; color: #475569; }
    .people-role-pill { display: inline-block; border-radius: 999px; padding: 3px 8px; font-size: 0.76rem; font-weight: 700; background: #e2e8f0; color: #334155; }
    .operator-directory-card { width: min(1020px, calc(100vw - 36px)); background: #f8fafc; border: 1px solid #d8e0ea; border-radius: 18px; box-shadow: 0 24px 48px rgba(15,23,42,0.20); overflow: hidden; }
    .operator-directory-head { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:14px 16px; border-bottom:1px solid #dde5ef; }
    .operator-directory-title { font-weight:800; color:#1f2937; }
    .operator-directory-sub { font-size:.83rem; color:#64748b; margin-top:4px; }
    .operator-directory-grid { display:grid; gap:0; padding:0; max-height:min(72vh, 760px); overflow:auto; }
    .operator-directory-row { display:grid; grid-template-columns: 1.35fr 1fr 1fr .95fr 120px; gap:12px; align-items:center; padding:12px 16px; border-bottom:1px solid #e5edf5; background:rgba(255,255,255,.94); cursor:pointer; transition: background-color .14s ease; }
    .operator-directory-row:hover:not(.header) { background:#f8fbff; }
    .operator-directory-row.header { position:sticky; top:0; z-index:2; background:#f8fafc; font-size:.76rem; font-weight:800; text-transform:uppercase; letter-spacing:.04em; color:#64748b; }
    .operator-directory-row:last-child { border-bottom:none; }
    .operator-directory-name { display:grid; gap:3px; min-width:0; }
    .operator-directory-name strong { font-size:.92rem; color:#0f172a; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .operator-directory-meta { font-size:.78rem; color:#64748b; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .operator-directory-cell { min-width:0; }
    .operator-directory-label { display:none; font-size:.68rem; font-weight:800; letter-spacing:.04em; text-transform:uppercase; color:#64748b; margin-bottom:2px; }
    .operator-directory-value { font-size:.83rem; color:#0f172a; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .operator-directory-subvalue { font-size:.74rem; color:#64748b; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:2px; }
    .operator-directory-badge { display:inline-flex; align-items:center; justify-content:center; border-radius:999px; padding:5px 9px; font-size:.72rem; font-weight:800; background:#e2e8f0; color:#334155; white-space:nowrap; }
    .operator-directory-badge.live { background:#dcfce7; color:#166534; }
    .operator-directory-empty { padding:24px 18px; color:#64748b; font-size:.9rem; }
    .operator-detail-card { width:min(860px, calc(100vw - 36px)); background:#f8fafc; border:1px solid #d8e0ea; border-radius:18px; box-shadow:0 24px 48px rgba(15,23,42,0.20); overflow:hidden; }
    .operator-detail-head { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:14px 16px; border-bottom:1px solid #dde5ef; }
    .operator-detail-title { font-weight:800; color:#1f2937; }
    .operator-detail-sub { font-size:.83rem; color:#64748b; margin-top:4px; }
    .operator-detail-body { padding:16px; display:grid; gap:14px; max-height:min(78vh, 780px); overflow:auto; }
    .operator-detail-grid { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:10px; }
    .operator-detail-item { border:1px solid #dbe4f0; border-radius:12px; background:#fff; padding:10px 12px; }
    .operator-detail-item .k { font-size:.72rem; font-weight:800; letter-spacing:.04em; text-transform:uppercase; color:#64748b; margin-bottom:4px; }
    .operator-detail-item .v { font-size:.86rem; color:#0f172a; overflow-wrap:anywhere; }
    .operator-detail-section { border:1px solid #dbe4f0; border-radius:14px; background:#fff; padding:12px; }
    .operator-detail-section h4 { margin:0 0 10px; font-size:.92rem; color:#0f172a; }
    .operator-detail-list { display:grid; gap:8px; }
    .operator-detail-list-item { border-left:3px solid #93c5fd; padding-left:10px; }
    .operator-detail-list-item strong { display:block; font-size:.82rem; color:#0f172a; }
    .operator-detail-list-item span { display:block; font-size:.77rem; color:#64748b; }
    .linkage-pill { display:inline-block; margin-left:8px; padding:2px 8px; border-radius:999px; font-size:.72rem; font-weight:800; background:#fff7ed; color:#c2410c; border:1px solid #fdba74; }
    .machine-linkage-flag { display:inline-block; margin-bottom:6px; padding:3px 8px; border-radius:999px; font-size:.72rem; font-weight:800; background:#ffedd5; color:#9a3412; border:1px solid #fdba74; box-shadow:0 0 0 0 rgba(251,146,60,.45); animation: linkagePulse 1.1s ease-in-out infinite; }
    @keyframes linkagePulse { 0%,100% { box-shadow:0 0 0 0 rgba(251,146,60,.25);} 50% { box-shadow:0 0 0 8px rgba(251,146,60,0);} }
    .finished-linkage-note { margin-top:8px; font-size:.82rem; color:#7c2d12; background:#fff7ed; border:1px solid #fed7aa; border-radius:10px; padding:8px 10px; }
    .settings-table-wrap { border: 1px solid #dbe4f0; border-radius: 12px; background: #fff; overflow: auto; }
    .settings-table { width: 100%; border-collapse: collapse; min-width: 520px; }
    .settings-table th, .settings-table td { border-bottom: 1px solid #edf2f7; padding: 8px 10px; text-align: left; font-size: 0.84rem; }
    .settings-table th { background: #f8fafc; color: #475569; font-weight: 700; }
    #overlayReviewSummary { min-height: 72px; height: 72px; }
    #overlayReviewRejects { min-height: 64px; height: 64px; }
    #overlayRawConsumption { min-height: 88px; height: 88px; }
    #overlayRawCycleSummary { min-height: 52px; height: 52px; }
    #overlayDowntimeSummary { min-height: 56px; height: 56px; }
    #overlayPeopleSummary { min-height: 62px; height: 62px; }
    #overlayReviewRemarks { min-height: 58px; height: 58px; }
    #editRejectBreakdown { min-height: 58px; height: 58px; }
    .review-pre { margin: 0; white-space: pre-wrap; word-break: break-word; font: 600 12px/1.45 "Consolas", "Courier New", monospace; color: #dbeafe; }
    .review-group-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 10px; }
    .review-group-card { border: 1px solid #dbe4f0; border-radius: 12px; background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%); overflow: hidden; }
    .review-group-card.wide { grid-column: 1 / -1; }
    .review-group-head { padding: 10px 12px; background: linear-gradient(90deg, #e8f0fb 0%, #f4f8fc 100%); border-bottom: 1px solid #dbe4f0; font-size: .83rem; font-weight: 800; color: #334155; letter-spacing: .04em; text-transform: uppercase; }
    .review-group-body { padding: 10px 12px; }
    .review-kv-table { width: 100%; border-collapse: collapse; table-layout: auto; }
    .review-data-table th { padding: 6px 8px; border-bottom: 1px solid #d8e3f0; text-align: left; font-size: .72rem; font-weight: 800; color: #64748b; text-transform: uppercase; letter-spacing: .03em; }
    .review-data-table td { font-size: .82rem; font-weight: 600; color: #0f172a; }
    .review-kv-table td { padding: 6px 8px; border-bottom: 1px solid #e8eef6; vertical-align: top; }
    .review-kv-table tr:last-child td { border-bottom: none; }
    .review-kv-key { width: 150px; min-width: 120px; font-size: .76rem; font-weight: 800; color: #64748b; text-transform: uppercase; letter-spacing: .03em; }
    .review-kv-value { font-size: .9rem; font-weight: 600; color: #0f172a; word-break: normal; overflow-wrap: break-word; }
    .review-more-note { margin-top: 8px; font-size: .78rem; font-weight: 700; color: #64748b; }
    .review-json-block { margin: 0; white-space: pre-wrap; word-break: break-word; font: 600 12px/1.45 "Consolas", "Courier New", monospace; color: #0f172a; background: #f8fafc; border: 1px solid #dbe4f0; border-radius: 10px; padding: 10px; max-height: 42vh; overflow: auto; }
    @keyframes reviewSlideIn { from { opacity: .45; transform: translateX(6px); } to { opacity: 1; transform: translateX(0); } }
    @keyframes cardPulseGreen {
      0% { box-shadow: 0 2px 8px rgba(0,0,0,0.08), 0 0 0 0 rgba(76,175,80,0.30); }
      50% { box-shadow: 0 2px 8px rgba(0,0,0,0.08), 0 0 0 7px rgba(76,175,80,0.12); }
      100% { box-shadow: 0 2px 8px rgba(0,0,0,0.08), 0 0 0 0 rgba(76,175,80,0.00); }
    }
    @keyframes cardPulseGreenDark {
      0% { box-shadow: 0 2px 8px rgba(0,0,0,0.22), 0 0 0 0 rgba(34,255,136,0.42), 0 0 14px rgba(34,255,136,.10); }
      50% { box-shadow: 0 2px 8px rgba(0,0,0,0.22), 0 0 0 8px rgba(34,255,136,0.16), 0 0 18px rgba(34,255,136,.22); }
      100% { box-shadow: 0 2px 8px rgba(0,0,0,0.22), 0 0 0 0 rgba(34,255,136,0.00), 0 0 14px rgba(34,255,136,.08); }
    }
    @keyframes cardPulseGreenPastel {
      0% { box-shadow: 0 2px 8px rgba(0,0,0,0.08), 0 0 0 0 rgba(143,211,177,0.34); }
      50% { box-shadow: 0 2px 8px rgba(0,0,0,0.08), 0 0 0 7px rgba(143,211,177,0.14); }
      100% { box-shadow: 0 2px 8px rgba(0,0,0,0.08), 0 0 0 0 rgba(143,211,177,0.00); }
    }
    @keyframes cardPulseGreenMuted {
      0% { box-shadow: 0 2px 8px rgba(0,0,0,0.08), 0 0 0 0 rgba(123,191,154,0.30); }
      50% { box-shadow: 0 2px 8px rgba(0,0,0,0.08), 0 0 0 7px rgba(123,191,154,0.12); }
      100% { box-shadow: 0 2px 8px rgba(0,0,0,0.08), 0 0 0 0 rgba(123,191,154,0.00); }
    }
    @keyframes cardPulseOrange {
      0% { box-shadow: 0 2px 8px rgba(0,0,0,0.08), 0 0 0 0 rgba(255,152,0,0.30); }
      50% { box-shadow: 0 2px 8px rgba(0,0,0,0.08), 0 0 0 8px rgba(255,152,0,0.14); }
      100% { box-shadow: 0 2px 8px rgba(0,0,0,0.08), 0 0 0 0 rgba(255,152,0,0.00); }
    }
    @keyframes statusBeatGreen {
      0%, 100% { transform:scale(1); box-shadow:0 0 0 3px rgba(34,197,94,.18), 0 0 8px rgba(34,197,94,.28); }
      50% { transform:scale(1.18); box-shadow:0 0 0 6px rgba(34,197,94,.10), 0 0 14px rgba(34,197,94,.48); }
    }
    @keyframes statusBeatRed {
      0%, 100% { transform:scale(1); box-shadow:0 0 0 3px rgba(239,68,68,.18), 0 0 8px rgba(239,68,68,.28); }
      50% { transform:scale(1.18); box-shadow:0 0 0 6px rgba(239,68,68,.10), 0 0 14px rgba(239,68,68,.48); }
    }
    @keyframes statusBeatOrange {
      0%, 100% { transform:scale(1); box-shadow:0 0 0 3px rgba(245,158,11,.20), 0 0 8px rgba(245,158,11,.30); }
      50% { transform:scale(1.18); box-shadow:0 0 0 6px rgba(245,158,11,.12), 0 0 14px rgba(245,158,11,.52); }
    }
    @keyframes linkageCardFlipOut {
      0% { transform:rotateY(0deg) scale(1); opacity:1; box-shadow:0 8px 20px rgba(15,23,42,.06); }
      100% { transform:rotateY(88deg) scale(.985); opacity:.72; box-shadow:0 18px 34px rgba(15,23,42,.16); }
    }
    @keyframes linkageCardFlipIn {
      0% { transform:rotateY(-88deg) scale(.985); opacity:.72; box-shadow:0 18px 34px rgba(15,23,42,.16); }
      58% { transform:rotateY(8deg) scale(1.002); opacity:1; box-shadow:0 14px 28px rgba(15,23,42,.12); }
      100% { transform:rotateY(0deg) scale(1); opacity:1; box-shadow:0 8px 20px rgba(15,23,42,.06); }
    }
    .overlay-head-actions { display:flex; align-items:center; gap:8px; }
    .icon-btn {
      width: 38px; height: 38px; border-radius: 12px; border: 1px solid #c7d0dd; background: #f8fafc;
      color: #334155; cursor: pointer; font-size: 18px; font-weight: 700;
    }
    .icon-btn:hover { background:#fff; box-shadow:0 6px 14px rgba(15,23,42,.08); }
    .machine-detail-status-panel { background:#f8fbff; border:1px solid #d9e6f6; border-radius:12px; padding:10px; display:grid; gap:8px; }
    .machine-detail-status-panel .row { display:grid; grid-template-columns: 160px 1fr auto; gap:8px; align-items:center; }
    .machine-detail-status-panel label { font-weight:700; color:#475569; font-size:.86rem; }
    .machine-detail-status-panel select { border:1px solid #cbd5e1; border-radius:10px; padding:8px 10px; font:inherit; background:#fff; }
    .machine-detail-status-panel textarea { border:1px solid #cbd5e1; border-radius:10px; padding:8px 10px; font:inherit; background:#fff; min-height:54px; resize:vertical; }
    .machine-detail-status-panel .hint { color:#64748b; font-size:.82rem; }
    .machine-status-save-feedback { display:none; align-items:center; gap:8px; }
    .machine-status-save-feedback.active { display:flex; }
    .machine-status-save-track { flex:1; height:10px; border-radius:999px; border:1px solid #cbd5e1; background:#fff; overflow:hidden; }
    .machine-status-save-bar { height:100%; width:0%; background: linear-gradient(90deg, #f97316, #22c55e); transition: width .10s linear; }
    .machine-status-save-check { width:22px; height:22px; border-radius:999px; border:2px solid #16a34a; color:#16a34a; display:flex; align-items:center; justify-content:center; font-weight:900; opacity:.15; transform:scale(.92); transition: all .16s ease; background:#fff; }
    .machine-status-save-check.done { opacity:1; transform:scale(1); background:#ecfdf5; }
    .machine-detail-card { width: min(980px, 100%); max-height: min(88vh, 860px); display: flex; flex-direction: column; }
    .machine-detail-body { padding: 14px; overflow: auto; display: grid; gap: 12px; }
    .machine-detail-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
    .machine-detail-item { background: #f8fbff; border: 1px solid #d9e6f6; border-radius: 10px; padding: 9px 10px; }
    .machine-detail-item .k { font-size: .76rem; color: #64748b; margin-bottom: 4px; text-transform: uppercase; letter-spacing: .03em; }
    .machine-detail-item .v { font-size: .92rem; font-weight: 600; color: #0f172a; overflow-wrap: anywhere; }
    .machine-detail-section { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 12px; }
    .machine-detail-section h4 { margin: 0 0 10px; color: #0f172a; font-size: .98rem; }
    .machine-detail-code { font-family: "Consolas","Courier New",monospace; font-size: .82rem; white-space: pre-wrap; overflow-wrap: anywhere; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px; max-height: 220px; overflow: auto; }
    .machine-detail-list { margin: 0; padding-left: 18px; display: grid; gap: 4px; }
    .machine-detail-list li { font-size: .88rem; color: #1f2937; }
    .machine-detail-empty { color: #64748b; font-size: .88rem; }
    .archive-detail-hero { display:grid; grid-template-columns: 1.35fr .9fr; gap:12px; align-items:stretch; background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 58%,#155e75 100%); color:#fff; border-radius:14px; padding:14px; }
    .archive-detail-hero h3 { margin:0; font-size:1.24rem; letter-spacing:0; }
    .archive-detail-hero .sub { margin-top:5px; font-size:.86rem; color:#dbeafe; overflow-wrap:anywhere; }
    .archive-detail-hero .archive-pill-row { display:flex; flex-wrap:wrap; gap:7px; margin-top:12px; }
    .archive-pill { display:inline-flex; align-items:center; border-radius:999px; padding:5px 9px; font-size:.72rem; font-weight:800; letter-spacing:.02em; text-transform:uppercase; background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.22); color:#eff6ff; }
    .archive-detail-hero-side { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
    .archive-hero-stat { background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.20); border-radius:10px; padding:9px 10px; min-width:0; }
    .archive-hero-stat .k { color:#bfdbfe; font-size:.68rem; font-weight:800; text-transform:uppercase; letter-spacing:.05em; }
    .archive-hero-stat .v { margin-top:3px; font-size:1.08rem; font-weight:900; overflow-wrap:anywhere; }
    .archive-metric-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }
    .archive-metric { border:1px solid #dbe4f0; background:linear-gradient(180deg,#ffffff 0%,#f8fbff 100%); border-radius:10px; padding:10px 11px; min-width:0; }
    .archive-metric .k { font-size:.72rem; color:#64748b; text-transform:uppercase; font-weight:800; letter-spacing:.04em; }
    .archive-metric .v { margin-top:4px; font-size:1.1rem; font-weight:900; color:#0f172a; overflow-wrap:anywhere; }
    .archive-metric.good { border-color:#bbf7d0; background:#f0fdf4; }
    .archive-metric.warn { border-color:#fed7aa; background:#fff7ed; }
    .archive-metric.bad { border-color:#fecaca; background:#fef2f2; }
    .archive-raw-details { margin-top:10px; }
    .archive-raw-details summary { cursor:pointer; font-size:.82rem; font-weight:800; color:#334155; }
    .detail-chart-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin-top:10px; }
    .detail-chart-card { border:1px solid #dbe4f0; border-radius:12px; background:#fff; padding:11px 12px; min-width:0; }
    .detail-chart-card .head { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:8px; }
    .detail-chart-card .title { font-size:.78rem; font-weight:900; letter-spacing:.04em; text-transform:uppercase; color:#334155; }
    .detail-chart-card .value { font-size:.82rem; font-weight:900; color:#0f172a; }
    .detail-bar { height:13px; border-radius:999px; background:#e5edf5; overflow:hidden; display:flex; border:1px solid #dbe4f0; }
    .detail-bar-seg { min-width:0; height:100%; }
    .detail-bar-seg.good { background:#22c55e; }
    .detail-bar-seg.butal { background:#f59e0b; }
    .detail-bar-seg.reject { background:#ef4444; }
    .detail-bar-seg.noshot { background:#64748b; }
    .detail-bar-legend { display:flex; flex-wrap:wrap; gap:7px 10px; margin-top:8px; }
    .detail-legend-item { display:inline-flex; align-items:center; gap:5px; font-size:.72rem; font-weight:800; color:#475569; }
    .detail-dot { width:9px; height:9px; border-radius:999px; display:inline-block; }
    .detail-dot.good { background:#22c55e; }
    .detail-dot.butal { background:#f59e0b; }
    .detail-dot.reject { background:#ef4444; }
    .detail-dot.noshot { background:#64748b; }
    .detail-progress { display:grid; gap:7px; }
    .detail-progress-row { display:grid; grid-template-columns:110px 1fr 52px; align-items:center; gap:8px; font-size:.76rem; font-weight:800; color:#475569; }
    .detail-progress-track { height:9px; border-radius:999px; background:#e5edf5; overflow:hidden; border:1px solid #dbe4f0; }
    .detail-progress-fill { height:100%; border-radius:999px; background:#2563eb; }
    .detail-progress-fill.warn { background:#f59e0b; }
    .detail-progress-fill.bad { background:#ef4444; }
    .raw-insight-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-bottom:10px; }
    .raw-insight-card { border:1px solid #dbe4f0; border-radius:12px; background:linear-gradient(180deg,#ffffff 0%,#f8fbff 100%); padding:10px 11px; min-width:0; }
    .raw-insight-card .k { font-size:.7rem; font-weight:900; color:#64748b; text-transform:uppercase; letter-spacing:.04em; }
    .raw-insight-card .v { margin-top:4px; font-size:1.05rem; font-weight:900; color:#0f172a; overflow-wrap:anywhere; }
    .raw-insight-card.warn { border-color:#fed7aa; background:#fff7ed; }
    .raw-insight-card.good { border-color:#bbf7d0; background:#f0fdf4; }
    .raw-insight-card.bad { border-color:#fecaca; background:#fef2f2; }
    .raw-match-list { display:grid; gap:8px; }
    .raw-match-item { border:1px solid #dbe4f0; border-radius:12px; background:#fff; padding:10px 11px; }
    .raw-match-top { display:flex; justify-content:space-between; gap:10px; align-items:flex-start; }
    .raw-match-name { font-weight:900; color:#0f172a; overflow-wrap:anywhere; }
    .raw-match-status { border-radius:999px; padding:4px 8px; font-size:.7rem; font-weight:900; text-transform:uppercase; white-space:nowrap; background:#e2e8f0; color:#334155; }
    .raw-match-status.good { background:#dcfce7; color:#166534; }
    .raw-match-status.warn { background:#ffedd5; color:#9a3412; }
    .raw-match-status.bad { background:#fee2e2; color:#991b1b; }
    .raw-match-meta { margin-top:7px; display:flex; flex-wrap:wrap; gap:7px; font-size:.76rem; font-weight:800; color:#475569; }
    body[data-theme="Soft Gray"] { background: #eef1f4; color: #243041; }
    body[data-theme="Soft Gray"] .diag-item,
    body[data-theme="Soft Gray"] .card,
    body[data-theme="Soft Gray"] .panel { background: #f8fafc; border-color: #d7dee8; }
    body[data-theme="Soft Gray"] .card.active { border-color: #7bbf9a; animation: cardPulseGreenMuted 1.5s ease-in-out infinite; }
    body[data-theme="Soft Gray"] .card.disconnected { border-color: #d28b8b; }
    body[data-theme="Soft Gray"] .card.maintenance { border-color: #d6a56a; animation: cardPulseOrange 1.5s ease-in-out infinite; }
    body[data-theme="Soft Gray"] .main-tab-button.active { background: #64748b; color: #fff; }
    body[data-theme="Soft Gray"] .main-tab-content { background: linear-gradient(180deg, rgba(248,250,252,.92), rgba(241,245,249,.82)); border-radius: 16px; }
    body[data-theme="Soft Gray"] .sub-tab-button { background:#fff; color:#475569; border-color:#dbe2eb; }
    body[data-theme="Soft Gray"] .sub-tab-button.active { background:#64748b; color:#fff; border-color:#64748b; }
    body[data-theme="Soft Gray"] .finished-item { background: linear-gradient(160deg, #ffffff 0%, #f8fafc 60%, #eef2f7 100%); border-color: #dbe2eb; box-shadow: 0 5px 14px rgba(51,65,85,.10); }
    body[data-theme="Soft Gray"] .finished-item h4 { color: #1f2937; }
    body[data-theme="Soft Gray"] .finished-grid div { background: #fff; border-color: #e5e7eb; color: #334155; }
    body[data-theme="Soft Gray"] .raw-list { background: #fff; border-color: #e5e7eb; color: #475569; }
    body[data-theme="Soft Gray"] .approve-print-btn { background: linear-gradient(135deg, #64748b 0%, #475569 100%); }
    body[data-theme="Dark"] { background: #0b1220; color: #e5e7eb; }
    body[data-theme="Dark"] .diag-item { background: #111827; color: #e5e7eb; box-shadow: 0 1px 3px rgba(0,0,0,0.35); }
    body[data-theme="Dark"] .diag-item .value { color: #f8fafc; }
    body[data-theme="Dark"] .main-tab-button { background: #1f2937; color: #d1d5db; }
    body[data-theme="Dark"] .main-tab-button.active { background: #2563eb; color: #fff; }
    body[data-theme="Dark"] .main-tab-content { background: linear-gradient(180deg, rgba(2,6,23,.42), rgba(2,6,23,.22)); border-radius: 16px; }
    body[data-theme="Dark"] .sub-tab-button { background:#0f172a; color:#d1d5db; border-color:#334155; }
    body[data-theme="Dark"] .sub-tab-button.active { background:#2563eb; color:#fff; border-color:#3b82f6; }
    body[data-theme="Dark"] .card,
    body[data-theme="Dark"] .panel,
    body[data-theme="Dark"] .table-wrap { background: #111827; color: #e5e7eb; border-color: #334155; }
    body[data-theme="Dark"] .card.active { border-color: #22ff88; animation: cardPulseGreenDark 1.5s ease-in-out infinite; }
    body[data-theme="Dark"] .card.disconnected { border-color: #ff4d6d; box-shadow: 0 2px 8px rgba(0,0,0,0.22), 0 0 0 1px rgba(255,77,109,.12) inset; }
    body[data-theme="Dark"] .card.maintenance { border-color:#f59e0b; animation: cardPulseOrange 1.5s ease-in-out infinite; }
    body[data-theme="Dark"] .card h3 { border-bottom-color: #334155; }
    body[data-theme="Dark"] .muted { color: #94a3b8; }
    body[data-theme="Dark"] .placeholder { background: #0f172a; border-color: #334155; color: #94a3b8; }
    body[data-theme="Dark"] .finished-item { background: linear-gradient(160deg, #0f172a 0%, #111827 60%, #0b1220 100%); border-color: #334155; box-shadow: 0 10px 22px rgba(0,0,0,.30); }
    body[data-theme="Dark"] .finished-item h4 { color: #e5e7eb; }
    body[data-theme="Dark"] .finished-badge { color: #bfdbfe; background: rgba(30,64,175,.25); border-color: #3b82f6; }
    body[data-theme="Dark"] .finished-grid div { background: rgba(15,23,42,.85); border-color: #334155; color: #d1d5db; }
    body[data-theme="Dark"] .raw-list { background: #0f172a; border-color: #334155; color: #cbd5e1; }
    body[data-theme="Dark"] .finished-linkage-note { background: rgba(60,20,10,.35); border-color: #fdba74; color: #fed7aa; }
    body[data-theme="Dark"] .approve-print-btn { background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%); box-shadow: inset 0 0 0 1px rgba(147,197,253,.18); }
    body[data-theme="Dark"] .approve-print-btn:hover { box-shadow: 0 10px 24px rgba(37,99,235,.35), inset 0 0 0 1px rgba(147,197,253,.18); }
    body[data-theme="Dark"] .data-table th { background: #1f2937; color: #e5e7eb; }
    body[data-theme="Dark"] .data-table td { border-bottom-color: #253041; }
    body[data-theme="Dark"] .data-table tr:hover td { background: #172033; }
    body[data-theme="Dark"] .mini-btn { background: #0f172a; color: #e5e7eb; border-color: #334155; }
    body[data-theme="Dark"] .settings-overlay { background: rgba(2,6,23,0.46); }
    body[data-theme="Dark"] .settings-card { background: #0f172a; border-color: #334155; box-shadow: 0 24px 48px rgba(0,0,0,0.38); }
    body[data-theme="Dark"] .settings-head { border-bottom-color: #334155; }
    body[data-theme="Dark"] .settings-head-title { color: #e5e7eb; }
    body[data-theme="Dark"] .settings-nav { background: #111827; border-right-color: #334155; }
    body[data-theme="Dark"] .settings-nav-btn { background: #0f172a; color: #d1d5db; border-color: #334155; }
    body[data-theme="Dark"] .settings-nav-btn.active { background: #1e3a8a; border-color: #3b82f6; color: #dbeafe; }
    body[data-theme="Dark"] .settings-row label { color: #cbd5e1; }
    body[data-theme="Dark"] .settings-row input, body[data-theme="Dark"] .settings-row select { background: #111827; color: #e5e7eb; border-color: #334155; }
    body[data-theme="Dark"] .settings-note { color: #94a3b8; }
    body[data-theme="Dark"] .people-role-list, body[data-theme="Dark"] .settings-table-wrap { background: #111827; border-color: #334155; }
    body[data-theme="Dark"] .people-role-row { border-bottom-color: #253041; color: #d1d5db; }
    body[data-theme="Dark"] .people-role-row.head { background: #1f2937; color: #cbd5e1; }
    body[data-theme="Dark"] .settings-table th { background: #1f2937; color: #cbd5e1; }
    body[data-theme="Dark"] .settings-table td { border-bottom-color: #253041; color: #e5e7eb; }
    body[data-theme="Dark"] .operator-directory-card { background:#0f172a; border-color:#334155; box-shadow:0 24px 48px rgba(0,0,0,0.38); }
    body[data-theme="Dark"] .operator-directory-head { border-bottom-color:#334155; }
    body[data-theme="Dark"] .operator-directory-title, body[data-theme="Dark"] .operator-directory-name strong, body[data-theme="Dark"] .operator-directory-value { color:#e5e7eb; }
    body[data-theme="Dark"] .operator-directory-sub, body[data-theme="Dark"] .operator-directory-meta, body[data-theme="Dark"] .operator-directory-subvalue, body[data-theme="Dark"] .operator-directory-empty, body[data-theme="Dark"] .operator-directory-row.header, body[data-theme="Dark"] .operator-directory-label { color:#94a3b8; }
    body[data-theme="Dark"] .operator-directory-row { background:#111827; border-bottom-color:#253041; }
    body[data-theme="Dark"] .operator-directory-row.header { background:#1f2937; }
    body[data-theme="Dark"] .operator-directory-row:hover:not(.header) { background:#172033; }
    body[data-theme="Dark"] .operator-detail-card { background:#0f172a; border-color:#334155; box-shadow:0 24px 48px rgba(0,0,0,0.38); }
    body[data-theme="Dark"] .operator-detail-head { border-bottom-color:#334155; }
    body[data-theme="Dark"] .operator-detail-title, body[data-theme="Dark"] .operator-detail-item .v, body[data-theme="Dark"] .operator-detail-section h4, body[data-theme="Dark"] .operator-detail-list-item strong { color:#e5e7eb; }
    body[data-theme="Dark"] .operator-detail-sub, body[data-theme="Dark"] .operator-detail-item .k, body[data-theme="Dark"] .operator-detail-list-item span { color:#94a3b8; }
    body[data-theme="Dark"] .operator-detail-item, body[data-theme="Dark"] .operator-detail-section { background:#111827; border-color:#334155; }
    body[data-theme="Red"] { background: #fff4f4; color: #3b0a0a; }
    body[data-theme="Red"] .diag-item,
    body[data-theme="Red"] .card,
    body[data-theme="Red"] .panel { background: #fff; border-color: #fecaca; }
    body[data-theme="Red"] .card.active { border-color: #8fd3b1; animation: cardPulseGreenPastel 1.5s ease-in-out infinite; }
    body[data-theme="Red"] .card.disconnected { border-color: #f3a6b3; }
    body[data-theme="Red"] .card.maintenance { border-color:#fb923c; animation: cardPulseOrange 1.5s ease-in-out infinite; }
    body[data-theme="Red"] .main-tab-button { background: #fee2e2; color: #7f1d1d; }
    body[data-theme="Red"] .main-tab-button.active { background: #dc2626; color: #fff; }
    body[data-theme="Red"] .main-tab-content { background: linear-gradient(180deg, rgba(254,242,242,.95), rgba(255,255,255,.88)); border-radius: 16px; }
    body[data-theme="Red"] .sub-tab-button { background:#fff; color:#7f1d1d; border-color:#fecaca; }
    body[data-theme="Red"] .sub-tab-button.active { background:#dc2626; color:#fff; border-color:#dc2626; }
    body[data-theme="Red"] .finished-item { border-color: #fecaca; background: linear-gradient(160deg, #fff 0%, #fff1f2 66%, #ffe4e6 100%); }
    body[data-theme="Red"] .operator-directory-row { border-bottom-color:#fee2e2; }
    body[data-theme="Red"] .operator-directory-row.header { background:#fef2f2; color:#991b1b; }
    body[data-theme="Red"] .operator-detail-card, body[data-theme="Red"] .operator-detail-item, body[data-theme="Red"] .operator-detail-section { border-color:#fecaca; }
    body[data-theme="Red"] .finished-item h4 { color: #7f1d1d; }
    body[data-theme="Red"] .finished-grid div { border-color: #fecdd3; background: rgba(255,255,255,.95); color: #7f1d1d; }
    body[data-theme="Red"] .raw-list { border-color: #fecdd3; background: #fff; color: #7f1d1d; }
    body[data-theme="Red"] .approve-print-btn { background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%); }
    body[data-theme="Red"] .table-wrap { border-color: #fecaca; }
    body[data-theme="Red"] .data-table th { background: #fef2f2; color: #7f1d1d; }
    body[data-theme="Red"] .settings-overlay { background: rgba(127,29,29,0.18); }
    body[data-theme="Red"] .settings-card { background: #fff7f7; border-color: #fecaca; }
    body[data-theme="Red"] .settings-head { border-bottom-color: #fecaca; }
    body[data-theme="Red"] .settings-head-title { color: #7f1d1d; }
    body[data-theme="Red"] .settings-nav { background: #fef2f2; border-right-color: #fecaca; }
    body[data-theme="Red"] .settings-nav-btn { background: #fff; color: #7f1d1d; border-color: #fecaca; }
    body[data-theme="Red"] .settings-nav-btn.active { background: #fee2e2; border-color: #fca5a5; color: #b91c1c; }
    body[data-theme="Red"] .settings-row label { color: #7f1d1d; }
    body[data-theme="Red"] .settings-row input, body[data-theme="Red"] .settings-row select { border-color: #fecaca; background: #fff; color: #7f1d1d; }
    body[data-theme="Red"] .settings-note { color: #991b1b; }
    body[data-theme="Red"] .people-role-list, body[data-theme="Red"] .settings-table-wrap { border-color: #fecaca; background: #fff; }
    body[data-theme="Red"] .people-role-row { border-bottom-color: #fee2e2; color: #7f1d1d; }
    body[data-theme="Red"] .people-role-row.head { background: #fef2f2; color: #991b1b; }
    body[data-theme="Red"] .settings-table th { background: #fef2f2; color: #991b1b; }
    body[data-theme="Red"] .settings-table td { border-bottom-color: #fee2e2; color: #7f1d1d; }
    body[data-theme="Soft Gray"] .settings-card { background: #f8fafc; border-color: #dbe2eb; }
    body[data-theme="Soft Gray"] .settings-head { border-bottom-color: #dbe2eb; }
    body[data-theme="Soft Gray"] .settings-head-title { color: #334155; }
    body[data-theme="Soft Gray"] .settings-nav { background: #eef2f7; border-right-color: #dbe2eb; }
    body[data-theme="Soft Gray"] .settings-nav-btn { background: #fff; color: #475569; border-color: #dbe2eb; }
    body[data-theme="Soft Gray"] .settings-nav-btn.active { background: #e2e8f0; border-color: #cbd5e1; color: #334155; }
    body[data-theme="Soft Gray"] .settings-row input, body[data-theme="Soft Gray"] .settings-row select { border-color: #dbe2eb; background: #fff; color: #334155; }
    body[data-theme="Soft Gray"] .people-role-list, body[data-theme="Soft Gray"] .settings-table-wrap { border-color: #dbe2eb; }
    body[data-theme="Soft Gray"] .people-role-row { border-bottom-color: #e5e7eb; color: #475569; }
    body[data-theme="Soft Gray"] .people-role-row.head { background: #f8fafc; color: #475569; }
    @media (max-width: 1650px) {
      .planning-board { grid-template-columns:1fr; }
      .planning-lane.backlog { height:460px; min-height:0; }
      .planning-ops-summary { grid-template-columns:repeat(3, minmax(140px,1fr)); }
    }
    @media (max-width: 1200px) {
      .diagnostics { grid-template-columns: repeat(4, 48px) repeat(2, minmax(150px, 1fr)); }
      #machineGrid { grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); }
      .maintenance-summary { grid-template-columns:repeat(2, minmax(0, 1fr)); }
      #maintenanceTab .maintenance-person { grid-template-columns:64px minmax(0,1fr); }
      #maintenanceTab .maintenance-stats { grid-column:1 / -1; border-left:none; border-top:1px solid #e5ecf4; }
      .archive-metric-grid, .raw-insight-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
    }
    @media (max-width: 900px) {
      .diagnostics { grid-template-columns: repeat(4, 48px) minmax(0, 1fr); }
      .main-tab-button { flex:1 1 140px; }
      .planning-head { display:grid; grid-template-columns:1fr; }
      .planning-ops-summary { grid-template-columns:repeat(2, minmax(0,1fr)); }
      .planning-controls { grid-template-columns:1fr auto auto; }
      .planning-machine-grid { grid-template-columns:1fr; max-height:560px; }
      .planning-machine-grid .planning-dropzone { grid-auto-columns:220px; }
      .planning-machine-grid .planning-dropzone > * { width:220px; min-width:220px; }
      .planning-recommend-list { grid-template-columns:1fr; }
      .machine-detail-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .archive-detail-hero { grid-template-columns:1fr; }
      .archive-detail-hero-side, .planning-left-grid, .detail-chart-grid { grid-template-columns:1fr; }
      .settings-body { grid-template-columns:1fr; }
      .settings-nav { display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); border-right:0; border-bottom:1px solid #dde6f0; }
      .operator-directory-row { grid-template-columns:1fr 1fr; }
      .operator-directory-row.header { display:none; }
      .operator-directory-label { display:block; }
    }
    @media (max-width: 640px) {
      body { font-size:14px; }
      .diagnostics { padding:8px; grid-template-columns:repeat(4, 42px); gap:6px; }
      .server-menu-btn { width:42px; min-width:42px; height:42px; }
      .diag-item { grid-column:1 / -1; }
      .main-tabs { padding:10px 8px; gap:6px; }
      .main-tab-button { flex:1 1 calc(50% - 6px); padding:8px 10px; }
      .main-tab-content { padding:0 8px 10px; }
      .grid { grid-template-columns:repeat(2, minmax(0, 1fr)); gap:8px; }
      #machineGrid { grid-template-columns:repeat(2, minmax(0, 1fr)); }
      .card p { font-size:.78rem; }
      .panel, .planning-shell, #maintenanceTab .maintenance-shell { padding:10px; border-radius:12px; }
      .finished-wrap, .finished-grid, .planning-controls, .planning-machine-grid, .machine-detail-grid, .archive-metric-grid, .raw-insight-grid, .maintenance-summary, .maintenance-list, .maintenance-person, #maintenanceTab .maintenance-person, .operator-detail-grid, .review-subslide.active, .review-group-list { grid-template-columns:1fr; }
      .planning-lane.backlog { min-height:320px; height:auto; }
      .planning-recommend-actions { width:100%; }
      .planning-recommend-actions select, .planning-recommend-actions button { flex:1 1 auto; }
      .overlay-card { width: calc(100vw - 16px); max-height: calc(100vh - 16px); border-radius: 14px; }
      .overlay-body { padding:10px; }
      .overlay-row, #overlayReviewStep .overlay-row, .machine-detail-status-panel .row { grid-template-columns:1fr; }
      #overlayReviewStep { padding:0 42px; max-height:calc(100vh - 170px); }
      #overlayReviewStep, .review-form-card { width:100%; }
      .review-edge-arrow.left { left:6px; }
      .review-edge-arrow.right { right:6px; }
      .people-role-row, .operator-directory-row { grid-template-columns:1fr; gap:6px; padding:10px 12px; }
      .operator-directory-row.header { display:none; }
      .operator-directory-label { display:block; }
      .maintenance-topbar { flex-direction:column; }
      .maintenance-date { text-align:left; white-space:normal; }
      .maintenance-avatar-wrap { border-right:none; border-bottom:1px solid #e5ecf4; }
      .maintenance-stats { border-left:none; border-top:1px solid #e5ecf4; }
    }
    @media (max-width: 420px) {
      .grid { grid-template-columns:1fr; }
      #machineGrid { grid-template-columns:1fr; }
      .main-tab-button { flex-basis:100%; }
      .data-table { min-width:720px; }
      .maintenance-performance-wrap .data-table { min-width:640px; }
      #overlayReviewStep { padding:0 34px; }
    }
  </style>
</head>
<body>
  <div class="diagnostics">
    <button id="serverSettingsBtn" class="server-menu-btn" type="button" aria-label="Open server settings">
      <div class="server-menu-icon"><span></span><span></span><span></span></div>
    </button>
    <button id="operatorsDirectoryBtn" class="server-menu-btn" type="button" aria-label="Open operator directory">
      <img class="menu-ico-img" src="/Images/worker.png" alt="" />
    </button>
    <button id="dailyRolesBtn" class="server-menu-btn" type="button" aria-label="Open people roles">
      <img class="menu-ico-img" src="/Images/admin.ico" alt="" />
    </button>
    <button id="profileCreatorBtn" class="server-menu-btn" type="button" aria-label="Open profile creator">
      <div class="person-menu-icon with-plus"><div class="person-plus-badge">+</div></div>
    </button>
    <div class="diag-item">Client Status<div class="value" id="client-status"><span class="status-dot disconnected"></span>Connecting...</div></div>
    <div class="diag-item">Server Time<div class="value" id="time">N/A</div></div>
    <div class="diag-item">Last Message<div class="value" id="last-message">N/A</div></div>
    <div class="diag-item">Machine Count<div class="value" id="machine-count">0</div></div>
  </div>

  <div class="main-tabs">
    <button class="main-tab-button active" data-target="machinesTab">Machines</button>
    <button class="main-tab-button" data-target="jobQueueTab">Job Queue</button>
    <button class="main-tab-button" data-target="planningTab">Planning</button>
    <button class="main-tab-button" data-target="finishShiftTab">Finish Shift</button>
    <button class="main-tab-button" data-target="finishedJobsTab">Finished Jobs</button>
    <button class="main-tab-button" data-target="archivedJobsTab">Archived Jobs</button>
    <button class="main-tab-button" data-target="machineArchiveTab">Machine Archive</button>
    <button class="main-tab-button" data-target="maintenanceTab">Maintenance</button>
    <button class="main-tab-button" data-target="pdrTab">PDR Reports</button>
  </div>

  <div id="machinesTab" class="main-tab-content active">
    <div class="grid" id="machineGrid"></div>
  </div>

  <div id="jobQueueTab" class="main-tab-content">
    <div class="panel">
      <h3>Job Queue</h3>
      <div class="muted">Live queue from active sessions. ETA shows one estimate from act cycle time and one from live pack cycle time.</div>
      <div id="jobQueueSummary" class="job-queue-summary"></div>
      <div id="jobQueueTableWrap" class="table-wrap"></div>
    </div>
  </div>

  <div id="planningTab" class="main-tab-content">
    <div class="planning-shell">
      <div class="planning-head">
        <div class="planning-title">
          <h3>Planning Board</h3>
          <div class="muted">Scan or type a BMS job/work order, then drag the job card into the machine lane you want to run it on.</div>
          <div id="planningStatus" class="planning-status"></div>
        </div>
        <div class="planning-controls">
          <input id="planningJobInput" type="text" placeholder="Scan or type job / work order..." />
          <button id="planningLookupBtn" type="button">Add Job</button>
          <button id="planningClearBtn" class="secondary" type="button">Clear List</button>
        </div>
      </div>
      <div id="planningOpsSummary" class="planning-ops-summary"></div>
      <div class="planning-board">
        <div class="planning-left-grid">
        <div class="planning-lane backlog">
            <div class="planning-recommend" style="border-top:none;">
              <div class="planning-recommend-head">
                <div>
                  <div class="planning-recommend-title">Jobs & Low Stock</div>
                  <div class="muted">Scanned jobs stay at the top. Drag any item into a machine.</div>
                </div>
                <div class="planning-recommend-actions">
                  <select id="planningLowStockLimit" title="Items to show">
                    <option value="10">10</option>
                    <option value="15" selected>15</option>
                    <option value="25">25</option>
                    <option value="50">50</option>
                  </select>
                  <button id="planningLowStockRefreshBtn" type="button">Refresh</button>
                </div>
              </div>
              <div class="planning-stock-search-row">
                <input id="planningLowStockSearch" type="text" placeholder="Search SKU, product ID, or item name..." />
                <div class="planning-stock-range">
                  <input id="planningLowStockMin" type="number" min="0" step="1" value="0" placeholder="Min stock" title="Minimum stock" />
                  <input id="planningLowStockMax" type="number" min="0" step="1" value="100" placeholder="Max stock" title="Maximum stock" />
                </div>
              </div>
              <div id="planningLowStockList" class="planning-recommend-list">
                <div class="planning-empty">Refresh to load low-stock recommendations.</div>
              </div>
            </div>
        </div>
        </div>
        <div id="planningMachineGrid" class="planning-machine-grid"></div>
      </div>
      <div class="planning-live-queue">
        <div class="planning-live-queue-head">
          <div>
            <div class="planning-live-queue-title">Live Job Queue</div>
            <div class="muted">Active machine jobs with cycle-time ETA used by planning lanes.</div>
          </div>
          <div id="planningQueueHint" class="muted"></div>
        </div>
        <div id="planningQueueTableWrap" class="table-wrap"></div>
      </div>
    </div>
  </div>

  <div id="finishShiftTab" class="main-tab-content">
    <div class="panel">
      <h3>Finish Shift Review</h3>
      <div class="muted">Pending and approved finished shifts saved from Finish Shift scans.</div>
      <div class="sub-tabs">
        <button class="sub-tab-button active" data-target="finishShiftQueuePane" type="button">Finished Shifts</button>
        <button class="sub-tab-button" data-target="finishShiftProgressPane" type="button">Job Progress</button>
      </div>
      <div id="finishShiftQueuePane" class="sub-tab-content active">
        <div id="finishedShiftQueueList" class="finished-wrap"></div>
      </div>
      <div id="finishShiftProgressPane" class="sub-tab-content">
        <div id="finishedShiftJobProgress" class="finished-wrap"></div>
      </div>
    </div>
  </div>

  <div id="finishedJobsTab" class="main-tab-content">
    <div class="panel">
      <h3>Finished Job Confirmation</h3>
      <div class="muted">Closed whole jobs stored from Finish Job QR scans, with approved shift partial context.</div>
      <div id="finishedJobsList" class="finished-wrap"></div>
    </div>
  </div>

  <div id="archivedJobsTab" class="main-tab-content">
    <div class="panel">
      <h3>Archived Jobs</h3>
      <div class="muted">Printed finished jobs archived in row format.</div>
      <div id="archivedJobsTableWrap" class="table-wrap"></div>
    </div>
  </div>

  <div id="machineArchiveTab" class="main-tab-content">
    <div class="panel">
      <h3>Machine Status Archive</h3>
      <div class="muted">Manual machine status overrides with reason, user, and duration.</div>
      <div id="machineStatusArchiveTableWrap" class="table-wrap"></div>
    </div>
    <div class="panel">
      <h3>Downtime Archive</h3>
      <div class="muted">Downtime summaries collected from finished/archived job records (read-only).</div>
      <div id="downtimeArchiveTableWrap" class="table-wrap"></div>
    </div>
  </div>

  <div id="maintenanceTab" class="main-tab-content">
    <div class="maintenance-shell">
      <div class="maintenance-topbar">
        <div>
          <h3>Maintenance Overview</h3>
          <div class="muted">Live availability, active downtime, assignments, and repair performance.</div>
        </div>
        <div id="maintenanceCurrentDate" class="maintenance-date">Accurate current date: -</div>
      </div>
      <div id="maintenanceSummary" class="maintenance-summary"></div>
      <div class="maintenance-call-board">
        <div class="maintenance-call-head">
          <div>
            <h3 class="maintenance-section-title">Maintenance Calls</h3>
            <div class="muted">PDR requests from operators waiting for Maintenance QR are shown here only.</div>
          </div>
          <div id="maintenanceCallCount" class="maintenance-call-count">0 waiting</div>
        </div>
        <div id="maintenanceCallBoard" class="maintenance-call-grid"></div>
      </div>
      <div class="maintenance-live-grid">
        <div>
          <h3 class="maintenance-section-title">Maintenance Team</h3>
          <div class="muted">Current assignment view from Maintenance People and active machine downtime.</div>
          <div id="maintenancePeopleList" class="maintenance-list"></div>
        </div>
      </div>
      <div class="maintenance-performance-panel">
        <h3 class="maintenance-performance-title">Repair Performance</h3>
        <div class="muted">Average repair speed computed from completed downtime records.</div>
        <div id="maintenancePerformanceTableWrap" class="maintenance-performance-wrap"></div>
      </div>
    </div>
  </div>

  <div id="pdrTab" class="main-tab-content">
    <div class="panel">
      <h3>Production Daily Reports</h3>
      <div class="placeholder">PDR table and print-preview placeholder</div>
    </div>
  </div>

  <div id="approvePrintOverlay" class="overlay-backdrop">
    <div class="overlay-card">
      <div class="overlay-head">
        <div class="overlay-title">Approve and Print QR</div>
        <button id="overlayCloseBtn" class="overlay-close" type="button">Close</button>
      </div>
      <div class="overlay-body">
        <div id="overlayReviewStep">
        <div class="review-slide-toolbar">
          <button id="overlayReviewPrevBtn" class="review-slide-arrow review-edge-arrow left" type="button" aria-label="Previous page">‹</button>
          <div id="overlayReviewSlideStatus" class="review-slide-status">Slide 1 / 6</div>
          <button id="overlayReviewNextBtn" class="review-slide-arrow review-edge-arrow right" type="button" aria-label="Next page">›</button>
        </div>
        <div id="reviewSubslide1" class="review-subslide">
          <div class="review-panel">
            <div class="review-panel-title" id="overlayReviewJobInfoDisplay">Finished Job</div>
            <div class="review-panel-body">
              <div class="review-inline-metrics" id="overlayReviewSummaryDisplay"></div>
            </div>
          </div>
          <div class="review-panel">
            <div class="review-panel-title">Reject Details</div>
            <div class="review-panel-body" id="overlayReviewRejectsDisplay"></div>
          </div>
          <input id="overlayReviewJobInfo" type="hidden" />
          <textarea id="overlayReviewSummary" readonly style="display:none;"></textarea>
          <textarea id="overlayReviewRejects" readonly style="display:none;"></textarea>
        </div>
        <div id="reviewSubslide2" class="review-subslide">
          <div class="review-panel">
            <div class="review-panel-title">Reject Details</div>
            <div class="review-panel-body" id="overlayRejectDetailsPageDisplay"></div>
          </div>
        </div>
        <div id="reviewSubslide3" class="review-subslide">
          <div class="review-panel">
            <div class="review-panel-title">Raw Materials</div>
            <div class="review-panel-body" id="overlayRawConsumptionDisplay"></div>
          </div>
        </div>
        <div id="reviewSubslide4" class="review-subslide">
          <div class="review-panel">
            <div class="review-panel-title">Job / Cycle</div>
            <div class="review-panel-body" id="overlayRawCycleSummaryDisplay"></div>
          </div>
          <textarea id="overlayRawConsumption" readonly style="display:none;"></textarea>
          <textarea id="overlayRawCycleSummary" readonly style="display:none;"></textarea>
        </div>
        <div id="reviewSubslide5" class="review-subslide">
          <div class="review-panel">
            <div class="review-panel-title">Downtime</div>
            <div class="review-panel-body" id="overlayDowntimeSummaryDisplay"></div>
          </div>
          <div class="review-panel">
            <div class="review-panel-title">People / Checks</div>
            <div class="review-panel-body" id="overlayPeopleSummaryDisplay"></div>
          </div>
          <textarea id="overlayDowntimeSummary" readonly style="display:none;"></textarea>
          <textarea id="overlayPeopleSummary" readonly style="display:none;"></textarea>
        </div>
        <div id="reviewSubslide6" class="review-subslide">
          <div class="review-panel">
            <div class="review-panel-title">Transfer / Print Requirements</div>
            <div class="review-panel-body" id="overlayTransferPreviewDisplay"></div>
          </div>
          <div class="review-form-card">
          <div class="overlay-row" style="display:none;"><label>Scan QR Input</label><input id="overlayReviewerScanInput" type="text" placeholder="Click 'Open QR Field' then scan..." style="display:none;" /></div>
          <div class="overlay-row"><label>Reviewer (Supervisor/QC QR)</label><input id="overlayReviewerBadge" type="text" placeholder="Scan supervisor/QC QR badge..." /></div>
          <div class="overlay-row"><label>Remarks</label><textarea id="overlayReviewRemarks" placeholder="Remarks required..."></textarea></div>
          <div class="overlay-row"><label>QR Scan Helper</label><button id="overlayOpenScanFieldBtn" class="btn-secondary" type="button">Open QR Field</button></div>
          <div id="overlayDisapproveFields">
            <div class="overlay-row"><label>Pack Count</label><input id="editPackCount" type="number" min="0" /></div>
            <div class="overlay-row"><label>Good</label><input id="editGoodTotal" type="number" min="0" /></div>
            <div class="overlay-row"><label>Butal</label><input id="editButalTotal" type="number" min="0" /></div>
            <div class="overlay-row"><label>Reject</label><input id="editRejectTotal" type="number" min="0" /></div>
            <div class="overlay-row"><label>Total Good</label><input id="editTotalGood" type="number" min="0" /></div>
            <div class="overlay-row"><label>Reject Details JSON</label><textarea id="editRejectBreakdown" placeholder='{"BM":"2","CS":"1"}'></textarea></div>
          </div>
          </div>
        </div>
        </div>

        <div id="overlayQrStep" style="display:none;">
        <div class="overlay-row">
          <label>Review Step</label>
          <input id="overlayQrStageLabel" type="text" readonly value="2 / 2 - QR Print" />
        </div>
        <div class="overlay-row">
          <label>Finished Job</label>
          <input id="overlayJobInfo" type="text" readonly />
        </div>
        <div class="overlay-row">
          <label>Product Name</label>
          <div class="overlay-input-wrap">
            <input id="overlayProductSelect" type="text" autocomplete="off" placeholder="Select or type product name..." />
            <div id="overlayProductSuggest" class="overlay-suggest"></div>
          </div>
        </div>
        <div class="overlay-row">
          <label>QR Payload</label>
          <textarea id="overlayQrPayload" readonly></textarea>
        </div>
        <div class="overlay-row">
          <label>PO Number</label>
          <input id="overlayPoNumber" type="text" placeholder="Enter PO Number..." />
        </div>
        <div class="overlay-row">
          <label>Quantity</label>
          <input id="overlayQty" type="text" readonly />
        </div>
        <div class="overlay-row">
          <label>Index</label>
          <input id="overlayIndex" type="text" readonly />
        </div>
        <div class="overlay-row">
          <label>Total</label>
          <input id="overlayTotal" type="text" readonly />
        </div>
        <div class="overlay-row">
          <label>Lot Number</label>
          <input id="overlayLotNumber" type="text" readonly />
        </div>
        </div>
      </div>
      <div class="overlay-actions">
        <button id="overlayCancelBtn" class="btn-secondary" type="button">Cancel</button>
        <button id="overlayReviewSubmitBtn" class="btn-primary" type="button">Save Review</button>
        <button id="overlayReviewContinueBtn" class="btn-primary" type="button">Approve & Continue</button>
        <button id="overlayBackToReviewBtn" class="btn-secondary" type="button" style="display:none;">Back to Review</button>
        <button id="overlayGenerateBtn" class="btn-primary" type="button">Generate QR Payload</button>
        <button id="overlayRequestBtn" class="btn-primary" type="button">Request Print</button>
      </div>
    </div>
  </div>

  <div id="machineDetailOverlay" class="overlay-backdrop">
    <div class="overlay-card machine-detail-card">
      <div class="overlay-head">
        <div class="overlay-title" id="machineDetailTitle">Machine Details</div>
        <div class="overlay-head-actions">
          <button id="machineDetailSettingsBtn" class="icon-btn" type="button" title="Machine status settings" aria-label="Machine status settings">⚙</button>
          <button id="machineDetailCloseBtn" class="overlay-close" type="button">Close</button>
        </div>
      </div>
      <div id="machineDetailStatusPanel" class="machine-detail-status-panel" style="display:none; margin: 12px 14px 0;">
        <div class="row">
          <label for="machineDetailStatusSelect">Machine Status Override</label>
          <select id="machineDetailStatusSelect">
            <option value="">Auto (Live Status)</option>
            <option value="Working">Working (Clear Override)</option>
            <option value="No schedule">No schedule</option>
            <option value="Scheduled for fix">Scheduled for fix</option>
            <option value="Not working">Not working</option>
          </select>
          <button id="machineDetailStatusSaveBtn" class="btn-primary" type="button">Save</button>
        </div>
        <div class="row" style="grid-template-columns: 160px 1fr;">
          <label for="machineDetailStatusReason">Reason (Required)</label>
          <textarea id="machineDetailStatusReason" placeholder="Enter reason (e.g. waiting parts, no schedule, breakdown details)..."></textarea>
        </div>
        <div class="row" style="grid-template-columns: 160px 1fr;">
          <label for="machineDetailStatusSetterBadge">User QR (Required)</label>
          <input id="machineDetailStatusSetterBadge" type="text" placeholder="Scan user QR badge to confirm..." />
        </div>
        <div id="machineStatusSaveFeedback" class="machine-status-save-feedback">
          <div class="machine-status-save-track"><div id="machineStatusSaveBar" class="machine-status-save-bar"></div></div>
          <div id="machineStatusSaveCheck" class="machine-status-save-check">✓</div>
        </div>
        <div class="hint">Override affects the machine flashcard status label and pulse color (orange) on the dashboard.</div>
      </div>
      <div class="machine-detail-body" id="machineDetailBody"></div>
    </div>
  </div>

  <div id="qrScanCaptureOverlay" class="scan-capture-backdrop">
    <div class="scan-capture-card">
      <div class="scan-capture-title">Waiting for QR Scan</div>
      <div class="scan-capture-sub">Scan Supervisor / QC QR now. It will be applied automatically.</div>
      <input id="qrScanCaptureInput" class="scan-capture-input" type="text" placeholder="Scan here..." />
      <div class="scan-capture-actions">
        <button id="qrScanCaptureCancelBtn" class="btn-secondary" type="button">Cancel</button>
      </div>
    </div>
  </div>

  <div id="operatorDirectoryOverlay" class="settings-overlay">
    <div class="operator-directory-card">
      <div class="operator-directory-head">
        <div>
          <div class="operator-directory-title">Operator Directory</div>
          <div class="operator-directory-sub">Shows about 10 operators at a time. Scroll for the rest.</div>
        </div>
        <button id="operatorDirectoryCloseBtn" class="overlay-close" type="button">Close</button>
      </div>
      <div id="operatorDirectoryGrid" class="operator-directory-grid"></div>
    </div>
  </div>

  <div id="operatorDetailOverlay" class="settings-overlay">
    <div class="operator-detail-card">
      <div class="operator-detail-head">
        <div>
          <div id="operatorDetailTitle" class="operator-detail-title">Operator Details</div>
          <div id="operatorDetailSub" class="operator-detail-sub">Recent machine activity and handled jobs.</div>
        </div>
        <button id="operatorDetailCloseBtn" class="overlay-close" type="button">Close</button>
      </div>
      <div id="operatorDetailBody" class="operator-detail-body"></div>
    </div>
  </div>

  <div id="serverSettingsOverlay" class="settings-overlay">
    <div class="settings-card">
      <div class="settings-head">
        <div class="settings-head-title">Server Settings</div>
        <button id="serverSettingsCloseBtn" class="overlay-close" type="button">Close</button>
      </div>
      <div class="settings-body">
        <div class="settings-nav">
          <button id="settingsNavGeneral" class="settings-nav-btn active" type="button">Settings</button>
          <button id="settingsNavTheme" class="settings-nav-btn" type="button">Theme</button>
          <button id="settingsNavApi" class="settings-nav-btn" type="button">API Configuration</button>
          <button id="settingsNavProfile" class="settings-nav-btn" type="button">Profile</button>
        </div>
        <div class="settings-content">
          <div id="settingsPageGeneral" class="settings-page active">
            <div class="settings-form">
              <div class="settings-row">
                <label>Server Host</label>
                <input id="settingsServerHost" type="text" readonly />
              </div>
              <div class="settings-row">
                <label>Mode</label>
                <input id="settingsServerMode" type="text" readonly value="Dashboard / QR Approval Server" />
              </div>
              <div class="settings-note">General server information and runtime configuration entry point.</div>
            </div>
          </div>
          <div id="settingsPageTheme" class="settings-page">
            <div class="settings-form">
              <div class="settings-row">
                <label>Theme</label>
                <select id="settingsThemeSelect">
                  <option value="Default">Default</option>
                  <option value="Soft Gray">Soft Gray</option>
                  <option value="Blue Accent">Blue Accent</option>
                  <option value="Dark">Dark</option>
                  <option value="Red">Red</option>
                </select>
              </div>
              <div class="settings-note">Theme setting is saved on the server and can be used for future dashboard styling variants.</div>
            </div>
          </div>
          <div id="settingsPageApi" class="settings-page">
            <div class="settings-form">
              <div class="settings-row">
                <label>QR Print API Base URL</label>
                <input id="settingsQrApiBaseUrl" type="text" placeholder="http://192.168.10.166:5000" />
              </div>
              <div class="settings-note">This is used by Request Print (`/api/qrgen/pending-request`) forwarding to your QR system.</div>
              <div class="settings-row" style="margin-top:8px;">
                <label>Product Items Cache (used by QR/product selection)</label>
                <input id="settingsProductsCount" type="text" readonly value="Loading..." />
              </div>
              <div class="settings-row">
                <label>Products Cache Updated</label>
                <input id="settingsProductsUpdated" type="text" readonly value="-" />
              </div>
              <div class="settings-row">
                <label>Products Source File</label>
                <input id="settingsProductsSourceFile" type="text" readonly value="-" />
              </div>
              <div class="settings-row">
                <label>Products Cache File</label>
                <input id="settingsProductsCacheFile" type="text" readonly value="-" />
              </div>
              <div class="settings-row">
                <label>Products Cache Status</label>
                <input id="settingsProductsStatus" type="text" readonly value="-" />
              </div>
              <div class="settings-actions">
                <button id="settingsProductsRefreshBtn" class="btn-secondary" type="button">Update Product Items</button>
                <button id="serverSettingsSaveBtn" class="btn-primary" type="button">Apply Settings</button>
              </div>
            </div>
          </div>
          <div id="settingsPageProfile" class="settings-page">
            <div class="settings-form">
              <div class="settings-note">Saved profiles define company roles and are used for ID detection in today privilege assignment.</div>
              <div class="settings-table-wrap">
                <table class="settings-table">
                  <thead><tr><th>Name</th><th>ID Number</th><th>Company Role</th><th>Date Created</th></tr></thead>
                  <tbody id="settingsProfilesTableBody"><tr><td colspan="4">Loading...</td></tr></tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div id="dailyRolesOverlay" class="settings-overlay">
    <div class="settings-card" style="width:min(760px, calc(100vw - 36px));">
      <div class="settings-head">
        <div class="settings-head-title">Today Supervisor / QC Rights</div>
        <button id="dailyRolesCloseBtn" class="overlay-close" type="button">Close</button>
      </div>
      <div class="settings-content" style="padding:14px;">
        <div class="settings-form">
          <div class="settings-row">
            <label>Scan Supervisor QR</label>
            <input id="dailyRoleBadgeInput" type="text" placeholder="Scan QR badge then press Enter..." />
          </div>
          <div class="settings-row">
            <label>Detected Person</label>
            <input id="dailyRoleNameInput" type="text" placeholder="Auto-filled / editable name" />
          </div>
          <div class="settings-row">
            <label>Detected Company Role</label>
            <input id="dailyRoleCompanyRoleInput" type="text" placeholder="Auto-detected from Profile" readonly />
          </div>
          <div class="settings-row">
            <label>Add Temporary Privilege (Today Only)</label>
            <select id="dailyRoleExtraPrivilegeSelect">
              <option value="none">None</option>
              <option value="supervisor">Add Supervisor Privilege</option>
              <option value="qc">Add QC Privilege</option>
            </select>
          </div>
          <div class="settings-row">
            <label>Effective Privilege for Today</label>
            <input id="dailyRoleEffectiveRightsInput" type="text" readonly value="Viewer" />
          </div>
          <div class="settings-actions">
            <button id="dailyRolesSaveBtn" class="btn-primary" type="button">Save Today Role</button>
          </div>
          <div class="settings-note">Base privilege is from the saved profile role. Add a temporary privilege only for today when someone is covering another function. Daily assignments reset by date automatically.</div>
        </div>
        <div id="dailyRolesList" class="people-role-list" style="margin-top:14px;"></div>
      </div>
    </div>
  </div>

<script>
  const clientStatus = document.getElementById("client-status");
  const serverSettingsBtn = document.getElementById("serverSettingsBtn");
  const operatorsDirectoryBtn = document.getElementById("operatorsDirectoryBtn");
  const dailyRolesBtn = document.getElementById("dailyRolesBtn");
  const profileCreatorBtn = document.getElementById("profileCreatorBtn");
  const operatorDirectoryOverlay = document.getElementById("operatorDirectoryOverlay");
  const operatorDirectoryCloseBtn = document.getElementById("operatorDirectoryCloseBtn");
  const operatorDirectoryGrid = document.getElementById("operatorDirectoryGrid");
  const operatorDetailOverlay = document.getElementById("operatorDetailOverlay");
  const operatorDetailCloseBtn = document.getElementById("operatorDetailCloseBtn");
  const operatorDetailTitle = document.getElementById("operatorDetailTitle");
  const operatorDetailSub = document.getElementById("operatorDetailSub");
  const operatorDetailBody = document.getElementById("operatorDetailBody");
  const serverSettingsOverlay = document.getElementById("serverSettingsOverlay");
  const serverSettingsCloseBtn = document.getElementById("serverSettingsCloseBtn");
  const settingsNavGeneral = document.getElementById("settingsNavGeneral");
  const settingsNavTheme = document.getElementById("settingsNavTheme");
  const settingsNavApi = document.getElementById("settingsNavApi");
  const settingsNavProfile = document.getElementById("settingsNavProfile");
  const settingsPageGeneral = document.getElementById("settingsPageGeneral");
  const settingsPageTheme = document.getElementById("settingsPageTheme");
  const settingsPageApi = document.getElementById("settingsPageApi");
  const settingsPageProfile = document.getElementById("settingsPageProfile");
  const settingsServerHost = document.getElementById("settingsServerHost");
  const settingsThemeSelect = document.getElementById("settingsThemeSelect");
  const settingsQrApiBaseUrl = document.getElementById("settingsQrApiBaseUrl");
  const settingsProductsCount = document.getElementById("settingsProductsCount");
  const settingsProductsUpdated = document.getElementById("settingsProductsUpdated");
  const settingsProductsSourceFile = document.getElementById("settingsProductsSourceFile");
  const settingsProductsCacheFile = document.getElementById("settingsProductsCacheFile");
  const settingsProductsStatus = document.getElementById("settingsProductsStatus");
  const settingsProductsRefreshBtn = document.getElementById("settingsProductsRefreshBtn");
  const settingsProfilesTableBody = document.getElementById("settingsProfilesTableBody");
  const serverSettingsSaveBtn = document.getElementById("serverSettingsSaveBtn");
  const dailyRolesOverlay = document.getElementById("dailyRolesOverlay");
  const dailyRolesCloseBtn = document.getElementById("dailyRolesCloseBtn");
  const dailyRoleBadgeInput = document.getElementById("dailyRoleBadgeInput");
  const dailyRoleNameInput = document.getElementById("dailyRoleNameInput");
  const dailyRoleCompanyRoleInput = document.getElementById("dailyRoleCompanyRoleInput");
  const dailyRoleExtraPrivilegeSelect = document.getElementById("dailyRoleExtraPrivilegeSelect");
  const dailyRoleEffectiveRightsInput = document.getElementById("dailyRoleEffectiveRightsInput");
  const dailyRolesSaveBtn = document.getElementById("dailyRolesSaveBtn");
  const dailyRolesList = document.getElementById("dailyRolesList");
  const timeEl = document.getElementById("time");
  const lastMessageEl = document.getElementById("last-message");
  const machineCountEl = document.getElementById("machine-count");
  const machineGrid = document.getElementById("machineGrid");
  const jobQueueSummary = document.getElementById("jobQueueSummary");
  const jobQueueTableWrap = document.getElementById("jobQueueTableWrap");
  const planningJobInput = document.getElementById("planningJobInput");
  const planningLookupBtn = document.getElementById("planningLookupBtn");
  const planningClearBtn = document.getElementById("planningClearBtn");
  const planningStatus = document.getElementById("planningStatus");
  const planningOpsSummary = document.getElementById("planningOpsSummary");
  const planningMachineGrid = document.getElementById("planningMachineGrid");
  const planningQueueHint = document.getElementById("planningQueueHint");
  const planningQueueTableWrap = document.getElementById("planningQueueTableWrap");
  const planningLowStockLimit = document.getElementById("planningLowStockLimit");
  const planningLowStockSearch = document.getElementById("planningLowStockSearch");
  const planningLowStockMin = document.getElementById("planningLowStockMin");
  const planningLowStockMax = document.getElementById("planningLowStockMax");
  const planningLowStockRefreshBtn = document.getElementById("planningLowStockRefreshBtn");
  const planningLowStockList = document.getElementById("planningLowStockList");
  const finishedShiftQueueList = document.getElementById("finishedShiftQueueList");
  const finishedShiftJobProgress = document.getElementById("finishedShiftJobProgress");
  const finishedJobsList = document.getElementById("finishedJobsList");
  const archivedJobsTableWrap = document.getElementById("archivedJobsTableWrap");
  const machineStatusArchiveTableWrap = document.getElementById("machineStatusArchiveTableWrap");
  const downtimeArchiveTableWrap = document.getElementById("downtimeArchiveTableWrap");
  const maintenanceSummary = document.getElementById("maintenanceSummary");
  const maintenanceCallBoard = document.getElementById("maintenanceCallBoard");
  const maintenanceCallCount = document.getElementById("maintenanceCallCount");
  const maintenancePeopleList = document.getElementById("maintenancePeopleList");
  const maintenancePerformanceTableWrap = document.getElementById("maintenancePerformanceTableWrap");
  const maintenanceCurrentDate = document.getElementById("maintenanceCurrentDate");
  const approvePrintOverlay = document.getElementById("approvePrintOverlay");
  const overlayCloseBtn = document.getElementById("overlayCloseBtn");
  const overlayCancelBtn = document.getElementById("overlayCancelBtn");
  const overlayGenerateBtn = document.getElementById("overlayGenerateBtn");
  const overlayRequestBtn = document.getElementById("overlayRequestBtn");
  const overlayJobInfo = document.getElementById("overlayJobInfo");
  const overlayReviewJobInfo = document.getElementById("overlayReviewJobInfo");
  const overlayReviewJobInfoDisplay = document.getElementById("overlayReviewJobInfoDisplay");
  const overlayReviewSummary = document.getElementById("overlayReviewSummary");
  const overlayReviewRejects = document.getElementById("overlayReviewRejects");
  const overlayReviewSummaryDisplay = document.getElementById("overlayReviewSummaryDisplay");
  const overlayReviewRejectsDisplay = document.getElementById("overlayReviewRejectsDisplay");
  const overlayRejectDetailsPageDisplay = document.getElementById("overlayRejectDetailsPageDisplay");
  const overlayRawConsumption = document.getElementById("overlayRawConsumption");
  const overlayRawCycleSummary = document.getElementById("overlayRawCycleSummary");
  const overlayDowntimeSummary = document.getElementById("overlayDowntimeSummary");
  const overlayPeopleSummary = document.getElementById("overlayPeopleSummary");
  const overlayRawConsumptionDisplay = document.getElementById("overlayRawConsumptionDisplay");
  const overlayRawCycleSummaryDisplay = document.getElementById("overlayRawCycleSummaryDisplay");
  const overlayDowntimeSummaryDisplay = document.getElementById("overlayDowntimeSummaryDisplay");
  const overlayPeopleSummaryDisplay = document.getElementById("overlayPeopleSummaryDisplay");
  const overlayReviewerBadge = document.getElementById("overlayReviewerBadge");
  const overlayReviewerScanInput = document.getElementById("overlayReviewerScanInput");
  const overlayOpenScanFieldBtn = document.getElementById("overlayOpenScanFieldBtn");
  const overlayReviewRemarks = document.getElementById("overlayReviewRemarks");
  const overlayReviewAction = document.getElementById("overlayReviewAction");
  const overlayDisapproveFields = document.getElementById("overlayDisapproveFields");
  const editPackCount = document.getElementById("editPackCount");
  const editGoodTotal = document.getElementById("editGoodTotal");
  const editButalTotal = document.getElementById("editButalTotal");
  const editRejectTotal = document.getElementById("editRejectTotal");
  const editTotalGood = document.getElementById("editTotalGood");
  const editRejectBreakdown = document.getElementById("editRejectBreakdown");
  const overlayReviewSubmitBtn = document.getElementById("overlayReviewSubmitBtn");
  const overlayReviewContinueBtn = document.getElementById("overlayReviewContinueBtn");
  const overlayBackToReviewBtn = document.getElementById("overlayBackToReviewBtn");
  const overlayReviewStep = document.getElementById("overlayReviewStep");
  const overlayQrStep = document.getElementById("overlayQrStep");
  const overlayReviewPrevBtn = document.getElementById("overlayReviewPrevBtn");
  const overlayReviewNextBtn = document.getElementById("overlayReviewNextBtn");
  const overlayReviewSlideStatus = document.getElementById("overlayReviewSlideStatus");
  const reviewSubslide1 = document.getElementById("reviewSubslide1");
  const reviewSubslide2 = document.getElementById("reviewSubslide2");
  const reviewSubslide3 = document.getElementById("reviewSubslide3");
  const reviewSubslide4 = document.getElementById("reviewSubslide4");
  const reviewSubslide5 = document.getElementById("reviewSubslide5");
  const reviewSubslide6 = document.getElementById("reviewSubslide6");
  const overlayTransferPreviewDisplay = document.getElementById("overlayTransferPreviewDisplay");
  const overlayProductSelect = document.getElementById("overlayProductSelect");
  const overlayProductSuggest = document.getElementById("overlayProductSuggest");
  const overlayQrPayload = document.getElementById("overlayQrPayload");
  const overlayPoNumber = document.getElementById("overlayPoNumber");
  const overlayQty = document.getElementById("overlayQty");
  const overlayIndex = document.getElementById("overlayIndex");
  const overlayTotal = document.getElementById("overlayTotal");
  const overlayLotNumber = document.getElementById("overlayLotNumber");
  const overlayPoNumberRow = overlayPoNumber ? overlayPoNumber.closest(".overlay-row") : null;
  const machineDetailOverlay = document.getElementById("machineDetailOverlay");
  const machineDetailSettingsBtn = document.getElementById("machineDetailSettingsBtn");
  const machineDetailCloseBtn = document.getElementById("machineDetailCloseBtn");
  const machineDetailTitle = document.getElementById("machineDetailTitle");
  const machineDetailStatusPanel = document.getElementById("machineDetailStatusPanel");
  const machineDetailStatusSelect = document.getElementById("machineDetailStatusSelect");
  const machineDetailStatusReason = document.getElementById("machineDetailStatusReason");
  const machineDetailStatusSetterBadge = document.getElementById("machineDetailStatusSetterBadge");
  const machineDetailStatusSaveBtn = document.getElementById("machineDetailStatusSaveBtn");
  const machineStatusSaveFeedback = document.getElementById("machineStatusSaveFeedback");
  const machineStatusSaveBar = document.getElementById("machineStatusSaveBar");
  const machineStatusSaveCheck = document.getElementById("machineStatusSaveCheck");
  const machineDetailBody = document.getElementById("machineDetailBody");
  const qrScanCaptureOverlay = document.getElementById("qrScanCaptureOverlay");
  const qrScanCaptureInput = document.getElementById("qrScanCaptureInput");
  const qrScanCaptureCancelBtn = document.getElementById("qrScanCaptureCancelBtn");
  const MACHINE_NAME_MAP = {
    "M00001": "IMM 301",
    "M00002": "IMM 302",
    "M00003": "IMM 303",
    "M00004": "IMM 304",
    "M00005": "IMM 305",
    "M00006": "IMM 306",
    "M00007": "IMM 307",
    "M00008": "IMM 308",
    "M00009": "IMM 309",
    "M00010": "IMM 310",
    "M00011": "IMM 311",
    "M00012": "IMM 312",
    "M00013": "IMM 313",
    "M00014": "IMM 314",
    "M00015": "IMM 315",
    "M00016": "IMM 316",
    "M00017": "IMM 317",
    "M00018": "IMM 318",
    "M00019": "IMM 319",
    "M00020": "IMM 320",
    "M00021": "IMM 321",
  };
  const DEFAULT_MACHINE_CODES = Object.keys(MACHINE_NAME_MAP);
  let latestState = { sessions: [], active_ttl_seconds: 30 };
  let planningBoard = { lanes: { BACKLOG: [] }, updated_at_utc: "" };
  let planningSaveTimer = null;
  let planningLocalDirty = false;
  let planningDragActive = false;
  let planningDeferredState = null;
  let planningDropCompleted = false;
  let planningMachineDropScrollLeft = {};
  let planningMachineScrollActiveUntil = 0;
  let operatorDirectoryState = [];
  const machineCardEls = new Map();
  const machineLinkageDisplayIndex = new Map();
  const machineLinkageFlipTimers = new Map();
  let finishedJobsState = [];
  let finishedShiftState = [];
  let archivedJobsState = [];
  let machineStatusArchiveState = [];
  let maintenanceCardIndexByKey = {};
  let finishedJobsInteractionLock = false;
  let pendingFinishedJobsRows = null;
  let productItems = [];
  let activeJobRow = null;
  let productsHydrated = false;
  let productSuggestionItems = [];
  let productSuggestionIndex = -1;
  const PRODUCT_SUGGEST_LIMIT = 8;
  let lowStockItemsState = [];
  let generatedQrState = {
    jobKey: "",
    payload: "",
    qty: "",
    index: "",
    total: "",
    lotNumber: "",
    stageLabel: "",
    stageKind: "",
    plan: [],
    planIndex: 0,
    printRequests: [],
  };
  let overlayReviewSavedApproved = false;
  let reviewSlideIndex = 0;
  let overlayReviewMode = "job";
  let serverSettingsState = { theme: "Default", qrgen_base_url: "" };
  let dailyRolesState = {};
  let settingsProfilesState = [];
  let machineStatusOverridesState = {};
  let activeMachineDetailCode = "";

  function esc(s){ return (s ?? "").toString().replaceAll("&","&amp;").replaceAll("<","&lt;"); }
  function escJson(v){
    try { return esc(JSON.stringify(v ?? {}, null, 2)); } catch { return esc(String(v ?? "")); }
  }

  function isMaintenanceSession(session){
    if(!session || typeof session !== "object") return false;
    return !!(
      session.downtime_active ||
      session.waiting_downtime_start_maintenance ||
      session.waiting_pdr_maintenance_reason ||
      session.waiting_downtime_end_maintenance ||
      session.waiting_maintenance_qr ||
      Number(session.downtime_wait_started_at || 0) > 0
    );
  }

  function statusClass(lastSeenUtc, activeTtlSeconds = 30, manualStatus = "", session = null){
    if(String(manualStatus || "").trim()) return "maintenance";
    if(!lastSeenUtc) return "disconnected";
    const seen = new Date(lastSeenUtc).getTime();
    if(Number.isNaN(seen)) return "disconnected";
    const ageSec = (Date.now() - seen) / 1000;
    const connected = ageSec <= Number(activeTtlSeconds || 30);
    if(!connected) return "disconnected";
    return isMaintenanceSession(session) ? "maintenance" : "active";
  }

  function fmtDateLocal(iso){
    if(!iso) return "-";
    const d = new Date(iso);
    if(Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleString();
  }

  function fmtDowntimeSeconds(s){
    const n = Number(s);
    if(!Number.isFinite(n) || n < 0) return "-";
    const t = Math.floor(n);
    const hh = Math.floor(t / 3600);
    const mm = Math.floor((t % 3600) / 60);
    const ss = t % 60;
    return `${String(hh).padStart(2,"0")}:${String(mm).padStart(2,"0")}:${String(ss).padStart(2,"0")}`;
  }

  function extractJobRecord(session){
    const payload = (session && typeof session.job_payload === "object" && session.job_payload) || {};
    if(payload.data && payload.data.job && typeof payload.data.job === "object") return payload.data.job;
    if(payload.job && typeof payload.job === "object") return payload.job;
    return payload;
  }

  function detailItem(label, value){
    return `<div class="machine-detail-item"><div class="k">${esc(label)}</div><div class="v">${esc(value ?? "-")}</div></div>`;
  }

  function archiveMetric(label, value, tone = ""){
    return `<div class="archive-metric ${esc(tone)}"><div class="k">${esc(label)}</div><div class="v">${esc(value ?? "-")}</div></div>`;
  }

  function pctPart(value, total){
    const n = Math.max(0, Number(value || 0));
    const t = Math.max(0, Number(total || 0));
    if(t <= 0 || n <= 0) return 0;
    return Math.max(1, Math.min(100, Math.round((n / t) * 100)));
  }

  function productionVisualHtml(row){
    const r = row || {};
    const good = Math.max(0, Number(r.good_total ?? r.good ?? 0));
    const butal = Math.max(0, Number(r.butal_total ?? r.butal ?? 0));
    const reject = Math.max(0, Number(r.reject_total ?? r.reject ?? 0));
    const noShot = Math.max(0, Number(r.no_shot_total ?? r.no_shot ?? 0));
    const total = good + butal + reject + noShot;
    const goodPct = pctPart(good, total);
    const butalPct = pctPart(butal, total);
    const rejectPct = pctPart(reject, total);
    const noShotPct = pctPart(noShot, total);
    return `
      <div class="detail-chart-grid">
        <div class="detail-chart-card">
          <div class="head"><div class="title">Production Mix</div><div class="value">${esc(total)} pcs</div></div>
          <div class="detail-bar" title="Good ${good}, Butal ${butal}, Reject ${reject}, No Shot ${noShot}">
            <div class="detail-bar-seg good" style="width:${goodPct}%"></div>
            <div class="detail-bar-seg butal" style="width:${butalPct}%"></div>
            <div class="detail-bar-seg reject" style="width:${rejectPct}%"></div>
            <div class="detail-bar-seg noshot" style="width:${noShotPct}%"></div>
          </div>
          <div class="detail-bar-legend">
            <span class="detail-legend-item"><span class="detail-dot good"></span>Good ${esc(good)}</span>
            <span class="detail-legend-item"><span class="detail-dot butal"></span>Butal ${esc(butal)}</span>
            <span class="detail-legend-item"><span class="detail-dot reject"></span>Reject ${esc(reject)}</span>
            <span class="detail-legend-item"><span class="detail-dot noshot"></span>No Shot ${esc(noShot)}</span>
          </div>
        </div>
        <div class="detail-chart-card">
          <div class="head"><div class="title">Quality Signal</div><div class="value">${esc(total ? Math.round(((good + butal) / total) * 100) : 0)}%</div></div>
          <div class="detail-progress">
            <div class="detail-progress-row"><span>Good</span><div class="detail-progress-track"><div class="detail-progress-fill" style="width:${goodPct}%"></div></div><span>${goodPct}%</span></div>
            <div class="detail-progress-row"><span>Butal</span><div class="detail-progress-track"><div class="detail-progress-fill warn" style="width:${butalPct}%"></div></div><span>${butalPct}%</span></div>
            <div class="detail-progress-row"><span>Reject</span><div class="detail-progress-track"><div class="detail-progress-fill bad" style="width:${rejectPct}%"></div></div><span>${rejectPct}%</span></div>
          </div>
        </div>
      </div>
    `;
  }

  function firstValue(...values){
    for(const value of values){
      if(value !== undefined && value !== null && String(value).trim() !== "") return value;
    }
    return "";
  }

  function normalizedArchiveArray(value){
    if(Array.isArray(value)) return value;
    if(value && typeof value === "object") return [value];
    return [];
  }

  function archivedMaterialRows(session){
    const rawScans = Array.isArray(session.raw_material_scans) ? session.raw_material_scans : [];
    const rawLogs = Array.isArray(session.raw_material_logs) ? session.raw_material_logs : [];
    const max = Math.max(rawScans.length, rawLogs.length);
    const rows = [];
    for(let i = 0; i < max; i += 1){
      const scan = rawScans[i];
      const log = rawLogs[i];
      const scanText = typeof scan === "string" ? scan : "";
      const scanObj = (scan && typeof scan === "object") ? scan : {};
      const logObj = (log && typeof log === "object") ? log : {};
      rows.push({
        index: i + 1,
        material: firstValue(
          logObj.material_name, logObj.material, logObj.product_name, logObj.code, logObj.value,
          scanObj.material_name, scanObj.material, scanObj.product_name, scanObj.code, scanObj.value,
          scanText
        ) || "-",
        qty: firstValue(logObj.qty, logObj.quantity, scanObj.qty, scanObj.quantity) || "-",
        lot: firstValue(logObj.lot_number, logObj.lot, scanObj.lot_number, scanObj.lot) || "-",
        time: firstValue(logObj.timestamp_utc, logObj.scanned_at, scanObj.timestamp_utc, scanObj.scanned_at) || "",
      });
    }
    return rows;
  }

  function rawPartRows(row){
    const item = (row && typeof row === "object") ? row : {};
    const payload = (item.job_payload && typeof item.job_payload === "object") ? item.job_payload : {};
    const data = (payload.data && typeof payload.data === "object") ? payload.data : {};
    const details = (data.job_details && typeof data.job_details === "object") ? data.job_details : {};
    const candidates = [
      Array.isArray(data.parts) ? data.parts : null,
      Array.isArray(details.parts) ? details.parts : null,
      Array.isArray(details.part_ids) ? details.part_ids : null,
      details.part_ids && typeof details.part_ids === "object" ? [details.part_ids] : null,
      Array.isArray(data.part_ids) ? data.part_ids : null,
      Array.isArray(payload.part_ids) ? payload.part_ids : null,
    ].filter(Boolean);
    for(const rows of candidates){
      const clean = rows.filter(x => x && typeof x === "object");
      if(clean.length) return clean;
    }
    return [];
  }

  function materialLabel(row){
    const x = row || {};
    return firstValue(x.material_name, x.material, x.name, x.part_name, x.product_name, x.description, x.sku, x.part_code, x.product_code, x.code, x.value, "-");
  }

  function materialKeyText(value){
    return String(value || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
  }

  function rawMaterialInsightsHtml(row){
    const item = (row && typeof row === "object") ? row : {};
    const materialRows = archivedMaterialRows(item);
    const parts = rawPartRows(item);
    const totalGood = Number(item.total_good ?? item.partial_qty ?? ((Number(item.good_total || 0) + Number(item.butal_total || 0))));
    const scannedQty = materialRows.reduce((sum, x) => sum + Math.max(0, Number(x.qty || 0)), 0);
    const expectedQty = parts.reduce((sum, part) => {
      const perUnit = Number(part.part_qty_per_unit || part.qty_per_unit || 0);
      const fixedQty = Number(part.request_part_qty || part.required_qty || part.qty || part.quantity || 0);
      return sum + Math.max(0, perUnit > 0 ? perUnit * totalGood : fixedQty);
    }, 0);
    const estimatedUsed = expectedQty > 0 ? Math.min(scannedQty, expectedQty) : "";
    const estimatedExcess = expectedQty > 0 ? Math.max(0, scannedQty - expectedQty) : "";
    const partMatches = parts.map(part => {
      const keys = [part.sku, part.name, part.part_name, part.material_name, part.product_name, part.description, part.part_code, part.product_code, part.code]
        .map(materialKeyText).filter(Boolean);
      const scanned = materialRows.reduce((sum, raw) => {
        const rawKeys = [raw.material, raw.lot].map(materialKeyText).filter(Boolean);
        const hit = keys.length && rawKeys.some(k => keys.some(pk => k.includes(pk) || pk.includes(k)));
        return hit ? sum + Math.max(0, Number(raw.qty || 0)) : sum;
      }, 0);
      const perUnit = Number(part.part_qty_per_unit || part.qty_per_unit || 0);
      const required = Math.max(0, perUnit > 0 ? perUnit * totalGood : Number(part.request_part_qty || part.required_qty || part.qty || part.quantity || 0));
      const status = required <= 0 ? "info" : (scanned >= required ? "good" : (scanned > 0 ? "warn" : "bad"));
      const statusText = required <= 0 ? "No target" : (scanned >= required ? "Covered" : (scanned > 0 ? "Short" : "Missing"));
      return { part, scanned, required, status, statusText };
    });
    const cards = `
      <div class="raw-insight-grid">
        <div class="raw-insight-card ${materialRows.length ? "good" : "bad"}"><div class="k">Scanned Bags</div><div class="v">${esc(materialRows.length)}</div></div>
        <div class="raw-insight-card"><div class="k">Scanned Qty</div><div class="v">${esc(scannedQty || "-")}</div></div>
        <div class="raw-insight-card"><div class="k">Expected Use</div><div class="v">${esc(expectedQty || "-")}</div></div>
        <div class="raw-insight-card ${Number(estimatedExcess || 0) > 0 ? "warn" : "good"}"><div class="k">Est. Excess</div><div class="v">${esc(estimatedExcess === "" ? "-" : estimatedExcess)}</div></div>
      </div>
    `;
    const coverage = partMatches.length ? `
      <div class="raw-match-list">
        ${partMatches.map(x => `
          <div class="raw-match-item">
            <div class="raw-match-top">
              <div class="raw-match-name">${esc(materialLabel(x.part))}</div>
              <span class="raw-match-status ${esc(x.status)}">${esc(x.statusText)}</span>
            </div>
            <div class="raw-match-meta">
              <span>Required: ${esc(x.required || "-")}</span>
              <span>Scanned: ${esc(x.scanned || 0)}</span>
              <span>Per Unit: ${esc(x.part.part_qty_per_unit || x.part.qty_per_unit || "-")}</span>
              <span>Code: ${esc(x.part.sku || x.part.part_code || x.part.product_code || x.part.code || "-")}</span>
            </div>
          </div>
        `).join("")}
      </div>
    ` : `<div class="machine-detail-empty">No target raw material list found from the Job API.</div>`;
    const table = tableFromRows(materialRows, [
      { label: "#", value: x => x.index },
      { label: "Material / Scan", value: x => x.material },
      { label: "Qty", value: x => x.qty },
      { label: "Lot", value: x => x.lot },
      { label: "Scanned At", value: x => fmtDateLocal(x.time || "") },
    ], "No raw materials scanned.", 12);
    return `
      ${cards}
      <div class="review-group-list">
        <div class="review-group-card wide">
          <div class="review-group-head">Scanned Materials</div>
          <div class="review-group-body">${table}</div>
        </div>
        <div class="review-group-card wide">
          <div class="review-group-head">Material Coverage</div>
          <div class="review-group-body">${coverage}</div>
        </div>
      </div>
    `;
  }

  function archivePrintRows(session){
    const row = (session && session._archive_row && typeof session._archive_row === "object") ? session._archive_row : session;
    const payloads = [
      ...normalizedArchiveArray(row.print_request_payloads),
      ...normalizedArchiveArray(row.print_request_payload),
      ...normalizedArchiveArray(row.printed_qr_payload),
    ].filter(Boolean);
    return payloads.map((item, idx) => {
      const obj = (item && typeof item === "object") ? item : {};
      const plan = Array.isArray(obj.plan) ? obj.plan : [];
      const firstPlan = plan.find(x => x && typeof x === "object") || {};
      return {
        index: idx + 1,
        stage: firstValue(obj.qr_stage_label, obj.stage_label, obj.stage, firstPlan.label, firstPlan.stage, firstPlan.kind, "Print Request"),
        product: firstValue(obj.product_name, obj.product_id, firstPlan.product_name, firstPlan.product_id, obj.product, "-"),
        qty: firstValue(obj.qty, obj.quantity, firstPlan.qty, firstPlan.quantity, "-"),
        po: firstValue(obj.po_number, firstPlan.po_number, "-"),
        lot: firstValue(obj.lot_number, firstPlan.lot_number, "-"),
        printed_at: firstValue(obj.printed_at_utc, obj.created_at_utc, row.printed_at_utc, row.archived_at_utc, ""),
      };
    });
  }

  function renderArchivedMachineDetail(session){
    const job = extractJobRecord(session) || {};
    const row = (session && session._archive_row && typeof session._archive_row === "object") ? session._archive_row : {};
    const totalGood = Number(row.total_good ?? (Number(session.good_total || 0) + Number(session.butal_total || 0)));
    const rejectRows = Object.entries((session.reject_breakdown && typeof session.reject_breakdown === "object") ? session.reject_breakdown : {})
      .sort((a,b) => String(a[0]).localeCompare(String(b[0])))
      .map(([reason, qty]) => ({reason, qty}));
    const materialRows = archivedMaterialRows(session);
    const scannedRawQty = materialRows.reduce((sum, x) => sum + Math.max(0, Number(x.qty || 0)), 0);
    const part = primaryRawPart(row);
    const perUnit = Number(part.part_qty_per_unit || 0);
    const estimatedUsed = perUnit > 0 ? totalGood * perUnit : 0;
    const estimatedExcess = estimatedUsed > 0 ? Math.max(0, scannedRawQty - estimatedUsed) : "";
    const printRows = archivePrintRows(session);
    const reviewLogs = Array.isArray(row.reject_review_logs) ? row.reject_review_logs : [];
    const approvedBy = row.supervisor_name || row.qc_name || (reviewLogs.find(x => x?.actor_name)?.actor_name) || "-";
    machineDetailTitle.textContent = `${session.machine_name || session.machine_code || "Archived Job"} Archive`;
    if(machineDetailSettingsBtn) machineDetailSettingsBtn.style.display = "none";
    if(machineDetailStatusPanel) machineDetailStatusPanel.style.display = "none";
    machineDetailBody.innerHTML = `
      <div class="archive-detail-hero">
        <div>
          <h3>${esc(session.job_name || session.job_code || "Archived Job")}</h3>
          <div class="sub">${esc(session.machine_name || session.machine_code || "-")} | Job ${esc(session.job_code || "-")}</div>
          <div class="archive-pill-row">
            <span class="archive-pill">${esc(row.archive_status || "Archived")}</span>
            <span class="archive-pill">Printed ${esc(fmtDateLocal(row.printed_at_utc || ""))}</span>
            <span class="archive-pill">Operator ${esc(displayNameForId(session.operator_id || "-"))}</span>
          </div>
        </div>
        <div class="archive-detail-hero-side">
          <div class="archive-hero-stat"><div class="k">Total Good</div><div class="v">${esc(totalGood)}</div></div>
          <div class="archive-hero-stat"><div class="k">Butal</div><div class="v">${esc(session.butal_total || 0)}</div></div>
          <div class="archive-hero-stat"><div class="k">Raw Sacks</div><div class="v">${esc(session.raw_sacks_count || materialRows.length || 0)}</div></div>
          <div class="archive-hero-stat"><div class="k">Printed QR</div><div class="v">${esc(printRows.length || (row.printed_qr_payload ? 1 : 0))}</div></div>
        </div>
      </div>
      <div class="machine-detail-section">
        <h4>Job Summary</h4>
        <div class="machine-detail-grid">
          ${detailItem("Machine", session.machine_code || "-")}
          ${detailItem("Machine Name", session.machine_name || "-")}
          ${detailItem("Archive Status", row.archive_status || "Archived")}
          ${detailItem("Job Code", session.job_code || "-")}
          ${detailItem("Job Name", session.job_name || "-")}
          ${detailItem("Job Ref", job.ref_no || job.reference || job.id || "-")}
          ${detailItem("Product ID", job.product_id || "-")}
          ${detailItem("Mold", job.custom_05 || "-")}
          ${detailItem("Color", job.custom_06 || "-")}
          ${detailItem("System Code", job.custom_09 || "-")}
          ${detailItem("Target / Cavity Info", job.custom_11 || "-")}
          ${detailItem("Approved By", approvedBy)}
          ${detailItem("Finished At", fmtDateLocal(row.finished_at_utc || ""))}
          ${detailItem("Printed At", fmtDateLocal(row.printed_at_utc || ""))}
          ${detailItem("Archived At", fmtDateLocal(row.archived_at_utc || ""))}
        </div>
      </div>
      <div class="machine-detail-section">
        <h4>Production Summary</h4>
        <div class="archive-metric-grid">
          ${archiveMetric("Pack", Number(row.pack_count ?? session.pack_total ?? 0))}
          ${archiveMetric("Good", Number(session.good_total || 0), "good")}
          ${archiveMetric("Butal", Number(session.butal_total || 0), Number(session.butal_total || 0) > 0 ? "warn" : "")}
          ${archiveMetric("Reject", Number(session.reject_total || 0), Number(session.reject_total || 0) > 0 ? "bad" : "")}
          ${archiveMetric("No Shot", Number(session.no_shot_total || 0))}
          ${archiveMetric("Total Good", totalGood, "good")}
          ${archiveMetric("Startup Reject", Number(session.startup_reject_total || 0))}
          ${archiveMetric("Cycle Time", session.cycle_time_current || "-")}
        </div>
        ${productionVisualHtml(session)}
      </div>
      <div class="machine-detail-section">
        <h4>Raw Materials</h4>
        ${rawMaterialInsightsHtml(row)}
      </div>
      <div class="machine-detail-section">
        <h4>Transfer / Print Records</h4>
        ${tableFromRows(printRows, [
          { label: "#", value: x => x.index },
          { label: "Stage", value: x => x.stage },
          { label: "Product", value: x => x.product },
          { label: "Qty", value: x => x.qty },
          { label: "PO", value: x => x.po },
          { label: "Lot", value: x => x.lot },
          { label: "Printed At", value: x => fmtDateLocal(x.printed_at || "") },
        ], "No print request payload recorded.", 8)}
      </div>
      <div class="machine-detail-section">
        <h4>Rejects & Downtime</h4>
        <div class="review-group-list">
          <div class="review-group-card">
            <div class="review-group-head">Reject Breakdown</div>
            <div class="review-group-body">${tableFromRows(rejectRows, [
              { label: "Reason", value: x => x.reason },
              { label: "Qty", value: x => x.qty },
            ], "No reject details recorded.", 8)}</div>
          </div>
          <div class="review-group-card">
            <div class="review-group-head">Downtime</div>
            <div class="review-group-body">
              <div class="machine-detail-grid">
                ${detailItem("Reason Code", session.downtime_reason_code || "-")}
                ${detailItem("Reason", session.downtime_reason_text || "-")}
                ${detailItem("Duration", fmtDowntimeSeconds(session.downtime_last_seconds))}
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="machine-detail-section">
        <h4>Job API Details</h4>
        <div class="machine-detail-grid">
          ${detailItem("Customer", job.customer_02 || job.customer || "-")}
          ${detailItem("Status", job.status || "-")}
          ${detailItem("Remarks", job.remarks || "-")}
        </div>
        <details class="archive-raw-details">
          <summary>Show raw Job API payload</summary>
          <div class="machine-detail-code" style="margin-top:8px;">${escJson(session.job_payload || {})}</div>
        </details>
      </div>
    `;
    machineDetailOverlay.classList.add("active");
  }

  function machineStatusOverrideFor(code){
    const c = String(code || "").trim();
    return (machineStatusOverridesState && machineStatusOverridesState[c]) || null;
  }

  function openMachineDetail(session){
    if(!session) return;
    if(session._is_archived_detail){
      activeMachineDetailCode = String(session.machine_code || "").trim();
      renderArchivedMachineDetail(session);
      return;
    }
    activeMachineDetailCode = String(session.machine_code || "").trim();
    if(machineDetailSettingsBtn) machineDetailSettingsBtn.style.display = "";
    const activeTtlSeconds = Number((latestState && latestState.active_ttl_seconds) || 30);
    const manual = machineStatusOverrideFor(activeMachineDetailCode);
    const manualStatus = String((manual && manual.status) || "").trim();
    const manualReason = String((manual && manual.reason) || "").trim();
    const status = manualStatus || statusClass(session.last_seen_utc, activeTtlSeconds, "", session).toUpperCase();
    const maintenanceMode = isMaintenanceSession(session);
    const totalGood = Number(session.good_total || 0) + Number(session.butal_total || 0);
    const job = extractJobRecord(session) || {};
    const rejectBreakdown = (session && typeof session.reject_breakdown === "object" && session.reject_breakdown) || {};
    const rejectRows = Object.entries(rejectBreakdown).sort((a,b) => String(a[0]).localeCompare(String(b[0])));
    const rawScans = Array.isArray(session.raw_material_scans) ? session.raw_material_scans : [];
    const rawLogs = Array.isArray(session.raw_material_logs) ? session.raw_material_logs : [];
    const materialRows = archivedMaterialRows(session);
    const scannedRawQty = materialRows.reduce((sum, x) => sum + Math.max(0, Number(x.qty || 0)), 0);
    const activeJobSummaryHtml = session.job_code || session.job_name ? `
      <div class="archive-detail-hero">
        <div>
          <h3>${esc(session.job_name || session.job_code || "Active Job")}</h3>
          <div class="sub">${esc(session.machine_name || session.machine_code || "-")} | Job ${esc(session.job_code || "-")}</div>
          <div class="archive-pill-row">
            <span class="archive-pill">${esc(status)}</span>
            <span class="archive-pill">Operator ${esc(displayNameForId(session.operator_id || "-"))}</span>
            <span class="archive-pill">Raw Bags ${esc(session.raw_sacks_count || materialRows.length || 0)}</span>
          </div>
        </div>
        <div class="archive-detail-hero-side">
          <div class="archive-hero-stat"><div class="k">Good</div><div class="v">${esc(session.good_total || 0)}</div></div>
          <div class="archive-hero-stat"><div class="k">Butal</div><div class="v">${esc(session.butal_total || 0)}</div></div>
          <div class="archive-hero-stat"><div class="k">Reject</div><div class="v">${esc(session.reject_total || 0)}</div></div>
          <div class="archive-hero-stat"><div class="k">Total Good</div><div class="v">${esc(totalGood)}</div></div>
        </div>
      </div>
    ` : "";
    const rawMaterialsHtml = materialRows.length
      ? tableFromRows(materialRows, [
          { label: "#", value: x => x.index },
          { label: "Material / Scan", value: x => x.material },
          { label: "Qty", value: x => x.qty },
          { label: "Lot", value: x => x.lot },
          { label: "Scanned At", value: x => fmtDateLocal(x.time || "") },
        ], "No raw materials scanned.", 12)
      : `<div class="machine-detail-empty">No raw materials scanned.</div>`;
    const rejectHtml = rejectRows.length
      ? `<ol class="machine-detail-list">${rejectRows.map(([k,v]) => `<li>${esc(k)} = ${esc(v)}</li>`).join("")}</ol>`
      : `<div class="machine-detail-empty">No reject details recorded.</div>`;

    machineDetailTitle.textContent = `${session.machine_name || session.machine_code || "Machine"} Details`;
    if(machineDetailStatusSelect) machineDetailStatusSelect.value = manualStatus;
    if(machineDetailStatusReason) machineDetailStatusReason.value = manualReason;
    if(machineDetailStatusSetterBadge) machineDetailStatusSetterBadge.value = "";
    if(machineDetailStatusPanel) machineDetailStatusPanel.style.display = "none";
    machineDetailBody.innerHTML = `
      ${activeJobSummaryHtml}
      <div class="machine-detail-section">
        <h4>Overview</h4>
        <div class="machine-detail-grid">
          ${detailItem("Machine", session.machine_code || "-")}
          ${detailItem("Machine Name", session.machine_name || "-")}
          ${detailItem("Status", status)}
          ${detailItem("Status Reason", manualReason || "-")}
          ${detailItem("Status Set By", (manual && manual.set_by_name) ? `${manual.set_by_name}${manual.set_by_role ? ` (${manual.set_by_role})` : ""}` : "-")}
          ${detailItem("Status Set At", fmtDateLocal((manual && (manual.started_at_utc || manual.updated_at_utc)) || ""))}
          ${detailItem("Client", displayNameForId(session.client_id || "-"))}
          ${detailItem("Job Code", session.job_code || "-")}
          ${detailItem("Job Name", session.job_name || "-")}
          ${detailItem("Operator", displayNameForId(session.operator_id || "-"))}
          ${detailItem("Last Seen", fmtDateLocal(session.last_seen_utc))}
          ${detailItem("Last Event", session.last_event || "-")}
        </div>
      </div>
      <div class="machine-detail-section">
        <h4>Production Counters</h4>
        <div class="archive-metric-grid">
          ${archiveMetric("Pack", Number(session.pack_total || 0))}
          ${archiveMetric("Good", Number(session.good_total || 0), "good")}
          ${archiveMetric("Butal", Number(session.butal_total || 0), Number(session.butal_total || 0) > 0 ? "warn" : "")}
          ${archiveMetric("Reject", Number(session.reject_total || 0), Number(session.reject_total || 0) > 0 ? "bad" : "")}
          ${archiveMetric("No Shot", Number(session.no_shot_total || 0))}
          ${archiveMetric("Total Good", totalGood, "good")}
          ${archiveMetric("Startup Reject", Number(session.startup_reject_total || 0))}
          ${archiveMetric("Raw Sacks", Number(session.raw_sacks_count || 0))}
          ${archiveMetric("Scanned Raw Qty", scannedRawQty || "-")}
          ${archiveMetric("Cycle Time", session.cycle_time_current || "-")}
          ${archiveMetric("Maintenance", maintenanceMode ? "YES" : "NO")}
          ${archiveMetric("Downtime Active", session.downtime_active ? "YES" : "NO")}
        </div>
        ${productionVisualHtml(session)}
      </div>
      <div class="machine-detail-section">
        <h4>Downtime</h4>
        <div class="machine-detail-grid">
          ${detailItem("Reason Code", session.downtime_reason_code || "-")}
          ${detailItem("Reason", session.downtime_reason_text || "-")}
          ${detailItem("Current/Last Duration", fmtDowntimeSeconds(session.downtime_active ? (Date.now()/1000 - Number(session.downtime_started_at || 0)) : session.downtime_last_seconds))}
          ${detailItem("Downtime Start", session.downtime_started_at ? new Date(Number(session.downtime_started_at) * 1000).toLocaleString() : "-")}
        </div>
      </div>
      <div class="machine-detail-section">
        <h4>Reject Details</h4>
        ${rejectHtml}
      </div>
      <div class="machine-detail-section">
        <h4>Raw Materials</h4>
        ${rawMaterialInsightsHtml(session)}
        ${rawScans.length ? `
          <details class="archive-raw-details">
            <summary>Show scanned raw text</summary>
            <div class="machine-detail-code" style="margin-top:8px;">${esc(rawScans.map(x => typeof x === "string" ? x : compactValue(x)).join("\\n"))}</div>
          </details>
        ` : ""}
      </div>
      <div class="machine-detail-section">
        <h4>Job Details</h4>
        <div class="machine-detail-grid">
          ${detailItem("Job Ref", job.ref_no || job.reference || job.id || "-")}
          ${detailItem("Product ID", job.product_id || "-")}
          ${detailItem("Mold", job.custom_05 || "-")}
          ${detailItem("Color", job.custom_06 || "-")}
          ${detailItem("System Code", job.custom_09 || "-")}
          ${detailItem("Target / Cavity Info", job.custom_11 || "-")}
          ${detailItem("Status", job.status || "-")}
          ${detailItem("Remarks", job.remarks || "-")}
        </div>
        <details class="archive-raw-details">
          <summary>Show raw Job API payload</summary>
          <div class="machine-detail-code" style="margin-top:8px;">${escJson(session.job_payload || {})}</div>
        </details>
      </div>
    `;
    machineDetailOverlay.classList.add("active");
  }

  function closeMachineDetail(){
    machineDetailOverlay.classList.remove("active");
    activeMachineDetailCode = "";
    if(machineDetailStatusPanel) machineDetailStatusPanel.style.display = "none";
    if(machineStatusSaveFeedback) machineStatusSaveFeedback.classList.remove("active");
    if(machineStatusSaveBar) machineStatusSaveBar.style.width = "0%";
    if(machineStatusSaveCheck) machineStatusSaveCheck.classList.remove("done");
    if(machineDetailSettingsBtn) machineDetailSettingsBtn.style.display = "";
  }

  function applyDashboardTheme(themeName){
    const t = String(themeName || "Default").trim() || "Default";
    if(t === "Default" || t === "Blue Accent"){
      delete document.body.dataset.theme;
    } else {
      document.body.dataset.theme = t;
    }
  }

  function showServerSettingsPage(key){
    const map = {
      general: [settingsNavGeneral, settingsPageGeneral],
      theme: [settingsNavTheme, settingsPageTheme],
      api: [settingsNavApi, settingsPageApi],
      profile: [settingsNavProfile, settingsPageProfile],
    };
    Object.entries(map).forEach(([k, pair]) => {
      const [btn, page] = pair;
      btn?.classList.toggle("active", k === key);
      page?.classList.toggle("active", k === key);
    });
  }

  function normalizeCompanyRoleLabel(role){
    const low = String(role || "").trim().toLowerCase();
    if(["qa", "qc", "qa/qc"].includes(low)) return "QA/QC";
    if(low === "production manager") return "Production Manager";
    if(low === "supervisor") return "Supervisor";
    if(low === "operator") return "Operator";
    if(low === "maintenance") return "Maintenance";
    if(low === "planner") return "Planner";
    return String(role || "").trim();
  }

  function basePrivilegeFromRole(role){
    const low = String(role || "").trim().toLowerCase();
    if(low === "supervisor") return "supervisor";
    if(["qa", "qc", "qa/qc"].includes(low)) return "qc";
    if(low === "maintenance") return "maintenance";
    return "viewer";
  }

  function combinePrivileges(base, extra){
    const set = new Set([String(base || "viewer").trim().toLowerCase() || "viewer"]);
    const ex = String(extra || "").trim().toLowerCase();
    if(ex && ex !== "none") set.add(ex);
    if(set.has("supervisor") && set.has("qc")) return "both";
    if(set.has("supervisor")) return "supervisor";
    if(set.has("qc")) return "qc";
    if(set.has("maintenance")) return "maintenance";
    return "viewer";
  }

  function privilegeLabel(v){
    const x = String(v || "").trim().toLowerCase();
    if(x === "both") return "Supervisor + QC";
    if(x === "supervisor") return "Supervisor";
    if(x === "qc") return "QC";
    if(x === "maintenance") return "Maintenance";
    return "Viewer";
  }

  function findSettingsProfileById(id){
    const code = String(id || "").trim();
    return settingsProfilesState.find(p => String(p?.id_number || "").trim() === code) || null;
  }

  function refreshDailyRoleDerivedUi(){
    const badge = (dailyRoleBadgeInput?.value || "").trim();
    const p = findSettingsProfileById(badge);
    const profileName = p ? String(p.name || "").trim() : "";
    const roleLabel = p ? normalizeCompanyRoleLabel(p.role || "") : "";
    if(dailyRoleNameInput && !dailyRoleNameInput.value.trim()){
      dailyRoleNameInput.value = profileName || knownPersonNameFromBadge(badge) || "";
    }
    if(dailyRoleCompanyRoleInput) dailyRoleCompanyRoleInput.value = roleLabel;
    if(dailyRoleEffectiveRightsInput){
      dailyRoleEffectiveRightsInput.value = privilegeLabel(combinePrivileges(basePrivilegeFromRole(roleLabel), dailyRoleExtraPrivilegeSelect?.value || "none"));
    }
  }

  async function loadSettingsProfilesUi(){
    try {
      const resp = await fetch("/api/profiles");
      const out = await resp.json();
      const rows = Array.isArray(out.items) ? out.items : [];
      settingsProfilesState = rows;
      if(settingsProfilesTableBody){
        settingsProfilesTableBody.innerHTML = rows.length ? rows.slice().reverse().map(r => `
          <tr>
            <td>${esc(r.name || "-")}</td>
            <td>${esc(r.id_number || "-")}</td>
            <td>${esc(normalizeCompanyRoleLabel(r.role || "-"))}</td>
            <td>${esc(fmtDateLocal(r.created_at_utc || ""))}</td>
          </tr>
        `).join("") : `<tr><td colspan="4">No profiles yet.</td></tr>`;
      }
    } catch {
      if(settingsProfilesTableBody) settingsProfilesTableBody.innerHTML = `<tr><td colspan="4">Failed to load profiles.</td></tr>`;
    }
    refreshDailyRoleDerivedUi();
  }

  async function loadServerSettingsUi(applyTheme = true){
    settingsServerHost && (settingsServerHost.value = location.origin);
    try {
      const resp = await fetch("/api/server-settings");
      const out = await resp.json();
      if(!out.ok) return;
      const s = (out.settings && typeof out.settings === "object") ? out.settings : {};
      serverSettingsState = {
        theme: s.theme || "Default",
        qrgen_base_url: s.qrgen_base_url || "",
      };
      if(applyTheme) applyDashboardTheme(serverSettingsState.theme);
      if(settingsThemeSelect) settingsThemeSelect.value = serverSettingsState.theme;
      if(settingsQrApiBaseUrl) settingsQrApiBaseUrl.value = serverSettingsState.qrgen_base_url;
    } catch {}
    await loadProductsSettingsInfo(false);
  }

  async function loadProductsSettingsInfo(forceRefresh = false){
    if(settingsProductsStatus) settingsProductsStatus.value = forceRefresh ? "Refreshing product items..." : "Loading product cache info...";
    try {
      const url = forceRefresh ? "/api/products?refresh=1" : "/api/products";
      const resp = await fetch(url);
      const out = await resp.json();
      if(!out.ok){
        if(settingsProductsStatus) settingsProductsStatus.value = out.error || "Failed to load products.";
        return;
      }
      const items = Array.isArray(out.items) ? out.items : [];
      if(settingsProductsCount) settingsProductsCount.value = `${items.length} item(s)${out.from_cache ? " (from cache)" : " (fresh)"}`;
      if(settingsProductsUpdated) settingsProductsUpdated.value = out.updated ? fmtDateLocal(out.updated) : "-";
      if(settingsProductsSourceFile) settingsProductsSourceFile.value = out.source_file || "-";
      if(settingsProductsCacheFile) settingsProductsCacheFile.value = out.cache_file || "-";
      if(settingsProductsStatus){
        const base = out.error ? `Loaded with warning: ${out.error}` : "OK";
        settingsProductsStatus.value = base;
      }
      if(forceRefresh){
        productItems = items;
        productsHydrated = items.length > 0;
      }
    } catch (e) {
      if(settingsProductsStatus) settingsProductsStatus.value = `Failed: ${e}`;
    }
  }

  async function saveServerSettingsUi(){
    const payload = {
      theme: (settingsThemeSelect?.value || "Default").trim(),
      qrgen_base_url: (settingsQrApiBaseUrl?.value || "").trim(),
    };
    if(!payload.qrgen_base_url){
      alert("QR Print API Base URL is required.");
      showServerSettingsPage("api");
      return;
    }
    const resp = await fetch("/api/server-settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const out = await resp.json();
    if(!out.ok){
      alert(out.error || "Failed to save settings.");
      return;
    }
    serverSettingsState = out.settings || payload;
    applyDashboardTheme(serverSettingsState.theme);
    alert("Server settings applied.");
  }

  function knownPersonNameFromBadge(code){
    const c = String(code || "").trim();
    const map = {
      "3000001": "Charlie Brown",
      "4000001": "Lucy Van Pelt",
    };
    return map[c] || "";
  }

  function displayNameForId(idValue){
    const raw = String(idValue || "").trim();
    if(!raw) return "-";
    const combinedMatch = raw.match(/^\\s*[\\w-]+\\s*-\\s*(.+)\\s*$/);
    if(combinedMatch && String(combinedMatch[1] || "").trim()){
      return String(combinedMatch[1] || "").trim();
    }
    const code = raw;
    if(!code) return "-";
    const profile = findSettingsProfileById(code);
    if(profile && String(profile.name || "").trim()) return String(profile.name || "").trim();
    const daily = (dailyRolesState && typeof dailyRolesState === "object") ? dailyRolesState[code] : null;
    if(daily && String(daily.name || "").trim()) return String(daily.name || "").trim();
    return knownPersonNameFromBadge(code) || code;
  }

  function fmtLocal(ts){
    if(!ts) return "-";
    const dt = new Date(ts);
    if(Number.isNaN(dt.getTime())) return "-";
    return dt.toLocaleString();
  }

  function compactPair(primary, secondary){
    const p = String(primary || "").trim();
    const s = String(secondary || "").trim();
    if(!p && !s) return { primary: "-", secondary: "" };
    if(!p && s) return { primary: s, secondary: "" };
    if(p && !s) return { primary: p, secondary: "" };
    if(p === s) return { primary: p, secondary: "" };
    return { primary: p, secondary: s };
  }

  function openOperatorDetail(index){
    const row = Array.isArray(operatorDirectoryState) ? operatorDirectoryState[index] : null;
    if(!row || !operatorDetailBody) return;
    const fullName = row.name || "-";
    const badge = row.is_active ? "ACTIVE" : "IDLE";
    const activity = Array.isArray(row.all_activity) ? row.all_activity : [];
    operatorDetailTitle.textContent = fullName;
    operatorDetailSub.textContent = `ID ${row.id_number || '-'} | ${row.role || 'Operator'} | ${badge}`;
    const currentPair = compactPair(row.current_machine_name || row.current_machine_code, row.current_job_name || row.current_job_code);
    const lastPair = compactPair(row.last_machine_name || row.last_machine_code, row.last_job_name || row.last_job_code);
    const activityHtml = activity.length
      ? activity.map(item => `<div class="operator-detail-list-item"><strong>${esc(item.label || 'Activity')}</strong><span>${esc(item.detail || '-')}</span><span>${esc(fmtLocal(item.at_utc))}</span></div>`).join('')
      : '<div class="operator-directory-empty" style="padding:0;">No machine activity recorded yet.</div>';
    operatorDetailBody.innerHTML = `
      <div class="operator-detail-grid">
        <div class="operator-detail-item"><div class="k">Current Machine</div><div class="v">${esc(currentPair.primary)}${currentPair.secondary ? `<br>${esc(currentPair.secondary)}` : ''}</div></div>
        <div class="operator-detail-item"><div class="k">Last Handled</div><div class="v">${esc(lastPair.primary)}${lastPair.secondary ? `<br>${esc(lastPair.secondary)}` : ''}</div></div>
        <div class="operator-detail-item"><div class="k">Last Activity</div><div class="v">${esc(fmtLocal(row.last_activity_at_utc))}</div></div>
      </div>
      <div class="operator-detail-section">
        <h4>Recent Activity</h4>
        <div class="operator-detail-list">${activityHtml}</div>
      </div>
    `;
    operatorDetailOverlay?.classList.add("active");
  }

  function renderOperatorDirectory(items){
    const rows = Array.isArray(items) ? items : [];
    if(!operatorDirectoryGrid) return;
    operatorDirectoryState = rows.slice();
    if(!rows.length){
      operatorDirectoryGrid.innerHTML = '<div class="operator-directory-empty">No operator profiles found yet.</div>';
      return;
    }
    const header = `<div class="operator-directory-row header">
      <div>Operator</div>
      <div>Current Machine</div>
      <div>Last Handled</div>
      <div>Last Activity</div>
      <div>Status</div>
    </div>`;
    const body = rows.map((x, index) => {
      const badge = x.is_active ? '<span class="operator-directory-badge live">ACTIVE</span>' : '<span class="operator-directory-badge">IDLE</span>';
      const currentPair = compactPair(x.current_machine_name || x.current_machine_code, x.current_job_name || x.current_job_code);
      const lastPair = compactPair(x.last_machine_name || x.last_machine_code, x.last_job_name || x.last_job_code);
      const activity = Array.isArray(x.recent_activity) ? x.recent_activity : [];
      const recentPreview = activity.length
        ? activity.map(item => `${item.label || 'Activity'}: ${item.detail || '-'}`).slice(0, 2).join(' | ')
        : 'No machine activity recorded yet.';
      return `<div class="operator-directory-row" data-operator-index="${index}">
        <div class="operator-directory-name">
          <strong>${esc(x.name || '-')}</strong>
          <div class="operator-directory-meta">ID ${esc(x.id_number || '-')} | ${esc(x.role || 'Operator')}</div>
        </div>
        <div class="operator-directory-cell">
          <div class="operator-directory-label">Current Machine</div>
          <div class="operator-directory-value">${esc(currentPair.primary)}</div>
          ${currentPair.secondary ? `<div class="operator-directory-subvalue">${esc(currentPair.secondary)}</div>` : ``}
        </div>
        <div class="operator-directory-cell">
          <div class="operator-directory-label">Last Handled</div>
          <div class="operator-directory-value">${esc(lastPair.primary)}</div>
          ${lastPair.secondary ? `<div class="operator-directory-subvalue">${esc(lastPair.secondary)}</div>` : ``}
        </div>
        <div class="operator-directory-cell">
          <div class="operator-directory-label">Last Activity</div>
          <div class="operator-directory-value">${esc(fmtLocal(x.last_activity_at_utc))}</div>
          <div class="operator-directory-subvalue">${esc(recentPreview)}</div>
        </div>
        <div class="operator-directory-cell">
          <div class="operator-directory-label">Status</div>
          ${badge}
        </div>
      </div>`;
    }).join('');
    operatorDirectoryGrid.innerHTML = header + body;
  }

  async function loadOperatorDirectory(){
    if(!operatorDirectoryGrid) return;
    operatorDirectoryGrid.innerHTML = '<div class="operator-directory-empty">Loading operator activity...</div>';
    const r = await fetch('/api/profiles/operators');
    const out = await r.json().catch(() => ({}));
    if(!r.ok || !out.ok){
      operatorDirectoryGrid.innerHTML = `<div class="operator-directory-empty">${esc(out.error || 'Failed to load operator activity.')}</div>`;
      return;
    }
    renderOperatorDirectory(out.items || []);
  }

  function renderDailyRolesList(items){
    const rows = (items && typeof items === "object") ? Object.entries(items) : [];
    if(!dailyRolesList) return;
    if(!rows.length){
      dailyRolesList.innerHTML = '<div class="placeholder" style="margin:0;">No roles assigned for today yet.</div>';
      return;
    }
    dailyRolesList.innerHTML = `
      <div class="people-role-row head"><div>Name</div><div>Badge</div><div>Base Role</div><div>Privilege</div><div>Updated</div></div>
      ${rows.map(([badge, item]) => `
        <div class="people-role-row">
          <div>${esc(item?.name || "-")}</div>
          <div>${esc(badge)}</div>
          <div>${esc(item?.company_role || "-")}</div>
          <div><span class="people-role-pill">${esc(privilegeLabel(item?.rights || ""))}</span></div>
          <div>${esc(fmtDateLocal(item?.updated_at_utc || ""))}</div>
        </div>
      `).join("")}
    `;
  }

  async function loadDailyRolesUi(){
    try {
      const resp = await fetch("/api/daily-roles");
      const out = await resp.json();
      if(!out.ok) return;
      dailyRolesState = (out.items && typeof out.items === "object") ? out.items : {};
      renderDailyRolesList(dailyRolesState);
    } catch {}
  }

  async function saveDailyRoleUi(){
    const badge = (dailyRoleBadgeInput?.value || "").trim();
    const profile = findSettingsProfileById(badge);
    const company_role = normalizeCompanyRoleLabel(profile?.role || "");
    const extra_privilege = (dailyRoleExtraPrivilegeSelect?.value || "none").trim().toLowerCase();
    const name = (dailyRoleNameInput?.value || "").trim() || String(profile?.name || "").trim() || knownPersonNameFromBadge(badge) || badge;
    if(!badge){
      alert("Scan QR badge first.");
      return;
    }
    if(!company_role){
      alert("Profile not found for this ID. Create the profile first so role-based privileges can be assigned.");
      return;
    }
    const resp = await fetch("/api/daily-roles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ badge_code: badge, name, company_role, extra_privilege }),
    });
    const out = await resp.json();
    if(!out.ok){
      alert(out.error || "Failed to save daily role.");
      return;
    }
    dailyRolesState = out.items || {};
    renderDailyRolesList(dailyRolesState);
    alert("Today role saved.");
  }

  function openQrScanCaptureOverlay(){
    if(!qrScanCaptureOverlay || !qrScanCaptureInput) return;
    qrScanCaptureOverlay.classList.add("active");
    qrScanCaptureInput.value = "";
    setTimeout(() => qrScanCaptureInput.focus(), 0);
  }

  function closeQrScanCaptureOverlay(){
    if(!qrScanCaptureOverlay || !qrScanCaptureInput) return;
    qrScanCaptureOverlay.classList.remove("active");
    qrScanCaptureInput.value = "";
  }

  function scoreProduct(item, q){
    const sku = (item.sku || "").toString().toLowerCase();
    const name = (item.name || "").toString().toLowerCase();
    const text = `${name} ${sku}`;
    const idx = text.indexOf(q);
    if(idx < 0) return 999999;
    return idx * 1000 + text.length;
  }

  function resolveProductIdFromText(text){
    const found = resolveProductFromText(text);
    return found ? String(found.id || "") : "";
  }

  function resolveProductFromText(text){
    const t = (text || "").trim();
    if(!t) return null;
    const exact = productItems.find(
      p =>
        `${p.sku || ""} - ${p.name}` === t
        || `${p.name}` === t
        || `${p.sku || ""}` === t
    );
    if(exact) return exact;
    const low = t.toLowerCase();
    const candidates = productItems
      .filter(p => `${(p.name||"").toString().toLowerCase()} ${(p.sku||"").toString().toLowerCase()}`.includes(low))
      .sort((a,b) => scoreProduct(a, low) - scoreProduct(b, low));
    if(candidates.length) return candidates[0];
    return null;
  }

  function renderProductSuggestions(query = ""){
    const q = (query || "").trim().toLowerCase();
    productSuggestionItems = [...productItems]
      .map(p => ({ ...p, label: `${p.sku || ""} - ${p.name}`.trim() }))
      .filter(p => !q || p.label.toLowerCase().includes(q) || String(p.name || "").toLowerCase().includes(q))
      .sort((a, b) => scoreProduct(a, q) - scoreProduct(b, q))
      .slice(0, PRODUCT_SUGGEST_LIMIT);
    productSuggestionIndex = -1;
    if(!productSuggestionItems.length){
      overlayProductSuggest.classList.remove("active");
      overlayProductSuggest.innerHTML = "";
      return;
    }
    overlayProductSuggest.innerHTML = productSuggestionItems
      .map((p, i) => `<button type="button" class="overlay-suggest-item" data-idx="${i}">${esc(p.label)}</button>`)
      .join("");
    overlayProductSuggest.classList.add("active");
  }

  function pickProductSuggestion(index){
    const item = productSuggestionItems[index];
    if(!item) return;
    overlayProductSelect.value = item.label;
    overlayProductSuggest.classList.remove("active");
    overlayProductSuggest.innerHTML = "";
    productSuggestionItems = [];
    productSuggestionIndex = -1;
  }

  function jobKeyOf(row){
    if(!row || typeof row !== "object") return "";
    return [
      row.finished_at_utc || "",
      row.machine_code || "",
      row.job_code || "",
      row.operator_id || "",
      row.pack_count ?? "",
      row.good_total ?? "",
      row.butal_total ?? "",
      row.reject_total ?? "",
    ].join("|");
  }

  function setOverlayStep(step){
    const isReview = step !== "qr";
    const approvedShiftView = isReview && overlayReviewMode === "shift" && isApprovedShiftRecord(activeJobRow);
    overlayReviewStep.style.display = isReview ? "" : "none";
    overlayQrStep.style.display = isReview ? "none" : "";
    overlayReviewSubmitBtn.style.display = (isReview && !approvedShiftView) ? "" : "none";
    overlayReviewContinueBtn.style.display = (isReview && overlayReviewMode !== "shift") ? "" : "none";
    overlayBackToReviewBtn.style.display = isReview ? "none" : "";
    overlayGenerateBtn.style.display = "none";
    overlayRequestBtn.style.display = isReview ? "none" : "";
    syncReviewSubslides();
  }

  function syncReviewSubslides(){
    const slides = [reviewSubslide1, reviewSubslide2, reviewSubslide3, reviewSubslide4, reviewSubslide5, reviewSubslide6];
    const visibleSlides = slides.filter((el, idx) => el && !(overlayReviewMode !== "shift" && idx === 1));
    const total = slides.length;
    const visibleTotal = visibleSlides.length;
    reviewSlideIndex = Math.max(0, Math.min(visibleTotal - 1, Number(reviewSlideIndex || 0)));
    slides.forEach(el => {
      if(el) el.classList.remove("active");
    });
    const active = visibleSlides[reviewSlideIndex];
    if(active) active.classList.add("active");
    if(overlayReviewPrevBtn) overlayReviewPrevBtn.disabled = reviewSlideIndex <= 0;
    if(overlayReviewNextBtn) overlayReviewNextBtn.disabled = reviewSlideIndex >= (visibleTotal - 1);
    if(overlayReviewSlideStatus){
      const labels = overlayReviewMode === "shift"
        ? ["Shift Summary", "Reject Details", "Raw Materials", "Job / Cycle", "Downtime / Team", "Review / Edit"]
        : ["Job Summary", "Raw Mats / Cycle", "Downtime / Team", "Approval"];
      overlayReviewSlideStatus.textContent = `Slide ${reviewSlideIndex + 1} / ${visibleTotal} - ${labels[reviewSlideIndex] || ""}`;
    }
  }

  function reviewSummaryText(row){
    if(!row) return "";
    return [
      `Finished Job: ${row.job_name || row.job_code || "-"}`,
      `Pack: ${row.pack_count ?? 0}`,
      `Good: ${row.good_total ?? 0}`,
      `Butal: ${row.butal_total ?? 0}`,
      `Reject: ${row.reject_total ?? 0}`,
      `No Shot: ${row.no_shot_total ?? 0}`,
      `Total Good: ${row.total_good ?? ((Number(row.good_total||0)+Number(row.butal_total||0)))}`,
    ].join("\\n");
  }

  function reviewRejectsText(row){
    const rb = (row && typeof row.reject_breakdown === "object" && row.reject_breakdown) || {};
    const keys = Object.keys(rb);
    if(!keys.length) return "No reject details recorded.";
    return keys.sort().map(k => `${k}: ${rb[k]}`).join("\\n");
  }

  function fillDisapproveFields(row){
    editPackCount.value = String(row?.pack_count ?? 0);
    editGoodTotal.value = String(row?.good_total ?? 0);
    editButalTotal.value = String(row?.butal_total ?? 0);
    editRejectTotal.value = String(row?.reject_total ?? 0);
    if(typeof editNoShotTotal !== "undefined" && editNoShotTotal) editNoShotTotal.value = String(row?.no_shot_total ?? 0);
    editTotalGood.value = String(row?.total_good ?? (Number(row?.good_total||0)+Number(row?.butal_total||0)));
    editRejectBreakdown.value = JSON.stringify((row && row.reject_breakdown) || {}, null, 2);
  }

  function qcFromFinishedJob(row){
    const logs = Array.isArray(row?.reject_review_logs) ? row.reject_review_logs : [];
    const qc = logs.find(x => String((x && x.actor_role) || "").toLowerCase() === "qc");
    return (qc && (qc.actor_name || qc.actor_code)) || "-";
  }

  function renderBulletListHtml(text, emptyLabel = "No data."){
    const lines = String(text || "").split(/\\r?\\n/).map(x => x.trim()).filter(Boolean);
    if(!lines.length) return `<div class="machine-detail-empty">${esc(emptyLabel)}</div>`;
    return `<ul class="review-line-list">${lines.map(x => `<li>${esc(x)}</li>`).join("")}</ul>`;
  }

  function safeJsonPretty(value){
    try {
      return JSON.stringify(value ?? {}, null, 2);
    } catch {
      return String(value ?? "");
    }
  }

  function renderPreformattedHtml(text, emptyLabel = "No data."){
    const raw = String(text || "").trim();
    if(!raw) return `<div class="machine-detail-empty">${esc(emptyLabel)}</div>`;
    return `<pre class="review-pre">${esc(raw)}</pre>`;
  }

  function renderKeyValueTableHtml(obj, emptyLabel = "No data."){
    const entries = Object.entries((obj && typeof obj === "object") ? obj : {}).filter(([_, v]) => v !== undefined);
    if(!entries.length) return `<div class="machine-detail-empty">${esc(emptyLabel)}</div>`;
    return `
      <table class="review-kv-table">
        <tbody>
          ${entries.map(([key, value]) => `
            <tr>
              <td class="review-kv-key">${esc(String(key).replace(/_/g, " "))}</td>
              <td class="review-kv-value">${esc(typeof value === "string" ? value : String(value))}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  }

  function compactValue(value){
    if(value === null || value === undefined || value === "") return "-";
    if(typeof value === "boolean") return value ? "Yes" : "No";
    if(Array.isArray(value)) return `${value.length} item${value.length === 1 ? "" : "s"}`;
    if(typeof value === "object") return Object.keys(value).length ? "Available" : "-";
    return String(value);
  }

  function tableFromRows(rows, columns, emptyLabel = "No data.", maxRows = 8){
    const items = Array.isArray(rows) ? rows : [];
    const cols = Array.isArray(columns) ? columns : [];
    if(!items.length || !cols.length) return `<div class="machine-detail-empty">${esc(emptyLabel)}</div>`;
    const limit = Math.max(1, Number(maxRows || 8));
    const visible = items.slice(0, limit);
    const hidden = Math.max(0, items.length - visible.length);
    return `
      <table class="review-kv-table review-data-table">
        <thead>
          <tr>${cols.map(col => `<th>${esc(col.label)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${visible.map(item => `
            <tr>
              ${cols.map(col => `<td>${esc(compactValue(col.value(item)))}</td>`).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
      ${hidden ? `<div class="review-more-note">Showing ${visible.length} of ${items.length} records.</div>` : ""}
    `;
  }

  function primaryRawPart(row){
    const payload = (row?.job_payload && typeof row.job_payload === "object") ? row.job_payload : {};
    const data = (payload.data && typeof payload.data === "object") ? payload.data : {};
    const details = (data.job_details && typeof data.job_details === "object") ? data.job_details : {};
    const candidates = [
      Array.isArray(data.parts) ? data.parts : null,
      Array.isArray(details.parts) ? details.parts : null,
      Array.isArray(details.part_ids) ? details.part_ids : null,
      details.part_ids && typeof details.part_ids === "object" ? [details.part_ids] : null,
      Array.isArray(data.part_ids) ? data.part_ids : null,
    ].filter(Boolean);
    for(const rows of candidates){
      const first = rows.find(x => x && typeof x === "object");
      if(first) return first;
    }
    return {};
  }

  function transferPreviewRows(row){
    const item = (row && typeof row === "object") ? row : {};
    const rawLogs = Array.isArray(item.raw_material_logs) ? item.raw_material_logs : [];
    const packLogs = Array.isArray(item.product_pack_history_logs) ? item.product_pack_history_logs : [];
    const part = primaryRawPart(item);
    const partQtyPerUnit = Number(part.part_qty_per_unit || 0);
    const totalGood = Number(item.total_good ?? ((Number(item.good_total || 0) + Number(item.butal_total || 0))));
    const scannedRawQty = rawLogs.reduce((sum, x) => sum + Math.max(0, Number(x?.qty || x?.quantity || 0)), 0);
    const usedRawQty = partQtyPerUnit > 0 ? Math.min(scannedRawQty, totalGood * partQtyPerUnit) : 0;
    const rawExcessQty = Math.max(0, Math.floor(scannedRawQty - usedRawQty));
    const butalQty = Math.max(0, Number(item.butal_total || 0));
    const latestRaw = rawLogs.length ? rawLogs[rawLogs.length - 1] : {};
    const latestPack = packLogs.length ? packLogs[packLogs.length - 1] : {};
    const rows = [];
    if(rawExcessQty > 0){
      rows.push({
        stage: "Raw Material Excess",
        qty: rawExcessQty,
        product: latestRaw.material_name || latestRaw.material || part.name || part.material_name || part.sku || "Select product",
        po: "Not required",
        required: "Product and generated lot",
      });
    }
    if(butalQty > 0){
      rows.push({
        stage: "Butal Return",
        qty: butalQty,
        product: latestPack.product_name || latestPack.product_p || latestPack.product_id || item.job_name || "Finished product",
        po: "Required",
        required: "PO number before print request",
      });
    }
    if(!rows.length){
      rows.push({
        stage: "Default Raw Material QR",
        qty: 1,
        product: "Selected product",
        po: "Not required",
        required: "Only used when no raw excess or Butal exists",
      });
    }
    return rows;
  }

  function renderTransferPreviewHtml(row){
    return tableFromRows(transferPreviewRows(row), [
      { label: "Stage", value: x => x.stage },
      { label: "Qty", value: x => x.qty },
      { label: "Product", value: x => x.product },
      { label: "PO", value: x => x.po },
      { label: "Needed Before Transfer", value: x => x.required },
    ], "No transfer data.", 6);
  }

  function renderShiftGroupedPanelHtml(panel, emptyLabel = "No data."){
    const groups = Array.isArray(panel) ? panel : [];
    if(!groups.length) return `<div class="machine-detail-empty">${esc(emptyLabel)}</div>`;
    return `
      <div class="review-group-list">
        ${groups.map(group => {
          const rawTitle = group && Object.prototype.hasOwnProperty.call(group, "title") ? group.title : "Section";
          const title = String(rawTitle || "").trim();
          const kind = String(group?.kind || "json").trim();
          const content = group?.content;
          let bodyHtml = "";
          if(kind === "table"){
            bodyHtml = renderKeyValueTableHtml(content, emptyLabel);
          } else if(kind === "metrics"){
            const metrics = Array.isArray(content) ? content : [];
            bodyHtml = metrics.length
              ? `<div class="archive-metric-grid">${metrics.map(x => archiveMetric(x?.label || "-", x?.value ?? "-", x?.tone || "")).join("")}</div>`
              : `<div class="machine-detail-empty">${esc(emptyLabel)}</div>`;
          } else if(kind === "html") {
            bodyHtml = String(content || "");
          } else {
            bodyHtml = `<div class="machine-detail-empty">Details are summarized in the other cards.</div>`;
          }
          return `
            <div class="review-group-card ${group?.wide ? "wide" : ""}">
              ${title ? `<div class="review-group-head">${esc(title)}</div>` : ""}
              <div class="review-group-body">${bodyHtml}</div>
            </div>
          `;
        }).join("")}
      </div>
    `;
  }

  function buildShiftPreviewPanels(row){
    const item = (row && typeof row === "object") ? row : {};
    const payload = (item.job_payload && typeof item.job_payload === "object") ? item.job_payload : {};
    const data = (payload.data && typeof payload.data === "object") ? payload.data : {};
    const job = (data.job && typeof data.job === "object") ? data.job : {};
    const jobDetails = (data.job_details && typeof data.job_details === "object") ? data.job_details : {};
    const partials = Array.isArray(data.partials) ? data.partials : [];
    const productParts = Array.isArray(data.product_parts) ? data.product_parts : [];
    let targetRawMaterials = [];
    if(Array.isArray(data.parts)) targetRawMaterials = data.parts.filter(x => x && typeof x === "object");
    else if(Array.isArray(jobDetails.parts)) targetRawMaterials = jobDetails.parts.filter(x => x && typeof x === "object");
    else if(Array.isArray(jobDetails.part_ids)) targetRawMaterials = jobDetails.part_ids.filter(x => x && typeof x === "object");
    else if(jobDetails.part_ids && typeof jobDetails.part_ids === "object") targetRawMaterials = [jobDetails.part_ids];
    else if(Array.isArray(data.part_ids)) targetRawMaterials = data.part_ids.filter(x => x && typeof x === "object");
    else if(Array.isArray(payload.part_ids)) targetRawMaterials = payload.part_ids.filter(x => x && typeof x === "object");
    const rawLogs = Array.isArray(item.raw_material_logs) ? item.raw_material_logs : [];
    const rawScans = Array.isArray(item.raw_material_scans) ? item.raw_material_scans : [];
    const materialRows = archivedMaterialRows(item);
    const packHistory = Array.isArray(item.product_pack_history_logs) ? item.product_pack_history_logs : [];
    const rejectReviews = Array.isArray(item.reject_review_logs) ? item.reject_review_logs : [];
    const rejectBreakdownRows = Object.entries((item.reject_breakdown && typeof item.reject_breakdown === "object") ? item.reject_breakdown : {})
      .map(([reason, qty]) => ({reason, qty}));
    const totalGood = Number(item.total_good ?? item.partial_qty ?? ((Number(item.good_total || 0) + Number(item.butal_total || 0))));
    const scannedRawQty = materialRows.reduce((sum, x) => sum + Math.max(0, Number(x.qty || 0)), 0);
    const shiftHero = `
      <div class="archive-detail-hero">
        <div>
          <h3>${esc(item.job_name || item.job_code || "Shift Review")}</h3>
          <div class="sub">${esc(item.machine_name || item.machine_code || "-")} | Shift ${esc(item.shift_index ?? "-")} | ${esc(item.reason || "Shift handoff")}</div>
          <div class="archive-pill-row">
            <span class="archive-pill">${esc(item.review_status || "Pending Review")}</span>
            <span class="archive-pill">Operator ${esc(displayNameForId(item.operator_id || item.operator_name || "-"))}</span>
            <span class="archive-pill">Ended ${esc(fmtDateLocal(item.ended_at_utc || item.finished_at_utc || ""))}</span>
          </div>
        </div>
        <div class="archive-detail-hero-side">
          <div class="archive-hero-stat"><div class="k">Total Good</div><div class="v">${esc(totalGood)}</div></div>
          <div class="archive-hero-stat"><div class="k">Good</div><div class="v">${esc(item.good_total ?? 0)}</div></div>
          <div class="archive-hero-stat"><div class="k">Butal</div><div class="v">${esc(item.butal_total ?? 0)}</div></div>
          <div class="archive-hero-stat"><div class="k">Reject</div><div class="v">${esc(item.reject_total ?? 0)}</div></div>
        </div>
      </div>
    `;
    const materialKey = value => String(value || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
    const partKeys = part => [part?.sku, part?.name, part?.part_name, part?.material_name, part?.product_name, part?.description]
      .map(materialKey)
      .filter(Boolean);
    const rawKeys = row => [row?.material_sku, row?.sku, row?.material_product_id, row?.product_id, row?.material_code, row?.material_name, row?.material]
      .map(materialKey)
      .filter(Boolean);
    const scannedQtyForPart = part => {
      const keys = new Set(partKeys(part));
      if(!keys.size) return "";
      return rawLogs.reduce((sum, row) => {
        const hit = rawKeys(row).some(k => keys.has(k));
        return hit ? sum + Number(row?.qty || row?.quantity || 0) : sum;
      }, 0);
    };
    const jobApiSummary = {
      ref_no: job.ref_no || job.code || item.job_code || "-",
      status: job.status || "-",
      mold: jobDetails.mold || job.custom_05 || "-",
      color: jobDetails.color || job.custom_06 || "-",
      machine_num: jobDetails.machine_num || item.machine_code || "-",
      machine_tons: jobDetails.machine_tons || "-",
      no_of_cavity: jobDetails.no_of_cavity || "-",
      qty_per_shift: jobDetails.qty_per_shift || job.custom_11 || "-",
      standard_cycle_time: jobDetails.std_cycle_time || job.custom_09 || item.cycle_time_current || "-",
    };
    const summaryIdentity = {
      record_type: item.record_type || "SHIFT_PARTIAL",
      review_status: item.review_status || "-",
      reason: item.reason || "-",
      machine_code: item.machine_code || "-",
      machine_name: item.machine_name || item.machine_code || "-",
      job_code: item.job_code || "-",
      job_name: item.job_name || "-",
      operator_id: item.operator_id || "-",
      operator_name: displayNameForId(item.operator_id || item.operator_name || "-"),
      shift_index: item.shift_index ?? "-",
      started_at_utc: item.started_at_utc || "-",
      ended_at_utc: item.ended_at_utc || item.finished_at_utc || "-",
    };
    const summaryProduction = {
      pack_count: item.pack_count ?? 0,
      good_total: item.good_total ?? 0,
      butal_total: item.butal_total ?? 0,
      reject_total: item.reject_total ?? 0,
      no_shot_total: item.no_shot_total ?? 0,
      startup_reject_total: item.startup_reject_total ?? 0,
      total_good: item.total_good ?? item.partial_qty ?? 0,
      partial_qty: item.partial_qty ?? item.total_good ?? 0,
      raw_sacks_count: item.raw_sacks_count ?? 0,
    };
    const summaryTiming = {
      cycle_time_current: item.cycle_time_current || "-",
      cycle_time_shift_avg_seconds: item.cycle_time_shift_avg_seconds ?? "-",
      qty_per_shift_avg_cycle: item.qty_per_shift_avg_cycle ?? "-",
      downtime_reason_code: item.downtime_reason_code || "-",
      downtime_reason_text: item.downtime_reason_text || "-",
      downtime_last_seconds: item.downtime_last_seconds ?? 0,
    };
    const summaryPeople = {
      maintenance_name: item.maintenance_name || "-",
      supervisor_name: item.supervisor_name || "-",
      linkage_enabled: !!item.linkage_enabled,
      linkage_job_code: item.linkage_job_code || "-",
      linkage_job_name: item.linkage_job_name || "-",
      raw_material_logs_count: rawLogs.length,
      raw_material_scans_count: rawScans.length,
      product_pack_history_count: packHistory.length,
      reject_review_logs_count: rejectReviews.length,
      partials_count: partials.length,
      product_parts_count: productParts.length,
    };
    return {
      summary: [
        { title: "", kind: "html", wide: true, content: shiftHero },
        { title: "Production", kind: "metrics", wide: true, content: [
          { label: "Pack", value: item.pack_count ?? 0 },
          { label: "Good", value: item.good_total ?? 0, tone: "good" },
          { label: "Butal", value: item.butal_total ?? 0, tone: Number(item.butal_total || 0) > 0 ? "warn" : "" },
          { label: "Reject", value: item.reject_total ?? 0, tone: Number(item.reject_total || 0) > 0 ? "bad" : "" },
          { label: "No Shot", value: item.no_shot_total ?? 0 },
          { label: "Startup Reject", value: item.startup_reject_total ?? 0 },
          { label: "Total Good", value: totalGood, tone: "good" },
          { label: "Partial Qty", value: item.partial_qty ?? totalGood },
        ] },
        { title: "Production Chart", kind: "html", wide: true, content: productionVisualHtml(item) },
        { title: "Shift Details", kind: "html", content: renderKeyValueTableHtml({
          record_type: item.record_type || "SHIFT_PARTIAL",
          reason: item.reason || "-",
          machine: `${item.machine_name || item.machine_code || "-"} (${item.machine_code || "-"})`,
          job: `${item.job_name || "-"} (${item.job_code || "-"})`,
          shift_index: item.shift_index ?? "-",
          started: fmtDateLocal(item.started_at_utc || ""),
          ended: fmtDateLocal(item.ended_at_utc || item.finished_at_utc || ""),
        }) },
        { title: "Timing", kind: "metrics", content: [
          { label: "Cycle Time", value: item.cycle_time_current || "-" },
          { label: "Shift Avg", value: item.cycle_time_shift_avg_seconds ?? "-" },
          { label: "Qty / Shift Avg", value: item.qty_per_shift_avg_cycle ?? "-" },
          { label: "Downtime", value: fmtDowntimeSeconds(item.downtime_last_seconds ?? 0), tone: Number(item.downtime_last_seconds || 0) > 0 ? "warn" : "" },
        ] },
      ],
      rejects: [
        { title: "Reject Breakdown", kind: "html", content: tableFromRows(rejectBreakdownRows, [
          { label: "Reason", value: x => x.reason },
          { label: "Qty", value: x => x.qty },
        ], "No reject breakdown recorded.") },
        { title: "Reject Review Logs", kind: "html", content: tableFromRows(rejectReviews, [
          { label: "Type", value: x => x.entry_type || x.action || "-" },
          { label: "Reason", value: x => x.reason_text || x.reason_code || "-" },
          { label: "Operator", value: x => x.operator_name || x.operator || x.actor_name || "-" },
          { label: "Time", value: x => fmtDateLocal(x.scanned_at || x.timestamp_utc || "") || "-" },
        ], "No reject review logs recorded.", 5) },
      ],
      rawConsumption: [
        { title: "Raw Material Status", kind: "html", wide: true, content: rawMaterialInsightsHtml(item) },
        { title: "Target Raw Materials", kind: "html", content: tableFromRows(targetRawMaterials, [
          { label: "SKU", value: x => x.sku || x.part_code || x.product_code || x.code || "-" },
          { label: "Material", value: x => x.name || x.part_name || x.material_name || x.product_name || x.description || "-" },
          { label: "Target Qty", value: x => x.request_part_qty || x.qty || x.quantity || x.required_qty || "-" },
          { label: "Scanned Qty", value: x => scannedQtyForPart(x) || 0 },
        ], "No target raw materials from Job API.", 8) },
        { title: "Product Pack History", kind: "html", content: tableFromRows(packHistory, [
          { label: "Type", value: x => x.type || x.source || "Pack" },
          { label: "Qty", value: x => x.qty || x.qty_q || x.good_qty || "-" },
          { label: "Time", value: x => fmtDateLocal(x.timestamp_utc || x.scanned_at || "") || "-" },
        ], "No product pack history recorded.", 8) },
      ],
      rawCycle: [
        { title: "Job Details", kind: "html", wide: true, content: `
          <div class="machine-detail-grid">
            ${detailItem("Job Ref", jobApiSummary.ref_no)}
            ${detailItem("Status", jobApiSummary.status)}
            ${detailItem("Mold", jobApiSummary.mold)}
            ${detailItem("Color", jobApiSummary.color)}
            ${detailItem("Machine Tons", jobApiSummary.machine_tons)}
            ${detailItem("Cavities", jobApiSummary.no_of_cavity)}
            ${detailItem("Qty / Shift", jobApiSummary.qty_per_shift)}
            ${detailItem("Standard Cycle", jobApiSummary.standard_cycle_time)}
          </div>
        ` },
        { title: "Job API Product Parts", kind: "html", content: tableFromRows(productParts, [
          { label: "Part", value: x => x.part_name || x.product_name || x.name || x.item_name || "-" },
          { label: "Code", value: x => x.part_code || x.product_code || x.code || x.sku || "-" },
          { label: "Qty", value: x => x.qty || x.quantity || x.required_qty || "-" },
        ], "No product parts recorded.", 5) },
        { title: "Job API Partials", kind: "html", content: tableFromRows(partials, [
          { label: "Date", value: x => fmtDateLocal(x.date || x.created_at || x.timestamp_utc || "") || "-" },
          { label: "Qty", value: x => x.partial_qty || x.qty || x.quantity || "-" },
          { label: "Status", value: x => x.status || "-" },
        ], "No API partials recorded.", 5) },
      ],
      downtime: [
        { title: "Downtime", kind: "metrics", wide: true, content: [
          { label: "Reason Code", value: item.downtime_reason_code || "-" },
          { label: "Reason", value: item.downtime_reason_text || "-" },
          { label: "Duration", value: fmtDowntimeSeconds(item.downtime_last_seconds ?? 0), tone: Number(item.downtime_last_seconds || 0) > 0 ? "warn" : "" },
          { label: "Active", value: item.downtime_active ? "YES" : "NO" },
        ] },
      ],
      people: [
        { title: "Team", kind: "html", content: renderKeyValueTableHtml({
          operator: displayNameForId(item.operator_id || item.operator_name || "-"),
          operator_id: item.operator_id || "-",
          maintenance: item.maintenance_name || "-",
          supervisor: item.supervisor_name || "-",
          qc: qcFromFinishedJob(item),
        }) },
        { title: "Linked Job / Records", kind: "metrics", content: [
          { label: "Linked", value: item.linkage_enabled ? "YES" : "NO", tone: item.linkage_enabled ? "warn" : "" },
          { label: "Linked Job", value: item.linkage_job_name || item.linkage_job_code || "-" },
          { label: "Raw Logs", value: rawLogs.length },
          { label: "Reject Logs", value: rejectReviews.length },
          { label: "Partials", value: partials.length },
          { label: "Product Parts", value: productParts.length },
        ] },
      ],
    };
  }

  function renderSummaryMetricsHtml(row){
    const r = row || {};
    const totalGood = Number(r.total_good ?? ((Number(r.good_total||0) + Number(r.butal_total||0))));
    return `
      <span>Finished Job:</span>
      <span>Pack: ${esc(r.pack_count ?? 0)}</span>
      <span class="dot">•</span>
      <span>Good: ${esc(r.good_total ?? 0)}</span>
      <span class="dot">•</span>
      <span>Butal: ${esc(r.butal_total ?? 0)}</span>
      <span class="dot">•</span>
      <span>Reject: <span class="reject-emph">${esc(r.reject_total ?? 0)}</span></span>
      <span>No Shot: <span class="reject-emph">${esc(r.no_shot_total ?? 0)}</span></span>
      <span class="dot">•</span>
      <span>Total Good: ${esc(totalGood)}</span>
    `;
  }

  function isShiftPartialRecord(row){
    return String(row?.record_type || "").toUpperCase() === "SHIFT_PARTIAL";
  }

  function isApprovedShiftRecord(row){
    return isShiftPartialRecord(row) && String(row?.review_status || "").toUpperCase() === "APPROVED";
  }

  function renderFinishedShiftQueue(rows){
    const items = Array.isArray(rows) ? rows : [];
    if(!finishedShiftQueueList) return;
    if(!items.length){
      finishedShiftQueueList.innerHTML = '<div class="placeholder">No finished shifts yet.</div>';
      return;
    }
    const sorted = [...items].reverse();
    finishedShiftQueueList.innerHTML = sorted.map((r, idx) => {
      const machineCode = String(r.machine_code || "").trim();
      const machineName = r.machine_name || MACHINE_NAME_MAP[machineCode] || machineCode || "-";
      const rawLogs = Array.isArray(r.raw_material_logs) ? r.raw_material_logs : [];
      const rawText = rawLogs.length
        ? rawLogs.map((x, rowIdx) => `${rowIdx+1}. ${x.material_name || x.material || "-"} | qty=${x.qty || 0}`).join("\\n")
        : "No raw materials scanned.";
      return `
        <div class="finished-item">
          <div class="finished-head">
            <h4>${esc(r.job_name || r.job_code || "Shift")} - ${esc(machineName)}</h4>
            <span class="finished-badge">${esc(r.review_status || "PENDING")}</span>
          </div>
          <div class="finished-grid">
            <div><strong>Shift End:</strong> ${esc(fmtDateLocal(r.finished_at_utc || r.ended_at_utc || ""))}</div>
            <div><strong>Operator:</strong> ${esc(displayNameForId(r.operator_id || "-"))}</div>
            <div><strong>Pack:</strong> ${esc(r.pack_count ?? 0)}</div>
            <div><strong>Total Good:</strong> ${esc(r.total_good ?? r.partial_qty ?? 0)}</div>
            <div><strong>Reject:</strong> ${esc(r.reject_total ?? 0)}</div>
            <div><strong>Downtime:</strong> ${esc(fmtDowntimeSeconds(r.downtime_last_seconds))}</div>
          </div>
          <div class="raw-list">${esc(rawText)}</div>
          <div class="finished-actions">
            <button class="approve-print-btn shift-review-btn" data-row-index="${idx}" type="button">${isApprovedShiftRecord(r) ? "View Shift" : "Review Shift"}</button>
          </div>
        </div>
      `;
    }).join("");
  }

  function renderFinishedShiftJobProgress(rows){
    const approved = (Array.isArray(rows) ? rows : []).filter(isApprovedShiftRecord);
    if(!finishedShiftJobProgress) return;
    if(!approved.length){
      finishedShiftJobProgress.innerHTML = '<div class="placeholder">No approved shift partials yet.</div>';
      return;
    }
    const grouped = new Map();
    approved.forEach(row => {
      const key = String(row.job_code || row.job_name || "").trim() || "UNKNOWN";
      if(!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(row);
    });
    const cards = Array.from(grouped.entries()).map(([key, list]) => {
      const first = list[0] || {};
      const approvedQty = list.reduce((sum, row) => sum + Number(row.partial_qty || row.total_good || 0), 0);
      const apiPartials = Array.isArray(first?.job_payload?.data?.partials) ? first.job_payload.data.partials : [];
      const apiPartialQty = apiPartials.reduce((sum, row) => sum + Number(row?.partial_qty || 0), 0);
      const targetQty = Number(first?.job_payload?.data?.job?.approve_qty || first?.job_payload?.data?.job?.request_qty || 0);
      const producedQty = approvedQty + apiPartialQty;
      const remainingQty = Math.max(0, targetQty - producedQty);
      const lines = list
        .slice()
        .sort((a, b) => String(a.finished_at_utc || a.ended_at_utc || "").localeCompare(String(b.finished_at_utc || b.ended_at_utc || "")))
        .map((row, idx) => `${idx + 1}. ${fmtDateLocal(row.finished_at_utc || row.ended_at_utc || "")} | Qty ${row.partial_qty || row.total_good || 0} | Reject ${row.reject_total || 0} | No Shot ${row.no_shot_total || 0} | Downtime ${fmtDowntimeSeconds(row.downtime_last_seconds)}`);
      return `
        <div class="finished-item">
          <div class="finished-head">
            <h4>${esc(first.job_name || first.job_code || key)}</h4>
            <span class="finished-badge">APPROVED PARTIALS</span>
          </div>
          <div class="finished-grid">
            <div><strong>Job Code:</strong> ${esc(first.job_code || key)}</div>
            <div><strong>Approved Shifts:</strong> ${esc(list.length)}</div>
            <div><strong>API Partials:</strong> ${esc(apiPartialQty)}</div>
            <div><strong>Approved Shift Qty:</strong> ${esc(approvedQty)}</div>
            <div><strong>Produced:</strong> ${esc(producedQty)}</div>
            <div><strong>Remaining:</strong> ${esc(remainingQty)}</div>
          </div>
          <div class="raw-list">${esc(lines.join("\\n"))}</div>
        </div>
      `;
    });
    finishedShiftJobProgress.innerHTML = cards.join("");
  }

  function applyGeneratedQrPlanEntry(entry){
    const item = entry && typeof entry === "object" ? entry : {};
    const poRequired = Boolean(item.po_required);
    const stagePo = String(item.po_number || "").trim();
    const payloadText = (poRequired && !stagePo) ? "" : String(item.qr_payload || item.payload || "").trim();
    const parsed = item.parsed && typeof item.parsed === "object" ? item.parsed : {};
    if(overlayQrStageLabel) overlayQrStageLabel.value = String(item.stage_label || "2 / 2 - QR Print");
    overlayQrPayload.value = payloadText || (poRequired ? "PO Number required for Butal QR. Enter PO Number, then Generate QR Payload." : "");
    overlayQty.value = parsed.qty || item.qty || "";
    overlayIndex.value = parsed.index || item.index || "";
    overlayTotal.value = parsed.total || item.total || "";
    overlayLotNumber.value = parsed.lot_number || item.lot_number || "";
    generatedQrState.payload = overlayQrPayload.value || "";
    generatedQrState.qty = overlayQty.value || "";
    generatedQrState.index = overlayIndex.value || "";
    generatedQrState.total = overlayTotal.value || "";
    generatedQrState.lotNumber = overlayLotNumber.value || "";
    generatedQrState.stageLabel = String(item.stage_label || "");
    generatedQrState.stageKind = String(item.stage_kind || "");
    generatedQrState.productName = String(item.product_name || "").trim();
    generatedQrState.productSku = String(item.product_sku || "").trim();
    generatedQrState.productId = String(item.product_id || "").trim();
    if(overlayPoNumberRow){
      overlayPoNumberRow.style.display = poRequired ? "" : "none";
    }
    if(overlayPoNumber){
      overlayPoNumber.value = stagePo;
      overlayPoNumber.placeholder = poRequired ? "Enter PO Number..." : "Not required for raw excess";
    }
    if(overlayProductSelect){
      const sku = String(item.product_sku || "").trim();
      const name = String(item.product_name || "").trim();
      overlayProductSelect.value = (sku && name) ? `${sku} - ${name}` : (name || sku || overlayProductSelect.value || "");
    }
  }

  async function refreshQrStagePayload(){
    if(!overlayReviewSavedApproved){
      overlayQrPayload.value = "Review approval is required before generating QR.";
      return;
    }
    const productId = resolveProductIdFromText(overlayProductSelect.value || "");
    const poNumber = (overlayPoNumber.value || "").trim();
    const needsPo = generatedQrState.stageKind === "BUTAL";
    if(needsPo && !poNumber){
      overlayQrPayload.value = "Enter PO Number for Butal.";
      return;
    }
    const resp = await fetch("/api/raw-material-qr", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_id: productId,
        po_number: poNumber,
        finished_job: activeJobRow || {},
        stage_index: generatedQrState.plan && generatedQrState.plan.length ? generatedQrState.planIndex : 0,
      }),
    });
    const out = await resp.json();
    const plan = Array.isArray(out.qr_plan) ? out.qr_plan : [];
    const payloadText = out.qr_payload || out.error || "Failed to generate.";
    const existingRequests = Array.isArray(generatedQrState.printRequests) ? generatedQrState.printRequests : [];
    generatedQrState = {
      jobKey: jobKeyOf(activeJobRow),
      payload: payloadText,
      qty: "",
      index: "",
      total: "",
      lotNumber: "",
      stageLabel: String(out.stage_label || ""),
      stageKind: "",
      plan: plan,
      planIndex: Number(out.selected_stage_index || 0),
      printRequests: existingRequests,
    };
    if(plan.length){
      applyGeneratedQrPlanEntry(plan[generatedQrState.planIndex] || plan[0]);
    } else {
      overlayQrPayload.value = payloadText;
      const parsed = out.parsed || {};
      overlayQty.value = parsed.qty || "";
      overlayIndex.value = parsed.index || "";
      overlayTotal.value = parsed.total || "";
      overlayLotNumber.value = parsed.lot_number || "";
      if(overlayQrStageLabel) overlayQrStageLabel.value = String(out.stage_label || "1 / 1 - QR Print");
      generatedQrState.qty = overlayQty.value || "";
      generatedQrState.index = overlayIndex.value || "";
      generatedQrState.total = overlayTotal.value || "";
      generatedQrState.lotNumber = overlayLotNumber.value || "";
      generatedQrState.stageKind = "DEFAULT";
    }
  }

  function renderFinishedJobs(rows){
    const allItems = Array.isArray(rows) ? rows : [];
    const shiftItems = allItems.filter(isShiftPartialRecord);
    const finalItems = allItems.filter(r => !isShiftPartialRecord(r));
    finishedShiftState = shiftItems;
    renderFinishedShiftQueue(shiftItems);
    renderFinishedShiftJobProgress(shiftItems);
    const items = finalItems;
    if(finishedJobsInteractionLock){
      pendingFinishedJobsRows = items;
      finishedJobsState = items;
      return;
    }
    pendingFinishedJobsRows = null;
    finishedJobsState = items;
    if(!items.length){
      finishedJobsList.innerHTML = '<div class="placeholder">No finished jobs yet.</div>';
      return;
    }
    const sorted = [...items].reverse();
    finishedJobsList.innerHTML = sorted.map((r, idx) => {
      const machineCode = String(r.machine_code || "").trim();
      const machineName = (r.machine_name || MACHINE_NAME_MAP[machineCode] || machineCode || "-");
      const rawLogs = Array.isArray(r.raw_material_logs) ? r.raw_material_logs : [];
      const relatedApprovedShifts = shiftItems.filter(x => isApprovedShiftRecord(x) && String(x.job_code || "") === String(r.job_code || ""));
      const rawText = rawLogs.length
        ? rawLogs.map((x, idx) => `${idx+1}. ${x.material || "-"} | qty=${x.qty || 0}`).join("\\n")
        : "No raw materials scanned.";
      const partialSummaryText = relatedApprovedShifts.length
        ? relatedApprovedShifts.map((x, rowIdx) => `${rowIdx + 1}. ${fmtDateLocal(x.finished_at_utc || x.ended_at_utc || "")} | Qty ${x.partial_qty || x.total_good || 0} | Reject ${x.reject_total || 0} | No Shot ${x.no_shot_total || 0} | Downtime ${fmtDowntimeSeconds(x.downtime_last_seconds)}`).join("\\n")
        : "No approved shift partials linked to this job yet.";
      const linkageRole = String(r.linkage_role || "").toUpperCase();
      const linkageTotal = Number(r.linkage_group_total_jobs || 0);
      const linkageBadge = linkageRole ? `<span class="linkage-pill">${esc(linkageRole)}${linkageTotal ? ` (${linkageTotal})` : ""}</span>` : "";
      const linkageNote = String(r.linkage_note || "").trim();
      return `
        <div class="finished-item">
          <div class="finished-head">
            <h4>${esc(r.job_name || r.job_code || "Finished Job")} - ${esc(machineName)} ${linkageBadge}</h4>
            <span class="finished-badge">FINISHED</span>
          </div>
          <div class="finished-grid">
            <div><strong>Finished UTC:</strong> ${esc(r.finished_at_utc || "-")}</div>
            <div><strong>Operator:</strong> ${esc(displayNameForId(r.operator_id || "-"))}</div>
            <div><strong>Pack Count:</strong> ${esc(r.pack_count ?? 0)}</div>
            <div><strong>Good:</strong> ${esc(r.good_total ?? 0)}</div>
            <div><strong>Butal:</strong> ${esc(r.butal_total ?? 0)}</div>
            <div><strong>Reject:</strong> ${esc(r.reject_total ?? 0)}</div>
            <div><strong>No Shot:</strong> ${esc(r.no_shot_total ?? 0)}</div>
            <div><strong>Total Good:</strong> ${esc(r.total_good ?? 0)}</div>
            <div><strong>Startup Reject:</strong> ${esc(r.startup_reject_total ?? 0)}</div>
            <div><strong>App Counter:</strong> ${esc(r.machine_counter_app_end ?? "-")}</div>
            <div><strong>Machine Counter:</strong> ${esc(r.machine_counter_end ?? "-")}</div>
            <div><strong>Counter Diff:</strong> ${esc(r.machine_counter_difference ?? "-")}</div>
            <div><strong>Raw Sacks:</strong> ${esc(r.raw_sacks_count ?? 0)}</div>
            <div><strong>Approved Shifts:</strong> ${esc(relatedApprovedShifts.length)}</div>
            <div><strong>Approved Shift Qty:</strong> ${esc(relatedApprovedShifts.reduce((sum, x) => sum + Number(x.partial_qty || x.total_good || 0), 0))}</div>
          </div>
          <div class="raw-list">${esc(rawText)}</div>
          <div class="raw-list">${esc(partialSummaryText)}</div>
          ${linkageNote ? `<div class="finished-linkage-note"><strong>Link Info:</strong> ${esc(linkageNote)}</div>` : ""}
          <div class="finished-actions">
            <button class="approve-print-btn" data-row-index="${idx}" type="button">Approve and Print QR</button>
          </div>
        </div>
      `;
    }).join("");
  }

  function archivedRowToMachineSessionLike(row){
    return {
      _is_archived_detail: true,
      _archive_row: row || {},
      client_id: row.client_id || "",
      machine_code: row.machine_code || "",
      machine_name: row.machine_name || row.machine_code || "",
      job_code: row.job_code || "",
      job_name: row.job_name || "",
      operator_id: row.operator_id || "",
      pack_total: row.pack_count || 0,
      good_total: row.good_total || 0,
      butal_total: row.butal_total || 0,
      reject_total: row.reject_total || 0,
      no_shot_total: row.no_shot_total || 0,
      reject_breakdown: row.reject_breakdown || {},
      raw_sacks_count: row.raw_sacks_count || 0,
      raw_material_scans: row.raw_material_scans || [],
      raw_material_logs: row.raw_material_logs || [],
      startup_reject_total: row.startup_reject_total || 0,
      downtime_reason_code: row.downtime_reason_code || "",
      downtime_reason_text: row.downtime_reason_text || "",
      downtime_last_seconds: row.downtime_last_seconds,
      cycle_time_current: row.cycle_time_current || "",
      maintenance_name: row.maintenance_name || "",
      supervisor_name: row.supervisor_name || "",
      qc_name: row.qc_name || "",
      reject_review_logs: row.reject_review_logs || [],
      job_payload: row.job_payload || {},
      print_request_payload: row.print_request_payload || null,
      print_request_payloads: row.print_request_payloads || [],
      printed_qr_payload: row.printed_qr_payload || null,
      product_pack_history_logs: row.product_pack_history_logs || [],
      butal_scan_logs: row.butal_scan_logs || [],
      last_seen_utc: row.printed_at_utc || row.archived_at_utc || row.finished_at_utc || "",
      last_event: `ARCHIVED${row.printed_at_utc ? " / PRINTED" : ""}`,
      downtime_active: false,
    };
  }

  function renderArchivedJobs(rows){
    const items = Array.isArray(rows) ? rows : [];
    archivedJobsState = items;
    if(!archivedJobsTableWrap) return;
    if(!items.length){
      archivedJobsTableWrap.innerHTML = '<div class="placeholder">No archived jobs yet.</div>';
      return;
    }
    const sorted = [...items].reverse();
    archivedJobsTableWrap.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Machine</th>
            <th>Job</th>
            <th>Operator</th>
            <th>Finished</th>
            <th>Printed</th>
            <th>Status</th>
            <th>Approved / Changed</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          ${sorted.map((r, idx) => {
            const machineCode = String(r.machine_code || "").trim();
            const machineName = r.machine_name || MACHINE_NAME_MAP[machineCode] || machineCode || "-";
            const actor = r.approved_by || r.changed_by || "-";
            const actorRole = r.approved_by_role || r.changed_by_role || "";
            const linkageRole = String(r.linkage_role || "").toUpperCase();
            const linkageTotal = Number(r.linkage_group_total_jobs || 0);
            const linkageNote = String(r.linkage_note || "").trim();
            return `
              <tr>
                <td>${esc(machineName)}<br><span class="muted">${esc(machineCode)}</span></td>
                <td>${esc(r.job_name || r.job_code || "-")}${linkageRole ? ` <span class="linkage-pill">${esc(linkageRole)}${linkageTotal ? ` (${linkageTotal})` : ""}</span>` : ""}<br><span class="muted">${esc(r.job_code || "-")}${linkageNote ? ` | ${esc(linkageNote)}` : ""}</span></td>
                <td>${esc(displayNameForId(r.operator_id || "-"))}</td>
                <td>${esc(fmtDateLocal(r.finished_at_utc || ""))}</td>
                <td>${esc(fmtDateLocal(r.printed_at_utc || r.archived_at_utc || ""))}</td>
                <td>${esc(r.review_status || "ARCHIVED")}</td>
                <td>${esc(actor)}${actorRole ? `<br><span class="muted">${esc(actorRole)}</span>` : ""}</td>
                <td><div class="table-actions"><button class="mini-btn primary archived-view-btn" data-row-index="${idx}" type="button">View</button></div></td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    `;
  }

  function machineStatusArchiveDurationLabel(r){
    const ended = String(r?.ended_at_utc || "").trim();
    const dur = Number(r?.duration_seconds);
    if(Number.isFinite(dur) && dur >= 0) return fmtDowntimeSeconds(dur);
    const startedIso = String(r?.started_at_utc || "").trim();
    const startedMs = startedIso ? new Date(startedIso).getTime() : NaN;
    if(!ended && Number.isFinite(startedMs)){
      const liveSec = Math.max(0, Math.floor((Date.now() - startedMs) / 1000));
      return `${fmtDowntimeSeconds(liveSec)} (ongoing)`;
    }
    return "-";
  }

  function renderMachineStatusArchive(rows){
    const items = Array.isArray(rows) ? rows : [];
    machineStatusArchiveState = items;
    if(!machineStatusArchiveTableWrap) return;
    if(!items.length){
      machineStatusArchiveTableWrap.innerHTML = '<div class="placeholder">No machine status archive logs yet.</div>';
      return;
    }
    const sorted = [...items].reverse();
    machineStatusArchiveTableWrap.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Machine</th>
            <th>Status</th>
            <th>Reason</th>
            <th>Set By</th>
            <th>Start</th>
            <th>End</th>
            <th>Duration</th>
          </tr>
        </thead>
        <tbody>
          ${sorted.map((r) => {
            const machineCode = String(r.machine_code || "").trim();
            const machineName = r.machine_name || MACHINE_NAME_MAP[machineCode] || machineCode || "-";
            const by = `${r.set_by_name || "-"}${r.set_by_role ? ` (${r.set_by_role})` : ""}`;
            return `
              <tr>
                <td>${esc(machineName)}<br><span class="muted">${esc(machineCode)}</span></td>
                <td>${esc(r.status || "-")}</td>
                <td>${esc(r.reason || "-")}</td>
                <td>${esc(by)}<br><span class="muted">${esc(r.set_by_badge || "-")}</span></td>
                <td>${esc(fmtDateLocal(r.started_at_utc || ""))}</td>
                <td>${esc(fmtDateLocal(r.ended_at_utc || ""))}</td>
                <td>${esc(machineStatusArchiveDurationLabel(r))}</td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    `;
  }

  function buildDowntimeArchiveRows(finishedRows, archivedRows){
    const all = [...(Array.isArray(finishedRows) ? finishedRows : []), ...(Array.isArray(archivedRows) ? archivedRows : [])];
    const seen = new Set();
    const out = [];
    for(const r of all){
      if(!r || typeof r !== "object") continue;
      const sec = Number(r.downtime_last_seconds);
      const active = Boolean(r.downtime_active);
      const reasonCode = String(r.downtime_reason_code || "").trim();
      const reasonText = String(r.downtime_reason_text || "").trim();
      if(!(Number.isFinite(sec) && sec > 0) && !active) continue;
      if(!reasonCode && !reasonText && !(Number.isFinite(sec) && sec > 0)) continue;
      const key = [
        String(r.machine_code || ""),
        String(r.job_code || ""),
        String(r.finished_at_utc || r.printed_at_utc || r.archived_at_utc || ""),
        String(reasonCode),
        String(reasonText),
        String(Number.isFinite(sec) ? sec : ""),
      ].join("|");
      if(seen.has(key)) continue;
      seen.add(key);
      out.push({
        machine_code: String(r.machine_code || "").trim(),
        machine_name: String(r.machine_name || "").trim(),
        job_code: String(r.job_code || "").trim(),
        job_name: String(r.job_name || "").trim(),
        operator_id: String(r.operator_id || "").trim(),
        maintenance_name: String(r.maintenance_name || "").trim(),
        reason_code: reasonCode,
        reason_text: reasonText,
        duration_seconds: Number.isFinite(sec) ? Math.max(0, Math.floor(sec)) : null,
        at_utc: String(r.finished_at_utc || r.printed_at_utc || r.archived_at_utc || r.last_seen_utc || "").trim(),
        source: String(r.printed_at_utc || r.archived_at_utc ? "Archived Job" : "Finished Job"),
      });
    }
    return out.sort((a, b) => {
      const ta = new Date(a.at_utc || 0).getTime() || 0;
      const tb = new Date(b.at_utc || 0).getTime() || 0;
      return tb - ta;
    });
  }

  function renderDowntimeArchive(finishedRows, archivedRows){
    if(!downtimeArchiveTableWrap) return;
    const rows = buildDowntimeArchiveRows(finishedRows, archivedRows);
    if(!rows.length){
      downtimeArchiveTableWrap.innerHTML = '<div class="placeholder">No downtime archive rows yet.</div>';
      return;
    }
    downtimeArchiveTableWrap.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Machine</th>
            <th>Job</th>
            <th>Operator</th>
            <th>Reason</th>
            <th>Duration</th>
            <th>Recorded</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((r) => {
            const machineName = r.machine_name || MACHINE_NAME_MAP[r.machine_code] || r.machine_code || "-";
            const reason = [r.reason_code, r.reason_text].filter(Boolean).join(" - ") || "-";
            return `
              <tr>
                <td>${esc(machineName)}<br><span class="muted">${esc(r.machine_code || "-")}</span></td>
                <td>${esc(r.job_name || r.job_code || "-")}<br><span class="muted">${esc(r.job_code || "-")}</span></td>
                <td>${esc(displayNameForId(r.operator_id || "-"))}</td>
                <td>${esc(reason)}</td>
                <td>${esc(fmtDowntimeSeconds(r.duration_seconds))}</td>
                <td>${esc(fmtDateLocal(r.at_utc || ""))}</td>
                <td>${esc(r.source || "-")}</td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    `;
  }

  function maintenancePeopleFromState(state){
    const byBadge = new Map();
    const profiles = Array.isArray(state?.maintenance_profiles) ? state.maintenance_profiles : [];
    profiles.forEach((row) => {
      const badge = String(row?.id_number || "").trim();
      if(!badge) return;
      byBadge.set(badge, {
        badge,
        name: String(row?.name || badge).trim() || badge,
        source: "profile",
      });
    });
    const dailyRoles = (state?.daily_roles && typeof state.daily_roles === "object") ? state.daily_roles : {};
    for(const [badge, row] of Object.entries(dailyRoles)){
      const rights = String(row?.rights || "").trim().toLowerCase();
      const companyRole = String(row?.company_role || "").trim().toLowerCase();
      if(rights !== "maintenance" && companyRole !== "maintenance") continue;
      const existing = byBadge.get(badge) || {};
      byBadge.set(badge, {
        badge,
        name: String(row?.name || existing.name || badge).trim() || badge,
        source: existing.source ? "profile+daily" : "daily",
      });
    }
    return Array.from(byBadge.values()).sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
  }

  function maintenanceMachineDurationSeconds(session){
    const active = Boolean(session?.downtime_active);
    const startDowntime = Number(session?.downtime_started_at || 0);
    const startWait = Number(session?.downtime_wait_started_at || 0);
    if(active && startDowntime > 0){
      return Math.max(0, Math.floor((Date.now() / 1000) - startDowntime));
    }
    if(active){
      return Math.max(0, Math.floor(Number(session?.downtime_last_seconds || 0)));
    }
    if(startWait > 0){
      return Math.max(0, Math.floor((Date.now() / 1000) - startWait));
    }
    return Math.max(0, Math.floor(Number(session?.downtime_wait_last_seconds || 0)));
  }

  function renderMaintenanceMachineCard(s){
    const machineName = s.machine_name || MACHINE_NAME_MAP[s.machine_code] || s.machine_code || "-";
    const active = Boolean(s.downtime_active);
    const duration = maintenanceMachineDurationSeconds(s);
    return `
      <div class="maintenance-machine ${active ? "busy" : "waiting"}">
        <div class="maintenance-machine-title">${esc(machineName)}: ${esc(active ? (s.downtime_reason_text || "Fixing") : "Waiting")}</div>
        <div class="maintenance-machine-time">${esc(fmtDowntimeSeconds(duration))}</div>
      </div>
    `;
  }

  function maintenanceCallReason(s){
    const code = String(s?.pdr_operator_reason_code || s?.downtime_reason_code || "").trim();
    const text = String(s?.pdr_operator_reason_text || s?.downtime_reason_text || "").trim();
    if(code && text) return `${code} - ${text}`;
    return text || code || "PDR call";
  }

  function renderMaintenanceCallBoard(calls){
    const rows = Array.isArray(calls) ? calls : [];
    if(maintenanceCallCount){
      maintenanceCallCount.textContent = `${rows.filter(s => !String(s.maintenance_name || "").trim()).length} waiting`;
    }
    if(!maintenanceCallBoard) return;
    if(!rows.length){
      maintenanceCallBoard.innerHTML = '<div class="placeholder" style="margin-top:0;">No active maintenance calls.</div>';
      return;
    }
    maintenanceCallBoard.innerHTML = rows.map((s) => {
      const machineName = s.machine_name || MACHINE_NAME_MAP[s.machine_code] || s.machine_code || "-";
      const assigned = String(s.maintenance_name || "").trim();
      const active = Boolean(s.downtime_active);
      const status = assigned ? (active ? "Repairing" : "Assigned") : "Waiting";
      const duration = maintenanceMachineDurationSeconds(s);
      return `
        <div class="maintenance-call-card ${active ? "active" : ""}">
          <div class="maintenance-call-top">
            <div class="maintenance-call-machine">${esc(machineName)}</div>
            <div class="maintenance-call-status ${active ? "active" : ""}">${esc(status)}</div>
          </div>
          <div class="maintenance-call-reason">${esc(maintenanceCallReason(s))}</div>
          <div class="maintenance-call-meta">Job: <strong>${esc(s.job_name || s.job_code || "-")}</strong></div>
          <div class="maintenance-call-meta">Operator: <strong>${esc(displayNameForId(s.operator_id || "-"))}</strong></div>
          <div class="maintenance-call-meta">Maintenance: <strong>${esc(assigned || "Not assigned")}</strong></div>
          <div class="maintenance-call-timer">${esc(fmtDowntimeSeconds(duration))}</div>
        </div>
      `;
    }).join("");
  }

  function maintenanceDateLabel(iso){
    const date = iso ? new Date(iso) : new Date();
    if(Number.isNaN(date.getTime())) return "Date unavailable";
    return date.toLocaleString("en-US", {
      weekday: "short",
      month: "short",
      day: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  }

  function buildMaintenancePerfMap(state){
    const allRows = buildDowntimeArchiveRows(state?.finished_jobs || [], state?.archived_jobs || []);
    const perfMap = new Map();
    allRows.forEach((row) => {
      const maintenanceName = String(row.maintenance_name || "").trim();
      if(!maintenanceName || !Number.isFinite(Number(row.duration_seconds))) return;
      const stat = perfMap.get(maintenanceName) || { name: maintenanceName, count: 0, total: 0, fastest: null, latest_utc: "" };
      const sec = Math.max(0, Math.floor(Number(row.duration_seconds || 0)));
      stat.count += 1;
      stat.total += sec;
      stat.fastest = stat.fastest === null ? sec : Math.min(stat.fastest, sec);
      if(String(row.at_utc || "").trim() > String(stat.latest_utc || "").trim()) stat.latest_utc = String(row.at_utc || "").trim();
      perfMap.set(maintenanceName, stat);
    });
    return perfMap;
  }

  function activeMaintenanceMachineRows(sessions){
    return (Array.isArray(sessions) ? sessions : []).filter((s) => {
      if(!s || typeof s !== "object") return false;
      const hasDowntime = Boolean(s.downtime_active);
      const hasWait = Number(s.downtime_wait_started_at || 0) > 0 || Number(s.downtime_wait_last_seconds || 0) > 0;
      const hasReason = String(s.downtime_reason_code || s.downtime_reason_text || s.pdr_operator_reason_code || s.pdr_operator_reason_text || "").trim() !== "";
      return hasReason && (hasDowntime || hasWait);
    });
  }

  function renderMaintenanceTab(state){
    const sessions = Array.isArray(state?.sessions) ? state.sessions : [];
    const maintenancePeople = maintenancePeopleFromState(state);
    const activeMachines = activeMaintenanceMachineRows(sessions);
    const perfMap = buildMaintenancePerfMap(state);
    const assignments = new Map();
    activeMachines.forEach((s) => {
      const name = String(s.maintenance_name || "").trim();
      if(!name) return;
      const rows = assignments.get(name) || [];
      rows.push(s);
      assignments.set(name, rows);
    });
    const busyCount = assignments.size;
    const availableCount = Math.max(0, maintenancePeople.length - busyCount);
    const waitingCount = activeMachines.filter(s => !String(s.maintenance_name || "").trim()).length;
    const activeFixCount = activeMachines.filter(s => Boolean(s.downtime_active)).length;
    if(maintenanceCurrentDate){
      maintenanceCurrentDate.textContent = maintenanceDateLabel(state?.server_time_utc || "");
    }

    if(maintenanceSummary){
      maintenanceSummary.innerHTML = `
        <div class="maintenance-metric blue"><div><div class="k">Maintenance Team</div><div class="v">${esc(maintenancePeople.length)}</div><div class="s">Technicians available in profiles or daily roles.</div></div><div class="icon"></div></div>
        <div class="maintenance-metric green"><div><div class="k">Available Now</div><div class="v">${esc(availableCount)}</div><div class="s">Not currently assigned to active downtime.</div></div><div class="icon"></div></div>
        <div class="maintenance-metric amber"><div><div class="k">Active Repairs</div><div class="v">${esc(activeFixCount)}</div><div class="s">Machines currently in repair downtime.</div></div><div class="icon"></div></div>
        <div class="maintenance-metric red"><div><div class="k">Waiting Queue</div><div class="v">${esc(waitingCount)}</div><div class="s">Machines waiting for maintenance assignment.</div></div><div class="icon"></div></div>
      `;
    }

    renderMaintenanceCallBoard(activeMachines);

    if(maintenancePeopleList){
      if(!maintenancePeople.length){
        maintenancePeopleList.innerHTML = '<div class="placeholder">No maintenance profiles yet.</div>';
      } else {
        const unassigned = activeMachines.filter(s => !String(s.maintenance_name || "").trim());
        maintenancePeopleList.innerHTML = maintenancePeople.map((person) => {
          const jobs = assignments.get(person.name) || [];
          const busy = jobs.length > 0;
          const perf = perfMap.get(person.name) || { count: 0, total: 0, fastest: null };
          const avgRepair = perf.count ? fmtDowntimeSeconds(Math.round(perf.total / Math.max(1, perf.count))) : "00:00:00";
          const waitFreq = perf.count ? `${Math.round((jobs.length / Math.max(1, perf.count)) * 100)}%` : "0%";
          const avgWait = jobs.length ? fmtDowntimeSeconds(Math.round(jobs.reduce((sum, row) => sum + maintenanceMachineDurationSeconds(row), 0) / jobs.length)) : "00:00:00";
          return `
            <div class="maintenance-person ${busy ? "busy" : "available"}">
              <div class="maintenance-avatar-wrap">
                <div class="maintenance-avatar" aria-hidden="true"></div>
              </div>
              <div class="maintenance-person-main">
                <div class="maintenance-person-head">
                  <div>
                    <div class="title">${esc(person.name)}</div>
                    <div class="meta">Badge: ${esc(person.badge || "-")}</div>
                  </div>
                  <span class="maintenance-badge ${busy ? "busy" : "available"}">${busy ? "Fixing" : "Available"}</span>
                </div>
                <div class="submeta">${jobs.length ? `${jobs.length} active machine assignment${jobs.length > 1 ? "s" : ""}.` : "No active machines."}<br>${jobs.length ? "Ready to continue assigned work." : "Ready for new call."}</div>
                <div class="maintenance-machine-grid">
                  ${jobs.length ? jobs.map(renderMaintenanceMachineCard).join("") : '<div class="submeta">No active machines.</div>'}
                </div>
              </div>
              <div class="maintenance-stats">
                <div class="maintenance-stats-title">Lifetime Stats</div>
                <div class="maintenance-stat-line"><span class="maintenance-stat-icon">◷</span><span>Avg. Repair: ${esc(avgRepair)}</span></div>
                <div class="maintenance-stat-line"><span class="maintenance-stat-icon">⟳</span><span>Wait Freq: ${esc(waitFreq)}</span></div>
                <div class="maintenance-stat-line"><span class="maintenance-stat-icon">◷</span><span>Avg. Wait: ${esc(avgWait)}</span></div>
              </div>
            </div>
          `;
        }).join("") + (
          unassigned.length ? `
            <div class="maintenance-person">
              <div class="maintenance-avatar-wrap">
                <div class="maintenance-avatar" aria-hidden="true"></div>
              </div>
              <div class="maintenance-person-main">
                <div class="maintenance-person-head">
                  <div>
                    <div class="title">Unassigned Maintenance Calls</div>
                    <div class="meta">Badge: -</div>
                  </div>
                  <span class="maintenance-badge waiting">Waiting</span>
                </div>
                <div class="submeta">Machines waiting for maintenance assignment.</div>
                <div class="maintenance-machine-grid">
                  ${unassigned.map(renderMaintenanceMachineCard).join("")}
                </div>
              </div>
              <div class="maintenance-stats">
                <div class="maintenance-stats-title">Queue Stats</div>
                <div class="maintenance-stat-line"><span class="maintenance-stat-icon">◷</span><span>Waiting jobs: ${esc(unassigned.length)}</span></div>
                <div class="maintenance-stat-line"><span class="maintenance-stat-icon">⚙</span><span>Active repairs: ${esc(activeFixCount)}</span></div>
                <div class="maintenance-stat-line"><span class="maintenance-stat-icon">△</span><span>Needs assignment now.</span></div>
              </div>
            </div>
          ` : ""
        );
      }
    }

    if(maintenancePerformanceTableWrap){
      const perfRows = Array.from(perfMap.values()).sort((a, b) => (a.total / Math.max(1, a.count)) - (b.total / Math.max(1, b.count)));
      if(!perfRows.length){
        maintenancePerformanceTableWrap.innerHTML = '<div class="placeholder">No downtime records with maintenance names yet.</div>';
      } else {
        maintenancePerformanceTableWrap.innerHTML = `
          <table class="data-table">
            <thead>
              <tr>
                <th>Maintenance</th>
                <th>Resolved Downtimes</th>
                <th>Average Repair Time</th>
                <th>Fastest Repair</th>
                <th>Last Recorded</th>
              </tr>
            </thead>
            <tbody>
              ${perfRows.map((row) => `
                <tr>
                  <td>${esc(row.name)}</td>
                  <td>${esc(row.count)}</td>
                  <td>${esc(fmtDowntimeSeconds(Math.round(row.total / Math.max(1, row.count))))}</td>
                  <td>${esc(fmtDowntimeSeconds(row.fastest))}</td>
                  <td>${esc(fmtDateLocal(row.latest_utc || ""))}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        `;
      }
    }
  }

  function queueStatusBadge(status){
    const raw = String(status || "").trim();
    const css = raw.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "running";
    return `<span class="queue-status-badge ${esc(css)}">${esc(raw || "RUNNING")}</span>`;
  }

  function queueRunningRows(rows){
    return (Array.isArray(rows) ? rows : []).filter(r => {
      const status = String(r?.status || "").trim();
      return status !== "DONE" && status !== "DISCONNECTED";
    });
  }

  function preferredQueueFinish(row){
    return row?.expected_finish_pack_utc || row?.expected_finish_act_utc || "";
  }

  function preferredQueueRemaining(row){
    return row?.remaining_seconds_pack ?? row?.remaining_seconds_act ?? null;
  }

  function planningCardCycleSeconds(card, fallback=0){
    const raw = card?.std_cycle_time ?? card?.cycle_time ?? card?.cycle_time_seconds ?? fallback;
    const n = Number(raw);
    return Number.isFinite(n) && n > 0 ? n : Number(fallback || 0);
  }

  function planningShiftHours(card){
    const raw = card?.shift_hours ?? card?.hours_per_shift ?? card?.total_hours_per_shift ?? 12;
    const n = Number(raw);
    return Number.isFinite(n) && n > 0 ? n : 12;
  }

  function planningQtyPerShift(card, fallbackCycle=0){
    const explicit = Number(card?.qty_per_shift || card?.quantity_per_shift || 0);
    if(Number.isFinite(explicit) && explicit > 0) return explicit;
    const cycle = planningCardCycleSeconds(card, fallbackCycle);
    if(!cycle) return 0;
    const cavity = Math.max(1, Number(card?.cavity_count || card?.cavity || 1));
    return Math.floor(((planningShiftHours(card) * 60 * 60) / cycle) * cavity);
  }

  function planningCardDurationSeconds(card, fallbackCycle=0){
    const qty = Math.max(0, Number(card?.request_qty || card?.qty || card?.quantity || 0));
    if(!qty) return 0;
    const qtyPerShift = planningQtyPerShift(card, fallbackCycle);
    const hours = planningShiftHours(card);
    if(qtyPerShift > 0) return (qty / qtyPerShift) * hours * 60 * 60;
    const cycle = planningCardCycleSeconds(card, fallbackCycle);
    const cavity = Math.max(1, Number(card?.cavity_count || card?.cavity || 1));
    return cycle ? Math.ceil(qty / cavity) * cycle : 0;
  }

  function renderPlanningOpsSummary(state, rows){
    if(!planningOpsSummary) return;
    const list = Array.isArray(rows) ? rows : [];
    const runningRows = queueRunningRows(list);
    const activeMachineCodes = new Set(runningRows.map(r => String(r?.machine_code || "").trim()).filter(Boolean));
    const lowStockCount = (lowStockItemsState || []).length;
    const nearFinishRows = runningRows.filter(r => {
      const remain = preferredQueueRemaining(r);
      return remain != null && Number(remain) >= 0 && Number(remain) <= 7200;
    });
    const machineTotal = Math.max(1, DEFAULT_MACHINE_CODES.length || activeMachineCodes.size || 1);
    const utilization = Math.round((activeMachineCodes.size / machineTotal) * 100);
    const nextFinish = nearFinishRows
      .slice()
      .sort((a,b) => Number(preferredQueueRemaining(a) ?? 999999999) - Number(preferredQueueRemaining(b) ?? 999999999))[0];
    planningOpsSummary.innerHTML = `
      <div class="planning-ops-metric"><div class="k">Active Jobs</div><div class="v">${esc(list.length)}</div><div class="s">${esc(runningRows.length)} running now</div></div>
      <div class="planning-ops-metric"><div class="k">Active Machines</div><div class="v">${esc(activeMachineCodes.size)}</div><div class="s">${esc(machineTotal)} configured lanes</div></div>
      <div class="planning-ops-metric warn"><div class="k">Low Stock</div><div class="v">${esc(lowStockCount)}</div><div class="s">IMS recommendations loaded</div></div>
      <div class="planning-ops-metric ${nearFinishRows.length ? "warn" : "good"}"><div class="k">Nearly Finished</div><div class="v">${esc(nearFinishRows.length)}</div><div class="s">${nextFinish ? `${esc(nextFinish.machine_name || nextFinish.machine_code || "-")} in ${esc(fmtDowntimeSeconds(preferredQueueRemaining(nextFinish)))}` : "No jobs under 2h"}</div></div>
      <div class="planning-ops-metric"><div class="k">Utilization</div><div class="v">${esc(utilization)}%</div><div class="s">Running machines / lanes</div></div>
    `;
  }

  function renderPlanningQueue(rows){
    if(!planningQueueTableWrap) return;
    const list = Array.isArray(rows) ? rows : [];
    if(planningQueueHint) planningQueueHint.textContent = `${list.length} active job${list.length === 1 ? "" : "s"}`;
    if(!list.length){
      planningQueueTableWrap.innerHTML = '<div class="placeholder">No active jobs in queue yet.</div>';
      return;
    }
    planningQueueTableWrap.innerHTML = `
      <table class="data-table">
        <thead><tr><th>Machine</th><th>Job</th><th>Start</th><th>Est Finish</th><th>Remaining</th><th>Cycle Basis</th></tr></thead>
        <tbody>
          ${list.map(row => {
            const finish = preferredQueueFinish(row);
            const remaining = preferredQueueRemaining(row);
            const cycle = row?.live_cycle_seconds ? `${Number(row.live_cycle_seconds).toFixed(2)}s pack` : (row?.act_cycle_seconds ? `${Number(row.act_cycle_seconds).toFixed(2)}s act` : "-");
            return `<tr>
              <td>${esc(row?.machine_name || row?.machine_code || "-")}<br><span class="muted">${esc(row?.machine_code || "-")}</span></td>
              <td>${esc(row?.job_name || row?.job_code || "-")}<br><span class="muted">${esc(row?.job_code || "-")}</span></td>
              <td>${esc(row?.job_started_at ? fmtDateLocal(row.job_started_at) : "-")}</td>
              <td>${esc(finish ? fmtDateLocal(finish) : "-")}</td>
              <td>${esc(remaining != null ? fmtDowntimeSeconds(remaining) : "-")}</td>
              <td>${esc(cycle)}</td>
            </tr>`;
          }).join("")}
        </tbody>
      </table>
    `;
  }

  function planningMachineTimingHtml(code, queueRow, cards){
    const finish = preferredQueueFinish(queueRow);
    const remaining = preferredQueueRemaining(queueRow);
    const activeStart = queueRow?.job_started_at ? fmtDateLocal(queueRow.job_started_at) : "-";
    const activeFinish = finish ? fmtDateLocal(finish) : "-";
    const fallbackCycle = Number(queueRow?.live_cycle_seconds || queueRow?.act_cycle_seconds || 0);
    let nextStartMs = finish ? Date.parse(finish) : Date.now();
    if(!Number.isFinite(nextStartMs)) nextStartMs = Date.now();
    const firstPlanned = Array.isArray(cards) && cards.length ? cards[0] : null;
    const firstDuration = firstPlanned ? planningCardDurationSeconds(firstPlanned, fallbackCycle) : 0;
    const firstEndMs = firstDuration ? nextStartMs + firstDuration * 1000 : null;
    const firstQtyPerShift = firstPlanned ? planningQtyPerShift(firstPlanned, fallbackCycle) : 0;
    const firstShiftHours = firstPlanned ? planningShiftHours(firstPlanned) : 12;
    return `
      <div class="planning-lane-time">
        <span>Live start: ${esc(activeStart)}</span>
        <span>Est finish: ${esc(activeFinish)}${remaining != null ? ` (${esc(fmtDowntimeSeconds(remaining))} left)` : ""}</span>
        <span>Next start: ${esc(firstPlanned ? new Date(nextStartMs).toLocaleString() : "-")}</span>
        <span>Next est finish: ${esc(firstEndMs ? new Date(firstEndMs).toLocaleString() : "-")}${firstQtyPerShift ? ` (${esc(Math.round(firstQtyPerShift))}/shift @ ${esc(firstShiftHours)}h)` : ""}</span>
      </div>
    `;
  }

  function renderJobQueue(rows){
    if(!jobQueueTableWrap) return;
    const list = Array.isArray(rows) ? rows : [];
    const runningRows = queueRunningRows(list);
    const disconnectedRows = list.filter(r => String(r?.status || "").trim() === "DISCONNECTED");
    const remainingTotal = runningRows.reduce((sum, r) => sum + Number(r?.remaining_qty || 0), 0);

    if(jobQueueSummary){
      jobQueueSummary.innerHTML = `
        <div class="job-queue-metric"><div class="k">Active Jobs</div><div class="v">${esc(list.length)}</div></div>
        <div class="job-queue-metric"><div class="k">Running Jobs</div><div class="v">${esc(runningRows.length)}</div></div>
        <div class="job-queue-metric"><div class="k">Disconnected</div><div class="v">${esc(disconnectedRows.length)}</div></div>
        <div class="job-queue-metric"><div class="k">Remaining Qty</div><div class="v">${esc(remainingTotal)}</div></div>
      `;
    }

    if(!list.length){
      jobQueueTableWrap.innerHTML = '<div class="placeholder">No active jobs in queue yet.</div>';
      return;
    }

    jobQueueTableWrap.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Machine</th>
            <th>Job</th>
            <th>Operator</th>
            <th>Started</th>
            <th>Status</th>
            <th>Produced</th>
            <th>Target</th>
            <th>Remaining</th>
            <th>Time Remaining</th>
            <th>Ends</th>
            <th>Act Cycle ETA</th>
            <th>Pack Cycle ETA</th>
          </tr>
        </thead>
        <tbody>
          ${list.map((row) => {
            const actCycleText = row?.act_cycle_seconds ? `${Number(row.act_cycle_seconds).toFixed(2)} sec | ${row?.act_qty_per_shift ?? "-"} / shift` : "-";
            const packCycleText = row?.live_cycle_seconds ? `${Number(row.live_cycle_seconds).toFixed(2)} sec | ${row?.live_qty_per_shift ?? "-"} / shift` : "-";
            const noTarget = Number(row?.target_qty || 0) <= 0;
            const isDisconnected = !Boolean(row?.is_connected);
            const startText = row?.job_started_at ? fmtDateLocal(row.job_started_at) : "-";
            const actEtaDate = row?.expected_finish_act_utc ? fmtDateLocal(row.expected_finish_act_utc) : "";
            const actEtaLeft = row?.expected_finish_act_utc ? `${fmtDowntimeSeconds(row?.remaining_seconds_act)} left${isDisconnected ? " (frozen)" : ""}` : (noTarget ? "No target qty" : (actCycleText === "-" ? "No act cycle time" : "Target reached"));
            const packEtaDate = row?.expected_finish_pack_utc ? fmtDateLocal(row.expected_finish_pack_utc) : "";
            const packEtaLeft = row?.expected_finish_pack_utc ? `${fmtDowntimeSeconds(row?.remaining_seconds_pack)} left${isDisconnected ? " (frozen)" : ""}` : (noTarget ? "No target qty" : (packCycleText === "-" ? "No pack cycle time" : "Target reached"));
            const preferredRemaining = row?.remaining_seconds_pack ?? row?.remaining_seconds_act ?? null;
            const preferredEnd = row?.expected_finish_pack_utc || row?.expected_finish_act_utc || "";
            const remainingText = preferredRemaining != null
              ? `${fmtDowntimeSeconds(preferredRemaining)}${isDisconnected ? " (frozen)" : ""}`
              : (noTarget ? "No target qty" : "Target reached");
            const endText = preferredEnd ? fmtDateLocal(preferredEnd) : (noTarget ? "No target qty" : "Target reached");
            return `
              <tr>
                <td>${esc(row?.machine_name || row?.machine_code || "-")}<br><span class="muted">${esc(row?.machine_code || "-")}</span></td>
                <td>${esc(row?.job_name || row?.job_code || "-")}<br><span class="muted">${esc(row?.job_code || "-")}</span></td>
                <td>${esc(displayNameForId(row?.operator_id || "-"))}${row?.last_seen_utc ? `<br><span class="muted">Last seen ${esc(fmtDateLocal(row.last_seen_utc))}</span>` : ""}</td>
                <td>${esc(startText)}</td>
                <td>${queueStatusBadge(row?.status || "RUNNING")}</td>
                <td>${esc(row?.produced_now ?? 0)}<br><span class="muted">Pack ${esc(row?.pack_count ?? 0)}</span></td>
                <td>${esc(row?.target_qty ?? 0)}<br><span class="muted">Cavity ${esc(row?.cavity_count ?? 1)}</span></td>
                <td>${esc(row?.remaining_qty ?? 0)}${Number(row?.overrun_qty || 0) > 0 ? `<br><span class="muted">Over ${esc(row?.overrun_qty || 0)}</span>` : ""}</td>
                <td>${esc(remainingText)}</td>
                <td>${esc(endText)}</td>
                <td>${actEtaDate ? `${esc(actEtaDate)}<br>` : ""}<span class="muted">${esc(actEtaLeft)}</span><br><span class="muted">${esc(actCycleText)}</span></td>
                <td>${packEtaDate ? `${esc(packEtaDate)}<br>` : ""}<span class="muted">${esc(packEtaLeft)}</span><br><span class="muted">${esc(packCycleText)}</span></td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    `;
  }

  function normalizePlanningBoard(board){
    const lanes = (board && typeof board.lanes === "object") ? board.lanes : {};
    const out = { lanes: {}, updated_at_utc: String(board?.updated_at_utc || "") };
    out.lanes.BACKLOG = Array.isArray(lanes.BACKLOG) ? lanes.BACKLOG : [];
    DEFAULT_MACHINE_CODES.forEach(code => { out.lanes[code] = Array.isArray(lanes[code]) ? lanes[code] : []; });
    Object.entries(lanes).forEach(([lane, cards]) => {
      if(!out.lanes[lane] && Array.isArray(cards)) out.lanes[lane] = cards;
    });
    return out;
  }

  function planningLaneCards(lane){
    planningBoard = normalizePlanningBoard(planningBoard);
    return planningBoard.lanes[lane] || [];
  }

  function planningSetStatus(text, isError=false){
    if(!planningStatus) return;
    planningStatus.textContent = text || "";
    planningStatus.style.color = isError ? "#b91c1c" : "#64748b";
  }

  function planningCardHtml(card, lane, queueIndex=null){
    const job = card || {};
    const title = job.job_ref || job.job_name || job.job_id || "Planned Job";
    const roleLabel = queueIndex === 0 ? "NEXT" : (Number.isInteger(queueIndex) ? `QUEUE ${queueIndex + 1}` : (job.source || "PLAN"));
    const roleClass = queueIndex === 0 ? "next" : (Number.isInteger(queueIndex) ? "queue" : "");
    const cardClass = queueIndex === 0 ? " next-job" : (Number.isInteger(queueIndex) ? " queue-job" : "");
    const product = [job.product_sku, job.product_name].filter(Boolean).join(" - ") || job.product_id || "-";
    const details = [
      Number.isInteger(queueIndex) ? (queueIndex === 0 ? "Status: next after ongoing job" : `Status: queued position ${queueIndex + 1}`) : "",
      `Product: ${product}`,
      job.mold ? `Mold: ${job.mold}` : "",
      job.color ? `Color: ${job.color}` : "",
      job.std_cycle_time ? `Cycle: ${job.std_cycle_time}` : "",
      job.request_qty ? `Qty: ${job.request_qty}` : "",
      job.source === "LOW STOCK" ? `Current stock: ${job.low_stock_total ?? 0}${job.low_stock_unit ? ` ${job.low_stock_unit}` : ""}` : "",
      job.source === "LOW STOCK" && job.low_stock_qty_source ? `Source: IMS ${job.low_stock_qty_source}` : "",
      job.source === "LOW STOCK" ? `Threshold: ${job.low_stock_threshold ?? "-"}` : "",
      job.tonnage ? `Tonnage: ${job.tonnage}` : "",
    ].filter(Boolean).join("<br>");
    return `<div class="planning-card${cardClass}" draggable="true" data-card-id="${esc(job.id || "")}" data-lane="${esc(lane)}"><div class="planning-card-top"><div class="planning-job">${esc(title)}</div><span class="planning-chip ${esc(roleClass)}">${esc(roleLabel)}</span></div><div class="planning-meta">${details || "No BMS details available."}</div><div class="planning-card-actions"><button class="planning-remove" type="button" data-card-id="${esc(job.id || "")}" data-lane="${esc(lane)}">Remove</button></div></div>`;
  }

  function livePlanningCardHtml(session){
    const title = session.job_name || session.job_code || "Running Job";
    return `<div class="planning-card live"><div class="planning-card-top"><div class="planning-job">${esc(title)}</div><span class="planning-chip ongoing">ONGOING</span></div><div class="planning-meta">Status: running now<br>Operator: ${esc(session.operator_id || "-")}<br>Pack: ${esc(session.pack_total || 0)} | Good: ${esc(session.good_total || 0)} | Reject: ${esc(session.reject_total || 0)}</div></div>`;
  }

  function renderLowStockRecommendations(items, meta = {}){
    if(!planningLowStockList) return;
    if(Array.isArray(items)) lowStockItemsState = items;
    const q = String(planningLowStockSearch?.value || "").trim().toLowerCase();
    const minStockRaw = String(planningLowStockMin?.value || "").trim();
    const maxStockRaw = String(planningLowStockMax?.value || "").trim();
    const minStock = minStockRaw === "" ? null : Number(minStockRaw);
    const maxStock = maxStockRaw === "" ? null : Number(maxStockRaw);
    const limit = Math.max(1, Number(planningLowStockLimit?.value || 15));
    planningBoard = normalizePlanningBoard(planningBoard);
    const backlogKeys = new Set((planningBoard.lanes.BACKLOG || []).flatMap(card => [
      String(card?.product_id || "").trim(),
      String(card?.product_sku || "").trim(),
      String(card?.sku || "").trim(),
    ]).filter(Boolean));
    const rows = (Array.isArray(items) ? items : lowStockItemsState).filter(item => {
      const productId = String(item?.product_id || "").trim();
      const sku = String(item?.sku || "").trim();
      if((productId && backlogKeys.has(productId)) || (sku && backlogKeys.has(sku))) return false;
      const stock = Number(item?.total_stock ?? 0);
      if(minStock !== null && Number.isFinite(minStock) && stock < minStock) return false;
      if(maxStock !== null && Number.isFinite(maxStock) && stock > maxStock) return false;
      if(!q) return true;
      return [item?.sku, item?.product_id, item?.name, item?.tonnage]
        .some(v => String(v || "").toLowerCase().includes(q));
    });
    const queuedCards = planningLaneCards("BACKLOG");
    const queuedHtml = queuedCards.length ? queuedCards.map(c => planningCardHtml(c, "BACKLOG")).join("") : "";
    if(!rows.length && !queuedCards.length){
      planningLowStockList.innerHTML = `<div class="planning-empty">${esc(meta.error || "No matching low-stock item.")}</div>`;
      return;
    }
    const visible = rows.slice(0, limit);
    const lowStockHtml = visible.map((item, idx) => {
      const wh = Array.isArray(item.warehouses) ? item.warehouses : [];
      const whText = wh
        .filter(x => Number(x?.qty || 0) > 0)
        .slice(0, 3)
        .map(x => `${x.warehouse_name || x.warehouse_id}: ${x.qty}${x.unit ? ` ${x.unit}` : ""}`)
        .join(" | ") || "No warehouse qty";
      const title = item.sku || item.product_id || "Product";
      return `
        <div class="stock-rec-card" draggable="true" data-rec-index="${idx}">
          <div class="stock-rec-top">
            <div class="stock-rec-sku">${esc(title)}</div>
            <span class="stock-rec-badge">${esc(item.total_stock ?? 0)}${item.unit ? ` ${esc(item.unit)}` : ""}</span>
          </div>
          <div class="stock-rec-name">${esc(item.name || "No product name")}</div>
          <div class="stock-rec-meta">
            <span>ID ${esc(item.product_id || "-")}</span>
            ${item.tonnage ? `<span>${esc(item.tonnage)} tons</span>` : ""}
            ${item.qty_source ? `<span>IMS ${esc(item.qty_source)}</span>` : ""}
            <span>Range ${esc(minStockRaw || "0")}-${esc(maxStockRaw || item.threshold || "-")}</span>
          </div>
          <div class="planning-meta">${esc(whText)}</div>
        </div>
      `;
    }).join("");
    planningLowStockList.innerHTML = `${queuedHtml}${lowStockHtml}`;
    planningLowStockList.querySelectorAll(".stock-rec-card[draggable='true']").forEach(cardEl => {
      cardEl.addEventListener("dragstart", ev => {
        const idx = Number(cardEl.getAttribute("data-rec-index") || -1);
        const item = visible[idx];
        const card = item ? queueLowStockPlanningItem(item, { render: false, status: false }) : null;
        if(!card) return;
        planningDragActive = true;
        planningDropCompleted = false;
        ev.dataTransfer.setData("text/plain", card.id || "");
        ev.dataTransfer.effectAllowed = "move";
      });
      cardEl.addEventListener("dragend", () => {
        planningDragActive = false;
        document.querySelectorAll(".planning-dropzone.drag-over").forEach(zone => zone.classList.remove("drag-over"));
        renderPlanningBoard({ ...latestState, planning_board: planningBoard });
      });
    });
  }

  function lowStockItemToPlanningCard(item){
    planningBoard = normalizePlanningBoard(planningBoard);
    const productId = String(item?.product_id || "").trim();
    const sku = String(item?.sku || "").trim();
    const title = sku || productId || "Low Stock Item";
    const card = {
      id: `low-stock-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      job_id: "",
      job_ref: title,
      job_name: title,
      product_id: productId,
      product_name: String(item?.name || "").trim(),
      product_sku: sku,
      tonnage: String(item?.tonnage || "").trim(),
      request_qty: "",
      source: "LOW STOCK",
      low_stock_total: item?.total_stock ?? 0,
      low_stock_unit: item?.unit || "",
      low_stock_qty_source: item?.qty_source || "",
      low_stock_threshold: item?.threshold ?? "",
      warehouses: Array.isArray(item?.warehouses) ? item.warehouses : [],
      created_at_utc: new Date().toISOString(),
    };
    return card;
  }

  function queueLowStockPlanningItem(item, options = {}){
    planningBoard = normalizePlanningBoard(planningBoard);
    const card = lowStockItemToPlanningCard(item);
    const productId = String(card.product_id || "").trim();
    const sku = String(card.product_sku || card.sku || "").trim();
    const title = card.job_ref || card.job_name || "Low Stock Item";
    planningBoard.lanes.BACKLOG.unshift(card);
    lowStockItemsState = (lowStockItemsState || []).filter(x => {
      const sameProduct = productId && String(x?.product_id || "").trim() === productId;
      const sameSku = sku && String(x?.sku || "").trim() === sku;
      return !(sameProduct || sameSku);
    });
    schedulePlanningSave();
    if(options.render !== false){
      renderPlanningBoard({ ...latestState, planning_board: planningBoard });
      renderLowStockRecommendations(lowStockItemsState);
    }
    if(options.status !== false) planningSetStatus(`Queued low-stock recommendation ${title}.`);
    return card;
  }

  async function loadLowStockRecommendations(forceRefresh = false){
    if(!planningLowStockList) return;
    const threshold = Number(planningLowStockMax?.value || 100);
    planningLowStockList.innerHTML = '<div class="planning-empty">Loading IMS stock recommendations...</div>';
    planningSetStatus("Checking IMS low-stock products...");
    try {
      const resp = await fetch(`/api/planning/low-stock?threshold=${encodeURIComponent(threshold)}&refresh=${forceRefresh ? 1 : 0}`);
      const out = await resp.json();
      if(!out.ok){
        lowStockItemsState = [];
        renderLowStockRecommendations([], { error: out.error || "Failed to load low-stock recommendations." });
        planningSetStatus(out.error || "Failed to load low-stock recommendations.", true);
        return;
      }
      lowStockItemsState = out.items || [];
      renderLowStockRecommendations(lowStockItemsState, out);
      renderPlanningOpsSummary(latestState || {}, latestState?.job_queue || []);
      const suffix = out.from_cache ? " from cache" : "";
      planningSetStatus(`Loaded ${(out.items || []).length} low-stock recommendation(s)${suffix}.`);
    } catch(e){
      renderLowStockRecommendations([], { error: `Low-stock lookup failed: ${e}` });
      renderPlanningOpsSummary(latestState || {}, latestState?.job_queue || []);
      planningSetStatus(`Low-stock lookup failed: ${e}`, true);
    }
  }

  function renderPlanningBoard(state){
    if(planningDragActive || Date.now() < planningMachineScrollActiveUntil) return;
    document.querySelectorAll(".planning-machine-grid .planning-dropzone").forEach(zone => {
      const lane = zone.getAttribute("data-lane") || "";
      if(lane) planningMachineDropScrollLeft[lane] = zone.scrollLeft || 0;
    });
    planningBoard = normalizePlanningBoard((planningLocalDirty ? planningBoard : state?.planning_board) || planningBoard);
    renderLowStockRecommendations(lowStockItemsState);
    if(planningMachineGrid){
      const sessionsByMachine = new Map((state?.sessions || []).map(s => [String(s.machine_code || ""), s]));
      const queueByMachine = new Map(((state?.job_queue || [])).map(row => [String(row?.machine_code || "").trim(), row]));
      planningMachineGrid.innerHTML = DEFAULT_MACHINE_CODES.map(code => {
        const cards = planningLaneCards(code);
        const live = sessionsByMachine.get(code);
        const queueRow = queueByMachine.get(code);
        return `<div class="planning-lane"><div class="planning-lane-head"><div><div class="planning-lane-title">${esc(MACHINE_NAME_MAP[code] || code)}</div>${planningMachineTimingHtml(code, queueRow, cards)}</div><div class="planning-lane-count">${esc(cards.length)} planned</div></div><div class="planning-dropzone" data-lane="${esc(code)}">${live && live.job_code ? livePlanningCardHtml(live) : ""}${cards.map((c, idx) => planningCardHtml(c, code, idx)).join("") || (!live || !live.job_code ? '<div class="planning-empty">Drop jobs here.</div>' : "")}</div></div>`;
      }).join("");
    }
    bindPlanningDragHandlers();
    document.querySelectorAll(".planning-machine-grid .planning-dropzone").forEach(zone => {
      const lane = zone.getAttribute("data-lane") || "";
      if(lane && planningMachineDropScrollLeft[lane] != null) zone.scrollLeft = planningMachineDropScrollLeft[lane];
    });
  }

  function findAndMovePlanningCard(cardId, targetLane){
    planningBoard = normalizePlanningBoard(planningBoard);
    let found = null;
    for(const [lane, cards] of Object.entries(planningBoard.lanes)){
      const idx = (cards || []).findIndex(c => String(c.id || "") === String(cardId || ""));
      if(idx >= 0){
        found = cards.splice(idx, 1)[0];
        break;
      }
    }
    if(!found) return false;
    if(!Array.isArray(planningBoard.lanes[targetLane])) planningBoard.lanes[targetLane] = [];
    planningBoard.lanes[targetLane].push(found);
    return true;
  }

  function bindPlanningDragHandlers(){
    const clearPlanningDragState = () => {
      planningDragActive = false;
      document.querySelectorAll(".planning-dropzone.drag-over").forEach(zone => zone.classList.remove("drag-over"));
    };
    const flushPlanningDeferredRender = () => {
      if(!planningDeferredState) return false;
      const state = planningDeferredState;
      planningDeferredState = null;
      render(state);
      return true;
    };
    document.querySelectorAll(".planning-card[draggable='true']").forEach(card => {
      card.addEventListener("dragstart", ev => {
        planningDragActive = true;
        planningDropCompleted = false;
        ev.dataTransfer.setData("text/plain", card.getAttribute("data-card-id") || "");
        ev.dataTransfer.effectAllowed = "move";
      });
      card.addEventListener("dragend", () => {
        clearPlanningDragState();
        if(!flushPlanningDeferredRender() && !planningDropCompleted){
          renderPlanningBoard({ ...latestState, planning_board: planningBoard });
        }
        planningDropCompleted = false;
      });
    });
    document.querySelectorAll(".planning-dropzone").forEach(zone => {
      zone.addEventListener("scroll", () => {
        const lane = zone.getAttribute("data-lane") || "";
        if(lane) planningMachineDropScrollLeft[lane] = zone.scrollLeft || 0;
        if(zone.closest(".planning-machine-grid")) planningMachineScrollActiveUntil = Date.now() + 900;
      }, { passive: true });
      zone.addEventListener("dragover", ev => {
        ev.preventDefault();
        if(!zone.classList.contains("drag-over")) zone.classList.add("drag-over");
      });
      zone.addEventListener("dragleave", ev => {
        const rect = zone.getBoundingClientRect();
        const stillInside = ev.clientX >= rect.left && ev.clientX <= rect.right && ev.clientY >= rect.top && ev.clientY <= rect.bottom;
        if(stillInside || zone.contains(ev.relatedTarget)) return;
        zone.classList.remove("drag-over");
      });
      zone.addEventListener("drop", ev => {
        ev.preventDefault();
        zone.classList.remove("drag-over");
        const cardId = ev.dataTransfer.getData("text/plain");
        const lane = zone.getAttribute("data-lane") || "BACKLOG";
        planningDragActive = false;
        planningDropCompleted = true;
        if(findAndMovePlanningCard(cardId, lane)){
          renderPlanningBoard({ ...latestState, planning_board: planningBoard });
          schedulePlanningSave();
        }
        clearPlanningDragState();
      });
    });
    document.querySelectorAll(".planning-remove").forEach(btn => {
      btn.addEventListener("click", () => {
        const cardId = btn.getAttribute("data-card-id") || "";
        const lane = btn.getAttribute("data-lane") || "BACKLOG";
        planningBoard = normalizePlanningBoard(planningBoard);
        const removed = (planningBoard.lanes[lane] || []).find(c => String(c.id || "") === cardId);
        planningBoard.lanes[lane] = (planningBoard.lanes[lane] || []).filter(c => String(c.id || "") !== cardId);
        if(removed && String(removed.source || "") === "LOW STOCK"){
          const productId = String(removed.product_id || "").trim();
          const sku = String(removed.product_sku || removed.sku || "").trim();
          const exists = (lowStockItemsState || []).some(x =>
            (productId && String(x?.product_id || "").trim() === productId)
            || (sku && String(x?.sku || "").trim() === sku)
          );
          if(!exists){
            lowStockItemsState.unshift({
              product_id: productId,
              sku,
              name: removed.product_name || "",
              tonnage: removed.tonnage || "",
              total_stock: removed.low_stock_total ?? 0,
              unit: removed.low_stock_unit || "",
              qty_source: removed.low_stock_qty_source || "stock",
              threshold: removed.low_stock_threshold || "",
              warehouses: Array.isArray(removed.warehouses) ? removed.warehouses : [],
            });
          }
        }
        renderPlanningBoard({ ...latestState, planning_board: planningBoard });
        renderLowStockRecommendations(lowStockItemsState);
        schedulePlanningSave();
      });
    });
  }

  function schedulePlanningSave(){
    planningLocalDirty = true;
    if(planningSaveTimer) clearTimeout(planningSaveTimer);
    planningSaveTimer = setTimeout(savePlanningBoard, 350);
  }

  async function savePlanningBoard(){
    planningBoard = normalizePlanningBoard(planningBoard);
    const resp = await fetch("/api/planning/board", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ board: planningBoard }),
    });
    const out = await resp.json();
    if(out.ok && out.board){
      planningBoard = normalizePlanningBoard(out.board);
      planningLocalDirty = false;
      planningSetStatus("Planning board saved.");
    } else {
      planningSetStatus(out.error || "Failed to save planning board.", true);
    }
  }

  async function addPlanningJobFromInput(){
    const value = String(planningJobInput?.value || "").trim();
    if(!value){
      planningSetStatus("Scan or type a job/work order first.", true);
      return;
    }
    planningSetStatus("Getting job details from BMS...");
    try{
      const resp = await fetch("/api/planning/lookup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_identifier: value }),
      });
      const out = await resp.json();
      if(!out.ok || !out.item){
        planningSetStatus(out.error || "BMS lookup failed.", true);
        return;
      }
      planningBoard = normalizePlanningBoard(planningBoard);
      const card = out.item;
      card.id = `${card.id || "plan-job"}-${Date.now()}`;
      planningBoard.lanes.BACKLOG.unshift(card);
      if(planningJobInput) planningJobInput.value = "";
      renderPlanningBoard({ ...latestState, planning_board: planningBoard });
      schedulePlanningSave();
      planningSetStatus(`Added ${card.job_ref || card.job_id || value} to the top of the planning list.`);
    }catch(e){
      planningSetStatus(`Planning lookup failed: ${e}`, true);
    }
  }

  function setFinishedJobsInteractionLock(locked){
    finishedJobsInteractionLock = Boolean(locked);
    if(!finishedJobsInteractionLock && pendingFinishedJobsRows){
      const rows = pendingFinishedJobsRows;
      pendingFinishedJobsRows = null;
      renderFinishedJobs(rows);
    }
  }

  async function loadProducts(forceRefresh = false){
    const shouldRefresh = forceRefresh;
    const url = shouldRefresh ? "/api/products?refresh=1" : "/api/products";
    const res = await fetch(url, { method: "GET" });
    const data = await res.json();
    productItems = Array.isArray(data.items) ? data.items : [];
    productsHydrated = true;
    if(!productItems.length){
      overlayProductSuggest.innerHTML = "";
      overlayProductSuggest.classList.remove("active");
      overlayProductSelect.value = "";
      overlayProductSelect.placeholder = "No products available";
      return;
    }
    if(!overlayProductSelect.value){
      const first = productItems[0];
      overlayProductSelect.value = `${first.sku || ""} - ${first.name}`;
    }
  }

  function openApprovePrintOverlay(job){
    activeJobRow = job || null;
    overlayReviewSavedApproved = false;
    overlayReviewMode = isShiftPartialRecord(activeJobRow) ? "shift" : "job";
    if(overlayReviewSubmitBtn) overlayReviewSubmitBtn.textContent = overlayReviewMode === "shift" ? "Approve & Continue" : "Save Review";
    if(overlayReviewContinueBtn) overlayReviewContinueBtn.style.display = overlayReviewMode === "shift" ? "none" : "";
    const title = activeJobRow
      ? `${activeJobRow.job_name || activeJobRow.job_code || "Finished Job"} | ${activeJobRow.machine_name || activeJobRow.machine_code || "-"}`
      : "Finished Job";
    const key = jobKeyOf(activeJobRow);
    overlayJobInfo.value = title;
    if(overlayReviewJobInfo) overlayReviewJobInfo.value = title;
    if(overlayReviewJobInfoDisplay) overlayReviewJobInfoDisplay.textContent = title;
    const shiftPanels = overlayReviewMode === "shift" ? buildShiftPreviewPanels(activeJobRow) : null;
    if(overlayReviewSummary) overlayReviewSummary.value = shiftPanels ? shiftPanels.summary : reviewSummaryText(activeJobRow);
    if(overlayReviewRejects) overlayReviewRejects.value = shiftPanels ? shiftPanels.rejects : reviewRejectsText(activeJobRow);
    if(overlayReviewSummaryDisplay) overlayReviewSummaryDisplay.innerHTML = shiftPanels
      ? renderShiftGroupedPanelHtml(shiftPanels.summary, "No shift summary.")
      : renderSummaryMetricsHtml(activeJobRow);
    if(overlayReviewRejectsDisplay) overlayReviewRejectsDisplay.innerHTML = shiftPanels
      ? '<div class="machine-detail-empty">Use the next arrow for reject details.</div>'
      : renderBulletListHtml(reviewRejectsText(activeJobRow), "No reject details recorded.");
    if(overlayRejectDetailsPageDisplay) overlayRejectDetailsPageDisplay.innerHTML = shiftPanels
      ? renderShiftGroupedPanelHtml(shiftPanels.rejects, "No reject details recorded.")
      : renderBulletListHtml(reviewRejectsText(activeJobRow), "No reject details recorded.");
    const rawLogs = Array.isArray(activeJobRow?.raw_material_logs) ? activeJobRow.raw_material_logs : [];
    if(overlayRawConsumption) overlayRawConsumption.value = shiftPanels
      ? shiftPanels.rawConsumption
      : (rawLogs.length
        ? rawLogs.map((x, i) => `${i + 1}. ${(x?.material || x?.code || x?.value || "-")} | qty=${x?.qty ?? 0}`).join("\\n")
        : "No raw material consumption records.");
    if(overlayRawConsumptionDisplay) overlayRawConsumptionDisplay.innerHTML = shiftPanels
      ? renderShiftGroupedPanelHtml(shiftPanels.rawConsumption, "No raw material records.")
      : renderBulletListHtml(overlayRawConsumption?.value || "", "No raw material consumption records.");
    if(overlayRawCycleSummary) overlayRawCycleSummary.value = shiftPanels
      ? shiftPanels.rawCycle
      : [
        `Raw Materials / Sacks Count: ${activeJobRow?.raw_sacks_count ?? 0}`,
        `Cycle Count (Pack): ${activeJobRow?.pack_count ?? 0}`,
        `Cycle Time: ${activeJobRow?.cycle_time_current || "-"}`,
      ].join("\\n");
    if(overlayRawCycleSummaryDisplay) overlayRawCycleSummaryDisplay.innerHTML = shiftPanels
      ? renderShiftGroupedPanelHtml(shiftPanels.rawCycle, "No raw/cycle data.")
      : renderBulletListHtml(overlayRawCycleSummary?.value || "");
    if(overlayDowntimeSummary) overlayDowntimeSummary.value = shiftPanels
      ? shiftPanels.downtime
      : [
        `Reason: ${activeJobRow?.downtime_reason_code || "-"} ${activeJobRow?.downtime_reason_text || ""}`.trim(),
        `Downtime: ${fmtDowntimeSeconds(activeJobRow?.downtime_last_seconds)}`,
      ].join("\\n");
    if(overlayDowntimeSummaryDisplay) overlayDowntimeSummaryDisplay.innerHTML = shiftPanels
      ? renderShiftGroupedPanelHtml(shiftPanels.downtime, "No downtime data.")
      : renderBulletListHtml(overlayDowntimeSummary?.value || "");
    if(overlayPeopleSummary) overlayPeopleSummary.value = shiftPanels
      ? shiftPanels.people
      : [
        `Maintenance: ${activeJobRow?.maintenance_name || "-"}`,
        `Supervisor: ${activeJobRow?.supervisor_name || "-"}`,
        `QC: ${qcFromFinishedJob(activeJobRow)}`,
        `Start Up Reject: ${activeJobRow?.startup_reject_total ?? 0}`,
        `No Shot: ${activeJobRow?.no_shot_total ?? 0}`,
      ].join("\\n");
    if(overlayPeopleSummaryDisplay) overlayPeopleSummaryDisplay.innerHTML = shiftPanels
      ? renderShiftGroupedPanelHtml(shiftPanels.people, "No team data.")
      : renderBulletListHtml(overlayPeopleSummary?.value || "");
    if(overlayTransferPreviewDisplay) overlayTransferPreviewDisplay.innerHTML = renderTransferPreviewHtml(activeJobRow);
    if(overlayReviewerBadge) overlayReviewerBadge.value = "";
    if(overlayReviewerScanInput){
      overlayReviewerScanInput.value = "";
      overlayReviewerScanInput.style.display = "none";
    }
    if(overlayReviewRemarks) overlayReviewRemarks.value = "";
    fillDisapproveFields(activeJobRow);
    reviewSlideIndex = 0;
    syncReviewSubslides();
    setOverlayStep("review");
    generatedQrState = { jobKey: key, payload: "", qty: "", index: "", total: "", lotNumber: "", stageLabel: "", stageKind: "", plan: [], planIndex: 0, printRequests: [] };
    overlayQrPayload.value = "";
    overlayQty.value = "";
    overlayIndex.value = "";
    overlayTotal.value = "";
    overlayLotNumber.value = "";
    if(overlayQrStageLabel) overlayQrStageLabel.value = "2 / 2 - QR Print";
    if(overlayPoNumber){
      overlayPoNumber.value = "";
      overlayPoNumber.placeholder = "Enter PO Number...";
    }
    if(overlayPoNumberRow){
      overlayPoNumberRow.style.display = "none";
    }
    approvePrintOverlay.classList.add("active");
    if(productItems.length){
      renderProductSuggestions(overlayProductSelect.value || "");
    }
  }

  function closeApprovePrintOverlay(){
    approvePrintOverlay.classList.remove("active");
    activeJobRow = null;
    overlayReviewSavedApproved = false;
    overlayReviewMode = "job";
    reviewSlideIndex = 0;
    syncReviewSubslides();
    setOverlayStep("review");
  }

  function machineLinkageDisplay(s, code){
    const linkedRows = Array.isArray(s.linkage_jobs) ? s.linkage_jobs : [];
    const jobs = [
      {
        role: "Original Job",
        job_code: s.job_code || "",
        job_name: s.job_name || "",
      },
      ...linkedRows.map((row, idx) => ({
        role: `Linked Job ${idx + 1}`,
        job_code: (row && row.job_code) || "",
        job_name: (row && row.job_name) || "",
      })),
    ];
    const total = Math.max(1, jobs.length);
    if(!machineLinkageDisplayIndex.has(code)){
      return { jobs, index: 0, current: jobs[0], total };
    }
    const rawIndex = Number(machineLinkageDisplayIndex.get(code) || 0);
    const index = ((rawIndex % total) + total) % total;
    machineLinkageDisplayIndex.set(code, index);
    return { jobs, index, current: jobs[index], total };
  }

  function renderMachineCardNow(code, flipLinkage = false){
    const card = machineCardEls.get(code);
    const s = (latestState.sessions || []).find(x => String(x.machine_code || "").trim() === code);
    if(!card || !s) return;
    const activeTtlSeconds = Number((latestState && latestState.active_ttl_seconds) || 30);
    const manualStatus = machineStatusOverrideFor(code);
    const css = statusClass(s.last_seen_utc, activeTtlSeconds, manualStatus, s) || "disconnected";
    const statusLabel = manualStatus || css.toUpperCase();
    const baseClassName = `card ${css}`;
    const nextClassName = `${baseClassName}${flipLinkage ? " linkage-flip" : ""}`;
    const nextHtml = machineCardHtml(s, code, css, statusLabel, flipLinkage);
    card.className = baseClassName;
    card.innerHTML = nextHtml;
    if(flipLinkage){
      void card.offsetWidth;
      card.className = nextClassName;
    }
    card.dataset.renderSig = `${nextClassName}|${nextHtml}`;
  }

  function cycleMachineLinkageCard(code){
    const card = machineCardEls.get(code);
    const fresh = (latestState.sessions || []).find(x => String(x.machine_code || "").trim() === code);
    if(!card || !fresh) return;
    const linkedRows = Array.isArray(fresh.linkage_jobs) ? fresh.linkage_jobs : [];
    const total = 1 + linkedRows.length;
    if(total <= 1) return;

    const existingTimers = machineLinkageFlipTimers.get(code) || [];
    existingTimers.forEach(t => clearTimeout(t));
    card.classList.remove("linkage-flip-out", "linkage-flip-in");
    void card.offsetWidth;
    card.classList.add("linkage-flip-out");

    const swapTimer = setTimeout(() => {
      const current = machineLinkageDisplayIndex.has(code) ? Number(machineLinkageDisplayIndex.get(code) || 0) : -1;
      const next = (current + 1) % total;
      machineLinkageDisplayIndex.set(code, next);
      renderMachineCardNow(code, false);
      const nextCard = machineCardEls.get(code);
      if(!nextCard) return;
      nextCard.classList.remove("linkage-flip-out", "linkage-flip-in");
      void nextCard.offsetWidth;
      nextCard.classList.add("linkage-flip-in");

      const cleanupTimer = setTimeout(() => {
        const doneCard = machineCardEls.get(code);
        if(doneCard) doneCard.classList.remove("linkage-flip-out", "linkage-flip-in");
        machineLinkageFlipTimers.delete(code);
      }, 380);
      machineLinkageFlipTimers.set(code, [cleanupTimer]);
    }, 230);
    machineLinkageFlipTimers.set(code, [swapTimer]);
  }

  function machineCardHtml(s, code, css, statusLabel, flipLinkage = false){
    const linkageJobs = Array.isArray(s.linkage_jobs) ? s.linkage_jobs : [];
    const hasLinkage = Boolean(s.linkage_enabled) && linkageJobs.length > 0;
    const linkageDisplay = hasLinkage ? machineLinkageDisplay(s, code) : null;
    const displayedJob = linkageDisplay ? linkageDisplay.current : null;
    const total = Number(s.good_total||0) + Number(s.butal_total||0);
    const currentJobLabel = s.job_name
      ? (s.job_code ? `${s.job_name} (${s.job_code})` : s.job_name)
      : (s.job_code || "No Job Set");
    const jobLabel = displayedJob
      ? (displayedJob.job_name ? (displayedJob.job_code ? `${displayedJob.job_name} (${displayedJob.job_code})` : displayedJob.job_name) : (displayedJob.job_code || currentJobLabel))
      : currentJobLabel;
    const seenLabel = s.last_seen_utc ? new Date(s.last_seen_utc).toLocaleString() : "-";
    const statusText = statusLabel || css.toUpperCase();
    const operatorText = displayNameForId(s.operator_id || "-");
    const clientText = displayNameForId(s.client_id || "-");
    const supervisorTooltip = [
      "Supervisor QR pending",
      "Scan Supervisor QR on the client to continue downtime resolution.",
      s.cycle_time_new_input ? `New cycle: ${s.cycle_time_new_input}` : "",
    ].filter(Boolean).join("\\n");
    const supervisorNotif = s.waiting_supervisor_qr ? `
      <div class="machine-notif-wrap">
        <div class="machine-notif-badge" tabindex="0" title="${esc(supervisorTooltip)}">!</div>
      </div>
    ` : "";
    return `
      ${supervisorNotif}
      ${hasLinkage ? `
        <div class="machine-linkage-flag">
          <span>LINKED JOBS: ${esc(linkageJobs.length)}</span>
          <button class="machine-linkage-switch" type="button" data-machine-code="${esc(code)}">Switch</button>
        </div>
      ` : ""}
      <div class="machine-card-head">
        <div class="machine-card-title">
          <h3>${esc(s.machine_name || s.machine_code)}</h3>
        </div>
        <span class="machine-status-badge ${esc(css)}">${esc(statusText)}</span>
      </div>
      <div class="machine-job-block">
        <div class="machine-job-name">${esc(jobLabel)}</div>
        <div class="machine-job-meta">
          <span>Operator: <strong>${esc(operatorText)}</strong></span>
          <span>Client: <strong>${esc(clientText)}</strong></span>
        </div>
      </div>
      <div class="machine-metrics">
        <div class="machine-metric"><div class="k">Pack</div><div class="v">${esc(s.pack_total || 0)}</div></div>
        <div class="machine-metric good"><div class="k">Good</div><div class="v">${esc(s.good_total || 0)}</div></div>
        <div class="machine-metric"><div class="k">Butal</div><div class="v">${esc(s.butal_total || 0)}</div></div>
        <div class="machine-metric bad"><div class="k">Reject</div><div class="v">${esc(s.reject_total || 0)}</div></div>
        <div class="machine-metric"><div class="k">No Shot</div><div class="v">${esc(s.no_shot_total || 0)}</div></div>
        <div class="machine-metric good"><div class="k">Total</div><div class="v">${esc(total)}</div></div>
      </div>
      <div class="machine-card-foot">
        <div>Last seen: ${esc(seenLabel)}</div>
        <div>Last event: ${esc(s.last_event || "-")}</div>
      </div>
    `;
  }

  function upsertMachineCard(s, code, css, statusLabel){
    let card = machineCardEls.get(code);
    if(!card){
      card = document.createElement("div");
      card.dataset.machineCode = code;
      card.addEventListener("click", (ev) => {
        const switchBtn = ev.target && ev.target.closest ? ev.target.closest(".machine-linkage-switch") : null;
        if(switchBtn){
          ev.preventDefault();
          ev.stopPropagation();
          cycleMachineLinkageCard(code);
          return;
        }
        const fresh = (latestState.sessions || []).find(x => String(x.machine_code || "").trim() === code) || s;
        openMachineDetail(fresh);
      });
      machineCardEls.set(code, card);
    }
    const nextClassName = `card ${css}`;
    const nextHtml = machineCardHtml(s, code, css, statusLabel);
    const nextRenderSig = `${nextClassName}|${nextHtml}`;
    if(card.dataset.renderSig !== nextRenderSig){
      card.className = nextClassName;
      card.innerHTML = nextHtml;
      card.dataset.renderSig = nextRenderSig;
    }
    return card;
  }

  function render(state){
    if(planningDragActive || Date.now() < planningMachineScrollActiveUntil){
      planningDeferredState = state || null;
      return;
    }
    latestState = state || { sessions: [] };
    machineStatusOverridesState = (state && state.machine_status_overrides && typeof state.machine_status_overrides === "object") ? state.machine_status_overrides : {};
    machineStatusArchiveState = (state && Array.isArray(state.machine_status_archive)) ? state.machine_status_archive : [];
    timeEl.textContent = "Server UTC: " + (state.server_time_utc || "-");
    const sessions = state.sessions || [];
    const activeTtlSeconds = Number(state.active_ttl_seconds || 30);
    const byCode = Object.fromEntries(sessions.map(s => [String(s.machine_code || "").trim(), s]));
    const sessionCodes = sessions
      .map(s => String(s.machine_code || "").trim())
      .filter(Boolean);
    const allCodes = Array.from(new Set([...DEFAULT_MACHINE_CODES, ...sessionCodes])).sort();
    machineCountEl.textContent = String(allCodes.length);

    const desiredCodes = new Set(allCodes);
    for(const code of allCodes){
      const s = byCode[code] || {
        machine_code: code,
        machine_name: MACHINE_NAME_MAP[code] || code,
        job_code: "",
        job_name: "",
        operator_id: "",
        client_id: "",
        pack_total: 0,
        good_total: 0,
        butal_total: 0,
        reject_total: 0,
        no_shot_total: 0,
        last_event: "No data yet",
        last_seen_utc: "",
      };
      const manual = machineStatusOverrideFor(code);
      const manualStatus = String((manual && manual.status) || "").trim();
      const css = statusClass(s.last_seen_utc, activeTtlSeconds, manualStatus, s) || "disconnected";
      const statusLabel = manualStatus || css.toUpperCase();
      s.machine_name = s.machine_name || MACHINE_NAME_MAP[code] || code;
      const card = upsertMachineCard(s, code, css, statusLabel);
      if(card.parentNode !== machineGrid){
        machineGrid.appendChild(card);
      }
    }

    for(const [code, card] of machineCardEls.entries()){
      if(desiredCodes.has(code)) continue;
      if(card && card.parentNode) card.parentNode.removeChild(card);
      machineCardEls.delete(code);
    }
    renderJobQueue(state.job_queue || []);
    renderFinishedJobs(state.finished_jobs || []);
    renderArchivedJobs(state.archived_jobs || []);
    renderMachineStatusArchive(machineStatusArchiveState);
    renderDowntimeArchive(state.finished_jobs || [], state.archived_jobs || []);
    renderMaintenanceTab(state || {});
    renderPlanningOpsSummary(state || {}, state.job_queue || []);
    renderPlanningQueue(state.job_queue || []);
    renderPlanningBoard(state || {});
  }

  // tab handling
  document.querySelectorAll(".main-tab-button").forEach(btn => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-target");
      document.querySelectorAll(".main-tab-button").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".main-tab-content").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(target)?.classList.add("active");
    });
  });
  document.querySelectorAll(".sub-tab-button").forEach(btn => {
    btn.addEventListener("click", () => {
      const host = btn.closest(".panel");
      if(!host) return;
      const target = btn.getAttribute("data-target");
      host.querySelectorAll(".sub-tab-button").forEach(b => b.classList.remove("active"));
      host.querySelectorAll(".sub-tab-content").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      host.querySelector(`#${target}`)?.classList.add("active");
    });
  });

  if(planningLookupBtn){
    planningLookupBtn.addEventListener("click", () => addPlanningJobFromInput());
  }
  if(planningJobInput){
    planningJobInput.addEventListener("keydown", ev => {
      if(ev.key === "Enter") addPlanningJobFromInput();
    });
  }
  if(planningClearBtn){
    planningClearBtn.addEventListener("click", () => {
      if(!confirm("Clear all scanned/queued jobs from the planning list?")) return;
      planningBoard = normalizePlanningBoard(planningBoard);
      planningBoard.lanes.BACKLOG = [];
      renderPlanningBoard({ ...latestState, planning_board: planningBoard });
      schedulePlanningSave();
    });
  }
  if(planningLowStockRefreshBtn){
    planningLowStockRefreshBtn.addEventListener("click", () => loadLowStockRecommendations(true));
  }
  [planningLowStockSearch, planningLowStockMin, planningLowStockMax, planningLowStockLimit].forEach(el => {
    if(el) el.addEventListener("input", () => renderLowStockRecommendations(lowStockItemsState));
    if(el) el.addEventListener("change", () => renderLowStockRecommendations(lowStockItemsState));
  });

  if(serverSettingsBtn){
    serverSettingsBtn.addEventListener("click", async () => {
      await loadServerSettingsUi(false);
      await loadSettingsProfilesUi();
      showServerSettingsPage("general");
      serverSettingsOverlay?.classList.add("active");
    });
  }
  if(dailyRolesBtn){
    dailyRolesBtn.addEventListener("click", async () => {
      if(dailyRoleBadgeInput) dailyRoleBadgeInput.value = "";
      if(dailyRoleNameInput) dailyRoleNameInput.value = "";
      if(dailyRoleCompanyRoleInput) dailyRoleCompanyRoleInput.value = "";
      if(dailyRoleExtraPrivilegeSelect) dailyRoleExtraPrivilegeSelect.value = "none";
      if(dailyRoleEffectiveRightsInput) dailyRoleEffectiveRightsInput.value = "Viewer";
      await loadSettingsProfilesUi();
      await loadDailyRolesUi();
      dailyRolesOverlay?.classList.add("active");
      setTimeout(() => dailyRoleBadgeInput?.focus(), 0);
    });
  }
  if(operatorsDirectoryBtn){
    operatorsDirectoryBtn.addEventListener("click", async () => {
      operatorDirectoryOverlay?.classList.add("active");
      await loadOperatorDirectory();
    });
  }
  if(profileCreatorBtn){
    profileCreatorBtn.addEventListener("click", async () => {
      const pw = window.prompt("Admin password required to open Profile Creation:", "");
      if(pw === null) return;
      try{
        const r = await fetch('/api/profiles/authorize-open', {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ admin_password: pw })
        });
        const j = await r.json().catch(() => ({}));
        if(!r.ok || !j.ok){
          alert(j.error || 'Invalid admin password');
          return;
        }
        window.open("/profiles", "_blank");
      }catch(err){
        alert(`Failed to authorize profile creation: ${err}`);
      }
    });
  }
  if(operatorDirectoryCloseBtn) operatorDirectoryCloseBtn.addEventListener("click", () => operatorDirectoryOverlay?.classList.remove("active"));
  if(operatorDirectoryOverlay){
    operatorDirectoryOverlay.addEventListener("click", (ev) => {
      if(ev.target === operatorDirectoryOverlay) operatorDirectoryOverlay.classList.remove("active");
    });
  }
  if(operatorDirectoryGrid){
    operatorDirectoryGrid.addEventListener("click", (ev) => {
      const row = ev.target && ev.target.closest ? ev.target.closest("[data-operator-index]") : null;
      if(!row) return;
      const idx = Number(row.getAttribute("data-operator-index") || "-1");
      if(idx >= 0) openOperatorDetail(idx);
    });
  }
  if(operatorDetailCloseBtn) operatorDetailCloseBtn.addEventListener("click", () => operatorDetailOverlay?.classList.remove("active"));
  if(operatorDetailOverlay){
    operatorDetailOverlay.addEventListener("click", (ev) => {
      if(ev.target === operatorDetailOverlay) operatorDetailOverlay.classList.remove("active");
    });
  }
  if(dailyRolesCloseBtn) dailyRolesCloseBtn.addEventListener("click", () => dailyRolesOverlay?.classList.remove("active"));
  if(dailyRolesOverlay){
    dailyRolesOverlay.addEventListener("click", (ev) => {
      if(ev.target === dailyRolesOverlay) dailyRolesOverlay.classList.remove("active");
    });
  }
  if(dailyRoleBadgeInput){
    dailyRoleBadgeInput.addEventListener("keydown", (ev) => {
      if(ev.key !== "Enter") return;
      ev.preventDefault();
      const badge = (dailyRoleBadgeInput.value || "").trim();
      if(!badge) return;
      const profile = findSettingsProfileById(badge);
      const known = (profile && profile.name) || knownPersonNameFromBadge(badge);
      if(known && dailyRoleNameInput && !dailyRoleNameInput.value.trim()){
        dailyRoleNameInput.value = known;
      }
      refreshDailyRoleDerivedUi();
      dailyRoleExtraPrivilegeSelect?.focus();
    });
    dailyRoleBadgeInput.addEventListener("input", () => {
      if(dailyRoleNameInput) dailyRoleNameInput.value = "";
      refreshDailyRoleDerivedUi();
    });
  }
  dailyRoleExtraPrivilegeSelect?.addEventListener("change", refreshDailyRoleDerivedUi);
  dailyRolesSaveBtn?.addEventListener("click", saveDailyRoleUi);
  if(serverSettingsCloseBtn) serverSettingsCloseBtn.addEventListener("click", () => serverSettingsOverlay?.classList.remove("active"));
  if(serverSettingsOverlay){
    serverSettingsOverlay.addEventListener("click", (ev) => {
      if(ev.target === serverSettingsOverlay) serverSettingsOverlay.classList.remove("active");
    });
  }
  settingsNavGeneral?.addEventListener("click", () => showServerSettingsPage("general"));
  settingsNavTheme?.addEventListener("click", () => showServerSettingsPage("theme"));
  settingsNavApi?.addEventListener("click", () => showServerSettingsPage("api"));
  settingsNavProfile?.addEventListener("click", async () => { await loadSettingsProfilesUi(); showServerSettingsPage("profile"); });
  settingsThemeSelect?.addEventListener("change", () => applyDashboardTheme(settingsThemeSelect.value));
  serverSettingsSaveBtn?.addEventListener("click", saveServerSettingsUi);
  settingsProductsRefreshBtn?.addEventListener("click", async () => {
    await loadProductsSettingsInfo(true);
  });

  finishedJobsList.addEventListener("click", async (ev) => {
    const btn = ev.target.closest(".approve-print-btn");
    if(!btn) return;
    setFinishedJobsInteractionLock(true);
    const idx = Number(btn.getAttribute("data-row-index"));
    if(Number.isNaN(idx) || idx < 0) return;
    const sorted = [...(finishedJobsState || [])].reverse();
    const row = sorted[idx];
    if(!row) return;
    openApprovePrintOverlay(row);
    if(!productItems.length){
      loadProducts(false);
    }
    setTimeout(() => setFinishedJobsInteractionLock(false), 0);
  });
  finishedShiftQueueList?.addEventListener("click", async (ev) => {
    const btn = ev.target.closest(".shift-review-btn");
    if(!btn) return;
    const idx = Number(btn.getAttribute("data-row-index"));
    if(Number.isNaN(idx) || idx < 0) return;
    const sorted = [...(finishedShiftState || [])].reverse();
    const row = sorted[idx];
    if(!row) return;
    openApprovePrintOverlay(row);
    setOverlayStep("review");
    if(overlayReviewContinueBtn) overlayReviewContinueBtn.style.display = "none";
    if(overlayReviewSubmitBtn) overlayReviewSubmitBtn.textContent = isApprovedShiftRecord(row) ? "Save Changes" : "Approve & Continue";
  });
  finishedJobsList.addEventListener("mouseover", (ev) => {
    if(ev.target.closest(".approve-print-btn")) setFinishedJobsInteractionLock(true);
  });
  finishedJobsList.addEventListener("mouseout", (ev) => {
    const btn = ev.target.closest(".approve-print-btn");
    if(!btn) return;
    const nextEl = ev.relatedTarget instanceof Element ? ev.relatedTarget : null;
    if(nextEl && btn.contains(nextEl)) return;
    setFinishedJobsInteractionLock(false);
  });
  finishedJobsList.addEventListener("mousedown", (ev) => {
    if(ev.target.closest(".approve-print-btn")) setFinishedJobsInteractionLock(true);
  });
  archivedJobsTableWrap?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".archived-view-btn");
    if(!btn) return;
    const idx = Number(btn.getAttribute("data-row-index"));
    if(Number.isNaN(idx) || idx < 0) return;
    const sorted = [...(archivedJobsState || [])].reverse();
    const row = sorted[idx];
    if(!row) return;
    openMachineDetail(archivedRowToMachineSessionLike(row));
  });

  overlayCloseBtn.addEventListener("click", closeApprovePrintOverlay);
  overlayCancelBtn.addEventListener("click", closeApprovePrintOverlay);
  if(overlayOpenScanFieldBtn && overlayReviewerScanInput){
    overlayOpenScanFieldBtn.addEventListener("click", () => {
      openQrScanCaptureOverlay();
    });
  }
  if(qrScanCaptureCancelBtn) qrScanCaptureCancelBtn.addEventListener("click", closeQrScanCaptureOverlay);
  if(qrScanCaptureOverlay){
    qrScanCaptureOverlay.addEventListener("click", (ev) => {
      if(ev.target === qrScanCaptureOverlay) closeQrScanCaptureOverlay();
    });
  }
  if(qrScanCaptureInput){
    qrScanCaptureInput.addEventListener("keydown", (ev) => {
      if(ev.key !== "Enter") return;
      ev.preventDefault();
      const scanned = (qrScanCaptureInput.value || "").trim();
      if(!scanned) return;
      if(overlayReviewerBadge) overlayReviewerBadge.value = scanned;
      closeQrScanCaptureOverlay();
      if(overlayReviewRemarks) overlayReviewRemarks.focus();
    });
  }
  if(overlayBackToReviewBtn) overlayBackToReviewBtn.addEventListener("click", () => setOverlayStep("review"));
  if(overlayReviewPrevBtn) overlayReviewPrevBtn.addEventListener("click", () => {
    reviewSlideIndex = Math.max(0, Number(reviewSlideIndex || 0) - 1);
    syncReviewSubslides();
  });
  if(overlayReviewNextBtn) overlayReviewNextBtn.addEventListener("click", () => {
    reviewSlideIndex = Number(reviewSlideIndex || 0) + 1;
    syncReviewSubslides();
  });
  machineDetailCloseBtn.addEventListener("click", closeMachineDetail);
  machineDetailSettingsBtn?.addEventListener("click", () => {
    if(!machineDetailStatusPanel) return;
    machineDetailStatusPanel.style.display = (machineDetailStatusPanel.style.display === "none") ? "" : "none";
  });
  machineDetailStatusSaveBtn?.addEventListener("click", async () => {
    const machineCode = String(activeMachineDetailCode || "").trim();
    if(!machineCode) return;
    const status = String(machineDetailStatusSelect?.value || "").trim();
    const isClearLikeStatus = (status === "" || status === "Working");
    const reason = String(machineDetailStatusReason?.value || "").trim();
    const setterBadge = String(machineDetailStatusSetterBadge?.value || "").trim();
    if(!isClearLikeStatus && !reason){
      alert("Reason is required before confirming machine status.");
      machineDetailStatusReason?.focus();
      return;
    }
    if(!setterBadge){
      alert("Scan user QR first before confirming machine status.");
      machineDetailStatusSetterBadge?.focus();
      return;
    }
    if(machineDetailStatusSaveBtn) machineDetailStatusSaveBtn.disabled = true;
    if(machineStatusSaveFeedback) machineStatusSaveFeedback.classList.add("active");
    if(machineStatusSaveBar) machineStatusSaveBar.style.width = "8%";
    if(machineStatusSaveCheck) machineStatusSaveCheck.classList.remove("done");
    let progress = 8;
    const anim = window.setInterval(() => {
      progress = Math.min(92, progress + 11);
      if(machineStatusSaveBar) machineStatusSaveBar.style.width = `${progress}%`;
    }, 70);
    try{
      const r = await fetch('/api/machines/status', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ machine_code: machineCode, status, reason, setter_badge: setterBadge })
      });
      const j = await r.json().catch(() => ({}));
      window.clearInterval(anim);
      if(!r.ok || !j.ok){
        if(machineStatusSaveFeedback) machineStatusSaveFeedback.classList.remove("active");
        if(machineStatusSaveBar) machineStatusSaveBar.style.width = "0%";
        alert(j.error || "Failed to save machine status");
        if(machineDetailStatusSaveBtn) machineDetailStatusSaveBtn.disabled = false;
        return;
      }
      if(machineStatusSaveBar) machineStatusSaveBar.style.width = "100%";
      if(machineStatusSaveCheck) machineStatusSaveCheck.classList.add("done");
      const savedStatusLabel = (status === "Working") ? "Working (Live Status)" : (status || "Auto (Live Status)");
      if(lastMessageEl) lastMessageEl.textContent = `Machine status updated: ${machineCode} -> ${savedStatusLabel} by ${j?.actor?.name || setterBadge}`;
      setTimeout(() => {
        if(machineDetailStatusPanel) machineDetailStatusPanel.style.display = "none";
        if(machineStatusSaveFeedback) machineStatusSaveFeedback.classList.remove("active");
        if(machineStatusSaveBar) machineStatusSaveBar.style.width = "0%";
        if(machineStatusSaveCheck) machineStatusSaveCheck.classList.remove("done");
        if(machineDetailStatusSetterBadge) machineDetailStatusSetterBadge.value = "";
      }, 650);
    }catch(err){
      window.clearInterval(anim);
      if(machineStatusSaveFeedback) machineStatusSaveFeedback.classList.remove("active");
      if(machineStatusSaveBar) machineStatusSaveBar.style.width = "0%";
      alert(`Failed to save machine status: ${err}`);
    } finally {
      if(machineDetailStatusSaveBtn) machineDetailStatusSaveBtn.disabled = false;
    }
  });
  approvePrintOverlay.addEventListener("click", (_ev) => {
    // Keep the review/print popup open unless user uses explicit Close/Cancel buttons.
  });
  machineDetailOverlay.addEventListener("click", (ev) => {
    if(ev.target === machineDetailOverlay) closeMachineDetail();
  });

  overlayProductSelect.addEventListener("focus", () => {
    if(productItems.length){
      renderProductSuggestions(overlayProductSelect.value || "");
    }
  });

  overlayProductSelect.addEventListener("input", () => {
    renderProductSuggestions(overlayProductSelect.value || "");
  });
  overlayPoNumber?.addEventListener("input", () => {
    if(generatedQrState.stageKind === "BUTAL"){
      const po = (overlayPoNumber.value || "").trim();
      if(!po){
        overlayQrPayload.value = "Enter PO Number for Butal.";
        return;
      }
      refreshQrStagePayload().catch(() => {});
    }
  });

  overlayProductSelect.addEventListener("keydown", (ev) => {
    if(!overlayProductSuggest.classList.contains("active")){
      if(ev.key === "Escape"){
        ev.stopPropagation();
      }
      return;
    }
    if(ev.key === "ArrowDown"){
      ev.preventDefault();
      productSuggestionIndex = Math.min(productSuggestionItems.length - 1, productSuggestionIndex + 1);
    } else if(ev.key === "ArrowUp"){
      ev.preventDefault();
      productSuggestionIndex = Math.max(0, productSuggestionIndex - 1);
    } else if(ev.key === "Enter"){
      if(productSuggestionIndex >= 0){
        ev.preventDefault();
        pickProductSuggestion(productSuggestionIndex);
      }
      return;
    } else if(ev.key === "Escape"){
      ev.preventDefault();
      ev.stopPropagation();
      overlayProductSuggest.classList.remove("active");
      return;
    } else {
      return;
    }
    Array.from(overlayProductSuggest.querySelectorAll(".overlay-suggest-item")).forEach((el, idx) => {
      el.classList.toggle("active", idx === productSuggestionIndex);
    });
  });

  overlayProductSuggest.addEventListener("mousedown", (ev) => {
    const btn = ev.target.closest(".overlay-suggest-item");
    if(!btn) return;
    ev.preventDefault();
    const idx = Number(btn.getAttribute("data-idx"));
    if(!Number.isNaN(idx)){
      pickProductSuggestion(idx);
    }
  });

  document.addEventListener("mousedown", (ev) => {
    if(!approvePrintOverlay.classList.contains("active")) return;
    if(ev.target === overlayProductSelect) return;
    if(overlayProductSuggest.contains(ev.target)) return;
    overlayProductSuggest.classList.remove("active");
  });

  overlayGenerateBtn.addEventListener("click", async () => {
    await refreshQrStagePayload();
  });

  overlayRequestBtn.addEventListener("click", async () => {
    if(!overlayReviewSavedApproved){
      overlayQrPayload.value = "Review approval is required before requesting print.";
      return;
    }
    const product = resolveProductFromText(overlayProductSelect.value || "") || (
      (generatedQrState.productName || generatedQrState.productSku || generatedQrState.productId)
        ? {
            id: generatedQrState.productId || "",
            sku: generatedQrState.productSku || "",
            name: generatedQrState.productName || generatedQrState.productId || "Selected product",
          }
        : null
    );
    if(!product){
      overlayQrPayload.value = "Select a product first.";
      return;
    }
    const quantity = (overlayQty.value || "").trim();
    const total = (overlayTotal.value || "").trim();
    const poNumber = (overlayPoNumber.value || "").trim();
    const lotNumber = (overlayLotNumber.value || "").trim();
    const stageNeedsPo = generatedQrState.stageKind === "BUTAL";
    if(!quantity || !total || !lotNumber || (stageNeedsPo && !poNumber)){
      overlayQrPayload.value = stageNeedsPo
        ? "Generate QR first so Quantity/Total/Lot/PO are complete."
        : "Generate QR first so Quantity/Total/Lot are complete.";
      return;
    }

    const productSku = (product.sku || "").toString().trim();
    const productDisplayName = (product.name || "").toString().trim();
    const productName = productSku ? `[${productSku}] ${productDisplayName}`.trim() : (productDisplayName || String(product.id || ""));
    const requestPayload = {
      product_name: productName,
      quantity: quantity,
      total: total,
      po_number: poNumber,
      product_desc: (activeJobRow && (activeJobRow.job_name || activeJobRow.job_code)) || "",
      requested_at_ph: "",
      lot_number: lotNumber,
      qr_stage_label: generatedQrState.stageLabel || "",
    };

    const resp = await fetch("/api/qrgen/pending-request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestPayload),
    });
    const out = await resp.json();
    if(out.ok){
      generatedQrState.printRequests = [...(generatedQrState.printRequests || []), requestPayload];
      const hasNext = Array.isArray(generatedQrState.plan) && generatedQrState.planIndex < (generatedQrState.plan.length - 1);
      if(hasNext){
        generatedQrState.planIndex += 1;
        applyGeneratedQrPlanEntry(generatedQrState.plan[generatedQrState.planIndex]);
        if(generatedQrState.stageKind === "BUTAL"){
          overlayQrPayload.value = "Enter PO Number for Butal.";
        } else {
          overlayQrPayload.value = `${overlayQrPayload.value}\n\nPrint request sent. Next QR stage loaded.`;
        }
        return;
      }
      overlayQrPayload.value = `${overlayQrPayload.value}\n\nPrint request sent. Shift finished.`;
      try {
        const archiveResp = await fetch("/api/finished-jobs/archive", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            job_key: jobKeyOf(activeJobRow),
            qr_payload: overlayQrPayload.value || "",
            print_payload: requestPayload,
            print_payloads: generatedQrState.printRequests || [],
          }),
        });
        const archiveOut = await archiveResp.json();
        if(archiveOut.ok){
          activeJobRow = archiveOut.item || activeJobRow;
          overlayQrPayload.value = `${overlayQrPayload.value}\nArchived to Archived Jobs.`;
          setTimeout(() => {
            closeApprovePrintOverlay();
          }, 450);
        } else {
          overlayQrPayload.value = `${overlayQrPayload.value}\nArchive warning: ${archiveOut.error || "Failed to archive."}`;
        }
      } catch (e) {
        overlayQrPayload.value = `${overlayQrPayload.value}\nArchive warning: ${e}`;
      }
    } else {
      const apiMsg = out?.target_base_url
        ? `QR generator API is not available. ${out.error || "Request failed."}`
        : (out.error || "Print request failed.");
      overlayQrPayload.value = apiMsg;
    }
  });

  async function submitFinishedJobReview(actionMode){
    if(!activeJobRow) return;
    const reviewerBadge = (overlayReviewerBadge.value || "").trim();
    const remarks = (overlayReviewRemarks.value || "").trim();
    const shiftNeedsPrint = overlayReviewMode === "shift" && !isApprovedShiftRecord(activeJobRow);
    const action = overlayReviewMode === "shift"
      ? (shiftNeedsPrint ? "approve" : "update")
      : (actionMode === "continue" ? "approve" : "disapprove");
    if(!reviewerBadge){
      overlayReviewRemarks.value = remarks;
      alert("Reviewer QR / badge is required.");
      return;
    }
    if(!remarks){
      alert("Remarks are required.");
      return;
    }
    let rejectBreakdown = {};
    try {
      rejectBreakdown = JSON.parse((editRejectBreakdown.value || "{}").trim() || "{}");
    } catch {
      alert("Reject Details JSON is invalid.");
      return;
    }
    const changes = {
      pack_count: Number(editPackCount.value || 0),
      good_total: Number(editGoodTotal.value || 0),
      butal_total: Number(editButalTotal.value || 0),
      reject_total: Number(editRejectTotal.value || 0),
      total_good: Number(editTotalGood.value || 0),
      reject_breakdown: rejectBreakdown,
    };
    const resp = await fetch("/api/finished-jobs/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_key: jobKeyOf(activeJobRow),
        action,
        remarks,
        reviewer_badge: reviewerBadge,
        changes,
      }),
    });
    const out = await resp.json();
    if(!out.ok){
      alert(out.error || "Failed to save review.");
      return;
    }
    activeJobRow = out.item || activeJobRow;
    overlayReviewJobInfo.value = `${activeJobRow.job_name || activeJobRow.job_code || "Finished Job"} | ${activeJobRow.machine_name || activeJobRow.machine_code || "-"}`;
    if(overlayReviewJobInfoDisplay) overlayReviewJobInfoDisplay.textContent = overlayReviewJobInfo.value;
    const shiftPanels = overlayReviewMode === "shift" ? buildShiftPreviewPanels(activeJobRow) : null;
    overlayReviewSummary.value = shiftPanels ? safeJsonPretty(shiftPanels.summary) : reviewSummaryText(activeJobRow) + `\\n\\nStatus: ${activeJobRow.review_status || "-"}`;
    overlayReviewRejects.value = shiftPanels ? safeJsonPretty(shiftPanels.rejects) : reviewRejectsText(activeJobRow);
    if(overlayReviewSummaryDisplay) overlayReviewSummaryDisplay.innerHTML = shiftPanels
      ? renderShiftGroupedPanelHtml(shiftPanels.summary, "No shift summary.")
      : renderSummaryMetricsHtml(activeJobRow);
    if(overlayReviewRejectsDisplay) overlayReviewRejectsDisplay.innerHTML = shiftPanels
      ? '<div class="machine-detail-empty">Use the next arrow for reject details.</div>'
      : renderBulletListHtml(overlayReviewRejects.value || "", "No reject details recorded.");
    if(overlayRejectDetailsPageDisplay) overlayRejectDetailsPageDisplay.innerHTML = shiftPanels
      ? renderShiftGroupedPanelHtml(shiftPanels.rejects, "No reject details recorded.")
      : renderBulletListHtml(overlayReviewRejects.value || "", "No reject details recorded.");
    if(overlayTransferPreviewDisplay) overlayTransferPreviewDisplay.innerHTML = renderTransferPreviewHtml(activeJobRow);
    fillDisapproveFields(activeJobRow);
    if(Array.isArray(latestState.finished_jobs)){
      const k = jobKeyOf(activeJobRow);
      latestState.finished_jobs = latestState.finished_jobs.map(x => jobKeyOf(x) === k ? activeJobRow : x);
      renderFinishedJobs(latestState.finished_jobs);
    }
    if(actionMode === "continue" || shiftNeedsPrint){
      overlayReviewSavedApproved = true;
      setOverlayStep("qr");
      generatedQrState = { jobKey: jobKeyOf(activeJobRow), payload: "", qty: "", index: "", total: "", lotNumber: "", stageLabel: "", stageKind: "", plan: [], planIndex: 0, printRequests: [] };
      if(overlayPoNumber){
        overlayPoNumber.value = "";
      }
      if(overlayPoNumberRow){
        overlayPoNumberRow.style.display = "none";
      }
      setTimeout(() => { refreshQrStagePayload().catch(() => {}); }, 0);
    } else {
      overlayReviewSavedApproved = action === "approve";
      if(action === "approve"){
        alert("Approved and saved. You can now continue to QR.");
      } else if(action === "update"){
        alert("Shift review changes saved.");
      } else {
        alert("Disapproved changes saved. Review again and approve to continue to QR.");
      }
    }
  }

  overlayReviewSubmitBtn.addEventListener("click", () => submitFinishedJobReview("save"));
  overlayReviewContinueBtn.addEventListener("click", () => submitFinishedJobReview("continue"));

  const wsProto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${wsProto}://${location.host}/ws`);

  ws.onopen = () => { clientStatus.innerHTML = '<span class="status-dot connected"></span>Connected'; };
  ws.onclose = () => { clientStatus.innerHTML = '<span class="status-dot disconnected"></span>Disconnected'; };
  ws.onerror = () => { clientStatus.innerHTML = '<span class="status-dot disconnected"></span>Error'; };

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    lastMessageEl.textContent = "STATE";
    if(msg.type === "STATE") render(msg);
  };

  // Apply saved dashboard theme/settings immediately on page load.
  loadServerSettingsUi(true).catch(() => {});

  // Warm product cache on page load so overlay opens fast.
  loadProducts(false).then(() => {
    // Optional background refresh; does not block UI.
    loadProducts(true).catch(() => {});
  }).catch(() => {});
</script>
</body>
</html>
"""


@APP.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(DASHBOARD_HTML)


PROFILE_CREATOR_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Profile QR Creator</title>
  <style>
    body { margin: 0; font-family: Poppins, Segoe UI, sans-serif; background: #eef2f7 url('/Images/bgbg.png') center / cover fixed no-repeat; color: #1f2937; }
    .wrap { max-width: 980px; margin: 22px auto; padding: 0 14px; }
    .card { background: rgba(255,255,255,.96); border: 1px solid #dbe4f0; border-radius: 16px; box-shadow: 0 20px 48px rgba(15,23,42,.18), 0 6px 16px rgba(15,23,42,.10); overflow: hidden; }
    .head { padding: 16px 18px; border-bottom: 1px solid #e5e7eb; font-weight: 800; font-size: 1.05rem; }
    .body { padding: 16px 18px; display: grid; grid-template-columns: 1fr 380px; gap: 16px; }
    .form { display: grid; gap: 10px; }
    .row { display: grid; gap: 6px; }
    label { font-size: .86rem; font-weight: 700; color: #475569; }
    input, select { border: 1px solid #cbd5e1; border-radius: 10px; padding: 10px 12px; font: inherit; background: rgba(255,255,255,.98); box-shadow: 0 10px 22px rgba(15,23,42,.18), 0 2px 6px rgba(15,23,42,.08), inset 0 1px 0 rgba(255,255,255,.75); }
    input:focus, select:focus { outline: none; border-color: #60a5fa; box-shadow: 0 0 0 4px rgba(59,130,246,.22), 0 14px 28px rgba(15,23,42,.20); }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 6px; }
    button { border: none; border-radius: 12px; padding: 10px 14px; cursor: pointer; font-weight: 600; transition: transform .12s ease, box-shadow .16s ease; }
    button:hover { transform: translateY(-1px); box-shadow: 0 8px 18px rgba(15,23,42,.10); }
    button:active { transform: translateY(0) scale(.985); }
    .primary { background: #1d4ed8; color: #fff; }
    .secondary { background: #fff; color: #1f2937; border: 1px solid #cbd5e1; }
    .preview { border: 1px solid #dbe4f0; border-radius: 14px; background: rgba(248,250,252,.95); padding: 12px; box-shadow: 0 14px 30px rgba(15,23,42,.14), inset 0 1px 0 rgba(255,255,255,.7); }
    .preview h4 { margin: 0 0 8px; }
    .preview img { width: 100%; height: auto; border: 1px solid #dbe4f0; border-radius: 10px; background: #fff; }
    .mono { font-family: Consolas, monospace; font-size: .75rem; white-space: pre-wrap; word-break: break-all; margin-top: 8px; background:#fff; border:1px solid #e5e7eb; border-radius:10px; padding:8px; }
    .status { font-size: .85rem; color: #334155; min-height: 20px; }
    .table { margin-top: 14px; border: 1px solid #dbe4f0; border-radius: 12px; overflow: auto; background: rgba(255,255,255,.96); box-shadow: 0 18px 38px rgba(15,23,42,.15), 0 4px 12px rgba(15,23,42,.08); }
    table { width: 100%; border-collapse: collapse; min-width: 720px; }
    th, td { border-bottom: 1px solid #edf2f7; padding: 8px 10px; text-align: left; font-size: .84rem; }
    th { background: #f8fafc; }
    .mini-btn { border: 1px solid #cbd5e1; background: #fff; color: #1f2937; border-radius: 10px; padding: 6px 9px; font-size: .78rem; font-weight: 600; cursor:pointer; }
    .mini-btn.primary { background: #1d4ed8; color: #fff; border-color: #1d4ed8; }
    .mini-btn.danger { background: #fff1f2; color: #be123c; border-color: #fecdd3; }
    .mini-actions { display:flex; gap:6px; flex-wrap:wrap; }
    body[data-theme="Soft Gray"] { background: #eef1f4 url('/Images/bgbg.png') center / cover fixed no-repeat; color: #243041; }
    body[data-theme="Soft Gray"] .card, body[data-theme="Soft Gray"] .table { background: rgba(248,250,252,.96); border-color: #dbe2eb; }
    body[data-theme="Soft Gray"] .head { border-bottom-color: #dbe2eb; color: #334155; }
    body[data-theme="Soft Gray"] label { color: #475569; }
    body[data-theme="Soft Gray"] input, body[data-theme="Soft Gray"] select { border-color: #dbe2eb; color: #334155; }
    body[data-theme="Soft Gray"] .preview { border-color: #dbe2eb; background: rgba(248,250,252,.95); }
    body[data-theme="Soft Gray"] th { background: #f8fafc; color: #475569; }
    body[data-theme="Dark"] { background: #0b1220 url('/Images/bgbg.png') center / cover fixed no-repeat; color: #e5e7eb; }
    body[data-theme="Dark"] .card, body[data-theme="Dark"] .table { background: rgba(15,23,42,.96); border-color: #334155; box-shadow: 0 20px 48px rgba(0,0,0,.40), 0 6px 16px rgba(0,0,0,.25); }
    body[data-theme="Dark"] .head { border-bottom-color: #334155; color: #e5e7eb; }
    body[data-theme="Dark"] label { color: #cbd5e1; }
    body[data-theme="Dark"] input, body[data-theme="Dark"] select { background: rgba(17,24,39,.96); border-color: #334155; color: #e5e7eb; box-shadow: 0 10px 22px rgba(0,0,0,.28), 0 2px 6px rgba(0,0,0,.18), inset 0 1px 0 rgba(255,255,255,.03); }
    body[data-theme="Dark"] input:focus, body[data-theme="Dark"] select:focus { border-color: #60a5fa; box-shadow: 0 0 0 4px rgba(59,130,246,.22), 0 14px 28px rgba(0,0,0,.30); }
    body[data-theme="Dark"] .secondary { background: #111827; color: #e5e7eb; border-color: #334155; }
    body[data-theme="Dark"] .primary { background: #2563eb; }
    body[data-theme="Dark"] .preview { border-color: #334155; background: rgba(17,24,39,.92); }
    body[data-theme="Dark"] .preview h4, body[data-theme="Dark"] .status { color: #e5e7eb; }
    body[data-theme="Dark"] .preview img, body[data-theme="Dark"] .mono { background: #0f172a; border-color: #334155; color: #cbd5e1; }
    body[data-theme="Dark"] th { background: #1f2937; color: #cbd5e1; }
    body[data-theme="Dark"] td { border-bottom-color: #253041; color: #e5e7eb; }
    body[data-theme="Dark"] .mini-btn { background: #111827; color: #e5e7eb; border-color: #334155; }
    body[data-theme="Dark"] .mini-btn.primary { background: #1d4ed8; border-color: #3b82f6; }
    body[data-theme="Dark"] .mini-btn.danger { background: rgba(127,29,29,.22); color: #fecdd3; border-color: #7f1d1d; }
    body[data-theme="Red"] { background: #fff4f4 url('/Images/bgbg.png') center / cover fixed no-repeat; color: #7f1d1d; }
    body[data-theme="Red"] .card, body[data-theme="Red"] .table { background: rgba(255,255,255,.96); border-color: #fecaca; }
    body[data-theme="Red"] .head { border-bottom-color: #fecaca; color: #7f1d1d; }
    body[data-theme="Red"] label { color: #991b1b; }
    body[data-theme="Red"] input, body[data-theme="Red"] select { border-color: #fecaca; color: #7f1d1d; }
    body[data-theme="Red"] .preview { border-color: #fecaca; background: rgba(255,247,247,.95); }
    body[data-theme="Red"] th { background: #fef2f2; color: #991b1b; }
    body[data-theme="Red"] td { border-bottom-color: #fee2e2; color: #7f1d1d; }
    body[data-theme="Red"] .secondary { border-color: #fecaca; color: #7f1d1d; }
    body[data-theme="Red"] .primary { background: #dc2626; }
    @media (max-width: 900px) { .body { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="head">Profile Creation / QR Generator</div>
      <div class="body">
        <div>
          <div class="form">
            <div class="row"><label>Name</label><input id="pfName" type="text" /></div>
            <div class="row"><label>ID Number</label><input id="pfId" type="text" /></div>
            <div class="row"><label>Company Role</label>
              <select id="pfRole">
                <option>Supervisor</option>
                <option>QA/QC</option>
                <option>Operator</option>
                <option>Maintenance</option>
                <option>Planner</option>
                <option>Production Manager</option>
              </select>
            </div>
            <div class="row"><label>Print Size</label>
              <select id="pfSize">
                <option value="barcode_4x1.25">Barcode Printer (4 x 1.25 split by 3)</option>
                <option value="normal_2x2">Normal Printer (2 x 2)</option>
              </select>
            </div>
            <div class="actions">
              <button id="pfPreviewBtn" class="secondary" type="button">Preview QR</button>
              <button id="pfSaveBtn" class="primary" type="button">Save Profile</button>
              <button id="pfSavePrintBtn" class="primary" type="button">Save Profile and Print QR</button>
            </div>
            <div id="pfStatus" class="status"></div>
          </div>
        </div>
        <div class="preview">
          <h4>QR Preview</h4>
          <img id="pfPreviewImg" alt="QR preview" />
          <div id="pfPayloadPreview" class="mono"></div>
        </div>
      </div>
    </div>
    <div class="table">
      <table>
        <thead><tr><th>Name</th><th>ID Number</th><th>Role</th><th>Created</th><th>Printed</th><th>Print Count</th><th>Action</th></tr></thead>
        <tbody id="pfTableBody"></tbody>
      </table>
    </div>
  </div>
<script>
  const pfName = document.getElementById('pfName');
  const pfId = document.getElementById('pfId');
  const pfRole = document.getElementById('pfRole');
  const pfSize = document.getElementById('pfSize');
  const pfPreviewBtn = document.getElementById('pfPreviewBtn');
  const pfSaveBtn = document.getElementById('pfSaveBtn');
  const pfSavePrintBtn = document.getElementById('pfSavePrintBtn');
  const pfStatus = document.getElementById('pfStatus');
  const pfPreviewImg = document.getElementById('pfPreviewImg');
  const pfPayloadPreview = document.getElementById('pfPayloadPreview');
  const pfTableBody = document.getElementById('pfTableBody');
  let lastPreview = { payload: '', image: '' };
  function esc(s){ return (s ?? '').toString().replaceAll('&','&amp;').replaceAll('<','&lt;'); }
  function escAttr(s){ return esc(s).replaceAll('\"','&quot;'); }
  function setStatus(t){ pfStatus.textContent = t || ''; }
  function applyProfileTheme(theme){
    const t = String(theme || 'Default').trim() || 'Default';
    if(t === 'Default' || t === 'Blue Accent'){
      delete document.body.dataset.theme;
    } else {
      document.body.dataset.theme = t;
    }
  }
  async function loadProfilePageTheme(){
    try{
      const r = await fetch('/api/server-settings');
      const out = await r.json();
      if(out && out.ok && out.settings) applyProfileTheme(out.settings.theme || 'Default');
    }catch(_e){}
  }
  function getForm(){
    return {
      name: (pfName.value || '').trim(),
      id_number: (pfId.value || '').trim(),
      role: (pfRole.value || '').trim(),
      print_size: (pfSize.value || 'barcode_4x1.25').trim(),
    };
  }
  async function loadProfiles(){
    const r = await fetch('/api/profiles');
    const out = await r.json();
    const rows = Array.isArray(out.items) ? out.items : [];
    pfTableBody.innerHTML = rows.slice().reverse().map(x => `<tr>
      <td>${esc(x.name)}</td>
      <td>${esc(x.id_number)}</td>
      <td>${esc(x.role)}</td>
      <td>${esc(new Date(x.created_at_utc).toLocaleString())}</td>
      <td>${esc(x.last_printed_at_utc ? new Date(x.last_printed_at_utc).toLocaleString() : "-")}</td>
      <td>${esc(x.print_count ?? 0)}</td>
      <td>
        <div class="mini-actions">
          <button type="button" class="mini-btn primary" data-act="print" data-id="${escAttr(x.id_number)}" data-name="${escAttr(x.name)}" data-role="${escAttr(x.role)}">Print</button>
          <button type="button" class="mini-btn danger" data-act="remove" data-id="${escAttr(x.id_number)}">Remove</button>
        </div>
      </td>
    </tr>`).join('') || '<tr><td colspan="7">No profiles yet.</td></tr>';
  }
  async function authorizeProfilePrint(idNumber){
    const firstResp = await fetch('/api/profiles/authorize-print', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ id_number: idNumber }) });
    if(firstResp.ok){
      return true;
    }
    const firstOut = await firstResp.json().catch(() => ({}));
    if(!firstOut.requires_password){
      setStatus(firstOut.error || 'Print authorization failed.');
      return false;
    }
    const pw = window.prompt('Admin password required for reprint:', '');
    if(pw === null){
      setStatus('Reprint cancelled.');
      return false;
    }
    const secondResp = await fetch('/api/profiles/authorize-print', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ id_number: idNumber, admin_password: pw }) });
    const secondOut = await secondResp.json();
    if(!secondResp.ok || !secondOut.ok){
      setStatus(secondOut.error || 'Invalid admin password.');
      return false;
    }
    return true;
  }
  async function removeProfile(idNumber){
    if(!idNumber){ return; }
    const pw = window.prompt('Admin password required to remove profile:', '');
    if(pw === null){ setStatus('Remove cancelled.'); return; }
    const r = await fetch('/api/profiles/delete', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ id_number: idNumber, admin_password: pw }) });
    const out = await r.json().catch(() => ({}));
    if(!r.ok || !out.ok){ setStatus(out.error || 'Remove failed.'); return; }
    setStatus('Profile removed.');
    await loadProfiles();
  }
  async function openPrintWindow(imageSrc, printSize){
    if(!imageSrc){ return; }
    const sizeCss = (printSize === 'normal_2x2')
      ? 'width:2in;height:2in;'
      : 'width:1.333in;height:1.25in;';
    const w = window.open('', '_blank');
    if(!w){ setStatus('Popup blocked.'); return; }
    w.document.write(`<!doctype html><html><head><title>Print QR</title>
      <style>
        @page { margin: 0; }
        html,body { margin:0; padding:0; background:#fff; }
        body { display:flex; align-items:flex-start; justify-content:flex-start; }
        img { ${sizeCss} display:block; object-fit:contain; image-rendering:auto; }
      </style></head><body><img src="${imageSrc}" /></body></html>`);
    w.document.close();
    try { w.focus(); } catch(_e) {}
    setTimeout(() => { try { w.print(); } catch(_e) {} }, 180);
  }
  async function printExistingProfile(idNumber, name, role){
    if(!idNumber){ return; }
    const allowed = await authorizeProfilePrint(idNumber);
    if(!allowed) return;
    const payload = {
      name: (name || '').trim(),
      id_number: (idNumber || '').trim(),
      role: (role || '').trim(),
      print_size: (pfSize.value || 'barcode_4x1.25').trim(),
    };
    const r = await fetch('/api/profile-qr-preview', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
    const out = await r.json();
    if(!r.ok || !out.ok){ setStatus(out.error || 'Preview failed.'); return; }
    pfPreviewImg.src = out.image_data_url || '';
    pfPayloadPreview.textContent = out.qr_payload || '';
    await openPrintWindow(out.image_data_url || '', payload.print_size);
    await loadProfiles();
    setStatus('Profile print opened.');
  }
  async function previewQr(){
    const form = getForm();
    if(!form.name || !form.id_number || !form.role){ setStatus('Complete Name, ID Number, and Role first.'); return false; }
    const r = await fetch('/api/profile-qr-preview', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(form) });
    const out = await r.json();
    if(!out.ok){ setStatus(out.error || 'Preview failed.'); return false; }
    lastPreview = { payload: out.qr_payload || '', image: out.image_data_url || '' };
    pfPreviewImg.src = out.image_data_url || '';
    pfPayloadPreview.textContent = out.qr_payload || '';
    setStatus('Preview generated.');
    return true;
  }
  async function saveProfile(andPrint=false){
    const form = getForm();
    if(!form.name || !form.id_number || !form.role){ setStatus('Complete Name, ID Number, and Role first.'); return; }
    const r = await fetch('/api/profiles', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(form) });
    const out = await r.json();
    if(!out.ok){ setStatus(out.error || 'Save failed.'); return; }
    setStatus('Profile saved.');
    await loadProfiles();
    if(andPrint){
      const allowed = await authorizeProfilePrint(form.id_number);
      if(!allowed) return;
      const ok = await previewQr();
      if(ok && pfPreviewImg.src){
        await openPrintWindow(pfPreviewImg.src, form.print_size);
      }
      await loadProfiles();
    }
  }
  pfPreviewBtn.addEventListener('click', previewQr);
  pfSaveBtn.addEventListener('click', () => saveProfile(false));
  pfSavePrintBtn.addEventListener('click', () => saveProfile(true));
  pfTableBody.addEventListener('click', async (ev) => {
    const btn = ev.target && ev.target.closest ? ev.target.closest('button[data-act]') : null;
    if(!btn) return;
    const act = btn.getAttribute('data-act') || '';
    const id = btn.getAttribute('data-id') || '';
    if(act === 'remove'){
      await removeProfile(id);
      return;
    }
    if(act === 'print'){
      await printExistingProfile(id, btn.getAttribute('data-name') || '', btn.getAttribute('data-role') || '');
    }
  });
  loadProfilePageTheme();
  loadProfiles();
</script>
</body>
</html>
"""


@APP.get("/profiles", response_class=HTMLResponse)
def profile_creator_page():
    return HTMLResponse(PROFILE_CREATOR_HTML)


@APP.get("/favicon.ico")
def favicon():
    # Return empty 204 so browser favicon requests don't pollute logs.
    return Response(status_code=204)


@APP.get("/api/profiles")
def api_profiles():
    return {"ok": True, "items": PROFILES}


@APP.get("/api/profiles/operators")
def api_profiles_operators():
    return {"ok": True, "items": build_operator_activity_directory()}


@APP.post("/api/profiles")
async def api_profiles_create(req: Request):
    data = await req.json()
    name = str(data.get("name", "")).strip()
    id_number = str(data.get("id_number", "")).strip()
    role = str(data.get("role", "")).strip()
    if not name or not id_number or not role:
        return JSONResponse({"ok": False, "error": "name, id_number, and role are required"}, status_code=400)
    if any(str(p.get("id_number", "")).strip() == id_number for p in PROFILES if isinstance(p, dict)):
        return JSONResponse({"ok": False, "error": "Profile already exists for this ID number"}, status_code=409)
    row = {
        "name": name,
        "id_number": id_number,
        "role": role,
        "created_at_utc": utc_now().isoformat(),
        "print_count": 0,
        "last_printed_at_utc": "",
    }
    PROFILES.append(row)
    save_profiles(PROFILES)
    return {"ok": True, "item": row}


@APP.post("/api/profile-qr-preview")
async def api_profile_qr_preview(req: Request):
    data = await req.json()
    name = str(data.get("name", "")).strip()
    id_number = str(data.get("id_number", "")).strip()
    role = str(data.get("role", "")).strip()
    print_size = str(data.get("print_size", "barcode_4x1.25")).strip()
    if not name or not id_number or not role:
        return JSONResponse({"ok": False, "error": "name, id_number, and role are required"}, status_code=400)
    if print_size not in ("barcode_4x1.25", "normal_2x2"):
        print_size = "barcode_4x1.25"
    payload = _profile_qr_payload(name=name, id_number=id_number, role=role)
    image_data_url = _profile_qr_png_data_url(payload, role=role, layout=print_size)
    return {"ok": True, "qr_payload": payload, "image_data_url": image_data_url, "print_size": print_size}


@APP.post("/api/profiles/authorize-print")
async def api_profiles_authorize_print(req: Request):
    data = await req.json()
    id_number = str(data.get("id_number", "")).strip()
    admin_password = str(data.get("admin_password", "") or "")
    if not id_number:
        return JSONResponse({"ok": False, "error": "id_number is required"}, status_code=400)
    idx = next((i for i, p in enumerate(PROFILES) if str((p or {}).get("id_number", "")).strip() == id_number), -1)
    if idx < 0:
        # If profile not yet saved, allow first print flow to proceed after save.
        return {"ok": True, "requires_password": False, "print_count": 0}
    row = PROFILES[idx]
    print_count = int(row.get("print_count", 0) or 0)
    if print_count > 0 and admin_password != PROFILE_REPRINT_ADMIN_PASSWORD:
        return JSONResponse(
            {"ok": False, "error": "Admin password required for reprint", "requires_password": True, "print_count": print_count},
            status_code=403,
        )
    row["print_count"] = print_count + 1
    row["last_printed_at_utc"] = utc_now().isoformat()
    PROFILES[idx] = row
    save_profiles(PROFILES)
    return {"ok": True, "requires_password": False, "print_count": int(row["print_count"])}


@APP.post("/api/profiles/delete")
async def api_profiles_delete(req: Request):
    data = await req.json()
    id_number = str(data.get("id_number", "")).strip()
    admin_password = str(data.get("admin_password", "") or "")
    if not id_number:
        return JSONResponse({"ok": False, "error": "id_number is required"}, status_code=400)
    if admin_password != PROFILE_REPRINT_ADMIN_PASSWORD:
        return JSONResponse({"ok": False, "error": "Invalid admin password"}, status_code=403)
    idx = next((i for i, p in enumerate(PROFILES) if str((p or {}).get("id_number", "")).strip() == id_number), -1)
    if idx < 0:
        return JSONResponse({"ok": False, "error": "Profile not found"}, status_code=404)
    removed = PROFILES.pop(idx)
    save_profiles(PROFILES)
    return {"ok": True, "item": removed}


@APP.post("/api/profiles/authorize-open")
async def api_profiles_authorize_open(req: Request):
    data = await req.json()
    admin_password = str(data.get("admin_password", "") or "")
    if admin_password != PROFILE_REPRINT_ADMIN_PASSWORD:
        return JSONResponse({"ok": False, "error": "Invalid admin password"}, status_code=403)
    return {"ok": True}


@APP.post("/api/machines/status")
async def api_machine_status_set(req: Request):
    data = await req.json()
    machine_code = str(data.get("machine_code", "")).strip()
    status = str(data.get("status", "")).strip()
    reason = str(data.get("reason", "")).strip()
    setter_badge = str(data.get("setter_badge", "")).strip()
    clear_like = {"", "Working"}
    valid = {"", "Working", "No schedule", "Scheduled for fix", "Not working"}
    if not machine_code:
        return JSONResponse({"ok": False, "error": "machine_code is required"}, status_code=400)
    if status not in valid:
        return JSONResponse({"ok": False, "error": "Invalid machine status"}, status_code=400)
    if status in clear_like:
        status = ""
    if status and not reason:
        return JSONResponse({"ok": False, "error": "Reason is required before confirming machine status"}, status_code=400)
    if not setter_badge:
        return JSONResponse({"ok": False, "error": "User QR is required before confirming machine status"}, status_code=400)
    setter = _person_from_badge_any(setter_badge)
    if not setter:
        return JSONResponse({"ok": False, "error": "Scanned user QR is not registered on server profiles/roles"}, status_code=403)
    now = utc_now()
    machine_name = _machine_display_name(machine_code, MACHINE_NAME_MAP.get(machine_code, machine_code))
    previous = MACHINE_STATUS_OVERRIDES.get(machine_code) if isinstance(MACHINE_STATUS_OVERRIDES, dict) else None
    previous_status = str((previous or {}).get("status") or "").strip()
    if not status:
        _close_machine_status_archive_entries(
            machine_code,
            closed_by_badge=setter["code"],
            closed_by_name=setter["name"],
            closed_by_role=setter.get("role", ""),
            closed_reason=reason,
            closed_action="cleared",
            ended_at=now,
        )
        MACHINE_STATUS_OVERRIDES.pop(machine_code, None)
    else:
        if previous_status:
            _close_machine_status_archive_entries(
                machine_code,
                closed_by_badge=setter["code"],
                closed_by_name=setter["name"],
                closed_by_role=setter.get("role", ""),
                closed_reason=reason,
                closed_action="changed" if previous_status != status else "updated",
                ended_at=now,
            )
        MACHINE_STATUS_OVERRIDES[machine_code] = {
            "status": status,
            "reason": reason,
            "updated_at_utc": now.isoformat(),
            "started_at_utc": now.isoformat(),
            "set_by_badge": setter["code"],
            "set_by_name": setter["name"],
            "set_by_role": setter.get("role", ""),
        }
        MACHINE_STATUS_ARCHIVE.append(
            {
                "machine_code": machine_code,
                "machine_name": machine_name,
                "status": status,
                "reason": reason,
                "set_by_badge": setter["code"],
                "set_by_name": setter["name"],
                "set_by_role": setter.get("role", ""),
                "started_at_utc": now.isoformat(),
                "ended_at_utc": "",
                "duration_seconds": None,
                "closed_by_badge": "",
                "closed_by_name": "",
                "closed_by_role": "",
                "closed_reason": "",
                "closed_action": "",
            }
        )
        save_machine_status_archive(MACHINE_STATUS_ARCHIVE)
    save_machine_status_overrides(MACHINE_STATUS_OVERRIDES)
    await broadcast_state()
    return {
        "ok": True,
        "machine_code": machine_code,
        "item": MACHINE_STATUS_OVERRIDES.get(machine_code),
        "actor": setter,
    }


@APP.post("/api/event")
async def api_event(req: Request):
    """
    Expected JSON:
    {
      "client_id": "PI-01",
      "machine_code": "M00001",
      "machine_name": "Machine 01",
      "job_code": "101245",
      "job_name": "J024-0305",
      "operator_id": "1000001",F
      "event": { ... },   # e.g. {"type":"PACK","pack_qty":1,"qty":6}
      "last_event": "PACK +1"
    }
    """
    data = await req.json()

    machine_code = str(data.get("machine_code", "")).strip()
    if not machine_code:
        return JSONResponse({"ok": False, "error": "machine_code required"}, status_code=400)
    client_id = str(data.get("client_id", "UNKNOWN")).strip() or "UNKNOWN"

    sess = SESSIONS.get(machine_code)
    if sess is None:
        sess = MachineSession(
            client_id=client_id,
            machine_code=machine_code,
            machine_name=_machine_display_name(machine_code, data.get("machine_name", machine_code)),
            reject_breakdown={},
            raw_material_scans=[],
            raw_material_logs=[],
            job_payload={},
            operator_shift_logs=[],
        )
        SESSIONS[machine_code] = sess

    # update common fields
    sess.client_id = client_id
    sess.machine_name = _machine_display_name(machine_code, data.get("machine_name", sess.machine_name))
    sess.job_code = data.get("job_code", sess.job_code)
    sess.job_name = data.get("job_name", sess.job_name)
    sess.operator_id = data.get("operator_id", sess.operator_id)
    sess.last_seen_utc = utc_now().isoformat()
    sess.last_event = str(data.get("last_event", sess.last_event))

    # apply event counters if provided
    ev = data.get("event") or {}
    ev_type = str(ev.get("type", "")).upper()
    if ev_type == "FINISH_SHIFT":
        finished_job = ev.get("finished_job")
        if isinstance(finished_job, dict):
            finished_job = dict(finished_job)
            finished_job["record_type"] = "SHIFT_PARTIAL"
            key = _finished_job_key(finished_job)
            idx = _find_finished_job_index(FINISHED_JOBS, key)
            if idx >= 0:
                FINISHED_JOBS[idx] = _prefer_finished_job_row(FINISHED_JOBS[idx], finished_job)
            else:
                FINISHED_JOBS.append(finished_job)
            try:
                save_finished_jobs(FINISHED_JOBS)
            except Exception as e:
                return JSONResponse({"ok": False, "error": str(e)}, status_code=503)
    elif ev_type == "FINISH_JOB":
        finished_job = ev.get("finished_job")
        if isinstance(finished_job, dict):
            FINISHED_JOBS.append(finished_job)
            try:
                save_finished_jobs(FINISHED_JOBS)
            except Exception as e:
                return JSONResponse({"ok": False, "error": str(e)}, status_code=503)
        if machine_code in SESSIONS:
            del SESSIONS[machine_code]
    elif ev_type == "PRODUCTION_DAILY_REPORT_RESOLVED":
        pdr_row = dict(ev)
        pdr_row.update({
            "client_id": client_id,
            "machine_code": machine_code,
            "machine_name": data.get("machine_name", machine_code),
            "job_code": data.get("job_code"),
            "job_name": data.get("job_name"),
            "operator_id": data.get("operator_id"),
        })
        if not _insert_pdr_report_sql(pdr_row):
            return JSONResponse({"ok": False, "error": "pdr_reports SQL storage is unavailable"}, status_code=503)
            _remove_persisted_active_session(machine_code)
    elif ev_type == "PRODUCTION_DAILY_REPORT":
        mode = str(ev.get("mode") or "").strip().upper()
        if mode == "WAITING_FOR_MAINTENANCE":
            sess.pdr_operator_reason_code = str(ev.get("operator_reason_code") or "").strip() or sess.pdr_operator_reason_code
            sess.pdr_operator_reason_text = str(ev.get("operator_reason") or "").strip() or sess.pdr_operator_reason_text
            sess.downtime_reason_code = None
            sess.downtime_reason_text = None
            sess.downtime_active = False
            sess.maintenance_name = None
            sess.waiting_downtime_start_maintenance = True
            sess.waiting_pdr_maintenance_reason = False
            sess.waiting_downtime_end_maintenance = False
            if not sess.downtime_wait_started_at:
                sess.downtime_wait_started_at = time.time()
    elif ev_type == "JOB_LINKAGE_SET":
        sess.linkage_enabled = True
        linked_code = str(ev.get("linked_job_code", "")).strip()
        linked_name = str(ev.get("linked_job_name", "")).strip()
        if linked_code or linked_name:
            rows = list(sess.linkage_jobs or [])
            rows.append({"job_code": linked_code, "job_name": linked_name})
            sess.linkage_jobs = rows
    elif ev_type == "OPERATOR_SHIFT_SAVE":
        shift_payload = ev.get("operator_shift")
        if isinstance(shift_payload, dict):
            rows = list(sess.operator_shift_logs or [])
            rows.append(shift_payload)
            sess.operator_shift_logs = rows[-40:]
    elif ev_type in ("SESSION_SYNC", "HEARTBEAT"):
        snap = ev.get("session_snapshot")
        if isinstance(snap, dict):
            sess.machine_name = _machine_display_name(machine_code, snap.get("machine_name") or sess.machine_name or machine_code)
            sess.job_code = snap.get("job_code", sess.job_code)
            sess.job_name = snap.get("job_name", sess.job_name)
            sess.job_started_at = snap.get("job_started_at", sess.job_started_at)
            sess.operator_id = snap.get("operator_id", sess.operator_id)
            sess.pack_total = int(snap.get("pack_total", snap.get("pack_count", sess.pack_total)) or 0)
            sess.good_total = int(snap.get("good_total", sess.good_total) or 0)
            sess.butal_total = int(snap.get("butal_total", sess.butal_total) or 0)
            sess.reject_total = int(snap.get("reject_total", sess.reject_total) or 0)
            sess.no_shot_total = int(snap.get("no_shot_total", sess.no_shot_total) or 0)
            if isinstance(snap.get("reject_breakdown"), dict):
                sess.reject_breakdown = dict(snap.get("reject_breakdown") or {})
            sess.raw_sacks_count = int(snap.get("raw_sacks_count", sess.raw_sacks_count) or 0)
            if isinstance(snap.get("raw_material_scans"), list):
                sess.raw_material_scans = list(snap.get("raw_material_scans") or [])
            if isinstance(snap.get("raw_material_logs"), list):
                sess.raw_material_logs = list(snap.get("raw_material_logs") or [])
            sess.startup_reject_total = int(snap.get("startup_reject_total", sess.startup_reject_total) or 0)
            sess.downtime_reason_code = snap.get("downtime_reason_code", sess.downtime_reason_code)
            sess.downtime_reason_text = snap.get("downtime_reason_text", sess.downtime_reason_text)
            sess.downtime_started_at = snap.get("downtime_started_at", sess.downtime_started_at)
            sess.downtime_last_seconds = snap.get("downtime_last_seconds", sess.downtime_last_seconds)
            sess.downtime_active = bool(snap.get("downtime_active", sess.downtime_active))
            sess.pdr_operator_reason_code = snap.get("pdr_operator_reason_code", sess.pdr_operator_reason_code)
            sess.pdr_operator_reason_text = snap.get("pdr_operator_reason_text", sess.pdr_operator_reason_text)
            sess.downtime_wait_started_at = snap.get("downtime_wait_started_at", sess.downtime_wait_started_at)
            sess.downtime_wait_last_seconds = snap.get("downtime_wait_last_seconds", sess.downtime_wait_last_seconds)
            sess.waiting_downtime_start_maintenance = bool(snap.get("waiting_downtime_start_maintenance", sess.waiting_downtime_start_maintenance))
            sess.waiting_pdr_maintenance_reason = bool(snap.get("waiting_pdr_maintenance_reason", sess.waiting_pdr_maintenance_reason))
            sess.waiting_downtime_end_maintenance = bool(snap.get("waiting_downtime_end_maintenance", sess.waiting_downtime_end_maintenance))
            sess.waiting_maintenance_qr = bool(snap.get("waiting_maintenance_qr", sess.waiting_maintenance_qr))
            sess.waiting_supervisor_qr = bool(snap.get("waiting_supervisor_qr", sess.waiting_supervisor_qr))
            sess.supervisor_downtime_confirmation_started_at = snap.get("supervisor_downtime_confirmation_started_at", sess.supervisor_downtime_confirmation_started_at)
            sess.cycle_time_new_input = snap.get("cycle_time_new_input", sess.cycle_time_new_input)
            sess.cycle_time_current = snap.get("cycle_time_current", sess.cycle_time_current)
            live_avg = snap.get("live_cycle_avg_seconds", sess.live_cycle_avg_seconds)
            try:
                sess.live_cycle_avg_seconds = float(live_avg) if live_avg is not None else sess.live_cycle_avg_seconds
            except Exception:
                pass
            sess.maintenance_name = snap.get("maintenance_name", sess.maintenance_name)
            sess.supervisor_name = snap.get("supervisor_name", sess.supervisor_name)
            if isinstance(snap.get("job_payload"), dict):
                sess.job_payload = dict(snap.get("job_payload") or {})
            sess.linkage_enabled = bool(snap.get("linkage_enabled", sess.linkage_enabled))
            if isinstance(snap.get("linkage_jobs"), list):
                sess.linkage_jobs = list(snap.get("linkage_jobs") or [])
            if isinstance(snap.get("operator_shift_logs"), list):
                sess.operator_shift_logs = list(snap.get("operator_shift_logs") or [])
            if isinstance(snap.get("butal_by_job"), dict):
                sess.butal_by_job = {str(k): int(v or 0) for k, v in dict(snap.get("butal_by_job") or {}).items()}
            sess.last_shift_butal_qty = int(snap.get("last_shift_butal_qty", sess.last_shift_butal_qty) or 0)
            sess.last_shift_butal_raw = str(snap.get("last_shift_butal_raw", sess.last_shift_butal_raw) or "")
            sess.last_shift_butal_saved_at = snap.get("last_shift_butal_saved_at", sess.last_shift_butal_saved_at)
            sess.last_shift_butal_job_code = snap.get("last_shift_butal_job_code", sess.last_shift_butal_job_code)
            sess.last_shift_butal_job_name = snap.get("last_shift_butal_job_name", sess.last_shift_butal_job_name)
            if isinstance(snap.get("last_shift_butal_by_job"), dict):
                sess.last_shift_butal_by_job = dict(snap.get("last_shift_butal_by_job") or {})
            _persist_active_sessions_state()
    elif ev_type == "PACK":
        qty = int(ev.get("qty", 0) or 0)
        pack_qty = int(ev.get("pack_qty", 1) or 1)
        sess.pack_total += pack_qty
        sess.good_total += qty
    elif ev_type == "LAST_SHIFT_BUTAL_PACK":
        sess.pack_total += int(ev.get("pack_qty", 1) or 1)
        butal_qty = int(ev.get("butal_qty", 0) or 0)
        sess.butal_total += butal_qty
        job_key = str(sess.job_code or "").strip()
        if job_key and butal_qty > 0:
            rows = dict(sess.butal_by_job or {})
            rows[job_key] = int(rows.get(job_key, 0) or 0) + butal_qty
            sess.butal_by_job = rows
        sess.last_shift_butal_qty = 0
        sess.last_shift_butal_raw = ""
        sess.last_shift_butal_saved_at = None
        sess.last_shift_butal_job_code = None
        sess.last_shift_butal_job_name = None
        if isinstance(sess.last_shift_butal_by_job, dict):
            key = str(sess.job_code or "").strip()
            if key:
                sess.last_shift_butal_by_job.pop(key, None)
    elif ev_type == "BUTAL":
        qty = int(ev.get("qty", 0) or 0)
        sess.butal_total += qty
        assigned_job_code = str(ev.get("assigned_job_code") or sess.job_code or "").strip()
        if assigned_job_code and qty > 0:
            rows = dict(sess.butal_by_job or {})
            rows[assigned_job_code] = int(rows.get(assigned_job_code, 0) or 0) + qty
            sess.butal_by_job = rows
    elif ev_type == "REJECT":
        qty = int(ev.get("qty", 1) or 1)
        reason = str(ev.get("reason", "")).strip()
        if reason.upper() == "NO":
            sess.no_shot_total += qty
        else:
            sess.reject_total += qty
        if reason:
            sess.reject_breakdown[reason] = sess.reject_breakdown.get(reason, 0) + qty

    if ev_type not in ("SESSION_SYNC", "HEARTBEAT", "FINISH_JOB"):
        _persist_active_sessions_state()

    await broadcast_state()
    return {"ok": True}


@APP.get("/api/finished-jobs")
def api_finished_jobs():
    return {"ok": True, "items": FINISHED_JOBS}


@APP.get("/api/planning/board")
def api_planning_board():
    return {"ok": True, "board": PLANNING_BOARD, "machines": MACHINE_NAME_MAP}


@APP.post("/api/planning/board")
async def api_planning_board_save(req: Request):
    global PLANNING_BOARD
    data = await req.json()
    board = data.get("board") if isinstance(data.get("board"), dict) else data
    if not isinstance(board, dict):
        return JSONResponse({"ok": False, "error": "board object is required"}, status_code=400)
    PLANNING_BOARD = save_planning_board(board)
    await broadcast_state()
    return {"ok": True, "board": PLANNING_BOARD}


@APP.post("/api/planning/lookup")
async def api_planning_lookup(req: Request):
    data = await req.json()
    job_identifier = str(data.get("job_identifier") or data.get("job_id") or data.get("work_order") or "").strip()
    if not job_identifier:
        return JSONResponse({"ok": False, "error": "job_identifier is required"}, status_code=400)
    try:
        card = fetch_planning_job_from_bms(job_identifier)
        return {"ok": True, "item": card}
    except urllib_error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return JSONResponse({"ok": False, "error": f"BMS HTTP {e.code}", "body": body[:500]}, status_code=502)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)


@APP.get("/api/planning/low-stock")
def api_planning_low_stock(threshold: float = 100, refresh: int = 0):
    try:
        result = _fetch_low_stock_recommendations(
            threshold=max(0.0, float(threshold or 0)),
            force_refresh=bool(refresh),
        )
        return {
            "ok": not bool(result.get("error")),
            "items": result.get("items") or [],
            "from_cache": bool(result.get("from_cache")),
            "saved_at_utc": result.get("saved_at_utc") or "",
            "threshold": threshold,
            "error": result.get("error") or "",
        }
    except urllib_error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return JSONResponse({"ok": False, "error": f"IMS HTTP {e.code}", "body": body[:500]}, status_code=502)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)


@APP.get("/api/server-settings")
def api_server_settings():
    return {
        "ok": True,
        "settings": {
            "theme": str(SERVER_SETTINGS.get("theme", "Default")),
            "qrgen_base_url": current_qrgen_base_url(),
        },
    }


@APP.get("/api/daily-roles")
def api_daily_roles():
    return {
        "ok": True,
        "date": _today_key_local(),
        "items": get_today_role_assignments(),
    }


@APP.post("/api/daily-roles")
async def api_daily_roles_save(req: Request):
    data = await req.json()
    badge_code = str(data.get("badge_code", "")).strip()
    if not badge_code:
        return JSONResponse({"ok": False, "error": "badge_code is required"}, status_code=400)
    profile = _find_profile_by_id_number(badge_code)
    if not isinstance(profile, dict):
        return JSONResponse({"ok": False, "error": "Profile not found for this ID number"}, status_code=404)
    company_role = _normalize_company_role(data.get("company_role") or profile.get("role") or "")
    if not company_role:
        return JSONResponse({"ok": False, "error": "company_role is required"}, status_code=400)
    extra_privilege = str(data.get("extra_privilege", "none") or "none").strip().lower()
    if extra_privilege not in ("none", "supervisor", "qc"):
        return JSONResponse({"ok": False, "error": "extra_privilege must be none, supervisor, or qc"}, status_code=400)
    rights = _combine_privileges(_base_privilege_from_company_role(company_role), extra_privilege)
    # Name fallback from profile/static maps if available, otherwise use incoming/displayed badge.
    person_name = (
        str(data.get("name", "")).strip()
        or str(profile.get("name", "")).strip()
        or SUPERVISOR_BADGES.get(badge_code)
        or QC_BADGES.get(badge_code)
        or badge_code
    )
    set_today_role_assignment(
        badge_code,
        person_name,
        rights,
        company_role=company_role,
        extra_privilege=extra_privilege,
    )
    return {"ok": True, "date": _today_key_local(), "items": get_today_role_assignments()}


@APP.post("/api/server-settings")
async def api_server_settings_save(req: Request):
    global SERVER_SETTINGS
    data = await req.json()
    theme = str(data.get("theme", SERVER_SETTINGS.get("theme", "Default"))).strip() or "Default"
    qrgen_base_url = str(data.get("qrgen_base_url", current_qrgen_base_url())).strip().rstrip("/")
    if not qrgen_base_url:
        return JSONResponse({"ok": False, "error": "qrgen_base_url is required"}, status_code=400)
    SERVER_SETTINGS = {
        "theme": theme,
        "qrgen_base_url": qrgen_base_url,
    }
    save_server_settings(SERVER_SETTINGS)
    return {"ok": True, "settings": SERVER_SETTINGS}


@APP.post("/api/finished-jobs/review")
async def api_finished_jobs_review(req: Request):
    data = await req.json()
    job_key = str(data.get("job_key", "")).strip()
    action = str(data.get("action", "")).strip().lower()  # approve | disapprove | update
    remarks = str(data.get("remarks", "")).strip()
    reviewer_badge = str(data.get("reviewer_badge", "")).strip()
    changes = data.get("changes") if isinstance(data.get("changes"), dict) else {}

    if not job_key:
        return JSONResponse({"ok": False, "error": "job_key is required"}, status_code=400)
    if action not in ("approve", "disapprove", "update"):
        return JSONResponse({"ok": False, "error": "action must be approve, disapprove, or update"}, status_code=400)
    if not remarks:
        return JSONResponse({"ok": False, "error": "remarks is required"}, status_code=400)

    reviewer = _reviewer_from_badge(reviewer_badge)
    if reviewer is None:
        return JSONResponse({"ok": False, "error": "Invalid reviewer QR/badge. Supervisor badge required."}, status_code=400)
    if str(reviewer.get("rights") or "").strip().lower() not in ("supervisor", "both"):
        return JSONResponse({"ok": False, "error": "Only Supervisor QR can approve or edit shift/job data."}, status_code=403)

    idx = _find_finished_job_index(FINISHED_JOBS, job_key)
    if idx < 0:
        return JSONResponse({"ok": False, "error": "Finished job not found"}, status_code=404)

    row = dict(FINISHED_JOBS[idx] or {})
    now_utc = utc_now().isoformat()
    row.setdefault("review_history", [])
    original_snapshot = {
        "pack_count": row.get("pack_count", 0),
        "good_total": row.get("good_total", 0),
        "butal_total": row.get("butal_total", 0),
        "reject_total": row.get("reject_total", 0),
        "no_shot_total": row.get("no_shot_total", 0),
        "total_good": row.get("total_good", 0),
        "reject_breakdown": dict(row.get("reject_breakdown") or {}),
    }

    def _apply_review_changes_to_row() -> Optional[JSONResponse]:
        int_fields = ("pack_count", "good_total", "butal_total", "reject_total", "startup_reject_total", "no_shot_total", "raw_sacks_count")
        for k in int_fields:
            if k in changes:
                try:
                    row[k] = int(changes.get(k) or 0)
                except Exception:
                    return JSONResponse({"ok": False, "error": f"{k} must be an integer"}, status_code=400)
        if "total_good" in changes:
            try:
                row["total_good"] = int(changes.get("total_good") or 0)
            except Exception:
                return JSONResponse({"ok": False, "error": "total_good must be an integer"}, status_code=400)
        else:
            row["total_good"] = int(row.get("good_total", 0) or 0) + int(row.get("butal_total", 0) or 0)

        if "reject_breakdown" in changes:
            rb = changes.get("reject_breakdown")
            if not isinstance(rb, dict):
                return JSONResponse({"ok": False, "error": "reject_breakdown must be an object"}, status_code=400)
            row["reject_breakdown"] = {str(k): int(v or 0) for k, v in rb.items()}
        return None

    if action == "approve":
        change_error = _apply_review_changes_to_row() if changes else None
        if change_error is not None:
            return change_error
        if changes:
            row["last_original_snapshot"] = original_snapshot
            row["changed_by"] = reviewer["name"]
            row["changed_by_code"] = reviewer["code"]
            row["changed_by_role"] = reviewer["role"]
            row["change_remarks"] = remarks
            row["changed_at_utc"] = now_utc
        row["approved_by"] = reviewer["name"]
        row["approved_by_code"] = reviewer["code"]
        row["approved_by_role"] = reviewer["role"]
        row["approved_remarks"] = remarks
        row["approved_at_utc"] = now_utc
        row["review_status"] = "APPROVED"
        row["review_history"].append({
            "action": "APPROVE",
            "remarks": remarks,
            "actor_name": reviewer["name"],
            "actor_code": reviewer["code"],
            "actor_role": reviewer["role"],
            "timestamp_utc": now_utc,
            "changes": changes if changes else {},
        })
    else:
        change_error = _apply_review_changes_to_row()
        if change_error is not None:
            return change_error

        row["changed_by"] = reviewer["name"]
        row["changed_by_code"] = reviewer["code"]
        row["changed_by_role"] = reviewer["role"]
        row["change_remarks"] = remarks
        row["changed_at_utc"] = now_utc
        if action == "disapprove":
            row["review_status"] = "DISAPPROVED_CHANGED"
            row["last_original_snapshot"] = original_snapshot
            row["review_history"].append({
                "action": "DISAPPROVE_CHANGE",
                "remarks": remarks,
                "actor_name": reviewer["name"],
                "actor_code": reviewer["code"],
                "actor_role": reviewer["role"],
                "timestamp_utc": now_utc,
                "changes": changes,
            })
        else:
            row["review_status"] = row.get("review_status") or "PENDING_SUPERVISOR"
            row["last_original_snapshot"] = original_snapshot
            row["review_history"].append({
                "action": "UPDATE",
                "remarks": remarks,
                "actor_name": reviewer["name"],
                "actor_code": reviewer["code"],
                "actor_role": reviewer["role"],
                "timestamp_utc": now_utc,
                "changes": changes,
            })

    FINISHED_JOBS[idx] = row
    save_finished_jobs(FINISHED_JOBS)
    await broadcast_state()
    return {"ok": True, "item": row}


@APP.post("/api/finished-jobs/archive")
async def api_finished_jobs_archive(req: Request):
    data = await req.json()
    job_key = str(data.get("job_key", "")).strip()
    print_payload = data.get("print_payload") if isinstance(data.get("print_payload"), dict) else {}
    print_payloads = data.get("print_payloads") if isinstance(data.get("print_payloads"), list) else []
    qr_payload = str(data.get("qr_payload", "")).strip()
    if not job_key:
        return JSONResponse({"ok": False, "error": "job_key is required"}, status_code=400)
    idx = _find_finished_job_index(FINISHED_JOBS, job_key)
    if idx < 0:
        return JSONResponse({"ok": False, "error": "Finished job not found"}, status_code=404)

    row = dict(FINISHED_JOBS[idx] or {})
    now_utc = utc_now().isoformat()
    row["printed_at_utc"] = now_utc
    row["archived_at_utc"] = now_utc
    row["print_request_payload"] = print_payload
    if print_payloads:
        row["print_request_payloads"] = list(print_payloads)
    if qr_payload:
        row["printed_qr_payload"] = qr_payload
    row["archive_status"] = "PRINTED_ARCHIVED"
    row.setdefault("review_history", [])
    row["review_history"].append({
        "action": "ARCHIVE_AFTER_PRINT",
        "timestamp_utc": now_utc,
    })

    next_archived_jobs = list(ARCHIVED_JOBS)
    next_finished_jobs = list(FINISHED_JOBS)
    next_archived_jobs.append(row)
    del next_finished_jobs[idx]
    try:
        save_archived_jobs(next_archived_jobs)
        save_finished_jobs(next_finished_jobs)
    except Exception as e:
        try:
            save_archived_jobs(ARCHIVED_JOBS)
        except Exception:
            pass
        return JSONResponse(
            {
                "ok": False,
                "error": f"Archive storage is unavailable: {e}",
                "item": row,
            },
            status_code=503,
        )
    ARCHIVED_JOBS[:] = next_archived_jobs
    FINISHED_JOBS[:] = next_finished_jobs
    await broadcast_state()
    return {"ok": True, "item": row}


@APP.get("/api/products")
def api_products(refresh: int = 0):
    result = get_products(force_refresh=bool(refresh))
    return {
        "ok": True,
        "items": result["items"],
        "from_cache": result["from_cache"],
        "updated": result["updated"],
        "error": result.get("error", ""),
        "source_file": _app_relative_path_str(PRODUCT_API_CONFIG_FILE),
        "cache_file": _app_relative_path_str(PRODUCT_CACHE_FILE),
    }


@APP.post("/api/raw-material-qr")
async def api_raw_material_qr(req: Request):
    data = await req.json()
    product_id = str(data.get("product_id", "")).strip()
    po_number = str(data.get("po_number", "")).strip()
    finished_job = data.get("finished_job") if isinstance(data.get("finished_job"), dict) else {}
    stage_index = int(data.get("stage_index", 0) or 0)
    qr_plan = _build_finished_job_qr_plan(finished_job, product_id, po_number)
    selected_index = max(0, min(stage_index, max(len(qr_plan) - 1, 0)))
    first_entry = qr_plan[selected_index] if qr_plan else {}
    stage_product_id = str(first_entry.get("product_id", "")).strip() or product_id
    payload = str(first_entry.get("qr_payload", "")).strip() or _build_raw_material_qr_value(stage_product_id, po_number=str(first_entry.get("po_number", "")).strip())
    product_meta = _lookup_product_meta(stage_product_id)
    product_name = str(first_entry.get("product_name", "")).strip() or product_meta.get("name", "")
    product_sku = str(first_entry.get("product_sku", "")).strip() or product_meta.get("sku", "")
    parsed_first = first_entry.get("parsed") if isinstance(first_entry.get("parsed"), dict) else _parse_qr_segments(payload)
    qty_value = int(_parse_number_like(parsed_first.get("qty") or 1) or 1)
    index_value = int(_parse_number_like(parsed_first.get("index") or 1) or 1)
    total_value = int(_parse_number_like(parsed_first.get("total") or 1) or 1)
    try:
        image_url = _qr_png_data_url(payload)
    except Exception:
        image_url = ""
    try:
        label_url = _label_png_data_url(
            payload,
            product_id=stage_product_id,
            product_name=product_name,
            product_sku=product_sku,
            qty=qty_value,
            index_value=index_value,
            total=total_value,
        )
    except Exception:
        label_url = image_url
    return {
        "ok": True,
        "qr_payload": payload,
        "qr_image_data_url": image_url,
        "label_image_data_url": label_url,
        "parsed": parsed_first,
        "qr_plan": qr_plan,
        "selected_stage_index": selected_index,
        "stage_label": first_entry.get("stage_label", "1 / 1 - QR"),
        "qr_format": _raw_qr_format_template(),
    }


@APP.post("/api/qrgen/pending-request")
async def api_qrgen_pending_request(req: Request):
    data = await req.json()
    product_name = str(data.get("product_name", "")).strip()
    quantity = str(data.get("quantity", "")).strip()
    total = str(data.get("total", "")).strip()
    po_number = str(data.get("po_number", "")).strip()
    product_desc = str(data.get("product_desc", "")).strip()
    lot_number = str(data.get("lot_number", "")).strip()
    requested_at_ph = str(data.get("requested_at_ph", "")).strip() or _requested_at_ph_str()
    qr_stage_label = str(data.get("qr_stage_label", "")).strip()
    stage_requires_po = "butal" in qr_stage_label.lower()

    if not product_name:
        return JSONResponse({"ok": False, "error": "product_name is required"}, status_code=400)
    if not quantity:
        return JSONResponse({"ok": False, "error": "quantity is required"}, status_code=400)
    if not total:
        return JSONResponse({"ok": False, "error": "total is required"}, status_code=400)
    if stage_requires_po and not po_number:
        return JSONResponse({"ok": False, "error": "po_number is required"}, status_code=400)

    outbound = {
        "product_name": product_name,
        "quantity": quantity,
        "total": total,
        "po_number": po_number or "",
        "product_desc": product_desc,
        "requested_at_ph": requested_at_ph,
    }
    if lot_number:
        outbound["lot_number"] = lot_number

    try:
        upstream = _post_qrgen_pending_request(outbound)
        return {
            "ok": True,
            "target_base_url": QRGEN_BASE_URL,
            "sent": outbound,
            "upstream_status_code": upstream.get("status_code"),
            "upstream_body": upstream.get("body"),
        }
    except urllib_error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return JSONResponse(
            {
                "ok": False,
                "error": f"QRGEN upstream HTTP {e.code}",
                "target_base_url": QRGEN_BASE_URL,
                "upstream_body": body,
                "sent": outbound,
            },
            status_code=502,
        )
    except Exception as e:
        return JSONResponse(
            {
                "ok": False,
                "error": f"QRGEN request failed: {e}",
                "target_base_url": QRGEN_BASE_URL,
                "sent": outbound,
            },
            status_code=502,
        )


@APP.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    WS_CLIENTS.append(ws)
    await broadcast_state()
    try:
        while True:
            # keep alive; client doesn't need to send anything
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if ws in WS_CLIENTS:
            WS_CLIENTS.remove(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:APP", host="0.0.0.0", port=8000, reload=False)
