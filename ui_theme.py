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
    font-size: 12px;
    color: #475569;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.7px;
}
QLabel#StatValue {
    font-family: "Segoe UI Variable Display", "Bahnschrift", "Inter";
    font-size: 50px;
    font-weight: 800;
    color: #0f172a;
}

/* Pack / Butal / Reject with stronger identity */
QFrame#StatPack {
    background: #eff6ff;
    border: 1px solid #93c5fd;
}
QFrame#StatButal {
    background: #ecfdf5;
    border: 1px solid #86efac;
}
QFrame#StatReject {
    background: #fef2f2;
    border: 1px solid #fca5a5;
}
QFrame#StatGood {
    background: #ecfeff;
    border: 1px solid #67e8f9;
}
QFrame#StatTotalGood {
    background: #ede9fe;
    border: 1px solid #c4b5fd;
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
