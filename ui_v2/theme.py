from __future__ import annotations

BG_MAIN = "#0b1220"
BG_SIDEBAR = "#0f1a2b"
BORDER = "#1a2a41"

TEXT = "#e8f0ff"
TEXT_MID = "#cfe0ff"
TEXT_MUTED = "#9fb0c6"

ACCENT = {
    "green":  "#34d399",
    "blue":   "#60a5fa",
    "orange": "#fb923c",
    "red":    "#f87171",
    "purple": "#a78bfa",
}

def _qss_base() -> str:
    return f"""
    QMainWindow {{
        background: {BG_MAIN};
    }}

    /* ---- Sidebar ---- */
    #Sidebar {{
        background: {BG_SIDEBAR};
        border: 1px solid #1c2a3f;
        border-radius: 18px;
    }}

    #AppTitle {{
        color: {TEXT};
        font-size: 18px;
        font-weight: 800;
    }}

    #PageTitle {{
        color: {TEXT};
        font-size: 20px;
        font-weight: 800;
    }}

    #NavBtn {{
        background: #12223a;
        color: #cbd5e1;
        border: none;
        border-radius: 12px;
        padding: 10px 12px;
        text-align: left;
        font-size: 13px;
    }}

    #NavBtn[active="1"] {{
        background: rgba(96,165,250,0.15);
        color: #ffffff;
        border-left: 3px solid #60a5fa;
    }}

    #NavBtn:hover {{
        background: #162b46;
    }}

    QPushButton#ActionButton {{
        color: rgba(248,251,255,0.96);
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.14);
        border-radius: 10px;
        padding: 6px 12px;
        font-size: 12px;
        font-weight: 700;
    }}

    QPushButton#ActionButton:hover {{
        background: rgba(255,255,255,0.12);
        border: 1px solid rgba(255,255,255,0.20);
    }}

    QPushButton#ActionButton:pressed {{
        background: rgba(255,255,255,0.06);
    }}

    QPushButton#ActionButton:disabled {{
        color: rgba(232,240,255,0.46);
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
    }}

    QComboBox#ActionSelect {{
        color: rgba(248,251,255,0.96);
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.14);
        border-radius: 10px;
        padding: 6px 34px 6px 12px;
        font-size: 12px;
        font-weight: 700;
    }}

    QComboBox#ActionSelect:hover {{
        background: rgba(255,255,255,0.12);
        border: 1px solid rgba(255,255,255,0.20);
    }}

    QComboBox#ActionSelect::drop-down {{
        border: none;
        width: 24px;
    }}

    QComboBox#ActionSelect QAbstractItemView {{
        background: rgba(10,14,22,0.98);
        color: #e8f0ff;
        border: 1px solid rgba(255,255,255,0.16);
        selection-background-color: rgba(96,165,250,0.22);
        padding: 4px;
    }}

    QLineEdit#ActionInput {{
        color: rgba(248,251,255,0.96);
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.14);
        border-radius: 10px;
        padding: 6px 12px;
        font-size: 12px;
        font-weight: 600;
        selection-background-color: rgba(96,165,250,0.32);
    }}

    QLineEdit#ActionInput:hover {{
        background: rgba(255,255,255,0.12);
        border: 1px solid rgba(255,255,255,0.20);
    }}

    QLineEdit#ActionInput:focus {{
        border: 1px solid rgba(96,165,250,0.75);
        background: rgba(255,255,255,0.12);
    }}

    QLineEdit#ActionInput:disabled {{
        color: rgba(232,240,255,0.46);
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
    }}

    /* ---- Cards ---- */
    #Card {{
        background: rgba(255,255,255,0.02);
        border: 1px solid {BORDER};
        border-radius: 18px;
    }}

    #Card[accent="green"] {{
        border-left: 4px solid {ACCENT["green"]};
    }}
    #Card[accent="blue"] {{
        border-left: 4px solid {ACCENT["blue"]};
    }}
    #Card[accent="orange"] {{
        border-left: 4px solid {ACCENT["orange"]};
    }}
    #Card[accent="red"] {{
        border-left: 4px solid {ACCENT["red"]};
    }}
    #Card[accent="purple"] {{
        border-left: 4px solid {ACCENT["purple"]};
    }}

    #CardTitle {{
        color: {TEXT_MID};
        font-size: 14px;
        font-weight: 750;
    }}

    #CardBig {{
        color: #ffffff;
        font-size: 30px;
        font-weight: 800;
    }}

    #CardSub {{
        color: {TEXT_MUTED};
        font-size: 12px;
    }}

    #Badge {{
        color: #f8fbff;
        background: rgba(96,165,250,0.16);
        border: 1px solid rgba(96,165,250,0.26);
        border-radius: 10px;
        padding: 5px 10px;
        font-size: 11px;
        font-weight: 700;
    }}

    QPushButton#Badge {{
        text-align: center;
    }}

    QToolButton#Badge {{
        text-align: center;
    }}

    QPushButton#Badge:hover {{
        background: rgba(96,165,250,0.22);
        border: 1px solid rgba(96,165,250,0.34);
    }}

    QToolButton#Badge:hover {{
        background: rgba(96,165,250,0.22);
        border: 1px solid rgba(96,165,250,0.34);
    }}

    #InspectorTitle {{
        color: {TEXT};
        font-size: 16px;
        font-weight: 800;
    }}

    #InspectorSub {{
        color: {TEXT_MUTED};
        font-size: 12px;
        font-weight: 600;
    }}

    #InspectorContainer {{
        background: transparent;
        border: none;
        border-radius: 0px;
    }}
    
"""


# --- v2 typography overrides (safe append) ---
TYPOGRAPHY_QSS = r'''
QLabel#CardHuge {
    font-size: 34px;
    font-weight: 800;
    letter-spacing: 0.2px;
    color: #ffffff;
}
QLabel#CardBig {
    font-size: 30px;
    font-weight: 800;
}
QLabel#CardTitle {
    font-size: 13px;
    font-weight: 700;
}
QLabel#CardSub {
    font-size: 11px;
    font-weight: 600;
    color: rgba(255,255,255,0.70);
}
'''

TOPBAR_QSS = r'''
QToolButton#TopBtn {
    background: rgba(255,255,255,0.08);
    color: #e8f0ff;
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 10px;
    padding: 6px 12px;
}

QToolButton#TopBtn:hover {
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.20);
}

QToolButton#TopBtn:pressed {
    background: rgba(255,255,255,0.06);
}

QToolButton#TopBtn::menu-indicator {
    image: none;
}

QToolButton#ExitBtn {
    border: none;
    padding: 6px 10px;
    color: #f87171;		/* soft red base */
    font-weight: 700;
    border-radius: 10px;
}

QToolButton#ExitBtn:hover {
    background: rgba(248,113,113,0.18);
    color: #ff4d4d;		/* brighter red */
}

QToolButton#ExitBtn:pressed {
    background: rgba(248,113,113,0.28);
}

QMenu {
    background: rgba(10,14,22,0.98);
    border: 1px solid rgba(255,255,255,0.16);
    color: #e8f0ff;
    padding: 6px;
}

QMenu::item {
    padding: 6px 18px;
    border-radius: 8px;
}

QMenu::item:selected {
    background: rgba(96,165,250,0.22);
}
'''

def qss():
    return _qss_base() + "\n" + TYPOGRAPHY_QSS + "\n" + TOPBAR_QSS
