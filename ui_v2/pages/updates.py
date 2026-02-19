from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout
from ui_v2.widgets.cards import UpdatesCard

class UpdatesPage(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        v.addWidget(UpdatesCard("red"))
        v.addStretch(1)
