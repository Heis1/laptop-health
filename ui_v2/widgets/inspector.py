from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget
from ui_v2.widgets.cards import MetricCard

class Inspector(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Inspector")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        hdr = QHBoxLayout()
        self.toggle = QToolButton()
        self.toggle.setObjectName("InspectorToggle")
        self.toggle.setText("System Inspector")
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.DownArrow)
        self.toggle.clicked.connect(self._toggle)

        hdr.addWidget(self.toggle)
        hdr.addStretch(1)
        dots = QLabel("• • •")
        dots.setObjectName("InspectorDots")
        hdr.addWidget(dots)
        outer.addLayout(hdr)

        self.body = QWidget()
        grid = QGridLayout(self.body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        grid.addWidget(MetricCard("CPU", "—", "Max Temp • Throttle • Chart", "green", spark_points=[0.2,0.4,0.35,0.5,0.46,0.62,0.58]), 0, 0)
        grid.addWidget(MetricCard("Disk Usage", "—", "Root • Logs • SMART", "purple", spark_points=[0.1,0.18,0.22,0.2,0.3,0.26,0.33]), 0, 1)
        grid.addWidget(MetricCard("Network", "—", "Wakeups • Suggestions • Chart", "orange", spark_points=[0.25,0.5,0.3,0.65,0.4,0.85,0.55]), 0, 2)

        outer.addWidget(self.body)

    def _toggle(self):
        self.body.setVisible(self.toggle.isChecked())
        self.toggle.setArrowType(Qt.DownArrow if self.toggle.isChecked() else Qt.RightArrow)
