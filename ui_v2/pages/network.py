from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from ui_v2.widgets.cards import MetricCard

class NetworkPage(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        v.addWidget(MetricCard("Network", "120 Mbps Down", "15 ms Latency", "purple"))
        v.addWidget(QPushButton("Run Speed Test"))
        v.addStretch(1)
