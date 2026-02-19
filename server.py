# server.py
from __future__ import annotations
import asyncio
import base64
import io
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib import request as urllib_request
from urllib.parse import urlencode
import qrcode
from PIL import Image, ImageDraw, ImageFont

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

APP = FastAPI(title="Machine Dashboard Server")

ACTIVE_TTL_SECONDS = 30  # client considered offline after 30s no heartbeat/event
FINISHED_JOBS_FILE = Path(__file__).resolve().parent / "Database" / "finished_jobs_server.json"
CLIENT_FINISHED_JOBS_FILE = Path(__file__).resolve().parent / "Database" / "finished_jobs_client.json"
PRODUCT_SOURCE_FILE = Path(__file__).resolve().parent / "Product_ID.json"
PRODUCT_CACHE_FILE = Path(__file__).resolve().parent / "Database" / "product_catalog_cache.json"
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


@dataclass
class MachineSession:
    client_id: str
    machine_code: str
    machine_name: str
    job_code: Optional[str] = None
    job_name: Optional[str] = None
    operator_id: Optional[str] = None
    pack_total: int = 0
    butal_total: int = 0
    reject_total: int = 0
    reject_breakdown: Dict[str, int] = None
    last_event: str = ""
    last_seen_utc: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["reject_breakdown"] = d["reject_breakdown"] or {}
        return d


SESSIONS: Dict[str, MachineSession] = {}  # key = machine_code
WS_CLIENTS: List[WebSocket] = []


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


def _zpad_digits(value: Any, width: int) -> str:
    d = re.sub(r"\D+", "", str(value or ""))
    if len(d) > width:
        d = d[-width:]
    return d.zfill(width)


def _build_raw_material_qr_value(product_id: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    p = "P" + _zpad_digits(product_id, WIDTH_P)
    q = "Q" + _zpad_digits("1", WIDTH_Q)
    i = "I" + _zpad_digits("1", WIDTH_I)
    t = "T" + _zpad_digits("1", WIDTH_T)
    l = "L" + f"{stamp}-000000000000"
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
    l_seg = _extract_seg(qr_value, "L", WIDTH_L)
    yy = ""
    mm = ""
    l_trim = l_seg.lstrip("0")
    if len(l_trim) >= 8 and l_trim[:8].isdigit():
        yyyy = l_trim[0:4]
        mm = l_trim[4:6]
        yy = yyyy[2:4]
    return {
        "product": _strip_leading_zeros(p_digits),
        "qty": _strip_leading_zeros(q_digits),
        "index": _strip_leading_zeros(i_digits),
        "yy": yy,
        "mm": mm,
    }


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_w: int, max_h: int, start: int, min_px: int = 10) -> ImageFont.ImageFont:
    for px in range(start, min_px - 1, -1):
        try:
            f = ImageFont.truetype("cour.ttf", px)
        except Exception:
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


def _load_json_object(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            obj = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    return {}


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

        products_url = f"{base_url}/products?{urlencode({'page': 1, 'perPage': 10000, 'includeInactive': 0})}"
        req_prod = urllib_request.Request(url=products_url, method="GET")
        req_prod.add_header("Authorization", f"Bearer {token}")
        with urllib_request.urlopen(req_prod, timeout=12) as resp:
            prod_raw = resp.read().decode("utf-8", errors="ignore")
        try:
            prod_parsed = json.loads(prod_raw)
        except Exception:
            return []
        return _extract_products_from_payload(prod_parsed)

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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def prune_dead_sessions():
    cutoff = utc_now() - timedelta(seconds=ACTIVE_TTL_SECONDS)
    dead = []
    for k, s in SESSIONS.items():
        try:
            t = datetime.fromisoformat(s.last_seen_utc)
        except Exception:
            t = utc_now()
        if t < cutoff:
            dead.append(k)
    for k in dead:
        del SESSIONS[k]


async def broadcast_state():
    prune_dead_sessions()
    payload = {
        "type": "STATE",
        "active_ttl_seconds": ACTIVE_TTL_SECONDS,
        "sessions": [s.to_dict() for s in SESSIONS.values()],
        "finished_jobs": FINISHED_JOBS,
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
    .diagnostics { padding: 16px 20px; background: #e9ecef; border-bottom: 1px solid #d9d9d9; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
    .diag-item { background: #fff; border-radius: 10px; padding: 10px 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); font-size: 13px; }
    .diag-item .value { font-weight: 700; margin-top: 6px; }
    .status-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
    .connected { background: #4CAF50; }
    .disconnected { background: #f44336; }
    .main-tabs { display: flex; gap: 10px; padding: 14px 20px 10px; flex-wrap: wrap; }
    .main-tab-button { background: #e1e5ef; border: none; border-radius: 20px; padding: 8px 18px; font-weight: 600; cursor: pointer; }
    .main-tab-button.active { background: #1f8ef1; color: #fff; }
    .main-tab-content { display: none; padding: 0 20px 20px; }
    .main-tab-content.active { display: block; }
    .grid { display: grid; grid-template-columns: repeat(8, minmax(0, 1fr)); gap: 12px; }
    .card { background: #fff; border-radius: 12px; padding: 16px; border: 2px solid transparent; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
    .card.active { border-color: #4CAF50; }
    .card.stopped { border-color: #f44336; }
    .card.maintenance { border-color: #FF9800; }
    .card h3 { margin: 0 0 10px; font-size: 1.05rem; border-bottom: 1px solid #eee; padding-bottom: 8px; }
    .card p { margin: 6px 0; font-size: 0.9rem; }
    .panel { margin-top: 14px; background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
    .panel h3 { margin: 0 0 6px; }
    .muted { color: #666; font-size: 0.9rem; }
    .placeholder { border: 1px dashed #d9d9d9; border-radius: 10px; padding: 14px; color: #777; background: #fafafa; margin-top: 12px; }
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
      cursor: default;
      opacity: 0.95;
    }
    .overlay-backdrop { position: fixed; inset: 0; background: rgba(15,23,42,0.42); display: none; align-items: center; justify-content: center; padding: 14px; z-index: 999; }
    .overlay-backdrop.active { display: flex; }
    .overlay-card { width: min(720px, 100%); background: #fff; border: 1px solid #dbe4f0; border-radius: 14px; box-shadow: 0 20px 42px rgba(2, 8, 23, 0.24); }
    .overlay-head { padding: 12px 14px; border-bottom: 1px solid #e5e7eb; display: flex; align-items: center; justify-content: space-between; }
    .overlay-title { font-weight: 700; color: #0f172a; }
    .overlay-close { border: none; background: #f1f5f9; border-radius: 8px; padding: 6px 10px; cursor: pointer; }
    .overlay-body { padding: 14px; display: grid; gap: 10px; }
    .overlay-row { display: grid; grid-template-columns: 140px 1fr; gap: 10px; align-items: center; }
    .overlay-row > * { min-width: 0; }
    .overlay-row select, .overlay-row input, .overlay-row textarea { width: 100%; max-width: 100%; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 10px; padding: 8px 10px; font-family: inherit; font-size: 0.9rem; }
    .overlay-row textarea { min-height: 80px; resize: vertical; }
    #overlayQrPayload { font-family: "Consolas", "Courier New", monospace; font-size: 0.78rem; line-height: 1.35; overflow-wrap: anywhere; word-break: break-all; }
    .overlay-preview { display: flex; align-items: center; justify-content: center; background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 10px; padding: 10px; min-height: 170px; }
    .overlay-preview img { width: 320px; max-width: 100%; height: auto; object-fit: contain; background: #fff; border: 1px solid #dbe4f0; border-radius: 8px; }
    .overlay-actions { padding: 12px 14px; border-top: 1px solid #e5e7eb; display: flex; justify-content: flex-end; gap: 8px; }
    .btn-secondary { border: 1px solid #cbd5e1; background: #fff; border-radius: 10px; padding: 8px 12px; cursor: pointer; }
    .btn-primary { border: none; background: #1d4ed8; color: #fff; border-radius: 10px; padding: 8px 12px; cursor: pointer; }
    @media (max-width: 1400px) { .grid { grid-template-columns: repeat(6, minmax(0, 1fr)); } }
    @media (max-width: 1100px) { .grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
    @media (max-width: 768px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .finished-wrap { grid-template-columns: 1fr; } .finished-grid { grid-template-columns: 1fr; } .overlay-row { grid-template-columns: 1fr; } .main-tab-content { padding: 0 12px 12px; } .main-tabs { padding: 12px; } .diagnostics { padding: 12px; } }
  </style>
</head>
<body>
  <div class="diagnostics">
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
      <div class="placeholder">Archived jobs list placeholder</div>
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
        <div class="overlay-row">
          <label>Finished Job</label>
          <input id="overlayJobInfo" type="text" readonly />
        </div>
        <div class="overlay-row">
          <label>Product Name</label>
          <input id="overlayProductSelect" type="text" list="overlayProductList" placeholder="Select or type product name..." />
          <datalist id="overlayProductList"></datalist>
        </div>
        <div class="overlay-row">
          <label>QR Payload</label>
          <textarea id="overlayQrPayload" readonly></textarea>
        </div>
        <div class="overlay-row">
          <label>QR Preview</label>
          <div class="overlay-preview">
            <img id="overlayQrPreview" alt="QR preview" />
          </div>
        </div>
      </div>
      <div class="overlay-actions">
        <button id="overlayCancelBtn" class="btn-secondary" type="button">Cancel</button>
        <button id="overlayGenerateBtn" class="btn-primary" type="button">Generate QR Payload</button>
      </div>
    </div>
  </div>

<script>
  const clientStatus = document.getElementById("client-status");
  const timeEl = document.getElementById("time");
  const lastMessageEl = document.getElementById("last-message");
  const machineCountEl = document.getElementById("machine-count");
  const machineGrid = document.getElementById("machineGrid");
  const finishedJobsList = document.getElementById("finishedJobsList");
  const approvePrintOverlay = document.getElementById("approvePrintOverlay");
  const overlayCloseBtn = document.getElementById("overlayCloseBtn");
  const overlayCancelBtn = document.getElementById("overlayCancelBtn");
  const overlayGenerateBtn = document.getElementById("overlayGenerateBtn");
  const overlayJobInfo = document.getElementById("overlayJobInfo");
  const overlayProductSelect = document.getElementById("overlayProductSelect");
  const overlayProductList = document.getElementById("overlayProductList");
  const overlayQrPayload = document.getElementById("overlayQrPayload");
  const overlayQrPreview = document.getElementById("overlayQrPreview");
  const MACHINE_CODES = Array.from({length: 23}, (_, i) => `M${String(i + 1).padStart(5, "0")}`);
  let finishedJobsState = [];
  let productItems = [];
  let activeJobRow = null;

  function esc(s){ return (s ?? "").toString().replaceAll("&","&amp;").replaceAll("<","&lt;"); }

  function statusClass(lastSeenUtc){
    if(!lastSeenUtc) return "stopped";
    const seen = new Date(lastSeenUtc).getTime();
    if(Number.isNaN(seen)) return "stopped";
    const ageSec = (Date.now() - seen) / 1000;
    return ageSec <= 30 ? "active" : "stopped";
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
    const t = (text || "").trim();
    if(!t) return "";
    const exact = productItems.find(
      p =>
        `${p.sku || ""} - ${p.name}` === t
        || `${p.name}` === t
        || `${p.sku || ""}` === t
    );
    if(exact) return String(exact.id || "");
    const low = t.toLowerCase();
    const candidates = productItems
      .filter(p => `${(p.name||"").toString().toLowerCase()} ${(p.sku||"").toString().toLowerCase()}`.includes(low))
      .sort((a,b) => scoreProduct(a, low) - scoreProduct(b, low));
    if(candidates.length) return String(candidates[0].id || "");
    return "";
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
      const rawLogs = Array.isArray(r.raw_material_logs) ? r.raw_material_logs : [];
      const rawText = rawLogs.length
        ? rawLogs.map((x, idx) => `${idx+1}. ${x.material || "-"} | qty=${x.qty || 0} | key=${x.unique_key || "-"}`).join("\\n")
        : "No raw materials scanned.";
      return `
        <div class="finished-item">
          <div class="finished-head">
            <h4>${esc(r.job_name || r.job_code || "Finished Job")} - ${esc(r.machine_name || r.machine_code || "-")}</h4>
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
          <div class="finished-actions">
            <button class="approve-print-btn" data-row-index="${idx}" type="button">Approve and Print QR</button>
          </div>
        </div>
      `;
    }).join("");
  }

  async function loadProducts(forceRefresh = false){
    const url = forceRefresh ? "/api/products?refresh=1" : "/api/products";
    const res = await fetch(url, { method: "GET" });
    const data = await res.json();
    productItems = Array.isArray(data.items) ? data.items : [];
    if(!productItems.length){
      overlayProductList.innerHTML = "";
      overlayProductSelect.value = "";
      overlayProductSelect.placeholder = "No products available";
      return;
    }
    overlayProductList.innerHTML = productItems
      .map(p => `<option value="${esc(p.sku || "")} - ${esc(p.name)}"></option>`)
      .join("");
    if(!overlayProductSelect.value){
      const first = productItems[0];
      overlayProductSelect.value = `${first.sku || ""} - ${first.name}`;
    }
  }

  function openApprovePrintOverlay(job){
    activeJobRow = job || null;
    const title = activeJobRow
      ? `${activeJobRow.job_name || activeJobRow.job_code || "Finished Job"} | ${activeJobRow.machine_name || activeJobRow.machine_code || "-"}`
      : "Finished Job";
    overlayJobInfo.value = title;
    overlayQrPayload.value = "";
    overlayQrPreview.removeAttribute("src");
    approvePrintOverlay.classList.add("active");
  }

  function closeApprovePrintOverlay(){
    approvePrintOverlay.classList.remove("active");
    activeJobRow = null;
  }

  function render(state){
    timeEl.textContent = "Server UTC: " + state.server_time_utc;
    machineGrid.innerHTML = "";
    const sessions = state.sessions || [];
    const byCode = Object.fromEntries(sessions.map(s => [String(s.machine_code || "").trim(), s]));
    machineCountEl.textContent = String(MACHINE_CODES.length);

    for(const code of MACHINE_CODES){
      const s = byCode[code] || {
        machine_code: code,
        machine_name: `Machine ${parseInt(code.slice(1), 10) || code}`,
        job_name: "",
        operator_id: "",
        pack_total: 0,
        butal_total: 0,
        reject_total: 0,
        last_event: "No data yet",
        last_seen_utc: "",
      };
      const css = statusClass(s.last_seen_utc) || "stopped";
      const card = document.createElement("div");
      card.className = `card ${css}`;
      const total = Number(s.pack_total||0) + Number(s.butal_total||0) + Number(s.reject_total||0);
      card.innerHTML = `
        <h3>${esc(s.machine_name || s.machine_code)}</h3>
        <p>Machine: <strong>${esc(s.machine_code || code)}</strong></p>
        <p>Job: <strong>${esc(s.job_name || "No Job Set")}</strong></p>
        <p>Operator: <strong>${esc(s.operator_id || "-")}</strong></p>
        <p>Status: <strong>${css.toUpperCase()}</strong></p>
        <p>Pack: <strong>${esc(s.pack_total)}</strong></p>
        <p>Butal: <strong>${esc(s.butal_total)}</strong></p>
        <p>Reject: <strong>${esc(s.reject_total)}</strong></p>
        <p>Total: <strong>${esc(total)}</strong></p>
        <p class="muted">Last Event: ${esc(s.last_event || "-")}</p>
      `;
      machineGrid.appendChild(card);
    }
    renderFinishedJobs(state.finished_jobs || []);
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

  finishedJobsList.addEventListener("click", async (ev) => {
    const btn = ev.target.closest(".approve-print-btn");
    if(!btn) return;
    const idx = Number(btn.getAttribute("data-row-index"));
    if(Number.isNaN(idx) || idx < 0) return;
    const sorted = [...(finishedJobsState || [])].reverse();
    const row = sorted[idx];
    if(!row) return;
    if(!productItems.length){
      await loadProducts(false);
    }
    openApprovePrintOverlay(row);
  });

  overlayCloseBtn.addEventListener("click", closeApprovePrintOverlay);
  overlayCancelBtn.addEventListener("click", closeApprovePrintOverlay);
  approvePrintOverlay.addEventListener("click", (ev) => {
    if(ev.target === approvePrintOverlay) closeApprovePrintOverlay();
  });

  overlayGenerateBtn.addEventListener("click", async () => {
    const productId = resolveProductIdFromText(overlayProductSelect.value || "");
    if(!productId){
      overlayQrPayload.value = "Select a product first.";
      return;
    }
    const resp = await fetch("/api/raw-material-qr", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_id: productId,
        finished_job: activeJobRow || {},
      }),
    });
    const out = await resp.json();
    overlayQrPayload.value = out.qr_payload || out.error || "Failed to generate.";
    if(out.label_image_data_url){
      overlayQrPreview.src = out.label_image_data_url;
    } else if(out.qr_image_data_url){
      overlayQrPreview.src = out.qr_image_data_url;
    } else {
      overlayQrPreview.removeAttribute("src");
    }
  });

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
</script>
</body>
</html>
"""


@APP.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(DASHBOARD_HTML)


@APP.get("/favicon.ico")
def favicon():
    # Return empty 204 so browser favicon requests don't pollute logs.
    return Response(status_code=204)


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
            machine_name=str(data.get("machine_name", machine_code)),
            reject_breakdown={},
        )
        SESSIONS[machine_code] = sess

    # update common fields
    sess.client_id = str(data.get("client_id", sess.client_id))
    sess.machine_name = str(data.get("machine_name", sess.machine_name))
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
    elif ev_type == "PACK":
        sess.pack_total += int(ev.get("qty", 0) or 0)
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
    if not product_id:
        return JSONResponse({"ok": False, "error": "product_id is required"}, status_code=400)
    payload = _build_raw_material_qr_value(product_id)
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
        "qr_format": _raw_qr_format_template(),
    }


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
