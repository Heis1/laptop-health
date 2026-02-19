from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from ui_v2.widgets.cards import MetricCard

class PowerPage(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        v.addWidget(MetricCard("CPU", "Wakeups: Warm", "Investigate high wake events", "orange"))
        v.addWidget(QPushButton("Investigate Wakeups"))
        v.addStretch(1)
