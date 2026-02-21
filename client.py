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

from PyQt6.QtCore import (
    Qt, QObject, QEvent, pyqtSignal, QTimer, QSize, QRectF,
    QPropertyAnimation, QEasingCurve, pyqtProperty,
)
from PyQt6.QtGui import QMovie, QPixmap, QColor, QPainter, QPen, QFont
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame, QGridLayout, QSizePolicy,
    QGraphicsDropShadowEffect, QGraphicsBlurEffect, QProgressBar, QPushButton, QComboBox, QScrollArea
)

from mappings import parse_scan, MACHINE_MAP, JOB_MAP, REJECT_REASON_MAP
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
    waiting_maintenance_qr: bool = False
    waiting_supervisor_qr: bool = False
    waiting_operator_downtime_confirm: bool = False
    showing_reject_summary: bool = False
    job_payload: Dict[str, Any] = None
    downtime_reason_code: Optional[str] = None
    downtime_reason_text: Optional[str] = None
    downtime_started_at: Optional[float] = None
    downtime_last_seconds: Optional[int] = None
    downtime_active: bool = False
    cycle_time_current: Optional[str] = None
    cycle_time_new_input: str = ""
    maintenance_name: Optional[str] = None
    supervisor_name: Optional[str] = None
    raw_sacks_count: int = 0
    raw_material_scans: List[str] = None
    raw_material_logs: List[Dict[str, Any]] = None
    raw_material_unique_keys: Set[str] = None
    startup_reject_total: int = 0
    reject_review_open: bool = False
    reject_review_phase: int = 0
    reject_review_actor_code: Optional[str] = None
    reject_review_actor_name: Optional[str] = None
    reject_review_actor_role: Optional[str] = None
    reject_review_logs: List[Dict[str, Any]] = None

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
        if self.reject_review_logs is None:
            self.reject_review_logs = []


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

    def set_target_rect(self, rect: QRectF):
        self._target_rect = QRectF(rect)
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

        max_age = 1.2
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
        duration = 1.2
        u = max(0.0, min(1.0, age / duration))
        start_out = 4.0
        end_out = 24.0
        out = start_out + (end_out - start_out) * (u ** 0.85)
        alpha = int(255 * (1.0 - u) ** 1.6)
        glow_w = 7.0 * (1.0 - u) + 1.4
        core_w = 2.0 * (1.0 - u) + 1.0
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
    scan_received = pyqtSignal(str)
    scanner_status = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.state = ClientState()
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
        root.setSpacing(8)

        leftWrap = QWidget()
        self.leftWrap = leftWrap
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(8)
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

        left.addWidget(self.banner)
        left.addWidget(self.scanSectionDivider)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        # Production panel
        self.cardProductionOuter, self.cardProduction = self._make_double_layer_card("Production")
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
        self.cardProductionOuter.setFixedHeight(171)
        grid.addWidget(self.cardProductionOuter, 0, 0, 1, 2)

        # Session panel
        self.cardSessionOuter, self.cardSession = self._make_double_layer_card("Session")
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
        self.cardSessionOuter.setFixedHeight(191)
        grid.addWidget(self.cardSessionOuter, 1, 0)

        # Reject detail panel
        self.cardRejectOuter, self.cardReject = self._make_double_layer_card("Reject Details")
        self.rejectDetailGrid = QGridLayout()
        self.rejectDetailGrid.setHorizontalSpacing(8)
        self.rejectDetailGrid.setVerticalSpacing(6)
        self.reject_detail_labels: Dict[str, QLabel] = {}

        for idx, (code, label) in enumerate(REJECT_DETAIL_ITEMS):
            item = QLabel(f"{label} = 0")
            item.setObjectName("RejectDetailItem")
            item.setWordWrap(False)
            item.setMinimumHeight(42)
            item.setProperty("active", "0")
            item.setProperty("flash", "0")
            item.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.reject_detail_labels[code] = item
            row = idx // 4
            col = idx % 4
            self.rejectDetailGrid.addWidget(item, row, col)

        self.cardReject.layout().addLayout(self.rejectDetailGrid)
        self.cardRejectOuter.setFixedHeight(316)
        grid.addWidget(self.cardRejectOuter, 2, 0, 1, 2)

        # Job details panel
        self.cardJobDetailsOuter, self.cardJobDetails = self._make_double_layer_card("Job Details")
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
        self.cardJobDetailsOuter.setFixedHeight(236)
        grid.addWidget(self.cardJobDetailsOuter, 3, 0, 1, 2)

        # Activity panel
        self.cardActivityOuter, self.cardActivity = self._make_double_layer_card("Activity")
        self.machineAnim.setText("Machine Status: Idle")
        self.machineAnim.setFixedHeight(40)
        self.machineAnim.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cardActivity.layout().addWidget(self.machineAnim)
        self.lblLast = QLabel("-")
        self.lblLast.setObjectName("MetaValue")
        self.lblLast.setWordWrap(True)
        self.cardActivity.layout().addWidget(self.lblLast)
        self.machinePulseOverlay = HeartbeatBorderPulseOverlay(self.cardActivity)
        self.machinePulseOverlay.setGeometry(self.cardActivity.rect())
        self.machinePulseOverlay.raise_()
        self.cardActivityOuter.setFixedHeight(181)
        grid.addWidget(self.cardActivityOuter, 1, 1)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        left.addLayout(grid)

        left.addStretch(1)

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
        self.rightCycleCount = QLabel("Cycle Count: 0")
        self.rightCycleCount.setObjectName("RightMonitorValue")
        self.rightCycleCurrent = QLabel("Cycle Time: ")
        self.rightCycleCurrent.setObjectName("RightMonitorValue")
        self.rightMaintenance = QLabel("Maintenance: ")
        self.rightMaintenance.setObjectName("RightMonitorValue")
        self.rightSupervisor = QLabel("Supervisor: ")
        self.rightSupervisor.setObjectName("RightMonitorValue")
        self.rightSupervisorLeft = QLabel("Supervisor: -")
        self.rightSupervisorLeft.setObjectName("RightMonitorValue")

        topRow = QHBoxLayout()
        topRow.setSpacing(12)

        rawOuter = QFrame()
        rawOuter.setObjectName("RightCardOuter")
        rawOuterLay = QVBoxLayout()
        rawOuterLay.setContentsMargins(8, 8, 8, 8)
        rawOuterLay.setSpacing(0)
        rawOuter.setLayout(rawOuterLay)

        rawFrame = QFrame()
        rawFrame.setObjectName("RightCardInner")
        rawFrame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        rawCol = QVBoxLayout()
        rawCol.setContentsMargins(12, 10, 12, 10)
        rawCol.setSpacing(6)
        rawFrame.setLayout(rawCol)
        rawCol.addWidget(self._make_right_title_with_icon("Raw Materials Consumption", "raw-material"))
        rawCol.addWidget(self.rightRawHint)
        rawCol.addWidget(self.rightRawSacks)
        rawCol.addWidget(self.rightRawScanned)
        rawOuterLay.addWidget(rawFrame)

        cycleOuter = QFrame()
        cycleOuter.setObjectName("RightCardOuter")
        cycleOuterLay = QVBoxLayout()
        cycleOuterLay.setContentsMargins(8, 8, 8, 8)
        cycleOuterLay.setSpacing(0)
        cycleOuter.setLayout(cycleOuterLay)

        cycleFrame = QFrame()
        cycleFrame.setObjectName("RightCardInner")
        cycleFrame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        cycleCol = QVBoxLayout()
        cycleCol.setContentsMargins(12, 10, 12, 10)
        cycleCol.setSpacing(6)
        cycleFrame.setLayout(cycleCol)
        cycleCol.addWidget(self._make_right_title_with_icon("Cycle Monitor", "cycle"))
        cycleCol.addWidget(self.rightCycleHint)
        cycleCol.addWidget(self.rightCycleCount)
        cycleCol.addWidget(self.rightCycleCurrent)
        cycleOuterLay.addWidget(cycleFrame)

        rawFrame.setMinimumHeight(140)
        cycleFrame.setMinimumHeight(140)
        topRow.addWidget(rawOuter, 1)
        topRow.addWidget(cycleOuter, 1)

        rightLayout.addLayout(topRow)
        rightLayout.addSpacing(10)
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

        rightLayout.addWidget(downtimeOuter)
        rightLayout.addStretch()

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
        self.resolveOverlay.setStyleSheet("")
        self.resolveOverlay.setLayout(QVBoxLayout())
        self.resolveOverlay.layout().setContentsMargins(14, 12, 14, 12)
        self.resolveOverlay.layout().setSpacing(8)
        self.resolveOverlay.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.resolveTitle = QLabel("DOWNTIME RESOLUTION")
        self.resolveTitle.setStyleSheet("color: #0f172a; font-size: 22px; font-weight: 900;")
        self.resolveHint = QLabel("Scan cycle time digits (num_0..num_9), backspace, then confirm")
        self.resolveHint.setStyleSheet("color: #334155; font-size: 14px; font-weight: 700;")
        self.resolveOldCycle = QLabel("Old Cycle Time: -")
        self.resolveOldCycle.setObjectName("MetaValue")
        self.resolveNewCycle = QLabel("Cycle Time: ")
        self.resolveNewCycle.setObjectName("MetaValue")
        self.resolveOverlay.layout().addWidget(self.resolveTitle)
        self.resolveOverlay.layout().addWidget(self.resolveHint)
        self.resolveOverlay.layout().addWidget(self.resolveOldCycle)
        self.resolveOverlay.layout().addWidget(self.resolveNewCycle)
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
        self.rawMatsHint = QLabel('Scan "showrawmats" again to close')
        self.rawMatsHint.setStyleSheet("color: #334155; font-size: 14px; font-weight: 700;")
        self.rawMatsList = QLabel("No raw materials scanned yet.")
        self.rawMatsList.setObjectName("ProductionLiveReason")
        self.rawMatsList.setWordWrap(True)
        self.rawMatsList.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.rawMatsOverlay.layout().addWidget(self.rawMatsTitle)
        self.rawMatsOverlay.layout().addWidget(self.rawMatsHint)
        self.rawMatsOverlay.layout().addWidget(self.rawMatsList)
        self.rawMatsOverlay.hide()
        self.rawMatsOverlay.raise_()

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
        self.settingsNav.layout().addWidget(self.settingsTitle)
        self.settingsNav.layout().addSpacing(8)
        self.settingsNav.layout().addWidget(self.settingsBtnGraphics)
        self.settingsNav.layout().addWidget(self.settingsBtnDisplay)
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

        self.settingsCloseBtn.clicked.connect(self._hide_settings_overlay)
        self.chkCheckAnimation.toggled.connect(self._on_setting_check_animation_toggled)
        self.chkFlashingLights.toggled.connect(self._on_setting_flashing_lights_toggled)
        self.chkPulseEffects.toggled.connect(self._on_setting_pulse_effects_toggled)
        self.settingsBtnGraphics.clicked.connect(lambda: self._show_settings_section("graphics"))
        self.settingsBtnDisplay.clicked.connect(lambda: self._show_settings_section("display"))
        self.displayApplyBtn.clicked.connect(self._apply_display_settings)
        self.settingsContent.layout().addLayout(self.settingsContentTop)
        self.settingsContent.layout().addWidget(self.settingsContentDivider)
        self.settingsContent.layout().addWidget(self.settingsGraphicsSection, 1)
        self.settingsContent.layout().addWidget(self.settingsDisplaySection, 1)
        self.settingsShell.layout().addWidget(self.settingsNav, 0)
        self.settingsShell.layout().addWidget(self.settingsContent, 1)
        self.settingsOverlay.layout().addWidget(self.settingsShell)
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
        self.hb.start(1000)

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
        QTimer.singleShot(0, self._sync_right_panel_top_alignment)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_right_panel_top_alignment()
        self._position_invalid_overlay()
        self._position_production_overlay()
        self._position_resolve_overlay()
        self._position_raw_mats_overlay()
        self._position_reject_review_overlay()
        self._position_finish_overlay()
        self._sync_machine_status_pulse_overlay()

    def _sync_machine_status_pulse_overlay(self):
        if not hasattr(self, "machinePulseOverlay"):
            return
        self.machinePulseOverlay.setGeometry(self.cardActivity.rect())
        top_left = self.machineAnim.mapTo(self.cardActivity, self.machineAnim.rect().topLeft())
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
            target_top = self.banner.mapTo(self, self.banner.rect().topLeft()).y()
            right_top = self.rightPanel.mapTo(self, self.rightPanel.rect().topLeft()).y()
            # Keep first right frame top aligned with scan banner top.
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
        w = min(700, max(460, int(self.width() * 0.52)))
        h = min(360, max(250, int(self.height() * 0.42)))
        x = max(0, (self.width() - w) // 2)
        y = max(0, (self.height() - h) // 2)
        self.resolveOverlay.setGeometry(x, y, w, h)

    def _position_raw_mats_overlay(self):
        w = min(760, max(520, int(self.width() * 0.58)))
        h = min(640, max(360, int(self.height() * 0.65)))
        x = max(0, (self.width() - w) // 2)
        y = max(0, (self.height() - h) // 2)
        self.rawMatsOverlay.setGeometry(x, y, w, h)

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
        h = min(460, max(320, int(self.height() * 0.48)))
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
        mats = self.state.raw_material_scans or []
        if not mats:
            self.rawMatsList.setText("No raw materials scanned yet.")
            return
        self.rawMatsList.setText("\n".join(f"{i}. {name}" for i, name in enumerate(mats, start=1)))

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

    def _reviewer_from_scan(self, raw: str) -> Optional[Dict[str, str]]:
        code = str(raw).strip()
        if code in SUPERVISOR_BADGES:
            return {"code": code, "name": SUPERVISOR_BADGES[code], "role": "SUPERVISOR"}
        if code in QC_BADGES:
            return {"code": code, "name": QC_BADGES[code], "role": "QC"}
        return None

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
        value_label.setObjectName("StatValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
            self._set_banner_text("Reject mode: Scan reason (BM01/CS02/CO03/CR04/DI05) or SUR")
        elif s.waiting_production_report_reason:
            self._set_banner_text("Production Daily Report mode: Scan reason QR (01-15)")
        elif s.waiting_cycle_time_input:
            self._set_banner_text("Downtime resolve: Scan cycle time digits, then confirm")
        elif s.waiting_maintenance_qr:
            self._set_banner_text("Downtime resolve: Scan Maintenance QR (2000001)")
        elif s.waiting_supervisor_qr:
            self._set_banner_text("Downtime resolve: Scan Supervisor QR (3000001)")
        elif s.waiting_operator_downtime_confirm:
            self._set_banner_text("Downtime resolve: Scan Operator QR to confirm")
        elif s.downtime_active:
            self._set_banner_text('Downtime active: scan "productiondailyreport~2" or SUR')
        else:
            self._set_banner_text("Ready: Scan PACK / BUTAL / Reject~1")
        self._refresh_job_details()
        self._refresh_downtime_panel()

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
        status_text = "Active" if is_active else "Idle"
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
        if s.raw_material_scans:
            self.rightRawScanned.setText(f"Raw Mats Scanned: {', '.join(s.raw_material_scans[-8:])}")
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

    def _save_finished_job_local(self, payload: Dict[str, Any]):
        os.makedirs(DATABASE_DIR, exist_ok=True)
        p = os.path.join(DATABASE_DIR, "finished_jobs_client.json")
        rows: List[Dict[str, Any]] = []
        try:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, list):
                    rows = loaded
        except Exception:
            rows = []
        rows.append(payload)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)

    def _active_session_file_path(self) -> str:
        os.makedirs(DATABASE_DIR, exist_ok=True)
        return os.path.join(DATABASE_DIR, "active_machine_sessions.json")

    def _load_active_sessions_map(self) -> Dict[str, Any]:
        p = self._active_session_file_path()
        try:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    return loaded
        except Exception:
            pass
        return {}

    def _save_active_sessions_map(self, rows: Dict[str, Any]):
        p = self._active_session_file_path()
        with open(p, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)

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
            "job_payload": s.job_payload or {},
            "downtime_reason_code": s.downtime_reason_code,
            "downtime_reason_text": s.downtime_reason_text,
            "downtime_started_at": s.downtime_started_at,
            "downtime_last_seconds": s.downtime_last_seconds,
            "downtime_active": bool(s.downtime_active),
            "cycle_time_current": s.cycle_time_current,
            "cycle_time_new_input": s.cycle_time_new_input,
            "waiting_cycle_time_input": bool(s.waiting_cycle_time_input),
            "waiting_maintenance_qr": bool(s.waiting_maintenance_qr),
            "waiting_supervisor_qr": bool(s.waiting_supervisor_qr),
            "waiting_operator_downtime_confirm": bool(s.waiting_operator_downtime_confirm),
            "maintenance_name": s.maintenance_name,
            "supervisor_name": s.supervisor_name,
            "raw_sacks_count": int(s.raw_sacks_count or 0),
            "raw_material_scans": list(s.raw_material_scans or []),
            "raw_material_logs": list(s.raw_material_logs or []),
            "raw_material_unique_keys": sorted(list(s.raw_material_unique_keys or set())),
            "startup_reject_total": int(s.startup_reject_total or 0),
            "reject_review_open": bool(s.reject_review_open),
            "reject_review_phase": int(s.reject_review_phase or 0),
            "reject_review_actor_code": s.reject_review_actor_code,
            "reject_review_actor_name": s.reject_review_actor_name,
            "reject_review_actor_role": s.reject_review_actor_role,
            "reject_review_logs": list(s.reject_review_logs or []),
        }

    def _save_active_session_snapshot(self):
        s = self.state
        machine_code = str(s.machine_code or "").strip()
        if not machine_code:
            return
        rows = self._load_active_sessions_map()
        rows[machine_code] = self._state_to_active_snapshot()
        self._save_active_sessions_map(rows)

    def _load_active_session_snapshot(self, machine_code: str) -> Optional[Dict[str, Any]]:
        rows = self._load_active_sessions_map()
        snap = rows.get(str(machine_code or "").strip())
        if isinstance(snap, dict):
            return snap
        return None

    def _clear_active_session_snapshot(self, machine_code: Optional[str]):
        code = str(machine_code or "").strip()
        if not code:
            return
        rows = self._load_active_sessions_map()
        if code in rows:
            del rows[code]
            self._save_active_sessions_map(rows)

    def _restore_state_from_snapshot(self, snap: Dict[str, Any]):
        s = self.state
        s.machine_code = snap.get("machine_code")
        s.machine_name = snap.get("machine_name")
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
        s.job_payload = snap.get("job_payload") or {}
        s.downtime_reason_code = snap.get("downtime_reason_code")
        s.downtime_reason_text = snap.get("downtime_reason_text")
        s.downtime_started_at = snap.get("downtime_started_at")
        s.downtime_last_seconds = snap.get("downtime_last_seconds")
        s.downtime_active = bool(snap.get("downtime_active"))
        s.cycle_time_current = snap.get("cycle_time_current")
        s.cycle_time_new_input = str(snap.get("cycle_time_new_input") or "")
        s.waiting_cycle_time_input = bool(snap.get("waiting_cycle_time_input"))
        s.waiting_maintenance_qr = bool(snap.get("waiting_maintenance_qr"))
        s.waiting_supervisor_qr = bool(snap.get("waiting_supervisor_qr"))
        s.waiting_operator_downtime_confirm = bool(snap.get("waiting_operator_downtime_confirm"))
        s.maintenance_name = snap.get("maintenance_name")
        s.supervisor_name = snap.get("supervisor_name")
        s.raw_sacks_count = int(snap.get("raw_sacks_count") or 0)
        s.raw_material_scans = list(snap.get("raw_material_scans") or [])
        s.raw_material_logs = list(snap.get("raw_material_logs") or [])
        s.raw_material_unique_keys = set(snap.get("raw_material_unique_keys") or [])
        s.startup_reject_total = int(snap.get("startup_reject_total") or 0)
        s.reject_review_open = bool(snap.get("reject_review_open"))
        s.reject_review_phase = int(snap.get("reject_review_phase") or 0)
        s.reject_review_actor_code = snap.get("reject_review_actor_code")
        s.reject_review_actor_name = snap.get("reject_review_actor_name")
        s.reject_review_actor_role = snap.get("reject_review_actor_role")
        s.reject_review_logs = list(snap.get("reject_review_logs") or [])
        self._refresh_ui()

    def _build_finished_job_payload(self) -> Dict[str, Any]:
        s = self.state
        return {
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "client_id": CLIENT_ID,
            "machine_code": s.machine_code,
            "machine_name": s.machine_name,
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
            "job_payload": s.job_payload or {},
            "reject_review_logs": list(s.reject_review_logs or []),
            "downtime_last_seconds": s.downtime_last_seconds,
            "downtime_reason_code": s.downtime_reason_code,
            "downtime_reason_text": s.downtime_reason_text,
            "cycle_time_current": s.cycle_time_current,
            "maintenance_name": s.maintenance_name,
            "supervisor_name": s.supervisor_name,
        }

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
        s.job_payload = {}
        s.downtime_reason_code = None
        s.downtime_reason_text = None
        s.downtime_started_at = None
        s.downtime_last_seconds = None
        s.downtime_active = False
        s.cycle_time_current = None
        s.maintenance_name = None
        s.supervisor_name = None
        s.raw_sacks_count = 0
        s.raw_material_scans = []
        s.raw_material_logs = []
        s.raw_material_unique_keys = set()
        s.startup_reject_total = 0
        s.reject_review_logs = []
        self._reset_downtime_resolution_state()
        self._hide_resolve_overlay()
        self._hide_production_overlay()
        self._hide_raw_mats_overlay()
        self._hide_reject_review_overlay()
        self._clear_active_session_snapshot(active_machine_code)
        self._refresh_ui()
        self.rightCycleCount.setText(f"Cycle Count: {s.pack_count}")
        self.rightCycleCurrent.setText(f"Cycle Time: {s.cycle_time_current or ''}")
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

    def _begin_downtime_resolution(self):
        s = self.state
        self._reset_downtime_resolution_state()
        s.waiting_cycle_time_input = True
        s.cycle_time_new_input = ""
        self._hide_production_overlay()
        self.resolveTitle.setText("DOWNTIME RESOLUTION")
        self.resolveHint.setText("Scan cycle time digits (num_0..num_9), backspace, then confirm")
        self.resolveOldCycle.setText(f"Old Cycle Time: {s.cycle_time_current or '-'}")
        self.resolveNewCycle.setText("Cycle Time: ")
        self._show_resolve_overlay()

    def _update_cycle_input_display(self):
        self.resolveNewCycle.setText(f"Cycle Time: {self.state.cycle_time_new_input}")

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
            item = self.reject_detail_labels[code]
            item.setText(f"{label} = {total}")
            is_active = total == 1
            item.setProperty("active", "1" if is_active else "0")
            if not is_active or not self.enable_flashing_lights:
                item.setProperty("flash", "0")
            item.style().unpolish(item)
            item.style().polish(item)

    def _tick_reject_detail_flash(self):
        if not self.enable_flashing_lights:
            return
        self._reject_detail_flash_on = not self._reject_detail_flash_on
        flash_value = "1" if self._reject_detail_flash_on else "0"
        for item in self.reject_detail_labels.values():
            if item.property("active") == "1":
                item.setProperty("flash", flash_value)
                item.style().unpolish(item)
                item.style().polish(item)

    def _on_setting_check_animation_toggled(self, checked: bool):
        self.enable_check_animation = bool(checked)
        self._set_toggle_button_text(self.chkCheckAnimation, "Check animation", self.enable_check_animation)

    def _on_setting_flashing_lights_toggled(self, checked: bool):
        self.enable_flashing_lights = bool(checked)
        self._set_toggle_button_text(self.chkFlashingLights, "Flashing lights", self.enable_flashing_lights)
        if not self.enable_flashing_lights:
            for item in self.reject_detail_labels.values():
                item.setProperty("flash", "0")
                item.style().unpolish(item)
                item.style().polish(item)

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
        self.settingsBtnGraphics.setChecked(is_graphics)
        self.settingsBtnDisplay.setChecked(not is_graphics)
        self.settingsGraphicsSection.setVisible(is_graphics)
        self.settingsDisplaySection.setVisible(not is_graphics)
        if is_graphics:
            self.settingsContentTitle.setText("Graphics")
        else:
            self.settingsContentTitle.setText("Display")

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
            or self.rejectReviewOverlay.isVisible()
            or self.finishOverlay.isVisible()
            or self.settingsOverlay.isVisible()
        )

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
        if res.kind == "PRODUCTION_DAILY_REPORT_TRIGGER":
            return "Production daily report mode enabled"
        if res.kind == "PRODUCTION_DAILY_REPORT_RESOLVE":
            return "Production daily report resolve"
        if res.kind == "JOB_STUB":
            return res.value
        return "Scan received"

    def log_last(self, text: str):
        self.lblLast.setText(text)

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
        if self._finish_anim_running:
            self.status.setText("Finish job in progress. Please wait.")
            return
        raw_s = str(raw).strip()
        raw_l = raw_s.lower()
        s = self.state

        reviewer = self._reviewer_from_scan(raw_s)
        if reviewer is not None:
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

        if raw_l == "showrawmats":
            if self.rawMatsOverlay.isVisible():
                self._hide_raw_mats_overlay()
                self.status.setText("Raw materials list closed.")
            else:
                self._show_raw_mats_overlay()
                self.status.setText("Raw materials list opened.")
            return

        if self.rawMatsOverlay.isVisible():
            self._hide_raw_mats_overlay()

        res_pre = parse_scan(raw_s)

        # Raw material scanning: no mode/state required, only needs active session.
        if res_pre and res_pre.kind == "RAW_MATERIAL":
            if not self.can_accept_production_scans():
                self.status.setText("Complete session first: MACHINE -> JOB -> OPERATOR.")
                return
            meta = res_pre.meta if isinstance(res_pre.meta, dict) else {}
            raw_job_code = self._normalize_job_code(meta.get("job_code")) if meta.get("job_code") else ""
            current_job_code = self._normalize_job_code(s.job_code)
            if raw_job_code and current_job_code and raw_job_code != current_job_code:
                self.status.setText(
                    f"Invalid RAW MATERIAL QR: job code {raw_job_code} does not match current job {s.job_code}."
                )
                self._show_invalid_overlay()
                return

            unique_key = str(meta.get("unique_key") or "").strip()
            if unique_key and unique_key in s.raw_material_unique_keys:
                self.status.setText("Invalid RAW MATERIAL QR: duplicate serial already scanned.")
                self._show_invalid_overlay()
                return

            qty = int(res_pre.qty or 1)
            s.raw_sacks_count += qty
            s.raw_material_scans.append(res_pre.value)
            s.raw_material_logs.append(
                {
                    "material": res_pre.value,
                    "qty": qty,
                    "unique_key": unique_key or None,
                    "raw_job_code": raw_job_code or None,
                    "scanned_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            if unique_key:
                s.raw_material_unique_keys.add(unique_key)
            self.log_last(self._scan_display_text(res_pre, raw_s))
            self.status.setText(f"Raw material scanned: {res_pre.value} (+{qty})")
            self._refresh_ui()
            self.push_event(
                {
                    "type": "RAW_MATERIAL",
                    "material": res_pre.value,
                    "qty": qty,
                    "unique_key": unique_key or None,
                    "raw_job_code": raw_job_code or None,
                },
                f"RAW MATERIAL {res_pre.value} +{qty}",
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
                self.resolveHint.setText("Scan Maintenance QR (2000001)")
                self.resolveNewCycle.setText(f"Cycle Time: {s.cycle_time_current}")
                return
            self.status.setText("Cycle Time input mode: scan num_0..num_9, backspace, confirm.")
            return

        # Resolution step 2: Maintenance
        if s.waiting_maintenance_qr:
            if raw_s == "2000001":
                s.maintenance_name = "Lucy Van Pelt"
                s.waiting_maintenance_qr = False
                s.waiting_supervisor_qr = True
                self.resolveHint.setText("Scan Supervisor QR (3000001)")
                self._refresh_downtime_panel()
                return
            self.status.setText("Scan valid Maintenance QR (2000001).")
            return

        # Resolution step 3: Supervisor
        if s.waiting_supervisor_qr:
            if raw_s == "3000001":
                s.supervisor_name = "Charlie Brown"
                s.waiting_supervisor_qr = False
                s.waiting_operator_downtime_confirm = True
                self.resolveHint.setText("Scan Operator QR to confirm.")
                self._refresh_downtime_panel()
                return
            self.status.setText("Scan valid Supervisor QR (3000001).")
            return

        # Resolution step 4: Operator confirmation
        if s.waiting_operator_downtime_confirm:
            res_op = parse_scan(raw_s)
            if res_op and res_op.kind == "OPERATOR":
                scanned_operator_code = self._operator_code_only(res_op.value)
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
            self.status.setText("Scan operator QR to confirm.")
            return

        # Downtime lock: allow resolve trigger and SUR while active
        if s.downtime_active and raw_l not in ("productiondailyreport~2", "sur"):
            self.status.setText('Downtime active: only "productiondailyreport~2" or "SUR" is allowed.')
            return

        res = parse_scan(raw_s)
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
            self.status.setText("Unknown scan (ignored).")
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
            finished_payload = self._build_finished_job_payload()
            try:
                self._save_finished_job_local(finished_payload)
            except Exception as e:
                self.status.setText(f"Finish saved to server only (local JSON failed: {e})")
            self.push_event(
                {"type": "FINISH_JOB", "finished_job": finished_payload},
                f"FINISH JOB {s.job_name or s.job_code or ''}".strip(),
            )
            self.status.setText("Finishing job...")
            self._finish_pending_clear = True
            self._show_finish_overlay()
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
                self.status.setText("Complete session first: MACHINE -> JOB -> OPERATOR.")
                return
            s.startup_reject_total += 1
            self.status.setText("Start Up Reject recorded.")
            self._refresh_ui()
            self.push_event({"type": "STARTUP_REJECT", "qty": 1}, "STARTUP REJECT +1")
            return

        if res.kind == "MACHINE":
            if s.machine_code:
                self.status.setText("Finish your current job first before changing machine.")
                self._show_invalid_overlay()
                return
            snap = self._load_active_session_snapshot(raw_s)
            if snap is not None and str(snap.get("job_code") or "").strip():
                self._restore_state_from_snapshot(snap)
                if not self.state.machine_name:
                    self.state.machine_name = res.value
                self.status.setText(
                    f"Recovered ongoing session for {self.state.machine_name} / {self.state.job_name or self.state.job_code}."
                )
                self.push_event({"type": "SESSION_RESUME"}, "SESSION RESUMED")
                self.sync_session_snapshot_to_server("SESSION SNAPSHOT SYNC (RESUME)")
                return
            s.machine_code = raw_s
            s.machine_name = res.value
            s.job_code = None
            s.job_name = None
            s.operator_id = None
            s.waiting_reject_reason = False
            s.waiting_production_report_reason = False
            s.showing_reject_summary = False
            s.job_payload = {}
            s.downtime_reason_code = None
            s.downtime_reason_text = None
            s.downtime_started_at = None
            s.downtime_last_seconds = None
            s.downtime_active = False
            s.cycle_time_current = None
            s.maintenance_name = None
            s.supervisor_name = None
            s.raw_sacks_count = 0
            s.raw_material_scans = []
            s.raw_material_logs = []
            s.raw_material_unique_keys = set()
            s.startup_reject_total = 0
            s.reject_review_logs = []
            self._reset_downtime_resolution_state()
            self._hide_resolve_overlay()
            self._hide_production_overlay()
            self._hide_raw_mats_overlay()
            self._hide_reject_review_overlay()
            self.status.setText(f"Machine set: {s.machine_name}")
            self._refresh_ui()
            self._save_active_session_snapshot()
            self.push_event({"type": "MACHINE_SET"}, f"MACHINE {s.machine_name}")
            self.sync_session_snapshot_to_server("SESSION SNAPSHOT SYNC (FIRST SCAN)")
            return

        if res.kind in ("JOB", "JOB_STUB"):
            if s.machine_code and s.job_code and s.operator_id:
                self.status.setText("Finish your current job first before changing machine or job.")
                return
            if not s.machine_code:
                self.status.setText("Scan MACHINE first.")
                return
            if res.kind == "JOB":
                po_from_meta = ""
                if isinstance(res.meta, dict):
                    po_from_meta = self._safe_text(res.meta.get("po_number"), "")
                s.job_code = po_from_meta or raw_s
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
            s.downtime_reason_code = None
            s.downtime_reason_text = None
            s.downtime_started_at = None
            s.downtime_last_seconds = None
            s.downtime_active = False
            s.maintenance_name = None
            s.supervisor_name = None
            s.raw_sacks_count = 0
            s.raw_material_scans = []
            s.raw_material_logs = []
            s.raw_material_unique_keys = set()
            s.startup_reject_total = 0
            s.reject_review_logs = []
            self._reset_downtime_resolution_state()
            self._hide_resolve_overlay()
            self._hide_production_overlay()
            self._hide_raw_mats_overlay()
            self._hide_reject_review_overlay()
            self.status.setText(f"Job set: {s.job_name}")
            self._refresh_ui()
            self._save_active_session_snapshot()
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
            s.waiting_production_report_reason = False
            self._hide_production_overlay()
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
            self._save_active_session_snapshot()
            self.push_event({"type": "OPERATOR_SET"}, f"OPERATOR {s.operator_id}")
            return

        if res.kind in ("PACK", "BUTAL", "REJECT_TRIGGER", "PRODUCTION_DAILY_REPORT_TRIGGER"):
            if not self.can_accept_production_scans():
                self.status.setText("Complete session first: MACHINE -> JOB -> OPERATOR.")
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


