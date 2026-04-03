from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class ExportReportDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setObjectName("ExportReportDialog")

        host = parent.window() if parent is not None else None
        if host is not None:
            self.setGeometry(host.geometry())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scrim = QFrame()
        scrim.setObjectName("ExportScrim")
        scrim_l = QVBoxLayout(scrim)
        scrim_l.setContentsMargins(0, 0, 0, 0)
        scrim_l.setSpacing(0)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(1)

        card = QFrame()
        card.setObjectName("ExportCard")
        card.setFixedWidth(420)
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(16, 16, 16, 16)
        card_l.setSpacing(10)

        title = QLabel("Choose report sections")
        title.setObjectName("DialogTitle")
        card_l.addWidget(title)

        subtitle = QLabel("Select which sections to include in the PDF report.")
        subtitle.setObjectName("DialogSubtitle")
        subtitle.setWordWrap(True)
        card_l.addWidget(subtitle)

        card_l.addWidget(_sep())

        hint = QLabel("Dashboard and Updates are optional. Use All pages for the remaining sections.")
        hint.setObjectName("DialogHint")
        hint.setWordWrap(True)
        card_l.addWidget(hint)

        self.chk_all = QCheckBox("All pages")
        self.chk_all.setTristate(False)
        self.chk_all.setToolTip("Toggle Power, Storage, Network, and Dev/Tools")
        card_l.addWidget(self.chk_all)

        self.chk_dashboard = QCheckBox("Dashboard screenshot")
        self.chk_updates = QCheckBox("Updates summary")
        self.chk_power = QCheckBox("Power summary")
        self.chk_storage = QCheckBox("Storage summary")
        self.chk_network = QCheckBox("Network summary")
        self.chk_devtools = QCheckBox("Dev/tools logs")

        # Defaults
        self.chk_dashboard.setChecked(True)
        self.chk_updates.setChecked(True)

        group_a = QVBoxLayout()
        group_a.addWidget(self.chk_dashboard)
        group_a.addWidget(self.chk_updates)

        group_b = QVBoxLayout()
        group_b.addWidget(self.chk_power)
        group_b.addWidget(self.chk_storage)
        group_b.addWidget(self.chk_network)
        group_b.addWidget(self.chk_devtools)

        card_l.addLayout(group_a)
        card_l.addWidget(_sep())
        card_l.addLayout(group_b)

        card_l.addWidget(_sep())

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.btn_all = self.buttons.addButton("Select all", QDialogButtonBox.ActionRole)
        self.btn_none = self.buttons.addButton("Select none", QDialogButtonBox.ActionRole)
        card_l.addWidget(self.buttons)

        self.chk_all.toggled.connect(self._on_all_toggle)
        for chk in self._section_checkboxes():
            chk.stateChanged.connect(self._on_section_toggle)

        self.btn_all.clicked.connect(self._select_all)
        self.btn_none.clicked.connect(self._select_none)

        self._sync_all_state()
        self._sync_ok_state()

        self.setMinimumWidth(360)
        self._apply_theme()
        row.addWidget(card)
        row.addStretch(1)
        scrim_l.addStretch(1)
        scrim_l.addLayout(row)
        scrim_l.addStretch(1)
        root.addWidget(scrim)

    def selected_sections(self) -> dict[str, bool]:
        return {
            "dashboard": self.chk_dashboard.isChecked(),
            "updates": self.chk_updates.isChecked(),
            "power": self.chk_power.isChecked(),
            "storage": self.chk_storage.isChecked(),
            "network": self.chk_network.isChecked(),
            "devtools": self.chk_devtools.isChecked(),
        }

    def _section_checkboxes(self) -> list[QCheckBox]:
        return [
            self.chk_dashboard,
            self.chk_updates,
            self.chk_power,
            self.chk_storage,
            self.chk_network,
            self.chk_devtools,
        ]

    def _page_checkboxes(self) -> list[QCheckBox]:
        return [
            self.chk_power,
            self.chk_storage,
            self.chk_network,
            self.chk_devtools,
        ]

    def _on_all_toggle(self, checked: bool) -> None:
        for chk in self._page_checkboxes():
            blocked = chk.blockSignals(True)
            chk.setChecked(checked)
            chk.blockSignals(blocked)
        self._sync_ok_state()

    def _on_section_toggle(self, _state: int) -> None:
        self._sync_all_state()
        self._sync_ok_state()

    def _sync_all_state(self) -> None:
        all_checked = all(chk.isChecked() for chk in self._page_checkboxes())
        block = self.chk_all.blockSignals(True)
        self.chk_all.setCheckState(Qt.Checked if all_checked else Qt.Unchecked)
        self.chk_all.blockSignals(block)

    def _sync_ok_state(self) -> None:
        any_checked = any(chk.isChecked() for chk in self._section_checkboxes())
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(any_checked)

    def _select_all(self) -> None:
        for chk in self._section_checkboxes():
            chk.setChecked(True)
        self._sync_all_state()
        self._sync_ok_state()

    def _select_none(self) -> None:
        for chk in self._section_checkboxes():
            chk.setChecked(False)
        self._sync_all_state()
        self._sync_ok_state()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QFrame#ExportScrim {
                background: rgba(0, 0, 0, 0.55);
            }
            QFrame#ExportCard {
                background: #0b1220;
                border: 1px solid rgba(255,255,255,0.14);
                border-left: 6px solid rgba(96,165,250,0.95);
                border-radius: 16px;
            }
            QLabel#DialogTitle {
                color: #e8f0ff;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#DialogSubtitle {
                color: #9fb0c6;
                font-size: 12px;
            }
            QLabel#DialogHint {
                color: #cfe0ff;
                font-size: 12px;
            }
            QCheckBox {
                color: #e8f0ff;
                spacing: 8px;
                font-size: 12px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid rgba(255,255,255,0.25);
                background: rgba(255,255,255,0.06);
            }
            QCheckBox::indicator:checked {
                background: rgba(96,165,250,0.9);
                border: 1px solid rgba(96,165,250,0.9);
            }
            QDialogButtonBox QPushButton {
                color: rgba(255,255,255,0.92);
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.14);
                padding: 7px 12px;
                border-radius: 10px;
                min-width: 90px;
            }
            QDialogButtonBox QPushButton:hover {
                background: rgba(255,255,255,0.12);
                border: 1px solid rgba(255,255,255,0.18);
            }
            QDialogButtonBox QPushButton:pressed {
                background: rgba(255,255,255,0.06);
            }
            QFrame {
                color: rgba(255,255,255,0.18);
            }
            """
        )

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(e)


def _sep() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line
