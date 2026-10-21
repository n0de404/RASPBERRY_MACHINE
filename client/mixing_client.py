"""Standalone Mixing Mode prototype for the machine client.

Run this file instead of ``client.py`` while testing Mixing Mode.  It reuses
the production client's UI and workflow without changing ``client.py``.

Mixing rules:
* a finished-product QR is one SACK, as a PACK QR is in the normal client;
* a finished-product QR's quantity remains the finished weight (for example,
  one sack whose QR quantity is 50 records 50 kg);
* each sack consumes each product part's configured Part Qty/Unit;
* scanned product-part quantities remain available across shifts, while the
  Request Part Qty display keeps a cumulative total of the original scans.

By default runtime/session data is stored under Database/mixing_mode so a
trial cannot overwrite the normal client's active session.  Set
MIXING_USE_MAIN_DATA=1 only when deliberately sharing normal client data.
"""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import re
import shutil
import sys
import time
from typing import Any, Dict, List, Optional


CLIENT_DIR = Path(__file__).resolve().parent
MAIN_DATA_DIR = CLIENT_DIR / "Database"
MIXING_DATA_DIR = Path(
    os.environ.get("MIXING_DATA_DIR", str(MAIN_DATA_DIR / "mixing_mode"))
).expanduser().resolve()
MIXING_MULTI_JOB_PATH = MIXING_DATA_DIR / "multi_job_sessions.json"
MIXING_PARTIAL_API_STUB_PATH = MIXING_DATA_DIR / "partial_api_stub.json"
MIXING_PARTIAL_API_OUTBOX_PATH = MIXING_DATA_DIR / "partial_api_outbox.json"


def _prepare_mixing_runtime() -> None:
    """Select isolated state and seed only configuration/cache files."""
    share_main = os.environ.get("MIXING_USE_MAIN_DATA", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if share_main:
        return

    os.environ.setdefault("MACHINE_DATA_DIR", str(MIXING_DATA_DIR))
    MIXING_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in (
        "job_api_config.json",
        "client_settings.json",
        "sql_config.json",
        "user_qr_profiles.json",
        "local_operator_cache.json",
        "product_catalog_cache.json",
        "job_details_cache.json",
    ):
        source = MAIN_DATA_DIR / name
        target = MIXING_DATA_DIR / name
        if source.is_file() and not target.exists():
            shutil.copy2(source, target)


_prepare_mixing_runtime()
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

import client as production_client  # noqa: E402  (runtime must be selected first)


_PACK_WORD = re.compile(r"\bpack(s)?\b", flags=re.IGNORECASE)
_MIXING_MACHINE_QR_ALIASES = {
    "MT301": "MT-301",
    "MT302": "MT-302",
    "MT303": "MT-303",
}
_MIXING_SCAN_JOB_FIRST = "__MIXING_SCAN_JOB_FIRST__"

# ``parse_scan`` uses the production module's machine map. These canonical
# entries exist only in the standalone Mixing Mode process.
for _mixing_machine_name in _MIXING_MACHINE_QR_ALIASES.values():
    production_client.MACHINE_MAP[_mixing_machine_name] = _mixing_machine_name


class _SerialScanFramer:
    """Split scanner input on CR, LF, or CRLF without waiting for another QR."""

    def __init__(self):
        self._buffer = bytearray()

    @staticmethod
    def _decode(raw: bytes) -> str:
        return raw.decode("utf-8", errors="ignore").strip()

    def feed(self, chunk: bytes) -> List[str]:
        if chunk:
            self._buffer.extend(chunk)
        data = bytes(self._buffer)
        frames: List[str] = []
        start = 0
        index = 0
        while index < len(data):
            if data[index] not in (10, 13):
                index += 1
                continue
            text = self._decode(data[start:index])
            if text:
                frames.append(text)
            index += 1
            while index < len(data) and data[index] in (10, 13):
                index += 1
            start = index
        self._buffer = bytearray(data[start:])
        return frames

    def flush(self) -> List[str]:
        text = self._decode(bytes(self._buffer))
        self._buffer.clear()
        return [text] if text else []


class _MixingScannerFilter(production_client.ScannerFilter):
    """Keyboard-scanner filter that does not require an Enter suffix."""

    # Some USB/HID scanners pause for 60-100 ms while sending a long,
    # high-density QR.  A 60 ms cutoff split one physical QR into a prefix and
    # tail, so the tail was not handled until the next scan.  A quarter-second
    # idle window is still immediate to the operator but safely keeps the full
    # structured payload together.
    IDLE_COMPLETE_MS = 250

    def __init__(self, plain_digit_numpad_enabled=None):
        super().__init__(plain_digit_numpad_enabled=plain_digit_numpad_enabled)
        self._idle_complete_timer = production_client.QTimer(self)
        self._idle_complete_timer.setSingleShot(True)
        self._idle_complete_timer.timeout.connect(self._emit_buffered_scan)

    def _emit_buffered_scan(self) -> None:
        text = "".join(self._buf).strip()
        self._buf.clear()
        if text:
            self.scanned.emit(text)

    def eventFilter(self, obj, event):
        handled = super().eventFilter(obj, event)
        if event.type() == production_client.QEvent.Type.KeyPress:
            if self._buf:
                self._idle_complete_timer.start(self.IDLE_COMPLETE_MS)
            else:
                self._idle_complete_timer.stop()
        return handled


def replace_pack_terms(text: Any) -> str:
    """Replace visible Pack/Packs wording while preserving letter case."""
    value = str(text or "")

    def replacement(match: re.Match[str]) -> str:
        plural = bool(match.group(1))
        source = match.group(0)
        target = "sacks" if plural else "sack"
        if source.isupper():
            return target.upper()
        if source[:1].isupper():
            return target.capitalize()
        return target

    return _PACK_WORD.sub(replacement, value)


class MixingClientUI(production_client.ClientUI):
    """Production ClientUI with isolated, scan-driven mixing totals."""

    def __init__(self):
        self._mixing_mode_ready = False
        self._mixing_partial_push_in_flight = False
        self._mixing_full_ui_restored = False
        self._mixing_sessions: Dict[str, Dict[str, Any]] = {}
        self._mixing_active_job_key = ""
        self._mixing_history_synced_keys = set()
        self._load_mixing_sessions()
        super().__init__()
        self._mixing_mode_ready = True
        self.setWindowTitle("Machine Client Dashboard - Mixing Mode")
        self._configure_mixing_partial_api_settings()
        self._ensure_mixing_history_cutoff()
        self._mixing_partial_outbox_timer = production_client.QTimer(self)
        self._mixing_partial_outbox_timer.setSingleShot(True)
        self._mixing_partial_outbox_timer.timeout.connect(
            self._drain_mixing_partial_api_outbox
        )
        production_client.QTimer.singleShot(
            5000, self._drain_mixing_partial_api_outbox
        )
        self._build_mixing_jobs_panel()
        self._configure_mixing_jobs_grid()
        self._configure_compact_pack_gap_warning()
        self._configure_mixing_finish_modal()
        self._apply_mixing_panel_visibility()
        self._apply_mixing_labels()
        self._clear_external_average_weight()
        self._sync_mixing_material_history_from_server()
        # The dashboard server may still be starting when Mixing Mode opens.
        # Retry shortly after the window is live; a successful key is cached.
        production_client.QTimer.singleShot(
            2500, self._sync_mixing_material_history_and_refresh
        )
        production_client.QTimer.singleShot(
            7000, self._sync_mixing_material_history_and_refresh
        )
        production_client.QTimer.singleShot(
            1200, self._activate_registry_open_job
        )
        production_client.QTimer.singleShot(
            3500, self._activate_registry_open_job
        )
        self._capture_current_mixing_session()
        self._refresh_mixing_jobs_panel()

    def _mixing_partial_api_mode(self) -> str:
        """Return the persisted shift-partial destination."""
        mode = str(
            (self.client_config or {}).get("mixing_partial_api_mode", "stub")
        ).strip().lower()
        return "api" if mode == "api" else "stub"

    def _ensure_mixing_history_cutoff(self) -> None:
        """Keep a fresh install from importing older server carryovers."""
        if str(
            (self.client_config or {}).get("mixing_history_not_before_utc", "")
            or ""
        ).strip():
            return
        candidate = dict(self.client_config or {})
        candidate["mixing_history_not_before_utc"] = (
            production_client.datetime.now(production_client.timezone.utc).isoformat()
        )
        if production_client._save_client_config(candidate):
            self.client_config = candidate

    def _configure_mixing_partial_api_settings(self) -> None:
        """Add the Mixing-only Stub/API selector to API Config settings."""
        self.apiMixingPartialModeLabel = production_client.QLabel(
            "Mixing Shift Partial Destination"
        )
        self.apiMixingPartialModeLabel.setObjectName("MetaLabel")
        self.apiMixingPartialModeCombo = production_client.QComboBox()
        self.apiMixingPartialModeCombo.setProperty(
            "app_log_name", "Mixing Partial Destination"
        )
        self.apiMixingPartialModeCombo.addItem("Stub (local test)", "stub")
        self.apiMixingPartialModeCombo.addItem("API (live)", "api")
        self.apiMixingPartialModeCombo.setFixedWidth(320)
        self.apiMixingPartialModeHelp = production_client.QLabel(
            "Stub writes partial_api_stub.json only. API sends the shift to "
            "the real Job API through the configured Machine Server URL."
        )
        self.apiMixingPartialModeHelp.setObjectName("MetaValue")
        self.apiMixingPartialModeHelp.setWordWrap(True)
        self.apiMixingPartialModeHelp.setStyleSheet(
            "color: #cbd5e1; font-size: 12px; font-weight: 800; "
            "background: transparent;"
        )
        layout = self.settingsApiSection.layout()
        apply_index = layout.indexOf(self.apiApplyBtn)
        insert_at = apply_index if apply_index >= 0 else layout.count()
        layout.insertWidget(insert_at, self.apiMixingPartialModeLabel)
        layout.insertWidget(
            insert_at + 1,
            self.apiMixingPartialModeCombo,
            0,
            production_client.Qt.AlignmentFlag.AlignLeft,
        )
        layout.insertWidget(insert_at + 2, self.apiMixingPartialModeHelp)
        selected = self.apiMixingPartialModeCombo.findData(
            self._mixing_partial_api_mode()
        )
        self.apiMixingPartialModeCombo.setCurrentIndex(max(0, selected))
        self.apiMixingPartialModeCombo.currentIndexChanged.connect(
            self._save_mixing_partial_api_mode
        )

    def _save_mixing_partial_api_mode(self, _index: int = -1) -> None:
        mode = str(self.apiMixingPartialModeCombo.currentData() or "stub")
        candidate = dict(self.client_config or {})
        candidate["mixing_partial_api_mode"] = mode
        if not production_client._save_client_config(candidate):
            self.status.setText(
                "Mixing partial destination was not saved. Check Database permissions."
            )
            return
        self.client_config = candidate
        label = "LIVE API" if mode == "api" else "STUB"
        self._append_app_log(
            "SETTINGS", f"Mixing partial destination changed to {label}"
        )
        self.status.setText(f"Mixing shift partial destination: {label}.")

    def _configure_mixing_finish_modal(self) -> None:
        """Restyle the inherited review as a dedicated Mixing confirmation."""
        overlay_layout = self.finishOverlay.layout()
        overlay_layout.setContentsMargins(28, 20, 28, 20)
        overlay_layout.setSpacing(12)
        for widget in (
            self.finishTitle,
            self.finishStatus,
            self.finishReviewHint,
            self.finishReviewPageInfo,
        ):
            overlay_layout.removeWidget(widget)

        header = production_client.QFrame()
        header.setObjectName("MixingFinishHeader")
        header.setLayout(production_client.QHBoxLayout())
        header.layout().setContentsMargins(0, 0, 0, 0)
        header.layout().setSpacing(10)
        title_box = production_client.QWidget()
        title_box.setObjectName("MixingFinishTitleBox")
        title_box.setLayout(production_client.QVBoxLayout())
        title_box.layout().setContentsMargins(0, 0, 0, 0)
        title_box.layout().setSpacing(0)
        self.mixingFinishEyebrow = production_client.QLabel("END OF SHIFT")
        self.mixingFinishEyebrow.setObjectName("MixingFinishEyebrow")
        title_box.layout().addWidget(self.mixingFinishEyebrow)
        title_box.layout().addWidget(self.finishTitle)
        header.layout().addWidget(title_box, 1)
        header.layout().addWidget(
            self.finishReviewPageInfo,
            0,
            production_client.Qt.AlignmentFlag.AlignRight
            | production_client.Qt.AlignmentFlag.AlignVCenter,
        )
        overlay_layout.insertWidget(0, header)
        self.mixingFinishHeader = header
        self.finishStatus.hide()
        self.finishReviewHint.hide()
        for widget in (
            self.finishSummaryScroll,
            self.finishSummaryBody,
            self.finishSummaryStack,
            self.finishReviewPageOne,
            self.finishReviewPageTwo,
            self.finishReviewPageThree,
            self.finishReviewPageFour,
        ):
            widget.setAutoFillBackground(False)
            widget.setStyleSheet("background:transparent; border:none;")

        footer = production_client.QFrame()
        footer.setObjectName("MixingFinishFooter")
        footer.setLayout(production_client.QHBoxLayout())
        footer.layout().setContentsMargins(0, 0, 0, 0)
        footer.layout().setSpacing(12)

        def add_instruction(
            object_name: str,
            heading: str,
            instruction: str,
            stretch: int,
        ):
            panel = production_client.QFrame()
            panel.setObjectName(object_name)
            panel.setLayout(production_client.QVBoxLayout())
            panel.layout().setContentsMargins(15, 9, 15, 9)
            panel.layout().setSpacing(2)
            heading_label = production_client.QLabel(heading)
            heading_label.setProperty("role", "heading")
            instruction_label = production_client.QLabel(instruction)
            instruction_label.setProperty("role", "instruction")
            panel.layout().addWidget(heading_label)
            panel.layout().addWidget(instruction_label)
            footer.layout().addWidget(panel, stretch)
            return heading_label, instruction_label

        self.mixingFinishReviewHeading, self.mixingFinishReviewInstruction = (
            add_instruction(
                "MixingReviewInstruction",
                "REVIEW",
                "Scan NEXT / PREV",
                3,
            )
        )
        self.mixingFinishConfirmHeading, self.mixingFinishConfirmInstruction = (
            add_instruction(
                "MixingConfirmInstruction",
                "CONFIRM SHIFT",
                "Scan Operator / Mixer QR",
                5,
            )
        )
        self.mixingFinishCancelHeading, self.mixingFinishCancelInstruction = (
            add_instruction(
                "MixingCancelInstruction",
                "CANCEL",
                "Scan Operator Shift QR",
                3,
            )
        )
        overlay_layout.addWidget(footer)
        footer_panel_styles = {
            "MixingReviewInstruction": (
                "QFrame { background:#383e47; border:2px solid #89919d; border-radius:11px; }"
                "QLabel { background:transparent; border:none; }"
            ),
            "MixingConfirmInstruction": (
                "QFrame { background:#22945f; border:2px solid #43d18d; border-radius:11px; }"
                "QLabel { background:transparent; border:none; }"
            ),
            "MixingCancelInstruction": (
                "QFrame { background:#211316; border:2px solid #d6535e; border-radius:11px; }"
                "QLabel { background:transparent; border:none; }"
            ),
        }
        for object_name, style in footer_panel_styles.items():
            panel = footer.findChild(production_client.QFrame, object_name)
            if panel is not None:
                panel.setStyleSheet(style)
        footer.hide()
        self.mixingFinishFooter = footer
        self._apply_mixing_finish_modal_style()

    def _apply_mixing_finish_modal_style(self) -> None:
        self.finishOverlay.setStyleSheet(
            "QFrame#ProductionOverlay {"
            " background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #4b5059,stop:1 #2d3239);"
            " border:1px solid #747b86; border-radius:18px; }"
            "QFrame#ProductionOverlay QWidget { background:transparent; }"
            "QFrame#MixingFinishHeader, QFrame#MixingFinishFooter { background:transparent; border:none; }"
            "QLabel#MixingFinishEyebrow { color:#8aa4bd; font-size:12px; font-weight:900; letter-spacing:2px; background:transparent; }"
            "QLabel { background:transparent; border:none; }"
            "QFrame#MixingReviewInstruction { background:#383e47; border:1px solid #707783; border-radius:11px; }"
            "QFrame#MixingConfirmInstruction { background:#22945f; border:1px solid #2aac72; border-radius:11px; }"
            "QFrame#MixingCancelInstruction { background:#211316; border:1px solid #913d45; border-radius:11px; }"
            "QFrame#MixingFinishFooter QLabel[role='heading'] { color:#9fb2c5; font-size:11px; font-weight:900; letter-spacing:1px; }"
            "QFrame#MixingFinishFooter QLabel[role='instruction'] { color:#f8fafc; font-size:15px; font-weight:900; }"
            "QFrame#MixingConfirmInstruction QLabel[role='heading'] { color:#ffffff; }"
            "QFrame#MixingCancelInstruction QLabel[role='heading'] { color:#ff818b; }"
        )
        self.finishTitle.setStyleSheet(
            "color:#f8fafc; font-size:28px; font-weight:900; background:transparent; border:none;"
        )
        self.finishTitle.setAlignment(
            production_client.Qt.AlignmentFlag.AlignLeft
            | production_client.Qt.AlignmentFlag.AlignVCenter
        )
        self.finishReviewPageInfo.setStyleSheet(
            "color:#dce8f4; font-size:13px; font-weight:900; padding:8px 16px;"
            "background:#383e47; border:1px solid #707783; border-radius:18px;"
        )

    def _start_average_weight_server(self) -> None:
        """Mixing Mode uses configured Part Qty/Unit and needs no weight feed."""
        self._avg_weight_server = None
        self._avg_weight_server_thread = None
        self._avg_weight_server_error = None

    def _poll_server_average_weight(self) -> None:
        return

    def _apply_external_average_weight(self, *args, **kwargs) -> None:
        return

    def _apply_server_average_weight(self, *args, **kwargs) -> None:
        return

    def _ensure_mixing_kg_counter(self) -> int:
        """Keep a cumulative job KG counter independent from shift output."""
        current_value = self._parse_int_value(self.state.machine_counter_current)
        current_kg = (
            max(0, int(current_value))
            if current_value is not None
            else max(0, int(self.state.good_total or 0))
        )
        self.state.machine_counter_current = current_kg
        if self.state.machine_counter_shift_start is None:
            self.state.machine_counter_shift_start = current_kg
        if self.state.operator_shift_baseline_machine_counter_start is None:
            self.state.operator_shift_baseline_machine_counter_start = current_kg
        self.state.waiting_initial_machine_counter_input = False
        self.state.waiting_shift_end_machine_counter_input = False
        self.state.waiting_machine_counter_overwrite_input = False
        self.state.waiting_machine_counter_overwrite_supervisor = False
        self.state.machine_counter_input = ""
        return current_kg

    def _repair_initial_setup_state(self) -> None:
        """Mixing starts immediately; sack scans supply the live cycle time."""
        self._ensure_mixing_kg_counter()
        self.state.waiting_initial_cycle_time_input = False
        self.state.waiting_initial_cycle_qc_confirm = False
        self.state.waiting_initial_machine_counter_input = False
        self.state.waiting_shift_end_machine_counter_input = False
        self.state.waiting_cycle_time_confirm_popup = False
        self.state.cycle_time_confirm_phase = 0
        self._hide_resolve_overlay()

    def _begin_initial_cycle_time_setup(self) -> None:
        """Disable manual cycle-time entry in Mixing Mode."""
        self._repair_initial_setup_state()

    def _show_machine_counter_prompt(self, mode: str):
        current_kg = self._ensure_mixing_kg_counter()
        if str(mode or "").strip().lower() == "shift_end":
            self.state.machine_counter_shift_end = current_kg
        self._hide_resolve_overlay()
        production_client.QTimer.singleShot(
            0, self._resume_pending_pack_after_prerequisites
        )

    def _show_machine_counter_overwrite_prompt(self):
        """Mixing KG is scan-derived, so it cannot be entered or overwritten."""
        self._ensure_mixing_kg_counter()
        self._hide_resolve_overlay()
        self.status.setText("KG counter updates automatically from accepted SACK scans.")

    def _pack_start_prerequisites_ready(self) -> bool:
        self._ensure_mixing_kg_counter()
        return True

    def _gate_pack_start_prerequisites(self, raw_scan: str) -> bool:
        self._ensure_mixing_kg_counter()
        self._pending_pack_prereq_raw = ""
        return False

    def _start_operator_shift_tracking(self):
        self._ensure_mixing_kg_counter()
        super()._start_operator_shift_tracking()
        # The first accepted sack establishes the timestamp. The second and
        # later sacks produce real sack-to-sack cycle intervals.
        self._reset_live_cycle_tracking(start_now=False)
        self.state.waiting_initial_cycle_time_input = False
        self.state.waiting_initial_cycle_qc_confirm = False
        self.state.waiting_cycle_time_confirm_popup = False
        if not str(self.state.cycle_time_current or "").strip():
            self.state.cycle_time_current = "SACK SCAN"
            self.state.cycle_time_temporary = "SACK SCAN"
        self._hide_resolve_overlay()

    def _mark_live_cycle_scan_event(self, units: int = 1):
        """Measure one cycle per accepted sack, regardless of sack KG."""
        super()._mark_live_cycle_scan_event(units=1)
        cycle_seconds = self.state.live_cycle_avg_seconds
        if cycle_seconds is not None and float(cycle_seconds) > 0:
            cycle_text = f"{float(cycle_seconds):.2f}".rstrip("0").rstrip(".")
            self.state.cycle_time_current = cycle_text
            self.state.cycle_time_temporary = cycle_text

    def _current_machine_counter_app_total(self) -> Optional[int]:
        if not (self.state.job_code or self.state.job_name):
            return None
        return self._ensure_mixing_kg_counter()

    def _sync_machine_counter_current(self) -> None:
        if self.state.job_code or self.state.job_name:
            self._ensure_mixing_kg_counter()
        self._refresh_machine_counter_header_labels()

    def _next_machine_counter_preview(
        self, current_counter: Optional[int] = None
    ) -> Optional[int]:
        if not (self.state.job_code or self.state.job_name):
            return None
        current_kg = (
            max(0, int(current_counter))
            if current_counter is not None
            else self._ensure_mixing_kg_counter()
        )
        kg_per_sack = self._mixing_kg_per_sack()
        return current_kg + kg_per_sack if kg_per_sack > 0 else current_kg

    def _refresh_machine_counter_header_labels(self) -> None:
        current_label = getattr(self, "headerMachineCounter", None)
        next_label = getattr(self, "headerNextMachineCounter", None)
        if current_label is None or next_label is None:
            return
        has_job = bool(self.state.job_code or self.state.job_name)
        current_kg = self._ensure_mixing_kg_counter()
        current_label.setText(f"Current KG Counter: {current_kg}" if has_job else "")
        current_label.setVisible(has_job)
        next_kg = self._next_machine_counter_preview(current_kg) if has_job else None
        next_label.setText(
            f"Next Sack KG Counter: {next_kg}" if next_kg is not None else ""
        )
        next_label.setVisible(next_kg is not None)

    def _configure_compact_pack_gap_warning(self) -> None:
        """Keep the missing-sack notice visible without covering the dashboard."""
        if not hasattr(self, "packGapWarning"):
            return
        layout = self.packGapWarning.layout()
        if layout is not None:
            layout.setContentsMargins(12, 8, 12, 8)
            layout.setSpacing(2)
        self.packGapWarningTitle.setStyleSheet(
            "background: transparent; border: none; color: #7f1d1d;"
            " font-size: 15px; font-weight: 900;"
        )
        self.packGapWarningMessage.setStyleSheet(
            "background: transparent; border: none; color: #111827;"
            " font-size: 11px; font-weight: 800;"
        )
        self.packGapWarningHint.setStyleSheet(
            "background: transparent; border: none; color: #7c2d12;"
            " font-size: 9px; font-weight: 800;"
        )
        self._position_pack_gap_warning()

    def _refresh_pack_gap_warning(self):
        """Do not place the missing-series notice above a finish review."""
        finish_overlay = getattr(self, "finishOverlay", None)
        if finish_overlay is not None and finish_overlay.isVisible():
            warning = getattr(self, "packGapWarning", None)
            if warning is not None:
                warning.hide()
            timer = getattr(self, "packGapWarningBlinkTimer", None)
            if timer is not None:
                timer.stop()
            return
        super()._refresh_pack_gap_warning()

    def _position_pack_gap_warning(self):
        """Use a slimmer warning card in Mixing Mode."""
        if not hasattr(self, "packGapWarning") or self.packGapWarning is None:
            return
        margin = 12
        # Constrain the frame itself, not only its text, so it occupies much
        # less of the working area on smaller mixing screens.
        width = min(360, max(300, int(self.width() * 0.24)))
        height = min(96, max(82, self.packGapWarning.sizeHint().height()))
        try:
            header_bottom = self.headerCard.mapTo(
                self, self.headerCard.rect().bottomLeft()
            ).y()
        except Exception:
            header_bottom = 0
        x = max(margin, self.width() - width - margin)
        y = max(margin, int(header_bottom) + 8)
        self.packGapWarning.setGeometry(x, y, width, height)

    def _position_finish_overlay(self):
        """Use a centered content-sized review modal in Mixing Mode."""
        review_open = bool(
            getattr(self, "_pending_shift_review_payload", None)
            or getattr(self, "_pending_final_review_payload", None)
            or getattr(self, "_operator_shift_flash_active", False)
        )
        if not review_open:
            super()._position_finish_overlay()
            return
        available_w = max(1, int(self.width()))
        available_h = max(1, int(self.height()))
        width = min(1000, max(820, int(available_w * 0.70)))
        height = min(485, max(420, int(available_h * 0.52)))
        width = min(width, max(1, available_w - 32))
        height = min(height, max(1, available_h - 32))
        x = max(0, (available_w - width) // 2)
        y = max(0, (available_h - height) // 2)
        self.finishOverlay.setGeometry(x, y, width, height)

    def _configure_mixing_jobs_grid(self) -> None:
        """Replace Linkage Mirror rows/counters with a six-job grid."""
        if getattr(self, "mixingJobsGrid", None) is not None:
            return
        if not hasattr(self, "linkageMirrorFrame"):
            return
        content = self.linkageMirrorFrame.findChild(
            production_client.QWidget, "LinkageMirrorContent"
        )
        if content is None or content.layout() is None:
            return
        old_left = self.linkageMirrorFrame.findChild(
            production_client.QFrame, "LinkageMirrorLeft"
        )
        old_right = self.linkageMirrorFrame.findChild(
            production_client.QFrame, "LinkageMirrorRight"
        )
        if old_left is not None:
            old_left.hide()
        if old_right is not None:
            old_right.hide()

        grid_host = production_client.QFrame()
        grid_host.setObjectName("MixingJobsGrid")
        grid = production_client.QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid_host.setLayout(grid)
        labels = []
        for index in range(6):
            cell = production_client.QFrame()
            cell.setObjectName("MixingJobCell")
            cell_layout = production_client.QHBoxLayout()
            cell_layout.setContentsMargins(9, 2, 9, 2)
            cell.setLayout(cell_layout)
            cell.setMinimumHeight(28)
            cell.setMaximumHeight(28)
            label = production_client.QLabel("-")
            label.setObjectName("MixingJobValue")
            label.setAlignment(
                production_client.Qt.AlignmentFlag.AlignLeft
                | production_client.Qt.AlignmentFlag.AlignVCenter
            )
            label.setSizePolicy(
                production_client.QSizePolicy.Policy.Expanding,
                production_client.QSizePolicy.Policy.Preferred,
            )
            cell_layout.addWidget(label, 1)
            grid.addWidget(cell, index // 2, index % 2)
            labels.append(label)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        content.layout().addWidget(grid_host, 2)
        content.layout().setStretch(content.layout().indexOf(grid_host), 2)
        self.linkageMirrorFrame.setStyleSheet(
            self.linkageMirrorFrame.styleSheet()
            + "QFrame#MixingJobsGrid { background: transparent; border: none; }"
            + "QFrame#MixingJobCell {"
            + " background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            + " stop:0 rgba(103,107,115,220), stop:1 rgba(56,59,66,230));"
            + " border: 1px solid #7a8089; border-radius: 12px; }"
            + "QLabel#MixingJobValue { color:#edf0f4; font-size:13px;"
            + " font-weight:900; background:transparent; border:none; }"
        )
        self.mixingJobsGrid = grid_host
        self.mixingJobGridLabels = labels

    def _mixing_operator_from_scan(self, raw: str) -> Optional[Dict[str, str]]:
        """Resolve an Operator/Mixer badge for finish confirmation."""
        person = self._operator_from_scan(raw) or self._offline_operator_from_scan(raw)
        if person is None:
            code = self._clean_badge_scan_code(raw)
            known_operators = [
                self.state.operator_id,
                (self._pending_shift_review_payload or {}).get("operator_id")
                if isinstance(self._pending_shift_review_payload, dict)
                else None,
                (self._pending_final_review_payload or {}).get("operator_id")
                if isinstance(self._pending_final_review_payload, dict)
                else None,
            ]
            for known in known_operators:
                operator_text = str(known or "").strip()
                operator_code = operator_text.split(" - ", 1)[0].strip()
                if not code or not operator_code or code != operator_code:
                    continue
                operator_name = (
                    operator_text.split(" - ", 1)[1].strip()
                    if " - " in operator_text
                    else operator_text
                )
                person = {"code": code, "name": operator_name or code}
                break
        if person is None:
            return None
        resolved = dict(person)
        resolved["role"] = "MIXER"
        resolved["can_operator"] = "1"
        return resolved

    def _show_operator_shift_overlay(
        self,
        shift_payload: Dict[str, Any],
        linked_payloads: Optional[List[Dict[str, Any]]] = None,
    ):
        super()._show_operator_shift_overlay(shift_payload, linked_payloads)
        self._apply_mixing_finish_modal_style()
        self.packGapWarning.hide()
        self.packGapWarningBlinkTimer.stop()
        self.mixingFinishEyebrow.setText("END OF SHIFT")
        self.mixingFinishConfirmHeading.setText("CONFIRM SHIFT")
        self.mixingFinishConfirmInstruction.setText("Scan Operator / Mixer QR")
        self.mixingFinishCancelInstruction.setText("Scan Operator Shift QR")
        self.finishStatus.hide()
        self.finishReviewHint.hide()
        self.mixingFinishFooter.show()
        self.finishTitle.setText("Mixing Shift Confirmation")
        self.finishStatus.setText(
            "Review the shift, then scan the Operator/Mixer QR to finish."
        )
        self.finishReviewHint.setText(
            'Scan "next" / "prev" to review, scan the Operator/Mixer QR to confirm, '
            "or scan Operator Shift QR again to cancel."
        )
        production_client.QTimer.singleShot(
            0,
            lambda: self.status.setText(
                "Mixing shift confirmation is open. Scan the Operator/Mixer QR."
            ),
        )

    def _show_final_job_review_overlay(
        self,
        finished_payload: Dict[str, Any],
        linked_payloads: Optional[List[Dict[str, Any]]] = None,
    ):
        super()._show_final_job_review_overlay(finished_payload, linked_payloads)
        self._apply_mixing_finish_modal_style()
        self.packGapWarning.hide()
        self.packGapWarningBlinkTimer.stop()
        self.mixingFinishEyebrow.setText("END OF JOB")
        self.mixingFinishConfirmHeading.setText("CONFIRM JOB")
        self.mixingFinishConfirmInstruction.setText("Scan Operator / Mixer QR")
        self.mixingFinishCancelInstruction.setText("Scan Finish Job QR")
        self.finishStatus.hide()
        self.finishReviewHint.hide()
        self.mixingFinishFooter.show()
        self.finishTitle.setText("Finish Mixing Job")
        self.finishStatus.setText(
            "Review the job, then scan the Operator/Mixer QR to finish it."
        )
        self.finishReviewHint.setText(
            'Scan "next" / "prev" to review, scan the Operator/Mixer QR to confirm, '
            "or scan Finish Job QR again to cancel."
        )
        self.status.setText(
            "Finish mixing job summary is open. Scan the Operator/Mixer QR."
        )

    def _hide_operator_shift_overlay(self):
        super()._hide_operator_shift_overlay()
        self.mixingFinishFooter.hide()

    def _hide_final_job_review_overlay(self):
        super()._hide_final_job_review_overlay()
        self.mixingFinishFooter.hide()

    def _expected_scan_instruction(self) -> str:
        if getattr(self, "_pending_final_review_payload", None):
            return 'Scan "next", "prev", or the Operator/Mixer QR.'
        if getattr(self, "_operator_shift_flash_active", False):
            return "Scan the Operator/Mixer QR to confirm the mixing shift."
        return super()._expected_scan_instruction()

    def _handle_mixing_finish_confirmation(self, raw: str) -> bool:
        """Handle Mixer-owned completion; return whether the scan was consumed."""
        raw_s = str(raw or "").strip()
        raw_l = raw_s.lower()
        if getattr(self, "_pending_final_review_payload", None):
            if self._should_ignore_duplicate_transport_scan(raw_s):
                return True
            if raw_l in ("finishjob", "finishjob~1", "jobfinish"):
                self._cancel_pending_finish_job()
                return True
            if raw_l in ("next", "prev", "previous", "preview"):
                self._change_finish_review_page(1 if raw_l == "next" else -1)
                return True
            mixer = self._mixing_operator_from_scan(raw_s)
            if mixer is not None:
                self.status.setText("Operator/Mixer QR accepted. Finishing job...")
                self._approve_pending_final_job_review(mixer, raw_s)
                return True
            self.status.setText("Scan a valid Operator/Mixer QR to finish this job.")
            self._show_invalid_overlay(
                "A valid Operator/Mixer QR is required to finish this mixing job."
            )
            return True
        if getattr(self, "_operator_shift_flash_active", False):
            pending_shift = dict(self._pending_shift_review_payload or {})
            if pending_shift:
                if self._should_ignore_duplicate_transport_scan(raw_s):
                    return True
                if raw_l in ("operatorshift~1", "operator_shift~1", "shiftchange~1"):
                    self._cancel_pending_finish_shift()
                    return True
                if raw_l in ("next", "prev", "previous", "preview"):
                    self._change_finish_review_page(1 if raw_l == "next" else -1)
                    return True
                mixer = self._mixing_operator_from_scan(raw_s)
                if mixer is not None:
                    self.status.setText(
                        "Operator/Mixer QR accepted. Finishing mixing shift..."
                    )
                    self._approve_pending_shift_review(mixer, raw_s)
                    return True
                self.status.setText(
                    "Scan a valid Operator/Mixer QR to finish this shift."
                )
                self._show_invalid_overlay(
                    "A valid Operator/Mixer QR is required to finish this mixing shift."
                )
                return True
        return False

    def _build_mixing_partial_api_request(
        self,
        shift_payload: Dict[str, Any],
        mixer_name: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Build the future POST /v1/jobs/{id}/partials request."""
        payload = dict(shift_payload or {})
        job_payload = payload.get("job_payload")
        job_data = job_payload.get("data") if isinstance(job_payload, dict) else {}
        job_row = job_data.get("job") if isinstance(job_data, dict) else {}
        raw_job_id = (
            job_row.get("id")
            if isinstance(job_row, dict)
            else None
        ) or payload.get("job_code")
        try:
            job_id = int(str(raw_job_id or "").strip())
        except (TypeError, ValueError):
            return None

        # The API partial is the accepted finished-sack output for this shift,
        # not the cumulative KG-counter delta. The counter is useful for the
        # operator display and audit, but a stale/corrupt counter must never
        # change the quantity posted to the job. The production shift builder
        # derives partial_qty from accepted sack scans (good_total + butal).
        produced_value: Any = None
        for field_name in ("partial_qty", "total_good", "good_total"):
            if payload.get(field_name) is not None:
                produced_value = payload.get(field_name)
                break
        if produced_value is None:
            # Compatibility for old saved Mixing payloads that predate the
            # standard produced-total fields.
            produced_value = payload.get(
                "mixing_kg_produced_shift", payload.get("mixing_total_kg", 0)
            )
        produced_qty = self._parse_number(produced_value)
        produced_qty = round(max(0.0, produced_qty), 4)

        part_ids: List[int] = []
        part_quantities: List[float] = []
        for part in payload.get("mixing_cumulative_part_totals") or []:
            if not isinstance(part, dict):
                continue
            raw_part_id = part.get("part_product_id") or part.get("product_id")
            try:
                part_id = int(str(raw_part_id or "").strip())
            except (TypeError, ValueError):
                continue
            qty_per_unit = max(
                0.0, self._parse_number(part.get("part_qty_per_unit"))
            )
            part_ids.append(part_id)
            part_quantities.append(round(produced_qty * qty_per_unit, 4))

        machine = str(payload.get("machine_code") or "-").strip()
        job_name = str(
            payload.get("job_name") or payload.get("job_code") or job_id
        ).strip()
        shift_index = int(payload.get("shift_index") or 0)
        note_parts = [f"Mixing {machine}", job_name]
        if shift_index > 0:
            note_parts.append(f"Shift {shift_index}")
        if str(mixer_name or "").strip():
            note_parts.append(f"Mixer {str(mixer_name).strip()}")

        body: Dict[str, Any] = {
            "partial_qty": produced_qty,
            # BMS requires an employee record for API-created partials. Keep
            # this integration identity fixed; do not substitute the mixer.
            "partial_by": 11,
            "partial_by_name": "API INTEGRATION",
            "partial_note": " | ".join(note_parts),
        }
        if part_ids:
            body["partial_part_product_id"] = part_ids
            body["partial_part_qty"] = part_quantities
        return {
            "method": "POST",
            "endpoint": f"/v1/jobs/{job_id}/partials",
            "job_id": job_id,
            "body": body,
        }

    def _record_mixing_partial_api_stub(
        self,
        shift_payload: Dict[str, Any],
        mixer_name: str = "",
    ) -> bool:
        """Record a mock request/response without contacting the Jobs API."""
        request_row = self._build_mixing_partial_api_request(
            shift_payload, mixer_name
        )
        if not isinstance(request_row, dict):
            self._append_job_api_log(
                "MIXING PARTIAL STUB skipped: numeric job ID is unavailable"
            )
            return False

        body = dict(request_row.get("body") or {})
        job_id = int(request_row.get("job_id") or 0)
        response_body = {
            "code": 200,
            "message": "msg_save_success",
            "data": {
                "partial": {
                    "id": 501,
                    "job_id": job_id,
                    "partial_qty": body.get("partial_qty", 0),
                }
            },
            "warning": "",
        }
        record = {
            "mode": "STUB_ONLY",
            "pushed_at_utc": production_client.datetime.now(
                production_client.timezone.utc
            ).isoformat(),
            "request": request_row,
            "response_status": 200,
            "response": response_body,
        }
        try:
            rows: List[Dict[str, Any]] = []
            if MIXING_PARTIAL_API_STUB_PATH.exists():
                loaded = json.loads(
                    MIXING_PARTIAL_API_STUB_PATH.read_text(encoding="utf-8")
                )
                if isinstance(loaded, list):
                    rows = [dict(row) for row in loaded if isinstance(row, dict)]
            rows.append(record)
            MIXING_PARTIAL_API_STUB_PATH.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = MIXING_PARTIAL_API_STUB_PATH.with_suffix(".tmp")
            temporary_path.write_text(
                json.dumps(rows[-100:], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary_path, MIXING_PARTIAL_API_STUB_PATH)
        except Exception as error:
            self._append_job_api_log(
                f"MIXING PARTIAL STUB save failed: {error}"
            )
            return False

        self._append_job_api_log(
            "MIXING PARTIAL STUB 200 "
            f"{request_row.get('endpoint')} body="
            f"{json.dumps(body, ensure_ascii=False, separators=(',', ':'))}"
        )
        self._append_app_log(
            "MIXING PARTIAL API STUB",
            f"POST {request_row.get('endpoint')} -> 200",
        )
        return True

    def _submit_mixing_partial_api(
        self,
        shift_payload: Dict[str, Any],
        mixer_name: str = "",
    ) -> bool:
        """Queue one durable API submission and start the single-flight worker."""
        request_row = self._build_mixing_partial_api_request(
            shift_payload, mixer_name
        )
        if not isinstance(request_row, dict):
            self._append_job_api_log(
                "MIXING PARTIAL API skipped: numeric job ID is unavailable"
            )
            self.status.setText(
                "Mixing shift saved locally, but Job API push was skipped: "
                "numeric job ID is unavailable."
            )
            return False
        identity = {
            "request": request_row,
            "machine_code": shift_payload.get("machine_code"),
            "job_code": shift_payload.get("job_code"),
            "shift_index": shift_payload.get("shift_index"),
            "finished_at_utc": shift_payload.get("finished_at_utc")
            or shift_payload.get("ended_at_utc"),
        }
        digest = hashlib.sha256(
            json.dumps(
                identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        request_id = f"mixing-{digest}"
        rows = self._load_mixing_partial_api_outbox()
        if not any(str(row.get("request_id") or "") == request_id for row in rows):
            rows.append(
                {
                    "request_id": request_id,
                    "queued_at_utc": production_client.datetime.now(
                        production_client.timezone.utc
                    ).isoformat(),
                    "attempt_count": 0,
                    "next_attempt_epoch": 0,
                    "last_error": "",
                    "request": request_row,
                }
            )
            if not self._save_mixing_partial_api_outbox(rows):
                self.status.setText(
                    "Mixing shift saved locally, but its API outbox entry "
                    "could not be saved."
                )
                return False
        self.status.setText(
            "Mixing shift queued once for the Job API. It will wait for "
            "the server if the API is unavailable."
        )
        production_client.QTimer.singleShot(
            0, self._drain_mixing_partial_api_outbox
        )
        return True

    @staticmethod
    def _load_mixing_partial_api_outbox() -> List[Dict[str, Any]]:
        try:
            loaded = json.loads(
                MIXING_PARTIAL_API_OUTBOX_PATH.read_text(encoding="utf-8")
            )
            if isinstance(loaded, list):
                return [dict(row) for row in loaded if isinstance(row, dict)]
        except (OSError, ValueError):
            pass
        return []

    @staticmethod
    def _save_mixing_partial_api_outbox(rows: List[Dict[str, Any]]) -> bool:
        try:
            MIXING_PARTIAL_API_OUTBOX_PATH.parent.mkdir(
                parents=True, exist_ok=True
            )
            temporary_path = MIXING_PARTIAL_API_OUTBOX_PATH.with_suffix(".tmp")
            temporary_path.write_text(
                json.dumps(rows, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary_path, MIXING_PARTIAL_API_OUTBOX_PATH)
            return True
        except Exception:
            return False

    def _schedule_mixing_partial_outbox(self, delay_seconds: float) -> None:
        if not hasattr(self, "_mixing_partial_outbox_timer"):
            return
        delay_ms = max(1000, int(max(1.0, delay_seconds) * 1000))
        self._mixing_partial_outbox_timer.start(delay_ms)

    def _drain_mixing_partial_api_outbox(self) -> None:
        """Send at most one queued item, then wait for acknowledgement."""
        if self._mixing_partial_push_in_flight:
            return
        rows = self._load_mixing_partial_api_outbox()
        if not rows:
            return
        if not bool(getattr(self, "_server_connection_ok", False)):
            self._schedule_mixing_partial_outbox(30)
            return

        now_epoch = time.time()
        item = rows[0]
        next_attempt = float(item.get("next_attempt_epoch") or 0)
        if next_attempt > now_epoch:
            self._schedule_mixing_partial_outbox(next_attempt - now_epoch)
            return

        request_row = item.get("request")
        if not isinstance(request_row, dict):
            rows.pop(0)
            self._save_mixing_partial_api_outbox(rows)
            self._schedule_mixing_partial_outbox(1)
            return
        server_url = str(
            (self.client_config or {}).get(
                "server_url", production_client.SERVER_URL
            )
            or production_client.SERVER_URL
        ).strip().rstrip("/")
        if not server_url:
            self._schedule_mixing_partial_outbox(60)
            return

        request_id = str(item.get("request_id") or "").strip()
        endpoint = str(request_row.get("endpoint") or "")
        job_id = int(request_row.get("job_id") or 0)
        body = dict(request_row.get("body") or {})
        proxy_url = f"{server_url}/api/mixing/jobs/{job_id}/partials"
        self._mixing_partial_push_in_flight = True
        acknowledged = False
        error_text = ""
        try:
            response = self._request_with_ui_events(
                production_client.requests.post,
                proxy_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-Idempotency-Key": request_id,
                },
                json=body,
                timeout=(1.5, 20.0),
            )
            try:
                response_body = response.json()
            except Exception:
                response_body = {}
            acknowledged = response.status_code == 200 and bool(
                response_body.get("ok")
                if isinstance(response_body, dict)
                else False
            )
            if not acknowledged:
                error_text = (
                    self._http_error_snippet(response)
                    or f"HTTP {response.status_code}"
                )
        except Exception as error:
            error_text = str(error)
        finally:
            self._mixing_partial_push_in_flight = False

        latest_rows = self._load_mixing_partial_api_outbox()
        current_index = next(
            (
                index
                for index, row in enumerate(latest_rows)
                if str(row.get("request_id") or "") == request_id
            ),
            -1,
        )
        if current_index < 0:
            return
        if acknowledged:
            latest_rows.pop(current_index)
            self._save_mixing_partial_api_outbox(latest_rows)
            self._append_job_api_log(
                f"MIXING PARTIAL API ACK {request_id} {endpoint}"
            )
            self._append_app_log(
                "MIXING PARTIAL API", f"ACK {request_id} {endpoint}"
            )
            self.status.setText(
                f"Mixing shift received by Job API for job {job_id}."
            )
            if latest_rows:
                self._schedule_mixing_partial_outbox(2)
            return

        queued = latest_rows[current_index]
        attempts = int(queued.get("attempt_count") or 0) + 1
        delay_seconds = min(300, 30 * (2 ** min(attempts - 1, 4)))
        queued["attempt_count"] = attempts
        queued["last_error"] = error_text[:500]
        queued["last_attempt_utc"] = production_client.datetime.now(
            production_client.timezone.utc
        ).isoformat()
        queued["next_attempt_epoch"] = time.time() + delay_seconds
        latest_rows[current_index] = queued
        self._save_mixing_partial_api_outbox(latest_rows)
        self._append_job_api_log(
            f"MIXING PARTIAL API WAIT {request_id}; retry in "
            f"{delay_seconds}s: {error_text}"
        )
        self.status.setText(
            "Job API is unavailable. One mixing partial is waiting; "
            f"next check in {delay_seconds} seconds."
        )
        self._schedule_mixing_partial_outbox(delay_seconds)

    def _push_mixing_partial(
        self,
        shift_payload: Dict[str, Any],
        mixer_name: str = "",
    ) -> bool:
        if self._mixing_partial_api_mode() == "api":
            return self._submit_mixing_partial_api(shift_payload, mixer_name)
        return self._record_mixing_partial_api_stub(shift_payload, mixer_name)

    def _approve_pending_shift_review(
        self, reviewer: Dict[str, Any], reviewer_badge: str
    ):
        """Finish the shift, then push its partial to the selected destination."""
        shift_payload = dict(self._pending_shift_review_payload or {})
        mixer_name = self._safe_text(
            reviewer.get("name"), self._safe_text(reviewer_badge)
        )
        super()._approve_pending_shift_review(reviewer, reviewer_badge)
        # The base method keeps the review payload open on any save failure.
        # Only create the mock API transaction after a successful completion.
        if shift_payload and not getattr(
            self, "_pending_shift_review_payload", None
        ):
            self._push_mixing_partial(shift_payload, mixer_name)

    def _approve_pending_final_job_review(
        self, reviewer: Dict[str, Any], reviewer_badge: str
    ):
        """Finish a mixing job with Mixer confirmation, without Supervisor."""
        if not self._pending_final_review_payload:
            return
        finished_payload = dict(self._pending_final_review_payload or {})
        linked_payloads = [
            dict(row)
            for row in (self._pending_final_review_linked_payloads or [])
            if isinstance(row, dict)
        ]
        mixer_name = self._safe_text(
            reviewer.get("name"), self._safe_text(reviewer_badge)
        )
        mixer_code = self._safe_text(
            reviewer.get("code"), self._safe_text(reviewer_badge)
        )
        confirmed_at = production_client.datetime.now(
            production_client.timezone.utc
        ).isoformat()
        remarks = f"Finish job confirmed on client by Mixer {mixer_name}"
        for row in [finished_payload] + linked_payloads:
            row["approved_by"] = mixer_name
            row["approved_by_code"] = mixer_code
            row["approved_by_role"] = "MIXER"
            row["approved_remarks"] = remarks
            row["approved_at_utc"] = confirmed_at
            row["review_status"] = production_client.REVIEW_STATUS_CLOSED
            row["mixing_confirmation_mode"] = "OPERATOR_MIXER"
            history = list(row.get("review_history") or [])
            history.append(
                {
                    "action": "CONFIRM_FINISH_JOB_BY_MIXER",
                    "remarks": remarks,
                    "actor_name": mixer_name,
                    "actor_code": mixer_code,
                    "actor_role": "MIXER",
                    "timestamp_utc": confirmed_at,
                }
            )
            row["review_history"] = history

        self._show_bms_loading("Finishing Mixing Job...")
        try:
            saved_ok = self._save_finished_job_local(finished_payload)
            for row in linked_payloads:
                saved_ok = self._save_finished_job_local(row) and saved_ok
            if not saved_ok:
                self.status.setText(
                    "Finish save failed: active mixing session kept for recovery."
                )
                return
            self.push_event(
                {"type": "FINISH_JOB", "finished_job": finished_payload},
                f"FINISH MIXING JOB {finished_payload.get('job_name') or finished_payload.get('job_code') or ''}".strip(),
            )
            for row in linked_payloads:
                self.push_event(
                    {"type": "FINISH_JOB", "finished_job": row},
                    f"FINISH MIXING JOB {row.get('job_name') or row.get('job_code') or ''}".strip(),
                    silent=True,
                )
            self._finish_job_cancel_snapshot = None
            self._finish_pending_clear = False
            for row in [finished_payload] + linked_payloads:
                self._clear_shift_carryover_record(
                    row.get("machine_code"), row.get("job_code")
                )
            self._clear_shift_session_keep_machine(preserve_carryover=False)
            self._hide_final_job_review_overlay()
            if not self.state.job_code:
                self.status.setText(
                    f"Mixing job confirmed by {mixer_name} and finished."
                )
        finally:
            self._hide_bms_loading()

    def _mixing_job_key(self, value: Any) -> str:
        return self._normalize_job_code(value)

    @staticmethod
    def _is_mixing_identity_row(part: Dict[str, Any]) -> bool:
        """Treat the BMS Col row as the mix identity, not a consumed part."""
        sku = str(
            part.get("sku")
            or part.get("part_sku")
            or part.get("product_sku")
            or ""
        ).strip().upper()
        return sku.startswith("Z-COL-")

    def _job_part_rows(
        self, payload: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        rows = super()._job_part_rows(payload)
        return [row for row in rows if not self._is_mixing_identity_row(row)]

    def _resolve_part_qty_per_unit(
        self, part: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Use the job's configured material quantity for Mixing Mode.

        A mixing material's ``part_qty_per_unit`` is its quantity for one kg
        of finished mix.  It must not be replaced by an average scanned weight
        or by a ratio derived from the material currently available.
        """
        if isinstance(part, dict):
            for key in (
                "part_qty_per_unit",
                "qty_per_unit",
                "quantity_per_unit",
                "part_quantity_per_unit",
                "component_qty_per_unit",
            ):
                value = self._parse_number(part.get(key))
                if value > 0:
                    unit_kind = self._part_unit_kind(part)
                    return {
                        "value": value,
                        "source": "mixing_job_part_qty_per_unit",
                        "unit": unit_kind,
                        "label": f"Job Part Qty/Unit ({value:.4f} {unit_kind})",
                    }
        return super()._resolve_part_qty_per_unit(part)

    @staticmethod
    def _normalize_mixing_machine_scan(raw: Any) -> str:
        value = str(raw or "").strip()
        lookup_key = re.sub(r"[^A-Z0-9]+", "", value.upper())
        return _MIXING_MACHINE_QR_ALIASES.get(lookup_key, value)

    def _mixing_session_is_for_current_machine(
        self, snapshot: Dict[str, Any]
    ) -> bool:
        current_machine = str(getattr(self.state, "machine_code", None) or "").strip().upper()
        snapshot_machine = str(snapshot.get("machine_code") or "").strip().upper()
        return not current_machine or not snapshot_machine or current_machine == snapshot_machine

    def _load_mixing_sessions(self) -> None:
        try:
            payload = json.loads(MIXING_MULTI_JOB_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        rows = payload.get("sessions") if isinstance(payload, dict) else None
        if not isinstance(rows, dict):
            return
        self._mixing_sessions = {
            str(key): {
                field: value
                for field, value in dict(snapshot).items()
                if field != "mixing_open_jobs"
            }
            for key, snapshot in rows.items()
            if str(key).strip() and isinstance(snapshot, dict)
        }
        for snapshot in self._mixing_sessions.values():
            snapshot.setdefault("mixing_open", True)
        self._mixing_active_job_key = str(
            payload.get("active_job_key") or ""
        ).strip()

    def _persist_mixing_sessions(self) -> None:
        try:
            MIXING_MULTI_JOB_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "active_job_key": self._mixing_active_job_key,
                "sessions": self._mixing_sessions,
            }
            temporary_path = MIXING_MULTI_JOB_PATH.with_suffix(".tmp")
            temporary_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            os.replace(temporary_path, MIXING_MULTI_JOB_PATH)
        except Exception as error:
            if hasattr(self, "status"):
                self.status.setText(f"Could not save Mixing Mode sessions: {error}")

    def _capture_current_mixing_session(
        self,
        *,
        persist: bool = True,
        allow_reopen_closed: bool = False,
    ) -> str:
        if not getattr(self, "_mixing_mode_ready", False):
            return ""
        job_key = self._mixing_job_key(self.state.job_code or self.state.job_name)
        if not job_key:
            return ""
        existing = self._mixing_sessions.get(job_key)
        if (
            isinstance(existing, dict)
            and not bool(existing.get("mixing_open", True))
            and str(self._mixing_active_job_key or "").strip() != job_key
            and not allow_reopen_closed
        ):
            # Do not let a stale server/local startup snapshot resurrect a
            # shift that the Mixing registry already marked closed.
            return ""
        snapshot = self._state_to_active_snapshot()
        snapshot.pop("mixing_open_jobs", None)
        snapshot["mixing_open"] = True
        snapshot["mixing_last_active_at"] = time.time()
        self._mixing_sessions[job_key] = snapshot
        self._mixing_active_job_key = job_key
        if persist:
            self._persist_mixing_sessions()
        self._refresh_mixing_jobs_panel()
        return job_key

    def _build_mixing_jobs_panel(self) -> None:
        if hasattr(self, "mixingJobsPanel") or not hasattr(self, "rightPanel"):
            return
        panel = production_client.QFrame()
        panel.setObjectName("MixingJobsPanel")
        layout = production_client.QVBoxLayout()
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)
        panel.setLayout(layout)

        self.mixingJobsTitle = production_client.QLabel("OPEN MIXING JOBS (0)")
        self.mixingJobsTitle.setObjectName("MixingJobsTitle")
        self.mixingJobsTitle.setAlignment(production_client.Qt.AlignmentFlag.AlignCenter)
        self.mixingJobsList = production_client.QLabel("Scan a JOB QR to begin.")
        self.mixingJobsList.setObjectName("MixingJobsList")
        self.mixingJobsList.setWordWrap(True)
        self.mixingJobsList.setAlignment(
            production_client.Qt.AlignmentFlag.AlignLeft
            | production_client.Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self.mixingJobsTitle)
        layout.addWidget(self.mixingJobsList)
        panel.setMinimumHeight(96)
        panel.setMaximumHeight(176)
        panel.setStyleSheet(
            "QFrame#MixingJobsPanel {"
            " background: rgba(35,39,47,238); border: 1px solid #737985;"
            " border-radius: 18px; }"
            "QLabel#MixingJobsTitle { color: #e5e7eb; font-size: 13px;"
            " font-weight: 900; padding-bottom: 4px; }"
            "QLabel#MixingJobsList { color: #d1d5db; font-size: 12px;"
            " font-weight: 700; }"
        )
        self.mixingJobsPanel = panel
        self.rightPanel.layout().insertWidget(1, panel)
        # Multi-job state is scan-driven. Keep it off the permanent dashboard
        # and show a temporary confirmation only when a job is opened/switched.
        panel.hide()

    def _refresh_mixing_jobs_panel(self) -> None:
        if not hasattr(self, "mixingJobsList"):
            return
        current_key = self._mixing_job_key(
            getattr(self.state, "job_code", None) or getattr(self.state, "job_name", None)
        )
        rows = sorted(
            (
                item
                for item in self._mixing_sessions.items()
                if self._mixing_session_is_for_current_machine(item[1])
                and bool(item[1].get("mixing_open", True))
            ),
            key=lambda item: float(item[1].get("mixing_last_active_at") or 0.0),
            reverse=True,
        )
        self.mixingJobsTitle.setText(f"OPEN MIXING JOBS ({len(rows)})")
        if not rows:
            self.mixingJobsList.setText("Scan a JOB QR to begin.")
            return
        display_rows: List[str] = []
        for key, snapshot in rows[:6]:
            marker = "ACTIVE >" if key == current_key else "       "
            job_name = str(
                snapshot.get("job_name") or snapshot.get("job_code") or key
            ).strip()
            sack_count = int(snapshot.get("mixing_sack_count", snapshot.get("pack_count", 0)) or 0)
            good_kg = int(snapshot.get("mixing_total_kg", snapshot.get("good_total", 0)) or 0)
            part_scans = len(snapshot.get("raw_material_logs") or [])
            display_rows.append(
                f"{marker} {job_name}  |  Parts {part_scans}  |  Sacks {sack_count}  |  {good_kg} kg"
            )
        if len(rows) > 6:
            display_rows.append(f"+ {len(rows) - 6} more open job(s)")
        self.mixingJobsList.setText("\n".join(display_rows))
        # The visible running-job list reuses the production Linkage Mirror.
        # Keep the old hidden panel refreshed as a fallback, then refresh the
        # mirror whenever a job is opened, switched, or closed.
        if hasattr(self, "linkageMirrorFrame"):
            self._refresh_linkage_panel()

    def _find_open_mixing_job(self, candidates: List[Any]) -> str:
        wanted = {
            self._mixing_job_key(value)
            for value in candidates
            if self._mixing_job_key(value)
        }
        if not wanted:
            return ""
        for key, snapshot in self._mixing_sessions.items():
            if not self._mixing_session_is_for_current_machine(snapshot):
                continue
            if not bool(snapshot.get("mixing_open", True)):
                continue
            identities = {
                self._mixing_job_key(key),
                self._mixing_job_key(snapshot.get("job_code")),
                self._mixing_job_key(snapshot.get("job_name")),
            }
            if wanted.intersection(identities):
                return key
        return ""

    def _switch_mixing_session(self, job_key: str, *, reason: str) -> bool:
        target_key = str(job_key or "").strip()
        snapshot = self._mixing_sessions.get(target_key)
        if not isinstance(snapshot, dict):
            return False
        current_key = self._mixing_job_key(self.state.job_code or self.state.job_name)
        if current_key and current_key != target_key:
            current_saved = self._mixing_sessions.get(current_key)
            # A shift that was already closed must not become OPEN again merely
            # because startup recovery briefly restored its old live snapshot.
            if not (
                isinstance(current_saved, dict)
                and not bool(current_saved.get("mixing_open", True))
            ):
                self._capture_current_mixing_session()
        if current_key != target_key:
            self._hide_invalid_overlay()
            self._hide_production_overlay()
            self._hide_resolve_overlay()
            self._restore_state_from_snapshot(dict(snapshot))
            self._sync_mixing_material_history_from_server()
        self._mixing_active_job_key = target_key
        self._mixing_sessions[target_key]["mixing_open"] = True
        self._mixing_sessions[target_key]["mixing_last_active_at"] = time.time()
        self._persist_mixing_sessions()
        super()._save_active_session_snapshot(force=True)
        self.sync_session_snapshot_to_server(
            "SESSION SNAPSHOT SYNC (MIXING ACTIVE JOB SWITCH)"
        )
        job_label = str(self.state.job_name or self.state.job_code or target_key)
        self.status.setText(f"Active mixing job: {job_label} ({reason}).")
        self._show_info_overlay(
            "MIXING JOB SELECTED",
            f"Active job: {job_label}\n"
            "Open mixing sessions: "
            f"{sum(1 for row in self._mixing_sessions.values() if bool(row.get('mixing_open', True)))}",
            hide_ms=2600,
        )
        self._refresh_ui(force=True)
        self._refresh_mixing_jobs_panel()
        return True

    def _restore_owned_session_on_startup(self) -> None:
        """Recover state, then display the registry's next OPEN mixing job."""
        super()._restore_owned_session_on_startup()
        target_key = str(self._mixing_active_job_key or "").strip()
        target = self._mixing_sessions.get(target_key)
        if not isinstance(target, dict) or not bool(target.get("mixing_open", True)):
            candidates = sorted(
                (
                    (key, snapshot)
                    for key, snapshot in self._mixing_sessions.items()
                    if isinstance(snapshot, dict)
                    and bool(snapshot.get("mixing_open", True))
                ),
                key=lambda item: float(item[1].get("mixing_last_active_at") or 0.0),
                reverse=True,
            )
            target_key = candidates[0][0] if candidates else ""
        current_key = self._mixing_job_key(self.state.job_code or self.state.job_name)
        if target_key and target_key != current_key:
            self._switch_mixing_session(
                target_key,
                reason="next running job restored",
            )

    def _activate_registry_open_job(self) -> None:
        """Reconcile delayed server recovery with the Mixing open-job registry."""
        target_key = str(self._mixing_active_job_key or "").strip()
        target = self._mixing_sessions.get(target_key)
        if not isinstance(target, dict) or not bool(target.get("mixing_open", True)):
            candidates = sorted(
                (
                    (key, snapshot)
                    for key, snapshot in self._mixing_sessions.items()
                    if isinstance(snapshot, dict)
                    and bool(snapshot.get("mixing_open", True))
                ),
                key=lambda item: float(item[1].get("mixing_last_active_at") or 0.0),
                reverse=True,
            )
            target_key = candidates[0][0] if candidates else ""
        current_key = self._mixing_job_key(self.state.job_code or self.state.job_name)
        if target_key and target_key != current_key:
            self._switch_mixing_session(target_key, reason="next running job")

    def _prepare_empty_mixing_session(self) -> None:
        machine_code = self.state.machine_code
        machine_name = self.state.machine_name
        self.state = production_client.ClientState()
        self.state.machine_code = machine_code
        self.state.machine_name = machine_name
        self._action_logs = []
        self._hide_invalid_overlay()
        self._hide_production_overlay()
        self._hide_resolve_overlay()
        self._hide_raw_mats_overlay()
        self._hide_reject_summary_overlay()
        self._hide_product_history_overlay()
        self._hide_reject_review_overlay()

    def _part_scan_identity(self, raw: str, result: Any) -> Dict[str, Any]:
        if result is None:
            return {}
        if result.kind == "RAW_MATERIAL":
            return dict(result.meta or {})
        if result.kind != "PACK":
            return {}
        fields = self._extract_pack_history_fields(raw)
        if not isinstance(fields, dict):
            return {}
        raw_product_id = str(
            fields.get("product_p") or fields.get("product_id") or ""
        ).strip()
        product_id = raw_product_id.lstrip("0") if raw_product_id.isdigit() else raw_product_id
        product_id = product_id or ("0" if raw_product_id else "")
        product_sku = self._lookup_product_sku(product_id) if product_id else ""
        return {
            "material_product_id": product_id or None,
            "product_id": product_id or None,
            "material_code": product_id or None,
            "material_sku": product_sku or None,
            "sku": product_sku or None,
        }

    def _snapshot_requires_part(
        self, snapshot: Dict[str, Any], item: Dict[str, Any]
    ) -> bool:
        payload = snapshot.get("job_payload")
        if not isinstance(payload, dict) or not isinstance(item, dict):
            return False
        item_product_id = self._normalize_material_match_key(
            item.get("material_product_id")
            or item.get("product_id")
            or item.get("material_code")
        )
        item_sku = self._normalize_material_match_key(
            item.get("material_sku") or item.get("sku") or item.get("product_sku")
        )
        for part in self._job_part_rows(payload):
            part_product_id = self._normalize_material_match_key(
                part.get("part_product_id")
                or part.get("product_id")
                or part.get("material_code")
            )
            part_sku = self._normalize_material_match_key(
                part.get("sku")
                or part.get("part_sku")
                or part.get("product_sku")
                or part.get("material_sku")
            )
            if item_product_id and part_product_id and item_product_id == part_product_id:
                return True
            if item_sku and part_sku and item_sku == part_sku:
                return True
        if item_product_id or item_sku:
            return False
        item_keys = self._raw_material_match_keys(item) | self._raw_material_name_keys(item)
        return any(
            item_keys.intersection(
                self._part_material_match_keys(part)
                | self._part_material_name_keys(part)
            )
            for part in self._job_part_rows(payload)
        )

    def _snapshot_matches_finished_item(
        self,
        snapshot: Dict[str, Any],
        item: Dict[str, Any],
        scanned_job_code: str,
    ) -> bool:
        """Match a finished-item QR to its exact open mixing job."""
        snapshot_job_code = self._mixing_job_key(
            snapshot.get("job_code") or snapshot.get("job_name")
        )
        normalized_scan_job = self._mixing_job_key(scanned_job_code)
        # Product-part labels commonly carry an empty/zero PO. Never treat
        # that placeholder as a job identity.
        if normalized_scan_job and normalized_scan_job != "0":
            if normalized_scan_job == snapshot_job_code:
                return True

        payload = snapshot.get("job_payload")
        identity = self._job_product_identity_from_payload(
            payload if isinstance(payload, dict) else {}
        )
        output_product_id = self._normalize_material_match_key(
            identity.get("product_id") or snapshot.get("product_id")
        )
        output_sku = self._normalize_material_match_key(
            identity.get("product_sku") or snapshot.get("product_sku")
        )
        scanned_product_id = self._normalize_material_match_key(
            item.get("product_id") or item.get("material_product_id")
        )
        scanned_sku = self._normalize_material_match_key(
            item.get("sku") or item.get("material_sku")
        )
        return bool(
            (
                scanned_product_id
                and output_product_id
                and scanned_product_id == output_product_id
            )
            or (scanned_sku and output_sku and scanned_sku == output_sku)
        )

    def _route_product_part_to_open_job(self, raw: str, result: Any) -> str:
        item = self._part_scan_identity(raw, result)
        if not item:
            return ""
        self._capture_current_mixing_session()
        if result.kind == "PACK":
            scanned_job_code = self._mixing_job_key(
                self._extract_job_code_from_pack_qr(raw)
            )
            output_matches = [
                key
                for key, snapshot in self._mixing_sessions.items()
                if self._mixing_session_is_for_current_machine(snapshot)
                and bool(snapshot.get("mixing_open", True))
                and self._snapshot_matches_finished_item(
                    snapshot, item, scanned_job_code
                )
            ]
            if output_matches:
                current_key = self._mixing_job_key(
                    self.state.job_code or self.state.job_name
                )
                target_key = current_key if current_key in output_matches else max(
                    output_matches,
                    key=lambda key: float(
                        self._mixing_sessions[key].get("mixing_last_active_at") or 0.0
                    ),
                )
                if target_key != current_key:
                    self._switch_mixing_session(
                        target_key, reason="matched scanned finished item"
                    )
                return target_key

        # Product-part labels do not own the active job selection. A material
        # can be required by multiple open jobs, so automatically choosing one
        # would place stock in the wrong session. Only the displayed job may
        # accept the part; the operator must scan its JOB QR before the part.
        current_key = self._mixing_job_key(
            self.state.job_code or self.state.job_name
        )
        matches = [
            key
            for key, snapshot in self._mixing_sessions.items()
            if self._mixing_session_is_for_current_machine(snapshot)
            and bool(snapshot.get("mixing_open", True))
            and self._snapshot_requires_part(snapshot, item)
        ]
        if not matches:
            return ""
        if current_key in matches:
            return current_key

        job_labels = []
        for key in matches[:3]:
            snapshot = self._mixing_sessions.get(key) or {}
            job_labels.append(
                str(snapshot.get("job_name") or snapshot.get("job_code") or key)
            )
        target_text = ", ".join(job_labels)
        self.status.setText(
            f"Product part not recorded. Scan JOB QR first: {target_text}."
        )
        self._show_info_overlay(
            "SCAN JOB QR FIRST",
            "This product part belongs to another open mixing job.\n"
            f"Scan the intended JOB QR first, then scan this part again.\n"
            f"Matching job: {target_text}",
            hide_ms=4200,
        )
        return _MIXING_SCAN_JOB_FIRST

    def _apply_mixing_panel_visibility(self) -> None:
        """Restore the complete production UI while retaining Mixing Mode."""
        if getattr(self, "_mixing_full_ui_restored", False):
            return
        required_widgets = (
            "rightTopRow",
            "cardSessionActivityOuter",
            "rawCycleSwapWrap",
            "cardJobDetailsOuter",
            "historyRowOuter",
        )
        if not all(hasattr(self, name) for name in required_widgets):
            return
        if hasattr(self, "rightTopRow"):
            self.rightTopRow.show()
        if hasattr(self, "rightTopSpacer"):
            self.rightTopSpacer.show()
        if hasattr(self, "rejectLabel"):
            self.rejectLabel.show()
        if hasattr(self, "rejectDetailTable"):
            self.rejectDetailTable.show()
        if hasattr(self, "cardSessionActivityOuter"):
            self.cardSessionActivityOuter.setMinimumHeight(374)
            self.cardSessionActivityOuter.setMaximumHeight(374)
            self.cardSessionActivityOuter.setSizePolicy(
                production_client.QSizePolicy.Policy.Preferred,
                production_client.QSizePolicy.Policy.Fixed,
            )

        raw_host = self.findChild(production_client.QFrame, "RawMirrorHost")
        raw_outer = raw_host.parentWidget() if raw_host is not None else None
        downtime_host = self.findChild(
            production_client.QFrame, "DowntimeMirrorHost"
        )
        downtime_outer = (
            downtime_host.parentWidget() if downtime_host is not None else None
        )

        if hasattr(self, "rawCycleSwapWrap"):
            raw_layout = self.rawCycleSwapWrap.layout()
            if raw_layout is not None:
                if raw_outer is not None and raw_layout.indexOf(raw_outer) < 0:
                    raw_layout.insertWidget(0, raw_outer, 1)
                if downtime_outer is not None and raw_layout.indexOf(downtime_outer) < 0:
                    raw_layout.addWidget(downtime_outer, 1)
            if raw_outer is not None:
                raw_outer.show()
            if downtime_outer is not None:
                downtime_outer.setMinimumHeight(150)
                downtime_outer.setMaximumHeight(16777215)
                downtime_outer.setSizePolicy(
                    production_client.QSizePolicy.Policy.Expanding,
                    production_client.QSizePolicy.Policy.Expanding,
                )
                downtime_host.setMinimumHeight(150)
                downtime_host.setMaximumHeight(16777215)
                downtime_outer.show()
                self.mixingDowntimeOuter = downtime_outer
            self.rawCycleSwapWrap.setMinimumHeight(440)
            self.rawCycleSwapWrap.setMaximumHeight(16777215)
            self.rawCycleSwapWrap.setSizePolicy(
                production_client.QSizePolicy.Policy.Expanding,
                production_client.QSizePolicy.Policy.Expanding,
            )
            self.rawCycleSwapWrap.show()

        main_grid = None
        if hasattr(self, "leftWrap") and self.leftWrap.layout() is not None:
            left_layout = self.leftWrap.layout()
            self.leftWrap.setMinimumHeight(0)
            self.leftWrap.setSizePolicy(
                production_client.QSizePolicy.Policy.Preferred,
                production_client.QSizePolicy.Policy.Preferred,
            )
            for layout_index in range(left_layout.count()):
                layout_item = left_layout.itemAt(layout_index)
                candidate = layout_item.layout() if layout_item is not None else None
                if not isinstance(candidate, production_client.QGridLayout):
                    continue
                if candidate.indexOf(self.cardProductionOuter) >= 0:
                    main_grid = candidate
                    left_layout.setStretch(layout_index, 1)
                    break
        if main_grid is not None:
            if main_grid.indexOf(self.rawCycleSwapWrap) < 0:
                main_grid.addWidget(self.rawCycleSwapWrap, 3, 0, 1, 2)
            main_grid.setRowStretch(0, 2)
            main_grid.setRowStretch(1, 2)
            main_grid.setRowStretch(2, 0)
            main_grid.setRowStretch(3, 0)

        if hasattr(self, "rightPanel") and self.rightPanel.layout() is not None:
            right_layout = self.rightPanel.layout()
            self.rightPanel.setMinimumHeight(0)
            self.rightPanel.setSizePolicy(
                production_client.QSizePolicy.Policy.Preferred,
                production_client.QSizePolicy.Policy.Preferred,
            )
            if right_layout.indexOf(self.cardJobDetailsOuter) < 0:
                top_index = right_layout.indexOf(self.rightTopRow)
                right_layout.insertWidget(
                    top_index + 1 if top_index >= 0 else right_layout.count(),
                    self.cardJobDetailsOuter,
                )
            self.cardJobDetailsOuter.setMinimumHeight(370)
            self.cardJobDetailsOuter.setMaximumHeight(470)
            self.cardJobDetailsOuter.setSizePolicy(
                production_client.QSizePolicy.Policy.Preferred,
                production_client.QSizePolicy.Policy.Maximum,
            )
            self.cardJobDetailsOuter.show()
            if hasattr(self, "historyRowOuter"):
                history_index = right_layout.indexOf(self.historyRowOuter)
                if history_index >= 0:
                    right_layout.setStretch(history_index, 1)
                self.historyRowOuter.setMinimumHeight(0)
                self.historyRowOuter.setMaximumHeight(16777215)
                self.historyRowOuter.setSizePolicy(
                    production_client.QSizePolicy.Policy.Expanding,
                    production_client.QSizePolicy.Policy.Expanding,
                )
        self._mixing_full_ui_restored = True
    def _apply_graphics_mode(self, mode: Any, persist: bool = True):
        """Use the same visual-effects preferences as the production client."""
        super()._apply_graphics_mode(mode, persist=persist)

    def _setup_scanner_input(self):
        """Enable immediate completion for both keyboard and serial scanners."""
        mode = str(
            self.client_config.get("scanner_mode", production_client.SCANNER_MODE)
        ).strip().lower()
        scanner_port = str(
            self.client_config.get(
                "scanner_com_port", production_client.SCANNER_COM_PORT
            )
        ).strip() or production_client.SCANNER_COM_PORT
        if mode not in ("auto", "keyboard", "serial"):
            mode = "auto"

        self.filter = _MixingScannerFilter(
            plain_digit_numpad_enabled=lambda: bool(
                mode == "serial" or self._serial_scanner_connected
            )
        )
        app = production_client.QApplication.instance()
        if app is not None:
            app.installEventFilter(self.filter)
        else:
            self.installEventFilter(self.filter)
        self.filter.scanned.connect(self.scan_received.emit)
        self.filter.minimize_requested.connect(self._minimize_to_desktop)
        self.filter.packing_guide_requested.connect(self._toggle_packing_guide)
        self.filter.reject_details_requested.connect(
            self._open_reject_details_shortcut
        )
        self.filter.job_api_refresh_requested.connect(
            self._refresh_running_jobs_shortcut
        )
        if mode == "keyboard":
            self._set_status_text("Scanner input: Keyboard mode (instant scan)")
            return

        if production_client.serial is None:
            if mode == "serial":
                self._set_status_text(
                    "Scanner input: Serial requested but pyserial is not installed."
                )
            else:
                self._set_status_text(
                    "Scanner input: Keyboard mode (pyserial not installed)"
                )
            return

        self._serial_thread = production_client.threading.Thread(
            target=self._serial_reader_loop,
            daemon=True,
        )
        self._serial_thread.start()
        if mode == "auto":
            self._set_status_text(
                f"Scanner input: Auto instant mode (keyboard + serial {scanner_port})"
            )
        else:
            self._set_status_text(
                f"Scanner input: Serial instant mode ({scanner_port}) + keyboard numpad"
            )

    def _serial_reader_loop(self):
        """Emit every serial QR as soon as CR or LF arrives.

        The production reader uses ``readline()``, which waits specifically for
        LF.  The test scanner terminates with CR, so its first QR could remain
        buffered and be joined to the next QR.  Mixing Mode accepts CR, LF, and
        CRLF, with a short idle flush for scanners configured without a suffix.
        """
        serial_module = production_client.serial
        if serial_module is None:
            return

        while not self._serial_stop.is_set():
            scanner_port = str(
                self.client_config.get(
                    "scanner_com_port", production_client.SCANNER_COM_PORT
                )
            ).strip() or production_client.SCANNER_COM_PORT
            scanner_baudrate = int(
                self.client_config.get(
                    "scanner_baudrate", production_client.SCANNER_BAUDRATE
                )
            )
            configured_timeout = max(
                production_client.SCANNER_MIN_TIMEOUT_SECONDS,
                float(
                    self.client_config.get(
                        "scanner_timeout", production_client.SCANNER_TIMEOUT
                    )
                ),
            )
            read_timeout = min(0.05, configured_timeout)
            # A QR at 9600 baud has sub-millisecond byte spacing.  Sixty
            # milliseconds of silence safely marks the end even when the
            # scanner is configured without CR/LF.
            idle_flush_seconds = 0.06
            framer = _SerialScanFramer()
            last_data_at = time.monotonic()
            try:
                serial_options = {
                    "port": scanner_port,
                    "baudrate": scanner_baudrate,
                    "timeout": read_timeout,
                }
                # The Mixing client must be the only process consuming this
                # byte stream.  Two readers on one tty divide the bytes between
                # them, producing truncated QRs that only appear to work after
                # several scans.  TIOCEXCL prevents a second Linux client from
                # opening the scanner while Mixing owns it.
                if os.name == "posix":
                    serial_options["exclusive"] = True
                with serial_module.Serial(**serial_options) as scanner:
                    self._serial_scanner_connected = True
                    self.scanner_status.emit(
                        f"Scanner serial connected: {scanner_port} @ {scanner_baudrate}"
                    )
                    while not self._serial_stop.is_set():
                        waiting = int(getattr(scanner, "in_waiting", 0) or 0)
                        chunk = scanner.read(max(1, waiting))
                        now = time.monotonic()
                        if chunk:
                            last_data_at = now
                            for scan in framer.feed(chunk):
                                self.scan_received.emit(scan)
                        elif now - last_data_at >= idle_flush_seconds:
                            for scan in framer.flush():
                                self.scan_received.emit(scan)
                            last_data_at = now
            except Exception as error:
                self._serial_scanner_connected = False
                self.scanner_status.emit(
                    f"Scanner serial retry ({scanner_port}): {error}"
                )
                self._serial_stop.wait(2.0)
            finally:
                self._serial_scanner_connected = False

    def _apply_mixing_labels(self) -> None:
        if not getattr(self, "_mixing_mode_ready", False):
            return

        if hasattr(self, "lblPack"):
            self.lblPack.title = "SACK"
            self.lblPack.update()
        if hasattr(self, "lblGood"):
            self.lblGood.title = "GOOD KG"
            self.lblGood.update()
        if hasattr(self, "lblTotalGood"):
            self.lblTotalGood.title = "TOTAL KG"
            self.lblTotalGood.update()
        if hasattr(self, "jobPartsTable") and self.jobPartsTable is not None:
            header = self.jobPartsTable.horizontalHeaderItem(3)
            if header is not None:
                header.setText("Rqst Part Qty")

        text_widget_types = (
            production_client.QLabel,
            production_client.QPushButton,
            production_client.QCheckBox,
        )
        for widget_type in text_widget_types:
            for widget in self.findChildren(widget_type):
                current = widget.text()
                updated = replace_pack_terms(current)
                if updated != current:
                    widget.setText(updated)

        for combo in self.findChildren(production_client.QComboBox):
            for index in range(combo.count()):
                current = combo.itemText(index)
                updated = replace_pack_terms(current)
                if updated != current:
                    combo.setItemText(index, updated)

        for table in self.findChildren(production_client.QTableWidget):
            for column in range(table.columnCount()):
                item = table.horizontalHeaderItem(column)
                if item is not None:
                    item.setText(replace_pack_terms(item.text()))

    def _refresh_ui(self, force: bool = False):
        super()._refresh_ui(force=force)

    def _refresh_ui_now(self):
        if hasattr(self, "state"):
            self._ensure_mixing_kg_counter()
        super()._refresh_ui_now()
        self._apply_mixing_panel_visibility()
        self._apply_mixing_labels()
        self._apply_mixing_cumulative_part_totals()

    @staticmethod
    def _mixing_qty_text(value: Any) -> str:
        number = float(value or 0.0)
        if abs(number - round(number)) <= 1e-9:
            return str(int(round(number)))
        return f"{number:.4f}".rstrip("0").rstrip(".")

    def _mixing_cumulative_scanned_part_qty(
        self, part: Dict[str, Any]
    ) -> float:
        """Total unique product-part QR quantity across this job's shifts."""
        machine_code = str(self.state.machine_code or "").strip().upper()
        job_code = self._normalize_job_code(self.state.job_code)
        if not machine_code or not job_code:
            return 0.0

        part_keys = (
            self._part_material_match_keys(part)
            | self._part_material_name_keys(part)
        )
        if not part_keys:
            return 0.0

        total = 0.0
        seen_scans = set()

        def add_logs(logs: Any, scope: str) -> None:
            nonlocal total
            for index, row in enumerate(logs or []):
                if not isinstance(row, dict):
                    continue
                if str(row.get("source") or "").startswith(
                    "FINISH_SHIFT_PART_CARRYOVER"
                ):
                    # This is unused stock from an earlier scan, not a new QR.
                    continue
                row_keys = (
                    self._raw_material_match_keys(row)
                    | self._raw_material_name_keys(row)
                )
                if not part_keys.intersection(row_keys):
                    continue
                stable_scan_id = str(
                    row.get("unique_key")
                    or row.get("raw_scan")
                    or row.get("scan_id")
                    or ""
                ).strip()
                if stable_scan_id:
                    scan_key = stable_scan_id
                else:
                    scan_key = "|".join(
                        (
                            scope,
                            str(index),
                            str(row.get("scanned_at") or ""),
                            str(row.get("material_product_id") or ""),
                            str(row.get("qty") or ""),
                        )
                    )
                if scan_key in seen_scans:
                    continue
                seen_scans.add(scan_key)
                total += max(0.0, self._parse_number(row.get("qty")))

        add_logs(self._mixing_cumulative_part_scan_rows(), "cumulative")
        return total

    def _sync_mixing_material_history_from_server(self, *, force: bool = False) -> bool:
        """Hydrate legacy cumulative scans from completed server shifts."""
        machine_code = str(self.state.machine_code or "").strip().upper()
        job_code = self._normalize_job_code(self.state.job_code)
        sync_key = f"{machine_code}|{job_code}" if machine_code and job_code else ""
        if not sync_key or (not force and sync_key in self._mixing_history_synced_keys):
            return False
        server_url = str(
            (self.client_config or {}).get("server_url", production_client.SERVER_URL)
            or production_client.SERVER_URL
        ).strip().rstrip("/")
        if not server_url:
            return False
        try:
            response = production_client.requests.get(
                f"{server_url}/api/mixing/material-history",
                params={"machine_code": machine_code, "job_code": job_code},
                headers={"Accept": "application/json"},
                timeout=4,
            )
            response.raise_for_status()
            body = response.json()
            server_scans = body.get("scans") if isinstance(body, dict) else None
            if not isinstance(server_scans, list):
                return False
            reset_cutoff_raw = str(
                (self.client_config or {}).get(
                    "mixing_history_not_before_utc", ""
                )
                or ""
            ).strip()
            if reset_cutoff_raw:
                try:
                    reset_cutoff = production_client.datetime.fromisoformat(
                        reset_cutoff_raw.replace("Z", "+00:00")
                    )
                    if reset_cutoff.tzinfo is None:
                        reset_cutoff = reset_cutoff.replace(
                            tzinfo=production_client.timezone.utc
                        )
                    filtered_scans = []
                    for row in server_scans:
                        if not isinstance(row, dict):
                            continue
                        scanned_raw = str(
                            row.get("scanned_at")
                            or row.get("carried_at_utc")
                            or row.get("created_at_utc")
                            or ""
                        ).strip()
                        if not scanned_raw:
                            continue
                        try:
                            scanned_at = production_client.datetime.fromisoformat(
                                scanned_raw.replace("Z", "+00:00")
                            )
                            if scanned_at.tzinfo is None:
                                scanned_at = scanned_at.replace(
                                    tzinfo=production_client.timezone.utc
                                )
                        except ValueError:
                            continue
                        if scanned_at >= reset_cutoff:
                            filtered_scans.append(row)
                    server_scans = filtered_scans
                except ValueError:
                    pass
        except Exception as error:
            if hasattr(self, "status"):
                self.status.setText(f"Mixing history sync pending: {error}")
            return False

        rows = production_client._load_shift_carryover_json()
        target = next(
            (
                row
                for row in rows
                if isinstance(row, dict)
                and self._shift_carryover_key(
                    row.get("machine_code"), row.get("job_code")
                )
                == sync_key
            ),
            None,
        )
        if target is None:
            target = {
                "key": sync_key,
                "client_id": self._current_client_id(),
                "machine_code": machine_code,
                "job_code": self.state.job_code,
                "job_name": self.state.job_name,
                "part_availability_carryover_logs": [],
                "butal_carryover": {},
            }
            rows.append(target)

        combined = [
            dict(row)
            for row in (target.get("mixing_cumulative_part_scans") or [])
            if isinstance(row, dict)
        ]
        combined.extend(dict(row) for row in server_scans if isinstance(row, dict))
        unique_rows: List[Dict[str, Any]] = []
        seen = set()
        for index, row in enumerate(combined):
            scan_id = str(
                row.get("raw_scan")
                or row.get("mixing_cumulative_scan_id")
                or row.get("unique_key")
                or row.get("scan_id")
                or ""
            ).strip()
            if not scan_id:
                scan_id = "|".join(
                    (
                        str(index),
                        str(row.get("scanned_at") or ""),
                        str(row.get("material_product_id") or ""),
                        str(row.get("material_sku") or ""),
                        str(row.get("qty") or ""),
                    )
                )
            if scan_id in seen:
                continue
            seen.add(scan_id)
            item = dict(row)
            item["mixing_cumulative_scan_id"] = scan_id
            item["source"] = "MIXING_SERVER_SHIFT_HISTORY"
            unique_rows.append(item)
        target["mixing_cumulative_part_scans"] = unique_rows
        target["mixing_history_synced_at"] = production_client.datetime.now(
            production_client.timezone.utc
        ).isoformat()
        if not production_client._save_shift_carryover_json(rows):
            return False
        self._mixing_history_synced_keys.add(sync_key)
        return True

    def _sync_mixing_material_history_and_refresh(self) -> None:
        if self._sync_mixing_material_history_from_server():
            self._capture_current_mixing_session()
            self._refresh_ui(force=True)

    def _mixing_cumulative_part_scan_rows(self) -> List[Dict[str, Any]]:
        """Return de-duplicated original scans retained across shift clears."""
        machine_code = str(self.state.machine_code or "").strip().upper()
        job_code = self._normalize_job_code(self.state.job_code)
        if not machine_code or not job_code:
            return []

        collected: List[Dict[str, Any]] = []
        carry_records = [
            row
            for row in production_client._load_shift_carryover_json()
            if isinstance(row, dict)
            and str(row.get("machine_code") or "").strip().upper() == machine_code
            and self._normalize_job_code(row.get("job_code")) == job_code
        ]
        if carry_records:
            carry_record = carry_records[-1]
            saved_scans = carry_record.get("mixing_cumulative_part_scans")
            if isinstance(saved_scans, list):
                collected.extend(
                    dict(row) for row in saved_scans if isinstance(row, dict)
                )
            else:
                # Compatibility for a shift completed before the cumulative
                # ledger existed. Recover the original quantity from its QR;
                # the carryover row's qty is only the unused remainder.
                for carry_row in carry_record.get(
                    "part_availability_carryover_logs"
                ) or []:
                    if not isinstance(carry_row, dict):
                        continue
                    item = dict(carry_row)
                    raw_scan = str(item.get("raw_scan") or "").strip()
                    parsed = production_client.parse_scan(raw_scan) if raw_scan else None
                    original_qty = self._parse_number(
                        getattr(parsed, "qty", 0) if parsed is not None else 0
                    )
                    if original_qty > 0:
                        item["qty"] = original_qty
                    item["unique_key"] = raw_scan or str(
                        item.get("unique_key") or ""
                    )
                    item["source"] = "MIXING_CUMULATIVE_LEDGER"
                    collected.append(item)

        for row in self.state.raw_material_logs or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("source") or "").startswith(
                "FINISH_SHIFT_PART_CARRYOVER"
            ):
                continue
            collected.append(dict(row))

        unique_rows: List[Dict[str, Any]] = []
        seen = set()
        for index, row in enumerate(collected):
            scan_id = str(
                row.get("raw_scan")
                or row.get("unique_key")
                or row.get("scan_id")
                or ""
            ).strip()
            if not scan_id:
                scan_id = "|".join(
                    (
                        str(index),
                        str(row.get("scanned_at") or ""),
                        str(row.get("material_product_id") or ""),
                        str(row.get("material_sku") or ""),
                        str(row.get("qty") or ""),
                    )
                )
            if scan_id in seen:
                continue
            seen.add(scan_id)
            item = dict(row)
            item["mixing_cumulative_scan_id"] = scan_id
            unique_rows.append(item)
        return unique_rows

    def _build_part_availability_carryover_logs(self) -> List[Dict[str, Any]]:
        """Calculate Mixing balance from cumulative scans minus cumulative KG use."""
        counter_kg = self._ensure_mixing_kg_counter()
        raw_logs = [
            row for row in (self.state.raw_material_logs or [])
            if isinstance(row, dict)
        ]
        carry_rows: List[Dict[str, Any]] = []
        for part in self._job_part_rows():
            if not isinstance(part, dict) or bool(part.get("_validation_exempt")):
                continue
            scanned_qty = self._mixing_cumulative_scanned_part_qty(part)
            per_kg = max(
                0.0,
                self._parse_number(
                    self._resolve_part_qty_per_unit(part).get("value")
                ),
            )
            used_qty = float(counter_kg) * per_kg
            balance_qty = max(0.0, scanned_qty - used_qty)
            matched = self._raw_logs_for_part(
                raw_logs,
                part,
                total_part_count=len(self._job_part_rows()),
            )
            source = dict(matched[-1]) if matched else {}
            product_id = str(
                part.get("part_product_id")
                or part.get("product_id")
                or source.get("material_product_id")
                or ""
            ).strip()
            sku = str(
                part.get("sku")
                or part.get("part_sku")
                or source.get("material_sku")
                or ""
            ).strip()
            name = str(
                part.get("name")
                or part.get("part_name")
                or source.get("material_name")
                or sku
                or "Job Part"
            ).strip()
            source.update(
                {
                    "material": name,
                    "material_name": name,
                    "material_product_id": product_id or None,
                    "material_sku": sku or None,
                    "job_part_name": name,
                    "job_part_sku": sku or None,
                    "qty": balance_qty,
                    "unit": self._part_unit_kind(part),
                    "source": "FINISH_SHIFT_PART_CARRYOVER",
                    "unique_key": (
                        f"MIXING-SHIFT-CARRY:{self._normalize_job_code(self.state.job_code)}:"
                        f"{product_id or sku}:{production_client.datetime.now(production_client.timezone.utc).isoformat()}"
                    ),
                    "carryover_from_job_code": str(self.state.job_code or ""),
                    "carryover_available_qty": balance_qty,
                    "mixing_cumulative_scanned_qty": scanned_qty,
                    "mixing_cumulative_used_qty": used_qty,
                    "mixing_kg_counter": counter_kg,
                    "part_qty_per_unit": per_kg,
                    "carried_at_utc": production_client.datetime.now(
                        production_client.timezone.utc
                    ).isoformat(),
                }
            )
            carry_rows.append(source)
        return carry_rows

    def _save_shift_carryover_record(self, shift_payload: Dict[str, Any]) -> bool:
        """Persist both unused stock and total original scans for next shift."""
        cumulative_scans = self._mixing_cumulative_part_scan_rows()
        saved = super()._save_shift_carryover_record(shift_payload)
        if not saved:
            return saved

        machine_code = str(
            shift_payload.get("machine_code") or self.state.machine_code or ""
        ).strip()
        job_code = str(
            shift_payload.get("job_code") or self.state.job_code or ""
        ).strip()
        key = self._shift_carryover_key(machine_code, job_code)
        rows = production_client._load_shift_carryover_json()
        target = next(
            (
                row
                for row in rows
                if isinstance(row, dict)
                and self._shift_carryover_key(
                    row.get("machine_code"), row.get("job_code")
                )
                == key
            ),
            None,
        )
        if target is None:
            target = {
                "key": key,
                "client_id": self._current_client_id(),
                "machine_code": machine_code,
                "job_code": job_code,
                "job_name": shift_payload.get("job_name") or self.state.job_name,
                "part_availability_carryover_logs": [],
                "butal_carryover": {},
                "saved_at_utc": production_client.datetime.now(
                    production_client.timezone.utc
                ).isoformat(),
            }
            rows.append(target)
        target["mixing_cumulative_part_scans"] = cumulative_scans
        target["mixing_kg_counter"] = int(
            shift_payload.get("mixing_kg_counter_end")
            or self._ensure_mixing_kg_counter()
            or 0
        )
        target["mixing_last_sack_cycle_time_seconds"] = (
            shift_payload.get("mixing_sack_cycle_time_seconds")
        )
        target["mixing_part_balances"] = [
            dict(row)
            for row in (shift_payload.get("part_availability_carryover_logs") or [])
            if isinstance(row, dict)
        ]
        return production_client._save_shift_carryover_json(rows)

    def _restore_same_job_part_carryover(self) -> int:
        """Restore stock plus the prior KG counter and actual sack cycle."""
        restored = super()._restore_same_job_part_carryover()
        key = self._shift_carryover_key(
            self.state.machine_code,
            self.state.job_code,
        )
        matches = [
            row
            for row in production_client._load_shift_carryover_json()
            if isinstance(row, dict)
            and self._shift_carryover_key(
                row.get("machine_code"), row.get("job_code")
            )
            == key
        ]
        if matches:
            latest = matches[-1]
            counter = self._parse_int_value(latest.get("mixing_kg_counter"))
            if counter is not None:
                self.state.machine_counter_current = max(0, counter)
                self.state.machine_counter_shift_start = max(0, counter)
                self.state.operator_shift_baseline_machine_counter_start = max(0, counter)
            cycle = self._parse_number(
                latest.get("mixing_last_sack_cycle_time_seconds")
            )
            if cycle > 0:
                cycle_text = f"{cycle:.2f}".rstrip("0").rstrip(".")
                self.state.cycle_time_current = cycle_text
                self.state.cycle_time_temporary = cycle_text
        return restored

    def _apply_mixing_cumulative_part_totals(self) -> None:
        """Show cumulative unique scans without changing production client UI."""
        table = getattr(self, "jobPartsTable", None)
        if table is None or not self.state.job_code:
            return

        parts_by_sku: Dict[str, Dict[str, Any]] = {}
        for part in self._job_part_rows():
            if not isinstance(part, dict):
                continue
            sku_key = self._normalize_material_match_key(
                part.get("sku")
                or part.get("part_sku")
                or part.get("product_sku")
            )
            if sku_key:
                parts_by_sku[sku_key] = part

        for row_index in range(int(table.rowCount() or 0)):
            sku_item = table.item(row_index, 0)
            if sku_item is None:
                continue
            part = parts_by_sku.get(
                self._normalize_material_match_key(sku_item.text())
            )
            if part is None:
                continue
            scanned_qty = self._mixing_cumulative_scanned_part_qty(part)
            requested_qty = max(
                0.0, self._parse_number(part.get("request_part_qty"))
            )
            scanned_text = self._mixing_qty_text(scanned_qty)
            display = scanned_text
            if requested_qty > 0:
                display = (
                    f"{scanned_text} / "
                    f"{self._mixing_qty_text(requested_qty)}"
                )
            item = table.item(row_index, 3)
            if item is None:
                item = production_client.QTableWidgetItem()
                table.setItem(row_index, 3, item)
            item.setText(display)
            item.setTextAlignment(
                int(production_client.Qt.AlignmentFlag.AlignCenter)
            )

    def _refresh_linkage_panel(self):
        """Use Linkage Mirror as a compact list of open mixing jobs."""
        if not hasattr(self, "linkageMirrorFrame"):
            return
        title = self.linkageMirrorFrame.findChild(
            production_client.QLabel, "RightTitle"
        )
        if title is not None:
            title.setText("OPEN MIXING JOBS")

        counter_frame = self.linkageMirrorFrame.findChild(
            production_client.QFrame, "LinkageMirrorRight"
        )
        if counter_frame is not None:
            counter_frame.hide()

        self._configure_mixing_jobs_grid()

        current_key = self._mixing_job_key(
            getattr(self.state, "job_code", None)
            or getattr(self.state, "job_name", None)
        )
        rows = sorted(
            (
                item
                for item in self._mixing_sessions.items()
                if self._mixing_session_is_for_current_machine(item[1])
                and bool(item[1].get("mixing_open", True))
            ),
            key=lambda item: float(item[1].get("mixing_last_active_at") or 0.0),
            reverse=True,
        )
        labels = list(getattr(self, "mixingJobGridLabels", []) or [])
        if not labels:
            labels = [
                getattr(self, "linkageMirrorJob1", None),
                getattr(self, "linkageMirrorJob2", None),
                getattr(self, "linkageMirrorJob3", None),
            ]
        for index, label in enumerate(labels):
            if label is None:
                continue
            if index >= len(rows):
                self._set_linkage_job_label_text(label, "-")
                label.setToolTip("")
                continue
            key, snapshot = rows[index]
            job_name = str(
                snapshot.get("job_name") or snapshot.get("job_code") or key
            ).strip()
            job_code = str(snapshot.get("job_code") or key).strip()
            state_text = "ACTIVE" if key == current_key else "RUNNING"
            if index == len(labels) - 1 and len(rows) > len(labels):
                display_text = (
                    f"{state_text}  {job_name}  (+{len(rows) - len(labels)} more)"
                )
            else:
                suffix = f" ({job_code})" if job_code and job_code != job_name else ""
                display_text = f"{state_text}  {job_name}{suffix}"
            self._set_linkage_job_label_text(label, display_text)
            label.setToolTip(f"{state_text}: {job_name} {job_code}".strip())

        if hasattr(self, "linkageMirrorOuter"):
            self.linkageMirrorOuter.show()
        self._refresh_history_panel()
        self._apply_mixing_panel_visibility()

    def _mixing_kg_per_sack(self) -> int:
        """Resolve the finished-product weight represented by one sack."""
        generated_qty = super()._generated_pack_qty_from_job_payload()
        if generated_qty is not None and int(generated_qty or 0) > 0:
            return int(generated_qty)

        payload = self.state.job_payload if isinstance(self.state.job_payload, dict) else {}
        context = self._extract_job_payload_context(payload)
        job = context.get("job") if isinstance(context.get("job"), dict) else {}
        details = (
            context.get("job_details")
            if isinstance(context.get("job_details"), dict)
            else {}
        )
        for row in (details, job, payload):
            for key in (
                "kg_per_sack",
                "weight_per_sack",
                "default_qty",
                "default_quantity",
                "pack_qty",
                "packing_qty",
                "qty_per_pack",
                "standard_qty",
            ):
                value = self._parse_number(row.get(key))
                if value > 0:
                    return max(1, int(round(value)))

        identity = self._job_product_identity_from_payload(payload)
        product_id = str(identity.get("product_id") or "").strip()
        catalog_qty = self._lookup_product_default_qty(product_id) if product_id else 0
        if catalog_qty > 0:
            return max(1, int(round(catalog_qty)))

        product_name = str(identity.get("product_name") or "")
        match = re.search(
            r"(?<!\d)(\d+(?:\.\d+)?)\s*(?:kg|kgs|kilogram|kilograms)\b",
            product_name,
            flags=re.IGNORECASE,
        )
        if match:
            return max(1, int(round(float(match.group(1)))))
        return 0

    def _apply_mixing_finished_sack_quantity(self, event: Dict[str, Any]) -> None:
        """Convert one accepted finished sack into its configured kg value."""
        allocation = (
            event.get("linkage_output_allocation")
            if isinstance(event.get("linkage_output_allocation"), dict)
            else {}
        )
        # The trial mode currently changes the main, non-linkage mixing flow.
        # Linked jobs retain the production client's allocation rules.
        if bool(allocation.get("special")):
            return

        counter_before = self._ensure_mixing_kg_counter()
        kg_per_sack = self._mixing_kg_per_sack()
        sack_count = max(1, int(event.get("pack_qty") or 1))
        desired_kg = sack_count * kg_per_sack
        recorded_kg = max(0, int(event.get("qty") or 0))
        if desired_kg <= 0:
            return

        difference = desired_kg - recorded_kg
        if difference:
            self.state.good_total = max(0, int(self.state.good_total or 0) + difference)

        event["qty"] = desired_kg
        event["mixing_sack_count"] = sack_count
        event["mixing_kg_per_sack"] = kg_per_sack
        event["mixing_good_kg"] = desired_kg
        allocation.update(
            {
                "main_qty": desired_kg,
                "full_pack_qty": desired_kg,
                "mixing_sack_count": sack_count,
                "mixing_kg_per_sack": kg_per_sack,
            }
        )
        event["linkage_output_allocation"] = allocation

        pack_record = (
            event.get("pack_record") if isinstance(event.get("pack_record"), dict) else {}
        )
        pack_record.update(
            {
                "qty_q": desired_kg,
                "good_qty": desired_kg,
                "main_job_output_qty": desired_kg,
                "completed_pack_qty": sack_count,
                "mixing_sack_count": sack_count,
                "mixing_kg_per_sack": kg_per_sack,
                "mixing_good_kg": desired_kg,
                "linkage_output_allocation": dict(allocation),
            }
        )
        event["pack_record"] = pack_record

        pack_key = str(event.get("pack_key") or "").strip()
        for row in reversed(self.state.product_pack_history_logs or []):
            if not isinstance(row, dict):
                continue
            row_key = self._pack_history_key(row)
            if pack_key and row_key != pack_key:
                continue
            row.update(pack_record)
            break

        self.state.machine_counter_current = counter_before + desired_kg
        self._sync_machine_counter_current()
        self.status.setText(
            f"Sack +{sack_count} | Good KG +{desired_kg} "
            f"({kg_per_sack} kg per sack)"
        )
        self._refresh_ui(force=True)

    def push_event(
        self,
        event: Dict[str, Any],
        last_event: str,
        silent: bool = False,
        defer_snapshot: bool = False,
    ) -> bool:
        event_payload = dict(event or {})
        if str(event_payload.get("type") or "").strip().upper() == "PACK":
            self._apply_mixing_finished_sack_quantity(event_payload)
            last_event = replace_pack_terms(last_event)
        return super().push_event(
            event_payload,
            last_event,
            silent=silent,
            defer_snapshot=defer_snapshot,
        )

    def on_scanned(self, raw: str):
        raw_s = self._normalize_mixing_machine_scan(raw)
        if self._handle_mixing_finish_confirmation(raw_s):
            return
        result = production_client.parse_scan(raw_s)
        handled_by_multi_job = False
        opened_new_job = False

        if result is not None and result.kind in ("JOB", "JOB_STUB"):
            candidates: List[Any] = [raw_s, result.value]
            if isinstance(result.meta, dict):
                candidates.extend(
                    [
                        result.meta.get("po_number"),
                        result.meta.get("job_code"),
                        result.meta.get("job_name"),
                    ]
                )
            existing_key = self._find_open_mixing_job(candidates)
            if existing_key:
                handled_by_multi_job = self._switch_mixing_session(
                    existing_key,
                    reason="job QR selected",
                )
            elif self.state.machine_code and self.state.job_code:
                self._capture_current_mixing_session()
                self._prepare_empty_mixing_session()
                opened_new_job = True

        block_part_scan = False
        if not handled_by_multi_job:
            if result is not None and result.kind in ("PACK", "RAW_MATERIAL"):
                block_part_scan = (
                    self._route_product_part_to_open_job(raw_s, result)
                    == _MIXING_SCAN_JOB_FIRST
                )
            if not block_part_scan:
                super().on_scanned(raw_s)

        self._sync_mixing_material_history_from_server()
        # A JOB QR that is not already open starts a fresh running session.
        # This explicitly permits a previously finished/closed job to reopen;
        # background autosaves still cannot resurrect closed jobs by accident.
        active_key = self._capture_current_mixing_session(
            allow_reopen_closed=opened_new_job
        )
        if opened_new_job and active_key:
            self.sync_session_snapshot_to_server(
                "SESSION SNAPSHOT SYNC (NEW MIXING ACTIVE JOB)"
            )
            job_label = str(self.state.job_name or self.state.job_code or active_key)
            operator_hint = " Scan the operator badge." if not self.state.operator_id else ""
            self.status.setText(
                f"New mixing session started: {job_label}.{operator_hint}"
            )
            self._show_info_overlay(
                "NEW MIXING SESSION",
                f"Started: {job_label}\n"
                "The previous mixing job remains open.\n"
                "Open mixing sessions: "
                f"{sum(1 for row in self._mixing_sessions.values() if bool(row.get('mixing_open', True)))}",
                hide_ms=3000,
            )
        # The production dashboard batches normal UI refreshes.  In Mixing Mode
        # operators need to see the machine/job/operator and scanned quantities
        # from this QR before they scan the next one, so render the updated state
        # synchronously at the end of every scan.
        self._refresh_ui(force=True)
        self._refresh_mixing_jobs_panel()
        for widget_name in (
            "lblMachine",
            "lblJob",
            "lblOperator",
            "lblPack",
            "lblGood",
            "lblTotalGood",
            "rightRawSacks",
            "rightRawField",
            "rightRawTotalScans",
            "resolveOldCycle",
            "resolveNewCycle",
            "status",
            "banner",
        ):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.repaint()
        app = production_client.QApplication.instance()
        if app is not None:
            # Deliver posted paint/layout events now so the operator sees this
            # scan before the scanner can submit another one.
            app.sendPostedEvents()
            app.processEvents()

    def _pack_raw_consumption_entries(
        self,
        qty: Any,
        job_output_qty: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Consume Part Qty/Unit multiplied by the finished quantity.

        For example, a 25 kg sack consumes 13.37 kg from a part configured as
        0.5348 kg per finished kg.  Scanned availability is never treated as a
        ratio and is never consumed in full merely because a sack was scanned.
        """
        entries = super()._pack_raw_consumption_entries(
            qty,
            job_output_qty=job_output_qty,
        )
        for entry in entries:
            per_output_unit = max(
                0.0, self._parse_number(entry.get("part_qty_per_unit"))
            )
            produced_units = max(
                0.0, self._parse_number(entry.get("produced_units"))
            )
            used_qty = produced_units * per_output_unit
            is_weight = str(entry.get("unit") or "").strip().lower() == "kg"
            entry.update(
                {
                    "part_qty_per_unit_source": "mixing_job_part_qty_per_unit",
                    "used_qty": used_qty,
                    "used_qty_kg": used_qty if is_weight else None,
                    "standard_pending_weight": False,
                    "weight_refresh_pending": False,
                    "temporary_weight": False,
                    "weight_label": "JOB PART QTY/UNIT",
                    "mixing_finished_qty_multiplier": produced_units,
                }
            )
        return entries

    def _pack_blocked_by_missing_part_availability(
        self,
        pack_qty: Any = 0,
        job_output_qty: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        entries = self._pack_raw_consumption_entries(
            pack_qty,
            job_output_qty=job_output_qty,
        )
        missing = [
            str(entry.get("name") or entry.get("sku") or "product part")
            for entry in entries
            if self._parse_number(
                entry.get("used_qty_kg")
                if entry.get("used_qty_kg") not in (None, "")
                else entry.get("used_qty")
            )
            <= 0
            and self._parse_number(entry.get("produced_units")) > 0
        ]
        if missing:
            shown = ", ".join(missing[:2])
            self._show_product_parts_missing_error(
                shown,
                message=(
                    f"SACK BLOCKED: scan {shown} before scanning the finished sack."
                ),
            )
            return shown

        # Mixing must never consume below zero, even when the normal client's
        # optional product-part restriction is disabled in Settings.
        shortages: List[str] = []
        statuses = self._current_part_availability_statuses()
        for status in statuses:
            status_keys = set(status.get("keys") or set())
            status_owner = self._normalize_job_code(
                status.get("required_from_job_code")
            )
            required_now = 0.0
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                entry_owner = self._normalize_job_code(
                    entry.get("required_from_job_code")
                )
                if status_owner and entry_owner and status_owner != entry_owner:
                    continue
                entry_keys = (
                    self._part_material_match_keys(entry)
                    | self._part_material_name_keys(entry)
                )
                if status_keys and entry_keys and not status_keys.intersection(entry_keys):
                    continue
                required_now += max(
                    0.0,
                    self._parse_number(
                        entry.get("used_qty_kg")
                        if entry.get("used_qty_kg") not in (None, "")
                        else entry.get("used_qty")
                    ),
                )
            available = float(status.get("available_qty") or 0.0)
            if required_now > 0 and available + 1e-9 < required_now:
                shortages.append(str(status.get("name") or "product part"))
        if shortages:
            shown = ", ".join(shortages[:2])
            self._show_product_parts_missing_error(
                shown,
                message=(
                    f"SACK BLOCKED: {shown} has insufficient balance. "
                    "Scan more product parts first."
                ),
            )
            return shown
        return super()._pack_blocked_by_missing_part_availability(
            pack_qty,
            job_output_qty=job_output_qty,
        )

    def _mixing_cumulative_part_totals_payload(self) -> List[Dict[str, Any]]:
        """Build the cumulative material totals sent to reviews and server."""
        carryover_by_key: Dict[str, float] = {}
        for carry in self._build_part_availability_carryover_logs():
            if not isinstance(carry, dict):
                continue
            for raw_key in (
                carry.get("material_sku"),
                carry.get("job_part_sku"),
                carry.get("material_product_id"),
            ):
                key = self._normalize_material_match_key(raw_key)
                if key:
                    carryover_by_key[key] = max(
                        0.0,
                        self._parse_number(
                            carry.get("carryover_available_qty", carry.get("qty"))
                        ),
                    )
        rows: List[Dict[str, Any]] = []
        for part in self._job_part_rows():
            if not isinstance(part, dict) or bool(part.get("_validation_exempt")):
                continue
            match_keys = (
                self._part_material_match_keys(part)
                | self._part_material_name_keys(part)
            )
            balance_qty = next(
                (carryover_by_key[key] for key in match_keys if key in carryover_by_key),
                0.0,
            )
            rows.append(
                {
                    "part_product_id": part.get("part_product_id")
                    or part.get("product_id"),
                    "sku": part.get("sku")
                    or part.get("part_sku")
                    or part.get("product_sku"),
                    "name": part.get("name")
                    or part.get("part_name")
                    or part.get("material_name"),
                    "unit": self._part_unit_kind(part),
                    "part_qty_per_unit": float(
                        self._resolve_part_qty_per_unit(part).get("value") or 0.0
                    ),
                    "request_part_qty": self._parse_number(
                        part.get("request_part_qty")
                    ),
                    "cumulative_scanned_qty": self._mixing_cumulative_scanned_part_qty(
                        part
                    ),
                    "balance_qty": balance_qty,
                    "remaining_balance_qty": balance_qty,
                }
            )
        return rows

    def _add_mixing_cumulative_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload["client_mode"] = "MIXING"
        # Mixing consumption comes from the configured Part Qty/Unit. Do not
        # publish or carry weighing-app values into shift/job reviews.
        payload["external_average_weight_grams"] = None
        payload["external_average_weight_unit"] = None
        payload["external_average_weight_received_at"] = None
        payload["external_average_weight_sent_at"] = None
        payload["external_average_weight_source"] = None
        payload["external_average_weight_sender"] = None
        payload["external_average_weight_needs_refresh"] = False
        payload["mixing_total_kg"] = int(self.state.good_total or 0)
        payload["mixing_sack_count"] = int(self.state.pack_count or 0)
        payload["mixing_kg_per_sack"] = self._mixing_kg_per_sack()
        payload["mixing_kg_counter_end"] = self._ensure_mixing_kg_counter()
        payload["mixing_sack_cycle_time_seconds"] = (
            float(self.state.live_cycle_avg_seconds)
            if self.state.live_cycle_avg_seconds is not None
            else None
        )
        payload["mixing_cumulative_part_scans"] = (
            self._mixing_cumulative_part_scan_rows()
        )
        payload["mixing_cumulative_part_totals"] = (
            self._mixing_cumulative_part_totals_payload()
        )
        return payload

    def _build_operator_shift_payload(
        self, reason: str
    ) -> Optional[Dict[str, Any]]:
        payload = super()._build_operator_shift_payload(reason)
        if isinstance(payload, dict):
            self._add_mixing_cumulative_payload(payload)
            kg_end = self._ensure_mixing_kg_counter()
            baseline_counter = self._parse_int_value(
                self.state.operator_shift_baseline_machine_counter_start
            )
            kg_start = (
                max(0, int(baseline_counter))
                if baseline_counter is not None
                else max(0, kg_end - int(self.state.good_total or 0))
            )
            kg_produced = max(0, kg_end - kg_start)
            payload.update(
                {
                    "mixing_kg_counter_start": kg_start,
                    "mixing_kg_counter_end": kg_end,
                    "mixing_kg_produced_shift": kg_produced,
                    # Keep the standard counter fields useful to older server
                    # views while giving them Mixing Mode KG semantics.
                    "machine_counter_start": kg_start,
                    "machine_counter_app_end": kg_end,
                    "machine_counter_end": kg_end,
                    "machine_counter_app_delta": kg_produced,
                    "machine_counter_difference": 0,
                }
            )
        return payload

    def _populate_finish_shift_summary(self, shift_payload: Dict[str, Any]):
        """Show a compact Mixing-only output and material-usage review."""
        super()._populate_finish_shift_summary(shift_payload)
        kg_start = max(0, int(shift_payload.get("mixing_kg_counter_start") or 0))
        kg_end = max(
            kg_start,
            int(
                shift_payload.get("mixing_kg_counter_end")
                or shift_payload.get("mixing_total_kg")
                or 0
            ),
        )
        kg_produced = max(
            0,
            int(
                shift_payload.get("mixing_kg_produced_shift")
                if shift_payload.get("mixing_kg_produced_shift") is not None
                else kg_end - kg_start
            ),
        )
        sack_cycle_seconds = shift_payload.get("mixing_sack_cycle_time_seconds")
        sack_cycle_text = (
            f"{float(sack_cycle_seconds):.2f} sec"
            if sack_cycle_seconds is not None
            else "-"
        )

        def review_table_for(attribute_name: str):
            widget = getattr(self, attribute_name, None)
            if widget is None:
                return None
            if getattr(widget, "_finish_rows_layout", None) is not None:
                return widget
            frames = widget.findChildren(production_client.QFrame)
            for frame in frames:
                if getattr(frame, "_finish_rows_layout", None) is not None:
                    return frame
            return None

        # Keep only four large output cards in the first row.
        card_labels = {
            "Machine": ("TOTAL KG PRODUCED", f"{self._mixing_qty_text(kg_produced)} kg"),
            "Job": ("KG COUNTER", f"{self._mixing_qty_text(kg_end)} kg"),
            "Operator": ("SACK CYCLE TIME", sack_cycle_text),
            "Shift Window": (
                "SACK OUTPUT",
                f"{int(shift_payload.get('pack_count') or 0)} sacks",
            ),
        }
        for card_key, value_label in getattr(self, "finishSummaryCards", {}).items():
            card = value_label.parentWidget() if value_label is not None else None
            if card_key not in card_labels:
                if card is not None:
                    card.hide()
                continue
            title, value = card_labels[card_key]
            if card is not None:
                card.show()
                card.setStyleSheet(
                    "QFrame { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #666b74,stop:1 #444952); border:1px solid #7a818c; border-radius:11px; }"
                    "QLabel[role='title'] { color:#d4e2ef; font-size:11px; font-weight:900; letter-spacing:1px; background:transparent; border:none; }"
                    "QLabel[role='value'] { color:#f8fafc; font-size:26px; font-weight:900; background:transparent; border:none; }"
                )
            value_label.setText(value)
            if card is not None:
                for label in card.findChildren(production_client.QLabel):
                    if label.property("role") == "title":
                        label.setText(title)
                        break
        self.finishSummaryOverviewSection.setStyleSheet(
            "QFrame { background:transparent; border:none; }"
        )
        self.finishSummaryOverviewSection.setMinimumHeight(96)
        self.finishSummaryOverviewSection.setMaximumHeight(104)
        self.finishSummaryOverviewSection.setSizePolicy(
            production_client.QSizePolicy.Policy.Expanding,
            production_client.QSizePolicy.Policy.Fixed,
        )

        totals = shift_payload.get("mixing_cumulative_part_totals")
        totals = totals if isinstance(totals, list) else []
        part_rows = []
        total_parts_used = 0.0
        total_parts_scanned = 0.0
        for row in totals:
            if not isinstance(row, dict):
                continue
            per_unit = max(0.0, self._parse_number(row.get("part_qty_per_unit")))
            used_qty = per_unit * float(kg_produced)
            scanned_qty = max(
                0.0, self._parse_number(row.get("cumulative_scanned_qty"))
            )
            total_parts_used += used_qty
            total_parts_scanned += scanned_qty
            unit = self._safe_text(row.get("unit"), "kg")
            part_rows.append(
                [
                    f"{self._safe_text(row.get('sku'))}\n{self._safe_text(row.get('name'))}",
                    f"{self._mixing_qty_text(scanned_qty)} {unit}",
                    f"{self._mixing_qty_text(used_qty)} {unit}",
                    f"{self._mixing_qty_text(per_unit)} {unit}",
                ]
            )
        if not part_rows:
            part_rows = [["No product parts used in this shift.", "-", "-", "-"]]

        parts_table = review_table_for("finishReviewJobDetails")
        if parts_table is not None:
            parts_table._finish_headers = ["PART", "SCANNED KG", "USED", "QTY / UNIT"]
            parts_table.setStyleSheet(
                "QFrame { background:#41464f; border:none; border-radius:10px; }"
                "QLabel[role='header'] { color:#d4e2ef; font-size:11px; font-weight:900; padding:6px; }"
                "QLabel[role='cell'] { color:#f8fafc; font-size:13px; font-weight:800; padding:8px; border-bottom:1px solid #2a3541; }"
            )
            title_label = getattr(parts_table, "_finish_title_label", None)
            if title_label is not None:
                title_label.setText(
                    "Product Parts Used"
                    f"    Used {self._mixing_qty_text(total_parts_used)} kg"
                    f"    Scanned {self._mixing_qty_text(total_parts_scanned)} kg"
                )
            self._set_finish_summary_table_rows(parts_table, part_rows)
            parts_grid = getattr(parts_table, "_finish_rows_layout", None)
            if parts_grid is not None:
                parts_grid.setColumnStretch(0, 4)
                parts_grid.setColumnStretch(1, 2)
                parts_grid.setColumnStretch(2, 2)
                parts_grid.setColumnStretch(3, 2)

        counter_table = review_table_for("finishReviewCounters")
        if counter_table is not None:
            counter_table._finish_headers = ["Mixing Output"]
            counter_table.setStyleSheet(
                "QFrame { background:#41464f; border:none; border-radius:10px; }"
                "QLabel[role='cell'] { color:#f8fafc; font-size:14px; font-weight:800; padding:10px; border-bottom:1px solid #2a3541; }"
            )
            title_label = getattr(counter_table, "_finish_title_label", None)
            if title_label is not None:
                title_label.setText("Mixing Output")
            self._set_finish_summary_table_rows(
                counter_table,
                [
                    [f"Total KG Produced: {self._mixing_qty_text(kg_produced)} kg"],
                    [f"KG Counter: {self._mixing_qty_text(kg_start)} -> {self._mixing_qty_text(kg_end)} kg"],
                    [f"Sack Cycle Time: {sack_cycle_text}"],
                    [f"Sack Output: {int(shift_payload.get('pack_count') or 0)}"],
                ],
            )

        # Mixing review needs only the output and product-parts sections.
        for table_name in ("finishReviewRejects", "finishReviewDowntime"):
            table = review_table_for(table_name)
            section = getattr(table, "_finish_section", None) if table is not None else None
            if section is not None:
                section.hide()
        for table in (parts_table, counter_table):
            section = getattr(table, "_finish_section", None) if table is not None else None
            if section is not None:
                section.show()
                section.setMinimumHeight(150)
                section.setMaximumHeight(175)
                section.setSizePolicy(
                    production_client.QSizePolicy.Policy.Expanding,
                    production_client.QSizePolicy.Policy.Fixed,
                )
                section.setStyleSheet(
                    "QFrame { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #5f646d,stop:1 #3d424a); border:1px solid #787f89; border-radius:11px; }"
                    "QLabel { color:#f8fafc; font-size:16px; font-weight:900; background:transparent; border:none; }"
                )
        parts_section = (
            getattr(parts_table, "_finish_section", None)
            if parts_table is not None
            else None
        )
        details_grid = (
            parts_section.parentWidget().layout()
            if parts_section is not None and parts_section.parentWidget() is not None
            else None
        )
        if isinstance(details_grid, production_client.QGridLayout):
            details_grid.setColumnStretch(0, 7)
            details_grid.setColumnStretch(1, 4)
            details_grid.setRowStretch(0, 0)
            details_grid.setRowStretch(1, 0)
        self._clear_finish_review_extra_pages()
        self._rebuild_finish_review_pages(
            include_second_page=False,
            include_third_page=False,
            include_fourth_page=False,
        )

    def _state_to_active_snapshot(self) -> Dict[str, Any]:
        snapshot = super()._state_to_active_snapshot()
        snapshot = self._add_mixing_cumulative_payload(snapshot)
        current_key = self._mixing_job_key(
            snapshot.get("job_code") or snapshot.get("job_name")
        )
        open_jobs: List[Dict[str, Any]] = []
        source_rows = dict(self._mixing_sessions)
        if current_key:
            source_rows[current_key] = snapshot
        for key, saved in sorted(
            source_rows.items(),
            key=lambda item: float(item[1].get("mixing_last_active_at") or 0.0),
            reverse=True,
        ):
            if (
                not isinstance(saved, dict)
                or not self._mixing_session_is_for_current_machine(saved)
                or not bool(saved.get("mixing_open", True))
            ):
                continue
            row = dict(saved)
            # Never nest the registry inside its own job snapshots.
            row.pop("mixing_open_jobs", None)
            row["mixing_job_key"] = key
            row["mixing_active"] = key == current_key
            open_jobs.append(row)
        snapshot["mixing_open_jobs"] = open_jobs
        return snapshot

    def _save_active_session_snapshot(self, force: bool = False):
        """Autosave both the selected session and Mixing Mode's job registry."""
        self._capture_current_mixing_session()
        return super()._save_active_session_snapshot(force=force)

    def _clear_shift_session_keep_machine(self, *, preserve_carryover: bool = True):
        """Remove the closed shift from OPEN jobs and activate the next job."""
        closing_key = self._mixing_job_key(self.state.job_code or self.state.job_name)
        finished_kg_counter = self._ensure_mixing_kg_counter()
        finished_sack_cycle = self._parse_number(self.state.live_cycle_avg_seconds)
        remaining_part_logs = self._build_part_availability_carryover_logs()
        next_key = ""
        if closing_key:
            candidates = sorted(
                (
                    (key, snapshot)
                    for key, snapshot in self._mixing_sessions.items()
                    if key != closing_key
                    and self._mixing_session_is_for_current_machine(snapshot)
                    and bool(snapshot.get("mixing_open", True))
                ),
                key=lambda item: float(item[1].get("mixing_last_active_at") or 0.0),
                reverse=True,
            )
            if candidates:
                next_key = candidates[0][0]

            if preserve_carryover:
                # Keep the job's cumulative KG/material state available when
                # its JOB QR is scanned for the next operator, but it is no
                # longer a currently running/open job after Finish Shift.
                saved = self._mixing_sessions.get(closing_key)
                if isinstance(saved, dict):
                    saved["mixing_open"] = False
                    saved["mixing_shift_closed_at"] = time.time()
                    saved["operator_id"] = None
                    saved["operator_qr_payload"] = ""
                    saved["operator_shift_started_at"] = None
                    saved["crew_members"] = []
                    saved["manpower_count"] = 0
                    # A completed shift is archived on the server. The local
                    # resumable job retains only job identity and carryovers.
                    saved["pack_count"] = 0
                    saved["good_total"] = 0
                    saved["butal_total"] = 0
                    saved["reject_total"] = 0
                    saved["reject_breakdown"] = {}
                    saved["startup_reject_total"] = 0
                    saved["no_shot_total"] = 0
                    saved["raw_sacks_count"] = 0
                    saved["raw_material_logs"] = [
                        dict(row) for row in remaining_part_logs
                    ]
                    saved["raw_material_scans"] = [
                        str(row.get("material_name") or row.get("material") or "")
                        for row in remaining_part_logs
                    ]
                    for field in (
                        "product_pack_history_logs",
                        "butal_scan_logs",
                        "reject_review_logs",
                        "production_adjustment_logs",
                        "action_logs",
                        "pdr_reason_segments",
                        "pdr_downtime_logs",
                        "operator_shift_logs",
                    ):
                        saved[field] = []
                    saved["machine_counter_current"] = finished_kg_counter
                    saved["machine_counter_shift_start"] = finished_kg_counter
                    saved["machine_counter_shift_end"] = None
                    saved["operator_shift_baseline_machine_counter_start"] = (
                        finished_kg_counter
                    )
                    saved["mixing_kg_counter_end"] = finished_kg_counter
                    saved["mixing_total_kg"] = 0
                    saved["mixing_sack_count"] = 0
                    saved["live_cycle_last_scan_at"] = None
                    saved["live_cycle_total_seconds"] = 0.0
                    saved["live_cycle_intervals"] = 0
                    saved["live_cycle_total_units"] = 0
                    saved["live_cycle_avg_seconds"] = None
                    if finished_sack_cycle > 0:
                        cycle_text = f"{finished_sack_cycle:.2f}".rstrip("0").rstrip(".")
                        saved["cycle_time_current"] = cycle_text
                        saved["cycle_time_temporary"] = cycle_text
                        saved["mixing_previous_sack_cycle_time_seconds"] = (
                            finished_sack_cycle
                        )
            else:
                # Finish Job permanently removes the completed session.
                self._mixing_sessions.pop(closing_key, None)
            if self._mixing_active_job_key == closing_key:
                self._mixing_active_job_key = ""
            self._persist_mixing_sessions()

        super()._clear_shift_session_keep_machine(preserve_carryover=preserve_carryover)
        if next_key and next_key in self._mixing_sessions:
            if self._switch_mixing_session(
                next_key,
                reason=(
                    "previous mixing shift finished"
                    if preserve_carryover
                    else "previous mixing job finished"
                ),
            ):
                self.status.setText(
                    "Finished mixing shift removed from open jobs. "
                    "The next running job is now active."
                    if preserve_carryover
                    else "Finished mixing job cleared. The next open job is now active."
                )
                return
        self._refresh_mixing_jobs_panel()

    def _build_finished_job_payload(self) -> Dict[str, Any]:
        payload = super()._build_finished_job_payload()
        self._add_mixing_cumulative_payload(payload)
        kg_end = self._ensure_mixing_kg_counter()
        payload.update(
            {
                "mixing_kg_counter_start": 0,
                "mixing_kg_counter_end": kg_end,
                "mixing_kg_produced_shift": kg_end,
                "machine_counter_start": 0,
                "machine_counter_app_end": kg_end,
                "machine_counter_end": kg_end,
                "machine_counter_app_delta": kg_end,
                "machine_counter_difference": 0,
            }
        )
        return payload


def main() -> None:
    app = production_client.QApplication(sys.argv)
    window = MixingClientUI()
    window.setWindowState(production_client.Qt.WindowState.WindowFullScreen)
    window.showFullScreen()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
