from __future__ import annotations

import os
DEV_MODE = os.getenv("LAPTOP_HEALTH_DEV", "").strip().lower() in ("1","true","yes","on")

from PySide6.QtWidgets import QFrame, QVBoxLayout, QPushButton, QLabel, QStyle


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
