from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QTextEdit, QFrame, QStyle,
)

from ui_v2.qtworker import QtWorker
from ui_v2.services.updates import get_update_count, reboot_required, list_upgradable, run_apt_action


# Accent colors used only for badge text (keeps rest controlled by your global QSS)
_ACCENT_TEXT = {
    "green": "rgba(120, 255, 190, 0.95)",
    "orange": "rgba(255, 190, 120, 0.95)",
    "red": "rgba(255, 130, 130, 0.95)",
    "blue": "rgba(150, 190, 255, 0.95)",
    "purple": "rgba(200, 170, 255, 0.95)",
}

_PAGE_QSS = """
/* --- Buttons (crisp, consistent) --- */
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
QPushButton#ActionBtn:pressed {
    background: rgba(255,255,255,0.06);
}
QPushButton#ActionBtn:disabled {
    color: rgba(255,255,255,0.35);
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
}

/* --- Table (premium, dark, subtle) --- */
QTableWidget#UpdatesTable {
    background: rgba(10, 14, 22, 0.52);
    alternate-background-color: rgba(255,255,255,0.035);
    color: rgba(255,255,255,0.90);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 12px;
    gridline-color: rgba(255,255,255,0.06);
    selection-background-color: rgba(255,255,255,0.10);
    selection-color: rgba(255,255,255,0.96);
}
QHeaderView::section {
    background: rgba(255,255,255,0.07);
    color: rgba(255,255,255,0.88);
    padding: 8px 10px;
    border: 0px;
    border-bottom: 1px solid rgba(255,255,255,0.10);
}
QTableWidget::item {
    padding: 7px 10px;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}
QTableCornerButton::section {
    background: rgba(255,255,255,0.07);
    border: 0px;
}

/* --- Output log --- */
QTextEdit#UpdatesLog {
    background: rgba(10, 14, 22, 0.52);
    color: rgba(255,255,255,0.88);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 12px;
    padding: 10px;
}

/* --- Dark Scrollbars --- */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 4px 0 4px 0;
}
QScrollBar::handle:vertical {
    background: rgba(255,255,255,0.18);
    border-radius: 5px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(255,255,255,0.28);
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0 4px 0 4px;
}
QScrollBar::handle:horizontal {
    background: rgba(255,255,255,0.18);
    border-radius: 5px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background: rgba(255,255,255,0.28);
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0px;
}
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
}
"""


def _mk_btn(text: str, icon, tip: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("ActionBtn")
    b.setIcon(icon)
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip(tip)
    return b


class UpdatesPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(_PAGE_QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        # Title row
        top = QHBoxLayout()
        title = QLabel("Updates")
        title.setObjectName("HeroTitle")
        top.addWidget(title)
        top.addStretch(1)

        self.btn_refresh = _mk_btn(
            "Refresh",
            self.style().standardIcon(QStyle.SP_BrowserReload),
            "Refresh pending updates list"
        )
        self.btn_refresh.clicked.connect(self.refresh)
        top.addWidget(self.btn_refresh)

        root.addLayout(top)

        # Status strip (Card)
        self.status = QFrame()
        self.status.setObjectName("Card")
        self.status.setProperty("accent", "orange")
        st = QHBoxLayout(self.status)
        st.setContentsMargins(14, 12, 14, 12)
        st.setSpacing(16)

        self.lbl_total = QLabel("Total: —")
        self.lbl_total.setObjectName("CardSub")
        st.addWidget(self.lbl_total)

        self.lbl_sec = QLabel("Security: —")
        self.lbl_sec.setObjectName("CardSub")
        st.addWidget(self.lbl_sec)

        self.lbl_reboot = QLabel("Reboot: —")
        self.lbl_reboot.setObjectName("CardSub")
        st.addWidget(self.lbl_reboot)

        st.addStretch(1)

        self.badge = QLabel("—")
        self.badge.setObjectName("Badge")
        st.addWidget(self.badge)

        root.addWidget(self.status)

        # Toolbar (Card)
        self.toolbar = QFrame()
        self.toolbar.setObjectName("Card")
        self.toolbar.setProperty("accent", "blue")
        tb = QHBoxLayout(self.toolbar)
        tb.setContentsMargins(12, 10, 12, 10)
        tb.setSpacing(10)

        self.btn_update_lists = _mk_btn(
            "Update lists",
            self.style().standardIcon(QStyle.SP_BrowserReload),
            "Runs: apt update"
        )
        self.btn_update_lists.clicked.connect(lambda: self._confirm_and_run("update"))
        tb.addWidget(self.btn_update_lists)

        self.btn_upgrade = _mk_btn(
            "Upgrade",
            self.style().standardIcon(QStyle.SP_ArrowUp),
            "Runs: apt -y upgrade"
        )
        self.btn_upgrade.clicked.connect(lambda: self._confirm_and_run("upgrade"))
        tb.addWidget(self.btn_upgrade)

        self.btn_full = _mk_btn(
            "Full upgrade",
            self.style().standardIcon(QStyle.SP_DialogApplyButton),
            "Runs: apt -y full-upgrade (may remove/replace packages)"
        )
        self.btn_full.clicked.connect(lambda: self._confirm_and_run("full-upgrade"))
        tb.addWidget(self.btn_full)

        self.btn_autoremove = _mk_btn(
            "Autoremove",
            self.style().standardIcon(QStyle.SP_TrashIcon),
            "Runs: apt -y autoremove"
        )
        self.btn_autoremove.clicked.connect(lambda: self._confirm_and_run("autoremove"))
        tb.addWidget(self.btn_autoremove)

        tb.addStretch(1)
        root.addWidget(self.toolbar)

        # ---- Font unification ----
        # Use CardSub label font as the "system UI v2 font" reference for this page.
        base_font = self.lbl_total.font()
        base_font.setPointSize(max(9, base_font.pointSize()))  # keep consistent + readable

        for b in (self.btn_refresh, self.btn_update_lists, self.btn_upgrade, self.btn_full, self.btn_autoremove):
            b.setFont(base_font)

        # Table
        self.table = QTableWidget(0, 3)
        self.table.setObjectName("UpdatesTable")
        self.table.setHorizontalHeaderLabels(["Package", "Origin", "Security"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)  # cleaner
        self.table.setFont(base_font)

        hdr_font = QFont(base_font)
        hdr_font.setBold(True)
        self.table.horizontalHeader().setFont(hdr_font)

        root.addWidget(self.table, 1)

        # Output log (keep monospace, but soften)
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
        col = _ACCENT_TEXT.get(accent, "rgba(255,255,255,0.85)")
        # Make the badge text pop (without messing with the global badge styling)
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

            # Security rows: make them stand out in a premium way (bold + accent-ish text)
            if sec_flag:
                f = name.font()
                f.setBold(True)
                name.setFont(f)
                origin.setFont(f)
                sec.setFont(f)

                name.setForeground(Qt.white)
                origin.setForeground(Qt.white)
                sec.setForeground(Qt.white)

            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, origin)
            self.table.setItem(r, 2, sec)

    def _append_log(self, text: str):
        if not text:
            return
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
        desc = {
            "update": "Update package lists (apt update).",
            "upgrade": "Install available upgrades (apt -y upgrade).",
            "full-upgrade": "Perform full upgrade (apt -y full-upgrade). May remove/replace packages.",
            "autoremove": "Remove unused packages (apt -y autoremove).",
        }.get(action, action)

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Confirm system change")
        box.setText(desc)
        box.setInformativeText(
            "This will require administrator privileges.\n"
            "You may be prompted for your password.\n"
            "Proceed?"
        )
        box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec() != QMessageBox.Ok:
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

        box = QMessageBox(self)
        box.setWindowTitle("Completed" if rc == 0 else "Failed")
        box.setIcon(QMessageBox.Information if rc == 0 else QMessageBox.Critical)
        box.setText("Command completed successfully." if rc == 0 else "Command failed or was cancelled.")
        if out:
            box.setDetailedText(out)
        box.exec()

    def _start_worker(self, w: QtWorker):
        from PySide6.QtCore import QThreadPool
        QThreadPool.globalInstance().start(w)
