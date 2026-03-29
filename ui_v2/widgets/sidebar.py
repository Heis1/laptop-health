from __future__ import annotations

import os
import webbrowser
from PySide6.QtCore import Qt
DEV_MODE = os.getenv("LAPTOP_HEALTH_DEV", "").strip().lower() in ("1","true","yes","on")
SIMULATE_UPDATE_AVAILABLE = os.getenv("LAPTOP_HEALTH_DEV_UPDATE_AVAILABLE", "").strip().lower() in ("1","true","yes","on")

from PySide6.QtWidgets import QFrame, QVBoxLayout, QPushButton, QLabel, QStyle
from ui_v2.services.devtools_state import get_sidebar_update_mode
from ui_v2.version import APP_VERSION, APP_RELEASE_DATE
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
        mk("updates", "Updates", QStyle.SP_BrowserReload)

        if DEV_MODE:

            dev_btn = mk("dev", "Dev Tools", QStyle.SP_FileDialogDetailedView)

        # Alias for any newer code paths
        if DEV_MODE:
            self.buttons["devtools"] = dev_btn

        v.addStretch(1)

        self.footer = QFrame()
        self.footer.setStyleSheet(
            "background: rgba(7,12,20,0.92);"
            "border: 1px solid rgba(96,165,250,0.18);"
            "border-radius: 12px;"
        )
        footer_l = QVBoxLayout(self.footer)
        footer_l.setContentsMargins(10, 8, 10, 8)
        footer_l.setSpacing(4)

        self.version_label = QLabel(self._version_text())
        self.version_label.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        self.version_label.setWordWrap(True)
        self.version_label.setStyleSheet(
            "color: rgba(191,219,254,0.72);"
            "font-size: 11px;"
            "padding: 0;"
        )
        footer_l.addWidget(self.version_label)

        self.update_status_label = QLabel("")
        self.update_status_label.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        self.update_status_label.setCursor(Qt.PointingHandCursor)
        self.update_status_label.setStyleSheet(
            "color: rgba(255,255,255,0.0);"
            "font-size: 11px;"
            "padding: 2px 8px;"
            "border-radius: 999px;"
            "background: transparent;"
        )
        self.update_status_label.mousePressEvent = self._open_release
        footer_l.addWidget(self.update_status_label)

        v.addWidget(self.footer)

        self._check_updates()

    def _check_updates(self):
        simulated_mode = get_sidebar_update_mode() if DEV_MODE else "real"
        if DEV_MODE and SIMULATE_UPDATE_AVAILABLE:
            simulated_mode = "available"

        if simulated_mode == "available":
            self._release_url = "https://github.com/Heis1/laptop-health/releases"
            self.update_status_label.setText("⬤ Update available (v9.9.9)")
            self.update_status_label.setStyleSheet(
                "color: rgb(255, 244, 230);"
                "font-size: 11px;"
                "padding: 2px 8px;"
                "border-radius: 999px;"
                "background: rgba(251,146,60,0.38);"
                "border: 1px solid rgba(253,186,116,0.78);"
            )
            return

        if simulated_mode == "current":
            self._release_url = "https://github.com/Heis1/laptop-health/releases"
            self.update_status_label.setText("Up to date")
            self.update_status_label.setStyleSheet(
                "color: rgb(220,252,231);"
                "font-size: 11px;"
                "padding: 2px 8px;"
                "border-radius: 999px;"
                "background: rgba(34,197,94,0.26);"
                "border: 1px solid rgba(74,222,128,0.62);"
            )
            return

        if simulated_mode == "error":
            self._release_url = None
            self.update_status_label.setText("Check failed")
            self.update_status_label.setStyleSheet(
                "color: rgb(254,226,226);"
                "font-size: 11px;"
                "padding: 2px 8px;"
                "border-radius: 999px;"
                "background: rgba(239,68,68,0.30);"
                "border: 1px solid rgba(248,113,113,0.62);"
            )
            return

        result = check_for_updates(APP_VERSION)
        if not result.ok:
            self._release_url = None
            self.update_status_label.clear()
            return

        self._release_url = result.release_url
        if result.update_available and result.latest_version:
            self.update_status_label.setText(f"⬤ Update available ({result.latest_version})")
            self.update_status_label.setStyleSheet(
                "color: rgb(255, 244, 230);"
                "font-size: 11px;"
                "padding: 2px 8px;"
                "border-radius: 999px;"
                "background: rgba(251,146,60,0.38);"
                "border: 1px solid rgba(253,186,116,0.78);"
            )
            return

        self.update_status_label.setText("Up to date")
        self.update_status_label.setStyleSheet(
            "color: rgb(220,252,231);"
            "font-size: 11px;"
            "padding: 2px 8px;"
            "border-radius: 999px;"
            "background: rgba(34,197,94,0.26);"
            "border: 1px solid rgba(74,222,128,0.62);"
        )

    def _version_text(self) -> str:
        release_date = (APP_RELEASE_DATE or "").strip()
        if release_date:
            return f"Version {APP_VERSION}\nReleased {release_date}"
        return f"Version {APP_VERSION}"
    def _open_release(self, event):
        if self._release_url:
            webbrowser.open(self._release_url)
        if event is not None:
            event.accept()
