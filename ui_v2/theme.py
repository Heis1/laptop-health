from __future__ import annotations
from PySide6.QtWidgets import QApplication

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

LIGHT_BG_MAIN = "#f3efe7"
LIGHT_BG_SIDEBAR = "#e8dcc9"
LIGHT_PANEL = "#fffaf2"
LIGHT_PANEL_SOFT = "#f7f0e4"
LIGHT_BORDER = "#d9cab3"
LIGHT_TEXT = "#1b2430"
LIGHT_TEXT_MID = "#344255"
LIGHT_TEXT_MUTED = "#67778b"
LIGHT_BLUE = "#2f6fed"
LIGHT_BLUE_SOFT = "rgba(47,111,237,0.12)"
LIGHT_GREEN_SOFT = "rgba(52,211,153,0.14)"
LIGHT_ORANGE_SOFT = "rgba(251,146,60,0.16)"
LIGHT_RED_SOFT = "rgba(248,113,113,0.14)"

def _qss_base() -> str:
    return f"""
    QMainWindow {{
        background: {BG_MAIN};
    }}

    QWidget#PopoutWindow {{
        background: rgba(6, 10, 18, 0.96);
    }}

    QFrame#PopoutSurface {{
        background: rgba(11, 18, 32, 0.96);
        border: 1px solid {BORDER};
        border-radius: 18px;
    }}

    QWidget#PopoutContent {{
        background: transparent;
    }}

    QTextEdit, QPlainTextEdit, QListWidget, QTableWidget, QTreeWidget {{
        background: rgba(10, 14, 22, 0.58);
        color: {TEXT};
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 12px;
        selection-background-color: rgba(96,165,250,0.24);
    }}

    QHeaderView::section {{
        background: rgba(15, 26, 43, 0.96);
        color: {TEXT_MID};
        border: 1px solid rgba(255,255,255,0.06);
        padding: 6px 8px;
    }}

    #TitleBar {{
        background: rgba(15,26,43,0.88);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 16px;
    }}

    #TitleBarMark {{
        min-width: 34px;
        min-height: 34px;
        max-width: 34px;
        max-height: 34px;
        border-radius: 17px;
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(96,165,250,0.96),
            stop:1 rgba(52,211,153,0.82)
        );
        color: white;
        font-size: 12px;
        font-weight: 900;
        letter-spacing: 0.8px;
    }}

    #TitleBarText {{
        color: {TEXT};
        font-size: 15px;
        font-weight: 800;
    }}

    #TitleBarSub {{
        color: rgba(191,219,254,0.66);
        font-size: 11px;
        font-weight: 600;
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

    #BrandBlock {{
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 16px;
    }}

    #BrandMark {{
        min-width: 42px;
        min-height: 42px;
        max-width: 42px;
        max-height: 42px;
        border-radius: 21px;
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(96,165,250,0.95),
            stop:1 rgba(52,211,153,0.80)
        );
        color: white;
        font-size: 14px;
        font-weight: 900;
        letter-spacing: 0.8px;
    }}

    #BrandSub {{
        color: rgba(191,219,254,0.68);
        font-size: 11px;
        font-weight: 600;
    }}

    #PageTitle {{
        color: {TEXT};
        font-size: 20px;
        font-weight: 800;
    }}

    #NavRow {{
        background: #12223a;
        border: none;
        border-radius: 12px;
    }}

    #NavRow[active="1"] {{
        background: rgba(96,165,250,0.15);
        border-left: 3px solid #60a5fa;
    }}

    #NavRow:hover {{
        background: #162b46;
    }}

    #NavBtn {{
        background: transparent;
        color: #cbd5e1;
        border: none;
        border-radius: 12px;
        padding: 10px 12px;
        text-align: left;
        font-size: 13px;
    }}

    #NavRow[active="1"] #NavBtn {{
        color: #ffffff;
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

    QPushButton#PopOutBtn {{
        color: rgba(232,240,255,0.90);
        background: transparent;
        border: none;
        border-radius: 10px;
        min-width: 34px;
        max-width: 34px;
        min-height: 32px;
        max-height: 32px;
        font-size: 13px;
        font-weight: 800;
        margin-right: 4px;
    }}

    QToolButton#Badge {{
        text-align: center;
    }}

    QPushButton#Badge:hover {{
        background: rgba(96,165,250,0.22);
        border: 1px solid rgba(96,165,250,0.34);
    }}

    QPushButton#PopOutBtn:hover {{
        background: rgba(96,165,250,0.18);
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

    #SidebarFooter {{
        background: rgba(7,12,20,0.92);
        border: 1px solid rgba(96,165,250,0.18);
        border-radius: 12px;
    }}

    #SidebarVersion {{
        color: rgba(191,219,254,0.72);
        font-size: 11px;
        padding: 0;
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

QToolButton#TitleBtn {
    background: rgba(255,255,255,0.06);
    color: #e8f0ff;
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 10px;
    padding: 4px 10px;
    min-width: 34px;
    min-height: 30px;
    font-size: 14px;
    font-weight: 700;
}

QToolButton#TitleBtn:hover {
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.18);
}

QToolButton#TitleCloseBtn {
    background: rgba(248,113,113,0.10);
    color: #fecaca;
    border: 1px solid rgba(248,113,113,0.18);
    border-radius: 10px;
    padding: 4px 10px;
    min-width: 34px;
    min-height: 30px;
    font-size: 14px;
    font-weight: 800;
}

QToolButton#TitleCloseBtn:hover {
    background: rgba(248,113,113,0.18);
    color: white;
    border: 1px solid rgba(248,113,113,0.30);
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

LIGHT_OVERRIDE_QSS = f"""
QMainWindow {{
    background: {LIGHT_BG_MAIN};
}}

QWidget#PopoutWindow {{
    background: rgba(243, 239, 231, 0.98);
}}

QFrame#PopoutSurface {{
    background: {LIGHT_PANEL};
    border: 1px solid {LIGHT_BORDER};
    border-radius: 18px;
}}

QWidget#PopoutContent {{
    background: transparent;
}}

QTextEdit, QPlainTextEdit, QListWidget, QTableWidget, QTreeWidget {{
    background: {LIGHT_PANEL_SOFT};
    color: {LIGHT_TEXT};
    border: 1px solid {LIGHT_BORDER};
    border-radius: 12px;
    selection-background-color: rgba(47,111,237,0.16);
}}

QHeaderView::section {{
    background: rgba(255,250,242,0.96);
    color: {LIGHT_TEXT_MID};
    border: 1px solid {LIGHT_BORDER};
    padding: 6px 8px;
}}

#TitleBar {{
    background: rgba(255,250,242,0.84);
    border: 1px solid rgba(27,36,48,0.08);
    border-radius: 16px;
}}

#TitleBarMark {{
    min-width: 34px;
    min-height: 34px;
    max-width: 34px;
    max-height: 34px;
    border-radius: 17px;
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #2f6fed,
        stop:1 #20b486
    );
    color: white;
    font-size: 12px;
    font-weight: 900;
    letter-spacing: 0.8px;
}}

#Sidebar {{
    background: {LIGHT_BG_SIDEBAR};
    border: 1px solid {LIGHT_BORDER};
}}

#BrandBlock {{
    background: rgba(255,250,242,0.72);
    border: 1px solid rgba(27,36,48,0.08);
    border-radius: 16px;
}}

#BrandMark {{
    min-width: 42px;
    min-height: 42px;
    max-width: 42px;
    max-height: 42px;
    border-radius: 21px;
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #2f6fed,
        stop:1 #20b486
    );
    color: white;
    font-size: 14px;
    font-weight: 900;
    letter-spacing: 0.8px;
}}

#AppTitle, #PageTitle, #InspectorTitle {{
    color: {LIGHT_TEXT};
}}

#TitleBarText {{
    color: {LIGHT_TEXT};
    font-size: 15px;
    font-weight: 800;
}}

#TitleBarSub {{
    color: {LIGHT_TEXT_MUTED};
    font-size: 11px;
    font-weight: 600;
}}

#BrandSub {{
    color: {LIGHT_TEXT_MUTED};
    font-size: 11px;
    font-weight: 600;
}}

#NavRow {{
    background: rgba(255,250,242,0.55);
    color: {LIGHT_TEXT};
    border: 1px solid rgba(27,36,48,0.06);
    border-radius: 12px;
}}

#NavRow[active="1"] {{
    background: rgba(255,250,242,0.92);
    border-left: 3px solid {LIGHT_BLUE};
}}

#NavRow:hover {{
    background: rgba(255,250,242,0.82);
}}

#NavBtn {{
    background: transparent;
    color: {LIGHT_TEXT};
    border: none;
}}

#NavRow[active="1"] #NavBtn {{
    color: {LIGHT_TEXT};
}}

QPushButton#ActionButton,
QToolButton#TopBtn,
QPushButton#Badge,
QPushButton#PopOutBtn,
QToolButton#Badge,
QComboBox#ActionSelect,
QLineEdit#ActionInput {{
    color: {LIGHT_TEXT};
    background: rgba(255,250,242,0.88);
    border: 1px solid rgba(27,36,48,0.10);
}}

QPushButton#ActionButton:hover,
QToolButton#TopBtn:hover,
QPushButton#Badge:hover,
QPushButton#PopOutBtn:hover,
QToolButton#Badge:hover,
QComboBox#ActionSelect:hover,
QLineEdit#ActionInput:hover {{
    background: #ffffff;
    border: 1px solid rgba(27,36,48,0.16);
}}

QToolButton#TitleBtn {{
    color: {LIGHT_TEXT};
    background: rgba(255,250,242,0.88);
    border: 1px solid rgba(27,36,48,0.10);
    border-radius: 10px;
    padding: 4px 10px;
    min-width: 34px;
    min-height: 30px;
    font-size: 14px;
    font-weight: 700;
}}

QToolButton#TitleBtn:hover {{
    background: #ffffff;
    border: 1px solid rgba(27,36,48,0.16);
}}

QToolButton#TitleCloseBtn {{
    color: #991b1b;
    background: rgba(220,38,38,0.08);
    border: 1px solid rgba(220,38,38,0.14);
    border-radius: 10px;
    padding: 4px 10px;
    min-width: 34px;
    min-height: 30px;
    font-size: 14px;
    font-weight: 800;
}}

QToolButton#TitleCloseBtn:hover {{
    background: rgba(220,38,38,0.14);
    border: 1px solid rgba(220,38,38,0.20);
    color: #7f1d1d;
}}

QLineEdit#ActionInput:focus {{
    border: 1px solid rgba(47,111,237,0.66);
    background: #ffffff;
}}

#Card, QFrame#Card {{
    background: {LIGHT_PANEL};
    border: 1px solid {LIGHT_BORDER};
}}

#Card[accent="green"], QFrame#Card[accent="green"] {{
    border-left: 4px solid #2ea97b;
    background: linear-gradient(to right, {LIGHT_GREEN_SOFT}, {LIGHT_PANEL});
}}

#Card[accent="blue"], QFrame#Card[accent="blue"] {{
    border-left: 4px solid {LIGHT_BLUE};
    background: linear-gradient(to right, {LIGHT_BLUE_SOFT}, {LIGHT_PANEL});
}}

#Card[accent="orange"], QFrame#Card[accent="orange"] {{
    border-left: 4px solid #d97706;
    background: linear-gradient(to right, {LIGHT_ORANGE_SOFT}, {LIGHT_PANEL});
}}

#Card[accent="red"], QFrame#Card[accent="red"] {{
    border-left: 4px solid #dc2626;
    background: linear-gradient(to right, {LIGHT_RED_SOFT}, {LIGHT_PANEL});
}}

#Card[accent="purple"], QFrame#Card[accent="purple"] {{
    border-left: 4px solid #7c3aed;
    background: linear-gradient(to right, rgba(124,58,237,0.12), {LIGHT_PANEL});
}}

#CardTitle, QLabel#CardTitle {{
    color: {LIGHT_TEXT_MID};
}}

#CardBig, QLabel#CardBig,
#CardHuge, QLabel#CardHuge {{
    color: {LIGHT_TEXT};
}}

#CardSub, QLabel#CardSub,
#InspectorSub {{
    color: {LIGHT_TEXT_MUTED};
}}

#Badge, QLabel#Badge {{
    color: {LIGHT_TEXT};
    background: rgba(47,111,237,0.10);
    border: 1px solid rgba(47,111,237,0.20);
}}

QMenu {{
    background: {LIGHT_PANEL};
    border: 1px solid {LIGHT_BORDER};
    color: {LIGHT_TEXT};
}}

QMenu::item:selected {{
    background: rgba(47,111,237,0.12);
}}

QListWidget,
QListView,
QAbstractItemView {{
    color: {LIGHT_TEXT};
    background: {LIGHT_PANEL_SOFT};
    border: 1px solid {LIGHT_BORDER};
}}

QComboBox#ActionSelect QAbstractItemView {{
    background: {LIGHT_PANEL};
    color: {LIGHT_TEXT};
    border: 1px solid {LIGHT_BORDER};
    selection-background-color: rgba(47,111,237,0.14);
}}

QDialog {{
    background: {LIGHT_BG_MAIN};
    color: {LIGHT_TEXT};
}}

QLabel {{
    color: {LIGHT_TEXT};
}}

#SidebarFooter {{
    background: rgba(255,250,242,0.88);
    border: 1px solid rgba(47,111,237,0.16);
    border-radius: 12px;
}}

#SidebarVersion {{
    color: {LIGHT_TEXT_MUTED};
    font-size: 11px;
    padding: 0;
}}

QToolButton#ExitBtn {{
    color: #b42318;
}}

QToolButton#ExitBtn:hover {{
    background: rgba(220,38,38,0.12);
    color: #991b1b;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: rgba(27,36,48,0.18);
    min-height: 24px;
    border-radius: 6px;
}}

QScrollBar::handle:vertical:hover {{
    background: rgba(27,36,48,0.28);
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: none;
    border: none;
}}
"""


def qss(mode: str = "dark"):
    base = _qss_base() + "\n" + TYPOGRAPHY_QSS + "\n" + TOPBAR_QSS
    if str(mode).lower() == "light":
        return base + "\n" + LIGHT_OVERRIDE_QSS
    return base


def current_theme_mode() -> str:
    app = QApplication.instance()
    if app is None:
        return "dark"
    mode = str(app.property("theme_mode") or "dark").lower()
    return "light" if mode == "light" else "dark"
