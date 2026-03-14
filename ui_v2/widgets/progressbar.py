from __future__ import annotations
from typing import Optional
from PySide6.QtWidgets import QProgressBar

class SlimBar(QProgressBar):
    def __init__(self, parent: Optional[object] = None):
        super().__init__(parent)
        self.setRange(0, 100)
        self.setTextVisible(False)
        self.setFixedHeight(16)
        self.setObjectName("SlimBar")
