from __future__ import annotations

import os
import re
import signal
import subprocess

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QTextEdit, QFrame, QStyle, QDialog,
    QGraphicsOpacityEffect, QMessageBox, QSplitter,
)
from ui_v2.qtworker import QtWorker
from ui_v2.theme import current_theme_mode
from ui_v2.services.updates import (
    UPDATE_ACCENT_RGBA,
    classify_update_status,
    get_apt_action_description,
    get_update_count,
    reboot_required,
    list_upgradable,
    run_apt_action,
    list_kept_back,
    list_holds,
    get_apt_action_argv,
)

_ACCENT_STRIP = UPDATE_ACCENT_RGBA

def _page_qss(mode: str) -> str:
    if mode == "light":
        return """
QPushButton#ActionBtn {
    color: rgba(27,36,48,0.96);
    background: rgba(255,250,242,0.88);
    border: 1px solid rgba(27,36,48,0.12);
    padding: 7px 12px;
    border-radius: 10px;
}
QPushButton#ActionBtn:hover {
    background: #ffffff;
    border: 1px solid rgba(27,36,48,0.18);
}
QPushButton#ActionBtn:pressed { background: rgba(27,36,48,0.06); }
QPushButton#ActionBtn:disabled {
    color: rgba(27,36,48,0.35);
    background: rgba(27,36,48,0.04);
    border: 1px solid rgba(27,36,48,0.08);
}
QPushButton#ActionBtn[accent="green"][status="idle"] {
    color: rgba(20,83,45,0.98); background: rgba(52,211,153,0.18); border: 1px solid rgba(52,211,153,0.34);
}
QPushButton#ActionBtn[accent="blue"][status="idle"] {
    color: rgba(30,64,175,0.98); background: rgba(47,111,237,0.14); border: 1px solid rgba(47,111,237,0.30);
}
QPushButton#ActionBtn[accent="orange"][status="idle"] {
    color: rgba(154,52,18,0.98); background: rgba(251,146,60,0.16); border: 1px solid rgba(251,146,60,0.30);
}
QPushButton#ActionBtn[accent="red"][status="idle"] {
    color: rgba(153,27,27,0.98); background: rgba(248,113,113,0.14); border: 1px solid rgba(248,113,113,0.30);
}
QPushButton#ActionBtn[accent="slate"][status="idle"] {
    color: rgba(51,65,85,0.96); background: rgba(148,163,184,0.16); border: 1px solid rgba(148,163,184,0.30);
}
QPushButton#ActionBtn[status="running"] { background: rgba(47,111,237,0.12); border: 1px solid rgba(47,111,237,0.28); color: rgba(27,36,48,0.98); }
QPushButton#ActionBtn[status="success"] { background: rgba(52,211,153,0.18); border: 1px solid rgba(52,211,153,0.34); color: rgba(27,36,48,0.98); }
QPushButton#ActionBtn[status="error"] { background: rgba(248,113,113,0.16); border: 1px solid rgba(248,113,113,0.34); color: rgba(27,36,48,0.98); }
QPushButton#ActionBtn[status="attention"] { background: rgba(251,146,60,0.16); border: 1px solid rgba(251,146,60,0.32); color: rgba(27,36,48,0.98); }
QTextEdit#UpdatesLog {
    background: rgba(255,250,242,0.92); color: rgba(27,36,48,0.92); border: 1px solid rgba(27,36,48,0.10); border-radius: 12px; padding: 10px;
}
QScrollBar:vertical { background: transparent; width: 10px; margin: 6px 0 6px 0; }
QScrollBar::handle:vertical { background: rgba(27,36,48,0.18); border-radius: 5px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: rgba(27,36,48,0.28); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0 6px 0 6px; }
QScrollBar::handle:horizontal { background: rgba(27,36,48,0.18); border-radius: 5px; min-width: 28px; }
QScrollBar::handle:horizontal:hover { background: rgba(27,36,48,0.28); }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
"""
    return """
QPushButton#ActionBtn {
    color: rgba(255,255,255,0.92);
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.14);
    padding: 7px 12px;
    border-radius: 10px;
}
QPushButton#ActionBtn:hover { background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.18); }
QPushButton#ActionBtn:pressed { background: rgba(255,255,255,0.06); }
QPushButton#ActionBtn:disabled { color: rgba(255,255,255,0.35); background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); }
QPushButton#ActionBtn[accent="green"][status="idle"] { color: rgba(220,255,238,0.98); background: rgba(52,211,153,0.20); border: 1px solid rgba(52,211,153,0.42); }
QPushButton#ActionBtn[accent="blue"][status="idle"] { color: rgba(230,242,255,0.98); background: rgba(96,165,250,0.18); border: 1px solid rgba(96,165,250,0.42); }
QPushButton#ActionBtn[accent="orange"][status="idle"] { color: rgba(255,241,224,0.98); background: rgba(251,146,60,0.20); border: 1px solid rgba(251,146,60,0.44); }
QPushButton#ActionBtn[accent="red"][status="idle"] { color: rgba(255,234,234,0.98); background: rgba(248,113,113,0.18); border: 1px solid rgba(248,113,113,0.42); }
QPushButton#ActionBtn[accent="slate"][status="idle"] { color: rgba(232,240,250,0.96); background: rgba(100,116,139,0.22); border: 1px solid rgba(148,163,184,0.42); }
QPushButton#ActionBtn[status="running"] { background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.34); color: rgba(255,255,255,0.98); }
QPushButton#ActionBtn[status="success"] { background: rgba(52,211,153,0.20); border: 1px solid rgba(52,211,153,0.48); color: rgba(255,255,255,0.98); }
QPushButton#ActionBtn[status="error"] { background: rgba(248,113,113,0.20); border: 1px solid rgba(248,113,113,0.46); color: rgba(255,255,255,0.98); }
QPushButton#ActionBtn[status="attention"] { background: rgba(251,146,60,0.18); border: 1px solid rgba(251,146,60,0.42); color: rgba(255,255,255,0.98); }
QTextEdit#UpdatesLog { background: rgba(10, 14, 22, 0.52); color: rgba(255,255,255,0.88); border: 1px solid rgba(255,255,255,0.10); border-radius: 12px; padding: 10px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 6px 0 6px 0; }
QScrollBar::handle:vertical { background: rgba(255,255,255,0.18); border-radius: 5px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.28); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0 6px 0 6px; }
QScrollBar::handle:horizontal { background: rgba(255,255,255,0.18); border-radius: 5px; min-width: 28px; }
QScrollBar::handle:horizontal:hover { background: rgba(255,255,255,0.28); }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
"""


def _table_qss(mode: str) -> str:
    if mode == "light":
        return """
QTableWidget#UpdatesTable {
    background: transparent;
    border: 1px solid rgba(27,36,48,0.10);
    border-radius: 12px;
    color: rgba(27,36,48,0.92);
    selection-background-color: rgba(47,111,237,0.12);
    selection-color: rgba(27,36,48,0.98);
    outline: 0;
}
QTableWidget#UpdatesTable::viewport { background: rgba(255,250,242,0.92); border-radius: 12px; }
QTableWidget::item { padding: 7px 10px; border-bottom: 1px solid rgba(27,36,48,0.05); background: transparent; }
QTableWidget::item:hover { background: rgba(27,36,48,0.04); }
QTableWidget::item:selected { background: rgba(47,111,237,0.12); }
QTableWidget::item:selected:hover { background: rgba(47,111,237,0.16); }
QTableCornerButton::section { background: rgba(27,36,48,0.05); border: 0px; }
"""
    return """
QTableWidget#UpdatesTable {
    background: transparent;
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 12px;
    color: rgba(255,255,255,0.90);
    selection-background-color: rgba(255,255,255,0.12);
    selection-color: rgba(255,255,255,0.96);
    outline: 0;
}
QTableWidget#UpdatesTable::viewport { background: rgba(10, 14, 22, 0.52); border-radius: 12px; }
QTableWidget::item { padding: 7px 10px; border-bottom: 1px solid rgba(255,255,255,0.05); background: transparent; }
QTableWidget::item:hover { background: rgba(255,255,255,0.06); }
QTableWidget::item:selected { background: rgba(255,255,255,0.12); }
QTableWidget::item:selected:hover { background: rgba(255,255,255,0.14); }
QTableCornerButton::section { background: rgba(255,255,255,0.07); border: 0px; }
"""


def _hdr_qss(mode: str) -> str:
    if mode == "light":
        return """
QHeaderView { background: rgba(255,250,242,0.92); }
QHeaderView::section {
    background: rgba(27,36,48,0.05);
    color: rgba(27,36,48,0.90);
    padding: 8px 10px;
    border: 0px;
    border-bottom: 1px solid rgba(27,36,48,0.10);
}
"""
    return """
QHeaderView { background: rgba(10, 14, 22, 0.52); }
QHeaderView::section {
    background: rgba(255,255,255,0.07);
    color: rgba(255,255,255,0.88);
    padding: 8px 10px;
    border: 0px;
    border-bottom: 1px solid rgba(255,255,255,0.10);
}
"""

_APT_FETCH_RE = re.compile(r"^(?:Get|Hit|Ign):\d+\s+\S+\s+(.+?)(?:\s+\[[^\]]+\])?$")
_PKG_STAGE_PATTERNS = (
    (re.compile(r"^Preparing to unpack .*?/([^/\s_]+)[^/\s]*\.deb"), "Preparing"),
    (re.compile(r"^Unpacking\s+([^\s:(]+)"), "Unpacking"),
    (re.compile(r"^Setting up\s+([^\s:(]+)"), "Setting up"),
    (re.compile(r"^Removing\s+([^\s:(]+)"), "Removing"),
    (re.compile(r"^Configuring\s+([^\s:(]+)"), "Configuring"),
)
_PERCENT_RE = re.compile(r"(\d{1,3})%")

_METRIC_STYLES = {
    "neutral": (
        "rgba(255,255,255,0.78)",
        "rgba(255,255,255,0.04)",
        "rgba(255,255,255,0.10)",
    ),
    "warning": (
        "rgba(255,214,170,0.98)",
        "rgba(251,146,60,0.14)",
        "rgba(251,146,60,0.30)",
    ),
    "danger": (
        "rgba(255,195,195,0.98)",
        "rgba(248,113,113,0.14)",
        "rgba(248,113,113,0.34)",
    ),
    "success": (
        "rgba(194,255,223,0.98)",
        "rgba(52,211,153,0.12)",
        "rgba(52,211,153,0.28)",
    ),
}


def _mk_btn(text: str, icon, tip: str, accent: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("ActionBtn")
    b.setProperty("accent", accent)
    b.setProperty("status", "idle")
    b.setIcon(icon)
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip(tip)
    return b


class AptActionRunner(QThread):
    line = Signal(str)
    done = Signal(int)

    def __init__(self, action: str, parent=None):
        super().__init__(parent)
        self.action = action
        self._proc: subprocess.Popen[str] | None = None

    def is_active(self) -> bool:
        proc = self._proc
        return bool(self.isRunning() or (proc is not None and proc.poll() is None))

    def _signal_proc(self, sig: int) -> bool:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return True
        try:
            if os.name == "posix":
                os.killpg(proc.pid, sig)
            else:
                proc.send_signal(sig)
            return True
        except ProcessLookupError:
            return True
        except Exception:
            return False

    def request_stop(self, timeout_ms: int = 2500) -> bool:
        if not self.is_active():
            return True
        self._signal_proc(signal.SIGINT)
        return self.wait(max(0, timeout_ms))

    def force_stop(self, timeout_ms: int = 1500) -> bool:
        if not self.is_active():
            return True
        self._signal_proc(signal.SIGTERM)
        if self.wait(max(0, timeout_ms)):
            return True
        self._signal_proc(signal.SIGKILL)
        return self.wait(max(0, timeout_ms))

    def run(self) -> None:
        try:
            argv = get_apt_action_argv(self.action)
        except ValueError as e:
            self.line.emit(str(e))
            self.done.emit(2)
            return
        except FileNotFoundError as e:
            self.line.emit(str(e))
            self.done.emit(127)
            return
        except Exception as e:
            self.line.emit(f"Failed to prepare command: {e}")
            self.done.emit(1)
            return

        try:
            self._proc = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                start_new_session=True,
            )

            assert self._proc.stdout is not None
            for raw in self._proc.stdout:
                line = raw.rstrip()
                if line:
                    self.line.emit(line)

            rc = int(self._proc.wait())
            self.done.emit(rc)
        except Exception as e:
            self.line.emit(f"Command failed: {e}")
            self.done.emit(1)
        finally:
            self._proc = None


class ConfirmDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, message: str, accent: str = "orange"):
        super().__init__(parent)

        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        host = parent.window()
        self.setGeometry(host.geometry())

        strip = _ACCENT_STRIP.get(accent, "rgba(255,190,120,0.95)")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scrim = QFrame()
        scrim.setObjectName("ConfirmScrim")
        scrim_lay = QVBoxLayout(scrim)
        scrim_lay.setContentsMargins(0, 0, 0, 0)
        scrim_lay.setSpacing(0)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(1)

        card = QFrame()
        card.setObjectName("ConfirmCard")
        card.setFixedWidth(480)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        ico = QLabel()
        ico.setPixmap(self.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(20, 20))
        hdr.addWidget(ico)

        t = QLabel(title)
        t.setObjectName("ConfirmTitle")
        hdr.addWidget(t)
        hdr.addStretch(1)

        self.btn_x = QPushButton("✕")
        self.btn_x.setObjectName("ConfirmX")
        self.btn_x.setCursor(Qt.PointingHandCursor)
        self.btn_x.clicked.connect(self.reject)
        hdr.addWidget(self.btn_x)

        lay.addLayout(hdr)

        body = QLabel(message)
        body.setObjectName("ConfirmBody")
        body.setWordWrap(True)
        lay.addWidget(body)

        btns = QHBoxLayout()
        btns.addStretch(1)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("ActionBtn")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_ok = QPushButton("Proceed")
        self.btn_ok.setObjectName("ActionBtn")
        self.btn_ok.clicked.connect(self.accept)

        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        lay.addLayout(btns)

        row.addWidget(card)
        row.addStretch(1)

        scrim_lay.addStretch(1)
        scrim_lay.addLayout(row)
        scrim_lay.addStretch(1)

        root.addWidget(scrim)

        scrim.mousePressEvent = lambda e: self.reject()

        self.setStyleSheet(f"""
            QFrame#ConfirmScrim {{
                background: rgba(0, 0, 0, 0.55);
            }}
            QFrame#ConfirmCard {{
                background: rgba(10, 14, 22, 0.92);
                border: 1px solid rgba(255,255,255,0.14);
                border-left: 6px solid {strip};
                border-radius: 16px;
            }}
            QLabel#ConfirmTitle {{
                color: rgba(255,255,255,0.96);
                font-weight: 700;
                font-size: 16px;
            }}
            QLabel#ConfirmBody {{
                color: rgba(255,255,255,0.82);
                font-size: 12px;
            }}
            QPushButton#ConfirmX {{
                color: rgba(255,255,255,0.75);
                background: transparent;
                border: 0px;
                padding: 4px 8px;
                border-radius: 10px;
                font-size: 14px;
            }}
            QPushButton#ConfirmX:hover {{
                background: rgba(255,255,255,0.10);
                color: rgba(255,255,255,0.92);
            }}
            QPushButton#ActionBtn {{
                color: rgba(255,255,255,0.92);
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.14);
                padding: 7px 12px;
                border-radius: 10px;
                min-width: 110px;
            }}
            QPushButton#ActionBtn:hover {{
                background: rgba(255,255,255,0.12);
                border: 1px solid rgba(255,255,255,0.18);
            }}
            QPushButton#ActionBtn:pressed {{
                background: rgba(255,255,255,0.06);
            }}
        """)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(e)


class UpdatesPage(QWidget):
    def __init__(self):
        super().__init__()
        self._theme_mode = current_theme_mode()
        self.setStyleSheet(_page_qss(self._theme_mode))
        self._refresh_failed = False
        self._active_action: str | None = None
        self._activity_rows: dict[str, int] = {}
        self._activity_order: list[str] = []
        self._last_activity_package: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 16, 18)
        root.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("Updates")
        title.setObjectName("HeroTitle")
        top.addWidget(title)
        top.addStretch(1)

        self.btn_refresh = _mk_btn("Refresh", self.style().standardIcon(QStyle.SP_BrowserReload), "Refresh pending updates list", "blue")
        self.btn_refresh.clicked.connect(self.refresh)
        top.addWidget(self.btn_refresh)
        root.addLayout(top)

        self.status = QFrame()
        self.status.setObjectName("Card")
        self.status.setProperty("accent", "orange")
        st = QHBoxLayout(self.status)
        st.setContentsMargins(14, 12, 14, 12)
        st.setSpacing(16)

        self.lbl_total = QLabel("Total: —"); self.lbl_total.setObjectName("CardSub"); st.addWidget(self.lbl_total)
        self.lbl_sec = QLabel("Security: —"); self.lbl_sec.setObjectName("CardSub"); st.addWidget(self.lbl_sec)
        self.lbl_reboot = QLabel("Reboot: —"); self.lbl_reboot.setObjectName("CardSub"); st.addWidget(self.lbl_reboot)
        self.lbl_kept = QLabel("Kept back: —"); self.lbl_kept.setObjectName("CardSub"); st.addWidget(self.lbl_kept)
        self.lbl_held = QLabel("Held: —"); self.lbl_held.setObjectName("CardSub"); st.addWidget(self.lbl_held)
        st.addStretch(1)
        self.badge = QLabel("—"); self.badge.setObjectName("Badge"); st.addWidget(self.badge)
        root.addWidget(self.status)

        self.toolbar = QFrame()
        self.toolbar.setObjectName("Card")
        self.toolbar.setProperty("accent", "blue")
        tb = QHBoxLayout(self.toolbar)
        tb.setContentsMargins(12, 10, 12, 10)
        tb.setSpacing(10)

        self.btn_update_lists = _mk_btn("Update lists", self.style().standardIcon(QStyle.SP_BrowserReload), self._command_tip("update"), "green")
        self.btn_update_lists.clicked.connect(lambda: self._confirm_and_run("update"))
        tb.addWidget(self.btn_update_lists)

        self.btn_upgrade = _mk_btn("Upgrade", self.style().standardIcon(QStyle.SP_ArrowUp), self._command_tip("upgrade"), "blue")
        self.btn_upgrade.clicked.connect(lambda: self._confirm_and_run("upgrade"))
        tb.addWidget(self.btn_upgrade)

        self.btn_full = _mk_btn(
            "Full upgrade",
            self.style().standardIcon(QStyle.SP_DialogApplyButton),
            f"Runs: {get_apt_action_description('full-upgrade')} (may remove/replace packages)",
            "orange",
        )
        self.btn_full.clicked.connect(lambda: self._confirm_and_run("full-upgrade"))
        tb.addWidget(self.btn_full)

        self.btn_autoremove = _mk_btn("Autoremove", self.style().standardIcon(QStyle.SP_TrashIcon), self._command_tip("autoremove"), "slate")
        self.btn_autoremove.clicked.connect(lambda: self._confirm_and_run("autoremove"))
        tb.addWidget(self.btn_autoremove)

        tb.addStretch(1)
        root.addWidget(self.toolbar)

        base_font = self.lbl_total.font()
        base_font.setPointSize(max(9, base_font.pointSize()))
        for b in (self.btn_refresh, self.btn_update_lists, self.btn_upgrade, self.btn_full, self.btn_autoremove):
            b.setFont(base_font)

        self.sections = QSplitter(Qt.Vertical)
        self.sections.setChildrenCollapsible(False)
        self.sections.setHandleWidth(10)
        root.addWidget(self.sections, 1)

        self.pending_panel = QFrame()
        self.pending_panel.setObjectName("Card")
        self.pending_panel.setProperty("accent", "blue")
        pending_l = QVBoxLayout(self.pending_panel)
        pending_l.setContentsMargins(14, 12, 14, 14)
        pending_l.setSpacing(8)

        self.pending_title = QLabel("Pending Updates")
        self.pending_title.setObjectName("CardTitle")
        pending_l.addWidget(self.pending_title)

        self.pending_sub = QLabel("Packages currently available to update on this system.")
        self.pending_sub.setObjectName("CardSub")
        pending_l.addWidget(self.pending_sub)

        self.table = QTableWidget(0, 4)
        self.table.setObjectName("UpdatesTable")
        self.table.setStyleSheet(_table_qss(self._theme_mode))
        self.table.setHorizontalHeaderLabels(["Package", "Origin", "Security", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setFont(base_font)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.verticalHeader().setMinimumSectionSize(34)

        hdr = self.table.horizontalHeader()
        hdr.setStyleSheet(_hdr_qss(self._theme_mode))
        hdr.setHighlightSections(False)
        hdr.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hdr.setMinimumHeight(34)

        hdr_font = QFont(base_font); hdr_font.setBold(True)
        hdr.setFont(hdr_font)

        pending_l.addWidget(self.table, 1)
        self.sections.addWidget(self.pending_panel)

        self.lower_panel = QFrame()
        self.lower_panel.setObjectName("Card")
        self.lower_panel.setProperty("accent", "blue")
        lower_l = QVBoxLayout(self.lower_panel)
        lower_l.setContentsMargins(14, 12, 14, 14)
        lower_l.setSpacing(10)

        self.lower_title = QLabel("Operations & Output")
        self.lower_title.setObjectName("CardTitle")
        lower_l.addWidget(self.lower_title)

        self.lower_sub = QLabel("Live package actions and command output for the current update task.")
        self.lower_sub.setObjectName("CardSub")
        lower_l.addWidget(self.lower_sub)

        lower_split = QSplitter(Qt.Horizontal)
        lower_split.setChildrenCollapsible(False)
        lower_split.setHandleWidth(10)
        lower_l.addWidget(lower_split, 1)

        self.activity_panel = QFrame()
        self.activity_panel.setObjectName("Card")
        self.activity_panel.setProperty("accent", "blue")
        activity_l = QVBoxLayout(self.activity_panel)
        activity_l.setContentsMargins(12, 10, 12, 12)
        activity_l.setSpacing(8)

        self.activity_title = QLabel("Active Operations")
        self.activity_title.setObjectName("CardTitle")
        activity_l.addWidget(self.activity_title)

        self.activity = QTableWidget(0, 3)
        self.activity.setObjectName("UpdatesTable")
        self.activity.setStyleSheet(_table_qss(self._theme_mode))
        self.activity.setHorizontalHeaderLabels(["Item", "Stage", "Progress"])
        self.activity.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.activity.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.activity.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.activity.verticalHeader().setVisible(False)
        self.activity.setSelectionMode(QTableWidget.NoSelection)
        self.activity.setEditTriggers(QTableWidget.NoEditTriggers)
        self.activity.setShowGrid(False)
        self.activity.setAlternatingRowColors(False)
        self.activity.setFont(base_font)
        self.activity.setFocusPolicy(Qt.NoFocus)
        self.activity.setWordWrap(False)
        self.activity.setTextElideMode(Qt.ElideRight)
        self.activity.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.activity.verticalHeader().setDefaultSectionSize(38)
        self.activity.verticalHeader().setMinimumSectionSize(34)
        self.activity.setMinimumHeight(140)

        activity_hdr = self.activity.horizontalHeader()
        activity_hdr.setStyleSheet(_hdr_qss(self._theme_mode))
        activity_hdr.setHighlightSections(False)
        activity_hdr.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        activity_hdr.setMinimumHeight(34)
        activity_hdr.setFont(hdr_font)

        activity_l.addWidget(self.activity, 1)
        lower_split.addWidget(self.activity_panel)

        self.log_panel = QFrame()
        self.log_panel.setObjectName("Card")
        self.log_panel.setProperty("accent", "blue")
        log_l = QVBoxLayout(self.log_panel)
        log_l.setContentsMargins(12, 10, 12, 12)
        log_l.setSpacing(8)

        self.log_title = QLabel("Command Output")
        self.log_title.setObjectName("CardTitle")
        log_l.addWidget(self.log_title)

        self.log = QTextEdit()
        self.log.setObjectName("UpdatesLog")
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Output will appear here…")

        self._busy_fx_table = QGraphicsOpacityEffect(self.table)
        self._busy_fx_table.setOpacity(1.0)
        self.table.setGraphicsEffect(self._busy_fx_table)

        self._busy_fx_log = QGraphicsOpacityEffect(self.log)
        self._busy_fx_log.setOpacity(1.0)
        self.log.setGraphicsEffect(self._busy_fx_log)

        self._busy_fx_activity = QGraphicsOpacityEffect(self.activity)
        self._busy_fx_activity.setOpacity(1.0)
        self.activity.setGraphicsEffect(self._busy_fx_activity)

        mono = QFont()
        mono.setFamilies(["JetBrains Mono", "Fira Code", "Monospace"])
        mono.setPointSize(max(9, base_font.pointSize() - 1))
        self.log.setFont(mono)
        self.log.setMinimumHeight(150)
        log_l.addWidget(self.log, 1)
        lower_split.addWidget(self.log_panel)

        lower_split.setStretchFactor(0, 3)
        lower_split.setStretchFactor(1, 4)
        lower_split.setSizes([360, 500])
        self.sections.addWidget(self.lower_panel)

        self.sections.setStretchFactor(0, 8)
        self.sections.setStretchFactor(1, 3)
        self.sections.setSizes([560, 240])

        self._workers: list[QtWorker] = []
        self._action_runner: AptActionRunner | None = None

        from PySide6.QtCore import QTimer
        self._busy_anim_tick = 0
        self._busy_anim = QTimer(self)
        self._busy_anim.setInterval(250)
        self._busy_anim.timeout.connect(self._tick_busy_badge)

        self.refresh()

    def apply_theme_mode(self, mode: str) -> None:
        self._theme_mode = "light" if str(mode).lower() == "light" else "dark"
        self.setStyleSheet(_page_qss(self._theme_mode))
        self.table.setStyleSheet(_table_qss(self._theme_mode))
        self.activity.setStyleSheet(_table_qss(self._theme_mode))
        self.table.horizontalHeader().setStyleSheet(_hdr_qss(self._theme_mode))
        self.activity.horizontalHeader().setStyleSheet(_hdr_qss(self._theme_mode))

    def _command_tip(self, action: str) -> str:
        return f"Runs: {get_apt_action_description(action)}"

    def _button_map(self) -> dict[str, QPushButton]:
        return {
            "refresh": self.btn_refresh,
            "update": self.btn_update_lists,
            "upgrade": self.btn_upgrade,
            "full-upgrade": self.btn_full,
            "autoremove": self.btn_autoremove,
        }

    def _set_button_status(self, key: str, status: str) -> None:
        btn = self._button_map().get(key)
        if btn is None:
            return
        btn.setProperty("status", status)
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        btn.update()

    def _set_output_panels_accent(self, accent: str) -> None:
        for panel in (self.lower_panel, self.activity_panel, self.log_panel):
            panel.setProperty("accent", accent)
            panel.style().unpolish(panel)
            panel.style().polish(panel)
            panel.update()

    def _clear_activity(self) -> None:
        self.activity.setRowCount(0)
        self._activity_rows.clear()
        self._activity_order.clear()
        self._last_activity_package = None

    def _activity_row(self, package: str) -> int:
        row = self._activity_rows.get(package)
        if row is not None:
            return row
        row = self.activity.rowCount()
        self.activity.insertRow(row)
        self._activity_rows[package] = row
        self._activity_order.append(package)

        pkg_item = QTableWidgetItem(package)
        stage_item = QTableWidgetItem("Queued")
        pct_item = QTableWidgetItem("0%")
        pct_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.activity.setItem(row, 0, pkg_item)
        self.activity.setItem(row, 1, stage_item)
        self.activity.setItem(row, 2, pct_item)
        return row

    def _update_activity(self, package: str, stage: str, percent: int | None = None) -> None:
        if not package:
            return
        row = self._activity_row(package)
        stage_item = self.activity.item(row, 1)
        pct_item = self.activity.item(row, 2)
        if stage_item is not None:
            stage_item.setText(stage)
        if pct_item is not None:
            if percent is None:
                if stage.lower() in {"downloaded", "setting up", "installed", "configured", "complete"}:
                    pct_item.setText("100%")
                elif "download" in stage.lower():
                    pct_item.setText("...")
            else:
                pct_item.setText(f"{max(0, min(100, int(percent)))}%")
        self._last_activity_package = package

    def _mark_all_activity_complete(self, success: bool) -> None:
        final_stage = "Complete" if success else "Interrupted"
        final_pct = "100%" if success else "!"
        for package in self._activity_order:
            row = self._activity_rows.get(package)
            if row is None:
                continue
            stage_item = self.activity.item(row, 1)
            pct_item = self.activity.item(row, 2)
            if stage_item is not None:
                stage_item.setText(final_stage)
            if pct_item is not None:
                pct_item.setText(final_pct)

    def _parse_fetch_package(self, line: str) -> str | None:
        match = _APT_FETCH_RE.match(line)
        if not match:
            return None
        tail = match.group(1).strip()
        if not tail:
            return None
        parts = tail.split()
        if not parts:
            return None
        name = parts[0].strip()
        if "/" in name or name.endswith(":"):
            return None
        return name

    def _parse_stage_package(self, line: str) -> tuple[str, str] | None:
        for pattern, stage in _PKG_STAGE_PATTERNS:
            match = pattern.search(line)
            if match:
                return match.group(1), stage
        return None

    def _handle_action_output(self, line: str) -> None:
        self._append_log(line)

        package = self._parse_fetch_package(line)
        if package:
            percent_match = _PERCENT_RE.search(line)
            percent = int(percent_match.group(1)) if percent_match else None
            self._update_activity(package, "Downloading", percent)
            return

        staged = self._parse_stage_package(line)
        if staged:
            package, stage = staged
            percent = 100 if stage in {"Setting up", "Configuring"} else None
            self._update_activity(package, stage, percent)
            return

        percent_match = _PERCENT_RE.search(line)
        if percent_match and self._last_activity_package:
            self._update_activity(
                self._last_activity_package,
                "Downloading",
                int(percent_match.group(1)),
            )

    def _set_badge(self, text: str, accent: str):
        self.badge.setText(text)
        col = _ACCENT_STRIP.get(accent, "rgba(255,255,255,0.85)")
        self.badge.setStyleSheet(
            "font-weight: 800;"
            "letter-spacing: 0.3px;"
            "padding: 4px 10px;"
            "border-radius: 999px;"
            f"color: {col};"
            f"border: 1px solid {col};"
            "background: rgba(255,255,255,0.06);"
        )

    def _set_metric(self, label: QLabel, title: str, value: str, state: str) -> None:
        fg, bg, border = _METRIC_STYLES.get(state, _METRIC_STYLES["neutral"])
        label.setText(f"{title}: {value}")
        label.setStyleSheet(
            f"color: {fg};"
            f"background: {bg};"
            f"border: 1px solid {border};"
            "border-radius: 999px;"
            "padding: 4px 10px;"
            "font-size: 12px;"
            "font-weight: 700;"
        )

    def _set_status(self, total: int | None, sec: int | None, reb: bool, kept: int = 0, held: int = 0):
        if total is None:
            self._set_metric(self.lbl_total, "Total", "—", "neutral")
            self._set_metric(self.lbl_sec, "Security", "—", "neutral")
            self._set_metric(self.lbl_reboot, "Reboot", "—", "neutral")
            self._set_metric(self.lbl_kept, "Kept back", "—", "neutral")
            self._set_metric(self.lbl_held, "Held", "—", "neutral")
            accent = "red"
            self._set_badge("UNKNOWN", accent)
        else:
            total = int(total)
            sec = 0 if sec is None else int(sec)
            self._set_metric(self.lbl_total, "Total", str(total), "warning" if total > 0 else "success")
            self._set_metric(self.lbl_sec, "Security", str(sec), "danger" if sec > 0 else "success")
            self._set_metric(self.lbl_reboot, "Reboot", "Yes" if reb else "No", "danger" if reb else "success")
            self._set_metric(self.lbl_kept, "Kept back", str(kept), "warning" if kept > 0 else "success")
            self._set_metric(self.lbl_held, "Held", str(held), "danger" if held > 0 else "success")

            badge, accent = classify_update_status(total, sec, reb, kept, held)
            self._set_badge(badge, accent)

        strip = _ACCENT_STRIP.get(accent, "rgba(255,255,255,0.14)")
        self.status.setStyleSheet(
            "background: rgba(255,255,255,0.02);"
            "border-radius: 16px;"
            "border: 1px solid rgba(255,255,255,0.14);"
            f"border-left: 6px solid {strip};"
        )

        self.status.setProperty("accent", accent)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.update()

    def _tint_row(self, r: int, bg: QColor | None = None):
        for c in range(self.table.columnCount()):
            it = self.table.item(r, c)
            if it is None:
                continue
            if bg is not None:
                it.setBackground(bg)

    def _fill_table(self, items: list[dict], kept_set: set[str] | None = None, held_set: set[str] | None = None):
        self.table.setRowCount(0)
        for it in items:
            r = self.table.rowCount()
            self.table.insertRow(r)

            pkg_name = str(it.get("name", ""))
            origin_txt = str(it.get("origin", ""))

            name = QTableWidgetItem(pkg_name)
            origin = QTableWidgetItem(origin_txt)

            sec_flag = bool(it.get("security"))
            sec = QTableWidgetItem("Yes" if sec_flag else "No")
            sec.setTextAlignment(Qt.AlignCenter)

            if sec_flag:
                f = name.font(); f.setBold(True)
                name.setFont(f); origin.setFont(f); sec.setFont(f)

            is_kept = bool(kept_set and pkg_name in kept_set)
            is_held = bool(held_set and pkg_name in held_set)

            status_txt = "Upgradable"
            if is_kept:
                status_txt = "Kept back"
            if is_held:
                status_txt = "Held"

            status = QTableWidgetItem(status_txt)
            status.setTextAlignment(Qt.AlignCenter)

            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, origin)
            self.table.setItem(r, 2, sec)
            self.table.setItem(r, 3, status)

            if is_held:
                status.setForeground(QColor(255, 150, 150))
                self._tint_row(r, bg=QColor(255, 120, 120, 28))
            elif is_kept:
                status.setForeground(QColor(255, 205, 150))
                self._tint_row(r, bg=QColor(255, 190, 120, 22))
            elif sec_flag:
                self._tint_row(r, bg=QColor(150, 190, 255, 16))

            if status_txt != "Upgradable":
                f2 = status.font(); f2.setBold(True)
                status.setFont(f2)
                f3 = name.font(); f3.setBold(True)
                name.setFont(f3)

    def _set_busy(self, busy: bool, msg: str | None = None) -> None:
        for b in (
            self.btn_refresh,
            self.btn_update_lists,
            self.btn_upgrade,
            self.btn_full,
            self.btn_autoremove,
        ):
            try:
                b.setEnabled(not busy)
            except Exception:
                pass

        try:
            self._busy_fx_table.setOpacity(0.55 if busy else 1.0)
            self._busy_fx_log.setOpacity(0.55 if busy else 1.0)
            self._busy_fx_activity.setOpacity(0.55 if busy else 1.0)
        except Exception:
            pass

        if msg:
            self._append_log(msg)

        if busy:
            self._set_output_panels_accent("blue")
            self._set_button_status("refresh", "running")
            self._busy_anim_tick = 0
            self._set_badge("REFRESHING", "blue")
            try:
                self._busy_anim.start()
            except Exception:
                pass
        else:
            self._set_output_panels_accent("blue")
            self._set_button_status("refresh", "error" if self._refresh_failed else "success")
            try:
                self._busy_anim.stop()
            except Exception:
                pass

    def _set_running(self, action: str) -> None:
        self._active_action = action
        for b in (
            self.btn_refresh,
            self.btn_update_lists,
            self.btn_upgrade,
            self.btn_full,
            self.btn_autoremove,
        ):
            try:
                b.setEnabled(False)
            except Exception:
                pass
        try:
            self._busy_fx_table.setOpacity(0.55)
            self._busy_fx_log.setOpacity(1.0)
            self._busy_fx_activity.setOpacity(1.0)
        except Exception:
            pass
        self._clear_activity()
        self._set_output_panels_accent("orange")
        self._set_button_status(action, "running")
        self._set_badge(f"RUNNING {action.upper()}", "orange")

    def _is_action_running(self) -> bool:
        runner = self._action_runner
        return bool(runner and runner.is_active())

    def shutdown_running_action(self) -> bool:
        runner = self._action_runner
        if not runner or not runner.is_active():
            return True

        self._append_log("\n== Shutdown requested: attempting graceful stop ==")
        self._set_badge("STOPPING", "orange")
        if self._active_action:
            self._set_button_status(self._active_action, "attention")

        if runner.request_stop(2500):
            self._append_log("== Update action stopped cleanly ==")
            return True

        dlg = ConfirmDialog(
            self,
            "Update Still Running",
            "The package operation did not stop cleanly.\n\n"
            "Force shutdown now? This will terminate the running package command.",
            accent="red",
        )
        if dlg.exec() != QDialog.Accepted:
            self._append_log("== Shutdown cancelled: update action still running ==")
            return False

        self._append_log("== Forcing update action shutdown ==")
        if runner.force_stop(2000):
            self._append_log("== Update action terminated ==")
            return True

        self._append_log("== Failed to terminate update action ==")
        QMessageBox.warning(
            self,
            "Shutdown blocked",
            "The update process is still running and could not be terminated.\n"
            "Laptop Health will remain open.",
        )
        return False

    def _tick_busy_badge(self) -> None:
        self._busy_anim_tick = (self._busy_anim_tick + 1) % 4
        dots = "." * self._busy_anim_tick
        self._set_badge(f"REFRESHING{dots}", "blue")

    def _append_log(self, text: str):
        if text:
            self.log.append(text)

    def refresh(self):
        self._refresh_failed = False
        self._set_busy(True, "\n== Refreshing updates list… ==")

        def job():
            total, sec = get_update_count()
            reb = reboot_required()
            items = list_upgradable()
            kept = list_kept_back()
            held = list_holds()
            return total, sec, reb, items, kept, held

        w = QtWorker(job)
        w.signals.result.connect(self._on_refresh)
        w.signals.error.connect(self._on_refresh_error)
        w.signals.finished.connect(lambda: self._set_busy(False))
        self._workers.append(w)
        self._start_worker(w)

    def _on_refresh(self, res):
        total, sec, reb, items, kept, held = res
        kept_set = set(kept or [])
        held_set = set(held or [])
        self._set_status(total, sec, reb, len(kept_set), len(held_set))
        self._fill_table(items, kept_set, held_set)

    def _on_refresh_error(self, error):
        self._refresh_failed = True
        self._append_log(f"[refresh error] {error}")

    def _confirm_and_run(self, action: str):
        cmd = get_apt_action_description(action)
        messages = {
            "update": f"This will update package lists ({cmd}).\n\nAdministrator privileges required.\nYou may be prompted for your password.",
            "upgrade": f"This will install available upgrades ({cmd}).\n\nAdministrator privileges required.\nYou may be prompted for your password.",
            "full-upgrade": f"This will perform a full upgrade ({cmd}).\nIt may remove or replace packages.\n\nAdministrator privileges required.\nYou may be prompted for your password.",
            "autoremove": f"This will remove unused packages ({cmd}).\n\nAdministrator privileges required.\nYou may be prompted for your password.",
        }

        accent = "red" if action == "full-upgrade" else "orange"
        dlg = ConfirmDialog(self, action.replace("-", " ").title(), messages.get(action, action), accent=accent)
        if dlg.exec() != QDialog.Accepted:
            return

        self._append_log(f"\n== Running: {action} ==")
        self._set_running(action)

        self._action_runner = AptActionRunner(action, self)
        self._action_runner.line.connect(self._handle_action_output)
        self._action_runner.done.connect(self._on_stream_action_done)
        self._action_runner.start()

    def _on_stream_action_done(self, rc: int):
        self._append_log(f"== Exit code: {rc} ==")
        self._action_runner = None
        self._mark_all_activity_complete(rc == 0)

        for b in (self.btn_update_lists, self.btn_upgrade, self.btn_full, self.btn_autoremove, self.btn_refresh):
            b.setEnabled(True)

        if rc == 0:
            if self._active_action:
                self._set_button_status(self._active_action, "success")
            self._set_badge("COMPLETE", "green")
        else:
            if self._active_action:
                self._set_button_status(self._active_action, "error")
            self._set_badge("FAILED", "red")

        try:
            self._busy_fx_table.setOpacity(1.0)
            self._busy_fx_log.setOpacity(1.0)
            self._busy_fx_activity.setOpacity(1.0)
        except Exception:
            pass

        self._set_output_panels_accent("blue")

        self.refresh()

    def _on_action_done(self, res):
        rc, out = res if isinstance(res, tuple) and len(res) == 2 else (1, str(res))
        self._append_log(out or "(no output)")
        self._append_log(f"== Exit code: {rc} ==")

        for b in (self.btn_update_lists, self.btn_upgrade, self.btn_full, self.btn_autoremove, self.btn_refresh):
            b.setEnabled(True)

        self.refresh()

    def _start_worker(self, w: QtWorker):
        from PySide6.QtCore import QThreadPool
        QThreadPool.globalInstance().start(w)
