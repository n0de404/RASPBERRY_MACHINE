APP_STYLESHEET = """
/* ===== Base ===== */
QWidget {
    background: #f1f5f9;                  /* add overall canvas */
    color: #0f172a;
    font-family: "Segoe UI", "Inter", "Verdana";
    font-size: 13px;
}
QLabel {
    background: transparent;
}

/* ===== Generic cards/panels ===== */
QFrame#Panel {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
}

/* Optional: use this objectName for inner sub-panels */
QFrame#SubPanel {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
}

/* ===== Titles ===== */
QLabel#PageTitle {
    font-size: 22px;
    font-weight: 800;
    color: #0f172a;
}
QLabel#SectionTitle,
QLabel#RightTitle {
    font-size: 15px;
    font-weight: 800;
    color: #0f172a;
}
QLabel#RightHint {
    color: #64748b;
    font-size: 12px;
}

/* ===== Top banner (scan instruction) ===== */
QLabel#Banner {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #2563eb, stop:1 #1d4ed8);
    color: #ffffff;
    border: 1px solid #1e40af;
    border-radius: 14px;
    padding: 12px 14px;
    font-size: 16px;
    font-weight: 800;
    letter-spacing: 0.3px;
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
    border-radius: 12px;
    padding: 8px 12px;
    font-weight: 700;
}

/* Machine state badge */
QLabel#MachineAnim {
    color: #0f766e;
    font-size: 14px;
    font-weight: 800;
    background: #ecfeff;
    border: 1px solid #99f6e4;
    border-radius: 12px;
    padding: 8px 12px;
}

/* ===== Meta fields (Machine/Job/Operator) ===== */
QLabel#MetaLabel {
    color: #64748b;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}
QLabel#MetaValue {
    color: #0f172a;
    font-size: 14px;
    font-weight: 700;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 10px 12px;
}

/* ===== KPI Stat Cards ===== */
QFrame[role="stat"] {
    border-radius: 16px;
    border: 1px solid #e2e8f0;
    padding: 10px;
}
QLabel#StatTitle {
    font-size: 11px;
    color: #475569;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}
QLabel#StatValue {
    font-family: "Segoe UI", "Inter";
    font-size: 42px;                       /* bigger = more KPI */
    font-weight: 900;
    color: #0f172a;
}

/* Pack / Butal / Reject with stronger identity */
QFrame#StatPack {
    background: #eff6ff;
    border: 1px solid #bfdbfe;
}
QFrame#StatButal {
    background: #ecfdf5;
    border: 1px solid #bbf7d0;
}
QFrame#StatReject {
    background: #fef2f2;
    border: 1px solid #fecaca;
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
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 8px 10px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #60a5fa;
}

/* ===== Buttons ===== */
QPushButton {
    background: #2563eb;
    color: #ffffff;
    border: 1px solid #1d4ed8;
    border-radius: 12px;
    padding: 8px 12px;
    font-weight: 800;
}
QPushButton:hover { background: #1d4ed8; }
QPushButton:pressed { background: #1e40af; }
QPushButton:disabled {
    background: #cbd5e1;
    border: 1px solid #cbd5e1;
    color: #64748b;
}
"""
