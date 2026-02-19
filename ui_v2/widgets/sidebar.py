from __future__ import annotations
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QStyle, QVBoxLayout

class Sidebar(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(260)

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        hdr = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(self.style().standardIcon(QStyle.SP_DesktopIcon).pixmap(28, 28))
        title = QLabel("Laptop Health")
        title.setObjectName("AppTitle")
        hdr.addWidget(logo)
        hdr.addWidget(title)
        hdr.addStretch(1)
        v.addLayout(hdr)

        v.addSpacing(6)

        self.buttons: dict[str, QPushButton] = {}
        for key, label in [
            ("dashboard", "System Overview"),
            ("power", "Power & Thermal"),
            ("storage", "Disk & Storage"),
            ("network", "Network & Internet"),
            ("updates", "Pending Updates"),
            ("dev", "Dev Tools"),
        ]:
            b = QPushButton(label)
            b.setObjectName("NavBtn")
            b.setCheckable(True)
            self.buttons[key] = b
            v.addWidget(b)

        v.addStretch(1)

        for label in ["Logs", "Settings"]:
            b = QPushButton(label)
            b.setObjectName("NavBtnSecondary")
            v.addWidget(b)

        self.set_active("dashboard")

    def set_active(self, key: str) -> None:
        for k, b in self.buttons.items():
            b.setChecked(False)
            b.setProperty("active", "")
            b.style().unpolish(b); b.style().polish(b)
        if key in self.buttons:
            b = self.buttons[key]
            b.setChecked(True)
            b.setProperty("active", "1")
            b.style().unpolish(b); b.style().polish(b)
