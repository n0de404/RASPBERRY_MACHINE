APP_STYLESHEET = """
/* ===== Base ===== */
QWidget {
    background: #f3f7ff;
    color: #0f172a;
    font-family: "Segoe UI Variable Display", "Bahnschrift", "Inter", "Segoe UI";
    font-size: 14px;
}
QLabel {
    background: transparent;
}

/* ===== Generic cards/panels ===== */
QFrame#Panel {
    background: #ffffff;
    border: 1px solid #dbe4f0;
    border-radius: 20px;
}

/* Optional: use this objectName for inner sub-panels */
QFrame#SubPanel {
    background: #f8fbff;
    border: 1px solid #e3eaf5;
    border-radius: 16px;
}

/* ===== Titles ===== */
QLabel#PageTitle {
    font-size: 30px;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: 0.4px;
}
QLabel#SectionTitle,
QLabel#RightTitle {
    font-size: 17px;
    font-weight: 750;
    color: #0f172a;
}
QLabel#RightHint {
    color: #6b7280;
    font-size: 12px;
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
                                stop:0 #2563eb, stop:1 #1e40af);
    color: #ffffff;
    border: 1px solid #1d4ed8;
    border-radius: 16px;
    padding: 14px 16px;
    font-size: 18px;
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
    color: #0369a1;
    font-size: 14px;
    font-weight: 800;
    background: #e0f2fe;
    border: 1px solid #7dd3fc;
    border-radius: 14px;
    padding: 8px 12px;
}

/* ===== Meta fields (Machine/Job/Operator) ===== */
QLabel#MetaLabel {
    color: #64748b;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}
QLabel#MetaValue {
    color: #0f172a;
    font-size: 15px;
    font-weight: 700;
    background: #ffffff;
    border: 1px solid #dbe4f0;
    border-radius: 14px;
    padding: 10px 12px;
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
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.7px;
}
QLabel#StatValue {
    font-family: "Segoe UI Variable Display", "Bahnschrift", "Inter";
    font-size: 50px;
    font-weight: 800;
    color: #22d3ee;
}
QFrame#StatPack QLabel#StatValue {
    color: #38bdf8;
}
QFrame#StatGood QLabel#StatValue {
    color: #22d3ee;
}
QFrame#StatButal QLabel#StatValue {
    color: #34d399;
}
QFrame#StatReject QLabel#StatValue {
    color: #fb7185;
}
QFrame#StatTotalGood QLabel#StatValue {
    color: #a78bfa;
}

/* Pack / Butal / Reject with stronger identity */
QFrame#StatPack {
    background: #0c4a6e;
    border: 1px solid #38bdf8;
}
QFrame#StatButal {
    background: #14532d;
    border: 1px solid #34d399;
}
QFrame#StatReject {
    background: #7f1d1d;
    border: 1px solid #fb7185;
}
QFrame#StatGood {
    background: #164e63;
    border: 1px solid #22d3ee;
}
QFrame#StatTotalGood {
    background: #4c1d95;
    border: 1px solid #a78bfa;
}

/* short pulse state toggled from client.py */
QFrame#StatPack[flash="1"] {
    border: 2px solid #2563eb;
    background: #dbeafe;
}
QFrame#StatGood[flash="1"] {
    border: 2px solid #0891b2;
    background: #cffafe;
}
QFrame#StatButal[flash="1"] {
    border: 2px solid #16a34a;
    background: #dcfce7;
}
QFrame#StatReject[flash="1"] {
    border: 2px solid #dc2626;
    background: #fee2e2;
}
QFrame#StatTotalGood[flash="1"] {
    border: 2px solid #7c3aed;
    background: #ddd6fe;
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
"""
