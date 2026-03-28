from __future__ import annotations

import os
import webbrowser
from PySide6.QtCore import Qt
DEV_MODE = os.getenv("LAPTOP_HEALTH_DEV", "").strip().lower() in ("1","true","yes","on")

from PySide6.QtWidgets import QFrame, QVBoxLayout, QPushButton, QLabel, QStyle
from ui_v2.version import APP_VERSION
from ui_v2.services.update_checker import check_for_updates


class Sidebar(QFrame):
    """
    Compatible with ui_v2/app.py:
      - exposes self.buttons dict with keys app.py expects
      - includes icons
    """
    def __init__(self):
        super().__init__()
        self.setObjectName("Sidebar")
        self.buttons: dict[str, QPushButton] = {}
        self._release_url: str | None = None

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(12)

        title = QLabel("Laptop Health")
        title.setObjectName("AppTitle")
        v.addWidget(title)

        def mk(key: str, text: str, icon_enum) -> QPushButton:
            btn = QPushButton(text)
            btn.setObjectName("NavBtn")
            btn.setIcon(self.style().standardIcon(icon_enum))
            self.buttons[key] = btn
            v.addWidget(btn)
            return btn

        mk("dashboard", "Overview", QStyle.SP_DesktopIcon)
        mk("power", "Power && Thermal", QStyle.SP_ComputerIcon)
        mk("network", "Network", QStyle.SP_DriveNetIcon)
        mk("storage", "Storage", QStyle.SP_DriveHDIcon)
        mk("updates", "Updates", QStyle.SP_MessageBoxWarning)

        if DEV_MODE:

            dev_btn = mk("dev", "Dev Tools", QStyle.SP_FileDialogDetailedView)

        # Alias for any newer code paths
        if DEV_MODE:
            self.buttons["devtools"] = dev_btn

        v.addStretch(1)

        self.version_label = QLabel(APP_VERSION)
        self.version_label.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        self.version_label.setStyleSheet(
            "color: rgba(255,255,255,0.50);"
            "font-size: 11px;"
            "padding: 2px 4px 0 4px;"
        )
        v.addWidget(self.version_label)

        self.update_status_label = QLabel("")
        self.update_status_label.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        self.update_status_label.setCursor(Qt.PointingHandCursor)
        self.update_status_label.setStyleSheet(
            "color: rgba(255,255,255,0.0);"
            "font-size: 11px;"
            "padding: 0 4px 0 4px;"
        )
        self.update_status_label.mousePressEvent = self._open_release
        v.addWidget(self.update_status_label)

        self._check_updates()

    def _check_updates(self):
        result = check_for_updates(APP_VERSION)
        if not result.ok:
            self._release_url = None
            self.update_status_label.clear()
            return

        self._release_url = result.release_url
        if result.update_available and result.latest_version:
            self.update_status_label.setText(f"⬤ Update available ({result.latest_version})")
            self.update_status_label.setStyleSheet(
                "color: rgba(251,146,60,0.96);"
                "font-size: 11px;"
                "padding: 0 4px 0 4px;"
            )
            return

        self.update_status_label.setText("Up to date")
        self.update_status_label.setStyleSheet(
            "color: rgba(255,255,255,0.55);"
            "font-size: 11px;"
            "padding: 0 4px 0 4px;"
        )

    def _open_release(self, event):
        if self._release_url:
            webbrowser.open(self._release_url)
        if event is not None:
            event.accept()
