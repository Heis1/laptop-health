from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

class DevToolsPage(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        v.addWidget(QLabel("Dev Tools (placeholder)"))
        v.addStretch(1)
