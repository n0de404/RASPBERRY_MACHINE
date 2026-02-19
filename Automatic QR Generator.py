import sys
import re
import json
import csv
import io
import sqlite3
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from math import ceil
from pathlib import Path

from PyQt6.QtCore import Qt, QSizeF, QRect, QRectF, QObject, QThreadPool, QRunnable, pyqtSignal, QTimer, QMarginsF, QSignalBlocker, QEvent, pyqtSlot, QByteArray
from PyQt6.QtGui import QImage, QPixmap, QPainter, QFont, QPageSize, QPageLayout
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QFormLayout, QHBoxLayout, QVBoxLayout, QMessageBox,
    QScrollArea, QFileDialog, QComboBox, QCompleter, QMenuBar, QMenu,
    QFrame, QProgressBar, QListWidget, QListWidgetItem
)
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog

import qrcode
try:
    import serial  # type: ignore
except Exception:
    serial = None


# ----------------------------
# PRODUCTS (name shown, id used in QR)
# ----------------------------
APP_DIR = Path(__file__).resolve().parent
MYSQL_CONFIG_PATH = APP_DIR / "mysql_config.example.json"
QR_LABELS_DIRNAME = "QR LABEL"
THEMES_DIR = APP_DIR / "themes"
LIGHT_QSS = THEMES_DIR / "light.qss"
DARK_QSS = THEMES_DIR / "dark.qss"
API_DB_PATH = APP_DIR / "qr_api_events.db"
API_DEFAULT_HOST = "0.0.0.0"
API_DEFAULT_PORT = 8787

FALLBACK_PRODUCTS = [
    {"id": "803", "name": "HANGER SPACE SAVER"},
    {"id": "9727", "name": "SUNNYWARE STAR STOOL"},
    {"id": "2053", "name": "PLASTIC BASIN 20L"},
]


def _mysql_settings_from_file(path: Path) -> dict:
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    host = str(data.get("host", "")).strip()
    user = str(data.get("user", "")).strip()
    password = str(data.get("password", "")).strip()
    database = str(data.get("database", "")).strip()

    port_val = data.get("port", 3306)
    try:
        port = int(str(port_val).strip() or "3306")
    except Exception:
        port = 3306

    if not (host and user and database):
        return {}

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
    }


def _try_import_mysql_connector():
    try:
        import mysql.connector  # type: ignore
        return mysql.connector
    except Exception:
        return None


def _mysql_connect():
    settings = _mysql_settings_from_file(MYSQL_CONFIG_PATH)
    connector = _try_import_mysql_connector()
    if not settings or connector is None:
        raise RuntimeError("MySQL not configured or mysql-connector-python not installed.")

    # Force pure-Python connector to avoid C-extension crashes on some setups.
    return connector.connect(
        host=settings["host"],
        port=settings["port"],
        user=settings["user"],
        password=settings["password"],
        database=settings["database"],
        use_pure=True,
        autocommit=True,
    )


def _ensure_mysql_schema_for_logs() -> None:
    con = _mysql_connect()
    try:
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS print_logs (
              id BIGINT PRIMARY KEY AUTO_INCREMENT,
              action VARCHAR(32) NOT NULL,
              created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              product_id VARCHAR(64) NULL,
              product_name VARCHAR(255) NULL,
              qty VARCHAR(64) NULL,
              total VARCHAR(64) NULL,
              labels_count INT NOT NULL,
              is_batch TINYINT(1) NOT NULL,
              output_path VARCHAR(1024) NULL
            )
            """
        )
    finally:
        con.close()


def _mysql_log_action(
    action: str,
    product_id: str | None,
    product_name: str | None,
    qty: str | None,
    total: str | None,
    labels_count: int,
    is_batch: bool,
    output_path: str | None,
) -> None:
    try:
        _ensure_mysql_schema_for_logs()
        con = _mysql_connect()
        try:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO print_logs
                  (action, product_id, product_name, qty, total, labels_count, is_batch, output_path)
                VALUES
                  (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    action,
                    product_id,
                    product_name,
                    qty,
                    total,
                    int(labels_count),
                    1 if is_batch else 0,
                    output_path,
                ),
            )
        finally:
            con.close()
    except Exception:
        # Never block printing/exporting if logging fails.
        return


def _load_products_from_mysql() -> list[dict]:
    try:
        con = _mysql_connect()
    except Exception:
        return []
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT id, name FROM products WHERE active = 1 ORDER BY name ASC"
        )
        rows = cur.fetchall()
        out: list[dict] = []
        for pid, name in rows:
            pid_s = str(pid).strip()
            name_s = str(name).strip()
            if pid_s and name_s:
                out.append({"id": pid_s, "name": name_s})
        return out
    finally:
        con.close()


def _qr_labels_dir() -> Path:
    d = APP_DIR / QR_LABELS_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _warn_mysql_fallback(msg: str) -> None:
    try:
        # If we're in GUI context, show a warning once; otherwise just print.
        app = QApplication.instance()
        if app is not None:
            QMessageBox.warning(
                None,
                "MySQL not used",
                msg,
            )
            return
    except Exception:
        pass

    try:
        print(msg, file=sys.stderr)
    except Exception:
        pass


# ----------------------------
# SIMPLE API QUEUE (SQLite + stdlib HTTP)
# ----------------------------
def _api_db_connect() -> sqlite3.Connection:
    con = sqlite3.connect(str(API_DB_PATH), check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    return con


def _api_init_db() -> None:
    con = _api_db_connect()
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS api_requests (
              id TEXT PRIMARY KEY,
              created_at TEXT NOT NULL,
              status TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              output_path TEXT NULL,
              error_text TEXT NULL,
              processed_at TEXT NULL
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_api_requests_status_created ON api_requests(status, created_at)")
        con.commit()
    finally:
        con.close()


def _api_add_request(payload: dict) -> str:
    _api_init_db()
    req_id = str(uuid.uuid4())
    con = _api_db_connect()
    try:
        con.execute(
            "INSERT INTO api_requests (id, created_at, status, payload_json) VALUES (?, ?, ?, ?)",
            (req_id, datetime.utcnow().isoformat(timespec="seconds") + "Z", "pending", json.dumps(payload, ensure_ascii=False)),
        )
        con.commit()
        return req_id
    finally:
        con.close()


def _api_pending_count() -> int:
    _api_init_db()
    con = _api_db_connect()
    try:
        cur = con.execute("SELECT COUNT(*) FROM api_requests WHERE status = 'pending'")
        row = cur.fetchone()
        return int(row[0] if row else 0)
    finally:
        con.close()


def _api_get_oldest_pending() -> dict | None:
    _api_init_db()
    con = _api_db_connect()
    try:
        cur = con.execute(
            "SELECT id, created_at, payload_json FROM api_requests WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            return None
        rid, created_at, payload_json = row
        try:
            payload = json.loads(payload_json or "{}")
        except Exception:
            payload = {}
        return {"id": str(rid), "created_at": str(created_at), "payload": payload}
    finally:
        con.close()


def _api_set_status(req_id: str, status: str, *, output_path: str | None = None, error_text: str | None = None) -> None:
    _api_init_db()
    con = _api_db_connect()
    try:
        con.execute(
            """
            UPDATE api_requests
               SET status = ?,
                   output_path = COALESCE(?, output_path),
                   error_text = COALESCE(?, error_text),
                   processed_at = ?
             WHERE id = ?
            """,
            (
                status,
                output_path,
                error_text,
                datetime.utcnow().isoformat(timespec="seconds") + "Z",
                req_id,
            ),
        )
        con.commit()
    finally:
        con.close()


def _api_list_requests(status: str, limit: int = 50) -> list[dict]:
    _api_init_db()
    limit_i = max(1, min(int(limit), 500))
    status_s = (status or "").strip().lower()
    if status_s not in {"pending", "processed", "failed"}:
        status_s = "pending"
    con = _api_db_connect()
    try:
        cur = con.execute(
            "SELECT id, created_at, status, payload_json, output_path, error_text, processed_at FROM api_requests WHERE status = ? ORDER BY created_at ASC LIMIT ?",
            (status_s, limit_i),
        )
        out: list[dict] = []
        for rid, created_at, st, payload_json, output_path, error_text, processed_at in cur.fetchall():
            try:
                payload = json.loads(payload_json or "{}")
            except Exception:
                payload = {}
            out.append(
                {
                    "id": str(rid),
                    "created_at": str(created_at),
                    "status": str(st),
                    "payload": payload,
                    "output_path": output_path,
                    "error_text": error_text,
                    "processed_at": processed_at,
                }
            )
        return out
    finally:
        con.close()


class _ApiHttpHandler(BaseHTTPRequestHandler):
    server_version = "QRApi/1.0"

    def _send_json(self, status: int, data: dict | list) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except Exception:
            length = 0
        raw = self.rfile.read(max(0, min(length, 1_000_000)))
        try:
            obj = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            obj = {}
        return obj if isinstance(obj, dict) else {}

    def log_message(self, format, *args):  # noqa: A003
        return

    def do_GET(self):  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/v1/queue":
                self._send_json(200, {"pending_count": _api_pending_count()})
                return

            if parsed.path == "/api/v1/products":
                items = []
                try:
                    items = load_products()
                except Exception:
                    items = []
                # Ensure stable shape
                out = []
                for it in items or []:
                    try:
                        pid = str(it.get("id", "")).strip()
                        name = str(it.get("name", "")).strip()
                    except Exception:
                        pid, name = "", ""
                    if pid and name:
                        out.append({"id": pid, "name": name})
                self._send_json(200, {"products": out})
                return

            if parsed.path == "/api/v1/requests":
                qs = parse_qs(parsed.query or "")
                status = (qs.get("status", ["pending"])[0] or "pending").strip().lower()
                limit = qs.get("limit", ["50"])[0]
                try:
                    limit_i = int(str(limit).strip() or "50")
                except Exception:
                    limit_i = 50
                self._send_json(200, {"requests": _api_list_requests(status, limit=limit_i)})
                return

            self._send_json(404, {"error": "not_found"})
        except Exception as e:
            self._send_json(500, {"error": "server_error", "detail": str(e)})

    def do_POST(self):  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path != "/api/v1/requests":
                self._send_json(404, {"error": "not_found"})
                return

            payload = self._read_json()
            product_id = str(payload.get("product_id", "")).strip()
            product_name = str(payload.get("product_name", "")).strip()
            qty = str(payload.get("qty", "")).strip()
            total = str(payload.get("total", "")).strip()
            lot_po = str(payload.get("lot_po", "")).strip()

            if not (qty and total and lot_po and (product_id or product_name)):
                self._send_json(
                    400,
                    {
                        "error": "validation_error",
                        "detail": "Required: qty, total, lot_po, and (product_id or product_name)",
                    },
                )
                return

            req_id = _api_add_request(
                {
                    "product_id": product_id,
                    "product_name": product_name,
                    "qty": qty,
                    "total": total,
                    "lot_po": lot_po,
                }
            )
            self._send_json(201, {"request_id": req_id, "pending_count": _api_pending_count()})
        except Exception as e:
            self._send_json(500, {"error": "server_error", "detail": str(e)})


class _ApiServerController(QObject):
    status_changed = pyqtSignal(str)

    def __init__(self, host: str = API_DEFAULT_HOST, port: int = API_DEFAULT_PORT):
        super().__init__()
        self.host = host
        self.port = int(port)
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def is_running(self) -> bool:
        return self._httpd is not None and self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running():
            return
        _api_init_db()
        self._httpd = ThreadingHTTPServer((self.host, self.port), _ApiHttpHandler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        self.status_changed.emit(f"Listening on http://{self.host}:{self.port}")

    def stop(self) -> None:
        try:
            if self._httpd is not None:
                self._httpd.shutdown()
                self._httpd.server_close()
        finally:
            self._httpd = None
            self._thread = None
            self.status_changed.emit("Stopped")


class _BarcodeToPoEventFilter(QObject):
    def __init__(self, po_line: QLineEdit, on_complete):
        super().__init__()
        self._po_line = po_line
        self._on_complete = on_complete
        self._buf = ""
        self._last_ms: int | None = None
        self._active = False
        self._commit_timer = QTimer()
        self._commit_timer.setSingleShot(True)
        self._commit_timer.timeout.connect(self._commit_if_active)

    def _now_ms(self) -> int:
        return int(datetime.now().timestamp() * 1000)

    def _reset(self) -> None:
        self._buf = ""
        self._last_ms = None
        self._active = False
        try:
            self._commit_timer.stop()
        except Exception:
            pass

    def _commit_if_active(self) -> None:
        if self._active and self._buf:
            self._po_line.setText(self._buf)
            try:
                self._on_complete()
            finally:
                self._reset()

    def eventFilter(self, obj, event):  # type: ignore[override]
        if event.type() != QEvent.Type.KeyPress:
            return False

        key = event.key()
        text = event.text() or ""

        # Ignore modifier combos.
        if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            self._reset()
            return False

        # If user is already typing in the PO field, don't interfere.
        try:
            if QApplication.focusWidget() is self._po_line:
                self._reset()
                return False
        except Exception:
            pass

        now_ms = self._now_ms()
        gap = None if self._last_ms is None else (now_ms - self._last_ms)
        self._last_ms = now_ms

        # End-of-scan (many scanners send Enter/Tab).
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
            if self._active and self._buf:
                self._commit_if_active()
                return True
            self._reset()
            return False

        # Only accept printable characters.
        if len(text) != 1 or not text.isprintable():
            self._reset()
            return False

        # First char, or long pause: start candidate (don't swallow).
        if gap is None or gap > 250:
            self._buf = text
            self._active = False
            return False

        # Fast stream: looks like a scanner.
        if gap <= BARCODE_SCAN_MAX_GAP_MS:
            self._buf += text
            if len(self._buf) >= BARCODE_SCAN_MIN_LEN:
                self._active = True
                self._po_line.setFocus(Qt.FocusReason.OtherFocusReason)
                # Keep PO updated even if scanner doesn't send Enter.
                self._po_line.setText(self._buf)
            if self._active:
                try:
                    self._commit_timer.start(BARCODE_SCAN_END_PAUSE_MS)
                except Exception:
                    pass
            return self._active

        # Slow typing / pause: if we were scanning, commit; otherwise reset.
        if self._active:
            self._commit_if_active()
            return True
        self._reset()
        return False


class _SerialScannerWorker(QObject):
    scanned = pyqtSignal(str)

    def __init__(self, port: str, baud: int):
        super().__init__()
        self._port = port
        self._baud = baud
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        if serial is None:
            return

        try:
            ser = serial.Serial(
                self._port,
                self._baud,
                timeout=SCANNER_SERIAL_TIMEOUT_S,
            )
        except Exception:
            return

        buf = bytearray()
        try:
            while not self._stop:
                try:
                    b = ser.read(1)
                except Exception:
                    break

                if not b:
                    continue

                if b in (b"\r", b"\n", b"\t"):
                    s = buf.decode("utf-8", errors="ignore").strip()
                    buf.clear()
                    if s:
                        self.scanned.emit(s)
                    continue

                buf += b
                if len(buf) > 4096:
                    buf.clear()
        finally:
            try:
                ser.close()
            except Exception:
                pass


def load_products() -> list[dict]:
    """
    Loads products from MySQL (mysql_config.example.json).
    """
    try:
        products = _load_products_from_mysql()
        if products:
            return products

        if not MYSQL_CONFIG_PATH.exists():
            _warn_mysql_fallback(f"Missing MySQL config: {MYSQL_CONFIG_PATH}")
        else:
            _warn_mysql_fallback(
                "No active products returned from MySQL. Using fallback list.\n"
                "Check your `products` table has rows with `active = 1`."
            )
        return FALLBACK_PRODUCTS
    except Exception as e:
        _warn_mysql_fallback(
            "Failed to load products from MySQL; using fallback list.\n"
            f"Config: {MYSQL_CONFIG_PATH}\n"
            f"Error: {e}"
        )
        return FALLBACK_PRODUCTS


def load_stylesheet(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def products_by_id(products: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in products or []:
        pid = str(item.get("id", "")).strip()
        name = str(item.get("name", "")).strip()
        if pid:
            out[pid] = name
    return out

def _try_import_openpyxl():
    try:
        import openpyxl  # type: ignore
        return openpyxl
    except Exception:
        return None


# ----------------------------
# DATA FORMAT CONFIG
# ----------------------------
DEFAULT_O_SEGMENT = "O000000000240000010237800000000000"  # fixed for now
FIXED_REMARK = "V2"

WIDTH_P = 11
WIDTH_Q = 11
WIDTH_I = 11
WIDTH_T = 11
# L lot format:
#   YYYYMMDDHHMMSS-XXXXXXXXXXXX (14 + 1 + 12 = 27 chars)
WIDTH_L = 27

# ----------------------------
# LABEL / LAYOUT CONFIG
# ----------------------------
COLS = 3
# Total print area (page) for 3-column sheet or 1-column barcode printer.
# - Total width is always 4.00" (split across columns)
# - Total height is always 1.25"
TOTAL_W_IN = 3.80
TOTAL_H_IN = 1.25

# Print/PDF calibration (inches). Positive X moves everything to the right.
PAGE_X_OFFSET_IN = 0.10

# Per-label size (computed from total width / columns); defaults assume 3 columns.
LABEL_W_IN = TOTAL_W_IN / COLS
LABEL_H_IN = TOTAL_H_IN

PRINT_DPI = 300
# Lower DPI for on-screen preview (keeps preview fast while matching proportions)
PREVIEW_DPI = 90

# QR generator resolution
QR_BOX_SIZE = 12
QR_BORDER = 1  # keep 1 for scan safety
QR_MID_SCALE = 1  # slightly smaller QR in the middle panel
BARCODE_SCAN_MAX_GAP_MS = 40  # typical scanners emit fast key events
BARCODE_SCAN_MIN_LEN = 6      # avoid hijacking normal typing
BARCODE_SCAN_END_PAUSE_MS = 120  # commit scan if no keys arrive
LABEL_FONT_FAMILY = "Courier New"

# Serial barcode scanner (non-keyboard scanners). Example: "COM6"
SCANNER_SERIAL_PORT = "COM6"
SCANNER_SERIAL_BAUD = 9600
SCANNER_SERIAL_TIMEOUT_S = 0.2

# ----------------------------
# FIXED BAND HEIGHTS (INCHES) - MUST SUM TO 1.25
# ----------------------------
TOP_BAR_IN = 0.22
MID_IN = 0.68
BOTTOM_IN = 0.35

# ----------------------------
# FONT SIZES (px at 300 DPI) - "START" SIZES
# ----------------------------
BASE_DPI = 300
IDX_FONT_PX_300 = 60     # index start
QTY_FONT_PX_300 = 40     # qty start
PC_FONT_PX_300 = 26      # PC start
DATE_FONT_PX_300 = 40    # YY/MM start
PROD_FONT_PX_300 = 40    # product start
DESC_FONT_PX_300 = 20    # description start (2nd line)


def font_px(px_at_300: int, dpi: int) -> int:
    return max(8, int(round(px_at_300 * (dpi / BASE_DPI))))


def only_digits(text: str) -> str:
    return re.sub(r"\D+", "", text or "")


def zpad(num_text: str, width: int) -> str:
    d = only_digits(num_text)
    if len(d) > width:
        d = d[-width:]
    return d.zfill(width)


def today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")

def now_yyyymmddhhmmss() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")

def _lot_suffix12_from_input(po_text: str) -> str:
    s = (po_text or "").strip()
    if "-" in s:
        s = s.split("-", 1)[1]
    return only_digits(s)[-12:].zfill(12)

def build_lot_digits(po_text: str) -> str:
    return f"{now_yyyymmddhhmmss()}-{_lot_suffix12_from_input(po_text)}"


def build_qr_value(
    product_id: str,
    qty: str,
    index_value: int,
    total: str,
    lot_po: str,
    lot_digits: str | None = None,
) -> str:
    p = "P" + zpad(product_id, WIDTH_P)
    q = "Q" + zpad(qty, WIDTH_Q)
    i = "I" + zpad(str(index_value), WIDTH_I)
    t = "T" + zpad(total, WIDTH_T)
    l = "L" + (lot_digits if lot_digits is not None else build_lot_digits(lot_po))
    return f"{DEFAULT_O_SEGMENT}{FIXED_REMARK}{p}{q}{i}{t}{l}"


def make_qr_qimage(data: str) -> QImage:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=QR_BOX_SIZE,
        border=QR_BORDER,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    w, h = img.size
    raw = img.tobytes("raw", "RGB")
    return QImage(raw, w, h, QImage.Format.Format_RGB888)


def make_qr_svg_bytes(data: str) -> bytes:
    # Vector QR (SVG) for crisp printing at any DPI.
    # Import lazily so the app still runs even if svg extras change.
    from qrcode.image.svg import SvgPathImage  # type: ignore

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=QR_BORDER,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(image_factory=SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue()


def inches_to_px(inches: float, dpi: int) -> int:
    return int(round(inches * dpi))


def inches_to_mm(inches: float) -> float:
    return inches * 25.4


def label_size_in(cols: int) -> tuple[float, float]:
    c = 1 if int(cols) <= 1 else 3
    return (TOTAL_W_IN / c, TOTAL_H_IN)


def strip_leading_zeros(digits: str) -> str:
    s = (digits or "").lstrip("0")
    return s if s != "" else "0"


def parse_qr_segments(qr_value: str) -> dict:
    def find_seg(tag: str, width: int) -> str:
        pos = qr_value.find(tag)
        if pos < 0:
            return ""
        return qr_value[pos + 1: pos + 1 + width]

    p_digits = find_seg("P", WIDTH_P)
    q_digits = find_seg("Q", WIDTH_Q)
    i_digits = find_seg("I", WIDTH_I)

    l_seg = find_seg("L", WIDTH_L)

    yy = ""
    mm = ""

    # Expect L to start with YYYYMMDDHHMMSS- (date/time) or YYYYMMDD (legacy).
    # Older versions may have left-zero padding before the timestamp.
    l_trim = l_seg.lstrip("0")
    if len(l_trim) >= 8 and l_trim[:8].isdigit():
        yyyy = l_trim[0:4]     # 2026
        mm = l_trim[4:6]       # 02
        yy = yyyy[2:4]         # 26

    return {
        "product": strip_leading_zeros(p_digits),
        "qty": strip_leading_zeros(q_digits),
        "index": strip_leading_zeros(i_digits),
        "yy": yy,
        "mm": mm,
    }



# ----------------------------
# AUTO-FIT TEXT HELPERS
# ----------------------------
def fit_font_to_rect(
    painter: QPainter,
    text: str,
    rect: QRect,
    start_px: int,
    min_px: int = 8,
    bold: bool = True,
    flags: int = int(Qt.AlignmentFlag.AlignCenter)
) -> QFont:
    f = QFont(LABEL_FONT_FAMILY)
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setFixedPitch(True)
    f.setBold(bold)

    for px in range(start_px, min_px - 1, -1):
        f.setPixelSize(px)
        painter.setFont(f)
        fm = painter.fontMetrics()
        br = fm.boundingRect(rect, flags, text)
        if br.width() <= rect.width() and br.height() <= rect.height():
            return f

    f.setPixelSize(min_px)
    return f


def draw_fitted_text(
    painter: QPainter,
    rect: QRect,
    text: str,
    start_px: int,
    min_px: int,
    bold: bool,
    color: Qt.GlobalColor,
    flags: int
):
    painter.setPen(color)
    font = fit_font_to_rect(
        painter=painter,
        text=text,
        rect=rect,
        start_px=start_px,
        min_px=min_px,
        bold=bold,
        flags=flags
    )
    painter.setFont(font)
    painter.drawText(rect, flags, text)


def make_label_qimage(
    qr_value: str,
    dpi: int = PRINT_DPI,
    label_w_in: float | None = None,
    label_h_in: float | None = None,
    products_by_id_map: dict[str, str] | None = None,
) -> QImage:
    """PRINT LABEL: exactly LABEL_W_IN x LABEL_H_IN at the given DPI (used for preview/PDF)."""
    if label_w_in is None:
        label_w_in = LABEL_W_IN
    if label_h_in is None:
        label_h_in = LABEL_H_IN

    label_w = inches_to_px(label_w_in, dpi)
    label_h = inches_to_px(label_h_in, dpi)

    top_bar_h = inches_to_px(TOP_BAR_IN, dpi)
    mid_h = inches_to_px(MID_IN, dpi)
    bottom_h = label_h - top_bar_h - mid_h

    img = QImage(label_w, label_h, QImage.Format.Format_RGB888)
    img.fill(Qt.GlobalColor.white)

    seg = parse_qr_segments(qr_value)

    painter = QPainter(img)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        line_thick = max(2, int(dpi * 0.01))
        painter.fillRect(0, top_bar_h - line_thick, label_w, line_thick, Qt.GlobalColor.black)
        painter.fillRect(0, top_bar_h + mid_h - line_thick, label_w, line_thick, Qt.GlobalColor.black)

        idx_box_w = int(label_w * 0.34)
        painter.fillRect(label_w - idx_box_w, 0, idx_box_w, top_bar_h, Qt.GlobalColor.black)

        idx_rect = QRect(label_w - idx_box_w, 0, idx_box_w, top_bar_h)
        draw_fitted_text(
            painter, idx_rect, seg["index"],
            start_px=font_px(IDX_FONT_PX_300, dpi), min_px=10,
            bold=True, color=Qt.GlobalColor.white,
            flags=int(Qt.AlignmentFlag.AlignCenter)
        )

        mid_y = top_bar_h
        left_col_w = int(label_w * 0.26)
        right_col_w = int(label_w * 0.26)
        center_w = label_w - left_col_w - right_col_w

        # Slightly smaller QR (middle panel)
        pad = max(4, int(label_w * 0.03))
        qr_target = min(center_w - 2 * pad, mid_h - 2 * pad)
        qr_target = max(10, int(qr_target * QR_MID_SCALE))

        qr_x = left_col_w + (center_w - qr_target) // 2
        qr_y = mid_y + (mid_h - qr_target) // 2
        painter.fillRect(QRect(qr_x, qr_y, qr_target, qr_target), Qt.GlobalColor.white)
        qr_svg = make_qr_svg_bytes(qr_value)
        qr_renderer = QSvgRenderer(QByteArray(qr_svg))
        qr_renderer.render(painter, QRectF(qr_x, qr_y, qr_target, qr_target))

        qty_rect = QRect(0, mid_y + int(mid_h * 0.30), left_col_w, int(mid_h * 0.22))
        draw_fitted_text(
            painter, qty_rect, seg["qty"],
            start_px=font_px(QTY_FONT_PX_300, dpi), min_px=10,
            bold=True, color=Qt.GlobalColor.black,
            flags=int(Qt.AlignmentFlag.AlignCenter)
        )

        pc_rect = QRect(0, mid_y + int(mid_h * 0.52), left_col_w, int(mid_h * 0.22))
        draw_fitted_text(
            painter, pc_rect, "PC",
            start_px=font_px(PC_FONT_PX_300, dpi), min_px=8,
            bold=True, color=Qt.GlobalColor.black,
            flags=int(Qt.AlignmentFlag.AlignCenter)
        )

        rx = left_col_w + center_w
        yy_rect = QRect(rx, mid_y + int(mid_h * 0.30), right_col_w, int(mid_h * 0.22))
        mm_rect = QRect(rx, mid_y + int(mid_h * 0.52), right_col_w, int(mid_h * 0.22))

        draw_fitted_text(
            painter, yy_rect, seg["yy"],
            start_px=font_px(DATE_FONT_PX_300, dpi), min_px=10,
            bold=True, color=Qt.GlobalColor.black,
            flags=int(Qt.AlignmentFlag.AlignCenter)
        )
        draw_fitted_text(
            painter, mm_rect, seg["mm"],
            start_px=font_px(DATE_FONT_PX_300, dpi), min_px=10,
            bold=True, color=Qt.GlobalColor.black,
            flags=int(Qt.AlignmentFlag.AlignCenter)
        )

        bottom_y = top_bar_h + mid_h
        top_h = int(bottom_h * 0.58)
        prod_rect = QRect(0, bottom_y, label_w, top_h)
        desc_rect = QRect(0, bottom_y + top_h, label_w, max(1, bottom_h - top_h))

        product_id = seg["product"]
        product_name = (products_by_id_map or {}).get(product_id, "").strip()
        draw_fitted_text(
            painter, prod_rect, product_id,
            start_px=font_px(PROD_FONT_PX_300, dpi), min_px=12,
            bold=True, color=Qt.GlobalColor.black,
            flags=int(Qt.AlignmentFlag.AlignCenter)
        )
        draw_fitted_text(
            painter, desc_rect, product_name or product_id,
            start_px=font_px(DESC_FONT_PX_300, dpi), min_px=10,
            bold=True, color=Qt.GlobalColor.black,
            flags=int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap) | int(Qt.TextFlag.TextWrapAnywhere)
        )

    finally:
        painter.end()

    return img


def make_label_preview_qimage(qr_value: str, size: int = 260) -> QImage:
    """Legacy helper (kept for compatibility)."""
    # Render the exact print layout at a lower DPI, then scale for screen.
    label = make_label_qimage(qr_value, dpi=PREVIEW_DPI)
    return label.scaledToWidth(max(10, int(size)), Qt.TransformationMode.FastTransformation)


def build_preview_sheet(label_images: list[QImage], cols: int = COLS) -> QImage:
    """Preview grid: uses label image size; draws a sheet."""
    if not label_images:
        img = QImage(600, 600, QImage.Format.Format_RGB888)
        img.fill(Qt.GlobalColor.white)
        return img

    cols = 1 if int(cols) <= 1 else 3
    cell_w = label_images[0].width()
    cell_h = label_images[0].height()
    gap = 0

    rows = ceil(len(label_images) / cols)
    sheet_w = cols * cell_w + (cols - 1) * gap
    sheet_h = rows * cell_h + (rows - 1) * gap

    sheet = QImage(sheet_w, sheet_h, QImage.Format.Format_RGB888)
    sheet.fill(Qt.GlobalColor.white)

    painter = QPainter(sheet)
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.setPen(Qt.GlobalColor.black)

        for idx, limg in enumerate(label_images):
            r = idx // cols
            c = idx % cols
            x = c * (cell_w + gap)
            y = r * (cell_h + gap)

            painter.drawImage(x, y, limg)
            painter.drawRect(x, y, cell_w - 1, cell_h - 1)

    finally:
        painter.end()

    return sheet


class _PreviewWorkerSignals(QObject):
    progress = pyqtSignal(int, int)  # current, total
    done = pyqtSignal(QImage, int)   # sheet, count
    error = pyqtSignal(str)


class _BuildPreviewWorker(QRunnable):
    def __init__(self, values: list[str], cols: int, size: int = 260, products_by_id_map: dict[str, str] | None = None):
        super().__init__()
        self.values = values
        self.cols = cols
        self.size = size
        self.products_by_id_map = products_by_id_map or {}
        self.signals = _PreviewWorkerSignals()

    def run(self):
        try:
            total = len(self.values)
            label_w_in, label_h_in = label_size_in(self.cols)
            screen_labels: list[QImage] = []
            for i, v in enumerate(self.values, start=1):
                # Strict preview: render using the same label layout as PDF, at PREVIEW_DPI.
                screen_labels.append(
                    make_label_qimage(
                        v,
                        dpi=PREVIEW_DPI,
                        label_w_in=label_w_in,
                        label_h_in=label_h_in,
                        products_by_id_map=self.products_by_id_map,
                    )
                )
                if i == 1 or i == total or i % 5 == 0:
                    self.signals.progress.emit(i, total)

            sheet = build_preview_sheet(screen_labels, cols=self.cols)
            self.signals.done.emit(sheet, total)
        except Exception as e:
            self.signals.error.emit(str(e))


class QRGeneratorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QR Generator")
        self.setMinimumSize(1250, 900)
        self.current_theme = "light"
        self.batch_rows: list[dict] = []

        # Load products list once
        self.products = load_products()

        # Header (menu left + theme selector right)
        self.menubar = QMenuBar()
        file_menu = self.menubar.addMenu("File")
        self.action_load_batch = file_menu.addAction("Import Batch (CSV/Excel)…")
        self.action_load_batch.triggered.connect(self.load_batch)
        self.action_clear_batch = file_menu.addAction("Clear Batch")
        self.action_clear_batch.triggered.connect(self.clear_batch)
        file_menu.addSeparator()
        self.action_exit = file_menu.addAction("Exit")
        self.action_exit.triggered.connect(self.close)

        theme_menu = self.menubar.addMenu("Theme")
        action_light = theme_menu.addAction("Light")
        action_dark = theme_menu.addAction("Dark")
        action_light.triggered.connect(lambda: self.apply_theme("light"))
        action_dark.triggered.connect(lambda: self.apply_theme("dark"))

        help_menu = self.menubar.addMenu("Help")
        help_menu.addAction("Instructions", self.show_instructions)

        server_menu = self.menubar.addMenu("Server")
        self.action_server_start = server_menu.addAction("Start API Server")
        self.action_server_stop = server_menu.addAction("Stop API Server")
        self.action_server_stop.setEnabled(False)

        self._api_server = _ApiServerController()
        self._api_server.status_changed.connect(self._on_api_status)
        self.action_server_start.triggered.connect(self._start_api_server)
        self.action_server_stop.triggered.connect(self._stop_api_server)

        header = QFrame()
        header.setObjectName("headerBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.addWidget(self.menubar, 0, Qt.AlignmentFlag.AlignLeft)
        header_layout.addStretch(1)

        # --- Product dropdown (name shown, id stored) ---
        self.cb_product = QComboBox()
        self.cb_product.setEditable(True)
        self.cb_product.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        # Populate
        self.cb_product.addItem("-- Select product --", "")
        for item in self.products:
            self.cb_product.addItem(item["name"], item["id"])

        # Completer for typing
        comp = QCompleter([p["name"] for p in self.products])
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp.setFilterMode(Qt.MatchFlag.MatchContains)
        self.cb_product.setCompleter(comp)

        # Inputs
        self.in_qty = QLineEdit()
        self.in_total = QLineEdit()

        self.in_lot_po = QLineEdit()
        self.in_lot_po.setPlaceholderText("PO number (date auto-added)")

        self.out_lot_preview = QLineEdit()
        self.out_lot_preview.setReadOnly(True)

        # Buttons
        self.btn_refresh = QPushButton("Generate / Refresh")
        self.btn_refresh.setObjectName("primaryButton")
        self.btn_refresh.clicked.connect(self.refresh_preview_async)

        self.btn_print = QPushButton("Print")
        self.btn_print.setObjectName("secondaryButton")
        self.btn_print.clicked.connect(self.print_labels)

        self.btn_next_batch = QPushButton("Add Batch")
        self.btn_next_batch.setObjectName("secondaryButton")
        self.btn_next_batch.clicked.connect(self.add_next_batch)

        self.btn_export_pdf = QPushButton('Export PDF')
        self.btn_export_pdf.setObjectName("secondaryButton")
        self.btn_export_pdf.clicked.connect(self.export_pdf)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setObjectName("dangerButton")
        self.btn_clear.clicked.connect(self.clear_all)

        # Barcode scanner support: scanners act like fast keyboard input + Enter.
        # If a scan is detected, it auto-fills the PO field.
        self._barcode_filter = _BarcodeToPoEventFilter(self.in_lot_po, self.refresh_preview_async)
        try:
            QApplication.instance().installEventFilter(self._barcode_filter)
        except Exception:
            pass

        # Serial scanner support (e.g., COM6). This is separate from keyboard-wedge scanners.
        self._scanner_worker = None
        self._scanner_thread = None
        if serial is not None and SCANNER_SERIAL_PORT:
            try:
                from PyQt6.QtCore import QThread

                self._scanner_thread = QThread(self)
                self._scanner_worker = _SerialScannerWorker(SCANNER_SERIAL_PORT, SCANNER_SERIAL_BAUD)
                self._scanner_worker.moveToThread(self._scanner_thread)
                self._scanner_thread.started.connect(self._scanner_worker.run)
                self._scanner_worker.scanned.connect(self._on_serial_scan)
                self._scanner_thread.start()
            except Exception:
                self._scanner_worker = None
                self._scanner_thread = None

        # Default focus to PO (helps typical scan workflows).
        self.in_lot_po.setFocus(Qt.FocusReason.OtherFocusReason)

        # Autorefresh on changes
        self.cb_product.currentIndexChanged.connect(self.on_change)
        self.cb_product.lineEdit().textChanged.connect(self.on_change)
        for w in [self.in_qty, self.in_total, self.in_lot_po]:
            w.textChanged.connect(self.on_change)

        # Form
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.in_qty.setPlaceholderText("digits only (auto zero-pad)")
        self.in_total.setPlaceholderText("digits only (auto zero-pad)  (also = number of labels)")

        form.addRow("Product Name:", self.cb_product)
        form.addRow("Quantity:", self.in_qty)
        form.addRow("Total labels:", self.in_total)
        form.addRow("Lot", self.in_lot_po)
        form.addRow("Lot (L) preview:", self.out_lot_preview)

        left_buttons = QVBoxLayout()
        left_buttons.setContentsMargins(0, 16, 0, 0)
        left_buttons.setSpacing(10)
        left_buttons.addWidget(self.btn_refresh)
        left_buttons.addWidget(self.btn_print)
        left_buttons.addWidget(self.btn_next_batch)
        left_buttons.addWidget(self.btn_export_pdf)
        left_buttons.addWidget(self.btn_clear)

        # API request panel (server-side)
        self.api_status = QLabel("API: stopped")
        self.api_status.setObjectName("apiStatus")
        self.api_pending = QLabel("Pending requests: 0")
        self.api_pending.setObjectName("apiPending")
        self.api_queue_bar = QProgressBar()
        self.api_queue_bar.setObjectName("apiQueueBar")
        self.api_queue_bar.setTextVisible(False)
        self.api_queue_bar.setFixedHeight(6)
        self.api_queue_bar.hide()

        self.api_requests_list = QListWidget()
        self.api_requests_list.setObjectName("apiRequestsList")
        self.api_requests_list.currentItemChanged.connect(self.load_selected_api_request_preview)

        self.btn_api_process = QPushButton("Process Selected Request")
        self.btn_api_process.setObjectName("primaryButton")
        self.btn_api_process.clicked.connect(self.process_selected_api_request)
        self.btn_api_process.setEnabled(True)

        api_panel = QFrame()
        api_panel.setObjectName("apiPanel")
        api_layout = QVBoxLayout(api_panel)
        api_layout.setContentsMargins(12, 12, 12, 12)
        api_layout.setSpacing(8)
        api_layout.addWidget(self.api_status)
        api_layout.addWidget(self.api_pending)
        api_layout.addWidget(self.api_queue_bar)
        api_layout.addWidget(self.api_requests_list)
        api_layout.addWidget(self.btn_api_process)
        left_buttons.addWidget(api_panel)

        left_buttons.addStretch(1)

        left_card = QFrame()
        left_card.setObjectName("leftCard")
        left_card_layout = QVBoxLayout(left_card)
        left_card_layout.setContentsMargins(16, 16, 16, 16)
        left_card_layout.setSpacing(12)
        left_card_layout.addLayout(form)
        left_card_layout.addLayout(left_buttons)

        left = QVBoxLayout()
        left.setContentsMargins(16, 16, 8, 16)
        left.addWidget(left_card)
        left.addStretch(1)

        # Preview
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName("previewScroll")

        self.preview_label = QLabel()
        self.preview_label.setObjectName("previewLabel")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.preview_label)

        preview_card = QFrame()
        preview_card.setObjectName("previewCard")
        preview_card_layout = QVBoxLayout(preview_card)
        preview_card_layout.setContentsMargins(16, 16, 16, 16)
        preview_card_layout.addWidget(self.scroll)

        right = QVBoxLayout()
        right.setContentsMargins(8, 16, 16, 16)
        right.setSpacing(12)
        self.lbl_hint = QLabel(f"Preview · {COLS} columns · 0 labels generated")
        self.lbl_hint.setObjectName("previewHint")
        self.busy_bar = QProgressBar()
        self.busy_bar.setObjectName("busyBar")
        self.busy_bar.setTextVisible(False)
        self.busy_bar.setFixedHeight(6)
        self.busy_bar.hide()
        right.addWidget(self.lbl_hint)
        right.addWidget(self.busy_bar)

        right.addWidget(preview_card)

        main = QHBoxLayout()
        main.addLayout(left, 2)
        main.addLayout(right, 3)

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(header)
        root.addLayout(main)
        self.setLayout(root)

        # Apply default theme
        self.apply_theme(self.current_theme)

        self.thread_pool = QThreadPool.globalInstance()
        self._preview_job_id = 0
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh_preview_async)

        self._loaded_api_request_id: str | None = None
        self._api_poll_timer = QTimer(self)
        self._api_poll_timer.setInterval(1500)
        self._api_poll_timer.timeout.connect(self._poll_api_queue)
        self._api_poll_timer.start()

        try:
            self._start_api_server()
        except Exception:
            pass

        self.on_change()

    # ----------------------------
    # Product selection helpers
    # ----------------------------
    def selected_product_id(self) -> str:
        """
        If user picked an item, use its userData (ID).
        If user typed, try to match typed name to a product and return its ID.
        """
        pid = str(self.cb_product.currentData() or "").strip()
        if pid:
            return pid

        typed = (self.cb_product.currentText() or "").strip().lower()
        for item in self.products:
            if item["name"].strip().lower() == typed:
                return item["id"]
        return ""

    # ----------------------------
    # Theme + Help
    # ----------------------------
    def apply_theme(self, name: str):
        self.current_theme = name
        if name == "dark":
            qss = load_stylesheet(DARK_QSS)
        else:
            qss = load_stylesheet(LIGHT_QSS)

        base = """
            QWidget { font-size: 14px; }
            QLineEdit { padding: 8px; }
            QComboBox { padding: 6px; }
            QPushButton { padding: 6px 12px; }
            QScrollBar:vertical { width: 12px; margin: 2px; }
            QScrollBar::handle:vertical { border-radius: 6px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar:horizontal { height: 12px; margin: 2px; }
            QScrollBar::handle:horizontal { border-radius: 6px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
        """
        self.setStyleSheet(base + qss)

    def show_instructions(self):
        text = (
            "1) Choose a product name (ID auto-fills for QR).\n"
            "2) Enter Quantity (Q) and Total labels (T).\n"
            "3) Add Lot/PO; today’s date is appended automatically.\n"
            "4) Click Generate / Refresh to preview labels.\n"
            "5) Export PDF to print 1.25\" x 4\" labels (3 columns).\n"
            "Tip: Quantity and Total accept digits only; values are zero-padded."
        )
        QMessageBox.information(self, "How to use", text)

    # ----------------------------
    # API server + queue helpers
    # ----------------------------
    def _on_api_status(self, text: str) -> None:
        self.api_status.setText(f"API: {text}")
        running = self._api_server.is_running()
        self.action_server_start.setEnabled(not running)
        self.action_server_stop.setEnabled(running)

    def _start_api_server(self) -> None:
        try:
            self._api_server.start()
        except Exception as e:
            QMessageBox.warning(self, "Server error", str(e) or "Failed to start API server.")

    def _stop_api_server(self) -> None:
        try:
            self._api_server.stop()
        except Exception:
            pass

    def _poll_api_queue(self) -> None:
        try:
            pending = _api_pending_count()
        except Exception:
            pending = 0
        self.api_pending.setText(f"Pending requests: {pending}")
        if pending >= 10:
            self.api_queue_bar.setRange(0, 0)
            self.api_queue_bar.show()
        elif pending > 0:
            self.api_queue_bar.setRange(0, 10)
            self.api_queue_bar.setValue(min(pending, 10))
            self.api_queue_bar.show()
        else:
            self.api_queue_bar.hide()

        try:
            pending_reqs = _api_list_requests("pending", limit=200)
        except Exception:
            pending_reqs = []

        try:
            sel_id = None
            sel = self.api_requests_list.currentItem()
            if sel is not None:
                sel_id = sel.data(Qt.ItemDataRole.UserRole)
        except Exception:
            sel_id = None

        # Updating the list triggers selection-change signals; block to avoid reloading preview every poll.
        blocker = QSignalBlocker(self.api_requests_list)
        self.api_requests_list.setUpdatesEnabled(False)
        try:
            self.api_requests_list.clear()
            for r in pending_reqs:
                rid = str(r.get("id", "")).strip()
                payload = r.get("payload") or {}
                created = str(r.get("created_at", "")).strip()
                pid = str(payload.get("product_id", "")).strip()
                pname = str(payload.get("product_name", "")).strip()
                qty = str(payload.get("qty", "")).strip()
                total = str(payload.get("total", "")).strip()
                lot_po = str(payload.get("lot_po", "")).strip()
                label = f"{created}  P:{pid or pname}  Q:{qty}  T:{total}  Lot:{lot_po}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, rid)
                self.api_requests_list.addItem(item)
                if sel_id and rid == sel_id:
                    self.api_requests_list.setCurrentItem(item)
        finally:
            self.api_requests_list.setUpdatesEnabled(True)
            try:
                del blocker
            except Exception:
                pass

    def process_selected_api_request(self) -> None:
        item = self.api_requests_list.currentItem()
        if item is None:
            QMessageBox.information(self, "API", "Select a request first.")
            return

        req_id = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        if not req_id:
            QMessageBox.warning(self, "API", "Invalid request.")
            return

        try:
            con = _api_db_connect()
            try:
                cur = con.execute("SELECT payload_json FROM api_requests WHERE id = ?", (req_id,))
                row = cur.fetchone()
            finally:
                con.close()
            if not row:
                QMessageBox.warning(self, "API", "Request not found.")
                return
            try:
                payload = json.loads(row[0] or "{}")
            except Exception:
                payload = {}

            product_id = str(payload.get("product_id", "")).strip()
            product_name = str(payload.get("product_name", "")).strip()
            qty = str(payload.get("qty", "")).strip()
            total = str(payload.get("total", "")).strip()
            lot_po = str(payload.get("lot_po", "")).strip()

            # Fill UI (so operator sees what's being processed)
            self.clear_batch()
            if product_id:
                idx = self.cb_product.findData(product_id)
                if idx >= 0:
                    self.cb_product.setCurrentIndex(idx)
                else:
                    self.cb_product.setCurrentIndex(0)
                    self.cb_product.setCurrentText(product_name or "")
            else:
                if product_name:
                    self.cb_product.setCurrentText(product_name)
                else:
                    self.cb_product.setCurrentIndex(0)
                    self.cb_product.setCurrentText("")

            self.in_qty.setText(qty)
            self.in_total.setText(total)
            self.in_lot_po.setText(lot_po)
            self.refresh_preview_async()

            out_dir = _qr_labels_dir()
            out_path = str(out_dir / f"api_{req_id}_{now_yyyymmddhhmmss()}.pdf")
            saved = self.export_pdf(silent=True, output_path=out_path)
            if saved:
                _api_set_status(req_id, "processed", output_path=saved)
                QMessageBox.information(self, "API", f"Success.\nSaved:\n{saved}")
            else:
                _api_set_status(req_id, "failed", error_text="export_failed")
                QMessageBox.warning(self, "API", "Failed to export PDF.")
        except Exception as e:
            _api_set_status(req_id, "failed", error_text=str(e))
            QMessageBox.warning(self, "API", str(e) or "Failed to process request.")
        finally:
            self._poll_api_queue()

    def load_selected_api_request_preview(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None = None) -> None:
        if current is None:
            return
        req_id = str(current.data(Qt.ItemDataRole.UserRole) or "").strip()
        if not req_id:
            return
        if (self._loaded_api_request_id or "") == req_id:
            return
        try:
            con = _api_db_connect()
            try:
                cur = con.execute("SELECT payload_json FROM api_requests WHERE id = ?", (req_id,))
                row = cur.fetchone()
            finally:
                con.close()
            if not row:
                return
            try:
                payload = json.loads(row[0] or "{}")
            except Exception:
                payload = {}

            product_id = str(payload.get("product_id", "")).strip()
            product_name = str(payload.get("product_name", "")).strip()
            qty = str(payload.get("qty", "")).strip()
            total = str(payload.get("total", "")).strip()
            lot_po = str(payload.get("lot_po", "")).strip()

            self.clear_batch()
            if product_id:
                idx = self.cb_product.findData(product_id)
                if idx >= 0:
                    self.cb_product.setCurrentIndex(idx)
                else:
                    self.cb_product.setCurrentIndex(0)
                    self.cb_product.setCurrentText(product_name or "")
            else:
                if product_name:
                    self.cb_product.setCurrentText(product_name)
                else:
                    self.cb_product.setCurrentIndex(0)
                    self.cb_product.setCurrentText("")

            self.in_qty.setText(qty)
            self.in_total.setText(total)
            self.in_lot_po.setText(lot_po)
            self._loaded_api_request_id = req_id
            self.refresh_preview_async()
        except Exception:
            return

    def on_change(self):
        lot_digits = build_lot_digits(self.in_lot_po.text())
        self.out_lot_preview.setText("L" + lot_digits)
        self.schedule_refresh_preview()

    def schedule_refresh_preview(self):
        # Debounce to avoid rebuilding previews on every keystroke immediately.
        self._refresh_timer.start(150)

    def clear_batch(self):
        self.batch_rows = []
        self.schedule_refresh_preview()

    def _clear_preview_ui(self):
        self._preview_job_id += 1  # invalidate any in-flight worker completion
        self._refresh_timer.stop()
        self.preview_label.clear()
        self.preview_label.resize(1, 1)
        self.lbl_hint.setText("Preview · 3 columns · 0 labels generated")

    def _clear_inputs_nonbatch(self):
        with (
            QSignalBlocker(self.cb_product),
            QSignalBlocker(self.in_qty),
            QSignalBlocker(self.in_total),
            QSignalBlocker(self.in_lot_po),
            QSignalBlocker(self.out_lot_preview),
        ):
            self.cb_product.setCurrentIndex(0)
            self.cb_product.setCurrentText("")
            self.in_qty.clear()
            self.in_total.clear()
            self.in_lot_po.clear()
            self.out_lot_preview.clear()
        self._clear_preview_ui()

    def add_next_batch(self):
        product_id = self.selected_product_id()
        if not product_id:
            QMessageBox.warning(self, "Missing product", "Please choose a product from the dropdown.")
            return

        qty = only_digits(self.in_qty.text())
        total = only_digits(self.in_total.text())
        if total == "":
            QMessageBox.warning(self, "Missing total", "Please enter Total labels.")
            return

        lot = (self.in_lot_po.text() or "").strip()
        lot_digits = f"{now_yyyymmddhhmmss()}-{_lot_suffix12_from_input(lot)}"
        self.batch_rows.append({"product": product_id, "qty": qty, "total": total, "lot": lot, "lot_digits": lot_digits})

        self.cb_product.setCurrentIndex(0)
        self.cb_product.setCurrentText("")
        self.in_qty.clear()
        self.in_total.clear()
        self.in_lot_po.clear()
        self.schedule_refresh_preview()

    def _resolve_product_id(self, product_value: str) -> str:
        raw = (product_value or "").strip()
        if raw == "":
            return ""
        if only_digits(raw) != "":
            return strip_leading_zeros(only_digits(raw))
        low = raw.lower()
        for item in self.products:
            if item["name"].strip().lower() == low:
                return str(item["id"])
        return raw

    def _parse_batch_csv(self, path: Path) -> list[dict]:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows: list[dict] = []
            for r in reader:
                if not r:
                    continue
                norm = {str(k or "").strip().lower(): (v or "") for k, v in r.items()}
                product = self._resolve_product_id(str(norm.get("product", "")).strip())
                qty = only_digits(str(norm.get("qty", "")).strip())
                total = only_digits(str(norm.get("total", "")).strip())
                lot = str(norm.get("lot", "")).strip()
                if product and total:
                    lot_digits = f"{now_yyyymmddhhmmss()}-{_lot_suffix12_from_input(lot)}"
                    rows.append({"product": product, "qty": qty, "total": total, "lot": lot, "lot_digits": lot_digits})
            return rows

    def _parse_batch_xlsx(self, path: Path) -> list[dict]:
        openpyxl = _try_import_openpyxl()
        if openpyxl is None:
            raise RuntimeError("Excel support requires 'openpyxl'. Please export as CSV or install openpyxl.")

        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active
        values = list(ws.iter_rows(values_only=True))
        if not values:
            return []

        headers = [str(h or "").strip().lower() for h in values[0]]
        idx = {h: i for i, h in enumerate(headers) if h}

        def get(row, key: str) -> str:
            i = idx.get(key, None)
            if i is None or i >= len(row):
                return ""
            return str(row[i] or "").strip()

        rows: list[dict] = []
        for row in values[1:]:
            product = self._resolve_product_id(get(row, "product"))
            qty = only_digits(get(row, "qty"))
            total = only_digits(get(row, "total"))
            lot = get(row, "lot")
            if product and total:
                lot_digits = f"{now_yyyymmddhhmmss()}-{_lot_suffix12_from_input(lot)}"
                rows.append({"product": product, "qty": qty, "total": total, "lot": lot, "lot_digits": lot_digits})
        return rows

    def load_batch(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load batch file",
            "",
            "Batch Files (*.csv *.xlsx);;CSV (*.csv);;Excel (*.xlsx)"
        )
        if not path:
            return

        p = Path(path)
        try:
            if p.suffix.lower() == ".csv":
                rows = self._parse_batch_csv(p)
            elif p.suffix.lower() == ".xlsx":
                rows = self._parse_batch_xlsx(p)
            else:
                QMessageBox.warning(self, "Unsupported file", "Please choose a .csv or .xlsx file.")
                return
        except Exception as e:
            QMessageBox.warning(self, "Batch load failed", str(e) or "Failed to load batch file.")
            return

        if not rows:
            QMessageBox.warning(self, "No rows", "No valid rows found. Expected headers: Product, Qty, Total, Lot.")
            return

        self.batch_rows = rows
        self.schedule_refresh_preview()

    def parse_total_as_count(self) -> int:
        raw = only_digits(self.in_total.text())
        if raw == "":
            return 1
        try:
            n = int(raw)
            if n < 1:
                return 1
            return min(n, 500)
        except:
            return 1

    def build_all_values(self) -> list[str]:
        if self.batch_rows:
            values: list[str] = []
            for row in self.batch_rows:
                product_id = str(row.get("product", "")).strip()
                qty = str(row.get("qty", "")).strip()
                total_raw = only_digits(str(row.get("total", "")).strip())
                lot = str(row.get("lot", "")).strip()
                lot_digits = str(row.get("lot_digits", "")).strip() or None

                if not product_id or total_raw == "":
                    continue
                try:
                    per_row_total = int(total_raw)
                except Exception:
                    continue

                per_row_total = max(1, min(per_row_total, 500))
                for idx in range(1, per_row_total + 1):
                    values.append(
                        build_qr_value(
                            product_id=product_id,
                            qty=qty,
                            index_value=idx,
                            total=total_raw,
                            lot_po=lot,
                            lot_digits=lot_digits,
                        )
                    )
                    if len(values) >= 500:
                        return values
            return values

        n = self.parse_total_as_count()
        product_id = self.selected_product_id()

        # If no product chosen, still show blank preview (or force warning on export)
        if not product_id:
            product_id = "0"

        values = []
        for idx in range(1, n + 1):
            values.append(
                build_qr_value(
                    product_id=product_id,
                    qty=self.in_qty.text(),
                    index_value=idx,
                    total=self.in_total.text(),
                    lot_po=self.in_lot_po.text(),
                )
            )
        return values

    def _set_busy(self, busy: bool, total: int | None = None):
        self.btn_refresh.setEnabled(not busy)
        self.btn_print.setEnabled(not busy)
        self.btn_next_batch.setEnabled(not busy)
        self.action_load_batch.setEnabled(not busy)
        self.action_clear_batch.setEnabled(not busy)
        self.btn_export_pdf.setEnabled(not busy)
        self.btn_clear.setEnabled(not busy)
        if busy:
            if total is None or total <= 0:
                self.busy_bar.setRange(0, 0)
            else:
                self.busy_bar.setRange(0, total)
                self.busy_bar.setValue(0)
            self.busy_bar.show()
        else:
            self.busy_bar.hide()

    def refresh_preview_async(self):
        values = self.build_all_values()
        self._preview_job_id += 1
        job_id = self._preview_job_id

        self._set_busy(True, total=len(values))
        worker = _BuildPreviewWorker(values=values, cols=COLS, size=260, products_by_id_map=products_by_id(self.products))

        def on_progress(current: int, total: int):
            if job_id != self._preview_job_id:
                return
            if self.busy_bar.maximum() != total:
                self.busy_bar.setRange(0, total)
            self.busy_bar.setValue(current)

        def on_done(sheet: QImage, count: int):
            if job_id != self._preview_job_id:
                return

            pix = QPixmap.fromImage(sheet)
            vw = self.scroll.viewport().width()
            if pix.width() > vw:
                pix = pix.scaledToWidth(vw - 12, Qt.TransformationMode.SmoothTransformation)

            self.preview_label.setPixmap(pix)
            self.preview_label.resize(pix.size())
            if self.batch_rows:
                self.lbl_hint.setText(f"Batch · {len(self.batch_rows)} rows · {count} labels previewed")
            else:
                self.lbl_hint.setText(f"Preview · {COLS} columns · {count} labels generated")
            self._set_busy(False)

        def on_error(msg: str):
            if job_id != self._preview_job_id:
                return
            self._set_busy(False)
            QMessageBox.warning(self, "Preview error", msg or "Failed to generate preview.")

        worker.signals.progress.connect(on_progress)
        worker.signals.done.connect(on_done)
        worker.signals.error.connect(on_error)
        self.thread_pool.start(worker)

    def export_pdf(self, silent: bool = False, output_path: str | None = None) -> str | None:
        # Block export if product not selected properly
        if not self.batch_rows and not self.selected_product_id():
            if not silent:
                QMessageBox.warning(self, "Missing product", "Please choose a product from the dropdown.")
            return None

        values = self.build_all_values()
        if not values:
            if not silent:
                QMessageBox.warning(self, "No QRs", "Nothing to export.")
            return None

        out_dir = _qr_labels_dir()
        path = output_path or str(out_dir / f"qr_labels_{today_yyyymmdd()}_{now_yyyymmddhhmmss()}.pdf")

        # Barcode-printer friendly PDF: 1 row per page, 3 columns across.
        cols = COLS
        is_nonbatch = not self.batch_rows
        page_w_mm = inches_to_mm(TOTAL_W_IN)
        page_h_mm = inches_to_mm(TOTAL_H_IN)

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        printer.setResolution(PRINT_DPI)
        printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
        printer.setPageSize(QPageSize(QSizeF(page_w_mm, page_h_mm), QPageSize.Unit.Millimeter))

        label_w_in, label_h_in = label_size_in(cols)
        label_w_px = inches_to_px(label_w_in, PRINT_DPI)
        label_h_px = inches_to_px(label_h_in, PRINT_DPI)
        page_x_offset_px = inches_to_px(PAGE_X_OFFSET_IN, PRINT_DPI)

        self._set_busy(True, total=len(values))
        painter = QPainter(printer)
        try:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.setPen(Qt.GlobalColor.black)

            for n, value in enumerate(values):
                # Draw 3 columns on the page; after one row (3 labels) start a new page.
                c = n % cols
                x = page_x_offset_px + (c * label_w_px)
                label_img = make_label_qimage(
                    value,
                    dpi=PRINT_DPI,
                    label_w_in=label_w_in,
                    label_h_in=label_h_in,
                    products_by_id_map=products_by_id(self.products),
                )
                painter.drawImage(x, 0, label_img)
                painter.drawRect(x, 0, label_w_px - 1, label_h_px - 1)
                if self.busy_bar.maximum() != len(values):
                    self.busy_bar.setRange(0, len(values))
                self.busy_bar.setValue(n + 1)
                if n == 0 or n == len(values) - 1 or n % 5 == 0:
                    QApplication.processEvents()
                if c == cols - 1 and n != len(values) - 1:
                    printer.newPage()

        finally:
            painter.end()
            self._set_busy(False)

        try:
            if self.batch_rows:
                _mysql_log_action(
                    "EXPORT_PDF",
                    None,
                    None,
                    None,
                    None,
                    labels_count=len(values),
                    is_batch=True,
                    output_path=path,
                )
            else:
                pid = self.selected_product_id()
                pname = ""
                for item in self.products:
                    if str(item.get("id", "")).strip() == pid:
                        pname = str(item.get("name", "")).strip()
                        break
                _mysql_log_action(
                    "EXPORT_PDF",
                    pid or None,
                    pname or None,
                    (self.in_qty.text() or "").strip() or None,
                    (self.in_total.text() or "").strip() or None,
                    labels_count=len(values),
                    is_batch=False,
                    output_path=path,
                )
        except Exception:
            pass

        if not silent:
            QMessageBox.information(self, "Saved", f"PDF exported:\n{path}")
        if is_nonbatch:
            self._clear_inputs_nonbatch()

        return path

    def print_labels(self):
        if not self.batch_rows and not self.selected_product_id():
            QMessageBox.warning(self, "Missing product", "Please choose a product from the dropdown.")
            return

        values = self.build_all_values()
        if not values:
            QMessageBox.warning(self, "No QRs", "Nothing to print.")
            return

        cols = COLS
        is_nonbatch = not self.batch_rows
        page_w_mm = inches_to_mm(TOTAL_W_IN)
        page_h_mm = inches_to_mm(TOTAL_H_IN)

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.NativeFormat)
        printer.setResolution(PRINT_DPI)
        printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
        printer.setPageSize(QPageSize(QSizeF(page_w_mm, page_h_mm), QPageSize.Unit.Millimeter))

        dlg = QPrintDialog(printer, self)
        dlg.setWindowTitle("Print QR Labels")
        if dlg.exec() != QPrintDialog.DialogCode.Accepted:
            return

        label_w_in, label_h_in = label_size_in(cols)
        label_w_px = inches_to_px(label_w_in, PRINT_DPI)
        label_h_px = inches_to_px(label_h_in, PRINT_DPI)
        page_x_offset_px = inches_to_px(PAGE_X_OFFSET_IN, PRINT_DPI)

        self._set_busy(True, total=len(values))
        painter = QPainter(printer)
        try:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.setPen(Qt.GlobalColor.black)

            for n, value in enumerate(values):
                c = n % cols
                x = page_x_offset_px + (c * label_w_px)
                label_img = make_label_qimage(
                    value,
                    dpi=PRINT_DPI,
                    label_w_in=label_w_in,
                    label_h_in=label_h_in,
                    products_by_id_map=products_by_id(self.products),
                )
                painter.drawImage(x, 0, label_img)
                painter.drawRect(x, 0, label_w_px - 1, label_h_px - 1)
                if self.busy_bar.maximum() != len(values):
                    self.busy_bar.setRange(0, len(values))
                self.busy_bar.setValue(n + 1)
                if n == 0 or n == len(values) - 1 or n % 5 == 0:
                    QApplication.processEvents()
                if c == cols - 1 and n != len(values) - 1:
                    printer.newPage()
        except Exception as e:
            QMessageBox.warning(self, "Print failed", str(e) or "Failed to print.")
            return
        finally:
            painter.end()
            self._set_busy(False)

        try:
            if self.batch_rows:
                _mysql_log_action(
                    "PRINT",
                    None,
                    None,
                    None,
                    None,
                    labels_count=len(values),
                    is_batch=True,
                    output_path=None,
                )
            else:
                pid = self.selected_product_id()
                pname = ""
                for item in self.products:
                    if str(item.get("id", "")).strip() == pid:
                        pname = str(item.get("name", "")).strip()
                        break
                _mysql_log_action(
                    "PRINT",
                    pid or None,
                    pname or None,
                    (self.in_qty.text() or "").strip() or None,
                    (self.in_total.text() or "").strip() or None,
                    labels_count=len(values),
                    is_batch=False,
                    output_path=None,
                )
        except Exception:
            pass

        if is_nonbatch:
            self._clear_inputs_nonbatch()

    def clear_all(self):
        self.cb_product.setCurrentIndex(0)
        self.cb_product.setCurrentText("")
        self.in_qty.clear()
        self.in_total.clear()
        self.in_lot_po.clear()
        self.clear_batch()
        self.schedule_refresh_preview()

    @pyqtSlot(str)
    def _on_serial_scan(self, text: str) -> None:
        self.in_lot_po.setText(text)
        self.refresh_preview_async()

    def closeEvent(self, event):  # type: ignore[override]
        try:
            try:
                self._stop_api_server()
            except Exception:
                pass
            if getattr(self, "_scanner_worker", None) is not None:
                self._scanner_worker.stop()
            if getattr(self, "_scanner_thread", None) is not None:
                self._scanner_thread.quit()
                self._scanner_thread.wait(1000)
        except Exception:
            pass
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = QRGeneratorApp()
    w.show()
    sys.exit(app.exec())
