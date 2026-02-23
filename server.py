# server.py
from __future__ import annotations
import asyncio
import base64
import io
import json
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib import request as urllib_request
from urllib import error as urllib_error
from urllib.parse import urlencode
import qrcode
from PIL import Image, ImageDraw, ImageFont

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

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

ACTIVE_TTL_SECONDS = 2  # aggressive monitoring: mark disconnected quickly
STATE_TICK_SECONDS = 0.25
FINISHED_JOBS_FILE = Path(__file__).resolve().parent / "Database" / "finished_jobs_server.json"
CLIENT_FINISHED_JOBS_FILE = Path(__file__).resolve().parent / "Database" / "finished_jobs_client.json"
ARCHIVED_JOBS_FILE = Path(__file__).resolve().parent / "Database" / "archived_jobs_server.json"
PRODUCT_SOURCE_FILE = Path(__file__).resolve().parent / "Product_ID.json"
PRODUCT_CACHE_FILE = Path(__file__).resolve().parent / "Database" / "product_catalog_cache.json"
SERVER_SETTINGS_FILE = Path(__file__).resolve().parent / "Database" / "server_settings.json"
DAILY_ROLE_ASSIGNMENTS_FILE = Path(__file__).resolve().parent / "Database" / "daily_role_assignments.json"
PROFILES_FILE = Path(__file__).resolve().parent / "Database" / "user_qr_profiles.json"
PROFILE_REPRINT_ADMIN_PASSWORD = "0t1docmtl$tm"
QRGEN_BASE_URL = os.environ.get("QRGEN_BASE_URL", "http://192.168.1.149:5000").strip().rstrip("/")
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
    "M00004": "IMM 303",
    "M00005": "IMM 304",
    "M00006": "IMM 305",
    "M00007": "IMM 306",
    "M00008": "IMM 307",
    "M00009": "IMM 308",
    "M00010": "IMM 309",
    "M00011": "IMM 310",
    "M00012": "IMM 311",
    "M00013": "IMM 312",
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
    operator_id: Optional[str] = None
    pack_total: int = 0
    good_total: int = 0
    butal_total: int = 0
    reject_total: int = 0
    reject_breakdown: Dict[str, int] = None
    raw_sacks_count: int = 0
    raw_material_scans: List[str] = None
    raw_material_logs: List[Dict[str, Any]] = None
    startup_reject_total: int = 0
    downtime_reason_code: Optional[str] = None
    downtime_reason_text: Optional[str] = None
    downtime_started_at: Optional[float] = None
    downtime_last_seconds: Optional[int] = None
    downtime_active: bool = False
    cycle_time_current: Optional[str] = None
    job_payload: Dict[str, Any] = None
    linkage_enabled: bool = False
    linkage_jobs: List[Dict[str, Any]] = None
    last_event: str = ""
    last_seen_utc: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["reject_breakdown"] = d["reject_breakdown"] or {}
        d["raw_material_scans"] = d["raw_material_scans"] or []
        d["raw_material_logs"] = d["raw_material_logs"] or []
        d["job_payload"] = d["job_payload"] or {}
        d["linkage_jobs"] = d["linkage_jobs"] or []
        return d


SESSIONS: Dict[str, MachineSession] = {}  # key = machine_code
WS_CLIENTS: List[WebSocket] = []
STATE_TICK_TASK: Optional[asyncio.Task] = None


def _read_json_list(path: Path) -> List[Dict[str, Any]]:
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return raw
    except Exception:
        pass
    return []


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
    if low == "maintenance":
        return "maintenance"
    if low in {"planner", "production manager"}:
        return "viewer"
    return "viewer"


def _combine_privileges(base_privilege: str, extra_privilege: str) -> str:
    base = str(base_privilege or "").strip().lower() or "viewer"
    extra = str(extra_privilege or "").strip().lower()
    if extra not in {"", "none", "supervisor", "qc"}:
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
    return "viewer"


def load_finished_jobs() -> List[Dict[str, Any]]:
    server_rows = _read_json_list(FINISHED_JOBS_FILE)
    client_rows = _read_json_list(CLIENT_FINISHED_JOBS_FILE)
    merged: List[Dict[str, Any]] = []
    seen = set()
    for row in server_rows + client_rows:
        if not isinstance(row, dict):
            continue
        key = _finished_job_key(row)
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    return merged


def save_finished_jobs(rows: List[Dict[str, Any]]):
    FINISHED_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    FINISHED_JOBS_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def load_archived_jobs() -> List[Dict[str, Any]]:
    return _read_json_list(ARCHIVED_JOBS_FILE)


def save_archived_jobs(rows: List[Dict[str, Any]]):
    ARCHIVED_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVED_JOBS_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def load_profiles() -> List[Dict[str, Any]]:
    rows = _read_json_list(PROFILES_FILE)
    return [r for r in rows if isinstance(r, dict)]


def save_profiles(rows: List[Dict[str, Any]]):
    PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROFILES_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _today_key_local() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def load_daily_role_assignments() -> Dict[str, Any]:
    return _load_json_object(DAILY_ROLE_ASSIGNMENTS_FILE)


def save_daily_role_assignments(rows: Dict[str, Any]):
    DAILY_ROLE_ASSIGNMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    DAILY_ROLE_ASSIGNMENTS_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _build_raw_material_qr_value(product_id: str, po_number: str = "") -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    p = "P" + _zpad_digits(product_id, WIDTH_P)
    q = "Q" + _zpad_digits("1", WIDTH_Q)
    i = "I" + _zpad_digits("1", WIDTH_I)
    t = "T" + _zpad_digits("1", WIDTH_T)
    po_digits = _zpad_digits(po_number, 12)
    l = "L" + f"{stamp}-{po_digits}"
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


def _load_json_object(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            obj = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    return {}


def load_server_settings() -> Dict[str, Any]:
    raw = _load_json_object(SERVER_SETTINGS_FILE)
    return {
        "theme": str(raw.get("theme", "Default")).strip() or "Default",
        "qrgen_base_url": str(raw.get("qrgen_base_url", QRGEN_BASE_URL)).strip().rstrip("/"),
    }


def save_server_settings(rows: Dict[str, Any]):
    SERVER_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SERVER_SETTINGS_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


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
        if pid and name:
            out.append({"id": pid, "name": name, "sku": sku})
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


def _save_product_cache(items: List[Dict[str, str]], source_meta: Optional[Dict[str, Any]] = None):
    PRODUCT_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "items": items,
        "source_meta": source_meta or {},
    }
    PRODUCT_CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_products_from_source() -> List[Dict[str, str]]:
    cfg = _load_json_object(PRODUCT_SOURCE_FILE)
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
                    {"source_file": str(PRODUCT_SOURCE_FILE), "cache_upgrade": True},
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
        _save_product_cache(fetched, {"source_file": str(PRODUCT_SOURCE_FILE)})
        return {"items": fetched, "from_cache": False, "updated": updated, "error": ""}

    return {"items": cached_items, "from_cache": True, "updated": False, "error": fetch_error}


FINISHED_JOBS: List[Dict[str, Any]] = load_finished_jobs()
ARCHIVED_JOBS: List[Dict[str, Any]] = load_archived_jobs()
PROFILES: List[Dict[str, Any]] = load_profiles()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def prune_dead_sessions():
    """
    Keep sessions so dashboard can show stale machines as DISCONNECTED.
    (No hard delete on heartbeat timeout.)
    """
    return


async def broadcast_state():
    payload = {
        "type": "STATE",
        "active_ttl_seconds": ACTIVE_TTL_SECONDS,
        "sessions": [s.to_dict() for s in SESSIONS.values()],
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
    html, body { height: 100%; margin: 0; }
    body { font-family: "Poppins", sans-serif; background: #f8f8f8; color: #333; display: flex; flex-direction: column; }
    .diagnostics { padding: 8px 14px; background: #e9ecef; border-bottom: 1px solid #d9d9d9; display: grid; grid-template-columns: 48px 48px 48px repeat(4, minmax(180px, 1fr)); gap: 8px; align-items: stretch; }
    .server-menu-btn { width: 48px; min-width: 48px; border: 1px solid #d4dae4; border-radius: 11px; background: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: transform .12s ease, box-shadow .16s ease, background-color .16s ease; }
    .server-menu-btn:hover { transform: translateY(-1px); box-shadow: 0 8px 18px rgba(15,23,42,0.08); background: #fbfcfe; }
    .server-menu-btn:active { transform: translateY(0) scale(0.985); }
    .server-menu-icon { width: 20px; height: 14px; position: relative; }
    .server-menu-icon span { display: block; position: absolute; left: 0; right: 0; height: 2px; background: #334155; border-radius: 999px; }
    .server-menu-icon span:nth-child(1){ top: 0; }
    .server-menu-icon span:nth-child(2){ top: 6px; }
    .server-menu-icon span:nth-child(3){ top: 12px; }
    .person-menu-icon { width: 20px; height: 20px; position: relative; }
    .person-menu-icon::before { content: ""; position: absolute; top: 1px; left: 5px; width: 10px; height: 10px; border: 2px solid #334155; border-radius: 50%; box-sizing: border-box; }
    .person-menu-icon::after { content: ""; position: absolute; bottom: 1px; left: 2px; width: 16px; height: 8px; border: 2px solid #334155; border-top-left-radius: 10px; border-top-right-radius: 10px; border-bottom: none; box-sizing: border-box; }
    .person-menu-icon.with-plus::marker { content: ""; }
    .person-plus-badge { position: absolute; right: -2px; bottom: -2px; width: 10px; height: 10px; border-radius: 50%; background: #2563eb; color: #fff; font-size: 9px; line-height: 1; display:flex; align-items:center; justify-content:center; font-weight: 700; }
    .diag-item { background: #fff; border-radius: 10px; padding: 6px 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); font-size: 12px; line-height: 1.15; }
    .diag-item .value { font-weight: 700; margin-top: 4px; line-height: 1.12; }
    .status-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
    .connected { background: #4CAF50; }
    .disconnected { background: #f44336; }
    .main-tabs { display: flex; gap: 10px; padding: 14px 20px 10px; flex-wrap: wrap; }
    .main-tab-button { background: #e1e5ef; border: none; border-radius: 20px; padding: 8px 18px; font-weight: 600; cursor: pointer; transition: transform .12s ease, box-shadow .16s ease, background-color .16s ease; }
    .main-tab-button:hover { transform: translateY(-1px); box-shadow: 0 6px 14px rgba(15,23,42,0.10); }
    .main-tab-button:active { transform: translateY(0) scale(0.985); }
    .main-tab-button.active { background: #1f8ef1; color: #fff; }
    .main-tab-content { display: none; padding: 0 20px 20px; }
    .main-tab-content.active { display: block; }
    .grid { display: grid; grid-template-columns: repeat(8, minmax(0, 1fr)); gap: 12px; }
    .card { background: #fff; border-radius: 12px; padding: 16px; border: 2px solid transparent; box-shadow: 0 2px 8px rgba(0,0,0,0.08); cursor: pointer; transition: transform .12s ease, box-shadow .12s ease; }
    .card:hover { transform: translateY(-2px); box-shadow: 0 8px 18px rgba(0,0,0,0.12); }
    .card.active { border-color: #4CAF50; }
    .card.disconnected { border-color: #f44336; }
    .card.maintenance { border-color: #FF9800; }
    .card h3 { margin: 0 0 10px; font-size: 1.05rem; border-bottom: 1px solid #eee; padding-bottom: 8px; }
    .card p { margin: 6px 0; font-size: 0.9rem; }
    .panel { margin-top: 14px; background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
    .panel h3 { margin: 0 0 6px; }
    .muted { color: #666; font-size: 0.9rem; }
    .placeholder { border: 1px dashed #d9d9d9; border-radius: 10px; padding: 14px; color: #777; background: #fafafa; margin-top: 12px; }
    .table-wrap { margin-top: 12px; border: 1px solid #dbe4f0; border-radius: 12px; overflow: auto; background: #fff; }
    .data-table { width: 100%; border-collapse: collapse; min-width: 920px; }
    .data-table th, .data-table td { padding: 10px 12px; border-bottom: 1px solid #edf2f7; text-align: left; font-size: 0.86rem; vertical-align: top; }
    .data-table th { background: #f8fafc; color: #334155; font-weight: 700; position: sticky; top: 0; z-index: 1; }
    .data-table tr:hover td { background: #f8fbff; }
    .table-actions { display: flex; gap: 8px; }
    .mini-btn { border: 1px solid #cbd5e1; background: #fff; color: #1f2937; border-radius: 8px; padding: 6px 10px; font-size: 0.82rem; cursor: pointer; transition: transform .12s ease, box-shadow .16s ease, background-color .16s ease; }
    .mini-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 12px rgba(15,23,42,0.08); }
    .mini-btn:active { transform: translateY(0) scale(0.985); }
    .mini-btn.primary { background: #eff6ff; border-color: #bfdbfe; color: #1d4ed8; }
    .finished-wrap { margin-top: 12px; display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 14px; }
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
    .overlay-card { width: min(900px, calc(100vw - 160px)); background: #f4f5f7; border: 1px solid #cfd4dc; border-radius: 20px; box-shadow: 0 22px 56px rgba(15, 23, 42, 0.20); position: relative; }
    .overlay-head { padding: 18px 24px 14px; border-bottom: 1px solid #d7dbe1; display: flex; align-items: center; justify-content: space-between; }
    .overlay-title { font-weight: 800; font-size: 1.08rem; color: #1d273c; letter-spacing: .01em; }
    .overlay-close { border: 1px solid #cfd4dc; background: #dde1e7; color: #2d3342; border-radius: 14px; width: 44px; height: 44px; padding: 0; cursor: pointer; font-size: 0; position: relative; }
    .overlay-close::before { content: "×"; font-size: 22px; line-height: 1; position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; }
    .overlay-body { padding: 10px 18px 8px; display: grid; gap: 6px; }
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
    .overlay-actions { padding: 10px 18px 14px; border-top: 1px solid #d7dbe1; display: flex; justify-content: flex-end; gap: 10px; }
    .btn-secondary { border: 1px solid #c7cdd8; background: #f3f4f6; color: #202737; border-radius: 14px; padding: 9px 20px; cursor: pointer; font-size: 0.94rem; transition: transform .12s ease, box-shadow .16s ease, background-color .16s ease; }
    .btn-secondary:hover { background: #f8f9fb; transform: translateY(-1px); box-shadow: 0 8px 18px rgba(15,23,42,0.08); }
    .btn-secondary:active { transform: translateY(0) scale(0.985); }
    .btn-primary { border: none; background: linear-gradient(180deg, #3961dc 0%, #2d52cb 100%); color: #fff; border-radius: 14px; padding: 9px 20px; cursor: pointer; font-size: 0.94rem; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.10); transition: transform .12s ease, box-shadow .16s ease, filter .16s ease; }
    .btn-primary:hover { transform: translateY(-1px); box-shadow: 0 10px 22px rgba(45,82,203,0.28), inset 0 0 0 1px rgba(255,255,255,0.10); filter: brightness(1.03); }
    .btn-primary:active { transform: translateY(0) scale(0.985); }
    .review-slide-status { font-size: 0.92rem; color: #4b5567; font-weight: 700; margin: 0 0 8px; }
    .review-slide-arrow { border: 1px solid rgba(199, 207, 219, 0.95); background: rgba(242,245,249,0.96); border-radius: 999px; width: 42px; height: 42px; cursor: pointer; font-size: 18px; box-shadow: 0 8px 22px rgba(15,23,42,0.11); color: #2f3a4d; transition: box-shadow .16s ease, background-color .16s ease, opacity .16s ease; }
    .review-slide-arrow:hover:not(:disabled) { box-shadow: 0 10px 22px rgba(15,23,42,0.13); background: rgba(248,250,252,0.98); }
    .review-slide-arrow:active:not(:disabled) { box-shadow: 0 7px 16px rgba(15,23,42,0.12); }
    .review-slide-arrow:disabled { opacity: 0.45; cursor: not-allowed; }
    .review-edge-arrow { position: absolute; top: 50%; transform: translateY(-50%); z-index: 5; }
    .review-edge-arrow.left { left: -54px; }
    .review-edge-arrow.right { right: -54px; }
    .review-subslide { display: none; animation: reviewSlideIn .16s ease; }
    .review-subslide.active { display: block; }
    #overlayReviewStep { padding: 0; width: min(690px, 100%); margin: 0 auto; }
    #overlayReviewStep .overlay-row { grid-template-columns: 190px 1fr; }
    #overlayReviewStep .overlay-row input[readonly] { background: #fff; }
    #overlayReviewStep .overlay-row textarea[readonly] { background: #fff; }
    .review-panel {
      background: #f7f8fb;
      border: 1px solid #d0d5de;
      border-radius: 16px;
      overflow: hidden;
      margin-bottom: 10px;
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
      padding: 10px 12px;
      color: #1f2937;
      font-size: 0.94rem;
      line-height: 1.32;
    }
    .review-line-list { margin: 0; padding-left: 24px; display: grid; gap: 6px; }
    .review-line-list li { font-size: 0.92rem; color: #1f2937; }
    .review-inline-metrics { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
    .review-inline-metrics .dot { color: #8b93a1; }
    .review-inline-metrics .reject-emph { color: #d63b45; font-weight: 700; }
    .review-form-card { background: #f7f8fb; border: 1px solid #d0d5de; border-radius: 16px; padding: 10px; width: min(690px, 100%); margin: 0 auto; }
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
    @keyframes reviewSlideIn { from { opacity: .45; transform: translateX(6px); } to { opacity: 1; transform: translateX(0); } }
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
    @media (max-width: 900px) { .machine-detail-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 1400px) { .grid { grid-template-columns: repeat(6, minmax(0, 1fr)); } }
    @media (max-width: 1100px) { .grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
    @media (max-width: 1100px) { .diagnostics { grid-template-columns: 48px 48px 48px repeat(2, minmax(180px, 1fr)); } }
    @media (max-width: 768px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .finished-wrap { grid-template-columns: 1fr; } .finished-grid { grid-template-columns: 1fr; } .overlay-row { grid-template-columns: 1fr; } .main-tab-content { padding: 0 12px 12px; } .main-tabs { padding: 12px; } .diagnostics { padding: 8px 10px; grid-template-columns: 48px 48px 48px 1fr; gap: 6px; } .machine-detail-grid { grid-template-columns: 1fr; } .overlay-card { width: calc(100vw - 18px); border-radius: 16px; } .review-edge-arrow.left { left: 8px; } .review-edge-arrow.right { right: 8px; } #overlayReviewStep, .review-form-card { width: 100%; } .people-role-row { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="diagnostics">
    <button id="serverSettingsBtn" class="server-menu-btn" type="button" aria-label="Open server settings">
      <div class="server-menu-icon"><span></span><span></span><span></span></div>
    </button>
    <button id="dailyRolesBtn" class="server-menu-btn" type="button" aria-label="Open people roles">
      <div class="person-menu-icon"></div>
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
    <button class="main-tab-button" data-target="finishedJobsTab">Finished Jobs</button>
    <button class="main-tab-button" data-target="archivedJobsTab">Archived Jobs</button>
    <button class="main-tab-button" data-target="pdrTab">PDR Reports</button>
  </div>

  <div id="machinesTab" class="main-tab-content active">
    <div class="grid" id="machineGrid"></div>
  </div>

  <div id="jobQueueTab" class="main-tab-content">
    <div class="panel">
      <h3>Job Queue Map</h3>
      <div class="muted">UI shell ready. Queue data wiring can be added next.</div>
      <div class="placeholder">Queue map placeholder</div>
    </div>
    <div class="panel">
      <h3>Auto-Assign Job</h3>
      <div class="placeholder">Form placeholder</div>
    </div>
  </div>

  <div id="finishedJobsTab" class="main-tab-content">
    <div class="panel">
      <h3>Finished Job Confirmation</h3>
      <div class="muted">Stored from Finish Job QR scans (server JSON-backed).</div>
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
      <button id="overlayReviewPrevBtn" class="review-slide-arrow review-edge-arrow left" type="button" style="display:none;">&#8592;</button>
      <button id="overlayReviewNextBtn" class="review-slide-arrow review-edge-arrow right" type="button" style="display:none;">&#8594;</button>
      <div class="overlay-body">
        <div id="overlayReviewStep">
        <div id="overlayReviewSlideStatus" class="review-slide-status">Slide 1 / 4</div>
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
            <div class="review-panel-title">Raw Materials Consumption</div>
            <div class="review-panel-body" id="overlayRawConsumptionDisplay"></div>
          </div>
          <div class="review-panel">
            <div class="review-panel-title">Raw Materials / Cycle</div>
            <div class="review-panel-body" id="overlayRawCycleSummaryDisplay"></div>
          </div>
          <textarea id="overlayRawConsumption" readonly style="display:none;"></textarea>
          <textarea id="overlayRawCycleSummary" readonly style="display:none;"></textarea>
        </div>
        <div id="reviewSubslide3" class="review-subslide">
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
        <div id="reviewSubslide4" class="review-subslide">
          <div class="review-form-card">
          <div class="overlay-row" style="display:none;"><label>Scan QR Input</label><input id="overlayReviewerScanInput" type="text" placeholder="Click 'Open QR Field' then scan..." style="display:none;" /></div>
          <div class="overlay-row"><label>Reviewer (Supervisor/QC QR)</label><input id="overlayReviewerBadge" type="text" placeholder="Scan supervisor/QC QR badge..." /></div>
          <div class="overlay-row"><label>Remarks</label><textarea id="overlayReviewRemarks" placeholder="Remarks required..."></textarea></div>
          <div class="overlay-row"><label>Decision</label><select id="overlayReviewAction"><option value="approve">Approved</option><option value="disapprove">Not Approved</option></select></div>
          <div class="overlay-row"><label>QR Scan Helper</label><button id="overlayOpenScanFieldBtn" class="btn-secondary" type="button">Open QR Field</button></div>
          <div id="overlayDisapproveFields" style="display:none;">
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
        <button id="machineDetailCloseBtn" class="overlay-close" type="button">Close</button>
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
                </select>
              </div>
              <div class="settings-note">Theme setting is saved on the server and can be used for future dashboard styling variants.</div>
            </div>
          </div>
          <div id="settingsPageApi" class="settings-page">
            <div class="settings-form">
              <div class="settings-row">
                <label>QR Print API Base URL</label>
                <input id="settingsQrApiBaseUrl" type="text" placeholder="http://192.168.1.149:5000" />
              </div>
              <div class="settings-note">This is used by Request Print (`/api/qrgen/pending-request`) forwarding to your QR system.</div>
              <div class="settings-actions">
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
            <label>Scan QR (Supervisor or QC)</label>
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
  const dailyRolesBtn = document.getElementById("dailyRolesBtn");
  const profileCreatorBtn = document.getElementById("profileCreatorBtn");
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
  const finishedJobsList = document.getElementById("finishedJobsList");
  const archivedJobsTableWrap = document.getElementById("archivedJobsTableWrap");
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
  const overlayReviewSlideStatus = document.getElementById("overlayReviewSlideStatus");
  const overlayReviewPrevBtn = document.getElementById("overlayReviewPrevBtn");
  const overlayReviewNextBtn = document.getElementById("overlayReviewNextBtn");
  const reviewSubslide1 = document.getElementById("reviewSubslide1");
  const reviewSubslide2 = document.getElementById("reviewSubslide2");
  const reviewSubslide3 = document.getElementById("reviewSubslide3");
  const reviewSubslide4 = document.getElementById("reviewSubslide4");
  const overlayProductSelect = document.getElementById("overlayProductSelect");
  const overlayProductSuggest = document.getElementById("overlayProductSuggest");
  const overlayQrPayload = document.getElementById("overlayQrPayload");
  const overlayPoNumber = document.getElementById("overlayPoNumber");
  const overlayQty = document.getElementById("overlayQty");
  const overlayIndex = document.getElementById("overlayIndex");
  const overlayTotal = document.getElementById("overlayTotal");
  const overlayLotNumber = document.getElementById("overlayLotNumber");
  const machineDetailOverlay = document.getElementById("machineDetailOverlay");
  const machineDetailCloseBtn = document.getElementById("machineDetailCloseBtn");
  const machineDetailTitle = document.getElementById("machineDetailTitle");
  const machineDetailBody = document.getElementById("machineDetailBody");
  const qrScanCaptureOverlay = document.getElementById("qrScanCaptureOverlay");
  const qrScanCaptureInput = document.getElementById("qrScanCaptureInput");
  const qrScanCaptureCancelBtn = document.getElementById("qrScanCaptureCancelBtn");
  const MACHINE_NAME_MAP = {
    "M00001": "IMM 301",
    "M00002": "IMM 302",
    "M00004": "IMM 303",
    "M00005": "IMM 304",
    "M00006": "IMM 305",
    "M00007": "IMM 306",
    "M00008": "IMM 307",
    "M00009": "IMM 308",
    "M00010": "IMM 309",
    "M00011": "IMM 310",
    "M00012": "IMM 311",
    "M00013": "IMM 312",
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
  let finishedJobsState = [];
  let archivedJobsState = [];
  let productItems = [];
  let activeJobRow = null;
  let productsHydrated = false;
  let productSuggestionItems = [];
  let productSuggestionIndex = -1;
  const PRODUCT_SUGGEST_LIMIT = 8;
  let generatedQrState = {
    jobKey: "",
    payload: "",
    qty: "",
    index: "",
    total: "",
    lotNumber: "",
  };
  let overlayReviewSavedApproved = false;
  let reviewSlideIndex = 0;
  let serverSettingsState = { theme: "Default", qrgen_base_url: "" };
  let dailyRolesState = {};
  let settingsProfilesState = [];

  function esc(s){ return (s ?? "").toString().replaceAll("&","&amp;").replaceAll("<","&lt;"); }
  function escJson(v){
    try { return esc(JSON.stringify(v ?? {}, null, 2)); } catch { return esc(String(v ?? "")); }
  }

  function statusClass(lastSeenUtc, activeTtlSeconds = 30){
    if(!lastSeenUtc) return "disconnected";
    const seen = new Date(lastSeenUtc).getTime();
    if(Number.isNaN(seen)) return "disconnected";
    const ageSec = (Date.now() - seen) / 1000;
    return ageSec <= Number(activeTtlSeconds || 30) ? "active" : "disconnected";
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

  function openMachineDetail(session){
    if(!session) return;
    const activeTtlSeconds = Number((latestState && latestState.active_ttl_seconds) || 30);
    const status = statusClass(session.last_seen_utc, activeTtlSeconds).toUpperCase();
    const totalGood = Number(session.good_total || 0) + Number(session.butal_total || 0);
    const job = extractJobRecord(session) || {};
    const rejectBreakdown = (session && typeof session.reject_breakdown === "object" && session.reject_breakdown) || {};
    const rejectRows = Object.entries(rejectBreakdown).sort((a,b) => String(a[0]).localeCompare(String(b[0])));
    const rawScans = Array.isArray(session.raw_material_scans) ? session.raw_material_scans : [];
    const rawLogs = Array.isArray(session.raw_material_logs) ? session.raw_material_logs : [];
    const rawConsumptionHtml = rawLogs.length
      ? `<ol class="machine-detail-list">${rawLogs.map(x => `<li>${esc((x && (x.material || x.code || x.value)) || "-")} | qty=${esc((x && x.qty) ?? 0)}</li>`).join("")}</ol>`
      : `<div class="machine-detail-empty">No raw material consumption records.</div>`;
    const rejectHtml = rejectRows.length
      ? `<ol class="machine-detail-list">${rejectRows.map(([k,v]) => `<li>${esc(k)} = ${esc(v)}</li>`).join("")}</ol>`
      : `<div class="machine-detail-empty">No reject details recorded.</div>`;

    machineDetailTitle.textContent = `${session.machine_name || session.machine_code || "Machine"} Details`;
    machineDetailBody.innerHTML = `
      <div class="machine-detail-section">
        <h4>Overview</h4>
        <div class="machine-detail-grid">
          ${detailItem("Machine", session.machine_code || "-")}
          ${detailItem("Machine Name", session.machine_name || "-")}
          ${detailItem("Status", status)}
          ${detailItem("Client", session.client_id || "-")}
          ${detailItem("Job Code", session.job_code || "-")}
          ${detailItem("Job Name", session.job_name || "-")}
          ${detailItem("Operator", session.operator_id || "-")}
          ${detailItem("Last Seen", fmtDateLocal(session.last_seen_utc))}
          ${detailItem("Last Event", session.last_event || "-")}
        </div>
      </div>
      <div class="machine-detail-section">
        <h4>Production Counters</h4>
        <div class="machine-detail-grid">
          ${detailItem("Pack", Number(session.pack_total || 0))}
          ${detailItem("Good", Number(session.good_total || 0))}
          ${detailItem("Butal", Number(session.butal_total || 0))}
          ${detailItem("Reject", Number(session.reject_total || 0))}
          ${detailItem("Total Good", totalGood)}
          ${detailItem("Start Up Reject", Number(session.startup_reject_total || 0))}
          ${detailItem("Raw Sacks Count", Number(session.raw_sacks_count || 0))}
          ${detailItem("Cycle Time", session.cycle_time_current || "-")}
          ${detailItem("Downtime Active", session.downtime_active ? "YES" : "NO")}
        </div>
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
        <h4>Raw Materials (Scanned IDs)</h4>
        ${rawScans.length ? `<div class="machine-detail-code">${esc(rawScans.join("\\n"))}</div>` : `<div class="machine-detail-empty">No raw materials scanned.</div>`}
      </div>
      <div class="machine-detail-section">
        <h4>Raw Materials Consumption</h4>
        ${rawConsumptionHtml}
      </div>
      <div class="machine-detail-section">
        <h4>Job Details Payload</h4>
        <div class="machine-detail-grid">
          ${detailItem("Job Ref", job.ref_no || job.reference || job.id || "-")}
          ${detailItem("Product ID", job.product_id || "-")}
          ${detailItem("Mold", job.custom_05 || "-")}
          ${detailItem("Color", job.custom_06 || "-")}
          ${detailItem("System Code", job.custom_09 || "-")}
          ${detailItem("Cavities", job.custom_11 || "-")}
        </div>
        <div class="machine-detail-code">${escJson(session.job_payload || {})}</div>
      </div>
    `;
    machineDetailOverlay.classList.add("active");
  }

  function closeMachineDetail(){
    machineDetailOverlay.classList.remove("active");
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

  async function loadServerSettingsUi(){
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
      if(settingsThemeSelect) settingsThemeSelect.value = serverSettingsState.theme;
      if(settingsQrApiBaseUrl) settingsQrApiBaseUrl.value = serverSettingsState.qrgen_base_url;
    } catch {}
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
    overlayReviewStep.style.display = isReview ? "" : "none";
    overlayQrStep.style.display = isReview ? "none" : "";
    overlayReviewSubmitBtn.style.display = isReview ? "" : "none";
    overlayReviewContinueBtn.style.display = isReview ? "" : "none";
    overlayBackToReviewBtn.style.display = isReview ? "none" : "";
    overlayGenerateBtn.style.display = isReview ? "none" : "";
    overlayRequestBtn.style.display = isReview ? "none" : "";
    syncReviewSubslides();
  }

  function syncReviewSubslides(){
    const slides = [reviewSubslide1, reviewSubslide2, reviewSubslide3, reviewSubslide4];
    const total = slides.length;
    reviewSlideIndex = Math.max(0, Math.min(total - 1, Number(reviewSlideIndex || 0)));
    slides.forEach((el, idx) => {
      if(el) el.classList.toggle("active", idx === reviewSlideIndex);
    });
    if(overlayReviewSlideStatus){
      const labels = ["Job Summary", "Raw Mats / Cycle", "Downtime / Team", "Approval"];
      overlayReviewSlideStatus.textContent = `Slide ${reviewSlideIndex + 1} / ${total} - ${labels[reviewSlideIndex] || ""}`;
    }
    if(overlayReviewPrevBtn){
      overlayReviewPrevBtn.disabled = reviewSlideIndex <= 0;
      overlayReviewPrevBtn.style.display = overlayReviewStep.style.display === "none" ? "none" : "";
    }
    if(overlayReviewNextBtn){
      overlayReviewNextBtn.disabled = reviewSlideIndex >= total - 1;
      overlayReviewNextBtn.style.display = overlayReviewStep.style.display === "none" ? "none" : "";
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
      <span class="dot">•</span>
      <span>Total Good: ${esc(totalGood)}</span>
    `;
  }

  function renderFinishedJobs(rows){
    const items = Array.isArray(rows) ? rows : [];
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
      const rawText = rawLogs.length
        ? rawLogs.map((x, idx) => `${idx+1}. ${x.material || "-"} | qty=${x.qty || 0}`).join("\\n")
        : "No raw materials scanned.";
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
            <div><strong>Operator:</strong> ${esc(r.operator_id || "-")}</div>
            <div><strong>Pack Count:</strong> ${esc(r.pack_count ?? 0)}</div>
            <div><strong>Good:</strong> ${esc(r.good_total ?? 0)}</div>
            <div><strong>Butal:</strong> ${esc(r.butal_total ?? 0)}</div>
            <div><strong>Reject:</strong> ${esc(r.reject_total ?? 0)}</div>
            <div><strong>Total Good:</strong> ${esc(r.total_good ?? 0)}</div>
            <div><strong>Startup Reject:</strong> ${esc(r.startup_reject_total ?? 0)}</div>
            <div><strong>Raw Sacks:</strong> ${esc(r.raw_sacks_count ?? 0)}</div>
          </div>
          <div class="raw-list">${esc(rawText)}</div>
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
      reject_review_logs: row.reject_review_logs || [],
      job_payload: row.job_payload || {},
      last_seen_utc: row.printed_at_utc || row.finished_at_utc || "",
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
                <td>${esc(r.operator_id || "-")}</td>
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
    const title = activeJobRow
      ? `${activeJobRow.job_name || activeJobRow.job_code || "Finished Job"} | ${activeJobRow.machine_name || activeJobRow.machine_code || "-"}`
      : "Finished Job";
    const key = jobKeyOf(activeJobRow);
    overlayJobInfo.value = title;
    if(overlayReviewJobInfo) overlayReviewJobInfo.value = title;
    if(overlayReviewJobInfoDisplay) overlayReviewJobInfoDisplay.textContent = title;
    if(overlayReviewSummary) overlayReviewSummary.value = reviewSummaryText(activeJobRow);
    if(overlayReviewRejects) overlayReviewRejects.value = reviewRejectsText(activeJobRow);
    if(overlayReviewSummaryDisplay) overlayReviewSummaryDisplay.innerHTML = renderSummaryMetricsHtml(activeJobRow);
    if(overlayReviewRejectsDisplay) overlayReviewRejectsDisplay.innerHTML = renderBulletListHtml(reviewRejectsText(activeJobRow), "No reject details recorded.");
    const rawLogs = Array.isArray(activeJobRow?.raw_material_logs) ? activeJobRow.raw_material_logs : [];
    if(overlayRawConsumption) overlayRawConsumption.value = rawLogs.length
      ? rawLogs.map((x, i) => `${i + 1}. ${(x?.material || x?.code || x?.value || "-")} | qty=${x?.qty ?? 0}`).join("\\n")
      : "No raw material consumption records.";
    if(overlayRawConsumptionDisplay) overlayRawConsumptionDisplay.innerHTML = renderBulletListHtml(overlayRawConsumption?.value || "", "No raw material consumption records.");
    if(overlayRawCycleSummary) overlayRawCycleSummary.value = [
      `Raw Materials / Sacks Count: ${activeJobRow?.raw_sacks_count ?? 0}`,
      `Cycle Count (Pack): ${activeJobRow?.pack_count ?? 0}`,
      `Cycle Time: ${activeJobRow?.cycle_time_current || "-"}`,
    ].join("\\n");
    if(overlayRawCycleSummaryDisplay) overlayRawCycleSummaryDisplay.innerHTML = renderBulletListHtml(overlayRawCycleSummary?.value || "");
    if(overlayDowntimeSummary) overlayDowntimeSummary.value = [
      `Reason: ${activeJobRow?.downtime_reason_code || "-"} ${activeJobRow?.downtime_reason_text || ""}`.trim(),
      `Downtime: ${fmtDowntimeSeconds(activeJobRow?.downtime_last_seconds)}`,
    ].join("\\n");
    if(overlayDowntimeSummaryDisplay) overlayDowntimeSummaryDisplay.innerHTML = renderBulletListHtml(overlayDowntimeSummary?.value || "");
    if(overlayPeopleSummary) overlayPeopleSummary.value = [
      `Maintenance: ${activeJobRow?.maintenance_name || "-"}`,
      `Supervisor: ${activeJobRow?.supervisor_name || "-"}`,
      `QC: ${qcFromFinishedJob(activeJobRow)}`,
      `Start Up Reject: ${activeJobRow?.startup_reject_total ?? 0}`,
    ].join("\\n");
    if(overlayPeopleSummaryDisplay) overlayPeopleSummaryDisplay.innerHTML = renderBulletListHtml(overlayPeopleSummary?.value || "");
    if(overlayReviewerBadge) overlayReviewerBadge.value = "";
    if(overlayReviewerScanInput){
      overlayReviewerScanInput.value = "";
      overlayReviewerScanInput.style.display = "none";
    }
    if(overlayReviewRemarks) overlayReviewRemarks.value = "";
    if(overlayReviewAction) overlayReviewAction.value = "approve";
    if(overlayDisapproveFields) overlayDisapproveFields.style.display = "none";
    fillDisapproveFields(activeJobRow);
    reviewSlideIndex = 0;
    syncReviewSubslides();
    setOverlayStep("review");
    if(generatedQrState.jobKey === key){
      overlayQrPayload.value = generatedQrState.payload || "";
      overlayQty.value = generatedQrState.qty || "";
      overlayIndex.value = generatedQrState.index || "";
      overlayTotal.value = generatedQrState.total || "";
      overlayLotNumber.value = generatedQrState.lotNumber || "";
    } else {
      generatedQrState = { jobKey: key, payload: "", qty: "", index: "", total: "", lotNumber: "" };
      overlayQrPayload.value = "";
      overlayQty.value = "";
      overlayIndex.value = "";
      overlayTotal.value = "";
      overlayLotNumber.value = "";
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
    reviewSlideIndex = 0;
    syncReviewSubslides();
    setOverlayStep("review");
  }

  function render(state){
    latestState = state || { sessions: [] };
    timeEl.textContent = "Server UTC: " + state.server_time_utc;
    machineGrid.innerHTML = "";
    const sessions = state.sessions || [];
    const activeTtlSeconds = Number(state.active_ttl_seconds || 30);
    const byCode = Object.fromEntries(sessions.map(s => [String(s.machine_code || "").trim(), s]));
    const sessionCodes = sessions
      .map(s => String(s.machine_code || "").trim())
      .filter(Boolean);
    const allCodes = Array.from(new Set([...DEFAULT_MACHINE_CODES, ...sessionCodes])).sort();
    machineCountEl.textContent = String(allCodes.length);

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
        last_event: "No data yet",
        last_seen_utc: "",
      };
      const css = statusClass(s.last_seen_utc, activeTtlSeconds) || "disconnected";
      s.machine_name = s.machine_name || MACHINE_NAME_MAP[code] || code;
      const linkageJobs = Array.isArray(s.linkage_jobs) ? s.linkage_jobs : [];
      const hasLinkage = Boolean(s.linkage_enabled) && linkageJobs.length > 0;
      const card = document.createElement("div");
      card.className = `card ${css}`;
      const total = Number(s.good_total||0) + Number(s.butal_total||0);
      const jobLabel = s.job_name
        ? (s.job_code ? `${s.job_name} (${s.job_code})` : s.job_name)
        : (s.job_code || "No Job Set");
      const seenLabel = s.last_seen_utc ? new Date(s.last_seen_utc).toLocaleString() : "-";
      card.innerHTML = `
        ${hasLinkage ? `<div class="machine-linkage-flag">LINKED JOBS: ${esc(linkageJobs.length)}</div>` : ""}
        <h3>${esc(s.machine_name || s.machine_code)}</h3>
        <p>Machine: <strong>${esc(s.machine_code || code)}</strong></p>
        <p>Job: <strong>${esc(jobLabel)}</strong></p>
        <p>Operator: <strong>${esc(s.operator_id || "-")}</strong></p>
        <p>Client: <strong>${esc(s.client_id || "-")}</strong></p>
        <p>Status: <strong>${css.toUpperCase()}</strong></p>
        <p>Pack: <strong>${esc(s.pack_total)}</strong></p>
        <p>Good: <strong>${esc(s.good_total)}</strong></p>
        <p>Butal: <strong>${esc(s.butal_total)}</strong></p>
        <p>Reject: <strong>${esc(s.reject_total)}</strong></p>
        <p>Total: <strong>${esc(total)}</strong></p>
        <p class="muted">Last Seen: ${esc(seenLabel)}</p>
        <p class="muted">Last Event: ${esc(s.last_event || "-")}</p>
      `;
      card.addEventListener("click", () => openMachineDetail(s));
      machineGrid.appendChild(card);
    }
    renderFinishedJobs(state.finished_jobs || []);
    renderArchivedJobs(state.archived_jobs || []);
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

  if(serverSettingsBtn){
    serverSettingsBtn.addEventListener("click", async () => {
      await loadServerSettingsUi();
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
  if(profileCreatorBtn){
    profileCreatorBtn.addEventListener("click", () => {
      window.open("/profiles", "_blank");
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
  serverSettingsSaveBtn?.addEventListener("click", saveServerSettingsUi);

  finishedJobsList.addEventListener("click", async (ev) => {
    const btn = ev.target.closest(".approve-print-btn");
    if(!btn) return;
    const idx = Number(btn.getAttribute("data-row-index"));
    if(Number.isNaN(idx) || idx < 0) return;
    const sorted = [...(finishedJobsState || [])].reverse();
    const row = sorted[idx];
    if(!row) return;
    openApprovePrintOverlay(row);
    if(!productItems.length){
      loadProducts(false);
    }
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
  if(overlayReviewAction){
    overlayReviewAction.addEventListener("change", () => {
      if(overlayDisapproveFields){
        overlayDisapproveFields.style.display = overlayReviewAction.value === "disapprove" ? "" : "none";
      }
      if(overlayReviewAction.value === "disapprove" && reviewSlideIndex < 3){
        reviewSlideIndex = 3;
        syncReviewSubslides();
      }
    });
  }
  if(overlayReviewPrevBtn){
    overlayReviewPrevBtn.addEventListener("click", () => {
      reviewSlideIndex = Math.max(0, reviewSlideIndex - 1);
      syncReviewSubslides();
    });
  }
  if(overlayReviewNextBtn){
    overlayReviewNextBtn.addEventListener("click", () => {
      reviewSlideIndex = Math.min(3, reviewSlideIndex + 1);
      syncReviewSubslides();
    });
  }
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
  machineDetailCloseBtn.addEventListener("click", closeMachineDetail);
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
    if(!overlayReviewSavedApproved){
      overlayQrPayload.value = "Review approval is required before generating QR.";
      return;
    }
    const productId = resolveProductIdFromText(overlayProductSelect.value || "");
    if(!productId){
      overlayQrPayload.value = "Select a product first.";
      return;
    }
    const poNumber = (overlayPoNumber.value || "").trim();
    if(!poNumber){
      overlayQrPayload.value = "Provide PO Number first.";
      return;
    }
    const resp = await fetch("/api/raw-material-qr", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_id: productId,
        po_number: poNumber,
        finished_job: activeJobRow || {},
      }),
    });
    const out = await resp.json();
    const payloadText = out.qr_payload || out.error || "Failed to generate.";
    overlayQrPayload.value = payloadText;
    const parsed = out.parsed || {};
    overlayQty.value = parsed.qty || "";
    overlayIndex.value = parsed.index || "";
    overlayTotal.value = parsed.total || "";
    overlayLotNumber.value = parsed.lot_number || "";
    generatedQrState = {
      jobKey: jobKeyOf(activeJobRow),
      payload: payloadText,
      qty: overlayQty.value || "",
      index: overlayIndex.value || "",
      total: overlayTotal.value || "",
      lotNumber: overlayLotNumber.value || "",
    };
  });

  overlayRequestBtn.addEventListener("click", async () => {
    if(!overlayReviewSavedApproved){
      overlayQrPayload.value = "Review approval is required before requesting print.";
      return;
    }
    const product = resolveProductFromText(overlayProductSelect.value || "");
    if(!product){
      overlayQrPayload.value = "Select a product first.";
      return;
    }
    const quantity = (overlayQty.value || "").trim();
    const total = (overlayTotal.value || "").trim();
    const poNumber = (overlayPoNumber.value || "").trim();
    const lotNumber = (overlayLotNumber.value || "").trim();
    if(!quantity || !total || !poNumber || !lotNumber){
      overlayQrPayload.value = "Generate QR first so Quantity/Total/Lot/PO are complete.";
      return;
    }

    const productName = `[${(product.sku || "").toString().trim()}] ${(product.name || "").toString().trim()}`.trim();
    const requestPayload = {
      product_name: productName,
      quantity: quantity,
      total: total,
      po_number: poNumber,
      product_desc: (activeJobRow && (activeJobRow.job_name || activeJobRow.job_code)) || "",
      requested_at_ph: "",
      lot_number: lotNumber,
    };

    const resp = await fetch("/api/qrgen/pending-request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestPayload),
    });
    const out = await resp.json();
    if(out.ok){
      overlayQrPayload.value = `${overlayQrPayload.value}\n\nPrint request sent.`;
      try {
        const archiveResp = await fetch("/api/finished-jobs/archive", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            job_key: jobKeyOf(activeJobRow),
            qr_payload: overlayQrPayload.value || "",
            print_payload: requestPayload,
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
      overlayQrPayload.value = out.error || "Print request failed.";
    }
  });

  async function submitFinishedJobReview(actionMode){
    if(!activeJobRow) return;
    const reviewerBadge = (overlayReviewerBadge.value || "").trim();
    const remarks = (overlayReviewRemarks.value || "").trim();
    const action = actionMode === "continue" ? "approve" : (overlayReviewAction.value || "approve");
    if(!reviewerBadge){
      overlayReviewRemarks.value = remarks;
      alert("Reviewer QR / badge is required.");
      return;
    }
    if(!remarks){
      alert("Remarks are required.");
      return;
    }
    let changes = {};
    if(action === "disapprove"){
      let rejectBreakdown = {};
      try {
        rejectBreakdown = JSON.parse((editRejectBreakdown.value || "{}").trim() || "{}");
      } catch {
        alert("Reject Details JSON is invalid.");
        return;
      }
      changes = {
        pack_count: Number(editPackCount.value || 0),
        good_total: Number(editGoodTotal.value || 0),
        butal_total: Number(editButalTotal.value || 0),
        reject_total: Number(editRejectTotal.value || 0),
        total_good: Number(editTotalGood.value || 0),
        reject_breakdown: rejectBreakdown,
      };
    }
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
    overlayReviewSummary.value = reviewSummaryText(activeJobRow) + `\\n\\nStatus: ${activeJobRow.review_status || "-"}`;
    overlayReviewRejects.value = reviewRejectsText(activeJobRow);
    if(overlayReviewSummaryDisplay) overlayReviewSummaryDisplay.innerHTML = renderSummaryMetricsHtml(activeJobRow);
    if(overlayReviewRejectsDisplay) overlayReviewRejectsDisplay.innerHTML = renderBulletListHtml(overlayReviewRejects.value || "", "No reject details recorded.");
    fillDisapproveFields(activeJobRow);
    if(Array.isArray(latestState.finished_jobs)){
      const k = jobKeyOf(activeJobRow);
      latestState.finished_jobs = latestState.finished_jobs.map(x => jobKeyOf(x) === k ? activeJobRow : x);
      renderFinishedJobs(latestState.finished_jobs);
    }
    if(actionMode === "continue"){
      overlayReviewSavedApproved = true;
      setOverlayStep("qr");
    } else {
      overlayReviewSavedApproved = action === "approve";
      if(action === "approve"){
        alert("Approved and saved. You can now continue to QR.");
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
    body { margin: 0; font-family: Poppins, Segoe UI, sans-serif; background: #eef2f7; color: #1f2937; }
    .wrap { max-width: 980px; margin: 22px auto; padding: 0 14px; }
    .card { background: #fff; border: 1px solid #dbe4f0; border-radius: 16px; box-shadow: 0 10px 24px rgba(15,23,42,.08); overflow: hidden; }
    .head { padding: 16px 18px; border-bottom: 1px solid #e5e7eb; font-weight: 800; font-size: 1.05rem; }
    .body { padding: 16px 18px; display: grid; grid-template-columns: 1fr 380px; gap: 16px; }
    .form { display: grid; gap: 10px; }
    .row { display: grid; gap: 6px; }
    label { font-size: .86rem; font-weight: 700; color: #475569; }
    input, select { border: 1px solid #cbd5e1; border-radius: 10px; padding: 10px 12px; font: inherit; }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 6px; }
    button { border: none; border-radius: 12px; padding: 10px 14px; cursor: pointer; font-weight: 600; transition: transform .12s ease, box-shadow .16s ease; }
    button:hover { transform: translateY(-1px); box-shadow: 0 8px 18px rgba(15,23,42,.10); }
    button:active { transform: translateY(0) scale(.985); }
    .primary { background: #1d4ed8; color: #fff; }
    .secondary { background: #fff; color: #1f2937; border: 1px solid #cbd5e1; }
    .preview { border: 1px solid #dbe4f0; border-radius: 14px; background: #f8fafc; padding: 12px; }
    .preview h4 { margin: 0 0 8px; }
    .preview img { width: 100%; height: auto; border: 1px solid #dbe4f0; border-radius: 10px; background: #fff; }
    .mono { font-family: Consolas, monospace; font-size: .75rem; white-space: pre-wrap; word-break: break-all; margin-top: 8px; background:#fff; border:1px solid #e5e7eb; border-radius:10px; padding:8px; }
    .status { font-size: .85rem; color: #334155; min-height: 20px; }
    .table { margin-top: 14px; border: 1px solid #dbe4f0; border-radius: 12px; overflow: auto; background:#fff; }
    table { width: 100%; border-collapse: collapse; min-width: 720px; }
    th, td { border-bottom: 1px solid #edf2f7; padding: 8px 10px; text-align: left; font-size: .84rem; }
    th { background: #f8fafc; }
    .mini-btn { border: 1px solid #cbd5e1; background: #fff; color: #1f2937; border-radius: 10px; padding: 6px 9px; font-size: .78rem; font-weight: 600; cursor:pointer; }
    .mini-btn.primary { background: #1d4ed8; color: #fff; border-color: #1d4ed8; }
    .mini-btn.danger { background: #fff1f2; color: #be123c; border-color: #fecdd3; }
    .mini-actions { display:flex; gap:6px; flex-wrap:wrap; }
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


@APP.post("/api/profiles")
async def api_profiles_create(req: Request):
    global PROFILES
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
    global PROFILES
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
    global PROFILES
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
      "operator_id": "1000001",
      "event": { ... },   # e.g. {"type":"PACK","qty":6}
      "last_event": "PACK +6"
    }
    """
    data = await req.json()

    machine_code = str(data.get("machine_code", "")).strip()
    if not machine_code:
        return JSONResponse({"ok": False, "error": "machine_code required"}, status_code=400)

    sess = SESSIONS.get(machine_code)
    if sess is None:
        sess = MachineSession(
            client_id=str(data.get("client_id", "UNKNOWN")),
            machine_code=machine_code,
            machine_name=_machine_display_name(machine_code, data.get("machine_name", machine_code)),
            reject_breakdown={},
            raw_material_scans=[],
            raw_material_logs=[],
            job_payload={},
        )
        SESSIONS[machine_code] = sess

    # update common fields
    sess.client_id = str(data.get("client_id", sess.client_id))
    sess.machine_name = _machine_display_name(machine_code, data.get("machine_name", sess.machine_name))
    sess.job_code = data.get("job_code", sess.job_code)
    sess.job_name = data.get("job_name", sess.job_name)
    sess.operator_id = data.get("operator_id", sess.operator_id)
    sess.last_seen_utc = utc_now().isoformat()
    sess.last_event = str(data.get("last_event", sess.last_event))

    # apply event counters if provided
    ev = data.get("event") or {}
    ev_type = str(ev.get("type", "")).upper()
    if ev_type == "FINISH_JOB":
        finished_job = ev.get("finished_job")
        if isinstance(finished_job, dict):
            FINISHED_JOBS.append(finished_job)
            save_finished_jobs(FINISHED_JOBS)
        if machine_code in SESSIONS:
            del SESSIONS[machine_code]
    elif ev_type == "JOB_LINKAGE_SET":
        sess.linkage_enabled = True
        linked_code = str(ev.get("linked_job_code", "")).strip()
        linked_name = str(ev.get("linked_job_name", "")).strip()
        if linked_code or linked_name:
            rows = list(sess.linkage_jobs or [])
            rows.append({"job_code": linked_code, "job_name": linked_name})
            sess.linkage_jobs = rows
    elif ev_type in ("SESSION_SYNC", "HEARTBEAT"):
        snap = ev.get("session_snapshot")
        if isinstance(snap, dict):
            sess.machine_name = _machine_display_name(machine_code, snap.get("machine_name") or sess.machine_name or machine_code)
            sess.job_code = snap.get("job_code", sess.job_code)
            sess.job_name = snap.get("job_name", sess.job_name)
            sess.operator_id = snap.get("operator_id", sess.operator_id)
            sess.pack_total = int(snap.get("pack_count", sess.pack_total) or 0)
            sess.good_total = int(snap.get("good_total", sess.good_total) or 0)
            sess.butal_total = int(snap.get("butal_total", sess.butal_total) or 0)
            sess.reject_total = int(snap.get("reject_total", sess.reject_total) or 0)
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
            sess.cycle_time_current = snap.get("cycle_time_current", sess.cycle_time_current)
            if isinstance(snap.get("job_payload"), dict):
                sess.job_payload = dict(snap.get("job_payload") or {})
            sess.linkage_enabled = bool(snap.get("linkage_enabled", sess.linkage_enabled))
            if isinstance(snap.get("linkage_jobs"), list):
                sess.linkage_jobs = list(snap.get("linkage_jobs") or [])
    elif ev_type == "PACK":
        qty = int(ev.get("qty", 0) or 0)
        sess.pack_total += qty
        sess.good_total += qty
    elif ev_type == "BUTAL":
        sess.butal_total += int(ev.get("qty", 0) or 0)
    elif ev_type == "REJECT":
        sess.reject_total += int(ev.get("qty", 1) or 1)
        reason = str(ev.get("reason", "")).strip()
        if reason:
            sess.reject_breakdown[reason] = sess.reject_breakdown.get(reason, 0) + int(ev.get("qty", 1) or 1)

    await broadcast_state()
    return {"ok": True}


@APP.get("/api/finished-jobs")
def api_finished_jobs():
    return {"ok": True, "items": FINISHED_JOBS}


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
    global FINISHED_JOBS
    data = await req.json()
    job_key = str(data.get("job_key", "")).strip()
    action = str(data.get("action", "")).strip().lower()  # approve | disapprove
    remarks = str(data.get("remarks", "")).strip()
    reviewer_badge = str(data.get("reviewer_badge", "")).strip()
    changes = data.get("changes") if isinstance(data.get("changes"), dict) else {}

    if not job_key:
        return JSONResponse({"ok": False, "error": "job_key is required"}, status_code=400)
    if action not in ("approve", "disapprove"):
        return JSONResponse({"ok": False, "error": "action must be approve or disapprove"}, status_code=400)
    if not remarks:
        return JSONResponse({"ok": False, "error": "remarks is required"}, status_code=400)

    reviewer = _reviewer_from_badge(reviewer_badge)
    if reviewer is None:
        return JSONResponse({"ok": False, "error": "Invalid reviewer QR/badge. Supervisor or QC badge required."}, status_code=400)

    idx = _find_finished_job_index(FINISHED_JOBS, job_key)
    if idx < 0:
        return JSONResponse({"ok": False, "error": "Finished job not found"}, status_code=404)

    row = dict(FINISHED_JOBS[idx] or {})
    now_utc = utc_now().isoformat()
    row.setdefault("review_history", [])

    if action == "approve":
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
        })
    else:
        original_snapshot = {
            "pack_count": row.get("pack_count", 0),
            "good_total": row.get("good_total", 0),
            "butal_total": row.get("butal_total", 0),
            "reject_total": row.get("reject_total", 0),
            "total_good": row.get("total_good", 0),
            "reject_breakdown": dict(row.get("reject_breakdown") or {}),
        }
        int_fields = ("pack_count", "good_total", "butal_total", "reject_total", "startup_reject_total", "raw_sacks_count")
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

        row["changed_by"] = reviewer["name"]
        row["changed_by_code"] = reviewer["code"]
        row["changed_by_role"] = reviewer["role"]
        row["change_remarks"] = remarks
        row["changed_at_utc"] = now_utc
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

    FINISHED_JOBS[idx] = row
    save_finished_jobs(FINISHED_JOBS)
    await broadcast_state()
    return {"ok": True, "item": row}


@APP.post("/api/finished-jobs/archive")
async def api_finished_jobs_archive(req: Request):
    global FINISHED_JOBS, ARCHIVED_JOBS
    data = await req.json()
    job_key = str(data.get("job_key", "")).strip()
    print_payload = data.get("print_payload") if isinstance(data.get("print_payload"), dict) else {}
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
    if qr_payload:
        row["printed_qr_payload"] = qr_payload
    row["archive_status"] = "PRINTED_ARCHIVED"
    row.setdefault("review_history", [])
    row["review_history"].append({
        "action": "ARCHIVE_AFTER_PRINT",
        "timestamp_utc": now_utc,
    })

    ARCHIVED_JOBS.append(row)
    del FINISHED_JOBS[idx]
    save_archived_jobs(ARCHIVED_JOBS)
    save_finished_jobs(FINISHED_JOBS)
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
        "source_file": str(PRODUCT_SOURCE_FILE),
        "cache_file": str(PRODUCT_CACHE_FILE),
    }


@APP.post("/api/raw-material-qr")
async def api_raw_material_qr(req: Request):
    data = await req.json()
    product_id = str(data.get("product_id", "")).strip()
    po_number = str(data.get("po_number", "")).strip()
    if not product_id:
        return JSONResponse({"ok": False, "error": "product_id is required"}, status_code=400)
    if not po_number:
        return JSONResponse({"ok": False, "error": "po_number is required"}, status_code=400)
    payload = _build_raw_material_qr_value(product_id, po_number=po_number)
    product_meta = _lookup_product_meta(product_id)
    product_name = product_meta.get("name", "")
    product_sku = product_meta.get("sku", "")
    try:
        image_url = _qr_png_data_url(payload)
    except Exception:
        image_url = ""
    try:
        label_url = _label_png_data_url(
            payload,
            product_id=product_id,
            product_name=product_name,
            product_sku=product_sku,
            qty=1,
            index_value=1,
            total=1,
        )
    except Exception:
        label_url = image_url
    return {
        "ok": True,
        "qr_payload": payload,
        "qr_image_data_url": image_url,
        "label_image_data_url": label_url,
        "parsed": _parse_qr_segments(payload),
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

    if not product_name:
        return JSONResponse({"ok": False, "error": "product_name is required"}, status_code=400)
    if not quantity:
        return JSONResponse({"ok": False, "error": "quantity is required"}, status_code=400)
    if not total:
        return JSONResponse({"ok": False, "error": "total is required"}, status_code=400)
    if not po_number:
        return JSONResponse({"ok": False, "error": "po_number is required"}, status_code=400)

    outbound = {
        "product_name": product_name,
        "quantity": quantity,
        "total": total,
        "po_number": po_number,
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
