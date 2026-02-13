# client.py
from __future__ import annotations
import os
import re
import socket
import sys
import threading
from dataclasses import dataclass
from typing import Optional, Dict, Any

import requests

from PyQt6.QtCore import Qt, QObject, QEvent, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QMovie, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame, QGridLayout, QSizePolicy, QGraphicsDropShadowEffect
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
INVALID_SCAN_GIF = os.environ.get("MACHINE_INVALID_SCAN_GIF", "slap-virtual-slap.gif").strip()

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
    showing_reject_summary: bool = False
    job_payload: Dict[str, Any] = None

    def __post_init__(self):
        if self.reject_breakdown is None:
            self.reject_breakdown = {}
        if self.job_payload is None:
            self.job_payload = {}


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


class ClientUI(QWidget):
    scan_received = pyqtSignal(str)
    scanner_status = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.state = ClientState()
        self._serial_stop = threading.Event()
        self._serial_thread: Optional[threading.Thread] = None
        self._motion_index = 0
        self._motion_frames = [
            "[M] >    ",
            "[M] >>   ",
            "[M] >>>  ",
            "[M]  >>> ",
            "[M]   >>>",
            "[M]    >>",
        ]
        self._label_icon_candidates = {
            "machine": ["machine.png", "machine.jpg", "machine.jpeg", "machine_icon.png", "icon_machine.png"],
            "job": ["job-seeker.png", "job.png", "job.jpg", "job.jpeg", "job_icon.png", "icon_job.png"],
            "operator": ["worker.png", "operator.png", "operator.jpg", "operator.jpeg", "operator_icon.png", "icon_operator.png"],
        }

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
        self.banner = QLabel(self._banner_base_text)
        self.banner.setObjectName("Banner")
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status = QLabel("Waiting...")
        self.status.setObjectName("StatusBar")
        self.status.setWordWrap(True)
        self.status.setFixedHeight(44)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.machineAnim = QLabel("[M] ----")
        self.machineAnim.setObjectName("MachineAnim")
        self.machineAnim.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.machineAnim.setFixedWidth(160)

        left.addWidget(self.pageTitle)
        left.addWidget(self.banner)
        left.addWidget(self.status)
        left.addWidget(self.machineAnim)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        # Production panel
        self.cardProduction = self._make_card("Production")
        statRow = QHBoxLayout()
        statRow.setSpacing(10)
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
        statRow.addWidget(self.cardStatPack)
        statRow.addWidget(self.cardStatGood)
        statRow.addWidget(self.cardStatButal)
        statRow.addWidget(self.cardStatReject)
        statRow.addWidget(self.cardStatTotalGood)
        self.cardProduction.layout().addLayout(statRow)
        self.cardProduction.setFixedHeight(155)
        grid.addWidget(self.cardProduction, 0, 0, 1, 2)

        # Session panel
        self.cardSession = self._make_card("Session")
        sessionGrid = QGridLayout()
        sessionGrid.setHorizontalSpacing(12)
        sessionGrid.setVerticalSpacing(10)
        sessionGrid.setContentsMargins(0, 0, 10, 0)
        sessionGrid.setColumnStretch(0, 0)
        sessionGrid.setColumnStretch(1, 1)

        self.lblMachine = QLabel("-")
        self.lblJob = QLabel("-")
        self.lblOperator = QLabel("-")

        session_rows = [
            ("Machine", self.lblMachine),
            ("Job", self.lblJob),
            ("Operator", self.lblOperator),
        ]
        for i, (name, value_lbl) in enumerate(session_rows):
            n = self._make_meta_label_with_icon(name)
            value_lbl.setObjectName("MetaValue")
            value_lbl.setMinimumWidth(260)
            value_lbl.setMinimumHeight(40)
            value_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            sessionGrid.addWidget(n, i, 0)
            sessionGrid.addWidget(value_lbl, i, 1)
        self.cardSession.layout().addLayout(sessionGrid)
        self.cardSession.setFixedHeight(175)
        grid.addWidget(self.cardSession, 1, 0)

        # Reject detail panel
        self.cardReject = self._make_card("Reject Details")
        self.rejectDetailGrid = QGridLayout()
        self.rejectDetailGrid.setHorizontalSpacing(8)
        self.rejectDetailGrid.setVerticalSpacing(6)
        self.reject_detail_labels: Dict[str, QLabel] = {}

        for idx, (code, label) in enumerate(REJECT_DETAIL_ITEMS):
            item = QLabel(f"{label} = 0")
            item.setObjectName("MetaValue")
            item.setWordWrap(True)
            item.setMinimumHeight(44)
            item.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.reject_detail_labels[code] = item
            row = idx // 4
            col = idx % 4
            self.rejectDetailGrid.addWidget(item, row, col)

        self.cardReject.layout().addLayout(self.rejectDetailGrid)
        self.cardReject.setFixedHeight(300)
        grid.addWidget(self.cardReject, 2, 0, 1, 2)

        # Job details panel
        self.cardJobDetails = self._make_card("Job Details")
        self.jobDetailGrid = QGridLayout()
        self.jobDetailGrid.setHorizontalSpacing(8)
        self.jobDetailGrid.setVerticalSpacing(6)
        self.jobDetailGrid.setContentsMargins(0, 0, 0, 0)
        self.job_detail_labels: Dict[str, QLabel] = {}

        fields = [
            ("Job Ref", "job_ref"),
            ("Product ID", "product_id"),
            ("Mold", "mold"),
            ("Color", "color"),
            ("System Code", "system_code"),
            ("Cavities", "cavities"),
        ]
        for idx, (title, key) in enumerate(fields):
            card = QFrame()
            card.setObjectName("SubPanel")
            card.setLayout(QVBoxLayout())
            card.layout().setContentsMargins(10, 8, 10, 8)
            card.layout().setSpacing(4)
            if key in ("job_ref", "color"):
                card.layout().setContentsMargins(10, 4, 10, 8)
                card.layout().setSpacing(2)
            t = QLabel(title)
            t.setObjectName("MetaLabel")
            v = QLabel("-")
            v.setObjectName("MetaValue")
            v.setWordWrap(True)
            v.setMinimumHeight(38)
            if key in ("job_ref", "color"):
                v.setMinimumHeight(34)
            card.layout().addWidget(t)
            card.layout().addWidget(v)
            self.job_detail_labels[key] = v
            row = idx // 3
            col = idx % 3
            self.jobDetailGrid.addWidget(card, row, col)

        self.cardJobDetails.layout().addLayout(self.jobDetailGrid)
        self.cardJobDetails.layout().addStretch(1)
        self.cardJobDetails.setFixedHeight(220)
        grid.addWidget(self.cardJobDetails, 3, 0, 1, 2)

        # Activity panel
        self.cardActivity = self._make_card("Activity")
        self.lblLast = QLabel("-")
        self.lblLast.setObjectName("MetaValue")
        self.lblLast.setWordWrap(True)
        self.cardActivity.layout().addWidget(self.lblLast)
        self.cardActivity.setFixedHeight(165)
        grid.addWidget(self.cardActivity, 1, 1)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        left.addLayout(grid)

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
        rightLayout.addWidget(self.rightTitle)
        rightLayout.addWidget(self.rightHint)
        rightLayout.addStretch()

        root.addWidget(leftWrap, 1)
        root.addWidget(self.rightPanel, 1)

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
        self.invalidTextLabel = QLabel("INVALID SCAN")
        self.invalidTextLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.invalidTextLabel.setStyleSheet("color: #ffffff; font-size: 28px; font-weight: 900;")
        gif_shadow = QGraphicsDropShadowEffect(self)
        gif_shadow.setBlurRadius(10)
        gif_shadow.setOffset(0, 0)
        gif_shadow.setColor(Qt.GlobalColor.black)
        self.invalidGifLabel.setGraphicsEffect(gif_shadow)
        text_shadow = QGraphicsDropShadowEffect(self)
        text_shadow.setBlurRadius(8)
        text_shadow.setOffset(0, 0)
        text_shadow.setColor(Qt.GlobalColor.black)
        self.invalidTextLabel.setGraphicsEffect(text_shadow)
        self.invalidOverlay.layout().addWidget(self.invalidGifLabel, 0, Qt.AlignmentFlag.AlignCenter)
        self.invalidOverlay.layout().addWidget(self.invalidTextLabel, 0, Qt.AlignmentFlag.AlignCenter)
        self.invalidOverlay.hide()
        self.invalidOverlay.raise_()
        self._invalid_movie: Optional[QMovie] = None
        self._invalid_hide_timer = QTimer(self)
        self._invalid_hide_timer.setSingleShot(True)
        self._invalid_hide_timer.timeout.connect(self._hide_invalid_overlay)
        self._setup_invalid_overlay_media()

        self.scan_received.connect(self.on_scanned)
        self.scanner_status.connect(self._set_status_text)
        self._setup_scanner_input()

        # heartbeat timer
        self.hb = QTimer(self)
        self.hb.timeout.connect(self.send_heartbeat)
        self.hb.start(5000)

        self.motionTimer = QTimer(self)
        self.motionTimer.timeout.connect(self._tick_motion)
        self.motionTimer.start(220)

        self._refresh_ui()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_invalid_overlay()
        if self._invalid_movie is not None:
            self._invalid_movie.setScaledSize(self._fit_movie_size(self.invalidOverlay.size()))

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
        ratio = min(max_w / frame.width(), max_h / frame.height())
        return QSize(max(1, int(frame.width() * ratio)), max(1, int(frame.height() * ratio)))

    def _position_invalid_overlay(self):
        fm = self.invalidTextLabel.fontMetrics()
        text_w = fm.horizontalAdvance("INVALID SCAN") + 24
        text_h = fm.height() + 12
        gif_size = QSize(220, 140)
        if self._invalid_movie is not None:
            f = self._invalid_movie.currentPixmap().size()
            if f.isValid():
                gif_size = QSize(max(180, min(320, f.width())), max(100, min(240, f.height())))
        w = max(text_w, gif_size.width()) + 30
        h = gif_size.height() + text_h + 34
        x = max(0, (self.width() - w) // 2)
        y = max(0, (self.height() - h) // 2)
        self.invalidOverlay.setGeometry(x, y, w, h)

    def _show_invalid_overlay(self):
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
        self._invalid_hide_timer.start(3000)

    def _hide_invalid_overlay(self):
        if self._invalid_movie is not None:
            self._invalid_movie.stop()
        self.invalidOverlay.hide()

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

    def _find_icon_path(self, key: str) -> Optional[str]:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        for candidate in self._label_icon_candidates.get(key.lower(), []):
            # Try script directory first, then current working directory.
            p1 = os.path.join(base_dir, candidate)
            if os.path.exists(p1):
                return p1
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
        value_label.setObjectName("StatValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f.layout().addWidget(t)
        f.layout().addWidget(value_label)
        return f

    def _pulse_card(self, card: QFrame):
        if card is None:
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
        self.lblMachine.setText(s.machine_name or "-")
        self.lblJob.setText(s.job_name or "-")
        self.lblOperator.setText(self._operator_display_name(s.operator_id))

        self.lblPack.setText(str(s.pack_count))
        self.lblGood.setText(str(s.good_total))
        self.lblButal.setText(str(s.butal_total))
        self.lblReject.setText(str(s.reject_total))
        self.lblTotalGood.setText(str(s.good_total + s.butal_total))

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
            self._set_banner_text("Reject mode: Scan reject reason (BM01/CS02/CO03/CR04/DI05)")
        else:
            self._set_banner_text("Ready: Scan PACK / BUTAL / Reject~1")
        self._refresh_job_details()

    def _session_is_running(self) -> bool:
        s = self.state
        return bool(s.machine_code and s.job_code and s.operator_id and not s.waiting_reject_reason)

    def _tick_motion(self):
        if self._session_is_running():
            frame = self._motion_frames[self._motion_index % len(self._motion_frames)]
            self.machineAnim.setText(frame)
            if self._motion_index % 2 == 0:
                self.banner.setText(f"{self._banner_base_text}  .")
            else:
                self.banner.setText(f"{self._banner_base_text}  ..")
            self._motion_index += 1
        else:
            if not self.state.machine_code:
                self.machineAnim.setText("[M] idle")
            else:
                self.machineAnim.setText("[M] ready")
            self.banner.setText(self._banner_base_text)

    def _refresh_reject_detail_grid(self):
        counts_by_name: Dict[str, int] = {}
        breakdown = self.state.reject_breakdown or {}

        for k, v in breakdown.items():
            key = str(k).strip().upper()
            try:
                qty = int(v or 0)
            except Exception:
                qty = 0
            counts_by_name[key] = counts_by_name.get(key, 0) + qty

        for code, label in REJECT_DETAIL_ITEMS:
            by_name = counts_by_name.get(label.upper(), 0)
            by_code = counts_by_name.get(code.upper(), 0)
            total = by_name if by_name else by_code
            self.reject_detail_labels[code].setText(f"{label} = {total}")

    def _safe_text(self, v: Any, fallback: str = "-") -> str:
        if v is None:
            return fallback
        s = str(v).strip()
        return s if s else fallback

    def _extract_job_record(self) -> Dict[str, Any]:
        payload = self.state.job_payload or {}
        if isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("job"), dict):
            return payload["data"]["job"]
        if isinstance(payload.get("job"), dict):
            return payload["job"]
        return payload if isinstance(payload, dict) else {}

    def _refresh_job_details(self):
        job = self._extract_job_record()
        fields = {
            "job_ref": self._safe_text(job.get("ref_no") or self.state.job_name),
            "product_id": self._safe_text(job.get("product_id")),
            "mold": self._safe_text(job.get("custom_05")),
            "color": self._safe_text(job.get("custom_06"), "N/A"),
            "system_code": self._safe_text(job.get("custom_09")),
            "cavities": self._safe_text(job.get("custom_11")),
        }
        for key, label in self.job_detail_labels.items():
            label.setText(fields.get(key, "-"))

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
        self.banner.setText(self._banner_base_text)
        if not self.state.machine_code:
            self.machineAnim.setText("[M] idle")
        else:
            self.machineAnim.setText("[M] active")

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
        if res.kind == "REJECT_SUMMARY":
            return "Reject summary requested"
        if res.kind == "JOB_STUB":
            return res.value
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
                s.waiting_reject_reason = False
                self.status.setText(f"Reject recorded: {reason}")
                self._refresh_ui()
                self._pulse_card(self.cardStatReject)
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
            s.showing_reject_summary = False
            s.job_payload = {}
            self.status.setText(f"Machine set: {s.machine_name}")
            self._refresh_ui()
            self.push_event({"type": "MACHINE_SET"}, f"MACHINE {s.machine_name}")
            return

        if res.kind in ("JOB", "JOB_STUB"):
            if not s.machine_code:
                self.status.setText("Scan MACHINE first.")
                return

            if res.kind == "JOB":
                s.job_code = raw.strip()
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
            self.status.setText(f"Job set: {s.job_name}")
            self._refresh_ui()
            if res.kind == "JOB":
                self.push_event({"type": "JOB_SET"}, f"JOB {s.job_name}")
            else:
                self.push_event({"type": "JOB_STUB_SET", "stub": s.job_payload}, f"JOB STUB {s.job_name}")
            return

        if res.kind == "REJECT_SUMMARY":
            if not s.machine_code or not s.job_code:
                self.status.setText("Scan MACHINE and JOB first.")
                return
            s.showing_reject_summary = True
            s.waiting_reject_reason = False
            self.status.setText("Reject summary loaded.")
            self._refresh_ui()
            self.push_event({"type": "REJECT_SUMMARY_VIEW"}, "REJECT SUMMARY")
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
                scanned_job_code = self._extract_job_code_from_pack_qr(raw)
                current_job_code = self._normalize_job_code(s.job_code)
                if scanned_job_code is None:
                    self.status.setText("Invalid PACK QR format: missing job code segment.")
                    self._show_invalid_overlay()
                    return
                if current_job_code and scanned_job_code != current_job_code:
                    self.status.setText(
                        f"Invalid PACK QR: job code {scanned_job_code} does not match current job {s.job_code}."
                    )
                    self._show_invalid_overlay()
                    return

                qty = int(res.qty or 0)
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
