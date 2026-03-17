APP_STYLESHEET = """
/* ===== Base ===== */
QWidget {
    background: #ffffff;
    color: #0f172a;
    font-family: "Segoe UI Variable Display", "Bahnschrift", "Inter", "Segoe UI";
    font-size: 14px;
}
QLabel {
    background: transparent;
}

/* ===== Generic cards/panels ===== */
QFrame#Panel {
    background: qradialgradient(cx:0.5, cy:0.34, radius:1.2, fx:0.5, fy:0.16,
                                stop:0 rgba(120,124,134,232),
                                stop:0.38 rgba(72,76,84,238),
                                stop:1 rgba(24,26,31,248));
    border: 1px solid #5b6069;
    border-radius: 24px;
}

QFrame#RightPanel {
    background: transparent;
    border: none;
    border-radius: 20px;
}

/* Optional: use this objectName for inner sub-panels */
QFrame#SubPanel {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 rgba(100,104,112,220),
                                stop:1 rgba(54,57,63,230));
    border: 1px solid #737882;
    border-radius: 16px;
}

QFrame#RightCardOuter {
    background: transparent;
    border: none;
    border-radius: 20px;
}
QFrame#RightCardInner {
    background: qradialgradient(cx:0.5, cy:0.34, radius:1.15, fx:0.5, fy:0.16,
                                stop:0 rgba(120,124,134,232),
                                stop:0.38 rgba(72,76,84,238),
                                stop:1 rgba(24,26,31,248));
    border: 1px solid #5d626c;
    border-radius: 22px;
}
QFrame#LeftCardOuter {
    background: transparent;
    border: none;
    border-radius: 20px;
}
QFrame#LeftCardInner {
    background: qradialgradient(cx:0.5, cy:0.34, radius:1.15, fx:0.5, fy:0.16,
                                stop:0 rgba(120,124,134,232),
                                stop:0.38 rgba(72,76,84,238),
                                stop:1 rgba(24,26,31,248));
    border: 1px solid #5d626c;
    border-radius: 22px;
}

/* ===== Titles ===== */
QLabel#PageTitle {
    font-size: 24px;
    font-weight: 800;
    color: #f8fafc;
    letter-spacing: 0.4px;
    padding-top: 2px;
    background: transparent;
}
QFrame#HeaderCard {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 rgba(97,102,111,228),
                                stop:0.5 rgba(68,72,79,232),
                                stop:1 rgba(43,46,52,236));
    border: 1px solid rgba(148, 163, 184, 0.42);
    border-radius: 0px;
}
QLabel#HeaderMetaValue {
    color: #f8fafc;
    font-size: 15px;
    font-weight: 800;
    background: transparent;
    border: none;
    border-radius: 0px;
    padding: 0px 2px;
}
QPushButton#HeaderSettingsButton {
    background: transparent;
    color: #f8fafc;
    border: none;
    border-radius: 12px;
    font-size: 22px;
    font-weight: 800;
    padding: 0px;
}
QPushButton#HeaderSettingsButton:hover {
    background: rgba(255,255,255,0.10);
    border: none;
}
QLabel#SectionTitle,
QLabel#RightTitle {
    font-size: 17px;
    font-weight: 750;
    color: #edf0f4;
}
QLabel#RightHint {
    color: #c5cad2;
    font-size: 12px;
}
QLabel#RightMonitorValue,
QLabel#RightMonitorValueAccent {
    color: #edf0f4;
    font-size: 15px;
    font-weight: 800;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 rgba(98,102,110,220),
                                stop:1 rgba(50,53,60,228));
    border: 1px solid #767b84;
    border-radius: 14px;
    padding: 8px 16px;
}
QLabel#RightMonitorValueAccent {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 rgba(128,132,141,228),
                                stop:0.42 rgba(108,112,121,228),
                                stop:1 rgba(60,63,70,236));
    border: 1px solid #858992;
}
QLabel#ProductionLiveReason {
    color: #0f172a;
    font-size: 16px;
    font-weight: 800;
    background: transparent;
    border: none;
    border-radius: 10px;
    padding: 4px 2px;
}
QLabel#ProductionCounter7 {
    color: #38bdf8;
    background: #2f343f;
    border: none;
    border-radius: 12px;
    padding: 10px 12px;
    font-family: "Consolas", "Lucida Console", "Courier New", monospace;
    font-size: 58px;
    font-weight: 900;
    letter-spacing: 4px;
}
QLabel#ProductionFixAnim {
    color: #0f172a;
    font-size: 20px;
    font-weight: 900;
    background: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 8px 12px;
}
QLabel#ProductionMarqueeText {
    color: #334155;
    font-size: 14px;
    font-weight: 700;
    background: transparent;
}
QFrame#ProductionOverlay {
    background: qradialgradient(cx:0.5, cy:0.45, radius:0.9,
                                fx:0.5, fy:0.45,
                                stop:0 rgba(255,255,255,0.99),
                                stop:0.58 rgba(248,250,252,0.98),
                                stop:1 rgba(226,232,240,0.98));
    border: 2px solid #fb923c;
    border-radius: 14px;
}
QFrame#ProductionOverlay[pulse="1"] {
    border: 2px solid #f97316;
}

/* ===== Top banner (scan instruction) ===== */
QLabel#Banner {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #2f6aea, stop:1 #2454c6);
    color: #ffffff;
    border: 1px solid #1d4ed8;
    border-radius: 16px;
    padding: 10px 14px;
    font-size: 20px;
    font-weight: 800;
    letter-spacing: 0.2px;
}

/* Scanner error / info strip */
QLabel#ScannerInfo {
    background: #fff7ed;
    color: #9a3412;
    border: 1px solid #fdba74;
    border-radius: 12px;
    padding: 8px 10px;
    font-size: 12px;
}

/* ===== Status pill at bottom / right ===== */
QLabel#StatusBar {
    background: #ecfeff;
    color: #0f766e;
    border: 1px solid #99f6e4;
    border-radius: 14px;
    padding: 9px 12px;
    font-size: 14px;
    font-weight: 700;
}

/* Machine state badge */
QLabel#MachineAnim {
    color: #fff7ed;
    font-size: 14px;
    font-weight: 800;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 rgba(251,146,60,245),
                                stop:1 rgba(234,88,12,248));
    border: 1px solid #fb923c;
    border-radius: 16px;
    padding: 8px 12px;
}
QLabel#MachineAnim[mode="active"][pulse="1"] {
    background: #16ff6f;
    border: 1px solid #22c55e;
    color: #052e16;
}
QLabel#MachineAnim[mode="active"][pulse="0"] {
    background: #b9fbcf;
    border: 1px solid #4ade80;
    color: #14532d;
}
QLabel#MachineAnim[mode="idle"][pulse="1"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 rgba(251,146,60,245),
                                stop:1 rgba(234,88,12,248));
    border: 1px solid #f97316;
    color: #fff7ed;
}
QLabel#MachineAnim[mode="idle"][pulse="0"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 rgba(251,146,60,245),
                                stop:1 rgba(234,88,12,248));
    border: 1px solid #fb923c;
    color: #fff7ed;
}

/* ===== Meta fields (Machine/Job/Operator) ===== */
QLabel#MetaLabel {
    color: #c7ccd4;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}
QLabel#MetaValue {
    color: #edf0f4;
    font-size: 15px;
    font-weight: 700;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 rgba(101,105,113,220),
                                stop:1 rgba(53,56,62,228));
    border: 1px solid #777c86;
    border-radius: 14px;
    padding: 10px 12px;
}
QLabel#RejectDetailItem {
    color: #6b7280;
    font-size: 13px;
    font-weight: 800;
    background: #f3f4f6;
    border: 1px solid #e5e7eb;
    border-left: 5px solid #9ca3af;
    border-radius: 12px;
    padding: 8px 10px;
}
QLabel#RejectDetailItem[active="1"] {
    color: #991b1b;
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-left: 5px solid #dc2626;
}
QLabel#RejectDetailItem[active="1"][flash="1"] {
    border-left: 5px solid #f52727;
}

/* ===== KPI Stat Cards ===== */
QFrame[role="stat"] {
    border-radius: 18px;
    border: 1px solid #dbe4f0;
    padding: 10px;
}
QLabel#StatTitle {
    font-size: 16px;
    color: #e2e8f0;
    font-weight: 900;
    text-transform: uppercase;
    letter-spacing: 0.7px;
}
QLabel#StatValue {
    font-family: "Segoe UI Variable Display", "Bahnschrift", "Inter";
    font-size: 46px;
    font-weight: 900;
    color: #22d3ee;
}
QFrame#StatPack QLabel#StatValue {
    color: #86efac;
}
QFrame#StatGood QLabel#StatValue {
    color: #86efac;
}
QFrame#StatButal QLabel#StatValue {
    color: #86efac;
}
QFrame#StatReject QLabel#StatValue {
    color: #fecdd3;
}
QFrame#StatTotalGood QLabel#StatValue {
    color: #bbf7d0;
}

/* Pack / Butal / Reject with stronger identity */
QFrame#StatPack {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #1f7a3d,
                                stop:0.48 #166534,
                                stop:1 #14532d);
    border: 1px solid #22c55e;
    border-top: 2px solid #4ade80;
    border-left: 2px solid #4ade80;
    border-right: 2px solid #14532d;
    border-bottom: 2px solid #14532d;
    border-radius: 18px;
}
QFrame#StatButal {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #1f7a3d,
                                stop:0.48 #166534,
                                stop:1 #14532d);
    border: 1px solid #22c55e;
    border-top: 2px solid #4ade80;
    border-left: 2px solid #4ade80;
    border-right: 2px solid #14532d;
    border-bottom: 2px solid #14532d;
}
QFrame#StatReject {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #b91c1c,
                                stop:0.48 #991b1b,
                                stop:1 #7f1d1d);
    border: 1px solid #ef4444;
    border-top: 2px solid #f87171;
    border-left: 2px solid #f87171;
    border-right: 2px solid #7f1d1d;
    border-bottom: 2px solid #7f1d1d;
}
QFrame#StatGood {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #1f7a3d,
                                stop:0.48 #166534,
                                stop:1 #14532d);
    border: 1px solid #22c55e;
    border-top: 2px solid #4ade80;
    border-left: 2px solid #4ade80;
    border-right: 2px solid #14532d;
    border-bottom: 2px solid #14532d;
}
QFrame#StatTotalGood {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #2a8a49,
                                stop:0.5 #1b6d3a,
                                stop:1 #165c32);
    border: 1px solid #4ade80;
    border-top: 2px solid #86efac;
    border-left: 2px solid #86efac;
    border-right: 2px solid #165c32;
    border-bottom: 2px solid #165c32;
}

/* short pulse state toggled from client.py */
QFrame#StatPack[flash="1"] {
    border: 2px solid #22c55e;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #34d399,
                                stop:1 #15803d);
}
QFrame#StatGood[flash="1"] {
    border: 2px solid #22c55e;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #34d399,
                                stop:1 #15803d);
}
QFrame#StatButal[flash="1"] {
    border: 2px solid #22c55e;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #34d399,
                                stop:1 #15803d);
}
QFrame#StatReject[flash="1"] {
    border: 2px solid #ef4444;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #f87171,
                                stop:1 #b91c1c);
}
QFrame#StatTotalGood[flash="1"] {
    border: 2px solid #4ade80;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #6ee7b7,
                                stop:1 #16a34a);
}

/* Optional accent bar (if you add a child frame inside each stat) */
QFrame#accentPack { background: #3b82f6; border-radius: 6px; }
QFrame#accentButal { background: #10b981; border-radius: 6px; }
QFrame#accentReject { background: #ef4444; border-radius: 6px; }

/* ===== Text areas / logs ===== */
QPlainTextEdit, QTextEdit, QListWidget {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 10px;
    color: #0f172a;
}
QPlainTextEdit:focus, QTextEdit:focus, QListWidget:focus {
    border: 1px solid #60a5fa;
}

/* ===== Inputs ===== */
QLineEdit, QComboBox, QSpinBox {
    background: #ffffff;
    border: 1px solid #dbe4f0;
    border-radius: 14px;
    padding: 8px 10px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #60a5fa;
}

/* ===== Buttons ===== */
QPushButton {
    background: #1d4ed8;
    color: #ffffff;
    border: 1px solid #1e40af;
    border-radius: 14px;
    padding: 8px 12px;
    font-weight: 700;
}
QPushButton:hover { background: #1e40af; }
QPushButton:pressed { background: #1e40af; }
QPushButton:disabled {
    background: #cbd5e1;
    border: 1px solid #cbd5e1;
    color: #64748b;
}

QPushButton#SettingsButton {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #dbe4f0;
    border-radius: 12px;
    font-size: 22px;
    font-weight: 800;
    padding: 0px;
}
QPushButton#SettingsButton:hover {
    background: #eff6ff;
    border: 1px solid #93c5fd;
}

QCheckBox {
    color: #0f172a;
    font-size: 14px;
    font-weight: 700;
    spacing: 8px;
}

QFrame#SettingsOverlay {
    background: #f2f3f5;
    border: 1px solid #d6d7dc;
    border-radius: 18px;
}
QFrame#SettingsShell {
    background: #f3f4f6;
    border: none;
    border-radius: 18px;
}
QFrame#SettingsNav {
    min-width: 150px;
    max-width: 170px;
    background: #e7e7ea;
    border-right: 1px solid #dcdee3;
    border-top-left-radius: 18px;
    border-bottom-left-radius: 18px;
}
QLabel#SettingsNavTitle {
    color: #50545c;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 0.4px;
    text-transform: uppercase;
    padding: 6px 8px 10px 8px;
}
QPushButton#SettingsNavButton {
    background: transparent;
    color: #474b53;
    border: 1px solid transparent;
    border-radius: 9px;
    text-align: left;
    padding: 9px 12px;
    font-size: 15px;
    font-weight: 600;
}
QPushButton#SettingsNavButton:hover {
    background: #f4f4f6;
    border: 1px solid #dddee3;
}
QPushButton#SettingsNavButton:checked {
    background: #ffffff;
    color: #2e3137;
    border: 1px solid #d8dae0;
}
QFrame#SettingsContent {
    background: #ffffff;
    border-top-right-radius: 18px;
    border-bottom-right-radius: 18px;
}
QWidget#SettingsPage {
    background: #ffffff;
}
QLabel#SettingsContentTitle {
    color: #2f333a;
    font-size: 18px;
    font-weight: 700;
}
QLabel#SettingsFieldLabel {
    color: #3d434d;
    font-size: 13px;
    font-weight: 700;
    padding-top: 4px;
}
QFrame#SettingsContentDivider {
    background: #e7e8ec;
    min-height: 1px;
    max-height: 1px;
    border: none;
}
QPushButton#SettingsCloseX {
    background: #eff0f2;
    color: #7b8089;
    border: 1px solid #d8dbe1;
    border-radius: 10px;
    min-width: 38px;
    max-width: 38px;
    min-height: 38px;
    max-height: 38px;
    font-size: 20px;
    font-weight: 500;
    padding: 0px;
}
QPushButton#SettingsCloseX:hover {
    background: #e7e8eb;
    color: #565b64;
}
QPushButton#SettingToggle {
    background: #ffffff;
    color: #3a3e45;
    border: 1px solid #d9dde4;
    border-radius: 10px;
    text-align: left;
    padding: 8px 11px;
    font-size: 13px;
    font-weight: 700;
}
QPushButton#SettingToggle:checked {
    background: #e4e6ea;
    color: #2f3339;
    border: 1px solid #ccd0d7;
}
QFrame#SettingsSegmentWrap {
    background: #f4f4f6;
    border: 1px solid #d7dbe2;
    border-radius: 10px;
    max-width: 370px;
}
QPushButton#SettingsSegmentBtn {
    background: transparent;
    border: none;
    border-radius: 10px;
    color: #646b75;
    min-height: 32px;
    font-size: 14px;
    font-weight: 600;
}
QPushButton#SettingsSegmentBtn:checked {
    background: #dbdde2;
    color: #4a5059;
    border: 1px solid #d1d3da;
}
QWidget#SettingsSwitchRow {
    border-top: 1px solid #e7e8ec;
    padding-top: 10px;
}
QLabel#SettingsSwitchLabel {
    color: #454b55;
    font-size: 16px;
    font-weight: 600;
}
QPushButton#SettingsSwitch {
    min-width: 46px;
    max-width: 46px;
    min-height: 26px;
    max-height: 26px;
    border-radius: 13px;
    background: #e4e5e9;
    border: 1px solid #d3d6dd;
    color: transparent;
}
QPushButton#SettingsSwitch:checked {
    background: #6ea4ee;
    border: 1px solid #5e92d8;
}
QComboBox {
    background: #ffffff;
    border: 1px solid #d9dde4;
    border-radius: 10px;
    padding: 8px 10px;
    color: #3c4047;
    min-width: 140px;
    max-width: 180px;
}
QComboBox:focus {
    border: 1px solid #c8cdd6;
}
"""
