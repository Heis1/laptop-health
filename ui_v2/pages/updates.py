from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QTextEdit, QFrame, QStyle, QDialog,
)

from ui_v2.qtworker import QtWorker
from ui_v2.services.updates import get_update_count, reboot_required, list_upgradable, run_apt_action


_ACCENT_STRIP = {
    "green": "rgba(120, 255, 190, 0.95)",
    "orange": "rgba(255, 190, 120, 0.95)",
    "red": "rgba(255, 130, 130, 0.95)",
    "blue": "rgba(150, 190, 255, 0.95)",
    "purple": "rgba(200, 170, 255, 0.95)",
}

_PAGE_QSS = """
QPushButton#ActionBtn {
    color: rgba(255,255,255,0.92);
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.14);
    padding: 7px 12px;
    border-radius: 10px;
}
QPushButton#ActionBtn:hover {
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.18);
}
QPushButton#ActionBtn:pressed { background: rgba(255,255,255,0.06); }
QPushButton#ActionBtn:disabled {
    color: rgba(255,255,255,0.35);
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
}

/* Output log */
QTextEdit#UpdatesLog {
    background: rgba(10, 14, 22, 0.52);
    color: rgba(255,255,255,0.88);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 12px;
    padding: 10px;
}

/* Scrollbars */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 6px 0 6px 0;
}
QScrollBar::handle:vertical {
    background: rgba(255,255,255,0.18);
    border-radius: 5px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.28); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0 6px 0 6px;
}
QScrollBar::handle:horizontal {
    background: rgba(255,255,255,0.18);
    border-radius: 5px;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover { background: rgba(255,255,255,0.28); }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
"""

_TABLE_QSS = """
QTableWidget#UpdatesTable {
    background: transparent;
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 12px;
    color: rgba(255,255,255,0.90);
    selection-background-color: rgba(255,255,255,0.12);
    selection-color: rgba(255,255,255,0.96);
    outline: 0;
}
QTableWidget#UpdatesTable::viewport {
    background: rgba(10, 14, 22, 0.52);
    border-radius: 12px;
}
QTableWidget::item {
    padding: 7px 10px;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    background: transparent;
}
QTableWidget::item:hover { background: rgba(255,255,255,0.06); }
QTableWidget::item:selected { background: rgba(255,255,255,0.12); }
QTableWidget::item:selected:hover { background: rgba(255,255,255,0.14); }

QTableCornerButton::section {
    background: rgba(255,255,255,0.07);
    border: 0px;
}
"""

_HDR_QSS = """
QHeaderView { background: rgba(10, 14, 22, 0.52); }
QHeaderView::section {
    background: rgba(255,255,255,0.07);
    color: rgba(255,255,255,0.88);
    padding: 8px 10px;
    border: 0px;
    border-bottom: 1px solid rgba(255,255,255,0.10);
}
"""


def _mk_btn(text: str, icon, tip: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("ActionBtn")
    b.setIcon(icon)
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip(tip)
    return b



class ConfirmDialog(QDialog):
    """
    Premium in-app confirm dialog:
    - Frameless (no OS title bar / no white header)
    - Dimmed backdrop (scrim) so text is readable over any page
    - Centered opaque card with accent strip
    """
    def __init__(self, parent: QWidget, title: str, message: str, accent: str = "orange"):
        super().__init__(parent)

        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # Match the parent window geometry (so the scrim covers everything)
        host = parent.window()
        self.setGeometry(host.geometry())

        strip = _ACCENT_STRIP.get(accent, "rgba(255,190,120,0.95)")

        # Root layout = scrim + centered card
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scrim = QFrame()
        scrim.setObjectName("ConfirmScrim")
        scrim_lay = QVBoxLayout(scrim)
        scrim_lay.setContentsMargins(0, 0, 0, 0)
        scrim_lay.setSpacing(0)

        # Center row
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

        # Close "x"
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

        # Click outside to cancel
        scrim.mousePressEvent = lambda e: self.reject()

        # Styling (self-contained, no reliance on page styles)
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
        self.setStyleSheet(_PAGE_QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 16, 18)
        root.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("Updates")
        title.setObjectName("HeroTitle")
        top.addWidget(title)
        top.addStretch(1)

        self.btn_refresh = _mk_btn("Refresh", self.style().standardIcon(QStyle.SP_BrowserReload), "Refresh pending updates list")
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
        st.addStretch(1)
        self.badge = QLabel("—"); self.badge.setObjectName("Badge"); st.addWidget(self.badge)
        root.addWidget(self.status)

        self.toolbar = QFrame()
        self.toolbar.setObjectName("Card")
        self.toolbar.setProperty("accent", "blue")
        tb = QHBoxLayout(self.toolbar)
        tb.setContentsMargins(12, 10, 12, 10)
        tb.setSpacing(10)

        self.btn_update_lists = _mk_btn("Update lists", self.style().standardIcon(QStyle.SP_BrowserReload), "Runs: apt update")
        self.btn_update_lists.clicked.connect(lambda: self._confirm_and_run("update"))
        tb.addWidget(self.btn_update_lists)

        self.btn_upgrade = _mk_btn("Upgrade", self.style().standardIcon(QStyle.SP_ArrowUp), "Runs: apt -y upgrade")
        self.btn_upgrade.clicked.connect(lambda: self._confirm_and_run("upgrade"))
        tb.addWidget(self.btn_upgrade)

        self.btn_full = _mk_btn("Full upgrade", self.style().standardIcon(QStyle.SP_DialogApplyButton),
                                "Runs: apt -y full-upgrade (may remove/replace packages)")
        self.btn_full.clicked.connect(lambda: self._confirm_and_run("full-upgrade"))
        tb.addWidget(self.btn_full)

        self.btn_autoremove = _mk_btn("Autoremove", self.style().standardIcon(QStyle.SP_TrashIcon), "Runs: apt -y autoremove")
        self.btn_autoremove.clicked.connect(lambda: self._confirm_and_run("autoremove"))
        tb.addWidget(self.btn_autoremove)

        tb.addStretch(1)
        root.addWidget(self.toolbar)

        base_font = self.lbl_total.font()
        base_font.setPointSize(max(9, base_font.pointSize()))
        for b in (self.btn_refresh, self.btn_update_lists, self.btn_upgrade, self.btn_full, self.btn_autoremove):
            b.setFont(base_font)

        self.table = QTableWidget(0, 3)
        self.table.setObjectName("UpdatesTable")
        self.table.setStyleSheet(_TABLE_QSS)
        self.table.setHorizontalHeaderLabels(["Package", "Origin", "Security"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setFont(base_font)
        self.table.setFocusPolicy(Qt.NoFocus)

        hdr = self.table.horizontalHeader()
        hdr.setStyleSheet(_HDR_QSS)
        hdr.setHighlightSections(False)
        hdr.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hdr.setMinimumHeight(34)

        hdr_font = QFont(base_font); hdr_font.setBold(True)
        hdr.setFont(hdr_font)

        root.addWidget(self.table, 1)

        self.log = QTextEdit()
        self.log.setObjectName("UpdatesLog")
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Output will appear here…")

        mono = QFont()
        mono.setFamilies(["JetBrains Mono", "Fira Code", "Monospace"])
        mono.setPointSize(max(9, base_font.pointSize() - 1))
        self.log.setFont(mono)
        self.log.setMinimumHeight(150)
        root.addWidget(self.log)

        self._workers: list[QtWorker] = []
        self.refresh()

    def _set_badge(self, text: str, accent: str):
        self.badge.setText(text)
        col = _ACCENT_STRIP.get(accent, "rgba(255,255,255,0.85)")
        self.badge.setStyleSheet(f"color: {col};")

    def _set_status(self, total: int | None, sec: int | None, reb: bool):
        if total is None:
            self.lbl_total.setText("Total: —")
            self.lbl_sec.setText("Security: —")
            self.lbl_reboot.setText("Reboot: —")
            accent = "red"
            self._set_badge("Unknown", accent)
        else:
            total = int(total)
            sec = 0 if sec is None else int(sec)
            self.lbl_total.setText(f"Total: {total}")
            self.lbl_sec.setText(f"Security: {sec}")
            self.lbl_reboot.setText("Reboot: Yes" if reb else "Reboot: No")

            if total == 0 and not reb:
                accent = "green"
                self._set_badge("OK", accent)
            else:
                accent = "red" if (sec > 0 or reb) else "orange"
                self._set_badge("Attention", accent)

        self.status.setProperty("accent", accent)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.update()

    def _fill_table(self, items: list[dict]):
        self.table.setRowCount(0)
        for it in items:
            r = self.table.rowCount()
            self.table.insertRow(r)

            name = QTableWidgetItem(it.get("name", ""))
            origin = QTableWidgetItem(it.get("origin", ""))
            sec_flag = bool(it.get("security"))
            sec = QTableWidgetItem("Yes" if sec_flag else "No")
            sec.setTextAlignment(Qt.AlignCenter)

            if sec_flag:
                f = name.font(); f.setBold(True)
                name.setFont(f); origin.setFont(f); sec.setFont(f)

            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, origin)
            self.table.setItem(r, 2, sec)

    def _append_log(self, text: str):
        if text:
            self.log.append(text)

    def refresh(self):
        def job():
            total, sec = get_update_count()
            reb = reboot_required()
            items = list_upgradable()
            return total, sec, reb, items

        w = QtWorker(job)
        w.signals.result.connect(self._on_refresh)
        w.signals.error.connect(lambda e: self._append_log(f"[refresh error] {e}"))
        self._workers.append(w)
        self._start_worker(w)

    def _on_refresh(self, res):
        total, sec, reb, items = res
        self._set_status(total, sec, reb)
        self._fill_table(items)

    def _confirm_and_run(self, action: str):
        messages = {
            "update": "This will update package lists (apt update).\n\nAdministrator privileges required.\nYou may be prompted for your password.",
            "upgrade": "This will install available upgrades (apt -y upgrade).\n\nAdministrator privileges required.\nYou may be prompted for your password.",
            "full-upgrade": "This will perform a full upgrade (apt -y full-upgrade).\nIt may remove or replace packages.\n\nAdministrator privileges required.\nYou may be prompted for your password.",
            "autoremove": "This will remove unused packages (apt -y autoremove).\n\nAdministrator privileges required.\nYou may be prompted for your password.",
        }

        accent = "red" if action == "full-upgrade" else "orange"
        dlg = ConfirmDialog(self, action.replace("-", " ").title(), messages.get(action, action), accent=accent)
        if dlg.exec() != QDialog.Accepted:
            return

        for b in (self.btn_update_lists, self.btn_upgrade, self.btn_full, self.btn_autoremove, self.btn_refresh):
            b.setEnabled(False)

        self._append_log(f"\n== Running: {action} ==")

        w = QtWorker(lambda: run_apt_action(action))
        w.signals.result.connect(self._on_action_done)
        w.signals.error.connect(lambda e: self._on_action_done((1, str(e))))
        self._workers.append(w)
        self._start_worker(w)

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
