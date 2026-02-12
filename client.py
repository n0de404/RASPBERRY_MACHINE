# client.py
from __future__ import annotations
import os
import socket
import sys
import threading
from dataclasses import dataclass
from typing import Optional, Dict, Any

import requests

from PyQt6.QtCore import Qt, QObject, QEvent, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame, QGridLayout, QSizePolicy
)

from mappings import parse_scan, MACHINE_MAP, JOB_MAP, REJECT_REASON_MAP
from ui_theme import APP_STYLESHEET

try:
    import serial  # pyserial
except Exception:
    serial = None


SERVER_URL = os.environ.get("MACHINE_SERVER_URL", "http://127.0.0.1:8000")
CLIENT_ID = os.environ.get("MACHINE_CLIENT_ID", socket.gethostname())
SCANNER_MODE = os.environ.get("MACHINE_SCANNER_MODE", "auto").strip().lower()
SCANNER_COM_PORT = os.environ.get("MACHINE_SCANNER_COM_PORT", "COM6").strip()
SCANNER_BAUDRATE = int(os.environ.get("MACHINE_SCANNER_BAUDRATE", "9600"))
SCANNER_TIMEOUT = float(os.environ.get("MACHINE_SCANNER_TIMEOUT", "1.0"))


@dataclass
class ClientState:
    machine_code: Optional[str] = None
    machine_name: Optional[str] = None
    job_code: Optional[str] = None
    job_name: Optional[str] = None
    operator_id: Optional[str] = None

    pack_total: int = 0
    butal_total: int = 0
    reject_total: int = 0
    reject_breakdown: Dict[str, int] = None

    waiting_reject_reason: bool = False

    def __post_init__(self):
        if self.reject_breakdown is None:
            self.reject_breakdown = {}


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


class ConveyorWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(90)
        self._items: list[dict] = []
        self._belt_y = 58.0
        self._phase = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def spawn_item(self, kind: str, qty: int = 1):
        if kind == "PACK":
            size = 18
            color = QColor("#3b82f6")
        elif kind == "BUTAL":
            size = 12
            color = QColor("#10b981")
        else:  # REJECT
            size = 16
            color = QColor("#ef4444")

        self._items.append({
            "kind": kind,
            "x": 8.0,
            "y": 2.0,
            "vy": 0.0,
            "size": float(size),
            "color": color,
            "landed": False,
        })

    def _tick(self):
        alive = []
        self._phase = (self._phase + 2) % 24
        exit_x = self.width() - 8
        for it in self._items:
            if not it["landed"]:
                it["vy"] += 0.9
                it["y"] += it["vy"]
                if it["y"] >= self._belt_y - it["size"]:
                    it["y"] = self._belt_y - it["size"]
                    it["landed"] = True
            else:
                speed = 3.4 if it["kind"] == "PACK" else 2.8 if it["kind"] == "BUTAL" else 2.0
                it["x"] += speed
                if it["x"] >= exit_x:
                    continue

            if it["x"] <= self.width() + 30:
                alive.append(it)
        self._items = alive
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Conveyor frame
        frame_y = int(self._belt_y) - 8
        p.setPen(QPen(QColor("#64748b"), 1))
        p.setBrush(QColor("#e2e8f0"))
        p.drawRoundedRect(4, frame_y, self.width() - 68, 40, 10, 10)

        # Belt bed
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#334155"))
        p.drawRoundedRect(12, int(self._belt_y), self.width() - 84, 14, 7, 7)

        # Moving belt slats
        p.setPen(QPen(QColor("#64748b"), 1))
        for i in range(14 - self._phase, self.width() - 84, 12):
            p.drawLine(i, int(self._belt_y) + 2, i + 4, int(self._belt_y) + 12)

        # rollers
        p.setPen(QPen(QColor("#475569"), 1))
        p.setBrush(QColor("#94a3b8"))
        for i in range(14, self.width() - 78, 32):
            p.drawEllipse(i, int(self._belt_y) + 16, 10, 10)

        # End chute
        p.setPen(QPen(QColor("#64748b"), 1))
        p.setBrush(QColor("#cbd5e1"))
        p.drawRoundedRect(self.width() - 18, int(self._belt_y) - 2, 12, 22, 4, 4)

        # items
        for it in self._items:
            x = int(it["x"])
            y = int(it["y"])
            s = int(it["size"])
            p.setPen(QPen(QColor("#334155"), 1))
            p.setBrush(it["color"])
            p.drawRoundedRect(x, y, s, s, 3, 3)

            if it["kind"] == "REJECT":
                # cracked marker
                p.setPen(QPen(QColor("#ffffff"), 2))
                p.drawLine(x + 3, y + 2, x + s - 4, y + s - 4)
                p.drawLine(x + s - 6, y + 2, x + 4, y + s - 5)

        p.end()


class ClientUI(QWidget):
    scan_received = pyqtSignal(str)
    scanner_status = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.state = ClientState()
        self._serial_stop = threading.Event()
        self._serial_thread: Optional[threading.Thread] = None

        self.setWindowTitle("Machine Client Dashboard")
        self.setMinimumSize(0, 0)
        self.setStyleSheet(APP_STYLESHEET)

        root = QHBoxLayout()
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(10)

        leftWrap = QWidget()
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(8)
        leftWrap.setLayout(left)

        self.pageTitle = QLabel("Machine Dashboard")
        self.pageTitle.setObjectName("PageTitle")

        self._banner_base_text = "Scan MACHINE QR to start"
        self._banner_anim_step = 0
        self.banner = QLabel(self._banner_base_text)
        self.banner.setObjectName("Banner")
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status = QLabel("Waiting...")
        self.status.setObjectName("StatusBar")
        self.status.setWordWrap(True)
        self.status.setFixedHeight(44)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

        left.addWidget(self.pageTitle)
        left.addWidget(self.banner)
        left.addWidget(self.status)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        # Production panel
        self.cardProduction = self._make_card("Production")
        statRow = QHBoxLayout()
        statRow.setSpacing(10)
        self.lblPack = QLabel("0")
        self.lblButal = QLabel("0")
        self.lblReject = QLabel("0")
        statRow.addWidget(self._make_stat_card("Pack", self.lblPack, "StatPack"))
        statRow.addWidget(self._make_stat_card("Butal", self.lblButal, "StatButal"))
        statRow.addWidget(self._make_stat_card("Reject", self.lblReject, "StatReject"))
        self.cardProduction.layout().addLayout(statRow)
        self.cardProduction.setFixedHeight(180)
        grid.addWidget(self.cardProduction, 0, 0, 1, 2)

        # Session panel
        self.cardSession = self._make_card("Session")
        sessionGrid = QGridLayout()
        sessionGrid.setHorizontalSpacing(10)
        sessionGrid.setVerticalSpacing(10)

        self.lblMachine = QLabel("-")
        self.lblJob = QLabel("-")
        self.lblOperator = QLabel("-")

        session_rows = [
            ("Machine", self.lblMachine),
            ("Job", self.lblJob),
            ("Operator", self.lblOperator),
        ]
        for i, (name, value_lbl) in enumerate(session_rows):
            n = QLabel(name)
            n.setObjectName("MetaLabel")
            value_lbl.setObjectName("MetaValue")
            sessionGrid.addWidget(n, i, 0)
            sessionGrid.addWidget(value_lbl, i, 1)
        self.cardSession.layout().addLayout(sessionGrid)
        self.cardSession.setFixedHeight(190)
        grid.addWidget(self.cardSession, 1, 0)

        # Reject detail panel
        self.cardReject = self._make_card("Reject Details")
        self.lblRejectBreak = QLabel("-")
        self.lblRejectBreak.setWordWrap(True)
        self.lblRejectBreak.setObjectName("MetaValue")
        self.lblRejectBreak.setFixedHeight(42)
        self.cardReject.layout().addWidget(self.lblRejectBreak)
        self.cardReject.setFixedHeight(120)
        grid.addWidget(self.cardReject, 2, 0)

        # Activity panel
        self.cardActivity = self._make_card("Activity")
        self.lblLast = QLabel("-")
        self.lblLast.setObjectName("MetaValue")
        self.cardActivity.layout().addWidget(self.lblLast)
        self.cardActivity.setFixedHeight(190)
        grid.addWidget(self.cardActivity, 1, 1)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        left.addLayout(grid)

        # Bottom conveyor panel
        self.cardConveyor = self._make_card("Conveyor")
        self.conveyor = ConveyorWidget()
        self.cardConveyor.layout().addWidget(self.conveyor)
        self.cardConveyor.setFixedHeight(165)
        left.addWidget(self.cardConveyor)
        left.addStretch(1)

        # Right side placeholder for future views.
        self.rightPanel = QFrame()
        self.rightPanel.setObjectName("Panel")
        rightLayout = QVBoxLayout()
        rightLayout.setContentsMargins(16, 14, 16, 14)
        rightLayout.setSpacing(10)
        self.rightPanel.setLayout(rightLayout)

        self.rightTitle = QLabel("Future View")
        self.rightTitle.setObjectName("RightTitle")
        self.rightHint = QLabel("Reserved area for upcoming UI modules.")
        self.rightHint.setObjectName("RightHint")
        self.machineAnim = QLabel("[M] ----")
        self.machineAnim.setObjectName("MachineAnim")
        self.machineAnim.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.machineAnim.setFixedWidth(160)

        rightLayout.addWidget(self.rightTitle)
        rightLayout.addWidget(self.rightHint)
        rightLayout.addStretch()
        rightLayout.addWidget(self.machineAnim)
        rightLayout.addStretch()

        root.addWidget(leftWrap, 1)
        root.addWidget(self.rightPanel, 1)

        self.setLayout(root)

        self.scan_received.connect(self.on_scanned)
        self.scanner_status.connect(self._set_status_text)
        self._setup_scanner_input()

        # heartbeat timer
        self.hb = QTimer(self)
        self.hb.timeout.connect(self.send_heartbeat)
        self.hb.start(5000)

        self.banner_anim = QTimer(self)
        self.banner_anim.timeout.connect(self._animate_banner)
        self.banner_anim.start(260)
        self.machine_anim_timer = QTimer(self)
        self.machine_anim_timer.timeout.connect(self._animate_machine_icon)
        self.machine_anim_timer.start(180)
        self._machine_anim_step = 0

        self._refresh_ui()

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

    def _make_stat_card(self, title: str, value_label: QLabel, stat_object_name: str) -> QFrame:
        f = QFrame()
        f.setProperty("role", "stat")
        f.setObjectName(stat_object_name)
        f.setLayout(QVBoxLayout())
        f.layout().setContentsMargins(8, 6, 8, 6)
        f.layout().setSpacing(2)
        t = QLabel(title)
        t.setObjectName("StatTitle")
        value_label.setObjectName("StatValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f.layout().addWidget(t)
        f.layout().addWidget(value_label)
        return f

    def _refresh_ui(self):
        s = self.state
        self.lblMachine.setText(s.machine_name or "-")
        self.lblJob.setText(s.job_name or "-")
        self.lblOperator.setText(self._operator_display_name(s.operator_id))

        self.lblPack.setText(str(s.pack_total))
        self.lblButal.setText(str(s.butal_total))
        self.lblReject.setText(str(s.reject_total))

        if s.reject_breakdown:
            parts = [f"{k}={v}" for k, v in s.reject_breakdown.items()]
            self.lblRejectBreak.setText(", ".join(parts))
        else:
            self.lblRejectBreak.setText("-")

        # banner message depending on workflow
        if not s.machine_code:
            self._set_banner_text("Scan MACHINE QR to start")
        elif not s.job_code:
            self._set_banner_text("Scan JOB QR")
        elif not s.operator_id:
            self._set_banner_text("Scan OPERATOR badge")
        elif s.waiting_reject_reason:
            self._set_banner_text("Reject mode: Scan reject reason (BM01/CS02/CO03/CR04/DI05)")
        else:
            self._set_banner_text("Ready: Scan PACK / BUTAL / Reject~1")

    def _set_banner_text(self, text: str):
        self._banner_base_text = text
        self._animate_banner()

    def _animate_banner(self):
        frames = ["[>   ]", "[>>  ]", "[ >>>]", "[  >>]", "[   >]"]
        frame = frames[self._banner_anim_step % len(frames)]
        self._banner_anim_step += 1
        self.banner.setText(f"{self._banner_base_text}  {frame}")

    def _animate_machine_icon(self):
        if not self.state.machine_code:
            self.machineAnim.setText("[M] idle")
            return
        frames = ["[M] active .  ", "[M] active .. ", "[M] active ..."]
        self.machineAnim.setText(frames[self._machine_anim_step % len(frames)])
        self._machine_anim_step += 1

    def _operator_display_name(self, text: Optional[str]) -> str:
        if not text:
            return "-"
        parts = [p.strip() for p in str(text).split(" - ", 1)]
        if len(parts) == 2:
            return parts[1] or "-"
        return str(text)

    def _scan_display_text(self, res, raw: str) -> str:
        if res is None:
            return "Unknown scan"
        if res.kind == "MACHINE":
            return f"Machine: {res.value}"
        if res.kind == "JOB":
            return f"Job: {res.value}"
        if res.kind == "OPERATOR":
            return f"Operator: {self._operator_display_name(res.value)}"
        if res.kind == "PACK":
            return f"Pack +{int(res.qty or 0)}"
        if res.kind == "BUTAL":
            return f"Butal +{int(res.qty or 0)}"
        if res.kind == "REJECT_TRIGGER":
            return "Reject mode enabled"
        if res.kind == "REJECT_REASON":
            return f"Reject reason: {res.value}"
        return "Scan received"

    def log_last(self, text: str):
        self.lblLast.setText(text)

    def _set_status_text(self, text: str):
        t = str(text).replace("\n", " ").strip()
        if len(t) > 120:
            short = t[:117] + "..."
            self.status.setText(short)
            self.status.setToolTip(t)
        else:
            self.status.setText(t)
            self.status.setToolTip("")

    def _setup_scanner_input(self):
        mode = SCANNER_MODE
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
            self._set_status_text(f"Scanner input: Auto mode (keyboard + serial {SCANNER_COM_PORT})")
        else:
            self._set_status_text(f"Scanner input: Serial mode ({SCANNER_COM_PORT})")

    def _serial_reader_loop(self):
        while not self._serial_stop.is_set():
            try:
                with serial.Serial(
                    port=SCANNER_COM_PORT,
                    baudrate=SCANNER_BAUDRATE,
                    timeout=SCANNER_TIMEOUT,
                ) as ser:
                    self.scanner_status.emit(
                        f"Scanner serial connected: {SCANNER_COM_PORT} @ {SCANNER_BAUDRATE}"
                    )
                    while not self._serial_stop.is_set():
                        raw = ser.readline()
                        if not raw:
                            continue
                        text = raw.decode("utf-8", errors="ignore").strip()
                        if text:
                            self.scan_received.emit(text)
            except Exception as e:
                self.scanner_status.emit(f"Scanner serial retry ({SCANNER_COM_PORT}): {e}")
                self._serial_stop.wait(2.0)

    def can_accept_production_scans(self) -> bool:
        s = self.state
        return bool(s.machine_code and s.job_code and s.operator_id)

    def on_scanned(self, raw: str):
        res = parse_scan(raw)
        self.log_last(self._scan_display_text(res, raw))

        if res is None:
            self.status.setText("Unknown scan (ignored).")
            return

        s = self.state

        # reject flow step 2
        if s.waiting_reject_reason:
            if res.kind == "REJECT_REASON":
                reason = res.value
                s.reject_total += 1
                s.reject_breakdown[reason] = s.reject_breakdown.get(reason, 0) + 1
                self.conveyor.spawn_item("REJECT")
                s.waiting_reject_reason = False
                self.status.setText(f"Reject recorded: {reason}")
                self._refresh_ui()
                self.push_event({"type": "REJECT", "qty": 1, "reason": reason}, f"REJECT {reason} +1")
                return
            else:
                self.status.setText("Reject mode: please scan a valid reason code (BM01/CS02/CO03/CR04/DI05).")
                return

        # workflow
        if res.kind == "MACHINE":
            s.machine_code = raw.strip()
            s.machine_name = res.value
            # reset when machine changes
            s.job_code = None
            s.job_name = None
            s.operator_id = None
            s.waiting_reject_reason = False
            self.status.setText(f"Machine set: {s.machine_name}")
            self._refresh_ui()
            self.push_event({"type": "MACHINE_SET"}, f"MACHINE {s.machine_name}")
            return

        if res.kind == "JOB":
            if not s.machine_code:
                self.status.setText("Scan MACHINE first.")
                return
            s.job_code = raw.strip()
            s.job_name = res.value
            s.operator_id = None
            self.status.setText(f"Job set: {s.job_name}")
            self._refresh_ui()
            self.push_event({"type": "JOB_SET"}, f"JOB {s.job_name}")
            return

        if res.kind == "OPERATOR":
            if not s.machine_code or not s.job_code:
                self.status.setText("Scan MACHINE then JOB first.")
                return
            s.operator_id = res.value
            self.status.setText(f"Operator set: {s.operator_id}")
            self._refresh_ui()
            self.push_event({"type": "OPERATOR_SET"}, f"OPERATOR {s.operator_id}")
            return

        # production scans require full session
        if res.kind in ("PACK", "BUTAL", "REJECT_TRIGGER"):
            if not self.can_accept_production_scans():
                self.status.setText("Complete session first: MACHINE → JOB → OPERATOR.")
                return

            if res.kind == "REJECT_TRIGGER":
                s.waiting_reject_reason = True
                self.status.setText("Reject mode enabled. Scan reason code now.")
                self._refresh_ui()
                # optional: notify server that reject mode started
                self.push_event({"type": "REJECT_MODE"}, "REJECT MODE")
                return

            if res.kind == "PACK":
                qty = int(res.qty or 0)
                s.pack_total += qty
                self.conveyor.spawn_item("PACK", qty=max(1, qty))
                self.status.setText(f"Pack +{qty}")
                self._refresh_ui()
                self.push_event({"type": "PACK", "qty": qty}, f"PACK +{qty}")
                return

            if res.kind == "BUTAL":
                qty = int(res.qty or 0)
                s.butal_total += qty
                self.conveyor.spawn_item("BUTAL")
                self.status.setText(f"Butal +{qty}")
                self._refresh_ui()
                self.push_event({"type": "BUTAL", "qty": qty}, f"BUTAL +{qty}")
                return

        self.status.setText(f"Scan handled: {res.kind}")
        self._refresh_ui()

    def send_heartbeat(self):
        # heartbeat is just a lightweight state push so server keeps it "active"
        if self.state.machine_code:
            self.push_event({"type": "HEARTBEAT"}, "HEARTBEAT", silent=True)

    def push_event(self, event: Dict[str, Any], last_event: str, silent: bool = False):
        s = self.state
        if not s.machine_code:
            return

        payload = {
            "client_id": CLIENT_ID,
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
                requests.post(f"{SERVER_URL}/api/event", json=payload, timeout=3)
                if not silent:
                    pass
            except Exception as e:
                if not silent:
                    self.status.setText(f"Server send failed: {e}")

        threading.Thread(target=_send, daemon=True).start()

    def closeEvent(self, event):
        self._serial_stop.set()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    w = ClientUI()
    w.setWindowState(Qt.WindowState.WindowFullScreen)
    w.showFullScreen()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
